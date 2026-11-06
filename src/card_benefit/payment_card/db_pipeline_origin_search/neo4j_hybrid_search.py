"""Neo4j-only keyword/vector RRF search over PostgreSQL table-mapped dp_ nodes."""
from __future__ import annotations

import json
import re
from time import perf_counter

from .benefit_search_service import FETCH_PER_TABLE, RRF_K, SearchHit, SearchOutcome, search_terms
from .neo4j_search import CARD_LOG, source

ENGINE = "neo4j"
GENERIC_CARD_TOKENS = ["카드", "하나", "체크카드", "신용카드", "체크", "신용", "하나카드", "우리카드"]
ALL_BENEFITS = re.compile(r"(주요|전체|모든|모두|어떤).*혜택|혜택\s*(전체|모두|목록)|혜택을\s*알려")

CANDIDATES_QUERY = """
CALL () {
  MATCH (b:dp_card_product_item {item_type_cd:'BENEFIT'})
  MATCH (p:dp_card_product)-[:dp_has_item]->(b)
  RETURN b.key AS key,true AS is_card,b.card_product_item_id AS id,b.item_cd AS bnft_cd,
         b.item_nm AS name,b.item_subtype_cd AS bnft_type_cd,b.search_text AS search_text,
         CASE WHEN b.embedding IS NULL OR $qvec IS NULL THEN null ELSE vector.similarity.cosine(b.embedding,$qvec) END AS sim,
         b.item_origin_cd AS origin_cd,b.card_id AS card_id,
         p.product_nm AS product_nm,[{card_id:p.card_id,product_nm:p.product_nm}] AS apply_cards,
         b.item_rule_txt AS rule_text,b.item_limit_txt AS limit_text
  UNION ALL
  MATCH (b:dp_card_common_bnft)
  OPTIONAL MATCH (b)-[:dp_applies_to]->(p:dp_card_product)
  WITH b,collect(DISTINCT CASE WHEN p IS NULL THEN null ELSE {card_id:p.card_id,product_nm:p.product_nm} END) AS applies
  RETURN b.key AS key,false AS is_card,b.card_common_bnft_id AS id,b.bnft_cd AS bnft_cd,
         b.bnft_nm AS name,b.bnft_type_cd AS bnft_type_cd,b.search_text AS search_text,
         CASE WHEN b.embedding IS NULL OR $qvec IS NULL THEN null ELSE vector.similarity.cosine(b.embedding,$qvec) END AS sim,
         'COMMON' AS origin_cd,null AS card_id,null AS product_nm,
         [x IN applies WHERE x IS NOT NULL] AS apply_cards,
         b.bnft_rule_txt AS rule_text,b.bnft_limit_txt AS limit_text
}
RETURN key,is_card,id,bnft_cd,name,bnft_type_cd,search_text,sim,origin_cd,card_id,product_nm,apply_cards,rule_text,limit_text
ORDER BY key
"""

PRODUCTS_QUERY = "MATCH (p:dp_card_product) RETURN p.card_id AS card_id,p.product_nm AS product_nm ORDER BY card_id"
TERMS_QUERY = """
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {item_type_cd:'TERMS'})
WHERE p.card_id IN $card_ids
OPTIONAL MATCH (i)-[l:dp_supported_by {ev_subject_cd:'ITEM'}]->(e:dp_card_source_evidence)
WITH p,i,e ORDER BY e.evidence_id
RETURN p.card_id AS card_id,p.product_nm AS product_nm,i.card_product_item_id AS card_product_item_id,
       i.source_json AS item_source,[x IN collect(e.source_json) WHERE x IS NOT NULL] AS evidence
ORDER BY card_id,card_product_item_id
"""
STATEMENTS = {"card.hybrid_search": "(dp_card_product_item|dp_card_common_bnft) keyword/vector + RRF",
              "card.products": "(dp_card_product)", "card.terms": "(dp_card_product)-[dp_has_item]->(TERMS)-[dp_supported_by]->(PDF evidence)"}
EVIDENCE_FIELDS = ("evidence_id", "page_no", "quote_txt", "approval_status_cd")


def _entity_key(hit: dict) -> str:
    if hit["is_card"]:
        return json.dumps(["card_product_item", int(hit["card_id"]), str(hit["id"])], ensure_ascii=False, separators=(",", ":"))
    return json.dumps(["card_common_bnft", _common_id(hit["key"]), str(hit["id"])], ensure_ascii=False, separators=(",", ":"))


def _common_id(key: str) -> int:
    parts = json.loads(key)
    if isinstance(parts, list) and len(parts) == 3:
        return int(parts[1])
    raise ValueError(f"invalid common benefit key {key!r}")


def _name_tokens(value: str) -> list[str]:
    return [token.casefold() for token in re.findall(r"[0-9A-Za-z가-힣]+", value)
            if len(token) > 1 and token not in GENERIC_CARD_TOKENS]


class Neo4jBenefitSearch:
    """Neo4j-only search adapter implementing the existing CardGraphRAG interface."""
    engine = ENGINE
    reads_postgresql_source = False

    def __init__(self, neo4j_search, embedder=None, strict_terms=True, card_priority=True, complete_card=True):
        self.neo4j_search = neo4j_search
        self.embedder = embedder
        self.strict_terms, self.card_priority, self.complete_card = strict_terms, card_priority, complete_card
        self.last_trace = {}

    def _run(self, statement_id, cypher, **params):
        return self.neo4j_search._run(statement_id, cypher, STATEMENTS[statement_id], params)

    def search(self, question: str, mode: str = "N", top_k: int = 5, use_graph: bool = True) -> SearchOutcome:
        started = perf_counter()
        vector = self.embedder.embed([question])[0] if self.embedder is not None else None
        rows = self._run("card.hybrid_search", CANDIDATES_QUERY, qvec=vector)
        terms = [term.casefold() for term in search_terms(question)]
        cards = self._run("card.products", PRODUCTS_QUERY)
        identified = []
        for card in cards:
            tokens = _name_tokens(card["product_nm"] or "")
            hits = [token for token in tokens if token in question.casefold()]
            if tokens and len(hits) == len(tokens):
                identified.append(card["card_id"])
        if not identified and cards:
            overlaps = [(sum(token in question.casefold() for token in _name_tokens(c["product_nm"] or "")), c["card_id"])
                        for c in cards]
            best = max((score for score, _ in overlaps), default=0)
            if best:
                identified = [card_id for score, card_id in overlaps if score == best]
        candidates = []
        for row in rows:
            row = dict(row)
            text = "\n".join(str(x or "") for x in (row.get("name"), row.get("search_text"), row.get("rule_text"), row.get("limit_text"))).casefold()
            if row["is_card"]:
                card_name = row.get("product_nm") or ""
                kw_fields = [card_name.casefold(), text]
                own = row.get("card_id") in identified
            else:
                kw_fields = [text, " ".join(x.get("product_nm", "") for x in row["apply_cards"]).casefold()]
                own = any(x.get("card_id") in identified for x in row["apply_cards"])
            row["kw"] = sum(any(term in field for field in kw_fields) for term in terms)
            row["sim"] = float(row["sim"]) if row.get("sim") is not None else None
            row["own_card"] = own
            row["key"] = _entity_key(row)
            candidates.append(row)
        keyword = sorted([r for r in candidates if r["kw"] > 0], key=lambda r: (-r["kw"], r["name"], r["key"]))
        vector_ranked = sorted([r for r in candidates if r["sim"] is not None], key=lambda r: (-r["sim"], r["key"]))
        keyword = keyword[:FETCH_PER_TABLE * 2]
        vector_ranked = vector_ranked[:FETCH_PER_TABLE * 2]
        scores = {}
        for channel, ranked in (("keyword", keyword), ("vector", vector_ranked)):
            for rank, row in enumerate(ranked, start=1):
                item = scores.setdefault(row["key"], {"row": row, "score": 0.0, "channels": []})
                item["score"] += 1.0 / (RRF_K + rank)
                item["channels"].append(channel)
        fused = sorted(scores.values(), key=lambda x: (-x["score"], x["row"]["key"]))
        all_benefits = bool(ALL_BENEFITS.search(question))
        if self.complete_card and all_benefits and identified:
            own_hits = [x for x in candidates if x["is_card"] and x["card_id"] in identified]
            present = {x["row"]["key"] for x in fused}
            fused = [{"row": x, "score": 0.0, "channels": []} for x in own_hits if x["key"] not in present] + fused
        if self.card_priority and identified:
            fused = [x for x in fused if x["row"]["own_card"]] + [x for x in fused if not x["row"]["own_card"]]
        selected = fused[:top_k]
        hits = []
        for item in selected:
            row = item["row"]
            applies = row["apply_cards"] if not row["is_card"] else [{"card_id": row["card_id"], "product_nm": row["product_nm"]}]
            hits.append(SearchHit("CARD_BNFT" if row["is_card"] else "CARD_COMMON_BNFT", row["key"], str(row["id"]),
                row.get("bnft_cd"), row["name"], row.get("bnft_type_cd"), applies, bool(applies), row.get("search_text"),
                row.get("sim"), row["kw"], row.get("origin_cd"), item["channels"], [], [], []))
        self.last_trace = {"identified_cards": identified, "pool": len(candidates), "keyword_candidates": len(keyword),
                           "vector_candidates": len(vector_ranked), "completed_card": all_benefits and bool(identified)}
        engines = (["neo4j_keyword"] if terms else []) + (["neo4j_vector"] if vector is not None else []) + ["neo4j_rrf"]
        CARD_LOG.log_summary("HYBRID", "neo4j", identified=identified or None, hits=len(hits), pool=len(candidates))
        return SearchOutcome(mode, hits, (perf_counter()-started)*1000, [], [], engines)

    def catalog_rows(self, question, mode, graph_catalog, top_k=8):
        from .neo4j_search import entity_ref
        catalog = {entity_ref(row["key"], row.get("id")): row for row in graph_catalog}
        outcome = self.search(question, mode, top_k)
        rows = []
        for hit in outcome.hits:
            known = catalog.get(entity_ref(hit.key, hit.benefit_id))
            rows.append(known or {"key": hit.key, "id": hit.benefit_id, "name": hit.bnft_nm,
                                  "status": None, "card": ", ".join(c.get("product_nm", "") for c in hit.cards),
                                  "targets": [], "payment_min_amounts": []})
        return rows, outcome

    def get_detail(self, key: str, sections: tuple[str, ...]):
        if key.startswith("pg:CARD_BNFT:"):
            _, _, owner, benefit_id = key.split(":", 3)
            key = json.dumps(["card_product_item", int(owner), benefit_id], ensure_ascii=False, separators=(",", ":"))
        elif key.startswith("pg:CARD_COMMON_BNFT:"):
            _, _, owner, benefit_id = key.split(":", 3)
            key = json.dumps(["card_common_bnft", int(owner), benefit_id], ensure_ascii=False, separators=(",", ":"))
        return self.neo4j_search.get_detail(key, sections)

    def card_terms(self, card_ids: list[int]) -> list[dict]:
        ids = sorted({int(value) for value in card_ids})
        if not ids:
            return []
        rows = self._run("card.terms", TERMS_QUERY, card_ids=ids)
        output = []
        for row in rows:
            item = source({"source_json": row["item_source"]})
            output.append({"card_id": row["card_id"], "card_product_item_id": row["card_product_item_id"],
                           "item_cd": item.get("item_cd"), "item_nm": item.get("item_nm"),
                           "item_data": item.get("item_data"), "item_rule_txt": item.get("item_rule_txt"),
                           "verification_status_cd": item.get("verification_status_cd"), "product_nm": row["product_nm"],
                           "evidence": [{field: source({"source_json": ev}).get(field) for field in EVIDENCE_FIELDS}
                                        for ev in row["evidence"]]})
        return output
