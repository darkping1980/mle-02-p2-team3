-- =====================================================================
-- 기존 모델(recipe_src) → 목표 모델(recipe) 데이터 이관
--
-- 실행: 직접 실행하지 않는다. tools/recipe_rebuild.py 가 recipe_target_schema.sql 직후 같은 트랜잭션에서
--       ``recipe_src.`` 를 원본 스키마, ``recipe.`` 를 대상 스키마로 치환해 실행하고,
--       recipe_target_validation.sql 이 모두 통과할 때만 COMMIT한다.
-- 원칙:
--   - 원본 스키마는 SELECT만 한다(UPDATE/DELETE/DDL 없음).
--   - 업무 ID를 새로 발급하지 않는다. 모든 ID 컬럼을 명시적으로 복사하므로 DEFAULT(시퀀스)가 호출되지 않는다.
--   - 생성·수정 일시/사용자, 검토 상태·메모·승인 이력을 값 그대로 복사한다.
--   - 제거 컬럼(ingr_cat_id, rcp.rcp_cat_id 등)은 부모 행에서 결정되는 중복 정보이며,
--     검증 SQL이 원본에서 부모 값과 일치함을 확인한다(정보 손실 0 확인).
--
-- 컬럼 매핑(원본 → 대상):
--   rcp_raw, rcp_cat, common_code_grp, common_cd : 전 컬럼 1:1
--   rcp          : rcp_cat_id 제외 전 컬럼 1:1
--   rcp_cat_rel  : 원본 rcp (rcp_id, rcp_cat_id). 관리 컬럼은 레시피 최초 등록 값(create_*)을
--                  생성·수정 값 모두에 사용한다(관계는 레시피 등록 시점에 생겨 이후 바뀐 적 없음)
--   rcp_step     : rcp_cat_id 제외 1:1
--   ingr         : ingr_cat_id 제외 1:1
--   ingr_als     : ingr_cat_id 제외 1:1 (ingr_als_id 유지)
--   rcp_ingr_stg : ingr_cat_id 제외 1:1
--   rcp_ingr     : ingr_cat_id, rcp_cat_id 제외 1:1
--   ingr_cat     : 이관하지 않음(백업 파일과 보존 스키마에만 남음)
-- =====================================================================

INSERT INTO recipe.common_code_grp (
    common_code_grp_id, common_code_grp_nm,
    create_date, create_user_id, update_date, update_user_id
)
SELECT
    common_code_grp_id, common_code_grp_nm,
    create_date, create_user_id, update_date, update_user_id
FROM recipe_src.common_code_grp;

INSERT INTO recipe.common_cd (
    common_code_grp_id, common_cd, common_cd_nm,
    create_date, create_user_id, update_date, update_user_id
)
SELECT
    common_code_grp_id, common_cd, common_cd_nm,
    create_date, create_user_id, update_date, update_user_id
FROM recipe_src.common_cd;

INSERT INTO recipe.rcp_cat (
    rcp_cat_id, rcp_cat_nm,
    create_date, create_user_id, update_date, update_user_id
)
SELECT
    rcp_cat_id, rcp_cat_nm,
    create_date, create_user_id, update_date, update_user_id
FROM recipe_src.rcp_cat;

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
    create_date, create_user_id, update_date, update_user_id
)
SELECT
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
    create_date, create_user_id, update_date, update_user_id
FROM recipe_src.rcp_raw;

INSERT INTO recipe.rcp (
    rcp_id, rcp_seq, rcp_raw_id, rcp_nm, cook_mthd_cd,
    rcp_serving_weight_value, rcp_energy_kcal, rcp_carbs_g, rcp_protein_g, rcp_fat_g, rcp_sodium_mg,
    rcp_nutrition_status, rcp_nutrition_review_note,
    rcp_hash_tag, rcp_image_url, rcp_image_large_url, rcp_sodium_reduction_tip_txt,
    create_date, create_user_id, update_date, update_user_id
)
SELECT
    rcp_id, rcp_seq, rcp_raw_id, rcp_nm, cook_mthd_cd,
    rcp_serving_weight_value, rcp_energy_kcal, rcp_carbs_g, rcp_protein_g, rcp_fat_g, rcp_sodium_mg,
    rcp_nutrition_status, rcp_nutrition_review_note,
    rcp_hash_tag, rcp_image_url, rcp_image_large_url, rcp_sodium_reduction_tip_txt,
    create_date, create_user_id, update_date, update_user_id
FROM recipe_src.rcp;

-- 기존 단일 분류(rcp.rcp_cat_id)를 관계 행으로 옮긴다. 원본에 없는 분류는 만들지 않는다.
INSERT INTO recipe.rcp_cat_rel (
    rcp_id, rcp_cat_id,
    create_date, create_user_id, update_date, update_user_id
)
SELECT
    rcp_id, rcp_cat_id,
    create_date, create_user_id, create_date, create_user_id
FROM recipe_src.rcp;

INSERT INTO recipe.rcp_step (
    rcp_id, step_no, rcp_step_instruction_txt, rcp_step_image_url,
    create_date, create_user_id, update_date, update_user_id
)
SELECT
    rcp_id, step_no, rcp_step_instruction_txt, rcp_step_image_url,
    create_date, create_user_id, update_date, update_user_id
FROM recipe_src.rcp_step;

INSERT INTO recipe.ingr (
    ingr_id, ingr_nm,
    create_date, create_user_id, update_date, update_user_id
)
SELECT
    ingr_id, ingr_nm,
    create_date, create_user_id, update_date, update_user_id
FROM recipe_src.ingr;

INSERT INTO recipe.ingr_als (
    ingr_id, ingr_als_id, ingr_als_nm,
    create_date, create_user_id, update_date, update_user_id
)
SELECT
    ingr_id, ingr_als_id, ingr_als_nm,
    create_date, create_user_id, update_date, update_user_id
FROM recipe_src.ingr_als;

INSERT INTO recipe.rcp_ingr_stg (
    rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id, rcp_ingr_line_no, ingr_id,
    rcp_ingr_raw_txt, rcp_ingr_parsed_nm, rcp_ingr_qty, rcp_ingr_unit_nm, rcp_ingr_section_txt,
    rcp_ingr_status, rcp_ingr_review_note, rcp_ingr_parser_version,
    rcp_ingr_approved_date, rcp_ingr_approved_user_id,
    create_date, create_user_id, update_date, update_user_id
)
SELECT
    rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id, rcp_ingr_line_no, ingr_id,
    rcp_ingr_raw_txt, rcp_ingr_parsed_nm, rcp_ingr_qty, rcp_ingr_unit_nm, rcp_ingr_section_txt,
    rcp_ingr_status, rcp_ingr_review_note, rcp_ingr_parser_version,
    rcp_ingr_approved_date, rcp_ingr_approved_user_id,
    create_date, create_user_id, update_date, update_user_id
FROM recipe_src.rcp_ingr_stg;

INSERT INTO recipe.rcp_ingr (
    rcp_id, ingr_id, rcp_raw_id,
    create_date, create_user_id, update_date, update_user_id
)
SELECT
    rcp_id, ingr_id, rcp_raw_id,
    create_date, create_user_id, update_date, update_user_id
FROM recipe_src.rcp_ingr;

-- ---------------------------------------------------------------------
-- 시퀀스: 원본의 발급 위치와 이관된 ID 일련번호 최댓값 중 큰 값으로 맞춰 이후 발급 ID 충돌을 막는다.
-- (seq_ingr_cat은 대상에 없음. CYCLE 999,999 도달 전까지 같은 날짜 접두어 충돌이 생기지 않는다.)
-- ---------------------------------------------------------------------
SELECT setval('recipe.seq_rcp_cat', greatest(
    (SELECT last_value FROM recipe_src.seq_rcp_cat),
    (SELECT coalesce(max(right(rcp_cat_id, 6)::int), 0) FROM recipe.rcp_cat WHERE rcp_cat_id ~ '^[0-9]{8}_[0-9]{6}$'),
    1), true);
SELECT setval('recipe.seq_rcp', greatest(
    (SELECT last_value FROM recipe_src.seq_rcp),
    (SELECT coalesce(max(right(rcp_id, 6)::int), 0) FROM recipe.rcp WHERE rcp_id ~ '^[0-9]{8}_[0-9]{6}$'),
    1), true);
SELECT setval('recipe.seq_ingr', greatest(
    (SELECT last_value FROM recipe_src.seq_ingr),
    (SELECT coalesce(max(right(ingr_id, 6)::int), 0) FROM recipe.ingr WHERE ingr_id ~ '^[0-9]{8}_[0-9]{6}$'),
    1), true);
SELECT setval('recipe.seq_ingr_als', greatest(
    (SELECT last_value FROM recipe_src.seq_ingr_als),
    (SELECT coalesce(max(right(ingr_als_id, 6)::int), 0) FROM recipe.ingr_als WHERE ingr_als_id ~ '^[0-9]{8}_[0-9]{6}$'),
    1), true);
SELECT setval('recipe.seq_import_batch', greatest(
    (SELECT last_value FROM recipe_src.seq_import_batch),
    (SELECT coalesce(max(right(rcp_raw_id, 6)::int), 0) FROM recipe.rcp_raw WHERE rcp_raw_id ~ '^[0-9]{8}_[0-9]{6}$'),
    1), true);
SELECT setval('recipe.seq_rcp_ingr_stg', greatest(
    (SELECT last_value FROM recipe_src.seq_rcp_ingr_stg),
    (SELECT coalesce(max(right(rcp_ingr_stg_id, 6)::int), 0) FROM recipe.rcp_ingr_stg WHERE rcp_ingr_stg_id ~ '^[0-9]{8}_[0-9]{6}$'),
    1), true);
