-- PostgreSQL db_pipeline schema-only snapshot generated from live system catalogs.
-- Extraction date (UTC): 2026-11-07T02:15:36.698961+00:00
-- Source database: postgres
-- Server version: PostgreSQL 17.11 on aarch64-unknown-linux-gnu, compiled by gcc (GCC) 15.2.0, 64-bit
-- Session read_only: on
-- pg_dump was not installed/available in the local environment; this DDL was assembled from live PostgreSQL catalogs.
-- No table rows or sequence current values are included.
-- Includes table columns/constraints, standalone indexes, non-identity sequences, routines, views, and sequence ownership.
-- Limitations versus pg_dump: no owner/ACL, COMMENT, extension installation, default privileges, or server-level objects.
-- Existing extensions required by types/functions: pg_stat_statements 1.11 in extensions, pgcrypto 1.3 in extensions, plpgsql 1.0 in pg_catalog, supabase_vault 0.3.1 in vault, uuid-ossp 1.1 in extensions, vector 0.8.2 in extensions

-- current_schema=public; search_path="\$user", public, extensions
CREATE SCHEMA IF NOT EXISTS "db_pipeline";

CREATE SEQUENCE "db_pipeline"."seq_card_ai_run" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 999999 START WITH 1 CACHE 1 CYCLE;

CREATE SEQUENCE "db_pipeline"."seq_card_bnft" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 999999 START WITH 1 CACHE 1 CYCLE;

CREATE SEQUENCE "db_pipeline"."seq_card_common" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1 NO CYCLE;

CREATE SEQUENCE "db_pipeline"."seq_card_common_bnft" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 999999 START WITH 1 CACHE 1 NO CYCLE;

CREATE SEQUENCE "db_pipeline"."seq_card_doc" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 999999 START WITH 1 CACHE 1 CYCLE;

CREATE SEQUENCE "db_pipeline"."seq_card_doc_chunk" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 999999 START WITH 1 CACHE 1 CYCLE;

CREATE SEQUENCE "db_pipeline"."seq_card_evidence_link" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 999999 START WITH 1 CACHE 1 CYCLE;

CREATE SEQUENCE "db_pipeline"."seq_card_extr_stg" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 999999 START WITH 1 CACHE 1 CYCLE;

CREATE SEQUENCE "db_pipeline"."seq_card_product" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START WITH 1 CACHE 1 NO CYCLE;

CREATE SEQUENCE "db_pipeline"."seq_card_product_item" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 999999 START WITH 1 CACHE 1 CYCLE;

CREATE SEQUENCE "db_pipeline"."seq_card_source_evidence" AS bigint INCREMENT BY 1 MINVALUE 1 MAXVALUE 999999 START WITH 1 CACHE 1 CYCLE;

CREATE OR REPLACE FUNCTION db_pipeline.fn_get_biz_id(p_tbl_nm text)
 RETURNS character varying
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
    v_seq regclass;
BEGIN
    IF p_tbl_nm IS NULL OR p_tbl_nm !~ '^[A-Za-z][A-Za-z0-9_]*$' THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = format('Invalid db_pipeline table name for business ID: %s', coalesce(p_tbl_nm, '<NULL>'));
    END IF;

    v_seq := to_regclass('db_pipeline.seq_' || lower(p_tbl_nm));
    IF v_seq IS NULL OR NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS c
        WHERE c.oid = v_seq
          AND c.relkind = 'S'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42P01',
            MESSAGE = format('db_pipeline ID sequence does not exist: %s', 'db_pipeline.seq_' || lower(p_tbl_nm));
    END IF;

    RETURN to_char((clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date, 'YYYYMMDD')
        || '_' || lpad(nextval(v_seq)::text, 6, '0');
END;
$function$
;

CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_brand_opt_list(p_list jsonb)
 RETURNS boolean
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
    SELECT CASE
        WHEN jsonb_typeof(p_list) IS DISTINCT FROM 'array' THEN false
        ELSE coalesce((
            SELECT bool_and(
                       jsonb_typeof(t.value) = 'object'
                       AND coalesce(t.value->>'brand_opt_cd', '') ~ '^[A-Za-z0-9_.:-]{1,80}$'
                       AND coalesce(t.value->>'brand_opt_nm', '') <> ''
                       AND coalesce(t.value->>'brand_cd', '') <> ''
                       AND coalesce(t.value->>'service_grade_cd', '') <> ''
                       AND coalesce(t.value->>'service_type_cd', '') <> ''
                       AND coalesce(t.value->>'brand_opt_status_cd', '') <> '')
                   AND count(*) = count(DISTINCT t.value->>'brand_opt_cd')
            FROM jsonb_array_elements(p_list) AS t(value)), true)
    END
$function$
;

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
$function$
;

CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_item_data(p_type text, p_data jsonb)
 RETURNS boolean
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
    v_line jsonb;
    v_keys text[] := '{}';
    v_basic numeric; v_aff numeric; v_total numeric;
BEGIN
    IF p_data IS NULL OR jsonb_typeof(p_data) <> 'object' THEN
        RETURN false;
    END IF;
    IF p_type = 'BENEFIT' THEN
        RETURN NOT (p_data ? 'schema_ver') OR p_data->>'schema_ver' = 'BENEFIT_V1';
    END IF;
    IF p_type = 'ANNUAL_FEE' THEN
        IF p_data->>'schema_ver' IS DISTINCT FROM 'ANNUAL_FEE_V1'
           OR jsonb_typeof(p_data->'fee_lines') IS DISTINCT FROM 'array'
           OR jsonb_array_length(p_data->'fee_lines') = 0 THEN
            RETURN false;
        END IF;
        FOR v_line IN SELECT value FROM jsonb_array_elements(p_data->'fee_lines') LOOP
            IF jsonb_typeof(v_line) <> 'object'
               OR coalesce(v_line->>'line_key', '') = ''
               OR (v_line->>'line_key') = ANY (v_keys)
               OR coalesce(v_line->>'holder_type_cd', '') NOT IN ('PRINCIPAL', 'FAMILY') THEN
                RETURN false;
            END IF;
            v_keys := v_keys || (v_line->>'line_key');
            -- 금액은 없거나 0 이상 정수
            IF EXISTS (SELECT 1 FROM unnest(ARRAY['basic_fee_amt', 'affiliate_fee_amt', 'total_fee_amt']) AS f(k)
                       WHERE v_line ? f.k AND jsonb_typeof(v_line->f.k) <> 'null'
                         AND (jsonb_typeof(v_line->f.k) <> 'number' OR (v_line->>f.k)::numeric < 0
                              OR (v_line->>f.k)::numeric <> trunc((v_line->>f.k)::numeric))) THEN
                RETURN false;
            END IF;
            v_basic := (v_line->>'basic_fee_amt')::numeric;
            v_aff := (v_line->>'affiliate_fee_amt')::numeric;
            v_total := (v_line->>'total_fee_amt')::numeric;
            IF v_basic IS NOT NULL AND v_aff IS NOT NULL AND v_total IS NOT NULL AND v_basic + v_aff <> v_total THEN
                RETURN false;
            END IF;
            -- 브랜드 옵션: null(전 브랜드) 또는 비어 있지 않은 문자열 배열
            IF v_line ? 'brand_opt_cds' AND jsonb_typeof(v_line->'brand_opt_cds') <> 'null'
               AND (jsonb_typeof(v_line->'brand_opt_cds') <> 'array' OR jsonb_array_length(v_line->'brand_opt_cds') = 0
                    OR EXISTS (SELECT 1 FROM jsonb_array_elements(v_line->'brand_opt_cds') b WHERE jsonb_typeof(b) <> 'string')) THEN
                RETURN false;
            END IF;
        END LOOP;
        RETURN true;
    END IF;
    IF p_type = 'TERMS' THEN
        -- TERMS_V1(2026-11-05): 할인 제공 유의사항·제외 목록. 원문은 고치지 않고 구간마다 문서·쪽·청크·위치를 둔다.
        -- 원문이 그 위치의 chunk_raw_txt와 같은지는 CHECK가 다른 테이블을 볼 수 없어 등록 프로그램(terms_register.py)이 검사한다.
        IF p_data->>'schema_ver' IS DISTINCT FROM 'TERMS_V1'
           OR jsonb_typeof(p_data->'terms_kind_cd') IS DISTINCT FROM 'string' OR btrim(p_data->>'terms_kind_cd') = ''
           OR jsonb_typeof(p_data->'scope') IS DISTINCT FROM 'object'
           OR coalesce(p_data->'scope'->>'scope_cd', '') NOT IN ('ALL_BENEFITS', 'PERFORMANCE', 'NAMED_ITEMS')
           OR jsonb_typeof(p_data->'scope'->'item_ids') IS DISTINCT FROM 'array'
           OR jsonb_typeof(p_data->'source') IS DISTINCT FROM 'object'
           OR jsonb_typeof(p_data->'entries') IS DISTINCT FROM 'array'
           OR jsonb_typeof(p_data->'footnotes') IS DISTINCT FROM 'array' THEN
            RETURN false;
        END IF;
        -- 적용 대상: NAMED_ITEMS일 때만 비어 있지 않은 문자열 배열(중복 없음). 대상 항목의 존재는 등록 프로그램이 검사한다.
        IF ((p_data->'scope'->>'scope_cd') = 'NAMED_ITEMS') <> (jsonb_array_length(p_data->'scope'->'item_ids') > 0)
           OR EXISTS (SELECT 1 FROM jsonb_array_elements(p_data->'scope'->'item_ids') x
                      WHERE jsonb_typeof(x) <> 'string' OR btrim(x #>> '{}') = '')
           OR (SELECT count(*) <> count(DISTINCT x #>> '{}') FROM jsonb_array_elements(p_data->'scope'->'item_ids') x) THEN
            RETURN false;
        END IF;
        -- 원문 구간(source 1개, entries, footnotes): 각 구간이 자기 위치를 가진다. 서로 떨어진 구간을 한 문자열로 합치지 않는다.
        FOR v_line IN SELECT p_data->'source'
                      UNION ALL SELECT value FROM jsonb_array_elements(p_data->'entries')
                      UNION ALL SELECT value FROM jsonb_array_elements(p_data->'footnotes') LOOP
            IF jsonb_typeof(v_line) <> 'object'
               OR jsonb_typeof(v_line->'txt') IS DISTINCT FROM 'string' OR (v_line->>'txt') = ''
               OR coalesce(v_line->>'card_doc_id', '') = '' OR coalesce(v_line->>'card_doc_chunk_id', '') = ''
               OR EXISTS (SELECT 1 FROM unnest(ARRAY['page_no', 'start_pos', 'end_pos']) AS f(k)
                          WHERE jsonb_typeof(v_line->f.k) IS DISTINCT FROM 'number'
                             OR (v_line->>f.k)::numeric < 1 OR (v_line->>f.k)::numeric <> trunc((v_line->>f.k)::numeric))
               OR (v_line->>'end_pos')::numeric - (v_line->>'start_pos')::numeric + 1 <> length(v_line->>'txt') THEN
                RETURN false;
            END IF;
        END LOOP;
        -- 키: entries의 entry_key, footnotes의 footnote_key(표기 marker 필수). 둘을 합쳐 중복 없음
        FOR v_line IN SELECT value FROM jsonb_array_elements(p_data->'entries') LOOP
            IF coalesce(v_line->>'entry_key', '') = '' OR (v_line->>'entry_key') = ANY (v_keys) THEN
                RETURN false;
            END IF;
            v_keys := v_keys || (v_line->>'entry_key');
        END LOOP;
        FOR v_line IN SELECT value FROM jsonb_array_elements(p_data->'footnotes') LOOP
            IF coalesce(v_line->>'footnote_key', '') = '' OR (v_line->>'footnote_key') = ANY (v_keys)
               OR jsonb_typeof(v_line->'marker') IS DISTINCT FROM 'string' OR (v_line->>'marker') = '' THEN
                RETURN false;
            END IF;
            v_keys := v_keys || (v_line->>'footnote_key');
        END LOOP;
        RETURN true;
    END IF;
    -- 2026-11-05: 그 밖의 유형은 유형값 때문에 막지 않는다. 맨 위의 기본 구조(JSON 객체) 검사만 적용한다.
    RETURN true;
END;
$function$
;

CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_relation_list(p_list jsonb, p_self_bnft_id text)
 RETURNS boolean
 LANGUAGE plpgsql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
DECLARE
    v_rel jsonb;
    v_keys text[] := '{}';
    v_pairs text[] := '{}';
    v_pair text;
BEGIN
    IF jsonb_typeof(p_list) IS DISTINCT FROM 'array' THEN
        RETURN false;
    END IF;
    FOR v_rel IN SELECT value FROM jsonb_array_elements(p_list) LOOP
        IF jsonb_typeof(v_rel) <> 'object'
           OR coalesce(v_rel->>'relation_key', '') !~ '^[A-Za-z0-9_.:-]{1,40}$'
           OR v_rel->>'relation_key' = ANY (v_keys)
           OR coalesce(v_rel->>'to_bnft_id', '') = ''
           OR v_rel->>'to_bnft_id' = p_self_bnft_id
           OR coalesce(v_rel->>'rel_type_cd', '') = ''
           OR coalesce(jsonb_typeof(v_rel->'rel_priority'), 'null') NOT IN ('number','null')
           OR v_rel ? 'trigger_pool_id' THEN
            RETURN false;
        END IF;
        v_pair := (v_rel->>'to_bnft_id') || '|' || (v_rel->>'rel_type_cd');
        IF v_pair = ANY (v_pairs) THEN
            RETURN false;
        END IF;
        v_pairs := v_pairs || v_pair;
        v_keys := v_keys || (v_rel->>'relation_key');
    END LOOP;
    RETURN true;
END;
$function$
;

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
$function$
;

CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_target_list(p_list jsonb)
 RETURNS boolean
 LANGUAGE sql
 IMMUTABLE
 SET search_path TO 'pg_catalog'
AS $function$
    SELECT CASE
        WHEN jsonb_typeof(p_list) IS DISTINCT FROM 'array' THEN false
        ELSE coalesce((
            SELECT bool_and(
                       jsonb_typeof(t.value) = 'object'
                       AND coalesce(t.value->>'target_type_cd', '') <> ''
                       AND coalesce(t.value->>'target_key', '') ~ '^.{1,100}$'
                       AND coalesce(t.value->>'target_nm', '') <> '')
                   AND count(*) = count(DISTINCT (t.value->>'target_type_cd', t.value->>'target_key'))
            FROM jsonb_array_elements(p_list) AS t(value)), true)
    END
$function$
;

CREATE TABLE "db_pipeline"."app_log" (
  "app_log_id" bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  "session_id" uuid NOT NULL,
  "request_id" uuid NOT NULL,
  "client_ip" inet,
  "request_text" text NOT NULL,
  "execution_log" text DEFAULT ''::text NOT NULL,
  "response_text" text DEFAULT ''::text NOT NULL,
  "error_text" text,
  "created_at" timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
  "detail_text" text,
  "pdf_evidence_text" text,
  "neo4j_summary" text,
  "pdf_evidence_summary" text,
  CONSTRAINT "app_log_pkey" PRIMARY KEY (app_log_id),
  CONSTRAINT "app_log_session_request_uk" UNIQUE (session_id, request_id)
);

CREATE INDEX ix_app_log_request_created ON db_pipeline.app_log USING btree (request_id, created_at DESC);
CREATE INDEX ix_app_log_session_created ON db_pipeline.app_log USING btree (session_id, created_at DESC);

CREATE TABLE "db_pipeline"."app_log_event_archive" (
  "app_log_id" bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
  "session_id" uuid NOT NULL,
  "request_id" uuid NOT NULL,
  "client_ip" inet,
  "log_type" text NOT NULL,
  "log_message" text NOT NULL,
  "created_at" timestamp with time zone DEFAULT clock_timestamp() NOT NULL,
  CONSTRAINT "app_log_event_archive_pkey" PRIMARY KEY (app_log_id),
  CONSTRAINT "app_log_event_archive_type_ck" CHECK (log_type = ANY (ARRAY['REQUEST'::text, 'QUERY'::text, 'RESPONSE'::text, 'ERROR'::text]))
);

CREATE INDEX ix_app_log_event_archive_request_created ON db_pipeline.app_log_event_archive USING btree (request_id, created_at);
CREATE INDEX ix_app_log_event_archive_session_created ON db_pipeline.app_log_event_archive USING btree (session_id, created_at DESC);

CREATE TABLE "db_pipeline"."backup_card_bnft" (
  "card_id" bigint NOT NULL,
  "card_bnft_id" character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_bnft'::text) NOT NULL,
  "bnft_cd" character varying(80) NOT NULL,
  "bnft_nm" text NOT NULL,
  "bnft_type_cd" character varying(20) NOT NULL,
  "bnft_origin_cd" character varying(20) NOT NULL,
  "bnft_scope_cd" character varying(20) NOT NULL,
  "bnft_brand_opt_cds" text[],
  "bnft_cond_expr" jsonb,
  "rule_list" jsonb DEFAULT '[]'::jsonb NOT NULL,
  "relation_list" jsonb DEFAULT '[]'::jsonb NOT NULL,
  "verification_status_cd" character varying(25) NOT NULL,
  "bnft_valid_from" date,
  "bnft_valid_to_excl" date,
  "bnft_rule_txt" text,
  "bnft_limit_txt" text,
  "bnft_search_txt" text,
  "bnft_embedding" vector(1536),
  CONSTRAINT "card_bnft_pkey" PRIMARY KEY (card_id, card_bnft_id),
  CONSTRAINT "card_bnft_card_id_bnft_cd_key" UNIQUE (card_id, bnft_cd),
  CONSTRAINT "card_bnft_ck_1" CHECK (bnft_scope_cd::text = 'PRODUCT'::text AND bnft_brand_opt_cds IS NULL OR bnft_scope_cd::text <> 'PRODUCT'::text AND COALESCE(cardinality(bnft_brand_opt_cds), 0) > 0),
  CONSTRAINT "card_bnft_ck_2" CHECK (db_pipeline.fn_valid_cond_expr(bnft_cond_expr)),
  CONSTRAINT "card_bnft_ck_3" CHECK (db_pipeline.fn_valid_rule_list(rule_list, 'LOCAL'::text)),
  CONSTRAINT "card_bnft_ck_4" CHECK (db_pipeline.fn_valid_relation_list(relation_list, card_bnft_id::text)),
  CONSTRAINT "card_bnft_ck_5" CHECK (bnft_origin_cd::text <> 'BRAND_SERVICE'::text OR bnft_scope_cd::text = 'BRAND'::text),
  CONSTRAINT "card_bnft_ck_6" CHECK (bnft_valid_to_excl IS NULL OR bnft_valid_from IS NULL OR bnft_valid_to_excl > bnft_valid_from)
);

CREATE INDEX ix_card_bnft_brand_opt_gin ON db_pipeline.backup_card_bnft USING gin (bnft_brand_opt_cds);
CREATE INDEX ix_card_bnft_cond_gin ON db_pipeline.backup_card_bnft USING gin (bnft_cond_expr jsonb_path_ops);
CREATE INDEX ix_card_bnft_relation_list_gin ON db_pipeline.backup_card_bnft USING gin (relation_list jsonb_path_ops);
CREATE INDEX ix_card_bnft_rule_list_gin ON db_pipeline.backup_card_bnft USING gin (rule_list jsonb_path_ops);

CREATE TABLE "db_pipeline"."card_ai_call" (
  "card_ai_run_id" character varying(20) NOT NULL,
  "card_doc_id" character varying(20) NOT NULL,
  "page_no" smallint NOT NULL,
  "card_doc_chunk_id" character varying(20) NOT NULL,
  "call_seq" smallint DEFAULT 1 NOT NULL,
  "call_input_sha256" character varying(64) NOT NULL,
  "call_status" character varying(20) NOT NULL,
  "call_resp_raw" text,
  "call_resp_json" jsonb,
  "call_error_msg" text,
  "call_input_token_cnt" integer,
  "call_output_token_cnt" integer,
  "call_latency_ms" integer,
  "call_req_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  CONSTRAINT "card_ai_call_pkey" PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq),
  CONSTRAINT "card_ai_call_call_seq_check" CHECK (call_seq > 0),
  CONSTRAINT "card_ai_call_check" CHECK (call_status::text <> 'SUCCEEDED'::text OR call_resp_json IS NOT NULL)
);

CREATE INDEX ix_card_ai_call_chunk_key ON db_pipeline.card_ai_call USING btree (card_doc_chunk_id);
CREATE INDEX ix_card_ai_call_doc_chunk_key ON db_pipeline.card_ai_call USING btree (card_doc_id, page_no, card_doc_chunk_id);

CREATE TABLE "db_pipeline"."card_ai_run" (
  "card_ai_run_id" character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_ai_run'::text) NOT NULL,
  "run_stage_cd" character varying(20) NOT NULL,
  "run_call_mthd_cd" character varying(20) NOT NULL,
  "run_model_nm" character varying(100) NOT NULL,
  "run_prompt_ver" character varying(50) NOT NULL,
  "run_prompt_txt" text NOT NULL,
  "run_param" jsonb,
  "run_target_card_doc_id" character varying(20),
  "run_status" character varying(20) DEFAULT 'RUNNING'::character varying NOT NULL,
  "run_start_date" timestamp with time zone DEFAULT now() NOT NULL,
  "run_end_date" timestamp with time zone,
  "run_note" text,
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  CONSTRAINT "card_ai_run_pkey" PRIMARY KEY (card_ai_run_id),
  CONSTRAINT "card_ai_run_check" CHECK (run_end_date IS NULL OR run_end_date >= run_start_date)
);

CREATE INDEX ix_card_ai_run_doc_key ON db_pipeline.card_ai_run USING btree (run_target_card_doc_id);

CREATE TABLE "db_pipeline"."card_common" (
  "card_common_id" bigint DEFAULT nextval('db_pipeline.seq_card_common'::regclass) NOT NULL,
  "common_cd" character varying(80) NOT NULL,
  "common_nm" text NOT NULL,
  "brand_cd" character varying(40),
  "service_grade_cd" character varying(40),
  "common_note" text,
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  CONSTRAINT "card_common_pkey" PRIMARY KEY (card_common_id),
  CONSTRAINT "card_common_common_cd_key" UNIQUE (common_cd)
);

CREATE TABLE "db_pipeline"."card_common_bnft" (
  "card_common_id" bigint NOT NULL,
  "card_common_bnft_id" character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_bnft'::text) NOT NULL,
  "bnft_cd" character varying(80) NOT NULL,
  "bnft_nm" text NOT NULL,
  "bnft_type_cd" character varying(20),
  "service_type_cd" character varying(20),
  "bnft_rule_txt" text,
  "bnft_limit_txt" text,
  "bnft_valid_from" date,
  "bnft_valid_to_excl" date,
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  "bnft_search_txt" text,
  "bnft_embedding" vector(1536),
  CONSTRAINT "card_common_bnft_pkey" PRIMARY KEY (card_common_id, card_common_bnft_id),
  CONSTRAINT "card_common_bnft_cd_key" UNIQUE (card_common_id, bnft_cd),
  CONSTRAINT "card_common_bnft_date_check" CHECK (bnft_valid_to_excl IS NULL OR bnft_valid_from IS NULL OR bnft_valid_to_excl > bnft_valid_from)
);

CREATE TABLE "db_pipeline"."card_common_bnft_apply" (
  "card_common_id" bigint NOT NULL,
  "card_common_bnft_id" character varying(20) NOT NULL,
  "card_id" bigint NOT NULL,
  CONSTRAINT "card_common_bnft_apply_pkey" PRIMARY KEY (card_common_id, card_common_bnft_id, card_id)
);

CREATE TABLE "db_pipeline"."card_common_doc" (
  "card_common_id" bigint NOT NULL,
  "card_doc_id" character varying(20) NOT NULL,
  CONSTRAINT "card_common_doc_pkey" PRIMARY KEY (card_common_id, card_doc_id)
);

CREATE TABLE "db_pipeline"."card_doc" (
  "card_doc_id" character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_doc'::text) NOT NULL,
  "doc_cd" character varying(50) NOT NULL,
  "doc_family_cd" character varying(100),
  "doc_type_cd" character varying(20) DEFAULT 'PRODUCT_GUIDE'::character varying NOT NULL,
  "doc_title" text NOT NULL,
  "doc_source_url" text,
  "doc_file_nm" text NOT NULL,
  "doc_file_size" bigint,
  "doc_sha256" character varying(64) NOT NULL,
  "doc_page_cnt" smallint,
  "doc_review_no" text,
  "doc_review_date" date,
  "doc_release_date" date,
  "doc_collect_date" timestamp with time zone NOT NULL,
  "doc_version_no" smallint DEFAULT 1 NOT NULL,
  "doc_status" character varying(20) DEFAULT 'ACTIVE'::character varying NOT NULL,
  "doc_note" text,
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  CONSTRAINT "card_doc_pkey" PRIMARY KEY (card_doc_id),
  CONSTRAINT "card_doc_doc_cd_key" UNIQUE (doc_cd),
  CONSTRAINT "card_doc_doc_sha256_key" UNIQUE (doc_sha256),
  CONSTRAINT "card_doc_doc_page_cnt_check" CHECK (doc_page_cnt IS NULL OR doc_page_cnt > 0),
  CONSTRAINT "card_doc_doc_sha256_check" CHECK (doc_sha256::text ~ '^[0-9a-f]{64}$'::text),
  CONSTRAINT "card_doc_doc_version_no_check" CHECK (doc_version_no > 0),
  CONSTRAINT "card_doc_family_cd_check" CHECK (doc_family_cd IS NULL OR doc_family_cd::text ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]*$'::text)
);

CREATE INDEX card_doc_family_version_idx ON db_pipeline.card_doc USING btree (doc_family_cd, doc_version_no, doc_release_date);

CREATE TABLE "db_pipeline"."card_doc_chunk" (
  "card_doc_id" character varying(20) NOT NULL,
  "page_no" smallint NOT NULL,
  "card_doc_chunk_id" character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_doc_chunk'::text) NOT NULL,
  "chunk_seq" integer NOT NULL,
  "chunk_section_nm" text,
  "chunk_type_cd" character varying(20) DEFAULT 'BODY'::character varying NOT NULL,
  "chunk_start_pos" integer NOT NULL,
  "chunk_end_pos" integer NOT NULL,
  "chunk_raw_txt" text NOT NULL,
  "chunk_clean_txt" text,
  "chunk_status" character varying(20) DEFAULT 'RAW'::character varying NOT NULL,
  "chunk_split_rule_ver" character varying(50) NOT NULL,
  "chunk_clean_rule_ver" character varying(50),
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  CONSTRAINT "card_doc_chunk_pkey" PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id),
  CONSTRAINT "card_doc_chunk_card_doc_chunk_id_key" UNIQUE (card_doc_chunk_id),
  CONSTRAINT "card_doc_chunk_card_doc_id_chunk_seq_key" UNIQUE (card_doc_id, chunk_seq),
  CONSTRAINT "card_doc_chunk_check" CHECK (chunk_start_pos >= 1 AND chunk_end_pos >= chunk_start_pos),
  CONSTRAINT "card_doc_chunk_check1" CHECK (chunk_status::text <> 'CLEANED'::text OR chunk_clean_txt IS NOT NULL AND chunk_clean_rule_ver IS NOT NULL),
  CONSTRAINT "card_doc_chunk_chunk_seq_check" CHECK (chunk_seq > 0)
);

CREATE TABLE "db_pipeline"."card_doc_page" (
  "card_doc_id" character varying(20) NOT NULL,
  "page_no" smallint NOT NULL,
  "page_raw_txt" text NOT NULL,
  "page_char_cnt" integer NOT NULL,
  "page_txt_sha256" character varying(64) NOT NULL,
  "page_layer_cd" character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
  "page_extractor_nm" character varying(50) NOT NULL,
  "page_extractor_ver" character varying(50),
  "page_note" text,
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  CONSTRAINT "card_doc_page_pkey" PRIMARY KEY (card_doc_id, page_no),
  CONSTRAINT "card_doc_page_page_char_cnt_check" CHECK (page_char_cnt >= 0),
  CONSTRAINT "card_doc_page_page_no_check" CHECK (page_no > 0)
);

CREATE TABLE "db_pipeline"."card_evidence_link" (
  "card_doc_id" character varying(20) NOT NULL,
  "page_no" smallint NOT NULL,
  "card_doc_chunk_id" character varying(20) NOT NULL,
  "evidence_id" character varying(20) NOT NULL,
  "card_id" bigint NOT NULL,
  "evidence_link_id" character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_evidence_link'::text) NOT NULL,
  "card_product_item_id" character varying(20),
  "ev_subject_cd" character varying(10) NOT NULL,
  "rule_key" character varying(40),
  "relation_key" character varying(40),
  "ev_item_cd" character varying(10) DEFAULT 'SELF'::character varying NOT NULL,
  "ev_item_key" character varying(100) DEFAULT '-'::character varying NOT NULL,
  CONSTRAINT "card_evidence_link_pkey" PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id),
  CONSTRAINT "card_evidence_link_id_key" UNIQUE (card_id, evidence_link_id),
  CONSTRAINT "card_evidence_link_natural_key" UNIQUE NULLS NOT DISTINCT (card_id, ev_subject_cd, card_product_item_id, rule_key, relation_key, ev_item_cd, ev_item_key, evidence_id),
  CONSTRAINT "card_evidence_link_ck_1" CHECK ((ev_item_cd::text = 'SELF'::text) = (ev_item_key::text = '-'::text)),
  CONSTRAINT "card_evidence_link_ck_2" CHECK (
CASE ev_subject_cd
    WHEN 'CARD'::text THEN num_nonnulls(card_product_item_id, rule_key, relation_key) = 0
    WHEN 'BNFT'::text THEN card_product_item_id IS NOT NULL AND num_nonnulls(rule_key, relation_key) = 0
    WHEN 'RULE'::text THEN card_product_item_id IS NOT NULL AND rule_key IS NOT NULL AND relation_key IS NULL
    WHEN 'REL'::text THEN card_product_item_id IS NOT NULL AND relation_key IS NOT NULL AND rule_key IS NULL
    WHEN 'ITEM'::text THEN card_product_item_id IS NOT NULL AND num_nonnulls(rule_key, relation_key) = 0
    ELSE false
END)
);

CREATE INDEX ix_card_evidence_link_evidence ON db_pipeline.card_evidence_link USING btree (evidence_id);
CREATE INDEX ix_card_evidence_link_subject ON db_pipeline.card_evidence_link USING btree (card_id, ev_subject_cd, card_product_item_id, rule_key);

CREATE TABLE "db_pipeline"."card_extr_stg" (
  "card_ai_run_id" character varying(20) NOT NULL,
  "card_doc_id" character varying(20) NOT NULL,
  "page_no" smallint NOT NULL,
  "card_doc_chunk_id" character varying(20) NOT NULL,
  "call_seq" smallint NOT NULL,
  "card_extr_stg_id" character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_extr_stg'::text) NOT NULL,
  "stg_item_seq" smallint NOT NULL,
  "card_id" bigint,
  "stg_kind_cd" character varying(20) NOT NULL,
  "stg_parent_card_extr_stg_id" character varying(20),
  "stg_raw_item" jsonb NOT NULL,
  "stg_evidence_txt" text NOT NULL,
  "stg_evidence_start_pos" integer,
  "stg_evidence_end_pos" integer,
  "stg_sql_check_cd" character varying(30),
  "stg_ai_vrfy_cd" character varying(20),
  "stg_ai_vrfy_card_ai_run_id" character varying(20),
  "stg_status" character varying(20) DEFAULT 'PENDING_REVIEW'::character varying NOT NULL,
  "stg_review_note" text,
  "stg_approved_date" timestamp with time zone,
  "stg_approved_user_id" character varying(50),
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  CONSTRAINT "card_extr_stg_pkey" PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id),
  CONSTRAINT "card_extr_stg_card_ai_run_id_card_doc_id_page_no_card_doc_c_key" UNIQUE (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, stg_item_seq),
  CONSTRAINT "card_extr_stg_card_extr_stg_id_key" UNIQUE (card_extr_stg_id),
  CONSTRAINT "card_extr_stg_check" CHECK (stg_evidence_start_pos IS NULL AND stg_evidence_end_pos IS NULL OR stg_evidence_start_pos >= 1 AND stg_evidence_end_pos >= stg_evidence_start_pos),
  CONSTRAINT "card_extr_stg_check1" CHECK ((stg_status::text <> ALL (ARRAY['AUTO_APPROVED'::character varying::text, 'MANUAL_APPROVED'::character varying::text])) OR NOT stg_sql_check_cd::text IS DISTINCT FROM 'OK'::text AND stg_evidence_start_pos IS NOT NULL AND stg_evidence_end_pos IS NOT NULL AND btrim(stg_evidence_txt) <> ''::text),
  CONSTRAINT "card_extr_stg_stg_item_seq_check" CHECK (stg_item_seq > 0)
);

CREATE INDEX ix_card_extr_stg_chunk_key ON db_pipeline.card_extr_stg USING btree (card_doc_chunk_id);
CREATE INDEX ix_card_extr_stg_status_key ON db_pipeline.card_extr_stg USING btree (stg_status, stg_kind_cd);

CREATE TABLE "db_pipeline"."card_product" (
  "card_id" bigint DEFAULT nextval('db_pipeline.seq_card_product'::regclass) NOT NULL,
  "product_cd" character varying(80) NOT NULL,
  "product_nm" text NOT NULL,
  "issuer" character varying(50) NOT NULL,
  "card_kind_cd" character varying(10) NOT NULL,
  "product_status_cd" character varying(20) DEFAULT 'ACTIVE'::character varying NOT NULL,
  "launched_on" date,
  "discontinued_on" date,
  "brand_opt_list" jsonb DEFAULT '[]'::jsonb NOT NULL,
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  "card_cond_expr" jsonb,
  "card_cond_status_cd" character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
  CONSTRAINT "card_product_pkey" PRIMARY KEY (card_id),
  CONSTRAINT "card_product_product_cd_key" UNIQUE (product_cd),
  CONSTRAINT "card_product_brand_opt_list_check" CHECK (db_pipeline.fn_valid_brand_opt_list(brand_opt_list)),
  CONSTRAINT "card_product_card_cond_expr_check" CHECK (db_pipeline.fn_valid_cond_expr(card_cond_expr)),
  CONSTRAINT "card_product_dates_check" CHECK (discontinued_on IS NULL OR launched_on IS NULL OR discontinued_on >= launched_on)
);

CREATE INDEX card_product_brand_opt_gin_idx ON db_pipeline.card_product USING gin (brand_opt_list jsonb_path_ops);
CREATE INDEX card_product_kind_status_idx ON db_pipeline.card_product USING btree (card_kind_cd, product_status_cd);

CREATE TABLE "db_pipeline"."card_product_doc" (
  "card_id" bigint NOT NULL,
  "card_doc_id" character varying(20) NOT NULL,
  "doc_role_cd" character varying(20) NOT NULL,
  "brand_opt_cds" text[],
  "approval_status_cd" character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
  "applicability_basis_txt" text NOT NULL,
  "approval_note" text,
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  CONSTRAINT "card_product_doc_pkey" PRIMARY KEY (card_id, card_doc_id),
  CONSTRAINT "card_product_doc_approved_check" CHECK (approval_status_cd::text <> 'APPROVED'::text OR length(TRIM(BOTH FROM applicability_basis_txt)) > 0),
  CONSTRAINT "card_product_doc_brand_check" CHECK (doc_role_cd::text <> 'BRAND_SERVICE'::text OR COALESCE(cardinality(brand_opt_cds), 0) > 0)
);

CREATE INDEX card_product_doc_doc_idx ON db_pipeline.card_product_doc USING btree (card_doc_id, card_id);

CREATE TABLE "db_pipeline"."card_product_item" (
  "card_id" bigint NOT NULL,
  "card_product_item_id" character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_product_item'::text) NOT NULL,
  "item_type_cd" character varying(20) NOT NULL,
  "item_cd" character varying(80) NOT NULL,
  "item_nm" text NOT NULL,
  "item_subtype_cd" character varying(20),
  "item_origin_cd" character varying(20) DEFAULT 'LOCAL'::character varying NOT NULL,
  "item_scope_cd" character varying(20) DEFAULT 'PRODUCT'::character varying NOT NULL,
  "item_brand_opt_cds" text[],
  "item_cond_expr" jsonb,
  "rule_list" jsonb DEFAULT '[]'::jsonb NOT NULL,
  "relation_list" jsonb DEFAULT '[]'::jsonb NOT NULL,
  "item_data" jsonb DEFAULT '{}'::jsonb NOT NULL,
  "verification_status_cd" character varying(25) DEFAULT 'PENDING_REVIEW'::character varying NOT NULL,
  "item_valid_from" date,
  "item_valid_to_excl" date,
  "item_rule_txt" text,
  "item_limit_txt" text,
  "item_search_txt" text,
  "item_embedding" vector(1536),
  "item_ref" text DEFAULT ((('card_product_item:'::text || (card_id)::text) || ':'::text) || (card_product_item_id)::text) GENERATED ALWAYS AS (((('card_product_item:'::text || (card_id)::text) || ':'::text) || (card_product_item_id)::text)) STORED,
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  CONSTRAINT "card_product_item_pkey" PRIMARY KEY (card_id, card_product_item_id),
  CONSTRAINT "card_product_item_cd_key" UNIQUE (card_id, item_cd),
  CONSTRAINT "card_product_item_ref_key" UNIQUE (item_ref),
  CONSTRAINT "card_product_item_cond_ck" CHECK (db_pipeline.fn_valid_cond_expr(item_cond_expr)),
  CONSTRAINT "card_product_item_data_ck" CHECK (db_pipeline.fn_valid_item_data(item_type_cd::text, item_data)),
  CONSTRAINT "card_product_item_date_ck" CHECK (item_valid_to_excl IS NULL OR item_valid_from IS NULL OR item_valid_to_excl > item_valid_from),
  CONSTRAINT "card_product_item_nonbnft_ck" CHECK (item_type_cd::text = 'BENEFIT'::text OR rule_list = '[]'::jsonb AND relation_list = '[]'::jsonb AND item_cond_expr IS NULL),
  CONSTRAINT "card_product_item_origin_ck" CHECK (item_origin_cd::text <> 'BRAND_SERVICE'::text OR item_scope_cd::text = 'BRAND'::text),
  CONSTRAINT "card_product_item_rel_ck" CHECK (db_pipeline.fn_valid_relation_list(relation_list, card_product_item_id::text)),
  CONSTRAINT "card_product_item_rule_ck" CHECK (db_pipeline.fn_valid_rule_list(rule_list, 'LOCAL'::text)),
  CONSTRAINT "card_product_item_scope_ck" CHECK (item_scope_cd::text = 'PRODUCT'::text AND item_brand_opt_cds IS NULL OR item_scope_cd::text <> 'PRODUCT'::text AND COALESCE(cardinality(item_brand_opt_cds), 0) > 0),
  CONSTRAINT "card_product_item_subtype_ck" CHECK ((item_type_cd::text = 'BENEFIT'::text) = (item_subtype_cd IS NOT NULL))
);

CREATE INDEX ix_card_product_item_brand_gin ON db_pipeline.card_product_item USING gin (item_brand_opt_cds);
CREATE INDEX ix_card_product_item_cond_gin ON db_pipeline.card_product_item USING gin (item_cond_expr jsonb_path_ops);
CREATE INDEX ix_card_product_item_data_gin ON db_pipeline.card_product_item USING gin (item_data jsonb_path_ops);
CREATE INDEX ix_card_product_item_rel_gin ON db_pipeline.card_product_item USING gin (relation_list jsonb_path_ops);
CREATE INDEX ix_card_product_item_rule_gin ON db_pipeline.card_product_item USING gin (rule_list jsonb_path_ops);
CREATE INDEX ix_card_product_item_type ON db_pipeline.card_product_item USING btree (card_id, item_type_cd);

CREATE TABLE "db_pipeline"."card_source_evidence" (
  "card_doc_id" character varying(20) NOT NULL,
  "page_no" smallint NOT NULL,
  "card_doc_chunk_id" character varying(20) NOT NULL,
  "evidence_id" character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_source_evidence'::text) NOT NULL,
  "card_extr_stg_id" character varying(20),
  "quote_txt" text NOT NULL,
  "start_pos" integer,
  "end_pos" integer,
  "approval_status_cd" character varying(20) NOT NULL,
  CONSTRAINT "card_source_evidence_pkey" PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id),
  CONSTRAINT "card_source_evidence_evidence_id_key" UNIQUE (evidence_id),
  CONSTRAINT "card_source_evidence_ck_1" CHECK (start_pos IS NULL OR start_pos > 0),
  CONSTRAINT "card_source_evidence_ck_2" CHECK (end_pos IS NULL OR start_pos IS NULL OR end_pos >= start_pos)
);

CREATE INDEX ix_card_source_evidence_lookup ON db_pipeline.card_source_evidence USING btree (card_doc_id, page_no, card_doc_chunk_id);

CREATE TABLE "db_pipeline"."common_cd" (
  "common_code_grp_id" character varying(20) NOT NULL,
  "common_cd" character varying(40) NOT NULL,
  "common_cd_nm" text NOT NULL,
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  "common_cd_desc" text,
  CONSTRAINT "pk_common_cd" PRIMARY KEY (common_code_grp_id, common_cd)
);

CREATE TABLE "db_pipeline"."common_code_grp" (
  "common_code_grp_id" character varying(20) NOT NULL,
  "common_code_grp_nm" text NOT NULL,
  "create_date" timestamp with time zone DEFAULT now() NOT NULL,
  "create_user_id" character varying(50) NOT NULL,
  "update_date" timestamp with time zone DEFAULT now() NOT NULL,
  "update_user_id" character varying(50) NOT NULL,
  "common_code_grp_desc" text,
  CONSTRAINT "pk_common_code_grp" PRIMARY KEY (common_code_grp_id)
);

CREATE OR REPLACE VIEW "db_pipeline"."v_card_bnft_rel" AS
 SELECT b.card_id,
    b.card_bnft_id AS from_bnft_id,
    x.value ->> 'to_bnft_id'::text AS to_bnft_id,
    x.value ->> 'relation_key'::text AS relation_key,
    x.value ->> 'rel_type_cd'::text AS rel_type_cd,
    (x.value ->> 'rel_priority'::text)::integer AS rel_priority,
    false AS reverse_yn
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) b
     CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) x(value)
UNION ALL
 SELECT b.card_id,
    x.value ->> 'to_bnft_id'::text AS from_bnft_id,
    b.card_bnft_id AS to_bnft_id,
    x.value ->> 'relation_key'::text AS relation_key,
    x.value ->> 'rel_type_cd'::text AS rel_type_cd,
    (x.value ->> 'rel_priority'::text)::integer AS rel_priority,
    true AS reverse_yn
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) b
     CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) x(value)
  WHERE (x.value ->> 'rel_type_cd'::text) = 'MUTUALLY_EXCLUSIVE'::text
;

CREATE OR REPLACE VIEW "db_pipeline"."v_card_brand_opt" AS
 SELECT p.card_id,
    p.product_cd,
    p.product_nm,
    o.value ->> 'brand_opt_cd'::text AS brand_opt_cd,
    o.value ->> 'brand_opt_nm'::text AS brand_opt_nm,
    o.value ->> 'brand_cd'::text AS brand_cd,
    o.value ->> 'service_grade_cd'::text AS service_grade_cd,
    o.value ->> 'service_type_cd'::text AS service_type_cd,
    o.value ->> 'brand_opt_status_cd'::text AS brand_opt_status_cd
   FROM db_pipeline.card_product p
     CROSS JOIN LATERAL jsonb_array_elements(p.brand_opt_list) o(value)
;

CREATE OR REPLACE VIEW "db_pipeline"."v_card_cond_atom" AS
 WITH src AS (
         SELECT 'CARD'::text AS owner_cd,
            p.card_id,
            NULL::character varying AS card_bnft_id,
            NULL::text AS rule_key,
            p.card_cond_expr AS expr
           FROM db_pipeline.card_product p
          WHERE p.card_cond_expr IS NOT NULL
        UNION ALL
         SELECT 'BNFT'::text AS text,
            b_1.card_id,
            b_1.card_bnft_id,
            NULL::text AS text,
            b_1.bnft_cond_expr
           FROM ( SELECT card_product_item.card_id,
                    card_product_item.card_product_item_id AS card_bnft_id,
                    card_product_item.item_cd AS bnft_cd,
                    card_product_item.item_nm AS bnft_nm,
                    card_product_item.item_subtype_cd AS bnft_type_cd,
                    card_product_item.item_origin_cd AS bnft_origin_cd,
                    card_product_item.item_scope_cd AS bnft_scope_cd,
                    card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
                    card_product_item.item_cond_expr AS bnft_cond_expr,
                    card_product_item.rule_list,
                    card_product_item.relation_list,
                    card_product_item.verification_status_cd,
                    card_product_item.item_valid_from AS bnft_valid_from,
                    card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
                    card_product_item.item_rule_txt AS bnft_rule_txt,
                    card_product_item.item_limit_txt AS bnft_limit_txt,
                    card_product_item.item_search_txt AS bnft_search_txt,
                    card_product_item.item_embedding AS bnft_embedding
                   FROM db_pipeline.card_product_item
                  WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) b_1
          WHERE b_1.bnft_cond_expr IS NOT NULL
        UNION ALL
         SELECT 'RULE'::text AS text,
            r.card_id,
            r.card_product_item_id AS card_bnft_id,
            r.rule_key,
            r.cond_expr
           FROM db_pipeline.v_card_rule r
          WHERE r.cond_expr IS NOT NULL
        )
 SELECT s.owner_cd,
    s.card_id,
    s.card_bnft_id AS card_product_item_id,
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
     CROSS JOIN LATERAL jsonb_array_elements(b.value -> 'atoms'::text) a(value)
;

CREATE OR REPLACE VIEW "db_pipeline"."v_card_integrity_issue" AS
 WITH atoms AS (
         SELECT v_card_cond_atom.owner_cd,
            v_card_cond_atom.card_id,
            v_card_cond_atom.card_product_item_id AS card_bnft_id,
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
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) x
  WHERE NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product p
          WHERE p.card_id = x.card_id))
UNION ALL
 SELECT 'local_confirmed_without_rule'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_bnft_id::text AS issue_key
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) x
  WHERE x.verification_status_cd::text = 'CONFIRMED'::text AND jsonb_array_length(x.rule_list) = 0
UNION ALL
 SELECT 'bnft_txt_without_evidence'::text AS gate_cd,
    (x.card_id || '/'::text) || x.card_bnft_id::text AS issue_key
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) x
  WHERE (x.bnft_rule_txt IS NOT NULL OR x.bnft_limit_txt IS NOT NULL) AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_evidence_link l
          WHERE l.card_id = x.card_id AND l.card_product_item_id::text = x.card_bnft_id::text AND l.ev_subject_cd::text = 'BNFT'::text AND l.ev_item_cd::text = 'SELF'::text))
UNION ALL
 SELECT 'rel_to_bnft_orphan'::text AS gate_cd,
    (x.card_id || '/'::text) || x.relation_key AS issue_key
   FROM db_pipeline.v_card_bnft_rel x
  WHERE NOT x.reverse_yn AND NOT (EXISTS ( SELECT 1
           FROM ( SELECT card_product_item.card_id,
                    card_product_item.card_product_item_id AS card_bnft_id,
                    card_product_item.item_cd AS bnft_cd,
                    card_product_item.item_nm AS bnft_nm,
                    card_product_item.item_subtype_cd AS bnft_type_cd,
                    card_product_item.item_origin_cd AS bnft_origin_cd,
                    card_product_item.item_scope_cd AS bnft_scope_cd,
                    card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
                    card_product_item.item_cond_expr AS bnft_cond_expr,
                    card_product_item.rule_list,
                    card_product_item.relation_list,
                    card_product_item.verification_status_cd,
                    card_product_item.item_valid_from AS bnft_valid_from,
                    card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
                    card_product_item.item_rule_txt AS bnft_rule_txt,
                    card_product_item.item_limit_txt AS bnft_limit_txt,
                    card_product_item.item_search_txt AS bnft_search_txt,
                    card_product_item.item_embedding AS bnft_embedding
                   FROM db_pipeline.card_product_item
                  WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) b
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
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) b
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
               FROM ( SELECT card_product_item.card_id,
                        card_product_item.card_product_item_id AS card_bnft_id,
                        card_product_item.item_cd AS bnft_cd,
                        card_product_item.item_nm AS bnft_nm,
                        card_product_item.item_subtype_cd AS bnft_type_cd,
                        card_product_item.item_origin_cd AS bnft_origin_cd,
                        card_product_item.item_scope_cd AS bnft_scope_cd,
                        card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
                        card_product_item.item_cond_expr AS bnft_cond_expr,
                        card_product_item.rule_list,
                        card_product_item.relation_list,
                        card_product_item.verification_status_cd,
                        card_product_item.item_valid_from AS bnft_valid_from,
                        card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
                        card_product_item.item_rule_txt AS bnft_rule_txt,
                        card_product_item.item_limit_txt AS bnft_limit_txt,
                        card_product_item.item_search_txt AS bnft_search_txt,
                        card_product_item.item_embedding AS bnft_embedding
                       FROM db_pipeline.card_product_item
                      WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) b
              WHERE b.card_id = l.card_id AND b.card_bnft_id::text = l.card_product_item_id::text))
            WHEN 'RULE'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_rule r
              WHERE r.card_id = l.card_id AND r.card_product_item_id::text = l.card_product_item_id::text AND r.rule_key = l.rule_key::text))
            WHEN 'REL'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_bnft_rel r
              WHERE NOT r.reverse_yn AND r.card_id = l.card_id AND r.from_bnft_id::text = l.card_product_item_id::text AND r.relation_key = l.relation_key::text))
            WHEN 'ITEM'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.card_product_item i
              WHERE i.card_id = l.card_id AND i.card_product_item_id::text = l.card_product_item_id::text))
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
              WHERE a.card_id = l.card_id AND a.atom_key = l.ev_item_key::text AND NOT a.card_bnft_id::text IS DISTINCT FROM l.card_product_item_id::text AND NOT a.rule_key IS DISTINCT FROM l.rule_key::text))
            WHEN 'TARGET'::text THEN (EXISTS ( SELECT 1
               FROM db_pipeline.v_card_rule_target t
              WHERE t.card_id = l.card_id AND t.card_product_item_id::text = l.card_product_item_id::text AND t.rule_key = l.rule_key::text AND t.target_key = l.ev_item_key::text))
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
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) b
     CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) o(cd)
  WHERE b.bnft_origin_cd::text = 'BRAND_SERVICE'::text AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_product_doc x
          WHERE x.card_id = b.card_id AND x.doc_role_cd::text = 'BRAND_SERVICE'::text AND (o.cd = ANY (x.brand_opt_cds))))
UNION ALL
 SELECT 'brand_bnft_confirmed_without_evidence'::text AS gate_cd,
    (b.card_id || '/'::text) || b.card_bnft_id::text AS issue_key
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) b
  WHERE b.bnft_origin_cd::text = 'BRAND_SERVICE'::text AND b.verification_status_cd::text = 'CONFIRMED'::text AND NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_evidence_link l
          WHERE l.card_id = b.card_id AND l.card_product_item_id::text = b.card_bnft_id::text))
UNION ALL
 SELECT 'evidence_brand_opt_mismatch'::text AS gate_cd,
    (l.card_id || '/'::text) || l.evidence_link_id::text AS issue_key
   FROM db_pipeline.card_evidence_link l
     JOIN db_pipeline.card_source_evidence e USING (evidence_id)
     JOIN ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) b ON b.card_id = l.card_id AND b.card_bnft_id::text = l.card_product_item_id::text
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
          WHERE c.common_code_grp_id::text = g.common_code_grp_id::text))
;

CREATE OR REPLACE VIEW "db_pipeline"."v_card_product_item_evidence" AS
 SELECT l.evidence_link_id,
    l.card_id,
    i.card_product_item_id,
    i.item_type_cd,
    i.item_ref,
    l.ev_subject_cd,
    l.rule_key,
    l.relation_key,
    l.ev_item_cd,
    l.ev_item_key,
    l.evidence_id,
    l.card_doc_id,
    l.page_no,
    l.card_doc_chunk_id
   FROM db_pipeline.card_evidence_link l
     JOIN db_pipeline.card_product_item i ON i.card_id = l.card_id AND i.card_product_item_id::text = l.card_product_item_id::text
  WHERE l.card_product_item_id IS NOT NULL
;

CREATE OR REPLACE VIEW "db_pipeline"."v_card_rule" AS
 SELECT b.card_id,
    b.card_bnft_id AS card_product_item_id,
    r.value ->> 'rule_key'::text AS rule_key,
    r.ord AS rule_seq,
    NULLIF(r.value -> 'cond_expr'::text, 'null'::jsonb) AS cond_expr,
    COALESCE(r.value -> 'target_list'::text, '[]'::jsonb) AS target_list,
    ((r.value ->> 'value_num'::text))::numeric(18,4) AS value_num,
    r.value ->> 'value_unit_cd'::text AS value_unit_cd,
    r.value ->> 'rule_status_cd'::text AS rule_status_cd
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) b
     CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) WITH ORDINALITY r(value, ord)
;

CREATE OR REPLACE VIEW "db_pipeline"."v_card_rule_target" AS
 SELECT r.card_id,
    r.card_product_item_id,
    r.rule_key,
    t.value ->> 'target_type_cd'::text AS target_type_cd,
    t.value ->> 'target_key'::text AS target_key,
    t.value ->> 'target_nm'::text AS target_nm
   FROM db_pipeline.v_card_rule r
     CROSS JOIN LATERAL jsonb_array_elements(r.target_list) t(value)
;

CREATE OR REPLACE VIEW "db_pipeline"."v_common_cd_usage" AS
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
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) card_bnft
  WHERE card_bnft.bnft_type_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.bnft_origin_cd'::text AS source_nm,
    'BNFT_ORIGIN'::character varying(20) AS common_code_grp_id,
    card_bnft.bnft_origin_cd::text AS cd_value
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) card_bnft
  WHERE card_bnft.bnft_origin_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.bnft_scope_cd'::text AS source_nm,
    'BNFT_SCOPE'::character varying(20) AS common_code_grp_id,
    card_bnft.bnft_scope_cd::text AS cd_value
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) card_bnft
  WHERE card_bnft.bnft_scope_cd IS NOT NULL
UNION ALL
 SELECT 'card_bnft.verification_status_cd'::text AS source_nm,
    'VERIFY_STATUS'::character varying(20) AS common_code_grp_id,
    card_bnft.verification_status_cd::text AS cd_value
   FROM ( SELECT card_product_item.card_id,
            card_product_item.card_product_item_id AS card_bnft_id,
            card_product_item.item_cd AS bnft_cd,
            card_product_item.item_nm AS bnft_nm,
            card_product_item.item_subtype_cd AS bnft_type_cd,
            card_product_item.item_origin_cd AS bnft_origin_cd,
            card_product_item.item_scope_cd AS bnft_scope_cd,
            card_product_item.item_brand_opt_cds AS bnft_brand_opt_cds,
            card_product_item.item_cond_expr AS bnft_cond_expr,
            card_product_item.rule_list,
            card_product_item.relation_list,
            card_product_item.verification_status_cd,
            card_product_item.item_valid_from AS bnft_valid_from,
            card_product_item.item_valid_to_excl AS bnft_valid_to_excl,
            card_product_item.item_rule_txt AS bnft_rule_txt,
            card_product_item.item_limit_txt AS bnft_limit_txt,
            card_product_item.item_search_txt AS bnft_search_txt,
            card_product_item.item_embedding AS bnft_embedding
           FROM db_pipeline.card_product_item
          WHERE card_product_item.item_type_cd::text = 'BENEFIT'::text) card_bnft
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
  WHERE v_card_cond_atom.expr_status_cd IS NOT NULL
;
