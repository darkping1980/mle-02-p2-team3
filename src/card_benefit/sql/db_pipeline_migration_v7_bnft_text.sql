-- V7 혜택·한도 TEXT 단순화. card_limit_pool, card_bnft_rule_pool을 제거하고 혜택 설명과 한도를 card_bnft TEXT로 일원화한다.
-- 선행: db_pipeline_backup 백업 4개와 card_bnft TEXT 이관(2026-11-02 사용자 실행 완료), db_pipeline_v7_bnft_text_precheck.sql 통과.
-- DBeaver: 스크립트 전체 실행(Alt+X)으로 돌린다. 문장 단위 실행(Ctrl+Enter)을 쓰지 않는다.
-- 단일 트랜잭션이다. 중간에 실패하면 COMMIT이 ROLLBACK으로 끝나 아무것도 바뀌지 않는다.
-- 재실행 안전: 이미 적용된 DB에서 다시 실행하면 가드를 건너뛰고 같은 구조로 수렴한다. 데이터를 다시 지우지 않는다.
-- DROP ... CASCADE를 쓰지 않는다. 뜻밖의 의존 객체가 있으면 DROP이 실패해 전체가 취소된다.
-- 물리 FK는 만들지 않는다. 공통코드와 다른 테이블의 데이터는 바꾸지 않는다.
-- 사후 확인: db_pipeline_v7_bnft_text_postcheck.sql. 복구: db_pipeline_migration_v7_bnft_text_rollback.sql.
BEGIN;
SET LOCAL lock_timeout = '10s';
DO $$
BEGIN
    IF to_regnamespace('db_pipeline_backup') IS NULL
       OR to_regclass('db_pipeline_backup.card_limit_pool_20261102') IS NULL
       OR to_regclass('db_pipeline_backup.card_bnft_rule_pool_20261102') IS NULL
       OR to_regclass('db_pipeline_backup.card_evidence_link_pre_simplify_20261102') IS NULL
       OR to_regclass('db_pipeline_backup.card_bnft_pre_simplify_20261102') IS NULL THEN
        RAISE EXCEPTION '백업이 없어 중단합니다: db_pipeline_backup의 4개 백업 테이블이 필요합니다';
    END IF;
    IF to_regclass('db_pipeline.card_limit_pool') IS NOT NULL THEN
        LOCK TABLE db_pipeline.card_bnft, db_pipeline.card_evidence_link, db_pipeline.card_limit_pool,
                   db_pipeline.card_bnft_rule_pool IN SHARE ROW EXCLUSIVE MODE;
    ELSE
        LOCK TABLE db_pipeline.card_bnft, db_pipeline.card_evidence_link IN SHARE ROW EXCLUSIVE MODE;
    END IF;
END;
$$;
-- 1. TEXT 컬럼. 이미 있으면 그대로 둔다.
ALTER TABLE db_pipeline.card_bnft ADD COLUMN IF NOT EXISTS bnft_rule_txt text;
ALTER TABLE db_pipeline.card_bnft ADD COLUMN IF NOT EXISTS bnft_limit_txt text;
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_rule_txt IS '공식 원문 근거에서 모은 혜택 계산 규칙 안내. 계산 확정값이 아니라 검토 대상 텍스트';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_limit_txt IS '원문 근거에서 모은 혜택별 이용/금액 한도. 여러 풀의 근거를 혜택별로 중복 제거한 텍스트';
-- 2. 가드. 사전 검증 SQL과 같은 조건이다. 하나라도 어긋나면 아무것도 지우지 않고 중단한다.
DO $$
DECLARE
    v_fail text;
BEGIN
    IF to_regclass('db_pipeline.card_limit_pool') IS NULL AND to_regclass('db_pipeline.card_bnft_rule_pool') IS NULL THEN
        RAISE NOTICE '두 테이블이 이미 없어 가드를 건너뜁니다. 재실행입니다';
        RETURN;
    END IF;
    IF to_regclass('db_pipeline.card_limit_pool') IS NULL OR to_regclass('db_pipeline.card_bnft_rule_pool') IS NULL THEN
        RAISE EXCEPTION '두 테이블 중 하나만 남아 있습니다. 상태를 확인하세요';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM db_pipeline_backup.card_evidence_link_pre_simplify_20261102 WHERE ev_subject_cd <> 'POOL') THEN
        RAISE EXCEPTION '근거 백업이 비어 있습니다';
    END IF;
    SELECT string_agg(check_cd || '(' || actual || '/' || expected || ')', ', ' ORDER BY check_cd) INTO v_fail
    FROM (
SELECT 'B01' AS check_cd, '백업 card_limit_pool과 현재 행 차이' AS check_nm, 0::bigint AS expected,
       (SELECT count(*) FROM ((SELECT * FROM db_pipeline.card_limit_pool EXCEPT ALL SELECT * FROM db_pipeline_backup.card_limit_pool_20261102)
        UNION ALL (SELECT * FROM db_pipeline_backup.card_limit_pool_20261102 EXCEPT ALL SELECT * FROM db_pipeline.card_limit_pool)) d) AS actual
UNION ALL
SELECT 'B02', '백업 card_bnft_rule_pool과 현재 행 차이', 0,
       (SELECT count(*) FROM ((SELECT * FROM db_pipeline.card_bnft_rule_pool EXCEPT ALL SELECT * FROM db_pipeline_backup.card_bnft_rule_pool_20261102)
        UNION ALL (SELECT * FROM db_pipeline_backup.card_bnft_rule_pool_20261102 EXCEPT ALL SELECT * FROM db_pipeline.card_bnft_rule_pool)) d)
UNION ALL
SELECT 'B03', '백업 POOL 근거와 현재 POOL 근거 차이', 0,
       (SELECT count(*) FROM ((SELECT card_id,ev_link_id,pool_id,ev_item_cd,ev_item_key,evidence_id FROM db_pipeline.card_evidence_link WHERE ev_subject_cd = 'POOL'
          EXCEPT ALL SELECT card_id,ev_link_id,pool_id,ev_item_cd,ev_item_key,evidence_id FROM db_pipeline_backup.card_evidence_link_pre_simplify_20261102 WHERE ev_subject_cd = 'POOL')
        UNION ALL (SELECT card_id,ev_link_id,pool_id,ev_item_cd,ev_item_key,evidence_id FROM db_pipeline_backup.card_evidence_link_pre_simplify_20261102 WHERE ev_subject_cd = 'POOL'
          EXCEPT ALL SELECT card_id,ev_link_id,pool_id,ev_item_cd,ev_item_key,evidence_id FROM db_pipeline.card_evidence_link WHERE ev_subject_cd = 'POOL')) d)
UNION ALL
SELECT 'B04', '백업 card_bnft와 현재 행 차이(TEXT 제외, 검증 상태 포함)', 0,
       (SELECT count(*) FROM ((SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline.card_bnft EXCEPT ALL SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline_backup.card_bnft_pre_simplify_20261102)
        UNION ALL (SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline_backup.card_bnft_pre_simplify_20261102 EXCEPT ALL SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline.card_bnft)) d)
UNION ALL
SELECT 'T01', '한도 풀을 쓰는 혜택 중 bnft_limit_txt가 비어 있는 혜택', 0,
       (SELECT count(*) FROM db_pipeline.card_bnft b
        WHERE coalesce(trim(b.bnft_limit_txt), '') = ''
          AND EXISTS (SELECT 1 FROM db_pipeline.card_bnft_rule_pool x WHERE (x.card_id, x.card_bnft_id) = (b.card_id, b.card_bnft_id)))
UNION ALL
SELECT 'T02', '규칙이 있는 혜택 중 bnft_rule_txt가 비어 있는 혜택', 0,
       (SELECT count(*) FROM db_pipeline.card_bnft b
        WHERE coalesce(trim(b.bnft_rule_txt), '') = '' AND jsonb_array_length(b.rule_list) > 0)
UNION ALL
SELECT 'T03', '한도 구간 값이 해당 혜택 bnft_limit_txt에 없는 건', 0,
       (SELECT count(*) FROM db_pipeline.card_limit_pool p
        CROSS JOIN LATERAL jsonb_array_elements(p.tier_list) AS t(value)
        CROSS JOIN LATERAL (SELECT trim_scale((t.value->>'limit_num')::numeric) AS n) v
        CROSS JOIN LATERAL (SELECT CASE p.period_cd WHEN 'TXN' THEN '건당' WHEN 'DAY' THEN '일' WHEN 'MONTH' THEN '월' WHEN 'YEAR' THEN '연' END
             || CASE WHEN p.cap_unit_cd = 'COUNT' THEN v.n::text || '회'
                     WHEN p.cap_unit_cd = 'KRW' AND v.n % 10000 = 0 THEN (v.n / 10000)::int::text || '만원'
                     WHEN p.cap_unit_cd = 'KRW' AND v.n % 1000 = 0 THEN (v.n / 1000)::int::text || '천원'
                     WHEN p.cap_unit_cd = 'KRW' THEN v.n::text || '원' END AS txt) e
        JOIN (SELECT DISTINCT card_id, pool_id, card_bnft_id FROM db_pipeline.card_bnft_rule_pool) x ON (x.card_id, x.pool_id) = (p.card_id, p.pool_id)
        JOIN db_pipeline.card_bnft b ON (b.card_id, b.card_bnft_id) = (x.card_id, x.card_bnft_id)
        WHERE e.txt IS NULL OR position(e.txt IN regexp_replace(coalesce(b.bnft_limit_txt, ''), '\s', '', 'g')) = 0)
UNION ALL
SELECT 'T04', 'TEXT 세그먼트 중 해당 혜택의 연결 원문 인용에 없는 건', 0,
       (SELECT count(*) FROM db_pipeline.card_bnft b
        CROSS JOIN LATERAL (VALUES (b.bnft_rule_txt), (b.bnft_limit_txt)) k(txt)
        CROSS JOIN LATERAL regexp_split_to_table(k.txt, '\s+/\s+') AS s(seg)
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_evidence_link l
                          JOIN db_pipeline.card_source_evidence e ON e.evidence_id = l.evidence_id
                          WHERE (l.card_id, l.card_bnft_id) = (b.card_id, b.card_bnft_id)
                            AND position(regexp_replace(s.seg, '\s', '', 'g') IN regexp_replace(e.quote_txt, '\s', '', 'g')) > 0))
UNION ALL
SELECT 'E01', 'POOL 근거 중 소비 혜택의 BNFT/SELF 근거가 없는 건(MISSING)', 0,
       (SELECT count(*) FROM db_pipeline.card_evidence_link l
        JOIN (SELECT DISTINCT card_id, pool_id, card_bnft_id FROM db_pipeline.card_bnft_rule_pool) x ON (x.card_id, x.pool_id) = (l.card_id, l.pool_id)
        WHERE l.ev_subject_cd = 'POOL'
          AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_evidence_link b
                          WHERE b.card_id = l.card_id AND b.ev_subject_cd = 'BNFT' AND b.card_bnft_id = x.card_bnft_id
                            AND b.ev_item_cd = 'SELF' AND b.evidence_id = l.evidence_id))
UNION ALL
SELECT 'E02', '소비 혜택이 없어 옮겨 갈 곳이 없는 POOL 근거', 0,
       (SELECT count(*) FROM db_pipeline.card_evidence_link l
        WHERE l.ev_subject_cd = 'POOL'
          AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_bnft_rule_pool x WHERE (x.card_id, x.pool_id) = (l.card_id, l.pool_id)))
UNION ALL
SELECT 'E03', 'SELF가 아닌 POOL 근거 또는 TIER 근거', 0,
       (SELECT count(*) FROM db_pipeline.card_evidence_link l
        WHERE (l.ev_subject_cd = 'POOL' AND l.ev_item_cd <> 'SELF') OR l.ev_item_cd = 'TIER')
UNION ALL
SELECT 'E04', '한도 구간에 달린 조건 atom', 0,
       (SELECT count(*) FROM db_pipeline.v_card_cond_atom WHERE owner_cd = 'POOL_TIER')
UNION ALL
SELECT 'J01', 'card_bnft.rule_list 내부 pool_refs', 0,
       (SELECT count(*) FROM db_pipeline.card_bnft b
        CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) AS r(value)
        WHERE jsonb_exists(r.value, 'pool_refs'))
UNION ALL
SELECT 'J02', 'card_bnft.relation_list 내부 trigger_pool_id 또는 FALLBACK_AFTER_CAP', 0,
       (SELECT count(*) FROM db_pipeline.card_bnft b
        CROSS JOIN LATERAL jsonb_array_elements(b.relation_list) AS r(value)
        WHERE jsonb_exists(r.value, 'trigger_pool_id') OR r.value->>'rel_type_cd' = 'FALLBACK_AFTER_CAP')
UNION ALL
SELECT 'S01', '여러 혜택이 공유하는 풀(TEXT로 옮기면 공유 관계가 사라짐)', 0,
       (SELECT count(*) FROM (SELECT card_id, pool_id FROM db_pipeline.card_bnft_rule_pool
                              GROUP BY 1, 2 HAVING count(DISTINCT card_bnft_id) > 1) d)
UNION ALL
SELECT 'S02', '같은 혜택 안에서 규칙별로 풀이 다른 혜택(규칙별 대응이 사라짐)', 0,
       (SELECT count(*) FROM (SELECT card_id, card_bnft_id FROM (
            SELECT card_id, card_bnft_id, rule_key, string_agg(pool_id, ',' ORDER BY pool_id) AS pools
            FROM db_pipeline.card_bnft_rule_pool GROUP BY 1, 2, 3) r
          GROUP BY 1, 2 HAVING count(DISTINCT pools) > 1) d)
UNION ALL
SELECT 'O01', '두 테이블에 의존하는 예상 밖 뷰', 0,
       (WITH RECURSIVE t(oid) AS (
            SELECT c.oid FROM pg_class c
            WHERE c.oid IN ('db_pipeline.card_limit_pool'::regclass, 'db_pipeline.card_bnft_rule_pool'::regclass)
            UNION
            SELECT r.ev_class FROM pg_depend d
            JOIN pg_rewrite r ON r.oid = d.objid
            JOIN t ON d.refobjid = t.oid
            WHERE d.classid = 'pg_rewrite'::regclass AND r.ev_class <> t.oid)
        SELECT count(*) FROM t JOIN pg_class c ON c.oid = t.oid
        WHERE c.relkind <> 'r'
          AND c.oid NOT IN ('db_pipeline.v_card_rule_pool'::regclass, 'db_pipeline.v_card_limit_tier'::regclass,
                             'db_pipeline.v_card_cond_atom'::regclass, 'db_pipeline.v_common_cd_usage'::regclass,
                             'db_pipeline.v_card_integrity_issue'::regclass))
UNION ALL
SELECT 'O02', '두 테이블에 걸린 물리 FK', 0,
       (SELECT count(*) FROM pg_constraint
        WHERE contype = 'f' AND (conrelid IN ('db_pipeline.card_limit_pool'::regclass, 'db_pipeline.card_bnft_rule_pool'::regclass)
                                 OR confrelid IN ('db_pipeline.card_limit_pool'::regclass, 'db_pipeline.card_bnft_rule_pool'::regclass)))
UNION ALL
SELECT 'O03', '두 테이블을 본문에서 참조하는 함수', 0,
       (SELECT count(*) FROM pg_proc WHERE pronamespace = 'db_pipeline'::regnamespace
          AND prosrc ~ 'card_limit_pool|card_bnft_rule_pool|v_card_limit_tier|v_card_rule_pool')
UNION ALL
SELECT 'O04', '두 테이블의 시퀀스를 기본값으로 쓰는 다른 테이블 컬럼', 0,
       (SELECT count(*) FROM information_schema.columns
        WHERE table_schema = 'db_pipeline' AND table_name <> 'card_limit_pool'
          AND column_default ~ 'card_limit_pool|card_bnft_rule_pool')
UNION ALL
SELECT 'G01', 'evidence_not_approved 외 정합성 게이트 위반', 0,
       (SELECT count(*) FROM db_pipeline.v_card_integrity_issue
        WHERE gate_cd NOT IN ('evidence_not_approved', 'rule_method_value_pending', 'predicate_params_pending'))
    ) c
    WHERE actual <> expected;
    IF v_fail IS NOT NULL THEN
        RAISE EXCEPTION '사전 조건 실패로 중단합니다. 항목(실제/기대): %', v_fail;
    END IF;
END;
$$;
-- 3. 시퀀스 현재값 보관. 복구에서 같은 값으로 되돌린다.
DO $$
BEGIN
    IF to_regclass('db_pipeline.seq_card_limit_pool') IS NOT NULL
       AND to_regclass('db_pipeline_backup.seq_card_limit_pool_20261102') IS NULL THEN
        CREATE TABLE db_pipeline_backup.seq_card_limit_pool_20261102 AS
        SELECT last_value, is_called FROM db_pipeline.seq_card_limit_pool;
    END IF;
END;
$$;
-- 4. 의존 뷰 제거. 의존 순서를 지키며 CASCADE를 쓰지 않는다.
DROP VIEW IF EXISTS db_pipeline.v_card_integrity_issue;
DROP VIEW IF EXISTS db_pipeline.v_common_cd_usage;
DROP VIEW IF EXISTS db_pipeline.v_card_cond_atom;
DROP VIEW IF EXISTS db_pipeline.v_card_limit_tier;
DROP VIEW IF EXISTS db_pipeline.v_card_rule_pool;
DROP VIEW IF EXISTS db_pipeline.v_card_bnft_rel;
-- 5. POOL 근거 정리. 가드 E01·E02가 혜택별 BNFT/SELF 연결을 확인했고 원본은 백업에 있다.
DELETE FROM db_pipeline.card_evidence_link WHERE ev_subject_cd = 'POOL';
-- 6. 근거 연결의 pool_id 제거. 자연키 이름은 ON CONFLICT ON CONSTRAINT가 쓰므로 유지한다.
ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT IF EXISTS card_evidence_link_ck_2;
ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT IF EXISTS card_evidence_link_natural_key;
ALTER TABLE db_pipeline.card_evidence_link DROP COLUMN IF EXISTS pool_id;
ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_natural_key UNIQUE NULLS NOT DISTINCT
    (card_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, ev_item_cd, ev_item_key, evidence_id);
ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_ck_2 CHECK (
        CASE ev_subject_cd
            WHEN 'CARD' THEN num_nonnulls(card_bnft_id, rule_key, relation_key) = 0
            WHEN 'BNFT' THEN card_bnft_id IS NOT NULL AND num_nonnulls(rule_key, relation_key) = 0
            WHEN 'RULE' THEN card_bnft_id IS NOT NULL AND rule_key IS NOT NULL AND relation_key IS NULL
            WHEN 'REL' THEN card_bnft_id IS NOT NULL AND relation_key IS NOT NULL AND rule_key IS NULL
            ELSE false
        END);
-- 7. 테이블·시퀀스·전용 함수 제거.
DROP TABLE IF EXISTS db_pipeline.card_bnft_rule_pool;
DROP TABLE IF EXISTS db_pipeline.card_limit_pool;
DROP SEQUENCE IF EXISTS db_pipeline.seq_card_limit_pool;
DROP FUNCTION IF EXISTS db_pipeline.fn_valid_tier_list(jsonb);
-- 8. 관계 계약에서 한도 풀 참조 제거.
CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_relation_list(p_list jsonb, p_self_bnft_id text) RETURNS boolean
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

-- 9. 뷰 재생성. 정의는 db_pipeline_schemaV7_draft.sql과 같다.
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

-- 10. 사후 검증. 하나라도 어긋나면 전체 취소한다.
DO $$
DECLARE
    v_n bigint;
BEGIN
    IF to_regclass('db_pipeline.card_limit_pool') IS NOT NULL OR to_regclass('db_pipeline.card_bnft_rule_pool') IS NOT NULL
       OR to_regclass('db_pipeline.v_card_limit_tier') IS NOT NULL OR to_regclass('db_pipeline.v_card_rule_pool') IS NOT NULL
       OR to_regclass('db_pipeline.seq_card_limit_pool') IS NOT NULL THEN
        RAISE EXCEPTION '제거 대상 객체가 남아 있습니다';
    END IF;
    SELECT count(*) INTO v_n FROM db_pipeline_backup.card_evidence_link_pre_simplify_20261102 k
    WHERE k.ev_subject_cd <> 'POOL'
      AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_evidence_link l WHERE (l.card_id, l.ev_link_id) = (k.card_id, k.ev_link_id));
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'POOL이 아닌 근거 연결 %건이 사라졌습니다', v_n;
    END IF;
    SELECT count(*) INTO v_n FROM db_pipeline.card_evidence_link WHERE ev_subject_cd = 'POOL' OR ev_item_cd = 'TIER';
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'POOL 또는 TIER 근거 %건이 남아 있습니다', v_n;
    END IF;
    SELECT count(*) INTO v_n FROM (
        (SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline.card_bnft EXCEPT ALL SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline_backup.card_bnft_pre_simplify_20261102)
        UNION ALL (SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline_backup.card_bnft_pre_simplify_20261102 EXCEPT ALL SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline.card_bnft)) d;
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'card_bnft 행이 백업과 다릅니다: %건', v_n;
    END IF;
    SELECT count(*) INTO v_n FROM db_pipeline.v_card_integrity_issue
    WHERE gate_cd NOT IN ('evidence_not_approved', 'rule_method_value_pending', 'predicate_params_pending');
    IF v_n <> 0 THEN
        RAISE EXCEPTION '정합성 게이트 위반 %건이 있습니다', v_n;
    END IF;
    RAISE NOTICE 'V7 TEXT 단순화 사후 검증 통과';
END;
$$;
COMMIT;
