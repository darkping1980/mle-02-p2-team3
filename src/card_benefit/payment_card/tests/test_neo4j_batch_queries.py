"""P3 Neo4j 묶음 조회 테스트. 실제 Neo4j에 접속하지 않는다(실데이터 동등성은 별도 읽기 전용 검증으로 확인)."""
import json
import re
import unittest

from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag, neo4j_search as n
from card_benefit.payment_card.db_pipeline_origin_search.benefit_search_service import BenefitSearchService

WRITE = re.compile(r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP)\b")


class FakeDriver:
    """_run이 보내는 문장과 파라미터를 기록하고, 문장 종류별로 준비한 행을 돌려준다."""

    def __init__(self, rows_by_kind):
        self.rows_by_kind, self.calls = rows_by_kind, []

    def session(self, **_):
        driver = self

        class Session:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def execute_read(self, work):
                class Tx:
                    def run(self, query, **params):
                        driver.calls.append((query, params))
                        kind = ("detail" if query.startswith("UNWIND $keys") else "list" if query.startswith("UNWIND $keywords")
                                else "catalog" if query.startswith("OPTIONAL CALL ()") else "other")
                        rows = driver.rows_by_kind[kind]
                        rows = rows(params) if callable(rows) else rows
                        return [type("R", (), {"data": lambda self, r=r: r})() for r in rows]
                return work(Tx())
        return Session()


class GeneratedCypherTests(unittest.TestCase):
    def all_batches(self):
        sections = [n.ALL_SECTIONS, ("rules", "conditions", "evidence"), ("evidence",), ()]
        return [n.LIST_BATCH_QUERY, n.CATALOG_BATCH_QUERY] + [
            n.detail_batch_query(q, s) for q in (n.EVIDENCE_QUERY, n.COMMON_EVIDENCE_QUERY, n.ITEM_EVIDENCE_QUERY) for s in sections]

    def test_batches_are_read_only_and_dp_scoped(self):
        for query in self.all_batches():
            self.assertNotRegex(query.upper(), WRITE)
            self.assertNotRegex(query, r"(?:^|[(:\[])fp_|(?:^|[(:\[])A8|(?:^|[(:\[])df_")
            labels = set(re.findall(r"[(\[]\w*:(\w+)", query))
            self.assertTrue(labels and all(label.startswith("dp_") for label in labels), labels)

    def test_batches_embed_named_queries_verbatim(self):
        detail = n.detail_batch_query(n.EVIDENCE_QUERY, n.ALL_SECTIONS)
        for query in (n.CONTEXT_QUERY, n.EVIDENCE_QUERY):
            self.assertIn(query.replace("$key", "key").rstrip().removesuffix(";"), detail)
        self.assertIn(n.LIST_QUERY.replace("$keyword", "keyword").rstrip().removesuffix(";"), n.LIST_BATCH_QUERY)
        for query in (n.CATALOG_QUERY, n.ITEM_CATALOG_QUERY, n.COMMON_CATALOG_QUERY):
            self.assertIn(query.rstrip().removesuffix(";"), n.CATALOG_BATCH_QUERY)
            self.assertFalse(n.CATALOG_BATCH_QUERY.endswith(";"))

    def test_subqueries_remove_standalone_cypher_terminators(self):
        for query in self.all_batches():
            self.assertNotRegex(query, r";\s*\n\s*}\s*")

    def test_only_batch_parameters_remain(self):
        for query in self.all_batches():
            self.assertTrue(set(re.findall(r"\$(\w+)", query)) <= {"keys", "keywords"}, query[:80])

    def test_unrequested_sections_are_not_queried(self):
        query = n.detail_batch_query(n.EVIDENCE_QUERY, ("evidence",))
        self.assertNotIn("LIMIT 0", query)
        self.assertIn("AS evidence", query)

    def test_evidence_projection_preserves_chunk_page_document(self):
        self.assertTrue({"owner", "evidence_labels", "chunk", "page", "document"} <= set(n.SECTION_FIELDS["evidence"]))
        query = n.detail_batch_query(n.EVIDENCE_QUERY, ("evidence",))
        collected = query.split("OPTIONAL CALL (key) {")[1].split("}\n", 1)[1]
        self.assertIn("chunk:", collected)
        self.assertIn("(chunk:dp_card_doc_chunk)", query)           # MATCH 경로는 그대로(같은 근거만 조회)

    def test_registries_are_unchanged(self):
        self.assertEqual(set(n.QUERIES.values()), set(n.STATEMENT_IDS))
        self.assertNotIn(n.LIST_BATCH_QUERY, n.STATEMENT_IDS)


class BatchMappingTests(unittest.TestCase):
    def test_get_details_maps_rows_like_get_detail(self):
        bnft, common, missing = '["card_product_item",2,"B"]', '["card_common_bnft",1,"C"]', '["card_product_item",2,"X"]'
        context = {field: None for field in n.CONTEXT_FIELDS} | {
            "benefit": {"card_product_item_id": "B", "source_json": '{"item_nm":"b","item_limit_txt":"월 1천원"}',
                        "rule_list": '[{"rule_key":"r1","target_list":[{"target_nm":"x"}]}]',
                        "item_cond_expr": '{"branches":[]}'},
            "card_sources": ['{"product_nm":"P"}']}
        common_context = {**context, "card_sources": []}

        def rows(params):
            out = []
            for key in params["keys"]:
                if key == missing:
                    continue
                out.append({"key": key, "context": [common_context if key == common else context],
                            "evidence": [{**{field: None for field in n.SECTION_FIELDS["evidence"]}, "evidence": {"source_json": "{}"}, "link": {}, "rule_key": None, "owner_labels": ["x"]}]})
            return out
        driver = FakeDriver({"detail": rows})
        result = n.Neo4jSearch(driver).get_details([bnft, common, missing, bnft], n.ALL_SECTIONS)
        self.assertEqual(set(result), {bnft, common, missing})
        self.assertIsNone(result[missing])
        self.assertEqual(len(driver.calls), 2)                       # 근거 Cypher 종류(혜택·공통)별 1문장
        self.assertEqual(result[bnft]["rules"][0]["rule"]["rule_key"], "r1")
        self.assertEqual(result[bnft]["rules"][0]["targets"], ["x"])
        self.assertEqual(result[bnft]["limits"], [{"limit_text": "월 1천원"}])
        self.assertEqual(list(result[bnft]["evidence"][0]), list(n.SECTION_FIELDS["evidence"]))
        self.assertEqual(n.source(result[common]["context"]["card"]), {"product_nm": "적용 카드 미확인"})   # get_detail과 같은 표시 처리
        self.assertIn(n.COMMON_EVIDENCE_QUERY.replace("$key", "key").rstrip().removesuffix(";"),
                      driver.calls[1][0] + driver.calls[0][0])

    def test_unrequested_sections_are_empty_lists(self):
        driver = FakeDriver({"detail": lambda p: [{"key": k, "context": [{f: None for f in n.CONTEXT_FIELDS}], "evidence": []}
                                                    for k in p["keys"]]})
        detail = n.Neo4jSearch(driver).get_details(['["card_bnft",2,"B"]'], ("evidence",))['["card_bnft",2,"B"]']
        self.assertEqual((detail["rules"], detail["conditions"], detail["limits"]), ([], [], []))

    def test_list_benefits_many_groups_by_keyword(self):
        driver = FakeDriver({"list": [{"keyword": "교통", "key": "k1", "name": "n", "id": "i", "status": None},
                                      {"keyword": "교통", "key": "k2", "name": "n2", "id": "i2", "status": None}]})
        result = n.Neo4jSearch(driver).list_benefits_many([" 교통 ", "카드", "교통"])
        self.assertEqual(list(result), ["교통", "카드"])
        self.assertEqual([row["key"] for row in result["교통"]], ["k1", "k2"])
        self.assertEqual(result["카드"], [])
        self.assertEqual(driver.calls[0][1], {"keywords": ["교통", "카드"]})
        self.assertEqual(n.Neo4jSearch(FakeDriver({})).list_benefits_many([]), {})

    def test_list_catalog_uses_one_statement_and_same_row_processing(self):
        catalog = [{"key": "a", "name": "A", "id": "1", "status": None, "card_source": '{"product_nm":"P"}',
                    "rule_list": "[]", "item_cond_expr": "{}", "item_rule_txt": "룰", "item_limit_txt": "한도"}]
        commons = [{"key": "c", "name": "C", "id": "2", "status": None, "common_nm": "S", "cards": []}]
        driver = FakeDriver({"catalog": [{"catalog": catalog, "items": [], "commons": commons, "products": [{"card_id": 1, "product_nm": "P"}]}]})
        rows = n.Neo4jSearch(driver).list_catalog()
        self.assertEqual(len(driver.calls), 1)
        expected = n.catalog_rows([dict(r) for r in catalog], [], [dict(r) for r in commons])
        self.assertEqual(rows, expected)
        self.assertEqual(rows[1]["card"], "적용 카드 미확인")


class CallerFallbackTests(unittest.TestCase):
    def test_keyword_scoring_same_with_batch_and_per_term(self):
        class Repo:
            def rows(self, name, **_):
                if name == "keyword_card_bnft":
                    return [{"card_id": 2, "card_bnft_id": "B1", "bnft_cd": "c", "bnft_nm": "버스", "bnft_type_cd": None,
                             "product_nm": "P", "keyword_score": 1}]
                return []

        class PerTerm:
            def list_benefits(self, term):
                return [{"key": '["card_bnft",2,"B1"]', "id": "B1"}] if term in ("버스", "교통") else []

        class Batch(PerTerm):
            def list_benefits_many(self, terms):
                return {term: self.list_benefits(term) for term in terms}

        scores = []
        for graph in (PerTerm(), Batch()):
            service = BenefitSearchService.__new__(BenefitSearchService)
            service.repository, service.neo4j_search = Repo(), graph
            scores.append([(h.key, h.keyword_score) for h in service._keyword("버스 교통 혜택", [])])
        self.assertEqual(scores[0], scores[1])
        self.assertEqual(scores[0][0][1], 3)

    def test_retrieve_uses_batch_once_and_falls_back_without_it(self):
        key = '["card_bnft",2,"B"]'
        detail = {"context": {"benefit": {"name": "b", "source_json": json.dumps({"card_bnft_id": "B"})},
                              "card": {"source_json": "{}"}},
                  "rules": [], "conditions": [], "limits": [], "evidence": []}

        class PerKey:
            def __init__(self): self.calls = []
            def get_detail(self, k, sections): self.calls.append(("one", k)); return json.loads(json.dumps(detail))

        class Batch(PerKey):
            def get_details(self, keys, sections): self.calls.append(("batch", tuple(keys))); return {k: json.loads(json.dumps(detail)) for k in keys}

        state = {"request_id": "r", "question": "q", "intent": "BENEFIT_DETAIL",
                 "search_parameters": {"benefit_ids": ["x"], "benefit_keys": [key], "sections": ["evidence"], "payment_amount": None}}
        results = []
        for search in (PerKey(), Batch()):
            out = card_graphrag.CardGraphRAG(search, None, None).retrieve(state)
            results.append(out["retrieved_data"])
            self.assertEqual(search.calls, [("one", key)] if type(search) is PerKey else [("batch", (key,))])
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
