"""검색 전용(autocommit·읽기 전용) DatabaseManager와 PostgresDbSession 가드 테스트. 실제 DB에 접속하지 않는다."""
import unittest
from pathlib import Path
from unittest import mock

from common import database_manager as dm
from common.postgres_db_session import PostgresDbSession

MAPPER_ROOT = Path(__file__).resolve().parents[2] / "card_benefit" / "payment_card" / "db_pipeline"


class FakePool:
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakePool.created.append(self)

    def wait(self): pass
    def close(self): pass


class PoolOptionTests(unittest.TestCase):
    def setUp(self):
        FakePool.created.clear()
        patcher = mock.patch.object(dm, "ConnectionPool", FakePool)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_manager_keeps_existing_connection_options(self):
        dm.DatabaseManager()._get_pool(False)
        kwargs = FakePool.created[0].kwargs["kwargs"]
        self.assertEqual(set(kwargs), {"row_factory"})              # autocommit·options 없음 = 기존 동작

    def test_search_manager_uses_autocommit_and_server_read_only(self):
        manager = dm.DatabaseManager(autocommit=True, read_only=True)
        manager._get_pool(False)
        kwargs = FakePool.created[0].kwargs["kwargs"]
        self.assertTrue(kwargs["autocommit"])
        self.assertNotIn("options", kwargs)            # pooler가 startup options를 적용하지 않으므로 세션 SET으로 건다
        self.assertIs(kwargs["row_factory"], dm.dict_row)
        self.assertIs(FakePool.created[0].kwargs["configure"], dm._configure_read_only_connection)

    def test_default_manager_keeps_existing_configure(self):
        dm.DatabaseManager()._get_pool(False)
        self.assertIs(FakePool.created[0].kwargs["configure"], dm._configure_connection)

    def test_read_only_configure_registers_vector_then_sets_session_read_only(self):
        conn = mock.MagicMock()
        with mock.patch.object(dm, "register_vector") as register:
            dm._configure_read_only_connection(conn)
        register.assert_called_once_with(conn)
        conn.execute.assert_called_once_with("SET default_transaction_read_only = on")

    def test_pool_is_reused_per_row_factory(self):
        manager = dm.DatabaseManager(autocommit=True, read_only=True)
        self.assertIs(manager._get_pool(False), manager._get_pool(False))
        self.assertEqual(len(FakePool.created), 1)


class ReadOnlySessionGuardTests(unittest.TestCase):
    def session(self, **flags):
        manager = dm.DatabaseManager(**flags)
        manager.connect = mock.MagicMock(side_effect=AssertionError("DB에 접속하면 안 된다"))
        return PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none", database_manager=manager)

    def test_write_and_transaction_are_rejected_before_connecting(self):
        session = self.session(autocommit=True, read_only=True)
        with self.assertRaisesRegex(RuntimeError, "execute\\(\\)"):
            session.execute("embedding_repository.finish_embedding_run", {})
        with self.assertRaisesRegex(RuntimeError, "execute_many"):
            session.execute_many("embedding_repository.update_card_bnft_text", [{}])
        with self.assertRaisesRegex(RuntimeError, "transaction"):
            with session.transaction():
                pass
        session.database_manager.connect.assert_not_called()

    def test_autocommit_only_manager_also_rejects_transaction(self):
        session = self.session(autocommit=True)
        with self.assertRaises(RuntimeError):
            with session.transaction():
                pass

    def test_default_manager_is_not_guarded(self):
        session = self.session()
        session._reject_read_only("execute()")                      # 예외 없음

    def test_mock_manager_attributes_are_not_treated_as_read_only(self):
        session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none",
                                    database_manager=mock.MagicMock())
        session._reject_read_only("execute()")                      # MagicMock의 임의 속성(truthy)은 무시

    def test_connection_helper_is_still_a_context_manager(self):
        import contextlib
        from contextlib import contextmanager

        @contextmanager
        def connect(camel_case_keys=True):
            yield "conn"
        manager = dm.DatabaseManager(autocommit=True, read_only=True)
        manager.connect = connect
        session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none", database_manager=manager)
        self.assertIsInstance(session._connection(), contextlib.AbstractContextManager)
        with session._connection() as connection:                  # 읽기(SELECT) 경로는 막지 않는다
            self.assertEqual(connection, "conn")


if __name__ == "__main__":
    unittest.main()
