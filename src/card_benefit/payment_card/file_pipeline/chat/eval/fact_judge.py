"""Evaluate answer facts with strict value matching followed by an optional LLM judge."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

try:
    from ..answer import answer_eval
except ImportError:
    from answer import answer_eval

MODEL = "gpt-6-luna"
DEFAULT_CACHE = "/tmp/fact_judge_cache.json"
INPUT_TOKENS_PER_CALL = 1200
COMPLETION_TOKENS = 2000


class CostLimitExceeded(RuntimeError):
    """Raised before starting a call that would exceed the configured budget."""


def _create_client():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY 환경 변수가 필요합니다.")
    from openai import OpenAI
    return OpenAI(api_key=key)


def _cache_key(answer, expected):
    payload = json.dumps([str(answer), str(expected)], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cache(path):
    target = answer_eval.safe_tmp(path)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(path, cache):
    target = answer_eval.safe_tmp(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_judgement(content):
    try:
        start, end = content.index("{"), content.rindex("}") + 1
        value = json.loads(content[start:end])
        verdict = value.get("verdict") if isinstance(value, dict) else None
        reason = value.get("reason", "") if isinstance(value, dict) else ""
        if verdict not in {"correct", "incorrect", "not_stated"} or not isinstance(reason, str):
            raise ValueError("invalid response schema")
        return {"verdict": verdict, "reason": reason[:40]}
    except (ValueError, TypeError, AttributeError):
        return {"verdict": "incorrect", "reason": "invalid_json"}


def _judge_prompt(question, expected, answer):
    system = (
        "기대 사실과 챗봇 답변의 의미를 비교하는 판정자다. 답변이 기대 사실의 의미를 담고 모순이 없으면 correct, "
        "숫자·조건·한도가 다르거나 명시적으로 모순되면 incorrect, 해당 내용을 언급하지 않으면 not_stated다. "
        "의역과 단위 환산은 허용한다. JSON 객체 하나만 반환하고 reason은 40자 이내로 쓴다."
    )
    user = f"[질문]\n{question}\n[기대 사실]\n{expected}\n[챗봇 답변]\n{answer}\nJSON: {{\"verdict\":\"correct|incorrect|not_stated\",\"reason\":\"<=40자\"}}"
    return system, user


def _estimated_call_cost():
    return INPUT_TOKENS_PER_CALL * 0.10 / 1_000_000 + COMPLETION_TOKENS * 0.50 / 1_000_000


def judge_records(records, *, client=None, cache_path=DEFAULT_CACHE, max_cost_usd=0.05, sleep=0.3):
    """Return fact-level judgements. A missing client performs a no-call dry count only."""
    if max_cost_usd < 0 or sleep < 0:
        raise ValueError("max_cost_usd and sleep must be non-negative")
    cache = _load_cache(cache_path)
    pending = []
    for row in records:
        question = row.get("question") or {}
        if question.get("no_answer"):
            continue
        answer = str(row.get("answer", ""))
        for expected in question.get("expected", []):
            matched = answer_eval._value_match(answer, str(expected), str(question.get("type", "")))[0]
            key = _cache_key(answer, expected)
            if not matched and key not in cache:
                pending.append((row, expected, key))
    if client is None:
        return [], {"llm_call_estimate": len(pending), "estimated_cost_usd": round(len(pending) * _estimated_call_cost(), 8)}

    from openai_llm_patch import CostLimitExceeded as PatchCostLimitExceeded
    from openai_llm_patch import install, reset_usage, usage_totals
    reset_usage()
    llm = install(model=MODEL, client=client, max_cost_usd=max_cost_usd, sleep=sleep,
                  min_completion_tokens=COMPLETION_TOKENS)
    # Estimate a per-call ceiling before sending data; the adapter also checks actual usage.
    for index, (row, expected, key) in enumerate(pending):
        if usage_totals()["cost_usd"] + _estimated_call_cost() > max_cost_usd:
            raise CostLimitExceeded("호출 예상 비용이 --max-cost-usd를 초과합니다.")
        question = row.get("question") or {}
        system, user = _judge_prompt(question.get("question", ""), expected, row.get("answer", ""))
        try:
            cache[key] = _parse_judgement(llm.complete(system, user, max_tokens=COMPLETION_TOKENS))
        except PatchCostLimitExceeded as exc:
            raise CostLimitExceeded(str(exc)) from exc
        _save_cache(cache_path, cache)

    judged = []
    for row in records:
        question = row.get("question") or {}
        answer = str(row.get("answer", ""))
        no_answer = bool(question.get("no_answer", False))
        facts = []
        for expected in question.get("expected", []):
            matched, kind, _ = answer_eval._value_match(answer, str(expected), str(question.get("type", "")))
            if matched:
                verdict, reason = "match_rule", str(kind or "")
            else:
                cached = cache.get(_cache_key(answer, expected), {"verdict": "incorrect", "reason": "not_judged"})
                verdict, reason = cached["verdict"], cached["reason"]
            facts.append({"expected": expected, "verdict": verdict, "reason": reason})
        abstained = answer_eval._refusal(answer) if no_answer else None
        correct = bool(abstained) if no_answer else all(f["verdict"] in {"match_rule", "correct"} for f in facts)
        judged.append({"id": row.get("id"), "facts": facts, "all_facts_correct": correct,
                       "abstained": abstained})
    return judged, {"llm_call_estimate": len(pending), "estimated_cost_usd": round(len(pending) * _estimated_call_cost(), 8),
                    "actual_cost_usd": usage_totals()["cost_usd"]}


def _rate(rows):
    return {"count": len(rows), "all_facts_correct": sum(bool(r["all_facts_correct"]) for r in rows),
            "all_facts_correct_rate": sum(bool(r["all_facts_correct"]) for r in rows) / len(rows) if rows else 0.0}


def summarize(records, results):
    entries = [(record, result) for record, result in zip(records, results)]
    summary = {"overall": _rate([r for _, r in entries]), "by_issuer": {}, "by_type": {}}
    for field, out_key in (("issuer", "by_issuer"), ("type", "by_type")):
        groups = {}
        for record, result in entries:
            value = (record.get("question") or {}).get(field, "unknown")
            groups.setdefault(str(value), []).append(result)
        summary[out_key] = {key: _rate(group) for key, group in sorted(groups.items())}
    return summary


def _read_jsonl(path):
    return [json.loads(line) for line in Path(path).expanduser().resolve().read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(description="JSONL answer fact judge")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="/tmp/fact-judge.jsonl")
    parser.add_argument("--summary", default="/tmp/fact-judge-summary.json")
    parser.add_argument("--cache", default=DEFAULT_CACHE)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--max-cost-usd", type=float, default=0.05)
    parser.add_argument("--sleep", type=float, default=0.3)
    args = parser.parse_args(argv)
    output, summary_path = answer_eval.safe_tmp(args.output), answer_eval.safe_tmp(args.summary)
    records = _read_jsonl(args.input)
    if not args.execute:
        _, estimate = judge_records(records, cache_path=args.cache, max_cost_usd=args.max_cost_usd, sleep=args.sleep)
        print(json.dumps({"mode": "dry-run", "record_count": len(records), **estimate}, ensure_ascii=False))
        return 0
    client = _create_client()
    results, cost = judge_records(records, client=client, cache_path=args.cache,
                                  max_cost_usd=args.max_cost_usd, sleep=args.sleep)
    output.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as stream:
        for result in results:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
    summary = summarize(records, results)
    summary.update(cost)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"mode": "execute", "record_count": len(records), "output": str(output),
                      "summary": str(summary_path), **cost}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
