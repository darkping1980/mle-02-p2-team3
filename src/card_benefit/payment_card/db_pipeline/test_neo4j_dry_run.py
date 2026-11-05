import copy
import unittest

from card_benefit.payment_card.db_pipeline.neo4j_dry_run import GraphValidationError, PK_FIELDS, Preview, build, expected_counts, key

DOC = "D1"
COMMON_DOC = "D2"


def fixture():
    atom = lambda k, n: {"atom_key": k, "atom_seq": 1, "negate_yn": n}
    expr = {"branches": [{"branch_no": 1, "atoms": [atom("spend", False)]},
                         {"branch_no": 2, "atoms": [atom("grace", True)]}]}
    target = {"target_type_cd": "MERCHANT", "target_key": "CU", "target_nm": "CU"}
    return {
        "products": [{"card_id": 2, "card_cond_status_cd": "DRAFT", "card_cond_expr": None},
                     {"card_id": 5, "card_cond_status_cd": "DRAFT", "card_cond_expr": None}],
        "product_docs": [{"card_id": 2, "card_doc_id": DOC, "doc_role_cd": "PRODUCT_GUIDE"}],
        "documents": [{"card_doc_id": DOC}, {"card_doc_id": COMMON_DOC}],
        "pages": [{"card_doc_id": DOC, "page_no": 1}],
        "chunks": [{"card_doc_id": DOC, "page_no": 1, "card_doc_chunk_id": "chunk"}],
        "evidence": [{"card_doc_id": DOC, "page_no": 1, "card_doc_chunk_id": "chunk", "evidence_id": "ev", "approval_status_cd": "PENDING"}],
        "benefits": [{"card_id": 2, "card_bnft_id": "benefit", "bnft_cond_expr": expr,
                      "bnft_rule_txt": "결제 건당 100원", "bnft_limit_txt": "월 5천원 / 일 1회",
                      "rule_list": [{"rule_key": "rule", "target_list": [target], "cond_expr": None}]},
                     {"card_id": 5, "card_bnft_id": "other", "bnft_cond_expr": None,
                      "rule_list": [{"rule_key": "rule", "target_list": [target], "cond_expr": None}]}],
        "links": [{"card_id": 2, "ev_subject_cd": "BNFT", "card_bnft_id": "benefit", "evidence_id": "ev", "ev_link_id": "link"}],
        "commons": [{"card_common_id": 1, "common_cd": "VISA"}],
        "common_docs": [{"card_common_id": 1, "card_doc_id": COMMON_DOC}],
        "common_benefits": [{"card_common_id": 1, "card_common_bnft_id": "C1", "bnft_nm": "컨시어지"}],
        "common_applies": [{"card_common_id": 1, "card_common_bnft_id": "C1", "card_id": 5}],
        "brand_compare": [],
    }


class PreviewTests(unittest.TestCase):
    def test_or_negation_and_source_are_preserved(self):
        graph, stats = build(fixture())
        self.assertEqual(stats["nodes"]["dp_cond_branch"], 2)
        self.assertEqual(stats["nodes"]["dp_cond_atom"], 2)
        self.assertIn('"negate_yn":true', graph.nodes[key("cond_atom", "BNFT:2:benefit", 2, "grace")]["source_json"])
        self.assertEqual(stats["relationships"]["dp_supported_by"], 1)

    def test_limit_is_benefit_text_and_pool_graph_is_gone(self):
        graph, stats = build(fixture())
        self.assertNotIn("dp_card_limit_pool", stats["nodes"])
        self.assertFalse({"dp_has_pool", "dp_consumes"} & set(stats["relationships"]))
        self.assertIn('"bnft_limit_txt":"월 5천원 / 일 1회"', graph.nodes[key("card_bnft", 2, "benefit")]["source_json"])

    def test_all_products_are_converted(self):
        _, stats = build(fixture())
        self.assertEqual(stats["nodes"]["dp_card_product"], 2)
        self.assertEqual(stats["nodes"]["dp_card_bnft"], 2)

    def test_identifiers_are_postgres_primary_keys(self):
        graph, _ = build(fixture())
        self.assertEqual(graph.nodes[key("card_bnft", 2, "benefit")]["pk"], {"card_id": 2, "card_bnft_id": "benefit"})
        self.assertEqual(graph.nodes[key("card_common_bnft", 1, "C1")]["pk"], {"card_common_id": 1, "card_common_bnft_id": "C1"})
        self.assertEqual(PK_FIELDS["card_product"], ("card_id",))
        self.assertEqual(PK_FIELDS["card_doc_chunk"], ("card_doc_id", "page_no", "card_doc_chunk_id"))

    def test_target_is_shared_between_cards_for_reverse_search(self):
        _, stats = build(fixture())
        self.assertEqual(stats["nodes"]["dp_rule_target"], 1)
        self.assertEqual(stats["relationships"]["dp_targets"], 2)

    def test_common_benefit_connects_only_through_apply_rows(self):
        graph, stats = build(fixture())
        edges = [e for e in graph.edges.values() if e["type"] == "dp_has_common_benefit"]
        self.assertEqual([e["start"] for e in edges], [key("card_product", 5)])
        self.assertEqual(stats["relationships"]["dp_belongs_to"], 1)
        self.assertEqual(stats["common_benefits_without_direct_evidence"], ["C1"])
        self.assertFalse(any(e["type"] == "dp_supported_by" and e["start"] == key("card_common_bnft", 1, "C1") for e in graph.edges.values()))

    def test_link_tables_become_relationships_not_nodes(self):
        _, stats = build(fixture())
        for table in ("dp_card_product_doc", "dp_card_common_doc", "dp_card_common_bnft_apply", "dp_card_evidence_link"):
            self.assertNotIn(table, stats["nodes"])
        self.assertEqual(stats["relationships"]["dp_has_document"], 2)

    def test_same_as_is_created_only_for_same_status(self):
        data = fixture()
        row = {"card_id": 5, "card_bnft_id": "other", "bnft_cd": "X", "card_common_id": 1, "card_common_bnft_id": "C1", "issues": []}
        data["brand_compare"] = [{**row, "status": "REVIEW", "issues": ["유효기간"]}]
        self.assertNotIn("dp_same_as", build(data)[1]["relationships"])
        data["brand_compare"] = [{**row, "status": "SAME"}]
        self.assertEqual(build(data)[1]["relationships"]["dp_same_as"], 1)

    def test_expected_counts_come_from_source_rows(self):
        nodes, relationships = expected_counts(fixture())
        graph, stats = build(fixture())
        self.assertEqual((nodes, relationships), (stats["nodes"], stats["relationships"]))
        self.assertEqual(relationships["dp_has_document"], 2)

    def test_unlinked_candidate_evidence_is_reported_not_loaded(self):
        """등록 전 추출 후보의 인용(연결 없음)은 노드로 만들지 않고 보고만 한다. 연결된 근거는 그대로 올린다."""
        data = fixture()
        data["evidence"].append({"card_doc_id": DOC, "page_no": 1, "card_doc_chunk_id": "chunk", "evidence_id": "candidate",
                                 "card_extr_stg_id": "S1", "approval_status_cd": "PENDING"})
        graph, stats = build(data)
        self.assertNotIn(key("card_source_evidence", "candidate"), graph.nodes)
        self.assertIn(key("card_source_evidence", "ev"), graph.nodes)
        self.assertEqual(stats["unlinked_evidence"], ["candidate"])
        self.assertEqual(stats["nodes"]["dp_card_source_evidence"], 1)
        self.assertEqual(expected_counts(data), (stats["nodes"], stats["relationships"]))

    def test_all_errors_are_reported_instead_of_skipped(self):
        data = fixture()
        data["common_applies"].append({"card_common_id": 9, "card_common_bnft_id": "X", "card_id": 5})
        data["links"].append({"card_id": 2, "ev_subject_cd": "BNFT", "card_bnft_id": "none", "evidence_id": "ev", "ev_link_id": "bad"})
        data["product_docs"].append({"card_id": 99, "card_doc_id": DOC})
        with self.assertRaises(GraphValidationError) as caught:
            build(data)
        self.assertEqual(len(caught.exception.errors), 3)

    def test_broken_condition_is_reported(self):
        data = fixture()
        data["benefits"][0]["bnft_cond_expr"] = {"branches": [{"branch_no": 1}]}
        with self.assertRaisesRegex(GraphValidationError, "조건식 해석 실패"):
            build(data)

    def test_broken_rule_is_reported(self):
        data = fixture()
        data["benefits"][0]["rule_list"][0]["target_list"] = [{"target_nm": "CU"}]
        with self.assertRaisesRegex(GraphValidationError, "규칙 해석 실패"):
            build(data)

    def test_removed_pool_subject_is_rejected(self):
        data = fixture()
        data["links"].append({"card_id": 2, "ev_subject_cd": "POOL", "pool_id": "pool", "evidence_id": "ev", "ev_link_id": "old"})
        with self.assertRaises(ValueError):
            build(data)

    def test_wrong_evidence_page_is_rejected(self):
        data = fixture()
        data["evidence"][0]["page_no"] = 2
        with self.assertRaises(ValueError):
            build(data)

    def test_duplicate_evidence_link_is_rejected(self):
        data = fixture()
        data["links"].append(copy.deepcopy(data["links"][0]))
        with self.assertRaises(ValueError):
            build(data)

    def test_rule_evidence_uses_existing_label_and_relationship(self):
        data = fixture()
        data["links"].append({"card_id": 2, "ev_subject_cd": "RULE", "card_bnft_id": "benefit", "rule_key": "rule",
                              "evidence_id": "ev", "ev_link_id": "rule_link"})
        graph, stats = build(data)
        self.assertEqual(stats["relationships"]["dp_supported_by"], 2)
        edge = next(e for e in graph.edges.values() if '"rule_link"' in e["source_json"])
        self.assertEqual(edge["start"], key("bnft_rule", 2, "benefit", "rule"))
        self.assertEqual(edge["end"], key("card_source_evidence", "ev"))

    def test_relation_evidence_hangs_on_benefit_with_relation_key(self):
        data = fixture()
        data["benefits"].append({"card_id": 2, "card_bnft_id": "other", "bnft_cond_expr": None, "rule_list": []})
        data["benefits"][0]["relation_list"] = [{"relation_key": "fb", "to_bnft_id": "other", "rel_type_cd": "FALLBACK_AFTER_CAP"}]
        data["links"].append({"card_id": 2, "ev_subject_cd": "REL", "card_bnft_id": "benefit", "relation_key": "fb",
                              "evidence_id": "ev", "ev_link_id": "rel_link"})
        graph, stats = build(data)
        self.assertEqual(stats["relationships"]["dp_supported_by"], 2)
        edge = next(e for e in graph.edges.values() if '"rel_link"' in e["source_json"])
        self.assertEqual(edge["start"], key("card_bnft", 2, "benefit"))
        self.assertIn('"relation_key":"fb"', edge["source_json"])
        self.assertIn('"ev_subject_cd":"REL"', edge["source_json"])

    def test_relation_evidence_without_stored_relation_is_rejected(self):
        data = fixture()
        data["benefits"].append({"card_id": 2, "card_bnft_id": "other", "bnft_cond_expr": None, "rule_list": []})
        data["benefits"][0]["relation_list"] = [{"relation_key": "fb", "to_bnft_id": "other", "rel_type_cd": "FALLBACK_AFTER_CAP"}]
        for relation_key in ("missing", None):
            bad = copy.deepcopy(data)
            bad["links"].append({"card_id": 2, "ev_subject_cd": "REL", "card_bnft_id": "benefit", "relation_key": relation_key,
                                 "evidence_id": "ev", "ev_link_id": "rel_link"})
            with self.assertRaisesRegex(GraphValidationError, "근거 연결 대상 없음"):
                build(bad)

    def test_benefit_relations_have_direction_source_and_stable_keys(self):
        data = fixture()
        data["benefits"].append({"card_id": 2, "card_bnft_id": "destination", "bnft_cond_expr": None, "rule_list": []})
        relation = {"relation_key": "fallback", "to_bnft_id": "destination", "rel_type_cd": "FALLBACK_AFTER_CAP", "rel_priority": None}
        data["benefits"][0]["relation_list"] = [relation]
        graph, stats = build(data)
        edges = [(k, e) for k, e in graph.edges.items() if e["type"] == "dp_related_to"]
        self.assertEqual(stats["relationships"]["dp_related_to"], 1)
        self.assertEqual(edges[0][1]["start"], key("card_bnft", 2, "benefit"))
        self.assertEqual(edges[0][1]["end"], key("card_bnft", 2, "destination"))
        import json
        self.assertEqual(json.loads(edges[0][1]["source_json"]), relation)
        self.assertEqual(set(graph.edges), set(build(data)[0].edges))

    def test_benefit_relation_rejects_missing_or_other_card_target(self):
        data = fixture()
        data["benefits"][0]["relation_list"] = [{"relation_key": "bad", "to_bnft_id": "other", "rel_type_cd": "OVERRIDES"}]
        with self.assertRaisesRegex(GraphValidationError, "혜택 관계 대상 없음"):
            build(data)

    def test_rule_key_is_scoped_by_benefit(self):
        data = fixture()
        data["links"].append({"card_id": 2, "ev_subject_cd": "RULE", "card_bnft_id": "other", "rule_key": "rule",
                              "evidence_id": "ev", "ev_link_id": "rule_link"})
        with self.assertRaises(GraphValidationError):
            build(data)

    def test_card_condition_and_evidence_hang_on_card(self):
        data = fixture()
        data["products"][0]["card_cond_expr"] = {"branches": [{"branch_no": 1, "atoms": [
            {"atom_key": "common", "atom_seq": 1, "negate_yn": True}]}]}
        data["links"].append({"card_id": 2, "ev_subject_cd": "CARD", "evidence_id": "ev", "ev_link_id": "card_link"})
        graph, _ = build(data)
        card, expr = key("card_product", 2), key("cond_expr", "CARD:2")
        self.assertTrue(any(e["type"] == "dp_has_expr" and e["start"] == card and e["end"] == expr for e in graph.edges.values()))
        self.assertTrue(any(e["type"] == "dp_supported_by" and e["start"] == card for e in graph.edges.values()))

    def test_confirmed_card_condition_needs_review_of_guard(self):
        data = fixture()
        data["products"][0]["card_cond_status_cd"] = "CONFIRMED"
        with self.assertRaises(ValueError):
            build(data)

    def test_dangling_edge_is_rejected(self):
        graph = Preview()
        graph.edge("X", "missing", "missing", {})
        with self.assertRaises(ValueError):
            graph.validate()

    def test_every_label_and_type_uses_dp_prefix(self):
        _, stats = build(fixture())
        self.assertTrue(all(label.startswith("dp_") for label in stats["nodes"]))
        self.assertTrue(all(kind.startswith("dp_") for kind in stats["relationships"]))

    def test_undefined_label_is_rejected(self):
        with self.assertRaises(ValueError):
            Preview().node("card_limit_pool", ["x"], {})

    def test_key_components_are_not_ambiguous(self):
        self.assertNotEqual(key("T", "a|b", "c"), key("T", "a", "b|c"))


if __name__ == "__main__":
    unittest.main()
