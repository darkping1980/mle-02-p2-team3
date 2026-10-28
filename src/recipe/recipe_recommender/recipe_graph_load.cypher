// Python 적재 CLI가 PostgreSQL 목표 모델 SELECT 결과를 $rows로 전달한다.
// 권장 순서: 1 요리 분류, 2 식재료/레시피, 3 요리 분류 관계(rcp_cat_rel), 4 USES(rcp_ingr), 5 조리 단계(rcp_step).
// 각 명령을 별도의 배치 트랜잭션으로 실행한다. 500~1,000행/배치부터 시작한다.
// ETL은 NOT NULL 키, 부모 참조, 승인 상태, 중복 키를 먼저 검증한다.
// PostgreSQL numeric은 Python에서 검토 후 Neo4j가 받는 float로 명시 변환한다.
// 식재료 분류 노드·관계는 목표 모델에서 제거되었다.

// name: load_recipe_categories
// $rows: [{rcp_cat_id, rcp_cat_nm}, ...]
UNWIND $rows AS row
MERGE (c:rcp_cat {rcp_cat_id: row.rcp_cat_id})
SET c.rcp_cat_nm = row.rcp_cat_nm;

// name: load_ingredients
// recipe.ingr LEFT JOIN recipe.ingr_als ON ingr_id.
// ETL에서 1식재료당 1행으로 묶고 별칭을 정렬·중복 제거한다.
// $rows: [{ingr_id, ingr_nm, ingr_nm_norm, alias_names: [], alias_names_norm: []}, ...]
UNWIND $rows AS row
MERGE (i:ingr {ingr_id: row.ingr_id})
SET i.ingr_nm = row.ingr_nm,
    i.ingr_nm_norm = row.ingr_nm_norm,
    i.alias_names = row.alias_names,
    i.alias_names_norm = row.alias_names_norm;

// name: load_recipes
// recipe.rcp LEFT JOIN recipe.common_cd
//   ON common_code_grp_id = 'COOK_MTHD' AND common_cd = cook_mthd_cd.
// 코드 그룹 검증 실패 시 ETL에서 중단한다.
// $rows: [{rcp_id, rcp_seq, rcp_nm, cook_mthd_cd, cook_mthd_nm,
//          rcp_energy_kcal, rcp_nutrition_status, rcp_image_url}, ...]
UNWIND $rows AS row
MERGE (r:rcp {rcp_id: row.rcp_id})
SET r.rcp_seq = row.rcp_seq,
    r.rcp_nm = row.rcp_nm,
    r.cook_mthd_cd = row.cook_mthd_cd,
    r.cook_mthd_nm = row.cook_mthd_nm,
    r.rcp_energy_kcal = row.rcp_energy_kcal,
    r.rcp_nutrition_status = row.rcp_nutrition_status,
    r.rcp_image_url = row.rcp_image_url;

// name: link_recipe_categories
// recipe.rcp_cat_rel 한 행 = 관계 하나. 사전 검증에서 입력 수 = 부모·자식 MATCH 수 확인 후 실행.
// $rows: [{rcp_id, rcp_cat_id}, ...]
UNWIND $rows AS row
MATCH (r:rcp {rcp_id: row.rcp_id})
MATCH (c:rcp_cat {rcp_cat_id: row.rcp_cat_id})
MERGE (r)-[:RCP_IN_RECIPE_CATEGORY]->(c);

// name: check_recipe_category_batch_matches
UNWIND $rows AS row
OPTIONAL MATCH (r:rcp {rcp_id: row.rcp_id})
OPTIONAL MATCH (c:rcp_cat {rcp_cat_id: row.rcp_cat_id})
RETURN count(*) AS input_rows,
       count(CASE WHEN r IS NOT NULL AND c IS NOT NULL THEN 1 END) AS matched_rows;

// name: check_uses_batch_matches
// 아래 결과가 {input_rows: N, matched_rows: N}인지 Python에서 검사한다.
// 하나라도 누락되면 다음 쓰기 명령을 실행하지 않는다.
UNWIND $rows AS row
OPTIONAL MATCH (r:rcp {rcp_id: row.rcp_id})
OPTIONAL MATCH (i:ingr {ingr_id: row.ingr_id})
RETURN count(*) AS input_rows,
       count(CASE WHEN r IS NOT NULL AND i IS NOT NULL THEN 1 END) AS matched_rows;

// name: link_uses
// $rows는 recipe.rcp_ingr의 서로 다른 PK (rcp_id, ingr_id)만 포함한다.
// 원본 등장 순서·수량·보류 staging 행은 추가하지 않는다.
UNWIND $rows AS row
MATCH (r:rcp {rcp_id: row.rcp_id})
MATCH (i:ingr {ingr_id: row.ingr_id})
MERGE (r)-[:RCP_USES]->(i);

// name: check_recipe_step_batch_matches
// 조리 단계의 부모 레시피가 모두 있는지 확인한다. 하나라도 없으면 load_recipe_steps를 실행하지 않는다.
UNWIND $rows AS row
OPTIONAL MATCH (r:rcp {rcp_id: row.rcp_id})
RETURN count(*) AS input_rows,
       count(CASE WHEN r IS NOT NULL THEN 1 END) AS matched_rows;

// name: load_recipe_steps
// recipe.rcp_step 한 행 = rcp_step 노드 하나 + RCP_HAS_STEP 관계 하나.
// 식약처 원본 MANUAL01~20 설명·MANUAL_IMG01~20 URL을 그대로 옮긴다(가공·생성 없음).
// 단계 이미지가 NULL이면 SET이 속성을 두지 않는다. 기존 rcp·ingr·rcp_cat 노드와 관계는 건드리지 않는다.
// $rows: [{rcp_id, step_no, rcp_step_instruction_txt, rcp_step_image_url}, ...]
UNWIND $rows AS row
MATCH (r:rcp {rcp_id: row.rcp_id})
MERGE (s:rcp_step {rcp_id: row.rcp_id, step_no: row.step_no})
SET s.rcp_step_instruction_txt = row.rcp_step_instruction_txt,
    s.rcp_step_image_url = row.rcp_step_image_url
MERGE (r)-[:RCP_HAS_STEP]->(s);

// 동일 배치를 재실행해도 MERGE된 노드·관계 수가 늘지 않는지 별도 검증한다.
// 원천에서 사라진 행의 삭제는 이 파일에 포함하지 않는다.
