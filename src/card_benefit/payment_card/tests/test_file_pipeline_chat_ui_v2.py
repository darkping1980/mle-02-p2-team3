from __future__ import annotations

import json
from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "file_pipeline"))

from chat.ui.ui_v2 import (
    EXAMPLE_QUESTIONS,
    build_analysis_question,
    build_compare_table,
    collect_sources,
    serialize_turn,
)


def test_build_analysis_question_adds_previous_entities_for_deixis():
    actual = build_analysis_question(
        "그 카드의 연회비는?",
        [{"question": "신세계 by JADE 카드 혜택은?", "answer": "..."}],
        ["신세계 by JADE 카드", "디지털 콘텐츠 할인"],
    )
    assert actual == "(이전 대화에서 다룬 대상: 신세계 by JADE 카드, 디지털 콘텐츠 할인)\n그 카드의 연회비는?"


def test_build_analysis_question_leaves_non_deictic_or_first_turn_unchanged():
    assert build_analysis_question("연회비가 얼마야?", [{"question": "이전 질문"}], ["카드"])
    assert build_analysis_question("연회비가 얼마야?", [{"question": "이전 질문"}], ["카드"]) == "연회비가 얼마야?"
    assert build_analysis_question("그 카드는?", [], ["카드"]) == "그 카드는?"


def test_collect_sources_includes_benefit_span_pages_documents_and_disclaimer():
    subgraph = {
        "nodes": [
            {"id": "b1", "label": "Benefit", "name": "디지털 콘텐츠 할인", "props": {
                "source_text": "월 1만원 할인", "source_text_pages": [3, 4], "source_text_truncated": False,
            }},
            {"id": "d1", "label": "Document", "name": "상품설명서", "props": {"sha256": "a" * 64}},
        ],
        "edges": [],
    }
    sources = collect_sources(subgraph, [{"doc_sha256": "a" * 64, "page_no": 3}])
    assert sources[0]["title"] == "디지털 콘텐츠 할인"
    assert sources[0]["text"] == "월 1만원 할인"
    assert sources[0]["pages"] == [3, 4]
    assert sources[1]["title"] == "문서 aaaaaaaa"
    assert sources[1]["pages"] == [3]
    assert any("원문 구간은 자동 추출 근거이며 사람 검수 전입니다" in s["text"] for s in sources)


def test_collect_sources_marks_missing_data_and_truncated_text():
    sources = collect_sources({"nodes": [
        {"id": "b", "label": "Benefit", "name": "혜택", "props": {"source_text": "근거 " * 200, "source_text_truncated": True}},
        {"id": "d", "label": "Document", "name": "상품설명서", "props": {}},
    ], "edges": []})
    benefit = sources[0]
    document = sources[1]
    assert len(benefit["text"]) <= 700
    assert benefit["truncated"] is True
    assert benefit["pages"] == "자료에서 확인하지 못함"
    assert document["title"] == "문서 자료에서 확인하지 못함"
    assert document["pages"] == "자료에서 확인하지 못함"
    assert any("원문 구간은 자동 추출 근거이며 사람 검수 전입니다" in s["text"] for s in sources)


def test_build_compare_table_returns_none_for_one_card_and_rows_for_two():
    nodes = [
        {"id": "c1", "label": "Card", "name": "하나 카드", "props": {}},
        {"id": "c2", "label": "Card", "name": "우리 카드", "props": {}},
        {"id": "b1", "label": "Benefit", "name": "커피 할인", "props": {}},
        {"id": "cnd", "label": "Condition", "name": "전월 실적", "props": {"text": "30만원 이상"}},
        {"id": "lim", "label": "Limit", "name": "월 한도", "props": {"text": "월 5천원"}},
        {"id": "exc", "label": "Target", "name": "상품권 제외", "props": {"text": "상품권 제외"}},
    ]
    edges = [
        {"source": "c1", "target": "b1", "type": "OFFERS"},
        {"source": "b1", "target": "cnd", "type": "HAS_CONDITION"},
        {"source": "b1", "target": "lim", "type": "HAS_LIMIT"},
        {"source": "b1", "target": "exc", "type": "EXCLUDES"},
    ]
    subgraph = {"nodes": nodes, "edges": edges}
    assert build_compare_table({"nodes": nodes[:1], "edges": []}) is None
    assert build_compare_table({**subgraph, "seeds": ["c1"]}) is None
    table = build_compare_table(subgraph)
    assert table["columns"] == ["카드", "혜택", "조건", "한도", "제외"]
    assert table["rows"] == [
        {"카드": "하나 카드", "혜택": "커피 할인", "조건": "30만원 이상", "한도": "월 5천원", "제외": "상품권 제외"},
        {"카드": "우리 카드", "혜택": "자료에서 확인하지 못함", "조건": "자료에서 확인하지 못함", "한도": "자료에서 확인하지 못함", "제외": "자료에서 확인하지 못함"},
    ]


def test_examples_and_turn_serialization_have_no_secrets_or_personal_data():
    assert 3 <= len(EXAMPLE_QUESTIONS) <= 4
    combined = " ".join(EXAMPLE_QUESTIONS)
    assert "신세계 by JADE" in combined
    assert "국민행복카드" in combined
    assert "OPENAI_API_KEY" not in combined
    assert "DB_URL" not in combined
    turn = {
        "question": "질문", "analysis_question": "분석 질문", "answer": "답변",
        "sources": [], "compare_table": None, "selected_entities": ["카드"], "latency_ms": {"total": 1.2},
    }
    encoded = serialize_turn(turn)
    assert json.loads(encoded) == turn


def test_streamlit_example_question_renders_answer_and_new_conversation_resets(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv("FP_QA_LOG", raising=False)

    fake_rag = types.ModuleType("rag")
    fake_rag.list_entities = lambda: [{"name": "합성 카드", "label": "Card"}]
    fake_rag.analyze = lambda question, entities: types.SimpleNamespace(
        entities=["합성 카드"], intent="합성", hops=1
    )
    fake_rag.explore = lambda analysis: {
        "nodes": [{"id": "b1", "label": "Benefit", "name": "합성 할인", "props": {
            "source_text": "합성 구간", "source_text_pages": [2],
        }}],
        "edges": [], "seeds": [],
    }
    fake_rag.generate_stream = lambda question, subgraph, history: iter(["합성 답변"])
    fake_llm = types.ModuleType("llm")
    fake_llm.usage_totals = lambda: {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0}
    monkeypatch.setitem(sys.modules, "rag", fake_rag)
    monkeypatch.setitem(sys.modules, "llm", fake_llm)

    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "file_pipeline" / "chat" / "ui" / "app_v2.py")).run()
    next(button for button in app.button if button.label.startswith("신세계 by JADE")).click().run()
    assert any("합성 답변" in str(element.value) for element in app.markdown)
    assert app.session_state["v2_current"] is not None
    next(button for button in app.button if button.label == "새 대화").click().run()
    assert app.session_state["v2_current"] is None
    assert any(button.label.startswith("신세계 by JADE") for button in app.button)
