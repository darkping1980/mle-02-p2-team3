--
-- PostgreSQL database dump
--

-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.0

-- Started on 2026-11-03 14:36:05

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 61 (class 2615 OID 20623)
-- Name: db_pipeline; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA db_pipeline;


--
-- TOC entry 4398 (class 0 OID 0)
-- Dependencies: 61
-- Name: SCHEMA db_pipeline; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA db_pipeline IS '카드 상품 중심 V7 공통코드·반정규화 스키마(초안)';


--
-- TOC entry 622 (class 1255 OID 20626)
-- Name: fn_cond_spend_bound(jsonb, text); Type: FUNCTION; Schema: db_pipeline; Owner: -
--

CREATE FUNCTION db_pipeline.fn_cond_spend_bound(p_expr jsonb, p_bound text) RETURNS numeric
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $$
    SELECT CASE WHEN count(*) = 1 THEN max((a.value->>p_bound)::numeric) END
    FROM jsonb_array_elements(p_expr->'branches') AS b(value)
    CROSS JOIN LATERAL jsonb_array_elements(b.value->'atoms') AS a(value)
    WHERE jsonb_array_length(p_expr->'branches') = 1
      AND a.value->>'cond_type_cd' = 'SPEND_REQ'
      AND a.value->>'cond_basis_cd' = 'PREV_MONTH_SPEND'
      AND (a.value->>'negate_yn')::boolean = false
$$;


--
-- TOC entry 4399 (class 0 OID 0)
-- Dependencies: 622
-- Name: FUNCTION fn_cond_spend_bound(p_expr jsonb, p_bound text); Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON FUNCTION db_pipeline.fn_cond_spend_bound(p_expr jsonb, p_bound text) IS '단일 branch의 전월 실적 구간 값 추출. OR식이나 구간 atom이 둘 이상이면 NULL을 반환하고 v_card_cond_atom으로 조회';


--
-- TOC entry 620 (class 1255 OID 20624)
-- Name: fn_get_biz_id(text); Type: FUNCTION; Schema: db_pipeline; Owner: -
--

CREATE FUNCTION db_pipeline.fn_get_biz_id(p_tbl_nm text) RETURNS character varying
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $_$
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
$_$;


--
-- TOC entry 4400 (class 0 OID 0)
-- Dependencies: 620
-- Name: FUNCTION fn_get_biz_id(p_tbl_nm text); Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON FUNCTION db_pipeline.fn_get_biz_id(p_tbl_nm text) IS 'db_pipeline.seq_<테이블명> 시퀀스로 YYYYMMDD_000001 형식 업무 ID 발급(Asia/Seoul 기준)';


--
-- TOC entry 624 (class 1255 OID 20630)
-- Name: fn_valid_brand_opt_list(jsonb); Type: FUNCTION; Schema: db_pipeline; Owner: -
--

CREATE FUNCTION db_pipeline.fn_valid_brand_opt_list(p_list jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
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
$_$;


--
-- TOC entry 4401 (class 0 OID 0)
-- Dependencies: 624
-- Name: FUNCTION fn_valid_brand_opt_list(p_list jsonb); Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON FUNCTION db_pipeline.fn_valid_brand_opt_list(p_list jsonb) IS '상품의 브랜드 선택지 목록 검증. 코드값 소속은 v_common_cd_usage로 검사';


--
-- TOC entry 621 (class 1255 OID 20625)
-- Name: fn_valid_cond_expr(jsonb); Type: FUNCTION; Schema: db_pipeline; Owner: -
--

CREATE FUNCTION db_pipeline.fn_valid_cond_expr(p_expr jsonb) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
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
$_$;


--
-- TOC entry 4402 (class 0 OID 0)
-- Dependencies: 621
-- Name: FUNCTION fn_valid_cond_expr(p_expr jsonb); Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON FUNCTION db_pipeline.fn_valid_cond_expr(p_expr jsonb) IS '조건식 JSONB 계약 검증. branch 사이 OR, branch 안 atom AND, negate_yn=NOT';


--
-- TOC entry 626 (class 1255 OID 20632)
-- Name: fn_valid_relation_list(jsonb, text); Type: FUNCTION; Schema: db_pipeline; Owner: -
--

CREATE FUNCTION db_pipeline.fn_valid_relation_list(p_list jsonb, p_self_bnft_id text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
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
$_$;


--
-- TOC entry 4403 (class 0 OID 0)
-- Dependencies: 626
-- Name: FUNCTION fn_valid_relation_list(p_list jsonb, p_self_bnft_id text); Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON FUNCTION db_pipeline.fn_valid_relation_list(p_list jsonb, p_self_bnft_id text) IS '혜택 관계 목록 JSONB 계약 검증. 자기 참조, relation_key 중복, 같은 대상·유형 중복, 제거된 trigger_pool_id 거부';


--
-- TOC entry 625 (class 1255 OID 20631)
-- Name: fn_valid_rule_list(jsonb, text); Type: FUNCTION; Schema: db_pipeline; Owner: -
--

CREATE FUNCTION db_pipeline.fn_valid_rule_list(p_list jsonb, p_owner text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
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
$_$;


--
-- TOC entry 4404 (class 0 OID 0)
-- Dependencies: 625
-- Name: FUNCTION fn_valid_rule_list(p_list jsonb, p_owner text); Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON FUNCTION db_pipeline.fn_valid_rule_list(p_list jsonb, p_owner text) IS '계산 규칙 목록 JSONB 계약 검증. 최종 규칙에는 pool_refs를 허용하지 않는다. p_owner는 LOCAL만 허용';


--
-- TOC entry 623 (class 1255 OID 20627)
-- Name: fn_valid_target_list(jsonb); Type: FUNCTION; Schema: db_pipeline; Owner: -
--

CREATE FUNCTION db_pipeline.fn_valid_target_list(p_list jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
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
$_$;


--
-- TOC entry 4405 (class 0 OID 0)
-- Dependencies: 623
-- Name: FUNCTION fn_valid_target_list(p_list jsonb); Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON FUNCTION db_pipeline.fn_valid_target_list(p_list jsonb) IS '대상 목록 JSONB 계약 검증. 비율·금액 키는 두지 않으며 대상별 비율이 다르면 규칙 행을 나눔';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 365 (class 1259 OID 20850)
-- Name: card_ai_call; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_ai_call (
    card_ai_run_id character varying(20) NOT NULL,
    card_doc_id character varying(20) NOT NULL,
    page_no smallint NOT NULL,
    card_doc_chunk_id character varying(20) NOT NULL,
    call_seq smallint DEFAULT 1 NOT NULL,
    call_input_sha256 character varying(64) NOT NULL,
    call_status character varying(20) NOT NULL,
    call_resp_raw text,
    call_resp_json jsonb,
    call_error_msg text,
    call_input_token_cnt integer,
    call_output_token_cnt integer,
    call_latency_ms integer,
    call_req_date timestamp with time zone DEFAULT now() NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT card_ai_call_call_seq_check CHECK ((call_seq > 0)),
    CONSTRAINT card_ai_call_check CHECK ((((call_status)::text <> 'SUCCEEDED'::text) OR (call_resp_json IS NOT NULL)))
);


--
-- TOC entry 4406 (class 0 OID 0)
-- Dependencies: 365
-- Name: TABLE card_ai_call; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_ai_call IS 'AI 호출 이력';


--
-- TOC entry 4407 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.card_ai_run_id IS 'AI 실행 아이디';


--
-- TOC entry 4408 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.card_doc_id IS '문서 아이디';


--
-- TOC entry 4409 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.page_no; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.page_no IS '페이지 번호';


--
-- TOC entry 4410 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.card_doc_chunk_id IS '청크 아이디';


--
-- TOC entry 4411 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.call_seq; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_seq IS '호출 순번';


--
-- TOC entry 4412 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.call_input_sha256; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_input_sha256 IS '호출 입력 해시';


--
-- TOC entry 4413 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.call_status; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_status IS '호출 상태';


--
-- TOC entry 4414 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.call_resp_raw; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_resp_raw IS '응답 원문';


--
-- TOC entry 4415 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.call_resp_json; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_resp_json IS '응답 JSON';


--
-- TOC entry 4416 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.call_error_msg; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_error_msg IS '오류 메시지';


--
-- TOC entry 4417 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.call_input_token_cnt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_input_token_cnt IS '입력 토큰 수';


--
-- TOC entry 4418 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.call_output_token_cnt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_output_token_cnt IS '출력 토큰 수';


--
-- TOC entry 4419 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.call_latency_ms; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_latency_ms IS '응답 시간';


--
-- TOC entry 4420 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.call_req_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_req_date IS '요청 일시';


--
-- TOC entry 4421 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.create_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.create_date IS '생성 일시';


--
-- TOC entry 4422 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4423 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.update_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.update_date IS '수정 일시';


--
-- TOC entry 4424 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_call.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_call.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 364 (class 1259 OID 20839)
-- Name: card_ai_run; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_ai_run (
    card_ai_run_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_ai_run'::text) NOT NULL,
    run_stage_cd character varying(20) NOT NULL,
    run_call_mthd_cd character varying(20) NOT NULL,
    run_model_nm character varying(100) NOT NULL,
    run_prompt_ver character varying(50) NOT NULL,
    run_prompt_txt text NOT NULL,
    run_param jsonb,
    run_target_card_doc_id character varying(20),
    run_status character varying(20) DEFAULT 'RUNNING'::character varying NOT NULL,
    run_start_date timestamp with time zone DEFAULT now() NOT NULL,
    run_end_date timestamp with time zone,
    run_note text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT card_ai_run_check CHECK (((run_end_date IS NULL) OR (run_end_date >= run_start_date)))
);


--
-- TOC entry 4425 (class 0 OID 0)
-- Dependencies: 364
-- Name: TABLE card_ai_run; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_ai_run IS 'AI 실행 이력';


--
-- TOC entry 4426 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.card_ai_run_id IS 'AI 실행 아이디';


--
-- TOC entry 4427 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.run_stage_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_stage_cd IS '실행 단계';


--
-- TOC entry 4428 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.run_call_mthd_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_call_mthd_cd IS 'AI 호출 방식';


--
-- TOC entry 4429 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.run_model_nm; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_model_nm IS '모델명';


--
-- TOC entry 4430 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.run_prompt_ver; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_prompt_ver IS '프롬프트 버전';


--
-- TOC entry 4431 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.run_prompt_txt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_prompt_txt IS '프롬프트 원문';


--
-- TOC entry 4432 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.run_param; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_param IS '모델 파라미터';


--
-- TOC entry 4433 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.run_target_card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_target_card_doc_id IS '대상 문서 아이디';


--
-- TOC entry 4434 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.run_status; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_status IS '실행 상태';


--
-- TOC entry 4435 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.run_start_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_start_date IS '실행 시작 일시';


--
-- TOC entry 4436 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.run_end_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_end_date IS '실행 종료 일시';


--
-- TOC entry 4437 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.run_note; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_note IS '실행 메모';


--
-- TOC entry 4438 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.create_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.create_date IS '생성 일시';


--
-- TOC entry 4439 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4440 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.update_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.update_date IS '수정 일시';


--
-- TOC entry 4441 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_ai_run.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_ai_run.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 360 (class 1259 OID 20709)
-- Name: card_bnft; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_bnft (
    card_id bigint NOT NULL,
    card_bnft_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_bnft'::text) NOT NULL,
    bnft_cd character varying(80) NOT NULL,
    bnft_nm text NOT NULL,
    bnft_type_cd character varying(20) NOT NULL,
    bnft_origin_cd character varying(20) NOT NULL,
    bnft_scope_cd character varying(20) NOT NULL,
    bnft_brand_opt_cds text[],
    bnft_cond_expr jsonb,
    rule_select_cd character varying(30),
    rule_list jsonb DEFAULT '[]'::jsonb NOT NULL,
    relation_list jsonb DEFAULT '[]'::jsonb NOT NULL,
    verification_status_cd character varying(25) NOT NULL,
    bnft_valid_from date,
    bnft_valid_to_excl date,
    bnft_rule_txt text,
    bnft_limit_txt text,
    bnft_search_txt text,
    bnft_embedding extensions.vector(1536),
    CONSTRAINT card_bnft_ck_1 CHECK (((((bnft_scope_cd)::text = 'PRODUCT'::text) AND (bnft_brand_opt_cds IS NULL)) OR (((bnft_scope_cd)::text <> 'PRODUCT'::text) AND (COALESCE(cardinality(bnft_brand_opt_cds), 0) > 0)))),
    CONSTRAINT card_bnft_ck_2 CHECK (db_pipeline.fn_valid_cond_expr(bnft_cond_expr)),
    CONSTRAINT card_bnft_ck_3 CHECK (db_pipeline.fn_valid_rule_list(rule_list, 'LOCAL'::text)),
    CONSTRAINT card_bnft_ck_4 CHECK (db_pipeline.fn_valid_relation_list(relation_list, (card_bnft_id)::text)),
    CONSTRAINT card_bnft_ck_5 CHECK ((((bnft_origin_cd)::text <> 'BRAND_SERVICE'::text) OR ((bnft_scope_cd)::text = 'BRAND'::text))),
    CONSTRAINT card_bnft_ck_6 CHECK (((bnft_valid_to_excl IS NULL) OR (bnft_valid_from IS NULL) OR (bnft_valid_to_excl > bnft_valid_from)))
);


--
-- TOC entry 4442 (class 0 OID 0)
-- Dependencies: 360
-- Name: TABLE card_bnft; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_bnft IS '카드 혜택';


--
-- TOC entry 4443 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.card_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.card_id IS '카드 아이디';


--
-- TOC entry 4444 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.card_bnft_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.card_bnft_id IS '혜택 아이디';


--
-- TOC entry 4445 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_cd IS '혜택 코드';


--
-- TOC entry 4446 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_nm; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_nm IS '혜택명';


--
-- TOC entry 4447 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_type_cd IS '혜택 유형';


--
-- TOC entry 4448 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_origin_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_origin_cd IS '혜택 출처';


--
-- TOC entry 4449 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_scope_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_scope_cd IS '혜택 적용 범위';


--
-- TOC entry 4450 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_brand_opt_cds; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_brand_opt_cds IS '적용 브랜드 선택지';


--
-- TOC entry 4451 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_cond_expr; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_cond_expr IS '혜택 적용 조건';


--
-- TOC entry 4452 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.rule_select_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.rule_select_cd IS '규칙 선택 방식';


--
-- TOC entry 4453 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.rule_list; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.rule_list IS '계산 규칙 목록';


--
-- TOC entry 4454 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.relation_list; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.relation_list IS '혜택 관계 목록';


--
-- TOC entry 4455 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.verification_status_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.verification_status_cd IS '혜택 검증 상태';


--
-- TOC entry 4456 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_valid_from; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_from IS '혜택 제공 시작일';


--
-- TOC entry 4457 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_valid_to_excl; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_to_excl IS '혜택 제공 종료일(미포함)';


--
-- TOC entry 4458 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_rule_txt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_rule_txt IS '공식 원문 근거에서 모은 혜택 계산 규칙 안내. 계산 확정값이 아니라 검토 대상 텍스트';


--
-- TOC entry 4459 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_limit_txt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_limit_txt IS '원문 근거에서 모은 혜택별 이용/금액 한도. 여러 풀의 근거를 혜택별로 중복 제거한 텍스트';


--
-- TOC entry 4460 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_search_txt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_search_txt IS '혜택 검색 텍스트. 임베딩 모델에 전달한 입력과 동일. 카드명 미포함';


--
-- TOC entry 4461 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_embedding; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_embedding IS '혜택 검색 텍스트 임베딩. 실제 적용 여부 판단에는 사용하지 않음';


--
-- TOC entry 379 (class 1259 OID 21668)
-- Name: seq_card_common; Type: SEQUENCE; Schema: db_pipeline; Owner: -
--

CREATE SEQUENCE db_pipeline.seq_card_common
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 4462 (class 0 OID 0)
-- Dependencies: 379
-- Name: SEQUENCE seq_card_common; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON SEQUENCE db_pipeline.seq_card_common IS '공통서비스 ID 발급';


--
-- TOC entry 381 (class 1259 OID 21670)
-- Name: card_common; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_common (
    card_common_id bigint DEFAULT nextval('db_pipeline.seq_card_common'::regclass) NOT NULL,
    common_cd character varying(80) NOT NULL,
    common_nm text NOT NULL,
    brand_cd character varying(40),
    service_grade_cd character varying(40),
    common_note text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


--
-- TOC entry 4463 (class 0 OID 0)
-- Dependencies: 381
-- Name: TABLE card_common; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_common IS '카드 브랜드 공통서비스 (실제 카드 상품 아님)';


--
-- TOC entry 4464 (class 0 OID 0)
-- Dependencies: 381
-- Name: COLUMN card_common.card_common_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common.card_common_id IS '공통서비스 아이디';


--
-- TOC entry 4465 (class 0 OID 0)
-- Dependencies: 381
-- Name: COLUMN card_common.common_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common.common_cd IS '공통서비스 업무 코드';


--
-- TOC entry 4466 (class 0 OID 0)
-- Dependencies: 381
-- Name: COLUMN card_common.common_nm; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common.common_nm IS '공통서비스명';


--
-- TOC entry 4467 (class 0 OID 0)
-- Dependencies: 381
-- Name: COLUMN card_common.brand_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common.brand_cd IS '국제 브랜드 코드';


--
-- TOC entry 4468 (class 0 OID 0)
-- Dependencies: 381
-- Name: COLUMN card_common.service_grade_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common.service_grade_cd IS '서비스 등급 코드';


--
-- TOC entry 383 (class 1259 OID 21687)
-- Name: card_common_bnft; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_common_bnft (
    card_common_id bigint NOT NULL,
    card_common_bnft_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_bnft'::text) NOT NULL,
    bnft_cd character varying(80) NOT NULL,
    bnft_nm text NOT NULL,
    bnft_type_cd character varying(20),
    service_type_cd character varying(20),
    bnft_rule_txt text,
    bnft_limit_txt text,
    bnft_valid_from date,
    bnft_valid_to_excl date,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    bnft_search_txt text,
    bnft_embedding extensions.vector(1536),
    CONSTRAINT card_common_bnft_date_check CHECK (((bnft_valid_to_excl IS NULL) OR (bnft_valid_from IS NULL) OR (bnft_valid_to_excl > bnft_valid_from)))
);


--
-- TOC entry 4469 (class 0 OID 0)
-- Dependencies: 383
-- Name: TABLE card_common_bnft; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_common_bnft IS '공통서비스 혜택';


--
-- TOC entry 4470 (class 0 OID 0)
-- Dependencies: 383
-- Name: COLUMN card_common_bnft.card_common_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.card_common_id IS '공통서비스 아이디 (논리 참조)';


--
-- TOC entry 4471 (class 0 OID 0)
-- Dependencies: 383
-- Name: COLUMN card_common_bnft.card_common_bnft_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.card_common_bnft_id IS '공통 혜택 아이디';


--
-- TOC entry 4472 (class 0 OID 0)
-- Dependencies: 383
-- Name: COLUMN card_common_bnft.bnft_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.bnft_cd IS '공통 혜택 업무 코드';


--
-- TOC entry 4473 (class 0 OID 0)
-- Dependencies: 383
-- Name: COLUMN card_common_bnft.bnft_nm; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.bnft_nm IS '공통 혜택명';


--
-- TOC entry 4474 (class 0 OID 0)
-- Dependencies: 383
-- Name: COLUMN card_common_bnft.service_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.service_type_cd IS '공통서비스 내 유형 (COMMON/선택서비스 등)';


--
-- TOC entry 4475 (class 0 OID 0)
-- Dependencies: 383
-- Name: COLUMN card_common_bnft.bnft_search_txt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.bnft_search_txt IS '공통 혜택 검색 텍스트. 임베딩 모델에 전달한 입력과 동일. 카드명 미포함';


--
-- TOC entry 4476 (class 0 OID 0)
-- Dependencies: 383
-- Name: COLUMN card_common_bnft.bnft_embedding; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.bnft_embedding IS '공통 혜택 검색 텍스트 임베딩. 카드 적용 관계는 card_common_bnft_apply로 확인';


--
-- TOC entry 384 (class 1259 OID 21700)
-- Name: card_common_bnft_apply; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_common_bnft_apply (
    card_common_id bigint NOT NULL,
    card_common_bnft_id character varying(20) NOT NULL,
    card_id bigint NOT NULL
);


--
-- TOC entry 4477 (class 0 OID 0)
-- Dependencies: 384
-- Name: TABLE card_common_bnft_apply; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_common_bnft_apply IS '공통 혜택과 실제 카드 상품 적용 관계';


--
-- TOC entry 4478 (class 0 OID 0)
-- Dependencies: 384
-- Name: COLUMN card_common_bnft_apply.card_common_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_bnft_apply.card_common_id IS '공통서비스 아이디 (논리 참조)';


--
-- TOC entry 4479 (class 0 OID 0)
-- Dependencies: 384
-- Name: COLUMN card_common_bnft_apply.card_common_bnft_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_bnft_apply.card_common_bnft_id IS '공통 혜택 아이디 (논리 참조)';


--
-- TOC entry 4480 (class 0 OID 0)
-- Dependencies: 384
-- Name: COLUMN card_common_bnft_apply.card_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_bnft_apply.card_id IS '실제 카드 상품 아이디 (논리 참조 CARD_PRODUCT)';


--
-- TOC entry 382 (class 1259 OID 21682)
-- Name: card_common_doc; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_common_doc (
    card_common_id bigint NOT NULL,
    card_doc_id character varying(20) NOT NULL
);


--
-- TOC entry 4481 (class 0 OID 0)
-- Dependencies: 382
-- Name: TABLE card_common_doc; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_common_doc IS '공통서비스별 원천 문서 관계';


--
-- TOC entry 4482 (class 0 OID 0)
-- Dependencies: 382
-- Name: COLUMN card_common_doc.card_common_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_doc.card_common_id IS '공통서비스 아이디 (논리 참조)';


--
-- TOC entry 4483 (class 0 OID 0)
-- Dependencies: 382
-- Name: COLUMN card_common_doc.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_common_doc.card_doc_id IS '원천 문서 아이디 (논리 참조 CARD_DOC)';


--
-- TOC entry 361 (class 1259 OID 20795)
-- Name: card_doc; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_doc (
    card_doc_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_doc'::text) NOT NULL,
    doc_cd character varying(50) NOT NULL,
    doc_family_cd character varying(100),
    doc_type_cd character varying(20) DEFAULT 'PRODUCT_GUIDE'::character varying NOT NULL,
    doc_title text NOT NULL,
    doc_source_url text,
    doc_file_nm text NOT NULL,
    doc_file_size bigint,
    doc_sha256 character varying(64) NOT NULL,
    doc_page_cnt smallint,
    doc_review_no text,
    doc_review_date date,
    doc_release_date date,
    doc_collect_date timestamp with time zone NOT NULL,
    doc_version_no smallint DEFAULT 1 NOT NULL,
    doc_status character varying(20) DEFAULT 'ACTIVE'::character varying NOT NULL,
    doc_note text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT card_doc_doc_page_cnt_check CHECK (((doc_page_cnt IS NULL) OR (doc_page_cnt > 0))),
    CONSTRAINT card_doc_doc_sha256_check CHECK (((doc_sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT card_doc_doc_version_no_check CHECK ((doc_version_no > 0)),
    CONSTRAINT card_doc_family_cd_check CHECK (((doc_family_cd IS NULL) OR ((doc_family_cd)::text ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]*$'::text)))
);


--
-- TOC entry 4484 (class 0 OID 0)
-- Dependencies: 361
-- Name: TABLE card_doc; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_doc IS '카드 관련 문서';


--
-- TOC entry 4485 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.card_doc_id IS '문서 아이디';


--
-- TOC entry 4486 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_cd IS '문서 코드';


--
-- TOC entry 4487 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_family_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_family_cd IS '문서 계열 코드';


--
-- TOC entry 4488 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_type_cd IS '문서 유형';


--
-- TOC entry 4489 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_title; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_title IS '문서 제목';


--
-- TOC entry 4490 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_source_url; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_source_url IS '문서 출처 URL';


--
-- TOC entry 4491 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_file_nm; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_file_nm IS '파일명';


--
-- TOC entry 4492 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_file_size; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_file_size IS '파일 크기';


--
-- TOC entry 4493 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_sha256; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_sha256 IS '파일 해시';


--
-- TOC entry 4494 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_page_cnt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_page_cnt IS '페이지 수';


--
-- TOC entry 4495 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_review_no; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_review_no IS '심의 번호';


--
-- TOC entry 4496 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_review_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_review_date IS '심의일';


--
-- TOC entry 4497 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_release_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_release_date IS '문서 발행일';


--
-- TOC entry 4498 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_collect_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_collect_date IS '수집 일시';


--
-- TOC entry 4499 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_version_no; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_version_no IS '문서 버전 번호';


--
-- TOC entry 4500 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_status; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_status IS '문서 상태';


--
-- TOC entry 4501 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.doc_note; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_note IS '문서 메모';


--
-- TOC entry 4502 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.create_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.create_date IS '생성 일시';


--
-- TOC entry 4503 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4504 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.update_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.update_date IS '수정 일시';


--
-- TOC entry 4505 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_doc.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 363 (class 1259 OID 20826)
-- Name: card_doc_chunk; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_doc_chunk (
    card_doc_id character varying(20) NOT NULL,
    page_no smallint NOT NULL,
    card_doc_chunk_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_doc_chunk'::text) NOT NULL,
    chunk_seq integer NOT NULL,
    chunk_section_nm text,
    chunk_type_cd character varying(20) DEFAULT 'BODY'::character varying NOT NULL,
    chunk_start_pos integer NOT NULL,
    chunk_end_pos integer NOT NULL,
    chunk_raw_txt text NOT NULL,
    chunk_clean_txt text,
    chunk_status character varying(20) DEFAULT 'RAW'::character varying NOT NULL,
    chunk_split_rule_ver character varying(50) NOT NULL,
    chunk_clean_rule_ver character varying(50),
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT card_doc_chunk_check CHECK (((chunk_start_pos >= 1) AND (chunk_end_pos >= chunk_start_pos))),
    CONSTRAINT card_doc_chunk_check1 CHECK ((((chunk_status)::text <> 'CLEANED'::text) OR ((chunk_clean_txt IS NOT NULL) AND (chunk_clean_rule_ver IS NOT NULL)))),
    CONSTRAINT card_doc_chunk_chunk_seq_check CHECK ((chunk_seq > 0))
);


--
-- TOC entry 4506 (class 0 OID 0)
-- Dependencies: 363
-- Name: TABLE card_doc_chunk; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_doc_chunk IS '문서 청크';


--
-- TOC entry 4507 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.card_doc_id IS '문서 아이디';


--
-- TOC entry 4508 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.page_no; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.page_no IS '페이지 번호';


--
-- TOC entry 4509 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.card_doc_chunk_id IS '청크 아이디';


--
-- TOC entry 4510 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.chunk_seq; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_seq IS '청크 순번';


--
-- TOC entry 4511 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.chunk_section_nm; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_section_nm IS '절 제목';


--
-- TOC entry 4512 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.chunk_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_type_cd IS '청크 유형';


--
-- TOC entry 4513 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.chunk_start_pos; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_start_pos IS '청크 시작 위치';


--
-- TOC entry 4514 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.chunk_end_pos; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_end_pos IS '청크 종료 위치';


--
-- TOC entry 4515 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.chunk_raw_txt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_raw_txt IS '청크 원문';


--
-- TOC entry 4516 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.chunk_clean_txt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_clean_txt IS '청크 정제문';


--
-- TOC entry 4517 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.chunk_status; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_status IS '청크 상태';


--
-- TOC entry 4518 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.chunk_split_rule_ver; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_split_rule_ver IS '청크 분리 규칙 버전';


--
-- TOC entry 4519 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.chunk_clean_rule_ver; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_clean_rule_ver IS '청크 정제 규칙 버전';


--
-- TOC entry 4520 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.create_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.create_date IS '생성 일시';


--
-- TOC entry 4521 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4522 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.update_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.update_date IS '수정 일시';


--
-- TOC entry 4523 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_chunk.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 362 (class 1259 OID 20816)
-- Name: card_doc_page; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_doc_page (
    card_doc_id character varying(20) NOT NULL,
    page_no smallint NOT NULL,
    page_raw_txt text NOT NULL,
    page_char_cnt integer NOT NULL,
    page_txt_sha256 character varying(64) NOT NULL,
    page_layer_cd character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    page_extractor_nm character varying(50) NOT NULL,
    page_extractor_ver character varying(50),
    page_note text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT card_doc_page_page_char_cnt_check CHECK ((page_char_cnt >= 0)),
    CONSTRAINT card_doc_page_page_no_check CHECK ((page_no > 0))
);


--
-- TOC entry 4524 (class 0 OID 0)
-- Dependencies: 362
-- Name: TABLE card_doc_page; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_doc_page IS '문서 페이지';


--
-- TOC entry 4525 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.card_doc_id IS '문서 아이디';


--
-- TOC entry 4526 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.page_no; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_no IS '페이지 번호';


--
-- TOC entry 4527 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.page_raw_txt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_raw_txt IS '페이지 원문';


--
-- TOC entry 4528 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.page_char_cnt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_char_cnt IS '페이지 문자 수';


--
-- TOC entry 4529 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.page_txt_sha256; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_txt_sha256 IS '페이지 원문 해시';


--
-- TOC entry 4530 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.page_layer_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_layer_cd IS '텍스트 레이어 유형';


--
-- TOC entry 4531 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.page_extractor_nm; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_extractor_nm IS '추출기명';


--
-- TOC entry 4532 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.page_extractor_ver; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_extractor_ver IS '추출기 버전';


--
-- TOC entry 4533 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.page_note; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_note IS '페이지 메모';


--
-- TOC entry 4534 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.create_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.create_date IS '생성 일시';


--
-- TOC entry 4535 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4536 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.update_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.update_date IS '수정 일시';


--
-- TOC entry 4537 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc_page.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_doc_page.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 386 (class 1259 OID 21778)
-- Name: card_evidence_link; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_evidence_link (
    card_doc_id character varying(20) NOT NULL,
    page_no smallint NOT NULL,
    card_doc_chunk_id character varying(20) NOT NULL,
    evidence_id character varying(20) NOT NULL,
    card_id bigint NOT NULL,
    evidence_link_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_evidence_link'::text) NOT NULL,
    card_bnft_id character varying(20),
    ev_subject_cd character varying(10) NOT NULL,
    rule_key character varying(40),
    relation_key character varying(40),
    ev_item_cd character varying(10) DEFAULT 'SELF'::character varying NOT NULL,
    ev_item_key character varying(100) DEFAULT '-'::character varying NOT NULL,
    CONSTRAINT card_evidence_link_ck_1 CHECK ((((ev_item_cd)::text = 'SELF'::text) = ((ev_item_key)::text = '-'::text))),
    CONSTRAINT card_evidence_link_ck_2 CHECK (
CASE ev_subject_cd
    WHEN 'CARD'::text THEN (num_nonnulls(card_bnft_id, rule_key, relation_key) = 0)
    WHEN 'BNFT'::text THEN ((card_bnft_id IS NOT NULL) AND (num_nonnulls(rule_key, relation_key) = 0))
    WHEN 'RULE'::text THEN ((card_bnft_id IS NOT NULL) AND (rule_key IS NOT NULL) AND (relation_key IS NULL))
    WHEN 'REL'::text THEN ((card_bnft_id IS NOT NULL) AND (relation_key IS NOT NULL) AND (rule_key IS NULL))
    ELSE false
END)
);


--
-- TOC entry 4538 (class 0 OID 0)
-- Dependencies: 386
-- Name: TABLE card_evidence_link; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_evidence_link IS '카드 근거 관계';


--
-- TOC entry 4539 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.card_doc_id IS '문서 아이디';


--
-- TOC entry 4540 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.page_no; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.page_no IS '페이지 번호';


--
-- TOC entry 4541 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.card_doc_chunk_id IS '청크 아이디';


--
-- TOC entry 4542 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.evidence_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.evidence_id IS '원문 근거 아이디';


--
-- TOC entry 4543 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.card_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.card_id IS '카드 아이디';


--
-- TOC entry 4544 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.evidence_link_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.evidence_link_id IS '근거 연결 아이디';


--
-- TOC entry 4545 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.card_bnft_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.card_bnft_id IS '혜택 아이디';


--
-- TOC entry 4546 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.ev_subject_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.ev_subject_cd IS '근거 대상 유형';


--
-- TOC entry 4547 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.rule_key; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.rule_key IS '규칙 키';


--
-- TOC entry 4548 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.relation_key; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.relation_key IS '혜택 관계 키';


--
-- TOC entry 4549 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.ev_item_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.ev_item_cd IS '근거 항목 유형';


--
-- TOC entry 4550 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_evidence_link.ev_item_key; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.ev_item_key IS '근거 항목 키';


--
-- TOC entry 367 (class 1259 OID 20873)
-- Name: card_excl_item; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_excl_item (
    card_excl_item_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_excl_item'::text) NOT NULL,
    issuer text NOT NULL,
    excl_item_nm text NOT NULL,
    excl_concept_cd character varying(50),
    excl_item_desc text,
    excl_alias_nms text[] DEFAULT '{}'::text[] NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


--
-- TOC entry 4551 (class 0 OID 0)
-- Dependencies: 367
-- Name: TABLE card_excl_item; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_excl_item IS '제외 항목 사전(검토중 일단 보류)';


--
-- TOC entry 4552 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_excl_item.card_excl_item_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_excl_item.card_excl_item_id IS '제외 항목 아이디';


--
-- TOC entry 4553 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_excl_item.issuer; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_excl_item.issuer IS '카드사';


--
-- TOC entry 4554 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_excl_item.excl_item_nm; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_nm IS '제외 항목명';


--
-- TOC entry 4555 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_excl_item.excl_concept_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_concept_cd IS '제외 분류 개념';


--
-- TOC entry 4556 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_excl_item.excl_item_desc; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_desc IS '제외 항목 설명';


--
-- TOC entry 4557 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_excl_item.excl_alias_nms; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_alias_nms IS '제외 항목 별칭';


--
-- TOC entry 4558 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_excl_item.create_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_excl_item.create_date IS '생성 일시';


--
-- TOC entry 4559 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_excl_item.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_excl_item.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4560 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_excl_item.update_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_excl_item.update_date IS '수정 일시';


--
-- TOC entry 4561 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_excl_item.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_excl_item.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 366 (class 1259 OID 20861)
-- Name: card_extr_stg; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_extr_stg (
    card_ai_run_id character varying(20) NOT NULL,
    card_doc_id character varying(20) NOT NULL,
    page_no smallint NOT NULL,
    card_doc_chunk_id character varying(20) NOT NULL,
    call_seq smallint NOT NULL,
    card_extr_stg_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_extr_stg'::text) NOT NULL,
    stg_item_seq smallint NOT NULL,
    card_id bigint,
    stg_kind_cd character varying(20) NOT NULL,
    stg_parent_card_extr_stg_id character varying(20),
    stg_raw_item jsonb NOT NULL,
    stg_normalized_item jsonb,
    stg_evidence_txt text NOT NULL,
    stg_evidence_start_pos integer,
    stg_evidence_end_pos integer,
    card_excl_item_id character varying(20),
    stg_sql_check_cd character varying(30),
    stg_ai_vrfy_cd character varying(20),
    stg_ai_vrfy_card_ai_run_id character varying(20),
    stg_status character varying(20) DEFAULT 'PENDING_REVIEW'::character varying NOT NULL,
    stg_review_note text,
    stg_approved_date timestamp with time zone,
    stg_approved_user_id character varying(50),
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT card_extr_stg_check CHECK ((((stg_evidence_start_pos IS NULL) AND (stg_evidence_end_pos IS NULL)) OR ((stg_evidence_start_pos >= 1) AND (stg_evidence_end_pos >= stg_evidence_start_pos)))),
    CONSTRAINT card_extr_stg_check1 CHECK ((((stg_status)::text <> ALL (ARRAY[('AUTO_APPROVED'::character varying)::text, ('MANUAL_APPROVED'::character varying)::text])) OR ((stg_normalized_item IS NOT NULL) AND (NOT ((stg_sql_check_cd)::text IS DISTINCT FROM 'OK'::text)) AND (stg_evidence_start_pos IS NOT NULL) AND (stg_evidence_end_pos IS NOT NULL) AND (btrim(stg_evidence_txt) <> ''::text)))),
    CONSTRAINT card_extr_stg_stg_item_seq_check CHECK ((stg_item_seq > 0))
);


--
-- TOC entry 4562 (class 0 OID 0)
-- Dependencies: 366
-- Name: TABLE card_extr_stg; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_extr_stg IS 'AI 추출 항목';


--
-- TOC entry 4563 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_ai_run_id IS 'AI 실행 아이디';


--
-- TOC entry 4564 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_doc_id IS '문서 아이디';


--
-- TOC entry 4565 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.page_no; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.page_no IS '페이지 번호';


--
-- TOC entry 4566 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_doc_chunk_id IS '청크 아이디';


--
-- TOC entry 4567 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.call_seq; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.call_seq IS '호출 순번';


--
-- TOC entry 4568 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.card_extr_stg_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_extr_stg_id IS '추출 항목 아이디';


--
-- TOC entry 4569 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_item_seq; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_item_seq IS '추출 항목 순번';


--
-- TOC entry 4570 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.card_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_id IS '카드 아이디(NULL이면 특정 카드에 연결되지 않은 후보)';


--
-- TOC entry 4571 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_kind_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_kind_cd IS '추출 항목 종류';


--
-- TOC entry 4572 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_parent_card_extr_stg_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_parent_card_extr_stg_id IS '상위 추출 항목 아이디';


--
-- TOC entry 4573 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_raw_item; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_raw_item IS '추출 원본';


--
-- TOC entry 4574 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_normalized_item; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_normalized_item IS '정제 항목';


--
-- TOC entry 4575 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_evidence_txt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_txt IS '추출 근거 문장';


--
-- TOC entry 4576 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_evidence_start_pos; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_start_pos IS '근거 시작 위치';


--
-- TOC entry 4577 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_evidence_end_pos; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_end_pos IS '근거 종료 위치';


--
-- TOC entry 4578 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.card_excl_item_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_excl_item_id IS '제외 항목 아이디';


--
-- TOC entry 4579 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_sql_check_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_sql_check_cd IS 'SQL 검증 결과';


--
-- TOC entry 4580 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_ai_vrfy_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_ai_vrfy_cd IS 'AI 검증 결과';


--
-- TOC entry 4581 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_ai_vrfy_card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_ai_vrfy_card_ai_run_id IS 'AI 검증 실행 아이디';


--
-- TOC entry 4582 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_status; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_status IS '검토 상태';


--
-- TOC entry 4583 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_review_note; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_review_note IS '검토 메모';


--
-- TOC entry 4584 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_approved_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_approved_date IS '승인 일시';


--
-- TOC entry 4585 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.stg_approved_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_approved_user_id IS '승인 사용자 아이디';


--
-- TOC entry 4586 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.create_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.create_date IS '생성 일시';


--
-- TOC entry 4587 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4588 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.update_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.update_date IS '수정 일시';


--
-- TOC entry 4589 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_extr_stg.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 354 (class 1259 OID 20645)
-- Name: seq_card_product; Type: SEQUENCE; Schema: db_pipeline; Owner: -
--

CREATE SEQUENCE db_pipeline.seq_card_product
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- TOC entry 4590 (class 0 OID 0)
-- Dependencies: 354
-- Name: SEQUENCE seq_card_product; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON SEQUENCE db_pipeline.seq_card_product IS 'card_product.card_id bigint 발급; 원본 백업에는 상품 마스터 시퀀스가 없음';


--
-- TOC entry 358 (class 1259 OID 20665)
-- Name: card_product; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_product (
    card_id bigint DEFAULT nextval('db_pipeline.seq_card_product'::regclass) NOT NULL,
    product_cd character varying(80) NOT NULL,
    product_nm text NOT NULL,
    issuer character varying(50) NOT NULL,
    card_kind_cd character varying(10) NOT NULL,
    product_status_cd character varying(20) DEFAULT 'ACTIVE'::character varying NOT NULL,
    launched_on date,
    discontinued_on date,
    brand_opt_list jsonb DEFAULT '[]'::jsonb NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    card_cond_expr jsonb,
    card_cond_status_cd character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    CONSTRAINT card_product_brand_opt_list_check CHECK (db_pipeline.fn_valid_brand_opt_list(brand_opt_list)),
    CONSTRAINT card_product_card_cond_expr_check CHECK (db_pipeline.fn_valid_cond_expr(card_cond_expr)),
    CONSTRAINT card_product_dates_check CHECK (((discontinued_on IS NULL) OR (launched_on IS NULL) OR (discontinued_on >= launched_on)))
);


--
-- TOC entry 4591 (class 0 OID 0)
-- Dependencies: 358
-- Name: TABLE card_product; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_product IS '카드 상품';


--
-- TOC entry 4592 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.card_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.card_id IS '카드 아이디';


--
-- TOC entry 4593 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.product_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.product_cd IS '상품 코드';


--
-- TOC entry 4594 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.product_nm; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.product_nm IS '상품명';


--
-- TOC entry 4595 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.issuer; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.issuer IS '카드사';


--
-- TOC entry 4596 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.card_kind_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.card_kind_cd IS '카드 구분';


--
-- TOC entry 4597 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.product_status_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.product_status_cd IS '상품 상태';


--
-- TOC entry 4598 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.launched_on; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.launched_on IS '출시일';


--
-- TOC entry 4599 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.discontinued_on; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.discontinued_on IS '판매 중단일';


--
-- TOC entry 4600 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.brand_opt_list; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.brand_opt_list IS '브랜드 선택지 목록';


--
-- TOC entry 4601 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.create_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.create_date IS '생성 일시';


--
-- TOC entry 4602 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4603 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.update_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.update_date IS '수정 일시';


--
-- TOC entry 4604 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 4605 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.card_cond_expr; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.card_cond_expr IS '카드 공통 조건';


--
-- TOC entry 4606 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.card_cond_status_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product.card_cond_status_cd IS '카드 공통 조건 상태';


--
-- TOC entry 359 (class 1259 OID 20696)
-- Name: card_product_doc; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_product_doc (
    card_id bigint NOT NULL,
    card_doc_id character varying(20) NOT NULL,
    doc_role_cd character varying(20) NOT NULL,
    brand_opt_cds text[],
    approval_status_cd character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    applicability_basis_txt text NOT NULL,
    approval_note text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT card_product_doc_approved_check CHECK ((((approval_status_cd)::text <> 'APPROVED'::text) OR (length(TRIM(BOTH FROM applicability_basis_txt)) > 0))),
    CONSTRAINT card_product_doc_brand_check CHECK ((((doc_role_cd)::text <> 'BRAND_SERVICE'::text) OR (COALESCE(cardinality(brand_opt_cds), 0) > 0)))
);


--
-- TOC entry 4607 (class 0 OID 0)
-- Dependencies: 359
-- Name: TABLE card_product_doc; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_product_doc IS '상품별 문서 관계';


--
-- TOC entry 4608 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.card_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product_doc.card_id IS '카드 아이디';


--
-- TOC entry 4609 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product_doc.card_doc_id IS '문서 아이디';


--
-- TOC entry 4610 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.doc_role_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product_doc.doc_role_cd IS '문서 역할';


--
-- TOC entry 4611 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.brand_opt_cds; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product_doc.brand_opt_cds IS '적용 브랜드 선택지';


--
-- TOC entry 4612 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.approval_status_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product_doc.approval_status_cd IS '승인 상태';


--
-- TOC entry 4613 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.applicability_basis_txt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product_doc.applicability_basis_txt IS '적용 근거';


--
-- TOC entry 4614 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.approval_note; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product_doc.approval_note IS '승인 메모';


--
-- TOC entry 4615 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.create_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product_doc.create_date IS '생성 일시';


--
-- TOC entry 4616 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product_doc.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4617 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.update_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product_doc.update_date IS '수정 일시';


--
-- TOC entry 4618 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_product_doc.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 385 (class 1259 OID 21754)
-- Name: card_source_evidence; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.card_source_evidence (
    card_doc_id character varying(20) NOT NULL,
    page_no smallint NOT NULL,
    card_doc_chunk_id character varying(20) NOT NULL,
    evidence_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_source_evidence'::text) NOT NULL,
    card_extr_stg_id character varying(20),
    quote_txt text NOT NULL,
    start_pos integer,
    end_pos integer,
    approval_status_cd character varying(20) NOT NULL,
    CONSTRAINT card_source_evidence_ck_1 CHECK (((start_pos IS NULL) OR (start_pos > 0))),
    CONSTRAINT card_source_evidence_ck_2 CHECK (((end_pos IS NULL) OR (start_pos IS NULL) OR (end_pos >= start_pos)))
);


--
-- TOC entry 4619 (class 0 OID 0)
-- Dependencies: 385
-- Name: TABLE card_source_evidence; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.card_source_evidence IS '원문 근거';


--
-- TOC entry 4620 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_source_evidence.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.card_doc_id IS '문서 아이디';


--
-- TOC entry 4621 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_source_evidence.page_no; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.page_no IS '페이지 번호';


--
-- TOC entry 4622 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_source_evidence.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.card_doc_chunk_id IS '청크 아이디';


--
-- TOC entry 4623 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_source_evidence.evidence_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.evidence_id IS '원문 근거 아이디';


--
-- TOC entry 4624 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_source_evidence.card_extr_stg_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.card_extr_stg_id IS '추출 항목 아이디';


--
-- TOC entry 4625 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_source_evidence.quote_txt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.quote_txt IS '원문 인용 문장';


--
-- TOC entry 4626 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_source_evidence.start_pos; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.start_pos IS '인용 시작 위치';


--
-- TOC entry 4627 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_source_evidence.end_pos; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.end_pos IS '인용 종료 위치';


--
-- TOC entry 4628 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_source_evidence.approval_status_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.approval_status_cd IS '승인 상태';


--
-- TOC entry 357 (class 1259 OID 20656)
-- Name: common_cd; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.common_cd (
    common_code_grp_id character varying(20) NOT NULL,
    common_cd character varying(40) NOT NULL,
    common_cd_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    common_cd_desc text
);


--
-- TOC entry 4629 (class 0 OID 0)
-- Dependencies: 357
-- Name: TABLE common_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.common_cd IS '공통코드';


--
-- TOC entry 4630 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.common_code_grp_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_cd.common_code_grp_id IS '공통코드 그룹 아이디';


--
-- TOC entry 4631 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.common_cd; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_cd.common_cd IS '공통코드';


--
-- TOC entry 4632 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.common_cd_nm; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_cd.common_cd_nm IS '공통코드명';


--
-- TOC entry 4633 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.create_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_cd.create_date IS '생성 일시';


--
-- TOC entry 4634 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_cd.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4635 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.update_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_cd.update_date IS '수정 일시';


--
-- TOC entry 4636 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_cd.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 4637 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.common_cd_desc; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_cd.common_cd_desc IS '공통코드 상세 설명(업무 의미, 적용 기준)';


--
-- TOC entry 356 (class 1259 OID 20647)
-- Name: common_code_grp; Type: TABLE; Schema: db_pipeline; Owner: -
--

CREATE TABLE db_pipeline.common_code_grp (
    common_code_grp_id character varying(20) NOT NULL,
    common_code_grp_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    common_code_grp_desc text
);


--
-- TOC entry 4638 (class 0 OID 0)
-- Dependencies: 356
-- Name: TABLE common_code_grp; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON TABLE db_pipeline.common_code_grp IS '공통코드 그룹';


--
-- TOC entry 4639 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.common_code_grp_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_code_grp.common_code_grp_id IS '공통코드 그룹 아이디';


--
-- TOC entry 4640 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.common_code_grp_nm; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_code_grp.common_code_grp_nm IS '공통코드 그룹명';


--
-- TOC entry 4641 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.create_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_code_grp.create_date IS '생성 일시';


--
-- TOC entry 4642 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_code_grp.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4643 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.update_date; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_code_grp.update_date IS '수정 일시';


--
-- TOC entry 4644 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_code_grp.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 4645 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.common_code_grp_desc; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON COLUMN db_pipeline.common_code_grp.common_code_grp_desc IS '공통코드 그룹 상세 설명(목적, 사용 범위, 업무 의미)';


--
-- TOC entry 347 (class 1259 OID 20634)
-- Name: seq_card_ai_run; Type: SEQUENCE; Schema: db_pipeline; Owner: -
--

CREATE SEQUENCE db_pipeline.seq_card_ai_run
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4646 (class 0 OID 0)
-- Dependencies: 347
-- Name: SEQUENCE seq_card_ai_run; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON SEQUENCE db_pipeline.seq_card_ai_run IS 'AI 실행 ID 발급';


--
-- TOC entry 348 (class 1259 OID 20635)
-- Name: seq_card_bnft; Type: SEQUENCE; Schema: db_pipeline; Owner: -
--

CREATE SEQUENCE db_pipeline.seq_card_bnft
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4647 (class 0 OID 0)
-- Dependencies: 348
-- Name: SEQUENCE seq_card_bnft; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON SEQUENCE db_pipeline.seq_card_bnft IS '확정 혜택 ID 발급';


--
-- TOC entry 380 (class 1259 OID 21669)
-- Name: seq_card_common_bnft; Type: SEQUENCE; Schema: db_pipeline; Owner: -
--

CREATE SEQUENCE db_pipeline.seq_card_common_bnft
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1;


--
-- TOC entry 4648 (class 0 OID 0)
-- Dependencies: 380
-- Name: SEQUENCE seq_card_common_bnft; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON SEQUENCE db_pipeline.seq_card_common_bnft IS '공통 혜택 ID 발급';


--
-- TOC entry 349 (class 1259 OID 20636)
-- Name: seq_card_doc; Type: SEQUENCE; Schema: db_pipeline; Owner: -
--

CREATE SEQUENCE db_pipeline.seq_card_doc
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4649 (class 0 OID 0)
-- Dependencies: 349
-- Name: SEQUENCE seq_card_doc; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON SEQUENCE db_pipeline.seq_card_doc IS '원본 문서 ID 발급';


--
-- TOC entry 350 (class 1259 OID 20637)
-- Name: seq_card_doc_chunk; Type: SEQUENCE; Schema: db_pipeline; Owner: -
--

CREATE SEQUENCE db_pipeline.seq_card_doc_chunk
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4650 (class 0 OID 0)
-- Dependencies: 350
-- Name: SEQUENCE seq_card_doc_chunk; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON SEQUENCE db_pipeline.seq_card_doc_chunk IS '문서 청크 ID 발급';


--
-- TOC entry 355 (class 1259 OID 20646)
-- Name: seq_card_evidence_link; Type: SEQUENCE; Schema: db_pipeline; Owner: -
--

CREATE SEQUENCE db_pipeline.seq_card_evidence_link
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4651 (class 0 OID 0)
-- Dependencies: 355
-- Name: SEQUENCE seq_card_evidence_link; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON SEQUENCE db_pipeline.seq_card_evidence_link IS 'card_evidence_link.evidence_link_id 로컬 업무 ID 발급';


--
-- TOC entry 351 (class 1259 OID 20638)
-- Name: seq_card_excl_item; Type: SEQUENCE; Schema: db_pipeline; Owner: -
--

CREATE SEQUENCE db_pipeline.seq_card_excl_item
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4652 (class 0 OID 0)
-- Dependencies: 351
-- Name: SEQUENCE seq_card_excl_item; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON SEQUENCE db_pipeline.seq_card_excl_item IS '표준 제외 항목 ID 발급';


--
-- TOC entry 352 (class 1259 OID 20639)
-- Name: seq_card_extr_stg; Type: SEQUENCE; Schema: db_pipeline; Owner: -
--

CREATE SEQUENCE db_pipeline.seq_card_extr_stg
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4653 (class 0 OID 0)
-- Dependencies: 352
-- Name: SEQUENCE seq_card_extr_stg; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON SEQUENCE db_pipeline.seq_card_extr_stg IS 'AI 추출 staging ID 발급';


--
-- TOC entry 353 (class 1259 OID 20644)
-- Name: seq_card_source_evidence; Type: SEQUENCE; Schema: db_pipeline; Owner: -
--

CREATE SEQUENCE db_pipeline.seq_card_source_evidence
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4654 (class 0 OID 0)
-- Dependencies: 353
-- Name: SEQUENCE seq_card_source_evidence; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON SEQUENCE db_pipeline.seq_card_source_evidence IS 'card_source_evidence.evidence_id 로컬 업무 ID 발급';


--
-- TOC entry 377 (class 1259 OID 21647)
-- Name: v_card_bnft_rel; Type: VIEW; Schema: db_pipeline; Owner: -
--

CREATE VIEW db_pipeline.v_card_bnft_rel AS
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


--
-- TOC entry 4655 (class 0 OID 0)
-- Dependencies: 377
-- Name: VIEW v_card_bnft_rel; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON VIEW db_pipeline.v_card_bnft_rel IS '혜택 관계를 행으로 복원. MUTUALLY_EXCLUSIVE는 reverse_yn=true 행을 더해 양방향 제공. 저장 행 조회는 reverse_yn=false';


--
-- TOC entry 369 (class 1259 OID 21577)
-- Name: v_card_rule; Type: VIEW; Schema: db_pipeline; Owner: -
--

CREATE VIEW db_pipeline.v_card_rule AS
 SELECT b.card_id,
    b.card_bnft_id,
    (r.value ->> 'rule_key'::text) AS rule_key,
    r.ord AS rule_seq,
    NULLIF((r.value -> 'cond_expr'::text), 'null'::jsonb) AS cond_expr,
    (db_pipeline.fn_cond_spend_bound(NULLIF((r.value -> 'cond_expr'::text), 'null'::jsonb), 'cond_min_amt'::text))::numeric(18,2) AS spend_min_amt,
    (db_pipeline.fn_cond_spend_bound(NULLIF((r.value -> 'cond_expr'::text), 'null'::jsonb), 'cond_max_amt_excl'::text))::numeric(18,2) AS spend_max_amt_excl,
    COALESCE((r.value -> 'target_list'::text), '[]'::jsonb) AS target_list,
    (r.value ->> 'predicate_state_cd'::text) AS predicate_state_cd,
    (r.value ->> 'calc_method_cd'::text) AS calc_method_cd,
    ((r.value ->> 'method_ver'::text))::integer AS method_ver,
    ((r.value ->> 'value_num'::text))::numeric(18,4) AS value_num,
    (r.value ->> 'value_unit_cd'::text) AS value_unit_cd,
    (r.value ->> 'payout_unit_cd'::text) AS payout_unit_cd,
    ((r.value ->> 'basis_amt'::text))::numeric(18,2) AS basis_amt,
    NULLIF((r.value -> 'calc_params'::text), 'null'::jsonb) AS calc_params,
    ((r.value ->> 'rule_priority'::text))::integer AS rule_priority,
    (r.value ->> 'rule_status_cd'::text) AS rule_status_cd
   FROM (db_pipeline.card_bnft b
     CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) WITH ORDINALITY r(value, ord));


--
-- TOC entry 4656 (class 0 OID 0)
-- Dependencies: 369
-- Name: VIEW v_card_rule; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON VIEW db_pipeline.v_card_rule IS '상품 계산 규칙을 행으로 복원. V5 card_bnft_rule 조회 대체';


--
-- TOC entry 371 (class 1259 OID 21596)
-- Name: v_card_bnft_rule_effective; Type: VIEW; Schema: db_pipeline; Owner: -
--

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
   FROM (db_pipeline.card_bnft b
     JOIN db_pipeline.v_card_rule r ON (((r.card_id = b.card_id) AND ((r.card_bnft_id)::text = (b.card_bnft_id)::text))));


--
-- TOC entry 4657 (class 0 OID 0)
-- Dependencies: 371
-- Name: VIEW v_card_bnft_rule_effective; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON VIEW db_pipeline.v_card_bnft_rule_effective IS '혜택과 계산 규칙의 단일 출력. 제공 기간은 걸러내지 않으므로 조회 기준일로 판정. 값은 정책 후보이며 거래별 보상액이 아님';


--
-- TOC entry 368 (class 1259 OID 20941)
-- Name: v_card_brand_opt; Type: VIEW; Schema: db_pipeline; Owner: -
--

CREATE VIEW db_pipeline.v_card_brand_opt AS
 SELECT p.card_id,
    p.product_cd,
    p.product_nm,
    (o.value ->> 'brand_opt_cd'::text) AS brand_opt_cd,
    (o.value ->> 'brand_opt_nm'::text) AS brand_opt_nm,
    (o.value ->> 'brand_cd'::text) AS brand_cd,
    (o.value ->> 'service_grade_cd'::text) AS service_grade_cd,
    (o.value ->> 'service_type_cd'::text) AS service_type_cd,
    (o.value ->> 'brand_opt_status_cd'::text) AS brand_opt_status_cd
   FROM (db_pipeline.card_product p
     CROSS JOIN LATERAL jsonb_array_elements(p.brand_opt_list) o(value));


--
-- TOC entry 4658 (class 0 OID 0)
-- Dependencies: 368
-- Name: VIEW v_card_brand_opt; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON VIEW db_pipeline.v_card_brand_opt IS '상품별 브랜드 선택지를 행으로 복원';


--
-- TOC entry 378 (class 1259 OID 21652)
-- Name: v_card_cond_atom; Type: VIEW; Schema: db_pipeline; Owner: -
--

CREATE VIEW db_pipeline.v_card_cond_atom AS
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
    (a.value ->> 'predicate_method_cd'::text) AS predicate_method_cd,
    ((a.value ->> 'predicate_method_ver'::text))::integer AS predicate_method_ver,
    (a.value -> 'cond_params'::text) AS cond_params,
    (a.value ->> 'card_excl_item_id'::text) AS card_excl_item_id,
    (a.value ->> 'excl_raw_txt'::text) AS excl_raw_txt,
    (a.value ->> 'cond_raw_txt'::text) AS cond_raw_txt,
    (a.value ->> 'link_role_cd'::text) AS link_role_cd,
    (a.value ->> 'cond_status_cd'::text) AS cond_status_cd
   FROM ((src s
     CROSS JOIN LATERAL jsonb_array_elements((s.expr -> 'branches'::text)) b(value))
     CROSS JOIN LATERAL jsonb_array_elements((b.value -> 'atoms'::text)) a(value));


--
-- TOC entry 4659 (class 0 OID 0)
-- Dependencies: 378
-- Name: VIEW v_card_cond_atom; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON VIEW db_pipeline.v_card_cond_atom IS '모든 조건식의 atom을 소유자와 함께 행으로 복원';


--
-- TOC entry 370 (class 1259 OID 21586)
-- Name: v_card_rule_target; Type: VIEW; Schema: db_pipeline; Owner: -
--

CREATE VIEW db_pipeline.v_card_rule_target AS
 SELECT r.card_id,
    r.card_bnft_id,
    r.rule_key,
    (t.value ->> 'target_type_cd'::text) AS target_type_cd,
    (t.value ->> 'target_key'::text) AS target_key,
    (t.value ->> 'target_nm'::text) AS target_nm
   FROM (db_pipeline.v_card_rule r
     CROSS JOIN LATERAL jsonb_array_elements(r.target_list) t(value));


--
-- TOC entry 4660 (class 0 OID 0)
-- Dependencies: 370
-- Name: VIEW v_card_rule_target; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON VIEW db_pipeline.v_card_rule_target IS '규칙 대상을 행으로 복원';


--
-- TOC entry 387 (class 1259 OID 21794)
-- Name: v_common_cd_usage; Type: VIEW; Schema: db_pipeline; Owner: -
--

CREATE VIEW db_pipeline.v_common_cd_usage AS
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
 SELECT 'card_bnft.rule_select_cd'::text AS source_nm,
    'RULE_SELECT'::character varying(20) AS common_code_grp_id,
    (card_bnft.rule_select_cd)::text AS cd_value
   FROM db_pipeline.card_bnft
  WHERE (card_bnft.rule_select_cd IS NOT NULL)
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
 SELECT 'card_bnft.rule_list[].predicate_state_cd'::text AS source_nm,
    'PREDICATE_STATE'::character varying AS common_code_grp_id,
    v_card_rule.predicate_state_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE (v_card_rule.predicate_state_cd IS NOT NULL)
UNION ALL
 SELECT 'card_bnft.rule_list[].calc_method_cd'::text AS source_nm,
    'CALC_METHOD'::character varying AS common_code_grp_id,
    v_card_rule.calc_method_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE (v_card_rule.calc_method_cd IS NOT NULL)
UNION ALL
 SELECT 'card_bnft.rule_list[].value_unit_cd'::text AS source_nm,
    'VALUE_UNIT'::character varying AS common_code_grp_id,
    v_card_rule.value_unit_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE (v_card_rule.value_unit_cd IS NOT NULL)
UNION ALL
 SELECT 'card_bnft.rule_list[].payout_unit_cd'::text AS source_nm,
    'PAYOUT_UNIT'::character varying AS common_code_grp_id,
    v_card_rule.payout_unit_cd AS cd_value
   FROM db_pipeline.v_card_rule
  WHERE (v_card_rule.payout_unit_cd IS NOT NULL)
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
 SELECT 'cond_expr atom predicate_method_cd'::text AS source_nm,
    'PREDICATE_METHOD'::character varying AS common_code_grp_id,
    v_card_cond_atom.predicate_method_cd AS cd_value
   FROM db_pipeline.v_card_cond_atom
  WHERE (v_card_cond_atom.predicate_method_cd IS NOT NULL)
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


--
-- TOC entry 4661 (class 0 OID 0)
-- Dependencies: 387
-- Name: VIEW v_common_cd_usage; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON VIEW db_pipeline.v_common_cd_usage IS '모든 공통코드 사용처(물리 컬럼·JSONB 키)와 소속 그룹. 공통코드 정합성 검증의 기준';


--
-- TOC entry 388 (class 1259 OID 21799)
-- Name: v_card_integrity_issue; Type: VIEW; Schema: db_pipeline; Owner: -
--

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
            ((r.rule_status_cd = 'CONFIRMED'::text) OR ((b.verification_status_cd)::text = 'CONFIRMED'::text)) AS final_yn
           FROM (db_pipeline.v_card_rule r
             JOIN db_pipeline.card_bnft b ON (((b.card_id = r.card_id) AND ((b.card_bnft_id)::text = (r.card_bnft_id)::text))))
          WHERE ((r.rule_status_cd <> 'RETIRED'::text) AND (((r.calc_method_cd = ANY (ARRAY['PERCENT_OF_TXN'::text, 'FIXED_PER_TXN'::text, 'UNITS_PER_AMOUNT'::text, 'MULTIPLY_EXTERNAL_POINTS'::text])) AND (r.value_num IS NULL)) OR ((r.calc_method_cd = 'UNITS_PER_AMOUNT'::text) AND (r.basis_amt IS NULL)) OR ((r.calc_method_cd = 'PERCENT_OF_TXN'::text) AND (r.value_unit_cd IS DISTINCT FROM 'PERCENT'::text)) OR ((r.calc_method_cd = 'MULTIPLY_EXTERNAL_POINTS'::text) AND (r.value_unit_cd IS DISTINCT FROM 'MULTIPLIER'::text)) OR ((r.calc_method_cd = ANY (ARRAY['FIXED_PER_TXN'::text, 'UNITS_PER_AMOUNT'::text])) AND (r.value_unit_cd = ANY (ARRAY['PERCENT'::text, 'MULTIPLIER'::text])))))
        ), predicate_param_gap AS (
         SELECT a.owner_cd,
            a.card_id,
            a.atom_key,
            ((a.cond_status_cd = 'CONFIRMED'::text) OR (a.expr_status_cd = 'CONFIRMED'::text)) AS final_yn
           FROM atoms a
          WHERE ((a.cond_status_cd <> 'RETIRED'::text) AND (((a.predicate_method_cd = 'EVERY_MONTH_MIN_SPEND'::text) AND ((a.cond_min_amt IS NULL) OR (jsonb_typeof((a.cond_params -> 'window_months'::text)) IS DISTINCT FROM 'number'::text))) OR ((a.predicate_method_cd = 'MONTH_IN'::text) AND
                CASE
                    WHEN (jsonb_typeof((a.cond_params -> 'months'::text)) = 'array'::text) THEN (jsonb_array_length((a.cond_params -> 'months'::text)) = 0)
                    ELSE true
                END)))
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
 SELECT
        CASE
            WHEN g.final_yn THEN 'rule_method_value_missing'::text
            ELSE 'rule_method_value_pending'::text
        END AS gate_cd,
    ((((g.card_id || '/'::text) || (g.card_bnft_id)::text) || '/'::text) || g.rule_key) AS issue_key
   FROM rule_value_gap g
UNION ALL
 SELECT
        CASE
            WHEN g.final_yn THEN 'predicate_params_missing'::text
            ELSE 'predicate_params_pending'::text
        END AS gate_cd,
    ((((g.owner_cd || '/'::text) || g.card_id) || '/'::text) || g.atom_key) AS issue_key
   FROM predicate_param_gap g
UNION ALL
 SELECT 'excl_item_unknown'::text AS gate_cd,
    ((a.owner_cd || '/'::text) || a.atom_key) AS issue_key
   FROM atoms a
  WHERE ((a.card_excl_item_id IS NOT NULL) AND (NOT (EXISTS ( SELECT 1
           FROM db_pipeline.card_excl_item i
          WHERE ((i.card_excl_item_id)::text = a.card_excl_item_id)))))
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


--
-- TOC entry 4662 (class 0 OID 0)
-- Dependencies: 388
-- Name: VIEW v_card_integrity_issue; Type: COMMENT; Schema: db_pipeline; Owner: -
--

COMMENT ON VIEW db_pipeline.v_card_integrity_issue IS '승인 전 정합성 게이트. 물리 FK가 없으므로 행이 1건이라도 있으면 승인하지 않음. *_pending은 확정 전 항목의 값 누락(검토 대기)이고 나머지는 무결성 위반';


--
-- TOC entry 4382 (class 0 OID 20850)
-- Dependencies: 365
-- Data for Name: card_ai_call; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_ai_call (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, call_input_sha256, call_status, call_resp_raw, call_resp_json, call_error_msg, call_input_token_cnt, call_output_token_cnt, call_latency_ms, call_req_date, create_date, create_user_id, update_date, update_user_id) FROM stdin;
20261101_000002	20261101_000002	1	20261101_000012	1	d4c1b3d3693a0700e9685bc9b52cc6eb57301bd91b38382bdc1f8b0d1fc19c54	SUCCEEDED	{\n  "page_no": 1,\n  "page_role": "MIXED",\n  "product": {\n    "product_nm": "ONE PICK STYLE 하나 체크카드",\n    "issuer": "하나카드",\n    "card_kind_cd": "DEBIT",\n    "brand_txts": ["국내전용", "국내외겸용(Mastercard)"],\n    "annual_fee_txt": "없음",\n    "issue_target_txt": "7세부터 발급 가능"\n  },\n  "benefits": [\n    {\n      "item_key": "one_pick",\n      "bnft_nm": "ONE PICK 편의점·카페 캐시백",\n      "bnft_type_cd": "CASHBACK",\n      "is_common_candidate": false,\n      "no_condition_stated": false,\n      "certainty": "HIGH",\n      "targets": [\n        {"target_type_cd": "MERCHANT", "target_nm": "CU"},\n        {"target_type_cd": "MERCHANT", "target_nm": "GS25"},\n        {"target_type_cd": "MERCHANT", "target_nm": "세븐일레븐"},\n        {"target_type_cd": "MERCHANT", "target_nm": "메가MGC커피"},\n        {"target_type_cd": "MERCHANT", "target_nm": "이디야커피"},\n        {"target_type_cd": "MERCHANT", "target_nm": "컴포즈커피"}\n      ],\n      "rules": [\n        {\n          "rule_key": "one_pick_100",\n          "calc_method_cd": "FIXED_PER_TXN",\n          "value_num": 100,\n          "value_raw_txt": "결제 건당\\n3천원 이상 시 \\n100원",\n          "value_unit_cd": "KRW",\n          "payout_unit_cd": "KRW",\n          "min_txn_amt": 3000,\n          "min_txn_raw_txt": "결제 건당\\n3천원 이상 시",\n          "conditions": [],\n          "limit_keys": ["one_pick_day", "one_pick_month_count", "one_pick_month_amount"]\n        },\n        {\n          "rule_key": "one_pick_500",\n          "calc_method_cd": "FIXED_PER_TXN",\n          "value_num": 500,\n          "value_raw_txt": "결제 건당\\n1만원 이상 시 \\n500원",\n          "value_unit_cd": "KRW",\n          "payout_unit_cd": "KRW",\n          "min_txn_amt": 10000,\n          "min_txn_raw_txt": "결제 건당\\n1만원 이상 시",\n          "conditions": [],\n          "limit_keys": ["one_pick_day", "one_pick_month_count", "one_pick_month_amount"]\n        }\n      ],\n      "limits": [\n        {\n          "limit_key": "one_pick_day",\n          "period_cd": "DAY",\n          "cap_unit_cd": "COUNT",\n          "limit_num": 1,\n          "limit_raw_txt": "일 1회\\n/ 월 30회",\n          "shared_scope_txt": null,\n          "applies_to_benefit_nms": ["ONE PICK 편의점·카페 캐시백"]\n        },\n        {\n          "limit_key": "one_pick_month_count",\n          "period_cd": "MONTH",\n          "cap_unit_cd": "COUNT",\n          "limit_num": 30,\n          "limit_raw_txt": "일 1회\\n/ 월 30회",\n          "shared_scope_txt": null,\n          "applies_to_benefit_nms": ["ONE PICK 편의점·카페 캐시백"]\n        },\n        {\n          "limit_key": "one_pick_month_amount",\n          "period_cd": "MONTH",\n          "cap_unit_cd": "KRW",\n          "limit_num": 5000,\n          "limit_raw_txt": "월 5천원",\n          "shared_scope_txt": null,\n          "applies_to_benefit_nms": ["ONE PICK 편의점·카페 캐시백"]\n        }\n      ],\n      "conditions": [],\n      "relations": [],\n      "evidence": [\n        {"quote_txt": "(지난달 실적 조건 없는 서비스)", "supports": "COND", "support_key": null, "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "CU, GS25, \\n세븐일레븐", "supports": "TARGET", "support_key": null, "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "메가MGC커피, \\n이디야커피, \\n컴포즈커피", "supports": "TARGET", "support_key": null, "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "supports": "RULE", "support_key": "one_pick_100", "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "supports": "RULE", "support_key": "one_pick_500", "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "일 1회\\n/ 월 30회", "supports": "LIMIT", "support_key": "one_pick_month_count", "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "월 5천원", "supports": "LIMIT", "support_key": "one_pick_month_amount", "link_basis": "TABLE_IMAGE"}\n      ],\n      "uncertainty_note": "결제금액 1만원 이상에서 두 정액 캐시백 조건의 적용 관계는 원문에 명시되지 않음."\n    },\n    {\n      "item_key": "style",\n      "bnft_nm": "STYLE 쇼핑·서점/문구·패션 캐시백",\n      "bnft_type_cd": "CASHBACK",\n      "is_common_candidate": false,\n      "no_condition_stated": false,\n      "certainty": "HIGH",\n      "targets": [\n        {"target_type_cd": "MERCHANT", "target_nm": "다이소"},\n        {"target_type_cd": "MERCHANT", "target_nm": "올리브영"},\n        {"target_type_cd": "MERCHANT", "target_nm": "교보문고"},\n        {"target_type_cd": "MERCHANT", "target_nm": "영풍문고"},\n        {"target_type_cd": "MERCHANT", "target_nm": "알라딘"},\n        {"target_type_cd": "MERCHANT", "target_nm": "yes24"},\n        {"target_type_cd": "MERCHANT", "target_nm": "아트박스"},\n        {"target_type_cd": "MERCHANT", "target_nm": "무신사"},\n        {"target_type_cd": "MERCHANT", "target_nm": "에이블리"}\n      ],\n      "rules": [\n        {\n          "rule_key": "style_100",\n          "calc_method_cd": "FIXED_PER_TXN",\n          "value_num": 100,\n          "value_raw_txt": "결제 건당\\n3천원 이상 시 \\n100원",\n          "value_unit_cd": "KRW",\n          "payout_unit_cd": "KRW",\n          "min_txn_amt": 3000,\n          "min_txn_raw_txt": "결제 건당\\n3천원 이상 시",\n          "conditions": [],\n          "limit_keys": ["style_day", "style_month_count", "style_month_amount"]\n        },\n        {\n          "rule_key": "style_500",\n          "calc_method_cd": "FIXED_PER_TXN",\n          "value_num": 500,\n          "value_raw_txt": "결제 건당\\n1만원 이상 시 \\n500원",\n          "value_unit_cd": "KRW",\n          "payout_unit_cd": "KRW",\n          "min_txn_amt": 10000,\n          "min_txn_raw_txt": "결제 건당\\n1만원 이상 시",\n          "conditions": [],\n          "limit_keys": ["style_day", "style_month_count", "style_month_amount"]\n        }\n      ],\n      "limits": [\n        {\n          "limit_key": "style_day",\n          "period_cd": "DAY",\n          "cap_unit_cd": "COUNT",\n          "limit_num": 1,\n          "limit_raw_txt": "일 1회\\n/ 월 10회",\n          "shared_scope_txt": null,\n          "applies_to_benefit_nms": ["STYLE 쇼핑·서점/문구·패션 캐시백"]\n        },\n        {\n          "limit_key": "style_month_count",\n          "period_cd": "MONTH",\n          "cap_unit_cd": "COUNT",\n          "limit_num": 10,\n          "limit_raw_txt": "일 1회\\n/ 월 10회",\n          "shared_scope_txt": null,\n          "applies_to_benefit_nms": ["STYLE 쇼핑·서점/문구·패션 캐시백"]\n        },\n        {\n          "limit_key": "style_month_amount",\n          "period_cd": "MONTH",\n          "cap_unit_cd": "KRW",\n          "limit_num": 5000,\n          "limit_raw_txt": "월 5천원",\n          "shared_scope_txt": null,\n          "applies_to_benefit_nms": ["STYLE 쇼핑·서점/문구·패션 캐시백"]\n        }\n      ],\n      "conditions": [],\n      "relations": [],\n      "evidence": [\n        {"quote_txt": "(지난달 실적 조건 없는 서비스)", "supports": "COND", "support_key": null, "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "다이소, 올리브영\\n교보문고, 영풍문고,\\n알라딘, yes24,\\n아트박스\\n무신사, 에이블리", "supports": "TARGET", "support_key": null, "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "supports": "RULE", "support_key": "style_100", "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "supports": "RULE", "support_key": "style_500", "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "일 1회\\n/ 월 10회", "supports": "LIMIT", "support_key": "style_month_count", "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "월 5천원", "supports": "LIMIT", "support_key": "style_month_amount", "link_basis": "TABLE_IMAGE"}\n      ],\n      "uncertainty_note": "결제금액 1만원 이상에서 두 정액 캐시백 조건의 적용 관계는 원문에 명시되지 않음."\n    },\n    {\n      "item_key": "transit",\n      "bnft_nm": "ONE MORE 대중교통 캐시백",\n      "bnft_type_cd": "CASHBACK",\n      "is_common_candidate": false,\n      "no_condition_stated": false,\n      "certainty": "HIGH",\n      "targets": [\n        {"target_type_cd": "SERVICE", "target_nm": "버스"},\n        {"target_type_cd": "SERVICE", "target_nm": "지하철"}\n      ],\n      "rules": [\n        {\n          "rule_key": "transit_rate",\n          "calc_method_cd": "PERCENT_OF_TXN",\n          "value_num": 5,\n          "value_raw_txt": "5%\\n캐시백",\n          "value_unit_cd": "PERCENT",\n          "payout_unit_cd": "KRW",\n          "min_txn_amt": null,\n          "min_txn_raw_txt": null,\n          "conditions": [],\n          "limit_keys": ["transit_month_amount"]\n        }\n      ],\n      "limits": [\n        {\n          "limit_key": "transit_month_amount",\n          "period_cd": "MONTH",\n          "cap_unit_cd": "KRW",\n          "limit_num": 1000,\n          "limit_raw_txt": "월 1천원",\n          "shared_scope_txt": null,\n          "applies_to_benefit_nms": ["ONE MORE 대중교통 캐시백"]\n        }\n      ],\n      "conditions": [\n        {\n          "cond_key": "transit_spend",\n          "cond_type_cd": "SPEND_REQ",\n          "cond_basis_cd": "PREV_MONTH_SPEND",\n          "cond_min_amt": 100000,\n          "cond_max_amt_excl": null,\n          "negate_yn": false,\n          "excl_raw_txt": null,\n          "cond_raw_txt": "지난달 실적\\n대중교통\\n버스, 지하철\\n월 1천원\\n5%\\n캐시백\\n10만원",\n          "scope": "THIS_BENEFIT",\n          "target_benefit_nms": ["ONE MORE 대중교통 캐시백"],\n          "evidence": [\n            {"quote_txt": "대중교통\\n버스, 지하철\\n월 1천원\\n5%\\n캐시백\\n10만원", "supports": "COND", "support_key": "transit_spend", "link_basis": "TABLE_IMAGE"},\n            {"quote_txt": "- 지난달 1일부터 말일(승인 시점 기준)까지 국내외 일시불 이용금액 10만원/20만원 이상 시\\n ONE MORE 서비스 제공", "supports": "COND", "support_key": "transit_spend", "link_basis": "SAME_TEXT"}\n          ]\n        },\n        {\n          "cond_key": "transit_grace",\n          "cond_type_cd": "GRACE",\n          "cond_basis_cd": "PREV_MONTH_SPEND",\n          "cond_min_amt": null,\n          "cond_max_amt_excl": null,\n          "negate_yn": false,\n          "excl_raw_txt": null,\n          "cond_raw_txt": "- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공",\n          "scope": "THIS_BENEFIT",\n          "target_benefit_nms": ["ONE MORE 대중교통 캐시백"],\n          "evidence": [\n            {"quote_txt": "- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공", "supports": "COND", "support_key": "transit_grace", "link_basis": "SAME_TEXT"}\n          ]\n        },\n        {\n          "cond_key": "transit_exclusions",\n          "cond_type_cd": "BNFT_EXCL",\n          "cond_basis_cd": null,\n          "cond_min_amt": null,\n          "cond_max_amt_excl": null,\n          "negate_yn": true,\n          "excl_raw_txt": "시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외",\n          "cond_raw_txt": "- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외",\n          "scope": "THIS_BENEFIT",\n          "target_benefit_nms": ["ONE MORE 대중교통 캐시백"],\n          "evidence": [\n            {"quote_txt": "- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "supports": "COND", "support_key": "transit_exclusions", "link_basis": "SAME_TEXT"}\n          ]\n        }\n      ],\n      "relations": [],\n      "evidence": [\n        {"quote_txt": "대중교통\\n버스, 지하철\\n월 1천원\\n5%\\n캐시백\\n10만원", "supports": "BNFT", "support_key": null, "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "5%\\n캐시백", "supports": "RULE", "support_key": "transit_rate", "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "월 1천원", "supports": "LIMIT", "support_key": "transit_month_amount", "link_basis": "TABLE_IMAGE"}\n      ],\n      "uncertainty_note": null\n    },\n    {\n      "item_key": "amusement",\n      "bnft_nm": "ONE MORE 놀이공원 현장할인",\n      "bnft_type_cd": "DISCOUNT",\n      "is_common_candidate": false,\n      "no_condition_stated": false,\n      "certainty": "HIGH",\n      "targets": [\n        {"target_type_cd": "MERCHANT", "target_nm": "에버랜드"},\n        {"target_type_cd": "MERCHANT", "target_nm": "롯데월드"}\n      ],\n      "rules": [\n        {\n          "rule_key": "amusement_rate",\n          "calc_method_cd": "PERCENT_OF_TXN",\n          "value_num": 50,\n          "value_raw_txt": "50% \\n현장할인\\n(1인 1매)",\n          "value_unit_cd": "PERCENT",\n          "payout_unit_cd": "KRW",\n          "min_txn_amt": null,\n          "min_txn_raw_txt": null,\n          "conditions": [],\n          "limit_keys": ["amusement_month", "amusement_year", "amusement_person"]\n        }\n      ],\n      "limits": [\n        {\n          "limit_key": "amusement_month",\n          "period_cd": "MONTH",\n          "cap_unit_cd": "COUNT",\n          "limit_num": 1,\n          "limit_raw_txt": "월 1회 \\n/ 연 2회",\n          "shared_scope_txt": null,\n          "applies_to_benefit_nms": ["ONE MORE 놀이공원 현장할인"]\n        },\n        {\n          "limit_key": "amusement_year",\n          "period_cd": "YEAR",\n          "cap_unit_cd": "COUNT",\n          "limit_num": 2,\n          "limit_raw_txt": "월 1회 \\n/ 연 2회",\n          "shared_scope_txt": null,\n          "applies_to_benefit_nms": ["ONE MORE 놀이공원 현장할인"]\n        },\n        {\n          "limit_key": "amusement_person",\n          "period_cd": "UNKNOWN",\n          "cap_unit_cd": "COUNT",\n          "limit_num": 1,\n          "limit_raw_txt": "(1인 1매)",\n          "shared_scope_txt": null,\n          "applies_to_benefit_nms": ["ONE MORE 놀이공원 현장할인"]\n        }\n      ],\n      "conditions": [\n        {\n          "cond_key": "amusement_spend",\n          "cond_type_cd": "SPEND_REQ",\n          "cond_basis_cd": "PREV_MONTH_SPEND",\n          "cond_min_amt": 200000,\n          "cond_max_amt_excl": null,\n          "negate_yn": false,\n          "excl_raw_txt": null,\n          "cond_raw_txt": "* ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공",\n          "scope": "THIS_BENEFIT",\n          "target_benefit_nms": ["ONE MORE 놀이공원 현장할인"],\n          "evidence": [\n            {"quote_txt": "* ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공", "supports": "COND", "support_key": "amusement_spend", "link_basis": "SAME_TEXT"}\n          ]\n        },\n        {\n          "cond_key": "amusement_first_month",\n          "cond_type_cd": "GRACE",\n          "cond_basis_cd": null,\n          "cond_min_amt": null,\n          "cond_max_amt_excl": null,\n          "negate_yn": true,\n          "excl_raw_txt": "최초 발급 월에는\\n서비스 미제공",\n          "cond_raw_txt": "최초 발급 월에는\\n서비스 미제공",\n          "scope": "THIS_BENEFIT",\n          "target_benefit_nms": ["ONE MORE 놀이공원 현장할인"],\n          "evidence": [\n            {"quote_txt": "최초 발급 월에는\\n서비스 미제공", "supports": "COND", "support_key": "amusement_first_month", "link_basis": "TABLE_IMAGE"}\n          ]\n        }\n      ],\n      "relations": [],\n      "evidence": [\n        {"quote_txt": "놀이공원\\n에버랜드, 롯데월드\\n월 1회 \\n/ 연 2회\\n50% \\n현장할인\\n(1인 1매)\\n20만원\\n최초 발급 월에는\\n서비스 미제공", "supports": "BNFT", "support_key": null, "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "50% \\n현장할인\\n(1인 1매)", "supports": "RULE", "support_key": "amusement_rate", "link_basis": "TABLE_IMAGE"},\n        {"quote_txt": "월 1회 \\n/ 연 2회", "supports": "LIMIT", "support_key": "amusement_year", "link_basis": "TABLE_IMAGE"}\n      ],\n      "uncertainty_note": null\n    }\n  ],\n  "card_conditions": [\n    {\n      "cond_key": "common_service_exclusion",\n      "cond_type_cd": "BNFT_EXCL",\n      "cond_basis_cd": null,\n      "cond_min_amt": null,\n      "cond_max_amt_excl": null,\n      "negate_yn": true,\n      "excl_raw_txt": "상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외",\n      "cond_raw_txt": "- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외",\n      "scope": "ALL_BENEFITS",\n      "target_benefit_nms": [],\n      "evidence": [\n        {"quote_txt": "- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "supports": "COND", "support_key": "common_service_exclusion", "link_basis": "SAME_TEXT"}\n      ]\n    },\n    {\n      "cond_key": "common_channel",\n      "cond_type_cd": "PAYMENT_METHOD",\n      "cond_basis_cd": null,\n      "cond_min_amt": null,\n      "cond_max_amt_excl": null,\n      "negate_yn": false,\n      "excl_raw_txt": "배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외",\n      "cond_raw_txt": "대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외",\n      "scope": "ALL_BENEFITS",\n      "target_benefit_nms": [],\n      "evidence": [\n        {"quote_txt": "대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "supports": "COND", "support_key": "common_channel", "link_basis": "SAME_TEXT"}\n      ]\n    },\n    {\n      "cond_key": "spend_exclusions",\n      "cond_type_cd": "SPEND_EXCL",\n      "cond_basis_cd": "PREV_MONTH_SPEND",\n      "cond_min_amt": null,\n      "cond_max_amt_excl": null,\n      "negate_yn": true,\n      "excl_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외",\n      "cond_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외",\n      "scope": "NAMED_BENEFITS",\n      "target_benefit_nms": ["ONE MORE 대중교통 캐시백", "ONE MORE 놀이공원 현장할인"],\n      "evidence": [\n        {"quote_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "supports": "COND", "support_key": "spend_exclusions", "link_basis": "SAME_TEXT"}\n      ]\n    },\n    {\n      "cond_key": "merchant_classification",\n      "cond_type_cd": "MERCHANT_RULE",\n      "cond_basis_cd": null,\n      "cond_min_amt": null,\n      "cond_max_amt_excl": null,\n      "negate_yn": false,\n      "excl_raw_txt": null,\n      "cond_raw_txt": "- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공",\n      "scope": "ALL_BENEFITS",\n      "target_benefit_nms": [],\n      "evidence": [\n        {"quote_txt": "- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공", "supports": "COND", "support_key": "merchant_classification", "link_basis": "SAME_TEXT"},\n        {"quote_txt": "- 가맹점 정보가 해당 업체가 아닌 결제대행업체(PG) 또는 간편결제 전용 가맹점으로 확인되는 \\n 경우 ‘결제대행업체’ 또는 ‘간편결제’ 가맹점으로 분류되어 각 서비스 영역에 따른 혜택이 제공됨", "supports": "COND", "support_key": "merchant_classification", "link_basis": "SAME_TEXT"}\n      ]\n    }\n  ],\n  "unresolved": [\n    {\n      "raw_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원",\n      "reason": "1만원 이상 결제 시 두 조건이 중첩되며, 중복 적용 또는 우선 적용 여부는 명시되지 않음."\n    },\n    {\n      "raw_txt": "12~17세 이상 손님",\n      "reason": "연령 범위와 ‘이상’이 함께 사용되어 발급 대상 연령 표현이 불명확함."\n    }\n  ]\n}	{"page_no": 1, "product": {"issuer": "하나카드", "brand_txts": ["국내전용", "국내외겸용(Mastercard)"], "product_nm": "ONE PICK STYLE 하나 체크카드", "card_kind_cd": "DEBIT", "annual_fee_txt": "없음", "issue_target_txt": "7세부터 발급 가능"}, "benefits": [{"rules": [{"rule_key": "one_pick_100", "value_num": "100", "conditions": [], "limit_keys": ["one_pick_day", "one_pick_month_count", "one_pick_month_amount"], "min_txn_amt": 3000, "value_raw_txt": "결제 건당\\n3천원 이상 시 \\n100원", "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": "결제 건당\\n3천원 이상 시"}, {"rule_key": "one_pick_500", "value_num": "500", "conditions": [], "limit_keys": ["one_pick_day", "one_pick_month_count", "one_pick_month_amount"], "min_txn_amt": 10000, "value_raw_txt": "결제 건당\\n1만원 이상 시 \\n500원", "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": "결제 건당\\n1만원 이상 시"}], "limits": [{"limit_key": "one_pick_day", "limit_num": 1, "period_cd": "DAY", "cap_unit_cd": "COUNT", "limit_raw_txt": "일 1회\\n/ 월 30회", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE PICK 편의점·카페 캐시백"]}, {"limit_key": "one_pick_month_count", "limit_num": 30, "period_cd": "MONTH", "cap_unit_cd": "COUNT", "limit_raw_txt": "일 1회\\n/ 월 30회", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE PICK 편의점·카페 캐시백"]}, {"limit_key": "one_pick_month_amount", "limit_num": 5000, "period_cd": "MONTH", "cap_unit_cd": "KRW", "limit_raw_txt": "월 5천원", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE PICK 편의점·카페 캐시백"]}], "bnft_nm": "ONE PICK 편의점·카페 캐시백", "targets": [{"target_nm": "CU", "target_type_cd": "MERCHANT"}, {"target_nm": "GS25", "target_type_cd": "MERCHANT"}, {"target_nm": "세븐일레븐", "target_type_cd": "MERCHANT"}, {"target_nm": "메가MGC커피", "target_type_cd": "MERCHANT"}, {"target_nm": "이디야커피", "target_type_cd": "MERCHANT"}, {"target_nm": "컴포즈커피", "target_type_cd": "MERCHANT"}], "evidence": [{"supports": "COND", "quote_txt": "(지난달 실적 조건 없는 서비스)", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "TARGET", "quote_txt": "CU, GS25, \\n세븐일레븐", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "TARGET", "quote_txt": "메가MGC커피, \\n이디야커피, \\n컴포즈커피", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "RULE", "quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "link_basis": "TABLE_IMAGE", "support_key": "one_pick_100"}, {"supports": "RULE", "quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "link_basis": "TABLE_IMAGE", "support_key": "one_pick_500"}, {"supports": "LIMIT", "quote_txt": "일 1회\\n/ 월 30회", "link_basis": "TABLE_IMAGE", "support_key": "one_pick_month_count"}, {"supports": "LIMIT", "quote_txt": "월 5천원", "link_basis": "TABLE_IMAGE", "support_key": "one_pick_month_amount"}], "item_key": "one_pick", "certainty": "HIGH", "relations": [], "conditions": [], "bnft_type_cd": "CASHBACK", "uncertainty_note": "결제금액 1만원 이상에서 두 정액 캐시백 조건의 적용 관계는 원문에 명시되지 않음.", "is_common_candidate": false, "no_condition_stated": false}, {"rules": [{"rule_key": "style_100", "value_num": "100", "conditions": [], "limit_keys": ["style_day", "style_month_count", "style_month_amount"], "min_txn_amt": 3000, "value_raw_txt": "결제 건당\\n3천원 이상 시 \\n100원", "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": "결제 건당\\n3천원 이상 시"}, {"rule_key": "style_500", "value_num": "500", "conditions": [], "limit_keys": ["style_day", "style_month_count", "style_month_amount"], "min_txn_amt": 10000, "value_raw_txt": "결제 건당\\n1만원 이상 시 \\n500원", "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": "결제 건당\\n1만원 이상 시"}], "limits": [{"limit_key": "style_day", "limit_num": 1, "period_cd": "DAY", "cap_unit_cd": "COUNT", "limit_raw_txt": "일 1회\\n/ 월 10회", "shared_scope_txt": null, "applies_to_benefit_nms": ["STYLE 쇼핑·서점/문구·패션 캐시백"]}, {"limit_key": "style_month_count", "limit_num": 10, "period_cd": "MONTH", "cap_unit_cd": "COUNT", "limit_raw_txt": "일 1회\\n/ 월 10회", "shared_scope_txt": null, "applies_to_benefit_nms": ["STYLE 쇼핑·서점/문구·패션 캐시백"]}, {"limit_key": "style_month_amount", "limit_num": 5000, "period_cd": "MONTH", "cap_unit_cd": "KRW", "limit_raw_txt": "월 5천원", "shared_scope_txt": null, "applies_to_benefit_nms": ["STYLE 쇼핑·서점/문구·패션 캐시백"]}], "bnft_nm": "STYLE 쇼핑·서점/문구·패션 캐시백", "targets": [{"target_nm": "다이소", "target_type_cd": "MERCHANT"}, {"target_nm": "올리브영", "target_type_cd": "MERCHANT"}, {"target_nm": "교보문고", "target_type_cd": "MERCHANT"}, {"target_nm": "영풍문고", "target_type_cd": "MERCHANT"}, {"target_nm": "알라딘", "target_type_cd": "MERCHANT"}, {"target_nm": "yes24", "target_type_cd": "MERCHANT"}, {"target_nm": "아트박스", "target_type_cd": "MERCHANT"}, {"target_nm": "무신사", "target_type_cd": "MERCHANT"}, {"target_nm": "에이블리", "target_type_cd": "MERCHANT"}], "evidence": [{"supports": "COND", "quote_txt": "(지난달 실적 조건 없는 서비스)", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "TARGET", "quote_txt": "다이소, 올리브영\\n교보문고, 영풍문고,\\n알라딘, yes24,\\n아트박스\\n무신사, 에이블리", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "RULE", "quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "link_basis": "TABLE_IMAGE", "support_key": "style_100"}, {"supports": "RULE", "quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "link_basis": "TABLE_IMAGE", "support_key": "style_500"}, {"supports": "LIMIT", "quote_txt": "일 1회\\n/ 월 10회", "link_basis": "TABLE_IMAGE", "support_key": "style_month_count"}, {"supports": "LIMIT", "quote_txt": "월 5천원", "link_basis": "TABLE_IMAGE", "support_key": "style_month_amount"}], "item_key": "style", "certainty": "HIGH", "relations": [], "conditions": [], "bnft_type_cd": "CASHBACK", "uncertainty_note": "결제금액 1만원 이상에서 두 정액 캐시백 조건의 적용 관계는 원문에 명시되지 않음.", "is_common_candidate": false, "no_condition_stated": false}, {"rules": [{"rule_key": "transit_rate", "value_num": "5", "conditions": [], "limit_keys": ["transit_month_amount"], "min_txn_amt": null, "value_raw_txt": "5%\\n캐시백", "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": null}], "limits": [{"limit_key": "transit_month_amount", "limit_num": 1000, "period_cd": "MONTH", "cap_unit_cd": "KRW", "limit_raw_txt": "월 1천원", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE MORE 대중교통 캐시백"]}], "bnft_nm": "ONE MORE 대중교통 캐시백", "targets": [{"target_nm": "버스", "target_type_cd": "SERVICE"}, {"target_nm": "지하철", "target_type_cd": "SERVICE"}], "evidence": [{"supports": "BNFT", "quote_txt": "대중교통\\n버스, 지하철\\n월 1천원\\n5%\\n캐시백\\n10만원", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "RULE", "quote_txt": "5%\\n캐시백", "link_basis": "TABLE_IMAGE", "support_key": "transit_rate"}, {"supports": "LIMIT", "quote_txt": "월 1천원", "link_basis": "TABLE_IMAGE", "support_key": "transit_month_amount"}], "item_key": "transit", "certainty": "HIGH", "relations": [], "conditions": [{"scope": "THIS_BENEFIT", "cond_key": "transit_spend", "evidence": [{"supports": "COND", "quote_txt": "대중교통\\n버스, 지하철\\n월 1천원\\n5%\\n캐시백\\n10만원", "link_basis": "TABLE_IMAGE", "support_key": "transit_spend"}, {"supports": "COND", "quote_txt": "- 지난달 1일부터 말일(승인 시점 기준)까지 국내외 일시불 이용금액 10만원/20만원 이상 시\\n ONE MORE 서비스 제공", "link_basis": "SAME_TEXT", "support_key": "transit_spend"}], "negate_yn": false, "cond_min_amt": 100000, "cond_raw_txt": "지난달 실적\\n대중교통\\n버스, 지하철\\n월 1천원\\n5%\\n캐시백\\n10만원", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 대중교통 캐시백"]}, {"scope": "THIS_BENEFIT", "cond_key": "transit_grace", "evidence": [{"supports": "COND", "quote_txt": "- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공", "link_basis": "SAME_TEXT", "support_key": "transit_grace"}], "negate_yn": false, "cond_min_amt": null, "cond_raw_txt": "- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공", "cond_type_cd": "GRACE", "excl_raw_txt": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 대중교통 캐시백"]}, {"scope": "THIS_BENEFIT", "cond_key": "transit_exclusions", "evidence": [{"supports": "COND", "quote_txt": "- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "link_basis": "SAME_TEXT", "support_key": "transit_exclusions"}], "negate_yn": true, "cond_min_amt": null, "cond_raw_txt": "- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "cond_basis_cd": null, "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 대중교통 캐시백"]}], "bnft_type_cd": "CASHBACK", "uncertainty_note": null, "is_common_candidate": false, "no_condition_stated": false}, {"rules": [{"rule_key": "amusement_rate", "value_num": "50", "conditions": [], "limit_keys": ["amusement_month", "amusement_year", "amusement_person"], "min_txn_amt": null, "value_raw_txt": "50% \\n현장할인\\n(1인 1매)", "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": null}], "limits": [{"limit_key": "amusement_month", "limit_num": 1, "period_cd": "MONTH", "cap_unit_cd": "COUNT", "limit_raw_txt": "월 1회 \\n/ 연 2회", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE MORE 놀이공원 현장할인"]}, {"limit_key": "amusement_year", "limit_num": 2, "period_cd": "YEAR", "cap_unit_cd": "COUNT", "limit_raw_txt": "월 1회 \\n/ 연 2회", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE MORE 놀이공원 현장할인"]}, {"limit_key": "amusement_person", "limit_num": 1, "period_cd": "UNKNOWN", "cap_unit_cd": "COUNT", "limit_raw_txt": "(1인 1매)", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE MORE 놀이공원 현장할인"]}], "bnft_nm": "ONE MORE 놀이공원 현장할인", "targets": [{"target_nm": "에버랜드", "target_type_cd": "MERCHANT"}, {"target_nm": "롯데월드", "target_type_cd": "MERCHANT"}], "evidence": [{"supports": "BNFT", "quote_txt": "놀이공원\\n에버랜드, 롯데월드\\n월 1회 \\n/ 연 2회\\n50% \\n현장할인\\n(1인 1매)\\n20만원\\n최초 발급 월에는\\n서비스 미제공", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "RULE", "quote_txt": "50% \\n현장할인\\n(1인 1매)", "link_basis": "TABLE_IMAGE", "support_key": "amusement_rate"}, {"supports": "LIMIT", "quote_txt": "월 1회 \\n/ 연 2회", "link_basis": "TABLE_IMAGE", "support_key": "amusement_year"}], "item_key": "amusement", "certainty": "HIGH", "relations": [], "conditions": [{"scope": "THIS_BENEFIT", "cond_key": "amusement_spend", "evidence": [{"supports": "COND", "quote_txt": "* ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공", "link_basis": "SAME_TEXT", "support_key": "amusement_spend"}], "negate_yn": false, "cond_min_amt": 200000, "cond_raw_txt": "* ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 놀이공원 현장할인"]}, {"scope": "THIS_BENEFIT", "cond_key": "amusement_first_month", "evidence": [{"supports": "COND", "quote_txt": "최초 발급 월에는\\n서비스 미제공", "link_basis": "TABLE_IMAGE", "support_key": "amusement_first_month"}], "negate_yn": true, "cond_min_amt": null, "cond_raw_txt": "최초 발급 월에는\\n서비스 미제공", "cond_type_cd": "GRACE", "excl_raw_txt": "최초 발급 월에는\\n서비스 미제공", "cond_basis_cd": null, "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 놀이공원 현장할인"]}], "bnft_type_cd": "DISCOUNT", "uncertainty_note": null, "is_common_candidate": false, "no_condition_stated": false}], "page_role": "MIXED", "unresolved": [{"reason": "1만원 이상 결제 시 두 조건이 중첩되며, 중복 적용 또는 우선 적용 여부는 명시되지 않음.", "raw_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원"}, {"reason": "연령 범위와 ‘이상’이 함께 사용되어 발급 대상 연령 표현이 불명확함.", "raw_txt": "12~17세 이상 손님"}], "card_conditions": [{"scope": "ALL_BENEFITS", "cond_key": "common_service_exclusion", "evidence": [{"supports": "COND", "quote_txt": "- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "link_basis": "SAME_TEXT", "support_key": "common_service_exclusion"}], "negate_yn": true, "cond_min_amt": null, "cond_raw_txt": "- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외", "cond_basis_cd": null, "cond_max_amt_excl": null, "target_benefit_nms": []}, {"scope": "ALL_BENEFITS", "cond_key": "common_channel", "evidence": [{"supports": "COND", "quote_txt": "대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "link_basis": "SAME_TEXT", "support_key": "common_channel"}], "negate_yn": false, "cond_min_amt": null, "cond_raw_txt": "대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_type_cd": "PAYMENT_METHOD", "excl_raw_txt": "배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_basis_cd": null, "cond_max_amt_excl": null, "target_benefit_nms": []}, {"scope": "NAMED_BENEFITS", "cond_key": "spend_exclusions", "evidence": [{"supports": "COND", "quote_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "link_basis": "SAME_TEXT", "support_key": "spend_exclusions"}], "negate_yn": true, "cond_min_amt": null, "cond_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "cond_type_cd": "SPEND_EXCL", "excl_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "cond_basis_cd": "PREV_MONTH_SPEND", "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 대중교통 캐시백", "ONE MORE 놀이공원 현장할인"]}, {"scope": "ALL_BENEFITS", "cond_key": "merchant_classification", "evidence": [{"supports": "COND", "quote_txt": "- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공", "link_basis": "SAME_TEXT", "support_key": "merchant_classification"}, {"supports": "COND", "quote_txt": "- 가맹점 정보가 해당 업체가 아닌 결제대행업체(PG) 또는 간편결제 전용 가맹점으로 확인되는 \\n 경우 ‘결제대행업체’ 또는 ‘간편결제’ 가맹점으로 분류되어 각 서비스 영역에 따른 혜택이 제공됨", "link_basis": "SAME_TEXT", "support_key": "merchant_classification"}], "negate_yn": false, "cond_min_amt": null, "cond_raw_txt": "- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공", "cond_type_cd": "MERCHANT_RULE", "excl_raw_txt": null, "cond_basis_cd": null, "cond_max_amt_excl": null, "target_benefit_nms": []}]}	\N	6794	6815	9	2026-11-01 01:14:30.868297+00	2026-11-01 01:14:30.868297+00	SYSTEM	2026-11-01 01:14:30.868297+00	SYSTEM
20261102_000003	20261102_000004	1	20261102_000020	1	dd5f888506bed4681d28936be4180ea05b9f44136338fe3432c13b7067849309	SUCCEEDED	{"page_no": 1, "page_role": "DETAIL", "benefits": [{"item_key": "VISA_CONCIERGE", "bnft_nm": "Visa 컨시어지", "bnft_type_cd": "SERVICE", "is_common_candidate": true, "certainty": "HIGH", "brand_txt": "Visa", "service_grade_txt": "Signature", "applicable_cards": [], "selection_service_txt": null, "excluded_cards": [], "validity_period_txt": "2026년1월1일~ 12월31일", "rules": [], "limits": [], "conditions": [], "evidence": [{"quote_txt": "Visa 컨시어지제공", "supports": "BNFT", "support_key": null, "link_basis": "SAME_TEXT"}, {"quote_txt": "아래의Visa Signature서비스는Visa Signature 등급카드\\n소지자에게공통으로제공됩니다.", "supports": "APPLICABILITY", "support_key": null, "link_basis": "SAME_TEXT"}, {"quote_txt": "본Visa Signature 서비스는기간이따로명시되지않은한\\n2026년1월1일~ 12월31일까지제공됩니다.", "supports": "APPLICABILITY", "support_key": null, "link_basis": "SAME_TEXT"}], "uncertainty_note": "수동으로 한 혜택만 발췌. 세부 제공 조건 및 비용은 미확인."}], "card_conditions": [], "unresolved": []}	{"page_no": 1, "product": null, "benefits": [{"rules": [], "limits": [], "bnft_nm": "Visa 컨시어지", "targets": [], "evidence": [{"supports": "BNFT", "quote_txt": "Visa 컨시어지제공", "link_basis": "SAME_TEXT", "support_key": null}, {"supports": "APPLICABILITY", "quote_txt": "아래의Visa Signature서비스는Visa Signature 등급카드\\n소지자에게공통으로제공됩니다.", "link_basis": "SAME_TEXT", "support_key": null}, {"supports": "APPLICABILITY", "quote_txt": "본Visa Signature 서비스는기간이따로명시되지않은한\\n2026년1월1일~ 12월31일까지제공됩니다.", "link_basis": "SAME_TEXT", "support_key": null}], "item_key": "VISA_CONCIERGE", "brand_txt": "Visa", "certainty": "HIGH", "relations": [], "conditions": [], "bnft_type_cd": "SERVICE", "excluded_cards": [], "applicable_cards": [], "uncertainty_note": "수동으로 한 혜택만 발췌. 세부 제공 조건 및 비용은 미확인.", "service_grade_txt": "Signature", "is_common_candidate": true, "no_condition_stated": false, "validity_period_txt": "2026년1월1일~ 12월31일", "selection_service_txt": null}], "page_role": "DETAIL", "unresolved": [], "card_conditions": []}	\N	\N	\N	0	2026-11-02 08:44:16.538489+00	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000003	20261102_000004	2	20261102_000021	1	2a7905b6b8e157d8d2de8377740c8c85d6e4c25fcc9ba1754a1eb03f3eaa3273	SUCCEEDED	{"page_no": 2, "page_role": "NOTICE", "benefits": [], "card_conditions": [], "unresolved": [{"raw_txt": "Visa\\nSignature 02\\n선택서비스\\nVisa Signature 선택서비스중특급호텔발렛파킹, 인천공항발렛파킹서비스를하나카드에서제공합니다.\\nVisa Signature 02 선택", "reason": "수동 단일 혜택 발췌; 이 페이지의 다른 혜택은 추출하지 않음"}]}	{"page_no": 2, "product": null, "benefits": [], "page_role": "NOTICE", "unresolved": [{"reason": "수동 단일 혜택 발췌; 이 페이지의 다른 혜택은 추출하지 않음", "raw_txt": "Visa\\nSignature 02\\n선택서비스\\nVisa Signature 선택서비스중특급호텔발렛파킹, 인천공항발렛파킹서비스를하나카드에서제공합니다.\\nVisa Signature 02 선택"}], "card_conditions": []}	\N	\N	\N	0	2026-11-02 08:44:16.538489+00	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
\.


--
-- TOC entry 4381 (class 0 OID 20839)
-- Dependencies: 364
-- Data for Name: card_ai_run; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_ai_run (card_ai_run_id, run_stage_cd, run_call_mthd_cd, run_model_nm, run_prompt_ver, run_prompt_txt, run_param, run_target_card_doc_id, run_status, run_start_date, run_end_date, run_note, create_date, create_user_id, update_date, update_user_id) FROM stdin;
20261101_000002	EXTRACT	PYTHON_RELAY	REPLAY:gpt-6.1-terra	EXTRACT_V1	당신은 카드 상품설명서에서 혜택 정보를 구조화하는 추출기입니다.\n입력은 페이지 전체 텍스트와 같은 페이지의 이미지입니다.\n\n역할을 구분합니다.\n- 텍스트: 혜택명, 금액, 비율, 횟수, 조건의 값을 확인합니다.\n- 이미지: 표의 행과 열을 보고 어떤 값이 어떤 혜택에 속하는지 판단합니다.\n\n규칙:\n1. 값은 페이지 텍스트에 있는 것만 씁니다. 이미지에서만 보이는 값은 unresolved에 적습니다.\n2. 원문에 없는 값, 구간, 우선순위를 추정하지 않습니다. 모르면 null 또는 UNKNOWN입니다.\n3. evidence.quote_txt는 페이지 텍스트를 그대로 복사합니다. 요약하거나 고치지 않습니다.\n4. 금액과 횟수는 정수로 씁니다. 예: 3천원은 3000, 월 30회는 30입니다. 원문 표기는 *_raw_txt에 그대로 둡니다.\n5. 표에서 읽은 값의 근거는 link_basis를 TABLE_IMAGE로 씁니다. 값과 혜택이 같은 문장에 있으면 SAME_TEXT입니다.\n6. 조건이 적용되는 범위를 scope로 구분합니다. 판단할 수 없으면 UNKNOWN입니다.\n7. 값이 같다는 이유로 한도를 공유한다고 판단하지 않습니다. 원문에 공유 표현이 있을 때만 shared_scope_txt를 씁니다.\n8. 해석하지 못한 문구는 버리지 말고 unresolved에 사유와 함께 적습니다.\n	{"image_dpi": 150, "input_mode": "TEXT_IMAGE", "schema_ver": "EXTRACT_SCHEMA_V1", "schema_sha256": "78e3aee5954a7ce5a75b7c5e181fd9af4750b584236719543f213dc5beb8b770", "split_rule_ver": "PAGE_V1"}	20261101_000002	PARTIAL	2026-11-01 01:14:29.972416+00	2026-11-01 01:14:39.868982+00	AI 입력 제외 페이지: [2]	2026-11-01 01:14:29.972416+00	SYSTEM	2026-11-01 01:14:39.868982+00	SYSTEM
20261102_000003	EXTRACT	PYTHON_RELAY	MANUAL_CURATED_SOURCE_V1	EXTRACT_V2	당신은 카드 상품설명서에서 혜택 정보를 구조화하는 추출기입니다.\n입력은 페이지 전체 텍스트와 같은 페이지의 이미지입니다.\n\n역할을 구분합니다.\n- 텍스트: 혜택명, 금액, 비율, 횟수, 조건의 값을 확인합니다.\n- 이미지: 표의 행과 열을 보고 어떤 값이 어떤 혜택에 속하는지 판단합니다.\n\n규칙:\n1. 값은 페이지 텍스트에 있는 것만 씁니다. 이미지에서만 보이는 값은 unresolved에 적습니다.\n2. 원문에 없는 값, 구간, 우선순위를 추정하지 않습니다. 모르면 null 또는 UNKNOWN입니다.\n3. evidence.quote_txt는 페이지 텍스트를 그대로 복사합니다. 요약하거나 고치지 않습니다.\n4. 금액과 횟수는 정수로 씁니다. 예: 3천원은 3000, 월 30회는 30입니다. 원문 표기는 *_raw_txt에 그대로 둡니다.\n5. 표에서 읽은 값의 근거는 link_basis를 TABLE_IMAGE로 씁니다. 값과 혜택이 같은 문장에 있으면 SAME_TEXT입니다.\n6. 조건이 적용되는 범위를 scope로 구분합니다. 판단할 수 없으면 UNKNOWN입니다.\n7. 값이 같다는 이유로 한도를 공유한다고 판단하지 않습니다. 원문에 공유 표현이 있을 때만 shared_scope_txt를 씁니다.\n8. 해석하지 못한 문구는 버리지 말고 unresolved에 사유와 함께 적습니다.\n9. 공통 브랜드 안내서는 혜택별 브랜드, 등급, 대상 카드, 선택서비스, 제외 카드와 제공 기간을 원문 그대로 기록합니다. 적용 대상과 기간을 뒷받침하는 인용은 APPLICABILITY 근거로 남깁니다. 문서에 없거나 다른 페이지와의 연결이 불명확하면 추정하지 말고 검토 대상으로 남깁니다.\n	{"coverage": "ONE_BENEFIT_ONLY", "image_dpi": 150, "merge_ver": "MERGE_V1", "input_mode": "TEXT_IMAGE", "schema_ver": "EXTRACT_SCHEMA_V2", "schema_sha256": "20479e63047478deb9c1b91fd20b119506381332ae02f53a5982732b0ba9ee7f", "split_rule_ver": "PAGE_V1", "paid_llm_called": false, "extraction_origin": "MANUAL_SOURCE_REVIEW"}	20261102_000004	SUCCEEDED	2026-11-02 08:44:16.538489+00	2026-11-02 08:44:16.538489+00	원문 수동 확인: Visa 컨시어지 1건만 발췌; 전체 AI 추출 결과가 아님	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261103_000004	EMBED	PYTHON_RELAY	text-embedding-3-small	BNFT_SEARCH_TXT_V1	혜택명 + 혜택 유형 + 이용처 또는 서비스 대상 + 핵심 혜택 내용	{"ids": null, "force": false, "table": "all", "result": {"card_bnft": {"failed": [], "embedded": 5}, "card_common_bnft": {"failed": [], "embedded": 0}}, "targets": 5, "dimensions": 1536}	\N	SUCCEEDED	2026-11-02 20:54:13.449749+00	2026-11-02 20:54:23.51704+00	\N	2026-11-02 20:54:13.449749+00	SYSTEM	2026-11-02 20:54:23.51704+00	SYSTEM
20261103_000005	EMBED	PYTHON_RELAY	text-embedding-3-small	BNFT_SEARCH_TXT_V1	혜택명 + 혜택 유형 + 이용처 또는 서비스 대상 + 핵심 혜택 내용	{"ids": ["20261103_000001"], "force": false, "table": "card_common_bnft", "result": {"card_common_bnft": {"failed": [], "embedded": 1}}, "targets": 1, "dimensions": 1536}	\N	SUCCEEDED	2026-11-02 21:07:30.700455+00	2026-11-02 21:07:34.194639+00	\N	2026-11-02 21:07:30.700455+00	SYSTEM	2026-11-02 21:07:34.194639+00	SYSTEM
\.


--
-- TOC entry 4377 (class 0 OID 20709)
-- Dependencies: 360
-- Data for Name: card_bnft; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_bnft (card_id, card_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, bnft_origin_cd, bnft_scope_cd, bnft_brand_opt_cds, bnft_cond_expr, rule_select_cd, rule_list, relation_list, verification_status_cd, bnft_valid_from, bnft_valid_to_excl, bnft_rule_txt, bnft_limit_txt, bnft_search_txt, bnft_embedding) FROM stdin;
5	20261102_000008	BRAND_7F12FC9CF2DC6811E91AE8A18EB1B6CE1379238A4FA2599FB407442C5F046BB9	Visa 컨시어지	SERVICE	BRAND_SERVICE	BRAND	{VISA_SIGNATURE_02}	\N	\N	[]	[]	PENDING_REVIEW	2026-01-01	2027-01-01	\N	\N	혜택명: Visa 컨시어지\n혜택 유형: 서비스 제공	[-0.031982422,0.0008010864,0.014099121,0.025527954,0.005340576,-0.029434204,-0.06695557,0.09265137,0.01940918,-0.047088623,0.02671814,-0.028625488,0.02645874,-0.029312134,-0.03829956,0.0088272095,-0.07183838,0.084228516,0.049591064,0.017791748,0.024856567,0.020965576,-0.021606445,0.009239197,0.0042266846,0.046051025,-0.062408447,-0.033416748,0.036071777,-0.051879883,0.045043945,-0.033935547,0.059570312,-0.026367188,0.0072631836,0.068603516,-0.00097465515,0.029953003,0.02684021,-0.007461548,0.009246826,-0.0020599365,0.038116455,-0.013725281,0.028167725,0.077941895,-0.007671356,0.026153564,-0.013389587,0.027709961,-0.02229309,-0.019836426,0.02128601,-0.040252686,-0.015914917,-0.036102295,0.037902832,-0.02067566,0.018997192,-0.011878967,0.036010742,-0.03250122,-0.01159668,0.03125,0.039154053,0.01977539,-0.009223938,-0.0064201355,-0.033599854,-0.0065727234,-0.018676758,0.031097412,0.04296875,0.0043258667,-0.010276794,0.015716553,-0.049591064,-0.0061950684,0.029891968,-0.03778076,-0.016677856,-0.024978638,-0.004814148,0.024902344,-0.030776978,-0.03237915,-0.07904053,-0.022415161,0.016677856,0.049224854,0.013008118,0.039093018,-0.04135132,0.015571594,0.06591797,0.018798828,-0.011436462,-0.029876709,-0.016708374,0.039978027,0.0036067963,-0.059783936,-0.017410278,-0.012016296,0.025115967,0.0062294006,-0.012939453,0.025527954,-0.019866943,0.020874023,-0.0039596558,0.0022335052,0.003314972,0.008163452,0.009994507,-0.03503418,0.03366089,-0.056152344,-0.028579712,0.012680054,0.008285522,-0.009407043,0.0006914139,-0.04296875,-0.037475586,0.026000977,-0.049926758,-0.0049362183,-0.07006836,0.013893127,-0.034179688,0.026473999,0.030273438,0.04006958,-0.016540527,-0.0231781,-0.013084412,0.010559082,-0.0051498413,0.019195557,-0.012077332,0.014846802,0.06323242,0.0236969,0.015914917,-0.04727173,-0.016601562,-0.0066070557,-0.025299072,0.04660034,-0.033813477,-0.021057129,-0.04534912,-0.00012010336,-0.033203125,-0.016586304,-0.025436401,0.033843994,-0.007472992,0.020843506,-0.024490356,-0.074035645,-0.04019165,0.00017511845,-0.008583069,-0.021484375,-0.022201538,0.06921387,-0.050872803,-0.022125244,0.006504059,-0.047607422,-0.083862305,0.044433594,-0.003900528,-0.016220093,0.07525635,-0.0035934448,-0.004951477,0.0070228577,0.018188477,0.07287598,-0.0015745163,-0.01828003,-0.037261963,-0.011627197,-0.016967773,-0.024276733,0.034362793,0.052581787,-0.019821167,-0.0209198,-0.0020809174,-0.0038757324,-0.027832031,-0.00036525726,-0.039520264,-0.034484863,0.0090789795,-0.05279541,-0.010658264,-0.04574585,0.015777588,-0.0062332153,-0.020477295,-0.054138184,-0.027511597,-0.0011615753,0.021896362,-0.011886597,0.0039253235,-0.016220093,-0.0048561096,0.010192871,0.008506775,-0.0003912449,0.033081055,-0.0070495605,0.020324707,0.001408577,-0.0262146,-0.01524353,0.036376953,0.0060653687,0.018936157,0.037109375,-0.036132812,-0.005012512,-0.028457642,-0.04373169,-0.023101807,0.042510986,0.019836426,-0.019638062,-0.050201416,0.049591064,0.032958984,0.0009417534,0.0014972687,-0.04147339,0.023513794,0.022064209,0.021392822,0.019134521,0.061706543,-0.019500732,0.021255493,-0.024795532,-0.002620697,9.763241e-05,0.016799927,0.009208679,-0.03253174,-0.018096924,0.029312134,0.028945923,0.013549805,0.030349731,0.0014925003,0.011260986,0.03656006,-0.024337769,-0.0026054382,0.015365601,-0.00207901,0.00932312,-0.0074043274,0.003271103,-0.0018577576,0.0032520294,-0.03010559,-0.026412964,0.033477783,0.015808105,-0.006881714,-0.012763977,0.016616821,0.010261536,0.036590576,0.044647217,0.00012743473,-0.0012187958,-0.036895752,-0.04220581,0.025817871,0.029876709,0.015594482,-0.0050964355,-0.04296875,0.0016145706,0.011917114,0.0040397644,0.0037288666,-0.07739258,-0.014228821,0.03363037,0.0011453629,0.011940002,0.05999756,0.014862061,0.012214661,0.0692749,-0.0015773773,0.0016784668,-0.044403076,0.05215454,0.016571045,0.03591919,-0.04937744,-0.036499023,-0.04736328,-0.033447266,-0.03845215,0.04638672,-0.006828308,-0.043792725,-0.025161743,0.00077676773,0.0016622543,-0.054351807,0.016098022,0.044403076,0.028457642,0.007259369,0.015991211,-0.01789856,-0.0096206665,-0.015266418,0.0035762787,-0.016357422,-0.022781372,0.0063438416,0.05822754,0.0038871765,-0.056793213,-0.02796936,-0.005859375,0.047943115,0.004764557,0.029785156,0.023330688,-0.023712158,-0.028167725,-0.011192322,0.0007147789,-0.03567505,0.06463623,0.03842163,0.038635254,0.031951904,0.004589081,-0.028320312,-0.023849487,0.0074882507,-0.015075684,-0.004878998,0.023757935,0.0020561218,-0.077941895,0.036254883,-0.036315918,0.008583069,0.0021533966,0.016937256,-0.010551453,0.02720642,-0.032562256,0.013114929,0.03704834,-0.011871338,-0.028030396,0.01725769,0.054138184,0.02041626,-0.0042686462,-0.028152466,0.024398804,0.049346924,0.053619385,-0.052459717,0.04046631,-0.063964844,-0.02255249,-0.01902771,0.030075073,0.013946533,5.477667e-05,-0.018066406,0.026901245,0.0055885315,0.042053223,0.038909912,-0.015075684,-0.03881836,0.02911377,-0.014976501,-0.029846191,0.028579712,-0.01876831,-0.028930664,0.03475952,-0.036712646,-0.002866745,-0.005580902,-0.020477295,-0.028793335,0.006389618,0.0056381226,-0.009712219,0.013053894,-0.009025574,-0.055389404,0.003932953,0.016616821,-0.00073480606,0.009536743,-0.07019043,0.0010166168,0.034332275,-0.054656982,-0.0072288513,0.016082764,-0.029647827,0.018005371,0.0055732727,-0.041229248,0.00043606758,0.04699707,0.002872467,0.0038833618,-0.042236328,-0.02810669,0.003648758,0.03878784,-0.022583008,0.026733398,0.015464783,-0.008232117,-0.010818481,0.006614685,0.0076789856,-0.0032463074,-0.022415161,-0.009765625,0.020507812,-0.035064697,0.022491455,0.022613525,0.0010261536,0.04864502,0.0058555603,0.03869629,-0.01828003,-0.020507812,-0.038085938,-0.064331055,0.02420044,-0.027877808,-0.013137817,-0.016098022,-0.0045318604,0.021377563,0.005958557,0.0056495667,0.062347412,-0.03353882,0.0042495728,-0.011550903,-0.025482178,-0.008102417,-0.020767212,0.03451538,0.04458618,0.015357971,-0.0045318604,-0.01890564,-0.012039185,-0.008255005,-0.01335907,0.02180481,-0.006095886,-0.023498535,-0.056732178,0.0107421875,0.052856445,0.042785645,0.072631836,-0.007881165,0.013320923,0.0025596619,0.041015625,0.008384705,0.01423645,-0.0056877136,0.003025055,0.026641846,0.014259338,0.00046420097,-0.03353882,0.016311646,-0.038208008,-0.07788086,-0.007850647,-0.023757935,0.020065308,0.028793335,0.018325806,-0.033233643,-0.0008325577,-0.010826111,-0.018920898,0.022384644,-0.023910522,0.006969452,-0.0013751984,-0.006942749,-0.007865906,0.013626099,-0.019165039,-0.0028419495,-0.026992798,0.0024547577,0.033355713,-0.007080078,0.0065345764,-0.0070343018,-0.0209198,-0.042785645,-0.00031590462,0.021835327,0.018127441,0.002254486,-0.029373169,0.0005712509,0.03262329,0.0096588135,-0.0015792847,0.023132324,0.03326416,0.0022678375,0.03656006,-0.008277893,0.011489868,0.0059432983,0.017318726,-0.032409668,0.0027389526,-0.018157959,0.012496948,0.031677246,-0.04736328,-0.044403076,0.012611389,0.0046195984,0.018707275,0.031463623,0.009284973,-0.004585266,-0.0063476562,-0.0018634796,0.018218994,0.015426636,-0.036132812,-0.016693115,-0.027954102,0.049682617,0.061553955,0.00087976456,-0.03189087,-0.010787964,-0.036499023,0.0017242432,0.011650085,0.05886841,0.033721924,-0.013694763,-0.034179688,-0.03579712,-0.02381897,0.015838623,0.014953613,0.023117065,-0.010498047,0.015274048,0.04168701,-0.01977539,-0.007797241,-0.0013837814,0.0024604797,0.008682251,0.020324707,0.01737976,0.008491516,-0.03845215,-0.021392822,-0.007232666,-0.0076065063,0.023483276,0.026611328,-0.038085938,0.018341064,-0.009674072,0.0076408386,-0.04458618,-0.033843994,0.0051498413,0.018615723,-0.027359009,0.02935791,-0.008964539,0.009162903,0.0017766953,0.022857666,-0.020645142,-0.05117798,-0.0003581047,-0.07702637,-0.014137268,-0.018249512,0.005126953,-0.011360168,-0.030654907,-0.007156372,-0.011238098,-0.0002655983,0.026397705,-0.022720337,-0.038238525,-0.05227661,0.017990112,0.013114929,0.02532959,0.03152466,-0.03967285,0.028411865,0.0317688,-0.02267456,0.0034809113,0.03555298,-0.009933472,-0.006259918,-0.009063721,0.0061149597,-0.044036865,0.036499023,-0.0010309219,-0.01146698,-0.017562866,0.015571594,0.0368042,0.02557373,-0.043273926,0.014259338,-0.04611206,0.018936157,0.0037555695,0.004005432,0.026290894,0.06524658,0.025268555,-0.01687622,0.040161133,-0.031982422,0.0060577393,0.013786316,0.0154953,0.027709961,0.011665344,-0.00048828125,-0.031677246,-0.010276794,0.008903503,-0.0050582886,-0.034820557,0.010032654,0.027709961,0.0076141357,-0.001996994,0.034820557,0.011482239,-0.017227173,-0.013999939,-0.009757996,0.016906738,0.006919861,-0.016662598,-0.023773193,-0.025817871,0.017959595,0.0014219284,0.015007019,-0.0018186569,0.053833008,-0.0042877197,0.004623413,0.024459839,0.031188965,-0.008239746,-0.008674622,-0.0043525696,0.00020229816,-0.030944824,0.029327393,-0.03781128,-0.04547119,-0.017425537,0.009483337,-0.024337769,0.03213501,0.0044174194,-0.021499634,-0.005138397,-0.021774292,-0.011001587,-0.016952515,0.010040283,-0.033813477,-0.0069389343,0.023422241,-0.004749298,-0.03994751,0.012466431,-0.00957489,-0.00085926056,-0.015487671,0.03878784,-0.0054244995,-0.009727478,-0.0055503845,0.016098022,-0.0019931793,-0.008964539,-0.014160156,-0.0074768066,0.04083252,-0.0039634705,-0.048065186,0.009689331,-0.04800415,-0.017410278,0.04046631,-0.043548584,0.028152466,-0.018875122,-0.011657715,-0.0057144165,-0.032928467,-0.0053710938,-0.018218994,0.024520874,-0.005924225,0.0019626617,0.019577026,-0.009559631,0.011199951,-0.0010261536,0.021835327,-0.0015974045,0.009094238,-0.015182495,0.0022830963,0.044769287,0.006000519,0.016677856,0.024551392,0.0048599243,-0.040771484,-0.008666992,-0.05126953,0.003124237,0.020446777,0.0057907104,-0.045288086,0.019973755,0.03781128,0.013259888,-0.016952515,-0.056427002,-0.00459671,0.018218994,0.023162842,-0.020095825,0.022125244,-0.014259338,-0.029205322,0.013015747,0.0064849854,-0.008415222,-0.0008158684,-0.032714844,0.0113220215,-0.03591919,-0.012298584,0.0053138733,-0.019943237,0.012779236,-0.016647339,-0.013549805,0.005844116,-0.013397217,-0.016021729,-0.0023212433,0.0047302246,0.03994751,-0.0039367676,0.002872467,-0.027267456,-0.015975952,0.008125305,-0.0062026978,-0.021942139,0.017913818,-0.044433594,-0.011428833,-0.002960205,0.008033752,-0.009819031,0.006668091,-0.025848389,-0.028015137,0.04623413,-0.037872314,-0.008308411,0.022964478,0.00089788437,0.0026245117,-0.034606934,-0.014503479,-0.025817871,-0.002614975,0.01663208,0.04232788,-0.0020580292,-0.009239197,0.015266418,0.002878189,-0.00038027763,0.031921387,-0.01876831,0.009361267,0.031799316,0.011779785,-0.02645874,-0.010116577,-0.04876709,-0.008979797,-0.0070266724,-0.021881104,0.019561768,0.01739502,-0.0076065063,-0.02355957,0.0024585724,0.009559631,0.04458618,-0.022140503,-0.014633179,0.018417358,-0.036590576,0.011756897,-0.0076789856,0.004196167,-0.0090408325,-0.046844482,0.053375244,0.016342163,0.011192322,0.019515991,0.013954163,-0.016326904,-0.025253296,-0.033813477,-0.006752014,-0.02897644,0.046447754,0.02281189,-0.0046043396,0.026733398,-0.045928955,-0.0035896301,0.041046143,0.00818634,-0.017196655,0.01676941,0.007232666,0.024993896,-0.01020813,0.018737793,-0.014022827,-0.027679443,0.033813477,0.033355713,0.028274536,-0.022338867,0.009689331,-0.017669678,-0.030670166,0.060272217,-0.013000488,-0.0025978088,-0.03933716,-0.015991211,-0.019607544,-0.0050315857,0.021484375,0.007888794,0.025817871,-0.024917603,0.014297485,0.011650085,-0.031341553,-0.038330078,-0.0057640076,-0.010803223,0.032592773,0.010231018,-0.026260376,0.020080566,0.03942871,0.00434494,0.0058631897,-0.025894165,0.002204895,-0.007911682,-0.011489868,-0.05117798,-0.034820557,-0.03186035,0.014518738,0.011108398,0.010658264,0.006248474,-7.3969364e-05,-0.00819397,-0.015419006,0.013397217,-0.023590088,0.0019779205,0.016281128,-0.014793396,0.050354004,0.012504578,-0.045043945,-0.006881714,0.032836914,-0.025802612,0.03302002,-0.013557434,-0.00970459,-0.007820129,-0.0016870499,0.0018081665,0.0020809174,-0.028396606,-0.012428284,0.0042381287,-0.010108948,0.03543091,0.014976501,-0.009208679,0.0067634583,-0.022262573,0.016021729,-0.018112183,0.007965088,0.007587433,0.014457703,0.045410156,0.041290283,0.013595581,-0.0006251335,0.03387451,0.031555176,0.014533997,0.0017948151,0.0692749,0.003129959,0.0068092346,0.0008711815,0.0063972473,-0.008262634,0.024658203,0.051483154,0.033325195,-0.039245605,-0.0076179504,-0.033050537,0.017120361,0.03930664,-0.006313324,-0.019165039,0.03302002,0.004016876,0.002565384,-0.007881165,-0.029434204,-0.014228821,0.026611328,-0.024673462,-0.039276123,0.020263672,-0.032318115,-0.009971619,-7.0273876e-05,0.046722412,-0.0104904175,-0.01374054,0.007209778,0.011077881,-0.014442444,0.015975952,-0.04321289,-0.012458801,0.009124756,-0.016571045,0.0061454773,0.0070114136,-0.020446777,0.04711914,-0.0034294128,0.016464233,0.03378296,-0.014678955,0.022644043,0.009895325,-0.0071372986,0.039123535,-0.014404297,0.004371643,-0.0069465637,-0.027908325,-0.0390625,0.003528595,0.012611389,-0.04675293,0.009399414,-0.032684326,-0.015655518,0.024673462,0.023239136,-0.0032958984,0.010971069,-0.00022995472,0.0057296753,0.0033817291,0.009208679,0.042236328,0.0015544891,0.04119873,-0.019927979,-0.005039215,-0.036956787,-0.017623901,0.009994507,-0.015701294,0.008773804,0.0287323,-0.00095653534,-0.011558533,0.023132324,-0.0002887249,-0.026641846,0.014129639,0.004901886,0.017227173,-0.001871109,-0.012275696,-0.0077781677,-0.039367676,-0.017501831,0.019302368,0.019119263,0.023834229,-0.016937256,0.026947021,-0.016830444,-0.02331543,-0.00047135353,-0.014526367,0.006767273,-0.005092621,0.016860962,0.0040779114,0.010818481,-0.0015859604,-0.0048179626,0.0074424744,-0.008224487,0.014137268,0.018585205,-0.013473511,0.017501831,0.005065918,0.04547119,-0.018585205,-0.038726807,0.016784668,0.034057617,0.04046631,-0.0069274902,0.013633728,0.034606934,0.041412354,-0.00081920624,0.00029182434,0.006587982,-0.0024795532,-0.014266968,-0.07128906,-0.00068473816,0.013908386,0.00064229965,0.044189453,-0.029434204,-0.029678345,-0.01159668,0.016433716,-0.03491211,-0.006198883,-0.0119018555,-0.023162842,-0.017807007,0.009010315,0.018066406,-0.005558014,0.019378662,-0.032226562,0.0051612854,-0.0045394897,0.03765869,0.039001465,-0.0013875961,-0.0021972656,-0.023544312,0.007297516,-0.008544922,0.0036010742,-0.02809143,-0.013183594,0.025848389,-0.00844574,-0.0064353943,-0.012748718,-0.026657104,0.00699234,0.0040245056,-0.04800415,0.05581665,-0.01158905,0.010192871,0.020584106,-0.00037407875,0.012786865,-0.0059890747,0.0077590942,0.015464783,0.028076172,0.0052337646,0.005744934,-0.001291275,0.016860962,0.009277344,0.016708374,-0.010559082,-0.034301758,-0.021575928,0.02053833,0.017120361,-0.031921387,0.02305603,-0.026321411,0.021911621,-0.008903503,-0.0079956055,0.019332886,0.056518555,0.0031661987,-0.012809753,0.018508911,0.018173218,-0.037139893,-0.000890255,-0.024383545,-0.0026016235,0.0024299622,0.039611816,0.018676758,-0.004096985,0.0021305084,0.0026397705,-0.014533997,0.043762207,0.009841919,-0.017211914,0.0016736984,0.035186768,-0.0072288513,0.030044556,-0.015586853,-0.019500732,-0.00010186434,-0.0019254684,-0.0034217834,-0.0021572113,-0.034179688,0.0126953125,-0.028015137,0.0028514862,-0.013717651,0.009277344,0.0035171509,-0.005405426,0.014259338,-0.06439209,0.00699234,-0.01234436,0.016921997,-0.007987976,-0.005405426,-0.004562378,-0.028930664,0.0054016113,-0.004508972,0.0059280396,0.02861023,-0.020446777,-0.01638794,0.029968262,0.055877686,0.012046814,-0.0006957054,-1.4305115e-05,0.018173218,-0.015731812,-0.004501343,0.02796936,0.0068092346,0.011329651,0.0055160522,-0.015335083,-0.018997192,0.01991272,-0.0035438538,-0.020385742,0.0030727386,-0.01687622,0.0012578964,0.029205322,-0.0053482056,-0.0029125214,0.05682373,-0.013908386,-0.03451538,-0.004421234,-0.009239197,0.031204224,0.015960693,0.005153656,-0.007949829,-0.0010442734,-0.044403076,-0.0110321045,0.027160645,0.009407043,-0.017059326,0.0010261536,0.020019531,-0.0011663437,-0.0067253113,-0.016067505,-0.03161621,0.0006504059,0.008613586,0.040649414,-0.014846802,0.016708374,-0.020935059,-0.027679443,-0.004119873,-0.0093307495,-0.010269165,0.026733398,0.010192871,-0.017288208,-0.006515503,0.012176514,-0.009918213,-0.005050659,0.0015363693,-0.024154663,-0.020462036,-0.0030269623,0.0067977905,-0.026168823,0.012611389,0.03894043,0.027633667,-0.0132751465,0.027313232,-0.0054893494,-0.037628174,0.019042969,0.0037593842,-0.010192871,0.026779175,-0.007511139,0.017059326,-0.016494751,0.009391785,-0.0657959,0.0043640137,-0.0070991516,-0.01676941,-0.02255249,0.036071777,0.033325195,0.013183594,-0.029525757,-0.017410278,-0.027053833,0.024520874,-0.0010461807,-0.017227173,0.0066871643,0.014526367,0.0047721863,-0.0006875992,-0.018554688,0.015525818,-0.0025806427,-0.011650085,0.0068244934,-0.012207031,-0.038024902,-0.007347107,-0.012329102,0.011276245,0.05206299,0.0054740906,0.018249512,0.055389404,-0.011909485,-0.0022659302,-0.0044136047,0.027511597,-0.03604126,-0.0259552,0.00447464,-0.017288208,-0.0031089783,0.023513794,0.014549255,-0.020324707,-0.004108429,0.016220093,-0.00066185,0.038635254,0.034240723,0.023910522,0.026016235,-0.0062675476,0.013504028,-0.00466156,0.033721924,0.015991211,0.010520935,-0.028747559,-0.001578331,0.0039978027,-0.011558533,-0.01763916,0.007007599,-0.0029945374,0.027816772,-0.013534546,-0.017959595,-0.0012645721,0.00051498413,0.015197754,0.0061950684,-0.020217896,-0.0074882507,0.013587952,0.034698486,0.017440796,-0.012275696,0.008178711,-0.029647827,-0.024139404,-0.0146865845,-0.0026569366,-0.0051612854,0.013320923,-0.027557373,-0.009971619,-0.00054836273,0.03778076,-0.026168823,0.0030174255,-0.035949707,-0.029388428,-0.02571106,-0.040252686,-0.006214142,-0.030288696,0.023376465,-0.017959595,-0.009414673,-0.012435913,-0.01449585,-0.022537231,0.052520752,0.0014162064,-0.014007568,0.024017334,0.009033203,-0.0149383545,-0.0079193115,0.0037117004,0.016647339,-0.017654419,0.0027370453,0.00868988,0.018600464,0.0025596619,0.016067505,-0.0052948,-0.027893066,0.005973816,0.02017212,-0.0066070557,-0.009750366,-0.017486572,0.03817749,0.02532959,0.016647339,0.0098724365,-0.0014886856,0.0013847351,-0.014137268,-0.005466461,0.001291275,0.0236969,0.007701874,-0.008621216,0.026321411,0.013809204,0.010398865,-0.040008545,0.0076065063,-0.0093307495,0.023132324,-0.0018577576,0.019805908,-0.010887146,-0.03213501,-0.04232788,0.0060310364,-0.003528595,-0.022277832,0.008712769,-0.005886078,0.0104904175,0.03677368,-0.009292603,0.035217285,0.025253296,-0.006832123,0.011680603,0.002702713,0.018203735,0.0519104,0.0064201355,0.00034213066,-0.007801056,0.01802063,0.043823242,0.01360321,0.0045776367,-0.023880005,-0.0044937134,-0.015533447,-0.029434204,0.0024871826,-0.04748535,0.015487671,0.010391235,0.004135132,0.008354187,-0.024261475,0.010871887,-0.034240723,0.048431396,-0.017807007,0.021957397,0.0044441223,0.016021729,0.0317688,0.030090332,-0.009719849,-0.022781372,0.0009384155,0.006664276,0.014602661,-0.022338867,0.018371582,-0.031341553,0.06567383,0.0002593994,-0.013885498,-0.023742676,0.012329102,0.048706055,-0.024337769,-0.025650024,-0.020553589,0.025909424,-0.002166748,-0.024124146,-0.0056648254,-0.009468079,0.008659363,-0.0013084412,0.04534912,0.02607727,-0.014305115,-0.019378662,0.009727478,-0.032073975,0.05923462,0.029693604,0.012741089,-0.010253906,-0.025939941,-0.004196167,-0.0011959076]
2	20261101_000001	BNFT_86FA3F68DB0B	ONE PICK 편의점·카페 캐시백	CASHBACK	LOCAL	PRODUCT	\N	\N	\N	[{"rule_key": "one_pick_100", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_one_pick_100", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 3000, "cond_raw_txt": "결제 건당\\n3천원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "value_num": 100, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "CU", "target_key": "CU", "target_type_cd": "MERCHANT"}, {"target_nm": "GS25", "target_key": "GS25", "target_type_cd": "MERCHANT"}, {"target_nm": "세븐일레븐", "target_key": "세븐일레븐", "target_type_cd": "MERCHANT"}, {"target_nm": "메가MGC커피", "target_key": "메가MGC커피", "target_type_cd": "MERCHANT"}, {"target_nm": "이디야커피", "target_key": "이디야커피", "target_type_cd": "MERCHANT"}, {"target_nm": "컴포즈커피", "target_key": "컴포즈커피", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}, {"rule_key": "one_pick_500", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_one_pick_500", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 10000, "cond_raw_txt": "결제 건당\\n1만원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "value_num": 500, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "CU", "target_key": "CU", "target_type_cd": "MERCHANT"}, {"target_nm": "GS25", "target_key": "GS25", "target_type_cd": "MERCHANT"}, {"target_nm": "세븐일레븐", "target_key": "세븐일레븐", "target_type_cd": "MERCHANT"}, {"target_nm": "메가MGC커피", "target_key": "메가MGC커피", "target_type_cd": "MERCHANT"}, {"target_nm": "이디야커피", "target_key": "이디야커피", "target_type_cd": "MERCHANT"}, {"target_nm": "컴포즈커피", "target_key": "컴포즈커피", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}]	[]	PENDING_REVIEW	\N	\N	결제 건당 3천원 이상 시 100원 / 결제 건당 1만원 이상 시 500원	월 5천원 / 일 1회 / 월 30회	혜택명: ONE PICK 편의점·카페 캐시백\n혜택 유형: 캐시백\n이용처: CU, GS25, 세븐일레븐, 메가MGC커피, 이디야커피, 컴포즈커피\n혜택 내용: 결제 건당 3천원 이상 시 100원, 1만원 이상 시 500원 캐시백	[-0.022888184,-0.056274414,-0.0003824234,0.023803711,-0.014587402,-0.043273926,-0.08520508,0.07659912,0.0031547546,-0.048034668,0.043548584,-0.03366089,-0.0071029663,-0.018966675,0.023071289,0.0067710876,-0.045013428,0.035308838,-0.023803711,0.028823853,-0.03591919,0.03866577,0.028549194,0.031051636,0.00012242794,0.025268555,-0.030303955,-0.025802612,0.021392822,-0.035736084,-0.017089844,-0.02268982,0.031158447,-0.038024902,-0.023208618,0.052947998,-0.005748749,0.039245605,0.03555298,-0.027709961,-0.029510498,-0.018798828,0.011924744,-0.04876709,0.025009155,0.01789856,0.019546509,0.013648987,-0.015853882,0.033081055,-0.02861023,0.032440186,0.006526947,-0.059631348,-0.009117126,-0.0637207,-0.037322998,0.01802063,0.055847168,0.005130768,-0.018157959,-0.04071045,-0.023834229,-0.0129776,0.04675293,-0.0049438477,-0.009841919,0.0046691895,-0.03479004,0.02659607,-0.03338623,0.026809692,0.042755127,-0.03591919,0.00472641,-0.016403198,0.004875183,-0.012672424,0.050201416,-0.04031372,0.0052757263,-0.067871094,-0.064575195,0.016723633,0.035705566,-0.057037354,-0.074279785,-0.019226074,-0.025650024,0.04031372,-0.013343811,-0.050964355,-0.008888245,0.018615723,0.01763916,0.005027771,-0.048034668,0.0018663406,-0.025268555,0.00957489,0.027297974,-0.05596924,0.0067329407,-0.043548584,-0.0053367615,0.040222168,0.016143799,0.05731201,0.019882202,-0.012901306,-0.024124146,-0.00655365,-0.043182373,0.04156494,0.019042969,-0.025680542,0.028121948,-0.027191162,-0.0413208,0.0045394897,0.026535034,0.030395508,0.0014009476,-0.083618164,-0.0335083,0.015823364,-0.002916336,-0.0020446777,-0.027770996,0.027191162,-0.026382446,0.009963989,-0.009971619,0.038360596,0.028915405,-0.005657196,0.0051078796,-0.019165039,-0.013435364,-0.0060157776,-0.017471313,-0.016281128,0.05117798,0.017669678,-0.018066406,-0.06616211,-0.03857422,-0.019256592,-0.033294678,0.022857666,-0.025024414,-0.059753418,-0.04586792,-0.04071045,-0.023834229,-0.02368164,-0.0022449493,0.054748535,-0.050323486,-0.0027542114,-0.032928467,-0.024490356,-0.05871582,0.022415161,-0.014465332,0.042907715,-0.037719727,0.0019741058,-0.0309906,-0.008743286,-0.025131226,-0.01474762,-0.015335083,0.01158905,-0.017120361,-0.0034294128,0.04928589,-0.00667572,-0.043914795,0.040100098,0.012802124,0.05041504,0.06555176,-0.021865845,-0.03604126,-0.0335083,-0.016433716,-0.036346436,0.015289307,0.03845215,0.018569946,-0.0011940002,-0.004108429,-0.014274597,-0.004180908,0.004886627,-0.008743286,0.03024292,0.0055503845,-0.033477783,-0.037109375,0.0012369156,0.016433716,0.05899048,-0.0040397644,-0.017913818,-0.056549072,0.010971069,0.047180176,-0.009529114,0.021560669,0.0058288574,-0.03768921,0.0065612793,-0.024993896,0.0118255615,0.020050049,0.026870728,-0.03314209,0.04058838,-0.0044555664,-0.022094727,0.0138549805,-0.0002425909,0.02243042,0.016036987,0.01637268,0.0010271072,0.00042891502,-0.04486084,-0.0019721985,0.027923584,-0.008743286,-0.013084412,-0.022842407,0.0927124,0.021026611,0.026367188,-0.025909424,-0.059570312,0.023635864,0.05682373,-0.009231567,0.009918213,0.019119263,0.013305664,0.005683899,0.016281128,0.011924744,-0.03302002,0.00018560886,0.042236328,-0.02079773,-0.025283813,0.034332275,-0.013145447,0.031921387,0.020477295,0.035858154,-0.02784729,0.053497314,0.0028419495,-0.035125732,0.0057640076,-0.014732361,0.00022137165,0.021560669,-0.008415222,-0.002380371,0.04663086,-0.032043457,0.011810303,0.035461426,0.016143799,0.024642944,-0.03793335,0.010040283,0.0034618378,-0.0231781,0.027038574,-0.0390625,-0.012001038,-0.009613037,-0.027862549,0.033966064,0.032989502,0.03338623,-0.008270264,-0.0004911423,0.012107849,0.00017046928,-0.07397461,-0.02394104,-0.06677246,0.011054993,0.0027980804,-0.019363403,0.0020332336,0.0012283325,-0.0070877075,0.012901306,0.092163086,-0.057556152,-0.043395996,0.0049705505,0.046813965,0.0055618286,0.057739258,0.0033512115,0.008163452,-0.036254883,-0.048675537,0.03503418,0.02734375,0.031082153,-0.0066375732,0.00969696,-0.014968872,0.038604736,-0.029830933,0.05380249,-0.004219055,-0.004627228,0.029144287,-0.0046920776,-0.008903503,0.01197052,-0.005443573,-0.007255554,0.015312195,0.022537231,-0.011871338,0.050628662,0.014732361,-0.07458496,-0.025436401,0.023361206,0.02279663,-0.044128418,0.008140564,0.039855957,-0.04208374,0.004878998,-0.012329102,-0.0074310303,-0.060455322,0.07733154,0.035736084,0.026229858,0.03741455,-0.01777649,-0.007095337,0.017532349,-0.00011765957,-0.013114929,0.012260437,-0.020980835,-0.02696228,-0.07183838,0.014533997,-0.023971558,0.027862549,0.049591064,-0.0032863617,0.025817871,0.019760132,-0.035064697,-0.018478394,-0.004047394,0.0072402954,-0.018997192,0.04144287,0.001420021,0.0009975433,-0.023651123,0.0059127808,0.021057129,0.024856567,0.04977417,-0.05041504,0.03756714,-0.05392456,-0.022262573,0.008659363,0.06402588,-0.04336548,0.048553467,-0.023620605,0.034454346,0.0050468445,-0.019378662,0.0118255615,-0.016693115,-0.0524292,0.0135650635,-0.0090408325,-0.04345703,0.03704834,-0.06341553,-0.0034122467,0.015068054,-0.030792236,-0.04550171,-0.01374054,-0.015548706,0.024276733,0.009674072,0.01802063,0.004142761,-0.010475159,0.02305603,-0.057525635,0.024627686,0.037353516,0.031021118,-0.011711121,-0.033203125,-0.003019333,-0.039642334,-0.04168701,0.016342163,-0.037200928,-0.06427002,-0.007698059,0.021759033,-0.0317688,-0.0006303787,0.066345215,-0.012664795,-0.013435364,0.013305664,-0.01928711,-0.0068359375,0.014862061,-0.06060791,-0.033233643,0.006023407,0.03112793,-0.032287598,-0.028289795,-0.06274414,0.025314331,-0.028411865,0.002943039,0.0007109642,0.00497818,0.025680542,0.023147583,-0.0037879944,-0.014541626,-0.053100586,0.02784729,-0.018676758,-0.008468628,-0.022537231,0.025238037,0.06915283,-0.05508423,0.014167786,-7.2836876e-05,-0.019134521,-0.00242424,0.0073661804,-0.0057373047,0.03463745,0.017715454,-9.441376e-05,0.026428223,0.013748169,0.027557373,-0.032989502,0.025436401,0.0029697418,0.04067993,0.02368164,-0.033935547,0.012924194,0.019119263,0.0124053955,0.017074585,-0.042114258,-0.0056877136,-0.031799316,-0.008712769,-0.009712219,0.026535034,0.08544922,0.031585693,-0.0073242188,-0.055236816,0.008056641,0.0011701584,0.006877899,-0.007896423,-0.02545166,0.025314331,0.020568848,-0.06512451,-0.012397766,-0.020324707,0.006164551,-0.039520264,-0.02633667,0.01914978,-0.030731201,0.025741577,-0.010955811,-0.02998352,-0.021148682,-0.011207581,-0.025390625,0.027557373,-0.010612488,-0.041015625,-0.0028800964,-0.019073486,-0.012550354,0.029281616,-0.017868042,-0.0030326843,-0.01965332,0.012329102,0.044006348,-0.02722168,0.00969696,-0.015060425,-0.006385803,-0.08782959,0.011817932,0.010635376,-0.0022640228,-0.0340271,0.018295288,0.0018672943,-0.0014047623,-0.033416748,-0.016845703,0.050750732,0.009017944,-0.014854431,0.009933472,-0.058685303,-0.0018320084,0.002401352,-0.021499634,-0.04751587,0.014907837,0.012237549,0.021209717,0.037841797,-0.0110321045,-0.02017212,0.0067253113,-0.009391785,0.022521973,-0.013534546,0.038116455,-0.019851685,0.020050049,-0.039916992,0.0074691772,-0.0067825317,0.0030536652,0.040924072,-0.011230469,0.04736328,0.014724731,0.04550171,-0.026824951,-0.048095703,-0.038238525,0.05859375,0.014968872,0.03366089,0.004558563,0.002948761,-0.020767212,0.0063705444,-0.041503906,0.007575989,0.0022678375,-0.025802612,0.004737854,0.017074585,0.023376465,-0.0006799698,-0.014007568,0.015991211,0.012054443,-0.0149383545,-0.0058784485,0.027801514,-0.019866943,-0.009819031,-0.0446167,-0.006275177,-0.02305603,0.0440979,0.04373169,-0.02909851,-0.013267517,0.003370285,-0.012084961,-0.020889282,-0.01184845,-0.020721436,0.0023021698,0.023117065,0.02104187,-0.017089844,0.035614014,0.031051636,0.0014896393,-0.02116394,-0.019866943,0.004837036,-0.024887085,0.019088745,0.013252258,0.007926941,-0.023803711,0.033050537,-0.0035552979,-0.037994385,-0.027191162,0.0052375793,0.010620117,-0.04534912,-0.017410278,-0.015701294,0.03237915,0.0067443848,0.0206604,-0.027389526,0.011817932,0.03704834,-0.024734497,0.016036987,0.032226562,-0.031143188,0.014099121,-0.017532349,0.023895264,-0.015045166,0.0025672913,-0.0138549805,-0.007419586,-0.011550903,0.012565613,-0.012748718,0.04550171,-0.0126571655,0.0053977966,-0.057434082,0.020904541,-0.0040664673,0.008895874,0.014778137,0.0068626404,0.00856781,-0.0055656433,0.05331421,-0.01737976,-2.670288e-05,-0.020263672,0.022644043,-0.013343811,-0.008056641,0.004310608,-0.020523071,-0.011016846,0.025131226,0.0335083,0.036987305,-0.01890564,0.041107178,0.027435303,-0.017532349,0.01826477,-0.010177612,0.02178955,0.023406982,-0.038238525,-0.021865845,0.017120361,-0.009666443,0.00087690353,-0.012527466,0.024414062,0.013931274,-0.0045051575,0.0137786865,0.054016113,0.055633545,0.0028896332,-0.004020691,0.0066604614,0.013031006,0.023513794,-0.0027446747,-0.027282715,-0.0057525635,0.038848877,-0.011016846,-0.024749756,0.0074539185,0.043762207,0.018127441,0.033233643,-0.026229858,0.010116577,-0.024215698,-0.004371643,-0.005760193,0.016403198,-0.004798889,0.0003182888,0.0046577454,0.013702393,0.0014839172,-0.019073486,0.0017976761,-0.011154175,-0.0345459,-0.0102005005,0.00059986115,-0.021774292,-0.018753052,-0.0059318542,0.008293152,0.017059326,-0.012184143,-0.011291504,0.010574341,-0.015205383,0.015525818,-0.057769775,0.0029563904,-0.031204224,0.00047564507,0.009033203,-0.030685425,0.002166748,-0.041778564,-0.025497437,-0.0046081543,-0.011871338,-0.038726807,-0.03237915,-0.0011014938,0.008666992,0.004928589,0.033447266,0.025344849,0.022750854,-0.009681702,-0.0073509216,-0.004512787,-0.005344391,-0.0057868958,-0.013160706,0.024551392,-0.032226562,0.0042800903,-0.0020637512,-0.0007109642,-0.025344849,-0.0309906,-0.030029297,-0.0024776459,0.033294678,-0.0063095093,-0.015129089,0.02432251,0.052856445,-0.0035705566,-0.011238098,-0.02293396,-0.029022217,-0.0054969788,0.013290405,-0.01625061,0.007873535,0.0029830933,0.005027771,-0.016571045,-0.011787415,-0.037841797,0.0037002563,0.006690979,0.027511597,-0.022521973,-0.023406982,-0.016708374,0.0014762878,0.04675293,-0.013755798,-0.054016113,0.03567505,0.029403687,-0.021987915,-0.007255554,-0.0066108704,0.0028305054,0.04559326,-0.021469116,-0.003112793,0.047088623,-0.009117126,-0.056152344,0.0003736019,0.025177002,0.01838684,0.034423828,-0.028015137,-0.015975952,0.0011806488,0.004837036,-0.01751709,0.020767212,0.02178955,-0.01777649,-0.00036525726,0.018463135,0.0041770935,0.017440796,-0.03503418,-0.0020008087,-0.0027503967,-0.022033691,-0.01939392,-0.008613586,0.010108948,-0.0129852295,-0.0011892319,-0.03250122,0.03186035,0.009986877,-0.050445557,0.01966858,0.00598526,0.025115967,0.015289307,-0.037628174,-0.025283813,0.0068969727,-0.015220642,-0.0005092621,-0.0037212372,0.04788208,-0.0021381378,-0.012001038,-0.0028800964,0.020736694,0.060302734,0.010002136,0.0030784607,-0.0126953125,0.0050201416,-0.0049858093,-0.022201538,0.002023697,-0.018371582,-0.07678223,0.013580322,0.03527832,0.00274086,0.02128601,0.031051636,-0.009262085,-0.008453369,-0.049591064,0.007926941,-0.04824829,0.032440186,-0.01499939,0.038635254,0.043701172,0.0017518997,0.0016021729,0.023910522,-0.027877808,-0.013595581,0.020080566,0.016998291,0.06329346,-0.027328491,-0.005619049,-0.0072669983,-0.016464233,0.05444336,-0.0070991516,0.026611328,0.0004632473,-0.015357971,-0.0138549805,-0.005290985,0.0034427643,0.022094727,0.0047340393,0.012901306,0.01953125,-0.04537964,-0.018981934,-0.005592346,0.04650879,-0.009895325,-0.0014066696,-0.0063819885,0.024993896,-0.014015198,-0.039215088,0.016967773,0.015060425,0.03302002,-0.0028095245,-0.04449463,0.017837524,0.02029419,-0.0011892319,-0.015548706,0.0036029816,0.007965088,-0.019195557,-0.008460999,-0.022827148,0.002155304,0.022460938,0.028518677,0.0137786865,0.018203735,-0.0022277832,0.037017822,-0.009468079,-0.026763916,-0.022903442,-0.012367249,-0.0022277832,-0.009460449,-0.016464233,0.013694763,-0.006164551,-0.006160736,-0.009674072,0.013908386,-0.0042495728,0.014518738,-0.04611206,-0.019546509,-0.011390686,0.0036029816,-0.038360596,0.013114929,-0.00440979,-0.0031394958,0.007965088,-0.011016846,0.01876831,0.032592773,0.014808655,-0.006790161,-0.021438599,0.00630188,-0.018310547,0.0048446655,-0.009887695,-0.01663208,0.030151367,0.034240723,0.048858643,0.02029419,0.013038635,-0.00039744377,0.044067383,0.011604309,0.0030345917,-0.010848999,0.00762558,0.022567749,0.031204224,-0.008491516,0.03338623,0.0057907104,0.010040283,-0.011772156,0.0047912598,-0.007320404,0.018417358,0.039611816,-0.03805542,0.002922058,0.05581665,-0.0010824203,-0.006149292,-0.009635925,-0.0602417,-0.010093689,0.031021118,0.00022733212,0.009178162,-0.0049934387,-0.019256592,-0.023727417,-0.024887085,-0.0025196075,0.026916504,0.026687622,-0.015342712,0.0016756058,-0.020599365,0.058044434,-0.0013990402,0.03378296,-0.024887085,-0.009223938,-0.026397705,-0.018447876,-0.005432129,-0.01499939,-0.03756714,0.031158447,0.01965332,-0.030563354,0.036987305,-0.030761719,0.037902832,0.018997192,-0.00969696,0.009727478,0.008125305,-0.026107788,-0.02532959,0.001332283,0.0016527176,-0.026901245,0.032562256,-0.007598877,-0.018371582,0.014404297,0.01361084,0.0128479,0.008491516,0.018920898,-0.024154663,-0.0039043427,0.012329102,0.005432129,0.0109939575,0.006980896,-0.0065307617,-0.017974854,-0.04083252,0.02178955,-0.0035114288,-0.032226562,0.00084638596,0.009635925,-0.012031555,-0.009231567,-0.0059776306,-0.0060577393,-0.0046958923,0.00843811,-0.010772705,0.023742676,-0.029129028,0.013725281,0.0029335022,-0.020874023,-0.054901123,0.0066070557,0.055908203,-0.012481689,-0.01184082,0.0005249977,-0.022521973,-0.0034694672,0.011260986,0.018814087,0.014137268,-0.014518738,0.0050621033,-0.0053138733,0.017303467,0.0014896393,0.016082764,0.029663086,-0.013092041,-0.01638794,0.013412476,0.00592041,-0.012580872,0.0009050369,0.056274414,-0.005706787,-0.010765076,-0.016662598,-0.0042037964,0.020141602,0.022750854,0.022033691,0.034088135,0.01777649,-0.024917603,-0.028656006,0.035217285,-0.015197754,0.009399414,-0.028060913,-0.016906738,0.0008621216,0.037750244,0.020935059,0.011192322,-0.0012588501,-0.01499176,0.014839172,0.005180359,-0.022247314,-0.006690979,-0.01651001,-0.020309448,0.009376526,0.005630493,-0.022735596,-0.0018081665,-0.018127441,-0.02961731,-0.0034885406,0.008049011,0.029510498,0.013618469,0.028335571,-0.015686035,0.023071289,0.00737381,0.009208679,0.03729248,-0.031707764,-0.01335144,0.007873535,0.017593384,-0.0064086914,-0.02659607,0.016540527,-0.020812988,-0.026931763,0.049072266,-0.04095459,0.026824951,-0.0077323914,6.0260296e-05,0.024887085,-0.0018844604,-0.004940033,0.042541504,0.01852417,0.009399414,0.0065345764,0.01184845,-0.00491333,0.010620117,-0.006729126,-0.018081665,-0.017410278,0.02999878,-0.001253128,-0.0154418945,-0.00013720989,0.007572174,-0.00907135,0.026123047,-0.0065574646,-0.018341064,0.005710602,0.0002450943,0.010467529,0.010482788,0.00019586086,0.014007568,-0.017089844,-0.005264282,-0.039093018,-0.024810791,-0.014717102,0.015419006,-0.0035076141,-0.0021266937,0.028762817,0.018188477,0.022460938,0.032562256,0.01687622,0.009185791,-0.023513794,0.010498047,-0.00025057793,0.024963379,-0.03817749,-0.029464722,-0.0206604,0.0090789795,-0.00025057793,-0.011650085,-0.0073127747,0.0073013306,0.009849548,0.023406982,0.00029921532,0.0017242432,-0.005748749,-0.01939392,-0.010551453,-0.02243042,-0.005908966,0.020629883,0.0016994476,-0.027038574,0.00623703,-0.025238037,-0.0035305023,-0.004436493,-0.0050201416,-0.0140686035,0.026824951,-0.019073486,0.001414299,0.029647827,0.06060791,0.028411865,-0.019317627,-0.039001465,-0.015640259,-0.0075302124,0.026504517,0.02204895,0.016784668,-0.0057792664,-0.009468079,-0.019485474,-0.016921997,0.010620117,-0.0076293945,0.021713257,0.007194519,-0.017486572,-0.009979248,-0.0058517456,0.00944519,0.02949524,0.0013494492,0.011520386,-0.0033245087,0.003353119,0.011558533,0.02798462,-0.014083862,0.016494751,0.002981186,0.028503418,0.0071372986,0.027175903,-0.024658203,0.020690918,-0.011711121,-0.0013027191,0.015701294,-0.00869751,0.011161804,0.006023407,-0.0044784546,-0.0015192032,0.018417358,0.007858276,0.034454346,-0.018829346,-0.026473999,-0.0076789856,-0.0054473877,-0.0256958,-0.029724121,0.01828003,-0.02217102,-0.010101318,4.7504902e-05,0.034729004,-0.01737976,0.029144287,-0.01701355,-0.017578125,-0.03277588,0.019210815,0.0021400452,-0.01878357,0.012794495,0.020431519,0.028198242,-0.009262085,0.017089844,0.036590576,-0.012031555,-0.0118255615,0.0103302,0.015594482,-0.005432129,-0.009536743,0.007671356,-0.012588501,-0.013504028,-0.04586792,-0.017288208,-0.029434204,-0.0017108917,-0.0062294006,0.028961182,-4.5716763e-05,0.017974854,-0.010101318,-0.029663086,-0.01939392,0.004901886,-0.00034618378,-0.019744873,0.007472992,0.029083252,-0.016677856,0.014930725,0.0027313232,0.012527466,-0.03164673,-0.013252258,0.021453857,-0.0053710938,-0.03640747,-0.032165527,-0.00032806396,0.014968872,0.0395813,0.011634827,0.028869629,0.052215576,-0.01146698,0.024490356,-0.0007224083,0.024337769,-0.009063721,0.012313843,-0.01374054,0.008735657,-0.0104599,0.026016235,-0.017913818,-0.02722168,-0.025497437,-0.0006518364,-0.025177002,-0.0014667511,0.0602417,-0.023117065,0.017700195,0.0289917,-0.016952515,0.004070282,-0.006729126,0.015579224,0.027008057,0.009185791,-0.0059776306,0.012481689,-0.0018968582,0.029312134,-0.0031814575,-0.010482788,0.028930664,-0.0066986084,0.022384644,0.0064811707,0.016998291,-0.045654297,0.014480591,0.014770508,0.019546509,-0.012481689,-0.009788513,0.009674072,0.004940033,-0.0009074211,0.026275635,-0.04095459,-0.004421234,-0.006134033,-0.025009155,-0.0043144226,-0.028015137,0.0042266846,-0.0018348694,0.03881836,-0.025161743,-0.0077552795,0.0076522827,-0.020431519,-0.009048462,-0.054870605,0.0068206787,0.00053167343,0.02885437,-0.036621094,-0.024337769,0.023895264,-0.008262634,-0.0063705444,0.023147583,0.013122559,-0.008079529,0.034606934,0.0079956055,-0.024856567,-0.004966736,0.0262146,0.030731201,-0.019332886,0.01828003,0.032318115,-0.014778137,-0.011505127,-0.014984131,-0.023071289,0.046722412,0.006336212,-0.003112793,-0.025680542,-0.003042221,0.008270264,0.017486572,-0.0007929802,0.03656006,0.012008667,0.010093689,-0.008666992,-0.05581665,-0.015945435,0.015991211,0.00028800964,0.015289307,-0.026031494,-0.016433716,-0.011741638,0.005470276,-0.014083862,-0.013908386,-0.028305054,0.025787354,-0.028289795,0.015289307,0.030090332,0.00491333,-0.011238098,0.009681702,-0.0014848709,-0.022216797,0.010978699,-0.000767231,0.037475586,0.04989624,-0.0038414001,0.0067596436,0.00039052963,0.0072021484,0.007083893,0.035614014,-0.0031604767,-0.0015954971,-0.0078086853,-0.02848816,-0.0062408447,0.00036764145,0.016662598,-0.0010566711,0.0022354126,0.0103302,0.021514893,-0.02998352,0.009483337,-0.0038795471,-0.039794922,0.032104492,0.00068855286,0.020095825,-0.023101807,-0.027694702,0.0047950745,-0.009429932,0.010673523,-0.017089844,0.001701355,0.019515991,-0.0037498474,0.0013751984,0.00010561943,-0.007297516,7.349253e-05,-0.027557373,0.030548096,0.03842163,0.00058078766,0.055725098,-0.035888672,0.017364502,-0.016723633,0.0077438354,-0.02772522,0.026870728,0.037322998,0.0053977966,-0.0096588135,0.004081726,-0.0074539185,0.008705139,-0.033447266,0.016311646,-0.0044517517,0.0006971359,0.023254395,0.015022278,-0.0063972473,-0.0011396408,-0.010139465,-0.0075569153,0.012504578,0.05343628,0.00038909912,0.042022705,0.03704834,-0.017837524,0.034179688,0.026275635]
2	20261101_000002	BNFT_44584D1B4FDB	STYLE 쇼핑·서점/문구·패션 캐시백	CASHBACK	LOCAL	PRODUCT	\N	\N	\N	[{"rule_key": "style_100", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_style_100", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 3000, "cond_raw_txt": "결제 건당\\n3천원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "value_num": 100, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "다이소", "target_key": "다이소", "target_type_cd": "MERCHANT"}, {"target_nm": "올리브영", "target_key": "올리브영", "target_type_cd": "MERCHANT"}, {"target_nm": "교보문고", "target_key": "교보문고", "target_type_cd": "MERCHANT"}, {"target_nm": "영풍문고", "target_key": "영풍문고", "target_type_cd": "MERCHANT"}, {"target_nm": "알라딘", "target_key": "알라딘", "target_type_cd": "MERCHANT"}, {"target_nm": "yes24", "target_key": "yes24", "target_type_cd": "MERCHANT"}, {"target_nm": "아트박스", "target_key": "아트박스", "target_type_cd": "MERCHANT"}, {"target_nm": "무신사", "target_key": "무신사", "target_type_cd": "MERCHANT"}, {"target_nm": "에이블리", "target_key": "에이블리", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}, {"rule_key": "style_500", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_style_500", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 10000, "cond_raw_txt": "결제 건당\\n1만원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "value_num": 500, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "다이소", "target_key": "다이소", "target_type_cd": "MERCHANT"}, {"target_nm": "올리브영", "target_key": "올리브영", "target_type_cd": "MERCHANT"}, {"target_nm": "교보문고", "target_key": "교보문고", "target_type_cd": "MERCHANT"}, {"target_nm": "영풍문고", "target_key": "영풍문고", "target_type_cd": "MERCHANT"}, {"target_nm": "알라딘", "target_key": "알라딘", "target_type_cd": "MERCHANT"}, {"target_nm": "yes24", "target_key": "yes24", "target_type_cd": "MERCHANT"}, {"target_nm": "아트박스", "target_key": "아트박스", "target_type_cd": "MERCHANT"}, {"target_nm": "무신사", "target_key": "무신사", "target_type_cd": "MERCHANT"}, {"target_nm": "에이블리", "target_key": "에이블리", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}]	[]	PENDING_REVIEW	\N	\N	결제 건당 3천원 이상 시 100원 / 결제 건당 1만원 이상 시 500원	월 5천원 / 일 1회 / 월 10회	혜택명: STYLE 쇼핑·서점/문구·패션 캐시백\n혜택 유형: 캐시백\n이용처: 다이소, 올리브영, 교보문고, 영풍문고, 알라딘, yes24, 아트박스, 무신사, 에이블리\n혜택 내용: 결제 건당 3천원 이상 시 100원, 1만원 이상 시 500원 캐시백	[0.014221191,-0.0050239563,-0.031311035,0.011619568,-0.020309448,-0.026672363,-0.06768799,0.04043579,0.009559631,-0.04272461,0.0015106201,-0.0137786865,0.011108398,-0.046295166,0.0027313232,0.029205322,-0.045440674,0.03164673,0.004184723,0.038757324,-0.03692627,0.042175293,-0.0068626404,-0.008018494,0.033416748,0.027282715,0.0054130554,-0.02734375,0.03375244,-0.0013399124,-0.00044465065,-0.025253296,0.057037354,-0.034362793,-0.019699097,0.062316895,-0.03503418,-0.0010128021,0.068481445,-0.005748749,-0.003982544,-0.0039634705,0.0158844,-0.033843994,0.043823242,0.044921875,0.0703125,0.01802063,-0.003255844,0.037902832,0.015716553,0.01914978,0.0038375854,-0.045318604,-0.028930664,-0.03390503,-0.03387451,0.009117126,0.05029297,-0.00012993813,-0.00043988228,-0.022033691,-0.0357666,-0.009086609,0.00258255,0.001739502,-0.023513794,0.026947021,-0.040374756,0.014251709,0.0154418945,-0.013000488,0.076416016,-0.023025513,-0.019592285,-0.04586792,0.0058937073,0.018539429,0.076538086,-0.010543823,0.007507324,-0.019836426,-0.05444336,0.049865723,0.01525116,-0.035736084,-0.063964844,-0.008880615,-0.050933838,0.05581665,-0.0019779205,-0.020736694,-0.0011672974,0.01979065,0.0004887581,0.012245178,-0.070373535,-0.0025501251,-0.02508545,0.027175903,0.018463135,-0.0413208,0.005680084,-0.012908936,-0.018218994,0.049926758,-0.016464233,-0.004333496,0.009498596,-0.017120361,-0.04421997,0.020339966,-0.025756836,0.026626587,0.029815674,0.03189087,0.029953003,-0.022338867,0.006401062,-0.008285522,0.0014638901,0.026382446,-0.0034046173,-0.077819824,-0.06829834,0.029708862,0.006084442,-0.017150879,-0.0395813,0.019683838,-0.041290283,-0.025238037,-0.02557373,-0.008636475,-0.0031490326,0.016494751,0.0047798157,-0.034820557,-0.026748657,-0.051849365,-0.028625488,0.00116539,0.06323242,0.01751709,-0.016189575,-0.027236938,-0.033935547,0.002412796,-0.018417358,0.026367188,-0.0065612793,-0.024520874,0.0060539246,0.00022053719,-0.008865356,-0.024658203,0.019851685,0.020431519,-0.049804688,-0.02116394,0.0038585663,-0.017745972,-0.020965576,-0.014945984,0.022506714,0.035705566,-0.014579773,0.020309448,-0.02609253,-0.025894165,0.0010538101,-0.026031494,-0.010391235,-0.019424438,-0.016937256,0.006603241,0.05328369,0.011360168,-0.0011253357,0.04244995,-0.015197754,0.047027588,0.06732178,-0.00087308884,-0.008049011,-0.06427002,-0.005580902,-0.0345459,0.022537231,0.05529785,-0.0051231384,-0.005039215,-0.01966858,-0.026245117,-0.003692627,0.033294678,0.0031261444,0.04309082,-0.041046143,-0.025283813,-0.020874023,-0.028030396,0.02960205,0.042510986,-0.023727417,-0.023529053,-0.05722046,-0.025115967,0.052825928,-0.039611816,0.018417358,0.0027122498,-0.031433105,0.0002567768,-0.010948181,0.025878906,0.04421997,0.0090408325,-0.030776978,0.029312134,-0.011161804,0.000910759,0.019851685,-0.0010213852,-0.00066661835,0.012321472,0.018081665,0.018936157,-0.010299683,-0.052612305,0.008781433,0.029586792,-0.0158844,0.026641846,-0.018829346,0.06713867,0.00057411194,0.017700195,-0.01826477,-0.050048828,0.037200928,0.023513794,0.025390625,0.022354126,0.030822754,0.004714966,0.01210022,-0.003074646,0.018218994,-0.019500732,0.01638794,0.024108887,-0.015548706,-0.02796936,0.027420044,-0.033203125,0.042541504,0.030654907,0.011711121,-0.03878784,0.030319214,-0.0501709,0.0058898926,0.01576233,-0.013687134,0.019729614,0.014183044,0.023513794,0.0073165894,0.03262329,-0.03918457,0.022140503,0.020843506,0.025726318,0.036071777,-0.06933594,-0.0056152344,0.02798462,0.028717041,0.033843994,0.0038318634,0.014205933,0.0014095306,-0.03213501,0.06173706,0.06329346,0.033996582,-0.03640747,-0.026306152,0.030181885,0.014953613,-0.061187744,-0.06878662,-0.07574463,-0.02255249,-0.016616821,-0.017105103,-0.019104004,0.017410278,-0.01184845,0.04498291,0.088012695,-0.02394104,-0.03857422,0.0038032532,0.03717041,-0.004508972,0.06567383,0.0045700073,-0.021469116,-0.017333984,-0.04135132,-0.0048675537,-0.026733398,-0.009735107,-0.010917664,-0.0037899017,0.02696228,0.054779053,-0.073913574,0.03253174,-0.020050049,0.035339355,0.018753052,0.006134033,-0.0178833,0.0066452026,-0.010795593,-0.022857666,0.014663696,0.016098022,-0.00059843063,0.036102295,0.024551392,-0.043701172,-0.025665283,0.062072754,0.00497818,-0.031982422,-0.005493164,0.011672974,-0.019317627,0.0023231506,-0.009979248,-0.01335144,-0.043640137,0.053894043,0.024627686,0.045715332,0.03338623,0.0064582825,-0.027557373,0.029541016,-0.017181396,-0.008575439,0.006538391,-0.01676941,-0.035095215,-0.06298828,0.030166626,-0.01676941,0.010047913,0.022644043,0.0061569214,0.015060425,0.040039062,-0.020477295,-0.019226074,0.033203125,0.019607544,-0.0011281967,0.045532227,-0.0058937073,-0.004016876,0.013427734,0.010498047,0.025939941,0.0087509155,-0.016403198,-0.037017822,0.036346436,-0.027435303,-0.040771484,0.020751953,0.085998535,-0.010375977,0.040771484,0.026367188,0.01007843,0.022277832,-0.023742676,0.017120361,0.014099121,-0.014434814,0.031982422,0.009727478,-0.024795532,0.032562256,-0.06384277,0.027832031,0.003189087,-0.016983032,-0.0060653687,-0.042633057,0.013710022,0.0181427,-0.013618469,0.01966858,0.015960693,-0.007663727,0.023742676,-0.06097412,0.014717102,0.04006958,0.011489868,-0.0017271042,-0.031982422,-0.013763428,-0.022705078,-0.048736572,0.025619507,-0.041107178,-0.050720215,-0.025360107,0.009796143,-0.036956787,0.007774353,0.04953003,-0.039520264,-0.009674072,-0.005519867,-0.026184082,-0.006389618,-0.00869751,-0.035736084,0.0014257431,0.01259613,0.034362793,-0.044006348,-0.054229736,-0.045654297,0.006225586,-0.03945923,0.030593872,-0.008232117,0.0051460266,0.018035889,0.0501709,-0.05984497,-0.038482666,-0.044158936,0.012619019,-0.06518555,0.0068740845,-0.02331543,0.012062073,0.035949707,-0.034210205,0.01335144,-0.013504028,0.03048706,0.007888794,0.038482666,0.029571533,0.035125732,0.011016846,-0.021911621,0.013183594,-0.001124382,0.01058197,-0.040893555,0.02331543,0.054473877,0.041900635,0.053375244,-0.028930664,0.00819397,0.015640259,0.057373047,0.015197754,-0.015457153,-0.013687134,-0.032562256,-0.00081062317,-0.022827148,0.04248047,0.077941895,0.014823914,-0.02758789,-0.04272461,-0.014419556,0.0068969727,0.028396606,-0.0075569153,-0.018508911,-0.01159668,0.00032258034,-0.011268616,0.011543274,-0.05218506,0.0063476562,-0.05078125,-0.014328003,0.012504578,-0.046722412,0.018035889,-0.015640259,-0.045074463,-0.018936157,0.030395508,-0.03643799,0.031707764,-0.016036987,-0.016738892,0.025039673,-0.048187256,-0.048339844,0.006729126,-0.014060974,0.0027713776,-0.020217896,0.00982666,0.014129639,-0.048034668,0.030166626,-0.021087646,-0.024383545,-0.07305908,0.011795044,0.0028476715,-0.00422287,-0.009300232,-0.0099105835,0.01625061,-0.010192871,-0.013366699,0.00096321106,0.04498291,0.024490356,0.006641388,0.029464722,-0.009605408,0.008125305,-0.026351929,-0.0074386597,-0.048980713,-0.010284424,0.009185791,0.012290955,0.03024292,-0.006565094,-0.0038318634,-0.008003235,-0.008598328,0.038085938,-0.0068473816,0.006931305,0.015403748,0.031341553,0.0005130768,0.0041770935,0.00049352646,0.0005559921,0.032470703,0.0107040405,0.036193848,0.019561768,-0.008087158,-0.040405273,-0.01739502,-0.05206299,0.039154053,0.018630981,0.026031494,0.0037765503,-0.010688782,-0.03616333,-0.0032348633,-0.01802063,0.0053863525,-0.00025582314,-0.0064048767,0.012939453,0.020080566,0.0018959045,0.003955841,-0.006752014,0.011833191,0.028411865,-0.02041626,-0.012298584,0.011497498,0.019821167,0.017791748,-0.0138549805,-0.012207031,-0.026107788,0.014305115,0.062561035,-0.017593384,-0.0064048767,-0.02281189,-0.0007748604,-0.06048584,-0.001750946,0.009132385,0.02545166,-0.0018615723,0.03652954,0.00034308434,0.031555176,0.023513794,-0.00053691864,-0.039794922,-0.04046631,0.004470825,-0.03353882,0.0076522827,0.012428284,-0.0036525726,-0.037597656,0.02734375,0.02659607,-0.022384644,-0.005191803,0.026046753,0.014389038,-0.05496216,-0.0049095154,-0.021972656,0.0053710938,0.010879517,0.04522705,-0.033416748,0.011436462,0.04437256,-0.02432251,0.027114868,0.022644043,0.012077332,0.03314209,-0.00774765,0.02027893,-0.028076172,-0.032989502,-0.021957397,-0.01033783,-0.0013418198,0.001791954,0.013183594,0.04748535,0.018600464,-0.00605011,-0.04736328,0.014343262,0.018966675,-0.015777588,0.033111572,0.016555786,0.007030487,-0.015457153,0.050231934,-0.02822876,0.00035715103,0.00017905235,0.013793945,0.005596161,0.012001038,0.03149414,-0.015090942,0.025344849,-0.0029144287,0.053131104,0.00554657,-0.019714355,0.039886475,0.0129852295,-0.03353882,-0.0066452026,0.0026798248,0.010192871,0.00043058395,-0.027526855,-0.01727295,-0.0033512115,-0.0063934326,0.0039901733,-0.012786865,-0.00894165,0.011810303,-0.0007519722,0.0031795502,0.030914307,0.03326416,0.0056915283,-0.0007581711,0.018417358,0.01423645,0.007865906,-0.0031871796,-0.018371582,-0.014251709,0.032470703,-0.026947021,0.026107788,0.015457153,0.032440186,0.039764404,0.02243042,-0.035888672,-0.0030670166,-0.0030651093,-0.00033426285,-0.0262146,-0.03010559,0.0014705658,0.03375244,-0.0038585663,0.022506714,0.0015764236,-0.046569824,0.018005371,-0.016647339,-0.033172607,-0.0026435852,-0.0025558472,-0.020996094,-0.022994995,0.0013961792,-0.005554199,0.014556885,0.0063323975,0.009056091,0.03286743,-0.0022201538,0.026687622,-0.027709961,0.01146698,-0.024520874,0.011329651,0.02420044,-0.012435913,-0.0107803345,-0.020065308,-0.01928711,-0.019134521,-0.040039062,-0.045013428,-0.017654419,0.01776123,0.031555176,0.0045166016,0.0289917,-0.006996155,0.014450073,-0.023071289,-0.0231781,-0.013000488,0.01713562,-0.01739502,0.017166138,-0.00818634,-0.0309906,0.014060974,-0.016281128,0.01512146,-0.036346436,0.009666443,-0.026794434,0.007205963,0.033081055,0.0035190582,-0.00422287,0.02017212,0.055603027,0.01979065,0.0017719269,0.0036239624,-0.022018433,-0.026153564,0.016494751,-0.033111572,0.01902771,0.015159607,-0.0071907043,0.004306793,0.0001244545,-0.033691406,0.03656006,-0.0041122437,-0.0143585205,-0.035217285,-0.022598267,-0.037200928,0.008682251,0.017303467,-0.011360168,-0.039978027,-0.0017576218,0.019989014,-0.0014305115,0.0043563843,-0.013725281,-0.0050582886,0.016143799,0.008598328,-0.0017929077,0.03463745,0.012916565,-0.033081055,0.0061187744,0.026901245,0.018859863,0.05102539,0.0008068085,-0.0022258759,-0.0151901245,0.008148193,0.0036640167,0.0068740845,0.029220581,-0.02519226,-0.0024318695,0.010147095,0.0592041,0.023483276,-0.014144897,-0.012001038,-0.0046157837,-0.022125244,-0.03338623,-0.011161804,0.014602661,0.006767273,0.04498291,-0.008300781,0.042541504,0.036071777,-0.03286743,0.0017747879,0.03878784,0.029785156,-0.0030536652,-0.04458618,-0.016403198,-0.0006380081,-0.014381409,-0.01739502,-0.02368164,0.058929443,0.0016756058,0.017456055,-0.016662598,0.023239136,0.005279541,0.01008606,0.002696991,-0.022537231,0.0031738281,0.010131836,-0.008598328,-0.009338379,-0.01638794,-0.06088257,-0.0031356812,0.014930725,0.017196655,0.04714966,0.015197754,0.0064697266,-0.02053833,-0.04840088,0.010864258,-0.050231934,0.018814087,0.00047588348,0.02154541,0.05618286,0.010658264,0.00064992905,0.026489258,-0.010551453,-0.032714844,0.014541626,0.030441284,0.04248047,-0.0015096664,-0.021743774,-0.025299072,-0.00818634,0.008850098,-0.008171082,0.02861023,-0.0054740906,-0.038726807,0.003156662,-0.032104492,0.016357422,-0.0018959045,-0.0262146,0.0061912537,0.022399902,-0.042022705,0.001616478,-0.01058197,0.029205322,-0.0036849976,-0.015472412,-0.0015544891,0.0284729,-0.004219055,-0.03439331,0.01763916,0.01838684,0.029754639,0.015670776,-0.039001465,0.029846191,0.044433594,-0.00970459,-0.0076828003,-0.0033359528,0.026489258,-0.04159546,-0.02078247,-0.03564453,0.014846802,0.012886047,0.008110046,0.001584053,-0.0057144165,0.008140564,0.04345703,0.0033416748,0.0028133392,0.006587982,0.0026359558,-0.029922485,-0.012374878,-0.02468872,-0.0027542114,0.013023376,-0.0028705597,0.021697998,-0.004547119,-0.018203735,0.017120361,-0.04562378,-0.0016784668,-0.00969696,0.004550934,-0.042144775,-0.000992775,-0.034484863,-0.0013027191,0.0019989014,-0.03488159,0.026855469,0.06112671,0.00818634,-0.03213501,-0.022750854,-0.0069274902,-0.028839111,0.008628845,-0.008544922,-0.017669678,0.023254395,0.02168274,0.066101074,0.0026779175,-0.001074791,0.003282547,0.022109985,0.021835327,0.014556885,-0.0119018555,-0.0031337738,0.02255249,0.024902344,-0.032196045,0.015731812,0.009895325,0.019180298,-0.013420105,-0.02218628,-0.0015172958,0.01725769,0.022140503,-0.014518738,0.032104492,0.058502197,0.029907227,0.006252289,0.0042800903,-0.020248413,-0.0015878677,0.028335571,-0.013153076,-0.025390625,-0.010894775,-0.023788452,-0.01033783,-0.03024292,-0.004184723,-0.0031356812,0.029647827,-0.03765869,0.022125244,-0.036590576,0.02709961,0.019226074,0.029373169,-0.01008606,0.009132385,-0.025985718,0.01335144,0.014198303,-0.0023212433,-0.026153564,0.029800415,0.017868042,-0.0043525696,0.051361084,-0.018981934,0.008705139,0.01777649,-0.007534027,0.015296936,-0.017089844,-0.032196045,-0.00037527084,0.0038280487,0.0016317368,-0.019104004,0.023483276,0.0071792603,-0.01512146,-0.001868248,0.01309967,-0.013122559,-0.015960693,0.027542114,-0.007633209,-0.028549194,-0.017852783,0.0105896,0.029968262,0.01928711,-0.02861023,0.026779175,-0.02217102,-0.015792847,-0.014526367,-0.03186035,-0.003868103,-0.008766174,0.00045919418,-0.0041770935,-0.012702942,0.015365601,0.0029315948,-0.0029182434,0.031341553,0.015060425,-0.048309326,0.03137207,0.0065193176,-0.017166138,-0.051086426,-0.008239746,0.035339355,0.013969421,-0.014945984,-0.010505676,0.014060974,0.015083313,0.023071289,0.03665161,0.02218628,-0.031829834,-0.00079250336,-0.008651733,0.019042969,0.015029907,-0.00033783913,0.013313293,0.013046265,-0.023406982,0.015388489,-0.011268616,0.0044059753,0.0033245087,0.053710938,-0.020690918,-0.0043182373,0.01309967,-0.0049476624,0.021591187,0.023452759,-0.0010509491,0.05822754,-0.008705139,-0.021194458,-0.002609253,0.008934021,-0.010749817,-0.0014152527,-0.03753662,-0.024414062,0.0068740845,0.035369873,0.04067993,-0.0064201355,-0.0007019043,-0.0054359436,0.018676758,0.012756348,-0.0032100677,0.00013685226,-0.02670288,-0.012573242,0.032226562,0.0011520386,-0.01713562,-0.0082473755,-0.0345459,-0.014045715,-0.009407043,0.021820068,0.04446411,0.0027313232,0.00088977814,-0.029586792,0.009849548,0.010093689,0.0113220215,0.013298035,-0.023620605,-0.023742676,0.006340027,0.0034751892,-0.019500732,-0.020248413,0.0035114288,0.002500534,-0.03765869,0.05316162,-0.02079773,0.013618469,-0.02796936,0.0056381226,0.010513306,-0.009918213,-9.083748e-05,0.04425049,-0.0004067421,0.017227173,0.024902344,-0.0037708282,-0.0050811768,0.010597229,0.010887146,-0.0028858185,-0.0033092499,0.030944824,0.01966858,0.0063667297,-0.0015573502,-0.005241394,-0.01864624,0.015777588,0.0053520203,0.0005874634,0.0178833,5.567074e-05,-0.0048561096,0.024932861,0.030227661,-0.013763428,0.00029206276,-0.022598267,-0.043182373,-0.0066986084,-0.008911133,0.025299072,-0.018875122,-0.010475159,0.029647827,-0.0039634705,0.02658081,0.020904541,0.038146973,0.012718201,-0.014541626,0.017623901,-0.015411377,0.06323242,-0.0390625,-0.03717041,-0.023071289,0.02078247,0.018676758,0.014251709,0.0057678223,-0.013656616,0.00484848,0.025650024,-0.0068740845,-0.0107803345,-0.005168915,0.004306793,-0.00932312,-0.030349731,-0.0010690689,0.009025574,0.020248413,-0.025360107,0.010223389,-0.029785156,-0.0105896,-0.016586304,0.008583069,0.0016422272,0.008666992,-0.0024585724,0.014129639,0.034942627,0.078063965,0.04324341,-0.026687622,-0.03451538,-0.02798462,-0.015327454,-0.017318726,0.024810791,0.02319336,-0.002292633,0.010543823,-0.021484375,-0.019805908,0.010948181,-0.0027122498,0.028625488,-0.019073486,0.011657715,-0.016448975,-0.0129852295,-0.0029182434,0.0009326935,-0.0022506714,0.0077056885,0.017547607,0.008811951,0.002696991,0.014923096,-0.014007568,0.025115967,0.00019598007,0.029144287,0.011520386,-0.002872467,0.0012874603,0.0028839111,-0.00020730495,0.0033569336,0.007411957,-0.0066490173,-0.0006747246,-0.0020561218,-0.0068359375,0.0020942688,0.016067505,0.03164673,0.04119873,-0.02180481,-0.02583313,-0.040405273,-0.007209778,-0.0025081635,0.008171082,-0.011199951,0.00078582764,-0.017074585,0.0039100647,0.02760315,0.006958008,0.0061302185,-0.01675415,-0.020599365,-0.064208984,-0.009094238,-0.017547607,-0.007286072,0.01374054,0.034851074,0.024765015,-0.019607544,0.0037498474,0.0072784424,-0.030349731,-0.00071430206,0.033966064,0.026260376,-0.016021729,-0.0024547577,0.0066986084,-0.018508911,-0.014541626,-0.0574646,-0.037353516,-0.026260376,-0.027420044,0.009880066,0.030441284,-0.004016876,0.018539429,0.013710022,-0.052215576,-0.015853882,-0.004901886,-0.030670166,0.0138168335,0.03869629,0.035736084,-0.007850647,0.01953125,-0.008560181,0.018630981,-0.02420044,-0.0231781,-0.014175415,-0.0046081543,-0.008468628,-0.021865845,-0.019683838,0.015853882,0.022750854,0.0104522705,0.017486572,0.030883789,-0.024108887,-0.014434814,0.00069856644,0.014411926,-0.012863159,-0.0038986206,-0.0009150505,0.0068092346,-0.006538391,0.052764893,-0.013954163,-0.038146973,-0.026901245,0.019134521,0.0129852295,-0.009666443,0.042114258,-0.020385742,0.007499695,0.0001527071,0.0059890747,0.005519867,0.013504028,0.029174805,0.021697998,0.019714355,-0.021194458,0.024978638,-0.017166138,0.030075073,-0.006942749,-0.00017356873,0.022857666,0.0032539368,0.018005371,-0.009208679,0.018630981,-0.033477783,0.0059432983,0.0028057098,0.02267456,-0.026000977,-0.0129470825,0.0060043335,0.019927979,0.010322571,0.016494751,-0.042877197,-0.0057754517,-0.031585693,-0.0018110275,-0.0033302307,-0.028457642,0.018203735,0.0063667297,0.038513184,-0.034820557,0.025253296,0.0047950745,-0.01776123,-0.0012254715,-0.057525635,0.0058784485,-0.0056915283,0.02368164,-0.021636963,-0.03060913,0.0028743744,0.010696411,0.005168915,0.0069503784,0.017623901,-0.0012512207,0.013511658,0.02659607,-0.017166138,-0.021591187,0.026992798,0.024017334,0.011245728,-0.00680542,0.008094788,0.019760132,-0.00932312,-0.008918762,0.0048561096,0.023849487,-0.0004658699,0.012268066,-0.034118652,0.014198303,0.015365601,0.023361206,0.011657715,0.02444458,0.027755737,-0.0029754639,-0.0082473755,-0.05078125,-0.014343262,0.031097412,-0.016662598,-0.0058517456,-0.040405273,-0.018737793,-0.025604248,0.028411865,-0.024795532,0.0022563934,0.0024528503,0.0058403015,-0.009521484,0.012428284,-0.006576538,-0.011016846,-0.020477295,0.009521484,-0.02357483,0.0058403015,0.025604248,0.015281677,0.01423645,0.019546509,-0.03829956,0.020370483,0.031707764,-0.020980835,0.03479004,0.004688263,-0.0023536682,-0.025894165,-0.004550934,-0.055755615,0.026672363,0.016204834,0.03567505,0.0012397766,0.0036087036,0.015312195,0.008155823,-0.022491455,0.0051498413,-0.010734558,0.012573242,-0.005882263,0.0044784546,0.046051025,-0.022705078,-0.027832031,-0.013420105,-0.019500732,0.01184845,-0.0031814575,0.012161255,0.027709961,0.024871826,0.03552246,0.019378662,0.0022201538,0.027450562,0.0027866364,-0.005596161,0.04019165,0.0030822754,0.04498291,-0.052764893,0.024414062,-0.029586792,-0.01826477,-0.024734497,0.032196045,0.037109375,0.009757996,0.027633667,0.011016846,-0.00019598007,0.011940002,-0.04055786,0.0056610107,0.015792847,-0.008216858,0.017807007,-0.01423645,-0.0019817352,-0.02128601,-0.042938232,-0.01285553,-0.010757446,0.0181427,0.0104599,0.048034668,0.028579712,0.001865387,0.03616333,0.011253357]
2	20261101_000004	BNFT_C63ED6040122	ONE MORE 놀이공원 현장할인	DISCOUNT	LOCAL	PRODUCT	\N	{"branches": [{"atoms": [{"atom_key": "amusement_spend", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 200000, "cond_raw_txt": "* ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "amusement_first_month", "atom_seq": 2, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "최초 발급 월에는\\n서비스 미제공", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "최초 발급 월에는\\n서비스 미제공", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "spend_exclusions", "atom_seq": 3, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "cond_type_cd": "SPEND_EXCL", "excl_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "amusement_per_person", "atom_seq": 4, "negate_yn": false, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "1인 1매", "cond_type_cd": "ETC", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}	\N	[{"rule_key": "amusement_rate", "basis_amt": null, "cond_expr": null, "value_num": 50, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "에버랜드", "target_key": "에버랜드", "target_type_cd": "MERCHANT"}, {"target_nm": "롯데월드", "target_key": "롯데월드", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "PENDING_REVIEW"}]	[]	PENDING_REVIEW	\N	\N	50% 현장할인 (1인 1매)	월 1회 / 연 2회	혜택명: ONE MORE 놀이공원 현장할인\n혜택 유형: 할인\n이용처: 에버랜드, 롯데월드\n혜택 내용: 50% 할인	[-0.024993896,-0.0035076141,0.0068855286,0.008255005,-0.01927185,-0.025634766,-0.043640137,0.06286621,0.0012683868,-0.025527954,-0.0115737915,0.0071487427,-0.002363205,-0.025878906,0.0024261475,0.044189453,-0.042236328,0.072753906,-0.019973755,0.024002075,0.007499695,0.017166138,0.007286072,0.009056091,0.019515991,0.030899048,-0.04031372,-0.016601562,0.033569336,-0.028884888,0.0019159317,-0.041107178,0.059783936,0.0017566681,-0.05508423,0.02078247,-0.00034451485,0.0049438477,0.008918762,-0.025878906,0.010444641,-0.028900146,0.003704071,0.006702423,0.023391724,0.08288574,-0.005886078,-2.8073788e-05,-0.028793335,8.4757805e-05,0.0047912598,-0.013916016,0.0019216537,-0.047698975,-0.03387451,0.008659363,-0.022003174,0.010597229,0.028900146,-0.02986145,0.010719299,0.0099105835,0.040039062,0.038146973,0.02003479,0.0061073303,-0.02633667,-0.017288208,-0.008369446,0.05105591,-0.012550354,0.029953003,0.0028419495,-0.0004606247,-0.01222229,0.05227661,-0.0041046143,0.013717651,-0.038330078,-0.012969971,0.0135269165,-0.021240234,-0.06774902,0.012252808,0.0019760132,-0.007987976,-0.06518555,-0.032562256,0.02760315,0.06286621,0.014671326,0.018493652,-0.032073975,-0.03137207,-0.0155181885,0.035980225,-0.04824829,-0.0017299652,-0.033721924,0.035217285,0.03201294,-0.060791016,0.012664795,-0.0104904175,-0.019866943,-0.017730713,-0.015350342,0.040496826,0.025741577,-0.018295288,-0.07733154,0.016738892,-0.059295654,0.019348145,0.016036987,-0.02128601,0.07067871,-0.01512146,-0.022827148,-0.011184692,-0.014831543,-0.010345459,-0.02166748,-0.068847656,0.0045051575,-0.008300781,-0.030700684,0.006351471,-0.03543091,-0.025878906,0.007663727,0.02128601,-0.018920898,-0.004901886,-0.042297363,-0.02949524,-0.017089844,0.0034484863,-0.02670288,-0.00484848,0.012702942,0.009552002,0.0128479,-0.039642334,-0.0065841675,0.020767212,0.029312134,-0.022277832,-0.0236969,0.027297974,0.0006585121,-0.018035889,-0.044647217,-0.075683594,-0.029754639,-0.04650879,-0.016647339,0.0011024475,-0.0289917,0.02279663,-0.030197144,-0.050872803,-0.019226074,0.015930176,0.029144287,0.030807495,-0.034729004,0.016342163,-0.037231445,-0.0034675598,-0.024276733,0.0096588135,-0.035705566,-0.013137817,0.0018901825,-0.031433105,0.019134521,0.011390686,-0.048461914,0.008293152,-0.0064353943,0.043914795,0.030883789,-0.0030975342,-0.032409668,-0.018157959,-0.002822876,-0.014823914,-0.023452759,0.025039673,0.0029964447,0.004032135,-0.0016078949,0.032165527,0.010475159,0.0054626465,-0.02470398,-0.03768921,0.018966675,-0.0027503967,-0.008155823,-0.030288696,0.037475586,0.011749268,-0.022415161,-0.009208679,-0.034240723,0.022277832,0.015792847,0.009902954,0.050476074,0.024673462,-0.0039978027,-0.040161133,0.003616333,-0.011764526,0.035858154,-0.008110046,0.04071045,0.061706543,-0.0071487427,-0.019363403,-0.01689148,0.02394104,0.0028362274,0.021316528,-0.020492554,-0.030532837,-0.0012559891,-0.002840042,-0.036499023,0.006324768,-0.0501709,-0.02142334,-0.05026245,0.07861328,0.033355713,-0.036590576,-0.010620117,-0.027648926,0.04660034,0.050354004,0.022415161,0.016677856,-0.0037231445,-0.020492554,0.023239136,-0.013877869,-0.009170532,0.0055351257,0.016174316,0.06842041,-0.035980225,-0.025543213,0.03060913,0.008857727,-0.015548706,0.02255249,0.00047039986,-0.0079574585,0.05429077,0.006137848,-0.04598999,0.019882202,-0.030090332,0.009384155,0.08868408,0.061676025,0.005180359,0.033935547,-0.050354004,-0.013999939,0.014427185,0.002418518,0.024047852,0.011817932,0.028656006,0.020050049,-0.010047913,0.047607422,0.0034637451,0.0022335052,0.020645142,-0.07458496,0.015640259,0.0021266937,0.013954163,0.011741638,0.0045661926,0.035125732,0.02494812,-0.010177612,0.026687622,-0.03253174,-0.017547607,0.01626587,0.009468079,-0.021560669,0.044128418,-0.028335571,0.016677856,0.018035889,-0.032836914,0.0152282715,0.033599854,0.058288574,0.00422287,0.03616333,-0.025253296,0.0028877258,-0.013900757,0.03274536,-0.013702393,0.090148926,-0.044952393,0.0052604675,-0.025344849,-0.009407043,0.041259766,0.008865356,0.029296875,0.022277832,-0.007843018,0.0066566467,0.014694214,-0.012901306,0.041137695,-0.027999878,0.007987976,0.0063972473,-0.039367676,0.00969696,0.02079773,-0.029312134,-0.016021729,-0.027633667,-0.029937744,0.00046610832,0.0054855347,-0.015731812,0.02116394,-0.019607544,-0.048706055,-0.0115356445,-0.0435791,-0.07305908,0.046142578,-0.013320923,0.02420044,0.023803711,-0.015357971,-0.025787354,-0.009902954,-0.029907227,-0.01939392,-0.043670654,0.0748291,-0.02394104,0.00944519,0.049591064,-0.068359375,0.0335083,0.05340576,0.007320404,0.037322998,0.042388916,-0.018035889,0.017944336,0.046173096,0.01914978,-0.0010147095,0.05895996,-0.018051147,0.038391113,-0.026885986,0.005405426,0.04626465,0.05682373,0.015716553,-0.05432129,-0.036499023,-0.025131226,0.034942627,0.039489746,0.034454346,-0.02709961,0.0027580261,0.009857178,0.014915466,-0.016296387,0.015457153,-0.0072631836,-0.061828613,-0.030700684,-0.0154418945,-0.01713562,-0.028900146,0.046691895,-0.04840088,0.003080368,0.00097322464,-0.047576904,-0.038909912,-0.019943237,-0.021224976,-0.0039520264,0.026031494,0.00013375282,-0.010063171,-0.04510498,-0.042388916,-0.076171875,0.0061836243,0.025527954,0.04550171,0.01525116,0.0107421875,-0.05065918,-0.011268616,-0.027893066,0.008079529,0.03353882,0.016036987,0.0049858093,0.011795044,-0.023483276,0.009628296,0.05050659,-0.05722046,-0.037475586,-0.039886475,-0.033233643,-0.022750854,0.009536743,-0.025802612,0.015327454,-0.005264282,0.03439331,0.039886475,0.000854969,-0.01626587,-0.0107803345,-0.036224365,0.0005531311,-0.03137207,0.018417358,-0.008552551,0.07196045,-0.026901245,0.0038394928,-0.028381348,0.006149292,-0.037628174,0.0055503845,-0.043762207,-0.025604248,0.016067505,-0.015449524,-0.004108429,-0.010185242,-0.03100586,-0.00737381,0.009841919,-0.03829956,0.02532959,-0.018539429,0.016662598,-0.013549805,-0.017028809,-0.00630188,-0.038391113,0.04156494,0.033569336,0.05230713,0.019119263,0.0054016113,-0.009765625,0.01953125,0.03567505,-0.07305908,-0.007709503,-0.034362793,-0.01979065,-0.028335571,-0.023788452,0.022491455,0.049987793,-0.023254395,-0.06640625,-0.07476807,-0.0012645721,0.010871887,0.029800415,-0.008605957,-0.033721924,-0.004310608,-0.01537323,0.0007419586,0.04071045,-0.009643555,-0.036956787,-0.07366943,0.021636963,0.0057678223,0.03527832,0.0138549805,-0.051757812,-0.031921387,-0.0065841675,0.010520935,-0.05960083,0.013595581,-0.023483276,0.004497528,-0.005153656,-0.010391235,-0.0069122314,0.03778076,0.0096206665,0.008392334,-0.03378296,0.012939453,0.021194458,-0.030761719,0.02558899,0.010879517,-0.03503418,-0.038391113,0.020904541,0.04144287,-0.027954102,-0.032165527,0.030456543,0.009391785,-0.005592346,-0.022872925,0.040100098,0.032592773,-0.008880615,-0.011772156,0.025131226,-0.0023555756,0.030563354,-0.0038890839,-0.007045746,-0.013328552,0.012313843,-0.006450653,0.027297974,0.009246826,-0.031951904,-0.024276733,0.013648987,-0.021972656,0.0134887695,-0.020446777,0.02017212,0.0012807846,0.008544922,-0.02418518,0.02520752,-0.0109939575,-0.013771057,0.008666992,0.00030064583,0.060577393,0.019226074,0.008934021,-0.017990112,-0.005859375,-0.023147583,0.008880615,-0.029846191,0.0073013306,-0.0046577454,-0.017242432,0.04345703,-0.0149002075,-0.020553589,-0.03060913,0.023254395,0.0021038055,-0.0011463165,0.0496521,0.02407837,-0.02532959,-0.020217896,0.025344849,-0.009384155,-0.00046420097,-0.0029792786,-0.004562378,-0.010398865,-0.032562256,-0.019714355,0.030349731,0.0030097961,0.046051025,0.056884766,-0.0015983582,0.056610107,-0.03111267,0.0008497238,-0.0044403076,-0.02444458,0.0015153885,-0.021057129,-0.0043792725,0.00017809868,-0.022720337,-0.0021133423,-0.023635864,0.0061569214,0.0026855469,-0.044555664,-0.017868042,-0.072021484,0.018051147,-0.0043945312,-0.018569946,-0.032318115,-0.017547607,0.00018024445,-0.014076233,-0.010269165,0.006160736,-0.010810852,-0.014228821,-0.015403748,0.004585266,0.0055351257,0.0035800934,0.018203735,-0.03567505,0.019165039,-0.011810303,-0.028396606,0.0074653625,0.014823914,0.013801575,0.023620605,0.0017251968,0.03277588,-0.0034809113,-0.014404297,-0.005054474,0.063964844,-0.0513916,0.027786255,-0.00881958,-0.007881165,-0.009063721,0.009109497,-0.023803711,0.012718201,-0.0023956299,-0.011627197,0.022521973,0.010299683,-0.013214111,-0.032287598,0.049591064,-0.023880005,-0.01751709,-0.03652954,0.036895752,0.0067863464,0.018997192,0.0099487305,-0.025497437,0.03552246,-0.009109497,0.016189575,0.0154953,-0.01499176,0.032226562,-0.0034446716,0.00365448,0.0054092407,0.02293396,-0.010810852,0.0066871643,-0.004585266,-0.031204224,0.017608643,0.0017623901,0.0129470825,0.0020484924,-0.0046958923,-0.036102295,-0.020950317,0.011772156,0.041290283,0.017166138,0.0046157837,0.022476196,0.0069351196,-0.02885437,-0.0018835068,-0.032165527,0.018707275,0.041229248,0.001865387,-0.021774292,-0.029342651,-0.0069007874,0.059417725,0.03100586,0.028884888,-0.03137207,0.016708374,-0.03994751,-0.013168335,-0.030410767,0.015701294,-9.894371e-05,0.016464233,-0.035583496,0.064575195,0.0054473877,-0.017837524,-0.018737793,-0.02407837,0.01689148,-0.0016622543,0.03970337,0.0028972626,-0.021896362,-0.028839111,0.002456665,-0.011550903,0.0021648407,-0.0046691895,0.00021708012,0.002286911,0.019943237,-0.07232666,0.018676758,-0.026275635,-0.015991211,0.048858643,-0.013717651,0.029586792,-0.01751709,-0.024002075,0.016616821,-0.022720337,-0.012077332,-0.066345215,0.024597168,-0.014190674,0.004825592,0.025131226,-0.020767212,0.031555176,-0.027801514,0.060821533,0.012748718,-0.009132385,0.008506775,0.033966064,0.02835083,0.008079529,-0.005004883,0.01940918,0.01763916,-0.029205322,-0.02027893,-0.029586792,0.020446777,0.015731812,-0.0146484375,-0.00018572807,-0.0184021,0.02017212,-0.012542725,-0.01197052,-0.028762817,0.01133728,0.0018177032,0.020645142,0.01424408,0.035888672,-0.01876831,-0.008705139,-0.028335571,0.031799316,-0.0006904602,0.033447266,-0.005718231,0.007499695,-0.029190063,0.017944336,-0.044311523,0.039855957,0.03552246,0.028503418,-0.03024292,-0.00422287,0.00018823147,-0.014381409,-0.011291504,0.014701843,0.04550171,0.012794495,-0.023742676,-0.02180481,0.04660034,-0.020385742,-0.045562744,-0.029647827,-0.023544312,0.023986816,0.013725281,0.006351471,0.005004883,0.0064849854,0.0006365776,-0.0004439354,-0.026107788,0.012588501,-0.051757812,-0.0009121895,0.018585205,-0.0022716522,0.0054359436,-0.05029297,0.018615723,0.018539429,-0.031433105,-0.020462036,0.014328003,0.007209778,-0.0024299622,-0.01259613,0.013824463,0.039642334,0.012512207,-0.017089844,0.004512787,0.0036621094,-0.00033807755,0.003780365,-0.033813477,-0.04168701,-0.019943237,-0.0012950897,-0.0014810562,0.01234436,0.00067329407,-0.016159058,0.0040130615,-0.0052833557,0.042907715,0.033569336,0.004600525,-0.016784668,0.017852783,0.01474762,-0.002691269,-0.014221191,0.0032310486,-0.0012111664,-0.026504517,0.020065308,0.01272583,-0.0035686493,0.018539429,0.015617371,-0.004348755,-0.05419922,-0.0067863464,-0.040985107,0.007095337,0.01259613,-0.0023479462,0.038482666,0.041381836,-0.026687622,-0.013595581,0.012641907,-0.00083208084,-0.0070114136,-0.005367279,0.006248474,0.024932861,-0.0019702911,0.026443481,-0.00039362907,-0.027954102,0.056762695,-0.0016345978,-0.0020141602,-0.0025081635,0.0045700073,-0.052886963,-0.030151367,0.020889282,-0.0079956055,0.015342712,-0.031921387,-0.0013313293,-0.019439697,-0.010246277,-0.0178833,0.016418457,0.014205933,-0.007881165,0.0259552,-0.010383606,0.0032424927,-0.022247314,0.03111267,-0.02468872,-0.011947632,-0.0033283234,-0.041259766,0.015403748,0.010757446,0.008888245,-0.023803711,0.05331421,-0.0069274902,-0.0069885254,-0.0015716553,0.00023210049,-0.02709961,-0.018981934,0.016815186,0.049468994,0.002784729,0.031677246,0.024887085,0.02810669,0.0023326874,0.011245728,-0.009933472,0.006160736,0.0031433105,-0.029663086,0.04144287,0.025604248,0.016998291,-0.015914917,0.012321472,-0.012313843,0.037994385,-0.03765869,-0.0032634735,-0.022842407,-0.0067749023,-0.002872467,0.025741577,-0.030181885,0.011222839,-0.010353088,-0.019958496,0.03970337,0.026031494,-0.0010309219,-0.011222839,-0.020263672,0.023590088,-0.028945923,-0.020339966,0.042236328,-0.015426636,0.041992188,0.035858154,0.03277588,-0.008041382,0.020462036,0.023498535,-0.025283813,0.023284912,0.06323242,0.014427185,0.0010662079,-0.015007019,0.01789856,0.003255844,0.039398193,-0.008255005,0.016296387,0.0030174255,0.012252808,0.0052261353,0.005924225,0.013298035,-0.013404846,-0.0040245056,0.028900146,0.008255005,-0.03173828,-0.0024909973,0.010261536,-0.021011353,0.039123535,-0.022277832,0.014472961,0.0158844,-0.049591064,0.005973816,-0.028259277,0.0015535355,-0.03933716,-0.002855301,0.024398804,0.009498596,0.01184082,0.0115737915,-0.017822266,0.02532959,-0.033691406,0.013114929,0.033172607,-0.03189087,8.8751316e-05,-0.0017032623,0.031143188,0.038391113,-0.0011415482,-0.027435303,-0.00749588,0.0018129349,0.013824463,0.023330688,-0.021896362,-0.0113220215,0.018081665,0.00032925606,-0.012817383,0.00793457,-0.021560669,-0.033721924,-0.03543091,-0.023330688,-0.008934021,0.011489868,-0.01360321,1.1265278e-05,-0.028182983,0.001461029,-0.00024020672,-0.017471313,0.012420654,0.027130127,0.017715454,0.02458191,-0.026931763,0.014518738,-0.012802124,0.0098724365,0.030761719,-0.013923645,-0.0070343018,0.032073975,-0.026779175,-0.033996582,-0.029159546,-0.02947998,-0.0463562,-0.0039043427,0.010597229,0.024353027,0.03677368,-0.039093018,0.02420044,-0.008644104,-0.01776123,0.01071167,0.023239136,0.024551392,0.0033073425,-0.008468628,-0.0007839203,0.035339355,0.048187256,-0.014320374,0.026489258,0.02432251,-0.009185791,0.01928711,0.019714355,0.005584717,-0.004699707,0.062286377,-0.008628845,0.002155304,0.02166748,0.027236938,0.011566162,-0.025375366,0.038238525,0.009109497,-0.031280518,-0.0024604797,0.04058838,0.0395813,0.010734558,-0.0049057007,0.029708862,0.025527954,0.00749588,-0.01739502,0.018051147,0.0010194778,-0.008888245,-0.012397766,0.0025520325,0.018569946,-0.0041656494,-0.0068588257,0.017944336,-0.005054474,0.020065308,0.009605408,-0.0027713776,-0.0025520325,-0.004878998,-0.0154953,-0.0099487305,-0.00073194504,0.004638672,-0.014122009,-0.0024967194,-0.046905518,-0.026184082,-0.0137786865,0.03262329,0.00819397,0.009651184,-0.0012741089,-0.024795532,0.033843994,0.0037765503,0.0016088486,0.03286743,0.006996155,-0.002571106,-0.005268097,-0.009544373,0.01033783,-0.07623291,0.021987915,0.00969696,0.016586304,0.072753906,-0.004535675,0.015174866,-0.051361084,0.012275696,0.025787354,-0.0104599,0.001282692,0.0033435822,0.034484863,0.01260376,-0.017166138,0.0031223297,0.0005598068,-0.040130615,0.001964569,0.01638794,0.016357422,0.02015686,0.04156494,3.33786e-05,0.011192322,-0.011772156,0.007724762,0.023971558,0.0077400208,0.009552002,0.006919861,0.026550293,0.021072388,0.019607544,0.02532959,0.019241333,-0.01713562,-0.013900757,-0.03237915,-0.0046920776,0.009811401,0.01651001,0.00819397,-0.009094238,0.027801514,-0.0066490173,0.014442444,0.036834717,0.021820068,-0.021194458,-0.021499634,0.010627747,-0.010261536,0.056488037,0.010406494,-0.017990112,0.0018434525,0.034484863,0.010139465,-0.040863037,-0.007358551,-0.022323608,-0.00094509125,0.025924683,-0.007835388,0.002286911,0.013664246,-0.0029659271,-0.016052246,-0.03930664,0.015266418,-0.0017747879,-0.004573822,0.009208679,-0.00080633163,0.026535034,-0.012275696,-0.022750854,0.005657196,-0.0056877136,0.00844574,0.0063591003,0.001996994,0.012573242,0.0023212433,0.027648926,-0.0008120537,-0.013015747,-0.00894165,0.039733887,0.007297516,-0.02432251,0.01121521,0.014419556,-0.011741638,-0.015457153,-0.015838623,0.04928589,0.018295288,0.015525818,-0.011451721,0.0069007874,0.013252258,0.041412354,-0.019470215,-0.0143966675,0.043426514,0.017211914,-0.008781433,-0.0007839203,-0.04473877,0.01940918,-0.0113220215,-0.026748657,-0.03250122,0.016998291,-0.0045051575,-0.00028038025,-0.010498047,0.028045654,-0.012252808,-0.01676941,0.034332275,-0.015426636,-0.03152466,-0.020370483,-0.013969421,0.033172607,0.010070801,-0.00730896,0.01260376,0.0102005005,-0.02229309,0.0012235641,-0.0044517517,0.026489258,-0.00932312,-0.04486084,0.0143966675,-0.003780365,-0.01222229,0.010475159,-0.0072135925,0.028808594,-0.0066604614,0.003118515,-0.025344849,0.0068473816,0.022338867,-0.028442383,-0.015571594,0.035339355,-0.011047363,-0.022903442,0.033721924,-0.008583069,-0.009880066,0.032836914,0.0076522827,-0.0154953,-0.0390625,-0.018615723,-0.0055236816,-0.01260376,0.004673004,-0.0066604614,0.013175964,0.015319824,-0.032409668,-0.028839111,0.004337311,0.025146484,0.015914917,0.000688076,-0.025985718,-0.0022697449,0.0072364807,0.001964569,0.008979797,0.029052734,0.0056114197,-0.019699097,0.014427185,-0.020767212,-0.007286072,-0.012573242,-0.02822876,0.025726318,0.01676941,-0.016082764,-0.013847351,0.020874023,-0.009597778,0.03527832,-0.00038599968,0.02229309,0.023742676,-0.004714966,0.011817932,-0.032409668,0.045074463,-0.0129470825,-0.023391724,-0.012168884,-0.00932312,0.004760742,0.021850586,0.019882202,-0.013999939,-0.0051994324,0.034729004,-0.017532349,0.027160645,-0.01576233,-0.016021729,0.05050659,-0.015716553,0.007774353,-0.013793945,0.0030670166,0.008369446,-0.0071868896,0.036712646,-0.00484848,-0.0052223206,-0.014381409,-0.027435303,-0.00041937828,0.01939392,-0.011222839,0.0062942505,0.04397583,0.013839722,0.025802612,-0.0016298294,-0.0064201355,-0.026809692,-0.015838623,0.017532349,0.022003174,0.019485474,0.016815186,0.029953003,0.029159546,-0.03894043,-0.0066986084,-0.011238098,-0.042175293,0.0115737915,-0.025878906,-0.016860962,-0.0015516281,0.02482605,-0.06744385,-0.028503418,0.00504303,-0.0026283264,-0.005630493,-0.040252686,-0.0014438629,0.0028686523,-0.00028967857,-0.027053833,-0.025848389,-0.0037193298,-0.005634308,-0.019943237,-0.013053894,0.045288086,-0.020645142,0.03857422,-0.0049743652,0.0012607574,-0.01550293,0.019088745,0.017166138,-0.005306244,-0.006511688,-0.015426636,0.0020198822,-0.007209778,-0.035888672,-0.016967773,0.00881958,0.010894775,-0.017166138,0.010215759,-0.010848999,0.009941101,0.0068511963,0.025039673,0.017150879,0.0025520325,0.0065689087,0.0045051575,-0.036102295,-0.00018274784,0.013580322,0.003112793,-0.03515625,-0.028289795,-0.00756073,0.01713562,0.012046814,-0.003791809,0.0025463104,0.007865906,0.011146545,-0.038879395,-0.004131317,0.040100098,-0.0126953125,-0.02432251,0.008766174,-0.0104599,-0.07196045,0.022781372,0.018676758,0.02645874,0.019165039,-0.0028076172,-0.017684937,0.04071045,-0.0032691956,0.035369873,0.007980347,0.038330078,-0.008117676,-0.019638062,-0.014480591,-0.013221741,0.012077332,0.025375366,0.012001038,0.024749756,-0.007659912,0.016983032,-0.015579224,0.01638794,-0.008293152,-0.050109863,0.05355835,-0.026046753,0.025344849,0.0050315857,-0.023391724,0.009849548,0.0047302246,0.015068054,-0.05328369,-0.023773193,-0.02029419,0.0096588135,-0.0064888,0.034179688,-0.022537231,-0.007911682,0.00052928925,0.0007867813,-0.01939392,-0.012428284,0.04257202,-0.0340271,0.023223877,0.011665344,-0.010063171,0.0001450777,0.0072631836,0.025039673,-0.010932922,0.004722595,-0.007171631,0.025939941,0.037475586,-0.012664795,-0.001124382,-0.010108948,-0.0029659271,-0.031036377,0.016052246,0.0098724365,-0.015853882,-0.0082092285,0.019104004,-0.0052986145,0.04373169,0.04824829,0.02708435,0.01687622,0.019088745,0.0055618286,0.0027770996]
2	20261101_000003	BNFT_7CA4D36CA64C	ONE MORE 대중교통 캐시백	CASHBACK	LOCAL	PRODUCT	\N	{"branches": [{"atoms": [{"atom_key": "transit_spend", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 100000, "cond_raw_txt": "- 지난달 1일부터 말일(승인 시점 기준)까지 국내외 일시불 이용금액 10만원/20만원 이상 시\\n ONE MORE 서비스 제공", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "spend_exclusions", "atom_seq": 2, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "cond_type_cd": "SPEND_EXCL", "excl_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}, {"atoms": [{"atom_key": "transit_grace", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공", "cond_type_cd": "GRACE", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 2}], "expr_status_cd": "DRAFT"}	\N	[{"rule_key": "transit_rate", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "transit_exclusions", "atom_seq": 1, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "value_num": 5, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "버스", "target_key": "버스", "target_type_cd": "SERVICE"}, {"target_nm": "지하철", "target_key": "지하철", "target_type_cd": "SERVICE"}], "rule_priority": null, "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}]	[]	PENDING_REVIEW	\N	\N	- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외 / 5% 캐시백	월 1천원	혜택명: ONE MORE 대중교통 캐시백\n혜택 유형: 캐시백\n서비스 대상: 버스, 지하철\n혜택 내용: 5% 캐시백	[-0.029144287,-0.041992188,-0.035888672,0.028503418,0.0025196075,-0.024902344,-0.06274414,0.06225586,0.025390625,-0.03074646,-0.009567261,-0.017044067,0.02243042,0.027801514,0.03643799,0.012588501,-0.01625061,0.036315918,-0.0064697266,-0.016723633,-0.01171875,0.0050849915,0.07019043,0.00017547607,0.019317627,-0.0025634766,-0.022766113,-0.051574707,0.0027217865,-0.07043457,-0.01977539,-0.011650085,0.051330566,-0.05126953,0.01965332,0.020050049,-0.036499023,0.0028038025,0.06738281,-0.046417236,0.014770508,-0.027679443,0.031982422,-0.061767578,0.02015686,0.0048179626,0.04611206,-0.043670654,-0.051757812,0.05545044,0.018432617,0.008026123,0.009986877,-0.07293701,-0.0084991455,-0.009048462,-0.011878967,-0.0015964508,0.052825928,-0.026016235,-0.015792847,-0.046783447,-0.0335083,0.014427185,0.011962891,0.0012493134,0.009162903,-0.02281189,-0.014968872,0.01272583,0.016204834,0.028213501,0.05508423,0.008224487,-0.0022945404,-8.702278e-06,-0.016159058,0.0065689087,0.053771973,0.012802124,0.016220093,-0.020751953,-0.019699097,0.0013303757,-0.00957489,-0.0501709,-0.07165527,-0.010673523,-0.035949707,0.018661499,0.03213501,-0.02104187,-0.026260376,0.024673462,0.019836426,-0.016479492,-0.02772522,-0.03050232,-0.004261017,-0.00831604,0.03527832,-0.029708862,0.0085372925,0.011222839,-0.010887146,0.017990112,-0.043670654,0.006706238,0.01802063,0.010696411,-0.005016327,0.005947113,-0.019058228,0.025360107,0.04107666,-0.006072998,0.05380249,-0.055480957,-0.025650024,0.021148682,0.0046691895,-0.027175903,-0.062164307,-0.05255127,-0.046722412,-0.0072021484,0.006214142,-0.0033512115,-0.047973633,0.03265381,-0.022903442,0.014144897,0.01776123,0.034698486,0.005092621,-0.022964478,-0.021591187,-0.006023407,-0.024597168,-0.01234436,-0.010032654,0.00022399426,0.048187256,0.014671326,-0.035949707,-0.051757812,0.025146484,-0.0012578964,-0.0390625,0.026641846,0.02166748,-0.013679504,-0.060791016,-0.0018072128,-0.05545044,-0.026824951,-0.016479492,0.05670166,-0.071899414,-0.0023860931,0.01940918,-0.046173096,-0.045776367,-0.02708435,0.029525757,0.02243042,-0.042907715,0.033813477,-0.06567383,-0.014175415,-0.033599854,-0.024337769,-0.020462036,0.019332886,-0.022247314,-0.008773804,0.013618469,-0.038360596,-0.016998291,-0.0007214546,0.033966064,0.06561279,0.017425537,-0.011482239,-0.0121154785,-0.043151855,0.020614624,-0.008834839,0.0068740845,0.042938232,-0.0016078949,0.022079468,-0.012397766,-0.019729614,-0.023864746,0.02798462,-0.014884949,0.002861023,0.0024662018,-0.038208008,0.007949829,-0.013320923,0.02154541,-0.0036239624,-0.041931152,-0.08190918,-0.019180298,0.018432617,0.023925781,-0.027130127,-0.0014801025,-0.016723633,-0.014465332,0.014671326,-0.019699097,0.019821167,0.004714966,0.042663574,0.023376465,0.014831543,0.0077705383,-0.059051514,0.013076782,0.03111267,0.039031982,0.036743164,-0.01184082,0.024154663,-0.021270752,-0.046875,-0.004425049,0.019119263,-0.043945312,-0.013954163,-0.008163452,0.05734253,0.042541504,-0.010856628,-0.006828308,-0.038330078,0.01058197,0.024673462,0.036346436,-0.021209717,0.039398193,0.019241333,-0.010734558,-0.036315918,-0.0038661957,0.0020389557,0.015792847,0.028213501,-0.018920898,-0.034057617,0.013969421,0.034698486,0.025115967,0.0022850037,0.03286743,-0.013832092,0.02809143,-0.00037837029,-0.010253906,-0.014801025,-0.016342163,-0.019622803,0.05532837,-0.005142212,0.03765869,0.014030457,-0.013015747,0.004878998,0.023742676,-0.010299683,-0.0031089783,-0.035217285,0.016662598,0.010253906,0.020492554,-0.016693115,-0.005569458,0.028289795,0.03479004,-0.03564453,0.03579712,0.01625061,0.049438477,-0.032684326,0.013938904,-0.015029907,0.0013074875,-0.0209198,-0.008262634,-0.068603516,-0.005180359,-0.004837036,-0.00061655045,-0.0262146,0.03363037,0.006641388,-0.006477356,0.059143066,-0.034118652,-0.009811401,0.01184082,0.07977295,0.0061187744,0.03656006,-0.042663574,-0.010765076,-0.014137268,0.020202637,-0.043823242,0.058898926,-0.01272583,-0.03668213,-0.021026611,-0.022064209,0.0524292,-0.00061130524,0.022018433,-7.8976154e-05,0.0019226074,0.024612427,0.023086548,-0.007987976,0.0020503998,-0.022094727,-0.040740967,-0.021591187,0.018722534,-0.0044784546,0.077941895,0.0023269653,-0.048950195,-0.018981934,-4.529953e-06,0.018325806,0.014823914,0.006565094,0.030014038,-0.022003174,-0.03451538,-0.022460938,-0.03753662,-0.05319214,0.074645996,0.011100769,0.014213562,0.022659302,0.010398865,0.020751953,-0.018661499,-0.0059318542,-0.025421143,0.011505127,0.012435913,0.014045715,-0.057678223,0.0552063,-0.014335632,0.013374329,-0.0075798035,0.022521973,0.0491333,0.033355713,0.013961792,0.0052490234,0.009185791,-0.0036830902,-0.045135498,0.04699707,0.022720337,0.030441284,-0.0027675629,0.017150879,0.035461426,0.053619385,0.047027588,-0.023452759,-0.0010404587,-0.062561035,-0.0053367615,0.02571106,0.08758545,0.014076233,0.01864624,0.0084991455,0.007926941,0.026260376,-0.018920898,0.030899048,-0.012542725,-0.0141067505,0.0055236816,0.0034046173,-0.0076560974,0.0635376,-0.053009033,0.003786087,0.01083374,-0.0513916,-0.0016212463,-0.00023651123,0.01725769,0.043762207,-0.017166138,-0.015975952,-0.013206482,-0.016906738,0.015670776,-0.059295654,0.040802002,-0.00046396255,0.031677246,0.0057792664,-0.04296875,0.002588272,-0.012817383,-0.045532227,-0.0044403076,0.0010280609,-0.048736572,-0.024108887,0.013290405,-0.0317688,0.014091492,0.10083008,0.0044059753,-0.020080566,0.021850586,-0.0031433105,-0.0054397583,0.01335144,-0.010185242,-0.035736084,0.009925842,0.016143799,-0.012245178,-0.020339966,-0.056488037,0.0071868896,-0.027664185,-0.00024914742,0.002752304,-0.019485474,0.0069465637,0.03744507,-0.026016235,0.052947998,-0.07421875,0.0033817291,-0.09124756,-0.005947113,-0.053894043,-0.04095459,0.038024902,-0.0690918,0.022338867,-0.008522034,-0.019729614,-0.01928711,0.0035972595,-0.019851685,0.044677734,-0.016342163,0.04055786,-0.026504517,0.010986328,-0.030029297,-0.008049011,0.09613037,0.013748169,0.062561035,0.011802673,-0.0027389526,0.0021400452,0.005432129,0.037628174,-0.0070610046,-0.016357422,-0.051208496,-0.0066566467,-0.021392822,0.00078582764,0.047607422,0.06939697,0.0031909943,0.003829956,-0.049560547,0.026382446,0.008346558,0.037994385,-0.006340027,-0.0040779114,-0.05166626,-0.014205933,0.007381439,0.001991272,-0.031951904,-0.017364502,-0.034240723,-0.0013189316,-0.024475098,0.0236969,0.0039405823,-0.010032654,-0.036193848,-0.0262146,-0.008796692,-0.041931152,-0.0022201538,-0.03717041,-0.034484863,-0.002746582,-0.01209259,-0.02532959,0.029525757,-0.014328003,0.022323608,-0.027145386,-0.009185791,0.031280518,-0.0335083,0.016189575,-0.0062446594,0.019104004,-0.049316406,0.0143585205,0.019363403,-0.025939941,-0.015525818,0.014823914,8.648634e-05,0.00258255,-0.014137268,0.021469116,0.05670166,-0.010147095,0.016403198,-0.0040397644,-0.019577026,0.03894043,0.0005745888,-0.007850647,-0.0045661926,0.01360321,-0.029037476,0.011497498,0.010406494,-0.01914978,-0.02835083,-0.005016327,0.0068740845,0.037261963,-0.016494751,0.003622055,0.0039711,0.023880005,-0.02305603,0.0031280518,0.0064849854,-0.003129959,0.009986877,-0.03616333,0.059143066,0.013069153,0.006996155,0.008956909,-0.026412964,-0.023452759,0.014335632,-0.0025482178,0.013008118,-0.0256958,-0.016418457,-0.021224976,-0.010955811,-0.0036888123,-0.0099105835,0.027877808,0.021652222,0.009765625,0.020935059,0.0024929047,-0.017028809,-0.004901886,-0.007610321,-0.011604309,0.0026512146,0.0023269653,0.009384155,-0.035980225,-0.007347107,-0.032196045,0.027297974,-0.00598526,0.022033691,0.033355713,-0.012245178,0.01713562,-0.07513428,-0.009803772,-0.00774765,-0.019760132,-0.036346436,0.006793976,-0.015640259,0.02708435,-0.0052871704,0.056640625,0.033416748,0.010925293,-0.030014038,-0.022125244,0.005756378,-0.050720215,0.012649536,0.00075769424,0.008346558,-0.013687134,-0.008255005,-0.0023021698,-0.06347656,-0.025344849,0.02418518,-0.018936157,-0.027313232,0.015823364,-0.023483276,-0.013252258,0.0038051605,-0.006008148,-0.05319214,0.003490448,0.029464722,-0.026809692,0.011695862,0.0067481995,-0.020217896,0.005176544,0.016601562,-0.0035896301,-0.017700195,-0.01725769,-0.011199951,0.04748535,-0.00598526,0.035980225,-0.007118225,0.033203125,-0.03062439,-0.021606445,-0.03152466,0.026062012,-0.0040779114,-0.0039978027,0.03994751,0.026901245,0.010108948,-0.037475586,0.028411865,-0.013511658,-0.012168884,0.021224976,0.03768921,0.040100098,0.030960083,0.018127441,-0.015464783,0.013160706,0.0029830933,0.03543091,0.005710602,-0.010910034,0.06689453,0.008529663,-0.006099701,0.0029010773,-0.024337769,-0.009880066,0.016708374,-0.032318115,-0.020614624,0.011131287,-0.01663208,0.0023117065,-0.007709503,-0.02456665,0.012756348,-0.013473511,-0.004875183,0.02684021,0.043182373,-0.008216858,0.013450623,0.028289795,0.015930176,-0.017242432,-0.0090408325,-0.034118652,-0.018157959,0.032928467,-0.0121154785,-0.037994385,0.011192322,0.046905518,-0.0013065338,0.023925781,0.0053977966,0.03805542,-0.018600464,-0.013328552,-0.028182983,0.027679443,0.017333984,-0.018005371,-0.002243042,0.015388489,-0.008460999,-0.012168884,-0.017486572,-0.045196533,-0.026763916,0.005458832,0.012374878,-0.050689697,-0.0050468445,-0.02670288,-0.01335907,0.032043457,-0.0026664734,-0.006580353,0.016403198,0.006164551,0.0107421875,-0.03793335,0.010231018,-0.023254395,-0.010345459,0.047210693,-0.04486084,0.024978638,-0.039916992,-0.0031089783,-0.011665344,-0.000341177,-0.031433105,-0.054901123,-0.01448822,-0.009681702,0.0026988983,0.04949951,0.0071258545,0.016067505,-0.007686615,0.01285553,-0.0078125,-0.00023448467,-0.022277832,-0.0019350052,0.004940033,0.0021591187,-0.027801514,-0.004722595,0.015838623,-0.013015747,-0.039276123,-0.025421143,-0.002046585,0.019241333,-0.018630981,0.00064992905,0.02078247,0.037963867,0.029342651,-0.013771057,-0.014404297,-0.0047416687,-0.015899658,-0.014205933,-0.0023937225,-0.00036239624,-0.00042581558,-0.006801605,0.0077400208,0.025054932,-0.01020813,0.018127441,-0.024169922,0.012176514,-0.017547607,-0.004798889,-0.016311646,0.012367249,0.013633728,-0.0049705505,-0.035888672,-0.011741638,0.03012085,-0.011154175,0.015563965,-0.03704834,0.0032978058,0.021118164,-0.018371582,0.007896423,0.03378296,-0.016525269,-0.046020508,0.004524231,-0.020462036,0.028244019,-0.004173279,0.0049858093,0.00592041,-0.028045654,0.031707764,-0.02684021,-0.012969971,0.007507324,-0.040863037,0.020507812,-0.017120361,0.0010795593,0.0009560585,-0.010421753,0.0031986237,0.00042319298,-0.008460999,-0.033050537,-0.01637268,0.016601562,-0.007610321,0.0082473755,0.008956909,0.007972717,0.009513855,-0.04660034,0.031311035,0.035858154,0.034210205,0.0087509155,-0.06161499,-0.03829956,0.023742676,-0.020858765,-0.02331543,-0.04257202,0.019805908,-0.039215088,0.013648987,-0.04208374,0.02999878,0.028167725,-0.009155273,-0.0023403168,-0.00844574,0.010650635,0.015777588,-0.028915405,0.016693115,-0.015792847,-0.045776367,0.03387451,0.011924744,0.03024292,0.036712646,0.004688263,0.014053345,0.0009202957,-0.05807495,0.0065345764,-0.016677856,0.009017944,0.0012807846,0.013626099,0.003314972,-0.022003174,-5.441904e-05,0.03353882,-0.0178833,-0.021881104,0.030593872,0.023513794,0.056427002,-0.023391724,0.014144897,0.003616333,-0.012916565,0.049713135,-0.022750854,0.020126343,0.0079574585,0.014823914,-0.008354187,-0.030090332,0.007091522,-0.0048446655,-0.020202637,-4.774332e-05,0.00031757355,-0.066345215,0.008735657,0.00066900253,0.019607544,-0.015144348,0.004776001,-0.0020313263,0.03213501,-0.027740479,-0.0473938,0.016906738,0.01802063,0.022644043,-0.0042037964,-0.023803711,0.032470703,0.060150146,-0.005290985,0.0038967133,-0.009864807,0.017913818,-0.02243042,0.014137268,-0.012756348,-0.0047187805,0.011817932,0.0041389465,0.0015621185,-0.008155823,0.00033640862,0.0158844,0.022994995,-0.03213501,-0.0076179504,-0.0035476685,0.006801605,0.0054740906,-0.02909851,0.011878967,-0.00044202805,-0.0018386841,-0.01499939,-0.018722534,0.0211792,0.008041382,-0.025634766,-0.00018489361,0.011756897,-0.00522995,-0.00806427,0.0021743774,0.01739502,-0.027359009,-0.010734558,-0.012878418,0.0053253174,0.053741455,0.0056610107,-0.023483276,-0.020996094,0.0178833,-0.043151855,0.007896423,0.008033752,-0.010856628,0.00995636,0.06317139,0.025650024,-0.009483337,0.019943237,-0.007598877,0.026184082,0.03668213,0.047210693,0.010421753,0.013542175,-0.017700195,0.013961792,-0.054138184,-0.00028276443,0.058898926,0.048675537,0.0031223297,0.011528015,-0.030059814,-0.0023288727,0.033843994,-0.014633179,0.010383606,0.0435791,0.009513855,0.018188477,0.0011739731,-0.049346924,0.0074310303,-0.001502037,0.003129959,-0.010177612,-0.015205383,-0.021591187,0.015853882,0.012268066,0.009437561,0.014915466,0.0082092285,-0.0049552917,-0.000487566,-0.012939453,0.010177612,-0.037078857,0.027053833,-0.0335083,-0.0077056885,0.027542114,0.027816772,0.0054779053,0.008674622,-0.020248413,0.01071167,0.001039505,0.006011963,0.035339355,-0.01386261,-0.0025081635,0.007751465,-0.004459381,0.006755829,-0.0041656494,0.031463623,-0.01802063,0.030456543,-0.002008438,-0.039031982,0.015899658,-0.02166748,-0.014328003,0.007255554,0.000541687,-0.01876831,-0.025787354,0.0009946823,-0.013282776,-0.039398193,-0.011604309,-0.0043945312,-0.0045166016,-0.0048561096,0.009407043,0.027908325,-0.00945282,-0.051208496,-0.0073547363,-0.015853882,0.006629944,0.022445679,-0.014297485,-0.03994751,-0.0041275024,0.0044403076,-0.04119873,-0.009750366,0.0018138885,0.028427124,0.0026626587,0.0012588501,-0.003791809,-0.017791748,-0.031402588,0.018203735,0.027420044,0.006000519,-0.017578125,-0.020324707,-0.02558899,0.015312195,0.03515625,5.5730343e-05,-0.0031223297,-0.013504028,0.0039978027,-0.003238678,-0.020599365,0.01651001,0.010604858,0.024627686,0.014953613,-0.0066490173,0.02671814,-0.0021629333,-0.0068092346,0.013557434,0.03604126,0.0009608269,-0.007045746,-0.012496948,0.009155273,0.02885437,0.012283325,0.015007019,0.053497314,0.046142578,-0.0040740967,-0.011604309,0.013290405,-0.036621094,-0.01146698,-0.017944336,-0.009666443,0.01272583,0.032318115,-0.0015153885,0.0046463013,0.013221741,0.011680603,0.0074272156,0.02305603,-0.013900757,-0.0146102905,-0.03363037,-0.02319336,0.02684021,0.0070724487,-0.002943039,0.0020713806,-0.050567627,-0.037200928,0.016174316,0.0042304993,0.051757812,0.019454956,-0.01638794,-0.00299263,0.013404846,0.014678955,0.018676758,-0.0020599365,-0.011940002,-0.03050232,-0.03274536,-0.0103302,-0.00012409687,0.0018453598,0.025878906,-0.009750366,-0.026184082,0.060821533,0.014976501,0.025665283,-0.021820068,0.0126953125,0.0064926147,-0.0127334595,0.021606445,0.025115967,0.018737793,0.012542725,0.01424408,0.016540527,-0.021881104,-0.0068244934,0.04650879,0.0129776,-0.012557983,0.026504517,0.02809143,-0.020462036,0.0061187744,0.01272583,-0.014793396,0.018005371,0.021575928,0.0071258545,0.017684937,0.009742737,-0.00048160553,0.0007843971,0.015319824,0.020980835,0.0032463074,0.018035889,-0.017150879,-0.043395996,-0.011878967,-0.0021743774,-0.028930664,-0.0090408325,0.036010742,0.012001038,0.026473999,0.029388428,0.05368042,0.016235352,-0.015060425,0.019973755,-0.016860962,0.059143066,-0.022766113,-0.045013428,-0.007972717,0.006904602,0.02078247,-0.0025920868,-0.010665894,0.016281128,-0.0027694702,0.041992188,-0.023513794,0.010803223,-0.009742737,0.006011963,-0.013999939,-0.060424805,-0.013168335,0.015914917,0.011528015,-0.021240234,-0.013809204,-0.01828003,-0.012107849,-0.003419876,0.008262634,-0.017349243,3.451109e-05,0.010818481,-0.0036449432,0.033843994,0.06970215,0.023132324,0.008216858,-0.024154663,-0.021530151,-0.009017944,0.025665283,0.0027217865,0.018341064,-0.0036392212,0.011802673,-0.03765869,-0.035186768,0.04562378,-0.006500244,-0.0019226074,-0.025665283,-0.012825012,-0.028503418,0.012107849,-0.011810303,-0.0050964355,0.035339355,-0.0050315857,0.022903442,-0.007736206,-0.0042381287,0.03414917,-0.0006723404,0.0042266846,0.012275696,0.033111572,-0.011199951,0.017929077,0.001335144,0.01574707,0.015136719,-0.029418945,0.03314209,-0.021957397,-0.011100769,-0.022506714,-0.017974854,-0.0025749207,-0.008140564,0.010108948,0.00617218,-0.0060577393,-0.028045654,0.0024089813,-0.005695343,-0.009681702,0.023666382,0.009941101,-0.02810669,-0.033843994,0.009925842,0.013587952,0.0039520264,0.013435364,-0.01991272,0.00027179718,-0.012817383,-0.010299683,0.027450562,-0.005218506,-0.026931763,0.027069092,0.0071983337,0.015670776,0.012207031,-0.0004453659,-0.047332764,0.0071411133,0.013504028,0.01550293,-0.017181396,0.005203247,0.019897461,0.0033454895,0.01335144,-0.039398193,-0.049987793,-0.019378662,-0.010551453,-0.0056419373,0.012588501,0.012466431,0.026321411,-0.008613586,-0.03189087,-0.0057792664,0.008117676,-0.004196167,-0.011100769,0.030517578,0.021835327,-0.023757935,0.024780273,-0.0126953125,0.002046585,-0.0287323,-0.012313843,0.02015686,-0.011726379,-0.023727417,-0.022323608,0.010231018,0.019821167,0.024276733,0.0102005005,0.034332275,0.04748535,-0.016586304,0.006626129,0.0032672882,0.006614685,-0.01776123,0.017852783,-0.005844116,0.022766113,-0.016189575,0.0287323,-0.022567749,-0.010231018,-0.0065193176,0.026947021,-0.016601562,0.008392334,0.035980225,-0.02142334,0.030090332,0.0039863586,0.0041885376,-0.0104904175,0.0030612946,0.005874634,0.024917603,-0.00390625,0.009307861,-0.0004067421,-0.01184082,-0.008125305,-0.023025513,0.01512146,0.021408081,0.012023926,0.015472412,-0.029296875,0.0065193176,-0.053985596,-0.0053520203,-0.006412506,0.018463135,-0.037261963,-0.009483337,-0.0069236755,-0.00705719,0.010543823,-0.008583069,-0.049987793,-0.011940002,-0.025894165,-0.00015628338,0.01965332,-0.018218994,-0.013999939,-0.019088745,0.02508545,-0.033325195,-0.00093364716,-0.022003174,-0.010528564,0.0036315918,-0.019714355,-0.010299683,-0.008110046,0.048431396,-0.020965576,-0.0335083,0.018493652,-0.000834465,-0.0062179565,0.03451538,0.015945435,-0.01663208,-0.008399963,0.019454956,0.018127441,-0.039794922,0.01675415,0.030136108,-0.031280518,0.008621216,0.004787445,-0.0054244995,0.0033302307,-0.024398804,-4.220009e-05,0.019226074,0.028152466,0.0046195984,-0.011932373,0.017700195,0.013710022,0.02444458,0.04031372,-0.021697998,0.0044670105,-0.019897461,0.0017766953,-0.032287598,0.008239746,0.00894165,0.029632568,-0.017425537,-0.058654785,0.009269714,-0.02532959,0.019088745,-0.031280518,-0.019195557,-0.013450623,0.033294678,0.008346558,0.0041503906,0.0048942566,-0.009391785,-0.017578125,-0.005191803,0.006210327,-0.024612427,0.006916046,-0.023788452,0.03201294,0.04711914,-0.019515991,-0.0034618378,0.029785156,-0.028121948,0.021881104,-0.011962891,0.005203247,-0.011047363,0.017196655,-0.015342712,0.0068588257,0.0076293945,0.05239868,-0.00018417835,0.028549194,0.0029888153,0.021713257,-0.008773804,-0.017791748,-0.015625,-0.03643799,0.0037384033,-0.02015686,-0.0063209534,-0.0070724487,-0.024154663,-0.007499695,-0.00983429,0.005619049,-0.016662598,0.0211792,0.027862549,0.023986816,0.003873825,0.008590698,-0.01675415,0.029464722,0.0019197464,-0.001499176,0.06744385,-0.027877808,0.02696228,-0.042175293,0.016540527,-0.001376152,-0.016235352,0.009788513,0.014457703,0.026245117,-9.75132e-05,0.020401001,-0.0007824898,0.033447266,0.008682251,-0.03527832,-0.0027198792,-0.0072135925,0.011009216,0.025360107,0.03137207,-0.026275635,0.0044822693,-0.03375244,0.00573349,-0.0062789917,0.0592041,0.034484863,0.032165527,0.024749756,-0.010818481,0.022781372,0.022659302]
\.


--
-- TOC entry 4387 (class 0 OID 21670)
-- Dependencies: 381
-- Data for Name: card_common; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_common (card_common_id, common_cd, common_nm, brand_cd, service_grade_cd, common_note, create_date, create_user_id, update_date, update_user_id) FROM stdin;
1	VISA_SIGNATURE	Visa Signature	VISA	SIGNATURE	\N	2026-11-02 21:07:17.527365+00	SYSTEM	2026-11-02 21:07:17.527365+00	SYSTEM
6	AMEX_PLATINUM_ELITE	AMEX Platinum Elite	AMEX	PLATINUM_ELITE	\N	2026-11-03 05:20:34.783526+00	SYSTEM	2026-11-03 05:20:34.783526+00	SYSTEM
7	AMEX_PLATINUM	AMEX Platinum	AMEX	PLATINUM	\N	2026-11-03 05:20:39.726129+00	SYSTEM	2026-11-03 05:20:39.726129+00	SYSTEM
9	MASTERCARD_PLATINUM	Mastercard Platinum	MASTERCARD	PLATINUM	\N	2026-11-03 05:20:52.903041+00	SYSTEM	2026-11-03 05:20:52.903041+00	SYSTEM
11	MASTERCARD_WORLD	Mastercard World	MASTERCARD	WORLD	\N	2026-11-03 05:21:03.19387+00	SYSTEM	2026-11-03 05:21:03.19387+00	SYSTEM
13	UPI_DIAMOND	UnionPay Diamond	UPI	DIAMOND	\N	2026-11-03 05:21:14.154311+00	SYSTEM	2026-11-03 05:21:14.154311+00	SYSTEM
15	UPI_PLATINUM	UnionPay Platinum	UPI	PLATINUM	\N	2026-11-03 05:21:23.814442+00	SYSTEM	2026-11-03 05:21:23.814442+00	SYSTEM
16	VISA_INFINITE	Visa Infinite	VISA	INFINITE	\N	2026-11-03 05:21:28.533172+00	SYSTEM	2026-11-03 05:21:28.533172+00	SYSTEM
17	VISA_PLATINUM	Visa Platinum	VISA	PLATINUM	\N	2026-11-03 05:21:32.951882+00	SYSTEM	2026-11-03 05:21:32.951882+00	SYSTEM
\.


--
-- TOC entry 4389 (class 0 OID 21687)
-- Dependencies: 383
-- Data for Name: card_common_bnft; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_common_bnft (card_common_id, card_common_bnft_id, bnft_cd, bnft_nm, bnft_type_cd, service_type_cd, bnft_rule_txt, bnft_limit_txt, bnft_valid_from, bnft_valid_to_excl, create_date, create_user_id, update_date, update_user_id, bnft_search_txt, bnft_embedding) FROM stdin;
1	20261103_000001	BRAND_7F12FC9CF2DC6811E91AE8A18EB1B6CE1379238A4FA2599FB407442C5F046BB9	Visa 컨시어지	SERVICE	COMMON	Visa 컨시어지제공	\N	2026-01-01	2027-01-01	2026-11-02 21:07:25.238029+00	SYSTEM	2026-11-02 21:07:33.157764+00	SYSTEM	공통서비스: Visa Signature\n브랜드: Visa\n서비스 등급: Signature\n혜택명: Visa 컨시어지\n혜택 유형: 서비스 제공\n서비스 구분: 등급 공통\n혜택 내용: Visa 컨시어지제공	[0.015350342,-0.008705139,-0.032043457,0.013534546,-0.011024475,-0.019332886,-0.052124023,0.04638672,-0.0044670105,-0.005493164,0.013000488,-0.018920898,0.011024475,-0.022033691,-0.016830444,0.0044555664,-0.07922363,0.078063965,0.022720337,-0.039154053,0.017913818,0.002658844,-0.039093018,0.011390686,0.0031909943,0.00667572,-0.05392456,0.0116119385,0.0362854,-0.037109375,0.06439209,-0.020736694,0.05831909,-0.045928955,0.0039787292,0.048675537,0.026000977,0.018371582,0.0446167,0.01776123,-0.024490356,0.023590088,-0.008522034,-0.009147644,0.054656982,0.023132324,0.004108429,0.013465881,0.012992859,0.023971558,-0.0018081665,-0.0075950623,0.0008535385,-0.007282257,-0.022003174,-0.033843994,0.019515991,0.0059051514,0.03463745,-0.009933472,0.0085372925,-0.051452637,-0.027526855,-0.0067100525,0.01146698,0.013748169,-0.037384033,0.0087890625,-0.024215698,-0.035980225,-0.010566711,0.022109985,0.03805542,0.033843994,-0.0026454926,0.018127441,-0.08459473,0.0039863586,0.04425049,-0.028274536,0.003736496,-0.013519287,-0.0040664673,0.048431396,-0.03375244,-0.007701874,-0.055786133,-0.0049934387,0.024368286,0.03552246,0.0011472702,0.005378723,-0.013008118,0.0093688965,0.03074646,0.004825592,-0.0110321045,-0.0055770874,-0.015792847,0.025024414,-0.0065345764,-0.029129028,0.011985779,-0.024353027,0.029296875,-0.016921997,-0.010566711,0.041625977,-0.04284668,0.0040245056,-0.01586914,0.05532837,-0.05090332,0.02758789,0.02381897,-0.01751709,-0.00674057,-0.07299805,-0.0501709,-0.01322937,-0.00052309036,0.0044021606,0.02949524,-0.032073975,-0.031921387,0.0034160614,-0.01763916,0.03265381,-0.05569458,-0.02798462,-0.0045433044,0.0049057007,0.010238647,0.0072669983,-0.0069389343,-0.005859375,0.006668091,-0.02243042,-0.011756897,-0.009590149,-0.012298584,0.013198853,0.07684326,-0.030288696,-0.019180298,-0.06518555,-0.04397583,0.02709961,-0.08117676,0.05065918,-0.057373047,0.011268616,-0.035339355,0.024230957,-0.022994995,-0.019973755,-0.00018119812,0.051208496,-0.026504517,0.04333496,0.003627777,-0.053833008,-0.027923584,-0.033966064,0.006778717,-0.045776367,0.0030956268,0.056488037,-0.019851685,-0.006629944,-0.010932922,-0.016494751,-0.02998352,-0.005214691,-0.015640259,-0.028182983,0.03955078,-0.0024929047,0.023361206,0.0057296753,0.0015497208,0.045806885,-0.0005750656,-0.045288086,-0.02722168,0.01309967,-0.028366089,-0.05596924,0.03286743,0.025619507,-0.016693115,0.0015583038,-0.0087890625,-0.02168274,-0.004951477,-0.006881714,-0.033294678,-0.019973755,-0.022277832,-0.05038452,0.00027537346,-0.025268555,0.007183075,-0.007972717,-0.015289307,-0.049621582,-0.035614014,0.040100098,0.02986145,0.026519775,-0.005832672,-0.015640259,-0.037384033,-0.0019378662,-0.019165039,0.031204224,0.048187256,-0.029846191,0.046203613,0.004547119,-0.02897644,-0.017303467,0.0034694672,0.01878357,-0.02017212,0.01663208,-0.017745972,-0.007385254,-0.045837402,-0.02696228,-0.0231781,0.066467285,0.028747559,-0.0045700073,-0.052124023,0.056732178,-0.009681702,0.042816162,0.04232788,-0.06994629,0.00055265427,0.04135132,0.026000977,0.035888672,0.04434204,-0.0010070801,0.011222839,0.013122559,-0.0029525757,0.019165039,-0.0038337708,-0.0042037964,-0.03866577,-0.027511597,0.037078857,0.023849487,-0.0035190582,0.027770996,-0.027374268,-0.0073509216,0.025527954,-0.01763916,-0.016616821,-0.006881714,-0.024093628,-0.013786316,-0.022827148,-0.017044067,0.018600464,0.010147095,-0.040222168,-0.012802124,0.019821167,0.022003174,-0.03375244,0.012840271,0.02949524,-0.014793396,0.054504395,0.047943115,-0.012046814,0.011871338,-0.011039734,-0.0135650635,0.011886597,0.015808105,0.024932861,-0.043151855,-0.029083252,0.00982666,0.04586792,-0.021453857,-0.00737381,-0.040527344,-0.015197754,0.034423828,0.0032978058,0.008087158,0.06555176,-0.01222229,0.010215759,0.018829346,0.010940552,0.0007953644,-0.046783447,0.09576416,0.023025513,0.04309082,-0.04547119,-0.04888916,0.005455017,-0.040283203,-0.04736328,0.019683838,-0.0038909912,-0.033721924,-0.010627747,-0.027694702,0.009841919,-0.059265137,0.017089844,0.008758545,0.061584473,-0.012748718,0.014595032,-0.04324341,-0.010009766,0.0035762787,0.0043792725,-0.017486572,0.0061187744,0.005924225,0.039031982,-0.009086609,-0.06390381,-0.031982422,0.017929077,0.04486084,-0.011665344,0.045135498,-0.014602661,-0.041992188,-0.0024681091,-0.0017700195,-0.0037021637,-0.020095825,0.046447754,0.0047302246,0.038146973,0.023162842,0.013366699,-0.007709503,-0.028930664,0.01663208,-0.016998291,0.0309906,0.017028809,-0.045288086,-0.05581665,0.016693115,-0.013000488,0.006465912,-0.03366089,0.036987305,0.011161804,0.00046682358,-0.008277893,-0.025009155,0.015129089,-0.09234619,-0.027786255,0.017150879,0.06274414,0.04244995,-0.015388489,-0.011657715,0.027908325,0.040008545,0.0418396,-0.02470398,0.033691406,-0.008293152,-0.017089844,-0.0058555603,0.037353516,0.020889282,-0.032928467,-0.031280518,0.022262573,0.03414917,0.008560181,0.0395813,0.022399902,-0.031280518,-0.007850647,0.0029716492,-0.008605957,0.01108551,-0.0074882507,0.023223877,0.045715332,-0.021713257,-0.0011081696,0.007537842,-0.033203125,-0.034423828,-0.0005373955,0.025909424,0.03326416,0.035827637,0.0073509216,-0.016815186,0.015991211,-0.00995636,-0.0022010803,0.0113220215,-0.050689697,-0.025466919,0.04321289,0.021728516,0.0002450943,0.016464233,-0.042175293,-0.01600647,0.003955841,-0.044891357,0.005722046,0.051849365,0.01977539,0.026672363,-0.03527832,-0.00058841705,0.014877319,0.0054359436,-0.051574707,0.00017225742,0.042175293,-0.013397217,-0.068237305,-0.005138397,-0.013389587,0.015602112,-0.03213501,-0.037963867,0.01259613,-0.01020813,0.039154053,-0.011581421,0.0418396,0.036712646,0.0057411194,0.00415802,-0.019378662,0.019226074,-0.04373169,-0.031555176,0.04257202,0.018188477,-0.011688232,-0.027786255,-0.015022278,0.03643799,0.006023407,-0.0011453629,0.05041504,-0.040618896,-0.037139893,-0.025497437,0.00038599968,-0.002696991,-0.045684814,0.018005371,0.030578613,0.0017852783,0.030212402,-0.033721924,0.0084991455,-0.015716553,-0.005962372,0.02293396,-0.0073661804,-0.016708374,-0.06768799,-0.020874023,0.019577026,0.04034424,0.011238098,0.010002136,-0.015853882,-0.00029563904,0.052764893,0.003227234,-0.012313843,-0.0051498413,0.018127441,0.008003235,0.03753662,-0.013549805,0.0013637543,-0.018493652,-8.428097e-05,-0.06311035,0.008666992,-0.024749756,0.003572464,0.04147339,-0.0104599,-0.03765869,0.032348633,-0.019378662,-0.02494812,-0.00223732,-0.017318726,0.021606445,0.0057754517,-0.017974854,0.026809692,0.013031006,-0.010887146,-0.033416748,0.0045661926,0.013656616,0.048583984,-0.016326904,-0.017456055,0.0062026978,-0.02798462,-0.018829346,-0.031280518,-0.030395508,-0.006149292,0.005493164,-0.022735596,0.017974854,0.016586304,-0.016784668,-0.007160187,0.015007019,0.016906738,0.02079773,0.014892578,-0.005065918,0.022384644,-0.008178711,0.009147644,-0.030471802,0.022918701,-0.0016546249,0.020828247,0.044799805,-0.039489746,-0.039215088,0.030456543,0.008361816,0.013633728,-0.0016832352,0.0103302,0.001613617,-0.025741577,-0.016403198,-0.0007853508,0.008903503,-0.041870117,-0.00447464,-0.033691406,0.031677246,0.031921387,0.0154953,-0.011756897,-0.0069885254,-0.0023002625,0.005710602,0.027053833,0.030258179,0.017608643,0.014305115,-0.0042533875,-0.012084961,-0.01777649,0.028900146,-0.00806427,0.01763916,0.0027923584,0.017242432,0.019592285,-0.001830101,-0.005393982,-0.00092458725,0.042785645,-0.012138367,0.01965332,0.009475708,-0.009712219,-0.0013408661,-0.020080566,0.01965332,-0.0049095154,0.02532959,0.036315918,-0.021057129,0.037750244,-0.0028953552,-0.014320374,-0.029022217,-0.05368042,0.005645752,0.017837524,-0.03552246,0.034362793,0.034851074,0.022628784,0.007610321,0.0035362244,-0.030136108,-0.058685303,0.0066490173,-0.047943115,-0.0042648315,0.0019330978,-0.0033740997,-0.012420654,-0.020858765,0.018173218,0.014465332,0.032806396,0.037078857,0.006248474,-0.06451416,-0.034484863,0.045288086,0.040618896,0.027908325,0.029266357,-0.020721436,0.03451538,0.03881836,-0.009277344,-0.0011520386,-0.01033783,0.0018434525,-0.00217247,0.0036506653,0.0065841675,-0.06677246,0.03466797,0.008842468,-0.02017212,-0.012268066,0.02684021,0.03555298,0.0023345947,-0.043823242,0.016036987,-0.07775879,-0.006904602,0.036834717,0.019454956,0.011390686,0.029327393,0.018844604,0.0077667236,0.03366089,-0.033294678,-0.002111435,0.02571106,0.0024471283,0.020950317,0.02116394,-0.017852783,-0.03213501,-0.004589081,0.020828247,-0.024627686,0.011680603,0.002620697,0.021331787,-0.0071372986,0.023391724,0.008018494,0.00051259995,-0.011550903,-0.018569946,-0.0019874573,0.023834229,-0.019256592,-0.0057411194,-0.013450623,-0.03878784,0.006877899,-0.012069702,0.006336212,0.027420044,0.0032482147,0.006137848,0.026519775,0.02746582,0.023025513,0.035980225,-0.027816772,0.03503418,0.026779175,-0.02947998,0.008087158,-0.042907715,-0.026855469,-0.00818634,0.0073165894,-0.022125244,-0.025024414,0.009422302,-0.03591919,0.045776367,-0.033569336,-0.0019664764,0.012107849,0.025268555,-0.039978027,-0.012939453,0.017364502,-0.013381958,-0.08239746,0.007972717,-0.016418457,-0.00045108795,0.018173218,0.019378662,-0.009902954,0.017303467,-0.002790451,0.024887085,0.008132935,-0.015472412,-0.036376953,-0.014511108,0.02394104,-0.007003784,-0.023254395,0.0036754608,-0.04147339,-0.03515625,0.032196045,-0.015701294,0.019882202,0.003955841,-0.00086450577,-0.015930176,-0.037109375,-0.014663696,-0.019683838,0.0022201538,0.0008788109,0.0015058517,0.021057129,-0.0062026978,0.00030517578,-0.012626648,0.0032234192,0.01096344,0.0068473816,-0.027236938,0.052520752,0.031677246,0.012741089,0.031066895,0.0071907043,0.01651001,-0.05328369,0.023254395,-0.0135269165,0.0027103424,-0.029418945,0.041931152,-0.0043029785,0.012763977,0.032470703,0.019714355,0.0025863647,-0.014190674,-0.0010614395,0.012794495,0.03164673,-0.033203125,-0.0019874573,-0.011550903,-0.0158844,0.023986816,-0.0110321045,-0.022583008,-0.0011892319,-0.036010742,-0.0022239685,-0.015670776,-0.008956909,-0.019943237,-0.022735596,0.032348633,-0.020965576,0.001824379,0.036376953,-0.015686035,-0.015914917,-0.016830444,0.011566162,0.047302246,0.0014696121,-0.001039505,-0.012504578,0.0040359497,-0.0021133423,-0.027816772,0.0029239655,0.013557434,-0.04925537,-0.015365601,-0.0049591064,0.01159668,-0.017120361,0.02029419,-0.03086853,-0.0309906,0.044525146,-0.041107178,-0.014549255,0.02772522,0.0007901192,0.005508423,-0.03543091,-0.0042037964,-0.018585205,0.017578125,0.0008611679,0.039764404,-0.0062217712,0.037719727,0.005958557,-0.0067443848,-0.024612427,0.042633057,-0.036315918,-0.00095129013,0.064208984,-0.006603241,-0.011512756,-0.013763428,-0.016921997,0.009483337,-0.009231567,-0.026245117,0.014266968,0.019546509,-0.014732361,-0.00030827522,0.010368347,-0.011291504,0.05215454,-0.021347046,0.0035972595,0.025360107,-0.030944824,0.0155181885,-0.0018138885,0.012252808,-0.023910522,-0.057281494,0.04525757,0.033447266,-0.0022182465,0.031555176,-0.008361816,0.007987976,-0.041259766,-0.0184021,0.0072364807,-0.012283325,0.035888672,0.012451172,-0.014595032,0.007007599,-0.026000977,-0.016403198,0.02949524,0.025848389,0.0068626404,-0.013648987,0.009155273,0.03265381,0.0013494492,0.037902832,-0.010971069,0.018173218,0.01373291,0.020767212,0.017074585,-0.027114868,-0.01524353,-0.008041382,-0.03390503,0.08880615,-0.0046195984,-0.0061836243,-0.01651001,-0.05340576,-0.052764893,-0.011489868,-6.28829e-05,0.017791748,0.02822876,-0.027648926,0.025726318,0.0071372986,-0.004085541,-0.025054932,0.011314392,0.029815674,0.056427002,0.028213501,-0.030059814,0.002691269,0.0052490234,-0.013328552,0.018722534,-0.018798828,0.028701782,-0.01586914,-0.04421997,-0.05630493,-0.034240723,-0.068603516,0.0051727295,0.006465912,-0.003501892,0.016326904,0.010368347,0.033447266,-0.03353882,0.014022827,0.018737793,-0.029846191,0.0011577606,-0.007282257,0.05596924,-0.04309082,-0.015602112,0.023330688,-0.00592041,-0.029022217,0.029937744,-0.032348633,-0.0041389465,-0.019119263,0.013977051,-0.030548096,-0.023101807,0.007106781,-0.040527344,-0.011184692,0.009185791,0.052093506,0.014793396,-0.0060577393,0.0030994415,-0.025131226,0.009376526,-0.04547119,-0.008705139,-0.027114868,0.008171082,0.058258057,-0.022003174,0.013519287,0.010864258,0.015258789,0.020767212,0.013595581,0.000828743,0.057891846,-0.017471313,0.011817932,0.021911621,-0.013221741,-0.015129089,0.0059127808,0.04067993,0.010398865,-0.0058555603,-0.020935059,-0.03930664,0.0002374649,0.012214661,-0.03955078,-0.0435791,0.025527954,-0.009010315,0.023132324,-0.004878998,-0.015274048,0.012451172,-0.0058059692,-0.0012025833,-0.015777588,0.023773193,-0.0063056946,-0.0011892319,-0.024215698,0.027069092,0.0018873215,-0.010795593,0.0121154785,0.02053833,0.008285522,0.0077934265,-0.007621765,-0.018798828,0.025405884,-0.011619568,-0.0009965897,0.030258179,0.0049819946,0.003036499,0.019180298,0.046722412,-0.012466431,-0.018035889,0.0135650635,-0.016021729,-0.00025057793,0.039093018,-0.0037155151,-0.0078086853,-0.013092041,-0.034973145,-0.035949707,-0.00592041,-0.009414673,-0.023376465,0.044677734,-0.03591919,-0.014053345,0.01965332,-0.008735657,-0.024963379,-0.00010710955,-0.016189575,-0.0078125,-0.009254456,0.003686905,0.010101318,0.017318726,0.037872314,0.00061941147,0.014350891,-0.026535034,-0.026641846,0.017227173,-0.0036506653,0.02772522,0.020126343,0.012046814,-0.011299133,0.030548096,-0.0069274902,-0.004928589,-0.0060920715,0.03265381,0.05215454,-0.009651184,0.009819031,0.007408142,-0.022323608,-0.020233154,0.01537323,-0.0021781921,0.04034424,-0.021713257,0.04727173,-0.02444458,-0.025726318,-0.0013856888,0.00031876564,-0.005027771,-0.03375244,0.03189087,0.014221191,0.022644043,0.00062036514,0.015487671,-0.015975952,-0.008262634,0.019317627,0.02468872,-0.008140564,-0.005264282,0.023117065,0.047943115,0.006942749,-0.028289795,0.010047913,0.0395813,0.034118652,0.0006814003,0.039978027,0.05203247,0.0033569336,-0.017959595,-0.0030956268,-0.0044174194,0.0069389343,-0.0070381165,-0.014801025,-0.008903503,0.0045776367,-0.020309448,0.036315918,-0.007633209,-0.015716553,0.007396698,0.021026611,-0.016784668,-0.009422302,-0.006881714,-0.042144775,0.0030708313,0.006263733,0.045288086,0.0015907288,0.0042533875,-0.027893066,0.044769287,0.0026855469,0.016143799,0.02746582,-0.0107040405,-0.0003464222,-0.008415222,-0.00069379807,0.020935059,0.013755798,-0.0032176971,-0.015136719,0.024139404,0.01222229,0.0005874634,-0.031677246,-0.018035889,0.023376465,0.016479492,-0.057159424,0.0435791,-0.0071372986,0.012924194,0.00844574,-0.008636475,0.014205933,-0.0058937073,0.023162842,0.021713257,-0.009933472,-0.0002245903,-0.011253357,0.03366089,0.029937744,0.019348145,0.003452301,0.01448822,-0.011924744,0.016113281,-0.0016565323,-0.002216339,-0.009887695,0.03845215,3.093481e-05,0.007633209,-0.017486572,-0.018997192,0.036865234,0.062408447,0.003370285,-0.024673462,0.011566162,0.0074157715,-0.025878906,-0.017868042,-0.013397217,-0.008529663,0.007827759,0.05819702,0.017730713,-0.018554688,-0.013298035,-0.0044784546,-0.007648468,0.034851074,-0.025360107,-0.02822876,0.02671814,0.030410767,0.018234253,0.034362793,-0.009635925,-0.017807007,0.008735657,0.013336182,-0.0066604614,0.012863159,-0.039093018,0.0034713745,-0.0055999756,-0.0044937134,-0.0016222,0.008674622,0.019454956,0.010398865,0.0036201477,-0.04949951,0.0064964294,-0.021453857,0.000182271,0.02709961,0.0007801056,-0.006462097,-0.013061523,-0.0013017654,0.024505615,0.025726318,0.035217285,-0.00447464,-0.014678955,0.012809753,0.056152344,0.009262085,-0.0066490173,-0.008811951,-0.015472412,-0.014274597,-0.01725769,0.029464722,-0.01878357,-0.0070533752,0.012626648,0.022079468,-0.02142334,0.0016098022,-0.010307312,-0.018829346,0.017807007,-0.035736084,-0.02267456,0.010734558,-0.031402588,0.0060539246,0.0206604,-0.036224365,-0.032470703,0.008354187,-0.00049495697,0.03149414,0.031402588,0.012626648,-0.0040740967,-0.027175903,-0.021270752,0.0019741058,0.011383057,0.0032596588,0.011657715,-0.0045166016,0.01411438,0.012504578,-0.016860962,-0.005645752,-0.008293152,-0.0006284714,-0.012306213,0.019088745,0.020080566,-0.0043563843,-0.008369446,0.0035934448,-0.0015506744,-0.018310547,-0.004119873,0.042510986,0.011756897,-0.023117065,-0.0012216568,0.0038585663,-0.0013360977,-0.01626587,0.0020656586,-0.024597168,-0.032592773,0.0011177063,-0.015945435,-0.019485474,0.045715332,0.014762878,0.03579712,0.0028915405,0.004096985,-0.01940918,-0.033721924,0.024398804,-0.010597229,-0.025268555,0.006793976,0.0035629272,-0.009231567,-0.02520752,0.017532349,-0.06506348,-0.021057129,-0.024169922,0.0137786865,0.007385254,0.01222229,0.046966553,-0.0032844543,-0.038726807,0.004673004,-0.012939453,0.05203247,-0.002363205,-0.018630981,0.018188477,0.0206604,-0.007461548,0.004688263,-0.014595032,0.03527832,-0.032287598,-0.01826477,0.029846191,-0.025100708,0.012832642,-0.010528564,0.00095176697,0.02671814,0.033325195,-0.04333496,-0.011131287,0.040740967,0.0010490417,6.955862e-05,-3.9041042e-05,0.01751709,-0.042663574,-0.03741455,-0.011192322,-0.015022278,0.0064811707,0.025924683,0.00068712234,-0.015823364,0.00023889542,-0.008529663,-0.0025634766,0.0118255615,0.042053223,0.03060913,0.026153564,-0.02545166,-0.0011787415,-0.031433105,0.010505676,-0.008918762,0.02029419,-0.009140015,0.011749268,0.025756836,-0.013191223,-0.011299133,0.02041626,0.018203735,0.03265381,-0.011878967,-0.0076179504,-0.029586792,-1.4841557e-05,0.06402588,0.010864258,-0.026443481,-0.00605011,0.017440796,-0.0024280548,0.03427124,0.006679535,0.024353027,-0.02394104,-0.028579712,0.0018577576,-0.01777649,0.010284424,-0.0026187897,-0.031555176,-0.005126953,-0.015068054,0.010032654,-0.006515503,0.04949951,-0.016983032,-0.025131226,-0.02961731,-0.056732178,-0.00013315678,-0.00957489,0.028579712,-0.0011034012,-0.031188965,0.016174316,0.009994507,-0.026535034,0.029541016,-0.0011634827,-0.0024929047,0.003742218,-0.00605011,-0.0064201355,0.0030670166,0.0020942688,0.040283203,-0.012054443,-0.014602661,0.010345459,-0.018844604,-0.0059432983,0.00056934357,0.001824379,0.005683899,0.017822266,0.014213562,-0.013648987,0.04031372,0.00016820431,0.02508545,0.032104492,0.011886597,0.002714157,0.011260986,0.003479004,-0.02772522,-0.0054969788,-0.0005402565,0.018432617,-0.00422287,-0.025558472,0.019317627,0.022384644,0.017471313,-0.036834717,0.011810303,-0.018127441,0.008644104,0.014907837,0.00051641464,0.007118225,-0.016098022,-0.0234375,-0.02658081,-0.040527344,-0.011688232,-0.0066490173,-0.014434814,-0.023162842,0.026931763,0.0046653748,-0.011917114,0.02017212,-0.037139893,0.0026664734,0.015899658,0.013427734,0.047973633,0.01966858,-0.022003174,-0.006210327,0.014541626,0.04446411,-0.009277344,0.012954712,0.00187397,-0.01309967,-0.01007843,-0.006290436,0.008995056,-0.029418945,0.005203247,0.008796692,0.017242432,0.007701874,0.008430481,0.0073394775,-0.057800293,0.042510986,-0.008361816,0.019577026,0.0061416626,0.0042381287,0.020874023,0.018722534,-0.0055770874,-0.014045715,-0.0067481995,0.0043296814,0.021713257,-0.00970459,0.021148682,-0.027450562,0.028076172,0.028411865,-0.027130127,-0.00044965744,0.011711121,0.018997192,-0.001572609,-0.034118652,-0.029632568,0.025619507,-0.0068740845,-0.045806885,-0.02722168,-0.012275696,0.009529114,-0.0006580353,0.052001953,0.015159607,-0.007835388,0.01121521,0.042633057,-0.041503906,0.041107178,0.009353638,0.02960205,-0.007835388,0.010108948,-0.00021111965,-0.005619049]
\.


--
-- TOC entry 4390 (class 0 OID 21700)
-- Dependencies: 384
-- Data for Name: card_common_bnft_apply; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_common_bnft_apply (card_common_id, card_common_bnft_id, card_id) FROM stdin;
1	20261103_000001	5
\.


--
-- TOC entry 4388 (class 0 OID 21682)
-- Dependencies: 382
-- Data for Name: card_common_doc; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_common_doc (card_common_id, card_doc_id) FROM stdin;
1	20261102_000004
6	20261103_000009
7	20261103_000010
7	20261103_000011
9	20261103_000013
9	20261103_000014
11	20261103_000015
11	20261103_000016
13	20261103_000017
13	20261103_000018
15	20261103_000019
16	20261103_000020
17	20261103_000021
17	20261103_000022
\.


--
-- TOC entry 4378 (class 0 OID 20795)
-- Dependencies: 361
-- Data for Name: card_doc; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_doc (card_doc_id, doc_cd, doc_family_cd, doc_type_cd, doc_title, doc_source_url, doc_file_nm, doc_file_size, doc_sha256, doc_page_cnt, doc_review_no, doc_review_date, doc_release_date, doc_collect_date, doc_version_no, doc_status, doc_note, create_date, create_user_id, update_date, update_user_id) FROM stdin;
20261101_000002	HANA_15650_20260429	HANA_15650	PRODUCT_GUIDE	ONE PICK STYLE 하나 체크카드 상품설명서	https://m.hanacard.co.kr/leaflet/15/15650_20260429.pdf	hana_all/debit/체크_ONEPICKSTYLE하나체크카드_상품설명서(공식PDF,URL추정확인)_15650_20260429.pdf	360659	6ec9641c2e318ce9429a916f5d01c0468ccc3cffb238eb1162a43b280e25c6d2	2	준법심의 L-26-0542(2026.04.29) / VI 260429-71	2026-04-29	\N	2026-10-30 07:00:52+00	1	ACTIVE	URL 추정으로 찾은 문서. 상품 페이지 직접 링크 없음, 공식 출처 미확정	2026-11-01 01:13:59.122334+00	SYSTEM	2026-11-01 01:13:59.122334+00	SYSTEM
20261102_000003	HANA_14955_20260609	HANA_14955	PRODUCT_GUIDE	JADE Classic 상품설명서	https://m.hanacard.co.kr/leaflet/14/14955_20260609.pdf	hana_all/credit/신용_JADEClassic_상품설명서(공식PDF)_14955_20260609.pdf	510462	1b4dcf06fca042f276718e877f9502ffe6625557b9e454bb324dacf35a8cf949	6	여신금융협회 심의필 제 2026-C1a-10094호(2026.07.03) / 준법심의 L-26-2051(2026.06.09) / VI 260615-71	2026-06-09	\N	2026-10-30 06:49:45+00	1	ACTIVE	공식 원본 PDF	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000004	HANA_VS002_20260317	HANA_VS002	BRAND_SERVICE	공통_VISA브랜드서비스_VS002_20260317	https://m.hanacard.co.kr/leaflet/VS/VS002_20260317.pdf	hana_all/common/공통_VISA브랜드서비스_VS002_20260317.pdf	247107	cd7356d44802272d4101f07d2187e18b48c939d750231bf66ef7681ba6686fa0	2	\N	\N	\N	2026-10-30 06:49:45+00	1	ACTIVE	공식 원본 PDF / 공유 상품: JADE Classic, JADE Prime, CLUB Signature SKYPASS 카드, JADE Prime 골드클럽멤버스, SHINSEGAE by JADE HanaCard	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261103_000009	HANA_AE001_20260305	HANA_AE001	BRAND_SERVICE	공통_AMEX브랜드서비스_AE001_20260305	https://m.hanacard.co.kr/leaflet/AE/AE001_20260305.pdf	hana_all/common/공통_AMEX브랜드서비스_AE001_20260305.pdf	547620	a52eff8857df2d431bad22a4c0fad485a789fae66b229f748fb8059ffc41bce2	3	\N	\N	\N	2026-10-30 06:49:52+00	1	ACTIVE	공식 원본 PDF	2026-11-03 05:20:34.783526+00	SYSTEM	2026-11-03 05:20:34.783526+00	SYSTEM
20261103_000010	HANA_AP002_20260305	HANA_AP002	BRAND_SERVICE	공통_AMEX브랜드서비스_AP002_20260305	https://m.hanacard.co.kr/leaflet/AP/AP002_20260305.pdf	hana_all/common/공통_AMEX브랜드서비스_AP002_20260305.pdf	544317	4f671f504251335639f03c7a44d8162a657bfae70018b720c60cbfa7db0b205e	2	\N	\N	\N	2026-10-30 06:49:41+00	1	ACTIVE	공식 원본 PDF	2026-11-03 05:20:39.726129+00	SYSTEM	2026-11-03 05:20:39.726129+00	SYSTEM
20261103_000011	HANA_AP003_20260609	HANA_AP003	BRAND_SERVICE	공통_AMEX브랜드서비스_AP003_20260609	https://m.hanacard.co.kr/leaflet/AP/AP003_20260609.pdf	hana_all/common/공통_AMEX브랜드서비스_AP003_20260609.pdf	281254	b3978c0b89ea14d606a4cc0da9e36f9f96a9da6c4c0206219a108d9b4d1da7cf	2	여신금융협회 심의필 제 2026-C1a-05144호(2026.04.13) / 준법심의 L-26-0405(2026.03.03) / VI 260818-31	2026-03-03	\N	2026-10-30 06:49:47+00	1	ACTIVE	공식 원본 PDF	2026-11-03 05:20:44.573836+00	SYSTEM	2026-11-03 05:20:44.573836+00	SYSTEM
20261103_000012	HANA_JP002_20260326	HANA_JP002	BRAND_SERVICE	공통_JCB브랜드서비스_JP002_20260326	https://m.hanacard.co.kr/leaflet/JP/JP002_20260326.pdf	hana_all/common/공통_JCB브랜드서비스_JP002_20260326.pdf	217296	fc623e6f290008b48c13b3e6ad83dd4dd525e910b159ca039c5aa38f90dd26dd	1	\N	\N	\N	2026-10-30 06:49:39+00	1	ACTIVE	공식 원본 PDF	2026-11-03 05:20:49.506204+00	SYSTEM	2026-11-03 05:20:49.506204+00	SYSTEM
20261103_000013	HANA_MP001_20260209	HANA_MP001	BRAND_SERVICE	공통_Mastercard브랜드서비스_MP001_20260209	https://m.hanacard.co.kr/leaflet/MP/MP001_20260209.pdf	hana_all/common/공통_Mastercard브랜드서비스_MP001_20260209.pdf	488407	52c2d271680ffd97045385ca0536198e4b6a0ae8a047a38b32f2a5c742ad14d1	2	\N	\N	\N	2026-10-30 06:49:40+00	1	ACTIVE	공식 원본 PDF / 공유 상품: CLUB SK(클럽 SK)카드, CLUB Primus Skypass 카드, 하나 골드클럽멤버스Ⅱ 카드	2026-11-03 05:20:52.903041+00	SYSTEM	2026-11-03 05:20:52.903041+00	SYSTEM
20261103_000014	HANA_MP004_20260209	HANA_MP004	BRAND_SERVICE	공통_Mastercard브랜드서비스_MP004_20260209	https://m.hanacard.co.kr/leaflet/MP/MP004_20260209.pdf	hana_all/common/공통_Mastercard브랜드서비스_MP004_20260209.pdf	486961	50912a96d6b7115b3fb876e0bebc5ec1a691ccdff48f1c312ded627bc1287995	2	\N	\N	\N	2026-10-30 06:49:54+00	1	ACTIVE	공식 원본 PDF	2026-11-03 05:20:57.765029+00	SYSTEM	2026-11-03 05:20:57.765029+00	SYSTEM
20261103_000015	HANA_MW002_20260209	HANA_MW002	BRAND_SERVICE	공통_Mastercard브랜드서비스_MW002_20260209	https://m.hanacard.co.kr/leaflet/MW/MW002_20260209.pdf	hana_all/common/공통_Mastercard브랜드서비스_MW002_20260209.pdf	483244	f8eb78e1e6f0d03b4b3eb26c8840b690716aaefa48b14b7b1b6f2a8ffaaf97c1	2	\N	\N	\N	2026-10-30 06:49:56+00	1	ACTIVE	공식 원본 PDF / 공유 상품: Club Leaders 5 카드, Club Leaders 8 카드, Club Leaders 10 카드, Club Leaders 15 카드	2026-11-03 05:21:03.19387+00	SYSTEM	2026-11-03 05:21:03.19387+00	SYSTEM
20261103_000016	HANA_MW003_20260209	HANA_MW003	BRAND_SERVICE	공통_Mastercard브랜드서비스_MW003_20260209	https://m.hanacard.co.kr/leaflet/MW/MW003_20260209.pdf	hana_all/common/공통_Mastercard브랜드서비스_MW003_20260209.pdf	485625	073cbb05588c0d9cfcc8354e20143798b9a43233ecf0fe9a5edf7dbcb771a93c	2	\N	\N	\N	2026-10-30 06:49:46+00	1	ACTIVE	공식 원본 PDF	2026-11-03 05:21:09.536855+00	SYSTEM	2026-11-03 05:21:09.536855+00	SYSTEM
20261103_000017	HANA_UD001_20260324	HANA_UD001	BRAND_SERVICE	공통_UnionPay브랜드서비스_UD001_20260324	https://m.hanacard.co.kr/leaflet/UD/UD001_20260324.pdf	hana_all/common/공통_UnionPay브랜드서비스_UD001_20260324.pdf	574820	1b1d36b8e55fdacc7fcb514598c945a23f65824600a827c9f1868032eec355f5	2	여신금융협회 심의필 제 2026-C1a-05041호 (2026.04.10) / 준법심의 L-26-0516(2026.03.24)/ VI 260421-31	2026-03-24	\N	2026-10-30 06:50:04+00	1	ACTIVE	공식 원본 PDF	2026-11-03 05:21:14.154311+00	SYSTEM	2026-11-03 05:21:14.154311+00	SYSTEM
20261103_000018	HANA_UD002_20260618	HANA_UD002	BRAND_SERVICE	공통_UnionPay브랜드서비스_UD002_20260618	https://m.hanacard.co.kr/leaflet/UD/UD002_20260618.pdf	hana_all/common/공통_UnionPay브랜드서비스_UD002_20260618.pdf	376310	17279bc573574f3f3105d4b101fc3dbfde83b14563c21fb9380e7be51fb047f1	2	여신금융협회 심의필 제 2026-C1a-05041호 (2026.04.10) / 준법심의 L-26-0516(2026.03.24)/ VI 260421-31	2026-03-24	\N	2026-10-30 06:49:48+00	1	ACTIVE	공식 원본 PDF	2026-11-03 05:21:19.166396+00	SYSTEM	2026-11-03 05:21:19.166396+00	SYSTEM
20261103_000019	HANA_UP001_20260324	HANA_UP001	BRAND_SERVICE	공통_UnionPay브랜드서비스_UP001_20260324	https://m.hanacard.co.kr/leaflet/UP/UP001_20260324.pdf	hana_all/common/공통_UnionPay브랜드서비스_UP001_20260324.pdf	251202	4371627fa481f07691439a570be790cbcdee0d6c74b57f7029b9837ab5105744	1	여신금융협회 심의필 제 2026-C1a-05040호 (2026.04.10) / 준법심의 L-26-0517(2026.03.24)/ VI 260421-32	2026-03-24	\N	2026-10-30 06:49:27+00	1	ACTIVE	공식 원본 PDF / 공유 상품: Mile1 하나카드, 길한통 체크카드	2026-11-03 05:21:23.814442+00	SYSTEM	2026-11-03 05:21:23.814442+00	SYSTEM
20261103_000020	HANA_VI001_20260317	HANA_VI001	BRAND_SERVICE	공통_VISA브랜드서비스_VI001_20260317	https://m.hanacard.co.kr/leaflet/VI/VI001_20260317.pdf	hana_all/common/공통_VISA브랜드서비스_VI001_20260317.pdf	428101	aaf942cdf7bb0b0c849a866eb2305eb1db808f534f28d2253e8be8c1092edc9d	2	\N	\N	\N	2026-10-30 06:49:50+00	1	ACTIVE	공식 원본 PDF / 공유 상품: JADE First, JADE First Centum	2026-11-03 05:21:28.533172+00	SYSTEM	2026-11-03 05:21:28.533172+00	SYSTEM
20261103_000021	HANA_VP001_20230727	HANA_VP001	BRAND_SERVICE	공통_VISA브랜드서비스_VP001_20230727	https://m.hanacard.co.kr/leaflet/VP/VP001_20230727.pdf	hana_all/common/공통_VISA브랜드서비스_VP001_20230727.pdf	248201	4ce0e34b4ae60d2171cb4f43c46903b8560b77ba6f9a0044bc61d84d53d0ddbd	2	\N	\N	\N	2026-10-30 06:49:29+00	1	ACTIVE	공식 원본 PDF	2026-11-03 05:21:32.951882+00	SYSTEM	2026-11-03 05:21:32.951882+00	SYSTEM
20261103_000022	HANA_VP001_20260317	HANA_VP001	BRAND_SERVICE	공통_VISA브랜드서비스_VP001_20260317	https://m.hanacard.co.kr/leaflet/VP/VP001_20260317.pdf	hana_all/common/공통_VISA브랜드서비스_VP001_20260317.pdf	239651	03c6c41b002c56c42938cad0ccc84ff6868f9965be2c1b4fa655f5775d648618	2	\N	\N	\N	2026-10-30 06:49:40+00	2	ACTIVE	공식 원본 PDF / 공유 상품: CLUB SK(클럽 SK)카드, CLUB Primus Skypass 카드	2026-11-03 05:21:37.985564+00	SYSTEM	2026-11-03 05:21:37.985564+00	SYSTEM
\.


--
-- TOC entry 4380 (class 0 OID 20826)
-- Dependencies: 363
-- Data for Name: card_doc_chunk; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_doc_chunk (card_doc_id, page_no, card_doc_chunk_id, chunk_seq, chunk_section_nm, chunk_type_cd, chunk_start_pos, chunk_end_pos, chunk_raw_txt, chunk_clean_txt, chunk_status, chunk_split_rule_ver, chunk_clean_rule_ver, create_date, create_user_id, update_date, update_user_id) FROM stdin;
20261101_000002	1	20261101_000012	1	\N	BODY	1	2482	[연회비] 없음 \n[발급브랜드] 국내전용, 국내외겸용(Mastercard)\n[발급대상] 7세부터 발급 가능 \n[후불교통] 선택가능(12세부터 발급 가능)\n* ONE PICK STYLE 하나 체크카드의 결제계좌는 하나은행 계좌에 한하여 이용 가능합니다. \n서비스 제공 안내    \n \n서비스 제외 대상\n- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외\n- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외\n실적 산정 기준\n- 지난달 1일부터 말일(승인 시점 기준)까지 국내외 일시불 이용금액 10만원/20만원 이상 시\n ONE MORE 서비스 제공\n실적 제외 대상\n- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외\n실적과 관계없이 서비스 제공\n- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공\n * ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공\n서비스 제공 방법\n- 캐시백 제공 시점 : 매출일자로부터 5영업일 이내 결제계좌로 입금 예정\n- 매출 접수된 국내 일시불 이용금액에 따라 캐시백 혜택을 제공하며, 매출 취소 시 취소가 접수된\n 월에서 실적 및 캐시백 제공 금액 차감 반영\n- 후불교통요금 등 무승인 거래(카드사의 승인없이 이용금액이 카드사에 접수됨)의 경우 매출이 \n 접수된 월의 이용금액에 반영\n- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공\n- 가맹점 정보가 해당 업체가 아닌 결제대행업체(PG) 또는 간편결제 전용 가맹점으로 확인되는 \n 경우 ‘결제대행업체’ 또는 ‘간편결제’ 가맹점으로 분류되어 각 서비스 영역에 따른 혜택이 제공됨\n 자세한 사항은 하나카드 고객센터(1800-1111)에 문의하시기 바람\n ※ 예시) 편의점에서 네이버페이로 결제 시 가맹점명이 ‘네이버페이’인 경우 \n               “편의점” 가맹점이 아닌 ‘간편결제’ 가맹점으로 분류\n서비스 영역\nONE PICK\n(편의점, \n 카페)\nSTYLE\n(쇼핑\n서점/문구,\n패션)\nCU, GS25, \n세븐일레븐\n다이소, 올리브영\n교보문고, 영풍문고,\n알라딘, yes24,\n아트박스\n무신사, 에이블리\n메가MGC커피, \n이디야커피, \n컴포즈커피\n결제 건당\n3천원 이상 시 \n100원\n/\n결제 건당\n1만원 이상 시 \n500원\n일 1회\n/ 월 10회\n월 5천원\n대상 가맹점\n캐시백 조건\n캐시백 한도\n횟수 한도\n금액 한도\n(지난달 실적 조건 없는 서비스)\nONE PICK\nSTYLE\n후불교통 기능 이용 안내\n* 발급대상 : 12세 이상 손님 (단, 연체 등 특이 정보가 있는 경우 발급이 제한될 수 있음)\n* 이용 시 유의사항 (후불교통기능 선택 시에만 해당) \n - 후불교통 이용금액은 손님 계좌에서 즉시 출금되지 않으며, 손님이 신용공여기간동안 이용한\n    금액이 결제일에 일시 출금됨\n - 후불교통/하이브리드 서비스 동시 이용 시에는 하이브리드 서비스(소액신용거래)에서 \n    결제 및 청구됨\n하이브리드 서비스 이용 안내\n하이브리드 서비스에 대한 상세한 내용은 하이브리드 서비스 신청 후 발송되는\n“하나카드 체크카드 하이브리드 서비스 약관”을 통해 확인 가능함\n미성년자 체크카드 이용 안내\n* 7~13세 미성년자 체크카드 발급 시 법정대리인 동의가 필수이며, \n 1일 3만원/1개월 30만원의 이용 한도가 적용됨\n (14세가 경과하면 고객센터에 요청하여 상향 가능)\n* 후불교통 체크카드는 12~17세 이상 손님은 법정대리인 동의 하에 발급 받을 수 있으며,\n 월 이용한도 10만원/전체 카드사 기준 1인 1매만 소지 가능\n (18세 이상의 미성년자는 법정대리인 동의 불필요)\n일 1회\n/ 월 30회\n월 5천원\n(지난달 실적 10만원/20만원 이상 시 받는 서비스)\n서비스 영역\n대상 가맹점\n서비스 방법\n서비스 한도\n지난달 실적\n대중교통\n버스, 지하철\n월 1천원\n5%\n캐시백\n10만원\n놀이공원\n에버랜드, 롯데월드\n월 1회 \n/ 연 2회\n50% \n현장할인\n(1인 1매)\n20만원\n최초 발급 월에는\n서비스 미제공\nONE MORE\n하나 체크카드\n하나 체크카드\nONE PICK\nSTYLE\n	\N	RAW	PAGE_V1	\N	2026-11-01 01:13:59.122334+00	SYSTEM	2026-11-01 01:13:59.122334+00	SYSTEM
20261101_000002	2	20261101_000013	2	\N	BODY	1	3181	부가서비스 유지 및 변경 안내    \n \n· 카드이용 시 제공되는 포인트 및 할인혜택 등의 부가서비스는 카드 신규 출시(2026년 3월 30일) \n 이후 3년 이상 축소·폐지 없이 유지됩니다.\n· 다만, 다음과 같은 사유가 발생한 경우 카드사는 부가서비스를 변경할 수 있습니다.\n ①: 카드사의 휴업·파산·경영상의 위기 등에 따른 불가피한 경우\n ①의2: 제휴업체의 휴업·파산·경영상의 위기로 인해 불가피하게 부가서비스를 축소·변경하는\n  \n \n경우로서 다른 제휴업체를 통해 같은 종류의 유사한 부가서비스 제공이 불가한 경우\n ②: 제휴업체가 카드사의 의사에 반하여 해당 부가서비스를 축소하거나 변경 시, 당초 부가서비스에 \n  \n상응하는 다른 부가서비스를 제공하는 경우 \n ③: 부가서비스를 3년 이상 제공한 상태에서 해당 부가서비스로 인해 상품의 수익성이 현저히\n  \n낮아진 경우 \n· 카드사가 부가서비스를 변경하는 경우 변경사유, 변경내용 등을 다음 각호에서 정하는 기간에 \n 따라 서면교부, 우편 또는 전자우편, 전화 또는 팩스, 휴대폰 메시지 또는 이에 준하는 전자적 \n 의사표시 중 서로 다른 2가지 이상의 방법 으로 고지하여 드립니다. 다만, 제2호의 경우 부가 \n 서비스 변경일 6개월 이전부터는 서면교부, 우편 또는 전자 우편, 전화 또는 팩스, 휴대폰 메시지 \n 또는 이에 준하는 전자적 의사표시 중 서로 다른 2가지 이상의 방법으로 매월 고지하여 드립니다.\n 1. ①, ①의2, ②: 사유발생 즉시\n   2. ③: 부가서비스 변경일 6개월 이전\n· 상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 \n 하락할 수 있습니다. \n· 개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다. \n· 일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 \n 있습니다. \n· 연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n  ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시: 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시: 거래 발생 시점의 동일한 할부 계약기간의 \n  유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 \n  가계자금대출금리* 중 높은  금리 적용\n  * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 \n     가중평균대출금리(신규대출 기준)\n         1800-1111\n하나카드 고객센터\n준법심의 L-26-0542(2026.04.29) / VI 260429-71\n결제이용대금 결제 안내    \n \n· 결제 계좌 개설기관의 영업 마감시간(16시) 이후 결제 계좌에 입금된 금액에 대해서는 결제 계좌 \n 개설 기관의 사정에 따라 당일 출금되지 못하여 연체로 처리 될 수 있으므로 유의하시기 바랍니다. \n 자동납부 업무 마감시간 이후에는 하나카드 홈페이지/모바일 등에서 즉시결제 또는 가상계좌입금 \n (송금납부)을 통해 당일 결제가 가능합니다.\n ※ 세부내용은 하나카드 홈페이지 [고객센터-카드이용안내-결제안내] 및 모바일 앱 [고객센터 탭] 참고\n•결제은행에 따라 안정적인 서비스 제공을 위한 전산 시스템 점검 시에는 23:00~06:00 중 체크카드 \n 이용이 일시적으로 제한될 수 있습니다.\n해외 결제 및 기타 안내    \n \n① 결제은행이 하나은행인 경우, 해외 이용 시(해외사이트 거래 포함) 미화(USD)기준 거래 금액에 \n \n카드승인시점의 하나은행이 고시한 전신환매도율을 적용한 금액으로 카드 승인일에 회원의 계좌 \n \n잔액에서 지급정지 되고, 이후 매출표가 접수되면 지급정지 금액 계산시와 동일한 방법으로 산정된\n \n미화(USD)금액에 접수일의 하나은행 최초고시 전신환 매도율을 적용한 원화금액으로 회원의 \n \n계좌에서 출금됩니다. 단, 1회 승인금액 100만원 이상의 거래(단, T&E업종 제외), 또는 카드사가 \n \n정한 특정브랜드(BC 등) 및 상품의 카드이용대금은 미화(USD) 기준 거래 금액에 카드 승인시점의\n \n하나은행이 고시한 전신환매도율을 적용한 원화금액으로 회원의 계좌잔액에서 즉시 인출됩니다.\n \n* T&E 업종: Travel and Entertainment 업종, 여행과 여가 관련 업종(항공, 호텔, 숙박, 렌터카 등)\n② ①의 인출금액에는 국제브랜드사가 부과하는 국제브랜드수수료(Mastercard 1.0%)와 \n \n하나카드가 부과하는 해외서비스수수료(US$0.5)가 포함됩니다.\n· 해외 가맹점에서 원화로 결제할 경우(DCC) 추가수수료가 발생하므로 \n 현지 통화 또는 미화로 거래하시기 바랍니다.\n· 해외원화결제서비스(DCC) 사전차단 서비스 이용 방법: 콜센터, 홈페이지/모바일App\n (마이페이지/라이프-이용안심서비스-해외원화결제(DCC) 차단서비스)\n· 일부 해외 거래 시 IC칩 비밀번호(PIN)를 요구하는 경우가 있으므로 출국 전 반드시 \n IC칩 비밀번호(PIN) 등록여부를 확인하시기 바랍니다.\n* 해외 이용 시 청구금액 산출 방법\n* 해외 이용 시 청구금액 \n   = (거래미화금액 × 전신환매도율¹) + 국제브랜드수수료² + 해외서비스수수료³\n \n1. 전신환매도율 : ① 접수일의 하나은행 최초고시 전신환매도율\n \n                              ② 즉시출금은 승인시점의 하나은행 전신환매도율\n \n2. 국제브랜드수수료 = (거래미화금액 × 국제브랜드이용수수료율(Mastercard 1.0%)) \n                                            × 전신환매도율 \n \n3. 해외서비스수수료 = (거래건수 × US$0.5) × 전신환매도율\n* 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 \n 영향을 미칠 수 있습니다.\n* 계약체결 전 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n* 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 \n 제한 될 수 있습니다.\n* 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 \n 상환하여야 합니다.\n* 소비자는 금융소비자보호법에 따라 해당 상품 또는 서비스에 대하여 \n 설명을 받을 권리가 있습니다.\n* 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다. \n* 자세한 내용은 하나카드 홈페이지(www.hanacard.co.kr)를 참고하시거나\n  고객센터로 문의 바랍니다.\n	\N	RAW	PAGE_V1	\N	2026-11-01 01:13:59.122334+00	SYSTEM	2026-11-01 01:13:59.122334+00	SYSTEM
20261102_000003	1	20261102_000014	1	\N	BODY	1	65	Classic\nClassic\nPremium is Already Brilliant,\nJADE\n제이드 클래식 상품설명서\n	\N	RAW	PAGE_V1	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000003	2	20261102_000015	2	\N	BODY	1	1226	Premium Voucher \nAirport\nReward\n[공통] 서비스 실적 조건 \n가족카드 이용 안내\n연회비\nPREMIUM VOUCHER \n바우처 5가지 중 1가지를 선택하여 이용 (연 1회) \nHOTEL\n호텔 다이닝 10만원 현장 할인\nSHOPPING\n신세계 상품권 10만원 모바일 교환권\nAUTO\nSK 모바일 주유권 10만원 \nFOOD & BEVERAGE\n배달의 민족 모바일 상품권 10만원\nFINANCE \n9만 하나머니   \n서비스 제공 기간\n서비스 실적 조건\n이용 방법\n\n유의 사항\t\n1\n1차년도 : 카드 발급월 포함 12개월\n2차년도 이후 : 전년도 바우처 제공 기간 종료 후 12개월 \n1차년도 : 카드 발급 후 50만원 이상 이용 시\n2차년도 이후 : 바우처 제공 기간 직전 1년간 600만원 이상 이용 시 \n⦁\t HOTEL(호텔 다이닝 10만원 할인) 현장 할인바우처는 제휴 호텔 \n\t 다이닝 가맹점에서 본인 회원 명의의 ‘JADE Classic’ 카드 제시 후 \n\t 10만원 이상 결제 시, 10만원 현장할인 적용\n\t ※\t제휴 호텔 다이닝 상세 이용 방법 및 사용처, 이용가능 여부는 \n\t \t 서비스 이용 전 하나카드 홈페이지 공지사항(www.hanacard.co.kr)\n\t \t 을 반드시 확인 후 이용\n⦁\t SHOPPING(신세계 상품권 10만원 모바일 교환권) 바우처는\n\t 전국 이마트 매장에서 신세계 상품권으로 교환 후 신세계 상품권 \n\t 사용처에서 이용 가능(이마트 매장에서만 교환 가능)\n⦁\t AUTO(SK 모바일 주유권 10만원) 바우처는 SK주유소 및 충전소에서\n\t 주유/충전 금액 5만원 이상 이용 시, 1매 이용 가능 (5만원권×2매 제공)\n\t ※ 주유 1회에 2매 동시 사용 불가하며 주유 앱을 통해 결제하는 경우 \n\t \t 서비스 제공 불가\n⦁\t FOOD & BEVERAGE(배달의 민족 모바일 상품권 10만원) 바우처는\n\t 배달의 민족 앱에서 등록 후 사용 가능하며, 배달 음식 및 배달팁에 대한\n\t 결제 수단으로 잔액 내 사용 가능\n⦁\t FINANCE 바우처는 신청일 기준 익월 10 영업일 이내 적립\n⦁\t 카드 발급 본인 회원에 한하여 제공됩니다.(가족카드 회원 제공 불가)\n⦁\t 제공기간을 경과한 미사용바우처는 자동 소멸되며 \n\t 다음해로 이월되지 않습니다.(FINANCE 바우처 제외)\n⦁\t 바우처 선택 및 변경은 하나카드 고객센터에서 가능합니다.\n⦁\t 바우처 변경은 신청 당일에만 가능하며, 신청 및 이용한 바우처는\n\t 취소할 수 없습니다.\n	\N	RAW	PAGE_V1	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000003	3	20261102_000016	3	\N	BODY	1	1897	서비스 제공 기간\n서비스 실적 조건\n이용 방법\n유의 사항\n1차년도 : 카드 발급월 포함 12개월\n2차년도 이후 : 전년도 서비스 제공 기간 종료 후 12개월 \n1차년도 : 지난달 1일부터 말일까지 50만원 이상 이용 시\n2차년도 이후 : 서비스 제공 기간 직전 1년간 600만원 이상 이용 시\n⦁\t 최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 \n\t 이용금액 50만원 미만 시에도 서비스 제공\n⦁\t THE LOUNGE 앱 설치 및 ‘JADE Classic’카드를 등록 후\n\t 라운지 이용권 다운로드\n⦁\t 제휴 라운지에 THE LOUNGE 이용권과 함께 \n\t 여권 및 항공 탑승권 제시 후 이용\n⦁\t 본인카드 회원과 라운지 입장 동반인/가족카드 회원 이용 횟수가 \n\t 합산되어 통합 연 3회, 일 3회 서비스 제공 됩니다.\n⦁\t 카드 해지 이후 다시 신규로 발급하는 경우에도 해지된 카드로 \n\t 이용한 횟수와 합산되어 통합 연 3회, 일 3회 한도로 제공됩니다.\n⦁\t 항공권 탑승자 이름, 여권 및 THE LOUNGE 앱에 등록된 \n\t 영문명이 동일해야 이용 가능합니다.\n⦁\t THE LOUNGE 앱 아이디 공유 및 라운지 이용권 양도는 \n\t 불가능합니다.\n⦁\t 다운로드(발급)받은 라운지 이용권은 ‘마이페이지 이용권 보관함’에\n\t 자동 저장되어 발급 후 24시간까지 유효하고 미사용시 자동 취소되어\n\t 이용 가능 횟수는 자동 복원됩니다.\n⦁\t 라운지 입장시 동반인 현장 결제 및 기타 사항은 각 라운지 규정을\n\t 준수합니다\n⦁\t 이용 가능 라운지 및 사용방법 등 서비스 관련 상세 내용은\n\t THE LOUNGE 홈페이지 및 고객센터에서 확인 가능합니다.\n\t ※ THE LOUNGE 홈페이지 : www.theloungemembers.com\n\t ※ 고객센터 : (국내) 1811-7437, (해외) +82-2-2664-7436\n전세계 공항 라운지 무료 이용\n(본인/가족/동반자 통합 연 3회, 일 3회)\n* 국내외겸용카드로 발급 시 서비스 제공(국내전용카드 보유 회원 제외)\nAIRPORT\nREWARD\n기본 적립\n국내외 가맹점 1% 하나머니 적립 제공\n(지난달 실적 조건 없음, 적립 한도 제한 없음)\n특별 적립\n영역별 1.5%~1.2% 하나머니 적립 제공\n(지난달 실적 50만원 이상, 월 통합 적립 한도 \n10만 하나머니)\n* \t해외결제 시 수수료가 발생할 수 있으니, [해외결제 및 기타 안내] 참조\n* \t항공/면세 : 공식 홈페이지(온라인/모바일앱) 및 오프라인 매장을 통한\n\t 결제 시에만 서비스 제공, 여행사, 구매대행사이트, 온라인쇼핑몰\n\t (오픈마켓, 소셜 등)을 통한 결제건은 서비스 제외됨\n*\t 여행/온라인쇼핑몰: 공식 홈페이지(온라인/모바일앱)를 통한 결제 시에만\n\t 서비스 제공되며, 몰 이동을 통해 다른 온라인 쇼핑몰로 이동하여\n\t 결제하는 경우는 서비스 제외됨\n\t ※ 여행 - 하나투어 가맹점은 오프라인 결제 시에도 서비스 제공됨\n*\t 백화점/아울렛/마트/주유 : 오프라인 결제건에 한하여 서비스 제공\n\t ※ 백화점/아울렛/마트의 상설·임대 매장은 서비스 제외됨\n\t ※ 마트 - 롯데마트맥스(창고형 할인매장)는 서비스 제외됨\n*\t 특별 적립과 기본 적립은 중복 제공되지 않음\n영역\n적립 대상 가맹점\n적립률적립 한도\n해외\n해외 가맹점\n1.5%\n월 통합\n10만\n하나머니\n항공\n대한항공, 아시아나 항공,\n진에어, 제주항공\n면세\n신라면세점, 롯데면세점,\n신세계면세점\n여행\n하나투어, 아고다,\n익스피디아, 호텔스닷컴\n쇼핑\n온라인\n쇼핑몰\n쿠팡, 컬리, SSG.COM, \n롯데ON, 더현대하이\n1.2%\n백화점롯데백화점, 신세계백화점, \n현대백화점, 더 현대 \n아울렛\n신세계사이먼, \n현대프리미엄, \n롯데프리미엄\n마트\n이마트, \n트레이더스 홀세일 클럽, \n홈플러스, 롯데마트\n주유\nLPG충전\n포함\nSK에너지, GS칼텍스, S-Oil, \nHD현대오일뱅크, 알뜰주유소\n2\n3\n	\N	RAW	PAGE_V1	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000003	4	20261102_000017	4	\N	BODY	1	1849	디지털 \n컨텐츠\n50% 적립\n디지털 컨텐츠 자동납부 시, \n50% 하나머니 적립 제공\n(지난달 실적 50만원 이상, 월 적립 한도 1만 하나머니)\n* \t자동납부 결제 건만 서비스 제공되며, 포인트, 캐시, 머니충전, \n\t 컨텐츠 개별 결제, 간편결제 및 앱스토어를 통한 결제건(인앱결제)은\n\t 서비스 제외됨\n영역\n적립 대상 가맹점\n적립률\n적립 한도\n디지털\n컨텐츠\n넷플릭스, 디즈니플러스,\n유튜브 프리미엄, Wavve, 티빙, \n멜론, 지니, FLO, 스포티파이\n50%\n1만\n하나머니\n커피\n50% 적립\n커피 이용금액 50% 하나머니 적립 제공\n(지난달 실적 50만원 이상, 월 적립 한도 5천 하나머니)\n*\t 스타벅스 오프라인 결제, 공식앱 또는 공식 홈페이지를 통한 주문 및 \n\t 결제에 한하여 서비스가 제공되며, 별개의 배달앱 혹은 식당 예약앱을 \n\t 통한 결제는 서비스 제외됨 \n*\t 대형시설물(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소, 공항, 호텔, \n\t 리조트, 역사, 마트) 입점 점포 및 임대 매장은 서비스 제외됨\n영역\n적립 대상 가맹점\n적립률\n적립 한도\n커피\n스타벅스\n50%\n5천\n하나머니\n택시\n50% 적립\n택시 이용금액 50% 하나머니 적립 제공\n(지난달 실적 50만원 이상, 월 적립 한도 5천 하나머니)\n* \t카카오T와 UT의 경우 공식 앱 또는 홈페이지를 통한 택시 결제건에\n\t 한하여 서비스가 제공되며, 대리운전·퀵 서비스·주차·기차 등\n\t 택시 이외의 결제건은 서비스가 제외됨\n영역\n적립 대상 가맹점\n적립률\n적립 한도\n택시\n택시업종, 카카오T, UT\n50%\n5천\n하나머니\n서비스 제공 기준\n⦁\t 모든 적립 서비스는 하나카드에 등록된 가맹점 및 가맹점 업종\n\t 기준에 따라 제공\n⦁\t 후불교통요금 등 무승인거래(카드사의 승인없이 이용금액이 카드사에\n\t 접수됨)의 경우 매출이 접수된 월의 이용금액에 반영\n⦁\t 매출 접수된 국내외 일시불/할부 이용금액에 따라 적립 혜택을 제공하며, \n\t 매출취소 시 취소가 접수된 월에 적립된 금액을 차감 반영\n⦁\t 할부 이용 전체 금액을 할부 이용한 달의 이용금액으로 반영\n⦁\t 해외 매출은 최종 원화 청구금액에 대하여 적립 제공\n⦁\t 적립 영역이 중복 되는 경우 적립금액이 큰 서비스가 우선 적용\n\t (매출 건당 하나의 서비스만 적용)\n⦁\t 특별적립, 디지털컨텐츠 50% 적립, 커피 50% 적립, 택시 50% 적립의\n\t 월 적립 한도를 모두 소진 후, 발생하는 추가 매출은 기본적립 제공\n서비스 제외 대상\n⦁\t 국세, 지방세, 수도/전기요금, 그외 공과금(우편요금, 과태료, 범칙금, \n\t 벌금, 국가/공공기관/공공단체가 부과하는 부담금), 도시가스 요금, \n\t 아파트관리비, 국민연금/고용보험료/산재보험료/건강보험료 납부 금액, \n\t 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 \n\t 기프트카드 구매, 선불카드 및 선불전자지급수단(하나머니 등) 충전 금액, \n\t 부동산임대료, 무이자 할부 이용금액\n적립 기준 \n⦁\t 적립기준: 하나머니(1하나머니=1원)\n⦁\t 하나머니 적립일 : 매출 접수된 다음날 하나머니가 적립됨\n⦁\t 소수점 이하 금액은 반올림됨\n※\t하나머니란?\n\t 하나카드의 하나머니 가맹점, 상품권 교환, 공익기부 등 \n\t 다양한 사용처에서 사용하시거나 연회비, 카드대금 등을 납부하실 때\n\t 사용하실 수 있습니다. (하나카드 홈페이지 ≦ ‘포인트’ 메뉴 참고)\n서비스 실적 조건\n⦁\t 기본적립 : 서비스 실적 조건 없음 \n⦁\t 특별적립 / 디지털컨텐츠 50% 적립 / 커피 50% 적립 / 택시 50% 적립\n\t : 지난달 1일부터 말일까지 50만원 이상 이용 시 서비스 제공\n⦁\t 최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 이용금액 \n\t 50만원 미만 시에도 서비스 제공\n4\n5\nREWARD\n	\N	RAW	PAGE_V1	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000003	5	20261102_000018	5	\N	BODY	1	2350	[공통] 서비스 실적 조건 \n가족카드 이용 안내\n실적 산정 기준\n⦁\t 국내외 일시불, 할부 이용금액 기준으로 산정됩니다.\n⦁\t 하나카드에 등록된 가맹점 및 가맹점 업종으로 기준으로 산정\n실적 제외 대상\n⦁\t 국세, 지방세, 수도/전기요금, 그외 공과금(우편요금, 과태료, 범칙금, \n\t 벌금, 국가/공공기관/공공단체가 부과하는 부담금), 도시가스 요금, \n\t 아파트관리비, 국민연금/고용보험료/산재보험료/건강보험료 납부 금액, \n\t 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 \n\t 기프트카드 구매, 선불카드 및 선불전자지급수단(하나머니 등) 충전 금액, \n\t 부동산임대료\n브랜드 서비스\n⦁\t 이 상품은 선택하신 브랜드에 따라 국제 브랜드 서비스가 제공됩니다.\n⦁\t 해당 국제 브랜드 서비스는 별도 안내장 및 하나카드 홈페이지\n\t (www.hanacard.co.kr)를 참조해 주시기 바랍니다.       \n\t\n- Visa : Visa Signature 02 유형\n\t - Mastercard : Mastercard World 03 유형\n\t - Amex : Amex Platinum 03 유형\n\t - UPI : UPI Diamond 02 유형\n⦁\t 국제 브랜드 서비스의 세부 내용 및 유의사항은 국제 브랜드 홈페이지를    \n\t 통해 확인하시기 바랍니다.  \n\t\n- Visa : www.visakorea.com\n\t - Mastercard : www.mastercard.co.kr\n\t - Amex : www.americanexpress.com/ko-kr/network\n\t - UPI : www.unionpaypremium.co.kr\n연회비 청구 및 \n반환 기준\n⦁\t 연회비 청구기준 : 카드별(본인/가족) 카드 발급일(발급 첫해에는 \n\t 카드사용등록일)이 속한 카드이용기간의 첫 결제일에 청구되며, \n\t 카드별 발급 시점을 기준으로 1년 단위로 청구됩니다.\n⦁\t 연회비 반환기준 : 이미 납부한 연회비에서 카드 발급 및 배송 비용(발급 \n\t 첫 해 연회비에 한정), 부가 서비스 제공에 소요된 비용을 차감한 후 카드별\n\t (본인/가족) 계약을 해지한 날부터 잔여기간에 대하여 일할 계산됩니다.\n⦁\t 연회비 반환시기 : 카드별(본인/가족) 해지일 기준 10영업일 이내 \n\t 결제계좌로 입금됩니다. 다만, 부가서비스 제공 상품의 경우 카드별 \n\t 해지일 기준 다음 다음달 5영업일에 입금됩니다.\n구분\n본인\n가족\n기본\n제휴\n총 연회비\n기본\n제휴\n총 연회비\n국내외겸용 \n(Visa, Mastercard,\nAmex)\n20,000\n100,000\n120,000\n20,000\n10,000\n30,000\n국내외겸용 \n(UPI)\n20,000\n95,000\n115,000\n20,000\n5,000\n25,000\n국내전용\n20,000\n95,000\n115,000\n20,000\n5,000\n25,000\n연회비\n가족카드 이용 안내\n⦁\t 가족카드 연회비는 각 상품별 연회비 부과 기준을 따르며\n\t 가족카드 발급매수에는 제한이 없습니다.\n⦁\t 가족카드 부가서비스의 지난달 실적, 적립 할인 한도는 본인카드와 \n\t 합산 적용됩니다.\n⦁\t 가족카드 연말정산 시 가족카드 사용금액은 가족카드 명의자\n\t [카드 앞(뒤)면에 표기된[이름]의 신용카드 등 사용금액으로 포함됩니다.\n⦁\t 연간 소득금액기준은 국세청 기준에 따릅니다.\n⦁\t 본인회원이 가족회원의 카드사용 내역에 대한 알림을 받고자 하는 경우\n\t 가족회원의 동의를 받아 본인회원이 고객센터(1800-1111)에\n\t 별도 신청하여야 합니다.\n⦁\t 가족카드 이용대금명세서는 본인회원이 지정한 주소와 방법으로\n\t 본인회원에게 합산되어 발송됩니다. 다만, 가족카드 이용대금명세서를 \n\t 별도 요청하는 경우에는 본인회원, 가족회원에게 별도 발송 가능합니다.\n⦁\t 가족카드 이용으로 적립된 포인트는 본인회원의 포인트에 합산되어\n\t 관리되며, 본인회원이 하나카드고객센터(1800-1111) 및 \n\t 홈페이지 > 포인트양도에서 가족으로 등록된 회원에게만 양도 가능하며,\n\t 타 회원에게 양도는 불가합니다. \n⦁\t 가족등록은 고객센터에서만 등록 가능합니다.\n⦁\t 이혼, 사망, 파양 등 가족관계 변동 시 본인회원 또는 가족회원이 \n\t 하나카드 고객센터(1800-1111) 및 홈페이지/모바일앱 > 카드관리 \n\t > 카드해지신청 에서 가족카드 정지 또는 해지 가능합니다.\n⦁\t 가족회원의 가족관계 변동 시 카드사에 즉시 통지해야 하며 가족관계 \n\t 변동이 되었음에도 가족카드를 정지 또는 해지하지 않은 경우 \n\t 본인회원에게 의도하지 않은 카드사용 및 책임이 발생 할 수 있습니다.\n⦁\t 본인회원이 요청할 경우 가족회원의 동의 없이 가족카드가\n\t 한도감액/정지/해지될 수 있습니다\n6\n7\n* 제휴 연회비는 PREMIUM VOUCHER, AIRPORT 등 서비스 제공에 소요됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000003	6	20261102_000019	6	\N	BODY	1	2691	부가서비스 유지 및 변경 안내\n·\t카드 이용 시 제공되는 포인트 및 할인 혜택 등의 부가서비스는 카드 신규 출시(2024년 02월 01일) \n\t 이후 3년 이상 축소·폐지 없이 유지됩니다.\n·\t다만, 다음과 같은 사유가 발생한 경우 카드사는 부가서비스를 변경할 수있습니다.\n   ①\t카드사 의 휴업·파산·경영상의 위기 등에 따른 불가피한 경우\n   ①의 2\t제휴업체의 휴업·파산·경영상의 위기로 인해 불가피하게 부가서비스를 축소·변경하는 경우\n\t \t\n\t\n로서 다른 제휴업체를 통해 같은 종류의 유사한 부가서비스 제공이 불가한 경우\n   ②\t제휴업체가 카드사의 의사에 반하여 해당 부가서비스를 축소하거나 변경 시, 당초 부가서비스에 \n\t \t\n상응하는 다른 부가서비스를 제공하는 경우\n   ③\t부가서비스를 3년 이상 제공한 상태에서 해당 부가서비스로 인해 상품의 수익성이 현저히 낮아진 경우\n·\t카드사가 부가서비스를 변경하는 경우 변경 사유, 변경 내용을 다음 각 호에서 정하는 기간에 따라 \n\t 서면교부, 우편 또는 전자우편, 전화 또는 팩스, 휴대폰 메시지 또는 이에준하는 전자적 의사표시 중 \n\t 서로 다른 2가지 이상 의 방법으로 고지하여 드립니다. 다만, 제 2호의 경우 부가서비스 변경일 6개월 \n\t 이전부터는 서면교부, 우편 또는 전자우편, 전화 또는 팩스, 휴대폰 메시지 또는 이에 준하는 전자적 \n\t 의사표시 중 서로 다른 2가지 이상의 방법으로  매월 고지하여 드립니다.\n  \t1. ①, ① 의2, ② : 사유발생 즉시       2. ③ : 부가서비스 변경일 6개월 이전\n여신금융협회 심의필 제 2026-C1a-10094호(2026.07.03) / 준법심의 L-26-2051(2026.06.09) / VI 260615-71\n해외결제 및 기타안내\n·\t해외 이용 시(해외사이트 거래 포함) 미화(USD) 기준 거래 금액에 접수일의 하나은행 최초 고시 \n\t 전신환 매도율을 적용한 후, 국제브랜드사가 부과하는 국제브랜드수수료(Visa 1.1%, Mastercard 1.0%, \n\t Amex 1.4%, UPI 0.8%)와 하나카드가 부과하는 해외서비스수수료(신용카드 0.2%)를 포함하여 \n\t 원화로 청구됩니다.\n\t * 해외 이용시 청구금액 = (거래미화금액×전신환매도율¹)+국제브랜드수수료²+해외서비스수수료³\n\t  1.\t전신환매도율 : 접수일의 하나은행 최초고시 전신환매도율\n\t  2.\t국제브랜드수수료 = 거래미화금액×국제브랜드 이용수수료율×전신환매도율\n\t \t\n- 국제브랜드 이용수수료율 : Visa 1.1%, Mastercard 1.0%, Amex 1.4%, UPI 0.8%\n\t  3.\t해외서비스수수료 = (거래미화금액×해외서비스수수료율 (신용카드 0.2%))×전신환매도율\n·\t해외 가맹점에서 원화로 결제할 경우(DCC) 추가수수료가 발생하므로 현지 통화 또는 미화로 \n\t 거래 하시기 바랍니다.\n·\t해외원화결제서비스(DCC) 사전차단 서비스 이용 방법 : 콜센터, 홈페이지/모바일App(마이페이지/\n\t 라이프-이용안심서비스-해외원화결제(DCC)차단서비스)\n·\t일부 해외 거래 시 IC칩 비밀번호(PIN)를 요구하는 경우가 있으므로 출국 전 반드시 IC칩 비밀번호\n\t (PIN) 등록여부를 확인하시기 바랍니다.\n결제이용대금 결제 안내\n·\t결제 계좌 개설기관의 영업 마감시간(16시) 이후 결제 계좌에 입금된 금액에 대해서는 결제 계좌\n\t 개설 기관의 사정에 따라 당일 출금되지 못하여 연체로 처리 될 수 있으므로 유의하시기 바랍니다.\n\t 자동납부 업무 마감시간 이후에는 하나카드 홈페이지 / 모바일 등에서 즉시결제 또는 가상계좌입금\n\t (송금 납부)을 통해 당일 결제가 가능합니다.\n\t * 세부내용은 하나카드 홈페이지 [고객센터-카드이용안내-결제안내] 및 모바일앱 [고객센터 탭] 참고\n*\t필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을\n\t 미칠 수 있습니다.\n*\t계약 체결 전 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n*\t신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한 될 수 있습니다.\n*\t카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n*\t소비자는 금융소비자보호법에 따라 해당 상품 또는 서비스에 대하여 \n\t 설명을 받을 권리가 있습니다.\n*\t본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다 .\n*\t자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나  \n\t 고객센터로 문의 바랍니다.\n⦁\t상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 있습니다. \n⦁\t개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n⦁\t일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n⦁\t연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, 법정 최고금리(20%)를 \n\t 초과하지 않습니다.\n\t ※\t단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n\t  -\t일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리    \n\t  -\t무이자할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리\n\t  -\t그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은 금리 적용\n\t \t * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리(신규대출 기준)\n8\n	\N	RAW	PAGE_V1	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000004	1	20261102_000020	1	\N	BODY	1	2344	Visa\nSignature\n공통서비스\n서비스\n· 진에어빠른체크인및빠른짐찾기서비스(연4회, 최대4인) \n· 카타르항공최대15% 할인\n(예약기간: ~26.10.31 / 여행기간: ~27.3.31)\n· 일본항공일본행항공권5% 할인(25.10.1~26.03.31)\n· 공항의전서비스(yQ Meet & Assist) 20% 할인\n내용\n· 전세계900여개호텔Visa Luxury Hotel Collection 혜택제공\n· Hotels.com 쿠폰코드입력시최대8% 할인(숙박기간: ~27.6.30)\n· Booking.com 최대7% 월렛포인트캐시백(매월1일~15일한정)\n· Expedia 8% 할인(숙박기간: ~27.6.30)\n· IHG Hotel&Resorts 20% 할인(숙박기간: ~27.1.3)\n· Accor China 중화권호텔최소2박예약시20% 할인(~26.9.30)\n· 반얀트리최소2박숙박시20%할인\n(예약기간: ~26.5.31 / 숙박기간: ~26.8.31)\n· Ascott 프로모션기간내사용시리워드등급업그레이드\n서비스(~27.11.30)\n· 국내특급호텔(약68여개) F&B 5~20% 할인\n· 국내특급호텔(약73여개) 객실/패키지5~60% 할인\n· 국내호텔스파(약22여개) 10~20% 할인\n· 국내부티크호텔(약23여개) 객실/F&B 5~50% 할인\n· 국내특급호텔(약6여개) 로비라운지5~20% 할인\nHotel\nAir &\nAirport\nTravel\nDining &\nLifestyle\nShopping\n* 아래의Visa Signature서비스는Visa Signature 등급카드\n소지자에게공통으로제공됩니다.\n· Hertz 해외렌터카기본10% 할인및추가혜택(~26.3.31)\n· AVIS 해외렌터카최대35% 할인\n· Rentalcars.com 10% 추가할인(~26.4.30)\n· Movv 이동서비스국내1.5~3.5만원, 해외8% 할인\n· 아시아태평양공항픽업서비스\nTBR Luxury Airport Transfer 15% 할인\n· 굿럭해외공항짐배송및보관20% 할인\n· 굿럭인천공항입국시교통약자짐찾기대행및배송서비스할인\n· Trip.com 최대6%할인\n· 롯데면세점(국내)고객면세점할인및\n회원등급업그레이드혜택제공(~26.6.30)\n· 롯데면세점싱가포르차이공항고객면세점할인\n(~26.10.16)\n· 현대백화점면세점골드멤버십제공(최대15% 할인)\n· Mitsui Outlet Park에서최대10%할인(~27.11.30)\n· 비자엘리트다이닝최대20% 할인혜택제공(~26.8.31)\n· 트립쿠폰멤버십무료제공\n· 하와이올로마나골프장그린피15% 할인및\n연습볼1버켓무료\n· Visa 컨시어지제공\n전화080-4880-880, 홈페이지www.concierge-asia.visa.com\n카카오톡“Visa 컨시어지” 채널추가\n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용\n평점이하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이\n발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가\n발생할수있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등\n적용되며, 법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) \n유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부\n계약기간의유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융\n가계자금대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관\n가중평균대출금리(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도\n등에영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기\n바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금\n결제일에상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가\n있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐\n제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를\n참고하시거나고객센터로문의바랍니다.\n여신금융협회심의필제2026 - C1a - 05178호( 2026.04.13 ) / 준법심의L-26-0467 (2026.03.16)\n* 본Visa Signature 서비스안내서는회원이발급받은카드\n상품안내장, 이용약관과함께교부되오니, 카드이용과관련한\n유의사항을반드시확인하시기바랍니다.\n* 본서비스는Visa에서제공하는서비스로, 프리미엄서비스에\n대한구체적내용, 적용기준및유의사항등\nhttp://www.visakorea.com → ‘Visa 인피니트’에서사전에\n반드시확인해주시기바랍니다.\n* 본Visa Signature 서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000004	2	20261102_000021	2	\N	BODY	1	3246	Visa\nSignature 02\n선택서비스\nVisa Signature 선택서비스중특급호텔발렛파킹, 인천공항발렛파킹서비스를하나카드에서제공합니다.\nVisa Signature 02 선택서비스\n특급호텔발렛파킹서비스\n서비스혜택\n- 국내주요특급호텔무료발렛파킹서비스제공\n이용조건\n- 호텔통합월2회서비스제공\n- 지난달(1일~말일) 국내외일시불/할부50만원이상이용시서비스제공\n(최초카드사용등록후다음달말일까지는지난달카드이용금액\n50만원미만시에도서비스제공)\n이용방법\n- 주차시호텔현관에서도어맨에게발렛파킹요청후주차권수령\n- 차량인수시도어맨에게주차권과비자프리미엄카드제시\n- 호텔단말기를통해서비스이용가능여부확인후서비스제공\n대상호텔\n서울\n그랜드워커힐서울\n그랜드하얏트서울\n스위스그랜드호텔\n노보텔앰배서더서울강남\n더플라자\n서울드래곤시티\n노보텔앰배서더서울동대문\n반얀트리클럽앤스파서울\n비스타워커힐서울\n서울신라호텔\n오크우드프리미어코엑스센터\n그랜드머큐어임피리얼팰리스서울\nJW메리어트동대문스퀘어서울\n앰배서더서울풀만호텔\n메이필드호텔\nJW 메리어트호텔서울\n파크하얏트서울\n르메르디앙&목시서울명동\n서울외\n그랜드하얏트인천\n파크하얏트부산\n소노캄여수\n웨스틴조선부산\n그랜드머큐어앰배서더창원\n호텔인터불고대구\n인천공항발렛파킹서비스\n서비스혜택\n- 인천공항제1,2 여객터미널및김포공항국내선무료발렛파킹제공\n이용조건\n- 공항통합월2회서비스제공\n- 김포공항발렛파킹서비스는JADE Classic, JADE Prime 카드에한하여\n서비스제공(CLUB Premier, CLUB Signature 카드는서비스미제공)\n- 지난달(1일~말일) 국내외일시불/할부50만원이상이용시서비스\n제공(최초카드사용등록후다음달말일까지는지난달카드이용금액\n50만원미만시에도서비스제공)\n대상공항별이용방법\n주차시: 1. 인천공항제1여객터미널발렛전용차로및안내표지판을따라\n지하1층단기주차장A구역으로이동\n2. Maxerve 유니폼착용공식대행직원에게발렛요청후모바일\n차량접수증수령(카카오톡접수증발송)\n출차시: 1. 주차대행접수증에안내된출차장소로이동(지하3층A32 또는H38)\n2. 유인정산소모바일접수증제시“제휴카드승인“ 후차량인수\n3. 주차장출차시, 추자요금별도정산\n- 제1여객터미널\n- 제2여객터미널\n주차시: 1. 제2여객터미널발렛전용차로및안내표지판을따라\n지하1층서편단기주차장으로이동\n2. 파란색유니폼착용한공식대행직원에게발렛요청후\n모바일접수증수령(카카오톡/문자수신)\n출차시: 1. 접수증에표시된연락처를통해접수번호및차량번호확인후출차진행\n2. 접수증(또는차량보관증)에명기된구역(동편단기주차장지하1층)\n고객대기실에서비자프리미엄카드와접수증제시\n3. 서비스이용가능여부확인후발렛파킹서비스무료제공\n(출차시주차요금별도정산)\n* Visa 프리미엄서비스에대한구체적내용, 적용기준및유의사항\n등은Visa 홈페이지(www.visakorea.com) 또는하나카드홈페이지\n에서확인해주시기바랍니다.\n* 본Visa 프리미엄서비스안내서는회원이발급받은카드상품안\n내장, 이용약관과함께교부되오니, 카드이용과관련한유의사항\n을반드시확인하시기바랍니다.\n* 본Visa 프리미엄서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용평점이\n하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가발생할수\n있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등적용되며, \n법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) 유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부계약기간의\n유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융가계자금\n대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관가중평균대출금리\n(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도등에\n영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금결제일에\n상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를참고하시거나\n고객센터로문의바랍니다.\n아래의대상카드발급시Visa Signature02\n선택서비스가제공됩니다.\nCLUB Premier 카드CLUB Signature 카드\nJADE Classic 카드JADE Prime 카드\nMG+ BLACK\n여신금융협회심의필제2026-C1a-05544호( 2026.04.17 )/ 준법심의L-26-0471 (2026.03.17)\n주차시: 1. 국내선청사2층우측하늘색라인따라진입후, 오렌지색유니폼\n착용공식주차대행직원에게발렛파킹요청\n2. 차량상태점검후차량인도및차량보관증수령\n출차시: 1. 출발지항공기탑승전차량보관증에기재된연락처로출차요청\n2. 차량인수시, 접수증과프리미엄마스터카드제시후서비스\n이용가능여부확인\n3. 차량인수후출차시고객이주차요금별도정산\n- 김포공항국내선(이용가능시간05:00~21:00 / 출차는24시간가능)\n사전예약처\n인천공항1터미널\nhttps://Maxerve-mparking.com/valet\n인천공항2터미널\nhttps://valet.amanopark.co.kr\n김포공항\n(사전예약없이이용가능)\n유의사항\n- 상기서비스는국내에서발급된비자프리미엄카드회원으로해당호텔의객실\n및식음료업장(연회장제외) 이용을위해내방한회원본인에한해\n제공함을원칙으로합니다.\n- 상기서비스는이용시호텔정책에따라해당호텔을이용한영수증제시를요청\n할수있으며, 영수증미지참시에는별도의발렛파킹비용과주차금액이청구될\n수있습니다.\n- 서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하셔야합니다.\n- 상기서비스이용시발렛파킹비용및1일3시간이내의주차비가무료로제공\n됩니다. 이용시간초과시주차금액이별도로부과될수있으며, 이는별도로\n부담하셔야합니다.\n- 일부호텔은반드시당일일정금액의영수증지참시에만서비스가제공됩니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시기\n바랍니다.\n유의사항\n- 서비스제공횟수초과시발렛파킹비용을별도로부담하셔야합니다.\n- 상기서비스는발렛파킹비용에만적용되므로, 주차비용은별도로정산하셔야\n합니다.\n- 3층여객터미널승용차전용도로에서5분이상정차시과태료가부과될수\n있습니다.\n- 사전예약고객대상으로서비스제공되며, 현장상황에따라당일서비스요청\n고객도접수가가능합니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시기\n바랍니다. \n	\N	RAW	PAGE_V1	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261103_000009	1	20261103_000042	1	\N	BODY	1	1268	AMEX\nPlatinum Elite\n공통서비스\n* 아래의AMEX Platinum Elite 서비스는AMEX Platinum Elite 등급카드\n소지자에게공통으로제공됩니다.\n서비스\n내용\nTravel\nHotel\nDining\nShopping\nLifestyle\n서비스\n내용\n* 본AMEX Platinum Elite 서비스안내서는회원이발급받은카드\n상품안내장, 이용약관과함께교부되오니, 카드이용과관련한\n유의사항을반드시확인하시기바랍니다.\n* 본서비스는AMEX에서제공하는서비스로, 프리미엄서비스에\n대한구체적내용, 적용기준및유의사항등은\nwww.americanexpress.com/ko-kr/network → ‘아멕스카드\n전체혜택’에서사전에반드시확인하시기바랍니다.\n* 본AMEX Platinum  Elite 서비스는기간이명시되지않는한\n2026년1월1일~ 12월31일까지제공됩니다.\n* 현대면세점, 신라면세점, 신라아이파크면세점\n5~20% 할인\n* 꽃집청년들관엽10%, 화환15% 할인\n* 유니페어구두5% 할인및Shoe Care 쿠폰제공\n* 메종레페토서울30만원이상구매시5% 할인\n* 인천/김포/김해공항라운지성인요금동반\n2인까지30% 할인\n* 인천/김포공항국제선F&B 매장10% 할인\n* 하이파킹지정주차장(21개) 주차요금20% 할인\n* 카모아국내외렌터카요금5% 할인\n* 국내29개특급호텔객실5~50% 할인\n* 국내27개특급호텔F&B 5~10% 할인\n* 빌라르코라이, 그란멜리아호텔나트랑\n최대25% 할인\n* JW 메리어트호텔하노이조식및웰컴드링크제공\n* 구름에2박이상숙박시1박무료\n* 조선왕가호텔객실10~20% 할인\n* 락고재객실10% 할인\n* 백미당전메뉴(베이커리류제외) 중1개구매시,\n아메리카노, 라떼, 소프트아이스크림중택1 \n제공(월1회, 연2회)\n* 카페아티제제조음료구매시, \n아메리카노쁘띠사이즈제공(월1회, 연6회)\n* 생어거스틴, 키친동백, 다인힐, 무탄10~20% 할인\n또는서비스메뉴제공\n* 수도권30여개골프장주중골프부킹대행서비스\n제공(연2회)\n* 리프레쉬골프10% 할인쿠폰6장제공\n* 사이판월드리조트골프패키지최대40% 할인\n* 국내특급호텔(4개) 스파정규프로그램할인\n*국내특급호텔(6개) 스파및더트리니티스파강남점\n5~20% 할인\n* 포브스코리아, 월간중앙, 이코노미스트1년구독료\n50% 할인\n* 오픈갤러리그림렌탈첫이용5만원할인\n* TURU Car Wash 세차및상품10% 할인\n* 인스타워시출장세차5~10% 할인\n* 서프홀릭서핑강습료5% 할인\n여신금융협회심의필제2026 - C1a - 05150호( 2026.04.13 )/ 준법심의L-26-0404 (2026.03.03)\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:34.783526+00	SYSTEM	2026-11-03 05:20:34.783526+00	SYSTEM
20261103_000009	2	20261103_000043	2	\N	BODY	1	2142	*필요이상의신용카드발급및사용은개인신용평점이나이용한도등에\n영향을미칠수있습니다.\n*카드발급신청시상품설명서및상품약관을반드시확인하시기바랍니다.\n*신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이제한될\n수있습니다.\n*카드이용대금과이에수반되는모든수수료를지정된대금결제일에\n상환하여야합니다.\n*금융소비자는해당상품또는서비스에대하여설명을받을권리가있습니다.\n*본상품설명서는법령및내부통제기준에따른절차를거쳐제공됩니다.\n*자세한내용은하나카드홈페이지(www.hanacard.co.kr)를참고하시거나\n고객센터로문의바랍니다.\n*상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용평점이\n하락할수있습니다.\n*개인신용평점하락시금융거래와관련된불이익이발생할수있습니다.\n*일정기간원리금을연체할경우, 모든원리금을변제할의무가발생할수\n있습니다.\n*연체이자율(약정이율+최대3%)은회원별·이용상품별로차등적용되며,\n법정최고금리(20%)를초과하지않습니다.\n※단, 연체발생시점에약정이율이없는경우는아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월)유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부계약기간의\n유이자할부금리\n- 그외의경우: 약정이율은상법상상시법정이율과상호금융가계자금\n대출금리*중높은금리적용\n*한국은행에서매월발표하는가장최근의비은행금융기관가중평균\n대출금리(신규대출기준)\n여신금융협회심의필제2026 - C1a - 05149호( 2026.04.13 )\n/ 준법심의L-26-0406 (2026.03.05)\nAMEX Platinum Elite 선택서비스\nAMEX\nPlatinum Elite\n선택서비스\nAMEX Platinum Elite 선택서비스\n아래대상카드발급시AMEX Platinum Elite\n선택서비스가제공됩니다.\n상품유형\n대상카드\nAMEX Platinum\nElite\n하나CLUB H\n아메리칸익스프레스리저브카드\n*AMEX 프리미엄서비스의상세한내용은AMEX 홈페이지\n(www.americanexpress.com/ko-kr/network) 또는하나카드\n홈페이지에서반드시확인하시기바랍니다.\n*본AMEX 프리미엄서비스안내서는회원이발급받은카드상품안내\n장, 이용약관과함께교부되오니, 카드이용과관련한유의사항을반\n드시확인하시기바랍니다.\n*본AMEX 프리미엄서비스는2026년1월1일~ 12월31일까지제공\n됩니다.\n공항커피서비스\n서비스혜택\n¶인천/김포공항내주요커피매장핫아메리카노(S) 무료\n이용조건\n¶통합월1회, 연12회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부50만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액50만원미만시에도서비스제공)\n이용방법\n¶대상카드와당일출국항공권함께제시\n구분\n대상가맹점\n인천국제공항\n제1여객터미널\n(면세구역)\n배스킨라빈스31, 커피빈, 잠바주스,엔제리너스,리브팜,던킨도너츠,\n크리스피크림도넛,커피앳웍스\n인천국제공항\n제2여객터미널\n(면세구역)\n커피앳웍스, 던킨도너츠, 쇼콜라팔레트, 크리스피크림도넛,\n잠바주스,리나스,베스킨라빈스31\n김포국제공항\n(일반구역)\n옐로우인더화이트\n공항리무진/공항철도서비스\n서비스혜택\n¶공항리무진및공항철도편도티켓무료서비스\n이용조건\n¶통합일1회, 연12회서비스제공\n¶아멕스프리미엄카드로50만원이상항공권구매후카드와\ne티켓함께제시(탑승일주일내e티켓제시, 본인항공권에\n한함, 합산불가)\n이용방법\n대상가맹점\n이용방법\n인천국제공항\n제1여객터미널\n통합매표소\n¶위치: (내부) 4.6.9.11번게이트유인정산소\n¶해당노선: 인천공항출발전노선\n¶이용안내: 티켓금액1만원초과시차액본인부담\n(현금결제만가능)\n인천국제공항\nK리무진\n직영매표소\n¶위치: 제1여객터미널3층일반지역8번출입구부근K Books \n매장, 제2여객터미널3층중앙K Books 매장\n¶해당노선: 6701(시청방면), 6702(남산방면), 6703(강남방면), \n6705(잠실방면)\n¶이용안내: 4개노선에한함, 차액부담없음\n공항철도\n온라인예약\n발권시스템\n¶AREX 공항철도직통열차홈페이지(www.airportrailroad.com)\n또는공항철도앱\n1. 승차권결제페이지에서할인선택후제휴카드정보입력란에\n정보입력\n2. 승차권발권후QR 인식하여게이트입장\n유의사항\n¶공항리무진은운영시간내에만서비스제공, 휴식시간에는서비스제공\n불가합니다.\n¶공항철도는현장매표소에서서비스적용불가하며, 공항철도앱을통해\n예약발권후이용가능합니다.\n¶제1터미널에서키오스크발권시서비스제공불가하며, 구매처에서발권\n후환불희망해도서비스이용으로간주되어서비스제공횟수가차감됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:34.783526+00	SYSTEM	2026-11-03 05:20:34.783526+00	SYSTEM
20261103_000009	3	20261103_000044	3	\N	BODY	1	2725	서비스혜택\n¶인천공항제1,2여객터미널및김포공항국내선무료발렛\n파킹서비스제공\n이용조건\n¶통합월2회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부50만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액50만원미만시에도서비스제공)\n이용방법\nhttps://maxervemparking.com/valet/\n차량인수후출차시주차요금별도정산\n차량인수후출차시주차요금별도정산\n※ 공항이용객이많은연휴기간, 명절, 여행성수기시즌등에는\n사전예약후이용하시기바랍니다.\n(예약: https://valet.amanopark.co.kr/#main)\n유의사항\n¶서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하셔야\n합니다.\n¶상기서비스는발렛파킹비용에만적용되므로, 주차요금은별도로정산\n하셔야합니다.\n¶여객터미널3층승용차전용도로에서5분이상정차시과태료가부가될\n수있습니다.\n¶인천공항제1 여객터미널\n¶인천공항제2 여객터미널\n¶김포공항국내선\n인천/김포공항발렛파킹서비스\nAMEX Platinum Elite 선택서비스\nAMEX Platinum Elite 선택서비스중인천/김포공항발렛파킹, 특급호텔발렛파킹, Be My Guest 서비스, 공항리무진/철도서비스, 공항커피/서점할인을하나카드에서제공합니다.\n공항Books Store 할인서비스\nBe My Guest 서비스\n서비스혜택\n¶대상점에서도서1권이상, 5천원이상결제시3천원할인\n이용조건\n¶통합월1회, 연12회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부50만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액50만원미만시에도서비스제공)\n대상가맹점\n¶인천공항Books Store 전매장\n서비스혜택\n¶호텔,패밀리레스토랑6만원이상결제시3만원현장할인\n¶ 호텔델리4만원이상결제시2만원현장할인\n이용조건\n¶통합월1회, 연3회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부50만원이상이용시\n서비스제공(최초카드사용등록후다음달말일까지는지난\n달카드이용금액50만원미만시에도서비스제공)\n¶다른프로모션및혜택과중복적용불가및일부기간내\n서비스이용이제한될수있음\n¶각대상가맹점별유의사항은AMEX 홈페이지참조\n구분\n대상가맹점\n호텔\n레스토랑\n포시즌스호텔서울(더마켓키친), 콘래드서울(아트리오,SUT.\nThe Butcher’s Edge), \nJW메리어트동대문스퀘어서울(타볼로24, BLT스테이크),\n반얀트리클럽앤스파서울(그라넘다이닝라운지,페스타바이충후),\n그랜드인터컨티넨탈서울파르나스(그랜드키친), \n앰배서더서울풀만(더킹스,풀하우스테라스), 안다즈서울강남\n(조각보바이츠앤와인,조각보키친, 조각보미트앤코),\n부산웨스틴조선(까밀리아, 오킴스, 파노라마라운지, 셔블),\n파라다이스부산(라스칼라,사까에), 더블트리바이힐튼서울판\n교(데메테르, 루프탑레스토랑&바), 서울신라호텔(콘티넨탈,라\n연,팔선,아리아께,더파크뷰), 웨스틴조선서울(아리아,루브리카,\n나인스게이트),그랜드워커힐서울(온달), 노보텔앰배서더동대\n문(푸드익스체인지,고메바&다이닝), 파르나스제주(콘페티), \n그랜드조선제주(아리아),그랜드조선부산(아리아,팔레드신,라\n운지앤바테라스292),호텔나루서울엠갤러리(부아쟁), 파크하\n얏트부산(리빙룸, 다이닝룸), 임피리얼팰리스서울(뷔페패밀리\n아, 천산),파크하얏트서울(더팀버하우스)\n패밀리\n레스토랑\nChai797(전국매장), 정육점(전국매장), 63스퀘어(워킹온더클라\n우드, 터치더스카이, 슈치쿠, 백리향), 아웃백스테이크하우스\n(전국매장, 딜리버리제외)\n호텔델리\n포시즌스서울(컨펙션즈바이포시즌스), 콘래드서울(플레임즈),\n앰배서더서울풀만(1955 그로세리아), 노보텔앰배서더동대문\n(더델리),그랜드조선부산(조선델리), 롯데호텔부산(델리카한스,\n더라운지앤바), 부산웨스틴조선(조선델리),\n호텔나루서울엠갤러리(마포에이트),그랜드머큐어임피리얼팰\n리스서울(카페델마르)\n¶원활한서비스이용을위해서비스이용전제휴처에이용가능여부를\n확인하시기바랍니다\n유의사항\n¶호텔정책에따라해당호텔객실및식음료업장(연회장제외) 이용한본인\n회원에한해제공되며, 영수증미지참시발렛파킹비용과주차요금이청구될\n수있습니다.\n¶1일3시간무료주차제공되며, 3시간초과이용시주차요금별도부과됩니다.\n¶ JW 메리어트호텔서울(50,000원이상), 몬드리안서울이태원(25,000원이상)\n, 포시즌스서울(30,000원이상)의호텔이용영수증을제시하는경우에한해\n서비스가제공되며이용확인증미지참시에는주차요금과발렛파킹이용료\n를현장에서지불하셔야합니다.\n¶파크하얏트서울은호텔정책에따라당일호텔에서2만원이상이용한영수\n증을제시하는경우에한해무료주차서비스가제공됩니다.\n¶서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하셔야\n합니다.\n¶원활한서비스이용을위해서비스이용전제휴처에이용가능여부를\n확인하시기바랍니다.\n¶국내주요특급호텔무료발렛파킹서비스제공\n이용방법\n¶호텔발렛파킹부스에서비스요청후주차권수령\n¶차량인수시해당카드와주차권및호텔이용영수증제시\n¶ 호텔직원서비스이용가능여부확인후서비스제공\n¶호텔통합월2회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부50만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액50만원미만시에도서비스제공)\n서비스혜택\n이용조건\n특급호텔발렛파킹서비스\n지역\n대상호텔\n서울\n앰배서더서울풀만호텔\n그랜드워커힐서울\n그랜드하얏트서울\n몬드리안서울이태원\n노보텔앰배서더서울강남\n노보텔엠배서더서울동대문\n르메르디앙서울명동\n메이필드호텔\n코트야드메리어트서울타임스퀘어\n메리어트이그제큐티브아파트먼트\n반얀트리클럽앤스파서울\n비스타워커힐서울\n서울신라호텔\n더플라자\n콘래드서울\n파크하얏트서울\nJW 메리어트동대문스퀘어\nJW 메리어트호텔서울\n안다즈서울강남\n포시즌스서울\n지방\n그랜드하얏트인천\n그랜드조선부산\n파크하얏트부산\n호텔인터불고대구\n힐튼경주\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:34.783526+00	SYSTEM	2026-11-03 05:20:34.783526+00	SYSTEM
20261103_000010	1	20261103_000045	1	\N	BODY	1	1179	AMEX\nPlatinum\n공통서비스\n* 아래의AMEX Platinum 서비스는AMEX Platinum 등급카드\n소지자에게공통으로제공됩니다.\n서비스\n내용\n* 인천/김포/김해공항라운지성인요금동반2인까지\n30% 할인\n* 인천/김포공항국제선F&B 매장10% 할인\n* 하이파킹지정주차장(21개) 주차요금20% 할인\n* 카모아국내외렌터카요금5% 할인\nTravel\nHotel\nDining\n* 현대면세점, 신라면세점, 신라아이파크면세점\n5~20% 할인\n* 꽃집청년들관엽10%, 화환15% 할인\n* 유니페어구두5% 할인및Shoe Care 쿠폰제공\n* 메종레페토서울30만원이상구매시5% 할인\nShopping\nLifestyle\n서비스\n내용\n* 본AMEX Platinum 서비스안내서는회원이발급받은카드\n상품안내장, 이용약관과함께교부되오니, 카드이용과관련한\n유의사항을반드시확인하시기바랍니다.\n* 본서비스는AMEX에서제공하는서비스로, 프리미엄서비스에\n대한구체적내용, 적용기준및유의사항등은\nwww.americanexpress.com/ko-kr/network → ‘아멕스카드\n전체혜택’에서사전에반드시확인하시기바랍니다.\n* 본AMEX Platinum 서비스는기간이명시되지않는한2026년\n1월1일~ 12월31일까지제공됩니다.\n* 국내29개특급호텔객실5~50% 할인\n* 국내27개특급호텔F&B 5~10% 할인\n* 빌라르코라이, 그란멜리아호텔나트랑\n최대25% 할인\n* JW 메리어트호텔하노이조식및웰컴드링크제공\n* 구름에2박이상숙박시1박무료\n* 조선왕가호텔객실10~20% 할인\n* 락고재객실10% 할인\n* 백미당전메뉴(베이커리류제외) 중1개구매시,\n아메리카노, 라떼, 소프트아이스크림중택1 \n제공(월1회, 연2회)\n*카페아티제제조음료구매시, 아메리카노쁘띠사이즈\n제공(월1회, 연6회)\n*생어거스틴, 키친동백, 다인힐, 무탄10~20% 할인또는\n서비스메뉴제공\n* 리프레쉬골프10% 할인쿠폰6장제공\n* 사이판월드리조트골프패키지최대40% 할인\n* 국내특급호텔(6개)스파및더트리니티스파강남점\n5~20% 할인\n* 포브스코리아, 월간중앙, 이코노미스트1년구독료\n50% 할인\n* 오픈갤러리그림렌탈첫이용5만원할인\n* TURU Car Wash 세차및상품10% 할인\n* 인스타워시출장세차5~10% 할인\n* 서프홀릭서핑강습료5% 할인\n여신금융협회심의필제2026 - C1a - 05144호( 2026.04.13 )/ 준법심의L-26-0405 (2026.03.03)\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:39.726129+00	SYSTEM	2026-11-03 05:20:39.726129+00	SYSTEM
20261103_000010	2	20261103_000046	2	\N	BODY	1	2298	AMEX Platinum 선택서비스중특급호텔발렛파킹, 인천공항발렛파킹서비스를하나카드에서제공합니다.\n*필요이상의신용카드발급및사용은개인신용평점이나이용한도등에\n영향을미칠수있습니다.\n*카드발급신청시상품설명서및상품약관을반드시확인하시기바랍니다.\n*신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이제한될\n수있습니다.\n*카드이용대금과이에수반되는모든수수료를지정된대금결제일에\n상환하여야합니다.\n*금융소비자는해당상품또는서비스에대하여설명을받을권리가있습니다.\n*본상품설명서는법령및내부통제기준에따른절차를거쳐제공됩니다.\n*자세한내용은하나카드홈페이지(www.hanacard.co.kr)를참고하시거나\n고객센터로문의바랍니다.\n*상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용평점이\n하락할수있습니다.\n*개인신용평점하락시금융거래와관련된불이익이발생할수있습니다.\n*일정기간원리금을연체할경우, 모든원리금을변제할의무가발생할수\n있습니다.\n*연체이자율(약정이율+최대3%)은회원별·이용상품별로차등적용되며,\n법정최고금리(20%)를초과하지않습니다.\n※단, 연체발생시점에약정이율이없는경우는아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월)유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부계약기간의\n유이자할부금리\n- 그외의경우: 약정이율은상법상상시법정이율과상호금융가계자금\n대출금리*중높은금리적용\n*한국은행에서매월발표하는가장최근의비은행금융기관가중평균\n대출금리(신규대출기준)\nAMEX\nPlatinum 02\n선택서비스\n유의사항\n¶호텔정책에따라해당호텔객실및식음료업장(연회장제외) 이용한\n본인회원에한해제공되며, 영수증미지참시발렛파킹비용과주차\n요금이청구될수있습니다.\n¶1일3시간무료주차제공되며, 3시간초과이용시주차요금별도부과\n됩니다.\n¶파크하얏트서울은호텔정책에따라당일호텔에서2만원이상이용한\n영수증을제시하는경우에한해무료주차서비스가제공됩니다.\n¶서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하셔야\n합니다.\n¶원활한서비스이용을위해서비스이용전제휴처에이용가능여부를\n확인하시기바랍니다.\n¶국내주요특급호텔무료발렛파킹서비스제공\n이용방법\n¶호텔발렛파킹부스에서비스요청후주차권수령\n¶차량인수시해당카드와주차권및호텔이용영수증\n제시\n¶ 호텔직원서비스이용가능여부확인후서비스제공\n¶호텔통합월3회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부30만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액30만원미만시에도서비스\n제공)\n서비스혜택\n이용조건\n특급호텔발렛파킹서비스\n지역\n대상호텔\n서울\n앰배서더서울풀만호텔\n그랜드워커힐서울\n그랜드하얏트서울\n노보텔앰배서더서울강남\n안다즈서울강남\n서울가든호텔\n노보텔엠배서더동대문\n메이필드호텔\n르메르디앙서울명동\n반얀트리클럽앤스파서울\n비스타워커힐서울\n서울신라호텔\n파크하얏트서울\n콘래드서울\nJW 메리어트동대문스퀘어\n메리어트이그제큐티브아파트먼트서울\n지방\n그랜드하얏트인천\n힐튼경주\n호텔인터불고대구\n파크하얏트부산\n소노캄여수\nAMEX Platinum 02 선택서비스\n아래대상카드발급시AMEX Platinum 02 선택서비스가제공됩니다.\n상품유형\n대상카드\nAMEX\nPlatinum 02\nCLUB SK 카드\nClub SK 카드hiplus 선불하이패스\nCLUB SK Point 카드\n*AMEX 프리미엄서비스의상세한내용은AMEX 홈페이지\n(www.americanexpress.com/ko-kr/network) 또는하나카드\n홈페이지에서반드시확인하시기바랍니다.\n*본AMEX 프리미엄서비스안내서는회원이발급받은카드상품안내\n장, 이용약관과함께교부되오니, 카드이용과관련한유의사항을반\n드시확인하시기바랍니다.\n*본AMEX 프리미엄서비스는2026년1월1일~ 12월31일까지제공\n됩니다.\nAMEX Platinum 02 선택서비스\n서비스혜택\n¶인천공항제1,2여객터미널무료발렛파킹서비스제공\n이용조건\n¶통합월3회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부30만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액30만원미만시에도서비스제공)\n이용방법\n차량인수후출차시주차요금별도정산\n※ 공항이용객이많은연휴기간, 명절, 여행성수기시즌등\n에는사전예약후이용하시기바랍니다.\n(예약: https://valet.amanopark.co.kr/#main)\n유의사항\n¶서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하\n셔야합니다.\n¶상기서비스는발렛파킹비용에만적용되므로, 주차요금은별도로\n정산하셔야합니다.\n¶여객터미널3층승용차전용도로에서5분이상정차시과태료가\n부가될수있습니다.\n¶원활한서비스이용을위해서비스이용전제휴처에이용가능여부를\n확인하시기바랍니다.\n¶인천공항제1 여객터미널\n¶인천공항제2 여객터미널\n인천공항발렛파킹서비스\n여신금융협회심의필제2026-C1a-05577호( 2026.04.20 )\n/ 준법심의L-26-0408 (2026.03.05)\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:39.726129+00	SYSTEM	2026-11-03 05:20:39.726129+00	SYSTEM
20261103_000011	1	20261103_000047	1	\N	BODY	1	2276	Amex\nPlatinum\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n공통서비스 \n•상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 \n    하락할 수 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다. \n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며,\n    법정 최고금리(20%)를 초과하지 않습니다.\n   ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n    - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n    - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n    - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n* 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n* 계약 체결 전 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n* 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한 될 수 있습니다.\n* 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n* 소비자는 금융소비자보호법에 따라 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n* 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다. \n* 자세한 내용은 하나카드 홈페이지(www.hanacard.co.kr)를 참고하시거나\n  고객센터로 문의 바랍니다.\n  \n \n여신금융협회 심의필 제 2026-C1a-05144호(2026.04.13) / 준법심의 L-26-0405(2026.03.03) / VI 260818-31\nAMEX Platinum Platinum 공통서비스\n· 국내 29개 특급호텔 객실 5~50% 할인\n· 국내 27개 특급호텔 F&B 5~10% 할인\n· 빌라 르 코라이, 그란 멜리아 호텔 나트랑 최대 25% 할인\n· JW 메리어트 호텔 하노이 조식 및 웰컴드링크 제공\n· 구름에 2박 이상 숙박 시 1박 무료\n· 조선왕가호텔 객실 10~20% 할인\n· 락고재 객실 10% 할인\nDining\nTravel\n· 백미당 전 메뉴(베이커리류 제외) 중 1개 구매 시,\n   아메리카노, 라떼, 소프트아이스크림 중 택 1 제공 (월 1회, 연 2회)\n· 카페 아티제 제조 음료 구매 시, 아메리카노 쁘띠 사이즈 제공\n  (월 1회, 연 6회)\n· 생어거스틴, 키친동백, 다인힐, 무탄 10~20% 할인 또는    \n  서비스 메뉴 제공\nHotel\n* 본 AMEX Platinum 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용 약관과 함께 \n  교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 서비스는 AMEX에서 제공하는 서비스로, \n   프리미엄 서비스에 대한 구체적 내용, 적용기준 및 유의사항 등은 \n   www.americanexpress.com/ko-kr/network → ‘아멕스카드 전체 혜택’에서 \n   사전에 반드시 확인하시기 바랍니다.\n* 본 AMEX Platinum 서비스는 기간이 명시되지 않는 한 \n   2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 인천/김포/김해공항 라운지 성인요금 동반 2인까지 30% 할인\n· 인천/김포공항 국제선 F&B 매장 10% 할인\n· 하이파킹 지정 주차장(21개) 주차 요금 20% 할인\n· 카모아 국내외 렌터카 요금 5% 할인\nLife\nStyle\n· 리프레쉬 골프 10% 할인 쿠폰 6장 제공\n· 사이판 월드리조트 골프 패키지 최대 40% 할인\n· 국내 특급호텔(5개) 스파 5~20% 할인\n· 포브스코리아, 월간중앙, 이코노미스트 1년 구독료 50% 할인\n· 오픈갤러리 그림 렌탈 첫 이용 5만원 할인\n· TURU Car Wash 세차 및 상품 10% 할인\n· 인스타워시 출장세차 5~10% 할인\n· 서프홀릭 서핑 강습료 5% 할인\nShopping\n서비스\n내용\n· 현대면세점, 신라면세점, 신라아이파크 면세점 5~20% 할인\n· 꽃집 청년들 관엽 10%, 화환 15% 할인\n· 유니페어 구두 5% 할인 및 Shoe Care 쿠폰 제공\n· 메종 레페토 서울 30만원 이상 구매 시 5% 할인\n* 아래의 AMEX Platinum 서비스는 AMEX Platinum 등급 카드 소지자에게 공통으로 제공됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:44.573836+00	SYSTEM	2026-11-03 05:20:44.573836+00	SYSTEM
20261103_000011	2	20261103_000048	2	\N	BODY	1	3671	Amex\nPlatinum 03\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n선택서비스 \nAmex Platinum 선택서비스 중 특급호텔 발렛파킹, 인천공항/김포공항 발렛파킹 서비스를 하나카드에서 제공합니다.\nAmex Platinum 03 \n상품유형\n대상카드\nJADE Classic 카드\n서비스혜택\n이용조건\n이용방법\n국내 주요 특급호텔 무료 발렛파킹 서비스 제공\n호텔 통합 월 2회 서비스 제공\n지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n(최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액 \n50만원 미만 시에도 서비스 제공)\n - 호텔 발렛파킹 부스에 서비스 요청 후 주차권 수령\n- 차량 인수 시 해당 카드와 주차권 및 호텔 이용 영수증 제시\n- 호텔 직원 서비스 이용 가능 여부 확인 후 서비스 제공\n그랜드 하얏트 인천\n힐튼 경주\n호텔 인터불고 대구\n파크하얏트 부산\n소노캄 여수\n서울\n서울 외\n지역\n대상 호텔\n유의사항\n- 호텔 정책에 따라 해당 호텔 객실 및 식음료업장(연회장 제외) 이용한 본인 회원에 한해 제공되며, \n   영수증 미지참 시 발렛파킹 비용과 주차 요금이 청구될 수 있습니다.\n- 1일 3시간 무료 주차 제공되며, 3시간 초과 이용 시 주차요금 별도 부과됩니다.\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능여부를 확인하시기 바랍니다. \n앰배서더 서울 풀만 호텔\n그랜드 워커힐 서울\n그랜드 하얏트 서울\n노보텔 앰배서더 서울 강남\n노보텔 앰배서더 서울 동대문\n안다즈 서울 강남\n서울 가든 호텔\n메이필드 호텔\n르메르디앙 서울 명동\n반얀트리 클럽 앤 스파 서울\n비스타 워커힐 서울\n서울 신라 호텔\n파크 하얏트 서울 호텔\n콘래드서울\nJW 메리어트 동대문 스퀘어\n메리어트 이그제큐티브 아파트먼트 서울\n특급호텔 발렛파킹 서비스\n아래 대상 카드 발급 시 Amex Platinum 03 선택서비스가 제공됩니다.\n* Amex 프리미엄 서비스의 상세한 내용은 Amex 홈페이지\n  (http://www.americanexpress.com/ko-kr/network/)를 통해 확인하시기  바랍니다.\n* 본 Amex 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품 안내장, 이용약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을  반드시 확인하시기 바랍니다.\n* 본 Amex 프리미엄 서비스는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\nAmex Platinum 03 선택서비스\n사전 예약처\n제2여객터미널  \n김포공항 국내선\n \n주차 시 : \n① 단기주차장 지하1층 서편 주차구역 110~112번 진입\n② 파란색 유니폼 착용 공식 주차대행 직원에게 발렛 요청\n③ 차량 접수증 알림톡 발송\n출차 시 :\n① 동편 단기주차장 지하1층 210번 고객대기실로 이동\n② 정산소에서 아멕스 프리미엄 카드 제시 및 주차장소 확인\n③ 차량 인수 후 출차 시 주차요금 별도 정산\n※ 공항 이용객이 많은 연휴기간, 명절, 여행 성수기 시즌 등에는\n     사전 예약 후 이용하시기 바랍니다.\n주차 시 : \n① 국내선 청사 출발층(2층) 제일 우측 라인(하늘색)따라 진입             \n② 오렌지색 유니폼 착용 공식 대행 직원에게 발렛파킹 요청             \n③ 차량 상태 점검 후 차량 인도 및 차량보관증 수령\n출차 시 :\n① 출발지 항공기 탑승 전 차량보관증에 있는 연락처로 차량 출차 요청\n② 조기 출발로 비행 일정이 변경된 경우, 반드시 사전에 차량보관증에\n    있는 연락처로 변경사항 전달 및 차량 출차 요청\n③ 차량 인수시, 접수증과 아멕스 프리미엄 카드 제시하여 단말기를 \n     통해 서비스 이용 가능여부 확인 후 서비스 무료 제공             \n④ 차량인수 후 출차 시, 주차 요금 별도 정산\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 상기 서비스는 발렛파킹 비용에만 적용되므로, 주차요금은 별도로 정산하셔야 합니다.\n- 여객터미널 3층 승용차전용도로에서 5분 이상 정차 시 과태료가 부가될 수 있습니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능여부를 확인하시기바랍니다. \n인천공항 1터미널 https://Maxerve-mparking.com/valet\n인천공항 2터미널 https://valet.amanopark.co.kr/#/main\n김포공항(사전예약 없이 이용가능)\n서비스혜택\n이용조건\n제1여객터미널  \n이용방법\n인천공항 제 1,2여객터미널, 김포공항 무료 발렛파킹 서비스 제공\n통합 월 2회 서비스 제공\n지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n(최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액 \n50만원 미만 시에도 서비스 제공)\n \n주차 시 : \n① 지하 1층 단기주차장 A구역 이동 후 Maxerve 유니폼 착용 공식\n     주차대행 직원에게 발렛 요청\n② 모바일 접수증 문자 발송 (카카오톡 접수증)\n출차 시 :\n① 입국 후 주차대행 접수증에 안내된 출차 장소로 이동\n     (지하 3층 A32구역 또는 H38 구역)\n② 유인정산소에서 모바일 접수증 제시 및 “제휴카드승인” 처리 후\n     차량 인수\n③ 주차장 출차 시, 주차요금은 별도정산\n※ 사전예약 고객 대상으로 서비스 제공, 현장상황에 따라 당일 서비스\n     요청 고객도 접수 가능\n인천공항 · 김포공항 발렛파킹 서비스\n•상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 \n    하락할 수 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다. \n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며,\n    법정 최고금리(20%)를 초과하지 않습니다.\n   ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n    - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n    - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n    - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n* 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n* 계약 체결 전 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n* 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한 될 수 있습니다.\n* 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n* 소비자는 금융소비자보호법에 따라 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n* 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다. \n* 자세한 내용은 하나카드 홈페이지(www.hanacard.co.kr)를 참고하시거나\n  고객센터로 문의 바랍니다.\n  \n \n여신금융협회 심의필 제 2026-C1a-11010호(2026.07.24) / 준법심의 L-26-2050(2026.06.09) / VI 260727-32\n(이용가능시간 05:00~21:00 / 출차는 24시간 가능)\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:44.573836+00	SYSTEM	2026-11-03 05:20:44.573836+00	SYSTEM
20261103_000012	1	20261103_000049	1	\N	BODY	1	2345	JCB Platinum\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nJCB Platinum 공통서비스\n*  JCB Prestige 서비스의 상세한 내용은 JCB 홈페이지(www.kr.jcb)를 통해 확인하시기 바랍니다.\n*  본 JCB Prestige 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n*  본 JCB Prestige 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-05514호(2026.04.17) / 준법심의 L-26-0521/ VI 260423-31\nDining : 다이닝서비스\n[일본 다이닝 서비스(1+1)]\n• 일본 최고 수준의 레스토랑에서 코스메뉴를 2인 이상 예약 시, \n 1인에 한해 무료 제공\n \nHotel : 호텔서비스\n[국내 특급호텔 할인 서비스]\n• 국내 33개 특급호텔에서 F&B(식음료) 및 객실, 스파 할인 서비스\nTravel : 여행서비스\n[해외 렌터카 서비스(Hertz)]\n• 60여 개국 Hertz 렌터카 할인 요금에서 추가 10% 할인 또는\n[일본 유니버설 스튜디오 재팬 JCB 전용 라운지 무료 이용 서비스]\n• 일본 유니버셜 스튜디오 재팬 JCB 라운지 본인 외 3명 (유아 포함) 무료 입장\n   (~3.31)\n[해외 Data 서비스(와이드 모바일) 할인가격 제공]\n• 해외  Data 서비스(와이드 모바일) 할인가격 제공\nAirport : 공항서비스\n[해외 공항 라운지 서비스(일본, 하와이)]\n• 일본/하와이의 주요 공항 라운지 서비스를 최대 6회 무료 이용 (~3.31)  \n * 대상 라운지는 JCB 홈페이지 참조\n[해외 공항 라운지 서비스(기타국가)_라운지키]\n• 중국, 싱가포르, 태국, 대만, 말레이시아 등 라운지를 연 2회 무료 이용가능\n * 대상 라운지는 JCB 홈페이지 참조\n \nShopping : 쇼핑서비스\n[면세점 할인 서비스]\n• 동화면세점 : 15% 현장 할인 전용 쿠폰 지급\n• 현대백화점면세점(무역센터점, 동대문점, 인천공항(T1, T2)\n     : 온·오프라인 5~15% 할인 혜택 멤버십 카드 발급\n• 신라 아이파크 면세점 : 오프라인 전용 5~15% 할인 혜택 골드카드 발급\nConcierge : 컨시어지서비스\n[JCB 컨시어지]\n• JCB 프리미엄 카드 회원을 위한 컨시어지 서비스 제공\n \n* 한국소재 시 02-755-4977(9:00~18:00, 일요일 및 공휴일 휴무)\n \n   해외소재 시 각국 전화번호는 JCB 홈페이지 참조\n \n* 한국컨시어지 데스크에서는 프리미엄 서비스에 관한 안내만 가능\n \n   그 외의 각종 문의 및 예약 대행 관련문의는 해당 해외 컨시어지 데스크로 문의\nGolf : 골프서비스\n[해외(일본) 골프 코스 우대 서비스]\n• 일본의 각종 유명 경기가 개최되는 코스에서 우대 서비스 제공\n * 코스 및 코스 별 서비스는 JCB 홈페이지 참조\n \n정상가 5~20% 할인 (~3.31)\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:49.506204+00	SYSTEM	2026-11-03 05:20:49.506204+00	SYSTEM
20261103_000013	1	20261103_000050	1	\N	BODY	1	3114	Mastercard\nPlatinum\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nMastercard Platinum 공통서비스\n· LANE4 AIR 서비스 3만원 할인 (왕복 예약 시 총 6만원 할인)\nHotel\nAirport\n· Trip.com 호텔 6%, 항공 3%, 액티비티 5% 할인\n· Agoda.com 8% 할인 (최대 USD 30),\n  (예약: 26.1.1~26.3.31 / 숙박: 26.1.1~26.12.31)\n· Hotels.com 8% 할인 (최대 USD 50),\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Expedia.com 8% 할인 (최대 10만원),\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Rakuten Travel 10% 할인 (최대 USD 30),\n  (예약: 26.1.1~26.12.30 / 숙박: 26.1.1~27.2.28)\n· Qatar Airways 항공권 최대 10% 할인\n· On Vacation 럭셔리호텔/크루즈 상품 5% 할인\n· Kkday 티켓/교통/액티비티 5% 할인, \n  해외투어/eSIM 10% 할인 (최대 USD 10),\n  (예약: 26.1.1~26.12.31 / 여행: 26.1.1~27.3.31)\n· Oh Show 60분 자유의 여신상 크루즈 티켓 1+1,\n  뉴욕 브로드웨이 뮤지컬 티켓 3% 할인, \n  라스베가스 쇼 및 하와이 태양의서커스 티켓 3% 할인\n· 제주도닷컴 패키지 5%, 렌터카 12%, 국내선 항공권 발권대행수수료 무료\n· Europcar 최대 15% 할인\n· 롯데렌터카 최대 제주 90%, 내륙 65% 할인 제공\n· Hertz 렌트 예약 시 10% 할인, 멤버십 무료 가입\n· 짐캐리 최대 20% 할인\n· Airalo eSIM 최대 20% 할인 (최대 USD 100)\n· 와이드모바일 와이파이도시락 15%, 도시락 eSIM/USIM 10% 할인\n· 유심사 해외 eSIM/USIM 20% 할인\nTravel\n* 본 Mastercard Platinum 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용 약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 서비스는 Mastercard 에서 제공하는 서비스로 , 프리미엄 서비스에 대한 구체적 내용, 적용기준 및 \n   유의사항 등은 http://www.mastercard.co.kr → ‘Premium Mastercard Services’에서 \n   사전에 반드시 확인하시기 바랍니다.\n* 본 Mastercard Platinum 서비스는 기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지\n   제공됩니다.\n서비스\n내용\n· 국내 특급호텔(약 39여개) F&B 5~15% 할인\n· 국내 특급호텔(약 43여개) 객실/패키지 5~50% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약 15여개) 스파 10~20% 할인\n· Trump Hotels 10% 할인 \n· Outrigger Hotels and Resorts 5% 할인\n· KA LA’I Waikiki Beach, LXR Hotels & Resorts 10% 할인 및 조식 제공\n· 코타키나발루 수트라하버 리조트 클럽 및 스위트 객실 25% 할인, \n  골드 카드 10% 할인\n· 신라면세점 골드플러스 멤버십 제공\n   (오프라인 최대 15%, 온라인 최대 20% 할인,\n    인터넷점 S.Rewards 7,000P 제공)\n· 신세계면세점 골드 멤버십 제공 (최대 15% 할인)\n· 트래블메이트 캐리어/여행용품 12% 추가 할인\n· 해외 프리미엄 아울렛 VIP 패스 제공 (10% 할인)\n· 몽쥬약국 구매 금액별 10~15% 할인 및 최대 15% 면세 혜택\n· Mastercard E-Commerce Protection 해외 온라인 직구 보험 \n   연간 최대 23만원 보상 \nShopping\n· 15개국 48개 골프장 그린피 25% 할인 (연 4회), (~6.30)\n· 코타키나발루 수트라하버 리조트 골프&컨트리클럽 그린피 본인 면제\n· LANE4 Golf 골프장 이동 서비스 5만원 할인\n· Car up 프리미엄 카 케어 서비스 20% 할인\n· 내셔널지오그래픽 트래블러 정기구독 결제 20% 할인\nGolf\nLife\n서비스\n내용\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-003747호 (2026.03.20) / 준법심의 L-26-0342 (2026.02.04) / VI 260327-33\n* 아래의 Mastercard Platinum 서비스는 Mastercard Platinum 등급 카드 소지자에게 공통으로 제공됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:52.903041+00	SYSTEM	2026-11-03 05:20:52.903041+00	SYSTEM
20261103_000013	2	20261103_000051	2	\N	BODY	1	4732	Mastercard\nPlatinum01\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n  \n선택서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03757호 (2026.03.20) / 준법심의 L-26-0357 (2026.02.09) / VI 260327-34\nMastercard Platinum 선택서비스 중 특급호텔 발렛파킹, 인천공항 발렛파킹, 공항라운지 입장 서비스를 하나카드에서 제공합니다.\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 발렛파킹 서비스는 본인 차량에 한해 제공되는 것을 원칙으로 합니다.\n   (타인 차량에는 서비스가 제공되지 않습니다.) \n- 호텔 영업장을 이용하지 않을 경우 일부 호텔에서는 발렛파킹 비용 및 주차료가 청구될 수 있습니다.\n- 1일 2~3시간 이내의 주차비용이 발렛파킹 서비스에 포함되어 있습니다. (일부 호텔 제외)\n- 레스케이프 호텔(30,000원 이상), 호텔 코리아나(25,000원 이상), 파크하얏트 서울(20,000원 이상)의 \n   호텔 영업장(당일 영수증) 제시 시 무료 발렛파킹 서비스 이용이 가능합니다. \n   영수증 미지참 시 제휴 서비스 이용은 제한되며, 발렛파킹 서비스 이용 요금 및 별도의 주차료는 \n   고객이 호텔에 직접 지불 하셔야 합니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n특급호텔 발렛파킹 서비스\n서비스혜택\n•국내 주요 특급호텔 무료 발렛파킹 서비스 제공 \n- 호텔 발렛파킹 부스에 서비스 요청 후 주차권 수령\n- 차량 인수 시 발렛파킹 부스에 주차권과 마스터카드 제시\n- 호텔 직원 서비스 대상카드 조회\n이용방법\n이용조건\n•호텔 통합 월 3회 서비스 제공\n•내 맘대로 쁨 카드, CLUB CEO 카드, CLUB SK 카드,\n CLUB SK Point 카드는 지난달 (1일~말일) 국내외 일시불 할부 \n 30만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 30만원 미만 시에도 서비스 제공)\n•하나골드클럽멤버스Ⅱ카드는 지난달 (1일~말일) 국내외 일시불 할부 \n 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 50만원 미만 시에도 서비스 제공)\n이용조건\n이용방법\n서비스혜택\n인천공항 발렛파킹 서비스\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 여객터미널 3층 승용차전용도로에서 5분 이상 정차 시 과태료가 부가될 수 있습니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n- 본 서비스는 인천국제공항 공식 주차대행 업체인 제1여객터미널 : ㈜맥서브, \n   제2여객터미널 : 아마노코리아에 의해 제공되니 서비스 이용 시 공식 주차대행 업체인지 \n   확인하시기 바랍니다.\n인천공항 무료 발렛파킹 서비스 제공 제 1,2 여객터미널\n•통합 월 3회 서비스 제공\n•내 맘대로 쁨 카드, CLUB CEO 카드, CLUB SK 카드,\n CLUB SK Point 카드는 지난달 (1일~말일) 국내외 일시불 할부 \n 30만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 30만원 미만 시에도 서비스 제공)\n•하나골드클럽멤버스Ⅱ카드는 지난달 (1일~말일) 국내외 일시불 할부 \n 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 50만원 미만 시에도 서비스 제공)\n유의사항\n- 라운지 이용과 관련한 문의는 마스터카드 라운지 서비스 데스크를 통해 서비스를 안내 받을 수 있습니다.\n- 마스터카드 라운지 서비스 데스크 : 02-3272-3731 (운영시간: 월~금, 09:00-18:00)\n인천공항\n- 스카이허브 라운지 제1여객터미널 동편\n- 스카이허브 라운지 제1여객터미널 서편\n- 스카이허브 라운지 제1여객터미널 탑승동\n김포공항\n김해공항\n- 스카이허브 라운지 김포공항 국제선 청사\n구분\n대상 라운지\n- 스카이허브 라운지 김해공항 국제선 청사\n대상 호텔\n지방\n지역\n서울\n그랜드 워커힐 서울\n그랜드 하얏트 서울\n스위스 그랜드 호텔\n노보텔 앰배서더 서울 강남\n비스타 워커힐 서울\n서울 드래곤 시티\n서울 신라 호텔\n메이필드 호텔\n레스케이프 호텔\n호텔 코리아나\n서울가든 호텔\n파크하얏트서울\n그랜드 하얏트 인천\n파크 하얏트 부산\n호텔 오노마\n그랜드 머큐어 앰배서더 창원\n공항 라운지 입장 서비스\n서비스혜택\n•마스터카드 제휴 라운지 무료 이용 서비스 제공 \n이용조건\n•라운지 통합 일 1회 , 연 2회 서비스 제공 본인에 한해 무료\n•내 맘대로 쁨 카드, CLUB CEO 카드, CLUB SK 카드,\n CLUB SK Point 카드는 지난달 (1일~말일) 국내외 일시불 할부 \n 30만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 30만원 미만 시에도 서비스 제공)\n•하나골드클럽멤버스Ⅱ카드는 지난달 (1일~말일 국내외 일시불 할부 \n 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 50만원 미만 시에도 서비스 제공)\n이용방법\n•라운지 안내 데스크에서 보딩패스와 마스터카드 제시 및 서비스 대상\n 카드여부 확인 후 무료 입장\n제1여객터미널\n제2여객터미널\n주차 시 : ① 지하 1층 단기주차장 A구역으로 이동 후 Maxerve 유니폼 착용 \n                   공식 주차대행 직원에게 발렛파킹 요청\n              ② 모바일 접수증 문자 발송 (카카오톡/ MMS 문자발송, \n                   문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시 : ① 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 \n                   (지하 3층 A32구역 또는 H38구역)\n              ② 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 \n                   차량 인수\n              ③ 차량 인수 후 주차요금 고객이 별도 정산\n주차 시 : ① 제2여객터미널 지하1층 서편 단기 주차장으로 진입\n              ② 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ③ 모바일 접수증 문자 발송 (알림톡/문자메세지 발송)\n출차 시 : ① 입국 후 접수증 안내에 따라 단기주차장 지하1층 \n                   동편 210번 앞 고객대기실로 이동\n              ② 출차장 정산소에서 프리미엄 마스터카드 제시 후 \n                  서비스 이용가능 여부 확인\n              ③ 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n아래 대상 카드 발급 시 Mastercard Platinum 01 선택서비스와 \nMastercard Platinum 공통서비스가 제공됩니다.\n- 하나골드클럽멤버스Ⅱ카드\n- 내 맘대로 쁨 카드\n- CLUB CEO 카드\n- CLUB SK 카드\n- CLUB SK Point 카드\n- Premium 카드\n- Premium Biz TR 카드\n- CLUB Primus 카드\n- SECRET Classic 카드\n- 스마트포인트 카드\n- 중앙일보카드\n- NEW 하나가족사랑카드\n* Mastercar 프리미엄 서비스의 서비스의 상세한 내용은 Mastercard 홈페이지\n  (http://www.mastercard.com/kr)를 통해 확인하시기 바랍니다. \n* 본 Mastercard 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 Mastercard Platinum 서비스는 기간이 명시되지 않는 한 \n   2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:52.903041+00	SYSTEM	2026-11-03 05:20:52.903041+00	SYSTEM
20261103_000014	1	20261103_000052	1	\N	BODY	1	3114	Mastercard\nPlatinum\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nMastercard Platinum 공통서비스\n· LANE4 AIR 서비스 3만원 할인 (왕복 예약 시 총 6만원 할인)\nHotel\nAirport\n· Trip.com 호텔 6%, 항공 3%, 액티비티 5% 할인\n· Agoda.com 8% 할인 (최대 USD 30),\n  (예약: 26.1.1~26.3.31 / 숙박: 26.1.1~26.12.31)\n· Hotels.com 8% 할인 (최대 USD 50),\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Expedia.com 8% 할인 (최대 10만원),\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Rakuten Travel 10% 할인 (최대 USD 30),\n  (예약: 26.1.1~26.12.30 / 숙박: 26.1.1~27.2.28)\n· Qatar Airways 항공권 최대 10% 할인\n· On Vacation 럭셔리호텔/크루즈 상품 5% 할인\n· Kkday 티켓/교통/액티비티 5% 할인, \n  해외투어/eSIM 10% 할인 (최대 USD 10),\n  (예약: 26.1.1~26.12.31 / 여행: 26.1.1~27.3.31)\n· Oh Show 60분 자유의 여신상 크루즈 티켓 1+1,\n  뉴욕 브로드웨이 뮤지컬 티켓 3% 할인, \n  라스베가스 쇼 및 하와이 태양의서커스 티켓 3% 할인\n· 제주도닷컴 패키지 5%, 렌터카 12%, 국내선 항공권 발권대행수수료 무료\n· Europcar 최대 15% 할인\n· 롯데렌터카 최대 제주 90%, 내륙 65% 할인 제공\n· Hertz 렌트 예약 시 10% 할인, 멤버십 무료 가입\n· 짐캐리 최대 20% 할인\n· Airalo eSIM 최대 20% 할인 (최대 USD 100)\n· 와이드모바일 와이파이도시락 15%, 도시락 eSIM/USIM 10% 할인\n· 유심사 해외 eSIM/USIM 20% 할인\nTravel\n* 본 Mastercard Platinum 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용 약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 서비스는 Mastercard 에서 제공하는 서비스로 , 프리미엄 서비스에 대한 구체적 내용, 적용기준 및 \n   유의사항 등은 http://www.mastercard.co.kr → ‘Premium Mastercard Services’에서 \n   사전에 반드시 확인하시기 바랍니다.\n* 본 Mastercard Platinum 서비스는 기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지\n   제공됩니다.\n서비스\n내용\n· 국내 특급호텔(약 39여개) F&B 5~15% 할인\n· 국내 특급호텔(약 43여개) 객실/패키지 5~50% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약 15여개) 스파 10~20% 할인\n· Trump Hotels 10% 할인 \n· Outrigger Hotels and Resorts 5% 할인\n· KA LA’I Waikiki Beach, LXR Hotels & Resorts 10% 할인 및 조식 제공\n· 코타키나발루 수트라하버 리조트 클럽 및 스위트 객실 25% 할인, \n  골드 카드 10% 할인\n· 신라면세점 골드플러스 멤버십 제공\n   (오프라인 최대 15%, 온라인 최대 20% 할인,\n    인터넷점 S.Rewards 7,000P 제공)\n· 신세계면세점 골드 멤버십 제공 (최대 15% 할인)\n· 트래블메이트 캐리어/여행용품 12% 추가 할인\n· 해외 프리미엄 아울렛 VIP 패스 제공 (10% 할인)\n· 몽쥬약국 구매 금액별 10~15% 할인 및 최대 15% 면세 혜택\n· Mastercard E-Commerce Protection 해외 온라인 직구 보험 \n   연간 최대 23만원 보상 \nShopping\n· 15개국 48개 골프장 그린피 25% 할인 (연 4회), (~6.30)\n· 코타키나발루 수트라하버 리조트 골프&컨트리클럽 그린피 본인 면제\n· LANE4 Golf 골프장 이동 서비스 5만원 할인\n· Car up 프리미엄 카 케어 서비스 20% 할인\n· 내셔널지오그래픽 트래블러 정기구독 결제 20% 할인\nGolf\nLife\n서비스\n내용\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-003747호 (2026.03.20) / 준법심의 L-26-0342 (2026.02.04) / VI 260327-33\n* 아래의 Mastercard Platinum 서비스는 Mastercard Platinum 등급 카드 소지자에게 공통으로 제공됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:57.765029+00	SYSTEM	2026-11-03 05:20:57.765029+00	SYSTEM
20261103_000014	2	20261103_000053	2	\N	BODY	1	4752	Mastercard\nPlatinum04\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n  \n선택서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03876호 (2026.03.23) / 준법심의 L-26-0360 (2026.02.09) / VI 260330-33\nMastercard Platinum 선택서비스 중 특급호텔 발렛파킹, 인천/김포공항 발렛파킹 \n서비스를 하나카드에서 제공합니다.\n특급호텔 발렛파킹 서비스\n서비스혜택\n•국내 주요 특급호텔 무료 발렛파킹 서비스 제공 \n- 호텔 발렛파킹 부스에 서비스 요청 후 주차권 수령\n- 차량 인수 시 발렛파킹 부스에 주차권과 마스터카드 제시\n- 호텔 직원 서비스 대상카드 조회\n이용방법\n이용조건\n•호텔 통합 월 3회 서비스 제공\n•CLUB NOBLE 카드는 지난달(1일~말일) 국내외 일시불/할부\n    30만원 이상 이용 시 서비스 제공 (최초 카드 사용등록 후 다음달 \n    말일까지는 지난달 카드 이용금액 30만원 미만 시에도 서비스 제공)\n•CLUB Leaders 3 카드는 지난달(1일~말일) 국내 일시불/할부\n    50만원 이상 이용 시 서비스 제공 (최초 카드 사용등록 후 다음달\n    말일까지는 지난달 카드 이용금액 50만원 미만 시에도 서비스 제공)\n이용조건\n서비스혜택\n인천공항 발렛파킹 서비스\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 여객터미널 3층 승용차전용도로에서 5분 이상 정차 시 과태료가 부가될 수 있습니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n- 본 서비스는 인천국제공항 공식 주차대행 업체인 제1여객터미널 : ㈜맥서브, \n   제2여객터미널 : 아마노코리아에 의해 제공되니 서비스 이용 시 공식 주차대행 업체인지 \n   확인하시기 바랍니다.\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 발렛파킹 서비스 제공 시간은 5시부터 21시이나, 출차 서비스는 24시간 제공됩니다.\n- 본 서비스는 주차대행 업체인 ㈜하이파킹에 의해 제공되니 서비스 이용 시 공식\n   주차대행업체인지 확인하시기 바랍니다.\n인천공항 무료 발렛파킹 서비스 제공 (제 1,2 여객터미널)\n•인천/김포공항 통합 월 7회 서비스 제공\n•CLUB Leaders 3 카드에 한하여 서비스 제공\n    (CLUB NOBLE은 서비스 미제공)\n•CLUB Leaders 3 카드는 지난달(1일~말일) 국내외 일시불/할부\n    50만원 이상 이용 시 서비스 제공 (최초 카드 사용등록 후 다음달 \n    말일까지는 지난달 카드 이용금액 50만원 미만 시에도 서비스 제공)\n대상 호텔\n지방\n지역\n서울\n그랜드 워커힐 서울\n그랜드 하얏트 서울\n스위스 그랜드 호텔\n메이필드 호텔\n비스타 워커힐 서울\n서울 드래곤 시티\n서울 호텔 신라\n레스케이프 호텔\n호텔 코리아나\n콘래드 서울\n더 플라자 호텔\n몬드리안 서울 이태원\n파크하얏트 서울\nJW메리어트 호텔 서울\n노보텔 앰배서더 서울 강남\n서울 가든 호텔\n앰배서더 서울 품만 호텔\n오크우드 프리미어 코엑스\n메리어트 이그제큐티브 아파트먼트\n반얀트리 클럽 앤 스파 서울\n그랜드 하얏트 인천\n파크 하얏트 부산\n호텔 오노마 대전\n그랜드 머큐어 앰배서더 창원\n이용방법\n제1여객터미널\n제2여객터미널\n주차 시 : ① 지하 1층 단기주차장 A구역으로 이동 후 Maxerve 유니폼 착용 \n                   공식 주차대행 직원에게 발렛파킹 요청\n              ② 모바일 접수증 문자 발송 (카카오톡/ MMS 문자발송, \n                   문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시 : ① 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 \n                   (지하 3층 A32구역 또는 H38구역)\n              ② 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 \n                   차량 인수\n              ③ 차량 인수 후 주차요금 고객이 별도 정산\n주차 시 : ① 제2여객터미널 지하1층 서편 단기 주차장으로 진입\n              ② 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ③ 모바일 접수증 문자 발송 (알림톡/문자메세지 발송)\n출차 시 : ① 입국 후 접수증 안내에 따라 단기주차장 지하1층 \n                   동편 210번 앞 고객대기실로 이동\n              ② 출차장 정산소에서 프리미엄 마스터카드 제시 후 \n                  서비스 이용가능 여부 확인\n              ③ 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n국내선 \n이용방법\n주차 시 : ① 국내선 청사 2층 우측 하늘색 라인따라 진입 후, 주황색 유니폼 \n                   착용 공식 주차대행 직원에게 발렛파킹 요청\n              ② 차량 상태 점검 후 차량 인도 및 차량 보관증 수령\n출차 시 : ① 출발지 항공기 탑승 전 차량보관증에 기재된 연락처로 출차 요청\n              ② 차량 인수 시, 접수증과 프리미엄 마스터카드 제시 후 서비스\n                   이용 가능 여부 확인\n              ③ 차량 인수 후 출차 시 고객이 주차요금 별도 정산\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 발렛파킹 서비스는 본인 차량에 한해 제공되는 것을 원칙으로 합니다.\n   (타인 차량에는 서비스가 제공되지 않습니다.) \n- 호텔 영업장을 이용하지 않을 경우 일부 호텔에서는 발렛파킹 비용 및 주차료가 청구될 수 있습니다.\n- 1일 2~3시간 이내의 주차비용이 발렛파킹 서비스에 포함되어 있습니다. (일부 호텔 제외)\n- 오크우드 프리미어 코엑스센터는 만차 시 3시간 무료 주차권이 제공되며 이용 한도가 차감됩니다.\n- JW메리어트 호텔 서울(50,000원 이상), 레스케이프 호텔(30,000원 이상), 몬드리안 서울 이태원 및 \n   호텔 코리아나(25,000원 이상), 파크하얏트 서울(20,000원 이상)의 호텔 영업장(당일 영수증) 제시 시 \n   무료 발렛파킹 서비스 이용이 가능합니다. \n   영수증 미지참 시 제휴 서비스 이용은 제한되며, 발렛파킹 서비스 이용요금 및 별도의 주차료는 고객이 \n   호텔에 직접 지불 하셔야 합니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n서비스혜택\n•김포공항 무료 발렛파킹 서비스 제공 (국내선)\n이용조건\n•인천/김포공항 통합 월 7회 서비스 제공\n•CLUB Leaders 3 카드에 한하여 서비스 제공\n    (CLUB NOBLE은 서비스 미제공)\n•CLUB Leaders 3 카드는 지난달(1일~말일) 국내외 일시불/할부\n    50만원 이상 이용 시 서비스 제공 (최초 카드 사용등록 후 다음달 \n    말일까지는 지난달 카드 이용금액 50만원 미만 시에도 서비스 제공)\n김포공항 라운지 입장 서비스\nCLUB NOBLE\nCLUB Leaders 3\n아래 대상 카드 발급 시 Mastercard Platinum04 선택서비스와 \nMastercard Platinum 공통서비스가 제공됩니다.\n* Mastercar 프리미엄 서비스의 서비스의 상세한 내용은 Mastercard 홈페이지\n  (http://www.mastercard.com/kr)를 통해 확인하시기 바랍니다. \n* 본 Mastercard 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 Mastercard Platinum 서비스는 기간이 명시되지 않는 한 \n   2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n상품유형\nMastercard World\nPlatinum04\n대상카드\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:20:57.765029+00	SYSTEM	2026-11-03 05:20:57.765029+00	SYSTEM
20261103_000015	1	20261103_000054	1	\N	BODY	1	3329	Mastercard\nWorld\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nMastercard World 공통서비스\n· LANE4 AIR 서비스 3만원 할인 (왕복 예약 시 총 6만원 할인)\nHotel\nAirport\n· KALPAK 제휴 호텔 예약 시 룸 업그레이드, 2인 무료 조식, \n   Room Creadit, Early Check in & Late Check out 서비스\n· Trip.com 호텔 15%, 항공 3%, 액티비티 5% 할인\n· Agoda.com 10% 할인 (최대 USD 30)\n  (예약: 26.1.1~26.3.31 / 숙박: 26.1.1~26.12.31)\n· Hotels.com 8% 할인 (최대 USD 50)\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Expedia.com 8% 할인 (최대 10만원)\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Rakuten Travel 20% 할인 (최대 USD 100)\n  (예약: 26.1.1~26.12.30 / 숙박: 26.1.1~27.2.28)\n· Qatar Airways 항공권 최대 10% 할인\n· 헤외 럭셔리 크루즈 셀렉션 7% 할인 또는 크루즈 캐시 제공 또는 \n   인천국제공항 밴서비스 제공\n· On Vacation 럭셔리호텔/크루즈 상품 5% 할인\n· Kkday 티켓/교통/액티비티 5% 할인, 해외투어/eSim 10% 할인\n  (최대 USD 10) (예약: 26.1.1~26.12.31 / 여행: 26.1.1~27.3.31)\n· Oh Show 60분 자유의 여신상 크루즈 티켓 1+1,\n   뉴욕 브로드웨이 뮤지컬 티켓 3% 할인, \n   라스베가스 쇼 및 하와이 태양의서커스 티켓 3% 할인\nTravel\nTravel\n* 본 Mastercard World 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용 약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 서비스는 Mastercard 에서 제공하는 서비스로 , 프리미엄 서비스에 대한 구체적 내용, 적용기준 및 \n   유의사항 등은 http://www.mastercard.co.kr → ‘Premium Mastercard Services’에서 \n   사전에 반드시 확인하시기 바랍니다.\n* 본 Mastercard World 서비스는 기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 국내 특급호텔(약 42여개) F&B 5~15% 할인\n· 국내 특급호텔(약 44여개) 객실/패키지 5~50% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약16여개) 스파 10~20% 할인\n· Trump Hotels 10% 할인 \n· Outrigger Hotels and Resorts 5% 할인\n· KA LA’I Waikiki Beach, LXR Hotels & Resorts 10% 할인 및 조식 제공\n· 코타키나발루 수트라하버 리조트 클럽 및 스위트 객실 25% 할인, \n   골드 카드 10% 할인\n· HoteLux 엘리트 멤버십 12개월 무료 제공 및 1,000 포인트 제공\n· 신라면세점 블랙 등급 혜택 제공\n  (온/오프라인 최대 20% 할인, 인터넷점 S.Rewards 10,000P 제공)\n· 신세계면세점 블랙 멤버십 제공 (최대 20% 할인)\n· 트래블메이트 캐리어/여행용품 12% 추가 할인\n· 해외 프리미엄 아울렛 VIP 패스 제공 (10% 할인)\n· 몽쥬약국 구매 금액별 10~15% 할인 및 최대 15% 면세혜택\n· Mastercard E-Commerce Protection 해외 온라인 직구 보험 \n  연간 최대 115만원 보상 \nShopping\n· 15개국 48개 골프장 그린피 50% 할인 (연 4회), (~6.30)\n· 코타키나발루 수트라하버 리조트 골프&컨트리클럽 그린피 본인 면제\n· LANE4 Golf 골프장 이동 서비스 5만원 할인\n· Car up 프리미엄 카 케어 서비스 30% 할인\n· 내셔널지오그래픽 트래블러 정기구독 결제 20% 할인\nGolf\nLife\n서비스\n내용\n· 제주도닷컴 패키지 5%, 렌터카 12%, 국내선 항공권 발권대행수수료 무료\n· Europcar 최대 15% 할인\n· 롯데렌터카 최대 제주 90%, 내륙 65% 할인 제공\n·  Hertz 렌트 예약 시 10% 할인, 멤버십 무료 가입\n· 짐캐리 최대 20% 할인(단, 최초 이용 시 1회 무료, 짐1 개 편도기준)\n· 와이드모바일 와이파이도시락 15%, 도시락 eSIM/USIM 10% 할인\n· Airalo eSIM 최대 20% 할인 (최대 USD 100)\n· 유심사 해외 eSIM/ USIM 20% 할인\n· AIG 손해보험 해외 여행자 보험 제공\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03840호 (2026.03.23) / 준법심의 L-26-0344 (2026.02.04) / VI 260326-31\n* 아래의 Mastercard World 서비스는 Mastercard World 등급카드 소지자에게 공통으로 제공됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:03.19387+00	SYSTEM	2026-11-03 05:21:03.19387+00	SYSTEM
20261103_000015	2	20261103_000055	2	\N	BODY	1	4568	Mastercard World 02 선택서비스\nMastercard World 02 선택서비스 중 특급호텔 발렛파킹, 인천/김포공항 발렛파킹을 하나카드에서 제공합니다.\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 발렛파킹 서비스는 본인 차량에 한해 제공되는 것을 원칙으로 합니다.\n   (타인 차량에는 서비스가 제공되지 않습니다.) \n- 호텔 영업장을 이용하지 않을 경우 일부 호텔에서는 발렛파킹 비용 및 주차료가 청구될 수 있습니다.\n- 1일 2~3시간 이내의 주차비용이 발렛파킹 서비스에 포함되어 있습니다. (일부 호텔 제외)\n- 오크우드 프리미어 코엑스센터는 만차 시 3시간 무료 주차권이 제공되며 이용한도가 차감됩니다.\n- JW 메리어트 서울(50,000원 이상), 레스케이프 호텔 및 JW 메리어트 동대문 스퀘어(30,000원 이상), \n   몬드리안 서울 이태원 및 호텔 코리아나(25,000원 이상), 파크하얏트 서울(20,000원 이상)의 \n   호텔 영업장(당일 영수증) 제시 시 무료 발렛파킹 서비스 이용이 가능합니다. \n   영수증 미지참 시 제휴서비스 이용은 제한되며, 발렛파킹 서비스 이용요금 및 별도의 주차료는 \n   고객이 호텔에 직접 지불 하셔야 합니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n특급호텔 발렛파킹 서비스\n서비스혜택\n국내 주요 특급호텔 무료 발렛파킹 서비스 제공 \n- 호텔 발렛파킹 부스에 서비스 요청 후 주차권 수령\n- 차량 인수 시 발렛파킹 부스에 주차권과 마스터카드 제시\n- 호텔 직원 서비스 대상카드 조회\n이용방법\n이용조건\n- 호텔 통합 월 7회 서비스 제공\n- CLUB Leaders 5,8,10,15 카드는 \n   지난달(1일~말일) 국내외 일시불/할부 50만원 이용 시 서비스 제공\n   (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 이용금액 \n   50만원 미만 시에도 서비스 제공)\n이용조건\n이용방법\n서비스혜택\n인천/김포공항 발렛파킹 서비스\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 여객터미널 3층 승용차전용도로에서 5분 이상 정차 시 과태료가 부가될 수 있습니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n- 인천공항 발렛파킹 서비스 운영시간은 24시간이며, 김포공항 발렛파킹 서비스 제공시간은 \n    5시부터 21시이나, 출차 서비스는 24시간 제공됩니다.\n- 본 서비스는 공식 주차대행 업체인 인천공항 제1여객터미널 : ㈜맥서브,\n   제2여객터미널 : 아마노코리아, 김포공항 국제선 : ㈜하이파킹 에 의해 제공되니 \n   서비스 이용 시 공식 주차대행업체인지 확인하시기 바랍니다.\n인천공항 제 1,2여객터미널 및 김포공항 국내선 \n무료 발렛파킹 서비스 제공\n- 호텔 통합 월 7회 서비스 제공\n- CLUB Leaders 5,8,10,15 카드는 \n   지난달(1일~말일) 국내외 일시불/할부 50만원 이용 시 서비스 제공\n   (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 이용금액 \n   50만원 미만 시에도 서비스 제공)\n대상 호텔\n지방\n지역\n서울\n앰배서더 서울 풀만\n그랜드 워커힐 서울 \n그랜드 하얏트 서울\n스위스 그랜드 호텔\n더 플라자 \n \n호텔 코리아나\n파크 하얏트 서울\n메이필드 호텔\n콘래드 서울\n호텔 리베라 청담\n \n레스케이프 호텔\n비스타 워커힐 서울\nJW 메리어트 동대문 스퀘어\nJW 메리어트 서울\n몬드리안 서울 이태원\n반얀트리 클럽앤스파 서울\n서울 가든 호텔\n서울 신라 호텔\n서울 드래곤 시티\n소피텔 앰배서더 서울\n \n \n노보텔 앰배서더 서울 강남\n노보텔 앰배서더 동대문\n글래드 강남 코엑스 센터\n더블리티 by 힐튼 판교\n코트야드 메리어트 서울 타임스퀘어\n르 메르디앙&목시 서울 명동\n오크우드 프리미어 코엑스\n메리어트 이그제큐티브\n아파트먼트 서울\n호텔 나루 서울 엠갤러리 \n호텔 오노마 대전\n인터불고 대구\n소노캄 여수\n소노캄 고양\n윈덤그랜드 부산\n그랜드 하얏트 인천\n파라다이스 부산 호텔\n그랜드조선부산\n세인트존스 호텔\n파크하얏트 부산\n힐튼 경주\n대구 메리어트 호텔\nJW 메리어트 제주 리조트&스파 \n파라다이스 시티 호텔\n그랜드머큐어엠배서더 창원\n인스파이어 엔터테이먼트 리조트\n인천공항\n제1여객터미널\n인천공항\n제2여객터미널\n주차 시 : ① 지하1층 단기주차장 A구역으로 이동 후 Maxerve 유니폼 착용\n                   공식 주차대행 직원에게 발렛파킹 요청\n              ② 모바일 접수증 문자 발송 (카카오톡/ MMS 문자발송, \n                   문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시 : ① 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 \n                   (지하 3층 A32구역 또는 H38구역)\n              ② 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 \n                   차량 인수\n              ③ 차량 인수 후 주차요금 고객이 별도 정산\n주차 시 : ① 제 2여객터미널 지하1층 서편 단기 주차장으로 진입\n              ② 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ③ 모바일 접수증 문자 발송 (알림톡/문자메세지 발송)\n출차 시 : ① 입국 후 접수증 안내에 따라 단기주차장 지하 1층 \n                   동편 210번 앞 고객대기실로 이동\n              ② 출차장 정산소에서 프리미엄 마스터카드 제시 후 \n                  서비스 이용가능 여부 확인\n              ③ 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n김포공항\n국내선\n주차 시 : ① 국내선 청사 2층 우측 하늘색 라인따라 진입 후, \n                    주황색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ② 차량 상태 점검 후 차량 인도 및 차량 보관증 수령\n출차 시 : ① 출발지 항공기 탑승 전 차량보관증에 기재된 연락처로 출차 요청\n              ② 차량 인수 시, 접수증과 프리미엄 마스터카드 제시 후 \n                   서비스 이용 가능 여부 확인\n              ③ 차량 인수 후 출차 시 고객이 주차요금 별도 정산\n* Mastercard 프리미엄 서비스의 상세한 내용은 Mastercard 홈페이지 \n   (http://www.mastercard.com/kr)를 통해 확인하시기 바랍니다.\n* 본 Mastercard 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품안내장,  \n   이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 Mastercard 프리미엄 서비스는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n상품유형\nMastercard World 02\n대상카드\nCLUB Leaders 5\nCLUB Leaders 8\nCLUB Leaders 10\nCLUB Leaders 15\n아래 대상 카드 발급 시 Mastercard World 02 선택서비스와 \nMastercard World 공통서비스가 제공됩니다.\nMastercard\nWorld 02\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n  \n선택서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03777호 (2026.03.20) / 준법심의 L-26-0363 (2026.02.09) / VI 260326-33\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:03.19387+00	SYSTEM	2026-11-03 05:21:03.19387+00	SYSTEM
20261103_000016	1	20261103_000056	1	\N	BODY	1	3329	Mastercard\nWorld\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nMastercard World 공통서비스\n· LANE4 AIR 서비스 3만원 할인 (왕복 예약 시 총 6만원 할인)\nHotel\nAirport\n· KALPAK 제휴 호텔 예약 시 룸 업그레이드, 2인 무료 조식, \n   Room Creadit, Early Check in & Late Check out 서비스\n· Trip.com 호텔 15%, 항공 3%, 액티비티 5% 할인\n· Agoda.com 10% 할인 (최대 USD 30)\n  (예약: 26.1.1~26.3.31 / 숙박: 26.1.1~26.12.31)\n· Hotels.com 8% 할인 (최대 USD 50)\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Expedia.com 8% 할인 (최대 10만원)\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Rakuten Travel 20% 할인 (최대 USD 100)\n  (예약: 26.1.1~26.12.30 / 숙박: 26.1.1~27.2.28)\n· Qatar Airways 항공권 최대 10% 할인\n· 헤외 럭셔리 크루즈 셀렉션 7% 할인 또는 크루즈 캐시 제공 또는 \n   인천국제공항 밴서비스 제공\n· On Vacation 럭셔리호텔/크루즈 상품 5% 할인\n· Kkday 티켓/교통/액티비티 5% 할인, 해외투어/eSim 10% 할인\n  (최대 USD 10) (예약: 26.1.1~26.12.31 / 여행: 26.1.1~27.3.31)\n· Oh Show 60분 자유의 여신상 크루즈 티켓 1+1,\n   뉴욕 브로드웨이 뮤지컬 티켓 3% 할인, \n   라스베가스 쇼 및 하와이 태양의서커스 티켓 3% 할인\nTravel\nTravel\n* 본 Mastercard World 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용 약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 서비스는 Mastercard 에서 제공하는 서비스로 , 프리미엄 서비스에 대한 구체적 내용, 적용기준 및 \n   유의사항 등은 http://www.mastercard.co.kr → ‘Premium Mastercard Services’에서 \n   사전에 반드시 확인하시기 바랍니다.\n* 본 Mastercard World 서비스는 기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 국내 특급호텔(약 42여개) F&B 5~15% 할인\n· 국내 특급호텔(약 44여개) 객실/패키지 5~50% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약16여개) 스파 10~20% 할인\n· Trump Hotels 10% 할인 \n· Outrigger Hotels and Resorts 5% 할인\n· KA LA’I Waikiki Beach, LXR Hotels & Resorts 10% 할인 및 조식 제공\n· 코타키나발루 수트라하버 리조트 클럽 및 스위트 객실 25% 할인, \n   골드 카드 10% 할인\n· HoteLux 엘리트 멤버십 12개월 무료 제공 및 1,000 포인트 제공\n· 신라면세점 블랙 등급 혜택 제공\n  (온/오프라인 최대 20% 할인, 인터넷점 S.Rewards 10,000P 제공)\n· 신세계면세점 블랙 멤버십 제공 (최대 20% 할인)\n· 트래블메이트 캐리어/여행용품 12% 추가 할인\n· 해외 프리미엄 아울렛 VIP 패스 제공 (10% 할인)\n· 몽쥬약국 구매 금액별 10~15% 할인 및 최대 15% 면세혜택\n· Mastercard E-Commerce Protection 해외 온라인 직구 보험 \n  연간 최대 115만원 보상 \nShopping\n· 15개국 48개 골프장 그린피 50% 할인 (연 4회), (~6.30)\n· 코타키나발루 수트라하버 리조트 골프&컨트리클럽 그린피 본인 면제\n· LANE4 Golf 골프장 이동 서비스 5만원 할인\n· Car up 프리미엄 카 케어 서비스 30% 할인\n· 내셔널지오그래픽 트래블러 정기구독 결제 20% 할인\nGolf\nLife\n서비스\n내용\n· 제주도닷컴 패키지 5%, 렌터카 12%, 국내선 항공권 발권대행수수료 무료\n· Europcar 최대 15% 할인\n· 롯데렌터카 최대 제주 90%, 내륙 65% 할인 제공\n·  Hertz 렌트 예약 시 10% 할인, 멤버십 무료 가입\n· 짐캐리 최대 20% 할인(단, 최초 이용 시 1회 무료, 짐1 개 편도기준)\n· 와이드모바일 와이파이도시락 15%, 도시락 eSIM/USIM 10% 할인\n· Airalo eSIM 최대 20% 할인 (최대 USD 100)\n· 유심사 해외 eSIM/ USIM 20% 할인\n· AIG 손해보험 해외 여행자 보험 제공\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03840호 (2026.03.23) / 준법심의 L-26-0344 (2026.02.04) / VI 260326-31\n* 아래의 Mastercard World 서비스는 Mastercard World 등급카드 소지자에게 공통으로 제공됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:09.536855+00	SYSTEM	2026-11-03 05:21:09.536855+00	SYSTEM
20261103_000016	2	20261103_000057	2	\N	BODY	1	4923	Mastercard World 03 선택서비스\nMastercard World 03 선택서비스 중 특급호텔 발렛파킹, 인천/김포공항 발렛파킹을 하나카드에서 제공합니다.\n실적 제외 대상\n국세, 지방세, 수도/전기요금, 그외 공과금(우편요금, 여권발급비용, 과태료, 범칙금, 벌금, 국가/공공기관/\n공공단체가 부과하는 부담금), 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/건강보험료 \n납부금액, 스쿨뱅킹, 초 ·중 ·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트카드 구매, \n선불카드 및 선불전자지급수단(하나머니 등) 충전금액, 부동산임대료\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 발렛파킹 서비스는 본인 차량에 한해 제공되는 것을 원칙으로 합니다.\n   (타인 차량에는 서비스가 제공되지 않습니다.) \n- 호텔 영업장을 이용하지 않을 경우 일부 호텔에서는 발렛파킹 비용 및 주차료가 청구될 수 있습니다.\n- 1일 2~3시간 이내의 주차비용이 발렛파킹 서비스에 포함되어 있습니다. (일부 호텔 제외)\n- 오크우드 프리미어 코엑스센터는 만차 시 3시간 무료 주차권이 제공되며 이용한도가 차감됩니다.\n- JW 메리어트 서울(50,000원 이상), 레스케이프 호텔 및 JW 메리어트 동대문 스퀘어(30,000원 이상), \n   몬드리안 서울 이태원 및 호텔 코리아나(25,000원 이상), 파크하얏트 서울(20,000원 이상)의 \n   호텔 영업장(당일 영수증) 제시 시 무료 발렛파킹 서비스 이용이 가능합니다. \n   영수증 미지참 시 제휴서비스 이용은 제한되며, 발렛파킹 서비스 이용요금 및 별도의 주차료는 \n   고객이 호텔에 직접 지불 하셔야 합니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n특급호텔 발렛파킹 서비스\n서비스혜택\n국내 주요 특급호텔 무료 발렛파킹 서비스 제공 \n- 호텔 발렛파킹 부스에 서비스 요청 후 주차권 수령\n- 차량 인수 시 발렛파킹 부스에 주차권과 마스터카드 제시\n- 호텔 직원 서비스 대상카드 조회\n이용방법\n이용조건\n- 호텔 통합 월 2회 서비스 제공\n- 대상 카드로 지난달(1일~말일) 국내외 일시불/할부 50만원 이용 시 \n   서비스 제공 (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 \n   이용금액 50만원 미만 시에도 서비스 제공)\n이용조건\n이용방법\n서비스혜택\n인천/김포공항 발렛파킹 서비스\n실적 제외 대상\n국세, 지방세, 수도/전기요금, 그외 공과금(우편요금, 여권발급비용, 과태료, 범칙금, 벌금, 국가/공공기관/\n공공단체가 부과하는 부담금), 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/건강보험료 \n납부금액, 스쿨뱅킹, 초 ·중 ·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트카드 구매, \n선불카드 및 선불전자지급수단(하나머니 등) 충전금액, 부동산임대료\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 여객터미널 3층 승용차전용도로에서 5분 이상 정차 시 과태료가 부가될 수 있습니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n- 인천공항 발렛파킹 서비스 운영시간은 24시간이며, 김포공항 발렛파킹 서비스 제공시간은 \n    5시부터 21시이나, 출차 서비스는 24시간 제공됩니다.\n- 본 서비스는 공식 주차대행 업체인 인천공항 제1여객터미널 : ㈜맥서브,\n   제2여객터미널 : 아마노코리아, 김포공항 국제선 : ㈜하이파킹 에 의해 제공되니 \n   서비스 이용 시 공식 주차대행업체인지 확인하시기 바랍니다.\n인천공항 제 1,2여객터미널 및 김포공항 국내선 \n무료 발렛파킹 서비스 제공\n- 호텔 통합 월 2회 서비스 제공\n- 대상 카드로 지난달(1일~말일) 국내외 일시불/할부 50만원 이용 시 \n   서비스 제공 (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 \n   이용금액 50만원 미만 시에도 서비스 제공)\n대상 호텔\n지방\n지역\n서울\n앰배서더 서울 풀만\n그랜드 워커힐 서울 \n그랜드 하얏트 서울\n스위스 그랜드 호텔\n더 플라자 \n \n호텔 코리아나\n파크 하얏트 서울\n메이필드 호텔\n콘래드 서울\n호텔 리베라 청담\n \n레스케이프 호텔\n비스타 워커힐 서울\nJW 메리어트 동대문 스퀘어\nJW 메리어트 서울\n몬드리안 서울 이태원\n반얀트리 클럽앤스파 서울\n서울 가든 호텔\n서울 신라 호텔\n서울 드래곤 시티\n소피텔 앰배서더 서울\n \n \n노보텔 앰배서더 서울 강남\n노보텔 앰배서더 동대문\n글래드 강남 코엑스 센터\n더블리티 by 힐튼 판교\n코트야드 메리어트 서울 타임스퀘어\n르 메르디앙&목시 서울 명동\n오크우드 프리미어 코엑스\n메리어트 이그제큐티브\n아파트먼트 서울\n호텔 나루 서울 엠갤러리 \n호텔 오노마 대전\n인터불고 대구\n소노캄 여수\n소노캄 고양\n윈덤그랜드 부산\n그랜드 하얏트 인천\n파라다이스 부산 호텔\n그랜드조선부산\n세인트존스 호텔\n파크하얏트 부산\n힐튼 경주\n대구 메리어트 호텔\nJW 메리어트 제주 리조트&스파 \n파라다이스 시티 호텔\n그랜드머큐어엠배서더 창원\n인스파이어 엔터테이먼트 리조트\n인천공항\n제1여객터미널\n인천공항\n제2여객터미널\n주차 시 : ① 지하1층 단기주차장 A구역으로 이동 후 Maxerve 유니폼 착용\n                   공식 주차대행 직원에게 발렛파킹 요청\n              ② 모바일 접수증 문자 발송 (카카오톡/ MMS 문자발송, \n                   문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시 : ① 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 \n                   (지하 3층 A32구역 또는 H38구역)\n              ② 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 \n                   차량 인수\n              ③ 차량 인수 후 주차요금 고객이 별도 정산\n주차 시 : ① 제 2여객터미널 지하1층 서편 단기 주차장으로 진입\n              ② 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ③ 모바일 접수증 문자 발송 (알림톡/문자메세지 발송)\n출차 시 : ① 입국 후 접수증 안내에 따라 단기주차장 지하 1층 \n                   동편 210번 앞 고객대기실로 이동\n              ② 출차장 정산소에서 프리미엄 마스터카드 제시 후 \n                  서비스 이용가능 여부 확인\n              ③ 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n김포공항\n국내선\n주차 시 : ① 국내선 청사 2층 우측 하늘색 라인따라 진입 후, \n                    주황색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ② 차량 상태 점검 후 차량 인도 및 차량 보관증 수령\n출차 시 : ① 출발지 항공기 탑승 전 차량보관증에 기재된 연락처로 출차 요청\n              ② 차량 인수 시, 접수증과 프리미엄 마스터카드 제시 후 \n                   서비스 이용 가능 여부 확인\n              ③ 차량 인수 후 출차 시 고객이 주차요금 별도 정산\n* Mastercard 프리미엄 서비스의 상세한 내용은 Mastercard 홈페이지 \n   (http://www.mastercard.com/kr)를 통해 확인하시기 바랍니다.\n* 본 Mastercard 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품안내장,  \n   이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 Mastercard 프리미엄 서비스는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n상품유형\nMastercard World 03\n대상카드\nJADE Classic\n아래 대상 카드 발급 시 Mastercard World 03 선택서비스와 \nMastercard World 공통서비스가 제공됩니다.\nMastercard\nWorld 03\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n  \n선택서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03778호 (2026.03.20) / 준법심의 L-26-0364 (2026.02.09) / VI 260326-34\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:09.536855+00	SYSTEM	2026-11-03 05:21:09.536855+00	SYSTEM
20261103_000017	1	20261103_000058	1	\N	BODY	1	2926	UnionPay Diamond\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nUnionPay Diamond 공통서비스\n· 트립닷컴 국내외 항공권 10% 할인, 국내외 호텔 20% 할인 \n· DB손해보험 해외여행자 보험 기본상품 가입 시, 최대 5일 무료 \n· 클룩 해외 액티비티 예약 시 유니온페이 프리미엄 카드로 $100 이상 \n   결제 시 최대 $30 할인\n· 마이리얼트립 국내 투어/티켓/숙소 등 결제 시 최대 10% 즉시 할인\n· 글로벌 원심(OneSIM) 무료 이용 서비스 제공 (4.1~)\nHotel\nAirport\n· 국내 특급호텔(약 45여개) 100여개 식음료 매장 5~15% 할인\n· 국내 특급호텔(약 43여개) 객실 5~40% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약 15여개) 스파 5~15% 할인 및 샘플 증정\n· 국내 특급호텔 (약 7여개) 로비라운지에서 음료 구매 시 \n   동반인 음료 무료 제공 (월 1회, 연 4회)\n· 싱가포르 마리나 베이 샌즈의 샌즈 리워드 라이프스타일 \n   엘리트 등급 멤버십 혜택 3개월간 제공\nTravel\n* UnionPay Diamond 서비스의 상세한 내용은 UnionPay 홈페이지(http://www.unionpaypremium.co.kr)를 통해 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 전세계 럭셔리 공항 라운지(The Lounge App에서 확인 가능) 할인\n  (1+1) 제공\n· 유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 K공항리무진 할인\n  (1+1)\n· 인천공항 제휴 매장에서 아메리카노 결제 시 10% 할인\n· 현대면세점 BLACK 등급 멤버십 제공 및 추가 3~8% 선불카드 할인 제공\n  (무역센터점, 인천공항점, 온라인몰/4월 중 오픈 예정)\n· 경복궁면세점 인천공항점 $1 이상 구매 시 사은품 제공\n· 인천공항 연계 교통 무료 이용 서비스 제공\n· 국내 골프장 온라인 예약 서비스 및 그린피 할인\n   (유니온페이 골프사이트에서 본인 인증 후 프리미엄 카드 결제 시 서비스 제공)\n· 국내 지정 골프장 클럽하우스 또는 스타트하우스에서 이용권 제시 시\n   커피(4잔) 50% 할인\n   (유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 이용권 할인 서비스 제공)\n· 국내  지정 골프 연습장 타석권 결제 시 정상가 금액에서 50% 할인\n   (유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 이용권 할인 서비스 제공)\nGlobal\n· 해외 컨시어지 서비스 제공 (7.21~)\n· 해외 긴급 의료지원 서비스 제공 (7.21~)\n· 국내외 제휴 서비스 및 컨시어지 플랫폼 서비스 제공 (7.21~)\n- 유의사항\n  · 서비스 과정에서 실제로 발생하는 비용은 별도 청구 (UPI 홈페이지 참조)\n  · 해외 지원 서비스는 전부 유니온페이 프리미엄 콜센터로 전화상담 후 \n     서비스 제공 (콜센터 : 1670-8893, 24시간 연중무휴)\n· 국내 다이닝 레스토랑 10% 할인 혜택\n   (제휴 매장에서 유니온페이 다이아몬드 카드 제시 및 결제 시 할인 서비스 제공)\n   * 관련 문의 1670-8890\n- 유의사항\n  · 국내 특급호텔 객실 할인 및 스파 서비스는 유니온페이 프리미엄 콜센터를 통해\n     전화 상담 후 서비스 제공 (콜센터 1670-8810, 24시간 연중 무휴)\nGolf\nLife\nStyle\n서비스\n내용\n· 현대아울렛 전점에서 무료 음료 1잔(월 1회) 및 외국인 특화점에서 \n   추가 혜택(연 1회) 제공\n· 예술의전당 고객센터(1668-1352)를 통한 다이아몬드 카드 회원 \n   인증 후 예술의전당 블루회원 멤버십 서비스 제공\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-05041호 (2026.04.10) / 준법심의 L-26-0516(2026.03.24)/ VI 260421-31\n* 아래의 UnionPay Diamond 서비스는 UnionPay Diamond 등급 카드 소지자에게 공통으로 제공됩니다. \n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:14.154311+00	SYSTEM	2026-11-03 05:21:14.154311+00	SYSTEM
20261103_000017	2	20261103_000059	2	\N	BODY	1	3944	UnionPay Diamond\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n  \n선택서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-04831호(2026.04.07) / 준법심의 L-26-0515(2026.03.24)/ VI 260325-31\n* UnionPay Diamond 선택서비스 중 특급 호텔 발렛파킹, 인천공항 발렛파킹, 국내공항 라운지 서비스를 하나카드에서 제공합니다. \n인천공항 발렛파킹 서비스\n서비스 혜택 - 인천공항 무료 발렛파킹 서비스 제공\n이용조건 \n- 통합 월 2회 서비스 제공\n- 지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 이용금액 \n  50만원 미만 시에도 서비스 제공)\n인천공항 제1여객터미널 이용방법\n주차 시\n1. 지하 1층 단기 주차장 A구역으로 이동\n2. Maxerve 유니폼 착용 공식 주차대행  직원에게 발렛파킹 요청\n3. 모바일 접수증 문자 발송 \n   (카카오톡/ MMS 문자발송, 문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시\n1. 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 (지하 3층 A32 구역 또는 H38 구역)\n2. 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 차량 인수\n3. 차량 인수 후 주차요금 고객이 별도 정산\n인천공항 제2여객터미널 이용방법\n주차 시\n1. 제 2여객터미널 발렛파킹 전용도로 및 발렛 안내 표지판을 따라\n    지하 1층 서편 단기 주차장으로 진입\n2. 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n3. 모바일 접수증 문자 발송 (알림톡 / 문자메시지 발송)\n출차 시\n1. 입국 후 접수증 안내에 따라 단기 주차장 지하 1층 동편 210 번 앞 고객 대기실로 이동\n2. 출차장 정산소에서 카드 제시 후 서비스 이용가능 여부 확인\n3. 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n특급호텔 발렛파킹 서비스\n유의사항\n- 상기 서비스는 국내에서 발급된 유니온페이 다이아몬드 카드 회원에 한하여 제공하며, \n   회원 본인에 한해 제공됩니다.\n- 서비스 제공 횟수를 초과했을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 서비스는 발렛파킹 비용에 한하여 적용되며, 주차비용은 별도로 부과됩니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다. \n서비스 혜택 - 국내 주요 특급호텔 무료 발렛파킹 서비스 제공\n이용조건 \n- 호텔 통합 월 2회 서비스 제공\n- 지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n  50만원 미만 시에도 서비스 제공)\n이용방법 \n- 주차시 호텔 현관에서 도어맨에게 발렛파킹 요청 후 차량보관증 수령  \n- 차량 인수 시 도어맨에게 차량보관증과 유니온페이 다이아몬드 카드 제시\n- 호텔 단말기를 통해 서비스 이용가능 여부 확인 후 서비스 제공\n국내공항 라운지 서비스\n대상 호텔\n대구 메리어트 호텔\n웨스틴 조선 부산\n호텔 오노마 대전 오토그래프 컬렉션\n서울\n지방\n※ 오크우드 프리미어 코엑스 센터 (서비스 제외기간 참고)\n그랜드 머큐어 앰배서더 서울 용산\n그랜드 워커힐 서울\n노보텔 스위트 앰배서더 서울 용산\n노보텔 앰배서더 서울 용산\n더 플라자\n노보텔 앰배서더 서울 강남\n앰배서더 서울 풀만 호텔\n메리어트 이그제큐티브 아파트먼트\n파크 하얏트 서울\n반얀트리 클럽 앤 스파 서울\n비스타 워커힐 서울\n서울 신라 호텔\n레스케이프 호텔\n호텔 코리아나\n그랜드 하얏트 서울\n오크우드 프리미어 코엑스센터\n이비스 스타일 앰배서더 서울 용산\n코트야드 메리어트 서울 타임스퀘어\n콘래드 서울\nJW 메리어트 동대문 스퀘어\nJW 메리어트 호텔 서울\n노보텔 앰배서더 서울 동대문 호텔 \n& 레지던스\n몬드리안 서울 이태원\n스위스 그랜드 호텔\n서비스 제외기간\n- 오크우드 프리미어 코엑스 센터의 경우 코엑스 내 전시 또는 행사 시 서비스가 제한될 수 있습니다.\n유의사항\n- 상기 서비스는 해당 호텔의 객실 및 식음료 업장(연회장 제외)이용을 위해 내방한 회원 본인에 한해 제공됩니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다. \n- 상기 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 상기 서비스 이용 시 발렛파킹 비용 및 1일 3시간 이내의 주차비가 무료로 제공되나, 이용 시간 초과 시 \n   주차 금액이 별도로 부과될 수 있으며, 이는 회원이 부담하셔야 합니다.\n유의사항\n- 본 서비스는 동반자 및 유소아 요금은 각 라운지 마다 별도 금액이 적용되며, 유니온페이 다이아몬드 카드로 \n   결제  시 할인 금액이 적용됩니다.\n서비스 혜택 - 유니온페이 제휴 라운지 무료 이용 서비스 제공\n이용조건 \n- 본인에 한해 무료 이용 가능하며, 통합 월 2회(연 6회) 서비스 제공\n- 가족카드 사용 불가\n이용방법\n- 라운지 안내 데스크에서 보딩패스와 유니온페이 다이아몬드 카드 제시 및 \n 서비스 대상카드 여부 확인 후 무료 입장\n대상 공항\n상세내용\n인천공항\n김포공항\n김해공항\n스카이허브 라운지 제 1여객터미널 동편\n스카이허브 라운지 제 1여객터미널 서편\n스카이허브 라운지 제 1여객터미널 탑승동\n워커힐 마티나 라운지 제 1여객터미널 동편\n워커힐 마티나 라운지 제 1여객터미널 서편\n스카이허브 라운지 제 2여객터미널 동편\n스카이허브 라운지 제 2여객터미널 서편\n워커힐 마티나 라운지 제 2여객터미널 중앙 \n스카이허브 라운지 김포공항 국제선 청사\n스카이허브 라운지 김해공항 국제선 청사\nCLUB Signature 카드\n*UnionPay Diamond 서비스의 상세한 내용은 UnionPay 홈페이지 (http://www.unionpaypremium.co.kr) \n  또는 하나카드 홈페이지에서 반드시 확인하시기 바랍니다.\n*본 UnionPay Diamond 서비스는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, \n  카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n*본 UnionPay Diamond 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다. \n아래 대상 카드 발급 시 Unionpay Diamond 선택서비스가 제공됩니다.  \n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:14.154311+00	SYSTEM	2026-11-03 05:21:14.154311+00	SYSTEM
20261103_000018	1	20261103_000060	1	\N	BODY	1	2926	UnionPay Diamond\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nUnionPay Diamond 공통서비스\n· 트립닷컴 국내외 항공권 10% 할인, 국내외 호텔 20% 할인 \n· DB손해보험 해외여행자 보험 기본상품 가입 시, 최대 5일 무료 \n· 클룩 해외 액티비티 예약 시 유니온페이 프리미엄 카드로 $100 이상 \n   결제 시 최대 $30 할인\n· 마이리얼트립 국내 투어/티켓/숙소 등 결제 시 최대 10% 즉시 할인\n· 글로벌 원심(OneSIM) 무료 이용 서비스 제공 (4.1~)\nHotel\nAirport\n· 국내 특급호텔(약 45여개) 100여개 식음료 매장 5~15% 할인\n· 국내 특급호텔(약 43여개) 객실 5~40% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약 15여개) 스파 5~15% 할인 및 샘플 증정\n· 국내 특급호텔 (약 7여개) 로비라운지에서 음료 구매 시 \n   동반인 음료 무료 제공 (월 1회, 연 4회)\n· 싱가포르 마리나 베이 샌즈의 샌즈 리워드 라이프스타일 \n   엘리트 등급 멤버십 혜택 3개월간 제공\nTravel\n* UnionPay Diamond 서비스의 상세한 내용은 UnionPay 홈페이지(http://www.unionpaypremium.co.kr)를 통해 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 전세계 럭셔리 공항 라운지(The Lounge App에서 확인 가능) 할인\n  (1+1) 제공\n· 유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 K공항리무진 할인\n  (1+1)\n· 인천공항 제휴 매장에서 아메리카노 결제 시 10% 할인\n· 현대면세점 BLACK 등급 멤버십 제공 및 추가 3~8% 선불카드 할인 제공\n  (무역센터점, 인천공항점, 온라인몰/4월 중 오픈 예정)\n· 경복궁면세점 인천공항점 $1 이상 구매 시 사은품 제공\n· 인천공항 연계 교통 무료 이용 서비스 제공\n· 국내 골프장 온라인 예약 서비스 및 그린피 할인\n   (유니온페이 골프사이트에서 본인 인증 후 프리미엄 카드 결제 시 서비스 제공)\n· 국내 지정 골프장 클럽하우스 또는 스타트하우스에서 이용권 제시 시\n   커피(4잔) 50% 할인\n   (유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 이용권 할인 서비스 제공)\n· 국내  지정 골프 연습장 타석권 결제 시 정상가 금액에서 50% 할인\n   (유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 이용권 할인 서비스 제공)\nGlobal\n· 해외 컨시어지 서비스 제공 (7.21~)\n· 해외 긴급 의료지원 서비스 제공 (7.21~)\n· 국내외 제휴 서비스 및 컨시어지 플랫폼 서비스 제공 (7.21~)\n- 유의사항\n  · 서비스 과정에서 실제로 발생하는 비용은 별도 청구 (UPI 홈페이지 참조)\n  · 해외 지원 서비스는 전부 유니온페이 프리미엄 콜센터로 전화상담 후 \n     서비스 제공 (콜센터 : 1670-8893, 24시간 연중무휴)\n· 국내 다이닝 레스토랑 10% 할인 혜택\n   (제휴 매장에서 유니온페이 다이아몬드 카드 제시 및 결제 시 할인 서비스 제공)\n   * 관련 문의 1670-8890\n- 유의사항\n  · 국내 특급호텔 객실 할인 및 스파 서비스는 유니온페이 프리미엄 콜센터를 통해\n     전화 상담 후 서비스 제공 (콜센터 1670-8810, 24시간 연중 무휴)\nGolf\nLife\nStyle\n서비스\n내용\n· 현대아울렛 전점에서 무료 음료 1잔(월 1회) 및 외국인 특화점에서 \n   추가 혜택(연 1회) 제공\n· 예술의전당 고객센터(1668-1352)를 통한 다이아몬드 카드 회원 \n   인증 후 예술의전당 블루회원 멤버십 서비스 제공\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-05041호 (2026.04.10) / 준법심의 L-26-0516(2026.03.24)/ VI 260421-31\n* 아래의 UnionPay Diamond 서비스는 UnionPay Diamond 등급 카드 소지자에게 공통으로 제공됩니다. \n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:19.166396+00	SYSTEM	2026-11-03 05:21:19.166396+00	SYSTEM
20261103_000018	2	20261103_000061	2	\N	BODY	1	3808	UnionPay Diamond 02\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n•상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 \n    하락할 수 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다. \n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며,\n    법정 최고금리(20%)를 초과하지 않습니다.\n   ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n    - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n    - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n    - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n* 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n* 계약 체결 전 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n* 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한 될 수 있습니다.\n* 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n* 소비자는 금융소비자보호법에 따라 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n* 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다. \n* 자세한 내용은 하나카드 홈페이지(www.hanacard.co.kr)를 참고하시거나\n  고객센터로 문의 바랍니다.\n  \n선택서비스 \n \n여신금융협회 심의필 제 2026-C1a-04831호(2026.04.07) / 준법심의 L-26-0515(2026.03.24)/ VI 260325-31\n* UnionPay Diamond 선택서비스 중 특급 호텔 발렛파킹, 인천공항/김포공항 발렛파킹 서비스를 하나카드에서 제공합니다.\n인천공항/김포공항 발렛파킹 서비스\n서비스 혜택 - 인천공항/김포공항 무료 발렛파킹 서비스 제공\n이용조건 \n- 통합 월 2회 서비스 제공\n- 지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 이용금액 \n  50만원 미만 시에도 서비스 제공)\n인천공항 제1여객터미널 이용방법\n주차 시\n1. 지하 1층 단기 주차장 A구역으로 이동\n2. Maxerve 유니폼 착용 공식 주차대행  직원에게 발렛파킹 요청\n3. 모바일 접수증 문자 발송 \n   (카카오톡/ MMS 문자발송, 문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시\n1. 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 (지하 3층 A32 구역 또는 H38 구역)\n2. 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 차량 인수\n3. 차량 인수 후 주차요금 고객이 별도 정산\n인천공항 제2여객터미널 이용방법\n주차 시\n1. 제 2여객터미널 발렛파킹 전용도로 및 발렛 안내 표지판을 따라\n    지하 1층 서편 단기 주차장으로 진입\n2. 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n3. 모바일 접수증 문자 발송 (알림톡 / 문자메시지 발송)\n출차 시\n1. 입국 후 접수증 안내에 따라 단기 주차장 지하 1층 동편 210 번 앞 고객 대기실로 이동\n2. 출차장 정산소에서 카드 제시 후 서비스 이용가능 여부 확인\n3. 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n특급호텔 발렛파킹 서비스\n김포공항 국내선 이용방법 (이용가능시간 05:00~21:00 / 출차는 24시간 가능)\n주차 시\n1. 국내선 청사 출발층(2층) 제일 우측 라인(하늘색)따라 진입 \n2. 오렌지색 유니폼 착용 공식 대행 직원에게 발렛파킹 요청 \n3.  차량 상태 점검 후 차량 인도 및 차량보관증 수령 \n출차 시\n1. 출발지 항공기 탑승 전 차량보관증에 있는 연락처로 차량 출차 요청\n2. 조기출발로 비행 일정이 변경된 경우, 반드시 사전에 차량보관증에 있는 연락처로  \n    변경사항 전달 및 차량 출차 요청 \n3.  차량 인수시, 접수증과 아멕스 프리미엄 카드 제시하여 단말기를 통해 \n     서비스 이용 가능여부 확인 후 서비스 무료 제공 \n4. 차량인수 후 출차 시, 주차 요금 별도 정산\n유의사항\n- 상기 서비스는 국내에서 발급된 유니온페이 다이아몬드 카드 회원에 한하여 제공하며, \n   회원 본인에 한해 제공됩니다.\n- 서비스 제공 횟수를 초과했을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 서비스는 발렛파킹 비용에 한하여 적용되며, 주차비용은 별도로 부과됩니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다. \n서비스 혜택 - 국내 주요 특급호텔 무료 발렛파킹 서비스 제공\n이용조건 \n- 호텔 통합 월 2회 서비스 제공\n- 지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n  50만원 미만 시에도 서비스 제공)\n이용방법 \n- 주차시 호텔 현관에서 도어맨에게 발렛파킹 요청 후 차량보관증 수령  \n- 차량 인수 시 도어맨에게 차량보관증과 유니온페이 다이아몬드 카드 제시\n- 호텔 단말기를 통해 서비스 이용가능 여부 확인 후 서비스 제공\n대상 호텔\n대구 메리어트 호텔\n웨스틴 조선 부산\n호텔 오노마 대전 오토그래프 컬렉션\n서울\n지방\n※ 오크우드 프리미어 코엑스 센터 (서비스 제외기간 참고)\n그랜드 머큐어 앰배서더 서울 용산\n그랜드 워커힐 서울\n노보텔 스위트 앰배서더 서울 용산\n노보텔 앰배서더 서울 용산\n더 플라자\n노보텔 앰배서더 서울 강남\n앰배서더 서울 풀만 호텔\n메리어트 이그제큐티브 아파트먼트\n파크 하얏트 서울\n반얀트리 클럽 앤 스파 서울\n비스타 워커힐 서울\n서울 신라 호텔\n레스케이프 호텔\n호텔 코리아나\n그랜드 하얏트 서울\n오크우드 프리미어 코엑스센터\n이비스 스타일 앰배서더 서울 용산\n코트야드 메리어트 서울 타임스퀘어\n콘래드 서울\nJW 메리어트 동대문 스퀘어\nJW 메리어트 호텔 서울\n노보텔 앰배서더 서울 동대문 호텔 \n& 레지던스\n몬드리안 서울 이태원\n스위스 그랜드 호텔\n서비스 제외기간\n- 오크우드 프리미어 코엑스 센터의 경우 코엑스 내 전시 또는 행사 시 서비스가 제한될 수 있습니다.\n유의사항\n- 상기 서비스는 해당 호텔의 객실 및 식음료 업장(연회장 제외) 이용을 위해 내방한 회원 본인에 한해 제공됩니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능여부를 확인하시기 바랍니다.\n- 해당 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 해당 서비스 이용 시 발렛파킹 비 용 및 1일 3시간 이내의 주차가 무료로 제공되나, 이용시간 초과 시 주차금액이 \n   별도로 부과될 수 있습니다.\n JADE Classic 카드 \n*UnionPay Diamond 02 서비스의 상세한 내용은 UnionPay 홈페이지 (http://www.unionpaypremium.co.kr) \n  또는 하나카드 홈페이지에서 반드시 확인하시기 바랍니다.\n*본 UnionPay Diamond 서비스는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, \n  카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n*본 UnionPay Diamond 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다. \n아래 대상 카드 발급 시 Unionpay Diamond 02 선택서비스가 제공됩니다.  \n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:19.166396+00	SYSTEM	2026-11-03 05:21:19.166396+00	SYSTEM
20261103_000019	1	20261103_000062	1	\N	BODY	1	2587	UnionPay Platinum\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nUnionPay UPI Platinum 공통서비스\n· 트립닷컴 국내외 항공권 10% 할인, 국내외 호텔 15% 할인 \n· DB손해보험 해외여행자 보험 기본상품 가입 시, 최대 3일 무료 \n· 클룩 해외 액티비티 예약 시 유니온페이 프리미엄 카드로 $100 이상 \n   결제 시 최대 $30 할인  \n· 마이리얼트립 국내 투어/티켓/숙소 등 결제 시 최대 10% 즉시 할인\n· 글로벌 원심(OneSIM) 무료 이용 서비스 제공 (4.1~)\nHotel\nAirport\n· 국내 특급호텔(약 45여개) 100여개 식음료 매장 5~15% 할인\n· 국내 특급호텔(약 43여개) 객실 5~40% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약 15여개) 스파 5~15% 할인 및 샘플 증정\n· 국내 특급호텔 (약 7여개) 로비라운지에서 음료 구매 시 \n   동반인 음료 무료 제공 (월 1회, 연 4회, 플래티늄 법인카드에 한함)\n· 싱가포르 마리나 베이 샌즈의 샌즈 리워드 라이프스타일 \n   엘리트 등급 멤버십 혜택 3개월간 제공\nTravel\n* UPI Platinum 서비스의 상세한 내용은 UnionPay 홈페이지(http://www.unionpaypremium.co.kr)를 통해 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 유니온페이 플래티늄 혜택 구매 사이트에서 결제 시 K공항리무진 할인\n  (1+1)\n· 인천공항 제휴 매장에서 아메리카노 결제 시 10% 할인\n· 경복궁면세점 인천공항점 $1 이상 구매 시 사은품 제공\n· 현대면세점 GOLD 등급 멤버십 제공 및 추가 3~8% 선불카드 할인 제공\n  (무역센터점, 인천공항점, 온라인몰/4월 중 오픈 예정)\n· 국내 골프장 온라인 예약 서비스 및 그린피 할인\n   (유니온페이 골프사이트에서 본인 인증 후 프리미엄 카드 결제 시 서비스 제공)\n· 국내 지정 골프장 클럽하우스 또는 스타트하우스에서 이용권 제시 시\n   커피(4잔) 30% 할인\n   (유니온페이 플래티늄 혜택 구매 사이트에서 결제 시 이용권 할인 서비스 제공)\nGlobal\n· 해외 컨시어지 서비스 제공 \n· 해외 긴급 의료지원 서비스 제공\n· 국내외 제휴 서비스 및 컨시어지 플랫폼 서비스 제공 \n- 유의사항\n  · 서비스 과정에서 실제로 발생하는 비용은 별도 청구 (UPI 홈페이지 참조)\n  · 해외 지원 서비스는 전부 유니온페이 프리미엄 콜센터로 전화상담 후 \n     서비스 제공 (콜센터 : 1670-8893, 24시간 연중무휴)\n- 유의사항\n  · 국내 특급호텔 객실 할인 및 스파 서비스는 유니온페이 프리미엄 콜센터를 통해\n     전화 상담 후 서비스 제공 (콜센터 1670-8810, 24시간 연중 무휴)\nGolf\nLife\nStyle\n서비스\n내용\n· 현대아울렛 전점에서 무료 음료 1잔(월 1회) 및 외국인 특화점에서 \n   추가 혜택(연 1회) 제공\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-05040호 (2026.04.10) / 준법심의 L-26-0517(2026.03.24)/ VI 260421-32\n* 아래의 UnionPay Platinum 서비스는 UnionPay Platinum 등급 카드 소지자에게 공통으로 제공됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:23.814442+00	SYSTEM	2026-11-03 05:21:23.814442+00	SYSTEM
20261103_000020	1	20261103_000063	1	\N	BODY	1	2407	Visa\nInfinite \n공통서비스\n서비스\n· 진에어빠른체크인및빠른짐찾기서비스(연4회, 최대4인)\n· 카타르항공최대15% 할인\n(예약기간: ~26.10.31 / 여행기간: ~27.3.31)\n· 일본항공일본행항공권8% 할인(25.10.1~26.3.31)\n· 공항의전서비스(yQ Meet & Assist) 25% 할인\n내용\n· 전세계900여개호텔Visa Luxury Hotel Collection 혜택제공\n· Hotels.com 쿠폰코드입력시최대8% 할인(숙박기간: ~27.6.30)\n· Booking.com 최대7% 월렛포인트캐시백(매월1일~15일한정)\n· Agoda 국내, 해외호텔3박투숙시2박요금만결제\n(숙박기간: ~27.12.31)\n· Expedia 8% 할인(숙박기간: ~27.6.30)\n· IHG Hotel&Resorts 20% 할인(숙박기간: ~27.1.3)\n· Accor China 중화권호텔최소2박예약시20% 할인(~26.9.30)\n· 반얀트리최소2박숙박시20%할인\n(예약기간: ~26.5.31 / 숙박기간: ~26.8.31)\n· GHA 디스커버리멤버십무상업그레이드\n· Ascott 프로모션기간내사용시리워드등급업그레이드\n서비스(~27.11.30)\n· 국내특급호텔(약68여개) F&B 5~20% 할인\n· 국내특급호텔(약73여개) 객실/패키지5~60% 할인\n· 국내호텔스파(약22여개) 10~20% 할인\n· 국내부티크호텔(약23여개) 객실/F&B 5~50% 할인\n· 국내특급호텔(약6여개) 로비라운지5~20% 할인\n· Hertz 해외렌터카기본10% 할인및추가혜택(~26.3.31)\n· AVIS 해외렌터카최대35% 할인\n· Rentalcars.com 10% 추가할인(~26.4.30)\n· Movv 이동서비스국내1.5~3.5만원, 해외8% 할인\n· 아시아태평양공항픽업서비스\nTBR Luxury Airport Transfer 20% 할인\n· 굿럭해외공항짐배송및보관20% 할인\n· 굿럭인천공항입국시교통약자짐찾기대행및배송서비스할인\n· Trip.com 최대6%할인\nHotel\nAir &\nAirport\nTravel\n· 비자엘리트다이닝최대20% 할인혜택제공(~26.8.31)\n· 트립쿠폰멤버십무료제공\n· 하와이올로마나골프장그린피15% 할인및\n연습볼1버켓무료\n· Visa 컨시어지제공\n전화080-4880-880, 홈페이지www.concierge-asia.visa.com\n카카오톡“Visa 컨시어지” 채널추가\nDinig &\nLifestyle\nShopping\n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용\n평점이하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이\n발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가\n발생할수있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등\n적용되며, 법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) \n유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부\n계약기간의유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융\n가계자금대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관\n가중평균대출금리(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도\n등에영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기\n바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금\n결제일에상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가\n있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐\n제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를\n참고하시거나고객센터로문의바랍니다.\n여신금융협회심의필제2026 - C1a - 05179호( 2026.04.13 ) / 준법심의L-26-0466 (2026.03.16)\n* 아래의Visa Infinite 서비스는Visa Infinite 등급카드\n소지자에게공통으로제공됩니다.\n· 롯데면세점(국내)고객면세점할인및\n회원등급업그레이드혜택제공(~26.6.30)\n· 롯데면세점싱가포르차이공항고객면세점할인\n(~26.10.16)\n· 현대백화점면세점블랙멤버십제공(최대20% 할인)\n· Mitsui Outlet Park에서최대10%할인(~27.11.30)\n* 본Visa Infinite 서비스안내서는회원이발급받은카드\n상품안내장, 이용약관과함께교부되오니, 카드이용과관련한\n유의사항을반드시확인하시기바랍니다.\n* 본서비스는Visa에서제공하는서비스로, 프리미엄서비스에\n대한구체적내용, 적용기준및유의사항등\nhttp://www.visakorea.com → ‘Visa 인피니트’에서사전에\n반드시확인해주시기바랍니다.\n* 본Visa Infinite 서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:28.533172+00	SYSTEM	2026-11-03 05:21:28.533172+00	SYSTEM
20261103_000020	2	20261103_000064	2	\N	BODY	1	3881	Visa Infinite 선택서비스중특급호텔발렛파킹, 인천공항발렛파킹서비스를하나카드에서제공합니다.\n* Visa 프리미엄서비스에대한구체적내용, 적용기준및유의사항\n등은Visa 홈페이지(www.visakorea.com) 또는하나카드홈페이지\n에서확인해주시기바랍니다.\n* 본Visa 프리미엄서비스안내서는회원이발급받은카드상품안\n내장, 이용약관과함께교부되오니, 카드이용과관련한유의사항\n을반드시확인하시기바랍니다.\n* 본Visa 프리미엄서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n아래의대상카드발급시Visa Infinite\n선택서비스가제공됩니다.\nJADE First                            JADE First Centum \n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용평점이\n하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가발생할수\n있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등적용되며, \n법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) 유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부계약기간의\n유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융가계자금\n대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관가중평균대출금리\n(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도등에\n영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금결제일에\n상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를참고하시거나\n고객센터로문의바랍니다.\n여신금융협회심의필제2026-C1a-05532호( 2026.04.17 ) / 준법심의L-26-0469 (2026.03.17)\nVisa infinite 선택서비스\n특급호텔발렛파킹무료이용\n- 국내특급호텔에서발렛파킹을무료이용하실수있습니다. (월8회/연60회)\n서비스제공한도\n- 호텔통합월8회/연60회한도내에서이용가능\n- 본인카드와가족카드의한도는개별제공\n1.월한도기준: 매월1일부터말일까지\n2.연한도기준: 매년1월1일부터12월31일까지\n- 서비스제공한도를초과할경우발렛파킹비용은본인부담\n이용방법\n- 호텔현관또는발렛파킹부스에발렛파킹요청후주차권수령\n- 차량인수시주차권과대상카드제시\n- 호텔단말기를통해서비스이용가능여부확인후서비스제공\n대상호텔\n서울\n그랜드워커힐서울\n그랜드하얏트서울\n글래드강남코엑스센터\n노보텔앰배서더서울강남\n노보텔앰배서더서울동대문\n더플라자\n레스케이프호텔\n르메르디앙& 목시서울명동\n파크하얏트서울\n포시즌스호텔서울\n호텔나루서울엠갤러리\n메리어트이그제큐티브아파트먼트서울\n메이필드호텔\n몬드리안서울이태원\n반얀트리클럽앤스파서울\n비스타워커힐서울\n서울신라호텔\n소피텔앰배서더서울&서비스드레지던스\n스위스그랜드호텔\n안다즈서울강남\n앰배서더서울풀만호텔\n오크우드프리미어코엑스센터\n그랜드머큐어임피리얼팰리스서울\n코트야드바이메리어트서울타임스퀘어\n콘래드서울\n서울가든호텔\n서울드래곤시티\nAC 호텔바이메리어트서울강남\nJW 메리어트동대문스퀘어서울\nJW 메리어트호텔서울\n호텔코리아나\n서울외\n그랜드조선부산\n웨스틴조선부산\n파크하얏트부산\n그랜드머큐어앰배서더창원\n그랜드하얏트인천\n대구메리어트호텔\n세인트존스호텔\n소노캄고양\n소노캄여수\n인스파이어엔터테인먼트리조트\n호텔오노마대전오토그래프컬렉션\n호텔인터불고대구\n유의사항\n- 주차요금은본인부담이며, 일부호텔에한해1일3시간까지무료주차가제공되므로\n발렛파킹이용전반드시방문하실호텔에서비스가능여부를확인하시기바랍니다.\n- 본서비스는국내에서발급된비자프리미엄카드회원이해당호텔의객실및식음료\n업장(연회장제외) 이용을위해내방한회원본인에한해제공합니다.\n- 본서비스이용시호텔정책에따라해당호텔은회원에게해당호텔을이용한영수증\n을요청할수있으며, 영수증미지참시에는별도의발렛파킹비용과주차금액이청구될\n수있습니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시기\n바랍니다.\n공항발렛파킹무료이용\n- 국내공항에서발렛파킹을무료이용하실수있습니다. (월8회/연60회)\n서비스제공한도\n- 공항통합월8회/연60회한도내에서이용가능합니다.\n- 본인카드와가족카드의한도는개별제공합니다.\n1) 월한도기준: 매월1일부터말일까지\n2) 연한도기준: 매년1월1일부터12월31일까지\n- 서비스제공횟수를초과할경우발렛파킹비용은본인부담입니다.\n대상공항별이용방법\n주차시: 1. 인천공항제1여객터미널발렛전용차로및안내표지판을따라\n지하1층단기주차장A구역으로이동\n2. Maxerve 유니폼착용공식대행직원에게발렛요청후모바일\n차량접수증수령(카카오톡접수증발송)\n출차시: 1. 주차대행접수증에안내된출차장소로이동(지하3층A32 또는H38)\n2. 유인정산소모바일접수증제시“제휴카드승인“ 후차량인수\n3. 주차장출차시, 추자요금별도정산\n- 인천공항제1터미널\n- 인천공항제2터미널\nVisa\nInfinite\n선택서비스\n힐튼경주\nJW 메리어트제주리조트&스파\n주차시: 1. 국내선청사2층우측하늘색라인따라진입후, 오렌지색유니폼\n착용공식주차대행직원에게발렛파킹요청\n2. 차량상태점검후차량인도및차량보관증수령\n출차시: 1. 출발지항공기탑승전차량보관증에기재된연락처로출차요청\n2. 차량인수시, 접수증과프리미엄마스터카드제시후서비스\n이용가능여부확인\n3. 차량인수후출차시고객이주차요금별도정산\n- 김포공항국내선(이용가능시간05:00~21:00 / 출차는24시간가능)\n주차시: 1. 출국일정24시간전사전예약처로유선예약시이용가능하며, \n예약시비자프리미엄카드회원임을반드시전달하고김해공항\n발렛파킹지정장소안내받음(국내선/국제선출발층) \n2. 안내받은장소에도착후차량인도및차량보관증수령\n출차시: 1. 도착후차량보관증에명시되어있는지정주차장연락처로연락\n2. 도착층지정장소에서무료셔틀이용해지정주차장이동\n3. 비자프리미엄카드로서비스이용가능여부확인후\n발렛파킹서비스무료제공(주차비정산후차량인수)\n- 김해공항(1일무료주차서비스함께제공)\n지난달실적조건: 지난달(1일~말일) 국내외일시불/할부50만원이상이용시서비스제공\n(최초카드사용등록후다음달말일까지는지난달카드이용금액50만원미만시에도서비스제공)\n실적제외대상: 국세, 지방세, 수도/전기요금, 그외공과금(우편요금, 여권발급비용, 과태료, 범칙\n금, 벌금, 국가/공공기관/공공단체가부과하는부담금), 도시가스요금, 아파트관리비, 국민연금/고용\n보험료/산재보험료/건강보험료납부금액, 스쿨뱅킹, 초·중·고학교납입금, 대학등록금, 대학원등록금, \n상품권및기프트카드구매, 선불카드및선불전자지급수단(하나머니등) 충전금액, 부동산임대료\n사전예약처\n주차시: 1. 제2여객터미널발렛전용차로및안내표지판을따라\n지하1층서편단기주차장으로이동\n2. 파란색유니폼착용한공식대행직원에게발렛요청후\n모바일접수증수령(카카오톡/문자수신)\n출차시: 1. 접수증에표시된연락처를통해접수번호및차량번호확인후출차진행\n2. 접수증(또는차량보관증)에명기된구역(동편단기주차장지하1층)\n고객대기실에서비자프리미엄카드와접수증제시\n3. 서비스이용가능여부확인후발렛파킹서비스무료제공\n(출차시주차요금별도정산)\n유의사항\n- 주차요금은본인부담이며, 지정된장소외에는5분이상정차시과태료가부과될\n수있습니다.\n- 본서비스는국내에서발급된비자프리미엄카드회원이해당공항발렛파킹서비스\n를사전예약하고내방한회원본인에한해제공하며, 현장상황에따라당일서비스\n요청고객도접수가가능합니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시기\n바랍니다\n인천공항1터미널\nhttps://Maxerve-mparking.com/valet\n인천공항2터미널\nhttps://valet.amanopark.co.kr\n김해공항\n전화예약051-903-7000\n김포공항\n(사전예약없이이용가능)\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:28.533172+00	SYSTEM	2026-11-03 05:21:28.533172+00	SYSTEM
20261103_000021	1	20261103_000065	1	\N	BODY	1	1806	VISA \nPlatinum 01 Service\nVISA Platinum 공통서비스\nTravel : 여행서비스\n[비자 Hotels.com 할인 서비스]\n· 전세계 수십만개 호텔과 2천 9백만개 실제 숙박리뷰를 보유하고 있는 \n Hotels.com 비자 프로모션 사이트에서 비자카드로 결제 시 최대 8% 할인 제공\n (프로모션코드: VISA8)\n[Booking.com 캐시백 서비스]\n· Booking.com/Visakr에서 캐시백 뱃지가 있는 숙소를 VISA카드로 예약 시 \n 10% 캐시백 제공 (App을 통한 예약 제외)\n[해외 렌터카 서비스]\n- Hertz와 AVIS에서 렌탈 시 다양한 혜택 제공   \n· Hertz 렌터카 : 기본 10% 할인과 추가 혜택 제공 (이용기간 : 23.1.1~23.9.30)    \n    (지역 별 프로모션 코드 VISA 홈페이지 참조)   \n· AVIS 렌터카: 최대 20% 할인 \n[비자 Rentalcars.com 서비스]\n· 온라인 렌터카 예약 사이트 Rentalcars.com의 비자 프로모션 사이트에서\n 결제 시 추가 10% 할인 서비스 제공\n[아시아 태평양 지역 공항 픽업 서비스]\n· TBR Global 프로모션 사이트를 통해 아시아 태평양 지역 공항 및 도시에서 \n 공항 또는 숙소까지 픽업 서비스 예약 및 할인 제공\n[굿럭(goodlugg) 해외여행 캐리어 배송/보관 할인 서비스]\n· 굿럭 앱을 통해 예약 및 결제 시 당일 짐 배송 및 글로벌 실시간 안심 \n 짐 보관 서비스 10% 할인\n[굿럭(goodlugg) 인천공항 입국시 짐찾기 대행 및 배송 서비스]\n· 인천공항으로 입국하는 교통약자 짐을 대신 찾아 도착지 숙소로 배송해주는 \n 서비스 최대 50% 할인\n[movv 이동 서비스 할인 혜택]\n· movv에서 국내/외 공항 또는 국내 골프장 이동 시 할인 혜택 제공 \n선택서비스를 제외한 아래의 VISA Platinum 서비스는 VISA Platinum 등급 카드 소지자에게 공통으로 제공됩니다. \n서비스 상세 이용조건 및 방법을 VISA 홈페이지 (http://www.visakorea.com)에서 반드시 확인하시기 바랍니다.\nLifestyle : 생활서비스\n[하와이 올로마나 골프장 할인 및 특별 혜택]\n· 그린피 15% 할인 및 연습볼 1 bucket 제공\n[온라인 교육 플랫폼 할인 혜택]\n· 세계 유수의 온라인 교육 플랫폼 10~ 40% 할인\n (이용기간 : 23.1.1~23.9.30)\nConcierge : 컨시어지서비스\n[비자 프리미엄 컨시어지]\n· 비자 프리미엄 카드 회원을 위한 컨시어지 서비스 제공\n * 플래티늄 컨시어지 82-2-6240-3678\n * 운영시간: 연중무휴 24시간 운영\nHotel : 호텔서비스\n[국내 특급호텔 F&B 할인 서비스]\n· 비자 프리미엄 카드 회원에게 53개 국내 특급 호텔 F&B 매장에서 \n 5%~15% 특별 할인 혜택 제공 \n[국내 특급호텔 객실 및 패키지 할인 서비스]\n· 비자 프리미엄 카드 회원에게 61개 국내 특급 호텔의 객실 및 패키지 특별 할인 제공\nAirport : 공항서비스\n[공항 의전 서비스(yQ Meet & Assist)]\n· 전 세계 약 450여 개 공항에서 제공되는 빠른 입국/출국 서비스를 \n 비자 프리미엄 카드로 결제 시 정상가 대비 15% 할인 서비스 제공\nShopping : 쇼핑서비스\n[면세점 할인 서비스]\n· 신세계면세점 VIP 골드 멤버십 혜택 제공 \n (최대 15% 할인, 오프라인 전 매장에서 제공)\n· 현대백화점 면세점 골드 멤버십 혜택 제공 (최대 15% 할인) \n[캐치패션 추가 캐쉬백 혜택]\n· 비자가 매월 선정하는 캐치패션 파트너사에서 구매 시 최대 3% 캐시백\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:32.951882+00	SYSTEM	2026-11-03 05:21:32.951882+00	SYSTEM
20261103_000021	2	20261103_000066	2	\N	BODY	1	3630	VISA Platinum 선택서비스 – VISA Platinum 01 유형\nVISA Platinum 선택서비스 중 특급호텔 발렛파킹, 인천공항 발렛파킹 서비스를 하나카드에서 제공합니다. \n그외 서비스 상세 이용조건 및 방법은 VISA 홈페이지(http://www.visakorea.com) 또는 하나카드 홈페이지(http://www.hanacard.co.kr)를 반드시 참고하시기 바랍니다.\n특급호텔 발렛파킹 서비스\n서비스혜택\n이용조건\n이용방법\n국내 주요 특급호텔 무료 발렛파킹 서비스 제공 \n- 호텔 통합 월 3회 서비스 제공\n- CLUB SK 카드, CLUB SK카드 hiplus 선불하이패스,\n\t 토스(Toss) 하나카드 Ver 2.0 은 \n\t 지난달(1일~말일) 국내외 일시불/할부 30만원 이상 이용 시 \n\t 서비스 제공 (최초 카드 사용등록 후 다음달 말일까지는 \n\t 지난달 카드 이용금액 30만원 미만 시에도 서비스 제공)\n- 주차 시 호텔 현관에서 도어맨에게 발렛파킹 요청 후 주차권 수령\n- 차량 인수 시 도어맨에게 주차권과 비자 프리미엄 카드 제시\n- 호텔 단말기를 통해 서비스 이용가능 여부 확인 후 서비스 제공\n유의사항\n- 상기 서비스는 해당 호텔의 객실 및 식음료업장(연회장 제외) 이용을 위해\n 내방한 회원 본인에 한해 제공함을 원칙으로 합니다.\n- 상기 서비스 이용 시 호텔 정책에 따라 해당 호텔을 이용한 영수증 제시를 요청할 수 있으며,\n 영수증 미지참시에는 별도의 발렛파킹 비용과 주차금액이 청구될 수 있습니다.\n- 연회 참석 및 국가 주요행사 시에는 상기 서비스를 이용하실 수 없으며,\n 이용고객의 집중으로 주차공간이 부족할 경우 서비스가 제한될 수 있습니다.\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 상기 서비스 이용 시 발렛파킹 비용 및 1일 3시간 이내의 주차비가 무료로 제공됩니다.\n 이용시간 초과 시 주차금액이 별도로 부과될 수 있으며, 이는 별도로 부담하셔야 합니다.\n- 일부 호텔은 반드시 당일 일정 금액의 영수증 지참 시에만 서비스가 제공되며 \n 서비스 상세 이용요건에 대해서는 VISA 홈페이지(http://www.visakorea.com) 또는 \n 하나카드 홈페이지(http://www.hanacard.co.kr)를 반드시 참고하시기 바랍니다.\n* VISA 프리미엄 서비스의 상세한 내용은 VISA 홈페이지(http://www.visakorea.com)를 통해 \n  확인하시기 바랍니다.\n* 본 VISA 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, \n  카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 VISA 프리미엄 서비스는 2023년 1월 1일 ~ 12월 31일까지 제공됩니다.\n* 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n* 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n* 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n* 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n* 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n* 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n* 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 문의 바랍니다.\n•상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 \n   하락할 수 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율+최대3%)은 회원별·이용상품별로 차등 적용되며, \n\t 법정 최고금리(20%)를 초과하지 않습니다.\n\t ※ 단, 연체 발생 시점에 약정이율이 없는 경우는 아래와 같이 적용함\n\t - 일시불 거래 연체 시 : 거래발생 시점의 최소기간(2개월) 유이자 할부금리\n\t - 무이자 할부 거래 연체 시 : 거래발생 시점의 동일한 할부 계약기간의 유이자 할부금리\n\t - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은 금리 적용\n여신금융협회 심의필 제 2023-C1a-08448호(2023.07.27) / 준법심의 L-23-0125 / VI 230731-33\n아래의 대상 카드 발급 시 국제 브랜드사 서비스로\nVISA Platinum 선택서비스(01 유형)과 VISA Platinum 공통서비스가 제공됩니다.\nVISA Platinum 01 Service\n대상카드\n플래티늄 Royal카드\nCLUB SK 카드\nCLUB SK카드 hiplus 선불하이패스\nPlatinum카드\nCLUB PRIMUS 카드\nSK Broadband Smart BIZ카드\nSK 패밀리 카드\n토스(Toss) 하나카드 Ver 2.0\nVISA Platinum 01\n상품유형\n인천공항 발렛파킹 서비스\n서비스혜택\n이용조건\n제1여객터미널\n이용방법\n제2여객터미널\n이용방법\n인천공항 무료 발렛파킹 서비스 제공(제1여객터미널, 제2여객터미널)\n- 통합 월 3회 서비스 제공\n- CLUB SK 카드, CLUB SK카드 hiplus 선불하이패스,\n\t 토스(Toss) 하나카드 Ver 2.0 은 \n\t 지난달(1일~말일) 국내외 일시불/할부 30만원 이상 이용 시 \n\t 서비스 제공 (최초 카드 사용등록 후 다음달 말일까지는 \n\t 지난달 카드 이용금액 30만원 미만 시에도 서비스 제공)\n주차 시 :  1. 인천공항 제1여객터미널 발렛 전용차로 및 \n  \n 발렛 안내 표지판을 따라 지하 1층 \n  \n 단기주차장 A구역으로 이동\n   \n2. 오렌지색 유니폼 착용 공식 대행 직원에게 발렛 요청 후 \n  \n 접수증 수령 (SMS 발송)\n출차 시 :  1. 접수증에 표시된 장소로 이동 후 차량 인수 시 \n  \n 접수증과 비자 프리미엄 카드 제시\n  \n2. 차량 인수 후 출차 시 주차요금 별도 정산\n주차 시 :   1. 인천공항 제2여객터미널 발렛 전용차로 및 \n  \n 발렛안내 표지판을 따라 단기주차장 지하 1층 \n  \n 서편 주차구역 110~112번으로 이동\n  \n2. 오렌지색 유니폼 착용 공식 대행 직원에게 \n  \n 발렛 요청 후 접수증 수령 (알림톡, SMS 발송)\n출차 시 :  1. 접수증에 표시된 동편 단기주차장 지하 1층 \n  \n 210번 고객 대기실로 이동\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 상기 서비스는 발렛파킹 비용에만 적용되므로, 주차비용은 별도로 정산하셔야 합니다.\n- 3층 여객터미널 승용차 전용 도로에서 5분 이상 정차 시 과태료가 부과될 수 있습니다.\n- 국가 주요행사 등 공항에서 정하는 규정에 따라 서비스가 제한될 수 있습니다.\n- 공항 이용객이 많은 성수기, 명절 기간 또는 공항 주차장 만차 시 서비스 이용이 \n   제한될 수 있습니다. \n노보텔 앰버서더 서울 동대문\n그랜드 워커힐 서울\n그랜드 하얏트 서울\t\n그랜드 하얏트 인천 \n그랜드 머큐어 앰배서더 창원\t\n호텔 농심\n노보텔 앰배서더 서울 강남\n서울 드래곤 시티\n페어몬트 앰배서더 서울\n파크 하얏트 부산\n호텔 인터불고 대구\n서울\n지방\n지역\n대상 호텔\n르 메르디앙 & 목시 서울 명동\n비스타 워커힐 서울\n앰배서더 서울 풀만 호텔\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:32.951882+00	SYSTEM	2026-11-03 05:21:32.951882+00	SYSTEM
20261103_000022	1	20261103_000067	1	\N	BODY	1	2109	서비스\n· 카타르항공최대15% 할인\n(예약기간: ~26.10.31 / 여행기간: ~27.3.31)\n· 일본항공일본행항공권5% 할인(25.10.1~26.3.31)\n· 공항의전서비스(yQ Meet & Assist) 15% 할인\n내용\n· Hotels.com 쿠폰코드입력시최대8% 할인(숙박기간: ~27.6.30)\n· Booking.com 최대7% 월렛포인트캐시백(매월1일~15일한정)\n· Expedia 8% 할인(숙박기간: ~27.6.30)\n· IHG Hotel&Resorts 20% 할인(숙박기간: ~27.1.3)\n· Accor China 중화권호텔최소2박예약시20% 할인(~26.9.30)\n. 반얀트리최소2박숙박시20%할인\n(예약기간: ~26.5.31 / 숙박기간: ~26.8.31)\n· 국내특급호텔(약52여개) F&B 5~20% 할인\n· 국내특급호텔(약59여개) 객실/패키지5~60% 할인\n· 국내부티크호텔(약23여개) 객실/F&B 5~50% 할인\n· 국내특급호텔(약5여개) 로비라운지5~20% 할인\n· Hertz 해외렌터카기본10% 할인및추가혜택(~26.3.31)\n· AVIS 해외렌터카최대20% 할인\n· Rentalcars.com 10% 추가할인(~26.4.30)\n· Movv 이동서비스국내1.5~3.5만원, 해외8% 할인혜택\n· 아시아태평양공항픽업서비스\nTBR Luxury Airport Transfer 10% 할인\n· 굿럭해외공항짐배송및보관10% 할인\n· 굿럭인천공항입국시교통약자짐찾기대행및배송서비스할인\n· Trip.com 최대6%할인\nHotel\nA i r\n&\nAirport\nTravel\n· 비자엘리트다이닝최대20% 할인혜택제공(~26.8.31)\n· 트립쿠폰멤버십무료제공\n· 하와이올로마나골프장그린피15% 할인및연습볼1버켓무료\n· Visa 컨시어지제공\n전화080-4880-880, 홈페이지www.concierge-asia.visa.com\n카카오톡“Visa 컨시어지” 채널추가\nDining &\nLifestyle\nShopping\n· 현대백화점면세점골드멤버십제공(최대15% 할인)\n· Mitsui Outlet Park에서최대10%할인(~27.11.30)\nVisa\nPlatinum\n공통서비스\n* 아래의Visa Platinum서비스는Visa Platinum 등급카드\n소지자에게공통으로제공됩니다.\n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용\n평점이하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이\n발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가\n발생할수있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등\n적용되며, 법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) \n유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부\n계약기간의유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융\n가계자금대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관\n가중평균대출금리(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도\n등에영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기\n바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금\n결제일에상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가\n있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐\n제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를\n참고하시거나고객센터로문의바랍니다.\n여신금융협회심의필제2026-C1a-05257호( 2026.04.14 ))/ 준법심의L-26-0468 (2026.03.16)\n* 본Visa Platinum 서비스안내서는회원이발급받은카드\n상품안내장, 이용약관과함께교부되오니, 카드이용과관련한\n유의사항을반드시확인하시기바랍니다.\n* 본서비스는Visa에서제공하는서비스로, 프리미엄서비스에\n대한구체적내용, 적용기준및유의사항등\nhttp://www.visakorea.com → ‘Visa 플래티늄’에서사전에\n반드시확인해주시기바랍니다.\n* 본Visa Platinum 서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:37.985564+00	SYSTEM	2026-11-03 05:21:37.985564+00	SYSTEM
20261103_000022	2	20261103_000068	2	\N	BODY	1	3084	Visa Platinum 선택서비스중특급호텔발렛파킹, 인천공항발렛파킹서비스를하나카드에서제공합니다.\nVisa Platinum 01 선택서비스\n특급호텔발렛파킹서비스\n서비스혜택\n- 국내주요특급호텔무료발렛파킹서비스제공\n이용조건\n- 호텔통합월3회서비스제공\n- CLUB SK 카드, CLUB SK카드hiplus 선불하이패스,\n토스(Toss) 하나카드Ver.2.0 은\n지난달(1일~말일) 국내외일시불/할부30만원이상이용시서비스제공\n(최초카드사용등록후다음달말일까지는지난달카드이용금액30만원미만시에도\n서비스제공)\n이용방법\n- 주차시호텔현관에서도어맨에게발렛파킹요청후주차권수령\n- 차량인수시도어맨에게주차권과비자프리미엄카드제시\n- 호텔단말기를통해서비스이용가능여부확인후서비스제공\n대상호텔\n서울\n그랜드워커힐서울\n그랜드하얏트서울\n노보텔앰배서더서울강남\n노보텔앰배서더서울동대문\n비스타워커힐서울\n그랜드머큐어임피리얼팰리스서울\n앰배서더서울풀만호텔\n르메르디앙&목시서울명동\n서울드래곤시티\n서울외\n그랜드하얏트인천\n파크하얏트부산\n그랜드머큐어앰배서더창원\n호텔인터불고대구\n유의사항\n- 상기서비스는국내에서발급된비자프리미엄카드회원으로해당호텔의객실\n및식음료업장(연회장제외) 이용을위해내방한회원본인에한해\n제공함을원칙으로합니다.\n- 상기서비스는이용시호텔정책에따라해당호텔을이용한영수증제시를요청\n할수있으며, 영수증미지참시에는별도의발렛파킹비용과주차금액이청구될\n수있습니다.\n- 서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하셔야합니다.\n- 상기서비스이용시발렛파킹비용및1일3시간이내의주차비가무료로제공\n됩니다. 이용시간초과시주차금액이별도로부과될수있으며, 이는별도로\n부담하셔야합니다.\n- 일부호텔은반드시당일일정금액의영수증지참시에만서비스가제공됩니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시\n기바랍니다.\n인천공항발렛파킹서비스\n서비스혜택\n- 인천공항무료발렛파킹서비스제공(제1여객터미널, 제2여객터미널)\n이용조건\n- 공항통합월3회서비스제공\n- CLUB SK 카드, CLUB SK카드hiplus 선불하이패스,\n토스(Toss) 하나카드Ver.2.0 은\n지난달(1일~말일) 국내외일시불/할부30만원이상이용시서비스제공\n(최초카드사용등록후다음달말일까지는지난달카드이용금액30만원미만시에도\n서비스제공)\n이용방법\n- 제1여객터미널\n- 제2여객터미널\nVisa\nPlatinum 01\n선택서비스\n그랜드조선부산\n이용방법\n· 비자프리미엄카드회원을위한컨시어지서비스제공\n* 플래티늄컨시어지82-2-6240-3678\n* 운영시간: 연중무휴24시간운영\nConcierge : 컨시어지서비스\n주차시: 1. 인천공항제1여객터미널발렛전용차로및안내표지판을따라\n지하1층단기주차장A구역으로이동\n2. Maxerve 유니폼착용공식대행직원에게발렛요청후모바일\n차량접수증수령(카카오톡접수증발송)\n출차시: 1. 주차대행접수증에안내된출차장소로이동(지하3층A32 또는H38)\n2. 유인정산소모바일접수증제시“제휴카드승인“ 후차량인수\n3. 주차장출차시, 추자요금별도정산\n주차시: 1. 제2여객터미널발렛전용차로및안내표지판을따라\n지하1층서편단기주차장으로이동\n2. 파란색유니폼착용한공식대행직원에게발렛요청후\n모바일접수증수령(카카오톡/문자수신)\n출차시: 1. 접수증에표시된연락처를통해접수번호및차량번호확인후출차진행\n2. 접수증(또는차량보관증)에명기된구역(동편단기주차장지하1층)\n고객대기실에서비자프리미엄카드와접수증제시\n3. 서비스이용가능여부확인후발렛파킹서비스무료제공\n(출차시주차요금별도정산)\n유의사항\n- 서비스제공횟수초과시발렛파킹비용을별도로부담하셔야합니다.\n- 상기서비스는발렛파킹비용에만적용되므로, 주차비용은별도로정산하셔야\n합니다.\n- 3층여객터미널승용차전용도로에서5분이상정차시과태료가부과될수\n있습니다.\n- 사전예약고객대상으로서비스제공되며, 현장상황에따라당일서비스요청\n고객도접수가가능합니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시기\n바랍니다.\n* Visa 프리미엄서비스에대한구체적내용, 적용기준및유의사항\n등은Visa 홈페이지(www.visakorea.com) 또는하나카드홈페이지\n에서확인해주시기바랍니다.\n* 본Visa 프리미엄서비스안내서는회원이발급받은카드상품안\n내장, 이용약관과함께교부되오니, 카드이용과관련한유의사항\n을반드시확인하시기바랍니다.\n* 본Visa 프리미엄서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용평점이\n하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가발생할수\n있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등적용되며, \n법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) 유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부계약기간의\n유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융가계자금\n대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관가중평균대출금리\n(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도등에\n영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금결제일에\n상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를참고하시거나\n고객센터로문의바랍니다.\n아래의대상카드발급시Visa Platinum01\n선택서비스가제공됩니다.\n여신금융협회심의필제2026-C1a-05552호( 2026.04.17 ) /준법심의L-26-0472 (2026.03.17)\n플래티늄Royal카드\nCLUB SK 카드\nCLUB SK카드hiplus 선불하이패스\nPlatinum카드\nCLUB PRIMUS 카드\nSK Broadband Smart BIZ카드\nSK 패밀리카드\n토스(Toss) 하나카드Ver.2.0\n사전예약처\n인천공항1터미널\nhttps://Maxerve-mparking.com/valet\n인천공항2터미널\nhttps://valet.amanopark.co.kr\n	\N	RAW	PAGE_V1	\N	2026-11-03 05:21:37.985564+00	SYSTEM	2026-11-03 05:21:37.985564+00	SYSTEM
\.


--
-- TOC entry 4379 (class 0 OID 20816)
-- Dependencies: 362
-- Data for Name: card_doc_page; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_doc_page (card_doc_id, page_no, page_raw_txt, page_char_cnt, page_txt_sha256, page_layer_cd, page_extractor_nm, page_extractor_ver, page_note, create_date, create_user_id, update_date, update_user_id) FROM stdin;
20261101_000002	1	[연회비] 없음 \n[발급브랜드] 국내전용, 국내외겸용(Mastercard)\n[발급대상] 7세부터 발급 가능 \n[후불교통] 선택가능(12세부터 발급 가능)\n* ONE PICK STYLE 하나 체크카드의 결제계좌는 하나은행 계좌에 한하여 이용 가능합니다. \n서비스 제공 안내    \n \n서비스 제외 대상\n- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외\n- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외\n실적 산정 기준\n- 지난달 1일부터 말일(승인 시점 기준)까지 국내외 일시불 이용금액 10만원/20만원 이상 시\n ONE MORE 서비스 제공\n실적 제외 대상\n- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외\n실적과 관계없이 서비스 제공\n- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공\n * ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공\n서비스 제공 방법\n- 캐시백 제공 시점 : 매출일자로부터 5영업일 이내 결제계좌로 입금 예정\n- 매출 접수된 국내 일시불 이용금액에 따라 캐시백 혜택을 제공하며, 매출 취소 시 취소가 접수된\n 월에서 실적 및 캐시백 제공 금액 차감 반영\n- 후불교통요금 등 무승인 거래(카드사의 승인없이 이용금액이 카드사에 접수됨)의 경우 매출이 \n 접수된 월의 이용금액에 반영\n- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공\n- 가맹점 정보가 해당 업체가 아닌 결제대행업체(PG) 또는 간편결제 전용 가맹점으로 확인되는 \n 경우 ‘결제대행업체’ 또는 ‘간편결제’ 가맹점으로 분류되어 각 서비스 영역에 따른 혜택이 제공됨\n 자세한 사항은 하나카드 고객센터(1800-1111)에 문의하시기 바람\n ※ 예시) 편의점에서 네이버페이로 결제 시 가맹점명이 ‘네이버페이’인 경우 \n               “편의점” 가맹점이 아닌 ‘간편결제’ 가맹점으로 분류\n서비스 영역\nONE PICK\n(편의점, \n 카페)\nSTYLE\n(쇼핑\n서점/문구,\n패션)\nCU, GS25, \n세븐일레븐\n다이소, 올리브영\n교보문고, 영풍문고,\n알라딘, yes24,\n아트박스\n무신사, 에이블리\n메가MGC커피, \n이디야커피, \n컴포즈커피\n결제 건당\n3천원 이상 시 \n100원\n/\n결제 건당\n1만원 이상 시 \n500원\n일 1회\n/ 월 10회\n월 5천원\n대상 가맹점\n캐시백 조건\n캐시백 한도\n횟수 한도\n금액 한도\n(지난달 실적 조건 없는 서비스)\nONE PICK\nSTYLE\n후불교통 기능 이용 안내\n* 발급대상 : 12세 이상 손님 (단, 연체 등 특이 정보가 있는 경우 발급이 제한될 수 있음)\n* 이용 시 유의사항 (후불교통기능 선택 시에만 해당) \n - 후불교통 이용금액은 손님 계좌에서 즉시 출금되지 않으며, 손님이 신용공여기간동안 이용한\n    금액이 결제일에 일시 출금됨\n - 후불교통/하이브리드 서비스 동시 이용 시에는 하이브리드 서비스(소액신용거래)에서 \n    결제 및 청구됨\n하이브리드 서비스 이용 안내\n하이브리드 서비스에 대한 상세한 내용은 하이브리드 서비스 신청 후 발송되는\n“하나카드 체크카드 하이브리드 서비스 약관”을 통해 확인 가능함\n미성년자 체크카드 이용 안내\n* 7~13세 미성년자 체크카드 발급 시 법정대리인 동의가 필수이며, \n 1일 3만원/1개월 30만원의 이용 한도가 적용됨\n (14세가 경과하면 고객센터에 요청하여 상향 가능)\n* 후불교통 체크카드는 12~17세 이상 손님은 법정대리인 동의 하에 발급 받을 수 있으며,\n 월 이용한도 10만원/전체 카드사 기준 1인 1매만 소지 가능\n (18세 이상의 미성년자는 법정대리인 동의 불필요)\n일 1회\n/ 월 30회\n월 5천원\n(지난달 실적 10만원/20만원 이상 시 받는 서비스)\n서비스 영역\n대상 가맹점\n서비스 방법\n서비스 한도\n지난달 실적\n대중교통\n버스, 지하철\n월 1천원\n5%\n캐시백\n10만원\n놀이공원\n에버랜드, 롯데월드\n월 1회 \n/ 연 2회\n50% \n현장할인\n(1인 1매)\n20만원\n최초 발급 월에는\n서비스 미제공\nONE MORE\n하나 체크카드\n하나 체크카드\nONE PICK\nSTYLE\n	2482	23aefeae399e08b69720fe6f45ce85d7e980f8ad074a33bd2f045b39c3c4798c	MIXED	PyMuPDF	1.28.2	\N	2026-11-01 01:13:59.122334+00	SYSTEM	2026-11-01 01:13:59.122334+00	SYSTEM
20261101_000002	2	부가서비스 유지 및 변경 안내    \n \n· 카드이용 시 제공되는 포인트 및 할인혜택 등의 부가서비스는 카드 신규 출시(2026년 3월 30일) \n 이후 3년 이상 축소·폐지 없이 유지됩니다.\n· 다만, 다음과 같은 사유가 발생한 경우 카드사는 부가서비스를 변경할 수 있습니다.\n ①: 카드사의 휴업·파산·경영상의 위기 등에 따른 불가피한 경우\n ①의2: 제휴업체의 휴업·파산·경영상의 위기로 인해 불가피하게 부가서비스를 축소·변경하는\n  \n \n경우로서 다른 제휴업체를 통해 같은 종류의 유사한 부가서비스 제공이 불가한 경우\n ②: 제휴업체가 카드사의 의사에 반하여 해당 부가서비스를 축소하거나 변경 시, 당초 부가서비스에 \n  \n상응하는 다른 부가서비스를 제공하는 경우 \n ③: 부가서비스를 3년 이상 제공한 상태에서 해당 부가서비스로 인해 상품의 수익성이 현저히\n  \n낮아진 경우 \n· 카드사가 부가서비스를 변경하는 경우 변경사유, 변경내용 등을 다음 각호에서 정하는 기간에 \n 따라 서면교부, 우편 또는 전자우편, 전화 또는 팩스, 휴대폰 메시지 또는 이에 준하는 전자적 \n 의사표시 중 서로 다른 2가지 이상의 방법 으로 고지하여 드립니다. 다만, 제2호의 경우 부가 \n 서비스 변경일 6개월 이전부터는 서면교부, 우편 또는 전자 우편, 전화 또는 팩스, 휴대폰 메시지 \n 또는 이에 준하는 전자적 의사표시 중 서로 다른 2가지 이상의 방법으로 매월 고지하여 드립니다.\n 1. ①, ①의2, ②: 사유발생 즉시\n   2. ③: 부가서비스 변경일 6개월 이전\n· 상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 \n 하락할 수 있습니다. \n· 개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다. \n· 일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 \n 있습니다. \n· 연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n  ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시: 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시: 거래 발생 시점의 동일한 할부 계약기간의 \n  유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 \n  가계자금대출금리* 중 높은  금리 적용\n  * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 \n     가중평균대출금리(신규대출 기준)\n         1800-1111\n하나카드 고객센터\n준법심의 L-26-0542(2026.04.29) / VI 260429-71\n결제이용대금 결제 안내    \n \n· 결제 계좌 개설기관의 영업 마감시간(16시) 이후 결제 계좌에 입금된 금액에 대해서는 결제 계좌 \n 개설 기관의 사정에 따라 당일 출금되지 못하여 연체로 처리 될 수 있으므로 유의하시기 바랍니다. \n 자동납부 업무 마감시간 이후에는 하나카드 홈페이지/모바일 등에서 즉시결제 또는 가상계좌입금 \n (송금납부)을 통해 당일 결제가 가능합니다.\n ※ 세부내용은 하나카드 홈페이지 [고객센터-카드이용안내-결제안내] 및 모바일 앱 [고객센터 탭] 참고\n•결제은행에 따라 안정적인 서비스 제공을 위한 전산 시스템 점검 시에는 23:00~06:00 중 체크카드 \n 이용이 일시적으로 제한될 수 있습니다.\n해외 결제 및 기타 안내    \n \n① 결제은행이 하나은행인 경우, 해외 이용 시(해외사이트 거래 포함) 미화(USD)기준 거래 금액에 \n \n카드승인시점의 하나은행이 고시한 전신환매도율을 적용한 금액으로 카드 승인일에 회원의 계좌 \n \n잔액에서 지급정지 되고, 이후 매출표가 접수되면 지급정지 금액 계산시와 동일한 방법으로 산정된\n \n미화(USD)금액에 접수일의 하나은행 최초고시 전신환 매도율을 적용한 원화금액으로 회원의 \n \n계좌에서 출금됩니다. 단, 1회 승인금액 100만원 이상의 거래(단, T&E업종 제외), 또는 카드사가 \n \n정한 특정브랜드(BC 등) 및 상품의 카드이용대금은 미화(USD) 기준 거래 금액에 카드 승인시점의\n \n하나은행이 고시한 전신환매도율을 적용한 원화금액으로 회원의 계좌잔액에서 즉시 인출됩니다.\n \n* T&E 업종: Travel and Entertainment 업종, 여행과 여가 관련 업종(항공, 호텔, 숙박, 렌터카 등)\n② ①의 인출금액에는 국제브랜드사가 부과하는 국제브랜드수수료(Mastercard 1.0%)와 \n \n하나카드가 부과하는 해외서비스수수료(US$0.5)가 포함됩니다.\n· 해외 가맹점에서 원화로 결제할 경우(DCC) 추가수수료가 발생하므로 \n 현지 통화 또는 미화로 거래하시기 바랍니다.\n· 해외원화결제서비스(DCC) 사전차단 서비스 이용 방법: 콜센터, 홈페이지/모바일App\n (마이페이지/라이프-이용안심서비스-해외원화결제(DCC) 차단서비스)\n· 일부 해외 거래 시 IC칩 비밀번호(PIN)를 요구하는 경우가 있으므로 출국 전 반드시 \n IC칩 비밀번호(PIN) 등록여부를 확인하시기 바랍니다.\n* 해외 이용 시 청구금액 산출 방법\n* 해외 이용 시 청구금액 \n   = (거래미화금액 × 전신환매도율¹) + 국제브랜드수수료² + 해외서비스수수료³\n \n1. 전신환매도율 : ① 접수일의 하나은행 최초고시 전신환매도율\n \n                              ② 즉시출금은 승인시점의 하나은행 전신환매도율\n \n2. 국제브랜드수수료 = (거래미화금액 × 국제브랜드이용수수료율(Mastercard 1.0%)) \n                                            × 전신환매도율 \n \n3. 해외서비스수수료 = (거래건수 × US$0.5) × 전신환매도율\n* 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 \n 영향을 미칠 수 있습니다.\n* 계약체결 전 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n* 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 \n 제한 될 수 있습니다.\n* 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 \n 상환하여야 합니다.\n* 소비자는 금융소비자보호법에 따라 해당 상품 또는 서비스에 대하여 \n 설명을 받을 권리가 있습니다.\n* 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다. \n* 자세한 내용은 하나카드 홈페이지(www.hanacard.co.kr)를 참고하시거나\n  고객센터로 문의 바랍니다.\n	3181	16e6bb7c10641adc9bc311ada24d25088b1fe5796a663b59c10b91b90b044c05	MIXED	PyMuPDF	1.28.2	\N	2026-11-01 01:13:59.122334+00	SYSTEM	2026-11-01 01:13:59.122334+00	SYSTEM
20261102_000003	1	Classic\nClassic\nPremium is Already Brilliant,\nJADE\n제이드 클래식 상품설명서\n	65	2d8af1dd76d85a2f3d95a0cdfcfcfd6cbfd10a4e7a4d4a7cfe7b8e749e635a2e	TEXT	PyMuPDF	1.28.2	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000003	2	Premium Voucher \nAirport\nReward\n[공통] 서비스 실적 조건 \n가족카드 이용 안내\n연회비\nPREMIUM VOUCHER \n바우처 5가지 중 1가지를 선택하여 이용 (연 1회) \nHOTEL\n호텔 다이닝 10만원 현장 할인\nSHOPPING\n신세계 상품권 10만원 모바일 교환권\nAUTO\nSK 모바일 주유권 10만원 \nFOOD & BEVERAGE\n배달의 민족 모바일 상품권 10만원\nFINANCE \n9만 하나머니   \n서비스 제공 기간\n서비스 실적 조건\n이용 방법\n\n유의 사항\t\n1\n1차년도 : 카드 발급월 포함 12개월\n2차년도 이후 : 전년도 바우처 제공 기간 종료 후 12개월 \n1차년도 : 카드 발급 후 50만원 이상 이용 시\n2차년도 이후 : 바우처 제공 기간 직전 1년간 600만원 이상 이용 시 \n⦁\t HOTEL(호텔 다이닝 10만원 할인) 현장 할인바우처는 제휴 호텔 \n\t 다이닝 가맹점에서 본인 회원 명의의 ‘JADE Classic’ 카드 제시 후 \n\t 10만원 이상 결제 시, 10만원 현장할인 적용\n\t ※\t제휴 호텔 다이닝 상세 이용 방법 및 사용처, 이용가능 여부는 \n\t \t 서비스 이용 전 하나카드 홈페이지 공지사항(www.hanacard.co.kr)\n\t \t 을 반드시 확인 후 이용\n⦁\t SHOPPING(신세계 상품권 10만원 모바일 교환권) 바우처는\n\t 전국 이마트 매장에서 신세계 상품권으로 교환 후 신세계 상품권 \n\t 사용처에서 이용 가능(이마트 매장에서만 교환 가능)\n⦁\t AUTO(SK 모바일 주유권 10만원) 바우처는 SK주유소 및 충전소에서\n\t 주유/충전 금액 5만원 이상 이용 시, 1매 이용 가능 (5만원권×2매 제공)\n\t ※ 주유 1회에 2매 동시 사용 불가하며 주유 앱을 통해 결제하는 경우 \n\t \t 서비스 제공 불가\n⦁\t FOOD & BEVERAGE(배달의 민족 모바일 상품권 10만원) 바우처는\n\t 배달의 민족 앱에서 등록 후 사용 가능하며, 배달 음식 및 배달팁에 대한\n\t 결제 수단으로 잔액 내 사용 가능\n⦁\t FINANCE 바우처는 신청일 기준 익월 10 영업일 이내 적립\n⦁\t 카드 발급 본인 회원에 한하여 제공됩니다.(가족카드 회원 제공 불가)\n⦁\t 제공기간을 경과한 미사용바우처는 자동 소멸되며 \n\t 다음해로 이월되지 않습니다.(FINANCE 바우처 제외)\n⦁\t 바우처 선택 및 변경은 하나카드 고객센터에서 가능합니다.\n⦁\t 바우처 변경은 신청 당일에만 가능하며, 신청 및 이용한 바우처는\n\t 취소할 수 없습니다.\n	1226	9786453560169ac12ae82e000f20261da32e81fa9b56859205ac1bdfd638403e	TEXT	PyMuPDF	1.28.2	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000003	3	서비스 제공 기간\n서비스 실적 조건\n이용 방법\n유의 사항\n1차년도 : 카드 발급월 포함 12개월\n2차년도 이후 : 전년도 서비스 제공 기간 종료 후 12개월 \n1차년도 : 지난달 1일부터 말일까지 50만원 이상 이용 시\n2차년도 이후 : 서비스 제공 기간 직전 1년간 600만원 이상 이용 시\n⦁\t 최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 \n\t 이용금액 50만원 미만 시에도 서비스 제공\n⦁\t THE LOUNGE 앱 설치 및 ‘JADE Classic’카드를 등록 후\n\t 라운지 이용권 다운로드\n⦁\t 제휴 라운지에 THE LOUNGE 이용권과 함께 \n\t 여권 및 항공 탑승권 제시 후 이용\n⦁\t 본인카드 회원과 라운지 입장 동반인/가족카드 회원 이용 횟수가 \n\t 합산되어 통합 연 3회, 일 3회 서비스 제공 됩니다.\n⦁\t 카드 해지 이후 다시 신규로 발급하는 경우에도 해지된 카드로 \n\t 이용한 횟수와 합산되어 통합 연 3회, 일 3회 한도로 제공됩니다.\n⦁\t 항공권 탑승자 이름, 여권 및 THE LOUNGE 앱에 등록된 \n\t 영문명이 동일해야 이용 가능합니다.\n⦁\t THE LOUNGE 앱 아이디 공유 및 라운지 이용권 양도는 \n\t 불가능합니다.\n⦁\t 다운로드(발급)받은 라운지 이용권은 ‘마이페이지 이용권 보관함’에\n\t 자동 저장되어 발급 후 24시간까지 유효하고 미사용시 자동 취소되어\n\t 이용 가능 횟수는 자동 복원됩니다.\n⦁\t 라운지 입장시 동반인 현장 결제 및 기타 사항은 각 라운지 규정을\n\t 준수합니다\n⦁\t 이용 가능 라운지 및 사용방법 등 서비스 관련 상세 내용은\n\t THE LOUNGE 홈페이지 및 고객센터에서 확인 가능합니다.\n\t ※ THE LOUNGE 홈페이지 : www.theloungemembers.com\n\t ※ 고객센터 : (국내) 1811-7437, (해외) +82-2-2664-7436\n전세계 공항 라운지 무료 이용\n(본인/가족/동반자 통합 연 3회, 일 3회)\n* 국내외겸용카드로 발급 시 서비스 제공(국내전용카드 보유 회원 제외)\nAIRPORT\nREWARD\n기본 적립\n국내외 가맹점 1% 하나머니 적립 제공\n(지난달 실적 조건 없음, 적립 한도 제한 없음)\n특별 적립\n영역별 1.5%~1.2% 하나머니 적립 제공\n(지난달 실적 50만원 이상, 월 통합 적립 한도 \n10만 하나머니)\n* \t해외결제 시 수수료가 발생할 수 있으니, [해외결제 및 기타 안내] 참조\n* \t항공/면세 : 공식 홈페이지(온라인/모바일앱) 및 오프라인 매장을 통한\n\t 결제 시에만 서비스 제공, 여행사, 구매대행사이트, 온라인쇼핑몰\n\t (오픈마켓, 소셜 등)을 통한 결제건은 서비스 제외됨\n*\t 여행/온라인쇼핑몰: 공식 홈페이지(온라인/모바일앱)를 통한 결제 시에만\n\t 서비스 제공되며, 몰 이동을 통해 다른 온라인 쇼핑몰로 이동하여\n\t 결제하는 경우는 서비스 제외됨\n\t ※ 여행 - 하나투어 가맹점은 오프라인 결제 시에도 서비스 제공됨\n*\t 백화점/아울렛/마트/주유 : 오프라인 결제건에 한하여 서비스 제공\n\t ※ 백화점/아울렛/마트의 상설·임대 매장은 서비스 제외됨\n\t ※ 마트 - 롯데마트맥스(창고형 할인매장)는 서비스 제외됨\n*\t 특별 적립과 기본 적립은 중복 제공되지 않음\n영역\n적립 대상 가맹점\n적립률적립 한도\n해외\n해외 가맹점\n1.5%\n월 통합\n10만\n하나머니\n항공\n대한항공, 아시아나 항공,\n진에어, 제주항공\n면세\n신라면세점, 롯데면세점,\n신세계면세점\n여행\n하나투어, 아고다,\n익스피디아, 호텔스닷컴\n쇼핑\n온라인\n쇼핑몰\n쿠팡, 컬리, SSG.COM, \n롯데ON, 더현대하이\n1.2%\n백화점롯데백화점, 신세계백화점, \n현대백화점, 더 현대 \n아울렛\n신세계사이먼, \n현대프리미엄, \n롯데프리미엄\n마트\n이마트, \n트레이더스 홀세일 클럽, \n홈플러스, 롯데마트\n주유\nLPG충전\n포함\nSK에너지, GS칼텍스, S-Oil, \nHD현대오일뱅크, 알뜰주유소\n2\n3\n	1897	7dd5502c1c7d6e10fe6253a16abc207c887e245fee2de55710c8590083ef2f31	TEXT	PyMuPDF	1.28.2	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000003	4	디지털 \n컨텐츠\n50% 적립\n디지털 컨텐츠 자동납부 시, \n50% 하나머니 적립 제공\n(지난달 실적 50만원 이상, 월 적립 한도 1만 하나머니)\n* \t자동납부 결제 건만 서비스 제공되며, 포인트, 캐시, 머니충전, \n\t 컨텐츠 개별 결제, 간편결제 및 앱스토어를 통한 결제건(인앱결제)은\n\t 서비스 제외됨\n영역\n적립 대상 가맹점\n적립률\n적립 한도\n디지털\n컨텐츠\n넷플릭스, 디즈니플러스,\n유튜브 프리미엄, Wavve, 티빙, \n멜론, 지니, FLO, 스포티파이\n50%\n1만\n하나머니\n커피\n50% 적립\n커피 이용금액 50% 하나머니 적립 제공\n(지난달 실적 50만원 이상, 월 적립 한도 5천 하나머니)\n*\t 스타벅스 오프라인 결제, 공식앱 또는 공식 홈페이지를 통한 주문 및 \n\t 결제에 한하여 서비스가 제공되며, 별개의 배달앱 혹은 식당 예약앱을 \n\t 통한 결제는 서비스 제외됨 \n*\t 대형시설물(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소, 공항, 호텔, \n\t 리조트, 역사, 마트) 입점 점포 및 임대 매장은 서비스 제외됨\n영역\n적립 대상 가맹점\n적립률\n적립 한도\n커피\n스타벅스\n50%\n5천\n하나머니\n택시\n50% 적립\n택시 이용금액 50% 하나머니 적립 제공\n(지난달 실적 50만원 이상, 월 적립 한도 5천 하나머니)\n* \t카카오T와 UT의 경우 공식 앱 또는 홈페이지를 통한 택시 결제건에\n\t 한하여 서비스가 제공되며, 대리운전·퀵 서비스·주차·기차 등\n\t 택시 이외의 결제건은 서비스가 제외됨\n영역\n적립 대상 가맹점\n적립률\n적립 한도\n택시\n택시업종, 카카오T, UT\n50%\n5천\n하나머니\n서비스 제공 기준\n⦁\t 모든 적립 서비스는 하나카드에 등록된 가맹점 및 가맹점 업종\n\t 기준에 따라 제공\n⦁\t 후불교통요금 등 무승인거래(카드사의 승인없이 이용금액이 카드사에\n\t 접수됨)의 경우 매출이 접수된 월의 이용금액에 반영\n⦁\t 매출 접수된 국내외 일시불/할부 이용금액에 따라 적립 혜택을 제공하며, \n\t 매출취소 시 취소가 접수된 월에 적립된 금액을 차감 반영\n⦁\t 할부 이용 전체 금액을 할부 이용한 달의 이용금액으로 반영\n⦁\t 해외 매출은 최종 원화 청구금액에 대하여 적립 제공\n⦁\t 적립 영역이 중복 되는 경우 적립금액이 큰 서비스가 우선 적용\n\t (매출 건당 하나의 서비스만 적용)\n⦁\t 특별적립, 디지털컨텐츠 50% 적립, 커피 50% 적립, 택시 50% 적립의\n\t 월 적립 한도를 모두 소진 후, 발생하는 추가 매출은 기본적립 제공\n서비스 제외 대상\n⦁\t 국세, 지방세, 수도/전기요금, 그외 공과금(우편요금, 과태료, 범칙금, \n\t 벌금, 국가/공공기관/공공단체가 부과하는 부담금), 도시가스 요금, \n\t 아파트관리비, 국민연금/고용보험료/산재보험료/건강보험료 납부 금액, \n\t 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 \n\t 기프트카드 구매, 선불카드 및 선불전자지급수단(하나머니 등) 충전 금액, \n\t 부동산임대료, 무이자 할부 이용금액\n적립 기준 \n⦁\t 적립기준: 하나머니(1하나머니=1원)\n⦁\t 하나머니 적립일 : 매출 접수된 다음날 하나머니가 적립됨\n⦁\t 소수점 이하 금액은 반올림됨\n※\t하나머니란?\n\t 하나카드의 하나머니 가맹점, 상품권 교환, 공익기부 등 \n\t 다양한 사용처에서 사용하시거나 연회비, 카드대금 등을 납부하실 때\n\t 사용하실 수 있습니다. (하나카드 홈페이지 ≦ ‘포인트’ 메뉴 참고)\n서비스 실적 조건\n⦁\t 기본적립 : 서비스 실적 조건 없음 \n⦁\t 특별적립 / 디지털컨텐츠 50% 적립 / 커피 50% 적립 / 택시 50% 적립\n\t : 지난달 1일부터 말일까지 50만원 이상 이용 시 서비스 제공\n⦁\t 최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 이용금액 \n\t 50만원 미만 시에도 서비스 제공\n4\n5\nREWARD\n	1849	02312d1085a70f5b6f316c44c1d7574bc43441d49b4618dfac0e05bec5f0e37e	TEXT	PyMuPDF	1.28.2	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000003	5	[공통] 서비스 실적 조건 \n가족카드 이용 안내\n실적 산정 기준\n⦁\t 국내외 일시불, 할부 이용금액 기준으로 산정됩니다.\n⦁\t 하나카드에 등록된 가맹점 및 가맹점 업종으로 기준으로 산정\n실적 제외 대상\n⦁\t 국세, 지방세, 수도/전기요금, 그외 공과금(우편요금, 과태료, 범칙금, \n\t 벌금, 국가/공공기관/공공단체가 부과하는 부담금), 도시가스 요금, \n\t 아파트관리비, 국민연금/고용보험료/산재보험료/건강보험료 납부 금액, \n\t 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 \n\t 기프트카드 구매, 선불카드 및 선불전자지급수단(하나머니 등) 충전 금액, \n\t 부동산임대료\n브랜드 서비스\n⦁\t 이 상품은 선택하신 브랜드에 따라 국제 브랜드 서비스가 제공됩니다.\n⦁\t 해당 국제 브랜드 서비스는 별도 안내장 및 하나카드 홈페이지\n\t (www.hanacard.co.kr)를 참조해 주시기 바랍니다.       \n\t\n- Visa : Visa Signature 02 유형\n\t - Mastercard : Mastercard World 03 유형\n\t - Amex : Amex Platinum 03 유형\n\t - UPI : UPI Diamond 02 유형\n⦁\t 국제 브랜드 서비스의 세부 내용 및 유의사항은 국제 브랜드 홈페이지를    \n\t 통해 확인하시기 바랍니다.  \n\t\n- Visa : www.visakorea.com\n\t - Mastercard : www.mastercard.co.kr\n\t - Amex : www.americanexpress.com/ko-kr/network\n\t - UPI : www.unionpaypremium.co.kr\n연회비 청구 및 \n반환 기준\n⦁\t 연회비 청구기준 : 카드별(본인/가족) 카드 발급일(발급 첫해에는 \n\t 카드사용등록일)이 속한 카드이용기간의 첫 결제일에 청구되며, \n\t 카드별 발급 시점을 기준으로 1년 단위로 청구됩니다.\n⦁\t 연회비 반환기준 : 이미 납부한 연회비에서 카드 발급 및 배송 비용(발급 \n\t 첫 해 연회비에 한정), 부가 서비스 제공에 소요된 비용을 차감한 후 카드별\n\t (본인/가족) 계약을 해지한 날부터 잔여기간에 대하여 일할 계산됩니다.\n⦁\t 연회비 반환시기 : 카드별(본인/가족) 해지일 기준 10영업일 이내 \n\t 결제계좌로 입금됩니다. 다만, 부가서비스 제공 상품의 경우 카드별 \n\t 해지일 기준 다음 다음달 5영업일에 입금됩니다.\n구분\n본인\n가족\n기본\n제휴\n총 연회비\n기본\n제휴\n총 연회비\n국내외겸용 \n(Visa, Mastercard,\nAmex)\n20,000\n100,000\n120,000\n20,000\n10,000\n30,000\n국내외겸용 \n(UPI)\n20,000\n95,000\n115,000\n20,000\n5,000\n25,000\n국내전용\n20,000\n95,000\n115,000\n20,000\n5,000\n25,000\n연회비\n가족카드 이용 안내\n⦁\t 가족카드 연회비는 각 상품별 연회비 부과 기준을 따르며\n\t 가족카드 발급매수에는 제한이 없습니다.\n⦁\t 가족카드 부가서비스의 지난달 실적, 적립 할인 한도는 본인카드와 \n\t 합산 적용됩니다.\n⦁\t 가족카드 연말정산 시 가족카드 사용금액은 가족카드 명의자\n\t [카드 앞(뒤)면에 표기된[이름]의 신용카드 등 사용금액으로 포함됩니다.\n⦁\t 연간 소득금액기준은 국세청 기준에 따릅니다.\n⦁\t 본인회원이 가족회원의 카드사용 내역에 대한 알림을 받고자 하는 경우\n\t 가족회원의 동의를 받아 본인회원이 고객센터(1800-1111)에\n\t 별도 신청하여야 합니다.\n⦁\t 가족카드 이용대금명세서는 본인회원이 지정한 주소와 방법으로\n\t 본인회원에게 합산되어 발송됩니다. 다만, 가족카드 이용대금명세서를 \n\t 별도 요청하는 경우에는 본인회원, 가족회원에게 별도 발송 가능합니다.\n⦁\t 가족카드 이용으로 적립된 포인트는 본인회원의 포인트에 합산되어\n\t 관리되며, 본인회원이 하나카드고객센터(1800-1111) 및 \n\t 홈페이지 > 포인트양도에서 가족으로 등록된 회원에게만 양도 가능하며,\n\t 타 회원에게 양도는 불가합니다. \n⦁\t 가족등록은 고객센터에서만 등록 가능합니다.\n⦁\t 이혼, 사망, 파양 등 가족관계 변동 시 본인회원 또는 가족회원이 \n\t 하나카드 고객센터(1800-1111) 및 홈페이지/모바일앱 > 카드관리 \n\t > 카드해지신청 에서 가족카드 정지 또는 해지 가능합니다.\n⦁\t 가족회원의 가족관계 변동 시 카드사에 즉시 통지해야 하며 가족관계 \n\t 변동이 되었음에도 가족카드를 정지 또는 해지하지 않은 경우 \n\t 본인회원에게 의도하지 않은 카드사용 및 책임이 발생 할 수 있습니다.\n⦁\t 본인회원이 요청할 경우 가족회원의 동의 없이 가족카드가\n\t 한도감액/정지/해지될 수 있습니다\n6\n7\n* 제휴 연회비는 PREMIUM VOUCHER, AIRPORT 등 서비스 제공에 소요됩니다.\n	2350	657dbbfba32037854970e0e47f533ceae4e078639ce79765ba0f52f8361ef1de	TEXT	PyMuPDF	1.28.2	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000003	6	부가서비스 유지 및 변경 안내\n·\t카드 이용 시 제공되는 포인트 및 할인 혜택 등의 부가서비스는 카드 신규 출시(2024년 02월 01일) \n\t 이후 3년 이상 축소·폐지 없이 유지됩니다.\n·\t다만, 다음과 같은 사유가 발생한 경우 카드사는 부가서비스를 변경할 수있습니다.\n   ①\t카드사 의 휴업·파산·경영상의 위기 등에 따른 불가피한 경우\n   ①의 2\t제휴업체의 휴업·파산·경영상의 위기로 인해 불가피하게 부가서비스를 축소·변경하는 경우\n\t \t\n\t\n로서 다른 제휴업체를 통해 같은 종류의 유사한 부가서비스 제공이 불가한 경우\n   ②\t제휴업체가 카드사의 의사에 반하여 해당 부가서비스를 축소하거나 변경 시, 당초 부가서비스에 \n\t \t\n상응하는 다른 부가서비스를 제공하는 경우\n   ③\t부가서비스를 3년 이상 제공한 상태에서 해당 부가서비스로 인해 상품의 수익성이 현저히 낮아진 경우\n·\t카드사가 부가서비스를 변경하는 경우 변경 사유, 변경 내용을 다음 각 호에서 정하는 기간에 따라 \n\t 서면교부, 우편 또는 전자우편, 전화 또는 팩스, 휴대폰 메시지 또는 이에준하는 전자적 의사표시 중 \n\t 서로 다른 2가지 이상 의 방법으로 고지하여 드립니다. 다만, 제 2호의 경우 부가서비스 변경일 6개월 \n\t 이전부터는 서면교부, 우편 또는 전자우편, 전화 또는 팩스, 휴대폰 메시지 또는 이에 준하는 전자적 \n\t 의사표시 중 서로 다른 2가지 이상의 방법으로  매월 고지하여 드립니다.\n  \t1. ①, ① 의2, ② : 사유발생 즉시       2. ③ : 부가서비스 변경일 6개월 이전\n여신금융협회 심의필 제 2026-C1a-10094호(2026.07.03) / 준법심의 L-26-2051(2026.06.09) / VI 260615-71\n해외결제 및 기타안내\n·\t해외 이용 시(해외사이트 거래 포함) 미화(USD) 기준 거래 금액에 접수일의 하나은행 최초 고시 \n\t 전신환 매도율을 적용한 후, 국제브랜드사가 부과하는 국제브랜드수수료(Visa 1.1%, Mastercard 1.0%, \n\t Amex 1.4%, UPI 0.8%)와 하나카드가 부과하는 해외서비스수수료(신용카드 0.2%)를 포함하여 \n\t 원화로 청구됩니다.\n\t * 해외 이용시 청구금액 = (거래미화금액×전신환매도율¹)+국제브랜드수수료²+해외서비스수수료³\n\t  1.\t전신환매도율 : 접수일의 하나은행 최초고시 전신환매도율\n\t  2.\t국제브랜드수수료 = 거래미화금액×국제브랜드 이용수수료율×전신환매도율\n\t \t\n- 국제브랜드 이용수수료율 : Visa 1.1%, Mastercard 1.0%, Amex 1.4%, UPI 0.8%\n\t  3.\t해외서비스수수료 = (거래미화금액×해외서비스수수료율 (신용카드 0.2%))×전신환매도율\n·\t해외 가맹점에서 원화로 결제할 경우(DCC) 추가수수료가 발생하므로 현지 통화 또는 미화로 \n\t 거래 하시기 바랍니다.\n·\t해외원화결제서비스(DCC) 사전차단 서비스 이용 방법 : 콜센터, 홈페이지/모바일App(마이페이지/\n\t 라이프-이용안심서비스-해외원화결제(DCC)차단서비스)\n·\t일부 해외 거래 시 IC칩 비밀번호(PIN)를 요구하는 경우가 있으므로 출국 전 반드시 IC칩 비밀번호\n\t (PIN) 등록여부를 확인하시기 바랍니다.\n결제이용대금 결제 안내\n·\t결제 계좌 개설기관의 영업 마감시간(16시) 이후 결제 계좌에 입금된 금액에 대해서는 결제 계좌\n\t 개설 기관의 사정에 따라 당일 출금되지 못하여 연체로 처리 될 수 있으므로 유의하시기 바랍니다.\n\t 자동납부 업무 마감시간 이후에는 하나카드 홈페이지 / 모바일 등에서 즉시결제 또는 가상계좌입금\n\t (송금 납부)을 통해 당일 결제가 가능합니다.\n\t * 세부내용은 하나카드 홈페이지 [고객센터-카드이용안내-결제안내] 및 모바일앱 [고객센터 탭] 참고\n*\t필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을\n\t 미칠 수 있습니다.\n*\t계약 체결 전 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n*\t신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한 될 수 있습니다.\n*\t카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n*\t소비자는 금융소비자보호법에 따라 해당 상품 또는 서비스에 대하여 \n\t 설명을 받을 권리가 있습니다.\n*\t본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다 .\n*\t자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나  \n\t 고객센터로 문의 바랍니다.\n⦁\t상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 있습니다. \n⦁\t개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n⦁\t일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n⦁\t연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, 법정 최고금리(20%)를 \n\t 초과하지 않습니다.\n\t ※\t단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n\t  -\t일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리    \n\t  -\t무이자할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리\n\t  -\t그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은 금리 적용\n\t \t * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리(신규대출 기준)\n8\n	2691	a10136b308147783d41f48535dbd6ac7a6b406d1acf95751be9126b38b8edcf4	MIXED	PyMuPDF	1.28.2	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000004	1	Visa\nSignature\n공통서비스\n서비스\n· 진에어빠른체크인및빠른짐찾기서비스(연4회, 최대4인) \n· 카타르항공최대15% 할인\n(예약기간: ~26.10.31 / 여행기간: ~27.3.31)\n· 일본항공일본행항공권5% 할인(25.10.1~26.03.31)\n· 공항의전서비스(yQ Meet & Assist) 20% 할인\n내용\n· 전세계900여개호텔Visa Luxury Hotel Collection 혜택제공\n· Hotels.com 쿠폰코드입력시최대8% 할인(숙박기간: ~27.6.30)\n· Booking.com 최대7% 월렛포인트캐시백(매월1일~15일한정)\n· Expedia 8% 할인(숙박기간: ~27.6.30)\n· IHG Hotel&Resorts 20% 할인(숙박기간: ~27.1.3)\n· Accor China 중화권호텔최소2박예약시20% 할인(~26.9.30)\n· 반얀트리최소2박숙박시20%할인\n(예약기간: ~26.5.31 / 숙박기간: ~26.8.31)\n· Ascott 프로모션기간내사용시리워드등급업그레이드\n서비스(~27.11.30)\n· 국내특급호텔(약68여개) F&B 5~20% 할인\n· 국내특급호텔(약73여개) 객실/패키지5~60% 할인\n· 국내호텔스파(약22여개) 10~20% 할인\n· 국내부티크호텔(약23여개) 객실/F&B 5~50% 할인\n· 국내특급호텔(약6여개) 로비라운지5~20% 할인\nHotel\nAir &\nAirport\nTravel\nDining &\nLifestyle\nShopping\n* 아래의Visa Signature서비스는Visa Signature 등급카드\n소지자에게공통으로제공됩니다.\n· Hertz 해외렌터카기본10% 할인및추가혜택(~26.3.31)\n· AVIS 해외렌터카최대35% 할인\n· Rentalcars.com 10% 추가할인(~26.4.30)\n· Movv 이동서비스국내1.5~3.5만원, 해외8% 할인\n· 아시아태평양공항픽업서비스\nTBR Luxury Airport Transfer 15% 할인\n· 굿럭해외공항짐배송및보관20% 할인\n· 굿럭인천공항입국시교통약자짐찾기대행및배송서비스할인\n· Trip.com 최대6%할인\n· 롯데면세점(국내)고객면세점할인및\n회원등급업그레이드혜택제공(~26.6.30)\n· 롯데면세점싱가포르차이공항고객면세점할인\n(~26.10.16)\n· 현대백화점면세점골드멤버십제공(최대15% 할인)\n· Mitsui Outlet Park에서최대10%할인(~27.11.30)\n· 비자엘리트다이닝최대20% 할인혜택제공(~26.8.31)\n· 트립쿠폰멤버십무료제공\n· 하와이올로마나골프장그린피15% 할인및\n연습볼1버켓무료\n· Visa 컨시어지제공\n전화080-4880-880, 홈페이지www.concierge-asia.visa.com\n카카오톡“Visa 컨시어지” 채널추가\n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용\n평점이하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이\n발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가\n발생할수있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등\n적용되며, 법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) \n유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부\n계약기간의유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융\n가계자금대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관\n가중평균대출금리(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도\n등에영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기\n바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금\n결제일에상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가\n있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐\n제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를\n참고하시거나고객센터로문의바랍니다.\n여신금융협회심의필제2026 - C1a - 05178호( 2026.04.13 ) / 준법심의L-26-0467 (2026.03.16)\n* 본Visa Signature 서비스안내서는회원이발급받은카드\n상품안내장, 이용약관과함께교부되오니, 카드이용과관련한\n유의사항을반드시확인하시기바랍니다.\n* 본서비스는Visa에서제공하는서비스로, 프리미엄서비스에\n대한구체적내용, 적용기준및유의사항등\nhttp://www.visakorea.com → ‘Visa 인피니트’에서사전에\n반드시확인해주시기바랍니다.\n* 본Visa Signature 서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n	2344	7baf4770d6a810cc9a006f91746d49a59ff7429ee03b5c39d16a8ffb9c6f02dc	MIXED	PyMuPDF	1.28.2	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261102_000004	2	Visa\nSignature 02\n선택서비스\nVisa Signature 선택서비스중특급호텔발렛파킹, 인천공항발렛파킹서비스를하나카드에서제공합니다.\nVisa Signature 02 선택서비스\n특급호텔발렛파킹서비스\n서비스혜택\n- 국내주요특급호텔무료발렛파킹서비스제공\n이용조건\n- 호텔통합월2회서비스제공\n- 지난달(1일~말일) 국내외일시불/할부50만원이상이용시서비스제공\n(최초카드사용등록후다음달말일까지는지난달카드이용금액\n50만원미만시에도서비스제공)\n이용방법\n- 주차시호텔현관에서도어맨에게발렛파킹요청후주차권수령\n- 차량인수시도어맨에게주차권과비자프리미엄카드제시\n- 호텔단말기를통해서비스이용가능여부확인후서비스제공\n대상호텔\n서울\n그랜드워커힐서울\n그랜드하얏트서울\n스위스그랜드호텔\n노보텔앰배서더서울강남\n더플라자\n서울드래곤시티\n노보텔앰배서더서울동대문\n반얀트리클럽앤스파서울\n비스타워커힐서울\n서울신라호텔\n오크우드프리미어코엑스센터\n그랜드머큐어임피리얼팰리스서울\nJW메리어트동대문스퀘어서울\n앰배서더서울풀만호텔\n메이필드호텔\nJW 메리어트호텔서울\n파크하얏트서울\n르메르디앙&목시서울명동\n서울외\n그랜드하얏트인천\n파크하얏트부산\n소노캄여수\n웨스틴조선부산\n그랜드머큐어앰배서더창원\n호텔인터불고대구\n인천공항발렛파킹서비스\n서비스혜택\n- 인천공항제1,2 여객터미널및김포공항국내선무료발렛파킹제공\n이용조건\n- 공항통합월2회서비스제공\n- 김포공항발렛파킹서비스는JADE Classic, JADE Prime 카드에한하여\n서비스제공(CLUB Premier, CLUB Signature 카드는서비스미제공)\n- 지난달(1일~말일) 국내외일시불/할부50만원이상이용시서비스\n제공(최초카드사용등록후다음달말일까지는지난달카드이용금액\n50만원미만시에도서비스제공)\n대상공항별이용방법\n주차시: 1. 인천공항제1여객터미널발렛전용차로및안내표지판을따라\n지하1층단기주차장A구역으로이동\n2. Maxerve 유니폼착용공식대행직원에게발렛요청후모바일\n차량접수증수령(카카오톡접수증발송)\n출차시: 1. 주차대행접수증에안내된출차장소로이동(지하3층A32 또는H38)\n2. 유인정산소모바일접수증제시“제휴카드승인“ 후차량인수\n3. 주차장출차시, 추자요금별도정산\n- 제1여객터미널\n- 제2여객터미널\n주차시: 1. 제2여객터미널발렛전용차로및안내표지판을따라\n지하1층서편단기주차장으로이동\n2. 파란색유니폼착용한공식대행직원에게발렛요청후\n모바일접수증수령(카카오톡/문자수신)\n출차시: 1. 접수증에표시된연락처를통해접수번호및차량번호확인후출차진행\n2. 접수증(또는차량보관증)에명기된구역(동편단기주차장지하1층)\n고객대기실에서비자프리미엄카드와접수증제시\n3. 서비스이용가능여부확인후발렛파킹서비스무료제공\n(출차시주차요금별도정산)\n* Visa 프리미엄서비스에대한구체적내용, 적용기준및유의사항\n등은Visa 홈페이지(www.visakorea.com) 또는하나카드홈페이지\n에서확인해주시기바랍니다.\n* 본Visa 프리미엄서비스안내서는회원이발급받은카드상품안\n내장, 이용약관과함께교부되오니, 카드이용과관련한유의사항\n을반드시확인하시기바랍니다.\n* 본Visa 프리미엄서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용평점이\n하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가발생할수\n있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등적용되며, \n법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) 유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부계약기간의\n유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융가계자금\n대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관가중평균대출금리\n(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도등에\n영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금결제일에\n상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를참고하시거나\n고객센터로문의바랍니다.\n아래의대상카드발급시Visa Signature02\n선택서비스가제공됩니다.\nCLUB Premier 카드CLUB Signature 카드\nJADE Classic 카드JADE Prime 카드\nMG+ BLACK\n여신금융협회심의필제2026-C1a-05544호( 2026.04.17 )/ 준법심의L-26-0471 (2026.03.17)\n주차시: 1. 국내선청사2층우측하늘색라인따라진입후, 오렌지색유니폼\n착용공식주차대행직원에게발렛파킹요청\n2. 차량상태점검후차량인도및차량보관증수령\n출차시: 1. 출발지항공기탑승전차량보관증에기재된연락처로출차요청\n2. 차량인수시, 접수증과프리미엄마스터카드제시후서비스\n이용가능여부확인\n3. 차량인수후출차시고객이주차요금별도정산\n- 김포공항국내선(이용가능시간05:00~21:00 / 출차는24시간가능)\n사전예약처\n인천공항1터미널\nhttps://Maxerve-mparking.com/valet\n인천공항2터미널\nhttps://valet.amanopark.co.kr\n김포공항\n(사전예약없이이용가능)\n유의사항\n- 상기서비스는국내에서발급된비자프리미엄카드회원으로해당호텔의객실\n및식음료업장(연회장제외) 이용을위해내방한회원본인에한해\n제공함을원칙으로합니다.\n- 상기서비스는이용시호텔정책에따라해당호텔을이용한영수증제시를요청\n할수있으며, 영수증미지참시에는별도의발렛파킹비용과주차금액이청구될\n수있습니다.\n- 서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하셔야합니다.\n- 상기서비스이용시발렛파킹비용및1일3시간이내의주차비가무료로제공\n됩니다. 이용시간초과시주차금액이별도로부과될수있으며, 이는별도로\n부담하셔야합니다.\n- 일부호텔은반드시당일일정금액의영수증지참시에만서비스가제공됩니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시기\n바랍니다.\n유의사항\n- 서비스제공횟수초과시발렛파킹비용을별도로부담하셔야합니다.\n- 상기서비스는발렛파킹비용에만적용되므로, 주차비용은별도로정산하셔야\n합니다.\n- 3층여객터미널승용차전용도로에서5분이상정차시과태료가부과될수\n있습니다.\n- 사전예약고객대상으로서비스제공되며, 현장상황에따라당일서비스요청\n고객도접수가가능합니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시기\n바랍니다. \n	3246	1180623294e6b0350dd332f014e9291bc7bfcdb3d20d857de4e120690090b577	MIXED	PyMuPDF	1.28.2	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
20261103_000013	2	Mastercard\nPlatinum01\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n  \n선택서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03757호 (2026.03.20) / 준법심의 L-26-0357 (2026.02.09) / VI 260327-34\nMastercard Platinum 선택서비스 중 특급호텔 발렛파킹, 인천공항 발렛파킹, 공항라운지 입장 서비스를 하나카드에서 제공합니다.\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 발렛파킹 서비스는 본인 차량에 한해 제공되는 것을 원칙으로 합니다.\n   (타인 차량에는 서비스가 제공되지 않습니다.) \n- 호텔 영업장을 이용하지 않을 경우 일부 호텔에서는 발렛파킹 비용 및 주차료가 청구될 수 있습니다.\n- 1일 2~3시간 이내의 주차비용이 발렛파킹 서비스에 포함되어 있습니다. (일부 호텔 제외)\n- 레스케이프 호텔(30,000원 이상), 호텔 코리아나(25,000원 이상), 파크하얏트 서울(20,000원 이상)의 \n   호텔 영업장(당일 영수증) 제시 시 무료 발렛파킹 서비스 이용이 가능합니다. \n   영수증 미지참 시 제휴 서비스 이용은 제한되며, 발렛파킹 서비스 이용 요금 및 별도의 주차료는 \n   고객이 호텔에 직접 지불 하셔야 합니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n특급호텔 발렛파킹 서비스\n서비스혜택\n•국내 주요 특급호텔 무료 발렛파킹 서비스 제공 \n- 호텔 발렛파킹 부스에 서비스 요청 후 주차권 수령\n- 차량 인수 시 발렛파킹 부스에 주차권과 마스터카드 제시\n- 호텔 직원 서비스 대상카드 조회\n이용방법\n이용조건\n•호텔 통합 월 3회 서비스 제공\n•내 맘대로 쁨 카드, CLUB CEO 카드, CLUB SK 카드,\n CLUB SK Point 카드는 지난달 (1일~말일) 국내외 일시불 할부 \n 30만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 30만원 미만 시에도 서비스 제공)\n•하나골드클럽멤버스Ⅱ카드는 지난달 (1일~말일) 국내외 일시불 할부 \n 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 50만원 미만 시에도 서비스 제공)\n이용조건\n이용방법\n서비스혜택\n인천공항 발렛파킹 서비스\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 여객터미널 3층 승용차전용도로에서 5분 이상 정차 시 과태료가 부가될 수 있습니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n- 본 서비스는 인천국제공항 공식 주차대행 업체인 제1여객터미널 : ㈜맥서브, \n   제2여객터미널 : 아마노코리아에 의해 제공되니 서비스 이용 시 공식 주차대행 업체인지 \n   확인하시기 바랍니다.\n인천공항 무료 발렛파킹 서비스 제공 제 1,2 여객터미널\n•통합 월 3회 서비스 제공\n•내 맘대로 쁨 카드, CLUB CEO 카드, CLUB SK 카드,\n CLUB SK Point 카드는 지난달 (1일~말일) 국내외 일시불 할부 \n 30만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 30만원 미만 시에도 서비스 제공)\n•하나골드클럽멤버스Ⅱ카드는 지난달 (1일~말일) 국내외 일시불 할부 \n 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 50만원 미만 시에도 서비스 제공)\n유의사항\n- 라운지 이용과 관련한 문의는 마스터카드 라운지 서비스 데스크를 통해 서비스를 안내 받을 수 있습니다.\n- 마스터카드 라운지 서비스 데스크 : 02-3272-3731 (운영시간: 월~금, 09:00-18:00)\n인천공항\n- 스카이허브 라운지 제1여객터미널 동편\n- 스카이허브 라운지 제1여객터미널 서편\n- 스카이허브 라운지 제1여객터미널 탑승동\n김포공항\n김해공항\n- 스카이허브 라운지 김포공항 국제선 청사\n구분\n대상 라운지\n- 스카이허브 라운지 김해공항 국제선 청사\n대상 호텔\n지방\n지역\n서울\n그랜드 워커힐 서울\n그랜드 하얏트 서울\n스위스 그랜드 호텔\n노보텔 앰배서더 서울 강남\n비스타 워커힐 서울\n서울 드래곤 시티\n서울 신라 호텔\n메이필드 호텔\n레스케이프 호텔\n호텔 코리아나\n서울가든 호텔\n파크하얏트서울\n그랜드 하얏트 인천\n파크 하얏트 부산\n호텔 오노마\n그랜드 머큐어 앰배서더 창원\n공항 라운지 입장 서비스\n서비스혜택\n•마스터카드 제휴 라운지 무료 이용 서비스 제공 \n이용조건\n•라운지 통합 일 1회 , 연 2회 서비스 제공 본인에 한해 무료\n•내 맘대로 쁨 카드, CLUB CEO 카드, CLUB SK 카드,\n CLUB SK Point 카드는 지난달 (1일~말일) 국내외 일시불 할부 \n 30만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 30만원 미만 시에도 서비스 제공)\n•하나골드클럽멤버스Ⅱ카드는 지난달 (1일~말일 국내외 일시불 할부 \n 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n 50만원 미만 시에도 서비스 제공)\n이용방법\n•라운지 안내 데스크에서 보딩패스와 마스터카드 제시 및 서비스 대상\n 카드여부 확인 후 무료 입장\n제1여객터미널\n제2여객터미널\n주차 시 : ① 지하 1층 단기주차장 A구역으로 이동 후 Maxerve 유니폼 착용 \n                   공식 주차대행 직원에게 발렛파킹 요청\n              ② 모바일 접수증 문자 발송 (카카오톡/ MMS 문자발송, \n                   문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시 : ① 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 \n                   (지하 3층 A32구역 또는 H38구역)\n              ② 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 \n                   차량 인수\n              ③ 차량 인수 후 주차요금 고객이 별도 정산\n주차 시 : ① 제2여객터미널 지하1층 서편 단기 주차장으로 진입\n              ② 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ③ 모바일 접수증 문자 발송 (알림톡/문자메세지 발송)\n출차 시 : ① 입국 후 접수증 안내에 따라 단기주차장 지하1층 \n                   동편 210번 앞 고객대기실로 이동\n              ② 출차장 정산소에서 프리미엄 마스터카드 제시 후 \n                  서비스 이용가능 여부 확인\n              ③ 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n아래 대상 카드 발급 시 Mastercard Platinum 01 선택서비스와 \nMastercard Platinum 공통서비스가 제공됩니다.\n- 하나골드클럽멤버스Ⅱ카드\n- 내 맘대로 쁨 카드\n- CLUB CEO 카드\n- CLUB SK 카드\n- CLUB SK Point 카드\n- Premium 카드\n- Premium Biz TR 카드\n- CLUB Primus 카드\n- SECRET Classic 카드\n- 스마트포인트 카드\n- 중앙일보카드\n- NEW 하나가족사랑카드\n* Mastercar 프리미엄 서비스의 서비스의 상세한 내용은 Mastercard 홈페이지\n  (http://www.mastercard.com/kr)를 통해 확인하시기 바랍니다. \n* 본 Mastercard 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 Mastercard Platinum 서비스는 기간이 명시되지 않는 한 \n   2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n	4732	4423e8e7bf7f8b10fca64d3eae0fd9ebefe4f14d35b300d2ae8b5fdbc3296c03	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:20:52.903041+00	SYSTEM	2026-11-03 05:20:52.903041+00	SYSTEM
20261103_000014	1	Mastercard\nPlatinum\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nMastercard Platinum 공통서비스\n· LANE4 AIR 서비스 3만원 할인 (왕복 예약 시 총 6만원 할인)\nHotel\nAirport\n· Trip.com 호텔 6%, 항공 3%, 액티비티 5% 할인\n· Agoda.com 8% 할인 (최대 USD 30),\n  (예약: 26.1.1~26.3.31 / 숙박: 26.1.1~26.12.31)\n· Hotels.com 8% 할인 (최대 USD 50),\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Expedia.com 8% 할인 (최대 10만원),\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Rakuten Travel 10% 할인 (최대 USD 30),\n  (예약: 26.1.1~26.12.30 / 숙박: 26.1.1~27.2.28)\n· Qatar Airways 항공권 최대 10% 할인\n· On Vacation 럭셔리호텔/크루즈 상품 5% 할인\n· Kkday 티켓/교통/액티비티 5% 할인, \n  해외투어/eSIM 10% 할인 (최대 USD 10),\n  (예약: 26.1.1~26.12.31 / 여행: 26.1.1~27.3.31)\n· Oh Show 60분 자유의 여신상 크루즈 티켓 1+1,\n  뉴욕 브로드웨이 뮤지컬 티켓 3% 할인, \n  라스베가스 쇼 및 하와이 태양의서커스 티켓 3% 할인\n· 제주도닷컴 패키지 5%, 렌터카 12%, 국내선 항공권 발권대행수수료 무료\n· Europcar 최대 15% 할인\n· 롯데렌터카 최대 제주 90%, 내륙 65% 할인 제공\n· Hertz 렌트 예약 시 10% 할인, 멤버십 무료 가입\n· 짐캐리 최대 20% 할인\n· Airalo eSIM 최대 20% 할인 (최대 USD 100)\n· 와이드모바일 와이파이도시락 15%, 도시락 eSIM/USIM 10% 할인\n· 유심사 해외 eSIM/USIM 20% 할인\nTravel\n* 본 Mastercard Platinum 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용 약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 서비스는 Mastercard 에서 제공하는 서비스로 , 프리미엄 서비스에 대한 구체적 내용, 적용기준 및 \n   유의사항 등은 http://www.mastercard.co.kr → ‘Premium Mastercard Services’에서 \n   사전에 반드시 확인하시기 바랍니다.\n* 본 Mastercard Platinum 서비스는 기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지\n   제공됩니다.\n서비스\n내용\n· 국내 특급호텔(약 39여개) F&B 5~15% 할인\n· 국내 특급호텔(약 43여개) 객실/패키지 5~50% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약 15여개) 스파 10~20% 할인\n· Trump Hotels 10% 할인 \n· Outrigger Hotels and Resorts 5% 할인\n· KA LA’I Waikiki Beach, LXR Hotels & Resorts 10% 할인 및 조식 제공\n· 코타키나발루 수트라하버 리조트 클럽 및 스위트 객실 25% 할인, \n  골드 카드 10% 할인\n· 신라면세점 골드플러스 멤버십 제공\n   (오프라인 최대 15%, 온라인 최대 20% 할인,\n    인터넷점 S.Rewards 7,000P 제공)\n· 신세계면세점 골드 멤버십 제공 (최대 15% 할인)\n· 트래블메이트 캐리어/여행용품 12% 추가 할인\n· 해외 프리미엄 아울렛 VIP 패스 제공 (10% 할인)\n· 몽쥬약국 구매 금액별 10~15% 할인 및 최대 15% 면세 혜택\n· Mastercard E-Commerce Protection 해외 온라인 직구 보험 \n   연간 최대 23만원 보상 \nShopping\n· 15개국 48개 골프장 그린피 25% 할인 (연 4회), (~6.30)\n· 코타키나발루 수트라하버 리조트 골프&컨트리클럽 그린피 본인 면제\n· LANE4 Golf 골프장 이동 서비스 5만원 할인\n· Car up 프리미엄 카 케어 서비스 20% 할인\n· 내셔널지오그래픽 트래블러 정기구독 결제 20% 할인\nGolf\nLife\n서비스\n내용\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-003747호 (2026.03.20) / 준법심의 L-26-0342 (2026.02.04) / VI 260327-33\n* 아래의 Mastercard Platinum 서비스는 Mastercard Platinum 등급 카드 소지자에게 공통으로 제공됩니다.\n	3114	1b3cb0408d945dbc5e109218a39e821d886a41fef229ecfda070c49961093cb2	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:20:57.765029+00	SYSTEM	2026-11-03 05:20:57.765029+00	SYSTEM
20261103_000014	2	Mastercard\nPlatinum04\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n  \n선택서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03876호 (2026.03.23) / 준법심의 L-26-0360 (2026.02.09) / VI 260330-33\nMastercard Platinum 선택서비스 중 특급호텔 발렛파킹, 인천/김포공항 발렛파킹 \n서비스를 하나카드에서 제공합니다.\n특급호텔 발렛파킹 서비스\n서비스혜택\n•국내 주요 특급호텔 무료 발렛파킹 서비스 제공 \n- 호텔 발렛파킹 부스에 서비스 요청 후 주차권 수령\n- 차량 인수 시 발렛파킹 부스에 주차권과 마스터카드 제시\n- 호텔 직원 서비스 대상카드 조회\n이용방법\n이용조건\n•호텔 통합 월 3회 서비스 제공\n•CLUB NOBLE 카드는 지난달(1일~말일) 국내외 일시불/할부\n    30만원 이상 이용 시 서비스 제공 (최초 카드 사용등록 후 다음달 \n    말일까지는 지난달 카드 이용금액 30만원 미만 시에도 서비스 제공)\n•CLUB Leaders 3 카드는 지난달(1일~말일) 국내 일시불/할부\n    50만원 이상 이용 시 서비스 제공 (최초 카드 사용등록 후 다음달\n    말일까지는 지난달 카드 이용금액 50만원 미만 시에도 서비스 제공)\n이용조건\n서비스혜택\n인천공항 발렛파킹 서비스\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 여객터미널 3층 승용차전용도로에서 5분 이상 정차 시 과태료가 부가될 수 있습니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n- 본 서비스는 인천국제공항 공식 주차대행 업체인 제1여객터미널 : ㈜맥서브, \n   제2여객터미널 : 아마노코리아에 의해 제공되니 서비스 이용 시 공식 주차대행 업체인지 \n   확인하시기 바랍니다.\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 발렛파킹 서비스 제공 시간은 5시부터 21시이나, 출차 서비스는 24시간 제공됩니다.\n- 본 서비스는 주차대행 업체인 ㈜하이파킹에 의해 제공되니 서비스 이용 시 공식\n   주차대행업체인지 확인하시기 바랍니다.\n인천공항 무료 발렛파킹 서비스 제공 (제 1,2 여객터미널)\n•인천/김포공항 통합 월 7회 서비스 제공\n•CLUB Leaders 3 카드에 한하여 서비스 제공\n    (CLUB NOBLE은 서비스 미제공)\n•CLUB Leaders 3 카드는 지난달(1일~말일) 국내외 일시불/할부\n    50만원 이상 이용 시 서비스 제공 (최초 카드 사용등록 후 다음달 \n    말일까지는 지난달 카드 이용금액 50만원 미만 시에도 서비스 제공)\n대상 호텔\n지방\n지역\n서울\n그랜드 워커힐 서울\n그랜드 하얏트 서울\n스위스 그랜드 호텔\n메이필드 호텔\n비스타 워커힐 서울\n서울 드래곤 시티\n서울 호텔 신라\n레스케이프 호텔\n호텔 코리아나\n콘래드 서울\n더 플라자 호텔\n몬드리안 서울 이태원\n파크하얏트 서울\nJW메리어트 호텔 서울\n노보텔 앰배서더 서울 강남\n서울 가든 호텔\n앰배서더 서울 품만 호텔\n오크우드 프리미어 코엑스\n메리어트 이그제큐티브 아파트먼트\n반얀트리 클럽 앤 스파 서울\n그랜드 하얏트 인천\n파크 하얏트 부산\n호텔 오노마 대전\n그랜드 머큐어 앰배서더 창원\n이용방법\n제1여객터미널\n제2여객터미널\n주차 시 : ① 지하 1층 단기주차장 A구역으로 이동 후 Maxerve 유니폼 착용 \n                   공식 주차대행 직원에게 발렛파킹 요청\n              ② 모바일 접수증 문자 발송 (카카오톡/ MMS 문자발송, \n                   문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시 : ① 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 \n                   (지하 3층 A32구역 또는 H38구역)\n              ② 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 \n                   차량 인수\n              ③ 차량 인수 후 주차요금 고객이 별도 정산\n주차 시 : ① 제2여객터미널 지하1층 서편 단기 주차장으로 진입\n              ② 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ③ 모바일 접수증 문자 발송 (알림톡/문자메세지 발송)\n출차 시 : ① 입국 후 접수증 안내에 따라 단기주차장 지하1층 \n                   동편 210번 앞 고객대기실로 이동\n              ② 출차장 정산소에서 프리미엄 마스터카드 제시 후 \n                  서비스 이용가능 여부 확인\n              ③ 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n국내선 \n이용방법\n주차 시 : ① 국내선 청사 2층 우측 하늘색 라인따라 진입 후, 주황색 유니폼 \n                   착용 공식 주차대행 직원에게 발렛파킹 요청\n              ② 차량 상태 점검 후 차량 인도 및 차량 보관증 수령\n출차 시 : ① 출발지 항공기 탑승 전 차량보관증에 기재된 연락처로 출차 요청\n              ② 차량 인수 시, 접수증과 프리미엄 마스터카드 제시 후 서비스\n                   이용 가능 여부 확인\n              ③ 차량 인수 후 출차 시 고객이 주차요금 별도 정산\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 발렛파킹 서비스는 본인 차량에 한해 제공되는 것을 원칙으로 합니다.\n   (타인 차량에는 서비스가 제공되지 않습니다.) \n- 호텔 영업장을 이용하지 않을 경우 일부 호텔에서는 발렛파킹 비용 및 주차료가 청구될 수 있습니다.\n- 1일 2~3시간 이내의 주차비용이 발렛파킹 서비스에 포함되어 있습니다. (일부 호텔 제외)\n- 오크우드 프리미어 코엑스센터는 만차 시 3시간 무료 주차권이 제공되며 이용 한도가 차감됩니다.\n- JW메리어트 호텔 서울(50,000원 이상), 레스케이프 호텔(30,000원 이상), 몬드리안 서울 이태원 및 \n   호텔 코리아나(25,000원 이상), 파크하얏트 서울(20,000원 이상)의 호텔 영업장(당일 영수증) 제시 시 \n   무료 발렛파킹 서비스 이용이 가능합니다. \n   영수증 미지참 시 제휴 서비스 이용은 제한되며, 발렛파킹 서비스 이용요금 및 별도의 주차료는 고객이 \n   호텔에 직접 지불 하셔야 합니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n서비스혜택\n•김포공항 무료 발렛파킹 서비스 제공 (국내선)\n이용조건\n•인천/김포공항 통합 월 7회 서비스 제공\n•CLUB Leaders 3 카드에 한하여 서비스 제공\n    (CLUB NOBLE은 서비스 미제공)\n•CLUB Leaders 3 카드는 지난달(1일~말일) 국내외 일시불/할부\n    50만원 이상 이용 시 서비스 제공 (최초 카드 사용등록 후 다음달 \n    말일까지는 지난달 카드 이용금액 50만원 미만 시에도 서비스 제공)\n김포공항 라운지 입장 서비스\nCLUB NOBLE\nCLUB Leaders 3\n아래 대상 카드 발급 시 Mastercard Platinum04 선택서비스와 \nMastercard Platinum 공통서비스가 제공됩니다.\n* Mastercar 프리미엄 서비스의 서비스의 상세한 내용은 Mastercard 홈페이지\n  (http://www.mastercard.com/kr)를 통해 확인하시기 바랍니다. \n* 본 Mastercard 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 Mastercard Platinum 서비스는 기간이 명시되지 않는 한 \n   2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n상품유형\nMastercard World\nPlatinum04\n대상카드\n	4752	acd6272a72d416dad47b24d81b54a17b0db4492a2dc0f361fdd3b2ea216ac0cb	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:20:57.765029+00	SYSTEM	2026-11-03 05:20:57.765029+00	SYSTEM
20261103_000015	1	Mastercard\nWorld\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nMastercard World 공통서비스\n· LANE4 AIR 서비스 3만원 할인 (왕복 예약 시 총 6만원 할인)\nHotel\nAirport\n· KALPAK 제휴 호텔 예약 시 룸 업그레이드, 2인 무료 조식, \n   Room Creadit, Early Check in & Late Check out 서비스\n· Trip.com 호텔 15%, 항공 3%, 액티비티 5% 할인\n· Agoda.com 10% 할인 (최대 USD 30)\n  (예약: 26.1.1~26.3.31 / 숙박: 26.1.1~26.12.31)\n· Hotels.com 8% 할인 (최대 USD 50)\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Expedia.com 8% 할인 (최대 10만원)\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Rakuten Travel 20% 할인 (최대 USD 100)\n  (예약: 26.1.1~26.12.30 / 숙박: 26.1.1~27.2.28)\n· Qatar Airways 항공권 최대 10% 할인\n· 헤외 럭셔리 크루즈 셀렉션 7% 할인 또는 크루즈 캐시 제공 또는 \n   인천국제공항 밴서비스 제공\n· On Vacation 럭셔리호텔/크루즈 상품 5% 할인\n· Kkday 티켓/교통/액티비티 5% 할인, 해외투어/eSim 10% 할인\n  (최대 USD 10) (예약: 26.1.1~26.12.31 / 여행: 26.1.1~27.3.31)\n· Oh Show 60분 자유의 여신상 크루즈 티켓 1+1,\n   뉴욕 브로드웨이 뮤지컬 티켓 3% 할인, \n   라스베가스 쇼 및 하와이 태양의서커스 티켓 3% 할인\nTravel\nTravel\n* 본 Mastercard World 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용 약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 서비스는 Mastercard 에서 제공하는 서비스로 , 프리미엄 서비스에 대한 구체적 내용, 적용기준 및 \n   유의사항 등은 http://www.mastercard.co.kr → ‘Premium Mastercard Services’에서 \n   사전에 반드시 확인하시기 바랍니다.\n* 본 Mastercard World 서비스는 기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 국내 특급호텔(약 42여개) F&B 5~15% 할인\n· 국내 특급호텔(약 44여개) 객실/패키지 5~50% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약16여개) 스파 10~20% 할인\n· Trump Hotels 10% 할인 \n· Outrigger Hotels and Resorts 5% 할인\n· KA LA’I Waikiki Beach, LXR Hotels & Resorts 10% 할인 및 조식 제공\n· 코타키나발루 수트라하버 리조트 클럽 및 스위트 객실 25% 할인, \n   골드 카드 10% 할인\n· HoteLux 엘리트 멤버십 12개월 무료 제공 및 1,000 포인트 제공\n· 신라면세점 블랙 등급 혜택 제공\n  (온/오프라인 최대 20% 할인, 인터넷점 S.Rewards 10,000P 제공)\n· 신세계면세점 블랙 멤버십 제공 (최대 20% 할인)\n· 트래블메이트 캐리어/여행용품 12% 추가 할인\n· 해외 프리미엄 아울렛 VIP 패스 제공 (10% 할인)\n· 몽쥬약국 구매 금액별 10~15% 할인 및 최대 15% 면세혜택\n· Mastercard E-Commerce Protection 해외 온라인 직구 보험 \n  연간 최대 115만원 보상 \nShopping\n· 15개국 48개 골프장 그린피 50% 할인 (연 4회), (~6.30)\n· 코타키나발루 수트라하버 리조트 골프&컨트리클럽 그린피 본인 면제\n· LANE4 Golf 골프장 이동 서비스 5만원 할인\n· Car up 프리미엄 카 케어 서비스 30% 할인\n· 내셔널지오그래픽 트래블러 정기구독 결제 20% 할인\nGolf\nLife\n서비스\n내용\n· 제주도닷컴 패키지 5%, 렌터카 12%, 국내선 항공권 발권대행수수료 무료\n· Europcar 최대 15% 할인\n· 롯데렌터카 최대 제주 90%, 내륙 65% 할인 제공\n·  Hertz 렌트 예약 시 10% 할인, 멤버십 무료 가입\n· 짐캐리 최대 20% 할인(단, 최초 이용 시 1회 무료, 짐1 개 편도기준)\n· 와이드모바일 와이파이도시락 15%, 도시락 eSIM/USIM 10% 할인\n· Airalo eSIM 최대 20% 할인 (최대 USD 100)\n· 유심사 해외 eSIM/ USIM 20% 할인\n· AIG 손해보험 해외 여행자 보험 제공\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03840호 (2026.03.23) / 준법심의 L-26-0344 (2026.02.04) / VI 260326-31\n* 아래의 Mastercard World 서비스는 Mastercard World 등급카드 소지자에게 공통으로 제공됩니다.\n	3329	fc8819a8af0837dcc6fd8a31c18ba73261c6cc63a1eb60877ee1cc4269479a22	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:21:03.19387+00	SYSTEM	2026-11-03 05:21:03.19387+00	SYSTEM
20261103_000015	2	Mastercard World 02 선택서비스\nMastercard World 02 선택서비스 중 특급호텔 발렛파킹, 인천/김포공항 발렛파킹을 하나카드에서 제공합니다.\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 발렛파킹 서비스는 본인 차량에 한해 제공되는 것을 원칙으로 합니다.\n   (타인 차량에는 서비스가 제공되지 않습니다.) \n- 호텔 영업장을 이용하지 않을 경우 일부 호텔에서는 발렛파킹 비용 및 주차료가 청구될 수 있습니다.\n- 1일 2~3시간 이내의 주차비용이 발렛파킹 서비스에 포함되어 있습니다. (일부 호텔 제외)\n- 오크우드 프리미어 코엑스센터는 만차 시 3시간 무료 주차권이 제공되며 이용한도가 차감됩니다.\n- JW 메리어트 서울(50,000원 이상), 레스케이프 호텔 및 JW 메리어트 동대문 스퀘어(30,000원 이상), \n   몬드리안 서울 이태원 및 호텔 코리아나(25,000원 이상), 파크하얏트 서울(20,000원 이상)의 \n   호텔 영업장(당일 영수증) 제시 시 무료 발렛파킹 서비스 이용이 가능합니다. \n   영수증 미지참 시 제휴서비스 이용은 제한되며, 발렛파킹 서비스 이용요금 및 별도의 주차료는 \n   고객이 호텔에 직접 지불 하셔야 합니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n특급호텔 발렛파킹 서비스\n서비스혜택\n국내 주요 특급호텔 무료 발렛파킹 서비스 제공 \n- 호텔 발렛파킹 부스에 서비스 요청 후 주차권 수령\n- 차량 인수 시 발렛파킹 부스에 주차권과 마스터카드 제시\n- 호텔 직원 서비스 대상카드 조회\n이용방법\n이용조건\n- 호텔 통합 월 7회 서비스 제공\n- CLUB Leaders 5,8,10,15 카드는 \n   지난달(1일~말일) 국내외 일시불/할부 50만원 이용 시 서비스 제공\n   (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 이용금액 \n   50만원 미만 시에도 서비스 제공)\n이용조건\n이용방법\n서비스혜택\n인천/김포공항 발렛파킹 서비스\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 여객터미널 3층 승용차전용도로에서 5분 이상 정차 시 과태료가 부가될 수 있습니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n- 인천공항 발렛파킹 서비스 운영시간은 24시간이며, 김포공항 발렛파킹 서비스 제공시간은 \n    5시부터 21시이나, 출차 서비스는 24시간 제공됩니다.\n- 본 서비스는 공식 주차대행 업체인 인천공항 제1여객터미널 : ㈜맥서브,\n   제2여객터미널 : 아마노코리아, 김포공항 국제선 : ㈜하이파킹 에 의해 제공되니 \n   서비스 이용 시 공식 주차대행업체인지 확인하시기 바랍니다.\n인천공항 제 1,2여객터미널 및 김포공항 국내선 \n무료 발렛파킹 서비스 제공\n- 호텔 통합 월 7회 서비스 제공\n- CLUB Leaders 5,8,10,15 카드는 \n   지난달(1일~말일) 국내외 일시불/할부 50만원 이용 시 서비스 제공\n   (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 이용금액 \n   50만원 미만 시에도 서비스 제공)\n대상 호텔\n지방\n지역\n서울\n앰배서더 서울 풀만\n그랜드 워커힐 서울 \n그랜드 하얏트 서울\n스위스 그랜드 호텔\n더 플라자 \n \n호텔 코리아나\n파크 하얏트 서울\n메이필드 호텔\n콘래드 서울\n호텔 리베라 청담\n \n레스케이프 호텔\n비스타 워커힐 서울\nJW 메리어트 동대문 스퀘어\nJW 메리어트 서울\n몬드리안 서울 이태원\n반얀트리 클럽앤스파 서울\n서울 가든 호텔\n서울 신라 호텔\n서울 드래곤 시티\n소피텔 앰배서더 서울\n \n \n노보텔 앰배서더 서울 강남\n노보텔 앰배서더 동대문\n글래드 강남 코엑스 센터\n더블리티 by 힐튼 판교\n코트야드 메리어트 서울 타임스퀘어\n르 메르디앙&목시 서울 명동\n오크우드 프리미어 코엑스\n메리어트 이그제큐티브\n아파트먼트 서울\n호텔 나루 서울 엠갤러리 \n호텔 오노마 대전\n인터불고 대구\n소노캄 여수\n소노캄 고양\n윈덤그랜드 부산\n그랜드 하얏트 인천\n파라다이스 부산 호텔\n그랜드조선부산\n세인트존스 호텔\n파크하얏트 부산\n힐튼 경주\n대구 메리어트 호텔\nJW 메리어트 제주 리조트&스파 \n파라다이스 시티 호텔\n그랜드머큐어엠배서더 창원\n인스파이어 엔터테이먼트 리조트\n인천공항\n제1여객터미널\n인천공항\n제2여객터미널\n주차 시 : ① 지하1층 단기주차장 A구역으로 이동 후 Maxerve 유니폼 착용\n                   공식 주차대행 직원에게 발렛파킹 요청\n              ② 모바일 접수증 문자 발송 (카카오톡/ MMS 문자발송, \n                   문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시 : ① 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 \n                   (지하 3층 A32구역 또는 H38구역)\n              ② 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 \n                   차량 인수\n              ③ 차량 인수 후 주차요금 고객이 별도 정산\n주차 시 : ① 제 2여객터미널 지하1층 서편 단기 주차장으로 진입\n              ② 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ③ 모바일 접수증 문자 발송 (알림톡/문자메세지 발송)\n출차 시 : ① 입국 후 접수증 안내에 따라 단기주차장 지하 1층 \n                   동편 210번 앞 고객대기실로 이동\n              ② 출차장 정산소에서 프리미엄 마스터카드 제시 후 \n                  서비스 이용가능 여부 확인\n              ③ 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n김포공항\n국내선\n주차 시 : ① 국내선 청사 2층 우측 하늘색 라인따라 진입 후, \n                    주황색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ② 차량 상태 점검 후 차량 인도 및 차량 보관증 수령\n출차 시 : ① 출발지 항공기 탑승 전 차량보관증에 기재된 연락처로 출차 요청\n              ② 차량 인수 시, 접수증과 프리미엄 마스터카드 제시 후 \n                   서비스 이용 가능 여부 확인\n              ③ 차량 인수 후 출차 시 고객이 주차요금 별도 정산\n* Mastercard 프리미엄 서비스의 상세한 내용은 Mastercard 홈페이지 \n   (http://www.mastercard.com/kr)를 통해 확인하시기 바랍니다.\n* 본 Mastercard 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품안내장,  \n   이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 Mastercard 프리미엄 서비스는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n상품유형\nMastercard World 02\n대상카드\nCLUB Leaders 5\nCLUB Leaders 8\nCLUB Leaders 10\nCLUB Leaders 15\n아래 대상 카드 발급 시 Mastercard World 02 선택서비스와 \nMastercard World 공통서비스가 제공됩니다.\nMastercard\nWorld 02\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n  \n선택서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03777호 (2026.03.20) / 준법심의 L-26-0363 (2026.02.09) / VI 260326-33\n	4568	2798ef62e0be551114b54a5a2e227954cef4abe1d8a9f5c5748bdd7750b6b8fb	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:21:03.19387+00	SYSTEM	2026-11-03 05:21:03.19387+00	SYSTEM
20261103_000016	1	Mastercard\nWorld\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nMastercard World 공통서비스\n· LANE4 AIR 서비스 3만원 할인 (왕복 예약 시 총 6만원 할인)\nHotel\nAirport\n· KALPAK 제휴 호텔 예약 시 룸 업그레이드, 2인 무료 조식, \n   Room Creadit, Early Check in & Late Check out 서비스\n· Trip.com 호텔 15%, 항공 3%, 액티비티 5% 할인\n· Agoda.com 10% 할인 (최대 USD 30)\n  (예약: 26.1.1~26.3.31 / 숙박: 26.1.1~26.12.31)\n· Hotels.com 8% 할인 (최대 USD 50)\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Expedia.com 8% 할인 (최대 10만원)\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Rakuten Travel 20% 할인 (최대 USD 100)\n  (예약: 26.1.1~26.12.30 / 숙박: 26.1.1~27.2.28)\n· Qatar Airways 항공권 최대 10% 할인\n· 헤외 럭셔리 크루즈 셀렉션 7% 할인 또는 크루즈 캐시 제공 또는 \n   인천국제공항 밴서비스 제공\n· On Vacation 럭셔리호텔/크루즈 상품 5% 할인\n· Kkday 티켓/교통/액티비티 5% 할인, 해외투어/eSim 10% 할인\n  (최대 USD 10) (예약: 26.1.1~26.12.31 / 여행: 26.1.1~27.3.31)\n· Oh Show 60분 자유의 여신상 크루즈 티켓 1+1,\n   뉴욕 브로드웨이 뮤지컬 티켓 3% 할인, \n   라스베가스 쇼 및 하와이 태양의서커스 티켓 3% 할인\nTravel\nTravel\n* 본 Mastercard World 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용 약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 서비스는 Mastercard 에서 제공하는 서비스로 , 프리미엄 서비스에 대한 구체적 내용, 적용기준 및 \n   유의사항 등은 http://www.mastercard.co.kr → ‘Premium Mastercard Services’에서 \n   사전에 반드시 확인하시기 바랍니다.\n* 본 Mastercard World 서비스는 기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 국내 특급호텔(약 42여개) F&B 5~15% 할인\n· 국내 특급호텔(약 44여개) 객실/패키지 5~50% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약16여개) 스파 10~20% 할인\n· Trump Hotels 10% 할인 \n· Outrigger Hotels and Resorts 5% 할인\n· KA LA’I Waikiki Beach, LXR Hotels & Resorts 10% 할인 및 조식 제공\n· 코타키나발루 수트라하버 리조트 클럽 및 스위트 객실 25% 할인, \n   골드 카드 10% 할인\n· HoteLux 엘리트 멤버십 12개월 무료 제공 및 1,000 포인트 제공\n· 신라면세점 블랙 등급 혜택 제공\n  (온/오프라인 최대 20% 할인, 인터넷점 S.Rewards 10,000P 제공)\n· 신세계면세점 블랙 멤버십 제공 (최대 20% 할인)\n· 트래블메이트 캐리어/여행용품 12% 추가 할인\n· 해외 프리미엄 아울렛 VIP 패스 제공 (10% 할인)\n· 몽쥬약국 구매 금액별 10~15% 할인 및 최대 15% 면세혜택\n· Mastercard E-Commerce Protection 해외 온라인 직구 보험 \n  연간 최대 115만원 보상 \nShopping\n· 15개국 48개 골프장 그린피 50% 할인 (연 4회), (~6.30)\n· 코타키나발루 수트라하버 리조트 골프&컨트리클럽 그린피 본인 면제\n· LANE4 Golf 골프장 이동 서비스 5만원 할인\n· Car up 프리미엄 카 케어 서비스 30% 할인\n· 내셔널지오그래픽 트래블러 정기구독 결제 20% 할인\nGolf\nLife\n서비스\n내용\n· 제주도닷컴 패키지 5%, 렌터카 12%, 국내선 항공권 발권대행수수료 무료\n· Europcar 최대 15% 할인\n· 롯데렌터카 최대 제주 90%, 내륙 65% 할인 제공\n·  Hertz 렌트 예약 시 10% 할인, 멤버십 무료 가입\n· 짐캐리 최대 20% 할인(단, 최초 이용 시 1회 무료, 짐1 개 편도기준)\n· 와이드모바일 와이파이도시락 15%, 도시락 eSIM/USIM 10% 할인\n· Airalo eSIM 최대 20% 할인 (최대 USD 100)\n· 유심사 해외 eSIM/ USIM 20% 할인\n· AIG 손해보험 해외 여행자 보험 제공\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03840호 (2026.03.23) / 준법심의 L-26-0344 (2026.02.04) / VI 260326-31\n* 아래의 Mastercard World 서비스는 Mastercard World 등급카드 소지자에게 공통으로 제공됩니다.\n	3329	fc8819a8af0837dcc6fd8a31c18ba73261c6cc63a1eb60877ee1cc4269479a22	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:21:09.536855+00	SYSTEM	2026-11-03 05:21:09.536855+00	SYSTEM
20261103_000016	2	Mastercard World 03 선택서비스\nMastercard World 03 선택서비스 중 특급호텔 발렛파킹, 인천/김포공항 발렛파킹을 하나카드에서 제공합니다.\n실적 제외 대상\n국세, 지방세, 수도/전기요금, 그외 공과금(우편요금, 여권발급비용, 과태료, 범칙금, 벌금, 국가/공공기관/\n공공단체가 부과하는 부담금), 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/건강보험료 \n납부금액, 스쿨뱅킹, 초 ·중 ·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트카드 구매, \n선불카드 및 선불전자지급수단(하나머니 등) 충전금액, 부동산임대료\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 발렛파킹 서비스는 본인 차량에 한해 제공되는 것을 원칙으로 합니다.\n   (타인 차량에는 서비스가 제공되지 않습니다.) \n- 호텔 영업장을 이용하지 않을 경우 일부 호텔에서는 발렛파킹 비용 및 주차료가 청구될 수 있습니다.\n- 1일 2~3시간 이내의 주차비용이 발렛파킹 서비스에 포함되어 있습니다. (일부 호텔 제외)\n- 오크우드 프리미어 코엑스센터는 만차 시 3시간 무료 주차권이 제공되며 이용한도가 차감됩니다.\n- JW 메리어트 서울(50,000원 이상), 레스케이프 호텔 및 JW 메리어트 동대문 스퀘어(30,000원 이상), \n   몬드리안 서울 이태원 및 호텔 코리아나(25,000원 이상), 파크하얏트 서울(20,000원 이상)의 \n   호텔 영업장(당일 영수증) 제시 시 무료 발렛파킹 서비스 이용이 가능합니다. \n   영수증 미지참 시 제휴서비스 이용은 제한되며, 발렛파킹 서비스 이용요금 및 별도의 주차료는 \n   고객이 호텔에 직접 지불 하셔야 합니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n특급호텔 발렛파킹 서비스\n서비스혜택\n국내 주요 특급호텔 무료 발렛파킹 서비스 제공 \n- 호텔 발렛파킹 부스에 서비스 요청 후 주차권 수령\n- 차량 인수 시 발렛파킹 부스에 주차권과 마스터카드 제시\n- 호텔 직원 서비스 대상카드 조회\n이용방법\n이용조건\n- 호텔 통합 월 2회 서비스 제공\n- 대상 카드로 지난달(1일~말일) 국내외 일시불/할부 50만원 이용 시 \n   서비스 제공 (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 \n   이용금액 50만원 미만 시에도 서비스 제공)\n이용조건\n이용방법\n서비스혜택\n인천/김포공항 발렛파킹 서비스\n실적 제외 대상\n국세, 지방세, 수도/전기요금, 그외 공과금(우편요금, 여권발급비용, 과태료, 범칙금, 벌금, 국가/공공기관/\n공공단체가 부과하는 부담금), 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/건강보험료 \n납부금액, 스쿨뱅킹, 초 ·중 ·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트카드 구매, \n선불카드 및 선불전자지급수단(하나머니 등) 충전금액, 부동산임대료\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 여객터미널 3층 승용차전용도로에서 5분 이상 정차 시 과태료가 부가될 수 있습니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다.\n- 인천공항 발렛파킹 서비스 운영시간은 24시간이며, 김포공항 발렛파킹 서비스 제공시간은 \n    5시부터 21시이나, 출차 서비스는 24시간 제공됩니다.\n- 본 서비스는 공식 주차대행 업체인 인천공항 제1여객터미널 : ㈜맥서브,\n   제2여객터미널 : 아마노코리아, 김포공항 국제선 : ㈜하이파킹 에 의해 제공되니 \n   서비스 이용 시 공식 주차대행업체인지 확인하시기 바랍니다.\n인천공항 제 1,2여객터미널 및 김포공항 국내선 \n무료 발렛파킹 서비스 제공\n- 호텔 통합 월 2회 서비스 제공\n- 대상 카드로 지난달(1일~말일) 국내외 일시불/할부 50만원 이용 시 \n   서비스 제공 (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 \n   이용금액 50만원 미만 시에도 서비스 제공)\n대상 호텔\n지방\n지역\n서울\n앰배서더 서울 풀만\n그랜드 워커힐 서울 \n그랜드 하얏트 서울\n스위스 그랜드 호텔\n더 플라자 \n \n호텔 코리아나\n파크 하얏트 서울\n메이필드 호텔\n콘래드 서울\n호텔 리베라 청담\n \n레스케이프 호텔\n비스타 워커힐 서울\nJW 메리어트 동대문 스퀘어\nJW 메리어트 서울\n몬드리안 서울 이태원\n반얀트리 클럽앤스파 서울\n서울 가든 호텔\n서울 신라 호텔\n서울 드래곤 시티\n소피텔 앰배서더 서울\n \n \n노보텔 앰배서더 서울 강남\n노보텔 앰배서더 동대문\n글래드 강남 코엑스 센터\n더블리티 by 힐튼 판교\n코트야드 메리어트 서울 타임스퀘어\n르 메르디앙&목시 서울 명동\n오크우드 프리미어 코엑스\n메리어트 이그제큐티브\n아파트먼트 서울\n호텔 나루 서울 엠갤러리 \n호텔 오노마 대전\n인터불고 대구\n소노캄 여수\n소노캄 고양\n윈덤그랜드 부산\n그랜드 하얏트 인천\n파라다이스 부산 호텔\n그랜드조선부산\n세인트존스 호텔\n파크하얏트 부산\n힐튼 경주\n대구 메리어트 호텔\nJW 메리어트 제주 리조트&스파 \n파라다이스 시티 호텔\n그랜드머큐어엠배서더 창원\n인스파이어 엔터테이먼트 리조트\n인천공항\n제1여객터미널\n인천공항\n제2여객터미널\n주차 시 : ① 지하1층 단기주차장 A구역으로 이동 후 Maxerve 유니폼 착용\n                   공식 주차대행 직원에게 발렛파킹 요청\n              ② 모바일 접수증 문자 발송 (카카오톡/ MMS 문자발송, \n                   문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시 : ① 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 \n                   (지하 3층 A32구역 또는 H38구역)\n              ② 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 \n                   차량 인수\n              ③ 차량 인수 후 주차요금 고객이 별도 정산\n주차 시 : ① 제 2여객터미널 지하1층 서편 단기 주차장으로 진입\n              ② 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ③ 모바일 접수증 문자 발송 (알림톡/문자메세지 발송)\n출차 시 : ① 입국 후 접수증 안내에 따라 단기주차장 지하 1층 \n                   동편 210번 앞 고객대기실로 이동\n              ② 출차장 정산소에서 프리미엄 마스터카드 제시 후 \n                  서비스 이용가능 여부 확인\n              ③ 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n김포공항\n국내선\n주차 시 : ① 국내선 청사 2층 우측 하늘색 라인따라 진입 후, \n                    주황색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n              ② 차량 상태 점검 후 차량 인도 및 차량 보관증 수령\n출차 시 : ① 출발지 항공기 탑승 전 차량보관증에 기재된 연락처로 출차 요청\n              ② 차량 인수 시, 접수증과 프리미엄 마스터카드 제시 후 \n                   서비스 이용 가능 여부 확인\n              ③ 차량 인수 후 출차 시 고객이 주차요금 별도 정산\n* Mastercard 프리미엄 서비스의 상세한 내용은 Mastercard 홈페이지 \n   (http://www.mastercard.com/kr)를 통해 확인하시기 바랍니다.\n* 본 Mastercard 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품안내장,  \n   이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 Mastercard 프리미엄 서비스는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n상품유형\nMastercard World 03\n대상카드\nJADE Classic\n아래 대상 카드 발급 시 Mastercard World 03 선택서비스와 \nMastercard World 공통서비스가 제공됩니다.\nMastercard\nWorld 03\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n  \n선택서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-03778호 (2026.03.20) / 준법심의 L-26-0364 (2026.02.09) / VI 260326-34\n	4923	89f16934be52683ab30a3c05a2366bf1329abe426136626eb70e05e41da0c1dc	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:21:09.536855+00	SYSTEM	2026-11-03 05:21:09.536855+00	SYSTEM
20261103_000017	1	UnionPay Diamond\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nUnionPay Diamond 공통서비스\n· 트립닷컴 국내외 항공권 10% 할인, 국내외 호텔 20% 할인 \n· DB손해보험 해외여행자 보험 기본상품 가입 시, 최대 5일 무료 \n· 클룩 해외 액티비티 예약 시 유니온페이 프리미엄 카드로 $100 이상 \n   결제 시 최대 $30 할인\n· 마이리얼트립 국내 투어/티켓/숙소 등 결제 시 최대 10% 즉시 할인\n· 글로벌 원심(OneSIM) 무료 이용 서비스 제공 (4.1~)\nHotel\nAirport\n· 국내 특급호텔(약 45여개) 100여개 식음료 매장 5~15% 할인\n· 국내 특급호텔(약 43여개) 객실 5~40% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약 15여개) 스파 5~15% 할인 및 샘플 증정\n· 국내 특급호텔 (약 7여개) 로비라운지에서 음료 구매 시 \n   동반인 음료 무료 제공 (월 1회, 연 4회)\n· 싱가포르 마리나 베이 샌즈의 샌즈 리워드 라이프스타일 \n   엘리트 등급 멤버십 혜택 3개월간 제공\nTravel\n* UnionPay Diamond 서비스의 상세한 내용은 UnionPay 홈페이지(http://www.unionpaypremium.co.kr)를 통해 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 전세계 럭셔리 공항 라운지(The Lounge App에서 확인 가능) 할인\n  (1+1) 제공\n· 유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 K공항리무진 할인\n  (1+1)\n· 인천공항 제휴 매장에서 아메리카노 결제 시 10% 할인\n· 현대면세점 BLACK 등급 멤버십 제공 및 추가 3~8% 선불카드 할인 제공\n  (무역센터점, 인천공항점, 온라인몰/4월 중 오픈 예정)\n· 경복궁면세점 인천공항점 $1 이상 구매 시 사은품 제공\n· 인천공항 연계 교통 무료 이용 서비스 제공\n· 국내 골프장 온라인 예약 서비스 및 그린피 할인\n   (유니온페이 골프사이트에서 본인 인증 후 프리미엄 카드 결제 시 서비스 제공)\n· 국내 지정 골프장 클럽하우스 또는 스타트하우스에서 이용권 제시 시\n   커피(4잔) 50% 할인\n   (유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 이용권 할인 서비스 제공)\n· 국내  지정 골프 연습장 타석권 결제 시 정상가 금액에서 50% 할인\n   (유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 이용권 할인 서비스 제공)\nGlobal\n· 해외 컨시어지 서비스 제공 (7.21~)\n· 해외 긴급 의료지원 서비스 제공 (7.21~)\n· 국내외 제휴 서비스 및 컨시어지 플랫폼 서비스 제공 (7.21~)\n- 유의사항\n  · 서비스 과정에서 실제로 발생하는 비용은 별도 청구 (UPI 홈페이지 참조)\n  · 해외 지원 서비스는 전부 유니온페이 프리미엄 콜센터로 전화상담 후 \n     서비스 제공 (콜센터 : 1670-8893, 24시간 연중무휴)\n· 국내 다이닝 레스토랑 10% 할인 혜택\n   (제휴 매장에서 유니온페이 다이아몬드 카드 제시 및 결제 시 할인 서비스 제공)\n   * 관련 문의 1670-8890\n- 유의사항\n  · 국내 특급호텔 객실 할인 및 스파 서비스는 유니온페이 프리미엄 콜센터를 통해\n     전화 상담 후 서비스 제공 (콜센터 1670-8810, 24시간 연중 무휴)\nGolf\nLife\nStyle\n서비스\n내용\n· 현대아울렛 전점에서 무료 음료 1잔(월 1회) 및 외국인 특화점에서 \n   추가 혜택(연 1회) 제공\n· 예술의전당 고객센터(1668-1352)를 통한 다이아몬드 카드 회원 \n   인증 후 예술의전당 블루회원 멤버십 서비스 제공\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-05041호 (2026.04.10) / 준법심의 L-26-0516(2026.03.24)/ VI 260421-31\n* 아래의 UnionPay Diamond 서비스는 UnionPay Diamond 등급 카드 소지자에게 공통으로 제공됩니다. \n	2926	4fae197f718dfb03c971706ee72c80f1ce4b9204460e9e9b4712332bf0f86c87	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:21:14.154311+00	SYSTEM	2026-11-03 05:21:14.154311+00	SYSTEM
20261103_000017	2	UnionPay Diamond\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n  \n선택서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-04831호(2026.04.07) / 준법심의 L-26-0515(2026.03.24)/ VI 260325-31\n* UnionPay Diamond 선택서비스 중 특급 호텔 발렛파킹, 인천공항 발렛파킹, 국내공항 라운지 서비스를 하나카드에서 제공합니다. \n인천공항 발렛파킹 서비스\n서비스 혜택 - 인천공항 무료 발렛파킹 서비스 제공\n이용조건 \n- 통합 월 2회 서비스 제공\n- 지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 이용금액 \n  50만원 미만 시에도 서비스 제공)\n인천공항 제1여객터미널 이용방법\n주차 시\n1. 지하 1층 단기 주차장 A구역으로 이동\n2. Maxerve 유니폼 착용 공식 주차대행  직원에게 발렛파킹 요청\n3. 모바일 접수증 문자 발송 \n   (카카오톡/ MMS 문자발송, 문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시\n1. 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 (지하 3층 A32 구역 또는 H38 구역)\n2. 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 차량 인수\n3. 차량 인수 후 주차요금 고객이 별도 정산\n인천공항 제2여객터미널 이용방법\n주차 시\n1. 제 2여객터미널 발렛파킹 전용도로 및 발렛 안내 표지판을 따라\n    지하 1층 서편 단기 주차장으로 진입\n2. 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n3. 모바일 접수증 문자 발송 (알림톡 / 문자메시지 발송)\n출차 시\n1. 입국 후 접수증 안내에 따라 단기 주차장 지하 1층 동편 210 번 앞 고객 대기실로 이동\n2. 출차장 정산소에서 카드 제시 후 서비스 이용가능 여부 확인\n3. 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n특급호텔 발렛파킹 서비스\n유의사항\n- 상기 서비스는 국내에서 발급된 유니온페이 다이아몬드 카드 회원에 한하여 제공하며, \n   회원 본인에 한해 제공됩니다.\n- 서비스 제공 횟수를 초과했을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 서비스는 발렛파킹 비용에 한하여 적용되며, 주차비용은 별도로 부과됩니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다. \n서비스 혜택 - 국내 주요 특급호텔 무료 발렛파킹 서비스 제공\n이용조건 \n- 호텔 통합 월 2회 서비스 제공\n- 지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n  50만원 미만 시에도 서비스 제공)\n이용방법 \n- 주차시 호텔 현관에서 도어맨에게 발렛파킹 요청 후 차량보관증 수령  \n- 차량 인수 시 도어맨에게 차량보관증과 유니온페이 다이아몬드 카드 제시\n- 호텔 단말기를 통해 서비스 이용가능 여부 확인 후 서비스 제공\n국내공항 라운지 서비스\n대상 호텔\n대구 메리어트 호텔\n웨스틴 조선 부산\n호텔 오노마 대전 오토그래프 컬렉션\n서울\n지방\n※ 오크우드 프리미어 코엑스 센터 (서비스 제외기간 참고)\n그랜드 머큐어 앰배서더 서울 용산\n그랜드 워커힐 서울\n노보텔 스위트 앰배서더 서울 용산\n노보텔 앰배서더 서울 용산\n더 플라자\n노보텔 앰배서더 서울 강남\n앰배서더 서울 풀만 호텔\n메리어트 이그제큐티브 아파트먼트\n파크 하얏트 서울\n반얀트리 클럽 앤 스파 서울\n비스타 워커힐 서울\n서울 신라 호텔\n레스케이프 호텔\n호텔 코리아나\n그랜드 하얏트 서울\n오크우드 프리미어 코엑스센터\n이비스 스타일 앰배서더 서울 용산\n코트야드 메리어트 서울 타임스퀘어\n콘래드 서울\nJW 메리어트 동대문 스퀘어\nJW 메리어트 호텔 서울\n노보텔 앰배서더 서울 동대문 호텔 \n& 레지던스\n몬드리안 서울 이태원\n스위스 그랜드 호텔\n서비스 제외기간\n- 오크우드 프리미어 코엑스 센터의 경우 코엑스 내 전시 또는 행사 시 서비스가 제한될 수 있습니다.\n유의사항\n- 상기 서비스는 해당 호텔의 객실 및 식음료 업장(연회장 제외)이용을 위해 내방한 회원 본인에 한해 제공됩니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다. \n- 상기 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 상기 서비스 이용 시 발렛파킹 비용 및 1일 3시간 이내의 주차비가 무료로 제공되나, 이용 시간 초과 시 \n   주차 금액이 별도로 부과될 수 있으며, 이는 회원이 부담하셔야 합니다.\n유의사항\n- 본 서비스는 동반자 및 유소아 요금은 각 라운지 마다 별도 금액이 적용되며, 유니온페이 다이아몬드 카드로 \n   결제  시 할인 금액이 적용됩니다.\n서비스 혜택 - 유니온페이 제휴 라운지 무료 이용 서비스 제공\n이용조건 \n- 본인에 한해 무료 이용 가능하며, 통합 월 2회(연 6회) 서비스 제공\n- 가족카드 사용 불가\n이용방법\n- 라운지 안내 데스크에서 보딩패스와 유니온페이 다이아몬드 카드 제시 및 \n 서비스 대상카드 여부 확인 후 무료 입장\n대상 공항\n상세내용\n인천공항\n김포공항\n김해공항\n스카이허브 라운지 제 1여객터미널 동편\n스카이허브 라운지 제 1여객터미널 서편\n스카이허브 라운지 제 1여객터미널 탑승동\n워커힐 마티나 라운지 제 1여객터미널 동편\n워커힐 마티나 라운지 제 1여객터미널 서편\n스카이허브 라운지 제 2여객터미널 동편\n스카이허브 라운지 제 2여객터미널 서편\n워커힐 마티나 라운지 제 2여객터미널 중앙 \n스카이허브 라운지 김포공항 국제선 청사\n스카이허브 라운지 김해공항 국제선 청사\nCLUB Signature 카드\n*UnionPay Diamond 서비스의 상세한 내용은 UnionPay 홈페이지 (http://www.unionpaypremium.co.kr) \n  또는 하나카드 홈페이지에서 반드시 확인하시기 바랍니다.\n*본 UnionPay Diamond 서비스는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, \n  카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n*본 UnionPay Diamond 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다. \n아래 대상 카드 발급 시 Unionpay Diamond 선택서비스가 제공됩니다.  \n	3944	30a5cefbf236f4c6941f206e284362d24124b70ba29c53b757ae66004d9353f4	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:21:14.154311+00	SYSTEM	2026-11-03 05:21:14.154311+00	SYSTEM
20261103_000018	1	UnionPay Diamond\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nUnionPay Diamond 공통서비스\n· 트립닷컴 국내외 항공권 10% 할인, 국내외 호텔 20% 할인 \n· DB손해보험 해외여행자 보험 기본상품 가입 시, 최대 5일 무료 \n· 클룩 해외 액티비티 예약 시 유니온페이 프리미엄 카드로 $100 이상 \n   결제 시 최대 $30 할인\n· 마이리얼트립 국내 투어/티켓/숙소 등 결제 시 최대 10% 즉시 할인\n· 글로벌 원심(OneSIM) 무료 이용 서비스 제공 (4.1~)\nHotel\nAirport\n· 국내 특급호텔(약 45여개) 100여개 식음료 매장 5~15% 할인\n· 국내 특급호텔(약 43여개) 객실 5~40% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약 15여개) 스파 5~15% 할인 및 샘플 증정\n· 국내 특급호텔 (약 7여개) 로비라운지에서 음료 구매 시 \n   동반인 음료 무료 제공 (월 1회, 연 4회)\n· 싱가포르 마리나 베이 샌즈의 샌즈 리워드 라이프스타일 \n   엘리트 등급 멤버십 혜택 3개월간 제공\nTravel\n* UnionPay Diamond 서비스의 상세한 내용은 UnionPay 홈페이지(http://www.unionpaypremium.co.kr)를 통해 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 전세계 럭셔리 공항 라운지(The Lounge App에서 확인 가능) 할인\n  (1+1) 제공\n· 유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 K공항리무진 할인\n  (1+1)\n· 인천공항 제휴 매장에서 아메리카노 결제 시 10% 할인\n· 현대면세점 BLACK 등급 멤버십 제공 및 추가 3~8% 선불카드 할인 제공\n  (무역센터점, 인천공항점, 온라인몰/4월 중 오픈 예정)\n· 경복궁면세점 인천공항점 $1 이상 구매 시 사은품 제공\n· 인천공항 연계 교통 무료 이용 서비스 제공\n· 국내 골프장 온라인 예약 서비스 및 그린피 할인\n   (유니온페이 골프사이트에서 본인 인증 후 프리미엄 카드 결제 시 서비스 제공)\n· 국내 지정 골프장 클럽하우스 또는 스타트하우스에서 이용권 제시 시\n   커피(4잔) 50% 할인\n   (유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 이용권 할인 서비스 제공)\n· 국내  지정 골프 연습장 타석권 결제 시 정상가 금액에서 50% 할인\n   (유니온페이 다이아몬드 혜택 구매 사이트에서 결제 시 이용권 할인 서비스 제공)\nGlobal\n· 해외 컨시어지 서비스 제공 (7.21~)\n· 해외 긴급 의료지원 서비스 제공 (7.21~)\n· 국내외 제휴 서비스 및 컨시어지 플랫폼 서비스 제공 (7.21~)\n- 유의사항\n  · 서비스 과정에서 실제로 발생하는 비용은 별도 청구 (UPI 홈페이지 참조)\n  · 해외 지원 서비스는 전부 유니온페이 프리미엄 콜센터로 전화상담 후 \n     서비스 제공 (콜센터 : 1670-8893, 24시간 연중무휴)\n· 국내 다이닝 레스토랑 10% 할인 혜택\n   (제휴 매장에서 유니온페이 다이아몬드 카드 제시 및 결제 시 할인 서비스 제공)\n   * 관련 문의 1670-8890\n- 유의사항\n  · 국내 특급호텔 객실 할인 및 스파 서비스는 유니온페이 프리미엄 콜센터를 통해\n     전화 상담 후 서비스 제공 (콜센터 1670-8810, 24시간 연중 무휴)\nGolf\nLife\nStyle\n서비스\n내용\n· 현대아울렛 전점에서 무료 음료 1잔(월 1회) 및 외국인 특화점에서 \n   추가 혜택(연 1회) 제공\n· 예술의전당 고객센터(1668-1352)를 통한 다이아몬드 카드 회원 \n   인증 후 예술의전당 블루회원 멤버십 서비스 제공\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-05041호 (2026.04.10) / 준법심의 L-26-0516(2026.03.24)/ VI 260421-31\n* 아래의 UnionPay Diamond 서비스는 UnionPay Diamond 등급 카드 소지자에게 공통으로 제공됩니다. \n	2926	4fae197f718dfb03c971706ee72c80f1ce4b9204460e9e9b4712332bf0f86c87	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:21:19.166396+00	SYSTEM	2026-11-03 05:21:19.166396+00	SYSTEM
20261103_000018	2	UnionPay Diamond 02\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n•상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 \n    하락할 수 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다. \n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며,\n    법정 최고금리(20%)를 초과하지 않습니다.\n   ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n    - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n    - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n    - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n* 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n* 계약 체결 전 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n* 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한 될 수 있습니다.\n* 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n* 소비자는 금융소비자보호법에 따라 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n* 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다. \n* 자세한 내용은 하나카드 홈페이지(www.hanacard.co.kr)를 참고하시거나\n  고객센터로 문의 바랍니다.\n  \n선택서비스 \n \n여신금융협회 심의필 제 2026-C1a-04831호(2026.04.07) / 준법심의 L-26-0515(2026.03.24)/ VI 260325-31\n* UnionPay Diamond 선택서비스 중 특급 호텔 발렛파킹, 인천공항/김포공항 발렛파킹 서비스를 하나카드에서 제공합니다.\n인천공항/김포공항 발렛파킹 서비스\n서비스 혜택 - 인천공항/김포공항 무료 발렛파킹 서비스 제공\n이용조건 \n- 통합 월 2회 서비스 제공\n- 지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용 등록 후 다음달 말일까지는 지난달 카드 이용금액 \n  50만원 미만 시에도 서비스 제공)\n인천공항 제1여객터미널 이용방법\n주차 시\n1. 지하 1층 단기 주차장 A구역으로 이동\n2. Maxerve 유니폼 착용 공식 주차대행  직원에게 발렛파킹 요청\n3. 모바일 접수증 문자 발송 \n   (카카오톡/ MMS 문자발송, 문자 발송이 불가한 경우 지류 영수증 발급)\n출차 시\n1. 입국 후 주차대행 접수증에 안내된 출차 장소로 이동 (지하 3층 A32 구역 또는 H38 구역)\n2. 유인정산소 모바일 접수증 제시 및 ‘제휴카드 승인’ 처리 후 차량 인수\n3. 차량 인수 후 주차요금 고객이 별도 정산\n인천공항 제2여객터미널 이용방법\n주차 시\n1. 제 2여객터미널 발렛파킹 전용도로 및 발렛 안내 표지판을 따라\n    지하 1층 서편 단기 주차장으로 진입\n2. 파란색 유니폼 착용 공식 주차대행 직원에게 발렛파킹 요청\n3. 모바일 접수증 문자 발송 (알림톡 / 문자메시지 발송)\n출차 시\n1. 입국 후 접수증 안내에 따라 단기 주차장 지하 1층 동편 210 번 앞 고객 대기실로 이동\n2. 출차장 정산소에서 카드 제시 후 서비스 이용가능 여부 확인\n3. 출차장에서 차량 인수 후 주차요금 정산 (고객이 별도 정산)\n특급호텔 발렛파킹 서비스\n김포공항 국내선 이용방법 (이용가능시간 05:00~21:00 / 출차는 24시간 가능)\n주차 시\n1. 국내선 청사 출발층(2층) 제일 우측 라인(하늘색)따라 진입 \n2. 오렌지색 유니폼 착용 공식 대행 직원에게 발렛파킹 요청 \n3.  차량 상태 점검 후 차량 인도 및 차량보관증 수령 \n출차 시\n1. 출발지 항공기 탑승 전 차량보관증에 있는 연락처로 차량 출차 요청\n2. 조기출발로 비행 일정이 변경된 경우, 반드시 사전에 차량보관증에 있는 연락처로  \n    변경사항 전달 및 차량 출차 요청 \n3.  차량 인수시, 접수증과 아멕스 프리미엄 카드 제시하여 단말기를 통해 \n     서비스 이용 가능여부 확인 후 서비스 무료 제공 \n4. 차량인수 후 출차 시, 주차 요금 별도 정산\n유의사항\n- 상기 서비스는 국내에서 발급된 유니온페이 다이아몬드 카드 회원에 한하여 제공하며, \n   회원 본인에 한해 제공됩니다.\n- 서비스 제공 횟수를 초과했을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 서비스는 발렛파킹 비용에 한하여 적용되며, 주차비용은 별도로 부과됩니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능 여부를 확인하시기 바랍니다. \n서비스 혜택 - 국내 주요 특급호텔 무료 발렛파킹 서비스 제공\n이용조건 \n- 호텔 통합 월 2회 서비스 제공\n- 지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n (최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액\n  50만원 미만 시에도 서비스 제공)\n이용방법 \n- 주차시 호텔 현관에서 도어맨에게 발렛파킹 요청 후 차량보관증 수령  \n- 차량 인수 시 도어맨에게 차량보관증과 유니온페이 다이아몬드 카드 제시\n- 호텔 단말기를 통해 서비스 이용가능 여부 확인 후 서비스 제공\n대상 호텔\n대구 메리어트 호텔\n웨스틴 조선 부산\n호텔 오노마 대전 오토그래프 컬렉션\n서울\n지방\n※ 오크우드 프리미어 코엑스 센터 (서비스 제외기간 참고)\n그랜드 머큐어 앰배서더 서울 용산\n그랜드 워커힐 서울\n노보텔 스위트 앰배서더 서울 용산\n노보텔 앰배서더 서울 용산\n더 플라자\n노보텔 앰배서더 서울 강남\n앰배서더 서울 풀만 호텔\n메리어트 이그제큐티브 아파트먼트\n파크 하얏트 서울\n반얀트리 클럽 앤 스파 서울\n비스타 워커힐 서울\n서울 신라 호텔\n레스케이프 호텔\n호텔 코리아나\n그랜드 하얏트 서울\n오크우드 프리미어 코엑스센터\n이비스 스타일 앰배서더 서울 용산\n코트야드 메리어트 서울 타임스퀘어\n콘래드 서울\nJW 메리어트 동대문 스퀘어\nJW 메리어트 호텔 서울\n노보텔 앰배서더 서울 동대문 호텔 \n& 레지던스\n몬드리안 서울 이태원\n스위스 그랜드 호텔\n서비스 제외기간\n- 오크우드 프리미어 코엑스 센터의 경우 코엑스 내 전시 또는 행사 시 서비스가 제한될 수 있습니다.\n유의사항\n- 상기 서비스는 해당 호텔의 객실 및 식음료 업장(연회장 제외) 이용을 위해 내방한 회원 본인에 한해 제공됩니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능여부를 확인하시기 바랍니다.\n- 해당 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 해당 서비스 이용 시 발렛파킹 비 용 및 1일 3시간 이내의 주차가 무료로 제공되나, 이용시간 초과 시 주차금액이 \n   별도로 부과될 수 있습니다.\n JADE Classic 카드 \n*UnionPay Diamond 02 서비스의 상세한 내용은 UnionPay 홈페이지 (http://www.unionpaypremium.co.kr) \n  또는 하나카드 홈페이지에서 반드시 확인하시기 바랍니다.\n*본 UnionPay Diamond 서비스는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, \n  카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n*본 UnionPay Diamond 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다. \n아래 대상 카드 발급 시 Unionpay Diamond 02 선택서비스가 제공됩니다.  \n	3808	006fb1d587a0ac8370ba2963bc881eafecf2f81157b5421a26d2e8c5456032eb	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:21:19.166396+00	SYSTEM	2026-11-03 05:21:19.166396+00	SYSTEM
20261103_000019	1	UnionPay Platinum\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nUnionPay UPI Platinum 공통서비스\n· 트립닷컴 국내외 항공권 10% 할인, 국내외 호텔 15% 할인 \n· DB손해보험 해외여행자 보험 기본상품 가입 시, 최대 3일 무료 \n· 클룩 해외 액티비티 예약 시 유니온페이 프리미엄 카드로 $100 이상 \n   결제 시 최대 $30 할인  \n· 마이리얼트립 국내 투어/티켓/숙소 등 결제 시 최대 10% 즉시 할인\n· 글로벌 원심(OneSIM) 무료 이용 서비스 제공 (4.1~)\nHotel\nAirport\n· 국내 특급호텔(약 45여개) 100여개 식음료 매장 5~15% 할인\n· 국내 특급호텔(약 43여개) 객실 5~40% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약 15여개) 스파 5~15% 할인 및 샘플 증정\n· 국내 특급호텔 (약 7여개) 로비라운지에서 음료 구매 시 \n   동반인 음료 무료 제공 (월 1회, 연 4회, 플래티늄 법인카드에 한함)\n· 싱가포르 마리나 베이 샌즈의 샌즈 리워드 라이프스타일 \n   엘리트 등급 멤버십 혜택 3개월간 제공\nTravel\n* UPI Platinum 서비스의 상세한 내용은 UnionPay 홈페이지(http://www.unionpaypremium.co.kr)를 통해 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 UPI 프리미엄 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 유니온페이 플래티늄 혜택 구매 사이트에서 결제 시 K공항리무진 할인\n  (1+1)\n· 인천공항 제휴 매장에서 아메리카노 결제 시 10% 할인\n· 경복궁면세점 인천공항점 $1 이상 구매 시 사은품 제공\n· 현대면세점 GOLD 등급 멤버십 제공 및 추가 3~8% 선불카드 할인 제공\n  (무역센터점, 인천공항점, 온라인몰/4월 중 오픈 예정)\n· 국내 골프장 온라인 예약 서비스 및 그린피 할인\n   (유니온페이 골프사이트에서 본인 인증 후 프리미엄 카드 결제 시 서비스 제공)\n· 국내 지정 골프장 클럽하우스 또는 스타트하우스에서 이용권 제시 시\n   커피(4잔) 30% 할인\n   (유니온페이 플래티늄 혜택 구매 사이트에서 결제 시 이용권 할인 서비스 제공)\nGlobal\n· 해외 컨시어지 서비스 제공 \n· 해외 긴급 의료지원 서비스 제공\n· 국내외 제휴 서비스 및 컨시어지 플랫폼 서비스 제공 \n- 유의사항\n  · 서비스 과정에서 실제로 발생하는 비용은 별도 청구 (UPI 홈페이지 참조)\n  · 해외 지원 서비스는 전부 유니온페이 프리미엄 콜센터로 전화상담 후 \n     서비스 제공 (콜센터 : 1670-8893, 24시간 연중무휴)\n- 유의사항\n  · 국내 특급호텔 객실 할인 및 스파 서비스는 유니온페이 프리미엄 콜센터를 통해\n     전화 상담 후 서비스 제공 (콜센터 1670-8810, 24시간 연중 무휴)\nGolf\nLife\nStyle\n서비스\n내용\n· 현대아울렛 전점에서 무료 음료 1잔(월 1회) 및 외국인 특화점에서 \n   추가 혜택(연 1회) 제공\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-05040호 (2026.04.10) / 준법심의 L-26-0517(2026.03.24)/ VI 260421-32\n* 아래의 UnionPay Platinum 서비스는 UnionPay Platinum 등급 카드 소지자에게 공통으로 제공됩니다.\n	2587	fa91cc8e823ee1c33b46d9798a7d763adbf7599f2ee17ff666d71c34ac488726	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:21:23.814442+00	SYSTEM	2026-11-03 05:21:23.814442+00	SYSTEM
20261103_000009	1	AMEX\nPlatinum Elite\n공통서비스\n* 아래의AMEX Platinum Elite 서비스는AMEX Platinum Elite 등급카드\n소지자에게공통으로제공됩니다.\n서비스\n내용\nTravel\nHotel\nDining\nShopping\nLifestyle\n서비스\n내용\n* 본AMEX Platinum Elite 서비스안내서는회원이발급받은카드\n상품안내장, 이용약관과함께교부되오니, 카드이용과관련한\n유의사항을반드시확인하시기바랍니다.\n* 본서비스는AMEX에서제공하는서비스로, 프리미엄서비스에\n대한구체적내용, 적용기준및유의사항등은\nwww.americanexpress.com/ko-kr/network → ‘아멕스카드\n전체혜택’에서사전에반드시확인하시기바랍니다.\n* 본AMEX Platinum  Elite 서비스는기간이명시되지않는한\n2026년1월1일~ 12월31일까지제공됩니다.\n* 현대면세점, 신라면세점, 신라아이파크면세점\n5~20% 할인\n* 꽃집청년들관엽10%, 화환15% 할인\n* 유니페어구두5% 할인및Shoe Care 쿠폰제공\n* 메종레페토서울30만원이상구매시5% 할인\n* 인천/김포/김해공항라운지성인요금동반\n2인까지30% 할인\n* 인천/김포공항국제선F&B 매장10% 할인\n* 하이파킹지정주차장(21개) 주차요금20% 할인\n* 카모아국내외렌터카요금5% 할인\n* 국내29개특급호텔객실5~50% 할인\n* 국내27개특급호텔F&B 5~10% 할인\n* 빌라르코라이, 그란멜리아호텔나트랑\n최대25% 할인\n* JW 메리어트호텔하노이조식및웰컴드링크제공\n* 구름에2박이상숙박시1박무료\n* 조선왕가호텔객실10~20% 할인\n* 락고재객실10% 할인\n* 백미당전메뉴(베이커리류제외) 중1개구매시,\n아메리카노, 라떼, 소프트아이스크림중택1 \n제공(월1회, 연2회)\n* 카페아티제제조음료구매시, \n아메리카노쁘띠사이즈제공(월1회, 연6회)\n* 생어거스틴, 키친동백, 다인힐, 무탄10~20% 할인\n또는서비스메뉴제공\n* 수도권30여개골프장주중골프부킹대행서비스\n제공(연2회)\n* 리프레쉬골프10% 할인쿠폰6장제공\n* 사이판월드리조트골프패키지최대40% 할인\n* 국내특급호텔(4개) 스파정규프로그램할인\n*국내특급호텔(6개) 스파및더트리니티스파강남점\n5~20% 할인\n* 포브스코리아, 월간중앙, 이코노미스트1년구독료\n50% 할인\n* 오픈갤러리그림렌탈첫이용5만원할인\n* TURU Car Wash 세차및상품10% 할인\n* 인스타워시출장세차5~10% 할인\n* 서프홀릭서핑강습료5% 할인\n여신금융협회심의필제2026 - C1a - 05150호( 2026.04.13 )/ 준법심의L-26-0404 (2026.03.03)\n	1268	65803175baa10b8927c5207d6cd462359e85cac10650ebc3e65c459ce7eab8a5	MIXED	PyMuPDF	1.28.2	\N	2026-11-03 05:20:34.783526+00	SYSTEM	2026-11-03 05:20:34.783526+00	SYSTEM
20261103_000009	2	*필요이상의신용카드발급및사용은개인신용평점이나이용한도등에\n영향을미칠수있습니다.\n*카드발급신청시상품설명서및상품약관을반드시확인하시기바랍니다.\n*신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이제한될\n수있습니다.\n*카드이용대금과이에수반되는모든수수료를지정된대금결제일에\n상환하여야합니다.\n*금융소비자는해당상품또는서비스에대하여설명을받을권리가있습니다.\n*본상품설명서는법령및내부통제기준에따른절차를거쳐제공됩니다.\n*자세한내용은하나카드홈페이지(www.hanacard.co.kr)를참고하시거나\n고객센터로문의바랍니다.\n*상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용평점이\n하락할수있습니다.\n*개인신용평점하락시금융거래와관련된불이익이발생할수있습니다.\n*일정기간원리금을연체할경우, 모든원리금을변제할의무가발생할수\n있습니다.\n*연체이자율(약정이율+최대3%)은회원별·이용상품별로차등적용되며,\n법정최고금리(20%)를초과하지않습니다.\n※단, 연체발생시점에약정이율이없는경우는아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월)유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부계약기간의\n유이자할부금리\n- 그외의경우: 약정이율은상법상상시법정이율과상호금융가계자금\n대출금리*중높은금리적용\n*한국은행에서매월발표하는가장최근의비은행금융기관가중평균\n대출금리(신규대출기준)\n여신금융협회심의필제2026 - C1a - 05149호( 2026.04.13 )\n/ 준법심의L-26-0406 (2026.03.05)\nAMEX Platinum Elite 선택서비스\nAMEX\nPlatinum Elite\n선택서비스\nAMEX Platinum Elite 선택서비스\n아래대상카드발급시AMEX Platinum Elite\n선택서비스가제공됩니다.\n상품유형\n대상카드\nAMEX Platinum\nElite\n하나CLUB H\n아메리칸익스프레스리저브카드\n*AMEX 프리미엄서비스의상세한내용은AMEX 홈페이지\n(www.americanexpress.com/ko-kr/network) 또는하나카드\n홈페이지에서반드시확인하시기바랍니다.\n*본AMEX 프리미엄서비스안내서는회원이발급받은카드상품안내\n장, 이용약관과함께교부되오니, 카드이용과관련한유의사항을반\n드시확인하시기바랍니다.\n*본AMEX 프리미엄서비스는2026년1월1일~ 12월31일까지제공\n됩니다.\n공항커피서비스\n서비스혜택\n¶인천/김포공항내주요커피매장핫아메리카노(S) 무료\n이용조건\n¶통합월1회, 연12회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부50만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액50만원미만시에도서비스제공)\n이용방법\n¶대상카드와당일출국항공권함께제시\n구분\n대상가맹점\n인천국제공항\n제1여객터미널\n(면세구역)\n배스킨라빈스31, 커피빈, 잠바주스,엔제리너스,리브팜,던킨도너츠,\n크리스피크림도넛,커피앳웍스\n인천국제공항\n제2여객터미널\n(면세구역)\n커피앳웍스, 던킨도너츠, 쇼콜라팔레트, 크리스피크림도넛,\n잠바주스,리나스,베스킨라빈스31\n김포국제공항\n(일반구역)\n옐로우인더화이트\n공항리무진/공항철도서비스\n서비스혜택\n¶공항리무진및공항철도편도티켓무료서비스\n이용조건\n¶통합일1회, 연12회서비스제공\n¶아멕스프리미엄카드로50만원이상항공권구매후카드와\ne티켓함께제시(탑승일주일내e티켓제시, 본인항공권에\n한함, 합산불가)\n이용방법\n대상가맹점\n이용방법\n인천국제공항\n제1여객터미널\n통합매표소\n¶위치: (내부) 4.6.9.11번게이트유인정산소\n¶해당노선: 인천공항출발전노선\n¶이용안내: 티켓금액1만원초과시차액본인부담\n(현금결제만가능)\n인천국제공항\nK리무진\n직영매표소\n¶위치: 제1여객터미널3층일반지역8번출입구부근K Books \n매장, 제2여객터미널3층중앙K Books 매장\n¶해당노선: 6701(시청방면), 6702(남산방면), 6703(강남방면), \n6705(잠실방면)\n¶이용안내: 4개노선에한함, 차액부담없음\n공항철도\n온라인예약\n발권시스템\n¶AREX 공항철도직통열차홈페이지(www.airportrailroad.com)\n또는공항철도앱\n1. 승차권결제페이지에서할인선택후제휴카드정보입력란에\n정보입력\n2. 승차권발권후QR 인식하여게이트입장\n유의사항\n¶공항리무진은운영시간내에만서비스제공, 휴식시간에는서비스제공\n불가합니다.\n¶공항철도는현장매표소에서서비스적용불가하며, 공항철도앱을통해\n예약발권후이용가능합니다.\n¶제1터미널에서키오스크발권시서비스제공불가하며, 구매처에서발권\n후환불희망해도서비스이용으로간주되어서비스제공횟수가차감됩니다.\n	2142	b200bafc41204d7e2a90d4dcf04e02ed4bf80aa90dca24af1436e688699ed7f3	MIXED	PyMuPDF	1.28.2	\N	2026-11-03 05:20:34.783526+00	SYSTEM	2026-11-03 05:20:34.783526+00	SYSTEM
20261103_000009	3	서비스혜택\n¶인천공항제1,2여객터미널및김포공항국내선무료발렛\n파킹서비스제공\n이용조건\n¶통합월2회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부50만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액50만원미만시에도서비스제공)\n이용방법\nhttps://maxervemparking.com/valet/\n차량인수후출차시주차요금별도정산\n차량인수후출차시주차요금별도정산\n※ 공항이용객이많은연휴기간, 명절, 여행성수기시즌등에는\n사전예약후이용하시기바랍니다.\n(예약: https://valet.amanopark.co.kr/#main)\n유의사항\n¶서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하셔야\n합니다.\n¶상기서비스는발렛파킹비용에만적용되므로, 주차요금은별도로정산\n하셔야합니다.\n¶여객터미널3층승용차전용도로에서5분이상정차시과태료가부가될\n수있습니다.\n¶인천공항제1 여객터미널\n¶인천공항제2 여객터미널\n¶김포공항국내선\n인천/김포공항발렛파킹서비스\nAMEX Platinum Elite 선택서비스\nAMEX Platinum Elite 선택서비스중인천/김포공항발렛파킹, 특급호텔발렛파킹, Be My Guest 서비스, 공항리무진/철도서비스, 공항커피/서점할인을하나카드에서제공합니다.\n공항Books Store 할인서비스\nBe My Guest 서비스\n서비스혜택\n¶대상점에서도서1권이상, 5천원이상결제시3천원할인\n이용조건\n¶통합월1회, 연12회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부50만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액50만원미만시에도서비스제공)\n대상가맹점\n¶인천공항Books Store 전매장\n서비스혜택\n¶호텔,패밀리레스토랑6만원이상결제시3만원현장할인\n¶ 호텔델리4만원이상결제시2만원현장할인\n이용조건\n¶통합월1회, 연3회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부50만원이상이용시\n서비스제공(최초카드사용등록후다음달말일까지는지난\n달카드이용금액50만원미만시에도서비스제공)\n¶다른프로모션및혜택과중복적용불가및일부기간내\n서비스이용이제한될수있음\n¶각대상가맹점별유의사항은AMEX 홈페이지참조\n구분\n대상가맹점\n호텔\n레스토랑\n포시즌스호텔서울(더마켓키친), 콘래드서울(아트리오,SUT.\nThe Butcher’s Edge), \nJW메리어트동대문스퀘어서울(타볼로24, BLT스테이크),\n반얀트리클럽앤스파서울(그라넘다이닝라운지,페스타바이충후),\n그랜드인터컨티넨탈서울파르나스(그랜드키친), \n앰배서더서울풀만(더킹스,풀하우스테라스), 안다즈서울강남\n(조각보바이츠앤와인,조각보키친, 조각보미트앤코),\n부산웨스틴조선(까밀리아, 오킴스, 파노라마라운지, 셔블),\n파라다이스부산(라스칼라,사까에), 더블트리바이힐튼서울판\n교(데메테르, 루프탑레스토랑&바), 서울신라호텔(콘티넨탈,라\n연,팔선,아리아께,더파크뷰), 웨스틴조선서울(아리아,루브리카,\n나인스게이트),그랜드워커힐서울(온달), 노보텔앰배서더동대\n문(푸드익스체인지,고메바&다이닝), 파르나스제주(콘페티), \n그랜드조선제주(아리아),그랜드조선부산(아리아,팔레드신,라\n운지앤바테라스292),호텔나루서울엠갤러리(부아쟁), 파크하\n얏트부산(리빙룸, 다이닝룸), 임피리얼팰리스서울(뷔페패밀리\n아, 천산),파크하얏트서울(더팀버하우스)\n패밀리\n레스토랑\nChai797(전국매장), 정육점(전국매장), 63스퀘어(워킹온더클라\n우드, 터치더스카이, 슈치쿠, 백리향), 아웃백스테이크하우스\n(전국매장, 딜리버리제외)\n호텔델리\n포시즌스서울(컨펙션즈바이포시즌스), 콘래드서울(플레임즈),\n앰배서더서울풀만(1955 그로세리아), 노보텔앰배서더동대문\n(더델리),그랜드조선부산(조선델리), 롯데호텔부산(델리카한스,\n더라운지앤바), 부산웨스틴조선(조선델리),\n호텔나루서울엠갤러리(마포에이트),그랜드머큐어임피리얼팰\n리스서울(카페델마르)\n¶원활한서비스이용을위해서비스이용전제휴처에이용가능여부를\n확인하시기바랍니다\n유의사항\n¶호텔정책에따라해당호텔객실및식음료업장(연회장제외) 이용한본인\n회원에한해제공되며, 영수증미지참시발렛파킹비용과주차요금이청구될\n수있습니다.\n¶1일3시간무료주차제공되며, 3시간초과이용시주차요금별도부과됩니다.\n¶ JW 메리어트호텔서울(50,000원이상), 몬드리안서울이태원(25,000원이상)\n, 포시즌스서울(30,000원이상)의호텔이용영수증을제시하는경우에한해\n서비스가제공되며이용확인증미지참시에는주차요금과발렛파킹이용료\n를현장에서지불하셔야합니다.\n¶파크하얏트서울은호텔정책에따라당일호텔에서2만원이상이용한영수\n증을제시하는경우에한해무료주차서비스가제공됩니다.\n¶서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하셔야\n합니다.\n¶원활한서비스이용을위해서비스이용전제휴처에이용가능여부를\n확인하시기바랍니다.\n¶국내주요특급호텔무료발렛파킹서비스제공\n이용방법\n¶호텔발렛파킹부스에서비스요청후주차권수령\n¶차량인수시해당카드와주차권및호텔이용영수증제시\n¶ 호텔직원서비스이용가능여부확인후서비스제공\n¶호텔통합월2회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부50만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액50만원미만시에도서비스제공)\n서비스혜택\n이용조건\n특급호텔발렛파킹서비스\n지역\n대상호텔\n서울\n앰배서더서울풀만호텔\n그랜드워커힐서울\n그랜드하얏트서울\n몬드리안서울이태원\n노보텔앰배서더서울강남\n노보텔엠배서더서울동대문\n르메르디앙서울명동\n메이필드호텔\n코트야드메리어트서울타임스퀘어\n메리어트이그제큐티브아파트먼트\n반얀트리클럽앤스파서울\n비스타워커힐서울\n서울신라호텔\n더플라자\n콘래드서울\n파크하얏트서울\nJW 메리어트동대문스퀘어\nJW 메리어트호텔서울\n안다즈서울강남\n포시즌스서울\n지방\n그랜드하얏트인천\n그랜드조선부산\n파크하얏트부산\n호텔인터불고대구\n힐튼경주\n	2725	14892bb325ad82b8f3b15741a67e69986ab35b6fd30b6ab1add017a484a5ffa5	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:20:34.783526+00	SYSTEM	2026-11-03 05:20:34.783526+00	SYSTEM
20261103_000010	1	AMEX\nPlatinum\n공통서비스\n* 아래의AMEX Platinum 서비스는AMEX Platinum 등급카드\n소지자에게공통으로제공됩니다.\n서비스\n내용\n* 인천/김포/김해공항라운지성인요금동반2인까지\n30% 할인\n* 인천/김포공항국제선F&B 매장10% 할인\n* 하이파킹지정주차장(21개) 주차요금20% 할인\n* 카모아국내외렌터카요금5% 할인\nTravel\nHotel\nDining\n* 현대면세점, 신라면세점, 신라아이파크면세점\n5~20% 할인\n* 꽃집청년들관엽10%, 화환15% 할인\n* 유니페어구두5% 할인및Shoe Care 쿠폰제공\n* 메종레페토서울30만원이상구매시5% 할인\nShopping\nLifestyle\n서비스\n내용\n* 본AMEX Platinum 서비스안내서는회원이발급받은카드\n상품안내장, 이용약관과함께교부되오니, 카드이용과관련한\n유의사항을반드시확인하시기바랍니다.\n* 본서비스는AMEX에서제공하는서비스로, 프리미엄서비스에\n대한구체적내용, 적용기준및유의사항등은\nwww.americanexpress.com/ko-kr/network → ‘아멕스카드\n전체혜택’에서사전에반드시확인하시기바랍니다.\n* 본AMEX Platinum 서비스는기간이명시되지않는한2026년\n1월1일~ 12월31일까지제공됩니다.\n* 국내29개특급호텔객실5~50% 할인\n* 국내27개특급호텔F&B 5~10% 할인\n* 빌라르코라이, 그란멜리아호텔나트랑\n최대25% 할인\n* JW 메리어트호텔하노이조식및웰컴드링크제공\n* 구름에2박이상숙박시1박무료\n* 조선왕가호텔객실10~20% 할인\n* 락고재객실10% 할인\n* 백미당전메뉴(베이커리류제외) 중1개구매시,\n아메리카노, 라떼, 소프트아이스크림중택1 \n제공(월1회, 연2회)\n*카페아티제제조음료구매시, 아메리카노쁘띠사이즈\n제공(월1회, 연6회)\n*생어거스틴, 키친동백, 다인힐, 무탄10~20% 할인또는\n서비스메뉴제공\n* 리프레쉬골프10% 할인쿠폰6장제공\n* 사이판월드리조트골프패키지최대40% 할인\n* 국내특급호텔(6개)스파및더트리니티스파강남점\n5~20% 할인\n* 포브스코리아, 월간중앙, 이코노미스트1년구독료\n50% 할인\n* 오픈갤러리그림렌탈첫이용5만원할인\n* TURU Car Wash 세차및상품10% 할인\n* 인스타워시출장세차5~10% 할인\n* 서프홀릭서핑강습료5% 할인\n여신금융협회심의필제2026 - C1a - 05144호( 2026.04.13 )/ 준법심의L-26-0405 (2026.03.03)\n	1179	1bf04e228c0c696be9acac7c17e37d77f7d47d7a26e3f2243387c07e7f2d7313	MIXED	PyMuPDF	1.28.2	\N	2026-11-03 05:20:39.726129+00	SYSTEM	2026-11-03 05:20:39.726129+00	SYSTEM
20261103_000010	2	AMEX Platinum 선택서비스중특급호텔발렛파킹, 인천공항발렛파킹서비스를하나카드에서제공합니다.\n*필요이상의신용카드발급및사용은개인신용평점이나이용한도등에\n영향을미칠수있습니다.\n*카드발급신청시상품설명서및상품약관을반드시확인하시기바랍니다.\n*신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이제한될\n수있습니다.\n*카드이용대금과이에수반되는모든수수료를지정된대금결제일에\n상환하여야합니다.\n*금융소비자는해당상품또는서비스에대하여설명을받을권리가있습니다.\n*본상품설명서는법령및내부통제기준에따른절차를거쳐제공됩니다.\n*자세한내용은하나카드홈페이지(www.hanacard.co.kr)를참고하시거나\n고객센터로문의바랍니다.\n*상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용평점이\n하락할수있습니다.\n*개인신용평점하락시금융거래와관련된불이익이발생할수있습니다.\n*일정기간원리금을연체할경우, 모든원리금을변제할의무가발생할수\n있습니다.\n*연체이자율(약정이율+최대3%)은회원별·이용상품별로차등적용되며,\n법정최고금리(20%)를초과하지않습니다.\n※단, 연체발생시점에약정이율이없는경우는아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월)유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부계약기간의\n유이자할부금리\n- 그외의경우: 약정이율은상법상상시법정이율과상호금융가계자금\n대출금리*중높은금리적용\n*한국은행에서매월발표하는가장최근의비은행금융기관가중평균\n대출금리(신규대출기준)\nAMEX\nPlatinum 02\n선택서비스\n유의사항\n¶호텔정책에따라해당호텔객실및식음료업장(연회장제외) 이용한\n본인회원에한해제공되며, 영수증미지참시발렛파킹비용과주차\n요금이청구될수있습니다.\n¶1일3시간무료주차제공되며, 3시간초과이용시주차요금별도부과\n됩니다.\n¶파크하얏트서울은호텔정책에따라당일호텔에서2만원이상이용한\n영수증을제시하는경우에한해무료주차서비스가제공됩니다.\n¶서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하셔야\n합니다.\n¶원활한서비스이용을위해서비스이용전제휴처에이용가능여부를\n확인하시기바랍니다.\n¶국내주요특급호텔무료발렛파킹서비스제공\n이용방법\n¶호텔발렛파킹부스에서비스요청후주차권수령\n¶차량인수시해당카드와주차권및호텔이용영수증\n제시\n¶ 호텔직원서비스이용가능여부확인후서비스제공\n¶호텔통합월3회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부30만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액30만원미만시에도서비스\n제공)\n서비스혜택\n이용조건\n특급호텔발렛파킹서비스\n지역\n대상호텔\n서울\n앰배서더서울풀만호텔\n그랜드워커힐서울\n그랜드하얏트서울\n노보텔앰배서더서울강남\n안다즈서울강남\n서울가든호텔\n노보텔엠배서더동대문\n메이필드호텔\n르메르디앙서울명동\n반얀트리클럽앤스파서울\n비스타워커힐서울\n서울신라호텔\n파크하얏트서울\n콘래드서울\nJW 메리어트동대문스퀘어\n메리어트이그제큐티브아파트먼트서울\n지방\n그랜드하얏트인천\n힐튼경주\n호텔인터불고대구\n파크하얏트부산\n소노캄여수\nAMEX Platinum 02 선택서비스\n아래대상카드발급시AMEX Platinum 02 선택서비스가제공됩니다.\n상품유형\n대상카드\nAMEX\nPlatinum 02\nCLUB SK 카드\nClub SK 카드hiplus 선불하이패스\nCLUB SK Point 카드\n*AMEX 프리미엄서비스의상세한내용은AMEX 홈페이지\n(www.americanexpress.com/ko-kr/network) 또는하나카드\n홈페이지에서반드시확인하시기바랍니다.\n*본AMEX 프리미엄서비스안내서는회원이발급받은카드상품안내\n장, 이용약관과함께교부되오니, 카드이용과관련한유의사항을반\n드시확인하시기바랍니다.\n*본AMEX 프리미엄서비스는2026년1월1일~ 12월31일까지제공\n됩니다.\nAMEX Platinum 02 선택서비스\n서비스혜택\n¶인천공항제1,2여객터미널무료발렛파킹서비스제공\n이용조건\n¶통합월3회서비스제공\n¶지난달(1일~말일) 국내외일시불/할부30만원이상이용\n시서비스제공(최초카드사용등록후다음달말일까지\n는지난달카드이용금액30만원미만시에도서비스제공)\n이용방법\n차량인수후출차시주차요금별도정산\n※ 공항이용객이많은연휴기간, 명절, 여행성수기시즌등\n에는사전예약후이용하시기바랍니다.\n(예약: https://valet.amanopark.co.kr/#main)\n유의사항\n¶서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하\n셔야합니다.\n¶상기서비스는발렛파킹비용에만적용되므로, 주차요금은별도로\n정산하셔야합니다.\n¶여객터미널3층승용차전용도로에서5분이상정차시과태료가\n부가될수있습니다.\n¶원활한서비스이용을위해서비스이용전제휴처에이용가능여부를\n확인하시기바랍니다.\n¶인천공항제1 여객터미널\n¶인천공항제2 여객터미널\n인천공항발렛파킹서비스\n여신금융협회심의필제2026-C1a-05577호( 2026.04.20 )\n/ 준법심의L-26-0408 (2026.03.05)\n	2298	9a70420d71a86cc815b24e9d5a6411612a4ac0f2a3831790033d09086d368bc0	MIXED	PyMuPDF	1.28.2	\N	2026-11-03 05:20:39.726129+00	SYSTEM	2026-11-03 05:20:39.726129+00	SYSTEM
20261103_000011	1	Amex\nPlatinum\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n공통서비스 \n•상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 \n    하락할 수 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다. \n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며,\n    법정 최고금리(20%)를 초과하지 않습니다.\n   ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n    - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n    - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n    - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n* 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n* 계약 체결 전 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n* 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한 될 수 있습니다.\n* 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n* 소비자는 금융소비자보호법에 따라 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n* 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다. \n* 자세한 내용은 하나카드 홈페이지(www.hanacard.co.kr)를 참고하시거나\n  고객센터로 문의 바랍니다.\n  \n \n여신금융협회 심의필 제 2026-C1a-05144호(2026.04.13) / 준법심의 L-26-0405(2026.03.03) / VI 260818-31\nAMEX Platinum Platinum 공통서비스\n· 국내 29개 특급호텔 객실 5~50% 할인\n· 국내 27개 특급호텔 F&B 5~10% 할인\n· 빌라 르 코라이, 그란 멜리아 호텔 나트랑 최대 25% 할인\n· JW 메리어트 호텔 하노이 조식 및 웰컴드링크 제공\n· 구름에 2박 이상 숙박 시 1박 무료\n· 조선왕가호텔 객실 10~20% 할인\n· 락고재 객실 10% 할인\nDining\nTravel\n· 백미당 전 메뉴(베이커리류 제외) 중 1개 구매 시,\n   아메리카노, 라떼, 소프트아이스크림 중 택 1 제공 (월 1회, 연 2회)\n· 카페 아티제 제조 음료 구매 시, 아메리카노 쁘띠 사이즈 제공\n  (월 1회, 연 6회)\n· 생어거스틴, 키친동백, 다인힐, 무탄 10~20% 할인 또는    \n  서비스 메뉴 제공\nHotel\n* 본 AMEX Platinum 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용 약관과 함께 \n  교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 서비스는 AMEX에서 제공하는 서비스로, \n   프리미엄 서비스에 대한 구체적 내용, 적용기준 및 유의사항 등은 \n   www.americanexpress.com/ko-kr/network → ‘아멕스카드 전체 혜택’에서 \n   사전에 반드시 확인하시기 바랍니다.\n* 본 AMEX Platinum 서비스는 기간이 명시되지 않는 한 \n   2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n서비스\n내용\n· 인천/김포/김해공항 라운지 성인요금 동반 2인까지 30% 할인\n· 인천/김포공항 국제선 F&B 매장 10% 할인\n· 하이파킹 지정 주차장(21개) 주차 요금 20% 할인\n· 카모아 국내외 렌터카 요금 5% 할인\nLife\nStyle\n· 리프레쉬 골프 10% 할인 쿠폰 6장 제공\n· 사이판 월드리조트 골프 패키지 최대 40% 할인\n· 국내 특급호텔(5개) 스파 5~20% 할인\n· 포브스코리아, 월간중앙, 이코노미스트 1년 구독료 50% 할인\n· 오픈갤러리 그림 렌탈 첫 이용 5만원 할인\n· TURU Car Wash 세차 및 상품 10% 할인\n· 인스타워시 출장세차 5~10% 할인\n· 서프홀릭 서핑 강습료 5% 할인\nShopping\n서비스\n내용\n· 현대면세점, 신라면세점, 신라아이파크 면세점 5~20% 할인\n· 꽃집 청년들 관엽 10%, 화환 15% 할인\n· 유니페어 구두 5% 할인 및 Shoe Care 쿠폰 제공\n· 메종 레페토 서울 30만원 이상 구매 시 5% 할인\n* 아래의 AMEX Platinum 서비스는 AMEX Platinum 등급 카드 소지자에게 공통으로 제공됩니다.\n	2276	720e5bb963ae25ce578cba6938e4be1a4eeaa3ce46bc1a00783fa3dea80c19a4	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:20:44.573836+00	SYSTEM	2026-11-03 05:20:44.573836+00	SYSTEM
20261103_000011	2	Amex\nPlatinum 03\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\n선택서비스 \nAmex Platinum 선택서비스 중 특급호텔 발렛파킹, 인천공항/김포공항 발렛파킹 서비스를 하나카드에서 제공합니다.\nAmex Platinum 03 \n상품유형\n대상카드\nJADE Classic 카드\n서비스혜택\n이용조건\n이용방법\n국내 주요 특급호텔 무료 발렛파킹 서비스 제공\n호텔 통합 월 2회 서비스 제공\n지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n(최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액 \n50만원 미만 시에도 서비스 제공)\n - 호텔 발렛파킹 부스에 서비스 요청 후 주차권 수령\n- 차량 인수 시 해당 카드와 주차권 및 호텔 이용 영수증 제시\n- 호텔 직원 서비스 이용 가능 여부 확인 후 서비스 제공\n그랜드 하얏트 인천\n힐튼 경주\n호텔 인터불고 대구\n파크하얏트 부산\n소노캄 여수\n서울\n서울 외\n지역\n대상 호텔\n유의사항\n- 호텔 정책에 따라 해당 호텔 객실 및 식음료업장(연회장 제외) 이용한 본인 회원에 한해 제공되며, \n   영수증 미지참 시 발렛파킹 비용과 주차 요금이 청구될 수 있습니다.\n- 1일 3시간 무료 주차 제공되며, 3시간 초과 이용 시 주차요금 별도 부과됩니다.\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능여부를 확인하시기 바랍니다. \n앰배서더 서울 풀만 호텔\n그랜드 워커힐 서울\n그랜드 하얏트 서울\n노보텔 앰배서더 서울 강남\n노보텔 앰배서더 서울 동대문\n안다즈 서울 강남\n서울 가든 호텔\n메이필드 호텔\n르메르디앙 서울 명동\n반얀트리 클럽 앤 스파 서울\n비스타 워커힐 서울\n서울 신라 호텔\n파크 하얏트 서울 호텔\n콘래드서울\nJW 메리어트 동대문 스퀘어\n메리어트 이그제큐티브 아파트먼트 서울\n특급호텔 발렛파킹 서비스\n아래 대상 카드 발급 시 Amex Platinum 03 선택서비스가 제공됩니다.\n* Amex 프리미엄 서비스의 상세한 내용은 Amex 홈페이지\n  (http://www.americanexpress.com/ko-kr/network/)를 통해 확인하시기  바랍니다.\n* 본 Amex 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품 안내장, 이용약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을  반드시 확인하시기 바랍니다.\n* 본 Amex 프리미엄 서비스는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\nAmex Platinum 03 선택서비스\n사전 예약처\n제2여객터미널  \n김포공항 국내선\n \n주차 시 : \n① 단기주차장 지하1층 서편 주차구역 110~112번 진입\n② 파란색 유니폼 착용 공식 주차대행 직원에게 발렛 요청\n③ 차량 접수증 알림톡 발송\n출차 시 :\n① 동편 단기주차장 지하1층 210번 고객대기실로 이동\n② 정산소에서 아멕스 프리미엄 카드 제시 및 주차장소 확인\n③ 차량 인수 후 출차 시 주차요금 별도 정산\n※ 공항 이용객이 많은 연휴기간, 명절, 여행 성수기 시즌 등에는\n     사전 예약 후 이용하시기 바랍니다.\n주차 시 : \n① 국내선 청사 출발층(2층) 제일 우측 라인(하늘색)따라 진입             \n② 오렌지색 유니폼 착용 공식 대행 직원에게 발렛파킹 요청             \n③ 차량 상태 점검 후 차량 인도 및 차량보관증 수령\n출차 시 :\n① 출발지 항공기 탑승 전 차량보관증에 있는 연락처로 차량 출차 요청\n② 조기 출발로 비행 일정이 변경된 경우, 반드시 사전에 차량보관증에\n    있는 연락처로 변경사항 전달 및 차량 출차 요청\n③ 차량 인수시, 접수증과 아멕스 프리미엄 카드 제시하여 단말기를 \n     통해 서비스 이용 가능여부 확인 후 서비스 무료 제공             \n④ 차량인수 후 출차 시, 주차 요금 별도 정산\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 상기 서비스는 발렛파킹 비용에만 적용되므로, 주차요금은 별도로 정산하셔야 합니다.\n- 여객터미널 3층 승용차전용도로에서 5분 이상 정차 시 과태료가 부가될 수 있습니다.\n- 원활한 서비스 이용을 위해 서비스 이용 전 제휴처에 이용 가능여부를 확인하시기바랍니다. \n인천공항 1터미널 https://Maxerve-mparking.com/valet\n인천공항 2터미널 https://valet.amanopark.co.kr/#/main\n김포공항(사전예약 없이 이용가능)\n서비스혜택\n이용조건\n제1여객터미널  \n이용방법\n인천공항 제 1,2여객터미널, 김포공항 무료 발렛파킹 서비스 제공\n통합 월 2회 서비스 제공\n지난달(1일~말일) 국내외 일시불/할부 50만원 이상 이용 시 서비스 제공\n(최초 카드 사용등록 후 다음달 말일까지는 지난달 카드 이용금액 \n50만원 미만 시에도 서비스 제공)\n \n주차 시 : \n① 지하 1층 단기주차장 A구역 이동 후 Maxerve 유니폼 착용 공식\n     주차대행 직원에게 발렛 요청\n② 모바일 접수증 문자 발송 (카카오톡 접수증)\n출차 시 :\n① 입국 후 주차대행 접수증에 안내된 출차 장소로 이동\n     (지하 3층 A32구역 또는 H38 구역)\n② 유인정산소에서 모바일 접수증 제시 및 “제휴카드승인” 처리 후\n     차량 인수\n③ 주차장 출차 시, 주차요금은 별도정산\n※ 사전예약 고객 대상으로 서비스 제공, 현장상황에 따라 당일 서비스\n     요청 고객도 접수 가능\n인천공항 · 김포공항 발렛파킹 서비스\n•상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 \n    하락할 수 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다. \n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며,\n    법정 최고금리(20%)를 초과하지 않습니다.\n   ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n    - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n    - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n    - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n* 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n* 계약 체결 전 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n* 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한 될 수 있습니다.\n* 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n* 소비자는 금융소비자보호법에 따라 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n* 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다. \n* 자세한 내용은 하나카드 홈페이지(www.hanacard.co.kr)를 참고하시거나\n  고객센터로 문의 바랍니다.\n  \n \n여신금융협회 심의필 제 2026-C1a-11010호(2026.07.24) / 준법심의 L-26-2050(2026.06.09) / VI 260727-32\n(이용가능시간 05:00~21:00 / 출차는 24시간 가능)\n	3671	3e125f38b4f740f23212be786d9307ba1987b2c878ab447736f029471423153e	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:20:44.573836+00	SYSTEM	2026-11-03 05:20:44.573836+00	SYSTEM
20261103_000012	1	JCB Platinum\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nJCB Platinum 공통서비스\n*  JCB Prestige 서비스의 상세한 내용은 JCB 홈페이지(www.kr.jcb)를 통해 확인하시기 바랍니다.\n*  본 JCB Prestige 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n*  본 JCB Prestige 서비스는 이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-05514호(2026.04.17) / 준법심의 L-26-0521/ VI 260423-31\nDining : 다이닝서비스\n[일본 다이닝 서비스(1+1)]\n• 일본 최고 수준의 레스토랑에서 코스메뉴를 2인 이상 예약 시, \n 1인에 한해 무료 제공\n \nHotel : 호텔서비스\n[국내 특급호텔 할인 서비스]\n• 국내 33개 특급호텔에서 F&B(식음료) 및 객실, 스파 할인 서비스\nTravel : 여행서비스\n[해외 렌터카 서비스(Hertz)]\n• 60여 개국 Hertz 렌터카 할인 요금에서 추가 10% 할인 또는\n[일본 유니버설 스튜디오 재팬 JCB 전용 라운지 무료 이용 서비스]\n• 일본 유니버셜 스튜디오 재팬 JCB 라운지 본인 외 3명 (유아 포함) 무료 입장\n   (~3.31)\n[해외 Data 서비스(와이드 모바일) 할인가격 제공]\n• 해외  Data 서비스(와이드 모바일) 할인가격 제공\nAirport : 공항서비스\n[해외 공항 라운지 서비스(일본, 하와이)]\n• 일본/하와이의 주요 공항 라운지 서비스를 최대 6회 무료 이용 (~3.31)  \n * 대상 라운지는 JCB 홈페이지 참조\n[해외 공항 라운지 서비스(기타국가)_라운지키]\n• 중국, 싱가포르, 태국, 대만, 말레이시아 등 라운지를 연 2회 무료 이용가능\n * 대상 라운지는 JCB 홈페이지 참조\n \nShopping : 쇼핑서비스\n[면세점 할인 서비스]\n• 동화면세점 : 15% 현장 할인 전용 쿠폰 지급\n• 현대백화점면세점(무역센터점, 동대문점, 인천공항(T1, T2)\n     : 온·오프라인 5~15% 할인 혜택 멤버십 카드 발급\n• 신라 아이파크 면세점 : 오프라인 전용 5~15% 할인 혜택 골드카드 발급\nConcierge : 컨시어지서비스\n[JCB 컨시어지]\n• JCB 프리미엄 카드 회원을 위한 컨시어지 서비스 제공\n \n* 한국소재 시 02-755-4977(9:00~18:00, 일요일 및 공휴일 휴무)\n \n   해외소재 시 각국 전화번호는 JCB 홈페이지 참조\n \n* 한국컨시어지 데스크에서는 프리미엄 서비스에 관한 안내만 가능\n \n   그 외의 각종 문의 및 예약 대행 관련문의는 해당 해외 컨시어지 데스크로 문의\nGolf : 골프서비스\n[해외(일본) 골프 코스 우대 서비스]\n• 일본의 각종 유명 경기가 개최되는 코스에서 우대 서비스 제공\n * 코스 및 코스 별 서비스는 JCB 홈페이지 참조\n \n정상가 5~20% 할인 (~3.31)\n	2345	34008ec7cae71058c449ae4210c77574b502528df8ed0e9be01d9a440e0c6d0f	MIXED	PyMuPDF	1.28.2	\N	2026-11-03 05:20:49.506204+00	SYSTEM	2026-11-03 05:20:49.506204+00	SYSTEM
20261103_000013	1	Mastercard\nPlatinum\n단기카드대출(현금서비스) / 장기카드대출(카드론)\n카드대출\nMastercard Platinum 공통서비스\n· LANE4 AIR 서비스 3만원 할인 (왕복 예약 시 총 6만원 할인)\nHotel\nAirport\n· Trip.com 호텔 6%, 항공 3%, 액티비티 5% 할인\n· Agoda.com 8% 할인 (최대 USD 30),\n  (예약: 26.1.1~26.3.31 / 숙박: 26.1.1~26.12.31)\n· Hotels.com 8% 할인 (최대 USD 50),\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Expedia.com 8% 할인 (최대 10만원),\n  (예약: 26.1.1~26.12.31 / 숙박: 26.1.1~27.6.30)\n· Rakuten Travel 10% 할인 (최대 USD 30),\n  (예약: 26.1.1~26.12.30 / 숙박: 26.1.1~27.2.28)\n· Qatar Airways 항공권 최대 10% 할인\n· On Vacation 럭셔리호텔/크루즈 상품 5% 할인\n· Kkday 티켓/교통/액티비티 5% 할인, \n  해외투어/eSIM 10% 할인 (최대 USD 10),\n  (예약: 26.1.1~26.12.31 / 여행: 26.1.1~27.3.31)\n· Oh Show 60분 자유의 여신상 크루즈 티켓 1+1,\n  뉴욕 브로드웨이 뮤지컬 티켓 3% 할인, \n  라스베가스 쇼 및 하와이 태양의서커스 티켓 3% 할인\n· 제주도닷컴 패키지 5%, 렌터카 12%, 국내선 항공권 발권대행수수료 무료\n· Europcar 최대 15% 할인\n· 롯데렌터카 최대 제주 90%, 내륙 65% 할인 제공\n· Hertz 렌트 예약 시 10% 할인, 멤버십 무료 가입\n· 짐캐리 최대 20% 할인\n· Airalo eSIM 최대 20% 할인 (최대 USD 100)\n· 와이드모바일 와이파이도시락 15%, 도시락 eSIM/USIM 10% 할인\n· 유심사 해외 eSIM/USIM 20% 할인\nTravel\n* 본 Mastercard Platinum 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용 약관과 함께 \n   교부되오니, 카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 서비스는 Mastercard 에서 제공하는 서비스로 , 프리미엄 서비스에 대한 구체적 내용, 적용기준 및 \n   유의사항 등은 http://www.mastercard.co.kr → ‘Premium Mastercard Services’에서 \n   사전에 반드시 확인하시기 바랍니다.\n* 본 Mastercard Platinum 서비스는 기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지\n   제공됩니다.\n서비스\n내용\n· 국내 특급호텔(약 39여개) F&B 5~15% 할인\n· 국내 특급호텔(약 43여개) 객실/패키지 5~50% 할인 또는 무료 업그레이드\n· 국내 특급호텔(약 15여개) 스파 10~20% 할인\n· Trump Hotels 10% 할인 \n· Outrigger Hotels and Resorts 5% 할인\n· KA LA’I Waikiki Beach, LXR Hotels & Resorts 10% 할인 및 조식 제공\n· 코타키나발루 수트라하버 리조트 클럽 및 스위트 객실 25% 할인, \n  골드 카드 10% 할인\n· 신라면세점 골드플러스 멤버십 제공\n   (오프라인 최대 15%, 온라인 최대 20% 할인,\n    인터넷점 S.Rewards 7,000P 제공)\n· 신세계면세점 골드 멤버십 제공 (최대 15% 할인)\n· 트래블메이트 캐리어/여행용품 12% 추가 할인\n· 해외 프리미엄 아울렛 VIP 패스 제공 (10% 할인)\n· 몽쥬약국 구매 금액별 10~15% 할인 및 최대 15% 면세 혜택\n· Mastercard E-Commerce Protection 해외 온라인 직구 보험 \n   연간 최대 23만원 보상 \nShopping\n· 15개국 48개 골프장 그린피 25% 할인 (연 4회), (~6.30)\n· 코타키나발루 수트라하버 리조트 골프&컨트리클럽 그린피 본인 면제\n· LANE4 Golf 골프장 이동 서비스 5만원 할인\n· Car up 프리미엄 카 케어 서비스 20% 할인\n· 내셔널지오그래픽 트래블러 정기구독 결제 20% 할인\nGolf\nLife\n서비스\n내용\n  \n공통서비스 \n \n \n•상환능력에 비해 신용카드의 사용액이 과도할 경우, 귀하의 개인신용평점이 하락할 수 \n 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율 + 최대 3%)은 회원별·이용상품별로 차등 적용되며, \n 법정 최고금리(20%)를 초과하지 않습니다.\n ※ 단, 연체 발생 시점에 약정이율이 없는 경우 아래와 같이 적용함\n - 일시불 거래 연체 시 : 거래 발생 시점의 최소기간(2개월) 유이자 할부 금리 \n - 무이자 할부 거래 연체 시 : 거래 발생 시점의 동일한 할부 계약기간의 유이자 할부 금리 \n - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은  금리 적용\n * 한국은행에서 매월 발표하는 가장 최근의 비은행 금융기관 가중평균대출금리 (신규대출 기준)\n * 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n * 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n * 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 \n   문의 바랍니다.\n * 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n * 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n * 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n * 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n여신금융협회 심의필 제 2026-C1a-003747호 (2026.03.20) / 준법심의 L-26-0342 (2026.02.04) / VI 260327-33\n* 아래의 Mastercard Platinum 서비스는 Mastercard Platinum 등급 카드 소지자에게 공통으로 제공됩니다.\n	3114	1b3cb0408d945dbc5e109218a39e821d886a41fef229ecfda070c49961093cb2	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:20:52.903041+00	SYSTEM	2026-11-03 05:20:52.903041+00	SYSTEM
20261103_000020	1	Visa\nInfinite \n공통서비스\n서비스\n· 진에어빠른체크인및빠른짐찾기서비스(연4회, 최대4인)\n· 카타르항공최대15% 할인\n(예약기간: ~26.10.31 / 여행기간: ~27.3.31)\n· 일본항공일본행항공권8% 할인(25.10.1~26.3.31)\n· 공항의전서비스(yQ Meet & Assist) 25% 할인\n내용\n· 전세계900여개호텔Visa Luxury Hotel Collection 혜택제공\n· Hotels.com 쿠폰코드입력시최대8% 할인(숙박기간: ~27.6.30)\n· Booking.com 최대7% 월렛포인트캐시백(매월1일~15일한정)\n· Agoda 국내, 해외호텔3박투숙시2박요금만결제\n(숙박기간: ~27.12.31)\n· Expedia 8% 할인(숙박기간: ~27.6.30)\n· IHG Hotel&Resorts 20% 할인(숙박기간: ~27.1.3)\n· Accor China 중화권호텔최소2박예약시20% 할인(~26.9.30)\n· 반얀트리최소2박숙박시20%할인\n(예약기간: ~26.5.31 / 숙박기간: ~26.8.31)\n· GHA 디스커버리멤버십무상업그레이드\n· Ascott 프로모션기간내사용시리워드등급업그레이드\n서비스(~27.11.30)\n· 국내특급호텔(약68여개) F&B 5~20% 할인\n· 국내특급호텔(약73여개) 객실/패키지5~60% 할인\n· 국내호텔스파(약22여개) 10~20% 할인\n· 국내부티크호텔(약23여개) 객실/F&B 5~50% 할인\n· 국내특급호텔(약6여개) 로비라운지5~20% 할인\n· Hertz 해외렌터카기본10% 할인및추가혜택(~26.3.31)\n· AVIS 해외렌터카최대35% 할인\n· Rentalcars.com 10% 추가할인(~26.4.30)\n· Movv 이동서비스국내1.5~3.5만원, 해외8% 할인\n· 아시아태평양공항픽업서비스\nTBR Luxury Airport Transfer 20% 할인\n· 굿럭해외공항짐배송및보관20% 할인\n· 굿럭인천공항입국시교통약자짐찾기대행및배송서비스할인\n· Trip.com 최대6%할인\nHotel\nAir &\nAirport\nTravel\n· 비자엘리트다이닝최대20% 할인혜택제공(~26.8.31)\n· 트립쿠폰멤버십무료제공\n· 하와이올로마나골프장그린피15% 할인및\n연습볼1버켓무료\n· Visa 컨시어지제공\n전화080-4880-880, 홈페이지www.concierge-asia.visa.com\n카카오톡“Visa 컨시어지” 채널추가\nDinig &\nLifestyle\nShopping\n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용\n평점이하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이\n발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가\n발생할수있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등\n적용되며, 법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) \n유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부\n계약기간의유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융\n가계자금대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관\n가중평균대출금리(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도\n등에영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기\n바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금\n결제일에상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가\n있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐\n제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를\n참고하시거나고객센터로문의바랍니다.\n여신금융협회심의필제2026 - C1a - 05179호( 2026.04.13 ) / 준법심의L-26-0466 (2026.03.16)\n* 아래의Visa Infinite 서비스는Visa Infinite 등급카드\n소지자에게공통으로제공됩니다.\n· 롯데면세점(국내)고객면세점할인및\n회원등급업그레이드혜택제공(~26.6.30)\n· 롯데면세점싱가포르차이공항고객면세점할인\n(~26.10.16)\n· 현대백화점면세점블랙멤버십제공(최대20% 할인)\n· Mitsui Outlet Park에서최대10%할인(~27.11.30)\n* 본Visa Infinite 서비스안내서는회원이발급받은카드\n상품안내장, 이용약관과함께교부되오니, 카드이용과관련한\n유의사항을반드시확인하시기바랍니다.\n* 본서비스는Visa에서제공하는서비스로, 프리미엄서비스에\n대한구체적내용, 적용기준및유의사항등\nhttp://www.visakorea.com → ‘Visa 인피니트’에서사전에\n반드시확인해주시기바랍니다.\n* 본Visa Infinite 서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n	2407	852a69cabdc35c3610682c8fefd699c0a33e06810001673d100e5812a0f26ef6	MIXED	PyMuPDF	1.28.2	\N	2026-11-03 05:21:28.533172+00	SYSTEM	2026-11-03 05:21:28.533172+00	SYSTEM
20261103_000020	2	Visa Infinite 선택서비스중특급호텔발렛파킹, 인천공항발렛파킹서비스를하나카드에서제공합니다.\n* Visa 프리미엄서비스에대한구체적내용, 적용기준및유의사항\n등은Visa 홈페이지(www.visakorea.com) 또는하나카드홈페이지\n에서확인해주시기바랍니다.\n* 본Visa 프리미엄서비스안내서는회원이발급받은카드상품안\n내장, 이용약관과함께교부되오니, 카드이용과관련한유의사항\n을반드시확인하시기바랍니다.\n* 본Visa 프리미엄서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n아래의대상카드발급시Visa Infinite\n선택서비스가제공됩니다.\nJADE First                            JADE First Centum \n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용평점이\n하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가발생할수\n있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등적용되며, \n법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) 유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부계약기간의\n유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융가계자금\n대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관가중평균대출금리\n(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도등에\n영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금결제일에\n상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를참고하시거나\n고객센터로문의바랍니다.\n여신금융협회심의필제2026-C1a-05532호( 2026.04.17 ) / 준법심의L-26-0469 (2026.03.17)\nVisa infinite 선택서비스\n특급호텔발렛파킹무료이용\n- 국내특급호텔에서발렛파킹을무료이용하실수있습니다. (월8회/연60회)\n서비스제공한도\n- 호텔통합월8회/연60회한도내에서이용가능\n- 본인카드와가족카드의한도는개별제공\n1.월한도기준: 매월1일부터말일까지\n2.연한도기준: 매년1월1일부터12월31일까지\n- 서비스제공한도를초과할경우발렛파킹비용은본인부담\n이용방법\n- 호텔현관또는발렛파킹부스에발렛파킹요청후주차권수령\n- 차량인수시주차권과대상카드제시\n- 호텔단말기를통해서비스이용가능여부확인후서비스제공\n대상호텔\n서울\n그랜드워커힐서울\n그랜드하얏트서울\n글래드강남코엑스센터\n노보텔앰배서더서울강남\n노보텔앰배서더서울동대문\n더플라자\n레스케이프호텔\n르메르디앙& 목시서울명동\n파크하얏트서울\n포시즌스호텔서울\n호텔나루서울엠갤러리\n메리어트이그제큐티브아파트먼트서울\n메이필드호텔\n몬드리안서울이태원\n반얀트리클럽앤스파서울\n비스타워커힐서울\n서울신라호텔\n소피텔앰배서더서울&서비스드레지던스\n스위스그랜드호텔\n안다즈서울강남\n앰배서더서울풀만호텔\n오크우드프리미어코엑스센터\n그랜드머큐어임피리얼팰리스서울\n코트야드바이메리어트서울타임스퀘어\n콘래드서울\n서울가든호텔\n서울드래곤시티\nAC 호텔바이메리어트서울강남\nJW 메리어트동대문스퀘어서울\nJW 메리어트호텔서울\n호텔코리아나\n서울외\n그랜드조선부산\n웨스틴조선부산\n파크하얏트부산\n그랜드머큐어앰배서더창원\n그랜드하얏트인천\n대구메리어트호텔\n세인트존스호텔\n소노캄고양\n소노캄여수\n인스파이어엔터테인먼트리조트\n호텔오노마대전오토그래프컬렉션\n호텔인터불고대구\n유의사항\n- 주차요금은본인부담이며, 일부호텔에한해1일3시간까지무료주차가제공되므로\n발렛파킹이용전반드시방문하실호텔에서비스가능여부를확인하시기바랍니다.\n- 본서비스는국내에서발급된비자프리미엄카드회원이해당호텔의객실및식음료\n업장(연회장제외) 이용을위해내방한회원본인에한해제공합니다.\n- 본서비스이용시호텔정책에따라해당호텔은회원에게해당호텔을이용한영수증\n을요청할수있으며, 영수증미지참시에는별도의발렛파킹비용과주차금액이청구될\n수있습니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시기\n바랍니다.\n공항발렛파킹무료이용\n- 국내공항에서발렛파킹을무료이용하실수있습니다. (월8회/연60회)\n서비스제공한도\n- 공항통합월8회/연60회한도내에서이용가능합니다.\n- 본인카드와가족카드의한도는개별제공합니다.\n1) 월한도기준: 매월1일부터말일까지\n2) 연한도기준: 매년1월1일부터12월31일까지\n- 서비스제공횟수를초과할경우발렛파킹비용은본인부담입니다.\n대상공항별이용방법\n주차시: 1. 인천공항제1여객터미널발렛전용차로및안내표지판을따라\n지하1층단기주차장A구역으로이동\n2. Maxerve 유니폼착용공식대행직원에게발렛요청후모바일\n차량접수증수령(카카오톡접수증발송)\n출차시: 1. 주차대행접수증에안내된출차장소로이동(지하3층A32 또는H38)\n2. 유인정산소모바일접수증제시“제휴카드승인“ 후차량인수\n3. 주차장출차시, 추자요금별도정산\n- 인천공항제1터미널\n- 인천공항제2터미널\nVisa\nInfinite\n선택서비스\n힐튼경주\nJW 메리어트제주리조트&스파\n주차시: 1. 국내선청사2층우측하늘색라인따라진입후, 오렌지색유니폼\n착용공식주차대행직원에게발렛파킹요청\n2. 차량상태점검후차량인도및차량보관증수령\n출차시: 1. 출발지항공기탑승전차량보관증에기재된연락처로출차요청\n2. 차량인수시, 접수증과프리미엄마스터카드제시후서비스\n이용가능여부확인\n3. 차량인수후출차시고객이주차요금별도정산\n- 김포공항국내선(이용가능시간05:00~21:00 / 출차는24시간가능)\n주차시: 1. 출국일정24시간전사전예약처로유선예약시이용가능하며, \n예약시비자프리미엄카드회원임을반드시전달하고김해공항\n발렛파킹지정장소안내받음(국내선/국제선출발층) \n2. 안내받은장소에도착후차량인도및차량보관증수령\n출차시: 1. 도착후차량보관증에명시되어있는지정주차장연락처로연락\n2. 도착층지정장소에서무료셔틀이용해지정주차장이동\n3. 비자프리미엄카드로서비스이용가능여부확인후\n발렛파킹서비스무료제공(주차비정산후차량인수)\n- 김해공항(1일무료주차서비스함께제공)\n지난달실적조건: 지난달(1일~말일) 국내외일시불/할부50만원이상이용시서비스제공\n(최초카드사용등록후다음달말일까지는지난달카드이용금액50만원미만시에도서비스제공)\n실적제외대상: 국세, 지방세, 수도/전기요금, 그외공과금(우편요금, 여권발급비용, 과태료, 범칙\n금, 벌금, 국가/공공기관/공공단체가부과하는부담금), 도시가스요금, 아파트관리비, 국민연금/고용\n보험료/산재보험료/건강보험료납부금액, 스쿨뱅킹, 초·중·고학교납입금, 대학등록금, 대학원등록금, \n상품권및기프트카드구매, 선불카드및선불전자지급수단(하나머니등) 충전금액, 부동산임대료\n사전예약처\n주차시: 1. 제2여객터미널발렛전용차로및안내표지판을따라\n지하1층서편단기주차장으로이동\n2. 파란색유니폼착용한공식대행직원에게발렛요청후\n모바일접수증수령(카카오톡/문자수신)\n출차시: 1. 접수증에표시된연락처를통해접수번호및차량번호확인후출차진행\n2. 접수증(또는차량보관증)에명기된구역(동편단기주차장지하1층)\n고객대기실에서비자프리미엄카드와접수증제시\n3. 서비스이용가능여부확인후발렛파킹서비스무료제공\n(출차시주차요금별도정산)\n유의사항\n- 주차요금은본인부담이며, 지정된장소외에는5분이상정차시과태료가부과될\n수있습니다.\n- 본서비스는국내에서발급된비자프리미엄카드회원이해당공항발렛파킹서비스\n를사전예약하고내방한회원본인에한해제공하며, 현장상황에따라당일서비스\n요청고객도접수가가능합니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시기\n바랍니다\n인천공항1터미널\nhttps://Maxerve-mparking.com/valet\n인천공항2터미널\nhttps://valet.amanopark.co.kr\n김해공항\n전화예약051-903-7000\n김포공항\n(사전예약없이이용가능)\n	3881	0d3c2ede467b514f0caa69987099c4a17141f3a8078845579cd49398c2f4ff31	MIXED	PyMuPDF	1.28.2	\N	2026-11-03 05:21:28.533172+00	SYSTEM	2026-11-03 05:21:28.533172+00	SYSTEM
20261103_000021	1	VISA \nPlatinum 01 Service\nVISA Platinum 공통서비스\nTravel : 여행서비스\n[비자 Hotels.com 할인 서비스]\n· 전세계 수십만개 호텔과 2천 9백만개 실제 숙박리뷰를 보유하고 있는 \n Hotels.com 비자 프로모션 사이트에서 비자카드로 결제 시 최대 8% 할인 제공\n (프로모션코드: VISA8)\n[Booking.com 캐시백 서비스]\n· Booking.com/Visakr에서 캐시백 뱃지가 있는 숙소를 VISA카드로 예약 시 \n 10% 캐시백 제공 (App을 통한 예약 제외)\n[해외 렌터카 서비스]\n- Hertz와 AVIS에서 렌탈 시 다양한 혜택 제공   \n· Hertz 렌터카 : 기본 10% 할인과 추가 혜택 제공 (이용기간 : 23.1.1~23.9.30)    \n    (지역 별 프로모션 코드 VISA 홈페이지 참조)   \n· AVIS 렌터카: 최대 20% 할인 \n[비자 Rentalcars.com 서비스]\n· 온라인 렌터카 예약 사이트 Rentalcars.com의 비자 프로모션 사이트에서\n 결제 시 추가 10% 할인 서비스 제공\n[아시아 태평양 지역 공항 픽업 서비스]\n· TBR Global 프로모션 사이트를 통해 아시아 태평양 지역 공항 및 도시에서 \n 공항 또는 숙소까지 픽업 서비스 예약 및 할인 제공\n[굿럭(goodlugg) 해외여행 캐리어 배송/보관 할인 서비스]\n· 굿럭 앱을 통해 예약 및 결제 시 당일 짐 배송 및 글로벌 실시간 안심 \n 짐 보관 서비스 10% 할인\n[굿럭(goodlugg) 인천공항 입국시 짐찾기 대행 및 배송 서비스]\n· 인천공항으로 입국하는 교통약자 짐을 대신 찾아 도착지 숙소로 배송해주는 \n 서비스 최대 50% 할인\n[movv 이동 서비스 할인 혜택]\n· movv에서 국내/외 공항 또는 국내 골프장 이동 시 할인 혜택 제공 \n선택서비스를 제외한 아래의 VISA Platinum 서비스는 VISA Platinum 등급 카드 소지자에게 공통으로 제공됩니다. \n서비스 상세 이용조건 및 방법을 VISA 홈페이지 (http://www.visakorea.com)에서 반드시 확인하시기 바랍니다.\nLifestyle : 생활서비스\n[하와이 올로마나 골프장 할인 및 특별 혜택]\n· 그린피 15% 할인 및 연습볼 1 bucket 제공\n[온라인 교육 플랫폼 할인 혜택]\n· 세계 유수의 온라인 교육 플랫폼 10~ 40% 할인\n (이용기간 : 23.1.1~23.9.30)\nConcierge : 컨시어지서비스\n[비자 프리미엄 컨시어지]\n· 비자 프리미엄 카드 회원을 위한 컨시어지 서비스 제공\n * 플래티늄 컨시어지 82-2-6240-3678\n * 운영시간: 연중무휴 24시간 운영\nHotel : 호텔서비스\n[국내 특급호텔 F&B 할인 서비스]\n· 비자 프리미엄 카드 회원에게 53개 국내 특급 호텔 F&B 매장에서 \n 5%~15% 특별 할인 혜택 제공 \n[국내 특급호텔 객실 및 패키지 할인 서비스]\n· 비자 프리미엄 카드 회원에게 61개 국내 특급 호텔의 객실 및 패키지 특별 할인 제공\nAirport : 공항서비스\n[공항 의전 서비스(yQ Meet & Assist)]\n· 전 세계 약 450여 개 공항에서 제공되는 빠른 입국/출국 서비스를 \n 비자 프리미엄 카드로 결제 시 정상가 대비 15% 할인 서비스 제공\nShopping : 쇼핑서비스\n[면세점 할인 서비스]\n· 신세계면세점 VIP 골드 멤버십 혜택 제공 \n (최대 15% 할인, 오프라인 전 매장에서 제공)\n· 현대백화점 면세점 골드 멤버십 혜택 제공 (최대 15% 할인) \n[캐치패션 추가 캐쉬백 혜택]\n· 비자가 매월 선정하는 캐치패션 파트너사에서 구매 시 최대 3% 캐시백\n	1806	a7b26a1e68b32558121c08bfdb972e6efc84cd4c80e062baf486c8e440b11c8b	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:21:32.951882+00	SYSTEM	2026-11-03 05:21:32.951882+00	SYSTEM
20261103_000021	2	VISA Platinum 선택서비스 – VISA Platinum 01 유형\nVISA Platinum 선택서비스 중 특급호텔 발렛파킹, 인천공항 발렛파킹 서비스를 하나카드에서 제공합니다. \n그외 서비스 상세 이용조건 및 방법은 VISA 홈페이지(http://www.visakorea.com) 또는 하나카드 홈페이지(http://www.hanacard.co.kr)를 반드시 참고하시기 바랍니다.\n특급호텔 발렛파킹 서비스\n서비스혜택\n이용조건\n이용방법\n국내 주요 특급호텔 무료 발렛파킹 서비스 제공 \n- 호텔 통합 월 3회 서비스 제공\n- CLUB SK 카드, CLUB SK카드 hiplus 선불하이패스,\n\t 토스(Toss) 하나카드 Ver 2.0 은 \n\t 지난달(1일~말일) 국내외 일시불/할부 30만원 이상 이용 시 \n\t 서비스 제공 (최초 카드 사용등록 후 다음달 말일까지는 \n\t 지난달 카드 이용금액 30만원 미만 시에도 서비스 제공)\n- 주차 시 호텔 현관에서 도어맨에게 발렛파킹 요청 후 주차권 수령\n- 차량 인수 시 도어맨에게 주차권과 비자 프리미엄 카드 제시\n- 호텔 단말기를 통해 서비스 이용가능 여부 확인 후 서비스 제공\n유의사항\n- 상기 서비스는 해당 호텔의 객실 및 식음료업장(연회장 제외) 이용을 위해\n 내방한 회원 본인에 한해 제공함을 원칙으로 합니다.\n- 상기 서비스 이용 시 호텔 정책에 따라 해당 호텔을 이용한 영수증 제시를 요청할 수 있으며,\n 영수증 미지참시에는 별도의 발렛파킹 비용과 주차금액이 청구될 수 있습니다.\n- 연회 참석 및 국가 주요행사 시에는 상기 서비스를 이용하실 수 없으며,\n 이용고객의 집중으로 주차공간이 부족할 경우 서비스가 제한될 수 있습니다.\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 상기 서비스 이용 시 발렛파킹 비용 및 1일 3시간 이내의 주차비가 무료로 제공됩니다.\n 이용시간 초과 시 주차금액이 별도로 부과될 수 있으며, 이는 별도로 부담하셔야 합니다.\n- 일부 호텔은 반드시 당일 일정 금액의 영수증 지참 시에만 서비스가 제공되며 \n 서비스 상세 이용요건에 대해서는 VISA 홈페이지(http://www.visakorea.com) 또는 \n 하나카드 홈페이지(http://www.hanacard.co.kr)를 반드시 참고하시기 바랍니다.\n* VISA 프리미엄 서비스의 상세한 내용은 VISA 홈페이지(http://www.visakorea.com)를 통해 \n  확인하시기 바랍니다.\n* 본 VISA 프리미엄 서비스 안내서는 회원이 발급받은 카드 상품안내장, 이용약관과 함께 교부되오니, \n  카드 이용과 관련한 유의사항을 반드시 확인하시기 바랍니다.\n* 본 VISA 프리미엄 서비스는 2023년 1월 1일 ~ 12월 31일까지 제공됩니다.\n* 필요 이상의 신용카드 발급 및 사용은 개인신용평점이나 이용한도 등에 영향을 미칠 수 있습니다.\n* 카드 발급 신청 시 상품설명서 및 상품 약관을 반드시 확인하시기 바랍니다.\n* 신용카드 발급이 부적정한 경우(개인신용평점 낮음 등) 카드발급이 제한될 수 있습니다.\n* 카드이용대금과 이에 수반되는 모든 수수료를 지정된 대금 결제일에 상환하여야 합니다.\n* 금융소비자는 해당 상품 또는 서비스에 대하여 설명을 받을 권리가 있습니다.\n* 본 상품설명서는 법령 및 내부통제기준에 따른 절차를 거쳐 제공됩니다.\n* 자세한 내용은 하나카드 홈페이지 (www.hanacard.co.kr) 를 참고하시거나 고객센터로 문의 바랍니다.\n•상환능력에 비해 신용카드 사용액이 과도할 경우, 귀하의 개인신용평점이 \n   하락할 수 있습니다.\n•개인신용평점 하락 시 금융거래와 관련된 불이익이 발생할 수 있습니다.\n•일정기간 원리금을 연체할 경우, 모든 원리금을 변제할 의무가 발생할 수 있습니다.\n•연체이자율(약정이율+최대3%)은 회원별·이용상품별로 차등 적용되며, \n\t 법정 최고금리(20%)를 초과하지 않습니다.\n\t ※ 단, 연체 발생 시점에 약정이율이 없는 경우는 아래와 같이 적용함\n\t - 일시불 거래 연체 시 : 거래발생 시점의 최소기간(2개월) 유이자 할부금리\n\t - 무이자 할부 거래 연체 시 : 거래발생 시점의 동일한 할부 계약기간의 유이자 할부금리\n\t - 그 외의 경우 : 약정이율은 상법상 상사법정이율과 상호금융 가계자금대출금리* 중 높은 금리 적용\n여신금융협회 심의필 제 2023-C1a-08448호(2023.07.27) / 준법심의 L-23-0125 / VI 230731-33\n아래의 대상 카드 발급 시 국제 브랜드사 서비스로\nVISA Platinum 선택서비스(01 유형)과 VISA Platinum 공통서비스가 제공됩니다.\nVISA Platinum 01 Service\n대상카드\n플래티늄 Royal카드\nCLUB SK 카드\nCLUB SK카드 hiplus 선불하이패스\nPlatinum카드\nCLUB PRIMUS 카드\nSK Broadband Smart BIZ카드\nSK 패밀리 카드\n토스(Toss) 하나카드 Ver 2.0\nVISA Platinum 01\n상품유형\n인천공항 발렛파킹 서비스\n서비스혜택\n이용조건\n제1여객터미널\n이용방법\n제2여객터미널\n이용방법\n인천공항 무료 발렛파킹 서비스 제공(제1여객터미널, 제2여객터미널)\n- 통합 월 3회 서비스 제공\n- CLUB SK 카드, CLUB SK카드 hiplus 선불하이패스,\n\t 토스(Toss) 하나카드 Ver 2.0 은 \n\t 지난달(1일~말일) 국내외 일시불/할부 30만원 이상 이용 시 \n\t 서비스 제공 (최초 카드 사용등록 후 다음달 말일까지는 \n\t 지난달 카드 이용금액 30만원 미만 시에도 서비스 제공)\n주차 시 :  1. 인천공항 제1여객터미널 발렛 전용차로 및 \n  \n 발렛 안내 표지판을 따라 지하 1층 \n  \n 단기주차장 A구역으로 이동\n   \n2. 오렌지색 유니폼 착용 공식 대행 직원에게 발렛 요청 후 \n  \n 접수증 수령 (SMS 발송)\n출차 시 :  1. 접수증에 표시된 장소로 이동 후 차량 인수 시 \n  \n 접수증과 비자 프리미엄 카드 제시\n  \n2. 차량 인수 후 출차 시 주차요금 별도 정산\n주차 시 :   1. 인천공항 제2여객터미널 발렛 전용차로 및 \n  \n 발렛안내 표지판을 따라 단기주차장 지하 1층 \n  \n 서편 주차구역 110~112번으로 이동\n  \n2. 오렌지색 유니폼 착용 공식 대행 직원에게 \n  \n 발렛 요청 후 접수증 수령 (알림톡, SMS 발송)\n출차 시 :  1. 접수증에 표시된 동편 단기주차장 지하 1층 \n  \n 210번 고객 대기실로 이동\n유의사항\n- 서비스 제공 횟수를 초과하였을 경우 발렛파킹 비용을 별도로 부담하셔야 합니다.\n- 상기 서비스는 발렛파킹 비용에만 적용되므로, 주차비용은 별도로 정산하셔야 합니다.\n- 3층 여객터미널 승용차 전용 도로에서 5분 이상 정차 시 과태료가 부과될 수 있습니다.\n- 국가 주요행사 등 공항에서 정하는 규정에 따라 서비스가 제한될 수 있습니다.\n- 공항 이용객이 많은 성수기, 명절 기간 또는 공항 주차장 만차 시 서비스 이용이 \n   제한될 수 있습니다. \n노보텔 앰버서더 서울 동대문\n그랜드 워커힐 서울\n그랜드 하얏트 서울\t\n그랜드 하얏트 인천 \n그랜드 머큐어 앰배서더 창원\t\n호텔 농심\n노보텔 앰배서더 서울 강남\n서울 드래곤 시티\n페어몬트 앰배서더 서울\n파크 하얏트 부산\n호텔 인터불고 대구\n서울\n지방\n지역\n대상 호텔\n르 메르디앙 & 목시 서울 명동\n비스타 워커힐 서울\n앰배서더 서울 풀만 호텔\n	3630	627f0e36fc127d933421bb3f367de9c8d6e1e0a211c1cc2eb6456bafdbe30570	TEXT	PyMuPDF	1.28.2	\N	2026-11-03 05:21:32.951882+00	SYSTEM	2026-11-03 05:21:32.951882+00	SYSTEM
20261103_000022	1	서비스\n· 카타르항공최대15% 할인\n(예약기간: ~26.10.31 / 여행기간: ~27.3.31)\n· 일본항공일본행항공권5% 할인(25.10.1~26.3.31)\n· 공항의전서비스(yQ Meet & Assist) 15% 할인\n내용\n· Hotels.com 쿠폰코드입력시최대8% 할인(숙박기간: ~27.6.30)\n· Booking.com 최대7% 월렛포인트캐시백(매월1일~15일한정)\n· Expedia 8% 할인(숙박기간: ~27.6.30)\n· IHG Hotel&Resorts 20% 할인(숙박기간: ~27.1.3)\n· Accor China 중화권호텔최소2박예약시20% 할인(~26.9.30)\n. 반얀트리최소2박숙박시20%할인\n(예약기간: ~26.5.31 / 숙박기간: ~26.8.31)\n· 국내특급호텔(약52여개) F&B 5~20% 할인\n· 국내특급호텔(약59여개) 객실/패키지5~60% 할인\n· 국내부티크호텔(약23여개) 객실/F&B 5~50% 할인\n· 국내특급호텔(약5여개) 로비라운지5~20% 할인\n· Hertz 해외렌터카기본10% 할인및추가혜택(~26.3.31)\n· AVIS 해외렌터카최대20% 할인\n· Rentalcars.com 10% 추가할인(~26.4.30)\n· Movv 이동서비스국내1.5~3.5만원, 해외8% 할인혜택\n· 아시아태평양공항픽업서비스\nTBR Luxury Airport Transfer 10% 할인\n· 굿럭해외공항짐배송및보관10% 할인\n· 굿럭인천공항입국시교통약자짐찾기대행및배송서비스할인\n· Trip.com 최대6%할인\nHotel\nA i r\n&\nAirport\nTravel\n· 비자엘리트다이닝최대20% 할인혜택제공(~26.8.31)\n· 트립쿠폰멤버십무료제공\n· 하와이올로마나골프장그린피15% 할인및연습볼1버켓무료\n· Visa 컨시어지제공\n전화080-4880-880, 홈페이지www.concierge-asia.visa.com\n카카오톡“Visa 컨시어지” 채널추가\nDining &\nLifestyle\nShopping\n· 현대백화점면세점골드멤버십제공(최대15% 할인)\n· Mitsui Outlet Park에서최대10%할인(~27.11.30)\nVisa\nPlatinum\n공통서비스\n* 아래의Visa Platinum서비스는Visa Platinum 등급카드\n소지자에게공통으로제공됩니다.\n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용\n평점이하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이\n발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가\n발생할수있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등\n적용되며, 법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) \n유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부\n계약기간의유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융\n가계자금대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관\n가중평균대출금리(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도\n등에영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기\n바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금\n결제일에상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가\n있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐\n제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를\n참고하시거나고객센터로문의바랍니다.\n여신금융협회심의필제2026-C1a-05257호( 2026.04.14 ))/ 준법심의L-26-0468 (2026.03.16)\n* 본Visa Platinum 서비스안내서는회원이발급받은카드\n상품안내장, 이용약관과함께교부되오니, 카드이용과관련한\n유의사항을반드시확인하시기바랍니다.\n* 본서비스는Visa에서제공하는서비스로, 프리미엄서비스에\n대한구체적내용, 적용기준및유의사항등\nhttp://www.visakorea.com → ‘Visa 플래티늄’에서사전에\n반드시확인해주시기바랍니다.\n* 본Visa Platinum 서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n	2109	965b9ef1901004bcce12425d26f0226cb8fec0e6f75a6d651b17a3ef9139761d	MIXED	PyMuPDF	1.28.2	\N	2026-11-03 05:21:37.985564+00	SYSTEM	2026-11-03 05:21:37.985564+00	SYSTEM
20261103_000022	2	Visa Platinum 선택서비스중특급호텔발렛파킹, 인천공항발렛파킹서비스를하나카드에서제공합니다.\nVisa Platinum 01 선택서비스\n특급호텔발렛파킹서비스\n서비스혜택\n- 국내주요특급호텔무료발렛파킹서비스제공\n이용조건\n- 호텔통합월3회서비스제공\n- CLUB SK 카드, CLUB SK카드hiplus 선불하이패스,\n토스(Toss) 하나카드Ver.2.0 은\n지난달(1일~말일) 국내외일시불/할부30만원이상이용시서비스제공\n(최초카드사용등록후다음달말일까지는지난달카드이용금액30만원미만시에도\n서비스제공)\n이용방법\n- 주차시호텔현관에서도어맨에게발렛파킹요청후주차권수령\n- 차량인수시도어맨에게주차권과비자프리미엄카드제시\n- 호텔단말기를통해서비스이용가능여부확인후서비스제공\n대상호텔\n서울\n그랜드워커힐서울\n그랜드하얏트서울\n노보텔앰배서더서울강남\n노보텔앰배서더서울동대문\n비스타워커힐서울\n그랜드머큐어임피리얼팰리스서울\n앰배서더서울풀만호텔\n르메르디앙&목시서울명동\n서울드래곤시티\n서울외\n그랜드하얏트인천\n파크하얏트부산\n그랜드머큐어앰배서더창원\n호텔인터불고대구\n유의사항\n- 상기서비스는국내에서발급된비자프리미엄카드회원으로해당호텔의객실\n및식음료업장(연회장제외) 이용을위해내방한회원본인에한해\n제공함을원칙으로합니다.\n- 상기서비스는이용시호텔정책에따라해당호텔을이용한영수증제시를요청\n할수있으며, 영수증미지참시에는별도의발렛파킹비용과주차금액이청구될\n수있습니다.\n- 서비스제공횟수를초과하였을경우발렛파킹비용을별도로부담하셔야합니다.\n- 상기서비스이용시발렛파킹비용및1일3시간이내의주차비가무료로제공\n됩니다. 이용시간초과시주차금액이별도로부과될수있으며, 이는별도로\n부담하셔야합니다.\n- 일부호텔은반드시당일일정금액의영수증지참시에만서비스가제공됩니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시\n기바랍니다.\n인천공항발렛파킹서비스\n서비스혜택\n- 인천공항무료발렛파킹서비스제공(제1여객터미널, 제2여객터미널)\n이용조건\n- 공항통합월3회서비스제공\n- CLUB SK 카드, CLUB SK카드hiplus 선불하이패스,\n토스(Toss) 하나카드Ver.2.0 은\n지난달(1일~말일) 국내외일시불/할부30만원이상이용시서비스제공\n(최초카드사용등록후다음달말일까지는지난달카드이용금액30만원미만시에도\n서비스제공)\n이용방법\n- 제1여객터미널\n- 제2여객터미널\nVisa\nPlatinum 01\n선택서비스\n그랜드조선부산\n이용방법\n· 비자프리미엄카드회원을위한컨시어지서비스제공\n* 플래티늄컨시어지82-2-6240-3678\n* 운영시간: 연중무휴24시간운영\nConcierge : 컨시어지서비스\n주차시: 1. 인천공항제1여객터미널발렛전용차로및안내표지판을따라\n지하1층단기주차장A구역으로이동\n2. Maxerve 유니폼착용공식대행직원에게발렛요청후모바일\n차량접수증수령(카카오톡접수증발송)\n출차시: 1. 주차대행접수증에안내된출차장소로이동(지하3층A32 또는H38)\n2. 유인정산소모바일접수증제시“제휴카드승인“ 후차량인수\n3. 주차장출차시, 추자요금별도정산\n주차시: 1. 제2여객터미널발렛전용차로및안내표지판을따라\n지하1층서편단기주차장으로이동\n2. 파란색유니폼착용한공식대행직원에게발렛요청후\n모바일접수증수령(카카오톡/문자수신)\n출차시: 1. 접수증에표시된연락처를통해접수번호및차량번호확인후출차진행\n2. 접수증(또는차량보관증)에명기된구역(동편단기주차장지하1층)\n고객대기실에서비자프리미엄카드와접수증제시\n3. 서비스이용가능여부확인후발렛파킹서비스무료제공\n(출차시주차요금별도정산)\n유의사항\n- 서비스제공횟수초과시발렛파킹비용을별도로부담하셔야합니다.\n- 상기서비스는발렛파킹비용에만적용되므로, 주차비용은별도로정산하셔야\n합니다.\n- 3층여객터미널승용차전용도로에서5분이상정차시과태료가부과될수\n있습니다.\n- 사전예약고객대상으로서비스제공되며, 현장상황에따라당일서비스요청\n고객도접수가가능합니다.\n- 원활한서비스이용을위해서비스이용전제휴처에이용가능여부를확인하시기\n바랍니다.\n* Visa 프리미엄서비스에대한구체적내용, 적용기준및유의사항\n등은Visa 홈페이지(www.visakorea.com) 또는하나카드홈페이지\n에서확인해주시기바랍니다.\n* 본Visa 프리미엄서비스안내서는회원이발급받은카드상품안\n내장, 이용약관과함께교부되오니, 카드이용과관련한유의사항\n을반드시확인하시기바랍니다.\n* 본Visa 프리미엄서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.\n* 상환능력에비해신용카드사용액이과도할경우, 귀하의개인신용평점이\n하락할수있습니다.\n* 개인신용평점하락시금융거래와관련된불이익이발생할수있습니다.\n* 일정기간원리금을연체할경우, 모든원리금을변제할의무가발생할수\n있습니다.  \n* 연체이자율(약정이율+최대3%)은회원별·이용상품별로차등적용되며, \n법정최고금리(20%)를초과하지않습니다.\n※ 단, 연체발생시점에약정이율이없는경우아래와같이적용함\n- 일시불거래연체시: 거래발생시점의최소기간(2개월) 유이자할부금리\n- 무이자할부거래연체시: 거래발생시점의동일한할부계약기간의\n유이자할부금리\n- 그외의경우: 약정이율은상법상상사법정이율과상호금융가계자금\n대출금리* 중높은금리적용\n* 한국은행에서매월발표하는가장최근의비은행금융기관가중평균대출금리\n(신규대출기준)\n* 필요이상의신용카드발급및사용은개인신용평점이나이용한도등에\n영향을미칠수있습니다.\n* 카드발급신청시상품설명서및상품약관을반드시확인하시기바랍니다.\n* 신용카드발급이부적정한경우(개인신용평점낮음등) 카드발급이\n제한될수있습니다.\n* 카드이용대금과이에수반되는모든수수료를지정된대금결제일에\n상환하여야합니다.\n* 금융소비자는해당상품또는서비스에대하여설명을받을권리가있습니다.\n* 본상품설명서는법령및내부통제기준에따른절차를거쳐제공됩니다.\n* 자세한내용은하나카드홈페이지(www.hanacard.co.kr)를참고하시거나\n고객센터로문의바랍니다.\n아래의대상카드발급시Visa Platinum01\n선택서비스가제공됩니다.\n여신금융협회심의필제2026-C1a-05552호( 2026.04.17 ) /준법심의L-26-0472 (2026.03.17)\n플래티늄Royal카드\nCLUB SK 카드\nCLUB SK카드hiplus 선불하이패스\nPlatinum카드\nCLUB PRIMUS 카드\nSK Broadband Smart BIZ카드\nSK 패밀리카드\n토스(Toss) 하나카드Ver.2.0\n사전예약처\n인천공항1터미널\nhttps://Maxerve-mparking.com/valet\n인천공항2터미널\nhttps://valet.amanopark.co.kr\n	3084	693b80c97d975853c0d5578adfd9ef1433e61065f4e9b9a34fe7408d9af8c0da	MIXED	PyMuPDF	1.28.2	\N	2026-11-03 05:21:37.985564+00	SYSTEM	2026-11-03 05:21:37.985564+00	SYSTEM
\.


--
-- TOC entry 4392 (class 0 OID 21778)
-- Dependencies: 386
-- Data for Name: card_evidence_link; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_evidence_link (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id, card_bnft_id, ev_subject_cd, rule_key, relation_key, ev_item_cd, ev_item_key) FROM stdin;
20261101_000002	1	20261101_000012	20261101_000031	2	20261101_000001	20261101_000001	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000032	2	20261101_000002	20261101_000001	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000033	2	20261101_000003	20261101_000001	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000034	2	20261101_000004	20261101_000001	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000035	2	20261101_000005	20261101_000001	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000036	2	20261101_000006	20261101_000001	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000037	2	20261101_000007	20261101_000001	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000038	2	20261101_000008	20261101_000002	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000039	2	20261101_000009	20261101_000002	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000040	2	20261101_000010	20261101_000002	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000041	2	20261101_000011	20261101_000002	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000042	2	20261101_000012	20261101_000002	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000043	2	20261101_000013	20261101_000002	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000044	2	20261101_000014	20261101_000003	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000045	2	20261101_000015	20261101_000003	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000046	2	20261101_000016	20261101_000003	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000047	2	20261101_000017	20261101_000003	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000048	2	20261101_000018	20261101_000003	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000049	2	20261101_000019	20261101_000003	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000050	2	20261101_000020	20261101_000003	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000051	2	20261101_000021	20261101_000004	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000052	2	20261101_000022	20261101_000004	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000053	2	20261101_000023	20261101_000004	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000054	2	20261101_000024	20261101_000004	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000055	2	20261101_000025	20261101_000004	BNFT	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000058	2	20261101_000028	20261101_000003	BNFT	\N	\N	COND	spend_exclusions
20261101_000002	1	20261101_000012	20261101_000058	2	20261101_000029	20261101_000004	BNFT	\N	\N	COND	spend_exclusions
20261101_000002	1	20261101_000012	20261101_000044	2	20261101_000042	20261101_000003	BNFT	\N	\N	COND	transit_spend
20261101_000002	1	20261101_000012	20261101_000048	2	20261101_000043	20261101_000003	BNFT	\N	\N	COND	transit_spend
20261101_000002	1	20261101_000012	20261101_000034	2	20261101_000044	20261101_000001	RULE	one_pick_100	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000034	2	20261101_000045	20261101_000001	RULE	one_pick_100	\N	COND	MIN_one_pick_100
20261101_000002	1	20261101_000012	20261101_000035	2	20261101_000046	20261101_000001	RULE	one_pick_500	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000035	2	20261101_000047	20261101_000001	RULE	one_pick_500	\N	COND	MIN_one_pick_500
20261101_000002	1	20261101_000012	20261101_000040	2	20261101_000048	20261101_000002	RULE	style_100	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000040	2	20261101_000049	20261101_000002	RULE	style_100	\N	COND	MIN_style_100
20261101_000002	1	20261101_000012	20261101_000041	2	20261101_000050	20261101_000002	RULE	style_500	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000041	2	20261101_000051	20261101_000002	RULE	style_500	\N	COND	MIN_style_500
20261101_000002	1	20261101_000012	20261101_000045	2	20261101_000052	20261101_000003	RULE	transit_rate	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000050	2	20261101_000053	20261101_000003	RULE	transit_rate	\N	COND	transit_exclusions
20261101_000002	1	20261101_000012	20261101_000052	2	20261101_000054	20261101_000004	RULE	amusement_rate	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000049	2	20261101_000055	20261101_000003	BNFT	\N	\N	COND	transit_grace
20261101_000002	1	20261101_000012	20261101_000054	2	20261101_000056	20261101_000004	BNFT	\N	\N	COND	amusement_spend
20261101_000002	1	20261101_000012	20261101_000048	2	20261101_000057	20261101_000004	BNFT	\N	\N	COND	amusement_spend
20261101_000002	1	20261101_000012	20261101_000055	2	20261101_000058	20261101_000004	BNFT	\N	\N	COND	amusement_first_month
20261101_000002	1	20261101_000012	20261101_000052	2	20261101_000059	20261101_000004	BNFT	\N	\N	COND	amusement_per_person
20261101_000002	1	20261101_000012	20261101_000056	2	20261101_000026	\N	CARD	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000057	2	20261101_000027	\N	CARD	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000059	2	20261101_000030	\N	CARD	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000060	2	20261101_000031	\N	CARD	\N	\N	SELF	-
20261101_000002	2	20261101_000013	20261101_000061	2	20261101_000041	\N	CARD	\N	\N	SELF	-
20261101_000002	1	20261101_000012	20261101_000056	2	20261101_000060	\N	CARD	\N	\N	COND	common_service_exclusion
20261101_000002	1	20261101_000012	20261101_000057	2	20261101_000061	\N	CARD	\N	\N	COND	common_channel
20261101_000002	1	20261101_000012	20261101_000059	2	20261101_000062	\N	CARD	\N	\N	COND	merchant_classification
20261102_000003	5	20261102_000018	20261102_000062	5	20261102_000089	\N	CARD	\N	\N	SELF	-
20261102_000004	1	20261102_000020	20261102_000063	5	20261102_000090	20261102_000008	BNFT	\N	\N	SELF	-
20261102_000004	1	20261102_000020	20261102_000064	5	20261102_000091	20261102_000008	BNFT	\N	\N	SELF	-
20261102_000004	1	20261102_000020	20261102_000065	5	20261102_000092	20261102_000008	BNFT	\N	\N	SELF	-
\.


--
-- TOC entry 4384 (class 0 OID 20873)
-- Dependencies: 367
-- Data for Name: card_excl_item; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_excl_item (card_excl_item_id, issuer, excl_item_nm, excl_concept_cd, excl_item_desc, excl_alias_nms, create_date, create_user_id, update_date, update_user_id) FROM stdin;
\.


--
-- TOC entry 4383 (class 0 OID 20861)
-- Dependencies: 366
-- Data for Name: card_extr_stg; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_extr_stg (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id, stg_item_seq, card_id, stg_kind_cd, stg_parent_card_extr_stg_id, stg_raw_item, stg_normalized_item, stg_evidence_txt, stg_evidence_start_pos, stg_evidence_end_pos, card_excl_item_id, stg_sql_check_cd, stg_ai_vrfy_cd, stg_ai_vrfy_card_ai_run_id, stg_status, stg_review_note, stg_approved_date, stg_approved_user_id, create_date, create_user_id, update_date, update_user_id) FROM stdin;
20261101_000002	20261101_000002	1	20261101_000012	1	20261101_000009	1	2	BENEFIT	\N	{"rules": [{"rule_key": "one_pick_100", "value_num": "100", "conditions": [], "limit_keys": ["one_pick_day", "one_pick_month_count", "one_pick_month_amount"], "min_txn_amt": 3000, "value_raw_txt": "결제 건당\\n3천원 이상 시 \\n100원", "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": "결제 건당\\n3천원 이상 시"}, {"rule_key": "one_pick_500", "value_num": "500", "conditions": [], "limit_keys": ["one_pick_day", "one_pick_month_count", "one_pick_month_amount"], "min_txn_amt": 10000, "value_raw_txt": "결제 건당\\n1만원 이상 시 \\n500원", "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": "결제 건당\\n1만원 이상 시"}], "limits": [{"limit_key": "one_pick_day", "limit_num": 1, "period_cd": "DAY", "cap_unit_cd": "COUNT", "limit_raw_txt": "일 1회\\n/ 월 30회", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE PICK 편의점·카페 캐시백"]}, {"limit_key": "one_pick_month_count", "limit_num": 30, "period_cd": "MONTH", "cap_unit_cd": "COUNT", "limit_raw_txt": "일 1회\\n/ 월 30회", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE PICK 편의점·카페 캐시백"]}, {"limit_key": "one_pick_month_amount", "limit_num": 5000, "period_cd": "MONTH", "cap_unit_cd": "KRW", "limit_raw_txt": "월 5천원", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE PICK 편의점·카페 캐시백"]}], "bnft_nm": "ONE PICK 편의점·카페 캐시백", "targets": [{"target_nm": "CU", "target_type_cd": "MERCHANT"}, {"target_nm": "GS25", "target_type_cd": "MERCHANT"}, {"target_nm": "세븐일레븐", "target_type_cd": "MERCHANT"}, {"target_nm": "메가MGC커피", "target_type_cd": "MERCHANT"}, {"target_nm": "이디야커피", "target_type_cd": "MERCHANT"}, {"target_nm": "컴포즈커피", "target_type_cd": "MERCHANT"}], "evidence": [{"supports": "COND", "quote_txt": "(지난달 실적 조건 없는 서비스)", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "TARGET", "quote_txt": "CU, GS25, \\n세븐일레븐", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "TARGET", "quote_txt": "메가MGC커피, \\n이디야커피, \\n컴포즈커피", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "RULE", "quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "link_basis": "TABLE_IMAGE", "support_key": "one_pick_100"}, {"supports": "RULE", "quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "link_basis": "TABLE_IMAGE", "support_key": "one_pick_500"}, {"supports": "LIMIT", "quote_txt": "일 1회\\n/ 월 30회", "link_basis": "TABLE_IMAGE", "support_key": "one_pick_month_count"}, {"supports": "LIMIT", "quote_txt": "월 5천원", "link_basis": "TABLE_IMAGE", "support_key": "one_pick_month_amount"}], "item_key": "one_pick", "certainty": "HIGH", "relations": [], "conditions": [], "bnft_type_cd": "CASHBACK", "uncertainty_note": "결제금액 1만원 이상에서 두 정액 캐시백 조건의 적용 관계는 원문에 명시되지 않음.", "is_common_candidate": false, "no_condition_stated": false}	{"merge": {"item_key": "BNFT_86FA3F68DB0B", "conflicts": [], "merge_ver": "MERGE_V1", "source_refs": [{"page_no": 1, "stg_item_seq": 1, "card_doc_chunk_id": "20261101_000012"}], "source_pages": [1]}, "checks": {"issues": ["one_pick_day: 근거 없음"], "link_check_cd": "NEEDS_REVIEW", "value_check_cd": "NO_EVIDENCE"}, "bnft_cd": "BNFT_86FA3F68DB0B", "bnft_nm": "ONE PICK 편의점·카페 캐시백", "rule_list": [{"rule_key": "one_pick_100", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_one_pick_100", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 3000, "cond_raw_txt": "결제 건당\\n3천원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "pool_refs": [{"pool_id": "one_pick_day", "pool_role_cd": "CONSUME"}, {"pool_id": "one_pick_month_count", "pool_role_cd": "CONSUME"}, {"pool_id": "one_pick_month_amount", "pool_role_cd": "CONSUME"}], "value_num": 100, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "CU", "target_key": "CU", "target_type_cd": "MERCHANT"}, {"target_nm": "GS25", "target_key": "GS25", "target_type_cd": "MERCHANT"}, {"target_nm": "세븐일레븐", "target_key": "세븐일레븐", "target_type_cd": "MERCHANT"}, {"target_nm": "메가MGC커피", "target_key": "메가MGC커피", "target_type_cd": "MERCHANT"}, {"target_nm": "이디야커피", "target_key": "이디야커피", "target_type_cd": "MERCHANT"}, {"target_nm": "컴포즈커피", "target_key": "컴포즈커피", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}, {"rule_key": "one_pick_500", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_one_pick_500", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 10000, "cond_raw_txt": "결제 건당\\n1만원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "pool_refs": [{"pool_id": "one_pick_day", "pool_role_cd": "CONSUME"}, {"pool_id": "one_pick_month_count", "pool_role_cd": "CONSUME"}, {"pool_id": "one_pick_month_amount", "pool_role_cd": "CONSUME"}], "value_num": 500, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "CU", "target_key": "CU", "target_type_cd": "MERCHANT"}, {"target_nm": "GS25", "target_key": "GS25", "target_type_cd": "MERCHANT"}, {"target_nm": "세븐일레븐", "target_key": "세븐일레븐", "target_type_cd": "MERCHANT"}, {"target_nm": "메가MGC커피", "target_key": "메가MGC커피", "target_type_cd": "MERCHANT"}, {"target_nm": "이디야커피", "target_key": "이디야커피", "target_type_cd": "MERCHANT"}, {"target_nm": "컴포즈커피", "target_key": "컴포즈커피", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}], "limit_list": [{"pool_key": "one_pick_day", "limit_num": 1, "period_cd": "DAY", "cap_unit_cd": "COUNT", "pool_scope_cd": "BENEFIT", "shared_scope_txt": null, "aggregation_key_cd": "CARD_MEMBER"}, {"pool_key": "one_pick_month_count", "limit_num": 30, "period_cd": "MONTH", "cap_unit_cd": "COUNT", "pool_scope_cd": "BENEFIT", "shared_scope_txt": null, "aggregation_key_cd": "CARD_MEMBER"}, {"pool_key": "one_pick_month_amount", "limit_num": 5000, "period_cd": "MONTH", "cap_unit_cd": "KRW", "pool_scope_cd": "BENEFIT", "shared_scope_txt": null, "aggregation_key_cd": "CARD_MEMBER"}], "schema_ver": "EXTRACT_SCHEMA_V1", "bnft_type_cd": "CASHBACK", "bnft_scope_cd": "PRODUCT", "relation_list": [], "bnft_cond_expr": null, "bnft_origin_cd": "LOCAL", "rule_select_cd": null, "bnft_brand_opt_cds": null, "is_common_candidate": false, "verification_status_cd": "PENDING_REVIEW"}	(지난달 실적 조건 없는 서비스)	1661	1678	\N	NO_EVIDENCE	\N	\N	PENDING_REVIEW	\N	\N	\N	2026-11-01 01:14:31.923648+00	SYSTEM	2026-11-01 01:14:36.959306+00	SYSTEM
20261101_000002	20261101_000002	1	20261101_000012	1	20261101_000010	2	2	BENEFIT	\N	{"rules": [{"rule_key": "style_100", "value_num": "100", "conditions": [], "limit_keys": ["style_day", "style_month_count", "style_month_amount"], "min_txn_amt": 3000, "value_raw_txt": "결제 건당\\n3천원 이상 시 \\n100원", "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": "결제 건당\\n3천원 이상 시"}, {"rule_key": "style_500", "value_num": "500", "conditions": [], "limit_keys": ["style_day", "style_month_count", "style_month_amount"], "min_txn_amt": 10000, "value_raw_txt": "결제 건당\\n1만원 이상 시 \\n500원", "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": "결제 건당\\n1만원 이상 시"}], "limits": [{"limit_key": "style_day", "limit_num": 1, "period_cd": "DAY", "cap_unit_cd": "COUNT", "limit_raw_txt": "일 1회\\n/ 월 10회", "shared_scope_txt": null, "applies_to_benefit_nms": ["STYLE 쇼핑·서점/문구·패션 캐시백"]}, {"limit_key": "style_month_count", "limit_num": 10, "period_cd": "MONTH", "cap_unit_cd": "COUNT", "limit_raw_txt": "일 1회\\n/ 월 10회", "shared_scope_txt": null, "applies_to_benefit_nms": ["STYLE 쇼핑·서점/문구·패션 캐시백"]}, {"limit_key": "style_month_amount", "limit_num": 5000, "period_cd": "MONTH", "cap_unit_cd": "KRW", "limit_raw_txt": "월 5천원", "shared_scope_txt": null, "applies_to_benefit_nms": ["STYLE 쇼핑·서점/문구·패션 캐시백"]}], "bnft_nm": "STYLE 쇼핑·서점/문구·패션 캐시백", "targets": [{"target_nm": "다이소", "target_type_cd": "MERCHANT"}, {"target_nm": "올리브영", "target_type_cd": "MERCHANT"}, {"target_nm": "교보문고", "target_type_cd": "MERCHANT"}, {"target_nm": "영풍문고", "target_type_cd": "MERCHANT"}, {"target_nm": "알라딘", "target_type_cd": "MERCHANT"}, {"target_nm": "yes24", "target_type_cd": "MERCHANT"}, {"target_nm": "아트박스", "target_type_cd": "MERCHANT"}, {"target_nm": "무신사", "target_type_cd": "MERCHANT"}, {"target_nm": "에이블리", "target_type_cd": "MERCHANT"}], "evidence": [{"supports": "COND", "quote_txt": "(지난달 실적 조건 없는 서비스)", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "TARGET", "quote_txt": "다이소, 올리브영\\n교보문고, 영풍문고,\\n알라딘, yes24,\\n아트박스\\n무신사, 에이블리", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "RULE", "quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "link_basis": "TABLE_IMAGE", "support_key": "style_100"}, {"supports": "RULE", "quote_txt": "결제 건당\\n3천원 이상 시 \\n100원\\n/\\n결제 건당\\n1만원 이상 시 \\n500원", "link_basis": "TABLE_IMAGE", "support_key": "style_500"}, {"supports": "LIMIT", "quote_txt": "일 1회\\n/ 월 10회", "link_basis": "TABLE_IMAGE", "support_key": "style_month_count"}, {"supports": "LIMIT", "quote_txt": "월 5천원", "link_basis": "TABLE_IMAGE", "support_key": "style_month_amount"}], "item_key": "style", "certainty": "HIGH", "relations": [], "conditions": [], "bnft_type_cd": "CASHBACK", "uncertainty_note": "결제금액 1만원 이상에서 두 정액 캐시백 조건의 적용 관계는 원문에 명시되지 않음.", "is_common_candidate": false, "no_condition_stated": false}	{"merge": {"item_key": "BNFT_44584D1B4FDB", "conflicts": [], "merge_ver": "MERGE_V1", "source_refs": [{"page_no": 1, "stg_item_seq": 2, "card_doc_chunk_id": "20261101_000012"}], "source_pages": [1]}, "checks": {"issues": ["style_day: 근거 없음"], "link_check_cd": "NEEDS_REVIEW", "value_check_cd": "NO_EVIDENCE"}, "bnft_cd": "BNFT_44584D1B4FDB", "bnft_nm": "STYLE 쇼핑·서점/문구·패션 캐시백", "rule_list": [{"rule_key": "style_100", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_style_100", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 3000, "cond_raw_txt": "결제 건당\\n3천원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "pool_refs": [{"pool_id": "style_day", "pool_role_cd": "CONSUME"}, {"pool_id": "style_month_count", "pool_role_cd": "CONSUME"}, {"pool_id": "style_month_amount", "pool_role_cd": "CONSUME"}], "value_num": 100, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "다이소", "target_key": "다이소", "target_type_cd": "MERCHANT"}, {"target_nm": "올리브영", "target_key": "올리브영", "target_type_cd": "MERCHANT"}, {"target_nm": "교보문고", "target_key": "교보문고", "target_type_cd": "MERCHANT"}, {"target_nm": "영풍문고", "target_key": "영풍문고", "target_type_cd": "MERCHANT"}, {"target_nm": "알라딘", "target_key": "알라딘", "target_type_cd": "MERCHANT"}, {"target_nm": "yes24", "target_key": "yes24", "target_type_cd": "MERCHANT"}, {"target_nm": "아트박스", "target_key": "아트박스", "target_type_cd": "MERCHANT"}, {"target_nm": "무신사", "target_key": "무신사", "target_type_cd": "MERCHANT"}, {"target_nm": "에이블리", "target_key": "에이블리", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}, {"rule_key": "style_500", "basis_amt": null, "cond_expr": {"branches": [{"atoms": [{"atom_key": "MIN_style_500", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 10000, "cond_raw_txt": "결제 건당\\n1만원 이상 시", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "TXN_AMT", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "pool_refs": [{"pool_id": "style_day", "pool_role_cd": "CONSUME"}, {"pool_id": "style_month_count", "pool_role_cd": "CONSUME"}, {"pool_id": "style_month_amount", "pool_role_cd": "CONSUME"}], "value_num": 500, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "다이소", "target_key": "다이소", "target_type_cd": "MERCHANT"}, {"target_nm": "올리브영", "target_key": "올리브영", "target_type_cd": "MERCHANT"}, {"target_nm": "교보문고", "target_key": "교보문고", "target_type_cd": "MERCHANT"}, {"target_nm": "영풍문고", "target_key": "영풍문고", "target_type_cd": "MERCHANT"}, {"target_nm": "알라딘", "target_key": "알라딘", "target_type_cd": "MERCHANT"}, {"target_nm": "yes24", "target_key": "yes24", "target_type_cd": "MERCHANT"}, {"target_nm": "아트박스", "target_key": "아트박스", "target_type_cd": "MERCHANT"}, {"target_nm": "무신사", "target_key": "무신사", "target_type_cd": "MERCHANT"}, {"target_nm": "에이블리", "target_key": "에이블리", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "KRW", "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "CONDITIONAL"}], "limit_list": [{"pool_key": "style_day", "limit_num": 1, "period_cd": "DAY", "cap_unit_cd": "COUNT", "pool_scope_cd": "BENEFIT", "shared_scope_txt": null, "aggregation_key_cd": "CARD_MEMBER"}, {"pool_key": "style_month_count", "limit_num": 10, "period_cd": "MONTH", "cap_unit_cd": "COUNT", "pool_scope_cd": "BENEFIT", "shared_scope_txt": null, "aggregation_key_cd": "CARD_MEMBER"}, {"pool_key": "style_month_amount", "limit_num": 5000, "period_cd": "MONTH", "cap_unit_cd": "KRW", "pool_scope_cd": "BENEFIT", "shared_scope_txt": null, "aggregation_key_cd": "CARD_MEMBER"}], "schema_ver": "EXTRACT_SCHEMA_V1", "bnft_type_cd": "CASHBACK", "bnft_scope_cd": "PRODUCT", "relation_list": [], "bnft_cond_expr": null, "bnft_origin_cd": "LOCAL", "rule_select_cd": null, "bnft_brand_opt_cds": null, "is_common_candidate": false, "verification_status_cd": "PENDING_REVIEW"}	(지난달 실적 조건 없는 서비스)	1661	1678	\N	NO_EVIDENCE	\N	\N	PENDING_REVIEW	\N	\N	\N	2026-11-01 01:14:31.923648+00	SYSTEM	2026-11-01 01:14:36.959306+00	SYSTEM
20261101_000002	20261101_000002	1	20261101_000012	1	20261101_000011	3	2	BENEFIT	\N	{"rules": [{"rule_key": "transit_rate", "value_num": "5", "conditions": [], "limit_keys": ["transit_month_amount"], "min_txn_amt": null, "value_raw_txt": "5%\\n캐시백", "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": null}], "limits": [{"limit_key": "transit_month_amount", "limit_num": 1000, "period_cd": "MONTH", "cap_unit_cd": "KRW", "limit_raw_txt": "월 1천원", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE MORE 대중교통 캐시백"]}], "bnft_nm": "ONE MORE 대중교통 캐시백", "targets": [{"target_nm": "버스", "target_type_cd": "SERVICE"}, {"target_nm": "지하철", "target_type_cd": "SERVICE"}], "evidence": [{"supports": "BNFT", "quote_txt": "대중교통\\n버스, 지하철\\n월 1천원\\n5%\\n캐시백\\n10만원", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "RULE", "quote_txt": "5%\\n캐시백", "link_basis": "TABLE_IMAGE", "support_key": "transit_rate"}, {"supports": "LIMIT", "quote_txt": "월 1천원", "link_basis": "TABLE_IMAGE", "support_key": "transit_month_amount"}], "item_key": "transit", "certainty": "HIGH", "relations": [], "conditions": [{"scope": "THIS_BENEFIT", "cond_key": "transit_spend", "evidence": [{"supports": "COND", "quote_txt": "대중교통\\n버스, 지하철\\n월 1천원\\n5%\\n캐시백\\n10만원", "link_basis": "TABLE_IMAGE", "support_key": "transit_spend"}, {"supports": "COND", "quote_txt": "- 지난달 1일부터 말일(승인 시점 기준)까지 국내외 일시불 이용금액 10만원/20만원 이상 시\\n ONE MORE 서비스 제공", "link_basis": "SAME_TEXT", "support_key": "transit_spend"}], "negate_yn": false, "cond_min_amt": 100000, "cond_raw_txt": "지난달 실적\\n대중교통\\n버스, 지하철\\n월 1천원\\n5%\\n캐시백\\n10만원", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 대중교통 캐시백"]}, {"scope": "THIS_BENEFIT", "cond_key": "transit_grace", "evidence": [{"supports": "COND", "quote_txt": "- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공", "link_basis": "SAME_TEXT", "support_key": "transit_grace"}], "negate_yn": false, "cond_min_amt": null, "cond_raw_txt": "- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공", "cond_type_cd": "GRACE", "excl_raw_txt": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 대중교통 캐시백"]}, {"scope": "THIS_BENEFIT", "cond_key": "transit_exclusions", "evidence": [{"supports": "COND", "quote_txt": "- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "link_basis": "SAME_TEXT", "support_key": "transit_exclusions"}], "negate_yn": true, "cond_min_amt": null, "cond_raw_txt": "- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "cond_basis_cd": null, "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 대중교통 캐시백"]}], "bnft_type_cd": "CASHBACK", "uncertainty_note": null, "is_common_candidate": false, "no_condition_stated": false}	{"merge": {"item_key": "BNFT_7CA4D36CA64C", "conflicts": [], "merge_ver": "MERGE_V1", "source_refs": [{"page_no": 1, "stg_item_seq": 3, "card_doc_chunk_id": "20261101_000012"}], "source_pages": [1]}, "checks": {"issues": ["transit_spend: 원문 표기가 인용에 없음"], "link_check_cd": "NEEDS_REVIEW", "value_check_cd": "VALUE_NOT_IN_QUOTE"}, "bnft_cd": "BNFT_7CA4D36CA64C", "bnft_nm": "ONE MORE 대중교통 캐시백", "rule_list": [{"rule_key": "transit_rate", "basis_amt": null, "cond_expr": null, "pool_refs": [{"pool_id": "transit_month_amount", "pool_role_cd": "CONSUME"}], "value_num": 5, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "버스", "target_key": "버스", "target_type_cd": "SERVICE"}, {"target_nm": "지하철", "target_key": "지하철", "target_type_cd": "SERVICE"}], "rule_priority": null, "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "PENDING_REVIEW"}], "limit_list": [{"pool_key": "transit_month_amount", "limit_num": 1000, "period_cd": "MONTH", "cap_unit_cd": "KRW", "pool_scope_cd": "BENEFIT", "shared_scope_txt": null, "aggregation_key_cd": "CARD_MEMBER"}], "schema_ver": "EXTRACT_SCHEMA_V1", "bnft_type_cd": "CASHBACK", "bnft_scope_cd": "PRODUCT", "relation_list": [], "bnft_cond_expr": {"branches": [{"atoms": [{"atom_key": "transit_spend", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 100000, "cond_raw_txt": "지난달 실적\\n대중교통\\n버스, 지하철\\n월 1천원\\n5%\\n캐시백\\n10만원", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "transit_grace", "atom_seq": 2, "negate_yn": false, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공", "cond_type_cd": "GRACE", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "transit_exclusions", "atom_seq": 3, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "spend_exclusions", "atom_seq": 4, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "cond_type_cd": "SPEND_EXCL", "excl_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "bnft_origin_cd": "LOCAL", "rule_select_cd": null, "bnft_brand_opt_cds": null, "is_common_candidate": false, "verification_status_cd": "PENDING_REVIEW"}	대중교통\n버스, 지하철\n월 1천원\n5%\n캐시백\n10만원	2342	2371	\N	VALUE_NOT_IN_QUOTE	\N	\N	PENDING_REVIEW	\N	\N	\N	2026-11-01 01:14:31.923648+00	SYSTEM	2026-11-01 01:14:36.959306+00	SYSTEM
20261101_000002	20261101_000002	1	20261101_000012	1	20261101_000012	4	2	BENEFIT	\N	{"rules": [{"rule_key": "amusement_rate", "value_num": "50", "conditions": [], "limit_keys": ["amusement_month", "amusement_year", "amusement_person"], "min_txn_amt": null, "value_raw_txt": "50% \\n현장할인\\n(1인 1매)", "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN", "payout_unit_cd": "KRW", "min_txn_raw_txt": null}], "limits": [{"limit_key": "amusement_month", "limit_num": 1, "period_cd": "MONTH", "cap_unit_cd": "COUNT", "limit_raw_txt": "월 1회 \\n/ 연 2회", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE MORE 놀이공원 현장할인"]}, {"limit_key": "amusement_year", "limit_num": 2, "period_cd": "YEAR", "cap_unit_cd": "COUNT", "limit_raw_txt": "월 1회 \\n/ 연 2회", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE MORE 놀이공원 현장할인"]}, {"limit_key": "amusement_person", "limit_num": 1, "period_cd": "UNKNOWN", "cap_unit_cd": "COUNT", "limit_raw_txt": "(1인 1매)", "shared_scope_txt": null, "applies_to_benefit_nms": ["ONE MORE 놀이공원 현장할인"]}], "bnft_nm": "ONE MORE 놀이공원 현장할인", "targets": [{"target_nm": "에버랜드", "target_type_cd": "MERCHANT"}, {"target_nm": "롯데월드", "target_type_cd": "MERCHANT"}], "evidence": [{"supports": "BNFT", "quote_txt": "놀이공원\\n에버랜드, 롯데월드\\n월 1회 \\n/ 연 2회\\n50% \\n현장할인\\n(1인 1매)\\n20만원\\n최초 발급 월에는\\n서비스 미제공", "link_basis": "TABLE_IMAGE", "support_key": null}, {"supports": "RULE", "quote_txt": "50% \\n현장할인\\n(1인 1매)", "link_basis": "TABLE_IMAGE", "support_key": "amusement_rate"}, {"supports": "LIMIT", "quote_txt": "월 1회 \\n/ 연 2회", "link_basis": "TABLE_IMAGE", "support_key": "amusement_year"}], "item_key": "amusement", "certainty": "HIGH", "relations": [], "conditions": [{"scope": "THIS_BENEFIT", "cond_key": "amusement_spend", "evidence": [{"supports": "COND", "quote_txt": "* ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공", "link_basis": "SAME_TEXT", "support_key": "amusement_spend"}], "negate_yn": false, "cond_min_amt": 200000, "cond_raw_txt": "* ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 놀이공원 현장할인"]}, {"scope": "THIS_BENEFIT", "cond_key": "amusement_first_month", "evidence": [{"supports": "COND", "quote_txt": "최초 발급 월에는\\n서비스 미제공", "link_basis": "TABLE_IMAGE", "support_key": "amusement_first_month"}], "negate_yn": true, "cond_min_amt": null, "cond_raw_txt": "최초 발급 월에는\\n서비스 미제공", "cond_type_cd": "GRACE", "excl_raw_txt": "최초 발급 월에는\\n서비스 미제공", "cond_basis_cd": null, "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 놀이공원 현장할인"]}], "bnft_type_cd": "DISCOUNT", "uncertainty_note": null, "is_common_candidate": false, "no_condition_stated": false}	{"merge": {"item_key": "BNFT_C63ED6040122", "conflicts": [], "merge_ver": "MERGE_V1", "source_refs": [{"page_no": 1, "stg_item_seq": 4, "card_doc_chunk_id": "20261101_000012"}], "source_pages": [1]}, "checks": {"issues": ["amusement_month: 근거 없음", "amusement_person: 근거 없음", "amusement_person: 한도 값 미확정"], "link_check_cd": "NEEDS_REVIEW", "value_check_cd": "NO_EVIDENCE"}, "bnft_cd": "BNFT_C63ED6040122", "bnft_nm": "ONE MORE 놀이공원 현장할인", "rule_list": [{"rule_key": "amusement_rate", "basis_amt": null, "cond_expr": null, "pool_refs": [{"pool_id": "amusement_month", "pool_role_cd": "CONSUME"}, {"pool_id": "amusement_year", "pool_role_cd": "CONSUME"}, {"pool_id": "amusement_person", "pool_role_cd": "CONSUME"}], "value_num": 50, "method_ver": 1, "calc_params": null, "target_list": [{"target_nm": "에버랜드", "target_key": "에버랜드", "target_type_cd": "MERCHANT"}, {"target_nm": "롯데월드", "target_key": "롯데월드", "target_type_cd": "MERCHANT"}], "rule_priority": null, "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN", "payout_unit_cd": "KRW", "rule_status_cd": "DRAFT", "predicate_state_cd": "PENDING_REVIEW"}], "limit_list": [{"pool_key": "amusement_month", "limit_num": 1, "period_cd": "MONTH", "cap_unit_cd": "COUNT", "pool_scope_cd": "BENEFIT", "shared_scope_txt": null, "aggregation_key_cd": "CARD_MEMBER"}, {"pool_key": "amusement_year", "limit_num": 2, "period_cd": "YEAR", "cap_unit_cd": "COUNT", "pool_scope_cd": "BENEFIT", "shared_scope_txt": null, "aggregation_key_cd": "CARD_MEMBER"}, {"pool_key": "amusement_person", "limit_num": 1, "period_cd": "UNKNOWN", "cap_unit_cd": "COUNT", "pool_scope_cd": "BENEFIT", "shared_scope_txt": null, "aggregation_key_cd": "CARD_MEMBER"}], "schema_ver": "EXTRACT_SCHEMA_V1", "bnft_type_cd": "DISCOUNT", "bnft_scope_cd": "PRODUCT", "relation_list": [], "bnft_cond_expr": {"branches": [{"atoms": [{"atom_key": "amusement_spend", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": 200000, "cond_raw_txt": "* ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공", "cond_type_cd": "SPEND_REQ", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "amusement_first_month", "atom_seq": 2, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "최초 발급 월에는\\n서비스 미제공", "cond_type_cd": "GRACE", "excl_raw_txt": "최초 발급 월에는\\n서비스 미제공", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "spend_exclusions", "atom_seq": 3, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "cond_type_cd": "SPEND_EXCL", "excl_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "bnft_origin_cd": "LOCAL", "rule_select_cd": null, "bnft_brand_opt_cds": null, "is_common_candidate": false, "verification_status_cd": "PENDING_REVIEW"}	놀이공원\n에버랜드, 롯데월드\n월 1회 \n/ 연 2회\n50% \n현장할인\n(1인 1매)\n20만원\n최초 발급 월에는\n서비스 미제공	2373	2441	\N	NO_EVIDENCE	\N	\N	PENDING_REVIEW	\N	\N	\N	2026-11-01 01:14:31.923648+00	SYSTEM	2026-11-01 01:14:36.959306+00	SYSTEM
20261101_000002	20261101_000002	1	20261101_000012	1	20261101_000013	5	2	CONDITION	\N	{"scope": "ALL_BENEFITS", "cond_key": "common_service_exclusion", "evidence": [{"supports": "COND", "quote_txt": "- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "link_basis": "SAME_TEXT", "support_key": "common_service_exclusion"}], "negate_yn": true, "cond_min_amt": null, "cond_raw_txt": "- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외", "cond_basis_cd": null, "cond_max_amt_excl": null, "target_benefit_nms": []}	{"merge": {"item_key": "COND_ECE6A8700C59", "conflicts": [], "merge_ver": "MERGE_V1", "source_refs": [{"page_no": 1, "stg_item_seq": 5, "card_doc_chunk_id": "20261101_000012"}], "source_pages": [1]}, "checks": {"issues": [], "link_check_cd": "TEXT_CONFIRMED", "value_check_cd": "OK"}, "scope_cd": "ALL_BENEFITS", "cond_expr": {"branches": [{"atoms": [{"atom_key": "common_service_exclusion", "atom_seq": 1, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "schema_ver": "EXTRACT_SCHEMA_V1", "applies_to_item_keys": []}	- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외	169	383	\N	OK	\N	\N	PENDING_REVIEW	\N	\N	\N	2026-11-01 01:14:31.923648+00	SYSTEM	2026-11-01 01:14:36.959306+00	SYSTEM
20261101_000002	20261101_000002	1	20261101_000012	1	20261101_000014	6	2	CONDITION	\N	{"scope": "ALL_BENEFITS", "cond_key": "common_channel", "evidence": [{"supports": "COND", "quote_txt": "대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "link_basis": "SAME_TEXT", "support_key": "common_channel"}], "negate_yn": false, "cond_min_amt": null, "cond_raw_txt": "대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_type_cd": "PAYMENT_METHOD", "excl_raw_txt": "배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_basis_cd": null, "cond_max_amt_excl": null, "target_benefit_nms": []}	{"merge": {"item_key": "COND_DC594D41533E", "conflicts": [], "merge_ver": "MERGE_V1", "source_refs": [{"page_no": 1, "stg_item_seq": 6, "card_doc_chunk_id": "20261101_000012"}], "source_pages": [1]}, "checks": {"issues": [], "link_check_cd": "TEXT_CONFIRMED", "value_check_cd": "OK"}, "scope_cd": "ALL_BENEFITS", "cond_expr": {"branches": [{"atoms": [{"atom_key": "common_channel", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_type_cd": "PAYMENT_METHOD", "excl_raw_txt": "배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "schema_ver": "EXTRACT_SCHEMA_V1", "applies_to_item_keys": []}	대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외	228	383	\N	OK	\N	\N	PENDING_REVIEW	\N	\N	\N	2026-11-01 01:14:31.923648+00	SYSTEM	2026-11-01 01:14:36.959306+00	SYSTEM
20261101_000002	20261101_000002	1	20261101_000012	1	20261101_000015	7	2	CONDITION	\N	{"scope": "NAMED_BENEFITS", "cond_key": "spend_exclusions", "evidence": [{"supports": "COND", "quote_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "link_basis": "SAME_TEXT", "support_key": "spend_exclusions"}], "negate_yn": true, "cond_min_amt": null, "cond_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "cond_type_cd": "SPEND_EXCL", "excl_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "cond_basis_cd": "PREV_MONTH_SPEND", "cond_max_amt_excl": null, "target_benefit_nms": ["ONE MORE 대중교통 캐시백", "ONE MORE 놀이공원 현장할인"]}	{"merge": {"item_key": "COND_1181E671576D", "conflicts": [], "merge_ver": "MERGE_V1", "source_refs": [{"page_no": 1, "stg_item_seq": 7, "card_doc_chunk_id": "20261101_000012"}], "source_pages": [1]}, "checks": {"issues": [], "link_check_cd": "TEXT_CONFIRMED", "value_check_cd": "OK"}, "scope_cd": "NAMED_BENEFITS", "cond_expr": {"branches": [{"atoms": [{"atom_key": "spend_exclusions", "atom_seq": 1, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "cond_type_cd": "SPEND_EXCL", "excl_raw_txt": "- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \\n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \\n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \\n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \\n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외", "link_role_cd": null, "cond_basis_cd": "PREV_MONTH_SPEND", "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "schema_ver": "EXTRACT_SCHEMA_V1", "applies_to_item_keys": ["BNFT_7CA4D36CA64C", "BNFT_C63ED6040122"]}	- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외	515	789	\N	OK	\N	\N	PENDING_REVIEW	\N	\N	\N	2026-11-01 01:14:31.923648+00	SYSTEM	2026-11-01 01:14:36.959306+00	SYSTEM
20261101_000002	20261101_000002	1	20261101_000012	1	20261101_000016	8	2	CONDITION	\N	{"scope": "ALL_BENEFITS", "cond_key": "merchant_classification", "evidence": [{"supports": "COND", "quote_txt": "- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공", "link_basis": "SAME_TEXT", "support_key": "merchant_classification"}, {"supports": "COND", "quote_txt": "- 가맹점 정보가 해당 업체가 아닌 결제대행업체(PG) 또는 간편결제 전용 가맹점으로 확인되는 \\n 경우 ‘결제대행업체’ 또는 ‘간편결제’ 가맹점으로 분류되어 각 서비스 영역에 따른 혜택이 제공됨", "link_basis": "SAME_TEXT", "support_key": "merchant_classification"}], "negate_yn": false, "cond_min_amt": null, "cond_raw_txt": "- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공", "cond_type_cd": "MERCHANT_RULE", "excl_raw_txt": null, "cond_basis_cd": null, "cond_max_amt_excl": null, "target_benefit_nms": []}	{"merge": {"item_key": "COND_C7B65B7F7980", "conflicts": [], "merge_ver": "MERGE_V1", "source_refs": [{"page_no": 1, "stg_item_seq": 8, "card_doc_chunk_id": "20261101_000012"}], "source_pages": [1]}, "checks": {"issues": [], "link_check_cd": "TEXT_CONFIRMED", "value_check_cd": "OK"}, "scope_cd": "ALL_BENEFITS", "cond_expr": {"branches": [{"atoms": [{"atom_key": "merchant_classification", "atom_seq": 1, "negate_yn": false, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공", "cond_type_cd": "MERCHANT_RULE", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}, "schema_ver": "EXTRACT_SCHEMA_V1", "applies_to_item_keys": []}	- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공	1146	1186	\N	OK	\N	\N	PENDING_REVIEW	\N	\N	\N	2026-11-01 01:14:31.923648+00	SYSTEM	2026-11-01 01:14:36.959306+00	SYSTEM
20261102_000003	20261102_000004	1	20261102_000020	1	20261102_000017	1	\N	BENEFIT	\N	{"rules": [], "limits": [], "bnft_nm": "Visa 컨시어지", "targets": [], "evidence": [{"supports": "BNFT", "quote_txt": "Visa 컨시어지제공", "link_basis": "SAME_TEXT", "support_key": null}, {"supports": "APPLICABILITY", "quote_txt": "아래의Visa Signature서비스는Visa Signature 등급카드\\n소지자에게공통으로제공됩니다.", "link_basis": "SAME_TEXT", "support_key": null}, {"supports": "APPLICABILITY", "quote_txt": "본Visa Signature 서비스는기간이따로명시되지않은한\\n2026년1월1일~ 12월31일까지제공됩니다.", "link_basis": "SAME_TEXT", "support_key": null}], "item_key": "VISA_CONCIERGE", "brand_txt": "Visa", "certainty": "HIGH", "relations": [], "conditions": [], "bnft_type_cd": "SERVICE", "excluded_cards": [], "applicable_cards": [], "uncertainty_note": "수동으로 한 혜택만 발췌. 세부 제공 조건 및 비용은 미확인.", "service_grade_txt": "Signature", "is_common_candidate": true, "no_condition_stated": false, "validity_period_txt": "2026년1월1일~ 12월31일", "selection_service_txt": null}	{"merge": {"item_key": "BNFT_BD6A3D0D63D1", "conflicts": [], "merge_ver": "MERGE_V1", "source_refs": [{"page_no": 1, "stg_item_seq": 1, "card_doc_chunk_id": "20261102_000020"}], "source_pages": [1]}, "checks": {"issues": [], "link_check_cd": "NEEDS_REVIEW", "value_check_cd": "OK"}, "bnft_cd": "BNFT_BD6A3D0D63D1", "bnft_nm": "Visa 컨시어지", "rule_list": [], "limit_list": [], "schema_ver": "EXTRACT_SCHEMA_V2", "bnft_type_cd": "SERVICE", "bnft_scope_cd": null, "relation_list": [], "bnft_cond_expr": null, "bnft_origin_cd": null, "rule_select_cd": null, "bnft_brand_opt_cds": null, "is_common_candidate": true, "verification_status_cd": "PENDING_REVIEW"}	Visa 컨시어지제공	1265	1275	\N	LINK_REVIEW	\N	\N	PENDING_REVIEW	\N	\N	\N	2026-11-02 08:44:16.538489+00	SYSTEM	2026-11-02 08:44:16.538489+00	SYSTEM
\.


--
-- TOC entry 4375 (class 0 OID 20665)
-- Dependencies: 358
-- Data for Name: card_product; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_product (card_id, product_cd, product_nm, issuer, card_kind_cd, product_status_cd, launched_on, discontinued_on, brand_opt_list, create_date, create_user_id, update_date, update_user_id, card_cond_expr, card_cond_status_cd) FROM stdin;
2	HANA_DEBIT_ONE_PICK_STYLE	ONE PICK STYLE 하나 체크카드	하나카드	DEBIT	ACTIVE	2026-03-30	\N	[{"brand_cd": "LOCAL", "brand_opt_cd": "LOCAL", "brand_opt_nm": "국내전용", "service_type_cd": "NONE", "service_grade_cd": "NONE", "brand_opt_status_cd": "ACTIVE"}, {"brand_cd": "MASTERCARD", "brand_opt_cd": "MASTERCARD", "brand_opt_nm": "Mastercard", "service_type_cd": "NONE", "service_grade_cd": "NONE", "brand_opt_status_cd": "ACTIVE"}]	2026-11-01 01:13:51.954632+00	A72_TEST	2026-11-01 01:13:51.954632+00	A72_TEST	{"branches": [{"atoms": [{"atom_key": "common_service_exclusion", "atom_seq": 1, "negate_yn": true, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_type_cd": "BNFT_EXCL", "excl_raw_txt": "상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "common_channel", "atom_seq": 2, "negate_yn": false, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "cond_type_cd": "PAYMENT_METHOD", "excl_raw_txt": "배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외", "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}, {"atom_key": "merchant_classification", "atom_seq": 3, "negate_yn": false, "cond_params": null, "cond_min_amt": null, "cond_raw_txt": "- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공", "cond_type_cd": "MERCHANT_RULE", "excl_raw_txt": null, "link_role_cd": null, "cond_basis_cd": null, "cond_status_cd": "DRAFT", "card_excl_item_id": null, "cond_max_amt_excl": null, "predicate_method_cd": null, "predicate_method_ver": null}], "branch_no": 1}], "expr_status_cd": "DRAFT"}	DRAFT
5	HANA_CREDIT_JADE_CLASSIC	JADE Classic	하나카드	CREDIT	ACTIVE	\N	\N	[{"brand_cd": "VISA", "brand_opt_cd": "VISA_SIGNATURE_02", "brand_opt_nm": "Visa Signature 02", "service_type_cd": "02", "service_grade_cd": "SIGNATURE", "brand_opt_status_cd": "ACTIVE"}, {"brand_cd": "MASTERCARD", "brand_opt_cd": "MASTERCARD_WORLD_03", "brand_opt_nm": "Mastercard World 03", "service_type_cd": "03", "service_grade_cd": "WORLD", "brand_opt_status_cd": "ACTIVE"}, {"brand_cd": "AMEX", "brand_opt_cd": "AMEX_PLATINUM_03", "brand_opt_nm": "Amex Platinum 03", "service_type_cd": "03", "service_grade_cd": "PLATINUM", "brand_opt_status_cd": "ACTIVE"}, {"brand_cd": "UPI", "brand_opt_cd": "UPI_DIAMOND_02", "brand_opt_nm": "UPI Diamond 02", "service_type_cd": "02", "service_grade_cd": "DIAMOND", "brand_opt_status_cd": "ACTIVE"}]	2026-11-02 08:44:16.538489+00	MANUAL_SOURCE_REVIEW	2026-11-02 08:44:16.538489+00	MANUAL_SOURCE_REVIEW	\N	DRAFT
\.


--
-- TOC entry 4376 (class 0 OID 20696)
-- Dependencies: 359
-- Data for Name: card_product_doc; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_product_doc (card_id, card_doc_id, doc_role_cd, brand_opt_cds, approval_status_cd, applicability_basis_txt, approval_note, create_date, create_user_id, update_date, update_user_id) FROM stdin;
2	20261101_000002	PRODUCT_GUIDE	\N	PENDING	PDF 상품명 일치; 공식 서버 URL 추정 확인, 적용 승인 대기	\N	2026-11-01 01:14:02.825713+00	A72_TEST	2026-11-01 01:14:02.825713+00	A72_TEST
5	20261102_000003	PRODUCT_GUIDE	\N	PENDING	JADE Classic 공식 상품설명서. Visa Signature 02 유형은 5쪽에 명시.	\N	2026-11-02 08:44:16.538489+00	MANUAL_SOURCE_REVIEW	2026-11-02 08:44:16.538489+00	MANUAL_SOURCE_REVIEW
5	20261102_000004	BRAND_SERVICE	{VISA_SIGNATURE_02}	PENDING	아래의Visa Signature서비스는Visa Signature 등급카드\n소지자에게공통으로제공됩니다. / 상품설명서: Visa : Visa Signature 02 유형	\N	2026-11-02 08:44:16.538489+00	MANUAL_SOURCE_REVIEW	2026-11-02 08:44:16.538489+00	MANUAL_SOURCE_REVIEW
\.


--
-- TOC entry 4391 (class 0 OID 21754)
-- Dependencies: 385
-- Data for Name: card_source_evidence; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.card_source_evidence (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_extr_stg_id, quote_txt, start_pos, end_pos, approval_status_cd) FROM stdin;
20261101_000002	1	20261101_000012	20261101_000031	20261101_000009	(지난달 실적 조건 없는 서비스)	1661	1678	PENDING
20261101_000002	1	20261101_000012	20261101_000032	20261101_000009	CU, GS25, \n세븐일레븐	1475	1490	PENDING
20261101_000002	1	20261101_000012	20261101_000033	20261101_000009	메가MGC커피, \n이디야커피, \n컴포즈커피	1541	1563	PENDING
20261101_000002	1	20261101_000012	20261101_000034	20261101_000009	결제 건당\n3천원 이상 시 \n100원\n/\n결제 건당\n1만원 이상 시 \n500원	1565	1607	PENDING
20261101_000002	1	20261101_000012	20261101_000035	20261101_000009	결제 건당\n3천원 이상 시 \n100원\n/\n결제 건당\n1만원 이상 시 \n500원	1565	1607	PENDING
20261101_000002	1	20261101_000012	20261101_000036	20261101_000009	일 1회\n/ 월 30회	2257	2268	PENDING
20261101_000002	1	20261101_000012	20261101_000038	20261101_000010	(지난달 실적 조건 없는 서비스)	1661	1678	PENDING
20261101_000002	1	20261101_000012	20261101_000039	20261101_000010	다이소, 올리브영\n교보문고, 영풍문고,\n알라딘, yes24,\n아트박스\n무신사, 에이블리	1492	1539	PENDING
20261101_000002	1	20261101_000012	20261101_000040	20261101_000010	결제 건당\n3천원 이상 시 \n100원\n/\n결제 건당\n1만원 이상 시 \n500원	1565	1607	PENDING
20261101_000002	1	20261101_000012	20261101_000041	20261101_000010	결제 건당\n3천원 이상 시 \n100원\n/\n결제 건당\n1만원 이상 시 \n500원	1565	1607	PENDING
20261101_000002	1	20261101_000012	20261101_000042	20261101_000010	일 1회\n/ 월 10회	1609	1620	PENDING
20261101_000002	1	20261101_000012	20261101_000043	20261101_000010	월 5천원	1622	1626	PENDING
20261101_000002	1	20261101_000012	20261101_000044	20261101_000011	대중교통\n버스, 지하철\n월 1천원\n5%\n캐시백\n10만원	2342	2371	PENDING
20261101_000002	1	20261101_000012	20261101_000045	20261101_000011	5%\n캐시백	2361	2366	PENDING
20261101_000002	1	20261101_000012	20261101_000046	20261101_000011	월 1천원	2355	2359	PENDING
20261101_000002	1	20261101_000012	20261101_000047	20261101_000011	대중교통\n버스, 지하철\n월 1천원\n5%\n캐시백\n10만원	2342	2371	PENDING
20261101_000002	1	20261101_000012	20261101_000048	20261101_000011	- 지난달 1일부터 말일(승인 시점 기준)까지 국내외 일시불 이용금액 10만원/20만원 이상 시\n ONE MORE 서비스 제공	435	504	PENDING
20261101_000002	1	20261101_000012	20261101_000049	20261101_000011	- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공	807	895	PENDING
20261101_000002	1	20261101_000012	20261101_000050	20261101_000011	- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외	385	424	PENDING
20261101_000002	1	20261101_000012	20261101_000051	20261101_000012	놀이공원\n에버랜드, 롯데월드\n월 1회 \n/ 연 2회\n50% \n현장할인\n(1인 1매)\n20만원\n최초 발급 월에는\n서비스 미제공	2373	2441	PENDING
20261101_000002	1	20261101_000012	20261101_000052	20261101_000012	50% \n현장할인\n(1인 1매)	2402	2418	PENDING
20261101_000002	1	20261101_000012	20261101_000053	20261101_000012	월 1회 \n/ 연 2회	2389	2400	PENDING
20261101_000002	1	20261101_000012	20261101_000054	20261101_000012	* ONE MORE 놀이공원 서비스는 지난달 실적 20만원 이상 시 서비스 제공	898	941	PENDING
20261101_000002	1	20261101_000012	20261101_000055	20261101_000012	최초 발급 월에는\n서비스 미제공	2425	2441	PENDING
20261101_000002	1	20261101_000012	20261101_000056	20261101_000013	- 공통 : 상품권 및 기프트카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액 제외,\n 대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외	169	383	PENDING
20261101_000002	1	20261101_000012	20261101_000057	20261101_000014	대상 가맹점의 공식 홈페이지(온라인/모바일 앱) 및 오프라인을 통한 결제 시에만 서비스가 제공되며,\n 배달 앱이나 식당 예약 앱을 통한 주문 결제, 대형시설(백화점, 할인점, 아울렛, 쇼핑몰, 휴게소,\n 호텔, 리조트, 공항, 역사, 마트) 입점 점포 및 임대 매장 결제 시 제외	228	383	PENDING
20261101_000002	1	20261101_000012	20261101_000058	20261101_000015	- 국세, 지방세, 수도/전기요금, 그 외 공과금[우편요금, 과태료, 범칙금, 벌금, 국가/공공기관/ \n 공공단체가 부과하는 부담금], 도시가스 요금, 아파트관리비, 국민연금/고용보험료/산재보험료/ \n 건강보험료 납부 금액, 스쿨뱅킹, 초·중·고 학교납입금, 대학등록금, 대학원등록금, 상품권 및 기프트 \n 카드 구매, 선불카드 및 선불전자지급수단(예시:하나머니) 충전 금액, 부동산 임대료, 국내외 ATM \n 이용금액, ONE PICK STYLE 하나 체크카드로 서비스 적용 받은 매출 제외	515	789	PENDING
20261101_000002	1	20261101_000012	20261101_000059	20261101_000016	- 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공	1146	1186	PENDING
20261101_000002	1	20261101_000012	20261101_000060	20261101_000016	- 가맹점 정보가 해당 업체가 아닌 결제대행업체(PG) 또는 간편결제 전용 가맹점으로 확인되는 \n 경우 ‘결제대행업체’ 또는 ‘간편결제’ 가맹점으로 분류되어 각 서비스 영역에 따른 혜택이 제공됨	1188	1295	PENDING
20261101_000002	1	20261101_000012	20261101_000037	20261101_000009	월 5천원	2270	2274	PENDING
20261101_000002	2	20261101_000013	20261101_000061	\N	부가서비스 유지 및 변경 안내    \n \n· 카드이용 시 제공되는 포인트 및 할인혜택 등의 부가서비스는 카드 신규 출시(2026년 3월 30일) \n 이후 3년 이상 축소·폐지 없이 유지됩니다.\n· 다만, 다음과 같은 사유가 발생한 경우 카드사는 부가서비스를 변경할 수 있습니다.\n ①: 카드사의 휴업·파산·경영상의 위기 등에 따른 불가피한 경우\n ①의2: 제휴업체의 휴업·파산·경영상의 위기로 인해 불가피하게 부가서비스를 축소·변경하는\n  \n \n경우로서 다른 제휴업체를 통해 같은 종류의 유사한 부가서비스 제공이 불가한 경우\n ②: 제휴업체가 카드사의 의사에 반하여 해당 부가서비스를 축소하거나 변경 시, 당초 부가서비스에 \n  \n상응하는 다른 부가서비스를 제공하는 경우 \n ③: 부가서비스를 3년 이상 제공한 상태에서 해당 부가서비스로 인해 상품의 수익성이 현저히\n  \n낮아진 경우 \n· 카드사가 부가서비스를 변경하는 경우 변경사유, 변경내용 등을 다음 각호에서 정하는 기간에 \n 따라 서면교부, 우편 또는 전자우편, 전화 또는 팩스, 휴대폰 메시지 또는 이에 준하는 전자적 \n 의사표시 중 서로 다른 2가지 이상의 방법 으로 고지하여 드립니다. 다만, 제2호의 경우 부가 \n 서비스 변경일 6개월 이전부터는 서면교부, 우편 또는 전자 우편, 전화 또는 팩스, 휴대폰 메시지 \n 또는 이에 준하는 전자적 의사표시 중 서로 다른 2가지 이상의 방법으로 매월 고지하여 드립니다.\n 1. ①, ①의2, ②: 사유발생 즉시\n   2. ③: 부가서비스 변경일 6개월 이전	1	763	PENDING
20261102_000003	5	20261102_000018	20261102_000062	\N	Visa : Visa Signature 02 유형	472	498	PENDING
20261102_000004	1	20261102_000020	20261102_000063	20261102_000017	Visa 컨시어지제공	1265	1275	PENDING
20261102_000004	1	20261102_000020	20261102_000064	20261102_000017	아래의Visa Signature서비스는Visa Signature 등급카드\n소지자에게공통으로제공됩니다.	733	788	PENDING
20261102_000004	1	20261102_000020	20261102_000065	20261102_000017	본Visa Signature 서비스는기간이따로명시되지않은한\n2026년1월1일~ 12월31일까지제공됩니다.	2286	2343	PENDING
\.


--
-- TOC entry 4374 (class 0 OID 20656)
-- Dependencies: 357
-- Data for Name: common_cd; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.common_cd (common_code_grp_id, common_cd, common_cd_nm, create_date, create_user_id, update_date, update_user_id, common_cd_desc) FROM stdin;
REL_TYPE	OVERRIDES	우선 적용	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	\N
EV_SUBJECT	CARD	카드	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	근거가 카드 공통 조건이나 상품 전체를 뒷받침하는 경우. 특정 혜택에 속하지 않는 내용에 쓰며 혜택, 규칙, 관계, 풀 컬럼은 모두 비워야 한다.
BNFT_ORIGIN	BRAND_SERVICE	브랜드 공통 서비스	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	국제 브랜드 서비스 안내서에 근거해 카드별로 등록한 혜택. 계산 규칙은 카드의 rule_list에 직접 두고 원문 근거는 공통 PDF의 근거를 공유한다. bnft_scope_cd가 BRAND여야 하고(card_bnft_ck_5), 적용 선택지에 BRAND_SERVICE 문서 연결이 없으면 게이트 brand_bnft_doc_not_linked에서 검출된다.
BNFT_ORIGIN	LOCAL	상품 고유 혜택	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	해당 상품 고유의 혜택. 상품설명서 등 상품 문서에 근거하며 현재 추출기는 모든 혜택을 이 값으로 정규화한다. 브랜드 서비스 안내서에 근거한 BRAND_SERVICE와 구분된다.
COND_TYPE	MERCHANT_RULE	가맹점 규칙	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	가맹점이나 업종의 분류 기준에 관한 조건. 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공한다는 카드 공통 조건이 해당한다. 개별 대상 가맹점은 target_list에 두고 이 유형은 판정 기준을 담는다.
EV_ITEM	COND	조건 atom	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	근거가 조건식의 atom 하나를 가리키는 경우. ev_item_key에 atom_key를 저장한다.
EV_ITEM	TARGET	대상	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	근거가 규칙 대상 하나를 가리키는 경우. ev_item_key에 target_key를 저장한다.
EV_ITEM	TIER	한도 구간	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	근거가 상품 한도 풀의 구간 하나를 가리키는 경우. ev_item_key에 tier_key를 저장한다.
SERVICE_GRADE	NONE	등급 없음	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	브랜드 서비스 등급이 없거나 해당하지 않는 경우. 등급 정보가 없는 브랜드 선택지에 쓴다. 등급을 확인하지 못했다는 뜻이 아니라 적용할 등급이 없다는 뜻이다.
SERVICE_TYPE	NONE	유형 없음	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	브랜드 서비스 유형 구분이 없거나 해당하지 않는 경우. 공통 서비스와 선택서비스 어느 쪽도 아닐 때 쓴다.
DOC_TYPE	BRAND_SERVICE	브랜드 서비스 안내	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	국제 브랜드의 등급별 서비스를 안내하는 문서. Visa, Mastercard, AMEX, JCB, UnionPay 안내서가 해당하며 여러 카드가 공유하는 문서로 한 번만 등록한다.
CALC_METHOD	FIXED_PER_TXN	건당 정액	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	조건을 충족한 결제 1건마다 정해진 금액이나 포인트·마일리지를 제공하는 방식. value_num은 건당 수량이며 ONE PICK의 100원, 500원 캐시백이 해당한다. 결제금액에 비례하는 PERCENT_OF_TXN, 금액 구간마다 적립하는 UNITS_PER_AMOUNT와 구분된다.
SERVICE_GRADE	PRESTIGE	Prestige	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	\N
APPROVAL_STATUS	APPROVED	승인	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	대상 데이터가 해당 업무의 검증 기준을 충족해 사용 승인을 받은 상태. 문서 연결은 적용 근거가 있어야 승인할 수 있고(card_product_doc_approved_check), 근거는 이 값일 때만 게이트 evidence_not_approved를 통과한다. 승인 대상과 범위는 사용하는 테이블에 따라 결정된다.
ITEM_STATUS	DRAFT	작성 중	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	규칙 또는 조건이 작성 중이라 아직 확정되지 않은 상태. AI 추출 결과를 정규화할 때 부여하는 초기값이며 card_product.card_cond_status_cd의 기본값이다. 혜택 전체가 아니라 규칙·조건 단위의 상태다.
APPROVAL_STATUS	PENDING	승인 대기	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	대상 문서 연결 또는 원문 근거의 정확성과 적용 여부에 대한 검토가 끝나지 않은 상태. 업무 사용 승인 전 단계이며 card_product_doc의 기본값이다. 이 상태의 근거가 카드 항목에 연결되어 있으면 게이트 evidence_not_approved에서 검출된다.
PRODUCT_STATUS	ACTIVE	판매 중	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	상품 또는 브랜드 선택지가 판매 중인 상태. 상품 등록의 기본값이다. 데이터 사용 가능 여부가 아닌 판매 사실을 나타내므로 DOC_STATUS.ACTIVE(문서 사용 중)와 의미가 다르다.
RUN_STAGE	EMBED	임베딩	2026-11-02 20:49:52.585482+00	SYSTEM	2026-11-02 20:49:52.585482+00	SYSTEM	혜택 검색 텍스트 임베딩 생성 실행
CARD_KIND	CREDIT	신용카드	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	이용대금을 나중에 결제하는 신용카드 상품. 신용카드 개인회원 표준약관을 적용받는다는 점에서 체크카드 약관을 적용받는 DEBIT와 구분된다.
CARD_KIND	DEBIT	체크카드	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	결제 계좌 잔액 범위에서 이용하는 체크카드 상품. 원문의 상품명에 체크카드로 표기되고 신용카드 약관이 아닌 체크카드 약관을 적용받는다는 점에서 CREDIT와 구분된다.
PRODUCT_STATUS	DISCONTINUED	판매 중단	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	상품 또는 브랜드 선택지의 판매가 중단된 상태. 상품에서는 discontinued_on에 중단일을 기록한다. 판매 사실만 나타내므로 정책이나 문서의 사용 가능 여부는 각자의 상태 코드로 판단한다.
DOC_ROLE	PRODUCT_GUIDE	상품설명서	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	문서가 해당 상품의 혜택과 조건을 설명하는 상품설명서 역할을 하는 경우. 상품별 혜택 추출의 기본 원천이며, 여러 상품에 공통 적용되는 COMMON_TERMS와 달리 해당 상품을 직접 설명한다.
DOC_ROLE	COMMON_TERMS	공통 약관	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	여러 상품에 공통으로 적용되는 약관이 해당 상품에 연결되는 경우. 신용카드 개인회원 표준약관, 체크카드 개인회원 약관처럼 특정 상품의 혜택표가 아니라 공통 이용 조건을 규정한다. 관계 코드이며 문서 자체의 종류는 DOC_TYPE.TERMS로 기록한다.
DOC_ROLE	BRAND_SERVICE	브랜드 서비스 안내	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	국제 브랜드 서비스 안내서가 상품의 특정 브랜드 선택지에 적용되는 경우. card_product_doc에서 이 역할은 brand_opt_cds가 필수이므로(card_product_doc_brand_check) 어느 선택지에 적용되는 문서인지 지정해야 한다.
DOC_ROLE	OTHER	기타	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	상품설명서, 공통 약관, 브랜드 서비스 안내 어디에도 해당하지 않는 문서 역할. 역할을 판단하지 못한 경우가 아니라 정의된 세 역할 밖의 문서를 연결할 때 사용한다. DOC_TYPE의 기타 코드는 ETC로 값이 다르다.
APPROVAL_STATUS	REJECTED	반려	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	대상 데이터가 검증 기준을 충족하지 못하거나 근거가 부적절해 승인을 거부한 상태. 검토를 마쳤다는 점에서 PENDING과 다르며, APPROVED만 인정하는 조회와 근거 게이트를 통과하지 못한다.
ITEM_STATUS	CONFIRMED	확정	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	규칙 또는 조건의 내용이 확정된 상태. 규칙은 이 값이면 target_list가 비어 있을 수 없고(fn_valid_rule_list), 현재 적용 규칙 조회의 대상이 된다. 혜택 단위 검증 완료인 VERIFY_STATUS.CONFIRMED와는 관리 단위가 다르다.
ITEM_STATUS	RETIRED	폐기	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	규칙 또는 조건을 더 이상 사용하지 않기로 폐기한 상태. 문서 개정 등으로 대체되어 사용이 끝난 항목을 이력으로 남길 때 쓴다. 아직 확정 전인 DRAFT와 구분된다.
VERIFY_STATUS	PENDING_REVIEW	검증 대기	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택이 등록되었지만 원문 대조 검증이 끝나지 않은 상태. AI 추출 결과를 정규화할 때 부여하는 초기값이다. 같은 코드값을 쓰는 PREDICATE_STATE, STG_STATUS와 달리 card_bnft 혜택 행의 검증 상태만 나타낸다.
VERIFY_STATUS	CONFIRMED	검증 완료	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택 내용이 원문과 대조되어 검증을 마친 상태. LOCAL 혜택이 이 값인데 규칙이 없으면 게이트 local_confirmed_without_rule에서 검출된다. 규칙·조건 단위의 ITEM_STATUS.CONFIRMED와는 관리 단위가 다르다.
BNFT_TYPE	DISCOUNT	할인	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	결제금액을 현장 또는 청구 단계에서 낮춰 주는 혜택. 놀이공원 현장할인, 청구할인이 해당한다. 원문이 할인으로 정의한 경우에 쓰며, 결제 후 돌려받는 CASHBACK이나 포인트로 쌓이는 POINT와 구분된다.
BNFT_TYPE	CASHBACK	캐시백	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	결제 후 금전으로 돌려주는 혜택. 원문이 캐시백으로 정의한 ONE PICK, 대중교통 캐시백이 해당한다. 결제금액 자체를 낮추는 DISCOUNT, 포인트로 지급하는 POINT와 구분된다.
BNFT_TYPE	POINT	포인트 적립	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	이용금액에 따라 하나머니나 UniMile 같은 포인트·마일리지를 적립해 주는 혜택. 실제 지급 단위는 규칙의 payout_unit_cd에 기록한다. 금전으로 지급하는 CASHBACK과 구분된다.
BNFT_TYPE	FEE_WAIVER	수수료·연회비 면제	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	연회비나 수수료 같은 비용을 면제해 주는 혜택. 결제금액에 대한 보상이 아니라 카드 이용에 드는 비용을 없앤다는 점에서 DISCOUNT와 구분된다.
BNFT_TYPE	SERVICE	서비스 제공	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	공항 라운지, 발렛파킹처럼 금전 보상이 아니라 서비스 이용 자체를 제공하는 혜택. 결제금액을 낮추는 DISCOUNT나 금전·포인트를 지급하는 CASHBACK, POINT와 구분된다.
BNFT_TYPE	INSTALLMENT	무이자 할부	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	할부 이자를 받지 않는 무이자 할부 혜택. 할부 결제 조건을 바꾸는 혜택으로, 수수료·연회비 면제인 FEE_WAIVER와 별도로 분류한다.
BNFT_TYPE	ETC	기타	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	정의된 혜택 유형 어디에도 해당하지 않는 혜택. 추출 단계의 UNKNOWN은 유형을 판단하지 못한 임시값이고 이 코드는 유형을 판단한 결과이므로 구분해서 쓴다.
BNFT_SCOPE	PRODUCT	상품 전체	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	상품의 모든 브랜드 선택지에 적용되는 혜택. 이 값이면 bnft_brand_opt_cds는 NULL이어야 한다(card_bnft_ck_1). 현재 추출기가 부여하는 기본값이다.
BNFT_SCOPE	BRAND	지정 브랜드 선택지	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	bnft_brand_opt_cds에 지정한 브랜드 선택지에만 적용되는 혜택. 지정 선택지가 1개 이상 있어야 하며(card_bnft_ck_1), 같은 상품이라도 브랜드나 서비스 유형에 따라 제공 여부가 달라질 때 쓴다. 코드값이 같은 BRAND 그룹과는 다른 의미다.
RULE_SELECT	EXCLUSIVE_BY_SCOPE	범위가 겹치지 않음	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	규칙들의 적용 범위가 서로 겹치지 않아 한 거래에 하나의 규칙만 해당하는 방식. 전월 실적 40만원 미만 1%, 이상 2%처럼 구간이 배타적인 경우다. 겹침을 해소하는 PRIORITY, MAX_BENEFIT_VALUE와 달리 애초에 겹침이 없음을 뜻한다.
RULE_SELECT	PRIORITY	우선순위 적용	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	규칙이 겹칠 때 rule_priority로 적용 순서를 정하는 방식. 원문에 우선 규칙이 명시된 경우에만 쓰며, 근거가 없으면 임의로 우선순위를 만들지 않는다. 보상 크기로 고르는 MAX_BENEFIT_VALUE와 구분된다.
RULE_SELECT	MAX_BENEFIT_VALUE	보상이 큰 규칙 적용	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	규칙이 겹칠 때 보상이 큰 규칙 하나를 적용하는 방식. 원문이 적립금액이 큰 서비스 우선 적용으로 명시한 경우에 쓴다. 한 혜택 안의 규칙을 고른다는 점에서 혜택 간 관계인 REL_TYPE.HIGHER_VALUE_WINS와 구분된다.
PREDICATE_STATE	CONDITIONAL	조건식 평가 필요	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	조건식을 평가해야 적용 여부가 결정되는 상태. 이 값이면 cond_expr가 반드시 있어야 하며, 없으면 fn_valid_* 검증에서 거부된다.
PREDICATE_STATE	VERIFIED_UNCONDITIONAL	원문 확인된 무조건	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	원문을 확인한 결과 조건 없이 적용되는 상태. 이 값이면 cond_expr가 없어야 한다. 조건식이 비어 있을 때 무조건으로 해석할 수 있는 유일한 값으로, 조건이 아직 파악되지 않은 PENDING_REVIEW와 구분된다.
PREDICATE_STATE	PENDING_REVIEW	검토 대기	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	조건 유무나 조건식의 완전성이 아직 검토되지 않은 상태. 추출 규칙에 조건이 없을 때 부여하는 값이고 cond_expr가 있어도 허용된다. 조건식이 없어도 무조건 적용으로 해석하면 안 된다.
CALC_METHOD	PERCENT_OF_TXN	결제금액 정률	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	결제금액에 고정 비율을 곱해 보상을 산출하는 방식. value_num은 퍼센트 수치이며(1.5는 1.5%) value_unit_cd는 PERCENT를 쓴다. 결제금액과 무관하게 일정액을 주는 FIXED_PER_TXN과 구분된다.
CALC_METHOD	UNITS_PER_AMOUNT	금액당 단위 적립	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	결제금액을 basis_amt 단위로 나누어 단위마다 value_num만큼 적립하는 방식. 1,500원당 45 UniMile이 해당하며 value_num=45, basis_amt=1500으로 저장한다. 비율로 계산하는 PERCENT_OF_TXN과 달리 기준금액 단위로 계산한다.
CALC_METHOD	MULTIPLY_EXTERNAL_POINTS	외부 포인트 배수	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	결제금액이 아니라 외부 제휴사가 적립한 포인트에 배수를 곱해 보상을 산출하는 방식. CJ ONE 적립 포인트의 2배 캐시백이 해당하며 value_num은 배수, value_unit_cd는 MULTIPLIER다. 외부 포인트 값이 없으면 산출할 수 없다.
CALC_METHOD	FREE_SERVICE	무상 서비스 제공	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	결제금액으로 보상을 계산하지 않고 공항 라운지나 발렛파킹 같은 서비스 이용을 무상으로 제공하는 방식. 금액이나 포인트를 산출하는 다른 계산 방법과 구분된다.
PREDICATE_METHOD	EVERY_MONTH_MIN_SPEND	기간 내 매월 최소 실적	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	지정한 기간의 모든 달이 각각 최소 실적을 충족하는지 판정하는 방법. 최근 3개월 매월 10만원 이상처럼 합계가 아니라 월별 충족을 보며, 최소 금액은 cond_min_amt, 기간은 cond_params에 둔다. cond_basis_cd는 ROLLING_MONTHS를 쓴다.
PREDICATE_METHOD	MONTH_IN	지정 월 해당	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	기준 월이 지정한 월 목록에 속하는지 판정하는 방법. 2, 3, 8, 9월에 매입된 거래처럼 금액이 아닌 달력 조건에 쓰며 월 목록과 기준은 cond_params에 둔다.
VALUE_UNIT	PERCENT	퍼센트	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	value_num이 퍼센트 수치임을 나타내는 단위. 5는 5%를 뜻하며 PERCENT_OF_TXN과 함께 쓴다. 고객이 받는 단위는 PAYOUT_UNIT에 별도로 기록한다.
VALUE_UNIT	KRW	원	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	value_num이 원화 금액임을 나타내는 단위. FIXED_PER_TXN의 건당 100원처럼 입력값 자체가 금액인 경우에 쓴다. 지급 단위 PAYOUT_UNIT.KRW, 한도 단위 LIMIT_UNIT.KRW와 코드값만 같고 사용 위치가 다르다.
VALUE_UNIT	UNIMILE	UniMile	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	value_num이 UniMile 수량임을 나타내는 단위. 1,500원당 45 UniMile의 45처럼 입력값이 마일 수량인 경우에 쓴다. 고객이 받는 단위를 나타내는 PAYOUT_UNIT.UNIMILE과 구분된다.
VALUE_UNIT	MULTIPLIER	배수	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	value_num이 곱할 배수임을 나타내는 단위. CJ ONE 포인트 2배의 2처럼 금액이나 비율이 아닌 배수를 저장할 때 쓴다. MULTIPLY_EXTERNAL_POINTS와 함께 쓴다.
PAYOUT_UNIT	KRW	원	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	보상을 원화로 받는 경우. 할인과 캐시백이 해당하며, 계산 입력값이 퍼센트여도 실제 보상이 원이면 이 값을 쓴다.
PAYOUT_UNIT	HANAMONEY	하나머니	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	보상을 하나머니 포인트로 받는 경우. JADE Classic의 특별 적립이 해당한다. 원화로 지급하는 KRW, 마일리지인 UNIMILE과 구분된다.
PAYOUT_UNIT	UNIMILE	UniMile	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	보상을 UniMile로 받는 경우. Mile1 카드의 마일리지 적립이 해당한다. 원문의 1,500원당 45 UniMile은 UNITS_PER_AMOUNT 규칙으로 표현한다.
PAYOUT_UNIT	WALLET_POINT	월렛 포인트	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	보상을 월렛 포인트로 받는 경우. Visa 브랜드 서비스의 Booking.com 월렛포인트 캐시백이 해당한다. 원화나 하나머니가 아닌 별도 포인트로 지급될 때 쓴다.
PAYOUT_UNIT	SERVICE	서비스 제공	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	보상이 금전이나 포인트가 아니라 서비스 이용 자체로 제공되는 경우. 공항 라운지, 발렛파킹처럼 지급 수량으로 환산하지 않는 혜택에 쓴다.
LIMIT_SCOPE	BENEFIT	혜택 단일	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택 하나의 규칙만 소비하는 한도. 같은 혜택 안의 두 규칙이 같은 풀을 써도 다른 혜택과는 공유하지 않는다. 현재 추출기는 원문에 공유 표현이 없으면 이 값을 부여한다.
LIMIT_SCOPE	BENEFIT_GROUP	혜택군 통합	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	원문이 여러 혜택의 공유를 명시해 묶어 누적하는 한도. 추출기는 공유 표현 shared_scope_txt가 있을 때 이 값을 부여하며, 금액이 같다는 이유만으로 공유로 판단하지 않는다.
LIMIT_SCOPE	AREA	서비스 영역	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	쇼핑, 교통처럼 특정 서비스 영역 안의 혜택이 함께 소비하는 한도. 달달 체크카드의 영역별 2천, 4천, 6천원 한도가 해당한다. 모든 영역을 합치는 CARD와 달리 영역마다 별도의 풀이다.
LIMIT_SCOPE	CARD	카드 전체 통합	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	카드의 모든 서비스 영역을 합쳐 누적하는 통합 한도. 달달 체크카드의 월 통합 1만, 2만, 3만원 한도가 해당한다. 영역 한도와 함께 있으면 한 결제가 두 풀을 모두 소비한다.
LIMIT_PERIOD	TXN	건당	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	결제 1건마다 적용되는 한도. 기간 동안 누적되지 않고 건별로 판단한다는 점에서 DAY, MONTH, YEAR와 구분된다.
LIMIT_PERIOD	DAY	일	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	하루 단위로 누적하는 한도. ONE PICK의 일 1회 제공이 해당한다. 월 한도와 동시에 걸리면 별도의 풀로 둔다.
LIMIT_PERIOD	MONTH	월	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	한 달 단위로 누적하는 한도. ONE PICK의 월 30회, 월 5천원이 해당하며 전월 실적에 따라 구간별로 금액이 달라지는 한도도 이 기간을 쓴다.
LIMIT_PERIOD	YEAR	연	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	1년 단위로 누적하는 한도. 놀이공원의 연 2회 제공이 해당한다. 월 1회처럼 다른 기간의 한도와 동시에 걸리면 별도의 풀로 둔다.
LIMIT_UNIT	KRW	원	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	한도를 원화 금액으로 관리하는 단위. 월 5천원, 월 통합 10만원이 해당한다. 혜택 제공 횟수를 세는 COUNT와 구분된다.
LIMIT_UNIT	HANAMONEY	하나머니	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	한도를 하나머니 적립량으로 관리하는 단위. JADE Classic의 월 통합 10만 하나머니가 해당한다. 원화로 환산하지 않고 원문의 단위대로 저장한다.
LIMIT_UNIT	COUNT	횟수	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	한도를 혜택 제공 횟수로 관리하는 단위. 일 1회, 월 30회, 연 2회가 해당한다. limit_num이 금액이 아니라 횟수이며 금액 한도와는 별도의 풀로 둔다.
LIMIT_AGG	CARD_MEMBER	회원 카드 단위(가족카드 합산)	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	회원의 카드 단위로 누적하면서 가족카드 사용분을 합산하는 기준. 원문의 본인카드와 가족카드의 실적 및 적립/할인한도는 합산이 해당한다. 현재 추출기가 일괄 입력하는 기본값이므로 이 값이 있다고 해당 상품의 원문이 확인된 것은 아니다.
POOL_ROLE	CONSUME	해당 규칙군 한도 소비	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	규칙이 자기 규칙군에 속한 한도 풀을 소비하는 역할. 달달 체크카드의 쇼핑 규칙이 쇼핑 영역 한도를 쓰는 경우다. 현재 추출기는 규칙의 한도 참조를 모두 이 값으로 만든다.
POOL_ROLE	SHARED	카드 통합 한도 동시 소비	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	규칙이 자기 규칙군의 한도와 함께 카드 통합 한도도 동시에 소비하는 역할. 달달 체크카드의 규칙이 쇼핑 영역 풀(CONSUME)과 모든 영역 통합 풀(SHARED)을 함께 소비하는 경우다.
REL_TYPE	MUTUALLY_EXCLUSIVE	상호 배타(양방향)	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	두 혜택을 한 거래에 함께 제공하지 않는 관계. 원문의 특별 적립과 기본 적립은 중복 제공되지 않음이 해당한다. 방향이 없어 한쪽 혜택에만 저장하고 v_card_bnft_rel이 양방향으로 복원하며, 양쪽에 저장하면 게이트 rel_mutual_stored_twice에서 검출된다.
REL_TYPE	HIGHER_VALUE_WINS	보상이 큰 혜택 우선	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	여러 혜택이 해당할 때 보상이 큰 혜택을 적용하는 관계. 원문의 적립 대상이 중복되면 적립률이 높은 서비스가 우선 적용이 해당한다. 혜택 사이의 관계라는 점에서 한 혜택 안의 RULE_SELECT.MAX_BENEFIT_VALUE와 구분된다.
REL_TYPE	FALLBACK_AFTER_CAP	한도 소진 후 대체	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	시작 혜택의 한도를 소진한 뒤 추가 거래에 대상 혜택을 적용하는 관계. 원문의 월 적립 한도 소진 후 발생하는 추가 매출은 기본적립 제공이 해당한다. 어느 한도의 소진인지 trigger_pool_id가 필수이고, 대체 순환은 게이트 rel_fallback_cycle에서 검출된다.
COND_TYPE	SPEND_REQ	실적 요건	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	금액 기준을 충족해야 하는 실적 요건. 지난달 실적 10만원 이상, 결제 건당 3천원 이상이 해당하며 cond_basis_cd가 필수다. 규칙의 건당 최소 금액도 추출기가 TXN_AMT 기준의 이 유형으로 만든다.
COND_TYPE	SPEND_EXCL	실적 산정 제외	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	특정 이용금액을 실적 산정에서 제외하는 조건. 국세, 공과금 등 실적 제외 항목이 해당하며 card_excl_item_id나 excl_raw_txt가 필수다. 혜택 제공에서 빼는 BNFT_EXCL과 같은 항목을 다뤄도 별도 조건으로 저장한다.
COND_TYPE	BNFT_EXCL	혜택 적용 제외	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	특정 거래나 상황을 혜택 제공에서 제외하는 조건. 상품권 구매 제외, 시외버스 제외, 최초 발급 월 미제공이 해당하며 card_excl_item_id나 excl_raw_txt가 필수다. 실적 계산에서 빼는 SPEND_EXCL과 구분된다.
COND_TYPE	USAGE_REQ	이용 요건	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택을 받기 위해 거래나 이용 행위가 갖춰야 하는 이용 요건. 설계상 건당 이용 요건과 자동이체 이용처럼 실적 구간이 아닌 이용 행위에 걸린 조건을 담는다. 금액 기준 요건을 나타내는 SPEND_REQ와 구분된다.
COND_TYPE	PAYMENT_METHOD	결제 방식	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	결제가 이루어지는 방식이나 경로에 걸린 조건. 대상 가맹점의 공식 홈페이지와 오프라인 결제 시에만 제공되고 배달 앱 결제는 해당하지 않는 경우가 이에 속한다. 가맹점 분류 기준인 MERCHANT_RULE과 구분된다.
COND_TYPE	GRACE	유예	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	요건을 일시적으로 완화해 미충족이어도 혜택을 제공하는 유예 조건. 최초 카드 사용 등록일부터 다음 달 말일까지 실적 10만원 미만이어도 서비스를 제공하는 경우다. 제공을 막는 제한은 유예가 아니므로 BNFT_EXCL로 표현한다.
COND_TYPE	ETC	기타	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	정의된 조건 유형에 해당하지 않아 원문으로 보존하는 조건. 놀이공원의 1인 1매가 해당하며 정형 판정이 아니라 cond_raw_txt로 내용을 유지한다. 추출 단계의 UNKNOWN과 달리 유형을 판단한 결과다.
COND_BASIS	PREV_MONTH_SPEND	전월 실적	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	전월 실적을 비교 기준으로 쓰는 값. 원문의 지난달 1일부터 말일까지 이용금액이 해당한다. v_card_rule의 실적 구간은 이 기준의 금액을 추출한다.
COND_BASIS	PREV_YEAR_SPEND	직전 1년 실적	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	직전 1년의 실적을 비교 기준으로 쓰는 값. 1개월 기준인 PREV_MONTH_SPEND, 월별로 각각 판정하는 ROLLING_MONTHS와 달리 1년 동안의 실적을 하나의 금액으로 본다.
COND_BASIS	TXN_AMT	건당 금액	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	결제 1건의 금액을 비교 기준으로 쓰는 값. 결제 건당 3천원 이상, 1만원 이상이 해당한다. 기간 누적이 아니라 거래별로 판정한다는 점에서 실적 기준 코드들과 구분된다.
COND_BASIS	MONTH_USAGE	당월 이용금액	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택 판정이 이루어지는 달의 이용금액을 비교 기준으로 쓰는 값. 원문의 이번달 합산 이용금액 10만원 이상이 해당한다. 지난달 기준인 PREV_MONTH_SPEND와 구분된다.
COND_BASIS	ROLLING_MONTHS	최근 N개월 각 월	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	최근 N개월의 각 월 실적을 비교 기준으로 쓰는 값. 합계가 아니라 월별로 각각 판정하며 최근 3개월 매월 10만원 이상이 해당한다. PREDICATE_METHOD.EVERY_MONTH_MIN_SPEND와 함께 쓴다.
TARGET_TYPE	MERCHANT	가맹점	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택 대상이 특정 가맹점이나 브랜드인 경우. CU, GS25, 에버랜드처럼 대상의 이름을 지정할 수 있을 때 쓴다. 범주 전체를 가리키는 INDUSTRY와 구분된다.
TARGET_TYPE	INDUSTRY	업종	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택 대상이 개별 가맹점이 아니라 업종 전체인 경우. 원문이 가맹점 이름 대신 업종 범주로 대상을 정의할 때 쓰며 MERCHANT와 구분된다.
TARGET_TYPE	CHANNEL	결제 채널·지역	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택 대상이 결제 채널이나 지역 범위로 정해지는 경우. 토스뱅크 Wide의 국내/해외 가맹점처럼 특정 가맹점을 나열하지 않고 범위 전체를 대상으로 할 때 쓴다.
TARGET_TYPE	SERVICE	제공 서비스	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택 대상이 가맹점이 아니라 이용하는 서비스 자체인 경우. ONE MORE 대중교통의 버스, 지하철이 해당한다.
BRAND	VISA	Visa	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	Visa 브랜드 선택지 또는 Visa가 제공하는 공통 서비스. Visa Platinum, Signature, Infinite 등급의 브랜드 서비스 안내서가 있다.
BRAND	MASTERCARD	Mastercard	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	Mastercard 브랜드 선택지 또는 Mastercard가 제공하는 공통 서비스. Platinum, World 등급의 브랜드 서비스 안내서가 있다.
BRAND	AMEX	American Express	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	American Express 브랜드 선택지 또는 AMEX가 제공하는 공통 서비스. Platinum, Platinum Elite 등급의 브랜드 서비스 안내서가 있다.
BRAND	JCB	JCB	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	JCB 브랜드 선택지 또는 JCB가 제공하는 공통 서비스. 수집 문서에는 JCB 브랜드 서비스 안내서 JP002가 있다.
BRAND	UPI	UnionPay	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	UnionPay 브랜드 선택지 또는 UnionPay가 제공하는 공통 서비스. 원문에는 UnionPay, UPI, 유니온페이로 표기되며 Platinum, Diamond 등급의 안내서가 있다.
BRAND	LOCAL	국내전용	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	국제 브랜드 없이 국내에서 이용하는 국내전용 선택지. 원문의 국내전용(Local) 발급 구분이 해당한다. 코드값은 같지만 혜택 출처 BNFT_ORIGIN.LOCAL과는 무관하다.
SERVICE_GRADE	PLATINUM	Platinum	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	브랜드 서비스의 Platinum 등급. Visa, Mastercard, AMEX, UnionPay 안내서에서 사용되며 브랜드마다 서비스 내용이 다르므로 BRAND와 함께 해석한다.
SERVICE_GRADE	PLATINUM_ELITE	Platinum Elite	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AMEX 브랜드 서비스의 Platinum Elite 등급. 안내서 AE001이 해당하며 AMEX Platinum 등급과는 별도의 공통·선택서비스를 가진다.
SERVICE_GRADE	SIGNATURE	Signature	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	Visa 브랜드 서비스의 Signature 등급. 안내서 VS002가 해당한다.
SERVICE_GRADE	WORLD	World	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	Mastercard 브랜드 서비스의 World 등급. 안내서 MW002, MW003이 해당한다.
SERVICE_GRADE	INFINITE	Infinite	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	Visa 브랜드 서비스의 Infinite 등급. 안내서 VI001이 해당하며 Signature와는 별도의 공통·선택서비스를 가진다.
SERVICE_GRADE	DIAMOND	Diamond	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	UnionPay 브랜드 서비스의 Diamond 등급. 안내서 UD001, UD002가 해당하며 UnionPay Platinum과는 별도의 서비스를 가진다.
SERVICE_TYPE	COMMON	등급 공통	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	해당 등급의 카드 소지자에게 공통으로 제공되는 서비스. 안내서의 공통서비스 항목이 해당하며, 대상 카드에 따라 달라지는 번호 유형과 구분된다.
SERVICE_TYPE	01	선택서비스 01	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	브랜드·등급별 선택서비스의 01 유형. Visa Platinum 01 선택서비스가 해당한다. 번호는 브랜드·등급과 조합해야 의미가 정해지며 대상 카드는 안내서의 대상카드 표를 따른다.
SERVICE_TYPE	02	선택서비스 02	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	브랜드·등급별 선택서비스의 02 유형. Mastercard World 02, Visa Signature 02 선택서비스가 해당하며 Mastercard World 02의 대상카드에는 CLUB Leaders 계열이 있다.
SERVICE_TYPE	03	선택서비스 03	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	브랜드·등급별 선택서비스의 03 유형. Mastercard World 03 선택서비스가 해당하며 JADE Classic이 대상카드다. 같은 번호라도 브랜드와 등급이 다르면 다른 서비스 묶음이다.
SERVICE_TYPE	04	선택서비스 04	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	브랜드·등급별 선택서비스의 04 유형. Mastercard 안내서 MP004의 상품유형 Mastercard World Platinum04가 해당한다.
EV_SUBJECT	BNFT	혜택	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	근거가 혜택 하나를 뒷받침하는 경우. card_bnft_id가 필수이고 규칙, 관계, 풀 컬럼은 비운다. 규칙 수준의 근거는 RULE을 쓴다.
EV_SUBJECT	RULE	계산 규칙	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	근거가 혜택 안의 계산 규칙을 뒷받침하는 경우. card_bnft_id와 rule_key가 필수다. rule_key가 바뀌면 근거 연결이 끊어지므로 게이트 evidence_subject_orphan으로 검증한다.
EV_SUBJECT	POOL	한도 풀	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	근거가 한도 풀을 뒷받침하는 경우. pool_id가 필수이고 혜택, 규칙, 관계 컬럼은 비운다. 여러 혜택이 공유할 수 있는 한도라서 혜택 대신 풀에 연결한다.
EV_SUBJECT	REL	혜택 관계	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	근거가 혜택 간 관계를 뒷받침하는 경우. card_bnft_id와 relation_key가 필수다. 배타, 우선, 대체 같은 관계의 원문 문장을 연결할 때 쓴다.
EV_ITEM	SELF	대상 전체	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	근거가 대상 전체를 가리키는 경우. 기본값이며 이 값일 때만 ev_item_key가 하이픈(-)이다. 대상 안의 특정 항목을 가리키는 다른 코드와 구분된다.
DOC_TYPE	PRODUCT_GUIDE	상품설명서	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	개별 카드 상품의 혜택과 유의사항을 설명하는 상품설명서. card_doc의 기본값이며 혜택 추출의 주 원천이다.
DOC_TYPE	TERMS	약관	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	카드 이용 조건을 규정하는 약관 문서. 신용카드 개인회원 표준약관, 체크카드 개인회원 약관이 해당한다. 상품과의 관계에서는 DOC_ROLE.COMMON_TERMS로 연결한다.
DOC_TYPE	ETC	기타	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	상품설명서, 약관, 브랜드 서비스 안내에 해당하지 않는 문서. 정의된 유형 밖의 자료에 쓰며, DOC_ROLE의 기타 코드는 OTHER로 값이 다르다.
DOC_STATUS	ACTIVE	사용 중	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	문서를 파이프라인에서 사용 중인 상태. 기본값이며 AI 입력은 이 상태의 문서만 대상이다. 문서가 사용 가능하다는 뜻일 뿐 특정 상품에 현재 적용된다는 뜻은 아니다.
DOC_STATUS	SUPERSEDED	대체됨	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	같은 문서 계열의 새 판으로 대체된 상태. 문서 행은 남아 있지만 AI 입력 대상에서는 빠진다. 문서 자체를 쓰지 않기로 한 EXCLUDED와 구분된다.
DOC_STATUS	EXCLUDED	제외	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	문서를 파이프라인 처리 대상에서 제외한 상태. 판이 바뀐 SUPERSEDED와 달리 문서 자체를 쓰지 않기로 한 경우다. 페이지·청크 단위 제외는 CHUNK_STATUS.EXCLUDED가 맡는다.
PAGE_LAYER	TEXT	텍스트	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	추출된 텍스트가 있고 이미지 같은 시각 요소가 없는 페이지. 프로그램이 텍스트만으로 페이지 내용을 읽을 수 있다고 판정한 경우다.
PAGE_LAYER	IMAGE	이미지	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	추출된 텍스트가 없고 시각 요소만 있는 페이지. 스캔본처럼 내용이 이미지에 있어 OCR 등 별도 처리가 필요하다.
PAGE_LAYER	MIXED	혼합	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	추출된 텍스트와 시각 요소가 함께 있는 페이지. 표가 이미지로 들어 있으면 그 안의 글자는 텍스트로 추출되지 않았을 수 있어 TEXT와 구분한다.
PAGE_LAYER	UNKNOWN	미확인	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	추출된 텍스트도 시각 요소도 확인되지 않은 페이지. card_doc_page의 기본값이며 페이지 내용을 판정할 수 없는 경우다.
CHUNK_TYPE	BODY	본문	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	본문 성격의 청크. card_doc_chunk의 기본값이며 현재 프로그램은 페이지 전체 청크를 모두 이 값으로 등록한다.
CHUNK_TYPE	TABLE	표	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	표 내용이 중심인 청크. 혜택과 한도가 행과 열로 정리된 부분을 본문과 구분해 다룰 때 쓴다.
CHUNK_TYPE	NOTICE	유의사항	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	유의사항이 중심인 청크. 혜택 표와 떨어져 있는 제외 조건과 안내 문구를 구분할 때 쓴다.
CHUNK_TYPE	HEADER_FOOTER	머리말·꼬리말	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	페이지 머리말·꼬리말 청크. 페이지마다 반복되는 문구처럼 혜택 내용이 아닌 부분을 구분할 때 쓴다.
CHUNK_TYPE	ETC	기타	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	본문, 표, 유의사항, 머리말·꼬리말에 해당하지 않는 청크.
CHUNK_STATUS	RAW	분리 완료	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	문서에서 분리만 된 청크. 정제 전 상태이며 기본값이다. CLEANED와 함께 AI 입력 대상이다.
CHUNK_STATUS	CLEANED	정제 완료	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	정제가 끝난 청크. 이 값이면 chunk_clean_txt와 chunk_clean_rule_ver가 필수다(card_doc_chunk_check1). RAW와 함께 AI 입력 대상이다.
CHUNK_STATUS	EXCLUDED	추출 제외	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 추출 대상에서 제외한 청크. OCR 검토 대상 페이지의 청크가 여기에 해당하며 검토를 통과하면 RAW로 되돌린다. 문서 전체의 제외인 DOC_STATUS.EXCLUDED와 구분된다.
RUN_STAGE	EXTRACT	추출	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	문서에서 혜택과 조건을 추출하는 단계의 실행. 현재 추출 파이프라인이 등록하는 값이며 결과는 card_ai_call과 card_extr_stg에 남는다.
RUN_STAGE	VERIFY	의미 검증	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	추출된 항목의 의미를 AI로 검증하는 단계의 실행. 결과는 stg_ai_vrfy_cd와 stg_ai_vrfy_card_ai_run_id에 기록하며, 추출과 다른 실행 이력으로 남긴다.
RUN_CALL_METHOD	PYTHON_RELAY	Python 중계	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	Python 프로그램이 LLM 호출을 중계하는 방식. 현재 추출 파이프라인의 실행 이력에 고정으로 기록되는 값이다.
RUN_CALL_METHOD	PGAI	pgai	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	pgai 등 PostgreSQL 확장으로 DB에서 AI를 호출하는 방식. 아키텍처 문서의 호출 방식 후보로, 현재 프로그램은 이 방식을 사용하지 않는다.
RUN_CALL_METHOD	EDGE_FUNCTION	Edge Function	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	Supabase Edge Functions로 AI를 호출하는 방식. 아키텍처 문서의 호출 방식 후보로, 현재 프로그램은 이 방식을 사용하지 않는다.
RUN_CALL_METHOD	ETC	기타	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	Python 중계, pgai, Edge Functions에 해당하지 않는 AI 호출 방식.
RUN_STATUS	RUNNING	실행 중	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	실행이 시작되어 아직 끝나지 않은 상태. 기본값이며 정상 종료나 오류 시 다른 값으로 바뀐다. 오래 남아 있으면 비정상 중단을 의심한다.
RUN_STATUS	SUCCEEDED	성공	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	대상 페이지를 모두 처리하고 문서 통합 저장까지 끝났으며 AI 입력에서 제외된 페이지도 없는 실행.
RUN_STATUS	PARTIAL	일부 실패	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	일부 결과는 있지만 완전하지 않은 실행. 실패한 페이지나 AI 입력 제외 페이지가 있거나 문서 통합 저장이 실패한 경우다. 실패 페이지가 있으면 문서 통합을 하지 않는다.
RUN_STATUS	FAILED	실패	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	성공한 페이지가 없거나 처리 중 오류로 중단된 실행. 일부 결과가 남는 PARTIAL과 구분된다.
CALL_STATUS	SUCCEEDED	성공	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 응답을 받아 JSON 구조 해석과 페이지 번호 검증을 통과한 호출. call_resp_json이 필수다. 호출이 성공했다는 뜻이며 추출 내용이 맞다는 뜻은 아니다.
CALL_STATUS	FAILED	호출 실패	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 호출 자체가 실패해 응답을 받지 못한 경우. 오류 유형을 call_error_msg에 남긴다. 응답은 받았지만 해석하지 못한 PARSE_ERROR와 구분된다.
CALL_STATUS	PARSE_ERROR	JSON 파싱 실패	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	응답은 받았지만 요구한 구조로 해석하지 못하거나 페이지 번호가 일치하지 않는 경우. 재검토를 위해 응답 원문을 call_resp_raw에 보존한다.
STG_KIND	BENEFIT	혜택	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택 1건을 담는 추출 항목. 문서 통합 결과가 stg_normalized_item에 V6 혜택 구조로 저장된다.
STG_KIND	CONDITION	조건	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	조건 1건을 담는 추출 항목. stg_parent_card_extr_stg_id로 조건이 걸린 혜택 항목을 가리키고, 값이 NULL이면 카드 전체 조건이다.
STG_STATUS	PENDING_REVIEW	검토 대기	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	추출 항목이 저장되었지만 검토가 끝나지 않은 상태. 기본값이다. 승인 전이므로 업무 데이터의 근거로 확정해서는 안 된다.
STG_STATUS	AUTO_APPROVED	자동 승인	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	사람의 개별 검토 없이 자동 기준으로 승인된 상태. stg_sql_check_cd가 OK이고 정제 항목, 근거 문장, 근거 위치가 모두 있어야 한다(card_extr_stg_check1).
STG_STATUS	MANUAL_APPROVED	수동 승인	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	사람이 검토해 승인한 상태. AUTO_APPROVED와 같은 CHECK 요건을 지켜야 하며, 의미가 모호해 자동 승인이 어려운 항목을 처리할 때 쓴다.
STG_STATUS	REJECTED	반려	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	검토 결과 업무 데이터로 쓰지 않기로 거부한 추출 항목. 관계·근거의 반려 APPROVAL_STATUS.REJECTED와 달리 AI 추출 항목에 대한 판정이다.
STG_AI_VRFY	MATCH	일치	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 의미 검증에서 추출 항목이 원문 의미와 일치한다고 판정한 결과. 최종 승인이 아니라 승인 판단의 참고 정보다.
STG_AI_VRFY	MISMATCH	불일치	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 의미 검증에서 추출 항목이 원문 의미와 다르다고 판정한 결과. 판정이 불가능한 UNCERTAIN과 달리 불일치를 명시적으로 판단한 경우다.
STG_AI_VRFY	UNCERTAIN	불확실	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 의미 검증에서 일치 여부를 판정하지 못한 결과. 사람의 검토가 필요하며, 검증을 실행하지 않은 NULL과 구분된다.
\.


--
-- TOC entry 4373 (class 0 OID 20647)
-- Dependencies: 356
-- Data for Name: common_code_grp; Type: TABLE DATA; Schema: db_pipeline; Owner: -
--

COPY db_pipeline.common_code_grp (common_code_grp_id, common_code_grp_nm, create_date, create_user_id, update_date, update_user_id, common_code_grp_desc) FROM stdin;
APPROVAL_STATUS	관계·근거 승인 상태	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	문서 연결과 원문 근거처럼 검토·승인이 필요한 관계·근거 데이터의 처리 상태를 구분하는 공통코드. card_product_doc.approval_status_cd, card_source_evidence.approval_status_cd에서 사용하며 실제 승인 대상은 사용하는 테이블에 따라 달라진다. 규칙·조건을 다루는 ITEM_STATUS, AI 추출 항목을 다루는 STG_STATUS와 관리 대상이 다르다.
PRODUCT_STATUS	상품·브랜드 선택지 상태	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	카드 상품과 상품 안의 브랜드 선택지가 현재 판매되는지를 구분하는 공통코드. card_product.product_status_cd와 card_product.brand_opt_list[].brand_opt_status_cd에서 사용한다. 데이터 처리 상태가 아니라 판매 사실을 나타낸다는 점에서 문서 상태 DOC_STATUS의 같은 값 ACTIVE와 구분된다.
DOC_ROLE	상품·정책에서 문서 역할	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	원천 문서가 특정 상품에서 어떤 역할을 하는지 구분하는 공통코드. card_product_doc.doc_role_cd에서 사용한다. 문서 자체의 종류를 나타내는 DOC_TYPE과 달리 상품과의 관계에 붙는 값이므로 같은 문서라도 연결 상품에 따라 역할을 따로 기록한다.
ITEM_STATUS	규칙·조건 상태	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	계산 규칙, 조건식, 카드 공통 조건이 작성 중인지 확정되었는지를 구분하는 공통코드. JSONB 안의 rule_status_cd, cond_status_cd, expr_status_cd와 card_product.card_cond_status_cd에서 사용한다. 혜택 단위 검증을 나타내는 VERIFY_STATUS보다 작은 규칙·조건 단위의 상태다.
COND_TYPE	조건 유형	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	조건식 atom의 업무 유형을 분류하는 공통코드. 조건식 atom의 cond_type_cd에서 사용하고 카드 공통, 혜택, 규칙, 한도 구간의 조건에 모두 적용된다. 금액을 어떤 기준으로 비교하는지는 COND_BASIS가, 금액 구간으로 표현되지 않는 판정법은 PREDICATE_METHOD가 맡는다.
CARD_KIND	카드 구분	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	카드 상품의 결제 성격을 신용카드와 체크카드로 구분하는 공통코드. card_product.card_kind_cd에서 사용하며 상품 조회와 필터의 기준이 된다. 상품의 판매 상태를 나타내는 PRODUCT_STATUS, 국제 브랜드를 나타내는 BRAND와는 별개의 축이다.
EV_SUBJECT	근거 대상 유형	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	원문 근거가 어떤 카드 대상을 뒷받침하는지 구분하는 공통코드. card_evidence_link.ev_subject_cd에서 사용하며 값에 따라 card_bnft_id, rule_key, relation_key, pool_id 중 채워야 할 컬럼이 CHECK로 고정된다. 대상 안의 세부 항목은 EV_ITEM이 구분한다.
EV_ITEM	근거 대상 내 항목	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	근거가 대상 전체를 가리키는지 대상 안의 JSONB 항목을 가리키는지 구분하는 공통코드. card_evidence_link.ev_item_cd에서 사용하고 ev_item_key와 짝을 이룬다. 대상의 종류를 나타내는 EV_SUBJECT보다 한 단계 아래를 가리킨다.
DOC_STATUS	원천 문서 상태	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	수집된 원천 문서를 파이프라인에서 사용할지 구분하는 공통코드. card_doc.doc_status에서 사용하며 AI 입력 대상은 ACTIVE 문서로 제한된다. 상품별 적용 여부는 이 값이 아니라 승인된 문서 관계로 판정하며, 판매 상태를 나타내는 PRODUCT_STATUS와도 구분된다.
BNFT_ORIGIN	혜택 출처	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	혜택의 원천을 구분하는 공통코드. card_bnft.bnft_origin_cd에서 사용한다. 출처와 관계없이 계산 규칙은 모두 card_bnft.rule_list에 있으며, 혜택이 어느 브랜드 선택지에 적용되는지를 나타내는 BNFT_SCOPE와는 별개의 축이다.
PREDICATE_STATE	조건 판정 상태	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	규칙이나 한도 구간의 적용 여부를 조건식으로 어떻게 판정할지 구분하는 공통코드. card_bnft.rule_list[].predicate_state_cd와 card_limit_pool.tier_list[].predicate_state_cd에서 사용한다. 조건식이 없다는 사실만으로 무조건 적용으로 해석하지 않도록, 원문으로 확인된 무조건과 미검토를 구분한다.
LIMIT_PERIOD	한도 기간	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	한도가 누적되는 시간 단위를 구분하는 공통코드. card_limit_pool.period_cd에서 사용한다. 한도를 묶는 혜택 범위인 LIMIT_SCOPE, 한도의 단위인 LIMIT_UNIT과 함께 한도 하나를 정의한다.
LIMIT_UNIT	한도 단위	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	한도 수치 limit_num이 어떤 단위인지 구분하는 공통코드. card_limit_pool.cap_unit_cd에서 사용한다. 보상 지급 단위인 PAYOUT_UNIT과 달리 금액뿐 아니라 이용 횟수도 포함한다.
LIMIT_AGG	한도 집계 기준	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	한도 사용액을 어떤 주체 단위로 합산할지 구분하는 공통코드. card_limit_pool.aggregation_key_cd에서 사용한다. 어떤 혜택을 묶는지를 나타내는 LIMIT_SCOPE와 달리 누구의 사용분을 합칠지를 나타낸다.
BRAND	국제 브랜드	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	카드 상품의 브랜드 선택지를 구분하는 공통코드. card_product.brand_opt_list[].brand_cd에서 사용한다. 그룹명은 국제 브랜드이지만 국내전용 선택지를 함께 포함하며, 브랜드 안의 등급은 SERVICE_GRADE, 선택서비스 유형은 SERVICE_TYPE이 구분한다.
SERVICE_GRADE	브랜드 서비스 등급	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	국제 브랜드 서비스의 등급을 구분하는 공통코드. card_product.brand_opt_list[].service_grade_cd에서 사용한다. BRAND와 조합해야 의미가 정해지며, 등급 안의 공통·선택서비스 구분은 SERVICE_TYPE이 맡는다.
SERVICE_TYPE	브랜드 서비스 유형	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	같은 브랜드와 등급 안에서 제공되는 서비스 묶음의 유형을 구분하는 공통코드. card_product.brand_opt_list[].service_type_cd에서 사용한다. 번호 코드는 BRAND, SERVICE_GRADE와 조합할 때만 의미가 정해지며 어떤 상품이 어떤 유형인지는 브랜드 서비스 안내서의 대상카드 표를 따른다.
CALC_METHOD	계산 방법	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	규칙이 한 거래의 후보 보상을 어떤 방식으로 산출하는지 구분하는 공통코드. rule_list[].calc_method_cd에서 사용하고, 코드별 value_num의 의미가 정해져 있다. 조건 판정 방법인 PREDICATE_METHOD와 구분된다. 규칙의 method_ver는 표현 계약 버전으로 현재 1이며 계산 실행 엔진의 버전을 뜻하지 않는다.
VERIFY_STATUS	혜택 검증 상태	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택 내용이 원문과 대조되어 검증되었는지를 구분하는 공통코드. card_bnft.verification_status_cd에서 사용한다. 혜택 1건 단위의 검증 여부만 나타내며, 그 안의 규칙·조건 확정은 ITEM_STATUS, AI 추출 단계의 승인은 STG_STATUS가 맡는다.
BNFT_TYPE	혜택 유형	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택이 고객에게 제공되는 형태를 분류하는 공통코드. card_bnft.bnft_type_cd에서 사용하며 AI 추출 스키마의 혜택 유형 값도 이 그룹을 따른다. 보상 계산법을 나타내는 CALC_METHOD나 지급 단위를 나타내는 PAYOUT_UNIT과 달리 혜택의 업무상 종류를 나타낸다.
BNFT_SCOPE	혜택 적용 범위	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	혜택이 상품 전체에 적용되는지 일부 브랜드 선택지에만 적용되는지를 구분하는 공통코드. card_bnft.bnft_scope_cd에서 사용하며 bnft_brand_opt_cds의 필수 여부를 결정한다. 규칙의 출처를 나타내는 BNFT_ORIGIN과 달리 혜택을 받을 수 있는 상품 선택지의 범위를 나타낸다.
RULE_SELECT	혜택 내 규칙 선택 방식	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	한 혜택 안에서 같은 거래에 여러 계산 규칙이 해당할 때 어떤 규칙을 적용할지 정하는 공통코드. card_bnft.rule_select_cd에서 사용하고, 값이 NULL이면 선택 방식이 아직 확정되지 않은 상태다. 혜택과 혜택 사이의 관계를 다루는 REL_TYPE과 달리 한 혜택 내부의 규칙 선택만 다룬다.
VALUE_UNIT	계산값 단위	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	계산 규칙의 입력값 value_num이 어떤 단위인지 구분하는 공통코드. rule_list[].value_unit_cd에서 사용한다. 고객이 실제로 받는 단위를 나타내는 PAYOUT_UNIT, 한도의 단위를 나타내는 LIMIT_UNIT과 구분되며, 예를 들어 값은 PERCENT이고 보상은 KRW일 수 있다.
PAYOUT_UNIT	보상 단위	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	고객이 혜택으로 실제 받는 보상의 단위를 구분하는 공통코드. rule_list[].payout_unit_cd에서 사용한다. 계산 입력값의 단위인 VALUE_UNIT, 누적 한도의 단위인 LIMIT_UNIT과 구분된다.
LIMIT_SCOPE	한도 범위	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	한도 풀이 어느 범위의 혜택을 묶어 누적하는지 구분하는 공통코드. card_limit_pool.pool_scope_cd에서 사용한다. 한도의 시간 범위인 LIMIT_PERIOD, 누적 주체인 LIMIT_AGG와 구분되며, 같은 금액의 한도라도 범위가 다르면 다른 풀이다.
REL_TYPE	혜택 간 관계	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	서로 다른 혜택 사이의 적용 관계를 구분하는 공통코드. card_bnft.relation_list[].rel_type_cd에서 사용하며 v_card_bnft_rel로 조회한다. 한 혜택 내부의 규칙 선택을 다루는 RULE_SELECT와 달리 혜택 간 배타, 우선, 대체를 다룬다.
POOL_ROLE	규칙에서 한도 역할	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	계산 규칙이 연결된 한도 풀을 어떤 역할로 소비하는지 구분하는 공통코드. card_bnft_rule_pool.pool_role_cd에서 사용한다. 한 규칙이 영역 한도와 카드 통합 한도를 동시에 소비하는 구조를 표현하기 위한 값이며, 풀 자체의 범위는 LIMIT_SCOPE가 정한다.
COND_BASIS	조건 금액 기준	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	조건의 금액 구간이 어떤 금액을 기준으로 비교되는지 구분하는 공통코드. 조건식 atom의 cond_basis_cd에서 사용하며, 실적 요건 SPEND_REQ에서는 필수다. 조건의 유형을 나타내는 COND_TYPE과 달리 비교 대상 금액의 정의만 나타낸다.
TARGET_TYPE	혜택 대상 유형	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	계산 규칙의 혜택 대상이 어떤 종류인지 구분하는 공통코드. rule_list[].target_list[].target_type_cd에서 사용하고 AI 추출 스키마의 대상 유형도 이 그룹을 따른다. 대상별 비율은 두지 않으며, 비율이 다르면 규칙을 나눈다.
DOC_TYPE	원천 문서 유형	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	원천 문서 자체의 종류를 구분하는 공통코드. card_doc.doc_type_cd에서 사용한다. 상품·정책과의 관계에서 부여되는 DOC_ROLE과 달리 문서 파일의 성격을 나타내며, 현재 문서 등록 프로그램은 상품설명서를 등록한다.
PAGE_LAYER	페이지 텍스트 레이어	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	PDF 페이지의 텍스트 레이어 상태를 구분하는 공통코드. card_doc_page.page_layer_cd에서 사용하며 문서 등록 프로그램이 텍스트와 시각 요소의 존재 여부로 판정한다. 페이지 추출 결과의 신뢰도를 판단하는 정보이고, 청크의 내용 분류인 CHUNK_TYPE과 구분된다.
CHUNK_TYPE	청크 유형	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	문서 청크의 내용 형식을 구분하는 공통코드. card_doc_chunk.chunk_type_cd에서 사용한다. 처리 단계를 나타내는 CHUNK_STATUS와 구분되며, 현재 프로그램은 페이지 전체를 청크 1건으로 나누므로 기본값 BODY로 등록한다.
CHUNK_STATUS	청크 상태	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	문서 청크의 처리 단계와 AI 입력 가능 여부를 구분하는 공통코드. card_doc_chunk.chunk_status에서 사용하며 RAW와 CLEANED만 AI 입력 대상이 된다. 내용 형식을 나타내는 CHUNK_TYPE, 문서 전체 사용 여부를 나타내는 DOC_STATUS와 구분된다.
RUN_STAGE	AI 실행 단계	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 실행 회차가 어느 처리 단계인지 구분하는 공통코드. card_ai_run.run_stage_cd에서 사용한다. 실행 결과를 나타내는 RUN_STATUS와 구분되며, 추출과 의미 검증을 서로 다른 실행 이력으로 남기기 위한 값이다.
RUN_CALL_METHOD	AI 호출 방식	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 모델을 어떤 기술 경로로 호출했는지 구분하는 공통코드. card_ai_run.run_call_mthd_cd에서 사용한다. 호출 방식이 설계 단계에서 확정되지 않아 후보를 값으로 기록하도록 만들어졌으며, 실행 단계를 나타내는 RUN_STAGE와 구분된다.
RUN_STATUS	AI 실행 상태	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 실행 회차 전체의 진행과 결과를 구분하는 공통코드. card_ai_run.run_status에서 사용한다. 페이지·청크 1건의 호출 결과를 나타내는 CALL_STATUS를 모은 실행 단위 상태이며, 문서 통합 저장 여부와 AI 입력 제외 페이지까지 반영한다.
CALL_STATUS	AI 호출 상태	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 호출 1건의 결과를 구분하는 공통코드. card_ai_call.call_status에서 사용한다. 실행 회차 전체의 결과인 RUN_STATUS보다 작은 단위이며, 추출 내용이 맞는지가 아니라 응답을 받아 구조화하는 데 성공했는지만 나타낸다.
STG_KIND	추출 항목 종류	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 추출 staging 항목의 종류를 구분하는 공통코드. card_extr_stg.stg_kind_cd에서 사용한다. 추출 단계의 항목 구분이며, 확정 혜택의 종류를 나타내는 BNFT_TYPE이나 조건 유형 COND_TYPE과 구분된다.
STG_STATUS	추출 항목 검토 상태	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI 추출 항목의 검토·승인 결과를 구분하는 공통코드. card_extr_stg.stg_status에서 사용한다. 항목의 최종 처리 상태이며 원문 검증 결과 stg_sql_check_cd, AI 의미 검증 결과 STG_AI_VRFY와 분리해서 기록한다. 관계·근거의 승인을 다루는 APPROVAL_STATUS와도 구분된다.
STG_AI_VRFY	AI 의미 검증 결과	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-10-31 07:48:44.634115+00	SEED_TEST	AI가 추출 항목의 의미를 원문과 대조해 판정한 결과를 구분하는 공통코드. card_extr_stg.stg_ai_vrfy_cd에서 사용하며 NULL이면 의미 검증을 실행하지 않은 상태다. 형식·근거 위치를 확인하는 stg_sql_check_cd와 분리해 기록하고, 최종 승인 여부인 STG_STATUS를 대신하지 않는다.
PREDICATE_METHOD	술어 방법	2026-10-31 07:48:44.634115+00	SEED_TEST	2026-11-02 07:58:57.468697+00	V7_MIGRATION	금액 구간만으로 표현되지 않는 조건을 판정하는 방법을 구분하는 공통코드. 조건 atom의 predicate_method_cd에서 사용하며 세부 값은 cond_params에 둔다. 보상 금액을 산출하는 CALC_METHOD와 달리 조건의 참·거짓만 판정한다. predicate_method_ver는 표현 계약 버전으로 현재 1이며 실행 엔진의 버전을 뜻하지 않는다.
\.


--
-- TOC entry 4663 (class 0 OID 0)
-- Dependencies: 347
-- Name: seq_card_ai_run; Type: SEQUENCE SET; Schema: db_pipeline; Owner: -
--

SELECT pg_catalog.setval('db_pipeline.seq_card_ai_run', 11, true);


--
-- TOC entry 4664 (class 0 OID 0)
-- Dependencies: 348
-- Name: seq_card_bnft; Type: SEQUENCE SET; Schema: db_pipeline; Owner: -
--

SELECT pg_catalog.setval('db_pipeline.seq_card_bnft', 10, true);


--
-- TOC entry 4665 (class 0 OID 0)
-- Dependencies: 379
-- Name: seq_card_common; Type: SEQUENCE SET; Schema: db_pipeline; Owner: -
--

SELECT pg_catalog.setval('db_pipeline.seq_card_common', 19, true);


--
-- TOC entry 4666 (class 0 OID 0)
-- Dependencies: 380
-- Name: seq_card_common_bnft; Type: SEQUENCE SET; Schema: db_pipeline; Owner: -
--

SELECT pg_catalog.setval('db_pipeline.seq_card_common_bnft', 3, true);


--
-- TOC entry 4667 (class 0 OID 0)
-- Dependencies: 349
-- Name: seq_card_doc; Type: SEQUENCE SET; Schema: db_pipeline; Owner: -
--

SELECT pg_catalog.setval('db_pipeline.seq_card_doc', 22, true);


--
-- TOC entry 4668 (class 0 OID 0)
-- Dependencies: 350
-- Name: seq_card_doc_chunk; Type: SEQUENCE SET; Schema: db_pipeline; Owner: -
--

SELECT pg_catalog.setval('db_pipeline.seq_card_doc_chunk', 68, true);


--
-- TOC entry 4669 (class 0 OID 0)
-- Dependencies: 355
-- Name: seq_card_evidence_link; Type: SEQUENCE SET; Schema: db_pipeline; Owner: -
--

SELECT pg_catalog.setval('db_pipeline.seq_card_evidence_link', 115, true);


--
-- TOC entry 4670 (class 0 OID 0)
-- Dependencies: 351
-- Name: seq_card_excl_item; Type: SEQUENCE SET; Schema: db_pipeline; Owner: -
--

SELECT pg_catalog.setval('db_pipeline.seq_card_excl_item', 1, false);


--
-- TOC entry 4671 (class 0 OID 0)
-- Dependencies: 352
-- Name: seq_card_extr_stg; Type: SEQUENCE SET; Schema: db_pipeline; Owner: -
--

SELECT pg_catalog.setval('db_pipeline.seq_card_extr_stg', 21, true);


--
-- TOC entry 4672 (class 0 OID 0)
-- Dependencies: 354
-- Name: seq_card_product; Type: SEQUENCE SET; Schema: db_pipeline; Owner: -
--

SELECT pg_catalog.setval('db_pipeline.seq_card_product', 5, true);


--
-- TOC entry 4673 (class 0 OID 0)
-- Dependencies: 353
-- Name: seq_card_source_evidence; Type: SEQUENCE SET; Schema: db_pipeline; Owner: -
--

SELECT pg_catalog.setval('db_pipeline.seq_card_source_evidence', 69, true);


--
-- TOC entry 4164 (class 2606 OID 20893)
-- Name: card_ai_call card_ai_call_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_ai_call
    ADD CONSTRAINT card_ai_call_pkey PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq);


--
-- TOC entry 4161 (class 2606 OID 20895)
-- Name: card_ai_run card_ai_run_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_ai_run
    ADD CONSTRAINT card_ai_run_pkey PRIMARY KEY (card_ai_run_id);


--
-- TOC entry 4138 (class 2606 OID 21501)
-- Name: card_bnft card_bnft_card_id_bnft_cd_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_bnft
    ADD CONSTRAINT card_bnft_card_id_bnft_cd_key UNIQUE (card_id, bnft_cd);


--
-- TOC entry 4140 (class 2606 OID 21499)
-- Name: card_bnft card_bnft_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_bnft
    ADD CONSTRAINT card_bnft_pkey PRIMARY KEY (card_id, card_bnft_id);


--
-- TOC entry 4193 (class 2606 OID 21704)
-- Name: card_common_bnft_apply card_common_bnft_apply_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_common_bnft_apply
    ADD CONSTRAINT card_common_bnft_apply_pkey PRIMARY KEY (card_common_id, card_common_bnft_id, card_id);


--
-- TOC entry 4189 (class 2606 OID 21699)
-- Name: card_common_bnft card_common_bnft_cd_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_common_bnft
    ADD CONSTRAINT card_common_bnft_cd_key UNIQUE (card_common_id, bnft_cd);


--
-- TOC entry 4191 (class 2606 OID 21697)
-- Name: card_common_bnft card_common_bnft_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_common_bnft
    ADD CONSTRAINT card_common_bnft_pkey PRIMARY KEY (card_common_id, card_common_bnft_id);


--
-- TOC entry 4183 (class 2606 OID 21681)
-- Name: card_common card_common_common_cd_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_common
    ADD CONSTRAINT card_common_common_cd_key UNIQUE (common_cd);


--
-- TOC entry 4187 (class 2606 OID 21686)
-- Name: card_common_doc card_common_doc_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_common_doc
    ADD CONSTRAINT card_common_doc_pkey PRIMARY KEY (card_common_id, card_doc_id);


--
-- TOC entry 4185 (class 2606 OID 21679)
-- Name: card_common card_common_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_common
    ADD CONSTRAINT card_common_pkey PRIMARY KEY (card_common_id);


--
-- TOC entry 4155 (class 2606 OID 20897)
-- Name: card_doc_chunk card_doc_chunk_card_doc_chunk_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_card_doc_chunk_id_key UNIQUE (card_doc_chunk_id);


--
-- TOC entry 4157 (class 2606 OID 20899)
-- Name: card_doc_chunk card_doc_chunk_card_doc_id_chunk_seq_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_card_doc_id_chunk_seq_key UNIQUE (card_doc_id, chunk_seq);


--
-- TOC entry 4159 (class 2606 OID 20901)
-- Name: card_doc_chunk card_doc_chunk_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_pkey PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id);


--
-- TOC entry 4146 (class 2606 OID 20813)
-- Name: card_doc card_doc_doc_cd_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_doc
    ADD CONSTRAINT card_doc_doc_cd_key UNIQUE (doc_cd);


--
-- TOC entry 4148 (class 2606 OID 20815)
-- Name: card_doc card_doc_doc_sha256_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_doc
    ADD CONSTRAINT card_doc_doc_sha256_key UNIQUE (doc_sha256);


--
-- TOC entry 4153 (class 2606 OID 20903)
-- Name: card_doc_page card_doc_page_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_doc_page
    ADD CONSTRAINT card_doc_page_pkey PRIMARY KEY (card_doc_id, page_no);


--
-- TOC entry 4151 (class 2606 OID 20811)
-- Name: card_doc card_doc_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_doc
    ADD CONSTRAINT card_doc_pkey PRIMARY KEY (card_doc_id);


--
-- TOC entry 4200 (class 2606 OID 21789)
-- Name: card_evidence_link card_evidence_link_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_evidence_link
    ADD CONSTRAINT card_evidence_link_id_key UNIQUE (card_id, evidence_link_id);


--
-- TOC entry 4202 (class 2606 OID 21791)
-- Name: card_evidence_link card_evidence_link_natural_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_evidence_link
    ADD CONSTRAINT card_evidence_link_natural_key UNIQUE NULLS NOT DISTINCT (card_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, ev_item_cd, ev_item_key, evidence_id);


--
-- TOC entry 4204 (class 2606 OID 21787)
-- Name: card_evidence_link card_evidence_link_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_evidence_link
    ADD CONSTRAINT card_evidence_link_pkey PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id);


--
-- TOC entry 4177 (class 2606 OID 20905)
-- Name: card_excl_item card_excl_item_issuer_excl_item_nm_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_excl_item
    ADD CONSTRAINT card_excl_item_issuer_excl_item_nm_key UNIQUE (issuer, excl_item_nm);


--
-- TOC entry 4179 (class 2606 OID 20907)
-- Name: card_excl_item card_excl_item_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_excl_item
    ADD CONSTRAINT card_excl_item_pkey PRIMARY KEY (card_excl_item_id);


--
-- TOC entry 4168 (class 2606 OID 20909)
-- Name: card_extr_stg card_extr_stg_card_ai_run_id_card_doc_id_page_no_card_doc_c_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_card_ai_run_id_card_doc_id_page_no_card_doc_c_key UNIQUE (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, stg_item_seq);


--
-- TOC entry 4170 (class 2606 OID 20911)
-- Name: card_extr_stg card_extr_stg_card_extr_stg_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_card_extr_stg_id_key UNIQUE (card_extr_stg_id);


--
-- TOC entry 4172 (class 2606 OID 20913)
-- Name: card_extr_stg card_extr_stg_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_pkey PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id);


--
-- TOC entry 4136 (class 2606 OID 20708)
-- Name: card_product_doc card_product_doc_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_product_doc
    ADD CONSTRAINT card_product_doc_pkey PRIMARY KEY (card_id, card_doc_id);


--
-- TOC entry 4131 (class 2606 OID 20678)
-- Name: card_product card_product_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_product
    ADD CONSTRAINT card_product_pkey PRIMARY KEY (card_id);


--
-- TOC entry 4133 (class 2606 OID 20680)
-- Name: card_product card_product_product_cd_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_product
    ADD CONSTRAINT card_product_product_cd_key UNIQUE (product_cd);


--
-- TOC entry 4195 (class 2606 OID 21765)
-- Name: card_source_evidence card_source_evidence_evidence_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_source_evidence
    ADD CONSTRAINT card_source_evidence_evidence_id_key UNIQUE (evidence_id);


--
-- TOC entry 4197 (class 2606 OID 21763)
-- Name: card_source_evidence card_source_evidence_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.card_source_evidence
    ADD CONSTRAINT card_source_evidence_pkey PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id);


--
-- TOC entry 4127 (class 2606 OID 20664)
-- Name: common_cd pk_common_cd; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.common_cd
    ADD CONSTRAINT pk_common_cd PRIMARY KEY (common_code_grp_id, common_cd);


--
-- TOC entry 4125 (class 2606 OID 20655)
-- Name: common_code_grp pk_common_code_grp; Type: CONSTRAINT; Schema: db_pipeline; Owner: -
--

ALTER TABLE ONLY db_pipeline.common_code_grp
    ADD CONSTRAINT pk_common_code_grp PRIMARY KEY (common_code_grp_id);


--
-- TOC entry 4149 (class 1259 OID 20921)
-- Name: card_doc_family_version_idx; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX card_doc_family_version_idx ON db_pipeline.card_doc USING btree (doc_family_cd, doc_version_no, doc_release_date);


--
-- TOC entry 4128 (class 1259 OID 20923)
-- Name: card_product_brand_opt_gin_idx; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX card_product_brand_opt_gin_idx ON db_pipeline.card_product USING gin (brand_opt_list jsonb_path_ops);


--
-- TOC entry 4134 (class 1259 OID 20924)
-- Name: card_product_doc_doc_idx; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX card_product_doc_doc_idx ON db_pipeline.card_product_doc USING btree (card_doc_id, card_id);


--
-- TOC entry 4129 (class 1259 OID 20922)
-- Name: card_product_kind_status_idx; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX card_product_kind_status_idx ON db_pipeline.card_product USING btree (card_kind_cd, product_status_cd);


--
-- TOC entry 4165 (class 1259 OID 20914)
-- Name: ix_card_ai_call_chunk_key; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_ai_call_chunk_key ON db_pipeline.card_ai_call USING btree (card_doc_chunk_id);


--
-- TOC entry 4166 (class 1259 OID 20915)
-- Name: ix_card_ai_call_doc_chunk_key; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_ai_call_doc_chunk_key ON db_pipeline.card_ai_call USING btree (card_doc_id, page_no, card_doc_chunk_id);


--
-- TOC entry 4162 (class 1259 OID 20916)
-- Name: ix_card_ai_run_doc_key; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_ai_run_doc_key ON db_pipeline.card_ai_run USING btree (run_target_card_doc_id);


--
-- TOC entry 4141 (class 1259 OID 20928)
-- Name: ix_card_bnft_brand_opt_gin; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_bnft_brand_opt_gin ON db_pipeline.card_bnft USING gin (bnft_brand_opt_cds);


--
-- TOC entry 4142 (class 1259 OID 20931)
-- Name: ix_card_bnft_cond_gin; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_bnft_cond_gin ON db_pipeline.card_bnft USING gin (bnft_cond_expr jsonb_path_ops);


--
-- TOC entry 4143 (class 1259 OID 20930)
-- Name: ix_card_bnft_relation_list_gin; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_bnft_relation_list_gin ON db_pipeline.card_bnft USING gin (relation_list jsonb_path_ops);


--
-- TOC entry 4144 (class 1259 OID 20929)
-- Name: ix_card_bnft_rule_list_gin; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_bnft_rule_list_gin ON db_pipeline.card_bnft USING gin (rule_list jsonb_path_ops);


--
-- TOC entry 4205 (class 1259 OID 21792)
-- Name: ix_card_evidence_link_evidence; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_evidence_link_evidence ON db_pipeline.card_evidence_link USING btree (evidence_id);


--
-- TOC entry 4206 (class 1259 OID 21793)
-- Name: ix_card_evidence_link_subject; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_evidence_link_subject ON db_pipeline.card_evidence_link USING btree (card_id, ev_subject_cd, card_bnft_id, rule_key);


--
-- TOC entry 4180 (class 1259 OID 20936)
-- Name: ix_card_excl_item_alias_gin; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_excl_item_alias_gin ON db_pipeline.card_excl_item USING gin (excl_alias_nms);


--
-- TOC entry 4181 (class 1259 OID 20917)
-- Name: ix_card_excl_item_concept_key; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_excl_item_concept_key ON db_pipeline.card_excl_item USING btree (excl_concept_cd);


--
-- TOC entry 4173 (class 1259 OID 20918)
-- Name: ix_card_extr_stg_chunk_key; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_extr_stg_chunk_key ON db_pipeline.card_extr_stg USING btree (card_doc_chunk_id);


--
-- TOC entry 4174 (class 1259 OID 20919)
-- Name: ix_card_extr_stg_excl_item_key; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_extr_stg_excl_item_key ON db_pipeline.card_extr_stg USING btree (card_excl_item_id);


--
-- TOC entry 4175 (class 1259 OID 20920)
-- Name: ix_card_extr_stg_status_key; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_extr_stg_status_key ON db_pipeline.card_extr_stg USING btree (stg_status, stg_kind_cd);


--
-- TOC entry 4198 (class 1259 OID 21766)
-- Name: ix_card_source_evidence_lookup; Type: INDEX; Schema: db_pipeline; Owner: -
--

CREATE INDEX ix_card_source_evidence_lookup ON db_pipeline.card_source_evidence USING btree (card_doc_id, page_no, card_doc_chunk_id);


-- Completed on 2026-11-03 14:36:46

--
-- PostgreSQL database dump complete
--

