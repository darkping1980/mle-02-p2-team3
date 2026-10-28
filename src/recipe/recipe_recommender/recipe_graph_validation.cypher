// Neo4jDbSession은 파일명과 // name: 선언을 조합해 쿼리를 찾는다.
// 이 파일은 그래프 사전 점검과 적재 후 읽기 전용 검증에 사용한다.

// name: server_version
CALL dbms.components() YIELD name, versions, edition
WHERE name = 'Neo4j Kernel'
RETURN versions, edition;

// name: database_name
CALL db.info() YIELD name
RETURN name;

// name: list_constraints
SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties
RETURN name, type, labelsOrTypes, properties;

// name: list_indexes
SHOW INDEXES YIELD name, type, labelsOrTypes, properties, owningConstraint
RETURN name, type, labelsOrTypes, properties, owningConstraint;

// name: total_nodes
MATCH (n)
RETURN count(n) AS n;

// name: total_relationships
MATCH ()-[r]->()
RETURN count(r) AS n;

// name: unknown_rcp_labels
// 이전 라벨(RcpRecipe 등 'Rcp' 접두어)이 남아 있어도 미지 라벨로 거부한다.
CALL db.labels() YIELD label
WHERE (label STARTS WITH 'Rcp' OR label STARTS WITH 'rcp' OR label STARTS WITH 'ingr') AND NOT label IN $expected
RETURN label;

// name: unknown_rcp_relationships
CALL db.relationshipTypes() YIELD relationshipType
WHERE relationshipType STARTS WITH 'RCP_' AND NOT relationshipType IN $expected
RETURN relationshipType;

// name: recipe_category_keys
MATCH (n:rcp_cat)
RETURN n.rcp_cat_id AS rcp_cat_id;

// name: ingredient_keys
MATCH (n:ingr)
RETURN n.ingr_id AS ingr_id;

// name: recipe_keys
MATCH (n:rcp)
RETURN n.rcp_id AS rcp_id, n.rcp_seq AS rcp_seq;

// name: recipe_category_links
MATCH (r:rcp)-[:RCP_IN_RECIPE_CATEGORY]->(c:rcp_cat)
RETURN r.rcp_id AS rcp_id, c.rcp_cat_id AS rcp_cat_id;

// name: uses_links
MATCH (r:rcp)-[:RCP_USES]->(i:ingr)
RETURN r.rcp_id AS rcp_id, i.ingr_id AS ingr_id;

// name: recipe_step_keys
MATCH (n:rcp_step)
RETURN n.rcp_id AS rcp_id, n.step_no AS step_no;

// name: recipe_step_links
// 관계 키는 부모 레시피 ID + 단계 번호. 다른 레시피의 단계에 잘못 걸린 관계는 step_link_errors가 잡는다.
MATCH (r:rcp)-[:RCP_HAS_STEP]->(s:rcp_step)
RETURN r.rcp_id AS rcp_id, s.step_no AS step_no;

// name: project_counts
CALL { MATCH (n:rcp_cat) RETURN count(n) AS recipe_categories }
CALL { MATCH (n:ingr) RETURN count(n) AS ingredients }
CALL { MATCH (n:rcp) RETURN count(n) AS recipes }
CALL { MATCH (n:rcp_step) RETURN count(n) AS recipe_steps }
CALL { MATCH ()-[r:RCP_IN_RECIPE_CATEGORY]->() RETURN count(r) AS recipe_category_links }
CALL { MATCH ()-[r:RCP_USES]->() RETURN count(r) AS uses_links }
CALL { MATCH ()-[r:RCP_HAS_STEP]->() RETURN count(r) AS step_links }
RETURN recipe_categories AS rcp_cat,
       ingredients AS ingr,
       recipes AS rcp,
       recipe_steps AS rcp_step,
       recipe_category_links AS RCP_IN_RECIPE_CATEGORY,
       uses_links AS RCP_USES,
       step_links AS RCP_HAS_STEP;

// name: category_errors
// 요리 분류 관계가 하나도 없는 레시피 수(rcp_cat_rel 기준 레시피당 1개 이상).
MATCH (r:rcp)
WHERE NOT (r)-[:RCP_IN_RECIPE_CATEGORY]->(:rcp_cat)
RETURN count(r) AS n;

// name: unlinked_recipe_count
MATCH (r:rcp)
WHERE NOT (r)-[:RCP_USES]->(:ingr)
RETURN count(r) AS n;

// name: step_link_errors
// 부모가 정확히 하나(같은 rcp_id의 rcp)가 아닌 조리 단계 수. 정상은 0.
MATCH (s:rcp_step)
OPTIONAL MATCH (r:rcp)-[:RCP_HAS_STEP]->(s)
WITH s, count(r) AS parents, count(CASE WHEN r.rcp_id = s.rcp_id THEN 1 END) AS owners
WHERE parents <> 1 OR owners <> 1
RETURN count(s) AS n;

// name: sample_recipe
MATCH (r:rcp {rcp_id: $id})
OPTIONAL MATCH (r)-[:RCP_USES]->(i:ingr)
RETURN r.rcp_seq AS rcp_seq, r.rcp_nm AS rcp_nm, count(i) AS ingredient_count;

// name: sample_ingredient
MATCH (i:ingr {ingr_id: $id})
OPTIONAL MATCH (r:rcp)-[:RCP_USES]->(i)
RETURN i.ingr_nm AS ingr_nm, count(r) AS recipe_count;
