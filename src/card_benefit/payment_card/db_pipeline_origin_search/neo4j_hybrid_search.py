"""Neo4j-only keyword/vector RRF search over PostgreSQL table-mapped dp_ nodes."""
from __future__ import annotations

import json
import re
from time import perf_counter

from .search_contract import FETCH_PER_TABLE, RRF_K, SearchHit, SearchOutcome, search_terms
from .neo4j_search import CARD_LOG, REQUEST_ID, source

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
  AND ($item_ids IS NULL OR i.card_product_item_id IN $item_ids)
OPTIONAL MATCH (i)-[l:dp_supported_by {ev_subject_cd:'ITEM'}]->(e:dp_card_source_evidence)
WITH p,i,e ORDER BY e.evidence_id
RETURN p.card_id AS card_id,p.product_nm AS product_nm,i.card_product_item_id AS card_product_item_id,
        i.source_json AS item_source,i.item_data AS item_data,i.item_rule_txt AS item_rule_txt,
        i.item_cd AS item_cd,i.verification_status_cd AS verification_status_cd,
        [x IN collect(e.source_json) WHERE x IS NOT NULL] AS evidence
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

    def search(self, question: str, top_k: int = 5, use_graph: bool = True) -> SearchOutcome:
        """[N 모드 단일 검색기] 질문 임베딩 + Neo4j Cypher 벡터 검색 + 키워드 빈도 매칭 + RRF 순위 융합.

        PostgreSQL이나 별도 검색 엔진 없이 Neo4j 그래프와 임베딩만으로 실행되는 단일 검색 경로다.
        Java의 Repository/Search Service에서 두 개의 검색 결과(키워드, 벡터)를 가져와
        In-Memory RRF(Reciprocal Rank Fusion) 알고리즘으로 병합·정렬하는 과정에 해당한다.

        입력:
            question: 사용자 자연어 질문 문자열.
            top_k: 최종 반환할 상위 혜택 후보 수 (기본 5개).
            use_graph: 그래프 관계 탐색 여부.

        반환:
            SearchOutcome(mode="N", hits=SearchHit 목록, elapsed_ms, engines):
            각 SearchHit는 혜택 식별자, 카드명, 유사도 점수, 매칭 채널 정보를 포함한다.
        """
        started = perf_counter()
        embed_started = perf_counter()
        # 1. 질문 텍스트를 고차원 벡터로 변환 (외부 임베딩 API 또는 모델 호출)
        vector = self.embedder.embed([question])[0] if self.embedder is not None else None
        CARD_LOG.log_summary("PERF", REQUEST_ID.get(), phase="question_embedding", elapsed_ms=(perf_counter() - embed_started) * 1000,
                             calls=1 if self.embedder is not None else 0, dimensions=len(vector) if vector is not None else None)
        # 2. Neo4j Cypher 실행: 벡터 인덱스 기반 유사도(sim) 및 기본 혜택 속성 조회
        rows = self._run("card.hybrid_search", CANDIDATES_QUERY, qvec=vector)
        terms = [term.casefold() for term in search_terms(question)]
        cards = getattr(self.neo4j_search, "catalog_products", None)
        if cards is None:
            cards = self._run("card.products", PRODUCTS_QUERY)
        transform_started = perf_counter()
        # 3. 질문에서 특정 카드 상품명 식별 (단어 완전 일치 우선, 부분 일치 차선)
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
        # 4. 각 혜택 레코드에 대해 키워드 매칭 점수(kw) 및 식별된 카드 소속 여부(own_card) 판정
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
        # 5. 키워드 점수 및 벡터 점수 기준 각각 정렬
        keyword = sorted([r for r in candidates if r["kw"] > 0], key=lambda r: (-r["kw"], r["name"], r["key"]))
        vector_ranked = sorted([r for r in candidates if r["sim"] is not None], key=lambda r: (-r["sim"], r["key"]))
        keyword = keyword[:FETCH_PER_TABLE * 2]
        vector_ranked = vector_ranked[:FETCH_PER_TABLE * 2]
        # 6. RRF(Reciprocal Rank Fusion) 점수 융합: score += 1.0 / (RRF_K + rank)
        scores = {}
        for channel, ranked in (("keyword", keyword), ("vector", vector_ranked)):
            for rank, row in enumerate(ranked, start=1):
                item = scores.setdefault(row["key"], {"row": row, "score": 0.0, "channels": []})
                item["score"] += 1.0 / (RRF_K + rank)
                item["channels"].append(channel)
        fused = sorted(scores.values(), key=lambda x: (-x["score"], x["row"]["key"]))
        # 7. '모든 혜택' 질문 시 식별된 카드의 누락 혜택 전수 보완 및 카드 우선순위 반영
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
        CARD_LOG.log_summary("PERF", REQUEST_ID.get(), phase="hybrid_python_merge", elapsed_ms=(perf_counter() - transform_started) * 1000,
                             candidate_rows=len(rows), candidate_bytes=len(json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")),
                             selected=len(hits), products=len(cards))
        engines = (["neo4j_keyword"] if terms else []) + (["neo4j_vector"] if vector is not None else []) + ["neo4j_rrf"]
        CARD_LOG.log_summary("HYBRID", "neo4j", identified=identified or None, hits=len(hits), pool=len(candidates))
        return SearchOutcome("N", hits, (perf_counter()-started)*1000, [], [], engines)

    def catalog_rows(self, question, graph_catalog, top_k=8):
        """[후보 카탈로그 변환] Neo4j 전체 카탈로그와 N 모드 search() 결과를 결합하여 프롬프트용 행을 구성한다.

        interpret 노드에서 LLM에 전달할 후보 목록(rows)을 만들 때 호출된다.
        search(question, top_k)로 융합 랭킹 상위 혜택을 추출한 뒤,
        전체 그래프 카탈로그에서 매칭되는 상세 정보(카드명, 규칙 텍스트 등)를 매핑한다.

        입력:
            question: 사용자 질문 문자열.
            graph_catalog: Neo4j list_catalog()로 가져온 전체 혜택 목록 dict 리스트.
            top_k: 선별할 최대 후보 수 (기본 8개).

        반환:
            (rows: list[dict], outcome: SearchOutcome) 튜플.
        """
        from .neo4j_search import entity_ref
        catalog = {entity_ref(row["key"], row.get("id")): row for row in graph_catalog}
        outcome = self.search(question, top_k=top_k)
        rows = []
        for hit in outcome.hits:
            known = catalog.get(entity_ref(hit.key, hit.benefit_id))
            rows.append(known or {"key": hit.key, "id": hit.benefit_id, "name": hit.bnft_nm,
                                  "status": None, "card": ", ".join(c.get("product_nm", "") for c in hit.cards),
                                  "targets": [], "payment_min_amounts": []})
        return rows, outcome

    def get_detail(self, key: str, sections: tuple[str, ...]):
        return self.neo4j_search.get_detail(key, sections)

    def card_terms(self, card_ids: list[int], details: list[dict] | None = None) -> list[dict]:
        ids = sorted({int(value) for value in card_ids})
        if not ids:
            return []
        cached = getattr(self.neo4j_search, "catalog_terms", None)
        item_ids = None
        if cached is not None and details is not None:
            selected = {}
            for detail in details:
                context = detail.get("context") or {}
                benefit = source(context.get("benefit") or {})
                card_id = benefit.get("card_id")
                item_id = benefit.get("card_product_item_id")
                if card_id is not None and item_id:
                    selected.setdefault(int(card_id), []).append((str(item_id), detail))
            item_ids = []
            for card_id in ids:
                for row in cached.get(card_id, []):
                    data = row.get("item_data") if isinstance(row.get("item_data"), dict) else {}
                    scope = data.get("scope") if isinstance(data.get("scope"), dict) else {}
                    scope_cd = scope.get("scope_cd")
                    for item_id, detail in selected.get(card_id, []):
                        if scope_cd == "ALL_BENEFITS":
                            item_ids.append(row["card_product_item_id"])
                        elif scope_cd == "NAMED_ITEMS" and item_id in (scope.get("item_ids") or []):
                            item_ids.append(row["card_product_item_id"])
                        elif scope_cd == "PERFORMANCE":
                            spend = any(source(condition.get("atom") or {}).get("cond_type_cd") == "SPEND_REQ"
                                        and source(condition.get("atom") or {}).get("cond_basis_cd") not in ("TXN_AMT", "TRANSACTION_AMOUNT")
                                        for condition in detail.get("conditions") or [])
                            if spend:
                                item_ids.append(row["card_product_item_id"])
                        elif scope_cd not in {"ALL_BENEFITS", "NAMED_ITEMS", "PERFORMANCE"}:
                            # Unknown scope is not discarded; retain it for review.
                            item_ids.append(row["card_product_item_id"])
            item_ids = sorted(set(item_ids))
            if not item_ids:
                return []
        rows = self._run("card.terms", TERMS_QUERY, card_ids=ids, item_ids=item_ids)
        output = []
        for row in rows:
            item = source({"source_json": row["item_source"], "item_data": row.get("item_data"),
                           "item_rule_txt": row.get("item_rule_txt"), "item_cd": row.get("item_cd"),
                           "verification_status_cd": row.get("verification_status_cd")})
            output.append({"card_id": row["card_id"], "card_product_item_id": row["card_product_item_id"],
                           "item_cd": item.get("item_cd"), "item_nm": item.get("item_nm"),
                           "item_data": item.get("item_data"), "item_rule_txt": item.get("item_rule_txt"),
                           "verification_status_cd": item.get("verification_status_cd"), "product_nm": row["product_nm"],
                           "evidence": [{field: source({"source_json": ev}).get(field) for field in EVIDENCE_FIELDS}
                                        for ev in row["evidence"]]})
        return output
