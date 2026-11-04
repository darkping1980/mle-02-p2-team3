"""수집 PDF 한 건을 읽어 페이지·청크로 구성하는 모듈. DB에 접근하지 않는다.

PDF 텍스트는 공통 ``DocumentReader`` 로 읽고, 정상 추출이 확인되지 않은 페이지가 있으면 등록을 막는다.
청크는 PAGE_V1 규칙으로 페이지당 1건이다. 표가 청크 경계로 갈라지지 않고, AI 호출과 근거 위치가 페이지와 일치한다.

[등록 파이프라인에서의 위치] 1단계의 "PDF 파싱 → 페이지/청크 생성" 부분. 결과는 메모리 객체(ParsedDocument)뿐이고,
DB 저장은 ``RegisterService`` → ``DocRepository`` 가 한다.

처리 흐름 (``DocumentService.read``)
    1. ``inspect``      : 경로 확인 → PDF 시그니처(%PDF-) 확인 → SHA-256 계산 → 메타데이터(doc_cd 등) 구성
                          · 하나카드: ``data/raw/hana_all/manifest.csv`` 의 해시·크기와 일치해야 한다.
                          · 타사(external_source): manifest 없이 CLI 인자로 받은 메타데이터를 쓴다.
    2. ``_read_pages``  : 공통 ``DocumentReader`` (common/document_reader.py)로 페이지 텍스트 추출.
                          SUSPECT·GARBLED·OCR_REQUIRED 페이지가 있으면 ValueError로 등록 자체를 거부한다.
    3. 페이지 수 대조, 파싱 중 파일 변경 여부(SHA-256 재계산) 확인
    4. ``_find_review`` : 준법심의 번호·일자 추출(없으면 None)
    5. ``_split_pages`` : 페이지 → 청크(DocChunk). PAGE_V1=페이지 1건, BLOCK_V1=block_chunking.split_blocks

데이터 클래스와 테이블의 대응(Java의 DTO/VO에 해당)
    ParsedDocument → card_doc 1행 / DocPage → card_doc_page 1행 / DocChunk → card_doc_chunk 1행
    PK는 Python이 만들지 않는다. card_doc_id·card_doc_chunk_id는 INSERT 시 DB 기본값(fn_get_biz_id)이 발급한다.

호출하는 곳: register_service.RegisterService, document_repository.DocRepository(page_chunks), main.py
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
import unicodedata

from common.document_reader import DocumentReader, measure_pdf_text

from .block_chunking import SPLIT_RULE_BLOCK, split_blocks

DATA_ROOT = Path(__file__).resolve().parents[2] / "data" / "raw" / "hana_all"
MANIFEST_NAME = "manifest.csv"

UNCONFIRMED_SOURCE_NOTE = "URL 추정으로 찾은 문서. 상품 페이지 직접 링크 없음, 공식 출처 미확정"
BLOCKING_PAGE_STATUS = ("SUSPECT", "GARBLED", "OCR_REQUIRED")   # 원문을 믿을 수 없어 등록하지 않는 페이지 상태
SPLIT_RULE_VER = "PAGE_V1"                                    # 분리 규칙을 바꾸면 V 번호도 올린다

KST = timezone(timedelta(hours=9))                            # manifest 수집일시의 기준 시간대
FILE_CODE_PATTERN = re.compile(r"_([A-Za-z]*\d+)_(\d{8})\.pdf$", re.IGNORECASE)
SIX_DIGIT_DATE_PATTERN = re.compile(r"_(\d{6})\.pdf$", re.IGNORECASE)
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
    chunk_type_cd: str = "BODY"  # CHUNK_TYPE 공통코드. BLOCK_V1은 유의사항을 NOTICE로 나눈다
    split_rule_ver: str = SPLIT_RULE_VER


@dataclass(frozen=True)
class ParsedDocument:
    """``card_doc`` 메타데이터와 추출한 페이지·청크."""

    doc_cd: str
    doc_family_cd: str
    doc_type_cd: str
    doc_title: str
    doc_source_url: str | None
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


@dataclass(frozen=True)
class ExternalDocumentSource:
    """Manifest-less, explicitly identified source for a non-Hana card PDF."""

    issuer_cd: str
    doc_code_prefix: str
    doc_family_cd: str
    doc_title: str
    doc_type_cd: str = "PRODUCT_GUIDE"
    doc_source_url: str | None = None


class DocumentService:
    """manifest에 있는 공식 상품설명서 PDF를 검증하고 페이지·청크로 구성한다."""

    def __init__(self, data_root: Path = DATA_ROOT, ocr_engine=None, split_rule: str = SPLIT_RULE_VER,
                 external_source: ExternalDocumentSource | None = None):
        self.data_root = Path(data_root)
        self.ocr_engine = ocr_engine
        self.split_rule = split_rule
        self.external_source = external_source

    def inspect(self, pdf: str | Path) -> ParsedDocument:
        """파일과 manifest를 확인해 문서 메타데이터만 만든다. 페이지는 파싱하지 않는다(``pages=()``, ``chunks=()``).

        ``pdf`` 가 상대 경로이면 ``data_root`` 기준이다. 중복 등록 판정에 쓰는 ``doc_sha256`` 과 ``doc_cd`` 가
        여기서 정해지므로, ``RegisterService.register`` 는 먼저 이 함수만 호출해 DB에 같은 문서가 있는지 본다.

        doc_cd 규칙
            하나카드: ``HANA_{디자인코드}_{파일명 날짜}`` (파일명 ``_코드_YYYYMMDD.pdf`` 에서 추출)
            타사: ``{doc_code_prefix}_{YYMMDD}_{SHA-256 앞 12자}``

        Raises:
            ValueError: 파일이 없거나 PDF가 아닌 경우, manifest와 다르거나 대상 문서가 아닌 경우.
        """
        # 원래 두 번째 docstring이던 설명(위 docstring과 같은 함수 설명이며 실행되지 않는 문자열이다):
        """PDF를 검증해 읽는다. ``pdf`` 가 상대 경로이면 ``data_root`` 기준이다.

        Raises:
            ValueError: 파일이 없거나 PDF가 아닌 경우, manifest와 다르거나 대상 문서가 아닌 경우.
        """
        path, relative_path = self._resolve(pdf)
        # 분기: manifest 없는 타사 PDF는 별도 검증 경로로 간다.
        if self.external_source is not None:
            return self._inspect_external(path, relative_path)
        rows = self._manifest_rows(relative_path)
        content = path.read_bytes()
        if not content.startswith(b"%PDF-"):
            raise ValueError(f"PDF 파일이 아닙니다: {relative_path}")
        # 파일 전체 SHA-256 = card_doc.doc_sha256. 같은 파일 재등록 방지(중복 판정)의 기준 값이다.
        file_sha256 = sha256_hex(content)
        row = rows[0]
        # 수집 당시 manifest에 기록한 해시·크기와 다르면 수집 후 바뀐 파일이므로 거부한다.
        if file_sha256 != row["SHA256"] or len(content) != int(row["파일크기(byte)"]):
            raise ValueError(f"manifest의 해시·크기와 다른 파일입니다: {relative_path}")

        match = FILE_CODE_PATTERN.search(path.name)
        if match is None:
            raise ValueError(f"파일명에서 디자인코드와 날짜를 찾지 못했습니다: {path.name}")
        design_cd, file_date = match.groups()
        names = list(dict.fromkeys(item["카드상품명"] for item in rows))
        common = "브랜드서비스안내" in row["문서종류"]
        note = self._source_note(row["문서구분"])
        if len(names) > 1:
            note += f" / 공유 상품: {', '.join(names)}"
        return ParsedDocument(
            doc_cd=f"HANA_{design_cd}_{file_date}",
            doc_family_cd=f"HANA_{design_cd}",
            doc_type_cd="BRAND_SERVICE" if common else "PRODUCT_GUIDE",
            doc_title=path.stem if common else f"{names[0]} 상품설명서",
            doc_source_url=row["PDF원본URL"],
            doc_file_nm=(Path(self.data_root.name) / relative_path).as_posix(),
            doc_file_size=len(content),
            doc_sha256=file_sha256,
            doc_review_no=None,
            doc_review_date=None,
            doc_collect_date=datetime.fromisoformat(row["수집일시"]).replace(tzinfo=KST),
            doc_note=note,
            pages=(),
            chunks=(),
        )

    def _inspect_external(self, path: Path, relative_path: Path) -> ParsedDocument:
        """Validate a separately identified source without inventing a design code or manifest row."""
        source = self.external_source
        content = path.read_bytes()
        if not content.startswith(b"%PDF-"):
            raise ValueError(f"PDF 파일이 아닙니다: {relative_path}")
        date_match = SIX_DIGIT_DATE_PATTERN.search(path.name)
        if date_match is None:
            raise ValueError(f"파일명 끝에서 YYMMDD 날짜를 찾지 못했습니다: {path.name}")
        file_date = date_match.group(1)
        # A checksum suffix makes the document code unique without pretending the source has a design code.
        digest = sha256_hex(content)
        try:
            import pymupdf
            with pymupdf.open(path) as pdf:
                page_count = len(pdf)
        except Exception as error:
            raise ValueError(f"PDF를 열 수 없습니다: {type(error).__name__}") from error
        if page_count < 1:
            raise ValueError("페이지가 없는 PDF입니다")
        collect_date = datetime.now(KST)
        return ParsedDocument(
            doc_cd=f"{source.doc_code_prefix}_{file_date}_{digest[:12]}",
            doc_family_cd=source.doc_family_cd,
            doc_type_cd=source.doc_type_cd,
            doc_title=source.doc_title,
            doc_source_url=source.doc_source_url,
            doc_file_nm=(Path(self.data_root.name) / relative_path).as_posix(),
            doc_file_size=len(content),
            doc_sha256=digest,
            doc_review_no=None,
            doc_review_date=None,
            doc_collect_date=collect_date,
            doc_note=(f"issuer={source.issuer_cd}; 로컬 수집 PDF. 원본 공식 URL은 별도 확인 필요; "
                      f"filename date={file_date}; declared pages={page_count}"),
            pages=(),
            chunks=(),
        )

    def read(self, pdf: str | Path) -> ParsedDocument:
        """PDF를 검증하고 페이지 원문과 청크까지 만든 ``ParsedDocument`` 를 반환한다. DB에 접근하지 않는다.

        처리 순서: inspect(메타데이터) → _read_pages(텍스트 추출·품질 차단) → 페이지 수 대조
        → 파일 해시 재확인 → _find_review(준법심의) → _split_pages(청크)

        Raises:
            ValueError: inspect 실패, 신뢰할 수 없는 페이지, 페이지 수 불일치, 파싱 중 파일 변경.
        """
        from dataclasses import replace
        identity = self.inspect(pdf)
        path, relative_path = self._resolve(pdf)
        pages = self._read_pages(path)
        if self.external_source is None:
            expected = int(self._manifest_rows(relative_path)[0]["페이지수"])
        else:
            import pymupdf
            with pymupdf.open(path) as pdf:
                expected = len(pdf)
        if len(pages) != expected:
            raise ValueError(f"문서 페이지 수({expected})와 다릅니다: {len(pages)}쪽")
        # 파싱 중 파일이 바뀌었다면 결과를 저장하지 않는다.
        if sha256_hex(path.read_bytes()) != identity.doc_sha256:
            raise ValueError("파싱 중 PDF 내용이 변경되었습니다")
        review_no, review_date = self._find_review(pages)
        # frozen dataclass라 값을 바꾸지 않고, inspect 결과에 페이지·청크를 채운 새 객체를 만든다.
        return replace(identity, doc_review_no=review_no, doc_review_date=review_date,
                       pages=pages, chunks=self._split_pages(pages))

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
        guides = [row for row in rows if row["문서구분"].startswith("공식 원본") and
                  ("상품설명서" in row["문서종류"] or "브랜드서비스안내" in row["문서종류"])]
        if not guides:
            raise ValueError(f"공식 상품설명서가 아닙니다: {relative_path}")
        return guides

    def _read_pages(self, path: Path) -> tuple[DocPage, ...]:
        """공통 Reader로 페이지별 원문을 읽는다. 정상 추출이 확인되지 않은 페이지가 있으면 거부한다."""
        reader = DocumentReader(path, ocr_engine=self.ocr_engine)
        reader.set_pdf_reader()
        if reader.reader.is_encrypted:
            raise ValueError(f"암호화된 PDF입니다: {path.name}")
        # set_pdf_doc_list: PyMuPDF(필요 시 pypdf·OCR 비교)로 페이지별 text와 page_quality_list(status 등)를 채운다.
        reader.set_pdf_doc_list()
        # 하나카드는 OCR 보정 전 품질로 바로 차단하고, 타사는 아래에서 문자 치환 후 품질을 다시 계산해 차단한다.
        blocked = [(row["page_no"], row["status"]) for row in reader.page_quality_list
                   if row["status"] in BLOCKING_PAGE_STATUS]
        if blocked and self.external_source is None:
            raise ValueError(f"원문 추출을 신뢰할 수 없는 페이지가 있습니다: {blocked}")
        pages = []
        for doc, quality in zip(reader.doc_list, reader.page_quality_list):
            # PostgreSQL text는 NUL을 저장할 수 없다. 같은 길이의 문자로 바꿔 위치를 유지한다.
            text = doc["text"].replace("\x00", "�")
            if self.external_source is not None:
                # Some Woori PDFs encode bullet/check icons as private-use font glyphs.
                # Map only those decorative glyphs to a same-width bullet; keep all text positions stable.
                text = "".join("•" if unicodedata.category(char) == "Co" else char for char in text)
                quality = {**quality, **measure_pdf_text(text, quality["has_visual"])}
            pages.append(DocPage(
                page_no=doc["page_no"],
                text=text,
                sha256=sha256_hex(text.encode("utf-8")),
                layer_cd=self._layer_cd(quality.get("source_text", text), quality["has_visual"]),
                extractor_nm=quality["extractor"],
                extractor_ver=quality["extractor_ver"],
                read_quality=quality,
            ))
        if self.external_source is not None:
            blocked = [(page.page_no, page.read_quality["status"]) for page in pages
                       if page.read_quality["status"] in BLOCKING_PAGE_STATUS]
            if blocked:
                raise ValueError(f"원문 추출을 신뢰할 수 없는 페이지가 있습니다: {blocked}")
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
        """페이지를 청크로 만든다. 내용이 없는 페이지는 건너뛰고, 순번은 문서 전체 기준이다.

        PAGE_V1은 페이지 전체 1건, BLOCK_V1은 ``block_chunking.split_blocks`` 의 의미 단위 청크다.
        """
        chunks: list[DocChunk] = []
        for page in pages:
            # OCR_REVIEW 페이지의 청크는 EXCLUDED로 만들어 LLM 입력에서 뺀다(사람 확인 후 approve_review_page로 RAW 전환).
            if page.text.strip():
                chunks.extend(page_chunks(page.page_no, page.text, len(chunks) + 1, self.split_rule,
                                          "EXCLUDED" if page.in_review else "RAW"))
        return tuple(chunks)


def page_chunks(page_no: int, text: str, first_seq: int, split_rule: str = SPLIT_RULE_VER,
                status: str = "RAW") -> list[DocChunk]:
    """페이지 1쪽의 청크. 위치는 페이지 원문 기준 1부터이고 청크를 이어 붙이면 원문과 같다."""
    if split_rule == SPLIT_RULE_VER:
        return [DocChunk(page_no, first_seq, 1, len(text), text, status)]
    if split_rule != SPLIT_RULE_BLOCK:
        raise ValueError(f"지원하지 않는 청크 분리 규칙입니다: {split_rule}")
    return [DocChunk(page_no, first_seq + index, block.start_pos, block.end_pos, block.text, status,
                     block.chunk_type_cd, SPLIT_RULE_BLOCK)
            for index, block in enumerate(split_blocks(page_no, text))]
