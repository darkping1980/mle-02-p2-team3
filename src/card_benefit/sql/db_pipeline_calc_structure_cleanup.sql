-- =====================================================================================================
-- 계산 구조 정리(2026-11-03). 고객 실적 계산·보상액 산출용 구조를 제거하고 검색·답변용 혜택 정보는 유지한다.
-- 기록: src/card_benefit/docs/schema_cleanup/  /  복구: db_pipeline_calc_structure_cleanup_rollback.sql
-- [승인 전 공유 DB 실행 금지] 격리된 로컬 테스트 DB에서 검증했다. DROP ... CASCADE를 쓰지 않는다.
--
-- 제거: v_card_bnft_rule_effective, fn_cond_spend_bound, card_excl_item(+인덱스·시퀀스), card_extr_stg.card_excl_item_id,
--       card_bnft.rule_select_cd, 정합성 게이트 rule_method_value_*·predicate_params_*·excl_item_unknown,
--       rule_list 키 predicate_state_cd, method_ver, calc_params, rule_priority, calc_method_cd, payout_unit_cd, basis_amt, 조건 atom 키 predicate_method_cd, predicate_method_ver, cond_params, card_excl_item_id, link_role_cd,
--       공통코드 그룹 PREDICATE_STATE, PREDICATE_METHOD, RULE_SELECT, LIMIT_PERIOD, LIMIT_UNIT, LIMIT_SCOPE, LIMIT_AGG, POOL_ROLE, CALC_METHOD, PAYOUT_UNIT,
--       card_extr_stg.stg_normalized_item(정제본. 등록 시 stg_raw_item에서 다시 만든다) — CHECK card_extr_stg_check1은 정제본 조건만 뺀 정의로 교체
-- 대체: v_card_rule·v_card_cond_atom(열 제거), v_common_cd_usage·v_card_integrity_issue(가지 제거),
--       fn_valid_rule_list·fn_valid_cond_expr(계산 필수 조건 제거)
-- 정제본 값 복구: 백업 폴더(backup_db_pipeline.py)의 restore_stg_normalized_item.sql. 생성 시점 지문 350건 / 4c49d051ffaa164e4d66d13632ae16ff
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
DECLARE v_n int; v_f text;
BEGIN
    IF EXISTS (SELECT 1 FROM db_pipeline.card_bnft WHERE rule_select_cd IS NOT NULL) THEN RAISE EXCEPTION 'rule_select_cd에 값이 있어 중단'; END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.card_extr_stg WHERE card_excl_item_id IS NOT NULL) THEN RAISE EXCEPTION 'card_extr_stg.card_excl_item_id에 값이 있어 중단'; END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.card_excl_item) THEN RAISE EXCEPTION 'card_excl_item에 행이 있어 중단'; END IF;
    IF (SELECT last_value FROM pg_sequences WHERE schemaname = 'db_pipeline' AND sequencename = 'seq_card_excl_item') IS NOT NULL THEN
        RAISE EXCEPTION 'seq_card_excl_item이 사용된 적이 있어 중단';
    END IF;
    -- 정제본: 백업 시점과 값이 같아야 백업 파일로 복구할 수 있다
    SELECT * INTO v_n, v_f FROM (SELECT count(*)::int, md5(coalesce(string_agg(card_extr_stg_id || ':' || stg_normalized_item::text, ',' ORDER BY card_extr_stg_id COLLATE "C"), '')) FROM db_pipeline.card_extr_stg WHERE stg_normalized_item IS NOT NULL) x;
    IF v_n <> 350 OR v_f <> '4c49d051ffaa164e4d66d13632ae16ff' THEN
        RAISE EXCEPTION '정제본 지문이 백업과 다름(% / %). 백업을 다시 만들고 SQL을 재생성하세요', v_n, v_f;
    END IF;
    -- 정제본 컬럼을 참조하는 객체는 CHECK card_extr_stg_check1 하나뿐이어야 한다(뷰·함수·인덱스·트리거 없음)
    IF EXISTS (SELECT 1 FROM pg_depend d
               WHERE d.refobjid = 'db_pipeline.card_extr_stg'::regclass
                 AND d.refobjsubid = (SELECT attnum FROM pg_attribute WHERE attrelid = 'db_pipeline.card_extr_stg'::regclass AND attname = 'stg_normalized_item')
                 AND NOT (d.classid = 'pg_constraint'::regclass
                          AND d.objid = (SELECT oid FROM pg_constraint WHERE conrelid = 'db_pipeline.card_extr_stg'::regclass AND conname = 'card_extr_stg_check1'))) THEN
        RAISE EXCEPTION 'stg_normalized_item에 다른 의존 객체가 있어 중단';
    END IF;
    IF (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'db_pipeline.card_extr_stg'::regclass AND conname = 'card_extr_stg_check1')
       IS DISTINCT FROM 'CHECK ((((stg_status)::text <> ALL (ARRAY[(''AUTO_APPROVED''::character varying)::text, (''MANUAL_APPROVED''::character varying)::text])) OR ((stg_normalized_item IS NOT NULL) AND (NOT ((stg_sql_check_cd)::text IS DISTINCT FROM ''OK''::text)) AND (stg_evidence_start_pos IS NOT NULL) AND (stg_evidence_end_pos IS NOT NULL) AND (btrim(stg_evidence_txt) <> ''''::text))))' THEN
        RAISE EXCEPTION 'card_extr_stg_check1 정의가 예상과 다름';
    END IF;
    -- 다시 만들 뷰 묶음 밖의 객체가 이 뷰들에 의존하면 중단한다(CASCADE 없이 지우기 위해).
    IF EXISTS (SELECT 1 FROM pg_depend d JOIN pg_rewrite w ON w.oid = d.objid JOIN pg_class v ON v.oid = w.ev_class
               WHERE d.refobjid IN ('db_pipeline.v_card_integrity_issue'::regclass, 'db_pipeline.v_common_cd_usage'::regclass, 'db_pipeline.v_card_bnft_rule_effective'::regclass, 'db_pipeline.v_card_rule_target'::regclass, 'db_pipeline.v_card_cond_atom'::regclass, 'db_pipeline.v_card_rule'::regclass)
                 AND v.oid <> d.refobjid
                 AND v.oid NOT IN ('db_pipeline.v_card_integrity_issue'::regclass, 'db_pipeline.v_common_cd_usage'::regclass, 'db_pipeline.v_card_bnft_rule_effective'::regclass, 'db_pipeline.v_card_rule_target'::regclass, 'db_pipeline.v_card_cond_atom'::regclass, 'db_pipeline.v_card_rule'::regclass)) THEN
        RAISE EXCEPTION '정리 대상 뷰에 의존하는 다른 객체가 있어 중단';
    END IF;
END
$pre$;
CREATE TEMP TABLE cleanup_before ON COMMIT DROP AS SELECT 'card_ai_call', count(*) FROM db_pipeline.card_ai_call UNION ALL SELECT 'card_ai_run', count(*) FROM db_pipeline.card_ai_run UNION ALL SELECT 'card_bnft', count(*) FROM db_pipeline.card_bnft UNION ALL SELECT 'card_common', count(*) FROM db_pipeline.card_common UNION ALL SELECT 'card_common_bnft', count(*) FROM db_pipeline.card_common_bnft UNION ALL SELECT 'card_common_bnft_apply', count(*) FROM db_pipeline.card_common_bnft_apply UNION ALL SELECT 'card_common_doc', count(*) FROM db_pipeline.card_common_doc UNION ALL SELECT 'card_doc', count(*) FROM db_pipeline.card_doc UNION ALL SELECT 'card_doc_chunk', count(*) FROM db_pipeline.card_doc_chunk UNION ALL SELECT 'card_doc_page', count(*) FROM db_pipeline.card_doc_page UNION ALL SELECT 'card_evidence_link', count(*) FROM db_pipeline.card_evidence_link UNION ALL SELECT 'card_extr_stg', count(*) FROM db_pipeline.card_extr_stg UNION ALL SELECT 'card_product', count(*) FROM db_pipeline.card_product UNION ALL SELECT 'card_product_doc', count(*) FROM db_pipeline.card_product_doc UNION ALL SELECT 'card_source_evidence', count(*) FROM db_pipeline.card_source_evidence;
-- 보존 지문: 정리로 바뀌지 않는 모든 컬럼(원문·청크·근거·추출 원본·병합 정보·검증 코드·실행 이력·공통서비스)
CREATE TEMP TABLE cleanup_keep ON COMMIT DROP AS
SELECT 'card_ai_call' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, call_input_sha256, call_status, call_resp_raw, call_resp_json, call_error_msg, call_input_token_cnt, call_output_token_cnt, call_latency_ms, call_req_date, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, call_input_sha256, call_status, call_resp_raw, call_resp_json, call_error_msg, call_input_token_cnt, call_output_token_cnt, call_latency_ms, call_req_date, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_ai_call
UNION ALL SELECT 'card_ai_run' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_ai_run_id, run_stage_cd, run_call_mthd_cd, run_model_nm, run_prompt_ver, run_prompt_txt, run_param, run_target_card_doc_id, run_status, run_start_date, run_end_date, run_note, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_ai_run_id, run_stage_cd, run_call_mthd_cd, run_model_nm, run_prompt_ver, run_prompt_txt, run_param, run_target_card_doc_id, run_status, run_start_date, run_end_date, run_note, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_ai_run
UNION ALL SELECT 'card_bnft' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, bnft_brand_opt_cds, relation_list, verification_status_cd, bnft_valid_from, bnft_valid_to_excl, bnft_rule_txt, bnft_limit_txt, bnft_search_txt, bnft_embedding)::text), ',' ORDER BY md5(row(card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, bnft_brand_opt_cds, relation_list, verification_status_cd, bnft_valid_from, bnft_valid_to_excl, bnft_rule_txt, bnft_limit_txt, bnft_search_txt, bnft_embedding)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_bnft
UNION ALL SELECT 'card_common' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_common_id, common_cd, common_nm, brand_cd, service_grade_cd, common_note, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_common_id, common_cd, common_nm, brand_cd, service_grade_cd, common_note, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_common
UNION ALL SELECT 'card_common_bnft' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_common_id, card_common_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, service_type_cd, bnft_rule_txt, bnft_limit_txt, bnft_valid_from, bnft_valid_to_excl, create_date, create_user_id, update_date, update_user_id, bnft_search_txt, bnft_embedding)::text), ',' ORDER BY md5(row(card_common_id, card_common_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, service_type_cd, bnft_rule_txt, bnft_limit_txt, bnft_valid_from, bnft_valid_to_excl, create_date, create_user_id, update_date, update_user_id, bnft_search_txt, bnft_embedding)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_common_bnft
UNION ALL SELECT 'card_common_bnft_apply' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_common_id, card_common_bnft_id, card_id)::text), ',' ORDER BY md5(row(card_common_id, card_common_bnft_id, card_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_common_bnft_apply
UNION ALL SELECT 'card_common_doc' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_common_id, card_doc_id)::text), ',' ORDER BY md5(row(card_common_id, card_doc_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_common_doc
UNION ALL SELECT 'card_doc' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_doc_id, doc_cd, doc_family_cd, doc_type_cd, doc_title, doc_source_url, doc_file_nm, doc_file_size, doc_sha256, doc_page_cnt, doc_review_no, doc_review_date, doc_release_date, doc_collect_date, doc_version_no, doc_status, doc_note, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_doc_id, doc_cd, doc_family_cd, doc_type_cd, doc_title, doc_source_url, doc_file_nm, doc_file_size, doc_sha256, doc_page_cnt, doc_review_no, doc_review_date, doc_release_date, doc_collect_date, doc_version_no, doc_status, doc_note, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_doc
UNION ALL SELECT 'card_doc_chunk' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_doc_id, page_no, card_doc_chunk_id, chunk_seq, chunk_section_nm, chunk_type_cd, chunk_start_pos, chunk_end_pos, chunk_raw_txt, chunk_clean_txt, chunk_status, chunk_split_rule_ver, chunk_clean_rule_ver, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_doc_id, page_no, card_doc_chunk_id, chunk_seq, chunk_section_nm, chunk_type_cd, chunk_start_pos, chunk_end_pos, chunk_raw_txt, chunk_clean_txt, chunk_status, chunk_split_rule_ver, chunk_clean_rule_ver, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_doc_chunk
UNION ALL SELECT 'card_doc_page' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_doc_id, page_no, page_raw_txt, page_char_cnt, page_txt_sha256, page_layer_cd, page_extractor_nm, page_extractor_ver, page_note, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_doc_id, page_no, page_raw_txt, page_char_cnt, page_txt_sha256, page_layer_cd, page_extractor_nm, page_extractor_ver, page_note, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_doc_page
UNION ALL SELECT 'card_evidence_link' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id, card_bnft_id, ev_subject_cd, rule_key, relation_key, ev_item_cd, ev_item_key)::text), ',' ORDER BY md5(row(card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id, card_bnft_id, ev_subject_cd, rule_key, relation_key, ev_item_cd, ev_item_key)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_evidence_link
UNION ALL SELECT 'card_extr_stg' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id, stg_item_seq, card_id, stg_kind_cd, stg_parent_card_extr_stg_id, stg_raw_item, stg_evidence_txt, stg_evidence_start_pos, stg_evidence_end_pos, stg_sql_check_cd, stg_ai_vrfy_cd, stg_ai_vrfy_card_ai_run_id, stg_status, stg_review_note, stg_approved_date, stg_approved_user_id, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id, stg_item_seq, card_id, stg_kind_cd, stg_parent_card_extr_stg_id, stg_raw_item, stg_evidence_txt, stg_evidence_start_pos, stg_evidence_end_pos, stg_sql_check_cd, stg_ai_vrfy_cd, stg_ai_vrfy_card_ai_run_id, stg_status, stg_review_note, stg_approved_date, stg_approved_user_id, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_extr_stg
UNION ALL SELECT 'card_product' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_id, product_cd, product_nm, issuer, card_kind_cd, product_status_cd, launched_on, discontinued_on, brand_opt_list, create_date, create_user_id, update_date, update_user_id, card_cond_status_cd)::text), ',' ORDER BY md5(row(card_id, product_cd, product_nm, issuer, card_kind_cd, product_status_cd, launched_on, discontinued_on, brand_opt_list, create_date, create_user_id, update_date, update_user_id, card_cond_status_cd)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_product
UNION ALL SELECT 'card_product_doc' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_id, card_doc_id, doc_role_cd, brand_opt_cds, approval_status_cd, applicability_basis_txt, approval_note, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_id, card_doc_id, doc_role_cd, brand_opt_cds, approval_status_cd, applicability_basis_txt, approval_note, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_product_doc
UNION ALL SELECT 'card_source_evidence' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_extr_stg_id, quote_txt, start_pos, end_pos, approval_status_cd)::text), ',' ORDER BY md5(row(card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_extr_stg_id, quote_txt, start_pos, end_pos, approval_status_cd)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_source_evidence;

-- 1. 뷰 제거(의존 순서, CASCADE 없음)
DROP VIEW db_pipeline.v_card_integrity_issue;
DROP VIEW db_pipeline.v_common_cd_usage;
DROP VIEW db_pipeline.v_card_bnft_rule_effective;
DROP VIEW db_pipeline.v_card_rule_target;
DROP VIEW db_pipeline.v_card_cond_atom;
DROP VIEW db_pipeline.v_card_rule;
DROP FUNCTION db_pipeline.fn_cond_spend_bound(jsonb, text);

-- 2. 검증 함수 교체(계산 필수 조건 제거). 데이터 정리 전에 바꿔야 CHECK가 통과한다.
CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_cond_expr(p_expr jsonb)
 RETURNS boolean
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
    v_branch jsonb;
    v_atom jsonb;
    v_branch_nos integer[] := '{}';
    v_atom_keys text[] := '{}';
    v_atom_seqs integer[];
    v_branch_no integer;
    v_atom_seq integer;
    v_key text;
    v_type text;
BEGIN
    IF p_expr IS NULL THEN
        RETURN true;
    END IF;
    IF jsonb_typeof(p_expr) <> 'object'
       OR coalesce(p_expr->>'expr_status_cd', '') = ''
       OR jsonb_typeof(p_expr->'branches') IS DISTINCT FROM 'array'
       OR jsonb_array_length(p_expr->'branches') = 0 THEN
        RETURN false;
    END IF;

    FOR v_branch IN SELECT value FROM jsonb_array_elements(p_expr->'branches') LOOP
        IF jsonb_typeof(v_branch) <> 'object'
           OR jsonb_typeof(v_branch->'branch_no') IS DISTINCT FROM 'number'
           OR jsonb_typeof(v_branch->'atoms') IS DISTINCT FROM 'array'
           OR jsonb_array_length(v_branch->'atoms') = 0 THEN
            RETURN false;
        END IF;
        v_branch_no := (v_branch->>'branch_no')::integer;
        IF v_branch_no < 1 OR v_branch_no = ANY (v_branch_nos) THEN
            RETURN false;
        END IF;
        v_branch_nos := v_branch_nos || v_branch_no;
        v_atom_seqs := '{}';

        FOR v_atom IN SELECT value FROM jsonb_array_elements(v_branch->'atoms') LOOP
            IF jsonb_typeof(v_atom) <> 'object'
               OR jsonb_typeof(v_atom->'atom_seq') IS DISTINCT FROM 'number'
               OR jsonb_typeof(v_atom->'negate_yn') IS DISTINCT FROM 'boolean' THEN
                RETURN false;
            END IF;
            v_atom_seq := (v_atom->>'atom_seq')::integer;
            v_key := v_atom->>'atom_key';
            v_type := v_atom->>'cond_type_cd';
            IF v_atom_seq < 1 OR v_atom_seq = ANY (v_atom_seqs)
               OR coalesce(v_key, '') !~ '^[A-Za-z0-9_.:-]{1,40}$'
               OR coalesce(v_type, '') = ''
               OR coalesce(v_atom->>'cond_status_cd', '') = '' THEN
                RETURN false;
            END IF;
            v_atom_seqs := v_atom_seqs || v_atom_seq;

            -- 같은 atom_key를 여러 branch에서 다시 쓰는 것은 금지. 근거 연결 키가 모호해지기 때문
            IF v_key = ANY (v_atom_keys) THEN
                RETURN false;
            END IF;
            v_atom_keys := v_atom_keys || v_key;

            IF jsonb_typeof(v_atom->'cond_min_amt') NOT IN ('number','null')
               OR jsonb_typeof(v_atom->'cond_max_amt_excl') NOT IN ('number','null') THEN
                RETURN false;
            END IF;
            IF (v_atom->>'cond_min_amt')::numeric < 0
               OR (v_atom->>'cond_max_amt_excl')::numeric <= (v_atom->>'cond_min_amt')::numeric THEN
                RETURN false;
            END IF;
            IF v_type = 'SPEND_REQ' AND coalesce(v_atom->>'cond_basis_cd', '') = '' THEN
                RETURN false;
            END IF;
            IF v_type IN ('SPEND_EXCL','BNFT_EXCL')
               AND coalesce(v_atom->>'excl_raw_txt', '') = '' THEN
                RETURN false;
            END IF;
        END LOOP;
    END LOOP;
    RETURN true;
END;
$function$;
CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_rule_list(p_list jsonb, p_owner text)
 RETURNS boolean
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
    v_rule jsonb;
    v_keys text[] := '{}';
BEGIN
    IF jsonb_typeof(p_list) IS DISTINCT FROM 'array' THEN
        RETURN false;
    END IF;
    FOR v_rule IN SELECT value FROM jsonb_array_elements(p_list) LOOP
        IF jsonb_typeof(v_rule) <> 'object'
           OR coalesce(v_rule->>'rule_key', '') !~ '^[A-Za-z0-9_.:-]{1,40}$'
           OR v_rule->>'rule_key' = ANY (v_keys)
           OR coalesce(v_rule->>'rule_status_cd', '') = '' THEN
            RETURN false;
        END IF;
        v_keys := v_keys || (v_rule->>'rule_key');

        IF coalesce(jsonb_typeof(v_rule->'value_num'), 'null') NOT IN ('number','null') THEN
            RETURN false;
        END IF;
        IF coalesce((v_rule->>'value_num')::numeric, 0) < 0 THEN
            RETURN false;
        END IF;

        IF NOT db_pipeline.fn_valid_cond_expr(nullif(v_rule->'cond_expr', 'null'::jsonb)) THEN
            RETURN false;
        END IF;

        IF NOT db_pipeline.fn_valid_target_list(coalesce(v_rule->'target_list', '[]'::jsonb)) THEN
            RETURN false;
        END IF;
        IF v_rule->>'rule_status_cd' = 'CONFIRMED'
           AND coalesce(jsonb_array_length(v_rule->'target_list'), 0) = 0 THEN
            RETURN false;
        END IF;

        IF p_owner IS DISTINCT FROM 'LOCAL' OR v_rule ? 'pool_refs' THEN
            RETURN false;
        END IF;
    END LOOP;
    RETURN true;
END;
$function$;
COMMENT ON FUNCTION db_pipeline.fn_valid_rule_list(jsonb, text) IS '혜택 규칙 목록 JSONB 계약 검증. 계산 방법·지급 단위·기준 금액·방법 버전·판정 상태·우선순위·계산 파라미터는 저장하지 않는다(2026-11-03 정리). pool_refs 불허, p_owner는 LOCAL만 허용';
COMMENT ON FUNCTION db_pipeline.fn_valid_cond_expr(jsonb) IS '조건식 JSONB 계약 검증. branch 사이 OR, branch 안 atom AND, negate_yn=NOT. 제외 조건은 excl_raw_txt 원문이 필요하다';

-- 3. 저장된 JSON에서 계산 전용 키 제거(값은 모두 비었거나 고정값). 추출 이력 card_extr_stg는 바꾸지 않는다.
CREATE FUNCTION pg_temp.db_pipeline_tmp_strip_atoms(p_expr jsonb) RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE WHEN p_expr IS NULL OR jsonb_typeof(p_expr) <> 'object' THEN p_expr ELSE
        jsonb_set(p_expr, '{branches}', (SELECT coalesce(jsonb_agg(jsonb_set(b.value, '{atoms}',
            (SELECT coalesce(jsonb_agg(a.value - ARRAY['predicate_method_cd', 'predicate_method_ver', 'cond_params', 'card_excl_item_id', 'link_role_cd']::text[] ORDER BY a.ord), '[]'::jsonb)
             FROM jsonb_array_elements(b.value->'atoms') WITH ORDINALITY AS a(value, ord))) ORDER BY b.ord), '[]'::jsonb)
            FROM jsonb_array_elements(p_expr->'branches') WITH ORDINALITY AS b(value, ord))) END
$$;
UPDATE db_pipeline.card_bnft SET
    rule_list = (SELECT coalesce(jsonb_agg((r.value - ARRAY['predicate_state_cd', 'method_ver', 'calc_params', 'rule_priority', 'calc_method_cd', 'payout_unit_cd', 'basis_amt']::text[])
              || CASE WHEN jsonb_typeof(r.value->'cond_expr') = 'object'
                      THEN jsonb_build_object('cond_expr', pg_temp.db_pipeline_tmp_strip_atoms(r.value->'cond_expr')) ELSE '{}'::jsonb END
              ORDER BY r.ord), '[]'::jsonb)
           FROM jsonb_array_elements(rule_list) WITH ORDINALITY AS r(value, ord)),
    bnft_cond_expr = pg_temp.db_pipeline_tmp_strip_atoms(bnft_cond_expr);
UPDATE db_pipeline.card_product SET card_cond_expr = pg_temp.db_pipeline_tmp_strip_atoms(card_cond_expr) WHERE card_cond_expr IS NOT NULL;

-- 4. 컬럼·테이블 제거
ALTER TABLE db_pipeline.card_bnft DROP COLUMN rule_select_cd;
DROP INDEX db_pipeline.ix_card_extr_stg_excl_item_key;
ALTER TABLE db_pipeline.card_extr_stg DROP COLUMN card_excl_item_id;
DROP INDEX db_pipeline.ix_card_excl_item_alias_gin;
DROP INDEX db_pipeline.ix_card_excl_item_concept_key;
DROP TABLE db_pipeline.card_excl_item;
DROP SEQUENCE db_pipeline.seq_card_excl_item;   -- 한 번도 발급하지 않음(last_value NULL)

-- 4-2. 정제본 컬럼 제거. 승인 조건에서 정제본 존재만 빼고 검증 코드 OK·근거 위치·근거 문장 조건은 유지한다.
ALTER TABLE db_pipeline.card_extr_stg DROP CONSTRAINT card_extr_stg_check1;
ALTER TABLE db_pipeline.card_extr_stg ADD CONSTRAINT card_extr_stg_check1 CHECK ((((stg_status)::text <> ALL (ARRAY[('AUTO_APPROVED'::character varying)::text, ('MANUAL_APPROVED'::character varying)::text])) OR ((NOT ((stg_sql_check_cd)::text IS DISTINCT FROM 'OK'::text)) AND (stg_evidence_start_pos IS NOT NULL) AND (stg_evidence_end_pos IS NOT NULL) AND (btrim(stg_evidence_txt) <> ''::text))));
ALTER TABLE db_pipeline.card_extr_stg DROP COLUMN stg_normalized_item;

-- 5. 뷰 재생성
CREATE VIEW db_pipeline.v_card_rule AS
 SELECT b.card_id,
    b.card_bnft_id,
    r.value ->> 'rule_key'::text AS rule_key,
    r.ord AS rule_seq,
    NULLIF(r.value -> 'cond_expr'::text, 'null'::jsonb) AS cond_expr,
    COALESCE(r.value -> 'target_list'::text, '[]'::jsonb) AS target_list,
    ((r.value ->> 'value_num'::text))::numeric(18,4) AS value_num,
    r.value ->> 'value_unit_cd'::text AS value_unit_cd,
    r.value ->> 'rule_status_cd'::text AS rule_status_cd
   FROM db_pipeline.card_bnft b
     CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) WITH ORDINALITY r(value, ord);
CREATE VIEW db_pipeline.v_card_cond_atom AS
 WITH src AS (
         SELECT 'CARD'::text AS owner_cd,
            p.card_id,
            NULL::character varying AS card_bnft_id,
            NULL::text AS rule_key,
            p.card_cond_expr AS expr
           FROM db_pipeline.card_product p
          WHERE p.card_cond_expr IS NOT NULL
        UNION ALL
         SELECT 'BNFT',
            b_1.card_id,
            b_1.card_bnft_id,
            NULL,
            b_1.bnft_cond_expr
           FROM db_pipeline.card_bnft b_1
          WHERE b_1.bnft_cond_expr IS NOT NULL
        UNION ALL
         SELECT 'RULE',
            r.card_id,
            r.card_bnft_id,
            r.rule_key,
            r.cond_expr
           FROM db_pipeline.v_card_rule r
          WHERE r.cond_expr IS NOT NULL
        )
 SELECT s.owner_cd,
    s.card_id,
    s.card_bnft_id,
    s.rule_key,
    s.expr ->> 'expr_status_cd'::text AS expr_status_cd,
    (b.value ->> 'branch_no'::text)::integer AS branch_no,
    (a.value ->> 'atom_seq'::text)::integer AS atom_seq,
    a.value ->> 'atom_key'::text AS atom_key,
    (a.value ->> 'negate_yn'::text)::boolean AS negate_yn,
    a.value ->> 'cond_type_cd'::text AS cond_type_cd,
    a.value ->> 'cond_basis_cd'::text AS cond_basis_cd,
    ((a.value ->> 'cond_min_amt'::text))::numeric(18,2) AS cond_min_amt,
    ((a.value ->> 'cond_max_amt_excl'::text))::numeric(18,2) AS cond_max_amt_excl,
    a.value ->> 'excl_raw_txt'::text AS excl_raw_txt,
    a.value ->> 'cond_raw_txt'::text AS cond_raw_txt,
    a.value ->> 'cond_status_cd'::text AS cond_status_cd
   FROM src s
     CROSS JOIN LATERAL jsonb_array_elements(s.expr -> 'branches'::text) b(value)
     CROSS JOIN LATERAL jsonb_array_elements(b.value -> 'atoms'::text) a(value);
CREATE VIEW db_pipeline.v_card_rule_target AS
 SELECT r.card_id,
    r.card_bnft_id,
    r.rule_key,
    t.value ->> 'target_type_cd'::text AS target_type_cd,
    t.value ->> 'target_key'::text AS target_key,
    t.value ->> 'target_nm'::text AS target_nm
   FROM db_pipeline.v_card_rule r
     CROSS JOIN LATERAL jsonb_array_elements(r.target_list) t(value);
CREATE VIEW db_pipeline.v_common_cd_usage AS
 SELECT 'card_product.card_kind_cd'::text AS source_nm,
    'CARD_KIND'::character varying(20) AS common_code_grp_id,
    card_product.card_kind_cd::text AS cd_value
   FROM db_pipeline.card_product
  WHERE card_product.card_kind_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.product_status_cd'::text AS source_nm,
    'PRODUCT_STATUS'::character varying(20) AS common_code_grp_id,
    card_product.product_status_cd::text AS cd_value
   FROM db_pipeline.card_product
  WHERE card_product.product_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.card_cond_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying(20) AS common_code_grp_id,
    card_product.card_cond_status_cd::text AS cd_value
   FROM db_pipeline.card_product
  WHERE card_product.card_cond_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_product_doc.doc_role_cd'::text AS source_nm,
    'DOC_ROLE'::character varying(20) AS common_code_grp_id,
    card_product_doc.doc_role_cd::text AS cd_value
   FROM db_pipeline.card_product_doc
  WHERE card_product_doc.doc_role_cd IS NOT NULL
UNION ALL
 SELECT 'card_product_doc.approval_status_cd'::text AS source_nm,
    'APPROVAL_STATUS'::character varying(20) AS common_code_grp_id,
    card_product_doc.approval_status_cd::text AS cd_value
   FROM db_pipeline.card_product_doc
  WHERE card_product_doc.approval_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.bnft_type_cd'::text AS source_nm,
    'BNFT_TYPE'::character varying(20) AS common_code_grp_id,
    card_bnft.bnft_type_cd::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE card_bnft.bnft_type_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.bnft_origin_cd'::text AS source_nm,
    'BNFT_ORIGIN'::character varying(20) AS common_code_grp_id,
    card_bnft.bnft_origin_cd::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE card_bnft.bnft_origin_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.bnft_scope_cd'::text AS source_nm,
    'BNFT_SCOPE'::character varying(20) AS common_code_grp_id,
    card_bnft.bnft_scope_cd::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE card_bnft.bnft_scope_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.verification_status_cd'::text AS source_nm,
    'VERIFY_STATUS'::character varying(20) AS common_code_grp_id,
    card_bnft.verification_status_cd::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE card_bnft.verification_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_source_evidence.approval_status_cd'::text AS source_nm,
    'APPROVAL_STATUS'::character varying(20) AS common_code_grp_id,
    card_source_evidence.approval_status_cd::text AS cd_value
   FROM db_pipeline.card_source_evidence
  WHERE card_source_evidence.approval_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_evidence_link.ev_subject_cd'::text AS source_nm,
    'EV_SUBJECT'::character varying(20) AS common_code_grp_id,
    card_evidence_link.ev_subject_cd::text AS cd_value
   FROM db_pipeline.card_evidence_link
  WHERE card_evidence_link.ev_subject_cd IS NOT NULL
UNION ALL
 SELECT 'card_evidence_link.ev_item_cd'::text AS source_nm,
    'EV_ITEM'::character varying(20) AS common_code_grp_id,
    card_evidence_link.ev_item_cd::text AS cd_value
   FROM db_pipeline.card_evidence_link
  WHERE card_evidence_link.ev_item_cd IS NOT NULL
UNION ALL
 SELECT 'card_doc.doc_type_cd'::text AS source_nm,
    'DOC_TYPE'::character varying(20) AS common_code_grp_id,
    card_doc.doc_type_cd::text AS cd_value
   FROM db_pipeline.card_doc
  WHERE card_doc.doc_type_cd IS NOT NULL
UNION ALL
 SELECT 'card_doc.doc_status'::text AS source_nm,
    'DOC_STATUS'::character varying(20) AS common_code_grp_id,
    card_doc.doc_status::text AS cd_value
   FROM db_pipeline.card_doc
  WHERE card_doc.doc_status IS NOT NULL
UNION ALL
 SELECT 'card_doc_page.page_layer_cd'::text AS source_nm,
    'PAGE_LAYER'::character varying(20) AS common_code_grp_id,
    card_doc_page.page_layer_cd::text AS cd_value
   FROM db_pipeline.card_doc_page
  WHERE card_doc_page.page_layer_cd IS NOT NULL
UNION ALL
 SELECT 'card_doc_chunk.chunk_type_cd'::text AS source_nm,
    'CHUNK_TYPE'::character varying(20) AS common_code_grp_id,
    card_doc_chunk.chunk_type_cd::text AS cd_value
   FROM db_pipeline.card_doc_chunk
  WHERE card_doc_chunk.chunk_type_cd IS NOT NULL
UNION ALL
 SELECT 'card_doc_chunk.chunk_status'::text AS source_nm,
    'CHUNK_STATUS'::character varying(20) AS common_code_grp_id,
    card_doc_chunk.chunk_status::text AS cd_value
   FROM db_pipeline.card_doc_chunk
  WHERE card_doc_chunk.chunk_status IS NOT NULL
UNION ALL
 SELECT 'card_ai_run.run_stage_cd'::text AS source_nm,
    'RUN_STAGE'::character varying(20) AS common_code_grp_id,
    card_ai_run.run_stage_cd::text AS cd_value
   FROM db_pipeline.card_ai_run
  WHERE card_ai_run.run_stage_cd IS NOT NULL
UNION ALL
 SELECT 'card_ai_run.run_call_mthd_cd'::text AS source_nm,
    'RUN_CALL_METHOD'::character varying(20) AS common_code_grp_id,
    card_ai_run.run_call_mthd_cd::text AS cd_value
   FROM db_pipeline.card_ai_run
  WHERE card_ai_run.run_call_mthd_cd IS NOT NULL
UNION ALL
 SELECT 'card_ai_run.run_status'::text AS source_nm,
    'RUN_STATUS'::character varying(20) AS common_code_grp_id,
    card_ai_run.run_status::text AS cd_value
   FROM db_pipeline.card_ai_run
  WHERE card_ai_run.run_status IS NOT NULL
UNION ALL
 SELECT 'card_ai_call.call_status'::text AS source_nm,
    'CALL_STATUS'::character varying(20) AS common_code_grp_id,
    card_ai_call.call_status::text AS cd_value
   FROM db_pipeline.card_ai_call
  WHERE card_ai_call.call_status IS NOT NULL
UNION ALL
 SELECT 'card_extr_stg.stg_kind_cd'::text AS source_nm,
    'STG_KIND'::character varying(20) AS common_code_grp_id,
    card_extr_stg.stg_kind_cd::text AS cd_value
   FROM db_pipeline.card_extr_stg
  WHERE card_extr_stg.stg_kind_cd IS NOT NULL
UNION ALL
 SELECT 'card_extr_stg.stg_status'::text AS source_nm,
    'STG_STATUS'::character varying(20) AS common_code_grp_id,
    card_extr_stg.stg_status::text AS cd_value
   FROM db_pipeline.card_extr_stg
  WHERE card_extr_stg.stg_status IS NOT NULL
UNION ALL
 SELECT 'card_extr_stg.stg_ai_vrfy_cd'::text AS source_nm,
    'STG_AI_VRFY'::character varying(20) AS common_code_grp_id,
    card_extr_stg.stg_ai_vrfy_cd::text AS cd_value
   FROM db_pipeline.card_extr_stg
  WHERE card_extr_stg.stg_ai_vrfy_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.brand_opt_list[].brand_cd'::text AS source_nm,
    'BRAND'::character varying AS common_code_grp_id,
    v_card_brand_opt.brand_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE v_card_brand_opt.brand_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.brand_opt_list[].service_grade_cd'::text AS source_nm,
    'SERVICE_GRADE'::character varying AS common_code_grp_id,
    v_card_brand_opt.service_grade_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE v_card_brand_opt.service_grade_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.brand_opt_list[].service_type_cd'::text AS source_nm,
    'SERVICE_TYPE'::character varying AS common_code_grp_id,
    v_card_brand_opt.service_type_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE v_card_brand_opt.service_type_cd IS NOT NULL
UNION ALL
 SELECT 'card_product.brand_opt_list[].brand_opt_status_cd'::text AS source_nm,
    'PRODUCT_STATUS'::character varying AS common_code_grp_id,
    v_card_brand_opt.brand_opt_status_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE v_card_brand_opt.brand_opt_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.rule_list[].value_unit_cd'::text AS source_nm,
    'VALUE_UNIT'::character varying AS common_code_grp_id,
    v_card_rule.value_unit_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE v_card_rule.value_unit_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.rule_list[].rule_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying AS common_code_grp_id,
    v_card_rule.rule_status_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE v_card_rule.rule_status_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.relation_list[].rel_type_cd'::text AS source_nm,
    'REL_TYPE'::character varying AS common_code_grp_id,
    v_card_bnft_rel.rel_type_cd AS cd_value
   FROM db_pipeline.v_card_bnft_rel
  WHERE v_card_bnft_rel.rel_type_cd IS NOT NULL AND NOT v_card_bnft_rel.reverse_yn
UNION ALL
 SELECT 'rule_list[].target_list[].target_type_cd'::text AS source_nm,
    'TARGET_TYPE'::character varying AS common_code_grp_id,
    v_card_rule_target.target_type_cd AS cd_value
   FROM db_pipeline.v_card_rule_target
  WHERE v_card_rule_target.target_type_cd IS NOT NULL
UNION ALL
 SELECT 'cond_expr atom cond_type_cd'::text AS source_nm,
    'COND_TYPE'::character varying AS common_code_grp_id,
    v_card_cond_atom.cond_type_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE v_card_cond_atom.cond_type_cd IS NOT NULL
UNION ALL
 SELECT 'cond_expr atom cond_basis_cd'::text AS source_nm,
    'COND_BASIS'::character varying AS common_code_grp_id,
    v_card_cond_atom.cond_basis_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE v_card_cond_atom.cond_basis_cd IS NOT NULL
UNION ALL
 SELECT 'cond_expr atom cond_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying AS common_code_grp_id,
    v_card_cond_atom.cond_status_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE v_card_cond_atom.cond_status_cd IS NOT NULL
UNION ALL
 SELECT 'cond_expr.expr_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying AS common_code_grp_id,
    v_card_cond_atom.expr_status_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE v_card_cond_atom.expr_status_cd IS NOT NULL;
CREATE VIEW db_pipeline.v_card_integrity_issue AS
 WITH atoms AS (
         SELECT v_card_cond_atom.owner_cd,
            v_card_cond_atom.card_id,
            v_card_cond_atom.card_bnft_id,
            v_card_cond_atom.rule_key,
            v_card_cond_atom.expr_status_cd,
            v_card_cond_atom.branch_no,
            v_card_cond_atom.atom_seq,
            v_card_cond_atom.atom_key,
            v_card_cond_atom.negate_yn,
            v_card_cond_atom.cond_type_cd,
            v_card_cond_atom.cond_basis_cd,
            v_card_cond_atom.cond_min_amt,
            v_card_cond_atom.cond_max_amt_excl,
            v_card_cond_atom.excl_raw_txt,
            v_card_cond_atom.cond_raw_txt,
            v_card_cond_atom.cond_status_cd
           FROM db_pipeline.v_card_cond_atom
        ), fallback AS (
         SELECT v_card_bnft_rel.card_id,
            v_card_bnft_rel.from_bnft_id,
            v_card_bnft_rel.to_bnft_id
           FROM db_pipeline.v_card_bnft_rel
          WHERE v_card_bnft_rel.rel_type_cd = 'FALLBACK_AFTER_CAP'::text AND NOT v_card_bnft_rel.reverse_yn
        ), cycle AS (
         WITH RECURSIVE walk(card_id, start_id, cur_id, path) AS (
                 SELECT fallback.card_id,
                    fallback.from_bnft_id,
                    fallback.to_bnft_id,
                    ARRAY[fallback.from_bnft_id, fallback.to_bnft_id::character varying] AS "array"
                   FROM fallback
                UNION ALL
                 SELECT w.card_id,
                    w.start_id,
                    f.to_bnft_id,
                    w.path || f.to_bnft_id::character varying
                   FROM walk w
                     JOIN fallback f ON f.card_id = w.card_id AND f.from_bnft_id::text = w.cur_id
                  WHERE NOT (f.to_bnft_id = ANY (w.path[2:]::text[]))
                )
         SELECT DISTINCT walk.card_id,
            walk.start_id
           FROM walk
          WHERE walk.cur_id = walk.start_id::text
        )
 SELECT 'bnft_without_product'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_bnft_id::text AS issue_key
   FROM db_pipeline.card_bnft x
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product p
          WHERE p.card_id = x.card_id))
UNION ALL
 SELECT 'local_confirmed_without_rule'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_bnft_id::text AS issue_key
   FROM db_pipeline.card_bnft x
  WHERE x.verification_status_cd::text = 'CONFIRMED'::text AND jsonb_array_length(x.rule_list) = 0
UNION ALL
 SELECT 'bnft_txt_without_evidence'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_bnft_id::text AS issue_key
   FROM db_pipeline.card_bnft x
  WHERE (x.bnft_rule_txt IS NOT NULL OR x.bnft_limit_txt IS NOT NULL) AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_evidence_link l
          WHERE l.card_id = x.card_id AND l.card_bnft_id::text = x.card_bnft_id::text AND l.ev_subject_cd::text = 'BNFT'::text AND l.ev_item_cd::text = 'SELF'::text))
UNION ALL
 SELECT 'rel_to_bnft_orphan'::text AS gate_cd,
    (x.card_id || '/'::text) || x.relation_key AS issue_key
   FROM db_pipeline.v_card_bnft_rel x
  WHERE NOT x.reverse_yn AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_bnft b
          WHERE b.card_id = x.card_id AND b.card_bnft_id::text = x.to_bnft_id))
UNION ALL
 SELECT 'rel_mutual_stored_twice'::text AS gate_cd,
    (((a.card_id || '/'::text) || a.from_bnft_id::text) || '/'::text) || a.to_bnft_id AS issue_key
   FROM db_pipeline.v_card_bnft_rel a
     JOIN db_pipeline.v_card_bnft_rel b ON a.card_id = b.card_id AND a.from_bnft_id::text = b.to_bnft_id AND a.to_bnft_id = b.from_bnft_id::text AND a.rel_type_cd = b.rel_type_cd
  WHERE NOT a.reverse_yn AND NOT b.reverse_yn AND a.rel_type_cd = 'MUTUALLY_EXCLUSIVE'::text AND a.from_bnft_id::text < a.to_bnft_id
UNION ALL
 SELECT 'rel_fallback_cycle'::text AS gate_cd,
    (c.card_id || '/'::text) || c.start_id::text AS issue_key
   FROM cycle c
UNION ALL
 SELECT 'product_doc_without_product'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_doc_id::text AS issue_key
   FROM db_pipeline.card_product_doc x
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product p
          WHERE p.card_id = x.card_id))
UNION ALL
 SELECT 'product_doc_orphan'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_doc_id::text AS issue_key
   FROM db_pipeline.card_product_doc x
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_doc d
          WHERE d.card_doc_id::text = x.card_doc_id::text))
UNION ALL
 SELECT 'bnft_brand_opt_unknown'::text AS gate_cd,
    (((b.card_id || '/'::text) || b.card_bnft_id::text) || '/'::text) || o.cd AS issue_key
   FROM db_pipeline.card_bnft b
     CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) o(cd)
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.v_card_brand_opt v
          WHERE v.card_id = b.card_id AND v.brand_opt_cd = o.cd))
UNION ALL
 SELECT 'doc_brand_opt_unknown'::text AS gate_cd,
    (((d.card_id || '/'::text) || d.card_doc_id::text) || '/'::text) || o.cd AS issue_key
   FROM db_pipeline.card_product_doc d
     CROSS JOIN LATERAL unnest(d.brand_opt_cds) o(cd)
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.v_card_brand_opt v
          WHERE v.card_id = d.card_id AND v.brand_opt_cd = o.cd))
UNION ALL
 SELECT 'evidence_source_orphan'::text AS gate_cd,
    e.evidence_id AS issue_key
   FROM db_pipeline.card_source_evidence e
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_doc_chunk c
          WHERE c.card_doc_id::text = e.card_doc_id::text AND c.page_no = e.page_no AND c.card_doc_chunk_id::text = e.card_doc_chunk_id::text))
UNION ALL
 SELECT 'evidence_doc_not_linked'::text AS gate_cd,
    (l.card_id || '/'::text) || l.evidence_link_id::text AS issue_key
   FROM db_pipeline.card_evidence_link l
     JOIN db_pipeline.card_source_evidence e USING (evidence_id)
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc d
          WHERE d.card_id = l.card_id AND d.card_doc_id::text = e.card_doc_id::text))
UNION ALL
 SELECT 'evidence_not_approved'::text AS gate_cd,
    l.evidence_id AS issue_key
   FROM ( SELECT DISTINCT card_evidence_link.evidence_id
           FROM db_pipeline.card_evidence_link) l
     LEFT JOIN db_pipeline.card_source_evidence e USING (evidence_id)
  WHERE e.evidence_id IS NULL OR e.approval_status_cd::text <> 'APPROVED'::text
UNION ALL
 SELECT 'evidence_subject_orphan'::text AS gate_cd,
    (l.card_id || '/'::text) || l.evidence_link_id::text AS issue_key
   FROM db_pipeline.card_evidence_link l
  WHERE NOT
        CASE l.ev_subject_cd
            WHEN 'CARD'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.card_product p
              WHERE p.card_id = l.card_id))
            WHEN 'BNFT'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.card_bnft b
              WHERE b.card_id = l.card_id AND b.card_bnft_id::text = l.card_bnft_id::text))
            WHEN 'RULE'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_rule r
              WHERE r.card_id = l.card_id AND r.card_bnft_id::text = l.card_bnft_id::text AND r.rule_key = l.rule_key::text))
            WHEN 'REL'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_bnft_rel r
              WHERE NOT r.reverse_yn AND r.card_id = l.card_id AND r.from_bnft_id::text = l.card_bnft_id::text AND r.relation_key = l.relation_key::text))
            ELSE false
        END
UNION ALL
 SELECT 'evidence_item_key_missing'::text AS gate_cd,
    (l.card_id || '/'::text) || l.evidence_link_id::text AS issue_key
   FROM db_pipeline.card_evidence_link l
  WHERE l.ev_item_cd::text <> 'SELF'::text AND NOT
        CASE l.ev_item_cd
            WHEN 'COND'::text THEN (EXISTS ( SELECT 1
               FROM atoms a
              WHERE a.card_id = l.card_id AND a.atom_key = l.ev_item_key::text AND NOT a.card_bnft_id::text IS DISTINCT FROM l.card_bnft_id::text AND NOT a.rule_key IS DISTINCT FROM l.rule_key::text))
            WHEN 'TARGET'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_rule_target t
              WHERE t.card_id = l.card_id AND t.card_bnft_id::text = l.card_bnft_id::text AND t.rule_key = l.rule_key::text AND t.target_key = l.ev_item_key::text))
            ELSE false
        END
UNION ALL
 SELECT 'product_doc_role_type_mismatch'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_doc_id::text AS issue_key
   FROM db_pipeline.card_product_doc x
     JOIN db_pipeline.card_doc d ON d.card_doc_id::text = x.card_doc_id::text
  WHERE x.doc_role_cd::text = 'BRAND_SERVICE'::text AND d.doc_type_cd::text <> 'BRAND_SERVICE'::text
UNION ALL
 SELECT 'brand_doc_option_conflict'::text AS gate_cd,
    z.card_doc_id AS issue_key
   FROM ( SELECT x.card_doc_id
           FROM db_pipeline.card_product_doc x
             CROSS JOIN LATERAL unnest(x.brand_opt_cds) o(cd)
             JOIN db_pipeline.v_card_brand_opt v ON v.card_id = x.card_id AND v.brand_opt_cd = o.cd
          WHERE x.doc_role_cd::text = 'BRAND_SERVICE'::text
          GROUP BY x.card_doc_id
         HAVING count(DISTINCT ROW(v.brand_cd, v.service_grade_cd, v.service_type_cd)) > 1) z
UNION ALL
 SELECT 'brand_bnft_doc_not_linked'::text AS gate_cd,
    (((b.card_id || '/'::text) || b.card_bnft_id::text) || '/'::text) || o.cd AS issue_key
   FROM db_pipeline.card_bnft b
     CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) o(cd)
  WHERE b.bnft_origin_cd::text = 'BRAND_SERVICE'::text AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc x
          WHERE x.card_id = b.card_id AND x.doc_role_cd::text = 'BRAND_SERVICE'::text AND (o.cd = ANY (x.brand_opt_cds))))
UNION ALL
 SELECT 'brand_bnft_confirmed_without_evidence'::text AS gate_cd,
    (b.card_id || '/'::text) || b.card_bnft_id::text AS issue_key
   FROM db_pipeline.card_bnft b
  WHERE b.bnft_origin_cd::text = 'BRAND_SERVICE'::text AND b.verification_status_cd::text = 'CONFIRMED'::text AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_evidence_link l
          WHERE l.card_id = b.card_id AND l.card_bnft_id::text = b.card_bnft_id::text))
UNION ALL
 SELECT 'evidence_brand_opt_mismatch'::text AS gate_cd,
    (l.card_id || '/'::text) || l.evidence_link_id::text AS issue_key
   FROM db_pipeline.card_evidence_link l
     JOIN db_pipeline.card_source_evidence e USING (evidence_id)
     JOIN db_pipeline.card_bnft b ON b.card_id = l.card_id AND b.card_bnft_id::text = l.card_bnft_id::text
     JOIN db_pipeline.card_product_doc x ON x.card_id = l.card_id AND x.card_doc_id::text = e.card_doc_id::text
  WHERE x.doc_role_cd::text = 'BRAND_SERVICE'::text AND NOT COALESCE(b.bnft_brand_opt_cds, '{}'::text[]) && x.brand_opt_cds
UNION ALL
 SELECT 'stg_card_not_linked'::text AS gate_cd,
    s.card_extr_stg_id AS issue_key
   FROM db_pipeline.card_extr_stg s
  WHERE s.card_id IS NOT NULL AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc x
          WHERE x.card_id = s.card_id AND x.card_doc_id::text = s.card_doc_id::text))
UNION ALL
 SELECT 'common_cd_invalid'::text AS gate_cd,
    (u.source_nm || '='::text) || u.cd_value AS issue_key
   FROM db_pipeline.v_common_cd_usage u
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_cd c
          WHERE c.common_code_grp_id::text = u.common_code_grp_id::text AND c.common_cd::text = u.cd_value))
UNION ALL
 SELECT 'common_cd_group_orphan'::text AS gate_cd,
    (c.common_code_grp_id::text || '/'::text) || c.common_cd::text AS issue_key
   FROM db_pipeline.common_cd c
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_code_grp g
          WHERE g.common_code_grp_id::text = c.common_code_grp_id::text))
UNION ALL
 SELECT 'common_code_grp_empty'::text AS gate_cd,
    g.common_code_grp_id AS issue_key
   FROM db_pipeline.common_code_grp g
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_cd c
          WHERE c.common_code_grp_id::text = g.common_code_grp_id::text));
COMMENT ON VIEW db_pipeline.v_card_rule IS '혜택 규칙(값·단위·대상·조건)을 행으로 복원. 계산 실행용 열(계산 방법·지급 단위·기준 금액·방법 버전·우선순위·계산 파라미터·판정 상태·실적 구간)은 2026-11-03 정리에서 제거';
COMMENT ON VIEW db_pipeline.v_card_cond_atom IS '모든 조건식의 atom을 소유자와 함께 행으로 복원. 술어 방법·파라미터·제외 사전·연결 역할 열은 2026-11-03 정리에서 제거';
COMMENT ON VIEW db_pipeline.v_card_rule_target IS '규칙 대상을 행으로 복원';
COMMENT ON VIEW db_pipeline.v_common_cd_usage IS '모든 공통코드 사용처(물리 컬럼·JSONB 키)와 소속 그룹. 공통코드 정합성 검증의 기준';
COMMENT ON VIEW db_pipeline.v_card_integrity_issue IS '승인 전 정합성 게이트. 물리 FK가 없으므로 행이 1건이라도 있으면 승인하지 않음. *_pending은 확정 전 항목의 값 누락(검토 대기)이고 나머지는 무결성 위반';
ALTER VIEW db_pipeline.v_card_rule OWNER TO postgres;
ALTER VIEW db_pipeline.v_card_cond_atom OWNER TO postgres;
ALTER VIEW db_pipeline.v_card_rule_target OWNER TO postgres;
ALTER VIEW db_pipeline.v_common_cd_usage OWNER TO postgres;
ALTER VIEW db_pipeline.v_card_integrity_issue OWNER TO postgres;

-- 6. 계산·한도 풀 전용 공통코드 제거
DELETE FROM db_pipeline.common_cd WHERE common_code_grp_id IN ('PREDICATE_STATE', 'PREDICATE_METHOD', 'RULE_SELECT', 'LIMIT_PERIOD', 'LIMIT_UNIT', 'LIMIT_SCOPE', 'LIMIT_AGG', 'POOL_ROLE', 'CALC_METHOD', 'PAYOUT_UNIT');
DELETE FROM db_pipeline.common_code_grp WHERE common_code_grp_id IN ('PREDICATE_STATE', 'PREDICATE_METHOD', 'RULE_SELECT', 'LIMIT_PERIOD', 'LIMIT_UNIT', 'LIMIT_SCOPE', 'LIMIT_AGG', 'POOL_ROLE', 'CALC_METHOD', 'PAYOUT_UNIT');

-- 7. 사후 검증: 데이터 건수 동일, 남은 계산 키 없음, 모든 행이 새 계약 통과, 공통코드 사용처 정합
DO $post$
DECLARE v_diff int; v_left int;
BEGIN
    SELECT count(*) INTO v_diff FROM (SELECT * FROM cleanup_before EXCEPT (SELECT 'card_ai_call', count(*) FROM db_pipeline.card_ai_call UNION ALL SELECT 'card_ai_run', count(*) FROM db_pipeline.card_ai_run UNION ALL SELECT 'card_bnft', count(*) FROM db_pipeline.card_bnft UNION ALL SELECT 'card_common', count(*) FROM db_pipeline.card_common UNION ALL SELECT 'card_common_bnft', count(*) FROM db_pipeline.card_common_bnft UNION ALL SELECT 'card_common_bnft_apply', count(*) FROM db_pipeline.card_common_bnft_apply UNION ALL SELECT 'card_common_doc', count(*) FROM db_pipeline.card_common_doc UNION ALL SELECT 'card_doc', count(*) FROM db_pipeline.card_doc UNION ALL SELECT 'card_doc_chunk', count(*) FROM db_pipeline.card_doc_chunk UNION ALL SELECT 'card_doc_page', count(*) FROM db_pipeline.card_doc_page UNION ALL SELECT 'card_evidence_link', count(*) FROM db_pipeline.card_evidence_link UNION ALL SELECT 'card_extr_stg', count(*) FROM db_pipeline.card_extr_stg UNION ALL SELECT 'card_product', count(*) FROM db_pipeline.card_product UNION ALL SELECT 'card_product_doc', count(*) FROM db_pipeline.card_product_doc UNION ALL SELECT 'card_source_evidence', count(*) FROM db_pipeline.card_source_evidence)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION '데이터 건수가 달라졌습니다'; END IF;
    SELECT count(*) INTO v_diff FROM (SELECT * FROM cleanup_keep EXCEPT (SELECT 'card_ai_call' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, call_input_sha256, call_status, call_resp_raw, call_resp_json, call_error_msg, call_input_token_cnt, call_output_token_cnt, call_latency_ms, call_req_date, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, call_input_sha256, call_status, call_resp_raw, call_resp_json, call_error_msg, call_input_token_cnt, call_output_token_cnt, call_latency_ms, call_req_date, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_ai_call
UNION ALL SELECT 'card_ai_run' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_ai_run_id, run_stage_cd, run_call_mthd_cd, run_model_nm, run_prompt_ver, run_prompt_txt, run_param, run_target_card_doc_id, run_status, run_start_date, run_end_date, run_note, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_ai_run_id, run_stage_cd, run_call_mthd_cd, run_model_nm, run_prompt_ver, run_prompt_txt, run_param, run_target_card_doc_id, run_status, run_start_date, run_end_date, run_note, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_ai_run
UNION ALL SELECT 'card_bnft' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, bnft_brand_opt_cds, relation_list, verification_status_cd, bnft_valid_from, bnft_valid_to_excl, bnft_rule_txt, bnft_limit_txt, bnft_search_txt, bnft_embedding)::text), ',' ORDER BY md5(row(card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, bnft_brand_opt_cds, relation_list, verification_status_cd, bnft_valid_from, bnft_valid_to_excl, bnft_rule_txt, bnft_limit_txt, bnft_search_txt, bnft_embedding)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_bnft
UNION ALL SELECT 'card_common' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_common_id, common_cd, common_nm, brand_cd, service_grade_cd, common_note, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_common_id, common_cd, common_nm, brand_cd, service_grade_cd, common_note, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_common
UNION ALL SELECT 'card_common_bnft' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_common_id, card_common_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, service_type_cd, bnft_rule_txt, bnft_limit_txt, bnft_valid_from, bnft_valid_to_excl, create_date, create_user_id, update_date, update_user_id, bnft_search_txt, bnft_embedding)::text), ',' ORDER BY md5(row(card_common_id, card_common_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, service_type_cd, bnft_rule_txt, bnft_limit_txt, bnft_valid_from, bnft_valid_to_excl, create_date, create_user_id, update_date, update_user_id, bnft_search_txt, bnft_embedding)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_common_bnft
UNION ALL SELECT 'card_common_bnft_apply' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_common_id, card_common_bnft_id, card_id)::text), ',' ORDER BY md5(row(card_common_id, card_common_bnft_id, card_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_common_bnft_apply
UNION ALL SELECT 'card_common_doc' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_common_id, card_doc_id)::text), ',' ORDER BY md5(row(card_common_id, card_doc_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_common_doc
UNION ALL SELECT 'card_doc' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_doc_id, doc_cd, doc_family_cd, doc_type_cd, doc_title, doc_source_url, doc_file_nm, doc_file_size, doc_sha256, doc_page_cnt, doc_review_no, doc_review_date, doc_release_date, doc_collect_date, doc_version_no, doc_status, doc_note, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_doc_id, doc_cd, doc_family_cd, doc_type_cd, doc_title, doc_source_url, doc_file_nm, doc_file_size, doc_sha256, doc_page_cnt, doc_review_no, doc_review_date, doc_release_date, doc_collect_date, doc_version_no, doc_status, doc_note, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_doc
UNION ALL SELECT 'card_doc_chunk' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_doc_id, page_no, card_doc_chunk_id, chunk_seq, chunk_section_nm, chunk_type_cd, chunk_start_pos, chunk_end_pos, chunk_raw_txt, chunk_clean_txt, chunk_status, chunk_split_rule_ver, chunk_clean_rule_ver, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_doc_id, page_no, card_doc_chunk_id, chunk_seq, chunk_section_nm, chunk_type_cd, chunk_start_pos, chunk_end_pos, chunk_raw_txt, chunk_clean_txt, chunk_status, chunk_split_rule_ver, chunk_clean_rule_ver, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_doc_chunk
UNION ALL SELECT 'card_doc_page' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_doc_id, page_no, page_raw_txt, page_char_cnt, page_txt_sha256, page_layer_cd, page_extractor_nm, page_extractor_ver, page_note, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_doc_id, page_no, page_raw_txt, page_char_cnt, page_txt_sha256, page_layer_cd, page_extractor_nm, page_extractor_ver, page_note, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_doc_page
UNION ALL SELECT 'card_evidence_link' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id, card_bnft_id, ev_subject_cd, rule_key, relation_key, ev_item_cd, ev_item_key)::text), ',' ORDER BY md5(row(card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id, card_bnft_id, ev_subject_cd, rule_key, relation_key, ev_item_cd, ev_item_key)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_evidence_link
UNION ALL SELECT 'card_extr_stg' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id, stg_item_seq, card_id, stg_kind_cd, stg_parent_card_extr_stg_id, stg_raw_item, stg_evidence_txt, stg_evidence_start_pos, stg_evidence_end_pos, stg_sql_check_cd, stg_ai_vrfy_cd, stg_ai_vrfy_card_ai_run_id, stg_status, stg_review_note, stg_approved_date, stg_approved_user_id, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id, stg_item_seq, card_id, stg_kind_cd, stg_parent_card_extr_stg_id, stg_raw_item, stg_evidence_txt, stg_evidence_start_pos, stg_evidence_end_pos, stg_sql_check_cd, stg_ai_vrfy_cd, stg_ai_vrfy_card_ai_run_id, stg_status, stg_review_note, stg_approved_date, stg_approved_user_id, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_extr_stg
UNION ALL SELECT 'card_product' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_id, product_cd, product_nm, issuer, card_kind_cd, product_status_cd, launched_on, discontinued_on, brand_opt_list, create_date, create_user_id, update_date, update_user_id, card_cond_status_cd)::text), ',' ORDER BY md5(row(card_id, product_cd, product_nm, issuer, card_kind_cd, product_status_cd, launched_on, discontinued_on, brand_opt_list, create_date, create_user_id, update_date, update_user_id, card_cond_status_cd)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_product
UNION ALL SELECT 'card_product_doc' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_id, card_doc_id, doc_role_cd, brand_opt_cds, approval_status_cd, applicability_basis_txt, approval_note, create_date, create_user_id, update_date, update_user_id)::text), ',' ORDER BY md5(row(card_id, card_doc_id, doc_role_cd, brand_opt_cds, approval_status_cd, applicability_basis_txt, approval_note, create_date, create_user_id, update_date, update_user_id)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_product_doc
UNION ALL SELECT 'card_source_evidence' AS t, count(*)::int AS n, md5(coalesce(string_agg(md5(row(card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_extr_stg_id, quote_txt, start_pos, end_pos, approval_status_cd)::text), ',' ORDER BY md5(row(card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_extr_stg_id, quote_txt, start_pos, end_pos, approval_status_cd)::text) COLLATE "C"), '')) AS f FROM db_pipeline.card_source_evidence)) x;
    IF v_diff > 0 THEN RAISE EXCEPTION '보존 컬럼 값이 달라진 테이블이 % 개 있습니다', v_diff; END IF;
    IF EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = 'db_pipeline.card_extr_stg'::regclass AND attname = 'stg_normalized_item' AND NOT attisdropped) THEN
        RAISE EXCEPTION 'stg_normalized_item이 남았습니다';
    END IF;
    IF (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'db_pipeline.card_extr_stg'::regclass AND conname = 'card_extr_stg_check1')
       IS DISTINCT FROM 'CHECK ((((stg_status)::text <> ALL (ARRAY[(''AUTO_APPROVED''::character varying)::text, (''MANUAL_APPROVED''::character varying)::text])) OR ((NOT ((stg_sql_check_cd)::text IS DISTINCT FROM ''OK''::text)) AND (stg_evidence_start_pos IS NOT NULL) AND (stg_evidence_end_pos IS NOT NULL) AND (btrim(stg_evidence_txt) <> ''''::text))))' THEN
        RAISE EXCEPTION '새 card_extr_stg_check1 정의가 예상과 다름';
    END IF;
    SELECT count(*) INTO v_left FROM db_pipeline.card_bnft b, jsonb_array_elements(b.rule_list) r
    WHERE r.value ?| ARRAY['predicate_state_cd', 'method_ver', 'calc_params', 'rule_priority', 'calc_method_cd', 'payout_unit_cd', 'basis_amt']::text[];
    IF v_left > 0 THEN RAISE EXCEPTION '규칙 계산 키가 남았습니다: %', v_left; END IF;
    SELECT count(*) INTO v_left FROM db_pipeline.card_bnft b,
        LATERAL (SELECT b.bnft_cond_expr AS e UNION ALL SELECT r.value->'cond_expr' FROM jsonb_array_elements(b.rule_list) r) x,
        jsonb_array_elements(CASE WHEN jsonb_typeof(x.e) = 'object' THEN x.e->'branches' ELSE '[]'::jsonb END) br,
        jsonb_array_elements(br.value->'atoms') a
    WHERE a.value ?| ARRAY['predicate_method_cd', 'predicate_method_ver', 'cond_params', 'card_excl_item_id', 'link_role_cd']::text[];
    IF v_left > 0 THEN RAISE EXCEPTION '조건 atom 계산 키가 남았습니다: %', v_left; END IF;
    IF NOT (SELECT bool_and(db_pipeline.fn_valid_rule_list(rule_list, 'LOCAL') AND db_pipeline.fn_valid_cond_expr(bnft_cond_expr))
            FROM db_pipeline.card_bnft) THEN RAISE EXCEPTION '새 계약을 통과하지 못한 혜택이 있습니다'; END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.v_common_cd_usage u WHERE u.common_code_grp_id IN ('PREDICATE_STATE', 'PREDICATE_METHOD', 'RULE_SELECT', 'LIMIT_PERIOD', 'LIMIT_UNIT', 'LIMIT_SCOPE', 'LIMIT_AGG', 'POOL_ROLE', 'CALC_METHOD', 'PAYOUT_UNIT')) THEN
        RAISE EXCEPTION '삭제한 코드 그룹을 쓰는 곳이 남았습니다';
    END IF;
    PERFORM count(*) FROM db_pipeline.v_card_integrity_issue;
    RAISE NOTICE '계산 구조 정리 완료';
END
$post$;

COMMIT;
