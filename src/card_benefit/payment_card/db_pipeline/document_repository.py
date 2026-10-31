"""PDF 원문 등록용 SQL mapper(``document_repository.sql``)를 호출하는 DB 접근 클래스."""

from __future__ import annotations

from pathlib import Path

from common.postgres_db_session import PostgresDbSession

from .document_service import SPLIT_RULE_VER, ParsedDocument

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
        """해시 또는 문서 코드가 같은 기존 문서를 반환한다."""
        return self.sql_session.select_list(
            "document_repository.select_doc_by_sha256_or_cd",
            {"DOC_SHA256": doc_sha256, "DOC_CD": doc_cd},
        )

    def insert_doc(self, document: ParsedDocument) -> str:
        """문서 한 건을 등록하고 DB가 발급한 ``card_doc_id`` 를 반환한다."""
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
        """페이지 원문을 일괄 등록하고 등록 건수를 반환한다."""
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

    def insert_chunks(self, card_doc_id: str, document: ParsedDocument) -> int:
        """청크를 일괄 등록하고 등록 건수를 반환한다. 청크 ID는 DB 기본값으로 발급된다."""
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
                    "CHUNK_STATUS": chunk.status,
                    "CHUNK_SPLIT_RULE_VER": SPLIT_RULE_VER,
                    "USER_ID": SYSTEM_USER_ID,
                }
                for chunk in document.chunks
            ],
        )

    def verify_doc(self, card_doc_id: str) -> list[dict]:
        """문서의 검증 항목별 위반 건수를 반환한다."""
        return self.sql_session.select_list("document_repository.verify_doc", {"CARD_DOC_ID": card_doc_id})

    def select_page_hashes(self, card_doc_id: str) -> list[dict]:
        """PDF 재추출 결과와 대조할 페이지 번호·해시를 반환한다."""
        return self.sql_session.select_list("document_repository.select_page_hashes", {"CARD_DOC_ID": card_doc_id})

    def select_review_pages(self, card_doc_id: str) -> list[dict]:
        """OCR 검토를 기다리는 페이지를 반환한다."""
        return self.sql_session.select_list("document_repository.select_review_pages", {"CARD_DOC_ID": card_doc_id})

    def approve_review_page(self, card_doc_id: str, page_no: int, reviewer_id: str) -> list[dict]:
        """사람이 확인한 OCR 페이지의 청크를 AI 추출 대상으로 전환하고, 전환한 청크를 반환한다."""
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
