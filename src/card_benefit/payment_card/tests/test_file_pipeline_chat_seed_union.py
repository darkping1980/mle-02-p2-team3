import importlib.util
from pathlib import Path
import sys
import types

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "file_pipeline" / "chat"


def load(name):
    sys.path.insert(0, str(CHAT))
    spec = importlib.util.spec_from_file_location(f"seed_union_test_{name}", next((p for p in (next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py"), CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py", CHAT / "retrieval" / f"{name}.py", CHAT / "answer" / f"{name}.py") if p.exists()), next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py")))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_union_is_repeatable_and_adds_card_benefits_without_removing():
    union = load("seed_union").union_seed_names
    candidates = [
        {"name": "가나다 카드", "label": "Card"},
        {"name": "더 긴 가나다 카드 플러스", "label": "Card"},
        {"name": "전월 실적 30만원", "label": "Benefit"},
        {"name": "편의점 10% 할인", "label": "Benefit"},
    ]
    selected = ["이미 선택된 노드"]
    first = union("더 긴 가나다 카드 플러스의 전월 실적과 편의점 혜택", candidates, selected)
    assert first == union("더 긴 가나다 카드 플러스의 전월 실적과 편의점 혜택", candidates, selected)
    assert first[0] == "이미 선택된 노드"
    assert "더 긴 가나다 카드 플러스" in first
    assert "가나다 카드" not in first
    assert "전월 실적 30만원" in first
    assert "편의점 10% 할인" in first


def test_union_caps_benefits_and_ignores_names_outside_candidates():
    union = load("seed_union").union_seed_names
    candidates = [
        {"name": "편의점 A", "label": "Benefit"},
        {"name": "편의점 B", "label": "Benefit"},
        {"name": "편의점 C", "label": "Benefit"},
        {"name": "편의점 D", "label": "Benefit"},
        {"name": "편의점 외부 후보", "label": "Benefit"},
    ]
    result = union("편의점 할인 알려줘", candidates[:4], ["사용자 선택"], max_benefits=3)
    assert result == ["사용자 선택", "편의점 A", "편의점 B", "편의점 C"]
    assert "편의점 외부 후보" not in result


@pytest.mark.parametrize("enabled,expected", [(False, ["LLM 선택"]), (True, ["LLM 선택", "가나다 카드", "편의점 할인"])])
def test_patch_seed_union_toggle(monkeypatch, enabled, expected):
    patch = load("fp_chat_patch")
    db = types.SimpleNamespace(run_query=lambda *_: [])
    candidates = [
        {"name": "가나다 카드", "label": "Card"},
        {"name": "편의점 할인", "label": "Benefit"},
    ]
    captured = []

    class Analysis:
        def __init__(self):
            self.entities, self.hops, self.intent = ["LLM 선택"], 1, "합성"

    rag = types.SimpleNamespace(
        ANSWER_SYSTEM="synthetic", answer=lambda *_: {},
        list_entities=lambda *_: candidates,
        analyze=lambda *_: Analysis(),
        explore=lambda analysis: captured.append(list(analysis.entities)) or {"nodes": [], "edges": []},
        generate_stream=lambda *_: iter(()),
    )
    monkeypatch.setitem(sys.modules, "db", db)
    monkeypatch.setitem(sys.modules, "rag", rag)
    monkeypatch.setattr(patch, "_load_modules", lambda: db)
    monkeypatch.setattr("importlib.reload", lambda module: module)
    monkeypatch.setenv("FP_DB_POOL", "0")
    if enabled:
        monkeypatch.setenv("FP_SEED_UNION", "yes")
    else:
        monkeypatch.delenv("FP_SEED_UNION", raising=False)

    patched = patch.apply()
    token = patch._CURRENT_QUESTION.set("가나다 카드 편의점 혜택")
    try:
        analysis = patched.analyze("가나다 카드 편의점 혜택", candidates)
        patched.explore(analysis)
    finally:
        patch._CURRENT_QUESTION.reset(token)
    assert captured == [expected]
