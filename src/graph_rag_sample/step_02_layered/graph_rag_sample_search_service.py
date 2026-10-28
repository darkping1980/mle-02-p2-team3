"""두 DB의 일반·벡터·그래프 조회를 맡는 Search Service."""

from collections.abc import Sequence

from graph_rag_sample.step_02_layered.graph_rag_sample_neo4j_repository import GraphRagSampleNeo4jRepository
from graph_rag_sample.step_02_layered.graph_rag_sample_postgres_repository import GraphRagSamplePostgresRepository


class GraphRagSampleSearchService:
    """질문 대상과 조회 요청을 Repository에 전달한다.

    대부분 Repository 메서드를 그대로 위임하고, ``search_postgres_hybrid()`` 만
    Keyword와 Vector 결과를 합치는 간단한 Service 로직을 가진다.
    """

    def __init__(
        self,
        postgres_repository: GraphRagSamplePostgresRepository,
        neo4j_repository: GraphRagSampleNeo4jRepository,
    ):
        """PostgreSQL과 Neo4j Repository를 전달받는다."""
        self.postgres_repository = postgres_repository
        self.neo4j_repository = neo4j_repository

    # region [PostgreSQL 조회]
    def search_postgres_general(self, test_run_id: str) -> list[dict]:
        """일반 SQL Mapper로 실행 ID에 해당하는 설명 행을 조회한다."""
        return self.postgres_repository.find_general_items(test_run_id)

    def search_postgres_vectors(
        self, test_run_id: str, query_embedding: Sequence[float]
    ) -> list[dict]:
        """pgvector 코사인 거리 순서로 가장 가까운 샘플을 조회한다."""
        return self.postgres_repository.find_similar_vectors(
            test_run_id, query_embedding, limit=3
        )

    def search_postgres_keyword(self, test_run_id: str, keyword: str) -> list[dict]:
        """문장에 키워드가 포함된 PostgreSQL 행을 조회한다."""
        return self.postgres_repository.find_keyword_items(test_run_id, keyword)

    def search_postgres_hybrid(
        self,
        test_run_id: str,
        keyword: str,
        query_embedding: Sequence[float],
    ) -> list[dict]:
        """Keyword 결과를 먼저 놓고 Vector 결과를 item_id 기준으로 합친다.

        Returns:
            item_id가 중복되지 않는 row list. 각 row에는 처음 발견된 출처(``"keyword"`` / ``"vector"``)를
            ``source`` key로 붙인다. 점수 기반 재정렬은 하지 않는다.
        """
        keyword_rows = self.search_postgres_keyword(test_run_id, keyword)
        vector_rows = self.search_postgres_vectors(test_run_id, query_embedding)
        merged_rows = []
        seen_item_ids = set()

        # region [Python 설명] tuple 목록 순회와 dict(row) 복사
        # `(("keyword", keyword_rows), ("vector", vector_rows))`를 순회하며 이름과 결과 목록을 함께 꺼낸다.
        # `dict(row)`는 얕은 복사본을 만들어, `source` key를 추가해도 Repository가 돌려준 원래 row는 바뀌지 않는다.
        # 이미 본 item_id는 set으로 확인해 건너뛴다(먼저 나온 keyword 결과가 우선).
        # endregion

        for source_name, rows in (("keyword", keyword_rows), ("vector", vector_rows)):
            for row in rows:
                item_id = row["item_id"]
                if item_id in seen_item_ids:
                    continue
                seen_item_ids.add(item_id)
                result_row = dict(row)
                result_row["source"] = source_name
                merged_rows.append(result_row)
        return merged_rows
    # endregion

    # region [Neo4j 조회]
    def search_neo4j_project(self, test_run_id: str, project_name: str) -> dict | None:
        """실행 ID가 일치하는 프로젝트 노드를 조회한다."""
        return self.neo4j_repository.find_project(test_run_id, project_name)

    def search_neo4j_technologies(self, test_run_id: str, project_name: str) -> list[dict]:
        """프로젝트와 USES_TECHNOLOGY로 연결된 기술 노드를 조회한다."""
        return self.neo4j_repository.find_technologies(test_run_id, project_name)

    def search_neo4j_relationships(self, test_run_id: str, project_name: str) -> list[dict]:
        """연결 방향, 관계 이름, 양쪽 노드 이름을 조회한다."""
        return self.neo4j_repository.find_relationships(test_run_id, project_name)
    # endregion
