"""PostgreSQL 원본과 Neo4j ``dp_`` 그래프를 읽기 전용으로 대조한다. 어떤 DB에도 쓰지 않는다.

[등록 파이프라인에서의 위치] 4단계 Neo4j 적재 후 검증. 적재(neo4j_load_draft.py) 다음에 실행한다.

처리 흐름 (``run``)
    1. PostgreSQL 스냅샷 → build → prepare (적재 때와 같은 변환을 다시 수행해 "기대 그래프"를 만든다)
    2. neo4j_validation.sql의 비교용 조회(COMPARED 4종)를 PostgresDbSession으로 실행
    3. Neo4j를 READ_ACCESS 세션으로 읽어 노드·관계 key/라벨/source_json, 범위 밖 건수, 고아 노드, 같은 비교 조회 결과 수집
    4. compare_graph + SQL·Cypher 결과 비교 → ``ok`` 판정. main은 ok가 아니면 종료 코드 1
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from common.neo4j_connection import create_neo4j_driver
from common.postgres_db_session import PostgresDbSession

from .neo4j_dry_run import build, load_snapshot
from .neo4j_load_draft import CYPHER, EXPECTED_DB, prepare, relationship_properties

MAPPER_ROOT = Path(__file__).resolve().parent
COMPARED = {
    "condition_structure": ("owner_cd", "card_id", "rule_key", "branch_no", "atom_seq", "atom_key", "cond_type_cd", "negate_yn",
                            "cond_min_amt", "cond_raw_txt"),
    "evidence_links": ("ev_link_id", "ev_subject_cd", "rule_key", "ev_item_cd", "ev_item_key", "evidence_id", "start_pos", "end_pos"),
    "common_applies": ("card_common_id", "card_common_bnft_id", "card_id"),
    "rule_targets": ("card_id", "card_bnft_id", "rule_key", "target_type_cd", "target_key", "target_nm"),
}


def _normalize(rows: list[dict], fields: tuple[str, ...]) -> list[tuple]:
    """DB별 표현 차이(Decimal, 정수)를 없애고 정렬해 비교한다."""
    def value(item):
        return float(item) if item is not None and not isinstance(item, (str, bool)) else item
    return sorted((tuple(value(row[field]) for field in fields) for row in rows), key=repr)


def compare_graph(nodes: list[dict], edges: list[dict], graph_nodes: list[dict], graph_edges: list[dict]) -> dict:
    """라벨 집합과 전체 속성, 관계 유형·끝점을 독립적으로 대조한다."""
    expected_nodes = {n["props"]["key"]: n for n in nodes}
    found_nodes = {n["key"]: n for n in graph_nodes}
    expected_edges = {e["key"]: e for e in edges}
    found_edges = {e["key"]: e for e in graph_edges}
    shared_nodes = set(expected_nodes) & set(found_nodes)
    shared_edges = set(expected_edges) & set(found_edges)

    def differences(key, expected, actual):
        return [{"key": key, "field": field, "expected_present": field in expected,
                 "actual_present": field in actual, "expected": expected.get(field), "actual": actual.get(field)}
                for field in sorted(set(expected) | set(actual))
                if field not in expected or field not in actual or expected[field] != actual[field]]

    node_labels, node_properties, edge_properties, edge_structure = [], [], [], []
    for k in sorted(shared_nodes):
        node = expected_nodes[k]
        labels = {"dp_node", node["label"]}
        if node["label"] == "dp_card_bnft":
            labels.add("dp_card_product_item")
        actual_labels = set(found_nodes[k]["labels"])
        if labels != actual_labels:
            node_labels.append({"key": k, "field": "labels", "expected": sorted(labels), "actual": sorted(actual_labels)})
        node_properties.extend(differences(k, node["props"], found_nodes[k]["props"]))
    for k in sorted(shared_edges):
        expected_edge, actual_edge = expected_edges[k], found_edges[k]
        edge_structure.extend(differences(k, {f: expected_edge[f] for f in ("type", "start", "end")},
                                          {f: actual_edge[f] for f in ("type", "start", "end")}))
        props = {"key": k, "source_json": expected_edge["source_json"], **relationship_properties(expected_edge)}
        edge_properties.extend(differences(k, props, actual_edge["props"]))
    return {
        "nodes_missing": sorted(set(expected_nodes) - set(found_nodes)),
        "nodes_extra": sorted(set(found_nodes) - set(expected_nodes)),
        "node_labels_changed": node_labels,
        "node_properties_changed": node_properties,
        "relationships_missing": sorted(set(expected_edges) - set(found_edges)),
        "relationships_extra": sorted(set(found_edges) - set(expected_edges)),
        "relationship_structure_changed": edge_structure,
        "relationship_properties_changed": edge_properties,
    }


def graph_ok(differences: int, outside: dict, orphans: list, *sql_equal: bool) -> bool:
    """dp_ 그래프만 판정한다. fp_ 건수는 ``other_graphs`` 로 보고하며 여기에 넣지 않는다."""
    return (differences == 0 and all(sql_equal) and not orphans
            and outside == {"outside_nodes": 0, "outside_relationships": 0})


def run() -> dict:
    """양쪽을 읽어 대조 결과를 만든다."""
    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as conn:
        snapshot = load_snapshot(conn)
    sql = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")
    try:
        sql_rows = {name: sql.select_list(f"neo4j_validation.{name}") for name in COMPARED}
    finally:
        sql.database_manager.close()
    graph, stats = build(snapshot)
    nodes, edges = prepare(graph)
    from neo4j import READ_ACCESS

    def read(session, name):
        return session.execute_read(lambda tx: [r.data() for r in tx.run(CYPHER[f"neo4j_validation.{name}"])])

    with create_neo4j_driver() as driver, driver.session(database=EXPECTED_DB, default_access_mode=READ_ACCESS) as session:
        result = compare_graph(nodes, edges, read(session, "node_sources"), read(session, "relationship_sources"))
        outside = read(session, "outside_scope_counts")[0]
        other_graphs = read(session, "other_graph_counts")[0]
        orphans = read(session, "orphan_nodes")
        cypher_rows = {name: read(session, name) for name in COMPARED}
        labels = read(session, "label_counts")
        relationships = read(session, "relationship_counts")
    equal = {name: _normalize(sql_rows[name], fields) == _normalize(cypher_rows[name], fields) for name, fields in COMPARED.items()}
    mismatch = sum(len(v) for v in result.values())
    return {"expected": {"nodes": stats["node_total"], "relationships": stats["relationship_total"]},
            "neo4j": {"nodes": sum(r["n"] for r in labels), "relationships": sum(r["n"] for r in relationships)},
            "label_counts": labels, "relationship_counts": relationships,
            "differences": {k: len(v) for k, v in result.items()}, "difference_keys": result,
            "outside_scope": outside, "other_graphs": other_graphs, "orphan_nodes": orphans,
            "sql_cypher": {name: [len(sql_rows[name]), len(cypher_rows[name]), equal[name]] for name in COMPARED},
            "ok": graph_ok(mismatch, outside, orphans, *equal.values())}


def main() -> None:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
