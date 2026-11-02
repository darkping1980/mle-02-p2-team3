"""실제 DB 트랜잭션 안에서 V6->V7 이관을 실행하고 항상 ROLLBACK한다.

--run-with-rollback 없이는 DB에 접속하지 않는다. COMMIT 경로가 없지만 실행 중에는 대상 테이블에 잠금이 걸린다.
V7이 적용된 뒤에는 쓰지 않는다. 이관 결과의 스냅샷은 Neo4j 격리 시험 입력으로 .work/에 저장한다.
접속 정보는 출력하지 않는다.
"""
import argparse
import json
import os
import pathlib
import pickle
import re
import sys

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--run-with-rollback", action="store_true", help="실제 DB에서 트랜잭션을 열고 끝에서 ROLLBACK한다")
if not parser.parse_args().run_with_rollback:
    raise SystemExit("실행하지 않았습니다. 실제 DB에서 시험하려면 --run-with-rollback을 명시하세요. README를 먼저 읽으세요.")
ROOT = pathlib.Path(__file__).resolve().parents[5]
WORK = pathlib.Path(__file__).resolve().parent / ".work"
WORK.mkdir(exist_ok=True)
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "src/card_benefit")]
load_dotenv(ROOT / ".env")
SQLD = ROOT / "src/card_benefit/sql"

from payment_card.db_pipeline import neo4j_dry_run as dry  # noqa: E402


def strip_tx(sql):
    assert sql.count("\nBEGIN;\n") == 1 and sql.rstrip().endswith("COMMIT;")
    return sql.replace("\nBEGIN;\n", "\n", 1).rstrip()[: -len("COMMIT;")]


def snapshot(cur):
    queries = {
        "product": ("SELECT * FROM db_pipeline.card_product WHERE card_id=%s", (dry.CARD_ID,)),
        "product_doc": ("SELECT * FROM db_pipeline.card_product_doc WHERE card_id=%s AND card_doc_id=%s", (dry.CARD_ID, dry.DOC_ID)),
        "benefits": ("SELECT * FROM db_pipeline.card_bnft WHERE card_id=%s ORDER BY card_bnft_id", (dry.CARD_ID,)),
        "pools": ("SELECT * FROM db_pipeline.card_limit_pool WHERE card_id=%s ORDER BY pool_id", (dry.CARD_ID,)),
        "links": ("SELECT * FROM db_pipeline.card_evidence_link WHERE card_id=%s ORDER BY ev_link_id", (dry.CARD_ID,)),
        "evidence": ("SELECT * FROM db_pipeline.card_source_evidence WHERE card_doc_id=%s ORDER BY evidence_id", (dry.DOC_ID,)),
        "chunks": ("SELECT * FROM db_pipeline.card_doc_chunk WHERE card_doc_id=%s ORDER BY page_no,card_doc_chunk_id", (dry.DOC_ID,)),
        "pages": ("SELECT * FROM db_pipeline.card_doc_page WHERE card_doc_id=%s ORDER BY page_no", (dry.DOC_ID,)),
        "document": ("SELECT * FROM db_pipeline.card_doc WHERE card_doc_id=%s", (dry.DOC_ID,)),
    }
    out = {}
    for name, (sql, params) in queries.items():
        cur.execute(sql, params)
        out[name] = cur.fetchall()
    return out


with psycopg.connect(os.environ["DB_URL"], connect_timeout=10, autocommit=False) as conn:
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("show server_version")
            print("server", cur.fetchone())
            cur.execute("set local statement_timeout = '120s'")
            cur.execute("select count(*) n from db_pipeline.card_policy_evidence")
            print("links before", cur.fetchone())
            cur.execute(strip_tx((SQLD / "db_pipeline_migration_V6_to_V7.sql").read_text(encoding="utf-8")))
            print("migration executed inside transaction")
            for label, sql in {
                "tables": "select count(*) n from pg_class where relnamespace='db_pipeline'::regnamespace and relkind='r'",
                "views": "select count(*) n from pg_class where relnamespace='db_pipeline'::regnamespace and relkind='v'",
                "policy objects": """select count(*) n from pg_class where relnamespace='db_pipeline'::regnamespace
                                     and relname in ('card_policy_version','card_policy_evidence','v_card_policy_doc','seq_card_policy_version')""",
                "links": "select count(*) n from db_pipeline.card_evidence_link",
                "card subject": "select count(*) n from db_pipeline.card_evidence_link where ev_subject_cd='CARD'",
                "cond atoms card": "select count(*) n from db_pipeline.v_card_cond_atom where owner_cd='CARD'",
            }.items():
                cur.execute(sql)
                print(label, cur.fetchone()["n"])
            cur.execute("select gate_cd, count(*) n from db_pipeline.v_card_integrity_issue group by 1")
            print("gate", cur.fetchall())
            cur.execute("select card_cond_status_cd, jsonb_array_length(card_cond_expr->'branches') b from db_pipeline.card_product")
            print("card cond", cur.fetchall())
            snap = snapshot(cur)
            cur.execute("""select owner_cd, card_bnft_id, rule_key, branch_no, atom_seq, atom_key, cond_type_cd, negate_yn, cond_min_amt, cond_raw_txt
                           from db_pipeline.v_card_cond_atom where card_id = 2""")
            sql_conditions = cur.fetchall()
            cur.execute("""select l.ev_link_id, l.ev_subject_cd, l.rule_key, l.pool_id, l.ev_item_cd, l.ev_item_key, l.evidence_id, e.start_pos, e.end_pos
                           from db_pipeline.card_evidence_link l join db_pipeline.card_source_evidence e on e.evidence_id=l.evidence_id
                           where l.card_id = 2""")
            sql_links = cur.fetchall()
            # 음성 시험: 파일의 BEGIN/ROLLBACK 없이 SAVEPOINT 안에서 실행한다.
            test = (SQLD / "db_pipeline_v7_integrity_test.sql").read_text(encoding="utf-8")
            body = test.split("\nBEGIN;\n", 1)[1].rsplit("ROLLBACK;", 1)[0]
            cur.execute("SAVEPOINT v7_test")
            cur.execute(body)
            cur.execute("ROLLBACK TO SAVEPOINT v7_test")
            print("integrity negative test on live copy: PASS")
    finally:
        conn.rollback()
        print("ROLLED BACK")

# 실제 DB가 그대로인지 새 연결로 확인한다.
with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as conn:
    conn.read_only = True
    with conn.cursor() as cur:
        cur.execute("""select to_regclass('db_pipeline.card_policy_version') is not null, to_regclass('db_pipeline.card_evidence_link') is null,
                              to_regnamespace('db_pipeline_v6_backup') is null""")
        print("live intact (v6 table, no v7 table, no backup schema):", cur.fetchone())
        cur.execute("select count(*) from db_pipeline.card_policy_evidence")
        print("live links", cur.fetchone()[0])

graph, stats = dry.build(snap)
print(json.dumps({k: stats[k] for k in ("node_total", "relationship_total", "dangling_edges")}))
print(stats["nodes"]); print(stats["relationships"])
with open(WORK / "v7_snapshot.pkl", "wb") as fh:
    pickle.dump({"snapshot": snap, "sql_conditions": sql_conditions, "sql_links": sql_links}, fh)
