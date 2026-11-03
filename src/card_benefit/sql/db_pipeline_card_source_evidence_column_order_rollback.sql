-- =====================================================================================================
-- [승인 전 실행 금지] CARD_SOURCE_EVIDENCE 컬럼 순서 되돌리기 (테이블 재생성)
-- 변경 스크립트 db_pipeline_card_source_evidence_column_order.sql과 같은 절차이며 컬럼 순서 배열만 반대다.
--
-- 되돌리기 전: card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_extr_stg_id, quote_txt, start_pos, end_pos, approval_status_cd
-- 되돌린 후:   evidence_id, card_doc_id, page_no, card_doc_chunk_id, card_extr_stg_id, quote_txt, start_pos, end_pos, approval_status_cd
-- PK·UNIQUE·CHECK·인덱스·기본값·주석·소유자·권한·RLS·의존 뷰를 그대로 복원하고, 데이터 지문이 같지 않으면 전체 ROLLBACK한다.
-- 이미 되돌린 상태면 아무것도 하지 않고, 예상과 다른 상태면 중단한다.
-- =====================================================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';
SET LOCAL search_path = pg_catalog;

LOCK TABLE db_pipeline.card_source_evidence, db_pipeline.v_card_integrity_issue, db_pipeline.v_common_cd_usage
    IN ACCESS EXCLUSIVE MODE;

DO $reorder$
DECLARE
    c_from  CONSTANT text[] := ARRAY['card_doc_id', 'page_no', 'card_doc_chunk_id', 'evidence_id', 'card_extr_stg_id',
                                     'quote_txt', 'start_pos', 'end_pos', 'approval_status_cd'];
    c_to    CONSTANT text[] := ARRAY['evidence_id', 'card_doc_id', 'page_no', 'card_doc_chunk_id', 'card_extr_stg_id',
                                     'quote_txt', 'start_pos', 'end_pos', 'approval_status_cd'];
    -- 지문용 고정 컬럼 순서(최초 컬럼 순서). 변경 전후, 되돌리기 전후 모두 같은 식으로 계산한다.
    c_print CONSTANT text[] := ARRAY['evidence_id', 'card_doc_id', 'page_no', 'card_doc_chunk_id', 'card_extr_stg_id',
                                     'quote_txt', 'start_pos', 'end_pos', 'approval_status_cd'];
    c_views CONSTANT text[] := ARRAY['v_common_cd_usage', 'v_card_integrity_issue'];   -- 생성 순서. 삭제는 역순
    c_table CONSTANT text := 'card_source_evidence';
    c_old   CONSTANT text := 'card_source_evidence__reorder_old';
    v_rel        regclass := 'db_pipeline.card_source_evidence'::regclass;
    v_current    text[];
    v_problem    text;
    v_cols       jsonb;   -- 컬럼 이름 → 정의
    v_cons       jsonb;   -- 제약 이름 → 유형·정의 (생성 순서 유지용 배열)
    v_idx        jsonb;   -- 제약이 아닌 인덱스 이름 → 정의
    v_tab        jsonb;   -- 테이블 속성
    v_views      jsonb;   -- 뷰 이름 → 정의·속성·결과 지문
    v_count      bigint;
    v_print      text;
    v_count2     bigint;
    v_print2     text;
    v_sql        text;
    v_item       record;
    v_name       text;
    v_after      jsonb;
BEGIN
    -- 1. 상태 판정
    SELECT array_agg(attname::text ORDER BY attnum) INTO v_current
    FROM pg_attribute WHERE attrelid = v_rel AND attnum > 0 AND NOT attisdropped;
    IF v_current = c_to THEN
        RAISE NOTICE '이미 목표 컬럼 순서입니다. 아무것도 바꾸지 않습니다: %', array_to_string(c_to, ', ');
        RETURN;
    END IF;
    IF v_current IS DISTINCT FROM c_from THEN
        RAISE EXCEPTION '예상과 다른 컬럼 구성이라 중단합니다: %', array_to_string(v_current, ', ');
    END IF;

    -- 2. 복원하지 않는 종속 객체가 있으면 중단
    SELECT string_agg(p, '; ') INTO v_problem FROM (
        SELECT '테이블 의존 객체: ' || pg_describe_object(d.classid, d.objid, d.objsubid) AS p
        FROM pg_depend d
        WHERE d.refclassid = 'pg_class'::regclass AND d.refobjid = v_rel
          AND NOT (d.classid = 'pg_attrdef'::regclass)
          AND NOT (d.classid = 'pg_type'::regclass AND d.objid = (SELECT reltype FROM pg_class WHERE oid = v_rel))   -- 자기 행 타입
          AND NOT (d.classid = 'pg_constraint'::regclass AND d.objid IN (SELECT oid FROM pg_constraint WHERE conrelid = v_rel))
          AND NOT (d.classid = 'pg_class'::regclass AND d.objid IN (SELECT indexrelid FROM pg_index WHERE indrelid = v_rel))
          AND NOT (d.classid = 'pg_class'::regclass AND d.objid = (SELECT reltoastrelid FROM pg_class WHERE oid = v_rel))
          AND NOT (d.classid = 'pg_rewrite'::regclass AND d.objid IN (
                SELECT r.oid FROM pg_rewrite r JOIN pg_class v ON v.oid = r.ev_class
                WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views)))
        UNION ALL
        SELECT '행 타입 의존 객체: ' || pg_describe_object(d.classid, d.objid, d.objsubid)
        FROM pg_depend d
        WHERE d.refclassid = 'pg_type'::regclass AND d.refobjid = (SELECT reltype FROM pg_class WHERE oid = v_rel)
          AND NOT (d.classid = 'pg_type'::regclass AND d.deptype = 'i')
        UNION ALL
        SELECT '뷰 의존 객체: ' || pg_describe_object(d.classid, d.objid, d.objsubid)
        FROM pg_class v JOIN pg_depend d ON d.refclassid = 'pg_class'::regclass AND d.refobjid = v.oid
        WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views)
          AND NOT (d.classid = 'pg_type'::regclass)
          AND NOT (d.classid = 'pg_rewrite'::regclass AND d.objid IN (
                SELECT r.oid FROM pg_rewrite r JOIN pg_class w ON w.oid = r.ev_class
                WHERE w.relnamespace = 'db_pipeline'::regnamespace AND w.relname = ANY (c_views)))
        UNION ALL
        SELECT '뷰 행 타입 의존 객체: ' || pg_describe_object(d.classid, d.objid, d.objsubid)
        FROM pg_class v JOIN pg_depend d ON d.refclassid = 'pg_type'::regclass AND d.refobjid = v.reltype
        WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views) AND d.deptype <> 'i'
        UNION ALL
        SELECT '트리거 ' || count(*) FROM pg_trigger WHERE tgrelid = v_rel AND NOT tgisinternal HAVING count(*) > 0
        UNION ALL
        SELECT '정책 ' || count(*) FROM pg_policy WHERE polrelid = v_rel HAVING count(*) > 0
        UNION ALL
        SELECT '규칙 ' || count(*) FROM pg_rewrite WHERE ev_class = v_rel HAVING count(*) > 0
        UNION ALL
        SELECT '발행 ' || count(*) FROM pg_publication_rel WHERE prrelid = v_rel HAVING count(*) > 0
        UNION ALL
        SELECT '상속 ' || count(*) FROM pg_inherits WHERE inhrelid = v_rel OR inhparent = v_rel HAVING count(*) > 0
        UNION ALL
        SELECT '확장 통계 ' || count(*) FROM pg_statistic_ext WHERE stxrelid = v_rel HAVING count(*) > 0
        UNION ALL
        SELECT '보안 레이블 ' || count(*) FROM pg_seclabel WHERE objoid = v_rel HAVING count(*) > 0
        UNION ALL
        SELECT '컬럼 권한·식별·생성·옵션 ' || count(*) FROM pg_attribute
        WHERE attrelid = v_rel AND attnum > 0 AND (attacl IS NOT NULL OR attidentity <> '' OR attgenerated <> ''
              OR attoptions IS NOT NULL OR attcollation NOT IN (0, 100)) HAVING count(*) > 0
        UNION ALL
        SELECT '복원하지 않는 제약 유형 ' || string_agg(conname, ',') FROM pg_constraint
        WHERE conrelid = v_rel AND contype NOT IN ('c', 'p', 'u') HAVING count(*) > 0
        UNION ALL
        SELECT '뷰 옵션·컬럼 주석·컬럼 권한' FROM pg_class v
        WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views)
          AND (v.reloptions IS NOT NULL OR EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = v.oid AND a.attnum > 0
                AND (a.attacl IS NOT NULL OR col_description(v.oid, a.attnum) IS NOT NULL)))
        UNION ALL
        SELECT '뷰 없음 ' || x FROM unnest(c_views) x
        WHERE to_regclass('db_pipeline.' || x) IS NULL
        UNION ALL
        SELECT '임시 이름 사용 중' WHERE to_regclass('db_pipeline.' || c_old) IS NOT NULL
    ) problems;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION '복원하지 않는 종속 객체가 있어 중단합니다: %', v_problem;
    END IF;

    -- 3. 현재 정의 읽기
    SELECT jsonb_object_agg(a.attname, jsonb_build_object(
               'type', format_type(a.atttypid, a.atttypmod), 'notnull', a.attnotnull,
               'default', pg_get_expr(d.adbin, d.adrelid), 'comment', col_description(a.attrelid, a.attnum),
               'storage', a.attstorage, 'compression', a.attcompression, 'stattarget', a.attstattarget))
      INTO v_cols
    FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    WHERE a.attrelid = v_rel AND a.attnum > 0 AND NOT a.attisdropped;

    SELECT jsonb_agg(jsonb_build_object('name', conname, 'type', contype, 'def', pg_get_constraintdef(oid),
                                        'comment', obj_description(oid, 'pg_constraint'))
                     ORDER BY CASE contype WHEN 'c' THEN 1 WHEN 'p' THEN 2 ELSE 3 END, conname)
      INTO v_cons
    FROM pg_constraint WHERE conrelid = v_rel;

    SELECT coalesce(jsonb_agg(jsonb_build_object('name', c.relname, 'def', pg_get_indexdef(i.indexrelid),
                                                 'comment', obj_description(i.indexrelid, 'pg_class'))
                              ORDER BY c.relname), '[]'::jsonb)
      INTO v_idx
    FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
    WHERE i.indrelid = v_rel AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid AND k.conrelid = v_rel);

    SELECT jsonb_build_object('owner', pg_get_userbyid(relowner), 'acl', relacl::text, 'rls', relrowsecurity,
                              'force_rls', relforcerowsecurity, 'replident', relreplident, 'reloptions', reloptions,
                              'comment', obj_description(oid, 'pg_class'))
      INTO v_tab
    FROM pg_class WHERE oid = v_rel;
    IF v_tab->>'replident' NOT IN ('d') THEN
        RAISE EXCEPTION 'REPLICA IDENTITY %는 이 스크립트가 복원하지 않아 중단합니다.', v_tab->>'replident';
    END IF;

    SELECT jsonb_object_agg(v.relname, jsonb_build_object(
               'def', pg_get_viewdef(v.oid), 'owner', pg_get_userbyid(v.relowner), 'acl', v.relacl::text,
               'comment', obj_description(v.oid, 'pg_class')))
      INTO v_views
    FROM pg_class v WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views);
    FOREACH v_name IN ARRAY c_views LOOP
        EXECUTE format('SELECT md5(coalesce(string_agg(t::text, E''\n'' ORDER BY t::text), '''')) FROM db_pipeline.%I t', v_name)
          INTO v_print;
        v_views := jsonb_set(v_views, ARRAY[v_name, 'result'], to_jsonb(v_print));
    END LOOP;

    v_sql := format('SELECT count(*), md5(string_agg(md5(row(%s)::text), '','' ORDER BY evidence_id)) FROM db_pipeline.%I',
                    (SELECT string_agg(quote_ident(x), ', ' ORDER BY o) FROM unnest(c_print) WITH ORDINALITY u(x, o)), c_table);
    EXECUTE v_sql INTO v_count, v_print;

    -- 4. 교체
    FOREACH v_name IN ARRAY (SELECT array_agg(x ORDER BY o DESC) FROM unnest(c_views) WITH ORDINALITY u(x, o)) LOOP
        EXECUTE format('DROP VIEW db_pipeline.%I', v_name);                                   -- CASCADE 없음
    END LOOP;

    EXECUTE format('ALTER TABLE db_pipeline.%I RENAME TO %I', c_table, c_old);
    FOR v_item IN SELECT value AS c FROM jsonb_array_elements(v_cons) WHERE value->>'type' IN ('p', 'u') LOOP
        EXECUTE format('ALTER TABLE db_pipeline.%I RENAME CONSTRAINT %I TO %I', c_old, v_item.c->>'name', (v_item.c->>'name') || '__old');
    END LOOP;
    FOR v_item IN SELECT value AS c FROM jsonb_array_elements(v_idx) LOOP
        EXECUTE format('ALTER INDEX db_pipeline.%I RENAME TO %I', v_item.c->>'name', (v_item.c->>'name') || '__old');
    END LOOP;

    EXECUTE format('CREATE TABLE db_pipeline.%I (%s)', c_table, (
        SELECT string_agg(format('%I %s%s%s', x, v_cols->x->>'type',
                                 CASE WHEN v_cols->x->>'default' IS NOT NULL THEN ' DEFAULT ' || (v_cols->x->>'default') ELSE '' END,
                                 CASE WHEN (v_cols->x->>'notnull')::boolean THEN ' NOT NULL' ELSE '' END), ', ' ORDER BY o)
        FROM unnest(c_to) WITH ORDINALITY u(x, o)));

    v_sql := (SELECT string_agg(quote_ident(x), ', ' ORDER BY o) FROM unnest(c_to) WITH ORDINALITY u(x, o));
    EXECUTE format('INSERT INTO db_pipeline.%I (%s) SELECT %s FROM db_pipeline.%I', c_table, v_sql, v_sql, c_old);

    FOR v_item IN SELECT value AS c FROM jsonb_array_elements(v_cons) LOOP
        EXECUTE format('ALTER TABLE db_pipeline.%I ADD CONSTRAINT %I %s', c_table, v_item.c->>'name', v_item.c->>'def');
        IF v_item.c->>'comment' IS NOT NULL THEN
            EXECUTE format('COMMENT ON CONSTRAINT %I ON db_pipeline.%I IS %L', v_item.c->>'name', c_table, v_item.c->>'comment');
        END IF;
    END LOOP;
    FOR v_item IN SELECT value AS c FROM jsonb_array_elements(v_idx) LOOP
        EXECUTE v_item.c->>'def';                                    -- 기존 정의 그대로 (이름 변경 전에 읽은 문장)
        IF v_item.c->>'comment' IS NOT NULL THEN
            EXECUTE format('COMMENT ON INDEX db_pipeline.%I IS %L', v_item.c->>'name', v_item.c->>'comment');
        END IF;
    END LOOP;

    EXECUTE format('DROP TABLE db_pipeline.%I', c_old);                                       -- CASCADE 없음

    EXECUTE format('ALTER TABLE db_pipeline.%I OWNER TO %I', c_table, v_tab->>'owner');
    IF v_tab->>'comment' IS NOT NULL THEN
        EXECUTE format('COMMENT ON TABLE db_pipeline.%I IS %L', c_table, v_tab->>'comment');
    END IF;
    FOR v_name IN SELECT x FROM unnest(c_to) x WHERE v_cols->x->>'comment' IS NOT NULL LOOP
        EXECUTE format('COMMENT ON COLUMN db_pipeline.%I.%I IS %L', c_table, v_name, v_cols->v_name->>'comment');
    END LOOP;
    IF v_tab->>'acl' IS NOT NULL THEN
        FOR v_item IN SELECT a.privilege_type, a.is_grantable,
                             CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(a.grantee)) END AS grantee
                      FROM aclexplode((v_tab->>'acl')::aclitem[]) a LOOP
            EXECUTE format('GRANT %s ON db_pipeline.%I TO %s%s', v_item.privilege_type, c_table, v_item.grantee,
                           CASE WHEN v_item.is_grantable THEN ' WITH GRANT OPTION' ELSE '' END);
        END LOOP;
    END IF;
    IF (v_tab->>'rls')::boolean IS DISTINCT FROM (SELECT relrowsecurity FROM pg_class WHERE oid = ('db_pipeline.' || c_table)::regclass) THEN
        EXECUTE format('ALTER TABLE db_pipeline.%I %s ROW LEVEL SECURITY', c_table,
                       CASE WHEN (v_tab->>'rls')::boolean THEN 'ENABLE' ELSE 'DISABLE' END);
    END IF;
    IF (v_tab->>'force_rls')::boolean THEN
        EXECUTE format('ALTER TABLE db_pipeline.%I FORCE ROW LEVEL SECURITY', c_table);
    END IF;
    IF v_tab->'reloptions' <> 'null'::jsonb THEN
        EXECUTE format('ALTER TABLE db_pipeline.%I SET (%s)', c_table,
                       (SELECT string_agg(x, ', ') FROM jsonb_array_elements_text(v_tab->'reloptions') x));
    END IF;

    FOREACH v_name IN ARRAY c_views LOOP
        EXECUTE format('CREATE VIEW db_pipeline.%I AS %s', v_name, rtrim(v_views->v_name->>'def', E'; \n'));
        EXECUTE format('ALTER VIEW db_pipeline.%I OWNER TO %I', v_name, v_views->v_name->>'owner');
        IF v_views->v_name->>'comment' IS NOT NULL THEN
            EXECUTE format('COMMENT ON VIEW db_pipeline.%I IS %L', v_name, v_views->v_name->>'comment');
        END IF;
        IF v_views->v_name->>'acl' IS NOT NULL THEN
            FOR v_item IN SELECT a.privilege_type, a.is_grantable,
                                 CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(a.grantee)) END AS grantee
                          FROM aclexplode((v_views->v_name->>'acl')::aclitem[]) a LOOP
                EXECUTE format('GRANT %s ON db_pipeline.%I TO %s%s', v_item.privilege_type, v_name, v_item.grantee,
                               CASE WHEN v_item.is_grantable THEN ' WITH GRANT OPTION' ELSE '' END);
            END LOOP;
        END IF;
    END LOOP;

    -- 5. 검증: 하나라도 다르면 오류로 전체 ROLLBACK
    v_rel := ('db_pipeline.' || c_table)::regclass;
    SELECT array_agg(attname::text ORDER BY attnum) INTO v_current
    FROM pg_attribute WHERE attrelid = v_rel AND attnum > 0 AND NOT attisdropped;
    IF v_current IS DISTINCT FROM c_to THEN
        RAISE EXCEPTION '검증 실패: 컬럼 순서 %', array_to_string(v_current, ', ');
    END IF;

    SELECT jsonb_object_agg(a.attname, jsonb_build_object(
               'type', format_type(a.atttypid, a.atttypmod), 'notnull', a.attnotnull,
               'default', pg_get_expr(d.adbin, d.adrelid), 'comment', col_description(a.attrelid, a.attnum),
               'storage', a.attstorage, 'compression', a.attcompression, 'stattarget', a.attstattarget))
      INTO v_after
    FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
    WHERE a.attrelid = v_rel AND a.attnum > 0 AND NOT a.attisdropped;
    IF v_after IS DISTINCT FROM v_cols THEN
        RAISE EXCEPTION '검증 실패: 컬럼 정의가 다릅니다. 전 % / 후 %', v_cols, v_after;
    END IF;

    SELECT jsonb_agg(jsonb_build_object('name', conname, 'type', contype, 'def', pg_get_constraintdef(oid),
                                        'comment', obj_description(oid, 'pg_constraint'))
                     ORDER BY CASE contype WHEN 'c' THEN 1 WHEN 'p' THEN 2 ELSE 3 END, conname)
      INTO v_after
    FROM pg_constraint WHERE conrelid = v_rel;
    IF v_after IS DISTINCT FROM v_cons THEN
        RAISE EXCEPTION '검증 실패: 제약이 다릅니다. 전 % / 후 %', v_cons, v_after;
    END IF;

    SELECT coalesce(jsonb_agg(jsonb_build_object('name', c.relname, 'def', pg_get_indexdef(i.indexrelid),
                                                 'comment', obj_description(i.indexrelid, 'pg_class'))
                              ORDER BY c.relname), '[]'::jsonb)
      INTO v_after
    FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
    WHERE i.indrelid = v_rel AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid AND k.conrelid = v_rel);
    IF v_after IS DISTINCT FROM v_idx THEN
        RAISE EXCEPTION '검증 실패: 인덱스가 다릅니다. 전 % / 후 %', v_idx, v_after;
    END IF;

    SELECT jsonb_build_object('owner', pg_get_userbyid(relowner), 'acl', relacl::text, 'rls', relrowsecurity,
                              'force_rls', relforcerowsecurity, 'replident', relreplident, 'reloptions', reloptions,
                              'comment', obj_description(oid, 'pg_class'))
      INTO v_after
    FROM pg_class WHERE oid = v_rel;
    IF v_after IS DISTINCT FROM v_tab THEN
        RAISE EXCEPTION '검증 실패: 테이블 속성(소유자·권한·RLS·주석)이 다릅니다. 전 % / 후 %', v_tab, v_after;
    END IF;

    v_sql := format('SELECT count(*), md5(string_agg(md5(row(%s)::text), '','' ORDER BY evidence_id)) FROM db_pipeline.%I',
                    (SELECT string_agg(quote_ident(x), ', ' ORDER BY o) FROM unnest(c_print) WITH ORDINALITY u(x, o)), c_table);
    EXECUTE v_sql INTO v_count2, v_print2;
    IF v_count2 <> v_count OR v_print2 IS DISTINCT FROM v_print THEN
        RAISE EXCEPTION '검증 실패: 데이터가 다릅니다. 건수 % → %, 지문 % → %', v_count, v_count2, v_print, v_print2;
    END IF;

    FOREACH v_name IN ARRAY c_views LOOP
        EXECUTE format('SELECT md5(coalesce(string_agg(t::text, E''\n'' ORDER BY t::text), '''')) FROM db_pipeline.%I t', v_name)
          INTO v_print2;
        SELECT jsonb_build_object('def', pg_get_viewdef(v.oid), 'owner', pg_get_userbyid(v.relowner), 'acl', v.relacl::text,
                                  'comment', obj_description(v.oid, 'pg_class'), 'result', v_print2)
          INTO v_after
        FROM pg_class v WHERE v.oid = ('db_pipeline.' || v_name)::regclass;
        IF v_after IS DISTINCT FROM v_views->v_name THEN
            RAISE EXCEPTION '검증 실패: 뷰 %의 정의·속성·결과가 다릅니다.', v_name;
        END IF;
    END LOOP;

    RAISE NOTICE '컬럼 순서 되돌리기 완료: %. 근거 %건, 지문 %. 제약 %개, 인덱스 %개, 뷰 %개 복원',
        array_to_string(c_to, ', '), v_count, v_print, jsonb_array_length(v_cons), jsonb_array_length(v_idx), array_length(c_views, 1);
END
$reorder$;

ANALYZE db_pipeline.card_source_evidence;

COMMIT;
