-- 계산 구조 정리 전 실제 DB 정의(2026-11-03 조회). 정리 대상과 대체 대상만 모았다. 전체 카탈로그는 pre_cleanup_catalog.json.

-- VIEW v_card_rule: 상품 계산 규칙을 행으로 복원. V5 card_bnft_rule 조회 대체
CREATE VIEW db_pipeline.v_card_rule AS
 SELECT b.card_id,
    b.card_bnft_id,
    r.value ->> 'rule_key'::text AS rule_key,
    r.ord AS rule_seq,
    NULLIF(r.value -> 'cond_expr'::text, 'null'::jsonb) AS cond_expr,
    db_pipeline.fn_cond_spend_bound(NULLIF(r.value -> 'cond_expr'::text, 'null'::jsonb), 'cond_min_amt'::text)::numeric(18,2) AS spend_min_amt,
    db_pipeline.fn_cond_spend_bound(NULLIF(r.value -> 'cond_expr'::text, 'null'::jsonb), 'cond_max_amt_excl'::text)::numeric(18,2) AS spend_max_amt_excl,
    COALESCE(r.value -> 'target_list'::text, '[]'::jsonb) AS target_list,
    r.value ->> 'predicate_state_cd'::text AS predicate_state_cd,
    r.value ->> 'calc_method_cd'::text AS calc_method_cd,
    (r.value ->> 'method_ver'::text)::integer AS method_ver,
    ((r.value ->> 'value_num'::text))::numeric(18,4) AS value_num,
    r.value ->> 'value_unit_cd'::text AS value_unit_cd,
    r.value ->> 'payout_unit_cd'::text AS payout_unit_cd,
    ((r.value ->> 'basis_amt'::text))::numeric(18,2) AS basis_amt,
    NULLIF(r.value -> 'calc_params'::text, 'null'::jsonb) AS calc_params,
    (r.value ->> 'rule_priority'::text)::integer AS rule_priority,
    r.value ->> 'rule_status_cd'::text AS rule_status_cd
   FROM db_pipeline.card_bnft b
     CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) WITH ORDINALITY r(value, ord);

-- VIEW v_card_bnft_rule_effective: 혜택과 계산 규칙의 단일 출력. 제공 기간은 걸러내지 않으므로 조회 기준일로 판정. 값은 정책 후보이며 거래별 보상액이 아님
CREATE VIEW db_pipeline.v_card_bnft_rule_effective AS
 SELECT b.card_id,
    b.card_bnft_id,
    b.bnft_nm,
    b.bnft_origin_cd,
    b.bnft_scope_cd,
    b.bnft_brand_opt_cds,
    b.bnft_valid_from,
    b.bnft_valid_to_excl,
    r.rule_key,
    r.calc_method_cd,
    r.method_ver,
    r.value_num,
    r.value_unit_cd,
    r.payout_unit_cd,
    r.basis_amt,
    r.calc_params,
    r.predicate_state_cd,
    r.target_list,
    b.bnft_cond_expr,
    r.cond_expr AS rule_cond_expr,
    r.rule_status_cd
   FROM db_pipeline.card_bnft b
     JOIN db_pipeline.v_card_rule r ON r.card_id = b.card_id AND r.card_bnft_id::text = b.card_bnft_id::text;

-- VIEW v_card_cond_atom: 모든 조건식의 atom을 소유자와 함께 행으로 복원
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
         SELECT 'BNFT'::text,
            b_1.card_id,
            b_1.card_bnft_id,
            NULL::text,
            b_1.bnft_cond_expr
           FROM db_pipeline.card_bnft b_1
          WHERE b_1.bnft_cond_expr IS NOT NULL
        UNION ALL
         SELECT 'RULE'::text,
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
    a.value ->> 'predicate_method_cd'::text AS predicate_method_cd,
    (a.value ->> 'predicate_method_ver'::text)::integer AS predicate_method_ver,
    a.value -> 'cond_params'::text AS cond_params,
    a.value ->> 'card_excl_item_id'::text AS card_excl_item_id,
    a.value ->> 'excl_raw_txt'::text AS excl_raw_txt,
    a.value ->> 'cond_raw_txt'::text AS cond_raw_txt,
    a.value ->> 'link_role_cd'::text AS link_role_cd,
    a.value ->> 'cond_status_cd'::text AS cond_status_cd
   FROM src s
     CROSS JOIN LATERAL jsonb_array_elements(s.expr -> 'branches'::text) b(value)
     CROSS JOIN LATERAL jsonb_array_elements(b.value -> 'atoms'::text) a(value);

-- VIEW v_card_rule_target: 규칙 대상을 행으로 복원
CREATE VIEW db_pipeline.v_card_rule_target AS
 SELECT r.card_id,
    r.card_bnft_id,
    r.rule_key,
    t.value ->> 'target_type_cd'::text AS target_type_cd,
    t.value ->> 'target_key'::text AS target_key,
    t.value ->> 'target_nm'::text AS target_nm
   FROM db_pipeline.v_card_rule r
     CROSS JOIN LATERAL jsonb_array_elements(r.target_list) t(value);

-- VIEW v_common_cd_usage: 모든 공통코드 사용처(물리 컬럼·JSONB 키)와 소속 그룹. 공통코드 정합성 검증의 기준
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
 SELECT 'card_bnft.rule_select_cd'::text AS source_nm,
    'RULE_SELECT'::character varying(20) AS common_code_grp_id,
    card_bnft.rule_select_cd::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE card_bnft.rule_select_cd IS NOT NULL
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
 SELECT 'card_bnft.rule_list[].predicate_state_cd'::text AS source_nm,
    'PREDICATE_STATE'::character varying AS common_code_grp_id,
    v_card_rule.predicate_state_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE v_card_rule.predicate_state_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.rule_list[].calc_method_cd'::text AS source_nm,
    'CALC_METHOD'::character varying AS common_code_grp_id,
    v_card_rule.calc_method_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE v_card_rule.calc_method_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.rule_list[].value_unit_cd'::text AS source_nm,
    'VALUE_UNIT'::character varying AS common_code_grp_id,
    v_card_rule.value_unit_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE v_card_rule.value_unit_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.rule_list[].payout_unit_cd'::text AS source_nm,
    'PAYOUT_UNIT'::character varying AS common_code_grp_id,
    v_card_rule.payout_unit_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE v_card_rule.payout_unit_cd IS NOT NULL
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
 SELECT 'cond_expr atom predicate_method_cd'::text AS source_nm,
    'PREDICATE_METHOD'::character varying AS common_code_grp_id,
    v_card_cond_atom.predicate_method_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE v_card_cond_atom.predicate_method_cd IS NOT NULL
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

-- VIEW v_card_integrity_issue: 승인 전 정합성 게이트. 물리 FK가 없으므로 행이 1건이라도 있으면 승인하지 않음. *_pending은 확정 전 항목의 값 누락(검토 대기)이고 나머지는 무결성 위반
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
            v_card_cond_atom.predicate_method_cd,
            v_card_cond_atom.predicate_method_ver,
            v_card_cond_atom.cond_params,
            v_card_cond_atom.card_excl_item_id,
            v_card_cond_atom.excl_raw_txt,
            v_card_cond_atom.cond_raw_txt,
            v_card_cond_atom.link_role_cd,
            v_card_cond_atom.cond_status_cd
           FROM db_pipeline.v_card_cond_atom
        ), rule_value_gap AS (
         SELECT r.card_id,
            r.card_bnft_id,
            r.rule_key,
            r.rule_status_cd = 'CONFIRMED'::text OR b.verification_status_cd::text = 'CONFIRMED'::text AS final_yn
           FROM db_pipeline.v_card_rule r
             JOIN db_pipeline.card_bnft b ON b.card_id = r.card_id AND b.card_bnft_id::text = r.card_bnft_id::text
          WHERE r.rule_status_cd <> 'RETIRED'::text AND ((r.calc_method_cd = ANY (ARRAY['PERCENT_OF_TXN'::text, 'FIXED_PER_TXN'::text, 'UNITS_PER_AMOUNT'::text, 'MULTIPLY_EXTERNAL_POINTS'::text])) AND r.value_num IS NULL OR r.calc_method_cd = 'UNITS_PER_AMOUNT'::text AND r.basis_amt IS NULL OR r.calc_method_cd = 'PERCENT_OF_TXN'::text AND r.value_unit_cd IS DISTINCT FROM 'PERCENT'::text OR r.calc_method_cd = 'MULTIPLY_EXTERNAL_POINTS'::text AND r.value_unit_cd IS DISTINCT FROM 'MULTIPLIER'::text OR (r.calc_method_cd = ANY (ARRAY['FIXED_PER_TXN'::text, 'UNITS_PER_AMOUNT'::text])) AND (r.value_unit_cd = ANY (ARRAY['PERCENT'::text, 'MULTIPLIER'::text])))
        ), predicate_param_gap AS (
         SELECT a.owner_cd,
            a.card_id,
            a.atom_key,
            a.cond_status_cd = 'CONFIRMED'::text OR a.expr_status_cd = 'CONFIRMED'::text AS final_yn
           FROM atoms a
          WHERE a.cond_status_cd <> 'RETIRED'::text AND (a.predicate_method_cd = 'EVERY_MONTH_MIN_SPEND'::text AND (a.cond_min_amt IS NULL OR jsonb_typeof(a.cond_params -> 'window_months'::text) IS DISTINCT FROM 'number'::text) OR a.predicate_method_cd = 'MONTH_IN'::text AND
                CASE
                    WHEN jsonb_typeof(a.cond_params -> 'months'::text) = 'array'::text THEN jsonb_array_length(a.cond_params -> 'months'::text) = 0
                    ELSE true
                END)
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
 SELECT
        CASE
            WHEN g.final_yn THEN 'rule_method_value_missing'::text
            ELSE 'rule_method_value_pending'::text
        END AS gate_cd,
    (((g.card_id || '/'::text) || g.card_bnft_id::text) || '/'::text) || g.rule_key AS issue_key
   FROM rule_value_gap g
UNION ALL
 SELECT
        CASE
            WHEN g.final_yn THEN 'predicate_params_missing'::text
            ELSE 'predicate_params_pending'::text
        END AS gate_cd,
    (((g.owner_cd || '/'::text) || g.card_id) || '/'::text) || g.atom_key AS issue_key
   FROM predicate_param_gap g
UNION ALL
 SELECT 'excl_item_unknown'::text AS gate_cd,
    (a.owner_cd || '/'::text) || a.atom_key AS issue_key
   FROM atoms a
  WHERE a.card_excl_item_id IS NOT NULL AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_excl_item i
          WHERE i.card_excl_item_id::text = a.card_excl_item_id))
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

-- FUNCTION fn_valid_rule_list: 계산 규칙 목록 JSONB 계약 검증. 최종 규칙에는 pool_refs를 허용하지 않는다. p_owner는 LOCAL만 허용
CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_rule_list(p_list jsonb, p_owner text)
 RETURNS boolean
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
    v_rule jsonb;
    v_keys text[] := '{}';
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

        IF p_owner IS DISTINCT FROM 'LOCAL' OR v_rule ? 'pool_refs' THEN
            RETURN false;
        END IF;
    END LOOP;
    RETURN true;
END;
$function$;

-- FUNCTION fn_valid_cond_expr: 조건식 JSONB 계약 검증. branch 사이 OR, branch 안 atom AND, negate_yn=NOT
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
               AND coalesce(v_atom->>'card_excl_item_id', v_atom->>'excl_raw_txt', '') = '' THEN
                RETURN false;
            END IF;
            -- 술어 방법 코드와 버전은 짝으로 저장
            IF (v_atom->>'predicate_method_cd' IS NULL) <> (v_atom->>'predicate_method_ver' IS NULL) THEN
                RETURN false;
            END IF;
            IF jsonb_typeof(v_atom->'predicate_method_ver') NOT IN ('number','null') THEN
                RETURN false;
            END IF;
            IF (v_atom->>'predicate_method_ver')::integer < 1 THEN
                RETURN false;
            END IF;
            IF jsonb_typeof(v_atom->'cond_params') NOT IN ('object','null') THEN
                RETURN false;
            END IF;
        END LOOP;
    END LOOP;
    RETURN true;
END;
$function$;

-- FUNCTION fn_cond_spend_bound: 단일 branch의 전월 실적 구간 값 추출. OR식이나 구간 atom이 둘 이상이면 NULL을 반환하고 v_card_cond_atom으로 조회
CREATE OR REPLACE FUNCTION db_pipeline.fn_cond_spend_bound(p_expr jsonb, p_bound text)
 RETURNS numeric
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
    SELECT CASE WHEN count(*) = 1 THEN max((a.value->>p_bound)::numeric) END
    FROM jsonb_array_elements(p_expr->'branches') AS b(value)
    CROSS JOIN LATERAL jsonb_array_elements(b.value->'atoms') AS a(value)
    WHERE jsonb_array_length(p_expr->'branches') = 1
      AND a.value->>'cond_type_cd' = 'SPEND_REQ'
      AND a.value->>'cond_basis_cd' = 'PREV_MONTH_SPEND'
      AND (a.value->>'negate_yn')::boolean = false
$function$;

-- TABLE card_excl_item (0행)
--   card_excl_item_id character varying NOT NULL DEFAULT db_pipeline.fn_get_biz_id('card_excl_item'::text) -- 제외 항목 아이디
--   issuer text NOT NULL  -- 카드사
--   excl_item_nm text NOT NULL  -- 제외 항목명
--   excl_concept_cd character varying NULL  -- 제외 분류 개념
--   excl_item_desc text NULL  -- 제외 항목 설명
--   excl_alias_nms ARRAY NOT NULL DEFAULT '{}'::text[] -- 제외 항목 별칭
--   create_date timestamp with time zone NOT NULL DEFAULT now() -- 생성 일시
--   create_user_id character varying NOT NULL  -- 생성 사용자 아이디
--   update_date timestamp with time zone NOT NULL DEFAULT now() -- 수정 일시
--   update_user_id character varying NOT NULL  -- 수정 사용자 아이디
--   card_excl_item_issuer_excl_item_nm_key: UNIQUE (issuer, excl_item_nm)
--   card_excl_item_pkey: PRIMARY KEY (card_excl_item_id)
CREATE UNIQUE INDEX card_excl_item_issuer_excl_item_nm_key ON db_pipeline.card_excl_item USING btree (issuer, excl_item_nm);
CREATE UNIQUE INDEX card_excl_item_pkey ON db_pipeline.card_excl_item USING btree (card_excl_item_id);
CREATE INDEX ix_card_excl_item_alias_gin ON db_pipeline.card_excl_item USING gin (excl_alias_nms);
CREATE INDEX ix_card_excl_item_concept_key ON db_pipeline.card_excl_item USING btree (excl_concept_cd);

-- COLUMN card_bnft.rule_select_cd character varying(30) NULL -- 규칙 선택 방식 (값 0건)
-- COLUMN card_extr_stg.card_excl_item_id character varying(20) NULL -- 제외 항목 아이디 (값 0건)
