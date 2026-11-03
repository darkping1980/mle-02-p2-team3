-- =====================================================================================================
-- [승인 전 실행 금지] CARD_SOURCE_EVIDENCE PK 승계 변경
-- 설계안: CARD_SOURCE_EVIDENCE_PK_INHERITANCE_PROPOSAL_20261103.md
-- 검토서: CARD_SOURCE_EVIDENCE_PK_INHERITANCE_REVIEW_20261103.md
--
-- 변경 전: PRIMARY KEY (evidence_id)
-- 변경 후: PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id) + UNIQUE (evidence_id)
--
-- 바꾸는 것: card_source_evidence의 PK와 UNIQUE 제약 2개뿐이다. 컬럼, 행, 다른 테이블, 뷰, 인덱스
--            ix_card_source_evidence_lookup은 바꾸지 않는다. CASCADE를 쓰지 않는다.
-- 실행 순서: _precheck.sql 통과 → 이 파일 → _postcheck.sql. 되돌리기는 _rollback.sql.
--
-- 안전장치
--   - 한 트랜잭션. 테이블을 ACCESS EXCLUSIVE로 먼저 잠그고(lock_timeout 5초) 같은 잠금 안에서 다시 검증한다.
--   - 현재 상태를 판정한다. 이미 변경된 상태면 아무것도 하지 않고, 예상과 다른 상태면 오류로 중단한다.
--   - 근거 건수와 전체 행 지문(md5)을 변경 전후로 비교해 다르면 오류로 중단한다.
--   - 오류가 나면 트랜잭션이 중단되어 마지막 COMMIT은 ROLLBACK으로 처리된다. 부분 적용이 남지 않는다.
-- =====================================================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

LOCK TABLE db_pipeline.card_source_evidence IN ACCESS EXCLUSIVE MODE;

DO $apply$
DECLARE
    v_rel          CONSTANT regclass := 'db_pipeline.card_source_evidence';
    v_old_pk       CONSTANT text := 'PRIMARY KEY (evidence_id)';
    v_new_pk       CONSTANT text := 'PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id)';
    v_unique       CONSTANT text := 'UNIQUE (evidence_id)';
    v_pk_name      text;
    v_pk_def       text;
    v_unique_count int;
    v_count        bigint;
    v_count_after  bigint;
    v_print        text;
    v_print_after  text;
    v_problem      text;
BEGIN
    SELECT conname, pg_get_constraintdef(oid) INTO v_pk_name, v_pk_def
    FROM pg_constraint WHERE conrelid = v_rel AND contype = 'p';
    SELECT count(*) INTO v_unique_count FROM pg_constraint WHERE conrelid = v_rel AND contype = 'u';

    -- 1. 상태 판정: 이미 변경됨이면 종료, 변경 전 상태가 아니면 중단
    IF v_pk_name = 'card_source_evidence_pkey' AND v_pk_def = v_new_pk AND v_unique_count = 1
       AND EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = v_rel AND contype = 'u'
                   AND conname = 'card_source_evidence_evidence_id_key' AND pg_get_constraintdef(oid) = v_unique) THEN
        RAISE NOTICE '이미 변경된 상태입니다. 아무것도 바꾸지 않습니다.';
        RETURN;
    END IF;
    IF v_pk_name IS DISTINCT FROM 'card_source_evidence_pkey' OR v_pk_def IS DISTINCT FROM v_old_pk OR v_unique_count <> 0 THEN
        RAISE EXCEPTION '예상과 다른 상태라 중단합니다. PK=% (%), UNIQUE 수=%', v_pk_name, v_pk_def, v_unique_count;
    END IF;

    -- 2. 차단 조건 재검증 (잠금을 잡은 뒤의 값)
    SELECT string_agg(problem, '; ') INTO v_problem FROM (
        SELECT 'FK 참조 ' || count(*) AS problem FROM pg_constraint WHERE confrelid = v_rel AND contype = 'f' HAVING count(*) > 0
        UNION ALL
        SELECT 'PK 의존 객체 ' || count(*) FROM pg_depend d
        WHERE d.refclassid = 'pg_constraint'::regclass AND d.deptype <> 'i'
          AND d.refobjid = (SELECT oid FROM pg_constraint WHERE conrelid = v_rel AND contype = 'p') HAVING count(*) > 0
        UNION ALL
        SELECT '새 UNIQUE 이름 사용 중' FROM pg_class
        WHERE relnamespace = 'db_pipeline'::regnamespace AND relname = 'card_source_evidence_evidence_id_key'
        UNION ALL
        SELECT 'PK 컬럼 NULL ' || count(*) FROM db_pipeline.card_source_evidence
        WHERE card_doc_id IS NULL OR page_no IS NULL OR card_doc_chunk_id IS NULL OR evidence_id IS NULL HAVING count(*) > 0
        UNION ALL
        SELECT 'EVIDENCE_ID 중복 ' || count(*) FROM (SELECT 1 FROM db_pipeline.card_source_evidence
                                                    GROUP BY evidence_id HAVING count(*) > 1) x HAVING count(*) > 0
        UNION ALL
        SELECT '상위 청크 없음 ' || count(*) FROM db_pipeline.card_source_evidence e
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc_chunk c WHERE c.card_doc_id = e.card_doc_id
                          AND c.page_no = e.page_no AND c.card_doc_chunk_id = e.card_doc_chunk_id) HAVING count(*) > 0
        UNION ALL
        SELECT '원문 없는 근거 연결 ' || count(*) FROM db_pipeline.card_evidence_link l
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_source_evidence e WHERE e.evidence_id = l.evidence_id) HAVING count(*) > 0
    ) p;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION '차단 조건이 있어 중단합니다: %', v_problem;
    END IF;

    SELECT count(*), md5(string_agg(md5(e::text), ',' ORDER BY e.evidence_id)) INTO v_count, v_print
    FROM db_pipeline.card_source_evidence e;

    -- 3. 키 제약 변경: UNIQUE 먼저 → 기존 PK 삭제(CASCADE 없음) → 복합 PK 생성
    ALTER TABLE db_pipeline.card_source_evidence
        ADD CONSTRAINT card_source_evidence_evidence_id_key UNIQUE (evidence_id);
    ALTER TABLE db_pipeline.card_source_evidence
        DROP CONSTRAINT card_source_evidence_pkey;
    ALTER TABLE db_pipeline.card_source_evidence
        ADD CONSTRAINT card_source_evidence_pkey PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id);

    -- 4. 변경 후 검증: 하나라도 다르면 오류로 전체를 되돌린다
    IF (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = v_rel AND contype = 'p') IS DISTINCT FROM v_new_pk THEN
        RAISE EXCEPTION '변경 후 PK가 목표와 다릅니다.';
    END IF;
    IF (SELECT count(*) FROM pg_constraint WHERE conrelid = v_rel AND contype = 'u'
        AND conname = 'card_source_evidence_evidence_id_key' AND pg_get_constraintdef(oid) = v_unique) <> 1 THEN
        RAISE EXCEPTION '변경 후 EVIDENCE_ID 단독 UNIQUE가 없습니다.';
    END IF;
    SELECT count(*), md5(string_agg(md5(e::text), ',' ORDER BY e.evidence_id)) INTO v_count_after, v_print_after
    FROM db_pipeline.card_source_evidence e;
    IF v_count_after <> v_count OR v_print_after IS DISTINCT FROM v_print THEN
        RAISE EXCEPTION '근거 데이터가 달라졌습니다. 건수 % → %', v_count, v_count_after;
    END IF;

    RAISE NOTICE '변경 완료. 근거 %건, 행 지문 %', v_count, v_print;
END
$apply$;

COMMIT;
