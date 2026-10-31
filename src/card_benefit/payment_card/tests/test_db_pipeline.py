"""db_pipeline PDF 원문 등록 단위 테스트. DB에 접속하지 않는다.

실행(src/card_benefit 폴더에서):
    uv run python -m unittest discover -s payment_card/tests -v

실제 PDF 검증은 원본 파일이 있을 때만 실행한다(원본 PDF는 Git에 없다).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from common.postgres_db_session import PostgresDbSession
import pymupdf

from payment_card.db_pipeline.document_service import (
    DATA_ROOT, SPLIT_RULE_VER, UNCONFIRMED_SOURCE_NOTE, DocumentService, sha256_hex,
)
from payment_card.db_pipeline.register_service import RegisterError, RegisterService, error_checks
from payment_card.db_pipeline.document_repository import MAPPER_ROOT

ONE_PICK_STYLE = next((DATA_ROOT / "debit").glob("*ONEPICKSTYLE*15650_20260429.pdf"), None)
MANIFEST_HEADER = "파일경로,카드상품명,문서구분,문서종류,PDF원본URL,파일크기(byte),페이지수,SHA256,수집일시\n"


def manifest_line(path: str, content: bytes, pages: int, kind: str = "상품설명서(공식PDF)") -> str:
    return (f"{path},테스트 카드,공식 원본 PDF,{kind},https://example.test/a.pdf,"
            f"{len(content)},{pages},{sha256_hex(content)},2026-10-30T16:00:52\n")


class FixtureMixin:
    """임시 수집 폴더에 PDF와 manifest를 만든다."""

    def make_root(self, page_texts: list[str], file_name: str = "신용_테스트_상품설명서_15650_20260429.pdf") -> Path:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name) / "hana_all"
        root.mkdir()
        with pymupdf.open() as document:
            for text in page_texts:
                document.new_page().insert_text((72, 72), text)
            content = document.tobytes()
        (root / file_name).write_bytes(content)
        (root / "manifest.csv").write_text(
            MANIFEST_HEADER + manifest_line(file_name, content, len(page_texts)), encoding="utf-8-sig",
        )
        return root


class DocumentServiceTests(FixtureMixin, unittest.TestCase):
    def test_builds_metadata_and_one_based_inclusive_positions(self):
        root = self.make_root(["first line\nsecond line", "third line"])
        document = DocumentService(root).read("신용_테스트_상품설명서_15650_20260429.pdf")
        self.assertEqual((document.doc_cd, document.doc_family_cd), ("HANA_15650_20260429", "HANA_15650"))
        self.assertEqual(document.doc_file_nm, "hana_all/신용_테스트_상품설명서_15650_20260429.pdf")
        self.assertEqual(document.doc_collect_date.utcoffset().total_seconds(), 9 * 3600)
        self.assertEqual([chunk.seq for chunk in document.chunks], list(range(1, len(document.chunks) + 1)))
        for chunk in document.chunks:
            page_text = document.pages[chunk.page_no - 1].text
            self.assertEqual(page_text[chunk.start_pos - 1:chunk.end_pos], chunk.text)

    def test_each_page_with_text_becomes_one_whole_page_chunk(self):
        root = self.make_root(["a", "b", "c"])

        def fill(reader):
            texts = ("  first page\nline \n", " \n", "third page")
            reader.doc_list = [{"page_no": no, "text": text} for no, text in enumerate(texts, start=1)]
            reader.page_quality_list = [{
                "page_no": no, "status": "OK", "extractor": "PyMuPDF", "extractor_ver": "1", "has_visual": False,
                "hangul_count": 0, "digit_count": 0, "suspect_count": 0,
            } for no in (1, 2, 3)]

        with patch("payment_card.db_pipeline.document_service.DocumentReader.set_pdf_doc_list", fill):
            document = DocumentService(root).read("신용_테스트_상품설명서_15650_20260429.pdf")
        self.assertEqual(
            [(chunk.seq, chunk.page_no, chunk.start_pos, chunk.end_pos) for chunk in document.chunks],
            [(1, 1, 1, 19), (2, 3, 1, 10)],                  # 공백뿐인 2쪽은 청크가 없고 순번은 이어진다
        )
        self.assertEqual(document.chunks[0].text, document.pages[0].text)
        self.assertEqual(SPLIT_RULE_VER, "PAGE_V1")

    def test_rejects_invalid_input(self):
        root = self.make_root(["text"])
        service = DocumentService(root)
        (root / "unknown.pdf").write_bytes(b"%PDF-")
        for pdf in ("missing.pdf", "unknown.pdf", "../outside.pdf"):
            with self.subTest(pdf=pdf), self.assertRaises(ValueError):
                service.read(pdf)

    def test_rejects_file_different_from_manifest(self):
        root = self.make_root(["text"])
        path = root / "신용_테스트_상품설명서_15650_20260429.pdf"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "manifest"):
            DocumentService(root).read(path.name)

    def test_rejects_document_that_is_not_product_guide(self):
        root = self.make_root(["text"])
        name = "신용_테스트_상품설명서_15650_20260429.pdf"
        content = (root / name).read_bytes()
        (root / "manifest.csv").write_text(
            MANIFEST_HEADER + manifest_line(name, content, 1, "상품상세 웹페이지"), encoding="utf-8-sig",
        )
        with self.assertRaisesRegex(ValueError, "상품설명서"):
            DocumentService(root).read(name)

    def test_blocks_page_whose_text_cannot_be_trusted(self):
        root = self.make_root(["text"])
        quality = [{"page_no": 1, "status": "SUSPECT", "extractor": "PyMuPDF", "extractor_ver": "1"}]

        def fill(reader):
            reader.doc_list = [{"page_no": 1, "text": "text"}]
            reader.page_quality_list = quality

        with patch("payment_card.db_pipeline.document_service.DocumentReader.set_pdf_doc_list", fill):
            with self.assertRaisesRegex(ValueError, "SUSPECT"):
                DocumentService(root).read("신용_테스트_상품설명서_15650_20260429.pdf")

    def test_nul_is_replaced_without_changing_positions(self):
        root = self.make_root(["text"])

        def fill(reader):
            reader.doc_list = [{"page_no": 1, "text": "a\x00b"}]
            reader.page_quality_list = [{
                "page_no": 1, "status": "OK", "extractor": "PyMuPDF", "extractor_ver": "1", "has_visual": False,
                "hangul_count": 0, "digit_count": 0, "suspect_count": 0,
            }]

        with patch("payment_card.db_pipeline.document_service.DocumentReader.set_pdf_doc_list", fill):
            document = DocumentService(root).read("신용_테스트_상품설명서_15650_20260429.pdf")
        self.assertEqual((document.pages[0].text, document.pages[0].char_cnt), ("a�b", 3))


class OcrReviewTests(FixtureMixin, unittest.TestCase):
    def test_ocr_page_is_kept_out_of_ai_input_until_reviewed(self):
        root = self.make_root(["text"])

        def fill(reader):
            reader.doc_list = [{"page_no": 1, "text": "월 5천원"}]
            reader.page_quality_list = [{
                "page_no": 1, "status": "OCR_REVIEW", "extractor": "WindowsOCR", "extractor_ver": "1", "has_visual": True,
                "source_status": "OCR_REQUIRED", "source_text": "", "ocr_agreement": None, "ocr_engine": "WindowsOCR",
                "ocr_replaced": True, "ocr_disputed_numbers": ["5%"],
                "hangul_count": 2, "digit_count": 1, "suspect_count": 0,
            }]

        with patch("payment_card.db_pipeline.document_service.DocumentReader.set_pdf_doc_list", fill):
            document = DocumentService(root).read("신용_테스트_상품설명서_15650_20260429.pdf")
        page = document.pages[0]
        self.assertEqual((page.extractor_nm, page.layer_cd), ("WindowsOCR", "IMAGE"))
        self.assertEqual(
            page.note, "OCR_REVIEW engine=WindowsOCR source=OCR_REQUIRED replaced=True agreement=NA disputed=['5%']",
        )
        self.assertEqual({chunk.status for chunk in document.chunks}, {"EXCLUDED"})


class FakeSession:
    """mapper 호출을 기록하고 트랜잭션 결과를 남기는 세션."""

    def __init__(self, found=(), issue_cnt=0, stored_hashes=None):
        self.found = list(found)
        self.issue_cnt = issue_cnt
        self.stored_hashes = stored_hashes
        self.calls = []
        self.transaction_result = None

    @contextmanager
    def transaction(self):
        try:
            yield self
        except BaseException:
            self.transaction_result = "ROLLBACK"
            raise
        self.transaction_result = "COMMIT"

    def select_list(self, statement_id, parameters=None):
        self.calls.append(statement_id)
        if statement_id.endswith("select_doc_by_sha256_or_cd"):
            return self.found
        if statement_id.endswith("verify_doc"):
            return [{"check_cd": "CHUNK_POSITION", "severity": "ERROR", "issue_cnt": self.issue_cnt}]
        return [{"page_no": page_no, "page_txt_sha256": sha256} for page_no, sha256 in (self.stored_hashes or {}).items()]

    def select_one(self, statement_id, parameters=None):
        self.calls.append(statement_id)
        return {"doc_cnt": 1, "page_cnt": 1, "chunk_cnt": 1}

    def execute(self, statement_id, parameters=None):
        self.calls.append(statement_id)
        return [{"card_doc_id": "20261031_000001"}]

    def execute_many(self, statement_id, parameters_list):
        self.calls.append(statement_id)
        if statement_id.endswith("insert_doc_chunk") and getattr(self, "fail_chunks", False):
            raise RuntimeError("chunk insert failed")
        return len(parameters_list)


class RegisterServiceTests(FixtureMixin, unittest.TestCase):
    PDF = "신용_테스트_상품설명서_15650_20260429.pdf"

    def run_register(self, session, apply=True):
        return RegisterService(session, DocumentService(self.make_root(["text"]))).register(self.PDF, apply=apply)

    def inserts(self, session):
        return [call for call in session.calls if ".insert_" in call]

    def test_dry_run_writes_nothing(self):
        session = FakeSession()
        result = self.run_register(session, apply=False)
        self.assertEqual(result.status, "DRY_RUN")
        self.assertEqual(self.inserts(session), [])
        self.assertIsNone(session.transaction_result)

    def test_apply_inserts_in_order_inside_one_transaction(self):
        session = FakeSession()
        document = DocumentService(self.make_root(["text"])).read(self.PDF)
        session.stored_hashes = {page.page_no: page.sha256 for page in document.pages}
        service = RegisterService(session, MagicMock(read=MagicMock(return_value=document)))
        result = service.register(self.PDF, apply=True)
        self.assertEqual(result.status, "REGISTERED")
        self.assertEqual(result.card_doc_id, "20261031_000001")
        self.assertEqual(self.inserts(session), [
            "document_repository.insert_doc", "document_repository.insert_doc_page", "document_repository.insert_doc_chunk",
        ])
        self.assertEqual(session.transaction_result, "COMMIT")

    def test_same_file_is_not_inserted_again(self):
        document = DocumentService(self.make_root(["text"])).read(self.PDF)
        session = FakeSession(
            found=[{"card_doc_id": "D1", "doc_sha256": document.doc_sha256, "doc_cd": document.doc_cd}],
            stored_hashes={page.page_no: page.sha256 for page in document.pages},
        )
        result = RegisterService(session, MagicMock(read=MagicMock(return_value=document))).register(self.PDF, apply=True)
        self.assertEqual((result.status, result.card_doc_id), ("ALREADY_REGISTERED", "D1"))
        self.assertEqual(self.inserts(session), [])
        self.assertEqual(error_checks(result.checks), [])

    def test_same_code_with_other_content_stops(self):
        session = FakeSession(found=[{"card_doc_id": "D1", "doc_sha256": "0" * 64, "doc_cd": "HANA_15650_20260429"}])
        with self.assertRaisesRegex(RegisterError, "내용이 다른"):
            self.run_register(session)
        self.assertEqual(self.inserts(session), [])

    def test_verification_error_rolls_back(self):
        session = FakeSession(issue_cnt=1)
        with self.assertRaisesRegex(RegisterError, "CHUNK_POSITION"):
            self.run_register(session)
        self.assertEqual(session.transaction_result, "ROLLBACK")

    def test_stored_text_different_from_pdf_rolls_back(self):
        session = FakeSession(stored_hashes={1: "0" * 64})
        with self.assertRaisesRegex(RegisterError, "PDF_TEXT_MATCH"):
            self.run_register(session)
        self.assertEqual(session.transaction_result, "ROLLBACK")

    def test_insert_failure_rolls_back(self):
        session = FakeSession()
        session.fail_chunks = True
        with self.assertRaisesRegex(RuntimeError, "chunk insert failed"):
            self.run_register(session)
        self.assertEqual(session.transaction_result, "ROLLBACK")


class MapperTests(unittest.TestCase):
    def setUp(self):
        self.session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")

    def test_mapper_registers_without_connecting(self):
        self.assertEqual(sorted(self.session.mappers), ["document_repository", "extraction_repository"])
        self.assertEqual(self.session.database_manager._pools, {})

    def test_every_statement_names_the_schema(self):
        for statement in self.session.mappers["document_repository"].available_queries:
            if statement.endswith("_cursor"):
                continue
            sql = self.session._query(f"document_repository.{statement}").sql
            self.assertIn("db_pipeline.card_doc", sql, statement)


@unittest.skipIf(ONE_PICK_STYLE is None, "카드 PDF 원본이 없는 환경")
class OnePickStyleTests(unittest.TestCase):
    """페이지 이미지와 대조한 값으로 실제 PDF의 등록 데이터를 검증한다."""

    @classmethod
    def setUpClass(cls):
        cls.document = DocumentService().read(ONE_PICK_STYLE.relative_to(DATA_ROOT))

    def test_metadata(self):
        document = self.document
        self.assertEqual(document.doc_cd, "HANA_15650_20260429")
        self.assertEqual(document.doc_sha256, "6ec9641c2e318ce9429a916f5d01c0468ccc3cffb238eb1162a43b280e25c6d2")
        self.assertEqual(document.doc_review_no, "준법심의 L-26-0542(2026.04.29) / VI 260429-71")
        self.assertEqual(document.doc_review_date, date(2026, 4, 29))
        self.assertEqual(document.doc_note, UNCONFIRMED_SOURCE_NOTE)
        self.assertNotIn("공식 원본", document.doc_note)

    def test_pages_and_positions(self):
        self.assertEqual([page.char_cnt for page in self.document.pages], [2482, 3181])
        self.assertEqual({page.extractor_nm for page in self.document.pages}, {"PyMuPDF"})
        for chunk in self.document.chunks:
            page_text = self.document.pages[chunk.page_no - 1].text
            self.assertEqual(page_text[chunk.start_pos - 1:chunk.end_pos], chunk.text)
        self.assertEqual(len({chunk.text for chunk in self.document.chunks}), len(self.document.chunks))
        self.assertEqual([(chunk.page_no, chunk.start_pos, chunk.end_pos) for chunk in self.document.chunks],
                         [(1, 1, 2482), (2, 1, 3181)])


if __name__ == "__main__":
    unittest.main()
