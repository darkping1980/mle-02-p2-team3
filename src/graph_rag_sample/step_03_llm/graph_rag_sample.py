"""두 데이터베이스 계층을 비교 실행하는 GraphRagSample 메인 클래스."""

import argparse
import os
from pathlib import Path
import uuid
from urllib.parse import urlparse

from dotenv import load_dotenv
from neo4j import GraphDatabase, TrustCustomCAs

from common.neo4j_db_session import Neo4jDbSession
from common.postgres_db_session import PostgresDbSession
from graph_rag_sample.step_03_llm.graph_rag_sample_neo4j_repository import GraphRagSampleNeo4jRepository
from graph_rag_sample.step_03_llm.graph_rag_sample_postgres_repository import GraphRagSamplePostgresRepository
from graph_rag_sample.step_03_llm.graph_rag_sample_register_service import GraphRagSampleRegisterService
from graph_rag_sample.step_03_llm.graph_rag_sample_search_service import GraphRagSampleSearchService
from graph_rag_sample.step_03_llm.graph_rag_sample_llm_service import GraphRagSampleLlmService


SAMPLE_QUESTION = "What technologies does Project A use?"


class GraphRagSample:
    """Service에 작업을 요청하고 사람이 읽을 수 있는 결과를 출력한다.

    계층 구조: GraphRagSample → (Register/Search/Llm) Service → (Postgres/Neo4j) Repository
    → (PostgresDbSession/Neo4jDbSession) → (.sql/.cypher) Mapper → DB.
    Step 2에 ``llm_service`` 가 추가되어, 검색 결과를 근거로 답변을 생성하는 ``ask()`` 를 제공한다.
    """

    def __init__(
        self,
        register_service: GraphRagSampleRegisterService,
        search_service: GraphRagSampleSearchService,
        llm_service: GraphRagSampleLlmService,
    ):
        """메인 클래스는 Service만 알고 Repository와 Mapper는 직접 다루지 않는다."""
        self.register_service = register_service
        self.search_service = search_service
        self.llm_service = llm_service

    # region [샘플 실행]
    def run(self) -> dict:
        """PostgreSQL 네 가지 동작과 Neo4j 노드·관계 동작을 실행한다."""
        # 실행마다 고유한 test_run_id를 만들어 이번 실행 데이터만 등록·조회·삭제한다.
        test_run_id = f"graph-rag-sample-{uuid.uuid4()}"
        postgres_result = self.register_service.run_postgres_demo(
            self.search_service, test_run_id
        )
        neo4j_result = self.register_service.run_neo4j_demo(
            self.search_service, test_run_id
        )
        return {
            "test_run_id": test_run_id,
            "postgres": postgres_result,
            "neo4j": neo4j_result,
        }

    def ask(self, question: str) -> dict:
        """DB 검색과 테스트 데이터 정리가 끝난 다음 별도 LLM Service를 호출한다.

        Returns:
            ``{"retrieval": run() 결과, "llm": generate_answer() 결과}``.
        """
        # 검색 결과는 이미 메모리 dict로 받아 두었으므로, DB 데이터가 정리된 뒤에도 답변 생성에 사용할 수 있다.
        retrieval_result = self.run()
        answer_result = self.llm_service.generate_answer(question, retrieval_result)
        return {"retrieval": retrieval_result, "llm": answer_result}
    # endregion


# =========================================================
# 01. 연결과 객체 생성
# region [01. 연결과 객체 생성]
# =========================================================
def _create_neo4j_driver(uri: str, username: str, password: str):
    """Aura 인증서를 검증하는 공식 Neo4j Driver를 만든다."""
    scheme = urlparse(uri).scheme
    if scheme in ("neo4j+s", "bolt+s"):
        import certifi

        uri = uri.replace(f"{scheme}://", f"{scheme[:-2]}://", 1)
        return GraphDatabase.driver(
            uri,
            auth=(username, password),
            encrypted=True,
            trusted_certificates=TrustCustomCAs(certifi.where()),
        )
    return GraphDatabase.driver(uri, auth=(username, password))


def create_sample(use_openai: bool = False) -> tuple[GraphRagSample, object]:
    """환경설정부터 메인 클래스까지 의존 객체를 연결한다.

    Args:
        use_openai: True면 실제 OpenAI 모델을, False(기본)면 Mock 모델을 사용한다.

    Returns:
        ``(GraphRagSample, Neo4j Driver)``. Driver는 호출자가 사용 후 ``close()`` 해야 한다.

    Raises:
        RuntimeError: DB/Neo4j/OpenAI 필수 환경변수가 없는 경우.
    """
    # 생성자 주입으로 Session → Repository → Service → GraphRagSample을 조립한다(Step 2의 같은 함수 설명 참고).
    load_dotenv()
    # LLM 설정 오류를 DB 연결 생성 전에 확인해 열린 Driver를 남기지 않는다.
    llm_service = GraphRagSampleLlmService(use_openai=use_openai)
    database_url = os.getenv("DB_URL")
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_username = os.getenv("NEO4J_USERNAME")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    if not database_url:
        raise RuntimeError("DB_URL 환경변수가 필요합니다.")
    if not all((neo4j_uri, neo4j_username, neo4j_password)):
        raise RuntimeError("NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD 환경변수가 필요합니다.")

    # Driver는 Neo4j 연결 수명만 관리한다. Cypher는 Session과 Repository가 처리한다.
    driver = _create_neo4j_driver(neo4j_uri, neo4j_username, neo4j_password)
    mapper_root = Path(__file__).resolve().parent
    postgres_session = PostgresDbSession(
        mapper_root=mapper_root,
        camel_case_keys=False,
        sql_log_mode="none",
    )
    neo4j_session = Neo4jDbSession(
        mapper_root=mapper_root,
        driver=driver,
        database=os.getenv("NEO4J_DATABASE"),
    )

    postgres_repository = GraphRagSamplePostgresRepository(postgres_session)
    neo4j_repository = GraphRagSampleNeo4jRepository(neo4j_session)
    register_service = GraphRagSampleRegisterService(postgres_repository, neo4j_repository)
    search_service = GraphRagSampleSearchService(postgres_repository, neo4j_repository)
    return GraphRagSample(register_service, search_service, llm_service), driver
# endregion


# =========================================================
# 02. 실행 진입점
# region [02. 실행 진입점]
# =========================================================
def main() -> int:
    """Service를 호출하고 두 DB의 샘플 조회 및 정리 결과를 출력한다."""
    parser = argparse.ArgumentParser(description="GraphRAG Step 3: retrieval augmented answer")
    parser.add_argument("--run-db", action="store_true", help="실제 DB에 샘플 데이터를 씁니다")
    parser.add_argument("--use-openai", action="store_true", help="명시적으로 실제 OpenAI API를 호출합니다")
    args = parser.parse_args()
    if not args.run_db:
        if args.use_openai:
            parser.error("--use-openai는 DB 검색 결과를 만드는 --run-db와 함께 지정해야 합니다.")
        print("오프라인 모드: DB와 외부 API를 호출하지 않았습니다. 기본 LLM은 Mock입니다.")
        return 0

    sample, driver = create_sample(use_openai=args.use_openai)
    try:
        result = sample.ask(SAMPLE_QUESTION)
        retrieval = result["retrieval"]
        llm = result["llm"]
        print("Question:", llm["question"])
        print("Keyword results:", retrieval["postgres"]["keyword_rows"])
        print("Vector results:", retrieval["postgres"]["vector_rows"])
        print("Graph results:", retrieval["neo4j"]["relationships"])
        print("Context:\n", llm["context"])
        print("Prompt:\n", llm["prompt"])
        print("Answer:", llm["answer"])
        print("LLM mode:", llm["model_mode"])
        print("PostgreSQL rows remaining:", len(retrieval["postgres"]["remaining_general_rows"]) + len(retrieval["postgres"]["remaining_vector_rows"]))
        print("Neo4j nodes/relationships remaining:", retrieval["neo4j"]["remaining_nodes"], retrieval["neo4j"]["remaining_relationships"])
    finally:
        # finally는 중간에 오류가 나도 Driver 연결을 닫는다.
        driver.close()
        sample.search_service.postgres_repository.query_session.database_manager.close()
    return 0
# endregion


if __name__ == "__main__":
    raise SystemExit(main())
