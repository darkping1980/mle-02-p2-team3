import importlib.util
import json
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[4]
CHAT = ROOT / "src/card_benefit/payment_card/file_pipeline/chat"


def load(name):
    sys.path.insert(0, str(CHAT))
    spec = importlib.util.spec_from_file_location(f"answer_check_test_{name}", next((p for p in (next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py"), CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py", CHAT / "retrieval" / f"{name}.py", CHAT / "answer" / f"{name}.py") if p.exists()), next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def sample_graph():
    return {
        "nodes": [
            {"id": "card1", "name": "합성 카드", "label": "Card", "props": {}},
            {"id": "benefit1", "name": "커피 적립", "label": "Benefit", "props": {"source_text": "월 1만원 적립"}},
            {"id": "limit1", "name": "월 한도", "label": "Limit", "props": {"source_text": "10,000원"}},
            {"id": "benefit2", "name": "교통 할인", "label": "Benefit", "props": {"source_text": "20% 할인"}},
            {"id": "limit2", "name": "교통 한도", "label": "Limit", "props": {"source_text": "월 1만원"}},
            {"id": "orphan", "name": "기타 조건", "label": "Condition", "props": {"source_text": "전월 30만원"}},
        ],
        "edges": [
            {"source": "card1", "target": "benefit1", "type": "OFFERS"},
            {"source": "benefit1", "target": "limit1", "type": "HAS_LIMIT"},
            {"source": "benefit2", "target": "limit2", "type": "HAS_LIMIT"},
        ],
    }


def test_scoped_numbers_classify_local_elsewhere_and_ungrounded():
    check = load("answer_check")
    result = check.check_answer_numbers("1만원, 20%, 99만원", sample_graph(), {"benefit1"})
    assert [item["raw"] for item in result["scoped_grounded"]] == ["1만원"]
    assert [item["raw"] for item in result["elsewhere_only"]] == ["20%"]
    assert [item["raw"] for item in result["ungrounded"]] == ["99만원"]
    assert result["counts"]["elsewhere_only"] == 1


def test_scope_unknown_reports_only_whole_union_results():
    check = load("answer_check")
    result = check.check_answer_numbers("20%, 99만원", sample_graph())
    assert result["scope_unknown"] is True
    assert result["whole_subgraph_grounded"] == [{"raw": "20%", "value": 20.0, "unit": "%", "kind": "percent"}]
    assert result["scoped_grounded"] == []
    assert result["elsewhere_only"] == []
    assert [item["raw"] for item in result["ungrounded"]] == ["99만원"]


def test_normalizes_korean_currency_units_and_excludes_dates_and_page_numbers():
    check = load("answer_check")
    assert [(item["value"], item["kind"]) for item in check.numbers_in("1만원 10000원 10,000원 2회 3%")] == [
        (10000, "won"), (10000, "won"), (10000, "won"), (2, "count"), (3.0, "percent")
    ]
    values = check.numbers_in("1만원 3회 3%")
    assert isinstance(values[1]["value"], int)
    assert isinstance(values[2]["value"], float)
    assert check.numbers_in("2025년 4월 3일, p. 7, 8페이지, 페이지 9") == []
    grounded = check.check_answer_numbers("10,000원", sample_graph(), {"benefit1"})
    assert grounded["counts"]["scoped_grounded"] == 1


def test_scope_nodes_respects_edge_direction():
    check = load("answer_check")
    graph = sample_graph()
    graph["nodes"].extend([
        {"id": "condition1", "label": "Condition"},
        {"id": "target1", "label": "Target"},
        {"id": "excluded1", "label": "Target"},
        {"id": "reverse1", "label": "Condition"},
    ])
    graph["edges"].extend([
        {"source": "benefit1", "target": "condition1", "type": "HAS_CONDITION"},
        {"source": "benefit1", "target": "target1", "type": "APPLIES_TO"},
        {"source": "benefit1", "target": "excluded1", "type": "EXCLUDES"},
        {"source": "reverse1", "target": "benefit1", "type": "HAS_CONDITION"},
    ])
    assert check.scope_nodes(graph, {"benefit1"}) == {
        "card1", "benefit1", "limit1", "condition1", "target1", "excluded1"
    }


def test_selected_entities_resolve_benefit_and_card_offers():
    patch = load("fp_chat_patch")
    graph = sample_graph()
    assert patch._selected_benefit_ids(graph, ["커피 적립"]) == {"benefit1"}
    assert patch._selected_benefit_ids(graph, ["합성 카드"]) == {"benefit1"}


def test_qa_log_records_number_check_without_changing_legacy_ungrounded_numbers(monkeypatch):
    qa = load("qa_log")
    monkeypatch.delenv("FP_QA_LOG", raising=False)
    record = qa.build_record(
        question="합성 질문", answer="1만원과 20%", result={"subgraph": sample_graph()},
        number_check={"scope_unknown": False, "counts": {"scoped_grounded": 1, "elsewhere_only": 1, "ungrounded": 0},
                      "elsewhere_only": [{"raw": "20%", "value": 20.0, "kind": "percent"}]},
    )
    assert record["ungrounded_numbers"] == []
    assert record["number_check"]["counts"]["elsewhere_only"] == 1
    assert record["number_check"]["elsewhere_only"][0]["raw"] == "20%"


def test_wrapper_check_failure_keeps_answer_and_does_not_log_connection_strings(monkeypatch, capsys):
    patch = load("fp_chat_patch")
    qa = load("qa_log")
    monkeypatch.setitem(sys.modules, "qa_log", qa)
    monkeypatch.setitem(sys.modules, "answer_eval", load("answer_eval"))
    monkeypatch.setitem(sys.modules, "answer.answer_eval", sys.modules["answer_eval"])
    captured = []
    original_build = qa.build_record

    def capture_record(**kwargs):
        record = original_build(**kwargs)
        captured.append(record)
        return record

    monkeypatch.setattr(qa, "build_record", capture_record)
    db = types.SimpleNamespace(run_query=lambda *args, **kwargs: [])
    analysis = types.SimpleNamespace(entities=["커피 적립"], hops=1, intent="합성")
    rag = types.SimpleNamespace(ANSWER_SYSTEM="synthetic")
    graph = sample_graph()
    graph["nodes"][1]["props"]["connection_string"] = "postgres://synthetic-secret"

    def original_answer(question, history=None):
        rag.list_entities(question)
        rag.analyze(question, [])
        subgraph = rag.explore(None)
        return {"answer": "원래 답변 1만원", "subgraph": subgraph, "sources": [], "steps": []}

    rag.answer = original_answer
    rag.list_entities = lambda *args: []
    rag.analyze = lambda *args: analysis
    rag.explore = lambda *args: graph
    rag.generate_stream = lambda *args: iter([])
    monkeypatch.setattr(patch, "_load_modules", lambda: db)
    monkeypatch.setattr("importlib.reload", lambda module: module)
    monkeypatch.setitem(sys.modules, "db", db)
    monkeypatch.setitem(sys.modules, "rag", rag)
    monkeypatch.setenv("FP_DB_POOL", "0")
    monkeypatch.setenv("FP_QA_LOG", "/tmp/fake-qa.jsonl")
    monkeypatch.delenv("FP_ANSWER_FORMAT", raising=False)
    check_module = load("answer_check")
    monkeypatch.setattr(check_module, "check_answer_numbers", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setitem(sys.modules, "answer_check", check_module)
    monkeypatch.setitem(sys.modules, "answer.answer_check", check_module)

    patched = patch.apply()
    result = patched.answer("합성 질문")
    assert result["answer"] == "원래 답변 1만원"
    assert captured[0]["number_check"] == {"error": "check_failed"}
    serialized = json.dumps(captured[0], ensure_ascii=False)
    assert "postgres://synthetic-secret" not in serialized
    assert "FP_NUMBER_CHECK_ERROR:check_failed" in capsys.readouterr().err
    patch.restore()
