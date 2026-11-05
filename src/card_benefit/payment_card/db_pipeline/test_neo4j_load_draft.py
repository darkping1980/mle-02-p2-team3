import re
import unittest

from card_benefit.payment_card.db_pipeline import neo4j_load_draft
from card_benefit.payment_card.db_pipeline.neo4j_dry_run import Preview
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


NODE = {"label": "dp_card_product", "pk": {"card_id": 2}, "props": {"key": "one", "card_id": 2}}
EDGE = {"type": "dp_has_benefit", "start": "one", "end": "two", "key": "r", "source_json": "{}"}


class LoaderTests(unittest.TestCase):
    def test_transaction_uses_only_dp_scope_and_primary_key(self):
        tx = FakeTx()
        self.assertEqual(write_transaction(tx, [NODE], [EDGE]), (1, 1))
        self.assertTrue(all("dp_node" in query for query, _ in tx.calls))
        self.assertIn("MERGE (n:dp_card_product {card_id: $pk.card_id})", tx.calls[0][0])
        self.assertEqual(tx.calls[0][1]["pk"], {"card_id": 2})

    def test_no_delete_statement_exists_in_loader(self):
        source = open(neo4j_load_draft.__file__, encoding="utf-8").read()
        self.assertNotRegex(source, r"(?i)\b(DETACH\s+DELETE|DELETE\s+[a-z])")
        self.assertNotRegex(source, r"\bfp_")

    def test_validation_file_has_named_read_only_statements(self):
        self.assertTrue({"neo4j_validation.node_keys", "neo4j_validation.relationship_keys", "neo4j_validation.card_constraints",
                         "neo4j_validation.existing_node_keys", "neo4j_validation.condition_structure",
                         "neo4j_validation.evidence_links", "neo4j_validation.orphan_nodes",
                         "neo4j_validation.common_applies", "neo4j_validation.rule_targets"} <= set(neo4j_load_draft.CYPHER))
        for query in neo4j_load_draft.CYPHER.values():
            self.assertNotRegex(query.upper(), r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP)\b")

    def test_allowlists_are_dp_only_and_have_no_link_table_label(self):
        self.assertEqual(len(neo4j_load_draft.NODE_LABELS), 14)
        self.assertIn("dp_related_to", neo4j_load_draft.REL_TYPES)
        self.assertNotIn("dp_card_common_bnft_apply", neo4j_load_draft.NODE_LABELS)
        self.assertNotIn("dp_card_limit_pool", neo4j_load_draft.NODE_LABELS)
        self.assertTrue(all(name.startswith("dp_") for name in neo4j_load_draft.NODE_LABELS | neo4j_load_draft.REL_TYPES))

    def test_other_project_label_is_refused(self):
        graph = Preview()
        graph.nodes["k"] = {"label": "fp_card_product", "key": "k", "pk": {}, "source_json": "{}"}
        with self.assertRaisesRegex(ValueError, "unexpected node scope"):
            prepare(graph)

    def test_constraints_follow_postgres_keys(self):
        joined = "\n".join(neo4j_load_draft.CREATE_CONSTRAINTS)
        self.assertIn("dp_node_key IF NOT EXISTS", joined)
        self.assertRegex(joined, r"dp_card_bnft_pk IF NOT EXISTS FOR \(n:dp_card_bnft\) REQUIRE \(n\.card_id, n\.card_bnft_id\) IS NODE KEY")
        self.assertRegex(joined, r"dp_card_common_bnft_pk .*\(n\.card_common_id, n\.card_common_bnft_id\) IS NODE KEY")
        self.assertFalse(re.search(r"fp_", joined))

    def test_node_properties_keep_primary_key(self):
        props = neo4j_load_draft.node_properties({"label": "dp_card_product", "key": "k", "pk": {"card_id": 2}, "source_json": '{"card_id": 2}'})
        self.assertEqual(props, {"key": "k", "source_json": '{"card_id": 2}', "card_id": 2})

    def test_embedding_columns_never_become_properties(self):
        props = neo4j_load_draft.node_properties({"label": "dp_card_product", "key": "k", "source_json": '{"bnft_embedding": "[1]", "bnft_search_txt": "x"}'})
        self.assertNotIn("bnft_embedding", props)
        self.assertNotIn("bnft_search_txt", props)

    def test_benefit_text_becomes_queryable_properties(self):
        source = '{"bnft_nm": "n", "bnft_rule_txt": "100원", "bnft_limit_txt": "월 5천원"}'
        props = neo4j_load_draft.node_properties({"label": "dp_card_product", "key": "k", "source_json": source})
        self.assertEqual((props["rule_text"], props["limit_text"]), ("100원", "월 5천원"))

    def test_rule_evidence_edge_passes_allowlist_and_keeps_item_key(self):
        graph = Preview()
        rule = graph.node("bnft_rule", [2, "benefit", "rule"], {"rule_key": "rule"})
        evidence = graph.node("card_source_evidence", ["ev"], {"evidence_id": "ev"})
        graph.edge("supported_by", rule, evidence, {"ev_link_id": "l", "ev_subject_cd": "RULE", "rule_key": "rule",
                                                    "ev_item_cd": "COND", "ev_item_key": "MIN_rule"})
        nodes, edges = prepare(graph)
        self.assertEqual({node["label"] for node in nodes}, {"dp_bnft_rule", "dp_card_source_evidence"})
        self.assertEqual(edges[0]["type"], "dp_supported_by")
        self.assertIn('"ev_item_key":"MIN_rule"', edges[0]["source_json"])

    def test_related_edge_keeps_identity_and_queryable_properties(self):
        graph = Preview()
        start = graph.node("card_bnft", [2, "a"], {"card_bnft_id": "a"})
        end = graph.node("card_bnft", [2, "b"], {"card_bnft_id": "b"})
        graph.edge("related_to", start, end, {"relation_key": "r1", "to_bnft_id": "b", "rel_type_cd": "OVERRIDES", "rel_priority": 1})
        _, edges = prepare(graph)
        self.assertEqual(edges, prepare(graph)[1])
        tx = FakeTx()
        edge = {**edges[0], "start": "one", "end": "two", "key": "r"}
        write_transaction(tx, [NODE], [edge])
        query, params = tx.calls[1]
        self.assertIn("MERGE (a)-[r:dp_related_to {key:$key}]->(b)", query)
        self.assertEqual(params["extra"], {"relation_key": "r1", "to_bnft_id": "b", "rel_type_cd": "OVERRIDES", "rel_priority": 1})

    def test_existing_evidence_edge_does_not_gain_relation_properties(self):
        tx = FakeTx()
        edge = {**EDGE, "type": "dp_supported_by", "source_json": '{"ev_subject_cd":"REL","relation_key":"r1"}'}
        write_transaction(tx, [NODE], [edge])
        self.assertEqual(tx.calls[1][1]["extra"], {"ev_subject_cd": "REL"})


if __name__ == "__main__":
    unittest.main()
