from __future__ import annotations

from pathlib import Path
import sys
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "file_pipeline"))


def test_render_uses_distinct_widget_and_session_state_keys(monkeypatch):
    from streamlit.testing.v1 import AppTest

    monkeypatch.delenv("FP_QA_LOG", raising=False)

    fake_rag = types.ModuleType("rag")
    fake_rag.list_entities = lambda: []
    fake_rag.analyze = lambda question, entities: None
    fake_rag.explore = lambda analysis: {"nodes": [], "edges": [], "seeds": []}
    fake_rag.generate_stream = lambda question, subgraph, history: iter(())
    fake_llm = types.ModuleType("llm")
    fake_llm.usage_totals = lambda: {"prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0}
    monkeypatch.setitem(sys.modules, "rag", fake_rag)
    monkeypatch.setitem(sys.modules, "llm", fake_llm)

    def app():
        from chat.ui.app_v2 import render

        render(key_prefix="a")
        render(key_prefix="b")

    at = AppTest.from_function(app).run()

    assert not at.exception
    widget_keys = {
        widget.key
        for widget in (*at.button, *at.toggle, *at.chat_input)
        if widget.key is not None
    }
    assert {
        "a_new_chat",
        "b_new_chat",
        "a_developer_mode",
        "b_developer_mode",
        "a_chat_input",
        "b_chat_input",
        "a_example_0",
        "b_example_0",
    } <= widget_keys
    assert len(widget_keys) == len(
        [widget.key for widget in (*at.button, *at.toggle, *at.chat_input) if widget.key is not None]
    )

    for name in ("conversations", "current", "developer_mode"):
        assert f"a_{name}" in at.session_state
        assert f"b_{name}" in at.session_state
    assert at.session_state["a_conversations"] == {}
    assert at.session_state["b_conversations"] == {}
    at.session_state["a_conversations"]["only-a"] = {"turns": []}
    assert "only-a" not in at.session_state["b_conversations"]
    assert at.session_state["a_current"] is None
    assert at.session_state["b_current"] is None
