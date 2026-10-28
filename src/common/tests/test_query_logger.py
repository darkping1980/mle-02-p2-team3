"""QueryLogger와 두 쿼리 세션에 연결된 로그 기능을 검증하는 오프라인 테스트.

PostgreSQL/Neo4j 서버를 사용하지 않는다. 연결, aiosql 쿼리, Neo4j Driver는 Mock으로 대체하고,
psycopg ``ClientCursor`` 는 실제 연결 없이 ``mogrify()`` 를 흉내 내는 가짜 클래스로 patch한다.

자주 쓰는 패턴:
    - ``with self.assertLogs(logger이름, "INFO") as logs:`` : 블록 안에서 남긴 로그를 ``logs.output``
      ("레벨:logger:메시지" 문자열 list)으로 받아 검사한다. 로그가 하나도 없으면 실패한다.
    - ``self.assertNoLogs(...)`` : 블록 안에서 로그가 없어야 통과한다.
    - ``patch.object(대상, "속성", 값)`` : 테스트 동안만 속성을 바꾸고 끝나면 원래대로 돌린다.
"""

from contextlib import contextmanager
import copy
import datetime
import io
import logging
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, Mock, patch

from neo4j import SummaryCounters
from neo4j.graph import Graph, Node, Path as GraphPath
try:
    from pgvector import Vector                 # pgvector>=0.4: utils 모듈 없음, 소스와 같은 경로
except ImportError:
    from pgvector.utils import Vector           # pgvector 0.3.x(langchain-postgres 사용 환경)
import psycopg

from common.neo4j_db_session import Neo4jDbSession, format_graph_value, render_cypher_params
from common.postgres_db_session import PostgresDbSession
from common.query_logger import DEFAULT_SENSITIVE_KEYS, LOG_DIVIDER, MASKED_VALUE, QueryLogger

SQL_LOGGER = "car_search_rag.sql"
NEO4J_LOGGER = "car_search_rag.neo4j"


def make_logger(**kwargs) -> QueryLogger:
    """테스트 전용 logger 이름으로 QueryLogger를 만든다."""
    return QueryLogger(logging.getLogger("test.query_logger"), **kwargs)


class FakeClientCursor:
    """psycopg.ClientCursor 대체 클래스. mogrify()에 전달된 파라미터를 클래스 속성 ``calls`` 에 기록한다."""

    # 클래스 속성이라 모든 인스턴스가 같은 list를 공유한다. 각 테스트의 setUp에서 빈 list로 초기화한다.
    calls: list = []

    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def mogrify(self, sql, params):
        FakeClientCursor.calls.append(params)
        return f"{sql} /* rendered {params!r} */"


#=========================================================
# QueryLogger
#=========================================================
class QueryLoggerSettingsTests(unittest.TestCase):
    """로그 모드·result_log_limit 검증과 logger 레벨 존중을 확인한다."""

    def test_accepts_all_modes(self):
        for mode in ("combined", "separate", "none"):
            self.assertEqual(make_logger(log_mode=mode).log_mode, mode)

    def test_rejects_unknown_mode_with_option_name(self):
        with self.assertRaisesRegex(ValueError, "cypher_log_mode must be one of"):
            make_logger(log_mode="full", mode_option_name="cypher_log_mode")
        query_logger = make_logger()
        with self.assertRaises(ValueError):
            query_logger.log_mode = "verbose"
        self.assertEqual(query_logger.log_mode, "combined")

    def test_result_log_limit_validation(self):
        self.assertEqual(make_logger(result_log_limit=0).result_log_limit, 0)
        for invalid in (-1, True, False, 1.5, "10", None):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "non-negative integer"):
                make_logger(result_log_limit=invalid)

    def test_respects_logger_level_and_skips_rendering(self):
        query_logger = make_logger()
        render = Mock(return_value="rendered")
        query_logger.logger.setLevel(logging.WARNING)
        try:
            with patch.object(query_logger, "sanitize") as sanitize:
                query_logger.log_query("a.b", "Q", {"x": 1}, render_combined=render)
            render.assert_not_called()
            sanitize.assert_not_called()
        finally:
            query_logger.logger.setLevel(logging.NOTSET)


class QueryLoggerFormattingTests(unittest.TestCase):
    """벡터 미리보기, 마스킹, 결과 표 포매팅을 확인한다."""

    def setUp(self):
        self.query_logger = make_logger(vector_types=(Vector,), sensitive_keys=DEFAULT_SENSITIVE_KEYS)

    def test_vector_preview_for_pgvector_and_numeric_lists(self):
        vector = Vector([0.123456, 0.234567, 0.345678, 0.4, 0.5, 0.6, 0.7, 0.8])
        self.assertEqual(self.query_logger.sanitize(vector),
                         "<VECTOR [0.123456, 0.234567, 0.345678, 0.400000, 0.500000, 0.600000, ...] dimension=8>")
        embedding = [0.25] * 1536
        self.assertEqual(self.query_logger.sanitize(embedding),
                         "<VECTOR [" + ", ".join(["0.250000"] * 6) + ", ...] dimension=1536>")
        self.assertTrue(self.query_logger.sanitize(tuple(embedding)).endswith("dimension=1536>"))

    def test_short_or_mixed_lists_are_not_vectors(self):
        self.assertEqual(self.query_logger.sanitize([1, 2, 3]), [1, 2, 3])
        self.assertEqual(self.query_logger.sanitize([True] * 40), [True] * 40)
        mixed = [1.0] * 39 + ["x"]
        self.assertEqual(self.query_logger.sanitize(mixed), mixed)

    def test_nested_structures_and_original_unchanged(self):
        parameters = {"outer": {"embedding": [0.5] * 32, "items": [{"api_key": "k", "name": "n"}], "t": (1, 2)},
                      "db_password": "pw", "token_count": 3}
        original = copy.deepcopy(parameters)
        shown = self.query_logger.sanitize(parameters)
        self.assertEqual(parameters, original)
        self.assertTrue(shown["outer"]["embedding"].startswith("<VECTOR"))
        self.assertEqual(shown["outer"]["items"], [{"api_key": MASKED_VALUE, "name": "n"}])
        self.assertEqual(shown["outer"]["t"], (1, 2))
        self.assertEqual(shown["db_password"], MASKED_VALUE)
        self.assertEqual(shown["token_count"], 3)   # suffix rule does not mask short keys like "token"

    def test_mask_returns_original_object_when_nothing_to_mask(self):
        parameters = {"embedding": [0.1] * 64, "name": "x"}
        self.assertIs(self.query_logger.mask(parameters), parameters)
        self.assertIs(make_logger().mask({"password": "x"}).get("password"), "x")   # masking off

    def test_korean_table_alignment_null_and_control_characters(self):
        table = self.query_logger.format_result_table([
            {"id": 1, "brand": "HYUNDAI", "model": "아반떼"},
            {"id": 2, "brand": None, "model": "쏘렌토\n\t"},
        ])
        lines = table.splitlines()
        widths = {self.query_logger.display_width(line) for line in lines}
        self.assertEqual(len(widths), 1, table)
        self.assertIn("| NULL    |", table)
        self.assertIn("쏘렌토\\n\\t", table)

    def test_long_cell_is_shortened_to_column_width(self):
        cell = self.query_logger.format_result_cell("가" * 50)
        self.assertTrue(cell.endswith("..."))
        self.assertLessEqual(self.query_logger.display_width(cell), QueryLogger.RESULT_LOG_COLUMN_WIDTH)

    def test_cell_formatting_failure_falls_back(self):
        class Broken:
            def __str__(self):
                raise RuntimeError("no str")

            def __repr__(self):
                raise RuntimeError("no repr")

        self.assertEqual(self.query_logger.format_result_cell(Broken()), "<Broken>")


class QueryLoggerOutputTests(unittest.TestCase):
    """QUERY/RESULT DATA/BATCH/요약 로그의 실제 출력 형식을 확인한다."""

    def setUp(self):
        self.query_logger = make_logger(result_log=True, result_log_limit=2)

    def test_combined_separate_none_query_output(self):
        render = Mock(return_value="SELECT 'v'")
        with self.assertLogs("test.query_logger", "INFO") as logs:
            self.query_logger.log_query("a.b", "SELECT %(x)s", {"x": "v"}, render_combined=render)
        self.assertEqual(logs.output[0].split(":", 2)[2],
                         f"QUERY [a.b]\n{LOG_DIVIDER}\nSELECT 'v'\n{LOG_DIVIDER}\nPARAMS {{'x': 'v'}}")
        self.query_logger.log_mode = "separate"
        with self.assertLogs("test.query_logger", "INFO") as logs:
            self.query_logger.log_query("a.b", "SELECT %(x)s", {"x": "v"}, render_combined=render)
        self.assertIn("SELECT %(x)s", logs.output[0])
        self.assertEqual(render.call_count, 1)
        self.query_logger.log_mode = "none"
        with self.assertNoLogs("test.query_logger", "INFO"):
            self.query_logger.log_query("a.b", "SELECT 1", None)
        with self.assertLogs("test.query_logger", "INFO") as logs:
            self.query_logger.log_query("a.b", "SELECT 1", None, force=True)
        self.assertIn("QUERY [a.b]", logs.output[0])

    def test_render_failure_falls_back_to_query_text(self):
        with self.assertLogs("test.query_logger", "INFO") as logs:
            self.query_logger.log_query("a.b", "SELECT 1", {}, render_combined=Mock(side_effect=ValueError))
        self.assertIn("SQL 로그 렌더링 실패 [a.b]: ValueError", logs.output[0])
        self.assertIn("SELECT 1", logs.output[1])

    def test_result_zero_rows_limit_and_truncation(self):
        with self.assertLogs("test.query_logger", "INFO") as logs:
            self.query_logger.log_result_data("a.b", [])
        self.assertEqual(logs.output, ["INFO:test.query_logger:RESULT DATA [a.b] no rows"])
        rows = [{"id": index} for index in range(5)]
        with self.assertLogs("test.query_logger", "INFO") as logs:
            self.query_logger.log_result_data("a.b", rows)
        self.assertNotIn("| 2  |", logs.output[0])
        self.assertEqual(logs.output[1].split(":", 2)[2], "RESULT DATA truncated: showing 2 of 5 rows")
        self.query_logger.result_log_limit = 0
        with self.assertLogs("test.query_logger", "INFO") as logs:
            self.query_logger.log_result_data("a.b", rows)
        self.assertIn("no rows shown", logs.output[0])
        self.assertEqual(rows, [{"id": index} for index in range(5)])

    def test_batch_log_limit_and_omitted_count(self):
        parameters_list = [{"i": index} for index in range(250)]
        with self.assertLogs("test.query_logger", "INFO") as logs:
            self.query_logger.log_batch_query("a.b", "INSERT", parameters_list)
        text = logs.output[0]
        self.assertIn("BATCH PARAMS rows=250", text)
        self.assertIn("[100/250]", text)
        self.assertNotIn("[101/250]", text)
        self.assertIn("생략된 배치 파라미터: 150건", text)
        self.query_logger.log_mode = "none"
        with self.assertNoLogs("test.query_logger", "INFO"):
            self.query_logger.log_batch_query("a.b", "INSERT", parameters_list)

    def test_summary_skips_unmeasured_values(self):
        with self.assertLogs("test.query_logger", "INFO") as logs:
            self.query_logger.log_summary("DONE", "a.b", rows=3, elapsed_ms=1.26, server_ms=None, counters="{}")
        self.assertEqual(logs.output[0].split(":", 2)[2], "DONE [a.b] rows=3 elapsed_ms=1.3 counters={}")

    def test_formatting_failure_is_logged_not_raised(self):
        with patch.object(self.query_logger, "format_result_table", side_effect=RuntimeError("boom")), \
                self.assertLogs("test.query_logger", "INFO") as logs:
            self.query_logger.log_result_data("a.b", [{"x": 1}])
        self.assertEqual(logs.output, ["WARNING:test.query_logger:RESULT DATA 로그 출력 실패 [a.b]: RuntimeError"])


#=========================================================
# PostgreSQL
#=========================================================
class PostgresLoggingTests(unittest.TestCase):
    """가짜 연결·가짜 aiosql 쿼리로 PostgresDbSession의 로그와 트랜잭션 동작을 확인한다."""

    def setUp(self):
        """가짜 DatabaseManager, 가짜 aiosql 쿼리, patch한 ClientCursor를 준비한다."""
        # `self.addCleanup(함수)`는 테스트가 끝난 뒤(실패해도) 실행할 정리 함수를 등록한다.
        self.temp = TemporaryDirectory()
        Path(self.temp.name, "car.sql").write_text("-- name: q\nselect 1;\n", encoding="utf-8")
        self.connection = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value.rowcount = 2
        manager = MagicMock()

        @contextmanager
        def connect(**_kwargs):
            yield self.connection

        manager.connect = connect
        self.manager = manager
        self.query = MagicMock(return_value=iter([{"id": 1}]))
        self.query.sql = "SELECT * FROM car WHERE id = %(id)s"
        FakeClientCursor.calls = []
        patcher = patch.object(psycopg, "ClientCursor", FakeClientCursor)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.temp.cleanup()

    def session(self, **kwargs) -> PostgresDbSession:
        """임시 mapper와 가짜 연결을 쓰는 세션을 만들고, `_query()`가 가짜 쿼리를 돌려주게 바꾼다."""
        session = PostgresDbSession(mapper_root=self.temp.name, database_manager=self.manager, **kwargs)
        session._query = lambda statement_id: self.query
        return session

    def test_constructor_compatibility_and_validation(self):
        session = self.session(sql_log_mode="separate", result_log=True, result_log_limit=5)
        self.assertEqual((session.sql_log_mode, session.result_log, session.result_log_limit), ("separate", True, 5))
        self.assertIsInstance(session.query_logger, QueryLogger)
        with self.assertRaisesRegex(ValueError, "sql_log_mode must be one of: combined, separate, none"):
            self.session(sql_log_mode="bad")
        with self.assertRaisesRegex(ValueError, "result_log_limit must be a non-negative integer"):
            self.session(result_log_limit=True)
        self.assertEqual(PostgresDbSession.SQL_LOG_MODES, ("combined", "separate", "none"))
        self.assertEqual(PostgresDbSession.VECTOR_LOG_PREVIEW_COUNT, 6)

    def test_select_list_renders_full_vector_and_keeps_return_type(self):
        session = self.session()
        vector = Vector([0.5] * 40)
        parameters = {"id": 1, "embedding": vector}
        with self.assertLogs(SQL_LOGGER, "INFO") as logs:
            rows = session.select_list("car.q", parameters)
        self.assertEqual(rows, [{"id": 1}])
        self.assertIs(FakeClientCursor.calls[0], parameters)                    # full_vector_sql: original binding
        self.assertIn("PARAMS {'id': 1, 'embedding': '<VECTOR", logs.output[0])
        self.assertRegex(logs.output[-1], r"RESULT \[car\.q\] rows=1 connect_ms=\d+\.\d sql_log_ms=\d+\.\d "
                                          r"query_fetch_ms=\d+\.\d total_ms=\d+\.\d$")
        self.query.assert_called_once_with(self.connection, id=1, embedding=vector)

    def test_execute_forces_query_log_in_none_mode(self):
        session = self.session(sql_log_mode="none")
        self.query.return_value = 1
        with self.assertLogs(SQL_LOGGER, "INFO") as logs:
            self.assertEqual(session.execute("car.q", {"id": 1}), 1)
        self.assertIn("QUERY [car.q]", logs.output[0])
        self.assertIn("DONE [car.q] elapsed_ms=", logs.output[1])
        self.query.return_value = iter([{"id": 1}])
        with self.assertLogs(SQL_LOGGER, "INFO") as logs:
            session.select_list("car.q", {"id": 1})
        self.assertFalse(any("QUERY [" in line for line in logs.output))

    def test_sensitive_keys_are_opt_in_and_execution_gets_original(self):
        parameters = {"id": 1, "password": "secret-value"}
        with self.assertLogs(SQL_LOGGER, "INFO") as logs:
            self.session().select_list("car.q", parameters)
        self.assertIn("secret-value", logs.output[0])                           # unchanged default behaviour
        self.query.return_value = iter([])
        with self.assertLogs(SQL_LOGGER, "INFO") as logs:
            self.session(sensitive_log_keys=DEFAULT_SENSITIVE_KEYS).select_list("car.q", parameters)
        self.assertNotIn("secret-value", "\n".join(logs.output))
        self.query.assert_called_with(self.connection, id=1, password="secret-value")
        self.assertEqual(parameters, {"id": 1, "password": "secret-value"})

    def test_render_failure_does_not_block_execution(self):
        with patch.object(FakeClientCursor, "mogrify", side_effect=TypeError("bad")), \
                self.assertLogs(SQL_LOGGER, "INFO") as logs:
            rows = self.session().select_list("car.q", {"id": 1})
        self.assertEqual(rows, [{"id": 1}])
        self.assertIn("SQL 로그 렌더링 실패 [car.q]: TypeError", logs.output[0])

    def test_execute_many_logs_batch_even_in_none_mode(self):
        session = self.session(sql_log_mode="none")
        parameters_list = [{"id": index} for index in range(120)]
        with self.assertLogs(SQL_LOGGER, "INFO") as logs:
            self.assertEqual(session.execute_many("car.q", parameters_list), 2)
        self.assertIn("생략된 배치 파라미터: 20건", logs.output[0])
        self.assertRegex(logs.output[1], r"BATCH DONE \[car\.q\] rows=120 elapsed_ms=\d+\.\d$")
        self.assertEqual(session.execute_many("car.q", []), 0)

    def test_transaction_commit_rollback_and_commit_failure(self):
        session = self.session()
        with self.assertLogs(SQL_LOGGER, "INFO") as logs:
            with session.transaction():
                pass
        self.assertEqual([line.split(":", 2)[2] for line in logs.output], ["TRANSACTION BEGIN", "TRANSACTION COMMIT"])

        with self.assertLogs(SQL_LOGGER, "INFO") as logs, self.assertRaisesRegex(ValueError, "work"):
            with session.transaction():
                raise ValueError("work")
        self.assertEqual(logs.output[-1].split(":", 2)[2], "TRANSACTION ROLLBACK")
        self.assertIsNone(session._active_connection)

        self.connection.commit.side_effect = RuntimeError("commit failed")
        with self.assertLogs(SQL_LOGGER, "INFO") as logs, self.assertRaisesRegex(RuntimeError, "commit failed"):
            with session.transaction():
                pass
        self.assertNotIn("TRANSACTION COMMIT", [line.split(":", 2)[2] for line in logs.output])
        self.assertIn("TRANSACTION COMMIT FAILED: RuntimeError", logs.output[-1])

    def test_rollback_failure_keeps_existing_propagation(self):
        session = self.session()
        self.connection.rollback.side_effect = OSError("rollback failed")
        with self.assertLogs(SQL_LOGGER, "ERROR") as logs, self.assertRaises(OSError) as raised:
            with session.transaction():
                raise ValueError("work")
        self.assertIsInstance(raised.exception.__context__, ValueError)
        self.assertIn("TRANSACTION ROLLBACK FAILED", logs.output[0])
        self.assertIsNone(session._active_connection)

    def test_nested_transaction_still_rejected(self):
        session = self.session()
        with session.transaction():
            with self.assertRaisesRegex(RuntimeError, "이미 Transaction이 실행 중입니다."):
                with session.transaction():
                    pass


#=========================================================
# Neo4j
#=========================================================
def neo4j_result(rows, columns=None, counters=None, available=None, consumed=None):
    """keys/레코드/consume() summary(counters, 서버 시간 포함)를 가진 가짜 Neo4j Result를 만든다."""
    result = MagicMock()
    result.keys.return_value = columns if columns is not None else (list(rows[0]) if rows else [])
    result.__iter__.return_value = iter(rows)
    summary = MagicMock(name="summary")
    summary.counters = SummaryCounters(counters or {})
    summary.result_available_after = available
    summary.result_consumed_after = consumed
    result.consume.return_value = summary
    return result


class Neo4jLoggingTests(unittest.TestCase):
    """가짜 Driver로 Neo4jDbSession의 로그 형식, 반환값 보존, 트랜잭션 로그를 확인한다."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        Path(self.temp.name, "vehicle.cypher").write_text(
            "// name: select_by_brand\nMATCH (v:Vehicle)\nWHERE v.brand = $brand\nRETURN v\nLIMIT $limit\n"
            "// name: create\nCREATE (v:Vehicle {brand: $brand}) RETURN v\n"
            "// name: create_no_return\nCREATE (v:Vehicle {brand: $brand})\n",
            encoding="utf-8",
        )
        self.driver = MagicMock()
        self.db_session = self.driver.session.return_value.__enter__.return_value
        self.tx = self.db_session.begin_transaction.return_value

    def tearDown(self):
        self.temp.cleanup()

    def session(self, **kwargs) -> Neo4jDbSession:
        return Neo4jDbSession(mapper_root=self.temp.name, driver=self.driver, database="neo4j", **kwargs)

    def test_constructor_options_and_validation(self):
        session = self.session(cypher_log_mode="separate", result_log=True, result_log_limit=3)
        self.assertEqual((session.cypher_log_mode, session.result_log, session.result_log_limit), ("separate", True, 3))
        with self.assertRaisesRegex(ValueError, "cypher_log_mode must be one of"):
            self.session(cypher_log_mode="combine")
        with self.assertRaisesRegex(ValueError, "result_log_limit"):
            self.session(result_log_limit=-1)
        with self.assertRaisesRegex(ValueError, "result_log_limit"):
            session.result_log_limit = True

    def test_combined_log_uses_browser_params_and_runs_once_with_driver_binding(self):
        self.db_session.run.return_value = neo4j_result([{"v": 1}])
        parameters = {"brand": "HYUNDAI", "limit": 10, "password": "pw"}
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs:
            rows = self.session().select_list("vehicle.select_by_brand", parameters)
        self.assertEqual(rows, [{"v": 1}])
        # 마스킹이 적용되면 인라인 Cypher를 만들지 않고, 재현 불가를 밝힌 뒤 :param 줄로 대체한다.
        self.assertEqual(logs.output[0].split(":", 2)[2], (
            f"QUERY [vehicle.select_by_brand]\n{LOG_DIVIDER}\n"
            "// NOT REPRODUCIBLE AS-IS: masked values differ from the executed values (masked parameters); "
            "showing :param lines instead\n"
            ":param brand => 'HYUNDAI';\n:param limit => 10;\n:param password => '<MASKED>';\n\n"
            f"MATCH (v:Vehicle)\nWHERE v.brand = $brand\nRETURN v\nLIMIT $limit\n{LOG_DIVIDER}"
        ))
        # The driver receives the query text and original values separately, exactly once.
        self.db_session.run.assert_called_once_with(
            "MATCH (v:Vehicle)\nWHERE v.brand = $brand\nRETURN v\nLIMIT $limit", parameters)
        self.db_session.run.return_value.consume.assert_called_once()

    def test_separate_and_none_modes(self):
        self.db_session.run.return_value = neo4j_result([], columns=["v"])
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs:
            self.session(cypher_log_mode="separate").select_list("vehicle.select_by_brand", {"brand": "K"})
        self.assertIn("WHERE v.brand = $brand", logs.output[0])
        self.assertIn("PARAMS {'brand': 'K'}", logs.output[0])
        self.db_session.run.return_value = neo4j_result([{"v": 1}])
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs:
            self.session(cypher_log_mode="none").execute("vehicle.create", {"brand": "K"})
        self.assertFalse(any("QUERY [" in line for line in logs.output))      # no forced log in Neo4j
        self.assertIn("DONE [vehicle.create] rows=1", logs.output[-1])

    def test_cypher_literal_rendering(self):
        query_logger = self.session().query_logger
        text = render_cypher_params(query_logger, "RETURN 1", {
            "s": "it's\n\"ok\"\\", "f": 1e20, "b": False, "n": None, "l": [1, "a", [2.5]],
            "m": {"a b": {"x": 1}}, "d": datetime.date(2026, 1, 2),
            "dt": datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc),
            "emb": [0.1] * 64, "raw": b"\x00",
        })
        self.assertIn(":param s => 'it\\'s\\n\"ok\"\\\\';", text)
        self.assertIn(":param f => 1e20;", text)
        self.assertIn(":param b => false;", text)
        self.assertIn(":param n => null;", text)
        self.assertIn(":param l => [1, 'a', [2.5]];", text)
        self.assertIn(":param m => {`a b`: {x: 1}};", text)
        self.assertIn(":param d => date('2026-01-02');", text)
        self.assertIn(":param dt => datetime('2026-01-02T03:04:05+00:00');", text)
        self.assertIn("// :param emb => <VECTOR [0.100000", text)
        self.assertIn("// :param raw => b'\\x00'; (not reproducible", text)
        self.assertTrue(text.endswith("\n\nRETURN 1"))

    def test_native_graph_values_returned_and_table_is_safe(self):
        graph = Graph()
        vehicle = Node(graph, "4:x:1", 1, {"Vehicle"}, {"brand": "HYUNDAI", "model": "아반떼"})
        brand = Node(graph, "4:x:2", 2, {"Brand"}, {"name": "현대"})
        made_by = graph.relationship_type("MADE_BY")(graph, "5:x:1", 1, {"since": 2020})
        made_by._start_node, made_by._end_node = vehicle, brand
        path = GraphPath(vehicle, made_by)
        self.db_session.run.return_value = neo4j_result([{"v": vehicle, "r": made_by, "p": path}])
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs:
            rows = self.session(result_log=True).select_list("vehicle.select_by_brand", {})
        self.assertIs(rows[0]["v"], vehicle)
        self.assertIs(rows[0]["p"], path)
        table = next(line for line in logs.output if "RESULT DATA" in line)
        self.assertIn("[:MADE_BY {since: 2020}]", table)
        self.assertIn("(:Vehicle {brand: 'HYUNDAI'", table)
        self.assertEqual(format_graph_value(path),
                         "(:Vehicle {brand: 'HYUNDAI', model: '아반떼'})-[:MADE_BY {since: 2020}]->(:Brand {name: '현대'})")

    def test_summary_counters_and_server_timings(self):
        result = neo4j_result([], counters={"nodes-created": 1, "properties-set": 2}, available=3, consumed=7)
        self.db_session.run.return_value = result
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs:
            returned = self.session(result_log=True).execute("vehicle.create_no_return", {"brand": "K"})
        self.assertIs(returned, result.consume.return_value)                  # native ResultSummary kept
        done = logs.output[-1]
        self.assertIn("DONE [vehicle.create_no_return] rows=0 counters={nodes_created: 1, properties_set: 2}", done)
        self.assertRegex(done, r"session_ms=\d+\.\d cypher_log_ms=\d+\.\d query_fetch_ms=\d+\.\d total_ms=\d+\.\d "
                               r"server_available_after_ms=3 server_consumed_after_ms=7$")
        self.assertFalse(any("RESULT DATA" in line for line in logs.output))   # summary is not a row table

    def test_mock_summary_without_counters_does_not_invent_values(self):
        result = MagicMock()
        result.keys.return_value = []
        result.__iter__.return_value = iter([])
        self.db_session.run.return_value = result
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs:
            self.session().execute("vehicle.create_no_return")
        self.assertIn("counters={}", logs.output[-1])
        self.assertNotIn("server_available_after_ms", logs.output[-1])

    def test_execute_many_single_batch_log_without_per_row_duplicates(self):
        self.tx.run.side_effect = [neo4j_result([], counters={"nodes-created": 1}) for _ in range(3)]
        parameters_list = [{"brand": f"B{index}"} for index in range(3)]
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs:
            results = self.session().execute_many("vehicle.create_no_return", parameters_list)
        self.assertEqual(len(results), 3)
        self.assertEqual(self.tx.run.call_count, 3)
        messages = [line.split(":", 2)[2] for line in logs.output]
        self.assertEqual(messages[0], "TRANSACTION BEGIN")
        self.assertTrue(messages[1].startswith("BATCH QUERY [vehicle.create_no_return]"))
        self.assertEqual(messages[2], "TRANSACTION COMMIT")
        self.assertRegex(messages[3], r"BATCH DONE \[vehicle\.create_no_return\] rows=3 "
                                      r"counters=\{nodes_created: 3\} elapsed_ms=\d+\.\d$")
        self.assertEqual(len(messages), 4)
        self.tx.commit.assert_called_once()

    def test_batch_log_respects_limit(self):
        self.tx.run.side_effect = [neo4j_result([]) for _ in range(150)]
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs:
            self.session().execute_many("vehicle.create_no_return", [{"brand": index} for index in range(150)])
        batch = next(line for line in logs.output if "BATCH QUERY" in line)
        self.assertIn("[100/150]", batch)
        self.assertIn("생략된 배치 파라미터: 50건", batch)

    def test_transaction_commit_failure_is_not_logged_as_commit(self):
        self.tx.commit.side_effect = RuntimeError("commit failed")
        session = self.session()
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs, self.assertRaisesRegex(RuntimeError, "commit failed"):
            with session.transaction():
                pass
        messages = [line.split(":", 2)[2] for line in logs.output]
        self.assertEqual(messages, ["TRANSACTION BEGIN", "TRANSACTION COMMIT FAILED: RuntimeError",
                                    "TRANSACTION ROLLBACK ATTEMPTED AFTER COMMIT FAILURE (commit outcome unknown)"])
        self.tx.rollback.assert_called_once()
        self.assertIsNone(session._active_transaction)

    def test_rollback_failure_logged_and_original_exception_preserved(self):
        self.tx.rollback.side_effect = OSError("rollback failed")
        session = self.session()
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs, self.assertRaisesRegex(ValueError, "work"):
            with session.transaction():
                raise ValueError("work")
        self.assertIn("TRANSACTION ROLLBACK FAILED", logs.output[-1])
        self.assertIn("OSError: rollback failed", logs.output[-1])              # traceback included
        self.assertIsNone(session._active_session)

    def test_log_formatting_failure_does_not_change_execution(self):
        self.db_session.run.return_value = neo4j_result([{"v": 1}])
        session = self.session(result_log=True)
        with patch.object(session.query_logger, "sanitize", side_effect=RuntimeError("boom")), \
                patch.object(session.query_logger, "format_result_table", side_effect=RuntimeError("boom")), \
                self.assertLogs(NEO4J_LOGGER, "INFO"):
            rows = session.select_list("vehicle.select_by_brand", {"brand": "K"})
        self.assertEqual(rows, [{"v": 1}])
        self.db_session.run.assert_called_once()

    def test_logging_disabled_still_executes_once(self):
        logger = logging.getLogger(NEO4J_LOGGER)
        previous = logger.level
        logger.setLevel(logging.WARNING)
        try:
            self.db_session.run.return_value = neo4j_result([{"v": 1}])
            with patch("common.neo4j_db_session.render_cypher_params") as render:
                self.assertEqual(self.session(result_log=True).select_list("vehicle.select_by_brand"), [{"v": 1}])
            render.assert_not_called()
            self.db_session.run.assert_called_once()
        finally:
            logger.setLevel(previous)


#=========================================================
# 최종 검수에서 추가한 회귀 테스트
#=========================================================
class _RaisingFilter(logging.Filter):
    """고장 난 handler filter 흉내: needle이 포함된 로그 메시지마다 예외를 낸다."""

    def __init__(self, needle=""):
        super().__init__()
        self.needle = needle

    def filter(self, record):
        if self.needle in record.getMessage():
            raise RuntimeError("broken log filter")
        return True


@contextmanager
def broken_logger(name, needle=""):
    """with 블록 동안 지정 logger의 handler filter가 예외를 내도록 설정하고, 끝나면 원래 설정으로 되돌린다."""
    logger = logging.getLogger(name)
    handler = logging.StreamHandler(io.StringIO())   # NullHandler.handle() never calls filters
    handler.addFilter(_RaisingFilter(needle))
    previous = (logger.level, logger.propagate)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous[0])
        logger.propagate = previous[1]


class PostgresSensitiveMaskingTests(unittest.TestCase):
    """sensitive_log_keys를 켰을 때 모든 PostgreSQL 로그 경로에서 비밀값이 노출되지 않는지 확인한다."""

    # region [Python 설명] 다른 클래스의 함수를 클래스 속성으로 재사용
    # 클래스 본문에서 `setUp = PostgresLoggingTests.setUp`처럼 함수를 대입하면 이 클래스의 메서드로 쓰인다.
    # 상속하면 PostgresLoggingTests의 test_ 메서드까지 다시 실행되므로, 준비 코드만 가져오려고 이렇게 했다.
    # endregion
    setUp = PostgresLoggingTests.setUp
    tearDown = PostgresLoggingTests.tearDown
    session = PostgresLoggingTests.session
    SECRETS = ("S-PW", "S-KEY", "S-TOKEN", "S-SECRET")

    def parameters(self):
        return {"id": 1, "password": "S-PW",
                "nested": {"api_key": "S-KEY", "rows": [{"token": "S-TOKEN"}]},
                "pair": ({"client_secret": "S-SECRET"},), "embedding": Vector([0.5] * 40)}

    def assert_no_secret(self, output):
        text = "\n".join(output) + "\n" + repr(FakeClientCursor.calls)
        for secret in self.SECRETS:
            self.assertNotIn(secret, text)

    def test_masking_in_all_postgres_log_paths(self):
        for mode in ("combined", "separate"):
            with self.subTest(mode=mode):
                FakeClientCursor.calls = []
                session = self.session(sql_log_mode=mode, sensitive_log_keys=DEFAULT_SENSITIVE_KEYS)
                parameters = self.parameters()
                original = copy.deepcopy({key: value for key, value in parameters.items() if key != "embedding"})
                with self.assertLogs(SQL_LOGGER, "INFO") as logs:
                    self.query.return_value = iter([])
                    session.select_list("car.q", parameters)          # full_vector_sql=True mogrify path
                    self.query.return_value = 1
                    session.execute("car.q", parameters)              # sanitized mogrify path
                    session.execute_many("car.q", [parameters, parameters])
                self.assert_no_secret(logs.output)
                # Execution still receives the original values and objects.
                self.query.assert_called_with(self.connection, **parameters)
                cursor = self.connection.cursor.return_value.__enter__.return_value
                cursor.executemany.assert_called_with(self.query.sql, [parameters, parameters])
                self.assertEqual({key: value for key, value in parameters.items() if key != "embedding"}, original)

    def test_full_vector_render_keeps_vector_but_masks_secret(self):
        session = self.session(sensitive_log_keys=DEFAULT_SENSITIVE_KEYS)
        parameters = self.parameters()
        with self.assertLogs(SQL_LOGGER, "INFO"):
            session.select_list("car.q", parameters)
        rendered = FakeClientCursor.calls[0]
        self.assertIs(rendered["embedding"], parameters["embedding"])   # full vector still rendered
        self.assertEqual(rendered["password"], MASKED_VALUE)


class LoggingFailureIsolationTests(unittest.TestCase):
    """모든 로그 출력이 실패해도 두 세션의 실행 결과와 트랜잭션 상태가 그대로인지 확인한다."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        Path(self.temp.name, "car.sql").write_text("-- name: q\nselect 1;\n", encoding="utf-8")
        Path(self.temp.name, "car.cypher").write_text("// name: w\nCREATE (n $p)", encoding="utf-8")
        self.connection = MagicMock()
        manager = MagicMock()

        @contextmanager
        def connect(**_kwargs):
            yield self.connection

        manager.connect = connect
        self.pg = PostgresDbSession(mapper_root=self.temp.name, database_manager=manager, result_log=True)
        self.query = MagicMock(side_effect=lambda connection, **params: iter([{"id": 1}]))
        self.query.sql = "SELECT 1"
        self.pg._query = lambda statement_id: self.query
        self.driver = MagicMock()
        self.tx = self.driver.session.return_value.__enter__.return_value.begin_transaction.return_value
        self.neo = Neo4jDbSession(mapper_root=self.temp.name, driver=self.driver, result_log=True)
        patcher = patch.object(psycopg, "ClientCursor", FakeClientCursor)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.temp.cleanup)

    def test_transaction_begin_log_failure_does_not_leave_session_stuck(self):
        with broken_logger(SQL_LOGGER, "BEGIN"):
            with self.pg.transaction():
                pass
        self.assertIsNone(self.pg._active_connection)
        self.connection.commit.assert_called_once()
        with broken_logger(NEO4J_LOGGER, "BEGIN"):
            with self.neo.transaction():
                pass
        self.assertIsNone(self.neo._active_transaction)
        self.tx.commit.assert_called_once()

    def test_every_log_line_failing_does_not_change_results(self):
        with broken_logger(SQL_LOGGER):
            self.assertEqual(self.pg.select_list("car.q", {"a": 1}), [{"id": 1}])
            self.assertEqual(self.pg.execute("car.q", {"a": 1}), [{"id": 1}])
            self.connection.cursor.return_value.__enter__.return_value.rowcount = 2
            self.assertEqual(self.pg.execute_many("car.q", [{"a": 1}]), 2)
            with self.pg.transaction():
                self.pg.execute("car.q")
        self.assertIsNone(self.pg._active_connection)
        self.tx.run.side_effect = lambda *args: neo4j_result([{"n": 1}])
        with broken_logger(NEO4J_LOGGER):
            self.assertEqual(self.neo.execute_many("car.w", [{"p": {}}, {"p": {}}]), [[{"n": 1}], [{"n": 1}]])
            with self.neo.transaction():
                self.assertEqual(self.neo.select_list("car.w"), [{"n": 1}])
        self.assertIsNone(self.neo._active_transaction)
        self.assertEqual(self.tx.commit.call_count, 2)


class Neo4jFailureSemanticsTests(unittest.TestCase):
    """run/fetch/consume/commit/rollback 실패 시 예외 전파와 트랜잭션 의미를 확인한다."""

    def setUp(self):
        self.temp = TemporaryDirectory()
        Path(self.temp.name, "car.cypher").write_text(
            "// name: w\nCREATE (n {i: $i})\n// name: r\nCREATE (n {i: $i}) RETURN n.i AS i", encoding="utf-8")
        self.driver = MagicMock()
        self.db_session = self.driver.session.return_value.__enter__.return_value
        self.tx = self.db_session.begin_transaction.return_value
        self.session = Neo4jDbSession(mapper_root=self.temp.name, driver=self.driver)
        self.addCleanup(self.temp.cleanup)

    def failing_result(self, stage):
        result = neo4j_result([{"i": 1}])
        if stage == "fetch":
            result.__iter__.side_effect = ConnectionError("fetch failed")
        elif stage == "consume":
            result.consume.side_effect = ConnectionError("consume failed")
        return result

    def test_run_fetch_consume_errors_propagate_and_roll_back(self):
        for stage in ("run", "fetch", "consume"):
            with self.subTest(stage=stage):
                self.tx.reset_mock()
                self.db_session.run.reset_mock()
                if stage == "run":
                    self.db_session.run.side_effect = self.tx.run.side_effect = ConnectionError("run failed")
                else:
                    self.db_session.run.side_effect = self.tx.run.side_effect = None
                    self.db_session.run.return_value = self.failing_result(stage)
                    self.tx.run.return_value = self.failing_result(stage)
                with self.assertLogs(NEO4J_LOGGER, "INFO") as logs, \
                        self.assertRaisesRegex(ConnectionError, f"{stage} failed"):
                    self.session.execute("car.r", {"i": 1})              # auto-commit path
                self.assertFalse(any("DONE [" in line for line in logs.output))
                self.assertEqual(self.db_session.run.call_count, 1)
                with self.assertLogs(NEO4J_LOGGER, "INFO"), self.assertRaises(ConnectionError) as raised:
                    with self.session.transaction():
                        self.session.execute("car.r", {"i": 1})
                self.assertIn(f"{stage} failed", str(raised.exception))
                self.tx.rollback.assert_called_once()
                self.tx.commit.assert_not_called()
                self.assertEqual(self.tx.run.call_count, 1)
                self.assertIsNone(self.session._active_transaction)

    def test_commit_outcome_unknown_is_not_reported_as_rollback(self):
        from neo4j.exceptions import IncompleteCommit, TransactionError
        self.tx.commit.side_effect = IncompleteCommit("connection lost during commit")
        # Real driver: commit() closes the transaction, so rollback() raises "Transaction closed".
        self.tx.rollback.side_effect = TransactionError(self.tx, "Transaction closed")
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs, self.assertRaises(IncompleteCommit):
            with self.session.transaction():
                pass
        messages = [line.split(":", 2)[2].splitlines()[0] for line in logs.output]
        self.assertEqual(messages, [
            "TRANSACTION BEGIN",
            "TRANSACTION COMMIT FAILED: IncompleteCommit",
            "TRANSACTION ROLLBACK FAILED AFTER COMMIT FAILURE (commit outcome unknown)",
        ])
        self.assertFalse(any(message in ("TRANSACTION ROLLBACK", "TRANSACTION COMMIT") for message in messages))
        self.assertIsNone(self.session._active_transaction)

    def test_execute_many_preserves_runs_results_summaries_and_atomicity(self):
        results = [neo4j_result([], counters={"nodes-created": 1}) for _ in range(3)]
        self.tx.run.side_effect = results
        returned = self.session.execute_many("car.w", [{"i": 1}, {"i": 2}, {"i": 3}])
        self.assertEqual(returned, [result.consume.return_value for result in results])   # native summaries
        self.assertEqual([call.args for call in self.tx.run.call_args_list],
                         [("CREATE (n {i: $i})", {"i": index}) for index in (1, 2, 3)])
        self.tx.commit.assert_called_once()

        self.tx.reset_mock()
        self.tx.run.side_effect = [neo4j_result([{"i": 1}]), neo4j_result([{"i": 2}])]
        self.assertEqual(self.session.execute_many("car.r", [{"i": 1}, {"i": 2}]), [[{"i": 1}], [{"i": 2}]])

        self.tx.reset_mock()
        self.tx.run.side_effect = [neo4j_result([]), ConnectionError("row 2 failed"), neo4j_result([])]
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs, self.assertRaisesRegex(ConnectionError, "row 2"):
            self.session.execute_many("car.w", [{"i": 1}, {"i": 2}, {"i": 3}])
        self.assertEqual(self.tx.run.call_count, 2)                     # stops at the failing row
        self.tx.rollback.assert_called_once()
        self.tx.commit.assert_not_called()
        self.assertFalse(any("BATCH DONE" in line for line in logs.output))

    def test_execute_many_inside_transaction_does_not_commit_itself(self):
        self.tx.run.side_effect = [neo4j_result([]), neo4j_result([])]
        with self.session.transaction():
            self.session.execute_many("car.w", [{"i": 1}, {"i": 2}])
            self.tx.commit.assert_not_called()
            self.db_session.begin_transaction.assert_called_once()
        self.tx.commit.assert_called_once()

    def test_execute_many_accepts_iterables_without_len(self):
        self.tx.run.side_effect = [neo4j_result([]), neo4j_result([])]
        with self.assertLogs(NEO4J_LOGGER, "INFO") as logs:
            returned = self.session.execute_many("car.w", ({"i": index} for index in range(2)))
        self.assertEqual(len(returned), 2)
        self.assertRegex(logs.output[-1], r"BATCH DONE \[car\.w\] rows=2 ")


class Neo4jCypherLiteralTests(unittest.TestCase):
    """:param 로그 렌더링에서 민감값이 노출되지 않는지 확인한다."""

    def test_masked_values_do_not_leak_into_param_lines(self):
        query_logger = make_logger(sensitive_keys=DEFAULT_SENSITIVE_KEYS)
        text = render_cypher_params(query_logger, "RETURN 1", {"password": "pw", "m": {"token": "t", "x": 1}})
        self.assertNotIn("'pw'", text)
        self.assertNotIn("'t'", text)


class CypherInlineRenderTests(unittest.TestCase):
    """Neo4j 전용 인라인 렌더링: 문자열·주석·백틱 밖의 ``$name`` 만 리터럴로 바꾸고, 안전하지 않으면 :param으로 대체."""

    def render(self, query, parameters, **kwargs):
        from common.neo4j_db_session import render_cypher_inline

        return render_cypher_inline(make_logger(**kwargs), query, parameters)

    def test_tokens_skip_strings_comments_backticks_and_respect_full_names(self):
        from common.neo4j_db_session import _cypher_parameter_tokens

        query = ("MATCH (n {id: $id, id2: $id2}) // $id in line comment\n"
                 "/* $id2 in block comment */ WHERE n.s = '$id' OR n.t = \"say $id2\" OR n.u = 'it\\'s $id'\n"
                 "RETURN n.`$id` AS `col $id2`, $`odd name` AS o, $0 AS p, $이름 AS k, $(1) AS x")
        names = [name for _, _, name in _cypher_parameter_tokens(query)]
        self.assertEqual(names, ["id", "id2", "odd name", "0", "이름"])

    def test_inline_values_for_each_type(self):
        query = "RETURN $s AS s, $q AS q, $n AS n, $b AS b, $i AS i, $neg AS neg, $f AS f, $nan AS nan, " \
                "$l AS l, $m AS m, $d AS d, $id AS a, $id2 AS c"
        parameters = {"s": "된장 두부찌개", "q": "O'Brien \\ \"x\"\n", "n": None, "b": True, "i": 42, "neg": -7,
                      "f": 1e-12, "nan": float("nan"), "l": [1, "두부", None], "m": {"이름": "두부", "a b": [1]},
                      "d": datetime.date(2026, 10, 24), "id": "A", "id2": "B"}
        before = copy.deepcopy({k: v for k, v in parameters.items() if k != "nan"})
        inline, reason = self.render(query, parameters)
        self.assertEqual(reason, "")
        self.assertEqual(inline, (
            "RETURN '된장 두부찌개' AS s, 'O\\'Brien \\\\ \"x\"\\n' AS q, null AS n, true AS b, 42 AS i, (-7) AS neg, "
            "1e-12 AS f, (0.0 / 0.0) AS nan, [1, '두부', null] AS l, {`이름`: '두부', `a b`: [1]} AS m, "
            "date('2026-10-24') AS d, 'A' AS a, 'B' AS c"))
        self.assertEqual({k: v for k, v in parameters.items() if k != "nan"}, before)   # 원본 불변

    def test_values_inside_strings_and_comments_are_left_alone(self):
        inline, _ = self.render("MATCH (n) WHERE n.x = $id // keep $id\nRETURN '$id' AS lit, n.`$id2` AS c",
                                {"id": 5, "id2": 6})
        self.assertEqual(inline, "MATCH (n) WHERE n.x = 5 // keep $id\nRETURN '$id' AS lit, n.`$id2` AS c")

    def test_unsafe_cases_fall_back(self):
        cases = (
            ("RETURN $v", {"v": b"\x00"}, "no exact literal for $v"),
            ("RETURN $v", {"v": list(range(32))}, "no exact literal for $v"),
            ("RETURN $v, $w", {"v": 1}, "parameters not provided: w"),
            ("RETURN 'unterminated $v", {"v": 1}, "cannot scan Cypher text"),
        )
        for query, parameters, reason in cases:
            with self.subTest(reason=reason):
                inline, got = self.render(query, parameters)
                self.assertIsNone(inline)
                self.assertTrue(got.startswith(reason), got)
        inline, got = self.render("RETURN $token", {"token": "secret"}, sensitive_keys=DEFAULT_SENSITIVE_KEYS)
        self.assertEqual((inline, got), (None, "masked parameters"))

    def test_log_text_marks_inline_or_fallback(self):
        from common.neo4j_db_session import render_cypher_log

        text = render_cypher_log(make_logger(), "RETURN $v AS v", {"v": "두부"})
        self.assertEqual(text, "// inline parameter values for log only (the driver executed this query with bound "
                               "parameters)\nRETURN '두부' AS v")
        text = render_cypher_log(make_logger(sensitive_keys=DEFAULT_SENSITIVE_KEYS), "RETURN $password", {"password": "pw"})
        self.assertTrue(text.startswith("// NOT REPRODUCIBLE AS-IS: masked values"))
        self.assertNotIn("'pw'", text)
        text = render_cypher_log(make_logger(), "RETURN $v", {"v": b"\x01"})
        self.assertTrue(text.startswith("// inline rendering skipped (no exact literal for $v"))
        self.assertIn("// :param v => b'\\x01'; (not reproducible as a literal)", text)
        self.assertEqual(render_cypher_log(make_logger(), "RETURN 1", {}), "RETURN 1")


class PostgresRenderNotesTests(unittest.TestCase):
    """PostgreSQL 전용 mogrify 렌더링은 그대로 두고, 실행 값과 달라지는 경우에만 SQL 주석으로 재현 불가를 밝힌다."""

    # 가짜 연결·가짜 쿼리 준비는 PostgresLoggingTests와 같다(상속하면 그 테스트들이 한 번 더 실행되므로 메서드만 빌린다).
    setUp = PostgresLoggingTests.setUp
    tearDown = PostgresLoggingTests.tearDown
    session = PostgresLoggingTests.session

    def test_plain_values_have_no_note(self):
        with self.assertLogs(SQL_LOGGER, "INFO") as logs:
            self.session().select_list("car.q", {"id": 1})
        self.assertNotIn("NOT REPRODUCIBLE", logs.output[0])

    def test_masked_values_are_marked(self):
        with self.assertLogs(SQL_LOGGER, "INFO") as logs:
            self.session(sensitive_log_keys=DEFAULT_SENSITIVE_KEYS).select_list("car.q", {"id": 1, "api_key": "S"})
        self.assertIn("-- NOT REPRODUCIBLE AS-IS: masked values", logs.output[0])

    def test_vector_preview_is_marked_only_on_execute_path(self):
        vector = Vector([0.5] * 40)
        with self.assertLogs(SQL_LOGGER, "INFO") as logs:
            self.session().select_list("car.q", {"id": 1, "embedding": vector})          # 전체 벡터 렌더링
        self.assertNotIn("NOT REPRODUCIBLE", logs.output[0])
        self.query.return_value = 1
        with self.assertLogs(SQL_LOGGER, "INFO") as logs:
            self.session().execute("car.q", {"id": 1, "embedding": vector})              # 미리보기 렌더링
        self.assertIn("-- NOT REPRODUCIBLE AS-IS: vector values are shown as previews", logs.output[0])
        self.query.assert_called_with(self.connection, id=1, embedding=vector)            # 실행은 원본 값


class SensitiveKeyCoverageTests(unittest.TestCase):
    """기본 마스킹 키 목록이 흔한 자격증명 이름을 덮는지 확인한다(2026-10-24 로그 검증에서 api_token 노출 발견)."""

    def test_common_credential_names_are_masked(self):
        query_logger = make_logger(sensitive_keys=DEFAULT_SENSITIVE_KEYS)
        for key in ("api_token", "API_TOKEN", "session_token", "id_token", "secret_key", "aws_secret_access_key",
                    "passphrase", "db_password", "x-api-key", "token"):
            with self.subTest(key=key):
                self.assertTrue(query_logger.is_sensitive_key(key))

    def test_ordinary_names_are_not_masked(self):
        query_logger = make_logger(sensitive_keys=DEFAULT_SENSITIVE_KEYS)
        for key in ("token_count", "tokenizer", "broken", "tokens", "term_norm", "rcp_id", "limit"):
            with self.subTest(key=key):
                self.assertFalse(query_logger.is_sensitive_key(key))

    def test_api_token_value_does_not_reach_cypher_or_params_line(self):
        query_logger = make_logger(sensitive_keys=DEFAULT_SENSITIVE_KEYS)
        parameters = {"term_norm": "두부", "api_token": "S-API", "options": {"session_token": "S-SESSION"}}
        before = copy.deepcopy(parameters)
        text = render_cypher_params(query_logger, "RETURN $term_norm", parameters)
        self.assertNotIn("S-API", text)
        self.assertNotIn("S-SESSION", text)
        self.assertIn(":param term_norm => '두부';", text)
        self.assertEqual(parameters, before)                       # 원본 파라미터는 그대로


class CommonLoggerDependencyTests(unittest.TestCase):
    """공통 QueryLogger가 DB 전용 라이브러리 없이 import되는지 확인한다."""

    def test_query_logger_imports_without_database_packages(self):
        """neo4j/psycopg/pgvector/aiosql/sqlalchemy import를 막은 별도 프로세스에서 query_logger를 로드한다."""
        # region [Python 설명] sys.meta_path로 import 막기와 subprocess
        # `sys.meta_path`의 finder는 모듈을 찾을 때 먼저 호출된다. `find_spec`에서 ImportError를 내면
        # 해당 패키지가 설치되어 있어도 import가 실패한 것처럼 만들 수 있다.
        # 현재 테스트 프로세스에는 이미 import된 모듈이 남아 있으므로, `subprocess.run([sys.executable, "-c", code])`로
        # 깨끗한 새 Python 프로세스에서 검사한다. `returncode == 0`이면 오류 없이 끝난 것이다.
        # endregion
        src = Path(__file__).resolve().parents[2]
        code = (
            "import sys\n"
            "class Block:\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name.split('.')[0] in ('neo4j', 'psycopg', 'psycopg_pool', 'pgvector', 'aiosql', 'sqlalchemy'):\n"
            "            raise ImportError('blocked ' + name)\n"
            "sys.meta_path.insert(0, Block())\n"
            f"sys.path.insert(0, {str(src)!r})\n"
            "import importlib.util\n"
            f"spec = importlib.util.spec_from_file_location('query_logger', {str(src / 'common' / 'query_logger.py')!r})\n"
            "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
            "print(module.QueryLogger.LOG_MODES)\n"
        )
        completed = subprocess.run([sys.executable, "-c", code], cwd=src, capture_output=True,
                                   text=True, encoding="utf-8", check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("combined", completed.stdout)


class OptionalNeo4jImportTests(unittest.TestCase):
    """neo4j 패키지가 없는 환경에서도 Neo4jDbSession 모듈을 import·사용할 수 있는지 확인한다."""

    def test_session_and_logger_import_without_neo4j_package(self):
        """neo4j import를 막은 별도 프로세스에서 세션 생성과 로그 렌더링 함수를 실행한다."""
        src = Path(__file__).resolve().parents[2]
        code = (
            "import sys\n"
            "class Block:\n"
            "    def find_spec(self, name, path=None, target=None):\n"
            "        if name == 'neo4j' or name.startswith('neo4j.'):\n"
            "            raise ImportError('blocked neo4j')\n"
            "sys.meta_path.insert(0, Block())\n"
            f"sys.path.insert(0, {str(src)!r})\n"
            "from pathlib import Path\n"
            "from tempfile import TemporaryDirectory\n"
            "from common.neo4j_db_session import Neo4jDbSession, format_graph_value, render_cypher_params\n"
            "with TemporaryDirectory() as d:\n"
            "    Path(d, 'a.cypher').write_text('// name: q\\nRETURN 1', encoding='utf-8')\n"
            "    s = Neo4jDbSession(mapper_root=d)\n"
            "    print(render_cypher_params(s.query_logger, 'RETURN $x', {'x': 1}).splitlines()[0])\n"
            "    print(format_graph_value({'a': [1]}))\n"
            "print('neo4j' in sys.modules)\n"
        )
        completed = subprocess.run([sys.executable, "-c", code], cwd=src, capture_output=True,
                                   text=True, encoding="utf-8", check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.split(), [":param", "x", "=>", "1;", "{a:", "[1]}", "False"])


if __name__ == "__main__":
    unittest.main()
