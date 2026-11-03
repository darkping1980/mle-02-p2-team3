-- =====================================================================================================
-- [승인 전 실행 금지] CARD_SOURCE_EVIDENCE PK 승계 변경 되돌리기
-- 변경 후: PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id) + UNIQUE (evidence_id)
-- 되돌린 후: PRIMARY KEY (evidence_id)  (UNIQUE 제거)
--
-- 바꾸는 것: card_source_evidence의 PK와 UNIQUE 제약뿐이다. 데이터는 바꾸지 않는다. CASCADE를 쓰지 않는다.
-- 변경 후에 이 테이블을 참조하는 FK나 PK·UNIQUE에 의존하는 객체가 새로 생겼으면 중단한다.
-- 이미 되돌린 상태면 아무것도 하지 않고, 예상과 다른 상태면 오류로 중단한다.
-- 실행 후 _precheck.sql의 C01~C03, _postcheck.sql의 I01~I04로 원래 상태를 확인한다.
-- =====================================================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

LOCK TABLE db_pipeline.card_source_evidence IN ACCESS EXCLUSIVE MODE;

DO $rollback$
DECLARE
    v_rel          CONSTANT regclass := 'db_pipeline.card_source_evidence';
    v_old_pk       CONSTANT text := 'PRIMARY KEY (evidence_id)';
    v_new_pk       CONSTANT text := 'PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id)';
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

    -- 1. 상태 판정
    IF v_pk_name = 'card_source_evidence_pkey' AND v_pk_def = v_old_pk AND v_unique_count = 0 THEN
        RAISE NOTICE '이미 변경 전 상태입니다. 아무것도 바꾸지 않습니다.';
        RETURN;
    END IF;
    IF v_pk_name IS DISTINCT FROM 'card_source_evidence_pkey' OR v_pk_def IS DISTINCT FROM v_new_pk OR v_unique_count <> 1
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = v_rel AND contype = 'u'
                      AND conname = 'card_source_evidence_evidence_id_key' AND pg_get_constraintdef(oid) = 'UNIQUE (evidence_id)') THEN
        RAISE EXCEPTION '예상과 다른 상태라 중단합니다. PK=% (%), UNIQUE 수=%', v_pk_name, v_pk_def, v_unique_count;
    END IF;

    -- 2. 변경 후 새로 생긴 참조·의존 객체 확인
    SELECT string_agg(problem, '; ') INTO v_problem FROM (
        SELECT 'FK 참조 ' || count(*) AS problem FROM pg_constraint WHERE confrelid = v_rel AND contype = 'f' HAVING count(*) > 0
        UNION ALL
        SELECT 'PK·UNIQUE 의존 객체 ' || count(*) FROM pg_depend d
        WHERE d.refclassid = 'pg_constraint'::regclass AND d.deptype <> 'i'
          AND d.refobjid IN (SELECT oid FROM pg_constraint WHERE conrelid = v_rel AND contype IN ('p', 'u')) HAVING count(*) > 0
    ) p;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION '되돌리면 영향받는 객체가 있어 중단합니다: %', v_problem;
    END IF;

    SELECT count(*), md5(string_agg(md5(e::text), ',' ORDER BY e.evidence_id)) INTO v_count, v_print
    FROM db_pipeline.card_source_evidence e;

    -- 3. 복합 PK 삭제 → EVIDENCE_ID 단독 PK 복원 → UNIQUE 삭제 (EVIDENCE_ID 유일성이 끊기지 않는 순서)
    ALTER TABLE db_pipeline.card_source_evidence
        DROP CONSTRAINT card_source_evidence_pkey;
    ALTER TABLE db_pipeline.card_source_evidence
        ADD CONSTRAINT card_source_evidence_pkey PRIMARY KEY (evidence_id);
    ALTER TABLE db_pipeline.card_source_evidence
        DROP CONSTRAINT card_source_evidence_evidence_id_key;

    -- 4. 되돌린 결과 검증
    IF (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = v_rel AND contype = 'p') IS DISTINCT FROM v_old_pk
       OR (SELECT count(*) FROM pg_constraint WHERE conrelid = v_rel AND contype = 'u') <> 0 THEN
        RAISE EXCEPTION '되돌린 키 구조가 변경 전과 다릅니다.';
    END IF;
    SELECT count(*), md5(string_agg(md5(e::text), ',' ORDER BY e.evidence_id)) INTO v_count_after, v_print_after
    FROM db_pipeline.card_source_evidence e;
    IF v_count_after <> v_count OR v_print_after IS DISTINCT FROM v_print THEN
        RAISE EXCEPTION '근거 데이터가 달라졌습니다. 건수 % → %', v_count, v_count_after;
    END IF;

    RAISE NOTICE '되돌리기 완료. 근거 %건, 행 지문 %', v_count, v_print;
END
$rollback$;

COMMIT;
