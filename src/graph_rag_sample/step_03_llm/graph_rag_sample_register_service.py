"""초보자용 등록, 트랜잭션, 정리 흐름을 맡는 Service."""

from graph_rag_sample.step_03_llm.graph_rag_sample_neo4j_repository import GraphRagSampleNeo4jRepository
from graph_rag_sample.step_03_llm.graph_rag_sample_postgres_repository import GraphRagSamplePostgresRepository
from graph_rag_sample.step_03_llm.graph_rag_sample_search_service import GraphRagSampleSearchService


class GraphRagSampleRegisterService:
    """샘플 행·벡터·노드·관계를 트랜잭션 안에서 등록하고 정리한다.

    트랜잭션 경계(``with ...query_session.transaction():``)는 이 Service가 정한다.
    Repository는 SQL/Cypher 호출만 하고, 어떤 호출을 한 트랜잭션으로 묶을지는 Service 책임이다
    (Spring의 @Transactional Service와 같은 역할 분담). 조회는 ``search_service`` 에 위임한다.
    """

    def __init__(
        self,
        postgres_repository: GraphRagSamplePostgresRepository,
        neo4j_repository: GraphRagSampleNeo4jRepository,
    ):
        """두 Repository를 전달받아 DB별 등록 흐름을 준비한다."""
        self.postgres_repository = postgres_repository
        self.neo4j_repository = neo4j_repository

    # region [PostgreSQL 임시 데이터 등록, 조회, 삭제]
    def run_postgres_demo(
        self, search_service: GraphRagSampleSearchService, test_run_id: str
    ) -> dict:
        """한 트랜잭션 안에서 일반 행과 벡터를 등록·조회·삭제한다.

        Returns:
            일반/키워드/벡터/Hybrid 조회 결과와 삭제 후 잔여 행 목록을 담은 dict.
        """
        result = {}
        # Session의 transaction()은 이 블록의 쿼리를 한 연결에서 실행하고 끝에 Commit한다.
        # (블록 안에서 예외가 나면 Rollback하고 예외를 그대로 전파한다.)
        with self.postgres_repository.query_session.transaction():
            self.postgres_repository.create_demo_tables()
            self.postgres_repository.register_general_item(
                test_run_id,
                "Project A uses Python for application code.",
                item_id="python",
            )
            self.postgres_repository.register_general_item(
                test_run_id,
                "Project A uses Neo4j to store technology relationships.",
                item_id="neo4j",
            )
            general_rows = search_service.search_postgres_general(test_run_id)
            keyword_rows = search_service.search_postgres_keyword(test_run_id, "Python")

            # 세 숫자로 된 작은 벡터를 써서 pgvector 거리 정렬을 보여준다.
            self.postgres_repository.register_vector(
                test_run_id, "Python", [1.0, 0.0, 0.0], item_id="python"
            )
            self.postgres_repository.register_vector(
                test_run_id, "Neo4j", [0.8, 0.2, 0.0], item_id="neo4j"
            )
            vector_rows = search_service.search_postgres_vectors(
                test_run_id, [1.0, 0.0, 0.0]
            )
            hybrid_rows = search_service.search_postgres_hybrid(
                test_run_id, "Python", [1.0, 0.0, 0.0]
            )

            # 삭제 대상을 test_run_id로 제한하고 삭제 결과가 비었는지 다시 확인한다.
            self.postgres_repository.delete_general_items(test_run_id)
            self.postgres_repository.delete_vectors(test_run_id)
            result = {
                "general_rows": general_rows,
                "keyword_rows": keyword_rows,
                "vector_rows": vector_rows,
                "hybrid_rows": hybrid_rows,
                "remaining_general_rows": search_service.search_postgres_general(test_run_id),
                "remaining_vector_rows": search_service.search_postgres_vectors(
                    test_run_id, [1.0, 0.0, 0.0]
                ),
            }
        # 임시 테이블은 ON COMMIT DROP 설정이라 위 트랜잭션이 commit되는 시점에 제거된다.
        return result
    # endregion

    # region [Neo4j 노드·관계 등록, 조회, 삭제]
    def run_neo4j_demo(
        self, search_service: GraphRagSampleSearchService, test_run_id: str
    ) -> dict:
        """노드 3개와 관계 2개를 등록·조회한 뒤 같은 실행 데이터만 삭제한다.

        Returns:
            프로젝트/기술/관계 조회 결과와 삭제 후 잔여 노드·관계 수를 담은 dict.
        """
        # 등록 → 조회 → 삭제 → 잔여 확인을 하나의 Neo4j 트랜잭션에서 실행하므로,
        # commit 시점에는 이번 실행 데이터가 이미 삭제된 상태다(다른 세션에는 등록 데이터가 보이지 않는다).
        project_name = f"Project A {test_run_id}"
        result = {}
        with self.neo4j_repository.query_session.transaction():
            self.neo4j_repository.create_project(test_run_id, project_name)
            self.neo4j_repository.create_technology(test_run_id, "Python", "애플리케이션 언어")
            self.neo4j_repository.create_technology(test_run_id, "Neo4j", "그래프 데이터베이스")
            self.neo4j_repository.connect_technology(test_run_id, project_name, "Python")
            self.neo4j_repository.connect_technology(test_run_id, project_name, "Neo4j")

            project = search_service.search_neo4j_project(test_run_id, project_name)
            technologies = search_service.search_neo4j_technologies(test_run_id, project_name)
            relationships = search_service.search_neo4j_relationships(test_run_id, project_name)
            self.neo4j_repository.delete_test_graph(test_run_id)
            result = {
                "project": project,
                "technologies": technologies,
                "relationships": relationships,
                "remaining_nodes": self.neo4j_repository.count_test_nodes(test_run_id),
                "remaining_relationships": self.neo4j_repository.count_test_relationships(test_run_id),
            }
        return result
    # endregion
