"""PDF 원문 등록용 SQL mapper(``document_repository.sql``)를 호출하는 DB 접근 클래스.

Java 관점: MyBatis Mapper/DAO에 해당한다. SQL은 이 파일에 없고 같은 폴더의 ``document_repository.sql`` 에
``-- name: 쿼리이름`` 으로 정의되어 있으며, ``sql_session.select_list("document_repository.쿼리이름", 파라미터)`` 처럼
"파일명.쿼리이름" 으로 호출한다. 이름 끝의 ``!`` (예: insert_doc_page!)는 결과 행을 돌려주지 않는 변경 SQL이다.

트랜잭션: 이 클래스는 commit/rollback을 하지 않는다. ``RegisterService`` 가 ``with sql_session.transaction():``
블록으로 감싸서 호출한다. 트랜잭션 밖에서 호출하면 PostgresDbSession이 SQL마다 pool 연결을 빌려 바로 커밋한다.

관련 테이블: card_doc, card_doc_page, card_doc_chunk, card_product(존재 확인), card_product_doc(상품 연결),
            v_card_integrity_issue(verify_doc의 정합성 경고)

호출하는 곳: register_service.RegisterService, main.py(MAPPER_ROOT·RAW_TEXT_LOG_KEYS),
            그 밖의 CLI들이 MAPPER_ROOT를 공유한다.
"""

from __future__ import annotations

from pathlib import Path

from common.postgres_db_session import PostgresDbSession

from .block_chunking import SPLIT_RULE_BLOCK
from .document_service import DocChunk, ParsedDocument, page_chunks

MAPPER_ROOT = Path(__file__).resolve().parent
SYSTEM_USER_ID = "SYSTEM"   # 생성·수정 사용자 컬럼에 기록할 시스템 사용자 ID
RAW_TEXT_LOG_KEYS = ("PAGE_RAW_TXT", "CHUNK_RAW_TXT")   # SQL 로그에서 가릴 원문 파라미터


class DocRepository:
    """``document_repository.*`` statement를 실행한다.

    DB 연결과 트랜잭션은 주입받은 ``sql_session`` 이 관리한다.
    조회 결과 key를 컬럼명 그대로 받도록 ``camel_case_keys=False`` 세션을 전달한다.
    """

    def __init__(self, sql_session: PostgresDbSession):
        self.sql_session = sql_session

    def find_doc(self, doc_sha256: str, doc_cd: str) -> list[dict]:
        """해시 또는 문서 코드가 같은 기존 문서를 반환한다.

        중복 등록 방지의 첫 단계다. 호출자(RegisterService.register)가 결과를 보고
        같은 해시 → 재사용(ALREADY_REGISTERED), 같은 doc_cd·다른 해시 → RegisterError로 분기한다.
        """
        return self.sql_session.select_list(
            "document_repository.select_doc_by_sha256_or_cd",
            {"DOC_SHA256": doc_sha256, "DOC_CD": doc_cd},
        )

    def insert_doc(self, document: ParsedDocument) -> str:
        """문서 한 건을 등록하고 DB가 발급한 ``card_doc_id`` 를 반환한다.

        PK ``card_doc_id`` 는 컬럼 기본값(fn_get_biz_id)이 발급하고 ``RETURNING card_doc_id`` 로 돌려받는다.
        ``doc_version_no`` 는 SQL 안에서 같은 doc_family_cd의 MAX+1로 계산한다.
        이후 페이지·청크 INSERT는 이 값을 FK(card_doc_id)로 쓴다.
        """
        rows = self.sql_session.execute(
            "document_repository.insert_doc",
            {
                "DOC_CD": document.doc_cd,
                "DOC_FAMILY_CD": document.doc_family_cd,
                "DOC_TYPE_CD": document.doc_type_cd,
                "DOC_TITLE": document.doc_title,
                "DOC_SOURCE_URL": document.doc_source_url,
                "DOC_FILE_NM": document.doc_file_nm,
                "DOC_FILE_SIZE": document.doc_file_size,
                "DOC_SHA256": document.doc_sha256,
                "DOC_PAGE_CNT": len(document.pages),
                "DOC_REVIEW_NO": document.doc_review_no,
                "DOC_REVIEW_DATE": document.doc_review_date,
                "DOC_COLLECT_DATE": document.doc_collect_date,
                "DOC_NOTE": document.doc_note,
                "USER_ID": SYSTEM_USER_ID,
            },
        )
        return rows[0]["card_doc_id"]

    def insert_pages(self, card_doc_id: str, document: ParsedDocument) -> int:
        """페이지 원문을 일괄 등록하고 등록 건수를 반환한다.

        ``execute_many`` 는 같은 INSERT를 페이지 수만큼 반복 실행한다(JDBC addBatch와 비슷한 용도).
        card_doc_page의 식별자는 (card_doc_id, page_no)이며 둘 다 Python이 넘긴다.
        """
        return self.sql_session.execute_many(
            "document_repository.insert_doc_page",
            [
                {
                    "CARD_DOC_ID": card_doc_id,
                    "PAGE_NO": page.page_no,
                    "PAGE_RAW_TXT": page.text,
                    "PAGE_CHAR_CNT": page.char_cnt,
                    "PAGE_TXT_SHA256": page.sha256,
                    "PAGE_LAYER_CD": page.layer_cd,
                    "PAGE_EXTRACTOR_NM": page.extractor_nm,
                    "PAGE_EXTRACTOR_VER": page.extractor_ver,
                    "PAGE_NOTE": page.note,
                    "USER_ID": SYSTEM_USER_ID,
                }
                for page in document.pages
            ],
        )

    def add_block_chunks(self, card_doc_id: str) -> list[DocChunk]:
        """이미 등록된 문서에 BLOCK_V1 청크를 추가한다. 기존 청크·근거는 바꾸지 않는다.

        페이지 원문은 DB의 ``card_doc_page`` 를 그대로 쓴다. BLOCK_V1 청크가 이미 있으면 중복을 막기 위해 거부한다.
        호출자가 트랜잭션을 연다.
        """
        state = self.sql_session.select_one("document_repository.select_chunk_state", {"CARD_DOC_ID": card_doc_id})
        if not state or not state["page_cnt"]:
            raise ValueError(f"페이지가 없는 문서입니다: {card_doc_id}")
        if SPLIT_RULE_BLOCK in (state["split_rules"] or []):
            raise ValueError(f"{SPLIT_RULE_BLOCK} 청크가 이미 있습니다: {card_doc_id}")
        chunks: list[DocChunk] = []
        for page in self.sql_session.select_list("document_repository.select_page_texts", {"CARD_DOC_ID": card_doc_id}):
            if page["page_raw_txt"].strip():
                status = "EXCLUDED" if (page["page_note"] or "").startswith("OCR_REVIEW") else "RAW"
                chunks.extend(page_chunks(page["page_no"], page["page_raw_txt"], state["max_seq"] + len(chunks) + 1,
                                          SPLIT_RULE_BLOCK, status))
        self._insert_chunk_rows(card_doc_id, chunks)
        return chunks

    def insert_chunks(self, card_doc_id: str, document: ParsedDocument) -> int:
        """청크를 일괄 등록하고 등록 건수를 반환한다. 청크 ID는 DB 기본값으로 발급된다."""
        return self._insert_chunk_rows(card_doc_id, document.chunks)

    def _insert_chunk_rows(self, card_doc_id: str, chunks) -> int:
        """``DocChunk`` 목록을 card_doc_chunk에 일괄 INSERT하고 건수를 반환한다.

        card_doc_chunk_id는 DB 기본값이 발급한다. (card_doc_id, page_no)는 card_doc_page를 가리키는 값이다.
        """
        return self.sql_session.execute_many(
            "document_repository.insert_doc_chunk",
            [
                {
                    "CARD_DOC_ID": card_doc_id,
                    "PAGE_NO": chunk.page_no,
                    "CHUNK_SEQ": chunk.seq,
                    "CHUNK_START_POS": chunk.start_pos,
                    "CHUNK_END_POS": chunk.end_pos,
                    "CHUNK_RAW_TXT": chunk.text,
                    "CHUNK_TYPE_CD": chunk.chunk_type_cd,
                    "CHUNK_STATUS": chunk.status,
                    "CHUNK_SPLIT_RULE_VER": chunk.split_rule_ver,
                    "USER_ID": SYSTEM_USER_ID,
                }
                for chunk in chunks
            ],
        )

    def verify_doc(self, card_doc_id: str) -> list[dict]:
        """문서의 검증 항목별 위반 건수를 반환한다.

        Returns:
            ``[{"check_cd", "severity", "issue_cnt"}, ...]``. 항목 목록(PAGE_COUNT, PAGE_HASH, CHUNK_POSITION 등)은
            document_repository.sql의 verify_doc 주석에 있다. severity=ERROR이고 issue_cnt>0이면 등록을 막는다.
        """
        return self.sql_session.select_list("document_repository.verify_doc", {"CARD_DOC_ID": card_doc_id})

    def select_page_hashes(self, card_doc_id: str) -> list[dict]:
        """PDF 재추출 결과와 대조할 페이지 번호·해시를 반환한다."""
        return self.sql_session.select_list("document_repository.select_page_hashes", {"CARD_DOC_ID": card_doc_id})

    def select_review_pages(self, card_doc_id: str) -> list[dict]:
        """OCR 검토를 기다리는 페이지를 반환한다."""
        return self.sql_session.select_list("document_repository.select_review_pages", {"CARD_DOC_ID": card_doc_id})

    def approve_review_page(self, card_doc_id: str, page_no: int, reviewer_id: str) -> list[dict]:
        """사람이 확인한 OCR 페이지의 청크를 AI 추출 대상으로 전환하고, 전환한 청크를 반환한다.

        card_doc_page.page_note를 OCR_CONFIRMED로 바꾸고 같은 페이지의 EXCLUDED 청크를 RAW로 UPDATE한다.
        확인 시점 기준으로 db_pipeline 안에는 이 메서드를 호출하는 코드가 없다.
        """
        return self.sql_session.execute(
            "document_repository.approve_review_page",
            {"CARD_DOC_ID": card_doc_id, "PAGE_NO": page_no, "USER_ID": reviewer_id},
        )

    def select_ai_target_chunks(self, card_doc_id: str) -> list[dict]:
        """AI 추출 대상 청크를 반환한다."""
        return self.sql_session.select_list("document_repository.select_ai_target_chunks", {"CARD_DOC_ID": card_doc_id})

    def select_table_counts(self, card_doc_id: str) -> dict:
        """문서·페이지·청크 등록 건수를 반환한다."""
        return self.sql_session.select_one("document_repository.select_table_counts", {"CARD_DOC_ID": card_doc_id})

    def card_exists(self, card_id: int) -> bool:
        """카드 상품이 있는지 확인한다."""
        return self.sql_session.select_one("document_repository.select_card_product_exists", {"CARD_ID": card_id}) is not None

    def link_product_doc(self, card_id: int, card_doc_id: str, basis_txt: str) -> None:
        """상품설명서를 상품에 승인 대기로 연결한다.

        card_product_doc에 (card_id, card_doc_id)를 approval_status_cd='PENDING'으로 INSERT한다.
        SQL의 ``ON CONFLICT (card_id, card_doc_id) DO NOTHING`` 때문에 재실행해도 관계는 1건이다.
        """
        self.sql_session.execute(
            "document_repository.insert_product_doc_link",
            {"CARD_ID": card_id, "CARD_DOC_ID": card_doc_id, "BASIS_TXT": basis_txt, "USER_ID": SYSTEM_USER_ID},
        )
