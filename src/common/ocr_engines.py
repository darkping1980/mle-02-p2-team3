"""``DocumentReader`` 에 선택적으로 연결하는 OCR 엔진 모듈.

엔진은 ``name``, ``version``, ``read_image(png 바이트) -> OcrResult`` 를 제공한다.
OCR 패키지는 선택 의존성이다(``uv sync --group ocr``). 엔진을 만들 때만 import하므로
OCR을 쓰지 않는 코드는 이 패키지가 없어도 동작한다.

RapidOCR 모델은 자동으로 내려받지 않는다. ``RAPIDOCR_MODEL_DIR`` 폴더에 미리 둔 파일만 쓴다.
"""

import asyncio
from dataclasses import dataclass
from importlib.metadata import version as package_version
import os
from pathlib import Path
import platform
import re

from dotenv import load_dotenv

RAPIDOCR_MODEL_DIR_ENV = "RAPIDOCR_MODEL_DIR"
RAPIDOCR_MODEL_FILES = {
    "Det.model_path": "ch_PP-OCRv5_det_mobile.onnx",
    "Cls.model_path": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    "Rec.model_path": "korean_PP-OCRv5_rec_mobile.onnx",
}
OCR_ENGINE_KINDS = ("windows", "rapidocr", "cross")

# 금액·할인율·횟수처럼 단위가 붙은 숫자. 틀리면 혜택 값이 달라지는 표기만 비교한다.
NUMERIC_PATTERN = re.compile(r"\d[\d,.]*\s*(?:%|천원|만원|원|회|개월|세|점)")


@dataclass(frozen=True)
class OcrResult:
    """OCR 결과 텍스트와 교차 확인에서 일치하지 않은 숫자 표기."""

    text: str
    disputed_numbers: tuple[str, ...] = ()


def extract_numbers(text: str) -> set[str]:
    """비교용 숫자 표기를 공백 없이 추출한다."""
    return {"".join(match.split()) for match in NUMERIC_PATTERN.findall(text)}


class WindowsOcrEngine:
    """Windows 내장 OCR. 추가 모델이 필요 없지만 Windows에서만 동작한다."""

    name = "WindowsOCR"

    def __init__(self, language: str = "ko"):
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine

        self.version = platform.version()
        self.engine = OcrEngine.try_create_from_language(Language(language))
        if self.engine is None:
            raise ValueError(f"Windows OCR 언어 팩이 없습니다: {language}")

    def read_image(self, image: bytes) -> OcrResult:
        """PNG 이미지를 읽어 줄 단위 텍스트를 반환한다."""
        return OcrResult(asyncio.run(self._recognize(image)))

    async def _recognize(self, image: bytes) -> str:
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(image)
        await writer.store_async()
        await writer.flush_async()
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        result = await self.engine.recognize_async(bitmap)
        return "\n".join(line.text for line in result.lines)


class RapidOcrEngine:
    """RapidOCR 한국어 모델. 운영체제와 무관하게 동작한다."""

    name = "RapidOCR"

    def __init__(self, model_dir: str | Path | None = None):
        from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

        load_dotenv()
        folder = model_dir or os.getenv(RAPIDOCR_MODEL_DIR_ENV)
        if not folder:
            raise ValueError(f"{RAPIDOCR_MODEL_DIR_ENV} 환경 변수가 필요합니다")
        paths = {key: Path(folder) / file_name for key, file_name in RAPIDOCR_MODEL_FILES.items()}
        missing = [path.name for path in paths.values() if not path.is_file()]
        if missing:
            raise ValueError(f"RapidOCR 모델 파일이 없습니다: {missing}")
        self.version = package_version("rapidocr")
        self.engine = RapidOCR(params={
            **{key: str(path) for key, path in paths.items()},
            "Det.ocr_version": OCRVersion.PPOCRV5,
            "Det.model_type": ModelType.MOBILE,
            "Rec.ocr_version": OCRVersion.PPOCRV5,
            "Rec.model_type": ModelType.MOBILE,
            "Rec.lang_type": LangRec.KOREAN,
        })

    def read_image(self, image: bytes) -> OcrResult:
        """PNG 이미지를 읽어 줄 단위 텍스트를 반환한다."""
        output = self.engine(image)
        return OcrResult("\n".join(output.txts) if output.txts else "")


class CrossCheckOcrEngine:
    """1차 엔진의 텍스트를 쓰고, 2차 엔진과 숫자 표기가 다른 항목을 함께 돌려준다."""

    def __init__(self, primary, secondary):
        self.primary = primary
        self.secondary = secondary
        self.name = f"{primary.name}+{secondary.name}"
        self.version = f"{primary.version}+{secondary.version}"

    def read_image(self, image: bytes) -> OcrResult:
        first = self.primary.read_image(image).text
        second = self.secondary.read_image(image).text
        joined_first, joined_second = "".join(first.split()), "".join(second.split())
        disputed = {number for number in extract_numbers(first) if number not in joined_second}
        disputed |= {number for number in extract_numbers(second) if number not in joined_first}
        return OcrResult(first, tuple(sorted(disputed)))


def create_ocr_engine(kind: str):
    """``windows``, ``rapidocr``, ``cross`` 중 하나의 엔진을 만든다."""
    if kind == "windows":
        return WindowsOcrEngine()
    if kind == "rapidocr":
        return RapidOcrEngine()
    if kind == "cross":
        return CrossCheckOcrEngine(WindowsOcrEngine(), RapidOcrEngine())
    raise ValueError(f"OCR 엔진은 {OCR_ENGINE_KINDS} 중 하나여야 합니다: {kind}")
