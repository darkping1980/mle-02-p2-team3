"""QuerySession 계약과 Neo4jDbSession의 mapper·실행·트랜잭션 동작을 Mock으로 검증하는 오프라인 테스트."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, Mock

from common.query_session import QuerySession
from common.neo4j_db_session import Neo4jDbSession


class QuerySessionContractTests(unittest.TestCase):
    """추상 계약 클래스는 직접 인스턴스로 만들 수 없음을 확인한다."""

    def test_abstract_contract_cannot_be_instantiated(self):
        with self.assertRaises(TypeError):
            QuerySession()


class Neo4jMapperTests(unittest.TestCase):
    """*.cypher mapper 등록 규칙(namespace, 중복, 잘못된 ID)을 확인한다."""

    def test_loads_namespaced_statements_and_ignores_other_comments(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "car_manual.cypher").write_text(
                "// mapper comment\n// name: find_car\nMATCH (c:Car {id: $car_id})\nRETURN c\n",
                encoding="utf-8",
            )
            session = Neo4jDbSession(mapper_root=root)
            self.assertEqual(session._query("car_manual.find_car"),
                             "MATCH (c:Car {id: $car_id})\nRETURN c")

    def test_rejects_duplicate_statement_across_mapper_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a").mkdir()
            (root / "b").mkdir()
            for folder in (root / "a", root / "b"):
                (folder / "manual.cypher").write_text("// name: find\nRETURN 1", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Duplicate Cypher statement"):
                Neo4jDbSession(mapper_root=root)

    def test_missing_mapper_and_invalid_id_have_clear_errors(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "car.cypher").write_text("// name: find\nRETURN 1", encoding="utf-8")
            session = Neo4jDbSession(mapper_root=root)
            with self.assertRaises(ValueError):
                session._query("invalid")
            with self.assertRaises(LookupError):
                session._query("car.missing")
            with self.assertRaisesRegex(RuntimeError, "inject an official driver"):
                session.select_list("car.find")


class Neo4jExecutionTests(unittest.TestCase):
    """가짜 Driver로 조회·실행·execute_many·트랜잭션의 호출 방식과 반환값을 확인한다."""

    def setUp(self):
        """임시 mapper 파일과 MagicMock Driver를 준비한다(실제 Neo4j 연결 없음)."""
        # `driver.session.return_value.__enter__.return_value`는 `with driver.session() as s:`의 s에 해당한다.
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "car.cypher").write_text(
            "// name: read\nMATCH (n) RETURN n\n// name: write\nCREATE (n)",
            encoding="utf-8",
        )
        self.driver = MagicMock()
        self.db_session = self.driver.session.return_value.__enter__.return_value
        self.tx = self.db_session.begin_transaction.return_value
        self.session = Neo4jDbSession(driver=self.driver, mapper_root=root, database="neo4j")

    def tearDown(self):
        self.temp.cleanup()

    def _result(self, rows, columns=None):
        """keys()/순회/consume()을 가진 가짜 Neo4j Result를 만든다."""
        result = MagicMock()
        result.keys.return_value = columns if columns is not None else (list(rows[0]) if rows else [])
        result.__iter__.return_value = iter(rows)
        result.consume.return_value = Mock(name="summary")
        return result

    def test_select_list_binds_parameters_and_returns_dict_rows(self):
        self.db_session.run.return_value = self._result([{"n": 1}, {"n": 2}])
        rows = self.session.select_list("car.read", {"limit": 2})
        self.assertEqual(rows, [{"n": 1}, {"n": 2}])
        self.driver.session.assert_called_once_with(database="neo4j")
        self.db_session.run.assert_called_once_with("MATCH (n) RETURN n", {"limit": 2})

    def test_select_one_returns_first_record_or_none(self):
        self.db_session.run.return_value = self._result([{"n": 1}, {"n": 2}])
        self.assertEqual(self.session.select_one("car.read"), {"n": 1})
        self.db_session.run.return_value = self._result([], columns=["n"])
        self.assertIsNone(self.session.select_one("car.read"))

    def test_execute_returns_rows_or_native_summary(self):
        self.db_session.run.return_value = self._result([{"n": 1}])
        self.assertEqual(self.session.execute("car.read"), [{"n": 1}])
        empty_read = self._result([], columns=["n"])
        self.db_session.run.return_value = empty_read
        self.assertEqual(self.session.execute("car.read"), [])
        result = self._result([])
        self.db_session.run.return_value = result
        self.assertIs(self.session.execute("car.write"), result.consume.return_value)

    def test_execute_many_repeats_in_one_transaction_and_commits(self):
        self.tx.run.side_effect = [self._result([]), self._result([])]
        results = self.session.execute_many("car.write", [{"i": 1}, {"i": 2}])
        self.assertEqual(len(results), 2)
        self.assertEqual(self.tx.run.call_count, 2)
        self.tx.run.assert_any_call("CREATE (n)", {"i": 1})
        self.tx.run.assert_any_call("CREATE (n)", {"i": 2})
        self.tx.commit.assert_called_once()
        self.tx.rollback.assert_not_called()
        self.driver.session.return_value.__exit__.assert_called_once()

    def test_transaction_rolls_back_and_preserves_original_exception(self):
        error = ValueError("operation failed")
        with self.assertRaisesRegex(ValueError, "operation failed"):
            with self.session.transaction():
                raise error
        self.tx.rollback.assert_called_once()
        self.tx.commit.assert_not_called()
        self.assertIsNone(self.session._active_transaction)
        self.assertIsNone(self.session._active_session)

    def test_transaction_rejects_nesting(self):
        with self.session.transaction():
            with self.assertRaisesRegex(RuntimeError, "Nested transactions"):
                with self.session.transaction():
                    pass
        self.tx.commit.assert_called_once()

    def test_execute_many_failure_rolls_back(self):
        self.tx.run.side_effect = [self._result([]), ValueError("batch failed")]
        with self.assertRaisesRegex(ValueError, "batch failed"):
            self.session.execute_many("car.write", [{"i": 1}, {"i": 2}])
        self.tx.rollback.assert_called_once()
        self.tx.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
