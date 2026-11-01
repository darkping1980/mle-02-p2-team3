"""공통 환경변수 로딩과 쿼리 로그 스위치·handler 설정을 검증하는 오프라인 테스트."""

import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from common import query_log_config as config
from common.query_log_config import QUERY_LOGGER_NAMES, attach_query_log_handlers, detach_query_log_handlers, query_log_switch


def reset_loggers():
    for name in QUERY_LOGGER_NAMES:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


class ProjectEnvironmentTests(unittest.TestCase):
    def test_project_root_has_common_package_regardless_of_cwd(self):
        self.assertTrue((config.project_root() / "src" / "common" / "query_log_config.py").is_file())

    def test_env_file_does_not_override_process_value(self):
        with TemporaryDirectory() as folder:
            Path(folder, ".env").write_text("A_FROM_FILE=file\nA_FROM_PROCESS=file\n", encoding="utf-8")
            with patch.object(config, "project_root", return_value=Path(folder)), patch.dict(os.environ, {"A_FROM_PROCESS": "process"}):
                config.load_project_environment()
                self.assertEqual(os.environ["A_FROM_FILE"], "file")
                self.assertEqual(os.environ["A_FROM_PROCESS"], "process")
                os.environ.pop("A_FROM_FILE")

    def test_local_dev_follows_env_file(self):
        with TemporaryDirectory() as folder, patch.object(config, "project_root", return_value=Path(folder)):
            self.assertFalse(config.is_local_dev())
            Path(folder, ".env").write_text("", encoding="utf-8")
            self.assertTrue(config.is_local_dev())


class QueryLogSwitchTests(unittest.TestCase):
    def test_first_variable_with_value_wins(self):
        for values, default, expected in (({}, True, True), ({}, False, False), ({"B": "1"}, False, True), ({"B": "0"}, True, False),
                                          ({"A": "0", "B": "1"}, True, False), ({"A": " ON ", "B": "0"}, False, True),
                                          ({"A": "", "B": "1"}, False, True), ({"A": "  ", "B": "0"}, True, False)):
            with self.subTest(values=values, default=default), patch.dict(os.environ, values):
                for name in ("A", "B"):
                    if name not in values:
                        os.environ.pop(name, None)
                self.assertEqual(query_log_switch(("A", "B"), default), expected)

    def test_only_listed_values_turn_on(self):
        for value, expected in (("1", True), ("TRUE", True), ("yes", True), ("on", True), ("0", False), ("off", False), ("2", False)):
            with self.subTest(value=value), patch.dict(os.environ, {"A": value}):
                self.assertEqual(query_log_switch(("A",), True), expected)


class QueryLogHandlerTests(unittest.TestCase):
    def setUp(self):
        reset_loggers()
        self.addCleanup(reset_loggers)

    def state(self):
        return [(logging.getLogger(n).level, len(logging.getLogger(n).handlers), logging.getLogger(n).propagate) for n in QUERY_LOGGER_NAMES]

    def test_first_run_off_changes_nothing(self):
        sql = logging.getLogger("car_search_rag.sql")
        sql.setLevel(logging.WARNING)                   # CLI가 직접 정한 레벨
        before = self.state()
        detach_query_log_handlers()
        self.assertEqual(self.state(), before)

    def test_attach_twice_keeps_one_handler(self):
        attach_query_log_handlers()
        attach_query_log_handlers()
        self.assertEqual(self.state(), [(logging.INFO, 1, False)] * len(QUERY_LOGGER_NAMES))

    def test_on_off_on_returns_to_each_state(self):
        attach_query_log_handlers()
        detach_query_log_handlers()
        self.assertEqual(self.state(), [(logging.NOTSET, 0, True)] * len(QUERY_LOGGER_NAMES))
        detach_query_log_handlers()                     # 재실행에서 OFF 반복
        self.assertEqual(self.state(), [(logging.NOTSET, 0, True)] * len(QUERY_LOGGER_NAMES))
        attach_query_log_handlers()
        self.assertEqual(self.state(), [(logging.INFO, 1, False)] * len(QUERY_LOGGER_NAMES))

    def test_detach_keeps_handler_added_by_others(self):
        logger = logging.getLogger("car_search_rag.neo4j")
        other = logging.NullHandler()
        logger.addHandler(other)
        attach_query_log_handlers()
        detach_query_log_handlers()
        self.assertEqual(logger.handlers, [other])

    def test_off_stops_output_of_child_logger(self):
        child = logging.getLogger("car_search_rag.neo4j.child")
        attach_query_log_handlers()
        self.assertTrue(child.isEnabledFor(logging.INFO))
        detach_query_log_handlers()
        self.assertFalse(child.isEnabledFor(logging.INFO))


if __name__ == "__main__":
    unittest.main()
