-- name: lock_card
SELECT card_id, product_cd, product_nm, issuer, card_kind_cd, product_status_cd, brand_opt_list
FROM db_pipeline.card_product WHERE card_id = :CARD_ID FOR UPDATE;

-- name: integrity_errors
SELECT gate_cd,issue_key FROM db_pipeline.v_card_integrity_issue
WHERE gate_cd NOT IN ('evidence_not_approved','rule_method_value_pending','predicate_params_pending');

-- name: find_card_by_code
SELECT card_id, product_cd, product_nm, issuer, card_kind_cd, product_status_cd, brand_opt_list
FROM db_pipeline.card_product WHERE product_cd = :PRODUCT_CD;

-- name: insert_card
INSERT INTO db_pipeline.card_product (product_cd,product_nm,issuer,card_kind_cd,brand_opt_list,create_user_id,update_user_id)
VALUES (:PRODUCT_CD,:PRODUCT_NM,:ISSUER,:CARD_KIND_CD,:BRAND_OPT_LIST,:USER_ID,:USER_ID)
ON CONFLICT (product_cd) DO NOTHING RETURNING card_id;

-- name: list_cards
SELECT card_id FROM db_pipeline.card_product WHERE product_status_cd = 'ACTIVE' ORDER BY card_id;

-- name: product_brand_evidence
SELECT d.doc_title,e.quote_txt,e.approval_status_cd,
       substring(c.chunk_raw_txt FROM e.start_pos FOR e.end_pos-e.start_pos+1) AS source_txt
FROM db_pipeline.card_product_doc pd
JOIN db_pipeline.card_doc d ON d.card_doc_id=pd.card_doc_id
JOIN db_pipeline.card_evidence_link l ON l.card_id=pd.card_id AND l.ev_subject_cd='CARD'
JOIN db_pipeline.card_source_evidence e ON e.evidence_id=l.evidence_id AND e.card_doc_id=pd.card_doc_id
JOIN db_pipeline.card_doc_chunk c ON (c.card_doc_id,c.page_no,c.card_doc_chunk_id)=(e.card_doc_id,e.page_no,e.card_doc_chunk_id)
WHERE pd.card_id=:CARD_ID AND pd.doc_role_cd='PRODUCT_GUIDE' AND d.doc_type_cd='PRODUCT_GUIDE'
  AND d.doc_status='ACTIVE' AND pd.approval_status_cd IN ('PENDING','APPROVED')
  AND e.approval_status_cd IN ('PENDING','APPROVED') AND e.start_pos IS NOT NULL AND e.end_pos IS NOT NULL;

-- name: list_runs
SELECT r.card_ai_run_id FROM db_pipeline.card_ai_run r JOIN db_pipeline.card_doc d
  ON d.card_doc_id = r.run_target_card_doc_id
WHERE r.run_status='SUCCEEDED' AND r.run_stage_cd='EXTRACT' AND d.doc_type_cd='BRAND_SERVICE'
  AND d.doc_status='ACTIVE' ORDER BY r.run_start_date, r.card_ai_run_id;

-- name: list_candidates
SELECT s.card_extr_stg_id, s.stg_raw_item, s.stg_normalized_item, s.stg_status,
       s.stg_sql_check_cd, d.card_doc_id, d.doc_family_cd, d.doc_sha256,d.doc_version_no
FROM db_pipeline.card_extr_stg s
JOIN db_pipeline.card_ai_run r ON r.card_ai_run_id=s.card_ai_run_id
JOIN db_pipeline.card_doc d ON d.card_doc_id=s.card_doc_id AND d.card_doc_id=r.run_target_card_doc_id
WHERE s.card_ai_run_id=:RUN_ID AND r.run_stage_cd='EXTRACT' AND r.run_status='SUCCEEDED'
  AND s.card_id IS NULL AND s.stg_kind_cd='BENEFIT' AND s.stg_normalized_item IS NOT NULL
  AND d.doc_type_cd='BRAND_SERVICE' AND d.doc_status='ACTIVE'
ORDER BY s.page_no,s.stg_item_seq;

-- name: candidate_evidence
SELECT e.evidence_id,e.quote_txt,e.start_pos,e.end_pos,e.approval_status_cd,
       e.card_doc_id,e.page_no,e.card_doc_chunk_id,
       substring(c.chunk_raw_txt FROM e.start_pos FOR e.end_pos-e.start_pos+1) AS source_txt
FROM db_pipeline.card_source_evidence e
JOIN db_pipeline.card_extr_stg s ON s.card_extr_stg_id=e.card_extr_stg_id
JOIN db_pipeline.card_doc_chunk c ON (c.card_doc_id,c.page_no,c.card_doc_chunk_id)=(e.card_doc_id,e.page_no,e.card_doc_chunk_id)
WHERE (s.card_extr_stg_id=:STG_ID OR s.stg_parent_card_extr_stg_id=:STG_ID)
  AND e.card_doc_id=s.card_doc_id AND e.page_no=s.page_no AND e.card_doc_chunk_id=s.card_doc_chunk_id
ORDER BY e.evidence_id;

-- name: find_benefit
SELECT * FROM db_pipeline.card_bnft WHERE card_id=:CARD_ID AND bnft_cd=:BNFT_CD;

-- name: prior_sources
SELECT DISTINCT d.doc_family_cd,d.doc_version_no,s.stg_raw_item,s.stg_normalized_item
FROM db_pipeline.card_evidence_link l
JOIN db_pipeline.card_source_evidence e ON e.evidence_id=l.evidence_id
JOIN db_pipeline.card_doc d ON d.card_doc_id=e.card_doc_id
JOIN db_pipeline.card_extr_stg s ON s.card_extr_stg_id=e.card_extr_stg_id
WHERE l.card_id=:CARD_ID AND l.card_bnft_id=:BNFT_ID AND s.stg_normalized_item IS NOT NULL;

-- name: insert_product_doc
INSERT INTO db_pipeline.card_product_doc (card_id,card_doc_id,doc_role_cd,brand_opt_cds,approval_status_cd,
  applicability_basis_txt,create_user_id,update_user_id)
VALUES (:CARD_ID,:DOC_ID,'BRAND_SERVICE',:BRAND_OPTS,'PENDING',:BASIS,:USER_ID,:USER_ID)
ON CONFLICT (card_id,card_doc_id) DO NOTHING RETURNING card_id;

-- name: get_product_doc
SELECT * FROM db_pipeline.card_product_doc WHERE card_id=:CARD_ID AND card_doc_id=:DOC_ID;

-- name: insert_pool
INSERT INTO db_pipeline.card_limit_pool (card_id,pool_scope_cd,period_cd,cap_unit_cd,aggregation_key_cd,tier_list)
VALUES (:CARD_ID,:POOL_SCOPE,:PERIOD,:CAP_UNIT,:AGGREGATION,:TIERS) RETURNING pool_id;

-- name: get_pool
SELECT * FROM db_pipeline.card_limit_pool WHERE card_id=:CARD_ID AND pool_id=:POOL_ID;

-- name: get_rule_pools
SELECT rule_key,pool_id,pool_role_cd FROM db_pipeline.card_bnft_rule_pool
WHERE card_id=:CARD_ID AND card_bnft_id=:BNFT_ID ORDER BY rule_key,pool_id;

-- name: insert_rule_pool
INSERT INTO db_pipeline.card_bnft_rule_pool (card_id,card_bnft_id,rule_key,pool_id,pool_role_cd)
VALUES (:CARD_ID,:BNFT_ID,:RULE_KEY,:POOL_ID,:POOL_ROLE) RETURNING pool_id;

-- name: valid_aggregation
SELECT common_cd FROM db_pipeline.common_cd WHERE common_code_grp_id='LIMIT_AGG' AND common_cd=:CODE;

-- name: insert_benefit
INSERT INTO db_pipeline.card_bnft (card_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,
  bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl)
VALUES (:CARD_ID,:BNFT_CD,:BNFT_NM,:BNFT_TYPE,'BRAND_SERVICE','BRAND',:BRAND_OPTS,:COND,NULL,:RULES,
  '[]'::jsonb,'PENDING_REVIEW',:VALID_FROM,:VALID_TO) ON CONFLICT (card_id,bnft_cd) DO NOTHING RETURNING card_bnft_id;

-- name: insert_evidence_link
INSERT INTO db_pipeline.card_evidence_link (card_id,ev_subject_cd,card_bnft_id,ev_item_cd,ev_item_key,evidence_id)
VALUES (:CARD_ID,'BNFT',:BNFT_ID,'SELF','-',:EVIDENCE_ID)
ON CONFLICT ON CONSTRAINT card_evidence_link_natural_key DO NOTHING RETURNING ev_link_id;

-- name: insert_pool_evidence_link
INSERT INTO db_pipeline.card_evidence_link (card_id,ev_subject_cd,pool_id,ev_item_cd,ev_item_key,evidence_id)
VALUES (:CARD_ID,'POOL',:POOL_ID,'SELF','-',:EVIDENCE_ID)
ON CONFLICT ON CONSTRAINT card_evidence_link_natural_key DO NOTHING RETURNING ev_link_id;

-- name: insert_rule_evidence_link
INSERT INTO db_pipeline.card_evidence_link (card_id,ev_subject_cd,card_bnft_id,rule_key,ev_item_cd,ev_item_key,evidence_id)
VALUES (:CARD_ID,'RULE',:BNFT_ID,:RULE_KEY,'SELF','-',:EVIDENCE_ID)
ON CONFLICT ON CONSTRAINT card_evidence_link_natural_key DO NOTHING RETURNING ev_link_id;

-- name: update_benefit
UPDATE db_pipeline.card_bnft SET bnft_nm=:BNFT_NM,bnft_type_cd=:BNFT_TYPE,
    bnft_cond_expr=:COND,rule_list=:RULES,bnft_valid_from=:VALID_FROM,bnft_valid_to_excl=:VALID_TO
WHERE card_id=:CARD_ID AND card_bnft_id=:BNFT_ID AND verification_status_cd='PENDING_REVIEW'
RETURNING card_bnft_id;
