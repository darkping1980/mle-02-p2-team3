// =========================================================
// GraphRAG 샘플 Neo4j mapper (namespace: graph_rag_sample, Step 2/3 공통 내용)
// =========================================================
// Python 호출: GraphRagSampleNeo4jRepository
// 설명 주석은 첫 statement 선언 앞(이 머리 부분)에만 둔다. 선언 뒤 주석은 Cypher 텍스트에 포함된다.
//
// 그래프 모델
//   (:GraphRagSampleProject {test_run_id, name})
//       -[:USES_TECHNOLOGY {test_run_id}]->
//   (:GraphRagSampleTechnology {test_run_id, name, description})
//
// GraphRAG에서의 역할
//   find_technologies는 질문의 대상 프로젝트에서 관계를 따라가 연결된 기술과 설명을 가져온다.
//   이 그래프 조회 결과가 PostgreSQL 키워드/벡터 검색 결과와 함께 답변 근거(context)가 된다.
//
// 정리용 statement
//   delete_test_graph는 test_run_id가 같은 노드를 DETACH DELETE(연결 관계 포함)하고,
//   count_test_nodes / count_test_relationships로 잔여 데이터가 없는지 확인한다.

// name: create_project
CREATE (project:GraphRagSampleProject {
    test_run_id: $test_run_id,
    name: $project_name
})
RETURN project.name AS project

// name: create_technology
CREATE (technology:GraphRagSampleTechnology {
    test_run_id: $test_run_id,
    name: $technology_name,
    description: $description
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

// name: find_technologies
MATCH (project:GraphRagSampleProject {test_run_id: $test_run_id, name: $project_name})
      -[:USES_TECHNOLOGY {test_run_id: $test_run_id}]->
      (technology:GraphRagSampleTechnology {test_run_id: $test_run_id})
RETURN project.name AS project,
       technology.name AS technology,
       technology.description AS description
ORDER BY technology

// name: find_relationships
MATCH (project:GraphRagSampleProject {test_run_id: $test_run_id, name: $project_name})
      -[relationship:USES_TECHNOLOGY {test_run_id: $test_run_id}]->
      (technology:GraphRagSampleTechnology {test_run_id: $test_run_id})
RETURN project.name AS from_project,
       type(relationship) AS relationship,
       technology.name AS to_technology
ORDER BY to_technology

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
