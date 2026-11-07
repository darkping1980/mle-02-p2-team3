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
    chat_dir = str(CHAT)
    if chat_dir not in sys.path:
        sys.path.insert(0, chat_dir)
    spec = importlib.util.spec_from_file_location(f"fact_judge_test_{name}", next((p for p in (next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py"), CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py", CHAT / "retrieval" / f"{name}.py", CHAT / "answer" / f"{name}.py") if p.exists()), next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.responses.pop(0)
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content=content))],
            usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=10),
        )


def record(answer="정기 납부로 결제해야 혜택을 받아요.", expected="자동 결제로 혜택 제공", no_answer=False):
    return {"id": "s1", "answer": answer, "question": {"question": "어떤 결제 방식인가요?", "expected": [expected], "no_answer": no_answer, "issuer": "sample", "type": "condition"}}


def test_rule_match_skips_llm(tmp_path):
    judge = load("fact_judge")
    client = FakeClient([])
    result, _ = judge.judge_records([record("주차 비용 할인", "주차 비용")], client=client, cache_path=tmp_path / "cache.json")
    assert result[0]["facts"][0]["verdict"] == "match_rule"
    assert client.calls == []


def test_llm_json_parsing_and_invalid_json_handling(tmp_path):
    judge = load("fact_judge")
    client = FakeClient(['{"verdict":"correct","reason":"같은 의미"}', "not json"])
    rows = [record(), record(answer="말씀하신 혜택을 확인하세요.", expected="특정 결제 조건")]
    result, _ = judge.judge_records(rows, client=client, cache_path=tmp_path / "cache.json")
    assert result[0]["facts"][0]["verdict"] == "correct"
    assert result[1]["facts"][0]["verdict"] == "incorrect"
    assert result[1]["facts"][0]["reason"] == "invalid_json"
    assert all("temperature" not in call and call["max_completion_tokens"] >= 2000 for call in client.calls)


def test_no_answer_uses_refusal_without_llm(tmp_path):
    judge = load("fact_judge")
    client = FakeClient([])
    rows = [record(answer="관련 정보가 없습니다.", expected="", no_answer=True)]
    result, _ = judge.judge_records(rows, client=client, cache_path=tmp_path / "cache.json")
    assert result[0]["abstained"] is True
    assert result[0]["all_facts_correct"] is True
    assert client.calls == []


def test_dry_run_does_not_create_client(tmp_path, monkeypatch, capsys):
    judge = load("fact_judge")
    monkeypatch.setattr(judge, "_create_client", lambda: pytest.fail("client created in dry run"))
    source = tmp_path / "in.jsonl"
    source.write_text(json.dumps(record()) + "\n", encoding="utf-8")
    assert judge.main(["--input", str(source), "--output", "/tmp/fact-out.jsonl", "--summary", "/tmp/fact-summary.json"]) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["mode"] == "dry-run" and dry["llm_call_estimate"] == 1


def test_cache_reuses_llm_decision(tmp_path):
    judge = load("fact_judge")
    cache = tmp_path / "cache.json"
    first = FakeClient(['{"verdict":"correct","reason":"동일 의미"}'])
    second = FakeClient([])
    assert judge.judge_records([record()], client=first, cache_path=cache)[0][0]["facts"][0]["verdict"] == "correct"
    assert judge.judge_records([record()], client=second, cache_path=cache)[0][0]["facts"][0]["verdict"] == "correct"
    assert len(first.calls) == 1 and second.calls == []


def test_cost_limit_stops_before_call(tmp_path):
    judge = load("fact_judge")
    client = FakeClient(['{"verdict":"correct","reason":"같은 뜻"}'])
    with pytest.raises(judge.CostLimitExceeded):
        judge.judge_records([record(), record(answer="정기 납부 방식입니다.", expected="정기 결제만 가능")], client=client,
                            cache_path=tmp_path / "cache.json", max_cost_usd=0)
    assert client.calls == []
