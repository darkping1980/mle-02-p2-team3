#!/usr/bin/env python
"""Run the original 1/2/3-hop questionnaire with optional local LLM trace JSON.

Detailed local traces are opt-in and require APP_ENV=development plus
APP_EVALUATION_TRACE_ENABLED=1. PostgreSQL app_log persistence can remain OFF.
Each selected question is invoked once; failures are recorded and are not retried.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

EVALUATION_DIR = Path(__file__).resolve().parent
QUESTIONNAIRE_PATH = EVALUATION_DIR / "card10_graphrag_golden_dataset_v1.jsonl"
RESULTS_DIR = EVALUATION_DIR / "results"


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(v) for v in value]
        return str(value)


def _load_questions(path: Path = QUESTIONNAIRE_PATH) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != 50:
        raise ValueError(f"Expected 50 questionnaire rows; got {len(rows)}")
    ids = [row.get("question_id") for row in rows]
    if len(set(ids)) != 50 or any(not row.get("question") for row in rows):
        raise ValueError("Questionnaire IDs must be unique and every question must be nonempty")
    return rows


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def _source_revision() -> tuple[str | None, dict[str, str]]:
    files = [
        Path(__file__).resolve(),
        EVALUATION_DIR.parents[1] / "payment_card" / "db_pipeline_origin_search" / "card_graphrag.py",
        EVALUATION_DIR.parents[1] / "payment_card" / "db_pipeline_origin_search" / "execution_log.py",
        EVALUATION_DIR.parents[1] / "payment_card" / "db_pipeline_origin_search" / "neo4j_search.py",
    ]
    hashes = {str(path.relative_to(EVALUATION_DIR.parents[2])): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in files if path.exists()}
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=EVALUATION_DIR.parents[2],
                              capture_output=True, text=True, timeout=3, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        head = None
    return head, hashes


def _expected_stages(path: list[str]) -> list[str]:
    expected = ["INTERPRET"]
    if "retrieve" in path:
        expected.append("RETRIEVE")
    if "answer" in path:
        expected.append("ANSWER")
    return expected


def _trace_validation(events: list[dict[str, Any]], expected: list[str]) -> dict[str, Any]:
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_stage.setdefault(str(event.get("stage", "")).upper(), []).append(event)
    missing = [stage for stage in expected if not by_stage.get(stage)]
    invalid_hashes = []
    missing_raw = []
    missing_snapshots = []
    for stage in expected:
        for event in by_stage.get(stage, []):
            if stage in {"INTERPRET", "ANSWER"}:
                prompt = event.get("prompt_text")
                if (not isinstance(prompt, str)
                        or hashlib.sha256(prompt.encode("utf-8")).hexdigest() != event.get("prompt_sha256")):
                    invalid_hashes.append(stage)
                if event.get("raw_output") is None:
                    missing_raw.append(stage)
            elif stage == "RETRIEVE" and (
                event.get("input_snapshot") is None or event.get("output_snapshot") is None
            ):
                missing_snapshots.append(stage)
    complete = not missing and not invalid_hashes and not missing_raw and not missing_snapshots
    return {
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "expected_stages": expected,
        "captured_stages": list(by_stage),
        "missing_stages": missing,
        "prompt_hash_mismatch_stages": invalid_hashes,
        "missing_raw_output_stages": missing_raw,
        "missing_input_output_snapshots": missing_snapshots,
        "event_count": len(events),
    }


def _result_record(gold: dict[str, Any], outcome: dict[str, Any] | None, error: dict[str, str] | None,
                   elapsed_ms: float, run_id: str, trace_events: list[dict[str, Any]],
                   trace_write_status: str) -> dict[str, Any]:
    outcome = outcome or {}
    answer = outcome.get("answer") or {}
    path = outcome.get("path") or []
    answer_called = any(call.get("node") == "answer" for call in outcome.get("llm_calls") or [])
    execution_status = "ERROR" if error or outcome.get("error") or answer.get("status") == "ERROR" else "COMPLETED"
    gold_status = gold.get("ground_truth_status", "NEEDS_REVIEW")
    judgment = "ERROR" if execution_status == "ERROR" else "HOLD"
    return {
        "question_id": gold["question_id"],
        "run_id": run_id,
        "hop_count": gold.get("hop_count"),
        "question": gold["question"],
        "ground_truth_status": gold_status,
        "expected_answer": gold.get("expected_answer"),
        "expected_facts": gold.get("expected_facts"),
        "official_pdf_evidence": gold.get("official_pdf_evidence"),
        "execution_status": execution_status,
        "path": path,
        "execution_stage_status": "STOPPED_AT_INTERPRET" if execution_status == "COMPLETED" and "retrieve" not in path
                                else "ANSWER_COMPLETED" if answer_called and execution_status == "COMPLETED"
                                else "EXECUTION_ERROR" if execution_status == "ERROR" else "RETRIEVE_COMPLETED_NO_ANSWER",
        "answer_generation_status": "ANSWERED" if answer_called and answer.get("status") != "ERROR"
                                    else "NOT_CALLED" if not answer_called else "ERROR",
        "judgment": judgment,
        "judgment_basis": "Golden source is not PDF_VERIFIED; HOLD is separate from execution status."
                          if judgment == "HOLD" and gold_status != "PDF_VERIFIED"
                          else "Factual adjudication is pending; HOLD is not counted as wrong.",
        "intent": outcome.get("intent"),
        "search_parameters": outcome.get("search_parameters"),
        "search": outcome.get("candidate_search"),
        "retrieval_trace": outcome.get("retrieval_trace", []),
        "retrieved_entity_refs": [row.get("entity_ref") for row in outcome.get("retrieved_data") or []],
        "retrieved_data": outcome.get("retrieved_data", []),
        "pdf_evidence": outcome.get("evidence", []),
        "answer": answer,
        "final_answer": answer.get("answer_text") or answer.get("conclusion"),
        "llm_calls": outcome.get("llm_calls", []),
        "llm_usage": {
            "calls": len(outcome.get("llm_calls") or []),
            "input_tokens": sum(call.get("input_tokens") or 0 for call in outcome.get("llm_calls") or []),
            "output_tokens": sum(call.get("output_tokens") or 0 for call in outcome.get("llm_calls") or []),
            "cost_usd": round(sum(call.get("cost_usd") or 0 for call in outcome.get("llm_calls") or []), 10),
        },
        "elapsed_ms": round(elapsed_ms, 2),
        "error": error or outcome.get("error"),
        "warnings": outcome.get("warnings", []),
        "trace": _trace_validation(trace_events, _expected_stages(path)),
        "trace_write_status": trace_write_status,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ids", nargs="+", help="Run specific question IDs once (smoke verification)")
    group.add_argument("--all", action="store_true", help="Run all 50 questionnaire questions once")
    parser.add_argument("--trace", action="store_true", help="Capture sanitized LLM inputs/outputs to a local trace JSON")
    parser.add_argument("--output-prefix", default="questionnaire_live", help="Output filename prefix")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    from dotenv import load_dotenv
    load_dotenv()
    source_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(source_root))
    from card_benefit.payment_card.db_pipeline_origin_search.execution_log import (
        evaluation_llm_trace_enabled, sanitize_llm_trace_event,
    )
    if args.trace and not evaluation_llm_trace_enabled():
        print("Trace capture refused: set APP_ENV=development and APP_EVALUATION_TRACE_ENABLED=1.", file=sys.stderr)
        return 2
    questions = _load_questions()
    by_id = {row["question_id"]: row for row in questions}
    selected = questions if args.all else [by_id[qid] for qid in args.ids if qid in by_id]
    unknown = [] if args.all else [qid for qid in args.ids if qid not in by_id]
    if unknown or (not args.all and len(selected) != len(args.ids)):
        print(f"Unknown question IDs: {unknown}", file=sys.stderr)
        return 2
    if len({row["question_id"] for row in selected}) != len(selected):
        print("Duplicate question IDs are not allowed in one run.", file=sys.stderr)
        return 2

    source_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(source_root))
    from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag, neo4j_search
    from card_benefit.payment_card.db_pipeline_origin_search.execution_log import configure_application_logging
    logging_level = __import__("logging").WARNING
    __import__("logging").basicConfig(level=logging_level)
    card_graphrag.configure_card_logging()
    configure_application_logging(False, card_graphrag.CARD_LOGGER_NAME)
    __import__("logging").getLogger(card_graphrag.CARD_LOGGER_NAME).setLevel(logging_level)
    interpret_llm, answer_llm = card_graphrag.create_llms()
    if interpret_llm is None or answer_llm is None:
        print("OPENAI_API_KEY unavailable; no requests were made.", file=sys.stderr)
        return 2
    search = neo4j_search.connect()
    candidate_search = card_graphrag.create_neo4j_benefit_search(search)
    pipeline = card_graphrag.CardGraphRAG(search, interpret_llm, answer_llm, candidate_search=candidate_search)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{args.output_prefix}-{stamp}-{uuid.uuid4().hex[:8]}"
    results_path = RESULTS_DIR / f"{run_id}.json"
    traces_path = RESULTS_DIR / f"{run_id}_trace.json"
    if results_path.exists() or traces_path.exists():
        print("Refusing to overwrite prior run files.", file=sys.stderr)
        search.driver.close()
        return 2
    head, hashes = _source_revision()
    results: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    trace_write_warning: str | None = None

    def checkpoint() -> None:
        nonlocal trace_write_warning
        results_doc = {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id, "git_head": head, "source_sha256": hashes,
            "model": card_graphrag.card_model(), "question_source": str(QUESTIONNAIRE_PATH),
            "runner": "direct CardGraphRAG.run; real Neo4j and LLM; app_log persistence disabled",
            "trace_requested": bool(args.trace), "trace_enabled": evaluation_llm_trace_enabled(),
            "retry_policy": "one call per question; no automatic retries",
            "question_count": len(results), "results": results,
        }
        try:
            _atomic_write_json(results_path, results_doc)
        except Exception as exc:
            print(f"WARNING: evaluation result JSON write failed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        if args.trace:
            trace_doc = {
                "created_at_utc": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id, "git_head": head, "source_sha256": hashes,
                "model": card_graphrag.card_model(), "trace_policy": "PII/secret redacted; prompt hash is over stored prompt_text",
                "question_count": len(traces), "traces": traces,
            }
            try:
                _atomic_write_json(traces_path, trace_doc)
                trace_write_warning = None
            except Exception as exc:
                trace_write_warning = f"{type(exc).__name__}: {exc}"
                print(f"WARNING: detailed Trace JSON write failed; capture is not considered successful: {trace_write_warning}",
                      file=sys.stderr, flush=True)

    try:
        for index, gold in enumerate(selected, 1):
            qid = gold["question_id"]
            request_id = str(uuid.uuid4())
            qrun = f"{run_id}:{qid}"
            started = perf_counter()
            outcome = None
            error = None
            try:
                outcome = pipeline.run(
                    gold["question"], request_id=request_id, question_id=qid,
                    capture_diagnostics=args.trace,
                )
            except Exception as exc:
                error = {"type": type(exc).__name__, "message": str(exc)[:1200]}
            elapsed_ms = (perf_counter() - started) * 1000
            safe_events = []
            for event in (outcome or {}).get("llm_trace_events") or []:
                safe_events.append(sanitize_llm_trace_event({
                    **event, "question_id": qid, "run_id": qrun, "request_id": request_id,
                }))
            trace_row = {"question_id": qid, "run_id": qrun, "request_id": request_id,
                         "events": safe_events}
            traces.append(trace_row)
            record = _result_record(gold, outcome, error, elapsed_ms, qrun, safe_events,
                                    "PENDING" if args.trace else "DISABLED")
            results.append(record)
            checkpoint()
            record["trace_write_status"] = "FAILED" if trace_write_warning else ("SAVED" if args.trace else "DISABLED")
            checkpoint()
            print(json.dumps({
                "index": index, "question_id": qid, "run_id": qrun,
                "execution_status": record["execution_status"],
                "execution_stage_status": record["execution_stage_status"],
                "answer_generation_status": record["answer_generation_status"],
                "trace_status": record["trace"]["status"],
                "trace_events": record["trace"]["event_count"],
                "trace_write_status": record["trace_write_status"],
                "llm_calls": record["llm_usage"]["calls"],
                "llm_cost_usd": record["llm_usage"]["cost_usd"],
            }, ensure_ascii=False), flush=True)
    finally:
        try:
            search.driver.close()
        except Exception:
            pass
        os.environ["APP_EVALUATION_TRACE_ENABLED"] = "0"
        checkpoint()

    print(json.dumps({
        "run_id": run_id, "results_file": str(results_path), "trace_file": str(traces_path),
        "questions_invoked": len(results),
        "trace_questions_complete": sum(r["trace"]["status"] == "COMPLETE" and r["trace_write_status"] == "SAVED" for r in results),
        "trace_write_warning": trace_write_warning,
        "llm_calls": sum(r["llm_usage"]["calls"] for r in results),
        "llm_cost_usd": round(sum(r["llm_usage"]["cost_usd"] for r in results), 10),
        "trace_gate_after_run": os.getenv("APP_EVALUATION_TRACE_ENABLED"),
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
