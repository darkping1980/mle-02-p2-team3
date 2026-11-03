-- =====================================================================================================
-- CARD_SOURCE_EVIDENCE PK 승계 변경: 변경 후 검증 (읽기 전용)
-- 변경(db_pipeline_card_source_evidence_pk_inheritance.sql) 또는 되돌리기 직후에 실행한다.
-- P* 항목은 ok가 true여야 한다. I* 항목은 사전 검증(_precheck.sql)에서 기록한 같은 번호의 값과 같아야 한다.
-- 되돌리기 후에는 P01·P02·P03이 false가 되는 것이 정상이며, 대신 _precheck.sql의 C01~C03이 true여야 한다.
-- =====================================================================================================

BEGIN TRANSACTION READ ONLY;

-- 1. 변경 결과
WITH rel AS (SELECT 'db_pipeline.card_source_evidence'::regclass AS oid),
checks(check_id, check_nm, expected, actual) AS (
    SELECT 'P01', 'PK 정의', 'PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id)',
        (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = (SELECT oid FROM rel) AND contype = 'p')
    UNION ALL SELECT 'P02', 'PK 제약명', 'card_source_evidence_pkey',
        (SELECT conname::text FROM pg_constraint WHERE conrelid = (SELECT oid FROM rel) AND contype = 'p')
    UNION ALL SELECT 'P03', 'UNIQUE 제약', 'card_source_evidence_evidence_id_key UNIQUE (evidence_id)',
        (SELECT string_agg(conname || ' ' || pg_get_constraintdef(oid), '; ' ORDER BY conname)
         FROM pg_constraint WHERE conrelid = (SELECT oid FROM rel) AND contype = 'u')
    UNION ALL SELECT 'P04', 'CHECK 제약(변경 없음)', 'card_source_evidence_ck_1, card_source_evidence_ck_2',
        (SELECT string_agg(conname, ', ' ORDER BY conname) FROM pg_constraint WHERE conrelid = (SELECT oid FROM rel) AND contype = 'c')
    UNION ALL SELECT 'P05', '이 테이블을 참조하는 물리 FK 수', '0',
        (SELECT count(*)::text FROM pg_constraint WHERE confrelid = (SELECT oid FROM rel) AND contype = 'f')
    UNION ALL SELECT 'P06', '컬럼 수(변경 없음)', '9',
        (SELECT count(*)::text FROM pg_attribute WHERE attrelid = (SELECT oid FROM rel) AND attnum > 0 AND NOT attisdropped)
    UNION ALL SELECT 'P07', '상위 CARD_DOC_CHUNK가 없는 근거 수', '0',
        (SELECT count(*)::text FROM db_pipeline.card_source_evidence e
         WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc_chunk c
                           WHERE c.card_doc_id = e.card_doc_id AND c.page_no = e.page_no AND c.card_doc_chunk_id = e.card_doc_chunk_id))
    UNION ALL SELECT 'P08', '원문 근거가 없는 CARD_EVIDENCE_LINK 행 수', '0',
        (SELECT count(*)::text FROM db_pipeline.card_evidence_link l
         WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_source_evidence e WHERE e.evidence_id = l.evidence_id))
    UNION ALL SELECT 'I01', '원문 근거 건수 — 사전 검증 I01과 같아야 함', NULL,
        (SELECT count(*)::text FROM db_pipeline.card_source_evidence)
    UNION ALL SELECT 'I02', '원문 근거 전체 행 지문(md5, 최초 컬럼 순서로 계산해 컬럼 배치와 무관) — 사전 검증 I02와 같아야 함', NULL,
        (SELECT md5(string_agg(md5(row(e.evidence_id, e.card_doc_id, e.page_no, e.card_doc_chunk_id, e.card_extr_stg_id, e.quote_txt,
                                       e.start_pos, e.end_pos, e.approval_status_cd)::text), ',' ORDER BY e.evidence_id))
         FROM db_pipeline.card_source_evidence e)
    UNION ALL SELECT 'I03', 'CARD_EVIDENCE_LINK 건수 / EVIDENCE_ID 단독 JOIN 건수 — 사전 검증 I03과 같아야 함', NULL,
        (SELECT count(*)::text FROM db_pipeline.card_evidence_link) || ' / '
        || (SELECT count(*)::text FROM db_pipeline.card_evidence_link l JOIN db_pipeline.card_source_evidence e USING (evidence_id))
    UNION ALL SELECT 'I04', '정합성 뷰 게이트별 건수 — 사전 검증 I04와 같아야 함', NULL,
        (SELECT coalesce(string_agg(gate_cd || '=' || n, ', ' ORDER BY gate_cd), '없음')
         FROM (SELECT gate_cd, count(*) AS n FROM db_pipeline.v_card_integrity_issue GROUP BY gate_cd) g)
    UNION ALL SELECT 'I05', '이 테이블의 인덱스 — PK 인덱스 컬럼만 달라지고 나머지는 같아야 함', NULL,
        (SELECT string_agg(indexrelid::regclass::text || ' ' || regexp_replace(pg_get_indexdef(indexrelid), '^.* USING ', ''), '; '
                           ORDER BY indexrelid::regclass::text)
         FROM pg_index WHERE indrelid = (SELECT oid FROM rel))
)
SELECT check_id, check_nm, expected, actual,
       CASE WHEN expected IS NULL THEN NULL ELSE expected IS NOT DISTINCT FROM actual END AS ok
FROM checks
ORDER BY check_id;

-- 2. EVIDENCE_ID 단독 조회가 기존처럼 동작하는지. 카드·혜택·규칙 근거 3종류를 모두 확인한다.
SELECT l.ev_subject_cd, count(*) AS links, count(e.evidence_id) AS joined
FROM db_pipeline.card_evidence_link l
LEFT JOIN db_pipeline.card_source_evidence e ON e.evidence_id = l.evidence_id
GROUP BY l.ev_subject_cd
ORDER BY l.ev_subject_cd;

-- 3. 문서 → 페이지 → 청크 → 근거 경로 조회 (새 PK의 앞쪽 컬럼 사용)
SELECT e.card_doc_id, e.page_no, count(*) AS evidence_count
FROM db_pipeline.card_doc_chunk c
JOIN db_pipeline.card_source_evidence e
  ON (e.card_doc_id, e.page_no, e.card_doc_chunk_id) = (c.card_doc_id, c.page_no, c.card_doc_chunk_id)
GROUP BY e.card_doc_id, e.page_no
ORDER BY e.card_doc_id, e.page_no;

ROLLBACK;
