// =========================================================
// Step 1 Neo4j 실습 mapper (namespace: basic_sample)
// =========================================================
// 설명 주석은 첫 statement 선언 앞(이 머리 부분)에만 둔다. 선언 뒤 주석은 Cypher 텍스트에 포함된다.
//
// 그래프 모델
//   (:GraphRagSampleProject {test_run_id, name})
//       -[:USES_TECHNOLOGY {test_run_id}]->
//   (:GraphRagSampleTechnology {test_run_id, name})
//   모든 노드와 관계에 test_run_id를 넣어 이번 실행 데이터만 조회·삭제한다.
//
// statement 요약
//   create_project, create_technology : 노드 CREATE 후 이름을 RETURN
//   create_technology_relationship    : 두 노드를 MATCH한 뒤 방향 관계를 CREATE
//   find_project, find_relationships  : 노드/관계 조회. type(relationship)은 관계 type 이름 문자열을 반환
//   delete_test_graph                 : test_run_id가 같은 노드를 DETACH DELETE(연결 관계도 함께 삭제)
//   count_test_nodes, count_test_relationships : 정리 후 잔여 건수 확인

// name: create_project
CREATE (project:GraphRagSampleProject {
    test_run_id: $test_run_id,
    name: $project_name
})
RETURN project.name AS project

// name: create_technology
CREATE (technology:GraphRagSampleTechnology {
    test_run_id: $test_run_id,
    name: $technology_name
})
RETURN technology.name AS technology

// name: create_technology_relationship
MATCH (project:GraphRagSampleProject {test_run_id: $test_run_id, name: $project_name})
MATCH (technology:GraphRagSampleTechnology {test_run_id: $test_run_id, name: $technology_name})
CREATE (project)-[:USES_TECHNOLOGY {test_run_id: $test_run_id}]->(technology)
RETURN project.name AS project, technology.name AS technology

// name: find_project
MATCH (project:GraphRagSampleProject {test_run_id: $test_run_id, name: $project_name})
RETURN project.name AS project

// name: find_relationships
MATCH (project:GraphRagSampleProject {test_run_id: $test_run_id, name: $project_name})
      -[relationship:USES_TECHNOLOGY {test_run_id: $test_run_id}]->
      (technology:GraphRagSampleTechnology {test_run_id: $test_run_id})
RETURN project.name AS project,
       type(relationship) AS relationship,
       technology.name AS technology
ORDER BY technology

// name: delete_test_graph
MATCH (node)
WHERE node.test_run_id = $test_run_id
DETACH DELETE node

// name: count_test_nodes
MATCH (node)
WHERE node.test_run_id = $test_run_id
RETURN count(node) AS count

// name: count_test_relationships
MATCH ()-[relationship:USES_TECHNOLOGY {test_run_id: $test_run_id}]->()
RETURN count(relationship) AS count
