// 계산 구조 정리 SQL 격리 시험(PGlite, 실제 DB 접속 없음).
// 기준 DB = V7 DDL + 실제 DB의 함수·뷰 정의 + 실제 데이터 백업. 정리 → 검증 → 복구 → 검증.
import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
const root = process.argv[2];
const sqlDir = `${root}/src/card_benefit/sql`;
const { PGlite } = await import(pathToFileURL(`${sqlDir}/tools/v7_verification/node_modules/@electric-sql/pglite/dist/index.js`).href);
const cat = JSON.parse(readFileSync(`${root}/src/card_benefit/docs/schema_cleanup/pre_cleanup_catalog.json`, 'utf8'));
const backup = JSON.parse(readFileSync(`${root}/src/data/backup/pre_calc_cleanup_20261103/postgres_db_pipeline.json`, 'utf8'));
const CLEANUP = readFileSync(`${sqlDir}/db_pipeline_calc_structure_cleanup.sql`, 'utf8');
const ROLLBACK = readFileSync(`${sqlDir}/db_pipeline_calc_structure_cleanup_rollback.sql`, 'utf8');
const results = [];
const expect = (name, ok, detail = '') => results.push({ name, ok: !!ok, detail });
const VIEW_ORDER = ['v_card_rule', 'v_card_bnft_rule_effective', 'v_card_cond_atom', 'v_card_rule_target', 'v_card_bnft_rel', 'v_card_brand_opt', 'v_common_cd_usage', 'v_card_integrity_issue'];
const REMOVED_GATES = ['rule_method_value_missing', 'rule_method_value_pending', 'predicate_params_missing', 'predicate_params_pending', 'excl_item_unknown'];

const db = new PGlite();
await db.exec(readFileSync(`${sqlDir}/db_pipeline_schemaV7_draft.sql`, 'utf8'));
for (const v of [...VIEW_ORDER].reverse()) await db.exec(`DROP VIEW IF EXISTS db_pipeline.${v}`);
// 실제 DB 함수로 맞춘다(fn_cond_spend_bound 포함)
for (const [name, def] of Object.entries(cat.functions)) await db.exec(def.replace('CREATE OR REPLACE FUNCTION', 'CREATE OR REPLACE FUNCTION') + ';');
// 실제 DB에만 있는 테이블·컬럼을 맞춘다(시험 전용: vector는 text)
const liveCols = {};
for (const [t, pos, col, type, nullable] of cat.columns) (liveCols[t] ??= []).push({ col, type: /USER-DEFINED|vector/.test(type) ? 'text' : type === 'ARRAY' ? 'text[]' : type });
for (const [t, cols] of Object.entries(liveCols)) {
  const exists = (await db.query(`SELECT to_regclass('db_pipeline.${t}') AS r`)).rows[0].r;
  if (!exists) { await db.exec(`CREATE TABLE db_pipeline.${t} (${cols.map((c) => `${c.col} ${c.type}`).join(', ')})`); continue; }
  const have = new Set((await db.query(`SELECT column_name FROM information_schema.columns WHERE table_schema='db_pipeline' AND table_name=$1`, [t])).rows.map((r) => r.column_name));
  for (const c of cols) if (!have.has(c.col)) await db.exec(`ALTER TABLE db_pipeline.${t} ADD COLUMN ${c.col} ${c.type}`);
}
// 실제 DB 인덱스(card_excl_item 개념 인덱스 등) 중 없는 것을 만든다
for (const [t, name, def] of cat.indexes) {
  const exists = (await db.query(`SELECT to_regclass('db_pipeline.${name}') AS r`)).rows[0].r;
  if (!exists && !/UNIQUE/.test(def)) await db.exec(def);
}
await db.exec(`SET search_path = pg_catalog;`);
for (const v of VIEW_ORDER) await db.exec(`CREATE VIEW db_pipeline.${v} AS ${cat.views[v].replace(/;\s*$/, '')}; COMMENT ON VIEW db_pipeline.${v} IS '${cat.view_comments[v].replace(/'/g, "''")}';`);
await db.exec(`RESET search_path;`);
// 데이터 적재(제약 검증 포함). 실제 값이 V7 CHECK를 통과해야 한다.
await db.exec(`SET session_replication_role = replica;`);   // 시퀀스 기본값 함수 등 트리거 없음, CHECK는 그대로 동작
for (const [t, v] of Object.entries(backup.tables)) {
  if (!v.rows.length) continue;
  await db.query(`INSERT INTO db_pipeline.${t} SELECT * FROM jsonb_populate_recordset(NULL::db_pipeline.${t}, $1::jsonb)`, [JSON.stringify(v.rows)]);
}
await db.exec(`SET session_replication_role = origin;`);

const one = async (q, p) => (await db.query(q, p)).rows;
const counts = async () => Object.fromEntries((await one(`SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='db_pipeline' AND relkind='r' ORDER BY 1`))
  .map((r) => r.relname).filter((t) => !['card_excl_item', 'common_cd', 'common_code_grp'].includes(t)).map((t) => [t, null])) ;
async function tableState() {
  const out = {};
  for (const t of Object.keys(await counts())) {
    const cols = (await one(`SELECT column_name FROM information_schema.columns WHERE table_schema='db_pipeline' AND table_name=$1 AND column_name NOT IN ('rule_select_cd','card_excl_item_id','rule_list','bnft_cond_expr','card_cond_expr') ORDER BY 1`, [t])).map((r) => r.column_name);
    out[t] = (await one(`SELECT count(*)::int n, md5(coalesce(string_agg(md5(row(${cols.join(',')})::text), ',' ORDER BY md5(row(${cols.join(',')})::text)), '')) f FROM db_pipeline.${t}`))[0];
  }
  return out;
}
const gates = async (exclude = []) => (await one(`SELECT gate_cd, issue_key FROM db_pipeline.v_card_integrity_issue ORDER BY 1,2`)).filter((r) => !exclude.includes(r.gate_cd)).map((r) => `${r.gate_cd}|${r.issue_key}`).join('\n');
const defs = async () => ({
  views: Object.fromEntries((await one(`SELECT c.relname, pg_get_viewdef(c.oid) d, obj_description(c.oid,'pg_class') cm FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='db_pipeline' AND relkind='v'`)).map((r) => [r.relname, r.d + '|' + r.cm])),
  indexes: (await one(`SELECT string_agg(indexdef, E'
' ORDER BY indexname) d FROM pg_indexes WHERE schemaname='db_pipeline'`))[0].d,
  funcs: Object.fromEntries((await one(`SELECT p.proname, pg_get_functiondef(p.oid) d FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='db_pipeline'`)).map((r) => [r.proname, r.d])),
});
const jsonState = async () => (await one(`SELECT md5(string_agg(card_id||card_bnft_id||rule_list::text||coalesce(bnft_cond_expr::text,''), ',' ORDER BY card_id, card_bnft_id)) b FROM db_pipeline.card_bnft`))[0].b
  + '/' + (await one(`SELECT md5(string_agg(card_id||coalesce(card_cond_expr::text,''), ',' ORDER BY card_id)) p FROM db_pipeline.card_product`))[0].p;
const codeState = async () => (await one(`SELECT (SELECT count(*)::int FROM db_pipeline.common_cd) cd, (SELECT count(*)::int FROM db_pipeline.common_code_grp) grp`))[0];

const before = { tables: await tableState(), gatesKept: await gates(REMOVED_GATES), gatesAll: await gates(), defs: await defs(), json: await jsonState(), codes: await codeState(), rules: (await one(`SELECT count(*)::int n FROM db_pipeline.card_bnft b, jsonb_array_elements(b.rule_list) r`))[0].n };
expect('기준 DB: 실제 데이터 적재·현재 정의 동작', Object.values(before.tables).every((s) => s.n >= 0) && before.gatesAll.length > 0, `card_bnft=${before.tables.card_bnft.n} evidence=${before.tables.card_source_evidence.n}`);

// ---- 정리 실행 ----
let err = null;
try { await db.exec(CLEANUP); } catch (e) { err = e.message; await db.exec('ROLLBACK').catch(() => {}); }
expect('정리 SQL 실행 성공', !err, err || '');
if (!err) {
  const after = { tables: await tableState(), gates: await gates(), defs: await defs(), codes: await codeState() };
  expect('테이블 행·값 유지(계산 컬럼 제외)', JSON.stringify(after.tables) === JSON.stringify(before.tables));
  expect('남은 정합성 게이트 결과 동일', after.gates === before.gatesKept, `${after.gates.split('\n').length} rows`);
  const gone = ['v_card_bnft_rule_effective', 'fn_cond_spend_bound', 'card_excl_item'];
  const objs = (await one(`SELECT relname n FROM pg_class c JOIN pg_namespace s ON s.oid=c.relnamespace WHERE s.nspname='db_pipeline' UNION SELECT proname FROM pg_proc p JOIN pg_namespace s ON s.oid=p.pronamespace WHERE s.nspname='db_pipeline'`)).map((r) => r.n);
  expect('삭제 대상 객체 제거', gone.every((g) => !objs.includes(g)), gone.filter((g) => objs.includes(g)).join(','));
  const cols = (await one(`SELECT table_name||'.'||column_name c FROM information_schema.columns WHERE table_schema='db_pipeline' AND column_name IN ('rule_select_cd','card_excl_item_id','predicate_state_cd','method_ver','calc_params','rule_priority','spend_min_amt','predicate_method_cd','cond_params','link_role_cd','calc_method_cd','payout_unit_cd','basis_amt')`)).map((r) => r.c);
  expect('삭제 대상 컬럼 제거(테이블·뷰)', cols.length === 0, cols.join(','));
  const keys = (await one(`SELECT count(*)::int n FROM db_pipeline.card_bnft b, jsonb_array_elements(b.rule_list) r WHERE r.value ?| ARRAY['predicate_state_cd','method_ver','calc_params','rule_priority','calc_method_cd','payout_unit_cd','basis_amt']`))[0].n;
  const kept = (await one(`SELECT count(*)::int n FROM db_pipeline.card_bnft b, jsonb_array_elements(b.rule_list) r WHERE r.value ?& ARRAY['rule_key','value_num','value_unit_cd','target_list','rule_status_cd']`))[0].n;
  expect('규칙 JSON: 계산 키만 제거, 값·단위·대상·상태 유지', keys === 0 && kept === before.rules, `removed-left=${keys} kept=${kept}`);
  expect('공통코드 10그룹·32코드 제거', after.codes.grp === before.codes.grp - 10 && after.codes.cd === before.codes.cd - 32, JSON.stringify(after.codes));
  // 계산 단위가 UNKNOWN이거나 없는 규칙도 새 계약을 통과한다
  const unknown = (await one(`SELECT db_pipeline.fn_valid_rule_list('[{"rule_key":"r1","rule_status_cd":"DRAFT","value_num":null,"value_unit_cd":null,"target_list":[]},{"rule_key":"r2","rule_status_cd":"DRAFT"}]'::jsonb,'LOCAL') ok`))[0].ok;
  const stillBad = (await one(`SELECT db_pipeline.fn_valid_rule_list('[{"rule_key":"bad key!","rule_status_cd":"DRAFT"}]'::jsonb,'LOCAL') a, db_pipeline.fn_valid_rule_list('[{"rule_key":"r1"}]'::jsonb,'LOCAL') b, db_pipeline.fn_valid_rule_list('[{"rule_key":"r1","rule_status_cd":"DRAFT","pool_refs":[]}]'::jsonb,'LOCAL') c, db_pipeline.fn_valid_cond_expr('{"expr_status_cd":"DRAFT","branches":[{"branch_no":1,"atoms":[{"atom_seq":1,"atom_key":"x","negate_yn":true,"cond_type_cd":"BNFT_EXCL","cond_status_cd":"DRAFT"}]}]}'::jsonb) d`))[0];
  expect('새 계약: 계산 방법·지급 단위 없는 규칙 허용', unknown === true);
  expect('새 계약: 구조 오류·상태 누락·pool_refs·제외 원문 없음은 계속 거부', !stillBad.a && !stillBad.b && !stillBad.c && !stillBad.d, JSON.stringify(stillBad));
  const viewRows = (await one(`SELECT (SELECT count(*)::int FROM db_pipeline.v_card_rule) r, (SELECT count(*)::int FROM db_pipeline.v_card_cond_atom) a, (SELECT count(*)::int FROM db_pipeline.v_card_rule_target) t`))[0];
  expect('규칙·조건·대상 뷰 조회 가능', viewRows.r > 0 && viewRows.a > 0 && viewRows.t > 0, JSON.stringify(viewRows));
  // ---- 정리 후 실행 SQL 호환성: 실제 프로그램이 쓰는 SQL을 그대로 실행한다 ----
  const mapper = (file) => Object.fromEntries(readFileSync(file, 'utf8').split(/^-- name: /m).slice(1)
    .map((block) => [block.split(/\s/)[0].replace(/[!<>*$#^]+$/, ''), block.slice(block.indexOf('\n') + 1).trim().replace(/;\s*$/, '')]));
  const dp = `${root}/src/card_benefit/payment_card/db_pipeline`;
  const maps = { v: mapper(`${dp}/neo4j_validation.sql`), e: mapper(`${dp}/embedding_repository.sql`), c: mapper(`${dp}/common_benefit_repository.sql`) };
  const bind = (sql, p) => sql.replace(/CAST\(:(\w+) AS ([\w.\[\]]+)\)/g, (_, k, t) => `CAST(${p[k]} AS ${t})`).replace(/:([A-Z_]+)/g, (_, k) => (k in p ? p[k] : `:${k}`));
  const P = { CARD_ID: '2', BNFT_ID: "'20261101_000001'", COMMON_ID: '15', RUN_ID: "'20261103_000031'", STG_ID: "'20261103_000335'", DOC_ID: "'20261103_000014'", TERMS: "ARRAY['트립닷컴']::text[]", RULE_KEY: "'one_pick_100'", EVIDENCE_ID: "'x'" };
  const runtime = [['v', 'condition_structure'], ['v', 'evidence_links'], ['v', 'common_applies'], ['v', 'rule_targets'],
                   ['e', 'select_card_bnft_detail'], ['e', 'select_common_bnft_detail'], ['e', 'select_card_bnft_evidence'], ['e', 'select_common_bnft_evidence'], ['e', 'keyword_card_bnft'],
                   ['c', 'integrity_errors'], ['c', 'common_integrity_errors'], ['c', 'brand_bnft_compare'], ['c', 'list_candidates'], ['c', 'candidate_evidence'], ['c', 'product_brand_evidence']];
  const failedSql = [];
  for (const [m, name] of runtime) {
    if (!maps[m][name]) { failedSql.push(`${name}: 없음`); continue; }
    try { await db.query(bind(maps[m][name], P)); } catch (e) { failedSql.push(`${name}: ${e.message}`); }
  }
  expect('정리 후 실행 SQL 호환(Neo4j 대조·GraphRAG 상세·등록 조회 15개)', failedSql.length === 0, failedSql.join(' / '));
  // 새 형식 규칙으로 개별 카드 혜택 INSERT(계산 단위 UNKNOWN) → 저장 가능, 이후 되돌림
  await db.exec('BEGIN');
  let insertErr = null;
  try {
    await db.query(bind(maps.c.insert_local_benefit, { CARD_ID: '2', BNFT_CD: "'BNFT_TEST_CLEANUP'", BNFT_NM: "'시험'", BNFT_TYPE: "'DISCOUNT'", COND: 'NULL',
      RULES: `'[{"rule_key":"r1","cond_expr":null,"target_list":[],"value_num":null,"value_unit_cd":null,"rule_status_cd":"DRAFT"}]'::jsonb`,
      RULE_TXT: "'원문'", LIMIT_TXT: 'NULL' }));
  } catch (e) { insertErr = e.message; }
  await db.exec('ROLLBACK');
  expect('개별 카드 혜택 INSERT: 계산 방법·지급 단위 없는 규칙 저장 가능(시험 후 롤백)', !insertErr, insertErr || '');
  // ---- 복구 ----
  let rerr = null;
  try { await db.exec(ROLLBACK); } catch (e) { rerr = e.message; await db.exec('ROLLBACK').catch(() => {}); }
  expect('복구 SQL 실행 성공', !rerr, rerr || '');
  if (!rerr) {
    const back = { tables: await tableState(), gates: await gates(), defs: await defs(), json: await jsonState(), codes: await codeState() };
    expect('복구: 데이터·JSON 원본 동일', JSON.stringify(back.tables) === JSON.stringify(before.tables) && back.json === before.json);
    expect('복구: 정합성 뷰 결과 동일', back.gates === before.gatesAll);
    const vdiff = Object.keys(before.defs.views).filter((v) => back.defs.views[v] !== before.defs.views[v]);
    const fdiff = Object.keys(before.defs.funcs).filter((f) => back.defs.funcs[f] !== before.defs.funcs[f]);
    expect('복구: 뷰·함수 정의와 주석 동일', vdiff.length === 0 && fdiff.length === 0, `views ${vdiff} funcs ${fdiff}`);
    for (const f of fdiff) { const a = before.defs.funcs[f], b = back.defs.funcs[f]; let i = 0; while (a[i] === b[i]) i++; console.log('DIFF', f, JSON.stringify(a.slice(i - 40, i + 60)), '||', JSON.stringify(b.slice(i - 40, i + 60))); }
    expect('복구: 인덱스 정의 전체 동일', back.defs.indexes === before.defs.indexes);
    expect('복구: 공통코드 동일', JSON.stringify(back.codes) === JSON.stringify(before.codes));
    const excl = (await one(`SELECT to_regclass('db_pipeline.card_excl_item') t, (SELECT count(*)::int FROM pg_indexes WHERE tablename='card_excl_item') i`))[0];
    expect('복구: card_excl_item 테이블·인덱스 4개', excl.t && excl.i === 4, JSON.stringify(excl));
  }
}
for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name}${r.detail ? '  :: ' + String(r.detail).slice(0, 300) : ''}`);
console.log(`TOTAL ${results.length} PASS ${results.filter((r) => r.ok).length}`);
process.exit(results.every((r) => r.ok) ? 0 : 1);
