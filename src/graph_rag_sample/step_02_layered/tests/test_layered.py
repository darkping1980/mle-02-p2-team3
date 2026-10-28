"""Repository와 Service 계층의 Mock 테스트."""

import os
from pathlib import Path
import unittest
from unittest.mock import Mock

from common.neo4j_db_session import Neo4jDbSession
from common.postgres_db_session import PostgresDbSession
from graph_rag_sample.step_02_layered.graph_rag_sample_neo4j_repository import GraphRagSampleNeo4jRepository
from graph_rag_sample.step_02_layered.graph_rag_sample_postgres_repository import GraphRagSamplePostgresRepository
from graph_rag_sample.step_02_layered.graph_rag_sample_search_service import GraphRagSampleSearchService


# region [Python 설명] unittest.mock.Mock과 call_args_list
# `Mock()`은 어떤 메서드를 호출해도 오류 없이 기록만 남기는 가짜 객체다(Mockito의 mock과 비슷).
# Repository에 가짜 세션을 넣으면 실제 DB 없이 "어떤 statement ID로 호출했는지"만 검사할 수 있다.
# `session.execute.call_args_list`는 execute 호출 기록 목록이고, `call.args[0]`은 첫 번째 위치 인자다.
# `mock.method.return_value = [...]`로 가짜 반환값을 정해 두면 Service 로직만 따로 검증할 수 있다.
# endregion
class GraphRagSampleTests(unittest.TestCase):
    """Mapper 경로와 Repository 위임 동작을 확인한다."""

    def test_mapper_root_is_required_for_each_db_session(self):
        """두 Session 모두 keyword 전용 필수 인자 mapper_root 없이 만들 수 없다."""
        with self.assertRaises(TypeError):
            PostgresDbSession()
        with self.assertRaises(TypeError):
            Neo4jDbSession()

    # region [Mapper 경로 분리]
    def test_sql_mapper_is_loaded_only_from_sample_folder(self):
        """Step 2 폴더의 graph_rag_sample SQL mapper만 등록된다."""
        mapper_root = Path(__file__).resolve().parents[1]
        session = PostgresDbSession(mapper_root=mapper_root, sql_log_mode="none")
        self.assertEqual(set(session.mappers), {"graph_rag_sample"})
        self.assertTrue(session._query("graph_rag_sample.find_similar_vectors"))

    def test_cypher_mapper_is_loaded_only_from_sample_folder(self):
        """Step 2 폴더의 Cypher statement 9개가 등록된다."""
        mapper_root = Path(__file__).resolve().parents[1]
        session = Neo4jDbSession(mapper_root=mapper_root)
        self.assertEqual(len(session.mappers), 9)
        self.assertIn("graph_rag_sample.find_relationships", session.mappers)
    # endregion

    # region [Repository의 QuerySession 위임]
    def test_postgres_repository_uses_sql_mapper_for_normal_and_vector_queries(self):
        """PostgreSQL Repository가 변경은 execute, 조회는 select_list로 올바른 statement ID를 호출한다."""
        session = Mock()
        repository = GraphRagSamplePostgresRepository(session)
        repository.register_general_item("run-1", "sample")
        repository.register_vector("run-1", "Python", [1.0, 0.0, 0.0])
        repository.find_general_items("run-1")
        repository.find_keyword_items("run-1", "sample")
        repository.find_similar_vectors("run-1", [1.0, 0.0, 0.0])
        self.assertEqual(
            [call.args[0] for call in session.execute.call_args_list],
            ["graph_rag_sample.insert_general_item", "graph_rag_sample.insert_vector_item"],
        )
        self.assertEqual(
            [call.args[0] for call in session.select_list.call_args_list],
            ["graph_rag_sample.find_general_items", "graph_rag_sample.find_keyword_items", "graph_rag_sample.find_similar_vectors"],
        )

    def test_search_service_hybrid_keeps_keyword_first_and_deduplicates_item_id(self):
        """Hybrid 병합은 keyword 결과를 앞에 두고, 같은 item_id는 처음 나온 것만 남긴다."""
        postgres = Mock()
        postgres.find_keyword_items.return_value = [
            {"item_id": "python", "content": "Python text"},
            {"item_id": "shared", "content": "Keyword text"},
        ]
        postgres.find_similar_vectors.return_value = [
            {"item_id": "shared", "item_name": "Shared"},
            {"item_id": "neo4j", "item_name": "Neo4j"},
        ]
        service = GraphRagSampleSearchService(postgres, Mock())

        results = service.search_postgres_hybrid("run-1", "Project", [1.0, 0.0, 0.0])

        self.assertEqual([row["item_id"] for row in results], ["python", "shared", "neo4j"])
        self.assertEqual([row["source"] for row in results], ["keyword", "keyword", "vector"])

    def test_neo4j_repository_uses_named_cypher_queries_for_nodes_and_relationships(self):
        """Neo4j Repository가 노드·관계 등록과 조회에 올바른 Cypher statement ID를 사용한다."""
        session = Mock()
        repository = GraphRagSampleNeo4jRepository(session)
        repository.create_project("run-1", "Project")
        repository.create_technology("run-1", "Neo4j", "Graph database")
        repository.connect_technology("run-1", "Project", "Neo4j")
        repository.find_project("run-1", "Project")
        repository.find_relationships("run-1", "Project")
        self.assertEqual(
            [call.args[0] for call in session.execute.call_args_list],
            ["graph_rag_sample.create_project", "graph_rag_sample.create_technology",
             "graph_rag_sample.create_technology_relationship"],
        )
        self.assertEqual(session.select_one.call_args.args[0], "graph_rag_sample.find_project")
        self.assertEqual(session.select_list.call_args.args[0], "graph_rag_sample.find_relationships")
    # endregion

    # region [실제 DB 통합 테스트]
    # `@unittest.skipUnless(조건, 사유)`는 조건이 거짓이면 테스트를 건너뛴다(skip으로 표시).
    # 환경변수 RUN_GRAPH_RAG_SAMPLE_INTEGRATION=1을 명시한 경우에만 실제 두 DB에 쓰는 테스트를 실행한다.
    @unittest.skipUnless(os.getenv("RUN_GRAPH_RAG_SAMPLE_INTEGRATION") == "1", "explicit two-database integration opt-in")
    def test_complete_postgres_pgvector_and_aura_lifecycle(self):
        """실제 DB에서 네 기능을 실행하고 실행 ID 데이터가 남지 않는지 확인한다."""
        from graph_rag_sample.step_02_layered.graph_rag_sample import create_sample

        sample, driver = create_sample()
        try:
            result = sample.run()
            self.assertEqual(len(result["postgres"]["general_rows"]), 2)
            self.assertEqual(len(result["postgres"]["keyword_rows"]), 1)
            self.assertEqual(len(result["postgres"]["vector_rows"]), 2)
            self.assertEqual(len(result["neo4j"]["technologies"]), 2)
            self.assertEqual(len(result["neo4j"]["relationships"]), 2)
            self.assertEqual(result["postgres"]["remaining_general_rows"], [])
            self.assertEqual(result["postgres"]["remaining_vector_rows"], [])
            self.assertEqual(
                (result["neo4j"]["remaining_nodes"], result["neo4j"]["remaining_relationships"]),
                (0, 0),
            )
        finally:
            driver.close()
            sample.search_service.postgres_repository.query_session.database_manager.close()
    # endregion


if __name__ == "__main__":
    unittest.main()
