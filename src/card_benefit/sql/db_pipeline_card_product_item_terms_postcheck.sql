-- =====================================================================================================
-- card_product_item TERMS 도입: 사후 검증(읽기 전용, ROLLBACK으로 끝남)
-- 생성: 2026-11-05, 운영 DB 정의를 읽어 생성(gen_terms_ddl.py). 변경 내용은 다음 세 가지뿐이다.
--   1) card_product_item_type_ck(고정 허용값 CHECK) 삭제
--   2) fn_valid_item_data: BENEFIT·ANNUAL_FEE 분기 원문 유지, TERMS_V1 분기 추가, 그 밖의 유형은 JSON 객체만 요구
--   3) v_card_integrity_issue: evidence_subject_orphan에 ITEM 근거의 항목 존재 분기만 추가
-- 다른 제약(subtype_ck, nonbnft_ck, cond/rule/rel/data_ck, PK, UNIQUE)과 업무 뷰는 바꾸지 않는다.
-- =====================================================================================================

-- C* 항목이 모두 true여야 한다. I01·I02는 _precheck와 같아야 하고(기존 행 불변),
-- I03은 evidence_subject_orphan만 ITEM 근거 오탐 수만큼 줄어야 한다(그 밖의 게이트 동일).
BEGIN TRANSACTION READ ONLY;

WITH checks(check_id, check_nm, expected, actual) AS (
    SELECT 'C01', '고정 허용값 CHECK 없음', '0',
        (SELECT count(*)::text FROM pg_constraint WHERE conname = 'card_product_item_type_ck')
    UNION ALL SELECT 'C02', 'fn_valid_item_data에 TERMS_V1 분기', 'true',
        (position('TERMS_V1' in pg_get_functiondef('db_pipeline.fn_valid_item_data(text,jsonb)'::regprocedure)) > 0)::text
    UNION ALL SELECT 'C03', 'evidence_subject_orphan의 ITEM 분기', 'true',
        (position('WHEN ''ITEM''::text THEN (EXISTS' in pg_get_viewdef('db_pipeline.v_card_integrity_issue'::regclass)) > 0)::text
    UNION ALL SELECT 'C04', '항목 유형 NOT NULL 유지', 'true',
        (SELECT attnotnull::text FROM pg_attribute WHERE attrelid = 'db_pipeline.card_product_item'::regclass AND attname = 'item_type_cd')
    UNION ALL SELECT 'C05', '유지 제약 이름', 'card_product_item_cd_key,card_product_item_cond_ck,card_product_item_data_ck,card_product_item_date_ck,card_product_item_nonbnft_ck,card_product_item_origin_ck,card_product_item_pkey,card_product_item_ref_key,card_product_item_rel_ck,card_product_item_rule_ck,card_product_item_scope_ck,card_product_item_subtype_ck',
        (SELECT string_agg(conname, ',' ORDER BY conname) FROM pg_constraint
         WHERE conrelid = 'db_pipeline.card_product_item'::regclass AND conname <> 'card_product_item_type_ck')
    UNION ALL SELECT 'C06', '기존 행 전부 fn_valid_item_data 통과', '0',
        (SELECT count(*)::text FROM db_pipeline.card_product_item WHERE NOT db_pipeline.fn_valid_item_data(item_type_cd::text, item_data))
)
SELECT check_id, check_nm, expected = actual AS ok, expected, actual FROM checks ORDER BY check_id;

SELECT 'I01' AS info_id, 'card_product_item 행 수·지문' AS info_nm,
       count(*)::text || ' / ' || md5(string_agg(md5(t::text), ',' ORDER BY md5(t::text) COLLATE "C")) AS value
FROM db_pipeline.card_product_item t
UNION ALL SELECT 'I02', 'card_evidence_link 행 수·지문',
       count(*)::text || ' / ' || md5(string_agg(md5(t::text), ',' ORDER BY md5(t::text) COLLATE "C")) FROM db_pipeline.card_evidence_link t
UNION ALL SELECT 'I03', '정합성 게이트(gate=건수)',
       coalesce(string_agg(gate_cd || '=' || n, ',' ORDER BY gate_cd), '-')
FROM (SELECT gate_cd, count(*) n FROM db_pipeline.v_card_integrity_issue GROUP BY gate_cd) g
UNION ALL SELECT 'I04', '항목 유형별 행 수', string_agg(item_type_cd || '=' || n, ',' ORDER BY item_type_cd)
FROM (SELECT item_type_cd, count(*) n FROM db_pipeline.card_product_item GROUP BY item_type_cd) x;

ROLLBACK;
