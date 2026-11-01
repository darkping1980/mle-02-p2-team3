"""Explicitly guarded A8 card-only loader. Never run --apply without approval."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from src.common.neo4j_db_session import Neo4jDbSession

from .neo4j_dry_run import NS, build, canonical, load_snapshot

EXPECTED_DB = "6ac1f0f8"
# 정적 조회는 neo4j_validation.cypher에 있다. 아래 MERGE는 라벨·관계 유형이 동적이라 파일로 옮기지 않는다.
CYPHER = Neo4jDbSession(mapper_root=Path(__file__).resolve().parent).mappers
CONFIRM = "APPROVED_ONE_PICK_STYLE_A8"
NODE_LABELS = frozenset("A8Card A8Policy A8Benefit A8Rule A8Expression A8Branch A8Condition A8Target A8LimitPool A8Evidence A8Chunk A8Page A8Document".split())
REL_TYPES = frozenset("A8_HAS_POLICY A8_HAS_BENEFIT A8_HAS_RULE A8_HAS_EXPR A8_HAS_BRANCH A8_HAS_ATOM A8_TARGETS A8_CONSUMES A8_SUPPORTED_BY A8_IN_CHUNK A8_ON_PAGE A8_IN_DOCUMENT".split())
# A10-3 기준 원본 건수. 원본이 바뀌면 검토 후 함께 수정한다(168 + 규칙 근거 11 + 조건 근거 10).
EXPECTED_NODES = 108
EXPECTED_RELATIONSHIPS = 189


def node_properties(node):
    raw = json.loads(node["source_json"])
    row = raw.get("source", raw)
    props = {"namespace": NS, "key": node["key"], "source_json": node["source_json"], "test_only": True}
    # Queryable scalar columns, leaving NULL represented in source_json.
    aliases = {"bnft_nm": "name", "verification_status_cd": "verification_status",
               "period_cd": "period", "cap_unit_cd": "unit", "atom_key": "key_name",
               "cond_type_cd": "kind", "cond_raw_txt": "raw_text", "negate_yn": "negate",
               "cond_min_amt": "min_amt", "approval_status_cd": "approval_status"}
    for name in ("card_id", "policy_ver_id", "card_bnft_id", "rule_key", "value_num", "pool_id",
                 "branch_no", "atom_seq", "evidence_id", "page_no", "start_pos", "end_pos", "target_nm"):
        value = row.get(name)
        if isinstance(value, (str, int, float, bool)):
            props[name] = value
    for src, dest in aliases.items():
        value = row.get(src)
        if isinstance(value, (str, int, float, bool)):
            props[dest] = value
    if raw.get("valid_from_is_assumption"):
        props["valid_from_is_assumption"] = True
    if raw.get("aggregation_is_assumption"):
        props["aggregation_is_assumption"] = True
    if node["label"] == "A8LimitPool" and row.get("tier_list"):
        props["value"] = row["tier_list"][0].get("limit_num")
    return props


def prepare(graph):
    graph.validate()
    nodes, relationships = [], []
    for n in graph.nodes.values():
        if n["label"] not in NODE_LABELS or n["namespace"] != NS:
            raise ValueError("unexpected node scope")
        nodes.append({"label": n["label"], "props": node_properties(n)})
    for k, e in graph.edges.items():
        if e["type"] not in REL_TYPES or e["namespace"] != NS:
            raise ValueError("unexpected relationship scope")
        relationships.append({"type": e["type"], "start": e["start"], "end": e["end"],
                              "key": hashlib.sha256(k.encode("utf-8")).hexdigest(),
                              "source_json": e["source_json"]})
    if len(nodes) != EXPECTED_NODES or len(relationships) != EXPECTED_RELATIONSHIPS:
        raise ValueError("unexpected source counts; re-review snapshot")
    return nodes, relationships


def write_transaction(tx, nodes, relationships):
    # Dedicated label and namespace only. No delete, no schema change.
    for n in nodes:
        label = n["label"]  # verified against constant allowlist in prepare
        result = tx.run(f"MERGE (n:A8Test:{label} {{namespace:$namespace,key:$key}}) SET n += $props RETURN count(n) AS n",
                        namespace=NS, key=n["props"]["key"], props=n["props"]).single(strict=True)
        if result["n"] != 1:
            raise ValueError("node creation mismatch")
    for e in relationships:
        kind = e["type"]  # verified against constant allowlist in prepare
        original = json.loads(e["source_json"])
        extra = {k: v for k, v in original.items()
                 if k in ("ev_link_id", "ev_subject_cd", "ev_item_cd", "ev_item_key", "atom_seq")
                 and isinstance(v, (str, int, float, bool))}
        result = tx.run(f"MATCH (a:A8Test {{namespace:$namespace,key:$start}}), (b:A8Test {{namespace:$namespace,key:$end}}) "
                        f"MERGE (a)-[r:{kind} {{namespace:$namespace,key:$key}}]->(b) "
                        "SET r.source_json=$source_json, r += $extra RETURN count(r) AS n", namespace=NS, extra=extra, **{k: e[k] for k in ("start", "end", "key", "source_json")}).single(strict=True)
        if result["n"] != 1:
            raise ValueError("relationship endpoint mismatch")
    found_nodes = [r["key"] for r in tx.run(CYPHER["neo4j_validation.node_keys"], ns=NS)]
    found_edges = [r["key"] for r in tx.run(CYPHER["neo4j_validation.relationship_keys"], ns=NS)]
    if len(found_nodes) != len(nodes) or set(found_nodes) != {n["props"]["key"] for n in nodes}:
        raise ValueError("node postcondition mismatch")
    if len(found_edges) != len(relationships) or set(found_edges) != {e["key"] for e in relationships}:
        raise ValueError("relationship postcondition mismatch")
    return len(nodes), len(relationships)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()
    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as c:
        graph, stats = build(load_snapshot(c))
    nodes, edges = prepare(graph)
    print(json.dumps({"mode": "APPLY" if args.apply else "PREVIEW", "nodes": len(nodes), "relationships": len(edges), "target_database": EXPECTED_DB}))
    if not args.apply:
        return
    if args.confirm != CONFIRM or os.getenv("NEO4J_DATABASE") != EXPECTED_DB:
        raise SystemExit("explicit approval confirmation and exact target database required")
    # Reuse verified project TLS implementation; no certificate verification bypass.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "recipe"))
    from recipe_recommender.neo4j_connection import create_neo4j_driver
    with create_neo4j_driver() as driver, driver.session(database=EXPECTED_DB) as session:
        constraints = list(session.run(CYPHER["neo4j_validation.card_constraints"]))
        if not any(x["type"] == "NODE_PROPERTY_UNIQUENESS" and x["labelsOrTypes"] == ["A8Test"] and x["properties"] == ["namespace", "key"] for x in constraints):
            raise SystemExit("required A8Test(namespace,key) uniqueness constraint absent")
        existing = session.run(CYPHER["neo4j_validation.existing_node_keys"], ns=NS).single(strict=True)["keys"]
        if existing and (len(existing) != len(nodes) or set(existing) != {n["props"]["key"] for n in nodes}):
            raise SystemExit("namespace differs from snapshot; refuse implicit deletion")
        print("committed", session.execute_write(write_transaction, nodes, edges))


if __name__ == "__main__":
    main()
