--
-- PostgreSQL database dump
--

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.0

-- Started on 2026-10-29 21:24:15

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
-- TOC entry 108 (class 2615 OID 47041)
-- Name: recipe; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA recipe;


ALTER SCHEMA recipe OWNER TO postgres;

--
-- TOC entry 4228 (class 0 OID 0)
-- Dependencies: 108
-- Name: SCHEMA recipe; Type: COMMENT; Schema: -; Owner: postgres
--

COMMENT ON SCHEMA recipe IS '식약처 레시피 GraphRAG 목표 모델(전환 2026-10-22T14:18:03Z, 원본 보존 recipe_legacy_20261022)';


--
-- TOC entry 648 (class 1255 OID 47048)
-- Name: fn_get_biz_id(text); Type: FUNCTION; Schema: recipe; Owner: postgres
--

CREATE FUNCTION recipe.fn_get_biz_id(p_tbl_nm text) RETURNS character varying
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $_$
DECLARE
    v_seq regclass;
BEGIN
    IF p_tbl_nm IS NULL OR p_tbl_nm !~ '^[A-Za-z][A-Za-z0-9_]*$' THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = format('Invalid recipe table name for business ID: %s', coalesce(p_tbl_nm, '<NULL>'));
    END IF;

    v_seq := to_regclass('recipe.seq_' || lower(p_tbl_nm));
    IF v_seq IS NULL OR NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS c
        WHERE c.oid = v_seq
          AND c.relkind = 'S'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42P01',
            MESSAGE = format('Recipe ID sequence does not exist: %s', 'recipe.seq_' || lower(p_tbl_nm));
    END IF;

    RETURN to_char((clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date, 'YYYYMMDD')
        || '_' || lpad(nextval(v_seq)::text, 6, '0');
END;
$_$;


ALTER FUNCTION recipe.fn_get_biz_id(p_tbl_nm text) OWNER TO postgres;

--
-- TOC entry 4229 (class 0 OID 0)
-- Dependencies: 648
-- Name: FUNCTION fn_get_biz_id(p_tbl_nm text); Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON FUNCTION recipe.fn_get_biz_id(p_tbl_nm text) IS 'recipe.seq_<테이블명> 시퀀스로 YYYYMMDD_000001 형식 업무 ID 발급(Asia/Seoul 기준)';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 406 (class 1259 OID 47082)
-- Name: common_cd; Type: TABLE; Schema: recipe; Owner: postgres
--

CREATE TABLE recipe.common_cd (
    common_code_grp_id character varying(20) NOT NULL,
    common_cd character varying(20) NOT NULL,
    common_cd_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


ALTER TABLE recipe.common_cd OWNER TO postgres;

--
-- TOC entry 4230 (class 0 OID 0)
-- Dependencies: 406
-- Name: TABLE common_cd; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON TABLE recipe.common_cd IS '공통코드';


--
-- TOC entry 4231 (class 0 OID 0)
-- Dependencies: 406
-- Name: COLUMN common_cd.common_code_grp_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_cd.common_code_grp_id IS '공통코드 그룹 ID';


--
-- TOC entry 4232 (class 0 OID 0)
-- Dependencies: 406
-- Name: COLUMN common_cd.common_cd; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_cd.common_cd IS '공통코드';


--
-- TOC entry 4233 (class 0 OID 0)
-- Dependencies: 406
-- Name: COLUMN common_cd.common_cd_nm; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_cd.common_cd_nm IS '공통코드명';


--
-- TOC entry 4234 (class 0 OID 0)
-- Dependencies: 406
-- Name: COLUMN common_cd.create_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_cd.create_date IS '생성 일시';


--
-- TOC entry 4235 (class 0 OID 0)
-- Dependencies: 406
-- Name: COLUMN common_cd.create_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_cd.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4236 (class 0 OID 0)
-- Dependencies: 406
-- Name: COLUMN common_cd.update_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_cd.update_date IS '수정 일시';


--
-- TOC entry 4237 (class 0 OID 0)
-- Dependencies: 406
-- Name: COLUMN common_cd.update_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_cd.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 405 (class 1259 OID 47073)
-- Name: common_code_grp; Type: TABLE; Schema: recipe; Owner: postgres
--

CREATE TABLE recipe.common_code_grp (
    common_code_grp_id character varying(20) NOT NULL,
    common_code_grp_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


ALTER TABLE recipe.common_code_grp OWNER TO postgres;

--
-- TOC entry 4238 (class 0 OID 0)
-- Dependencies: 405
-- Name: TABLE common_code_grp; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON TABLE recipe.common_code_grp IS '공통코드 그룹';


--
-- TOC entry 4239 (class 0 OID 0)
-- Dependencies: 405
-- Name: COLUMN common_code_grp.common_code_grp_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_code_grp.common_code_grp_id IS '공통코드 그룹 ID(예: COOK_MTHD)';


--
-- TOC entry 4240 (class 0 OID 0)
-- Dependencies: 405
-- Name: COLUMN common_code_grp.common_code_grp_nm; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_code_grp.common_code_grp_nm IS '공통코드 그룹명';


--
-- TOC entry 4241 (class 0 OID 0)
-- Dependencies: 405
-- Name: COLUMN common_code_grp.create_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_code_grp.create_date IS '생성 일시';


--
-- TOC entry 4242 (class 0 OID 0)
-- Dependencies: 405
-- Name: COLUMN common_code_grp.create_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_code_grp.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4243 (class 0 OID 0)
-- Dependencies: 405
-- Name: COLUMN common_code_grp.update_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_code_grp.update_date IS '수정 일시';


--
-- TOC entry 4244 (class 0 OID 0)
-- Dependencies: 405
-- Name: COLUMN common_code_grp.update_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.common_code_grp.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 410 (class 1259 OID 47122)
-- Name: ingr; Type: TABLE; Schema: recipe; Owner: postgres
--

CREATE TABLE recipe.ingr (
    ingr_id character varying(20) DEFAULT recipe.fn_get_biz_id('ingr'::text) NOT NULL,
    ingr_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


ALTER TABLE recipe.ingr OWNER TO postgres;

--
-- TOC entry 4245 (class 0 OID 0)
-- Dependencies: 410
-- Name: TABLE ingr; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON TABLE recipe.ingr IS '표준 식재료';


--
-- TOC entry 4246 (class 0 OID 0)
-- Dependencies: 410
-- Name: COLUMN ingr.ingr_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr.ingr_id IS '표준 식재료 ID(단독 PK)';


--
-- TOC entry 4247 (class 0 OID 0)
-- Dependencies: 410
-- Name: COLUMN ingr.ingr_nm; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr.ingr_nm IS '표준 식재료명';


--
-- TOC entry 4248 (class 0 OID 0)
-- Dependencies: 410
-- Name: COLUMN ingr.create_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr.create_date IS '생성 일시';


--
-- TOC entry 4249 (class 0 OID 0)
-- Dependencies: 410
-- Name: COLUMN ingr.create_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4250 (class 0 OID 0)
-- Dependencies: 410
-- Name: COLUMN ingr.update_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr.update_date IS '수정 일시';


--
-- TOC entry 4251 (class 0 OID 0)
-- Dependencies: 410
-- Name: COLUMN ingr.update_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 411 (class 1259 OID 47134)
-- Name: ingr_als; Type: TABLE; Schema: recipe; Owner: postgres
--

CREATE TABLE recipe.ingr_als (
    ingr_id character varying(20) NOT NULL,
    ingr_als_id character varying(20) DEFAULT recipe.fn_get_biz_id('ingr_als'::text) NOT NULL,
    ingr_als_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


ALTER TABLE recipe.ingr_als OWNER TO postgres;

--
-- TOC entry 4252 (class 0 OID 0)
-- Dependencies: 411
-- Name: TABLE ingr_als; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON TABLE recipe.ingr_als IS '식재료 별칭';


--
-- TOC entry 4253 (class 0 OID 0)
-- Dependencies: 411
-- Name: COLUMN ingr_als.ingr_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr_als.ingr_id IS '표준 식재료 ID';


--
-- TOC entry 4254 (class 0 OID 0)
-- Dependencies: 411
-- Name: COLUMN ingr_als.ingr_als_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr_als.ingr_als_id IS '식재료 별칭 ID(기존 발급값 유지)';


--
-- TOC entry 4255 (class 0 OID 0)
-- Dependencies: 411
-- Name: COLUMN ingr_als.ingr_als_nm; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr_als.ingr_als_nm IS '식재료 별칭명';


--
-- TOC entry 4256 (class 0 OID 0)
-- Dependencies: 411
-- Name: COLUMN ingr_als.create_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr_als.create_date IS '생성 일시';


--
-- TOC entry 4257 (class 0 OID 0)
-- Dependencies: 411
-- Name: COLUMN ingr_als.create_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr_als.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4258 (class 0 OID 0)
-- Dependencies: 411
-- Name: COLUMN ingr_als.update_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr_als.update_date IS '수정 일시';


--
-- TOC entry 4259 (class 0 OID 0)
-- Dependencies: 411
-- Name: COLUMN ingr_als.update_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.ingr_als.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 407 (class 1259 OID 47091)
-- Name: rcp; Type: TABLE; Schema: recipe; Owner: postgres
--

CREATE TABLE recipe.rcp (
    rcp_id character varying(20) DEFAULT recipe.fn_get_biz_id('rcp'::text) NOT NULL,
    rcp_seq text NOT NULL,
    rcp_raw_id character varying(20) NOT NULL,
    rcp_nm text NOT NULL,
    cook_mthd_cd character varying(20) NOT NULL,
    rcp_serving_weight_value numeric(10,2),
    rcp_energy_kcal numeric(10,2),
    rcp_carbs_g numeric(10,2),
    rcp_protein_g numeric(10,2),
    rcp_fat_g numeric(10,2),
    rcp_sodium_mg numeric(10,2),
    rcp_nutrition_status character varying(20) DEFAULT 'UNCHECKED'::character varying NOT NULL,
    rcp_nutrition_review_note text,
    rcp_hash_tag text,
    rcp_image_url text,
    rcp_image_large_url text,
    rcp_sodium_reduction_tip_txt text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT ck_rcp_nutrition_status CHECK (((rcp_nutrition_status)::text = ANY ((ARRAY['UNCHECKED'::character varying, 'VALID'::character varying, 'REVIEW_REQUIRED'::character varying, 'REVIEWED_OK'::character varying])::text[])))
);


ALTER TABLE recipe.rcp OWNER TO postgres;

--
-- TOC entry 4260 (class 0 OID 0)
-- Dependencies: 407
-- Name: TABLE rcp; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON TABLE recipe.rcp IS '정제 레시피';


--
-- TOC entry 4261 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_id IS '레시피 ID(내부 발급, 단독 PK)';


--
-- TOC entry 4262 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_seq; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_seq IS '식약처 원본 레시피 번호(RCP_SEQ)';


--
-- TOC entry 4263 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_raw_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_raw_id IS '최종 반영 원본 수집 회차 ID';


--
-- TOC entry 4264 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_nm; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_nm IS '레시피명';


--
-- TOC entry 4265 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.cook_mthd_cd; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.cook_mthd_cd IS '조리 방법 코드(공통코드 COOK_MTHD)';


--
-- TOC entry 4266 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_serving_weight_value; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_serving_weight_value IS '제공량(원본 INFO_WGT, 단위 미확정)';


--
-- TOC entry 4267 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_energy_kcal; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_energy_kcal IS '열량(kcal)';


--
-- TOC entry 4268 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_carbs_g; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_carbs_g IS '탄수화물(g)';


--
-- TOC entry 4269 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_protein_g; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_protein_g IS '단백질(g)';


--
-- TOC entry 4270 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_fat_g; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_fat_g IS '지방(g)';


--
-- TOC entry 4271 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_sodium_mg; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_sodium_mg IS '나트륨(mg)';


--
-- TOC entry 4272 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_nutrition_status; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_nutrition_status IS '영양정보 검증 상태';


--
-- TOC entry 4273 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_nutrition_review_note; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_nutrition_review_note IS '영양정보 검토 메모';


--
-- TOC entry 4274 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_hash_tag; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_hash_tag IS '해시태그(원본 HASH_TAG)';


--
-- TOC entry 4275 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_image_url; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_image_url IS '대표 이미지 URL';


--
-- TOC entry 4276 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_image_large_url; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_image_large_url IS '큰 대표 이미지 URL';


--
-- TOC entry 4277 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.rcp_sodium_reduction_tip_txt; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.rcp_sodium_reduction_tip_txt IS '나트륨 저감 조리 팁';


--
-- TOC entry 4278 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.create_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.create_date IS '생성 일시';


--
-- TOC entry 4279 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.create_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4280 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.update_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.update_date IS '수정 일시';


--
-- TOC entry 4281 (class 0 OID 0)
-- Dependencies: 407
-- Name: COLUMN rcp.update_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 404 (class 1259 OID 47061)
-- Name: rcp_cat; Type: TABLE; Schema: recipe; Owner: postgres
--

CREATE TABLE recipe.rcp_cat (
    rcp_cat_id character varying(20) DEFAULT recipe.fn_get_biz_id('rcp_cat'::text) NOT NULL,
    rcp_cat_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


ALTER TABLE recipe.rcp_cat OWNER TO postgres;

--
-- TOC entry 4282 (class 0 OID 0)
-- Dependencies: 404
-- Name: TABLE rcp_cat; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON TABLE recipe.rcp_cat IS '요리 분류';


--
-- TOC entry 4283 (class 0 OID 0)
-- Dependencies: 404
-- Name: COLUMN rcp_cat.rcp_cat_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat.rcp_cat_id IS '요리 분류 ID';


--
-- TOC entry 4284 (class 0 OID 0)
-- Dependencies: 404
-- Name: COLUMN rcp_cat.rcp_cat_nm; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat.rcp_cat_nm IS '요리 분류명(원본 RCP_PAT2 또는 별도 승인된 분류)';


--
-- TOC entry 4285 (class 0 OID 0)
-- Dependencies: 404
-- Name: COLUMN rcp_cat.create_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat.create_date IS '생성 일시';


--
-- TOC entry 4286 (class 0 OID 0)
-- Dependencies: 404
-- Name: COLUMN rcp_cat.create_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4287 (class 0 OID 0)
-- Dependencies: 404
-- Name: COLUMN rcp_cat.update_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat.update_date IS '수정 일시';


--
-- TOC entry 4288 (class 0 OID 0)
-- Dependencies: 404
-- Name: COLUMN rcp_cat.update_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 408 (class 1259 OID 47105)
-- Name: rcp_cat_rel; Type: TABLE; Schema: recipe; Owner: postgres
--

CREATE TABLE recipe.rcp_cat_rel (
    rcp_id character varying(20) NOT NULL,
    rcp_cat_id character varying(20) NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


ALTER TABLE recipe.rcp_cat_rel OWNER TO postgres;

--
-- TOC entry 4289 (class 0 OID 0)
-- Dependencies: 408
-- Name: TABLE rcp_cat_rel; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON TABLE recipe.rcp_cat_rel IS '레시피·요리 분류 관계(N:M)';


--
-- TOC entry 4290 (class 0 OID 0)
-- Dependencies: 408
-- Name: COLUMN rcp_cat_rel.rcp_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat_rel.rcp_id IS '레시피 ID';


--
-- TOC entry 4291 (class 0 OID 0)
-- Dependencies: 408
-- Name: COLUMN rcp_cat_rel.rcp_cat_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat_rel.rcp_cat_id IS '요리 분류 ID';


--
-- TOC entry 4292 (class 0 OID 0)
-- Dependencies: 408
-- Name: COLUMN rcp_cat_rel.create_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat_rel.create_date IS '생성 일시';


--
-- TOC entry 4293 (class 0 OID 0)
-- Dependencies: 408
-- Name: COLUMN rcp_cat_rel.create_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat_rel.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4294 (class 0 OID 0)
-- Dependencies: 408
-- Name: COLUMN rcp_cat_rel.update_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat_rel.update_date IS '수정 일시';


--
-- TOC entry 4295 (class 0 OID 0)
-- Dependencies: 408
-- Name: COLUMN rcp_cat_rel.update_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_cat_rel.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 413 (class 1259 OID 47162)
-- Name: rcp_ingr; Type: TABLE; Schema: recipe; Owner: postgres
--

CREATE TABLE recipe.rcp_ingr (
    rcp_id character varying(20) NOT NULL,
    ingr_id character varying(20) NOT NULL,
    rcp_raw_id character varying(20) NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);


ALTER TABLE recipe.rcp_ingr OWNER TO postgres;

--
-- TOC entry 4296 (class 0 OID 0)
-- Dependencies: 413
-- Name: TABLE rcp_ingr; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON TABLE recipe.rcp_ingr IS '레시피별 사용 식재료(N:M)';


--
-- TOC entry 4297 (class 0 OID 0)
-- Dependencies: 413
-- Name: COLUMN rcp_ingr.rcp_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr.rcp_id IS '레시피 ID';


--
-- TOC entry 4298 (class 0 OID 0)
-- Dependencies: 413
-- Name: COLUMN rcp_ingr.ingr_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr.ingr_id IS '표준 식재료 ID';


--
-- TOC entry 4299 (class 0 OID 0)
-- Dependencies: 413
-- Name: COLUMN rcp_ingr.rcp_raw_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr.rcp_raw_id IS '관계 생성 근거 원본 수집 회차 ID';


--
-- TOC entry 4300 (class 0 OID 0)
-- Dependencies: 413
-- Name: COLUMN rcp_ingr.create_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr.create_date IS '생성 일시';


--
-- TOC entry 4301 (class 0 OID 0)
-- Dependencies: 413
-- Name: COLUMN rcp_ingr.create_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4302 (class 0 OID 0)
-- Dependencies: 413
-- Name: COLUMN rcp_ingr.update_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr.update_date IS '수정 일시';


--
-- TOC entry 4303 (class 0 OID 0)
-- Dependencies: 413
-- Name: COLUMN rcp_ingr.update_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 412 (class 1259 OID 47146)
-- Name: rcp_ingr_stg; Type: TABLE; Schema: recipe; Owner: postgres
--

CREATE TABLE recipe.rcp_ingr_stg (
    rcp_raw_id character varying(20) NOT NULL,
    rcp_raw_seq character varying(6) NOT NULL,
    rcp_ingr_stg_id character varying(20) DEFAULT recipe.fn_get_biz_id('rcp_ingr_stg'::text) NOT NULL,
    rcp_ingr_line_no smallint NOT NULL,
    ingr_id character varying(20),
    rcp_ingr_raw_txt text NOT NULL,
    rcp_ingr_parsed_nm text,
    rcp_ingr_qty numeric(12,3),
    rcp_ingr_unit_nm text,
    rcp_ingr_section_txt text,
    rcp_ingr_status character varying(20) DEFAULT 'PENDING_REVIEW'::character varying NOT NULL,
    rcp_ingr_review_note text,
    rcp_ingr_parser_version character varying(50),
    rcp_ingr_approved_date timestamp with time zone,
    rcp_ingr_approved_user_id character varying(50),
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT ck_rcp_ingr_stg_approval CHECK ((((rcp_ingr_status)::text <> ALL ((ARRAY['AUTO_APPROVED'::character varying, 'MANUAL_APPROVED'::character varying])::text[])) OR (ingr_id IS NOT NULL))),
    CONSTRAINT ck_rcp_ingr_stg_rcp_ingr_line_no CHECK ((rcp_ingr_line_no > 0)),
    CONSTRAINT ck_rcp_ingr_stg_status CHECK (((rcp_ingr_status)::text = ANY ((ARRAY['PENDING_REVIEW'::character varying, 'AUTO_APPROVED'::character varying, 'MANUAL_APPROVED'::character varying, 'REJECTED'::character varying])::text[])))
);


ALTER TABLE recipe.rcp_ingr_stg OWNER TO postgres;

--
-- TOC entry 4304 (class 0 OID 0)
-- Dependencies: 412
-- Name: TABLE rcp_ingr_stg; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON TABLE recipe.rcp_ingr_stg IS '레시피 재료 원문 파싱 및 검토';


--
-- TOC entry 4305 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_raw_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_raw_id IS '원본 수집 회차 ID';


--
-- TOC entry 4306 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_raw_seq; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_raw_seq IS '원본 행 순번';


--
-- TOC entry 4307 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_stg_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_stg_id IS '재료 staging ID';


--
-- TOC entry 4308 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_line_no; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_line_no IS '재료 원문 등장 순번';


--
-- TOC entry 4309 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.ingr_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.ingr_id IS '매핑된 표준 식재료 ID(미매핑 NULL)';


--
-- TOC entry 4310 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_raw_txt; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_raw_txt IS '재료 항목 원문';


--
-- TOC entry 4311 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_parsed_nm; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_parsed_nm IS '파싱된 재료명 후보';


--
-- TOC entry 4312 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_qty; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_qty IS '파싱된 수량';


--
-- TOC entry 4313 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_unit_nm; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_unit_nm IS '파싱된 단위';


--
-- TOC entry 4314 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_section_txt; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_section_txt IS '재료 구획(주재료·양념 등)';


--
-- TOC entry 4315 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_status; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_status IS '검토 상태';


--
-- TOC entry 4316 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_review_note; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_review_note IS '파싱 결과 및 검토 메모';


--
-- TOC entry 4317 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_parser_version; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_parser_version IS '파서 버전';


--
-- TOC entry 4318 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_approved_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_approved_date IS '승인 일시';


--
-- TOC entry 4319 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.rcp_ingr_approved_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_approved_user_id IS '승인 사용자 ID';


--
-- TOC entry 4320 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.create_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.create_date IS '생성 일시';


--
-- TOC entry 4321 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.create_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4322 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.update_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.update_date IS '수정 일시';


--
-- TOC entry 4323 (class 0 OID 0)
-- Dependencies: 412
-- Name: COLUMN rcp_ingr_stg.update_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_ingr_stg.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 403 (class 1259 OID 47049)
-- Name: rcp_raw; Type: TABLE; Schema: recipe; Owner: postgres
--

CREATE TABLE recipe.rcp_raw (
    rcp_raw_id character varying(20) NOT NULL,
    rcp_raw_seq character varying(6) NOT NULL,
    rcp_seq text NOT NULL,
    rcp_nm text,
    rcp_way2 text,
    rcp_pat2 text,
    info_wgt text,
    info_eng text,
    info_car text,
    info_pro text,
    info_fat text,
    info_na text,
    hash_tag text,
    att_file_no_main text,
    att_file_no_mk text,
    rcp_parts_dtls text,
    manual01 text,
    manual_img01 text,
    manual02 text,
    manual_img02 text,
    manual03 text,
    manual_img03 text,
    manual04 text,
    manual_img04 text,
    manual05 text,
    manual_img05 text,
    manual06 text,
    manual_img06 text,
    manual07 text,
    manual_img07 text,
    manual08 text,
    manual_img08 text,
    manual09 text,
    manual_img09 text,
    manual10 text,
    manual_img10 text,
    manual11 text,
    manual_img11 text,
    manual12 text,
    manual_img12 text,
    manual13 text,
    manual_img13 text,
    manual14 text,
    manual_img14 text,
    manual15 text,
    manual_img15 text,
    manual16 text,
    manual_img16 text,
    manual17 text,
    manual_img17 text,
    manual18 text,
    manual_img18 text,
    manual19 text,
    manual_img19 text,
    manual20 text,
    manual_img20 text,
    rcp_na_tip text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT ck_rcp_raw_rcp_raw_seq CHECK ((((rcp_raw_seq)::text ~ '^[0-9]{6}$'::text) AND ((rcp_raw_seq)::text <> '000000'::text)))
);


ALTER TABLE recipe.rcp_raw OWNER TO postgres;

--
-- TOC entry 4324 (class 0 OID 0)
-- Dependencies: 403
-- Name: TABLE rcp_raw; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON TABLE recipe.rcp_raw IS '식약처 레시피 원본(수집 회차별)';


--
-- TOC entry 4325 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.rcp_raw_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.rcp_raw_id IS '원본 수집 회차 ID';


--
-- TOC entry 4326 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.rcp_raw_seq; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.rcp_raw_seq IS '수집 회차 내 원본 행 순번(CSV 행 순서, 000001부터)';


--
-- TOC entry 4327 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.rcp_seq; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.rcp_seq IS '식약처 원본 레시피 번호(RCP_SEQ)';


--
-- TOC entry 4328 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.rcp_nm; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.rcp_nm IS '원본 RCP_NM 레시피명';


--
-- TOC entry 4329 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.rcp_way2; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.rcp_way2 IS '원본 RCP_WAY2 조리 방법';


--
-- TOC entry 4330 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.rcp_pat2; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.rcp_pat2 IS '원본 RCP_PAT2 요리 종류';


--
-- TOC entry 4331 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.info_wgt; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.info_wgt IS '원본 INFO_WGT 제공량';


--
-- TOC entry 4332 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.info_eng; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.info_eng IS '원본 INFO_ENG 열량';


--
-- TOC entry 4333 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.info_car; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.info_car IS '원본 INFO_CAR 탄수화물';


--
-- TOC entry 4334 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.info_pro; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.info_pro IS '원본 INFO_PRO 단백질';


--
-- TOC entry 4335 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.info_fat; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.info_fat IS '원본 INFO_FAT 지방';


--
-- TOC entry 4336 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.info_na; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.info_na IS '원본 INFO_NA 나트륨';


--
-- TOC entry 4337 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.hash_tag; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.hash_tag IS '원본 HASH_TAG 해시태그';


--
-- TOC entry 4338 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.att_file_no_main; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.att_file_no_main IS '원본 ATT_FILE_NO_MAIN 대표 이미지 URL';


--
-- TOC entry 4339 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.att_file_no_mk; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.att_file_no_mk IS '원본 ATT_FILE_NO_MK 큰 이미지 URL';


--
-- TOC entry 4340 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.rcp_parts_dtls; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.rcp_parts_dtls IS '원본 RCP_PARTS_DTLS 재료 문자열';


--
-- TOC entry 4341 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual01; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual01 IS '원본 MANUAL01 조리 단계';


--
-- TOC entry 4342 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img01; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img01 IS '원본 MANUAL_IMG01 단계 이미지 URL';


--
-- TOC entry 4343 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual02; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual02 IS '원본 MANUAL02 조리 단계';


--
-- TOC entry 4344 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img02; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img02 IS '원본 MANUAL_IMG02 단계 이미지 URL';


--
-- TOC entry 4345 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual03; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual03 IS '원본 MANUAL03 조리 단계';


--
-- TOC entry 4346 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img03; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img03 IS '원본 MANUAL_IMG03 단계 이미지 URL';


--
-- TOC entry 4347 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual04; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual04 IS '원본 MANUAL04 조리 단계';


--
-- TOC entry 4348 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img04; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img04 IS '원본 MANUAL_IMG04 단계 이미지 URL';


--
-- TOC entry 4349 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual05; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual05 IS '원본 MANUAL05 조리 단계';


--
-- TOC entry 4350 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img05; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img05 IS '원본 MANUAL_IMG05 단계 이미지 URL';


--
-- TOC entry 4351 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual06; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual06 IS '원본 MANUAL06 조리 단계';


--
-- TOC entry 4352 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img06; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img06 IS '원본 MANUAL_IMG06 단계 이미지 URL';


--
-- TOC entry 4353 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual07; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual07 IS '원본 MANUAL07 조리 단계';


--
-- TOC entry 4354 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img07; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img07 IS '원본 MANUAL_IMG07 단계 이미지 URL';


--
-- TOC entry 4355 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual08; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual08 IS '원본 MANUAL08 조리 단계';


--
-- TOC entry 4356 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img08; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img08 IS '원본 MANUAL_IMG08 단계 이미지 URL';


--
-- TOC entry 4357 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual09; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual09 IS '원본 MANUAL09 조리 단계';


--
-- TOC entry 4358 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img09; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img09 IS '원본 MANUAL_IMG09 단계 이미지 URL';


--
-- TOC entry 4359 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual10; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual10 IS '원본 MANUAL10 조리 단계';


--
-- TOC entry 4360 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img10; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img10 IS '원본 MANUAL_IMG10 단계 이미지 URL';


--
-- TOC entry 4361 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual11; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual11 IS '원본 MANUAL11 조리 단계';


--
-- TOC entry 4362 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img11; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img11 IS '원본 MANUAL_IMG11 단계 이미지 URL';


--
-- TOC entry 4363 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual12; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual12 IS '원본 MANUAL12 조리 단계';


--
-- TOC entry 4364 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img12; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img12 IS '원본 MANUAL_IMG12 단계 이미지 URL';


--
-- TOC entry 4365 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual13; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual13 IS '원본 MANUAL13 조리 단계';


--
-- TOC entry 4366 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img13; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img13 IS '원본 MANUAL_IMG13 단계 이미지 URL';


--
-- TOC entry 4367 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual14; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual14 IS '원본 MANUAL14 조리 단계';


--
-- TOC entry 4368 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img14; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img14 IS '원본 MANUAL_IMG14 단계 이미지 URL';


--
-- TOC entry 4369 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual15; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual15 IS '원본 MANUAL15 조리 단계';


--
-- TOC entry 4370 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img15; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img15 IS '원본 MANUAL_IMG15 단계 이미지 URL';


--
-- TOC entry 4371 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual16; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual16 IS '원본 MANUAL16 조리 단계';


--
-- TOC entry 4372 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img16; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img16 IS '원본 MANUAL_IMG16 단계 이미지 URL';


--
-- TOC entry 4373 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual17; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual17 IS '원본 MANUAL17 조리 단계';


--
-- TOC entry 4374 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img17; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img17 IS '원본 MANUAL_IMG17 단계 이미지 URL';


--
-- TOC entry 4375 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual18; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual18 IS '원본 MANUAL18 조리 단계';


--
-- TOC entry 4376 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img18; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img18 IS '원본 MANUAL_IMG18 단계 이미지 URL';


--
-- TOC entry 4377 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual19; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual19 IS '원본 MANUAL19 조리 단계';


--
-- TOC entry 4378 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img19; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img19 IS '원본 MANUAL_IMG19 단계 이미지 URL';


--
-- TOC entry 4379 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual20; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual20 IS '원본 MANUAL20 조리 단계';


--
-- TOC entry 4380 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.manual_img20; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.manual_img20 IS '원본 MANUAL_IMG20 단계 이미지 URL';


--
-- TOC entry 4381 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.rcp_na_tip; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.rcp_na_tip IS '원본 RCP_NA_TIP 나트륨 저감 팁';


--
-- TOC entry 4382 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.create_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.create_date IS '생성 일시';


--
-- TOC entry 4383 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.create_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4384 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.update_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.update_date IS '수정 일시';


--
-- TOC entry 4385 (class 0 OID 0)
-- Dependencies: 403
-- Name: COLUMN rcp_raw.update_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_raw.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 409 (class 1259 OID 47112)
-- Name: rcp_step; Type: TABLE; Schema: recipe; Owner: postgres
--

CREATE TABLE recipe.rcp_step (
    rcp_id character varying(20) NOT NULL,
    step_no smallint NOT NULL,
    rcp_step_instruction_txt text NOT NULL,
    rcp_step_image_url text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT ck_rcp_step_no CHECK (((step_no >= 1) AND (step_no <= 20)))
);


ALTER TABLE recipe.rcp_step OWNER TO postgres;

--
-- TOC entry 4386 (class 0 OID 0)
-- Dependencies: 409
-- Name: TABLE rcp_step; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON TABLE recipe.rcp_step IS '레시피 조리 단계';


--
-- TOC entry 4387 (class 0 OID 0)
-- Dependencies: 409
-- Name: COLUMN rcp_step.rcp_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_step.rcp_id IS '레시피 ID';


--
-- TOC entry 4388 (class 0 OID 0)
-- Dependencies: 409
-- Name: COLUMN rcp_step.step_no; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_step.step_no IS '조리 단계 번호(원본 MANUAL 번호)';


--
-- TOC entry 4389 (class 0 OID 0)
-- Dependencies: 409
-- Name: COLUMN rcp_step.rcp_step_instruction_txt; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_step.rcp_step_instruction_txt IS '조리 단계 설명';


--
-- TOC entry 4390 (class 0 OID 0)
-- Dependencies: 409
-- Name: COLUMN rcp_step.rcp_step_image_url; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_step.rcp_step_image_url IS '조리 단계 이미지 URL';


--
-- TOC entry 4391 (class 0 OID 0)
-- Dependencies: 409
-- Name: COLUMN rcp_step.create_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_step.create_date IS '생성 일시';


--
-- TOC entry 4392 (class 0 OID 0)
-- Dependencies: 409
-- Name: COLUMN rcp_step.create_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_step.create_user_id IS '생성 사용자 ID';


--
-- TOC entry 4393 (class 0 OID 0)
-- Dependencies: 409
-- Name: COLUMN rcp_step.update_date; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_step.update_date IS '수정 일시';


--
-- TOC entry 4394 (class 0 OID 0)
-- Dependencies: 409
-- Name: COLUMN rcp_step.update_user_id; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON COLUMN recipe.rcp_step.update_user_id IS '수정 사용자 ID';


--
-- TOC entry 401 (class 1259 OID 47046)
-- Name: seq_import_batch; Type: SEQUENCE; Schema: recipe; Owner: postgres
--

CREATE SEQUENCE recipe.seq_import_batch
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE recipe.seq_import_batch OWNER TO postgres;

--
-- TOC entry 4395 (class 0 OID 0)
-- Dependencies: 401
-- Name: SEQUENCE seq_import_batch; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON SEQUENCE recipe.seq_import_batch IS '원본 수집 회차 ID(rcp_raw_id) 발급; 회차당 한 번';


--
-- TOC entry 399 (class 1259 OID 47044)
-- Name: seq_ingr; Type: SEQUENCE; Schema: recipe; Owner: postgres
--

CREATE SEQUENCE recipe.seq_ingr
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE recipe.seq_ingr OWNER TO postgres;

--
-- TOC entry 4396 (class 0 OID 0)
-- Dependencies: 399
-- Name: SEQUENCE seq_ingr; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON SEQUENCE recipe.seq_ingr IS '표준 식재료 ID 발급';


--
-- TOC entry 400 (class 1259 OID 47045)
-- Name: seq_ingr_als; Type: SEQUENCE; Schema: recipe; Owner: postgres
--

CREATE SEQUENCE recipe.seq_ingr_als
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE recipe.seq_ingr_als OWNER TO postgres;

--
-- TOC entry 4397 (class 0 OID 0)
-- Dependencies: 400
-- Name: SEQUENCE seq_ingr_als; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON SEQUENCE recipe.seq_ingr_als IS '식재료 별칭 ID 발급';


--
-- TOC entry 398 (class 1259 OID 47043)
-- Name: seq_rcp; Type: SEQUENCE; Schema: recipe; Owner: postgres
--

CREATE SEQUENCE recipe.seq_rcp
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE recipe.seq_rcp OWNER TO postgres;

--
-- TOC entry 4398 (class 0 OID 0)
-- Dependencies: 398
-- Name: SEQUENCE seq_rcp; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON SEQUENCE recipe.seq_rcp IS '레시피 ID 발급';


--
-- TOC entry 397 (class 1259 OID 47042)
-- Name: seq_rcp_cat; Type: SEQUENCE; Schema: recipe; Owner: postgres
--

CREATE SEQUENCE recipe.seq_rcp_cat
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE recipe.seq_rcp_cat OWNER TO postgres;

--
-- TOC entry 4399 (class 0 OID 0)
-- Dependencies: 397
-- Name: SEQUENCE seq_rcp_cat; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON SEQUENCE recipe.seq_rcp_cat IS '요리 종류 ID 발급';


--
-- TOC entry 402 (class 1259 OID 47047)
-- Name: seq_rcp_ingr_stg; Type: SEQUENCE; Schema: recipe; Owner: postgres
--

CREATE SEQUENCE recipe.seq_rcp_ingr_stg
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;


ALTER SEQUENCE recipe.seq_rcp_ingr_stg OWNER TO postgres;

--
-- TOC entry 4400 (class 0 OID 0)
-- Dependencies: 402
-- Name: SEQUENCE seq_rcp_ingr_stg; Type: COMMENT; Schema: recipe; Owner: postgres
--

COMMENT ON SEQUENCE recipe.seq_rcp_ingr_stg IS '재료 staging ID 발급';


--
-- TOC entry 4048 (class 2606 OID 47090)
-- Name: common_cd pk_common_cd; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.common_cd
    ADD CONSTRAINT pk_common_cd PRIMARY KEY (common_code_grp_id, common_cd);


--
-- TOC entry 4046 (class 2606 OID 47081)
-- Name: common_code_grp pk_common_code_grp; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.common_code_grp
    ADD CONSTRAINT pk_common_code_grp PRIMARY KEY (common_code_grp_id);


--
-- TOC entry 4059 (class 2606 OID 47131)
-- Name: ingr pk_ingr; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.ingr
    ADD CONSTRAINT pk_ingr PRIMARY KEY (ingr_id);


--
-- TOC entry 4063 (class 2606 OID 47143)
-- Name: ingr_als pk_ingr_als; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.ingr_als
    ADD CONSTRAINT pk_ingr_als PRIMARY KEY (ingr_id, ingr_als_id);


--
-- TOC entry 4050 (class 2606 OID 47102)
-- Name: rcp pk_rcp; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.rcp
    ADD CONSTRAINT pk_rcp PRIMARY KEY (rcp_id);


--
-- TOC entry 4042 (class 2606 OID 47070)
-- Name: rcp_cat pk_rcp_cat; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.rcp_cat
    ADD CONSTRAINT pk_rcp_cat PRIMARY KEY (rcp_cat_id);


--
-- TOC entry 4055 (class 2606 OID 47111)
-- Name: rcp_cat_rel pk_rcp_cat_rel; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.rcp_cat_rel
    ADD CONSTRAINT pk_rcp_cat_rel PRIMARY KEY (rcp_id, rcp_cat_id);


--
-- TOC entry 4073 (class 2606 OID 47168)
-- Name: rcp_ingr pk_rcp_ingr; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.rcp_ingr
    ADD CONSTRAINT pk_rcp_ingr PRIMARY KEY (rcp_id, ingr_id);


--
-- TOC entry 4068 (class 2606 OID 47159)
-- Name: rcp_ingr_stg pk_rcp_ingr_stg; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.rcp_ingr_stg
    ADD CONSTRAINT pk_rcp_ingr_stg PRIMARY KEY (rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id);


--
-- TOC entry 4038 (class 2606 OID 47058)
-- Name: rcp_raw pk_rcp_raw; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.rcp_raw
    ADD CONSTRAINT pk_rcp_raw PRIMARY KEY (rcp_raw_id, rcp_raw_seq);


--
-- TOC entry 4057 (class 2606 OID 47121)
-- Name: rcp_step pk_rcp_step; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.rcp_step
    ADD CONSTRAINT pk_rcp_step PRIMARY KEY (rcp_id, step_no);


--
-- TOC entry 4065 (class 2606 OID 47145)
-- Name: ingr_als uq_ingr_als_ingr_als_nm; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.ingr_als
    ADD CONSTRAINT uq_ingr_als_ingr_als_nm UNIQUE (ingr_id, ingr_als_nm);


--
-- TOC entry 4061 (class 2606 OID 47133)
-- Name: ingr uq_ingr_ingr_nm; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.ingr
    ADD CONSTRAINT uq_ingr_ingr_nm UNIQUE (ingr_nm);


--
-- TOC entry 4044 (class 2606 OID 47072)
-- Name: rcp_cat uq_rcp_cat_rcp_cat_nm; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.rcp_cat
    ADD CONSTRAINT uq_rcp_cat_rcp_cat_nm UNIQUE (rcp_cat_nm);


--
-- TOC entry 4070 (class 2606 OID 47161)
-- Name: rcp_ingr_stg uq_rcp_ingr_stg_line_no; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.rcp_ingr_stg
    ADD CONSTRAINT uq_rcp_ingr_stg_line_no UNIQUE (rcp_raw_id, rcp_raw_seq, rcp_ingr_line_no);


--
-- TOC entry 4040 (class 2606 OID 47060)
-- Name: rcp_raw uq_rcp_raw_rcp_seq; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.rcp_raw
    ADD CONSTRAINT uq_rcp_raw_rcp_seq UNIQUE (rcp_raw_id, rcp_seq);


--
-- TOC entry 4052 (class 2606 OID 47104)
-- Name: rcp uq_rcp_rcp_seq; Type: CONSTRAINT; Schema: recipe; Owner: postgres
--

ALTER TABLE ONLY recipe.rcp
    ADD CONSTRAINT uq_rcp_rcp_seq UNIQUE (rcp_seq);


--
-- TOC entry 4053 (class 1259 OID 47169)
-- Name: ix_rcp_cat_rel_cat_key; Type: INDEX; Schema: recipe; Owner: postgres
--

CREATE INDEX ix_rcp_cat_rel_cat_key ON recipe.rcp_cat_rel USING btree (rcp_cat_id, rcp_id);


--
-- TOC entry 4071 (class 1259 OID 47170)
-- Name: ix_rcp_ingr_ingr_key; Type: INDEX; Schema: recipe; Owner: postgres
--

CREATE INDEX ix_rcp_ingr_ingr_key ON recipe.rcp_ingr USING btree (ingr_id, rcp_id);


--
-- TOC entry 4066 (class 1259 OID 47171)
-- Name: ix_rcp_ingr_stg_ingr_key; Type: INDEX; Schema: recipe; Owner: postgres
--

CREATE INDEX ix_rcp_ingr_stg_ingr_key ON recipe.rcp_ingr_stg USING btree (ingr_id);


-- Completed on 2026-10-29 21:24:26

--
-- PostgreSQL database dump complete
--

