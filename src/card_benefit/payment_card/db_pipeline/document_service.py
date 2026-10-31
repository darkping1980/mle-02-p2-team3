"""수집 PDF 한 건을 읽어 페이지·청크로 구성하는 모듈. DB에 접근하지 않는다.

PDF 텍스트는 공통 ``DocumentReader`` 로 읽고, 정상 추출이 확인되지 않은 페이지가 있으면 등록을 막는다.
청크는 PAGE_V1 규칙으로 페이지당 1건이다. 표가 청크 경계로 갈라지지 않고, AI 호출과 근거 위치가 페이지와 일치한다.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re

from common.document_reader import DocumentReader

DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "hana_all"
MANIFEST_NAME = "manifest.csv"

UNCONFIRMED_SOURCE_NOTE = "URL 추정으로 찾은 문서. 상품 페이지 직접 링크 없음, 공식 출처 미확정"
BLOCKING_PAGE_STATUS = ("SUSPECT", "GARBLED", "OCR_REQUIRED")   # 원문을 믿을 수 없어 등록하지 않는 페이지 상태
SPLIT_RULE_VER = "PAGE_V1"                                    # 분리 규칙을 바꾸면 V 번호도 올린다

KST = timezone(timedelta(hours=9))                            # manifest 수집일시의 기준 시간대
FILE_CODE_PATTERN = re.compile(r"_(\d+)_(\d{8})\.pdf$", re.IGNORECASE)
REVIEW_PATTERN = re.compile(r"^.*준법심의\s*\S+?\((\d{4})\.(\d{1,2})\.(\d{1,2})\).*$", re.MULTILINE)
QUALITY_PATTERNS = {
    "amount": re.compile(r"\d[\d,]*(?:천|만)?원"),
    "rate": re.compile(r"\d+(?:\.\d+)?%"),
    "count": re.compile(r"[일월연] ?\d+회"),
}


@dataclass(frozen=True)
class DocPage:
    """``card_doc_page`` 한 행. ``text`` 는 추출 결과를 정규화하지 않은 원문이다."""

    page_no: int
    text: str
    sha256: str
    layer_cd: str
    extractor_nm: str
    extractor_ver: str
    read_quality: dict

    @property
    def char_cnt(self) -> int:
        return len(self.text)

    @property
    def in_review(self) -> bool:
        """OCR로 읽어 사람의 확인이 필요한 페이지인지 여부."""
        return self.read_quality["status"] == "OCR_REVIEW"

    @property
    def note(self) -> str | None:
        """``page_note`` 값. 검토 대상 페이지의 사유를 남긴다."""
        if not self.in_review:
            return None
        quality = self.read_quality
        agreement = quality["ocr_agreement"]
        return (
            f"OCR_REVIEW engine={quality['ocr_engine']} source={quality['source_status']}"
            f" replaced={quality['ocr_replaced']}"
            f" agreement={'NA' if agreement is None else f'{agreement:.2f}'}"
            f" disputed={quality['ocr_disputed_numbers']}"
        )


@dataclass(frozen=True)
class DocChunk:
    """``card_doc_chunk`` 한 행. 위치는 페이지 원문 기준 1부터이고 종료 위치의 문자를 포함한다."""

    page_no: int
    seq: int
    start_pos: int
    end_pos: int
    text: str
    status: str = "RAW"          # CHUNK_STATUS 공통코드. 검토 대상 페이지의 청크는 EXCLUDED로 AI 입력에서 뺀다


@dataclass(frozen=True)
class ParsedDocument:
    """``card_doc`` 메타데이터와 추출한 페이지·청크."""

    doc_cd: str
    doc_family_cd: str
    doc_type_cd: str
    doc_title: str
    doc_source_url: str
    doc_file_nm: str
    doc_file_size: int
    doc_sha256: str
    doc_review_no: str | None
    doc_review_date: date | None
    doc_collect_date: datetime
    doc_note: str
    pages: tuple[DocPage, ...]
    chunks: tuple[DocChunk, ...]

    def quality(self) -> list[dict]:
        """페이지별 추출 상태. 문자가 추출됐다는 뜻일 뿐 표의 행·셀 대응까지 보장하지는 않는다."""
        return [
            {
                "page_no": page.page_no,
                "extractor": page.extractor_nm,
                "status": page.read_quality["status"],
                "chars": page.char_cnt,
                "hangul": page.read_quality["hangul_count"],
                "digit": page.read_quality["digit_count"],
                "suspect": page.read_quality["suspect_count"],
                "layer_cd": page.layer_cd,
                "note": page.note,
                **{name: len(pattern.findall(page.text)) for name, pattern in QUALITY_PATTERNS.items()},
            }
            for page in self.pages
        ]


def sha256_hex(data: bytes) -> str:
    """소문자 16진수 SHA-256. ``card_doc`` 과 ``card_doc_page`` 의 해시 형식이다."""
    return hashlib.sha256(data).hexdigest()


class DocumentService:
    """manifest에 있는 공식 상품설명서 PDF를 검증하고 페이지·청크로 구성한다."""

    def __init__(self, data_root: Path = DATA_ROOT, ocr_engine=None):
        self.data_root = Path(data_root)
        self.ocr_engine = ocr_engine

    def read(self, pdf: str | Path) -> ParsedDocument:
        """PDF를 검증해 읽는다. ``pdf`` 가 상대 경로이면 ``data_root`` 기준이다.

        Raises:
            ValueError: 파일이 없거나 PDF가 아닌 경우, manifest와 다르거나 대상 문서가 아닌 경우.
        """
        path, relative_path = self._resolve(pdf)
        rows = self._manifest_rows(relative_path)
        content = path.read_bytes()
        if not content.startswith(b"%PDF-"):
            raise ValueError(f"PDF 파일이 아닙니다: {relative_path}")
        file_sha256 = sha256_hex(content)
        row = rows[0]
        if file_sha256 != row["SHA256"] or len(content) != int(row["파일크기(byte)"]):
            raise ValueError(f"manifest의 해시·크기와 다른 파일입니다: {relative_path}")

        pages = self._read_pages(path)
        if len(pages) != int(row["페이지수"]):
            raise ValueError(f"manifest의 페이지 수({row['페이지수']})와 다릅니다: {len(pages)}쪽")

        match = FILE_CODE_PATTERN.search(path.name)
        if match is None:
            raise ValueError(f"파일명에서 디자인코드와 날짜를 찾지 못했습니다: {path.name}")
        design_cd, file_date = match.groups()
        review_no, review_date = self._find_review(pages)
        names = list(dict.fromkeys(item["카드상품명"] for item in rows))
        note = self._source_note(row["문서구분"])
        if len(names) > 1:
            note += f" / 공유 상품: {', '.join(names)}"
        return ParsedDocument(
            doc_cd=f"HANA_{design_cd}_{file_date}",
            doc_family_cd=f"HANA_{design_cd}",
            doc_type_cd="PRODUCT_GUIDE",
            doc_title=f"{names[0]} 상품설명서",
            doc_source_url=row["PDF원본URL"],
            doc_file_nm=(Path(self.data_root.name) / relative_path).as_posix(),
            doc_file_size=len(content),
            doc_sha256=file_sha256,
            doc_review_no=review_no,
            doc_review_date=review_date,
            doc_collect_date=datetime.fromisoformat(row["수집일시"]).replace(tzinfo=KST),
            doc_note=note,
            pages=pages,
            chunks=self._split_pages(pages),
        )

    @staticmethod
    def _source_note(source_kind: str) -> str:
        """``doc_note`` 출처 설명. URL 추정으로 찾은 문서는 공식 출처로 표시하지 않는다."""
        return UNCONFIRMED_SOURCE_NOTE if "URL 추정" in source_kind else source_kind

    def _resolve(self, pdf: str | Path) -> tuple[Path, Path]:
        """``data_root`` 안의 실제 파일 경로와 manifest 조회용 상대 경로를 반환한다."""
        root = self.data_root.resolve()
        path = (root / pdf).resolve()                # pdf가 절대 경로이면 그 경로가 그대로 쓰인다
        if not path.is_relative_to(root):
            raise ValueError(f"{root} 아래의 PDF만 등록할 수 있습니다: {pdf}")
        if not path.is_file():
            raise ValueError(f"PDF 파일이 없습니다: {pdf}")
        return path, path.relative_to(root)

    def _manifest_rows(self, relative_path: Path) -> list[dict]:
        """이 파일의 manifest 행을 반환한다. 공식 상품설명서 행이 없으면 등록 대상이 아니다."""
        with (self.data_root / MANIFEST_NAME).open(encoding="utf-8-sig", newline="") as file:
            rows = [row for row in csv.DictReader(file) if row["파일경로"] == relative_path.as_posix()]
        if not rows:
            raise ValueError(f"manifest에 없는 파일입니다: {relative_path}")
        guides = [row for row in rows if row["문서구분"].startswith("공식 원본") and "상품설명서" in row["문서종류"]]
        if not guides:
            raise ValueError(f"공식 상품설명서가 아닙니다: {relative_path}")
        return guides

    def _read_pages(self, path: Path) -> tuple[DocPage, ...]:
        """공통 Reader로 페이지별 원문을 읽는다. 정상 추출이 확인되지 않은 페이지가 있으면 거부한다."""
        reader = DocumentReader(path, ocr_engine=self.ocr_engine)
        reader.set_pdf_reader()
        if reader.reader.is_encrypted:
            raise ValueError(f"암호화된 PDF입니다: {path.name}")
        reader.set_pdf_doc_list()
        blocked = [(row["page_no"], row["status"]) for row in reader.page_quality_list
                   if row["status"] in BLOCKING_PAGE_STATUS]
        if blocked:
            raise ValueError(f"원문 추출을 신뢰할 수 없는 페이지가 있습니다: {blocked}")
        pages = []
        for doc, quality in zip(reader.doc_list, reader.page_quality_list):
            # PostgreSQL text는 NUL을 저장할 수 없다. 같은 길이의 문자로 바꿔 위치를 유지한다.
            text = doc["text"].replace("\x00", "�")
            pages.append(DocPage(
                page_no=doc["page_no"],
                text=text,
                sha256=sha256_hex(text.encode("utf-8")),
                layer_cd=self._layer_cd(quality.get("source_text", text), quality["has_visual"]),
                extractor_nm=quality["extractor"],
                extractor_ver=quality["extractor_ver"],
                read_quality=quality,
            ))
        return tuple(pages)

    @staticmethod
    def _layer_cd(text: str, has_visual: bool) -> str:
        """``PAGE_LAYER`` 공통코드. 이미지가 함께 있으면 그 안의 글자는 추출되지 않았을 수 있다."""
        if text.strip():
            return "MIXED" if has_visual else "TEXT"
        return "IMAGE" if has_visual else "UNKNOWN"

    @staticmethod
    def _find_review(pages: tuple[DocPage, ...]) -> tuple[str | None, date | None]:
        """준법심의 표기 줄 원문과 심의일을 찾는다. 표기가 없으면 추정하지 않고 ``None`` 으로 둔다."""
        for page in pages:
            match = REVIEW_PATTERN.search(page.text)
            if match:
                return match.group(0).strip(), date(*map(int, match.groups()))
        return None, None

    def _split_pages(self, pages: tuple[DocPage, ...]) -> tuple[DocChunk, ...]:
        """페이지 전체를 청크 1건으로 만든다. 내용이 없는 페이지는 건너뛰고, 순번은 문서 전체 기준이다."""
        chunks: list[DocChunk] = []
        for page in pages:
            if page.text.strip():
                status = "EXCLUDED" if page.in_review else "RAW"
                chunks.append(DocChunk(page.page_no, len(chunks) + 1, 1, page.char_cnt, page.text, status))
        return tuple(chunks)
