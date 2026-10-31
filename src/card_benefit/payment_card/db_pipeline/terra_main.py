"""단일 페이지 Terra 추출 CLI. 실행은 유료 호출 및 중간 테이블 쓰기다."""
from __future__ import annotations
import argparse
from decimal import Decimal
from dotenv import load_dotenv
from openai import OpenAI
from common.postgres_db_session import PostgresDbSession
from common.query_logger import QueryLogger
from .document_repository import MAPPER_ROOT
from .extraction_repository import RAW_RESPONSE_LOG_KEYS
from .extraction_service import ExtractionService
from .terra_client import TerraClient


def main(argv=None):
    p = argparse.ArgumentParser(description='Terra 단일 페이지 추출: 실제 API 호출 및 DB 저장')
    p.add_argument('--card-id', type=int, required=True)
    p.add_argument('--doc-id', required=True)
    p.add_argument('--page', type=int, required=True)
    p.add_argument('--input-token-estimate', type=int, required=True, help='이미지를 포함한 보수적인 입력 토큰 추정')
    p.add_argument('--max-output-tokens', type=int, default=8000)
    p.add_argument('--budget-usd', type=Decimal, default=Decimal('1'))
    p.add_argument('--previous-spend-usd', type=Decimal, required=True, help='이전 호출 실제 누적 비용; 사용량 불명이면 실행 금지')
    p.add_argument('--execute', action='store_true', help='실제 유료 호출과 DB 저장 실행')
    args = p.parse_args(argv)
    if args.page < 1 or args.input_token_estimate < 1 or args.max_output_tokens < 1:
        p.error('페이지 및 토큰은 양수여야 합니다')
    estimated = TerraClient.cost(args.input_token_estimate, args.max_output_tokens)
    print(f'예상 최대 비용(입력 추정 기준): ${estimated}; 이전 사용액: ${args.previous_spend_usd}')
    if args.previous_spend_usd < 0 or args.budget_usd <= 0 or args.previous_spend_usd + estimated > args.budget_usd:
        p.error('예상 누적 비용이 예산을 초과합니다')
    if not args.execute:
        print('dry-run: DB 연결과 API 호출을 수행하지 않았습니다')
        return 0
    load_dotenv()
    session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False,
        sensitive_log_keys=(*QueryLogger.DEFAULT_SENSITIVE_KEYS, *RAW_RESPONSE_LOG_KEYS))
    try:
        usage = session.select_one('extraction_repository.select_terra_usage', {'CARD_DOC_ID': args.doc_id})
        if usage['unknown_calls']:
            raise RuntimeError('사용량을 확인할 수 없는 기존 호출이 있어 실행을 중단합니다')
        recorded = TerraClient.cost(usage['input_tokens'], usage['output_tokens'])
        prior = max(args.previous_spend_usd, recorded)
        if prior + estimated > args.budget_usd:
            raise RuntimeError('DB 누적 사용량을 포함한 예상 비용이 예산을 초과합니다')
        llm = TerraClient(OpenAI(max_retries=0), input_token_estimate=args.input_token_estimate,
                          max_output_tokens=args.max_output_tokens, budget_usd=args.budget_usd,
                          spent_usd=prior)
        result = ExtractionService(session, llm).run(args.doc_id, args.card_id, page_numbers={args.page})
        print(f'run={result.card_ai_run_id} status={result.status} note={result.note}')
        print(f'누적 사용액(토큰 기준): ${llm.spent_usd}; 사용량 불명: {llm.usage_uncertain}')
        return 0 if result.pages_ok else 1
    finally:
        session.database_manager.close()


if __name__ == '__main__':
    raise SystemExit(main())
