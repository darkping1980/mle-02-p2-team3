// TEXT 단순화 이관을 메모리 PostgreSQL에서 시험한다. 실제 DB에 접속하지 않는다.
// 사용법: node verify_bnft_text.mjs            합성 데이터
//         node verify_bnft_text.mjs real       .work/simplify_rows.json (export_simplify_rows.py 결과)
// 합격 기준: 사전 검증 전부 PASS, 가드 음성 시험 전부 중단, 새 V7과 카탈로그 차이 0,
// 재실행 수렴, 복구 후 이전 구조·데이터와 차이 0, 복구 재실행과 재이관 성공.
import { readFileSync, existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { PGlite } from '@electric-sql/pglite';

const repo = fileURLToPath(new URL('../../../../../', import.meta.url));
const sql = fileURLToPath(new URL('../../', import.meta.url));
const read = (n) => readFileSync(sql + n, 'utf8');
const J = (x) => JSON.stringify(x);
const mode = process.argv[2] || 'synthetic';
const BASE = 'bdb94bc'; // TEXT 단순화 직전 V7
const oldDdl = spawnSync('git', ['-C', repo, 'show', `${BASE}:src/card_benefit/sql/db_pipeline_schemaV7_draft.sql`], { encoding: 'utf8', maxBuffer: 1 << 26 });
if (oldDdl.status !== 0) throw Error(oldDdl.stderr);
const [PRE, MIG, RB, POST] = ['db_pipeline_v7_bnft_text_precheck.sql', 'db_pipeline_migration_v7_bnft_text.sql',
  'db_pipeline_migration_v7_bnft_text_rollback.sql', 'db_pipeline_v7_bnft_text_postcheck.sql'].map(read);
const q = async (db, s, p) => (await db.query(s, p)).rows;
const COLS = 'card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl';

function syntheticRows() {
  const rule = (k) => ({ rule_key: k, calc_method_cd: 'FREE_SERVICE', payout_unit_cd: 'SERVICE', rule_status_cd: 'DRAFT', method_ver: 1, predicate_state_cd: 'PENDING_REVIEW', target_list: [] });
  const quoteSeg = (id, quote) => ({ evidence_id: id, card_doc_id: 'D1', page_no: 1, card_doc_chunk_id: 'C1', quote_txt: quote, approval_status_cd: 'PENDING' });
  return { tables: {
    card_product: [{ card_id: 91, product_cd: 'T', product_nm: 'test', issuer: 'i', card_kind_cd: 'CREDIT', create_user_id: 'T', update_user_id: 'T', product_status_cd: 'ACTIVE', brand_opt_list: [], card_cond_status_cd: 'DRAFT' }],
    card_bnft: [{ card_id: 91, card_bnft_id: 'B1', bnft_cd: 'B1', bnft_nm: 'b', bnft_type_cd: 'SERVICE', bnft_origin_cd: 'LOCAL', bnft_scope_cd: 'PRODUCT', rule_list: [rule('R1'), rule('R2')], relation_list: [], verification_status_cd: 'PENDING_REVIEW', bnft_rule_txt: '발레 무료', bnft_limit_txt: '월 5천원 / 일 1회' },
                 { card_id: 91, card_bnft_id: 'B2', bnft_cd: 'B2', bnft_nm: 'c', bnft_type_cd: 'SERVICE', bnft_origin_cd: 'LOCAL', bnft_scope_cd: 'PRODUCT', rule_list: [], relation_list: [], verification_status_cd: 'PENDING_REVIEW' }],
    card_limit_pool: [{ card_id: 91, pool_id: 'P1', pool_scope_cd: 'BENEFIT', period_cd: 'MONTH', cap_unit_cd: 'KRW', aggregation_key_cd: 'CARD_MEMBER', tier_list: [{ tier_key: 'T1', predicate_state_cd: 'PENDING_REVIEW', limit_num: 5000 }] },
                      { card_id: 91, pool_id: 'P2', pool_scope_cd: 'BENEFIT', period_cd: 'DAY', cap_unit_cd: 'COUNT', aggregation_key_cd: 'CARD_MEMBER', tier_list: [{ tier_key: 'T2', predicate_state_cd: 'PENDING_REVIEW', limit_num: 1 }] }],
    card_bnft_rule_pool: [['R1', 'P1'], ['R1', 'P2'], ['R2', 'P1'], ['R2', 'P2']].map(([r, p]) => ({ card_id: 91, card_bnft_id: 'B1', rule_key: r, pool_id: p, pool_role_cd: 'CONSUME' })),
    card_source_evidence: [quoteSeg('E1', '발레 무료'), quoteSeg('E2', '월 5천원\n/ 일 1회')],
    card_evidence_link: [
      { card_id: 91, ev_link_id: 'L1', ev_subject_cd: 'BNFT', card_bnft_id: 'B1', ev_item_cd: 'SELF', ev_item_key: '-', evidence_id: 'E1' },
      { card_id: 91, ev_link_id: 'L2', ev_subject_cd: 'BNFT', card_bnft_id: 'B1', ev_item_cd: 'SELF', ev_item_key: '-', evidence_id: 'E2' },
      { card_id: 91, ev_link_id: 'L3', ev_subject_cd: 'POOL', pool_id: 'P1', ev_item_cd: 'SELF', ev_item_key: '-', evidence_id: 'E2' },
      { card_id: 91, ev_link_id: 'L4', ev_subject_cd: 'POOL', pool_id: 'P2', ev_item_cd: 'SELF', ev_item_key: '-', evidence_id: 'E2' }],
    card_doc: [{ card_doc_id: 'D1', card_id: 91, doc_cd: 'D1', doc_title: 't', doc_file_nm: 'x.pdf', doc_sha256: 'a'.repeat(64), doc_collect_date: '2026-01-01T00:00:00Z', create_user_id: 'T', update_user_id: 'T' }],
    card_product_doc: [{ card_id: 91, card_doc_id: 'D1', doc_role_cd: 'PRODUCT_GUIDE', approval_status_cd: 'PENDING', applicability_basis_txt: 'x', create_user_id: 'T', update_user_id: 'T' }],
    card_doc_page: [], card_doc_chunk: [{ card_doc_id: 'D1', page_no: 1, card_doc_chunk_id: 'C1', chunk_seq: 1, chunk_start_pos: 1, chunk_end_pos: 9, chunk_raw_txt: '발레 무료 월 5천원', chunk_split_rule_ver: 'V', create_user_id: 'T', update_user_id: 'T' }],
  }, sequences: { seq_card_limit_pool: [11, true] } };
}

async function load(db, rows) {
  await db.exec(`ALTER TABLE db_pipeline.card_bnft ADD COLUMN bnft_rule_txt text; ALTER TABLE db_pipeline.card_bnft ADD COLUMN bnft_limit_txt text;
    COMMENT ON COLUMN db_pipeline.card_bnft.bnft_rule_txt IS '공식 원문 근거에서 모은 혜택 계산 규칙 안내. 계산 확정값이 아니라 검토 대상 텍스트';
    COMMENT ON COLUMN db_pipeline.card_bnft.bnft_limit_txt IS '원문 근거에서 모은 혜택별 이용/금액 한도. 여러 풀의 근거를 혜택별로 중복 제거한 텍스트';
    DELETE FROM db_pipeline.common_cd; DELETE FROM db_pipeline.common_code_grp;`);
  await db.exec(read('db_pipeline_common_code_seedV7.sql'));
  await db.exec(read('db_pipeline_common_code_descV7.sql'));
  for (const [name, list] of Object.entries(rows.tables)) {
    if (!list.length || ['common_cd', 'common_code_grp'].includes(name)) continue;
    // 입력에 없는 컬럼은 기본값을 쓰도록 목록에서 뺀다.
    const present = [...new Set(list.flatMap((row) => Object.keys(row)))];
    const cols = (await q(db, `select string_agg(quote_ident(column_name), ',') c from information_schema.columns
      where table_schema='db_pipeline' and table_name=$1 and is_generated='NEVER' and column_name = any($2::text[])`, [name, present]))[0].c;
    await db.query(`insert into db_pipeline.${name} (${cols}) select ${cols} from jsonb_populate_recordset(null::db_pipeline.${name}, $1::jsonb)`, [J(list)]);
  }
  for (const [s, v] of Object.entries(rows.sequences)) await db.query(`select setval('db_pipeline.${s}', $1, $2)`, [v[0], v[1]]);
  await db.exec(`CREATE SCHEMA IF NOT EXISTS db_pipeline_backup;
    CREATE TABLE db_pipeline_backup.card_limit_pool_20261102 AS SELECT * FROM db_pipeline.card_limit_pool;
    CREATE TABLE db_pipeline_backup.card_bnft_rule_pool_20261102 AS SELECT * FROM db_pipeline.card_bnft_rule_pool;
    CREATE TABLE db_pipeline_backup.card_evidence_link_pre_simplify_20261102 AS SELECT * FROM db_pipeline.card_evidence_link;
    CREATE TABLE db_pipeline_backup.card_bnft_pre_simplify_20261102 AS SELECT ${COLS} FROM db_pipeline.card_bnft;`);
}

const CATALOG = {
  columns: `select table_name t, column_name c, data_type d, character_maximum_length l, is_nullable n, column_default df from information_schema.columns where table_schema='db_pipeline' order by 1,2`,
  constraints: `select conrelid::regclass::text t, conname c, contype::text k, pg_get_constraintdef(oid) d from pg_constraint where connamespace='db_pipeline'::regnamespace and conrelid<>0 order by 1,2`,
  indexes: `select tablename t, indexname i, indexdef d from pg_indexes where schemaname='db_pipeline' order by 1,2`,
  views: `select viewname v, definition d from pg_views where schemaname='db_pipeline' order by 1`,
  view_comments: `select c.relname v, obj_description(c.oid) d from pg_class c where c.relnamespace='db_pipeline'::regnamespace and c.relkind='v' order by 1`,
  functions: `select proname p, pg_get_function_identity_arguments(oid) a, prosrc s, obj_description(oid) d from pg_proc where pronamespace='db_pipeline'::regnamespace order by 1`,
  sequences: `select c.relname s, obj_description(c.oid) d from pg_class c where c.relnamespace='db_pipeline'::regnamespace and c.relkind='S' order by 1`,
  comments: `select c.relname t, a.attname c, col_description(c.oid,a.attnum) d from pg_class c join pg_attribute a on a.attrelid=c.oid where c.relnamespace='db_pipeline'::regnamespace and c.relkind='r' and a.attnum>0 and not a.attisdropped order by 1,2`,
};
const catalog = async (db) => { const r = {}; for (const [k, s] of Object.entries(CATALOG)) r[k] = await q(db, s); return r; };
function catDiff(a, b) {
  const out = [];
  for (const k of Object.keys(a)) {
    const A = new Set(a[k].map(J)), B = new Set(b[k].map(J));
    for (const x of A) if (!B.has(x)) out.push(`${k} L ${x.slice(0, 220)}`);
    for (const x of B) if (!A.has(x)) out.push(`${k} R ${x.slice(0, 220)}`);
  }
  return out;
}
const tables = async (db) => {
  const res = {};
  for (const { relname: n } of await q(db, `select relname from pg_class where relnamespace='db_pipeline'::regnamespace and relkind='r' order by 1`))
    res[n] = (await q(db, `select to_jsonb(t) j from db_pipeline.${n} t`)).map((r) => J(Object.keys(r.j).sort().map((k) => [k, r.j[k]]))).sort();
  return res;
};
const ok = (cond, msg) => { if (!cond) throw Error('FAIL: ' + msg); console.log('PASS', msg); };
const expectAbort = async (db, fragment, label) => {
  let message = null;
  await db.exec(MIG).catch((e) => { message = e.message; });
  await db.exec('ROLLBACK').catch(() => {});
  if (!message || !message.includes(fragment)) throw Error(`guard ${label}: expected ${fragment}, got ${message}`);
  console.log('PASS guard', label, '->', message.slice(0, 110));
};
const precheck = async (db) => {
  await db.exec('BEGIN');
  const sets = await db.exec(PRE);
  await db.exec('ROLLBACK');
  return sets.filter((s) => s.rows?.length);
};

if (mode === 'real' && !existsSync(new URL('.work/simplify_rows.json', import.meta.url))) throw Error('run export_simplify_rows.py first');
const rows = mode === 'real' ? JSON.parse(readFileSync(new URL('.work/simplify_rows.json', import.meta.url), 'utf8')) : syntheticRows();
const fresh = async () => { const d = new PGlite(); await d.exec(oldDdl.stdout); await load(d, rows); return d; };

// ---- 사전 검증
const db = await fresh();
const [checks, table, pool] = await precheck(db);
const failed = checks.rows.filter((r) => r.result !== 'PASS');
if (failed.length) console.log(failed);
ok(!failed.length, `precheck ${checks.rows.length} rows, ${failed.length} failed`);
console.table(table.rows.map(({ card_bnft_id, pool_values, bnft_limit_txt }) => ({ card_bnft_id, pool_values, bnft_limit_txt })));
console.log('POOL evidence', pool.rows[0]);
let beforeCat = await catalog(db), beforeRows = await tables(db);
const gatesBefore = await q(db, `select gate_cd, count(*)::int n from db_pipeline.v_card_integrity_issue group by 1 order by 1`);

// ---- 가드 음성 시험: 각 위반이 자기 항목으로 중단되고 아무것도 바뀌지 않아야 한다.
const b0 = (await q(db, `select card_bnft_id, bnft_limit_txt, bnft_rule_txt from db_pipeline.card_bnft where bnft_limit_txt is not null order by 1 limit 1`))[0];
const firstLink = (await q(db, `select l.ev_link_id, l.pool_id from db_pipeline.card_evidence_link l where ev_subject_cd='POOL' order by 1 limit 1`))[0];
const guards = [
  ['T01', `UPDATE db_pipeline.card_bnft SET bnft_limit_txt=NULL WHERE card_bnft_id='${b0.card_bnft_id}'`],
  ['T02', `UPDATE db_pipeline.card_bnft SET bnft_rule_txt=NULL WHERE card_bnft_id='${b0.card_bnft_id}'`],
  ['T03', `UPDATE db_pipeline.card_bnft SET bnft_limit_txt='발레 무료' WHERE card_bnft_id='${b0.card_bnft_id}'`],
  ['T04', `UPDATE db_pipeline.card_bnft SET bnft_limit_txt=bnft_limit_txt||' / 원문에없는값' WHERE card_bnft_id='${b0.card_bnft_id}'`],
  ['E01', `DELETE FROM db_pipeline.card_evidence_link WHERE ev_subject_cd='BNFT' AND card_bnft_id='${b0.card_bnft_id}' AND evidence_id=(SELECT evidence_id FROM db_pipeline.card_evidence_link WHERE ev_link_id='${firstLink.ev_link_id}')`],
  ['B01', `UPDATE db_pipeline.card_limit_pool SET period_cd='YEAR' WHERE pool_id='${firstLink.pool_id}'`],
  ['B02', `DELETE FROM db_pipeline.card_bnft_rule_pool WHERE pool_id='${firstLink.pool_id}'`],
  ['B04', `UPDATE db_pipeline.card_bnft SET verification_status_cd='CONFIRMED' WHERE card_bnft_id='${b0.card_bnft_id}'`],
];
for (const [code, change] of guards) {
  await db.exec('BEGIN'); await db.exec(change); await db.exec('COMMIT');
  await expectAbort(db, code + '(', code);
  await db.exec(`DROP SCHEMA db_pipeline CASCADE; DROP SCHEMA db_pipeline_backup CASCADE;`);
  await db.exec(oldDdl.stdout); await load(db, rows);
}
// 재구성하면 시드의 create_date가 새로 찍히므로 기준선을 다시 잡는다.
beforeCat = await catalog(db); beforeRows = await tables(db);
await db.exec(`ALTER TABLE db_pipeline_backup.card_limit_pool_20261102 RENAME TO x`);
await expectAbort(db, '백업이 없어', 'missing backup');
await db.exec(`ALTER TABLE db_pipeline_backup.x RENAME TO card_limit_pool_20261102`);
ok(J(await tables(db)) === J(beforeRows), 'aborted migration left rows unchanged');

// ---- 이관
await db.exec(MIG);
const after = await catalog(db), afterRows = await tables(db);
const target = new PGlite();
for (const f of ['db_pipeline_schemaV7_draft.sql', 'db_pipeline_common_code_seedV7.sql', 'db_pipeline_common_code_descV7.sql']) await target.exec(read(f));
const cd = catDiff(await catalog(target), after);
cd.slice(0, 20).forEach((x) => console.log('  ', x));
ok(cd.length === 0, 'migrated catalog equals fresh V7');
ok(!afterRows.card_limit_pool && !afterRows.card_bnft_rule_pool, 'both tables dropped');
const poolCount = beforeRows.card_evidence_link.filter((x) => x.includes('"POOL"')).length;
ok(afterRows.card_evidence_link.length === beforeRows.card_evidence_link.length - poolCount, `links ${beforeRows.card_evidence_link.length} -> ${afterRows.card_evidence_link.length}`);
for (const t of Object.keys(afterRows)) if (t !== 'card_evidence_link') ok(J(afterRows[t]) === J(beforeRows[t]), `unchanged ${t} (${afterRows[t].length})`);
const gatesAfter = await q(db, `select gate_cd, count(*)::int n from db_pipeline.v_card_integrity_issue group by 1 order by 1`);
console.log('gates', J(gatesBefore), '->', J(gatesAfter));
ok(J(gatesBefore) === J(gatesAfter), 'gate result unchanged');
if (mode === 'real') {
  await db.exec('BEGIN');
  const postSets = (await db.exec(POST)).filter((s) => s.rows?.length);
  await db.exec('ROLLBACK');
  const bad = postSets[0].rows.filter((r) => r.result !== 'PASS');
  if (bad.length) console.log(bad);
  ok(!bad.length, `postcheck ${postSets[0].rows.length} rows`);
}
// 새 구조가 제거된 값을 거부한다.
await db.query(`SELECT 1`);
for (const [label, s] of [['POOL subject', `INSERT INTO db_pipeline.card_evidence_link(card_id,ev_link_id,ev_subject_cd,evidence_id) VALUES (1,'Z','POOL','E')`]]) {
  let code = null; await db.exec(s).catch((e) => { code = e.code; });
  ok(code === '23514', `reject ${label}`);
}
ok((await q(db, `select db_pipeline.fn_valid_relation_list('[{"relation_key":"r","to_bnft_id":"x","rel_type_cd":"FALLBACK_AFTER_CAP","trigger_pool_id":"P"}]','y') v`))[0].v === false, 'trigger_pool_id rejected');
ok((await q(db, `select db_pipeline.fn_valid_relation_list('[{"relation_key":"r","to_bnft_id":"x","rel_type_cd":"FALLBACK_AFTER_CAP"}]','y') v`))[0].v === true, 'fallback without pool accepted');

// ---- 재실행
await db.exec(MIG);
ok(catDiff(after, await catalog(db)).length === 0 && J(afterRows) === J(await tables(db)), 'migration rerun converges');

// ---- 복구
await db.exec(RB);
const backCat = await catalog(db), backRows = await tables(db);
const bd = catDiff(beforeCat, backCat);
bd.slice(0, 20).forEach((x) => console.log('  ', x));
ok(bd.length === 0, 'rollback catalog equals pre-migration');
ok(J(backRows) === J(beforeRows), 'rollback rows equal pre-migration');
const seq = rows.sequences.seq_card_limit_pool;
ok(J(await q(db, `select last_value::int, is_called from db_pipeline.seq_card_limit_pool`)) === J([{ last_value: seq[0], is_called: seq[1] }]), 'sequence restored');
await db.exec(RB);
ok(J(await tables(db)) === J(beforeRows), 'rollback rerun converges');
ok(!(await precheck(db))[0].rows.some((r) => r.result !== 'PASS'), 'precheck passes after rollback');

// ---- 재이관
await db.exec(MIG);
ok(catDiff(after, await catalog(db)).length === 0 && J(afterRows) === J(await tables(db)), 're-migration after rollback');

// ---- 복구 가드
await db.exec(`UPDATE db_pipeline.card_bnft SET relation_list='[{"relation_key":"r","to_bnft_id":"zz","rel_type_cd":"FALLBACK_AFTER_CAP"}]' WHERE card_bnft_id='${b0.card_bnft_id}'`);
let rbMessage = null; await db.exec(RB).catch((e) => { rbMessage = e.message; }); await db.exec('ROLLBACK').catch(() => {});
ok(rbMessage?.includes('FALLBACK_AFTER_CAP'), 'rollback stops on fallback relation');
await db.close(); await target.close();
console.log(`verify_bnft_text ${mode}: ALL PASS`);
