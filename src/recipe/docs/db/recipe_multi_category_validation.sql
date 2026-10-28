-- [이력 문서] 2026-10-22 목표 모델 전환 전 기존 모델 대상 다중 분류 사전 검증 SQL. 실행용 최종본: recipe_target_schema.sql / recipe_target_validation.sql
-- 읽기 전용 사전 검증. 아래 '현재 모델' 조회는 현행 DB에서 바로 실행 가능.
-- 각 SELECT는 문제 건수 또는 문제 행을 반환한다. PK가 있는 테이블도
-- 마이그레이션 전에 키 손상·잘못된 논리 참조를 다시 확인한다.

-- 현재 모델: 단독 레시피 ID 및 원본 번호 중복.
SELECT rcp_id, count(*) AS n
FROM recipe.rcp
GROUP BY rcp_id HAVING count(*) > 1;

SELECT rcp_seq, count(*) AS n
FROM recipe.rcp
GROUP BY rcp_seq HAVING count(*) > 1;

-- 현재 모델: 조리 단계 / 식재료 관계의 목표 복합 PK 중복.
SELECT rcp_id, step_no, count(*) AS n
FROM recipe.rcp_step
GROUP BY rcp_id, step_no HAVING count(*) > 1;

SELECT ingr_cat_id, ingr_id, rcp_id, count(*) AS n
FROM recipe.rcp_ingr
GROUP BY ingr_cat_id, ingr_id, rcp_id HAVING count(*) > 1;

-- 현재 모델: 부모 참조 누락 또는 부모와 요리 분류 불일치.
SELECT s.rcp_cat_id, s.rcp_id, s.step_no
FROM recipe.rcp_step AS s
LEFT JOIN recipe.rcp AS r
  ON r.rcp_id = s.rcp_id AND r.rcp_cat_id = s.rcp_cat_id
WHERE r.rcp_id IS NULL;

SELECT f.ingr_cat_id, f.ingr_id, f.rcp_cat_id, f.rcp_id
FROM recipe.rcp_ingr AS f
LEFT JOIN recipe.rcp AS r
  ON r.rcp_id = f.rcp_id AND r.rcp_cat_id = f.rcp_cat_id
LEFT JOIN recipe.ingr AS i
  ON i.ingr_cat_id = f.ingr_cat_id AND i.ingr_id = f.ingr_id
WHERE r.rcp_id IS NULL OR i.ingr_id IS NULL;

SELECT r.rcp_id, r.rcp_cat_id
FROM recipe.rcp AS r
LEFT JOIN recipe.rcp_cat AS c ON c.rcp_cat_id = r.rcp_cat_id
WHERE c.rcp_cat_id IS NULL;

-- 현재 분류를 관계로 옮길 때 후보 (rcp_id, rcp_cat_id) 중복/누락.
SELECT rcp_id, rcp_cat_id, count(*) AS n
FROM recipe.rcp
GROUP BY rcp_id, rcp_cat_id HAVING count(*) > 1;

SELECT rcp_id
FROM recipe.rcp
WHERE rcp_cat_id IS NULL;

-- 원본 회차/원본 번호 및 승인 식재료 staging 참조.
SELECT r.rcp_id, r.rcp_raw_id, r.rcp_seq
FROM recipe.rcp AS r
LEFT JOIN recipe.rcp_raw AS raw
  ON raw.rcp_raw_id = r.rcp_raw_id AND raw.rcp_seq = r.rcp_seq
WHERE raw.rcp_raw_id IS NULL;

SELECT s.rcp_raw_id, s.rcp_raw_seq, s.rcp_ingr_stg_id
FROM recipe.rcp_ingr_stg AS s
LEFT JOIN recipe.rcp_raw AS raw
  ON raw.rcp_raw_id = s.rcp_raw_id AND raw.rcp_raw_seq = s.rcp_raw_seq
LEFT JOIN recipe.ingr AS i
  ON i.ingr_cat_id = s.ingr_cat_id AND i.ingr_id = s.ingr_id
WHERE raw.rcp_raw_id IS NULL
   OR (s.rcp_ingr_status IN ('AUTO_APPROVED', 'MANUAL_APPROVED')
       AND i.ingr_id IS NULL);

-- 목표 적용 후 조회는 recipe_multi_category_target_validation.sql 참조.
