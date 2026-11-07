"""인덱스의 대표 문서를 청크 JSON으로 만든다. 입력은 batch가 만든 traceability JSON이다.

JSON에는 쪽 원문이 들어간다. 출력 폴더는 직접 지정하고, 커밋 전에 내용을 확인한다.
예: PYTHONPATH=src:src/card_benefit uv run --locked --no-sync python -m payment_card.file_pipeline.chunking.cli \
      --issuer woori --trace-dir <batch 출력 폴더> --output-dir <저장 폴더>
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

from ..doc_index.batch import select_documents
from .build import build_doc_chunks
from .headings import find_heading_offsets


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def products_of(links: list[dict], doc_id: str) -> list[dict]:
    """같은 내용(doc_id)을 쓰는 상품 목록. 이름과 번호가 같은 것은 한 번만 넣는다."""
    seen, products = set(), []
    for link in links:
        if link["doc_id"] != doc_id:
            continue
        key = (link["product_name"], link["product_ids"])
        if key not in seen:
            seen.add(key)
            products.append({"product_name": link["product_name"], "product_ids": json.loads(link["product_ids"])})
    return products


def run(
    issuer: str,
    data_root: Path,
    index_dir: Path,
    trace_dir: Path,
    output_dir: Path,
    overwrite: bool,
    include_ocr: bool = False,
) -> dict:
    import pymupdf

    rows = read_csv(index_dir / issuer / "documents.csv")
    links = read_csv(index_dir / issuer / "product_docs.csv")
    targets, skipped = select_documents(rows)
    included_ocr = 0
    if include_ocr:
        skipped_paths = {item["file_path"] for item in skipped}
        ocr_targets = [row for row in rows if row["file_path"] in skipped_paths]
        targets.extend(ocr_targets)
        included_ocr = len(ocr_targets)
        skipped = []
    done, failed = [], []
    for row in targets:
        output = output_dir / issuer / f'{row["doc_id"]}.chunks.json'
        try:
            if output.exists() and not overwrite:
                raise FileExistsError(f"파일이 이미 있습니다: {output.name}")
            trace = json.loads((trace_dir / issuer / f'{row["doc_id"]}.json').read_text(encoding="utf-8"))
            with pymupdf.open(data_root / row["file_path"]) as pdf:
                finder = lambda page_no, text: find_heading_offsets(pdf[page_no - 1], text)
                result = build_doc_chunks(row, trace, products_of(links, row["doc_id"]), finder)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            done.append({"file_path": row["file_path"], "chunks": len(result["chunks"]),
                         "sizes": [len(c["text"]) for c in result["chunks"]]})
        except (FileExistsError, FileNotFoundError, ValueError, OSError) as error:
            failed.append({"file_path": row["file_path"], "error": str(error)})
    return {"done": done, "skipped": skipped, "failed": failed, "included_ocr": included_ocr}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", required=True, choices=["hana", "woori"])
    parser.add_argument("--trace-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("src/data"))
    parser.add_argument("--index-dir", type=Path, default=Path("src/card_benefit/data/index"))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--include-ocr", action="store_true", help="OCR 필요 문서도 traceability JSON으로 청킹")
    args = parser.parse_args()

    summary = run(
        args.issuer, args.data_root, args.index_dir, args.trace_dir, args.output_dir,
        args.overwrite, include_ocr=args.include_ocr,
    )
    sizes = [n for d in summary["done"] for n in d["sizes"]]
    print(json.dumps({
        "docs": len(summary["done"]), "chunks": len(sizes),
        "over_4000": sum(n > 4000 for n in sizes), "under_200": sum(n < 200 for n in sizes),
        "skipped_ocr": len(summary["skipped"]), "failed": len(summary["failed"]),
        "included_ocr": summary["included_ocr"],
    }, ensure_ascii=False))
    for item in summary["failed"][:5]:
        print("실패:", item["file_path"], item["error"], file=sys.stderr)
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
