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
from graph_rag_sample.step_02_layered.graph_rag_sample_neo4j_repository import GraphRagSampleNeo4jRepository
from graph_rag_sample.step_02_layered.graph_rag_sample_postgres_repository import GraphRagSamplePostgresRepository
from graph_rag_sample.step_02_layered.graph_rag_sample_register_service import GraphRagSampleRegisterService
from graph_rag_sample.step_02_layered.graph_rag_sample_search_service import GraphRagSampleSearchService


class GraphRagSample:
    """Service에 작업을 요청하고 사람이 읽을 수 있는 결과를 출력한다.

    계층 구조: GraphRagSample → (Register/Search) Service → (Postgres/Neo4j) Repository
    → (PostgresDbSession/Neo4jDbSession) → (.sql/.cypher) Mapper → DB.
    각 계층은 바로 아래 계층만 알고, 객체 연결은 ``create_sample()`` 이 한곳에서 담당한다.
    """

    def __init__(
        self,
        register_service: GraphRagSampleRegisterService,
        search_service: GraphRagSampleSearchService,
    ):
        """메인 클래스는 Service만 알고 Repository와 Mapper는 직접 다루지 않는다."""
        self.register_service = register_service
        self.search_service = search_service

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


def create_sample() -> tuple[GraphRagSample, object]:
    """환경설정부터 메인 클래스까지 의존 객체를 연결한다.

    Returns:
        ``(GraphRagSample, Neo4j Driver)``. Driver는 호출자가 사용 후 ``close()`` 해야 한다.

    Raises:
        RuntimeError: DB_URL 또는 Neo4j 접속 환경변수가 없는 경우.
    """
    # region [Python 설명] 생성자 주입으로 객체 조립
    # 각 클래스는 필요한 객체를 직접 만들지 않고 생성자 인자로 받는다.
    # 이 함수가 Session → Repository → Service → GraphRagSample 순으로 만들어 넘겨 준다.
    # Spring 같은 DI 컨테이너 없이 Python 코드로 직접 조립하는 방식이며, 테스트에서는 가짜 객체를 넣을 수 있다.
    # `camel_case_keys=False`이므로 PostgreSQL 결과 key는 SQL 컬럼명 그대로(item_id 등)다.
    # endregion
    load_dotenv()
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
    return GraphRagSample(register_service, search_service), driver
# endregion


# =========================================================
# 02. 실행 진입점
# region [02. 실행 진입점]
# =========================================================
def main() -> int:
    """Service를 호출하고 두 DB의 샘플 조회 및 정리 결과를 출력한다."""
    parser = argparse.ArgumentParser(description="GraphRAG Step 2: layered DB sample")
    parser.add_argument("--run-db", action="store_true", help="실제 DB에 샘플 데이터를 씁니다")
    if not parser.parse_args().run_db:
        print("오프라인 모드: DB 쓰기는 실행하지 않았습니다. 실제 실습에는 --run-db를 지정하세요.")
        return 0

    sample, driver = create_sample()
    try:
        result = sample.run()
        postgres = result["postgres"]
        neo4j = result["neo4j"]
        print(f"test_run_id: {result['test_run_id']}")
        print("PostgreSQL 일반 조회:", postgres["general_rows"])
        print("PostgreSQL pgvector 유사도 조회:", postgres["vector_rows"])
        print("PostgreSQL 키워드 조회:", postgres["keyword_rows"])
        print("PostgreSQL 단순 Hybrid 조회:", postgres["hybrid_rows"])
        print(
            "PostgreSQL 삭제 후 잔여 행:",
            len(postgres["remaining_general_rows"]) + len(postgres["remaining_vector_rows"]),
        )
        print("Neo4j 프로젝트 조회:", neo4j["project"])
        print("Neo4j 기술 노드 조회:", neo4j["technologies"])
        print("Neo4j 관계 조회:", neo4j["relationships"])
        print(
            "Neo4j 삭제 후 잔여 노드/관계:",
            neo4j["remaining_nodes"],
            neo4j["remaining_relationships"],
        )
    finally:
        # finally는 중간에 오류가 나도 Driver 연결을 닫는다.
        driver.close()
        sample.search_service.postgres_repository.query_session.database_manager.close()
    return 0
# endregion


if __name__ == "__main__":
    raise SystemExit(main())
