"""Neo4j 샘플 노드와 관계를 접근하는 Repository."""

from common.query_session import QuerySession


class GraphRagSampleNeo4jRepository:
    """Cypher Mapper와 QuerySession 메서드만 사용해 그래프를 다룬다.

    PostgreSQL Repository와 같은 ``QuerySession`` 메서드 이름(select_one/select_list/execute)을 사용하지만,
    전달되는 statement는 ``graph_rag_sample.cypher`` 의 Cypher다. 쿼리 언어 차이는 세션 구현이 감춘다.
    """

    def __init__(self, query_session: QuerySession):
        """Cypher를 실행할 공통 QuerySession을 전달받는다."""
        self.query_session = query_session

    # region [노드 등록]
    def create_project(self, test_run_id: str, project_name: str) -> list[dict]:
        """실행 ID로 격리된 프로젝트 노드를 등록한다."""
        return self.query_session.execute(
            "graph_rag_sample.create_project",
            {"test_run_id": test_run_id, "project_name": project_name},
        )

    def create_technology(self, test_run_id: str, name: str, description: str) -> list[dict]:
        """실행 ID로 격리된 기술 노드를 등록한다."""
        return self.query_session.execute(
            "graph_rag_sample.create_technology",
            {"test_run_id": test_run_id, "technology_name": name, "description": description},
        )
    # endregion

    # region [관계 등록과 조회]
    def connect_technology(self, test_run_id: str, project_name: str, technology_name: str):
        """프로젝트와 기술 사이에 USES_TECHNOLOGY 관계를 등록한다."""
        return self.query_session.execute(
            "graph_rag_sample.create_technology_relationship",
            {
                "test_run_id": test_run_id,
                "project_name": project_name,
                "technology_name": technology_name,
            },
        )

    def find_project(self, test_run_id: str, project_name: str) -> dict | None:
        """실행 ID와 이름이 일치하는 프로젝트 노드를 하나 조회한다."""
        return self.query_session.select_one(
            "graph_rag_sample.find_project",
            {"test_run_id": test_run_id, "project_name": project_name},
        )

    def find_technologies(self, test_run_id: str, project_name: str) -> list[dict]:
        """프로젝트와 연결된 기술 및 설명을 조회한다."""
        return self.query_session.select_list(
            "graph_rag_sample.find_technologies",
            {"test_run_id": test_run_id, "project_name": project_name},
        )

    def find_relationships(self, test_run_id: str, project_name: str) -> list[dict]:
        """프로젝트에서 나가는 관계의 시작·종료 노드를 조회한다."""
        return self.query_session.select_list(
            "graph_rag_sample.find_relationships",
            {"test_run_id": test_run_id, "project_name": project_name},
        )
    # endregion

    # region [테스트 데이터 정리]
    def delete_test_graph(self, test_run_id: str):
        """현재 실행 ID가 표시된 노드와 연결 관계만 삭제한다."""
        return self.query_session.execute(
            "graph_rag_sample.delete_test_graph", {"test_run_id": test_run_id}
        )

    def count_test_nodes(self, test_run_id: str) -> int:
        """실행 ID가 남아 있는 노드 수를 확인한다."""
        # count() 집계는 보통 한 행을 돌려주지만, 결과가 없을 때(None)도 0으로 처리한다.
        row = self.query_session.select_one(
            "graph_rag_sample.count_test_nodes", {"test_run_id": test_run_id}
        )
        return int(row["count"] if row else 0)

    def count_test_relationships(self, test_run_id: str) -> int:
        """실행 ID가 남아 있는 관계 수를 확인한다."""
        row = self.query_session.select_one(
            "graph_rag_sample.count_test_relationships", {"test_run_id": test_run_id}
        )
        return int(row["count"] if row else 0)
    # endregion
