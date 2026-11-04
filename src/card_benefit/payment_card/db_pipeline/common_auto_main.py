"""기존 공통서비스 문서 1건의 추출·승인 판정·혜택 등록 CLI."""
# 주의: 위 모듈 docstring은 main()의 argparse description(--help 출력)으로 쓰이므로 내용을 바꾸지 않았다.
#
# [등록 파이프라인에서의 위치] 이미 1단계로 등록되고 card_common_doc에 연결된 BRAND_SERVICE 문서에 대해
# 2단계(LLM 추출)와 3단계(공통 혜택 등록)를 CommonAutoPipeline으로 이어서 실행한다.
#
# 처리 순서(--execute일 때만 DB·API 접속)
#     1. RegisterService.register(apply=False)로 ALREADY_REGISTERED·BRAND_SERVICE인지 확인(신규 문서는 거부)
#     2. 연결된 공통서비스가 정확히 1개인지 확인
#     3. AI 입력 청크 수 × 최대 추정 비용 + 기존 사용액이 예산 이내인지 확인
#     4. TerraClient(OpenAI) 생성 → CommonAutoPipeline.run → 결과 JSON 출력
# 종료 코드: 0 정상(REVIEW 포함), 1 파이프라인 ERROR, 2 인자 오류. 사전 확인의 ValueError는 잡지 않는다.
from __future__ import annotations

import argparse
from dataclasses import asdict
from decimal import Decimal
import json
import os
from dotenv import load_dotenv
from openai import OpenAI
from common.postgres_db_session import PostgresDbSession
from common.query_logger import QueryLogger
from .common_auto_pipeline import CommonAutoPipeline, PostgresCommonApproval
from .common_benefit_service import CommonBenefitService
from .document_repository import MAPPER_ROOT
from .extraction_repository import RAW_RESPONSE_LOG_KEYS
from .extraction_service import ExtractionService
from .register_service import RegisterService
from .terra_client import TerraClient


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', required=True, help='hana_all 기준 경로; 기존 공통 문서 연결이 있어야 합니다')
    parser.add_argument('--input-token-estimate', type=int, required=True)
    parser.add_argument('--max-output-tokens', type=int, default=8000)
    parser.add_argument('--budget-usd', type=Decimal, required=True)
    parser.add_argument('--previous-spend-usd', type=Decimal, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    if args.input_token_estimate < 1 or args.max_output_tokens < 1 or args.budget_usd <= 0 or args.previous_spend_usd < 0:
        parser.error('토큰 및 예산은 양수, 이전 비용은 0 이상이어야 합니다')
    if not args.execute:
        print('dry-run: DB 및 API 호출 없음')
        return 0
    load_dotenv()
    session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode='none',
        sensitive_log_keys=(*QueryLogger.DEFAULT_SENSITIVE_KEYS, *RAW_RESPONSE_LOG_KEYS))
    try:
        registration = RegisterService(session)
        inspected = registration.register(args.pdf, apply=False)
        if inspected.status != 'ALREADY_REGISTERED' or inspected.document.doc_type_cd != 'BRAND_SERVICE':
            raise ValueError('기존 등록된 공통 문서만 실행합니다')
        doc_id = inspected.card_doc_id
        common = CommonBenefitService(session)
        if len(common.repo.rows('common_of_doc', DOC_ID=doc_id)) != 1:
            raise ValueError('연결된 공통서비스가 정확히 하나여야 합니다')
        extraction_repo = ExtractionService(session, None).repository
        chunks = extraction_repo.select_ai_input_chunks(doc_id)
        usage = session.select_one('extraction_repository.select_terra_usage', {'CARD_DOC_ID': doc_id})
        if usage['unknown_calls']:
            raise ValueError('이전 호출 사용량을 확인할 수 없습니다')
        previous = max(args.previous_spend_usd, TerraClient.cost(usage['input_tokens'], usage['output_tokens']))
        estimate = TerraClient.cost(args.input_token_estimate, args.max_output_tokens) * len(chunks)
        print(f'문서={doc_id} 페이지={len(chunks)} 이전비용=${previous} 신규 최대 추정=${estimate} 예산=${args.budget_usd}', flush=True)
        if not chunks or previous + estimate > args.budget_usd:
            raise ValueError('입력 페이지가 없거나 최대 추정 비용이 예산을 초과합니다')
        llm = TerraClient(OpenAI(max_retries=0), input_token_estimate=args.input_token_estimate,
                          max_output_tokens=args.max_output_tokens, budget_usd=args.budget_usd, spent_usd=previous)
        pipeline = CommonAutoPipeline(registration, ExtractionService(session, llm), common, PostgresCommonApproval(session, common))
        result = pipeline.run(args.pdf)
        print(json.dumps(asdict(result), ensure_ascii=False, default=str, indent=2))
        print(f'누적 토큰 기준 비용=${llm.spent_usd}; 사용량 불명={llm.usage_uncertain}')
        return 1 if result.status == 'ERROR' else 0
    finally:
        session.database_manager.close()


if __name__ == '__main__':
    raise SystemExit(main())
