"""Estimate table density from chunk text only; these are coarse signals, not PDF table detection."""
from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path
from typing import Any

from ..eval.eval_runs import load_run
from ..verify import _item_values, _numbers, _shared_keyword_flags
from ..eval.variance import GROUPS


def density_score(text: str) -> float:
    lines = [line for line in str(text).splitlines() if line.strip()]
    if not lines:
        return 0.0
    short = sum(len(line.strip()) <= 40 for line in lines) / len(lines)
    numeric = sum(bool(re.search(r"\d|%|원", line)) for line in lines) / len(lines)
    separated = sum(bool("\t" in line or re.search(r" {2,}", line)) for line in lines) / len(lines)
    lengths = [len(line.strip()) for line in lines]
    cv = statistics.pstdev(lengths) / max(1, statistics.mean(lengths))
    return round(short + numeric + separated + min(cv, 2) / 2, 8)


def classify_density(scores: list[float]) -> list[str]:
    n = len(scores)
    if not n:
        return []
    order = sorted(range(n), key=lambda i: (scores[i], i))
    labels = [""] * n
    for rank, index in enumerate(order):
        labels[index] = "low" if rank < (n + 2) // 3 else "middle" if rank < (2 * n + 2) // 3 else "high"
    return labels


def _chunk_index(directory: str | Path) -> dict[str, dict[str, Any]]:
    out = {}
    for path in Path(directory).glob("*.chunks.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        out.update({str(c["chunk_id"]): c for c in doc.get("chunks", []) if c.get("chunk_id") is not None})
    return out


def _has_verify_flags(row: dict[str, Any]) -> bool:
    extraction = row.get("extraction")
    if extraction is None:
        return False
    connected = {endpoint for relation in (extraction.get("relations") or []) for endpoint in (relation.get("source"), relation.get("target"))}
    for group in GROUPS[:-1]:
        for item in extraction.get(group, []) or []:
            if _shared_keyword_flags(group, item) or item.get("id") not in connected:
                return True
            quote_text = " ".join(e.get("text", "") for e in (item.get("evidence") or []))
            if any(value is not None and _numbers(value) and not _numbers(value).issubset(_numbers(quote_text)) for value in _item_values(group, item)):
                return True
    if any(e.get("location") is None for group in GROUPS for item in (extraction.get(group) or []) for e in (item.get("evidence") or [])):
        return True
    return False


def _run_report(rows: list[dict[str, Any]], ids_by_density: dict[str, set[str]]) -> dict[str, Any]:
    by_id = {str(r.get("chunk_id")): r for r in rows if r.get("chunk_id") is not None}
    result = {}
    for label, ids in ids_by_density.items():
        selected = [by_id[cid] for cid in ids if cid in by_id]
        n = len(selected)
        valid = [r for r in selected if r.get("extraction") is not None]
        evidence = [e for r in valid for g in GROUPS for item in ((r.get("extraction") or {}).get(g) or []) for e in (item.get("evidence") or [])]
        flagged = sum(_has_verify_flags(row) for row in selected)
        result[label] = {"chunks": n, "empty_rate": sum(r.get("extraction") is not None and not any((r.get("extraction") or {}).get(g) for g in GROUPS) for r in selected) / n if n else 0,
                         "ambiguous_quote_rate": sum(e.get("location") is None for e in evidence) / len(evidence) if evidence else 0,
                         "location_failure_rate": sum(f.get("code") == "quote_location_failure" for r in selected for f in (r.get("failures") or [])) / len(evidence) if evidence else 0,
                         "items_mean": sum(sum(len((r.get("extraction") or {}).get(g) or []) for g in GROUPS) for r in valid) / n if n else 0,
                         "verify_flag_rate": flagged / n if n else 0}
    return result


def build_report(chunk_dir: str | Path, runs: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    chunk_dir = Path(chunk_dir)
    chunks = _chunk_index(chunk_dir)
    result_ids = {str(row["chunk_id"]) for rows in runs.values() for row in rows if row.get("chunk_id") is not None}
    ids = sorted(result_ids & chunks.keys())
    labels = classify_density([density_score(chunks[cid].get("text", "")) for cid in ids])
    density_by_id = dict(zip(ids, labels))
    groups = {key: {cid for cid in ids if density_by_id[cid] == key} for key in ("low", "middle", "high")}
    report = {"chunks": [{"chunk_id": cid, "density": density_by_id[cid], "score": density_score(chunks[cid].get("text", ""))} for cid in ids], "runs": {}}
    for label, rows in runs.items():
        report["runs"][label] = _run_report(rows, groups)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--run", action="append", required=True, help="label=results_dir")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(); runs = {}
    for spec in args.run:
        label, sep, directory = spec.partition("=")
        if not sep or not label or not directory:
            parser.error("--run 형식은 label=results_dir 입니다")
        runs[label] = load_run(directory)
    report = build_report(args.chunk_dir, runs)
    path = Path(args.output).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[6]
    if path == repo_root or repo_root in path.parents:
        parser.error("출력 JSON은 저장소 밖이어야 합니다")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
