"""dp_ 그래프 읽기 전용 조회. Cypher는 graph_questions.cypher에 있고 실행과 로그는 여기서 맡는다.

Java 관점: Neo4j용 Repository/DAO다. Cypher 문장은 같은 폴더의 ``graph_questions.cypher`` 에 ``// name: 이름`` 으로
정의되어 있고, ``MAPPERS["graph_questions.이름"]`` 으로 문자열을 꺼내 파라미터와 함께 실행한다(LLM이 Cypher를 만들지 않음).
모든 조회는 ``READ_ACCESS`` 세션의 ``execute_read`` 로 실행되어 그래프를 바꾸지 않는다.
그래프 자체는 db_pipeline/neo4j_load_draft.py가 PostgreSQL에서 적재한 ``dp_`` 라벨 노드·관계다.

Cypher별 용도 (STATEMENTS의 식별자 → 호출 메서드)
    card.catalog / card.item_catalog / card.common_catalog  → list_catalog : 질문 해석용 혜택·연회비 항목·공통 혜택 목록
    card.list                                              → list_benefits : 혜택명 문자열 검색(B·C 후보 점수 보강)
    card.relations                                         → candidate_relations : 후보별 적용 대상·제외 문구
    card.context                                           → get_detail : 혜택 1건과 카드·공통서비스·문서
    card.rules / card.conditions / card.limits             → get_detail : 규칙·대상, 조건식(branch·atom), 한도 원문
    card.evidence / card.common_evidence / card.item_evidence → get_detail : 연결된 PDF 원문 근거(페이지·청크·문서)
    card.hop*                                              → hop : 다중 홉 조회(GraphRAG 흐름에서는 호출하지 않고 tests/test_neo4j_origin_search.py만 사용)

호출하는 곳: card_graphrag.CardGraphRAG(interpret·retrieve), benefit_search_service.BenefitSearchService,
            streamlit_app(connect, QUERIES 표시), verify_view(STATEMENTS·flatten_record)
"""
from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar
from pathlib import Path
from time import perf_counter

from common.neo4j_connection import create_neo4j_driver
from common.neo4j_db_session import Neo4jDbSession, render_cypher_inline, render_cypher_log
from common.query_logger import DEFAULT_SENSITIVE_KEYS, QueryLogger
from neo4j import READ_ACCESS

GRAPH_PREFIX = "dp_"     # 이 프로젝트의 라벨·관계 접두사
# 공통 Neo4j logger의 자식이다. 부모에 붙는 기존 handler로 출력되므로 handler를 새로 만들지 않는다.
CARD_LOGGER_NAME = "car_search_rag.neo4j.card_graphrag"
# 레시피의 Neo4jDbSession과 같은 combined 모드. 로그의 Cypher에는 값이 들어가 DBeaver에 그대로 붙일 수 있다.
CARD_LOG = QueryLogger(logging.getLogger(CARD_LOGGER_NAME), log_mode="combined", query_label="Cypher",
                       result_log=True, sensitive_keys=DEFAULT_SENSITIVE_KEYS)
REQUEST_ID: ContextVar[str] = ContextVar("card_request_id", default="-")  # Cypher 로그를 질문 요청과 연결한다.
DETAIL_LOG: ContextVar[bool] = ContextVar("card_detail_log", default=False)  # 검증 모드에서 Cypher 전문과 레코드를 남긴다.
# 레코드 표시에서 뺄 내부 속성과, source_json에서 꺼내 보여 줄 값.
HIDDEN_PROPERTIES = frozenset({"source_json", "key", "card_source", "card_sources"})
SOURCE_FIELDS = ("cond_basis_cd", "excl_raw_txt", "cond_status_cd", "value_unit_cd",
                 "rule_status_cd", "quote_txt", "card_cond_status_cd")

# 공통 세션의 ``// name:`` mapper만 재사용한다. 실행은 READ_ACCESS를 보장하는 Neo4jSearch._query가 맡는다.
MAPPERS = Neo4jDbSession(mapper_root=Path(__file__).resolve().parent).mappers
CATALOG_QUERY = MAPPERS["graph_questions.catalog"]
COMMON_CATALOG_QUERY = MAPPERS["graph_questions.common_catalog"]
ITEM_CATALOG_QUERY = MAPPERS["graph_questions.item_catalog"]
ITEM_EVIDENCE_QUERY = MAPPERS["graph_questions.item_evidence"]
LIST_QUERY = MAPPERS["graph_questions.list_benefits"]
RELATION_QUERY = MAPPERS["graph_questions.candidate_relations"]
CONTEXT_QUERY = MAPPERS["graph_questions.benefit_context"]
RULE_QUERY = MAPPERS["graph_questions.benefit_rules"]
CONDITION_QUERY = MAPPERS["graph_questions.benefit_conditions"]
LIMIT_QUERY = MAPPERS["graph_questions.benefit_limits"]
EVIDENCE_QUERY = MAPPERS["graph_questions.benefit_evidence"]
COMMON_EVIDENCE_QUERY = MAPPERS["graph_questions.common_benefit_evidence"]
HOP_QUERIES = {name: MAPPERS[f"graph_questions.{name}"] for name in
               ("hop1_card_benefits", "hop2_card_rules", "hop2_card_common", "hop3_card_targets", "hop3_common_docs", "hop3_target_cards")}
QUERIES = {"카탈로그": CATALOG_QUERY, "항목 카탈로그": ITEM_CATALOG_QUERY, "항목 근거": ITEM_EVIDENCE_QUERY,
           "공통 카탈로그": COMMON_CATALOG_QUERY, "목록": LIST_QUERY, "후보 관계": RELATION_QUERY,
           "카드·혜택": CONTEXT_QUERY, "규칙·대상": RULE_QUERY, "조건식": CONDITION_QUERY, "한도": LIMIT_QUERY, "근거": EVIDENCE_QUERY,
           "공통 혜택 근거": COMMON_EVIDENCE_QUERY, **HOP_QUERIES}
# 로그에 쓰는 Cypher 식별자와 그 쿼리가 지나가는 노드·관계 경로.
STATEMENTS = {
    "card.catalog": (CATALOG_QUERY, "(dp_card_product)-[dp_has_benefit]->(dp_card_bnft)"
                                    "-[dp_has_rule]->(dp_bnft_rule)-[dp_targets]->(dp_rule_target), "
                                    "(dp_bnft_rule)-[dp_has_expr]->()-[dp_has_branch]->()-[dp_has_atom]->(dp_cond_atom)"),
    "card.item_catalog": (ITEM_CATALOG_QUERY, "(dp_card_product)-[dp_has_item]->(dp_card_product_item)"),
    "card.item_evidence": (ITEM_EVIDENCE_QUERY, "(dp_card_product)-[dp_has_item]->(dp_card_product_item)-[dp_supported_by]->"
                                                "(dp_card_source_evidence)-[dp_in_chunk]->(dp_card_doc_chunk)-[dp_on_page]->(dp_card_doc_page)"),
    "card.common_catalog": (COMMON_CATALOG_QUERY, "(dp_card_product)-[dp_has_common_benefit]->(dp_card_common_bnft)-[dp_belongs_to]->(dp_card_common)"),
    "card.list": (LIST_QUERY, "(dp_card_bnft|dp_card_common_bnft)"),
    "card.relations": (RELATION_QUERY, "(dp_card_product)-[dp_has_benefit|dp_has_common_benefit]->(혜택)-[dp_has_rule]->()-[dp_targets]->(dp_rule_target), "
                                       "(혜택|규칙)-[dp_has_expr]->()-[dp_has_branch]->()-[dp_has_atom]->(dp_cond_atom)"),
    "card.context": (CONTEXT_QUERY, "(dp_card_product)-[dp_has_benefit|dp_has_common_benefit]->(혜택)-[dp_belongs_to]->(dp_card_common)-[dp_has_document]->(dp_card_doc)"),
    "card.rules": (RULE_QUERY, "(dp_card_bnft)-[dp_has_rule]->(dp_bnft_rule)-[dp_targets]->(dp_rule_target)"),
    "card.conditions": (CONDITION_QUERY, "(dp_card_product|dp_card_bnft|dp_bnft_rule)-[dp_has_expr]->(dp_cond_expr)"
                                         "-[dp_has_branch]->(dp_cond_branch)-[dp_has_atom]->(dp_cond_atom)"),
    "card.limits": (LIMIT_QUERY, "(혜택).limit_text"),
    "card.evidence": (EVIDENCE_QUERY, "(dp_card_product|dp_card_bnft|dp_bnft_rule)-[dp_supported_by]->(dp_card_source_evidence)"
                                      "-[dp_in_chunk]->(dp_card_doc_chunk)-[dp_on_page]->(dp_card_doc_page)-[dp_in_document]->(dp_card_doc)"),
    "card.common_evidence": (COMMON_EVIDENCE_QUERY, "(dp_card_common_bnft)<-[dp_same_as]-(dp_card_bnft)-[dp_supported_by]->(dp_card_source_evidence)"
                                                    "-[dp_in_chunk]->(dp_card_doc_chunk)-[dp_on_page]->(dp_card_doc_page)-[dp_in_document]->(dp_card_doc)"),
    **{f"card.{name}": (query, name) for name, query in HOP_QUERIES.items()},
}
STATEMENT_IDS = {query: statement_id for statement_id, (query, _) in STATEMENTS.items()}
SECTION_QUERIES = {"rules": RULE_QUERY, "conditions": CONDITION_QUERY, "limits": LIMIT_QUERY,
                   "evidence": EVIDENCE_QUERY}
ALL_SECTIONS = tuple(SECTION_QUERIES)


def source(props: dict) -> dict:
    """Decode the original JSON; never infer a missing value as approved."""
    value = props.get("source_json")
    return json.loads(value) if value else {}


def flatten_record(row: dict) -> dict:
    """Cypher 레코드를 표 한 행으로 만든다. 내부 속성은 빼고 ``source_json`` 의 주요 값은 꺼낸다."""
    flat = {}
    for column, value in row.items():
        if column in HIDDEN_PROPERTIES:
            continue
        if isinstance(value, dict):
            original = source(value)
            original = original.get("source", original) if isinstance(original.get("source"), dict) else original
            flat.update({f"{column}.{name}": item for name, item in value.items() if name not in HIDDEN_PROPERTIES})
            flat.update({f"{column}.{name}": original[name] for name in SOURCE_FIELDS if original.get(name) is not None})
        elif isinstance(value, list):
            flat[column] = ", ".join(str(item) for item in value)
        else:
            flat[column] = value
    return flat


def is_item_key(key: str) -> bool:
    """혜택이 아닌 카드 상품 항목(연회비 등) 노드의 key인지 판별한다."""
    return key.startswith('["card_product_item"')


def is_common_key(key: str) -> bool:
    """공통 혜택 노드의 내부 key인지 판별한다."""
    return key.startswith('["card_common_bnft"')


def entity_ref(key: str, fallback: str | None = None) -> str | None:
    """혜택 key를 엔터티 종류·소유자·ID가 모두 들어간 표준 참조로 바꾼다.

    카드 상품 항목: ``card_product_item:{card_id}:{card_product_item_id}``. 혜택의 그래프 key ``["card_bnft",6,"ID"]``,
    PostgreSQL key ``pg:CARD_BNFT:6:ID``, 연회비 등 항목 key ``["card_product_item",6,"ID"]`` 가 모두 이 참조가 된다.
    공통 혜택: ``card_common_bnft:{card_common_id}:{card_common_bnft_id}``. 카드 항목과 ID 문자열이 같아도 섞이지 않는다.
    형식이 다른 key는 ``fallback`` 을 쓴다.
    """
    if key.startswith("pg:"):
        parts = key.split(":", 3)
        if len(parts) != 4:
            return fallback
        kind = ITEM_KINDS.get(parts[1].lower())
        return f"{kind}:{parts[2]}:{parts[3]}" if kind else fallback
    try:
        parts = json.loads(key)
    except (TypeError, ValueError):
        return fallback
    if isinstance(parts, list) and len(parts) == 3 and parts[0] in ITEM_KINDS:
        return f"{ITEM_KINDS[parts[0]]}:{parts[1]}:{parts[2]}"
    return fallback


# key의 종류 → 표준 참조의 종류. 혜택(card_bnft)은 카드 상품 항목이다(2026-11-04 card_product_item 전환).
ITEM_KINDS = {"card_bnft": "card_product_item", "card_product_item": "card_product_item",
              "card_common_bnft": "card_common_bnft"}


def statement_plan(statement_id: str, **params) -> dict:
    """실행할 Cypher를 표시용으로 만든다. ``browser_cypher`` 는 값이 들어가 그대로 실행할 수 있다."""
    query, path = STATEMENTS[statement_id]
    bound = dict(params)
    inline, _ = render_cypher_inline(CARD_LOG, query, bound)
    return {"statement_id": statement_id, "path": path, "cypher": query, "parameters": bound, "browser_cypher": inline or query}


def detail_statements(sections: tuple[str, ...] = ALL_SECTIONS) -> list[str]:
    """``get_detail`` 이 실행하는 순서대로 Cypher 식별자를 돌려준다."""
    return ["card.context", *(f"card.{name}" for name in SECTION_QUERIES if name in sections)]


def detail_plan(keys: list[str], sections: tuple[str, ...]) -> list[dict]:
    """혜택 키별로 ``get_detail`` 이 실행할 Cypher 목록을 만든다."""
    return [statement_plan("card.common_evidence" if statement_id == "card.evidence" and is_common_key(key) else statement_id, key=key)
            for key in keys for statement_id in detail_statements(sections)]


class Neo4jSearch:
    """dp_ 그래프 조회 객체. 드라이버와 대상 DB 이름을 갖고, 모든 공개 메서드는 _query를 거쳐 읽기 전용으로 실행한다."""

    def __init__(self, driver, database: str | None = None):
        self.driver = driver
        self.database = database

    def _query(self, query: str, **params) -> list[dict]:
        """Cypher 1건을 READ_ACCESS 세션에서 실행하고 레코드를 dict 목록으로 반환한다.

        값은 ``$파라미터`` 로만 전달한다(문자열 조합 없음). 요약 로그는 항상, Cypher 전문·레코드는 DEBUG 또는 검증 모드에서만 남긴다.

        Raises:
            neo4j 드라이버 예외(연결·인증 등)를 그대로 전파한다. CardGraphRAG 노드가 잡아 NEO4J_FAILED로 바꾼다.
        """
        statement_id = STATEMENT_IDS.get(query, "card.unregistered")
        label = f"{REQUEST_ID.get()}/{statement_id}"
        detail = DETAIL_LOG.get() or CARD_LOG.logger.isEnabledFor(logging.DEBUG)  # 전문과 레코드는 DEBUG·검증 모드에서만
        if detail:
            bound = dict(params)
            CARD_LOG.log_query(label, query, bound, render_combined=lambda _: render_cypher_log(CARD_LOG, query, bound))
        started = perf_counter()
        with self.driver.session(database=self.database, default_access_mode=READ_ACCESS) as session:
            rows = session.execute_read(lambda tx: [record.data() for record in tx.run(query, **params)])
        CARD_LOG.log_summary("CYPHER", label, params=CARD_LOG.sanitize(params), rows=len(rows),
                             path=STATEMENTS.get(statement_id, ("", "미등록"))[1],
                             elapsed_ms=(perf_counter() - started) * 1000)
        if detail:
            CARD_LOG.log_result_data(label, [flatten_record(row) for row in rows])
        return rows

    def list_catalog(self) -> list[dict]:
        """질문 해석에 쓸 카드별·공통 혜택 목록과 적용 대상을 반환한다.

        Cypher 3건을 차례로 실행해 한 목록으로 합친다.
            catalog        카드 혜택(dp_card_bnft) + 규칙 대상·결제 기준 금액 → item_type="BENEFIT"
                           (공통 혜택과 dp_same_as로 동일성이 확인된 카드 혜택은 빼고 공통 혜택 쪽으로 보여 준다)
            item_catalog   혜택 외 상품 항목(dp_card_product_item, 연회비 등) → item_data.fee_lines의 같은 사실 참조 포함
            common_catalog 공통 혜택(dp_card_common_bnft) 전체와 적용 카드 이름 → item_type="COMMON_BENEFIT"
                           (적용 관계가 없으면 card="적용 카드 미확인")
        각 행의 key는 그래프 노드 key(JSON 배열 문자열)이며, retrieve의 get_detail 인자로 그대로 쓰인다.
        """
        rows = self._query(CATALOG_QUERY)
        for row in rows:
            row["card"] = source({"source_json": row.pop("card_source")}).get("product_nm", "미확인")
            row["item_type"] = "BENEFIT"
        for row in self._query(ITEM_CATALOG_QUERY):
            card = source({"source_json": row.pop("card_source")})
            item = source({"source_json": row.pop("item_source")})
            lines = (item.get("item_data") or {}).get("fee_lines") or []
            rows.append({**row, "card": card.get("product_nm", "미확인"), "issuer": card.get("issuer"),
                         "card_id": card.get("card_id"), "targets": [], "payment_min_amounts": [],
                         # 같은 사실을 담은 기존 혜택 참조(예: 가족카드 연회비 면제). 답변에서 한 번만 쓴다.
                         "same_fact_refs": [line["same_fact_item_ref"] for line in lines if line.get("same_fact_item_ref")]})
        for row in self._query(COMMON_CATALOG_QUERY):
            cards = row.pop("cards")
            rows.append({**row, "card": ", ".join(cards) or "적용 카드 미확인", "targets": [], "payment_min_amounts": [],
                         "item_type": "COMMON_BENEFIT"})
        return rows

    def list_benefits(self, keyword: str = "") -> list[dict]:
        """혜택명에 keyword가 들어간 카드·공통 혜택을 찾는다(BenefitSearchService._keyword의 점수 보강용)."""
        return self._query(LIST_QUERY, keyword=keyword.strip())

    def candidate_relations(self, ids: list[str]) -> dict[str, dict]:
        """검색 후보별 카드·대상·제외 문구를 관계로 찾는다."""
        # ID 문자열이 같은 카드·공통 혜택을 따로 돌려준다. 결과는 종류·소유자 포함 참조로 찾는다.
        return {entity_ref(row["key"], row["id"]): row for row in self._query(RELATION_QUERY, ids=ids)} if ids else {}

    def hop(self, name: str, **params) -> list[dict]:
        """다중 홉 조회를 실행한다."""
        return self._query(HOP_QUERIES[name], **params)

    def get_detail(self, key: str, sections: tuple[str, ...] = ALL_SECTIONS) -> dict | None:
        """혜택 상세를 조회한다. ``sections`` 에 없는 항목은 조회하지 않고 빈 목록으로 둔다.

        CardGraphRAG.retrieve가 그래프 key마다 호출한다. 실행 순서는 detail_statements와 같다.
            1. card.context : 혜택 노드와 카드(들)·공통서비스 정보. 없으면 None 반환
            2. sections 순서대로 rules / conditions / limits / evidence
               evidence는 key 종류에 따라 Cypher가 다르다 — 공통 혜택: common_evidence(dp_same_as로 연결된 카드 혜택의 근거),
               연회비 등 항목: item_evidence, 그 밖: benefit_evidence
        근거 행은 (dp_card_source_evidence)-[in_chunk]->(청크)-[on_page]->(페이지)-[in_document]->(문서) 경로로
        PDF 페이지와 인용 원문을 함께 돌려준다.

        Returns:
            ``{"context": ..., "rules": [...], "conditions": [...], "limits": [...], "evidence": [...]}`` 또는 None.
        """
        context = self._query(CONTEXT_QUERY, key=key)
        if not context:
            return None
        detail = {"context": context[0]}
        sources = context[0].get("card_sources")
        if sources is not None and len(sources) != 1:   # 적용 카드가 없거나 여럿이면 표시용 이름을 합친다.
            names = [source({"source_json": item}).get("product_nm") for item in sources]
            context[0]["card"] = {"source_json": json.dumps({"product_nm": ", ".join(names) or "적용 카드 미확인"}, ensure_ascii=False)}
        for name, query in SECTION_QUERIES.items():
            if name == "evidence" and is_common_key(key):
                query = COMMON_EVIDENCE_QUERY
            elif name == "evidence" and is_item_key(key):
                query = ITEM_EVIDENCE_QUERY
            detail[name] = self._query(query, key=key) if name in sections else []
        return detail


def connect() -> Neo4jSearch:
    """공통 드라이버 생성 함수로 Neo4j에 연결하고, NEO4J_DATABASE(없으면 기본 DB)를 대상으로 Neo4jSearch를 만든다."""
    driver =create_neo4j_driver()  # project helper keeps certificate verification enabled
    return Neo4jSearch(driver, os.getenv("NEO4J_DATABASE") or None)
