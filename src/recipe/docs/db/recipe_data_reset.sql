-- =====================================================================
-- recipe 스키마 업무 데이터 전체 초기화 (테이블 구조는 유지, DROP/CREATE 없음)
--   대상: database postgres, schema recipe 의 프로젝트 테이블 11개와 프로젝트 시퀀스 7개.
--   다른 스키마는 건드리지 않으며 CASCADE를 쓰지 않는다(TRUNCATE ... RESTRICT).
--   단일 트랜잭션: 사전 검증 → TRUNCATE → 0건 확인 → 시퀀스 재시작 → COMMIT.
--   시퀀스 setval은 rollback되지 않으므로 모든 검증 뒤 마지막에 둔다.
--   실행: python -m recipe_recommender.tools.reset_recipe_data --confirm-reset
--   일반 CSV 등록과 단위 테스트는 이 스크립트를 실행하지 않는다.
-- =====================================================================

BEGIN;

DO $preflight$
DECLARE
    v_expected text[] := ARRAY[
        'rcp_raw','rcp_cat','common_code_grp','common_cd','rcp','rcp_step',
        'ingr_cat','ingr','ingr_als','rcp_ingr_stg','rcp_ingr'];
    v_sequences text[] := ARRAY[
        'seq_rcp_cat','seq_rcp','seq_ingr_cat','seq_ingr','seq_ingr_als','seq_import_batch','seq_rcp_ingr_stg'];
    v_text text;
BEGIN
    IF current_database() <> 'postgres' THEN
        RAISE EXCEPTION 'Unexpected database: %', current_database();
    END IF;

    SELECT string_agg(c.relname, ', ') INTO v_text
    FROM pg_class AS c
    WHERE c.relnamespace = 'recipe'::regnamespace
      AND ((c.relkind IN ('r','p') AND c.relname <> ALL (v_expected))
        OR (c.relkind = 'S' AND c.relname <> ALL (v_sequences))
        OR c.relkind IN ('v','m','f'));
    IF v_text IS NOT NULL THEN
        RAISE EXCEPTION 'Unexpected objects in schema recipe: %', v_text;
    END IF;
    SELECT string_agg(name, ', ') INTO v_text FROM unnest(v_expected) AS name
    WHERE to_regclass('recipe.' || name) IS NULL;
    IF v_text IS NOT NULL THEN
        RAISE EXCEPTION 'Missing project tables: %', v_text;
    END IF;
    SELECT string_agg(name, ', ') INTO v_text FROM unnest(v_sequences) AS name
    WHERE to_regclass('recipe.' || name) IS NULL;
    IF v_text IS NOT NULL THEN
        RAISE EXCEPTION 'Missing project sequences: %', v_text;
    END IF;

    SELECT string_agg(conrelid::regclass::text, ', ') INTO v_text
    FROM pg_constraint
    WHERE contype = 'f'
      AND (confrelid IN (SELECT oid FROM pg_class WHERE relnamespace = 'recipe'::regnamespace)
        OR conrelid IN (SELECT oid FROM pg_class WHERE relnamespace = 'recipe'::regnamespace));
    IF v_text IS NOT NULL THEN
        RAISE EXCEPTION 'Foreign keys referencing recipe objects: %', v_text;
    END IF;
    SELECT string_agg(DISTINCT v.oid::regclass::text, ', ') INTO v_text
    FROM pg_depend AS d
    JOIN pg_rewrite AS rw ON rw.oid = d.objid
    JOIN pg_class AS v ON v.oid = rw.ev_class
    JOIN pg_class AS t ON t.oid = d.refobjid
    WHERE t.relnamespace = 'recipe'::regnamespace AND v.oid <> t.oid;
    IF v_text IS NOT NULL THEN
        RAISE EXCEPTION 'Views depending on recipe tables: %', v_text;
    END IF;
    SELECT string_agg(t.tgname, ', ') INTO v_text
    FROM pg_trigger AS t
    JOIN pg_class AS c ON c.oid = t.tgrelid
    WHERE c.relnamespace = 'recipe'::regnamespace AND NOT t.tgisinternal;
    IF v_text IS NOT NULL THEN
        RAISE EXCEPTION 'User triggers on recipe tables: %', v_text;
    END IF;
    RAISE NOTICE 'Preflight OK: 11 project tables, 7 project sequences, no external dependency';
END
$preflight$;

TRUNCATE TABLE
    recipe.rcp_ingr,
    recipe.rcp_ingr_stg,
    recipe.ingr_als,
    recipe.ingr,
    recipe.ingr_cat,
    recipe.rcp_step,
    recipe.rcp,
    recipe.common_cd,
    recipe.common_code_grp,
    recipe.rcp_cat,
    recipe.rcp_raw
RESTRICT;

DO $verify$
DECLARE
    v_total bigint;
BEGIN
    SELECT (SELECT count(*) FROM recipe.rcp_raw) + (SELECT count(*) FROM recipe.rcp_cat)
         + (SELECT count(*) FROM recipe.common_code_grp) + (SELECT count(*) FROM recipe.common_cd)
         + (SELECT count(*) FROM recipe.rcp) + (SELECT count(*) FROM recipe.rcp_step)
         + (SELECT count(*) FROM recipe.ingr_cat) + (SELECT count(*) FROM recipe.ingr)
         + (SELECT count(*) FROM recipe.ingr_als) + (SELECT count(*) FROM recipe.rcp_ingr_stg)
         + (SELECT count(*) FROM recipe.rcp_ingr)
      INTO v_total;
    IF v_total <> 0 THEN
        RAISE EXCEPTION 'Rows remain after TRUNCATE: %', v_total;
    END IF;
    RAISE NOTICE 'Verify OK: all 11 tables are empty';
END
$verify$;

-- 모든 테이블이 비었으므로 업무 ID를 000001부터 다시 발급해도 충돌하지 않는다.
SELECT setval('recipe.seq_rcp_cat', 1, false);
SELECT setval('recipe.seq_rcp', 1, false);
SELECT setval('recipe.seq_ingr_cat', 1, false);
SELECT setval('recipe.seq_ingr', 1, false);
SELECT setval('recipe.seq_ingr_als', 1, false);
SELECT setval('recipe.seq_import_batch', 1, false);
SELECT setval('recipe.seq_rcp_ingr_stg', 1, false);

COMMIT;
