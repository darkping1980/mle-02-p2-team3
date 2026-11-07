"""Opt-in local Q/A diagnostics. Question text may contain personal data; keep files private.

This module records no database URLs, credentials, API keys, or other connection strings.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

try:
    from .answer.answer_eval import _number_candidates
    from .answer.answer_format import ANSWER_FORMAT_VERSION, check_answer_format
except ImportError:  # Script-style imports from this directory.
    from answer.answer_eval import _number_candidates
    from answer.answer_format import ANSWER_FORMAT_VERSION, check_answer_format

ROOT = Path(__file__).resolve().parents[5]


def safe_tmp(path) -> Path:
    target = Path(path).expanduser().resolve()
    root = Path("/tmp").resolve()
    if target == root or ROOT in target.parents or target == ROOT or root not in target.parents:
        raise ValueError("output path must be below /tmp")
    return target


def ungrounded_numbers(answer: str, evidence_text: str) -> list[str]:
    evidence = {(value, unit) for value, unit, _, _ in _number_candidates(evidence_text)}
    return [answer[a:b].replace(" ", "").replace(",", "")
            for value, unit, a, b in _number_candidates(answer)
            if (value, unit) not in evidence]


def build_record(*, question, answer, result, session_id=None, model=None, usage=None,
                 latency_ms=None, answer_format_version=ANSWER_FORMAT_VERSION,
                 graph_schema="fp_chat", source_refs=None, evidence_error=None,
                 app_version=None, number_check=None) -> dict:
    subgraph = result.get("subgraph") or {}
    nodes = list(subgraph.get("nodes") or [])
    retrieved_ids = [str(node.get("id")) for node in nodes if node.get("id") is not None][:200]
    fp_ids = [str(node.get("props", {}).get("fp_id")) for node in nodes
              if node.get("props", {}).get("fp_id") and not str(node["props"]["fp_id"]).startswith("doc:")]
    runs = sorted({str(node.get("props", {}).get("run_id")) for node in nodes
                   if node.get("props", {}).get("run_id") is not None})
    try:
        from .answer import answer_eval
    except ImportError:
        from answer import answer_eval
    evidence_text = "\n".join(
        [str(node.get("name", "")) + " " + " ".join(str(v) for v in (node.get("props") or {}).values())
         for node in nodes]
        + [" ".join(str(edge.get(k, "")) for k in ("source", "type", "target"))
           for edge in subgraph.get("edges", [])]
    )
    if number_check is None:
        try:
            try:
                from .answer.answer_check import check_answer_numbers
            except ImportError:
                from answer.answer_check import check_answer_numbers
            number_check = check_answer_numbers(str(answer), subgraph)
        except Exception:
            number_check = {"error": "check_failed"}
            print("FP_NUMBER_CHECK_ERROR:check_failed", file=sys.stderr)
    if not isinstance(number_check, dict) or "error" in number_check:
        number_check_summary = {"error": "check_failed"}
    else:
        counts = number_check.get("counts") or {}
        number_check_summary = {
            "scope_unknown": bool(number_check.get("scope_unknown")),
            "counts": {key: int(counts.get(key, 0)) for key in
                       ("scoped_grounded", "elsewhere_only", "ungrounded", "whole_subgraph_grounded")},
            "elsewhere_only": list(number_check.get("elsewhere_only") or []),
        }
    record = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "question": str(question),
        "answer": str(answer),
        "answer_format_version": answer_format_version,
        "model": model,
        "prompt_tokens": (usage or {}).get("prompt_tokens"),
        "completion_tokens": (usage or {}).get("completion_tokens"),
        "cost_usd": (usage or {}).get("cost_usd"),
        "latency_ms": {name: (latency_ms or {}).get(name) for name in
                       ("entities_db", "analyze_llm", "explore_db", "first_token", "total")},
        "selected_entities": list(result.get("selected_entities") or []),
        "retrieved_node_ids": retrieved_ids,
        "retrieved_node_count": len(nodes),
        "source_refs": list(source_refs or []),
        "source_refs_error": evidence_error,
        "graph_schema": graph_schema,
        "run_ids": runs,
        "refusal": answer_eval._refusal(str(answer)),
        "ungrounded_numbers": ungrounded_numbers(str(answer), evidence_text),
        "number_check": number_check_summary,
        "format_check": check_answer_format(str(answer)),
        "user_feedback": None,
        "app_version": app_version,
        # Adapter-only evidence lookup keys; stripped before serialization.
        "_fp_node_ids": fp_ids,
    }
    return record


def write_record(record: dict, path=None) -> bool:
    """Append one sanitized JSONL row; report only a code if anything fails."""
    configured = path if path is not None else os.environ.get("FP_QA_LOG")
    if not configured:
        return False
    try:
        target = safe_tmp(configured)
        target.parent.mkdir(parents=True, exist_ok=True)
        serializable = {k: v for k, v in record.items() if not k.startswith("_")}
        with target.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(serializable, ensure_ascii=False) + "\n")
        return True
    except ValueError:
        error_code = "invalid_path"
    except Exception:
        error_code = "write_error"
    print(f"FP_QA_LOG_ERROR:{error_code}", file=sys.stderr)
    return False
