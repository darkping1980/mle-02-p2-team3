"""PDF 원문 등록 순서와 트랜잭션을 관리하는 Service 모듈."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from time import perf_counter

from common.postgres_db_session import PostgresDbSession

from .document_service import DocumentService, ParsedDocument
from .document_repository import DocRepository

register_logger = logging.getLogger("card_benefit.db_pipeline")


class RegisterError(Exception):
    """등록을 진행할 수 없는 경우. 트랜잭션 안에서 발생하면 등록 내용은 rollback된다."""


@dataclass
class RegisterResult:
    """등록 결과. ``status`` 는 DRY_RUN, REGISTERED, ALREADY_REGISTERED 중 하나다."""

    status: str
    document: ParsedDocument
    card_doc_id: str | None = None
    checks: list[dict] = field(default_factory=list)
    counts: dict | None = None
    elapsed_ms: float = 0.0


class RegisterService:
    """PDF 한 건을 ``card_doc`` → ``card_doc_page`` → ``card_doc_chunk`` 순서로 등록한다.

    상품(``card_product``)과 정책 버전은 만들지 않는다. 문서와 상품의 연결은 원문 검증 뒤의 단계이므로
    ``card_doc.card_id`` 는 NULL로 등록한다.
    """

    def __init__(self, sql_session: PostgresDbSession, document_service: DocumentService | None = None):
        self.sql_session = sql_session
        self.repository = DocRepository(sql_session)
        self.document_service = document_service if document_service is not None else DocumentService()

    def register(self, pdf: str | Path, apply: bool = False) -> RegisterResult:
        """PDF를 등록한다. ``apply=False`` 이면 조회만 하고 DB를 변경하지 않는다.

        같은 해시의 문서가 있으면 다시 등록하지 않고 기존 등록 내용을 검증해 반환한다.

        Raises:
            ValueError: PDF 검증에 실패한 경우.
            RegisterError: 문서 코드가 충돌하거나 등록 내용 검증에 실패한 경우.
        """
        started = perf_counter()
        document = self.document_service.read(pdf)
        register_logger.info(
            "PDF READ doc_cd=%s pages=%d chunks=%d", document.doc_cd, len(document.pages), len(document.chunks),
        )
        found = self.repository.find_doc(document.doc_sha256, document.doc_cd)
        same_file = next((row for row in found if row["doc_sha256"] == document.doc_sha256), None)
        if same_file is not None:
            card_doc_id = same_file["card_doc_id"]
            result = RegisterResult("ALREADY_REGISTERED", document, card_doc_id)
            result.checks = self._verify(card_doc_id, document)
            result.counts = self.repository.select_table_counts(card_doc_id)
        elif found:
            raise RegisterError(
                f"문서 코드가 같지만 내용이 다른 문서가 있습니다: {document.doc_cd} ({found[0]['card_doc_id']})"
            )
        elif not apply:
            result = RegisterResult("DRY_RUN", document)
        else:
            result = self._insert(document)
        result.elapsed_ms = (perf_counter() - started) * 1000
        register_logger.info(
            "REGISTER %s doc_cd=%s card_doc_id=%s elapsed_ms=%.1f",
            result.status, document.doc_cd, result.card_doc_id, result.elapsed_ms,
        )
        return result

    def _insert(self, document: ParsedDocument) -> RegisterResult:
        """세 테이블을 한 트랜잭션으로 등록한다. 검증 오류가 있으면 예외로 전체를 rollback한다."""
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
        return RegisterResult("REGISTERED", document, card_doc_id, checks, counts)

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
