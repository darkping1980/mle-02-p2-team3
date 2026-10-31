-- V4 integrated creation for an EMPTY db_pipeline schema.
-- No DROP and no physical foreign keys. Apply only after target/row/dependency checks.
-- Product policy is the parent of confirmed benefits; source documents remain evidence.
-- Approval overlap and logical orphan checks are application/validation SQL responsibilities.


CREATE SCHEMA db_pipeline;

COMMENT ON SCHEMA db_pipeline IS '카드 상품 중심 V4 확정 혜택 및 원천 추적 스키마';

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

COMMENT ON FUNCTION db_pipeline.fn_get_biz_id(p_tbl_nm text) IS 'db_pipeline.seq_<테이블명> 시퀀스로 YYYYMMDD_000001 형식 업무 ID 발급(Asia/Seoul 기준)';

CREATE SEQUENCE db_pipeline.seq_card_ai_run
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

CREATE SEQUENCE db_pipeline.seq_card_bnft
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

CREATE SEQUENCE db_pipeline.seq_card_cond
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

CREATE SEQUENCE db_pipeline.seq_card_doc
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

CREATE SEQUENCE db_pipeline.seq_card_doc_chunk
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

CREATE SEQUENCE db_pipeline.seq_card_excl_item
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

CREATE SEQUENCE db_pipeline.seq_card_excl_item_als
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

CREATE SEQUENCE db_pipeline.seq_card_extr_stg
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

CREATE SEQUENCE db_pipeline.seq_card_product AS bigint
    START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1 NO CYCLE;

CREATE SEQUENCE db_pipeline.seq_card_product_variant
    START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

CREATE SEQUENCE db_pipeline.seq_card_policy_version INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_policy_version IS 'card_policy_version.policy_ver_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_bnft_rule INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_bnft_rule IS 'card_bnft_rule.rule_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_bnft_target INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_bnft_target IS 'card_bnft_target.target_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_cond_expr INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_cond_expr IS 'card_cond_expr.expr_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_limit_pool INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_limit_pool IS 'card_limit_pool.pool_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_limit_tier INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_limit_tier IS 'card_limit_tier.tier_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_bnft INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_bnft IS 'card_common_bnft.common_bnft_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_policy_version INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_policy_version IS 'card_common_policy_version.common_ver_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_bnft_rule INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_bnft_rule IS 'card_common_bnft_rule.common_rule_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_cond INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_cond IS 'card_common_cond.common_cond_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_cond_expr INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_cond_expr IS 'card_common_cond_expr.common_expr_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_target INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_target IS 'card_common_target.common_target_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_limit_pool INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_limit_pool IS 'card_common_limit_pool.common_pool_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_limit_tier INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_limit_tier IS 'card_common_limit_tier.common_tier_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_source_evidence INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_source_evidence IS 'card_source_evidence.evidence_id 로컬 업무 ID 발급';

CREATE TABLE db_pipeline.card_product (
    card_id bigint NOT NULL DEFAULT nextval('db_pipeline.seq_card_product'::regclass),
    product_cd varchar(80) NOT NULL,
    product_nm text NOT NULL,
    issuer varchar(50) NOT NULL,
    card_kind_cd varchar(10) NOT NULL,
    product_status_cd varchar(20) NOT NULL DEFAULT 'ACTIVE',
    launched_on date,
    discontinued_on date,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT card_product_pkey PRIMARY KEY (card_id),
    CONSTRAINT card_product_product_cd_key UNIQUE (product_cd),
    CONSTRAINT card_product_card_kind_cd_check CHECK (card_kind_cd IN ('CREDIT','DEBIT')),
    CONSTRAINT card_product_status_check CHECK (product_status_cd IN ('ACTIVE','DISCONTINUED')),
    CONSTRAINT card_product_dates_check CHECK
        (discontinued_on IS NULL OR launched_on IS NULL OR discontinued_on >= launched_on)
);

CREATE TABLE db_pipeline.card_product_variant (
    card_id bigint NOT NULL,
    card_variant_id varchar(20) NOT NULL
        DEFAULT db_pipeline.fn_get_biz_id('card_product_variant'),
    variant_cd varchar(80) NOT NULL,
    variant_nm text NOT NULL,
    brand_cd varchar(30) NOT NULL,
    service_grade_cd varchar(30) NOT NULL DEFAULT 'NONE',
    service_type_cd varchar(30) NOT NULL DEFAULT 'NONE',
    variant_status_cd varchar(20) NOT NULL DEFAULT 'ACTIVE',
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT card_product_variant_pkey PRIMARY KEY (card_id, card_variant_id),
    CONSTRAINT card_product_variant_id_key UNIQUE (card_variant_id),
    CONSTRAINT card_product_variant_cd_key UNIQUE (card_id, variant_cd),
    CONSTRAINT card_product_variant_status_check CHECK
        (variant_status_cd IN ('ACTIVE','DISCONTINUED')),
    CONSTRAINT card_product_variant_codes_check CHECK
        (length(trim(brand_cd)) > 0 AND length(trim(service_grade_cd)) > 0
         AND length(trim(service_type_cd)) > 0)
);

CREATE TABLE db_pipeline.card_policy_version (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_policy_version') NOT NULL,
    policy_ver_no integer NOT NULL,
    policy_scope_cd varchar(20) NOT NULL,
    policy_effect_cd varchar(20) NOT NULL,
    valid_from date NOT NULL,
    valid_to_excl date,
    approved_at timestamptz,
    policy_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id),
    UNIQUE (card_id, policy_ver_no),
    CONSTRAINT card_policy_version_ck_1 CHECK (policy_ver_no > 0),
    CONSTRAINT card_policy_version_ck_2 CHECK (valid_to_excl IS NULL OR valid_to_excl > valid_from),
    CONSTRAINT card_policy_version_ck_3 CHECK (policy_scope_cd IN ('PRODUCT','VARIANT')),
    CONSTRAINT card_policy_version_ck_4 CHECK (policy_effect_cd IN ('BASE','SUPPLEMENT')),
    CONSTRAINT card_policy_version_ck_5 CHECK (policy_status_cd IN ('DRAFT','APPROVED','RETIRED')),
    CONSTRAINT card_policy_version_ck_6 CHECK (policy_scope_cd <> 'PRODUCT' OR policy_effect_cd = 'BASE')
);

COMMENT ON TABLE db_pipeline.card_policy_version IS '상품 정책 개정판. PRODUCT=전체, VARIANT=지정 발급형 추가 정책. 승인일/적용일/문서일 분리';

COMMENT ON COLUMN db_pipeline.card_policy_version.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_policy_version.policy_ver_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_policy_version.policy_ver_no IS 'policy_ver_no 업무 속성';

COMMENT ON COLUMN db_pipeline.card_policy_version.policy_scope_cd IS 'policy_scope_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_policy_version.policy_effect_cd IS 'policy_effect_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_policy_version.valid_from IS 'valid_from 업무 속성';

COMMENT ON COLUMN db_pipeline.card_policy_version.valid_to_excl IS 'valid_to_excl 업무 속성';

COMMENT ON COLUMN db_pipeline.card_policy_version.approved_at IS 'approved_at 업무 속성';

COMMENT ON COLUMN db_pipeline.card_policy_version.policy_status_cd IS 'policy_status_cd 업무 속성';

CREATE TABLE db_pipeline.card_policy_variant (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_variant_id varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_variant_id)
);

COMMENT ON TABLE db_pipeline.card_policy_variant IS 'VARIANT 정책판에 한해 적용 발급형 명시; 관계 PK는 양 부모 키 상속';

COMMENT ON COLUMN db_pipeline.card_policy_variant.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_policy_variant.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_policy_variant.card_variant_id IS '부모 키 상속 또는 관계 키';

CREATE TABLE db_pipeline.card_policy_doc (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_doc_id varchar(20) NOT NULL,
    source_role_cd varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_doc_id)
);

COMMENT ON TABLE db_pipeline.card_policy_doc IS '승인 정책판의 원천 문서 연결. 문서 개정판과 정책 개정판은 별개';

COMMENT ON COLUMN db_pipeline.card_policy_doc.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_policy_doc.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_policy_doc.card_doc_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_policy_doc.source_role_cd IS 'source_role_cd 업무 속성';

CREATE TABLE db_pipeline.card_bnft (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_bnft') NOT NULL,
    bnft_cd varchar(80) NOT NULL,
    bnft_nm text NOT NULL,
    bnft_type_cd varchar(20) NOT NULL,
    bnft_origin_cd varchar(20) NOT NULL,
    bnft_scope_cd varchar(20) NOT NULL,
    rule_select_cd varchar(30),
    verification_status_cd varchar(25) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id),
    UNIQUE (card_id, policy_ver_id, bnft_cd),
    CONSTRAINT card_bnft_ck_1 CHECK (bnft_origin_cd IN ('LOCAL','COMMON_LINK'))
);

COMMENT ON TABLE db_pipeline.card_bnft IS '상품 정책의 혜택 인스턴스. LOCAL 또는 COMMON_LINK; 계산값 없음. V3 문서 PK를 교체';

COMMENT ON COLUMN db_pipeline.card_bnft.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft.card_bnft_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_cd IS 'bnft_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_nm IS 'bnft_nm 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_type_cd IS 'bnft_type_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_origin_cd IS 'bnft_origin_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_scope_cd IS 'bnft_scope_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft.rule_select_cd IS 'rule_select_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft.verification_status_cd IS 'verification_status_cd 업무 속성';

CREATE TABLE db_pipeline.card_bnft_variant (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    card_variant_id varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, card_variant_id)
);

COMMENT ON TABLE db_pipeline.card_bnft_variant IS 'VARIANT 혜택에만 사용. 혜택의 부모 PK와 발급형의 부모 PK를 연결';

COMMENT ON COLUMN db_pipeline.card_bnft_variant.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_variant.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_variant.card_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_variant.card_variant_id IS '부모 키 상속 또는 관계 키';

CREATE TABLE db_pipeline.card_bnft_rule (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    rule_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_bnft_rule') NOT NULL,
    expr_id varchar(20),
    predicate_state_cd varchar(30) NOT NULL,
    calc_method_cd varchar(40) NOT NULL,
    method_ver integer NOT NULL,
    value_num numeric(18,4),
    value_unit_cd varchar(30),
    payout_unit_cd varchar(30) NOT NULL,
    basis_amt numeric(18,2),
    calc_params jsonb,
    rule_priority integer,
    rule_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, rule_id),
    CONSTRAINT card_bnft_rule_ck_1 CHECK (method_ver > 0),
    CONSTRAINT card_bnft_rule_ck_2 CHECK (value_num IS NULL OR value_num >= 0),
    CONSTRAINT card_bnft_rule_ck_3 CHECK (basis_amt IS NULL OR basis_amt >= 0),
    CONSTRAINT card_bnft_rule_ck_4 CHECK (calc_params IS NULL OR jsonb_typeof(calc_params) = 'object')
);

COMMENT ON TABLE db_pipeline.card_bnft_rule IS 'LOCAL 혜택의 유일한 계산값 원천. COMMON_LINK에는 로컬 규칙 없음';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.card_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.rule_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.expr_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.predicate_state_cd IS 'predicate_state_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.calc_method_cd IS 'calc_method_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.method_ver IS 'method_ver 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.value_num IS 'value_num 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.value_unit_cd IS 'value_unit_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.payout_unit_cd IS 'payout_unit_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.basis_amt IS 'basis_amt 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.calc_params IS 'calc_params 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.rule_priority IS 'rule_priority 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rule.rule_status_cd IS 'rule_status_cd 업무 속성';

CREATE TABLE db_pipeline.card_bnft_target (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    target_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_bnft_target') NOT NULL,
    target_type_cd varchar(30) NOT NULL,
    target_key varchar(100) NOT NULL,
    target_nm text NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, target_id)
);

COMMENT ON TABLE db_pipeline.card_bnft_target IS '혜택 소속 대상. 비율/금액 저장하지 않음';

COMMENT ON COLUMN db_pipeline.card_bnft_target.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_target.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_target.card_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_target.target_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_bnft_target.target_type_cd IS 'target_type_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_target.target_key IS 'target_key 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_target.target_nm IS 'target_nm 업무 속성';

CREATE TABLE db_pipeline.card_bnft_rule_target (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    rule_id varchar(20) NOT NULL,
    target_id varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, rule_id, target_id)
);

COMMENT ON TABLE db_pipeline.card_bnft_rule_target IS '규칙↔대상. 각 부모의 식별 키 전체 상속';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_target.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_target.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_target.card_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_target.rule_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_target.target_id IS '부모 키 상속 또는 관계 키';

CREATE TABLE db_pipeline.card_cond (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_cond_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_cond') NOT NULL,
    cond_type_cd varchar(30) NOT NULL,
    cond_basis_cd varchar(30),
    cond_min_amt numeric(18,2),
    cond_max_amt_excl numeric(18,2),
    predicate_method_cd varchar(40),
    predicate_method_ver integer,
    cond_params jsonb,
    card_excl_item_id varchar(20),
    cond_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_cond_id),
    CONSTRAINT card_cond_ck_1 CHECK (cond_max_amt_excl IS NULL OR cond_min_amt IS NULL OR cond_max_amt_excl > cond_min_amt),
    CONSTRAINT card_cond_ck_2 CHECK (cond_params IS NULL OR jsonb_typeof(cond_params) = 'object')
);

COMMENT ON TABLE db_pipeline.card_cond IS '상품 정책판의 재사용 원자 조건. 혜택의 직접 자식 아님; 출력값/한도 없음';

COMMENT ON COLUMN db_pipeline.card_cond.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_cond.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_cond.card_cond_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_cond.cond_type_cd IS 'cond_type_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_cond.cond_basis_cd IS 'cond_basis_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_cond.cond_min_amt IS 'cond_min_amt 업무 속성';

COMMENT ON COLUMN db_pipeline.card_cond.cond_max_amt_excl IS 'cond_max_amt_excl 업무 속성';

COMMENT ON COLUMN db_pipeline.card_cond.predicate_method_cd IS 'predicate_method_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_cond.predicate_method_ver IS 'predicate_method_ver 업무 속성';

COMMENT ON COLUMN db_pipeline.card_cond.cond_params IS 'cond_params 업무 속성';

COMMENT ON COLUMN db_pipeline.card_cond.card_excl_item_id IS 'card_excl_item_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_cond.cond_status_cd IS 'cond_status_cd 업무 속성';

CREATE TABLE db_pipeline.card_bnft_cond (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    card_cond_id varchar(20) NOT NULL,
    link_role_cd varchar(25) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, card_cond_id)
);

COMMENT ON TABLE db_pipeline.card_bnft_cond IS '혜택 전체↔공유 원자 조건. V3의 문서 PK/중복 card_cond.card_bnft_id 제거';

COMMENT ON COLUMN db_pipeline.card_bnft_cond.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_cond.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_cond.card_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_cond.card_cond_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_cond.link_role_cd IS 'link_role_cd 업무 속성';

CREATE TABLE db_pipeline.card_cond_expr (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    expr_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_cond_expr') NOT NULL,
    expr_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, expr_id)
);

COMMENT ON TABLE db_pipeline.card_cond_expr IS '상품 정책판의 DNF 조건식. 규칙 또는 한도 tier에서 재사용';

COMMENT ON COLUMN db_pipeline.card_cond_expr.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_cond_expr.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_cond_expr.expr_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_cond_expr.expr_status_cd IS 'expr_status_cd 업무 속성';

CREATE TABLE db_pipeline.card_cond_expr_atom (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    expr_id varchar(20) NOT NULL,
    branch_no integer NOT NULL,
    atom_seq integer NOT NULL,
    card_cond_id varchar(20) NOT NULL,
    negate_yn boolean NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, expr_id, branch_no, atom_seq),
    CONSTRAINT card_cond_expr_atom_ck_1 CHECK (branch_no > 0),
    CONSTRAINT card_cond_expr_atom_ck_2 CHECK (atom_seq > 0)
);

COMMENT ON TABLE db_pipeline.card_cond_expr_atom IS '같은 branch의 atom은 AND, branch 사이 OR, negate는 NOT';

COMMENT ON COLUMN db_pipeline.card_cond_expr_atom.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_cond_expr_atom.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_cond_expr_atom.expr_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_cond_expr_atom.branch_no IS 'branch_no 업무 속성';

COMMENT ON COLUMN db_pipeline.card_cond_expr_atom.atom_seq IS 'atom_seq 업무 속성';

COMMENT ON COLUMN db_pipeline.card_cond_expr_atom.card_cond_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_cond_expr_atom.negate_yn IS 'negate_yn 업무 속성';

CREATE TABLE db_pipeline.card_limit_pool (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    pool_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_limit_pool') NOT NULL,
    pool_scope_cd varchar(30) NOT NULL,
    period_cd varchar(20) NOT NULL,
    cap_unit_cd varchar(30) NOT NULL,
    aggregation_key_cd varchar(30) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, pool_id)
);

COMMENT ON TABLE db_pipeline.card_limit_pool IS '상품 정책판의 독립 한도. 여러 규칙이 공유; 혜택의 자식이 아님';

COMMENT ON COLUMN db_pipeline.card_limit_pool.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_limit_pool.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_limit_pool.pool_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_limit_pool.pool_scope_cd IS 'pool_scope_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_limit_pool.period_cd IS 'period_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_limit_pool.cap_unit_cd IS 'cap_unit_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_limit_pool.aggregation_key_cd IS 'aggregation_key_cd 업무 속성';

CREATE TABLE db_pipeline.card_limit_tier (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    pool_id varchar(20) NOT NULL,
    tier_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_limit_tier') NOT NULL,
    expr_id varchar(20),
    predicate_state_cd varchar(30) NOT NULL,
    limit_num numeric(18,2) NOT NULL,
    tier_priority integer,
    PRIMARY KEY (card_id, policy_ver_id, pool_id, tier_id),
    CONSTRAINT card_limit_tier_ck_1 CHECK (limit_num >= 0),
    CONSTRAINT card_limit_tier_ck_2 CHECK (tier_priority IS NULL OR tier_priority > 0)
);

COMMENT ON TABLE db_pipeline.card_limit_tier IS '풀의 조건식별 한도값. 상한 값은 여기만 저장';

COMMENT ON COLUMN db_pipeline.card_limit_tier.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_limit_tier.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_limit_tier.pool_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_limit_tier.tier_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_limit_tier.expr_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_limit_tier.predicate_state_cd IS 'predicate_state_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_limit_tier.limit_num IS 'limit_num 업무 속성';

COMMENT ON COLUMN db_pipeline.card_limit_tier.tier_priority IS 'tier_priority 업무 속성';

CREATE TABLE db_pipeline.card_bnft_rule_pool (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    rule_id varchar(20) NOT NULL,
    pool_id varchar(20) NOT NULL,
    pool_role_cd varchar(30) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, rule_id, pool_id)
);

COMMENT ON TABLE db_pipeline.card_bnft_rule_pool IS '규칙이 소비하는 한도 풀. 영역/전체 풀 동시 연결 가능';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.card_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.rule_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.pool_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.pool_role_cd IS 'pool_role_cd 업무 속성';

CREATE TABLE db_pipeline.card_bnft_rel (
    card_id bigint NOT NULL,
    from_policy_ver_id varchar(20) NOT NULL,
    from_bnft_id varchar(20) NOT NULL,
    to_policy_ver_id varchar(20) NOT NULL,
    to_bnft_id varchar(20) NOT NULL,
    rel_type_cd varchar(30) NOT NULL,
    trigger_pool_id varchar(20),
    rel_priority integer,
    PRIMARY KEY (card_id, from_policy_ver_id, from_bnft_id, to_policy_ver_id, to_bnft_id, rel_type_cd),
    CONSTRAINT card_bnft_rel_ck_1 CHECK (from_policy_ver_id <> to_policy_ver_id OR from_bnft_id <> to_bnft_id)
);

COMMENT ON TABLE db_pipeline.card_bnft_rel IS '한 상품의 동시 유효한 두 혜택 간 배타/우선/대체. BASE와 VARIANT SUPPLEMENT 사이도 가능';

COMMENT ON COLUMN db_pipeline.card_bnft_rel.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rel.from_policy_ver_id IS 'from_policy_ver_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rel.from_bnft_id IS 'from_bnft_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rel.to_policy_ver_id IS 'to_policy_ver_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rel.to_bnft_id IS 'to_bnft_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rel.rel_type_cd IS 'rel_type_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rel.trigger_pool_id IS 'trigger_pool_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rel.rel_priority IS 'rel_priority 업무 속성';

CREATE TABLE db_pipeline.card_method_catalog (
    method_kind_cd varchar(20) NOT NULL,
    method_cd varchar(40) NOT NULL,
    method_ver integer NOT NULL,
    param_schema jsonb NOT NULL,
    handler_key varchar(100) NOT NULL,
    method_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (method_kind_cd, method_cd, method_ver),
    CONSTRAINT card_method_catalog_ck_1 CHECK (method_ver > 0),
    CONSTRAINT card_method_catalog_ck_2 CHECK (jsonb_typeof(param_schema) = 'object')
);

COMMENT ON TABLE db_pipeline.card_method_catalog IS '상품/공통 양쪽 계산·술어 코드와 JSON 계약. 글로벌 독립 코드';

COMMENT ON COLUMN db_pipeline.card_method_catalog.method_kind_cd IS 'method_kind_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_method_catalog.method_cd IS 'method_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_method_catalog.method_ver IS 'method_ver 업무 속성';

COMMENT ON COLUMN db_pipeline.card_method_catalog.param_schema IS 'param_schema 업무 속성';

COMMENT ON COLUMN db_pipeline.card_method_catalog.handler_key IS 'handler_key 업무 속성';

COMMENT ON COLUMN db_pipeline.card_method_catalog.method_status_cd IS 'method_status_cd 업무 속성';

CREATE TABLE db_pipeline.card_common_bnft (
    common_bnft_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_bnft') NOT NULL,
    provider_cd varchar(30) NOT NULL,
    common_bnft_cd varchar(80) NOT NULL,
    common_bnft_nm text NOT NULL,
    PRIMARY KEY (common_bnft_id),
    UNIQUE (common_bnft_cd)
);

COMMENT ON TABLE db_pipeline.card_common_bnft IS '특정 카드에 종속되지 않는 공통 서비스 정체성. 동일 이름만으로 병합 금지';

COMMENT ON COLUMN db_pipeline.card_common_bnft.common_bnft_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_common_bnft.provider_cd IS 'provider_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_bnft.common_bnft_cd IS 'common_bnft_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_bnft.common_bnft_nm IS 'common_bnft_nm 업무 속성';

CREATE TABLE db_pipeline.card_common_policy_version (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_policy_version') NOT NULL,
    common_ver_no integer NOT NULL,
    valid_from date NOT NULL,
    valid_to_excl date,
    approved_at timestamptz,
    policy_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id),
    UNIQUE (common_bnft_id, common_ver_no),
    CONSTRAINT card_common_policy_version_ck_1 CHECK (common_ver_no > 0),
    CONSTRAINT card_common_policy_version_ck_2 CHECK (valid_to_excl IS NULL OR valid_to_excl > valid_from),
    CONSTRAINT card_common_policy_version_ck_3 CHECK (policy_status_cd IN ('DRAFT','APPROVED','RETIRED'))
);

COMMENT ON TABLE db_pipeline.card_common_policy_version IS '공통 서비스 정책 개정판; 카드 상품/문서 버전과 별개';

COMMENT ON COLUMN db_pipeline.card_common_policy_version.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_policy_version.common_ver_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_common_policy_version.common_ver_no IS 'common_ver_no 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_policy_version.valid_from IS 'valid_from 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_policy_version.valid_to_excl IS 'valid_to_excl 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_policy_version.approved_at IS 'approved_at 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_policy_version.policy_status_cd IS 'policy_status_cd 업무 속성';

CREATE TABLE db_pipeline.card_common_bnft_rule (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_rule_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_bnft_rule') NOT NULL,
    common_expr_id varchar(20),
    predicate_state_cd varchar(30) NOT NULL,
    calc_method_cd varchar(40) NOT NULL,
    method_ver integer NOT NULL,
    value_num numeric(18,4),
    value_unit_cd varchar(30),
    payout_unit_cd varchar(30) NOT NULL,
    basis_amt numeric(18,2),
    calc_params jsonb,
    rule_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_rule_id),
    CONSTRAINT card_common_bnft_rule_ck_1 CHECK (method_ver > 0),
    CONSTRAINT card_common_bnft_rule_ck_2 CHECK (value_num IS NULL OR value_num >= 0),
    CONSTRAINT card_common_bnft_rule_ck_3 CHECK (basis_amt IS NULL OR basis_amt >= 0),
    CONSTRAINT card_common_bnft_rule_ck_4 CHECK (calc_params IS NULL OR jsonb_typeof(calc_params) = 'object')
);

COMMENT ON TABLE db_pipeline.card_common_bnft_rule IS '공통 혜택 계산값의 단일 기준; 상품 로컬 규칙과 값 복제 금지';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.common_rule_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.common_expr_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.predicate_state_cd IS 'predicate_state_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.calc_method_cd IS 'calc_method_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.method_ver IS 'method_ver 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.value_num IS 'value_num 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.value_unit_cd IS 'value_unit_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.payout_unit_cd IS 'payout_unit_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.basis_amt IS 'basis_amt 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.calc_params IS 'calc_params 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.rule_status_cd IS 'rule_status_cd 업무 속성';

CREATE TABLE db_pipeline.card_common_cond (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_cond_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_cond') NOT NULL,
    cond_type_cd varchar(30) NOT NULL,
    cond_basis_cd varchar(30),
    cond_min_amt numeric(18,2),
    cond_max_amt_excl numeric(18,2),
    predicate_method_cd varchar(40),
    predicate_method_ver integer,
    cond_params jsonb,
    cond_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_cond_id),
    CONSTRAINT card_common_cond_ck_1 CHECK (cond_max_amt_excl IS NULL OR cond_min_amt IS NULL OR cond_max_amt_excl > cond_min_amt),
    CONSTRAINT card_common_cond_ck_2 CHECK (cond_params IS NULL OR jsonb_typeof(cond_params) = 'object')
);

COMMENT ON TABLE db_pipeline.card_common_cond IS '공통 서비스판의 원자 조건. 카드별 추가 조건과 구분';

COMMENT ON COLUMN db_pipeline.card_common_cond.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_cond.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_cond.common_cond_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_common_cond.cond_type_cd IS 'cond_type_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_cond.cond_basis_cd IS 'cond_basis_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_cond.cond_min_amt IS 'cond_min_amt 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_cond.cond_max_amt_excl IS 'cond_max_amt_excl 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_cond.predicate_method_cd IS 'predicate_method_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_cond.predicate_method_ver IS 'predicate_method_ver 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_cond.cond_params IS 'cond_params 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_cond.cond_status_cd IS 'cond_status_cd 업무 속성';

CREATE TABLE db_pipeline.card_common_cond_expr (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_expr_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_cond_expr') NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_expr_id)
);

COMMENT ON TABLE db_pipeline.card_common_cond_expr IS '공통 정책판의 DNF 조건식';

COMMENT ON COLUMN db_pipeline.card_common_cond_expr.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_cond_expr.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_cond_expr.common_expr_id IS '로컬 업무 ID';

CREATE TABLE db_pipeline.card_common_expr_atom (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_expr_id varchar(20) NOT NULL,
    branch_no integer NOT NULL,
    atom_seq integer NOT NULL,
    common_cond_id varchar(20) NOT NULL,
    negate_yn boolean NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_expr_id, branch_no, atom_seq),
    CONSTRAINT card_common_expr_atom_ck_1 CHECK (branch_no > 0),
    CONSTRAINT card_common_expr_atom_ck_2 CHECK (atom_seq > 0)
);

COMMENT ON TABLE db_pipeline.card_common_expr_atom IS '공통 조건식의 AND/OR/NOT atom';

COMMENT ON COLUMN db_pipeline.card_common_expr_atom.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_expr_atom.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_expr_atom.common_expr_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_expr_atom.branch_no IS 'branch_no 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_expr_atom.atom_seq IS 'atom_seq 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_expr_atom.common_cond_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_expr_atom.negate_yn IS 'negate_yn 업무 속성';

CREATE TABLE db_pipeline.card_common_target (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_target_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_target') NOT NULL,
    target_type_cd varchar(30) NOT NULL,
    target_key varchar(100) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_target_id)
);

COMMENT ON TABLE db_pipeline.card_common_target IS '공통 정책의 가맹점/업종/채널 대상';

COMMENT ON COLUMN db_pipeline.card_common_target.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_target.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_target.common_target_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_common_target.target_type_cd IS 'target_type_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_target.target_key IS 'target_key 업무 속성';

CREATE TABLE db_pipeline.card_common_rule_target (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_rule_id varchar(20) NOT NULL,
    common_target_id varchar(20) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_rule_id, common_target_id)
);

COMMENT ON TABLE db_pipeline.card_common_rule_target IS '공통 규칙↔공통 대상';

COMMENT ON COLUMN db_pipeline.card_common_rule_target.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_rule_target.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_rule_target.common_rule_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_rule_target.common_target_id IS '부모 키 상속 또는 관계 키';

CREATE TABLE db_pipeline.card_common_limit_pool (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_pool_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_limit_pool') NOT NULL,
    period_cd varchar(20) NOT NULL,
    cap_unit_cd varchar(30) NOT NULL,
    aggregation_key_cd varchar(30) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_pool_id)
);

COMMENT ON TABLE db_pipeline.card_common_limit_pool IS '공통 정책의 공유 한도; 상품 고유 한도와 분리';

COMMENT ON COLUMN db_pipeline.card_common_limit_pool.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_limit_pool.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_limit_pool.common_pool_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_common_limit_pool.period_cd IS 'period_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_limit_pool.cap_unit_cd IS 'cap_unit_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_limit_pool.aggregation_key_cd IS 'aggregation_key_cd 업무 속성';

CREATE TABLE db_pipeline.card_common_limit_tier (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_pool_id varchar(20) NOT NULL,
    common_tier_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_limit_tier') NOT NULL,
    common_expr_id varchar(20),
    predicate_state_cd varchar(30) NOT NULL,
    limit_num numeric(18,2) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_pool_id, common_tier_id),
    CONSTRAINT card_common_limit_tier_ck_1 CHECK (limit_num >= 0)
);

COMMENT ON TABLE db_pipeline.card_common_limit_tier IS '공통 풀의 조건별 한도 수치';

COMMENT ON COLUMN db_pipeline.card_common_limit_tier.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_limit_tier.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_limit_tier.common_pool_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_limit_tier.common_tier_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_common_limit_tier.common_expr_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_limit_tier.predicate_state_cd IS 'predicate_state_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_common_limit_tier.limit_num IS 'limit_num 업무 속성';

CREATE TABLE db_pipeline.card_common_rule_pool (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_rule_id varchar(20) NOT NULL,
    common_pool_id varchar(20) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_rule_id, common_pool_id)
);

COMMENT ON TABLE db_pipeline.card_common_rule_pool IS '공통 규칙↔공통 한도 풀';

COMMENT ON COLUMN db_pipeline.card_common_rule_pool.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_rule_pool.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_rule_pool.common_rule_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_rule_pool.common_pool_id IS '부모 키 상속 또는 관계 키';

CREATE TABLE db_pipeline.card_bnft_common (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    apply_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, common_bnft_id, common_ver_id)
);

COMMENT ON TABLE db_pipeline.card_bnft_common IS '상품 혜택 인스턴스↔승인된 공통 정책판 N:M. COMMON_LINK에서만 사용; 로컬 조건은 card_bnft_cond로 AND 추가';

COMMENT ON COLUMN db_pipeline.card_bnft_common.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_common.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_common.card_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_common.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_common.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_common.apply_status_cd IS 'apply_status_cd 업무 속성';

CREATE TABLE db_pipeline.card_doc (
    card_doc_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_doc'::text) NOT NULL,
    card_id bigint,
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
    CONSTRAINT card_doc_doc_status_check CHECK (((doc_status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'SUPERSEDED'::character varying, 'EXCLUDED'::character varying])::text[]))),
    CONSTRAINT card_doc_doc_type_cd_check CHECK (((doc_type_cd)::text = ANY ((ARRAY['PRODUCT_GUIDE'::character varying, 'TERMS'::character varying, 'BRAND_SERVICE'::character varying, 'ETC'::character varying])::text[]))),
    CONSTRAINT card_doc_doc_version_no_check CHECK ((doc_version_no > 0)),
    CONSTRAINT card_doc_family_cd_check CHECK (doc_family_cd IS NULL OR doc_family_cd ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]*$'),
    CONSTRAINT card_doc_pkey PRIMARY KEY (card_doc_id),
    CONSTRAINT card_doc_doc_cd_key UNIQUE (doc_cd),
    CONSTRAINT card_doc_doc_sha256_key UNIQUE (doc_sha256)
);

CREATE TABLE db_pipeline.card_product_doc (
    card_id bigint NOT NULL,
    card_doc_id varchar(20) NOT NULL,
    doc_role_cd varchar(20) NOT NULL,
    effective_from date,
    effective_to_excl date,
    approval_status_cd varchar(20) NOT NULL DEFAULT 'PENDING',
    applicability_basis_txt text NOT NULL,
    approval_note text,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT card_product_doc_pkey PRIMARY KEY (card_id, card_doc_id),
    CONSTRAINT card_product_doc_role_check CHECK
        (doc_role_cd IN ('PRODUCT_GUIDE','COMMON_TERMS','OTHER')),
    CONSTRAINT card_product_doc_approval_check CHECK
        (approval_status_cd IN ('PENDING','APPROVED','REJECTED')),
    CONSTRAINT card_product_doc_period_check CHECK
        (effective_to_excl IS NULL OR
         (effective_from IS NOT NULL AND effective_to_excl > effective_from)),
    CONSTRAINT card_product_doc_approved_check CHECK
        (approval_status_cd <> 'APPROVED' OR
         (effective_from IS NOT NULL AND length(trim(applicability_basis_txt)) > 0))
);

CREATE TABLE db_pipeline.card_product_variant_doc (
    card_id bigint NOT NULL,
    card_variant_id varchar(20) NOT NULL,
    card_doc_id varchar(20) NOT NULL,
    doc_role_cd varchar(20) NOT NULL DEFAULT 'BRAND_SERVICE',
    effective_from date,
    effective_to_excl date,
    approval_status_cd varchar(20) NOT NULL DEFAULT 'PENDING',
    applicability_basis_txt text NOT NULL,
    approval_note text,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT card_product_variant_doc_pkey
        PRIMARY KEY (card_id, card_variant_id, card_doc_id),
    CONSTRAINT card_product_variant_doc_role_check CHECK
        (doc_role_cd IN ('BRAND_SERVICE','PRODUCT_GUIDE','OTHER')),
    CONSTRAINT card_product_variant_doc_approval_check CHECK
        (approval_status_cd IN ('PENDING','APPROVED','REJECTED')),
    CONSTRAINT card_product_variant_doc_period_check CHECK
        (effective_to_excl IS NULL OR
         (effective_from IS NOT NULL AND effective_to_excl > effective_from)),
    CONSTRAINT card_product_variant_doc_approved_check CHECK
        (approval_status_cd <> 'APPROVED' OR
         (effective_from IS NOT NULL AND length(trim(applicability_basis_txt)) > 0))
);

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

CREATE TABLE db_pipeline.card_excl_item_als (
    card_excl_item_id character varying(20) NOT NULL,
    card_excl_item_als_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_excl_item_als'::text) NOT NULL,
    excl_item_als_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);

CREATE TABLE db_pipeline.card_source_evidence (
    evidence_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_source_evidence') NOT NULL,
    card_doc_id varchar(20) NOT NULL,
    page_no smallint NOT NULL,
    card_doc_chunk_id varchar(20) NOT NULL,
    card_extr_stg_id varchar(20),
    quote_txt text NOT NULL,
    start_pos integer,
    end_pos integer,
    approval_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (evidence_id),
    CONSTRAINT card_source_evidence_ck_1 CHECK (start_pos IS NULL OR start_pos > 0),
    CONSTRAINT card_source_evidence_ck_2 CHECK (end_pos IS NULL OR start_pos IS NULL OR end_pos >= start_pos)
);

COMMENT ON TABLE db_pipeline.card_source_evidence IS '승인된 문장/청크 근거. 독립 evidence_id; 문서키는 업무 PK로 전파되지 않음';

COMMENT ON COLUMN db_pipeline.card_source_evidence.evidence_id IS '로컬 업무 ID';

COMMENT ON COLUMN db_pipeline.card_source_evidence.card_doc_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_source_evidence.page_no IS 'page_no 업무 속성';

COMMENT ON COLUMN db_pipeline.card_source_evidence.card_doc_chunk_id IS 'card_doc_chunk_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_source_evidence.card_extr_stg_id IS 'card_extr_stg_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_source_evidence.quote_txt IS 'quote_txt 업무 속성';

COMMENT ON COLUMN db_pipeline.card_source_evidence.start_pos IS 'start_pos 업무 속성';

COMMENT ON COLUMN db_pipeline.card_source_evidence.end_pos IS 'end_pos 업무 속성';

COMMENT ON COLUMN db_pipeline.card_source_evidence.approval_status_cd IS 'approval_status_cd 업무 속성';

CREATE TABLE db_pipeline.card_bnft_rule_evidence (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    rule_id varchar(20) NOT NULL,
    evidence_id varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, rule_id, evidence_id)
);

COMMENT ON TABLE db_pipeline.card_bnft_rule_evidence IS '상품 규칙↔원문 근거 N:M; 한 규칙에 여러 PDF 근거 가능';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_evidence.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_evidence.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_evidence.card_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_evidence.rule_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rule_evidence.evidence_id IS '부모 키 상속 또는 관계 키';

CREATE TABLE db_pipeline.card_cond_evidence (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_cond_id varchar(20) NOT NULL,
    evidence_id varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_cond_id, evidence_id)
);

COMMENT ON TABLE db_pipeline.card_cond_evidence IS '상품 원자 조건↔원문 근거 N:M';

COMMENT ON COLUMN db_pipeline.card_cond_evidence.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_cond_evidence.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_cond_evidence.card_cond_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_cond_evidence.evidence_id IS '부모 키 상속 또는 관계 키';

CREATE TABLE db_pipeline.card_common_rule_evidence (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_rule_id varchar(20) NOT NULL,
    evidence_id varchar(20) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_rule_id, evidence_id)
);

COMMENT ON TABLE db_pipeline.card_common_rule_evidence IS '공통 규칙↔원문 근거 N:M';

COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.common_rule_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.evidence_id IS '부모 키 상속 또는 관계 키';

CREATE TABLE db_pipeline.card_common_cond_evidence (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_cond_id varchar(20) NOT NULL,
    evidence_id varchar(20) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_cond_id, evidence_id)
);

COMMENT ON TABLE db_pipeline.card_common_cond_evidence IS '공통 원자 조건↔원문 근거 N:M';

COMMENT ON COLUMN db_pipeline.card_common_cond_evidence.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_cond_evidence.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_cond_evidence.common_cond_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_cond_evidence.evidence_id IS '부모 키 상속 또는 관계 키';

CREATE TABLE db_pipeline.card_limit_pool_evidence (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    pool_id varchar(20) NOT NULL,
    evidence_id varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, pool_id, evidence_id)
);

COMMENT ON TABLE db_pipeline.card_limit_pool_evidence IS '상품 공유 한도와 승인 원문 근거';

COMMENT ON COLUMN db_pipeline.card_limit_pool_evidence.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_limit_pool_evidence.policy_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_limit_pool_evidence.pool_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_limit_pool_evidence.evidence_id IS '부모 키 상속 또는 관계 키';

CREATE TABLE db_pipeline.card_bnft_rel_evidence (
    card_id bigint NOT NULL,
    from_policy_ver_id varchar(20) NOT NULL,
    from_bnft_id varchar(20) NOT NULL,
    to_policy_ver_id varchar(20) NOT NULL,
    to_bnft_id varchar(20) NOT NULL,
    rel_type_cd varchar(30) NOT NULL,
    evidence_id varchar(20) NOT NULL,
    PRIMARY KEY (card_id, from_policy_ver_id, from_bnft_id, to_policy_ver_id, to_bnft_id, rel_type_cd, evidence_id)
);

COMMENT ON TABLE db_pipeline.card_bnft_rel_evidence IS '상품 혜택 간 우선 및 대체 관계와 승인 원문 근거';

COMMENT ON COLUMN db_pipeline.card_bnft_rel_evidence.card_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_bnft_rel_evidence.from_policy_ver_id IS 'from_policy_ver_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rel_evidence.from_bnft_id IS 'from_bnft_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rel_evidence.to_policy_ver_id IS 'to_policy_ver_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rel_evidence.to_bnft_id IS 'to_bnft_id 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rel_evidence.rel_type_cd IS 'rel_type_cd 업무 속성';

COMMENT ON COLUMN db_pipeline.card_bnft_rel_evidence.evidence_id IS '부모 키 상속 또는 관계 키';

CREATE TABLE db_pipeline.card_common_limit_pool_evidence (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_pool_id varchar(20) NOT NULL,
    evidence_id varchar(20) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id, common_pool_id, evidence_id)
);

COMMENT ON TABLE db_pipeline.card_common_limit_pool_evidence IS '공통 정책 공유 한도와 승인 원문 근거';

COMMENT ON COLUMN db_pipeline.card_common_limit_pool_evidence.common_bnft_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_limit_pool_evidence.common_ver_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_limit_pool_evidence.common_pool_id IS '부모 키 상속 또는 관계 키';

COMMENT ON COLUMN db_pipeline.card_common_limit_pool_evidence.evidence_id IS '부모 키 상속 또는 관계 키';

COMMENT ON TABLE db_pipeline.card_ai_call IS 'AI 실행 내 청크별 호출 원 응답(정제 전 AI 출력)';

COMMENT ON COLUMN db_pipeline.card_ai_call.card_ai_run_id IS 'AI 실행 ID';

COMMENT ON COLUMN db_pipeline.card_ai_call.card_doc_id IS '원본 문서 ID(card_doc_chunk 부모 PK 승계)';

COMMENT ON COLUMN db_pipeline.card_ai_call.page_no IS '청크가 속한 PDF 페이지 번호(card_doc_chunk 부모 PK 승계)';

COMMENT ON COLUMN db_pipeline.card_ai_call.card_doc_chunk_id IS '입력 청크 ID';

COMMENT ON COLUMN db_pipeline.card_ai_call.call_seq IS '같은 실행·청크 내 호출 순번(재시도 시 증가)';

COMMENT ON COLUMN db_pipeline.card_ai_call.call_input_sha256 IS '실제 입력(프롬프트+청크) SHA-256';

COMMENT ON COLUMN db_pipeline.card_ai_call.call_status IS '호출 상태(SUCCEEDED, FAILED: 호출 실패, PARSE_ERROR: JSON 파싱 실패)';

COMMENT ON COLUMN db_pipeline.card_ai_call.call_resp_raw IS '모델 응답 원문';

COMMENT ON COLUMN db_pipeline.card_ai_call.call_resp_json IS '파싱한 응답 JSON';

COMMENT ON COLUMN db_pipeline.card_ai_call.call_error_msg IS '오류 메시지';

COMMENT ON COLUMN db_pipeline.card_ai_call.call_input_token_cnt IS '입력 토큰 수';

COMMENT ON COLUMN db_pipeline.card_ai_call.call_output_token_cnt IS '출력 토큰 수';

COMMENT ON COLUMN db_pipeline.card_ai_call.call_latency_ms IS '응답 시간(밀리초)';

COMMENT ON COLUMN db_pipeline.card_ai_call.call_req_date IS '요청 일시';

COMMENT ON COLUMN db_pipeline.card_ai_call.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_ai_call.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_ai_call.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_ai_call.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE db_pipeline.card_ai_run IS 'AI 추출·검증 실행 이력(실행 회차 단위)';

COMMENT ON COLUMN db_pipeline.card_ai_run.card_ai_run_id IS 'AI 실행 ID';

COMMENT ON COLUMN db_pipeline.card_ai_run.run_stage_cd IS '실행 단계(EXTRACT: 혜택·조건 추출, VERIFY: 추출 결과 의미 검증)';

COMMENT ON COLUMN db_pipeline.card_ai_run.run_call_mthd_cd IS 'AI 호출 방식(PYTHON_RELAY, PGAI, EDGE_FUNCTION, ETC). 기술 검증 후 확정';

COMMENT ON COLUMN db_pipeline.card_ai_run.run_model_nm IS '사용 모델명';

COMMENT ON COLUMN db_pipeline.card_ai_run.run_prompt_ver IS '프롬프트 버전';

COMMENT ON COLUMN db_pipeline.card_ai_run.run_prompt_txt IS '실행에 사용한 프롬프트 템플릿 원문';

COMMENT ON COLUMN db_pipeline.card_ai_run.run_param IS '모델 호출 파라미터(temperature, 출력 스키마 등)';

COMMENT ON COLUMN db_pipeline.card_ai_run.run_target_card_doc_id IS '대상 원본 문서 ID(여러 문서 실행이면 NULL)';

COMMENT ON COLUMN db_pipeline.card_ai_run.run_status IS '실행 상태(RUNNING, SUCCEEDED, PARTIAL: 일부 호출 실패, FAILED)';

COMMENT ON COLUMN db_pipeline.card_ai_run.run_start_date IS '실행 시작 일시';

COMMENT ON COLUMN db_pipeline.card_ai_run.run_end_date IS '실행 종료 일시';

COMMENT ON COLUMN db_pipeline.card_ai_run.run_note IS '실행 메모';

COMMENT ON COLUMN db_pipeline.card_ai_run.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_ai_run.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_ai_run.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_ai_run.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE db_pipeline.card_doc IS '원천 PDF 파일/문서판. 상품 적용은 card_product_doc 또는 card_product_variant_doc에서 관리';

COMMENT ON COLUMN db_pipeline.card_doc.card_doc_id IS '원본 문서 ID';

COMMENT ON COLUMN db_pipeline.card_doc.card_id IS '기존 파이프라인의 단일 상품 힌트. 신규 문서에서는 NULL; 적용 기준은 상품-문서 관계 테이블';

COMMENT ON COLUMN db_pipeline.card_doc.doc_cd IS '파이프라인 공통 문서 코드(예: HANA_15650_20260429). 결과 A·B 비교 키 후보';

COMMENT ON COLUMN db_pipeline.card_doc.doc_type_cd IS '문서 유형(PRODUCT_GUIDE, TERMS, BRAND_SERVICE, ETC)';

COMMENT ON COLUMN db_pipeline.card_doc.doc_family_cd IS '개정판을 묶는 문서 계열 코드. 동일 계열의 각 판은 별도 card_doc_id';

COMMENT ON COLUMN db_pipeline.card_doc.doc_title IS '문서 제목';

COMMENT ON COLUMN db_pipeline.card_doc.doc_source_url IS '공식 출처 URL';

COMMENT ON COLUMN db_pipeline.card_doc.doc_file_nm IS '수집 파일명';

COMMENT ON COLUMN db_pipeline.card_doc.doc_file_size IS '수집 파일 크기(바이트)';

COMMENT ON COLUMN db_pipeline.card_doc.doc_sha256 IS '수집 파일 SHA-256(소문자 16진수 64자)';

COMMENT ON COLUMN db_pipeline.card_doc.doc_page_cnt IS 'PDF 페이지 수';

COMMENT ON COLUMN db_pipeline.card_doc.doc_review_no IS '준법심의·여신협회 심의필 번호 원문';

COMMENT ON COLUMN db_pipeline.card_doc.doc_review_date IS '심의일';

COMMENT ON COLUMN db_pipeline.card_doc.doc_release_date IS '기존 상품 출시일 기록; 공통 문서는 확인된 문서 발행일만 기재. 관계 적용 시작일과 구별';

COMMENT ON COLUMN db_pipeline.card_doc.doc_collect_date IS '파일 수집(다운로드) 일시';

COMMENT ON COLUMN db_pipeline.card_doc.doc_version_no IS '문서판 번호(1부터). 상품별 적용 기간은 관계 테이블에서 관리';

COMMENT ON COLUMN db_pipeline.card_doc.doc_status IS '원천 문서 상태(ACTIVE, SUPERSEDED, EXCLUDED). 상품별 현재 적용 여부는 승인된 문서 관계의 기간으로 판정';

COMMENT ON COLUMN db_pipeline.card_doc.doc_note IS '문서 범위·확인 사항 메모';

COMMENT ON COLUMN db_pipeline.card_doc.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_doc.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_doc.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_doc.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE db_pipeline.card_doc_chunk IS '문서 청크(조항·표·안내 단위) 원문과 SQL 정제 결과';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.card_doc_id IS '원본 문서 ID';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.page_no IS '청크가 속한 페이지 번호(청크는 페이지를 넘지 않음)';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.card_doc_chunk_id IS '청크 ID';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_seq IS '문서 내 청크 순번(1부터)';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_section_nm IS '원문 절 제목(예: [실적 산정 기준], 서비스 제외 대상)';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_type_cd IS '청크 유형(BODY, TABLE, NOTICE: 유의사항, HEADER_FOOTER: 머리말·꼬리말, ETC)';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_start_pos IS 'page_raw_txt 내 시작 문자 위치(1부터, PostgreSQL substr 기준)';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_end_pos IS 'page_raw_txt 내 끝 문자 위치(포함)';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_raw_txt IS '청크 원문(정제 전, page_raw_txt의 부분 문자열)';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_clean_txt IS 'SQL 정제 후 텍스트(AI 입력)';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_status IS '청크 상태(RAW: 분리만 됨, CLEANED: 정제 완료, EXCLUDED: 추출 대상 제외)';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_split_rule_ver IS '청크 분리 규칙 버전';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_clean_rule_ver IS 'SQL 정제 규칙 버전';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_doc_chunk.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE db_pipeline.card_doc_page IS '문서 페이지별 추출 원문(정제 전, 적재 후 변경 금지)';

COMMENT ON COLUMN db_pipeline.card_doc_page.card_doc_id IS '원본 문서 ID';

COMMENT ON COLUMN db_pipeline.card_doc_page.page_no IS 'PDF 페이지 번호(1부터)';

COMMENT ON COLUMN db_pipeline.card_doc_page.page_raw_txt IS '추출기가 반환한 페이지 텍스트 원문(가공 없음)';

COMMENT ON COLUMN db_pipeline.card_doc_page.page_char_cnt IS '페이지 원문 문자 수';

COMMENT ON COLUMN db_pipeline.card_doc_page.page_txt_sha256 IS '페이지 원문 SHA-256(재추출 시 변경 감지)';

COMMENT ON COLUMN db_pipeline.card_doc_page.page_layer_cd IS '텍스트 레이어 유형(TEXT, IMAGE, MIXED: 일부 표가 이미지, UNKNOWN)';

COMMENT ON COLUMN db_pipeline.card_doc_page.page_extractor_nm IS '텍스트 추출기명(예: PyMuPDF)';

COMMENT ON COLUMN db_pipeline.card_doc_page.page_extractor_ver IS '텍스트 추출기 버전';

COMMENT ON COLUMN db_pipeline.card_doc_page.page_note IS '추출 한계·확인 메모(표 미탐지 등)';

COMMENT ON COLUMN db_pipeline.card_doc_page.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_doc_page.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_doc_page.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_doc_page.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE db_pipeline.card_excl_item IS '표준 제외 항목(카드사 범위 개념, 정책 아님)';

COMMENT ON COLUMN db_pipeline.card_excl_item.card_excl_item_id IS '표준 제외 항목 ID';

COMMENT ON COLUMN db_pipeline.card_excl_item.issuer IS '카드사(card_product.issuer와 같은 표기). 병합은 같은 카드사 안에서만';

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_nm IS '표준 제외 항목명(예: 상품권·기프트카드 구매)';

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_concept_cd IS '카드사 공통 분류 개념 코드(예: GIFT_CERT_PURCHASE). 분류용이며 정책 동일을 뜻하지 않음';

COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_desc IS '항목 설명·포함 범위';

COMMENT ON COLUMN db_pipeline.card_excl_item.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_excl_item.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_excl_item.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_excl_item.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE db_pipeline.card_excl_item_als IS '제외 항목 원문 표기 별칭(SQL 정규화 사전)';

COMMENT ON COLUMN db_pipeline.card_excl_item_als.card_excl_item_id IS '표준 제외 항목 ID';

COMMENT ON COLUMN db_pipeline.card_excl_item_als.card_excl_item_als_id IS '제외 항목 별칭 ID';

COMMENT ON COLUMN db_pipeline.card_excl_item_als.excl_item_als_nm IS '원문 표기(공백 제거 비교 기준). 의미가 불확실한 표기(예: 상품/)는 등록하지 않음';

COMMENT ON COLUMN db_pipeline.card_excl_item_als.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_excl_item_als.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_excl_item_als.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_excl_item_als.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE db_pipeline.card_extr_stg IS 'AI 추출 혜택·조건 staging(정제 전 원 항목, 정제 후 값, 검증·승인 상태)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_ai_run_id IS 'AI 추출 실행 ID';

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_doc_id IS '원본 문서 ID(card_ai_call 부모 PK 승계)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.page_no IS 'PDF 페이지 번호(card_ai_call 부모 PK 승계)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_doc_chunk_id IS '근거 청크 ID';

COMMENT ON COLUMN db_pipeline.card_extr_stg.call_seq IS '응답을 만든 호출 순번(card_ai_call)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_extr_stg_id IS '추출 staging ID';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_item_seq IS '응답 내 항목 순번(1부터)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_id IS '추출 실행의 대상 상품 ID. 공유 문서는 상품 연결 범위를 별도 검증';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_kind_cd IS '항목 종류(BENEFIT: 혜택, CONDITION: 조건)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_parent_card_extr_stg_id IS '조건이 걸린 혜택의 staging ID(카드 전체 조건이면 NULL)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_raw_item IS 'AI가 추출한 개별 혜택 또는 조건의 원본 JSON';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_normalized_item IS 'AI 추출 원본을 정제 및 표준화한 JSON';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_txt IS 'AI가 제시한 근거 원문 문장';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_start_pos IS '근거 청크 원문 내 시작 문자 위치(1부터)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_end_pos IS '근거 청크 원문 내 종료 문자 위치(포함)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.card_excl_item_id IS '매핑된 표준 제외 항목 ID(미매핑 NULL)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_sql_check_cd IS '정제 JSON, 원문 근거, 참조 관계 등을 검증한 SQL 검증 결과';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_ai_vrfy_cd IS 'AI 의미 검증 결과(NULL: 미실행, MATCH, MISMATCH, UNCERTAIN)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_ai_vrfy_card_ai_run_id IS 'AI 의미 검증 실행 ID';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_status IS '검토 상태(PENDING_REVIEW, AUTO_APPROVED, MANUAL_APPROVED, REJECTED)';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_review_note IS '검증 결과 및 검토 메모';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_approved_date IS '승인 일시';

COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_approved_user_id IS '승인 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_extr_stg.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_extr_stg.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_extr_stg.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_extr_stg.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE db_pipeline.card_product IS '카드 상품 마스터. 상품 PK는 발급형 및 문서 관계의 부모';

COMMENT ON COLUMN db_pipeline.card_product.card_id IS 'bigint 상품 ID. 기존 card_id 타입과 일치; seq_card_product.nextval 발급';

COMMENT ON COLUMN db_pipeline.card_product.product_cd IS '문서 파일명과 독립된 상품 업무 코드';

COMMENT ON COLUMN db_pipeline.card_product.product_nm IS '카드 상품명';

COMMENT ON COLUMN db_pipeline.card_product.issuer IS '발급 카드사; 제외 항목 issuer와 논리적 범위 일치';

COMMENT ON COLUMN db_pipeline.card_product.card_kind_cd IS 'CREDIT 또는 DEBIT';

COMMENT ON COLUMN db_pipeline.card_product.product_status_cd IS '상품 출시/중단 상태';

COMMENT ON COLUMN db_pipeline.card_product.launched_on IS '상품 출시일(확인된 경우)';

COMMENT ON COLUMN db_pipeline.card_product.discontinued_on IS '상품 중단일(확인된 경우)';

COMMENT ON COLUMN db_pipeline.card_product.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_product.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_product.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_product.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE db_pipeline.card_product_variant IS '상품 발급형. 복합 PK가 부모 card_product.card_id를 상속';

COMMENT ON COLUMN db_pipeline.card_product_variant.card_id IS '부모 상품 ID; 별도 발급 없음';

COMMENT ON COLUMN db_pipeline.card_product_variant.card_variant_id IS 'fn_get_biz_id와 seq_card_product_variant로 발급';

COMMENT ON COLUMN db_pipeline.card_product_variant.variant_cd IS '상품 안의 발급형 업무 코드';

COMMENT ON COLUMN db_pipeline.card_product_variant.variant_nm IS '발급형 표시명';

COMMENT ON COLUMN db_pipeline.card_product_variant.brand_cd IS '국제 브랜드 코드';

COMMENT ON COLUMN db_pipeline.card_product_variant.service_grade_cd IS '브랜드 서비스 등급';

COMMENT ON COLUMN db_pipeline.card_product_variant.service_type_cd IS '선택서비스 유형(예: PLATINUM_01/04, VP001)';

COMMENT ON COLUMN db_pipeline.card_product_variant.variant_status_cd IS '발급형 출시/중단 상태';

COMMENT ON COLUMN db_pipeline.card_product_variant.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_product_variant.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_product_variant.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_product_variant.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE db_pipeline.card_product_doc IS '상품 전체↔문서판 N:M. PK는 상품/문서 양 부모 키';

COMMENT ON COLUMN db_pipeline.card_product_doc.card_id IS '부모 상품 ID';

COMMENT ON COLUMN db_pipeline.card_product_doc.card_doc_id IS '부모 원천 문서판 ID';

COMMENT ON COLUMN db_pipeline.card_product_doc.doc_role_cd IS '상품 전체에 적용되는 문서 역할';

COMMENT ON COLUMN db_pipeline.card_product_doc.effective_from IS '상품에 문서판 적용 시작일(포함)';

COMMENT ON COLUMN db_pipeline.card_product_doc.effective_to_excl IS '상품에 문서판 적용 종료일(미포함)';

COMMENT ON COLUMN db_pipeline.card_product_doc.approval_status_cd IS '관계 검증/승인 상태';

COMMENT ON COLUMN db_pipeline.card_product_doc.applicability_basis_txt IS '상품에 이 문서가 적용된다는 원문/출처 근거';

COMMENT ON COLUMN db_pipeline.card_product_doc.approval_note IS '승인·검토 메모';

COMMENT ON COLUMN db_pipeline.card_product_doc.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_product_doc.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_product_doc.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_product_doc.update_user_id IS '수정 사용자 ID';

COMMENT ON TABLE db_pipeline.card_product_variant_doc IS '발급형↔문서판 N:M. PK가 상품·발급형 부모 키 및 문서 키를 상속';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.card_id IS '부모 상품 ID';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.card_variant_id IS '부모 발급형 ID; 다시 발급하지 않음';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.card_doc_id IS '부모 원천 문서판 ID';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.doc_role_cd IS '발급형에 적용되는 문서 역할';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.effective_from IS '발급형에 문서판 적용 시작일(포함)';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.effective_to_excl IS '발급형에 문서판 적용 종료일(미포함)';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.approval_status_cd IS '관계 검증/승인 상태';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.applicability_basis_txt IS '발급형별 적용 원문/출처 근거';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.approval_note IS '승인·검토 메모';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.create_date IS '생성 일시';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.create_user_id IS '생성 사용자 ID';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.update_date IS '수정 일시';

COMMENT ON COLUMN db_pipeline.card_product_variant_doc.update_user_id IS '수정 사용자 ID';

ALTER TABLE ONLY db_pipeline.card_ai_call
    ADD CONSTRAINT card_ai_call_pkey PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq);

ALTER TABLE ONLY db_pipeline.card_ai_run
    ADD CONSTRAINT card_ai_run_pkey PRIMARY KEY (card_ai_run_id);

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_card_doc_chunk_id_key UNIQUE (card_doc_chunk_id);

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_card_doc_id_chunk_seq_key UNIQUE (card_doc_id, chunk_seq);

ALTER TABLE ONLY db_pipeline.card_doc_chunk
    ADD CONSTRAINT card_doc_chunk_pkey PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id);

ALTER TABLE ONLY db_pipeline.card_doc_page
    ADD CONSTRAINT card_doc_page_pkey PRIMARY KEY (card_doc_id, page_no);

ALTER TABLE ONLY db_pipeline.card_excl_item_als
    ADD CONSTRAINT card_excl_item_als_card_excl_item_id_excl_item_als_nm_key UNIQUE (card_excl_item_id, excl_item_als_nm);

ALTER TABLE ONLY db_pipeline.card_excl_item_als
    ADD CONSTRAINT card_excl_item_als_pkey PRIMARY KEY (card_excl_item_id, card_excl_item_als_id);

ALTER TABLE ONLY db_pipeline.card_excl_item
    ADD CONSTRAINT card_excl_item_issuer_excl_item_nm_key UNIQUE (issuer, excl_item_nm);

ALTER TABLE ONLY db_pipeline.card_excl_item
    ADD CONSTRAINT card_excl_item_pkey PRIMARY KEY (card_excl_item_id);

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_card_ai_run_id_card_doc_id_page_no_card_doc_c_key UNIQUE (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, stg_item_seq);

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_card_extr_stg_id_key UNIQUE (card_extr_stg_id);

ALTER TABLE ONLY db_pipeline.card_extr_stg
    ADD CONSTRAINT card_extr_stg_pkey PRIMARY KEY (card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id);

CREATE INDEX ix_card_ai_call_chunk_key ON db_pipeline.card_ai_call USING btree (card_doc_chunk_id);

CREATE INDEX ix_card_ai_call_doc_chunk_key ON db_pipeline.card_ai_call USING btree (card_doc_id, page_no, card_doc_chunk_id);

CREATE INDEX ix_card_ai_run_doc_key ON db_pipeline.card_ai_run USING btree (run_target_card_doc_id);

CREATE INDEX ix_card_excl_item_concept_key ON db_pipeline.card_excl_item USING btree (excl_concept_cd);

CREATE INDEX ix_card_extr_stg_chunk_key ON db_pipeline.card_extr_stg USING btree (card_doc_chunk_id);

CREATE INDEX ix_card_extr_stg_excl_item_key ON db_pipeline.card_extr_stg USING btree (card_excl_item_id);

CREATE INDEX ix_card_extr_stg_status_key ON db_pipeline.card_extr_stg USING btree (stg_status, stg_kind_cd);

CREATE INDEX card_doc_family_version_idx
    ON db_pipeline.card_doc (doc_family_cd, doc_version_no, doc_release_date);

CREATE INDEX card_product_kind_status_idx ON db_pipeline.card_product (card_kind_cd, product_status_cd);

CREATE INDEX card_product_variant_service_idx
    ON db_pipeline.card_product_variant (brand_cd, service_grade_cd, service_type_cd);

CREATE INDEX card_product_doc_doc_idx ON db_pipeline.card_product_doc (card_doc_id, card_id);

CREATE INDEX card_product_doc_current_idx
    ON db_pipeline.card_product_doc (card_id, effective_from, effective_to_excl)
    WHERE approval_status_cd = 'APPROVED';

CREATE INDEX card_product_variant_doc_doc_idx
    ON db_pipeline.card_product_variant_doc (card_doc_id, card_id, card_variant_id);

CREATE INDEX card_product_variant_doc_current_idx
    ON db_pipeline.card_product_variant_doc
       (card_id, card_variant_id, effective_from, effective_to_excl)
    WHERE approval_status_cd = 'APPROVED';

COMMENT ON SEQUENCE db_pipeline.seq_card_ai_run IS 'AI 실행 ID 발급';

COMMENT ON SEQUENCE db_pipeline.seq_card_bnft IS '확정 혜택 ID 발급';

COMMENT ON SEQUENCE db_pipeline.seq_card_cond IS '확정 조건 ID 발급';

COMMENT ON SEQUENCE db_pipeline.seq_card_doc IS '원본 문서 ID 발급';

COMMENT ON SEQUENCE db_pipeline.seq_card_doc_chunk IS '문서 청크 ID 발급';

COMMENT ON SEQUENCE db_pipeline.seq_card_excl_item IS '표준 제외 항목 ID 발급';

COMMENT ON SEQUENCE db_pipeline.seq_card_excl_item_als IS '제외 항목 별칭 ID 발급';

COMMENT ON SEQUENCE db_pipeline.seq_card_extr_stg IS 'AI 추출 staging ID 발급';

COMMENT ON SEQUENCE db_pipeline.seq_card_product IS 'card_product.card_id bigint 발급; 원본 백업에는 상품 마스터 시퀀스가 없음';

COMMENT ON SEQUENCE db_pipeline.seq_card_product_variant IS '발급형 varchar(20) 업무 ID; 기존 fn_get_biz_id 및 6자리 순환 규칙 적용';

CREATE INDEX ix_card_policy_version_lookup ON db_pipeline.card_policy_version (card_id, policy_status_cd, valid_from, valid_to_excl);

CREATE INDEX ix_card_bnft_cond_lookup ON db_pipeline.card_bnft_cond (card_id, policy_ver_id, card_cond_id);

CREATE INDEX ix_card_bnft_rule_target_lookup ON db_pipeline.card_bnft_rule_target (card_id, policy_ver_id, card_bnft_id, target_id);

CREATE INDEX ix_card_bnft_rule_pool_lookup ON db_pipeline.card_bnft_rule_pool (card_id, policy_ver_id, pool_id);

CREATE INDEX ix_card_bnft_common_lookup ON db_pipeline.card_bnft_common (common_bnft_id, common_ver_id);

CREATE INDEX ix_card_bnft_rel_lookup ON db_pipeline.card_bnft_rel (card_id, to_policy_ver_id, to_bnft_id);

CREATE INDEX ix_card_source_evidence_lookup ON db_pipeline.card_source_evidence (card_doc_id, page_no, card_doc_chunk_id);

CREATE INDEX ix_card_common_policy_version_lookup ON db_pipeline.card_common_policy_version (common_bnft_id, policy_status_cd, valid_from, valid_to_excl);

-- Approved BASE policy overlap (must return 0 rows before approval):
-- SELECT a.card_id,a.policy_ver_id,b.policy_ver_id
-- FROM db_pipeline.card_policy_version a JOIN db_pipeline.card_policy_version b
-- ON a.card_id=b.card_id AND a.policy_ver_id<b.policy_ver_id
-- AND a.policy_status_cd='APPROVED' AND b.policy_status_cd='APPROVED'
-- AND a.policy_effect_cd='BASE' AND b.policy_effect_cd='BASE'
-- AND a.valid_from<coalesce(b.valid_to_excl,'infinity'::date)
-- AND b.valid_from<coalesce(a.valid_to_excl,'infinity'::date);
-- Because physical FKs are intentionally absent, run logical orphan checks before approval.

