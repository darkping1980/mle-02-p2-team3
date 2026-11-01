"""Parameterized, read-only queries for the isolated A8 test graph."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from neo4j import READ_ACCESS

NAMESPACE = "ONE_PICK_STYLE_A8"
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "src" / "recipe"))
from recipe_recommender.neo4j_connection import create_neo4j_driver  # noqa: E402

LIST_QUERY = """
MATCH (c:A8Card {namespace:$ns})-[:A8_HAS_POLICY]->(p:A8Policy {namespace:$ns})
      -[:A8_HAS_BENEFIT]->(b:A8Benefit {namespace:$ns})
WHERE toLower(coalesce(b.name,'')) CONTAINS toLower($keyword)
RETURN b.key AS key, b.name AS name, b.card_bnft_id AS id,
       b.verification_status AS status ORDER BY b.name
"""
CONTEXT_QUERY = """
MATCH (c:A8Card {namespace:$ns})-[:A8_HAS_POLICY]->(p:A8Policy {namespace:$ns})
      -[:A8_HAS_BENEFIT]->(b:A8Benefit {namespace:$ns,key:$key})
RETURN properties(c) AS card, properties(p) AS policy, properties(b) AS benefit,
       labels(c) AS card_labels, labels(p) AS policy_labels, labels(b) AS benefit_labels
"""
RULE_QUERY = """
MATCH (b:A8Benefit {namespace:$ns,key:$key})-[:A8_HAS_RULE]->(r:A8Rule {namespace:$ns})
OPTIONAL MATCH (r)-[:A8_TARGETS]->(t:A8Target {namespace:$ns})
RETURN properties(r) AS rule, labels(r) AS labels, collect(DISTINCT t.target_nm) AS targets
ORDER BY rule.rule_key
"""
CONDITION_QUERY = """
MATCH (p:A8Policy {namespace:$ns})-[:A8_HAS_BENEFIT]->(b:A8Benefit {namespace:$ns,key:$key})
OPTIONAL MATCH (b)-[:A8_HAS_RULE]->(r:A8Rule {namespace:$ns})
WITH p,b,collect(DISTINCT r) AS rules
UNWIND [p,b] + rules AS owner
MATCH (owner)-[:A8_HAS_EXPR]->(x:A8Expression {namespace:$ns})
      -[:A8_HAS_BRANCH]->(branch:A8Branch {namespace:$ns})
      -[:A8_HAS_ATOM]->(a:A8Condition {namespace:$ns})
RETURN labels(owner) AS owner_labels, owner.rule_key AS rule_key,
       properties(x) AS expression, branch.branch_no AS branch_no,
       properties(a) AS atom, labels(a) AS labels
ORDER BY owner_labels, rule_key, branch_no, a.atom_seq
"""
LIMIT_QUERY = """
MATCH (b:A8Benefit {namespace:$ns,key:$key})-[:A8_HAS_RULE]->(r:A8Rule {namespace:$ns})
      -[:A8_CONSUMES]->(pool:A8LimitPool {namespace:$ns})
RETURN properties(pool) AS pool, labels(pool) AS labels,
       collect(DISTINCT r.rule_key) AS rule_keys ORDER BY pool.pool_id
"""
EVIDENCE_QUERY = """
MATCH (policy:A8Policy {namespace:$ns})-[:A8_HAS_BENEFIT]->(b:A8Benefit {namespace:$ns,key:$key})
OPTIONAL MATCH (b)-[:A8_HAS_RULE]->(:A8Rule)-[:A8_CONSUMES]->(pool:A8LimitPool {namespace:$ns})
WITH policy,b,collect(DISTINCT pool) AS pools
UNWIND [policy,b] + pools AS owner
MATCH (owner)-[link:A8_SUPPORTED_BY]->(e:A8Evidence {namespace:$ns})
      -[:A8_IN_CHUNK]->(chunk:A8Chunk {namespace:$ns})
      -[:A8_ON_PAGE]->(page:A8Page {namespace:$ns})
      -[:A8_IN_DOCUMENT]->(doc:A8Document {namespace:$ns})
RETURN labels(owner) AS owner_labels, owner.pool_id AS pool_id,
       properties(link) AS link, properties(e) AS evidence,
       properties(chunk) AS chunk, properties(page) AS page, properties(doc) AS document
ORDER BY page.page_no, e.start_pos, e.evidence_id
"""
QUERIES = {"목록": LIST_QUERY, "카드·정책": CONTEXT_QUERY, "규칙·대상": RULE_QUERY,
           "조건식": CONDITION_QUERY, "한도": LIMIT_QUERY, "근거": EVIDENCE_QUERY}


def source(props: dict) -> dict:
    """Decode the original JSON; never infer a missing value as approved."""
    value = props.get("source_json")
    return json.loads(value) if value else {}


class Neo4jSearch:
    def __init__(self, driver, database: str | None = None):
        self.driver = driver
        self.database = database

    def _query(self, query: str, **params) -> list[dict]:
        with self.driver.session(database=self.database, default_access_mode=READ_ACCESS) as session:
            return session.execute_read(lambda tx: [record.data() for record in tx.run(query, ns=NAMESPACE, **params)])

    def list_benefits(self, keyword: str = "") -> list[dict]:
        return self._query(LIST_QUERY, keyword=keyword.strip())

    def get_detail(self, key: str) -> dict | None:
        context = self._query(CONTEXT_QUERY, key=key)
        if not context:
            return None
        return {"context": context[0], "rules": self._query(RULE_QUERY, key=key),
                "conditions": self._query(CONDITION_QUERY, key=key),
                "limits": self._query(LIMIT_QUERY, key=key),
                "evidence": self._query(EVIDENCE_QUERY, key=key)}


def connect() -> Neo4jSearch:
    driver = create_neo4j_driver()  # project helper keeps certificate verification enabled
    return Neo4jSearch(driver, os.getenv("NEO4J_DATABASE") or None)
