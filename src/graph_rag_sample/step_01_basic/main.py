"""DB Session과 외부 Mapper를 직접 호출하는 가장 작은 실행 예제입니다.

Repository/Service 계층 없이 ``PostgresDbSession`` 과 ``Neo4jDbSession`` 을 바로 호출해
SQL mapper(``basic_sample.sql``)와 Cypher mapper(``basic_sample.cypher``)의 사용법을 보여 준다.

실행(README 참고):
    uv run python -m graph_rag_sample.step_01_basic.main            # 오프라인 안내만 출력
    uv run python -m graph_rag_sample.step_01_basic.main --run-db   # 실제 DB에 등록·조회·정리
"""

import argparse
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from neo4j import GraphDatabase, TrustCustomCAs
try:
    from pgvector import Vector  # pgvector >= 0.4
except ImportError:
    from pgvector.utils import Vector  # pgvector 0.3.x

from common.neo4j_db_session import Neo4jDbSession
from common.postgres_db_session import PostgresDbSession


# 예시 질문과 검색용 고정 벡터. 3차원 벡터는 실제 의미 embedding이 아니라 pgvector 거리 계산 실습용 좌표다.
SAMPLE_QUESTION = "What technologies does Project A use?"
SEARCH_VECTOR = [1.0, 0.0, 0.0]


# =========================================================
# 01. Neo4j 연결 설정
# =========================================================
# region [01. Neo4j 연결 설정]
def create_neo4j_driver(uri: str, username: str, password: str):
    """Neo4j Driver를 만든다. Driver는 연결 설정을 관리하고 쿼리는 Session이 실행한다."""
    # `neo4j+s://` / `bolt+s://`이면 "+s"를 떼고 암호화 + certifi CA 검증을 직접 지정한다.
    # (aura_test.create_driver()와 같은 방식이며, 인증서 검증은 끄지 않는다.)
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
# endregion


# =========================================================
# 02. 명시적인 DB 실습
# =========================================================
# region [02. 명시적인 DB 실습]
def run_database_sample() -> dict:
    """작은 테스트 데이터를 넣고 조회한 뒤 이번 실행 데이터만 삭제한다.

    Returns:
        단계별 조회 결과를 담은 dict(PostgreSQL 일반/벡터 조회, Neo4j 노드/관계 조회, 정리 후 잔여 건수).

    Raises:
        RuntimeError: DB_URL 또는 Neo4j 접속 환경변수가 없는 경우.
    """
    # 필수 환경변수를 먼저 확인한다.
    load_dotenv()
    database_url = os.getenv("DB_URL")
    neo4j_uri = os.getenv("NEO4J_URI")
    neo4j_username = os.getenv("NEO4J_USERNAME")
    neo4j_password = os.getenv("NEO4J_PASSWORD")
    if not database_url:
        raise RuntimeError("DB_URL 환경 변수가 필요합니다.")
    if not all((neo4j_uri, neo4j_username, neo4j_password)):
        raise RuntimeError("NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD가 필요합니다.")

    # Mapper 경로는 이 Python 파일의 위치를 기준으로 하므로 실행 CWD와 무관하다.
    mapper_root = Path(__file__).resolve().parent
    postgres = PostgresDbSession(mapper_root=mapper_root, sql_log_mode="none")
    driver = create_neo4j_driver(neo4j_uri, neo4j_username, neo4j_password)
    neo4j = Neo4jDbSession(
        mapper_root=mapper_root,
        driver=driver,
        database=os.getenv("NEO4J_DATABASE"),
    )
    test_run_id = f"step-01-{uuid.uuid4()}"
    project_name = f"Project A {test_run_id}"
    output = {"question": SAMPLE_QUESTION, "test_run_id": test_run_id}

    # region [DB 설명] 임시 테이블과 하나의 트랜잭션
    # basic_sample.sql의 테이블은 `CREATE TEMP TABLE ... ON COMMIT DROP`이라 트랜잭션이 끝나면 자동 삭제된다.
    # 트랜잭션 밖에서 execute()를 따로 부르면 호출마다 commit되어 다음 SQL에서 테이블이 이미 사라진다.
    # 그래서 생성 → 등록 → 조회 → 삭제를 `postgres.transaction()` 하나로 묶어 같은 연결에서 실행한다.
    # Neo4j 쪽도 `neo4j.transaction()` 하나로 묶어, 블록이 정상 종료되면 commit, 예외가 나면 rollback된다.
    # 두 DB의 트랜잭션은 서로 독립적이다(두 DB를 함께 묶는 분산 트랜잭션이 아님).
    # endregion
    try:
        # PostgreSQL 트랜잭션 하나로 묶어, ON COMMIT DROP 임시 테이블이 정리 단계까지 유지되게 한다.
        with postgres.transaction():
            postgres.execute("basic_sample.create_general_table")
            postgres.execute("basic_sample.create_vector_table")
            postgres.execute(
                "basic_sample.insert_general_item",
                {"test_run_id": test_run_id, "item_id": "python", "content": "Project A uses Python for application code."},
            )
            postgres.execute(
                "basic_sample.insert_general_item",
                {"test_run_id": test_run_id, "item_id": "neo4j", "content": "Project A uses Neo4j to store technology relationships."},
            )
            output["postgres_general"] = postgres.select_list(
                "basic_sample.find_general_items", {"test_run_id": test_run_id}
            )
            postgres.execute(
                "basic_sample.insert_vector_item",
                {"test_run_id": test_run_id, "item_id": "python", "item_name": "Python", "embedding": Vector([1.0, 0.0, 0.0])},
            )
            postgres.execute(
                "basic_sample.insert_vector_item",
                {"test_run_id": test_run_id, "item_id": "neo4j", "item_name": "Neo4j", "embedding": Vector([0.8, 0.2, 0.0])},
            )
            output["postgres_vectors"] = postgres.select_list(
                "basic_sample.find_similar_vectors",
                {"test_run_id": test_run_id, "query_embedding": Vector(SEARCH_VECTOR), "limit": 3},
            )
            postgres.execute("basic_sample.delete_general_items", {"test_run_id": test_run_id})
            postgres.execute("basic_sample.delete_vector_items", {"test_run_id": test_run_id})
            output["postgres_remaining_general"] = postgres.select_list(
                "basic_sample.find_general_items", {"test_run_id": test_run_id}
            )
            output["postgres_remaining_vectors"] = postgres.select_list(
                "basic_sample.find_similar_vectors",
                {"test_run_id": test_run_id, "query_embedding": Vector(SEARCH_VECTOR), "limit": 3},
            )

        # Neo4jDbSession.transaction()은 정상 종료 시 commit, 오류 시 rollback한다.
        # 노드 생성 → 관계 생성 → 조회 → 이번 test_run_id 그래프 삭제 → 잔여 건수 확인 순서로 실행한다.
        with neo4j.transaction():
            neo4j.execute("basic_sample.create_project", {"test_run_id": test_run_id, "project_name": project_name})
            for technology in ("Python", "Neo4j"):
                neo4j.execute("basic_sample.create_technology", {"test_run_id": test_run_id, "technology_name": technology})
                neo4j.execute("basic_sample.create_technology_relationship", {"test_run_id": test_run_id, "project_name": project_name, "technology_name": technology})
            output["neo4j_project"] = neo4j.select_one(
                "basic_sample.find_project", {"test_run_id": test_run_id, "project_name": project_name}
            )
            output["neo4j_relationships"] = neo4j.select_list(
                "basic_sample.find_relationships", {"test_run_id": test_run_id, "project_name": project_name}
            )
            neo4j.execute("basic_sample.delete_test_graph", {"test_run_id": test_run_id})
            output["neo4j_remaining_nodes"] = neo4j.select_one(
                "basic_sample.count_test_nodes", {"test_run_id": test_run_id}
            )["count"]
            output["neo4j_remaining_relationships"] = neo4j.select_one(
                "basic_sample.count_test_relationships", {"test_run_id": test_run_id}
            )["count"]
        return output
    # 성공·실패와 관계없이 이 함수가 만든 Neo4j Driver와 PostgreSQL pool을 닫는다(자원 소유자가 정리).
    finally:
        driver.close()
        postgres.database_manager.close()
# endregion


# =========================================================
# 03. 실행 진입점
# =========================================================
# region [03. 실행 진입점]
def main() -> int:
    """기본은 연결 없이 도움말을 보이고, --run-db가 있을 때만 DB에 쓴다."""
    # region [Python 설명] argparse와 SystemExit
    # `argparse`는 명령줄 인자를 정의하고 해석한다. `action="store_true"`는 옵션이 있으면 True, 없으면 False다.
    # `args.run_db`처럼 옵션 이름의 `-`는 `_`로 바뀐 속성으로 읽는다.
    # 아래 `raise SystemExit(main())`은 main()의 반환값(0 등)을 프로세스 종료 코드로 사용한다.
    # endregion
    parser = argparse.ArgumentParser(description="GraphRAG Step 1: direct DB Session calls")
    parser.add_argument("--run-db", action="store_true", help="실제 DB에 샘플을 등록·조회·정리합니다")
    args = parser.parse_args()
    if not args.run_db:
        print("오프라인 모드: DB 쓰기는 실행하지 않았습니다.")
        print("실제 실습은 --run-db 옵션과 DB 환경 변수를 함께 지정하세요.")
        print(f"예시 질문: {SAMPLE_QUESTION}")
        print("고정 벡터는 의미 임베딩이 아닌 pgvector 실습용 좌표입니다.")
        return 0

    result = run_database_sample()
    for section, value in result.items():
        print(f"{section}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# endregion
