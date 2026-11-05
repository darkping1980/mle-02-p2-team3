"""Neo4j 단일 하이브리드 검색(search_mode "N"). 질문 처리 중 PostgreSQL 업무 데이터를 읽지 않는다.

역할 분담
    Python : 질문 해석(검색 낱말 추출, "혜택 전체" 질문 판별), 질문 임베딩 생성, Neo4j 호출, 결과 행 → SearchHit 변환
    Neo4j  : 카드 식별, 키워드 일치·점수, 코사인 유사도(vector.similarity.cosine 전수 계산), RRF 통합, 동일성 병합,
             관계(대상·제외 문구) 보정, 명시 카드 우선, 카드 전체 혜택 포함, 최종 순위 — 모두 HYBRID_SEARCH_QUERY 한 문장
    임베딩 벡터는 Neo4j 밖으로 보내지 않는다(유사도 값만 반환).

순위 규칙은 기존 C(문자열 SQL + pgvector + RRF(k=60) + 관계 보정)와 같고, 아래 개선은 파라미터로 켠다(기본 켬).
    strict_terms   : 영문·숫자 낱말은 단어 경계로만 일치(하이픈도 낱말의 일부: "ONE" ⊄ "Two-in-One"). 한글 낱말은 기존처럼 부분 일치
    card_priority  : 질문에 카드명이 있으면 그 카드 혜택(그 카드에 적용된 공통 혜택 포함)을 후보 앞쪽에 둔다(나머지 순서 유지)
    complete_card  : 카드명 + "혜택 전체" 질문이면 그 카드의 혜택을 top_k와 관계없이 모두 후보에 넣는다
세 옵션을 모두 끄면 기존 C와 같은 순위다(동등성 검증용). 캐시 없음.
"""
from __future__ import annotations

import json
import re
from datetime import date
from time import perf_counter

from .benefit_search_service import FETCH_PER_TABLE, RRF_K, SearchHit, SearchOutcome, search_terms
from .neo4j_search import CARD_LOG, source

ENGINE = "neo4j"
GENERIC_CARD_TOKENS = ["카드", "하나", "체크카드", "신용카드", "체크", "신용", "하나카드", "우리카드"]
# 카드의 혜택 전체를 묻는 표현(질문 해석). "대중교통 혜택 있어?"처럼 특정 혜택 존재를 묻는 표현은 넣지 않는다.
ALL_BENEFITS = re.compile(r"(주요|전체|모든|모두|전부|어떤)\s*혜택|혜택\s*(전체|전부|모두|목록)"
                          r"|혜택(을|를|은|는|과|와|이|가)?\s*(다\s*)?(알려|소개|정리|뭐|무엇)")

# 낱말 일치식: strict이고 영문·숫자 낱말이면 단어 경계 정규식, 그 밖은 부분 문자열(기존 SQL strpos(lower()) 규칙).
# 영문·숫자 낱말([0-9a-z]+)만 정규식에 넣으므로 특수문자 이스케이프가 필요 없다. 하이픈은 낱말의 일부로 본다(Two-in-One).
_MATCH = ("({f} IS NOT NULL AND CASE WHEN $strict AND {t} =~ '[0-9a-z]+' "
          "THEN toLower({f}) =~ ('(?s).*(?<![0-9a-z-])' + {t} + '(?![0-9a-z-]).*') ELSE toLower({f}) CONTAINS {t} END)")


def _m(term: str, field: str) -> str:
    return _MATCH.format(t=term, f=field)


HYBRID_SEARCH_QUERY = f"""
// 1. 질문에 나온 카드: 카드명 구별 낱말이 모두 있으면 그 카드들, 없으면 가장 많이 맞은 카드들
CALL () {{
  MATCH (p:dp_card_product)
  WITH p, [t IN apoc.text.split(toLower(p.product_nm), '[^0-9a-z가-힣]+') WHERE size(t) >= 2 AND NOT t IN $generic] AS toks
  WITH p, toks, [t IN toks WHERE CASE WHEN t =~ '[0-9a-z]+'
                                  THEN $question =~ ('(?s).*(?<![0-9a-z-])' + t + '(?![0-9a-z-]).*') ELSE $question CONTAINS t END] AS hit
  WITH collect({{id: p.card_id, n: size(hit), full: size(toks) > 0 AND size(hit) = size(toks)}}) AS ps
  WITH ps, [x IN ps WHERE x.full | x.id] AS full, reduce(m = 0, y IN ps | CASE WHEN y.n > m THEN y.n ELSE m END) AS best
  RETURN CASE WHEN NOT ($card_priority OR $complete_card) THEN []
              WHEN size(full) > 0 THEN full ELSE [x IN ps WHERE best > 0 AND x.n = best | x.id] END AS identified
}}
// 2. 유효 혜택 풀: 키워드 점수(기존 keyword SQL + card.list 보강)와 코사인 유사도(pgvector와 같은 cos 값)
CALL () {{
  MATCH (b:dp_node)
  WHERE (b:dp_card_bnft OR b:dp_card_common_bnft) AND (b.bnft_valid_to_excl IS NULL OR toString(b.bnft_valid_to_excl) > $today)
  OPTIONAL MATCH (p:dp_card_product)-[:dp_has_benefit]->(b)
  OPTIONAL MATCH (b)-[:dp_belongs_to]->(s:dp_card_common)
  OPTIONAL MATCH (a:dp_card_product)-[:dp_has_common_benefit]->(b)
  WITH b, p, s, a ORDER BY a.card_id
  WITH b, p, s, [x IN collect(a) WHERE x IS NOT NULL | {{card_id: x.card_id, product_nm: x.product_nm}}] AS apply_cards
  OPTIONAL MATCH (b)-[:dp_has_rule]->(:dp_bnft_rule)-[:dp_targets]->(t:dp_rule_target)
  WITH b, p, s, apply_cards, collect(t.target_nm) AS targets
  OPTIONAL MATCH (b)-[:dp_has_rule*0..1]->(owner)-[:dp_has_expr]->(:dp_cond_expr)-[:dp_has_branch]->(:dp_cond_branch)
        -[:dp_has_atom]->(x:dp_cond_atom {{kind: 'BNFT_EXCL'}})
  WITH b, p, s, apply_cards, targets, collect(DISTINCT x.excl_raw_txt) AS exclusions
  WITH b, p, s, apply_cards, targets, exclusions, b:dp_card_bnft AS is_card,
       EXISTS {{ (b)-[:dp_same_as]->(:dp_card_common_bnft) }} AS has_same_as,
       CASE WHEN b:dp_card_bnft THEN [p.product_nm, b.name] + targets
            ELSE [b.name, s.common_nm] + [c IN apply_cards | c.product_nm] END AS fields
  WITH b, p, apply_cards, targets, exclusions, is_card, has_same_as,
       size([t IN $terms WHERE any(f IN fields WHERE {_m('t', 'f')})])
         + size([t IN $terms WHERE NOT has_same_as AND {_m('t', 'b.name')}]) AS kw,
       CASE WHEN b.embedding IS NULL OR $qvec IS NULL THEN null ELSE 2 * vector.similarity.cosine(b.embedding, $qvec) - 1 END AS sim
  ORDER BY b.key
  RETURN collect({{key: b.key, is_card: is_card, id: coalesce(b.card_bnft_id, b.card_common_bnft_id), bnft_cd: b.bnft_cd,
                   name: b.name, bnft_type_cd: b.bnft_type_cd, card_id: b.card_id, product_nm: p.product_nm, apply_cards: apply_cards,
                   search_text: b.search_text, origin_cd: apoc.convert.fromJsonMap(b.source_json).bnft_origin_cd,
                   targets: targets, exclusions: exclusions, has_same_as: has_same_as, kw: kw, sim: sim, model: b.embedding_model,
                   brand_status: b.brand_compare_status, brand_issues: b.brand_compare_issues,
                   brand_common_key: b.brand_compare_common_key}}) AS pool
}}
// 3. 키워드 순위(점수 내림차순, 이름) · 벡터 순위(테이블별 상위 $fetch, 유사도 내림차순)
WITH identified, pool,
     apoc.coll.sortMulti([r IN pool WHERE r.kw > 0], ['kw', '^name', '^key']) AS K,
     apoc.coll.sortMulti(apoc.coll.sortMulti([r IN pool WHERE r.is_card AND r.sim IS NOT NULL], ['sim', '^key'])[0..$fetch]
                         + apoc.coll.sortMulti([r IN pool WHERE NOT r.is_card AND r.sim IS NOT NULL], ['sim', '^key'])[0..$fetch],
                         ['sim', '^key']) AS V
// 4. RRF 통합(1/(k+순위) 합). 같은 점수는 기존처럼 키워드 순서, 그다음 벡터 순서
WITH identified, pool, K, V,
     [i IN range(0, size(K) - 1) | {{key: K[i].key, s: 1.0 / ($rrf_k + i + 1), pos: i, ch: 'keyword'}}]
     + [i IN range(0, size(V) - 1) | {{key: V[i].key, s: 1.0 / ($rrf_k + i + 1), pos: size(K) + i, ch: 'vector'}}] AS parts
WITH identified, pool, K, V, parts, apoc.coll.toSet([x IN parts | x.key]) AS fused_keys
WITH identified, pool, K, V, apoc.coll.sortMulti([k IN fused_keys |
       {{key: k, score: reduce(acc = 0.0, x IN parts | acc + CASE WHEN x.key = k THEN x.s ELSE 0.0 END),
        pos: reduce(m = 1000000, x IN parts | CASE WHEN x.key = k AND x.pos < m THEN x.pos ELSE m END),
        channels: [x IN parts WHERE x.key = k | x.ch]}}], ['score', '^pos']) AS fused
WITH identified, pool, [k IN K | k.key] AS kkeys, [v IN V | v.key] AS vkeys,
     [f IN fused | f {{.*, row: head([r IN pool WHERE r.key = f.key])}}] AS fused
// 5. 동일성 SAME 병합: 기존 BRAND_SERVICE 행과 공통 혜택이 함께 후보일 때만, 확인된 쌍의 카드 혜택을 뺀다
WITH identified, pool, kkeys, vkeys, fused,
     any(f IN fused WHERE f.row.origin_cd = 'BRAND_SERVICE') AND any(f IN fused WHERE NOT f.row.is_card) AS gate
WITH identified, pool, kkeys, vkeys, fused, gate,
     CASE WHEN gate THEN [r IN pool WHERE r.is_card AND r.brand_status = 'SAME' AND r.brand_common_key IS NOT NULL
                          | [r.key, r.brand_common_key]] ELSE [] END AS confirmed
WITH identified, pool, kkeys, vkeys, gate, fused,
     [f IN fused WHERE f.row.is_card AND any(c IN confirmed WHERE c[0] = f.key AND any(g IN fused WHERE g.key = c[1])) | f.key] AS merged
WITH identified, pool, kkeys, vkeys, gate, merged, [f IN fused WHERE NOT f.key IN merged] AS fused
// 6. 관계 보정: 질문 낱말이 적용 대상과 맞으면 앞으로, 제외 문구 낱말이면 top_k 안에서 뒤로(기존 _rank_with_graph)
WITH identified, pool, kkeys, vkeys, gate, merged,
     [i IN range(0, size(fused) - 1) | apoc.map.merge(fused[i], {{i: i,
        target_terms: [t IN $terms WHERE any(n IN fused[i].row.targets WHERE {_m('t', 'n')})],
        excl_tokens: reduce(acc = [], e IN fused[i].row.exclusions | acc + apoc.text.split(toLower(e), '[\\\\s,/()·\\\\[\\\\]:]+'))}})] AS fused
WITH identified, pool, kkeys, vkeys, gate, merged,
     [f IN fused | f {{.*, excluded_terms: [t IN $terms WHERE t IN f.excl_tokens AND t <> '' AND NOT t IN f.target_terms],
                      nt: CASE WHEN size(f.target_terms) > 0 THEN 0 ELSE 1 END}}] AS fused
WITH identified, pool, kkeys, vkeys, gate, merged, apoc.coll.sortMulti(fused, ['^nt', '^i']) AS ranked
WITH identified, pool, kkeys, vkeys, gate, merged,
     [j IN range(0, size(ranked) - 1) | apoc.map.merge(ranked[j], {{j: j, ex: CASE WHEN size(ranked[j].excluded_terms) > 0 THEN 1 ELSE 0 END}})] AS ranked
WITH identified, pool, kkeys, vkeys, gate, merged,
     apoc.coll.sortMulti(ranked[0..$top_k], ['^ex', '^j']) + ranked[$top_k..] AS ranked
// 7. 명시 카드: 카드 전체 혜택 질문이면 그 카드 혜택을 모두 포함하고, 그 카드 혜택을 앞쪽에 둔다(순서는 유지)
WITH identified, pool, kkeys, vkeys, gate, merged, ranked,
     CASE WHEN $complete_card AND $all_benefits AND size(identified) > 0
          THEN [r IN pool WHERE r.is_card AND r.card_id IN identified AND NOT r.has_same_as AND NOT any(x IN ranked WHERE x.key = r.key)
                | {{key: r.key, score: 0.0, channels: [], row: r, target_terms: [], excluded_terms: []}}]
          ELSE [] END AS extra
WITH identified, pool, kkeys, vkeys, gate, merged, ranked + extra AS ranked, size(extra) > 0 AS completed
WITH identified, pool, kkeys, vkeys, gate, merged, completed,
     [x IN ranked | x {{.*, own: (x.row.is_card AND x.row.card_id IN identified)
                          OR (NOT x.row.is_card AND any(c IN x.row.apply_cards WHERE c.card_id IN identified))}}] AS ranked
WITH identified, pool, kkeys, vkeys, gate, merged, completed, ranked,
     CASE WHEN completed THEN apoc.coll.max([$top_k, size([x IN ranked WHERE x.own])]) ELSE $top_k END AS lim
WITH identified, pool, kkeys, vkeys, gate, merged, completed, lim,
     CASE WHEN $card_priority AND size(identified) > 0 THEN [x IN ranked WHERE x.own] + [x IN ranked WHERE NOT x.own] ELSE ranked END AS ranked
// 8. 반환: 순위 행(점수 포함)과 판정 정보. 임베딩 벡터는 반환하지 않는다
RETURN identified, lim, completed, merged, size(pool) AS pool_size,
       apoc.coll.toSet([r IN pool WHERE r.model IS NOT NULL | r.model]) AS models,
       CASE WHEN gate THEN [r IN pool WHERE r.is_card AND r.brand_status IS NOT NULL AND NOT (r.brand_status = 'SAME' AND r.brand_common_key IS NOT NULL)
                             | {{id: r.id, status: r.brand_status, issues: r.brand_issues}}] ELSE [] END AS brand_warnings,
       [x IN ranked[0..lim] | {{key: x.key, is_card: x.row.is_card, id: x.row.id, bnft_cd: x.row.bnft_cd, name: x.row.name,
            bnft_type_cd: x.row.bnft_type_cd, card_id: x.row.card_id, product_nm: x.row.product_nm, apply_cards: x.row.apply_cards,
            search_text: x.row.search_text, origin_cd: x.row.origin_cd, rrf: x.score, channels: x.channels,
            kw: CASE WHEN x.key IN kkeys THEN x.row.kw ELSE 0 END, sim: CASE WHEN x.key IN vkeys THEN x.row.sim ELSE null END,
            graph_targets: apoc.coll.toSet(x.row.targets), target_terms: x.target_terms, excluded_terms: x.excluded_terms,
            own_card: coalesce(x.own, false)}}] AS hits"""
PRODUCTS_QUERY = "MATCH (p:dp_card_product) RETURN p.card_id AS card_id, p.product_nm AS product_nm ORDER BY card_id"
COMMON_LINK_EVIDENCE_QUERY = """
MATCH (c:dp_card_common_bnft {key: $key})-[l:dp_supported_by {link_source: 'COMMON_STG'}]->(e:dp_card_source_evidence)
RETURN l.ev_subject_cd AS ev_subject_cd, l.ev_item_key AS ev_item_key, e.source_json AS evidence
ORDER BY e.page_no, e.evidence_id"""
TERMS_QUERY = """
MATCH (c:dp_card_product)-[:dp_has_item]->(i:dp_card_product_item {item_type_cd: 'TERMS'})
WHERE c.card_id IN $card_ids
OPTIONAL MATCH (i)-[l:dp_supported_by {ev_subject_cd: 'ITEM'}]->(e:dp_card_source_evidence)
WITH c, i, e ORDER BY e.evidence_id
RETURN c.card_id AS card_id, c.product_nm AS product_nm, i.card_product_item_id AS card_product_item_id, i.source_json AS item_source,
       [x IN collect(e) | x.source_json] AS evidence
ORDER BY card_id, card_product_item_id"""
STATEMENTS = {"card.hybrid_search": "카드 식별 + (혜택)+(카드|공통서비스|적용 카드)+(대상)+(제외 조건) + 키워드·코사인·RRF·관계 보정·순위",
              "card.products": "(dp_card_product)", "card.common_link_evidence": "(공통 혜택)-[COMMON_STG]->(근거)",
              "card.terms": "(dp_card_product)-[dp_has_item]->(TERMS)-[dp_supported_by ITEM]->(근거)"}
EVIDENCE_FIELDS = ("evidence_id", "page_no", "quote_txt", "approval_status_cd")


class Neo4jBenefitSearch:
    """Neo4j만 읽는 후보 검색·근거 보완·TERMS. CardGraphRAG의 benefit_search로 쓴다(BenefitSearchService와 같은 인터페이스)."""

    engine = ENGINE
    reads_postgresql_source = False          # 제외 판정은 적재 시 PostgreSQL과 대조된 그래프 source_json으로 한다

    def __init__(self, neo4j_search, embedder=None, strict_terms: bool = True, card_priority: bool = True,
                 complete_card: bool = True):
        self.neo4j_search = neo4j_search
        self.embedder = embedder
        self.strict_terms, self.card_priority, self.complete_card = strict_terms, card_priority, complete_card
        self.last_trace: dict = {}

    def _run(self, statement_id: str, cypher: str, **params) -> list[dict]:
        return self.neo4j_search._run(statement_id, cypher, STATEMENTS[statement_id], params)

    # region 후보 검색 (순위 계산은 Neo4j)
    def search(self, question: str, mode: str = "N", top_k: int = 5, use_graph: bool = True) -> SearchOutcome:
        started = perf_counter()
        vector = self.embedder.embed([question])[0] if self.embedder is not None else None
        row = self._run("card.hybrid_search", HYBRID_SEARCH_QUERY,
                        terms=[term.casefold() for term in search_terms(question)], question=question.casefold(), qvec=vector,
                        strict=self.strict_terms, card_priority=self.card_priority, complete_card=self.complete_card,
                        all_benefits=bool(ALL_BENEFITS.search(question)), generic=GENERIC_CARD_TOKENS, today=date.today().isoformat(),
                        top_k=top_k, fetch=FETCH_PER_TABLE, rrf_k=RRF_K)[0]
        model = getattr(self.embedder, "model_nm", None)
        if vector is not None and row["models"] and set(row["models"]) != {model}:
            raise ValueError(f"저장된 벡터의 모델({sorted(row['models'])})과 질문 모델({model})이 다릅니다")
        hits = [self._hit(item) for item in row["hits"]]
        warnings = []
        for item in row["brand_warnings"]:
            if item["status"] == "SAME":
                warnings.append(f"공통 혜택 소유자를 확인하지 못해 병합하지 않음: {item['id']}")
            else:
                warnings.append(f"동일성 미확정, 병합하지 않음: {item['id']} {json.loads(item['issues'] or '[]')}")
        unapplied = [hit.bnft_nm for hit in hits if not hit.applied]
        if unapplied:
            warnings.append(f"카드 적용 관계가 없는 공통 혜택: {unapplied}")
        engines = ["neo4j_keyword", "neo4j_name"] + (["neo4j_vector_exact"] if vector is not None else []) + ["neo4j_relations"]
        engines += (["card_complete"] if row["completed"] else []) + (["card_priority"] if self.card_priority and row["identified"] else [])
        self.last_trace = {"identified_cards": row["identified"], "limit": row["lim"], "pool": row["pool_size"],
                           "rrf": [item["rrf"] for item in row["hits"]], "own_card": [item["own_card"] for item in row["hits"]]}
        CARD_LOG.log_summary("HYBRID", "neo4j", identified=row["identified"] or None, limit=row["lim"], hits=len(hits))
        return SearchOutcome(mode, hits, (perf_counter() - started) * 1000, row["merged"], warnings, engines)

    @staticmethod
    def _hit(item: dict) -> SearchHit:
        if item["is_card"]:
            cards, applied, origin = [{"card_id": item["card_id"], "product_nm": item["product_nm"]}], True, item["origin_cd"]
        else:
            cards, applied, origin = item["apply_cards"], bool(item["apply_cards"]), "COMMON"
        return SearchHit("CARD_COMMON_BNFT" if not item["is_card"] else "CARD_BNFT", item["key"], item["id"], item["bnft_cd"],
                         item["name"], item["bnft_type_cd"], cards, applied, item["search_text"], item["sim"], item["kw"], origin,
                         list(item["channels"]), list(item["graph_targets"]), list(item["target_terms"]), list(item["excluded_terms"]))

    def catalog_rows(self, question: str, mode: str, graph_catalog: list[dict], top_k: int = 8) -> tuple[list[dict], SearchOutcome]:
        """기존 catalog_rows와 같은 행. 후보가 모두 그래프 노드라 pg: key를 만들지 않는다."""
        from .neo4j_search import entity_ref
        graph = {entity_ref(row["key"], row["id"]): row for row in graph_catalog}
        outcome = self.search(question, mode, top_k, use_graph=True)
        rows = []
        for hit in outcome.hits:
            known = graph.get(entity_ref(hit.key))
            target = (hit.search_txt or "").splitlines()
            rows.append(known if known else {
                "key": hit.key, "id": hit.benefit_id, "name": hit.bnft_nm, "status": None,
                "card": ", ".join(card["product_nm"] for card in hit.cards) or "적용 카드 미확인",
                "targets": [line.split(": ", 1)[1] for line in target if line.startswith(("이용처", "서비스 대상"))],
                "payment_min_amounts": []})
        return rows, outcome
    # endregion

    # region 상세·근거·TERMS (질문 시점 PostgreSQL 대체 조회를 Neo4j로)
    def get_detail(self, key: str, sections: tuple[str, ...]) -> dict | None:
        """CardGraphRAG의 공통 혜택 근거 대체 조회(``pg:CARD_COMMON_BNFT:…``)를 적재된 COMMON_STG 연결로 처리한다.

        반환 형식은 기존 PostgreSQL 대체 조회(select_common_bnft_evidence)와 같다. 그 밖의 key는 그래프 상세로 처리한다.
        """
        if key.startswith("pg:CARD_COMMON_BNFT:"):
            _, _, owner, bnft_id = key.split(":", 3)
            graph_key = json.dumps(["card_common_bnft", int(owner), bnft_id], ensure_ascii=False, separators=(",", ":"))
            rows = self._run("card.common_link_evidence", COMMON_LINK_EVIDENCE_QUERY, key=graph_key)
            evidence = [{"link": {"ev_subject_cd": row["ev_subject_cd"], "ev_item_key": row["ev_item_key"]}, "rule_key": None,
                         "evidence": {"source_json": json.dumps({f: source({"source_json": row["evidence"]}).get(f) for f in EVIDENCE_FIELDS},
                                                                ensure_ascii=False)}} for row in rows]
            return {"context": {}, "rules": [], "conditions": [], "limits": [], "evidence": evidence if "evidence" in sections else []}
        if key.startswith("pg:CARD_BNFT:"):
            _, _, owner, bnft_id = key.split(":", 3)
            key = json.dumps(["card_bnft", int(owner), bnft_id], ensure_ascii=False, separators=(",", ":"))
        return self.neo4j_search.get_detail(key, sections)

    def card_terms(self, card_ids: list[int]) -> list[dict]:
        """기존 select_card_terms와 같은 행(카드 TERMS 항목 + ITEM 근거, evidence_id 순)."""
        ids = sorted({int(card_id) for card_id in card_ids})
        if not ids:
            return []
        out = []
        for row in self._run("card.terms", TERMS_QUERY, card_ids=ids):
            item = source({"source_json": row["item_source"]})
            out.append({"card_id": row["card_id"], "card_product_item_id": row["card_product_item_id"], "item_cd": item.get("item_cd"),
                        "item_nm": item.get("item_nm"), "item_data": item.get("item_data"), "item_rule_txt": item.get("item_rule_txt"),
                        "verification_status_cd": item.get("verification_status_cd"), "product_nm": row["product_nm"],
                        "evidence": [{f: source({"source_json": e}).get(f) for f in EVIDENCE_FIELDS} for e in row["evidence"]]})
        return out
    # endregion
