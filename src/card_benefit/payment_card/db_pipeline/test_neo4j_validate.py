import unittest

from card_benefit.payment_card.db_pipeline.neo4j_load_draft import CYPHER
from card_benefit.payment_card.db_pipeline.neo4j_validate import MAPPER_ROOT, _normalize, compare_graph, graph_ok
from common.postgres_db_session import PostgresDbSession


def expected():
    nodes = [{"label": "dp_bnft_rule", "props": {"key": "n1", "source_json": "{}"}}]
    edges = [{"key": "e1", "type": "dp_supported_by", "start": "n1", "end": "n2", "source_json": "{}"}]
    return nodes, edges


def found_node(labels=None, **props):
    return {"key": "n1", "labels": labels or ["dp_node", "dp_bnft_rule"],
            "props": {"key": "n1", "source_json": "{}", **props}}


def found_edge(**changes):
    return {"key": "e1", "type": "dp_supported_by", "start": "n1", "end": "n2",
            "source_json": "{}", "props": {"key": "e1", "source_json": "{}"}, **changes}


class CompareTests(unittest.TestCase):
    def test_identical_graph_has_no_difference(self):
        nodes, edges = expected()
        result = compare_graph(nodes, edges, [found_node()], [found_edge()])
        self.assertEqual(sum(len(v) for v in result.values()), 0)

    def test_changed_json_label_and_missing_items_are_reported(self):
        nodes, edges = expected()
        self.assertEqual(compare_graph(nodes, edges, [found_node(source_json="x")], [])["node_properties_changed"][0]["field"], "source_json")
        self.assertEqual(compare_graph(nodes, edges, [found_node(["dp_node", "dp_card_product"])], [])["node_labels_changed"][0]["key"], "n1")
        self.assertEqual(compare_graph(nodes, edges, [], [])["relationships_missing"], ["e1"])

    def test_changed_endpoint_is_reported(self):
        nodes, edges = expected()
        moved = found_edge(end="other")
        diff = compare_graph(nodes, edges, [found_node()], [moved])["relationship_structure_changed"][0]
        self.assertEqual((diff["key"], diff["field"], diff["expected"], diff["actual"]), ("e1", "end", "n2", "other"))

    def test_extra_graph_item_is_reported(self):
        result = compare_graph([], [], [{"key": "x", "labels": ["dp_node", "dp_bnft_rule"], "props": {}}], [])
        self.assertEqual(result["nodes_extra"], ["x"])

    def test_benefit_label_order_never_changes_verdict(self):
        node = {"label": "dp_card_bnft", "props": {"key": "n1", "source_json": "{}"}}
        a = found_node(["dp_node", "dp_card_bnft", "dp_card_product_item"])
        b = found_node(["dp_card_product_item", "dp_node", "dp_card_bnft"])
        self.assertNotEqual(a["labels"][1], b["labels"][1])  # 첫 라벨로 비교하면 오판 가능
        self.assertEqual(compare_graph([node], [], [a], []), compare_graph([node], [], [b], []))
        self.assertFalse(any(compare_graph([node], [], [b], []).values()))

    def test_property_difference_reports_key_field_and_values(self):
        nodes, _ = expected()
        diff = compare_graph(nodes, [], [found_node(source_json="changed")], [])["node_properties_changed"][0]
        self.assertEqual((diff["key"], diff["field"], diff["expected"], diff["actual"]), ("n1", "source_json", "{}", "changed"))

    def test_new_edges_are_missing_not_modified_existing(self):
        _, edges = expected()
        related = {"key": "new", "type": "dp_related_to", "start": "n1", "end": "n2", "source_json": "{}"}
        result = compare_graph([], edges + [related], [], [found_edge()])
        self.assertEqual(result["relationships_missing"], ["new"])
        self.assertFalse(result["relationship_properties_changed"])

    def test_dp_verdict_takes_only_dp_results(self):
        clean = {"outside_nodes": 0, "outside_relationships": 0}
        self.assertTrue(graph_ok(0, clean, [], True, True, True, True))
        self.assertFalse(graph_ok(1, clean, [], True, True, True, True))
        self.assertFalse(graph_ok(0, {**clean, "outside_relationships": 1}, [], True, True))
        self.assertFalse(graph_ok(0, clean, ["n"], True, True))
        self.assertFalse(graph_ok(0, clean, [], True, False, True, True))

    def test_outside_scope_counts_dp_boundary_not_other_pipelines(self):
        lines = CYPHER["neo4j_validation.outside_scope_counts"].splitlines()
        query = "\n".join(line for line in lines if not line.lstrip().startswith("//"))
        self.assertIn("dp_node", query)
        self.assertNotIn("fp_", query)

    def test_other_graphs_are_reported_separately(self):
        query = CYPHER["neo4j_validation.other_graph_counts"]
        for word in ("fp_nodes", "fp_relationships"):
            self.assertIn(word, query)

    def test_sql_file_statements(self):
        session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")
        for name in ("condition_structure", "evidence_links", "common_applies", "rule_targets"):
            self.assertTrue(session._query(f"neo4j_validation.{name}").sql.strip().upper().startswith("SELECT"))
        self.assertEqual(session.database_manager._pools, {})

    def test_normalize_hides_numeric_type_only(self):
        from decimal import Decimal
        self.assertEqual(_normalize([{"a": Decimal("100000.00"), "b": None}], ("a", "b")), _normalize([{"a": 100000, "b": None}], ("a", "b")))
        self.assertNotEqual(_normalize([{"a": 1, "b": "x"}], ("a", "b")), _normalize([{"a": 1, "b": "y"}], ("a", "b")))


if __name__ == "__main__":
    unittest.main()
