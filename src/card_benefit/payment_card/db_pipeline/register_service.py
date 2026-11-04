"""PDF 원문 등록 순서와 트랜잭션을 관리하는 Service 모듈.

[등록 파이프라인에서의 위치] 1단계의 "PostgreSQL 등록" 부분. Java의 @Service + @Transactional 역할이다.

처리 흐름 (``RegisterService.register``)
    1. DocumentService.inspect  : 해시·doc_cd만 계산(페이지 파싱 없음)
    2. DocRepository.find_doc   : 같은 해시 또는 같은 doc_cd 문서 조회 → 3가지로 분기
       a) 같은 해시 있음       → ALREADY_REGISTERED. 다시 넣지 않고 저장 구조만 검증, 필요하면 연결만 추가
       b) 같은 doc_cd·다른 해시 → RegisterError (같은 코드에 다른 내용 금지)
       c) 없음                 → apply=False: DocumentService.read 후 DRY_RUN 반환(DB 변경 없음)
                                 apply=True : read 후 ``_insert`` (한 트랜잭션)
    3. ``_insert`` : card_doc → card_doc_page → card_doc_chunk INSERT → verify_doc + 해시 대조
                     → ERROR가 있으면 예외로 전체 rollback → 상품/공통서비스 연결 → 블록 종료 시 commit

호출 관계
    main.py, common_auto_main.py, common_auto_pipeline.py → RegisterService.register
    RegisterService → DocumentService(document_service.py), DocRepository(document_repository.py),
                      CommonBenefitService.ensure_common / link_doc(common_benefit_service.py, 공통서비스 연결 시)

관련 테이블: card_doc, card_doc_page, card_doc_chunk, card_product_doc, card_common, card_common_doc
이 모듈은 LLM을 호출하지 않고 card_product(상품) 행도 만들지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from time import perf_counter

from common.postgres_db_session import PostgresDbSession

from .common_benefit_service import CommonBenefitService
from .document_service import DocumentService, ParsedDocument
from .document_repository import DocRepository

register_logger = logging.getLogger("card_benefit.db_pipeline")


class RegisterError(Exception):
    """등록을 진행할 수 없는 경우. 트랜잭션 안에서 발생하면 등록 내용은 rollback된다."""


@dataclass(frozen=True)
class ProductDocLink:
    """상품설명서 경로: CARD_DOC → CARD_PRODUCT_DOC → CARD_PRODUCT."""

    card_id: int
    basis_txt: str          # applicability_basis_txt. 상품에 적용되는 근거 설명


@dataclass(frozen=True)
class CommonDocLink:
    """브랜드 공통서비스 문서 경로: CARD_DOC → CARD_COMMON_DOC → CARD_COMMON."""

    common_cd: str
    common_nm: str
    brand_cd: str | None = None
    service_grade_cd: str | None = None
    common_note: str | None = None


@dataclass
class RegisterResult:
    """등록 결과. ``status`` 는 DRY_RUN, REGISTERED, ALREADY_REGISTERED 중 하나다."""

    status: str
    document: ParsedDocument
    card_doc_id: str | None = None
    checks: list[dict] = field(default_factory=list)
    counts: dict | None = None
    elapsed_ms: float = 0.0
    linked: str | None = None       # 연결한 관계 설명


class RegisterService:
    """PDF 한 건을 ``card_doc`` → ``card_doc_page`` → ``card_doc_chunk`` 순서로 등록한다.

    PDF 등록·파싱·청킹은 문서 종류와 무관하게 같고, 연결만 ``product_link`` 또는 ``common_link`` 로 나뉜다.
    연결을 지정하지 않으면 문서만 등록한다. 상품(``card_product``)은 만들지 않는다.
    """

    def __init__(self, sql_session: PostgresDbSession, document_service: DocumentService | None = None):
        self.sql_session = sql_session
        self.repository = DocRepository(sql_session)
        self.document_service = document_service if document_service is not None else DocumentService()

    def register(self, pdf: str | Path, apply: bool = False, product_link: ProductDocLink | None = None,
                 common_link: CommonDocLink | None = None) -> RegisterResult:
        """PDF를 등록한다. ``apply=False`` 이면 조회만 하고 DB를 변경하지 않는다.

        같은 해시의 문서가 있으면 다시 등록하지 않고 기존 등록 내용을 검증해 반환한다.

        Raises:
            ValueError: PDF 검증에 실패한 경우.
            RegisterError: 문서 코드가 충돌하거나 등록 내용 검증에 실패한 경우, 연결 대상이 맞지 않는 경우.
        """
        if product_link and common_link:
            raise RegisterError("상품 연결과 공통서비스 연결은 함께 지정할 수 없습니다")
        started = perf_counter()
        # 기존 파일은 페이지 재파싱 없이 해시와 저장 구조를 검증한다.
        # 실제 DocumentService면 inspect(메타데이터만), 다른 객체(테스트의 MagicMock 등)면 read(페이지 포함)를 쓴다.
        if isinstance(self.document_service, DocumentService):
            document = self.document_service.inspect(pdf)
        else:
            document = self.document_service.read(pdf)
        expected_type = "PRODUCT_GUIDE" if product_link else ("BRAND_SERVICE" if common_link else None)
        if expected_type and document.doc_type_cd != expected_type:
            raise RegisterError(f"{document.doc_type_cd} 문서는 이 경로로 연결할 수 없습니다: {expected_type} 필요")
        register_logger.info(
            "PDF READ doc_cd=%s pages=%d chunks=%d", document.doc_cd, len(document.pages), len(document.chunks),
        )
        # region 중복 등록 판정과 분기
        # 중복 판정: doc_sha256(파일 내용) 또는 doc_cd(문서 코드)가 같은 기존 card_doc 행을 찾는다.
        found = self.repository.find_doc(document.doc_sha256, document.doc_cd)
        same_file = next((row for row in found if row["doc_sha256"] == document.doc_sha256), None)
        # 분기 a) 같은 파일이 이미 있음: INSERT하지 않고 기존 card_doc_id를 재사용한다.
        if same_file is not None:
            card_doc_id = same_file["card_doc_id"]
            result = RegisterResult("ALREADY_REGISTERED", document, card_doc_id)
            result.checks = (self.repository.verify_doc(card_doc_id) if not document.pages
                             else self._verify(card_doc_id, document))
            result.counts = self.repository.select_table_counts(card_doc_id)
            if error_checks(result.checks):
                raise RegisterError("기존 문서의 저장 구조 검증 실패")
            # 기존 문서에 연결만 추가하는 경우. 트랜잭션 시작 → _link → 블록 종료 시 commit(예외면 rollback).
            if apply and (product_link or common_link):
                with self.sql_session.transaction():
                    result.linked = self._link(card_doc_id, product_link, common_link)
        # 분기 b) doc_cd는 같은데 해시가 다름: 같은 코드로 다른 내용을 등록하지 않는다.
        elif found:
            raise RegisterError(
                f"문서 코드가 같지만 내용이 다른 문서가 있습니다: {document.doc_cd} ({found[0]['card_doc_id']})"
            )
        # 분기 c-1) 신규 문서 + dry-run: 파싱만 해서 결과를 보여주고 DB는 바꾸지 않는다.
        elif not apply:
            if not document.pages:
                document = self.document_service.read(pdf)
            result = RegisterResult("DRY_RUN", document)
        # 분기 c-2) 신규 문서 + --apply: 페이지를 파싱한 뒤 _insert에서 한 트랜잭션으로 등록한다.
        else:
            if not document.pages:
                parsed = self.document_service.read(pdf)
                # inspect와 read 사이에 파일이 바뀌었으면 중복 판정 결과를 믿을 수 없으므로 중단한다.
                if parsed.doc_sha256 != document.doc_sha256:
                    raise RegisterError("등록 중 PDF 내용이 변경되었습니다")
                document = parsed
            result = self._insert(document, product_link, common_link)
        # endregion
        result.elapsed_ms = (perf_counter() - started) * 1000
        register_logger.info(
            "REGISTER %s doc_cd=%s card_doc_id=%s elapsed_ms=%.1f",
            result.status, document.doc_cd, result.card_doc_id, result.elapsed_ms,
        )
        return result

    def _link(self, card_doc_id: str, product_link: ProductDocLink | None, common_link: CommonDocLink | None) -> str | None:
        """문서를 상품 또는 공통서비스에 연결한다. 재실행해도 관계는 하나다.

        호출자가 트랜잭션을 연 상태에서 부른다(``register`` 의 기존 문서 분기, ``_insert``).

        - product_link: card_product 존재 확인 → card_product_doc INSERT(ON CONFLICT DO NOTHING, 승인 대기)
        - common_link : CommonBenefitService.ensure_common(card_common 없으면 INSERT, 있으면 값 일치 확인)
                        → link_doc(BRAND_SERVICE 문서만 card_common_doc INSERT, ON CONFLICT DO NOTHING)

        Returns:
            연결 설명 문자열. 연결을 지정하지 않으면 ``None``.

        Raises:
            RegisterError: 상품이 없거나 공통서비스 정보·문서 종류가 맞지 않는 경우(ValueError를 바꿔 던진다).
        """
        if product_link:
            if not self.repository.card_exists(product_link.card_id):
                raise RegisterError(f"card_product가 없습니다: {product_link.card_id}")
            self.repository.link_product_doc(product_link.card_id, card_doc_id, product_link.basis_txt)
            return f"card_product_doc card_id={product_link.card_id}"
        if common_link:
            service = CommonBenefitService(self.sql_session)
            try:
                common_id = service.ensure_common(vars(common_link))
                service.link_doc(common_id, card_doc_id)
            except ValueError as error:
                raise RegisterError(str(error)) from error
            return f"card_common_doc card_common_id={common_id}"
        return None

    def _insert(self, document: ParsedDocument, product_link: ProductDocLink | None = None,
                common_link: CommonDocLink | None = None) -> RegisterResult:
        """문서와 연결을 한 트랜잭션으로 등록한다. 검증 오류가 있으면 예외로 전체를 rollback한다.

        처리 순서(모두 같은 DB 연결·같은 트랜잭션):
            card_doc INSERT(PK 발급) → card_doc_page 일괄 INSERT → card_doc_chunk 일괄 INSERT
            → verify_doc SQL 검증 + PDF 재추출 해시 대조 → 건수 조회 → 상품/공통서비스 연결

        Raises:
            RegisterError: 검증 ERROR가 있거나 연결 대상이 맞지 않는 경우. 이때 위 INSERT는 모두 rollback된다.
        """
        # 트랜잭션 시작: 블록을 정상 종료하면 commit, 예외가 밖으로 나가면 rollback(PostgresDbSession.transaction).
        with self.sql_session.transaction():
            # insert_doc이 돌려준 card_doc_id(PK)를 페이지·청크 INSERT의 FK 값으로 넘긴다.
            card_doc_id = self.repository.insert_doc(document)
            page_cnt = self.repository.insert_pages(card_doc_id, document)
            chunk_cnt = self.repository.insert_chunks(card_doc_id, document)
            register_logger.info("INSERTED card_doc_id=%s pages=%s chunks=%s", card_doc_id, page_cnt, chunk_cnt)
            # 커밋 전에 방금 넣은 행을 SQL로 다시 읽어 검증한다. 같은 트랜잭션이라 미커밋 행도 보인다.
            checks = self._verify(card_doc_id, document)
            errors = error_checks(checks)
            if errors:
                raise RegisterError(f"등록 검증 실패: {[row['check_cd'] for row in errors]}")
            counts = self.repository.select_table_counts(card_doc_id)
            linked = self._link(card_doc_id, product_link, common_link)
        # 트랜잭션 종료(commit 완료) 후 결과를 만든다.
        return RegisterResult("REGISTERED", document, card_doc_id, checks, counts, linked=linked)

    def _verify(self, card_doc_id: str, document: ParsedDocument) -> list[dict]:
        """SQL 검증 결과에 PDF 재추출 결과와의 해시 대조를 더한다.

        PDF_TEXT_MATCH(ERROR): 메모리의 페이지 해시와 DB의 page_txt_sha256이 다른 페이지 수
        + DB에만 있는 페이지 수. 0이어야 통과다.
        """
        expected = {page.page_no: page.sha256 for page in document.pages}
        stored = {row["page_no"]: row["page_txt_sha256"] for row in self.repository.select_page_hashes(card_doc_id)}
        differs = sum(stored.get(page_no) != sha256 for page_no, sha256 in expected.items())
        return [
            *self.repository.verify_doc(card_doc_id),
            {"check_cd": "PDF_TEXT_MATCH", "severity": "ERROR", "issue_cnt": differs + len(stored.keys() - expected)},
        ]


def error_checks(checks: list[dict]) -> list[dict]:
    """위반이 있는 ERROR 항목만 반환한다."""
    return [row for row in checks if row["severity"] == "ERROR" and row["issue_cnt"]]
