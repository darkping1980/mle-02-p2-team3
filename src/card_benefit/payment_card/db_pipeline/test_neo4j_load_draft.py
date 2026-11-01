import unittest
from unittest.mock import patch

from card_benefit.payment_card.db_pipeline import neo4j_load_draft
from card_benefit.payment_card.db_pipeline.neo4j_dry_run import NS, Preview
from card_benefit.payment_card.db_pipeline.neo4j_load_draft import prepare, write_transaction


class Result:
    def __init__(self, rows=None): self.rows = rows or []
    def single(self, strict=True):
        return {"n": 1}
    def __iter__(self): return iter(self.rows)


class FakeTx:
    def __init__(self): self.calls = []
    def run(self, query, **params):
        self.calls.append((query, params))
        if "RETURN n.key AS key" in query: return Result([{"key": "one"}])
        if "RETURN r.key AS key" in query: return Result([{"key": "r"}])
        return Result()


class LoaderTests(unittest.TestCase):
    def test_transaction_uses_only_dedicated_scope(self):
        tx = FakeTx()
        nodes = [{"label": "df_card_product", "props": {"key": "one", "namespace": NS}}]
        rels = [{"type": "df_has_policy", "start": "one", "end": "two", "key": "r", "source_json": "{}"}]
        self.assertEqual(write_transaction(tx, nodes, rels), (1, 1))
        self.assertTrue(all("df_node" in query for query, _ in tx.calls))
        self.assertTrue(all(params.get("namespace", params.get("ns")) == NS for _, params in tx.calls))

    def test_validation_file_has_named_read_only_statements(self):
        self.assertTrue({"neo4j_validation.node_keys", "neo4j_validation.relationship_keys", "neo4j_validation.card_constraints",
                         "neo4j_validation.existing_node_keys", "neo4j_validation.condition_structure",
                         "neo4j_validation.evidence_links", "neo4j_validation.orphan_nodes"} <= set(neo4j_load_draft.CYPHER))
        for query in neo4j_load_draft.CYPHER.values():
            self.assertNotRegex(query.upper(), r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP)\b")

    def test_namespace_is_passed_as_parameter(self):
        tx = FakeTx()
        write_transaction(tx, [{"label": "df_card_product", "props": {"key": "one", "namespace": NS}}],
                          [{"type": "df_has_policy", "start": "one", "end": "two", "key": "r", "source_json": "{}"}])
        self.assertTrue(all(NS not in query for query, _ in tx.calls))

    def test_allowlists_have_13_labels_and_12_types_of_df_only(self):
        self.assertEqual(len(neo4j_load_draft.NODE_LABELS), 13)
        self.assertEqual(len(neo4j_load_draft.REL_TYPES), 12)
        self.assertTrue(all(name.startswith("df_") for name in neo4j_load_draft.NODE_LABELS | neo4j_load_draft.REL_TYPES))

    def test_pf_label_is_refused(self):
        graph = Preview()
        graph.nodes["k"] = {"label": "pf_card_product", "key": "k", "namespace": NS, "source_json": "{}"}
        with self.assertRaisesRegex(ValueError, "unexpected node scope"):
            prepare(graph)

    def test_constraint_is_df_only_and_idempotent(self):
        query = neo4j_load_draft.CREATE_CONSTRAINT
        self.assertIn("df_node_key IF NOT EXISTS", query)
        self.assertIn("(n:df_node)", query)
        self.assertNotIn("pf_", query)

    def test_node_properties_have_no_test_marker(self):
        props = neo4j_load_draft.node_properties({"label": "df_card_product", "key": "k", "source_json": '{"card_id": 2}'})
        self.assertEqual(props, {"namespace": NS, "key": "k", "source_json": '{"card_id": 2}', "card_id": 2})

    def test_preview_count_guard(self):
        graph = Preview(); graph.node("card_product", [2], {})
        with self.assertRaises(ValueError): prepare(graph)

    def test_rule_evidence_edge_passes_allowlist_and_keeps_item_key(self):
        graph = Preview()
        rule = graph.node("bnft_rule", [2, "benefit", "rule"], {"rule_key": "rule"})
        evidence = graph.node("card_source_evidence", ["ev"], {"evidence_id": "ev"})
        graph.edge("supported_by", rule, evidence, {"ev_link_id": "l", "ev_subject_cd": "RULE", "rule_key": "rule",
                                                    "ev_item_cd": "COND", "ev_item_key": "MIN_rule"})
        with patch.object(neo4j_load_draft, "EXPECTED_NODES", 2), patch.object(neo4j_load_draft, "EXPECTED_RELATIONSHIPS", 1):
            nodes, edges = prepare(graph)
        self.assertEqual({node["label"] for node in nodes}, {"df_bnft_rule", "df_card_source_evidence"})
        self.assertEqual(edges[0]["type"], "df_supported_by")
        self.assertIn('"ev_item_key":"MIN_rule"', edges[0]["source_json"])


if __name__ == "__main__":
    unittest.main()
