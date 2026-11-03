-- =====================================================================================================
-- CARD_EVIDENCE_LINK PK 승계: 사전 검증 (읽기 전용, ROLLBACK으로 끝남)
-- C* 항목이 모두 true여야 변경 스크립트를 실행한다. I* 값은 기록해 두고 _postcheck.sql의 같은 번호와 비교한다.
-- 지문(I02)은 기존 9개 값만으로 계산하므로 변경 전후, 컬럼 이름 변경 전후에 같은 값이 나온다.
-- =====================================================================================================

BEGIN TRANSACTION READ ONLY;

WITH rel AS (SELECT 'db_pipeline.card_evidence_link'::regclass AS oid),
cols AS (SELECT string_agg(attname, ',' ORDER BY attnum) AS v FROM pg_attribute
         WHERE attrelid = (SELECT oid FROM rel) AND attnum > 0 AND NOT attisdropped),
link_id AS (SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid = (SELECT oid FROM rel) AND attname = 'ev_link_id' AND NOT attisdropped)
                        THEN 'ev_link_id' ELSE 'evidence_link_id' END AS name),
checks(check_id, check_nm, expected, actual) AS (
    SELECT 'C01', '현재 컬럼 구성', 'card_id,ev_link_id,ev_subject_cd,card_bnft_id,rule_key,relation_key,ev_item_cd,ev_item_key,evidence_id', (SELECT v FROM cols)
    UNION ALL SELECT 'C02', '현재 PK', 'PRIMARY KEY (card_id, ev_link_id)',
        (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = (SELECT oid FROM rel) AND contype = 'p')
    UNION ALL SELECT 'C03', '현재 제약 이름', 'card_evidence_link_ck_1,card_evidence_link_ck_2,card_evidence_link_natural_key,card_evidence_link_pkey',
        (SELECT string_agg(conname, ',' ORDER BY conname) FROM pg_constraint WHERE conrelid = (SELECT oid FROM rel))
    UNION ALL SELECT 'C04', '이 테이블을 참조하거나 이 테이블이 참조하는 물리 FK 수', '0',
        (SELECT count(*)::text FROM pg_constraint WHERE contype = 'f' AND (confrelid = (SELECT oid FROM rel) OR conrelid = (SELECT oid FROM rel)))
    UNION ALL SELECT 'C05', '의존 뷰 (두 뷰만 허용)', 'db_pipeline.v_card_integrity_issue,db_pipeline.v_common_cd_usage',
        (SELECT string_agg(DISTINCT v.oid::regclass::text, ',') FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class v ON v.oid = r.ev_class
         WHERE d.refobjid = (SELECT oid FROM rel) AND v.oid <> (SELECT oid FROM rel))
    UNION ALL SELECT 'C06', '두 뷰를 참조하는 다른 뷰 (v_card_integrity_issue→v_common_cd_usage 제외)', '0',
        (SELECT count(DISTINCT r.ev_class)::text FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid
         WHERE d.refobjid IN ('db_pipeline.v_card_integrity_issue'::regclass, 'db_pipeline.v_common_cd_usage'::regclass)
           AND r.ev_class NOT IN ('db_pipeline.v_card_integrity_issue'::regclass, 'db_pipeline.v_common_cd_usage'::regclass))
    UNION ALL SELECT 'C07', '트리거·정책·규칙·발행·컬럼 권한', '0',
        (SELECT ((SELECT count(*) FROM pg_trigger WHERE tgrelid = (SELECT oid FROM rel) AND NOT tgisinternal)
               + (SELECT count(*) FROM pg_policy WHERE polrelid = (SELECT oid FROM rel))
               + (SELECT count(*) FROM pg_rewrite WHERE ev_class = (SELECT oid FROM rel))
               + (SELECT count(*) FROM pg_publication_rel WHERE prrelid = (SELECT oid FROM rel))
               + (SELECT count(*) FROM pg_attribute WHERE attrelid = (SELECT oid FROM rel) AND attacl IS NOT NULL))::text)
    UNION ALL SELECT 'C08', '원문 근거 UNIQUE(evidence_id)', 'card_source_evidence_evidence_id_key',
        (SELECT conname::text FROM pg_constraint WHERE conrelid = 'db_pipeline.card_source_evidence'::regclass AND pg_get_constraintdef(oid) = 'UNIQUE (evidence_id)')
    UNION ALL SELECT 'C09', '원문 근거가 없는 연결 수', '0',
        (SELECT count(*)::text FROM db_pipeline.card_evidence_link l
         WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_source_evidence e WHERE e.evidence_id = l.evidence_id))
    UNION ALL SELECT 'C10', '(card_id, 연결 ID) 중복 수', '0',
        (SELECT count(*)::text FROM (SELECT 1 FROM db_pipeline.card_evidence_link
                                     GROUP BY card_id, (to_jsonb(card_evidence_link)->>(SELECT name FROM link_id)) HAVING count(*) > 1) x)
    UNION ALL SELECT 'C11', '이관 SELECT 결과가 원래 건수와 같음', 'true',
        ((SELECT count(*) FROM db_pipeline.card_evidence_link l JOIN db_pipeline.card_source_evidence e ON e.evidence_id = l.evidence_id)
         = (SELECT count(*) FROM db_pipeline.card_evidence_link))::text
    UNION ALL SELECT 'C12', '새 6컬럼 PK 중복 수', '0',
        (SELECT count(*)::text FROM (SELECT 1 FROM db_pipeline.card_evidence_link l JOIN db_pipeline.card_source_evidence e ON e.evidence_id = l.evidence_id
                                     GROUP BY e.card_doc_id, e.page_no, e.card_doc_chunk_id, l.evidence_id, l.card_id,
                                              (to_jsonb(l)->>(SELECT name FROM link_id)) HAVING count(*) > 1) x)
    UNION ALL SELECT 'C13', '다른 세션의 잠금 수 (근거 연결·원문 근거·두 뷰)', '0',
        (SELECT count(*)::text FROM pg_locks WHERE pid <> pg_backend_pid() AND relation IN
            ((SELECT oid FROM rel), 'db_pipeline.card_source_evidence'::regclass,
             'db_pipeline.v_card_integrity_issue'::regclass, 'db_pipeline.v_common_cd_usage'::regclass))
    UNION ALL SELECT 'C14', '새 객체 이름 사용 중 (card_evidence_link_id_key, 임시 테이블)', '0',
        (SELECT count(*)::text FROM pg_class WHERE relnamespace = 'db_pipeline'::regnamespace
           AND relname IN ('card_evidence_link_id_key', 'card_evidence_link__pkinherit_old', 'card_evidence_link__pkinherit_new'))
    UNION ALL SELECT 'I01', '연결 건수', NULL, (SELECT count(*)::text FROM db_pipeline.card_evidence_link)
    UNION ALL SELECT 'I02', '연결 행 지문 (기존 9개 값)', NULL,
        (SELECT md5(string_agg(md5(row(l.card_id, to_jsonb(l)->>(SELECT name FROM link_id), l.ev_subject_cd, l.card_bnft_id, l.rule_key,
                                       l.relation_key, l.ev_item_cd, l.ev_item_key, l.evidence_id)::text),
                               ',' ORDER BY l.card_id, to_jsonb(l)->>(SELECT name FROM link_id)))
         FROM db_pipeline.card_evidence_link l)
    UNION ALL SELECT 'I03', '유형별 건수', NULL,
        (SELECT string_agg(ev_subject_cd || '=' || n, ', ' ORDER BY ev_subject_cd)
         FROM (SELECT ev_subject_cd, count(*) n FROM db_pipeline.card_evidence_link GROUP BY 1) g)
    UNION ALL SELECT 'I04', 'CARD 유형 중 card_bnft_id NULL 건수', NULL,
        (SELECT count(*)::text FROM db_pipeline.card_evidence_link WHERE ev_subject_cd = 'CARD' AND card_bnft_id IS NULL)
    UNION ALL SELECT 'I05', '정합성 뷰 게이트별 건수', NULL,
        (SELECT coalesce(string_agg(gate_cd || '=' || n, ', ' ORDER BY gate_cd), '없음')
         FROM (SELECT gate_cd, count(*) n FROM db_pipeline.v_card_integrity_issue GROUP BY 1) g)
    UNION ALL SELECT 'I06', '원문 근거 건수와 지문', NULL,
        (SELECT count(*) || ' ' || md5(string_agg(md5(row(evidence_id, card_doc_id, page_no, card_doc_chunk_id, card_extr_stg_id, quote_txt,
                                                          start_pos, end_pos, approval_status_cd)::text), ',' ORDER BY evidence_id))
         FROM db_pipeline.card_source_evidence)
)
SELECT check_id, check_nm, expected, actual,
       CASE WHEN expected IS NULL THEN NULL ELSE expected IS NOT DISTINCT FROM actual END AS ok
FROM checks ORDER BY check_id;

-- 원인 확인: 원문 근거가 없는 연결 (정상 0행)
SELECT l.card_id, l.evidence_id, l.ev_subject_cd, l.card_bnft_id
FROM db_pipeline.card_evidence_link l
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_source_evidence e WHERE e.evidence_id = l.evidence_id);

-- 잠금을 기다리게 할 수 있는 열린 트랜잭션 (정상 0행)
SELECT pid, usename, application_name, state, now() - xact_start AS xact_age
FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid() AND xact_start IS NOT NULL;

ROLLBACK;
