import json
import sys
import types
from pathlib import Path

CHAT = Path(__file__).resolve().parents[1] / "file_pipeline" / "chat"
sys.path.insert(0, str(CHAT))


import pytest


@pytest.fixture(autouse=True)
def _restore_llm_module():
    """install() 이 sys.modules['llm'] 에 넣는 대체 모듈이 다른 테스트로 새지 않게 원상 복구한다."""
    before = sys.modules.get("llm")
    patch_mod = sys.modules.get("openai_llm_patch")
    yield
    if before is None:
        sys.modules.pop("llm", None)
    else:
        sys.modules["llm"] = before
    if patch_mod is not None:
        patch_mod._ORIGINALS = None


class _Resp:
    def __init__(self, text, finish="stop", completion=10, reasoning=3):
        message = types.SimpleNamespace(content=text)
        self.choices = [types.SimpleNamespace(message=message, finish_reason=finish)]
        self.usage = types.SimpleNamespace(prompt_tokens=100, completion_tokens=completion,
                                           completion_tokens_details=types.SimpleNamespace(reasoning_tokens=reasoning))


class _Client:
    def __init__(self, text="{}", finish="stop"):
        self.calls = []
        outer = self
        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return _Resp(text, finish)
        self.chat = types.SimpleNamespace(completions=_Completions())


def test_small_request_is_raised_to_minimum_budget_and_logged(tmp_path, monkeypatch):
    import openai_llm_patch as patch
    monkeypatch.delitem(sys.modules, "llm", raising=False)
    log = Path("/tmp") / f"fp-llm-call-log-test-{tmp_path.name}.jsonl"
    monkeypatch.setenv("FP_LLM_CALL_LOG", str(log))
    client = _Client('{"entities": []}', finish="length")
    llm = patch.install(client=client, sleep=0, min_completion_tokens=2000)
    patch.reset_usage()
    assert llm.complete("s", "u", max_tokens=400) == '{"entities": []}'
    assert client.calls[0]["max_completion_tokens"] == 2000 and "temperature" not in client.calls[0]
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["finish_reason"] == "length" and rows[0]["reasoning_tokens"] == 3
    assert rows[0]["requested_max"] == 2000 and "api" not in json.dumps(rows[0]).lower()
    log.unlink()


def test_log_is_not_written_outside_tmp_or_when_unset(tmp_path, monkeypatch):
    import openai_llm_patch as patch
    monkeypatch.delitem(sys.modules, "llm", raising=False)
    inside_repo = Path(__file__).resolve().parent / "should-not-exist.jsonl"
    monkeypatch.setenv("FP_LLM_CALL_LOG", str(inside_repo))
    llm = patch.install(client=_Client(), sleep=0)
    llm.complete("s", "u")
    assert not inside_repo.exists()
    monkeypatch.delenv("FP_LLM_CALL_LOG")
    llm.complete("s", "u")


def test_normalize_entities_strips_only_label_suffix():
    import openai_llm_patch as patch
    raw = '앞 {"entities": ["A카드(Card)", "혜택X(Benefit)", "CLUB X(클럽 X)카드", "Y(Limit) ", 3], "hops": 1} 뒤'
    data = json.loads(patch.normalize_entities(raw))
    assert data["entities"] == ["A카드", "혜택X", "CLUB X(클럽 X)카드", "Y", 3] and data["hops"] == 1
    assert patch.normalize_entities("텍스트만") == "텍스트만"
    assert patch.normalize_entities('{"answer": "A(Card)"}') == '{"answer": "A(Card)"}'
    assert patch.normalize_entities("{깨진 json}") == "{깨진 json}"


def test_complete_returns_normalized_entities(monkeypatch):
    import openai_llm_patch as patch
    monkeypatch.delitem(sys.modules, "llm", raising=False)
    monkeypatch.delenv("FP_LLM_CALL_LOG", raising=False)
    llm = patch.install(client=_Client('{"entities": ["A카드(Card)"], "hops": 1}'), sleep=0)
    assert json.loads(llm.complete("s", "u"))["entities"] == ["A카드"]
