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
// 1. 카드별 BENEFIT 항목을 카드 상품 관계로 연결하고, 혜택 임베딩과 질문 벡터의 코사인 유사도를 계산한다.
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
  // 2. 공통 혜택도 같은 결과 열 형태로 조회하고, dp_applies_to 카드 목록을 중복 제거해 붙인다.
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
// 3. 두 후보 집합을 통일된 열 이름으로 내보낸다. 키워드 점수와 RRF 순위 계산은 Python에서 수행한다.
RETURN key,is_card,id,bnft_cd,name,bnft_type_cd,search_text,sim,origin_cd,card_id,product_nm,apply_cards,rule_text,limit_text
ORDER BY key
"""

# 카드명 식별을 위한 보조 메타데이터 조회. 상품 이름과 card_id만 반환한다.
PRODUCTS_QUERY = "MATCH (p:dp_card_product) RETURN p.card_id AS card_id,p.product_nm AS product_nm ORDER BY card_id"
TERMS_QUERY = """
// 선택 카드의 TERMS 항목과 적용 범위에 맞는 PDF 근거를 조회한다.
MATCH (p:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {item_type_cd:'TERMS'})
WHERE p.card_id IN $card_ids
  AND ($item_ids IS NULL OR i.card_product_item_id IN $item_ids)
// 근거 관계가 없는 TERMS도 남기고, 근거가 있는 경우 evidence_id 순으로 모은다.
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
    """카드 전용 혜택과 공통 혜택의 ID 중복을 피하도록 노드 종류를 포함한 검색 키를 만든다."""
    if hit["is_card"]:
        return json.dumps(["card_product_item", int(hit["card_id"]), str(hit["id"])], ensure_ascii=False, separators=(",", ":"))
    return json.dumps(["card_common_bnft", _common_id(hit["key"]), str(hit["id"])], ensure_ascii=False, separators=(",", ":"))


def _common_id(key: str) -> int:
    parts = json.loads(key)
    if isinstance(parts, list) and len(parts) == 3:
        return int(parts[1])
    raise ValueError(f"invalid common benefit key {key!r}")


def _name_tokens(value: str) -> list[str]:
    """카드명 비교용 토큰을 만든다. 한 글자와 일반 카드 종류 단어는 식별 점수에서 제외한다."""
    return [token.casefold() for token in re.findall(r"[0-9A-Za-z가-힣]+", value)
            if len(token) > 1 and token not in GENERIC_CARD_TOKENS]


class Neo4jBenefitSearch:
    """N 모드 검색 어댑터. Neo4j는 후보·유사도를 조회하고 Python은 키워드 점수와 RRF를 결합한다."""
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
        """N 모드 후보 검색을 수행하고, 카드 식별·키워드/벡터 랭킹·RRF·우선순위 보정을 적용한다.

        질문 임베딩은 embedder에 요청하고, Cypher는 카드/공통 혜택 후보와 cosine 유사도(sim)를 반환한다.
        질문 키워드 매칭, 채널별 정렬, RRF 합산, 카드 우선 배치, top_k 자르기는 Python 처리다.
        """
        started = perf_counter()                                      # 전체 검색 소요 시간 측정을 위한 시작 타임스탬프 (Java System.nanoTime() 유사)
        # 질문 벡터를 만들고 Neo4j가 반환하는 sim을 받는다. 이 Cypher에는 키워드 필터나 RRF 계산이 없다.
        embed_started = perf_counter()                                # 질문 임베딩 API 호출 시간 측정을 위한 시작 시각
        vector = self.embedder.embed([question])[0] if self.embedder is not None else None  # 임베더가 있으면 질문을 고차원 벡터(float 리스트)로 변환
        CARD_LOG.log_summary("PERF", REQUEST_ID.get(), phase="question_embedding", elapsed_ms=(perf_counter() - embed_started) * 1000,
                             calls=1 if self.embedder is not None else 0, dimensions=len(vector) if vector is not None else None)
        rows = self._run("card.hybrid_search", CANDIDATES_QUERY, qvec=vector)  # Neo4j에서 혜택 임베딩과 qvec의 코사인 유사도(sim), 후보 속성을 조회
        terms = [term.casefold() for term in search_terms(question)]  # 질문에서 명사/키워드 추출 후 소문자 정규화 (Java String.toLowerCase())
        cards = getattr(self.neo4j_search, "catalog_products", None)  # 캐시된 카드 상품 목록 확인 (없으면 None)
        if cards is None:                                             # 캐시된 카드 목록이 없으면
            cards = self._run("card.products", PRODUCTS_QUERY)        # Neo4j에서 카드 상품 메타데이터(card_id, product_nm) 직접 조회
        transform_started = perf_counter()                            # Python 내 순위 융합 및 데이터 가공 시작 시각
        identified = []                                               # 질문에서 식별된 카드 ID 목록 (Java List<Integer>)
        for card in cards:                                            # 전체 등록 카드 목록을 순회
            tokens = _name_tokens(card["product_nm"] or "")           # 카드 상품명을 공백·특수문자 기준 토큰 리스트로 분리
            hits = [token for token in tokens if token in question.casefold()]  # 카드명 토큰 중 질문에 포함된 토큰 추출 (Stream filter)
            if tokens and len(hits) == len(tokens):                   # 모든 토큰이 질문에 포함되어 있으면 완전 일치로 간주
                identified.append(card["card_id"])                    # 식별된 카드 ID 목록에 추가
        if not identified and cards:                                  # 완전 일치 카드가 없으면 부분 겹침(Overlap) 점수 계산
            overlaps = [(sum(token in question.casefold() for token in _name_tokens(c["product_nm"] or "")), c["card_id"])
                        for c in cards]                               # 각 카드별 토큰 매칭 개수 집계
            best = max((score for score, _ in overlaps), default=0)    # 가장 많이 겹치는 최대 매칭 점수 확인
            if best:                                                  # 1개 이상 겹친 카드가 있으면
                identified = [card_id for score, card_id in overlaps if score == best]  # 동점 최고 점수 카드 ID들을 식별 목록에 저장
        # Cypher 행을 Python 후보로 바꾸며 질문 키워드와 카드명 식별 결과로 별도 키워드 점수를 계산한다.
        candidates = []                                               # 키워드 점수와 벡터 점수가 결합될 후보 dict 리스트 (Java List<Map>)
        for row in rows:                                              # Neo4j 벡터 검색 결과 레코드(dict)를 하나씩 순회
            row = dict(row)                                           # 불변 레코드를 수정 가능한 Python dict(Java HashMap)로 복사
            text = "\n".join(str(x or "") for x in (row.get("name"), row.get("search_text"), row.get("rule_text"), row.get("limit_text"))).casefold()  # 검색 대상 필드들을 단일 텍스트로 합침
            if row["is_card"]:                                        # 개별 카드 전용 혜택(BENEFIT)인 경우
                card_name = row.get("product_nm") or ""               # 소속 카드 상품명 추출
                kw_fields = [card_name.casefold(), text]              # 카드명과 혜택 본문을 키워드 검색 대상 필드로 지정
                own = row.get("card_id") in identified                # 해당 혜택의 카드가 질문에서 식별된 카드인지 확인 (boolean)
            else:                                                     # 여러 카드에 적용되는 공통 혜택(COMMON)인 경우
                kw_fields = [text, " ".join(x.get("product_nm", "") for x in row["apply_cards"]).casefold()]  # 혜택 본문과 적용 카드명들을 대상 필드로 지정
                own = any(x.get("card_id") in identified for x in row["apply_cards"])  # 적용 카드 중 하나라도 식별된 카드에 속하는지 확인
            row["kw"] = sum(any(term in field for field in kw_fields) for term in terms)  # 질문의 키워드가 필드에 등장한 빈도 점수 계산
            row["sim"] = float(row["sim"]) if row.get("sim") is not None else None  # 벡터 유사도 점수를 실수형(float)으로 변환
            row["own_card"] = own                                     # 식별된 카드 소속 여부 플래그 저장
            row["key"] = _entity_key(row)                             # 혜택 식별 고유 키(item_id 또는 common_id) 생성
            candidates.append(row)                                    # 계산된 메타데이터를 후보 리스트에 추가
        keyword = sorted([r for r in candidates if r["kw"] > 0], key=lambda r: (-r["kw"], r["name"], r["key"]))  # 키워드 점수(kw) 내림차순 정렬
        vector_ranked = sorted([r for r in candidates if r["sim"] is not None], key=lambda r: (-r["sim"], r["key"]))  # 벡터 점수(sim) 내림차순 정렬
        keyword = keyword[:FETCH_PER_TABLE * 2]                       # 키워드 상위 후보 슬라이싱 (Java subList)
        vector_ranked = vector_ranked[:FETCH_PER_TABLE * 2]           # 벡터 상위 후보 슬라이싱
        # 두 채널에 중복 등장한 같은 key는 하나의 점수에 각 채널 역순위 기여분을 합산한다.
        scores = {}                                                   # RRF 융합 점수를 누적할 dict (Java Map<String, RrfScoreDto>)
        for channel, ranked in (("keyword", keyword), ("vector", vector_ranked)):  # 키워드 랭킹과 벡터 랭킹을 순서대로 순회
            for rank, row in enumerate(ranked, start=1):              # 1위부터 순위(rank) 매기기
                item = scores.setdefault(row["key"], {"row": row, "score": 0.0, "channels": []})  # 키가 없으면 기본 구조 생성 (Map.putIfAbsent)
                item["score"] += 1.0 / (RRF_K + rank)                 # RRF 공식: 1 / (60 + 순위) 점수를 누적 합산하여 두 채널 점수 융합
                item["channels"].append(channel)                      # 어떤 채널(keyword/vector)에서 선정되었는지 기록
        fused = sorted(scores.values(), key=lambda x: (-x["score"], x["row"]["key"]))  # 융합된 RRF 점수 기준 내림차순 정렬
        all_benefits = bool(ALL_BENEFITS.search(question))            # 질문이 "모든 혜택"을 묻는 정규식 패턴인지 검사
        if self.complete_card and all_benefits and identified:        # '모든 혜택' 질문이고 특정 카드가 식별된 경우
            own_hits = [x for x in candidates if x["is_card"] and x["card_id"] in identified]  # 해당 카드의 모든 혜택을 추출
            present = {x["row"]["key"] for x in fused}                # 현재 융합 순위에 포함된 키 집합 (Java Set)
            fused = [{"row": x, "score": 0.0, "channels": []} for x in own_hits if x["key"] not in present] + fused  # 누락된 혜택을 강제 보완
        # 식별된 카드의 후보를 앞쪽에 재배치한 뒤 top_k를 적용한다. 이 단계는 RRF 점수를 다시 계산하지 않는다.
        if self.card_priority and identified:                         # 카드 우선순위 옵션이 켜져 있고 카드가 식별된 경우
            fused = [x for x in fused if x["row"]["own_card"]] + [x for x in fused if not x["row"]["own_card"]]  # 해당 카드 혜택을 앞쪽에 우선 배치
        selected = fused[:top_k]                                      # 최종 요구된 상위 top_k개 후보만 선택
        hits = []                                                     # 화면 및 LangGraph에 전달할 SearchHit 객체 리스트
        for item in selected:                                         # 선택된 각 후보 항목을 순회
            row = item["row"]                                         # 후보의 원본 레코드 dict 추출
            applies = row["apply_cards"] if not row["is_card"] else [{"card_id": row["card_id"], "product_nm": row["product_nm"]}]  # 적용 카드 정보 구성
            hits.append(SearchHit("CARD_BNFT" if row["is_card"] else "CARD_COMMON_BNFT", row["key"], str(row["id"]),
                row.get("bnft_cd"), row["name"], row.get("bnft_type_cd"), applies, bool(applies), row.get("search_text"),
                row.get("sim"), row["kw"], row.get("origin_cd"), item["channels"], [], [], []))  # SearchHit DTO 객체 생성 및 리스트 추가
        self.last_trace = {"identified_cards": identified, "pool": len(candidates), "keyword_candidates": len(keyword),
                           "vector_candidates": len(vector_ranked), "completed_card": all_benefits and bool(identified)}  # 디버깅용 통계 저장
        CARD_LOG.log_summary("PERF", REQUEST_ID.get(), phase="hybrid_python_merge", elapsed_ms=(perf_counter() - transform_started) * 1000,
                             candidate_rows=len(rows), candidate_bytes=len(json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")),
                             selected=len(hits), products=len(cards))
        engines = (["neo4j_keyword"] if terms else []) + (["neo4j_vector"] if vector is not None else []) + ["neo4j_rrf"]  # 사용된 검색 엔진 명칭 리스트
        CARD_LOG.log_summary("HYBRID", "neo4j", identified=identified or None, hits=len(hits), pool=len(candidates))
        return SearchOutcome("N", hits, (perf_counter()-started)*1000, [], [], engines)  # N 모드 결과 객체 반환 (Java SearchOutcome DTO)

    def catalog_rows(self, question, graph_catalog, top_k=8):
        """전체 카탈로그에서 N 모드 검색 후보의 상세 텍스트를 찾아 interpret 입력 행을 만든다.

        search()의 SearchHit ID를 카탈로그 entity_ref와 매칭한다. 매칭된 카탈로그 행은 규칙·조건·한도를
        유지하고, 카탈로그에 없는 hit는 기본 필드만 가진 행으로 전달한다.
        """
        from .neo4j_search import entity_ref                          # 혜택 고유 식별 문자열 생성 헬퍼 함수 임포트
        catalog = {entity_ref(row["key"], row.get("id")): row for row in graph_catalog}  # 전체 카탈로그를 entity_ref 키로 Map 변환 (빠른 O(1) 조회를 위함)
        outcome = self.search(question, top_k=top_k)                  # N 모드 하이브리드 검색 실행 (top_k개 SearchHit 수신)
        rows = []                                                     # interpret 노드의 프롬프트에 넣을 혜택 메타데이터 리스트
        for hit in outcome.hits:                                      # 검색된 SearchHit를 순회
            known = catalog.get(entity_ref(hit.key, hit.benefit_id))  # 전체 카탈로그 Map에서 상세 정보(규칙, 한도 텍스트 등) 조회
            rows.append(known or {"key": hit.key, "id": hit.benefit_id, "name": hit.bnft_nm,
                                  "status": None, "card": ", ".join(c.get("product_nm", "") for c in hit.cards),
                                  "targets": [], "payment_min_amounts": []})  # 카탈로그에 있으면 매핑 행, 없으면 기본 dict 생성하여 추가
        return rows, outcome                                          # (후보 dict 리스트, 검색 결과 객체) 튜플 반환 (interpret 노드로 전달)
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
