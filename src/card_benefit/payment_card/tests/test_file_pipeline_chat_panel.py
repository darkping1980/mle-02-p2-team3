from __future__ import annotations

import ast
import importlib
import os
from pathlib import Path
import sys
import types


PANEL_NAME = "payment_card.file_pipeline.chat.panel"
CHAT_DIR = Path(__file__).resolve().parents[1] / "file_pipeline" / "chat"
RUN_SCRIPT = CHAT_DIR / "run_fp_chat_v2.py"


def _load_panel(monkeypatch):
    monkeypatch.delitem(sys.modules, PANEL_NAME, raising=False)
    panel = importlib.import_module(PANEL_NAME)
    monkeypatch.setattr(panel, "_BACKEND_PREPARED", False)
    return panel


def _stub_dependencies(monkeypatch, calls):
    for name in ("rag", "llm", "db"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))

    fp_chat_patch = types.ModuleType("fp_chat_patch")

    def apply():
        calls.append(("apply",))

    fp_chat_patch.apply = apply
    monkeypatch.setitem(sys.modules, "fp_chat_patch", fp_chat_patch)

    openai_llm_patch = types.ModuleType("openai_llm_patch")

    def install(**kwargs):
        calls.append(("install", kwargs))

    openai_llm_patch.install = install
    monkeypatch.setitem(sys.modules, "openai_llm_patch", openai_llm_patch)


def _set_missing_env_file(monkeypatch, tmp_path):
    missing_env = tmp_path / "does-not-exist.env"
    assert not missing_env.exists()
    monkeypatch.setenv("FP_CHAT_ENV_FILE", str(missing_env))


def test_import_has_no_path_environment_or_streamlit_side_effects(monkeypatch):
    import streamlit as st

    monkeypatch.delitem(sys.modules, PANEL_NAME, raising=False)

    def unexpected_streamlit_call(*args, **kwargs):
        raise AssertionError("panel import called Streamlit")

    for name in ("set_page_config", "error", "stop"):
        monkeypatch.setattr(st, name, unexpected_streamlit_call)

    before_path = list(sys.path)
    before_env = dict(os.environ)
    importlib.import_module(PANEL_NAME)

    assert sys.path == before_path
    assert dict(os.environ) == before_env


def test_prepare_backend_reports_missing_key_without_installing(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    panel = _load_panel(monkeypatch)
    _set_missing_env_file(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls = []
    _stub_dependencies(monkeypatch, calls)

    def app():
        from payment_card.file_pipeline.chat.panel import prepare_backend

        assert prepare_backend() is False

    result = AppTest.from_function(app).run()

    assert not result.exception
    assert any("OPENAI_API_KEY 환경 변수가 필요합니다." in error.value for error in result.error)
    assert calls == []
    assert panel._BACKEND_PREPARED is False


def test_prepare_backend_installs_and_applies_once_per_process(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    panel = _load_panel(monkeypatch)
    _set_missing_env_file(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-key")
    monkeypatch.setenv("FP_MAX_COST_USD", "0.42")
    monkeypatch.setenv("FP_LLM_SLEEP", "0.0")
    calls = []
    _stub_dependencies(monkeypatch, calls)

    def app():
        from payment_card.file_pipeline.chat.panel import prepare_backend

        assert prepare_backend() is True
        assert prepare_backend() is True

    result = AppTest.from_function(app).run()

    assert not result.exception
    assert calls == [
        ("install", {"max_cost_usd": 0.42, "sleep": 0.0}),
        ("apply",),
    ]
    assert panel._BACKEND_PREPARED is True


def test_render_delegates_only_after_successful_prepare(monkeypatch):
    panel = _load_panel(monkeypatch)
    calls = []
    ui_name = "payment_card.file_pipeline.chat.ui"
    screen_name = f"{ui_name}.app_v2"
    fake_ui = types.ModuleType(ui_name)
    fake_ui.__path__ = []
    fake_screen = types.ModuleType(screen_name)
    fake_screen.render = lambda *, key_prefix: calls.append(key_prefix)
    monkeypatch.setitem(sys.modules, ui_name, fake_ui)
    monkeypatch.setitem(sys.modules, screen_name, fake_screen)
    monkeypatch.setattr(panel, "prepare_backend", lambda: True)

    panel.render(key_prefix="x")
    assert calls == ["x"]

    monkeypatch.setattr(panel, "prepare_backend", lambda: False)
    panel.render(key_prefix="ignored")
    assert calls == ["x"]


def test_standalone_entrypoint_uses_panel_without_runpy(monkeypatch, tmp_path):
    from streamlit.testing.v1 import AppTest

    source = RUN_SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "runpy" not in source
    assert any(
        isinstance(node, ast.ImportFrom)
        and node.module == "payment_card.file_pipeline.chat.panel"
        and {alias.name for alias in node.names} >= {"prepare_backend", "render"}
        for node in ast.walk(tree)
    )
    assert 'render(key_prefix="v2")' in source

    panel = _load_panel(monkeypatch)
    _set_missing_env_file(monkeypatch, tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    calls = []
    _stub_dependencies(monkeypatch, calls)

    result = AppTest.from_file(str(RUN_SCRIPT)).run()

    assert not result.exception
    assert any("OPENAI_API_KEY 환경 변수가 필요합니다." in error.value for error in result.error)
    assert calls == []
    assert panel._BACKEND_PREPARED is False
