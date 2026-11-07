"""Aggregate a saved extraction run without writing source or quote text."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import tempfile

from .ambiguity_report import ambiguity_report
from ..diagnose import diagnose_empty_results
from ..review.empty_review import _empty
from ..eval.eval_runs import load_run
from .table_density_report import build_report as build_density_report
from ..verify import verify_results

GROUPS = ("benefits", "conditions", "limits", "targets", "relations")
ENTITY_GROUPS = GROUPS[:-1]
LENGTH_BUCKETS = (("<=499", 0, 499), ("500-999", 500, 999), ("1000-1999", 1000, 1999),
                  ("2000-3999", 2000, 3999), (">=4000", 4000, None))
_REPO_ROOT = Path(__file__).resolve().parents[6]


def _load_chunks(directory: Path) -> dict[str, dict]:
    chunks = {}
    for path in sorted(directory.expanduser().glob("*.chunks.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        for chunk in document.get("chunks", []):
            if isinstance(chunk, dict) and chunk.get("chunk_id") is not None:
                chunks[str(chunk["chunk_id"])] = chunk
    return chunks


def _schema_path(failure: dict) -> str | None:
    path = failure.get("path")
    if isinstance(path, (str, list, tuple)):
        return str(path)
    message = failure.get("message")
    if isinstance(message, str):
        match = re.search(r"\n([a-z_]+(?:\.\d+)?(?:\.[a-z_]+)*)\n", message)
        if match:
            parts = match.group(1).split(".")
            if len(parts) > 1 and parts[1].isdigit():
                return f"{parts[0]}[{parts[1]}]" + ("." + ".".join(parts[2:]) if len(parts) > 2 else "")
            return ".".join(parts)
    return None


def _enum_values(failure: dict) -> list[str]:
    """Return only recognized schema enum literals, never arbitrary error text."""
    message = failure.get("message")
    if not isinstance(message, str):
        return []
    expected = re.search(r"Input should be (.+)", message)
    if not expected:
        return []
    known = {"DISCOUNT", "CASHBACK", "POINT", "SPEND_REQ", "EXCLUDE", "USAGE", "PAYMENT",
             "MERCHANT", "OTHER", "TXN", "DAY", "MONTH", "YEAR", "UNKNOWN", "INDUSTRY",
             "CHANNEL", "SERVICE", "HAS_CONDITION", "HAS_LIMIT", "APPLIES_TO", "EXCLUDES",
             "MUTUALLY_EXCLUSIVE"}
    return sorted(set(re.findall(r"'([A-Z_]+)'", expected.group(1))) & known)


def build_report(result_dir: str | Path, chunk_dir: str | Path, output_dir: str | Path | None = None) -> dict:
    """Build and optionally save source-free summary metrics for one run."""
    results_path, chunks_path = Path(result_dir).expanduser(), Path(chunk_dir).expanduser()
    rows = load_run(results_path)
    chunks = _load_chunks(chunks_path)
    by_id = {str(row.get("chunk_id")): row for row in rows if row.get("chunk_id") is not None}
    failures_by_code = Counter()
    schema_paths, enum_names = Counter(), Counter()
    location = Counter({"success": 0, "failure": 0, "ambiguous": 0})
    group_items, group_evidence = Counter(), Counter()
    success = failed = empty = partial = 0
    for row in rows:
        extraction = row.get("extraction")
        row_failures = row.get("failures") or []
        for failure in row_failures:
            code = str(failure.get("code", "unknown"))
            failures_by_code[code] += 1
            if code.startswith(("schema", "validation")):
                path = _schema_path(failure)
                if path:
                    schema_paths[path] += 1
                enum = failure.get("enum") or failure.get("enum_name")
                if isinstance(enum, str):
                    enum_names[enum] += 1
                else:
                    enum_names.update(_enum_values(failure))
            if code == "quote_location_failure":
                location["failure"] += 1
        if extraction is None:
            failed += 1
            continue
        success += 1
        is_empty = _empty(row)
        empty += is_empty
        partial += bool(not is_empty and row_failures)
        for group in GROUPS:
            items = extraction.get(group) or []
            group_items[group] += len(items)
            group_evidence[group] += sum(len(item.get("evidence") or []) for item in items)
            for item in items:
                for evidence in item.get("evidence") or []:
                    if evidence.get("location") is None:
                        location["ambiguous"] += 1
                    else:
                        location["success"] += 1

    lengths = {cid: len(str(chunk.get("text", ""))) for cid, chunk in chunks.items()}
    long_ids = sorted(cid for cid, length in lengths.items() if length > 4000 and cid in by_id)
    empty_ids = sorted(cid for cid, row in by_id.items() if _empty(row))
    length_buckets = {}
    for label, low, high in LENGTH_BUCKETS:
        ids = [cid for cid, row in by_id.items() if low <= lengths.get(cid, -1) and (high is None or lengths.get(cid, -1) <= high)]
        empty_count = sum(_empty(by_id[cid]) for cid in ids)
        length_buckets[label] = {"chunks": len(ids), "empty_chunks": empty_count,
                                 "empty_rate": empty_count / len(ids) if ids else 0}

    # Reuse existing report functions in a disposable directory. Their intermediate files
    # contain metadata only and are removed after the aggregate has been computed.
    with tempfile.TemporaryDirectory(prefix="full-run-report-") as temporary:
        temp = Path(temporary)
        verify_results(results_path, chunks_path, temp / "verify")
        diagnosis = diagnose_empty_results(results_path, chunks_path, temp / "diagnose")
        ambiguity = ambiguity_report(results_path, chunks_path, temp / "ambiguity")
        density = build_density_report(chunks_path, {"run": rows})
        density_labels = {row["chunk_id"]: row["density"] for row in density["chunks"]}
        empty_high_density = sorted(cid for cid in empty_ids if density_labels.get(cid) == "high")
        schema_violation_count = sum(count for code, count in failures_by_code.items()
                                     if code.startswith(("schema", "validation")))

    total = len(rows)
    report = {
        "chunks": total, "success_chunks": success, "failure_chunks": failed,
        "empty_chunks": empty, "partial_chunks": partial,
        "failures_by_code": dict(sorted(failures_by_code.items())),
        "location_evidence": dict(location),
        "schema_violations": {"count": schema_violation_count, "by_path": dict(sorted(schema_paths.items())),
                              "enum_names": dict(sorted(enum_names.items()))},
        "groups": {group: {"items": group_items[group], "evidence": group_evidence[group],
                           "items_per_chunk": group_items[group] / total if total else 0,
                           "evidence_per_chunk": group_evidence[group] / total if total else 0}
                   for group in GROUPS},
        "long_chunks": {"count": len(long_ids), "chunk_ids": long_ids},
        "empty_high_density_chunk_ids": empty_high_density,
        "length_buckets": length_buckets,
        "ambiguity_evidence_count": ambiguity["count"],
        "diagnosed_empty_count": diagnosis["count"],
    }
    if output_dir is not None:
        destination = Path(output_dir).expanduser().resolve()
        if destination == _REPO_ROOT or _REPO_ROOT in destination.parents:
            raise ValueError("집계 JSON은 저장소 밖에 지정해야 합니다.")
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "full_run_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--chunk-dir", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    destination = args.output_json.expanduser().resolve()
    if destination == _REPO_ROOT or _REPO_ROOT in destination.parents:
        parser.error("집계 JSON은 저장소 밖에 지정해야 합니다.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(args.result_dir, args.chunk_dir)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
