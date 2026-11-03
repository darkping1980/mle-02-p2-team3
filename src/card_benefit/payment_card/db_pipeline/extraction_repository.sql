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
SELECT card_doc_id, doc_cd, doc_type_cd, doc_file_nm, doc_sha256, doc_page_cnt, doc_status
FROM db_pipeline.card_doc
WHERE card_doc_id = :CARD_DOC_ID
;

-- name: select_ai_input_chunks
-- AI 입력 청크를 조회한다. 사용 중인 문서의 RAW·CLEANED 청크이고, 페이지가 OCR 검토 대기가 아니어야 한다.
SELECT c.card_doc_id, c.page_no, c.card_doc_chunk_id, c.chunk_seq, c.chunk_raw_txt, c.chunk_split_rule_ver, c.chunk_type_cd,
       p.page_layer_cd, p.page_note, p.page_txt_sha256, p.page_extractor_nm, p.page_extractor_ver,
       c.chunk_start_pos, c.chunk_end_pos, c.chunk_status
FROM db_pipeline.card_doc_chunk c
JOIN db_pipeline.card_doc d ON d.card_doc_id = c.card_doc_id
JOIN db_pipeline.card_doc_page p ON (p.card_doc_id, p.page_no) = (c.card_doc_id, c.page_no)
WHERE c.card_doc_id = :CARD_DOC_ID
  AND d.doc_status = 'ACTIVE'
  AND c.chunk_status IN ('RAW', 'CLEANED')
  AND COALESCE(left(p.page_note, 11), '') <> 'OCR_REVIEW '
ORDER BY c.chunk_seq
;

-- name: select_reusable_runs
SELECT card_ai_run_id FROM db_pipeline.card_ai_run
WHERE run_target_card_doc_id = :CARD_DOC_ID AND run_stage_cd = 'EXTRACT'
  AND run_status = 'SUCCEEDED' AND run_model_nm = :MODEL
  AND run_prompt_ver = :PROMPT_VER AND run_param->>'reuse_fingerprint' = :FINGERPRINT
ORDER BY run_start_date DESC;

-- name: select_reuse_items
SELECT s.card_doc_chunk_id, s.call_seq, s.card_id, s.stg_kind_cd, s.stg_item_seq, s.stg_raw_item,
       s.stg_sql_check_cd, s.stg_parent_card_extr_stg_id,
       (SELECT COALESCE(jsonb_agg(e.quote_txt ORDER BY e.quote_txt), '[]'::jsonb) FROM db_pipeline.card_source_evidence e
        WHERE e.card_extr_stg_id = s.card_extr_stg_id AND e.card_doc_id = s.card_doc_id
          AND e.page_no = s.page_no AND e.card_doc_chunk_id = s.card_doc_chunk_id) AS evidence_quotes
FROM db_pipeline.card_extr_stg s WHERE s.card_ai_run_id = :CARD_AI_RUN_ID;

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
-- 페이지별 추출 항목을 등록한다. 통합 연결·검증 코드는 문서 단위 통합 뒤에 채운다.
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
-- 문서 단위 통합 결과(대표 항목 연결·검증 코드)를 기록한다. stg_raw_item은 바꾸지 않는다.
-- 등록용 정제본은 저장하지 않고 등록 시 stg_raw_item에서 다시 만든다(normalize_stored_run).
UPDATE db_pipeline.card_extr_stg
SET stg_parent_card_extr_stg_id = :STG_PARENT_CARD_EXTR_STG_ID,
    stg_sql_check_cd = :STG_SQL_CHECK_CD,
    update_date = now(),
    update_user_id = :USER_ID
WHERE card_extr_stg_id = :CARD_EXTR_STG_ID
;

-- name: select_run_calls
-- 실행의 호출 이력과 토큰을 조회한다.
SELECT card_ai_run_id, page_no, card_doc_chunk_id, call_seq, call_status, call_error_msg, call_resp_json,
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
-- 문서 단위 대표 혜택과 검증 상태를 조회한다. 대표 항목은 검증 코드가 있고 같은 종류의 부모가 없는 행이다.
SELECT s.card_extr_stg_id, s.page_no, s.stg_status, s.stg_sql_check_cd,
       s.stg_raw_item->>'bnft_nm' AS bnft_nm,
       (SELECT count(*) FROM db_pipeline.card_extr_stg d
        WHERE d.stg_parent_card_extr_stg_id = s.card_extr_stg_id AND d.stg_kind_cd = 'BENEFIT') + 1 AS source_cnt
FROM db_pipeline.card_extr_stg s
LEFT JOIN db_pipeline.card_extr_stg p ON p.card_extr_stg_id = s.stg_parent_card_extr_stg_id
WHERE s.card_ai_run_id = :CARD_AI_RUN_ID
  AND s.stg_kind_cd = 'BENEFIT'
  AND s.stg_sql_check_cd IS NOT NULL
  AND p.card_extr_stg_id IS NULL
ORDER BY s.page_no, s.stg_item_seq
;

-- name: select_merged_rules
-- 대표 혜택 원문 항목의 규칙 값을 컬럼으로 조회한다(통합 전 페이지 원문 기준).
SELECT s.page_no, s.stg_sql_check_cd,
       s.stg_raw_item->>'bnft_nm' AS bnft_nm,
       r.value->>'rule_key' AS rule_key,
       (r.value->>'value_num')::numeric AS value_num,
       r.value->>'value_unit_cd' AS value_unit_cd,
       r.value->>'value_raw_txt' AS value_raw_txt
FROM db_pipeline.card_extr_stg s
CROSS JOIN LATERAL jsonb_array_elements(COALESCE(s.stg_raw_item->'rules', '[]'::jsonb)) AS r(value)
WHERE s.card_ai_run_id = :CARD_AI_RUN_ID
  AND s.stg_kind_cd = 'BENEFIT'
  AND s.stg_sql_check_cd IS NOT NULL
  AND s.stg_parent_card_extr_stg_id IS NULL
ORDER BY s.page_no, s.stg_item_seq
;

-- name: select_merged_conditions
-- 문서 단위 조건과 연결된 혜택을 조회한다. 조건과 혜택의 페이지가 달라도 연결된다.
SELECT c.card_extr_stg_id, c.page_no AS cond_page, b.page_no AS benefit_page,
       b.stg_raw_item->>'bnft_nm' AS bnft_nm,
       c.stg_raw_item->>'scope' AS scope_cd,
       c.stg_raw_item->>'cond_raw_txt' AS cond_raw_txt,
       c.stg_sql_check_cd
FROM db_pipeline.card_extr_stg c
LEFT JOIN db_pipeline.card_extr_stg b
  ON b.card_extr_stg_id = c.stg_parent_card_extr_stg_id AND b.stg_kind_cd = 'BENEFIT'
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
