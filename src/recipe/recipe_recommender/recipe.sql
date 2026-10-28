--=========================================================
-- recipe SQL mapper
--   파일 이름(recipe)이 namespace이며, Python에서는 "recipe.쿼리이름"으로 호출한다.
--   쿼리 이름 끝의 느낌표(!)는 영향 행 수(rowcount)를 돌려주는 변경 SQL,
--   접미사가 없으면 결과 행을 돌려주는 SQL이다.
--   콜론으로 시작하는 대문자 이름은 named parameter이며 psycopg 바인딩 변수로 전달된다.
--   모든 객체는 recipe 스키마를 명시한다(search_path에 의존하지 않음).
--   물리 FK가 없으므로 부모 존재 여부는 Service의 사전 검증과 정합성 SQL로 확인한다.
--   업무 ID DEFAULT(recipe.fn_get_biz_id)는 INSERT 시 시퀀스를 소비하므로
--   Service가 기존 키를 먼저 조회해 새 행만 INSERT한다(ON CONFLICT는 안전장치).
--   psycopg pyformat 규칙상 SQL 본문에 퍼센트 기호를 직접 쓰지 않는다.
--
--   식별자 구분:
--     rcp_raw_id  : 원본 수집 회차 ID (seq_import_batch, 회차당 1회 발급)
--     rcp_raw_seq : 회차 내 CSV 원본 행 순번 (Python에서 000001부터 생성)
--     rcp_seq     : 식약처 원본 레시피 번호 (RCP_SEQ, 일반 속성)
--     rcp_id      : 정제 레시피 내부 ID (seq_rcp, rcp 단독 PK)
--     rcp_cat_id  : 요리 분류 ID. 레시피와 N:M(rcp_cat_rel)
--     ingr_id     : 표준 식재료 ID (ingr 단독 PK, 식재료 분류 없음)
--   다른 스키마(격리 리허설 등)에서 실행할 때는 database.create_recipe_sql_session(schema=...)이
--   ``recipe.`` 한정자만 바꾼 사본을 등록한다(sql_schema.render_schema_sql).
--=========================================================

-- name: find_schema_model
-- 연결 대상 스키마가 목표 모델(rcp_cat_rel 있음, ingr_cat 없음)인지 확인한다. 쓰기 전 가드.
SELECT
    to_regclass('recipe.rcp_cat_rel') IS NOT NULL AS has_rcp_cat_rel,
    to_regclass('recipe.ingr_cat') IS NOT NULL AS has_ingr_cat;

--=========================================================
-- 원본 수집 회차
--=========================================================

-- name: find_next_rcp_raw_id
-- 원본 수집 회차 ID를 한 번 발급한다. rollback되어도 소비된 번호는 돌아오지 않는다.
SELECT recipe.fn_get_biz_id('import_batch') AS rcp_raw_id;

-- name: find_latest_raw_batch
-- 가장 최근에 생성된 원본 수집 회차와 그 회차의 원본 행 수.
SELECT
    rcp_raw_id,
    count(*) AS raw_count,
    max(create_date) AS last_create_date
FROM recipe.rcp_raw
GROUP BY rcp_raw_id
ORDER BY max(create_date) DESC, rcp_raw_id DESC
LIMIT 1;

-- name: list_raw_rows_by_batch
-- 지정 회차의 원본 행 순번과 55개 원본 컬럼(동일 원본 재실행 판정용).
SELECT
    rcp_raw_seq,
    rcp_seq, rcp_nm, rcp_way2, rcp_pat2,
    info_wgt, info_eng, info_car, info_pro, info_fat, info_na,
    hash_tag, att_file_no_main, att_file_no_mk, rcp_parts_dtls,
    manual01, manual_img01, manual02, manual_img02, manual03, manual_img03,
    manual04, manual_img04, manual05, manual_img05, manual06, manual_img06,
    manual07, manual_img07, manual08, manual_img08, manual09, manual_img09,
    manual10, manual_img10, manual11, manual_img11, manual12, manual_img12,
    manual13, manual_img13, manual14, manual_img14, manual15, manual_img15,
    manual16, manual_img16, manual17, manual_img17, manual18, manual_img18,
    manual19, manual_img19, manual20, manual_img20,
    rcp_na_tip
FROM recipe.rcp_raw
WHERE rcp_raw_id = :RCP_RAW_ID;

--=========================================================
-- 참조 마스터: 요리 종류 / 공통코드
--=========================================================

-- name: find_recipe_category
-- 요리 종류명(RCP_PAT2 원본값)으로 요리 종류 ID를 조회한다.
SELECT
    rcp_cat_id,
    rcp_cat_nm
FROM recipe.rcp_cat
WHERE rcp_cat_nm = :RCP_CAT_NM;

-- name: list_recipe_categories
-- 등록된 요리 종류 전체(이름 → ID 매핑표).
SELECT
    rcp_cat_id,
    rcp_cat_nm
FROM recipe.rcp_cat
ORDER BY rcp_cat_nm;

-- name: insert_recipe_category!
-- 요리 종류를 등록한다. rcp_cat_id는 DEFAULT(fn_get_biz_id('rcp_cat'))로 발급된다.
INSERT INTO recipe.rcp_cat (rcp_cat_nm, create_user_id, update_user_id)
VALUES (:RCP_CAT_NM, :USER_ID, :USER_ID)
ON CONFLICT ON CONSTRAINT uq_rcp_cat_rcp_cat_nm DO NOTHING;

-- name: upsert_common_code_group!
-- 공통코드 그룹을 등록하고, 이름이 바뀐 경우에만 갱신한다.
INSERT INTO recipe.common_code_grp (common_code_grp_id, common_code_grp_nm, create_user_id, update_user_id)
VALUES (:COMMON_CODE_GRP_ID, :COMMON_CODE_GRP_NM, :USER_ID, :USER_ID)
ON CONFLICT ON CONSTRAINT pk_common_code_grp DO UPDATE SET
    common_code_grp_nm = EXCLUDED.common_code_grp_nm,
    update_date = now(),
    update_user_id = EXCLUDED.update_user_id
WHERE recipe.common_code_grp.common_code_grp_nm IS DISTINCT FROM EXCLUDED.common_code_grp_nm;

-- name: upsert_common_code!
-- 공통코드 상세를 등록하고, 코드명이 바뀐 경우에만 갱신한다.
INSERT INTO recipe.common_cd (common_code_grp_id, common_cd, common_cd_nm, create_user_id, update_user_id)
VALUES (:COMMON_CODE_GRP_ID, :COMMON_CD, :COMMON_CD_NM, :USER_ID, :USER_ID)
ON CONFLICT ON CONSTRAINT pk_common_cd DO UPDATE SET
    common_cd_nm = EXCLUDED.common_cd_nm,
    update_date = now(),
    update_user_id = EXCLUDED.update_user_id
WHERE recipe.common_cd.common_cd_nm IS DISTINCT FROM EXCLUDED.common_cd_nm;

-- name: list_common_codes
-- 지정 그룹의 공통코드 목록. 그룹 마스터와 JOIN해 그룹 존재까지 확인한다.
SELECT
    c.common_cd,
    c.common_cd_nm
FROM recipe.common_cd AS c
JOIN recipe.common_code_grp AS g
  ON g.common_code_grp_id = c.common_code_grp_id
WHERE c.common_code_grp_id = :COMMON_CODE_GRP_ID
ORDER BY c.common_cd;

--=========================================================
-- 기존 키 조회
--=========================================================

-- name: list_recipe_keys
-- 등록된 레시피의 PK, 원본 번호, 최종 반영 회차.
SELECT
    rcp_id,
    rcp_seq,
    rcp_raw_id
FROM recipe.rcp;

-- name: list_recipe_category_relations
-- 등록된 레시피·요리 분류 관계(원본 분류 변경 검출용, 삭제하지 않음).
SELECT
    rcp_id,
    rcp_cat_id
FROM recipe.rcp_cat_rel;

-- name: list_recipe_step_keys
-- 등록된 조리 단계 키(원본에서 사라진 단계 검출용, 삭제하지 않음).
SELECT
    rcp_id,
    step_no
FROM recipe.rcp_step;

-- name: list_staging_keys_by_batch
-- 지정 회차에 이미 등록된 staging 행의 (원본 행 순번, 재료 등장 순번).
SELECT
    rcp_raw_seq,
    rcp_ingr_line_no
FROM recipe.rcp_ingr_stg
WHERE rcp_raw_id = :RCP_RAW_ID;

--=========================================================
-- 원본 등록
--=========================================================

-- name: insert_recipe_raw!
-- CSV 한 행의 55개 원본 컬럼을 그대로 저장한다. 같은 회차·같은 행 순번이 있으면 건너뛴다.
INSERT INTO recipe.rcp_raw (
    rcp_raw_id, rcp_raw_seq, rcp_seq, rcp_nm, rcp_way2, rcp_pat2,
    info_wgt, info_eng, info_car, info_pro, info_fat, info_na,
    hash_tag, att_file_no_main, att_file_no_mk, rcp_parts_dtls,
    manual01, manual_img01, manual02, manual_img02, manual03, manual_img03,
    manual04, manual_img04, manual05, manual_img05, manual06, manual_img06,
    manual07, manual_img07, manual08, manual_img08, manual09, manual_img09,
    manual10, manual_img10, manual11, manual_img11, manual12, manual_img12,
    manual13, manual_img13, manual14, manual_img14, manual15, manual_img15,
    manual16, manual_img16, manual17, manual_img17, manual18, manual_img18,
    manual19, manual_img19, manual20, manual_img20,
    rcp_na_tip,
    create_user_id, update_user_id
)
VALUES (
    :RCP_RAW_ID, :RCP_RAW_SEQ, :RCP_SEQ, :RCP_NM, :RCP_WAY2, :RCP_PAT2,
    :INFO_WGT, :INFO_ENG, :INFO_CAR, :INFO_PRO, :INFO_FAT, :INFO_NA,
    :HASH_TAG, :ATT_FILE_NO_MAIN, :ATT_FILE_NO_MK, :RCP_PARTS_DTLS,
    :MANUAL01, :MANUAL_IMG01, :MANUAL02, :MANUAL_IMG02, :MANUAL03, :MANUAL_IMG03,
    :MANUAL04, :MANUAL_IMG04, :MANUAL05, :MANUAL_IMG05, :MANUAL06, :MANUAL_IMG06,
    :MANUAL07, :MANUAL_IMG07, :MANUAL08, :MANUAL_IMG08, :MANUAL09, :MANUAL_IMG09,
    :MANUAL10, :MANUAL_IMG10, :MANUAL11, :MANUAL_IMG11, :MANUAL12, :MANUAL_IMG12,
    :MANUAL13, :MANUAL_IMG13, :MANUAL14, :MANUAL_IMG14, :MANUAL15, :MANUAL_IMG15,
    :MANUAL16, :MANUAL_IMG16, :MANUAL17, :MANUAL_IMG17, :MANUAL18, :MANUAL_IMG18,
    :MANUAL19, :MANUAL_IMG19, :MANUAL20, :MANUAL_IMG20,
    :RCP_NA_TIP,
    :USER_ID, :USER_ID
)
ON CONFLICT ON CONSTRAINT pk_rcp_raw DO NOTHING;

--=========================================================
-- 레시피 / 조리 단계 등록
--=========================================================

-- name: insert_recipe!
-- 새 정제 레시피를 등록한다. rcp_id는 DEFAULT(fn_get_biz_id('rcp'))로 발급된다.
-- Service는 아직 rcp_seq가 등록되지 않은 레시피만 이 SQL로 보낸다.
INSERT INTO recipe.rcp (
    rcp_seq, rcp_raw_id, rcp_nm, cook_mthd_cd,
    rcp_serving_weight_value, rcp_energy_kcal, rcp_carbs_g, rcp_protein_g, rcp_fat_g, rcp_sodium_mg,
    rcp_nutrition_status, rcp_nutrition_review_note,
    rcp_hash_tag, rcp_image_url, rcp_image_large_url, rcp_sodium_reduction_tip_txt,
    create_user_id, update_user_id
)
VALUES (
    :RCP_SEQ, :RCP_RAW_ID, :RCP_NM, :COOK_MTHD_CD,
    :RCP_SERVING_WEIGHT_VALUE, :RCP_ENERGY_KCAL, :RCP_CARBS_G, :RCP_PROTEIN_G, :RCP_FAT_G, :RCP_SODIUM_MG,
    :RCP_NUTRITION_STATUS, :RCP_NUTRITION_REVIEW_NOTE,
    :RCP_HASH_TAG, :RCP_IMAGE_URL, :RCP_IMAGE_LARGE_URL, :RCP_SODIUM_REDUCTION_TIP_TXT,
    :USER_ID, :USER_ID
)
ON CONFLICT ON CONSTRAINT uq_rcp_rcp_seq DO NOTHING;

-- name: update_recipe!
-- 이미 등록된 레시피를 PK(rcp_id)로 찾아 값이 달라졌을 때만 갱신한다. PK는 바꾸지 않는다.
UPDATE recipe.rcp
SET
    rcp_raw_id = :RCP_RAW_ID,
    rcp_nm = :RCP_NM,
    cook_mthd_cd = :COOK_MTHD_CD,
    rcp_serving_weight_value = :RCP_SERVING_WEIGHT_VALUE,
    rcp_energy_kcal = :RCP_ENERGY_KCAL,
    rcp_carbs_g = :RCP_CARBS_G,
    rcp_protein_g = :RCP_PROTEIN_G,
    rcp_fat_g = :RCP_FAT_G,
    rcp_sodium_mg = :RCP_SODIUM_MG,
    rcp_nutrition_status = :RCP_NUTRITION_STATUS,
    rcp_nutrition_review_note = :RCP_NUTRITION_REVIEW_NOTE,
    rcp_hash_tag = :RCP_HASH_TAG,
    rcp_image_url = :RCP_IMAGE_URL,
    rcp_image_large_url = :RCP_IMAGE_LARGE_URL,
    rcp_sodium_reduction_tip_txt = :RCP_SODIUM_REDUCTION_TIP_TXT,
    update_date = now(),
    update_user_id = :USER_ID
WHERE rcp_id = :RCP_ID
  AND rcp_seq = :RCP_SEQ
  AND (
      rcp_raw_id, rcp_nm, cook_mthd_cd,
      rcp_serving_weight_value, rcp_energy_kcal, rcp_carbs_g, rcp_protein_g, rcp_fat_g, rcp_sodium_mg,
      rcp_nutrition_status, rcp_nutrition_review_note,
      rcp_hash_tag, rcp_image_url, rcp_image_large_url, rcp_sodium_reduction_tip_txt
  ) IS DISTINCT FROM (
      :RCP_RAW_ID, :RCP_NM, :COOK_MTHD_CD,
      :RCP_SERVING_WEIGHT_VALUE, :RCP_ENERGY_KCAL, :RCP_CARBS_G, :RCP_PROTEIN_G, :RCP_FAT_G, :RCP_SODIUM_MG,
      :RCP_NUTRITION_STATUS, :RCP_NUTRITION_REVIEW_NOTE,
      :RCP_HASH_TAG, :RCP_IMAGE_URL, :RCP_IMAGE_LARGE_URL, :RCP_SODIUM_REDUCTION_TIP_TXT
  );

-- name: insert_recipe_category_relation!
-- 레시피·요리 분류 관계를 등록한다. 이미 있으면 그대로 둔다(기존 관계를 지우거나 바꾸지 않는다).
INSERT INTO recipe.rcp_cat_rel (rcp_id, rcp_cat_id, create_user_id, update_user_id)
VALUES (:RCP_ID, :RCP_CAT_ID, :USER_ID, :USER_ID)
ON CONFLICT ON CONSTRAINT pk_rcp_cat_rel DO NOTHING;

-- name: upsert_recipe_step!
-- 조리 단계를 원본 번호 그대로 등록한다. 같은 키가 있으면 내용이 달라졌을 때만 갱신한다.
INSERT INTO recipe.rcp_step (
    rcp_id, step_no,
    rcp_step_instruction_txt, rcp_step_image_url,
    create_user_id, update_user_id
)
VALUES (
    :RCP_ID, :STEP_NO,
    :RCP_STEP_INSTRUCTION_TXT, :RCP_STEP_IMAGE_URL,
    :USER_ID, :USER_ID
)
ON CONFLICT ON CONSTRAINT pk_rcp_step DO UPDATE SET
    rcp_step_instruction_txt = EXCLUDED.rcp_step_instruction_txt,
    rcp_step_image_url = EXCLUDED.rcp_step_image_url,
    update_date = now(),
    update_user_id = EXCLUDED.update_user_id
WHERE (recipe.rcp_step.rcp_step_instruction_txt, recipe.rcp_step.rcp_step_image_url)
    IS DISTINCT FROM (EXCLUDED.rcp_step_instruction_txt, EXCLUDED.rcp_step_image_url);

--=========================================================
-- 식재료 마스터 (검증된 표준명·별칭 사전, 식재료 분류 없음)
--=========================================================

-- name: list_ingredients
SELECT
    ingr_id,
    ingr_nm
FROM recipe.ingr;

-- name: insert_ingredient!
-- 표준 식재료를 등록한다. ingr_id는 DEFAULT(fn_get_biz_id('ingr')).
INSERT INTO recipe.ingr (ingr_nm, create_user_id, update_user_id)
VALUES (:INGR_NM, :USER_ID, :USER_ID)
ON CONFLICT ON CONSTRAINT uq_ingr_ingr_nm DO NOTHING;

-- name: list_ingredient_alias_keys
SELECT
    ingr_id,
    ingr_als_id,
    ingr_als_nm
FROM recipe.ingr_als;

-- name: insert_ingredient_alias!
-- 식재료 별칭을 등록한다. ingr_als_id는 DEFAULT(fn_get_biz_id('ingr_als')).
INSERT INTO recipe.ingr_als (ingr_id, ingr_als_nm, create_user_id, update_user_id)
VALUES (:INGR_ID, :INGR_ALS_NM, :USER_ID, :USER_ID)
ON CONFLICT ON CONSTRAINT uq_ingr_als_ingr_als_nm DO NOTHING;

--=========================================================
-- 재료 staging / 최종 관계
--=========================================================

-- name: insert_recipe_ingredient_staging!
-- 원문 재료 한 항목의 파싱 결과를 저장한다. rcp_ingr_stg_id는 DEFAULT(fn_get_biz_id('rcp_ingr_stg')).
-- Service는 같은 (회차, 원본 행, 등장 순번)이 없는 행만 보낸다. 검토·승인 내용을 덮어쓰지 않는다.
INSERT INTO recipe.rcp_ingr_stg (
    rcp_raw_id, rcp_raw_seq, rcp_ingr_line_no,
    rcp_ingr_raw_txt, rcp_ingr_parsed_nm, rcp_ingr_qty, rcp_ingr_unit_nm, rcp_ingr_section_txt,
    rcp_ingr_status, rcp_ingr_review_note, rcp_ingr_parser_version,
    create_user_id, update_user_id
)
VALUES (
    :RCP_RAW_ID, :RCP_RAW_SEQ, :RCP_INGR_LINE_NO,
    :RCP_INGR_RAW_TXT, :RCP_INGR_PARSED_NM, :RCP_INGR_QTY, :RCP_INGR_UNIT_NM, :RCP_INGR_SECTION_TXT,
    'PENDING_REVIEW', :RCP_INGR_REVIEW_NOTE, :RCP_INGR_PARSER_VERSION,
    :USER_ID, :USER_ID
)
ON CONFLICT ON CONSTRAINT uq_rcp_ingr_stg_line_no DO NOTHING;

-- name: update_staging_verified_matches!
-- 이름 분리가 신뢰 가능한(parse=OK/PARTIAL) 검토 대기 행 중, 후보명이 표준 식재료명 또는
-- 별칭과 정확히 같고 그 대상이 하나뿐인 경우에만 자동 승인한다. 유사 이름은 합치지 않는다.
UPDATE recipe.rcp_ingr_stg AS s
SET
    ingr_id = m.ingr_id,
    rcp_ingr_status = 'AUTO_APPROVED',
    rcp_ingr_review_note = concat_ws('; ', s.rcp_ingr_review_note, 'auto-approved: exact ' || m.match_type || ' match'),
    rcp_ingr_approved_date = now(),
    rcp_ingr_approved_user_id = :USER_ID,
    update_date = now(),
    update_user_id = :USER_ID
FROM (
    SELECT
        nm,
        min(ingr_id) AS ingr_id,
        min(match_type) AS match_type
    FROM (
        SELECT ingr_nm AS nm, ingr_id, 'name' AS match_type FROM recipe.ingr
        UNION
        SELECT ingr_als_nm AS nm, ingr_id, 'alias' AS match_type FROM recipe.ingr_als
    ) AS verified_name
    GROUP BY nm
    HAVING count(DISTINCT ingr_id) = 1
) AS m
WHERE s.rcp_raw_id = :RCP_RAW_ID
  AND s.rcp_ingr_status = 'PENDING_REVIEW'
  AND s.ingr_id IS NULL
  AND (starts_with(s.rcp_ingr_review_note, 'parse=OK') OR starts_with(s.rcp_ingr_review_note, 'parse=PARTIAL'))
  AND s.rcp_ingr_parsed_nm = m.nm;

-- name: insert_recipe_ingredient_relations!
-- 선택 회차의 승인된 staging 행만 최종 N:M 관계로 만든다.
-- staging → rcp_raw(부모 원본 행) → rcp(rcp_seq, 같은 회차)로 rcp_id를 찾고,
-- ingr PK로 존재를 확인한 뒤 DISTINCT로 같은 레시피-식재료 관계를 한 건으로 합친다.
-- (한 레시피 원문에 같은 식재료가 여러 번 나오면 승인 staging 행 수 > 관계 수가 된다.)
INSERT INTO recipe.rcp_ingr (
    rcp_id, ingr_id, rcp_raw_id,
    create_user_id, update_user_id
)
SELECT DISTINCT
    r.rcp_id,
    i.ingr_id,
    r.rcp_raw_id,
    :USER_ID,
    :USER_ID
FROM recipe.rcp_ingr_stg AS s
JOIN recipe.rcp_raw AS raw
  ON raw.rcp_raw_id = s.rcp_raw_id
 AND raw.rcp_raw_seq = s.rcp_raw_seq
JOIN recipe.rcp AS r
  ON r.rcp_seq = raw.rcp_seq
 AND r.rcp_raw_id = raw.rcp_raw_id
JOIN recipe.ingr AS i
  ON i.ingr_id = s.ingr_id
WHERE s.rcp_raw_id = :RCP_RAW_ID
  AND s.rcp_ingr_status IN ('AUTO_APPROVED', 'MANUAL_APPROVED')
ON CONFLICT ON CONSTRAINT pk_rcp_ingr DO UPDATE SET
    rcp_raw_id = EXCLUDED.rcp_raw_id,
    update_date = now(),
    update_user_id = EXCLUDED.update_user_id
WHERE recipe.rcp_ingr.rcp_raw_id IS DISTINCT FROM EXCLUDED.rcp_raw_id;

--=========================================================
-- 적재 결과 집계 / 정합성 검사 (읽기 전용)
--=========================================================

-- name: count_recipe_tables
-- recipe 스키마 11개 테이블의 전체 행 수.
SELECT
    (SELECT count(*) FROM recipe.rcp_raw) AS rcp_raw,
    (SELECT count(*) FROM recipe.rcp_cat) AS rcp_cat,
    (SELECT count(*) FROM recipe.rcp_cat_rel) AS rcp_cat_rel,
    (SELECT count(*) FROM recipe.common_code_grp) AS common_code_grp,
    (SELECT count(*) FROM recipe.common_cd) AS common_cd,
    (SELECT count(*) FROM recipe.rcp) AS rcp,
    (SELECT count(*) FROM recipe.rcp_step) AS rcp_step,
    (SELECT count(*) FROM recipe.ingr) AS ingr,
    (SELECT count(*) FROM recipe.ingr_als) AS ingr_als,
    (SELECT count(*) FROM recipe.rcp_ingr_stg) AS rcp_ingr_stg,
    (SELECT count(*) FROM recipe.rcp_ingr) AS rcp_ingr;

-- name: count_batch_rows
-- 지정 회차 기준 행 수와 staging 상태별 건수.
SELECT
    (SELECT count(*) FROM recipe.rcp_raw WHERE rcp_raw_id = :RCP_RAW_ID) AS raw_count,
    (SELECT count(*) FROM recipe.rcp WHERE rcp_raw_id = :RCP_RAW_ID) AS recipe_count,
    (SELECT count(*)
       FROM recipe.rcp_step AS st
       JOIN recipe.rcp AS r ON r.rcp_id = st.rcp_id
      WHERE r.rcp_raw_id = :RCP_RAW_ID) AS step_count,
    (SELECT count(*)
       FROM recipe.rcp_cat_rel AS rel
       JOIN recipe.rcp AS r ON r.rcp_id = rel.rcp_id
      WHERE r.rcp_raw_id = :RCP_RAW_ID) AS category_relation_count,
    (SELECT count(*) FROM recipe.rcp_ingr_stg WHERE rcp_raw_id = :RCP_RAW_ID) AS staging_count,
    (SELECT count(*) FROM recipe.rcp_ingr_stg
      WHERE rcp_raw_id = :RCP_RAW_ID AND rcp_ingr_status = 'PENDING_REVIEW') AS staging_pending_count,
    (SELECT count(*) FROM recipe.rcp_ingr_stg
      WHERE rcp_raw_id = :RCP_RAW_ID AND rcp_ingr_status IN ('AUTO_APPROVED', 'MANUAL_APPROVED')) AS staging_approved_count,
    (SELECT count(*) FROM recipe.rcp_ingr WHERE rcp_raw_id = :RCP_RAW_ID) AS relation_count,
    (SELECT count(*) FROM recipe.rcp
      WHERE rcp_raw_id = :RCP_RAW_ID AND rcp_nutrition_status = 'REVIEW_REQUIRED') AS nutrition_review_count;

-- name: count_integrity_violations
-- 논리 참조·중복 검사 항목별 위반 건수. 모든 값이 0이어야 정상이다.
SELECT
    (SELECT count(*) FROM recipe.rcp AS r
      WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp_cat_rel AS rel WHERE rel.rcp_id = r.rcp_id)) AS rcp_without_category,
    (SELECT count(*) FROM recipe.rcp_cat_rel AS rel
      WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp AS r WHERE r.rcp_id = rel.rcp_id)) AS category_relation_without_recipe,
    (SELECT count(*) FROM recipe.rcp_cat_rel AS rel
      WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp_cat AS c WHERE c.rcp_cat_id = rel.rcp_cat_id)) AS category_relation_without_category,
    (SELECT count(*) FROM recipe.rcp AS r
       LEFT JOIN recipe.common_cd AS c ON c.common_code_grp_id = 'COOK_MTHD' AND c.common_cd = r.cook_mthd_cd
      WHERE c.common_cd IS NULL) AS rcp_without_cook_method,
    (SELECT count(*) FROM recipe.common_cd AS c
      WHERE c.common_code_grp_id = 'COOK_MTHD'
        AND c.common_cd !~ '^[0-9]{6}$') AS invalid_cook_method_code,
    (SELECT count(*) FROM recipe.common_cd AS c
       LEFT JOIN recipe.common_code_grp AS g ON g.common_code_grp_id = c.common_code_grp_id
      WHERE g.common_code_grp_id IS NULL) AS code_without_group,
    (SELECT count(*) FROM recipe.rcp AS r
       LEFT JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = r.rcp_raw_id AND raw.rcp_seq = r.rcp_seq
      WHERE raw.rcp_seq IS NULL) AS rcp_without_raw,
    (SELECT count(*) FROM (
        SELECT rcp_seq FROM recipe.rcp GROUP BY rcp_seq HAVING count(*) > 1
     ) AS d) AS duplicate_rcp_seq,
    (SELECT count(*) FROM recipe.rcp_step AS st
       LEFT JOIN recipe.rcp AS r ON r.rcp_id = st.rcp_id
      WHERE r.rcp_id IS NULL) AS step_without_recipe,
    (SELECT count(*) FROM recipe.rcp_ingr_stg AS s
       LEFT JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq
      WHERE raw.rcp_raw_seq IS NULL) AS staging_without_raw,
    (SELECT count(*) FROM (
        SELECT rcp_ingr_stg_id FROM recipe.rcp_ingr_stg GROUP BY rcp_ingr_stg_id HAVING count(*) > 1
     ) AS d) AS duplicate_staging_id,
    (SELECT count(*) FROM recipe.rcp_ingr_stg AS s
       LEFT JOIN recipe.ingr AS i ON i.ingr_id = s.ingr_id
      WHERE s.ingr_id IS NOT NULL AND i.ingr_id IS NULL) AS staging_without_ingredient,
    (SELECT count(*) FROM recipe.ingr_als AS a
       LEFT JOIN recipe.ingr AS i ON i.ingr_id = a.ingr_id
      WHERE i.ingr_id IS NULL) AS alias_without_ingredient,
    (SELECT count(*) FROM (
        SELECT nm FROM (
            SELECT ingr_nm AS nm, ingr_id FROM recipe.ingr
            UNION
            SELECT ingr_als_nm, ingr_id FROM recipe.ingr_als
        ) AS n GROUP BY nm HAVING count(DISTINCT ingr_id) > 1
     ) AS d) AS name_with_multiple_ingredients,
    (SELECT count(*) FROM recipe.rcp_ingr AS f
       LEFT JOIN recipe.rcp AS r ON r.rcp_id = f.rcp_id
       LEFT JOIN recipe.ingr AS i ON i.ingr_id = f.ingr_id
      WHERE r.rcp_id IS NULL OR i.ingr_id IS NULL) AS relation_without_parent,
    (SELECT count(*) FROM recipe.rcp_ingr AS f
       JOIN recipe.rcp AS r ON r.rcp_id = f.rcp_id
      WHERE NOT EXISTS (
          SELECT 1
          FROM recipe.rcp_ingr_stg AS s
          JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq
          WHERE s.rcp_raw_id = f.rcp_raw_id
            AND raw.rcp_seq = r.rcp_seq
            AND s.ingr_id = f.ingr_id
            AND s.rcp_ingr_status IN ('AUTO_APPROVED', 'MANUAL_APPROVED')
      )) AS relation_without_approved_staging;

--=========================================================
-- 레시피 조회 (RecipeSearchService)
--   읽기 전용. 목록 조회는 LIMIT/OFFSET 파라미터를 받는다(최대 크기는 Service가 제한).
--   선택 조건은 CAST(:X AS text) IS NULL 형태로 두어 값이 없으면 조건을 건너뛴다.
--=========================================================

-- name: find_recipe_detail
-- 원본 레시피 번호 또는 내부 레시피 ID로 레시피 한 건과 요리 분류·조리 방법·원본 정보를 조회한다.
-- 요리 분류는 rcp_cat_rel(N:M)이므로 분류명 목록을 이름순으로 합쳐 한 행으로 돌려준다.
SELECT
    r.rcp_id,
    r.rcp_seq,
    r.rcp_nm,
    cat.rcp_cat_nm,
    cat.rcp_cat_ids,
    r.cook_mthd_cd,
    cd.common_cd_nm AS cook_mthd_nm,
    r.rcp_serving_weight_value,
    r.rcp_energy_kcal,
    r.rcp_carbs_g,
    r.rcp_protein_g,
    r.rcp_fat_g,
    r.rcp_sodium_mg,
    r.rcp_nutrition_status,
    r.rcp_nutrition_review_note,
    r.rcp_hash_tag,
    r.rcp_image_url,
    r.rcp_sodium_reduction_tip_txt,
    r.rcp_raw_id,
    raw.rcp_raw_seq,
    raw.rcp_parts_dtls
FROM recipe.rcp AS r
LEFT JOIN LATERAL (
    SELECT
        string_agg(c.rcp_cat_nm, ', ' ORDER BY c.rcp_cat_nm) AS rcp_cat_nm,
        string_agg(c.rcp_cat_id, ', ' ORDER BY c.rcp_cat_nm) AS rcp_cat_ids
    FROM recipe.rcp_cat_rel AS rel
    JOIN recipe.rcp_cat AS c
      ON c.rcp_cat_id = rel.rcp_cat_id
    WHERE rel.rcp_id = r.rcp_id
) AS cat ON true
LEFT JOIN recipe.common_cd AS cd
  ON cd.common_code_grp_id = 'COOK_MTHD'
 AND cd.common_cd = r.cook_mthd_cd
LEFT JOIN recipe.rcp_raw AS raw
  ON raw.rcp_raw_id = r.rcp_raw_id
 AND raw.rcp_seq = r.rcp_seq
WHERE (CAST(:RCP_SEQ AS text) IS NULL OR r.rcp_seq = :RCP_SEQ)
  AND (CAST(:RCP_ID AS text) IS NULL OR r.rcp_id = :RCP_ID);

-- name: list_recipes
-- 레시피명(부분 일치, 대소문자 무시)·요리 분류명·조리 방법으로 레시피 목록을 조회한다.
-- 조리 방법 조건은 COOK_MTHD 코드(예: 000004) 또는 코드명(예: 찌기)을 받는다.
-- 분류 조건은 EXISTS로 걸어 여러 분류에 속한 레시피가 목록·건수에서 중복되지 않게 한다.
SELECT
    r.rcp_id,
    r.rcp_seq,
    r.rcp_nm,
    (SELECT string_agg(c.rcp_cat_nm, ', ' ORDER BY c.rcp_cat_nm)
       FROM recipe.rcp_cat_rel AS rel
       JOIN recipe.rcp_cat AS c ON c.rcp_cat_id = rel.rcp_cat_id
      WHERE rel.rcp_id = r.rcp_id) AS rcp_cat_nm,
    r.cook_mthd_cd,
    (SELECT cd.common_cd_nm
       FROM recipe.common_cd AS cd
      WHERE cd.common_code_grp_id = 'COOK_MTHD'
        AND cd.common_cd = r.cook_mthd_cd) AS cook_mthd_nm,
    r.rcp_energy_kcal,
    (SELECT count(*)
       FROM recipe.rcp_ingr AS f
      WHERE f.rcp_id = r.rcp_id) AS ingredient_count
FROM recipe.rcp AS r
WHERE (CAST(:RCP_NM AS text) IS NULL OR strpos(lower(r.rcp_nm), lower(:RCP_NM)) > 0)
  AND (CAST(:RCP_CAT_NM AS text) IS NULL OR EXISTS (
        SELECT 1
        FROM recipe.rcp_cat_rel AS rel
        JOIN recipe.rcp_cat AS c ON c.rcp_cat_id = rel.rcp_cat_id
        WHERE rel.rcp_id = r.rcp_id
          AND c.rcp_cat_nm = :RCP_CAT_NM))
  AND (CAST(:COOK_MTHD_CD AS text) IS NULL OR r.cook_mthd_cd = :COOK_MTHD_CD OR EXISTS (
        SELECT 1
        FROM recipe.common_cd AS cd
        WHERE cd.common_code_grp_id = 'COOK_MTHD'
          AND cd.common_cd = r.cook_mthd_cd
          AND cd.common_cd_nm = :COOK_MTHD_CD))
ORDER BY r.rcp_nm, length(r.rcp_seq), r.rcp_seq
LIMIT :LIMIT OFFSET :OFFSET;

-- name: count_recipes
-- list_recipes 와 같은 조건의 전체 건수.
SELECT count(*) AS total_count
FROM recipe.rcp AS r
WHERE (CAST(:RCP_NM AS text) IS NULL OR strpos(lower(r.rcp_nm), lower(:RCP_NM)) > 0)
  AND (CAST(:RCP_CAT_NM AS text) IS NULL OR EXISTS (
        SELECT 1
        FROM recipe.rcp_cat_rel AS rel
        JOIN recipe.rcp_cat AS c ON c.rcp_cat_id = rel.rcp_cat_id
        WHERE rel.rcp_id = r.rcp_id
          AND c.rcp_cat_nm = :RCP_CAT_NM))
  AND (CAST(:COOK_MTHD_CD AS text) IS NULL OR r.cook_mthd_cd = :COOK_MTHD_CD OR EXISTS (
        SELECT 1
        FROM recipe.common_cd AS cd
        WHERE cd.common_code_grp_id = 'COOK_MTHD'
          AND cd.common_cd = r.cook_mthd_cd
          AND cd.common_cd_nm = :COOK_MTHD_CD));

-- name: list_recipe_steps
-- 레시피 PK로 조리 단계를 원본 단계 번호 순서로 조회한다.
SELECT
    st.step_no,
    st.rcp_step_instruction_txt,
    st.rcp_step_image_url
FROM recipe.rcp_step AS st
WHERE st.rcp_id = :RCP_ID
ORDER BY st.step_no;

-- name: list_recipe_ingredients
-- 레시피별 사용 식재료(rcp_ingr)를 식재료·레시피 PK로 조인해 조회한다.
-- 같은 회차 staging의 원문 표기와 등장 횟수를 함께 보여 준다.
SELECT
    i.ingr_id,
    i.ingr_nm,
    (SELECT count(*)
       FROM recipe.rcp_ingr_stg AS s
       JOIN recipe.rcp_raw AS raw
         ON raw.rcp_raw_id = s.rcp_raw_id
        AND raw.rcp_raw_seq = s.rcp_raw_seq
      WHERE s.rcp_raw_id = f.rcp_raw_id
        AND raw.rcp_seq = r.rcp_seq
        AND s.ingr_id = f.ingr_id) AS occurrence_count,
    (SELECT string_agg(s.rcp_ingr_raw_txt, ' | ' ORDER BY s.rcp_ingr_line_no)
       FROM recipe.rcp_ingr_stg AS s
       JOIN recipe.rcp_raw AS raw
         ON raw.rcp_raw_id = s.rcp_raw_id
        AND raw.rcp_raw_seq = s.rcp_raw_seq
      WHERE s.rcp_raw_id = f.rcp_raw_id
        AND raw.rcp_seq = r.rcp_seq
        AND s.ingr_id = f.ingr_id) AS raw_texts
FROM recipe.rcp_ingr AS f
JOIN recipe.rcp AS r
  ON r.rcp_id = f.rcp_id
JOIN recipe.ingr AS i
  ON i.ingr_id = f.ingr_id
WHERE f.rcp_id = :RCP_ID
ORDER BY i.ingr_nm;

-- name: list_recipe_unmatched_stagings
-- 레시피의 재료 원문 중 표준 식재료에 연결되지 않은(검토 보류) staging 행.
SELECT
    s.rcp_ingr_line_no,
    s.rcp_ingr_raw_txt,
    s.rcp_ingr_parsed_nm,
    s.rcp_ingr_status,
    s.rcp_ingr_review_note
FROM recipe.rcp AS r
JOIN recipe.rcp_raw AS raw
  ON raw.rcp_raw_id = r.rcp_raw_id
 AND raw.rcp_seq = r.rcp_seq
JOIN recipe.rcp_ingr_stg AS s
  ON s.rcp_raw_id = raw.rcp_raw_id
 AND s.rcp_raw_seq = raw.rcp_raw_seq
WHERE r.rcp_id = :RCP_ID
  AND s.rcp_ingr_status NOT IN ('AUTO_APPROVED', 'MANUAL_APPROVED')
ORDER BY s.rcp_ingr_line_no;

-- name: find_ingredient_by_name
-- 표준 식재료명 또는 별칭과 정확히 일치하는 표준 식재료를 찾는다.
SELECT DISTINCT
    i.ingr_id,
    i.ingr_nm,
    CASE WHEN i.ingr_nm = :INGR_NM THEN 'name' ELSE 'alias' END AS matched_by
FROM recipe.ingr AS i
LEFT JOIN recipe.ingr_als AS a
  ON a.ingr_id = i.ingr_id
WHERE i.ingr_nm = :INGR_NM
   OR a.ingr_als_nm = :INGR_NM;

-- name: list_ingredient_aliases
-- 표준 식재료 PK로 별칭 목록을 조회한다.
SELECT
    a.ingr_als_id,
    a.ingr_als_nm
FROM recipe.ingr_als AS a
WHERE a.ingr_id = :INGR_ID
ORDER BY a.ingr_als_nm;

-- name: list_recipes_by_ingredient
-- 특정 표준 식재료를 사용하는 레시피 목록(rcp_ingr → rcp PK 조인).
SELECT
    r.rcp_id,
    r.rcp_seq,
    r.rcp_nm,
    (SELECT string_agg(c.rcp_cat_nm, ', ' ORDER BY c.rcp_cat_nm)
       FROM recipe.rcp_cat_rel AS rel
       JOIN recipe.rcp_cat AS c ON c.rcp_cat_id = rel.rcp_cat_id
      WHERE rel.rcp_id = r.rcp_id) AS rcp_cat_nm,
    r.cook_mthd_cd,
    (SELECT cd.common_cd_nm
       FROM recipe.common_cd AS cd
      WHERE cd.common_code_grp_id = 'COOK_MTHD'
        AND cd.common_cd = r.cook_mthd_cd) AS cook_mthd_nm
FROM recipe.rcp_ingr AS f
JOIN recipe.rcp AS r
  ON r.rcp_id = f.rcp_id
WHERE f.ingr_id = :INGR_ID
ORDER BY length(r.rcp_seq), r.rcp_seq
LIMIT :LIMIT OFFSET :OFFSET;

-- name: count_recipes_by_ingredient
-- 특정 표준 식재료를 사용하는 레시피 수.
SELECT count(*) AS total_count
FROM recipe.rcp_ingr AS f
WHERE f.ingr_id = :INGR_ID;
