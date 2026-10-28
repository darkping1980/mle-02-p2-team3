"""PostgreSQL 일반 행과 pgvector 벡터를 접근하는 Repository."""

from collections.abc import Sequence

from pgvector.utils import Vector

from common.query_session import QuerySession


class GraphRagSamplePostgresRepository:
    """SQL Mapper와 QuerySession 메서드만 사용해 PostgreSQL을 다룬다.

    생성자 type hint가 구체 클래스(``PostgresDbSession``)가 아니라 추상 계약 ``QuerySession`` 이므로,
    테스트에서는 같은 메서드를 가진 가짜 세션을 넣어 DB 없이 검증할 수 있다(인터페이스에 의존하는 설계).
    SQL 본문은 ``graph_rag_sample.sql`` 에 있고, 이 클래스는 statement ID와 파라미터 dict만 만든다.
    """

    def __init__(self, query_session: QuerySession):
        """SQL을 실행할 공통 QuerySession을 전달받는다."""
        self.query_session = query_session

    # region [임시 테이블 준비]
    def create_demo_tables(self) -> None:
        """현재 트랜잭션이 끝날 때 제거되는 일반·벡터 임시 테이블을 만든다."""
        self.query_session.execute("graph_rag_sample.create_general_temp_table")
        self.query_session.execute("graph_rag_sample.create_vector_temp_table")
    # endregion

    # region [일반 데이터 등록과 삭제]
    def register_general_item(
        self, test_run_id: str, content: str, item_id: str = "general-1"
    ) -> list[dict]:
        """샘플 텍스트 한 건을 등록하고 RETURNING 결과를 받는다."""
        return self.query_session.execute(
            "graph_rag_sample.insert_general_item",
            {"test_run_id": test_run_id, "item_id": item_id, "content": content},
        )

    def delete_general_items(self, test_run_id: str):
        """해당 실행 ID의 일반 샘플 행만 삭제한다."""
        return self.query_session.execute(
            "graph_rag_sample.delete_general_items", {"test_run_id": test_run_id}
        )
    # endregion

    # region [벡터 등록과 삭제]
    def register_vector(
        self,
        test_run_id: str,
        item_name: str,
        embedding: Sequence[float],
        item_id: str | None = None,
    ) -> list[dict]:
        """벡터를 pgvector 형식으로 바꾸어 Mapper에 전달한다."""
        # `item_id or item_name.lower()`는 item_id가 None/빈 문자열이면 이름의 소문자를 ID로 쓴다.
        # `Vector(list(embedding))`은 tuple 등 어떤 Sequence가 와도 list로 바꾼 뒤 pgvector 값으로 감싼다.
        return self.query_session.execute(
            "graph_rag_sample.insert_vector_item",
            {
                "test_run_id": test_run_id,
                "item_id": item_id or item_name.lower(),
                "item_name": item_name,
                "embedding": Vector(list(embedding)),
            },
        )

    def delete_vectors(self, test_run_id: str):
        """해당 실행 ID의 벡터 행만 삭제한다."""
        return self.query_session.execute(
            "graph_rag_sample.delete_vector_items", {"test_run_id": test_run_id}
        )
    # endregion

    # region [조회]
    def find_general_items(self, test_run_id: str) -> list[dict]:
        """실행 ID가 일치하는 일반 텍스트 행을 조회한다."""
        return self.query_session.select_list(
            "graph_rag_sample.find_general_items", {"test_run_id": test_run_id}
        )

    def find_keyword_items(self, test_run_id: str, keyword: str) -> list[dict]:
        """SQL Mapper의 대소문자 무시 키워드 검색 결과를 반환한다."""
        return self.query_session.select_list(
            "graph_rag_sample.find_keyword_items",
            {"test_run_id": test_run_id, "keyword": keyword},
        )

    def find_similar_vectors(
        self, test_run_id: str, query_embedding: Sequence[float], limit: int = 3
    ) -> list[dict]:
        """코사인 거리 연산자로 가까운 벡터를 순서대로 조회한다."""
        return self.query_session.select_list(
            "graph_rag_sample.find_similar_vectors",
            {
                "test_run_id": test_run_id,
                "query_embedding": Vector(list(query_embedding)),
                "limit": limit,
            },
        )
    # endregion
