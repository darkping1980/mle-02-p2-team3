-- =====================================================================================================
-- [승인 전 실행 금지] CARD_EVIDENCE_LINK 원문 근거 PK 전체 승계, EV_LINK_ID → EVIDENCE_LINK_ID
-- 검토서: CARD_EVIDENCE_LINK_PK_INHERITANCE_REVIEW_20261103.md
-- 사전 검증: _precheck.sql / 사후 검증: _postcheck.sql / 되돌리기: _rollback.sql
--
-- 변경 전 컬럼: card_id, ev_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, ev_item_cd, ev_item_key, evidence_id
--            PK (card_id, ev_link_id)
-- 변경 후 컬럼: card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id,
--            card_bnft_id, ev_subject_cd, rule_key, relation_key, ev_item_cd, ev_item_key
--            PK (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id)
--            UNIQUE card_evidence_link_id_key (card_id, evidence_link_id)
-- 유지: card_evidence_link_natural_key, card_evidence_link_ck_1, card_evidence_link_ck_2, 인덱스 2개, 기본값,
--       evidence_link_id 값과 생성 함수 인자('card_evidence_link'), 주석, 소유자, 권한, 의존 뷰 2개.
-- 상위키 3개는 card_source_evidence에서 evidence_id(UNIQUE)로 조회해 채운다. 물리 FK는 만들지 않는다.
--
-- 처리 (한 트랜잭션, 실패하면 전체 ROLLBACK)
--   1. 근거 연결·원문 근거·두 뷰를 잠근다(lock_timeout 5초). 원문 근거는 SHARE로 잠가 복사 중 변경을 막는다.
--   2. 상태 판정: 이미 변경 후면 아무것도 하지 않고, 변경 전 구성이 아니면 중단한다.
--   3. 두 뷰 외 종속 객체, 트리거·정책·규칙·발행, 고아 연결, (card_id, ev_link_id) 중복, 원문 근거 UNIQUE 부재면 중단한다.
--   4. 행 지문·유형별 건수·뷰 결과를 기록한다.
--   5. ev_link_id 이름 변경 → 뷰 정의 읽기 → 뷰 삭제(역순, CASCADE 없음) → 기존 테이블 이름 변경 → 새 테이블 생성
--      → 원문 근거와 JOIN해 복사 → 제약·인덱스 → 기존 테이블 삭제(CASCADE 없음) → 주석·소유자·권한 → 뷰 재생성.
--   6. 컬럼 순서·정의, 제약, 인덱스, 테이블 속성, 행 지문, 유형별 건수, 상위키 일치, 뷰 정의·결과를 비교한다.
-- =====================================================================================================

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';
SET LOCAL search_path = pg_catalog;

LOCK TABLE db_pipeline.card_evidence_link, db_pipeline.v_card_integrity_issue, db_pipeline.v_common_cd_usage IN ACCESS EXCLUSIVE MODE;
LOCK TABLE db_pipeline.card_source_evidence IN SHARE MODE;

DO $link$
DECLARE
    c_from  CONSTANT text[] := ARRAY['card_id', 'ev_link_id', 'ev_subject_cd', 'card_bnft_id', 'rule_key', 'relation_key',
                                     'ev_item_cd', 'ev_item_key', 'evidence_id'];
    c_to    CONSTANT text[] := ARRAY['card_doc_id', 'page_no', 'card_doc_chunk_id', 'evidence_id', 'card_id', 'evidence_link_id',
                                     'card_bnft_id', 'ev_subject_cd', 'rule_key', 'relation_key', 'ev_item_cd', 'ev_item_key'];
    c_views CONSTANT text[] := ARRAY['v_common_cd_usage', 'v_card_integrity_issue'];      -- 생성 순서. 삭제는 역순
    c_new_pk     CONSTANT text := 'PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id)';
    c_new_unique CONSTANT text := 'UNIQUE (card_id, evidence_link_id)';
    v_rel      regclass := 'db_pipeline.card_evidence_link'::regclass;
    v_current  text[];
    v_problem  text;
    v_cons     jsonb;     -- 유지할 제약 (CHECK 2개, 자연키)
    v_idx      jsonb;     -- 제약이 아닌 인덱스
    v_comments jsonb;     -- 컬럼 주석 (이름 변경 후 기준)
    v_tab      jsonb;
    v_views    jsonb;
    v_count    bigint; v_print text; v_subjects text;
    v_count2   bigint; v_print2 text; v_subjects2 text;
    v_name     text; v_item record; v_after jsonb; v_out text;
BEGIN
    -- 1. 상태 판정
    SELECT array_agg(attname::text ORDER BY attnum) INTO v_current
    FROM pg_attribute WHERE attrelid = v_rel AND attnum > 0 AND NOT attisdropped;
    IF v_current = c_to THEN
        RAISE NOTICE '이미 변경된 구조입니다. 아무것도 바꾸지 않습니다.';
        RETURN;
    END IF;
    IF v_current IS DISTINCT FROM c_from THEN
        RAISE EXCEPTION '예상과 다른 컬럼 구성이라 중단합니다: %', array_to_string(v_current, ', ');
    END IF;
    IF (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = v_rel AND contype = 'p') IS DISTINCT FROM 'PRIMARY KEY (card_id, ev_link_id)' THEN
        RAISE EXCEPTION '예상과 다른 PK라 중단합니다.';
    END IF;

    -- 2. 차단 조건
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
        FROM pg_depend d
        WHERE d.refclassid = 'pg_type'::regclass AND d.refobjid = (SELECT reltype FROM pg_class WHERE oid = v_rel) AND d.deptype <> 'i'
        UNION ALL
        SELECT '뷰 의존 객체: ' || pg_describe_object(d.classid, d.objid, d.objsubid)
        FROM pg_class v JOIN pg_depend d ON d.refclassid = 'pg_class'::regclass AND d.refobjid = v.oid
        WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views) AND d.classid <> 'pg_type'::regclass
          AND NOT (d.classid = 'pg_rewrite'::regclass AND d.objid IN (
                SELECT r.oid FROM pg_rewrite r JOIN pg_class w ON w.oid = r.ev_class
                WHERE w.relnamespace = 'db_pipeline'::regnamespace AND w.relname = ANY (c_views)))
        UNION ALL
        SELECT '뷰 행 타입 의존 객체: ' || pg_describe_object(d.classid, d.objid, d.objsubid)
        FROM pg_class v JOIN pg_depend d ON d.refclassid = 'pg_type'::regclass AND d.refobjid = v.reltype
        WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views) AND d.deptype <> 'i'
        UNION ALL
        SELECT '트리거·정책·규칙·발행·상속·확장 통계 ' || (
            (SELECT count(*) FROM pg_trigger WHERE tgrelid = v_rel AND NOT tgisinternal) + (SELECT count(*) FROM pg_policy WHERE polrelid = v_rel)
          + (SELECT count(*) FROM pg_rewrite WHERE ev_class = v_rel) + (SELECT count(*) FROM pg_publication_rel WHERE prrelid = v_rel)
          + (SELECT count(*) FROM pg_inherits WHERE inhrelid = v_rel OR inhparent = v_rel) + (SELECT count(*) FROM pg_statistic_ext WHERE stxrelid = v_rel))
        WHERE (SELECT count(*) FROM pg_trigger WHERE tgrelid = v_rel AND NOT tgisinternal) + (SELECT count(*) FROM pg_policy WHERE polrelid = v_rel)
            + (SELECT count(*) FROM pg_rewrite WHERE ev_class = v_rel) + (SELECT count(*) FROM pg_publication_rel WHERE prrelid = v_rel)
            + (SELECT count(*) FROM pg_inherits WHERE inhrelid = v_rel OR inhparent = v_rel) + (SELECT count(*) FROM pg_statistic_ext WHERE stxrelid = v_rel) > 0
        UNION ALL
        SELECT '컬럼 권한·식별·생성 ' || count(*) FROM pg_attribute
        WHERE attrelid = v_rel AND attnum > 0 AND NOT attisdropped AND (attacl IS NOT NULL OR attidentity <> '' OR attgenerated <> '') HAVING count(*) > 0
        UNION ALL
        SELECT '예상 밖 제약 ' || string_agg(conname, ',') FROM pg_constraint
        WHERE conrelid = v_rel AND conname NOT IN ('card_evidence_link_pkey', 'card_evidence_link_natural_key', 'card_evidence_link_ck_1', 'card_evidence_link_ck_2')
        HAVING count(*) > 0
        UNION ALL
        SELECT '원문 근거 UNIQUE(evidence_id) 없음' WHERE NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conrelid = 'db_pipeline.card_source_evidence'::regclass AND contype IN ('u', 'p')
              AND pg_get_constraintdef(oid) = 'UNIQUE (evidence_id)')
        UNION ALL
        SELECT '원문 근거 없는 연결 ' || count(*) FROM db_pipeline.card_evidence_link l
        WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_source_evidence e WHERE e.evidence_id = l.evidence_id) HAVING count(*) > 0
        UNION ALL
        SELECT '(card_id, ev_link_id) 중복 ' || count(*) FROM (SELECT 1 FROM db_pipeline.card_evidence_link
                                                              GROUP BY card_id, ev_link_id HAVING count(*) > 1) x HAVING count(*) > 0
        UNION ALL
        SELECT '뷰 옵션·컬럼 주석·컬럼 권한' FROM pg_class v
        WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views)
          AND (v.reloptions IS NOT NULL OR EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = v.oid AND a.attnum > 0
                AND (a.attacl IS NOT NULL OR col_description(v.oid, a.attnum) IS NOT NULL)))
        UNION ALL
        SELECT '임시 이름 사용 중' WHERE to_regclass('db_pipeline.card_evidence_link__pkinherit_old') IS NOT NULL
           OR to_regclass('db_pipeline.card_evidence_link_id_key') IS NOT NULL
    ) problems;
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION '차단 조건이 있어 중단합니다: %', v_problem;
    END IF;

    -- 3. 변경 전 기록
    SELECT count(*), md5(string_agg(md5(row(card_id, ev_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key,
                                            ev_item_cd, ev_item_key, evidence_id)::text), ',' ORDER BY card_id, ev_link_id))
      INTO v_count, v_print
    FROM db_pipeline.card_evidence_link;
    SELECT string_agg(ev_subject_cd || '=' || n, ', ' ORDER BY ev_subject_cd) INTO v_subjects
    FROM (SELECT ev_subject_cd, count(*) n FROM db_pipeline.card_evidence_link GROUP BY 1) g;

    SELECT jsonb_agg(jsonb_build_object('name', conname, 'def', pg_get_constraintdef(oid)) ORDER BY conname) INTO v_cons
    FROM pg_constraint WHERE conrelid = v_rel AND conname IN ('card_evidence_link_ck_1', 'card_evidence_link_ck_2', 'card_evidence_link_natural_key');
    SELECT coalesce(jsonb_agg(jsonb_build_object('name', c.relname, 'def', pg_get_indexdef(i.indexrelid)) ORDER BY c.relname), '[]'::jsonb) INTO v_idx
    FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
    WHERE i.indrelid = v_rel AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid AND k.conrelid = v_rel);
    SELECT jsonb_build_object('owner', pg_get_userbyid(relowner), 'acl', relacl::text, 'rls', relrowsecurity,
                              'force_rls', relforcerowsecurity, 'replident', relreplident, 'reloptions', reloptions,
                              'comment', obj_description(oid, 'pg_class')) INTO v_tab
    FROM pg_class WHERE oid = v_rel;
    IF v_tab->>'replident' <> 'd' OR v_tab->'reloptions' <> 'null'::jsonb THEN
        RAISE EXCEPTION 'REPLICA IDENTITY 또는 테이블 옵션이 기본값이 아니라 중단합니다.';
    END IF;

    -- 4. 컬럼 이름 변경. 뷰 정의는 컬럼 번호로 저장되므로 새 이름을 따라간다. 뷰의 출력 컬럼 이름은 바뀌지 않는다.
    ALTER TABLE db_pipeline.card_evidence_link RENAME COLUMN ev_link_id TO evidence_link_id;
    SELECT jsonb_object_agg(attname, col_description(attrelid, attnum)) INTO v_comments
    FROM pg_attribute WHERE attrelid = v_rel AND attnum > 0 AND NOT attisdropped;
    v_comments := v_comments || jsonb_build_object('card_doc_id', '문서 아이디', 'page_no', '페이지 번호', 'card_doc_chunk_id', '청크 아이디');

    SELECT jsonb_object_agg(v.relname, jsonb_build_object('def', pg_get_viewdef(v.oid), 'owner', pg_get_userbyid(v.relowner),
                                                          'acl', v.relacl::text, 'comment', obj_description(v.oid, 'pg_class')))
      INTO v_views
    FROM pg_class v WHERE v.relnamespace = 'db_pipeline'::regnamespace AND v.relname = ANY (c_views);
    FOREACH v_name IN ARRAY c_views LOOP
        EXECUTE format('SELECT md5(coalesce(string_agg(t::text, E''\n'' ORDER BY t::text), '''')) FROM db_pipeline.%I t', v_name) INTO v_out;
        v_views := jsonb_set(v_views, ARRAY[v_name, 'result'], to_jsonb(v_out));
    END LOOP;

    -- 5. 교체
    DROP VIEW db_pipeline.v_card_integrity_issue;                                         -- CASCADE 없음
    DROP VIEW db_pipeline.v_common_cd_usage;
    ALTER TABLE db_pipeline.card_evidence_link RENAME TO card_evidence_link__pkinherit_old;
    ALTER TABLE db_pipeline.card_evidence_link__pkinherit_old RENAME CONSTRAINT card_evidence_link_pkey TO card_evidence_link_pkey__old;
    ALTER TABLE db_pipeline.card_evidence_link__pkinherit_old RENAME CONSTRAINT card_evidence_link_natural_key TO card_evidence_link_natural_key__old;
    FOR v_item IN SELECT value AS c FROM jsonb_array_elements(v_idx) LOOP
        EXECUTE format('ALTER INDEX db_pipeline.%I RENAME TO %I', v_item.c->>'name', (v_item.c->>'name') || '__old');
    END LOOP;

    CREATE TABLE db_pipeline.card_evidence_link (
        card_doc_id       varchar(20) NOT NULL,
        page_no           smallint NOT NULL,
        card_doc_chunk_id varchar(20) NOT NULL,
        evidence_id       varchar(20) NOT NULL,
        card_id           bigint NOT NULL,
        evidence_link_id  varchar(20) DEFAULT db_pipeline.fn_get_biz_id('card_evidence_link') NOT NULL,
        card_bnft_id      varchar(20),
        ev_subject_cd     varchar(10) NOT NULL,
        rule_key          varchar(40),
        relation_key      varchar(40),
        ev_item_cd        varchar(10) DEFAULT 'SELF' NOT NULL,
        ev_item_key       varchar(100) DEFAULT '-' NOT NULL
    );

    INSERT INTO db_pipeline.card_evidence_link (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id,
                                                card_bnft_id, ev_subject_cd, rule_key, relation_key, ev_item_cd, ev_item_key)
    SELECT e.card_doc_id, e.page_no, e.card_doc_chunk_id, l.evidence_id, l.card_id, l.evidence_link_id,
           l.card_bnft_id, l.ev_subject_cd, l.rule_key, l.relation_key, l.ev_item_cd, l.ev_item_key
    FROM db_pipeline.card_evidence_link__pkinherit_old l
    JOIN db_pipeline.card_source_evidence e ON e.evidence_id = l.evidence_id;

    FOR v_item IN SELECT value AS c FROM jsonb_array_elements(v_cons) WHERE value->>'name' LIKE '%\_ck\_%' LOOP
        EXECUTE format('ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT %I %s', v_item.c->>'name', v_item.c->>'def');
    END LOOP;
    ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_pkey
        PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id);
    ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_id_key UNIQUE (card_id, evidence_link_id);
    EXECUTE format('ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_natural_key %s',
                   (SELECT value->>'def' FROM jsonb_array_elements(v_cons) WHERE value->>'name' = 'card_evidence_link_natural_key'));
    FOR v_item IN SELECT value AS c FROM jsonb_array_elements(v_idx) LOOP
        EXECUTE v_item.c->>'def';
    END LOOP;

    DROP TABLE db_pipeline.card_evidence_link__pkinherit_old;                             -- CASCADE 없음

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
    IF (v_tab->>'force_rls')::boolean THEN ALTER TABLE db_pipeline.card_evidence_link FORCE ROW LEVEL SECURITY; END IF;
    COMMENT ON SEQUENCE db_pipeline.seq_card_evidence_link IS 'card_evidence_link.evidence_link_id 로컬 업무 ID 발급';

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

    -- 6. 검증: 하나라도 다르면 오류로 전체 ROLLBACK
    v_rel := 'db_pipeline.card_evidence_link'::regclass;
    SELECT array_agg(attname::text ORDER BY attnum) INTO v_current FROM pg_attribute WHERE attrelid = v_rel AND attnum > 0 AND NOT attisdropped;
    IF v_current IS DISTINCT FROM c_to THEN RAISE EXCEPTION '검증 실패: 컬럼 순서 %', v_current; END IF;
    IF (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = v_rel AND contype = 'p') IS DISTINCT FROM c_new_pk
       OR (SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = v_rel AND conname = 'card_evidence_link_id_key') IS DISTINCT FROM c_new_unique THEN
        RAISE EXCEPTION '검증 실패: PK 또는 UNIQUE(card_id, evidence_link_id)';
    END IF;
    SELECT jsonb_agg(jsonb_build_object('name', conname, 'def', pg_get_constraintdef(oid)) ORDER BY conname) INTO v_after
    FROM pg_constraint WHERE conrelid = v_rel AND conname IN ('card_evidence_link_ck_1', 'card_evidence_link_ck_2', 'card_evidence_link_natural_key');
    IF v_after IS DISTINCT FROM v_cons THEN RAISE EXCEPTION '검증 실패: CHECK·자연키 정의가 다릅니다. 전 % / 후 %', v_cons, v_after; END IF;
    IF (SELECT count(*) FROM pg_constraint WHERE conrelid = v_rel) <> 5 THEN RAISE EXCEPTION '검증 실패: 제약 수'; END IF;
    SELECT coalesce(jsonb_agg(jsonb_build_object('name', c.relname, 'def', pg_get_indexdef(i.indexrelid)) ORDER BY c.relname), '[]'::jsonb) INTO v_after
    FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
    WHERE i.indrelid = v_rel AND NOT EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid AND k.conrelid = v_rel);
    IF v_after IS DISTINCT FROM v_idx THEN RAISE EXCEPTION '검증 실패: 인덱스가 다릅니다. 전 % / 후 %', v_idx, v_after; END IF;
    IF (SELECT pg_get_expr(adbin, adrelid) FROM pg_attrdef WHERE adrelid = v_rel
        AND adnum = (SELECT attnum FROM pg_attribute WHERE attrelid = v_rel AND attname = 'evidence_link_id'))
       IS DISTINCT FROM 'db_pipeline.fn_get_biz_id(''card_evidence_link''::text)' THEN
        RAISE EXCEPTION '검증 실패: evidence_link_id 기본값';
    END IF;
    SELECT jsonb_build_object('owner', pg_get_userbyid(relowner), 'acl', relacl::text, 'rls', relrowsecurity,
                              'force_rls', relforcerowsecurity, 'replident', relreplident, 'reloptions', reloptions,
                              'comment', obj_description(oid, 'pg_class')) INTO v_after FROM pg_class WHERE oid = v_rel;
    IF v_after IS DISTINCT FROM v_tab THEN RAISE EXCEPTION '검증 실패: 테이블 속성이 다릅니다. 전 % / 후 %', v_tab, v_after; END IF;
    IF EXISTS (SELECT 1 FROM unnest(c_to) x WHERE col_description(v_rel, (SELECT attnum FROM pg_attribute WHERE attrelid = v_rel AND attname = x))
               IS DISTINCT FROM v_comments->>x) THEN
        RAISE EXCEPTION '검증 실패: 컬럼 주석';
    END IF;

    SELECT count(*), md5(string_agg(md5(row(card_id, evidence_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key,
                                            ev_item_cd, ev_item_key, evidence_id)::text), ',' ORDER BY card_id, evidence_link_id))
      INTO v_count2, v_print2 FROM db_pipeline.card_evidence_link;
    SELECT string_agg(ev_subject_cd || '=' || n, ', ' ORDER BY ev_subject_cd) INTO v_subjects2
    FROM (SELECT ev_subject_cd, count(*) n FROM db_pipeline.card_evidence_link GROUP BY 1) g;
    IF v_count2 <> v_count OR v_print2 IS DISTINCT FROM v_print OR v_subjects2 IS DISTINCT FROM v_subjects THEN
        RAISE EXCEPTION '검증 실패: 연결 데이터가 다릅니다. 건수 % → %, 유형 % → %', v_count, v_count2, v_subjects, v_subjects2;
    END IF;
    IF (SELECT count(*) FROM db_pipeline.card_evidence_link l JOIN db_pipeline.card_source_evidence e
          ON (e.card_doc_id, e.page_no, e.card_doc_chunk_id, e.evidence_id) = (l.card_doc_id, l.page_no, l.card_doc_chunk_id, l.evidence_id)) <> v_count THEN
        RAISE EXCEPTION '검증 실패: 승계한 상위키가 원문 근거와 다른 행이 있습니다.';
    END IF;

    FOREACH v_name IN ARRAY c_views LOOP
        EXECUTE format('SELECT md5(coalesce(string_agg(t::text, E''\n'' ORDER BY t::text), '''')) FROM db_pipeline.%I t', v_name) INTO v_out;
        SELECT jsonb_build_object('def', pg_get_viewdef(v.oid), 'owner', pg_get_userbyid(v.relowner), 'acl', v.relacl::text,
                                  'comment', obj_description(v.oid, 'pg_class'), 'result', v_out) INTO v_after
        FROM pg_class v WHERE v.oid = ('db_pipeline.' || v_name)::regclass;
        IF v_after IS DISTINCT FROM v_views->v_name THEN RAISE EXCEPTION '검증 실패: 뷰 %의 정의·속성·결과가 다릅니다.', v_name; END IF;
    END LOOP;

    RAISE NOTICE '근거 연결 PK 승계 완료. 연결 %건(%), 지문 %. PK 6컬럼, UNIQUE(card_id, evidence_link_id), 제약 5개, 인덱스 %개, 뷰 %개 복원',
        v_count, v_subjects, v_print, jsonb_array_length(v_idx), array_length(c_views, 1);
END
$link$;

ANALYZE db_pipeline.card_evidence_link;

COMMIT;
