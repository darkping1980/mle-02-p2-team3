"""Small, opt-in answer quality evaluation for fp_chat using the team rag pipeline."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import re

ROOT = Path(__file__).resolve().parents[6]


def safe_tmp(path):
    path = Path(path).expanduser().resolve()
    if path == ROOT or ROOT in path.parents or Path("/tmp").resolve() not in path.parents:
        raise ValueError("출력은 저장소 밖 /tmp 아래만 허용됩니다.")
    return path


def _norm(value):
    return "".join(str(value).replace(",", "").replace("₩", "").replace("원", "").split()).casefold()


def _answer_has(answer, expected):
    return _norm(expected) in _norm(answer)


_NUM_RE = re.compile(r"(?<![\w])\d[\d,]*(?:\.\d+)?\s*(?:억|만|천)?\s*(?:원|점|회|%|개월|일)?(?![\w])")
_GENERIC = {"의", "을", "를", "이", "가", "은", "는", "에", "와", "과", "및", "등", "할인", "혜택"}
_UNITS = ("개월", "원", "점", "회", "%", "일")


def _number_candidates(text):
    # Exclude date-shaped spans; retain their year/month/day from becoming matches.
    dates = list(re.finditer(r"\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일", text))
    date_ranges = [(m.start(), m.end()) for m in dates]
    out = []
    for match in _NUM_RE.finditer(text):
        if any(a <= match.start() < b for a, b in date_ranges):
            continue
        raw = match.group(0).replace(" ", "").replace(",", "")
        m = re.fullmatch(r"(\d+(?:\.\d+)?)(억|만|천)?(원|점|회|%|개월|일)?", raw)
        if not m:
            continue
        value = float(m.group(1)) * {None: 1, "천": 1_000, "만": 10_000, "억": 100_000_000}[m.group(2)]
        out.append((value, m.group(3), match.start(), match.end()))
    return out


def _name_norm(text):
    return "".join(ch for ch in str(text).casefold() if ch.isalnum())


def _tokens(text):
    return [t.casefold() for t in re.findall(r"[가-힣A-Za-z0-9]+", text) if t.casefold() not in _GENERIC]


def _span(answer, start, end):
    left, right = max(0, start - 15), min(len(answer), end + 15)
    return answer[left:right][:40]


def _value_match(answer, expected, question_type=""):
    val = str(expected)
    date_matches = list(re.finditer(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", answer))
    if date_matches and (re.fullmatch(r"\d{1,2}\s*(?:년|월|일)", val) or (val.isdigit() and any(val in m.groups() for m in date_matches))):
        return False, None, None
    # Hash/document identifiers are alphanumeric and must match as a token.
    if re.fullmatch(r"\d{8,}", val) and re.search(r"(?<![\w])[0-9a-fA-F]{8,}(?![\w])", answer) and re.search(r"[a-fA-F]", answer):
        return False, None, None
    if re.fullmatch(r"[0-9a-fA-F]{8,}", val) and re.search(r"[a-fA-F]", val):
        m = re.search(rf"(?<![\w]){re.escape(val[:8])}[0-9a-fA-F]*(?![\w])", answer, re.I)
        return (True, "hash", _span(answer, m.start(), m.end())) if m else (False, None, None)
    literal = val in answer
    old = _answer_has(answer, val)
    if literal and not re.search(r"\d", val):
        at = answer.find(val)
        return True, "exact", _span(answer, at, at + len(val))
    if re.search(r"\d", val):
        want = _number_candidates(val)
        got = _number_candidates(answer)
        if want:
            wv, wu, _, _ = want[0]
            for av, au, a, b in got:
                if abs(wv - av) < 1e-8 and wu and au == wu:
                    return True, "number_unit", _span(answer, a, b)
                if abs(wv - av) < 1e-8 and not wu and (not au or question_type in {"benefit_limit", "benefit_condition"}):
                    return True, "number_unitless", _span(answer, a, b)
            # Preserve strict digit matching only when no conflicting unit follows it.
            if old and not any(a <= (m.start() + len(val)) < b and unit for _, unit, a, b in got for m in [re.search(re.escape(val), answer)] if m):
                at = _norm(answer).find(_norm(val))
                return True, "exact", _span(answer, max(0, at), max(0, at) + len(val))
    elif old:
        at = _norm(answer).find(_norm(val))
        return True, "exact_normalized", _span(answer, max(0, at), max(0, at) + len(val))
    normalized = _name_norm(val)
    ansnorm = _name_norm(answer)
    if normalized and not re.search(r"\d", val) and normalized in ansnorm:
        # locate approximate normalized hit for evidence
        return True, "exact_normalized", answer[:40]
    expected_tokens = _tokens(val)
    original_tokens = re.findall(r"[가-힣A-Za-z0-9]+", val)
    if (len(expected_tokens) <= 1 and len(original_tokens) <= 1) or len(normalized) < 4:
        return False, None, None
    answer_tokens = set(_tokens(answer))
    hit = [token for token in expected_tokens if token in answer_tokens]
    if hit and len(hit) / len(expected_tokens) >= .8:
        return True, "name_partial", " ".join(hit)[:40]
    return False, None, None


_FIRST_LINE_REFUSAL = ("확인되지 않", "확인하지 못")


def _refusal(answer):
    if any(pattern in answer for pattern in ("모르겠", "모릅니다", "알 수 없", "찾지 못", "찾을 수 없", "정보가 없", "없습니다", "없음", "없다", "확인할 수 없")):
        return True
    # v2 답변 형식이 지시하는 '확인되지 않음' 표현은 첫 줄에 있을 때만 거절로 본다.
    # 꼬리말('※ 확인되지 않은 항목: ...')만 붙이고 내용을 지어낸 답변이 통과하지 않게 하기 위해서다.
    first_line = next((line for line in str(answer).splitlines() if line.strip()), "")
    return any(pattern in first_line for pattern in _FIRST_LINE_REFUSAL)


def judge_answer(question, result, selected_names):
    answer = str(result.get("answer", ""))
    expected = list(map(str, question.get("expected", [])))
    no_answer = bool(question.get("no_answer", False))
    expected_seeds = set(map(str, question.get("seed_entities", [])))
    selected = set(map(str, selected_names))
    sub = result.get("subgraph", {})
    nodes = sub.get("nodes", [])
    haystack = " ".join(str(node.get("name", "")) + " " + " ".join(map(str, (node.get("props") or {}).values())) for node in nodes)
    search_expected = [value for value in expected if _answer_has(haystack, value)]
    matches = []
    for value in expected:
        matched, kind, evidence = _value_match(answer, value, question.get("type", ""))
        matches.append({"value": value, "matched": matched, "match_kind": kind, "evidence_span": evidence})
    strict_included = sum(_answer_has(answer, value) for value in expected)
    included = sum(item["matched"] for item in matches)
    seed_hit = bool(expected_seeds & selected) if expected_seeds else None
    if no_answer:
        classification = "no_answer_refused" if _refusal(answer) else "no_answer_answered"
    elif not nodes or (expected and not search_expected):
        classification = "search_miss"
    elif any(_answer_has(haystack, value) and not _value_match(answer, value, question.get("type", ""))[0] for value in expected):
        classification = "search_hit_answer_miss"
    else:
        classification = "search_hit_answer_hit" if nodes else "search_miss"
    return {
        "seed_hit": seed_hit,
        "expected_values": len(expected),
        "expected_values_in_answer": included,
        "expected_values_in_answer_strict": strict_included,
        "value_matches": matches,
        "expected_value_inclusion_rate": included / len(expected) if expected else None,
        "source_displayed": bool(result.get("sources")),
        "refusal": _refusal(answer),
        "classification": classification,
        "expected_values_in_subgraph": len(search_expected),
        "no_answer": no_answer,
        "no_answer_success": bool(_refusal(answer)) if no_answer else None,
    }


def _load_questions(path, limit):
    payload = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    questions = payload.get("questions", [])
    return questions[:max(0, limit)]


def rejudge_files(results_path, questions_path, output_path):
    qpath = Path(questions_path).expanduser().resolve()
    out = safe_tmp(output_path)
    if Path("/tmp").resolve() not in qpath.parents or ROOT in qpath.parents:
        raise ValueError("질문 JSON은 /tmp 아래에 있어야 합니다.")
    questions = json.loads(qpath.read_text(encoding="utf-8")).get("questions", [])
    qmap = {str(q.get("id")): q for q in questions}
    records = [json.loads(line) for line in Path(results_path).expanduser().resolve().read_text(encoding="utf-8").splitlines() if line.strip()]
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as stream:
        for record in records:
            question = qmap.get(str(record.get("id")), record.get("question", {}))
            judgement = judge_answer(question, {"answer": record.get("answer", ""), "sources": [None] * record.get("source_count", 0), "subgraph": {"nodes": []}}, record.get("selected_seed_names", []))
            record.update(judgement)
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return records


def _judge_cli():
    import argparse
    parser = argparse.ArgumentParser(description="Rejudge saved fp_chat answer results without DB or LLM")
    parser.add_argument("--results", required=True)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    records = rejudge_files(args.results, args.questions, args.output)
    print(f"재채점 문항: {len(records)}; 출력: {safe_tmp(args.output)}")
    return 0


def _redact_secret(value):
    secret = os.environ.get("OPENAI_API_KEY")
    if isinstance(value, dict):
        return {key: _redact_secret(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_secret(item) for item in value]
    if isinstance(value, str) and secret:
        return value.replace(secret, "[REDACTED]")
    return value


def run(args):
    qpath = Path(args.questions).expanduser().resolve()
    if Path("/tmp").resolve() not in qpath.parents or ROOT in qpath.parents:
        raise ValueError("질문 JSON은 /tmp 아래에 있어야 합니다.")
    questions = _load_questions(qpath, args.limit)
    out, summary = safe_tmp(args.output), safe_tmp(args.summary)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)
    if not args.execute:
        calls = len(questions) * 2
        tokens_in, tokens_out = calls * 1200, calls * 400
        cost = tokens_in * 0.10 / 1_000_000 + tokens_out * 0.50 / 1_000_000
        print(json.dumps({"mode": "dry-run", "question_count": len(questions),
                          "llm_call_estimate": calls, "estimated_cost_usd": round(cost, 8)}, ensure_ascii=False))
        return 0
    if not os.environ.get("DB_URL"):
        raise RuntimeError("DB_URL 환경 변수가 필요합니다. FP_DATABASE_URL 값을 사용자가 복사하세요.")
    if args.llm != "openai":
        raise ValueError("--execute에는 --llm openai가 필요합니다.")

    try:
        from ..openai_llm_patch import install, reset_usage, usage_totals, CostLimitExceeded
        from ..fp_chat_patch import apply as apply_db
    except ImportError:  # 스크립트식 실행: PYTHONPATH 에 chat/ 폴더 필요
        from openai_llm_patch import install, reset_usage, usage_totals, CostLimitExceeded
        from fp_chat_patch import apply as apply_db
    reset_usage()
    install(max_cost_usd=args.max_cost_usd, sleep=args.sleep)
    rag = apply_db("fp_chat")
    original_analyze, original_explore = rag.analyze, rag.explore
    by_type = {}
    errors = 0
    records = []
    with out.open("w", encoding="utf-8") as stream:
        for question in questions:
            started = time.perf_counter()
            capture = {"selected_names": [], "subgraph": None}
            def analyze(q, entities):
                result = original_analyze(q, entities)
                result.hops = args.hops
                capture["selected_names"] = list(result.entities)
                return result
            def explore(analysis):
                sub = original_explore(analysis)
                capture["subgraph"] = sub
                return sub
            rag.analyze, rag.explore = analyze, explore
            try:
                result = rag.answer(question["question"])
                judgement = judge_answer(question, result, capture["selected_names"])
                sub = result.get("subgraph", {})
                totals = usage_totals()
                record = {"id": question.get("id"), "type": question.get("type"), "question": question,
                          "selected_seed_names": capture["selected_names"], "subgraph_node_count": len(sub.get("nodes", [])),
                          "retrieved_node_ids": list(dict.fromkeys(str(n.get("id")) for n in sub.get("nodes", []) if n.get("id")))[:200],
                          "subgraph_edge_count": len(sub.get("edges", [])), "answer": result.get("answer", ""),
                          "source_count": len(result.get("sources", [])), "elapsed_seconds": time.perf_counter() - started,
                          **totals, **judgement, "status": "ok"}
                errors = 0
            except CostLimitExceeded:
                errors += 1
                sub = capture.get("subgraph") or {"nodes": [], "edges": []}
                totals = usage_totals()
                record = {"id": question.get("id"), "type": question.get("type"), "question": question,
                          "selected_seed_names": capture["selected_names"], "subgraph_node_count": len(sub["nodes"]),
                          "retrieved_node_ids": list(dict.fromkeys(str(n.get("id")) for n in sub.get("nodes", []) if n.get("id")))[:200],
                          "subgraph_edge_count": len(sub["edges"]), "answer": "", "source_count": 0,
                          "elapsed_seconds": time.perf_counter() - started, **totals, "status": "error",
                          "error_type": "CostLimitExceeded", "error": "누적 비용 상한 초과"}
            except Exception as exc:
                errors += 1
                sub = capture.get("subgraph") or {"nodes": [], "edges": []}
                totals = usage_totals()
                record = {"id": question.get("id"), "type": question.get("type"), "question": question,
                          "selected_seed_names": capture["selected_names"], "subgraph_node_count": len(sub["nodes"]),
                          "retrieved_node_ids": list(dict.fromkeys(str(n.get("id")) for n in sub.get("nodes", []) if n.get("id")))[:200],
                          "subgraph_edge_count": len(sub["edges"]), "answer": "", "source_count": 0,
                          "elapsed_seconds": time.perf_counter() - started, **totals, "status": "error",
                          "error_type": type(exc).__name__, "error": "질문 처리 오류"}
            finally:
                rag.analyze, rag.explore = original_analyze, original_explore
            records.append(record)
            stream.write(json.dumps(_redact_secret(record), ensure_ascii=False) + "\n")
            stream.flush()
            bucket = by_type.setdefault(record.get("type") or "(유형 없음)", {"questions": 0, "seed_hits": 0, "seed_expected": 0,
                "expected_included": 0, "expected_total": 0, "sources": 0, "refusals": 0, "search_hit_answer_miss": 0,
                "search_miss": 0, "no_answer_questions": 0, "no_answer_refusals": 0, "errors": 0})
            bucket["questions"] += 1
            bucket["errors"] += record["status"] == "error"
            if record["status"] == "ok":
                bucket["seed_hits"] += bool(record.get("seed_hit"))
                bucket["seed_expected"] += record.get("seed_hit") is not None
                bucket["expected_included"] += record["expected_values_in_answer"]
                bucket["expected_total"] += record["expected_values"]
                bucket["sources"] += record["source_displayed"]
                bucket["refusals"] += record["refusal"]
                if record.get("no_answer"):
                    bucket["no_answer_questions"] += 1
                    bucket["no_answer_refusals"] += bool(record.get("no_answer_success"))
                bucket[record["classification"]] = bucket.get(record["classification"], 0) + 1
            if errors >= 3:
                break
            if record.get("error_type") == "CostLimitExceeded":
                break
    totals = usage_totals()
    for row in by_type.values():
        row['no_answer_refusal_rate'] = row['no_answer_refusals'] / row['no_answer_questions'] if row['no_answer_questions'] else None
    no_answer_total = sum(r['no_answer_questions'] for r in by_type.values())
    no_answer_refused = sum(r['no_answer_refusals'] for r in by_type.values())
    aggregate = {"questions": len(records), "errors": sum(r["status"] == "error" for r in records), **totals}
    aggregate['no_answer_questions'] = no_answer_total
    aggregate['no_answer_refusals'] = no_answer_refused
    aggregate['no_answer_refusal_rate'] = no_answer_refused / no_answer_total if no_answer_total else None
    payload = {"overall": aggregate, "by_type": by_type}
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("유형\t문항\t시드 적중\t정답 포함\t엄격 규칙\t출처\t거절\t정답없음 거절률\t검색 성공·답변 실패\t검색 실패\t오류")
    for kind, row in sorted(by_type.items()):
        refusal_rate = f"{row['no_answer_refusals']}/{row['no_answer_questions']}" if row['no_answer_questions'] else "-"
        strict = sum(r.get("expected_values_in_answer_strict", 0) for r in records if r.get("type") == kind and r.get("status") == "ok")
        total = sum(r.get("expected_values", 0) for r in records if r.get("type") == kind and r.get("status") == "ok")
        print(f"{kind}\t{row['questions']}\t{row['seed_hits']}/{row['seed_expected']}\t{row['expected_included']}/{row['expected_total']}\t{strict}/{total}\t{row['sources']}\t{row['refusals']}\t{refusal_rate}\t{row.get('search_hit_answer_miss',0)}\t{row.get('search_miss',0)}\t{row['errors']}")
    print(f"전체\t{aggregate['questions']}\t토큰 {totals['prompt_tokens'] + totals['completion_tokens']}\t비용 ${totals['cost_usd']:.8f}")
    print(json.dumps({"output": str(out), "summary": str(summary), "totals": aggregate}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_judge_cli())
