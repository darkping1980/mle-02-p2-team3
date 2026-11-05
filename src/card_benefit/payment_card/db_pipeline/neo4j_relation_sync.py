"""PostgreSQL ``relation_list`` 원장 기준으로 Neo4j ``dp_related_to`` 관계만 동기화한다.

기본 실행은 읽기 전용 사전 검증(preview)이다. ``--apply`` 와 확인 문구·기대 변경 건수가 모두 맞을 때만 쓴다.

업무 식별 기준 (PostgreSQL CHECK ``card_product_item_rel_ck`` → ``fn_valid_relation_list``)
    - 한 출발 혜택 안에서 ``relation_key`` 는 필수·유일하다. 근거 연결(card_evidence_link, ev_subject_cd='REL')도
      (card_id, card_product_item_id, relation_key)로 관계를 가리킨다. → 관계 식별자 = (출발 노드, relation_key)
    - 한 출발 혜택 안에서 (to_bnft_id, rel_type_cd)도 유일하다. → 보조 유일키로 검사만 한다.
      같은 출발·대상이라도 rel_type_cd가 다르면 서로 다른 정상 관계다.
    - ``rel_priority`` 는 number|null 이며 어떤 유일 조건에도 없다. → 식별자가 아닌 갱신 가능한 속성이다.

동기화 규칙
    create  : 원장에 있고 Neo4j에 없는 식별자 → MERGE로 생성
    update  : 식별자·끝점이 같고 속성만 다름 → 같은 관계의 속성만 교체(SET r = $props). 새 관계를 만들지 않는다
    replace : 식별자는 같은데 대상 노드가 바뀜 → Neo4j 관계는 끝점을 옮길 수 없으므로 그 관계만 삭제 후 생성
    delete  : Neo4j에 있고 원장에 없는 식별자 → 그 dp_related_to만 삭제
    그 외 관계 유형·노드는 읽기만 하고, 트랜잭션 안에서 적용 전후 지문(fingerprint)이 같아야 commit한다.

관계 ``key`` 속성은 기존 적재기(prepare)와 같은 값(유형·끝점·원본 JSON 해시)을 그대로 기록한다. 그래서 neo4j_validate의
기존 비교와 호환된다. 원본 내용이 바뀌면 key 값도 바뀌지만, 관계의 식별은 key가 아니라 (출발, relation_key)로 한다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter

PREFIX = "dp_"
REL_TYPE = "dp_related_to"
CONFIRM = "APPROVED_DP_RELATED_TO_SYNC"

# 첫 줄의 ``// rel_sync:이름`` 은 Neo4j에서는 주석이고, 테스트의 가짜 트랜잭션은 이 이름으로 구문을 구분한다.
READ_RELATED = """// rel_sync:read_related
MATCH (a)-[r:dp_related_to]->(b)
RETURN elementId(r) AS id, a.key AS start, b.key AS end, (a:dp_node AND b:dp_node) AS in_scope, properties(r) AS props"""
READ_NODES = """// rel_sync:read_nodes
MATCH (n:dp_node) RETURN n.key AS key, labels(n) AS labels, properties(n) AS props"""
READ_OTHER_RELS = """// rel_sync:read_other_rels
MATCH (a)-[r]->(b) WHERE type(r) STARTS WITH 'dp_' AND type(r) <> 'dp_related_to'
RETURN type(r) AS type, a.key AS start, b.key AS end, properties(r) AS props"""
DELETE_RELATED = """// rel_sync:delete_related
MATCH (:dp_node)-[r:dp_related_to]->(:dp_node) WHERE elementId(r) IN $ids
DELETE r RETURN count(*) AS n"""
UPDATE_RELATED = """// rel_sync:update_related
UNWIND $rows AS row
MATCH (:dp_node)-[r:dp_related_to]->(:dp_node) WHERE elementId(r) = row.id
SET r = row.props RETURN count(r) AS n"""
MERGE_RELATED = """// rel_sync:merge_related
UNWIND $rows AS row
MATCH (a:dp_node {key: row.start}), (b:dp_node {key: row.end})
MERGE (a)-[r:dp_related_to {relation_key: row.relation_key}]->(b)
SET r = row.props RETURN count(r) AS n"""
WRITE_STATEMENTS = (DELETE_RELATED, UPDATE_RELATED, MERGE_RELATED)


class RelationSyncError(ValueError):
    """원장·그래프 상태가 동기화 전제와 맞지 않는다. 추측해서 고치지 않고 중단한다."""


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


# region 1. 원장(기대 관계) 구성
def ledger_relations(nodes: list[dict], edges: list[dict]) -> dict[tuple, dict]:
    """prepare 결과에서 dp_related_to만 골라 (출발 key, relation_key) → 기대 관계로 만든다.

    PostgreSQL CHECK와 같은 조건을 다시 확인한다. 하나라도 어기면 RelationSyncError(원장 오류, 그래프 미변경).
    """
    from .neo4j_load_draft import relationship_properties

    by_key = {n["props"]["key"]: n for n in nodes}
    result, pairs, errors = {}, set(), []
    for e in edges:
        if e["type"] != REL_TYPE:
            continue
        source = json.loads(e["source_json"])
        relation_key = source.get("relation_key")
        start, end = by_key.get(e["start"]), by_key.get(e["end"])
        identity = (e["start"], relation_key)
        if not relation_key:
            errors.append(f"relation_key 없음: {e['start']}")
        elif identity in result:
            errors.append(f"relation_key 중복: {identity}")
        if start is None or end is None:
            errors.append(f"끝점 노드 없음: {e['start']} -> {e['end']}")
        else:
            if start["props"].get("card_id") != end["props"].get("card_id"):
                errors.append(f"다른 카드 대상: {identity}")
            if end["props"].get("card_bnft_id") != source.get("to_bnft_id"):
                errors.append(f"to_bnft_id와 대상 노드 불일치: {identity}")
            if e["start"] == e["end"]:
                errors.append(f"자기 참조: {identity}")
        pair = (e["start"], e["end"], source.get("rel_type_cd"))
        if pair in pairs:
            errors.append(f"(대상, rel_type_cd) 중복: {pair}")
        pairs.add(pair)
        result[identity] = {"start": e["start"], "end": e["end"], "relation_key": relation_key,
                            "props": {"key": e["key"], "source_json": e["source_json"], **relationship_properties(e)}}
    if errors:
        raise RelationSyncError("원장 관계 오류: " + "; ".join(errors))
    return result
# endregion


# region 2. 계획 (순수 함수)
def plan(ledger: dict[tuple, dict], related_rows: list[dict]) -> dict:
    """원장과 Neo4j의 dp_related_to를 식별자로 맞춰 create/update/replace/delete/unchanged로 나눈다."""
    errors, found = [], {}
    for row in related_rows:
        if not row.get("in_scope"):
            errors.append(f"dp_node 밖의 dp_related_to: {row['id']}")
            continue
        relation_key = (row["props"] or {}).get("relation_key")
        if not relation_key:
            errors.append(f"relation_key 없는 기존 관계: {row['id']} {row['start']}")
            continue
        identity = (row["start"], relation_key)
        if identity in found:
            # 어느 쪽이 맞는지 알 수 없으므로 고르지 않는다.
            errors.append(f"같은 식별자의 기존 관계가 여러 개: {identity}")
            continue
        found[identity] = row
    if errors:
        raise RelationSyncError("기존 그래프 관계 오류: " + "; ".join(errors))
    result = {"create": [], "update": [], "replace": [], "delete": [], "unchanged": []}
    for identity, want in sorted(ledger.items()):
        have = found.get(identity)
        if have is None:
            result["create"].append(want)
        elif have["end"] != want["end"]:
            result["replace"].append({"old_id": have["id"], "old_end": have["end"], **want})
        elif canonical(have["props"]) != canonical(want["props"]):
            changed = sorted(k for k in set(have["props"]) | set(want["props"]) if have["props"].get(k) != want["props"].get(k))
            result["update"].append({"id": have["id"], "fields": changed, **want})
        else:
            result["unchanged"].append(identity)
    for identity, have in sorted(found.items()):
        if identity not in ledger:
            result["delete"].append({"id": have["id"], "start": have["start"], "end": have["end"], "relation_key": identity[1],
                                     "rel_type_cd": (have["props"] or {}).get("rel_type_cd")})
    return result


def plan_counts(p: dict) -> dict:
    return {name: len(items) for name, items in p.items()}
# endregion


# region 3. 지문 (dp_related_to 외 상태가 바뀌지 않았는지)
def fingerprint(node_rows: list[dict], other_rel_rows: list[dict]) -> dict:
    """라벨 순서와 행 순서에 무관한 노드·관계 지문. 속성은 전체 map을 정규화해 비교한다."""
    nodes = sorted(canonical([r["key"], sorted(r["labels"]), r["props"]]) for r in node_rows)
    rels = sorted(canonical([r["type"], r["start"], r["end"], r["props"]]) for r in other_rel_rows)
    digest = lambda lines: hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()  # noqa: E731
    return {"nodes": len(nodes), "nodes_sha256": digest(nodes), "other_relationships": len(rels),
            "other_relationships_sha256": digest(rels), "other_by_type": dict(sorted(Counter(r["type"] for r in other_rel_rows).items()))}


def _read(tx, query, **params) -> list[dict]:
    return [record.data() for record in tx.run(query, **params)]


def read_state(tx) -> dict:
    return {"related": _read(tx, READ_RELATED), "nodes": _read(tx, READ_NODES), "other": _read(tx, READ_OTHER_RELS)}
# endregion


# region 4. 적용 (하나의 쓰기 트랜잭션)
def sync_transaction(tx, ledger: dict[tuple, dict], expected_counts: dict | None = None) -> dict:
    """계획을 트랜잭션 안에서 다시 계산해 적용하고 사후 검증한다. 예외면 execute_write가 rollback한다.

    Args:
        expected_counts: 사전 승인한 {create, update, replace, delete} 건수. 트랜잭션 안에서 다시 계산한 계획과
            다르면(사전 검증 뒤 그래프가 바뀜) 쓰기 전에 중단한다.
    """
    before = read_state(tx)
    p = plan(ledger, before["related"])
    counts = plan_counts(p)
    if expected_counts is not None:
        actual = {k: counts[k] for k in ("create", "update", "replace", "delete")}
        if actual != {k: expected_counts.get(k, 0) for k in actual}:
            raise RelationSyncError(f"승인한 변경 건수와 다릅니다: 승인 {expected_counts}, 현재 {actual}")
    fp_before = fingerprint(before["nodes"], before["other"])

    delete_ids = [item["id"] for item in p["delete"]] + [item["old_id"] for item in p["replace"]]
    if delete_ids and tx.run(DELETE_RELATED, ids=delete_ids).single(strict=True)["n"] != len(delete_ids):
        raise RelationSyncError("삭제 건수 불일치")
    if p["update"]:
        rows = [{"id": item["id"], "props": item["props"]} for item in p["update"]]
        if tx.run(UPDATE_RELATED, rows=rows).single(strict=True)["n"] != len(rows):
            raise RelationSyncError("갱신 건수 불일치")
    creates = p["create"] + p["replace"]
    if creates:
        rows = [{k: item[k] for k in ("start", "end", "relation_key", "props")} for item in creates]
        if tx.run(MERGE_RELATED, rows=rows).single(strict=True)["n"] != len(rows):
            raise RelationSyncError("생성 건수 불일치(끝점 노드 없음 가능)")

    after = read_state(tx)
    residual = plan(ledger, after["related"])
    if any(residual[k] for k in ("create", "update", "replace", "delete")) or len(after["related"]) != len(ledger):
        raise RelationSyncError(f"사후 검증 실패: 남은 차이 {plan_counts(residual)}, 관계 {len(after['related'])}/{len(ledger)}")
    fp_after = fingerprint(after["nodes"], after["other"])
    if fp_after != fp_before:
        raise RelationSyncError(f"dp_related_to 외 노드·관계가 바뀌었습니다: 전 {fp_before} 후 {fp_after}")
    return {"applied": {k: counts[k] for k in ("create", "update", "replace", "delete")},
            "unchanged": counts["unchanged"], "related_after": len(after["related"]), "fingerprint": fp_after}
# endregion


# region 5. 사전 검증 보고 (읽기 전용)
def classify_orphans(orphan_keys: list[str], expected_edges: list[dict], found_edges: list[dict]) -> dict:
    """Neo4j 고아 노드를, 원장 그래프에서도 같은 연결 상태인 것(원천 기존 문제)과 적재 차이로 생긴 것으로 나눈다.

    판정을 완화하지 않는다. 분류는 보고용이며 고아가 1건이라도 있으면 전체 검증 실패는 그대로다.
    """
    def incident(edges, key):
        return sorted((e["type"], e["start"], e["end"]) for e in edges if key in (e["start"], e["end"]))
    source, load = [], []
    for key in orphan_keys:
        (source if incident(expected_edges, key) == incident(found_edges, key) else load).append(key)
    return {"source_preexisting": source, "load_mismatch": load}


def preflight(nodes, edges, state: dict, validation: dict | None = None) -> dict:
    """적재 전 상태를 보고한다. 관계 동기화 준비 여부와 전체 검증 결과를 분리해서 둘 다 보여 준다."""
    ledger = ledger_relations(nodes, edges)
    p = plan(ledger, state["related"])
    counts = plan_counts(p)
    other_expected = [e for e in edges if e["type"] != REL_TYPE]
    current_total = len(state["other"]) + len(state["related"])
    after_total = current_total + counts["create"] - counts["delete"]
    report = {
        "ledger_related": len(ledger),
        "neo4j_now": {"nodes": len(state["nodes"]), "relationships": current_total, "related_to": len(state["related"])},
        "plan": counts,
        "plan_detail": {k: [{f: v for f, v in item.items() if f in ("start", "end", "relation_key", "fields", "old_end", "rel_type_cd")}
                            | ({"rel_type_cd": json.loads(item["props"]["source_json"]).get("rel_type_cd")} if "props" in item else {})
                            for item in p[k]] for k in ("create", "update", "replace", "delete")},
        "expected_after": {"nodes": len(state["nodes"]), "relationships": after_total, "related_to": len(ledger)},
        "ledger_expected": {"nodes": len(nodes), "relationships": len(edges)},
        "other_relationships_expected_vs_now": [len(other_expected), len(state["other"])],
        "fingerprint_before": fingerprint(state["nodes"], state["other"]),
    }
    if validation is not None:
        diff = validation["difference_keys"]
        non_related = {k: [x for x in v if not _is_related(x, edges, state)] for k, v in diff.items()}
        orphans = [row["key"] for row in validation["orphan_nodes"]]
        found_edges = [{"type": r["type"], "start": r["start"], "end": r["end"]} for r in state["other"]] + \
                      [{"type": REL_TYPE, "start": r["start"], "end": r["end"]} for r in state["related"]]
        report["full_validation"] = {"ok": validation["ok"], "differences": validation["differences"],
                                     "orphans": classify_orphans(orphans, edges, found_edges),
                                     "sql_cypher": validation["sql_cypher"], "outside_scope": validation["outside_scope"]}
        report["non_related_differences"] = {k: len(v) for k, v in non_related.items()}
        report["relation_sync_ready"] = (not any(non_related.values()) and validation["outside_scope"] ==
                                         {"outside_nodes": 0, "outside_relationships": 0}
                                         and all(v[2] for v in validation["sql_cypher"].values())
                                         and not report["full_validation"]["orphans"]["load_mismatch"])
    return report


def _is_related(item, edges, state) -> bool:
    """compare_graph 차이 항목이 dp_related_to 관계에 대한 것인지(관계 key 기준)."""
    key = item["key"] if isinstance(item, dict) else item
    related_keys = {e["key"] for e in edges if e["type"] == REL_TYPE} | {(r["props"] or {}).get("key") for r in state["related"]}
    return key in related_keys
# endregion


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--confirm", default="")
    ap.add_argument("--expect", default="", help="승인한 변경 건수 JSON, 예: {\"create\":6,\"update\":0,\"replace\":0,\"delete\":0}")
    args = ap.parse_args()

    import psycopg
    from dotenv import load_dotenv
    from neo4j import READ_ACCESS

    from common.neo4j_connection import create_neo4j_driver

    from .neo4j_dry_run import build, load_snapshot
    from .neo4j_load_draft import EXPECTED_DB, prepare
    from .neo4j_validate import run as run_validation

    load_dotenv(".env")
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as c:   # load_snapshot이 READ ONLY로 읽는다
        graph, _ = build(load_snapshot(c))
    nodes, edges = prepare(graph)
    ledger = ledger_relations(nodes, edges)
    with create_neo4j_driver() as driver:
        with driver.session(database=EXPECTED_DB, default_access_mode=READ_ACCESS) as session:
            state = session.execute_read(read_state)
        report = preflight(nodes, edges, state, run_validation())
        print(json.dumps({"mode": "APPLY" if args.apply else "PREVIEW", "target_database": EXPECTED_DB, **report},
                         ensure_ascii=False, indent=1, default=str))
        if not args.apply:
            return
        if args.confirm != CONFIRM or os.getenv("NEO4J_DATABASE") != EXPECTED_DB:
            raise SystemExit("explicit approval confirmation and exact target database required")
        if not report.get("relation_sync_ready"):
            raise SystemExit("관계 동기화 전제(dp_related_to 외 차이 0, 범위·SQL 대조 정상, 적재 원인 고아 0)를 만족하지 않습니다")
        expected = json.loads(args.expect) if args.expect else None
        if expected is None:
            raise SystemExit("--expect 로 승인한 변경 건수를 지정해야 합니다")
        with driver.session(database=EXPECTED_DB) as session:
            print("committed", json.dumps(session.execute_write(sync_transaction, ledger, expected), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
