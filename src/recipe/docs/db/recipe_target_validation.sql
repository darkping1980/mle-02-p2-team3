-- =====================================================================
-- 목표 모델 이관 검증 (읽기 전용 SELECT 하나)
--
-- ``recipe_src.`` = 이관 원본(기존 모델), ``recipe.`` = 대상(목표 모델).
-- tools/recipe_rebuild.py 가 스키마를 치환해 실행하고 (check_nm, actual)을 기대값과 비교한다.
-- 기대값은 이름 규칙으로 정한다: cnt_* 는 기준 건수(BASELINE), 그 밖의 모든 항목은 0.
--   diff_*  : 원본·대상 행 집합 차이(양방향 EXCEPT). 업무 ID·매핑·생성/수정/검토 이력 컬럼 전체 비교
--   lost_*  : 제거한 분류 컬럼이 부모 값과 달라 이관 시 정보가 사라지는 행
--   orphan_*/dup_*/conflict_* : 대상의 논리 참조·키 중복·별칭 충돌
--   seq_*   : 이후 자동 발급 ID가 기존 ID와 충돌할 수 있는 시퀀스
-- 자동 승인 staging과 최종 관계 수의 차이(gap_*)는 같은 레시피 안의 같은 식재료 반복 등장으로만
-- 설명되어야 한다: gap_unexplained = (승인 행 - 관계 행) - (승인 행 - 서로 다른 (레시피, 식재료) 쌍) = 0.
-- =====================================================================
WITH
src_approved AS (
    SELECT r.rcp_id, s.ingr_id
    FROM recipe_src.rcp_ingr_stg AS s
    JOIN recipe_src.rcp_raw AS raw ON raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq
    JOIN recipe_src.rcp AS r ON r.rcp_seq = raw.rcp_seq AND r.rcp_raw_id = raw.rcp_raw_id
    WHERE s.rcp_ingr_status IN ('AUTO_APPROVED', 'MANUAL_APPROVED')
),
tgt_approved AS (
    SELECT r.rcp_id, s.ingr_id
    FROM recipe.rcp_ingr_stg AS s
    JOIN recipe.rcp_raw AS raw ON raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq
    JOIN recipe.rcp AS r ON r.rcp_seq = raw.rcp_seq AND r.rcp_raw_id = raw.rcp_raw_id
    WHERE s.rcp_ingr_status IN ('AUTO_APPROVED', 'MANUAL_APPROVED')
),
id_seq AS (
    SELECT 'rcp_cat' AS seq_nm,
           (SELECT last_value FROM recipe.seq_rcp_cat) AS tgt_value,
           (SELECT last_value FROM recipe_src.seq_rcp_cat) AS src_value,
           (SELECT coalesce(max(right(rcp_cat_id, 6)::int), 0) FROM recipe.rcp_cat WHERE rcp_cat_id ~ '^[0-9]{8}_[0-9]{6}$') AS max_id
    UNION ALL
    SELECT 'rcp', (SELECT last_value FROM recipe.seq_rcp), (SELECT last_value FROM recipe_src.seq_rcp),
           (SELECT coalesce(max(right(rcp_id, 6)::int), 0) FROM recipe.rcp WHERE rcp_id ~ '^[0-9]{8}_[0-9]{6}$')
    UNION ALL
    SELECT 'ingr', (SELECT last_value FROM recipe.seq_ingr), (SELECT last_value FROM recipe_src.seq_ingr),
           (SELECT coalesce(max(right(ingr_id, 6)::int), 0) FROM recipe.ingr WHERE ingr_id ~ '^[0-9]{8}_[0-9]{6}$')
    UNION ALL
    SELECT 'ingr_als', (SELECT last_value FROM recipe.seq_ingr_als), (SELECT last_value FROM recipe_src.seq_ingr_als),
           (SELECT coalesce(max(right(ingr_als_id, 6)::int), 0) FROM recipe.ingr_als WHERE ingr_als_id ~ '^[0-9]{8}_[0-9]{6}$')
    UNION ALL
    SELECT 'import_batch', (SELECT last_value FROM recipe.seq_import_batch), (SELECT last_value FROM recipe_src.seq_import_batch),
           (SELECT coalesce(max(right(rcp_raw_id, 6)::int), 0) FROM recipe.rcp_raw WHERE rcp_raw_id ~ '^[0-9]{8}_[0-9]{6}$')
    UNION ALL
    SELECT 'rcp_ingr_stg', (SELECT last_value FROM recipe.seq_rcp_ingr_stg), (SELECT last_value FROM recipe_src.seq_rcp_ingr_stg),
           (SELECT coalesce(max(right(rcp_ingr_stg_id, 6)::int), 0) FROM recipe.rcp_ingr_stg WHERE rcp_ingr_stg_id ~ '^[0-9]{8}_[0-9]{6}$')
)
SELECT check_nm, actual::bigint AS actual
FROM (VALUES
    -- ----- 기준 건수(대상) -----
    ('cnt_rcp_raw', (SELECT count(*) FROM recipe.rcp_raw)),
    ('cnt_rcp_cat', (SELECT count(*) FROM recipe.rcp_cat)),
    ('cnt_common_code_grp', (SELECT count(*) FROM recipe.common_code_grp)),
    ('cnt_common_cd', (SELECT count(*) FROM recipe.common_cd)),
    ('cnt_rcp', (SELECT count(*) FROM recipe.rcp)),
    ('cnt_rcp_cat_rel', (SELECT count(*) FROM recipe.rcp_cat_rel)),
    ('cnt_rcp_step', (SELECT count(*) FROM recipe.rcp_step)),
    ('cnt_ingr', (SELECT count(*) FROM recipe.ingr)),
    ('cnt_ingr_als', (SELECT count(*) FROM recipe.ingr_als)),
    ('cnt_rcp_ingr_stg', (SELECT count(*) FROM recipe.rcp_ingr_stg)),
    ('cnt_stg_auto_approved', (SELECT count(*) FROM recipe.rcp_ingr_stg WHERE rcp_ingr_status = 'AUTO_APPROVED')),
    ('cnt_stg_manual_approved', (SELECT count(*) FROM recipe.rcp_ingr_stg WHERE rcp_ingr_status = 'MANUAL_APPROVED')),
    ('cnt_stg_pending', (SELECT count(*) FROM recipe.rcp_ingr_stg WHERE rcp_ingr_status = 'PENDING_REVIEW')),
    ('cnt_stg_rejected', (SELECT count(*) FROM recipe.rcp_ingr_stg WHERE rcp_ingr_status = 'REJECTED')),
    ('cnt_rcp_ingr', (SELECT count(*) FROM recipe.rcp_ingr)),
    ('cnt_approved_minus_relation', (SELECT count(*) FROM tgt_approved) - (SELECT count(*) FROM recipe.rcp_ingr)),

    -- ----- 원본 → 대상 / 대상 → 원본 행 차이: 같은 구조 테이블은 전체 컬럼 -----
    ('diff_rcp_raw_src_only', (SELECT count(*) FROM (SELECT * FROM recipe_src.rcp_raw EXCEPT ALL SELECT * FROM recipe.rcp_raw) AS d)),
    ('diff_rcp_raw_tgt_only', (SELECT count(*) FROM (SELECT * FROM recipe.rcp_raw EXCEPT ALL SELECT * FROM recipe_src.rcp_raw) AS d)),
    ('diff_rcp_cat_src_only', (SELECT count(*) FROM (SELECT * FROM recipe_src.rcp_cat EXCEPT ALL SELECT * FROM recipe.rcp_cat) AS d)),
    ('diff_rcp_cat_tgt_only', (SELECT count(*) FROM (SELECT * FROM recipe.rcp_cat EXCEPT ALL SELECT * FROM recipe_src.rcp_cat) AS d)),
    ('diff_common_code_grp_src_only', (SELECT count(*) FROM (SELECT * FROM recipe_src.common_code_grp EXCEPT ALL SELECT * FROM recipe.common_code_grp) AS d)),
    ('diff_common_code_grp_tgt_only', (SELECT count(*) FROM (SELECT * FROM recipe.common_code_grp EXCEPT ALL SELECT * FROM recipe_src.common_code_grp) AS d)),
    ('diff_common_cd_src_only', (SELECT count(*) FROM (SELECT * FROM recipe_src.common_cd EXCEPT ALL SELECT * FROM recipe.common_cd) AS d)),
    ('diff_common_cd_tgt_only', (SELECT count(*) FROM (SELECT * FROM recipe.common_cd EXCEPT ALL SELECT * FROM recipe_src.common_cd) AS d)),

    -- ----- 구조가 바뀐 테이블: 제거 컬럼을 뺀 전체 컬럼 -----
    ('diff_rcp_src_only', (SELECT count(*) FROM (
        SELECT rcp_id, rcp_seq, rcp_raw_id, rcp_nm, cook_mthd_cd, rcp_serving_weight_value, rcp_energy_kcal, rcp_carbs_g,
               rcp_protein_g, rcp_fat_g, rcp_sodium_mg, rcp_nutrition_status, rcp_nutrition_review_note, rcp_hash_tag,
               rcp_image_url, rcp_image_large_url, rcp_sodium_reduction_tip_txt, create_date, create_user_id, update_date, update_user_id
        FROM recipe_src.rcp
        EXCEPT ALL
        SELECT rcp_id, rcp_seq, rcp_raw_id, rcp_nm, cook_mthd_cd, rcp_serving_weight_value, rcp_energy_kcal, rcp_carbs_g,
               rcp_protein_g, rcp_fat_g, rcp_sodium_mg, rcp_nutrition_status, rcp_nutrition_review_note, rcp_hash_tag,
               rcp_image_url, rcp_image_large_url, rcp_sodium_reduction_tip_txt, create_date, create_user_id, update_date, update_user_id
        FROM recipe.rcp) AS d)),
    ('diff_rcp_tgt_only', (SELECT count(*) FROM (
        SELECT rcp_id, rcp_seq, rcp_raw_id, rcp_nm, cook_mthd_cd, rcp_serving_weight_value, rcp_energy_kcal, rcp_carbs_g,
               rcp_protein_g, rcp_fat_g, rcp_sodium_mg, rcp_nutrition_status, rcp_nutrition_review_note, rcp_hash_tag,
               rcp_image_url, rcp_image_large_url, rcp_sodium_reduction_tip_txt, create_date, create_user_id, update_date, update_user_id
        FROM recipe.rcp
        EXCEPT ALL
        SELECT rcp_id, rcp_seq, rcp_raw_id, rcp_nm, cook_mthd_cd, rcp_serving_weight_value, rcp_energy_kcal, rcp_carbs_g,
               rcp_protein_g, rcp_fat_g, rcp_sodium_mg, rcp_nutrition_status, rcp_nutrition_review_note, rcp_hash_tag,
               rcp_image_url, rcp_image_large_url, rcp_sodium_reduction_tip_txt, create_date, create_user_id, update_date, update_user_id
        FROM recipe_src.rcp) AS d)),
    ('diff_rcp_cat_rel_src_only', (SELECT count(*) FROM (
        SELECT rcp_id, rcp_cat_id, create_date, create_user_id FROM recipe_src.rcp
        EXCEPT ALL
        SELECT rcp_id, rcp_cat_id, create_date, create_user_id FROM recipe.rcp_cat_rel) AS d)),
    ('diff_rcp_cat_rel_tgt_only', (SELECT count(*) FROM (
        SELECT rcp_id, rcp_cat_id, create_date, create_user_id FROM recipe.rcp_cat_rel
        EXCEPT ALL
        SELECT rcp_id, rcp_cat_id, create_date, create_user_id FROM recipe_src.rcp) AS d)),
    ('diff_rcp_step_src_only', (SELECT count(*) FROM (
        SELECT rcp_id, step_no, rcp_step_instruction_txt, rcp_step_image_url, create_date, create_user_id, update_date, update_user_id
        FROM recipe_src.rcp_step
        EXCEPT ALL
        SELECT rcp_id, step_no, rcp_step_instruction_txt, rcp_step_image_url, create_date, create_user_id, update_date, update_user_id
        FROM recipe.rcp_step) AS d)),
    ('diff_rcp_step_tgt_only', (SELECT count(*) FROM (
        SELECT rcp_id, step_no, rcp_step_instruction_txt, rcp_step_image_url, create_date, create_user_id, update_date, update_user_id
        FROM recipe.rcp_step
        EXCEPT ALL
        SELECT rcp_id, step_no, rcp_step_instruction_txt, rcp_step_image_url, create_date, create_user_id, update_date, update_user_id
        FROM recipe_src.rcp_step) AS d)),
    ('diff_ingr_src_only', (SELECT count(*) FROM (
        SELECT ingr_id, ingr_nm, create_date, create_user_id, update_date, update_user_id FROM recipe_src.ingr
        EXCEPT ALL
        SELECT ingr_id, ingr_nm, create_date, create_user_id, update_date, update_user_id FROM recipe.ingr) AS d)),
    ('diff_ingr_tgt_only', (SELECT count(*) FROM (
        SELECT ingr_id, ingr_nm, create_date, create_user_id, update_date, update_user_id FROM recipe.ingr
        EXCEPT ALL
        SELECT ingr_id, ingr_nm, create_date, create_user_id, update_date, update_user_id FROM recipe_src.ingr) AS d)),
    ('diff_ingr_als_src_only', (SELECT count(*) FROM (
        SELECT ingr_id, ingr_als_id, ingr_als_nm, create_date, create_user_id, update_date, update_user_id FROM recipe_src.ingr_als
        EXCEPT ALL
        SELECT ingr_id, ingr_als_id, ingr_als_nm, create_date, create_user_id, update_date, update_user_id FROM recipe.ingr_als) AS d)),
    ('diff_ingr_als_tgt_only', (SELECT count(*) FROM (
        SELECT ingr_id, ingr_als_id, ingr_als_nm, create_date, create_user_id, update_date, update_user_id FROM recipe.ingr_als
        EXCEPT ALL
        SELECT ingr_id, ingr_als_id, ingr_als_nm, create_date, create_user_id, update_date, update_user_id FROM recipe_src.ingr_als) AS d)),
    ('diff_rcp_ingr_stg_src_only', (SELECT count(*) FROM (
        SELECT rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id, rcp_ingr_line_no, ingr_id, rcp_ingr_raw_txt, rcp_ingr_parsed_nm,
               rcp_ingr_qty, rcp_ingr_unit_nm, rcp_ingr_section_txt, rcp_ingr_status, rcp_ingr_review_note,
               rcp_ingr_parser_version, rcp_ingr_approved_date, rcp_ingr_approved_user_id,
               create_date, create_user_id, update_date, update_user_id
        FROM recipe_src.rcp_ingr_stg
        EXCEPT ALL
        SELECT rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id, rcp_ingr_line_no, ingr_id, rcp_ingr_raw_txt, rcp_ingr_parsed_nm,
               rcp_ingr_qty, rcp_ingr_unit_nm, rcp_ingr_section_txt, rcp_ingr_status, rcp_ingr_review_note,
               rcp_ingr_parser_version, rcp_ingr_approved_date, rcp_ingr_approved_user_id,
               create_date, create_user_id, update_date, update_user_id
        FROM recipe.rcp_ingr_stg) AS d)),
    ('diff_rcp_ingr_stg_tgt_only', (SELECT count(*) FROM (
        SELECT rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id, rcp_ingr_line_no, ingr_id, rcp_ingr_raw_txt, rcp_ingr_parsed_nm,
               rcp_ingr_qty, rcp_ingr_unit_nm, rcp_ingr_section_txt, rcp_ingr_status, rcp_ingr_review_note,
               rcp_ingr_parser_version, rcp_ingr_approved_date, rcp_ingr_approved_user_id,
               create_date, create_user_id, update_date, update_user_id
        FROM recipe.rcp_ingr_stg
        EXCEPT ALL
        SELECT rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id, rcp_ingr_line_no, ingr_id, rcp_ingr_raw_txt, rcp_ingr_parsed_nm,
               rcp_ingr_qty, rcp_ingr_unit_nm, rcp_ingr_section_txt, rcp_ingr_status, rcp_ingr_review_note,
               rcp_ingr_parser_version, rcp_ingr_approved_date, rcp_ingr_approved_user_id,
               create_date, create_user_id, update_date, update_user_id
        FROM recipe_src.rcp_ingr_stg) AS d)),
    ('diff_rcp_ingr_src_only', (SELECT count(*) FROM (
        SELECT rcp_id, ingr_id, rcp_raw_id, create_date, create_user_id, update_date, update_user_id FROM recipe_src.rcp_ingr
        EXCEPT ALL
        SELECT rcp_id, ingr_id, rcp_raw_id, create_date, create_user_id, update_date, update_user_id FROM recipe.rcp_ingr) AS d)),
    ('diff_rcp_ingr_tgt_only', (SELECT count(*) FROM (
        SELECT rcp_id, ingr_id, rcp_raw_id, create_date, create_user_id, update_date, update_user_id FROM recipe.rcp_ingr
        EXCEPT ALL
        SELECT rcp_id, ingr_id, rcp_raw_id, create_date, create_user_id, update_date, update_user_id FROM recipe_src.rcp_ingr) AS d)),

    -- ----- 제거한 분류 컬럼의 정보 손실 여부(원본 기준) -----
    ('lost_rcp_step_rcp_cat_id', (SELECT count(*) FROM recipe_src.rcp_step AS st
        LEFT JOIN recipe_src.rcp AS r ON r.rcp_id = st.rcp_id
        WHERE r.rcp_cat_id IS DISTINCT FROM st.rcp_cat_id)),
    ('lost_rcp_ingr_rcp_cat_id', (SELECT count(*) FROM recipe_src.rcp_ingr AS f
        LEFT JOIN recipe_src.rcp AS r ON r.rcp_id = f.rcp_id
        WHERE r.rcp_cat_id IS DISTINCT FROM f.rcp_cat_id)),
    ('lost_rcp_ingr_ingr_cat_id', (SELECT count(*) FROM recipe_src.rcp_ingr AS f
        LEFT JOIN recipe_src.ingr AS i ON i.ingr_id = f.ingr_id
        WHERE i.ingr_cat_id IS DISTINCT FROM f.ingr_cat_id)),
    ('lost_ingr_als_ingr_cat_id', (SELECT count(*) FROM recipe_src.ingr_als AS a
        LEFT JOIN recipe_src.ingr AS i ON i.ingr_id = a.ingr_id
        WHERE i.ingr_cat_id IS DISTINCT FROM a.ingr_cat_id)),
    ('lost_stg_ingr_cat_id', (SELECT count(*) FROM recipe_src.rcp_ingr_stg AS s
        LEFT JOIN recipe_src.ingr AS i ON i.ingr_id = s.ingr_id
        WHERE (s.ingr_id IS NULL AND s.ingr_cat_id IS NOT NULL)
           OR (s.ingr_id IS NOT NULL AND i.ingr_cat_id IS DISTINCT FROM s.ingr_cat_id))),

    -- ----- 대상 키 중복·논리 참조 -----
    ('dup_rcp_seq', (SELECT count(*) FROM (SELECT rcp_seq FROM recipe.rcp GROUP BY rcp_seq HAVING count(*) > 1) AS d)),
    ('dup_ingr_als_id', (SELECT count(*) FROM (SELECT ingr_als_id FROM recipe.ingr_als GROUP BY ingr_als_id HAVING count(*) > 1) AS d)),
    ('dup_rcp_ingr_stg_id', (SELECT count(*) FROM (SELECT rcp_ingr_stg_id FROM recipe.rcp_ingr_stg GROUP BY rcp_ingr_stg_id HAVING count(*) > 1) AS d)),
    ('orphan_rcp_without_raw', (SELECT count(*) FROM recipe.rcp AS r
        WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp_raw AS raw WHERE raw.rcp_raw_id = r.rcp_raw_id AND raw.rcp_seq = r.rcp_seq))),
    ('orphan_rcp_without_cook_method', (SELECT count(*) FROM recipe.rcp AS r
        WHERE NOT EXISTS (SELECT 1 FROM recipe.common_cd AS c WHERE c.common_code_grp_id = 'COOK_MTHD' AND c.common_cd = r.cook_mthd_cd))),
    ('orphan_code_without_group', (SELECT count(*) FROM recipe.common_cd AS c
        WHERE NOT EXISTS (SELECT 1 FROM recipe.common_code_grp AS g WHERE g.common_code_grp_id = c.common_code_grp_id))),
    ('orphan_rcp_without_category', (SELECT count(*) FROM recipe.rcp AS r
        WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp_cat_rel AS rel WHERE rel.rcp_id = r.rcp_id))),
    ('orphan_cat_rel_without_rcp', (SELECT count(*) FROM recipe.rcp_cat_rel AS rel
        WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp AS r WHERE r.rcp_id = rel.rcp_id))),
    ('orphan_cat_rel_without_cat', (SELECT count(*) FROM recipe.rcp_cat_rel AS rel
        WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp_cat AS c WHERE c.rcp_cat_id = rel.rcp_cat_id))),
    ('orphan_step_without_rcp', (SELECT count(*) FROM recipe.rcp_step AS st
        WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp AS r WHERE r.rcp_id = st.rcp_id))),
    ('orphan_als_without_ingr', (SELECT count(*) FROM recipe.ingr_als AS a
        WHERE NOT EXISTS (SELECT 1 FROM recipe.ingr AS i WHERE i.ingr_id = a.ingr_id))),
    ('orphan_stg_without_raw', (SELECT count(*) FROM recipe.rcp_ingr_stg AS s
        WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp_raw AS raw WHERE raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq))),
    ('orphan_stg_without_ingr', (SELECT count(*) FROM recipe.rcp_ingr_stg AS s
        WHERE s.ingr_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM recipe.ingr AS i WHERE i.ingr_id = s.ingr_id))),
    ('orphan_rcp_ingr_without_rcp', (SELECT count(*) FROM recipe.rcp_ingr AS f
        WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp AS r WHERE r.rcp_id = f.rcp_id))),
    ('orphan_rcp_ingr_without_ingr', (SELECT count(*) FROM recipe.rcp_ingr AS f
        WHERE NOT EXISTS (SELECT 1 FROM recipe.ingr AS i WHERE i.ingr_id = f.ingr_id))),
    ('orphan_relation_without_approved_staging', (SELECT count(*) FROM recipe.rcp_ingr AS f
        WHERE NOT EXISTS (SELECT 1 FROM tgt_approved AS a WHERE a.rcp_id = f.rcp_id AND a.ingr_id = f.ingr_id))),
    ('orphan_approved_staging_without_relation', (SELECT count(*) FROM tgt_approved AS a
        WHERE NOT EXISTS (SELECT 1 FROM recipe.rcp_ingr AS f WHERE f.rcp_id = a.rcp_id AND f.ingr_id = a.ingr_id))),
    ('conflict_name_multi_ingredient', (SELECT count(*) FROM (
        SELECT nm FROM (
            SELECT ingr_nm AS nm, ingr_id FROM recipe.ingr
            UNION
            SELECT ingr_als_nm, ingr_id FROM recipe.ingr_als
        ) AS n GROUP BY nm HAVING count(DISTINCT ingr_id) > 1) AS d)),

    -- ----- 자동 승인 10,611 vs 최종 관계 10,428 차이 설명 -----
    ('gap_unexplained', ((SELECT count(*) FROM tgt_approved) - (SELECT count(*) FROM recipe.rcp_ingr))
                      - ((SELECT count(*) FROM tgt_approved) - (SELECT count(DISTINCT (rcp_id, ingr_id)) FROM tgt_approved))),
    ('gap_src_tgt_approved_differs', (SELECT count(*) FROM (
        (SELECT rcp_id, ingr_id FROM src_approved EXCEPT ALL SELECT rcp_id, ingr_id FROM tgt_approved)
        UNION ALL
        (SELECT rcp_id, ingr_id FROM tgt_approved EXCEPT ALL SELECT rcp_id, ingr_id FROM src_approved)) AS d)),

    -- ----- 시퀀스 -----
    ('seq_behind_max_id', (SELECT count(*) FROM id_seq WHERE tgt_value < max_id)),
    ('seq_behind_source', (SELECT count(*) FROM id_seq WHERE tgt_value < src_value))
) AS checks(check_nm, actual);
