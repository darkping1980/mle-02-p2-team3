import importlib.util
from pathlib import Path
import sys


CHAT = Path(__file__).resolve().parents[1] / "file_pipeline" / "chat"
sys.path.insert(0, str(CHAT))
spec = importlib.util.spec_from_file_location("value_conflicts_test", CHAT / "eval" / "value_conflicts.py")
value_conflicts = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = value_conflicts
spec.loader.exec_module(value_conflicts)


def _subgraph(names_and_rates, card_id="card-1"):
    nodes = [{"id": card_id, "name": "Synthetic Card", "label": "Card", "props": {}}]
    edges = []
    for index, (name, rate, page) in enumerate(names_and_rates):
        node_id = f"benefit-{card_id}-{index}"
        nodes.append({"id": node_id, "name": name, "label": "Benefit",
                      "props": {"rate": rate, "source_text": f"(p.{page}) synthetic evidence"}})
        edges.append({"source": card_id, "target": node_id, "type": "OFFERS"})
    return {"nodes": nodes, "edges": edges}


def test_exact_normalized_name_with_different_values_and_pages():
    subgraph = _subgraph([
        ("Synthetic Hotel Room 15% 할인", "15%", 31),
        ("synthetic hotel room 할인", "10%", 47),
    ], card_id="CLUB1카드200")
    conflicts = value_conflicts.detect_value_conflicts(subgraph)
    assert len(conflicts) == 1
    assert conflicts[0]["node_ids"]
    assert {entry["value"] for entry in conflicts[0]["values"]} == {"10%", "15%"}
    assert {entry["page"] for entry in conflicts[0]["values"]} == {31, 47}


def test_equivalent_percentage_notation_is_not_a_conflict():
    assert value_conflicts.detect_value_conflicts(_subgraph([
        ("Synthetic Pay Discount", "1.0%", 2),
        ("Synthetic Pay Discount", "1%", 4),
    ])) == []


def test_same_page_tier_values_are_not_a_conflict():
    assert value_conflicts.detect_value_conflicts(_subgraph([
        ("Synthetic Convenience Discount", "10%", 2),
        ("Synthetic Convenience Discount", "7%", 2),
        ("Synthetic Convenience Discount", "7%", 2),
    ])) == []


def test_unknown_page_value_is_counted_only_when_a_conflict_exists():
    graph = _subgraph([
        ("Synthetic Hotel Room", "15%", 31),
        ("Synthetic Hotel Room", "10%", None),
    ])
    assert value_conflicts.detect_value_conflicts(graph) == []
    graph = _subgraph([
        ("Synthetic Hotel Room", "15%", 31),
        ("Synthetic Hotel Room", "10%", 47),
        ("Synthetic Hotel Room", "20%", None),
    ])
    conflicts = value_conflicts.detect_value_conflicts(graph)
    assert len(conflicts) == 1
    assert conflicts[0]["page_unknown_count"] == 1


def test_common_money_notations_have_same_canonical_value():
    normalized = {
        value_conflicts._canonical_value(value)
        for value in ("5,000韩元", "5천원", "5,000원", "5000 KRW", "5,000 won", "5,000韓元")
    }
    assert normalized == {"krw:5000"}
    assert value_conflicts._canonical_value("1만원") == "krw:10000"
    assert value_conflicts._canonical_value("5~20%") == "range:percent:5..percent:20"


def test_hotel_and_air_targets_are_not_a_conflict():
    assert value_conflicts.detect_value_conflicts(_subgraph([
        ("SyntheticTrip 호텔 할인", "10%", 2),
        ("SyntheticTrip 항공 할인", "20%", 3),
    ])) == []


def test_identical_values_are_not_a_conflict():
    assert value_conflicts.detect_value_conflicts(_subgraph([
        ("카페 할인", "10%", 2), ("카페 혜택", "10%", 3),
    ])) == []


def test_different_cards_are_not_compared():
    graph = _subgraph([("Synthetic Room 10 할인", "10%", 2)], "card-a")
    other = _subgraph([("Synthetic Room 할인", "20%", 3)], "card-b")
    graph["nodes"].extend(other["nodes"])
    graph["edges"].extend(other["edges"])
    assert value_conflicts.detect_value_conflicts(graph) == []


def test_unknown_card_benefits_are_excluded_when_multiple_cards_exist():
    graph = {
        "nodes": [
            {"id": "card-a", "name": "A", "label": "Card", "props": {}},
            {"id": "card-b", "name": "B", "label": "Card", "props": {}},
            {"id": "known", "name": "Synthetic Room 할인", "label": "Benefit", "props": {"rate": "10%"}},
            {"id": "unknown", "name": "Synthetic Room 15 할인", "label": "Benefit", "props": {"rate": "15%"}},
        ],
        "edges": [{"source": "card-a", "target": "known", "type": "OFFERS"}],
    }
    assert value_conflicts.detect_value_conflicts(graph) == []


def test_unknown_card_is_marked_when_single_card_scope_applies():
    graph = _subgraph([("Synthetic Room 할인", "10%", 2)])
    graph["nodes"].append({"id": "unknown", "name": "Synthetic Room 15 할인", "label": "Benefit",
                           "props": {"rate": "15%", "source_text": "(p.4) synthetic"}})
    conflicts = value_conflicts.detect_value_conflicts(graph)
    assert len(conflicts) == 1
    assert conflicts[0]["card_unknown"] is True


def test_unrelated_names_are_not_compared_and_missing_page_is_none():
    graph = {"nodes": [
        {"id": "x", "name": "주유 적립", "label": "Benefit", "props": {"rate": "5%"}},
        {"id": "y", "name": "호텔 숙박", "label": "Benefit", "props": {"rate": "10%", "source_text": "synthetic evidence"}},
    ], "edges": []}
    assert value_conflicts.detect_value_conflicts(graph) == []
    assert value_conflicts._page_number("synthetic evidence") is None
    assert value_conflicts._page_number("(p.47) synthetic evidence") == 47
