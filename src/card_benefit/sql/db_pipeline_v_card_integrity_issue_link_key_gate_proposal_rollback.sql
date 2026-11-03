-- =====================================================================================================
-- [제안 / 승인 전 실행 금지] 정합성 뷰 보강 되돌리기: evidence_link_key_mismatch 게이트 제거
-- 현재 정의에서 마지막 UNION ALL 가지(이 게이트)만 잘라 CREATE OR REPLACE한다. 게이트가 마지막 가지가 아니면 중단한다.
-- 게이트가 없으면 아무것도 하지 않는다. 다른 게이트의 결과가 바뀌면 오류로 ROLLBACK한다.
-- =====================================================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SET LOCAL search_path = pg_catalog;

LOCK TABLE db_pipeline.v_card_integrity_issue IN ACCESS EXCLUSIVE MODE;

DO $gate_back$
DECLARE
    c_gate CONSTANT text := 'evidence_link_key_mismatch';
    v_view   regclass := 'db_pipeline.v_card_integrity_issue'::regclass;
    v_def    text;
    v_cut    int;
    v_meta   text;
    v_before text;
    v_after  text;
BEGIN
    v_def := rtrim(pg_get_viewdef(v_view), E'; \n');
    v_cut := position(E'UNION ALL\n SELECT ''' || c_gate || '''::text' IN v_def);
    IF v_cut = 0 THEN
        RAISE NOTICE '게이트 %가 없습니다. 아무것도 바꾸지 않습니다.', c_gate;
        RETURN;
    END IF;
    IF position('UNION ALL' IN substr(v_def, v_cut + 9)) > 0 THEN
        RAISE EXCEPTION '게이트 %가 마지막 가지가 아니라 중단합니다.', c_gate;
    END IF;
    SELECT pg_get_userbyid(relowner) || '|' || coalesce(relacl::text, '-') || '|' || coalesce(obj_description(oid, 'pg_class'), '-') INTO v_meta
    FROM pg_class WHERE oid = v_view;
    SELECT md5(coalesce(string_agg(t::text, E'\n' ORDER BY t::text), '')) INTO v_before
    FROM db_pipeline.v_card_integrity_issue t WHERE t.gate_cd <> c_gate;

    EXECUTE format('CREATE OR REPLACE VIEW db_pipeline.v_card_integrity_issue AS %s', rtrim(substr(v_def, 1, v_cut - 1), E' \n'));

    SELECT md5(coalesce(string_agg(t::text, E'\n' ORDER BY t::text), '')) INTO v_after FROM db_pipeline.v_card_integrity_issue t;
    IF v_after IS DISTINCT FROM v_before
       OR (SELECT pg_get_userbyid(relowner) || '|' || coalesce(relacl::text, '-') || '|' || coalesce(obj_description(oid, 'pg_class'), '-')
           FROM pg_class WHERE oid = v_view) IS DISTINCT FROM v_meta THEN
        RAISE EXCEPTION '검증 실패: 되돌린 뷰의 결과 또는 속성이 다릅니다.';
    END IF;
    RAISE NOTICE '게이트 % 제거 완료', c_gate;
END
$gate_back$;

COMMIT;
