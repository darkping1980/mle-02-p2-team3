#!/usr/bin/env python
"""Run a deliberately small, non-UI GraphRAG evaluation batch.

This runner invokes the same CardGraphRAG LangGraph backend as Streamlit, but
does not import Streamlit or persist app_log rows. A two-question paid smoke run
requires an explicit flag. Full 50-question runs require a separate, stronger
confirmation flag and should only be used after explicit approval.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


EVALUATION_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = EVALUATION_DIR / "evaluation_set_50.json"
GOLD_PATH = EVALUATION_DIR / "golden_answer_set_50.json"
DEFAULT_OUTPUT = EVALUATION_DIR / "runs"
ALLOWED_JUDGMENTS = {"CORRECT", "PARTIAL", "WRONG", "EXECUTION_ERROR", "JUDGMENT_HOLD"}
HOLD_IDS = {"CARD10-030"}
DEFAULT_SMOKE_IDS = ("CARD10-001", "CARD10-021")


def load_evaluation_sets() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    questions_doc = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    gold_doc = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    questions = questions_doc.get("questions")
    records = gold_doc.get("records")
    if not isinstance(questions, list) or not isinstance(records, list):
        raise ValueError("Expected questions[] and records[] in evaluation JSON files")
    if len(questions) != 50 or len(records) != 50:
        raise ValueError(f"Expected 50 questions and 50 gold records; got {len(questions)} and {len(records)}")
    q_by_id = {item.get("question_id"): item for item in questions}
    g_by_id = {item.get("question_id"): item for item in records}
    if len(q_by_id) != 50 or len(g_by_id) != 50 or set(q_by_id) != set(g_by_id):
        raise ValueError("Question IDs must be unique and match gold record IDs exactly")
    for question_id, question in q_by_id.items():
        gold = g_by_id[question_id]
        if question.get("hop_type") != gold.get("hop_type"):
            raise ValueError(f"Hop mismatch for {question_id}")
    verified = [record for record in records if record.get("verification_status") == "VERIFIED"]
    if len(verified) != 49 or sum(q.get("hop_type") == "1-hop" for q in questions) != 25 \
            or sum(q.get("hop_type") == "2-hop" for q in questions) != 25:
        raise ValueError("Expected 49 VERIFIED records and a 25/25 1-hop/2-hop split")
    if not all(question_id in q_by_id for question_id in HOLD_IDS):
        raise ValueError("The known review-hold question CARD10-030 is missing")
    return questions, g_by_id


def choose_questions(args: argparse.Namespace, questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {item["question_id"]: item for item in questions}
    if args.all:
        if not args.execute or not args.confirm_paid_calls or not args.confirm_full_50:
            raise ValueError("A 50-question run requires --execute --confirm-paid-calls --confirm-full-50")
        return questions
    ids = args.question_ids or list(DEFAULT_SMOKE_IDS)
    if args.execute and (len(ids) > 2 or not args.confirm_paid_calls):
        raise ValueError("Execution is limited to at most two selected questions and requires --confirm-paid-calls")
    unknown = [question_id for question_id in ids if question_id not in by_id]
    if unknown:
        raise ValueError(f"Unknown question IDs: {unknown}")
    return [by_id[question_id] for question_id in ids]


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(key): _safe_json(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_safe_json(item) for item in value]
        return str(value)


def _answer_evidence_ids(answer: dict[str, Any] | None) -> list[str]:
    ids = {str(evidence_id) for point in (answer or {}).get("points", [])
           for evidence_id in (point.get("evidence_ids") or [])}
    return sorted(ids)


def _outcome_record(question: dict[str, Any], gold: dict[str, Any], outcome: dict[str, Any], elapsed_ms: float) -> dict[str, Any]:
    answer = outcome.get("answer") or {}
    candidate_search = outcome.get("candidate_search") or {}
    parameters = outcome.get("search_parameters") or {}
    candidates = candidate_search.get("hits") or []
    selected_refs = parameters.get("benefit_ids") or []
    selected_candidate_ids = [item.get("benefit_id") for item in candidates
                              if item.get("id") in set(selected_refs) and item.get("benefit_id") is not None]
    expected_ids = question.get("benefit_ids") or ([question["benefit_id"]] if question.get("benefit_id") else [])
    candidate_id_strings = {str(item.get("benefit_id")) for item in candidates if item.get("benefit_id") is not None}
    selected_id_strings = {str(value) for value in selected_candidate_ids}
    selected_keys = parameters.get("benefit_keys") or []
    evidence = outcome.get("evidence") or []
    cited_evidence_ids = _answer_evidence_ids(answer)
    all_evidence_ids = sorted({str(item.get("evidence_id")) for item in evidence if item.get("evidence_id")})
    error = outcome.get("error")
    execution_status = "EXECUTION_ERROR" if error or answer.get("status") == "ERROR" else "COMPLETED"
    if question["question_id"] in HOLD_IDS:
        judgment = "JUDGMENT_HOLD"
    elif execution_status == "EXECUTION_ERROR":
        judgment = "EXECUTION_ERROR"
    else:
        # A factual judgment requires checking the official PDF, not text similarity alone.
        judgment = "PENDING_PDF_REVIEW"

    return {
        "question_id": question["question_id"],
        "hop_type": question["hop_type"],
        "source_type": question.get("source_type"),
        "question": question["question"],
        "gold_verification_status": gold.get("verification_status"),
        "accuracy_eligible": gold.get("verification_status") == "VERIFIED",
        "execution_status": execution_status,
        "judgment": judgment,
        "evidence_match": None,
        "evidence_review_status": "PENDING_PDF_REVIEW",
        "wall_elapsed_ms": round(elapsed_ms, 2),
        "answer": _safe_json(answer),
        "answer_diagnostics": _safe_json(outcome.get("answer_diagnostics")),
        "search": {
            "candidate_benefit_ids": [item.get("benefit_id") for item in candidates],
            "expected_benefit_ids": expected_ids,
            "expected_ids_missing_from_candidates": [value for value in expected_ids if str(value) not in candidate_id_strings],
            "expected_ids_not_selected_from_hybrid_hits": [value for value in expected_ids if str(value) not in selected_id_strings],
            "candidate_keys": [item.get("key") for item in candidates],
            "candidate_names": [item.get("bnft_nm") for item in candidates],
            "selected_benefit_ids_from_hybrid_hits": selected_candidate_ids,
            "selected_entity_refs": selected_refs,
            "selected_benefit_keys": selected_keys,
            "selected_candidate_refs": candidate_search.get("selected_ids", []),
            "unselected_candidate_refs": candidate_search.get("unselected_candidate_ids", []),
            "coverage_gaps": candidate_search.get("coverage_gaps", []),
            "candidate_search_elapsed_ms": candidate_search.get("elapsed_ms"),
            "engines": candidate_search.get("engines", []),
        },
        "retrieval_trace": _safe_json(outcome.get("retrieval_trace", [])),
        "retrieved_entity_refs": [detail.get("entity_ref") for detail in (outcome.get("retrieved_data") or [])],
        "pdf_evidence": [{
            "evidence_id": item.get("evidence_id"),
            "document_id": item.get("document_id"),
            "document_title": item.get("document_title"),
            "pdf_file_name": item.get("pdf_file_name"),
            "page_no": item.get("page_no"),
            "chunk_id": item.get("chunk_id"),
            "quote": item.get("quote"),
            "benefit_ids": item.get("benefit_ids", []),
        } for item in evidence],
        "unreferenced_retrieved_evidence_ids": sorted(set(all_evidence_ids) - set(cited_evidence_ids)),
        "pdf_evidence_records_by_benefit": [{
            "benefit_key": detail.get("entity_ref"),
            "evidence_records": _safe_json(detail.get("evidence", [])),
        } for detail in (outcome.get("retrieved_data") or [])],
        "answer_cited_evidence_ids": cited_evidence_ids,
        "llm_calls": _safe_json(outcome.get("llm_calls", [])),
        "error": _safe_json(error),
        "warnings": _safe_json(outcome.get("warnings", [])),
        "expected_answer_for_review": gold.get("expected_answer"),
        "expected_facts_for_review": gold.get("expected_facts"),
        "pdf_for_review": _safe_json(gold.get("pdf")),
    }


def print_plan(selected: list[dict[str, Any]], gold_by_id: dict[str, dict[str, Any]], execute: bool) -> None:
    print("Mode:", "EXECUTE (paid backend calls)" if execute else "PLAN ONLY (no network or DB calls)")
    print("Selected questions:", len(selected))
    for question in selected:
        gold = gold_by_id[question["question_id"]]
        denominator = "included" if gold.get("verification_status") == "VERIFIED" else "excluded; retain run output"
        print(f"- {question['question_id']} [{question['hop_type']}; {gold.get('verification_status')}; accuracy denominator {denominator}]")
        print("  ", question["question"])
    if execute:
        count = len(selected)
        print(f"Call budget: {count} embedding request(s), up to {2 * count} LLM request(s), plus read-only Neo4j queries.")


def run_backend(selected: list[dict[str, Any]], gold_by_id: dict[str, dict[str, Any]], output_path: Path) -> None:
    # Resolve src/ so the project package can be imported from this standalone script.
    source_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(source_root))

    # These are the same constructors and concrete run method used by Streamlit's get_pipeline().
    # Do not import streamlit_app: its request wrapper persists app_log rows by default.
    from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag, neo4j_search
    from card_benefit.payment_card.db_pipeline_origin_search.execution_log import configure_application_logging

    logging.basicConfig(level=logging.WARNING)
    card_graphrag.configure_card_logging()
    configure_application_logging(False, card_graphrag.CARD_LOGGER_NAME)
    logger = logging.getLogger(card_graphrag.CARD_LOGGER_NAME)
    logger.setLevel(logging.WARNING)

    interpret_llm, answer_llm = card_graphrag.create_llms()
    if interpret_llm is None or answer_llm is None:
        raise RuntimeError("OPENAI_API_KEY is unavailable; refusing to start paid evaluation requests")
    search = neo4j_search.connect()
    candidate_search = card_graphrag.create_neo4j_benefit_search(search)
    pipeline = card_graphrag.CardGraphRAG(search, interpret_llm, answer_llm, candidate_search=candidate_search)

    results = []
    try:
        for question in selected:
            gold = gold_by_id[question["question_id"]]
            started = perf_counter()
            try:
                outcome = pipeline.run(question["question"])
                elapsed_ms = (perf_counter() - started) * 1000
                results.append(_outcome_record(question, gold, outcome, elapsed_ms))
            except Exception as error:  # Preserve per-question exceptions and continue the requested smoke batch.
                elapsed_ms = (perf_counter() - started) * 1000
                results.append({
                    "question_id": question["question_id"], "hop_type": question["hop_type"],
                    "source_type": question.get("source_type"), "question": question["question"],
                    "gold_verification_status": gold.get("verification_status"),
                    "accuracy_eligible": gold.get("verification_status") == "VERIFIED",
                    "execution_status": "EXECUTION_ERROR",
                    "judgment": "JUDGMENT_HOLD" if question["question_id"] in HOLD_IDS else "EXECUTION_ERROR",
                    "evidence_match": None, "evidence_review_status": "PENDING_PDF_REVIEW",
                    "wall_elapsed_ms": round(elapsed_ms, 2), "error": {"type": type(error).__name__, "message": str(error)[:1000]},
                    "answer": None, "search": {}, "pdf_evidence": [], "answer_cited_evidence_ids": [],
                    "llm_calls": [], "expected_answer_for_review": gold.get("expected_answer"),
                    "expected_facts_for_review": gold.get("expected_facts"), "pdf_for_review": _safe_json(gold.get("pdf")),
                })
    finally:
        close = getattr(search, "close", None)
        if callable(close):
            close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "runner": "CardGraphRAG.run via direct backend; Streamlit not imported",
        "app_log_persistence": "disabled / not invoked",
        "result_count": len(results),
        "results": results,
        "adjudication_note": "Do not finalize factual judgments from string overlap; review the cited official PDF and benefit ownership.",
    }
    output_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(results)} result(s): {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="Execute the selected backend questions; this makes paid API calls.")
    parser.add_argument("--question-ids", nargs="+", help="Select at most two IDs for a smoke execution; defaults to CARD10-001 and CARD10-021.")
    parser.add_argument("--all", action="store_true", help="Select all 50. Requires both explicit confirmation flags with --execute.")
    parser.add_argument("--confirm-paid-calls", action="store_true", help="Acknowledge paid embedding/LLM API requests for selected smoke questions.")
    parser.add_argument("--confirm-full-50", action="store_true", help="Acknowledge the full 50-question cost/latency run after separate approval.")
    parser.add_argument("--output", type=Path, default=None, help="Result JSON path (default: evaluation/runs/<UTC timestamp>.json).")
    parser.add_argument("--score", type=Path, default=None, help="Summarize a completed results JSON after human PDF adjudication; no backend calls.")
    return parser.parse_args()


def score_results(path: Path) -> int:
    document = json.loads(path.read_text(encoding="utf-8"))
    records = document.get("results")
    if not isinstance(records, list):
        raise ValueError("Results file must contain results[]")
    verified = [row for row in records if row.get("accuracy_eligible")]
    holds = [row for row in records if row.get("judgment") == "JUDGMENT_HOLD"]
    unknown = sorted({row.get("judgment") for row in records} - ALLOWED_JUDGMENTS - {"PENDING_PDF_REVIEW"})
    if unknown:
        raise ValueError(f"Unknown judgment values: {unknown}")
    print(f"Verified questions present: {len(verified)}/49; full set: {len(verified) == 49}")
    print(f"Review-hold records preserved: {len(holds)}")
    for hop in ("1-hop", "2-hop"):
        subset = [row for row in verified if row.get("hop_type") == hop]
        correct = sum(row.get("judgment") == "CORRECT" for row in subset)
        print(f"{hop}: {correct}/{len(subset)} correct ({(100 * correct / len(subset)) if subset else 0:.1f}%)")
    errors_all = sum(row.get("execution_status") == "EXECUTION_ERROR" or row.get("judgment") == "EXECUTION_ERROR" for row in records)
    errors_verified = sum(row.get("execution_status") == "EXECUTION_ERROR" or row.get("judgment") == "EXECUTION_ERROR" for row in verified)
    pending = sum(row.get("judgment") == "PENDING_PDF_REVIEW" for row in verified)
    partial = sum(row.get("judgment") == "PARTIAL" for row in verified)
    wrong = sum(row.get("judgment") == "WRONG" for row in verified)
    evidence_reviewed = [row for row in verified if row.get("evidence_match") in (True, False)]
    evidence_matches = sum(row.get("evidence_match") is True for row in evidence_reviewed)
    candidate_misses = sum(bool((row.get("search") or {}).get("expected_ids_missing_from_candidates")) for row in verified)
    print(f"PARTIAL: {partial}; WRONG: {wrong}; execution errors: {errors_all} total / {errors_verified} VERIFIED; pending PDF judgments: {pending}")
    if evidence_reviewed:
        print(f"Evidence match: {evidence_matches}/{len(evidence_reviewed)} reviewed ({100 * evidence_matches / len(evidence_reviewed):.1f}%)")
    else:
        print("Evidence match: no human-reviewed evidence records yet")
    print(f"Questions with expected benefit IDs missing from Hybrid candidates: {candidate_misses}/{len(verified)}")
    if len(verified) < 49 or pending:
        print("Accuracy/evidence summaries are provisional until all VERIFIED records are run and PDF-adjudicated.")
    return 0


def main() -> int:
    args = parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if args.score is not None:
        try:
            return score_results(args.score)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            print(f"Scoring failed: {error}", file=sys.stderr)
            return 2
    try:
        questions, gold_by_id = load_evaluation_sets()
        selected = choose_questions(args, questions)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Preflight failed: {error}", file=sys.stderr)
        return 2

    print_plan(selected, gold_by_id, args.execute)
    if not args.execute:
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = args.output or (DEFAULT_OUTPUT / f"evaluation_run_{timestamp}.json")
    try:
        run_backend(selected, gold_by_id, output_path)
    except Exception as error:
        print(f"Evaluation run did not complete: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
