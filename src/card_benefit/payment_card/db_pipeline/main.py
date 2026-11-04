"""PDF 원문 등록 CLI. ``--apply`` 가 없으면 조회만 하고 DB를 변경하지 않는다.

실행 예(src/card_benefit 폴더에서, PDF 경로는 data/raw/hana_all 기준):
    uv run python -m payment_card.db_pipeline.main --pdf "debit/파일명.pdf"
    uv run python -m payment_card.db_pipeline.main --pdf "debit/파일명.pdf" --apply
    uv run python -m payment_card.db_pipeline.main --pdf "credit/파일명.pdf" --card-id 5 --basis "상품명 일치" --apply
    uv run python -m payment_card.db_pipeline.main --pdf "common/파일명.pdf" --common-cd VISA_SIGNATURE
        --common-nm "Visa Signature" --brand-cd VISA --service-grade-cd SIGNATURE --apply

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

from .document_service import DocumentService, ExternalDocumentSource
from .register_service import (CommonDocLink, ProductDocLink, RegisterError, RegisterResult, RegisterService,
                               error_checks)
from .document_repository import MAPPER_ROOT, RAW_TEXT_LOG_KEYS


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """등록 대상 PDF와 실행 옵션을 해석한다."""
    parser = argparse.ArgumentParser(prog="db_pipeline", description="PDF 원문 등록")
    parser.add_argument("--pdf", required=True, help="--data-root 또는 기본 하나카드 PDF root 기준 상대 경로")
    parser.add_argument("--data-root", help="manifest-less input PDF root (for another issuer)")
    parser.add_argument("--issuer-cd", help="explicit issuer identifier for a manifest-less PDF")
    parser.add_argument("--doc-code-prefix", help="issuer-specific document code prefix")
    parser.add_argument("--doc-family-cd", help="explicit document family identifier")
    parser.add_argument("--doc-title", help="explicit product/document title")
    parser.add_argument("--doc-type-cd", choices=("PRODUCT_GUIDE", "BRAND_SERVICE"), default="PRODUCT_GUIDE")
    parser.add_argument("--source-url", help="official source URL, if confirmed")
    parser.add_argument("--apply", action="store_true", help="실제로 등록한다. 없으면 dry-run")
    parser.add_argument("--ocr", choices=OCR_ENGINE_KINDS, help="문제 페이지에 쓸 OCR 엔진. 없으면 해당 PDF를 등록하지 않음")
    parser.add_argument("--card-id", type=int, help="상품설명서를 연결할 card_product.card_id")
    parser.add_argument("--basis", help="상품 적용 근거 설명(applicability_basis_txt). --card-id와 함께 필수")
    parser.add_argument("--common-cd", help="브랜드 공통서비스 문서를 연결할 card_common.common_cd. 없으면 만든다")
    parser.add_argument("--common-nm", help="공통서비스명. --common-cd와 함께 필수")
    parser.add_argument("--brand-cd", help="BRAND 공통코드")
    parser.add_argument("--service-grade-cd", help="SERVICE_GRADE 공통코드")
    parser.add_argument("--sql-log", default="combined", choices=QueryLogger.LOG_MODES, help="SQL 상세 로그 형식")
    args = parser.parse_args(argv)
    if args.card_id is not None and not args.basis:
        parser.error("--card-id에는 --basis가 필요합니다")
    if args.common_cd and not args.common_nm:
        parser.error("--common-cd에는 --common-nm이 필요합니다")
    if args.card_id is not None and args.common_cd:
        parser.error("--card-id와 --common-cd는 함께 쓸 수 없습니다")
    source_values = (args.issuer_cd, args.doc_code_prefix, args.doc_family_cd, args.doc_title)
    if any(source_values) and not all(source_values):
        parser.error("manifest-less PDF는 --issuer-cd, --doc-code-prefix, --doc-family-cd, --doc-title이 모두 필요합니다")
    if args.data_root and not all(source_values):
        parser.error("--data-root에는 명시적 source metadata가 필요합니다")
    if args.source_url and not args.issuer_cd:
        parser.error("--source-url은 manifest-less source metadata와 함께 사용합니다")
    return args


def links(args: argparse.Namespace) -> dict:
    """인자를 문서 연결로 바꾼다."""
    if args.card_id is not None:
        return {"product_link": ProductDocLink(args.card_id, args.basis)}
    if args.common_cd:
        return {"common_link": CommonDocLink(args.common_cd, args.common_nm, args.brand_cd, args.service_grade_cd)}
    return {}


def print_result(result: RegisterResult) -> None:
    """등록 결과 요약을 출력한다. 원문은 출력하지 않는다."""
    document = result.document
    print(f"상태: {result.status}")
    print(f"문서: {document.doc_cd} / {document.doc_title} / card_doc_id={result.card_doc_id}")
    print(f"파일: {document.doc_file_nm} ({document.doc_file_size:,} byte) sha256={document.doc_sha256}")
    print(f"심의: {document.doc_review_no} / {document.doc_review_date}")
    if result.status == "ALREADY_REGISTERED" and not document.pages:
        print("기존 문서 재사용: 페이지 재파싱 생략")
    else:
        print(f"PDF 추출: {len(document.pages)}쪽, 청크 {len(document.chunks)}개")
    for row in document.quality():
        print(f"  {row}")
    if result.counts:
        print(f"DB 등록 건수: {result.counts}")
    for row in result.checks:
        print(f"  {row['severity']:<5} {row['check_cd']:<18} {row['issue_cnt']}")
    if result.linked:
        print(f"문서 연결: {result.linked}")
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
        external_source = None
        data_root = None
        if args.issuer_cd:
            external_source = ExternalDocumentSource(
                issuer_cd=args.issuer_cd,
                doc_code_prefix=args.doc_code_prefix,
                doc_family_cd=args.doc_family_cd,
                doc_title=args.doc_title,
                doc_type_cd=args.doc_type_cd,
                doc_source_url=args.source_url,
            )
            data_root = args.data_root
        document_service = DocumentService(data_root=data_root, ocr_engine=ocr_engine,
                                           external_source=external_source) if data_root else DocumentService(
                                               ocr_engine=ocr_engine, external_source=external_source)
        result = RegisterService(sql_session, document_service).register(args.pdf, apply=args.apply, **links(args))
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
