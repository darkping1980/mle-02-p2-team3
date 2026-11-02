"""혜택 검색 텍스트·임베딩 일괄 처리 CLI. ``--apply`` 가 없으면 건수만 확인하고 API와 DB 쓰기를 하지 않는다.

실행 예(src/card_benefit 폴더에서):
    uv run python -m payment_card.db_pipeline.embedding_main                      # 대상 확인
    uv run python -m payment_card.db_pipeline.embedding_main --apply              # 누락·변경분만 처리
    uv run python -m payment_card.db_pipeline.embedding_main --table card_bnft --id 20261101_000001 --apply
    uv run python -m payment_card.db_pipeline.embedding_main --text-only --apply  # 텍스트만 재생성
    uv run python -m payment_card.db_pipeline.embedding_main --force --apply      # 모델·규칙 변경 후 전체 재생성

종료 코드: 0 성공, 1 입력 오류 또는 일부 실패, 2 인자 오류, 3 DB 오류.
"""
from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlparse

from common.postgres_db_session import PostgresDbSession
from common.query_log_config import load_project_environment
from common.query_logger import QueryLogger
import psycopg

from .document_repository import MAPPER_ROOT
from .embedding_service import (EMBEDDING_LOG_KEYS, TABLES, EmbeddingError, EmbeddingService, OpenAIEmbedder,
                                SyncResult, embedding_model)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="embedding_main", description="혜택 검색 텍스트·임베딩 일괄 처리")
    parser.add_argument("--table", default="all", choices=("all", *TABLES), help="대상 테이블")
    parser.add_argument("--id", action="append", dest="ids", help="혜택 ID. 여러 번 지정할 수 있다. 없으면 전체")
    parser.add_argument("--text-only", action="store_true", help="검색 텍스트만 다시 만든다. API를 호출하지 않는다")
    parser.add_argument("--force", action="store_true", help="같은 텍스트여도 임베딩을 다시 만든다")
    parser.add_argument("--max-attempts", type=int, default=3, help="API 호출 시도 횟수")
    parser.add_argument("--apply", action="store_true", help="실제로 저장한다. 없으면 dry-run")
    return parser.parse_args(argv)


def print_result(result: SyncResult, status: list[dict]) -> None:
    for report in result.reports:
        print(f"{report.table}: 대상 {report.targets}, 텍스트 변경 {report.text_changed}, 건너뜀 {report.skipped}, "
              f"임베딩 성공 {report.embedded}, 실패 {len(report.failed)}")
        for item in report.failed:
            print(f"  실패 {item['id']}: {item['error']}")
        for item in report.review:
            print(f"  검토 {item['id']}: {'; '.join(item['items'])}")
    print(f"실행 이력: {result.run_id}")
    for row in status:
        print(f"저장 현황 {row}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_attempts < 1:
        print("--max-attempts는 1 이상이어야 합니다", file=sys.stderr)
        return 2
    load_project_environment()
    session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none",
                                sensitive_log_keys=(*QueryLogger.DEFAULT_SENSITIVE_KEYS, *EMBEDDING_LOG_KEYS))
    print(f"접속 대상: {urlparse(os.getenv('DB_URL', '')).hostname} / 모델: {embedding_model()} / "
          f"{'적용' if args.apply else 'dry-run'}")
    try:
        embedder = OpenAIEmbedder() if args.apply and not args.text_only else None
        service = EmbeddingService(session, embedder, max_attempts=args.max_attempts)
        result = service.sync(args.table, args.ids, force=args.force, text_only=args.text_only, apply=args.apply)
        print_result(result, service.status())
        return 0 if result.ok else 1
    except EmbeddingError as error:
        print(f"임베딩 오류: {error}", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(f"DB 오류: {type(error).__name__}", file=sys.stderr)
        return 3
    finally:
        session.database_manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
