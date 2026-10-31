"""DocumentReader 단위 테스트. DB와 외부 서비스에 접속하지 않는다.

PDF는 임시 폴더에 생성하고, 카드 PDF 검증은 파일이 있을 때만 실행한다(원본 PDF는 Git에 없다).
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pymupdf

from common.document_reader import DocumentReader, is_suspect_char, measure_ocr_agreement, measure_pdf_text
from common.ocr_engines import OcrResult

ONE_PICK_STYLE = next(
    (Path(__file__).resolve().parents[2] / "card_benefit/data/raw/hana_all/debit").glob("*ONEPICKSTYLE*15650_20260429.pdf"),
    None,
)


def write_pdf(path: Path, page_texts: list[str]) -> Path:
    """페이지별 텍스트를 넣은 PDF를 만든다. 빈 문자열이면 빈 페이지가 된다."""
    with pymupdf.open() as document:
        for text in page_texts:
            page = document.new_page()
            if text:
                page.insert_text((72, 72), text)
        document.save(path)
    return path


def read(path: Path) -> DocumentReader:
    reader = DocumentReader(path)
    reader.set_pdf_reader()
    reader.set_pdf_doc_list()
    return reader


class MeasureTests(unittest.TestCase):
    def test_status(self):
        cases = (
            ("하나카드 월 5천원 5%", False, "OK"),
            ("", False, "EMPTY"),
            (" \n ", True, "OCR_REQUIRED"),
            ("೜ਸ�\x01", False, "GARBLED"),
            ("가" * 95 + "೜", False, "SUSPECT"),
        )
        for text, has_visual, status in cases:
            with self.subTest(text=text):
                self.assertEqual(measure_pdf_text(text, has_visual)["status"], status)

    def test_counts(self):
        quality = measure_pdf_text("월 5천원\n5%", False)
        self.assertEqual((quality["char_count"], quality["hangul_count"], quality["digit_count"]), (6, 3, 2))

    def test_normal_text_is_not_suspect(self):
        for char in "가A1%·※①“‘■\n\t한漢":
            self.assertFalse(is_suspect_char(char), char)


class DocListCompatibilityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_doc_list_keeps_existing_shape(self):
        reader = read(write_pdf(self.folder / "a.pdf", ["first page", "second page"]))
        self.assertEqual([sorted(doc) for doc in reader.doc_list], [["page_no", "text"]] * 2)
        self.assertEqual([doc["page_no"] for doc in reader.doc_list], [1, 2])
        self.assertIn("second page", reader.doc_list[1]["text"])
        self.assertEqual(type(reader.reader).__name__, "PdfReader")

    def test_second_call_appends_like_before(self):
        reader = read(write_pdf(self.folder / "a.pdf", ["first page"]))
        reader.set_pdf_doc_list()
        self.assertEqual([doc["page_no"] for doc in reader.doc_list], [1, 1])
        self.assertEqual(len(reader.page_quality_list), 2)

    def test_quality_list_reports_each_page(self):
        reader = read(write_pdf(self.folder / "a.pdf", ["first page", ""]))
        first, blank = reader.page_quality_list
        self.assertEqual((first["page_no"], first["extractor"], first["status"]), (1, "PyMuPDF", "OK"))
        self.assertEqual(blank["status"], "EMPTY")

    def test_text_drawn_without_text_layer_requires_ocr(self):
        path = self.folder / "a.pdf"
        with pymupdf.open() as document:
            document.new_page().draw_rect(pymupdf.Rect(50, 50, 200, 200), fill=(0, 0, 0))
            document.save(path)
        self.assertEqual(read(path).page_quality_list[0]["status"], "OCR_REQUIRED")


class FallbackTests(unittest.TestCase):
    def reader_with(self, mupdf_text: str, pypdf_text: str | None) -> DocumentReader:
        reader = DocumentReader("unused.pdf")
        page = MagicMock()
        page.extract_text.return_value = pypdf_text
        reader.reader = MagicMock(pages=[page])
        with patch.object(DocumentReader, "_read_mupdf_pages", return_value=[(mupdf_text, False)] if mupdf_text is not None else []):
            reader.set_pdf_doc_list()
        return reader

    def test_good_text_does_not_call_pypdf(self):
        reader = self.reader_with("정상 텍스트", "다른 텍스트")
        reader.reader.pages[0].extract_text.assert_not_called()
        self.assertEqual(reader.doc_list[0]["text"], "정상 텍스트")

    def test_empty_page_uses_pypdf_text(self):
        reader = self.reader_with("", "대체 텍스트")
        self.assertEqual(reader.doc_list[0]["text"], "대체 텍스트")
        self.assertEqual(reader.page_quality_list[0]["extractor"], "pypdf")

    def test_unreadable_file_uses_pypdf_text(self):
        reader = self.reader_with(None, "대체 텍스트")
        self.assertEqual(reader.page_quality_list[0]["extractor"], "pypdf")

    def test_worse_fallback_keeps_primary_text(self):
        garbled = "೜ਸ೜ਸ"
        reader = self.reader_with(garbled, "೜")
        self.assertEqual(reader.doc_list[0]["text"], garbled)
        self.assertEqual((reader.page_quality_list[0]["extractor"], reader.page_quality_list[0]["status"]), ("PyMuPDF", "GARBLED"))

    def test_none_from_pypdf_is_empty(self):
        reader = self.reader_with("", None)
        self.assertEqual(reader.doc_list[0]["text"], "")


class FakeOcr:
    name = "FakeOCR"
    version = "1"

    def __init__(self, text="월 5천원 인식 결과", error=None, disputed=()):
        self.text = text
        self.error = error
        self.disputed = disputed
        self.calls = 0

    def read_image(self, image: bytes) -> OcrResult:
        self.calls += 1
        self.assert_png = image.startswith(b"\x89PNG")
        if self.error:
            raise self.error
        return OcrResult(self.text, self.disputed)


class SelectiveOcrTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "a.pdf"
        with pymupdf.open() as document:
            document.new_page().insert_text((72, 72), "normal page")
            document.new_page().draw_rect(pymupdf.Rect(50, 50, 200, 200), fill=(0, 0, 0))
            document.new_page()
            document.save(self.path)

    def read(self, engine) -> DocumentReader:
        reader = DocumentReader(self.path, ocr_engine=engine)
        reader.set_pdf_reader()
        reader.set_pdf_doc_list()
        return reader

    def test_only_doubtful_page_is_read_and_stays_under_review(self):
        engine = FakeOcr()
        reader = self.read(engine)
        self.assertEqual(engine.calls, 1)                # 정상·빈 페이지는 OCR하지 않는다
        self.assertTrue(engine.assert_png)
        normal, drawn, blank = reader.page_quality_list
        self.assertEqual((normal["status"], normal["extractor"]), ("OK", "PyMuPDF"))
        self.assertEqual(blank["status"], "EMPTY")
        self.assertEqual((drawn["status"], drawn["extractor"], drawn["source_status"]), ("OCR_REVIEW", "FakeOCR", "OCR_REQUIRED"))
        self.assertIsNone(drawn["ocr_agreement"])        # 대조할 텍스트 레이어가 없다
        self.assertEqual(reader.doc_list[1]["text"], "월 5천원 인식 결과")

    def test_ocr_failure_keeps_original_status(self):
        for engine in (FakeOcr(error=RuntimeError("fail")), FakeOcr(text="  ")):
            quality = self.read(engine).page_quality_list[1]
            self.assertEqual((quality["status"], quality["extractor"]), ("OCR_REQUIRED", "PyMuPDF"))

    def test_without_engine_nothing_is_ocr_processed(self):
        self.assertEqual(self.read(None).page_quality_list[1]["status"], "OCR_REQUIRED")

    def suspect_reader(self, source: str, ocr_text: str, disputed=()) -> DocumentReader:
        reader = DocumentReader(self.path, ocr_engine=FakeOcr(ocr_text, disputed=disputed))
        reader.reader = MagicMock(pages=[MagicMock()])
        with patch.object(DocumentReader, "_read_mupdf_pages", return_value=[(source, False)]):
            reader.set_pdf_doc_list()
        return reader

    def test_suspect_page_keeps_text_layer_when_ocr_is_not_better(self):
        source = "연회비 없음 월 5천원 1만원 이상 시 \u0cdc 혜택 제공 안내 문구"
        reader = self.suspect_reader(source, "연회비 없음")
        quality = reader.page_quality_list[0]
        self.assertEqual(reader.doc_list[0]["text"], source)
        self.assertEqual((quality["extractor"], quality["status"], quality["source_status"]), ("PyMuPDF", "OCR_REVIEW", "SUSPECT"))
        self.assertFalse(quality["ocr_replaced"])
        self.assertEqual(quality["ocr_text"], "연회비 없음")
        self.assertEqual(quality["ocr_disputed_numbers"], ["1만원", "5천원"])    # 텍스트 레이어 숫자가 OCR에 없다

    def test_suspect_page_is_replaced_only_when_ocr_is_better(self):
        reader = self.suspect_reader("연회비 없음 월 5천원 \u0cdc", "연회비 없음 월 5천원 혜택 안내")
        quality = reader.page_quality_list[0]
        self.assertTrue(quality["ocr_replaced"])
        self.assertEqual((quality["extractor"], quality["status"]), ("FakeOCR", "OCR_REVIEW"))

    def test_few_suspect_characters_keep_text_layer_even_if_ocr_reads_more(self):
        source = "연회비 없음 월 5천원 " * 20 + "\u0cdc"
        reader = self.suspect_reader(source, source.replace("\u0cdc", "") + "사진 속 글자")
        quality = reader.page_quality_list[0]
        self.assertEqual(reader.doc_list[0]["text"], source)
        self.assertEqual((quality["extractor"], quality["ocr_replaced"]), ("PyMuPDF", False))

    def test_cross_check_disputes_are_kept(self):
        reader = self.suspect_reader("연회비 \u0cdc", "연회비 월 5천원 안내", disputed=("5%",))
        self.assertEqual(reader.page_quality_list[0]["ocr_disputed_numbers"], ["5%"])

    def test_agreement_uses_only_trusted_tokens(self):
        self.assertEqual(measure_ocr_agreement("월 5천원 ೜ਸ", "월5천원"), 1.0)
        self.assertEqual(measure_ocr_agreement("월 1만원", "월 2만원"), 0.5)
        self.assertIsNone(measure_ocr_agreement("೜ਸ", "월"))


@unittest.skipIf(ONE_PICK_STYLE is None, "카드 PDF 원본이 없는 환경")
class OnePickStyleTests(unittest.TestCase):
    """페이지 이미지와 대조해 확인한 표기가 추출되는지 검증한다."""

    def test_identity_h_font_without_to_unicode_is_extracted(self):
        reader = read(ONE_PICK_STYLE)
        self.assertEqual([row["status"] for row in reader.page_quality_list], ["OK", "OK"])
        self.assertEqual([row["extractor"] for row in reader.page_quality_list], ["PyMuPDF", "PyMuPDF"])
        self.assertGreater(reader.page_quality_list[0]["hangul_count"], 1400)
        page1, page2 = (doc["text"].replace(" ", "") for doc in reader.doc_list)
        for token in ("메가MGC커피", "3천원이상시", "1만원이상시", "월5천원", "월1천원", "5%", "50%", "10만원", "20만원"):
            self.assertIn(token, page1)
        self.assertIn("준법심의L-26-0542(2026.04.29)", page2)
        self.assertIn("Mastercard1.0%", page2)


if __name__ == "__main__":
    unittest.main()
