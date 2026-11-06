from .neo4j_relational_model import build
from .neo4j_validate import compare_graph
from .test_neo4j_relational_model import snapshot


def test_comparison_detects_exact_source_match():
    model = build(snapshot())
    nodes = [{"key": item["key"], "labels": ["dp_node", item["label"]], "props": item["props"]}
             for item in model["nodes"]]
    edges = [{"key": item["key"], "type": item["type"], "start": item["start"], "end": item["end"],
              "props": item["props"]} for item in model["relationships"]]
    result = compare_graph(model, nodes, edges)
    assert not result["nodes_missing"] and not result["nodes_extra"]
    assert not result["relationships_missing"] and not result["relationships_extra"]
    assert not result["node_property_differences"] and not result["relationship_property_differences"]


def test_comparison_flags_removed_source_property():
    model = build(snapshot())
    nodes = [{"key": item["key"], "labels": ["dp_node", item["label"]], "props": dict(item["props"])}
             for item in model["nodes"]]
    nodes[0]["props"].pop("source_json")
    result = compare_graph(model, nodes, [])
    assert any(issue["field"] == "source_json" for issue in result["node_property_differences"])
