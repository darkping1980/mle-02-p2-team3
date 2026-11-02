"""TEXT 단순화 격리 시험 입력을 내려받는다. 읽기 전용 세션이며 .work/ 밖으로 쓰지 않는다.

사용법: python export_simplify_rows.py   (결과: .work/simplify_rows.json, Git 제외)
"""
import json
import os
import pathlib

import psycopg
from dotenv import load_dotenv

HERE = pathlib.Path(__file__).resolve().parent
load_dotenv(HERE.parents[4] / ".env")
OUT = HERE / ".work" / "simplify_rows.json"


def main():
    res = {"tables": {}, "backup": {}, "sequences": {}}
    with psycopg.connect(os.environ["DB_URL"], connect_timeout=15) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            for schema, target in (("db_pipeline", "tables"), ("db_pipeline_backup", "backup")):
                cur.execute("""SELECT relname FROM pg_class WHERE relnamespace=%s::regnamespace AND relkind='r' ORDER BY 1""", (schema,))
                for (name,) in cur.fetchall():
                    cur.execute(f'SELECT to_jsonb(t) FROM {schema}."{name}" t')
                    res[target][name] = [row[0] for row in cur.fetchall()]
            cur.execute("""SELECT relname FROM pg_class WHERE relnamespace='db_pipeline'::regnamespace AND relkind='S' ORDER BY 1""")
            for (name,) in cur.fetchall():
                cur.execute(f'SELECT last_value, is_called FROM db_pipeline."{name}"')
                res["sequences"][name] = cur.fetchone()
        conn.rollback()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(res, ensure_ascii=False, default=str), encoding="utf-8")
    print({k: len(v) for k, v in res["tables"].items()})
    print({k: len(v) for k, v in res["backup"].items()})
    print(res["sequences"])


if __name__ == "__main__":
    main()
