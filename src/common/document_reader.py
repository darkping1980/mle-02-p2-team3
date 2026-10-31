"""PDF/CSV 문서를 읽어 페이지별 텍스트 목록으로 만드는 도우미 모듈.

차량 매뉴얼 등록(``CarManualRegisterService``)과 샘플 스크립트가
PDF 페이지 텍스트를 ``doc_list`` 로 얻기 위해 사용한다.

PDF 텍스트는 PyMuPDF로 추출하고, 페이지 결과가 정상이 아니면 pypdf 결과와 비교해 나은 쪽을 쓴다.
pypdf는 ToUnicode가 없는 Identity-H 폰트의 글리프 번호를 문자로 내보내 한글이 깨진다.
"""

from typing import Any

import logging
from pathlib import Path
import sys
import unicodedata

from .ocr_engines import extract_numbers

reader_logger = logging.getLogger("common.document_reader")

PDF_EXTRACTOR_PYMUPDF = "PyMuPDF"
PDF_EXTRACTOR_PYPDF = "pypdf"

OCR_DPI = 300                                               # OCR에 넘길 페이지 이미지 해상도
OCR_TARGET_STATUS = ("SUSPECT", "GARBLED", "OCR_REQUIRED")  # OCR로 다시 읽는 페이지 상태
OCR_MIN_AGREEMENT = 0.8                                     # SUSPECT 페이지를 OCR로 바꾸는 최소 어절 일치율
OCR_MIN_SUSPECT_RATIO = 0.05                                # 의심 문자가 이 비율 미만이면 기호 오탐으로 보고 텍스트를 유지한다

GARBLED_RATIO = 0.1                 # 공백 외 문자 중 의심 문자가 이 비율을 넘으면 깨진 페이지로 본다
TEXT_SCRIPTS = (                    # 유니코드 문자 이름의 첫 단어. 그 밖의 문자(글자)는 의심 문자로 센다
    "LATIN", "HANGUL", "CJK", "HIRAGANA", "KATAKANA", "GREEK", "FULLWIDTH", "HALFWIDTH",
)


def is_suspect_char(char: str) -> bool:
    """추출 오류로 볼 문자인지 판단한다. 대체 문자, 제어·사용자 정의 문자, 예상 밖 문자권 글자가 해당한다."""
    if char.isspace():
        return False
    category = unicodedata.category(char)
    if char == "�" or category in ("Cc", "Co", "Cn", "Cs"):
        return True
    return category.startswith("L") and unicodedata.name(char, "").split(" ")[0] not in TEXT_SCRIPTS


def measure_ocr_agreement(source_text: str, ocr_text: str) -> float | None:
    """텍스트 레이어의 정상 어절이 OCR 결과에 있는 비율. 대조할 어절이 없으면 ``None`` 이다."""
    tokens = [token for token in source_text.split() if not any(is_suspect_char(char) for char in token)]
    if not tokens:
        return None
    joined = "".join(ocr_text.split())
    return sum(token in joined for token in tokens) / len(tokens)


def measure_pdf_text(text: str, has_visual: bool) -> dict[str, Any]:
    """페이지 텍스트의 문자 수와 추출 상태를 계산한다.

    Args:
        text: 추출한 페이지 텍스트.
        has_visual: 이미지가 있거나, 텍스트 없이 눈에 보이는 내용(도형으로 그린 글자 등)이 있는 페이지 여부.

    Returns:
        ``status`` 는 OK, SUSPECT(일부 문자 의심), GARBLED(문자가 깨짐),
        OCR_REQUIRED(텍스트 없이 보이는 내용만 있음), EMPTY(빈 페이지) 중 하나다.
        ``ocr_engine`` 으로 다시 읽은 페이지는 ``set_pdf_doc_list()`` 가 OCR_REVIEW로 바꾼다.
        OK여도 표의 행·셀 대응이나 이미지 안의 글자까지 추출됐다는 뜻은 아니다.
    """
    char_count = sum(not char.isspace() for char in text)
    suspect_count = sum(is_suspect_char(char) for char in text)
    if char_count == 0:
        status = "OCR_REQUIRED" if has_visual else "EMPTY"
    elif suspect_count / char_count > GARBLED_RATIO:
        status = "GARBLED"
    elif suspect_count:
        status = "SUSPECT"
    else:
        status = "OK"
    return {
        "char_count": char_count,
        "hangul_count": sum("가" <= char <= "힣" for char in text),
        "digit_count": sum(char.isdigit() for char in text),
        "suspect_count": suspect_count,
        "has_visual": has_visual,
        "status": status,
    }


#=========================================================
# 문서 파일 읽기 및 전처리 관리
#=========================================================
class DocumentReader:
    """
    문서 파일 읽기 및 전처리 관리

    파일 경로만 받아 두고, 실제 읽기는 ``set_pdf_reader()`` / ``set_csv_reader()`` 를
    호출할 때 수행한다. 사용 순서(PDF):

        reader = DocumentReader(file_path)
        reader.set_pdf_reader()      # self.reader = pypdf.PdfReader
        reader.set_pdf_doc_list()    # self.doc_list 에 페이지별 dict 추가

    Attributes:
        file_path: 읽을 파일 경로(``Path``).
        reader: ``pypdf.PdfReader`` 또는 ``pandas.DataFrame``. 읽기 전에는 ``None``.
        doc_list: ``{"page_no": 1부터 시작, "text": 추출 텍스트}`` dict 목록.
        page_quality_list: ``doc_list`` 와 같은 순서의 페이지별 추출기·문자 수·상태 dict 목록.
    """

    file_path :str          # 파일경로
    doc_list : list[Any]    # 문서 리스트
    reader : Any            # 문서 리더 객체
    page_quality_list : list[dict[str, Any]]    # 페이지별 추출 품질
    ocr_engine : Any                            # 선택 OCR 엔진. name, version, read_image(png 바이트) 제공 (common.ocr_engines)

    #=========================================================
    # 생성자 읽을 파일 설정
    #=========================================================
    def __init__(self, file_path, ocr_engine=None):
        """
        읽을 파일 경로를 ``Path`` 로 저장하고 reader와 doc_list를 빈 상태로 초기화한다.

        파일은 이 시점에 열지 않으며, 상대 경로는 현재 작업 디렉터리 기준으로 해석된다.
        ``ocr_engine`` 을 생략하면 OCR을 하지 않는다. 지정해도 정상 페이지는 OCR하지 않는다.
        """
        self.file_path = Path(file_path)
        self.reader = None
        self.doc_list = []
        self.page_quality_list = []
        self.ocr_engine = ocr_engine


    #=========================================================
    # pdf 읽어서 설정
    #=========================================================
    def set_pdf_reader(self):
        """
        pdf 읽어서 설정

        ``pypdf.PdfReader`` 로 ``self.file_path`` 를 열어 ``self.reader`` 에 보관한다.
        """
        # region [Python 설명] 함수 안의 import
        # import를 함수 본문에 두면 이 메서드를 실제로 호출할 때만 모듈을 불러온다.
        # PDF를 읽지 않는 코드에서는 pypdf/pandas를 불러오지 않아 import 시간과 의존성을 줄인다.
        # endregion
        from pypdf import PdfReader

        self.reader = PdfReader(self.file_path)

    #=========================================================
    # csv 읽어서 설정
    #=========================================================
    def set_csv_reader(self):
        """
        csv 읽어서 설정

        ``pandas.read_csv()`` 결과 ``DataFrame`` 을 ``self.reader`` 에 보관한다.
        """
        import pandas as pd

        self.reader = pd.read_csv(self.file_path)


    #=========================================================
    # 읽은 pdf 내용 doc_list 로 설정
    #=========================================================
    def set_pdf_doc_list(self):
        """
        읽은 pdf 내용 doc_list 로 설정

        ``set_pdf_reader()`` 를 먼저 호출해야 한다. 기존 ``doc_list`` 를 비우지 않고 뒤에 추가하므로
        두 번 호출하면 페이지가 중복된다. 추출 결과의 상태는 ``page_quality_list`` 에서 확인한다.
        """
        import pymupdf
        import pypdf

        mupdf_pages = self._read_mupdf_pages()

        # 페이지를 순서대로 돌며 텍스트를 추출한다.
        # region [Python 설명] enumerate()
        # `enumerate(items)`는 `(index, item)` 쌍을 0부터 순서대로 돌려준다.
        # Java의 `for (int i = 0; ...)`와 향상된 for문을 합친 형태로 생각하면 된다.
        # endregion
        for i, page in enumerate(self.reader.pages):
            text, has_visual = mupdf_pages[i] if i < len(mupdf_pages) else ("", False)
            extractor, version = PDF_EXTRACTOR_PYMUPDF, pymupdf.__version__
            quality = measure_pdf_text(text, has_visual)

            # 텍스트를 얻지 못했거나 깨진 페이지만 pypdf로 다시 읽고, 정상 문자가 더 많을 때만 바꾼다.
            if quality["status"] in ("GARBLED", "OCR_REQUIRED", "EMPTY"):
                fallback_text = page.extract_text() or ""
                fallback_quality = measure_pdf_text(fallback_text, has_visual)
                if (fallback_quality["char_count"] - fallback_quality["suspect_count"]
                        > quality["char_count"] - quality["suspect_count"]):
                    text, quality = fallback_text, fallback_quality
                    extractor, version = PDF_EXTRACTOR_PYPDF, pypdf.__version__

            if self.ocr_engine is not None and quality["status"] in OCR_TARGET_STATUS:
                ocr_result = self._read_page_with_ocr(i, text, quality)
                if ocr_result is not None:
                    text, quality, replaced = ocr_result
                    if replaced:
                        extractor, version = self.ocr_engine.name, self.ocr_engine.version

            self.doc_list.append({             # 현재 페이지 번호와 추출 텍스트를 하나의 딕셔너리로 목록에 추가
                "page_no": i + 1,               # 사용자에게 보이는 실제 페이지 순서처럼 1부터 시작하도록 페이지 번호 저장
                "text": text                    # 현재 페이지에서 추출된 전체 텍스트 저장
            })
            self.page_quality_list.append({"page_no": i + 1, "extractor": extractor, "extractor_ver": version, **quality})

    def _read_page_with_ocr(self, index: int, source_text: str, source_quality: dict[str, Any]):
        """페이지를 OCR로 다시 읽는다. OCR 실패·빈 결과이면 ``None`` 을 반환해 기존 결과를 유지한다.

        OCR은 금액·비율을 틀릴 수 있어 자동 확정하지 않는다. 상태는 항상 OCR_REVIEW이고, 대조 결과를
        ``ocr_text``, ``ocr_replaced``, ``ocr_agreement``, ``ocr_disputed_numbers`` 로 남긴다.

        Returns:
            ``(채택한 텍스트, 품질 dict, OCR 채택 여부)`` tuple 또는 ``None``.
        """
        import pymupdf

        try:
            with pymupdf.open(self.file_path) as document:
                image = document[index].get_pixmap(dpi=OCR_DPI).tobytes("png")
            result = self.ocr_engine.read_image(image)
        except Exception as exc:
            reader_logger.warning("OCR 실패 page=%d: %s", index + 1, type(exc).__name__)
            return None
        ocr_text = result.text
        if not ocr_text or not ocr_text.strip():
            return None

        ocr_quality = measure_pdf_text(ocr_text, source_quality["has_visual"])
        agreement = measure_ocr_agreement(source_text, ocr_text)
        replaced = self._ocr_is_better(source_quality, ocr_quality, agreement)
        trusted = " ".join(token for token in source_text.split() if not any(map(is_suspect_char, token)))
        joined = "".join(ocr_text.split())
        disputed = set(result.disputed_numbers) | {number for number in extract_numbers(trusted) if number not in joined}
        quality = dict(ocr_quality if replaced else source_quality)
        quality.update(
            status="OCR_REVIEW",
            source_status=source_quality["status"],
            source_text=source_text,
            ocr_text=ocr_text,
            ocr_replaced=replaced,
            ocr_agreement=agreement,
            ocr_disputed_numbers=sorted(disputed),
            ocr_engine=self.ocr_engine.name,
        )
        return (ocr_text if replaced else source_text), quality, replaced

    @staticmethod
    def _ocr_is_better(source_quality: dict[str, Any], ocr_quality: dict[str, Any], agreement: float | None) -> bool:
        """OCR 결과로 바꿀지 판단한다.

        SUSPECT는 문서 기호를 잘못 잡은 오탐이 많고 텍스트 레이어의 나머지 문자는 정확하다.
        의심 문자가 충분히 많고, OCR이 정상 문자를 더 많이 읽었으며, 텍스트 레이어와도 맞을 때만 바꾼다.
        """
        if source_quality["status"] != "SUSPECT":
            return True
        valid = lambda quality: quality["char_count"] - quality["suspect_count"]  # noqa: E731
        return (source_quality["suspect_count"] / source_quality["char_count"] >= OCR_MIN_SUSPECT_RATIO
                and valid(ocr_quality) >= valid(source_quality)
                and agreement is not None and agreement >= OCR_MIN_AGREEMENT)

    def _read_mupdf_pages(self) -> list[tuple[str, bool]]:
        """PyMuPDF로 페이지별 ``(텍스트, 시각 요소 포함 여부)`` 를 읽는다. 열 수 없는 파일이면 빈 목록을 반환한다."""
        import pymupdf

        def has_visual(page, text: str) -> bool:
            """이미지가 있거나, 텍스트가 없는데 렌더링 결과가 한 가지 색이 아니면 보이는 내용이 있다."""
            if page.get_image_info():
                return True
            if text.strip():
                return False
            samples = page.get_pixmap(dpi=40, colorspace=pymupdf.csGRAY).samples
            return min(samples) != max(samples)

        try:
            with pymupdf.open(self.file_path) as document:
                return [(text, has_visual(page, text)) for page in document for text in (page.get_text(),)]
        except (pymupdf.FileDataError, pymupdf.mupdf.FzErrorBase):
            return []

    #=========================================================
    # doc_list 청크 설정후 재저장
    #=========================================================
    def set_pdf_chunk_doc_list(selft):
        """
        doc_list 청크 설정후 재저장

        아직 구현되지 않았다. 호출하면 안내 문구만 출력한다.
        (첫 매개변수 이름이 ``self`` 가 아닌 ``selft`` 지만 Python은 첫 인자를 이름과 무관하게 인스턴스로 전달한다.)
        """
        print("구현 예정")

