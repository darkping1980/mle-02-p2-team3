"""Repository와 Service 계층의 Mock 테스트."""

import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from common.neo4j_db_session import Neo4jDbSession
from common.postgres_db_session import PostgresDbSession
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from graph_rag_sample.step_03_llm.graph_rag_sample import GraphRagSample
from graph_rag_sample.step_03_llm.graph_rag_sample_llm_service import GraphRagSampleLlmService
from graph_rag_sample.step_03_llm.graph_rag_sample_neo4j_repository import GraphRagSampleNeo4jRepository
from graph_rag_sample.step_03_llm.graph_rag_sample_postgres_repository import GraphRagSamplePostgresRepository
from graph_rag_sample.step_03_llm.graph_rag_sample_search_service import GraphRagSampleSearchService


# Mock, call_args_list, skipUnless 사용법은 step_02_layered/tests/test_layered.py 상단 설명과 같다.
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
        """Step 3 폴더의 graph_rag_sample SQL mapper만 등록된다."""
        mapper_root = Path(__file__).resolve().parents[1]
        session = PostgresDbSession(mapper_root=mapper_root, sql_log_mode="none")
        self.assertEqual(set(session.mappers), {"graph_rag_sample"})
        self.assertTrue(session._query("graph_rag_sample.find_similar_vectors"))

    def test_cypher_mapper_is_loaded_only_from_sample_folder(self):
        """Step 3 폴더의 Cypher statement 9개가 등록된다."""
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

    def test_llm_service_builds_cited_context_prompt_and_uses_injected_mock(self):
        """세 검색 경로의 출처 제목이 Context에 들어가고, 주입한 가짜 모델의 답변이 그대로 반환된다."""
        # lambda를 RunnableLambda로 감싸 항상 같은 AIMessage를 돌려주는 가짜 chat model을 만든다.
        model = RunnableLambda(lambda prompt_value: AIMessage(content="Mock test answer"))
        service = GraphRagSampleLlmService(chat_model=model)
        search_results = {
            "postgres": {
                "keyword_rows": [{"content": "Project A uses Python."}],
                "vector_rows": [{"item_name": "Python", "similarity": 1.0}],
            },
            "neo4j": {
                "relationships": [
                    {"project": "Project A", "relationship": "USES_TECHNOLOGY", "to_technology": "Python"}
                ]
            },
        }

        result = service.generate_answer("What does Project A use?", search_results)

        self.assertIn("[PostgreSQL - Keyword]", result["context"])
        self.assertIn("[PostgreSQL - Vector]", result["context"])
        self.assertIn("[Neo4j - Graph]", result["context"])
        self.assertIn("Context", result["prompt"])
        self.assertEqual(result["answer"], "Mock test answer")
        self.assertEqual(result["model_mode"], "injected")

    def test_empty_search_results_produce_no_evidence_prompt_and_safe_mock_answer(self):
        """검색 결과가 없으면 "No retrieved evidence." Context와 근거 없음 답변을 만든다."""
        service = GraphRagSampleLlmService()

        result = service.generate_answer("Unknown question", {})

        self.assertEqual(result["context"], "No retrieved evidence.")
        self.assertIn("추측하지 마세요", result["prompt"])
        self.assertIn("근거가 없어", result["answer"])
        self.assertEqual(result["model_mode"], "mock")

    def test_default_mock_answer_mentions_only_technologies_in_retrieved_context(self):
        """기본 Mock 답변은 검색 근거에 실제로 있는 기술 이름만 언급한다."""
        service = GraphRagSampleLlmService()
        search_results = {
            "postgres": {"keyword_rows": [], "vector_rows": []},
            "neo4j": {
                "relationships": [
                    {"project": "Project A", "relationship": "USES", "to_technology": "Python"}
                ]
            },
        }

        result = service.generate_answer("What does the project use?", search_results)

        self.assertIn("Python", result["answer"])
        self.assertNotIn("Neo4j", result["answer"])

    def test_openai_mode_requires_api_key_but_default_mode_never_needs_it(self):
        """API key가 없어도 Mock 모드는 생성되고, OpenAI 모드는 RuntimeError를 낸다."""
        # `patch.dict(os.environ, {}, clear=True)`는 with 블록 동안 환경변수를 모두 비웠다가 끝나면 복원한다.
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(GraphRagSampleLlmService().model_mode, "mock")
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                GraphRagSampleLlmService(use_openai=True)

    def test_graph_rag_main_runs_search_before_calling_llm(self):
        """ask()는 두 DB 작업이 끝난 뒤에 LLM Service를 호출한다(호출 순서 검증)."""
        # 함수 안에 필요한 메서드만 가진 작은 가짜 클래스를 정의해 실제 Service 대신 넣는다(duck typing).
        # 각 가짜 메서드가 바깥 list `execution`에 기록을 남겨 호출 순서를 확인한다.
        execution = []

        class RegisterService:
            def run_postgres_demo(self, search_service, test_run_id):
                execution.append("postgres-transaction-finished")
                return {}

            def run_neo4j_demo(self, search_service, test_run_id):
                execution.append("neo4j-transaction-finished")
                return {}

        class LlmService:
            def generate_answer(self, question, search_results):
                self.assertions = execution[:]
                execution.append("llm-called")
                return {"answer": "done"}

        sample = GraphRagSample(RegisterService(), Mock(), LlmService())
        result = sample.ask("test question")

        self.assertEqual(result["llm"]["answer"], "done")
        self.assertEqual(execution, ["postgres-transaction-finished", "neo4j-transaction-finished", "llm-called"])

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
    # RUN_GRAPH_RAG_SAMPLE_INTEGRATION=1을 명시한 경우에만 실제 두 DB에 쓰는 테스트를 실행한다.
    @unittest.skipUnless(os.getenv("RUN_GRAPH_RAG_SAMPLE_INTEGRATION") == "1", "explicit two-database integration opt-in")
    def test_complete_postgres_pgvector_and_aura_lifecycle(self):
        """실제 DB에서 네 기능을 실행하고 실행 ID 데이터가 남지 않는지 확인한다."""
        from graph_rag_sample.step_03_llm.graph_rag_sample import create_sample

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
