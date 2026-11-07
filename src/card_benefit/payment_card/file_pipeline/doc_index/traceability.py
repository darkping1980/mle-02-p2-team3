"""PDF의 페이지별 원문과 청크 위치 정보를 JSON으로 저장한다."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from common.document_reader import DocumentReader


def create_traceability(
    pdf_path: str | Path,
    expected_sha256: str | None = None,
    expected_page_count: int | None = None,
) -> dict:
    """PDF를 읽어 페이지와 청크 정보를 만든다.

    청크 위치는 페이지마다 1부터 시작하고 끝 글자도 포함한다.
    글자가 없는 페이지는 페이지 정보만 기록한다.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("입력 파일은 PDF여야 합니다.")

    pdf_bytes = pdf_path.read_bytes()
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("올바른 PDF 파일이 아닙니다.")

    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    if expected_sha256 and pdf_sha256 != expected_sha256:
        raise ValueError(f"SHA-256이 다릅니다: {pdf_sha256}")
    if expected_page_count is not None and expected_page_count < 1:
        raise ValueError("확인할 페이지 수는 1 이상이어야 합니다.")

    reader = DocumentReader(pdf_path)
    reader.set_pdf_reader()
    reader.set_pdf_doc_list()

    if not reader.doc_list:
        raise ValueError("PDF에서 페이지를 읽지 못했습니다.")
    if expected_page_count is not None and len(reader.doc_list) != expected_page_count:
        raise ValueError(f"페이지 수가 다릅니다: {len(reader.doc_list)}")
    if len(reader.doc_list) != len(reader.page_quality_list):
        raise ValueError("페이지 텍스트와 품질 정보의 개수가 다릅니다.")

    pages = []
    chunks = []

    for page_number, page in enumerate(reader.doc_list, start=1):
        quality = reader.page_quality_list[page_number - 1]
        text = page["text"]

        if page["page_no"] != page_number or quality["page_no"] != page_number:
            raise ValueError(f"페이지 번호가 순서와 다릅니다: {page_number}")
        if not isinstance(text, str):
            raise ValueError(f"{page_number}페이지 텍스트가 문자열이 아닙니다.")

        page_result = {
            "page_no": page_number,
            "text": text,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "quality": quality.copy(),
            "chunk_status": "NO_TEXT" if not text.strip() else "HAS_CHUNK",
            "excluded_reason": None,
        }

        if not text.strip():
            page_result["excluded_reason"] = (
                "추출된 글자가 없습니다. 빈 페이지인지 그림만 있는 페이지인지 눈으로 확인하세요."
            )
        else:
            chunks.append({
                "chunk_id": f"p{page_number:04d}",
                "page_no": page_number,
                "start_pos": 1,
                "end_pos": len(text),
                "text": text,
            })

        pages.append(page_result)

    return {
        "schema_version": "traceability-v1",
        "document": {
            "filename": pdf_path.name,
            "size_bytes": len(pdf_bytes),
            "sha256": pdf_sha256,
            "page_count": len(pages),
        },
        "pages": pages,
        "chunks": chunks,
    }


def write_traceability(data: dict, output_path: str | Path, overwrite: bool = False) -> Path:
    """페이지 원문이 들어 있는 JSON 파일을 저장한다."""
    output_path = Path(output_path)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"파일이 이미 있습니다. 다른 경로를 쓰세요: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="PDF 페이지와 청크 위치를 JSON으로 저장합니다.")
    parser.add_argument("--pdf", required=True, help="처리할 PDF 경로")
    parser.add_argument("--output", required=True, help="JSON 저장 경로")
    parser.add_argument("--expected-sha256", help="확인할 원본 SHA-256")
    parser.add_argument("--expected-page-count", type=int, help="확인할 페이지 수")
    parser.add_argument("--overwrite", action="store_true", help="기존 결과 파일 덮어쓰기")
    args = parser.parse_args()

    try:
        result = create_traceability(
            args.pdf,
            expected_sha256=args.expected_sha256,
            expected_page_count=args.expected_page_count,
        )
        output_path = write_traceability(result, args.output, args.overwrite)
    except (FileExistsError, FileNotFoundError, ModuleNotFoundError, OSError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1

    print(
        f"완료: {output_path} / 페이지 {len(result['pages'])}개 / "
        f"청크 {len(result['chunks'])}개 / SHA-256 {result['document']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
