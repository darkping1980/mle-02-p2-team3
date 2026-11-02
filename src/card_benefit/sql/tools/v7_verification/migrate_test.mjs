// V6 -> V7 -> 롤백 -> V7 재이관을 메모리 PostgreSQL에서 시험한다. 실제 DB에 접속하지 않는다.
// 입력: .work/live_rows.json (export_live_rows.py). 사용법: node migrate_test.mjs live | file
// live는 실제 DB처럼 card_product_doc의 effective_*를 지운 V6, file은 V6 파일 그대로다.
import { readFileSync, writeFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { PGlite } from '@electric-sql/pglite';

const dir = fileURLToPath(new URL('../../', import.meta.url));
const work = fileURLToPath(new URL('.work/', import.meta.url));
// V6 -> V7 이관 파일은 TEXT 단순화 직전 V7에서 멈춘다. DDL과 무결성 시험은 그 시점 파일로 비교한다.
const pinned = new Set(['db_pipeline_schemaV7_draft.sql', 'db_pipeline_v7_integrity_test.sql']);
const show = (n) => {
  const r = spawnSync('git', ['-C', dir, 'show', `bdb94bc:src/card_benefit/sql/${n}`], { encoding: 'utf8', maxBuffer: 1 << 26 });
  if (r.status !== 0) throw Error(r.stderr);
  return r.stdout;
};
const read = (n) => (pinned.has(n) ? show(n) : readFileSync(dir + n, 'utf8'));
const live = JSON.parse(readFileSync(work + 'live_rows.json', 'utf8'));
const shape = process.argv[2] || 'live'; // live: effective_* 없음, file: V6 파일 그대로

const CATALOG = {
  columns: `select table_name t, column_name c, data_type d, character_maximum_length l, is_nullable n, column_default df
            from information_schema.columns where table_schema='db_pipeline' order by 1,ordinal_position`,
  constraints: `select conrelid::regclass::text t, conname c, contype::text k, pg_get_constraintdef(oid) d from pg_constraint
                where connamespace='db_pipeline'::regnamespace and conrelid<>0 order by 1,2`,
  indexes: `select tablename t, indexname i, indexdef d from pg_indexes where schemaname='db_pipeline' order by 1,2`,
  views: `select viewname v, definition d from pg_views where schemaname='db_pipeline' order by 1`,
  functions: `select proname p, pg_get_function_identity_arguments(oid) a, prosrc s from pg_proc where pronamespace='db_pipeline'::regnamespace order by 1`,
  sequences: `select c.relname s from pg_class c where c.relnamespace='db_pipeline'::regnamespace and c.relkind='S' order by 1`,
  comments: `select c.relname t, a.attname c, col_description(c.oid,a.attnum) d from pg_class c join pg_attribute a on a.attrelid=c.oid
             where c.relnamespace='db_pipeline'::regnamespace and c.relkind='r' and a.attnum>0 and not a.attisdropped order by 1,2`,
};
const q = async (db, s, p) => (await db.query(s, p)).rows;
const catalog = async (db) => { const r = {}; for (const [k, s] of Object.entries(CATALOG)) r[k] = await q(db, s); return r; };
const J = (x) => JSON.stringify(x);

function diffCatalog(a, b, ignoreCols = false) {
  const out = [];
  for (const k of Object.keys(CATALOG)) {
    const key = (r) => J(Object.values(r).slice(0, k === 'columns' || k === 'comments' || k === 'constraints' || k === 'indexes' ? 2 : (k === 'functions' ? 2 : 1)));
    const ma = new Map(a[k].map((r) => [key(r), J(r)]));
    const mb = new Map(b[k].map((r) => [key(r), J(r)]));
    for (const [kk, v] of ma) if (!mb.has(kk)) out.push(`${k} only-left ${kk}`); else if (mb.get(kk) !== v) out.push(`${k} changed ${kk}\n   L ${v.slice(0, 260)}\n   R ${mb.get(kk).slice(0, 260)}`);
    for (const kk of mb.keys()) if (!ma.has(kk)) out.push(`${k} only-right ${kk}`);
  }
  return out;
}

const tableRows = async (db) => {
  const names = (await q(db, `select relname from pg_class where relnamespace='db_pipeline'::regnamespace and relkind='r' order by 1`)).map((r) => r.relname);
  const res = {};
  for (const n of names) res[n] = (await q(db, `select to_jsonb(t) j from db_pipeline.${n} t`)).map((r) => r.j);
  return res;
};
const sortRows = (rows) => rows.map((r) => J(Object.keys(r).sort().map((k) => [k, r[k]]))).sort();

// ---- build V6 with live rows
const db = new PGlite();
await db.exec(read('db_pipeline_schemaV6_draft.sql'));
if (shape === 'live') {
  await db.exec(`DROP INDEX db_pipeline.card_product_doc_current_idx;
    ALTER TABLE db_pipeline.card_product_doc DROP CONSTRAINT card_product_doc_period_check;
    ALTER TABLE db_pipeline.card_product_doc DROP CONSTRAINT card_product_doc_approved_check;
    ALTER TABLE db_pipeline.card_product_doc DROP COLUMN effective_from;
    ALTER TABLE db_pipeline.card_product_doc DROP COLUMN effective_to_excl;`);
}
for (const [name, rows] of Object.entries(live.tables)) {
  if (!rows.length) continue;
  await db.query(`insert into db_pipeline.${name} select * from jsonb_populate_recordset(null::db_pipeline.${name}, $1::jsonb)`, [J(rows)]);
}
for (const [s, v] of Object.entries(live.sequences)) if (v) await db.query(`select setval('db_pipeline.${s}', ${v})`);
const before = await tableRows(db);
const beforeCat = await catalog(db);
console.log('V6 loaded', Object.fromEntries(Object.entries(before).map(([k, v]) => [k, v.length]).filter(([, n]) => n)));
const gateBefore = await q(db, `select gate_cd, count(*)::int n from db_pipeline.v_card_integrity_issue group by 1`);
const usageBefore = await q(db, `select common_code_grp_id g, cd_value c, count(*)::int n from db_pipeline.v_common_cd_usage group by 1,2 order by 1,2`);
const atomsBefore = await q(db, `select * from db_pipeline.v_card_cond_atom`);
const rulesBefore = await q(db, `select * from db_pipeline.v_card_rule`);
const tiersBefore = await q(db, `select * from db_pipeline.v_card_limit_tier`);
const poolRefBefore = await q(db, `select * from db_pipeline.v_card_rule_pool`);

// ---- migrate
await db.exec(read('db_pipeline_migration_V6_to_V7.sql'));
const after = await tableRows(db);
const afterCat = await catalog(db);

// fresh V7
const fresh = new PGlite();
for (const f of ['db_pipeline_schemaV7_draft.sql', 'db_pipeline_common_code_seedV7.sql', 'db_pipeline_common_code_descV7.sql']) await fresh.exec(read(f));
const freshCat = await catalog(fresh);
const catDiff = diffCatalog(freshCat, afterCat);
console.log('catalog fresh-V7 vs migrated diffs:', catDiff.length);
catDiff.slice(0, 20).forEach((x) => console.log('  ', x));

// descriptions: migrated == desc file
const dF = await q(fresh, `select common_code_grp_id g, common_cd c, common_cd_nm n, common_cd_desc d from db_pipeline.common_cd order by 1,2`);
const dM = await q(db, `select common_code_grp_id g, common_cd c, common_cd_nm n, common_cd_desc d from db_pipeline.common_cd order by 1,2`);
const gF = await q(fresh, `select common_code_grp_id g, common_code_grp_nm n, common_code_grp_desc d from db_pipeline.common_code_grp order by 1`);
const gM = await q(db, `select common_code_grp_id g, common_code_grp_nm n, common_code_grp_desc d from db_pipeline.common_code_grp order by 1`);
for (let i = 0; i < Math.max(dF.length, dM.length); i++) if (J(dF[i]) !== J(dM[i])) { console.log('code diff', J(dF[i]).slice(0, 160), J(dM[i]).slice(0, 160)); break; }
console.log('codes equal to V7 seed+desc:', J(dF) === J(dM), dM.length, 'desc', dM.filter((r) => r.d).length, 'nulls', dM.filter((r) => !r.d).map((r) => r.g + '.' + r.c));
console.log('groups equal:', J(gF) === J(gM), gM.length, 'desc', gM.filter((r) => r.d).length);

// semantic checks
const eq = (name, a, b) => console.log(name, J(sortRows(a)) === J(sortRows(b)) ? 'SAME' : 'DIFF', a.length, b.length);
const strip = (rows, ...keys) => rows.map((r) => { const c = { ...r }; keys.forEach((k) => delete c[k]); return c; });
const withoutRuleRefs = (rows) => rows.map((r) => ({ ...r, rule_list: r.rule_list.map(({ pool_refs, ...rule }) => rule) }));
eq('card_bnft', withoutRuleRefs(strip(before.card_bnft, 'policy_ver_id')), strip(after.card_bnft, 'bnft_valid_from', 'bnft_valid_to_excl'));
console.log('bnft period all null:', after.card_bnft.every((r) => r.bnft_valid_from === null && r.bnft_valid_to_excl === null));
console.log('stg unchanged, card_id kept:', J(sortRows(before.card_extr_stg)) === J(sortRows(after.card_extr_stg)), after.card_extr_stg.filter((r) => r.card_id === 2).length);
eq('card_limit_pool', strip(before.card_limit_pool, 'policy_ver_id'), after.card_limit_pool);
eq('card_source_evidence', before.card_source_evidence, after.card_source_evidence);
eq('card_evidence_link', strip(before.card_policy_evidence, 'policy_ver_id').map((r) => ({ ...r, ev_subject_cd: r.ev_subject_cd === 'POLICY' ? 'CARD' : r.ev_subject_cd })), after.card_evidence_link);
const pol = before.card_policy_version[0];
const prod = after.card_product[0];
console.log('card_cond_expr equal:', J(sortDeep(pol.policy_cond_expr)) === J(sortDeep(prod.card_cond_expr)), 'status', prod.card_cond_status_cd, 'atoms', prod.card_cond_expr.branches.flatMap((b) => b.atoms).map((a) => a.atom_key + ':' + a.cond_type_cd));
eq('card_product(existing cols)', before.card_product, strip(after.card_product, 'card_cond_expr', 'card_cond_status_cd'));
for (const t of Object.keys(before)) {
  if (['card_bnft', 'card_limit_pool', 'card_policy_evidence', 'card_policy_version', 'card_product', 'common_cd', 'common_code_grp', 'card_bnft_common', 'card_common_bnft', 'card_common_policy_version', 'card_common_rule_evidence', 'card_method_catalog'].includes(t)) continue;
  if (J(sortRows(before[t])) !== J(sortRows(after[t]))) console.log('UNEXPECTED change', t);
}
const atomsAfter = await q(db, `select * from db_pipeline.v_card_cond_atom`);
eq('atoms', strip(atomsBefore, 'policy_ver_id', 'common_bnft_id', 'common_ver_id').map((r) => ({ ...r, owner_cd: r.owner_cd === 'POLICY' ? 'CARD' : r.owner_cd })), atomsAfter);
eq('v_card_rule', strip(rulesBefore, 'policy_ver_id', 'pool_refs'), await q(db, `select * from db_pipeline.v_card_rule`));
eq('v_card_limit_tier', strip(tiersBefore, 'policy_ver_id'), await q(db, `select * from db_pipeline.v_card_limit_tier`));
eq('v_card_rule_pool', strip(poolRefBefore, 'policy_ver_id'), await q(db, `select * from db_pipeline.v_card_rule_pool`));
console.log('gate before', J(gateBefore), 'after', J(await q(db, `select gate_cd, count(*)::int n from db_pipeline.v_card_integrity_issue group by 1`)));
console.log('usage diff', usageDiff(usageBefore, await q(db, `select common_code_grp_id g, cd_value c, count(*)::int n from db_pipeline.v_common_cd_usage group by 1,2 order by 1,2`)));

// negative integrity test
const tableNames = (await q(db, `select relname from pg_class where relnamespace='db_pipeline'::regnamespace and relkind='r'`)).length;
console.log('tables', tableNames, 'views', (await q(db, `select count(*)::int n from pg_views where schemaname='db_pipeline'`))[0].n);
await db.exec(read('db_pipeline_v7_integrity_test.sql')).then(() => console.log('integrity test on migrated: PASS'), async (e) => { console.log('integrity FAIL:', e.message); await db.exec('ROLLBACK'); });
await fresh.exec(read('db_pipeline_v7_integrity_test.sql')).then(() => console.log('integrity test on fresh V7: PASS'), async (e) => { console.log('integrity fresh FAIL:', e.message); await fresh.exec('ROLLBACK'); });
const afterTest = await tableRows(db);
console.log('integrity test left no rows:', J(after) === J(afterTest));

// multi-policy guard (separate copy)
writeFileSync(`${work}migrated_${shape}.json`, J(after));

// rollback must stop while V7-only data exists
await db.exec(`UPDATE db_pipeline.card_extr_stg SET card_id = NULL WHERE card_extr_stg_id = (SELECT min(card_extr_stg_id) FROM db_pipeline.card_extr_stg)`);
await db.exec(read('db_pipeline_migration_V7_to_V6_rollback.sql')).then(() => console.log('rollback guard FAILED'), async (e) => { console.log('rollback guard:', e.message); await db.exec('ROLLBACK'); });
await db.exec(`UPDATE db_pipeline.card_extr_stg SET card_id = 2 WHERE card_id IS NULL`);

// ---- rollback
await db.exec(read('db_pipeline_migration_V7_to_V6_rollback.sql'));
const back = await tableRows(db);
const backCat = await catalog(db);
for (const t of Object.keys(before)) {
  const a = J(sortRows(before[t])), b = J(sortRows((back[t] || [])));
  if (a !== b) console.log('ROLLBACK data diff', t, (back[t] || []).length);
}
const bd = diffCatalog(beforeCat, backCat);
console.log('rollback catalog diffs:', bd.length); bd.slice(0, 25).forEach((x) => console.log('  ', x.slice(0, 330)));
console.log('rollback seq', (await q(db, `select last_value from db_pipeline.seq_card_policy_version`))[0], (await q(db, `select last_value from db_pipeline.seq_card_policy_evidence`))[0]);
console.log('backup schema gone:', (await q(db, `select count(*)::int n from pg_namespace where nspname='db_pipeline_v6_backup'`))[0].n === 0);

// ---- re-migrate after rollback, then guard tests on a V6 copy
await db.exec(read('db_pipeline_migration_V6_to_V7.sql'));
console.log('re-migrate after rollback: OK');
await db.close(); await fresh.close();

const g = new PGlite();
await g.exec(read('db_pipeline_schemaV6_draft.sql'));
for (const [name, rows] of Object.entries(live.tables)) {
  if (rows.length && name !== 'card_product_doc') await g.query(`insert into db_pipeline.${name} select * from jsonb_populate_recordset(null::db_pipeline.${name}, $1::jsonb)`, [J(rows)]);
}
await g.exec(`INSERT INTO db_pipeline.card_policy_version (card_id, policy_ver_id, policy_ver_no, valid_from, policy_status_cd) VALUES (2,'P2',2,'2027-01-01','DRAFT')`);
await g.exec(read('db_pipeline_migration_V6_to_V7.sql')).then(() => console.log('multi-policy guard FAILED'), async (e) => { console.log('multi-policy guard:', e.message); await g.exec('ROLLBACK'); });
console.log('policy table still there:', (await q(g, `select count(*)::int n from db_pipeline.card_policy_version`))[0].n, 'bnft policy col kept:', (await q(g, `select count(*)::int n from information_schema.columns where table_name='card_bnft' and column_name='policy_ver_id'`))[0].n);
await g.exec(`DELETE FROM db_pipeline.card_policy_version WHERE policy_ver_id='P2'`);
await g.exec(`INSERT INTO db_pipeline.card_common_bnft (common_bnft_id, provider_cd, common_bnft_cd, common_bnft_nm) VALUES ('C1','VISA','C1','시험')`);
await g.exec(read('db_pipeline_migration_V6_to_V7.sql')).then(() => console.log('common guard FAILED'), async (e) => { console.log('common guard:', e.message); await g.exec('ROLLBACK'); });
console.log('common row kept:', (await q(g, `select count(*)::int n from db_pipeline.card_common_bnft`))[0].n);
await g.exec(`DELETE FROM db_pipeline.card_common_bnft`);
await g.query(`insert into db_pipeline.card_product_doc select * from jsonb_populate_recordset(null::db_pipeline.card_product_doc, $1::jsonb)`, [J(live.tables.card_product_doc)]);
await g.exec(`INSERT INTO db_pipeline.card_method_catalog VALUES ('CALC','UNITS_PER_AMOUNT',1,'{}','REAL_HANDLER','ACTIVE')`);
await g.exec(read('db_pipeline_migration_V6_to_V7.sql')).then(() => console.log('catalog guard FAILED'), async (e) => { console.log('catalog guard:', e.message); await g.exec('ROLLBACK'); });
console.log('catalog rows kept:', (await q(g, `select count(*)::int n from db_pipeline.card_method_catalog`))[0].n);
await g.exec(`DELETE FROM db_pipeline.card_method_catalog WHERE handler_key='REAL_HANDLER'`);
await g.exec(`DELETE FROM db_pipeline.card_product_doc`);
await g.exec(read('db_pipeline_migration_V6_to_V7.sql')).then(() => console.log('doc guard FAILED'), async (e) => { console.log('doc guard:', e.message); await g.exec('ROLLBACK'); });
await g.close();

function sortDeep(x) {
  if (Array.isArray(x)) return x.map(sortDeep);
  if (x && typeof x === 'object') return Object.keys(x).sort().map((k) => [k, sortDeep(x[k])]);
  return x;
}
function usageDiff(a, b) {
  const s = (r) => J(r);
  const A = new Set(a.map(s)), B = new Set(b.map(s));
  return { only_before: a.filter((r) => !B.has(s(r))), only_after: b.filter((r) => !A.has(s(r))) };
}
