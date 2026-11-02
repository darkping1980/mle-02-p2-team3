-- V7 혜택·한도 TEXT 단순화 복구. db_pipeline_migration_v7_bnft_text.sql 직전 구조와 데이터로 되돌린다.
-- DBeaver: 스크립트 전체 실행(Alt+X)으로 돌린다. 문장 단위 실행(Ctrl+Enter)을 쓰지 않는다.
-- 단일 트랜잭션이고 재실행해도 같은 상태로 수렴한다. 복구 원본은 db_pipeline_backup의 백업이다.
-- card_bnft.bnft_rule_txt, bnft_limit_txt는 이관 전에도 있던 컬럼이므로 지우지 않는다.
-- 프로그램도 함께 되돌려야 한다. 구조만 복구하면 TEXT 기준으로 수정된 Python 코드와 맞지 않는다.
BEGIN;
SET LOCAL lock_timeout = '10s';
LOCK TABLE db_pipeline.card_bnft, db_pipeline.card_evidence_link IN SHARE ROW EXCLUSIVE MODE;
DO $$
BEGIN
    IF to_regclass('db_pipeline_backup.card_limit_pool_20261102') IS NULL
       OR to_regclass('db_pipeline_backup.card_bnft_rule_pool_20261102') IS NULL
       OR to_regclass('db_pipeline_backup.card_evidence_link_pre_simplify_20261102') IS NULL
       OR to_regclass('db_pipeline_backup.seq_card_limit_pool_20261102') IS NULL THEN
        RAISE EXCEPTION '복구 원본 백업이 없습니다';
    END IF;
    -- 이전 계약에서 소진 대체 관계는 trigger_pool_id가 필수다. 값을 지어내지 않고 중단한다.
    IF EXISTS (SELECT 1 FROM db_pipeline.card_bnft b
               CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) AS r(value)
               WHERE r.value->>'rel_type_cd' = 'FALLBACK_AFTER_CAP') THEN
        RAISE EXCEPTION '이관 후 등록된 FALLBACK_AFTER_CAP 관계가 있어 복구할 수 없습니다. 해당 관계를 먼저 검토하세요';
    END IF;
END;
$$;
-- 1. 뷰 제거.
DROP VIEW IF EXISTS db_pipeline.v_card_integrity_issue;
DROP VIEW IF EXISTS db_pipeline.v_common_cd_usage;
DROP VIEW IF EXISTS db_pipeline.v_card_cond_atom;
DROP VIEW IF EXISTS db_pipeline.v_card_limit_tier;
DROP VIEW IF EXISTS db_pipeline.v_card_rule_pool;
DROP VIEW IF EXISTS db_pipeline.v_card_bnft_rel;
-- 2. 함수·시퀀스 복구.
CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_tier_list(p_list jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
    SELECT CASE
        WHEN jsonb_typeof(p_list) IS DISTINCT FROM 'array' OR jsonb_array_length(p_list) = 0 THEN false
        ELSE (
            SELECT bool_and(
                       jsonb_typeof(t.value) = 'object'
                       AND coalesce(t.value->>'tier_key', '') ~ '^[A-Za-z0-9_.:-]{1,40}$'
                       AND jsonb_typeof(t.value->'limit_num') IS NOT DISTINCT FROM 'number'
                       AND (t.value->>'limit_num')::numeric >= 0
                       AND jsonb_typeof(t.value->'tier_priority') IS DISTINCT FROM 'string'
                       AND coalesce((t.value->>'tier_priority')::integer, 1) > 0
                       AND CASE t.value->>'predicate_state_cd'
                               WHEN 'CONDITIONAL' THEN t.value->'cond_expr' IS NOT NULL
                                                       AND db_pipeline.fn_valid_cond_expr(t.value->'cond_expr')
                               WHEN 'VERIFIED_UNCONDITIONAL' THEN t.value->'cond_expr' IS NULL
                               WHEN 'PENDING_REVIEW' THEN db_pipeline.fn_valid_cond_expr(t.value->'cond_expr')
                               ELSE false
                           END)
                   AND count(*) = count(DISTINCT t.value->>'tier_key')
            FROM jsonb_array_elements(p_list) AS t(value))
    END
$_$;

COMMENT ON FUNCTION db_pipeline.fn_valid_tier_list(jsonb) IS '한도 풀 tier 목록 검증. limit_num은 0 이상의 숫자, 상태별 cond_expr 필수 여부 검사';

CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_relation_list(p_list jsonb, p_self_bnft_id text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
DECLARE
    v_rel jsonb;
    v_keys text[] := '{}';
    v_pairs text[] := '{}';
    v_pair text;
BEGIN
    IF jsonb_typeof(p_list) IS DISTINCT FROM 'array' THEN
        RETURN false;
    END IF;
    FOR v_rel IN SELECT value FROM jsonb_array_elements(p_list) LOOP
        IF jsonb_typeof(v_rel) <> 'object'
           OR coalesce(v_rel->>'relation_key', '') !~ '^[A-Za-z0-9_.:-]{1,40}$'
           OR v_rel->>'relation_key' = ANY (v_keys)
           OR coalesce(v_rel->>'to_bnft_id', '') = ''
           OR v_rel->>'to_bnft_id' = p_self_bnft_id
           OR coalesce(v_rel->>'rel_type_cd', '') = ''
           OR coalesce(jsonb_typeof(v_rel->'rel_priority'), 'null') NOT IN ('number','null')
           OR coalesce(jsonb_typeof(v_rel->'trigger_pool_id'), 'null') NOT IN ('string','null') THEN
            RETURN false;
        END IF;
        IF v_rel->>'rel_type_cd' = 'FALLBACK_AFTER_CAP' AND coalesce(v_rel->>'trigger_pool_id', '') = '' THEN
            RETURN false;
        END IF;
        v_pair := (v_rel->>'to_bnft_id') || '|' || (v_rel->>'rel_type_cd');
        IF v_pair = ANY (v_pairs) THEN
            RETURN false;
        END IF;
        v_pairs := v_pairs || v_pair;
        v_keys := v_keys || (v_rel->>'relation_key');
    END LOOP;
    RETURN true;
END;
$_$;

COMMENT ON FUNCTION db_pipeline.fn_valid_relation_list(jsonb, text) IS '혜택 관계 목록 JSONB 계약 검증. 자기 참조, relation_key 중복, 같은 대상·유형 중복, 소진 대체의 trigger_pool_id 누락 거부';

CREATE SEQUENCE IF NOT EXISTS db_pipeline.seq_card_limit_pool INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
COMMENT ON SEQUENCE db_pipeline.seq_card_limit_pool IS 'card_limit_pool.pool_id 로컬 업무 ID 발급';
DO $$
DECLARE
    v_last bigint;
    v_called boolean;
BEGIN
    SELECT last_value, is_called INTO STRICT v_last, v_called FROM db_pipeline_backup.seq_card_limit_pool_20261102;
    PERFORM setval('db_pipeline.seq_card_limit_pool', v_last, v_called);
END;
$$;
-- 3. 테이블과 행 복구.
CREATE TABLE IF NOT EXISTS db_pipeline.card_limit_pool (
    card_id bigint NOT NULL,
    pool_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_limit_pool') NOT NULL,
    pool_scope_cd varchar(30) NOT NULL,
    period_cd varchar(20) NOT NULL,
    cap_unit_cd varchar(30) NOT NULL,
    aggregation_key_cd varchar(30) NOT NULL,
    tier_list jsonb NOT NULL,
    PRIMARY KEY (card_id, pool_id),
    CONSTRAINT card_limit_pool_ck_1 CHECK (db_pipeline.fn_valid_tier_list(tier_list))
);
COMMENT ON TABLE db_pipeline.card_limit_pool IS '혜택 공유 한도';
COMMENT ON COLUMN db_pipeline.card_limit_pool.card_id IS '카드 아이디';
COMMENT ON COLUMN db_pipeline.card_limit_pool.pool_id IS '한도 풀 아이디';
COMMENT ON COLUMN db_pipeline.card_limit_pool.pool_scope_cd IS '한도 적용 범위';
COMMENT ON COLUMN db_pipeline.card_limit_pool.period_cd IS '한도 기간';
COMMENT ON COLUMN db_pipeline.card_limit_pool.cap_unit_cd IS '한도 단위';
COMMENT ON COLUMN db_pipeline.card_limit_pool.aggregation_key_cd IS '한도 집계 기준';
COMMENT ON COLUMN db_pipeline.card_limit_pool.tier_list IS '한도 구간 목록';
CREATE TABLE IF NOT EXISTS db_pipeline.card_bnft_rule_pool (
    card_id bigint NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    rule_key varchar(40) NOT NULL,
    pool_id varchar(20) NOT NULL,
    pool_role_cd varchar(30) NOT NULL,
    PRIMARY KEY (card_id, card_bnft_id, rule_key, pool_id)
);
COMMENT ON TABLE db_pipeline.card_bnft_rule_pool IS '카드 혜택 규칙과 한도 풀의 논리적 관계. 물리 FK 없음';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.card_id IS '카드 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.card_bnft_id IS '혜택 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.rule_key IS '계산 규칙 키';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.pool_id IS '한도 풀 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.pool_role_cd IS '한도 풀 역할';

INSERT INTO db_pipeline.card_limit_pool (card_id, pool_id, pool_scope_cd, period_cd, cap_unit_cd, aggregation_key_cd, tier_list)
SELECT card_id, pool_id, pool_scope_cd, period_cd, cap_unit_cd, aggregation_key_cd, tier_list
FROM db_pipeline_backup.card_limit_pool_20261102
ON CONFLICT (card_id, pool_id) DO NOTHING;
INSERT INTO db_pipeline.card_bnft_rule_pool (card_id, card_bnft_id, rule_key, pool_id, pool_role_cd)
SELECT card_id, card_bnft_id, rule_key, pool_id, pool_role_cd
FROM db_pipeline_backup.card_bnft_rule_pool_20261102
ON CONFLICT (card_id, card_bnft_id, rule_key, pool_id) DO NOTHING;
-- 4. 근거 연결 구조와 POOL 근거 복구.
ALTER TABLE db_pipeline.card_evidence_link ADD COLUMN IF NOT EXISTS pool_id varchar(20);
COMMENT ON COLUMN db_pipeline.card_evidence_link.pool_id IS '한도 풀 아이디';
ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT IF EXISTS card_evidence_link_ck_2;
ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT IF EXISTS card_evidence_link_natural_key;
ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_natural_key UNIQUE NULLS NOT DISTINCT
    (card_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, pool_id, ev_item_cd, ev_item_key, evidence_id);
ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_ck_2 CHECK (
        CASE ev_subject_cd
            WHEN 'CARD' THEN num_nonnulls(card_bnft_id, rule_key, relation_key, pool_id) = 0
            WHEN 'BNFT' THEN card_bnft_id IS NOT NULL AND num_nonnulls(rule_key, relation_key, pool_id) = 0
            WHEN 'RULE' THEN card_bnft_id IS NOT NULL AND rule_key IS NOT NULL
                             AND num_nonnulls(relation_key, pool_id) = 0
            WHEN 'POOL' THEN pool_id IS NOT NULL AND num_nonnulls(card_bnft_id, rule_key, relation_key) = 0
            WHEN 'REL' THEN card_bnft_id IS NOT NULL AND relation_key IS NOT NULL
                            AND num_nonnulls(rule_key, pool_id) = 0
            ELSE false
        END);
INSERT INTO db_pipeline.card_evidence_link (card_id, ev_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, pool_id, ev_item_cd, ev_item_key, evidence_id)
SELECT card_id, ev_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, pool_id, ev_item_cd, ev_item_key, evidence_id
FROM db_pipeline_backup.card_evidence_link_pre_simplify_20261102
WHERE ev_subject_cd = 'POOL'
ON CONFLICT (card_id, ev_link_id) DO NOTHING;
-- 5. 이전 뷰 복구.
CREATE VIEW db_pipeline.v_card_rule_pool AS
SELECT card_id, card_bnft_id, rule_key, pool_id, pool_role_cd
FROM db_pipeline.card_bnft_rule_pool;

COMMENT ON VIEW db_pipeline.v_card_rule_pool IS '규칙↔한도 풀 연결 테이블 조회';

CREATE VIEW db_pipeline.v_card_bnft_rel AS
SELECT b.card_id, b.card_bnft_id AS from_bnft_id,
       x.value->>'to_bnft_id' AS to_bnft_id,
       x.value->>'relation_key' AS relation_key,
       x.value->>'rel_type_cd' AS rel_type_cd,
       x.value->>'trigger_pool_id' AS trigger_pool_id,
       (x.value->>'rel_priority')::integer AS rel_priority,
       false AS reverse_yn
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) AS x(value)
UNION ALL
SELECT b.card_id, x.value->>'to_bnft_id',
       b.card_bnft_id,
       x.value->>'relation_key',
       x.value->>'rel_type_cd',
       x.value->>'trigger_pool_id',
       (x.value->>'rel_priority')::integer,
       true
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) AS x(value)
WHERE x.value->>'rel_type_cd' = 'MUTUALLY_EXCLUSIVE';

COMMENT ON VIEW db_pipeline.v_card_bnft_rel IS '혜택 관계를 행으로 복원. MUTUALLY_EXCLUSIVE는 reverse_yn=true 행을 더해 양방향 제공. 저장 행 조회는 reverse_yn=false';

CREATE VIEW db_pipeline.v_card_limit_tier AS
SELECT p.card_id, p.pool_id, p.pool_scope_cd, p.period_cd, p.cap_unit_cd,
       p.aggregation_key_cd,
       t.value->>'tier_key' AS tier_key,
       (t.value->>'tier_priority')::integer AS tier_priority,
       t.value->>'predicate_state_cd' AS predicate_state_cd,
       (t.value->>'limit_num')::numeric(18,2) AS limit_num,
       db_pipeline.fn_cond_spend_bound(t.value->'cond_expr', 'cond_min_amt') AS spend_min_amt,
       db_pipeline.fn_cond_spend_bound(t.value->'cond_expr', 'cond_max_amt_excl') AS spend_max_amt_excl,
       t.value->'cond_expr' AS cond_expr
FROM db_pipeline.card_limit_pool p
CROSS JOIN LATERAL jsonb_array_elements(p.tier_list) AS t(value);

COMMENT ON VIEW db_pipeline.v_card_limit_tier IS '한도 풀 구간을 행으로 복원';

CREATE VIEW db_pipeline.v_card_cond_atom AS
WITH src AS (
    SELECT 'CARD'::text AS owner_cd, p.card_id, NULL::varchar AS card_bnft_id,
           NULL::text AS rule_key, NULL::varchar AS pool_id, NULL::text AS item_key,
           p.card_cond_expr AS expr
    FROM db_pipeline.card_product p WHERE p.card_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'BNFT', b.card_id, b.card_bnft_id, NULL, NULL, NULL, b.bnft_cond_expr
    FROM db_pipeline.card_bnft b WHERE b.bnft_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'RULE', r.card_id, r.card_bnft_id, r.rule_key, NULL, NULL, r.cond_expr
    FROM db_pipeline.v_card_rule r WHERE r.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'POOL_TIER', t.card_id, NULL, NULL, t.pool_id, t.tier_key, t.cond_expr
    FROM db_pipeline.v_card_limit_tier t WHERE t.cond_expr IS NOT NULL
)
SELECT s.owner_cd, s.card_id, s.card_bnft_id, s.rule_key, s.pool_id, s.item_key,
       s.expr->>'expr_status_cd' AS expr_status_cd,
       (b.value->>'branch_no')::integer AS branch_no,
       (a.value->>'atom_seq')::integer AS atom_seq,
       a.value->>'atom_key' AS atom_key,
       (a.value->>'negate_yn')::boolean AS negate_yn,
       a.value->>'cond_type_cd' AS cond_type_cd,
       a.value->>'cond_basis_cd' AS cond_basis_cd,
       (a.value->>'cond_min_amt')::numeric(18,2) AS cond_min_amt,
       (a.value->>'cond_max_amt_excl')::numeric(18,2) AS cond_max_amt_excl,
       a.value->>'predicate_method_cd' AS predicate_method_cd,
       (a.value->>'predicate_method_ver')::integer AS predicate_method_ver,
       a.value->'cond_params' AS cond_params,
       a.value->>'card_excl_item_id' AS card_excl_item_id,
       a.value->>'excl_raw_txt' AS excl_raw_txt,
       a.value->>'cond_raw_txt' AS cond_raw_txt,
       a.value->>'link_role_cd' AS link_role_cd,
       a.value->>'cond_status_cd' AS cond_status_cd
FROM src s
CROSS JOIN LATERAL jsonb_array_elements(s.expr->'branches') AS b(value)
CROSS JOIN LATERAL jsonb_array_elements(b.value->'atoms') AS a(value);

COMMENT ON VIEW db_pipeline.v_card_cond_atom IS '모든 조건식의 atom을 소유자와 함께 행으로 복원';

CREATE VIEW db_pipeline.v_common_cd_usage AS
SELECT 'card_product.card_kind_cd'::text AS source_nm, 'CARD_KIND'::varchar(20) AS common_code_grp_id, card_kind_cd::text AS cd_value
FROM db_pipeline.card_product WHERE card_kind_cd IS NOT NULL
UNION ALL
SELECT 'card_product.product_status_cd'::text AS source_nm, 'PRODUCT_STATUS'::varchar(20) AS common_code_grp_id, product_status_cd::text AS cd_value
FROM db_pipeline.card_product WHERE product_status_cd IS NOT NULL
UNION ALL
SELECT 'card_product.card_cond_status_cd'::text AS source_nm, 'ITEM_STATUS'::varchar(20) AS common_code_grp_id, card_cond_status_cd::text AS cd_value
FROM db_pipeline.card_product WHERE card_cond_status_cd IS NOT NULL
UNION ALL
SELECT 'card_product_doc.doc_role_cd'::text AS source_nm, 'DOC_ROLE'::varchar(20) AS common_code_grp_id, doc_role_cd::text AS cd_value
FROM db_pipeline.card_product_doc WHERE doc_role_cd IS NOT NULL
UNION ALL
SELECT 'card_product_doc.approval_status_cd'::text AS source_nm, 'APPROVAL_STATUS'::varchar(20) AS common_code_grp_id, approval_status_cd::text AS cd_value
FROM db_pipeline.card_product_doc WHERE approval_status_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.bnft_type_cd'::text AS source_nm, 'BNFT_TYPE'::varchar(20) AS common_code_grp_id, bnft_type_cd::text AS cd_value
FROM db_pipeline.card_bnft WHERE bnft_type_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.bnft_origin_cd'::text AS source_nm, 'BNFT_ORIGIN'::varchar(20) AS common_code_grp_id, bnft_origin_cd::text AS cd_value
FROM db_pipeline.card_bnft WHERE bnft_origin_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.bnft_scope_cd'::text AS source_nm, 'BNFT_SCOPE'::varchar(20) AS common_code_grp_id, bnft_scope_cd::text AS cd_value
FROM db_pipeline.card_bnft WHERE bnft_scope_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_select_cd'::text AS source_nm, 'RULE_SELECT'::varchar(20) AS common_code_grp_id, rule_select_cd::text AS cd_value
FROM db_pipeline.card_bnft WHERE rule_select_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.verification_status_cd'::text AS source_nm, 'VERIFY_STATUS'::varchar(20) AS common_code_grp_id, verification_status_cd::text AS cd_value
FROM db_pipeline.card_bnft WHERE verification_status_cd IS NOT NULL
UNION ALL
SELECT 'card_limit_pool.pool_scope_cd'::text AS source_nm, 'LIMIT_SCOPE'::varchar(20) AS common_code_grp_id, pool_scope_cd::text AS cd_value
FROM db_pipeline.card_limit_pool WHERE pool_scope_cd IS NOT NULL
UNION ALL
SELECT 'card_limit_pool.period_cd'::text AS source_nm, 'LIMIT_PERIOD'::varchar(20) AS common_code_grp_id, period_cd::text AS cd_value
FROM db_pipeline.card_limit_pool WHERE period_cd IS NOT NULL
UNION ALL
SELECT 'card_limit_pool.cap_unit_cd'::text AS source_nm, 'LIMIT_UNIT'::varchar(20) AS common_code_grp_id, cap_unit_cd::text AS cd_value
FROM db_pipeline.card_limit_pool WHERE cap_unit_cd IS NOT NULL
UNION ALL
SELECT 'card_limit_pool.aggregation_key_cd'::text AS source_nm, 'LIMIT_AGG'::varchar(20) AS common_code_grp_id, aggregation_key_cd::text AS cd_value
FROM db_pipeline.card_limit_pool WHERE aggregation_key_cd IS NOT NULL
UNION ALL
SELECT 'card_source_evidence.approval_status_cd'::text AS source_nm, 'APPROVAL_STATUS'::varchar(20) AS common_code_grp_id, approval_status_cd::text AS cd_value
FROM db_pipeline.card_source_evidence WHERE approval_status_cd IS NOT NULL
UNION ALL
SELECT 'card_evidence_link.ev_subject_cd'::text AS source_nm, 'EV_SUBJECT'::varchar(20) AS common_code_grp_id, ev_subject_cd::text AS cd_value
FROM db_pipeline.card_evidence_link WHERE ev_subject_cd IS NOT NULL
UNION ALL
SELECT 'card_evidence_link.ev_item_cd'::text AS source_nm, 'EV_ITEM'::varchar(20) AS common_code_grp_id, ev_item_cd::text AS cd_value
FROM db_pipeline.card_evidence_link WHERE ev_item_cd IS NOT NULL
UNION ALL
SELECT 'card_doc.doc_type_cd'::text AS source_nm, 'DOC_TYPE'::varchar(20) AS common_code_grp_id, doc_type_cd::text AS cd_value
FROM db_pipeline.card_doc WHERE doc_type_cd IS NOT NULL
UNION ALL
SELECT 'card_doc.doc_status'::text AS source_nm, 'DOC_STATUS'::varchar(20) AS common_code_grp_id, doc_status::text AS cd_value
FROM db_pipeline.card_doc WHERE doc_status IS NOT NULL
UNION ALL
SELECT 'card_doc_page.page_layer_cd'::text AS source_nm, 'PAGE_LAYER'::varchar(20) AS common_code_grp_id, page_layer_cd::text AS cd_value
FROM db_pipeline.card_doc_page WHERE page_layer_cd IS NOT NULL
UNION ALL
SELECT 'card_doc_chunk.chunk_type_cd'::text AS source_nm, 'CHUNK_TYPE'::varchar(20) AS common_code_grp_id, chunk_type_cd::text AS cd_value
FROM db_pipeline.card_doc_chunk WHERE chunk_type_cd IS NOT NULL
UNION ALL
SELECT 'card_doc_chunk.chunk_status'::text AS source_nm, 'CHUNK_STATUS'::varchar(20) AS common_code_grp_id, chunk_status::text AS cd_value
FROM db_pipeline.card_doc_chunk WHERE chunk_status IS NOT NULL
UNION ALL
SELECT 'card_ai_run.run_stage_cd'::text AS source_nm, 'RUN_STAGE'::varchar(20) AS common_code_grp_id, run_stage_cd::text AS cd_value
FROM db_pipeline.card_ai_run WHERE run_stage_cd IS NOT NULL
UNION ALL
SELECT 'card_ai_run.run_call_mthd_cd'::text AS source_nm, 'RUN_CALL_METHOD'::varchar(20) AS common_code_grp_id, run_call_mthd_cd::text AS cd_value
FROM db_pipeline.card_ai_run WHERE run_call_mthd_cd IS NOT NULL
UNION ALL
SELECT 'card_ai_run.run_status'::text AS source_nm, 'RUN_STATUS'::varchar(20) AS common_code_grp_id, run_status::text AS cd_value
FROM db_pipeline.card_ai_run WHERE run_status IS NOT NULL
UNION ALL
SELECT 'card_ai_call.call_status'::text AS source_nm, 'CALL_STATUS'::varchar(20) AS common_code_grp_id, call_status::text AS cd_value
FROM db_pipeline.card_ai_call WHERE call_status IS NOT NULL
UNION ALL
SELECT 'card_extr_stg.stg_kind_cd'::text AS source_nm, 'STG_KIND'::varchar(20) AS common_code_grp_id, stg_kind_cd::text AS cd_value
FROM db_pipeline.card_extr_stg WHERE stg_kind_cd IS NOT NULL
UNION ALL
SELECT 'card_extr_stg.stg_status'::text AS source_nm, 'STG_STATUS'::varchar(20) AS common_code_grp_id, stg_status::text AS cd_value
FROM db_pipeline.card_extr_stg WHERE stg_status IS NOT NULL
UNION ALL
SELECT 'card_extr_stg.stg_ai_vrfy_cd'::text AS source_nm, 'STG_AI_VRFY'::varchar(20) AS common_code_grp_id, stg_ai_vrfy_cd::text AS cd_value
FROM db_pipeline.card_extr_stg WHERE stg_ai_vrfy_cd IS NOT NULL
UNION ALL
SELECT 'card_product.brand_opt_list[].brand_cd', 'BRAND', brand_cd::text
FROM db_pipeline.v_card_brand_opt WHERE brand_cd IS NOT NULL
UNION ALL
SELECT 'card_product.brand_opt_list[].service_grade_cd', 'SERVICE_GRADE', service_grade_cd::text
FROM db_pipeline.v_card_brand_opt WHERE service_grade_cd IS NOT NULL
UNION ALL
SELECT 'card_product.brand_opt_list[].service_type_cd', 'SERVICE_TYPE', service_type_cd::text
FROM db_pipeline.v_card_brand_opt WHERE service_type_cd IS NOT NULL
UNION ALL
SELECT 'card_product.brand_opt_list[].brand_opt_status_cd', 'PRODUCT_STATUS', brand_opt_status_cd::text
FROM db_pipeline.v_card_brand_opt WHERE brand_opt_status_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_list[].predicate_state_cd', 'PREDICATE_STATE', predicate_state_cd::text
FROM db_pipeline.v_card_rule WHERE predicate_state_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_list[].calc_method_cd', 'CALC_METHOD', calc_method_cd::text
FROM db_pipeline.v_card_rule WHERE calc_method_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_list[].value_unit_cd', 'VALUE_UNIT', value_unit_cd::text
FROM db_pipeline.v_card_rule WHERE value_unit_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_list[].payout_unit_cd', 'PAYOUT_UNIT', payout_unit_cd::text
FROM db_pipeline.v_card_rule WHERE payout_unit_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_list[].rule_status_cd', 'ITEM_STATUS', rule_status_cd::text
FROM db_pipeline.v_card_rule WHERE rule_status_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft_rule_pool.pool_role_cd', 'POOL_ROLE', pool_role_cd::text
FROM db_pipeline.v_card_rule_pool WHERE pool_role_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.relation_list[].rel_type_cd', 'REL_TYPE', rel_type_cd::text
FROM db_pipeline.v_card_bnft_rel WHERE rel_type_cd IS NOT NULL AND NOT reverse_yn
UNION ALL
SELECT 'rule_list[].target_list[].target_type_cd', 'TARGET_TYPE', target_type_cd::text
FROM db_pipeline.v_card_rule_target WHERE target_type_cd IS NOT NULL
UNION ALL
SELECT 'card_limit_pool.tier_list[].predicate_state_cd', 'PREDICATE_STATE', predicate_state_cd::text
FROM db_pipeline.v_card_limit_tier WHERE predicate_state_cd IS NOT NULL
UNION ALL
SELECT 'cond_expr atom cond_type_cd', 'COND_TYPE', cond_type_cd::text
FROM db_pipeline.v_card_cond_atom WHERE cond_type_cd IS NOT NULL
UNION ALL
SELECT 'cond_expr atom cond_basis_cd', 'COND_BASIS', cond_basis_cd::text
FROM db_pipeline.v_card_cond_atom WHERE cond_basis_cd IS NOT NULL
UNION ALL
SELECT 'cond_expr atom predicate_method_cd', 'PREDICATE_METHOD', predicate_method_cd::text
FROM db_pipeline.v_card_cond_atom WHERE predicate_method_cd IS NOT NULL
UNION ALL
SELECT 'cond_expr atom cond_status_cd', 'ITEM_STATUS', cond_status_cd::text
FROM db_pipeline.v_card_cond_atom WHERE cond_status_cd IS NOT NULL
UNION ALL
SELECT 'cond_expr.expr_status_cd', 'ITEM_STATUS', expr_status_cd::text
FROM db_pipeline.v_card_cond_atom WHERE expr_status_cd IS NOT NULL;

COMMENT ON VIEW db_pipeline.v_common_cd_usage IS '모든 공통코드 사용처(물리 컬럼·JSONB 키)와 소속 그룹. 공통코드 정합성 검증의 기준';

CREATE VIEW db_pipeline.v_card_integrity_issue AS
WITH atoms AS (SELECT * FROM db_pipeline.v_card_cond_atom),
-- 방식별 필수값. 지급 단위는 포인트·마일리지일 수 있어 정액·금액당 방식의 단위를 특정 값으로 제한하지 않는다.
-- final_yn이 true면 확정 데이터의 무결성 위반, false면 확정 전 값 누락이다. 값을 보완하지 않고 구분만 한다.
rule_value_gap AS (
    SELECT r.card_id, r.card_bnft_id, r.rule_key,
           (r.rule_status_cd = 'CONFIRMED' OR b.verification_status_cd = 'CONFIRMED') AS final_yn
    FROM db_pipeline.v_card_rule r
    JOIN db_pipeline.card_bnft b ON (b.card_id, b.card_bnft_id) = (r.card_id, r.card_bnft_id)
    WHERE r.rule_status_cd <> 'RETIRED'
      AND ((r.calc_method_cd IN ('PERCENT_OF_TXN', 'FIXED_PER_TXN', 'UNITS_PER_AMOUNT', 'MULTIPLY_EXTERNAL_POINTS') AND r.value_num IS NULL)
           OR (r.calc_method_cd = 'UNITS_PER_AMOUNT' AND r.basis_amt IS NULL)
           OR (r.calc_method_cd = 'PERCENT_OF_TXN' AND r.value_unit_cd IS DISTINCT FROM 'PERCENT')
           OR (r.calc_method_cd = 'MULTIPLY_EXTERNAL_POINTS' AND r.value_unit_cd IS DISTINCT FROM 'MULTIPLIER')
           OR (r.calc_method_cd IN ('FIXED_PER_TXN', 'UNITS_PER_AMOUNT') AND r.value_unit_cd IN ('PERCENT', 'MULTIPLIER')))
),
-- 필수 파라미터가 정해진 판정 방식만 검사한다. cond_params를 모든 조건에 강제하지 않는다.
predicate_param_gap AS (
    SELECT a.owner_cd, a.card_id, a.atom_key,
           (a.cond_status_cd = 'CONFIRMED' OR a.expr_status_cd = 'CONFIRMED') AS final_yn
    FROM atoms a
    WHERE a.cond_status_cd <> 'RETIRED'
      AND ((a.predicate_method_cd = 'EVERY_MONTH_MIN_SPEND'
            AND (a.cond_min_amt IS NULL OR jsonb_typeof(a.cond_params->'window_months') IS DISTINCT FROM 'number'))
           OR (a.predicate_method_cd = 'MONTH_IN'
               AND CASE WHEN jsonb_typeof(a.cond_params->'months') = 'array'
                        THEN jsonb_array_length(a.cond_params->'months') = 0 ELSE true END))
),
fallback AS (
    SELECT card_id, from_bnft_id, to_bnft_id
    FROM db_pipeline.v_card_bnft_rel
    WHERE rel_type_cd = 'FALLBACK_AFTER_CAP' AND NOT reverse_yn
),
cycle AS (
    WITH RECURSIVE walk(card_id, start_id, cur_id, path) AS (
        SELECT card_id, from_bnft_id, to_bnft_id, ARRAY[from_bnft_id, to_bnft_id]
        FROM fallback
        UNION ALL
        SELECT w.card_id, w.start_id, f.to_bnft_id, w.path || f.to_bnft_id
        FROM walk w
        JOIN fallback f ON (f.card_id, f.from_bnft_id) = (w.card_id, w.cur_id)
        WHERE NOT f.to_bnft_id = ANY (w.path[2:])
    )
    SELECT DISTINCT card_id, start_id FROM walk WHERE cur_id = start_id
)
SELECT 'bnft_without_product' AS gate_cd, x.card_id || '/' || x.card_bnft_id AS issue_key
FROM db_pipeline.card_bnft x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = x.card_id)
UNION ALL
SELECT 'local_confirmed_without_rule', x.card_id || '/' || x.card_bnft_id
FROM db_pipeline.card_bnft x
WHERE x.verification_status_cd = 'CONFIRMED' AND jsonb_array_length(x.rule_list) = 0
UNION ALL
SELECT 'pool_without_product', x.card_id || '/' || x.pool_id
FROM db_pipeline.card_limit_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = x.card_id)
UNION ALL
SELECT 'pool_ref_orphan', x.card_id || '/' || x.rule_key || '/' || x.pool_id
FROM db_pipeline.v_card_rule_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id, p.pool_id) = (x.card_id, x.pool_id))
UNION ALL
SELECT 'rule_pool_product_orphan', x.card_id || '/' || x.card_bnft_id || '/' || x.rule_key || '/' || x.pool_id
FROM db_pipeline.card_bnft_rule_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id=x.card_id)
UNION ALL
SELECT 'rule_pool_benefit_orphan', x.card_id || '/' || x.card_bnft_id || '/' || x.rule_key || '/' || x.pool_id
FROM db_pipeline.card_bnft_rule_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id,b.card_bnft_id)=(x.card_id,x.card_bnft_id))
UNION ALL
SELECT 'rule_pool_rule_orphan', x.card_id || '/' || x.card_bnft_id || '/' || x.rule_key || '/' || x.pool_id
FROM db_pipeline.card_bnft_rule_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.v_card_rule r WHERE (r.card_id,r.card_bnft_id,r.rule_key)=(x.card_id,x.card_bnft_id,x.rule_key))
UNION ALL
SELECT 'rel_to_bnft_orphan', x.card_id || '/' || x.relation_key
FROM db_pipeline.v_card_bnft_rel x
WHERE NOT x.reverse_yn
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id, b.card_bnft_id) = (x.card_id, x.to_bnft_id))
UNION ALL
SELECT 'rel_trigger_pool_orphan', x.card_id || '/' || x.relation_key
FROM db_pipeline.v_card_bnft_rel x
WHERE NOT x.reverse_yn AND x.trigger_pool_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id, p.pool_id) = (x.card_id, x.trigger_pool_id))
UNION ALL
SELECT 'rel_mutual_stored_twice', a.card_id || '/' || a.from_bnft_id || '/' || a.to_bnft_id
FROM db_pipeline.v_card_bnft_rel a
JOIN db_pipeline.v_card_bnft_rel b
  ON (a.card_id, a.from_bnft_id, a.to_bnft_id, a.rel_type_cd) = (b.card_id, b.to_bnft_id, b.from_bnft_id, b.rel_type_cd)
WHERE NOT a.reverse_yn AND NOT b.reverse_yn AND a.rel_type_cd = 'MUTUALLY_EXCLUSIVE' AND a.from_bnft_id < a.to_bnft_id
UNION ALL
SELECT 'rel_fallback_cycle', c.card_id || '/' || c.start_id FROM cycle c
UNION ALL
SELECT 'product_doc_without_product', x.card_id || '/' || x.card_doc_id
FROM db_pipeline.card_product_doc x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = x.card_id)
UNION ALL
SELECT 'product_doc_orphan', x.card_id || '/' || x.card_doc_id
FROM db_pipeline.card_product_doc x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc d WHERE d.card_doc_id = x.card_doc_id)
UNION ALL
SELECT 'bnft_brand_opt_unknown', b.card_id || '/' || b.card_bnft_id || '/' || o.cd
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) AS o(cd)
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.v_card_brand_opt v WHERE v.card_id = b.card_id AND v.brand_opt_cd = o.cd)
UNION ALL
SELECT 'doc_brand_opt_unknown', d.card_id || '/' || d.card_doc_id || '/' || o.cd
FROM db_pipeline.card_product_doc d
CROSS JOIN LATERAL unnest(d.brand_opt_cds) AS o(cd)
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.v_card_brand_opt v WHERE v.card_id = d.card_id AND v.brand_opt_cd = o.cd)
UNION ALL
SELECT CASE WHEN g.final_yn THEN 'rule_method_value_missing' ELSE 'rule_method_value_pending' END,
       g.card_id || '/' || g.card_bnft_id || '/' || g.rule_key
FROM rule_value_gap g
UNION ALL
SELECT CASE WHEN g.final_yn THEN 'predicate_params_missing' ELSE 'predicate_params_pending' END,
       g.owner_cd || '/' || g.card_id || '/' || g.atom_key
FROM predicate_param_gap g
UNION ALL
SELECT 'excl_item_unknown', a.owner_cd || '/' || a.atom_key
FROM atoms a
WHERE a.card_excl_item_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_excl_item i WHERE i.card_excl_item_id = a.card_excl_item_id)
UNION ALL
SELECT 'evidence_source_orphan', e.evidence_id
FROM db_pipeline.card_source_evidence e
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc_chunk c WHERE (c.card_doc_id, c.page_no, c.card_doc_chunk_id) = (e.card_doc_id, e.page_no, e.card_doc_chunk_id))
UNION ALL
SELECT 'evidence_doc_not_linked', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_evidence_link l
JOIN db_pipeline.card_source_evidence e USING (evidence_id)
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc d WHERE (d.card_id, d.card_doc_id) = (l.card_id, e.card_doc_id))
UNION ALL
SELECT 'evidence_not_approved', l.evidence_id
FROM (SELECT DISTINCT evidence_id FROM db_pipeline.card_evidence_link) l
LEFT JOIN db_pipeline.card_source_evidence e USING (evidence_id)
WHERE e.evidence_id IS NULL OR e.approval_status_cd <> 'APPROVED'
UNION ALL
SELECT 'evidence_subject_orphan', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_evidence_link l
WHERE NOT CASE l.ev_subject_cd
    WHEN 'CARD' THEN EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = l.card_id)
    WHEN 'BNFT' THEN EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id, b.card_bnft_id) = (l.card_id, l.card_bnft_id))
    WHEN 'RULE' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_rule r WHERE (r.card_id, r.card_bnft_id, r.rule_key) = (l.card_id, l.card_bnft_id, l.rule_key))
    WHEN 'POOL' THEN EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id, p.pool_id) = (l.card_id, l.pool_id))
    WHEN 'REL' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_bnft_rel r WHERE NOT r.reverse_yn AND (r.card_id, r.from_bnft_id, r.relation_key) = (l.card_id, l.card_bnft_id, l.relation_key))
    ELSE false
END
UNION ALL
SELECT 'evidence_item_key_missing', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_evidence_link l
WHERE l.ev_item_cd <> 'SELF' AND NOT CASE l.ev_item_cd
    WHEN 'COND' THEN EXISTS (SELECT 1 FROM atoms a WHERE a.card_id = l.card_id AND a.atom_key = l.ev_item_key
                             AND a.card_bnft_id IS NOT DISTINCT FROM l.card_bnft_id AND a.rule_key IS NOT DISTINCT FROM l.rule_key AND a.pool_id IS NOT DISTINCT FROM l.pool_id)
    WHEN 'TARGET' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_rule_target t WHERE (t.card_id, t.card_bnft_id, t.rule_key) = (l.card_id, l.card_bnft_id, l.rule_key) AND t.target_key = l.ev_item_key)
    WHEN 'TIER' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_limit_tier t WHERE (t.card_id, t.pool_id) = (l.card_id, l.pool_id) AND t.tier_key = l.ev_item_key)
    ELSE false
END
UNION ALL
SELECT 'product_doc_role_type_mismatch', x.card_id || '/' || x.card_doc_id
FROM db_pipeline.card_product_doc x
JOIN db_pipeline.card_doc d ON d.card_doc_id = x.card_doc_id
WHERE x.doc_role_cd = 'BRAND_SERVICE' AND d.doc_type_cd <> 'BRAND_SERVICE'
UNION ALL
SELECT 'shared_doc_bound_to_card', d.card_doc_id
FROM db_pipeline.card_doc d
WHERE d.card_id IS NOT NULL AND d.doc_type_cd IN ('BRAND_SERVICE', 'TERMS')
UNION ALL
SELECT 'brand_doc_option_conflict', z.card_doc_id
FROM (SELECT x.card_doc_id
      FROM db_pipeline.card_product_doc x
      CROSS JOIN LATERAL unnest(x.brand_opt_cds) AS o(cd)
      JOIN db_pipeline.v_card_brand_opt v ON (v.card_id, v.brand_opt_cd) = (x.card_id, o.cd)
      WHERE x.doc_role_cd = 'BRAND_SERVICE'
      GROUP BY 1 HAVING count(DISTINCT (v.brand_cd, v.service_grade_cd, v.service_type_cd)) > 1) z
UNION ALL
SELECT 'brand_bnft_doc_not_linked', b.card_id || '/' || b.card_bnft_id || '/' || o.cd
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) AS o(cd)
WHERE b.bnft_origin_cd = 'BRAND_SERVICE'
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc x
                  WHERE x.card_id = b.card_id AND x.doc_role_cd = 'BRAND_SERVICE' AND o.cd = ANY (x.brand_opt_cds))
UNION ALL
SELECT 'brand_bnft_confirmed_without_evidence', b.card_id || '/' || b.card_bnft_id
FROM db_pipeline.card_bnft b
WHERE b.bnft_origin_cd = 'BRAND_SERVICE' AND b.verification_status_cd = 'CONFIRMED'
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_evidence_link l
                  WHERE (l.card_id, l.card_bnft_id) = (b.card_id, b.card_bnft_id))
UNION ALL
SELECT 'evidence_brand_opt_mismatch', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_evidence_link l
JOIN db_pipeline.card_source_evidence e USING (evidence_id)
JOIN db_pipeline.card_bnft b ON (b.card_id, b.card_bnft_id) = (l.card_id, l.card_bnft_id)
JOIN db_pipeline.card_product_doc x ON (x.card_id, x.card_doc_id) = (l.card_id, e.card_doc_id)
WHERE x.doc_role_cd = 'BRAND_SERVICE' AND NOT (coalesce(b.bnft_brand_opt_cds, '{}') && x.brand_opt_cds)
UNION ALL
SELECT 'stg_card_not_linked', s.card_extr_stg_id
FROM db_pipeline.card_extr_stg s
WHERE s.card_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc x WHERE (x.card_id, x.card_doc_id) = (s.card_id, s.card_doc_id))
UNION ALL
SELECT 'common_cd_invalid', u.source_nm || '=' || u.cd_value
FROM db_pipeline.v_common_cd_usage u
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd c WHERE (c.common_code_grp_id, c.common_cd) = (u.common_code_grp_id, u.cd_value))
UNION ALL
SELECT 'common_cd_group_orphan', c.common_code_grp_id || '/' || c.common_cd
FROM db_pipeline.common_cd c
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.common_code_grp g WHERE g.common_code_grp_id = c.common_code_grp_id)
UNION ALL
SELECT 'common_code_grp_empty', g.common_code_grp_id
FROM db_pipeline.common_code_grp g
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd c WHERE c.common_code_grp_id = g.common_code_grp_id);

COMMENT ON VIEW db_pipeline.v_card_integrity_issue IS '승인 전 정합성 게이트. 물리 FK가 없으므로 행이 1건이라도 있으면 승인하지 않음. *_pending은 확정 전 항목의 값 누락(검토 대기)이고 나머지는 무결성 위반';

COMMIT;
