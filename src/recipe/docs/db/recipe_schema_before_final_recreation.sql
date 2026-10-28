-- Proposed recipe schema DDL (9 tables after common-code consolidation). Run only after validating the recipe schema scope.
-- Assumes schema recipe already exists. No physical FK constraints are defined.
-- Logical references are validated by ETL and docs/db/recipe_integrity_checks.sql.

CREATE SEQUENCE recipe.seq_ingr_cat START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE recipe.seq_ingr START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE recipe.seq_import_batch START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
COMMENT ON SEQUENCE recipe.seq_import_batch IS '수집 회차 ID를 batch당 한 번 발급하는 독립 시퀀스';

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

CREATE TABLE recipe.rcp_raw (
    batch_id varchar(20) NOT NULL,
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
    CONSTRAINT pk_rcp_raw PRIMARY KEY (batch_id, rcp_seq)
);



CREATE TABLE recipe.cmn_cd (
    cd_grp varchar(20) NOT NULL,
    cd varchar(20) NOT NULL,
    cd_nm text NOT NULL,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_cmn_cd PRIMARY KEY (cd_grp, cd)
);

CREATE TABLE recipe.rcp (
    rcp_seq text NOT NULL,
    batch_id varchar(20) NOT NULL,
    rcp_nm text NOT NULL,
    rcp_cat_cd varchar(20) NOT NULL,
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
    CONSTRAINT pk_rcp PRIMARY KEY (rcp_seq),
    CONSTRAINT ck_rcp_nutrition_status CHECK (rcp_nutrition_status IN ('UNCHECKED','VALID','REVIEW_REQUIRED','REVIEWED_OK'))
);

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
    ingr_als_nm text NOT NULL,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_ingr_als PRIMARY KEY (ingr_cat_id, ingr_id, ingr_als_nm),
    CONSTRAINT uq_ingr_als_ingr_als_nm UNIQUE (ingr_als_nm)
);

CREATE TABLE recipe.rcp_ingr_stg (
    batch_id varchar(20) NOT NULL,
    rcp_seq text NOT NULL,
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
    CONSTRAINT pk_rcp_ingr_stg PRIMARY KEY (batch_id, rcp_seq, rcp_ingr_line_no),
    CONSTRAINT ck_rcp_ingr_stg_rcp_ingr_line_no CHECK (rcp_ingr_line_no > 0),
    CONSTRAINT ck_rcp_ingr_stg_status CHECK (rcp_ingr_status IN ('PENDING_REVIEW','AUTO_APPROVED','MANUAL_APPROVED','REJECTED')),
    CONSTRAINT ck_rcp_ingr_stg_ingredient_pair CHECK ((ingr_cat_id IS NULL AND ingr_id IS NULL) OR (ingr_cat_id IS NOT NULL AND ingr_id IS NOT NULL)),
    CONSTRAINT ck_rcp_ingr_stg_approval CHECK ((rcp_ingr_status IN ('AUTO_APPROVED','MANUAL_APPROVED') AND ingr_cat_id IS NOT NULL AND ingr_id IS NOT NULL) OR rcp_ingr_status NOT IN ('AUTO_APPROVED','MANUAL_APPROVED'))
);

CREATE TABLE recipe.rcp_ingr (
    ingr_cat_id varchar(20) NOT NULL,
    ingr_id varchar(20) NOT NULL,
    rcp_seq text NOT NULL,
    batch_id varchar(20) NOT NULL,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_rcp_ingr PRIMARY KEY (ingr_cat_id, ingr_id, rcp_seq)
);

CREATE TABLE recipe.rcp_step (
    rcp_seq text NOT NULL,
    rcp_step_no smallint NOT NULL,
    rcp_step_instruction_txt text NOT NULL,
    rcp_step_image_url text,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_rcp_step PRIMARY KEY (rcp_seq, rcp_step_no),
    CONSTRAINT ck_rcp_step_rcp_step_no CHECK (rcp_step_no BETWEEN 1 AND 20)
);

-- Indexes support logical references and the non-leading recipe lookup.
CREATE INDEX ix_rcp_batch_seq ON recipe.rcp (batch_id, rcp_seq);
CREATE INDEX ix_rcp_rcp_cat_cd ON recipe.rcp (rcp_cat_cd);
CREATE INDEX ix_rcp_cook_mthd_cd ON recipe.rcp (cook_mthd_cd);
CREATE INDEX ix_rcp_ingr_stg_rcp_seq ON recipe.rcp_ingr_stg (rcp_seq);
CREATE INDEX ix_rcp_ingr_stg_ingr_key ON recipe.rcp_ingr_stg (ingr_cat_id, ingr_id);
CREATE INDEX ix_rcp_ingr_rcp_seq ON recipe.rcp_ingr (rcp_seq);

COMMENT ON TABLE recipe.rcp_raw IS '식약처 레시피 CSV 원본 55개 컬럼을 수집 회차별로 보존하는 테이블';
COMMENT ON COLUMN recipe.rcp_raw.batch_id IS '수집회차 식별자; 회차당 한 번 발급하여 관련 행에 공유';
COMMENT ON COLUMN recipe.rcp_raw.rcp_seq IS '식약처 원본 레시피 식별자';
COMMENT ON COLUMN recipe.rcp_raw.rcp_nm IS '원본 RCP_NM 레시피명';
COMMENT ON COLUMN recipe.rcp_raw.rcp_way2 IS '원본 RCP_WAY2 조리방법';
COMMENT ON COLUMN recipe.rcp_raw.rcp_pat2 IS '원본 RCP_PAT2 요리종류';
COMMENT ON COLUMN recipe.rcp_raw.info_wgt IS '원본 INFO_WGT 제공량 문자열; 단위 미확정';
COMMENT ON COLUMN recipe.rcp_raw.info_eng IS '원본 INFO_ENG 열량 문자열';
COMMENT ON COLUMN recipe.rcp_raw.info_car IS '원본 INFO_CAR 탄수화물 문자열';
COMMENT ON COLUMN recipe.rcp_raw.info_pro IS '원본 INFO_PRO 단백질 문자열';
COMMENT ON COLUMN recipe.rcp_raw.info_fat IS '원본 INFO_FAT 지방 문자열';
COMMENT ON COLUMN recipe.rcp_raw.info_na IS '원본 INFO_NA 나트륨 문자열';
COMMENT ON COLUMN recipe.rcp_raw.hash_tag IS '원본 HASH_TAG 문자열; 재료 목록으로 간주하지 않음';
COMMENT ON COLUMN recipe.rcp_raw.att_file_no_main IS '원본 ATT_FILE_NO_MAIN 대표 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.att_file_no_mk IS '원본 ATT_FILE_NO_MK 큰 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.rcp_parts_dtls IS '원본 RCP_PARTS_DTLS 재료·분량 전체 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual01 IS '원본 MANUAL01 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img01 IS '원본 MANUAL_IMG01 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual02 IS '원본 MANUAL02 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img02 IS '원본 MANUAL_IMG02 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual03 IS '원본 MANUAL03 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img03 IS '원본 MANUAL_IMG03 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual04 IS '원본 MANUAL04 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img04 IS '원본 MANUAL_IMG04 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual05 IS '원본 MANUAL05 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img05 IS '원본 MANUAL_IMG05 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual06 IS '원본 MANUAL06 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img06 IS '원본 MANUAL_IMG06 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual07 IS '원본 MANUAL07 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img07 IS '원본 MANUAL_IMG07 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual08 IS '원본 MANUAL08 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img08 IS '원본 MANUAL_IMG08 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual09 IS '원본 MANUAL09 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img09 IS '원본 MANUAL09 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual10 IS '원본 MANUAL10 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img10 IS '원본 MANUAL10 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual11 IS '원본 MANUAL11 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img11 IS '원본 MANUAL11 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual12 IS '원본 MANUAL12 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img12 IS '원본 MANUAL12 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual13 IS '원본 MANUAL13 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img13 IS '원본 MANUAL13 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual14 IS '원본 MANUAL14 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img14 IS '원본 MANUAL14 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual15 IS '원본 MANUAL15 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img15 IS '원본 MANUAL15 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual16 IS '원본 MANUAL16 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img16 IS '원본 MANUAL16 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual17 IS '원본 MANUAL17 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img17 IS '원본 MANUAL17 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual18 IS '원본 MANUAL18 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img18 IS '원본 MANUAL18 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual19 IS '원본 MANUAL19 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img19 IS '원본 MANUAL19 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.manual20 IS '원본 MANUAL20 조리 단계 문자열';
COMMENT ON COLUMN recipe.rcp_raw.manual_img20 IS '원본 MANUAL_IMG20 조리 단계 이미지 주소';
COMMENT ON COLUMN recipe.rcp_raw.rcp_na_tip IS '원본 RCP_NA_TIP 나트륨 저감 조리 팁';
COMMENT ON COLUMN recipe.rcp_raw.create_date IS '최초 생성 일시';
COMMENT ON COLUMN recipe.rcp_raw.create_user_id IS '최초 생성 사용자 식별자';
COMMENT ON COLUMN recipe.rcp_raw.update_date IS '최종 수정 일시; UPDATE 시 ETL이 명시적으로 갱신';
COMMENT ON COLUMN recipe.rcp_raw.update_user_id IS '최종 수정 사용자 식별자';



COMMENT ON TABLE recipe.rcp IS '현재 정제 레시피, 영양정보 및 품질 검토 상태';
COMMENT ON COLUMN recipe.rcp.rcp_seq IS '식약처 원본 레시피 식별자';
COMMENT ON COLUMN recipe.rcp.batch_id IS '수집회차 식별자; 회차당 한 번 발급하여 관련 행에 공유';
COMMENT ON COLUMN recipe.rcp.rcp_nm IS '정제 레시피명';
COMMENT ON COLUMN recipe.rcp.rcp_cat_cd IS '요리 종류 코드';
COMMENT ON COLUMN recipe.rcp.cook_mthd_cd IS '조리 방법 코드';
COMMENT ON COLUMN recipe.rcp.rcp_serving_weight_value IS '원본 INFO_WGT 숫자 변환 후보; 단위 미확정';
COMMENT ON COLUMN recipe.rcp.rcp_energy_kcal IS '원본 INFO_ENG 열량; 이상값 자동 수정 금지';
COMMENT ON COLUMN recipe.rcp.rcp_carbs_g IS '원본 INFO_CAR 탄수화물';
COMMENT ON COLUMN recipe.rcp.rcp_protein_g IS '원본 INFO_PRO 단백질';
COMMENT ON COLUMN recipe.rcp.rcp_fat_g IS '원본 INFO_FAT 지방';
COMMENT ON COLUMN recipe.rcp.rcp_sodium_mg IS '원본 INFO_NA 나트륨';
COMMENT ON COLUMN recipe.rcp.rcp_nutrition_status IS '영양정보 검증 상태';
COMMENT ON COLUMN recipe.rcp.rcp_nutrition_review_note IS '영양정보 검토 메모 및 이상값 근거';
COMMENT ON COLUMN recipe.rcp.rcp_hash_tag IS '원본 HASH_TAG; 재료 정규화 근거로 사용하지 않음';
COMMENT ON COLUMN recipe.rcp.rcp_image_url IS '대표 이미지 URL';
COMMENT ON COLUMN recipe.rcp.rcp_image_large_url IS '큰 대표 이미지 URL';
COMMENT ON COLUMN recipe.rcp.rcp_sodium_reduction_tip_txt IS '원본 나트륨 저감 조리 팁';
COMMENT ON COLUMN recipe.rcp.create_date IS '최초 생성 일시';
COMMENT ON COLUMN recipe.rcp.create_user_id IS '최초 생성 사용자 식별자';
COMMENT ON COLUMN recipe.rcp.update_date IS '최종 수정 일시; UPDATE 시 ETL이 명시적으로 갱신';
COMMENT ON COLUMN recipe.rcp.update_user_id IS '최종 수정 사용자 식별자';

COMMENT ON TABLE recipe.ingr_cat IS '프로젝트가 정의하는 식재료 분류 마스터';
COMMENT ON COLUMN recipe.ingr_cat.ingr_cat_id IS '식재료 분류 업무 식별자';
COMMENT ON COLUMN recipe.ingr_cat.ingr_cat_nm IS '식재료 분류명';
COMMENT ON COLUMN recipe.ingr_cat.ingr_cat_desc IS '식재료 분류 설명';
COMMENT ON COLUMN recipe.ingr_cat.create_date IS '최초 생성 일시';
COMMENT ON COLUMN recipe.ingr_cat.create_user_id IS '최초 생성 사용자 식별자';
COMMENT ON COLUMN recipe.ingr_cat.update_date IS '최종 수정 일시; UPDATE 시 ETL이 명시적으로 갱신';
COMMENT ON COLUMN recipe.ingr_cat.update_user_id IS '최종 수정 사용자 식별자';

COMMENT ON TABLE recipe.ingr IS '표준 식재료 정보; 각 식재료는 프로젝트 분류 하나를 가짐';
COMMENT ON COLUMN recipe.ingr.ingr_id IS '표준 식재료 업무 식별자';
COMMENT ON COLUMN recipe.ingr.ingr_cat_id IS '식재료 분류 업무 식별자';
COMMENT ON COLUMN recipe.ingr.ingr_nm IS '표준 식재료명';
COMMENT ON COLUMN recipe.ingr.create_date IS '최초 생성 일시';
COMMENT ON COLUMN recipe.ingr.create_user_id IS '최초 생성 사용자 식별자';
COMMENT ON COLUMN recipe.ingr.update_date IS '최종 수정 일시; UPDATE 시 ETL이 명시적으로 갱신';
COMMENT ON COLUMN recipe.ingr.update_user_id IS '최종 수정 사용자 식별자';

COMMENT ON TABLE recipe.ingr_als IS '검증된 식재료 동의어와 표준 식재료의 논리 연결';
COMMENT ON COLUMN recipe.ingr_als.ingr_als_nm IS '검증된 동의어 문자열; 자연키';
COMMENT ON COLUMN recipe.ingr_als.ingr_cat_id IS '식재료 분류 업무 식별자';
COMMENT ON COLUMN recipe.ingr_als.ingr_id IS '표준 식재료 업무 식별자';
COMMENT ON COLUMN recipe.ingr_als.create_date IS '최초 생성 일시';
COMMENT ON COLUMN recipe.ingr_als.create_user_id IS '최초 생성 사용자 식별자';
COMMENT ON COLUMN recipe.ingr_als.update_date IS '최종 수정 일시; UPDATE 시 ETL이 명시적으로 갱신';
COMMENT ON COLUMN recipe.ingr_als.update_user_id IS '최종 수정 사용자 식별자';

COMMENT ON TABLE recipe.rcp_ingr_stg IS '원본 재료 문자열 파싱 및 승인 대기 내역';
COMMENT ON COLUMN recipe.rcp_ingr_stg.batch_id IS '수집회차 식별자; 회차당 한 번 발급하여 관련 행에 공유';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_seq IS '식약처 원본 레시피 식별자';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_line_no IS '레시피 재료 행 순번';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_raw_txt IS '원본에서 분리한 재료 행 문자열';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_parsed_nm IS '파싱된 후보 식재료명; 미확정 가능';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_qty IS '파싱된 수량 후보';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_unit_nm IS '파싱된 단위 원문';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_section_txt IS '재료 구획 또는 그룹 원문';
COMMENT ON COLUMN recipe.rcp_ingr_stg.ingr_cat_id IS '식재료 분류 업무 식별자';
COMMENT ON COLUMN recipe.rcp_ingr_stg.ingr_id IS '표준 식재료 업무 식별자';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_status IS '검토 및 승인 상태';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_review_note IS '자동/수동 검토 메모';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_parser_version IS '파싱 로직 버전 식별자';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_approved_date IS '승인 일시';
COMMENT ON COLUMN recipe.rcp_ingr_stg.rcp_ingr_approved_user_id IS '승인 사용자 식별자';
COMMENT ON COLUMN recipe.rcp_ingr_stg.create_date IS '최초 생성 일시';
COMMENT ON COLUMN recipe.rcp_ingr_stg.create_user_id IS '최초 생성 사용자 식별자';
COMMENT ON COLUMN recipe.rcp_ingr_stg.update_date IS '최종 수정 일시; UPDATE 시 ETL이 명시적으로 갱신';
COMMENT ON COLUMN recipe.rcp_ingr_stg.update_user_id IS '최종 수정 사용자 식별자';

COMMENT ON TABLE recipe.cmn_cd IS '요리 종류와 조리 방법 공통코드';
COMMENT ON COLUMN recipe.cmn_cd.cd_grp IS '공통코드 그룹';
COMMENT ON COLUMN recipe.cmn_cd.cd IS '공통코드';
COMMENT ON COLUMN recipe.cmn_cd.cd_nm IS '공통코드명';
COMMENT ON COLUMN recipe.cmn_cd.create_date IS '최초 생성 일시';
COMMENT ON COLUMN recipe.cmn_cd.create_user_id IS '최초 생성 사용자 식별자';
COMMENT ON COLUMN recipe.cmn_cd.update_date IS '최종 수정 일시; UPDATE 시 ETL이 명시적으로 갱신';
COMMENT ON COLUMN recipe.cmn_cd.update_user_id IS '최종 수정 사용자 식별자';

COMMENT ON COLUMN recipe.rcp_ingr.rcp_seq IS '식약처 원본 레시피 식별자';
COMMENT ON TABLE recipe.rcp_ingr IS '레시피와 표준 식재료의 중복 없는 사용 관계';
COMMENT ON COLUMN recipe.rcp_ingr.ingr_cat_id IS '식재료 분류 업무 식별자';
COMMENT ON COLUMN recipe.rcp_ingr.ingr_id IS '표준 식재료 업무 식별자';
COMMENT ON COLUMN recipe.rcp_ingr.batch_id IS '수집회차 식별자; 회차당 한 번 발급하여 관련 행에 공유';
COMMENT ON COLUMN recipe.rcp_ingr.create_date IS '최초 생성 일시';
COMMENT ON COLUMN recipe.rcp_ingr.create_user_id IS '최초 생성 사용자 식별자';
COMMENT ON COLUMN recipe.rcp_ingr.update_date IS '최종 수정 일시; UPDATE 시 ETL이 명시적으로 갱신';
COMMENT ON COLUMN recipe.rcp_ingr.update_user_id IS '최종 수정 사용자 식별자';

COMMENT ON TABLE recipe.rcp_step IS '레시피 조리 순서 및 단계별 이미지; 원본 순번과 공백 보존';
COMMENT ON COLUMN recipe.rcp_step.rcp_seq IS '식약처 원본 레시피 식별자';
COMMENT ON COLUMN recipe.rcp_step.rcp_step_no IS '원본 MANUAL 접미 순번; 재번호 매기지 않음';
COMMENT ON COLUMN recipe.rcp_step.rcp_step_instruction_txt IS '조리 단계 설명';
COMMENT ON COLUMN recipe.rcp_step.rcp_step_image_url IS '조리 단계 이미지 URL';
COMMENT ON COLUMN recipe.rcp_step.create_date IS '최초 생성 일시';
COMMENT ON COLUMN recipe.rcp_step.create_user_id IS '최초 생성 사용자 식별자';
COMMENT ON COLUMN recipe.rcp_step.update_date IS '최종 수정 일시; UPDATE 시 ETL이 명시적으로 갱신';
COMMENT ON COLUMN recipe.rcp_step.update_user_id IS '최종 수정 사용자 식별자';
