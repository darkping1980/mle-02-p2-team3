"""실제 DB 카탈로그와 catalog_dump.mjs 결과를 읽기 전용으로 비교한다. 사용법: python catalog_diff.py .work/v6_catalog.json"""
import json
import os
import pathlib
import re
import sys

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[5]
load_dotenv(ROOT / ".env")
built = json.load(open(sys.argv[1], encoding="utf-8"))

Q = {
    "columns": """select table_name t, column_name c, data_type d, character_maximum_length l, is_nullable n, column_default df, ordinal_position p
                  from information_schema.columns where table_schema='db_pipeline' order by 1,7""",
    "constraints": """select conrelid::regclass::text t, conname c, contype::text k, pg_get_constraintdef(oid) d from pg_constraint
                      where connamespace='db_pipeline'::regnamespace and conrelid<>0 order by 1,2""",
    "indexes": "select tablename t, indexname i, indexdef d from pg_indexes where schemaname='db_pipeline' order by 1,2",
    "views": "select viewname v, definition d from pg_views where schemaname='db_pipeline' order by 1",
    "functions": """select proname p, pg_get_function_identity_arguments(oid) a, prosrc s from pg_proc
                    where pronamespace='db_pipeline'::regnamespace order by 1""",
    "sequences": "select c.relname s from pg_class c where c.relnamespace='db_pipeline'::regnamespace and c.relkind='S' order by 1",
    "comments": """select c.relname t, a.attname c, col_description(c.oid,a.attnum) d from pg_class c join pg_attribute a on a.attrelid=c.oid
                   where c.relnamespace='db_pipeline'::regnamespace and c.relkind='r' and a.attnum>0 and not a.attisdropped order by 1,2""",
}
KEYS = {"columns": ("t", "c"), "constraints": ("t", "c"), "indexes": ("t", "i"), "views": ("v",),
        "functions": ("p", "a"), "sequences": ("s",), "comments": ("t", "c")}


def norm(v):
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else None


with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as conn:
    conn.read_only = True
    with conn.cursor(row_factory=dict_row) as cur:
        for name, sql in Q.items():
            cur.execute(sql)
            live = {tuple(r[k] for k in KEYS[name]): r for r in cur.fetchall()}
            file_ = {tuple(r[k] for k in KEYS[name]): r for r in built[name]}
            only_live = sorted(set(live) - set(file_))
            only_file = sorted(set(file_) - set(live))
            changed = []
            for k in sorted(set(live) & set(file_)):
                a, b = live[k], file_[k]
                diffs = [f for f in a if norm(a[f]) != norm(b[f])]
                if diffs:
                    changed.append((k, {f: (norm(a[f])[:150] if a[f] else None, norm(b[f])[:150] if b[f] else None) for f in diffs}))
            print(f"[{name}] live={len(live)} file={len(file_)} only_live={only_live} only_file={only_file} changed={len(changed)}")
            for item in changed[:14]:
                print("   ", item)
