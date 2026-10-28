// 그래프 관계 탐색(Streamlit 모드 B, graph_question_service.py)이 쓰는 읽기 전용 조회.
// Q1·Q2·Q5는 recipe_graph_queries.cypher의 recipes_by_ingredient_term, similar_recipes, recipe_steps를 그대로 쓴다.
// 여기에는 기존 쿼리로 답할 수 없는 Q3(3-hop)·Q4(2-hop)와 화면 선택지 조회만 둔다. 모두 MATCH/RETURN만 쓴다.
// Hop = 패턴에서 건너가는 관계 수(LangGraph Node 실행 횟수가 아님).

// name: recipe_options
// 화면의 레시피 선택지(관계 탐색 없음). 이름이 같은 레시피가 있어 원본 번호(rcp_seq)를 함께 보여 준다.
MATCH (r:rcp)
RETURN r.rcp_id AS rcp_id, r.rcp_nm AS rcp_nm, r.rcp_seq AS rcp_seq
ORDER BY r.rcp_nm, r.rcp_seq;

// name: category_options
// 화면의 요리 분류 선택지(관계 탐색 없음).
MATCH (c:rcp_cat)
RETURN c.rcp_cat_id AS rcp_cat_id, c.rcp_cat_nm AS rcp_cat_nm
ORDER BY c.rcp_cat_nm;

// name: similar_recipe_categories
// Q3 (3-hop) '기준 레시피와 공통 재료를 쓰는 다른 레시피들은 어떤 요리 분류에 속하는가?'
// 경로: (base:rcp)-[:RCP_USES]->(:ingr)<-[:RCP_USES]-(other:rcp)-[:RCP_IN_RECIPE_CATEGORY]->(:rcp_cat)
// 공통 재료가 여러 개여도 다른 레시피는 count(DISTINCT shared)로 한 번만 센다.
// $min_common: 공통 재료 최소 개수(1이면 재료 하나만 겹쳐도 포함). 분류별 레시피 수 내림차순, 분류명 순.
// sample_recipes는 공통 재료가 많은 순(같으면 이름·ID 순) 최대 5개다.
MATCH (base:rcp {rcp_id: $rcp_id})-[:RCP_USES]->(shared:ingr)<-[:RCP_USES]-(other:rcp)
WHERE other <> base
WITH other, count(DISTINCT shared) AS common_count
WHERE common_count >= $min_common
MATCH (other)-[:RCP_IN_RECIPE_CATEGORY]->(c:rcp_cat)
WITH c, other, common_count
ORDER BY common_count DESC, other.rcp_nm, other.rcp_id
RETURN c.rcp_cat_nm AS rcp_cat_nm, count(DISTINCT other) AS recipe_count,
       max(common_count) AS max_common_count, collect(other.rcp_nm)[0..5] AS sample_recipes
ORDER BY recipe_count DESC, rcp_cat_nm;

// name: category_ingredients
// Q4 (2-hop) '반찬으로 분류된 레시피에서 사용하는 식재료는 무엇인가?'
// 경로: (:rcp_cat)<-[:RCP_IN_RECIPE_CATEGORY]-(:rcp)-[:RCP_USES]->(:ingr)
// 식재료별로 그 재료를 쓰는 레시피 수(DISTINCT)를 센다. 레시피 수 내림차순, 식재료명 순, 상위 $limit개.
// category_recipe_count(분류의 레시피 수)·category_ingredient_count(분류에서 쓰는 식재료 종류 수)는
// 상위 $limit개로 자르기 전의 분류 전체 규모이며 모든 행에 같은 값이다.
MATCH (c:rcp_cat {rcp_cat_nm: $rcp_cat_nm})<-[:RCP_IN_RECIPE_CATEGORY]-(r:rcp)
WITH c, count(r) AS category_recipe_count
MATCH (c)<-[:RCP_IN_RECIPE_CATEGORY]-(r:rcp)-[:RCP_USES]->(i:ingr)
WITH category_recipe_count, i, count(DISTINCT r) AS recipe_count
ORDER BY recipe_count DESC, i.ingr_nm
WITH category_recipe_count, collect({ingr_nm: i.ingr_nm, recipe_count: recipe_count}) AS ranked
UNWIND ranked[0..$limit] AS row
RETURN row.ingr_nm AS ingr_nm, row.recipe_count AS recipe_count,
       category_recipe_count, size(ranked) AS category_ingredient_count
ORDER BY recipe_count DESC, ingr_nm;
