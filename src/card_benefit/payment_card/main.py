"""카드 상품 등록·조회 CLI.

실행 예(src/card_benefit 폴더에서):
    uv run python -m payment_card.main register --issuer 하나카드 --card-name "테스트 신용카드 A" --card-type CREDIT
    uv run python -m payment_card.main list
    uv run python -m payment_card.main get --card-id 1

종료 코드: 0 성공, 1 입력 오류 또는 대상 없음, 2 인자 오류(argparse), 3 DB 오류.
"""

from __future__ import annotations

import argparse
import sys

import psycopg

from common.postgres_db_session import PostgresDbSession

from .models import CARD_TYPES, Card, NewCard
from .repository import MAPPER_ROOT, CardRepository


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """``register`` / ``list`` / ``get`` 하위 명령을 해석한다."""
    parser = argparse.ArgumentParser(prog="payment_card", description="카드 상품 등록·조회")
    commands = parser.add_subparsers(dest="command", required=True)

    register = commands.add_parser("register", help="카드 상품 한 건 등록")
    register.add_argument("--issuer", required=True, help="카드사 (예: 하나카드)")
    register.add_argument("--card-name", required=True, help="카드 상품명")
    register.add_argument("--card-type", required=True, choices=CARD_TYPES, help="CREDIT: 신용카드, DEBIT: 체크카드")

    commands.add_parser("list", help="등록된 카드 목록 조회")

    get = commands.add_parser("get", help="card_id로 카드 한 건 조회")
    get.add_argument("--card-id", required=True, type=int)
    return parser.parse_args(argv)


def format_card(card: Card) -> str:
    """콘솔 출력용 한 줄 문자열."""
    return f"{card.card_id}\t{card.card_type}\t{card.issuer}\t{card.card_name}\t{card.created_at:%Y-%m-%d %H:%M:%S}"


def main(argv: list[str] | None = None) -> int:
    """인자를 검증한 뒤 DB 세션을 열어 명령을 실행하고, 끝나면 연결 pool을 닫는다."""
    args = parse_args(argv)
    try:
        new_card = NewCard(args.issuer, args.card_name, args.card_type) if args.command == "register" else None
    except ValueError as error:
        print(f"입력 오류: {error}", file=sys.stderr)
        return 1

    # 입력 검증을 통과한 뒤에만 세션을 만든다. pool은 첫 SQL 실행 때 열린다.
    sql_session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")
    repository = CardRepository(sql_session)
    try:
        if args.command == "register":
            print(format_card(repository.insert_card(new_card)))
        elif args.command == "list":
            cards = repository.list_cards()
            for card in cards:
                print(format_card(card))
            print(f"총 {len(cards)}건")
        else:
            card = repository.find_card(args.card_id)
            if card is None:
                print(f"card_id={args.card_id} 카드가 없습니다.", file=sys.stderr)
                return 1
            print(format_card(card))
        return 0
    except psycopg.Error as error:
        print(f"DB 오류: {type(error).__name__}: {error}", file=sys.stderr)
        return 3
    finally:
        sql_session.database_manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
