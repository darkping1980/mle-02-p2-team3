-- V7 혜택·한도 TEXT 단순화: DROP 전 검증. 읽기 전용이며 데이터와 구조를 바꾸지 않는다.
-- 실행 시점: db_pipeline_migration_v7_bnft_text.sql 실행 직전. 두 테이블이 아직 있어야 실행된다.
-- DBeaver: 스크립트 전체 실행(Alt+X)으로 돌린다. 문장 단위 실행(Ctrl+Enter)을 쓰지 않는다.
-- 판정: 첫 결과의 FAIL이 0건이고 C99가 PASS일 때만 이관을 실행한다. 같은 조건을 이관 SQL 가드도 다시 검사한다.
-- 둘째 결과는 사람이 보는 값 대조표, 셋째 결과는 이관 전 POOL 근거 현황(TOTAL/LINKED/MISSING)이다.
WITH c AS (
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
)
SELECT check_cd, check_nm, expected, actual, CASE WHEN actual = expected THEN 'PASS' ELSE 'FAIL' END AS result FROM c
UNION ALL
SELECT 'C99', '전체 판정', 0, count(*) FILTER (WHERE actual <> expected),
       CASE WHEN count(*) FILTER (WHERE actual <> expected) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM c
ORDER BY 1;
-- 값 대조표: 풀 값과 TEXT를 나란히 본다. 집계 기준 CARD_MEMBER는 원문 미확인 가정값이라 TEXT로 옮기지 않았다.
SELECT b.card_id, b.card_bnft_id, b.bnft_nm, b.verification_status_cd,
       (SELECT string_agg(p.period_cd || ':' || (t.value->>'limit_num') || ' ' || p.cap_unit_cd, ', ' ORDER BY p.pool_id)
        FROM (SELECT DISTINCT card_id, card_bnft_id, pool_id FROM db_pipeline.card_bnft_rule_pool) x
        JOIN db_pipeline.card_limit_pool p ON (p.card_id, p.pool_id) = (x.card_id, x.pool_id)
        CROSS JOIN LATERAL jsonb_array_elements(p.tier_list) AS t(value)
        WHERE (x.card_id, x.card_bnft_id) = (b.card_id, b.card_bnft_id)) AS pool_values,
       b.bnft_limit_txt, b.bnft_rule_txt
FROM db_pipeline.card_bnft b
ORDER BY 1, 2;
-- POOL 근거 현황. 혜택 단위로 센다. 풀 하나가 여러 혜택에 쓰이면 혜택마다 BNFT/SELF가 있어야 LINKED다.
SELECT count(*) AS total,
       count(*) FILTER (WHERE y.linked) AS linked,
       count(*) FILTER (WHERE NOT y.linked) AS missing
FROM db_pipeline.card_evidence_link l
JOIN (SELECT DISTINCT card_id, pool_id, card_bnft_id FROM db_pipeline.card_bnft_rule_pool) x ON (x.card_id, x.pool_id) = (l.card_id, l.pool_id)
CROSS JOIN LATERAL (SELECT EXISTS (SELECT 1 FROM db_pipeline.card_evidence_link b
                                   WHERE b.card_id = l.card_id AND b.ev_subject_cd = 'BNFT' AND b.card_bnft_id = x.card_bnft_id
                                     AND b.ev_item_cd = 'SELF' AND b.evidence_id = l.evidence_id) AS linked) y
WHERE l.ev_subject_cd = 'POOL';
