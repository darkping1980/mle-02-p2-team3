"""Neo4j 단일 검색용 투영(임베딩·검색 텍스트·동일성 판정 상태·공통 혜택 PDF 근거)을 PostgreSQL 원장 기준으로 동기화한다.

기본 실행은 읽기 전용 사전 검증(preview)이다. ``--apply`` 는 확인 문구와 승인 건수가 맞을 때만 쓴다.
``--create-indexes`` 는 데이터와 별도의 스키마 단계다(Neo4j는 스키마·데이터 변경을 한 트랜잭션에 섞을 수 없다).

기준 그래프는 ``neo4j_dry_run.build`` → ``neo4j_load_draft.prepare`` 결과 하나다(적재기·검증기와 같은 정의).
허용하는 변경만 반영하고, 그 밖의 차이(기존 노드·관계·속성)가 하나라도 있으면 쓰지 않고 중단한다.
    - 새 노드: 공통 혜택 근거에서만 쓰이는 ``dp_card_source_evidence`` 와 그 ``dp_in_chunk``
    - 관계: 공통 혜택 근거 ``dp_supported_by {link_source:'COMMON_STG'}`` 생성·속성 갱신·원장에서 사라진 것 삭제
    - 속성: ``dp_card_bnft``·``dp_card_common_bnft`` 의 PROJECTION_PROPS 설정·갱신·제거
적용 후 기준 그래프와 Neo4j의 차이가 0이어야 commit한다(compare_graph 전체 대조).
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter

from .neo4j_dry_run import COMMON_LABEL, COMMON_LINK_SOURCE, EMBEDDING_DIM, PREFIX, PROJECTION_PROPS

CONFIRM = "APPROVED_DP_SEARCH_PROJECTION_SYNC"
INDEX_CONFIRM = "APPROVED_DP_SEARCH_INDEXES"
EVIDENCE_LABEL = PREFIX + "card_source_evidence"
PROJECTION_LABELS = (PREFIX + "card_bnft", PREFIX + "card_common_bnft")
SUPPORTED_BY, IN_CHUNK = PREFIX + "supported_by", PREFIX + "in_chunk"

# 쓰기 구문은 모두 dp_ 투영 범위만 다룬다. 첫 줄 주석은 테스트의 가짜 트랜잭션이 구문을 구분하는 이름이다.
CREATE_EVIDENCE = f"""// projection:create_evidence
UNWIND $rows AS row
MERGE (n:{EVIDENCE_LABEL} {{evidence_id: row.pk.evidence_id}})
SET n:{COMMON_LABEL}, n += row.props RETURN count(n) AS n"""
MERGE_EDGES = {kind: f"""// projection:merge_{kind[3:]}
UNWIND $rows AS row
MATCH (a:{COMMON_LABEL} {{key: row.start}}), (b:{COMMON_LABEL} {{key: row.end}})
MERGE (a)-[r:{kind} {{key: row.key}}]->(b)
SET r.source_json = row.source_json, r += row.extra RETURN count(r) AS n""" for kind in (SUPPORTED_BY, IN_CHUNK)}
UPDATE_LINKS = f"""// projection:update_links
UNWIND $rows AS row
MATCH (:{COMMON_LABEL})-[r:{SUPPORTED_BY} {{key: row.key}}]->(:{EVIDENCE_LABEL})
WHERE r.link_source = '{COMMON_LINK_SOURCE}'
SET r = row.props RETURN count(r) AS n"""
DELETE_LINKS = f"""// projection:delete_links
MATCH (:{COMMON_LABEL})-[r:{SUPPORTED_BY}]->(:{EVIDENCE_LABEL})
WHERE r.key IN $keys AND r.link_source = '{COMMON_LINK_SOURCE}'
DELETE r RETURN count(*) AS n"""
DELETE_EVIDENCE = f"""// projection:delete_evidence
MATCH (n:{EVIDENCE_LABEL})
WHERE n.key IN $keys AND NOT ()-[:{SUPPORTED_BY}]->(n)
DETACH DELETE n RETURN count(*) AS n"""
SET_PROPS = f"""// projection:set_props
UNWIND $rows AS row
MATCH (n:{COMMON_LABEL} {{key: row.key}})
WHERE n:{PROJECTION_LABELS[0]} OR n:{PROJECTION_LABELS[1]}
SET n += row.props RETURN count(n) AS n"""
WRITE_STATEMENTS = (CREATE_EVIDENCE, *MERGE_EDGES.values(), UPDATE_LINKS, DELETE_LINKS, DELETE_EVIDENCE, SET_PROPS)

VECTOR_INDEXES = {f"{label}_embedding": label for label in PROJECTION_LABELS}
INDEX_STATEMENTS = tuple(
    f"CREATE VECTOR INDEX {name} IF NOT EXISTS FOR (n:{label}) ON n.embedding "
    f"OPTIONS {{indexConfig: {{`vector.dimensions`: {EMBEDDING_DIM}, `vector.similarity_function`: 'cosine'}}}}"
    for name, label in VECTOR_INDEXES.items())


class ProjectionSyncError(ValueError):
    """허용 범위 밖의 차이 또는 사후 검증 실패. 쓰지 않거나 rollback한다."""


AUDIT_ONLY_LABEL = PREFIX + "card_common_bnft"
AUDIT_ONLY_FIELDS = frozenset({"update_date"})


def audit_only_change(actual: str | None, expected: str | None) -> bool:
    """두 source_json이 같은 키 구조이고 update_date만 다른지(2026-11-05 승인: 임베딩 저장이 바꾼 감사 시각만 반영).

    업무 속성·JSON 구조(키 추가·삭제)가 하나라도 다르면 False다.
    """
    try:
        a, e = json.loads(actual), json.loads(expected)
    except (TypeError, ValueError):
        return False
    if not isinstance(a, dict) or not isinstance(e, dict) or set(a) != set(e):
        return False
    changed = {k for k in e if a[k] != e[k]}
    return bool(changed) and changed <= AUDIT_ONLY_FIELDS


def is_projection_edge(edge: dict) -> bool:
    """기준 관계(source_json) 또는 Neo4j 관계(props)가 공통 혜택 근거 투영인지."""
    if edge.get("type") != SUPPORTED_BY:
        return False
    props = edge.get("props")
    if props is not None:
        return props.get("link_source") == COMMON_LINK_SOURCE
    return json.loads(edge["source_json"]).get("link_source") == COMMON_LINK_SOURCE


# region 1. 계획 (순수 함수)
def plan(nodes: list[dict], edges: list[dict], found_nodes: list[dict], found_edges: list[dict]) -> dict:
    """기준 그래프와 Neo4j 차이를 허용 변경과 차단 항목으로 나눈다."""
    from .neo4j_load_draft import relationship_properties
    from .neo4j_validate import compare_graph

    diff = compare_graph(nodes, edges, found_nodes, found_edges)
    expected_nodes = {n["props"]["key"]: n for n in nodes}
    expected_edges = {e["key"]: e for e in edges}
    found_node_map = {n["key"]: n for n in found_nodes}
    found_edge_map = {e["key"]: e for e in found_edges}
    incoming = {}
    for e in edges:
        if e["type"] == SUPPORTED_BY:
            incoming.setdefault(e["end"], []).append(e)
    blocked: list[tuple] = []
    p = {"create_evidence": [], "create_edges": [], "update_links": [], "delete_links": [], "delete_evidence": [],
         "set_props": {}, "blocked": blocked}

    for k in diff["nodes_missing"]:
        node = expected_nodes[k]
        if node["label"] == EVIDENCE_LABEL and incoming.get(k) and all(is_projection_edge(e) for e in incoming[k]):
            p["create_evidence"].append(node)
        else:
            blocked.append(("node_missing", k))
    created = {n["props"]["key"] for n in p["create_evidence"]}
    for k in diff["relationships_missing"]:
        e = expected_edges[k]
        if is_projection_edge(e) or (e["type"] == IN_CHUNK and e["start"] in created):
            p["create_edges"].append(e)
        else:
            blocked.append(("relationship_missing", k))
    deleted_links, deferred_chunks = set(), []
    for k in diff["relationships_extra"]:
        e = found_edge_map[k]
        if is_projection_edge(e):
            p["delete_links"].append(k); deleted_links.add(k)
        elif e["type"] == IN_CHUNK:
            deferred_chunks.append(e)           # 지울 근거 노드의 in_chunk인지 노드 판정 뒤에 본다
        else:
            blocked.append(("relationship_extra", k))
    for k in diff["nodes_extra"]:
        node = found_node_map[k]
        touching = [e for e in found_edges if k in (e["start"], e["end"])]
        if (EVIDENCE_LABEL in node["labels"] and touching
                and all((e["type"] == IN_CHUNK and e["start"] == k) or e["key"] in deleted_links for e in touching)):
            p["delete_evidence"].append(k)      # DETACH DELETE가 그 노드의 in_chunk를 함께 지운다
        else:
            blocked.append(("node_extra", k))
    for e in deferred_chunks:
        if e["start"] not in p["delete_evidence"]:
            blocked.append(("relationship_extra", e["key"]))
    for item in diff["node_properties_changed"]:
        node = expected_nodes.get(item["key"])
        if node is not None and node["label"] in PROJECTION_LABELS and item["field"] in PROJECTION_PROPS:
            p["set_props"].setdefault(item["key"], {})[item["field"]] = item["expected"] if item["expected_present"] else None
        elif (node is not None and node["label"] == AUDIT_ONLY_LABEL and item["field"] == "source_json"
              and item["expected_present"] and item["actual_present"] and audit_only_change(item["actual"], item["expected"])):
            p["set_props"].setdefault(item["key"], {})["source_json"] = item["expected"]
        else:
            blocked.append(("node_property", item["key"], item["field"]))
    for item in diff["relationship_properties_changed"]:
        e = expected_edges[item["key"]]
        if is_projection_edge(e) and is_projection_edge(found_edge_map[item["key"]]):
            if item["key"] not in {x["key"] for x in p["update_links"]}:
                p["update_links"].append({"key": item["key"], "props": {"key": e["key"], "source_json": e["source_json"],
                                                                       **relationship_properties(e)}})
        else:
            blocked.append(("relationship_property", item["key"], item["field"]))
    for item in diff["node_labels_changed"]:
        blocked.append(("node_labels", item["key"]))
    for item in diff["relationship_structure_changed"]:
        blocked.append(("relationship_structure", item["key"], item["field"]))
    return p


def plan_counts(p: dict) -> dict:
    """승인·대조용 건수. 속성은 (라벨 무관) 필드별 설정·제거 건수다."""
    fields = Counter()
    for props in p["set_props"].values():
        for field, value in props.items():
            fields[f"{'remove' if value is None else 'set'}:{field}"] += 1
    return {"create_evidence": len(p["create_evidence"]),
            "create_edges": dict(sorted(Counter(e["type"] for e in p["create_edges"]).items())),
            "update_links": len(p["update_links"]), "delete_links": len(p["delete_links"]),
            "delete_evidence": len(p["delete_evidence"]), "set_prop_nodes": len(p["set_props"]),
            "set_props": dict(sorted(fields.items())), "blocked": len(p["blocked"])}


def simulate(p: dict, found_nodes: list[dict], found_edges: list[dict]) -> tuple[list[dict], list[dict]]:
    """계획을 메모리 사본에 적용한다(dry-run 검증용). 쓰기 구문과 같은 의미로 만든다."""
    from .neo4j_load_draft import relationship_properties

    nodes = {n["key"]: {"key": n["key"], "labels": list(n["labels"]), "props": dict(n["props"])} for n in found_nodes}
    edges = {e["key"]: {**e, "props": dict(e["props"])} for e in found_edges}
    for k in p["delete_links"]:
        edges.pop(k)
    for k in p["delete_evidence"]:
        nodes.pop(k)
        for ek in [ek for ek, e in edges.items() if k in (e["start"], e["end"])]:
            edges.pop(ek)
    for n in p["create_evidence"]:
        nodes[n["props"]["key"]] = {"key": n["props"]["key"], "labels": [COMMON_LABEL, n["label"]], "props": dict(n["props"])}
    for e in p["create_edges"]:
        edges[e["key"]] = {"key": e["key"], "type": e["type"], "start": e["start"], "end": e["end"], "source_json": e["source_json"],
                           "props": {"key": e["key"], "source_json": e["source_json"], **relationship_properties(e)}}
    for item in p["update_links"]:
        edges[item["key"]]["props"] = dict(item["props"])
    for k, props in p["set_props"].items():
        for field, value in props.items():
            if value is None:
                nodes[k]["props"].pop(field, None)
            else:
                nodes[k]["props"][field] = value
    return list(nodes.values()), list(edges.values())
# endregion


# region 2. 적용 (쓰기 트랜잭션 1개)
def _read(tx, query, **params):
    return [record.data() for record in tx.run(query, **params)]


def read_graph(tx) -> tuple[list[dict], list[dict]]:
    from .neo4j_load_draft import CYPHER
    return _read(tx, CYPHER["neo4j_validation.node_sources"]), _read(tx, CYPHER["neo4j_validation.relationship_sources"])


def _run_count(tx, query, expected: int, label: str, **params):
    if expected and tx.run(query, **params).single(strict=True)["n"] != expected:
        raise ProjectionSyncError(f"{label} 건수 불일치")


def sync_transaction(tx, nodes: list[dict], edges: list[dict], approved: dict) -> dict:
    """트랜잭션 안에서 계획을 다시 만들고, 승인 건수와 같을 때만 쓴 뒤 기준 그래프와 차이 0을 확인한다."""
    from .neo4j_load_draft import relationship_properties
    from .neo4j_validate import compare_graph

    p = plan(nodes, edges, *read_graph(tx))
    counts = plan_counts(p)
    if p["blocked"]:
        raise ProjectionSyncError(f"허용 범위 밖 차이 {len(p['blocked'])}건: {p['blocked'][:5]}")
    if counts != approved:
        raise ProjectionSyncError(f"승인한 변경 건수와 다릅니다: 승인 {approved}, 현재 {counts}")
    _run_count(tx, DELETE_LINKS, len(p["delete_links"]), "근거 연결 삭제", keys=p["delete_links"])
    _run_count(tx, DELETE_EVIDENCE, len(p["delete_evidence"]), "근거 노드 삭제", keys=p["delete_evidence"])
    _run_count(tx, CREATE_EVIDENCE, len(p["create_evidence"]), "근거 노드 생성",
               rows=[{"pk": n["pk"], "props": n["props"]} for n in p["create_evidence"]])
    for kind, query in MERGE_EDGES.items():
        rows = [{"start": e["start"], "end": e["end"], "key": e["key"], "source_json": e["source_json"],
                 "extra": relationship_properties(e)} for e in p["create_edges"] if e["type"] == kind]
        _run_count(tx, query, len(rows), f"{kind} 생성", rows=rows)
    _run_count(tx, UPDATE_LINKS, len(p["update_links"]), "근거 연결 갱신", rows=p["update_links"])
    rows = [{"key": k, "props": props} for k, props in p["set_props"].items()]
    _run_count(tx, SET_PROPS, len(rows), "투영 속성", rows=rows)
    after = compare_graph(nodes, edges, *read_graph(tx))
    if any(after.values()):
        raise ProjectionSyncError(f"사후 검증 실패: {({k: len(v) for k, v in after.items() if v})}")
    return {"applied": counts}
# endregion


# region 3. 인덱스 (별도 스키마 단계)
def create_indexes(session) -> list[str]:
    for statement in INDEX_STATEMENTS:
        session.run(statement).consume()
    session.run("CALL db.awaitIndexes(600)").consume()        # 벡터 인덱스는 비동기로 채워진다. ONLINE까지 기다린 뒤 검증한다
    return list(VECTOR_INDEXES)


def verify_vector_indexes(session, k: int = 10) -> dict:
    """읽기 전용. 저장 벡터마다 인덱스 상위 k가 전수 코사인 상위 k와 같은지 본다(근사 인덱스 정확도 확인)."""
    report = {}
    for name, label in VECTOR_INDEXES.items():
        state = session.run("SHOW INDEXES YIELD name, state WHERE name = $name RETURN state", name=name).single()
        rows = session.run(f"MATCH (n:{label}) WHERE n.embedding IS NOT NULL RETURN n.key AS key", ).data()
        mismatch = []
        for row in rows:
            exact = [r["key"] for r in session.run(
                f"MATCH (q:{label} {{key:$key}}) MATCH (n:{label}) WHERE n.embedding IS NOT NULL "
                "RETURN n.key AS key ORDER BY vector.similarity.cosine(q.embedding, n.embedding) DESC, n.key LIMIT $k",
                key=row["key"], k=k).data()]
            approx = [r["key"] for r in session.run(
                f"MATCH (q:{label} {{key:$key}}) CALL db.index.vector.queryNodes($index, $k, q.embedding) YIELD node "
                "RETURN node.key AS key", key=row["key"], k=k, index=name).data()]
            if exact != approx:
                mismatch.append(row["key"])
        report[name] = {"state": state and state["state"], "vectors": len(rows), "topk_mismatch": len(mismatch), "examples": mismatch[:3]}
    return report
# endregion


# region 4. 임베딩 대상·비용 계획 (PostgreSQL 읽기 전용, API 호출 없음)
EMBEDDING_PRICE_PER_1M_TOKENS = 0.02      # text-embedding-3-small 표준 단가 가정(USD). 실행 전 가격표 재확인


def embedding_plan(repository) -> dict:
    """기존 EmbeddingService와 같은 규칙(검색 텍스트 생성 함수·변경 판정)으로 생성 대상과 토큰 수를 센다."""
    import tiktoken
    from .embedding_service import SPECS

    encoding = tiktoken.get_encoding("cl100k_base")     # text-embedding-3 계열 토크나이저
    report = {}
    for table, spec in SPECS.items():
        targets, reuse, changed, tokens, review = 0, 0, 0, 0, 0
        for row in repository.rows(f"select_{spec.statement}_rows", IDS=None):
            built = spec.build(row)
            text_changed = built.text != row["bnft_search_txt"]
            needs = text_changed or not row["has_embedding"]
            review += bool(built.review)
            if row["has_embedding"] and not text_changed:
                reuse += 1
            changed += bool(row["has_embedding"] and text_changed)
            if needs:
                targets += 1
                tokens += len(encoding.encode(built.text))
        report[table] = {"reuse_existing": reuse, "existing_text_changed": changed, "generate": targets,
                         "tokens": tokens, "rows_with_review_items": review}
    total = sum(item["tokens"] for item in report.values())
    report["total"] = {"generate": sum(item["generate"] for item in report.values()), "tokens": total,
                       "estimated_usd": round(total * EMBEDDING_PRICE_PER_1M_TOKENS / 1_000_000, 6)}
    return report
# endregion


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--create-indexes", action="store_true")
    ap.add_argument("--confirm", default="")
    ap.add_argument("--expect", default="", help="승인한 plan_counts JSON")
    args = ap.parse_args()

    import psycopg
    from dotenv import load_dotenv
    from neo4j import READ_ACCESS

    from common.database_manager import DatabaseManager
    from common.neo4j_connection import create_neo4j_driver
    from common.postgres_db_session import PostgresDbSession

    from .document_repository import MAPPER_ROOT
    from .embedding_service import EmbeddingRepository
    from .neo4j_dry_run import build, load_snapshot
    from .neo4j_load_draft import EXPECTED_DB, prepare
    from .neo4j_validate import compare_graph

    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as c:      # load_snapshot이 READ ONLY 트랜잭션으로 읽는다
        graph, stats = build(load_snapshot(c))
    nodes, edges = prepare(graph)
    manager = DatabaseManager(autocommit=True, read_only=True)
    try:
        session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none", database_manager=manager)
        embedding = embedding_plan(EmbeddingRepository(session))
    finally:
        manager.close()
    with create_neo4j_driver() as driver:
        with driver.session(database=EXPECTED_DB, default_access_mode=READ_ACCESS) as s:
            found_nodes, found_edges = s.execute_read(read_graph)
        p = plan(nodes, edges, found_nodes, found_edges)
        after_nodes, after_edges = simulate(p, found_nodes, found_edges)
        residual = compare_graph(nodes, edges, after_nodes, after_edges)
        vectors = lambda ns: Counter(next(l for l in n["labels"] if l in PROJECTION_LABELS)
                                     for n in ns if "embedding" in n["props"] and set(n["labels"]) & set(PROJECTION_LABELS))
        report = {"mode": "APPLY" if args.apply else "CREATE_INDEXES" if args.create_indexes else "PREVIEW",
                  "target_database": EXPECTED_DB,
                  "now": {"nodes": len(found_nodes), "relationships": len(found_edges)},
                  "expected": {"nodes": len(nodes), "relationships": len(edges)},
                  "after_simulated": {"nodes": len(after_nodes), "relationships": len(after_edges),
                                      "residual_differences": {k: len(v) for k, v in residual.items()}},
                  "plan": plan_counts(p), "blocked_examples": p["blocked"][:10],
                  "embedding_reconciliation": {"targets": sum(1 for n in nodes if n["label"] in PROJECTION_LABELS),
                                               "ledger_vectors": dict(vectors([{"labels": [n["label"]], "props": n["props"]} for n in nodes])),
                                               "neo4j_vectors_now": dict(vectors(found_nodes)),
                                               "neo4j_vectors_after": dict(vectors(after_nodes))},
                  "embedding_generation_plan": embedding, "index_statements": list(INDEX_STATEMENTS),
                  "projection_stats": stats["search_projection"]}
        print(json.dumps(report, ensure_ascii=False, indent=1, default=str))
        if args.apply:
            if args.confirm != CONFIRM or os.getenv("NEO4J_DATABASE") != EXPECTED_DB or not args.expect:
                raise SystemExit("explicit approval confirmation, exact target database and --expect required")
            if p["blocked"] or any(residual.values()):
                raise SystemExit("허용 범위 밖 차이가 있거나 모의 적용 후 차이가 남아 중단합니다")
            with driver.session(database=EXPECTED_DB) as s:
                print("committed", json.dumps(s.execute_write(sync_transaction, nodes, edges, json.loads(args.expect)), ensure_ascii=False))
        if args.create_indexes:
            if args.confirm != INDEX_CONFIRM or os.getenv("NEO4J_DATABASE") != EXPECTED_DB:
                raise SystemExit("explicit index approval confirmation and exact target database required")
            with driver.session(database=EXPECTED_DB) as s:
                print("indexes", create_indexes(s))
                print("verify", json.dumps(verify_vector_indexes(s), ensure_ascii=False))


if __name__ == "__main__":
    main()
