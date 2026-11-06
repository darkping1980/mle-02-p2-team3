import json, os
import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
load_dotenv(".env")
with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as conn, conn.cursor(row_factory=dict_row) as cur:
    cur.execute("SELECT current_database() AS db,inet_server_addr()::text AS host,version() AS version")
    identity=cur.fetchone()
    cur.execute("SELECT table_name,table_type FROM information_schema.tables WHERE table_schema='db_pipeline' ORDER BY table_type,table_name")
    rels=cur.fetchall()
    cur.execute("SELECT conrelid::regclass::text AS table,conname,pg_get_constraintdef(oid) AS definition FROM pg_constraint WHERE connamespace='db_pipeline'::regnamespace AND contype='f' ORDER BY 1,2")
    fks=cur.fetchall()
    cur.execute("SELECT table_name,column_name,udt_name,is_nullable FROM information_schema.columns WHERE table_schema='db_pipeline' AND (udt_name IN ('jsonb','json','vector','_text','_varchar','_int4') OR column_name LIKE '%embedding%') ORDER BY table_name,ordinal_position")
    special=cur.fetchall()
    tables=[]
    for rel in rels:
        if rel['table_type']!='BASE TABLE': continue
        name=rel['table_name']
        cur.execute("SELECT a.attname FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum,ord) ON true JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum WHERE n.nspname='db_pipeline' AND c.relname=%s AND i.indisprimary ORDER BY k.ord",(name,))
        pk=[r['attname'] for r in cur.fetchall()]
        cur.execute(f'SELECT count(*) AS n FROM db_pipeline."{name}"')
        tables.append({'name':name,'pk':pk,'rows':cur.fetchone()['n']})
print(json.dumps({'identity':identity,'relations':rels,'tables':tables,'foreign_keys':fks,'json_embedding_columns':special},ensure_ascii=False,indent=2,default=str))
