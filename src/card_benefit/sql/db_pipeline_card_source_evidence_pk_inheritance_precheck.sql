-- =====================================================================================================
-- CARD_SOURCE_EVIDENCE PK 승계 변경: 사전 검증 (읽기 전용)
-- 설계안: CARD_SOURCE_EVIDENCE_PK_INHERITANCE_PROPOSAL_20261103.md
-- 검토서: CARD_SOURCE_EVIDENCE_PK_INHERITANCE_REVIEW_20261103.md
--
-- SELECT만 실행하고 READ ONLY 트랜잭션을 ROLLBACK으로 끝낸다. 데이터와 구조를 바꾸지 않는다.
-- 1번 결과의 ok가 모두 true여야 변경 스크립트를 실행할 수 있다. 정보 항목(I*)은 결과값을 기록해 두고
-- 변경 후 검증(_postcheck.sql)의 같은 항목과 비교한다.
-- =====================================================================================================

BEGIN TRANSACTION READ ONLY;

-- 1. 차단 조건(C*)과 비교 기준값(I*)
WITH rel AS (SELECT 'db_pipeline.card_source_evidence'::regclass AS oid),
pk AS (SELECT c.oid, c.conname, pg_get_constraintdef(c.oid) AS def
       FROM pg_constraint c WHERE c.conrelid = (SELECT oid FROM rel) AND c.contype = 'p'),
checks(check_id, check_nm, expected, actual) AS (
    SELECT 'C01', '현재 PK 정의', 'PRIMARY KEY (evidence_id)', (SELECT def FROM pk)
    UNION ALL SELECT 'C02', '현재 PK 제약명', 'card_source_evidence_pkey', (SELECT conname FROM pk)
    UNION ALL SELECT 'C03', '이 테이블의 UNIQUE 제약 수', '0',
        (SELECT count(*)::text FROM pg_constraint WHERE conrelid = (SELECT oid FROM rel) AND contype = 'u')
    UNION ALL SELECT 'C04', '이 테이블을 참조하는 물리 FK 수', '0',
        (SELECT count(*)::text FROM pg_constraint WHERE confrelid = (SELECT oid FROM rel) AND contype = 'f')
    UNION ALL SELECT 'C05', 'PK 제약에 의존하는 객체 수(자기 인덱스 제외. GROUP BY 함수 종속 뷰 등)', '0',
        (SELECT count(*)::text FROM pg_depend d
         WHERE d.refclassid = 'pg_constraint'::regclass AND d.refobjid = (SELECT oid FROM pk) AND d.deptype <> 'i')
    UNION ALL SELECT 'C06', '새 UNIQUE 이름(card_source_evidence_evidence_id_key)과 겹치는 객체 수', '0',
        (SELECT count(*)::text FROM pg_class
         WHERE relnamespace = 'db_pipeline'::regnamespace AND relname = 'card_source_evidence_evidence_id_key')
    UNION ALL SELECT 'C07', 'PK 후보 컬럼 중 NULL 허용 컬럼 수', '0',
        (SELECT count(*)::text FROM pg_attribute
         WHERE attrelid = (SELECT oid FROM rel) AND attname IN ('card_doc_id', 'page_no', 'card_doc_chunk_id', 'evidence_id')
           AND NOT attnotnull)
    UNION ALL SELECT 'C08', 'PK 후보 컬럼에 NULL이 있는 행 수', '0',
        (SELECT count(*)::text FROM db_pipeline.card_source_evidence
         WHERE card_doc_id IS NULL OR page_no IS NULL OR card_doc_chunk_id IS NULL OR evidence_id IS NULL)
    UNION ALL SELECT 'C09', 'EVIDENCE_ID 중복 값 수', '0',
        (SELECT count(*)::text FROM (SELECT evidence_id FROM db_pipeline.card_source_evidence
                                     GROUP BY evidence_id HAVING count(*) > 1) x)
    UNION ALL SELECT 'C10', '새 복합 PK 중복 값 수', '0',
        (SELECT count(*)::text FROM (SELECT 1 FROM db_pipeline.card_source_evidence
                                     GROUP BY card_doc_id, page_no, card_doc_chunk_id, evidence_id HAVING count(*) > 1) x)
    UNION ALL SELECT 'C11', '상위 CARD_DOC_CHUNK가 없는 근거 수', '0',
        (SELECT count(*)::text FROM db_pipeline.card_source_evidence e
         WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc_chunk c
                           WHERE c.card_doc_id = e.card_doc_id AND c.page_no = e.page_no AND c.card_doc_chunk_id = e.card_doc_chunk_id))
    UNION ALL SELECT 'C12', '원문 근거가 없는 CARD_EVIDENCE_LINK 행 수', '0',
        (SELECT count(*)::text FROM db_pipeline.card_evidence_link l
         WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_source_evidence e WHERE e.evidence_id = l.evidence_id))
    UNION ALL SELECT 'C13', '다른 세션이 이 테이블에 잡은 잠금 수', '0',
        (SELECT count(*)::text FROM pg_locks WHERE relation = (SELECT oid FROM rel) AND pid <> pg_backend_pid())
    UNION ALL SELECT 'I01', '원문 근거 건수', NULL, (SELECT count(*)::text FROM db_pipeline.card_source_evidence)
    UNION ALL SELECT 'I02', '원문 근거 전체 행 지문(md5, 최초 컬럼 순서로 계산해 컬럼 배치와 무관)', NULL,
        (SELECT md5(string_agg(md5(row(e.evidence_id, e.card_doc_id, e.page_no, e.card_doc_chunk_id, e.card_extr_stg_id, e.quote_txt,
                                       e.start_pos, e.end_pos, e.approval_status_cd)::text), ',' ORDER BY e.evidence_id))
         FROM db_pipeline.card_source_evidence e)
    UNION ALL SELECT 'I03', 'CARD_EVIDENCE_LINK 건수 / EVIDENCE_ID 단독 JOIN 건수', NULL,
        (SELECT count(*)::text FROM db_pipeline.card_evidence_link) || ' / '
        || (SELECT count(*)::text FROM db_pipeline.card_evidence_link l JOIN db_pipeline.card_source_evidence e USING (evidence_id))
    UNION ALL SELECT 'I04', '정합성 뷰 v_card_integrity_issue 게이트별 건수', NULL,
        (SELECT coalesce(string_agg(gate_cd || '=' || n, ', ' ORDER BY gate_cd), '없음')
         FROM (SELECT gate_cd, count(*) AS n FROM db_pipeline.v_card_integrity_issue GROUP BY gate_cd) g)
    UNION ALL SELECT 'I05', '이 테이블의 인덱스', NULL,
        (SELECT string_agg(indexrelid::regclass::text || ' ' || regexp_replace(pg_get_indexdef(indexrelid), '^.* USING ', ''), '; '
                           ORDER BY indexrelid::regclass::text)
         FROM pg_index WHERE indrelid = (SELECT oid FROM rel))
    UNION ALL SELECT 'I06', '이 테이블에 의존하는 뷰', NULL,
        (SELECT string_agg(DISTINCT v.oid::regclass::text, ', ')
         FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class v ON v.oid = r.ev_class
         WHERE d.refobjid = (SELECT oid FROM rel) AND v.oid <> (SELECT oid FROM rel))
)
SELECT check_id, check_nm, expected, actual,
       CASE WHEN expected IS NULL THEN NULL ELSE expected IS NOT DISTINCT FROM actual END AS ok
FROM checks
ORDER BY check_id;

-- 2. 차단 조건이 실패했을 때 원인 행 확인. 정상이면 모두 0행이다.
-- 2-1. 상위 청크가 없는 근거
SELECT e.evidence_id, e.card_doc_id, e.page_no, e.card_doc_chunk_id
FROM db_pipeline.card_source_evidence e
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc_chunk c
                  WHERE c.card_doc_id = e.card_doc_id AND c.page_no = e.page_no AND c.card_doc_chunk_id = e.card_doc_chunk_id)
ORDER BY e.evidence_id;

-- 2-2. 원문 근거가 없는 근거 연결
SELECT l.card_id, l.evidence_link_id, l.evidence_id
FROM db_pipeline.card_evidence_link l
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_source_evidence e WHERE e.evidence_id = l.evidence_id)
ORDER BY l.card_id, l.evidence_link_id;

-- 2-3. 이 테이블을 참조하는 FK와 PK 제약에 의존하는 객체
SELECT 'FK' AS kind, c.conrelid::regclass::text AS object, pg_get_constraintdef(c.oid) AS detail
FROM pg_constraint c
WHERE c.confrelid = 'db_pipeline.card_source_evidence'::regclass AND c.contype = 'f'
UNION ALL
SELECT 'PK 의존', pg_describe_object(d.classid, d.objid, d.objsubid), d.deptype::text
FROM pg_depend d
WHERE d.refclassid = 'pg_constraint'::regclass AND d.deptype <> 'i'
  AND d.refobjid = (SELECT oid FROM pg_constraint
                    WHERE conrelid = 'db_pipeline.card_source_evidence'::regclass AND contype = 'p');

-- 2-4. 잠금을 기다리게 할 수 있는 오래된 트랜잭션
SELECT pid, usename, state, now() - xact_start AS xact_age, left(query, 80) AS query
FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid() AND xact_start IS NOT NULL
ORDER BY xact_start;

ROLLBACK;
