import json
import os

from dotenv import load_dotenv
from neo4j import READ_ACCESS

from common.neo4j_connection import create_neo4j_driver
from card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import Neo4jSearch
from card_benefit.payment_card.db_pipeline_origin_search.neo4j_hybrid_search import Neo4jBenefitSearch
from card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import benefit_context

load_dotenv(".env")
database = os.environ["NEO4J_DATABASE"]
with create_neo4j_driver() as driver:
    with driver.session(database=database, default_access_mode=READ_ACCESS) as session:
        info = session.run("CALL db.info() YIELD name,id RETURN name,id").single().data()
        isolated = [r.data() for r in session.run("MATCH (n:dp_node) WHERE NOT (n)--() RETURN n.source_table AS table,n.key AS key LIMIT 20")]
        benefits = [r.data() for r in session.run("""
          MATCH (p:dp_card_product)-[:dp_has_item]->(b:dp_card_product_item {item_type_cd:'BENEFIT'})
          WHERE p.product_nm CONTAINS '카드의정석 POINT II'
            AND (b.item_nm CONTAINS '특별' OR b.item_nm CONTAINS '모아포인트')
          RETURN p.card_id AS card_id,p.product_nm AS card,b.key AS key,b.card_product_item_id AS item_id,
                 b.item_nm AS benefit,b.embedding AS embedding,b.item_rule_txt AS rule,b.item_limit_txt AS limit
          ORDER BY benefit
        """)]
    search = Neo4jSearch(driver, database)
    details = []
    for benefit in benefits:
        details.append(search.get_detail(benefit["key"], ("rules", "conditions", "limits", "evidence")))
    class FixedEmbedding:
        def __init__(self, vector): self.vector = vector
        def embed(self, texts): return [self.vector for _ in texts]
    first_vector = next((item["embedding"] for item in benefits if item.get("embedding")), None)
    outcome = Neo4jBenefitSearch(search, FixedEmbedding(first_vector) if first_vector else None).search(
        "카드의정석 POINT II에서 전월 실적이 60만원이면 특별·추가 적립의 통합 월 한도는 얼마야?", top_k=10)
    def safe_context(detail):
        try:
            return benefit_context(detail)
        except Exception as error:
            return {"error": type(error).__name__, "message": str(error)}
    print(json.dumps({"db": info, "isolated": isolated,
      "benefits": [{k:v for k,v in row.items() if k != "embedding"} for row in benefits],
      "details": [{"benefit_context": (safe_context(d) if d else None),
                   "raw_item_cond_expr": (d or {}).get("context",{}).get("benefit",{}).get("item_cond_expr"),
                   "raw_rule_list": (d or {}).get("context",{}).get("benefit",{}).get("rule_list"),
                   "extraction_source_count":len((d or {}).get("context",{}).get("extraction_sources",[])),
                   "evidence": [{"evidence_id": x["evidence"].get("evidence_id"),
                                 "page_no": x["page"].get("page_no"),
                                 "chunk_id": x["chunk"].get("card_doc_chunk_id"),
                                 "quote": x["evidence"].get("quote_txt"),
                                 "document": x["document"].get("doc_title")}
                                for x in (d or {}).get("evidence",[])]} for d in details],
      "search_hits": [{"name": h.bnft_nm,"key":h.key,"cards":h.cards,"sim":h.similarity,"kw":h.keyword_score}
                      for h in outcome.hits],"engines":outcome.engines},ensure_ascii=True,default=str,indent=2))
