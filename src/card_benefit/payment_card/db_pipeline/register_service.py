"""PDF 원문 등록 순서와 트랜잭션을 관리하는 Service 모듈."""

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
        found = self.repository.find_doc(document.doc_sha256, document.doc_cd)
        same_file = next((row for row in found if row["doc_sha256"] == document.doc_sha256), None)
        if same_file is not None:
            card_doc_id = same_file["card_doc_id"]
            result = RegisterResult("ALREADY_REGISTERED", document, card_doc_id)
            result.checks = (self.repository.verify_doc(card_doc_id) if not document.pages
                             else self._verify(card_doc_id, document))
            result.counts = self.repository.select_table_counts(card_doc_id)
            if error_checks(result.checks):
                raise RegisterError("기존 문서의 저장 구조 검증 실패")
            if apply and (product_link or common_link):
                with self.sql_session.transaction():
                    result.linked = self._link(card_doc_id, product_link, common_link)
        elif found:
            raise RegisterError(
                f"문서 코드가 같지만 내용이 다른 문서가 있습니다: {document.doc_cd} ({found[0]['card_doc_id']})"
            )
        elif not apply:
            if not document.pages:
                document = self.document_service.read(pdf)
            result = RegisterResult("DRY_RUN", document)
        else:
            if not document.pages:
                parsed = self.document_service.read(pdf)
                if parsed.doc_sha256 != document.doc_sha256:
                    raise RegisterError("등록 중 PDF 내용이 변경되었습니다")
                document = parsed
            result = self._insert(document, product_link, common_link)
        result.elapsed_ms = (perf_counter() - started) * 1000
        register_logger.info(
            "REGISTER %s doc_cd=%s card_doc_id=%s elapsed_ms=%.1f",
            result.status, document.doc_cd, result.card_doc_id, result.elapsed_ms,
        )
        return result

    def _link(self, card_doc_id: str, product_link: ProductDocLink | None, common_link: CommonDocLink | None) -> str | None:
        """문서를 상품 또는 공통서비스에 연결한다. 재실행해도 관계는 하나다."""
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
        """문서와 연결을 한 트랜잭션으로 등록한다. 검증 오류가 있으면 예외로 전체를 rollback한다."""
        with self.sql_session.transaction():
            card_doc_id = self.repository.insert_doc(document)
            page_cnt = self.repository.insert_pages(card_doc_id, document)
            chunk_cnt = self.repository.insert_chunks(card_doc_id, document)
            register_logger.info("INSERTED card_doc_id=%s pages=%s chunks=%s", card_doc_id, page_cnt, chunk_cnt)
            checks = self._verify(card_doc_id, document)
            errors = error_checks(checks)
            if errors:
                raise RegisterError(f"등록 검증 실패: {[row['check_cd'] for row in errors]}")
            counts = self.repository.select_table_counts(card_doc_id)
            linked = self._link(card_doc_id, product_link, common_link)
        return RegisterResult("REGISTERED", document, card_doc_id, checks, counts, linked=linked)

    def _verify(self, card_doc_id: str, document: ParsedDocument) -> list[dict]:
        """SQL 검증 결과에 PDF 재추출 결과와의 해시 대조를 더한다."""
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
