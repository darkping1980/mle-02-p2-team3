"""A8 시험 그래프 읽기 전용 조회. Cypher는 graph_questions.cypher에 있고 실행과 로그는 여기서 맡는다."""
from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from pathlib import Path
from time import perf_counter

from neo4j import READ_ACCESS

NAMESPACE = "ONE_PICK_STYLE_A8"
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "recipe"))
from recipe_recommender.neo4j_connection import create_neo4j_driver  # noqa: E402
from src.common.neo4j_db_session import Neo4jDbSession  # noqa: E402
from src.common.query_logger import DEFAULT_SENSITIVE_KEYS, QueryLogger  # noqa: E402

# 공통 Neo4j logger의 자식이다. 부모에 붙는 기존 handler로 출력되므로 handler를 새로 만들지 않는다.
CARD_LOGGER_NAME = "car_search_rag.neo4j.card_graphrag"
CARD_LOG = QueryLogger(logging.getLogger(CARD_LOGGER_NAME), log_mode="separate", query_label="Cypher",
                       sensitive_keys=DEFAULT_SENSITIVE_KEYS)
REQUEST_ID: ContextVar[str] = ContextVar("card_request_id", default="-")  # Cypher 로그를 질문 요청과 연결한다.

# 공통 세션의 ``// name:`` mapper만 재사용한다. 실행은 READ_ACCESS를 보장하는 Neo4jSearch._query가 맡는다.
MAPPERS = Neo4jDbSession(mapper_root=Path(__file__).resolve().parent).mappers
CATALOG_QUERY = MAPPERS["graph_questions.catalog"]
LIST_QUERY = MAPPERS["graph_questions.list_benefits"]
CONTEXT_QUERY = MAPPERS["graph_questions.benefit_context"]
RULE_QUERY = MAPPERS["graph_questions.benefit_rules"]
CONDITION_QUERY = MAPPERS["graph_questions.benefit_conditions"]
LIMIT_QUERY = MAPPERS["graph_questions.benefit_limits"]
EVIDENCE_QUERY = MAPPERS["graph_questions.benefit_evidence"]
QUERIES = {"카탈로그": CATALOG_QUERY, "목록": LIST_QUERY, "카드·정책": CONTEXT_QUERY, "규칙·대상": RULE_QUERY,
           "조건식": CONDITION_QUERY, "한도": LIMIT_QUERY, "근거": EVIDENCE_QUERY}
# 로그에 쓰는 Cypher 식별자와 그 쿼리가 지나가는 노드·관계 경로.
STATEMENTS = {
    "card.catalog": (CATALOG_QUERY, "(A8Card)-[A8_HAS_POLICY]->(A8Policy)-[A8_HAS_BENEFIT]->(A8Benefit)"
                                    "-[A8_HAS_RULE]->(A8Rule)-[A8_TARGETS]->(A8Target), "
                                    "(A8Rule)-[A8_HAS_EXPR]->()-[A8_HAS_BRANCH]->()-[A8_HAS_ATOM]->(A8Condition)"),
    "card.list": (LIST_QUERY, "(A8Card)-[A8_HAS_POLICY]->(A8Policy)-[A8_HAS_BENEFIT]->(A8Benefit)"),
    "card.context": (CONTEXT_QUERY, "(A8Card)-[A8_HAS_POLICY]->(A8Policy)-[A8_HAS_BENEFIT]->(A8Benefit)"),
    "card.rules": (RULE_QUERY, "(A8Benefit)-[A8_HAS_RULE]->(A8Rule)-[A8_TARGETS]->(A8Target)"),
    "card.conditions": (CONDITION_QUERY, "(A8Policy|A8Benefit|A8Rule)-[A8_HAS_EXPR]->(A8Expression)"
                                         "-[A8_HAS_BRANCH]->(A8Branch)-[A8_HAS_ATOM]->(A8Condition)"),
    "card.limits": (LIMIT_QUERY, "(A8Benefit)-[A8_HAS_RULE]->(A8Rule)-[A8_CONSUMES]->(A8LimitPool)"),
    "card.evidence": (EVIDENCE_QUERY, "(A8Policy|A8Benefit|A8Rule|A8LimitPool)-[A8_SUPPORTED_BY]->(A8Evidence)"
                                      "-[A8_IN_CHUNK]->(A8Chunk)-[A8_ON_PAGE]->(A8Page)-[A8_IN_DOCUMENT]->(A8Document)"),
}
STATEMENT_IDS = {query: statement_id for statement_id, (query, _) in STATEMENTS.items()}
SECTION_QUERIES = {"rules": RULE_QUERY, "conditions": CONDITION_QUERY, "limits": LIMIT_QUERY,
                   "evidence": EVIDENCE_QUERY}
ALL_SECTIONS = tuple(SECTION_QUERIES)


def source(props: dict) -> dict:
    """Decode the original JSON; never infer a missing value as approved."""
    value = props.get("source_json")
    return json.loads(value) if value else {}


class Neo4jSearch:
    def __init__(self, driver, database: str | None = None):
        self.driver = driver
        self.database = database

    def _query(self, query: str, **params) -> list[dict]:
        statement_id = STATEMENT_IDS.get(query, "card.unregistered")
        label = f"{REQUEST_ID.get()}/{statement_id}"
        if CARD_LOG.logger.isEnabledFor(logging.DEBUG):       # Cypher 전문은 DEBUG에서만 출력한다.
            CARD_LOG.log_query(label, query, {"ns": NAMESPACE, **params})
        started = perf_counter()
        with self.driver.session(database=self.database, default_access_mode=READ_ACCESS) as session:
            rows = session.execute_read(lambda tx: [record.data() for record in tx.run(query, ns=NAMESPACE, **params)])
        CARD_LOG.log_summary("CYPHER", label, params=CARD_LOG.sanitize(params), rows=len(rows),
                             path=STATEMENTS.get(statement_id, ("", "미등록"))[1],
                             elapsed_ms=(perf_counter() - started) * 1000)
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
