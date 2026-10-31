"""PDF 원문 등록 CLI. ``--apply`` 가 없으면 조회만 하고 DB를 변경하지 않는다.

실행 예(src/card_benefit 폴더에서, PDF 경로는 data/raw/hana_all 기준):
    uv run python -m payment_card.db_pipeline.main --pdf "debit/파일명.pdf"
    uv run python -m payment_card.db_pipeline.main --pdf "debit/파일명.pdf" --apply

종료 코드: 0 성공, 1 입력 오류·등록 불가·검증 실패, 2 인자 오류(argparse), 3 DB 오류.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from urllib.parse import urlparse

from common.ocr_engines import OCR_ENGINE_KINDS, create_ocr_engine
from common.postgres_db_session import PostgresDbSession
from common.query_logger import QueryLogger
import psycopg

from .document_service import DocumentService
from .register_service import RegisterError, RegisterResult, RegisterService, error_checks
from .document_repository import MAPPER_ROOT, RAW_TEXT_LOG_KEYS


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """등록 대상 PDF와 실행 옵션을 해석한다."""
    parser = argparse.ArgumentParser(prog="db_pipeline", description="PDF 원문 등록")
    parser.add_argument("--pdf", required=True, help="data/raw/hana_all 기준 PDF 경로")
    parser.add_argument("--apply", action="store_true", help="실제로 등록한다. 없으면 dry-run")
    parser.add_argument("--ocr", choices=OCR_ENGINE_KINDS, help="문제 페이지에 쓸 OCR 엔진. 없으면 해당 PDF를 등록하지 않음")
    parser.add_argument("--sql-log", default="combined", choices=QueryLogger.LOG_MODES, help="SQL 상세 로그 형식")
    return parser.parse_args(argv)


def print_result(result: RegisterResult) -> None:
    """등록 결과 요약을 출력한다. 원문은 출력하지 않는다."""
    document = result.document
    print(f"상태: {result.status}")
    print(f"문서: {document.doc_cd} / {document.doc_title} / card_doc_id={result.card_doc_id}")
    print(f"파일: {document.doc_file_nm} ({document.doc_file_size:,} byte) sha256={document.doc_sha256}")
    print(f"심의: {document.doc_review_no} / {document.doc_review_date}")
    print(f"PDF 추출: {len(document.pages)}쪽, 청크 {len(document.chunks)}개")
    for row in document.quality():
        print(f"  {row}")
    if result.counts:
        print(f"DB 등록 건수: {result.counts}")
    for row in result.checks:
        print(f"  {row['severity']:<5} {row['check_cd']:<18} {row['issue_cnt']}")
    print(f"소요 시간: {result.elapsed_ms:.1f} ms")


def main(argv: list[str] | None = None) -> int:
    """인자를 해석해 등록을 실행하고, 끝나면 연결 pool을 닫는다."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sql_session = PostgresDbSession(
        mapper_root=MAPPER_ROOT,
        camel_case_keys=False,
        sql_log_mode=args.sql_log,
        sensitive_log_keys=(*QueryLogger.DEFAULT_SENSITIVE_KEYS, *RAW_TEXT_LOG_KEYS),
    )
    print(f"접속 대상: {urlparse(os.getenv('DB_URL', '')).hostname} / {'등록' if args.apply else 'dry-run'}")
    try:
        ocr_engine = create_ocr_engine(args.ocr) if args.ocr else None
        result = RegisterService(sql_session, DocumentService(ocr_engine=ocr_engine)).register(args.pdf, apply=args.apply)
        print_result(result)
        return 1 if error_checks(result.checks) else 0
    except (ValueError, RegisterError) as error:
        print(f"등록 오류: {error}", file=sys.stderr)
        return 1
    except psycopg.Error as error:
        print(f"DB 오류: {type(error).__name__}: {error}", file=sys.stderr)
        return 3
    finally:
        sql_session.database_manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
