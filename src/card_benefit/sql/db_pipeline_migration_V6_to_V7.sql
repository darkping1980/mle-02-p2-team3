-- V6 -> V7: 카드 정책 버전 계층 제거, 공통 혜택 구조 제거, 방법 카탈로그 제거, card_product_doc 간소화.
-- 실행 전 사용자 승인이 필요하다. card_policy_version을 삭제하고 policy_ver_id 컬럼을 지운다.
-- 전체가 한 트랜잭션이다. 사전 검사나 사후 검사가 실패하면 아무것도 바뀌지 않는다.
-- 삭제 대상과 복구용 값은 db_pipeline_v6_backup 스키마에 남긴다. 복구는 db_pipeline_migration_V7_to_V6_rollback.sql을 쓴다.
-- 대상은 V6 스키마다. card_product_doc의 effective_* 컬럼이 이미 없는 실제 DB와 파일 그대로의 V6 모두 처리한다.
-- 카드별 정책판이 2건 이상이거나 공통 혜택 4개 테이블에 행이 있으면 자동 변환하지 않고 중단한다.

BEGIN;

SET LOCAL lock_timeout = '10s';

-- ---------------------------------------------------------------------------
-- 1. 사전 검사
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    v_bad text;
BEGIN
    IF to_regclass('db_pipeline.card_policy_version') IS NULL THEN
        RAISE EXCEPTION 'V6 스키마가 아닙니다: card_policy_version이 없습니다';
    END IF;
    IF to_regnamespace('db_pipeline_v6_backup') IS NOT NULL THEN
        RAISE EXCEPTION '백업 스키마 db_pipeline_v6_backup이 이미 있습니다';
    END IF;

    SELECT string_agg(card_id::text, ', ') INTO v_bad FROM (
        SELECT card_id FROM db_pipeline.card_policy_version GROUP BY card_id HAVING count(*) > 1) x;
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION '정책판이 2건 이상인 카드가 있어 자동 병합하지 않습니다: %', v_bad;
    END IF;

    SELECT string_agg(src, ', ') INTO v_bad FROM (
        SELECT 'card_bnft' AS src FROM db_pipeline.card_bnft x
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
        UNION
        SELECT 'card_limit_pool' FROM db_pipeline.card_limit_pool x
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
        UNION
        SELECT 'card_policy_evidence' FROM db_pipeline.card_policy_evidence x
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_policy_version v WHERE (v.card_id, v.policy_ver_id) = (x.card_id, x.policy_ver_id))
    ) x;
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION '정책판을 찾을 수 없는 행이 있습니다: %', v_bad;
    END IF;

    -- 공통 혜택 데이터의 카드별 변환 규칙은 정의하지 않았다. 행이 있으면 지우지 않고 멈춘다.
    SELECT string_agg(src, ', ') INTO v_bad FROM (
        SELECT 'card_common_bnft' AS src WHERE EXISTS (SELECT 1 FROM db_pipeline.card_common_bnft)
        UNION ALL SELECT 'card_common_policy_version' WHERE EXISTS (SELECT 1 FROM db_pipeline.card_common_policy_version)
        UNION ALL SELECT 'card_bnft_common' WHERE EXISTS (SELECT 1 FROM db_pipeline.card_bnft_common)
        UNION ALL SELECT 'card_common_rule_evidence' WHERE EXISTS (SELECT 1 FROM db_pipeline.card_common_rule_evidence)
        UNION ALL SELECT 'card_bnft.COMMON_LINK' WHERE EXISTS (SELECT 1 FROM db_pipeline.card_bnft WHERE bnft_origin_cd = 'COMMON_LINK')
    ) x;
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION '공통 혜택 데이터가 있어 삭제하지 않습니다: %', v_bad;
    END IF;

    -- source_doc_list는 card_product_doc으로 대체되므로 빠지는 문서가 없어야 한다.
    SELECT string_agg(v.card_id || '/' || (d.value->>'card_doc_id'), ', ') INTO v_bad
    FROM db_pipeline.card_policy_version v
    CROSS JOIN LATERAL jsonb_array_elements(v.source_doc_list) AS d(value)
    WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc x
                      WHERE (x.card_id, x.card_doc_id, x.doc_role_cd) = (v.card_id, d.value->>'card_doc_id', d.value->>'source_role_cd'));
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION 'card_product_doc에 없는 정책 문서가 있습니다: %', v_bad;
    END IF;

    -- 실행 가능한 방법 계약이 등록되어 있으면 지우지 않고 멈춘다. 시험용 UNEXECUTABLE 행만 삭제 대상이다.
    IF EXISTS (SELECT 1 FROM db_pipeline.card_method_catalog WHERE method_status_cd <> 'UNEXECUTABLE') THEN
        RAISE EXCEPTION '실행 가능한 방법 계약이 있어 card_method_catalog를 삭제하지 않습니다';
    END IF;

    -- 복구된 APPROVED 근거 CHECK를 위반하는 행이 있으면 먼저 알린다.
    SELECT string_agg(card_id || '/' || card_doc_id, ', ') INTO v_bad
    FROM db_pipeline.card_product_doc
    WHERE approval_status_cd = 'APPROVED' AND length(trim(applicability_basis_txt)) = 0;
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION '적용 근거 없는 승인 문서 관계가 있습니다: %', v_bad;
    END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- 2. 복구용 백업 (삭제되는 값만)
-- ---------------------------------------------------------------------------
CREATE SCHEMA db_pipeline_v6_backup;
COMMENT ON SCHEMA db_pipeline_v6_backup IS 'V6->V7 이관 때 삭제한 정책판 값. 롤백 기간이 끝나면 삭제한다';

CREATE TABLE db_pipeline_v6_backup.card_policy_version AS TABLE db_pipeline.card_policy_version;
CREATE TABLE db_pipeline_v6_backup.card_method_catalog AS TABLE db_pipeline.card_method_catalog;
CREATE TABLE db_pipeline_v6_backup.common_code_grp AS TABLE db_pipeline.common_code_grp;
CREATE TABLE db_pipeline_v6_backup.common_cd AS TABLE db_pipeline.common_cd;
CREATE TABLE db_pipeline_v6_backup.seq_state AS
    SELECT 'seq_card_policy_version'::text AS seq_nm, last_value, is_called FROM db_pipeline.seq_card_policy_version
    UNION ALL SELECT 'seq_card_common_bnft', last_value, is_called FROM db_pipeline.seq_card_common_bnft
    UNION ALL SELECT 'seq_card_common_policy_version', last_value, is_called FROM db_pipeline.seq_card_common_policy_version;
CREATE TABLE db_pipeline_v6_backup.row_counts AS
    SELECT (SELECT count(*) FROM db_pipeline.card_product) AS card_product,
           (SELECT count(*) FROM db_pipeline.card_bnft) AS card_bnft,
           (SELECT count(*) FROM db_pipeline.card_limit_pool) AS card_limit_pool,
           (SELECT count(*) FROM db_pipeline.card_policy_evidence) AS card_evidence_link,
           (SELECT count(*) FROM db_pipeline.card_source_evidence) AS card_source_evidence;

-- ---------------------------------------------------------------------------
-- 3. 뷰 제거
-- ---------------------------------------------------------------------------
DROP VIEW db_pipeline.v_card_integrity_issue;
DROP VIEW db_pipeline.v_common_cd_usage;
DROP VIEW db_pipeline.v_card_bnft_rule_effective;
DROP VIEW db_pipeline.v_card_cond_atom;
DROP VIEW db_pipeline.v_card_limit_tier;
DROP VIEW db_pipeline.v_card_rule_target;
DROP VIEW db_pipeline.v_card_bnft_rel;
DROP VIEW db_pipeline.v_card_rule_pool;
DROP VIEW db_pipeline.v_card_rule;
DROP VIEW db_pipeline.v_card_policy_doc;
DROP VIEW db_pipeline.v_card_common_limit;
DROP VIEW db_pipeline.v_card_common_rule;

-- ---------------------------------------------------------------------------
-- 4. card_product: 카드 공통 조건 이관
-- ---------------------------------------------------------------------------
ALTER TABLE db_pipeline.card_product ADD COLUMN card_cond_expr jsonb;
ALTER TABLE db_pipeline.card_product ADD COLUMN card_cond_status_cd varchar(20) NOT NULL DEFAULT 'DRAFT';
ALTER TABLE db_pipeline.card_product
    ADD CONSTRAINT card_product_card_cond_expr_check CHECK (db_pipeline.fn_valid_cond_expr(card_cond_expr));
COMMENT ON COLUMN db_pipeline.card_product.card_cond_expr IS '카드 공통 조건';
COMMENT ON COLUMN db_pipeline.card_product.card_cond_status_cd IS '카드 공통 조건 상태';

-- policy_status_cd는 POLICY_STATUS, card_cond_status_cd는 ITEM_STATUS다. 값을 올리지 않고 같은 단계로 옮긴다.
UPDATE db_pipeline.card_product p
SET card_cond_expr = v.policy_cond_expr,
    card_cond_status_cd = CASE v.policy_status_cd
        WHEN 'DRAFT' THEN 'DRAFT'
        WHEN 'APPROVED' THEN 'CONFIRMED'
        WHEN 'RETIRED' THEN 'RETIRED'
    END
FROM db_pipeline.card_policy_version v
WHERE v.card_id = p.card_id;

-- ---------------------------------------------------------------------------
-- 5. card_product_doc 간소화 (이미 지워졌으면 건너뛴다)
-- ---------------------------------------------------------------------------
DROP INDEX IF EXISTS db_pipeline.card_product_doc_current_idx;
ALTER TABLE db_pipeline.card_product_doc DROP CONSTRAINT IF EXISTS card_product_doc_period_check;
ALTER TABLE db_pipeline.card_product_doc DROP CONSTRAINT IF EXISTS card_product_doc_approved_check;
ALTER TABLE db_pipeline.card_product_doc DROP COLUMN IF EXISTS effective_from;
ALTER TABLE db_pipeline.card_product_doc DROP COLUMN IF EXISTS effective_to_excl;
ALTER TABLE db_pipeline.card_product_doc ADD CONSTRAINT card_product_doc_approved_check CHECK
    (approval_status_cd <> 'APPROVED' OR length(trim(applicability_basis_txt)) > 0);

-- ---------------------------------------------------------------------------
-- 6. policy_ver_id 제거와 키 변경
-- ---------------------------------------------------------------------------
ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_pkey;
ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_card_id_policy_ver_id_bnft_cd_key;
ALTER TABLE db_pipeline.card_bnft DROP COLUMN policy_ver_id;
ALTER TABLE db_pipeline.card_bnft ADD PRIMARY KEY (card_id, card_bnft_id);
ALTER TABLE db_pipeline.card_bnft ADD UNIQUE (card_id, bnft_cd);

ALTER TABLE db_pipeline.card_limit_pool DROP CONSTRAINT card_limit_pool_pkey;
ALTER TABLE db_pipeline.card_limit_pool DROP COLUMN policy_ver_id;
ALTER TABLE db_pipeline.card_limit_pool ADD PRIMARY KEY (card_id, pool_id);

-- ---------------------------------------------------------------------------
-- 7. card_policy_evidence -> card_evidence_link
-- ---------------------------------------------------------------------------
ALTER TABLE db_pipeline.card_policy_evidence DROP CONSTRAINT card_policy_evidence_pkey;
ALTER TABLE db_pipeline.card_policy_evidence DROP CONSTRAINT card_policy_evidence_natural_key;
ALTER TABLE db_pipeline.card_policy_evidence DROP CONSTRAINT card_policy_evidence_ck_2;
DROP INDEX db_pipeline.ix_card_policy_evidence_subject;
ALTER TABLE db_pipeline.card_policy_evidence DROP COLUMN policy_ver_id;

UPDATE db_pipeline.card_policy_evidence SET ev_subject_cd = 'CARD' WHERE ev_subject_cd = 'POLICY';

ALTER TABLE db_pipeline.card_policy_evidence RENAME TO card_evidence_link;
ALTER TABLE db_pipeline.card_evidence_link RENAME CONSTRAINT card_policy_evidence_ck_1 TO card_evidence_link_ck_1;
ALTER INDEX db_pipeline.ix_card_policy_evidence_evidence RENAME TO ix_card_evidence_link_evidence;
ALTER SEQUENCE db_pipeline.seq_card_policy_evidence RENAME TO seq_card_evidence_link;
COMMENT ON SEQUENCE db_pipeline.seq_card_evidence_link IS 'card_evidence_link.ev_link_id 로컬 업무 ID 발급';

ALTER TABLE db_pipeline.card_evidence_link
    ALTER COLUMN ev_link_id SET DEFAULT db_pipeline.fn_get_biz_id('card_evidence_link');
ALTER TABLE db_pipeline.card_evidence_link ADD PRIMARY KEY (card_id, ev_link_id);
ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_natural_key UNIQUE NULLS NOT DISTINCT
    (card_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, pool_id, ev_item_cd, ev_item_key, evidence_id);
ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_ck_2 CHECK (
    CASE ev_subject_cd
        WHEN 'CARD' THEN num_nonnulls(card_bnft_id, rule_key, relation_key, pool_id) = 0
        WHEN 'BNFT' THEN card_bnft_id IS NOT NULL AND num_nonnulls(rule_key, relation_key, pool_id) = 0
        WHEN 'RULE' THEN card_bnft_id IS NOT NULL AND rule_key IS NOT NULL
                         AND num_nonnulls(relation_key, pool_id) = 0
        WHEN 'POOL' THEN pool_id IS NOT NULL AND num_nonnulls(card_bnft_id, rule_key, relation_key) = 0
        WHEN 'REL' THEN card_bnft_id IS NOT NULL AND relation_key IS NOT NULL
                        AND num_nonnulls(rule_key, pool_id) = 0
        ELSE false
    END);
CREATE INDEX ix_card_evidence_link_subject ON db_pipeline.card_evidence_link (card_id, ev_subject_cd, card_bnft_id, rule_key);
COMMENT ON TABLE db_pipeline.card_evidence_link IS '카드 근거 관계';

-- ---------------------------------------------------------------------------
-- 8. card_policy_version 제거
-- ---------------------------------------------------------------------------
DROP TABLE db_pipeline.card_policy_version;
DROP TABLE db_pipeline.card_method_catalog;
DROP SEQUENCE db_pipeline.seq_card_policy_version;
DROP FUNCTION db_pipeline.fn_valid_doc_ref_list(jsonb);

-- ---------------------------------------------------------------------------
-- 8-1. 공통 혜택 구조 제거. 브랜드 혜택은 카드별 card_bnft에 저장하고 문서·근거를 공유한다
-- ---------------------------------------------------------------------------
DROP TABLE db_pipeline.card_common_rule_evidence;
DROP TABLE db_pipeline.card_bnft_common;
DROP TABLE db_pipeline.card_common_policy_version;
DROP TABLE db_pipeline.card_common_bnft;
DROP SEQUENCE db_pipeline.seq_card_common_policy_version;
DROP SEQUENCE db_pipeline.seq_card_common_bnft;

-- 호출부(extraction_repository.sql)가 있어 2인자 시그니처를 유지한다. COMMON 분기만 없앤다.

-- 원본 규칙 JSON은 V6 복구 및 정확한 값 비교를 위해 백업 스키마에 보존한다.
CREATE TABLE db_pipeline_v6_backup.v7_rule_list_before_pool_split AS
SELECT card_id,card_bnft_id,rule_list FROM db_pipeline.card_bnft;
CREATE TEMP TABLE rule_pool_before ON COMMIT DROP AS
SELECT b.card_id,b.card_bnft_id,r.value->>'rule_key' AS rule_key,
       p.value->>'pool_id' AS pool_id,p.value->>'pool_role_cd' AS pool_role_cd
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) r(value)
CROSS JOIN LATERAL jsonb_array_elements(coalesce(r.value->'pool_refs','[]'::jsonb)) p(value);
DO $$
BEGIN
 IF EXISTS (
   SELECT 1 FROM db_pipeline.card_bnft b CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) r(value)
   CROSS JOIN LATERAL jsonb_array_elements(coalesce(r.value->'pool_refs','[]'::jsonb)) p(value)
   WHERE jsonb_typeof(p.value) <> 'object' OR (p.value - 'pool_id' - 'pool_role_cd') <> '{}'::jsonb
      OR jsonb_typeof(p.value->'pool_id') IS DISTINCT FROM 'string'
      OR jsonb_typeof(p.value->'pool_role_cd') IS DISTINCT FROM 'string'
 ) THEN RAISE EXCEPTION '한도 참조에 보존할 수 없는 필드 또는 값이 있습니다'; END IF;
 IF EXISTS (SELECT 1 FROM rule_pool_before GROUP BY card_id,card_bnft_id,rule_key,pool_id HAVING count(*) > 1)
 THEN RAISE EXCEPTION '중복된 규칙·한도 관계가 있습니다'; END IF;
 IF EXISTS (SELECT 1 FROM rule_pool_before x
     WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id=x.card_id)
        OR NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id,b.card_bnft_id)=(x.card_id,x.card_bnft_id))
        OR NOT EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id,p.pool_id)=(x.card_id,x.pool_id))
        OR NOT EXISTS (SELECT 1 FROM db_pipeline.common_cd c WHERE c.common_code_grp_id='POOL_ROLE' AND c.common_cd=x.pool_role_cd))
 THEN RAISE EXCEPTION '고아 또는 미등록 역할 관계가 있습니다'; END IF;
END $$;

CREATE TABLE db_pipeline.card_bnft_rule_pool (
    card_id bigint NOT NULL,
    card_bnft_id varchar(20) NOT NULL,
    rule_key varchar(40) NOT NULL,
    pool_id varchar(20) NOT NULL,
    pool_role_cd varchar(30) NOT NULL,
    PRIMARY KEY (card_id, card_bnft_id, rule_key, pool_id)
);
COMMENT ON TABLE db_pipeline.card_bnft_rule_pool IS '카드 혜택 규칙과 한도 풀의 논리적 관계. 물리 FK 없음';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.card_id IS '카드 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.card_bnft_id IS '혜택 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.rule_key IS '계산 규칙 키';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.pool_id IS '한도 풀 아이디';
COMMENT ON COLUMN db_pipeline.card_bnft_rule_pool.pool_role_cd IS '한도 풀 역할';

INSERT INTO db_pipeline.card_bnft_rule_pool(card_id,card_bnft_id,rule_key,pool_id,pool_role_cd)
SELECT card_id,card_bnft_id,rule_key,pool_id,pool_role_cd FROM rule_pool_before;
DO $$ BEGIN
 IF EXISTS ((SELECT * FROM rule_pool_before EXCEPT ALL SELECT * FROM db_pipeline.card_bnft_rule_pool)
            UNION ALL (SELECT * FROM db_pipeline.card_bnft_rule_pool EXCEPT ALL SELECT * FROM rule_pool_before))
 THEN RAISE EXCEPTION '규칙·한도 이관 결과가 원본과 다릅니다'; END IF;
END $$;
UPDATE db_pipeline.card_bnft b SET rule_list = x.rules
FROM (SELECT b2.card_id,b2.card_bnft_id,coalesce(jsonb_agg(r.value-'pool_refs' ORDER BY r.ord)
     FILTER (WHERE r.value IS NOT NULL),'[]'::jsonb) AS rules
      FROM db_pipeline.card_bnft b2 LEFT JOIN LATERAL jsonb_array_elements(b2.rule_list)
      WITH ORDINALITY r(value,ord) ON true GROUP BY b2.card_id,b2.card_bnft_id) x
WHERE (b.card_id,b.card_bnft_id)=(x.card_id,x.card_bnft_id);

CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_rule_list(p_list jsonb, p_owner text) RETURNS boolean
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
DROP FUNCTION db_pipeline.fn_valid_limit_list(jsonb);

ALTER TABLE db_pipeline.card_bnft DROP CONSTRAINT card_bnft_ck_5;
ALTER TABLE db_pipeline.card_bnft ADD CONSTRAINT card_bnft_ck_5 CHECK (bnft_origin_cd <> 'BRAND_SERVICE' OR bnft_scope_cd = 'BRAND');
ALTER TABLE db_pipeline.card_bnft ADD COLUMN bnft_valid_from date;
ALTER TABLE db_pipeline.card_bnft ADD COLUMN bnft_valid_to_excl date;
ALTER TABLE db_pipeline.card_bnft ADD CONSTRAINT card_bnft_ck_6 CHECK
    (bnft_valid_to_excl IS NULL OR bnft_valid_from IS NULL OR bnft_valid_to_excl > bnft_valid_from);
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_from IS '혜택 제공 시작일';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_valid_to_excl IS '혜택 제공 종료일(미포함)';

-- 공통 PDF는 카드 등록 전에도 추출한다. NULL은 카드 미연결 후보이며 공통 혜택 확정을 뜻하지 않는다.
ALTER TABLE db_pipeline.card_extr_stg ALTER COLUMN card_id DROP NOT NULL;
COMMENT ON COLUMN db_pipeline.card_extr_stg.card_id IS '카드 아이디(NULL이면 특정 카드에 연결되지 않은 후보)';

-- ---------------------------------------------------------------------------
-- 9. 공통코드: 코드 교체와 삭제, 달라진 설명만 갱신 (보류 2건은 건드리지 않는다)
-- ---------------------------------------------------------------------------
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '계산 규칙이 연결된 한도 풀을 어떤 역할로 소비하는지 구분하는 공통코드. card_bnft_rule_pool.pool_role_cd에서 사용한다. 한 규칙이 영역 한도와 카드 통합 한도를 동시에 소비하는 구조를 표현하기 위한 값이며, 풀 자체의 범위는 LIMIT_SCOPE가 정한다.' WHERE common_code_grp_id = 'POOL_ROLE';

UPDATE db_pipeline.common_cd
SET common_cd = 'CARD', common_cd_nm = '카드', common_cd_desc = '근거가 카드 공통 조건이나 상품 전체를 뒷받침하는 경우. 특정 혜택에 속하지 않는 내용에 쓰며 혜택, 규칙, 관계, 풀 컬럼은 모두 비워야 한다.',
    update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'EV_SUBJECT' AND common_cd = 'POLICY';

UPDATE db_pipeline.common_cd
SET common_cd = 'BRAND_SERVICE', common_cd_nm = '브랜드 공통 서비스', common_cd_desc = '국제 브랜드 서비스 안내서에 근거해 카드별로 등록한 혜택. 계산 규칙은 카드의 rule_list에 직접 두고 원문 근거는 공통 PDF의 근거를 공유한다. bnft_scope_cd가 BRAND여야 하고(card_bnft_ck_5), 적용 선택지에 BRAND_SERVICE 문서 연결이 없으면 게이트 brand_bnft_doc_not_linked에서 검출된다.',
    update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'BNFT_ORIGIN' AND common_cd = 'COMMON_LINK';
UPDATE db_pipeline.common_cd SET common_cd_nm = '상품 고유 혜택', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'BNFT_ORIGIN' AND common_cd = 'LOCAL';

-- 사용처가 없어진 코드만 삭제한다. 원본은 db_pipeline_v6_backup에 있다.
DELETE FROM db_pipeline.common_cd WHERE common_code_grp_id = 'POLICY_STATUS';
DELETE FROM db_pipeline.common_code_grp WHERE common_code_grp_id = 'POLICY_STATUS';
DELETE FROM db_pipeline.common_cd WHERE common_code_grp_id = 'EV_ITEM' AND common_cd = 'LIMIT';
DELETE FROM db_pipeline.common_cd WHERE common_code_grp_id IN ('METHOD_KIND', 'METHOD_STATUS');
DELETE FROM db_pipeline.common_code_grp WHERE common_code_grp_id IN ('METHOD_KIND', 'METHOD_STATUS');

UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '원천 문서가 특정 상품에서 어떤 역할을 하는지 구분하는 공통코드. card_product_doc.doc_role_cd에서 사용한다. 문서 자체의 종류를 나타내는 DOC_TYPE과 달리 상품과의 관계에 붙는 값이므로 같은 문서라도 연결 상품에 따라 역할을 따로 기록한다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'DOC_ROLE';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '계산 규칙, 조건식, 카드 공통 조건이 작성 중인지 확정되었는지를 구분하는 공통코드. JSONB 안의 rule_status_cd, cond_status_cd, expr_status_cd와 card_product.card_cond_status_cd에서 사용한다. 혜택 단위 검증을 나타내는 VERIFY_STATUS보다 작은 규칙·조건 단위의 상태다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'ITEM_STATUS';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '조건식 atom의 업무 유형을 분류하는 공통코드. 조건식 atom의 cond_type_cd에서 사용하고 카드 공통, 혜택, 규칙, 한도 구간의 조건에 모두 적용된다. 금액을 어떤 기준으로 비교하는지는 COND_BASIS가, 금액 구간으로 표현되지 않는 판정법은 PREDICATE_METHOD가 맡는다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'COND_TYPE';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '원문 근거가 어떤 카드 대상을 뒷받침하는지 구분하는 공통코드. card_evidence_link.ev_subject_cd에서 사용하며 값에 따라 card_bnft_id, rule_key, relation_key, pool_id 중 채워야 할 컬럼이 CHECK로 고정된다. 대상 안의 세부 항목은 EV_ITEM이 구분한다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'EV_SUBJECT';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '근거가 대상 전체를 가리키는지 대상 안의 JSONB 항목을 가리키는지 구분하는 공통코드. card_evidence_link.ev_item_cd에서 사용하고 ev_item_key와 짝을 이룬다. 대상의 종류를 나타내는 EV_SUBJECT보다 한 단계 아래를 가리킨다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'EV_ITEM';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '수집된 원천 문서를 파이프라인에서 사용할지 구분하는 공통코드. card_doc.doc_status에서 사용하며 AI 입력 대상은 ACTIVE 문서로 제한된다. 상품별 적용 여부는 이 값이 아니라 승인된 문서 관계로 판정하며, 판매 상태를 나타내는 PRODUCT_STATUS와도 구분된다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'DOC_STATUS';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '문서 연결과 원문 근거처럼 검토·승인이 필요한 관계·근거 데이터의 처리 상태를 구분하는 공통코드. card_product_doc.approval_status_cd, card_source_evidence.approval_status_cd에서 사용하며 실제 승인 대상은 사용하는 테이블에 따라 달라진다. 규칙·조건을 다루는 ITEM_STATUS, AI 추출 항목을 다루는 STG_STATUS와 관리 대상이 다르다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'APPROVAL_STATUS';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '혜택의 원천을 구분하는 공통코드. card_bnft.bnft_origin_cd에서 사용한다. 출처와 관계없이 계산 규칙은 모두 card_bnft.rule_list에 있으며, 혜택이 어느 브랜드 선택지에 적용되는지를 나타내는 BNFT_SCOPE와는 별개의 축이다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'BNFT_ORIGIN';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '규칙이나 한도 구간의 적용 여부를 조건식으로 어떻게 판정할지 구분하는 공통코드. card_bnft.rule_list[].predicate_state_cd와 card_limit_pool.tier_list[].predicate_state_cd에서 사용한다. 조건식이 없다는 사실만으로 무조건 적용으로 해석하지 않도록, 원문으로 확인된 무조건과 미검토를 구분한다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'PREDICATE_STATE';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '한도가 누적되는 시간 단위를 구분하는 공통코드. card_limit_pool.period_cd에서 사용한다. 한도를 묶는 혜택 범위인 LIMIT_SCOPE, 한도의 단위인 LIMIT_UNIT과 함께 한도 하나를 정의한다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'LIMIT_PERIOD';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '한도 수치 limit_num이 어떤 단위인지 구분하는 공통코드. card_limit_pool.cap_unit_cd에서 사용한다. 보상 지급 단위인 PAYOUT_UNIT과 달리 금액뿐 아니라 이용 횟수도 포함한다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'LIMIT_UNIT';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '한도 사용액을 어떤 주체 단위로 합산할지 구분하는 공통코드. card_limit_pool.aggregation_key_cd에서 사용한다. 어떤 혜택을 묶는지를 나타내는 LIMIT_SCOPE와 달리 누구의 사용분을 합칠지를 나타낸다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'LIMIT_AGG';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '카드 상품의 브랜드 선택지를 구분하는 공통코드. card_product.brand_opt_list[].brand_cd에서 사용한다. 그룹명은 국제 브랜드이지만 국내전용 선택지를 함께 포함하며, 브랜드 안의 등급은 SERVICE_GRADE, 선택서비스 유형은 SERVICE_TYPE이 구분한다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'BRAND';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '국제 브랜드 서비스의 등급을 구분하는 공통코드. card_product.brand_opt_list[].service_grade_cd에서 사용한다. BRAND와 조합해야 의미가 정해지며, 등급 안의 공통·선택서비스 구분은 SERVICE_TYPE이 맡는다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'SERVICE_GRADE';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '같은 브랜드와 등급 안에서 제공되는 서비스 묶음의 유형을 구분하는 공통코드. card_product.brand_opt_list[].service_type_cd에서 사용한다. 번호 코드는 BRAND, SERVICE_GRADE와 조합할 때만 의미가 정해지며 어떤 상품이 어떤 유형인지는 브랜드 서비스 안내서의 대상카드 표를 따른다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'SERVICE_TYPE';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '카드 상품과 상품 안의 브랜드 선택지가 현재 판매되는지를 구분하는 공통코드. card_product.product_status_cd와 card_product.brand_opt_list[].brand_opt_status_cd에서 사용한다. 데이터 처리 상태가 아니라 판매 사실을 나타낸다는 점에서 문서 상태 DOC_STATUS의 같은 값 ACTIVE와 구분된다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'PRODUCT_STATUS';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '규칙이 한 거래의 후보 보상을 어떤 방식으로 산출하는지 구분하는 공통코드. rule_list[].calc_method_cd에서 사용하고, 코드별 value_num의 의미가 정해져 있다. 조건 판정 방법인 PREDICATE_METHOD와 구분된다. 규칙의 method_ver는 표현 계약 버전으로 현재 1이며 계산 실행 엔진의 버전을 뜻하지 않는다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'CALC_METHOD';
UPDATE db_pipeline.common_code_grp SET common_code_grp_desc = '금액 구간만으로 표현되지 않는 조건을 판정하는 방법을 구분하는 공통코드. 조건 atom의 predicate_method_cd에서 사용하며 세부 값은 cond_params에 둔다. 보상 금액을 산출하는 CALC_METHOD와 달리 조건의 참·거짓만 판정한다. predicate_method_ver는 표현 계약 버전으로 현재 1이며 실행 엔진의 버전을 뜻하지 않는다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'PREDICATE_METHOD';
UPDATE db_pipeline.common_cd SET common_cd_desc = '대상 데이터가 해당 업무의 검증 기준을 충족해 사용 승인을 받은 상태. 문서 연결은 적용 근거가 있어야 승인할 수 있고(card_product_doc_approved_check), 근거는 이 값일 때만 게이트 evidence_not_approved를 통과한다. 승인 대상과 범위는 사용하는 테이블에 따라 결정된다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'APPROVAL_STATUS' AND common_cd = 'APPROVED';
UPDATE db_pipeline.common_cd SET common_cd_desc = '규칙 또는 조건이 작성 중이라 아직 확정되지 않은 상태. AI 추출 결과를 정규화할 때 부여하는 초기값이며 card_product.card_cond_status_cd의 기본값이다. 혜택 전체가 아니라 규칙·조건 단위의 상태다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'ITEM_STATUS' AND common_cd = 'DRAFT';
UPDATE db_pipeline.common_cd SET common_cd_desc = '해당 상품 고유의 혜택. 상품설명서 등 상품 문서에 근거하며 현재 추출기는 모든 혜택을 이 값으로 정규화한다. 브랜드 서비스 안내서에 근거한 BRAND_SERVICE와 구분된다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'BNFT_ORIGIN' AND common_cd = 'LOCAL';
UPDATE db_pipeline.common_cd SET common_cd_desc = '가맹점이나 업종의 분류 기준에 관한 조건. 모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공한다는 카드 공통 조건이 해당한다. 개별 대상 가맹점은 target_list에 두고 이 유형은 판정 기준을 담는다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'COND_TYPE' AND common_cd = 'MERCHANT_RULE';
UPDATE db_pipeline.common_cd SET common_cd_desc = '근거가 조건식의 atom 하나를 가리키는 경우. ev_item_key에 atom_key를 저장한다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'EV_ITEM' AND common_cd = 'COND';
UPDATE db_pipeline.common_cd SET common_cd_desc = '근거가 규칙 대상 하나를 가리키는 경우. ev_item_key에 target_key를 저장한다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'EV_ITEM' AND common_cd = 'TARGET';
UPDATE db_pipeline.common_cd SET common_cd_desc = '근거가 상품 한도 풀의 구간 하나를 가리키는 경우. ev_item_key에 tier_key를 저장한다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'EV_ITEM' AND common_cd = 'TIER';
UPDATE db_pipeline.common_cd SET common_cd_desc = '대상 문서 연결 또는 원문 근거의 정확성과 적용 여부에 대한 검토가 끝나지 않은 상태. 업무 사용 승인 전 단계이며 card_product_doc의 기본값이다. 이 상태의 근거가 카드 항목에 연결되어 있으면 게이트 evidence_not_approved에서 검출된다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'APPROVAL_STATUS' AND common_cd = 'PENDING';
UPDATE db_pipeline.common_cd SET common_cd_desc = '브랜드 서비스 등급이 없거나 해당하지 않는 경우. 등급 정보가 없는 브랜드 선택지에 쓴다. 등급을 확인하지 못했다는 뜻이 아니라 적용할 등급이 없다는 뜻이다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'SERVICE_GRADE' AND common_cd = 'NONE';
UPDATE db_pipeline.common_cd SET common_cd_desc = '브랜드 서비스 유형 구분이 없거나 해당하지 않는 경우. 공통 서비스와 선택서비스 어느 쪽도 아닐 때 쓴다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'SERVICE_TYPE' AND common_cd = 'NONE';
UPDATE db_pipeline.common_cd SET common_cd_desc = '국제 브랜드의 등급별 서비스를 안내하는 문서. Visa, Mastercard, AMEX, JCB, UnionPay 안내서가 해당하며 여러 카드가 공유하는 문서로 한 번만 등록한다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'DOC_TYPE' AND common_cd = 'BRAND_SERVICE';
UPDATE db_pipeline.common_cd SET common_cd_desc = '상품 또는 브랜드 선택지가 판매 중인 상태. 상품 등록의 기본값이다. 데이터 사용 가능 여부가 아닌 판매 사실을 나타내므로 DOC_STATUS.ACTIVE(문서 사용 중)와 의미가 다르다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'PRODUCT_STATUS' AND common_cd = 'ACTIVE';
UPDATE db_pipeline.common_cd SET common_cd_desc = '조건을 충족한 결제 1건마다 정해진 금액이나 포인트·마일리지를 제공하는 방식. value_num은 건당 수량이며 ONE PICK의 100원, 500원 캐시백이 해당한다. 결제금액에 비례하는 PERCENT_OF_TXN, 금액 구간마다 적립하는 UNITS_PER_AMOUNT와 구분된다.', update_date = now(), update_user_id = 'V7_MIGRATION'
WHERE common_code_grp_id = 'CALC_METHOD' AND common_cd = 'FIXED_PER_TXN';

-- ---------------------------------------------------------------------------
-- 10. 뷰 재생성
-- ---------------------------------------------------------------------------
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

CREATE VIEW db_pipeline.v_card_rule_pool AS
SELECT card_id, card_bnft_id, rule_key, pool_id, pool_role_cd
FROM db_pipeline.card_bnft_rule_pool;

COMMENT ON VIEW db_pipeline.v_card_rule_pool IS '규칙↔한도 풀 연결 테이블 조회';

CREATE VIEW db_pipeline.v_card_bnft_rel AS
SELECT b.card_id, b.card_bnft_id AS from_bnft_id,
       x.value->>'to_bnft_id' AS to_bnft_id,
       x.value->>'relation_key' AS relation_key,
       x.value->>'rel_type_cd' AS rel_type_cd,
       x.value->>'trigger_pool_id' AS trigger_pool_id,
       (x.value->>'rel_priority')::integer AS rel_priority,
       false AS reverse_yn
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) AS x(value)
UNION ALL
SELECT b.card_id, x.value->>'to_bnft_id',
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
SELECT r.card_id, r.card_bnft_id, r.rule_key,
       t.value->>'target_type_cd' AS target_type_cd,
       t.value->>'target_key' AS target_key,
       t.value->>'target_nm' AS target_nm
FROM db_pipeline.v_card_rule r
CROSS JOIN LATERAL jsonb_array_elements(r.target_list) AS t(value);

COMMENT ON VIEW db_pipeline.v_card_rule_target IS '규칙 대상을 행으로 복원';

CREATE VIEW db_pipeline.v_card_limit_tier AS
SELECT p.card_id, p.pool_id, p.pool_scope_cd, p.period_cd, p.cap_unit_cd,
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

CREATE VIEW db_pipeline.v_card_cond_atom AS
WITH src AS (
    SELECT 'CARD'::text AS owner_cd, p.card_id, NULL::varchar AS card_bnft_id,
           NULL::text AS rule_key, NULL::varchar AS pool_id, NULL::text AS item_key,
           p.card_cond_expr AS expr
    FROM db_pipeline.card_product p WHERE p.card_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'BNFT', b.card_id, b.card_bnft_id, NULL, NULL, NULL, b.bnft_cond_expr
    FROM db_pipeline.card_bnft b WHERE b.bnft_cond_expr IS NOT NULL
    UNION ALL
    SELECT 'RULE', r.card_id, r.card_bnft_id, r.rule_key, NULL, NULL, r.cond_expr
    FROM db_pipeline.v_card_rule r WHERE r.cond_expr IS NOT NULL
    UNION ALL
    SELECT 'POOL_TIER', t.card_id, NULL, NULL, t.pool_id, t.tier_key, t.cond_expr
    FROM db_pipeline.v_card_limit_tier t WHERE t.cond_expr IS NOT NULL
)
SELECT s.owner_cd, s.card_id, s.card_bnft_id, s.rule_key, s.pool_id, s.item_key,
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
SELECT 'card_bnft_rule_pool.pool_role_cd', 'POOL_ROLE', pool_role_cd::text
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
SELECT 'pool_without_product', x.card_id || '/' || x.pool_id
FROM db_pipeline.card_limit_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id = x.card_id)
UNION ALL
SELECT 'pool_ref_orphan', x.card_id || '/' || x.rule_key || '/' || x.pool_id
FROM db_pipeline.v_card_rule_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id, p.pool_id) = (x.card_id, x.pool_id))
UNION ALL
SELECT 'rule_pool_product_orphan', x.card_id || '/' || x.card_bnft_id || '/' || x.rule_key || '/' || x.pool_id
FROM db_pipeline.card_bnft_rule_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product p WHERE p.card_id=x.card_id)
UNION ALL
SELECT 'rule_pool_benefit_orphan', x.card_id || '/' || x.card_bnft_id || '/' || x.rule_key || '/' || x.pool_id
FROM db_pipeline.card_bnft_rule_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id,b.card_bnft_id)=(x.card_id,x.card_bnft_id))
UNION ALL
SELECT 'rule_pool_rule_orphan', x.card_id || '/' || x.card_bnft_id || '/' || x.rule_key || '/' || x.pool_id
FROM db_pipeline.card_bnft_rule_pool x
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.v_card_rule r WHERE (r.card_id,r.card_bnft_id,r.rule_key)=(x.card_id,x.card_bnft_id,x.rule_key))
UNION ALL
SELECT 'rel_to_bnft_orphan', x.card_id || '/' || x.relation_key
FROM db_pipeline.v_card_bnft_rel x
WHERE NOT x.reverse_yn
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft b WHERE (b.card_id, b.card_bnft_id) = (x.card_id, x.to_bnft_id))
UNION ALL
SELECT 'rel_trigger_pool_orphan', x.card_id || '/' || x.relation_key
FROM db_pipeline.v_card_bnft_rel x
WHERE NOT x.reverse_yn AND x.trigger_pool_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id, p.pool_id) = (x.card_id, x.trigger_pool_id))
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
    WHEN 'POOL' THEN EXISTS (SELECT 1 FROM db_pipeline.card_limit_pool p WHERE (p.card_id, p.pool_id) = (l.card_id, l.pool_id))
    WHEN 'REL' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_bnft_rel r WHERE NOT r.reverse_yn AND (r.card_id, r.from_bnft_id, r.relation_key) = (l.card_id, l.card_bnft_id, l.relation_key))
    ELSE false
END
UNION ALL
SELECT 'evidence_item_key_missing', l.card_id || '/' || l.ev_link_id
FROM db_pipeline.card_evidence_link l
WHERE l.ev_item_cd <> 'SELF' AND NOT CASE l.ev_item_cd
    WHEN 'COND' THEN EXISTS (SELECT 1 FROM atoms a WHERE a.card_id = l.card_id AND a.atom_key = l.ev_item_key
                             AND a.card_bnft_id IS NOT DISTINCT FROM l.card_bnft_id AND a.rule_key IS NOT DISTINCT FROM l.rule_key AND a.pool_id IS NOT DISTINCT FROM l.pool_id)
    WHEN 'TARGET' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_rule_target t WHERE (t.card_id, t.card_bnft_id, t.rule_key) = (l.card_id, l.card_bnft_id, l.rule_key) AND t.target_key = l.ev_item_key)
    WHEN 'TIER' THEN EXISTS (SELECT 1 FROM db_pipeline.v_card_limit_tier t WHERE (t.card_id, t.pool_id) = (l.card_id, l.pool_id) AND t.tier_key = l.ev_item_key)
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

COMMENT ON SCHEMA db_pipeline IS '카드 상품 중심 V7 공통코드·반정규화 스키마(초안)';

-- ---------------------------------------------------------------------------
-- 11. 사후 검사
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    c db_pipeline_v6_backup.row_counts%ROWTYPE;
    v_bad text;
BEGIN
    SELECT * INTO c FROM db_pipeline_v6_backup.row_counts;
    IF c.card_product <> (SELECT count(*) FROM db_pipeline.card_product)
       OR c.card_bnft <> (SELECT count(*) FROM db_pipeline.card_bnft)
       OR c.card_limit_pool <> (SELECT count(*) FROM db_pipeline.card_limit_pool)
       OR c.card_evidence_link <> (SELECT count(*) FROM db_pipeline.card_evidence_link)
       OR c.card_source_evidence <> (SELECT count(*) FROM db_pipeline.card_source_evidence) THEN
        RAISE EXCEPTION '이관 전후 행 수가 다릅니다';
    END IF;

    IF EXISTS (SELECT 1 FROM db_pipeline_v6_backup.card_policy_version v
               JOIN db_pipeline.card_product p USING (card_id)
               WHERE p.card_cond_expr IS DISTINCT FROM v.policy_cond_expr) THEN
        RAISE EXCEPTION '카드 공통 조건이 원본과 다릅니다';
    END IF;

    SELECT string_agg(DISTINCT gate_cd, ', ') INTO v_bad
    FROM db_pipeline.v_card_integrity_issue
    WHERE gate_cd NOT IN ('evidence_not_approved', 'rule_method_value_pending', 'predicate_params_pending');
    IF v_bad IS NOT NULL THEN
        RAISE EXCEPTION '정합성 게이트 위반: %', v_bad;
    END IF;
END;
$$;

COMMIT;
