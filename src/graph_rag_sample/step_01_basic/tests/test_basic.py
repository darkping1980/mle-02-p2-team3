"""Step 1 Mapper 범위와 기본 실행 안전성을 검사합니다."""

import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from common.neo4j_db_session import Neo4jDbSession
from common.postgres_db_session import PostgresDbSession
from graph_rag_sample.step_01_basic import main as basic_main


# region [Python 설명] unittest 기본 구조
# `unittest.TestCase`를 상속한 클래스의 `test_`로 시작하는 메서드가 각각 하나의 테스트다(JUnit의 @Test와 비슷).
# `self.assertEqual(a, b)`, `self.assertIn(x, y)`처럼 assert 메서드로 기대값을 검사한다.
# `with self.assertRaises(TypeError):` 블록 안에서 그 예외가 나야 통과한다.
# pytest로 실행해도 unittest.TestCase 테스트를 그대로 수집해 실행한다.
# endregion
class BasicSampleTests(unittest.TestCase):
    """실제 DB 없이 Mapper 파일과 기본 실행 모드를 검증합니다."""

    def test_mapper_root_is_required(self):
        """두 Session 모두 keyword 전용 필수 인자 mapper_root 없이 만들 수 없다."""
        with self.assertRaises(TypeError):
            PostgresDbSession()
        with self.assertRaises(TypeError):
            Neo4jDbSession()

    def test_sql_mapper_loads_only_basic_sample_namespace(self):
        """Step 1 디렉터리를 mapper_root로 쓰면 basic_sample SQL mapper만 등록된다(DB 연결 없음)."""
        mapper_root = Path(__file__).resolve().parents[1]
        session = PostgresDbSession(mapper_root=mapper_root, sql_log_mode="none")

        self.assertEqual(set(session.mappers), {"basic_sample"})
        self.assertTrue(session._query("basic_sample.find_general_items"))
        self.assertTrue(session._query("basic_sample.find_similar_vectors"))

    def test_cypher_mapper_loads_basic_node_and_relationship_queries(self):
        """Cypher mapper의 statement 8개가 모두 등록된다(Driver 없이 생성 가능)."""
        mapper_root = Path(__file__).resolve().parents[1]
        session = Neo4jDbSession(mapper_root=mapper_root)

        self.assertEqual(len(session.mappers), 8)
        self.assertIn("basic_sample.create_project", session.mappers)
        self.assertIn("basic_sample.find_relationships", session.mappers)

    def test_default_main_does_not_connect_or_write_to_databases(self):
        """--run-db 없이 main()을 실행하면 DB에 연결하지 않고 안내만 출력한다."""
        # region [Python 설명] patch.object와 redirect_stdout
        # `patch.object(sys, "argv", ["main"])`은 with 블록 동안만 명령줄 인자를 가짜 값으로 바꾸고, 끝나면 되돌린다.
        # `redirect_stdout(output)`은 print 출력이 화면 대신 StringIO 버퍼에 쌓이게 해 출력 내용을 검사할 수 있게 한다.
        # 여러 context manager는 `with A, B:`처럼 쉼표로 한 줄에 함께 쓸 수 있다.
        # endregion
        output = io.StringIO()
        with patch.object(sys, "argv", ["main"]), redirect_stdout(output):
            result = basic_main.main()

        self.assertEqual(result, 0)
        self.assertIn("DB 쓰기는 실행하지 않았습니다", output.getvalue())


if __name__ == "__main__":
    unittest.main()
