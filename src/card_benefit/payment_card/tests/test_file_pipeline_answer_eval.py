import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest

CHAT = Path(__file__).resolve().parents[1] / "file_pipeline" / "chat"


@pytest.fixture(autouse=True)
def _restore_chatbot_modules():
    names = ("db", "rag", "llm")
    before = {name: sys.modules.get(name) for name in names}
    yield
    for name in names:
        module = before[name]
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def load(name):
    spec = importlib.util.spec_from_file_location(f"answer_eval_test_{name}", next((p for p in (next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py"), CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py", CHAT / "retrieval" / f"{name}.py", CHAT / "answer" / f"{name}.py") if p.exists()), next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_openai_patch_injects_llm_module_without_anthropic(monkeypatch):
    import importlib.util
    patch = load("openai_llm_patch")
    monkeypatch.delitem(sys.modules, "llm", raising=False)
    fake = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=lambda **kw: types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="ok"))], usage=types.SimpleNamespace(prompt_tokens=3, completion_tokens=2)))))
    llm = patch.install(client=fake)
    assert sys.modules["llm"] is llm
    assert llm.complete("s", "u") == "ok"
    assert patch.usage_totals() == {"prompt_tokens": 3, "completion_tokens": 2, "cost_usd": 0.0000013}
    monkeypatch.setitem(sys.modules, "db", types.SimpleNamespace(NODES="fp_chat.nodes", EDGES="fp_chat.edges"))
    monkeypatch.setitem(sys.modules, "timing", types.ModuleType("timing"))
    spec = importlib.util.spec_from_file_location("rag_without_anthropic", CHAT.parents[3] / "graphrag_chatbot" / "rag.py")
    rag = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = rag
    spec.loader.exec_module(rag)
    assert callable(rag.answer)


def test_openai_patch_request_arguments_and_stream_fallback(monkeypatch):
    patch = load("openai_llm_patch")
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        if kwargs.get("stream"):
            raise RuntimeError("unsupported stream options")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="whole"))], usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))
    fake = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
    llm = patch.install(client=fake)
    assert list(llm.stream("s", [{"role": "user", "content": "q"}])) == ["whole"]
    assert "max_completion_tokens" in calls[0] and "max_tokens" not in calls[0]
    assert "temperature" not in calls[0]
    assert calls[0]["stream_options"] == {"include_usage": True}


def test_answer_metrics_normalize_refusal_and_classification():
    answer_eval = load("answer_eval")
    assert answer_eval.judge_answer(
        {"expected": ["₩20,000", "월", "해외 가맹점"], "seed_entities": ["가나다 카드"]},
        {"answer": "모르겠습니다. 월 20000원", "sources": [], "subgraph": {"nodes": [{"name": "가나다 카드", "props": {"amount": 20000, "target": "해외 가맹점"}}]}},
        ["가나다 카드"],
    )["classification"] == "search_hit_answer_miss"
    refused = answer_eval.judge_answer({"expected": ["월"], "seed_entities": ["없음"]}, {"answer": "관련 정보가 없습니다", "sources": [], "subgraph": {"nodes": []}}, [])
    assert refused["refusal"] is True
    assert refused["classification"] == "search_miss"
    no_answer = answer_eval.judge_answer({"no_answer": True}, {"answer": "정보가 없습니다", "subgraph": {"nodes": []}}, [])
    assert no_answer["no_answer_success"] is True and no_answer["expected_values"] == 0


def test_refusal_recognizes_answer_format_v2_phrase_only_on_first_line():
    # v2 답변 형식이 지시하는 '확인되지 않음' 표현이 거절로 인식되어야 한다(H1 에서 정답 없음 12회 중 9회를 놓쳤다).
    answer_eval = load("answer_eval")
    assert answer_eval._refusal("반려동물호텔 혜택은 확인되지 않음.\n※ 확인되지 않은 항목: 반려동물호텔")
    assert answer_eval._refusal("그래프 근거로는 발렛파킹 여부가 확인되지 않습니다.")
    # 꼬리말에만 있는 표현은 거절이 아니다(내용을 지어낸 답변이 통과하면 안 된다).
    assert not answer_eval._refusal("캠핑장은 연 12회 무료입니다.\n\n※ 확인되지 않은 항목: 이용 기간")
    # 기존 규칙은 그대로 동작한다.
    assert answer_eval._refusal("정보가 없습니다")
    assert not answer_eval._refusal("월 30만원까지 할인됩니다.")


def test_dry_run_does_not_touch_db_or_openai(tmp_path, monkeypatch, capsys):
    run = load("run_eval")
    qfile = Path("/tmp/fp-answer-eval-dry-test.json")
    qfile.write_text(json.dumps({"questions": [{"id": "q1", "question": "synthetic", "expected": ["x"]}]}))
    try:
        assert run.main([str(qfile), "--mode", "answer", "--llm", "openai"]) == 0
        assert json.loads(capsys.readouterr().out)["question_count"] == 1
    finally:
        qfile.unlink(missing_ok=True)


def test_output_repo_guard():
    answer_eval = load("answer_eval")
    try:
        answer_eval.safe_tmp(Path(__file__))
    except ValueError:
        return
    assert False, "repository output path was accepted"


def test_openai_cost_limit_stops_and_redacts_key(monkeypatch, capsys):
    patch = load("openai_llm_patch")
    key = "synthetic-secret-never-print"
    monkeypatch.setenv("OPENAI_API_KEY", key)
    made = []
    def create(**kwargs):
        made.append(kwargs)
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="safe"))], usage=types.SimpleNamespace(prompt_tokens=1000000, completion_tokens=0))
    fake = types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=create)))
    patch.reset_usage()
    patch.install(client=fake, max_cost_usd=0.01)
    try:
        sys.modules["llm"].complete("s", "u")
    except patch.CostLimitExceeded:
        pass
    assert len(made) == 1
    assert key not in capsys.readouterr().out
    assert key not in json.dumps(patch.usage_totals())


def test_execute_with_fake_chatbot_db_and_openai_modules(tmp_path, monkeypatch, capsys):
    import argparse
    answer_eval = load("answer_eval")
    monkeypatch.setenv("DB_URL", "synthetic-db-url")
    secret = "synthetic-openai-key-never-write"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    qfile = Path("/tmp/fp-answer-execute-fake.json")
    output = Path("/tmp/fp-answer-execute-fake.jsonl")
    summary = Path("/tmp/fp-answer-execute-fake-summary.json")
    qfile.write_text(json.dumps({"questions": [{"id": "s1", "type": "synthetic", "question": "synthetic?", "seed_entities": ["synthetic node"], "expected": ["20,000"]}]}))
    fake_db = types.SimpleNamespace(run_query=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fake DB should not query")))
    monkeypatch.setitem(sys.modules, "db", fake_db)
    class Analysis:
        entities = ["synthetic node"]
        hops = 1
    rag = types.SimpleNamespace()
    rag.analyze = lambda question, entities: Analysis()
    rag.explore = lambda analysis: {"nodes": [{"id": "1", "name": "synthetic node", "label": "Limit", "props": {"amount": 20000}}], "edges": [], "seeds": ["1"]}
    rag.answer = lambda question: {"answer": "20,000 won", "sources": [{"title": "synthetic"}], "subgraph": rag.explore(rag.analyze(question, []))}
    monkeypatch.setitem(sys.modules, "fp_chat_patch", types.SimpleNamespace(apply=lambda schema: rag))
    fake_llm_patch = types.ModuleType("openai_llm_patch")
    fake_llm_patch.CostLimitExceeded = type("CostLimitExceeded", (BaseException,), {})
    fake_llm_patch.install = lambda **kwargs: None
    fake_llm_patch.reset_usage = lambda: None
    fake_llm_patch.usage_totals = lambda: {"prompt_tokens": 7, "completion_tokens": 3, "cost_usd": 0.0000022}
    monkeypatch.setitem(sys.modules, "openai_llm_patch", fake_llm_patch)
    args = argparse.Namespace(questions=str(qfile), limit=1, output=str(output), summary=str(summary),
                              execute=True, llm="openai", max_cost_usd=0.10, sleep=0.0, hops=1)
    assert answer_eval.run(args) == 0
    row = json.loads(output.read_text().splitlines()[0])
    assert row["status"] == "ok" and row["selected_seed_names"] == ["synthetic node"]
    assert row["expected_values_in_answer"] == 1 and row["prompt_tokens"] == 7
    assert row["retrieved_node_ids"] == ["1"]
    stdout = capsys.readouterr().out
    assert "synthetic?" not in stdout
    assert secret not in stdout and secret not in output.read_text()
    qfile.unlink(missing_ok=True)
    output.unlink(missing_ok=True)
    summary.unlink(missing_ok=True)


def test_answer_value_match_rules():
    answer_eval = load("answer_eval")
    for expected, answer, kind in [("300000", "30만원", "number_unitless"), ("300000", "30만 원", "number_unitless"), ("1000000", "1,000,000원", "number_unitless"), ("30000", "3만 점", "number_unitless"), ("100000", "10만점", "number_unitless"), ("1000", "1천 원", "number_unitless"), ("3", "3회", "number_unitless")]:
        matched, actual_kind, _ = answer_eval._value_match(answer, expected, "benefit_limit")
        assert matched and actual_kind == kind, (expected, answer, actual_kind)
    assert not answer_eval._value_match("3%", "3회")[0]
    assert not answer_eval._value_match("2026년 10월 31일", "31일")[0]
    assert not answer_eval._value_match("hash 017b032712345678", "12345678")[0]
    assert answer_eval._value_match("문서 017b0327", "017b0327")[1] == "hash"
    assert answer_eval._value_match("카타르항공 최대 15% 할인", "카타르항공 할인")[1] == "name_partial"
    assert not answer_eval._value_match("네이버페이만", "네이버페이 혜택")[0]
    assert answer_eval._value_match("주차 비용 안내", "주차 비용")[1] == "exact"
    assert answer_eval._value_match("주차비용 안내", "주차 비용")[1] == "exact_normalized"
    # Conversions: Korean large units, punctuation separators, and equivalent units.
    for expected, answer in [("100000000", "1억원"), ("12000", "1.2만원"), ("2000", "2천원"), ("20000", "2 만원"), ("3000", "3,000원"), ("3", "3회"), ("15", "15%"), ("3500", "3.5천원")]:
        assert answer_eval._value_match(answer, expected, "benefit_limit")[0], (expected, answer)
    assert not answer_eval._value_match("3%", "3회", "benefit_limit")[0]
    assert not answer_eval._value_match("2026년 10월 31일", "10", "benefit_limit")[0]
    assert not answer_eval._value_match("2026년 10월 31일", "31", "benefit_limit")[0]
    assert not answer_eval._value_match("문서 017b032712345678", "12345678")[0]
    assert answer_eval._value_match("문서 017b032712345678", "017b0327deadbeef")[1] == "hash"
    assert answer_eval._value_match("카타르항공 최대 고객 프리미엄", "카타르항공 최대 고객 프리미엄 제공")[1] == "name_partial"
    assert not answer_eval._value_match("네이버페이만", "네이버페이 혜택")[0]


def test_judgement_preserves_strict_and_new_counts():
    answer_eval = load("answer_eval")
    row = answer_eval.judge_answer({"type": "benefit_condition", "expected": ["500000"]}, {"answer": "전월 실적 50만원 이상", "subgraph": {"nodes": []}}, [])
    assert row["expected_values_in_answer"] == 1
    assert row["expected_values_in_answer_strict"] == 0
    assert row["value_matches"][0]["match_kind"] == "number_unitless"


def test_rejudge_rejects_repository_output(tmp_path):
    answer_eval = load("answer_eval")
    q = Path("/tmp/fp-rejudge-synthetic-questions.json")
    q.write_text(json.dumps({"questions": []}))
    try:
        with pytest.raises(ValueError, match="출력은 저장소 밖"):
            answer_eval.rejudge_files("/tmp/no-such-results", q, Path(__file__))
    finally:
        q.unlink(missing_ok=True)
