"""Aggregate human review marks from a review_sheet.py Markdown file.

Accuracy is the match ratio among checked items: match / all single-mark checked
items. Unchecked items are excluded from that denominator and reported separately.
Rows with multiple marks are ambiguous and excluded from both checked counts and
the accuracy denominator.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

GROUPS = ("benefits", "conditions", "limits", "targets", "relations")
LABELS = ("match", "value_error", "missing", "hallucination")
MARK = re.compile(r"\[(x| )\]\s*(원문과 일치|값 오류|누락 있음|환각)")
LABEL_MAP = dict(zip(("원문과 일치", "값 오류", "누락 있음", "환각"), LABELS))


def _new_counts() -> Counter:
    return Counter({name: 0 for name in (*LABELS, "unchecked", "ambiguous")})


def _summary(counts: Counter) -> dict:
    checked = sum(counts[label] for label in LABELS)
    return {
        **{label: counts[label] for label in (*LABELS, "unchecked", "ambiguous")},
        "checked": checked,
        "accuracy": counts["match"] / checked if checked else None,
        "ratios_among_checked": {
            label: counts[label] / checked if checked else None for label in LABELS
        },
    }


def tally(sheet: str | Path) -> dict:
    """Return mark counts and checked-item ratios grouped by chunk and section."""
    section = None
    chunk = None
    chunks: dict[str, dict[str, Counter]] = {}
    totals = {name: _new_counts() for name in GROUPS}
    for line in Path(sheet).read_text(encoding="utf-8").splitlines():
        if line.startswith("## 청크 "):
            chunk = line.removeprefix("## 청크 ").strip()
            chunks.setdefault(chunk, {name: _new_counts() for name in GROUPS})
            section = None
            continue
        if line.startswith("### "):
            candidate = line.removeprefix("### ").strip()
            section = candidate if candidate in GROUPS else None
            continue
        marks = MARK.findall(line)
        if not marks or section not in GROUPS or chunk is None:
            continue
        selected = [LABEL_MAP[label] for mark, label in marks if mark == "x"]
        if len(selected) > 1:
            label = "ambiguous"
        elif len(selected) == 1:
            label = selected[0]
        else:
            label = "unchecked"
        chunks[chunk][section][label] += 1
        totals[section][label] += 1
    return {
        "accuracy_definition": "match / singly checked items; unchecked excluded; ambiguous excluded",
        "chunks": {
            chunk_id: {name: _summary(counts[name]) for name in GROUPS}
            for chunk_id, counts in chunks.items()
        },
        "sections": {name: _summary(totals[name]) for name in GROUPS},
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="사람 검토표의 표시 수만 집계")
    parser.add_argument("--sheet", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    result = tally(args.sheet)
    (output_dir / "review_tally.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    checked = sum(item["checked"] for item in result["sections"].values())
    unchecked = sum(item["unchecked"] for item in result["sections"].values())
    ambiguous = sum(item["ambiguous"] for item in result["sections"].values())
    matches = sum(item["match"] for item in result["sections"].values())
    print(json.dumps({"chunks": len(result["chunks"]), "checked": checked,
                      "matches": matches, "unchecked": unchecked,
                      "ambiguous": ambiguous,
                      "accuracy": matches / checked if checked else None}, sort_keys=True))


if __name__ == "__main__":
    main()
