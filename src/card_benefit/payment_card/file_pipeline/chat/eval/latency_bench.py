"""DB-only latency comparison for fp_chat candidate lookup and graph exploration."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import time

try:
    from ..answer.answer_eval import safe_tmp
except ImportError:  # Script-style imports from this directory.
    from answer.answer_eval import safe_tmp


def _records(path: Path, limit: int) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            question = row.get("question", {})
            if isinstance(question, str):
                question = {"question": question}
            rows.append({"question": str(question.get("question", "")),
                         "selected_seed_names": list(row.get("selected_seed_names", []))})
    return rows[:max(0, limit)]


def _stats(samples: list[float]) -> dict:
    ordered = sorted(samples)
    if not ordered:
        return {"n": 0, "median_ms": None, "p95_ms": None, "max_ms": None}
    p95_index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * .95 + .999999)))
    return {"n": len(ordered), "median_ms": round(statistics.median(ordered), 3),
            "p95_ms": round(ordered[p95_index], 3), "max_ms": round(ordered[-1], 3)}


def _measure(fn):
    started = time.perf_counter()
    fn()
    return (time.perf_counter() - started) * 1000


def _run_mode(records: list[dict], repeat: int, mode: str) -> dict:
    if not os.environ.get("DB_URL"):
        raise RuntimeError("DB_URL 환경 변수가 필요합니다.")
    from fp_chat_patch import apply, restore  # noqa: PLC0415

    rag = apply("fp_chat")
    if mode == "nopool":
        # Keep fp_chat's rag/list-entity overrides, but restore only its DB function.
        restore()
    candidate, explore = [], []
    for repeat_index in range(repeat):
        for row in records:
            candidate.append(_measure(lambda: rag.list_entities(row["question"])))
            analysis = rag.Analysis(entities=row["selected_seed_names"], hops=1, intent="latency bench")
            explore.append(_measure(lambda: rag.explore(analysis)))
    restore()
    candidate_warmup = candidate.pop(0) if candidate else None
    explore_warmup = explore.pop(0) if explore else None
    return {"candidate_lookup": {**_stats(candidate), "warmup_ms": round(candidate_warmup, 3) if candidate_warmup is not None else None},
            "explore": {**_stats(explore), "warmup_ms": round(explore_warmup, 3) if explore_warmup is not None else None}}


def _ratio(pool, nopool):
    a, b = pool["median_ms"], nopool["median_ms"]
    return round(a / b, 3) if a is not None and b not in (None, 0) else None


def main(argv=None):
    parser = argparse.ArgumentParser(description="DB-only fp_chat pool latency comparison (no LLM)")
    parser.add_argument("--input", default="/tmp/fp-answer-golden-dev-r1.jsonl")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--mode", choices=("pool", "nopool", "both"), default="both")
    parser.add_argument("--output-dir", default="/tmp/fp-latency-bench")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        raise ValueError("--repeat은 1 이상이어야 합니다.")
    source = Path(args.input).expanduser().resolve()
    records = _records(source, args.limit)
    modes = ("pool", "nopool") if args.mode == "both" else (args.mode,)
    plan = {"mode": "dry-run", "question_count": len(records), "repeat": args.repeat,
            "modes": list(modes), "segment_calls": len(records) * args.repeat * len(modes) * 2,
            "db_call_upper_bound": len(records) * args.repeat * len(modes) * 5}
    if not args.execute:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
        return 0
    out_dir = safe_tmp(Path(args.output_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    result = {"input": str(source), "question_count": len(records), "repeat": args.repeat,
              "question_prefixes": [row["question"][:20] for row in records], "modes": {}}
    for mode in modes:
        result["modes"][mode] = _run_mode(records, args.repeat, mode)
    if "pool" in result["modes"] and "nopool" in result["modes"]:
        for segment in ("candidate_lookup", "explore"):
            result["modes"]["pool"][segment]["pool_nopool_median_ratio"] = _ratio(
                result["modes"]["pool"][segment], result["modes"]["nopool"][segment])
    (out_dir / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for mode in modes:
        for segment in ("candidate_lookup", "explore"):
            row = result["modes"][mode][segment]
            print(f"{mode:6} {segment:16} n={row['n']} median={row['median_ms']} p95={row['p95_ms']} max={row['max_ms']} ratio={row.get('pool_nopool_median_ratio')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
