--=========================================================
-- extraction_repository SQL mapper
--   파일 이름(extraction_repository)이 namespace이며, Python에서는 "extraction_repository.쿼리이름"으로 호출한다.
--   테이블 앞의 db_pipeline은 namespace가 아니라 DB 스키마다.
--   AI 실행 이력, 페이지별 추출 원본, 문서 단위 통합 결과를 저장하고 조회한다.
--   조회문은 DBeaver에서 그대로 실행할 수 있고, 콜론으로 시작하는 파라미터는 실행할 때 입력한다.
--=========================================================

-- name: select_card_product
-- 추출 항목이 연결될 카드 상품을 확인한다. card_extr_stg.card_id가 NOT NULL이라 상품이 먼저 있어야 한다.
SELECT card_id, product_cd, product_nm, issuer, card_kind_cd
FROM db_pipeline.card_product
WHERE card_id = :CARD_ID
;

-- name: select_terra_usage
-- 같은 문서의 Terra 호출 누적 사용량. 사용량이 없는 이력은 후속 호출 전 확인이 필요하다.
SELECT COALESCE(sum(c.call_input_token_cnt), 0) AS input_tokens,
       COALESCE(sum(c.call_output_token_cnt), 0) AS output_tokens,
       count(*) FILTER (WHERE c.call_input_token_cnt IS NULL OR c.call_output_token_cnt IS NULL) AS unknown_calls
FROM db_pipeline.card_ai_run r
JOIN db_pipeline.card_ai_call c ON c.card_ai_run_id = r.card_ai_run_id
WHERE r.run_target_card_doc_id = :CARD_DOC_ID AND r.run_model_nm = 'gpt-6.1-terra';

-- name: select_doc
-- 추출 대상 문서와 PDF 파일 정보를 조회한다.
SELECT card_doc_id, doc_cd, doc_file_nm, doc_sha256, doc_page_cnt, doc_status
FROM db_pipeline.card_doc
WHERE card_doc_id = :CARD_DOC_ID
;

-- name: select_ai_input_chunks
-- AI 입력 청크를 조회한다. 사용 중인 문서의 RAW·CLEANED 청크이고, 페이지가 OCR 검토 대기가 아니어야 한다.
SELECT c.card_doc_id, c.page_no, c.card_doc_chunk_id, c.chunk_seq, c.chunk_raw_txt, c.chunk_split_rule_ver,
       p.page_layer_cd, p.page_note
FROM db_pipeline.card_doc_chunk c
JOIN db_pipeline.card_doc d ON d.card_doc_id = c.card_doc_id
JOIN db_pipeline.card_doc_page p ON (p.card_doc_id, p.page_no) = (c.card_doc_id, c.page_no)
WHERE c.card_doc_id = :CARD_DOC_ID
  AND d.doc_status = 'ACTIVE'
  AND c.chunk_status IN ('RAW', 'CLEANED')
  AND COALESCE(left(p.page_note, 11), '') <> 'OCR_REVIEW '
ORDER BY c.chunk_seq
;

-- name: select_blocked_pages
-- 내용이 있지만 AI 입력에서 제외된 페이지를 조회한다.
SELECT DISTINCT c.page_no
FROM db_pipeline.card_doc_chunk c
JOIN db_pipeline.card_doc_page p ON (p.card_doc_id, p.page_no) = (c.card_doc_id, c.page_no)
WHERE c.card_doc_id = :CARD_DOC_ID
  AND (c.chunk_status NOT IN ('RAW', 'CLEANED') OR COALESCE(left(p.page_note, 11), '') = 'OCR_REVIEW ')
ORDER BY c.page_no
;

-- name: insert_run
-- AI 실행을 등록한다. card_ai_run_id는 기본값 fn_get_biz_id가 발급한다.
INSERT INTO db_pipeline.card_ai_run (
    run_stage_cd,
    run_call_mthd_cd,
    run_model_nm,
    run_prompt_ver,
    run_prompt_txt,
    run_param,
    run_target_card_doc_id,
    create_user_id,
    update_user_id
) VALUES (
    'EXTRACT',
    'PYTHON_RELAY',
    :RUN_MODEL_NM,
    :RUN_PROMPT_VER,
    :RUN_PROMPT_TXT,
    :RUN_PARAM,
    :RUN_TARGET_CARD_DOC_ID,
    :USER_ID,
    :USER_ID
)
RETURNING card_ai_run_id;

-- name: finish_run!
-- 실행 상태와 종료 일시를 기록한다.
UPDATE db_pipeline.card_ai_run
SET run_status = :RUN_STATUS,
    run_end_date = now(),
    run_note = :RUN_NOTE,
    update_date = now(),
    update_user_id = :USER_ID
WHERE card_ai_run_id = :CARD_AI_RUN_ID
;

-- name: insert_call!
-- LLM 호출 1건을 기록한다. 비용이 든 응답을 잃지 않도록 추출 항목 저장과 별도로 먼저 커밋한다.
INSERT INTO db_pipeline.card_ai_call (
    card_ai_run_id,
    card_doc_id,
    page_no,
    card_doc_chunk_id,
    call_seq,
    call_input_sha256,
    call_status,
    call_resp_raw,
    call_resp_json,
    call_error_msg,
    call_input_token_cnt,
    call_output_token_cnt,
    call_latency_ms,
    create_user_id,
    update_user_id
) VALUES (
    :CARD_AI_RUN_ID,
    :CARD_DOC_ID,
    :PAGE_NO,
    :CARD_DOC_CHUNK_ID,
    :CALL_SEQ,
    :CALL_INPUT_SHA256,
    :CALL_STATUS,
    :CALL_RESP_RAW,
    :CALL_RESP_JSON,
    :CALL_ERROR_MSG,
    :CALL_INPUT_TOKEN_CNT,
    :CALL_OUTPUT_TOKEN_CNT,
    :CALL_LATENCY_MS,
    :USER_ID,
    :USER_ID
);

-- name: insert_stg
-- 페이지별 추출 항목을 등록한다. 정제본은 문서 단위 통합 뒤에 채운다.
INSERT INTO db_pipeline.card_extr_stg (
    card_ai_run_id,
    card_doc_id,
    page_no,
    card_doc_chunk_id,
    call_seq,
    stg_item_seq,
    card_id,
    stg_kind_cd,
    stg_raw_item,
    stg_evidence_txt,
    stg_evidence_start_pos,
    stg_evidence_end_pos,
    create_user_id,
    update_user_id
) VALUES (
    :CARD_AI_RUN_ID,
    :CARD_DOC_ID,
    :PAGE_NO,
    :CARD_DOC_CHUNK_ID,
    :CALL_SEQ,
    :STG_ITEM_SEQ,
    :CARD_ID,
    :STG_KIND_CD,
    :STG_RAW_ITEM,
    :STG_EVIDENCE_TXT,
    :STG_EVIDENCE_START_POS,
    :STG_EVIDENCE_END_POS,
    :USER_ID,
    :USER_ID
)
RETURNING card_extr_stg_id;

-- name: insert_evidence!
-- 원문 근거 1건을 승인 대기로 등록한다. 찾지 못한 인용은 위치 없이 남긴다.
INSERT INTO db_pipeline.card_source_evidence (
    card_doc_id,
    page_no,
    card_doc_chunk_id,
    card_extr_stg_id,
    quote_txt,
    start_pos,
    end_pos,
    approval_status_cd
) VALUES (
    :CARD_DOC_ID,
    :PAGE_NO,
    :CARD_DOC_CHUNK_ID,
    :CARD_EXTR_STG_ID,
    :QUOTE_TXT,
    :START_POS,
    :END_POS,
    'PENDING'
);

-- name: update_stg_merge!
-- 문서 단위 통합 결과를 항목에 기록한다. stg_raw_item은 바꾸지 않는다.
UPDATE db_pipeline.card_extr_stg
SET stg_normalized_item = :STG_NORMALIZED_ITEM,
    stg_parent_card_extr_stg_id = :STG_PARENT_CARD_EXTR_STG_ID,
    stg_sql_check_cd = :STG_SQL_CHECK_CD,
    update_date = now(),
    update_user_id = :USER_ID
WHERE card_extr_stg_id = :CARD_EXTR_STG_ID
;

-- name: select_run_calls
-- 실행의 호출 이력과 토큰을 조회한다.
SELECT card_ai_run_id, page_no, card_doc_chunk_id, call_seq, call_status, call_error_msg,
       call_input_token_cnt, call_output_token_cnt, call_latency_ms
FROM db_pipeline.card_ai_call
WHERE card_ai_run_id = :CARD_AI_RUN_ID
ORDER BY page_no, call_seq
;

-- name: select_review_queue
-- 실행의 항목을 검증 결과별로 집계한다.
SELECT stg_kind_cd, stg_sql_check_cd, stg_status, COUNT(*) AS item_cnt
FROM db_pipeline.card_extr_stg
WHERE card_ai_run_id = :CARD_AI_RUN_ID
GROUP BY stg_kind_cd, stg_sql_check_cd, stg_status
ORDER BY stg_kind_cd, stg_sql_check_cd
;

-- name: select_merged_benefits
-- 문서 단위 통합 혜택과 검증 상태를 조회한다.
SELECT s.card_extr_stg_id, s.page_no, s.stg_status, s.stg_sql_check_cd,
       s.stg_normalized_item->>'bnft_cd' AS bnft_cd,
       s.stg_normalized_item->>'bnft_nm' AS bnft_nm,
       s.stg_normalized_item->'merge'->'source_pages' AS source_pages,
       s.stg_normalized_item->'merge'->'conflicts' AS conflicts,
       s.stg_normalized_item->'checks'->>'value_check_cd' AS value_check_cd,
       s.stg_normalized_item->'checks'->>'link_check_cd' AS link_check_cd
FROM db_pipeline.card_extr_stg s
WHERE s.card_ai_run_id = :CARD_AI_RUN_ID
  AND s.stg_kind_cd = 'BENEFIT'
  AND s.stg_normalized_item IS NOT NULL
ORDER BY s.page_no, s.stg_item_seq
;

-- name: select_merged_rules
-- 통합 혜택의 계산 규칙을 컬럼으로 조회한다.
SELECT s.page_no, s.stg_sql_check_cd,
       s.stg_normalized_item->>'bnft_nm' AS bnft_nm,
       r.value->>'rule_key' AS rule_key,
       r.value->>'calc_method_cd' AS calc_method_cd,
       (r.value->>'value_num')::numeric AS value_num,
       r.value->>'value_unit_cd' AS value_unit_cd,
       r.value->>'payout_unit_cd' AS payout_unit_cd,
       r.value->>'predicate_state_cd' AS predicate_state_cd
FROM db_pipeline.card_extr_stg s
CROSS JOIN LATERAL jsonb_array_elements(s.stg_normalized_item->'rule_list') AS r(value)
WHERE s.card_ai_run_id = :CARD_AI_RUN_ID
  AND s.stg_kind_cd = 'BENEFIT'
ORDER BY s.page_no, s.stg_item_seq
;

-- name: select_merged_limits
-- 통합 혜택의 한도를 컬럼으로 조회한다.
SELECT s.page_no,
       s.stg_normalized_item->>'bnft_nm' AS bnft_nm,
       l.value->>'pool_key' AS pool_key,
       l.value->>'pool_scope_cd' AS pool_scope_cd,
       l.value->>'period_cd' AS period_cd,
       l.value->>'cap_unit_cd' AS cap_unit_cd,
       (l.value->>'limit_num')::numeric AS limit_num
FROM db_pipeline.card_extr_stg s
CROSS JOIN LATERAL jsonb_array_elements(s.stg_normalized_item->'limit_list') AS l(value)
WHERE s.card_ai_run_id = :CARD_AI_RUN_ID
  AND s.stg_kind_cd = 'BENEFIT'
ORDER BY s.page_no, s.stg_item_seq
;

-- name: select_merged_conditions
-- 문서 단위 조건과 연결된 혜택을 조회한다. 조건과 혜택의 페이지가 달라도 연결된다.
SELECT c.card_extr_stg_id, c.page_no AS cond_page, b.page_no AS benefit_page,
       b.stg_normalized_item->>'bnft_nm' AS bnft_nm,
       c.stg_normalized_item->>'scope_cd' AS scope_cd,
       c.stg_normalized_item->'applies_to_item_keys' AS applies_to_item_keys,
       c.stg_raw_item->>'cond_raw_txt' AS cond_raw_txt,
       c.stg_sql_check_cd
FROM db_pipeline.card_extr_stg c
LEFT JOIN db_pipeline.card_extr_stg b ON b.card_extr_stg_id = c.stg_parent_card_extr_stg_id
WHERE c.card_ai_run_id = :CARD_AI_RUN_ID
  AND c.stg_kind_cd = 'CONDITION'
ORDER BY c.page_no, c.stg_item_seq
;

-- name: select_item_evidence
-- 항목별 근거를 페이지·청크·위치와 함께 조회하고 원문과 대조한다.
SELECT s.card_extr_stg_id, s.stg_kind_cd, e.evidence_id, e.page_no, e.card_doc_chunk_id,
       e.quote_txt, e.start_pos, e.end_pos, e.approval_status_cd,
       substr(c.chunk_raw_txt, e.start_pos, e.end_pos - e.start_pos + 1) = e.quote_txt AS exact_match
FROM db_pipeline.card_extr_stg s
JOIN db_pipeline.card_source_evidence e ON e.card_extr_stg_id = s.card_extr_stg_id
JOIN db_pipeline.card_doc_chunk c
  ON (c.card_doc_id, c.page_no, c.card_doc_chunk_id) = (e.card_doc_id, e.page_no, e.card_doc_chunk_id)
WHERE s.card_ai_run_id = :CARD_AI_RUN_ID
ORDER BY s.page_no, s.stg_item_seq, e.evidence_id
;

-- name: select_contract_check
-- 정제본을 V6 JSONB 계약 함수로 검사한다. 키는 승인 시 실제 ID로 바뀌므로 자리표시 값을 그대로 검사한다.
SELECT s.card_extr_stg_id, s.stg_kind_cd,
       CASE WHEN s.stg_kind_cd = 'BENEFIT'
            THEN db_pipeline.fn_valid_rule_list(s.stg_normalized_item->'rule_list', 'LOCAL') END AS rule_ok,
       CASE WHEN s.stg_kind_cd = 'BENEFIT'
            THEN db_pipeline.fn_valid_cond_expr(NULLIF(s.stg_normalized_item->'bnft_cond_expr', 'null'::jsonb))
            ELSE db_pipeline.fn_valid_cond_expr(NULLIF(s.stg_normalized_item->'cond_expr', 'null'::jsonb)) END AS cond_ok,
       CASE WHEN s.stg_kind_cd = 'BENEFIT'
            THEN db_pipeline.fn_valid_relation_list(s.stg_normalized_item->'relation_list', '-') END AS relation_ok
FROM db_pipeline.card_extr_stg s
WHERE s.card_ai_run_id = :CARD_AI_RUN_ID
  AND s.stg_normalized_item IS NOT NULL
ORDER BY s.page_no, s.stg_item_seq
;

-- name: select_run_compare
-- 두 실행의 혜택 정제본을 비교한다. 비교 키는 Python이 혜택명으로 만든 bnft_cd이고, 검증 정보는 비교하지 않는다.
WITH item AS (
    SELECT card_ai_run_id, stg_normalized_item->>'bnft_cd' AS bnft_cd,
           stg_normalized_item->'rule_list' AS rule_list,
           stg_normalized_item->'limit_list' AS limit_list,
           stg_normalized_item->'bnft_cond_expr' AS cond_expr
    FROM db_pipeline.card_extr_stg
    WHERE stg_kind_cd = 'BENEFIT'
      AND stg_normalized_item IS NOT NULL
)
SELECT COALESCE(o.bnft_cd, n.bnft_cd) AS bnft_cd,
       CASE WHEN o.bnft_cd IS NULL THEN 'ADDED'
            WHEN n.bnft_cd IS NULL THEN 'REMOVED'
            WHEN (o.rule_list, o.limit_list, o.cond_expr) IS DISTINCT FROM (n.rule_list, n.limit_list, n.cond_expr)
            THEN 'CHANGED'
            ELSE 'SAME' END AS diff_cd
FROM (SELECT * FROM item WHERE card_ai_run_id = :OLD_RUN_ID) o
FULL JOIN (SELECT * FROM item WHERE card_ai_run_id = :NEW_RUN_ID) n USING (bnft_cd)
ORDER BY 1
;
