"""OCR 엔진 단위 테스트. 패키지·모델이 없는 환경에서는 실제 엔진 시험을 건너뛴다."""

from __future__ import annotations

from importlib.util import find_spec
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from common.ocr_engines import CrossCheckOcrEngine, OcrResult, RapidOcrEngine, create_ocr_engine, extract_numbers


class Fake:
    version = "1"

    def __init__(self, name, text):
        self.name = name
        self.text = text

    def read_image(self, image):
        return OcrResult(self.text)


class ExtractNumbersTests(unittest.TestCase):
    def test_only_numbers_with_units(self):
        self.assertEqual(extract_numbers("월 5천원, 1.0 % 일 1 회 1800-1111"), {"5천원", "1.0%", "1회"})


class CrossCheckTests(unittest.TestCase):
    def check(self, first, second):
        return CrossCheckOcrEngine(Fake("A", first), Fake("B", second)).read_image(b"")

    def test_same_numbers_have_no_dispute(self):
        result = self.check("월 5천원 5%", "월5천원 5 %")
        self.assertEqual((result.text, result.disputed_numbers), ("월 5천원 5%", ()))

    def test_different_numbers_are_disputed_from_both_sides(self):
        self.assertEqual(self.check("월 5천원 5%", "월 3천원 5%").disputed_numbers, ("3천원", "5천원"))

    def test_name_keeps_both_engines(self):
        engine = CrossCheckOcrEngine(Fake("A", ""), Fake("B", ""))
        self.assertEqual((engine.name, engine.version), ("A+B", "1+1"))


class ConfigurationTests(unittest.TestCase):
    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            create_ocr_engine("other")

    @unittest.skipIf(find_spec("rapidocr") is None, "ocr 의존성 그룹이 없는 환경")
    def test_rapidocr_requires_prepared_models(self):
        with patch.dict(os.environ, {"RAPIDOCR_MODEL_DIR": ""}), patch("common.ocr_engines.load_dotenv"):
            with self.assertRaisesRegex(ValueError, "RAPIDOCR_MODEL_DIR"):
                RapidOcrEngine()
        with self.assertRaisesRegex(ValueError, "모델 파일이 없습니다"):
            RapidOcrEngine(Path(__file__).parent)


if __name__ == "__main__":
    unittest.main()
