"""실제 DB 정의(pre_cleanup_catalog.json)와 데이터(pre_cleanup_data.json)에서 정리 SQL과 복구 SQL을 만든다."""
import json, re, sys
from pathlib import Path

ROOT = Path(r'C:\myproject\workspace\mle-02-p2-team3\src\card_benefit')
cat = json.loads((ROOT / 'docs/schema_cleanup/pre_cleanup_catalog.json').read_text(encoding='utf-8'))
data = json.loads((ROOT / 'docs/schema_cleanup/pre_cleanup_data.json').read_text(encoding='utf-8'))
V, F = cat['views'], cat['functions']
VC, FC = cat['view_comments'], cat['function_comments']

RULE_KEYS = ('predicate_state_cd', 'method_ver', 'calc_params', 'rule_priority', 'calc_method_cd', 'payout_unit_cd', 'basis_amt')
ATOM_KEYS = ('predicate_method_cd', 'predicate_method_ver', 'cond_params', 'card_excl_item_id', 'link_role_cd')
CODE_GROUPS = ('PREDICATE_STATE', 'PREDICATE_METHOD', 'RULE_SELECT', 'LIMIT_PERIOD', 'LIMIT_UNIT', 'LIMIT_SCOPE', 'LIMIT_AGG', 'POOL_ROLE', 'CALC_METHOD', 'PAYOUT_UNIT')
DROP_GATES = ("FROM rule_value_gap g", "FROM predicate_param_gap g", "'excl_item_unknown'::text AS gate_cd")
DROP_USAGE = ("'card_bnft.rule_select_cd'::text", "'card_bnft.rule_list[].predicate_state_cd'::text", "'cond_expr atom predicate_method_cd'::text",
              "'card_bnft.rule_list[].calc_method_cd'::text", "'card_bnft.rule_list[].payout_unit_cd'::text")


def drop_lines(sql, names, prefix=''):
    out, removed = [], 0
    for line in sql.split('\n'):
        if any(re.search(rf"(AS {n},?$|{prefix}{n},?$|'{n}'::text\)?\)?(::\w+(\(\d+(,\d+)?\))?)? AS {n},?$)", line.strip()) for n in names):
            removed += 1
            continue
        out.append(line)
    if removed != len(names):
        raise SystemExit(f'열 삭제 수 불일치 {removed} != {len(names)}')
    text = '\n'.join(out)
    return re.sub(r',(\s*\n\s*FROM )', r'\1', text)          # 마지막 열 뒤 쉼표 정리


def drop_union(sql, markers):
    parts = sql.rstrip().rstrip(';').split('\nUNION ALL\n')
    kept = [p for p in parts if not any(m in p for m in markers)]
    if len(parts) - len(kept) != len(markers):
        raise SystemExit(f'UNION 가지 삭제 수 불일치 {len(parts) - len(kept)}')
    return '\nUNION ALL\n'.join(kept)


def drop_cte(sql, name, next_name):
    start = sql.index(f'), {name} AS (')
    end = sql.index(f'), {next_name} AS (') if next_name else sql.index('\n        )\n', start)
    return sql[:start] + sql[end:]


# ---- 새 정의 ----
new_rule = drop_lines(V['v_card_rule'], ('spend_min_amt', 'spend_max_amt_excl', 'predicate_state_cd', 'method_ver', 'calc_params', 'rule_priority',
                                         'calc_method_cd', 'payout_unit_cd', 'basis_amt'))
new_atom = drop_lines(V['v_card_cond_atom'], ATOM_KEYS)
integ = V['v_card_integrity_issue']
for col in ATOM_KEYS:
    integ = integ.replace(f'            v_card_cond_atom.{col},\n', '')
ctes = re.findall(r'\), (\w+) AS \(', integ)
integ = drop_cte(integ, 'rule_value_gap', ctes[ctes.index('rule_value_gap') + 1])
ctes = re.findall(r'\), (\w+) AS \(', integ)
nxt = ctes[ctes.index('predicate_param_gap') + 1] if ctes.index('predicate_param_gap') + 1 < len(ctes) else None
integ = drop_cte(integ, 'predicate_param_gap', nxt)
new_integ = drop_union(integ, DROP_GATES)
new_usage = drop_union(V['v_common_cd_usage'], DROP_USAGE)
for removed in ATOM_KEYS + ('rule_value_gap', 'predicate_param_gap', 'card_excl_item', 'calc_method_cd', 'payout_unit_cd', 'basis_amt'):
    if removed in new_integ:
        raise SystemExit(f'정합성 뷰에 {removed}가 남음')

fr = F['fn_valid_rule_list']
for old in ("           OR coalesce(v_rule->>'calc_method_cd', '') = ''\n",
            "           OR coalesce(v_rule->>'payout_unit_cd', '') = ''\n",
            "           OR jsonb_typeof(v_rule->'method_ver') IS DISTINCT FROM 'number'\n",
            "           OR (v_rule->>'method_ver')::integer < 1 THEN\n"):
    if old not in fr:
        raise SystemExit('fn_valid_rule_list 형식이 다름: ' + old)
fr = fr.replace("           OR jsonb_typeof(v_rule->'method_ver') IS DISTINCT FROM 'number'\n           OR (v_rule->>'method_ver')::integer < 1 THEN\n", '')
fr = fr.replace("           OR coalesce(v_rule->>'calc_method_cd', '') = ''\n", '').replace("           OR coalesce(v_rule->>'payout_unit_cd', '') = ''\n", '')
fr = fr.replace("           OR coalesce(v_rule->>'rule_status_cd', '') = ''\n", "           OR coalesce(v_rule->>'rule_status_cd', '') = '' THEN\n")
state_block = fr[fr.index("        v_state := v_rule->>'predicate_state_cd';"):fr.index("        IF NOT db_pipeline.fn_valid_target_list")]
fr = fr.replace(state_block, "        IF NOT db_pipeline.fn_valid_cond_expr(nullif(v_rule->'cond_expr', 'null'::jsonb)) THEN\n            RETURN false;\n        END IF;\n\n")
fr = fr.replace("    v_state text;\n", '')
for old, new in (("           OR coalesce(jsonb_typeof(v_rule->'basis_amt'), 'null') NOT IN ('number','null')\n", ''),
                 ("        IF coalesce((v_rule->>'value_num')::numeric, 0) < 0\n           OR coalesce((v_rule->>'basis_amt')::numeric, 0) < 0 THEN",
                  "        IF coalesce((v_rule->>'value_num')::numeric, 0) < 0 THEN")):
    if old not in fr:
        raise SystemExit('fn_valid_rule_list basis_amt 형식이 다름: ' + old)
    fr = fr.replace(old, new)
fc = F['fn_valid_cond_expr']
fc = fc.replace("coalesce(v_atom->>'card_excl_item_id', v_atom->>'excl_raw_txt', '') = ''", "coalesce(v_atom->>'excl_raw_txt', '') = ''")
fc = fc[:fc.index('            -- 술어 방법 코드와 버전은 짝으로 저장')] + fc[fc.index('        END LOOP;\n    END LOOP;'):]
for word in ('predicate', 'method_ver', 'calc_method_cd', 'payout_unit_cd', 'basis_amt', 'card_excl_item_id', 'cond_params'):
    if word in fr or word in fc:
        raise SystemExit(f'함수에 {word}가 남음')


def lit(value):
    return "'" + value.replace("'", "''") + "'"


def strip_rules_sql(column):
    return (f"""(SELECT coalesce(jsonb_agg((r.value - ARRAY{list(RULE_KEYS)}::text[])
              || CASE WHEN jsonb_typeof(r.value->'cond_expr') = 'object'
                      THEN jsonb_build_object('cond_expr', pg_temp.db_pipeline_tmp_strip_atoms(r.value->'cond_expr')) ELSE '{{}}'::jsonb END
              ORDER BY r.ord), '[]'::jsonb)
           FROM jsonb_array_elements({column}) WITH ORDINALITY AS r(value, ord))""")


strip_fn = f"""CREATE FUNCTION pg_temp.db_pipeline_tmp_strip_atoms(p_expr jsonb) RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN p_expr IS NULL OR jsonb_typeof(p_expr) <> 'object' THEN p_expr ELSE
        jsonb_set(p_expr, '{{branches}}', (SELECT coalesce(jsonb_agg(jsonb_set(b.value, '{{atoms}}',
            (SELECT coalesce(jsonb_agg(a.value - ARRAY{list(ATOM_KEYS)}::text[] ORDER BY a.ord), '[]'::jsonb)
             FROM jsonb_array_elements(b.value->'atoms') WITH ORDINALITY AS a(value, ord))) ORDER BY b.ord), '[]'::jsonb)
            FROM jsonb_array_elements(p_expr->'branches') WITH ORDINALITY AS b(value, ord))) END
$$;"""

new_comments = {
    'v_card_rule': '혜택 규칙(값·단위·대상·조건)을 행으로 복원. 계산 실행용 열(계산 방법·지급 단위·기준 금액·방법 버전·우선순위·계산 파라미터·판정 상태·실적 구간)은 2026-11-03 정리에서 제거',
    'v_card_cond_atom': '모든 조건식의 atom을 소유자와 함께 행으로 복원. 술어 방법·파라미터·제외 사전·연결 역할 열은 2026-11-03 정리에서 제거',
}
fn_comments = {
    'fn_valid_rule_list': '혜택 규칙 목록 JSONB 계약 검증. 계산 방법·지급 단위·기준 금액·방법 버전·판정 상태는 저장하지 않는다(2026-11-03 정리). pool_refs 불허, p_owner는 LOCAL만 허용',
    'fn_valid_cond_expr': '조건식 JSONB 계약 검증. branch 사이 OR, branch 안 atom AND, negate_yn=NOT. 제외 조건은 excl_raw_txt 원문이 필요하다',
}

view_drop_order = ['v_card_integrity_issue', 'v_common_cd_usage', 'v_card_bnft_rule_effective', 'v_card_rule_target', 'v_card_cond_atom', 'v_card_rule']
counts_tables = ['card_ai_call', 'card_ai_run', 'card_bnft', 'card_common', 'card_common_bnft', 'card_common_bnft_apply', 'card_common_doc', 'card_doc',
                 'card_doc_chunk', 'card_doc_page', 'card_evidence_link', 'card_extr_stg', 'card_product', 'card_product_doc', 'card_source_evidence']
count_sql = ' UNION ALL '.join(f"SELECT '{t}', count(*) FROM db_pipeline.{t}" for t in counts_tables)

cleanup = f"""-- =====================================================================================================
-- 계산 구조 정리(2026-11-03). 고객 실적 계산·보상액 산출용 구조를 제거하고 검색·답변용 혜택 정보는 유지한다.
-- 기록: src/card_benefit/docs/schema_cleanup/  /  복구: db_pipeline_calc_structure_cleanup_rollback.sql
-- [승인 전 공유 DB 실행 금지] 격리된 로컬 테스트 DB에서 검증했다. DROP ... CASCADE를 쓰지 않는다.
--
-- 제거: v_card_bnft_rule_effective, fn_cond_spend_bound, card_excl_item(+인덱스), card_extr_stg.card_excl_item_id,
--       card_bnft.rule_select_cd, 정합성 게이트 rule_method_value_*·predicate_params_*·excl_item_unknown,
--       rule_list 키 {', '.join(RULE_KEYS)}, 조건 atom 키 {', '.join(ATOM_KEYS)},
--       공통코드 그룹 {', '.join(CODE_GROUPS)}
-- 대체: v_card_rule·v_card_cond_atom(열 제거), v_common_cd_usage·v_card_integrity_issue(가지 제거),
--       fn_valid_rule_list·fn_valid_cond_expr(계산 필수 조건 제거)
-- 유지: value_num·value_unit_cd(답변 수치 검증·검색 텍스트·Neo4j), target_list, 조건 원문·유형·금액,
--       relation_list, bnft_rule_txt·bnft_limit_txt, 원문 근거·청크·임베딩, 공통서비스 데이터, 추출 이력(card_extr_stg)
-- =====================================================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = pg_catalog;

LOCK TABLE db_pipeline.card_bnft, db_pipeline.card_product, db_pipeline.card_extr_stg, db_pipeline.card_excl_item,
           db_pipeline.common_cd, db_pipeline.common_code_grp IN ACCESS EXCLUSIVE MODE;

-- 0. 사전 조건: 지울 컬럼·테이블에 값이 없어야 한다. 정리 전 건수를 임시 테이블에 둔다.
DO $pre$
BEGIN
    IF EXISTS (SELECT 1 FROM db_pipeline.card_bnft WHERE rule_select_cd IS NOT NULL) THEN RAISE EXCEPTION 'rule_select_cd에 값이 있어 중단'; END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.card_extr_stg WHERE card_excl_item_id IS NOT NULL) THEN RAISE EXCEPTION 'card_extr_stg.card_excl_item_id에 값이 있어 중단'; END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.card_excl_item) THEN RAISE EXCEPTION 'card_excl_item에 행이 있어 중단'; END IF;
    -- 다시 만들 뷰 묶음 밖의 객체가 이 뷰들에 의존하면 중단한다(CASCADE 없이 지우기 위해).
    IF EXISTS (SELECT 1 FROM pg_depend d JOIN pg_rewrite w ON w.oid = d.objid JOIN pg_class v ON v.oid = w.ev_class
               WHERE d.refobjid IN ({', '.join(f"'db_pipeline.{v}'::regclass" for v in view_drop_order)})
                 AND v.oid <> d.refobjid
                 AND v.oid NOT IN ({', '.join(f"'db_pipeline.{v}'::regclass" for v in view_drop_order)})) THEN
        RAISE EXCEPTION '정리 대상 뷰에 의존하는 다른 객체가 있어 중단';
    END IF;
END
$pre$;
CREATE TEMP TABLE cleanup_before ON COMMIT DROP AS {count_sql};

-- 1. 뷰 제거(의존 순서, CASCADE 없음)
{chr(10).join(f'DROP VIEW db_pipeline.{v};' for v in view_drop_order)}
DROP FUNCTION db_pipeline.fn_cond_spend_bound(jsonb, text);

-- 2. 검증 함수 교체(계산 필수 조건 제거). 데이터 정리 전에 바꿔야 CHECK가 통과한다.
{fc.rstrip()};
{fr.rstrip()};
COMMENT ON FUNCTION db_pipeline.fn_valid_rule_list(jsonb, text) IS {lit(fn_comments['fn_valid_rule_list'])};
COMMENT ON FUNCTION db_pipeline.fn_valid_cond_expr(jsonb) IS {lit(fn_comments['fn_valid_cond_expr'])};

-- 3. 저장된 JSON에서 계산 전용 키 제거(값은 모두 비었거나 고정값). 추출 이력 card_extr_stg는 바꾸지 않는다.
{strip_fn}
UPDATE db_pipeline.card_bnft SET
    rule_list = {strip_rules_sql('rule_list')},
    bnft_cond_expr = pg_temp.db_pipeline_tmp_strip_atoms(bnft_cond_expr);
UPDATE db_pipeline.card_product SET card_cond_expr = pg_temp.db_pipeline_tmp_strip_atoms(card_cond_expr) WHERE card_cond_expr IS NOT NULL;

-- 4. 컬럼·테이블 제거
ALTER TABLE db_pipeline.card_bnft DROP COLUMN rule_select_cd;
DROP INDEX db_pipeline.ix_card_extr_stg_excl_item_key;
ALTER TABLE db_pipeline.card_extr_stg DROP COLUMN card_excl_item_id;
DROP INDEX db_pipeline.ix_card_excl_item_alias_gin;
DROP INDEX db_pipeline.ix_card_excl_item_concept_key;
DROP TABLE db_pipeline.card_excl_item;

-- 5. 뷰 재생성
CREATE VIEW db_pipeline.v_card_rule AS
{new_rule.rstrip().rstrip(';')};
CREATE VIEW db_pipeline.v_card_cond_atom AS
{new_atom.rstrip().rstrip(';')};
CREATE VIEW db_pipeline.v_card_rule_target AS
{V['v_card_rule_target'].rstrip().rstrip(';')};
CREATE VIEW db_pipeline.v_common_cd_usage AS
{new_usage.rstrip().rstrip(';')};
CREATE VIEW db_pipeline.v_card_integrity_issue AS
{new_integ.rstrip().rstrip(';')};
COMMENT ON VIEW db_pipeline.v_card_rule IS {lit(new_comments['v_card_rule'])};
COMMENT ON VIEW db_pipeline.v_card_cond_atom IS {lit(new_comments['v_card_cond_atom'])};
COMMENT ON VIEW db_pipeline.v_card_rule_target IS {lit(VC['v_card_rule_target'])};
COMMENT ON VIEW db_pipeline.v_common_cd_usage IS {lit(VC['v_common_cd_usage'])};
COMMENT ON VIEW db_pipeline.v_card_integrity_issue IS {lit(VC['v_card_integrity_issue'])};
{chr(10).join(f'ALTER VIEW db_pipeline.{v} OWNER TO postgres;' for v in ('v_card_rule', 'v_card_cond_atom', 'v_card_rule_target', 'v_common_cd_usage', 'v_card_integrity_issue'))}

-- 6. 계산·한도 풀 전용 공통코드 제거
DELETE FROM db_pipeline.common_cd WHERE common_code_grp_id IN ({', '.join(lit(g) for g in CODE_GROUPS)});
DELETE FROM db_pipeline.common_code_grp WHERE common_code_grp_id IN ({', '.join(lit(g) for g in CODE_GROUPS)});

-- 7. 사후 검증: 데이터 건수 동일, 남은 계산 키 없음, 모든 행이 새 계약 통과, 공통코드 사용처 정합
DO $post$
DECLARE v_diff int; v_left int;
BEGIN
    SELECT count(*) INTO v_diff FROM (SELECT * FROM cleanup_before EXCEPT ({count_sql})) x;
    IF v_diff > 0 THEN RAISE EXCEPTION '데이터 건수가 달라졌습니다'; END IF;
    SELECT count(*) INTO v_left FROM db_pipeline.card_bnft b, jsonb_array_elements(b.rule_list) r
    WHERE r.value ?| ARRAY{list(RULE_KEYS)}::text[];
    IF v_left > 0 THEN RAISE EXCEPTION '규칙 계산 키가 남았습니다: %', v_left; END IF;
    SELECT count(*) INTO v_left FROM db_pipeline.card_bnft b,
        LATERAL (SELECT b.bnft_cond_expr AS e UNION ALL SELECT r.value->'cond_expr' FROM jsonb_array_elements(b.rule_list) r) x,
        jsonb_array_elements(CASE WHEN jsonb_typeof(x.e) = 'object' THEN x.e->'branches' ELSE '[]'::jsonb END) br,
        jsonb_array_elements(br.value->'atoms') a
    WHERE a.value ?| ARRAY{list(ATOM_KEYS)}::text[];
    IF v_left > 0 THEN RAISE EXCEPTION '조건 atom 계산 키가 남았습니다: %', v_left; END IF;
    IF NOT (SELECT bool_and(db_pipeline.fn_valid_rule_list(rule_list, 'LOCAL') AND db_pipeline.fn_valid_cond_expr(bnft_cond_expr))
            FROM db_pipeline.card_bnft) THEN RAISE EXCEPTION '새 계약을 통과하지 못한 혜택이 있습니다'; END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.v_common_cd_usage u WHERE u.common_code_grp_id IN ({', '.join(lit(g) for g in CODE_GROUPS)})) THEN
        RAISE EXCEPTION '삭제한 코드 그룹을 쓰는 곳이 남았습니다';
    END IF;
    PERFORM count(*) FROM db_pipeline.v_card_integrity_issue;
    RAISE NOTICE '계산 구조 정리 완료';
END
$post$;

COMMIT;
"""

# ---- 복구 SQL ----
def json_lit(value):
    return lit(json.dumps(value, ensure_ascii=False)) + '::jsonb'


excl_cols = [c for c in cat['columns'] if c[0] == 'card_excl_item']
type_map = {'character varying': 'character varying(20)', 'ARRAY': 'text[]'}
excl_ddl = ',\n    '.join(
    f"{c[2]} {('character varying(20)' if c[2] == 'card_excl_item_id' else 'character varying(50)' if c[2] in ('excl_concept_cd', 'create_user_id', 'update_user_id') else type_map.get(c[3], c[3]))}"
    f"{' NOT NULL' if c[4] == 'NO' else ''}{' DEFAULT ' + c[5] if c[5] else ''}" for c in excl_cols)
excl_cons = [c for c in cat['constraints'] if c[0] == 'db_pipeline.card_excl_item']
excl_idx = [i for i in cat['indexes'] if i[0] == 'card_excl_item' and i[1].startswith('ix_')]
stg_excl_idx = next(i[2] for i in cat['indexes'] if i[1] == 'ix_card_extr_stg_excl_item_key') + ';'

restore_rows = '\n'.join(
    f"UPDATE db_pipeline.card_bnft SET rule_list = {json_lit(r['rule_list'])}, bnft_cond_expr = {json_lit(r['bnft_cond_expr']) if r['bnft_cond_expr'] is not None else 'NULL'} "
    f"WHERE card_id = {r['card_id']} AND card_bnft_id = {lit(r['card_bnft_id'])};" for r in data['card_bnft'])
restore_prod = '\n'.join(
    f"UPDATE db_pipeline.card_product SET card_cond_expr = {json_lit(r['card_cond_expr'])} WHERE card_id = {r['card_id']};"
    for r in data['card_product'] if r['card_cond_expr'] is not None)
grp_cols = list(data['code_groups'][0].keys())
cd_cols = list(data['codes'][0].keys())
def row_values(row, cols):
    return '(' + ', '.join('NULL' if row[c] is None else lit(str(row[c])) for c in cols) + ')'
restore_codes = (f"INSERT INTO db_pipeline.common_code_grp ({', '.join(grp_cols)}) VALUES\n    "
                 + ',\n    '.join(row_values(r, grp_cols) for r in data['code_groups']) + ';\n'
                 + f"INSERT INTO db_pipeline.common_cd ({', '.join(cd_cols)}) VALUES\n    "
                 + ',\n    '.join(row_values(r, cd_cols) for r in data['codes']) + ';')

rollback = f"""-- =====================================================================================================
-- 계산 구조 정리 복구. db_pipeline_calc_structure_cleanup.sql 실행 전 상태로 되돌린다.
-- 정의와 값은 정리 전 실제 DB에서 추출했다(docs/schema_cleanup/pre_cleanup_catalog.json, pre_cleanup_data.json).
-- 복구한 컬럼(card_bnft.rule_select_cd, card_extr_stg.card_excl_item_id)은 테이블 맨 뒤에 추가된다(값은 정리 전에도 모두 NULL).
-- =====================================================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL search_path = pg_catalog;

DROP VIEW db_pipeline.v_card_integrity_issue;
DROP VIEW db_pipeline.v_common_cd_usage;
DROP VIEW db_pipeline.v_card_rule_target;
DROP VIEW db_pipeline.v_card_cond_atom;
DROP VIEW db_pipeline.v_card_rule;

-- 1. 함수(정리 전 정의)
{F['fn_valid_cond_expr'].rstrip()};
{F['fn_valid_rule_list'].rstrip()};
{F['fn_cond_spend_bound'].rstrip()};
COMMENT ON FUNCTION db_pipeline.fn_valid_rule_list(jsonb, text) IS {lit(FC['fn_valid_rule_list'])};
COMMENT ON FUNCTION db_pipeline.fn_valid_cond_expr(jsonb) IS {lit(FC['fn_valid_cond_expr'])};
COMMENT ON FUNCTION db_pipeline.fn_cond_spend_bound(jsonb, text) IS {lit(FC['fn_cond_spend_bound'])};
ALTER FUNCTION db_pipeline.fn_cond_spend_bound(jsonb, text) OWNER TO postgres;

-- 2. 테이블·컬럼
CREATE TABLE db_pipeline.card_excl_item (
    {excl_ddl}
);
{chr(10).join(f'ALTER TABLE db_pipeline.card_excl_item ADD CONSTRAINT {c[1]} {c[2]};' for c in sorted(excl_cons, key=lambda c: c[1] != 'card_excl_item_pkey'))}
{chr(10).join(i[2] + ';' for i in excl_idx)}
COMMENT ON TABLE db_pipeline.card_excl_item IS {lit(data['excl_table_comment'])};
{chr(10).join(f"COMMENT ON COLUMN db_pipeline.card_excl_item.{c[2]} IS {lit(c[6])};" for c in excl_cols if c[6])}
ALTER TABLE db_pipeline.card_excl_item OWNER TO postgres;
ALTER TABLE db_pipeline.card_bnft ADD COLUMN rule_select_cd character varying(30);
COMMENT ON COLUMN db_pipeline.card_bnft.rule_select_cd IS '규칙 선택 방식';
ALTER TABLE db_pipeline.card_extr_stg ADD COLUMN card_excl_item_id character varying(20);
COMMENT ON COLUMN db_pipeline.card_extr_stg.card_excl_item_id IS '제외 항목 아이디';
{stg_excl_idx}

-- 3. 데이터(정리 전 JSON 원본)
{restore_rows}
{restore_prod}

-- 4. 뷰(정리 전 정의)
CREATE VIEW db_pipeline.v_card_rule AS
{V['v_card_rule'].rstrip().rstrip(';')};
CREATE VIEW db_pipeline.v_card_bnft_rule_effective AS
{V['v_card_bnft_rule_effective'].rstrip().rstrip(';')};
CREATE VIEW db_pipeline.v_card_cond_atom AS
{V['v_card_cond_atom'].rstrip().rstrip(';')};
CREATE VIEW db_pipeline.v_card_rule_target AS
{V['v_card_rule_target'].rstrip().rstrip(';')};
CREATE VIEW db_pipeline.v_common_cd_usage AS
{V['v_common_cd_usage'].rstrip().rstrip(';')};
CREATE VIEW db_pipeline.v_card_integrity_issue AS
{V['v_card_integrity_issue'].rstrip().rstrip(';')};
{chr(10).join(f'COMMENT ON VIEW db_pipeline.{v} IS {lit(VC[v])};' for v in ('v_card_rule', 'v_card_bnft_rule_effective', 'v_card_cond_atom', 'v_card_rule_target', 'v_common_cd_usage', 'v_card_integrity_issue'))}
{chr(10).join(f'ALTER VIEW db_pipeline.{v} OWNER TO postgres;' for v in ('v_card_rule', 'v_card_bnft_rule_effective', 'v_card_cond_atom', 'v_card_rule_target', 'v_common_cd_usage', 'v_card_integrity_issue'))}

-- 5. 공통코드
{restore_codes}

COMMIT;
"""
LF = chr(10)
(ROOT / 'sql/db_pipeline_calc_structure_cleanup.sql').write_text(cleanup, encoding='utf-8', newline=LF)
(ROOT / 'sql/db_pipeline_calc_structure_cleanup_rollback.sql').write_text(rollback, encoding='utf-8', newline=LF)
print('cleanup', len(cleanup), 'rollback', len(rollback))
