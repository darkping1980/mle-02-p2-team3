"""PDF 한 개의 해시, 쪽수, 추출 글자 수를 잰다."""

from __future__ import annotations

import hashlib
from pathlib import Path


def measure_pdf(path: Path) -> dict:
    """파일이 없으면 exists=False만 돌려준다. 열 수 없는 PDF는 error에 사유를 적는다."""
    if not path.is_file():
        return {"exists": False}
    data = path.read_bytes()
    result = {"exists": True, "sha256": hashlib.sha256(data).hexdigest(), "pages": None, "text_chars": None}
    if not data.startswith(b"%PDF-"):
        result["error"] = "PDF 서명 없음"
        return result
    try:
        import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as doc:
            result["pages"] = doc.page_count
            result["text_chars"] = sum(len(page.get_text().strip()) for page in doc)
    except Exception as error:  # 손상 PDF도 인덱스에는 남기고 검토 대상으로 둔다
        result["error"] = f"PDF 열기 실패: {error}"
    return result
