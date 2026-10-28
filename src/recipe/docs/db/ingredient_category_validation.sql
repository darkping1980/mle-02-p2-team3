-- [이력 문서] 2026-10-22 목표 모델 전환 전 기존 모델 대상 식재료 분류 제거 사전 검증 SQL. 실행용 최종본: recipe_target_schema.sql / recipe_target_validation.sql
-- 식재료 분류 제거 영향 검증. 현행 recipe 스키마 전용 SELECT.
-- DDL/DML 없음. 집계와 문제 행 조회를 각각 실행해 결과를 대조한다.

SELECT count(*) AS ingredient_count, count(DISTINCT ingr_id) AS distinct_ingr_id
FROM recipe.ingr;

SELECT ingr_id, count(*) AS n
FROM recipe.ingr
GROUP BY ingr_id HAVING count(*) > 1;

SELECT c.ingr_cat_id, c.ingr_cat_nm, count(i.ingr_id) AS ingredient_count
FROM recipe.ingr_cat AS c
LEFT JOIN recipe.ingr AS i ON i.ingr_cat_id = c.ingr_cat_id
GROUP BY c.ingr_cat_id, c.ingr_cat_nm
ORDER BY c.ingr_cat_nm;

SELECT i.ingr_cat_id, i.ingr_id, i.ingr_nm
FROM recipe.ingr AS i
LEFT JOIN recipe.ingr_cat AS c ON c.ingr_cat_id = i.ingr_cat_id
WHERE c.ingr_cat_id IS NULL;

SELECT count(*) AS alias_count,
       count(DISTINCT ingr_id) AS ingredients_with_alias,
       count(DISTINCT ingr_als_nm) AS distinct_alias_names
FROM recipe.ingr_als;

SELECT a.ingr_id, a.ingr_als_nm, count(*) AS n
FROM recipe.ingr_als AS a
GROUP BY a.ingr_id, a.ingr_als_nm HAVING count(*) > 1;

SELECT a.ingr_cat_id, a.ingr_id, a.ingr_als_nm
FROM recipe.ingr_als AS a
LEFT JOIN recipe.ingr AS i
  ON i.ingr_cat_id = a.ingr_cat_id AND i.ingr_id = a.ingr_id
WHERE i.ingr_id IS NULL;

SELECT nm, count(DISTINCT ingr_id) AS target_count
FROM (
    SELECT ingr_nm AS nm, ingr_id FROM recipe.ingr
    UNION ALL
    SELECT ingr_als_nm AS nm, ingr_id FROM recipe.ingr_als
) AS names
GROUP BY nm HAVING count(DISTINCT ingr_id) > 1;

SELECT a.ingr_als_nm, i.ingr_nm
FROM recipe.ingr_als AS a
JOIN recipe.ingr AS i
  ON i.ingr_cat_id = a.ingr_cat_id AND i.ingr_id = a.ingr_id
ORDER BY a.ingr_als_nm
LIMIT 20;

SELECT count(*) AS relation_count,
       count(DISTINCT (rcp_id, ingr_id)) AS distinct_target_pairs
FROM recipe.rcp_ingr;

SELECT rcp_id, ingr_id, count(*) AS n
FROM recipe.rcp_ingr
GROUP BY rcp_id, ingr_id HAVING count(*) > 1;

SELECT f.rcp_id, f.ingr_cat_id, f.ingr_id
FROM recipe.rcp_ingr AS f
LEFT JOIN recipe.ingr AS i
  ON i.ingr_cat_id = f.ingr_cat_id AND i.ingr_id = f.ingr_id
WHERE i.ingr_id IS NULL;

SELECT s.rcp_raw_id, s.rcp_raw_seq, s.rcp_ingr_stg_id, s.ingr_cat_id, s.ingr_id
FROM recipe.rcp_ingr_stg AS s
LEFT JOIN recipe.ingr AS i
  ON i.ingr_cat_id = s.ingr_cat_id AND i.ingr_id = s.ingr_id
WHERE s.ingr_id IS NOT NULL AND i.ingr_id IS NULL;

SELECT count(*) FILTER (WHERE rcp_ingr_review_note LIKE '%exact alias match%') AS exact_alias_auto_approved,
       count(*) FILTER (WHERE rcp_ingr_review_note LIKE '%exact name match%') AS exact_name_auto_approved
FROM recipe.rcp_ingr_stg;

-- 그래프 검색과 같은 trim/lower 정규화에서 다른 식재료로 갈라지는 명칭.
SELECT lower(btrim(nm)) AS normalized_name, count(DISTINCT ingr_id) AS target_count
FROM (
    SELECT ingr_nm AS nm, ingr_id FROM recipe.ingr
    UNION ALL
    SELECT ingr_als_nm AS nm, ingr_id FROM recipe.ingr_als
) AS names
GROUP BY lower(btrim(nm)) HAVING count(DISTINCT ingr_id) > 1;

SELECT count(*) AS stage_count,
       count(*) FILTER (WHERE ingr_id IS NOT NULL) AS mapped_stage_count,
       count(*) FILTER (WHERE ingr_id IS NULL AND ingr_cat_id IS NOT NULL) AS incomplete_pair_count
FROM recipe.rcp_ingr_stg;
