-- card_product_item 생성·이관·전환 되돌리기 (2026-11-04).

-- 1) backup_card_bnft를 card_bnft로 되돌린다. 2) 뷰를 전환 전 정의(백업 pre_calc_cleanup_20261104_141447 catalog.json)로 복원한다.

-- 3) 새 객체를 지운다. card_bnft·card_evidence_link 원본 데이터는 전 과정에서 바뀌지 않았다.

-- 주의: 전환 뒤 card_product_item에 새로 등록된 항목은 card_bnft에 없으므로, 실행 전에 따로 옮기거나 확인한다.

BEGIN;

ALTER TABLE db_pipeline.backup_card_bnft RENAME TO card_bnft;

COMMENT ON TABLE db_pipeline.card_bnft IS NULL;

CREATE OR REPLACE VIEW db_pipeline.v_card_bnft_rel AS
 SELECT b.card_id,
    b.card_bnft_id AS from_bnft_id,
    (x.value ->> 'to_bnft_id'::text) AS to_bnft_id,
    (x.value ->> 'relation_key'::text) AS relation_key,
    (x.value ->> 'rel_type_cd'::text) AS rel_type_cd,
    ((x.value ->> 'rel_priority'::text))::integer AS rel_priority,
    false AS reverse_yn
   FROM (db_pipeline.card_bnft b
     CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) x(value))
UNION ALL
 SELECT b.card_id,
    (x.value ->> 'to_bnft_id'::text) AS from_bnft_id,
    b.card_bnft_id AS to_bnft_id,
    (x.value ->> 'relation_key'::text) AS relation_key,
    (x.value ->> 'rel_type_cd'::text) AS rel_type_cd,
    ((x.value ->> 'rel_priority'::text))::integer AS rel_priority,
    true AS reverse_yn
   FROM (db_pipeline.card_bnft b
     CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) x(value))
  WHERE ((x.value ->> 'rel_type_cd'::text) = 'MUTUALLY_EXCLUSIVE'::text);

CREATE OR REPLACE VIEW db_pipeline.v_card_rule AS
 SELECT b.card_id,
    b.card_bnft_id,
    (r.value ->> 'rule_key'::text) AS rule_key,
    r.ord AS rule_seq,
    NULLIF((r.value -> 'cond_expr'::text), 'null'::jsonb) AS cond_expr,
    COALESCE((r.value -> 'target_list'::text), '[]'::jsonb) AS target_list,
    ((r.value ->> 'value_num'::text))::numeric(18,4) AS value_num,
    (r.value ->> 'value_unit_cd'::text) AS value_unit_cd,
    (r.value ->> 'rule_status_cd'::text) AS rule_status_cd
   FROM (db_pipeline.card_bnft b
     CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) WITH ORDINALITY r(value, ord));

CREATE OR REPLACE VIEW db_pipeline.v_card_cond_atom AS
 WITH src AS (
         SELECT 'CARD'::text AS owner_cd,
            p.card_id,
            NULL::character varying AS card_bnft_id,
            NULL::text AS rule_key,
            p.card_cond_expr AS expr
           FROM db_pipeline.card_product p
          WHERE (p.card_cond_expr IS NOT NULL)
        UNION ALL
         SELECT 'BNFT'::text,
            b_1.card_id,
            b_1.card_bnft_id,
            NULL::text,
            b_1.bnft_cond_expr
           FROM db_pipeline.card_bnft b_1
          WHERE (b_1.bnft_cond_expr IS NOT NULL)
        UNION ALL
         SELECT 'RULE'::text,
            r.card_id,
            r.card_bnft_id,
            r.rule_key,
            r.cond_expr
           FROM db_pipeline.v_card_rule r
          WHERE (r.cond_expr IS NOT NULL)
        )
 SELECT s.owner_cd,
    s.card_id,
    s.card_bnft_id,
    s.rule_key,
    (s.expr ->> 'expr_status_cd'::text) AS expr_status_cd,
    ((b.value ->> 'branch_no'::text))::integer AS branch_no,
    ((a.value ->> 'atom_seq'::text))::integer AS atom_seq,
    (a.value ->> 'atom_key'::text) AS atom_key,
    ((a.value ->> 'negate_yn'::text))::boolean AS negate_yn,
    (a.value ->> 'cond_type_cd'::text) AS cond_type_cd,
    (a.value ->> 'cond_basis_cd'::text) AS cond_basis_cd,
    ((a.value ->> 'cond_min_amt'::text))::numeric(18,2) AS cond_min_amt,
    ((a.value ->> 'cond_max_amt_excl'::text))::numeric(18,2) AS cond_max_amt_excl,
    (a.value ->> 'excl_raw_txt'::text) AS excl_raw_txt,
    (a.value ->> 'cond_raw_txt'::text) AS cond_raw_txt,
    (a.value ->> 'cond_status_cd'::text) AS cond_status_cd
   FROM ((src s
     CROSS JOIN LATERAL jsonb_array_elements((s.expr -> 'branches'::text)) b(value))
     CROSS JOIN LATERAL jsonb_array_elements((b.value -> 'atoms'::text)) a(value));

CREATE OR REPLACE VIEW db_pipeline.v_common_cd_usage AS
 SELECT 'card_product.card_kind_cd'::text AS source_nm,
    'CARD_KIND'::character varying(20) AS common_code_grp_id,
    (card_product.card_kind_cd)::text AS cd_value
   FROM db_pipeline.card_product
  WHERE (card_product.card_kind_cd IS NOT NULL)
UNION ALL
 SELECT 'card_product.product_status_cd'::text AS source_nm,
    'PRODUCT_STATUS'::character varying(20) AS common_code_grp_id,
    (card_product.product_status_cd)::text AS cd_value
   FROM db_pipeline.card_product
  WHERE (card_product.product_status_cd IS NOT NULL)
UNION ALL
 SELECT 'card_product.card_cond_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying(20) AS common_code_grp_id,
    (card_product.card_cond_status_cd)::text AS cd_value
   FROM db_pipeline.card_product
  WHERE (card_product.card_cond_status_cd IS NOT NULL)
UNION ALL
 SELECT 'card_product_doc.doc_role_cd'::text AS source_nm,
    'DOC_ROLE'::character varying(20) AS common_code_grp_id,
    (card_product_doc.doc_role_cd)::text AS cd_value
   FROM db_pipeline.card_product_doc
  WHERE (card_product_doc.doc_role_cd IS NOT NULL)
UNION ALL
 SELECT 'card_product_doc.approval_status_cd'::text AS source_nm,
    'APPROVAL_STATUS'::character varying(20) AS common_code_grp_id,
    (card_product_doc.approval_status_cd)::text AS cd_value
   FROM db_pipeline.card_product_doc
  WHERE (card_product_doc.approval_status_cd IS NOT NULL)
UNION ALL
 SELECT 'card_bnft.bnft_type_cd'::text AS source_nm,
    'BNFT_TYPE'::character varying(20) AS common_code_grp_id,
    (card_bnft.bnft_type_cd)::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE (card_bnft.bnft_type_cd IS NOT NULL)
UNION ALL
 SELECT 'card_bnft.bnft_origin_cd'::text AS source_nm,
    'BNFT_ORIGIN'::character varying(20) AS common_code_grp_id,
    (card_bnft.bnft_origin_cd)::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE (card_bnft.bnft_origin_cd IS NOT NULL)
UNION ALL
 SELECT 'card_bnft.bnft_scope_cd'::text AS source_nm,
    'BNFT_SCOPE'::character varying(20) AS common_code_grp_id,
    (card_bnft.bnft_scope_cd)::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE (card_bnft.bnft_scope_cd IS NOT NULL)
UNION ALL
 SELECT 'card_bnft.verification_status_cd'::text AS source_nm,
    'VERIFY_STATUS'::character varying(20) AS common_code_grp_id,
    (card_bnft.verification_status_cd)::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE (card_bnft.verification_status_cd IS NOT NULL)
UNION ALL
 SELECT 'card_source_evidence.approval_status_cd'::text AS source_nm,
    'APPROVAL_STATUS'::character varying(20) AS common_code_grp_id,
    (card_source_evidence.approval_status_cd)::text AS cd_value
   FROM db_pipeline.card_source_evidence
  WHERE (card_source_evidence.approval_status_cd IS NOT NULL)
UNION ALL
 SELECT 'card_evidence_link.ev_subject_cd'::text AS source_nm,
    'EV_SUBJECT'::character varying(20) AS common_code_grp_id,
    (card_evidence_link.ev_subject_cd)::text AS cd_value
   FROM db_pipeline.card_evidence_link
  WHERE (card_evidence_link.ev_subject_cd IS NOT NULL)
UNION ALL
 SELECT 'card_evidence_link.ev_item_cd'::text AS source_nm,
    'EV_ITEM'::character varying(20) AS common_code_grp_id,
    (card_evidence_link.ev_item_cd)::text AS cd_value
   FROM db_pipeline.card_evidence_link
  WHERE (card_evidence_link.ev_item_cd IS NOT NULL)
UNION ALL
 SELECT 'card_doc.doc_type_cd'::text AS source_nm,
    'DOC_TYPE'::character varying(20) AS common_code_grp_id,
    (card_doc.doc_type_cd)::text AS cd_value
   FROM db_pipeline.card_doc
  WHERE (card_doc.doc_type_cd IS NOT NULL)
UNION ALL
 SELECT 'card_doc.doc_status'::text AS source_nm,
    'DOC_STATUS'::character varying(20) AS common_code_grp_id,
    (card_doc.doc_status)::text AS cd_value
   FROM db_pipeline.card_doc
  WHERE (card_doc.doc_status IS NOT NULL)
UNION ALL
 SELECT 'card_doc_page.page_layer_cd'::text AS source_nm,
    'PAGE_LAYER'::character varying(20) AS common_code_grp_id,
    (card_doc_page.page_layer_cd)::text AS cd_value
   FROM db_pipeline.card_doc_page
  WHERE (card_doc_page.page_layer_cd IS NOT NULL)
UNION ALL
 SELECT 'card_doc_chunk.chunk_type_cd'::text AS source_nm,
    'CHUNK_TYPE'::character varying(20) AS common_code_grp_id,
    (card_doc_chunk.chunk_type_cd)::text AS cd_value
   FROM db_pipeline.card_doc_chunk
  WHERE (card_doc_chunk.chunk_type_cd IS NOT NULL)
UNION ALL
 SELECT 'card_doc_chunk.chunk_status'::text AS source_nm,
    'CHUNK_STATUS'::character varying(20) AS common_code_grp_id,
    (card_doc_chunk.chunk_status)::text AS cd_value
   FROM db_pipeline.card_doc_chunk
  WHERE (card_doc_chunk.chunk_status IS NOT NULL)
UNION ALL
 SELECT 'card_ai_run.run_stage_cd'::text AS source_nm,
    'RUN_STAGE'::character varying(20) AS common_code_grp_id,
    (card_ai_run.run_stage_cd)::text AS cd_value
   FROM db_pipeline.card_ai_run
  WHERE (card_ai_run.run_stage_cd IS NOT NULL)
UNION ALL
 SELECT 'card_ai_run.run_call_mthd_cd'::text AS source_nm,
    'RUN_CALL_METHOD'::character varying(20) AS common_code_grp_id,
    (card_ai_run.run_call_mthd_cd)::text AS cd_value
   FROM db_pipeline.card_ai_run
  WHERE (card_ai_run.run_call_mthd_cd IS NOT NULL)
UNION ALL
 SELECT 'card_ai_run.run_status'::text AS source_nm,
    'RUN_STATUS'::character varying(20) AS common_code_grp_id,
    (card_ai_run.run_status)::text AS cd_value
   FROM db_pipeline.card_ai_run
  WHERE (card_ai_run.run_status IS NOT NULL)
UNION ALL
 SELECT 'card_ai_call.call_status'::text AS source_nm,
    'CALL_STATUS'::character varying(20) AS common_code_grp_id,
    (card_ai_call.call_status)::text AS cd_value
   FROM db_pipeline.card_ai_call
  WHERE (card_ai_call.call_status IS NOT NULL)
UNION ALL
 SELECT 'card_extr_stg.stg_kind_cd'::text AS source_nm,
    'STG_KIND'::character varying(20) AS common_code_grp_id,
    (card_extr_stg.stg_kind_cd)::text AS cd_value
   FROM db_pipeline.card_extr_stg
  WHERE (card_extr_stg.stg_kind_cd IS NOT NULL)
UNION ALL
 SELECT 'card_extr_stg.stg_status'::text AS source_nm,
    'STG_STATUS'::character varying(20) AS common_code_grp_id,
    (card_extr_stg.stg_status)::text AS cd_value
   FROM db_pipeline.card_extr_stg
  WHERE (card_extr_stg.stg_status IS NOT NULL)
UNION ALL
 SELECT 'card_extr_stg.stg_ai_vrfy_cd'::text AS source_nm,
    'STG_AI_VRFY'::character varying(20) AS common_code_grp_id,
    (card_extr_stg.stg_ai_vrfy_cd)::text AS cd_value
   FROM db_pipeline.card_extr_stg
  WHERE (card_extr_stg.stg_ai_vrfy_cd IS NOT NULL)
UNION ALL
 SELECT 'card_product.brand_opt_list[].brand_cd'::text AS source_nm,
    'BRAND'::character varying AS common_code_grp_id,
    v_card_brand_opt.brand_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE (v_card_brand_opt.brand_cd IS NOT NULL)
UNION ALL
 SELECT 'card_product.brand_opt_list[].service_grade_cd'::text AS source_nm,
    'SERVICE_GRADE'::character varying AS common_code_grp_id,
    v_card_brand_opt.service_grade_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE (v_card_brand_opt.service_grade_cd IS NOT NULL)
UNION ALL
 SELECT 'card_product.brand_opt_list[].service_type_cd'::text AS source_nm,
    'SERVICE_TYPE'::character varying AS common_code_grp_id,
    v_card_brand_opt.service_type_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE (v_card_brand_opt.service_type_cd IS NOT NULL)
UNION ALL
 SELECT 'card_product.brand_opt_list[].brand_opt_status_cd'::text AS source_nm,
    'PRODUCT_STATUS'::character varying AS common_code_grp_id,
    v_card_brand_opt.brand_opt_status_cd AS cd_value
   FROM db_pipeline.v_card_brand_opt
  WHERE (v_card_brand_opt.brand_opt_status_cd IS NOT NULL)
UNION ALL
 SELECT 'card_bnft.rule_list[].value_unit_cd'::text AS source_nm,
    'VALUE_UNIT'::character varying AS common_code_grp_id,
    v_card_rule.value_unit_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE (v_card_rule.value_unit_cd IS NOT NULL)
UNION ALL
 SELECT 'card_bnft.rule_list[].rule_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying AS common_code_grp_id,
    v_card_rule.rule_status_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE (v_card_rule.rule_status_cd IS NOT NULL)
UNION ALL
 SELECT 'card_bnft.relation_list[].rel_type_cd'::text AS source_nm,
    'REL_TYPE'::character varying AS common_code_grp_id,
    v_card_bnft_rel.rel_type_cd AS cd_value
   FROM db_pipeline.v_card_bnft_rel
  WHERE ((v_card_bnft_rel.rel_type_cd IS NOT NULL) AND (NOT v_card_bnft_rel.reverse_yn))
UNION ALL
 SELECT 'rule_list[].target_list[].target_type_cd'::text AS source_nm,
    'TARGET_TYPE'::character varying AS common_code_grp_id,
    v_card_rule_target.target_type_cd AS cd_value
   FROM db_pipeline.v_card_rule_target
  WHERE (v_card_rule_target.target_type_cd IS NOT NULL)
UNION ALL
 SELECT 'cond_expr atom cond_type_cd'::text AS source_nm,
    'COND_TYPE'::character varying AS common_code_grp_id,
    v_card_cond_atom.cond_type_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE (v_card_cond_atom.cond_type_cd IS NOT NULL)
UNION ALL
 SELECT 'cond_expr atom cond_basis_cd'::text AS source_nm,
    'COND_BASIS'::character varying AS common_code_grp_id,
    v_card_cond_atom.cond_basis_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE (v_card_cond_atom.cond_basis_cd IS NOT NULL)
UNION ALL
 SELECT 'cond_expr atom cond_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying AS common_code_grp_id,
    v_card_cond_atom.cond_status_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE (v_card_cond_atom.cond_status_cd IS NOT NULL)
UNION ALL
 SELECT 'cond_expr.expr_status_cd'::text AS source_nm,
    'ITEM_STATUS'::character varying AS common_code_grp_id,
    v_card_cond_atom.expr_status_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE (v_card_cond_atom.expr_status_cd IS NOT NULL);

CREATE OR REPLACE VIEW db_pipeline.v_card_integrity_issue AS
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
          WHERE ((v_card_bnft_rel.rel_type_cd = 'FALLBACK_AFTER_CAP'::text) AND (NOT v_card_bnft_rel.reverse_yn))
        ), cycle AS (
         WITH RECURSIVE walk(card_id, start_id, cur_id, path) AS (
                 SELECT fallback.card_id,
                    fallback.from_bnft_id,
                    fallback.to_bnft_id,
                    ARRAY[fallback.from_bnft_id, (fallback.to_bnft_id)::character varying] AS "array"
                   FROM fallback
                UNION ALL
                 SELECT w.card_id,
                    w.start_id,
                    f.to_bnft_id,
                    (w.path || (f.to_bnft_id)::character varying)
                   FROM (walk w
                     JOIN fallback f ON (((f.card_id = w.card_id) AND ((f.from_bnft_id)::text = w.cur_id))))
                  WHERE (NOT (f.to_bnft_id = ANY ((w.path[2:])::text[])))
                )
         SELECT DISTINCT walk.card_id,
            walk.start_id
           FROM walk
          WHERE (walk.cur_id = (walk.start_id)::text)
        )
 SELECT 'bnft_without_product'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_bnft_id)::text) AS issue_key
   FROM db_pipeline.card_bnft x
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product p
          WHERE (p.card_id = x.card_id))))
UNION ALL
 SELECT 'local_confirmed_without_rule'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_bnft_id)::text) AS issue_key
   FROM db_pipeline.card_bnft x
  WHERE (((x.verification_status_cd)::text = 'CONFIRMED'::text) AND (jsonb_array_length(x.rule_list) = 0))
UNION ALL
 SELECT 'bnft_txt_without_evidence'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_bnft_id)::text) AS issue_key
   FROM db_pipeline.card_bnft x
  WHERE (((x.bnft_rule_txt IS NOT NULL) OR (x.bnft_limit_txt IS NOT NULL)) AND (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_evidence_link l
          WHERE ((l.card_id = x.card_id) AND ((l.card_bnft_id)::text = (x.card_bnft_id)::text) AND ((l.ev_subject_cd)::text = 'BNFT'::text) AND ((l.ev_item_cd)::text = 'SELF'::text))))))
UNION ALL
 SELECT 'rel_to_bnft_orphan'::text AS gate_cd,
    ((x.card_id || '/'::text) || x.relation_key) AS issue_key
   FROM db_pipeline.v_card_bnft_rel x
  WHERE ((NOT x.reverse_yn) AND (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_bnft b
          WHERE ((b.card_id = x.card_id) AND ((b.card_bnft_id)::text = x.to_bnft_id))))))
UNION ALL
 SELECT 'rel_mutual_stored_twice'::text AS gate_cd,
    ((((a.card_id || '/'::text) || (a.from_bnft_id)::text) || '/'::text) || a.to_bnft_id) AS issue_key
   FROM (db_pipeline.v_card_bnft_rel a
     JOIN db_pipeline.v_card_bnft_rel b ON (((a.card_id = b.card_id) AND ((a.from_bnft_id)::text = b.to_bnft_id) AND (a.to_bnft_id = (b.from_bnft_id)::text) AND (a.rel_type_cd = b.rel_type_cd))))
  WHERE ((NOT a.reverse_yn) AND (NOT b.reverse_yn) AND (a.rel_type_cd = 'MUTUALLY_EXCLUSIVE'::text) AND ((a.from_bnft_id)::text < a.to_bnft_id))
UNION ALL
 SELECT 'rel_fallback_cycle'::text AS gate_cd,
    ((c.card_id || '/'::text) || (c.start_id)::text) AS issue_key
   FROM cycle c
UNION ALL
 SELECT 'product_doc_without_product'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_doc_id)::text) AS issue_key
   FROM db_pipeline.card_product_doc x
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product p
          WHERE (p.card_id = x.card_id))))
UNION ALL
 SELECT 'product_doc_orphan'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_doc_id)::text) AS issue_key
   FROM db_pipeline.card_product_doc x
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_doc d
          WHERE ((d.card_doc_id)::text = (x.card_doc_id)::text))))
UNION ALL
 SELECT 'bnft_brand_opt_unknown'::text AS gate_cd,
    ((((b.card_id || '/'::text) || (b.card_bnft_id)::text) || '/'::text) || o.cd) AS issue_key
   FROM (db_pipeline.card_bnft b
     CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) o(cd))
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.v_card_brand_opt v
          WHERE ((v.card_id = b.card_id) AND (v.brand_opt_cd = o.cd)))))
UNION ALL
 SELECT 'doc_brand_opt_unknown'::text AS gate_cd,
    ((((d.card_id || '/'::text) || (d.card_doc_id)::text) || '/'::text) || o.cd) AS issue_key
   FROM (db_pipeline.card_product_doc d
     CROSS JOIN LATERAL unnest(d.brand_opt_cds) o(cd))
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.v_card_brand_opt v
          WHERE ((v.card_id = d.card_id) AND (v.brand_opt_cd = o.cd)))))
UNION ALL
 SELECT 'evidence_source_orphan'::text AS gate_cd,
    e.evidence_id AS issue_key
   FROM db_pipeline.card_source_evidence e
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_doc_chunk c
          WHERE (((c.card_doc_id)::text = (e.card_doc_id)::text) AND (c.page_no = e.page_no) AND ((c.card_doc_chunk_id)::text = (e.card_doc_chunk_id)::text)))))
UNION ALL
 SELECT 'evidence_doc_not_linked'::text AS gate_cd,
    ((l.card_id || '/'::text) || (l.evidence_link_id)::text) AS issue_key
   FROM (db_pipeline.card_evidence_link l
     JOIN db_pipeline.card_source_evidence e USING (evidence_id))
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc d
          WHERE ((d.card_id = l.card_id) AND ((d.card_doc_id)::text = (e.card_doc_id)::text)))))
UNION ALL
 SELECT 'evidence_not_approved'::text AS gate_cd,
    l.evidence_id AS issue_key
   FROM (( SELECT DISTINCT card_evidence_link.evidence_id
           FROM db_pipeline.card_evidence_link) l
     LEFT JOIN db_pipeline.card_source_evidence e USING (evidence_id))
  WHERE ((e.evidence_id IS NULL) OR ((e.approval_status_cd)::text <> 'APPROVED'::text))
UNION ALL
 SELECT 'evidence_subject_orphan'::text AS gate_cd,
    ((l.card_id || '/'::text) || (l.evidence_link_id)::text) AS issue_key
   FROM db_pipeline.card_evidence_link l
  WHERE (NOT
        CASE l.ev_subject_cd
            WHEN 'CARD'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.card_product p
              WHERE (p.card_id = l.card_id)))
            WHEN 'BNFT'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.card_bnft b
              WHERE ((b.card_id = l.card_id) AND ((b.card_bnft_id)::text = (l.card_bnft_id)::text))))
            WHEN 'RULE'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_rule r
              WHERE ((r.card_id = l.card_id) AND ((r.card_bnft_id)::text = (l.card_bnft_id)::text) AND (r.rule_key = (l.rule_key)::text))))
            WHEN 'REL'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_bnft_rel r
              WHERE ((NOT r.reverse_yn) AND (r.card_id = l.card_id) AND ((r.from_bnft_id)::text = (l.card_bnft_id)::text) AND (r.relation_key = (l.relation_key)::text))))
            ELSE false
        END)
UNION ALL
 SELECT 'evidence_item_key_missing'::text AS gate_cd,
    ((l.card_id || '/'::text) || (l.evidence_link_id)::text) AS issue_key
   FROM db_pipeline.card_evidence_link l
  WHERE (((l.ev_item_cd)::text <> 'SELF'::text) AND (NOT
        CASE l.ev_item_cd
            WHEN 'COND'::text THEN (EXISTS ( SELECT 1
               FROM atoms a
              WHERE ((a.card_id = l.card_id) AND (a.atom_key = (l.ev_item_key)::text) AND (NOT ((a.card_bnft_id)::text IS DISTINCT FROM (l.card_bnft_id)::text)) AND (NOT (a.rule_key IS DISTINCT FROM (l.rule_key)::text)))))
            WHEN 'TARGET'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_rule_target t
              WHERE ((t.card_id = l.card_id) AND ((t.card_bnft_id)::text = (l.card_bnft_id)::text) AND (t.rule_key = (l.rule_key)::text) AND (t.target_key = (l.ev_item_key)::text))))
            ELSE false
        END))
UNION ALL
 SELECT 'product_doc_role_type_mismatch'::text AS gate_cd,
    ((x.card_id || '/'::text) || (x.card_doc_id)::text) AS issue_key
   FROM (db_pipeline.card_product_doc x
     JOIN db_pipeline.card_doc d ON (((d.card_doc_id)::text = (x.card_doc_id)::text)))
  WHERE (((x.doc_role_cd)::text = 'BRAND_SERVICE'::text) AND ((d.doc_type_cd)::text <> 'BRAND_SERVICE'::text))
UNION ALL
 SELECT 'brand_doc_option_conflict'::text AS gate_cd,
    z.card_doc_id AS issue_key
   FROM ( SELECT x.card_doc_id
           FROM ((db_pipeline.card_product_doc x
             CROSS JOIN LATERAL unnest(x.brand_opt_cds) o(cd))
             JOIN db_pipeline.v_card_brand_opt v ON (((v.card_id = x.card_id) AND (v.brand_opt_cd = o.cd))))
          WHERE ((x.doc_role_cd)::text = 'BRAND_SERVICE'::text)
          GROUP BY x.card_doc_id
         HAVING (count(DISTINCT ROW(v.brand_cd, v.service_grade_cd, v.service_type_cd)) > 1)) z
UNION ALL
 SELECT 'brand_bnft_doc_not_linked'::text AS gate_cd,
    ((((b.card_id || '/'::text) || (b.card_bnft_id)::text) || '/'::text) || o.cd) AS issue_key
   FROM (db_pipeline.card_bnft b
     CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) o(cd))
  WHERE (((b.bnft_origin_cd)::text = 'BRAND_SERVICE'::text) AND (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc x
          WHERE ((x.card_id = b.card_id) AND ((x.doc_role_cd)::text = 'BRAND_SERVICE'::text) AND (o.cd = ANY (x.brand_opt_cds)))))))
UNION ALL
 SELECT 'brand_bnft_confirmed_without_evidence'::text AS gate_cd,
    ((b.card_id || '/'::text) || (b.card_bnft_id)::text) AS issue_key
   FROM db_pipeline.card_bnft b
  WHERE (((b.bnft_origin_cd)::text = 'BRAND_SERVICE'::text) AND ((b.verification_status_cd)::text = 'CONFIRMED'::text) AND (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_evidence_link l
          WHERE ((l.card_id = b.card_id) AND ((l.card_bnft_id)::text = (b.card_bnft_id)::text))))))
UNION ALL
 SELECT 'evidence_brand_opt_mismatch'::text AS gate_cd,
    ((l.card_id || '/'::text) || (l.evidence_link_id)::text) AS issue_key
   FROM (((db_pipeline.card_evidence_link l
     JOIN db_pipeline.card_source_evidence e USING (evidence_id))
     JOIN db_pipeline.card_bnft b ON (((b.card_id = l.card_id) AND ((b.card_bnft_id)::text = (l.card_bnft_id)::text))))
     JOIN db_pipeline.card_product_doc x ON (((x.card_id = l.card_id) AND ((x.card_doc_id)::text = (e.card_doc_id)::text))))
  WHERE (((x.doc_role_cd)::text = 'BRAND_SERVICE'::text) AND (NOT (COALESCE(b.bnft_brand_opt_cds, '{}'::text[]) && x.brand_opt_cds)))
UNION ALL
 SELECT 'stg_card_not_linked'::text AS gate_cd,
    s.card_extr_stg_id AS issue_key
   FROM db_pipeline.card_extr_stg s
  WHERE ((s.card_id IS NOT NULL) AND (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc x
          WHERE ((x.card_id = s.card_id) AND ((x.card_doc_id)::text = (s.card_doc_id)::text))))))
UNION ALL
 SELECT 'common_cd_invalid'::text AS gate_cd,
    ((u.source_nm || '='::text) || u.cd_value) AS issue_key
   FROM db_pipeline.v_common_cd_usage u
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_cd c
          WHERE (((c.common_code_grp_id)::text = (u.common_code_grp_id)::text) AND ((c.common_cd)::text = u.cd_value)))))
UNION ALL
 SELECT 'common_cd_group_orphan'::text AS gate_cd,
    (((c.common_code_grp_id)::text || '/'::text) || (c.common_cd)::text) AS issue_key
   FROM db_pipeline.common_cd c
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_code_grp g
          WHERE ((g.common_code_grp_id)::text = (c.common_code_grp_id)::text))))
UNION ALL
 SELECT 'common_code_grp_empty'::text AS gate_cd,
    g.common_code_grp_id AS issue_key
   FROM db_pipeline.common_code_grp g
  WHERE (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.common_cd c
          WHERE ((c.common_code_grp_id)::text = (g.common_code_grp_id)::text))));

DROP VIEW IF EXISTS db_pipeline.v_card_product_item_evidence;

DROP TABLE IF EXISTS db_pipeline.card_product_item;

DROP FUNCTION IF EXISTS db_pipeline.fn_valid_item_data(text, jsonb);

DROP SEQUENCE IF EXISTS db_pipeline.seq_card_product_item;

DELETE FROM db_pipeline.common_cd WHERE create_user_id = 'P1_PRODUCT_ITEM';

DELETE FROM db_pipeline.common_code_grp WHERE create_user_id = 'P1_PRODUCT_ITEM';

COMMIT;
