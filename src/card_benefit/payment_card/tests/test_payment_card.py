"""payment_card 단위 테스트(DB 연결 없음)와 명시적으로만 실행하는 테스트 DB 통합 테스트.

실행(src/card_benefit 폴더에서):
    uv run python -m unittest discover -s payment_card/tests -v

통합 테스트는 환경변수 ``PAYMENT_CARD_TEST_DB_URL`` 이 있을 때만 실행한다.
그 DB에 ``card_benefit/sql/schema.sql`` 이 적용되어 있어야 하며, 등록한 행은 rollback으로 남기지 않는다.
"""

from __future__ import annotations

import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from common.postgres_db_session import PostgresDbSession
from payment_card import main as cli
from payment_card.models import Card, NewCard
from payment_card.repository import MAPPER_ROOT, CardRepository

CREATED_AT = datetime(2026, 10, 29, 9, 0, tzinfo=timezone.utc)


def card_row(card_id: int = 1, card_type: str = "CREDIT") -> dict:
    """``camel_case_keys=False`` 세션이 돌려주는 형태의 결과 행."""
    return {
        "card_id": card_id, "issuer": "하나카드", "card_name": "테스트 신용카드 A",
        "card_type": card_type, "created_at": CREATED_AT,
    }


class NewCardValidationTests(unittest.TestCase):
    def test_credit_and_debit_are_accepted(self):
        for card_type in ("CREDIT", "DEBIT"):
            card = NewCard(" 하나카드 ", "테스트 카드", card_type)
            self.assertEqual((card.issuer, card.card_type), ("하나카드", card_type))

    def test_invalid_card_type_is_rejected(self):
        for card_type in ("credit", "PREPAID", ""):
            with self.subTest(card_type=card_type), self.assertRaises(ValueError):
                NewCard("하나카드", "테스트 카드", card_type)

    def test_missing_required_value_is_rejected(self):
        for issuer, card_name in ((None, "테스트 카드"), ("  ", "테스트 카드"), ("하나카드", "")):
            with self.subTest(issuer=issuer, card_name=card_name), self.assertRaises(ValueError):
                NewCard(issuer, card_name, "CREDIT")


class MapperCompatibilityTests(unittest.TestCase):
    def test_common_session_registers_payment_card_mapper_without_connecting(self):
        session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")
        self.assertEqual(list(session.mappers), ["payment_card"])            # 패키지 안의 named SQL은 payment_card.sql뿐이다
        self.assertLessEqual({"insert_card", "list_cards", "find_card"}, set(session.mappers["payment_card"].available_queries))
        self.assertEqual(session.database_manager._pools, {})                 # pool은 첫 SQL 실행 전까지 열리지 않는다
        insert_sql = session._query("payment_card.insert_card").sql
        for name in ("issuer", "card_name", "card_type"):
            self.assertIn(f"%({name})s", insert_sql)                           # 값은 바인딩 파라미터로 전달된다


class CardRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock(spec=PostgresDbSession)
        self.repository = CardRepository(self.session)

    def test_insert_card_binds_parameters_and_returns_card(self):
        self.session.execute.return_value = [card_row()]
        card = self.repository.insert_card(NewCard("하나카드", "테스트 신용카드 A", "CREDIT"))
        self.session.execute.assert_called_once_with(
            "payment_card.insert_card",
            {"issuer": "하나카드", "card_name": "테스트 신용카드 A", "card_type": "CREDIT"},
        )
        self.assertEqual(card, Card(**card_row()))

    def test_list_and_find(self):
        self.session.select_list.return_value = [card_row(1), card_row(2, "DEBIT")]
        self.assertEqual([c.card_id for c in self.repository.list_cards()], [1, 2])
        self.session.select_list.assert_called_once_with("payment_card.list_cards")

        self.session.select_one.return_value = card_row(2, "DEBIT")
        self.assertEqual(self.repository.find_card(2).card_type, "DEBIT")
        self.session.select_one.assert_called_once_with("payment_card.find_card", {"card_id": 2})

        self.session.select_one.return_value = None
        self.assertIsNone(self.repository.find_card(99))


class CliTests(unittest.TestCase):
    def run_cli(self, argv, session=None):
        """``PostgresDbSession`` 을 가짜로 바꿔 CLI를 실행하고 (종료 코드, stdout, stderr, 세션 클래스)를 돌려준다."""
        session = session or MagicMock(spec=PostgresDbSession)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(cli, "PostgresDbSession", return_value=session) as session_class, \
                redirect_stdout(out), redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue(), session_class

    def test_help_exits_normally(self):
        with redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as raised:
            cli.parse_args(["--help"])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn("register", out.getvalue())

    def test_register_prints_card_and_closes_pool(self):
        session = MagicMock(spec=PostgresDbSession)
        session.database_manager = MagicMock()
        session.execute.return_value = [card_row()]
        code, out, _, session_class = self.run_cli(
            ["register", "--issuer", "하나카드", "--card-name", "테스트 신용카드 A", "--card-type", "CREDIT"], session
        )
        self.assertEqual(code, 0)
        self.assertIn("1\tCREDIT\t하나카드\t테스트 신용카드 A", out)
        session_class.assert_called_once_with(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")
        session.database_manager.close.assert_called_once()

    def test_blank_input_is_rejected_before_db_session(self):
        code, _, err, session_class = self.run_cli(
            ["register", "--issuer", " ", "--card-name", "A", "--card-type", "DEBIT"]
        )
        self.assertEqual(code, 1)
        self.assertIn("issuer is required", err)
        session_class.assert_not_called()

    def test_invalid_card_type_is_rejected_by_argparse(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            cli.parse_args(["register", "--issuer", "A", "--card-name", "B", "--card-type", "GOLD"])
        self.assertEqual(raised.exception.code, 2)

    def test_get_missing_card_returns_1(self):
        session = MagicMock(spec=PostgresDbSession)
        session.database_manager = MagicMock()
        session.select_one.return_value = None
        code, _, err, _ = self.run_cli(["get", "--card-id", "99"], session)
        self.assertEqual(code, 1)
        self.assertIn("card_id=99", err)
        session.database_manager.close.assert_called_once()


class _Rollback(Exception):
    """통합 테스트 데이터를 남기지 않으려고 트랜잭션을 되돌리는 신호."""


@unittest.skipUnless(os.getenv("PAYMENT_CARD_TEST_DB_URL"), "PAYMENT_CARD_TEST_DB_URL이 없으면 실DB 통합 테스트를 건너뛴다")
class TestDatabaseIntegrationTests(unittest.TestCase):
    def test_register_find_list_in_rolled_back_transaction(self):
        with patch.dict(os.environ, {"DB_URL": os.environ["PAYMENT_CARD_TEST_DB_URL"]}):
            session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")
            repository = CardRepository(session)
            try:
                with self.assertRaises(_Rollback), session.transaction():
                    created = repository.insert_card(NewCard("테스트카드사", "통합 테스트 체크카드", "DEBIT"))
                    self.assertEqual(repository.find_card(created.card_id), created)
                    self.assertIn(created, repository.list_cards())
                    raise _Rollback
            finally:
                session.database_manager.close()


if __name__ == "__main__":
    unittest.main()
