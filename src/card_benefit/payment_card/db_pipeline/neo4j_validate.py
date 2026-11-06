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

from .neo4j_dry_run import build, canonical, column_coverage, load_snapshot
from .neo4j_load_draft import CYPHER, EXPECTED_DB, prepare, relationship_properties

MAPPER_ROOT = Path(__file__).resolve().parent
COMPARED = {
    "condition_structure": ("owner_cd", "card_id", "rule_key", "branch_no", "atom_seq", "atom_key", "cond_type_cd", "negate_yn",
                            "cond_min_amt", "cond_raw_txt"),
    "evidence_links": ("ev_link_id", "ev_subject_cd", "rule_key", "ev_item_cd", "ev_item_key", "evidence_id", "start_pos", "end_pos"),
    "common_evidence_links": ("card_common_id", "card_common_bnft_id", "evidence_id", "ev_subject_cd", "ev_item_key"),
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


def source_column_map(rows: list[dict]) -> dict[str, list[str]]:
    """information_schema 행 → 테이블별 컬럼 목록(원래 순서)."""
    out: dict[str, list[str]] = {}
    for row in rows:
        out.setdefault(row["table_name"], []).append(row["column_name"])
    return out


def compare_item_data(pg_rows: list[dict], graph_rows: list[dict]) -> list[dict]:
    """혜택별 item_data를 PostgreSQL(직접 조회)과 Neo4j source_json에서 대조한다(2026-11-06 P2).

    스냅샷 함수를 거치지 않으므로 load_snapshot SELECT에서 item_data가 빠져도 차이로 나온다.
    Neo4j에 item_data 키가 없으면(has_item_data=false) PostgreSQL 값이 {}여도 차이다(NULL·빈 값과 키 없음을 구분).
    """
    def key(row):
        return int(row["card_id"]), str(row["card_bnft_id"])

    def value(item):
        return canonical(json.loads(item) if isinstance(item, str) else item)
    graph = {key(row): row for row in graph_rows}
    problems = []
    for row in pg_rows:
        found = graph.get(key(row))
        expected = value(row["item_data"])
        if found is None:
            problems.append({"key": key(row), "problem": "Neo4j 혜택 노드 없음"})
        elif not found.get("has_item_data"):
            problems.append({"key": key(row), "problem": "Neo4j source_json에 item_data 키 없음", "expected": expected})
        elif value(found.get("item_data")) != expected:
            problems.append({"key": key(row), "problem": "item_data 값 다름", "expected": expected,
                             "actual": value(found.get("item_data"))})
    extra = set(graph) - {key(row) for row in pg_rows}
    problems.extend({"key": k, "problem": "PostgreSQL에 없는 Neo4j 혜택"} for k in sorted(extra))
    return problems


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
        source_columns = source_column_map(sql.select_list("neo4j_validation.source_columns"))
        pg_item_data = sql.select_list("neo4j_validation.benefit_item_data")
    finally:
        sql.database_manager.close()
    # 스냅샷 SELECT와 독립된 원천 컬럼 목록으로 분류 누락을 검사한다(2026-11-06 P2).
    coverage = column_coverage(source_columns, snapshot)
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
        graph_item_data = read(session, "benefit_item_data")
    equal = {name: _normalize(sql_rows[name], fields) == _normalize(cypher_rows[name], fields) for name, fields in COMPARED.items()}
    mismatch = sum(len(v) for v in result.values())
    item_data = compare_item_data(pg_item_data, graph_item_data)
    return {"expected": {"nodes": stats["node_total"], "relationships": stats["relationship_total"]},
            "neo4j": {"nodes": sum(r["n"] for r in labels), "relationships": sum(r["n"] for r in relationships)},
            "label_counts": labels, "relationship_counts": relationships,
            "differences": {k: len(v) for k, v in result.items()}, "difference_keys": result,
            "outside_scope": outside, "other_graphs": other_graphs, "orphan_nodes": orphans,
            "sql_cypher": {name: [len(sql_rows[name]), len(cypher_rows[name]), equal[name]] for name in COMPARED},
            "column_coverage": coverage, "item_data_mismatch": {"count": len(item_data), "items": item_data[:20]},
            "ok": graph_ok(mismatch, outside, orphans, *equal.values()) and not coverage and not item_data}


def main() -> None:
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
