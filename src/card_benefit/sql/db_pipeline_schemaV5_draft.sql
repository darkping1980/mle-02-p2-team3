-- V5 draft integrated creation for an EMPTY db_pipeline schema.
-- No DROP and no physical foreign keys. Apply only after target/row/dependency checks.
-- This file does not replace V4 until the design review is finished.
-- Product policy is the parent of confirmed benefits; source documents remain evidence.
-- V5 keeps PK inheritance and folds dependent detail into JSONB validated by CHECK functions.
--
-- JSONB contracts (validated by fn_valid_*):
--   cond_expr       {"expr_status_cd", "branches":[{"branch_no","atoms":[{"atom_seq","atom_key",
--                    "negate_yn","cond_type_cd","cond_basis_cd","cond_min_amt","cond_max_amt_excl",
--                    "predicate_method_cd","predicate_method_ver","cond_params","card_excl_item_id",
--                    "excl_raw_txt","cond_raw_txt","link_role_cd","cond_status_cd"}]}]}
--                    branches = OR, atoms in a branch = AND, negate_yn = NOT, [min,max) spend range.
--   target_list     [{"target_type_cd","target_key","target_nm"}]
--   tier_list       [{"tier_key","tier_priority","predicate_state_cd","limit_num","cond_expr"}]
--   limit_list      [{"limit_key","pool_key","period_cd","cap_unit_cd","aggregation_key_cd",
--                     "predicate_state_cd","limit_num","cond_expr"}]
--   brand_opt_list  [{"brand_opt_cd","brand_opt_nm","brand_cd","service_grade_cd","service_type_cd",
--                     "brand_opt_status_cd"}]
-- Effective condition: policy_cond_expr AND bnft_cond_expr AND rule cond_expr (LOCAL or COMMON).


CREATE SCHEMA db_pipeline;

COMMENT ON SCHEMA db_pipeline IS '카드 상품 중심 V5 확정 혜택 및 원천 추적 스키마(초안)';

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

-- ---------------------------------------------------------------------------
-- JSONB 계약 검증 함수 (테이블 CHECK와 생성 컬럼에서 사용. 모두 IMMUTABLE)
-- ---------------------------------------------------------------------------
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
       OR coalesce(p_expr->>'expr_status_cd', '') NOT IN ('DRAFT','CONFIRMED','RETIRED')
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
               OR coalesce(v_type, '') NOT IN
                  ('SPEND_REQ','SPEND_EXCL','BNFT_EXCL','USAGE_REQ','PAYMENT_METHOD','MERCHANT_RULE','GRACE','ETC')
               OR coalesce(v_atom->>'cond_status_cd', '') NOT IN ('DRAFT','CONFIRMED','RETIRED') THEN
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

COMMENT ON FUNCTION db_pipeline.fn_valid_cond_expr(jsonb) IS '조건식 JSONB 계약 검증. branch 사이 OR, branch 안 atom AND, negate_yn=NOT';

CREATE FUNCTION db_pipeline.fn_cond_spend_bound(p_expr jsonb, p_bound text) RETURNS numeric
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
    SELECT CASE WHEN count(*) = 1 THEN max((a.value->>p_bound)::numeric) END
    FROM jsonb_array_elements(p_expr->'branches') AS b(value)
    CROSS JOIN LATERAL jsonb_array_elements(b.value->'atoms') AS a(value)
    WHERE jsonb_array_length(p_expr->'branches') = 1
      AND a.value->>'cond_type_cd' = 'SPEND_REQ'
      AND a.value->>'cond_basis_cd' = 'PREV_MONTH_SPEND'
      AND (a.value->>'negate_yn')::boolean = false
$_$;

COMMENT ON FUNCTION db_pipeline.fn_cond_spend_bound(jsonb, text) IS '단일 branch의 전월 실적 구간 값 추출. OR식이나 구간 atom이 둘 이상이면 NULL을 반환하고 v_card_cond_atom으로 조회';

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

COMMENT ON FUNCTION db_pipeline.fn_valid_target_list(jsonb) IS '대상 목록 JSONB 계약 검증. 비율·금액 키는 두지 않으며 대상별 비율이 다르면 규칙 행을 나눔';

CREATE FUNCTION db_pipeline.fn_valid_tier_list(p_list jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
    SELECT CASE
        WHEN jsonb_typeof(p_list) IS DISTINCT FROM 'array' OR jsonb_array_length(p_list) = 0 THEN false
        ELSE (
            SELECT bool_and(
                       jsonb_typeof(t.value) = 'object'
                       AND coalesce(t.value->>'tier_key', '') ~ '^[A-Za-z0-9_.:-]{1,40}$'
                       AND jsonb_typeof(t.value->'limit_num') IS NOT DISTINCT FROM 'number'
                       AND (t.value->>'limit_num')::numeric >= 0
                       AND jsonb_typeof(t.value->'tier_priority') IS DISTINCT FROM 'string'
                       AND coalesce((t.value->>'tier_priority')::integer, 1) > 0
                       AND CASE t.value->>'predicate_state_cd'
                               WHEN 'CONDITIONAL' THEN t.value->'cond_expr' IS NOT NULL
                                                       AND db_pipeline.fn_valid_cond_expr(t.value->'cond_expr')
                               WHEN 'VERIFIED_UNCONDITIONAL' THEN t.value->'cond_expr' IS NULL
                               WHEN 'PENDING_REVIEW' THEN db_pipeline.fn_valid_cond_expr(t.value->'cond_expr')
                               ELSE false
                           END)
                   AND count(*) = count(DISTINCT t.value->>'tier_key')
            FROM jsonb_array_elements(p_list) AS t(value))
    END
$_$;

COMMENT ON FUNCTION db_pipeline.fn_valid_tier_list(jsonb) IS '한도 풀 tier 목록 검증. limit_num은 0 이상의 숫자, 상태별 cond_expr 필수 여부 검사';

CREATE FUNCTION db_pipeline.fn_valid_limit_list(p_list jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
    SELECT CASE
        WHEN jsonb_typeof(p_list) IS DISTINCT FROM 'array' THEN false
        ELSE coalesce((
            SELECT bool_and(
                       jsonb_typeof(t.value) = 'object'
                       AND coalesce(t.value->>'limit_key', '') ~ '^[A-Za-z0-9_.:-]{1,40}$'
                       AND coalesce(t.value->>'period_cd', '') <> ''
                       AND coalesce(t.value->>'cap_unit_cd', '') <> ''
                       AND coalesce(t.value->>'aggregation_key_cd', '') <> ''
                       AND jsonb_typeof(t.value->'limit_num') IS NOT DISTINCT FROM 'number'
                       AND (t.value->>'limit_num')::numeric >= 0
                       AND coalesce(jsonb_typeof(t.value->'pool_key'), 'null') IN ('string','null')
                       AND CASE t.value->>'predicate_state_cd'
                               WHEN 'CONDITIONAL' THEN t.value->'cond_expr' IS NOT NULL
                                                       AND db_pipeline.fn_valid_cond_expr(t.value->'cond_expr')
                               WHEN 'VERIFIED_UNCONDITIONAL' THEN t.value->'cond_expr' IS NULL
                               WHEN 'PENDING_REVIEW' THEN db_pipeline.fn_valid_cond_expr(t.value->'cond_expr')
                               ELSE false
                           END)
                   AND count(*) = count(DISTINCT t.value->>'limit_key')
            FROM jsonb_array_elements(p_list) AS t(value)), true)
    END
$_$;

COMMENT ON FUNCTION db_pipeline.fn_valid_limit_list(jsonb) IS '공통 규칙 내장 한도 목록 검증. 같은 공통 정책판의 같은 pool_key는 공유 한도';

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
                       AND coalesce(t.value->>'brand_opt_status_cd', '') IN ('ACTIVE','DISCONTINUED'))
                   AND count(*) = count(DISTINCT t.value->>'brand_opt_cd')
            FROM jsonb_array_elements(p_list) AS t(value)), true)
    END
$_$;

COMMENT ON FUNCTION db_pipeline.fn_valid_brand_opt_list(jsonb) IS '상품의 브랜드 선택지 목록 검증. V4 card_product_variant 컬럼과 1:1 대응';

-- ---------------------------------------------------------------------------
-- 시퀀스
-- ---------------------------------------------------------------------------
CREATE SEQUENCE db_pipeline.seq_card_ai_run
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_ai_run IS 'AI 실행 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_bnft
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_bnft IS '확정 혜택 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_doc
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_doc IS '원본 문서 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_doc_chunk
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_doc_chunk IS '문서 청크 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_excl_item
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_excl_item IS '표준 제외 항목 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_excl_item_als
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_excl_item_als IS '제외 항목 별칭 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_extr_stg
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_extr_stg IS 'AI 추출 staging ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_policy_version INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_policy_version IS 'card_policy_version.policy_ver_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_bnft_rule INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_bnft_rule IS 'card_bnft_rule.rule_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_limit_pool INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_limit_pool IS 'card_limit_pool.pool_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_bnft INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_bnft IS 'card_common_bnft.common_bnft_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_policy_version INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_policy_version IS 'card_common_policy_version.common_ver_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_common_bnft_rule INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_common_bnft_rule IS 'card_common_bnft_rule.common_rule_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_source_evidence INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_source_evidence IS 'card_source_evidence.evidence_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_product AS bigint
    START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1 NO CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_product IS 'card_product.card_id bigint 발급; 원본 백업에는 상품 마스터 시퀀스가 없음';

CREATE SEQUENCE db_pipeline.seq_card_policy_evidence INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_policy_evidence IS 'card_policy_evidence.ev_link_id 로컬 업무 ID 발급';

-- ---------------------------------------------------------------------------
-- 상품·정책 영역
-- ---------------------------------------------------------------------------
CREATE TABLE db_pipeline.card_product (
    card_id bigint NOT NULL DEFAULT nextval('db_pipeline.seq_card_product'::regclass),
    product_cd varchar(80) NOT NULL,
    product_nm text NOT NULL,
    issuer varchar(50) NOT NULL,
    card_kind_cd varchar(10) NOT NULL,
    product_status_cd varchar(20) NOT NULL DEFAULT 'ACTIVE',
    launched_on date,
    discontinued_on date,
    brand_opt_list jsonb NOT NULL DEFAULT '[]'::jsonb,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT card_product_pkey PRIMARY KEY (card_id),
    CONSTRAINT card_product_product_cd_key UNIQUE (product_cd),
    CONSTRAINT card_product_card_kind_cd_check CHECK (card_kind_cd IN ('CREDIT','DEBIT')),
    CONSTRAINT card_product_status_check CHECK (product_status_cd IN ('ACTIVE','DISCONTINUED')),
    CONSTRAINT card_product_dates_check CHECK
        (discontinued_on IS NULL OR launched_on IS NULL OR discontinued_on >= launched_on),
    CONSTRAINT card_product_brand_opt_list_check CHECK (db_pipeline.fn_valid_brand_opt_list(brand_opt_list))
);

COMMENT ON TABLE db_pipeline.card_product IS '카드 상품 마스터. 상품 PK는 정책판·문서 관계의 부모. 브랜드 선택지는 brand_opt_list에 통합';
COMMENT ON COLUMN db_pipeline.card_product.card_id IS 'bigint 상품 ID. 기존 card_id 타입과 일치; seq_card_product.nextval 발급';
COMMENT ON COLUMN db_pipeline.card_product.product_cd IS '문서 파일명과 독립된 상품 업무 코드';
COMMENT ON COLUMN db_pipeline.card_product.product_nm IS '카드 상품명';
COMMENT ON COLUMN db_pipeline.card_product.issuer IS '발급 카드사; 제외 항목 issuer와 논리적 범위 일치';
COMMENT ON COLUMN db_pipeline.card_product.card_kind_cd IS 'CREDIT 또는 DEBIT';
COMMENT ON COLUMN db_pipeline.card_product.product_status_cd IS '상품 출시/중단 상태';
COMMENT ON COLUMN db_pipeline.card_product.launched_on IS '상품 출시일(확인된 경우)';
COMMENT ON COLUMN db_pipeline.card_product.discontinued_on IS '상품 중단일(확인된 경우)';
COMMENT ON COLUMN db_pipeline.card_product.brand_opt_list IS '브랜드 선택지 JSONB 배열. [{brand_opt_cd,brand_opt_nm,brand_cd,service_grade_cd,service_type_cd,brand_opt_status_cd}]. V4 card_product_variant 대체';
COMMENT ON COLUMN db_pipeline.card_product.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_product.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN db_pipeline.card_product.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_product.update_user_id IS '수정 사용자 ID';

CREATE TABLE db_pipeline.card_policy_version (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_policy_version') NOT NULL,
    policy_ver_no integer NOT NULL,
    policy_cond_expr jsonb,
    valid_from date NOT NULL,
    valid_to_excl date,
    approved_at timestamptz,
    policy_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id),
    UNIQUE (card_id, policy_ver_no),
    CONSTRAINT card_policy_version_ck_1 CHECK (policy_ver_no > 0),
    CONSTRAINT card_policy_version_ck_2 CHECK (valid_to_excl IS NULL OR valid_to_excl > valid_from),
    CONSTRAINT card_policy_version_ck_3 CHECK (policy_status_cd IN ('DRAFT','APPROVED','RETIRED')),
    CONSTRAINT card_policy_version_ck_4 CHECK (db_pipeline.fn_valid_cond_expr(policy_cond_expr))
);

COMMENT ON TABLE db_pipeline.card_policy_version IS '상품 정책 개정판. 상품당 같은 시점의 승인 정책은 1개. 승인일/적용일/문서일 분리';
COMMENT ON COLUMN db_pipeline.card_policy_version.card_id IS '부모 상품 ID 상속';
COMMENT ON COLUMN db_pipeline.card_policy_version.policy_ver_id IS '정책판 로컬 업무 ID';
COMMENT ON COLUMN db_pipeline.card_policy_version.policy_ver_no IS '상품 안의 정책판 번호(1부터)';
COMMENT ON COLUMN db_pipeline.card_policy_version.policy_cond_expr IS '카드 전체 조건식. 실적 산정 기준, 실적 제외, 유예 조건처럼 특정 혜택에 속하지 않는 조건';
COMMENT ON COLUMN db_pipeline.card_policy_version.valid_from IS '정책 적용 시작일(포함)';
COMMENT ON COLUMN db_pipeline.card_policy_version.valid_to_excl IS '정책 적용 종료일(미포함)';
COMMENT ON COLUMN db_pipeline.card_policy_version.approved_at IS '정책 승인 일시';
COMMENT ON COLUMN db_pipeline.card_policy_version.policy_status_cd IS '정책 상태(DRAFT, APPROVED, RETIRED)';

CREATE TABLE db_pipeline.card_policy_doc (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_doc_id varchar(20) NOT NULL,
    source_role_cd varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_doc_id)
);

COMMENT ON TABLE db_pipeline.card_policy_doc IS '승인 정책판의 원천 문서 연결. 문서 개정판과 정책 개정판은 별개';
COMMENT ON COLUMN db_pipeline.card_policy_doc.card_id IS '부모 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_policy_doc.policy_ver_id IS '부모 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_policy_doc.card_doc_id IS '부모 원천 문서판 ID';
COMMENT ON COLUMN db_pipeline.card_policy_doc.source_role_cd IS '정책판에서 문서가 맡는 역할';

CREATE TABLE db_pipeline.card_product_doc (
    card_id bigint NOT NULL,
    card_doc_id varchar(20) NOT NULL,
    doc_role_cd varchar(20) NOT NULL,
    brand_opt_cds text[],
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
        (doc_role_cd IN ('PRODUCT_GUIDE','COMMON_TERMS','BRAND_SERVICE','OTHER')),
    CONSTRAINT card_product_doc_brand_check CHECK
        (doc_role_cd <> 'BRAND_SERVICE' OR coalesce(cardinality(brand_opt_cds), 0) > 0),
    CONSTRAINT card_product_doc_approval_check CHECK
        (approval_status_cd IN ('PENDING','APPROVED','REJECTED')),
    CONSTRAINT card_product_doc_period_check CHECK
        (effective_to_excl IS NULL OR
         (effective_from IS NOT NULL AND effective_to_excl > effective_from)),
    CONSTRAINT card_product_doc_approved_check CHECK
        (approval_status_cd <> 'APPROVED' OR
         (effective_from IS NOT NULL AND length(trim(applicability_basis_txt)) > 0))
);

COMMENT ON TABLE db_pipeline.card_product_doc IS '상품↔문서판 N:M. PK는 상품/문서 양 부모 키. 브랜드 서비스 문서는 brand_opt_cds로 적용 브랜드 표시';
COMMENT ON COLUMN db_pipeline.card_product_doc.card_id IS '부모 상품 ID';
COMMENT ON COLUMN db_pipeline.card_product_doc.card_doc_id IS '부모 원천 문서판 ID';
COMMENT ON COLUMN db_pipeline.card_product_doc.doc_role_cd IS '상품에 적용되는 문서 역할(PRODUCT_GUIDE, COMMON_TERMS, BRAND_SERVICE, OTHER)';
COMMENT ON COLUMN db_pipeline.card_product_doc.brand_opt_cds IS '문서가 적용되는 brand_opt_cd 목록. BRAND_SERVICE 문서는 필수, NULL이면 상품 전체. V4 card_product_variant_doc 대체';
COMMENT ON COLUMN db_pipeline.card_product_doc.effective_from IS '상품에 문서판 적용 시작일(포함)';
COMMENT ON COLUMN db_pipeline.card_product_doc.effective_to_excl IS '상품에 문서판 적용 종료일(미포함)';
COMMENT ON COLUMN db_pipeline.card_product_doc.approval_status_cd IS '관계 검증/승인 상태';
COMMENT ON COLUMN db_pipeline.card_product_doc.applicability_basis_txt IS '상품에 이 문서가 적용된다는 원문/출처 근거';
COMMENT ON COLUMN db_pipeline.card_product_doc.approval_note IS '승인·검토 메모';
COMMENT ON COLUMN db_pipeline.card_product_doc.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_product_doc.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN db_pipeline.card_product_doc.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_product_doc.update_user_id IS '수정 사용자 ID';

-- ---------------------------------------------------------------------------
-- 상품 혜택 영역
-- ---------------------------------------------------------------------------
CREATE TABLE db_pipeline.card_bnft (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_bnft') NOT NULL,
    bnft_cd varchar(80) NOT NULL,
    bnft_nm text NOT NULL,
    bnft_type_cd varchar(20) NOT NULL,
    bnft_origin_cd varchar(20) NOT NULL,
    bnft_scope_cd varchar(20) NOT NULL,
    bnft_brand_opt_cds text[],
    bnft_cond_expr jsonb,
    rule_select_cd varchar(30),
    verification_status_cd varchar(25) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id),
    UNIQUE (card_id, policy_ver_id, bnft_cd),
    CONSTRAINT card_bnft_ck_1 CHECK (bnft_origin_cd IN ('LOCAL','COMMON_LINK')),
    CONSTRAINT card_bnft_ck_2 CHECK (bnft_scope_cd IN ('PRODUCT','BRAND')),
    CONSTRAINT card_bnft_ck_3 CHECK
        ((bnft_scope_cd = 'PRODUCT' AND bnft_brand_opt_cds IS NULL)
         OR (bnft_scope_cd = 'BRAND' AND coalesce(cardinality(bnft_brand_opt_cds), 0) > 0)),
    CONSTRAINT card_bnft_ck_4 CHECK (db_pipeline.fn_valid_cond_expr(bnft_cond_expr)),
    CONSTRAINT card_bnft_ck_5 CHECK
        (rule_select_cd IS NULL OR rule_select_cd IN ('EXCLUSIVE_BY_SCOPE','PRIORITY','MAX_BENEFIT_VALUE'))
);

COMMENT ON TABLE db_pipeline.card_bnft IS '상품 정책의 혜택 인스턴스. LOCAL 또는 COMMON_LINK; 계산값 없음. 혜택 전체 조건은 bnft_cond_expr';
COMMENT ON COLUMN db_pipeline.card_bnft.card_id IS '부모 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft.policy_ver_id IS '부모 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft.card_bnft_id IS '혜택 로컬 업무 ID';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_cd IS '정책판 안의 혜택 업무 코드';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_nm IS '혜택명';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_type_cd IS '혜택 유형(DISCOUNT, CASHBACK, POINT, FEE_WAIVER, SERVICE, INSTALLMENT, ETC)';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_origin_cd IS 'LOCAL: 상품 고유 규칙 사용, COMMON_LINK: card_bnft_common으로 공통 규칙 사용';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_scope_cd IS 'PRODUCT: 상품 전체, BRAND: bnft_brand_opt_cds에 있는 브랜드 선택지만 적용';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_brand_opt_cds IS '적용 brand_opt_cd 목록. V4 card_bnft_variant 대체';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_cond_expr IS '혜택 전체 조건식. 규칙 조건 및 공통 규칙 조건과 AND로 결합. V4 card_bnft_cond 대체';
COMMENT ON COLUMN db_pipeline.card_bnft.rule_select_cd IS '한 혜택 안에서 규칙이 겹칠 때 선택 방식(EXCLUSIVE_BY_SCOPE, PRIORITY, MAX_BENEFIT_VALUE)';
COMMENT ON COLUMN db_pipeline.card_bnft.verification_status_cd IS '혜택 검증 상태';

CREATE TABLE db_pipeline.card_bnft_rule (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    rule_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_bnft_rule') NOT NULL,
    cond_expr jsonb,
    spend_min_amt numeric(18,2) GENERATED ALWAYS AS
        (db_pipeline.fn_cond_spend_bound(cond_expr, 'cond_min_amt')) STORED,
    spend_max_amt_excl numeric(18,2) GENERATED ALWAYS AS
        (db_pipeline.fn_cond_spend_bound(cond_expr, 'cond_max_amt_excl')) STORED,
    target_list jsonb NOT NULL DEFAULT '[]'::jsonb,
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
    CONSTRAINT card_bnft_rule_ck_4 CHECK (calc_params IS NULL OR jsonb_typeof(calc_params) = 'object'),
    CONSTRAINT card_bnft_rule_ck_5 CHECK (db_pipeline.fn_valid_cond_expr(cond_expr)),
    CONSTRAINT card_bnft_rule_ck_6 CHECK (db_pipeline.fn_valid_target_list(target_list)),
    CONSTRAINT card_bnft_rule_ck_7 CHECK
        ((predicate_state_cd = 'CONDITIONAL' AND cond_expr IS NOT NULL)
         OR (predicate_state_cd = 'VERIFIED_UNCONDITIONAL' AND cond_expr IS NULL)
         OR predicate_state_cd = 'PENDING_REVIEW'),
    CONSTRAINT card_bnft_rule_ck_8 CHECK (rule_status_cd IN ('DRAFT','CONFIRMED','RETIRED')),
    CONSTRAINT card_bnft_rule_ck_9 CHECK (rule_status_cd <> 'CONFIRMED' OR jsonb_array_length(target_list) > 0)
);

COMMENT ON TABLE db_pipeline.card_bnft_rule IS 'LOCAL 혜택의 유일한 계산값 원천. 규칙 조건과 대상은 cond_expr, target_list에 내장. COMMON_LINK에는 로컬 규칙 없음';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.card_id IS '부모 혜택 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.policy_ver_id IS '부모 혜택 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.card_bnft_id IS '부모 혜택 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.rule_id IS '규칙 로컬 업무 ID';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.cond_expr IS '규칙 조건식. NULL은 무조건을 뜻하지 않으며 predicate_state_cd로 판정. V4 expr_id, card_cond_expr, card_cond_expr_atom, card_cond 대체';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.spend_min_amt IS 'cond_expr에서 파생한 전월 실적 하한(포함). 직접 입력 금지. OR식은 NULL';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.spend_max_amt_excl IS 'cond_expr에서 파생한 전월 실적 상한(미포함). 직접 입력 금지. OR식은 NULL';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.target_list IS '규칙 대상 JSONB 배열. [{target_type_cd,target_key,target_nm}]. V4 card_bnft_target, card_bnft_rule_target 대체';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.predicate_state_cd IS 'CONDITIONAL, VERIFIED_UNCONDITIONAL(원문 확인된 무조건), PENDING_REVIEW';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.calc_method_cd IS '계산 방법 코드. card_method_catalog 논리 참조';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.method_ver IS '계산 방법 버전';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.value_num IS '방법 코드별로 의미가 고정된 값. PERCENT_OF_TXN의 1.5는 1.5%';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.value_unit_cd IS 'value_num의 단위';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.payout_unit_cd IS '실제 보상 단위(KRW, HANAMONEY, UNIMILE 등)';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.basis_amt IS '기준 금액(1,500원당 적립의 1500 등)';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.calc_params IS '방법별 가변 파라미터. card_method_catalog.param_schema로 검증';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.rule_priority IS '원문에 명시된 규칙 우선순위';
COMMENT ON COLUMN db_pipeline.card_bnft_rule.rule_status_cd IS '규칙 상태(DRAFT, CONFIRMED, RETIRED)';

CREATE TABLE db_pipeline.card_limit_pool (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    pool_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_limit_pool') NOT NULL,
    pool_scope_cd varchar(30) NOT NULL,
    period_cd varchar(20) NOT NULL,
    cap_unit_cd varchar(30) NOT NULL,
    aggregation_key_cd varchar(30) NOT NULL,
    tier_list jsonb NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, pool_id),
    CONSTRAINT card_limit_pool_ck_1 CHECK (db_pipeline.fn_valid_tier_list(tier_list))
);

COMMENT ON TABLE db_pipeline.card_limit_pool IS '상품 정책판의 독립 한도. 여러 규칙이 공유; 혜택의 자식이 아님. 한도 구간은 tier_list에 내장';
COMMENT ON COLUMN db_pipeline.card_limit_pool.card_id IS '부모 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_limit_pool.policy_ver_id IS '부모 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_limit_pool.pool_id IS '한도 풀 로컬 업무 ID';
COMMENT ON COLUMN db_pipeline.card_limit_pool.pool_scope_cd IS '한도 범위(영역, 카드 전체 등)';
COMMENT ON COLUMN db_pipeline.card_limit_pool.period_cd IS '한도 기간(TXN, DAY, MONTH, YEAR 등)';
COMMENT ON COLUMN db_pipeline.card_limit_pool.cap_unit_cd IS '한도 단위(KRW, HANAMONEY, COUNT 등)';
COMMENT ON COLUMN db_pipeline.card_limit_pool.aggregation_key_cd IS '누적 집계 기준';
COMMENT ON COLUMN db_pipeline.card_limit_pool.tier_list IS '한도 구간 JSONB 배열. [{tier_key,tier_priority,predicate_state_cd,limit_num,cond_expr}]. V4 card_limit_tier 대체';

CREATE TABLE db_pipeline.card_bnft_rule_pool (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    rule_id varchar(20) NOT NULL,
    pool_id varchar(20) NOT NULL,
    pool_role_cd varchar(30) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, rule_id, pool_id)
);

COMMENT ON TABLE db_pipeline.card_bnft_rule_pool IS '규칙이 소비하는 한도 풀 N:M. 영역/전체 풀 동시 연결 가능';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.card_id IS '부모 규칙 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.policy_ver_id IS '부모 규칙 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.card_bnft_id IS '부모 규칙 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.rule_id IS '부모 규칙 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.pool_id IS '부모 한도 풀 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.pool_role_cd IS '규칙에서 풀이 맡는 역할';

CREATE TABLE db_pipeline.card_bnft_rel (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    from_bnft_id varchar(20) NOT NULL,
    to_bnft_id varchar(20) NOT NULL,
    rel_type_cd varchar(30) NOT NULL,
    trigger_pool_id varchar(20),
    rel_priority integer,
    PRIMARY KEY (card_id, policy_ver_id, from_bnft_id, to_bnft_id, rel_type_cd),
    CONSTRAINT card_bnft_rel_ck_1 CHECK (from_bnft_id <> to_bnft_id),
    CONSTRAINT card_bnft_rel_ck_2 CHECK (rel_type_cd <> 'FALLBACK_AFTER_CAP' OR trigger_pool_id IS NOT NULL)
);

COMMENT ON TABLE db_pipeline.card_bnft_rel IS '같은 정책판의 두 혜택 간 배타/우선/대체. 소진 후 대체는 trigger_pool_id 필수';
COMMENT ON COLUMN db_pipeline.card_bnft_rel.card_id IS '부모 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_rel.policy_ver_id IS '부모 정책판 키 상속. 발급형 추가 정책판 제거로 from/to 구분 불필요';
COMMENT ON COLUMN db_pipeline.card_bnft_rel.from_bnft_id IS '관계 시작 혜택 ID';
COMMENT ON COLUMN db_pipeline.card_bnft_rel.to_bnft_id IS '관계 도착 혜택 ID';
COMMENT ON COLUMN db_pipeline.card_bnft_rel.rel_type_cd IS '관계 유형(MUTUALLY_EXCLUSIVE, FALLBACK_AFTER_CAP, OVERRIDES 등)';
COMMENT ON COLUMN db_pipeline.card_bnft_rel.trigger_pool_id IS '소진 시 대체를 일으키는 한도 풀 ID';
COMMENT ON COLUMN db_pipeline.card_bnft_rel.rel_priority IS '관계 우선순위';

-- ---------------------------------------------------------------------------
-- 공통 혜택 영역. 정체성·정책판·규칙·적용 관계만 테이블로 유지
-- ---------------------------------------------------------------------------
CREATE TABLE db_pipeline.card_common_bnft (
    common_bnft_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_bnft') NOT NULL,
    provider_cd varchar(30) NOT NULL,
    service_grade_cd varchar(30) NOT NULL DEFAULT 'NONE',
    service_type_cd varchar(30) NOT NULL DEFAULT 'NONE',
    common_bnft_cd varchar(80) NOT NULL,
    common_bnft_nm text NOT NULL,
    PRIMARY KEY (common_bnft_id),
    UNIQUE (common_bnft_cd)
);

COMMENT ON TABLE db_pipeline.card_common_bnft IS '특정 카드에 종속되지 않는 공통 서비스 정체성. 동일 이름이나 같은 PDF만으로 병합 금지';
COMMENT ON COLUMN db_pipeline.card_common_bnft.common_bnft_id IS '공통 혜택 업무 ID';
COMMENT ON COLUMN db_pipeline.card_common_bnft.provider_cd IS '제공 주체(국제 브랜드 등)';
COMMENT ON COLUMN db_pipeline.card_common_bnft.service_grade_cd IS '브랜드 서비스 등급(PLATINUM, WORLD 등). 해당 없으면 NONE';
COMMENT ON COLUMN db_pipeline.card_common_bnft.service_type_cd IS '서비스 유형(COMMON: 등급 공통, 01~04: 선택서비스 유형). 해당 없으면 NONE';
COMMENT ON COLUMN db_pipeline.card_common_bnft.common_bnft_cd IS '공통 혜택 업무 코드';
COMMENT ON COLUMN db_pipeline.card_common_bnft.common_bnft_nm IS '공통 혜택명';

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
COMMENT ON COLUMN db_pipeline.card_common_policy_version.common_bnft_id IS '부모 공통 혜택 키 상속';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.common_ver_id IS '공통 정책판 로컬 업무 ID';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.common_ver_no IS '공통 혜택 안의 정책판 번호(1부터)';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.valid_from IS '공통 정책 적용 시작일(포함)';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.valid_to_excl IS '공통 정책 적용 종료일(미포함)';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.approved_at IS '공통 정책 승인 일시';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.policy_status_cd IS '정책 상태(DRAFT, APPROVED, RETIRED)';

CREATE TABLE db_pipeline.card_common_bnft_rule (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_rule_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_bnft_rule') NOT NULL,
    cond_expr jsonb,
    target_list jsonb NOT NULL DEFAULT '[]'::jsonb,
    limit_list jsonb NOT NULL DEFAULT '[]'::jsonb,
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
    CONSTRAINT card_common_bnft_rule_ck_4 CHECK (calc_params IS NULL OR jsonb_typeof(calc_params) = 'object'),
    CONSTRAINT card_common_bnft_rule_ck_5 CHECK (db_pipeline.fn_valid_cond_expr(cond_expr)),
    CONSTRAINT card_common_bnft_rule_ck_6 CHECK (db_pipeline.fn_valid_target_list(target_list)),
    CONSTRAINT card_common_bnft_rule_ck_7 CHECK (db_pipeline.fn_valid_limit_list(limit_list)),
    CONSTRAINT card_common_bnft_rule_ck_8 CHECK
        ((predicate_state_cd = 'CONDITIONAL' AND cond_expr IS NOT NULL)
         OR (predicate_state_cd = 'VERIFIED_UNCONDITIONAL' AND cond_expr IS NULL)
         OR predicate_state_cd = 'PENDING_REVIEW'),
    CONSTRAINT card_common_bnft_rule_ck_9 CHECK (rule_status_cd IN ('DRAFT','CONFIRMED','RETIRED')),
    CONSTRAINT card_common_bnft_rule_ck_10 CHECK (rule_status_cd <> 'CONFIRMED' OR jsonb_array_length(target_list) > 0)
);

COMMENT ON TABLE db_pipeline.card_common_bnft_rule IS '공통 혜택 계산값의 단일 기준. 조건·대상·한도를 JSONB로 내장; 상품 로컬 규칙에 값 복제 금지';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.common_bnft_id IS '부모 공통 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.common_ver_id IS '부모 공통 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.common_rule_id IS '공통 규칙 로컬 업무 ID';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.cond_expr IS '공통 조건식. card_cond_expr와 같은 계약. 상품별 추가 조건은 card_bnft.bnft_cond_expr에 두고 AND 결합';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.target_list IS '공통 대상 JSONB 배열. card_bnft_rule.target_list와 같은 계약';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.limit_list IS '공통 한도 JSONB 배열. [{limit_key,pool_key,period_cd,cap_unit_cd,aggregation_key_cd,predicate_state_cd,limit_num,cond_expr}]. 같은 정책판의 같은 pool_key는 공유 한도';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.predicate_state_cd IS 'CONDITIONAL, VERIFIED_UNCONDITIONAL, PENDING_REVIEW';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.calc_method_cd IS '계산 방법 코드. card_method_catalog 논리 참조';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.method_ver IS '계산 방법 버전';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.value_num IS '방법 코드별로 의미가 고정된 값';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.value_unit_cd IS 'value_num의 단위';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.payout_unit_cd IS '실제 보상 단위';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.basis_amt IS '기준 금액';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.calc_params IS '방법별 가변 파라미터';
COMMENT ON COLUMN db_pipeline.card_common_bnft_rule.rule_status_cd IS '규칙 상태(DRAFT, CONFIRMED, RETIRED)';

CREATE TABLE db_pipeline.card_bnft_common (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    apply_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, common_bnft_id, common_ver_id),
    CONSTRAINT card_bnft_common_ck_1 CHECK (apply_status_cd IN ('PENDING','APPROVED','REJECTED'))
);

COMMENT ON TABLE db_pipeline.card_bnft_common IS '상품 혜택 인스턴스↔승인된 공통 정책판 N:M. COMMON_LINK에서만 사용; 상품별 조건은 card_bnft.bnft_cond_expr로 AND 추가';
COMMENT ON COLUMN db_pipeline.card_bnft_common.card_id IS '부모 혜택 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_common.policy_ver_id IS '부모 혜택 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_common.card_bnft_id IS '부모 혜택 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_common.common_bnft_id IS '부모 공통 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_common.common_ver_id IS '부모 공통 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_bnft_common.apply_status_cd IS '적용 승인 상태(PENDING, APPROVED, REJECTED)';

-- ---------------------------------------------------------------------------
-- 근거 연결 영역
-- ---------------------------------------------------------------------------
CREATE TABLE db_pipeline.card_policy_evidence (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    ev_link_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_policy_evidence') NOT NULL,
    ev_subject_cd varchar(10) NOT NULL,
    card_bnft_id varchar(20),
    rule_id varchar(20),
    pool_id varchar(20),
    to_bnft_id varchar(20),
    rel_type_cd varchar(30),
    ev_item_cd varchar(10) NOT NULL DEFAULT 'SELF',
    ev_item_key varchar(100) NOT NULL DEFAULT '-',
    evidence_id varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, ev_link_id),
    CONSTRAINT card_policy_evidence_natural_key UNIQUE NULLS NOT DISTINCT
        (card_id, policy_ver_id, ev_subject_cd, card_bnft_id, rule_id, pool_id,
         to_bnft_id, rel_type_cd, ev_item_cd, ev_item_key, evidence_id),
    CONSTRAINT card_policy_evidence_ck_1 CHECK (ev_item_cd IN ('SELF','COND','TARGET','TIER')),
    CONSTRAINT card_policy_evidence_ck_2 CHECK ((ev_item_cd = 'SELF') = (ev_item_key = '-')),
    CONSTRAINT card_policy_evidence_ck_3 CHECK (
        CASE ev_subject_cd
            WHEN 'POLICY' THEN num_nonnulls(card_bnft_id, rule_id, pool_id, to_bnft_id, rel_type_cd) = 0
            WHEN 'BNFT' THEN card_bnft_id IS NOT NULL
                             AND num_nonnulls(rule_id, pool_id, to_bnft_id, rel_type_cd) = 0
            WHEN 'RULE' THEN card_bnft_id IS NOT NULL AND rule_id IS NOT NULL
                             AND num_nonnulls(pool_id, to_bnft_id, rel_type_cd) = 0
            WHEN 'POOL' THEN pool_id IS NOT NULL
                             AND num_nonnulls(card_bnft_id, rule_id, to_bnft_id, rel_type_cd) = 0
            WHEN 'REL' THEN card_bnft_id IS NOT NULL AND to_bnft_id IS NOT NULL AND rel_type_cd IS NOT NULL
                            AND num_nonnulls(rule_id, pool_id) = 0
            ELSE false
        END),
    CONSTRAINT card_policy_evidence_ck_4 CHECK (
        CASE ev_item_cd
            WHEN 'SELF' THEN true
            WHEN 'COND' THEN ev_subject_cd IN ('POLICY','BNFT','RULE','POOL')
            WHEN 'TARGET' THEN ev_subject_cd = 'RULE'
            WHEN 'TIER' THEN ev_subject_cd = 'POOL'
        END)
);

COMMENT ON TABLE db_pipeline.card_policy_evidence IS '상품 정책 대상↔원문 근거 연결. 대상 유형별 타입 컬럼을 CHECK로 고정해 논리 FK 검사 가능. V4 근거 연결 4종 통합';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.card_id IS '부모 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.policy_ver_id IS '부모 정책판 키 상속';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.ev_link_id IS '근거 연결 로컬 업무 ID';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.ev_subject_cd IS '근거 대상 유형(POLICY, BNFT, RULE, POOL, REL)';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.card_bnft_id IS 'BNFT, RULE의 혜택 ID 또는 REL의 from_bnft_id';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.rule_id IS 'RULE의 규칙 ID';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.pool_id IS 'POOL의 한도 풀 ID';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.to_bnft_id IS 'REL의 to_bnft_id';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.rel_type_cd IS 'REL의 관계 유형';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.ev_item_cd IS '대상 안의 JSONB 항목 유형(SELF: 행 전체, COND: 조건 atom, TARGET: 대상, TIER: 한도 구간)';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.ev_item_key IS 'JSONB 항목 키(atom_key, target_key, tier_key). SELF는 -';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.evidence_id IS '부모 원문 근거 ID';

CREATE TABLE db_pipeline.card_common_rule_evidence (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    common_rule_id varchar(20) NOT NULL,
    evidence_id varchar(20) NOT NULL,
    ev_item_cd varchar(10) NOT NULL DEFAULT 'SELF',
    ev_item_key varchar(100) NOT NULL DEFAULT '-',
    PRIMARY KEY (common_bnft_id, common_ver_id, common_rule_id, evidence_id, ev_item_cd, ev_item_key),
    CONSTRAINT card_common_rule_evidence_ck_1 CHECK (ev_item_cd IN ('SELF','COND','TARGET','LIMIT')),
    CONSTRAINT card_common_rule_evidence_ck_2 CHECK ((ev_item_cd = 'SELF') = (ev_item_key = '-'))
);

COMMENT ON TABLE db_pipeline.card_common_rule_evidence IS '공통 규칙↔원문 근거 N:M. 규칙에 내장된 조건·대상·한도 근거는 ev_item_cd/ev_item_key로 구분';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.common_bnft_id IS '부모 공통 규칙 키 상속';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.common_ver_id IS '부모 공통 규칙 키 상속';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.common_rule_id IS '부모 공통 규칙 키 상속';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.evidence_id IS '부모 원문 근거 ID';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.ev_item_cd IS '규칙 안의 항목 유형(SELF, COND, TARGET, LIMIT)';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.ev_item_key IS 'JSONB 항목 키(atom_key, target_key, limit_key). SELF는 -';

-- ---------------------------------------------------------------------------
-- 계산 방법·원천 문서·AI 파싱·근거 영역. V4 정의 유지
-- ---------------------------------------------------------------------------
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

COMMENT ON TABLE db_pipeline.card_doc IS '원천 PDF 파일/문서판. 상품 적용은 card_product_doc에서 관리';
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

CREATE TABLE db_pipeline.card_excl_item_als (
    card_excl_item_id character varying(20) NOT NULL,
    card_excl_item_als_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_excl_item_als'::text) NOT NULL,
    excl_item_als_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);

COMMENT ON TABLE db_pipeline.card_excl_item_als IS '제외 항목 원문 표기 별칭(SQL 정규화 사전)';
COMMENT ON COLUMN db_pipeline.card_excl_item_als.card_excl_item_id IS '표준 제외 항목 ID';
COMMENT ON COLUMN db_pipeline.card_excl_item_als.card_excl_item_als_id IS '제외 항목 별칭 ID';
COMMENT ON COLUMN db_pipeline.card_excl_item_als.excl_item_als_nm IS '원문 표기(공백 제거 비교 기준). 의미가 불확실한 표기(예: 상품/)는 등록하지 않음';
COMMENT ON COLUMN db_pipeline.card_excl_item_als.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_excl_item_als.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN db_pipeline.card_excl_item_als.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_excl_item_als.update_user_id IS '수정 사용자 ID';

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

-- ---------------------------------------------------------------------------
-- 인덱스 (업무 영역)
-- ---------------------------------------------------------------------------
CREATE INDEX card_product_kind_status_idx ON db_pipeline.card_product (card_kind_cd, product_status_cd);

CREATE INDEX card_product_brand_opt_gin_idx ON db_pipeline.card_product USING gin (brand_opt_list jsonb_path_ops);

CREATE INDEX card_product_doc_doc_idx ON db_pipeline.card_product_doc (card_doc_id, card_id);

CREATE INDEX card_product_doc_current_idx
    ON db_pipeline.card_product_doc (card_id, effective_from, effective_to_excl)
    WHERE approval_status_cd = 'APPROVED';

CREATE INDEX ix_card_policy_version_lookup ON db_pipeline.card_policy_version (card_id, policy_status_cd, valid_from, valid_to_excl);

CREATE INDEX ix_card_bnft_brand_opt_gin ON db_pipeline.card_bnft USING gin (bnft_brand_opt_cds);

CREATE INDEX ix_card_bnft_cond_gin ON db_pipeline.card_bnft USING gin (bnft_cond_expr jsonb_path_ops);

CREATE INDEX ix_card_bnft_rule_spend ON db_pipeline.card_bnft_rule (card_id, policy_ver_id, spend_min_amt, spend_max_amt_excl);

CREATE INDEX ix_card_bnft_rule_target_gin ON db_pipeline.card_bnft_rule USING gin (target_list jsonb_path_ops);

CREATE INDEX ix_card_bnft_rule_cond_gin ON db_pipeline.card_bnft_rule USING gin (cond_expr jsonb_path_ops);

CREATE INDEX ix_card_bnft_rule_pool_lookup ON db_pipeline.card_bnft_rule_pool (card_id, policy_ver_id, pool_id);

CREATE INDEX ix_card_bnft_rel_lookup ON db_pipeline.card_bnft_rel (card_id, policy_ver_id, to_bnft_id);

CREATE INDEX ix_card_bnft_common_lookup ON db_pipeline.card_bnft_common (common_bnft_id, common_ver_id);

CREATE INDEX ix_card_common_policy_version_lookup ON db_pipeline.card_common_policy_version (common_bnft_id, policy_status_cd, valid_from, valid_to_excl);

CREATE INDEX ix_card_common_bnft_service ON db_pipeline.card_common_bnft (provider_cd, service_grade_cd, service_type_cd);

CREATE INDEX ix_card_common_rule_target_gin ON db_pipeline.card_common_bnft_rule USING gin (target_list jsonb_path_ops);

CREATE INDEX ix_card_source_evidence_lookup ON db_pipeline.card_source_evidence (card_doc_id, page_no, card_doc_chunk_id);

CREATE INDEX ix_card_policy_evidence_subject ON db_pipeline.card_policy_evidence (card_id, policy_ver_id, ev_subject_cd, card_bnft_id, rule_id);

CREATE INDEX ix_card_policy_evidence_evidence ON db_pipeline.card_policy_evidence (evidence_id);

CREATE INDEX ix_card_common_rule_evidence_evidence ON db_pipeline.card_common_rule_evidence (evidence_id);

-- ---------------------------------------------------------------------------
-- 조회 뷰. JSONB 저장값을 V4와 같은 행 구조로 펼쳐 SQL 검증과 Neo4j 적재에 사용
-- ---------------------------------------------------------------------------
CREATE VIEW db_pipeline.v_card_brand_opt AS
SELECT p.card_id, p.product_cd, p.product_nm,
       o.value->>'brand_opt_cd' AS brand_opt_cd,
       o.value->>'brand_opt_nm' AS brand_opt_nm,
       o.value->>'brand_cd' AS brand_cd,
       o.value->>'service_grade_cd' AS service_grade_cd,
       o.value->>'service_type_cd' AS service_type_cd,
       o.value->>'brand_opt_status_cd' AS brand_opt_status_cd
FROM db_pipeline.card_product p
CROSS JOIN LATERAL jsonb_array_elements(p.brand_opt_list) AS o(value);

COMMENT ON VIEW db_pipeline.v_card_brand_opt IS '상품별 브랜드 선택지를 행으로 펼친 뷰. V4 card_product_variant 조회 대체';

CREATE VIEW db_pipeline.v_card_rule_target AS
SELECT 'LOCAL'::text AS rule_source_cd, r.card_id, r.policy_ver_id, r.card_bnft_id, r.rule_id,
       NULL::varchar AS common_bnft_id, NULL::varchar AS common_ver_id, NULL::varchar AS common_rule_id,
       t.value->>'target_type_cd' AS target_type_cd,
       t.value->>'target_key' AS target_key,
       t.value->>'target_nm' AS target_nm
FROM db_pipeline.card_bnft_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.target_list) AS t(value)
UNION ALL
SELECT 'COMMON', NULL, NULL, NULL, NULL,
       r.common_bnft_id, r.common_ver_id, r.common_rule_id,
       t.value->>'target_type_cd', t.value->>'target_key', t.value->>'target_nm'
FROM db_pipeline.card_common_bnft_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.target_list) AS t(value);

COMMENT ON VIEW db_pipeline.v_card_rule_target IS '규칙 대상을 행으로 펼친 뷰. V4 card_bnft_rule_target JOIN card_bnft_target 조회 대체';

CREATE VIEW db_pipeline.v_card_limit_tier AS
SELECT p.card_id, p.policy_ver_id, p.pool_id, p.pool_scope_cd, p.period_cd, p.cap_unit_cd,
       p.aggregation_key_cd,
       t.value->>'tier_key' AS tier_key,
       (t.value->>'tier_priority')::integer AS tier_priority,
       t.value->>'predicate_state_cd' AS predicate_state_cd,
       (t.value->>'limit_num')::numeric(18,2) AS limit_num,
       db_pipeline.fn_cond_spend_bound(t.value->'cond_expr', 'cond_min_amt') AS spend_min_amt,
       db_pipeline.fn_cond_spend_bound(t.value->'cond_expr', 'cond_max_amt_excl') AS spend_max_amt_excl,
       t.value->'cond_expr' AS cond_expr
FROM db_pipeline.card_limit_pool p
CROSS JOIN LATERAL jsonb_array_elements(p.tier_list) AS t(value);

COMMENT ON VIEW db_pipeline.v_card_limit_tier IS '한도 풀 구간을 행으로 펼친 뷰. V4 card_limit_tier 조회 대체';

CREATE VIEW db_pipeline.v_card_common_limit AS
SELECT r.common_bnft_id, r.common_ver_id, r.common_rule_id,
       l.value->>'limit_key' AS limit_key,
       coalesce(l.value->>'pool_key', r.common_rule_id || ':' || (l.value->>'limit_key')) AS pool_key,
       l.value->>'period_cd' AS period_cd,
       l.value->>'cap_unit_cd' AS cap_unit_cd,
       l.value->>'aggregation_key_cd' AS aggregation_key_cd,
       l.value->>'predicate_state_cd' AS predicate_state_cd,
       (l.value->>'limit_num')::numeric(18,2) AS limit_num,
       l.value->'cond_expr' AS cond_expr
FROM db_pipeline.card_common_bnft_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.limit_list) AS l(value);

COMMENT ON VIEW db_pipeline.v_card_common_limit IS '공통 규칙 내장 한도를 행으로 펼친 뷰. V4 card_common_limit_pool/tier/rule_pool 조회 대체';

CREATE VIEW db_pipeline.v_card_cond_atom AS
WITH src AS (
    SELECT 'POLICY'::text AS owner_cd, v.card_id, v.policy_ver_id, NULL::varchar AS card_bnft_id,
           NULL::varchar AS rule_id, NULL::varchar AS pool_id, NULL::text AS item_key,
           NULL::varchar AS common_bnft_id, NULL::varchar AS common_ver_id, NULL::varchar AS common_rule_id,
           v.policy_cond_expr AS expr
    FROM db_pipeline.card_policy_version v WHERE v.policy_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'BNFT', b.card_id, b.policy_ver_id, b.card_bnft_id, NULL, NULL, NULL, NULL, NULL, NULL, b.bnft_cond_expr
    FROM db_pipeline.card_bnft b WHERE b.bnft_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'RULE', r.card_id, r.policy_ver_id, r.card_bnft_id, r.rule_id, NULL, NULL, NULL, NULL, NULL, r.cond_expr
    FROM db_pipeline.card_bnft_rule r WHERE r.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'POOL_TIER', t.card_id, t.policy_ver_id, NULL, NULL, t.pool_id, t.tier_key, NULL, NULL, NULL, t.cond_expr
    FROM db_pipeline.v_card_limit_tier t WHERE t.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'COMMON_RULE', NULL, NULL, NULL, NULL, NULL, NULL,
           r.common_bnft_id, r.common_ver_id, r.common_rule_id, r.cond_expr
    FROM db_pipeline.card_common_bnft_rule r WHERE r.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'COMMON_LIMIT', NULL, NULL, NULL, NULL, NULL, l.limit_key,
           l.common_bnft_id, l.common_ver_id, l.common_rule_id, l.cond_expr
    FROM db_pipeline.v_card_common_limit l WHERE l.cond_expr IS NOT NULL
)
SELECT s.owner_cd, s.card_id, s.policy_ver_id, s.card_bnft_id, s.rule_id, s.pool_id, s.item_key,
       s.common_bnft_id, s.common_ver_id, s.common_rule_id,
       (b.value->>'branch_no')::integer AS branch_no,
       (a.value->>'atom_seq')::integer AS atom_seq,
       a.value->>'atom_key' AS atom_key,
       (a.value->>'negate_yn')::boolean AS negate_yn,
       a.value->>'cond_type_cd' AS cond_type_cd,
       a.value->>'cond_basis_cd' AS cond_basis_cd,
       (a.value->>'cond_min_amt')::numeric(18,2) AS cond_min_amt,
       (a.value->>'cond_max_amt_excl')::numeric(18,2) AS cond_max_amt_excl,
       a.value->>'predicate_method_cd' AS predicate_method_cd,
       (a.value->>'predicate_method_ver')::integer AS predicate_method_ver,
       a.value->'cond_params' AS cond_params,
       a.value->>'card_excl_item_id' AS card_excl_item_id,
       a.value->>'excl_raw_txt' AS excl_raw_txt,
       a.value->>'cond_raw_txt' AS cond_raw_txt,
       a.value->>'link_role_cd' AS link_role_cd,
       a.value->>'cond_status_cd' AS cond_status_cd
FROM src s
CROSS JOIN LATERAL jsonb_array_elements(s.expr->'branches') AS b(value)
CROSS JOIN LATERAL jsonb_array_elements(b.value->'atoms') AS a(value);

COMMENT ON VIEW db_pipeline.v_card_cond_atom IS '모든 조건식의 atom을 소유자와 함께 행으로 펼친 뷰. V4 card_cond, card_cond_expr_atom, card_bnft_cond 조회 대체';

CREATE VIEW db_pipeline.v_card_bnft_rule_effective AS
SELECT b.card_id, b.policy_ver_id, b.card_bnft_id, b.bnft_nm, b.bnft_scope_cd, b.bnft_brand_opt_cds,
       'LOCAL'::text AS rule_source_cd, r.rule_id AS rule_key,
       NULL::varchar AS common_bnft_id, NULL::varchar AS common_ver_id,
       NULL::date AS common_valid_from, NULL::date AS common_valid_to_excl,
       r.calc_method_cd, r.method_ver, r.value_num, r.value_unit_cd, r.payout_unit_cd, r.basis_amt,
       r.calc_params, r.predicate_state_cd, r.target_list,
       b.bnft_cond_expr, r.cond_expr AS rule_cond_expr, r.rule_status_cd
FROM db_pipeline.card_bnft b
JOIN db_pipeline.card_bnft_rule r
  ON (r.card_id, r.policy_ver_id, r.card_bnft_id) = (b.card_id, b.policy_ver_id, b.card_bnft_id)
WHERE b.bnft_origin_cd = 'LOCAL'
UNION ALL
SELECT b.card_id, b.policy_ver_id, b.card_bnft_id, b.bnft_nm, b.bnft_scope_cd, b.bnft_brand_opt_cds,
       'COMMON', cr.common_rule_id, x.common_bnft_id, x.common_ver_id,
       cv.valid_from, cv.valid_to_excl,
       cr.calc_method_cd, cr.method_ver, cr.value_num, cr.value_unit_cd, cr.payout_unit_cd, cr.basis_amt,
       cr.calc_params, cr.predicate_state_cd, cr.target_list,
       b.bnft_cond_expr, cr.cond_expr, cr.rule_status_cd
FROM db_pipeline.card_bnft b
JOIN db_pipeline.card_bnft_common x
  ON (x.card_id, x.policy_ver_id, x.card_bnft_id) = (b.card_id, b.policy_ver_id, b.card_bnft_id)
JOIN db_pipeline.card_common_policy_version cv
  ON (cv.common_bnft_id, cv.common_ver_id) = (x.common_bnft_id, x.common_ver_id)
JOIN db_pipeline.card_common_bnft_rule cr
  ON (cr.common_bnft_id, cr.common_ver_id) = (x.common_bnft_id, x.common_ver_id)
WHERE b.bnft_origin_cd = 'COMMON_LINK'
  AND x.apply_status_cd = 'APPROVED'
  AND cv.policy_status_cd = 'APPROVED';

COMMENT ON VIEW db_pipeline.v_card_bnft_rule_effective IS '상품 고유 규칙과 승인된 공통 규칙의 단일 출력. 값은 정책 후보이며 거래별 보상액이 아님';

-- Approved policy overlap (must return 0 rows before approval):
-- SELECT a.card_id,a.policy_ver_id,b.policy_ver_id
-- FROM db_pipeline.card_policy_version a JOIN db_pipeline.card_policy_version b
-- ON a.card_id=b.card_id AND a.policy_ver_id<b.policy_ver_id
-- AND a.policy_status_cd='APPROVED' AND b.policy_status_cd='APPROVED'
-- AND daterange(a.valid_from,a.valid_to_excl,'[)') && daterange(b.valid_from,b.valid_to_excl,'[)');
-- Because physical FKs are intentionally absent, run logical orphan checks before approval.
