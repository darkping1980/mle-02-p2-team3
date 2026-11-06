import json
import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

load_dotenv(".env")
with psycopg.connect(os.environ["DB_URL"], connect_timeout=10, autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT current_database() AS db, inet_server_addr()::text AS host, inet_server_port() AS port, version() AS version")
        identity = cur.fetchone()
        cur.execute("""SELECT c.table_name,c.column_name,c.ordinal_position,c.data_type,c.udt_name,c.is_nullable
          FROM information_schema.columns c WHERE c.table_schema='db_pipeline' ORDER BY c.table_name,c.ordinal_position""")
        columns = cur.fetchall()
        cur.execute("""SELECT t.relname AS table_name, con.conname AS name, con.contype AS type,
          pg_get_constraintdef(con.oid) AS definition
          FROM pg_constraint con JOIN pg_class t ON t.oid=con.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
          WHERE n.nspname='db_pipeline' ORDER BY t.relname,con.contype,con.conname""")
        constraints = cur.fetchall()
        tables = sorted({row["table_name"] for row in columns})
        counts = {}
        for table in tables:
            cur.execute(f'SELECT count(*) AS n FROM db_pipeline."{table}"')
            counts[table] = cur.fetchone()["n"]
print(json.dumps({"identity": identity, "table_count": len(tables), "tables": tables,
                  "columns": columns, "constraints": constraints, "counts": counts}, ensure_ascii=False, default=str, indent=2))
