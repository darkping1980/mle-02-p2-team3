"""Summarize ambiguous evidence without writing quote or chunk text."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from ..evidence import locate_quote

SECTIONS = ("benefits", "conditions", "limits", "targets", "relations")
LENGTH_BUCKETS = (("<=10", 0, 10), ("11-20", 11, 20), ("21-40", 21, 40), (">=41", 41, None))


def ambiguity_report(result_dir: Path | str, chunk_dir: Path | str, output_dir: Path | str) -> dict:
    """Write quote-free rows and return counts for ambiguous evidence."""
    chunks = {}
    for path in sorted(Path(chunk_dir).expanduser().glob("*.chunks.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for chunk in data.get("chunks", []):
            chunks[chunk.get("chunk_id")] = chunk

    rows = []
    for path in sorted(Path(result_dir).expanduser().glob("*.result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        chunk_id = result.get("chunk_id")
        chunk = chunks.get(chunk_id)
        if not isinstance(chunk, dict) or not isinstance(chunk.get("text"), str):
            continue
        ambiguous_paths = {
            failure.get("path") for failure in result.get("failures", [])
            if failure.get("code") == "quote_location_ambiguous"
        }
        if not ambiguous_paths:
            continue
        items = []
        all_item_quotes = []
        for section in SECTIONS:
            for index, item in enumerate((result.get("extraction") or {}).get(section, [])):
                item_path = f"{section}[{index}]"
                for quote_index, evidence in enumerate(item.get("evidence", [])):
                    evidence_path = f"{item_path}.evidence[{quote_index}]"
                    if isinstance(evidence.get("text"), str):
                        all_item_quotes.append((item_path, evidence["text"]))
                    if evidence_path in ambiguous_paths and isinstance(evidence.get("text"), str):
                        items.append((section, item_path, evidence_path, evidence["text"]))
        for section, item_path, evidence_path, quote in items:
            located = locate_quote(chunk["text"], chunk.get("start_pos", 1), quote)
            if located is None:
                continue
            reused = any(other_item != item_path and other_quote == quote
                         for other_item, other_quote in all_item_quotes)
            rows.append({"chunk_id": chunk_id, "item_path": evidence_path,
                         "length": len(quote), "occurrence_count": located.occurrences,
                         "section": section, "reused_by_other_item": reused})

    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "ambiguity_report.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    section_counts = Counter(row["section"] for row in rows)
    length_counts = Counter()
    occurrence_counts = Counter(row["occurrence_count"] for row in rows)
    for row in rows:
        for label, low, high in LENGTH_BUCKETS:
            if row["length"] >= low and (high is None or row["length"] <= high):
                length_counts[label] += 1
                break
    return {"count": len(rows), "by_section": {key: section_counts[key] for key in SECTIONS},
            "by_length_bucket": {label: length_counts[label] for label, _, _ in LENGTH_BUCKETS},
            "by_occurrence_count": dict(sorted(occurrence_counts.items())),
            "output": str(output / "ambiguity_report.json")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--chunk-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(ambiguity_report(args.result_dir, args.chunk_dir, args.output_dir), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
