"""PostgreSQL에서 만든 ``dp_`` 그래프를 지정 Neo4j DB에 적재한다. ``--apply`` 와 확인 문구 없이는 쓰지 않는다.

MERGE만 쓰므로 재실행해도 중복되지 않는다. 노드·관계 삭제 구문이 없고 ``dp_`` 밖의 데이터는 건드리지 않는다.
스키마 변경은 ``dp_`` 제약 생성뿐이다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from common.neo4j_connection import create_neo4j_driver
from common.neo4j_db_session import Neo4jDbSession

from .neo4j_dry_run import COMMON_LABEL, PK_FIELDS, PREFIX, build, load_snapshot

EXPECTED_DB = "6ac1f0f8"
# 정적 조회는 neo4j_validation.cypher에 있다. 아래 MERGE는 라벨·관계 유형이 동적이라 파일로 옮기지 않는다.
CYPHER = Neo4jDbSession(mapper_root=Path(__file__).resolve().parent).mappers
CONFIRM = "APPROVED_DP_HANA_CARD"
NODE_LABELS = frozenset(PREFIX + label for label in PK_FIELDS)
REL_TYPES = frozenset(PREFIX + kind for kind in (
    "has_document", "has_benefit", "has_rule", "has_expr", "has_branch", "has_atom", "targets", "supported_by",
    "in_chunk", "on_page", "in_document", "has_common_benefit", "belongs_to", "same_as"))
# 쓰기 구문이므로 읽기 전용 neo4j_validation.cypher에 두지 않는다. --apply에서만 실행한다.
CREATE_CONSTRAINTS = (
    f"CREATE CONSTRAINT dp_node_key IF NOT EXISTS FOR (n:{COMMON_LABEL}) REQUIRE n.key IS UNIQUE",
    *(f"CREATE CONSTRAINT {PREFIX}{label}_pk IF NOT EXISTS FOR (n:{PREFIX}{label}) "
      f"REQUIRE ({', '.join('n.' + field for field in fields)}) IS NODE KEY"
      for label, fields in PK_FIELDS.items()),
)
SCALAR_FIELDS = ("card_id", "card_bnft_id", "rule_key", "value_num", "bnft_cd", "bnft_type_cd", "product_cd", "product_nm",
                 "card_kind_cd", "card_common_id", "card_common_bnft_id", "common_cd", "common_nm", "brand_cd",
                 "service_grade_cd", "service_type_cd", "card_doc_id", "doc_title", "doc_type_cd", "card_doc_chunk_id",
                 "branch_no", "atom_seq", "evidence_id", "page_no", "start_pos", "end_pos", "target_nm", "target_key",
                 "target_type_cd", "excl_raw_txt", "bnft_valid_from", "bnft_valid_to_excl")
ALIASES = {"bnft_nm": "name", "verification_status_cd": "verification_status", "bnft_rule_txt": "rule_text",
           "bnft_limit_txt": "limit_text", "atom_key": "key_name", "cond_type_cd": "kind", "cond_raw_txt": "raw_text",
           "negate_yn": "negate", "cond_min_amt": "min_amt", "approval_status_cd": "approval_status",
           "card_cond_status_cd": "card_cond_status"}


def node_properties(node):
    """PK와 조회용 스칼라를 속성으로 올린다. NULL은 ``source_json`` 에만 남는다."""
    row = json.loads(node["source_json"])
    props = {"key": node["key"], "source_json": node["source_json"], **node.get("pk", {})}
    for name in SCALAR_FIELDS:
        value = row.get(name)
        if isinstance(value, (str, int, float, bool)):
            props[name] = value
    for src, dest in ALIASES.items():
        value = row.get(src)
        if isinstance(value, (str, int, float, bool)):
            props[dest] = value
    return props


def prepare(graph):
    """적재 형식으로 바꾼다. 허용 목록 밖의 라벨·유형은 거부한다."""
    graph.validate()
    nodes, relationships = [], []
    for n in graph.nodes.values():
        if n["label"] not in NODE_LABELS:
            raise ValueError("unexpected node scope")
        nodes.append({"label": n["label"], "pk": n["pk"], "props": node_properties(n)})
    for k, e in graph.edges.items():
        if e["type"] not in REL_TYPES:
            raise ValueError("unexpected relationship scope")
        relationships.append({"type": e["type"], "start": e["start"], "end": e["end"],
                              "key": hashlib.sha256(k.encode("utf-8")).hexdigest(), "source_json": e["source_json"]})
    return nodes, relationships


def write_transaction(tx, nodes, relationships):
    """전용 라벨과 PK로만 MERGE한다. 값은 파라미터로 전달한다."""
    for n in nodes:
        label = n["label"]  # prepare에서 허용 목록으로 확인했다.
        match = ", ".join(f"{field}: $pk.{field}" for field in n["pk"])
        result = tx.run(f"MERGE (n:{label} {{{match}}}) SET n:{COMMON_LABEL}, n += $props RETURN count(n) AS n",
                        pk=n["pk"], props=n["props"]).single(strict=True)
        if result["n"] != 1:
            raise ValueError("node creation mismatch")
    for e in relationships:
        kind = e["type"]  # prepare에서 허용 목록으로 확인했다.
        original = json.loads(e["source_json"])
        extra = {k: v for k, v in original.items()
                 if k in ("ev_link_id", "ev_subject_cd", "ev_item_cd", "ev_item_key", "atom_seq", "doc_role_cd",
                          "approval_status_cd", "status", "bnft_cd") and isinstance(v, (str, int, float, bool))}
        result = tx.run(f"MATCH (a:{COMMON_LABEL} {{key:$start}}), (b:{COMMON_LABEL} {{key:$end}}) "
                        f"MERGE (a)-[r:{kind} {{key:$key}}]->(b) SET r.source_json=$source_json, r += $extra RETURN count(r) AS n",
                        extra=extra, **{k: e[k] for k in ("start", "end", "key", "source_json")}).single(strict=True)
        if result["n"] != 1:
            raise ValueError("relationship endpoint mismatch")
    found_nodes = [r["key"] for r in tx.run(CYPHER["neo4j_validation.node_keys"])]
    found_edges = [r["key"] for r in tx.run(CYPHER["neo4j_validation.relationship_keys"])]
    if len(found_nodes) != len(nodes) or set(found_nodes) != {n["props"]["key"] for n in nodes}:
        raise ValueError("node postcondition mismatch")
    if len(found_edges) != len(relationships) or set(found_edges) != {e["key"] for e in relationships}:
        raise ValueError("relationship postcondition mismatch")
    return len(nodes), len(relationships)


def prepare_schema(session) -> dict:
    """dp_ 제약을 만든다. 다른 프로젝트의 제약은 바꾸지 않는다."""
    for statement in CREATE_CONSTRAINTS:
        session.run(statement).consume()
    names = {row["name"] for row in session.run(CYPHER["neo4j_validation.card_constraints"])}
    wanted = {"dp_node_key", *(f"{PREFIX}{label}_pk" for label in PK_FIELDS)}
    if not wanted <= names:
        raise SystemExit(f"dp_ 제약이 없습니다: {sorted(wanted - names)}")
    return {"dp_constraints": len(wanted)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()
    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as c:
        graph, stats = build(load_snapshot(c))
    nodes, edges = prepare(graph)
    print(json.dumps({"mode": "APPLY" if args.apply else "PREVIEW", "nodes": len(nodes), "relationships": len(edges),
                      "target_database": EXPECTED_DB, "by_label": stats["nodes"], "by_type": stats["relationships"],
                      "isolated_nodes": stats["isolated_nodes"], "unlinked_evidence": stats["unlinked_evidence"],
                      "brand_compare": stats["brand_compare"]}, ensure_ascii=False))
    if not args.apply:
        return
    if args.confirm != CONFIRM or os.getenv("NEO4J_DATABASE") != EXPECTED_DB:
        raise SystemExit("explicit approval confirmation and exact target database required")
    # Reuse verified project TLS implementation; no certificate verification bypass.
    with create_neo4j_driver() as driver, driver.session(database=EXPECTED_DB) as session:
        print("schema", prepare_schema(session))
        existing = set(session.run(CYPHER["neo4j_validation.existing_node_keys"]).single(strict=True)["keys"])
        stale = existing - {n["props"]["key"] for n in nodes}
        if stale:
            raise SystemExit(f"원천에 없는 dp_ 노드가 있어 적재를 중단합니다. 자동 삭제하지 않습니다: {sorted(stale)[:5]}")
        print("committed", session.execute_write(write_transaction, nodes, edges))


if __name__ == "__main__":
    main()
