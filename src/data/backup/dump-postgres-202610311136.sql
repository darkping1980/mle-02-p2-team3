--
-- PostgreSQL database dump
--

-- Dumped from database version 17.11
-- Dumped by pg_dump version 17.0

-- Started on 2026-10-31 11:36:11

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
-- TOC entry 23 (class 2615 OID 19115)
-- Name: db_pipeline; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA db_pipeline;


ALTER SCHEMA db_pipeline OWNER TO postgres;

--
-- TOC entry 4250 (class 0 OID 0)
-- Dependencies: 23
-- Name: SCHEMA db_pipeline; Type: COMMENT; Schema: -; Owner: postgres
--

COMMENT ON SCHEMA db_pipeline IS 'DB 기반 파이프라인 전용: 카드 상품설명서 PDF 수집·정제·AI 추출·검증. 카드 마스터는 card_benefit.card_product';


--
-- TOC entry 591 (class 1255 OID 19124)
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
-- TOC entry 4251 (class 0 OID 0)
-- Dependencies: 591
-- Name: FUNCTION fn_get_biz_id(p_tbl_nm text); Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON FUNCTION db_pipeline.fn_get_biz_id(p_tbl_nm text) IS 'db_pipeline.seq_<테이블명> 시퀀스로 YYYYMMDD_000001 형식 업무 ID 발급(Asia/Seoul 기준)';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 357 (class 1259 OID 19344)
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
    CONSTRAINT card_ai_call_call_status_check CHECK (((call_status)::text = ANY ((ARRAY['SUCCEEDED'::character varying, 'FAILED'::character varying, 'PARSE_ERROR'::character varying])::text[]))),
    CONSTRAINT card_ai_call_check CHECK ((((call_status)::text <> 'SUCCEEDED'::text) OR (call_resp_json IS NOT NULL)))
);


ALTER TABLE db_pipeline.card_ai_call OWNER TO postgres;

--
-- TOC entry 4252 (class 0 OID 0)
-- Dependencies: 357
-- Name: TABLE card_ai_call; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_ai_call IS 'AI 실행 내 청크별 호출 원 응답(정제 전 AI 출력)';


--
-- TOC entry 4253 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.card_ai_run_id IS 'AI 실행 ID';


--
-- TOC entry 4254 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.card_doc_id IS '원본 문서 ID(card_doc_chunk 부모 PK 승계)';


--
-- TOC entry 4255 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.page_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.page_no IS '청크가 속한 PDF 페이지 번호(card_doc_chunk 부모 PK 승계)';


--
-- TOC entry 4256 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.card_doc_chunk_id IS '입력 청크 ID';


--
-- TOC entry 4257 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.call_seq; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_seq IS '같은 실행·청크 내 호출 순번(재시도 시 증가)';


--
-- TOC entry 4258 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.call_input_sha256; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_input_sha256 IS '실제 입력(프롬프트+청크) SHA-256';


--
-- TOC entry 4259 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.call_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_status IS '호출 상태(SUCCEEDED, FAILED: 호출 실패, PARSE_ERROR: JSON 파싱 실패)';


--
-- TOC entry 4260 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.call_resp_raw; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_resp_raw IS '모델 응답 원문';


--
-- TOC entry 4261 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.call_resp_json; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_resp_json IS '파싱한 응답 JSON';


--
-- TOC entry 4262 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.call_error_msg; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_error_msg IS '오류 메시지';


--
-- TOC entry 4263 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.call_input_token_cnt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_input_token_cnt IS '입력 토큰 수';


--
-- TOC entry 4264 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.call_output_token_cnt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_output_token_cnt IS '출력 토큰 수';


--
-- TOC entry 4265 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.call_latency_ms; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_latency_ms IS '응답 시간(밀리초)';


--
-- TOC entry 4266 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.call_req_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.call_req_date IS '요청 일시';


--
-- TOC entry 4267 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.create_date IS '생성 일시';


--
-- TOC entry 4268 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4269 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.update_date IS '수정 일시';


--
-- TOC entry 4270 (class 0 OID 0)
-- Dependencies: 357
-- Name: COLUMN card_ai_call.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_call.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 352 (class 1259 OID 19183)
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
    CONSTRAINT card_ai_run_check CHECK (((run_end_date IS NULL) OR (run_end_date >= run_start_date))),
    CONSTRAINT card_ai_run_run_call_mthd_cd_check CHECK (((run_call_mthd_cd)::text = ANY ((ARRAY['PYTHON_RELAY'::character varying, 'PGAI'::character varying, 'EDGE_FUNCTION'::character varying, 'ETC'::character varying])::text[]))),
    CONSTRAINT card_ai_run_run_stage_cd_check CHECK (((run_stage_cd)::text = ANY ((ARRAY['EXTRACT'::character varying, 'VERIFY'::character varying])::text[]))),
    CONSTRAINT card_ai_run_run_status_check CHECK (((run_status)::text = ANY ((ARRAY['RUNNING'::character varying, 'SUCCEEDED'::character varying, 'PARTIAL'::character varying, 'FAILED'::character varying])::text[])))
);


ALTER TABLE db_pipeline.card_ai_run OWNER TO postgres;

--
-- TOC entry 4271 (class 0 OID 0)
-- Dependencies: 352
-- Name: TABLE card_ai_run; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_ai_run IS 'AI 추출·검증 실행 이력(실행 회차 단위)';


--
-- TOC entry 4272 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.card_ai_run_id IS 'AI 실행 ID';


--
-- TOC entry 4273 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.run_stage_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_stage_cd IS '실행 단계(EXTRACT: 혜택·조건 추출, VERIFY: 추출 결과 의미 검증)';


--
-- TOC entry 4274 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.run_call_mthd_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_call_mthd_cd IS 'AI 호출 방식(PYTHON_RELAY, PGAI, EDGE_FUNCTION, ETC). 기술 검증 후 확정';


--
-- TOC entry 4275 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.run_model_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_model_nm IS '사용 모델명';


--
-- TOC entry 4276 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.run_prompt_ver; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_prompt_ver IS '프롬프트 버전';


--
-- TOC entry 4277 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.run_prompt_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_prompt_txt IS '실행에 사용한 프롬프트 템플릿 원문';


--
-- TOC entry 4278 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.run_param; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_param IS '모델 호출 파라미터(temperature, 출력 스키마 등)';


--
-- TOC entry 4279 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.run_target_card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_target_card_doc_id IS '대상 원본 문서 ID(여러 문서 실행이면 NULL)';


--
-- TOC entry 4280 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.run_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_status IS '실행 상태(RUNNING, SUCCEEDED, PARTIAL: 일부 호출 실패, FAILED)';


--
-- TOC entry 4281 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.run_start_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_start_date IS '실행 시작 일시';


--
-- TOC entry 4282 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.run_end_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_end_date IS '실행 종료 일시';


--
-- TOC entry 4283 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.run_note; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.run_note IS '실행 메모';


--
-- TOC entry 4284 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.create_date IS '생성 일시';


--
-- TOC entry 4285 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4286 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.update_date IS '수정 일시';


--
-- TOC entry 4287 (class 0 OID 0)
-- Dependencies: 352
-- Name: COLUMN card_ai_run.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_ai_run.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 355 (class 1259 OID 19266)
-- Name: card_bnft; Type: TABLE; Schema: db_pipeline; Owner: postgres
--

CREATE TABLE db_pipeline.card_bnft (
    card_doc_id character varying(20) NOT NULL,
    card_bnft_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_bnft'::text) NOT NULL,
    card_id bigint NOT NULL,
    bnft_nm text NOT NULL,
    bnft_grp_nm text,
    bnft_type_cd character varying(20) NOT NULL,
    bnft_target_txt text,
    bnft_rate numeric(6,3),
    bnft_amt numeric(12,0),
    bnft_value_txt text,
    card_doc_chunk_id character varying(20) NOT NULL,
    bnft_evidence_txt text NOT NULL,
    bnft_evidence_start_pos integer NOT NULL,
    bnft_evidence_end_pos integer NOT NULL,
    card_extr_stg_id character varying(20) NOT NULL,
    bnft_status character varying(20) DEFAULT 'CONFIRMED'::character varying NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT card_bnft_bnft_status_check CHECK (((bnft_status)::text = ANY ((ARRAY['CONFIRMED'::character varying, 'RETIRED'::character varying])::text[]))),
    CONSTRAINT card_bnft_bnft_type_cd_check CHECK (((bnft_type_cd)::text = ANY ((ARRAY['DISCOUNT'::character varying, 'CASHBACK'::character varying, 'POINT'::character varying, 'FEE_WAIVER'::character varying, 'SERVICE'::character varying, 'INSTALLMENT'::character varying, 'ETC'::character varying])::text[]))),
    CONSTRAINT card_bnft_check CHECK (((bnft_evidence_start_pos >= 1) AND (bnft_evidence_end_pos >= bnft_evidence_start_pos)))
);


ALTER TABLE db_pipeline.card_bnft OWNER TO postgres;

--
-- TOC entry 4288 (class 0 OID 0)
-- Dependencies: 355
-- Name: TABLE card_bnft; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_bnft IS '검증 완료 혜택(db_pipeline 결과 B, 문서 버전별)';


--
-- TOC entry 4289 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.card_doc_id IS '근거 원본 문서 ID';


--
-- TOC entry 4290 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.card_bnft_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.card_bnft_id IS '혜택 ID(Neo4j Benefit 노드 키)';


--
-- TOC entry 4291 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.card_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.card_id IS '카드 상품 ID(card_doc.card_id와 일치해야 함)';


--
-- TOC entry 4292 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.bnft_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_nm IS '혜택명';


--
-- TOC entry 4293 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.bnft_grp_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_grp_nm IS '혜택 서비스 영역명(예: ONE PICK, ONE MORE)';


--
-- TOC entry 4294 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.bnft_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_type_cd IS '혜택 유형(DISCOUNT, CASHBACK, POINT, FEE_WAIVER, SERVICE, INSTALLMENT, ETC)';


--
-- TOC entry 4295 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.bnft_target_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_target_txt IS '대상 가맹점·업종 원문 표기';


--
-- TOC entry 4296 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.bnft_rate; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_rate IS '대표 할인·적립률(%). 구간별 값은 card_cond TIER';


--
-- TOC entry 4297 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.bnft_amt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_amt IS '대표 정액 혜택 금액(원)';


--
-- TOC entry 4298 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.bnft_value_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_value_txt IS '혜택 값 원문 표기';


--
-- TOC entry 4299 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.card_doc_chunk_id IS '근거 청크 ID';


--
-- TOC entry 4300 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.bnft_evidence_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_evidence_txt IS '근거 원문 문장';


--
-- TOC entry 4301 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.bnft_evidence_start_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_evidence_start_pos IS '근거의 chunk_raw_txt 내 시작 위치';


--
-- TOC entry 4302 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.bnft_evidence_end_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_evidence_end_pos IS '근거의 chunk_raw_txt 내 끝 위치';


--
-- TOC entry 4303 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.card_extr_stg_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.card_extr_stg_id IS '확정 근거 staging ID';


--
-- TOC entry 4304 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.bnft_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_status IS '상태(CONFIRMED, RETIRED: 신규 문서 버전으로 대체)';


--
-- TOC entry 4305 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.create_date IS '생성 일시';


--
-- TOC entry 4306 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4307 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.update_date IS '수정 일시';


--
-- TOC entry 4308 (class 0 OID 0)
-- Dependencies: 355
-- Name: COLUMN card_bnft.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 359 (class 1259 OID 19391)
-- Name: card_bnft_cond; Type: TABLE; Schema: db_pipeline; Owner: postgres
--

CREATE TABLE db_pipeline.card_bnft_cond (
    card_doc_id character varying(20) NOT NULL,
    card_bnft_id character varying(20) NOT NULL,
    card_cond_id character varying(20) NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


ALTER TABLE db_pipeline.card_bnft_cond OWNER TO postgres;

--
-- TOC entry 4309 (class 0 OID 0)
-- Dependencies: 359
-- Name: TABLE card_bnft_cond; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_bnft_cond IS '카드 혜택과 적용 조건 간 N:M 논리 관계. Neo4j Benefit-Condition 관계 생성 기준';


--
-- TOC entry 4310 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_bnft_cond.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft_cond.card_doc_id IS '카드 문서 ID. 두 부모 테이블의 공통 PK';


--
-- TOC entry 4311 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_bnft_cond.card_bnft_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft_cond.card_bnft_id IS '혜택 ID. card_bnft 부모 PK 승계';


--
-- TOC entry 4312 (class 0 OID 0)
-- Dependencies: 359
-- Name: COLUMN card_bnft_cond.card_cond_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_bnft_cond.card_cond_id IS '조건 ID. card_cond 부모 PK 승계';


--
-- TOC entry 356 (class 1259 OID 19286)
-- Name: card_cond; Type: TABLE; Schema: db_pipeline; Owner: postgres
--

CREATE TABLE db_pipeline.card_cond (
    card_doc_id character varying(20) NOT NULL,
    card_cond_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_cond'::text) NOT NULL,
    card_id bigint NOT NULL,
    card_bnft_id character varying(20),
    cond_apply_lvl_cd character varying(20) NOT NULL,
    cond_type_cd character varying(20) NOT NULL,
    card_excl_item_id character varying(20),
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
    card_doc_chunk_id character varying(20) NOT NULL,
    cond_evidence_txt text NOT NULL,
    cond_evidence_start_pos integer NOT NULL,
    cond_evidence_end_pos integer NOT NULL,
    card_extr_stg_id character varying(20) NOT NULL,
    cond_status character varying(20) DEFAULT 'CONFIRMED'::character varying NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    cond_rule_json jsonb NOT NULL,
    CONSTRAINT card_cond_check CHECK (((((cond_apply_lvl_cd)::text = 'CARD'::text) AND (card_bnft_id IS NULL)) OR (((cond_apply_lvl_cd)::text = 'BENEFIT'::text) AND (card_bnft_id IS NOT NULL)))),
    CONSTRAINT card_cond_check1 CHECK ((((cond_type_cd)::text <> ALL ((ARRAY['SPEND_EXCL'::character varying, 'BNFT_EXCL'::character varying])::text[])) OR ((card_excl_item_id IS NOT NULL) AND (cond_excl_raw_txt IS NOT NULL)))),
    CONSTRAINT card_cond_check2 CHECK (((cond_min_amt IS NULL) OR (cond_max_amt IS NULL) OR (cond_min_amt <= cond_max_amt))),
    CONSTRAINT card_cond_check3 CHECK (((cond_evidence_start_pos >= 1) AND (cond_evidence_end_pos >= cond_evidence_start_pos))),
    CONSTRAINT card_cond_cond_basis_cd_check CHECK (((cond_basis_cd)::text = ANY ((ARRAY['PREV_MONTH_SPEND'::character varying, 'PREV_YEAR_SPEND'::character varying, 'TXN_AMT'::character varying, 'MONTH_USAGE'::character varying, 'NONE'::character varying])::text[]))),
    CONSTRAINT card_cond_cond_modality_cd_check CHECK (((cond_modality_cd)::text = ANY ((ARRAY['CONFIRMED'::character varying, 'POSSIBLE'::character varying])::text[]))),
    CONSTRAINT card_cond_cond_period_cd_check CHECK (((cond_period_cd)::text = ANY ((ARRAY['TXN'::character varying, 'DAY'::character varying, 'MONTH'::character varying, 'YEAR'::character varying, 'NONE'::character varying])::text[]))),
    CONSTRAINT card_cond_cond_status_check CHECK (((cond_status)::text = ANY ((ARRAY['CONFIRMED'::character varying, 'RETIRED'::character varying])::text[]))),
    CONSTRAINT card_cond_cond_type_cd_check CHECK (((cond_type_cd)::text = ANY ((ARRAY['SPEND_REQ'::character varying, 'SPEND_EXCL'::character varying, 'BNFT_EXCL'::character varying, 'LIMIT'::character varying, 'TIER'::character varying, 'USAGE_REQ'::character varying, 'GRACE'::character varying, 'MERCHANT_RULE'::character varying, 'ETC'::character varying])::text[])))
);


ALTER TABLE db_pipeline.card_cond OWNER TO postgres;

--
-- TOC entry 4313 (class 0 OID 0)
-- Dependencies: 356
-- Name: TABLE card_cond; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_cond IS '검증 완료 조건(전월실적·실적 제외·혜택 제외·한도·구간·예외; 카드·혜택별 정책 인스턴스)';


--
-- TOC entry 4314 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.card_doc_id IS '근거 원본 문서 ID';


--
-- TOC entry 4315 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.card_cond_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.card_cond_id IS '조건 ID(Neo4j Condition 노드·EXCLUDES 관계 키)';


--
-- TOC entry 4316 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.card_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.card_id IS '카드 상품 ID(card_doc.card_id와 일치해야 함)';


--
-- TOC entry 4317 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.card_bnft_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.card_bnft_id IS '조건이 걸린 혜택 ID(카드 전체 조건이면 NULL)';


--
-- TOC entry 4318 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_apply_lvl_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_apply_lvl_cd IS '적용 수준(CARD: 카드 전체, BENEFIT: 특정 혜택)';


--
-- TOC entry 4319 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_type_cd IS '조건 유형(SPEND_REQ: 전월실적 요건, SPEND_EXCL: 실적 산정 제외, BNFT_EXCL: 혜택 적용 제외, LIMIT: 한도, TIER: 구간별 혜택률·금액, USAGE_REQ: 건당 이용 요건, GRACE: 유예, MERCHANT_RULE: 가맹점 분류 규칙, ETC)';


--
-- TOC entry 4320 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.card_excl_item_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.card_excl_item_id IS '표준 제외 항목 ID(SPEND_EXCL·BNFT_EXCL 필수)';


--
-- TOC entry 4321 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_excl_raw_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_excl_raw_txt IS '제외 항목 원문 표기';


--
-- TOC entry 4322 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_basis_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_basis_cd IS '금액 기준(PREV_MONTH_SPEND, TXN_AMT, MONTH_USAGE, NONE)';


--
-- TOC entry 4323 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_min_amt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_min_amt IS '구간 하한 금액(원, 이상). 실적 무관은 SPEND_REQ + 0';


--
-- TOC entry 4324 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_max_amt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_max_amt IS '구간 상한 금액(원, 미만)';


--
-- TOC entry 4325 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_rate; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_rate IS '구간 할인·적립률(%)';


--
-- TOC entry 4326 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_amt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_amt IS '구간 정액 혜택 금액(원)';


--
-- TOC entry 4327 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_limit_amt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_limit_amt IS '한도 금액(원)';


--
-- TOC entry 4328 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_limit_cnt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_limit_cnt IS '한도 횟수';


--
-- TOC entry 4329 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_period_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_period_cd IS '한도 기간(TXN, DAY, MONTH, YEAR, NONE)';


--
-- TOC entry 4330 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_modality_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_modality_cd IS '적용 확정성(CONFIRMED: 확정, POSSIBLE: 제외될 수 있음)';


--
-- TOC entry 4331 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_value_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_value_txt IS '금액·비율·횟수 원문 표기';


--
-- TOC entry 4332 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_target_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_target_txt IS '대상 가맹점·업종·거래 원문 표기';


--
-- TOC entry 4333 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_natural_key; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_natural_key IS '조건 자연키 SHA-256(카드·혜택·유형·제외 항목·기준·값). 재적재 중복 방지';


--
-- TOC entry 4334 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_policy_cand_key; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_policy_cand_key IS '동일 정책 후보 키 SHA-256(카드사·유형·적용 범위·제외 항목·값, 카드 제외). 자동 병합 근거 아님';


--
-- TOC entry 4335 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.card_doc_chunk_id IS '근거 청크 ID';


--
-- TOC entry 4336 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_evidence_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_evidence_txt IS '근거 원문 문장';


--
-- TOC entry 4337 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_evidence_start_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_evidence_start_pos IS '근거의 chunk_raw_txt 내 시작 위치';


--
-- TOC entry 4338 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_evidence_end_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_evidence_end_pos IS '근거의 chunk_raw_txt 내 끝 위치';


--
-- TOC entry 4339 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.card_extr_stg_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.card_extr_stg_id IS '확정 근거 staging ID';


--
-- TOC entry 4340 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_status IS '상태(CONFIRMED, RETIRED: 신규 문서 버전으로 대체)';


--
-- TOC entry 4341 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.create_date IS '생성 일시';


--
-- TOC entry 4342 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4343 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.update_date IS '수정 일시';


--
-- TOC entry 4344 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 4345 (class 0 OID 0)
-- Dependencies: 356
-- Name: COLUMN card_cond.cond_rule_json; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_cond.cond_rule_json IS 'card_extr_stg.stg_normalized_item에서 검증 및 승인된 조건 JSON 전체. 복합 조건, AND/OR, 선택 규칙 등 보존';


--
-- TOC entry 349 (class 1259 OID 19125)
-- Name: card_doc; Type: TABLE; Schema: db_pipeline; Owner: postgres
--

CREATE TABLE db_pipeline.card_doc (
    card_doc_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_doc'::text) NOT NULL,
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
    CONSTRAINT card_doc_doc_page_cnt_check CHECK (((doc_page_cnt IS NULL) OR (doc_page_cnt > 0))),
    CONSTRAINT card_doc_doc_sha256_check CHECK (((doc_sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT card_doc_doc_status_check CHECK (((doc_status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'SUPERSEDED'::character varying, 'EXCLUDED'::character varying])::text[]))),
    CONSTRAINT card_doc_doc_type_cd_check CHECK (((doc_type_cd)::text = ANY ((ARRAY['PRODUCT_GUIDE'::character varying, 'TERMS'::character varying, 'ETC'::character varying])::text[]))),
    CONSTRAINT card_doc_doc_version_no_check CHECK ((doc_version_no > 0))
);


ALTER TABLE db_pipeline.card_doc OWNER TO postgres;

--
-- TOC entry 4346 (class 0 OID 0)
-- Dependencies: 349
-- Name: TABLE card_doc; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_doc IS '카드 상품설명서 원본 문서(문서 버전 단위)';


--
-- TOC entry 4347 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.card_doc_id IS '원본 문서 ID';


--
-- TOC entry 4348 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.card_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.card_id IS '카드 상품 ID(card_benefit.card_product.card_id 논리 참조)';


--
-- TOC entry 4349 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_cd IS '파이프라인 공통 문서 코드(예: HANA_15650_20260429). 결과 A·B 비교 키 후보';


--
-- TOC entry 4350 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_type_cd IS '문서 유형(PRODUCT_GUIDE: 상품설명서, TERMS: 약관, ETC)';


--
-- TOC entry 4351 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_title; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_title IS '문서 제목';


--
-- TOC entry 4352 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_source_url; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_source_url IS '공식 출처 URL';


--
-- TOC entry 4353 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_file_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_file_nm IS '수집 파일명';


--
-- TOC entry 4354 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_file_size; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_file_size IS '수집 파일 크기(바이트)';


--
-- TOC entry 4355 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_sha256; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_sha256 IS '수집 파일 SHA-256(소문자 16진수 64자)';


--
-- TOC entry 4356 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_page_cnt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_page_cnt IS 'PDF 페이지 수';


--
-- TOC entry 4357 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_review_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_review_no IS '준법심의·여신협회 심의필 번호 원문';


--
-- TOC entry 4358 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_review_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_review_date IS '심의일';


--
-- TOC entry 4359 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_release_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_release_date IS '상품 출시일';


--
-- TOC entry 4360 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_collect_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_collect_date IS '파일 수집(다운로드) 일시';


--
-- TOC entry 4361 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_version_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_version_no IS '카드·문서 유형 내 문서 버전 번호(1부터)';


--
-- TOC entry 4362 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_status IS '문서 상태(ACTIVE: 현재 유효, SUPERSEDED: 신규 버전으로 대체, EXCLUDED: 분석 제외)';


--
-- TOC entry 4363 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.doc_note; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.doc_note IS '문서 범위·확인 사항 메모';


--
-- TOC entry 4364 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.create_date IS '생성 일시';


--
-- TOC entry 4365 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4366 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.update_date IS '수정 일시';


--
-- TOC entry 4367 (class 0 OID 0)
-- Dependencies: 349
-- Name: COLUMN card_doc.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 351 (class 1259 OID 19162)
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
    CONSTRAINT card_doc_chunk_chunk_seq_check CHECK ((chunk_seq > 0)),
    CONSTRAINT card_doc_chunk_chunk_status_check CHECK (((chunk_status)::text = ANY ((ARRAY['RAW'::character varying, 'CLEANED'::character varying, 'EXCLUDED'::character varying])::text[]))),
    CONSTRAINT card_doc_chunk_chunk_type_cd_check CHECK (((chunk_type_cd)::text = ANY ((ARRAY['BODY'::character varying, 'TABLE'::character varying, 'NOTICE'::character varying, 'HEADER_FOOTER'::character varying, 'ETC'::character varying])::text[])))
);


ALTER TABLE db_pipeline.card_doc_chunk OWNER TO postgres;

--
-- TOC entry 4368 (class 0 OID 0)
-- Dependencies: 351
-- Name: TABLE card_doc_chunk; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_doc_chunk IS '문서 청크(조항·표·안내 단위) 원문과 SQL 정제 결과';


--
-- TOC entry 4369 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.card_doc_id IS '원본 문서 ID';


--
-- TOC entry 4370 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.page_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.page_no IS '청크가 속한 페이지 번호(청크는 페이지를 넘지 않음)';


--
-- TOC entry 4371 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.card_doc_chunk_id IS '청크 ID';


--
-- TOC entry 4372 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.chunk_seq; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_seq IS '문서 내 청크 순번(1부터)';


--
-- TOC entry 4373 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.chunk_section_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_section_nm IS '원문 절 제목(예: [실적 산정 기준], 서비스 제외 대상)';


--
-- TOC entry 4374 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.chunk_type_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_type_cd IS '청크 유형(BODY, TABLE, NOTICE: 유의사항, HEADER_FOOTER: 머리말·꼬리말, ETC)';


--
-- TOC entry 4375 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.chunk_start_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_start_pos IS 'page_raw_txt 내 시작 문자 위치(1부터, PostgreSQL substr 기준)';


--
-- TOC entry 4376 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.chunk_end_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_end_pos IS 'page_raw_txt 내 끝 문자 위치(포함)';


--
-- TOC entry 4377 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.chunk_raw_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_raw_txt IS '청크 원문(정제 전, page_raw_txt의 부분 문자열)';


--
-- TOC entry 4378 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.chunk_clean_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_clean_txt IS 'SQL 정제 후 텍스트(AI 입력)';


--
-- TOC entry 4379 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.chunk_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_status IS '청크 상태(RAW: 분리만 됨, CLEANED: 정제 완료, EXCLUDED: 추출 대상 제외)';


--
-- TOC entry 4380 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.chunk_split_rule_ver; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_split_rule_ver IS '청크 분리 규칙 버전';


--
-- TOC entry 4381 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.chunk_clean_rule_ver; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_clean_rule_ver IS 'SQL 정제 규칙 버전';


--
-- TOC entry 4382 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.create_date IS '생성 일시';


--
-- TOC entry 4383 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4384 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.update_date IS '수정 일시';


--
-- TOC entry 4385 (class 0 OID 0)
-- Dependencies: 351
-- Name: COLUMN card_doc_chunk.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_chunk.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 350 (class 1259 OID 19149)
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
    CONSTRAINT card_doc_page_page_layer_cd_check CHECK (((page_layer_cd)::text = ANY ((ARRAY['TEXT'::character varying, 'IMAGE'::character varying, 'MIXED'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT card_doc_page_page_no_check CHECK ((page_no > 0))
);


ALTER TABLE db_pipeline.card_doc_page OWNER TO postgres;

--
-- TOC entry 4386 (class 0 OID 0)
-- Dependencies: 350
-- Name: TABLE card_doc_page; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_doc_page IS '문서 페이지별 추출 원문(정제 전, 적재 후 변경 금지)';


--
-- TOC entry 4387 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.card_doc_id IS '원본 문서 ID';


--
-- TOC entry 4388 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.page_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_no IS 'PDF 페이지 번호(1부터)';


--
-- TOC entry 4389 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.page_raw_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_raw_txt IS '추출기가 반환한 페이지 텍스트 원문(가공 없음)';


--
-- TOC entry 4390 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.page_char_cnt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_char_cnt IS '페이지 원문 문자 수';


--
-- TOC entry 4391 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.page_txt_sha256; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_txt_sha256 IS '페이지 원문 SHA-256(재추출 시 변경 감지)';


--
-- TOC entry 4392 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.page_layer_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_layer_cd IS '텍스트 레이어 유형(TEXT, IMAGE, MIXED: 일부 표가 이미지, UNKNOWN)';


--
-- TOC entry 4393 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.page_extractor_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_extractor_nm IS '텍스트 추출기명(예: PyMuPDF)';


--
-- TOC entry 4394 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.page_extractor_ver; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_extractor_ver IS '텍스트 추출기 버전';


--
-- TOC entry 4395 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.page_note; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.page_note IS '추출 한계·확인 메모(표 미탐지 등)';


--
-- TOC entry 4396 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.create_date IS '생성 일시';


--
-- TOC entry 4397 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4398 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.update_date IS '수정 일시';


--
-- TOC entry 4399 (class 0 OID 0)
-- Dependencies: 350
-- Name: COLUMN card_doc_page.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_doc_page.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 353 (class 1259 OID 19213)
-- Name: card_excl_item; Type: TABLE; Schema: db_pipeline; Owner: postgres
--

CREATE TABLE db_pipeline.card_excl_item (
    card_excl_item_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_excl_item'::text) NOT NULL,
    issuer text NOT NULL,
    excl_item_nm text NOT NULL,
    excl_concept_cd character varying(50),
    excl_item_desc text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


ALTER TABLE db_pipeline.card_excl_item OWNER TO postgres;

--
-- TOC entry 4400 (class 0 OID 0)
-- Dependencies: 353
-- Name: TABLE card_excl_item; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_excl_item IS '표준 제외 항목(카드사 범위 개념, 정책 아님)';


--
-- TOC entry 4401 (class 0 OID 0)
-- Dependencies: 353
-- Name: COLUMN card_excl_item.card_excl_item_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.card_excl_item_id IS '표준 제외 항목 ID';


--
-- TOC entry 4402 (class 0 OID 0)
-- Dependencies: 353
-- Name: COLUMN card_excl_item.issuer; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.issuer IS '카드사(card_product.issuer와 같은 표기). 병합은 같은 카드사 안에서만';


--
-- TOC entry 4403 (class 0 OID 0)
-- Dependencies: 353
-- Name: COLUMN card_excl_item.excl_item_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_nm IS '표준 제외 항목명(예: 상품권·기프트카드 구매)';


--
-- TOC entry 4404 (class 0 OID 0)
-- Dependencies: 353
-- Name: COLUMN card_excl_item.excl_concept_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_concept_cd IS '카드사 공통 분류 개념 코드(예: GIFT_CERT_PURCHASE). 분류용이며 정책 동일을 뜻하지 않음';


--
-- TOC entry 4405 (class 0 OID 0)
-- Dependencies: 353
-- Name: COLUMN card_excl_item.excl_item_desc; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_desc IS '항목 설명·포함 범위';


--
-- TOC entry 4406 (class 0 OID 0)
-- Dependencies: 353
-- Name: COLUMN card_excl_item.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.create_date IS '생성 일시';


--
-- TOC entry 4407 (class 0 OID 0)
-- Dependencies: 353
-- Name: COLUMN card_excl_item.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4408 (class 0 OID 0)
-- Dependencies: 353
-- Name: COLUMN card_excl_item.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.update_date IS '수정 일시';


--
-- TOC entry 4409 (class 0 OID 0)
-- Dependencies: 353
-- Name: COLUMN card_excl_item.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 354 (class 1259 OID 19225)
-- Name: card_excl_item_als; Type: TABLE; Schema: db_pipeline; Owner: postgres
--

CREATE TABLE db_pipeline.card_excl_item_als (
    card_excl_item_id character varying(20) NOT NULL,
    card_excl_item_als_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_excl_item_als'::text) NOT NULL,
    excl_item_als_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


ALTER TABLE db_pipeline.card_excl_item_als OWNER TO postgres;

--
-- TOC entry 4410 (class 0 OID 0)
-- Dependencies: 354
-- Name: TABLE card_excl_item_als; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_excl_item_als IS '제외 항목 원문 표기 별칭(SQL 정규화 사전)';


--
-- TOC entry 4411 (class 0 OID 0)
-- Dependencies: 354
-- Name: COLUMN card_excl_item_als.card_excl_item_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item_als.card_excl_item_id IS '표준 제외 항목 ID';


--
-- TOC entry 4412 (class 0 OID 0)
-- Dependencies: 354
-- Name: COLUMN card_excl_item_als.card_excl_item_als_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item_als.card_excl_item_als_id IS '제외 항목 별칭 ID';


--
-- TOC entry 4413 (class 0 OID 0)
-- Dependencies: 354
-- Name: COLUMN card_excl_item_als.excl_item_als_nm; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item_als.excl_item_als_nm IS '원문 표기(공백 제거 비교 기준). 의미가 불확실한 표기(예: 상품/)는 등록하지 않음';


--
-- TOC entry 4414 (class 0 OID 0)
-- Dependencies: 354
-- Name: COLUMN card_excl_item_als.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item_als.create_date IS '생성 일시';


--
-- TOC entry 4415 (class 0 OID 0)
-- Dependencies: 354
-- Name: COLUMN card_excl_item_als.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item_als.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4416 (class 0 OID 0)
-- Dependencies: 354
-- Name: COLUMN card_excl_item_als.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item_als.update_date IS '수정 일시';


--
-- TOC entry 4417 (class 0 OID 0)
-- Dependencies: 354
-- Name: COLUMN card_excl_item_als.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_excl_item_als.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 358 (class 1259 OID 19366)
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
    card_id bigint NOT NULL,
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
    CONSTRAINT card_extr_stg_check1 CHECK ((((stg_status)::text <> ALL ((ARRAY['AUTO_APPROVED'::character varying, 'MANUAL_APPROVED'::character varying])::text[])) OR ((stg_normalized_item IS NOT NULL) AND (NOT ((stg_sql_check_cd)::text IS DISTINCT FROM 'OK'::text)) AND (stg_evidence_start_pos IS NOT NULL) AND (stg_evidence_end_pos IS NOT NULL) AND (btrim(stg_evidence_txt) <> ''::text)))),
    CONSTRAINT card_extr_stg_stg_ai_vrfy_cd_check CHECK (((stg_ai_vrfy_cd IS NULL) OR ((stg_ai_vrfy_cd)::text = ANY ((ARRAY['MATCH'::character varying, 'MISMATCH'::character varying, 'UNCERTAIN'::character varying])::text[])))),
    CONSTRAINT card_extr_stg_stg_item_seq_check CHECK ((stg_item_seq > 0)),
    CONSTRAINT card_extr_stg_stg_kind_cd_check CHECK (((stg_kind_cd)::text = ANY ((ARRAY['BENEFIT'::character varying, 'CONDITION'::character varying])::text[]))),
    CONSTRAINT card_extr_stg_stg_status_check CHECK (((stg_status)::text = ANY ((ARRAY['PENDING_REVIEW'::character varying, 'AUTO_APPROVED'::character varying, 'MANUAL_APPROVED'::character varying, 'REJECTED'::character varying])::text[])))
);


ALTER TABLE db_pipeline.card_extr_stg OWNER TO postgres;

--
-- TOC entry 4418 (class 0 OID 0)
-- Dependencies: 358
-- Name: TABLE card_extr_stg; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON TABLE db_pipeline.card_extr_stg IS 'AI 추출 혜택·조건 staging(정제 전 원 항목, 정제 후 값, 검증·승인 상태)';


--
-- TOC entry 4419 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_ai_run_id IS 'AI 추출 실행 ID';


--
-- TOC entry 4420 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.card_doc_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_doc_id IS '원본 문서 ID(card_ai_call 부모 PK 승계)';


--
-- TOC entry 4421 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.page_no; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.page_no IS 'PDF 페이지 번호(card_ai_call 부모 PK 승계)';


--
-- TOC entry 4422 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.card_doc_chunk_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_doc_chunk_id IS '근거 청크 ID';


--
-- TOC entry 4423 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.call_seq; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.call_seq IS '응답을 만든 호출 순번(card_ai_call)';


--
-- TOC entry 4424 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.card_extr_stg_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_extr_stg_id IS '추출 staging ID';


--
-- TOC entry 4425 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_item_seq; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_item_seq IS '응답 내 항목 순번(1부터)';


--
-- TOC entry 4426 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.card_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_id IS '대상 카드 상품 ID(문서의 card_id)';


--
-- TOC entry 4427 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_kind_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_kind_cd IS '항목 종류(BENEFIT: 혜택, CONDITION: 조건)';


--
-- TOC entry 4428 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_parent_card_extr_stg_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_parent_card_extr_stg_id IS '조건이 걸린 혜택의 staging ID(카드 전체 조건이면 NULL)';


--
-- TOC entry 4429 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_raw_item; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_raw_item IS 'AI가 추출한 개별 혜택 또는 조건의 원본 JSON';


--
-- TOC entry 4430 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_normalized_item; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_normalized_item IS 'AI 추출 원본을 정제 및 표준화한 JSON';


--
-- TOC entry 4431 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_evidence_txt; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_txt IS 'AI가 제시한 근거 원문 문장';


--
-- TOC entry 4432 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_evidence_start_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_start_pos IS '근거 청크 원문 내 시작 문자 위치(1부터)';


--
-- TOC entry 4433 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_evidence_end_pos; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_end_pos IS '근거 청크 원문 내 종료 문자 위치(포함)';


--
-- TOC entry 4434 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.card_excl_item_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_excl_item_id IS '매핑된 표준 제외 항목 ID(미매핑 NULL)';


--
-- TOC entry 4435 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_sql_check_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_sql_check_cd IS '정제 JSON, 원문 근거, 참조 관계 등을 검증한 SQL 검증 결과';


--
-- TOC entry 4436 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_ai_vrfy_cd; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_ai_vrfy_cd IS 'AI 의미 검증 결과(NULL: 미실행, MATCH, MISMATCH, UNCERTAIN)';


--
-- TOC entry 4437 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_ai_vrfy_card_ai_run_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_ai_vrfy_card_ai_run_id IS 'AI 의미 검증 실행 ID';


--
-- TOC entry 4438 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_status; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_status IS '검토 상태(PENDING_REVIEW, AUTO_APPROVED, MANUAL_APPROVED, REJECTED)';


--
-- TOC entry 4439 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_review_note; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_review_note IS '검증 결과 및 검토 메모';


--
-- TOC entry 4440 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_approved_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_approved_date IS '승인 일시';


--
-- TOC entry 4441 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.stg_approved_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_approved_user_id IS '승인 사용자 ID';


--
-- TOC entry 4442 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.create_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.create_date IS '생성 일시';


--
-- TOC entry 4443 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.create_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4444 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.update_date; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.update_date IS '수정 일시';


--
-- TOC entry 4445 (class 0 OID 0)
-- Dependencies: 358
-- Name: COLUMN card_extr_stg.update_user_id; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON COLUMN db_pipeline.card_extr_stg.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 343 (class 1259 OID 19118)
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
-- TOC entry 4446 (class 0 OID 0)
-- Dependencies: 343
-- Name: SEQUENCE seq_card_ai_run; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_ai_run IS 'AI 실행 ID 발급';


--
-- TOC entry 347 (class 1259 OID 19122)
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
-- TOC entry 4447 (class 0 OID 0)
-- Dependencies: 347
-- Name: SEQUENCE seq_card_bnft; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_bnft IS '확정 혜택 ID 발급';


--
-- TOC entry 348 (class 1259 OID 19123)
-- Name: seq_card_cond; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_cond
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE db_pipeline.seq_card_cond OWNER TO postgres;

--
-- TOC entry 4448 (class 0 OID 0)
-- Dependencies: 348
-- Name: SEQUENCE seq_card_cond; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_cond IS '확정 조건 ID 발급';


--
-- TOC entry 341 (class 1259 OID 19116)
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
-- TOC entry 4449 (class 0 OID 0)
-- Dependencies: 341
-- Name: SEQUENCE seq_card_doc; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_doc IS '원본 문서 ID 발급';


--
-- TOC entry 342 (class 1259 OID 19117)
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
-- TOC entry 4450 (class 0 OID 0)
-- Dependencies: 342
-- Name: SEQUENCE seq_card_doc_chunk; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_doc_chunk IS '문서 청크 ID 발급';


--
-- TOC entry 345 (class 1259 OID 19120)
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
-- TOC entry 4451 (class 0 OID 0)
-- Dependencies: 345
-- Name: SEQUENCE seq_card_excl_item; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_excl_item IS '표준 제외 항목 ID 발급';


--
-- TOC entry 346 (class 1259 OID 19121)
-- Name: seq_card_excl_item_als; Type: SEQUENCE; Schema: db_pipeline; Owner: postgres
--

CREATE SEQUENCE db_pipeline.seq_card_excl_item_als
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE db_pipeline.seq_card_excl_item_als OWNER TO postgres;

--
-- TOC entry 4452 (class 0 OID 0)
-- Dependencies: 346
-- Name: SEQUENCE seq_card_excl_item_als; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_excl_item_als IS '제외 항목 별칭 ID 발급';


--
-- TOC entry 344 (class 1259 OID 19119)
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
-- TOC entry 4453 (class 0 OID 0)
-- Dependencies: 344
-- Name: SEQUENCE seq_card_extr_stg; Type: COMMENT; Schema: db_pipeline; Owner: postgres
--

COMMENT ON SEQUENCE db_pipeline.seq_card_extr_stg IS 'AI 추출 staging ID 발급';


--
-- TOC entry 4081 (class 2606 OID 19357)
-- Name: card_ai_call card_ai_call_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_ai_call
    ADD CONSTRAINT card_ai_call_pkey PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq);


--
-- TOC entry 4048 (class 2606 OID 19198)
-- Name: card_ai_run card_ai_run_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_ai_run
    ADD CONSTRAINT card_ai_run_pkey PRIMARY KEY (card_ai_run_id);


--
-- TOC entry 4060 (class 2606 OID 19281)
-- Name: card_bnft card_bnft_card_bnft_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_bnft
    ADD CONSTRAINT card_bnft_card_bnft_id_key UNIQUE (card_bnft_id);


--
-- TOC entry 4062 (class 2606 OID 19283)
-- Name: card_bnft card_bnft_card_doc_id_bnft_nm_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_bnft
    ADD CONSTRAINT card_bnft_card_doc_id_bnft_nm_key UNIQUE (card_doc_id, bnft_nm);


--
-- TOC entry 4064 (class 2606 OID 19285)
-- Name: card_bnft card_bnft_card_extr_stg_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_bnft
    ADD CONSTRAINT card_bnft_card_extr_stg_id_key UNIQUE (card_extr_stg_id);


--
-- TOC entry 4094 (class 2606 OID 19397)
-- Name: card_bnft_cond card_bnft_cond_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_bnft_cond
    ADD CONSTRAINT card_bnft_cond_pkey PRIMARY KEY (card_doc_id, card_bnft_id, card_cond_id);


--
-- TOC entry 4066 (class 2606 OID 19279)
-- Name: card_bnft card_bnft_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_bnft
    ADD CONSTRAINT card_bnft_pkey PRIMARY KEY (card_doc_id, card_bnft_id);


--
-- TOC entry 4069 (class 2606 OID 19310)
-- Name: card_cond card_cond_card_cond_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_cond
    ADD CONSTRAINT card_cond_card_cond_id_key UNIQUE (card_cond_id);


--
-- TOC entry 4071 (class 2606 OID 19312)
-- Name: card_cond card_cond_card_doc_id_cond_natural_key_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_cond
    ADD CONSTRAINT card_cond_card_doc_id_cond_natural_key_key UNIQUE (card_doc_id, cond_natural_key);


--
-- TOC entry 4073 (class 2606 OID 19314)
-- Name: card_cond card_cond_card_extr_stg_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_cond
    ADD CONSTRAINT card_cond_card_extr_stg_id_key UNIQUE (card_extr_stg_id);


--
-- TOC entry 4075 (class 2606 OID 19308)
-- Name: card_cond card_cond_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_cond
    ADD CONSTRAINT card_cond_pkey PRIMARY KEY (card_doc_id, card_cond_id);


--
-- TOC entry 4031 (class 2606 OID 19148)
-- Name: card_doc card_doc_card_id_doc_type_cd_doc_version_no_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc
    ADD CONSTRAINT card_doc_card_id_doc_type_cd_doc_version_no_key UNIQUE (card_id, doc_type_cd, doc_version_no);


--
-- TOC entry 4042 (class 2606 OID 19180)
-- Name: card_doc_chunk card_doc_chunk_card_doc_chunk_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_card_doc_chunk_id_key UNIQUE (card_doc_chunk_id);


--
-- TOC entry 4044 (class 2606 OID 19182)
-- Name: card_doc_chunk card_doc_chunk_card_doc_id_chunk_seq_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_card_doc_id_chunk_seq_key UNIQUE (card_doc_id, chunk_seq);


--
-- TOC entry 4046 (class 2606 OID 19178)
-- Name: card_doc_chunk card_doc_chunk_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_pkey PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id);


--
-- TOC entry 4033 (class 2606 OID 19144)
-- Name: card_doc card_doc_doc_cd_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc
    ADD CONSTRAINT card_doc_doc_cd_key UNIQUE (doc_cd);


--
-- TOC entry 4035 (class 2606 OID 19146)
-- Name: card_doc card_doc_doc_sha256_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc
    ADD CONSTRAINT card_doc_doc_sha256_key UNIQUE (doc_sha256);


--
-- TOC entry 4040 (class 2606 OID 19161)
-- Name: card_doc_page card_doc_page_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc_page
    ADD CONSTRAINT card_doc_page_pkey PRIMARY KEY (card_doc_id, page_no);


--
-- TOC entry 4037 (class 2606 OID 19142)
-- Name: card_doc card_doc_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_doc
    ADD CONSTRAINT card_doc_pkey PRIMARY KEY (card_doc_id);


--
-- TOC entry 4056 (class 2606 OID 19236)
-- Name: card_excl_item_als card_excl_item_als_card_excl_item_id_excl_item_als_nm_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_excl_item_als
    ADD CONSTRAINT card_excl_item_als_card_excl_item_id_excl_item_als_nm_key UNIQUE (card_excl_item_id, excl_item_als_nm);


--
-- TOC entry 4058 (class 2606 OID 19234)
-- Name: card_excl_item_als card_excl_item_als_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_excl_item_als
    ADD CONSTRAINT card_excl_item_als_pkey PRIMARY KEY (card_excl_item_id, card_excl_item_als_id);


--
-- TOC entry 4051 (class 2606 OID 19224)
-- Name: card_excl_item card_excl_item_issuer_excl_item_nm_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_excl_item
    ADD CONSTRAINT card_excl_item_issuer_excl_item_nm_key UNIQUE (issuer, excl_item_nm);


--
-- TOC entry 4053 (class 2606 OID 19222)
-- Name: card_excl_item card_excl_item_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_excl_item
    ADD CONSTRAINT card_excl_item_pkey PRIMARY KEY (card_excl_item_id);


--
-- TOC entry 4085 (class 2606 OID 19386)
-- Name: card_extr_stg card_extr_stg_card_ai_run_id_card_doc_id_page_no_card_doc_c_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_card_ai_run_id_card_doc_id_page_no_card_doc_c_key UNIQUE (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, stg_item_seq);


--
-- TOC entry 4087 (class 2606 OID 19384)
-- Name: card_extr_stg card_extr_stg_card_extr_stg_id_key; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_card_extr_stg_id_key UNIQUE (card_extr_stg_id);


--
-- TOC entry 4089 (class 2606 OID 19382)
-- Name: card_extr_stg card_extr_stg_pkey; Type: CONSTRAINT; Schema: db_pipeline; Owner: postgres
--

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_pkey PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id);


--
-- TOC entry 4082 (class 1259 OID 19358)
-- Name: ix_card_ai_call_chunk_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_ai_call_chunk_key ON db_pipeline.card_ai_call USING btree (card_doc_chunk_id);


--
-- TOC entry 4083 (class 1259 OID 19359)
-- Name: ix_card_ai_call_doc_chunk_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_ai_call_doc_chunk_key ON db_pipeline.card_ai_call USING btree (card_doc_id, page_no, card_doc_chunk_id);


--
-- TOC entry 4049 (class 1259 OID 19316)
-- Name: ix_card_ai_run_doc_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_ai_run_doc_key ON db_pipeline.card_ai_run USING btree (run_target_card_doc_id);


--
-- TOC entry 4067 (class 1259 OID 19322)
-- Name: ix_card_bnft_card_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_bnft_card_key ON db_pipeline.card_bnft USING btree (card_id, card_doc_id);


--
-- TOC entry 4095 (class 1259 OID 19398)
-- Name: ix_card_bnft_cond_cond_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_bnft_cond_cond_key ON db_pipeline.card_bnft_cond USING btree (card_doc_id, card_cond_id, card_bnft_id);


--
-- TOC entry 4076 (class 1259 OID 19323)
-- Name: ix_card_cond_bnft_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_cond_bnft_key ON db_pipeline.card_cond USING btree (card_bnft_id);


--
-- TOC entry 4077 (class 1259 OID 19324)
-- Name: ix_card_cond_card_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_cond_card_key ON db_pipeline.card_cond USING btree (card_id, cond_type_cd);


--
-- TOC entry 4078 (class 1259 OID 19325)
-- Name: ix_card_cond_excl_item_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_cond_excl_item_key ON db_pipeline.card_cond USING btree (card_excl_item_id, cond_type_cd);


--
-- TOC entry 4079 (class 1259 OID 19326)
-- Name: ix_card_cond_policy_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_cond_policy_key ON db_pipeline.card_cond USING btree (cond_policy_cand_key);


--
-- TOC entry 4054 (class 1259 OID 19318)
-- Name: ix_card_excl_item_concept_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_excl_item_concept_key ON db_pipeline.card_excl_item USING btree (excl_concept_cd);


--
-- TOC entry 4090 (class 1259 OID 19387)
-- Name: ix_card_extr_stg_chunk_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_extr_stg_chunk_key ON db_pipeline.card_extr_stg USING btree (card_doc_chunk_id);


--
-- TOC entry 4091 (class 1259 OID 19388)
-- Name: ix_card_extr_stg_excl_item_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_extr_stg_excl_item_key ON db_pipeline.card_extr_stg USING btree (card_excl_item_id);


--
-- TOC entry 4092 (class 1259 OID 19389)
-- Name: ix_card_extr_stg_status_key; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE INDEX ix_card_extr_stg_status_key ON db_pipeline.card_extr_stg USING btree (stg_status, stg_kind_cd);


--
-- TOC entry 4038 (class 1259 OID 19315)
-- Name: uq_card_doc_active; Type: INDEX; Schema: db_pipeline; Owner: postgres
--

CREATE UNIQUE INDEX uq_card_doc_active ON db_pipeline.card_doc USING btree (card_id, doc_type_cd) WHERE ((doc_status)::text = 'ACTIVE'::text);


-- Completed on 2026-10-31 11:36:36

--
-- PostgreSQL database dump complete
--

