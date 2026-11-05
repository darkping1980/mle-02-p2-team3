"""Neo4j 단일 하이브리드 검색(N) 테스트. 순위 계산은 Cypher에 있으므로 여기서는 구문 계약·파라미터·행 변환·연결을 본다.
실데이터 동등성(C 대비)은 RUN_NEO4J_INTEGRATION=1일 때만 읽기 전용으로 실행한다."""
import json
import os
import re
import unittest

from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag, execution_log
from card_benefit.payment_card.db_pipeline_origin_search import neo4j_hybrid_search as h
from card_benefit.payment_card.db_pipeline_origin_search.benefit_search_service import FETCH_PER_TABLE, RRF_K

WRITE = re.compile(r"(?<![.\w])(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP)\b")   # apoc.map.merge 같은 함수명은 제외


def hit_row(**changes):
    row = {"key": '["card_bnft",2,"B1"]', "is_card": True, "id": "B1", "bnft_cd": "c", "name": "버스", "bnft_type_cd": None,
           "card_id": 2, "product_nm": "P", "apply_cards": [], "search_text": "혜택명: 버스", "origin_cd": "PRODUCT", "rrf": 0.03,
           "channels": ["keyword", "vector"], "kw": 2, "sim": 0.5, "graph_targets": ["버스"], "target_terms": ["버스"],
           "excluded_terms": [], "own_card": True}
    return {**row, **changes}


class FakeNeo4jSearch:
    def __init__(self, result): self.result, self.calls = result, []
    def _run(self, statement_id, cypher, path, params):
        self.calls.append((statement_id, cypher, params))
        return [self.result]


class Emb:
    model_nm = "text-embedding-3-small"
    def embed(self, texts): return [[0.1] * 3 for _ in texts]


def result(**changes):
    base = {"identified": [2], "lim": 8, "completed": False, "merged": [], "pool_size": 116, "models": ["text-embedding-3-small"],
            "brand_warnings": [], "hits": [hit_row()]}
    return {**base, **changes}


class QueryContractTests(unittest.TestCase):
    def test_query_is_read_only_dp_scoped_and_ranks_in_cypher(self):
        q = h.HYBRID_SEARCH_QUERY
        self.assertNotRegex(q.upper(), WRITE)
        labels = set(re.findall(r"[(\[]\w*:(\w+)", q))
        self.assertTrue(labels and all(label.startswith("dp_") for label in labels), labels)
        for piece in ("vector.similarity.cosine(b.embedding, $qvec)", "apoc.coll.sortMulti", "$rrf_k", "$top_k", "$fetch",
                      "dp_same_as", "BNFT_EXCL", "$card_priority", "$complete_card", "$all_benefits"):
            self.assertIn(piece, q)

    def test_embedding_vectors_are_never_returned(self):
        returned = h.HYBRID_SEARCH_QUERY.split("// 8.")[1]
        self.assertNotRegex(returned, r"embedding\s*[:,]|\.embedding\b(?!_)")
        pool_map = h.HYBRID_SEARCH_QUERY.split("RETURN collect({key: b.key")[1].split("}) AS pool")[0]
        self.assertNotRegex(pool_map, r"b\.embedding(?!_)")                    # 풀 행에도 벡터를 담지 않는다(유사도 값만)

    def test_strict_word_boundary_only_for_latin_terms(self):
        self.assertIn("THEN toLower(f) =~ ('(?s).*(?<![0-9a-z-])' + t + '(?![0-9a-z-]).*')", h.HYBRID_SEARCH_QUERY)
        self.assertIn("ELSE toLower(f) CONTAINS t END", h.HYBRID_SEARCH_QUERY)

    def test_exclusion_split_matches_python_rule(self):
        from card_benefit.payment_card.db_pipeline.benefit_search_text import TOKEN_SPLIT
        self.assertIn("apoc.text.split(toLower(e), '[\\\\s,/()·\\\\[\\\\]:]+')", h.HYBRID_SEARCH_QUERY)
        self.assertEqual(TOKEN_SPLIT.pattern, r"[\s,/()·\[\]:]+")


class SearchCallTests(unittest.TestCase):
    def test_python_only_passes_interpretation_and_embedding(self):
        neo = FakeNeo4jSearch(result())
        out = h.Neo4jBenefitSearch(neo, Emb()).search("ONE PICK STYLE 카드의 주요 혜택을 알려줘.", "N", 8)
        statement_id, _, params = neo.calls[0]
        self.assertEqual(statement_id, "card.hybrid_search")
        self.assertEqual(params["terms"], ["one", "pick", "style", "주요"])
        self.assertTrue(params["all_benefits"])
        self.assertEqual((params["top_k"], params["fetch"], params["rrf_k"]), (8, FETCH_PER_TABLE, RRF_K))
        self.assertEqual(len(neo.calls), 1)                          # 후보 검색은 1문장
        self.assertEqual(out.hits[0].key, '["card_bnft",2,"B1"]')
        self.assertEqual((out.hits[0].keyword_score, out.hits[0].similarity, out.hits[0].target_terms), (2, 0.5, ["버스"]))
        self.assertIn("card_priority", out.engines)

    def test_parity_options_are_passed_through(self):
        neo = FakeNeo4jSearch(result(identified=[]))
        h.Neo4jBenefitSearch(neo, Emb(), strict_terms=False, card_priority=False, complete_card=False).search("q", "N", 5)
        params = neo.calls[0][2]
        self.assertEqual((params["strict"], params["card_priority"], params["complete_card"]), (False, False, False))

    def test_model_mismatch_is_refused(self):
        neo = FakeNeo4jSearch(result(models=["other-model"]))
        with self.assertRaisesRegex(ValueError, "모델"):
            h.Neo4jBenefitSearch(neo, Emb()).search("q", "N", 5)

    def test_brand_and_unapplied_warnings_keep_existing_text(self):
        common = hit_row(key='["card_common_bnft",1,"C1"]', is_card=False, id="C1", name="라운지", apply_cards=[])
        neo = FakeNeo4jSearch(result(hits=[common], brand_warnings=[{"id": "B9", "status": "REVIEW", "issues": json.dumps(["유효기간"])},
                                                                      {"id": "B8", "status": "SAME", "issues": "[]"}]))
        out = h.Neo4jBenefitSearch(neo, Emb()).search("q", "N", 5)
        self.assertIn("동일성 미확정, 병합하지 않음: B9 ['유효기간']", out.warnings)
        self.assertIn("공통 혜택 소유자를 확인하지 못해 병합하지 않음: B8", out.warnings)
        self.assertIn("카드 적용 관계가 없는 공통 혜택: ['라운지']", out.warnings)
        self.assertFalse(out.hits[0].applied)

    def test_all_benefits_intent_patterns(self):
        yes = ["ONE PICK STYLE 카드의 주요 혜택을 알려줘.", "더 심플 하나카드 혜택이 뭐야?", "JADE Classic 전체 혜택", "어떤 혜택이 있어?",
               "ONE PICK STYLE 카드의 전월 실적 조건과 혜택을 알려줘."]
        no = ["ONE PICK STYLE 카드의 대중교통 혜택은?", "대중교통 혜택 있어?", "DAILY 카드 넷플릭스 할인 한도 알려줘"]
        self.assertTrue(all(h.ALL_BENEFITS.search(q) for q in yes))
        self.assertFalse(any(h.ALL_BENEFITS.search(q) for q in no))


class PipelineWiringTests(unittest.TestCase):
    def test_neo4j_search_never_reads_postgresql_source(self):
        self.assertFalse(h.Neo4jBenefitSearch.reads_postgresql_source)
        self.assertEqual(h.Neo4jBenefitSearch.engine, "neo4j")

    def test_request_pipeline_passes_neo4j_mode_through(self):
        base = card_graphrag.CardGraphRAG(None, benefit_search=h.Neo4jBenefitSearch(None, None), search_mode="N")
        pipeline, cleanup = execution_log.request_pipeline(base, "N")
        self.assertIs(pipeline, base)
        cleanup()

    def test_common_evidence_fallback_comes_from_neo4j_link(self):
        rows = [{"ev_subject_cd": "BNFT", "ev_item_key": "-",
                 "evidence": json.dumps({"evidence_id": "E1", "page_no": 1, "quote_txt": "q", "approval_status_cd": "PENDING", "x": 1})}]

        class Neo:
            def _run(self, statement_id, cypher, path, params):
                self.params = params; return rows
        neo = Neo()
        detail = h.Neo4jBenefitSearch(neo, None).get_detail("pg:CARD_COMMON_BNFT:1:C1", ("evidence",))
        self.assertEqual(neo.params["key"], '["card_common_bnft",1,"C1"]')
        self.assertEqual(detail["evidence"][0]["link"], {"ev_subject_cd": "BNFT", "ev_item_key": "-"})
        self.assertEqual(json.loads(detail["evidence"][0]["evidence"]["source_json"]),
                         {"evidence_id": "E1", "page_no": 1, "quote_txt": "q", "approval_status_cd": "PENDING"})   # 기존 PG 대체 조회와 같은 4개 필드

    def test_retrieve_with_neo4j_search_skips_postgresql_read_source(self):
        key = '["card_bnft",2,"B"]'
        detail = {"context": {"benefit": {"name": "b", "source_json": json.dumps({"card_bnft_id": "B", "card_id": 2})},
                              "card": {"source_json": "{}"}}, "rules": [], "conditions": [], "limits": [], "evidence": []}

        class Graph:
            def get_details(self, keys, sections): return {k: json.loads(json.dumps(detail)) for k in keys}

        class NeoSearch(h.Neo4jBenefitSearch):
            @property
            def repository(self): raise AssertionError("PostgreSQL repository must not be used")
        state = {"request_id": "r", "question": "버스", "intent": "BENEFIT_DETAIL",
                 "search_parameters": {"benefit_ids": ["x"], "benefit_keys": [key], "sections": ["evidence"], "payment_amount": None}}
        out = card_graphrag.CardGraphRAG(Graph(), None, None, benefit_search=NeoSearch(None, None), search_mode="N").retrieve(state)
        self.assertNotIn("error", {k: v for k, v in out.items() if v})


@unittest.skipUnless(os.getenv("RUN_NEO4J_INTEGRATION") == "1", "실제 Neo4j 읽기 테스트는 명시적으로 켠다")
class LiveTermBoundaryTests(unittest.TestCase):
    def test_one_does_not_match_two_in_one_when_strict(self):
        from card_benefit.payment_card.db_pipeline_origin_search import neo4j_search
        search = neo4j_search.connect()
        try:
            strict = h.Neo4jBenefitSearch(search, None).search("ONE 혜택", "N", 50)
            loose = h.Neo4jBenefitSearch(search, None, strict_terms=False, card_priority=False, complete_card=False).search("ONE 혜택", "N", 50)
        finally:
            search.driver.close()
        # 임베딩 없이(키워드만) 비교한다. 기존 규칙은 "one"이 "Two-in-One"에 부분 일치하고, strict는 일치하지 않는다.
        self.assertFalse(any("two-in-one" in hit.bnft_nm.casefold() for hit in strict.hits))
        self.assertTrue(any("two-in-one" in hit.bnft_nm.casefold() for hit in loose.hits))
        self.assertTrue(any(hit.bnft_nm.casefold().startswith("one ") for hit in strict.hits))   # 낱말 "ONE"은 그대로 찾는다


if __name__ == "__main__":
    unittest.main()
