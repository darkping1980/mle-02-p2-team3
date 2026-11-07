-- file_pipeline에서 참고하는 카드 문서·AI 추출·혜택 스키마.
-- 현재 Python file_pipeline은 JSON 파일 기반이며 이 DDL을 자동 실행하지 않는다.
-- 별도 PostgreSQL schema에 적용한다. vector 확장이 미리 설치되어 있어야 한다.
-- 참고용 명세. 실행하지 말 것. graph/schema.sql(pf_ 접두사, public)과 별개이며 팀 DB에 적용하기 전에 스키마 이름·접두사·RLS·pgvector 합의 필요. 비교는 docs/작업이력/2026-11-03-스키마비교-참고명세와pf-laptop.md 참조.
CREATE SCHEMA IF NOT EXISTS file_pipeline;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE file_pipeline.card_doc (
  card_doc_id varchar PRIMARY KEY, doc_cd varchar UNIQUE NOT NULL, doc_family_cd varchar,
  doc_type_cd varchar NOT NULL, doc_title text NOT NULL, doc_source_url text,
  doc_file_nm text NOT NULL, doc_file_size int8, doc_sha256 varchar UNIQUE NOT NULL,
  doc_page_cnt int2, doc_review_no text, doc_review_date date, doc_release_date date,
  doc_collect_date timestamptz NOT NULL, doc_version_no int2 NOT NULL,
  doc_status varchar NOT NULL, doc_note text,
  create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL
);

CREATE TABLE file_pipeline.card_doc_page (
  card_doc_id varchar NOT NULL, page_no int2 NOT NULL, page_raw_txt text NOT NULL,
  page_char_cnt int4 NOT NULL, page_txt_sha256 varchar NOT NULL, page_layer_cd varchar NOT NULL,
  page_extractor_nm varchar NOT NULL, page_extractor_ver varchar, page_note text,
  create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL,
  PRIMARY KEY (card_doc_id, page_no)
);

CREATE TABLE file_pipeline.card_doc_chunk (
  card_doc_id varchar NOT NULL, page_no int2 NOT NULL, card_doc_chunk_id varchar NOT NULL UNIQUE,
  chunk_seq int4 NOT NULL, chunk_section_nm text, chunk_type_cd varchar NOT NULL,
  chunk_start_pos int4 NOT NULL, chunk_end_pos int4 NOT NULL, chunk_raw_txt text NOT NULL,
  chunk_clean_txt text, chunk_status varchar NOT NULL, chunk_split_rule_ver varchar NOT NULL,
  chunk_clean_rule_ver varchar, create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL,
  PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id)
);

CREATE TABLE file_pipeline.card_ai_run (
  card_ai_run_id varchar PRIMARY KEY, run_stage_cd varchar NOT NULL, run_call_mthd_cd varchar NOT NULL,
  run_model_nm varchar NOT NULL, run_prompt_ver varchar NOT NULL, run_prompt_txt text NOT NULL,
  run_param jsonb, run_target_card_doc_id varchar, run_status varchar NOT NULL,
  run_start_date timestamptz NOT NULL, run_end_date timestamptz, run_note text,
  create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL
);

CREATE TABLE file_pipeline.card_ai_call (
  card_ai_run_id varchar NOT NULL, card_doc_id varchar NOT NULL, page_no int2 NOT NULL,
  card_doc_chunk_id varchar NOT NULL, call_seq int2 NOT NULL, call_input_sha256 varchar NOT NULL,
  call_status varchar NOT NULL, call_resp_raw text, call_resp_json jsonb, call_error_msg text,
  call_input_token_cnt int4, call_output_token_cnt int4, call_latency_ms int4,
  call_req_date timestamptz NOT NULL, create_date timestamptz NOT NULL,
  create_user_id varchar NOT NULL, update_date timestamptz NOT NULL, update_user_id varchar NOT NULL,
  PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq)
);

CREATE TABLE file_pipeline.card_product (
  card_id int8 PRIMARY KEY, product_cd varchar UNIQUE NOT NULL, product_nm text NOT NULL,
  issuer varchar NOT NULL, card_kind_cd varchar NOT NULL, product_status_cd varchar NOT NULL,
  launched_on date, discontinued_on date, brand_opt_list jsonb NOT NULL,
  create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL,
  card_cond_expr jsonb, card_cond_status_cd varchar NOT NULL
);

CREATE TABLE file_pipeline.card_product_doc (
  card_id int8 NOT NULL, card_doc_id varchar NOT NULL, doc_role_cd varchar NOT NULL,
  brand_opt_cds text[], approval_status_cd varchar NOT NULL, applicability_basis_txt text NOT NULL,
  approval_note text, create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL,
  PRIMARY KEY (card_id, card_doc_id)
);

CREATE TABLE file_pipeline.card_bnft (
  card_id int8 NOT NULL, card_bnft_id varchar NOT NULL, bnft_cd varchar NOT NULL,
  bnft_nm text NOT NULL, bnft_type_cd varchar NOT NULL, bnft_origin_cd varchar NOT NULL,
  bnft_scope_cd varchar NOT NULL, bnft_brand_opt_cds text[], bnft_cond_expr jsonb,
  rule_select_cd varchar, rule_list jsonb NOT NULL, relation_list jsonb NOT NULL,
  verification_status_cd varchar NOT NULL, bnft_valid_from date, bnft_valid_to_excl date,
  bnft_rule_txt text, bnft_limit_txt text, bnft_search_txt text, bnft_embedding vector,
  PRIMARY KEY (card_id, card_bnft_id)
);

CREATE TABLE file_pipeline.card_common (
  card_common_id int8 PRIMARY KEY, common_cd varchar UNIQUE NOT NULL, common_nm text NOT NULL,
  brand_cd varchar, service_grade_cd varchar, common_note text,
  create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL
);

CREATE TABLE file_pipeline.card_common_bnft (
  card_common_id int8 NOT NULL, card_common_bnft_id varchar NOT NULL, bnft_cd varchar NOT NULL,
  bnft_nm text NOT NULL, bnft_type_cd varchar, service_type_cd varchar,
  bnft_rule_txt text, bnft_limit_txt text, bnft_valid_from date, bnft_valid_to_excl date,
  create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL,
  bnft_search_txt text, bnft_embedding vector,
  PRIMARY KEY (card_common_id, card_common_bnft_id)
);

CREATE TABLE file_pipeline.card_common_bnft_apply (
  card_common_id int8 NOT NULL, card_common_bnft_id varchar NOT NULL, card_id int8 NOT NULL,
  PRIMARY KEY (card_common_id, card_common_bnft_id, card_id)
);

CREATE TABLE file_pipeline.card_common_doc (
  card_common_id int8 NOT NULL, card_doc_id varchar NOT NULL,
  PRIMARY KEY (card_common_id, card_doc_id)
);

CREATE TABLE file_pipeline.card_evidence_link (
  card_doc_id varchar NOT NULL, page_no int2 NOT NULL, card_doc_chunk_id varchar NOT NULL,
  evidence_id varchar NOT NULL, card_id int8 NOT NULL, evidence_link_id varchar NOT NULL,
  card_bnft_id varchar, ev_subject_cd varchar NOT NULL, rule_key varchar, relation_key varchar,
  ev_item_cd varchar NOT NULL, ev_item_key varchar NOT NULL,
  PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id)
);

CREATE TABLE file_pipeline.card_excl_item (
  card_excl_item_id varchar PRIMARY KEY, issuer text NOT NULL, excl_item_nm text NOT NULL,
  excl_concept_cd varchar, excl_item_desc text, excl_alias_nms text[] NOT NULL,
  create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL
);

CREATE TABLE file_pipeline.card_extr_stg (
  card_ai_run_id varchar NOT NULL, card_doc_id varchar NOT NULL, page_no int2 NOT NULL,
  card_doc_chunk_id varchar NOT NULL, call_seq int2 NOT NULL, card_extr_stg_id varchar NOT NULL UNIQUE,
  stg_item_seq int2 NOT NULL, card_id int8, stg_kind_cd varchar NOT NULL,
  stg_parent_card_extr_stg_id varchar, stg_raw_item jsonb NOT NULL,
  stg_normalized_item jsonb, stg_evidence_txt text NOT NULL,
  stg_evidence_start_pos int4, stg_evidence_end_pos int4, card_excl_item_id varchar,
  stg_sql_check_cd varchar, stg_ai_vrfy_cd varchar, stg_ai_vrfy_card_ai_run_id varchar,
  stg_status varchar NOT NULL, stg_review_note text, stg_approved_date timestamptz,
  stg_approved_user_id varchar, create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL,
  PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq)
);

CREATE TABLE file_pipeline.card_source_evidence (
  card_doc_id varchar NOT NULL, page_no int2 NOT NULL, card_doc_chunk_id varchar NOT NULL,
  evidence_id varchar NOT NULL UNIQUE, card_extr_stg_id varchar, quote_txt text NOT NULL,
  start_pos int4, end_pos int4, approval_status_cd varchar NOT NULL,
  PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id)
);

CREATE TABLE file_pipeline.common_code_grp (
  common_code_grp_id varchar PRIMARY KEY, common_code_grp_nm text NOT NULL,
  create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL,
  common_code_grp_desc text
);

CREATE TABLE file_pipeline.common_cd (
  common_code_grp_id varchar NOT NULL, common_cd varchar NOT NULL, common_cd_nm text NOT NULL,
  create_date timestamptz NOT NULL, create_user_id varchar NOT NULL,
  update_date timestamptz NOT NULL, update_user_id varchar NOT NULL, common_cd_desc text,
  PRIMARY KEY (common_code_grp_id, common_cd)
);
