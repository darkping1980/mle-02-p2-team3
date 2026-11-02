-- V7 -> V6 복구. db_pipeline_migration_V6_to_V7.sql 실행 직후의 상태를 이관 전 상태로 되돌린다.
-- db_pipeline_v6_backup 스키마가 필요하다. 이관 이후 새로 등록한 혜택·한도·근거가 있으면 실행하지 말고 먼저 검토한다.
-- 브랜드 혜택, 혜택 제공 기간, 카드 미연결 추출 항목은 V6에 담을 수 없으므로 있으면 중단한다.
-- 되돌린 뒤 policy_ver_id 컬럼의 물리 위치는 테이블 끝이 된다. 값과 키, 제약조건은 이관 전과 같다.
-- card_product_doc의 effective_* 컬럼은 이관 전 실제 DB에도 없었으므로 되살리지 않는다.

BEGIN;

SET LOCAL lock_timeout = '10s';

DO $$
BEGIN
    IF to_regclass('db_pipeline_v6_backup.card_policy_version') IS NULL THEN
        RAISE EXCEPTION '백업 스키마 db_pipeline_v6_backup이 없습니다';
    END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.card_bnft x
               WHERE NOT EXISTS (SELECT 1 FROM db_pipeline_v6_backup.card_policy_version v WHERE v.card_id = x.card_id)) THEN
        RAISE EXCEPTION '이관 후 정책판이 없는 카드의 혜택이 추가되었습니다';
    END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.card_bnft
               WHERE bnft_origin_cd = 'BRAND_SERVICE' OR bnft_valid_from IS NOT NULL OR bnft_valid_to_excl IS NOT NULL) THEN
        RAISE EXCEPTION 'V6에 담을 수 없는 브랜드 혜택 또는 제공 기간이 있습니다';
    END IF;
    IF EXISTS (SELECT 1 FROM db_pipeline.card_extr_stg WHERE card_id IS NULL) THEN
        RAISE EXCEPTION 'V6에 담을 수 없는 카드 미연결 추출 항목이 있습니다';
    END IF;
END;
$$;

DROP VIEW db_pipeline.v_card_integrity_issue;
DROP VIEW db_pipeline.v_common_cd_usage;
DROP VIEW db_pipeline.v_card_bnft_rule_effective;
DROP VIEW db_pipeline.v_card_cond_atom;
DROP VIEW db_pipeline.v_card_limit_tier;
DROP VIEW db_pipeline.v_card_rule_target;
DROP VIEW db_pipeline.v_card_bnft_rel;
DROP VIEW db_pipeline.v_card_rule_pool;
DROP VIEW db_pipeline.v_card_rule;

CREATE SEQUENCE db_pipeline.seq_card_common_bnft INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
COMMENT ON SEQUENCE db_pipeline.seq_card_common_bnft IS 'card_common_bnft.common_bnft_id 로컬 업무 ID 발급';
CREATE SEQUENCE db_pipeline.seq_card_common_policy_version INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
COMMENT ON SEQUENCE db_pipeline.seq_card_common_policy_version IS 'card_common_policy_version.common_ver_id 로컬 업무 ID 발급';
CREATE SEQUENCE db_pipeline.seq_card_policy_version INCREMENT BY 1 START WITH 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
COMMENT ON SEQUENCE db_pipeline.seq_card_policy_version IS 'card_policy_version.policy_ver_id 로컬 업무 ID 발급';
SELECT setval('db_pipeline.' || seq_nm, last_value, is_called) FROM db_pipeline_v6_backup.seq_state;

CREATE FUNCTION db_pipeline.fn_valid_doc_ref_list(p_list jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
    SELECT CASE
        WHEN jsonb_typeof(p_list) IS DISTINCT FROM 'array' THEN false
        ELSE coalesce((
            SELECT bool_and(jsonb_typeof(t.value) = 'object'
                            AND coalesce(t.value->>'card_doc_id', '') <> ''
                            AND coalesce(t.value->>'source_role_cd', '') <> '')
                   AND count(*) = count(DISTINCT t.value->>'card_doc_id')
            FROM jsonb_array_elements(p_list) AS t(value)), true)
    END
$_$;

COMMENT ON FUNCTION db_pipeline.fn_valid_doc_ref_list(jsonb) IS '정책판 근거 문서 목록 JSONB 계약 검증. V5 card_policy_doc 대체';

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

CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_rule_list(p_list jsonb, p_owner text) RETURNS boolean
    LANGUAGE plpgsql IMMUTABLE
    SET search_path TO 'pg_catalog'
    AS $_$
DECLARE
    v_rule jsonb;
    v_ref jsonb;
    v_keys text[] := '{}';
    v_pools text[];
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

        IF p_owner = 'LOCAL' THEN
            IF v_rule ? 'limit_list' OR jsonb_typeof(coalesce(v_rule->'pool_refs', '[]'::jsonb)) <> 'array' THEN
                RETURN false;
            END IF;
            v_pools := '{}';
            FOR v_ref IN SELECT value FROM jsonb_array_elements(coalesce(v_rule->'pool_refs', '[]'::jsonb)) LOOP
                IF jsonb_typeof(v_ref) <> 'object'
                   OR coalesce(v_ref->>'pool_id', '') = ''
                   OR coalesce(v_ref->>'pool_role_cd', '') = ''
                   OR v_ref->>'pool_id' = ANY (v_pools) THEN
                    RETURN false;
                END IF;
                v_pools := v_pools || (v_ref->>'pool_id');
            END LOOP;
        ELSIF p_owner = 'COMMON' THEN
            IF v_rule ? 'pool_refs'
               OR NOT db_pipeline.fn_valid_limit_list(coalesce(v_rule->'limit_list', '[]'::jsonb)) THEN
                RETURN false;
            END IF;
        ELSE
            RETURN false;
        END IF;
    END LOOP;
    RETURN true;
END;
$_$;

COMMENT ON FUNCTION db_pipeline.fn_valid_rule_list(jsonb, text) IS '계산 규칙 목록 JSONB 계약 검증. rule_key 중복, 금액 타입, 조건 상태, 대상, pool_refs(LOCAL), limit_list(COMMON) 검사';


-- 고아 관계는 자동 삭제하지 않고 복구를 중단한다.
DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM db_pipeline.card_bnft_rule_pool x
  WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id=x.card_id)
     OR NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id,b.card_bnft_id)=(x.card_id,x.card_bnft_id))
     OR NOT EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id,p.pool_id)=(x.card_id,x.pool_id))
     OR NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) r(value)
                    WHERE (b.card_id,b.card_bnft_id)=(x.card_id,x.card_bnft_id) AND r.value->>'rule_key'=x.rule_key)
     OR NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd c WHERE c.common_code_grp_id='POOL_ROLE' AND c.common_cd=x.pool_role_cd))
 THEN RAISE EXCEPTION '고아 또는 미등록 규칙·한도 관계를 확인해야 합니다'; END IF;
END $$;
-- V6 표현으로 복원. 동일 규칙 안의 풀은 pool_id 순서로 재구성한다.
UPDATE db_pipeline.card_bnft b SET rule_list = x.rules
FROM (SELECT b2.card_id,b2.card_bnft_id,coalesce(jsonb_agg(
      r.value || jsonb_build_object('pool_refs',coalesce((SELECT jsonb_agg(jsonb_build_object('pool_id',p.pool_id,'pool_role_cd',p.pool_role_cd) ORDER BY p.pool_id)
      FROM db_pipeline.card_bnft_rule_pool p WHERE (p.card_id,p.card_bnft_id,p.rule_key)=(b2.card_id,b2.card_bnft_id,r.value->>'rule_key')),'[]'::jsonb))
      ORDER BY r.ord) FILTER (WHERE r.value IS NOT NULL),'[]'::jsonb) AS rules
      FROM db_pipeline.card_bnft b2 LEFT JOIN LATERAL jsonb_array_elements(b2.rule_list) WITH ORDINALITY r(value,ord) ON true
      GROUP BY b2.card_id,b2.card_bnft_id) x WHERE (b.card_id,b.card_bnft_id)=(x.card_id,x.card_bnft_id);
-- 이관 후 해당 규칙과 관계가 그대로인 행은 원래 JSON과 배열 순서까지 복원한다.
UPDATE db_pipeline.card_bnft b SET rule_list = saved.rule_list
FROM db_pipeline_v6_backup.v7_rule_list_before_pool_split saved
WHERE (b.card_id,b.card_bnft_id)=(saved.card_id,saved.card_bnft_id)
  AND (SELECT coalesce(jsonb_agg(r.value-'pool_refs' ORDER BY r.ord),'[]'::jsonb) FROM jsonb_array_elements(b.rule_list) WITH ORDINALITY r(value,ord))
   = (SELECT coalesce(jsonb_agg(r.value-'pool_refs' ORDER BY r.ord),'[]'::jsonb) FROM jsonb_array_elements(saved.rule_list) WITH ORDINALITY r(value,ord))
  AND NOT EXISTS (
      (SELECT r.value->>'rule_key',p.value->>'pool_id',p.value->>'pool_role_cd' FROM jsonb_array_elements(saved.rule_list) r(value)
       CROSS JOIN LATERAL jsonb_array_elements(coalesce(r.value->'pool_refs','[]'::jsonb)) p(value)
       EXCEPT ALL SELECT p.rule_key,p.pool_id,p.pool_role_cd FROM db_pipeline.card_bnft_rule_pool p WHERE (p.card_id,p.card_bnft_id)=(b.card_id,b.card_bnft_id))
      UNION ALL
      (SELECT p.rule_key,p.pool_id,p.pool_role_cd FROM db_pipeline.card_bnft_rule_pool p WHERE (p.card_id,p.card_bnft_id)=(b.card_id,b.card_bnft_id)
       EXCEPT ALL SELECT r.value->>'rule_key',p.value->>'pool_id',p.value->>'pool_role_cd' FROM jsonb_array_elements(saved.rule_list) r(value)
       CROSS JOIN LATERAL jsonb_array_elements(coalesce(r.value->'pool_refs','[]'::jsonb)) p(value)));
DROP TABLE db_pipeline.card_bnft_rule_pool;

CREATE TABLE db_pipeline.card_policy_version (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_policy_version') NOT NULL,
    policy_ver_no integer NOT NULL,
    policy_cond_expr jsonb,
    source_doc_list jsonb NOT NULL DEFAULT '[]'::jsonb,
    valid_from date NOT NULL,
    valid_to_excl date,
    approved_at timestamptz,
    policy_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id),
    UNIQUE (card_id, policy_ver_no),
    CONSTRAINT card_policy_version_ck_1 CHECK (policy_ver_no > 0),
    CONSTRAINT card_policy_version_ck_2 CHECK (valid_to_excl IS NULL OR valid_to_excl > valid_from),
    CONSTRAINT card_policy_version_ck_3 CHECK (db_pipeline.fn_valid_cond_expr(policy_cond_expr)),
    CONSTRAINT card_policy_version_ck_4 CHECK (db_pipeline.fn_valid_doc_ref_list(source_doc_list))
);

COMMENT ON TABLE db_pipeline.card_policy_version IS '카드 정책 버전';
COMMENT ON COLUMN db_pipeline.card_policy_version.card_id IS '카드 아이디';
COMMENT ON COLUMN db_pipeline.card_policy_version.policy_ver_id IS '정책 버전 아이디';
COMMENT ON COLUMN db_pipeline.card_policy_version.policy_ver_no IS '정책 버전 번호';
COMMENT ON COLUMN db_pipeline.card_policy_version.policy_cond_expr IS '카드 공통 조건';
COMMENT ON COLUMN db_pipeline.card_policy_version.source_doc_list IS '근거 문서 목록';
COMMENT ON COLUMN db_pipeline.card_policy_version.valid_from IS '적용 시작일';
COMMENT ON COLUMN db_pipeline.card_policy_version.valid_to_excl IS '적용 종료일';
COMMENT ON COLUMN db_pipeline.card_policy_version.approved_at IS '승인 일시';
COMMENT ON COLUMN db_pipeline.card_policy_version.policy_status_cd IS '정책 상태';

CREATE INDEX ix_card_policy_version_lookup ON db_pipeline.card_policy_version (card_id, policy_status_cd, valid_from, valid_to_excl);
CREATE INDEX ix_card_policy_version_doc_gin ON db_pipeline.card_policy_version USING gin (source_doc_list jsonb_path_ops);

INSERT INTO db_pipeline.card_policy_version SELECT * FROM db_pipeline_v6_backup.card_policy_version;

ALTER TABLE db_pipeline.card_bnft ADD COLUMN policy_ver_id varchar(20);
UPDATE db_pipeline.card_bnft x SET policy_ver_id = v.policy_ver_id FROM db_pipeline.card_policy_version v WHERE v.card_id = x.card_id;
ALTER TABLE db_pipeline.card_bnft ALTER COLUMN policy_ver_id SET NOT NULL;
ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_pkey;
ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_card_id_bnft_cd_key;
ALTER TABLE db_pipeline.card_bnft ADD PRIMARY KEY (card_id, policy_ver_id, card_bnft_id);
ALTER TABLE db_pipeline.card_bnft ADD UNIQUE (card_id, policy_ver_id, bnft_cd);
COMMENT ON COLUMN db_pipeline.card_bnft.policy_ver_id IS '정책 버전 아이디';

ALTER TABLE db_pipeline.card_limit_pool ADD COLUMN policy_ver_id varchar(20);
UPDATE db_pipeline.card_limit_pool x SET policy_ver_id = v.policy_ver_id FROM db_pipeline.card_policy_version v WHERE v.card_id = x.card_id;
ALTER TABLE db_pipeline.card_limit_pool ALTER COLUMN policy_ver_id SET NOT NULL;
ALTER TABLE db_pipeline.card_limit_pool DROP CONSTRAINT card_limit_pool_pkey;
ALTER TABLE db_pipeline.card_limit_pool ADD PRIMARY KEY (card_id, policy_ver_id, pool_id);
COMMENT ON COLUMN db_pipeline.card_limit_pool.policy_ver_id IS '정책 버전 아이디';

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

COMMENT ON TABLE db_pipeline.card_common_bnft IS '공통 혜택';
COMMENT ON COLUMN db_pipeline.card_common_bnft.common_bnft_id IS '공통 혜택 아이디';
COMMENT ON COLUMN db_pipeline.card_common_bnft.provider_cd IS '제공 브랜드';
COMMENT ON COLUMN db_pipeline.card_common_bnft.service_grade_cd IS '서비스 등급';
COMMENT ON COLUMN db_pipeline.card_common_bnft.service_type_cd IS '서비스 유형';
COMMENT ON COLUMN db_pipeline.card_common_bnft.common_bnft_cd IS '공통 혜택 코드';
COMMENT ON COLUMN db_pipeline.card_common_bnft.common_bnft_nm IS '공통 혜택명';

CREATE TABLE db_pipeline.card_common_policy_version (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_common_policy_version') NOT NULL,
    common_ver_no integer NOT NULL,
    rule_list jsonb NOT NULL DEFAULT '[]'::jsonb,
    valid_from date NOT NULL,
    valid_to_excl date,
    approved_at timestamptz,
    policy_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (common_bnft_id, common_ver_id),
    UNIQUE (common_bnft_id, common_ver_no),
    CONSTRAINT card_common_policy_version_ck_1 CHECK (common_ver_no > 0),
    CONSTRAINT card_common_policy_version_ck_2 CHECK (valid_to_excl IS NULL OR valid_to_excl > valid_from),
    CONSTRAINT card_common_policy_version_ck_3 CHECK (db_pipeline.fn_valid_rule_list(rule_list, 'COMMON'))
);

COMMENT ON TABLE db_pipeline.card_common_policy_version IS '공통 혜택 정책 버전';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.common_bnft_id IS '공통 혜택 아이디';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.common_ver_id IS '공통 정책 버전 아이디';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.common_ver_no IS '공통 정책 버전 번호';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.rule_list IS '계산 규칙 목록';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.valid_from IS '적용 시작일';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.valid_to_excl IS '적용 종료일';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.approved_at IS '승인 일시';
COMMENT ON COLUMN db_pipeline.card_common_policy_version.policy_status_cd IS '정책 상태';

CREATE TABLE db_pipeline.card_bnft_common (
    card_id bigint NOT NULL,
    policy_ver_id varchar(20) NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    apply_status_cd varchar(20) NOT NULL,
    PRIMARY KEY (card_id, policy_ver_id, card_bnft_id, common_bnft_id, common_ver_id)
);

COMMENT ON TABLE db_pipeline.card_bnft_common IS '상품별 공통 혜택 관계';
COMMENT ON COLUMN db_pipeline.card_bnft_common.card_id IS '카드 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft_common.policy_ver_id IS '정책 버전 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft_common.card_bnft_id IS '혜택 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft_common.common_bnft_id IS '공통 혜택 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft_common.common_ver_id IS '공통 정책 버전 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft_common.apply_status_cd IS '적용 승인 상태';

CREATE TABLE db_pipeline.card_common_rule_evidence (
    common_bnft_id varchar(20) NOT NULL,
    common_ver_id varchar(20) NOT NULL,
    rule_key varchar(40) NOT NULL,
    evidence_id varchar(20) NOT NULL,
    ev_item_cd varchar(10) NOT NULL DEFAULT 'SELF',
    ev_item_key varchar(100) NOT NULL DEFAULT '-',
    PRIMARY KEY (common_bnft_id, common_ver_id, rule_key, evidence_id, ev_item_cd, ev_item_key),
    CONSTRAINT card_common_rule_evidence_ck_1 CHECK ((ev_item_cd = 'SELF') = (ev_item_key = '-'))
);

COMMENT ON TABLE db_pipeline.card_common_rule_evidence IS '공통 규칙 근거 관계';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.common_bnft_id IS '공통 혜택 아이디';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.common_ver_id IS '공통 정책 버전 아이디';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.rule_key IS '규칙 키';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.evidence_id IS '원문 근거 아이디';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.ev_item_cd IS '근거 항목 유형';
COMMENT ON COLUMN db_pipeline.card_common_rule_evidence.ev_item_key IS '근거 항목 키';

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

COMMENT ON TABLE db_pipeline.card_method_catalog IS '계산 방법 관리';
COMMENT ON COLUMN db_pipeline.card_method_catalog.method_kind_cd IS '계산 방식 종류';
COMMENT ON COLUMN db_pipeline.card_method_catalog.method_cd IS '계산 방식 코드';
COMMENT ON COLUMN db_pipeline.card_method_catalog.method_ver IS '계산 방식 버전';
COMMENT ON COLUMN db_pipeline.card_method_catalog.param_schema IS '파라미터 스키마';
COMMENT ON COLUMN db_pipeline.card_method_catalog.handler_key IS '실행 핸들러';
COMMENT ON COLUMN db_pipeline.card_method_catalog.method_status_cd IS '계산 방식 상태';

INSERT INTO db_pipeline.card_method_catalog SELECT * FROM db_pipeline_v6_backup.card_method_catalog;

CREATE INDEX ix_card_bnft_common_lookup ON db_pipeline.card_bnft_common (common_bnft_id, common_ver_id);
CREATE INDEX ix_card_common_policy_version_lookup ON db_pipeline.card_common_policy_version (common_bnft_id, policy_status_cd, valid_from, valid_to_excl);
CREATE INDEX ix_card_common_rule_list_gin ON db_pipeline.card_common_policy_version USING gin (rule_list jsonb_path_ops);
CREATE INDEX ix_card_common_bnft_service ON db_pipeline.card_common_bnft (provider_cd, service_grade_cd, service_type_cd);
CREATE INDEX ix_card_common_rule_evidence_evidence ON db_pipeline.card_common_rule_evidence (evidence_id);

ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_ck_6;
ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_ck_5;
ALTER TABLE db_pipeline.card_bnft ADD CONSTRAINT card_bnft_ck_5 CHECK (bnft_origin_cd <> 'COMMON_LINK' OR jsonb_array_length(rule_list) = 0);
ALTER TABLE db_pipeline.card_bnft DROP COLUMN bnft_valid_from;
ALTER TABLE db_pipeline.card_bnft DROP COLUMN bnft_valid_to_excl;

ALTER TABLE db_pipeline.card_extr_stg ALTER COLUMN card_id SET NOT NULL;
COMMENT ON COLUMN db_pipeline.card_extr_stg.card_id IS '카드 아이디';

ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT card_evidence_link_pkey;
ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT card_evidence_link_natural_key;
ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT card_evidence_link_ck_2;
DROP INDEX db_pipeline.ix_card_evidence_link_subject;
ALTER TABLE db_pipeline.card_evidence_link RENAME TO card_policy_evidence;
ALTER TABLE db_pipeline.card_policy_evidence RENAME CONSTRAINT card_evidence_link_ck_1 TO card_policy_evidence_ck_1;
ALTER INDEX db_pipeline.ix_card_evidence_link_evidence RENAME TO ix_card_policy_evidence_evidence;
ALTER SEQUENCE db_pipeline.seq_card_evidence_link RENAME TO seq_card_policy_evidence;
COMMENT ON SEQUENCE db_pipeline.seq_card_policy_evidence IS 'card_policy_evidence.ev_link_id 로컬 업무 ID 발급';
ALTER TABLE db_pipeline.card_policy_evidence
    ALTER COLUMN ev_link_id SET DEFAULT db_pipeline.fn_get_biz_id('card_policy_evidence');
ALTER TABLE db_pipeline.card_policy_evidence ADD COLUMN policy_ver_id varchar(20);
UPDATE db_pipeline.card_policy_evidence x SET policy_ver_id = v.policy_ver_id FROM db_pipeline.card_policy_version v WHERE v.card_id = x.card_id;
ALTER TABLE db_pipeline.card_policy_evidence ALTER COLUMN policy_ver_id SET NOT NULL;
UPDATE db_pipeline.card_policy_evidence SET ev_subject_cd = 'POLICY' WHERE ev_subject_cd = 'CARD';
ALTER TABLE db_pipeline.card_policy_evidence ADD PRIMARY KEY (card_id, policy_ver_id, ev_link_id);
ALTER TABLE db_pipeline.card_policy_evidence ADD CONSTRAINT card_policy_evidence_natural_key UNIQUE NULLS NOT DISTINCT
    (card_id, policy_ver_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, pool_id, ev_item_cd, ev_item_key, evidence_id);
ALTER TABLE db_pipeline.card_policy_evidence ADD CONSTRAINT card_policy_evidence_ck_2 CHECK (
    CASE ev_subject_cd
        WHEN 'POLICY' THEN num_nonnulls(card_bnft_id, rule_key, relation_key, pool_id) = 0
        WHEN 'BNFT' THEN card_bnft_id IS NOT NULL AND num_nonnulls(rule_key, relation_key, pool_id) = 0
        WHEN 'RULE' THEN card_bnft_id IS NOT NULL AND rule_key IS NOT NULL
                         AND num_nonnulls(relation_key, pool_id) = 0
        WHEN 'POOL' THEN pool_id IS NOT NULL AND num_nonnulls(card_bnft_id, rule_key, relation_key) = 0
        WHEN 'REL' THEN card_bnft_id IS NOT NULL AND relation_key IS NOT NULL
                        AND num_nonnulls(rule_key, pool_id) = 0
        ELSE false
    END);
CREATE INDEX ix_card_policy_evidence_subject ON db_pipeline.card_policy_evidence (card_id, policy_ver_id, ev_subject_cd, card_bnft_id, rule_key);
COMMENT ON TABLE db_pipeline.card_policy_evidence IS '정책 근거 관계';
COMMENT ON COLUMN db_pipeline.card_policy_evidence.policy_ver_id IS '정책 버전 아이디';

ALTER TABLE db_pipeline.card_product_doc DROP CONSTRAINT card_product_doc_approved_check;

ALTER TABLE db_pipeline.card_product DROP CONSTRAINT card_product_card_cond_expr_check;
ALTER TABLE db_pipeline.card_product DROP COLUMN card_cond_expr;
ALTER TABLE db_pipeline.card_product DROP COLUMN card_cond_status_cd;

DELETE FROM db_pipeline.common_cd;
DELETE FROM db_pipeline.common_code_grp;
INSERT INTO db_pipeline.common_code_grp SELECT * FROM db_pipeline_v6_backup.common_code_grp;
INSERT INTO db_pipeline.common_cd SELECT * FROM db_pipeline_v6_backup.common_cd;

CREATE VIEW db_pipeline.v_card_policy_doc AS
SELECT v.card_id, v.policy_ver_id,
       d.value->>'card_doc_id' AS card_doc_id,
       d.value->>'source_role_cd' AS source_role_cd
FROM db_pipeline.card_policy_version v
CROSS JOIN LATERAL jsonb_array_elements(v.source_doc_list) AS d(value);

COMMENT ON VIEW db_pipeline.v_card_policy_doc IS '정책판의 원천 문서를 행으로 복원. V5 card_policy_doc 조회 대체';

CREATE VIEW db_pipeline.v_card_rule AS
SELECT b.card_id, b.policy_ver_id, b.card_bnft_id,
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
       r.value->>'rule_status_cd' AS rule_status_cd,
       coalesce(r.value->'pool_refs', '[]'::jsonb) AS pool_refs
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) WITH ORDINALITY AS r(value, ord);

COMMENT ON VIEW db_pipeline.v_card_rule IS '상품 계산 규칙을 행으로 복원. V5 card_bnft_rule 조회 대체';

CREATE VIEW db_pipeline.v_card_common_rule AS
SELECT v.common_bnft_id, v.common_ver_id,
       r.value->>'rule_key' AS rule_key,
       r.ord AS rule_seq,
       nullif(r.value->'cond_expr', 'null'::jsonb) AS cond_expr,
       coalesce(r.value->'target_list', '[]'::jsonb) AS target_list,
       coalesce(r.value->'limit_list', '[]'::jsonb) AS limit_list,
       r.value->>'predicate_state_cd' AS predicate_state_cd,
       r.value->>'calc_method_cd' AS calc_method_cd,
       (r.value->>'method_ver')::integer AS method_ver,
       (r.value->>'value_num')::numeric(18,4) AS value_num,
       r.value->>'value_unit_cd' AS value_unit_cd,
       r.value->>'payout_unit_cd' AS payout_unit_cd,
       (r.value->>'basis_amt')::numeric(18,2) AS basis_amt,
       nullif(r.value->'calc_params', 'null'::jsonb) AS calc_params,
       r.value->>'rule_status_cd' AS rule_status_cd
FROM db_pipeline.card_common_policy_version v
CROSS JOIN LATERAL jsonb_array_elements(v.rule_list) WITH ORDINALITY AS r(value, ord);

COMMENT ON VIEW db_pipeline.v_card_common_rule IS '공통 계산 규칙을 행으로 복원. V5 card_common_bnft_rule 조회 대체';

CREATE VIEW db_pipeline.v_card_rule_pool AS
SELECT r.card_id, r.policy_ver_id, r.card_bnft_id, r.rule_key,
       p.value->>'pool_id' AS pool_id,
       p.value->>'pool_role_cd' AS pool_role_cd
FROM db_pipeline.v_card_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.pool_refs) AS p(value);

COMMENT ON VIEW db_pipeline.v_card_rule_pool IS '규칙↔한도 풀 관계를 행으로 복원. V5 card_bnft_rule_pool 조회 대체';

CREATE VIEW db_pipeline.v_card_bnft_rel AS
SELECT b.card_id, b.policy_ver_id,
       b.card_bnft_id AS from_bnft_id,
       x.value->>'to_bnft_id' AS to_bnft_id,
       x.value->>'relation_key' AS relation_key,
       x.value->>'rel_type_cd' AS rel_type_cd,
       x.value->>'trigger_pool_id' AS trigger_pool_id,
       (x.value->>'rel_priority')::integer AS rel_priority,
       false AS reverse_yn
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) AS x(value)
UNION ALL
SELECT b.card_id, b.policy_ver_id,
       x.value->>'to_bnft_id',
       b.card_bnft_id,
       x.value->>'relation_key',
       x.value->>'rel_type_cd',
       x.value->>'trigger_pool_id',
       (x.value->>'rel_priority')::integer,
       true
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) AS x(value)
WHERE x.value->>'rel_type_cd' = 'MUTUALLY_EXCLUSIVE';

COMMENT ON VIEW db_pipeline.v_card_bnft_rel IS '혜택 관계를 행으로 복원. MUTUALLY_EXCLUSIVE는 reverse_yn=true 행을 더해 양방향 제공. 저장 행 조회는 reverse_yn=false';

CREATE VIEW db_pipeline.v_card_rule_target AS
SELECT 'LOCAL'::text AS rule_source_cd, r.card_id, r.policy_ver_id, r.card_bnft_id, r.rule_key,
       NULL::varchar AS common_bnft_id, NULL::varchar AS common_ver_id,
       t.value->>'target_type_cd' AS target_type_cd,
       t.value->>'target_key' AS target_key,
       t.value->>'target_nm' AS target_nm
FROM db_pipeline.v_card_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.target_list) AS t(value)
UNION ALL
SELECT 'COMMON', NULL, NULL, NULL, r.rule_key, r.common_bnft_id, r.common_ver_id,
       t.value->>'target_type_cd', t.value->>'target_key', t.value->>'target_nm'
FROM db_pipeline.v_card_common_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.target_list) AS t(value);

COMMENT ON VIEW db_pipeline.v_card_rule_target IS '규칙 대상을 행으로 복원(상품·공통)';

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

COMMENT ON VIEW db_pipeline.v_card_limit_tier IS '한도 풀 구간을 행으로 복원';

CREATE VIEW db_pipeline.v_card_common_limit AS
SELECT r.common_bnft_id, r.common_ver_id, r.rule_key,
       l.value->>'limit_key' AS limit_key,
       coalesce(l.value->>'pool_key', r.rule_key || ':' || (l.value->>'limit_key')) AS pool_key,
       l.value->>'period_cd' AS period_cd,
       l.value->>'cap_unit_cd' AS cap_unit_cd,
       l.value->>'aggregation_key_cd' AS aggregation_key_cd,
       l.value->>'predicate_state_cd' AS predicate_state_cd,
       (l.value->>'limit_num')::numeric(18,2) AS limit_num,
       l.value->'cond_expr' AS cond_expr
FROM db_pipeline.v_card_common_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.limit_list) AS l(value);

COMMENT ON VIEW db_pipeline.v_card_common_limit IS '공통 규칙 내장 한도를 행으로 복원';

CREATE VIEW db_pipeline.v_card_cond_atom AS
WITH src AS (
    SELECT 'POLICY'::text AS owner_cd, v.card_id, v.policy_ver_id, NULL::varchar AS card_bnft_id,
           NULL::text AS rule_key, NULL::varchar AS pool_id, NULL::text AS item_key,
           NULL::varchar AS common_bnft_id, NULL::varchar AS common_ver_id,
           v.policy_cond_expr AS expr
    FROM db_pipeline.card_policy_version v WHERE v.policy_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'BNFT', b.card_id, b.policy_ver_id, b.card_bnft_id, NULL, NULL, NULL, NULL, NULL, b.bnft_cond_expr
    FROM db_pipeline.card_bnft b WHERE b.bnft_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'RULE', r.card_id, r.policy_ver_id, r.card_bnft_id, r.rule_key, NULL, NULL, NULL, NULL, r.cond_expr
    FROM db_pipeline.v_card_rule r WHERE r.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'POOL_TIER', t.card_id, t.policy_ver_id, NULL, NULL, t.pool_id, t.tier_key, NULL, NULL, t.cond_expr
    FROM db_pipeline.v_card_limit_tier t WHERE t.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'COMMON_RULE', NULL, NULL, NULL, r.rule_key, NULL, NULL, r.common_bnft_id, r.common_ver_id, r.cond_expr
    FROM db_pipeline.v_card_common_rule r WHERE r.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'COMMON_LIMIT', NULL, NULL, NULL, l.rule_key, NULL, l.limit_key, l.common_bnft_id, l.common_ver_id, l.cond_expr
    FROM db_pipeline.v_card_common_limit l WHERE l.cond_expr IS NOT NULL
)
SELECT s.owner_cd, s.card_id, s.policy_ver_id, s.card_bnft_id, s.rule_key, s.pool_id, s.item_key,
       s.common_bnft_id, s.common_ver_id,
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
SELECT b.card_id, b.policy_ver_id, b.card_bnft_id, b.bnft_nm, b.bnft_scope_cd, b.bnft_brand_opt_cds,
       'LOCAL'::text AS rule_source_cd, r.rule_key,
       NULL::varchar AS common_bnft_id, NULL::varchar AS common_ver_id,
       NULL::date AS common_valid_from, NULL::date AS common_valid_to_excl,
       r.calc_method_cd, r.method_ver, r.value_num, r.value_unit_cd, r.payout_unit_cd, r.basis_amt,
       r.calc_params, r.predicate_state_cd, r.target_list,
       b.bnft_cond_expr, r.cond_expr AS rule_cond_expr, r.rule_status_cd
FROM db_pipeline.card_bnft b
JOIN db_pipeline.v_card_rule r
  ON (r.card_id, r.policy_ver_id, r.card_bnft_id) = (b.card_id, b.policy_ver_id, b.card_bnft_id)
WHERE b.bnft_origin_cd = 'LOCAL'
UNION ALL
SELECT b.card_id, b.policy_ver_id, b.card_bnft_id, b.bnft_nm, b.bnft_scope_cd, b.bnft_brand_opt_cds,
       'COMMON', cr.rule_key, x.common_bnft_id, x.common_ver_id,
       cv.valid_from, cv.valid_to_excl,
       cr.calc_method_cd, cr.method_ver, cr.value_num, cr.value_unit_cd, cr.payout_unit_cd, cr.basis_amt,
       cr.calc_params, cr.predicate_state_cd, cr.target_list,
       b.bnft_cond_expr, cr.cond_expr, cr.rule_status_cd
FROM db_pipeline.card_bnft b
JOIN db_pipeline.card_bnft_common x
  ON (x.card_id, x.policy_ver_id, x.card_bnft_id) = (b.card_id, b.policy_ver_id, b.card_bnft_id)
JOIN db_pipeline.card_common_policy_version cv
  ON (cv.common_bnft_id, cv.common_ver_id) = (x.common_bnft_id, x.common_ver_id)
JOIN db_pipeline.v_card_common_rule cr
  ON (cr.common_bnft_id, cr.common_ver_id) = (x.common_bnft_id, x.common_ver_id)
WHERE b.bnft_origin_cd = 'COMMON_LINK'
  AND x.apply_status_cd = 'APPROVED'
  AND cv.policy_status_cd = 'APPROVED';

COMMENT ON VIEW db_pipeline.v_card_bnft_rule_effective IS '상품 고유 규칙과 승인된 공통 규칙의 단일 출력. 값은 정책 후보이며 거래별 보상액이 아님';

CREATE VIEW db_pipeline.v_common_cd_usage AS
SELECT 'card_product.card_kind_cd'::text AS source_nm, 'CARD_KIND'::varchar(20) AS common_code_grp_id, card_kind_cd::text AS cd_value
FROM db_pipeline.card_product WHERE card_kind_cd IS NOT NULL
UNION ALL
SELECT 'card_product.product_status_cd'::text AS source_nm, 'PRODUCT_STATUS'::varchar(20) AS common_code_grp_id, product_status_cd::text AS cd_value
FROM db_pipeline.card_product WHERE product_status_cd IS NOT NULL
UNION ALL
SELECT 'card_product_doc.doc_role_cd'::text AS source_nm, 'DOC_ROLE'::varchar(20) AS common_code_grp_id, doc_role_cd::text AS cd_value
FROM db_pipeline.card_product_doc WHERE doc_role_cd IS NOT NULL
UNION ALL
SELECT 'card_product_doc.approval_status_cd'::text AS source_nm, 'APPROVAL_STATUS'::varchar(20) AS common_code_grp_id, approval_status_cd::text AS cd_value
FROM db_pipeline.card_product_doc WHERE approval_status_cd IS NOT NULL
UNION ALL
SELECT 'card_policy_version.policy_status_cd'::text AS source_nm, 'POLICY_STATUS'::varchar(20) AS common_code_grp_id, policy_status_cd::text AS cd_value
FROM db_pipeline.card_policy_version WHERE policy_status_cd IS NOT NULL
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
SELECT 'card_limit_pool.pool_scope_cd'::text AS source_nm, 'LIMIT_SCOPE'::varchar(20) AS common_code_grp_id, pool_scope_cd::text AS cd_value
FROM db_pipeline.card_limit_pool WHERE pool_scope_cd IS NOT NULL
UNION ALL
SELECT 'card_limit_pool.period_cd'::text AS source_nm, 'LIMIT_PERIOD'::varchar(20) AS common_code_grp_id, period_cd::text AS cd_value
FROM db_pipeline.card_limit_pool WHERE period_cd IS NOT NULL
UNION ALL
SELECT 'card_limit_pool.cap_unit_cd'::text AS source_nm, 'LIMIT_UNIT'::varchar(20) AS common_code_grp_id, cap_unit_cd::text AS cd_value
FROM db_pipeline.card_limit_pool WHERE cap_unit_cd IS NOT NULL
UNION ALL
SELECT 'card_limit_pool.aggregation_key_cd'::text AS source_nm, 'LIMIT_AGG'::varchar(20) AS common_code_grp_id, aggregation_key_cd::text AS cd_value
FROM db_pipeline.card_limit_pool WHERE aggregation_key_cd IS NOT NULL
UNION ALL
SELECT 'card_method_catalog.method_kind_cd'::text AS source_nm, 'METHOD_KIND'::varchar(20) AS common_code_grp_id, method_kind_cd::text AS cd_value
FROM db_pipeline.card_method_catalog WHERE method_kind_cd IS NOT NULL
UNION ALL
SELECT 'card_method_catalog.method_status_cd'::text AS source_nm, 'METHOD_STATUS'::varchar(20) AS common_code_grp_id, method_status_cd::text AS cd_value
FROM db_pipeline.card_method_catalog WHERE method_status_cd IS NOT NULL
UNION ALL
SELECT 'card_common_bnft.provider_cd'::text AS source_nm, 'BRAND'::varchar(20) AS common_code_grp_id, provider_cd::text AS cd_value
FROM db_pipeline.card_common_bnft WHERE provider_cd IS NOT NULL
UNION ALL
SELECT 'card_common_bnft.service_grade_cd'::text AS source_nm, 'SERVICE_GRADE'::varchar(20) AS common_code_grp_id, service_grade_cd::text AS cd_value
FROM db_pipeline.card_common_bnft WHERE service_grade_cd IS NOT NULL
UNION ALL
SELECT 'card_common_bnft.service_type_cd'::text AS source_nm, 'SERVICE_TYPE'::varchar(20) AS common_code_grp_id, service_type_cd::text AS cd_value
FROM db_pipeline.card_common_bnft WHERE service_type_cd IS NOT NULL
UNION ALL
SELECT 'card_common_policy_version.policy_status_cd'::text AS source_nm, 'POLICY_STATUS'::varchar(20) AS common_code_grp_id, policy_status_cd::text AS cd_value
FROM db_pipeline.card_common_policy_version WHERE policy_status_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft_common.apply_status_cd'::text AS source_nm, 'APPROVAL_STATUS'::varchar(20) AS common_code_grp_id, apply_status_cd::text AS cd_value
FROM db_pipeline.card_bnft_common WHERE apply_status_cd IS NOT NULL
UNION ALL
SELECT 'card_source_evidence.approval_status_cd'::text AS source_nm, 'APPROVAL_STATUS'::varchar(20) AS common_code_grp_id, approval_status_cd::text AS cd_value
FROM db_pipeline.card_source_evidence WHERE approval_status_cd IS NOT NULL
UNION ALL
SELECT 'card_policy_evidence.ev_subject_cd'::text AS source_nm, 'EV_SUBJECT'::varchar(20) AS common_code_grp_id, ev_subject_cd::text AS cd_value
FROM db_pipeline.card_policy_evidence WHERE ev_subject_cd IS NOT NULL
UNION ALL
SELECT 'card_policy_evidence.ev_item_cd'::text AS source_nm, 'EV_ITEM'::varchar(20) AS common_code_grp_id, ev_item_cd::text AS cd_value
FROM db_pipeline.card_policy_evidence WHERE ev_item_cd IS NOT NULL
UNION ALL
SELECT 'card_common_rule_evidence.ev_item_cd'::text AS source_nm, 'EV_ITEM'::varchar(20) AS common_code_grp_id, ev_item_cd::text AS cd_value
FROM db_pipeline.card_common_rule_evidence WHERE ev_item_cd IS NOT NULL
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
SELECT 'card_policy_version.source_doc_list[].source_role_cd', 'DOC_ROLE', source_role_cd::text
FROM db_pipeline.v_card_policy_doc WHERE source_role_cd IS NOT NULL
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
SELECT 'card_common_policy_version.rule_list[].predicate_state_cd', 'PREDICATE_STATE', predicate_state_cd::text
FROM db_pipeline.v_card_common_rule WHERE predicate_state_cd IS NOT NULL
UNION ALL
SELECT 'card_common_policy_version.rule_list[].calc_method_cd', 'CALC_METHOD', calc_method_cd::text
FROM db_pipeline.v_card_common_rule WHERE calc_method_cd IS NOT NULL
UNION ALL
SELECT 'card_common_policy_version.rule_list[].value_unit_cd', 'VALUE_UNIT', value_unit_cd::text
FROM db_pipeline.v_card_common_rule WHERE value_unit_cd IS NOT NULL
UNION ALL
SELECT 'card_common_policy_version.rule_list[].payout_unit_cd', 'PAYOUT_UNIT', payout_unit_cd::text
FROM db_pipeline.v_card_common_rule WHERE payout_unit_cd IS NOT NULL
UNION ALL
SELECT 'card_common_policy_version.rule_list[].rule_status_cd', 'ITEM_STATUS', rule_status_cd::text
FROM db_pipeline.v_card_common_rule WHERE rule_status_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.rule_list[].pool_refs[].pool_role_cd', 'POOL_ROLE', pool_role_cd::text
FROM db_pipeline.v_card_rule_pool WHERE pool_role_cd IS NOT NULL
UNION ALL
SELECT 'card_bnft.relation_list[].rel_type_cd', 'REL_TYPE', rel_type_cd::text
FROM db_pipeline.v_card_bnft_rel WHERE rel_type_cd IS NOT NULL AND NOT reverse_yn
UNION ALL
SELECT 'rule_list[].target_list[].target_type_cd', 'TARGET_TYPE', target_type_cd::text
FROM db_pipeline.v_card_rule_target WHERE target_type_cd IS NOT NULL
UNION ALL
SELECT 'card_limit_pool.tier_list[].predicate_state_cd', 'PREDICATE_STATE', predicate_state_cd::text
FROM db_pipeline.v_card_limit_tier WHERE predicate_state_cd IS NOT NULL
UNION ALL
SELECT 'rule_list[].limit_list[].period_cd', 'LIMIT_PERIOD', period_cd::text
FROM db_pipeline.v_card_common_limit WHERE period_cd IS NOT NULL
UNION ALL
SELECT 'rule_list[].limit_list[].cap_unit_cd', 'LIMIT_UNIT', cap_unit_cd::text
FROM db_pipeline.v_card_common_limit WHERE cap_unit_cd IS NOT NULL
UNION ALL
SELECT 'rule_list[].limit_list[].aggregation_key_cd', 'LIMIT_AGG', aggregation_key_cd::text
FROM db_pipeline.v_card_common_limit WHERE aggregation_key_cd IS NOT NULL
UNION ALL
SELECT 'rule_list[].limit_list[].predicate_state_cd', 'PREDICATE_STATE', predicate_state_cd::text
FROM db_pipeline.v_card_common_limit WHERE predicate_state_cd IS NOT NULL
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
fallback AS (
    SELECT card_id, policy_ver_id, from_bnft_id, to_bnft_id
    FROM db_pipeline.v_card_bnft_rel
    WHERE rel_type_cd = 'FALLBACK_AFTER_CAP' AND NOT reverse_yn
),
cycle AS (
    WITH RECURSIVE walk(card_id, policy_ver_id, start_id, cur_id, path) AS (
        SELECT card_id, policy_ver_id, from_bnft_id, to_bnft_id, ARRAY[from_bnft_id, to_bnft_id]
        FROM fallback
        UNION ALL
        SELECT w.card_id, w.policy_ver_id, w.start_id, f.to_bnft_id, w.path || f.to_bnft_id
        FROM walk w
        JOIN fallback f ON (f.card_id, f.policy_ver_id, f.from_bnft_id) = (w.card_id, w.policy_ver_id, w.cur_id)
        WHERE NOT f.to_bnft_id = ANY (w.path[2:])
    )
    SELECT DISTINCT card_id, policy_ver_id, start_id FROM walk WHERE cur_id = start_id
)
SELECT 'policy_without_product' AS gate_cd, x.card_id || '/' || x.policy_ver_id AS issue_key
FROM db_pipeline.card_policy_version x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = x.card_id)
UNION ALL
SELECT 'bnft_without_policy', x.card_id || '/' || x.policy_ver_id || '/' || x.card_bnft_id
FROM db_pipeline.card_bnft x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
UNION ALL
SELECT 'local_confirmed_without_rule', x.card_id || '/' || x.policy_ver_id || '/' || x.card_bnft_id
FROM db_pipeline.card_bnft x
WHERE x.bnft_origin_cd = 'LOCAL' AND x.verification_status_cd = 'CONFIRMED' AND jsonb_array_length(x.rule_list) = 0
UNION ALL
SELECT 'pool_without_policy', x.card_id || '/' || x.policy_ver_id || '/' || x.pool_id
FROM db_pipeline.card_limit_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
UNION ALL
SELECT 'pool_ref_orphan', x.card_id || '/' || x.rule_key || '/' || x.pool_id
FROM db_pipeline.v_card_rule_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id, p.policy_ver_id, p.pool_id) = (x.card_id, x.policy_ver_id, x.pool_id))
UNION ALL
SELECT 'rel_to_bnft_orphan', x.card_id || '/' || x.relation_key
FROM db_pipeline.v_card_bnft_rel x
WHERE NOT x.reverse_yn
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id, b.policy_ver_id, b.card_bnft_id) = (x.card_id, x.policy_ver_id, x.to_bnft_id))
UNION ALL
SELECT 'rel_trigger_pool_orphan', x.card_id || '/' || x.relation_key
FROM db_pipeline.v_card_bnft_rel x
WHERE NOT x.reverse_yn AND x.trigger_pool_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id, p.policy_ver_id, p.pool_id) = (x.card_id, x.policy_ver_id, x.trigger_pool_id))
UNION ALL
SELECT 'rel_mutual_stored_twice', a.card_id || '/' || a.from_bnft_id || '/' || a.to_bnft_id
FROM db_pipeline.v_card_bnft_rel a
JOIN db_pipeline.v_card_bnft_rel b
  ON (a.card_id, a.policy_ver_id, a.from_bnft_id, a.to_bnft_id, a.rel_type_cd) = (b.card_id, b.policy_ver_id, b.to_bnft_id, b.from_bnft_id, b.rel_type_cd)
WHERE NOT a.reverse_yn AND NOT b.reverse_yn AND a.rel_type_cd = 'MUTUALLY_EXCLUSIVE' AND a.from_bnft_id < a.to_bnft_id
UNION ALL
SELECT 'rel_fallback_cycle', c.card_id || '/' || c.start_id FROM cycle c
UNION ALL
SELECT 'common_link_orphan', x.card_id || '/' || x.card_bnft_id || '/' || x.common_bnft_id
FROM db_pipeline.card_bnft_common x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id, b.policy_ver_id, b.card_bnft_id) = (x.card_id, x.policy_ver_id, x.card_bnft_id) AND b.bnft_origin_cd = 'COMMON_LINK')
   OR NOT EXISTS (SELECT 1 FROM db_pipeline.card_common_policy_version v WHERE (v.common_bnft_id, v.common_ver_id) = (x.common_bnft_id, x.common_ver_id))
UNION ALL
SELECT 'common_link_without_link', b.card_id || '/' || b.policy_ver_id || '/' || b.card_bnft_id
FROM db_pipeline.card_bnft b
WHERE b.bnft_origin_cd = 'COMMON_LINK'
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft_common x WHERE (x.card_id, x.policy_ver_id, x.card_bnft_id) = (b.card_id, b.policy_ver_id, b.card_bnft_id))
UNION ALL
SELECT 'common_link_multi_approved_same_period', a.card_id || '/' || a.card_bnft_id
FROM db_pipeline.card_bnft_common a
JOIN db_pipeline.card_bnft_common b
  ON (a.card_id, a.policy_ver_id, a.card_bnft_id) = (b.card_id, b.policy_ver_id, b.card_bnft_id)
 AND (a.common_bnft_id, a.common_ver_id) < (b.common_bnft_id, b.common_ver_id)
JOIN db_pipeline.card_common_policy_version va ON (va.common_bnft_id, va.common_ver_id) = (a.common_bnft_id, a.common_ver_id)
JOIN db_pipeline.card_common_policy_version vb ON (vb.common_bnft_id, vb.common_ver_id) = (b.common_bnft_id, b.common_ver_id)
WHERE a.apply_status_cd = 'APPROVED' AND b.apply_status_cd = 'APPROVED'
  AND daterange(va.valid_from, va.valid_to_excl, '[)') && daterange(vb.valid_from, vb.valid_to_excl, '[)')
UNION ALL
SELECT 'policy_period_overlap', a.card_id || '/' || a.policy_ver_id || '/' || b.policy_ver_id
FROM db_pipeline.card_policy_version a
JOIN db_pipeline.card_policy_version b ON a.card_id = b.card_id AND a.policy_ver_id < b.policy_ver_id
WHERE a.policy_status_cd = 'APPROVED' AND b.policy_status_cd = 'APPROVED'
  AND daterange(a.valid_from, a.valid_to_excl, '[)') && daterange(b.valid_from, b.valid_to_excl, '[)')
UNION ALL
SELECT 'policy_doc_orphan', x.card_id || '/' || x.policy_ver_id || '/' || x.card_doc_id
FROM db_pipeline.v_card_policy_doc x
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
SELECT 'method_not_in_catalog', m.calc_method_cd || '/' || m.method_ver
FROM (SELECT calc_method_cd, method_ver FROM db_pipeline.v_card_rule
      UNION SELECT calc_method_cd, method_ver FROM db_pipeline.v_card_common_rule) m
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_method_catalog c WHERE c.method_kind_cd = 'CALC' AND c.method_cd = m.calc_method_cd AND c.method_ver = m.method_ver)
UNION ALL
SELECT 'catalog_method_not_in_code', c.method_kind_cd || '/' || c.method_cd
FROM db_pipeline.card_method_catalog c
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd d
                  WHERE d.common_cd = c.method_cd
                    AND d.common_code_grp_id = CASE c.method_kind_cd WHEN 'CALC' THEN 'CALC_METHOD' ELSE 'PREDICATE_METHOD' END)
UNION ALL
SELECT 'excl_item_unknown', a.owner_cd || '/' || a.atom_key
FROM atoms a
WHERE a.card_excl_item_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_excl_item i WHERE i.card_excl_item_id = a.card_excl_item_id)
UNION ALL
SELECT 'common_pool_key_conflict', z.common_bnft_id || '/' || z.common_ver_id || '/' || z.pool_key
FROM (SELECT common_bnft_id, common_ver_id, pool_key FROM db_pipeline.v_card_common_limit
      GROUP BY 1, 2, 3 HAVING count(DISTINCT (period_cd, cap_unit_cd, aggregation_key_cd, limit_num)) > 1) z
UNION ALL
SELECT 'evidence_source_orphan', e.evidence_id
FROM db_pipeline.card_source_evidence e
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc_chunk c WHERE (c.card_doc_id, c.page_no, c.card_doc_chunk_id) = (e.card_doc_id, e.page_no, e.card_doc_chunk_id))
UNION ALL
SELECT 'evidence_not_approved', l.evidence_id
FROM (SELECT evidence_id FROM db_pipeline.card_policy_evidence
      UNION SELECT evidence_id FROM db_pipeline.card_common_rule_evidence) l
LEFT JOIN db_pipeline.card_source_evidence e USING (evidence_id)
WHERE e.evidence_id IS NULL OR e.approval_status_cd <> 'APPROVED'
UNION ALL
SELECT 'evidence_subject_orphan', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_policy_evidence l
WHERE NOT CASE l.ev_subject_cd
    WHEN 'POLICY' THEN EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (l.card_id, l.policy_ver_id))
    WHEN 'BNFT' THEN EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id, b.policy_ver_id, b.card_bnft_id) = (l.card_id, l.policy_ver_id, l.card_bnft_id))
    WHEN 'RULE' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_rule r WHERE (r.card_id, r.policy_ver_id, r.card_bnft_id, r.rule_key) = (l.card_id, l.policy_ver_id, l.card_bnft_id, l.rule_key))
    WHEN 'POOL' THEN EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id, p.policy_ver_id, p.pool_id) = (l.card_id, l.policy_ver_id, l.pool_id))
    WHEN 'REL' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_bnft_rel r WHERE NOT r.reverse_yn AND (r.card_id, r.policy_ver_id, r.from_bnft_id, r.relation_key) = (l.card_id, l.policy_ver_id, l.card_bnft_id, l.relation_key))
    ELSE false
END
UNION ALL
SELECT 'evidence_item_key_missing', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_policy_evidence l
WHERE l.ev_item_cd <> 'SELF' AND NOT CASE l.ev_item_cd
    WHEN 'COND' THEN EXISTS (SELECT 1 FROM atoms a WHERE (a.card_id, a.policy_ver_id) = (l.card_id, l.policy_ver_id) AND a.atom_key = l.ev_item_key
                             AND a.card_bnft_id IS NOT DISTINCT FROM l.card_bnft_id AND a.rule_key IS NOT DISTINCT FROM l.rule_key AND a.pool_id IS NOT DISTINCT FROM l.pool_id)
    WHEN 'TARGET' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_rule_target t WHERE (t.card_id, t.policy_ver_id, t.card_bnft_id, t.rule_key) = (l.card_id, l.policy_ver_id, l.card_bnft_id, l.rule_key) AND t.target_key = l.ev_item_key)
    WHEN 'TIER' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_limit_tier t WHERE (t.card_id, t.policy_ver_id, t.pool_id) = (l.card_id, l.policy_ver_id, l.pool_id) AND t.tier_key = l.ev_item_key)
    ELSE false
END
UNION ALL
SELECT 'common_evidence_subject_orphan', l.common_bnft_id || '/' || l.rule_key
FROM db_pipeline.card_common_rule_evidence l
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.v_card_common_rule r WHERE (r.common_bnft_id, r.common_ver_id, r.rule_key) = (l.common_bnft_id, l.common_ver_id, l.rule_key))
UNION ALL
SELECT 'common_evidence_item_key_missing', l.common_bnft_id || '/' || l.rule_key || '/' || l.ev_item_key
FROM db_pipeline.card_common_rule_evidence l
WHERE l.ev_item_cd <> 'SELF' AND NOT CASE l.ev_item_cd
    WHEN 'COND' THEN EXISTS (SELECT 1 FROM atoms a WHERE (a.common_bnft_id, a.common_ver_id, a.rule_key) = (l.common_bnft_id, l.common_ver_id, l.rule_key) AND a.atom_key = l.ev_item_key)
    WHEN 'TARGET' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_rule_target t WHERE (t.common_bnft_id, t.common_ver_id, t.rule_key) = (l.common_bnft_id, l.common_ver_id, l.rule_key) AND t.target_key = l.ev_item_key)
    WHEN 'LIMIT' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_common_limit t WHERE (t.common_bnft_id, t.common_ver_id, t.rule_key) = (l.common_bnft_id, l.common_ver_id, l.rule_key) AND t.limit_key = l.ev_item_key)
    ELSE false
END
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

COMMENT ON VIEW db_pipeline.v_card_integrity_issue IS '승인 전 정합성 게이트. 물리 FK가 없으므로 행이 1건이라도 있으면 승인하지 않음';

COMMENT ON SCHEMA db_pipeline IS '카드 상품 중심 V6 공통코드·반정규화 스키마(초안)';

DROP SCHEMA db_pipeline_v6_backup CASCADE;

COMMIT;
