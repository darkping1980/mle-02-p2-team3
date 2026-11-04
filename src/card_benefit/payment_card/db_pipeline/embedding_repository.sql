--=========================================================
-- embedding_repository SQL mapper
--   혜택 검색 텍스트·임베딩 저장과 혜택 검색 조회.
--   vector 타입과 연산자는 search_path에 의존하지 않도록 extensions 스키마를 명시한다.
--   카드명은 검색 텍스트에 넣지 않고, 결과 표시와 문자열 검색에서만 card_product를 읽는다.
--=========================================================

-- name: select_card_bnft_rows
-- 검색 텍스트를 만들 카드별 혜택. :IDS가 NULL이면 전체다.
SELECT b.card_id, b.card_product_item_id AS card_bnft_id, b.item_nm AS bnft_nm, b.item_subtype_cd AS bnft_type_cd,
       t.common_cd_nm AS bnft_type_nm, b.item_origin_cd AS bnft_origin_cd, b.rule_list, b.item_cond_expr AS bnft_cond_expr,
       b.item_rule_txt AS bnft_rule_txt, b.item_search_txt AS bnft_search_txt,
       b.item_embedding IS NOT NULL AS has_embedding
FROM db_pipeline.card_product_item b
LEFT JOIN db_pipeline.common_cd t ON t.common_code_grp_id = 'BNFT_TYPE' AND t.common_cd = b.item_subtype_cd
WHERE b.item_type_cd = 'BENEFIT'
  AND (CAST(:IDS AS text[]) IS NULL OR b.card_product_item_id = ANY (CAST(:IDS AS text[])))
ORDER BY b.card_id, b.card_product_item_id
;

-- name: select_common_bnft_rows
-- 검색 텍스트를 만들 공통 혜택. 적용 카드는 읽지 않는다.
SELECT b.card_common_id, b.card_common_bnft_id, b.bnft_nm, b.bnft_type_cd, b.bnft_rule_txt, b.bnft_search_txt,
       b.bnft_embedding IS NOT NULL AS has_embedding,
       c.common_nm, br.common_cd_nm AS brand_nm, g.common_cd_nm AS service_grade_nm,
       t.common_cd_nm AS bnft_type_nm, s.common_cd_nm AS service_type_nm
FROM db_pipeline.card_common_bnft b
JOIN db_pipeline.card_common c ON c.card_common_id = b.card_common_id
LEFT JOIN db_pipeline.common_cd br ON br.common_code_grp_id = 'BRAND' AND br.common_cd = c.brand_cd
LEFT JOIN db_pipeline.common_cd g ON g.common_code_grp_id = 'SERVICE_GRADE' AND g.common_cd = c.service_grade_cd
LEFT JOIN db_pipeline.common_cd t ON t.common_code_grp_id = 'BNFT_TYPE' AND t.common_cd = b.bnft_type_cd
LEFT JOIN db_pipeline.common_cd s ON s.common_code_grp_id = 'SERVICE_TYPE' AND s.common_cd = b.service_type_cd
WHERE CAST(:IDS AS text[]) IS NULL OR b.card_common_bnft_id = ANY (CAST(:IDS AS text[]))
ORDER BY b.card_common_id, b.card_common_bnft_id
;

-- name: update_card_bnft_text
-- 텍스트가 바뀌면 벡터를 비운다. 벡터가 있으면 항상 현재 텍스트에서 만든 값이어야 한다.
UPDATE db_pipeline.card_product_item
SET item_search_txt = :BNFT_SEARCH_TXT, item_embedding = NULL, update_date = now()
WHERE card_id = :OWNER_ID AND card_product_item_id = :BNFT_ID
RETURNING card_product_item_id AS card_bnft_id;

-- name: update_common_bnft_text
UPDATE db_pipeline.card_common_bnft
SET bnft_search_txt = :BNFT_SEARCH_TXT, bnft_embedding = NULL, update_date = now(), update_user_id = :USER_ID
WHERE card_common_id = :OWNER_ID AND card_common_bnft_id = :BNFT_ID
RETURNING card_common_bnft_id;

-- name: update_card_bnft_embedding
-- 임베딩 입력과 저장 텍스트가 다르면 0건이 되어 저장하지 않는다.
UPDATE db_pipeline.card_product_item
SET item_embedding = CAST(:BNFT_EMBEDDING AS extensions.vector), update_date = now()
WHERE card_id = :OWNER_ID AND card_product_item_id = :BNFT_ID AND item_search_txt = :BNFT_SEARCH_TXT
RETURNING card_product_item_id AS card_bnft_id;

-- name: update_common_bnft_embedding
UPDATE db_pipeline.card_common_bnft
SET bnft_embedding = CAST(:BNFT_EMBEDDING AS extensions.vector), update_date = now(), update_user_id = :USER_ID
WHERE card_common_id = :OWNER_ID AND card_common_bnft_id = :BNFT_ID AND bnft_search_txt = :BNFT_SEARCH_TXT
RETURNING card_common_bnft_id;

-- name: insert_embedding_run
-- 임베딩 실행 이력. 벡터별 모델 컬럼을 두지 않고 실행 이력으로 저장 모델을 추적한다.
INSERT INTO db_pipeline.card_ai_run (run_stage_cd, run_call_mthd_cd, run_model_nm, run_prompt_ver, run_prompt_txt,
                                     run_param, create_user_id, update_user_id)
VALUES ('EMBED', 'PYTHON_RELAY', :RUN_MODEL_NM, :RUN_PROMPT_VER, :RUN_PROMPT_TXT, :RUN_PARAM, :USER_ID, :USER_ID)
RETURNING card_ai_run_id;

-- name: finish_embedding_run!
UPDATE db_pipeline.card_ai_run
SET run_status = :RUN_STATUS, run_end_date = now(), run_param = run_param || :RUN_RESULT,
    run_note = :RUN_NOTE, update_date = now(), update_user_id = :USER_ID
WHERE card_ai_run_id = :CARD_AI_RUN_ID
;

-- name: select_last_embedding_run
-- 벡터가 저장됐을 수 있는 최근 실행의 모델을 조회한다.
SELECT card_ai_run_id, run_model_nm, run_prompt_ver, run_status
FROM db_pipeline.card_ai_run
WHERE run_stage_cd = 'EMBED' AND run_status IN ('SUCCEEDED', 'PARTIAL')
ORDER BY run_start_date DESC, card_ai_run_id DESC
LIMIT 1
;

-- name: select_embedding_status
-- 테이블별 저장 현황. 차원이 다르거나 텍스트 없이 벡터만 있는 행은 0이어야 한다.
SELECT 'card_bnft' AS table_nm, count(*) AS row_cnt, count(item_search_txt) AS text_cnt, count(item_embedding) AS embedding_cnt,
       count(*) FILTER (WHERE extensions.vector_dims(item_embedding) <> :DIMENSIONS) AS bad_dim_cnt,
       count(*) FILTER (WHERE item_embedding IS NOT NULL AND item_search_txt IS NULL) AS vector_only_cnt
FROM db_pipeline.card_product_item WHERE item_type_cd = 'BENEFIT'   -- table_nm은 임베딩 대상 이름(카드 혜택)
UNION ALL
SELECT 'card_common_bnft', count(*), count(bnft_search_txt), count(bnft_embedding),
       count(*) FILTER (WHERE extensions.vector_dims(bnft_embedding) <> :DIMENSIONS),
       count(*) FILTER (WHERE bnft_embedding IS NOT NULL AND bnft_search_txt IS NULL)
FROM db_pipeline.card_common_bnft
;

-- name: search_card_bnft
-- 카드별 혜택 코사인 유사도 검색. 유사도는 후보 선정에만 쓴다.
SELECT b.card_id, b.card_product_item_id AS card_bnft_id, b.item_cd AS bnft_cd, b.item_nm AS bnft_nm,
       b.item_subtype_cd AS bnft_type_cd, b.item_origin_cd AS bnft_origin_cd, b.item_search_txt AS bnft_search_txt,
       b.verification_status_cd, p.product_nm,
       1 - (b.item_embedding OPERATOR(extensions.<=>) CAST(:QUERY_EMBEDDING AS extensions.vector)) AS similarity
FROM db_pipeline.card_product_item b
JOIN db_pipeline.card_product p ON p.card_id = b.card_id
WHERE b.item_type_cd = 'BENEFIT' AND b.item_embedding IS NOT NULL
  AND (b.item_valid_to_excl IS NULL OR b.item_valid_to_excl > CURRENT_DATE)
ORDER BY b.item_embedding OPERATOR(extensions.<=>) CAST(:QUERY_EMBEDDING AS extensions.vector)
LIMIT :TOP_K
;

-- name: search_common_bnft
-- 공통 혜택 코사인 유사도 검색. 적용 카드는 card_common_bnft_apply로만 확인한다.
SELECT b.card_common_id, b.card_common_bnft_id, b.bnft_cd, b.bnft_nm, b.bnft_type_cd, b.bnft_search_txt,
       c.common_nm,
       (SELECT COALESCE(jsonb_agg(jsonb_build_object('card_id', p.card_id, 'product_nm', p.product_nm) ORDER BY p.card_id), '[]'::jsonb)
        FROM db_pipeline.card_common_bnft_apply a
        JOIN db_pipeline.card_product p ON p.card_id = a.card_id
        WHERE a.card_common_id = b.card_common_id AND a.card_common_bnft_id = b.card_common_bnft_id) AS apply_cards,
       1 - (b.bnft_embedding OPERATOR(extensions.<=>) CAST(:QUERY_EMBEDDING AS extensions.vector)) AS similarity
FROM db_pipeline.card_common_bnft b
JOIN db_pipeline.card_common c ON c.card_common_id = b.card_common_id
WHERE b.bnft_embedding IS NOT NULL
  AND (b.bnft_valid_to_excl IS NULL OR b.bnft_valid_to_excl > CURRENT_DATE)
ORDER BY b.bnft_embedding OPERATOR(extensions.<=>) CAST(:QUERY_EMBEDDING AS extensions.vector)
LIMIT :TOP_K
;

-- name: keyword_card_bnft
-- 카드명·혜택명·실제 대상의 문자열 검색. rule_list 전체를 읽지 않아 제외 문구는 걸리지 않는다.
SELECT b.card_id, b.card_product_item_id AS card_bnft_id, b.item_cd AS bnft_cd, b.item_nm AS bnft_nm,
       b.item_subtype_cd AS bnft_type_cd, b.item_origin_cd AS bnft_origin_cd, b.item_search_txt AS bnft_search_txt,
       b.verification_status_cd, p.product_nm,
       (SELECT count(*) FROM unnest(CAST(:TERMS AS text[])) AS term(value)
        WHERE strpos(lower(p.product_nm), lower(term.value)) > 0 OR strpos(lower(b.item_nm), lower(term.value)) > 0
           OR EXISTS (SELECT 1 FROM db_pipeline.v_card_rule_target t
                      WHERE t.card_id = b.card_id AND t.card_product_item_id = b.card_product_item_id
                        AND strpos(lower(t.target_nm), lower(term.value)) > 0)) AS keyword_score
FROM db_pipeline.card_product_item b
JOIN db_pipeline.card_product p ON p.card_id = b.card_id
WHERE b.item_type_cd = 'BENEFIT'
  AND (b.item_valid_to_excl IS NULL OR b.item_valid_to_excl > CURRENT_DATE)
;

-- name: keyword_common_bnft
SELECT b.card_common_id, b.card_common_bnft_id, b.bnft_cd, b.bnft_nm, b.bnft_type_cd, b.bnft_search_txt, c.common_nm,
       (SELECT COALESCE(jsonb_agg(jsonb_build_object('card_id', p.card_id, 'product_nm', p.product_nm) ORDER BY p.card_id), '[]'::jsonb)
        FROM db_pipeline.card_common_bnft_apply a
        JOIN db_pipeline.card_product p ON p.card_id = a.card_id
        WHERE a.card_common_id = b.card_common_id AND a.card_common_bnft_id = b.card_common_bnft_id) AS apply_cards,
       (SELECT count(*) FROM unnest(CAST(:TERMS AS text[])) AS term(value)
        WHERE strpos(lower(b.bnft_nm), lower(term.value)) > 0 OR strpos(lower(c.common_nm), lower(term.value)) > 0
           OR EXISTS (SELECT 1 FROM db_pipeline.card_common_bnft_apply a
                      JOIN db_pipeline.card_product p ON p.card_id = a.card_id
                      WHERE a.card_common_id = b.card_common_id AND a.card_common_bnft_id = b.card_common_bnft_id
                        AND strpos(lower(p.product_nm), lower(term.value)) > 0)) AS keyword_score
FROM db_pipeline.card_common_bnft b
JOIN db_pipeline.card_common c ON c.card_common_id = b.card_common_id
WHERE (b.bnft_valid_to_excl IS NULL OR b.bnft_valid_to_excl > CURRENT_DATE)
;

-- name: select_card_bnft_detail
-- Neo4j에 없는 혜택의 상세. 카드 조건과 함께 읽는다.
SELECT b.card_id, b.card_product_item_id AS card_bnft_id, b.item_nm AS bnft_nm, b.item_subtype_cd AS bnft_type_cd,
       b.verification_status_cd, b.item_rule_txt AS bnft_rule_txt, b.item_limit_txt AS bnft_limit_txt, b.rule_list,
       b.item_cond_expr AS bnft_cond_expr, p.product_nm, p.card_cond_expr
FROM db_pipeline.card_product_item b
JOIN db_pipeline.card_product p ON p.card_id = b.card_id
WHERE b.card_id = :CARD_ID AND b.card_product_item_id = :BNFT_ID AND b.item_type_cd = 'BENEFIT'
;

-- name: select_common_bnft_detail
SELECT b.card_common_id, b.card_common_bnft_id, b.bnft_nm, b.bnft_type_cd, b.bnft_rule_txt, b.bnft_limit_txt,
       c.common_nm,
       (SELECT COALESCE(jsonb_agg(p.product_nm ORDER BY p.card_id), '[]'::jsonb)
        FROM db_pipeline.card_common_bnft_apply a
        JOIN db_pipeline.card_product p ON p.card_id = a.card_id
        WHERE a.card_common_id = b.card_common_id AND a.card_common_bnft_id = b.card_common_bnft_id) AS apply_cards
FROM db_pipeline.card_common_bnft b
JOIN db_pipeline.card_common c ON c.card_common_id = b.card_common_id
WHERE b.card_common_id = :COMMON_ID AND b.card_common_bnft_id = :BNFT_ID
;

-- name: select_card_bnft_evidence
SELECT DISTINCT l.ev_subject_cd, l.rule_key, l.ev_item_key, e.evidence_id, e.page_no, e.quote_txt, e.approval_status_cd
FROM db_pipeline.card_evidence_link l
JOIN db_pipeline.card_source_evidence e ON e.evidence_id = l.evidence_id
WHERE l.card_id = :CARD_ID AND l.card_product_item_id = :BNFT_ID
ORDER BY e.page_no, e.evidence_id
;

-- name: select_common_bnft_evidence
-- CARD_EVIDENCE_LINK가 공통 혜택을 담지 못해 문서와 추출 항목 경로로 찾는다.
SELECT DISTINCT 'BNFT' AS ev_subject_cd, NULL AS rule_key, '-' AS ev_item_key,
       e.evidence_id, e.page_no, e.quote_txt, e.approval_status_cd
FROM db_pipeline.card_common_bnft b
JOIN db_pipeline.card_common_doc d ON d.card_common_id = b.card_common_id
JOIN db_pipeline.card_extr_stg s
  ON s.card_doc_id = d.card_doc_id AND s.stg_kind_cd = 'BENEFIT' AND s.stg_raw_item->>'bnft_nm' = b.bnft_nm
 AND s.stg_sql_check_cd IS NOT NULL AND s.stg_parent_card_extr_stg_id IS NULL   -- 문서 단위 대표 혜택
JOIN db_pipeline.card_source_evidence e ON e.card_extr_stg_id = s.card_extr_stg_id
WHERE b.card_common_id = :COMMON_ID AND b.card_common_bnft_id = :BNFT_ID
ORDER BY e.page_no, e.evidence_id
;
