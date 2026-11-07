"""인덱스의 대표 문서를 traceability JSON으로 일괄 변환한다.

JSON에는 페이지 전체 원문이 들어간다. 저장 폴더는 반드시 직접 지정하고, 커밋 전에 내용을 확인한다.
예: PYTHONPATH=src:src/card_benefit uv run --locked --no-sync python -m payment_card.file_pipeline.doc_index.batch \
      --issuer woori --output-dir /tmp/trace
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

from .traceability import create_traceability, write_traceability

# 이 역할의 대표 문서만 처리한다. 약관·미분류는 대상이 아니다.
TARGET_ROLES = {"product_guide", "web_capture", "brand_service"}
# 이번 범위는 신용카드와 공통 문서다. 사람이 체크카드로 확인한 문서는 제외한다.
TARGET_CARD_TYPES = {"credit", "common"}


def select_documents(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """처리할 문서와 건너뛸 문서(사유 포함)를 나눈다."""
    targets, skipped = [], []
    for row in rows:
        if row["canonical"] != "Y" or row["doc_role"] not in TARGET_ROLES or row["card_type"] not in TARGET_CARD_TYPES:
            continue
        if row["ocr_needed"] == "Y":
            skipped.append({"file_path": row["file_path"], "reason": "OCR 필요(이미지 PDF)"})
        else:
            targets.append(row)
    return targets, skipped


def run_batch(
    issuer: str,
    data_root: Path,
    index_dir: Path,
    output_dir: Path,
    overwrite: bool = False,
    convert=create_traceability,
) -> dict:
    with (index_dir / issuer / "documents.csv").open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    targets, skipped = select_documents(rows)

    done, failed = [], []
    for row in targets:
        output = output_dir / issuer / f'{row["doc_id"]}.json'
        try:
            result = convert(
                data_root / row["file_path"],
                expected_sha256=row["sha256"],
                expected_page_count=int(row["pages"]) if row["pages"] else None,
            )
            write_traceability(result, output, overwrite)
            done.append({"file_path": row["file_path"], "chunks": len(result["chunks"])})
        except (FileExistsError, FileNotFoundError, ModuleNotFoundError, OSError, ValueError) as error:
            failed.append({"file_path": row["file_path"], "error": str(error)})
    return {"done": done, "skipped": skipped, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", required=True, choices=["hana", "woori"])
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--data-root", type=Path, default=Path("src/data"))
    parser.add_argument("--index-dir", type=Path, default=Path("src/card_benefit/data/index"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    summary = run_batch(args.issuer, args.data_root, args.index_dir, args.output_dir, args.overwrite)
    report = {k: len(v) for k, v in summary.items()}
    print(json.dumps(report, ensure_ascii=False))
    report_path = args.output_dir / args.issuer / "batch_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
