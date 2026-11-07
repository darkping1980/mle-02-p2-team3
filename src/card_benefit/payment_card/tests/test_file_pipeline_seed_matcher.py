import importlib.util
from pathlib import Path
import sys

CHAT = Path(__file__).resolve().parents[1] / "file_pipeline" / "chat"
sys.path.insert(0, str(CHAT))


def load(name):
    spec = importlib.util.spec_from_file_location(name, next((p for p in (next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py"), CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py", CHAT / "retrieval" / f"{name}.py", CHAT / "answer" / f"{name}.py") if p.exists()), next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py")))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


matcher = load("seed_matcher")
reval = load("retrieval_eval")


def test_normalization_removes_particles_and_punctuation():
    assert matcher.normalize("ABC 카드의 혜택은!") == "abc카드혜택"


def test_empty_below_threshold_and_deterministic_ties():
    nodes = [{"name": name, "label": "Benefit"} for name in ("가나다", "가나랑")]
    assert matcher.select_seeds_fuzzy(nodes, "아무것", threshold=0.99) == []
    assert matcher.select_seeds_fuzzy(nodes, "가나다", threshold=0) == ["가나다", "가나랑"]
    assert matcher.select_seeds_fuzzy(nodes, "가나") == matcher.select_seeds_fuzzy(nodes, "가나")


def test_label_priority_and_general_word_penalty():
    nodes = [
        {"name": "하나", "label": "Condition"},
        {"name": "하나", "label": "Card"},
        {"name": "하나 혜택", "label": "Benefit"},
    ]
    # Duplicate common short names are excluded; a descriptive benefit can rank.
    assert "하나" not in matcher.select_seeds_fuzzy(nodes, "하나 혜택", n=3)
    assert matcher.select_seeds_fuzzy(nodes, "하나 혜택", n=3)[0] == "하나 혜택"
    ranked = [
        {"name": "가나다", "label": "Condition"},
        {"name": "가나랑", "label": "Card"},
    ]
    assert matcher.select_seeds_fuzzy(ranked, "가나다 가나랑", n=1)[0] == "가나랑"


def test_fuzzy_evaluate_metrics_and_no_db_llm_imports(monkeypatch):
    nodes = [{"id": "1", "name": "가나다 카드", "label": "Card", "props": {}}]
    rows = reval.evaluate([{"question": "가나다 카드의", "seed_entities": ["가나다 카드"], "expected": ["가나다"]}], nodes, [], "fuzzy")
    metric = rows[0]["metrics"]
    assert rows[0]["seeds"] == ["가나다 카드"]
    assert metric["seed_precision"] == 1 and metric["wrong_seed_count"] == 0
    assert reval.aggregate([metric])["seed_hit_rate"] == 1
    assert "db" not in sys.modules and "rag" not in sys.modules and "llm" not in sys.modules


def test_cli_accepts_fuzzy():
    import pytest
    with pytest.raises(SystemExit) as exc:
        reval.main(["--help"])
    assert exc.value.code == 0
