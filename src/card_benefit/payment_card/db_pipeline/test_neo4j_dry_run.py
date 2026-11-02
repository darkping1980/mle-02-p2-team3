import copy
import unittest

from card_benefit.payment_card.db_pipeline.neo4j_dry_run import NS, Preview, build, key


def fixture():
    atom = lambda k, n: {"atom_key": k, "atom_seq": 1, "negate_yn": n}
    expr = {"branches": [{"branch_no": 1, "atoms": [atom("spend", False)]},
                         {"branch_no": 2, "atoms": [atom("grace", True)]}]}
    return {
        "product": [{"card_id": 2, "card_cond_status_cd": "DRAFT", "card_cond_expr": None}],
        "product_doc": [{}], "document": [{}],
        "pages": [{"page_no": 1}],
        "chunks": [{"card_doc_id": "20261101_000002", "page_no": 1, "card_doc_chunk_id": "chunk"}],
        "evidence": [{"card_doc_id": "20261101_000002", "page_no": 1, "card_doc_chunk_id": "chunk", "evidence_id": "ev", "approval_status_cd": "PENDING"}],
        "pools": [{"pool_id": "pool", "aggregation_key_cd": "CARD_MEMBER"}],
        "benefits": [{"card_bnft_id": "benefit", "bnft_cond_expr": expr,
                      "rule_list": [{"rule_key": "rule", "target_list": [],
                                     "pool_refs": [{"pool_id": "pool"}], "cond_expr": None}]}],
        "links": [{"ev_subject_cd": "BNFT", "card_bnft_id": "benefit", "evidence_id": "ev", "ev_link_id": "link"}],
    }


class PreviewTests(unittest.TestCase):
    def test_or_negation_and_source_are_preserved(self):
        snapshot = fixture()
        graph, stats = build(snapshot)
        self.assertEqual(stats["nodes"]["df_cond_branch"], 2)
        self.assertEqual(stats["nodes"]["df_cond_atom"], 2)
        self.assertIn('"negate_yn":true', graph.nodes[key("cond_atom", "benefit", 2, "benefit", 2, "grace")]["source_json"])
        self.assertEqual(stats["relationships"]["df_supported_by"], 1)
        self.assertEqual(stats["relationships"]["df_consumes"], 1)

    def test_missing_pool_is_rejected(self):
        data = fixture(); data["pools"] = []
        with self.assertRaises(KeyError): build(data)

    def test_wrong_evidence_page_is_rejected(self):
        data = fixture(); data["evidence"][0]["page_no"] = 2
        with self.assertRaises(ValueError): build(data)

    def test_duplicate_evidence_link_is_rejected(self):
        data = fixture(); data["links"].append(copy.deepcopy(data["links"][0]))
        with self.assertRaises(ValueError): build(data)

    def test_rule_evidence_uses_existing_label_and_relationship(self):
        data = fixture()
        data["links"].append({"ev_subject_cd": "RULE", "card_bnft_id": "benefit", "rule_key": "rule",
                              "evidence_id": "ev", "ev_link_id": "rule_link"})
        graph, stats = build(data)
        self.assertEqual(stats["relationships"]["df_supported_by"], 2)
        self.assertEqual(stats["nodes"]["df_bnft_rule"], 1)
        edge = next(e for e in graph.edges.values() if '"rule_link"' in e["source_json"])
        self.assertEqual(edge["type"], "df_supported_by")
        self.assertEqual(edge["start"], key("bnft_rule", 2, "benefit", "rule"))
        self.assertEqual(edge["end"], key("card_source_evidence", "ev"))

    def test_rule_evidence_for_missing_rule_is_rejected(self):
        data = fixture()
        data["links"].append({"ev_subject_cd": "RULE", "card_bnft_id": "benefit", "rule_key": "nope",
                              "evidence_id": "ev", "ev_link_id": "rule_link"})
        with self.assertRaises(KeyError): build(data)

    def test_rule_key_is_scoped_by_benefit(self):
        data = fixture()
        data["links"].append({"ev_subject_cd": "RULE", "card_bnft_id": "other", "rule_key": "rule",
                              "evidence_id": "ev", "ev_link_id": "rule_link"})
        with self.assertRaises(KeyError): build(data)

    def test_unknown_evidence_subject_is_still_rejected(self):
        data = fixture()
        data["links"].append({"ev_subject_cd": "REL", "card_bnft_id": "benefit", "evidence_id": "ev", "ev_link_id": "rel"})
        with self.assertRaises(ValueError): build(data)

    def test_removed_policy_subject_is_rejected(self):
        data = fixture()
        data["links"].append({"ev_subject_cd": "POLICY", "evidence_id": "ev", "ev_link_id": "old"})
        with self.assertRaises(ValueError): build(data)

    def test_benefit_pool_and_document_connect_directly_to_card(self):
        graph, stats = build(fixture())
        card = key("card_product", 2)
        for kind, end in (("df_has_benefit", key("card_bnft", 2, "benefit")),
                          ("df_has_pool", key("card_limit_pool", 2, "pool")),
                          ("df_has_document", key("card_doc", "20261101_000002"))):
            self.assertTrue(any(e["type"] == kind and e["start"] == card and e["end"] == end for e in graph.edges.values()), kind)
        self.assertNotIn("df_card_policy_version", stats["nodes"])
        self.assertNotIn("df_has_policy", stats["relationships"])

    def test_card_condition_and_evidence_hang_on_card(self):
        data = fixture()
        data["product"][0]["card_cond_expr"] = {"branches": [{"branch_no": 1, "atoms": [
            {"atom_key": "common", "atom_seq": 1, "negate_yn": True}]}]}
        data["links"].append({"ev_subject_cd": "CARD", "evidence_id": "ev", "ev_link_id": "card_link"})
        graph, stats = build(data)
        card, expr = key("card_product", 2), key("cond_expr", "card", 2)
        self.assertTrue(any(e["type"] == "df_has_expr" and e["start"] == card and e["end"] == expr for e in graph.edges.values()))
        self.assertTrue(any(e["type"] == "df_supported_by" and e["start"] == card for e in graph.edges.values()))
        self.assertIn('"negate_yn":true', graph.nodes[key("cond_atom", "card", 2, 1, "common")]["source_json"])

    def test_confirmed_card_condition_needs_review_of_guard(self):
        data = fixture(); data["product"][0]["card_cond_status_cd"] = "CONFIRMED"
        with self.assertRaises(ValueError): build(data)

    def test_dangling_edge_is_rejected(self):
        graph = Preview(); graph.edge("X", "missing", "missing", {})
        with self.assertRaises(ValueError): graph.validate()

    def test_every_label_and_type_uses_df_prefix_and_namespace(self):
        graph, stats = build(fixture())
        self.assertTrue(all(label.startswith("df_") for label in stats["nodes"]))
        self.assertTrue(all(kind.startswith("df_") for kind in stats["relationships"]))
        self.assertTrue(all(n["namespace"] == NS and n["key"].startswith(f'["{NS}",') for n in graph.nodes.values()))
        self.assertTrue(all(e["namespace"] == NS for e in graph.edges.values()))

    def test_node_has_no_test_marker(self):
        graph, _ = build(fixture())
        self.assertTrue(all("test_only" not in node for node in graph.nodes.values()))

    def test_key_components_are_not_ambiguous(self):
        self.assertNotEqual(key("T", "a|b", "c"), key("T", "a", "b|c"))


if __name__ == "__main__":
    unittest.main()
