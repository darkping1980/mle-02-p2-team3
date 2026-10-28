// 2026-10-22 실제 적재 후 8개 명명 조회를 실행해 기본 결과를 검증했다.
// 모든 이름은 식별 키가 아니라 검색 조건이다. 여러 후보가 나오면 rcp_id / ingr_id로 선택한다.

// name: find_recipe_by_name
// $rcp_nm 예: 사용자가 입력한 레시피 이름
MATCH (r:rcp {rcp_nm: $rcp_nm})
RETURN r.rcp_id AS rcp_id, r.rcp_seq AS rcp_seq, r.rcp_nm AS rcp_nm
ORDER BY r.rcp_id;

// name: recipe_ingredients
// '새우 두부 계란찜에 어떤 재료가 사용되는가?'
// 먼저 find_recipe_by_name에서 rcp_id를 선택한다.
MATCH (r:rcp {rcp_id: $rcp_id})
OPTIONAL MATCH (r)-[:RCP_USES]->(i:ingr)
RETURN r.rcp_id AS rcp_id, r.rcp_nm AS rcp_nm,
       collect(CASE WHEN i IS NULL THEN null ELSE {
         ingr_id: i.ingr_id, ingr_nm: i.ingr_nm
       } END) AS ingredients;

// name: recipes_using_ingredient
// '칵테일새우를 사용하는 다른 레시피는?'
// 표준명/별칭으로 후보 식재료를 먼저 찾고, 선택한 ingr_id를 전달한다.
MATCH (i:ingr {ingr_id: $ingr_id})
MATCH (r:rcp)-[:RCP_USES]->(i)
WHERE $exclude_rcp_id IS NULL OR r.rcp_id <> $exclude_rcp_id
RETURN i.ingr_nm AS ingredient, r.rcp_id AS rcp_id, r.rcp_nm AS rcp_nm
ORDER BY r.rcp_nm, r.rcp_id
LIMIT 30;

// name: similar_recipes
// 공통 재료 수와 Jaccard = 교집합 / 합집합을 함께 제공한다.
MATCH (base:rcp {rcp_id: $rcp_id})
MATCH (base)-[:RCP_USES]->(shared:ingr)<-[:RCP_USES]-(candidate:rcp)
WHERE candidate <> base
WITH base, candidate, count(DISTINCT shared) AS common_count,
     collect(DISTINCT shared.ingr_nm) AS common_ingredients
WITH candidate, common_count, common_ingredients,
     size([(base)-[:RCP_USES]->() | 1]) AS base_total,
     size([(candidate)-[:RCP_USES]->() | 1]) AS candidate_total
RETURN candidate.rcp_id AS rcp_id,
       candidate.rcp_nm AS rcp_nm, common_count, common_ingredients,
       toFloat(common_count) / (base_total + candidate_total - common_count) AS jaccard
ORDER BY common_count DESC, jaccard DESC, rcp_id
LIMIT 20;

// name: ingredient_name_candidates
// ETL과 동일하게 양끝 공백 제거 + 소문자화된 입력 $term_norm.
// 별칭이 여러 식재료를 가리키면 모두 반환해 사용자가 고르게 한다.
MATCH (i:ingr)
WHERE i.ingr_nm_norm = $term_norm OR $term_norm IN coalesce(i.alias_names_norm, [])
RETURN i.ingr_id AS ingr_id,
       i.ingr_nm AS ingr_nm, i.alias_names AS alias_names
ORDER BY i.ingr_nm;

// name: recipes_by_ingredient_term
// '계란이 들어가는 레시피는?' — 입력어($term_norm, 양끝 공백 제거·소문자화)를 표준명 또는 별칭으로 해석한다.
// 별칭 '계란'은 표준 식재료 '달걀'로 매핑된다. 유사 이름(두부/연두부)은 합치지 않는다.
MATCH (i:ingr)
WHERE i.ingr_nm_norm = $term_norm OR $term_norm IN coalesce(i.alias_names_norm, [])
MATCH (r:rcp)-[:RCP_USES]->(i)
RETURN i.ingr_id AS ingr_id, i.ingr_nm AS ingredient,
       r.rcp_id AS rcp_id, r.rcp_seq AS rcp_seq, r.rcp_nm AS rcp_nm
ORDER BY r.rcp_nm, r.rcp_id;

// name: recipes_with_all_ingredients
// '계란과 두부가 모두 들어가는 레시피는?' — 입력어마다 그 표준명·별칭에 해당하는 식재료를 하나 이상 사용하는 레시피.
// $terms_norm: 정규화된 입력어 목록. 해석되지 않는 입력어가 있으면 결과는 비어 있다.
WITH [term IN $terms_norm WHERE term <> ''] AS terms
WHERE size(terms) > 0
MATCH (r:rcp)
WHERE all(term IN terms WHERE EXISTS {
    MATCH (r)-[:RCP_USES]->(i:ingr)
    WHERE i.ingr_nm_norm = term OR term IN coalesce(i.alias_names_norm, [])
})
RETURN r.rcp_id AS rcp_id, r.rcp_seq AS rcp_seq, r.rcp_nm AS rcp_nm,
       [(r)-[:RCP_USES]->(i:ingr)
        WHERE any(term IN terms WHERE i.ingr_nm_norm = term OR term IN coalesce(i.alias_names_norm, []))
        | i.ingr_nm] AS matched_ingredients
ORDER BY r.rcp_nm, r.rcp_id;

// name: recipes_in_category
// '반찬 분류에 속한 레시피는?' — rcp_cat_rel 행마다 만든 RCP_IN_RECIPE_CATEGORY를 따라간다(다중 분류 가능).
MATCH (c:rcp_cat {rcp_cat_nm: $rcp_cat_nm})<-[:RCP_IN_RECIPE_CATEGORY]-(r:rcp)
RETURN c.rcp_cat_id AS rcp_cat_id, r.rcp_id AS rcp_id, r.rcp_seq AS rcp_seq, r.rcp_nm AS rcp_nm
ORDER BY r.rcp_nm, r.rcp_id;

// name: pantry_recommendations
// $names_norm: Python에서 정규화한 보유 식재료명 목록.
// 이름이 모호하면 ingredient_name_candidates로 먼저 사용자 확인을 거친다.
// 같은 식재료에 걸린 여러 별칭 입력은 collect(DISTINCT i)로 1개로 센다.
UNWIND $names_norm AS term
WITH DISTINCT term WHERE term <> ''
MATCH (i:ingr)
WHERE i.ingr_nm_norm = term OR term IN coalesce(i.alias_names_norm, [])
WITH collect(DISTINCT i) AS pantry
UNWIND pantry AS owned
MATCH (r:rcp)-[:RCP_USES]->(owned)
WITH r, pantry, collect(DISTINCT owned) AS matched
OPTIONAL MATCH (r)-[:RCP_USES]->(needed:ingr)
WITH r, pantry, matched, collect(DISTINCT needed) AS all_ingredients
RETURN r.rcp_id AS rcp_id, r.rcp_nm AS rcp_nm,
       size(matched) AS matched_count,
       size(all_ingredients) - size(matched) AS missing_count,
       [x IN matched | x.ingr_nm] AS matched_ingredients,
       [x IN all_ingredients WHERE NOT (x IN pantry) | x.ingr_nm] AS missing_ingredients
ORDER BY missing_count ASC, matched_count DESC, rcp_id
LIMIT 20;

// name: category_and_ingredient
// '반찬 종류 중에서 달걀이 들어가는 레시피는?'
// $rcp_cat_nm='반찬', $term_norm은 달걀 등의 정규화된 표준명 또는 별칭.
MATCH (c:rcp_cat {rcp_cat_nm: $rcp_cat_nm})<-[:RCP_IN_RECIPE_CATEGORY]-(r:rcp)
MATCH (r)-[:RCP_USES]->(i:ingr)
WHERE i.ingr_nm_norm = $term_norm OR $term_norm IN coalesce(i.alias_names_norm, [])
RETURN DISTINCT r.rcp_id AS rcp_id,
       r.rcp_nm AS rcp_nm, i.ingr_nm AS matched_ingredient
ORDER BY rcp_nm
LIMIT 30;

// name: graphrag_context
// LangGraph가 rcp_id로 조회해 LLM에 전달할 구조화된 근거. 요리 분류는 여러 개일 수 있다.
// image_url은 화면 표시용 식약처 대표 이미지(rcp.rcp_image_url)이며 LLM 근거에는 넣지 않는다.
// 조리 단계는 recipe_steps로 별도 조회한다.
MATCH (r:rcp {rcp_id: $rcp_id})
OPTIONAL MATCH (r)-[:RCP_IN_RECIPE_CATEGORY]->(c:rcp_cat)
WITH r, collect(DISTINCT c.rcp_cat_nm) AS category_names
OPTIONAL MATCH (r)-[:RCP_USES]->(i:ingr)
WITH r, category_names, collect(DISTINCT i.ingr_nm) AS ingredient_names
RETURN {rcp_id: r.rcp_id, rcp_seq: r.rcp_seq,
        name: r.rcp_nm, categories: category_names,
        method: r.cook_mthd_nm, energy_kcal: r.rcp_energy_kcal,
        nutrition_status: r.rcp_nutrition_status,
        image_url: r.rcp_image_url,
        ingredients: ingredient_names} AS context;

// name: recipe_steps
// '이 레시피는 어떤 순서로 만드나?' — 식약처 원본 조리 과정(MANUAL01~20)을 원본 번호 순서로 돌려준다.
// $rcp_ids: 추천된 레시피 ID 목록(한 번에 조회). 단계가 없는 레시피는 행이 없다.
// step_no는 원본 번호 그대로라 중간 번호가 비어 있을 수 있다(예: 1, 2, 4).
UNWIND $rcp_ids AS id
MATCH (r:rcp {rcp_id: id})-[:RCP_HAS_STEP]->(s:rcp_step)
RETURN r.rcp_id AS rcp_id, s.step_no AS step_no,
       s.rcp_step_instruction_txt AS instruction_txt, s.rcp_step_image_url AS image_url
ORDER BY rcp_id, step_no;
