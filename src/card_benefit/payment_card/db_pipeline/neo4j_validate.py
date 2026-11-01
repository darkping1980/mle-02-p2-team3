"""PostgreSQL 원본과 Neo4j 시험 그래프를 읽기 전용으로 대조한다. 어떤 DB에도 쓰지 않는다."""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from common.neo4j_connection import create_neo4j_driver
from common.postgres_db_session import PostgresDbSession

from .neo4j_dry_run import NS, build, load_snapshot
from .neo4j_load_draft import CYPHER, EXPECTED_DB, prepare

MAPPER_ROOT = Path(__file__).resolve().parent


def _normalize(rows: list[dict], fields: tuple[str, ...]) -> list[tuple]:
    """DB별 표현 차이(Decimal, 정수)를 없애고 정렬해 비교한다."""
    def value(item):
        return float(item) if item is not None and not isinstance(item, (str, bool)) else item
    return sorted((tuple(value(row[field]) for field in fields) for row in rows), key=repr)


def compare_graph(nodes: list[dict], edges: list[dict], graph_nodes: list[dict], graph_edges: list[dict]) -> dict:
    """변환 결과와 Neo4j의 키, 라벨, 원본 JSON, 관계 유형, 끝점을 대조한다."""
    expected_nodes = {n["props"]["key"]: n for n in nodes}
    found_nodes = {n["key"]: n for n in graph_nodes}
    expected_edges = {e["key"]: e for e in edges}
    found_edges = {e["key"]: e for e in graph_edges}
    shared_nodes = set(expected_nodes) & set(found_nodes)
    shared_edges = set(expected_edges) & set(found_edges)
    return {
        "nodes_missing": sorted(set(expected_nodes) - set(found_nodes)),
        "nodes_extra": sorted(set(found_nodes) - set(expected_nodes)),
        "nodes_changed": sorted(k for k in shared_nodes if found_nodes[k]["source_json"] != expected_nodes[k]["props"]["source_json"]
                                or found_nodes[k]["label"] != expected_nodes[k]["label"]),
        "relationships_missing": sorted(set(expected_edges) - set(found_edges)),
        "relationships_extra": sorted(set(found_edges) - set(expected_edges)),
        "relationships_changed": sorted(k for k in shared_edges if any(
            found_edges[k][field] != expected_edges[k][field] for field in ("type", "start", "end", "source_json"))),
    }


def graph_ok(differences: int, outside: dict, orphans: list, conditions_equal: bool, links_equal: bool) -> bool:
    """DF 그래프만 판정한다. A8 공존과 PF 적재는 ``other_graphs`` 로 보고하며 여기에 넣지 않는다."""
    return (differences == 0 and conditions_equal and links_equal and not orphans
            and outside == {"outside_nodes": 0, "outside_relationships": 0})


def run() -> dict:
    """양쪽을 읽어 대조 결과를 만든다."""
    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as conn:
        snapshot = load_snapshot(conn)
    sql = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")
    try:
        sql_conditions = sql.select_list("neo4j_validation.condition_structure")
        sql_links = sql.select_list("neo4j_validation.evidence_links")
    finally:
        sql.database_manager.close()
    graph, stats = build(snapshot)
    nodes, edges = prepare(graph)
    from neo4j import READ_ACCESS

    def read(session, name):
        return session.execute_read(lambda tx: [r.data() for r in tx.run(CYPHER[f"neo4j_validation.{name}"], ns=NS)])

    with create_neo4j_driver() as driver, driver.session(database=EXPECTED_DB, default_access_mode=READ_ACCESS) as session:
        result = compare_graph(nodes, edges, read(session, "node_sources"), read(session, "relationship_sources"))
        outside = read(session, "outside_scope_counts")[0]
        other_graphs = read(session, "other_graph_counts")[0]
        orphans = read(session, "orphan_nodes")
        cypher_conditions = read(session, "condition_structure")
        cypher_links = read(session, "evidence_links")
        labels = read(session, "label_counts")
        relationships = read(session, "relationship_counts")
    condition_fields = ("owner_cd", "rule_key", "branch_no", "atom_seq", "atom_key", "cond_type_cd", "negate_yn", "cond_min_amt", "cond_raw_txt")
    link_fields = ("ev_link_id", "ev_subject_cd", "rule_key", "pool_id", "ev_item_cd", "ev_item_key", "evidence_id", "start_pos", "end_pos")
    mismatch = sum(len(v) for v in result.values())
    conditions_equal = _normalize(sql_conditions, condition_fields) == _normalize(cypher_conditions, condition_fields)
    links_equal = _normalize(sql_links, link_fields) == _normalize(cypher_links, link_fields)
    return {"expected": {"nodes": stats["node_total"], "relationships": stats["relationship_total"]},
            "neo4j": {"nodes": sum(r["n"] for r in labels), "relationships": sum(r["n"] for r in relationships)},
            "relationship_counts": relationships, "differences": {k: len(v) for k, v in result.items()}, "difference_keys": result,
            "outside_scope": outside, "other_graphs": other_graphs, "orphan_nodes": orphans,
            "sql_cypher": {"conditions": [len(sql_conditions), len(cypher_conditions), conditions_equal],
                           "evidence_links": [len(sql_links), len(cypher_links), links_equal]},
            "ok": graph_ok(mismatch, outside, orphans, conditions_equal, links_equal)}


def main() -> None:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
