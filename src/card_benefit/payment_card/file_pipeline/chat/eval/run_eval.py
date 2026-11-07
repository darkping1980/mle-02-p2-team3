"""Command line entry point for answer and retrieval evaluations."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[6]
CHATBOT_DIR = HERE.parents[4] / "graphrag_chatbot"
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))


def metrics(records):
    search_total = search_hit = answer_total = answer_hit = source_hit = 0
    durations = []
    for rec in records:
        result = rec["result"]
        expected = rec["question"].get("expected", [])
        expected_names = rec["question"].get("expected_node_names", [])
        node_names = {n.get("name", "") for n in result.get("subgraph", {}).get("nodes", [])}
        if expected_names:
            search_total += len(expected_names)
            search_hit += sum(name in node_names for name in expected_names)
        answer = result.get("answer", "")
        answer_total += len(expected)
        answer_hit += sum(str(value) in answer for value in expected)
        source_hit += bool(result.get("sources"))
        durations.append(rec.get("elapsed_seconds", 0.0))
    count = len(records)
    return {"retrieval_hit_rate": search_hit / search_total if search_total else 0.0,
            "retrieval_hits": search_hit, "retrieval_expected": search_total,
            "answer_inclusion_rate": answer_hit / answer_total if answer_total else 0.0,
            "answer_included": answer_hit, "answer_expected": answer_total,
            "source_rate": source_hit / count if count else 0.0,
            "average_seconds": sum(durations) / len(durations) if durations else 0.0,
            "questions": count}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("questions", help="/tmp 아래 eval_questions JSON")
    parser.add_argument("--mode", choices=("answer", "retrieval"), default="answer")
    parser.add_argument("--llm", choices=("openai",), default="openai")
    parser.add_argument("--source", choices=("csv", "db"), default="csv")
    parser.add_argument("--seed-mode", choices=("contains", "fuzzy", "oracle"), default="contains")
    parser.add_argument("--seed-threshold", type=float, default=0.15)
    parser.add_argument("--hops", type=int, choices=(1, 2, 3))
    parser.add_argument("--csv-dir", action="append", default=[])
    parser.add_argument("--summary")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--output")
    parser.add_argument("--max-cost-usd", type=float, default=0.10)
    parser.add_argument("--sleep", type=float, default=0.3)
    args = parser.parse_args(argv)
    if args.hops is None:
        args.hops = 2 if args.mode == "retrieval" else 1
    if args.summary is None:
        args.summary = "/tmp/fp-retrieval-summary.json" if args.mode == "retrieval" else "/tmp/fp-answer-summary.json"
    if args.output is None:
        args.output = "/tmp/fp-chat-eval.jsonl" if args.mode == "answer" else "/tmp/fp-retrieval.jsonl"
    qpath = Path(args.questions).expanduser().resolve()
    if Path("/tmp").resolve() not in qpath.parents or REPO_ROOT in qpath.parents:
        raise ValueError("질문 JSON은 /tmp 아래에 있어야 합니다.")
    if args.mode == "retrieval":
        from eval.retrieval_eval import main as retrieval_main
        forwarded = [str(qpath), "--source", args.source, "--seed-mode", args.seed_mode,
                     "--seed-threshold", str(args.seed_threshold), "--hops", str(args.hops),
                     "--output", args.output, "--summary", args.summary]
        if args.execute:
            forwarded.append("--execute")
        for folder in args.csv_dir:
            forwarded.extend(["--csv-dir", folder])
        return retrieval_main(forwarded)
    from answer.answer_eval import run
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
