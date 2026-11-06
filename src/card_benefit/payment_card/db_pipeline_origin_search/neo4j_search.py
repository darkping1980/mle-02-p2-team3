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
BENEFIT_RELATIONS_QUERY = MAPPERS["graph_questions.benefit_relations"]
CONTEXT_QUERY = MAPPERS["graph_questions.benefit_context"]
EVIDENCE_QUERY = MAPPERS["graph_questions.benefit_evidence"]
COMMON_EVIDENCE_QUERY = MAPPERS["graph_questions.common_benefit_evidence"]
HOP_QUERIES = {name: MAPPERS[f"graph_questions.{name}"] for name in
               ("hop1_card_benefits", "hop2_card_rules", "hop2_card_common", "hop3_card_targets", "hop3_common_docs", "hop3_target_cards")}
QUERIES = {"카탈로그": CATALOG_QUERY, "항목 카탈로그": ITEM_CATALOG_QUERY, "항목 근거": ITEM_EVIDENCE_QUERY,
           "공통 카탈로그": COMMON_CATALOG_QUERY, "목록": LIST_QUERY, "후보 관계": RELATION_QUERY, "혜택 간 관계": BENEFIT_RELATIONS_QUERY,
            "카드·혜택·규칙·조건·한도": CONTEXT_QUERY, "근거": EVIDENCE_QUERY,
           "공통 혜택 근거": COMMON_EVIDENCE_QUERY, **HOP_QUERIES}
# 로그에 쓰는 Cypher 식별자와 그 쿼리가 지나가는 노드·관계 경로.
STATEMENTS = {
    "card.catalog": (CATALOG_QUERY, "(dp_card_product)-[dp_has_item]->(dp_card_product_item)"),
    "card.item_catalog": (ITEM_CATALOG_QUERY, "(dp_card_product)-[dp_has_item]->(dp_card_product_item)"),
    "card.item_evidence": (ITEM_EVIDENCE_QUERY, "(dp_card_product)-[dp_has_item]->(dp_card_product_item)-[dp_supported_by]->"
                                                "(dp_card_source_evidence)-[dp_in_chunk]->(dp_card_doc_chunk)-[dp_on_page]->(dp_card_doc_page)"),
    "card.common_catalog": (COMMON_CATALOG_QUERY, "(dp_card_common_bnft)-[dp_belongs_to]->(dp_card_common), optionally (dp_card_common_bnft)-[dp_applies_to]->(dp_card_product)"),
    "card.list": (LIST_QUERY, "(dp_card_product_item|dp_card_common_bnft)"),
    "card.relations": (RELATION_QUERY, "dp_card_product_item and dp_card_common_bnft application relationships"),
    "card.benefit_relations": (BENEFIT_RELATIONS_QUERY, "dp_card_product_item.relation_list (source JSON)"),
    "card.context": (CONTEXT_QUERY, "dp_card_product_item source row plus card/common ownership"),
    "card.evidence": (EVIDENCE_QUERY, "(dp_card_product_item|dp_card_common_bnft)-[dp_supported_by]->(dp_card_source_evidence)"
                                      "-[dp_in_chunk]->(dp_card_doc_chunk)-[dp_on_page]->(dp_card_doc_page)-[dp_in_document]->(dp_card_doc)"),
    "card.common_evidence": (COMMON_EVIDENCE_QUERY, "(dp_card_common_bnft)-[dp_supported_by]->(dp_card_source_evidence)"
                                                    "-[dp_in_chunk]->(dp_card_doc_chunk)-[dp_on_page]->(dp_card_doc_page)-[dp_in_document]->(dp_card_doc)"),
    **{f"card.{name}": (query, name) for name, query in HOP_QUERIES.items()},
}
STATEMENT_IDS = {query: statement_id for statement_id, (query, _) in STATEMENTS.items()}
SECTION_QUERIES = {"evidence": EVIDENCE_QUERY}
ALL_SECTIONS = tuple(SECTION_QUERIES)

# region 배치 조회 (P3, 2026-11-05) — 같은 named query를 한 문장으로 묶어 네트워크 왕복을 줄인다. 데이터 캐시는 없다.
# 각 named query 본문을 CALL 서브쿼리에 넣고 ``$key``/``$keyword`` 만 바깥 변수로 바꾼다. 단독 실행용 끝 세미콜론은 제거한다.
# 반환 행은 원래 RETURN 열 순서대로 다시 만든다. 근거 행만 로직이 읽는 열(owner_labels, rule_key, link, evidence)로 줄인다.
# 청크·페이지·문서의 전체 속성은 전송하지 않지만 MATCH 경로(근거→청크→페이지→문서)는 그대로라 같은 근거만 조회된다.
CONTEXT_FIELDS = ("card", "benefit", "card_sources", "common", "common_docs", "card_labels", "benefit_labels", "extraction_sources")
SECTION_FIELDS = {"evidence": ("owner_labels", "owner", "evidence_labels", "rule_key", "link", "evidence", "chunk", "page", "document")}
SECTION_PRESENT = {"evidence": "evidence"}
LIST_FIELDS = ("key", "name", "id", "status")
CATALOG_FIELDS = {"catalog": ("key", "name", "id", "status", "card_source", "rule_list", "item_cond_expr",
                              "item_rule_txt", "item_limit_txt"),
                  "items": ("key", "name", "id", "status", "item_type", "card_id", "item_source", "item_data", "item_rule_txt", "item_cd", "card_source"),
                  "commons": ("key", "name", "id", "status", "common_nm", "cards"),
                  "products": ("card_id", "product_nm")}


def _subquery(query: str, variable: str | None = None) -> str:
    """named query를 서브쿼리 본문으로 쓴다. 파라미터 이름을 바꾸고 단독 실행용 종료 세미콜론을 제거한다."""
    body = (query.replace(f"${variable}", variable) if variable else query).rstrip().removesuffix(";")
    if "$" in body:
        raise ValueError("배치 서브쿼리에 바꾸지 않은 파라미터가 남았습니다")
    return body


def _map(fields: tuple[str, ...]) -> str:
    return "{" + ", ".join(f"{field}: {field}" for field in fields) + "}"


def evidence_query_for(key: str) -> str:
    """get_detail과 같은 규칙으로 key 종류별 근거 Cypher를 고른다."""
    return COMMON_EVIDENCE_QUERY if is_common_key(key) else ITEM_EVIDENCE_QUERY if is_item_key(key) else EVIDENCE_QUERY


def detail_batch_query(evidence_query: str, sections: tuple[str, ...]) -> str:
    """여러 혜택 key의 context + sections를 한 문장으로 조회한다(근거 Cypher가 같은 key끼리)."""
    lines = ["UNWIND $keys AS key", "CALL (key) {", _subquery(CONTEXT_QUERY, "key"), "}",
             f"WITH key, collect({_map(CONTEXT_FIELDS)}) AS context"]
    carried = ["key", "context"]
    for name, query in SECTION_QUERIES.items():
        if name not in sections:
            continue
        query = evidence_query if name == "evidence" else query
        lines += ["OPTIONAL CALL (key) {", _subquery(query, "key"), "}",
                  f"WITH {', '.join(carried)}, [x IN collect({_map(SECTION_FIELDS[name])}) WHERE x.{SECTION_PRESENT[name]} IS NOT NULL] AS {name}"]
        carried.append(name)
    lines.append("RETURN " + ", ".join(carried))
    return "\n".join(lines)


LIST_BATCH_QUERY = "\n".join(["UNWIND $keywords AS keyword", "CALL (keyword) {", _subquery(LIST_QUERY, "keyword"), "}",
                              "RETURN keyword, " + ", ".join(LIST_FIELDS)])
CATALOG_BATCH_QUERY = "\n".join([
    "OPTIONAL CALL () {", _subquery(CATALOG_QUERY), "}",
    f"WITH [x IN collect({_map(CATALOG_FIELDS['catalog'])}) WHERE x.key IS NOT NULL] AS catalog",
    "OPTIONAL CALL () {", _subquery(ITEM_CATALOG_QUERY), "}",
    f"WITH catalog, [x IN collect({_map(CATALOG_FIELDS['items'])}) WHERE x.key IS NOT NULL] AS items",
    "OPTIONAL CALL () {", _subquery(COMMON_CATALOG_QUERY), "}",
    f"WITH catalog, items, [x IN collect({_map(CATALOG_FIELDS['commons'])}) WHERE x.key IS NOT NULL] AS commons",
    "OPTIONAL CALL () {", "MATCH (p:dp_card_product) RETURN p.card_id AS card_id,p.product_nm AS product_nm ORDER BY card_id", "}",
    f"WITH catalog, items, commons, [x IN collect({_map(CATALOG_FIELDS['products'])}) WHERE x.card_id IS NOT NULL] AS products",
    "RETURN catalog, items, commons, products"])


def _ordered(row: dict, fields: tuple[str, ...]) -> dict:
    """map으로 받은 행을 원래 RETURN 열 순서의 dict로 만든다."""
    return {field: row[field] for field in fields}


def _finish_context(context: dict) -> dict:
    """get_detail·get_details 공통: 적용 카드가 없거나 여럿이면 표시용 카드 이름을 합친다."""
    sources = context.get("card_sources")
    if sources is not None and len(sources) != 1:
        names = [item.get("product_nm") or source({"source_json": item}).get("product_nm") for item in sources]
        context["card"] = {"source_json": json.dumps({"product_nm": ", ".join(names) or "적용 카드 미확인"}, ensure_ascii=False)}
    return context


def catalog_rows(catalog: list[dict], items: list[dict], commons: list[dict]) -> list[dict]:
    """``list_catalog`` 의 행 처리. 세 카탈로그 Cypher 결과(행 순서 그대로)를 질문 해석용 한 목록으로 만든다."""
    rows = catalog
    for row in rows:
        card = source({"source_json": row.pop("card_source")})
        rules = _decode_json(row.pop("rule_list", None), [])
        item_expr = _decode_json(row.pop("item_cond_expr", None), {})
        conditions = []
        for _, _, expression in _condition_expressions({"rule_list": rules, "item_cond_expr": item_expr}):
            for branch in expression.get("branches") or []:
                for atom in branch.get("atoms") or []:
                    if not isinstance(atom, dict):
                        continue
                    text = atom.get("cond_raw_txt") or atom.get("excl_raw_txt")
                    if text and text not in conditions:
                        conditions.append(text)
        row["card"] = card.get("product_nm", "미확인")
        row["card_id"] = card.get("card_id")
        row["issuer"] = card.get("issuer")
        row["item_type"] = "BENEFIT"
        row["targets"] = list(dict.fromkeys(
            target.get("target_nm") for rule in rules if isinstance(rule, dict)
            for target in rule.get("target_list") or [] if isinstance(target, dict) and target.get("target_nm")))
        row["payment_min_amounts"] = _payment_minimums(rules, item_expr)
        # Compact conditions distinguish similar benefit names without returning source JSON.
        row["condition_text"] = conditions
    for row in items:
        card = source({"source_json": row.pop("card_source")})
        item = source({"source_json": row.pop("item_source"), "item_data": row.pop("item_data", None),
                       "item_rule_txt": row.pop("item_rule_txt", None), "item_cd": row.pop("item_cd", None)})
        lines = (item.get("item_data") or {}).get("fee_lines") or []
        rows.append({**row, "card": card.get("product_nm", "미확인"), "issuer": card.get("issuer"),
                     "card_id": card.get("card_id"), "targets": [], "payment_min_amounts": [],
                     # 같은 사실을 담은 기존 혜택 참조(예: 가족카드 연회비 면제). 답변에서 한 번만 쓴다.
                     "same_fact_refs": [line["same_fact_item_ref"] for line in lines if line.get("same_fact_item_ref")]})
    for row in commons:
        cards = row.pop("cards")
        rows.append({**row, "card": ", ".join(cards) or "적용 카드 미확인", "targets": [], "payment_min_amounts": [],
                     "item_type": "COMMON_BENEFIT"})
    return rows
# endregion


def source(props: dict) -> dict:
    """Decode source_json and overlay actual Neo4j columns; Neo4j projection wins."""
    if not isinstance(props, dict):
        return {}
    value = props.get("source_json")
    try:
        decoded = json.loads(value) if isinstance(value, str) and value else value
    except (TypeError, ValueError):
        decoded = {}
    result = dict(decoded) if isinstance(decoded, dict) else {}
    for name, item in props.items():
        if name == "source_json":
            continue
        result[name] = _decode_json(item, item) if name in {"rule_list", "item_cond_expr", "item_data", "relation_list"} else item
    for name in ("rule_list", "item_cond_expr", "item_data", "relation_list"):
        if name in result:
            result[name] = _decode_json(result[name], result[name])
    return result


def _decode_json(value, fallback=None):
    if not isinstance(value, str):
        return value if value is not None else fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback if fallback is not None else value


def _condition_expressions(benefit: dict) -> list[tuple[str, str | None, dict]]:
    """Yield item-level and rule-scoped condition expressions without losing their owner."""
    result = []
    item_expr = _decode_json(benefit.get("item_cond_expr"), {})
    if isinstance(item_expr, dict) and item_expr:
        result.append(("BENEFIT", None, item_expr))
    rules = _decode_json(benefit.get("rule_list"), [])
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            expr = _decode_json(rule.get("cond_expr"), {})
            if isinstance(expr, dict) and expr:
                result.append(("RULE", rule.get("rule_key"), expr))
            # Compatibility with extracted rows that store conditions directly on a rule.
            conditions = _decode_json(rule.get("conditions"), [])
            if isinstance(conditions, list) and conditions:
                result.append(("RULE", rule.get("rule_key"), {"branches": [{"branch_no": 1, "atoms": conditions}]}))
    return result


def _normalize_item_contract(benefit: dict) -> dict:
    """Project table-faithful rule_list/item_cond_expr JSON into the stable Python detail contract."""
    raw_rules = _decode_json(benefit.get("rule_list"), [])
    rules = []
    for rule in raw_rules if isinstance(raw_rules, list) else []:
        if not isinstance(rule, dict):
            continue
        targets = [target.get("target_nm") for target in rule.get("target_list") or []
                   if isinstance(target, dict) and target.get("target_nm")]
        rules.append({"rule": rule, "targets": targets})
    condition_rows = []
    for owner_cd, rule_key, expr in _condition_expressions(benefit):
        expr_key = expr.get("key") or expr.get("expr_key") or f"{owner_cd}:{rule_key or 'item'}"
        for branch_index, branch in enumerate(expr.get("branches") or [], start=1):
            if not isinstance(branch, dict):
                continue
            for atom in branch.get("atoms") or []:
                if isinstance(atom, dict):
                    condition_rows.append({"owner_cd": owner_cd, "rule_key": rule_key,
                                           "expression": {"key": expr_key},
                                           "branch_no": branch.get("branch_no", branch_index), "atom": atom})
    return {"rules": rules, "conditions": condition_rows}


def _payment_minimums(rules: list, item_expr: dict | None = None) -> list[int]:
    """Return only explicit per-transaction SPEND_REQ minima used by payment amount filtering."""
    values = []
    synthetic = {"rule_list": rules, "item_cond_expr": item_expr or {}}
    for _, _, expr in _condition_expressions(synthetic):
        for branch in expr.get("branches") or []:
            for atom in branch.get("atoms") or []:
                if (atom.get("cond_type_cd") == "SPEND_REQ" and atom.get("cond_basis_cd") == "TXN_AMT"
                        and atom.get("cond_min_amt") is not None):
                    try:
                        values.append(int(atom["cond_min_amt"]))
                    except (TypeError, ValueError):
                        continue
    return sorted(set(values))


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
    """상세 데이터와 PDF 근거는 물리적으로 하나의 배치 Cypher로 조회된다."""
    return ["card.detail_batch"] if sections else []


def detail_plan(keys: list[str], sections: tuple[str, ...]) -> list[dict]:
    """실제 detail_batch 요청 단위와 동일한 Browser용 조회 계획을 만든다."""
    plans = []
    groups: dict[str, list[str]] = {}
    for key in dict.fromkeys(keys):
        groups.setdefault(evidence_query_for(key), []).append(key)
    for evidence_query, group in groups.items():
        query = detail_batch_query(evidence_query, sections)
        params = {"keys": group}
        inline, _ = render_cypher_inline(CARD_LOG, query, params)
        plans.append({"statement_id": "card.detail_batch", "path": "card.context + " + STATEMENT_IDS.get(evidence_query, "card.evidence"),
                      "cypher": query, "parameters": params, "browser_cypher": inline or query})
    return plans


def catalog_batch_plan() -> dict:
    """Return the single physical catalog query used by ``list_catalog``."""
    inline, _ = render_cypher_inline(CARD_LOG, CATALOG_BATCH_QUERY, {})
    return {"statement_id": "card.catalog_batch", "path": "card.catalog + card.item_catalog + card.common_catalog + card.products",
            "cypher": CATALOG_BATCH_QUERY, "parameters": {}, "browser_cypher": inline or CATALOG_BATCH_QUERY}


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
        return self._run(statement_id, query, STATEMENTS.get(statement_id, ("", "미등록"))[1], params)

    def _run(self, statement_id: str, query: str, path: str, params: dict) -> list[dict]:
        """``_query`` 의 실행부. 배치 문장(STATEMENTS에 없는 생성 문장)도 식별자·경로를 붙여 같은 방식으로 실행·기록한다."""
        label = f"{REQUEST_ID.get()}/{statement_id}"
        detail = DETAIL_LOG.get() or CARD_LOG.logger.isEnabledFor(logging.DEBUG)  # 전문과 레코드는 DEBUG·검증 모드에서만
        if detail:
            bound = dict(params)
            CARD_LOG.log_query(label, query, bound, render_combined=lambda _: render_cypher_log(CARD_LOG, query, bound))
        started = perf_counter()
        with self.driver.session(database=self.database, default_access_mode=READ_ACCESS) as session:
            rows = session.execute_read(lambda tx: [record.data() for record in tx.run(query, **params)])
        query_elapsed_ms = (perf_counter() - started) * 1000
        serialization_started = perf_counter()
        returned_bytes = len(json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8"))
        CARD_LOG.log_summary("CYPHER", label, params=CARD_LOG.sanitize(params), rows=len(rows), path=path,
                             elapsed_ms=query_elapsed_ms)
        CARD_LOG.log_summary("PERF", REQUEST_ID.get(), phase=f"{statement_id}_result_size", rows=len(rows),
                             returned_bytes=returned_bytes,
                             size_measure_ms=(perf_counter() - serialization_started) * 1000)
        if detail:
            CARD_LOG.log_result_data(label, [flatten_record(row) for row in rows])
        return rows

    def list_catalog(self) -> list[dict]:
        """질문 해석에 쓸 카드별·공통 혜택 목록과 적용 대상을 반환한다.

        Cypher 3건을 차례로 실행해 한 목록으로 합친다.
            catalog        카드 상품 항목(dp_card_product_item) 중 BENEFIT 행
            item_catalog   혜택 외 상품 항목(dp_card_product_item, 연회비 등) → item_data.fee_lines의 같은 사실 참조 포함
            common_catalog 공통 혜택(dp_card_common_bnft) 전체와 적용 카드 이름
                           (적용 관계가 없으면 card="적용 카드 미확인")
        각 행의 key는 그래프 노드 key(JSON 배열 문자열)이며, retrieve의 get_detail 인자로 그대로 쓰인다.

        세 Cypher는 서브쿼리로 묶어 한 문장(왕복 1회)으로 실행한다(P3). 조회 조건·정렬·행 처리는 기존과 같다.
        """
        batch = self._run("card.catalog_batch", CATALOG_BATCH_QUERY, "card.catalog + card.item_catalog + card.common_catalog + card.products", {})[0]
        started = perf_counter()
        self.catalog_products = [_ordered(row, CATALOG_FIELDS["products"]) for row in batch.get("products", [])]
        item_rows = [_ordered(row, CATALOG_FIELDS["items"]) for row in batch["items"]]
        self.catalog_terms = {}
        for row in item_rows:
            if row.get("item_type") != "TERMS":
                continue
            card = source({"source_json": row.get("card_source")})
            item = source({"source_json": row.get("item_source"), "item_data": row.get("item_data"),
                           "item_rule_txt": row.get("item_rule_txt"), "item_cd": row.get("item_cd")})
            card_id = row.get("card_id", card.get("card_id"))
            if card_id is not None:
                self.catalog_terms.setdefault(int(card_id), []).append({**item, "card_id": int(card_id),
                    "card_product_item_id": row.get("id"), "product_nm": card.get("product_nm")})
        rows = catalog_rows([_ordered(row, CATALOG_FIELDS["catalog"]) for row in batch["catalog"]],
                            item_rows, [_ordered(row, CATALOG_FIELDS["commons"]) for row in batch["commons"]])
        CARD_LOG.log_summary("PERF", REQUEST_ID.get(), phase="catalog_python_transform",
                             elapsed_ms=(perf_counter() - started) * 1000, catalog_rows=len(rows), product_rows=len(self.catalog_products))
        return rows

    def list_benefits(self, keyword: str = "") -> list[dict]:
        """혜택명에 keyword가 들어간 카드·공통 혜택을 찾는다(BenefitSearchService._keyword의 점수 보강용)."""
        return self._query(LIST_QUERY, keyword=keyword.strip())

    def list_benefits_many(self, keywords: list[str]) -> dict[str, list[dict]]:
        """``list_benefits`` 를 낱말 여러 개에 대해 한 문장으로 실행한다. 낱말 → list_benefits(낱말)와 같은 행 목록(P3)."""
        terms = list(dict.fromkeys(keyword.strip() for keyword in keywords))
        result = {term: [] for term in terms}
        if not terms:
            return result
        for row in self._run("card.list_batch", LIST_BATCH_QUERY, "card.list × 낱말", {"keywords": terms}):
            result[row["keyword"]].append(_ordered(row, LIST_FIELDS))
        return result

    def get_details(self, keys: list[str], sections: tuple[str, ...] = ALL_SECTIONS) -> dict[str, dict | None]:
        """여러 혜택의 ``get_detail`` 을 근거 Cypher 종류별 한 문장으로 조회한다(P3). key → get_detail(key)와 같은 구조.

        혜택 N개 × (context + sections) 문장을 1문장(혜택·연회비 항목·공통 혜택이 섞이면 종류 수만큼)으로 줄인다.
        근거 행은 로직이 읽는 열(owner_labels, rule_key, link, evidence)만 담는다.
        """
        keys = list(dict.fromkeys(keys))
        result: dict[str, dict | None] = {key: None for key in keys}
        groups: dict[str, list[str]] = {}
        for key in keys:
            groups.setdefault(evidence_query_for(key), []).append(key)
        names = [name for name in SECTION_QUERIES if name in sections]
        for evidence_query, group in groups.items():
            evidence_id = STATEMENT_IDS.get(evidence_query, "card.evidence")
            path = "card.context + " + " + ".join(evidence_id if name == "evidence" else f"card.{name}" for name in names)
            rows = self._run("card.detail_batch", detail_batch_query(evidence_query, sections), path, {"keys": group})
            transform_started = perf_counter()
            for row in rows:
                if not row.get("context"):
                    continue
                detail = {"context": _finish_context(_ordered(row["context"][0], CONTEXT_FIELDS))}
                benefit = source(detail["context"]["benefit"])
                detail.update(_normalize_item_contract(benefit))
                detail["limits"] = ([{"limit_text": benefit.get("item_limit_txt") or benefit.get("bnft_limit_txt")}]
                                     if benefit.get("item_limit_txt") or benefit.get("bnft_limit_txt") else [])
                detail["evidence"] = [_ordered(item, SECTION_FIELDS["evidence"]) for item in row.get("evidence", [])] if "evidence" in sections else []
                result[row["key"]] = detail
            CARD_LOG.log_summary("PERF", REQUEST_ID.get(), phase="detail_python_transform",
                                 elapsed_ms=(perf_counter() - transform_started) * 1000, requested_keys=len(group),
                                 detail_rows=len(rows), returned_bytes=len(json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")))
        return result

    def candidate_relations(self, ids: list[str]) -> dict[str, dict]:
        """검색 후보별 카드·대상·제외 문구를 관계로 찾는다."""
        # ID 문자열이 같은 카드·공통 혜택을 따로 돌려준다. 결과는 종류·소유자 포함 참조로 찾는다.
        return {entity_ref(row["key"], row["id"]): row for row in self._query(RELATION_QUERY, ids=ids)} if ids else {}

    def benefit_relations(self, key: str) -> list[dict]:
        """혜택에서 출발하는 관계를 명시적으로 조회한다. 기존 검색 결과에는 반영하지 않는다."""
        return self._query(BENEFIT_RELATIONS_QUERY, key=key)

    def hop(self, name: str, **params) -> list[dict]:
        """다중 홉 조회를 실행한다."""
        return self._query(HOP_QUERIES[name], **params)

    def get_detail(self, key: str, sections: tuple[str, ...] = ALL_SECTIONS) -> dict | None:
        """혜택 상세를 조회한다. ``sections`` 에 없는 항목은 조회하지 않고 빈 목록으로 둔다.

        CardGraphRAG.retrieve가 그래프 key마다 호출한다. 실행 순서는 detail_statements와 같다.
            1. card.context : 혜택 노드와 카드(들)·공통서비스 정보. 없으면 None 반환
            2. sections 순서대로 원장 JSON/text와 evidence를 투영한다. RULE/COND 탐색 노드는 없으며,
               PDF는 실제 dp_supported_by 관계에서 Evidence → chunk → page → document를 따라 조회한다.
        근거 행은 (dp_card_source_evidence)-[in_chunk]->(청크)-[on_page]->(페이지)-[in_document]->(문서) 경로로
        PDF 페이지와 인용 원문을 함께 돌려준다.

        Returns:
            ``{"context": ..., "rules": [...], "conditions": [...], "limits": [...], "evidence": [...]}`` 또는 None.
        """
        return self.get_details([key], sections).get(key)


def connect() -> Neo4jSearch:
    """공통 드라이버 생성 함수로 Neo4j에 연결하고, NEO4J_DATABASE(없으면 기본 DB)를 대상으로 Neo4jSearch를 만든다."""
    driver =create_neo4j_driver()  # project helper keeps certificate verification enabled
    return Neo4jSearch(driver, os.getenv("NEO4J_DATABASE") or None)
