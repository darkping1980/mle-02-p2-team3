-- 연결 테이블 V7 -> 기존 JSON 참조 V7. 단일 트랜잭션.
BEGIN;
SET LOCAL lock_timeout = '10s';
LOCK TABLE db_pipeline.card_bnft,db_pipeline.card_limit_pool,db_pipeline.card_bnft_rule_pool IN SHARE ROW EXCLUSIVE MODE;
DROP VIEW db_pipeline.v_card_integrity_issue;
DROP VIEW db_pipeline.v_common_cd_usage;
DROP VIEW db_pipeline.v_card_bnft_rule_effective;
DROP VIEW db_pipeline.v_card_cond_atom;
DROP VIEW db_pipeline.v_card_rule_target;
DROP VIEW db_pipeline.v_card_rule_pool;
DROP VIEW db_pipeline.v_card_rule;
CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_rule_list(p_list jsonb, p_owner text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
DECLARE
    v_rule jsonb;
    v_ref jsonb;
    v_keys text[] := '{}';
    v_pools text[];
    v_state text;
BEGIN
    IF jsonb_typeof(p_list) IS DISTINCT FROM 'array' THEN
        RETURN false;
    END IF;
    FOR v_rule IN SELECT value FROM jsonb_array_elements(p_list) LOOP
        IF jsonb_typeof(v_rule) <> 'object'
           OR coalesce(v_rule->>'rule_key', '') !~ '^[A-Za-z0-9_.:-]{1,40}$'
           OR v_rule->>'rule_key' = ANY (v_keys)
           OR coalesce(v_rule->>'calc_method_cd', '') = ''
           OR coalesce(v_rule->>'payout_unit_cd', '') = ''
           OR coalesce(v_rule->>'rule_status_cd', '') = ''
           OR jsonb_typeof(v_rule->'method_ver') IS DISTINCT FROM 'number'
           OR (v_rule->>'method_ver')::integer < 1 THEN
            RETURN false;
        END IF;
        v_keys := v_keys || (v_rule->>'rule_key');

        IF coalesce(jsonb_typeof(v_rule->'value_num'), 'null') NOT IN ('number','null')
           OR coalesce(jsonb_typeof(v_rule->'basis_amt'), 'null') NOT IN ('number','null')
           OR coalesce(jsonb_typeof(v_rule->'rule_priority'), 'null') NOT IN ('number','null')
           OR coalesce(jsonb_typeof(v_rule->'calc_params'), 'null') NOT IN ('object','null') THEN
            RETURN false;
        END IF;
        IF coalesce((v_rule->>'value_num')::numeric, 0) < 0
           OR coalesce((v_rule->>'basis_amt')::numeric, 0) < 0 THEN
            RETURN false;
        END IF;

        v_state := v_rule->>'predicate_state_cd';
        IF NOT db_pipeline.fn_valid_cond_expr(nullif(v_rule->'cond_expr', 'null'::jsonb)) THEN
            RETURN false;
        END IF;
        IF v_state = 'CONDITIONAL' AND coalesce(jsonb_typeof(v_rule->'cond_expr'), 'null') = 'null' THEN
            RETURN false;
        END IF;
        IF v_state = 'VERIFIED_UNCONDITIONAL' AND coalesce(jsonb_typeof(v_rule->'cond_expr'), 'null') <> 'null' THEN
            RETURN false;
        END IF;
        IF coalesce(v_state, '') = '' THEN
            RETURN false;
        END IF;

        IF NOT db_pipeline.fn_valid_target_list(coalesce(v_rule->'target_list', '[]'::jsonb)) THEN
            RETURN false;
        END IF;
        IF v_rule->>'rule_status_cd' = 'CONFIRMED'
           AND coalesce(jsonb_array_length(v_rule->'target_list'), 0) = 0 THEN
            RETURN false;
        END IF;

        IF p_owner = 'LOCAL' THEN
            IF jsonb_typeof(coalesce(v_rule->'pool_refs', '[]'::jsonb)) <> 'array' THEN
                RETURN false;
            END IF;
            v_pools := '{}';
            FOR v_ref IN SELECT value FROM jsonb_array_elements(coalesce(v_rule->'pool_refs', '[]'::jsonb)) LOOP
                IF jsonb_typeof(v_ref) <> 'object'
                   OR coalesce(v_ref->>'pool_id', '') = ''
                   OR coalesce(v_ref->>'pool_role_cd', '') = ''
                   OR v_ref->>'pool_id' = ANY (v_pools) THEN
                    RETURN false;
                END IF;
                v_pools := v_pools || (v_ref->>'pool_id');
            END LOOP;
        ELSE
            RETURN false;
        END IF;
    END LOOP;
    RETURN true;
END;
$_$;

COMMENT ON FUNCTION db_pipeline.fn_valid_rule_list(jsonb, text) IS '계산 규칙 목록 JSONB 계약 검증. rule_key 중복, 금액 타입, 조건 상태, 대상, pool_refs 검사. p_owner는 LOCAL만 허용';


DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM db_pipeline.card_bnft_rule_pool x
  WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id=x.card_id)
     OR NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id,b.card_bnft_id)=(x.card_id,x.card_bnft_id))
     OR NOT EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id,p.pool_id)=(x.card_id,x.pool_id))
     OR NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) r(value)
                    WHERE (b.card_id,b.card_bnft_id)=(x.card_id,x.card_bnft_id) AND r.value->>'rule_key'=x.rule_key)
     OR NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd c WHERE c.common_code_grp_id='POOL_ROLE' AND c.common_cd=x.pool_role_cd))
 THEN RAISE EXCEPTION '고아 또는 미등록 규칙·한도 관계를 확인해야 합니다'; END IF;
END $$;
-- V6 표현으로 복원. 동일 규칙 안의 풀은 pool_id 순서로 재구성한다.
UPDATE db_pipeline.card_bnft b SET rule_list = x.rules
FROM (SELECT b2.card_id,b2.card_bnft_id,coalesce(jsonb_agg(
      r.value || jsonb_build_object('pool_refs',coalesce((SELECT jsonb_agg(jsonb_build_object('pool_id',p.pool_id,'pool_role_cd',p.pool_role_cd) ORDER BY p.pool_id)
      FROM db_pipeline.card_bnft_rule_pool p WHERE (p.card_id,p.card_bnft_id,p.rule_key)=(b2.card_id,b2.card_bnft_id,r.value->>'rule_key')),'[]'::jsonb))
      ORDER BY r.ord) FILTER (WHERE r.value IS NOT NULL),'[]'::jsonb) AS rules
      FROM db_pipeline.card_bnft b2 LEFT JOIN LATERAL jsonb_array_elements(b2.rule_list) WITH ORDINALITY r(value,ord) ON true
      GROUP BY b2.card_id,b2.card_bnft_id) x WHERE (b.card_id,b.card_bnft_id)=(x.card_id,x.card_bnft_id);
-- 이관 후 해당 규칙과 관계가 그대로인 행은 원래 JSON과 배열 순서까지 복원한다.
UPDATE db_pipeline.card_bnft b SET rule_list = saved.rule_list
FROM db_pipeline_v6_backup.v7_rule_list_before_pool_split saved
WHERE (b.card_id,b.card_bnft_id)=(saved.card_id,saved.card_bnft_id)
  AND (SELECT coalesce(jsonb_agg(r.value-'pool_refs' ORDER BY r.ord),'[]'::jsonb) FROM jsonb_array_elements(b.rule_list) WITH ORDINALITY r(value,ord))
   = (SELECT coalesce(jsonb_agg(r.value-'pool_refs' ORDER BY r.ord),'[]'::jsonb) FROM jsonb_array_elements(saved.rule_list) WITH ORDINALITY r(value,ord))
  AND NOT EXISTS (
      (SELECT r.value->>'rule_key',p.value->>'pool_id',p.value->>'pool_role_cd' FROM jsonb_array_elements(saved.rule_list) r(value)
       CROSS JOIN LATERAL jsonb_array_elements(coalesce(r.value->'pool_refs','[]'::jsonb)) p(value)
       EXCEPT ALL SELECT p.rule_key,p.pool_id,p.pool_role_cd FROM db_pipeline.card_bnft_rule_pool p WHERE (p.card_id,p.card_bnft_id)=(b.card_id,b.card_bnft_id))
      UNION ALL
      (SELECT p.rule_key,p.pool_id,p.pool_role_cd FROM db_pipeline.card_bnft_rule_pool p WHERE (p.card_id,p.card_bnft_id)=(b.card_id,b.card_bnft_id)
       EXCEPT ALL SELECT r.value->>'rule_key',p.value->>'pool_id',p.value->>'pool_role_cd' FROM jsonb_array_elements(saved.rule_list) r(value)
       CROSS JOIN LATERAL jsonb_array_elements(coalesce(r.value->'pool_refs','[]'::jsonb)) p(value)));
DROP TABLE db_pipeline.card_bnft_rule_pool;


CREATE VIEW db_pipeline.v_card_rule AS
SELECT b.card_id, b.card_bnft_id,
       r.value->>'rule_key' AS rule_key,
       r.ord AS rule_seq,
       nullif(r.value->'cond_expr', 'null'::jsonb) AS cond_expr,
       db_pipeline.fn_cond_spend_bound(nullif(r.value->'cond_expr', 'null'::jsonb), 'cond_min_amt')::numeric(18,2) AS spend_min_amt,
       db_pipeline.fn_cond_spend_bound(nullif(r.value->'cond_expr', 'null'::jsonb), 'cond_max_amt_excl')::numeric(18,2) AS spend_max_amt_excl,
       coalesce(r.value->'target_list', '[]'::jsonb) AS target_list,
       r.value->>'predicate_state_cd' AS predicate_state_cd,
       r.value->>'calc_method_cd' AS calc_method_cd,
       (r.value->>'method_ver')::integer AS method_ver,
       (r.value->>'value_num')::numeric(18,4) AS value_num,
       r.value->>'value_unit_cd' AS value_unit_cd,
       r.value->>'payout_unit_cd' AS payout_unit_cd,
       (r.value->>'basis_amt')::numeric(18,2) AS basis_amt,
       nullif(r.value->'calc_params', 'null'::jsonb) AS calc_params,
       (r.value->>'rule_priority')::integer AS rule_priority,
       r.value->>'rule_status_cd' AS rule_status_cd,
       coalesce(r.value->'pool_refs', '[]'::jsonb) AS pool_refs
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) WITH ORDINALITY AS r(value, ord);

COMMENT ON VIEW db_pipeline.v_card_rule IS '상품 계산 규칙을 행으로 복원. V5 card_bnft_rule 조회 대체';

CREATE VIEW db_pipeline.v_card_rule_pool AS
SELECT r.card_id, r.card_bnft_id, r.rule_key,
       p.value->>'pool_id' AS pool_id,
       p.value->>'pool_role_cd' AS pool_role_cd
FROM db_pipeline.v_card_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.pool_refs) AS p(value);

COMMENT ON VIEW db_pipeline.v_card_rule_pool IS '규칙↔한도 풀 관계를 행으로 복원. V5 card_bnft_rule_pool 조회 대체';

CREATE VIEW db_pipeline.v_card_rule_target AS
SELECT r.card_id, r.card_bnft_id, r.rule_key,
       t.value->>'target_type_cd' AS target_type_cd,
       t.value->>'target_key' AS target_key,
       t.value->>'target_nm' AS target_nm
FROM db_pipeline.v_card_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.target_list) AS t(value);

COMMENT ON VIEW db_pipeline.v_card_rule_target IS '규칙 대상을 행으로 복원';

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

CREATE VIEW db_pipeline.v_card_bnft_rule_effective AS
SELECT b.card_id, b.card_bnft_id, b.bnft_nm, b.bnft_origin_cd, b.bnft_scope_cd, b.bnft_brand_opt_cds,
       b.bnft_valid_from, b.bnft_valid_to_excl, r.rule_key,
       r.calc_method_cd, r.method_ver, r.value_num, r.value_unit_cd, r.payout_unit_cd, r.basis_amt,
       r.calc_params, r.predicate_state_cd, r.target_list,
       b.bnft_cond_expr, r.cond_expr AS rule_cond_expr, r.rule_status_cd
FROM db_pipeline.card_bnft b
JOIN db_pipeline.v_card_rule r
  ON (r.card_id, r.card_bnft_id) = (b.card_id, b.card_bnft_id);

COMMENT ON VIEW db_pipeline.v_card_bnft_rule_effective IS '혜택과 계산 규칙의 단일 출력. 제공 기간은 걸러내지 않으므로 조회 기준일로 판정. 값은 정책 후보이며 거래별 보상액이 아님';

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
SELECT 'card_bnft.rule_list[].pool_refs[].pool_role_cd', 'POOL_ROLE', pool_role_cd::text
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

UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '계산 규칙이 연결된 한도 풀을 어떤 역할로 소비하는지 구분하는 공통코드. card_bnft.rule_list[].pool_refs[].pool_role_cd에서 사용한다. 한 규칙이 영역 한도와 카드 통합 한도를 동시에 소비하는 구조를 표현하기 위한 값이며, 풀 자체의 범위는 LIMIT_SCOPE가 정한다.' WHERE common_code_grp_id='POOL_ROLE';
COMMIT;
