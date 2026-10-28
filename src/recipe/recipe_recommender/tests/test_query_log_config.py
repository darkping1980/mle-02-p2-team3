"""개발용 SQL/Cypher 터미널 로그 설정과 DB별 로그 렌더링 재현 테스트.

    Mock 기반   스위치 판정(환경변수 > 로컬 개발 기본값), logging 설정의 멱등성, Neo4j/PostgreSQL 세션의 로그 모드 선택.
    실제 DB     ``LiveQueryLogAppTests``: 실제 streamlit_app.py에서 모드 A 추천·모드 B 조회 버튼을 눌러 로그 출력 여부 확인
                (AuraDB 읽기, LLM 미사용). ``LiveInlineReplayTests``: 로그에 찍힌 쿼리 텍스트를 파라미터 없이 다시 실행해
                프로그램 결과와 비교(Neo4j 인라인 Cypher는 READ 세션, PostgreSQL mogrify SQL은 READ ONLY 트랜잭션).
"""

from __future__ import annotations

import logging
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

import recipe_recommender.config as config  # noqa: E402
from recipe_recommender.config import (  # noqa: E402
    QUERY_LOG_ENV, QUERY_LOGGER_NAMES, configure_query_logging, load_project_environment,
    local_dev_query_log_default, query_log_enabled,
)

load_project_environment()
APP_PATH = str(TASK_DIR / "streamlit_app.py")
DIVIDER = "=" * 72


def reset_query_loggers():
    """configure_query_logging이 바꾼 logger 상태와 '이 프로세스에서 켬' 표시를 되돌린다."""
    config._query_log_active = False
    for name in QUERY_LOGGER_NAMES:
        logger = logging.getLogger(name)
        for handler in [h for h in logger.handlers if getattr(h, "recipe_query_log", False)]:
            logger.removeHandler(handler)
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def without_env():
    """RECIPE_QUERY_LOG를 지운 환경(테스트 종료 시 원래 값 복원)."""
    patcher = patch.dict(os.environ, {}, clear=False)
    patcher.start()
    os.environ.pop(QUERY_LOG_ENV, None)
    return patcher


class QueryLogSwitchTests(unittest.TestCase):
    def setUp(self):
        reset_query_loggers()

    def tearDown(self):
        reset_query_loggers()

    def test_env_value_wins_over_default(self):
        for value, default, expected in (("1", False, True), ("TRUE", False, True), (" on ", False, True),
                                         ("yes", False, True), ("0", True, False), ("off", True, False),
                                         ("false", True, False)):
            with self.subTest(value=value, default=default), patch.dict(os.environ, {QUERY_LOG_ENV: value}):
                self.assertEqual(query_log_enabled(default), expected)

    def test_without_env_the_default_decides(self):
        patcher = without_env()
        self.addCleanup(patcher.stop)
        self.assertFalse(query_log_enabled())
        self.assertTrue(query_log_enabled(default=True))
        self.assertFalse(configure_query_logging())                 # CLI 기본값: 꺼짐
        for name in QUERY_LOGGER_NAMES:
            self.assertFalse(any(getattr(h, "recipe_query_log", False) for h in logging.getLogger(name).handlers))

    def test_local_dev_default_follows_env_file_and_source_constant(self):
        with patch.object(config, "is_local_dev", return_value=True):
            self.assertTrue(local_dev_query_log_default())
            with patch.object(config, "LOCAL_DEV_QUERY_LOG_DEFAULT", False):
                self.assertFalse(local_dev_query_log_default())
        with patch.object(config, "is_local_dev", return_value=False):       # Streamlit Cloud: .env 없음
            self.assertFalse(local_dev_query_log_default())

    def test_enabling_sets_info_and_one_handler_per_logger(self):
        with patch.dict(os.environ, {QUERY_LOG_ENV: "1"}):
            self.assertTrue(configure_query_logging())
            self.assertTrue(configure_query_logging())            # Streamlit 재실행처럼 반복 호출
        for name in QUERY_LOGGER_NAMES:
            logger = logging.getLogger(name)
            self.assertEqual(logger.level, logging.INFO)
            self.assertEqual(sum(getattr(h, "recipe_query_log", False) for h in logger.handlers), 1)
            self.assertFalse(logger.propagate)

    def test_explicit_off_after_on_disables_extra_lookup_gate(self):
        with patch.dict(os.environ, {QUERY_LOG_ENV: "1"}):
            self.assertTrue(configure_query_logging())
            self.assertTrue(config.query_logging_active())
        with patch.dict(os.environ, {QUERY_LOG_ENV: "0"}):
            self.assertFalse(configure_query_logging(default=True))
            self.assertFalse(config.query_logging_active())

    def test_sessions_follow_the_process_decision(self):
        from recipe_recommender.database import create_recipe_sql_session
        from recipe_recommender.recipe_graph_repository import RecipeGraphRepository

        patcher = without_env()
        self.addCleanup(patcher.stop)
        with patch("common.postgres_db_session.DatabaseManager", Mock()):
            self.assertEqual(RecipeGraphRepository(driver=Mock(), database="neo4j").mapper.cypher_log_mode, "none")
            self.assertEqual(create_recipe_sql_session().sql_log_mode, "none")
            self.assertTrue(configure_query_logging(default=True))           # Streamlit 앱의 로컬 개발 기본값
            self.assertEqual(RecipeGraphRepository(driver=Mock(), database="neo4j").mapper.cypher_log_mode, "combined")
            self.assertEqual(create_recipe_sql_session().sql_log_mode, "combined")
            self.assertEqual(create_recipe_sql_session(sql_log=False).sql_log_mode, "none")   # 명시값 우선
        with patch.dict(os.environ, {QUERY_LOG_ENV: "0"}):                    # 명시적으로 끄면 끔
            self.assertEqual(RecipeGraphRepository(driver=Mock(), database="neo4j").mapper.cypher_log_mode, "none")


class PostgresRecommendationLogCheckTests(unittest.TestCase):
    """가짜 그래프와 SQL 세션으로 추천 버튼의 추가 SELECT 조건을 검증한다."""

    def setUp(self):
        import streamlit as st

        reset_query_loggers()
        st.cache_resource.clear()

    def tearDown(self):
        import streamlit as st

        st.cache_resource.clear()
        reset_query_loggers()

    def click_recommend(self, sql_session):
        from streamlit.testing.v1 import AppTest

        from recipe_recommender.tests.test_streamlit_app import _ConnectedFakeGraph

        with patch("recipe_recommender.recipe_graph_repository.RecipeGraphRepository", _ConnectedFakeGraph), \
             patch("recipe_recommender.pantry_graphrag.create_llm", return_value=None), \
             patch("recipe_recommender.database.create_recipe_sql_session", return_value=sql_session) as factory:
            app = AppTest.from_file(APP_PATH, default_timeout=60).run()
            app.form_submit_button[0].click().run()
        self.assertFalse(app.exception)
        self.assertIn("두부달걀덮밥", "\n".join(str(item.value) for item in app.markdown))
        return app, factory

    def test_log_on_uses_existing_search_service_and_four_selects(self):
        session = Mock()
        session.select_one.return_value = {"rcpId": "r2", "rcpSeq": "28"}
        session.select_list.side_effect = [[], [], []]
        with patch.dict(os.environ, {QUERY_LOG_ENV: "1"}):
            _, factory = self.click_recommend(session)
        factory.assert_called_once_with()
        session.select_one.assert_called_once_with(
            "recipe.find_recipe_detail", {"RCP_SEQ": None, "RCP_ID": "r2"})
        self.assertEqual([call.args[0] for call in session.select_list.call_args_list], [
            "recipe.list_recipe_steps", "recipe.list_recipe_ingredients", "recipe.list_recipe_unmatched_stagings",
        ])
        self.assertEqual(session.execute.call_count, 0)
        self.assertEqual(session.execute_many.call_count, 0)

    def test_local_default_without_env_runs_postgres_selects(self):
        patcher = without_env()
        self.addCleanup(patcher.stop)
        session = Mock()
        session.select_one.return_value = {"rcpId": "r2", "rcpSeq": "28"}
        session.select_list.side_effect = [[], [], []]
        with patch("recipe_recommender.config.is_local_dev", return_value=True), \
             patch("recipe_recommender.config.load_project_environment", return_value=None):
            _, factory = self.click_recommend(session)
        factory.assert_called_once_with()
        self.assertEqual(session.select_one.call_count + session.select_list.call_count, 4)

    def test_log_off_and_cloud_default_do_not_create_postgres_session(self):
        for env, local in (("0", True), (None, False)):
            with self.subTest(env=env, local=local):
                self.setUp()
                setting = {QUERY_LOG_ENV: env} if env is not None else {}
                with patch.dict(os.environ, setting), \
                     patch("recipe_recommender.config.is_local_dev", return_value=local), \
                     patch("recipe_recommender.config.load_project_environment", return_value=None):
                    if env is None:
                        os.environ.pop(QUERY_LOG_ENV, None)
                    _, factory = self.click_recommend(Mock())
                factory.assert_not_called()

    def test_postgres_failure_keeps_neo4j_recommendations(self):
        session = Mock()
        session.select_one.side_effect = ConnectionError("PostgreSQL unavailable")
        with patch.dict(os.environ, {QUERY_LOG_ENV: "1"}), self.assertLogs("streamlit_app", "WARNING") as logs:
            app, _ = self.click_recommend(session)
        self.assertTrue(any("PostgreSQL log check failed" in item for item in logs.output))
        self.assertFalse(app.error)
        session.select_one.assert_called_once()


def query_blocks(lines: list[str], statement: str) -> list[str]:
    """assertLogs 출력에서 statement의 QUERY 로그 본문(구분선 사이)을 꺼낸다."""
    return [line.split(DIVIDER)[1].strip("\n") for line in lines if f"QUERY [{statement}]" in line]


@unittest.skipUnless(os.getenv("NEO4J_URI"), "NEO4J_URI is not configured")
class LiveQueryLogAppTests(unittest.TestCase):
    """실제 앱 버튼 클릭 → Neo4j 실행 Cypher가 인라인 형식으로 logger에 기록되는지(AuraDB 읽기 전용, LLM 미사용)."""

    def setUp(self):
        import streamlit as st

        st.cache_resource.clear()                                # 로그 모드는 Repository 생성 시 정해진다
        reset_query_loggers()

    def tearDown(self):
        import streamlit as st

        st.cache_resource.clear()
        reset_query_loggers()

    def click_buttons(self):
        from streamlit.testing.v1 import AppTest

        with patch("recipe_recommender.pantry_graphrag.create_llm", return_value=None):
            at = AppTest.from_file(APP_PATH, default_timeout=120).run()
            at.form_submit_button[0].click().run()                         # 모드 A 레시피 추천
            at.segmented_control(key="app_mode").set_value("graph").run()
            at.radio(key="graph_question").set_value("Q3").run()
            at.form_submit_button[0].click().run()                         # 모드 B 그래프 조회
        self.assertFalse(at.exception)
        self.assertFalse(any("실행 Cypher" in e.label for e in at.expander))   # 화면에는 표시하지 않음
        return at

    def logged_queries(self) -> list[str]:
        logger = logging.getLogger("car_search_rag.neo4j")
        with self.assertLogs("car_search_rag.neo4j", "INFO") as logs:
            logger.info("marker")                                          # assertLogs는 기록이 하나는 있어야 한다
            self.click_buttons()
        return [line for line in logs.output if "QUERY [" in line]

    def test_local_dev_default_logs_inline_cypher(self):
        patcher = without_env()
        self.addCleanup(patcher.stop)
        with patch.object(config, "is_local_dev", return_value=True):
            queries = self.logged_queries()
        self.assertTrue(any("pantry_graphrag.pantry_recommendations_by_coverage" in q for q in queries))   # 모드 A
        q3 = next(q for q in queries if "graph_questions.similar_recipe_categories" in q)                   # 모드 B
        self.assertIn("// inline parameter values for log only", q3)
        self.assertRegex(q3, r"MATCH \(base:rcp \{rcp_id: '\d{8}_\d{6}'\}\)")
        self.assertIn("WHERE common_count >= 3", q3)

    def test_cloud_default_and_explicit_off_do_not_log(self):
        patcher = without_env()
        self.addCleanup(patcher.stop)
        with patch.object(config, "is_local_dev", return_value=False):        # Streamlit Cloud(.env 없음)
            self.assertEqual(self.logged_queries(), [])
        import streamlit as st

        st.cache_resource.clear()
        reset_query_loggers()
        with patch.dict(os.environ, {QUERY_LOG_ENV: "0"}), patch.object(config, "is_local_dev", return_value=True):
            self.assertEqual(self.logged_queries(), [])

    @unittest.skipUnless(os.getenv("DB_URL"), "DB_URL is not configured")
    def test_recommend_button_logs_four_postgres_selects_with_cypher(self):
        """실제 추천 버튼에서 두 DB의 조회 로그가 같은 실행 경로에 남는지 확인한다."""
        from streamlit.testing.v1 import AppTest

        with patch.dict(os.environ, {QUERY_LOG_ENV: "1"}), \
             patch("recipe_recommender.pantry_graphrag.create_llm", return_value=None), \
             self.assertLogs("car_search_rag.sql", "INFO") as sql_logs, \
             self.assertLogs("car_search_rag.neo4j", "INFO") as graph_logs:
            app = AppTest.from_file(APP_PATH, default_timeout=60).run()
            app.form_submit_button[0].click().run()
        self.assertFalse(app.exception)
        sql_ids = [line.split("QUERY [", 1)[1].split("]", 1)[0]
                   for line in sql_logs.output if "QUERY [" in line]
        self.assertEqual(sql_ids, [
            "recipe.find_recipe_detail", "recipe.list_recipe_steps",
            "recipe.list_recipe_ingredients", "recipe.list_recipe_unmatched_stagings",
        ])
        cypher = [line for line in graph_logs.output if "QUERY [" in line]
        self.assertTrue(any("pantry_recommendations_by_coverage" in line for line in cypher))
        # 기본 추천 5건: 입력어 후보 3 + 추천 1 + 근거 5 + 조리 단계 1.
        self.assertEqual(len(cypher), 10)
        self.assertFalse(any("PostgreSQL" in str(item.value) for item in app.error))


@unittest.skipUnless(os.getenv("NEO4J_URI") and os.getenv("DB_URL"), "NEO4J_URI and DB_URL are required")
class LiveInlineReplayTests(unittest.TestCase):
    """로그 텍스트만으로 같은 결과가 나오는지: 파라미터 없이 다시 실행해 프로그램 결과와 비교한다(읽기 전용)."""

    NEO4J_TRICKY = (
        "// name: tricky\n"
        "// header comment mentions $id and $id2\n"
        "WITH $id AS id, $id2 AS id2 /* $id2 in block comment */\n"
        "RETURN id, id2, '$id literal' AS lit, \"say $id2\" AS dq, 'it\\'s $id' AS esc, $`odd name` AS odd,\n"
        "       $m AS m, $l AS l, $neg AS neg, $f AS f, $flag AS flag, $nothing AS nothing, $d AS d,\n"
        "       {`$id`: 1}.`$id` AS backtick_key\n")
    NEO4J_PARAMS = {"id": "두부", "id2": "O'Brien \\ \"x\"", "odd name": "공백 이름", "m": {"이름": "두부", "n": 1},
                    "l": [1, "a", None, True], "neg": -7, "f": 1e-12, "flag": False, "nothing": None}
    PG_TRICKY = (
        "-- name: tricky\n"
        "-- header comment mentions :id and :id2\n"
        "SELECT CAST(:id AS integer) AS a,\n"
        "       CAST(:id2 AS integer) AS b,\n"
        "       :id2::text AS b_text,\n"
        "       ':id 문자열' AS lit,\n"
        "       CAST(:name AS text) AS name,\n"
        "       :flag::boolean AS flag,\n"
        "       CAST(:nothing AS text) AS nothing,\n"
        "       CAST(:day AS date) AS day,\n"
        "       CAST(:tags AS text[]) AS tags,\n"
        "       '50%%' AS pct,\n"
        "       t.\"col:id\" AS quoted_identifier\n"
        "FROM (SELECT 1 AS \"col:id\") AS t -- trailing comment :id2\n")

    def test_neo4j_real_mapper_queries_replay_from_inline_log(self):
        from neo4j import READ_ACCESS

        from recipe_recommender.recipe_graph_repository import RecipeGraphRepository

        reset_query_loggers()
        self.addCleanup(reset_query_loggers)
        with patch.dict(os.environ, {QUERY_LOG_ENV: "1"}):
            graph = RecipeGraphRepository()
        self.addCleanup(graph.close)
        base = graph.query_example("find_recipe_by_name", {"rcp_nm": "된장 두부찌개"})[0]["rcp_id"]
        cases = [
            ("recipe_graph_queries.recipes_by_ingredient_term", {"term_norm": "계란"}),
            ("recipe_graph_queries.similar_recipes", {"rcp_id": base}),
            ("recipe_graph_queries.recipe_steps", {"rcp_ids": [base]}),
            ("recipe_graph_queries.recipes_using_ingredient", {"ingr_id": "20261022_000042", "exclude_rcp_id": None}),
            ("pantry_graphrag.pantry_recommendations_by_coverage", {"names_norm": ["계란", "두부", "양파"], "limit": 20}),
            ("graph_questions.similar_recipe_categories", {"rcp_id": base, "min_common": 3}),
            ("graph_questions.category_ingredients", {"rcp_cat_nm": "반찬", "limit": 10}),
        ]
        with graph.driver.session(database=graph.database, default_access_mode=READ_ACCESS) as session:
            for statement, parameters in cases:
                with self.subTest(statement=statement):
                    with self.assertLogs("car_search_rag.neo4j", "INFO") as logs:
                        rows = graph.mapper.select_list(statement, parameters)
                    text = query_blocks(logs.output, statement)[0]
                    self.assertTrue(text.startswith("// inline parameter values for log only"))
                    self.assertNotIn(":param", text)
                    replay = [record.data() for record in session.run(text)]           # 파라미터 없이 실행
                    self.assertEqual(normalize(replay), normalize(rows))

    def test_neo4j_tricky_tokens_replay(self):
        from neo4j import READ_ACCESS

        from common.neo4j_db_session import Neo4jDbSession
        from recipe_recommender.neo4j_connection import create_neo4j_driver

        driver = create_neo4j_driver()
        self.addCleanup(driver.close)
        database = os.getenv("NEO4J_DATABASE") or None
        with TemporaryDirectory() as folder:
            Path(folder, "logcheck.cypher").write_text(self.NEO4J_TRICKY, encoding="utf-8")
            session = Neo4jDbSession(mapper_root=folder, driver=driver, database=database, cypher_log_mode="combined")
            parameters = dict(self.NEO4J_PARAMS, d=__import__("datetime").date(2026, 10, 24))
            with self.assertLogs("car_search_rag.neo4j", "INFO") as logs:
                rows = session.select_list("logcheck.tricky", parameters)
        text = query_blocks(logs.output, "logcheck.tricky")[0]
        self.assertIn("// header comment mentions $id and $id2", text)          # 주석 안은 그대로
        self.assertIn("'$id literal' AS lit", text)                              # 문자열 안은 그대로
        self.assertIn("{`$id`: 1}.`$id` AS backtick_key", text)                  # 백틱 식별자 안은 그대로
        self.assertIn("WITH '두부' AS id, 'O\\'Brien \\\\ \"x\"' AS id2", text)    # $id / $id2 구분
        self.assertIn("(-7) AS neg", text)
        with driver.session(database=database, default_access_mode=READ_ACCESS) as replay_session:
            replay = [record.data() for record in replay_session.run(text)]
        self.assertEqual(replay, rows)
        self.assertEqual(rows[0]["lit"], "$id literal")

    def test_postgres_mogrify_sql_replays_including_tricky_syntax(self):
        import datetime

        from recipe_recommender.database import create_recipe_sql_session

        reset_query_loggers()
        self.addCleanup(reset_query_loggers)
        with TemporaryDirectory() as folder:
            Path(folder, "logcheck.sql").write_text(self.PG_TRICKY, encoding="utf-8")
            from common.postgres_db_session import PostgresDbSession

            real = create_recipe_sql_session(sql_log=True)
            self.addCleanup(real.database_manager.close)
            session = PostgresDbSession(mapper_root=folder, database_manager=real.database_manager,
                                        sql_log_mode="combined", camel_case_keys=False)
            parameters = {"id": 7, "id2": 8, "name": "O'Brien 두부 \\ :id", "flag": True, "nothing": None,
                          "day": datetime.date(2026, 10, 24), "tags": ["두부", "it's", None]}
            cases = [("logcheck.tricky", parameters),
                     ("recipe.list_recipes", {"RCP_NM": "두부", "RCP_CAT_NM": None, "COOK_MTHD_CD": "찌기",
                                              "LIMIT": 5, "OFFSET": 0})]
            for statement, params in cases:
                target = session if statement.startswith("logcheck") else real
                with self.subTest(statement=statement):
                    with self.assertLogs("car_search_rag.sql", "INFO") as logs:
                        rows = target.select_list(statement, params)
                    text = query_blocks(logs.output, statement)[0]
                    self.assertNotIn("%(", text.split("--", 1)[0])
                    with real.database_manager.connect(camel_case_keys=target.camel_case_keys) as connection:
                        connection.execute("BEGIN TRANSACTION READ ONLY")
                        try:
                            replay = [dict(row) for row in connection.execute(text).fetchall()]
                        finally:
                            connection.rollback()
                    self.assertEqual(replay, rows)

    def test_postgres_recipe_detail_four_selects_replay(self):
        """추천 버튼과 동일한 상세 조회의 SQL 네 개를 READ ONLY로 재실행한다."""
        from recipe_recommender.database import create_recipe_sql_session
        from recipe_recommender.recipe_search_service import RecipeSearchService

        session = create_recipe_sql_session(sql_log=True)
        self.addCleanup(session.database_manager.close)
        # 기존 조회 테스트가 사용하는 식약처 원본 번호. SELECT로 내부 ID만 확인한다.
        recipe = session.select_one("recipe.find_recipe_detail", {"RCP_SEQ": "28", "RCP_ID": None})
        self.assertIsNotNone(recipe)
        rcp_id = recipe["rcpId"]
        service = RecipeSearchService(sql_session=session)
        statements = (
            ("recipe.find_recipe_detail", "select_one", {"RCP_SEQ": None, "RCP_ID": rcp_id}),
            ("recipe.list_recipe_steps", "select_list", {"RCP_ID": rcp_id}),
            ("recipe.list_recipe_ingredients", "select_list", {"RCP_ID": rcp_id}),
            ("recipe.list_recipe_unmatched_stagings", "select_list", {"RCP_ID": rcp_id}),
        )
        with self.assertLogs("car_search_rag.sql", "INFO") as logs:
            detail = service.get_recipe_detail(rcp_id=rcp_id)
        self.assertEqual(len([line for line in logs.output if "QUERY [" in line]), 4)
        expected = (detail["recipe"], detail["steps"], detail["ingredients"], detail["unmatchedIngredients"])
        for (statement, method, parameters), bound_result in zip(statements, expected):
            with self.subTest(statement=statement):
                self.assertEqual(getattr(session, method)(statement, parameters), bound_result)
                sql = query_blocks(logs.output, statement)[0]
                self.assertNotIn("%(RCP_ID)s", sql)
                self.assertIn(rcp_id, sql)
                with session.database_manager.connect(camel_case_keys=session.camel_case_keys) as connection:
                    connection.execute("BEGIN TRANSACTION READ ONLY")
                    try:
                        cursor = connection.execute(sql)  # 로그의 SQL만; 파라미터를 다시 전달하지 않는다.
                        rows = [dict(row) for row in cursor.fetchall()]
                    finally:
                        connection.rollback()
                replay = rows[0] if method == "select_one" and rows else rows
                self.assertEqual(replay, bound_result)


def normalize(rows):
    """collect() 목록의 원소 순서 차이만 없앤 비교용 사본."""
    def norm(value):
        if isinstance(value, list):
            items = [norm(item) for item in value]
            return sorted(items, key=repr)
        if isinstance(value, dict):
            return {key: norm(item) for key, item in value.items()}
        return value
    return [norm(row) for row in rows]


if __name__ == "__main__":
    unittest.main()
