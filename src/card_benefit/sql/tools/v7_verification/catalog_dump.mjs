// 메모리 PostgreSQL에 SQL 파일을 순서대로 실행해 카탈로그를 JSON으로 저장한다. 실제 DB에 접속하지 않는다.
// 사용법: node catalog_dump.mjs .work/out.json ../../ddl.sql ../../seed.sql ../../desc.sql
import { readFileSync, writeFileSync } from 'node:fs';
import { PGlite } from '@electric-sql/pglite';

const [out, ...files] = process.argv.slice(2);
const db = new PGlite();
for (const f of files) await db.exec(readFileSync(f, 'utf8'));
const q = async (s) => (await db.query(s)).rows;
const res = {
  columns: await q(`select table_name t, column_name c, data_type d, character_maximum_length l, is_nullable n, column_default df, ordinal_position p
                    from information_schema.columns where table_schema='db_pipeline' order by 1,7`),
  constraints: await q(`select conrelid::regclass::text t, conname c, contype::text k, pg_get_constraintdef(oid) d from pg_constraint
                        where connamespace='db_pipeline'::regnamespace and conrelid<>0 order by 1,2`),
  indexes: await q(`select tablename t, indexname i, indexdef d from pg_indexes where schemaname='db_pipeline' order by 1,2`),
  views: await q(`select viewname v, definition d from pg_views where schemaname='db_pipeline' order by 1`),
  functions: await q(`select proname p, pg_get_function_identity_arguments(oid) a, prosrc s from pg_proc where pronamespace='db_pipeline'::regnamespace order by 1`),
  sequences: await q(`select c.relname s from pg_class c where c.relnamespace='db_pipeline'::regnamespace and c.relkind='S' order by 1`),
  comments: await q(`select c.relname t, a.attname c, col_description(c.oid,a.attnum) d from pg_class c join pg_attribute a on a.attrelid=c.oid
                     where c.relnamespace='db_pipeline'::regnamespace and c.relkind='r' and a.attnum>0 and not a.attisdropped order by 1,2`),
};
writeFileSync(out, JSON.stringify(res));
await db.close();
