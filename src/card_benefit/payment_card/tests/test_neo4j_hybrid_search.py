import json

from card_benefit.payment_card.db_pipeline_origin_search.neo4j_hybrid_search import (
    CANDIDATES_QUERY, Neo4jBenefitSearch,
)


class Embedder:
    def embed(self, texts):
        return [[0.1] * 1536 for _ in texts]


class FakeNeo4j:
    def __init__(self):
        self.calls = []
        self.rows = [{"key": json.dumps(["card_product_item", 23, "I1"]), "is_card": True,
                      "id": "I1", "bnft_cd": "P", "name": "모아포인트 추가적립",
                      "bnft_type_cd": "POINT", "search_text": "간편결제 포인트", "sim": 0.82,
                      "origin_cd": "PRODUCT", "card_id": 23, "product_nm": "카드의정석 POINT II",
                      "apply_cards": [{"card_id": 23, "product_nm": "카드의정석 POINT II"}],
                      "rule_text": "간편결제 추가 적립", "limit_text": "통합 월 적립 한도 2만원"}]

    def _run(self, statement_id, cypher, path, params):
        self.calls.append((statement_id, cypher, path, params))
        if statement_id == "card.hybrid_search":
            return self.rows
        if statement_id == "card.products":
            return [{"card_id": 23, "product_nm": "카드의정석 POINT II"}]
        raise AssertionError(statement_id)


def test_query_reads_only_new_table_faithful_labels_and_has_keyword_vector_fusion_inputs():
    assert "dp_card_product_item" in CANDIDATES_QUERY
    assert "dp_card_common_bnft" in CANDIDATES_QUERY
    assert "vector.similarity.cosine" in CANDIDATES_QUERY
    assert "dp_card_bnft" not in CANDIDATES_QUERY
    assert "dp_bnft_rule" not in CANDIDATES_QUERY
    assert "embedding AS" not in CANDIDATES_QUERY


def test_hybrid_search_returns_table_primary_key_and_rrf_channels():
    neo = FakeNeo4j()
    outcome = Neo4jBenefitSearch(neo, Embedder()).search(
        "카드의정석 POINT II 모아포인트 추가적립", top_k=5)
    assert outcome.hits
    hit = outcome.hits[0]
    assert hit.key == json.dumps(["card_product_item", 23, "I1"], separators=(",", ":"))
    assert hit.bnft_nm == "모아포인트 추가적립"
    assert neo.calls[0][0] == "card.hybrid_search"
    assert neo.calls[0][3]["qvec"] == [0.1] * 1536
    assert "neo4j_rrf" in outcome.engines


def test_card_name_is_identified_and_priority_retains_card_benefits():
    neo = FakeNeo4j()
    outcome = Neo4jBenefitSearch(neo, None).search("카드의정석 POINT II 추가적립", top_k=1)
    assert outcome.hits[0].cards[0]["card_id"] == 23
    assert Neo4jBenefitSearch(neo, None).reads_postgresql_source is False
