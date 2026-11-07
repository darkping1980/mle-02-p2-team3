"""카드사 한 곳의 인덱스를 만든다.

예: PYTHONPATH=src:src/card_benefit uv run --locked --no-sync python -m payment_card.file_pipeline.doc_index.cli \
      --issuer woori --data-root src/data --output-dir src/card_benefit/data/index
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

from .adapters import ADAPTERS
from .core import build_index
from .measure import measure_pdf
from .schema import DOCUMENT_COLUMNS, PRODUCT_DOC_COLUMNS


def _write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def load_overrides(path: Path) -> dict:
    """사람이 확인한 카드 구분 파일(상품명, card_type, reason)을 읽는다. 파일이 없으면 빈 값이다."""
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as file:
        return {row["product_name"]: row["card_type"] for row in csv.DictReader(file)}


def load_review_decisions(path: Path) -> dict:
    """확인 결과 파일(doc_id, name_ok, content_image, …)을 읽는다. 파일이 없으면 빈 값이다."""
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as file:
        return {
            row["doc_id"]: {"name_ok": row["name_ok"] == "Y", "content_image": row["content_image"] == "Y"}
            for row in csv.DictReader(file)
        }


def run(issuer: str, data_root: Path, output_dir: Path, overwrite: bool = False) -> dict:
    issuer_root = data_root / f"{issuer}_all"
    entries, extra = ADAPTERS[issuer].load_entries(issuer_root)
    overrides = load_overrides(output_dir / issuer / "card_type_overrides.csv")
    decisions = load_review_decisions(output_dir / issuer / "review_decisions.csv")
    documents, product_docs, summary = build_index(
        issuer, issuer_root, entries, measure_pdf, overrides, decisions
    )
    summary.update(extra)

    out = output_dir / issuer
    targets = [out / "documents.csv", out / "product_docs.csv", out / "summary.json"]
    if not overwrite and any(t.exists() for t in targets):
        raise FileExistsError(f"이미 결과가 있습니다. 덮어쓰려면 --overwrite를 쓰세요: {out}")
    out.mkdir(parents=True, exist_ok=True)
    _write_csv(targets[0], DOCUMENT_COLUMNS, documents)
    _write_csv(targets[1], PRODUCT_DOC_COLUMNS, product_docs)
    targets[2].write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer", required=True, choices=sorted(ADAPTERS))
    parser.add_argument("--data-root", type=Path, default=Path("src/data"))
    parser.add_argument("--output-dir", type=Path, default=Path("src/card_benefit/data/index"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        summary = run(args.issuer, args.data_root, args.output_dir, args.overwrite)
    except (OSError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    shown = dict(summary)
    shown["skipped_rows"] = len(summary["skipped_rows"])  # 목록 전체는 summary.json에 있으므로 건수만 보여 준다
    print(json.dumps(shown, ensure_ascii=False, indent=2))
    return 0 if not summary["missing_files"] and not summary["bad_canonical_groups"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
