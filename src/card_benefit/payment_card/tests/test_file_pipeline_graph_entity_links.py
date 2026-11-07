import csv

from payment_card.file_pipeline.graph.entity_links_loader import validate_links
from payment_card.file_pipeline.chat.retrieval.entity_dedupe import dedupe_subgraph


def _write_csv(path, fieldnames, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_loader_validates_members_canonical_and_node_ids(tmp_path):
    fields = ["group_id", "kind", "canonical_node_id", "member_node_id", "same_props", "distinct_pages"]
    links = tmp_path / "links.csv"
    nodes = tmp_path / "nodes.csv"
    _write_csv(links, fields, [
        {"group_id": "G1", "kind": "Benefit", "canonical_node_id": "n1", "member_node_id": "n1", "same_props": "true", "distinct_pages": "2"},
        {"group_id": "G1", "kind": "Benefit", "canonical_node_id": "n1", "member_node_id": "n2", "same_props": "true", "distinct_pages": "2"},
    ])
    _write_csv(nodes, ["id"], [{"id": "n1"}, {"id": "n2"}])
    report = validate_links(links, nodes_csv=nodes)
    assert report["groups"] == 1
    assert report["members"] == 2
    assert report["errors"] == []


def test_loader_rejects_duplicate_members_and_missing_canonical_or_node(tmp_path):
    fields = ["group_id", "kind", "canonical_node_id", "member_node_id", "same_props", "distinct_pages"]
    links = tmp_path / "links.csv"
    nodes = tmp_path / "nodes.csv"
    _write_csv(links, fields, [
        {"group_id": "G1", "kind": "Benefit", "canonical_node_id": "missing", "member_node_id": "n1", "same_props": "true", "distinct_pages": "2"},
        {"group_id": "G2", "kind": "Benefit", "canonical_node_id": "n1", "member_node_id": "n1", "same_props": "true", "distinct_pages": "2"},
        {"group_id": "G3", "kind": "Benefit", "canonical_node_id": "n1", "member_node_id": "n1", "same_props": "true", "distinct_pages": "2"},
    ])
    _write_csv(nodes, ["id"], [{"id": "n1"}])
    report = validate_links(links, nodes_csv=nodes)
    assert any("more than one group" in error for error in report["errors"])
    assert any("canonical" in error for error in report["errors"])
    assert any("not present" in error for error in report["errors"])


def test_dedupe_preserves_evidence_and_deduplicates_pages():
    graph = {
        "nodes": [
            {"id": "n1", "name": "혜택", "label": "Benefit", "props": {"source_text": "근거 A", "source_text_pages": [2]}},
            {"id": "n2", "name": "혜택", "label": "Benefit", "props": {"source_text": "근거 B", "source_text_pages": [2, 3]}},
            {"id": "l1", "name": "한도", "label": "Limit", "props": {}},
        ],
        "edges": [{"source": "n2", "target": "l1", "type": "HAS_LIMIT"}],
        "evidence": [
            {"node_id": "n1", "doc_sha256": "a" * 64, "page_no": 2, "start_pos": 1},
            {"node_id": "n2", "doc_sha256": "b" * 64, "page_no": 2, "start_pos": 9},
        ],
        "seeds": ["n2"],
    }
    result = dedupe_subgraph(graph, {"n2": "n1"})
    canonical = next(node for node in result["nodes"] if node["id"] == "n1")
    assert len(result["nodes"]) == 2
    assert canonical["merged_member_count"] == 2
    assert canonical["props"]["source_text_pages"] == [2, 3]
    assert {source["text"] for source in canonical["sources"]} >= {"근거 A", "근거 B"}
    assert result["edges"] == [{"source": "n1", "target": "l1", "type": "HAS_LIMIT"}]
    assert len(result["evidence"]) == 2
    assert {row["node_id"] for row in result["evidence"]} == {"n1"}
    assert result["seeds"] == ["n1"]


def test_across_cards_similar_links_are_excluded_from_merge_mapping(tmp_path):
    from payment_card.file_pipeline.graph.entity_links_loader import validate_links
    from payment_card.file_pipeline.chat.retrieval.entity_dedupe import dedupe_subgraph

    # SIMILAR rows are intentionally not part of the loader's merge mapping.
    fields = ["group_id", "kind", "canonical_node_id", "member_node_id", "same_props", "distinct_pages", "scope", "link_type", "merge_target"]
    links = tmp_path / "similar.csv"
    _write_csv(links, fields, [{"group_id": "A1", "kind": "Benefit", "canonical_node_id": "a", "member_node_id": "b", "same_props": "true", "distinct_pages": 2, "scope": "across_cards", "link_type": "SIMILAR", "merge_target": "false"}])
    report = validate_links(links)
    graph = {"nodes": [{"id": "a", "name": "X", "label": "Benefit", "props": {}}, {"id": "b", "name": "X", "label": "Benefit", "props": {}}], "edges": [], "seeds": []}
    result = dedupe_subgraph(graph, report["merge_mapping"])
    assert len(result["nodes"]) == 2


def test_entity_dedupe_is_off_by_default(monkeypatch):
    from payment_card.file_pipeline.chat.fp_chat_patch import _dedupe_retrieved_subgraph

    monkeypatch.delenv("FP_ENTITY_DEDUPE", raising=False)
    monkeypatch.setenv("FP_ENTITY_LINKS_CSV", "/missing/should-not-be-read.csv")
    graph = {"nodes": [{"id": "a"}, {"id": "b"}], "edges": [], "seeds": []}
    assert _dedupe_retrieved_subgraph(graph) is graph

