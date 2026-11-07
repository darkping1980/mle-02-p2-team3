import importlib
import importlib.util
import json
from pathlib import Path
import sys
import types

import pytest


CHAT = Path(__file__).resolve().parents[1] / "file_pipeline" / "chat"


@pytest.fixture(autouse=True)
def _restore_chatbot_modules():
    names = ("db", "rag", "llm", "db_pool", "fp_chat_patch", "latency_bench", "psycopg_pool", "psycopg", "psycopg.rows")
    before = {name: sys.modules.get(name) for name in names}
    yield
    for name in names:
        module = before[name]
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


def load(name):
    spec = importlib.util.spec_from_file_location(f"db_pool_test_{name}", next((p for p in (next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py"), CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py", CHAT / "retrieval" / f"{name}.py", CHAT / "answer" / f"{name}.py") if p.exists()), next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeOperationalError(Exception):
    pass


def install_fake_pool(monkeypatch, failures=0):
    made = []

    class Connection:
        def __init__(self):
            self.calls = []
            self.closed = False

        def execute(self, query, params):
            self.calls.append((query, params))
            if sum(len(conn.calls) for conn in made[-1].connections) <= failures:
                raise FakeOperationalError("synthetic connection failure")
            return types.SimpleNamespace(fetchall=lambda: [{"query": query}])

        def close(self):
            self.closed = True

    class ConnectionContext:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self.connection

        def __exit__(self, *_):
            return False

    class Pool:
        check_connection = object()

        def __init__(self, conninfo, **kwargs):
            self.conninfo = conninfo
            self.kwargs = kwargs
            self.connections = [Connection()]
            self.opened = False
            made.append(self)

        def open(self):
            self.opened = True

        def connection(self):
            return ConnectionContext(self.connections[0])

        def close(self):
            self.closed = True

    fake_psycopg = types.ModuleType("psycopg")
    fake_psycopg.Error = FakeOperationalError
    fake_psycopg.__path__ = []
    monkeypatch.setitem(sys.modules, "psycopg_pool", types.SimpleNamespace(ConnectionPool=Pool))
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", types.SimpleNamespace(dict_row=object()))
    return made


def install_fake_chatbot(monkeypatch, original):
    db = types.SimpleNamespace(run_query=original, SCHEMA="graphrag", NODES="graphrag.nodes", EDGES="graphrag.edges")
    rag = types.SimpleNamespace(answer=lambda *_: {}, list_entities=lambda: [], analyze=lambda *_: None)
    monkeypatch.setitem(sys.modules, "db", db)
    monkeypatch.setitem(sys.modules, "rag", rag)
    monkeypatch.setattr(importlib, "reload", lambda module: module)
    return db, rag


def test_replacement_reuses_one_pool_connection(monkeypatch):
    monkeypatch.syspath_prepend(str(CHAT))
    monkeypatch.setenv("DB_URL", "synthetic-db-url")
    made = install_fake_pool(monkeypatch)
    original_calls = []
    db, _ = install_fake_chatbot(monkeypatch, lambda *args: original_calls.append(args) or [])
    patch = load("fp_chat_patch")

    patch.apply("fp_chat")
    assert db.run_query("one") == [{"query": "one"}]
    assert db.run_query("two") == [{"query": "two"}]

    assert len(made) == 1
    assert len(made[0].connections[0].calls) == 2
    assert original_calls == []
    assert made[0].kwargs["check"] is made[0].check_connection
    assert made[0].kwargs["max_idle"] == 60 and made[0].kwargs["max_lifetime"] == 300


def test_connection_error_retries_once_then_falls_back(monkeypatch):
    monkeypatch.syspath_prepend(str(CHAT))
    monkeypatch.setenv("DB_URL", "synthetic-db-url")
    made = install_fake_pool(monkeypatch, failures=2)
    fallback = []
    db, _ = install_fake_chatbot(monkeypatch, lambda query, params=None: fallback.append((query, params)) or [{"fallback": True}])
    patch = load("fp_chat_patch")

    patch.apply("fp_chat")
    assert db.run_query("select synthetic", {"x": 1}) == [{"fallback": True}]

    assert len(made[0].connections[0].calls) == 2
    assert made[0].connections[0].closed is True
    assert fallback == [("select synthetic", {"x": 1})]


def test_pool_opt_out_and_restore(monkeypatch):
    monkeypatch.syspath_prepend(str(CHAT))
    monkeypatch.setenv("FP_DB_POOL", "0")
    original = lambda *_: [{"original": True}]
    db, _ = install_fake_chatbot(monkeypatch, original)
    patch = load("fp_chat_patch")

    patch.apply("fp_chat")
    assert db.run_query is original
    monkeypatch.delenv("FP_DB_POOL")
    patch.apply("fp_chat")
    assert db.run_query is not original
    patch.restore()
    assert db.run_query is original


def test_repeated_apply_uses_single_pool(monkeypatch):
    monkeypatch.syspath_prepend(str(CHAT))
    monkeypatch.setenv("DB_URL", "synthetic-db-url")
    made = install_fake_pool(monkeypatch)
    db, _ = install_fake_chatbot(monkeypatch, lambda *_: [])
    patch = load("fp_chat_patch")

    patch.apply("fp_chat")
    db.run_query("first")
    patch.apply("fp_chat")
    db.run_query("second")

    assert len(made) == 1


def test_latency_dry_run_creates_no_connection_and_redacts_url(tmp_path, monkeypatch, capsys):
    monkeypatch.syspath_prepend(str(CHAT))
    secret = "synthetic-db-url-never-print"
    monkeypatch.setenv("DB_URL", secret)
    made = install_fake_pool(monkeypatch)
    source = tmp_path / "golden.jsonl"
    source.write_text(json.dumps({"selected_seed_names": ["synthetic"], "question": {"question": "synthetic question"}}) + "\n", encoding="utf-8")
    bench = load("latency_bench")

    assert bench.main(["--input", str(source), "--limit", "1", "--output-dir", "/tmp/fp-latency-dry-test"]) == 0

    output = capsys.readouterr().out
    assert "dry-run" in output
    assert not made
    assert secret not in output
