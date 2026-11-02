"""V7 그래프를 격리 네임스페이스 df_v7_test에 적재하고 조회한 뒤 지운다.

--write-test-namespace 없이는 Neo4j에 접속하지 않는다. 공유 Aura DB에 쓰는 도구이므로 사용자 승인을 받고 실행한다.
쓰기와 삭제는 namespace = df_v7_test 노드로 한정한다. 운영 네임스페이스는 전후 해시만 비교한다.
입력: live_rollback_dryrun.py가 만든 .work/v7_snapshot.pkl. 현재 샘플 카드 1장 구조만 다룬다.
"""
import argparse
import hashlib
import json
import os
import pathlib
import pickle
import sys

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--write-test-namespace", action="store_true", help="공유 Neo4j의 df_v7_test 네임스페이스에 쓰고 지운다")
if not parser.parse_args().write_test_namespace:
    raise SystemExit("실행하지 않았습니다. 시험 적재하려면 --write-test-namespace를 명시하세요. README를 먼저 읽으세요.")
ROOT = pathlib.Path(__file__).resolve().parents[5]
WORK = pathlib.Path(__file__).resolve().parent / ".work"
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "src/card_benefit")]
load_dotenv(ROOT / ".env")

from common.neo4j_connection import create_neo4j_driver  # noqa: E402
from neo4j import READ_ACCESS  # noqa: E402
from payment_card.db_pipeline import neo4j_dry_run as dry, neo4j_load_draft as load, neo4j_validate as val  # noqa: E402
from payment_card.db_pipeline_origin_search import neo4j_search as search  # noqa: E402
from payment_card.db_pipeline_origin_search import card_graphrag as rag  # noqa: E402

TEST_NS = "df_v7_test"
REAL_NS = "df_one_pick_style"
dry.NS = load.NS = search.NAMESPACE = TEST_NS
DB = load.EXPECTED_DB
if os.getenv("NEO4J_DATABASE") != DB:
    raise SystemExit("unexpected target database")

saved = pickle.load(open(WORK / "v7_snapshot.pkl", "rb"))
graph, stats = dry.build(saved["snapshot"])
nodes, edges = load.prepare(graph)
print("prepared", len(nodes), len(edges))
assert all(n["props"]["namespace"] == TEST_NS for n in nodes)

COUNT = """MATCH (n:df_node {namespace:$ns}) WITH count(n) AS nodes
           OPTIONAL MATCH (a:df_node {namespace:$ns})-[r]->(:df_node {namespace:$ns}) RETURN nodes, count(r) AS rels"""
OTHER = """OPTIONAL MATCH (n) WHERE NOT n:df_node WITH count(n) AS other_nodes
           OPTIONAL MATCH (a)-[r]->(b) WHERE NOT a:df_node AND NOT b:df_node RETURN other_nodes, count(r) AS other_rels"""
DIGEST = """MATCH (n:df_node {namespace:$ns}) WITH n ORDER BY n.key
            RETURN collect(n.key + '|' + coalesce(n.source_json,'')) AS items"""


def real_state(session):
    counts = session.run(COUNT, ns=REAL_NS).single().data()
    items = session.run(DIGEST, ns=REAL_NS).single()["items"]
    other = session.run(OTHER).single().data()
    return counts, hashlib.sha256("\n".join(items).encode()).hexdigest(), other


with create_neo4j_driver() as driver:
    with driver.session(database=DB) as session:
        before = real_state(session)
        print("real namespace before", before[0], before[1][:12], "other", before[2])
        leftover = session.run(COUNT, ns=TEST_NS).single().data()
        if leftover["nodes"]:
            raise SystemExit(f"test namespace not empty: {leftover}")
        try:
            print("committed", session.execute_write(load.write_transaction, nodes, edges))

            def read(name):
                return session.execute_read(lambda tx: [r.data() for r in tx.run(load.CYPHER[f"neo4j_validation.{name}"], ns=TEST_NS)])

            result = val.compare_graph(nodes, edges, read("node_sources"), read("relationship_sources"))
            print("graph differences", {k: len(v) for k, v in result.items()})
            print("orphans", read("orphan_nodes"))
            print("labels", {r["label"]: r["n"] for r in read("label_counts")})
            condition_fields = ("owner_cd", "rule_key", "branch_no", "atom_seq", "atom_key", "cond_type_cd", "negate_yn", "cond_min_amt", "cond_raw_txt")
            link_fields = ("ev_link_id", "ev_subject_cd", "rule_key", "pool_id", "ev_item_cd", "ev_item_key", "evidence_id", "start_pos", "end_pos")
            a, b = val._normalize(saved["sql_conditions"], condition_fields), val._normalize(read("condition_structure"), condition_fields)
            print("SQL=Cypher conditions", len(a), len(b), a == b)
            a, b = val._normalize(saved["sql_links"], link_fields), val._normalize(read("evidence_links"), link_fields)
            print("SQL=Cypher evidence links", len(a), len(b), a == b)

            s = search.Neo4jSearch(driver, DB)
            catalog = s.list_catalog()
            print("catalog", [(r["name"], r["status"], r["targets"][:3], r["payment_min_amounts"]) for r in catalog])
            details = {r["name"]: s.get_detail(r["key"]) for r in catalog}
            ctx = next(iter(details.values()))["context"]
            print("context keys", sorted(ctx))
            print("\n=== 질문별 조회 ===")
            for name, d in details.items():
                groups = rag.condition_groups(d["conditions"])
                print(f"\n[{name}]")
                print(" rules:", [(rs["rule"]["rule_key"], rs["rule"].get("value_num"), rs["targets"][:3]) for rs in d["rules"]])
                print(" limits:", [(l["pool"].get("period"), l["pool"].get("unit"), l["pool"].get("value"), l["rule_keys"]) for l in d["limits"]])
                for g in groups:
                    print(f" cond[{g['scope']}]:", [[(a['type'], 'NOT' if a['negate'] else '', a['min_amt'], (a['text'] or '')[:34].replace(chr(10), ' ')) for a in br['atoms']] for br in g["branches"]])
                ev = rag.collect_evidence([d], "BENEFIT_DETAIL")
                subj = {}
                for e in ev:
                    for x in e["subjects"]:
                        subj[x] = subj.get(x, 0) + 1
                print(" evidence:", len(ev), "subjects", subj, "pages", sorted({e["page_no"] for e in ev}), "status", {e["approval_status"] for e in ev})
                print(" first:", [(e["page_no"], e["quote"][:44].replace(chr(10), ' ')) for e in ev[:2]])
                print(" unresolved:", [u[:60] for u in rag.find_unresolved([d])])
        finally:
            deleted = session.run("MATCH (n:df_node {namespace:$ns}) DETACH DELETE n RETURN count(n) AS n", ns=TEST_NS).consume().counters
            print("removed test nodes", deleted.nodes_deleted, "rels", deleted.relationships_deleted)
        after = real_state(session)
        print("test namespace after", session.run(COUNT, ns=TEST_NS).single().data())
        print("real namespace unchanged", before == after, after[0])
