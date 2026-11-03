-- name: lock_card
SELECT card_id, product_cd, product_nm, issuer, card_kind_cd, product_status_cd, brand_opt_list
FROM db_pipeline.card_product WHERE card_id = :CARD_ID FOR UPDATE;

-- name: integrity_errors
SELECT gate_cd,issue_key FROM db_pipeline.v_card_integrity_issue
WHERE gate_cd NOT IN ('evidence_not_approved','rule_method_value_pending','predicate_params_pending');

-- name: common_integrity_errors
-- v_card_integrity_issue와 v_common_cd_usage가 공통서비스 테이블을 보지 않아 등록 시 별도로 검사한다.
SELECT 'common_doc_orphan' AS gate_cd, x.card_common_id||'/'||x.card_doc_id AS issue_key
FROM db_pipeline.card_common_doc x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_common c WHERE c.card_common_id=x.card_common_id)
   OR NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc d WHERE d.card_doc_id=x.card_doc_id AND d.doc_type_cd='BRAND_SERVICE')
UNION ALL
SELECT 'common_bnft_orphan', b.card_common_id||'/'||b.card_common_bnft_id
FROM db_pipeline.card_common_bnft b
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_common c WHERE c.card_common_id=b.card_common_id)
UNION ALL
SELECT 'common_apply_orphan', a.card_common_id||'/'||a.card_common_bnft_id||'/'||a.card_id
FROM db_pipeline.card_common_bnft_apply a
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_common_bnft b
                  WHERE b.card_common_id=a.card_common_id AND b.card_common_bnft_id=a.card_common_bnft_id)
   OR NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id=a.card_id)
UNION ALL
SELECT 'common_code_invalid', 'card_common_bnft/'||b.card_common_bnft_id
FROM db_pipeline.card_common_bnft b
WHERE (b.bnft_type_cd IS NOT NULL AND NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd x WHERE x.common_code_grp_id='BNFT_TYPE' AND x.common_cd=b.bnft_type_cd))
   OR (b.service_type_cd IS NOT NULL AND NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd x WHERE x.common_code_grp_id='SERVICE_TYPE' AND x.common_cd=b.service_type_cd))
UNION ALL
SELECT 'common_code_invalid', 'card_common/'||c.card_common_id
FROM db_pipeline.card_common c
WHERE (c.brand_cd IS NOT NULL AND NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd x WHERE x.common_code_grp_id='BRAND' AND x.common_cd=c.brand_cd))
   OR (c.service_grade_cd IS NOT NULL AND NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd x WHERE x.common_code_grp_id='SERVICE_GRADE' AND x.common_cd=c.service_grade_cd));

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
SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,verification_status_cd
FROM db_pipeline.card_bnft WHERE card_id=:CARD_ID AND bnft_cd=:BNFT_CD;

-- name: brand_bnft_compare
-- 카드별 BRAND_SERVICE 행과 같은 bnft_cd의 공통 혜택을 항목별로 나란히 읽는다. 판정은 Python이 한다.
SELECT b.card_id, b.card_bnft_id, b.bnft_cd, b.bnft_nm, b.bnft_type_cd, b.bnft_valid_from, b.bnft_valid_to_excl,
       b.bnft_rule_txt, b.bnft_limit_txt, b.verification_status_cd,
       (SELECT array_agg(DISTINCT o.brand_cd || '/' || o.service_grade_cd)
        FROM unnest(b.bnft_brand_opt_cds) AS x(cd)
        JOIN db_pipeline.v_card_brand_opt o ON o.card_id = b.card_id AND o.brand_opt_cd = x.cd) AS brand_grades,
       (SELECT array_agg(DISTINCT l.evidence_id::text) FROM db_pipeline.card_evidence_link l
        WHERE l.card_id = b.card_id AND l.card_bnft_id = b.card_bnft_id) AS evidence_ids,
       (SELECT array_agg(DISTINCT e.card_doc_id::text) FROM db_pipeline.card_evidence_link l
        JOIN db_pipeline.card_source_evidence e ON e.evidence_id = l.evidence_id
        WHERE l.card_id = b.card_id AND l.card_bnft_id = b.card_bnft_id) AS doc_ids,
       cb.card_common_id, cb.card_common_bnft_id, cb.bnft_nm AS common_bnft_nm, cb.bnft_type_cd AS common_bnft_type_cd,
       cb.bnft_valid_from AS common_valid_from, cb.bnft_valid_to_excl AS common_valid_to_excl,
       cb.bnft_rule_txt AS common_rule_txt, cb.bnft_limit_txt AS common_limit_txt,
       c.brand_cd || '/' || c.service_grade_cd AS common_brand_grade,
       (SELECT array_agg(d.card_doc_id::text) FROM db_pipeline.card_common_doc d
        WHERE d.card_common_id = cb.card_common_id) AS common_doc_ids,
       (SELECT array_agg(DISTINCT e.evidence_id::text) FROM db_pipeline.card_common_doc d
        JOIN db_pipeline.card_extr_stg s
          ON s.card_doc_id = d.card_doc_id AND s.stg_kind_cd = 'BENEFIT' AND s.stg_normalized_item->>'bnft_nm' = cb.bnft_nm
        JOIN db_pipeline.card_source_evidence e ON e.card_extr_stg_id = s.card_extr_stg_id
        WHERE d.card_common_id = cb.card_common_id) AS common_evidence_ids,
       EXISTS (SELECT 1 FROM db_pipeline.card_common_bnft_apply a
               WHERE a.card_common_id = cb.card_common_id AND a.card_common_bnft_id = cb.card_common_bnft_id
                 AND a.card_id = b.card_id) AS applied
FROM db_pipeline.card_bnft b
LEFT JOIN db_pipeline.card_common_bnft cb ON cb.bnft_cd = b.bnft_cd
LEFT JOIN db_pipeline.card_common c ON c.card_common_id = cb.card_common_id
WHERE b.bnft_origin_cd = 'BRAND_SERVICE'
ORDER BY b.card_id, b.card_bnft_id;

-- name: insert_evidence_link
-- 원문 근거의 문서·페이지·청크 ID는 card_source_evidence에서 evidence_id로 읽어 승계한다. 원문 근거가 없으면 등록하지 않는다.
INSERT INTO db_pipeline.card_evidence_link (card_doc_id,page_no,card_doc_chunk_id,evidence_id,card_id,ev_subject_cd,card_bnft_id,ev_item_cd,ev_item_key)
SELECT e.card_doc_id,e.page_no,e.card_doc_chunk_id,e.evidence_id,CAST(:CARD_ID AS bigint),'BNFT',CAST(:BNFT_ID AS varchar),'SELF','-'
FROM db_pipeline.card_source_evidence e WHERE e.evidence_id=:EVIDENCE_ID
ON CONFLICT ON CONSTRAINT card_evidence_link_natural_key DO NOTHING RETURNING evidence_link_id;

-- name: insert_rule_evidence_link
-- 원문 근거의 문서·페이지·청크 ID는 card_source_evidence에서 evidence_id로 읽어 승계한다. 원문 근거가 없으면 등록하지 않는다.
INSERT INTO db_pipeline.card_evidence_link (card_doc_id,page_no,card_doc_chunk_id,evidence_id,card_id,ev_subject_cd,card_bnft_id,rule_key,ev_item_cd,ev_item_key)
SELECT e.card_doc_id,e.page_no,e.card_doc_chunk_id,e.evidence_id,CAST(:CARD_ID AS bigint),'RULE',CAST(:BNFT_ID AS varchar),CAST(:RULE_KEY AS varchar),'SELF','-'
FROM db_pipeline.card_source_evidence e WHERE e.evidence_id=:EVIDENCE_ID
ON CONFLICT ON CONSTRAINT card_evidence_link_natural_key DO NOTHING RETURNING evidence_link_id;

-- name: list_product_candidates
-- 상품설명서 추출 혜택. 상품·문서 연결이 있어야 하고 다른 페이지로 합쳐진 행은 읽지 않는다.
SELECT s.card_extr_stg_id,s.stg_raw_item,s.stg_normalized_item,s.stg_status,s.stg_sql_check_cd,s.card_doc_id
FROM db_pipeline.card_extr_stg s
JOIN db_pipeline.card_ai_run r ON r.card_ai_run_id=s.card_ai_run_id
JOIN db_pipeline.card_doc d ON d.card_doc_id=s.card_doc_id AND d.card_doc_id=r.run_target_card_doc_id
JOIN db_pipeline.card_product_doc pd ON pd.card_id=s.card_id AND pd.card_doc_id=s.card_doc_id AND pd.doc_role_cd='PRODUCT_GUIDE'
WHERE s.card_ai_run_id=:RUN_ID AND s.card_id=:CARD_ID AND s.stg_kind_cd='BENEFIT' AND s.stg_normalized_item IS NOT NULL
  AND d.doc_type_cd='PRODUCT_GUIDE' AND d.doc_status='ACTIVE' AND pd.approval_status_cd<>'REJECTED'
ORDER BY s.page_no,s.stg_item_seq;

-- name: insert_local_benefit
INSERT INTO db_pipeline.card_bnft (card_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,
  bnft_cond_expr,rule_list,relation_list,verification_status_cd,bnft_rule_txt,bnft_limit_txt)
VALUES (:CARD_ID,:BNFT_CD,:BNFT_NM,:BNFT_TYPE,'LOCAL','PRODUCT',:COND,:RULES,'[]'::jsonb,'PENDING_REVIEW',:RULE_TXT,:LIMIT_TXT)
ON CONFLICT (card_id,bnft_cd) DO NOTHING RETURNING card_bnft_id;

-- name: find_common
SELECT card_common_id,common_cd,common_nm,brand_cd,service_grade_cd FROM db_pipeline.card_common WHERE common_cd=:COMMON_CD;

-- name: insert_common
INSERT INTO db_pipeline.card_common (common_cd,common_nm,brand_cd,service_grade_cd,common_note,create_user_id,update_user_id)
VALUES (:COMMON_CD,:COMMON_NM,:BRAND_CD,:SERVICE_GRADE_CD,:COMMON_NOTE,:USER_ID,:USER_ID)
ON CONFLICT (common_cd) DO NOTHING RETURNING card_common_id;

-- name: find_doc_type
SELECT card_doc_id,doc_type_cd,doc_status FROM db_pipeline.card_doc WHERE card_doc_id=:DOC_ID;

-- name: insert_common_doc
INSERT INTO db_pipeline.card_common_doc (card_common_id,card_doc_id) VALUES (:COMMON_ID,:DOC_ID)
ON CONFLICT (card_common_id,card_doc_id) DO NOTHING RETURNING card_doc_id;

-- name: common_of_doc
-- 후보는 문서를 통해서만 공통서비스에 속한다.
SELECT c.card_common_id,c.common_cd,c.common_nm,c.brand_cd,c.service_grade_cd
FROM db_pipeline.card_common_doc d JOIN db_pipeline.card_common c ON c.card_common_id=d.card_common_id
WHERE d.card_doc_id=:DOC_ID ORDER BY c.card_common_id;

-- name: lock_common
SELECT card_common_id FROM db_pipeline.card_common WHERE card_common_id=:COMMON_ID FOR UPDATE;

-- name: find_common_bnft
SELECT card_common_id,card_common_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,service_type_cd,bnft_rule_txt,bnft_limit_txt,
       bnft_valid_from,bnft_valid_to_excl
FROM db_pipeline.card_common_bnft WHERE card_common_id=:COMMON_ID AND bnft_cd=:BNFT_CD;

-- name: insert_common_bnft
INSERT INTO db_pipeline.card_common_bnft (card_common_id,bnft_cd,bnft_nm,bnft_type_cd,service_type_cd,bnft_rule_txt,bnft_limit_txt,
  bnft_valid_from,bnft_valid_to_excl,create_user_id,update_user_id)
VALUES (:COMMON_ID,:BNFT_CD,:BNFT_NM,:BNFT_TYPE,:SERVICE_TYPE,:RULE_TXT,:LIMIT_TXT,:VALID_FROM,:VALID_TO,:USER_ID,:USER_ID)
ON CONFLICT (card_common_id,bnft_cd) DO NOTHING RETURNING card_common_bnft_id;

-- name: update_common_bnft
-- 문서 개정 반영. 입력 원문이 바뀌므로 검색 텍스트와 벡터를 비우고 다시 만든다.
UPDATE db_pipeline.card_common_bnft SET bnft_nm=:BNFT_NM,bnft_type_cd=:BNFT_TYPE,service_type_cd=:SERVICE_TYPE,
    bnft_rule_txt=:RULE_TXT,bnft_limit_txt=:LIMIT_TXT,bnft_valid_from=:VALID_FROM,bnft_valid_to_excl=:VALID_TO,
    bnft_search_txt=NULL,bnft_embedding=NULL,update_date=now(),update_user_id=:USER_ID
WHERE card_common_id=:COMMON_ID AND card_common_bnft_id=:BNFT_ID RETURNING card_common_bnft_id;

-- name: prior_common_sources
-- 같은 공통서비스 문서의 후보. 현재 행이 수동 수정 없이 이전 판에서 왔는지 비교한다.
SELECT DISTINCT d.doc_family_cd,d.doc_version_no,s.stg_raw_item,s.stg_normalized_item
FROM db_pipeline.card_common_doc x
JOIN db_pipeline.card_doc d ON d.card_doc_id=x.card_doc_id
JOIN db_pipeline.card_extr_stg s ON s.card_doc_id=d.card_doc_id
WHERE x.card_common_id=:COMMON_ID AND s.stg_kind_cd='BENEFIT' AND s.stg_normalized_item IS NOT NULL;

-- name: insert_common_apply
INSERT INTO db_pipeline.card_common_bnft_apply (card_common_id,card_common_bnft_id,card_id)
VALUES (:COMMON_ID,:BNFT_ID,:CARD_ID)
ON CONFLICT (card_common_id,card_common_bnft_id,card_id) DO NOTHING RETURNING card_id;
