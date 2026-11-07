"""Summarize numeric run metrics; counts and rates do not measure extraction correctness."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from .variance import GROUPS

ENTITY_GROUPS = GROUPS[:-1]
_REPO_ROOT = Path(__file__).resolve().parents[6]


def load_run(directory: str | Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(directory).expanduser().glob("*.result.json"))]


def summarize_group(values: list[float | int]) -> dict[str, float | int | None]:
    if not values:
        return {"mean": 0, "stdev": None, "min": 0, "max": 0}
    return {"mean": round(statistics.mean(values), 4),
            "stdev": round(statistics.stdev(values), 4) if len(values) >= 2 else None,
            "min": min(values), "max": max(values)}


def within_range(value: float, values: list[float | int]) -> bool | None:
    return None if not values else min(values) <= value <= max(values)


def run_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    n = len(rows)
    successes = [r for r in rows if r.get("extraction") is not None]
    empty = [r for r in successes if not any((r.get("extraction") or {}).get(g) for g in GROUPS)]
    failed = [r for r in rows if r.get("extraction") is None]
    schema = sum(any(str(f.get("code", "")).startswith(("schema", "validation")) for f in (r.get("failures") or [])) for r in rows)
    loc_fail = sum(f.get("code") == "quote_location_failure" for r in rows for f in (r.get("failures") or []))
    evidences = [e for r in successes for g in GROUPS for item in ((r.get("extraction") or {}).get(g) or []) for e in (item.get("evidence") or [])]
    ambiguous = sum(e.get("location") is None for e in evidences)
    nonempty = [r for r in successes if r not in empty]
    out = {"chunks": n, "success_chunks": len(nonempty), "failure_chunks": len(failed),
           "empty_chunks": len(empty),
           "empty_rate": len(empty) / n if n else 0, "schema_violation_rate": schema / n if n else 0,
           "location_failure_rate": loc_fail / max(1, len(evidences)),
           "ambiguity_rate": ambiguous / max(1, len(evidences)),
           "evidence_mean": len(evidences) / n if n else 0}
    for group in GROUPS:
        out[f"{group}_mean"] = sum(len((r.get("extraction") or {}).get(group, []) or []) for r in successes) / n if n else 0
    return out


def compare_groups(groups: dict[str, list[list[dict[str, Any]]]]) -> dict[str, Any]:
    report = {}
    for label, runs in groups.items():
        metrics = [run_metrics(rows) for rows in runs]
        keys = sorted(set().union(*(m.keys() for m in metrics))) if metrics else []
        report[label] = {"runs": len(runs), "metrics": {key: summarize_group([m[key] for m in metrics]) for key in keys}}
    variation = {}
    for label, runs in groups.items():
        if len(runs) != 1:
            continue
        candidate = run_metrics(runs[0])
        variation[label] = {}
        for baseline_label, baseline_runs in groups.items():
            if baseline_label == label or len(baseline_runs) < 2:
                continue
            baselines = [run_metrics(rows) for rows in baseline_runs]
            keys = sorted(set(candidate) & set.intersection(*(set(m) for m in baselines)))
            variation[label][baseline_label] = {
                key: {"value": round(candidate[key], 4),
                      "within_repeated_run_range": within_range(candidate[key], [m[key] for m in baselines])}
                for key in keys
            }
    return {"groups": report, "single_run_comparison": variation}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--group", action="append", required=True, help="label=dirA,dirB")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(); groups = {}
    for spec in args.group:
        label, sep, dirs = spec.partition("=")
        if not sep or not label or not dirs:
            parser.error("--group 형식은 label=dirA,dirB 입니다")
        groups[label] = [load_run(p) for p in dirs.split(",")]
    report = compare_groups(groups)
    path = Path(args.output).expanduser().resolve()
    if path == _REPO_ROOT or _REPO_ROOT in path.parents:
        parser.error("출력 JSON은 저장소 밖이어야 합니다")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
