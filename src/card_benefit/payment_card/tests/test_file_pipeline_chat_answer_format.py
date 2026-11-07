import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest


CHAT = Path(__file__).resolve().parents[1] / "file_pipeline" / "chat"


def load(name):
    sys.path.insert(0, str(CHAT))
    spec = importlib.util.spec_from_file_location(f"answer_format_test_{name}", next((p for p in (next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py"), CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py", CHAT / "retrieval" / f"{name}.py", CHAT / "answer" / f"{name}.py") if p.exists()), next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_prompt_and_format_check_synthetic_cases():
    fmt = load("answer_format")
    assert "관계와 속성만" in fmt.ANSWER_SYSTEM_V2
    assert "추측하지 마세요" in fmt.ANSWER_SYSTEM_V2
    assert "확인되지 않음" in fmt.ANSWER_SYSTEM_V2
    assert "실적 구간 → 한도" in fmt.ANSWER_SYSTEM_V2
    report = fmt.check_answer_format("요약\n\n**[적립]**\n- 1% 적립\n  - 조건: 전월 30만원")
    assert report["bracket_label_count"] == 1
    assert report["bullet_count"] == 2
    assert report["single_paragraph"] is False
    assert report["longest_paragraph_length"] > 0
    assert fmt.check_answer_format("짧은 답")["single_paragraph"] is True


def test_answer_prompt_versions_and_selection(monkeypatch):
    fmt = load("answer_format")
    rule = "같은 대상(같은 호텔·가맹점·혜택)에 대해 근거에 서로 다른 수치(rate, amount, 한도)가 둘 이상 있으면 하나만 고르지 말고 모두 나열한다. 각 항목에 혜택 이름과 근거 쪽(속성 source_text 앞의 (p.N) 표시)을 붙여 어느 프로그램·조건의 수치인지 구분하고, 어느 것이 질문자에게 적용되는지 근거로 판단할 수 없으면 판단하지 말고 차이를 그대로 알린다."
    assert fmt.ANSWER_SYSTEM_V3.startswith(fmt.ANSWER_SYSTEM_V2)
    assert rule in fmt.ANSWER_SYSTEM_V3
    monkeypatch.delenv("FP_ANSWER_FORMAT", raising=False)
    assert fmt.select_answer_system() == fmt.ANSWER_SYSTEM_V2
    assert fmt.get_answer_format_version() == "v2"
    assert fmt.ANSWER_SYSTEM_V2 == fmt.select_answer_system()
    monkeypatch.setenv("FP_ANSWER_FORMAT", "v3")
    assert fmt.select_answer_system() == fmt.ANSWER_SYSTEM_V3
    assert fmt.get_answer_format_version() == "v3"
    monkeypatch.setenv("FP_ANSWER_FORMAT", "v2")
    assert fmt.select_answer_system() == fmt.ANSWER_SYSTEM_V2
    monkeypatch.setenv("FP_ANSWER_FORMAT", "invalid")
    assert fmt.select_answer_system() == fmt.ANSWER_SYSTEM_V2
    assert fmt.get_answer_format_version() == "v2"


def test_qa_record_numbers_path_and_noop(monkeypatch, tmp_path):
    qa = load("qa_log")
    monkeypatch.delenv("FP_QA_LOG", raising=False)
    record = qa.build_record(
        question="합성 질문", answer="월 5만원, 8%", result={"answer": "", "subgraph": {
            "nodes": [{"id": "n1", "name": "합성 카드", "props": {"한도": "5만원", "rate": "1%", "run_id": "r1"}}],
            "edges": []}, "selected_entities": ["합성 카드"]},
        latency_ms={"entities_db": 1}, usage={"prompt_tokens": 3, "completion_tokens": 4, "cost_usd": 0.001})
    assert record["selected_entities"] == ["합성 카드"]
    assert record["retrieved_node_ids"] == ["n1"]
    assert record["run_ids"] == ["r1"]
    assert record["prompt_tokens"] == 3
    assert qa.ungrounded_numbers("월 5만원, 8%", "한도 5만원") == ["8%"]
    assert qa.write_record(record) is False
    with pytest.raises(ValueError):
        qa.safe_tmp(CHAT / "outside.jsonl")
    local = Path("/tmp") / f"fp-qa-test-{record['id']}.jsonl"
    monkeypatch.setenv("FP_QA_LOG", str(local))
    assert qa.write_record(record)
    payload = json.loads(local.read_text(encoding="utf-8"))
    assert "DB_URL" not in payload and "connection_string" not in payload
    local.unlink()


def test_answer_format_toggle_restore_and_failure_does_not_block(monkeypatch, capsys):
    patch = load("fp_chat_patch")
    qa = load("qa_log")
    monkeypatch.setitem(sys.modules, "qa_log", qa)
    built = []
    original_build = qa.build_record
    def capture_record(**kwargs):
        value = original_build(**kwargs)
        built.append(value)
        return value
    monkeypatch.setattr(qa, "build_record", capture_record)
    original_prompt = "합성 레거시 프롬프트"
    queries = []
    def run_query(query, params=None):
        queries.append(query)
        if "public.fp_evidence" in query:
            raise RuntimeError("synthetic failure")
        return [{"name": "합성 카드", "label": "Card"}]
    db = types.SimpleNamespace(run_query=run_query)

    class Analysis:
        def __init__(self):
            self.entities, self.hops, self.intent = ["합성 카드"], 1, "합성"

    rag = types.SimpleNamespace(ANSWER_SYSTEM=original_prompt)
    def answer(question, history=None):
        rag.list_entities(question)
        rag.analyze(question, [])
        sub = rag.explore(None)
        return {"answer": "합성 답변 5만원", "subgraph": sub, "sources": [], "steps": []}
    rag.answer = answer
    rag.explore = lambda analysis: {"nodes": [{"id": "n1", "name": "합성", "label": "Benefit", "props": {"fp_id": "f1", "한도": "5만원"}}], "edges": [], "seeds": []}
    rag.generate_stream = lambda *args: iter(["답"])
    rag.list_entities = lambda *_: []
    rag.analyze = lambda *_: Analysis()
    monkeypatch.setitem(sys.modules, "db", db)
    monkeypatch.setitem(sys.modules, "rag", rag)
    monkeypatch.setattr(patch, "_load_modules", lambda: db)
    monkeypatch.setattr("importlib.reload", lambda module: module)
    monkeypatch.setenv("FP_DB_POOL", "0")
    monkeypatch.delenv("FP_QA_LOG", raising=False)
    monkeypatch.delenv("FP_ANSWER_FORMAT", raising=False)
    patched = patch.apply()
    assert "확인되지 않음" in patched.ANSWER_SYSTEM
    result = patched.answer("로그 없는 합성 질문")
    assert result["answer"] == "합성 답변 5만원"
    assert "selected_entities" not in result
    assert not any("public.fp_evidence" in query for query in queries)
    monkeypatch.setenv("FP_QA_LOG", "/tmp")
    result = patched.answer("로그 실패 합성 질문")
    assert result["answer"] == "합성 답변 5만원"
    assert built[0]["source_refs"] == []
    assert built[0]["source_refs_error"] == "source_refs_query_error"
    assert "FP_QA_LOG_ERROR:invalid_path" in capsys.readouterr().err
    monkeypatch.setenv("FP_ANSWER_FORMAT", "v3")
    patched = patch.apply()
    assert patched.ANSWER_SYSTEM.endswith("차이를 그대로 알린다.")
    patched.answer("V3 로그 선택 합성 질문")
    assert built[-1]["answer_format_version"] == "v3"
    monkeypatch.setenv("FP_ANSWER_FORMAT", "legacy")
    patched = patch.apply()
    assert patched.ANSWER_SYSTEM == original_prompt
    patch.restore()
    assert patched.ANSWER_SYSTEM == original_prompt
