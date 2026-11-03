-- =====================================================================================================
-- [승인 전 실행 금지] CARD_EVIDENCE_LINK PK 승계 되돌리기
-- 되돌리기 전: card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id, card_bnft_id, ev_subject_cd,
--             rule_key, relation_key, ev_item_cd, ev_item_key / PK 6컬럼 + UNIQUE (card_id, evidence_link_id)
-- 되돌린 후:   card_id, ev_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, ev_item_cd, ev_item_key, evidence_id
--             PK (card_id, ev_link_id)
-- 승계 컬럼 3개는 원문 근거에서 다시 얻을 수 있는 값이라 버린다. 그 밖의 값은 그대로 옮기고 행 지문으로 확인한다.
-- 되돌리기 전에 승계 컬럼이 원문 근거와 다른 행이 있으면 중단한다(그 사이 잘못 등록된 행을 숨기지 않기 위해).
-- 같은 이유로 _precheck.sql의 되돌리기 판정 항목을 먼저 확인한다. 한 트랜잭션, 실패하면 전체 ROLLBACK.
-- 프로그램 SQL도 함께 되돌려야 한다(검토서 7절).
-- =====================================================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';
SET LOCAL search_path = pg_catalog;

LOCK TABLE db_pipeline.card_evidence_link, db_pipeline.v_card_integrity_issue, db_pipeline.v_common_cd_usage IN ACCESS EXCLUSIVE MODE;
LOCK TABLE db_pipeline.card_source_evidence IN SHARE MODE;

DO $link_back$
DECLARE
    c_from  CONSTANT text[] := ARRAY['card_doc_id', 'page_no', 'card_doc_chunk_id', 'evidence_id', 'card_id', 'evidence_link_id',
                                     'card_bnft_id', 'ev_subject_cd', 'rule_key', 'relation_key', 'ev_item_cd', 'ev_item_key'];
    c_to    CONSTANT text[] := ARRAY['card_id', 'ev_link_id', 'ev_subject_cd', 'card_bnft_id', 'rule_key', 'relation_key',
                                     'ev_item_cd', 'ev_item_key', 'evidence_id'];
    c_views CONSTANT text[] := ARRAY['v_common_cd_usage', 'v_card_integrity_issue'];
    v_rel      regclass := 'db_pipeline.card_evidence_link'::regclass;
    v_current  text[];
    v_problem  text;
    v_cons     jsonb; v_idx jsonb; v_comments jsonb; v_tab jsonb; v_views jsonb;
    v_count    bigint; v_print text; v_subjects text;
    v_count2   bigint; v_print2 text; v_subjects2 text;
    v_name     text; v_item record; v_after jsonb; v_out text;
BEGIN
    SELECT array_agg(attname::text ORDER BY attnum) INTO v_current FROM pg_attribute WHERE attrelid = v_rel AND attnum > 0 AND NOT attisdropped;
    IF v_current = c_to THEN
        RAISE NOTICE '이미 변경 전 구조입니다. 아무것도 바꾸지 않습니다.';
        RETURN;
    END IF;
    IF v_current IS DISTINCT FROM c_from THEN
        RAISE EXCEPTION '예상과 다른 컬럼 구성이라 중단합니다: %', array_to_string(v_current, ', ');
    END IF;

    SELECT string_agg(p, '; ') INTO v_problem FROM (
        SELECT '테이블 의존 객체: ' || pg_describe_object(d.classid, d.objid, d.objsubid) AS p
        FROM pg_depend d
        WHERE d.refclassid = 'pg_class'::regclass AND d.refobjid = v_rel
          AND d.classid <> 'pg_attrdef'::regclass
          AND NOT (d.classid = 'pg_type'::regclass AND d.objid = (SELECT reltype FROM pg_class WHERE oid = v_rel))
          AND NOT (d.classid = 'pg_constraint'::regclass AND d.objid IN (SELECT oid FROM pg_constraint WHERE conrelid = v_rel))
          AND NOT (d.classid = 'pg_class'::regclass AND d.objid IN (SELECT indexrelid FROM pg_index WHERE indrelid = v_rel))
          AND NOT (d.classid = 'pg_class'::regclass AND d.objid = (SELECT reltoastrelid FROM pg_class WHERE oid = v_rel))
          AND NOT (d.classid = 'pg_rewrite'::regclass AND d.objid IN (
                SELECT r.oid FROM pg_rewrite r JOIN pg_class v ON v.oid = r.ev_class
                WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views)))
        UNION ALL
        SELECT '행 타입 의존 객체: ' || pg_describe_object(d.classid, d.objid, d.objsubid)
        FROM pg_depend d WHERE d.refclassid = 'pg_type'::regclass AND d.refobjid = (SELECT reltype FROM pg_class WHERE oid = v_rel) AND d.deptype <> 'i'
        UNION ALL
        SELECT '뷰 의존 객체: ' || pg_describe_object(d.classid, d.objid, d.objsubid)
        FROM pg_class v JOIN pg_depend d ON d.refclassid = 'pg_class'::regclass AND d.refobjid = v.oid
        WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views) AND d.classid <> 'pg_type'::regclass
          AND NOT (d.classid = 'pg_rewrite'::regclass AND d.objid IN (
                SELECT r.oid FROM pg_rewrite r JOIN pg_class w ON w.oid = r.ev_class
                WHERE w.relnamespace = 'db_pipeline'::regnamespace AND w.relname = ANY (c_views)))
        UNION ALL
        SELECT 'FK·트리거·정책 ' || ((SELECT count(*) FROM pg_constraint WHERE (conrelid = v_rel OR confrelid = v_rel) AND contype = 'f')
                                + (SELECT count(*) FROM pg_trigger WHERE tgrelid = v_rel AND NOT tgisinternal) + (SELECT count(*) FROM pg_policy WHERE polrelid = v_rel))
        WHERE (SELECT count(*) FROM pg_constraint WHERE (conrelid = v_rel OR confrelid = v_rel) AND contype = 'f')
            + (SELECT count(*) FROM pg_trigger WHERE tgrelid = v_rel AND NOT tgisinternal) + (SELECT count(*) FROM pg_policy WHERE polrelid = v_rel) > 0
        UNION ALL
        SELECT '승계 컬럼이 원문 근거와 다른 행 ' || count(*) FROM db_pipeline.card_evidence_link l
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_source_evidence e WHERE (e.card_doc_id, e.page_no, e.card_doc_chunk_id, e.evidence_id)
                          = (l.card_doc_id, l.page_no, l.card_doc_chunk_id, l.evidence_id)) HAVING count(*) > 0
        UNION ALL
        SELECT '임시 이름 사용 중' WHERE to_regclass('db_pipeline.card_evidence_link__pkinherit_new') IS NOT NULL
    ) problems;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION '차단 조건이 있어 중단합니다: %', v_problem;
    END IF;

    SELECT count(*), md5(string_agg(md5(row(card_id, evidence_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key,
                                            ev_item_cd, ev_item_key, evidence_id)::text), ',' ORDER BY card_id, evidence_link_id))
      INTO v_count, v_print FROM db_pipeline.card_evidence_link;
    SELECT string_agg(ev_subject_cd || '=' || n, ', ' ORDER BY ev_subject_cd) INTO v_subjects
    FROM (SELECT ev_subject_cd, count(*) n FROM db_pipeline.card_evidence_link GROUP BY 1) g;
    SELECT jsonb_agg(jsonb_build_object('name', conname, 'def', pg_get_constraintdef(oid)) ORDER BY conname) INTO v_cons
    FROM pg_constraint WHERE conrelid = v_rel AND conname IN ('card_evidence_link_ck_1', 'card_evidence_link_ck_2', 'card_evidence_link_natural_key');
    SELECT coalesce(jsonb_agg(jsonb_build_object('name', c.relname, 'def', pg_get_indexdef(i.indexrelid)) ORDER BY c.relname), '[]'::jsonb) INTO v_idx
    FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
    WHERE i.indrelid = v_rel AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid AND k.conrelid = v_rel);
    SELECT jsonb_build_object('owner', pg_get_userbyid(relowner), 'acl', relacl::text, 'rls', relrowsecurity,
                              'force_rls', relforcerowsecurity, 'replident', relreplident, 'reloptions', reloptions,
                              'comment', obj_description(oid, 'pg_class')) INTO v_tab FROM pg_class WHERE oid = v_rel;

    -- 컬럼 이름을 먼저 되돌려 뷰 정의가 ev_link_id를 따라가게 한다
    ALTER TABLE db_pipeline.card_evidence_link RENAME COLUMN evidence_link_id TO ev_link_id;
    SELECT jsonb_object_agg(attname, col_description(attrelid, attnum)) INTO v_comments
    FROM pg_attribute WHERE attrelid = v_rel AND attnum > 0 AND NOT attisdropped;
    SELECT jsonb_object_agg(v.relname, jsonb_build_object('def', pg_get_viewdef(v.oid), 'owner', pg_get_userbyid(v.relowner),
                                                          'acl', v.relacl::text, 'comment', obj_description(v.oid, 'pg_class')))
      INTO v_views FROM pg_class v WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views);
    FOREACH v_name IN ARRAY c_views LOOP
        EXECUTE format('SELECT md5(coalesce(string_agg(t::text, E''\n'' ORDER BY t::text), '''')) FROM db_pipeline.%I t', v_name) INTO v_out;
        v_views := jsonb_set(v_views, ARRAY[v_name, 'result'], to_jsonb(v_out));
    END LOOP;

    DROP VIEW db_pipeline.v_card_integrity_issue;
    DROP VIEW db_pipeline.v_common_cd_usage;
    ALTER TABLE db_pipeline.card_evidence_link RENAME TO card_evidence_link__pkinherit_new;
    ALTER TABLE db_pipeline.card_evidence_link__pkinherit_new RENAME CONSTRAINT card_evidence_link_pkey TO card_evidence_link_pkey__new;
    ALTER TABLE db_pipeline.card_evidence_link__pkinherit_new RENAME CONSTRAINT card_evidence_link_natural_key TO card_evidence_link_natural_key__new;
    FOR v_item IN SELECT value AS c FROM jsonb_array_elements(v_idx) LOOP
        EXECUTE format('ALTER INDEX db_pipeline.%I RENAME TO %I', v_item.c->>'name', (v_item.c->>'name') || '__new');
    END LOOP;

    CREATE TABLE db_pipeline.card_evidence_link (
        card_id       bigint NOT NULL,
        ev_link_id    varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_evidence_link') NOT NULL,
        ev_subject_cd varchar(10) NOT NULL,
        card_bnft_id  varchar(20),
        rule_key      varchar(40),
        relation_key  varchar(40),
        ev_item_cd    varchar(10) DEFAULT 'SELF' NOT NULL,
        ev_item_key   varchar(100) DEFAULT '-' NOT NULL,
        evidence_id   varchar(20) NOT NULL
    );
    INSERT INTO db_pipeline.card_evidence_link (card_id, ev_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, ev_item_cd, ev_item_key, evidence_id)
    SELECT card_id, ev_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, ev_item_cd, ev_item_key, evidence_id
    FROM db_pipeline.card_evidence_link__pkinherit_new;

    FOR v_item IN SELECT value AS c FROM jsonb_array_elements(v_cons) WHERE value->>'name' LIKE '%\_ck\_%' LOOP
        EXECUTE format('ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT %I %s', v_item.c->>'name', v_item.c->>'def');
    END LOOP;
    ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_pkey PRIMARY KEY (card_id, ev_link_id);
    EXECUTE format('ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_natural_key %s',
                   (SELECT value->>'def' FROM jsonb_array_elements(v_cons) WHERE value->>'name' = 'card_evidence_link_natural_key'));
    FOR v_item IN SELECT value AS c FROM jsonb_array_elements(v_idx) LOOP
        EXECUTE v_item.c->>'def';
    END LOOP;
    DROP TABLE db_pipeline.card_evidence_link__pkinherit_new;                             -- CASCADE 없음

    EXECUTE format('ALTER TABLE db_pipeline.card_evidence_link OWNER TO %I', v_tab->>'owner');
    EXECUTE format('COMMENT ON TABLE db_pipeline.card_evidence_link IS %L', v_tab->>'comment');
    FOREACH v_name IN ARRAY c_to LOOP
        IF v_comments->>v_name IS NOT NULL THEN
            EXECUTE format('COMMENT ON COLUMN db_pipeline.card_evidence_link.%I IS %L', v_name, v_comments->>v_name);
        END IF;
    END LOOP;
    IF v_tab->>'acl' IS NOT NULL THEN
        FOR v_item IN SELECT a.privilege_type, a.is_grantable,
                             CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(a.grantee)) END AS grantee
                      FROM aclexplode((v_tab->>'acl')::aclitem[]) a LOOP
            EXECUTE format('GRANT %s ON db_pipeline.card_evidence_link TO %s%s', v_item.privilege_type, v_item.grantee,
                           CASE WHEN v_item.is_grantable THEN ' WITH GRANT OPTION' ELSE '' END);
        END LOOP;
    END IF;
    IF (v_tab->>'rls')::boolean THEN ALTER TABLE db_pipeline.card_evidence_link ENABLE ROW LEVEL SECURITY; END IF;
    COMMENT ON SEQUENCE db_pipeline.seq_card_evidence_link IS 'card_evidence_link.ev_link_id 로컬 업무 ID 발급';

    FOREACH v_name IN ARRAY c_views LOOP
        EXECUTE format('CREATE VIEW db_pipeline.%I AS %s', v_name, rtrim(v_views->v_name->>'def', E'; \n'));
        EXECUTE format('ALTER VIEW db_pipeline.%I OWNER TO %I', v_name, v_views->v_name->>'owner');
        IF v_views->v_name->>'comment' IS NOT NULL THEN
            EXECUTE format('COMMENT ON VIEW db_pipeline.%I IS %L', v_name, v_views->v_name->>'comment');
        END IF;
    END LOOP;

    v_rel := 'db_pipeline.card_evidence_link'::regclass;
    SELECT array_agg(attname::text ORDER BY attnum) INTO v_current FROM pg_attribute WHERE attrelid = v_rel AND attnum > 0 AND NOT attisdropped;
    IF v_current IS DISTINCT FROM c_to
       OR (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = v_rel AND contype = 'p') IS DISTINCT FROM 'PRIMARY KEY (card_id, ev_link_id)'
       OR (SELECT count(*) FROM pg_constraint WHERE conrelid = v_rel) <> 4 THEN
        RAISE EXCEPTION '검증 실패: 되돌린 구조가 다릅니다.';
    END IF;
    SELECT jsonb_agg(jsonb_build_object('name', conname, 'def', pg_get_constraintdef(oid)) ORDER BY conname) INTO v_after
    FROM pg_constraint WHERE conrelid = v_rel AND conname IN ('card_evidence_link_ck_1', 'card_evidence_link_ck_2', 'card_evidence_link_natural_key');
    IF v_after IS DISTINCT FROM v_cons THEN RAISE EXCEPTION '검증 실패: CHECK·자연키'; END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object('name', c.relname, 'def', pg_get_indexdef(i.indexrelid)) ORDER BY c.relname), '[]'::jsonb) INTO v_after
    FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
    WHERE i.indrelid = v_rel AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid AND k.conrelid = v_rel);
    IF v_after IS DISTINCT FROM v_idx THEN RAISE EXCEPTION '검증 실패: 인덱스'; END IF;
    SELECT count(*), md5(string_agg(md5(row(card_id, ev_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key,
                                            ev_item_cd, ev_item_key, evidence_id)::text), ',' ORDER BY card_id, ev_link_id))
      INTO v_count2, v_print2 FROM db_pipeline.card_evidence_link;
    SELECT string_agg(ev_subject_cd || '=' || n, ', ' ORDER BY ev_subject_cd) INTO v_subjects2
    FROM (SELECT ev_subject_cd, count(*) n FROM db_pipeline.card_evidence_link GROUP BY 1) g;
    IF v_count2 <> v_count OR v_print2 IS DISTINCT FROM v_print OR v_subjects2 IS DISTINCT FROM v_subjects THEN
        RAISE EXCEPTION '검증 실패: 연결 데이터가 다릅니다.';
    END IF;
    FOREACH v_name IN ARRAY c_views LOOP
        EXECUTE format('SELECT md5(coalesce(string_agg(t::text, E''\n'' ORDER BY t::text), '''')) FROM db_pipeline.%I t', v_name) INTO v_out;
        SELECT jsonb_build_object('def', pg_get_viewdef(v.oid), 'owner', pg_get_userbyid(v.relowner), 'acl', v.relacl::text,
                                  'comment', obj_description(v.oid, 'pg_class'), 'result', v_out) INTO v_after
        FROM pg_class v WHERE v.oid = ('db_pipeline.' || v_name)::regclass;
        IF v_after IS DISTINCT FROM v_views->v_name THEN RAISE EXCEPTION '검증 실패: 뷰 %', v_name; END IF;
    END LOOP;

    RAISE NOTICE '근거 연결 되돌리기 완료. 연결 %건(%), 지문 %', v_count, v_subjects, v_print;
END
$link_back$;

ANALYZE db_pipeline.card_evidence_link;

COMMIT;
