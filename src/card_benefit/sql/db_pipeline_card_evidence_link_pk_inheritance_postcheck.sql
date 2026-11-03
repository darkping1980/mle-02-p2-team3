-- =====================================================================================================
-- CARD_EVIDENCE_LINK PK 승계: 사후 검증 (읽기 전용, ROLLBACK으로 끝남)
-- P* 항목은 true여야 한다. I* 값은 _precheck.sql의 같은 번호와 같아야 한다.
-- 새 컬럼(card_doc_id 등)을 참조하므로 변경 후에만 실행한다. 변경 전에 실행하면 컬럼 없음 오류가 난다.
-- =====================================================================================================

BEGIN TRANSACTION READ ONLY;

WITH rel AS (SELECT 'db_pipeline.card_evidence_link'::regclass AS oid),
checks(check_id, check_nm, expected, actual) AS (
    SELECT 'P01', '컬럼 순서', 'card_doc_id,page_no,card_doc_chunk_id,evidence_id,card_id,evidence_link_id,card_bnft_id,ev_subject_cd,rule_key,relation_key,ev_item_cd,ev_item_key',
        (SELECT string_agg(attname, ',' ORDER BY attnum) FROM pg_attribute WHERE attrelid = (SELECT oid FROM rel) AND attnum > 0 AND NOT attisdropped)
    UNION ALL SELECT 'P02', 'PK 6컬럼', 'PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id)',
        (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = (SELECT oid FROM rel) AND contype = 'p')
    UNION ALL SELECT 'P03', 'UNIQUE (card_id, evidence_link_id)', 'card_evidence_link_id_key UNIQUE (card_id, evidence_link_id)',
        (SELECT conname || ' ' || pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = (SELECT oid FROM rel) AND conname = 'card_evidence_link_id_key')
    UNION ALL SELECT 'P04', '자연키 유지 (ON CONFLICT 대상)',
        'UNIQUE NULLS NOT DISTINCT (card_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, ev_item_cd, ev_item_key, evidence_id)',
        (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = (SELECT oid FROM rel) AND conname = 'card_evidence_link_natural_key')
    UNION ALL SELECT 'P05', '제약 이름', 'card_evidence_link_ck_1,card_evidence_link_ck_2,card_evidence_link_id_key,card_evidence_link_natural_key,card_evidence_link_pkey',
        (SELECT string_agg(conname, ',' ORDER BY conname) FROM pg_constraint WHERE conrelid = (SELECT oid FROM rel))
    UNION ALL SELECT 'P06', 'evidence_link_id 기본값 (생성 함수 인자 유지)', 'db_pipeline.fn_get_biz_id(''card_evidence_link''::text)',
        (SELECT pg_get_expr(d.adbin, d.adrelid) FROM pg_attrdef d JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
         WHERE d.adrelid = (SELECT oid FROM rel) AND a.attname = 'evidence_link_id')
    UNION ALL SELECT 'P07', '물리 FK 수 (도입하지 않음)', '0',
        (SELECT count(*)::text FROM pg_constraint WHERE contype = 'f' AND (confrelid = (SELECT oid FROM rel) OR conrelid = (SELECT oid FROM rel)))
    UNION ALL SELECT 'P08', '승계한 상위키가 원문 근거와 다른 연결 수', '0',
        (SELECT count(*)::text FROM db_pipeline.card_evidence_link l
         WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_source_evidence e
                           WHERE (e.card_doc_id, e.page_no, e.card_doc_chunk_id, e.evidence_id) = (l.card_doc_id, l.page_no, l.card_doc_chunk_id, l.evidence_id)))
    UNION ALL SELECT 'P09', '인덱스', 'card_evidence_link_id_key,card_evidence_link_natural_key,card_evidence_link_pkey,ix_card_evidence_link_evidence,ix_card_evidence_link_subject',
        (SELECT string_agg(c.relname, ',' ORDER BY c.relname) FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid WHERE i.indrelid = (SELECT oid FROM rel))
    UNION ALL SELECT 'P10', '의존 뷰', 'db_pipeline.v_card_integrity_issue,db_pipeline.v_common_cd_usage',
        (SELECT string_agg(DISTINCT v.oid::regclass::text, ',') FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class v ON v.oid = r.ev_class
         WHERE d.refobjid = (SELECT oid FROM rel) AND v.oid <> (SELECT oid FROM rel))
    UNION ALL SELECT 'I01', '연결 건수 — 사전 I01과 같아야 함', NULL, (SELECT count(*)::text FROM db_pipeline.card_evidence_link)
    UNION ALL SELECT 'I02', '연결 행 지문 (기존 9개 값) — 사전 I02와 같아야 함', NULL,
        (SELECT md5(string_agg(md5(row(card_id, evidence_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, ev_item_cd, ev_item_key,
                                       evidence_id)::text), ',' ORDER BY card_id, evidence_link_id)) FROM db_pipeline.card_evidence_link)
    UNION ALL SELECT 'I03', '유형별 건수 — 사전 I03과 같아야 함', NULL,
        (SELECT string_agg(ev_subject_cd || '=' || n, ', ' ORDER BY ev_subject_cd)
         FROM (SELECT ev_subject_cd, count(*) n FROM db_pipeline.card_evidence_link GROUP BY 1) g)
    UNION ALL SELECT 'I04', 'CARD 유형 중 card_bnft_id NULL 건수 — 사전 I04와 같아야 함', NULL,
        (SELECT count(*)::text FROM db_pipeline.card_evidence_link WHERE ev_subject_cd = 'CARD' AND card_bnft_id IS NULL)
    UNION ALL SELECT 'I05', '정합성 뷰 게이트별 건수 — 사전 I05와 같아야 함', NULL,
        (SELECT coalesce(string_agg(gate_cd || '=' || n, ', ' ORDER BY gate_cd), '없음')
         FROM (SELECT gate_cd, count(*) n FROM db_pipeline.v_card_integrity_issue GROUP BY 1) g)
    UNION ALL SELECT 'I06', '원문 근거 건수와 지문 — 사전 I06과 같아야 함', NULL,
        (SELECT count(*) || ' ' || md5(string_agg(md5(row(evidence_id, card_doc_id, page_no, card_doc_chunk_id, card_extr_stg_id, quote_txt,
                                                          start_pos, end_pos, approval_status_cd)::text), ',' ORDER BY evidence_id))
         FROM db_pipeline.card_source_evidence)
)
SELECT check_id, check_nm, expected, actual,
       CASE WHEN expected IS NULL THEN NULL ELSE expected IS NOT DISTINCT FROM actual END AS ok
FROM checks ORDER BY check_id;

-- 유형별 원문 근거 연결 (카드 자체·혜택·규칙)
SELECT l.ev_subject_cd, count(*) AS links, count(e.evidence_id) AS joined, count(*) FILTER (WHERE l.card_bnft_id IS NULL) AS bnft_null
FROM db_pipeline.card_evidence_link l
LEFT JOIN db_pipeline.card_source_evidence e
  ON (e.card_doc_id, e.page_no, e.card_doc_chunk_id, e.evidence_id) = (l.card_doc_id, l.page_no, l.card_doc_chunk_id, l.evidence_id)
GROUP BY l.ev_subject_cd ORDER BY l.ev_subject_cd;

ROLLBACK;
