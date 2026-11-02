"""실제 DB의 db_pipeline 전체 행을 읽기 전용으로 내려받는다. 결과는 .work/에만 저장하며 접속 정보는 출력하지 않는다."""
import json
import os
import pathlib
import sys

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[5]
WORK = pathlib.Path(__file__).resolve().parent / ".work"
WORK.mkdir(exist_ok=True)
load_dotenv(ROOT / ".env")
OUT = WORK / "live_rows.json"
data = {"tables": {}, "sequences": {}}
with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as conn:
    conn.read_only = True
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""select c.relname from pg_class c where c.relnamespace='db_pipeline'::regnamespace and c.relkind='r' order by 1""")
        for name in [r["relname"] for r in cur.fetchall()]:
            cur.execute(f"select coalesce(jsonb_agg(to_jsonb(t)), '[]'::jsonb) AS rows from db_pipeline.{name} t")
            data["tables"][name] = cur.fetchone()["rows"]
        cur.execute("select sequencename, last_value from pg_sequences where schemaname='db_pipeline'")
        for r in cur.fetchall():
            data["sequences"][r["sequencename"]] = r["last_value"]
OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
print({k: len(v) for k, v in data["tables"].items()})
