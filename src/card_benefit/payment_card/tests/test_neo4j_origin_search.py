"""Neo4j 조회 모듈 테스트. 실제 Neo4j 테스트는 RUN_NEO4J_INTEGRATION=1 일 때만 읽기 조회로 실행한다."""
import logging
import os
import re
import unittest

from card_benefit.payment_card.db_pipeline.neo4j_dry_run import NS
from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag, neo4j_search


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
            self.assertIn("$ns", query)
            for word in ("DELETE ", "CREATE ", "MERGE ", " SET "):
                self.assertNotIn(word, query.upper())
        self.assertIn("$keyword", neo4j_search.LIST_QUERY)

    def test_queries_come_from_named_cypher_file(self):
        names = {"catalog", "list_benefits", "benefit_context", "benefit_rules", "benefit_conditions",
                 "benefit_limits", "benefit_evidence"}
        self.assertEqual(set(neo4j_search.MAPPERS), {f"graph_questions.{name}" for name in names})
        self.assertEqual(set(neo4j_search.QUERIES.values()), set(neo4j_search.MAPPERS.values()))

    def test_cypher_file_has_no_write_clause(self):
        for query in neo4j_search.MAPPERS.values():
            self.assertNotRegex(query.upper(), r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP)\b")

    def test_evidence_query_reads_rule_path(self):
        self.assertIn("df_has_rule", neo4j_search.EVIDENCE_QUERY)
        self.assertIn("+ rules AS owner", neo4j_search.EVIDENCE_QUERY)

    def test_every_query_uses_df_names_only(self):
        for query in neo4j_search.MAPPERS.values():
            self.assertNotRegex(query, r"A8|pf_")
            names = set(re.findall(r"[(\[]\w*:(\w+)", query))
            self.assertTrue(names)
            self.assertTrue(all(name.startswith("df_") for name in names), names)

    def test_search_and_loader_share_one_namespace(self):
        self.assertEqual(neo4j_search.NAMESPACE, NS)

    def test_condition_order_does_not_depend_on_label_names(self):
        query = neo4j_search.CONDITION_QUERY
        self.assertIn("ORDER BY owner_cd, rule_key, branch_no, a.atom_seq", query)
        self.assertNotIn("labels(owner)", query)

    def test_every_query_has_statement_id(self):
        self.assertEqual(set(neo4j_search.QUERIES.values()), set(neo4j_search.STATEMENT_IDS))

    def test_source_preserves_unknown(self):
        self.assertEqual(neo4j_search.source({"source_json": '{"rule_select_cd": null}'}), {"rule_select_cd": None})

    def test_query_is_read_only_and_logged_without_cypher_text(self):
        driver = FakeDriver([{"a": 1}])
        with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
            rows = neo4j_search.Neo4jSearch(driver).list_benefits("교통")
        self.assertEqual(rows, [{"a": 1}])
        self.assertEqual(driver.options[0]["default_access_mode"], neo4j_search.READ_ACCESS)
        self.assertEqual(driver.tx.calls[0][1], {"ns": neo4j_search.NAMESPACE, "keyword": "교통"})
        self.assertIn("card.list", logs.output[0])
        self.assertIn("rows=1", logs.output[0])
        self.assertNotIn("MATCH (", logs.output[0].split("path=")[0])

    def test_debug_level_shows_cypher_text(self):
        with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "DEBUG") as logs:
            neo4j_search.Neo4jSearch(FakeDriver([])).list_benefits("교통")
        self.assertIn("MATCH (c:df_card_product", " ".join(logs.output))

    def test_detail_log_shows_cypher_and_records_without_debug_level(self):
        driver = FakeDriver([{"benefit": {"limit_text": "MONTH", "source_json": '{"secret_like": 1}'}, "labels": ["df_card_bnft"]}])
        token = neo4j_search.DETAIL_LOG.set(True)
        try:
            with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
                neo4j_search.Neo4jSearch(driver).list_benefits("x")
        finally:
            neo4j_search.DETAIL_LOG.reset(token)
        text = "\n".join(logs.output)
        for word in ("QUERY [", "MATCH (c:df_card_product", "PARAMS", "RESULT DATA [", "benefit.limit_text", "MONTH"):
            self.assertIn(word, text)
        self.assertNotIn("source_json", text)

    def test_detail_log_cypher_has_values_like_recipe_combined_mode(self):
        token = neo4j_search.DETAIL_LOG.set(True)
        try:
            with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
                neo4j_search.Neo4jSearch(FakeDriver([])).get_detail("it's", ("limits",))
        finally:
            neo4j_search.DETAIL_LOG.reset(token)
        block = next(line for line in logs.output if "card.context" in line and "QUERY" in line)
        cypher = block.split("=" * 72)[1]
        self.assertNotIn("$ns", cypher)
        self.assertNotIn("$key", cypher)
        self.assertNotIn(":param", cypher)
        self.assertIn(f"namespace:'{neo4j_search.NAMESPACE}'", cypher)
        self.assertIn("PARAMS {'ns':", block)

    def test_driver_still_receives_bound_query_when_detail_log_is_on(self):
        driver = FakeDriver([])
        token = neo4j_search.DETAIL_LOG.set(True)
        try:
            with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO"):
                neo4j_search.Neo4jSearch(driver).list_benefits("교통")
        finally:
            neo4j_search.DETAIL_LOG.reset(token)
        self.assertEqual(driver.tx.calls, [(neo4j_search.LIST_QUERY, {"ns": neo4j_search.NAMESPACE, "keyword": "교통"})])
        self.assertIn("$ns", driver.tx.calls[0][0])

    def test_info_level_has_no_cypher_text_or_records(self):
        with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
            neo4j_search.Neo4jSearch(FakeDriver([{"a": 1}])).list_benefits("x")
        self.assertEqual(len(logs.output), 1)
        self.assertNotIn("RESULT DATA", logs.output[0])

    def test_plan_matches_queries_get_detail_executes(self):
        driver = FakeDriver([{"card": {}}])
        sections = ("rules", "conditions", "evidence")
        neo4j_search.Neo4jSearch(driver).get_detail("k", sections)
        plan = neo4j_search.detail_plan(["k"], sections)
        self.assertEqual([query for query, _ in driver.tx.calls], [item["cypher"] for item in plan])
        self.assertEqual([params for _, params in driver.tx.calls], [item["parameters"] for item in plan])
        self.assertEqual([item["statement_id"] for item in plan], ["card.context", "card.rules", "card.conditions", "card.evidence"])

    def test_browser_cypher_has_values_and_no_parameters(self):
        item = neo4j_search.statement_plan("card.limits", key="it's")
        self.assertNotIn("$ns", item["browser_cypher"])
        self.assertNotIn("$key", item["browser_cypher"])
        self.assertIn(f"namespace:'{neo4j_search.NAMESPACE}'", item["browser_cypher"])
        self.assertIn("it\\'s", item["browser_cypher"])

    def test_flatten_record_shows_source_values_and_hides_internal(self):
        row = {"evidence": {"evidence_id": "E", "key": "k", "namespace": "n",
                            "source_json": '{"quote_txt": "원문"}'}, "labels": ["A", "B"], "rule_key": None}
        self.assertEqual(neo4j_search.flatten_record(row), {"evidence.evidence_id": "E", "evidence.quote_txt": "원문", "labels": "A, B", "rule_key": None})

    def test_sections_skip_unrequested_queries(self):
        driver = FakeDriver([{"card": {}}])
        detail = neo4j_search.Neo4jSearch(driver).get_detail("k", ("limits",))
        queries = [query for query, _ in driver.tx.calls]
        self.assertEqual(queries, [neo4j_search.CONTEXT_QUERY, neo4j_search.LIMIT_QUERY])
        self.assertEqual(detail["rules"], [])


@unittest.skipUnless(os.getenv("RUN_NEO4J_INTEGRATION") == "1", "실제 Neo4j 읽기 테스트는 명시적으로 켠다")
class LiveNeo4jTests(unittest.TestCase):
    """실제 Aura 개발 그래프를 읽기 전용으로 확인한다."""

    @classmethod
    def setUpClass(cls):
        logging.getLogger(neo4j_search.CARD_LOGGER_NAME).setLevel(logging.WARNING)
        cls.search = neo4j_search.connect()
        cls.catalog = {row["name"]: row for row in cls.search.list_catalog()}

    @classmethod
    def tearDownClass(cls):
        cls.search.driver.close()
        logging.getLogger(neo4j_search.CARD_LOGGER_NAME).setLevel(logging.NOTSET)

    def detail(self, word):
        row = next(item for name, item in self.catalog.items() if word in name)
        return self.search.get_detail(row["key"])

    def test_browser_cypher_returns_same_records_as_bound_query(self):
        row = next(item for name, item in self.catalog.items() if "대중교통" in name)
        for item in neo4j_search.detail_plan([row["key"]], neo4j_search.ALL_SECTIONS):
            with self.search.driver.session(database=self.search.database, default_access_mode=neo4j_search.READ_ACCESS) as session:
                manual = session.execute_read(lambda tx, q=item["browser_cypher"]: [r.data() for r in tx.run(q)])
            bound = self.search._query(item["cypher"], key=row["key"])
            self.assertEqual(manual, bound, item["statement_id"])

    def test_four_benefits(self):
        self.assertEqual(len(self.catalog), 4)
        self.assertEqual({row["status"] for row in self.catalog.values()}, {"PENDING_REVIEW"})

    def test_transit_condition_keeps_or_branches_and_not(self):
        groups = card_graphrag.condition_groups(self.detail("대중교통")["conditions"])
        benefit = next(group for group in groups if group["scope"] == "혜택")
        self.assertEqual([branch["branch_no"] for branch in benefit["branches"]], [1, 2])
        atoms = {atom["atom_key"]: atom for atom in benefit["branches"][0]["atoms"]}
        self.assertTrue(atoms["spend_exclusions"]["negate"])
        self.assertFalse(atoms["transit_spend"]["negate"])
        self.assertEqual(benefit["branches"][1]["atoms"][0]["atom_key"], "transit_grace")

    def test_one_pick_and_style_have_different_limits(self):
        def limits(word):
            return sorted((item["pool"]["period"], item["pool"]["unit"], item["pool"]["value"])
                          for item in self.detail(word)["limits"])
        self.assertNotEqual(limits("ONE PICK"), limits("STYLE"))
        self.assertIn(("MONTH", "COUNT", 30), limits("ONE PICK"))
        self.assertIn(("MONTH", "COUNT", 10), limits("STYLE"))

    def test_evidence_links_to_document_and_is_pending(self):
        detail = self.detail("놀이공원")
        self.assertTrue(detail["evidence"])
        for row in detail["evidence"]:
            self.assertTrue(row["document"])
            self.assertTrue(row["page"]["page_no"])
        evidence = card_graphrag.collect_evidence([detail], "BENEFIT_DETAIL")
        self.assertEqual({item["approval_status"] for item in evidence}, {"PENDING"})


if __name__ == "__main__":
    unittest.main()
