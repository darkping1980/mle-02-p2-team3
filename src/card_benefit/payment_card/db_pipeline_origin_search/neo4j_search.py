"""DF 그래프 읽기 전용 조회. Cypher는 graph_questions.cypher에 있고 실행과 로그는 여기서 맡는다."""
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

NAMESPACE = "df_one_pick_style"
# 공통 Neo4j logger의 자식이다. 부모에 붙는 기존 handler로 출력되므로 handler를 새로 만들지 않는다.
CARD_LOGGER_NAME = "car_search_rag.neo4j.card_graphrag"
# 레시피의 Neo4jDbSession과 같은 combined 모드. 로그의 Cypher에는 값이 들어가 DBeaver에 그대로 붙일 수 있다.
CARD_LOG = QueryLogger(logging.getLogger(CARD_LOGGER_NAME), log_mode="combined", query_label="Cypher",
                       result_log=True, sensitive_keys=DEFAULT_SENSITIVE_KEYS)
REQUEST_ID: ContextVar[str] = ContextVar("card_request_id", default="-")  # Cypher 로그를 질문 요청과 연결한다.
DETAIL_LOG: ContextVar[bool] = ContextVar("card_detail_log", default=False)  # 검증 모드에서 Cypher 전문과 레코드를 남긴다.
# 레코드 표시에서 뺄 내부 속성과, source_json에서 꺼내 보여 줄 값.
HIDDEN_PROPERTIES = frozenset({"source_json", "namespace", "key", "card_source"})
SOURCE_FIELDS = ("cond_basis_cd", "excl_raw_txt", "cond_status_cd", "value_unit_cd", "calc_method_cd", "rule_select_cd",
                 "rule_status_cd", "quote_txt", "card_cond_status_cd")

# 공통 세션의 ``// name:`` mapper만 재사용한다. 실행은 READ_ACCESS를 보장하는 Neo4jSearch._query가 맡는다.
MAPPERS = Neo4jDbSession(mapper_root=Path(__file__).resolve().parent).mappers
CATALOG_QUERY = MAPPERS["graph_questions.catalog"]
LIST_QUERY = MAPPERS["graph_questions.list_benefits"]
CONTEXT_QUERY = MAPPERS["graph_questions.benefit_context"]
RULE_QUERY = MAPPERS["graph_questions.benefit_rules"]
CONDITION_QUERY = MAPPERS["graph_questions.benefit_conditions"]
LIMIT_QUERY = MAPPERS["graph_questions.benefit_limits"]
EVIDENCE_QUERY = MAPPERS["graph_questions.benefit_evidence"]
QUERIES = {"카탈로그": CATALOG_QUERY, "목록": LIST_QUERY, "카드·혜택": CONTEXT_QUERY, "규칙·대상": RULE_QUERY,
           "조건식": CONDITION_QUERY, "한도": LIMIT_QUERY, "근거": EVIDENCE_QUERY}
# 로그에 쓰는 Cypher 식별자와 그 쿼리가 지나가는 노드·관계 경로.
STATEMENTS = {
    "card.catalog": (CATALOG_QUERY, "(df_card_product)-[df_has_benefit]->(df_card_bnft)"
                                    "-[df_has_rule]->(df_bnft_rule)-[df_targets]->(df_rule_target), "
                                    "(df_bnft_rule)-[df_has_expr]->()-[df_has_branch]->()-[df_has_atom]->(df_cond_atom)"),
    "card.list": (LIST_QUERY, "(df_card_product)-[df_has_benefit]->(df_card_bnft)"),
    "card.context": (CONTEXT_QUERY, "(df_card_product)-[df_has_benefit]->(df_card_bnft)"),
    "card.rules": (RULE_QUERY, "(df_card_bnft)-[df_has_rule]->(df_bnft_rule)-[df_targets]->(df_rule_target)"),
    "card.conditions": (CONDITION_QUERY, "(df_card_product|df_card_bnft|df_bnft_rule)-[df_has_expr]->(df_cond_expr)"
                                         "-[df_has_branch]->(df_cond_branch)-[df_has_atom]->(df_cond_atom)"),
    "card.limits": (LIMIT_QUERY, "(df_card_bnft).limit_text"),
    "card.evidence": (EVIDENCE_QUERY, "(df_card_product|df_card_bnft|df_bnft_rule)-[df_supported_by]->(df_card_source_evidence)"
                                      "-[df_in_chunk]->(df_card_doc_chunk)-[df_on_page]->(df_card_doc_page)-[df_in_document]->(df_card_doc)"),
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


def statement_plan(statement_id: str, **params) -> dict:
    """실행할 Cypher를 표시용으로 만든다. ``browser_cypher`` 는 값이 들어가 그대로 실행할 수 있다."""
    query, path = STATEMENTS[statement_id]
    bound = {"ns": NAMESPACE, **params}
    inline, _ = render_cypher_inline(CARD_LOG, query, bound)
    return {"statement_id": statement_id, "path": path, "cypher": query, "parameters": bound, "browser_cypher": inline or query}


def detail_statements(sections: tuple[str, ...] = ALL_SECTIONS) -> list[str]:
    """``get_detail`` 이 실행하는 순서대로 Cypher 식별자를 돌려준다."""
    return ["card.context", *(f"card.{name}" for name in SECTION_QUERIES if name in sections)]


def detail_plan(keys: list[str], sections: tuple[str, ...]) -> list[dict]:
    """혜택 키별로 ``get_detail`` 이 실행할 Cypher 목록을 만든다."""
    return [statement_plan(statement_id, key=key) for key in keys for statement_id in detail_statements(sections)]


class Neo4jSearch:
    def __init__(self, driver, database: str | None = None):
        self.driver = driver
        self.database = database

    def _query(self, query: str, **params) -> list[dict]:
        statement_id = STATEMENT_IDS.get(query, "card.unregistered")
        label = f"{REQUEST_ID.get()}/{statement_id}"
        detail = DETAIL_LOG.get() or CARD_LOG.logger.isEnabledFor(logging.DEBUG)  # 전문과 레코드는 DEBUG·검증 모드에서만
        if detail:
            bound = {"ns": NAMESPACE, **params}
            CARD_LOG.log_query(label, query, bound, render_combined=lambda _: render_cypher_log(CARD_LOG, query, bound))
        started = perf_counter()
        with self.driver.session(database=self.database, default_access_mode=READ_ACCESS) as session:
            rows = session.execute_read(lambda tx: [record.data() for record in tx.run(query, ns=NAMESPACE, **params)])
        CARD_LOG.log_summary("CYPHER", label, params=CARD_LOG.sanitize(params), rows=len(rows),
                             path=STATEMENTS.get(statement_id, ("", "미등록"))[1],
                             elapsed_ms=(perf_counter() - started) * 1000)
        if detail:
            CARD_LOG.log_result_data(label, [flatten_record(row) for row in rows])
        return rows

    def list_catalog(self) -> list[dict]:
        """질문 해석에 쓸 실제 혜택 목록과 적용 대상을 반환한다."""
        rows = self._query(CATALOG_QUERY)
        for row in rows:
            row["card"] = source({"source_json": row.pop("card_source")}).get("product_nm", "미확인")
        return rows

    def list_benefits(self, keyword: str = "") -> list[dict]:
        return self._query(LIST_QUERY, keyword=keyword.strip())

    def get_detail(self, key: str, sections: tuple[str, ...] = ALL_SECTIONS) -> dict | None:
        """혜택 상세를 조회한다. ``sections`` 에 없는 항목은 조회하지 않고 빈 목록으로 둔다."""
        context = self._query(CONTEXT_QUERY, key=key)
        if not context:
            return None
        detail = {"context": context[0]}
        for name, query in SECTION_QUERIES.items():
            detail[name] = self._query(query, key=key) if name in sections else []
        return detail


def connect() -> Neo4jSearch:
    driver = create_neo4j_driver()  # project helper keeps certificate verification enabled
    return Neo4jSearch(driver, os.getenv("NEO4J_DATABASE") or None)
