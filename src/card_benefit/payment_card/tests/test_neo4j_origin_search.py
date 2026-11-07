"""Neo4j 조회 모듈 테스트. 실제 Neo4j 테스트는 RUN_NEO4J_INTEGRATION=1 일 때만 읽기 조회로 실행한다."""
import logging
import os
import re
import unittest

from card_benefit.payment_card.db_pipeline.neo4j_dry_run import PREFIX
from card_benefit.payment_card.db_pipeline_origin_search import neo4j_search, neo4j_hybrid_search


class FakeTx:
    def __init__(self, rows): self.rows, self.calls = rows, []
    def run(self, query, **params):
        self.calls.append((query, params))
        return [type("Record", (), {"data": lambda self, row=row: row})() for row in self.rows]


class FakeSession:
    def __init__(self, tx): self.tx = tx
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def execute_read(self, work): return work(self.tx)


class FakeDriver:
    def __init__(self, rows):
        self.tx, self.options = FakeTx(rows), []
    def session(self, **options):
        self.options.append(options)
        return FakeSession(self.tx)


class SearchTests(unittest.TestCase):
    def test_queries_are_scoped_and_parameterized(self):
        for query in neo4j_search.QUERIES.values():
            self.assertNotIn("namespace", query)
            self.assertIn("dp_", query)
            for word in ("DELETE ", "CREATE ", "MERGE ", " SET "):
                self.assertNotIn(word, query.upper())
        self.assertIn("$keyword", neo4j_search.LIST_QUERY)

    def test_queries_come_from_named_cypher_file(self):
        names = {"catalog", "common_catalog", "list_benefits", "candidate_relations", "benefit_relations", "benefit_context",
                 "benefit_evidence", "common_benefit_evidence",
                 "item_catalog", "item_evidence", *neo4j_search.HOP_QUERIES}
        self.assertEqual(set(neo4j_search.MAPPERS), {f"graph_questions.{name}" for name in names})
        self.assertEqual(set(neo4j_search.QUERIES.values()), set(neo4j_search.MAPPERS.values()))

    def test_benefit_relations_are_explicit_and_directional(self):
        driver = FakeDriver([{"key": "source", "relation_list": "[]", "item_data": "{}"}])
        rows = neo4j_search.Neo4jSearch(driver).benefit_relations("source")
        self.assertEqual(rows[0]["relation_list"], "[]")
        self.assertEqual(driver.tx.calls, [(neo4j_search.BENEFIT_RELATIONS_QUERY, {"key": "source"})])
        self.assertIn("b.relation_list AS relation_list", neo4j_search.BENEFIT_RELATIONS_QUERY)
        self.assertNotIn("dp_related_to", neo4j_search.BENEFIT_RELATIONS_QUERY)
        self.assertNotIn(neo4j_search.BENEFIT_RELATIONS_QUERY, neo4j_search.SECTION_QUERIES.values())

    def test_cypher_file_has_no_write_clause(self):
        for query in neo4j_search.MAPPERS.values():
            self.assertNotRegex(query.upper(), r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP)\b")

    def test_evidence_query_reads_rule_path(self):
        self.assertIn("dp_supported_by", neo4j_search.EVIDENCE_QUERY)
        self.assertNotIn("dp_bnft_rule", neo4j_search.EVIDENCE_QUERY)

    def test_every_query_uses_dp_names_only(self):
        for query in neo4j_search.MAPPERS.values():
            self.assertNotRegex(query, r"(?:^|[(:\[])A8|(?:^|[(:\[])fp_|(?:^|[(:\[])df_")
            names = set(re.findall(r"[(\[]\w*:(\w+)", query))
            self.assertTrue(names)
            self.assertTrue(all(name.startswith("dp_") for name in names), names)

    def test_search_and_loader_share_one_prefix(self):
        self.assertEqual(neo4j_search.GRAPH_PREFIX, PREFIX)

    def test_common_key_uses_common_evidence_path(self):
        key = '["card_common_bnft",1,"C1"]'
        context = {field: None for field in neo4j_search.CONTEXT_FIELDS}
        context.update({"benefit": {"card_common_bnft_id": "C1", "source_json": "{}"}, "card_sources": []})
        driver = FakeDriver([{"key": key, "context": [context], "evidence": []}])
        detail = neo4j_search.Neo4jSearch(driver).get_detail(key, ("evidence",))
        self.assertEqual(len(driver.tx.calls), 1)
        self.assertIn(neo4j_search.COMMON_EVIDENCE_QUERY.replace("$key", "key").rstrip().removesuffix(";"), driver.tx.calls[0][0])
        self.assertEqual(neo4j_search.source(detail["context"]["card"]), {"product_nm": "적용 카드 미확인"})
        self.assertEqual([item["statement_id"] for item in neo4j_search.detail_plan([key], ("evidence",))], ["card.detail_batch"])

    def test_common_evidence_requires_same_as_relation(self):
        self.assertIn("dp_supported_by", neo4j_search.COMMON_EVIDENCE_QUERY)
        self.assertNotIn("dp_same_as", neo4j_search.COMMON_EVIDENCE_QUERY)

    def test_legacy_rule_condition_queries_are_removed_and_json_fields_projected(self):
        query = neo4j_search.CONTEXT_QUERY
        self.assertIn("rule_list:b.rule_list", query)
        self.assertIn("item_cond_expr:b.item_cond_expr", query)
        self.assertNotIn("dp_cond_atom", query)
        self.assertNotIn("LIMIT 0", query)

    def test_every_query_has_statement_id(self):
        self.assertEqual(set(neo4j_search.QUERIES.values()), set(neo4j_search.STATEMENT_IDS))

    def test_source_preserves_unknown(self):
        self.assertEqual(neo4j_search.source({"source_json": '{"bnft_limit_txt": null}'}), {"bnft_limit_txt": None})

    def test_source_overlays_and_decodes_table_native_json_columns(self):
        value = neo4j_search.source({"source_json": '{"item_nm":"old","item_data":"{}"}',
                                    "item_nm": "new", "rule_list": '[{"rule_key":"r1"}]',
                                    "item_cond_expr": '{"branches":[]}'})
        self.assertEqual(value["item_nm"], "new")
        self.assertEqual(value["rule_list"][0]["rule_key"], "r1")
        self.assertEqual(value["item_cond_expr"], {"branches": []})
        self.assertEqual(value["item_data"], {})

    def test_query_is_read_only_and_logged_without_cypher_text(self):
        driver = FakeDriver([{"a": 1}])
        with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
            rows = neo4j_search.Neo4jSearch(driver).list_benefits("교통")
        self.assertEqual(rows, [{"a": 1}])
        self.assertEqual(driver.options[0]["default_access_mode"], neo4j_search.READ_ACCESS)
        self.assertEqual(driver.tx.calls[0][1], {"keyword": "교통"})
        self.assertIn("card.list", logs.output[0])
        self.assertIn("rows=1", logs.output[0])
        self.assertNotIn("MATCH (", logs.output[0].split("path=")[0])

    def test_debug_level_shows_cypher_text(self):
        with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "DEBUG") as logs:
            neo4j_search.Neo4jSearch(FakeDriver([])).list_benefits("교통")
        self.assertIn("MATCH (b:dp_card_product_item", " ".join(logs.output))

    def test_detail_log_shows_cypher_and_records_without_debug_level(self):
        driver = FakeDriver([{"benefit": {"limit_text": "MONTH", "source_json": '{"secret_like": 1}'}, "labels": ["dp_card_product_item"]}])
        token = neo4j_search.DETAIL_LOG.set(True)
        try:
            with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
                neo4j_search.Neo4jSearch(driver).list_benefits("x")
        finally:
            neo4j_search.DETAIL_LOG.reset(token)
        text = "\n".join(logs.output)
        for word in ("QUERY [", "MATCH (b:dp_card_product_item", "PARAMS", "RESULT DATA [", "benefit.limit_text", "MONTH"):
            self.assertIn(word, text)
        self.assertNotIn("source_json", text)

    def test_detail_log_cypher_has_values_like_recipe_combined_mode(self):
        token = neo4j_search.DETAIL_LOG.set(True)
        try:
            with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
                neo4j_search.Neo4jSearch(FakeDriver([])).get_detail("it's", ("evidence",))
        finally:
            neo4j_search.DETAIL_LOG.reset(token)
        block = next(line for line in logs.output if "card.detail_batch" in line and "QUERY" in line)
        cypher = block.split("=" * 72)[1]
        self.assertNotIn("$key", cypher)
        self.assertNotIn(":param", cypher)
        self.assertIn("PARAMS", block)
        self.assertIn("'keys':", block)

    def test_driver_still_receives_bound_query_when_detail_log_is_on(self):
        driver = FakeDriver([])
        token = neo4j_search.DETAIL_LOG.set(True)
        try:
            with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO"):
                neo4j_search.Neo4jSearch(driver).list_benefits("교통")
        finally:
            neo4j_search.DETAIL_LOG.reset(token)
        self.assertEqual(driver.tx.calls, [(neo4j_search.LIST_QUERY, {"keyword": "교통"})])
        self.assertIn("$keyword", driver.tx.calls[0][0])

    def test_detailed_hybrid_log_inlines_full_vector_but_keeps_preview_summary_and_bound_execution(self):
        driver = FakeDriver([])
        vector = [index / 1000 for index in range(1536)]
        parameters = {"qvec": vector}
        token = neo4j_search.DETAIL_LOG.set(True)
        try:
            with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
                neo4j_search.Neo4jSearch(driver)._run(
                    "card.hybrid_search", neo4j_hybrid_search.CANDIDATES_QUERY, "hybrid test", parameters)
        finally:
            neo4j_search.DETAIL_LOG.reset(token)
        query_log = next(line for line in logs.output if "QUERY [" in line)
        summary_log = next(line for line in logs.output if "CYPHER [" in line)
        self.assertIn("vector.similarity.cosine(b.embedding,[0.0, 0.001, 0.002", query_log)
        self.assertNotIn("$qvec", query_log)
        self.assertIn("PARAMS {'qvec': '<VECTOR [0.000000, 0.001000", query_log)
        self.assertIn("$qvec", driver.tx.calls[0][0])
        self.assertIs(driver.tx.calls[0][1]["qvec"], vector)
        self.assertIn("<VECTOR [0.000000, 0.001000", summary_log)

    def test_detailed_terms_log_keeps_bound_driver_call(self):
        driver = FakeDriver([])
        parameters = {"card_ids": [2], "item_ids": ["I-1"]}
        token = neo4j_search.DETAIL_LOG.set(True)
        try:
            with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
                neo4j_search.Neo4jSearch(driver)._run(
                    "card.terms", neo4j_hybrid_search.TERMS_QUERY, "terms test", parameters)
        finally:
            neo4j_search.DETAIL_LOG.reset(token)
        query_log = next(line for line in logs.output if "QUERY [" in line)
        self.assertIn("p.card_id IN [2]", query_log)
        self.assertIn("i.card_product_item_id IN ['I-1']", query_log)
        self.assertEqual(driver.tx.calls[0], (neo4j_hybrid_search.TERMS_QUERY, parameters))

    def test_info_level_has_no_cypher_text_or_records(self):
        with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
            neo4j_search.Neo4jSearch(FakeDriver([{"a": 1}])).list_benefits("x")
        self.assertEqual(sum("CYPHER" in line for line in logs.output), 1)
        self.assertEqual(sum("result_size" in line for line in logs.output), 1)
        self.assertNotIn("RESULT DATA", logs.output[0])

    def test_plan_matches_queries_get_detail_executes(self):
        driver = FakeDriver([{"card": {}}])
        sections = ("rules", "conditions", "evidence")
        neo4j_search.Neo4jSearch(driver).get_detail("k", sections)
        plan = neo4j_search.detail_plan(["k"], sections)
        self.assertEqual([query for query, _ in driver.tx.calls], [item["cypher"] for item in plan])
        self.assertEqual([params for _, params in driver.tx.calls], [item["parameters"] for item in plan])
        self.assertEqual([item["statement_id"] for item in plan], ["card.detail_batch"])

    def test_browser_cypher_has_values_and_no_parameters(self):
        item = neo4j_search.detail_plan(["it's"], ("evidence",))[0]
        self.assertNotIn("$key", item["browser_cypher"])
        self.assertIn("it\\'s", item["browser_cypher"])

    def test_flatten_record_shows_source_values_and_hides_internal(self):
        row = {"evidence": {"evidence_id": "E", "key": "k",
                            "source_json": '{"quote_txt": "원문"}'}, "labels": ["A", "B"], "rule_key": None}
        self.assertEqual(neo4j_search.flatten_record(row), {"evidence.evidence_id": "E", "evidence.quote_txt": "원문", "labels": "A, B", "rule_key": None})

    def test_sections_skip_unrequested_queries(self):
        context = {field: None for field in neo4j_search.CONTEXT_FIELDS}
        context.update({"benefit": {"source_json": "{}"}, "card_sources": []})
        driver = FakeDriver([{"key": "k", "context": [context], "evidence": []}])
        detail = neo4j_search.Neo4jSearch(driver).get_detail("k", ())
        queries = [query for query, _ in driver.tx.calls]
        self.assertEqual(len(queries), 1)
        self.assertEqual(detail["rules"], [])


@unittest.skipUnless(os.getenv("RUN_NEO4J_INTEGRATION") == "1", "실제 Neo4j 읽기 테스트는 명시적으로 켠다")
class LiveNeo4jTests(unittest.TestCase):
    """실제 PostgreSQL 테이블 매핑 그래프를 읽기 전용으로 확인한다."""

    @classmethod
    def setUpClass(cls):
        logging.getLogger(neo4j_search.CARD_LOGGER_NAME).setLevel(logging.WARNING)
        cls.search = neo4j_search.connect()
        cls.catalog = cls.search.list_catalog()

    @classmethod
    def tearDownClass(cls):
        cls.search.driver.close()
        logging.getLogger(neo4j_search.CARD_LOGGER_NAME).setLevel(logging.NOTSET)

    def test_catalog_and_point2_retrieve_pdf_evidence(self):
        point = next(row for row in self.catalog if row["id"] == "20261105_000100")
        detail = self.search.get_details([point["key"]], neo4j_search.ALL_SECTIONS)[point["key"]]
        self.assertIsNotNone(detail)
        evidence = {row["evidence"]["evidence_id"]: row for row in detail["evidence"]}
        self.assertIn("20261105_002745", evidence)
        self.assertIn("20261105_002740", evidence)
        for evidence_id in ("20261105_002745", "20261105_002740"):
            row = evidence[evidence_id]
            self.assertEqual(row["evidence"]["page_no"], 3)
            self.assertEqual(row["chunk"]["chunk_id"], "20261105_000176")

    def test_live_json_contract_spend_rules_payment_terms_and_card_scope(self):
        from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag
        from card_benefit.payment_card.db_pipeline_origin_search.neo4j_hybrid_search import Neo4jBenefitSearch

        point = next(row for row in self.catalog if row["id"] == "20261105_000100")
        point_detail = self.search.get_details([point["key"]])[point["key"]]
        self.assertGreaterEqual(len(point_detail["rules"]), 2)
        point_atoms = [neo4j_search.source(row["atom"]) for row in point_detail["conditions"]]
        self.assertTrue(any(atom.get("cond_type_cd") == "SPEND_REQ" and atom.get("cond_basis_cd") == "PREV_MONTH_SPEND"
                            for atom in point_atoms))
        point_context = card_graphrag.benefit_context(point_detail, previous_spend=600000)
        self.assertEqual(point_context["card"], "카드의정석 POINT II")
        self.assertTrue(any(atom.get("type") == "SPEND_REQ" for group in point_context["conditions"]
                            for branch in group["branches"] for atom in branch["atoms"]))

        one_pick = next(row for row in self.catalog if row["id"] == "20261101_000001")
        self.assertEqual(one_pick["payment_min_amounts"], [3000])
        one_pick_detail = self.search.get_details([one_pick["key"]])[one_pick["key"]]
        self.assertTrue(any(neo4j_search.source(row["atom"]).get("cond_basis_cd") == "TXN_AMT"
                            for row in one_pick_detail["conditions"]))

        terms_rows = Neo4jBenefitSearch(self.search).card_terms([point["card_id"]])
        terms, _ = card_graphrag.attach_terms([point_detail], terms_rows)
        for entry in terms:
            self.assertTrue(all(ref == "card_product_item:23:20261105_000100" for ref in entry["benefit_ids"]))

    def test_live_two_card_detail_scopes_do_not_mix(self):
        from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag
        keys = [row["key"] for row in self.catalog if row["id"] in {"20261105_000099", "20261105_000180"}]
        self.assertEqual(len(keys), 2)
        details = self.search.get_details(keys)
        cards = {neo4j_search.source(details[key]["context"]["card"]).get("product_nm") for key in keys}
        self.assertEqual(cards, {"더 심플 하나카드", "카드의정석2 DAILY"})
        for key in keys:
            self.assertEqual(card_graphrag.benefit_context(details[key])["card"],
                             neo4j_search.source(details[key]["context"]["card"]).get("product_nm"))

    def test_keyword_common_and_candidate_queries(self):
        point = next(row for row in self.catalog if row["id"] == "20261105_000100")
        keyword_rows = self.search.list_benefits("추가적립")
        self.assertTrue(any(row.get("id") == "20261105_000100" for row in keyword_rows))
        batched = self.search.list_benefits_many(["추가적립", "간편결제"])
        self.assertTrue(batched["추가적립"])
        self.assertTrue(self.search._query(neo4j_search.COMMON_CATALOG_QUERY))
        candidates = self.search.candidate_relations([point["id"]])
        self.assertIn("card_product_item:23:20261105_000100", candidates)
        common = next(row for row in self.catalog if row["key"].startswith('["card_common_bnft"'))
        common_detail = self.search.get_details([common["key"]], neo4j_search.ALL_SECTIONS)[common["key"]]
        self.assertIsNotNone(common_detail)

    def test_one_hop_card_benefit_and_two_hop_source_text_queries(self):
        card_ids = sorted({row["card_id"] for row in self.catalog if "ONE PICK STYLE" in row["card"]})
        one_hop = self.search.hop("hop1_card_benefits", card_ids=card_ids)
        two_hop = self.search.hop("hop2_card_rules", card_ids=card_ids)
        self.assertEqual(len(one_hop), 4)
        self.assertEqual(len(two_hop), 4)
        self.assertEqual({(row["card"], row["benefit"]) for row in one_hop},
                         {(row["card"], row["benefit"]) for row in two_hop})
        self.assertTrue(all(row["rule_text"] is not None for row in one_hop))
        self.assertTrue(all(row["rule_text"] is not None for row in two_hop))
        self.assertTrue(all(row["rule_list"] is not None or row["condition_json"] is not None for row in two_hop))


if __name__ == "__main__":
    unittest.main()
