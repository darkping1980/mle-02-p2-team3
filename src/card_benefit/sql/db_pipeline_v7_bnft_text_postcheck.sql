-- V7 혜택·한도 TEXT 단순화 사후 검증. 읽기 전용. db_pipeline_migration_v7_bnft_text.sql 실행 후 돌린다.
-- DBeaver: 스크립트 전체 실행(Alt+X)으로 돌린다. 문장 단위 실행(Ctrl+Enter)을 쓰지 않는다.
-- 기대값은 2026-11-02 개발 DB 기준이다. 이후 데이터가 늘면 건수 항목(P·D·E01·V·G02)은 재검토한다.
WITH c AS (
SELECT 'P01' AS check_cd, 'card_limit_pool, card_bnft_rule_pool 제거' AS check_nm, 0::bigint AS expected,
       (SELECT count(*) FROM pg_class WHERE relnamespace = 'db_pipeline'::regnamespace AND relname IN ('card_limit_pool', 'card_bnft_rule_pool')) AS actual
UNION ALL
SELECT 'P02', '제거 대상 뷰·시퀀스·함수', 0,
       (SELECT count(*) FROM pg_class WHERE relnamespace = 'db_pipeline'::regnamespace AND relname IN ('v_card_limit_tier', 'v_card_rule_pool', 'seq_card_limit_pool'))
       + (SELECT count(*) FROM pg_proc WHERE pronamespace = 'db_pipeline'::regnamespace AND proname = 'fn_valid_tier_list')
UNION ALL
SELECT 'P03', 'card_evidence_link.pool_id 제거', 0,
       (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'db_pipeline' AND table_name = 'card_evidence_link' AND column_name = 'pool_id')
UNION ALL
SELECT 'P04', 'TEXT 컬럼 2개 유지', 2,
       (SELECT count(*) FROM information_schema.columns WHERE table_schema = 'db_pipeline' AND table_name = 'card_bnft' AND column_name IN ('bnft_rule_txt', 'bnft_limit_txt'))
UNION ALL
SELECT 'P05', '테이블 수', 14, (SELECT count(*) FROM pg_class WHERE relnamespace = 'db_pipeline'::regnamespace AND relkind = 'r')
UNION ALL
SELECT 'P06', '뷰 수', 8, (SELECT count(*) FROM pg_class WHERE relnamespace = 'db_pipeline'::regnamespace AND relkind = 'v')
UNION ALL
SELECT 'P07', '시퀀스 수', 9, (SELECT count(*) FROM pg_class WHERE relnamespace = 'db_pipeline'::regnamespace AND relkind = 'S')
UNION ALL
SELECT 'P08', '함수 수', 7, (SELECT count(*) FROM pg_proc WHERE pronamespace = 'db_pipeline'::regnamespace)
UNION ALL
SELECT 'P09', '물리 FK', 0, (SELECT count(*) FROM pg_constraint WHERE connamespace = 'db_pipeline'::regnamespace AND contype = 'f')
UNION ALL
SELECT 'D01', 'card_bnft 백업 대비 차이(TEXT 제외, 검증 상태 포함)', 0,
       (SELECT count(*) FROM ((SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline.card_bnft EXCEPT ALL SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline_backup.card_bnft_pre_simplify_20261102)
        UNION ALL (SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline_backup.card_bnft_pre_simplify_20261102 EXCEPT ALL SELECT card_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd,bnft_valid_from,bnft_valid_to_excl FROM db_pipeline.card_bnft)) d)
UNION ALL
SELECT 'D02', 'TEXT가 채워진 혜택 수', 4,
       (SELECT count(*) FROM db_pipeline.card_bnft WHERE bnft_rule_txt IS NOT NULL AND bnft_limit_txt IS NOT NULL)
UNION ALL
SELECT 'D03', 'TEXT가 NULL인 혜택 수(CARD_ID=5 Visa 컨시어지)', 1,
       (SELECT count(*) FROM db_pipeline.card_bnft WHERE bnft_rule_txt IS NULL AND bnft_limit_txt IS NULL)
UNION ALL
SELECT 'D04', 'PENDING_REVIEW가 아닌 혜택', 0,
       (SELECT count(*) FROM db_pipeline.card_bnft WHERE verification_status_cd <> 'PENDING_REVIEW')
UNION ALL
SELECT 'E01', '근거 연결 수(백업 66 - POOL 9)', 57, (SELECT count(*) FROM db_pipeline.card_evidence_link)
UNION ALL
SELECT 'E02', '남은 POOL 근거', 0, (SELECT count(*) FROM db_pipeline.card_evidence_link WHERE ev_subject_cd = 'POOL')
UNION ALL
SELECT 'E03', '백업의 비 POOL 근거 중 사라진 건', 0,
       (SELECT count(*) FROM db_pipeline_backup.card_evidence_link_pre_simplify_20261102 k
        WHERE k.ev_subject_cd <> 'POOL'
          AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_evidence_link l
                          WHERE (l.card_id, l.ev_link_id, l.ev_subject_cd, l.evidence_id) = (k.card_id, k.ev_link_id, k.ev_subject_cd, k.evidence_id)))
UNION ALL
SELECT 'E04', '백업 POOL 근거의 원문이 소비 혜택 BNFT/SELF로 남지 않은 건', 0,
       (SELECT count(*) FROM db_pipeline_backup.card_evidence_link_pre_simplify_20261102 k
        JOIN (SELECT DISTINCT card_id, pool_id, card_bnft_id FROM db_pipeline_backup.card_bnft_rule_pool_20261102) x ON (x.card_id, x.pool_id) = (k.card_id, k.pool_id)
        WHERE k.ev_subject_cd = 'POOL'
          AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_evidence_link l
                          WHERE l.card_id = k.card_id AND l.ev_subject_cd = 'BNFT' AND l.card_bnft_id = x.card_bnft_id
                            AND l.ev_item_cd = 'SELF' AND l.evidence_id = k.evidence_id))
UNION ALL
SELECT 'V01', '조건 atom 수', 15, (SELECT count(*) FROM db_pipeline.v_card_cond_atom)
UNION ALL
SELECT 'V02', '계산 규칙 수', 6, (SELECT count(*) FROM db_pipeline.v_card_rule)
UNION ALL
SELECT 'V03', '혜택 관계 수', 0, (SELECT count(*) FROM db_pipeline.v_card_bnft_rel)
UNION ALL
SELECT 'G01', 'evidence_not_approved 외 정합성 게이트 위반', 0,
       (SELECT count(*) FROM db_pipeline.v_card_integrity_issue WHERE gate_cd <> 'evidence_not_approved')
UNION ALL
SELECT 'G02', 'evidence_not_approved(이관 전과 동일)', 35,
       (SELECT count(*) FROM db_pipeline.v_card_integrity_issue WHERE gate_cd = 'evidence_not_approved')
)
SELECT check_cd, check_nm, expected, actual, CASE WHEN actual = expected THEN 'PASS' ELSE 'FAIL' END AS result FROM c
UNION ALL
SELECT 'C99', '전체 판정', 0, count(*) FILTER (WHERE actual <> expected),
       CASE WHEN count(*) FILTER (WHERE actual <> expected) = 0 THEN 'PASS' ELSE 'FAIL' END
FROM c
ORDER BY 1;
SELECT card_id, card_bnft_id, bnft_nm, verification_status_cd, bnft_rule_txt, bnft_limit_txt
FROM db_pipeline.card_bnft ORDER BY 1, 2;
