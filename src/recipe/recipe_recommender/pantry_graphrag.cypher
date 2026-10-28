// 냉장고 재료 추천 GraphRAG(pantry_graphrag.py)가 쓰는 읽기 전용 조회.
// 입력어 해석·근거 조회는 recipe_graph_queries.cypher의 ingredient_name_candidates, pantry_recommendations,
// graphrag_context를 그대로 재사용한다. 여기에는 LLM 답변 검증용 어휘 조회와, 기존 추천 쿼리와 정렬만 다른
// 보유 재료 우선 추천 쿼리를 둔다. 모두 읽기 전용(MATCH/RETURN)이다.

// name: ingredient_vocabulary
// LLM 답변에 근거 밖 식재료가 등장했는지 검사하기 위한 전체 표준 식재료명·별칭 목록.
MATCH (i:ingr)
RETURN i.ingr_id AS ingr_id, i.ingr_nm AS ingr_nm, coalesce(i.alias_names, []) AS alias_names
ORDER BY i.ingr_id;

// name: pantry_recommendations_by_coverage
// recipe_graph_queries.pantry_recommendations와 같은 매칭·반환 형식이고 정렬만 다르다.
// 보유 재료를 많이 쓰는 레시피 우선(사용 재료 수 내림차순 → 부족 재료 수 오름차순). $limit: 1~20.
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
ORDER BY matched_count DESC, missing_count ASC, rcp_id
LIMIT $limit;
