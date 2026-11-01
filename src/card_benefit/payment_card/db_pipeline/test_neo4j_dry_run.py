import copy
import unittest

from src.card_benefit.payment_card.db_pipeline.neo4j_dry_run import Preview, build, key


def fixture():
    atom = lambda k, n: {"atom_key": k, "atom_seq": 1, "negate_yn": n}
    expr = {"branches": [{"branch_no": 1, "atoms": [atom("spend", False)]},
                         {"branch_no": 2, "atoms": [atom("grace", True)]}]}
    return {
        "product": [{"card_id": 2}],
        "policy": [{"policy_status_cd": "DRAFT", "policy_cond_expr": None}],
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
        self.assertEqual(stats["nodes"]["A8Branch"], 2)
        self.assertEqual(stats["nodes"]["A8Condition"], 2)
        self.assertIn('"negate_yn":true', graph.nodes[key("Condition", "benefit", 2, "20261101_000001", "benefit", 2, "grace")]["source_json"])
        self.assertEqual(stats["relationships"]["A8_SUPPORTED_BY"], 1)
        self.assertEqual(stats["relationships"]["A8_CONSUMES"], 1)

    def test_missing_pool_is_rejected(self):
        data = fixture(); data["pools"] = []
        with self.assertRaises(KeyError): build(data)

    def test_wrong_evidence_page_is_rejected(self):
        data = fixture(); data["evidence"][0]["page_no"] = 2
        with self.assertRaises(ValueError): build(data)

    def test_duplicate_evidence_link_is_rejected(self):
        data = fixture(); data["links"].append(copy.deepcopy(data["links"][0]))
        with self.assertRaises(ValueError): build(data)

    def test_dangling_edge_is_rejected(self):
        graph = Preview(); graph.edge("X", "missing", "missing", {})
        with self.assertRaises(ValueError): graph.validate()

    def test_key_components_are_not_ambiguous(self):
        self.assertNotEqual(key("T", "a|b", "c"), key("T", "a", "b|c"))


if __name__ == "__main__":
    unittest.main()
