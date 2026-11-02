--
-- PostgreSQL database dump
--

-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.0

-- Started on 2026-11-03 05:24:43

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
-- Name: db_pipeline; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA db_pipeline;


ALTER SCHEMA db_pipeline OWNER TO postgres;

--
-- TOC entry 4365 (class 0 OID 0)
-- Dependencies: 61
-- Name: SCHEMA db_pipeline; Type: COMMENT; Schema: -; Owner: postgres
--

COMMENT ON SCHEMA db_pipeline IS '카드 상품 중심 V7 공통코드·반정규화 스키마(초안)';


--
-- TOC entry 622 (class 1255 OID 20626)
-- Name: fn_cond_spend_bound(jsonb, text); Type: FUNCTION; Schema: db_pipeline; Owner: postgres
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


ALTER FUNCTION db_pipeline.fn_cond_spend_bound(p_expr jsonb, p_bound text) OWNER TO postgres;

--
-- TOC entry 4366 (class 0 OID 0)
-- Dependencies: 622
-- Name: FUNCTION fn_cond_spend_bound(p_expr jsonb, p_bound text); Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON FUNCTION db_pipeline.fn_cond_spend_bound(p_expr jsonb, p_bound text) IS '단일 branch의 전월 실적 구간 값 추출. OR식이나 구간 atom이 둘 이상이면 NULL을 반환하고 v_card_cond_atom으로 조회';


--
-- TOC entry 620 (class 1255 OID 20624)
-- Name: fn_get_biz_id(text); Type: FUNCTION; Schema: db_pipeline; Owner: postgres
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


ALTER FUNCTION db_pipeline.fn_get_biz_id(p_tbl_nm text) OWNER TO postgres;

--
-- TOC entry 4367 (class 0 OID 0)
-- Dependencies: 620
-- Name: FUNCTION fn_get_biz_id(p_tbl_nm text); Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON FUNCTION db_pipeline.fn_get_biz_id(p_tbl_nm text) IS 'db_pipeline.seq_<테이블명> 시퀀스로 YYYYMMDD_000001 형식 업무 ID 발급(Asia/Seoul 기준)';


--
-- TOC entry 624 (class 1255 OID 20630)
-- Name: fn_valid_brand_opt_list(jsonb); Type: FUNCTION; Schema: db_pipeline; Owner: postgres
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


ALTER FUNCTION db_pipeline.fn_valid_brand_opt_list(p_list jsonb) OWNER TO postgres;

--
-- TOC entry 4368 (class 0 OID 0)
-- Dependencies: 624
-- Name: FUNCTION fn_valid_brand_opt_list(p_list jsonb); Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON FUNCTION db_pipeline.fn_valid_brand_opt_list(p_list jsonb) IS '상품의 브랜드 선택지 목록 검증. 코드값 소속은 v_common_cd_usage로 검사';


--
-- TOC entry 621 (class 1255 OID 20625)
-- Name: fn_valid_cond_expr(jsonb); Type: FUNCTION; Schema: db_pipeline; Owner: postgres
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


ALTER FUNCTION db_pipeline.fn_valid_cond_expr(p_expr jsonb) OWNER TO postgres;

--
-- TOC entry 4369 (class 0 OID 0)
-- Dependencies: 621
-- Name: FUNCTION fn_valid_cond_expr(p_expr jsonb); Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON FUNCTION db_pipeline.fn_valid_cond_expr(p_expr jsonb) IS '조건식 JSONB 계약 검증. branch 사이 OR, branch 안 atom AND, negate_yn=NOT';


--
-- TOC entry 626 (class 1255 OID 20632)
-- Name: fn_valid_relation_list(jsonb, text); Type: FUNCTION; Schema: db_pipeline; Owner: postgres
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


ALTER FUNCTION db_pipeline.fn_valid_relation_list(p_list jsonb, p_self_bnft_id text) OWNER TO postgres;

--
-- TOC entry 4370 (class 0 OID 0)
-- Dependencies: 626
-- Name: FUNCTION fn_valid_relation_list(p_list jsonb, p_self_bnft_id text); Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON FUNCTION db_pipeline.fn_valid_relation_list(p_list jsonb, p_self_bnft_id text) IS '혜택 관계 목록 JSONB 계약 검증. 자기 참조, relation_key 중복, 같은 대상·유형 중복, 제거된 trigger_pool_id 거부';


--
-- TOC entry 625 (class 1255 OID 20631)
-- Name: fn_valid_rule_list(jsonb, text); Type: FUNCTION; Schema: db_pipeline; Owner: postgres
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


ALTER FUNCTION db_pipeline.fn_valid_rule_list(p_list jsonb, p_owner text) OWNER TO postgres;

--
-- TOC entry 4371 (class 0 OID 0)
-- Dependencies: 625
-- Name: FUNCTION fn_valid_rule_list(p_list jsonb, p_owner text); Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON FUNCTION db_pipeline.fn_valid_rule_list(p_list jsonb, p_owner text) IS '계산 규칙 목록 JSONB 계약 검증. 최종 규칙에는 pool_refs를 허용하지 않는다. p_owner는 LOCAL만 허용';


--
-- TOC entry 623 (class 1255 OID 20627)
-- Name: fn_valid_target_list(jsonb); Type: FUNCTION; Schema: db_pipeline; Owner: postgres
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


ALTER FUNCTION db_pipeline.fn_valid_target_list(p_list jsonb) OWNER TO postgres;

--
-- TOC entry 4372 (class 0 OID 0)
-- Dependencies: 623
-- Name: FUNCTION fn_valid_target_list(p_list jsonb); Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON FUNCTION db_pipeline.fn_valid_target_list(p_list jsonb) IS '대상 목록 JSONB 계약 검증. 비율·금액 키는 두지 않으며 대상별 비율이 다르면 규칙 행을 나눔';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 366 (class 1259 OID 20850)
-- Name: card_ai_call; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.card_ai_call OWNER TO postgres;

--
-- TOC entry 4373 (class 0 OID 0)
-- Dependencies: 366
-- Name: TABLE card_ai_call; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_ai_call IS 'AI 호출 이력';


--
-- TOC entry 4374 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.card_ai_run_id IS 'AI 실행 아이디';


--
-- TOC entry 4375 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.card_doc_id IS '문서 아이디';


--
-- TOC entry 4376 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.page_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.page_no IS '페이지 번호';


--
-- TOC entry 4377 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.card_doc_chunk_id IS '청크 아이디';


--
-- TOC entry 4378 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.call_seq; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_seq IS '호출 순번';


--
-- TOC entry 4379 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.call_input_sha256; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_input_sha256 IS '호출 입력 해시';


--
-- TOC entry 4380 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.call_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_status IS '호출 상태';


--
-- TOC entry 4381 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.call_resp_raw; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_resp_raw IS '응답 원문';


--
-- TOC entry 4382 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.call_resp_json; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_resp_json IS '응답 JSON';


--
-- TOC entry 4383 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.call_error_msg; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_error_msg IS '오류 메시지';


--
-- TOC entry 4384 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.call_input_token_cnt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_input_token_cnt IS '입력 토큰 수';


--
-- TOC entry 4385 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.call_output_token_cnt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_output_token_cnt IS '출력 토큰 수';


--
-- TOC entry 4386 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.call_latency_ms; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_latency_ms IS '응답 시간';


--
-- TOC entry 4387 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.call_req_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_req_date IS '요청 일시';


--
-- TOC entry 4388 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.create_date IS '생성 일시';


--
-- TOC entry 4389 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4390 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.update_date IS '수정 일시';


--
-- TOC entry 4391 (class 0 OID 0)
-- Dependencies: 366
-- Name: COLUMN card_ai_call.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 365 (class 1259 OID 20839)
-- Name: card_ai_run; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.card_ai_run OWNER TO postgres;

--
-- TOC entry 4392 (class 0 OID 0)
-- Dependencies: 365
-- Name: TABLE card_ai_run; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_ai_run IS 'AI 실행 이력';


--
-- TOC entry 4393 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.card_ai_run_id IS 'AI 실행 아이디';


--
-- TOC entry 4394 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.run_stage_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_stage_cd IS '실행 단계';


--
-- TOC entry 4395 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.run_call_mthd_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_call_mthd_cd IS 'AI 호출 방식';


--
-- TOC entry 4396 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.run_model_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_model_nm IS '모델명';


--
-- TOC entry 4397 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.run_prompt_ver; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_prompt_ver IS '프롬프트 버전';


--
-- TOC entry 4398 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.run_prompt_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_prompt_txt IS '프롬프트 원문';


--
-- TOC entry 4399 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.run_param; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_param IS '모델 파라미터';


--
-- TOC entry 4400 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.run_target_card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_target_card_doc_id IS '대상 문서 아이디';


--
-- TOC entry 4401 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.run_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_status IS '실행 상태';


--
-- TOC entry 4402 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.run_start_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_start_date IS '실행 시작 일시';


--
-- TOC entry 4403 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.run_end_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_end_date IS '실행 종료 일시';


--
-- TOC entry 4404 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.run_note; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_note IS '실행 메모';


--
-- TOC entry 4405 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.create_date IS '생성 일시';


--
-- TOC entry 4406 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4407 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.update_date IS '수정 일시';


--
-- TOC entry 4408 (class 0 OID 0)
-- Dependencies: 365
-- Name: COLUMN card_ai_run.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 360 (class 1259 OID 20709)
-- Name: card_bnft; Type: TABLE; Schema: db_pipeline; Owner: postgres
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
    CONSTRAINT card_bnft_ck_1 CHECK (((((bnft_scope_cd)::text = 'PRODUCT'::text) AND (bnft_brand_opt_cds IS NULL)) OR (((bnft_scope_cd)::text <> 'PRODUCT'::text) AND (COALESCE(cardinality(bnft_brand_opt_cds), 0) > 0)))),
    CONSTRAINT card_bnft_ck_2 CHECK (db_pipeline.fn_valid_cond_expr(bnft_cond_expr)),
    CONSTRAINT card_bnft_ck_3 CHECK (db_pipeline.fn_valid_rule_list(rule_list, 'LOCAL'::text)),
    CONSTRAINT card_bnft_ck_4 CHECK (db_pipeline.fn_valid_relation_list(relation_list, (card_bnft_id)::text)),
    CONSTRAINT card_bnft_ck_5 CHECK ((((bnft_origin_cd)::text <> 'BRAND_SERVICE'::text) OR ((bnft_scope_cd)::text = 'BRAND'::text))),
    CONSTRAINT card_bnft_ck_6 CHECK (((bnft_valid_to_excl IS NULL) OR (bnft_valid_from IS NULL) OR (bnft_valid_to_excl > bnft_valid_from)))
);


ALTER TABLE db_pipeline.card_bnft OWNER TO postgres;

--
-- TOC entry 4409 (class 0 OID 0)
-- Dependencies: 360
-- Name: TABLE card_bnft; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_bnft IS '카드 혜택';


--
-- TOC entry 4410 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.card_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.card_id IS '카드 아이디';


--
-- TOC entry 4411 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.card_bnft_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.card_bnft_id IS '혜택 아이디';


--
-- TOC entry 4412 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_cd IS '혜택 코드';


--
-- TOC entry 4413 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_nm IS '혜택명';


--
-- TOC entry 4414 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_type_cd IS '혜택 유형';


--
-- TOC entry 4415 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_origin_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_origin_cd IS '혜택 출처';


--
-- TOC entry 4416 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_scope_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_scope_cd IS '혜택 적용 범위';


--
-- TOC entry 4417 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_brand_opt_cds; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_brand_opt_cds IS '적용 브랜드 선택지';


--
-- TOC entry 4418 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_cond_expr; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_cond_expr IS '혜택 적용 조건';


--
-- TOC entry 4419 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.rule_select_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.rule_select_cd IS '규칙 선택 방식';


--
-- TOC entry 4420 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.rule_list; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.rule_list IS '계산 규칙 목록';


--
-- TOC entry 4421 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.relation_list; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.relation_list IS '혜택 관계 목록';


--
-- TOC entry 4422 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.verification_status_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.verification_status_cd IS '혜택 검증 상태';


--
-- TOC entry 4423 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_valid_from; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_from IS '혜택 제공 시작일';


--
-- TOC entry 4424 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_valid_to_excl; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_to_excl IS '혜택 제공 종료일(미포함)';


--
-- TOC entry 4425 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_rule_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_rule_txt IS '공식 원문 근거에서 모은 혜택 계산 규칙 안내. 계산 확정값이 아니라 검토 대상 텍스트';


--
-- TOC entry 4426 (class 0 OID 0)
-- Dependencies: 360
-- Name: COLUMN card_bnft.bnft_limit_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_limit_txt IS '원문 근거에서 모은 혜택별 이용/금액 한도. 여러 풀의 근거를 혜택별로 중복 제거한 텍스트';


--
-- TOC entry 383 (class 1259 OID 21668)
-- Name: seq_card_common; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_common
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE db_pipeline.seq_card_common OWNER TO postgres;

--
-- TOC entry 4427 (class 0 OID 0)
-- Dependencies: 383
-- Name: SEQUENCE seq_card_common; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_common IS '공통서비스 ID 발급';


--
-- TOC entry 385 (class 1259 OID 21670)
-- Name: card_common; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.card_common OWNER TO postgres;

--
-- TOC entry 4428 (class 0 OID 0)
-- Dependencies: 385
-- Name: TABLE card_common; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_common IS '카드 브랜드 공통서비스 (실제 카드 상품 아님)';


--
-- TOC entry 4429 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_common.card_common_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common.card_common_id IS '공통서비스 아이디';


--
-- TOC entry 4430 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_common.common_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common.common_cd IS '공통서비스 업무 코드';


--
-- TOC entry 4431 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_common.common_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common.common_nm IS '공통서비스명';


--
-- TOC entry 4432 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_common.brand_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common.brand_cd IS '국제 브랜드 코드';


--
-- TOC entry 4433 (class 0 OID 0)
-- Dependencies: 385
-- Name: COLUMN card_common.service_grade_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common.service_grade_cd IS '서비스 등급 코드';


--
-- TOC entry 387 (class 1259 OID 21687)
-- Name: card_common_bnft; Type: TABLE; Schema: db_pipeline; Owner: postgres
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
    CONSTRAINT card_common_bnft_date_check CHECK (((bnft_valid_to_excl IS NULL) OR (bnft_valid_from IS NULL) OR (bnft_valid_to_excl > bnft_valid_from)))
);


ALTER TABLE db_pipeline.card_common_bnft OWNER TO postgres;

--
-- TOC entry 4434 (class 0 OID 0)
-- Dependencies: 387
-- Name: TABLE card_common_bnft; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_common_bnft IS '공통서비스 혜택';


--
-- TOC entry 4435 (class 0 OID 0)
-- Dependencies: 387
-- Name: COLUMN card_common_bnft.card_common_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.card_common_id IS '공통서비스 아이디 (논리 참조)';


--
-- TOC entry 4436 (class 0 OID 0)
-- Dependencies: 387
-- Name: COLUMN card_common_bnft.card_common_bnft_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.card_common_bnft_id IS '공통 혜택 아이디';


--
-- TOC entry 4437 (class 0 OID 0)
-- Dependencies: 387
-- Name: COLUMN card_common_bnft.bnft_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.bnft_cd IS '공통 혜택 업무 코드';


--
-- TOC entry 4438 (class 0 OID 0)
-- Dependencies: 387
-- Name: COLUMN card_common_bnft.bnft_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.bnft_nm IS '공통 혜택명';


--
-- TOC entry 4439 (class 0 OID 0)
-- Dependencies: 387
-- Name: COLUMN card_common_bnft.service_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common_bnft.service_type_cd IS '공통서비스 내 유형 (COMMON/선택서비스 등)';


--
-- TOC entry 388 (class 1259 OID 21700)
-- Name: card_common_bnft_apply; Type: TABLE; Schema: db_pipeline; Owner: postgres
--

CREATE TABLE db_pipeline.card_common_bnft_apply (
    card_common_id bigint NOT NULL,
    card_common_bnft_id character varying(20) NOT NULL,
    card_id bigint NOT NULL
);


ALTER TABLE db_pipeline.card_common_bnft_apply OWNER TO postgres;

--
-- TOC entry 4440 (class 0 OID 0)
-- Dependencies: 388
-- Name: TABLE card_common_bnft_apply; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_common_bnft_apply IS '공통 혜택과 실제 카드 상품 적용 관계';


--
-- TOC entry 4441 (class 0 OID 0)
-- Dependencies: 388
-- Name: COLUMN card_common_bnft_apply.card_common_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common_bnft_apply.card_common_id IS '공통서비스 아이디 (논리 참조)';


--
-- TOC entry 4442 (class 0 OID 0)
-- Dependencies: 388
-- Name: COLUMN card_common_bnft_apply.card_common_bnft_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common_bnft_apply.card_common_bnft_id IS '공통 혜택 아이디 (논리 참조)';


--
-- TOC entry 4443 (class 0 OID 0)
-- Dependencies: 388
-- Name: COLUMN card_common_bnft_apply.card_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common_bnft_apply.card_id IS '실제 카드 상품 아이디 (논리 참조 CARD_PRODUCT)';


--
-- TOC entry 386 (class 1259 OID 21682)
-- Name: card_common_doc; Type: TABLE; Schema: db_pipeline; Owner: postgres
--

CREATE TABLE db_pipeline.card_common_doc (
    card_common_id bigint NOT NULL,
    card_doc_id character varying(20) NOT NULL
);


ALTER TABLE db_pipeline.card_common_doc OWNER TO postgres;

--
-- TOC entry 4444 (class 0 OID 0)
-- Dependencies: 386
-- Name: TABLE card_common_doc; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_common_doc IS '공통서비스별 원천 문서 관계';


--
-- TOC entry 4445 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_common_doc.card_common_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common_doc.card_common_id IS '공통서비스 아이디 (논리 참조)';


--
-- TOC entry 4446 (class 0 OID 0)
-- Dependencies: 386
-- Name: COLUMN card_common_doc.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_common_doc.card_doc_id IS '원천 문서 아이디 (논리 참조 CARD_DOC)';


--
-- TOC entry 362 (class 1259 OID 20795)
-- Name: card_doc; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.card_doc OWNER TO postgres;

--
-- TOC entry 4447 (class 0 OID 0)
-- Dependencies: 362
-- Name: TABLE card_doc; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_doc IS '카드 관련 문서';


--
-- TOC entry 4448 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.card_doc_id IS '문서 아이디';


--
-- TOC entry 4449 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_cd IS '문서 코드';


--
-- TOC entry 4450 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_family_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_family_cd IS '문서 계열 코드';


--
-- TOC entry 4451 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_type_cd IS '문서 유형';


--
-- TOC entry 4452 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_title; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_title IS '문서 제목';


--
-- TOC entry 4453 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_source_url; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_source_url IS '문서 출처 URL';


--
-- TOC entry 4454 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_file_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_file_nm IS '파일명';


--
-- TOC entry 4455 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_file_size; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_file_size IS '파일 크기';


--
-- TOC entry 4456 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_sha256; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_sha256 IS '파일 해시';


--
-- TOC entry 4457 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_page_cnt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_page_cnt IS '페이지 수';


--
-- TOC entry 4458 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_review_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_review_no IS '심의 번호';


--
-- TOC entry 4459 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_review_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_review_date IS '심의일';


--
-- TOC entry 4460 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_release_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_release_date IS '문서 발행일';


--
-- TOC entry 4461 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_collect_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_collect_date IS '수집 일시';


--
-- TOC entry 4462 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_version_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_version_no IS '문서 버전 번호';


--
-- TOC entry 4463 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_status IS '문서 상태';


--
-- TOC entry 4464 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.doc_note; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_note IS '문서 메모';


--
-- TOC entry 4465 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.create_date IS '생성 일시';


--
-- TOC entry 4466 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4467 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.update_date IS '수정 일시';


--
-- TOC entry 4468 (class 0 OID 0)
-- Dependencies: 362
-- Name: COLUMN card_doc.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 364 (class 1259 OID 20826)
-- Name: card_doc_chunk; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.card_doc_chunk OWNER TO postgres;

--
-- TOC entry 4469 (class 0 OID 0)
-- Dependencies: 364
-- Name: TABLE card_doc_chunk; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_doc_chunk IS '문서 청크';


--
-- TOC entry 4470 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.card_doc_id IS '문서 아이디';


--
-- TOC entry 4471 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.page_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.page_no IS '페이지 번호';


--
-- TOC entry 4472 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.card_doc_chunk_id IS '청크 아이디';


--
-- TOC entry 4473 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.chunk_seq; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_seq IS '청크 순번';


--
-- TOC entry 4474 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.chunk_section_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_section_nm IS '절 제목';


--
-- TOC entry 4475 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.chunk_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_type_cd IS '청크 유형';


--
-- TOC entry 4476 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.chunk_start_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_start_pos IS '청크 시작 위치';


--
-- TOC entry 4477 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.chunk_end_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_end_pos IS '청크 종료 위치';


--
-- TOC entry 4478 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.chunk_raw_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_raw_txt IS '청크 원문';


--
-- TOC entry 4479 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.chunk_clean_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_clean_txt IS '청크 정제문';


--
-- TOC entry 4480 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.chunk_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_status IS '청크 상태';


--
-- TOC entry 4481 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.chunk_split_rule_ver; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_split_rule_ver IS '청크 분리 규칙 버전';


--
-- TOC entry 4482 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.chunk_clean_rule_ver; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_clean_rule_ver IS '청크 정제 규칙 버전';


--
-- TOC entry 4483 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.create_date IS '생성 일시';


--
-- TOC entry 4484 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4485 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.update_date IS '수정 일시';


--
-- TOC entry 4486 (class 0 OID 0)
-- Dependencies: 364
-- Name: COLUMN card_doc_chunk.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 363 (class 1259 OID 20816)
-- Name: card_doc_page; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.card_doc_page OWNER TO postgres;

--
-- TOC entry 4487 (class 0 OID 0)
-- Dependencies: 363
-- Name: TABLE card_doc_page; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_doc_page IS '문서 페이지';


--
-- TOC entry 4488 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.card_doc_id IS '문서 아이디';


--
-- TOC entry 4489 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.page_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_no IS '페이지 번호';


--
-- TOC entry 4490 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.page_raw_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_raw_txt IS '페이지 원문';


--
-- TOC entry 4491 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.page_char_cnt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_char_cnt IS '페이지 문자 수';


--
-- TOC entry 4492 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.page_txt_sha256; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_txt_sha256 IS '페이지 원문 해시';


--
-- TOC entry 4493 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.page_layer_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_layer_cd IS '텍스트 레이어 유형';


--
-- TOC entry 4494 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.page_extractor_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_extractor_nm IS '추출기명';


--
-- TOC entry 4495 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.page_extractor_ver; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_extractor_ver IS '추출기 버전';


--
-- TOC entry 4496 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.page_note; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_note IS '페이지 메모';


--
-- TOC entry 4497 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.create_date IS '생성 일시';


--
-- TOC entry 4498 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4499 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.update_date IS '수정 일시';


--
-- TOC entry 4500 (class 0 OID 0)
-- Dependencies: 363
-- Name: COLUMN card_doc_page.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 361 (class 1259 OID 20766)
-- Name: card_evidence_link; Type: TABLE; Schema: db_pipeline; Owner: postgres
--

CREATE TABLE db_pipeline.card_evidence_link (
    card_id bigint NOT NULL,
    ev_link_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_evidence_link'::text) NOT NULL,
    ev_subject_cd character varying(10) NOT NULL,
    card_bnft_id character varying(20),
    rule_key character varying(40),
    relation_key character varying(40),
    ev_item_cd character varying(10) DEFAULT 'SELF'::character varying NOT NULL,
    ev_item_key character varying(100) DEFAULT '-'::character varying NOT NULL,
    evidence_id character varying(20) NOT NULL,
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


ALTER TABLE db_pipeline.card_evidence_link OWNER TO postgres;

--
-- TOC entry 4501 (class 0 OID 0)
-- Dependencies: 361
-- Name: TABLE card_evidence_link; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_evidence_link IS '카드 근거 관계';


--
-- TOC entry 4502 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_evidence_link.card_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.card_id IS '카드 아이디';


--
-- TOC entry 4503 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_evidence_link.ev_link_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.ev_link_id IS '근거 연결 아이디';


--
-- TOC entry 4504 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_evidence_link.ev_subject_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.ev_subject_cd IS '근거 대상 유형';


--
-- TOC entry 4505 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_evidence_link.card_bnft_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.card_bnft_id IS '혜택 아이디';


--
-- TOC entry 4506 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_evidence_link.rule_key; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.rule_key IS '규칙 키';


--
-- TOC entry 4507 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_evidence_link.relation_key; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.relation_key IS '혜택 관계 키';


--
-- TOC entry 4508 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_evidence_link.ev_item_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.ev_item_cd IS '근거 항목 유형';


--
-- TOC entry 4509 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_evidence_link.ev_item_key; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.ev_item_key IS '근거 항목 키';


--
-- TOC entry 4510 (class 0 OID 0)
-- Dependencies: 361
-- Name: COLUMN card_evidence_link.evidence_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_evidence_link.evidence_id IS '원문 근거 아이디';


--
-- TOC entry 368 (class 1259 OID 20873)
-- Name: card_excl_item; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.card_excl_item OWNER TO postgres;

--
-- TOC entry 4511 (class 0 OID 0)
-- Dependencies: 368
-- Name: TABLE card_excl_item; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_excl_item IS '제외 항목 사전(검토중 일단 보류)';


--
-- TOC entry 4512 (class 0 OID 0)
-- Dependencies: 368
-- Name: COLUMN card_excl_item.card_excl_item_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.card_excl_item_id IS '제외 항목 아이디';


--
-- TOC entry 4513 (class 0 OID 0)
-- Dependencies: 368
-- Name: COLUMN card_excl_item.issuer; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.issuer IS '카드사';


--
-- TOC entry 4514 (class 0 OID 0)
-- Dependencies: 368
-- Name: COLUMN card_excl_item.excl_item_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_nm IS '제외 항목명';


--
-- TOC entry 4515 (class 0 OID 0)
-- Dependencies: 368
-- Name: COLUMN card_excl_item.excl_concept_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_concept_cd IS '제외 분류 개념';


--
-- TOC entry 4516 (class 0 OID 0)
-- Dependencies: 368
-- Name: COLUMN card_excl_item.excl_item_desc; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_desc IS '제외 항목 설명';


--
-- TOC entry 4517 (class 0 OID 0)
-- Dependencies: 368
-- Name: COLUMN card_excl_item.excl_alias_nms; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_alias_nms IS '제외 항목 별칭';


--
-- TOC entry 4518 (class 0 OID 0)
-- Dependencies: 368
-- Name: COLUMN card_excl_item.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.create_date IS '생성 일시';


--
-- TOC entry 4519 (class 0 OID 0)
-- Dependencies: 368
-- Name: COLUMN card_excl_item.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4520 (class 0 OID 0)
-- Dependencies: 368
-- Name: COLUMN card_excl_item.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.update_date IS '수정 일시';


--
-- TOC entry 4521 (class 0 OID 0)
-- Dependencies: 368
-- Name: COLUMN card_excl_item.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 367 (class 1259 OID 20861)
-- Name: card_extr_stg; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.card_extr_stg OWNER TO postgres;

--
-- TOC entry 4522 (class 0 OID 0)
-- Dependencies: 367
-- Name: TABLE card_extr_stg; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_extr_stg IS 'AI 추출 항목';


--
-- TOC entry 4523 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_ai_run_id IS 'AI 실행 아이디';


--
-- TOC entry 4524 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_doc_id IS '문서 아이디';


--
-- TOC entry 4525 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.page_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.page_no IS '페이지 번호';


--
-- TOC entry 4526 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_doc_chunk_id IS '청크 아이디';


--
-- TOC entry 4527 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.call_seq; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.call_seq IS '호출 순번';


--
-- TOC entry 4528 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.card_extr_stg_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_extr_stg_id IS '추출 항목 아이디';


--
-- TOC entry 4529 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_item_seq; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_item_seq IS '추출 항목 순번';


--
-- TOC entry 4530 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.card_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_id IS '카드 아이디(NULL이면 특정 카드에 연결되지 않은 후보)';


--
-- TOC entry 4531 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_kind_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_kind_cd IS '추출 항목 종류';


--
-- TOC entry 4532 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_parent_card_extr_stg_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_parent_card_extr_stg_id IS '상위 추출 항목 아이디';


--
-- TOC entry 4533 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_raw_item; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_raw_item IS '추출 원본';


--
-- TOC entry 4534 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_normalized_item; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_normalized_item IS '정제 항목';


--
-- TOC entry 4535 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_evidence_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_txt IS '추출 근거 문장';


--
-- TOC entry 4536 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_evidence_start_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_start_pos IS '근거 시작 위치';


--
-- TOC entry 4537 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_evidence_end_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_end_pos IS '근거 종료 위치';


--
-- TOC entry 4538 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.card_excl_item_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_excl_item_id IS '제외 항목 아이디';


--
-- TOC entry 4539 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_sql_check_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_sql_check_cd IS 'SQL 검증 결과';


--
-- TOC entry 4540 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_ai_vrfy_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_ai_vrfy_cd IS 'AI 검증 결과';


--
-- TOC entry 4541 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_ai_vrfy_card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_ai_vrfy_card_ai_run_id IS 'AI 검증 실행 아이디';


--
-- TOC entry 4542 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_status IS '검토 상태';


--
-- TOC entry 4543 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_review_note; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_review_note IS '검토 메모';


--
-- TOC entry 4544 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_approved_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_approved_date IS '승인 일시';


--
-- TOC entry 4545 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.stg_approved_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_approved_user_id IS '승인 사용자 아이디';


--
-- TOC entry 4546 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.create_date IS '생성 일시';


--
-- TOC entry 4547 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4548 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.update_date IS '수정 일시';


--
-- TOC entry 4549 (class 0 OID 0)
-- Dependencies: 367
-- Name: COLUMN card_extr_stg.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 354 (class 1259 OID 20645)
-- Name: seq_card_product; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_product
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE db_pipeline.seq_card_product OWNER TO postgres;

--
-- TOC entry 4550 (class 0 OID 0)
-- Dependencies: 354
-- Name: SEQUENCE seq_card_product; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_product IS 'card_product.card_id bigint 발급; 원본 백업에는 상품 마스터 시퀀스가 없음';


--
-- TOC entry 358 (class 1259 OID 20665)
-- Name: card_product; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.card_product OWNER TO postgres;

--
-- TOC entry 4551 (class 0 OID 0)
-- Dependencies: 358
-- Name: TABLE card_product; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_product IS '카드 상품';


--
-- TOC entry 4552 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.card_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.card_id IS '카드 아이디';


--
-- TOC entry 4553 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.product_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.product_cd IS '상품 코드';


--
-- TOC entry 4554 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.product_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.product_nm IS '상품명';


--
-- TOC entry 4555 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.issuer; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.issuer IS '카드사';


--
-- TOC entry 4556 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.card_kind_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.card_kind_cd IS '카드 구분';


--
-- TOC entry 4557 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.product_status_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.product_status_cd IS '상품 상태';


--
-- TOC entry 4558 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.launched_on; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.launched_on IS '출시일';


--
-- TOC entry 4559 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.discontinued_on; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.discontinued_on IS '판매 중단일';


--
-- TOC entry 4560 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.brand_opt_list; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.brand_opt_list IS '브랜드 선택지 목록';


--
-- TOC entry 4561 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.create_date IS '생성 일시';


--
-- TOC entry 4562 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4563 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.update_date IS '수정 일시';


--
-- TOC entry 4564 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 4565 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.card_cond_expr; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.card_cond_expr IS '카드 공통 조건';


--
-- TOC entry 4566 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_product.card_cond_status_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product.card_cond_status_cd IS '카드 공통 조건 상태';


--
-- TOC entry 359 (class 1259 OID 20696)
-- Name: card_product_doc; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.card_product_doc OWNER TO postgres;

--
-- TOC entry 4567 (class 0 OID 0)
-- Dependencies: 359
-- Name: TABLE card_product_doc; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_product_doc IS '상품별 문서 관계';


--
-- TOC entry 4568 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.card_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product_doc.card_id IS '카드 아이디';


--
-- TOC entry 4569 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product_doc.card_doc_id IS '문서 아이디';


--
-- TOC entry 4570 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.doc_role_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product_doc.doc_role_cd IS '문서 역할';


--
-- TOC entry 4571 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.brand_opt_cds; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product_doc.brand_opt_cds IS '적용 브랜드 선택지';


--
-- TOC entry 4572 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.approval_status_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product_doc.approval_status_cd IS '승인 상태';


--
-- TOC entry 4573 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.applicability_basis_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product_doc.applicability_basis_txt IS '적용 근거';


--
-- TOC entry 4574 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.approval_note; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product_doc.approval_note IS '승인 메모';


--
-- TOC entry 4575 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product_doc.create_date IS '생성 일시';


--
-- TOC entry 4576 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product_doc.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4577 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product_doc.update_date IS '수정 일시';


--
-- TOC entry 4578 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_product_doc.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_product_doc.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 369 (class 1259 OID 20882)
-- Name: card_source_evidence; Type: TABLE; Schema: db_pipeline; Owner: postgres
--

CREATE TABLE db_pipeline.card_source_evidence (
    evidence_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_source_evidence'::text) NOT NULL,
    card_doc_id character varying(20) NOT NULL,
    page_no smallint NOT NULL,
    card_doc_chunk_id character varying(20) NOT NULL,
    card_extr_stg_id character varying(20),
    quote_txt text NOT NULL,
    start_pos integer,
    end_pos integer,
    approval_status_cd character varying(20) NOT NULL,
    CONSTRAINT card_source_evidence_ck_1 CHECK (((start_pos IS NULL) OR (start_pos > 0))),
    CONSTRAINT card_source_evidence_ck_2 CHECK (((end_pos IS NULL) OR (start_pos IS NULL) OR (end_pos >= start_pos)))
);


ALTER TABLE db_pipeline.card_source_evidence OWNER TO postgres;

--
-- TOC entry 4579 (class 0 OID 0)
-- Dependencies: 369
-- Name: TABLE card_source_evidence; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_source_evidence IS '원문 근거';


--
-- TOC entry 4580 (class 0 OID 0)
-- Dependencies: 369
-- Name: COLUMN card_source_evidence.evidence_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.evidence_id IS '원문 근거 아이디';


--
-- TOC entry 4581 (class 0 OID 0)
-- Dependencies: 369
-- Name: COLUMN card_source_evidence.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.card_doc_id IS '문서 아이디';


--
-- TOC entry 4582 (class 0 OID 0)
-- Dependencies: 369
-- Name: COLUMN card_source_evidence.page_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.page_no IS '페이지 번호';


--
-- TOC entry 4583 (class 0 OID 0)
-- Dependencies: 369
-- Name: COLUMN card_source_evidence.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.card_doc_chunk_id IS '청크 아이디';


--
-- TOC entry 4584 (class 0 OID 0)
-- Dependencies: 369
-- Name: COLUMN card_source_evidence.card_extr_stg_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.card_extr_stg_id IS '추출 항목 아이디';


--
-- TOC entry 4585 (class 0 OID 0)
-- Dependencies: 369
-- Name: COLUMN card_source_evidence.quote_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.quote_txt IS '원문 인용 문장';


--
-- TOC entry 4586 (class 0 OID 0)
-- Dependencies: 369
-- Name: COLUMN card_source_evidence.start_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.start_pos IS '인용 시작 위치';


--
-- TOC entry 4587 (class 0 OID 0)
-- Dependencies: 369
-- Name: COLUMN card_source_evidence.end_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.end_pos IS '인용 종료 위치';


--
-- TOC entry 4588 (class 0 OID 0)
-- Dependencies: 369
-- Name: COLUMN card_source_evidence.approval_status_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_source_evidence.approval_status_cd IS '승인 상태';


--
-- TOC entry 357 (class 1259 OID 20656)
-- Name: common_cd; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.common_cd OWNER TO postgres;

--
-- TOC entry 4589 (class 0 OID 0)
-- Dependencies: 357
-- Name: TABLE common_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.common_cd IS '공통코드';


--
-- TOC entry 4590 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.common_code_grp_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_cd.common_code_grp_id IS '공통코드 그룹 아이디';


--
-- TOC entry 4591 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.common_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_cd.common_cd IS '공통코드';


--
-- TOC entry 4592 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.common_cd_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_cd.common_cd_nm IS '공통코드명';


--
-- TOC entry 4593 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_cd.create_date IS '생성 일시';


--
-- TOC entry 4594 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_cd.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4595 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_cd.update_date IS '수정 일시';


--
-- TOC entry 4596 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_cd.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 4597 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN common_cd.common_cd_desc; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_cd.common_cd_desc IS '공통코드 상세 설명(업무 의미, 적용 기준)';


--
-- TOC entry 356 (class 1259 OID 20647)
-- Name: common_code_grp; Type: TABLE; Schema: db_pipeline; Owner: postgres
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


ALTER TABLE db_pipeline.common_code_grp OWNER TO postgres;

--
-- TOC entry 4598 (class 0 OID 0)
-- Dependencies: 356
-- Name: TABLE common_code_grp; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.common_code_grp IS '공통코드 그룹';


--
-- TOC entry 4599 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.common_code_grp_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_code_grp.common_code_grp_id IS '공통코드 그룹 아이디';


--
-- TOC entry 4600 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.common_code_grp_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_code_grp.common_code_grp_nm IS '공통코드 그룹명';


--
-- TOC entry 4601 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_code_grp.create_date IS '생성 일시';


--
-- TOC entry 4602 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_code_grp.create_user_id IS '생성 사용자 아이디';


--
-- TOC entry 4603 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_code_grp.update_date IS '수정 일시';


--
-- TOC entry 4604 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_code_grp.update_user_id IS '수정 사용자 아이디';


--
-- TOC entry 4605 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN common_code_grp.common_code_grp_desc; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.common_code_grp.common_code_grp_desc IS '공통코드 그룹 상세 설명(목적, 사용 범위, 업무 의미)';


--
-- TOC entry 347 (class 1259 OID 20634)
-- Name: seq_card_ai_run; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_ai_run
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE db_pipeline.seq_card_ai_run OWNER TO postgres;

--
-- TOC entry 4606 (class 0 OID 0)
-- Dependencies: 347
-- Name: SEQUENCE seq_card_ai_run; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_ai_run IS 'AI 실행 ID 발급';


--
-- TOC entry 348 (class 1259 OID 20635)
-- Name: seq_card_bnft; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_bnft
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE db_pipeline.seq_card_bnft OWNER TO postgres;

--
-- TOC entry 4607 (class 0 OID 0)
-- Dependencies: 348
-- Name: SEQUENCE seq_card_bnft; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_bnft IS '확정 혜택 ID 발급';


--
-- TOC entry 384 (class 1259 OID 21669)
-- Name: seq_card_common_bnft; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_common_bnft
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1;


ALTER SEQUENCE db_pipeline.seq_card_common_bnft OWNER TO postgres;

--
-- TOC entry 4608 (class 0 OID 0)
-- Dependencies: 384
-- Name: SEQUENCE seq_card_common_bnft; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_common_bnft IS '공통 혜택 ID 발급';


--
-- TOC entry 349 (class 1259 OID 20636)
-- Name: seq_card_doc; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_doc
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE db_pipeline.seq_card_doc OWNER TO postgres;

--
-- TOC entry 4609 (class 0 OID 0)
-- Dependencies: 349
-- Name: SEQUENCE seq_card_doc; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_doc IS '원본 문서 ID 발급';


--
-- TOC entry 350 (class 1259 OID 20637)
-- Name: seq_card_doc_chunk; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_doc_chunk
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE db_pipeline.seq_card_doc_chunk OWNER TO postgres;

--
-- TOC entry 4610 (class 0 OID 0)
-- Dependencies: 350
-- Name: SEQUENCE seq_card_doc_chunk; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_doc_chunk IS '문서 청크 ID 발급';


--
-- TOC entry 355 (class 1259 OID 20646)
-- Name: seq_card_evidence_link; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_evidence_link
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE db_pipeline.seq_card_evidence_link OWNER TO postgres;

--
-- TOC entry 4611 (class 0 OID 0)
-- Dependencies: 355
-- Name: SEQUENCE seq_card_evidence_link; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_evidence_link IS 'card_evidence_link.ev_link_id 로컬 업무 ID 발급';


--
-- TOC entry 351 (class 1259 OID 20638)
-- Name: seq_card_excl_item; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_excl_item
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE db_pipeline.seq_card_excl_item OWNER TO postgres;

--
-- TOC entry 4612 (class 0 OID 0)
-- Dependencies: 351
-- Name: SEQUENCE seq_card_excl_item; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_excl_item IS '표준 제외 항목 ID 발급';


--
-- TOC entry 352 (class 1259 OID 20639)
-- Name: seq_card_extr_stg; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_extr_stg
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE db_pipeline.seq_card_extr_stg OWNER TO postgres;

--
-- TOC entry 4613 (class 0 OID 0)
-- Dependencies: 352
-- Name: SEQUENCE seq_card_extr_stg; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_extr_stg IS 'AI 추출 staging ID 발급';


--
-- TOC entry 353 (class 1259 OID 20644)
-- Name: seq_card_source_evidence; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_source_evidence
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE db_pipeline.seq_card_source_evidence OWNER TO postgres;

--
-- TOC entry 4614 (class 0 OID 0)
-- Dependencies: 353
-- Name: SEQUENCE seq_card_source_evidence; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_source_evidence IS 'card_source_evidence.evidence_id 로컬 업무 ID 발급';


--
-- TOC entry 379 (class 1259 OID 21647)
-- Name: v_card_bnft_rel; Type: VIEW; Schema: db_pipeline; Owner: postgres
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


ALTER VIEW db_pipeline.v_card_bnft_rel OWNER TO postgres;

--
-- TOC entry 4615 (class 0 OID 0)
-- Dependencies: 379
-- Name: VIEW v_card_bnft_rel; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON VIEW db_pipeline.v_card_bnft_rel IS '혜택 관계를 행으로 복원. MUTUALLY_EXCLUSIVE는 reverse_yn=true 행을 더해 양방향 제공. 저장 행 조회는 reverse_yn=false';


--
-- TOC entry 371 (class 1259 OID 21577)
-- Name: v_card_rule; Type: VIEW; Schema: db_pipeline; Owner: postgres
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


ALTER VIEW db_pipeline.v_card_rule OWNER TO postgres;

--
-- TOC entry 4616 (class 0 OID 0)
-- Dependencies: 371
-- Name: VIEW v_card_rule; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON VIEW db_pipeline.v_card_rule IS '상품 계산 규칙을 행으로 복원. V5 card_bnft_rule 조회 대체';


--
-- TOC entry 373 (class 1259 OID 21596)
-- Name: v_card_bnft_rule_effective; Type: VIEW; Schema: db_pipeline; Owner: postgres
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


ALTER VIEW db_pipeline.v_card_bnft_rule_effective OWNER TO postgres;

--
-- TOC entry 4617 (class 0 OID 0)
-- Dependencies: 373
-- Name: VIEW v_card_bnft_rule_effective; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON VIEW db_pipeline.v_card_bnft_rule_effective IS '혜택과 계산 규칙의 단일 출력. 제공 기간은 걸러내지 않으므로 조회 기준일로 판정. 값은 정책 후보이며 거래별 보상액이 아님';


--
-- TOC entry 370 (class 1259 OID 20941)
-- Name: v_card_brand_opt; Type: VIEW; Schema: db_pipeline; Owner: postgres
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


ALTER VIEW db_pipeline.v_card_brand_opt OWNER TO postgres;

--
-- TOC entry 4618 (class 0 OID 0)
-- Dependencies: 370
-- Name: VIEW v_card_brand_opt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON VIEW db_pipeline.v_card_brand_opt IS '상품별 브랜드 선택지를 행으로 복원';


--
-- TOC entry 380 (class 1259 OID 21652)
-- Name: v_card_cond_atom; Type: VIEW; Schema: db_pipeline; Owner: postgres
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


ALTER VIEW db_pipeline.v_card_cond_atom OWNER TO postgres;

--
-- TOC entry 4619 (class 0 OID 0)
-- Dependencies: 380
-- Name: VIEW v_card_cond_atom; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON VIEW db_pipeline.v_card_cond_atom IS '모든 조건식의 atom을 소유자와 함께 행으로 복원';


--
-- TOC entry 372 (class 1259 OID 21586)
-- Name: v_card_rule_target; Type: VIEW; Schema: db_pipeline; Owner: postgres
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


ALTER VIEW db_pipeline.v_card_rule_target OWNER TO postgres;

--
-- TOC entry 4620 (class 0 OID 0)
-- Dependencies: 372
-- Name: VIEW v_card_rule_target; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON VIEW db_pipeline.v_card_rule_target IS '규칙 대상을 행으로 복원';


--
-- TOC entry 381 (class 1259 OID 21657)
-- Name: v_common_cd_usage; Type: VIEW; Schema: db_pipeline; Owner: postgres
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


ALTER VIEW db_pipeline.v_common_cd_usage OWNER TO postgres;

--
-- TOC entry 4621 (class 0 OID 0)
-- Dependencies: 381
-- Name: VIEW v_common_cd_usage; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON VIEW db_pipeline.v_common_cd_usage IS '모든 공통코드 사용처(물리 컬럼·JSONB 키)와 소속 그룹. 공통코드 정합성 검증의 기준';


--
-- TOC entry 382 (class 1259 OID 21662)
-- Name: v_card_integrity_issue; Type: VIEW; Schema: db_pipeline; Owner: postgres
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
    ((l.card_id || '/'::text) || (l.ev_link_id)::text) AS issue_key
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
    ((l.card_id || '/'::text) || (l.ev_link_id)::text) AS issue_key
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
    ((l.card_id || '/'::text) || (l.ev_link_id)::text) AS issue_key
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
    ((l.card_id || '/'::text) || (l.ev_link_id)::text) AS issue_key
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


ALTER VIEW db_pipeline.v_card_integrity_issue OWNER TO postgres;

--
-- TOC entry 4622 (class 0 OID 0)
-- Dependencies: 382
-- Name: VIEW v_card_integrity_issue; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON VIEW db_pipeline.v_card_integrity_issue IS '승인 전 정합성 게이트. 물리 FK가 없으므로 행이 1건이라도 있으면 승인하지 않음. *_pending은 확정 전 항목의 값 누락(검토 대기)이고 나머지는 무결성 위반';


--
-- TOC entry 4170 (class 2606 OID 20893)
-- Name: card_ai_call card_ai_call_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_ai_call
    ADD CONSTRAINT card_ai_call_pkey PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq);


--
-- TOC entry 4167 (class 2606 OID 20895)
-- Name: card_ai_run card_ai_run_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_ai_run
    ADD CONSTRAINT card_ai_run_pkey PRIMARY KEY (card_ai_run_id);


--
-- TOC entry 4138 (class 2606 OID 21501)
-- Name: card_bnft card_bnft_card_id_bnft_cd_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_bnft
    ADD CONSTRAINT card_bnft_card_id_bnft_cd_key UNIQUE (card_id, bnft_cd);


--
-- TOC entry 4140 (class 2606 OID 21499)
-- Name: card_bnft card_bnft_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_bnft
    ADD CONSTRAINT card_bnft_pkey PRIMARY KEY (card_id, card_bnft_id);


--
-- TOC entry 4202 (class 2606 OID 21704)
-- Name: card_common_bnft_apply card_common_bnft_apply_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_common_bnft_apply
    ADD CONSTRAINT card_common_bnft_apply_pkey PRIMARY KEY (card_common_id, card_common_bnft_id, card_id);


--
-- TOC entry 4198 (class 2606 OID 21699)
-- Name: card_common_bnft card_common_bnft_cd_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_common_bnft
    ADD CONSTRAINT card_common_bnft_cd_key UNIQUE (card_common_id, bnft_cd);


--
-- TOC entry 4200 (class 2606 OID 21697)
-- Name: card_common_bnft card_common_bnft_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_common_bnft
    ADD CONSTRAINT card_common_bnft_pkey PRIMARY KEY (card_common_id, card_common_bnft_id);


--
-- TOC entry 4192 (class 2606 OID 21681)
-- Name: card_common card_common_common_cd_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_common
    ADD CONSTRAINT card_common_common_cd_key UNIQUE (common_cd);


--
-- TOC entry 4196 (class 2606 OID 21686)
-- Name: card_common_doc card_common_doc_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_common_doc
    ADD CONSTRAINT card_common_doc_pkey PRIMARY KEY (card_common_id, card_doc_id);


--
-- TOC entry 4194 (class 2606 OID 21679)
-- Name: card_common card_common_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_common
    ADD CONSTRAINT card_common_pkey PRIMARY KEY (card_common_id);


--
-- TOC entry 4161 (class 2606 OID 20897)
-- Name: card_doc_chunk card_doc_chunk_card_doc_chunk_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_card_doc_chunk_id_key UNIQUE (card_doc_chunk_id);


--
-- TOC entry 4163 (class 2606 OID 20899)
-- Name: card_doc_chunk card_doc_chunk_card_doc_id_chunk_seq_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_card_doc_id_chunk_seq_key UNIQUE (card_doc_id, chunk_seq);


--
-- TOC entry 4165 (class 2606 OID 20901)
-- Name: card_doc_chunk card_doc_chunk_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_pkey PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id);


--
-- TOC entry 4152 (class 2606 OID 20813)
-- Name: card_doc card_doc_doc_cd_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc
    ADD CONSTRAINT card_doc_doc_cd_key UNIQUE (doc_cd);


--
-- TOC entry 4154 (class 2606 OID 20815)
-- Name: card_doc card_doc_doc_sha256_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc
    ADD CONSTRAINT card_doc_doc_sha256_key UNIQUE (doc_sha256);


--
-- TOC entry 4159 (class 2606 OID 20903)
-- Name: card_doc_page card_doc_page_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc_page
    ADD CONSTRAINT card_doc_page_pkey PRIMARY KEY (card_doc_id, page_no);


--
-- TOC entry 4157 (class 2606 OID 20811)
-- Name: card_doc card_doc_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc
    ADD CONSTRAINT card_doc_pkey PRIMARY KEY (card_doc_id);


--
-- TOC entry 4146 (class 2606 OID 21645)
-- Name: card_evidence_link card_evidence_link_natural_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_evidence_link
    ADD CONSTRAINT card_evidence_link_natural_key UNIQUE NULLS NOT DISTINCT (card_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, ev_item_cd, ev_item_key, evidence_id);


--
-- TOC entry 4148 (class 2606 OID 21506)
-- Name: card_evidence_link card_evidence_link_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_evidence_link
    ADD CONSTRAINT card_evidence_link_pkey PRIMARY KEY (card_id, ev_link_id);


--
-- TOC entry 4183 (class 2606 OID 20905)
-- Name: card_excl_item card_excl_item_issuer_excl_item_nm_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_excl_item
    ADD CONSTRAINT card_excl_item_issuer_excl_item_nm_key UNIQUE (issuer, excl_item_nm);


--
-- TOC entry 4185 (class 2606 OID 20907)
-- Name: card_excl_item card_excl_item_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_excl_item
    ADD CONSTRAINT card_excl_item_pkey PRIMARY KEY (card_excl_item_id);


--
-- TOC entry 4174 (class 2606 OID 20909)
-- Name: card_extr_stg card_extr_stg_card_ai_run_id_card_doc_id_page_no_card_doc_c_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_card_ai_run_id_card_doc_id_page_no_card_doc_c_key UNIQUE (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, stg_item_seq);


--
-- TOC entry 4176 (class 2606 OID 20911)
-- Name: card_extr_stg card_extr_stg_card_extr_stg_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_card_extr_stg_id_key UNIQUE (card_extr_stg_id);


--
-- TOC entry 4178 (class 2606 OID 20913)
-- Name: card_extr_stg card_extr_stg_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_pkey PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id);


--
-- TOC entry 4136 (class 2606 OID 20708)
-- Name: card_product_doc card_product_doc_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_product_doc
    ADD CONSTRAINT card_product_doc_pkey PRIMARY KEY (card_id, card_doc_id);


--
-- TOC entry 4131 (class 2606 OID 20678)
-- Name: card_product card_product_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_product
    ADD CONSTRAINT card_product_pkey PRIMARY KEY (card_id);


--
-- TOC entry 4133 (class 2606 OID 20680)
-- Name: card_product card_product_product_cd_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_product
    ADD CONSTRAINT card_product_product_cd_key UNIQUE (product_cd);


--
-- TOC entry 4189 (class 2606 OID 20891)
-- Name: card_source_evidence card_source_evidence_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_source_evidence
    ADD CONSTRAINT card_source_evidence_pkey PRIMARY KEY (evidence_id);


--
-- TOC entry 4127 (class 2606 OID 20664)
-- Name: common_cd pk_common_cd; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.common_cd
    ADD CONSTRAINT pk_common_cd PRIMARY KEY (common_code_grp_id, common_cd);


--
-- TOC entry 4125 (class 2606 OID 20655)
-- Name: common_code_grp pk_common_code_grp; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.common_code_grp
    ADD CONSTRAINT pk_common_code_grp PRIMARY KEY (common_code_grp_id);


--
-- TOC entry 4155 (class 1259 OID 20921)
-- Name: card_doc_family_version_idx; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX card_doc_family_version_idx ON db_pipeline.card_doc USING btree (doc_family_cd, doc_version_no, doc_release_date);


--
-- TOC entry 4128 (class 1259 OID 20923)
-- Name: card_product_brand_opt_gin_idx; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX card_product_brand_opt_gin_idx ON db_pipeline.card_product USING gin (brand_opt_list jsonb_path_ops);


--
-- TOC entry 4134 (class 1259 OID 20924)
-- Name: card_product_doc_doc_idx; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX card_product_doc_doc_idx ON db_pipeline.card_product_doc USING btree (card_doc_id, card_id);


--
-- TOC entry 4129 (class 1259 OID 20922)
-- Name: card_product_kind_status_idx; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX card_product_kind_status_idx ON db_pipeline.card_product USING btree (card_kind_cd, product_status_cd);


--
-- TOC entry 4171 (class 1259 OID 20914)
-- Name: ix_card_ai_call_chunk_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_ai_call_chunk_key ON db_pipeline.card_ai_call USING btree (card_doc_chunk_id);


--
-- TOC entry 4172 (class 1259 OID 20915)
-- Name: ix_card_ai_call_doc_chunk_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_ai_call_doc_chunk_key ON db_pipeline.card_ai_call USING btree (card_doc_id, page_no, card_doc_chunk_id);


--
-- TOC entry 4168 (class 1259 OID 20916)
-- Name: ix_card_ai_run_doc_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_ai_run_doc_key ON db_pipeline.card_ai_run USING btree (run_target_card_doc_id);


--
-- TOC entry 4141 (class 1259 OID 20928)
-- Name: ix_card_bnft_brand_opt_gin; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_bnft_brand_opt_gin ON db_pipeline.card_bnft USING gin (bnft_brand_opt_cds);


--
-- TOC entry 4142 (class 1259 OID 20931)
-- Name: ix_card_bnft_cond_gin; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_bnft_cond_gin ON db_pipeline.card_bnft USING gin (bnft_cond_expr jsonb_path_ops);


--
-- TOC entry 4143 (class 1259 OID 20930)
-- Name: ix_card_bnft_relation_list_gin; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_bnft_relation_list_gin ON db_pipeline.card_bnft USING gin (relation_list jsonb_path_ops);


--
-- TOC entry 4144 (class 1259 OID 20929)
-- Name: ix_card_bnft_rule_list_gin; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_bnft_rule_list_gin ON db_pipeline.card_bnft USING gin (rule_list jsonb_path_ops);


--
-- TOC entry 4149 (class 1259 OID 20939)
-- Name: ix_card_evidence_link_evidence; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_evidence_link_evidence ON db_pipeline.card_evidence_link USING btree (evidence_id);


--
-- TOC entry 4150 (class 1259 OID 21510)
-- Name: ix_card_evidence_link_subject; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_evidence_link_subject ON db_pipeline.card_evidence_link USING btree (card_id, ev_subject_cd, card_bnft_id, rule_key);


--
-- TOC entry 4186 (class 1259 OID 20936)
-- Name: ix_card_excl_item_alias_gin; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_excl_item_alias_gin ON db_pipeline.card_excl_item USING gin (excl_alias_nms);


--
-- TOC entry 4187 (class 1259 OID 20917)
-- Name: ix_card_excl_item_concept_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_excl_item_concept_key ON db_pipeline.card_excl_item USING btree (excl_concept_cd);


--
-- TOC entry 4179 (class 1259 OID 20918)
-- Name: ix_card_extr_stg_chunk_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_extr_stg_chunk_key ON db_pipeline.card_extr_stg USING btree (card_doc_chunk_id);


--
-- TOC entry 4180 (class 1259 OID 20919)
-- Name: ix_card_extr_stg_excl_item_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_extr_stg_excl_item_key ON db_pipeline.card_extr_stg USING btree (card_excl_item_id);


--
-- TOC entry 4181 (class 1259 OID 20920)
-- Name: ix_card_extr_stg_status_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_extr_stg_status_key ON db_pipeline.card_extr_stg USING btree (stg_status, stg_kind_cd);


--
-- TOC entry 4190 (class 1259 OID 20937)
-- Name: ix_card_source_evidence_lookup; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_source_evidence_lookup ON db_pipeline.card_source_evidence USING btree (card_doc_id, page_no, card_doc_chunk_id);


-- Completed on 2026-11-03 05:25:12

--
-- PostgreSQL database dump complete
--

