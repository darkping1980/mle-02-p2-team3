import unittest

from src.card_benefit.payment_card.db_pipeline.neo4j_validate import MAPPER_ROOT, _normalize, compare_graph
from src.common.postgres_db_session import PostgresDbSession


def expected():
    nodes = [{"label": "A8Rule", "props": {"key": "n1", "source_json": "{}"}}]
    edges = [{"key": "e1", "type": "A8_SUPPORTED_BY", "start": "n1", "end": "n2", "source_json": "{}"}]
    return nodes, edges


class CompareTests(unittest.TestCase):
    def test_identical_graph_has_no_difference(self):
        nodes, edges = expected()
        result = compare_graph(nodes, edges, [{"key": "n1", "label": "A8Rule", "source_json": "{}"}], [dict(edges[0])])
        self.assertEqual(sum(len(v) for v in result.values()), 0)

    def test_changed_json_label_and_missing_items_are_reported(self):
        nodes, edges = expected()
        self.assertEqual(compare_graph(nodes, edges, [{"key": "n1", "label": "A8Rule", "source_json": "x"}], [])["nodes_changed"], ["n1"])
        self.assertEqual(compare_graph(nodes, edges, [{"key": "n1", "label": "A8Card", "source_json": "{}"}], [])["nodes_changed"], ["n1"])
        self.assertEqual(compare_graph(nodes, edges, [], [])["relationships_missing"], ["e1"])

    def test_changed_endpoint_is_reported(self):
        nodes, edges = expected()
        moved = {**edges[0], "end": "other"}
        self.assertEqual(compare_graph(nodes, edges, [{"key": "n1", "label": "A8Rule", "source_json": "{}"}], [moved])["relationships_changed"], ["e1"])

    def test_extra_graph_item_is_reported(self):
        result = compare_graph([], [], [{"key": "x", "label": "A8Rule", "source_json": "{}"}], [])
        self.assertEqual(result["nodes_extra"], ["x"])

    def test_sql_file_statements(self):
        session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")
        for name in ("condition_structure", "evidence_links"):
            self.assertTrue(session._query(f"neo4j_validation.{name}").sql.strip().upper().startswith("SELECT"))
        self.assertEqual(session.database_manager._pools, {})

    def test_normalize_hides_numeric_type_only(self):
        from decimal import Decimal
        self.assertEqual(_normalize([{"a": Decimal("100000.00"), "b": None}], ("a", "b")), _normalize([{"a": 100000, "b": None}], ("a", "b")))
        self.assertNotEqual(_normalize([{"a": 1, "b": "x"}], ("a", "b")), _normalize([{"a": 1, "b": "y"}], ("a", "b")))


if __name__ == "__main__":
    unittest.main()
