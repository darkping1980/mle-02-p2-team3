-- [이력 문서] 2026-10-22 목표 모델 전환 전 다중 분류 초안 검증 SQL. 실행용 최종본: recipe_target_schema.sql / recipe_target_validation.sql
-- 읽기 전용 목표 모델 검증. 목표 스키마를 별도 승인 후 적용한 뒤에만 실행.
-- 정상 상태라면 모든 조회는 0행을 반환한다.

SELECT rcp_id, rcp_cat_id, count(*) AS n
FROM recipe.rcp_cat_rel
GROUP BY rcp_id, rcp_cat_id HAVING count(*) > 1;

SELECT rel.rcp_id, rel.rcp_cat_id
FROM recipe.rcp_cat_rel AS rel
LEFT JOIN recipe.rcp AS r ON r.rcp_id = rel.rcp_id
LEFT JOIN recipe.rcp_cat AS c ON c.rcp_cat_id = rel.rcp_cat_id
WHERE r.rcp_id IS NULL OR c.rcp_cat_id IS NULL;

SELECT r.rcp_id
FROM recipe.rcp AS r
LEFT JOIN recipe.rcp_cat_rel AS rel ON rel.rcp_id = r.rcp_id
WHERE rel.rcp_id IS NULL;

SELECT c.rcp_cat_id, c.rcp_cat_axis_cd
FROM recipe.rcp_cat AS c
LEFT JOIN recipe.common_cd AS cd
  ON cd.common_code_grp_id = 'RCP_CAT_AXIS'
 AND cd.common_cd = c.rcp_cat_axis_cd
WHERE cd.common_cd IS NULL;

SELECT s.rcp_id, s.step_no
FROM recipe.rcp_step AS s
LEFT JOIN recipe.rcp AS r ON r.rcp_id = s.rcp_id
WHERE r.rcp_id IS NULL;

SELECT f.ingr_cat_id, f.ingr_id, f.rcp_id
FROM recipe.rcp_ingr AS f
LEFT JOIN recipe.rcp AS r ON r.rcp_id = f.rcp_id
LEFT JOIN recipe.ingr AS i
  ON i.ingr_cat_id = f.ingr_cat_id AND i.ingr_id = f.ingr_id
WHERE r.rcp_id IS NULL OR i.ingr_id IS NULL;

SELECT rcp_id, step_no, count(*) AS n
FROM recipe.rcp_step
GROUP BY rcp_id, step_no HAVING count(*) > 1;

SELECT ingr_cat_id, ingr_id, rcp_id, count(*) AS n
FROM recipe.rcp_ingr
GROUP BY ingr_cat_id, ingr_id, rcp_id HAVING count(*) > 1;
