--
-- PostgreSQL database dump
--

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.0

-- Started on 2026-10-30 12:43:56

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
-- TOC entry 109 (class 2615 OID 47522)
-- Name: card_benefit; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA card_benefit;


--
-- TOC entry 4358 (class 0 OID 0)
-- Dependencies: 109
-- Name: SCHEMA card_benefit; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA card_benefit IS '카드 상품설명서 PDF 수집·정제·AI 추출·검증(db_pipeline). 카드 마스터는 card_benefit.card_product';


--
-- TOC entry 668 (class 1255 OID 47531)
-- Name: fn_get_biz_id(text); Type: FUNCTION; Schema: card_benefit; Owner: -
--

CREATE FUNCTION card_benefit.fn_get_biz_id(p_tbl_nm text) RETURNS character varying
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $_$
DECLARE
    v_seq regclass;
BEGIN
    IF p_tbl_nm IS NULL OR p_tbl_nm !~ '^[A-Za-z][A-Za-z0-9_]*$' THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = format('Invalid card_benefit table name for business ID: %s', coalesce(p_tbl_nm, '<NULL>'));
    END IF;

    v_seq := to_regclass('card_benefit.seq_' || lower(p_tbl_nm));
    IF v_seq IS NULL OR NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS c
        WHERE c.oid = v_seq
          AND c.relkind = 'S'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42P01',
            MESSAGE = format('card_benefit ID sequence does not exist: %s', 'card_benefit.seq_' || lower(p_tbl_nm));
    END IF;

    RETURN to_char((clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date, 'YYYYMMDD')
        || '_' || lpad(nextval(v_seq)::text, 6, '0');
END;
$_$;


--
-- TOC entry 4359 (class 0 OID 0)
-- Dependencies: 668
-- Name: FUNCTION fn_get_biz_id(p_tbl_nm text); Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON FUNCTION card_benefit.fn_get_biz_id(p_tbl_nm text) IS 'card_benefit.seq_<테이블명> 시퀀스로 YYYYMMDD_000001 형식 업무 ID 발급(Asia/Seoul 기준)';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 427 (class 1259 OID 47607)
-- Name: card_ai_call; Type: TABLE; Schema: card_benefit; Owner: -
--

CREATE TABLE card_benefit.card_ai_call (
    run_id character varying(20) NOT NULL,
    chunk_id character varying(20) NOT NULL,
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
    CONSTRAINT ck_card_ai_call_call_seq CHECK ((call_seq > 0)),
    CONSTRAINT ck_card_ai_call_call_status CHECK (((call_status)::text = ANY (ARRAY[('SUCCEEDED'::character varying)::text, ('FAILED'::character varying)::text, ('PARSE_ERROR'::character varying)::text]))),
    CONSTRAINT ck_card_ai_call_succeeded CHECK ((((call_status)::text <> 'SUCCEEDED'::text) OR (call_resp_json IS NOT NULL)))
);


--
-- TOC entry 4360 (class 0 OID 0)
-- Dependencies: 427
-- Name: TABLE card_ai_call; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON TABLE card_benefit.card_ai_call IS 'AI 실행 내 청크별 호출 원 응답(정제 전 AI 출력)';


--
-- TOC entry 4361 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.run_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.run_id IS 'AI 실행 ID';


--
-- TOC entry 4362 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.chunk_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.chunk_id IS '입력 청크 ID';


--
-- TOC entry 4363 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.call_seq; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.call_seq IS '같은 실행·청크 내 호출 순번(재시도 시 증가)';


--
-- TOC entry 4364 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.call_input_sha256; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.call_input_sha256 IS '실제 입력(프롬프트+청크) SHA-256';


--
-- TOC entry 4365 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.call_status; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.call_status IS '호출 상태(SUCCEEDED, FAILED: 호출 실패, PARSE_ERROR: JSON 파싱 실패)';


--
-- TOC entry 4366 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.call_resp_raw; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.call_resp_raw IS '모델 응답 원문';


--
-- TOC entry 4367 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.call_resp_json; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.call_resp_json IS '파싱한 응답 JSON';


--
-- TOC entry 4368 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.call_error_msg; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.call_error_msg IS '오류 메시지';


--
-- TOC entry 4369 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.call_input_token_cnt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.call_input_token_cnt IS '입력 토큰 수';


--
-- TOC entry 4370 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.call_output_token_cnt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.call_output_token_cnt IS '출력 토큰 수';


--
-- TOC entry 4371 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.call_latency_ms; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.call_latency_ms IS '응답 시간(밀리초)';


--
-- TOC entry 4372 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.call_req_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.call_req_date IS '요청 일시';


--
-- TOC entry 4373 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.create_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.create_date IS '생성 일시';


--
-- TOC entry 4374 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.create_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4375 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.update_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.update_date IS '수정 일시';


--
-- TOC entry 4376 (class 0 OID 0)
-- Dependencies: 427
-- Name: COLUMN card_ai_call.update_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_call.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 426 (class 1259 OID 47590)
-- Name: card_ai_run; Type: TABLE; Schema: card_benefit; Owner: -
--

CREATE TABLE card_benefit.card_ai_run (
    run_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_ai_run'::text) NOT NULL,
    run_stage_cd character varying(20) NOT NULL,
    run_call_mthd_cd character varying(20) NOT NULL,
    run_model_nm character varying(100) NOT NULL,
    run_prompt_ver character varying(50) NOT NULL,
    run_prompt_txt text NOT NULL,
    run_param jsonb,
    run_target_doc_id character varying(20),
    run_status character varying(20) DEFAULT 'RUNNING'::character varying NOT NULL,
    run_start_date timestamp with time zone DEFAULT now() NOT NULL,
    run_end_date timestamp with time zone,
    run_note text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT ck_card_ai_run_run_call_mthd_cd CHECK (((run_call_mthd_cd)::text = ANY (ARRAY[('PYTHON_RELAY'::character varying)::text, ('PGAI'::character varying)::text, ('EDGE_FUNCTION'::character varying)::text, ('ETC'::character varying)::text]))),
    CONSTRAINT ck_card_ai_run_run_end_date CHECK (((run_end_date IS NULL) OR (run_end_date >= run_start_date))),
    CONSTRAINT ck_card_ai_run_run_stage_cd CHECK (((run_stage_cd)::text = ANY (ARRAY[('EXTRACT'::character varying)::text, ('VERIFY'::character varying)::text]))),
    CONSTRAINT ck_card_ai_run_run_status CHECK (((run_status)::text = ANY (ARRAY[('RUNNING'::character varying)::text, ('SUCCEEDED'::character varying)::text, ('PARTIAL'::character varying)::text, ('FAILED'::character varying)::text])))
);


--
-- TOC entry 4377 (class 0 OID 0)
-- Dependencies: 426
-- Name: TABLE card_ai_run; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON TABLE card_benefit.card_ai_run IS 'AI 추출·검증 실행 이력(실행 회차 단위)';


--
-- TOC entry 4378 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_id IS 'AI 실행 ID';


--
-- TOC entry 4379 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_stage_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_stage_cd IS '실행 단계(EXTRACT: 혜택·조건 추출, VERIFY: 추출 결과 의미 검증)';


--
-- TOC entry 4380 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_call_mthd_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_call_mthd_cd IS 'AI 호출 방식(PYTHON_RELAY, PGAI, EDGE_FUNCTION, ETC). 기술 검증 후 확정';


--
-- TOC entry 4381 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_model_nm; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_model_nm IS '사용 모델명';


--
-- TOC entry 4382 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_prompt_ver; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_prompt_ver IS '프롬프트 버전';


--
-- TOC entry 4383 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_prompt_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_prompt_txt IS '실행에 사용한 프롬프트 템플릿 원문';


--
-- TOC entry 4384 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_param; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_param IS '모델 호출 파라미터(temperature, 출력 스키마 등)';


--
-- TOC entry 4385 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_target_doc_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_target_doc_id IS '대상 원본 문서 ID(여러 문서 실행이면 NULL)';


--
-- TOC entry 4386 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_status; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_status IS '실행 상태(RUNNING, SUCCEEDED, PARTIAL: 일부 호출 실패, FAILED)';


--
-- TOC entry 4387 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_start_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_start_date IS '실행 시작 일시';


--
-- TOC entry 4388 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_end_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_end_date IS '실행 종료 일시';


--
-- TOC entry 4389 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.run_note; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.run_note IS '실행 메모';


--
-- TOC entry 4390 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.create_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.create_date IS '생성 일시';


--
-- TOC entry 4391 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.create_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4392 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.update_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.update_date IS '수정 일시';


--
-- TOC entry 4393 (class 0 OID 0)
-- Dependencies: 426
-- Name: COLUMN card_ai_run.update_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_ai_run.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 431 (class 1259 OID 47677)
-- Name: card_bnft; Type: TABLE; Schema: card_benefit; Owner: -
--

CREATE TABLE card_benefit.card_bnft (
    bnft_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_bnft'::text) NOT NULL,
    card_id bigint NOT NULL,
    doc_id character varying(20) NOT NULL,
    bnft_nm text NOT NULL,
    bnft_grp_nm text,
    bnft_type_cd character varying(20) NOT NULL,
    bnft_target_txt text,
    bnft_rate numeric(6,3),
    bnft_amt numeric(12,0),
    bnft_value_txt text,
    chunk_id character varying(20) NOT NULL,
    bnft_evidence_txt text NOT NULL,
    bnft_evidence_start_pos integer NOT NULL,
    bnft_evidence_end_pos integer NOT NULL,
    stg_id character varying(20) NOT NULL,
    bnft_status character varying(20) DEFAULT 'CONFIRMED'::character varying NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT ck_card_bnft_bnft_status CHECK (((bnft_status)::text = ANY (ARRAY[('CONFIRMED'::character varying)::text, ('RETIRED'::character varying)::text]))),
    CONSTRAINT ck_card_bnft_bnft_type_cd CHECK (((bnft_type_cd)::text = ANY (ARRAY[('DISCOUNT'::character varying)::text, ('CASHBACK'::character varying)::text, ('POINT'::character varying)::text, ('FEE_WAIVER'::character varying)::text, ('SERVICE'::character varying)::text, ('INSTALLMENT'::character varying)::text, ('ETC'::character varying)::text]))),
    CONSTRAINT ck_card_bnft_evidence_pos CHECK (((bnft_evidence_start_pos >= 1) AND (bnft_evidence_end_pos >= bnft_evidence_start_pos)))
);


--
-- TOC entry 4394 (class 0 OID 0)
-- Dependencies: 431
-- Name: TABLE card_bnft; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON TABLE card_benefit.card_bnft IS '검증 완료 혜택(db_pipeline 결과 B, 문서 버전별)';


--
-- TOC entry 4395 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_id IS '혜택 ID(Neo4j Benefit 노드 키)';


--
-- TOC entry 4396 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.card_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.card_id IS '카드 상품 ID(card_doc.card_id와 일치해야 함)';


--
-- TOC entry 4397 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.doc_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.doc_id IS '근거 원본 문서 ID';


--
-- TOC entry 4398 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_nm; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_nm IS '혜택명';


--
-- TOC entry 4399 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_grp_nm; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_grp_nm IS '혜택 서비스 영역명(예: ONE PICK, ONE MORE)';


--
-- TOC entry 4400 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_type_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_type_cd IS '혜택 유형(DISCOUNT, CASHBACK, POINT, FEE_WAIVER, SERVICE, INSTALLMENT, ETC)';


--
-- TOC entry 4401 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_target_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_target_txt IS '대상 가맹점·업종 원문 표기';


--
-- TOC entry 4402 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_rate; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_rate IS '대표 할인·적립률(%). 구간별 값은 card_cond TIER';


--
-- TOC entry 4403 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_amt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_amt IS '대표 정액 혜택 금액(원)';


--
-- TOC entry 4404 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_value_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_value_txt IS '혜택 값 원문 표기';


--
-- TOC entry 4405 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.chunk_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.chunk_id IS '근거 청크 ID';


--
-- TOC entry 4406 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_evidence_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_evidence_txt IS '근거 원문 문장';


--
-- TOC entry 4407 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_evidence_start_pos; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_evidence_start_pos IS '근거의 chunk_raw_txt 내 시작 위치';


--
-- TOC entry 4408 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_evidence_end_pos; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_evidence_end_pos IS '근거의 chunk_raw_txt 내 끝 위치';


--
-- TOC entry 4409 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.stg_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.stg_id IS '확정 근거 staging ID';


--
-- TOC entry 4410 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.bnft_status; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.bnft_status IS '상태(CONFIRMED, RETIRED: 신규 문서 버전으로 대체)';


--
-- TOC entry 4411 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.create_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.create_date IS '생성 일시';


--
-- TOC entry 4412 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.create_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4413 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.update_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.update_date IS '수정 일시';


--
-- TOC entry 4414 (class 0 OID 0)
-- Dependencies: 431
-- Name: COLUMN card_bnft.update_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_bnft.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 432 (class 1259 OID 47696)
-- Name: card_cond; Type: TABLE; Schema: card_benefit; Owner: -
--

CREATE TABLE card_benefit.card_cond (
    cond_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_cond'::text) NOT NULL,
    card_id bigint NOT NULL,
    doc_id character varying(20) NOT NULL,
    bnft_id character varying(20),
    cond_apply_lvl_cd character varying(20) NOT NULL,
    cond_type_cd character varying(20) NOT NULL,
    excl_item_id character varying(20),
    cond_excl_raw_txt text,
    cond_basis_cd character varying(20) DEFAULT 'NONE'::character varying NOT NULL,
    cond_min_amt numeric(12,0),
    cond_max_amt numeric(12,0),
    cond_rate numeric(6,3),
    cond_amt numeric(12,0),
    cond_limit_amt numeric(12,0),
    cond_limit_cnt integer,
    cond_period_cd character varying(20) DEFAULT 'NONE'::character varying NOT NULL,
    cond_modality_cd character varying(20) DEFAULT 'CONFIRMED'::character varying NOT NULL,
    cond_value_txt text,
    cond_target_txt text,
    cond_natural_key character varying(64) NOT NULL,
    cond_policy_cand_key character varying(64),
    chunk_id character varying(20) NOT NULL,
    cond_evidence_txt text NOT NULL,
    cond_evidence_start_pos integer NOT NULL,
    cond_evidence_end_pos integer NOT NULL,
    stg_id character varying(20) NOT NULL,
    cond_status character varying(20) DEFAULT 'CONFIRMED'::character varying NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT ck_card_cond_amt_range CHECK (((cond_min_amt IS NULL) OR (cond_max_amt IS NULL) OR (cond_min_amt <= cond_max_amt))),
    CONSTRAINT ck_card_cond_apply_lvl CHECK (((((cond_apply_lvl_cd)::text = 'CARD'::text) AND (bnft_id IS NULL)) OR (((cond_apply_lvl_cd)::text = 'BENEFIT'::text) AND (bnft_id IS NOT NULL)))),
    CONSTRAINT ck_card_cond_cond_basis_cd CHECK (((cond_basis_cd)::text = ANY (ARRAY[('PREV_MONTH_SPEND'::character varying)::text, ('TXN_AMT'::character varying)::text, ('MONTH_USAGE'::character varying)::text, ('NONE'::character varying)::text]))),
    CONSTRAINT ck_card_cond_cond_modality_cd CHECK (((cond_modality_cd)::text = ANY (ARRAY[('CONFIRMED'::character varying)::text, ('POSSIBLE'::character varying)::text]))),
    CONSTRAINT ck_card_cond_cond_period_cd CHECK (((cond_period_cd)::text = ANY (ARRAY[('TXN'::character varying)::text, ('DAY'::character varying)::text, ('MONTH'::character varying)::text, ('YEAR'::character varying)::text, ('NONE'::character varying)::text]))),
    CONSTRAINT ck_card_cond_cond_status CHECK (((cond_status)::text = ANY (ARRAY[('CONFIRMED'::character varying)::text, ('RETIRED'::character varying)::text]))),
    CONSTRAINT ck_card_cond_cond_type_cd CHECK (((cond_type_cd)::text = ANY (ARRAY[('SPEND_REQ'::character varying)::text, ('SPEND_EXCL'::character varying)::text, ('BNFT_EXCL'::character varying)::text, ('LIMIT'::character varying)::text, ('TIER'::character varying)::text, ('USAGE_REQ'::character varying)::text, ('GRACE'::character varying)::text, ('MERCHANT_RULE'::character varying)::text, ('ETC'::character varying)::text]))),
    CONSTRAINT ck_card_cond_evidence_pos CHECK (((cond_evidence_start_pos >= 1) AND (cond_evidence_end_pos >= cond_evidence_start_pos))),
    CONSTRAINT ck_card_cond_excl_item CHECK ((((cond_type_cd)::text <> ALL (ARRAY[('SPEND_EXCL'::character varying)::text, ('BNFT_EXCL'::character varying)::text])) OR ((excl_item_id IS NOT NULL) AND (cond_excl_raw_txt IS NOT NULL))))
);


--
-- TOC entry 4415 (class 0 OID 0)
-- Dependencies: 432
-- Name: TABLE card_cond; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON TABLE card_benefit.card_cond IS '검증 완료 조건(전월실적·실적 제외·혜택 제외·한도·구간·예외; 카드·혜택별 정책 인스턴스)';


--
-- TOC entry 4416 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_id IS '조건 ID(Neo4j Condition 노드·EXCLUDES 관계 키)';


--
-- TOC entry 4417 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.card_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.card_id IS '카드 상품 ID(card_doc.card_id와 일치해야 함)';


--
-- TOC entry 4418 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.doc_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.doc_id IS '근거 원본 문서 ID';


--
-- TOC entry 4419 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.bnft_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.bnft_id IS '조건이 걸린 혜택 ID(카드 전체 조건이면 NULL)';


--
-- TOC entry 4420 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_apply_lvl_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_apply_lvl_cd IS '적용 수준(CARD: 카드 전체, BENEFIT: 특정 혜택)';


--
-- TOC entry 4421 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_type_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_type_cd IS '조건 유형(SPEND_REQ: 전월실적 요건, SPEND_EXCL: 실적 산정 제외, BNFT_EXCL: 혜택 적용 제외, LIMIT: 한도, TIER: 구간별 혜택률·금액, USAGE_REQ: 건당 이용 요건, GRACE: 유예, MERCHANT_RULE: 가맹점 분류 규칙, ETC)';


--
-- TOC entry 4422 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.excl_item_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.excl_item_id IS '표준 제외 항목 ID(SPEND_EXCL·BNFT_EXCL 필수)';


--
-- TOC entry 4423 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_excl_raw_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_excl_raw_txt IS '제외 항목 원문 표기';


--
-- TOC entry 4424 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_basis_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_basis_cd IS '금액 기준(PREV_MONTH_SPEND, TXN_AMT, MONTH_USAGE, NONE)';


--
-- TOC entry 4425 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_min_amt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_min_amt IS '구간 하한 금액(원, 이상). 실적 무관은 SPEND_REQ + 0';


--
-- TOC entry 4426 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_max_amt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_max_amt IS '구간 상한 금액(원, 미만)';


--
-- TOC entry 4427 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_rate; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_rate IS '구간 할인·적립률(%)';


--
-- TOC entry 4428 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_amt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_amt IS '구간 정액 혜택 금액(원)';


--
-- TOC entry 4429 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_limit_amt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_limit_amt IS '한도 금액(원)';


--
-- TOC entry 4430 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_limit_cnt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_limit_cnt IS '한도 횟수';


--
-- TOC entry 4431 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_period_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_period_cd IS '한도 기간(TXN, DAY, MONTH, YEAR, NONE)';


--
-- TOC entry 4432 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_modality_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_modality_cd IS '적용 확정성(CONFIRMED: 확정, POSSIBLE: 제외될 수 있음)';


--
-- TOC entry 4433 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_value_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_value_txt IS '금액·비율·횟수 원문 표기';


--
-- TOC entry 4434 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_target_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_target_txt IS '대상 가맹점·업종·거래 원문 표기';


--
-- TOC entry 4435 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_natural_key; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_natural_key IS '조건 자연키 SHA-256(카드·혜택·유형·제외 항목·기준·값). 재적재 중복 방지';


--
-- TOC entry 4436 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_policy_cand_key; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_policy_cand_key IS '동일 정책 후보 키 SHA-256(카드사·유형·적용 범위·제외 항목·값, 카드 제외). 자동 병합 근거 아님';


--
-- TOC entry 4437 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.chunk_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.chunk_id IS '근거 청크 ID';


--
-- TOC entry 4438 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_evidence_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_evidence_txt IS '근거 원문 문장';


--
-- TOC entry 4439 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_evidence_start_pos; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_evidence_start_pos IS '근거의 chunk_raw_txt 내 시작 위치';


--
-- TOC entry 4440 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_evidence_end_pos; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_evidence_end_pos IS '근거의 chunk_raw_txt 내 끝 위치';


--
-- TOC entry 4441 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.stg_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.stg_id IS '확정 근거 staging ID';


--
-- TOC entry 4442 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.cond_status; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.cond_status IS '상태(CONFIRMED, RETIRED: 신규 문서 버전으로 대체)';


--
-- TOC entry 4443 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.create_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.create_date IS '생성 일시';


--
-- TOC entry 4444 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.create_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4445 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.update_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.update_date IS '수정 일시';


--
-- TOC entry 4446 (class 0 OID 0)
-- Dependencies: 432
-- Name: COLUMN card_cond.update_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_cond.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 423 (class 1259 OID 47532)
-- Name: card_doc; Type: TABLE; Schema: card_benefit; Owner: -
--

CREATE TABLE card_benefit.card_doc (
    doc_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_doc'::text) NOT NULL,
    card_id bigint NOT NULL,
    doc_cd character varying(50) NOT NULL,
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
    CONSTRAINT ck_card_doc_doc_page_cnt CHECK (((doc_page_cnt IS NULL) OR (doc_page_cnt > 0))),
    CONSTRAINT ck_card_doc_doc_sha256 CHECK (((doc_sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_card_doc_doc_status CHECK (((doc_status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('SUPERSEDED'::character varying)::text, ('EXCLUDED'::character varying)::text]))),
    CONSTRAINT ck_card_doc_doc_type_cd CHECK (((doc_type_cd)::text = ANY (ARRAY[('PRODUCT_GUIDE'::character varying)::text, ('TERMS'::character varying)::text, ('ETC'::character varying)::text]))),
    CONSTRAINT ck_card_doc_doc_version_no CHECK ((doc_version_no > 0))
);


--
-- TOC entry 4447 (class 0 OID 0)
-- Dependencies: 423
-- Name: TABLE card_doc; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON TABLE card_benefit.card_doc IS '카드 상품설명서 원본 문서(문서 버전 단위)';


--
-- TOC entry 4448 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_id IS '원본 문서 ID';


--
-- TOC entry 4449 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.card_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.card_id IS '카드 상품 ID(card_benefit.card_product.card_id 논리 참조)';


--
-- TOC entry 4450 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_cd IS '파이프라인 공통 문서 코드(예: HANA_15650_20260429). 결과 A·B 비교 키 후보';


--
-- TOC entry 4451 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_type_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_type_cd IS '문서 유형(PRODUCT_GUIDE: 상품설명서, TERMS: 약관, ETC)';


--
-- TOC entry 4452 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_title; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_title IS '문서 제목';


--
-- TOC entry 4453 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_source_url; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_source_url IS '공식 출처 URL';


--
-- TOC entry 4454 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_file_nm; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_file_nm IS '수집 파일명';


--
-- TOC entry 4455 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_file_size; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_file_size IS '수집 파일 크기(바이트)';


--
-- TOC entry 4456 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_sha256; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_sha256 IS '수집 파일 SHA-256(소문자 16진수 64자)';


--
-- TOC entry 4457 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_page_cnt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_page_cnt IS 'PDF 페이지 수';


--
-- TOC entry 4458 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_review_no; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_review_no IS '준법심의·여신협회 심의필 번호 원문';


--
-- TOC entry 4459 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_review_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_review_date IS '심의일';


--
-- TOC entry 4460 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_release_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_release_date IS '상품 출시일';


--
-- TOC entry 4461 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_collect_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_collect_date IS '파일 수집(다운로드) 일시';


--
-- TOC entry 4462 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_version_no; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_version_no IS '카드·문서 유형 내 문서 버전 번호(1부터)';


--
-- TOC entry 4463 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_status; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_status IS '문서 상태(ACTIVE: 현재 유효, SUPERSEDED: 신규 버전으로 대체, EXCLUDED: 분석 제외)';


--
-- TOC entry 4464 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.doc_note; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.doc_note IS '문서 범위·확인 사항 메모';


--
-- TOC entry 4465 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.create_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.create_date IS '생성 일시';


--
-- TOC entry 4466 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.create_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4467 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.update_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.update_date IS '수정 일시';


--
-- TOC entry 4468 (class 0 OID 0)
-- Dependencies: 423
-- Name: COLUMN card_doc.update_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 425 (class 1259 OID 47570)
-- Name: card_doc_chunk; Type: TABLE; Schema: card_benefit; Owner: -
--

CREATE TABLE card_benefit.card_doc_chunk (
    chunk_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_doc_chunk'::text) NOT NULL,
    doc_id character varying(20) NOT NULL,
    page_no smallint NOT NULL,
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
    CONSTRAINT ck_card_doc_chunk_chunk_seq CHECK ((chunk_seq > 0)),
    CONSTRAINT ck_card_doc_chunk_chunk_status CHECK (((chunk_status)::text = ANY (ARRAY[('RAW'::character varying)::text, ('CLEANED'::character varying)::text, ('EXCLUDED'::character varying)::text]))),
    CONSTRAINT ck_card_doc_chunk_chunk_type_cd CHECK (((chunk_type_cd)::text = ANY (ARRAY[('BODY'::character varying)::text, ('TABLE'::character varying)::text, ('NOTICE'::character varying)::text, ('HEADER_FOOTER'::character varying)::text, ('ETC'::character varying)::text]))),
    CONSTRAINT ck_card_doc_chunk_cleaned CHECK ((((chunk_status)::text <> 'CLEANED'::text) OR ((chunk_clean_txt IS NOT NULL) AND (chunk_clean_rule_ver IS NOT NULL)))),
    CONSTRAINT ck_card_doc_chunk_pos CHECK (((chunk_start_pos >= 1) AND (chunk_end_pos >= chunk_start_pos)))
);


--
-- TOC entry 4469 (class 0 OID 0)
-- Dependencies: 425
-- Name: TABLE card_doc_chunk; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON TABLE card_benefit.card_doc_chunk IS '문서 청크(조항·표·안내 단위) 원문과 SQL 정제 결과';


--
-- TOC entry 4470 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.chunk_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_id IS '청크 ID';


--
-- TOC entry 4471 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.doc_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.doc_id IS '원본 문서 ID';


--
-- TOC entry 4472 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.page_no; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.page_no IS '청크가 속한 페이지 번호(청크는 페이지를 넘지 않음)';


--
-- TOC entry 4473 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.chunk_seq; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_seq IS '문서 내 청크 순번(1부터)';


--
-- TOC entry 4474 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.chunk_section_nm; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_section_nm IS '원문 절 제목(예: [실적 산정 기준], 서비스 제외 대상)';


--
-- TOC entry 4475 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.chunk_type_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_type_cd IS '청크 유형(BODY, TABLE, NOTICE: 유의사항, HEADER_FOOTER: 머리말·꼬리말, ETC)';


--
-- TOC entry 4476 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.chunk_start_pos; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_start_pos IS 'page_raw_txt 내 시작 문자 위치(1부터, PostgreSQL substr 기준)';


--
-- TOC entry 4477 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.chunk_end_pos; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_end_pos IS 'page_raw_txt 내 끝 문자 위치(포함)';


--
-- TOC entry 4478 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.chunk_raw_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_raw_txt IS '청크 원문(정제 전, page_raw_txt의 부분 문자열)';


--
-- TOC entry 4479 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.chunk_clean_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_clean_txt IS 'SQL 정제 후 텍스트(AI 입력)';


--
-- TOC entry 4480 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.chunk_status; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_status IS '청크 상태(RAW: 분리만 됨, CLEANED: 정제 완료, EXCLUDED: 추출 대상 제외)';


--
-- TOC entry 4481 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.chunk_split_rule_ver; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_split_rule_ver IS '청크 분리 규칙 버전';


--
-- TOC entry 4482 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.chunk_clean_rule_ver; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_clean_rule_ver IS 'SQL 정제 규칙 버전';


--
-- TOC entry 4483 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.create_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.create_date IS '생성 일시';


--
-- TOC entry 4484 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.create_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4485 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.update_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.update_date IS '수정 일시';


--
-- TOC entry 4486 (class 0 OID 0)
-- Dependencies: 425
-- Name: COLUMN card_doc_chunk.update_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_chunk.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 424 (class 1259 OID 47557)
-- Name: card_doc_page; Type: TABLE; Schema: card_benefit; Owner: -
--

CREATE TABLE card_benefit.card_doc_page (
    doc_id character varying(20) NOT NULL,
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
    CONSTRAINT ck_card_doc_page_page_char_cnt CHECK ((page_char_cnt >= 0)),
    CONSTRAINT ck_card_doc_page_page_layer_cd CHECK (((page_layer_cd)::text = ANY (ARRAY[('TEXT'::character varying)::text, ('IMAGE'::character varying)::text, ('MIXED'::character varying)::text, ('UNKNOWN'::character varying)::text]))),
    CONSTRAINT ck_card_doc_page_page_no CHECK ((page_no > 0))
);


--
-- TOC entry 4487 (class 0 OID 0)
-- Dependencies: 424
-- Name: TABLE card_doc_page; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON TABLE card_benefit.card_doc_page IS '문서 페이지별 추출 원문(정제 전, 적재 후 변경 금지)';


--
-- TOC entry 4488 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.doc_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.doc_id IS '원본 문서 ID';


--
-- TOC entry 4489 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.page_no; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.page_no IS 'PDF 페이지 번호(1부터)';


--
-- TOC entry 4490 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.page_raw_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.page_raw_txt IS '추출기가 반환한 페이지 텍스트 원문(가공 없음)';


--
-- TOC entry 4491 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.page_char_cnt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.page_char_cnt IS '페이지 원문 문자 수';


--
-- TOC entry 4492 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.page_txt_sha256; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.page_txt_sha256 IS '페이지 원문 SHA-256(재추출 시 변경 감지)';


--
-- TOC entry 4493 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.page_layer_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.page_layer_cd IS '텍스트 레이어 유형(TEXT, IMAGE, MIXED: 일부 표가 이미지, UNKNOWN)';


--
-- TOC entry 4494 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.page_extractor_nm; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.page_extractor_nm IS '텍스트 추출기명(예: PyMuPDF)';


--
-- TOC entry 4495 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.page_extractor_ver; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.page_extractor_ver IS '텍스트 추출기 버전';


--
-- TOC entry 4496 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.page_note; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.page_note IS '추출 한계·확인 메모(표 미탐지 등)';


--
-- TOC entry 4497 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.create_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.create_date IS '생성 일시';


--
-- TOC entry 4498 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.create_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4499 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.update_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.update_date IS '수정 일시';


--
-- TOC entry 4500 (class 0 OID 0)
-- Dependencies: 424
-- Name: COLUMN card_doc_page.update_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_doc_page.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 428 (class 1259 OID 47622)
-- Name: card_excl_item; Type: TABLE; Schema: card_benefit; Owner: -
--

CREATE TABLE card_benefit.card_excl_item (
    excl_item_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_excl_item'::text) NOT NULL,
    issuer text NOT NULL,
    excl_item_nm text NOT NULL,
    excl_concept_cd character varying(50),
    excl_item_desc text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


--
-- TOC entry 4501 (class 0 OID 0)
-- Dependencies: 428
-- Name: TABLE card_excl_item; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON TABLE card_benefit.card_excl_item IS '표준 제외 항목(카드사 범위 개념, 정책 아님)';


--
-- TOC entry 4502 (class 0 OID 0)
-- Dependencies: 428
-- Name: COLUMN card_excl_item.excl_item_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item.excl_item_id IS '표준 제외 항목 ID';


--
-- TOC entry 4503 (class 0 OID 0)
-- Dependencies: 428
-- Name: COLUMN card_excl_item.issuer; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item.issuer IS '카드사(card_product.issuer와 같은 표기). 병합은 같은 카드사 안에서만';


--
-- TOC entry 4504 (class 0 OID 0)
-- Dependencies: 428
-- Name: COLUMN card_excl_item.excl_item_nm; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item.excl_item_nm IS '표준 제외 항목명(예: 상품권·기프트카드 구매)';


--
-- TOC entry 4505 (class 0 OID 0)
-- Dependencies: 428
-- Name: COLUMN card_excl_item.excl_concept_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item.excl_concept_cd IS '카드사 공통 분류 개념 코드(예: GIFT_CERT_PURCHASE). 분류용이며 정책 동일을 뜻하지 않음';


--
-- TOC entry 4506 (class 0 OID 0)
-- Dependencies: 428
-- Name: COLUMN card_excl_item.excl_item_desc; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item.excl_item_desc IS '항목 설명·포함 범위';


--
-- TOC entry 4507 (class 0 OID 0)
-- Dependencies: 428
-- Name: COLUMN card_excl_item.create_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item.create_date IS '생성 일시';


--
-- TOC entry 4508 (class 0 OID 0)
-- Dependencies: 428
-- Name: COLUMN card_excl_item.create_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4509 (class 0 OID 0)
-- Dependencies: 428
-- Name: COLUMN card_excl_item.update_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item.update_date IS '수정 일시';


--
-- TOC entry 4510 (class 0 OID 0)
-- Dependencies: 428
-- Name: COLUMN card_excl_item.update_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 429 (class 1259 OID 47635)
-- Name: card_excl_item_als; Type: TABLE; Schema: card_benefit; Owner: -
--

CREATE TABLE card_benefit.card_excl_item_als (
    excl_item_id character varying(20) NOT NULL,
    excl_item_als_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_excl_item_als'::text) NOT NULL,
    excl_item_als_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


--
-- TOC entry 4511 (class 0 OID 0)
-- Dependencies: 429
-- Name: TABLE card_excl_item_als; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON TABLE card_benefit.card_excl_item_als IS '제외 항목 원문 표기 별칭(SQL 정규화 사전)';


--
-- TOC entry 4512 (class 0 OID 0)
-- Dependencies: 429
-- Name: COLUMN card_excl_item_als.excl_item_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item_als.excl_item_id IS '표준 제외 항목 ID';


--
-- TOC entry 4513 (class 0 OID 0)
-- Dependencies: 429
-- Name: COLUMN card_excl_item_als.excl_item_als_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item_als.excl_item_als_id IS '제외 항목 별칭 ID';


--
-- TOC entry 4514 (class 0 OID 0)
-- Dependencies: 429
-- Name: COLUMN card_excl_item_als.excl_item_als_nm; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item_als.excl_item_als_nm IS '원문 표기(공백 제거 비교 기준). 의미가 불확실한 표기(예: 상품/)는 등록하지 않음';


--
-- TOC entry 4515 (class 0 OID 0)
-- Dependencies: 429
-- Name: COLUMN card_excl_item_als.create_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item_als.create_date IS '생성 일시';


--
-- TOC entry 4516 (class 0 OID 0)
-- Dependencies: 429
-- Name: COLUMN card_excl_item_als.create_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item_als.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4517 (class 0 OID 0)
-- Dependencies: 429
-- Name: COLUMN card_excl_item_als.update_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item_als.update_date IS '수정 일시';


--
-- TOC entry 4518 (class 0 OID 0)
-- Dependencies: 429
-- Name: COLUMN card_excl_item_als.update_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_excl_item_als.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 430 (class 1259 OID 47647)
-- Name: card_extr_stg; Type: TABLE; Schema: card_benefit; Owner: -
--

CREATE TABLE card_benefit.card_extr_stg (
    stg_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_extr_stg'::text) NOT NULL,
    run_id character varying(20) NOT NULL,
    chunk_id character varying(20) NOT NULL,
    call_seq smallint NOT NULL,
    stg_item_seq smallint NOT NULL,
    card_id bigint NOT NULL,
    stg_kind_cd character varying(20) NOT NULL,
    stg_parent_stg_id character varying(20),
    stg_raw_item jsonb NOT NULL,
    stg_bnft_nm text,
    stg_bnft_grp_nm text,
    stg_bnft_type_cd character varying(20),
    stg_cond_type_cd character varying(20),
    stg_apply_lvl_cd character varying(20),
    stg_excl_raw_txt text,
    excl_item_id character varying(20),
    stg_basis_cd character varying(20),
    stg_min_amt numeric(12,0),
    stg_max_amt numeric(12,0),
    stg_rate numeric(6,3),
    stg_amt numeric(12,0),
    stg_limit_amt numeric(12,0),
    stg_limit_cnt integer,
    stg_period_cd character varying(20),
    stg_modality_cd character varying(20),
    stg_value_txt text,
    stg_target_txt text,
    stg_evidence_txt text NOT NULL,
    stg_evidence_start_pos integer,
    stg_evidence_end_pos integer,
    stg_sql_check_cd character varying(30),
    stg_ai_vrfy_cd character varying(20),
    stg_ai_vrfy_run_id character varying(20),
    stg_status character varying(20) DEFAULT 'PENDING_REVIEW'::character varying NOT NULL,
    stg_review_note text,
    stg_approved_date timestamp with time zone,
    stg_approved_user_id character varying(50),
    bnft_id character varying(20),
    cond_id character varying(20),
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT ck_card_extr_stg_amt_range CHECK (((stg_min_amt IS NULL) OR (stg_max_amt IS NULL) OR (stg_min_amt <= stg_max_amt))),
    CONSTRAINT ck_card_extr_stg_approval CHECK ((((stg_status)::text <> ALL (ARRAY[('AUTO_APPROVED'::character varying)::text, ('MANUAL_APPROVED'::character varying)::text])) OR (((stg_sql_check_cd)::text = 'OK'::text) AND (stg_evidence_start_pos IS NOT NULL) AND (((stg_cond_type_cd)::text <> ALL (ARRAY[('SPEND_EXCL'::character varying)::text, ('BNFT_EXCL'::character varying)::text])) OR (stg_cond_type_cd IS NULL) OR (excl_item_id IS NOT NULL))))),
    CONSTRAINT ck_card_extr_stg_evidence_pos CHECK (((stg_evidence_start_pos IS NULL) OR ((stg_evidence_start_pos >= 1) AND (stg_evidence_end_pos >= stg_evidence_start_pos)))),
    CONSTRAINT ck_card_extr_stg_kind_required CHECK (((((stg_kind_cd)::text = 'BENEFIT'::text) AND (stg_bnft_nm IS NOT NULL)) OR (((stg_kind_cd)::text = 'CONDITION'::text) AND (stg_cond_type_cd IS NOT NULL)))),
    CONSTRAINT ck_card_extr_stg_stg_ai_vrfy_cd CHECK (((stg_ai_vrfy_cd IS NULL) OR ((stg_ai_vrfy_cd)::text = ANY (ARRAY[('MATCH'::character varying)::text, ('MISMATCH'::character varying)::text, ('UNCERTAIN'::character varying)::text])))),
    CONSTRAINT ck_card_extr_stg_stg_apply_lvl_cd CHECK (((stg_apply_lvl_cd IS NULL) OR ((stg_apply_lvl_cd)::text = ANY (ARRAY[('CARD'::character varying)::text, ('BENEFIT'::character varying)::text])))),
    CONSTRAINT ck_card_extr_stg_stg_basis_cd CHECK (((stg_basis_cd IS NULL) OR ((stg_basis_cd)::text = ANY (ARRAY[('PREV_MONTH_SPEND'::character varying)::text, ('TXN_AMT'::character varying)::text, ('MONTH_USAGE'::character varying)::text, ('NONE'::character varying)::text])))),
    CONSTRAINT ck_card_extr_stg_stg_bnft_type_cd CHECK (((stg_bnft_type_cd IS NULL) OR ((stg_bnft_type_cd)::text = ANY (ARRAY[('DISCOUNT'::character varying)::text, ('CASHBACK'::character varying)::text, ('POINT'::character varying)::text, ('FEE_WAIVER'::character varying)::text, ('SERVICE'::character varying)::text, ('INSTALLMENT'::character varying)::text, ('ETC'::character varying)::text])))),
    CONSTRAINT ck_card_extr_stg_stg_cond_type_cd CHECK (((stg_cond_type_cd IS NULL) OR ((stg_cond_type_cd)::text = ANY (ARRAY[('SPEND_REQ'::character varying)::text, ('SPEND_EXCL'::character varying)::text, ('BNFT_EXCL'::character varying)::text, ('LIMIT'::character varying)::text, ('TIER'::character varying)::text, ('USAGE_REQ'::character varying)::text, ('GRACE'::character varying)::text, ('MERCHANT_RULE'::character varying)::text, ('ETC'::character varying)::text])))),
    CONSTRAINT ck_card_extr_stg_stg_item_seq CHECK ((stg_item_seq > 0)),
    CONSTRAINT ck_card_extr_stg_stg_kind_cd CHECK (((stg_kind_cd)::text = ANY (ARRAY[('BENEFIT'::character varying)::text, ('CONDITION'::character varying)::text]))),
    CONSTRAINT ck_card_extr_stg_stg_modality_cd CHECK (((stg_modality_cd IS NULL) OR ((stg_modality_cd)::text = ANY (ARRAY[('CONFIRMED'::character varying)::text, ('POSSIBLE'::character varying)::text])))),
    CONSTRAINT ck_card_extr_stg_stg_period_cd CHECK (((stg_period_cd IS NULL) OR ((stg_period_cd)::text = ANY (ARRAY[('TXN'::character varying)::text, ('DAY'::character varying)::text, ('MONTH'::character varying)::text, ('YEAR'::character varying)::text, ('NONE'::character varying)::text])))),
    CONSTRAINT ck_card_extr_stg_stg_status CHECK (((stg_status)::text = ANY (ARRAY[('PENDING_REVIEW'::character varying)::text, ('AUTO_APPROVED'::character varying)::text, ('MANUAL_APPROVED'::character varying)::text, ('REJECTED'::character varying)::text])))
);


--
-- TOC entry 4519 (class 0 OID 0)
-- Dependencies: 430
-- Name: TABLE card_extr_stg; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON TABLE card_benefit.card_extr_stg IS 'AI 추출 혜택·조건 staging(정제 전 원 항목, 정제 후 값, 검증·승인 상태)';


--
-- TOC entry 4520 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_id IS '추출 staging ID';


--
-- TOC entry 4521 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.run_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.run_id IS 'AI 추출 실행 ID';


--
-- TOC entry 4522 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.chunk_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.chunk_id IS '근거 청크 ID';


--
-- TOC entry 4523 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.call_seq; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.call_seq IS '응답을 만든 호출 순번(card_ai_call)';


--
-- TOC entry 4524 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_item_seq; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_item_seq IS '응답 내 항목 순번(1부터)';


--
-- TOC entry 4525 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.card_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.card_id IS '대상 카드 상품 ID(문서의 card_id)';


--
-- TOC entry 4526 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_kind_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_kind_cd IS '항목 종류(BENEFIT: 혜택, CONDITION: 조건)';


--
-- TOC entry 4527 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_parent_stg_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_parent_stg_id IS '조건이 걸린 혜택의 staging ID(카드 전체 조건이면 NULL)';


--
-- TOC entry 4528 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_raw_item; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_raw_item IS 'AI 응답의 항목 원본 JSON(정제 전)';


--
-- TOC entry 4529 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_bnft_nm; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_bnft_nm IS '혜택명';


--
-- TOC entry 4530 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_bnft_grp_nm; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_bnft_grp_nm IS '혜택 서비스 영역명(예: ONE PICK)';


--
-- TOC entry 4531 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_bnft_type_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_bnft_type_cd IS '혜택 유형(DISCOUNT, CASHBACK, POINT, FEE_WAIVER, SERVICE, INSTALLMENT, ETC)';


--
-- TOC entry 4532 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_cond_type_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_cond_type_cd IS '조건 유형(SPEND_REQ: 전월실적 요건, SPEND_EXCL: 실적 산정 제외, BNFT_EXCL: 혜택 적용 제외, LIMIT, TIER, USAGE_REQ, GRACE, MERCHANT_RULE, ETC)';


--
-- TOC entry 4533 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_apply_lvl_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_apply_lvl_cd IS '적용 수준(CARD: 카드 전체, BENEFIT: 특정 혜택)';


--
-- TOC entry 4534 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_excl_raw_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_excl_raw_txt IS '제외 항목 원문 표기';


--
-- TOC entry 4535 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.excl_item_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.excl_item_id IS '매핑된 표준 제외 항목 ID(미매핑 NULL)';


--
-- TOC entry 4536 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_basis_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_basis_cd IS '금액 기준(PREV_MONTH_SPEND: 전월실적, TXN_AMT: 건당 이용금액, MONTH_USAGE: 당월 이용, NONE)';


--
-- TOC entry 4537 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_min_amt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_min_amt IS '구간 하한 금액(원, 이상)';


--
-- TOC entry 4538 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_max_amt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_max_amt IS '구간 상한 금액(원, 미만)';


--
-- TOC entry 4539 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_rate; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_rate IS '할인·적립률(%)';


--
-- TOC entry 4540 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_amt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_amt IS '정액 혜택 금액(원)';


--
-- TOC entry 4541 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_limit_amt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_limit_amt IS '한도 금액(원)';


--
-- TOC entry 4542 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_limit_cnt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_limit_cnt IS '한도 횟수';


--
-- TOC entry 4543 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_period_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_period_cd IS '한도 기간(TXN, DAY, MONTH, YEAR, NONE)';


--
-- TOC entry 4544 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_modality_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_modality_cd IS '적용 확정성(CONFIRMED: 제외/적용, POSSIBLE: 제외될 수 있음)';


--
-- TOC entry 4545 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_value_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_value_txt IS '금액·비율·횟수 원문 표기';


--
-- TOC entry 4546 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_target_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_target_txt IS '대상 가맹점·업종 원문 표기';


--
-- TOC entry 4547 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_evidence_txt; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_evidence_txt IS 'AI가 제시한 근거 원문 문장';


--
-- TOC entry 4548 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_evidence_start_pos; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_evidence_start_pos IS '근거의 chunk_raw_txt 내 시작 위치(SQL 대조 성공 시 채움)';


--
-- TOC entry 4549 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_evidence_end_pos; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_evidence_end_pos IS '근거의 chunk_raw_txt 내 끝 위치';


--
-- TOC entry 4550 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_sql_check_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_sql_check_cd IS 'SQL 검증 결과(NULL: 미검사, OK, EVIDENCE_NOT_FOUND, SCHEMA_VIOLATION, DUPLICATE, ORPHAN_REF, UNMAPPED_ITEM, VALUE_PARSE_ERROR)';


--
-- TOC entry 4551 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_ai_vrfy_cd; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_ai_vrfy_cd IS 'AI 의미 검증 결과(NULL: 미실행, MATCH, MISMATCH, UNCERTAIN)';


--
-- TOC entry 4552 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_ai_vrfy_run_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_ai_vrfy_run_id IS 'AI 의미 검증 실행 ID';


--
-- TOC entry 4553 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_status; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_status IS '검토 상태(PENDING_REVIEW, AUTO_APPROVED, MANUAL_APPROVED, REJECTED)';


--
-- TOC entry 4554 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_review_note; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_review_note IS '검증 결과 및 검토 메모';


--
-- TOC entry 4555 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_approved_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_approved_date IS '승인 일시';


--
-- TOC entry 4556 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.stg_approved_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.stg_approved_user_id IS '승인 사용자 ID';


--
-- TOC entry 4557 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.bnft_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.bnft_id IS '확정 반영된 혜택 ID';


--
-- TOC entry 4558 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.cond_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.cond_id IS '확정 반영된 조건 ID';


--
-- TOC entry 4559 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.create_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.create_date IS '생성 일시';


--
-- TOC entry 4560 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.create_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4561 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.update_date; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.update_date IS '수정 일시';


--
-- TOC entry 4562 (class 0 OID 0)
-- Dependencies: 430
-- Name: COLUMN card_extr_stg.update_user_id; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON COLUMN card_benefit.card_extr_stg.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 417 (class 1259 OID 47525)
-- Name: seq_card_ai_run; Type: SEQUENCE; Schema: card_benefit; Owner: -
--

CREATE SEQUENCE card_benefit.seq_card_ai_run
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4563 (class 0 OID 0)
-- Dependencies: 417
-- Name: SEQUENCE seq_card_ai_run; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON SEQUENCE card_benefit.seq_card_ai_run IS 'AI 실행 ID 발급';


--
-- TOC entry 421 (class 1259 OID 47529)
-- Name: seq_card_bnft; Type: SEQUENCE; Schema: card_benefit; Owner: -
--

CREATE SEQUENCE card_benefit.seq_card_bnft
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4564 (class 0 OID 0)
-- Dependencies: 421
-- Name: SEQUENCE seq_card_bnft; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON SEQUENCE card_benefit.seq_card_bnft IS '확정 혜택 ID 발급';


--
-- TOC entry 422 (class 1259 OID 47530)
-- Name: seq_card_cond; Type: SEQUENCE; Schema: card_benefit; Owner: -
--

CREATE SEQUENCE card_benefit.seq_card_cond
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4565 (class 0 OID 0)
-- Dependencies: 422
-- Name: SEQUENCE seq_card_cond; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON SEQUENCE card_benefit.seq_card_cond IS '확정 조건 ID 발급';


--
-- TOC entry 415 (class 1259 OID 47523)
-- Name: seq_card_doc; Type: SEQUENCE; Schema: card_benefit; Owner: -
--

CREATE SEQUENCE card_benefit.seq_card_doc
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4566 (class 0 OID 0)
-- Dependencies: 415
-- Name: SEQUENCE seq_card_doc; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON SEQUENCE card_benefit.seq_card_doc IS '원본 문서 ID 발급';


--
-- TOC entry 416 (class 1259 OID 47524)
-- Name: seq_card_doc_chunk; Type: SEQUENCE; Schema: card_benefit; Owner: -
--

CREATE SEQUENCE card_benefit.seq_card_doc_chunk
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4567 (class 0 OID 0)
-- Dependencies: 416
-- Name: SEQUENCE seq_card_doc_chunk; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON SEQUENCE card_benefit.seq_card_doc_chunk IS '문서 청크 ID 발급';


--
-- TOC entry 419 (class 1259 OID 47527)
-- Name: seq_card_excl_item; Type: SEQUENCE; Schema: card_benefit; Owner: -
--

CREATE SEQUENCE card_benefit.seq_card_excl_item
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4568 (class 0 OID 0)
-- Dependencies: 419
-- Name: SEQUENCE seq_card_excl_item; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON SEQUENCE card_benefit.seq_card_excl_item IS '표준 제외 항목 ID 발급';


--
-- TOC entry 420 (class 1259 OID 47528)
-- Name: seq_card_excl_item_als; Type: SEQUENCE; Schema: card_benefit; Owner: -
--

CREATE SEQUENCE card_benefit.seq_card_excl_item_als
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4569 (class 0 OID 0)
-- Dependencies: 420
-- Name: SEQUENCE seq_card_excl_item_als; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON SEQUENCE card_benefit.seq_card_excl_item_als IS '제외 항목 별칭 ID 발급';


--
-- TOC entry 418 (class 1259 OID 47526)
-- Name: seq_card_extr_stg; Type: SEQUENCE; Schema: card_benefit; Owner: -
--

CREATE SEQUENCE card_benefit.seq_card_extr_stg
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


--
-- TOC entry 4570 (class 0 OID 0)
-- Dependencies: 418
-- Name: SEQUENCE seq_card_extr_stg; Type: COMMENT; Schema: card_benefit; Owner: -
--

COMMENT ON SEQUENCE card_benefit.seq_card_extr_stg IS 'AI 추출 staging ID 발급';


--
-- TOC entry 4347 (class 0 OID 47607)
-- Dependencies: 427
-- Data for Name: card_ai_call; Type: TABLE DATA; Schema: card_benefit; Owner: -
--

COPY card_benefit.card_ai_call (run_id, chunk_id, call_seq, call_input_sha256, call_status, call_resp_raw, call_resp_json, call_error_msg, call_input_token_cnt, call_output_token_cnt, call_latency_ms, call_req_date, create_date, create_user_id, update_date, update_user_id) FROM stdin;
\.


--
-- TOC entry 4346 (class 0 OID 47590)
-- Dependencies: 426
-- Data for Name: card_ai_run; Type: TABLE DATA; Schema: card_benefit; Owner: -
--

COPY card_benefit.card_ai_run (run_id, run_stage_cd, run_call_mthd_cd, run_model_nm, run_prompt_ver, run_prompt_txt, run_param, run_target_doc_id, run_status, run_start_date, run_end_date, run_note, create_date, create_user_id, update_date, update_user_id) FROM stdin;
\.


--
-- TOC entry 4351 (class 0 OID 47677)
-- Dependencies: 431
-- Data for Name: card_bnft; Type: TABLE DATA; Schema: card_benefit; Owner: -
--

COPY card_benefit.card_bnft (bnft_id, card_id, doc_id, bnft_nm, bnft_grp_nm, bnft_type_cd, bnft_target_txt, bnft_rate, bnft_amt, bnft_value_txt, chunk_id, bnft_evidence_txt, bnft_evidence_start_pos, bnft_evidence_end_pos, stg_id, bnft_status, create_date, create_user_id, update_date, update_user_id) FROM stdin;
\.


--
-- TOC entry 4352 (class 0 OID 47696)
-- Dependencies: 432
-- Data for Name: card_cond; Type: TABLE DATA; Schema: card_benefit; Owner: -
--

COPY card_benefit.card_cond (cond_id, card_id, doc_id, bnft_id, cond_apply_lvl_cd, cond_type_cd, excl_item_id, cond_excl_raw_txt, cond_basis_cd, cond_min_amt, cond_max_amt, cond_rate, cond_amt, cond_limit_amt, cond_limit_cnt, cond_period_cd, cond_modality_cd, cond_value_txt, cond_target_txt, cond_natural_key, cond_policy_cand_key, chunk_id, cond_evidence_txt, cond_evidence_start_pos, cond_evidence_end_pos, stg_id, cond_status, create_date, create_user_id, update_date, update_user_id) FROM stdin;
\.


--
-- TOC entry 4343 (class 0 OID 47532)
-- Dependencies: 423
-- Data for Name: card_doc; Type: TABLE DATA; Schema: card_benefit; Owner: -
--

COPY card_benefit.card_doc (doc_id, card_id, doc_cd, doc_type_cd, doc_title, doc_source_url, doc_file_nm, doc_file_size, doc_sha256, doc_page_cnt, doc_review_no, doc_review_date, doc_release_date, doc_collect_date, doc_version_no, doc_status, doc_note, create_date, create_user_id, update_date, update_user_id) FROM stdin;
\.


--
-- TOC entry 4345 (class 0 OID 47570)
-- Dependencies: 425
-- Data for Name: card_doc_chunk; Type: TABLE DATA; Schema: card_benefit; Owner: -
--

COPY card_benefit.card_doc_chunk (chunk_id, doc_id, page_no, chunk_seq, chunk_section_nm, chunk_type_cd, chunk_start_pos, chunk_end_pos, chunk_raw_txt, chunk_clean_txt, chunk_status, chunk_split_rule_ver, chunk_clean_rule_ver, create_date, create_user_id, update_date, update_user_id) FROM stdin;
\.


--
-- TOC entry 4344 (class 0 OID 47557)
-- Dependencies: 424
-- Data for Name: card_doc_page; Type: TABLE DATA; Schema: card_benefit; Owner: -
--

COPY card_benefit.card_doc_page (doc_id, page_no, page_raw_txt, page_char_cnt, page_txt_sha256, page_layer_cd, page_extractor_nm, page_extractor_ver, page_note, create_date, create_user_id, update_date, update_user_id) FROM stdin;
\.


--
-- TOC entry 4348 (class 0 OID 47622)
-- Dependencies: 428
-- Data for Name: card_excl_item; Type: TABLE DATA; Schema: card_benefit; Owner: -
--

COPY card_benefit.card_excl_item (excl_item_id, issuer, excl_item_nm, excl_concept_cd, excl_item_desc, create_date, create_user_id, update_date, update_user_id) FROM stdin;
\.


--
-- TOC entry 4349 (class 0 OID 47635)
-- Dependencies: 429
-- Data for Name: card_excl_item_als; Type: TABLE DATA; Schema: card_benefit; Owner: -
--

COPY card_benefit.card_excl_item_als (excl_item_id, excl_item_als_id, excl_item_als_nm, create_date, create_user_id, update_date, update_user_id) FROM stdin;
\.


--
-- TOC entry 4350 (class 0 OID 47647)
-- Dependencies: 430
-- Data for Name: card_extr_stg; Type: TABLE DATA; Schema: card_benefit; Owner: -
--

COPY card_benefit.card_extr_stg (stg_id, run_id, chunk_id, call_seq, stg_item_seq, card_id, stg_kind_cd, stg_parent_stg_id, stg_raw_item, stg_bnft_nm, stg_bnft_grp_nm, stg_bnft_type_cd, stg_cond_type_cd, stg_apply_lvl_cd, stg_excl_raw_txt, excl_item_id, stg_basis_cd, stg_min_amt, stg_max_amt, stg_rate, stg_amt, stg_limit_amt, stg_limit_cnt, stg_period_cd, stg_modality_cd, stg_value_txt, stg_target_txt, stg_evidence_txt, stg_evidence_start_pos, stg_evidence_end_pos, stg_sql_check_cd, stg_ai_vrfy_cd, stg_ai_vrfy_run_id, stg_status, stg_review_note, stg_approved_date, stg_approved_user_id, bnft_id, cond_id, create_date, create_user_id, update_date, update_user_id) FROM stdin;
\.


--
-- TOC entry 4571 (class 0 OID 0)
-- Dependencies: 417
-- Name: seq_card_ai_run; Type: SEQUENCE SET; Schema: card_benefit; Owner: -
--

SELECT pg_catalog.setval('card_benefit.seq_card_ai_run', 1, false);


--
-- TOC entry 4572 (class 0 OID 0)
-- Dependencies: 421
-- Name: seq_card_bnft; Type: SEQUENCE SET; Schema: card_benefit; Owner: -
--

SELECT pg_catalog.setval('card_benefit.seq_card_bnft', 1, false);


--
-- TOC entry 4573 (class 0 OID 0)
-- Dependencies: 422
-- Name: seq_card_cond; Type: SEQUENCE SET; Schema: card_benefit; Owner: -
--

SELECT pg_catalog.setval('card_benefit.seq_card_cond', 1, false);


--
-- TOC entry 4574 (class 0 OID 0)
-- Dependencies: 415
-- Name: seq_card_doc; Type: SEQUENCE SET; Schema: card_benefit; Owner: -
--

SELECT pg_catalog.setval('card_benefit.seq_card_doc', 1, false);


--
-- TOC entry 4575 (class 0 OID 0)
-- Dependencies: 416
-- Name: seq_card_doc_chunk; Type: SEQUENCE SET; Schema: card_benefit; Owner: -
--

SELECT pg_catalog.setval('card_benefit.seq_card_doc_chunk', 1, false);


--
-- TOC entry 4576 (class 0 OID 0)
-- Dependencies: 419
-- Name: seq_card_excl_item; Type: SEQUENCE SET; Schema: card_benefit; Owner: -
--

SELECT pg_catalog.setval('card_benefit.seq_card_excl_item', 1, false);


--
-- TOC entry 4577 (class 0 OID 0)
-- Dependencies: 420
-- Name: seq_card_excl_item_als; Type: SEQUENCE SET; Schema: card_benefit; Owner: -
--

SELECT pg_catalog.setval('card_benefit.seq_card_excl_item_als', 1, false);


--
-- TOC entry 4578 (class 0 OID 0)
-- Dependencies: 418
-- Name: seq_card_extr_stg; Type: SEQUENCE SET; Schema: card_benefit; Owner: -
--

SELECT pg_catalog.setval('card_benefit.seq_card_extr_stg', 1, false);


--
-- TOC entry 4152 (class 2606 OID 47620)
-- Name: card_ai_call pk_card_ai_call; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_ai_call
    ADD CONSTRAINT pk_card_ai_call PRIMARY KEY (run_id, chunk_id, call_seq);


--
-- TOC entry 4149 (class 2606 OID 47605)
-- Name: card_ai_run pk_card_ai_run; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_ai_run
    ADD CONSTRAINT pk_card_ai_run PRIMARY KEY (run_id);


--
-- TOC entry 4171 (class 2606 OID 47690)
-- Name: card_bnft pk_card_bnft; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_bnft
    ADD CONSTRAINT pk_card_bnft PRIMARY KEY (bnft_id);


--
-- TOC entry 4181 (class 2606 OID 47718)
-- Name: card_cond pk_card_cond; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_cond
    ADD CONSTRAINT pk_card_cond PRIMARY KEY (cond_id);


--
-- TOC entry 4132 (class 2606 OID 47549)
-- Name: card_doc pk_card_doc; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_doc
    ADD CONSTRAINT pk_card_doc PRIMARY KEY (doc_id);


--
-- TOC entry 4144 (class 2606 OID 47586)
-- Name: card_doc_chunk pk_card_doc_chunk; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_doc_chunk
    ADD CONSTRAINT pk_card_doc_chunk PRIMARY KEY (chunk_id);


--
-- TOC entry 4141 (class 2606 OID 47569)
-- Name: card_doc_page pk_card_doc_page; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_doc_page
    ADD CONSTRAINT pk_card_doc_page PRIMARY KEY (doc_id, page_no);


--
-- TOC entry 4155 (class 2606 OID 47631)
-- Name: card_excl_item pk_card_excl_item; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_excl_item
    ADD CONSTRAINT pk_card_excl_item PRIMARY KEY (excl_item_id);


--
-- TOC entry 4159 (class 2606 OID 47644)
-- Name: card_excl_item_als pk_card_excl_item_als; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_excl_item_als
    ADD CONSTRAINT pk_card_excl_item_als PRIMARY KEY (excl_item_id, excl_item_als_id);


--
-- TOC entry 4166 (class 2606 OID 47671)
-- Name: card_extr_stg pk_card_extr_stg; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_extr_stg
    ADD CONSTRAINT pk_card_extr_stg PRIMARY KEY (stg_id);


--
-- TOC entry 4173 (class 2606 OID 47692)
-- Name: card_bnft uq_card_bnft_bnft_nm; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_bnft
    ADD CONSTRAINT uq_card_bnft_bnft_nm UNIQUE (doc_id, bnft_nm);


--
-- TOC entry 4175 (class 2606 OID 47694)
-- Name: card_bnft uq_card_bnft_stg_id; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_bnft
    ADD CONSTRAINT uq_card_bnft_stg_id UNIQUE (stg_id);


--
-- TOC entry 4183 (class 2606 OID 47720)
-- Name: card_cond uq_card_cond_natural_key; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_cond
    ADD CONSTRAINT uq_card_cond_natural_key UNIQUE (doc_id, cond_natural_key);


--
-- TOC entry 4185 (class 2606 OID 47722)
-- Name: card_cond uq_card_cond_stg_id; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_cond
    ADD CONSTRAINT uq_card_cond_stg_id UNIQUE (stg_id);


--
-- TOC entry 4146 (class 2606 OID 47588)
-- Name: card_doc_chunk uq_card_doc_chunk_seq; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_doc_chunk
    ADD CONSTRAINT uq_card_doc_chunk_seq UNIQUE (doc_id, chunk_seq);


--
-- TOC entry 4135 (class 2606 OID 47551)
-- Name: card_doc uq_card_doc_doc_cd; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_doc
    ADD CONSTRAINT uq_card_doc_doc_cd UNIQUE (doc_cd);


--
-- TOC entry 4137 (class 2606 OID 47553)
-- Name: card_doc uq_card_doc_doc_sha256; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_doc
    ADD CONSTRAINT uq_card_doc_doc_sha256 UNIQUE (doc_sha256);


--
-- TOC entry 4139 (class 2606 OID 47555)
-- Name: card_doc uq_card_doc_version; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_doc
    ADD CONSTRAINT uq_card_doc_version UNIQUE (card_id, doc_type_cd, doc_version_no);


--
-- TOC entry 4161 (class 2606 OID 47646)
-- Name: card_excl_item_als uq_card_excl_item_als_excl_item_als_nm; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_excl_item_als
    ADD CONSTRAINT uq_card_excl_item_als_excl_item_als_nm UNIQUE (excl_item_id, excl_item_als_nm);


--
-- TOC entry 4157 (class 2606 OID 47633)
-- Name: card_excl_item uq_card_excl_item_excl_item_nm; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_excl_item
    ADD CONSTRAINT uq_card_excl_item_excl_item_nm UNIQUE (issuer, excl_item_nm);


--
-- TOC entry 4168 (class 2606 OID 47673)
-- Name: card_extr_stg uq_card_extr_stg_item_seq; Type: CONSTRAINT; Schema: card_benefit; Owner: -
--

ALTER TABLE ONLY card_benefit.card_extr_stg
    ADD CONSTRAINT uq_card_extr_stg_item_seq UNIQUE (run_id, chunk_id, call_seq, stg_item_seq);


--
-- TOC entry 4150 (class 1259 OID 47621)
-- Name: ix_card_ai_call_chunk_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_ai_call_chunk_key ON card_benefit.card_ai_call USING btree (chunk_id);


--
-- TOC entry 4147 (class 1259 OID 47606)
-- Name: ix_card_ai_run_doc_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_ai_run_doc_key ON card_benefit.card_ai_run USING btree (run_target_doc_id);


--
-- TOC entry 4169 (class 1259 OID 47695)
-- Name: ix_card_bnft_card_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_bnft_card_key ON card_benefit.card_bnft USING btree (card_id, doc_id);


--
-- TOC entry 4176 (class 1259 OID 47724)
-- Name: ix_card_cond_bnft_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_cond_bnft_key ON card_benefit.card_cond USING btree (bnft_id);


--
-- TOC entry 4177 (class 1259 OID 47723)
-- Name: ix_card_cond_card_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_cond_card_key ON card_benefit.card_cond USING btree (card_id, cond_type_cd);


--
-- TOC entry 4178 (class 1259 OID 47725)
-- Name: ix_card_cond_excl_item_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_cond_excl_item_key ON card_benefit.card_cond USING btree (excl_item_id, cond_type_cd);


--
-- TOC entry 4179 (class 1259 OID 47726)
-- Name: ix_card_cond_policy_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_cond_policy_key ON card_benefit.card_cond USING btree (cond_policy_cand_key);


--
-- TOC entry 4142 (class 1259 OID 47589)
-- Name: ix_card_doc_chunk_page_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_doc_chunk_page_key ON card_benefit.card_doc_chunk USING btree (doc_id, page_no);


--
-- TOC entry 4153 (class 1259 OID 47634)
-- Name: ix_card_excl_item_concept_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_excl_item_concept_key ON card_benefit.card_excl_item USING btree (excl_concept_cd);


--
-- TOC entry 4162 (class 1259 OID 47674)
-- Name: ix_card_extr_stg_chunk_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_extr_stg_chunk_key ON card_benefit.card_extr_stg USING btree (chunk_id);


--
-- TOC entry 4163 (class 1259 OID 47676)
-- Name: ix_card_extr_stg_excl_item_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_extr_stg_excl_item_key ON card_benefit.card_extr_stg USING btree (excl_item_id);


--
-- TOC entry 4164 (class 1259 OID 47675)
-- Name: ix_card_extr_stg_status_key; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE INDEX ix_card_extr_stg_status_key ON card_benefit.card_extr_stg USING btree (stg_status, stg_kind_cd);


--
-- TOC entry 4133 (class 1259 OID 47556)
-- Name: uq_card_doc_active; Type: INDEX; Schema: card_benefit; Owner: -
--

CREATE UNIQUE INDEX uq_card_doc_active ON card_benefit.card_doc USING btree (card_id, doc_type_cd) WHERE ((doc_status)::text = 'ACTIVE'::text);


-- Completed on 2026-10-30 12:44:03

--
-- PostgreSQL database dump complete
--

