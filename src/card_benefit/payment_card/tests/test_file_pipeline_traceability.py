from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from payment_card.file_pipeline.doc_index.traceability import create_traceability, write_traceability


class FakeDocumentReader:
    pages: list[dict]
    qualities: list[dict]

    def __init__(self, _path: Path):
        self.doc_list = []
        self.page_quality_list = []

    def set_pdf_reader(self):
        pass

    def set_pdf_doc_list(self):
        self.doc_list = [
            {"page_no": page["page_no"], "text": page["text"]}
            for page in self.pages
        ]
        self.page_quality_list = self.qualities


class TraceabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.pdf = self.root / "sample.pdf"
        self.pdf.write_bytes(b"%PDF-fake source")
        FakeDocumentReader.pages = [
            {"page_no": 1, "text": "혜택 원문\n조건 문장"},
            {"page_no": 2, "text": "   "},
        ]
        FakeDocumentReader.qualities = [
            {"page_no": 1, "status": "OK", "extractor": "PyMuPDF", "extractor_ver": "test"},
            {"page_no": 2, "status": "EMPTY", "extractor": "PyMuPDF", "extractor_ver": "test"},
        ]

    def make_traceability(self, **options):
        with patch("payment_card.file_pipeline.doc_index.traceability.DocumentReader", FakeDocumentReader):
            return create_traceability(self.pdf, **options)

    def test_preserves_pages_and_exact_one_based_chunk_span(self):
        result = self.make_traceability()

        self.assertEqual(result["document"]["sha256"], hashlib.sha256(self.pdf.read_bytes()).hexdigest())
        self.assertEqual(result["document"]["page_count"], 2)
        self.assertEqual([page["page_no"] for page in result["pages"]], [1, 2])
        self.assertEqual(len(result["chunks"]), 1)
        chunk = result["chunks"][0]
        page_text = result["pages"][chunk["page_no"] - 1]["text"]
        self.assertEqual(page_text[chunk["start_pos"] - 1:chunk["end_pos"]], chunk["text"])
        self.assertEqual((chunk["start_pos"], chunk["end_pos"]), (1, len(page_text)))
        self.assertEqual(result["pages"][1]["chunk_status"], "NO_TEXT")
        self.assertIn("눈으로 확인", result["pages"][1]["excluded_reason"])

    def test_rejects_unexpected_hash_or_page_count(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.make_traceability(expected_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "페이지 수"):
            self.make_traceability(expected_page_count=3)
        with self.assertRaisesRegex(ValueError, "1 이상"):
            self.make_traceability(expected_page_count=0)

    def test_writes_json_without_overwriting_by_default(self):
        result = self.make_traceability()
        output = self.root / "trace.json"
        write_traceability(result, output)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["document"]["page_count"], 2)
        with self.assertRaisesRegex(FileExistsError, "파일이 이미 있습니다"):
            write_traceability(result, output)

    @unittest.skip("main 의 src/common/ocr_engines.py 가 python-dotenv 를 모듈 최상단에서 필수로 임포트한다(팀 코드, main 의 pyproject 에 필수 의존성으로 선언됨). 선택 의존성 가정은 더는 성립하지 않는다.")
    def test_document_reader_import_does_not_require_optional_dotenv(self):
        repo_root = Path(__file__).resolve().parents[4]
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(repo_root / "src"), str(repo_root / "src/card_benefit")))
        code = "import sys; sys.modules['dotenv'] = None; from common.document_reader import DocumentReader"

        result = subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
