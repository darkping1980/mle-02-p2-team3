-- Final recipe schema DDL (11 tables). Assumes schema recipe already exists.
-- No physical FK constraints. Logical parent references are validated by ETL and
-- docs/db/recipe_integrity_checks.sql. Reference masters (rcp_cat, common_code_grp,
-- common_cd) are registered by the CSV loader from actual CSV values, not seeded here.
-- Full drop/recreate of an existing schema: docs/db/recipe_schema_rebuild.sql.

CREATE SEQUENCE recipe.seq_rcp_cat START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE recipe.seq_rcp START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE recipe.seq_ingr_cat START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE recipe.seq_ingr START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE recipe.seq_ingr_als START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE recipe.seq_import_batch START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE recipe.seq_rcp_ingr_stg START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
COMMENT ON SEQUENCE recipe.seq_rcp_cat IS '요리 종류 ID 발급';
COMMENT ON SEQUENCE recipe.seq_rcp IS '레시피 ID 발급';
COMMENT ON SEQUENCE recipe.seq_ingr_cat IS '식재료 분류 ID 발급';
COMMENT ON SEQUENCE recipe.seq_ingr IS '표준 식재료 ID 발급';
COMMENT ON SEQUENCE recipe.seq_ingr_als IS '식재료 별칭 ID 발급';
COMMENT ON SEQUENCE recipe.seq_import_batch IS '원본 수집 회차 ID(rcp_raw_id) 발급; 회차당 한 번';
COMMENT ON SEQUENCE recipe.seq_rcp_ingr_stg IS '재료 staging ID 발급';

CREATE OR REPLACE FUNCTION recipe.fn_get_biz_id(p_tbl_nm text)
RETURNS varchar(20)
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, recipe
AS $$
DECLARE
    v_seq regclass;
BEGIN
    IF p_tbl_nm IS NULL OR p_tbl_nm !~ '^[A-Za-z][A-Za-z0-9_]*$' THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = format('Invalid recipe table name for business ID: %s', coalesce(p_tbl_nm, '<NULL>'));
    END IF;

    v_seq := to_regclass(format('%I.%I', 'recipe', 'seq_' || lower(p_tbl_nm)));
    IF v_seq IS NULL OR NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS c
        WHERE c.oid = v_seq
          AND c.relkind = 'S'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42P01',
            MESSAGE = format('Recipe ID sequence does not exist: recipe.seq_%s', lower(p_tbl_nm));
    END IF;

    RETURN to_char((clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date, 'YYYYMMDD')
        || '_' || lpad(nextval(v_seq)::text, 6, '0');
END;
$$;

COMMENT ON FUNCTION recipe.fn_get_biz_id(text) IS 'recipe.seq_<테이블명> 시퀀스로 YYYYMMDD_000001 형식 업무 ID 발급(Asia/Seoul 기준)';

-- ---------------------------------------------------------------------
-- 원본
-- ---------------------------------------------------------------------
CREATE TABLE recipe.rcp_raw (
    rcp_raw_id varchar(20) NOT NULL,
    rcp_raw_seq varchar(6) NOT NULL,
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
    manual01 text, manual_img01 text,
    manual02 text, manual_img02 text,
    manual03 text, manual_img03 text,
    manual04 text, manual_img04 text,
    manual05 text, manual_img05 text,
    manual06 text, manual_img06 text,
    manual07 text, manual_img07 text,
    manual08 text, manual_img08 text,
    manual09 text, manual_img09 text,
    manual10 text, manual_img10 text,
    manual11 text, manual_img11 text,
    manual12 text, manual_img12 text,
    manual13 text, manual_img13 text,
    manual14 text, manual_img14 text,
    manual15 text, manual_img15 text,
    manual16 text, manual_img16 text,
    manual17 text, manual_img17 text,
    manual18 text, manual_img18 text,
    manual19 text, manual_img19 text,
    manual20 text, manual_img20 text,
    rcp_na_tip text,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_rcp_raw PRIMARY KEY (rcp_raw_id, rcp_raw_seq),
    CONSTRAINT uq_rcp_raw_rcp_seq UNIQUE (rcp_raw_id, rcp_seq),
    CONSTRAINT ck_rcp_raw_rcp_raw_seq CHECK (rcp_raw_seq ~ '^[0-9]{6}$' AND rcp_raw_seq <> '000000')
);

-- ---------------------------------------------------------------------
-- 참조 마스터
-- ---------------------------------------------------------------------
CREATE TABLE recipe.rcp_cat (
    rcp_cat_id varchar(20) NOT NULL DEFAULT recipe.fn_get_biz_id('rcp_cat'),
    rcp_cat_nm text NOT NULL,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_rcp_cat PRIMARY KEY (rcp_cat_id),
    CONSTRAINT uq_rcp_cat_rcp_cat_nm UNIQUE (rcp_cat_nm)
);

CREATE TABLE recipe.common_code_grp (
    common_code_grp_id varchar(20) NOT NULL,
    common_code_grp_nm text NOT NULL,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_common_code_grp PRIMARY KEY (common_code_grp_id)
);

CREATE TABLE recipe.common_cd (
    common_code_grp_id varchar(20) NOT NULL,
    common_cd varchar(20) NOT NULL,
    common_cd_nm text NOT NULL,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_common_cd PRIMARY KEY (common_code_grp_id, common_cd)
);

-- ---------------------------------------------------------------------
-- 레시피
-- ---------------------------------------------------------------------
CREATE TABLE recipe.rcp (
    rcp_cat_id varchar(20) NOT NULL,
    rcp_id varchar(20) NOT NULL DEFAULT recipe.fn_get_biz_id('rcp'),
    rcp_seq text NOT NULL,
    rcp_raw_id varchar(20) NOT NULL,
    rcp_nm text NOT NULL,
    cook_mthd_cd varchar(20) NOT NULL,
    rcp_serving_weight_value numeric(10,2),
    rcp_energy_kcal numeric(10,2),
    rcp_carbs_g numeric(10,2),
    rcp_protein_g numeric(10,2),
    rcp_fat_g numeric(10,2),
    rcp_sodium_mg numeric(10,2),
    rcp_nutrition_status varchar(20) NOT NULL DEFAULT 'UNCHECKED',
    rcp_nutrition_review_note text,
    rcp_hash_tag text,
    rcp_image_url text,
    rcp_image_large_url text,
    rcp_sodium_reduction_tip_txt text,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_rcp PRIMARY KEY (rcp_cat_id, rcp_id),
    CONSTRAINT uq_rcp_rcp_id UNIQUE (rcp_id),
    CONSTRAINT uq_rcp_rcp_seq UNIQUE (rcp_seq),
    CONSTRAINT ck_rcp_nutrition_status CHECK (rcp_nutrition_status IN ('UNCHECKED','VALID','REVIEW_REQUIRED','REVIEWED_OK'))
);

CREATE TABLE recipe.rcp_step (
    rcp_cat_id varchar(20) NOT NULL,
    rcp_id varchar(20) NOT NULL,
    step_no smallint NOT NULL,
    rcp_step_instruction_txt text NOT NULL,
    rcp_step_image_url text,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_rcp_step PRIMARY KEY (rcp_cat_id, rcp_id, step_no),
    CONSTRAINT ck_rcp_step_no CHECK (step_no BETWEEN 1 AND 20)
);

-- ---------------------------------------------------------------------
-- 식재료
-- ---------------------------------------------------------------------
CREATE TABLE recipe.ingr_cat (
    ingr_cat_id varchar(20) NOT NULL DEFAULT recipe.fn_get_biz_id('ingr_cat'),
    ingr_cat_nm text NOT NULL,
    ingr_cat_desc text,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_ingr_cat PRIMARY KEY (ingr_cat_id),
    CONSTRAINT uq_ingr_cat_ingr_cat_nm UNIQUE (ingr_cat_nm)
);

CREATE TABLE recipe.ingr (
    ingr_cat_id varchar(20) NOT NULL,
    ingr_id varchar(20) NOT NULL DEFAULT recipe.fn_get_biz_id('ingr'),
    ingr_nm text NOT NULL,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_ingr PRIMARY KEY (ingr_cat_id, ingr_id),
    CONSTRAINT uq_ingr_ingr_nm UNIQUE (ingr_nm)
);

CREATE TABLE recipe.ingr_als (
    ingr_cat_id varchar(20) NOT NULL,
    ingr_id varchar(20) NOT NULL,
    ingr_als_id varchar(20) NOT NULL DEFAULT recipe.fn_get_biz_id('ingr_als'),
    ingr_als_nm text NOT NULL,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_ingr_als PRIMARY KEY (ingr_cat_id, ingr_id, ingr_als_id),
    CONSTRAINT uq_ingr_als_ingr_als_nm UNIQUE (ingr_cat_id, ingr_id, ingr_als_nm)
);

-- ---------------------------------------------------------------------
-- 재료 staging / 레시피별 사용 식재료
-- ---------------------------------------------------------------------
CREATE TABLE recipe.rcp_ingr_stg (
    rcp_raw_id varchar(20) NOT NULL,
    rcp_raw_seq varchar(6) NOT NULL,
    rcp_ingr_stg_id varchar(20) NOT NULL DEFAULT recipe.fn_get_biz_id('rcp_ingr_stg'),
    rcp_ingr_line_no smallint NOT NULL,
    ingr_cat_id varchar(20),
    ingr_id varchar(20),
    rcp_ingr_raw_txt text NOT NULL,
    rcp_ingr_parsed_nm text,
    rcp_ingr_qty numeric(12,3),
    rcp_ingr_unit_nm text,
    rcp_ingr_section_txt text,
    rcp_ingr_status varchar(20) NOT NULL DEFAULT 'PENDING_REVIEW',
    rcp_ingr_review_note text,
    rcp_ingr_parser_version varchar(50),
    rcp_ingr_approved_date timestamptz,
    rcp_ingr_approved_user_id varchar(50),
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_rcp_ingr_stg PRIMARY KEY (rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id),
    CONSTRAINT uq_rcp_ingr_stg_line_no UNIQUE (rcp_raw_id, rcp_raw_seq, rcp_ingr_line_no),
    CONSTRAINT ck_rcp_ingr_stg_rcp_ingr_line_no CHECK (rcp_ingr_line_no > 0),
    CONSTRAINT ck_rcp_ingr_stg_status CHECK (rcp_ingr_status IN ('PENDING_REVIEW','AUTO_APPROVED','MANUAL_APPROVED','REJECTED')),
    CONSTRAINT ck_rcp_ingr_stg_ingredient_pair CHECK ((ingr_cat_id IS NULL AND ingr_id IS NULL) OR (ingr_cat_id IS NOT NULL AND ingr_id IS NOT NULL)),
    CONSTRAINT ck_rcp_ingr_stg_approval CHECK ((rcp_ingr_status IN ('AUTO_APPROVED','MANUAL_APPROVED') AND ingr_cat_id IS NOT NULL AND ingr_id IS NOT NULL) OR rcp_ingr_status NOT IN ('AUTO_APPROVED','MANUAL_APPROVED'))
);

CREATE TABLE recipe.rcp_ingr (
    ingr_cat_id varchar(20) NOT NULL,
    ingr_id varchar(20) NOT NULL,
    rcp_cat_id varchar(20) NOT NULL,
    rcp_id varchar(20) NOT NULL,
    rcp_raw_id varchar(20) NOT NULL,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_rcp_ingr PRIMARY KEY (ingr_cat_id, ingr_id, rcp_cat_id, rcp_id)
);

-- 레시피 기준 사용 식재료 조회(PK 후행부)와 표준 식재료 기준 staging 조회용.
CREATE INDEX ix_rcp_ingr_rcp_key ON recipe.rcp_ingr (rcp_cat_id, rcp_id);
CREATE INDEX ix_rcp_ingr_stg_ingr_key ON recipe.rcp_ingr_stg (ingr_cat_id, ingr_id);

-- ---------------------------------------------------------------------
-- COMMENT
-- ---------------------------------------------------------------------
COMMENT ON TABLE recipe.rcp_raw IS '식약처 레시피 원본(수집 회차별)';
COMMENT ON COLUMN recipe.rcp_raw.rcp_raw_id IS '원본 수집 회차 ID';
COMMENT ON COLUMN recipe.rcp_raw.rcp_raw_seq IS '수집 회차 내 원본 행 순번(CSV 행 순서, 000001부터)';
COMMENT ON COLUMN recipe.rcp_raw.rcp_seq IS '식약처 원본 레시피 번호(RCP_SEQ)';
COMMENT ON COLUMN recipe.rcp_raw.rcp_nm IS '원본 RCP_NM 레시피명';
COMMENT ON COLUMN recipe.rcp_raw.rcp_way2 IS '원본 RCP_WAY2 조리 방법';
COMMENT ON COLUMN recipe.rcp_raw.rcp_pat2 IS '원본 RCP_PAT2 요리 종류';
COMMENT ON COLUMN recipe.rcp_raw.info_wgt IS '원본 INFO_WGT 제공량';
COMMENT ON COLUMN recipe.rcp_raw.info_eng IS '원본 INFO_ENG 열량';
COMMENT ON COLUMN recipe.rcp_raw.info_car IS '원본 INFO_CAR 탄수화물';
COMMENT ON COLUMN recipe.rcp_raw.info_pro IS '원본 INFO_PRO 단백질';
COMMENT ON COLUMN recipe.rcp_raw.info_fat IS '원본 INFO_FAT 지방';
COMMENT ON COLUMN recipe.rcp_raw.info_na IS '원본 INFO_NA 나트륨';
COMMENT ON COLUMN recipe.rcp_raw.hash_tag IS '원본 HASH_TAG 해시태그';
COMMENT ON COLUMN recipe.rcp_raw.att_file_no_main IS '원본 ATT_FILE_NO_MAIN 대표 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.att_file_no_mk IS '원본 ATT_FILE_NO_MK 큰 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.rcp_parts_dtls IS '원본 RCP_PARTS_DTLS 재료 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual01 IS '원본 MANUAL01 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img01 IS '원본 MANUAL_IMG01 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual02 IS '원본 MANUAL02 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img02 IS '원본 MANUAL_IMG02 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual03 IS '원본 MANUAL03 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img03 IS '원본 MANUAL_IMG03 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual04 IS '원본 MANUAL04 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img04 IS '원본 MANUAL_IMG04 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual05 IS '원본 MANUAL05 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img05 IS '원본 MANUAL_IMG05 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual06 IS '원본 MANUAL06 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img06 IS '원본 MANUAL_IMG06 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual07 IS '원본 MANUAL07 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img07 IS '원본 MANUAL_IMG07 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual08 IS '원본 MANUAL08 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img08 IS '원본 MANUAL_IMG08 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual09 IS '원본 MANUAL09 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img09 IS '원본 MANUAL_IMG09 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual10 IS '원본 MANUAL10 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img10 IS '원본 MANUAL_IMG10 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual11 IS '원본 MANUAL11 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img11 IS '원본 MANUAL_IMG11 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual12 IS '원본 MANUAL12 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img12 IS '원본 MANUAL_IMG12 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual13 IS '원본 MANUAL13 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img13 IS '원본 MANUAL_IMG13 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual14 IS '원본 MANUAL14 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img14 IS '원본 MANUAL_IMG14 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual15 IS '원본 MANUAL15 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img15 IS '원본 MANUAL_IMG15 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual16 IS '원본 MANUAL16 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img16 IS '원본 MANUAL_IMG16 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual17 IS '원본 MANUAL17 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img17 IS '원본 MANUAL_IMG17 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual18 IS '원본 MANUAL18 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img18 IS '원본 MANUAL_IMG18 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual19 IS '원본 MANUAL19 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img19 IS '원본 MANUAL_IMG19 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.manual20 IS '원본 MANUAL20 조리 단계';
COMMENT ON COLUMN recipe.rcp_raw.manual_img20 IS '원본 MANUAL_IMG20 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_raw.rcp_na_tip IS '원본 RCP_NA_TIP 나트륨 저감 팁';
COMMENT ON COLUMN recipe.rcp_raw.create_date IS '생성 일시';
COMMENT ON COLUMN recipe.rcp_raw.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN recipe.rcp_raw.update_date IS '수정 일시';
COMMENT ON COLUMN recipe.rcp_raw.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE recipe.rcp_cat IS '요리 종류';
COMMENT ON COLUMN recipe.rcp_cat.rcp_cat_id IS '요리 종류 ID';
COMMENT ON COLUMN recipe.rcp_cat.rcp_cat_nm IS '요리 종류명(원본 RCP_PAT2)';
COMMENT ON COLUMN recipe.rcp_cat.create_date IS '생성 일시';
COMMENT ON COLUMN recipe.rcp_cat.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN recipe.rcp_cat.update_date IS '수정 일시';
COMMENT ON COLUMN recipe.rcp_cat.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE recipe.common_code_grp IS '공통코드 그룹';
COMMENT ON COLUMN recipe.common_code_grp.common_code_grp_id IS '공통코드 그룹 ID(예: COOK_MTHD)';
COMMENT ON COLUMN recipe.common_code_grp.common_code_grp_nm IS '공통코드 그룹명';
COMMENT ON COLUMN recipe.common_code_grp.create_date IS '생성 일시';
COMMENT ON COLUMN recipe.common_code_grp.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN recipe.common_code_grp.update_date IS '수정 일시';
COMMENT ON COLUMN recipe.common_code_grp.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE recipe.common_cd IS '공통코드';
COMMENT ON COLUMN recipe.common_cd.common_code_grp_id IS '공통코드 그룹 ID';
COMMENT ON COLUMN recipe.common_cd.common_cd IS '공통코드';
COMMENT ON COLUMN recipe.common_cd.common_cd_nm IS '공통코드명';
COMMENT ON COLUMN recipe.common_cd.create_date IS '생성 일시';
COMMENT ON COLUMN recipe.common_cd.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN recipe.common_cd.update_date IS '수정 일시';
COMMENT ON COLUMN recipe.common_cd.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE recipe.rcp IS '정제 레시피';
COMMENT ON COLUMN recipe.rcp.rcp_cat_id IS '요리 종류 ID';
COMMENT ON COLUMN recipe.rcp.rcp_id IS '레시피 ID(내부 발급)';
COMMENT ON COLUMN recipe.rcp.rcp_seq IS '식약처 원본 레시피 번호(RCP_SEQ)';
COMMENT ON COLUMN recipe.rcp.rcp_raw_id IS '최종 반영 원본 수집 회차 ID';
COMMENT ON COLUMN recipe.rcp.rcp_nm IS '레시피명';
COMMENT ON COLUMN recipe.rcp.cook_mthd_cd IS '조리 방법 코드(공통코드 COOK_MTHD)';
COMMENT ON COLUMN recipe.rcp.rcp_serving_weight_value IS '제공량(원본 INFO_WGT, 단위 미확정)';
COMMENT ON COLUMN recipe.rcp.rcp_energy_kcal IS '열량(kcal)';
COMMENT ON COLUMN recipe.rcp.rcp_carbs_g IS '탄수화물(g)';
COMMENT ON COLUMN recipe.rcp.rcp_protein_g IS '단백질(g)';
COMMENT ON COLUMN recipe.rcp.rcp_fat_g IS '지방(g)';
COMMENT ON COLUMN recipe.rcp.rcp_sodium_mg IS '나트륨(mg)';
COMMENT ON COLUMN recipe.rcp.rcp_nutrition_status IS '영양정보 검증 상태';
COMMENT ON COLUMN recipe.rcp.rcp_nutrition_review_note IS '영양정보 검토 메모';
COMMENT ON COLUMN recipe.rcp.rcp_hash_tag IS '해시태그(원본 HASH_TAG)';
COMMENT ON COLUMN recipe.rcp.rcp_image_url IS '대표 이미지 URL';
COMMENT ON COLUMN recipe.rcp.rcp_image_large_url IS '큰 대표 이미지 URL';
COMMENT ON COLUMN recipe.rcp.rcp_sodium_reduction_tip_txt IS '나트륨 저감 조리 팁';
COMMENT ON COLUMN recipe.rcp.create_date IS '생성 일시';
COMMENT ON COLUMN recipe.rcp.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN recipe.rcp.update_date IS '수정 일시';
COMMENT ON COLUMN recipe.rcp.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE recipe.rcp_step IS '레시피 조리 단계';
COMMENT ON COLUMN recipe.rcp_step.rcp_cat_id IS '요리 종류 ID';
COMMENT ON COLUMN recipe.rcp_step.rcp_id IS '레시피 ID';
COMMENT ON COLUMN recipe.rcp_step.step_no IS '조리 단계 번호(원본 MANUAL 번호)';
COMMENT ON COLUMN recipe.rcp_step.rcp_step_instruction_txt IS '조리 단계 설명';
COMMENT ON COLUMN recipe.rcp_step.rcp_step_image_url IS '조리 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_step.create_date IS '생성 일시';
COMMENT ON COLUMN recipe.rcp_step.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN recipe.rcp_step.update_date IS '수정 일시';
COMMENT ON COLUMN recipe.rcp_step.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE recipe.ingr_cat IS '식재료 분류';
COMMENT ON COLUMN recipe.ingr_cat.ingr_cat_id IS '식재료 분류 ID';
COMMENT ON COLUMN recipe.ingr_cat.ingr_cat_nm IS '식재료 분류명';
COMMENT ON COLUMN recipe.ingr_cat.ingr_cat_desc IS '식재료 분류 설명';
COMMENT ON COLUMN recipe.ingr_cat.create_date IS '생성 일시';
COMMENT ON COLUMN recipe.ingr_cat.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN recipe.ingr_cat.update_date IS '수정 일시';
COMMENT ON COLUMN recipe.ingr_cat.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE recipe.ingr IS '표준 식재료';
COMMENT ON COLUMN recipe.ingr.ingr_cat_id IS '식재료 분류 ID';
COMMENT ON COLUMN recipe.ingr.ingr_id IS '표준 식재료 ID';
COMMENT ON COLUMN recipe.ingr.ingr_nm IS '표준 식재료명';
COMMENT ON COLUMN recipe.ingr.create_date IS '생성 일시';
COMMENT ON COLUMN recipe.ingr.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN recipe.ingr.update_date IS '수정 일시';
COMMENT ON COLUMN recipe.ingr.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE recipe.ingr_als IS '식재료 별칭';
COMMENT ON COLUMN recipe.ingr_als.ingr_cat_id IS '식재료 분류 ID';
COMMENT ON COLUMN recipe.ingr_als.ingr_id IS '표준 식재료 ID';
COMMENT ON COLUMN recipe.ingr_als.ingr_als_id IS '식재료 별칭 ID';
COMMENT ON COLUMN recipe.ingr_als.ingr_als_nm IS '식재료 별칭명';
COMMENT ON COLUMN recipe.ingr_als.create_date IS '생성 일시';
COMMENT ON COLUMN recipe.ingr_als.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN recipe.ingr_als.update_date IS '수정 일시';
COMMENT ON COLUMN recipe.ingr_als.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE recipe.rcp_ingr_stg IS '레시피 재료 원문 파싱 및 검토';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_raw_id IS '원본 수집 회차 ID';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_raw_seq IS '원본 행 순번';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_stg_id IS '재료 staging ID';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_line_no IS '재료 원문 등장 순번';
COMMENT ON COLUMN recipe.rcp_ingr_stg.ingr_cat_id IS '매핑된 식재료 분류 ID';
COMMENT ON COLUMN recipe.rcp_ingr_stg.ingr_id IS '매핑된 표준 식재료 ID';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_raw_txt IS '재료 항목 원문';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_parsed_nm IS '파싱된 재료명 후보';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_qty IS '파싱된 수량';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_unit_nm IS '파싱된 단위';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_section_txt IS '재료 구획(주재료·양념 등)';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_status IS '검토 상태';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_review_note IS '파싱 결과 및 검토 메모';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_parser_version IS '파서 버전';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_approved_date IS '승인 일시';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_approved_user_id IS '승인 사용자 ID';
COMMENT ON COLUMN recipe.rcp_ingr_stg.create_date IS '생성 일시';
COMMENT ON COLUMN recipe.rcp_ingr_stg.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN recipe.rcp_ingr_stg.update_date IS '수정 일시';
COMMENT ON COLUMN recipe.rcp_ingr_stg.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE recipe.rcp_ingr IS '레시피별 사용 식재료';
COMMENT ON COLUMN recipe.rcp_ingr.ingr_cat_id IS '식재료 분류 ID';
COMMENT ON COLUMN recipe.rcp_ingr.ingr_id IS '표준 식재료 ID';
COMMENT ON COLUMN recipe.rcp_ingr.rcp_cat_id IS '요리 종류 ID';
COMMENT ON COLUMN recipe.rcp_ingr.rcp_id IS '레시피 ID';
COMMENT ON COLUMN recipe.rcp_ingr.rcp_raw_id IS '관계 생성 근거 원본 수집 회차 ID';
COMMENT ON COLUMN recipe.rcp_ingr.create_date IS '생성 일시';
COMMENT ON COLUMN recipe.rcp_ingr.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN recipe.rcp_ingr.update_date IS '수정 일시';
COMMENT ON COLUMN recipe.rcp_ingr.update_user_id IS '수정 사용자 ID';
