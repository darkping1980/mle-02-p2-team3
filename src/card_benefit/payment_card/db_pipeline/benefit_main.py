"""추출 후보를 혜택으로 등록하는 CLI. ``--apply`` 없이는 실행하지 않는다. 등록 뒤 임베딩을 시도한다.

실행 예(src/card_benefit 폴더에서):
    uv run python -m payment_card.db_pipeline.benefit_main product --run-id 20261101_000002 --card-id 2 --apply
    uv run python -m payment_card.db_pipeline.benefit_main common --run-id 20261102_000003 \
        --identity 20261102_000017=VISA_SIGNATURE_CONCIERGE --card-id 5 --apply
    uv run python -m payment_card.db_pipeline.benefit_main brand-compare --apply     # 기존 BRAND_SERVICE 행 동일성 판정(읽기 전용)

``--identity`` 는 사람이 검토한 ``추출항목ID=업무식별자`` 다. 공통 혜택은 ``--card-id`` 로 지정한 카드만 적용을 판단한다.
종료 코드: 0 성공, 1 입력 오류, 2 인자 오류, 3 DB 오류.
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

from .common_benefit_service import CommonBenefitService
from .document_repository import MAPPER_ROOT
from .embedding_service import EMBEDDING_LOG_KEYS, EmbeddingService, OpenAIEmbedder
from .product_benefit_service import ProductBenefitService


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="benefit_main", description="추출 후보 혜택 등록")
    parser.add_argument("kind", choices=("product", "common", "brand-compare", "review-queue"))
    parser.add_argument("--run-id", help="card_ai_run_id. product, common에 필수")
    parser.add_argument("--card-id", type=int, action="append", default=[], help="대상 카드. product는 1개 필수")
    parser.add_argument("--identity", action="append", default=[], help="추출항목ID=업무식별자 (common)")
    parser.add_argument("--no-embed", action="store_true", help="임베딩을 만들지 않는다. embedding_main으로 나중에 처리")
    parser.add_argument("--apply", action="store_true", help="실제로 등록한다")
    args = parser.parse_args(argv)
    if args.kind != "brand-compare" and not args.run_id:
        parser.error("--run-id가 필요합니다")
    if args.kind == "product" and len(args.card_id) != 1:
        parser.error("product에는 --card-id 1개가 필요합니다")
    if any("=" not in item for item in args.identity):
        parser.error("--identity 형식은 추출항목ID=업무식별자 입니다")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.apply and args.kind != "review-queue":
        print("dry-run: --apply가 없어 DB에 접속하지 않았습니다")
        return 0
    load_project_environment()
    session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none",
                                sensitive_log_keys=(*QueryLogger.DEFAULT_SENSITIVE_KEYS, *EMBEDDING_LOG_KEYS))
    print(f"접속 대상: {urlparse(os.getenv('DB_URL', '')).hostname}")
    try:
        if args.kind == "review-queue":
            import json
            rows = ProductBenefitService(session).unresolved_review_queue(args.run_id)
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
            return 0
        if args.kind == "brand-compare":
            for row in CommonBenefitService(session).compare_brand_benefits():
                print(row)
            return 0
        embedding = None if args.no_embed else EmbeddingService(session, OpenAIEmbedder())
        if args.kind == "product":
            results = ProductBenefitService(session, embedding).register_run(args.card_id[0], args.run_id)
        else:
            identities = dict(item.split("=", 1) for item in args.identity)
            service = CommonBenefitService(session, embedding_service=embedding)
            results = service.register_run(args.run_id, identities)
            for card_id in args.card_id:
                results += service.apply_run(card_id, args.run_id, identities)
        for item in results:
            print(f"{item.status:<14} card={item.card_id} stg={item.stg_id} {item.reason}")
        return 0
    except ValueError as error:
        print(f"등록 오류: {error}", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(f"DB 오류: {type(error).__name__}", file=sys.stderr)
        return 3
    finally:
        session.database_manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
