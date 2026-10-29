"""카드 상품 SQL mapper(``payment_card.sql``)를 호출하는 DB 접근 클래스."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from common.postgres_db_session import PostgresDbSession

from .models import Card, NewCard

# PostgresDbSession의 mapper_root(이 패키지 폴더). 하위 폴더까지 ``-- name:`` 이 있는 *.sql을 등록하며,
# 파일명 payment_card.sql이 namespace ``payment_card`` 가 된다.
MAPPER_ROOT = Path(__file__).resolve().parent


class CardRepository:
    """``payment_card.*`` statement를 실행하고 결과 행을 ``Card`` 로 바꾼다.

    DB 연결·트랜잭션·종료는 주입받은 ``sql_session`` 이 관리한다.
    조회 결과 key를 컬럼명 그대로 받도록 ``camel_case_keys=False`` 세션을 전달한다.
    """

    def __init__(self, sql_session: PostgresDbSession):
        self.sql_session = sql_session

    def insert_card(self, card: NewCard) -> Card:
        """카드 한 건을 등록하고 DB가 채운 ``card_id`` · ``created_at`` 을 포함해 반환한다."""
        rows = self.sql_session.execute("payment_card.insert_card", asdict(card))
        return Card(**rows[0])

    def list_cards(self) -> list[Card]:
        """등록된 카드를 ``card_id`` 순으로 반환한다."""
        return [Card(**row) for row in self.sql_session.select_list("payment_card.list_cards")]

    def find_card(self, card_id: int) -> Card | None:
        """``card_id`` 로 카드 한 건을 찾고, 없으면 ``None`` 을 반환한다."""
        row = self.sql_session.select_one("payment_card.find_card", {"card_id": card_id})
        return Card(**row) if row else None
