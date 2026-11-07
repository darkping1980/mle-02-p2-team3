"""Compare item/evidence COUNTS across prompt runs; counts do not measure correctness."""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

GROUPS = ("benefits", "conditions", "limits", "targets", "relations")
VERSIONS = ("out3", "out4", "out5a", "out5b", "out6")


def _counts(row: dict[str, Any]) -> dict[str, dict[str, int]]:
    extraction = row.get("extraction") or {}
    result = {}
    for group in GROUPS:
        items = extraction.get(group, []) or []
        result[group] = {"items": len(items), "evidence": sum(len(i.get("evidence", []) or []) for i in items)}
    return result


def compare_runs(runs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    chunks: dict[str, dict[str, dict[str, Any]]] = {}
    versions: dict[str, Any] = {}
    for version, rows in runs.items():
        by_chunk = {str(r["chunk_id"]): r for r in rows if r.get("chunk_id") is not None}
        chunks[version] = by_chunk
        valid = {cid: row for cid, row in by_chunk.items() if row.get("extraction") is not None}
        empty = sorted(cid for cid, row in valid.items()
                       if not any((row.get("extraction") or {}).get(g) for g in GROUPS))
        section_stats = {}
        per_chunk = {}
        for group in GROUPS:
            item_values = [len((row.get("extraction") or {}).get(group, []) or []) for row in valid.values()]
            evidence_values = [sum(len(i.get("evidence", []) or []) for i in
                                    ((row.get("extraction") or {}).get(group, []) or [])) for row in valid.values()]
            section_stats[group] = {
                "items_total": sum(item_values), "items_mean": round(statistics.mean(item_values), 3) if item_values else 0,
                "items_median": statistics.median(item_values) if item_values else 0,
                "evidence_total": sum(evidence_values), "evidence_mean": round(statistics.mean(evidence_values), 3) if evidence_values else 0,
                "evidence_median": statistics.median(evidence_values) if evidence_values else 0,
            }
        for cid, row in sorted(by_chunk.items()):
            per_chunk[cid] = _counts(row) if row.get("extraction") is not None else None
        versions[version] = {"extraction_chunks": len(valid), "empty_result_chunks": empty,
                             "sections": section_stats, "per_chunk": per_chunk}

    directions = {}
    ordered = [v for v in VERSIONS if v in chunks]
    for before, after in zip(ordered, ordered[1:]):
        by_group = {}
        common = set(chunks[before]) & set(chunks[after])
        for group in GROUPS:
            tally = Counter()
            for cid in common:
                left, right = chunks[before][cid].get("extraction"), chunks[after][cid].get("extraction")
                if left is None or right is None:
                    continue
                a = len(left.get(group, []) or [])
                b = len(right.get(group, []) or [])
                tally["increase" if b > a else "decrease" if b < a else "same"] += 1
            by_group[group] = {key: tally[key] for key in ("increase", "decrease", "same")}
        directions[f"{before}->{after}"] = by_group
    return {"counts_not_correctness": True, "versions": versions, "directions": directions}


def _load_run(directory: str | Path) -> list[dict[str, Any]]:
    path = Path(directory)
    rows = []
    for item_path in sorted(path.glob("*.result.json")):
        rows.append(json.loads(item_path.read_text(encoding="utf-8")))
    aggregate = path / "result.json"
    if not rows and aggregate.is_file():
        data = json.loads(aggregate.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        for key in ("results", "chunks", "items"):
            if isinstance(data.get(key), list):
                return data[key]
        raise ValueError(f"Unsupported aggregate format: {aggregate}")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in VERSIONS:
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--output", required=True, help="JSON path outside the repository")
    args = parser.parse_args()
    runs = {name: _load_run(getattr(args, name)) for name in VERSIONS}
    report = compare_runs(runs)
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
