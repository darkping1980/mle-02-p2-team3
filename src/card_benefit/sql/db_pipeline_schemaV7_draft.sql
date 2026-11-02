-- V7 draft integrated creation for an EMPTY db_pipeline schema.
-- No DROP and no physical foreign keys. Apply only after target/row/dependency checks.
-- V7 removes the card policy version layer: benefits, limits and evidence attach directly to card_product.
-- V7 also removes the common benefit tables: a brand benefit is stored per card in card_bnft, while the
-- brand PDF, its AI extraction and its source evidence are stored once and shared by evidence links.
-- An existing V6 database moves with db_pipeline_migration_V6_to_V7.sql, not with this file.
-- Load db_pipeline_common_code_seedV7.sql after this file, then db_pipeline_common_code_descV7.sql.
-- Code columns are validated by v_card_integrity_issue against common_cd, so enumerations are
-- not repeated in CHECK constraints.
-- CHECK constraints keep structure rules only: types, ranges, required pairs, key uniqueness.
--
-- JSONB contracts (validated by fn_valid_*):
--   cond_expr        {"expr_status_cd", "branches":[{"branch_no","atoms":[{"atom_seq","atom_key",
--                     "negate_yn","cond_type_cd","cond_basis_cd","cond_min_amt","cond_max_amt_excl",
--                     "predicate_method_cd","predicate_method_ver","cond_params","card_excl_item_id",
--                     "excl_raw_txt","cond_raw_txt","link_role_cd","cond_status_cd"}]}]}
--                     branches = OR, atoms in a branch = AND, negate_yn = NOT, [min,max) spend range.
--   rule_list        [{"rule_key","cond_expr","predicate_state_cd","target_list","calc_method_cd",
--                      "method_ver","value_num","value_unit_cd","payout_unit_cd","basis_amt",
--                      "calc_params","rule_priority","rule_status_cd"}]        card_bnft
--   relation_list    [{"relation_key","to_bnft_id","rel_type_cd","rel_priority"}]
--   target_list      [{"target_type_cd","target_key","target_nm"}]
--   brand_opt_list   [{"brand_opt_cd","brand_opt_nm","brand_cd","service_grade_cd","service_type_cd",
--                      "brand_opt_status_cd"}]
-- method_ver and predicate_method_ver are representation contract versions, currently 1. V7 has no calculation
-- engine or method catalog, so nothing checks them against an executable handler.
-- Effective condition: card_cond_expr AND bnft_cond_expr AND rule cond_expr.
-- 혜택 설명과 한도는 card_bnft.bnft_rule_txt, bnft_limit_txt의 원문 기반 TEXT로 둔다. 고객별 지급액을 계산하지 않으므로
-- 한도 풀과 규칙-한도 연결은 만들지 않는다. TEXT NULL은 한도 없음이 아니라 미확인이다.


CREATE SCHEMA db_pipeline;

COMMENT ON SCHEMA db_pipeline IS '카드 상품 중심 V7 공통코드·반정규화 스키마(초안)';

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

COMMENT ON FUNCTION db_pipeline.fn_valid_brand_opt_list(jsonb) IS '상품의 브랜드 선택지 목록 검증. 코드값 소속은 v_common_cd_usage로 검사';

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

COMMENT ON FUNCTION db_pipeline.fn_valid_rule_list(jsonb, text) IS '계산 규칙 목록 JSONB 계약 검증. 최종 규칙에는 pool_refs를 허용하지 않는다. p_owner는 LOCAL만 허용';

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

COMMENT ON FUNCTION db_pipeline.fn_valid_relation_list(jsonb, text) IS '혜택 관계 목록 JSONB 계약 검증. 자기 참조, relation_key 중복, 같은 대상·유형 중복, 제거된 trigger_pool_id 거부';

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

CREATE SEQUENCE db_pipeline.seq_card_extr_stg
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 999999
    CACHE 1
    CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_extr_stg IS 'AI 추출 staging ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_source_evidence INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_source_evidence IS 'card_source_evidence.evidence_id 로컬 업무 ID 발급';

CREATE SEQUENCE db_pipeline.seq_card_product AS bigint
    START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1 NO CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_product IS 'card_product.card_id bigint 발급; 원본 백업에는 상품 마스터 시퀀스가 없음';

CREATE SEQUENCE db_pipeline.seq_card_evidence_link INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE db_pipeline.seq_card_evidence_link IS 'card_evidence_link.ev_link_id 로컬 업무 ID 발급';

-- ---------------------------------------------------------------------------
-- 공통코드 영역
-- ---------------------------------------------------------------------------
CREATE TABLE db_pipeline.common_code_grp (
    common_code_grp_id varchar(20) NOT NULL,
    common_code_grp_nm text NOT NULL,
    create_date timestamptz DEFAULT now() NOT NULL,
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz DEFAULT now() NOT NULL,
    update_user_id varchar(50) NOT NULL,
    common_code_grp_desc text,
    CONSTRAINT pk_common_code_grp
        PRIMARY KEY (common_code_grp_id)
);

COMMENT ON TABLE db_pipeline.common_code_grp IS '공통코드 그룹';
COMMENT ON COLUMN db_pipeline.common_code_grp.common_code_grp_id IS '공통코드 그룹 아이디';
COMMENT ON COLUMN db_pipeline.common_code_grp.common_code_grp_nm IS '공통코드 그룹명';
COMMENT ON COLUMN db_pipeline.common_code_grp.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.common_code_grp.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.common_code_grp.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.common_code_grp.update_user_id IS '수정 사용자 아이디';
COMMENT ON COLUMN db_pipeline.common_code_grp.common_code_grp_desc IS '공통코드 그룹 상세 설명(목적, 사용 범위, 업무 의미)';

CREATE TABLE db_pipeline.common_cd (
    common_code_grp_id varchar(20) NOT NULL,
    common_cd varchar(40) NOT NULL,
    common_cd_nm text NOT NULL,
    create_date timestamptz DEFAULT now() NOT NULL,
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz DEFAULT now() NOT NULL,
    update_user_id varchar(50) NOT NULL,
    common_cd_desc text,
    CONSTRAINT pk_common_cd
        PRIMARY KEY (common_code_grp_id, common_cd)
);

COMMENT ON TABLE db_pipeline.common_cd IS '공통코드';
COMMENT ON COLUMN db_pipeline.common_cd.common_code_grp_id IS '공통코드 그룹 아이디';
COMMENT ON COLUMN db_pipeline.common_cd.common_cd IS '공통코드';
COMMENT ON COLUMN db_pipeline.common_cd.common_cd_nm IS '공통코드명';
COMMENT ON COLUMN db_pipeline.common_cd.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.common_cd.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.common_cd.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.common_cd.update_user_id IS '수정 사용자 아이디';
COMMENT ON COLUMN db_pipeline.common_cd.common_cd_desc IS '공통코드 상세 설명(업무 의미, 적용 기준)';

-- ---------------------------------------------------------------------------
-- 상품 영역
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
    card_cond_expr jsonb,
    card_cond_status_cd varchar(20) NOT NULL DEFAULT 'DRAFT',
    CONSTRAINT card_product_pkey PRIMARY KEY (card_id),
    CONSTRAINT card_product_product_cd_key UNIQUE (product_cd),
    CONSTRAINT card_product_dates_check CHECK
        (discontinued_on IS NULL OR launched_on IS NULL OR discontinued_on >= launched_on),
    CONSTRAINT card_product_brand_opt_list_check CHECK (db_pipeline.fn_valid_brand_opt_list(brand_opt_list)),
    CONSTRAINT card_product_card_cond_expr_check CHECK (db_pipeline.fn_valid_cond_expr(card_cond_expr))
);

COMMENT ON TABLE db_pipeline.card_product IS '카드 상품';
COMMENT ON COLUMN db_pipeline.card_product.card_id IS '카드 아이디';
COMMENT ON COLUMN db_pipeline.card_product.product_cd IS '상품 코드';
COMMENT ON COLUMN db_pipeline.card_product.product_nm IS '상품명';
COMMENT ON COLUMN db_pipeline.card_product.issuer IS '카드사';
COMMENT ON COLUMN db_pipeline.card_product.card_kind_cd IS '카드 구분';
COMMENT ON COLUMN db_pipeline.card_product.product_status_cd IS '상품 상태';
COMMENT ON COLUMN db_pipeline.card_product.launched_on IS '출시일';
COMMENT ON COLUMN db_pipeline.card_product.discontinued_on IS '판매 중단일';
COMMENT ON COLUMN db_pipeline.card_product.brand_opt_list IS '브랜드 선택지 목록';
COMMENT ON COLUMN db_pipeline.card_product.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_product.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_product.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_product.update_user_id IS '수정 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_product.card_cond_expr IS '카드 공통 조건';
COMMENT ON COLUMN db_pipeline.card_product.card_cond_status_cd IS '카드 공통 조건 상태';

CREATE TABLE db_pipeline.card_product_doc (
    card_id bigint NOT NULL,
    card_doc_id varchar(20) NOT NULL,
    doc_role_cd varchar(20) NOT NULL,
    brand_opt_cds text[],
    approval_status_cd varchar(20) NOT NULL DEFAULT 'PENDING',
    applicability_basis_txt text NOT NULL,
    approval_note text,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT card_product_doc_pkey PRIMARY KEY (card_id, card_doc_id),
    CONSTRAINT card_product_doc_brand_check CHECK
        (doc_role_cd <> 'BRAND_SERVICE' OR coalesce(cardinality(brand_opt_cds), 0) > 0),
    CONSTRAINT card_product_doc_approved_check CHECK
        (approval_status_cd <> 'APPROVED' OR length(trim(applicability_basis_txt)) > 0)
);

COMMENT ON TABLE db_pipeline.card_product_doc IS '상품별 문서 관계';
COMMENT ON COLUMN db_pipeline.card_product_doc.card_id IS '카드 아이디';
COMMENT ON COLUMN db_pipeline.card_product_doc.card_doc_id IS '문서 아이디';
COMMENT ON COLUMN db_pipeline.card_product_doc.doc_role_cd IS '문서 역할';
COMMENT ON COLUMN db_pipeline.card_product_doc.brand_opt_cds IS '적용 브랜드 선택지';
COMMENT ON COLUMN db_pipeline.card_product_doc.approval_status_cd IS '승인 상태';
COMMENT ON COLUMN db_pipeline.card_product_doc.applicability_basis_txt IS '적용 근거';
COMMENT ON COLUMN db_pipeline.card_product_doc.approval_note IS '승인 메모';
COMMENT ON COLUMN db_pipeline.card_product_doc.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_product_doc.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_product_doc.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_product_doc.update_user_id IS '수정 사용자 아이디';

-- ---------------------------------------------------------------------------
-- 상품 혜택 영역. 규칙과 혜택 관계는 JSONB, 혜택 설명과 한도는 원문 기반 TEXT로 저장
-- ---------------------------------------------------------------------------
CREATE TABLE db_pipeline.card_bnft (
    card_id bigint NOT NULL,
    card_bnft_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_bnft') NOT NULL,
    bnft_cd varchar(80) NOT NULL,
    bnft_nm text NOT NULL,
    bnft_type_cd varchar(20) NOT NULL,
    bnft_origin_cd varchar(20) NOT NULL,
    bnft_scope_cd varchar(20) NOT NULL,
    bnft_brand_opt_cds text[],
    bnft_cond_expr jsonb,
    rule_select_cd varchar(30),
    rule_list jsonb NOT NULL DEFAULT '[]'::jsonb,
    relation_list jsonb NOT NULL DEFAULT '[]'::jsonb,
    verification_status_cd varchar(25) NOT NULL,
    bnft_valid_from date,
    bnft_valid_to_excl date,
    bnft_rule_txt text,
    bnft_limit_txt text,
    PRIMARY KEY (card_id, card_bnft_id),
    UNIQUE (card_id, bnft_cd),
    CONSTRAINT card_bnft_ck_1 CHECK
        ((bnft_scope_cd = 'PRODUCT' AND bnft_brand_opt_cds IS NULL)
         OR (bnft_scope_cd <> 'PRODUCT' AND coalesce(cardinality(bnft_brand_opt_cds), 0) > 0)),
    CONSTRAINT card_bnft_ck_2 CHECK (db_pipeline.fn_valid_cond_expr(bnft_cond_expr)),
    CONSTRAINT card_bnft_ck_3 CHECK (db_pipeline.fn_valid_rule_list(rule_list, 'LOCAL')),
    CONSTRAINT card_bnft_ck_4 CHECK (db_pipeline.fn_valid_relation_list(relation_list, card_bnft_id)),
    CONSTRAINT card_bnft_ck_5 CHECK (bnft_origin_cd <> 'BRAND_SERVICE' OR bnft_scope_cd = 'BRAND'),
    CONSTRAINT card_bnft_ck_6 CHECK
        (bnft_valid_to_excl IS NULL OR bnft_valid_from IS NULL OR bnft_valid_to_excl > bnft_valid_from)
);

COMMENT ON TABLE db_pipeline.card_bnft IS '카드 혜택';
COMMENT ON COLUMN db_pipeline.card_bnft.card_id IS '카드 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft.card_bnft_id IS '혜택 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_cd IS '혜택 코드';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_nm IS '혜택명';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_type_cd IS '혜택 유형';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_origin_cd IS '혜택 출처';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_scope_cd IS '혜택 적용 범위';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_brand_opt_cds IS '적용 브랜드 선택지';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_cond_expr IS '혜택 적용 조건';
COMMENT ON COLUMN db_pipeline.card_bnft.rule_select_cd IS '규칙 선택 방식';
COMMENT ON COLUMN db_pipeline.card_bnft.rule_list IS '계산 규칙 목록';
COMMENT ON COLUMN db_pipeline.card_bnft.relation_list IS '혜택 관계 목록';
COMMENT ON COLUMN db_pipeline.card_bnft.verification_status_cd IS '혜택 검증 상태';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_from IS '혜택 제공 시작일';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_to_excl IS '혜택 제공 종료일(미포함)';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_rule_txt IS '공식 원문 근거에서 모은 혜택 계산 규칙 안내. 계산 확정값이 아니라 검토 대상 텍스트';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_limit_txt IS '원문 근거에서 모은 혜택별 이용/금액 한도. 여러 풀의 근거를 혜택별로 중복 제거한 텍스트';

-- ---------------------------------------------------------------------------
-- 근거 연결 영역
-- ---------------------------------------------------------------------------
CREATE TABLE db_pipeline.card_evidence_link (
    card_id bigint NOT NULL,
    ev_link_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_evidence_link') NOT NULL,
    ev_subject_cd varchar(10) NOT NULL,
    card_bnft_id varchar(20),
    rule_key varchar(40),
    relation_key varchar(40),
    ev_item_cd varchar(10) NOT NULL DEFAULT 'SELF',
    ev_item_key varchar(100) NOT NULL DEFAULT '-',
    evidence_id varchar(20) NOT NULL,
    PRIMARY KEY (card_id, ev_link_id),
    CONSTRAINT card_evidence_link_natural_key UNIQUE NULLS NOT DISTINCT
        (card_id, ev_subject_cd, card_bnft_id, rule_key, relation_key,
         ev_item_cd, ev_item_key, evidence_id),
    CONSTRAINT card_evidence_link_ck_1 CHECK ((ev_item_cd = 'SELF') = (ev_item_key = '-')),
    CONSTRAINT card_evidence_link_ck_2 CHECK (
        CASE ev_subject_cd
            WHEN 'CARD' THEN num_nonnulls(card_bnft_id, rule_key, relation_key) = 0
            WHEN 'BNFT' THEN card_bnft_id IS NOT NULL AND num_nonnulls(rule_key, relation_key) = 0
            WHEN 'RULE' THEN card_bnft_id IS NOT NULL AND rule_key IS NOT NULL AND relation_key IS NULL
            WHEN 'REL' THEN card_bnft_id IS NOT NULL AND relation_key IS NOT NULL AND rule_key IS NULL
            ELSE false
        END)
);

COMMENT ON TABLE db_pipeline.card_evidence_link IS '카드 근거 관계';
COMMENT ON COLUMN db_pipeline.card_evidence_link.card_id IS '카드 아이디';
COMMENT ON COLUMN db_pipeline.card_evidence_link.ev_link_id IS '근거 연결 아이디';
COMMENT ON COLUMN db_pipeline.card_evidence_link.ev_subject_cd IS '근거 대상 유형';
COMMENT ON COLUMN db_pipeline.card_evidence_link.card_bnft_id IS '혜택 아이디';
COMMENT ON COLUMN db_pipeline.card_evidence_link.rule_key IS '규칙 키';
COMMENT ON COLUMN db_pipeline.card_evidence_link.relation_key IS '혜택 관계 키';
COMMENT ON COLUMN db_pipeline.card_evidence_link.ev_item_cd IS '근거 항목 유형';
COMMENT ON COLUMN db_pipeline.card_evidence_link.ev_item_key IS '근거 항목 키';
COMMENT ON COLUMN db_pipeline.card_evidence_link.evidence_id IS '원문 근거 아이디';

-- ---------------------------------------------------------------------------
-- 원천 문서·AI 파싱·근거 영역. 코드 열거 CHECK만 공통코드로 이관
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
    CONSTRAINT card_doc_doc_version_no_check CHECK ((doc_version_no > 0)),
    CONSTRAINT card_doc_family_cd_check CHECK (doc_family_cd IS NULL OR doc_family_cd ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]*$'),
    CONSTRAINT card_doc_pkey PRIMARY KEY (card_doc_id),
    CONSTRAINT card_doc_doc_cd_key UNIQUE (doc_cd),
    CONSTRAINT card_doc_doc_sha256_key UNIQUE (doc_sha256)
);

COMMENT ON TABLE db_pipeline.card_doc IS '원천 문서';
COMMENT ON COLUMN db_pipeline.card_doc.card_doc_id IS '문서 아이디';
COMMENT ON COLUMN db_pipeline.card_doc.card_id IS '카드 아이디';
COMMENT ON COLUMN db_pipeline.card_doc.doc_cd IS '문서 코드';
COMMENT ON COLUMN db_pipeline.card_doc.doc_type_cd IS '문서 유형';
COMMENT ON COLUMN db_pipeline.card_doc.doc_family_cd IS '문서 계열 코드';
COMMENT ON COLUMN db_pipeline.card_doc.doc_title IS '문서 제목';
COMMENT ON COLUMN db_pipeline.card_doc.doc_source_url IS '문서 출처 URL';
COMMENT ON COLUMN db_pipeline.card_doc.doc_file_nm IS '파일명';
COMMENT ON COLUMN db_pipeline.card_doc.doc_file_size IS '파일 크기';
COMMENT ON COLUMN db_pipeline.card_doc.doc_sha256 IS '파일 해시';
COMMENT ON COLUMN db_pipeline.card_doc.doc_page_cnt IS '페이지 수';
COMMENT ON COLUMN db_pipeline.card_doc.doc_review_no IS '심의 번호';
COMMENT ON COLUMN db_pipeline.card_doc.doc_review_date IS '심의일';
COMMENT ON COLUMN db_pipeline.card_doc.doc_release_date IS '문서 발행일';
COMMENT ON COLUMN db_pipeline.card_doc.doc_collect_date IS '수집 일시';
COMMENT ON COLUMN db_pipeline.card_doc.doc_version_no IS '문서 버전 번호';
COMMENT ON COLUMN db_pipeline.card_doc.doc_status IS '문서 상태';
COMMENT ON COLUMN db_pipeline.card_doc.doc_note IS '문서 메모';
COMMENT ON COLUMN db_pipeline.card_doc.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_doc.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_doc.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_doc.update_user_id IS '수정 사용자 아이디';

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

COMMENT ON TABLE db_pipeline.card_doc_page IS '문서 페이지';
COMMENT ON COLUMN db_pipeline.card_doc_page.card_doc_id IS '문서 아이디';
COMMENT ON COLUMN db_pipeline.card_doc_page.page_no IS '페이지 번호';
COMMENT ON COLUMN db_pipeline.card_doc_page.page_raw_txt IS '페이지 원문';
COMMENT ON COLUMN db_pipeline.card_doc_page.page_char_cnt IS '페이지 문자 수';
COMMENT ON COLUMN db_pipeline.card_doc_page.page_txt_sha256 IS '페이지 원문 해시';
COMMENT ON COLUMN db_pipeline.card_doc_page.page_layer_cd IS '텍스트 레이어 유형';
COMMENT ON COLUMN db_pipeline.card_doc_page.page_extractor_nm IS '추출기명';
COMMENT ON COLUMN db_pipeline.card_doc_page.page_extractor_ver IS '추출기 버전';
COMMENT ON COLUMN db_pipeline.card_doc_page.page_note IS '페이지 메모';
COMMENT ON COLUMN db_pipeline.card_doc_page.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_doc_page.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_doc_page.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_doc_page.update_user_id IS '수정 사용자 아이디';

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

COMMENT ON TABLE db_pipeline.card_doc_chunk IS '문서 청크';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.card_doc_id IS '문서 아이디';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.page_no IS '페이지 번호';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.card_doc_chunk_id IS '청크 아이디';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_seq IS '청크 순번';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_section_nm IS '절 제목';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_type_cd IS '청크 유형';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_start_pos IS '청크 시작 위치';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_end_pos IS '청크 종료 위치';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_raw_txt IS '청크 원문';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_clean_txt IS '청크 정제문';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_status IS '청크 상태';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_split_rule_ver IS '청크 분리 규칙 버전';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.chunk_clean_rule_ver IS '청크 정제 규칙 버전';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_doc_chunk.update_user_id IS '수정 사용자 아이디';

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

COMMENT ON TABLE db_pipeline.card_ai_run IS 'AI 실행 이력';
COMMENT ON COLUMN db_pipeline.card_ai_run.card_ai_run_id IS 'AI 실행 아이디';
COMMENT ON COLUMN db_pipeline.card_ai_run.run_stage_cd IS '실행 단계';
COMMENT ON COLUMN db_pipeline.card_ai_run.run_call_mthd_cd IS 'AI 호출 방식';
COMMENT ON COLUMN db_pipeline.card_ai_run.run_model_nm IS '모델명';
COMMENT ON COLUMN db_pipeline.card_ai_run.run_prompt_ver IS '프롬프트 버전';
COMMENT ON COLUMN db_pipeline.card_ai_run.run_prompt_txt IS '프롬프트 원문';
COMMENT ON COLUMN db_pipeline.card_ai_run.run_param IS '모델 파라미터';
COMMENT ON COLUMN db_pipeline.card_ai_run.run_target_card_doc_id IS '대상 문서 아이디';
COMMENT ON COLUMN db_pipeline.card_ai_run.run_status IS '실행 상태';
COMMENT ON COLUMN db_pipeline.card_ai_run.run_start_date IS '실행 시작 일시';
COMMENT ON COLUMN db_pipeline.card_ai_run.run_end_date IS '실행 종료 일시';
COMMENT ON COLUMN db_pipeline.card_ai_run.run_note IS '실행 메모';
COMMENT ON COLUMN db_pipeline.card_ai_run.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_ai_run.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_ai_run.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_ai_run.update_user_id IS '수정 사용자 아이디';

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

COMMENT ON TABLE db_pipeline.card_ai_call IS 'AI 호출 이력';
COMMENT ON COLUMN db_pipeline.card_ai_call.card_ai_run_id IS 'AI 실행 아이디';
COMMENT ON COLUMN db_pipeline.card_ai_call.card_doc_id IS '문서 아이디';
COMMENT ON COLUMN db_pipeline.card_ai_call.page_no IS '페이지 번호';
COMMENT ON COLUMN db_pipeline.card_ai_call.card_doc_chunk_id IS '청크 아이디';
COMMENT ON COLUMN db_pipeline.card_ai_call.call_seq IS '호출 순번';
COMMENT ON COLUMN db_pipeline.card_ai_call.call_input_sha256 IS '호출 입력 해시';
COMMENT ON COLUMN db_pipeline.card_ai_call.call_status IS '호출 상태';
COMMENT ON COLUMN db_pipeline.card_ai_call.call_resp_raw IS '응답 원문';
COMMENT ON COLUMN db_pipeline.card_ai_call.call_resp_json IS '응답 JSON';
COMMENT ON COLUMN db_pipeline.card_ai_call.call_error_msg IS '오류 메시지';
COMMENT ON COLUMN db_pipeline.card_ai_call.call_input_token_cnt IS '입력 토큰 수';
COMMENT ON COLUMN db_pipeline.card_ai_call.call_output_token_cnt IS '출력 토큰 수';
COMMENT ON COLUMN db_pipeline.card_ai_call.call_latency_ms IS '응답 시간';
COMMENT ON COLUMN db_pipeline.card_ai_call.call_req_date IS '요청 일시';
COMMENT ON COLUMN db_pipeline.card_ai_call.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_ai_call.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_ai_call.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_ai_call.update_user_id IS '수정 사용자 아이디';

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
    CONSTRAINT card_extr_stg_check1 CHECK ((((stg_status)::text <> ALL ((ARRAY['AUTO_APPROVED'::character varying, 'MANUAL_APPROVED'::character varying])::text[])) OR ((stg_normalized_item IS NOT NULL) AND (NOT ((stg_sql_check_cd)::text IS DISTINCT FROM 'OK'::text)) AND (stg_evidence_start_pos IS NOT NULL) AND (stg_evidence_end_pos IS NOT NULL) AND (btrim(stg_evidence_txt) <> ''::text)))),
    CONSTRAINT card_extr_stg_stg_item_seq_check CHECK ((stg_item_seq > 0))
);

COMMENT ON TABLE db_pipeline.card_extr_stg IS 'AI 추출 항목';
COMMENT ON COLUMN db_pipeline.card_extr_stg.card_ai_run_id IS 'AI 실행 아이디';
COMMENT ON COLUMN db_pipeline.card_extr_stg.card_doc_id IS '문서 아이디';
COMMENT ON COLUMN db_pipeline.card_extr_stg.page_no IS '페이지 번호';
COMMENT ON COLUMN db_pipeline.card_extr_stg.card_doc_chunk_id IS '청크 아이디';
COMMENT ON COLUMN db_pipeline.card_extr_stg.call_seq IS '호출 순번';
COMMENT ON COLUMN db_pipeline.card_extr_stg.card_extr_stg_id IS '추출 항목 아이디';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_item_seq IS '추출 항목 순번';
COMMENT ON COLUMN db_pipeline.card_extr_stg.card_id IS '카드 아이디(NULL이면 특정 카드에 연결되지 않은 후보)';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_kind_cd IS '추출 항목 종류';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_parent_card_extr_stg_id IS '상위 추출 항목 아이디';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_raw_item IS '추출 원본';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_normalized_item IS '정제 항목';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_txt IS '추출 근거 문장';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_start_pos IS '근거 시작 위치';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_evidence_end_pos IS '근거 종료 위치';
COMMENT ON COLUMN db_pipeline.card_extr_stg.card_excl_item_id IS '제외 항목 아이디';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_sql_check_cd IS 'SQL 검증 결과';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_ai_vrfy_cd IS 'AI 검증 결과';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_ai_vrfy_card_ai_run_id IS 'AI 검증 실행 아이디';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_status IS '검토 상태';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_review_note IS '검토 메모';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_approved_date IS '승인 일시';
COMMENT ON COLUMN db_pipeline.card_extr_stg.stg_approved_user_id IS '승인 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_extr_stg.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_extr_stg.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_extr_stg.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_extr_stg.update_user_id IS '수정 사용자 아이디';

CREATE TABLE db_pipeline.card_excl_item (
    card_excl_item_id character varying(20) DEFAULT db_pipeline.fn_get_biz_id('card_excl_item'::text) NOT NULL,
    issuer text NOT NULL,
    excl_item_nm text NOT NULL,
    excl_concept_cd character varying(50),
    excl_item_desc text,
    excl_alias_nms text[] NOT NULL DEFAULT '{}'::text[],
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL
);

COMMENT ON TABLE db_pipeline.card_excl_item IS '제외 항목 사전';
COMMENT ON COLUMN db_pipeline.card_excl_item.card_excl_item_id IS '제외 항목 아이디';
COMMENT ON COLUMN db_pipeline.card_excl_item.issuer IS '카드사';
COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_nm IS '제외 항목명';
COMMENT ON COLUMN db_pipeline.card_excl_item.excl_concept_cd IS '제외 분류 개념';
COMMENT ON COLUMN db_pipeline.card_excl_item.excl_item_desc IS '제외 항목 설명';
COMMENT ON COLUMN db_pipeline.card_excl_item.create_date IS '생성 일시';
COMMENT ON COLUMN db_pipeline.card_excl_item.create_user_id IS '생성 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_excl_item.update_date IS '수정 일시';
COMMENT ON COLUMN db_pipeline.card_excl_item.update_user_id IS '수정 사용자 아이디';
COMMENT ON COLUMN db_pipeline.card_excl_item.excl_alias_nms IS '제외 항목 별칭';

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

COMMENT ON TABLE db_pipeline.card_source_evidence IS '원문 근거';
COMMENT ON COLUMN db_pipeline.card_source_evidence.evidence_id IS '원문 근거 아이디';
COMMENT ON COLUMN db_pipeline.card_source_evidence.card_doc_id IS '문서 아이디';
COMMENT ON COLUMN db_pipeline.card_source_evidence.page_no IS '페이지 번호';
COMMENT ON COLUMN db_pipeline.card_source_evidence.card_doc_chunk_id IS '청크 아이디';
COMMENT ON COLUMN db_pipeline.card_source_evidence.card_extr_stg_id IS '추출 항목 아이디';
COMMENT ON COLUMN db_pipeline.card_source_evidence.quote_txt IS '원문 인용 문장';
COMMENT ON COLUMN db_pipeline.card_source_evidence.start_pos IS '인용 시작 위치';
COMMENT ON COLUMN db_pipeline.card_source_evidence.end_pos IS '인용 종료 위치';
COMMENT ON COLUMN db_pipeline.card_source_evidence.approval_status_cd IS '승인 상태';

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

CREATE INDEX ix_card_bnft_brand_opt_gin ON db_pipeline.card_bnft USING gin (bnft_brand_opt_cds);

CREATE INDEX ix_card_bnft_rule_list_gin ON db_pipeline.card_bnft USING gin (rule_list jsonb_path_ops);

CREATE INDEX ix_card_bnft_relation_list_gin ON db_pipeline.card_bnft USING gin (relation_list jsonb_path_ops);

CREATE INDEX ix_card_bnft_cond_gin ON db_pipeline.card_bnft USING gin (bnft_cond_expr jsonb_path_ops);

CREATE INDEX ix_card_excl_item_alias_gin ON db_pipeline.card_excl_item USING gin (excl_alias_nms);

CREATE INDEX ix_card_source_evidence_lookup ON db_pipeline.card_source_evidence (card_doc_id, page_no, card_doc_chunk_id);

CREATE INDEX ix_card_evidence_link_subject ON db_pipeline.card_evidence_link (card_id, ev_subject_cd, card_bnft_id, rule_key);

CREATE INDEX ix_card_evidence_link_evidence ON db_pipeline.card_evidence_link (evidence_id);

-- ---------------------------------------------------------------------------
-- 조회 뷰. JSONB를 V5와 같은 행 구조로 복원해 SQL 검증과 Neo4j 적재에 사용
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

COMMENT ON VIEW db_pipeline.v_card_brand_opt IS '상품별 브랜드 선택지를 행으로 복원';

CREATE VIEW db_pipeline.v_card_rule AS
SELECT b.card_id, b.card_bnft_id,
       r.value->>'rule_key' AS rule_key,
       r.ord AS rule_seq,
       nullif(r.value->'cond_expr', 'null'::jsonb) AS cond_expr,
       db_pipeline.fn_cond_spend_bound(nullif(r.value->'cond_expr', 'null'::jsonb), 'cond_min_amt')::numeric(18,2) AS spend_min_amt,
       db_pipeline.fn_cond_spend_bound(nullif(r.value->'cond_expr', 'null'::jsonb), 'cond_max_amt_excl')::numeric(18,2) AS spend_max_amt_excl,
       coalesce(r.value->'target_list', '[]'::jsonb) AS target_list,
       r.value->>'predicate_state_cd' AS predicate_state_cd,
       r.value->>'calc_method_cd' AS calc_method_cd,
       (r.value->>'method_ver')::integer AS method_ver,
       (r.value->>'value_num')::numeric(18,4) AS value_num,
       r.value->>'value_unit_cd' AS value_unit_cd,
       r.value->>'payout_unit_cd' AS payout_unit_cd,
       (r.value->>'basis_amt')::numeric(18,2) AS basis_amt,
       nullif(r.value->'calc_params', 'null'::jsonb) AS calc_params,
       (r.value->>'rule_priority')::integer AS rule_priority,
       r.value->>'rule_status_cd' AS rule_status_cd
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) WITH ORDINALITY AS r(value, ord);

COMMENT ON VIEW db_pipeline.v_card_rule IS '상품 계산 규칙을 행으로 복원. V5 card_bnft_rule 조회 대체';

CREATE VIEW db_pipeline.v_card_bnft_rel AS
SELECT b.card_id, b.card_bnft_id AS from_bnft_id,
       x.value->>'to_bnft_id' AS to_bnft_id,
       x.value->>'relation_key' AS relation_key,
       x.value->>'rel_type_cd' AS rel_type_cd,
       (x.value->>'rel_priority')::integer AS rel_priority,
       false AS reverse_yn
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) AS x(value)
UNION ALL
SELECT b.card_id, x.value->>'to_bnft_id',
       b.card_bnft_id,
       x.value->>'relation_key',
       x.value->>'rel_type_cd',
       (x.value->>'rel_priority')::integer,
       true
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) AS x(value)
WHERE x.value->>'rel_type_cd' = 'MUTUALLY_EXCLUSIVE';

COMMENT ON VIEW db_pipeline.v_card_bnft_rel IS '혜택 관계를 행으로 복원. MUTUALLY_EXCLUSIVE는 reverse_yn=true 행을 더해 양방향 제공. 저장 행 조회는 reverse_yn=false';

CREATE VIEW db_pipeline.v_card_rule_target AS
SELECT r.card_id, r.card_bnft_id, r.rule_key,
       t.value->>'target_type_cd' AS target_type_cd,
       t.value->>'target_key' AS target_key,
       t.value->>'target_nm' AS target_nm
FROM db_pipeline.v_card_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.target_list) AS t(value);

COMMENT ON VIEW db_pipeline.v_card_rule_target IS '규칙 대상을 행으로 복원';

CREATE VIEW db_pipeline.v_card_cond_atom AS
WITH src AS (
    SELECT 'CARD'::text AS owner_cd, p.card_id, NULL::varchar AS card_bnft_id,
           NULL::text AS rule_key,
           p.card_cond_expr AS expr
    FROM db_pipeline.card_product p WHERE p.card_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'BNFT', b.card_id, b.card_bnft_id, NULL, b.bnft_cond_expr
    FROM db_pipeline.card_bnft b WHERE b.bnft_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'RULE', r.card_id, r.card_bnft_id, r.rule_key, r.cond_expr
    FROM db_pipeline.v_card_rule r WHERE r.cond_expr IS NOT NULL
)
SELECT s.owner_cd, s.card_id, s.card_bnft_id, s.rule_key,
       s.expr->>'expr_status_cd' AS expr_status_cd,
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

COMMENT ON VIEW db_pipeline.v_card_cond_atom IS '모든 조건식의 atom을 소유자와 함께 행으로 복원';

CREATE VIEW db_pipeline.v_card_bnft_rule_effective AS
SELECT b.card_id, b.card_bnft_id, b.bnft_nm, b.bnft_origin_cd, b.bnft_scope_cd, b.bnft_brand_opt_cds,
       b.bnft_valid_from, b.bnft_valid_to_excl, r.rule_key,
       r.calc_method_cd, r.method_ver, r.value_num, r.value_unit_cd, r.payout_unit_cd, r.basis_amt,
       r.calc_params, r.predicate_state_cd, r.target_list,
       b.bnft_cond_expr, r.cond_expr AS rule_cond_expr, r.rule_status_cd
FROM db_pipeline.card_bnft b
JOIN db_pipeline.v_card_rule r
  ON (r.card_id, r.card_bnft_id) = (b.card_id, b.card_bnft_id);

COMMENT ON VIEW db_pipeline.v_card_bnft_rule_effective IS '혜택과 계산 규칙의 단일 출력. 제공 기간은 걸러내지 않으므로 조회 기준일로 판정. 값은 정책 후보이며 거래별 보상액이 아님';

CREATE VIEW db_pipeline.v_common_cd_usage AS
SELECT 'card_product.card_kind_cd'::text AS source_nm, 'CARD_KIND'::varchar(20) AS common_code_grp_id, card_kind_cd::text AS cd_value
FROM db_pipeline.card_product WHERE card_kind_cd IS NOT NULL
UNION ALL
SELECT 'card_product.product_status_cd'::text AS source_nm, 'PRODUCT_STATUS'::varchar(20) AS common_code_grp_id, product_status_cd::text AS cd_value
FROM db_pipeline.card_product WHERE product_status_cd IS NOT NULL
UNION ALL
SELECT 'card_product.card_cond_status_cd'::text AS source_nm, 'ITEM_STATUS'::varchar(20) AS common_code_grp_id, card_cond_status_cd::text AS cd_value
FROM db_pipeline.card_product WHERE card_cond_status_cd IS NOT NULL
UNION ALL
SELECT 'card_product_doc.doc_role_cd'::text AS source_nm, 'DOC_ROLE'::varchar(20) AS common_code_grp_id, doc_role_cd::text AS cd_value
FROM db_pipeline.card_product_doc WHERE doc_role_cd IS NOT NULL
UNION ALL
SELECT 'card_product_doc.approval_status_cd'::text AS source_nm, 'APPROVAL_STATUS'::varchar(20) AS common_code_grp_id, approval_status_cd::text AS cd_value
FROM db_pipeline.card_product_doc WHERE approval_status_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.bnft_type_cd'::text AS source_nm, 'BNFT_TYPE'::varchar(20) AS common_code_grp_id, bnft_type_cd::text AS cd_value
FROM db_pipeline.card_bnft WHERE bnft_type_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.bnft_origin_cd'::text AS source_nm, 'BNFT_ORIGIN'::varchar(20) AS common_code_grp_id, bnft_origin_cd::text AS cd_value
FROM db_pipeline.card_bnft WHERE bnft_origin_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.bnft_scope_cd'::text AS source_nm, 'BNFT_SCOPE'::varchar(20) AS common_code_grp_id, bnft_scope_cd::text AS cd_value
FROM db_pipeline.card_bnft WHERE bnft_scope_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_select_cd'::text AS source_nm, 'RULE_SELECT'::varchar(20) AS common_code_grp_id, rule_select_cd::text AS cd_value
FROM db_pipeline.card_bnft WHERE rule_select_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.verification_status_cd'::text AS source_nm, 'VERIFY_STATUS'::varchar(20) AS common_code_grp_id, verification_status_cd::text AS cd_value
FROM db_pipeline.card_bnft WHERE verification_status_cd IS NOT NULL
UNION ALL
SELECT 'card_source_evidence.approval_status_cd'::text AS source_nm, 'APPROVAL_STATUS'::varchar(20) AS common_code_grp_id, approval_status_cd::text AS cd_value
FROM db_pipeline.card_source_evidence WHERE approval_status_cd IS NOT NULL
UNION ALL
SELECT 'card_evidence_link.ev_subject_cd'::text AS source_nm, 'EV_SUBJECT'::varchar(20) AS common_code_grp_id, ev_subject_cd::text AS cd_value
FROM db_pipeline.card_evidence_link WHERE ev_subject_cd IS NOT NULL
UNION ALL
SELECT 'card_evidence_link.ev_item_cd'::text AS source_nm, 'EV_ITEM'::varchar(20) AS common_code_grp_id, ev_item_cd::text AS cd_value
FROM db_pipeline.card_evidence_link WHERE ev_item_cd IS NOT NULL
UNION ALL
SELECT 'card_doc.doc_type_cd'::text AS source_nm, 'DOC_TYPE'::varchar(20) AS common_code_grp_id, doc_type_cd::text AS cd_value
FROM db_pipeline.card_doc WHERE doc_type_cd IS NOT NULL
UNION ALL
SELECT 'card_doc.doc_status'::text AS source_nm, 'DOC_STATUS'::varchar(20) AS common_code_grp_id, doc_status::text AS cd_value
FROM db_pipeline.card_doc WHERE doc_status IS NOT NULL
UNION ALL
SELECT 'card_doc_page.page_layer_cd'::text AS source_nm, 'PAGE_LAYER'::varchar(20) AS common_code_grp_id, page_layer_cd::text AS cd_value
FROM db_pipeline.card_doc_page WHERE page_layer_cd IS NOT NULL
UNION ALL
SELECT 'card_doc_chunk.chunk_type_cd'::text AS source_nm, 'CHUNK_TYPE'::varchar(20) AS common_code_grp_id, chunk_type_cd::text AS cd_value
FROM db_pipeline.card_doc_chunk WHERE chunk_type_cd IS NOT NULL
UNION ALL
SELECT 'card_doc_chunk.chunk_status'::text AS source_nm, 'CHUNK_STATUS'::varchar(20) AS common_code_grp_id, chunk_status::text AS cd_value
FROM db_pipeline.card_doc_chunk WHERE chunk_status IS NOT NULL
UNION ALL
SELECT 'card_ai_run.run_stage_cd'::text AS source_nm, 'RUN_STAGE'::varchar(20) AS common_code_grp_id, run_stage_cd::text AS cd_value
FROM db_pipeline.card_ai_run WHERE run_stage_cd IS NOT NULL
UNION ALL
SELECT 'card_ai_run.run_call_mthd_cd'::text AS source_nm, 'RUN_CALL_METHOD'::varchar(20) AS common_code_grp_id, run_call_mthd_cd::text AS cd_value
FROM db_pipeline.card_ai_run WHERE run_call_mthd_cd IS NOT NULL
UNION ALL
SELECT 'card_ai_run.run_status'::text AS source_nm, 'RUN_STATUS'::varchar(20) AS common_code_grp_id, run_status::text AS cd_value
FROM db_pipeline.card_ai_run WHERE run_status IS NOT NULL
UNION ALL
SELECT 'card_ai_call.call_status'::text AS source_nm, 'CALL_STATUS'::varchar(20) AS common_code_grp_id, call_status::text AS cd_value
FROM db_pipeline.card_ai_call WHERE call_status IS NOT NULL
UNION ALL
SELECT 'card_extr_stg.stg_kind_cd'::text AS source_nm, 'STG_KIND'::varchar(20) AS common_code_grp_id, stg_kind_cd::text AS cd_value
FROM db_pipeline.card_extr_stg WHERE stg_kind_cd IS NOT NULL
UNION ALL
SELECT 'card_extr_stg.stg_status'::text AS source_nm, 'STG_STATUS'::varchar(20) AS common_code_grp_id, stg_status::text AS cd_value
FROM db_pipeline.card_extr_stg WHERE stg_status IS NOT NULL
UNION ALL
SELECT 'card_extr_stg.stg_ai_vrfy_cd'::text AS source_nm, 'STG_AI_VRFY'::varchar(20) AS common_code_grp_id, stg_ai_vrfy_cd::text AS cd_value
FROM db_pipeline.card_extr_stg WHERE stg_ai_vrfy_cd IS NOT NULL
UNION ALL
SELECT 'card_product.brand_opt_list[].brand_cd', 'BRAND', brand_cd::text
FROM db_pipeline.v_card_brand_opt WHERE brand_cd IS NOT NULL
UNION ALL
SELECT 'card_product.brand_opt_list[].service_grade_cd', 'SERVICE_GRADE', service_grade_cd::text
FROM db_pipeline.v_card_brand_opt WHERE service_grade_cd IS NOT NULL
UNION ALL
SELECT 'card_product.brand_opt_list[].service_type_cd', 'SERVICE_TYPE', service_type_cd::text
FROM db_pipeline.v_card_brand_opt WHERE service_type_cd IS NOT NULL
UNION ALL
SELECT 'card_product.brand_opt_list[].brand_opt_status_cd', 'PRODUCT_STATUS', brand_opt_status_cd::text
FROM db_pipeline.v_card_brand_opt WHERE brand_opt_status_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_list[].predicate_state_cd', 'PREDICATE_STATE', predicate_state_cd::text
FROM db_pipeline.v_card_rule WHERE predicate_state_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_list[].calc_method_cd', 'CALC_METHOD', calc_method_cd::text
FROM db_pipeline.v_card_rule WHERE calc_method_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_list[].value_unit_cd', 'VALUE_UNIT', value_unit_cd::text
FROM db_pipeline.v_card_rule WHERE value_unit_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_list[].payout_unit_cd', 'PAYOUT_UNIT', payout_unit_cd::text
FROM db_pipeline.v_card_rule WHERE payout_unit_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_list[].rule_status_cd', 'ITEM_STATUS', rule_status_cd::text
FROM db_pipeline.v_card_rule WHERE rule_status_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.relation_list[].rel_type_cd', 'REL_TYPE', rel_type_cd::text
FROM db_pipeline.v_card_bnft_rel WHERE rel_type_cd IS NOT NULL AND NOT reverse_yn
UNION ALL
SELECT 'rule_list[].target_list[].target_type_cd', 'TARGET_TYPE', target_type_cd::text
FROM db_pipeline.v_card_rule_target WHERE target_type_cd IS NOT NULL
UNION ALL
SELECT 'cond_expr atom cond_type_cd', 'COND_TYPE', cond_type_cd::text
FROM db_pipeline.v_card_cond_atom WHERE cond_type_cd IS NOT NULL
UNION ALL
SELECT 'cond_expr atom cond_basis_cd', 'COND_BASIS', cond_basis_cd::text
FROM db_pipeline.v_card_cond_atom WHERE cond_basis_cd IS NOT NULL
UNION ALL
SELECT 'cond_expr atom predicate_method_cd', 'PREDICATE_METHOD', predicate_method_cd::text
FROM db_pipeline.v_card_cond_atom WHERE predicate_method_cd IS NOT NULL
UNION ALL
SELECT 'cond_expr atom cond_status_cd', 'ITEM_STATUS', cond_status_cd::text
FROM db_pipeline.v_card_cond_atom WHERE cond_status_cd IS NOT NULL
UNION ALL
SELECT 'cond_expr.expr_status_cd', 'ITEM_STATUS', expr_status_cd::text
FROM db_pipeline.v_card_cond_atom WHERE expr_status_cd IS NOT NULL;

COMMENT ON VIEW db_pipeline.v_common_cd_usage IS '모든 공통코드 사용처(물리 컬럼·JSONB 키)와 소속 그룹. 공통코드 정합성 검증의 기준';

CREATE VIEW db_pipeline.v_card_integrity_issue AS
WITH atoms AS (SELECT * FROM db_pipeline.v_card_cond_atom),
-- 방식별 필수값. 지급 단위는 포인트·마일리지일 수 있어 정액·금액당 방식의 단위를 특정 값으로 제한하지 않는다.
-- final_yn이 true면 확정 데이터의 무결성 위반, false면 확정 전 값 누락이다. 값을 보완하지 않고 구분만 한다.
rule_value_gap AS (
    SELECT r.card_id, r.card_bnft_id, r.rule_key,
           (r.rule_status_cd = 'CONFIRMED' OR b.verification_status_cd = 'CONFIRMED') AS final_yn
    FROM db_pipeline.v_card_rule r
    JOIN db_pipeline.card_bnft b ON (b.card_id, b.card_bnft_id) = (r.card_id, r.card_bnft_id)
    WHERE r.rule_status_cd <> 'RETIRED'
      AND ((r.calc_method_cd IN ('PERCENT_OF_TXN', 'FIXED_PER_TXN', 'UNITS_PER_AMOUNT', 'MULTIPLY_EXTERNAL_POINTS') AND r.value_num IS NULL)
           OR (r.calc_method_cd = 'UNITS_PER_AMOUNT' AND r.basis_amt IS NULL)
           OR (r.calc_method_cd = 'PERCENT_OF_TXN' AND r.value_unit_cd IS DISTINCT FROM 'PERCENT')
           OR (r.calc_method_cd = 'MULTIPLY_EXTERNAL_POINTS' AND r.value_unit_cd IS DISTINCT FROM 'MULTIPLIER')
           OR (r.calc_method_cd IN ('FIXED_PER_TXN', 'UNITS_PER_AMOUNT') AND r.value_unit_cd IN ('PERCENT', 'MULTIPLIER')))
),
-- 필수 파라미터가 정해진 판정 방식만 검사한다. cond_params를 모든 조건에 강제하지 않는다.
predicate_param_gap AS (
    SELECT a.owner_cd, a.card_id, a.atom_key,
           (a.cond_status_cd = 'CONFIRMED' OR a.expr_status_cd = 'CONFIRMED') AS final_yn
    FROM atoms a
    WHERE a.cond_status_cd <> 'RETIRED'
      AND ((a.predicate_method_cd = 'EVERY_MONTH_MIN_SPEND'
            AND (a.cond_min_amt IS NULL OR jsonb_typeof(a.cond_params->'window_months') IS DISTINCT FROM 'number'))
           OR (a.predicate_method_cd = 'MONTH_IN'
               AND CASE WHEN jsonb_typeof(a.cond_params->'months') = 'array'
                        THEN jsonb_array_length(a.cond_params->'months') = 0 ELSE true END))
),
fallback AS (
    SELECT card_id, from_bnft_id, to_bnft_id
    FROM db_pipeline.v_card_bnft_rel
    WHERE rel_type_cd = 'FALLBACK_AFTER_CAP' AND NOT reverse_yn
),
cycle AS (
    WITH RECURSIVE walk(card_id, start_id, cur_id, path) AS (
        SELECT card_id, from_bnft_id, to_bnft_id, ARRAY[from_bnft_id, to_bnft_id]
        FROM fallback
        UNION ALL
        SELECT w.card_id, w.start_id, f.to_bnft_id, w.path || f.to_bnft_id
        FROM walk w
        JOIN fallback f ON (f.card_id, f.from_bnft_id) = (w.card_id, w.cur_id)
        WHERE NOT f.to_bnft_id = ANY (w.path[2:])
    )
    SELECT DISTINCT card_id, start_id FROM walk WHERE cur_id = start_id
)
SELECT 'bnft_without_product' AS gate_cd, x.card_id || '/' || x.card_bnft_id AS issue_key
FROM db_pipeline.card_bnft x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = x.card_id)
UNION ALL
SELECT 'local_confirmed_without_rule', x.card_id || '/' || x.card_bnft_id
FROM db_pipeline.card_bnft x
WHERE x.verification_status_cd = 'CONFIRMED' AND jsonb_array_length(x.rule_list) = 0
UNION ALL
SELECT 'bnft_txt_without_evidence', x.card_id || '/' || x.card_bnft_id
FROM db_pipeline.card_bnft x
WHERE (x.bnft_rule_txt IS NOT NULL OR x.bnft_limit_txt IS NOT NULL)
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_evidence_link l
                  WHERE (l.card_id, l.card_bnft_id) = (x.card_id, x.card_bnft_id)
                    AND l.ev_subject_cd = 'BNFT' AND l.ev_item_cd = 'SELF')
UNION ALL
SELECT 'rel_to_bnft_orphan', x.card_id || '/' || x.relation_key
FROM db_pipeline.v_card_bnft_rel x
WHERE NOT x.reverse_yn
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id, b.card_bnft_id) = (x.card_id, x.to_bnft_id))
UNION ALL
SELECT 'rel_mutual_stored_twice', a.card_id || '/' || a.from_bnft_id || '/' || a.to_bnft_id
FROM db_pipeline.v_card_bnft_rel a
JOIN db_pipeline.v_card_bnft_rel b
  ON (a.card_id, a.from_bnft_id, a.to_bnft_id, a.rel_type_cd) = (b.card_id, b.to_bnft_id, b.from_bnft_id, b.rel_type_cd)
WHERE NOT a.reverse_yn AND NOT b.reverse_yn AND a.rel_type_cd = 'MUTUALLY_EXCLUSIVE' AND a.from_bnft_id < a.to_bnft_id
UNION ALL
SELECT 'rel_fallback_cycle', c.card_id || '/' || c.start_id FROM cycle c
UNION ALL
SELECT 'product_doc_without_product', x.card_id || '/' || x.card_doc_id
FROM db_pipeline.card_product_doc x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = x.card_id)
UNION ALL
SELECT 'product_doc_orphan', x.card_id || '/' || x.card_doc_id
FROM db_pipeline.card_product_doc x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc d WHERE d.card_doc_id = x.card_doc_id)
UNION ALL
SELECT 'bnft_brand_opt_unknown', b.card_id || '/' || b.card_bnft_id || '/' || o.cd
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) AS o(cd)
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.v_card_brand_opt v WHERE v.card_id = b.card_id AND v.brand_opt_cd = o.cd)
UNION ALL
SELECT 'doc_brand_opt_unknown', d.card_id || '/' || d.card_doc_id || '/' || o.cd
FROM db_pipeline.card_product_doc d
CROSS JOIN LATERAL unnest(d.brand_opt_cds) AS o(cd)
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.v_card_brand_opt v WHERE v.card_id = d.card_id AND v.brand_opt_cd = o.cd)
UNION ALL
SELECT CASE WHEN g.final_yn THEN 'rule_method_value_missing' ELSE 'rule_method_value_pending' END,
       g.card_id || '/' || g.card_bnft_id || '/' || g.rule_key
FROM rule_value_gap g
UNION ALL
SELECT CASE WHEN g.final_yn THEN 'predicate_params_missing' ELSE 'predicate_params_pending' END,
       g.owner_cd || '/' || g.card_id || '/' || g.atom_key
FROM predicate_param_gap g
UNION ALL
SELECT 'excl_item_unknown', a.owner_cd || '/' || a.atom_key
FROM atoms a
WHERE a.card_excl_item_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_excl_item i WHERE i.card_excl_item_id = a.card_excl_item_id)
UNION ALL
SELECT 'evidence_source_orphan', e.evidence_id
FROM db_pipeline.card_source_evidence e
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc_chunk c WHERE (c.card_doc_id, c.page_no, c.card_doc_chunk_id) = (e.card_doc_id, e.page_no, e.card_doc_chunk_id))
UNION ALL
SELECT 'evidence_doc_not_linked', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_evidence_link l
JOIN db_pipeline.card_source_evidence e USING (evidence_id)
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc d WHERE (d.card_id, d.card_doc_id) = (l.card_id, e.card_doc_id))
UNION ALL
SELECT 'evidence_not_approved', l.evidence_id
FROM (SELECT DISTINCT evidence_id FROM db_pipeline.card_evidence_link) l
LEFT JOIN db_pipeline.card_source_evidence e USING (evidence_id)
WHERE e.evidence_id IS NULL OR e.approval_status_cd <> 'APPROVED'
UNION ALL
SELECT 'evidence_subject_orphan', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_evidence_link l
WHERE NOT CASE l.ev_subject_cd
    WHEN 'CARD' THEN EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = l.card_id)
    WHEN 'BNFT' THEN EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id, b.card_bnft_id) = (l.card_id, l.card_bnft_id))
    WHEN 'RULE' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_rule r WHERE (r.card_id, r.card_bnft_id, r.rule_key) = (l.card_id, l.card_bnft_id, l.rule_key))
    WHEN 'REL' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_bnft_rel r WHERE NOT r.reverse_yn AND (r.card_id, r.from_bnft_id, r.relation_key) = (l.card_id, l.card_bnft_id, l.relation_key))
    ELSE false
END
UNION ALL
SELECT 'evidence_item_key_missing', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_evidence_link l
WHERE l.ev_item_cd <> 'SELF' AND NOT CASE l.ev_item_cd
    WHEN 'COND' THEN EXISTS (SELECT 1 FROM atoms a WHERE a.card_id = l.card_id AND a.atom_key = l.ev_item_key
                             AND a.card_bnft_id IS NOT DISTINCT FROM l.card_bnft_id AND a.rule_key IS NOT DISTINCT FROM l.rule_key)
    WHEN 'TARGET' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_rule_target t WHERE (t.card_id, t.card_bnft_id, t.rule_key) = (l.card_id, l.card_bnft_id, l.rule_key) AND t.target_key = l.ev_item_key)
    ELSE false
END
UNION ALL
SELECT 'product_doc_role_type_mismatch', x.card_id || '/' || x.card_doc_id
FROM db_pipeline.card_product_doc x
JOIN db_pipeline.card_doc d ON d.card_doc_id = x.card_doc_id
WHERE x.doc_role_cd = 'BRAND_SERVICE' AND d.doc_type_cd <> 'BRAND_SERVICE'
UNION ALL
SELECT 'shared_doc_bound_to_card', d.card_doc_id
FROM db_pipeline.card_doc d
WHERE d.card_id IS NOT NULL AND d.doc_type_cd IN ('BRAND_SERVICE', 'TERMS')
UNION ALL
SELECT 'brand_doc_option_conflict', z.card_doc_id
FROM (SELECT x.card_doc_id
      FROM db_pipeline.card_product_doc x
      CROSS JOIN LATERAL unnest(x.brand_opt_cds) AS o(cd)
      JOIN db_pipeline.v_card_brand_opt v ON (v.card_id, v.brand_opt_cd) = (x.card_id, o.cd)
      WHERE x.doc_role_cd = 'BRAND_SERVICE'
      GROUP BY 1 HAVING count(DISTINCT (v.brand_cd, v.service_grade_cd, v.service_type_cd)) > 1) z
UNION ALL
SELECT 'brand_bnft_doc_not_linked', b.card_id || '/' || b.card_bnft_id || '/' || o.cd
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL unnest(b.bnft_brand_opt_cds) AS o(cd)
WHERE b.bnft_origin_cd = 'BRAND_SERVICE'
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc x
                  WHERE x.card_id = b.card_id AND x.doc_role_cd = 'BRAND_SERVICE' AND o.cd = ANY (x.brand_opt_cds))
UNION ALL
SELECT 'brand_bnft_confirmed_without_evidence', b.card_id || '/' || b.card_bnft_id
FROM db_pipeline.card_bnft b
WHERE b.bnft_origin_cd = 'BRAND_SERVICE' AND b.verification_status_cd = 'CONFIRMED'
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_evidence_link l
                  WHERE (l.card_id, l.card_bnft_id) = (b.card_id, b.card_bnft_id))
UNION ALL
SELECT 'evidence_brand_opt_mismatch', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_evidence_link l
JOIN db_pipeline.card_source_evidence e USING (evidence_id)
JOIN db_pipeline.card_bnft b ON (b.card_id, b.card_bnft_id) = (l.card_id, l.card_bnft_id)
JOIN db_pipeline.card_product_doc x ON (x.card_id, x.card_doc_id) = (l.card_id, e.card_doc_id)
WHERE x.doc_role_cd = 'BRAND_SERVICE' AND NOT (coalesce(b.bnft_brand_opt_cds, '{}') && x.brand_opt_cds)
UNION ALL
SELECT 'stg_card_not_linked', s.card_extr_stg_id
FROM db_pipeline.card_extr_stg s
WHERE s.card_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc x WHERE (x.card_id, x.card_doc_id) = (s.card_id, s.card_doc_id))
UNION ALL
SELECT 'common_cd_invalid', u.source_nm || '=' || u.cd_value
FROM db_pipeline.v_common_cd_usage u
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd c WHERE (c.common_code_grp_id, c.common_cd) = (u.common_code_grp_id, u.cd_value))
UNION ALL
SELECT 'common_cd_group_orphan', c.common_code_grp_id || '/' || c.common_cd
FROM db_pipeline.common_cd c
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.common_code_grp g WHERE g.common_code_grp_id = c.common_code_grp_id)
UNION ALL
SELECT 'common_code_grp_empty', g.common_code_grp_id
FROM db_pipeline.common_code_grp g
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd c WHERE c.common_code_grp_id = g.common_code_grp_id);

COMMENT ON VIEW db_pipeline.v_card_integrity_issue IS '승인 전 정합성 게이트. 물리 FK가 없으므로 행이 1건이라도 있으면 승인하지 않음. *_pending은 확정 전 항목의 값 누락(검토 대기)이고 나머지는 무결성 위반';

-- Approval gate (must return 0 rows): SELECT gate_cd, count(*) FROM db_pipeline.v_card_integrity_issue GROUP BY 1;
-- Unused code review: see the V6 design report, section 11.
