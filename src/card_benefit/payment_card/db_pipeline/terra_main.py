"""단일 페이지 Terra 추출 CLI. 실행은 유료 호출 및 중간 테이블 쓰기다."""
from __future__ import annotations
import argparse
from decimal import Decimal
from types import SimpleNamespace
from dotenv import load_dotenv
from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema
import pymupdf
from common.postgres_db_session import PostgresDbSession
from common.query_logger import QueryLogger
from .document_repository import MAPPER_ROOT
from .extraction_repository import RAW_RESPONSE_LOG_KEYS
from .extraction_service import ExtractionService
from .extraction_schema import PageExtraction
from .terra_client import TerraClient


def preflight(session, args, estimated):
    """읽기 전용 DB 조회와 실제 입력 구성. 네트워크 모델 호출이나 데이터 저장은 없다."""
    with session.database_manager.connect(camel_case_keys=False) as conn:
        conn.execute('SET TRANSACTION READ ONLY')
        row = conn.execute('''SELECT p.card_id, d.card_doc_id, d.doc_file_nm, d.doc_sha256,
            d.doc_status, pd.approval_status_cd, c.card_doc_chunk_id, c.chunk_raw_txt,
            c.chunk_status, c.chunk_split_rule_ver, pg.page_raw_txt, pg.page_note
            FROM db_pipeline.card_product p
            JOIN db_pipeline.card_product_doc pd ON pd.card_id=p.card_id
            JOIN db_pipeline.card_doc d ON d.card_doc_id=pd.card_doc_id
            JOIN db_pipeline.card_doc_chunk c ON c.card_doc_id=d.card_doc_id
            JOIN db_pipeline.card_doc_page pg ON (pg.card_doc_id,pg.page_no)=(c.card_doc_id,c.page_no)
            WHERE p.card_id=%s AND d.card_doc_id=%s AND c.page_no=%s''',
            (args.card_id, args.doc_id, args.page)).fetchall()
        if len(row) != 1:
            raise ValueError('상품·문서 연결 또는 페이지 청크가 없거나 여러 건입니다')
        item = row[0]
        if item['doc_status'] != 'ACTIVE' or item['chunk_status'] not in ('RAW', 'CLEANED'):
            raise ValueError('문서 또는 청크가 AI 입력 가능 상태가 아닙니다')
        if (item['page_note'] or '').startswith('OCR_REVIEW '):
            raise ValueError('OCR_REVIEW 페이지는 입력할 수 없습니다')
        if item['chunk_split_rule_ver'] != 'PAGE_V1' or not item['chunk_raw_txt'].strip():
            raise ValueError('PAGE_V1 청크 또는 텍스트가 유효하지 않습니다')
        if item['chunk_raw_txt'] != item['page_raw_txt']:
            raise ValueError('PAGE_V1 청크와 페이지 원문이 일치하지 않습니다')
        usage = conn.execute('''SELECT COALESCE(sum(c.call_input_token_cnt),0) AS input_tokens,
            COALESCE(sum(c.call_output_token_cnt),0) AS output_tokens,
            count(*) FILTER (WHERE c.call_input_token_cnt IS NULL OR c.call_output_token_cnt IS NULL) AS unknown_calls
            FROM db_pipeline.card_ai_run r JOIN db_pipeline.card_ai_call c ON c.card_ai_run_id=r.card_ai_run_id
            WHERE r.run_target_card_doc_id=%s AND r.run_model_nm='gpt-6.1-terra' ''', (args.doc_id,)).fetchone()
    if usage['unknown_calls']:
        raise ValueError('기존 호출의 사용량을 알 수 없어 예산 검증이 불가능합니다')
    prior = max(args.previous_spend_usd, TerraClient.cost(usage['input_tokens'], usage['output_tokens']))
    if prior + estimated > args.budget_usd:
        raise ValueError('기존 사용량을 포함한 예상 비용이 예산을 초과합니다')
    service = ExtractionService(session, llm_client=None)
    pdf = service._local_pdf(item)
    page_input = service.build_input({**item, 'page_no': args.page}, pdf)
    image = pymupdf.Pixmap(page_input.image_png)
    if image.width <= 0 or image.height <= 0:
        raise ValueError('페이지 이미지 크기가 유효하지 않습니다')
    image_size = (image.width, image.height)
    schema = to_strict_json_schema(PageExtraction)
    if schema.get('type') != 'object' or schema.get('additionalProperties') is not False:
        raise ValueError('strict Structured Outputs 스키마가 유효하지 않습니다')
    # 실제 어댑터가 만드는 요청을 가짜 클라이언트에 전달해 본다. 원문은 출력하지 않는다.
    class Capture:
        def create(self, **kwargs):
            self.request = kwargs
            return SimpleNamespace(output_text='{}', usage=SimpleNamespace(input_tokens=0, output_tokens=0))
    capture = Capture()
    adapter = TerraClient(SimpleNamespace(responses=capture), input_token_estimate=args.input_token_estimate,
        max_output_tokens=args.max_output_tokens, budget_usd=args.budget_usd, spent_usd=prior)
    adapter.extract(page_input)
    request = capture.request
    content = request['input'][0]['content']
    if (request['model'] != 'gpt-6.1-terra' or request['reasoning'] != {'effort': 'medium'}
            or request['text']['format']['strict'] is not True
            or request['text']['format']['schema'] != schema
            or page_input.page_text not in content[0]['text']
            or not content[1]['image_url'].startswith('data:image/png;base64,')):
        raise ValueError('Terra 요청 구성이 올바르지 않습니다')
    print(f"preflight OK: card_id={args.card_id} doc_id={args.doc_id} page={args.page} "
          f"chunk={item['card_doc_chunk_id']} status={item['chunk_status']} "
          f"document_approval={item['approval_status_cd']}")
    print(f'PAGE_V1 text_chars={len(page_input.page_text)} image={image_size[0]}x{image_size[1]} '
          f'png_bytes={len(page_input.image_png)} input_sha256={page_input.input_sha256}')
    print(f'기존 토큰 기반 비용=${prior}; 예상 최대 비용=${estimated}; 예산=${args.budget_usd}')
    print('요청 구성 Mock 확인; API 실제 권한·서버 스키마 수용 및 청구액은 미확인')


def main(argv=None):
    p = argparse.ArgumentParser(description='Terra 단일 페이지 추출: 실제 API 호출 및 DB 저장')
    p.add_argument('--card-id', type=int, required=True)
    p.add_argument('--doc-id', required=True)
    p.add_argument('--page', type=int, required=True)
    p.add_argument('--input-token-estimate', type=int, required=True, help='이미지를 포함한 보수적인 입력 토큰 추정')
    p.add_argument('--max-output-tokens', type=int, default=8000)
    p.add_argument('--budget-usd', type=Decimal, default=Decimal('1'))
    p.add_argument('--previous-spend-usd', type=Decimal, required=True, help='이전 호출 실제 누적 비용; 사용량 불명이면 실행 금지')
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true', help='실제 유료 호출과 DB 저장 실행')
    mode.add_argument('--preflight', action='store_true', help='DB 읽기 전용으로 실제 입력 검증; API 호출 없음')
    args = p.parse_args(argv)
    if args.page < 1 or args.input_token_estimate < 1 or args.max_output_tokens < 1:
        p.error('페이지 및 토큰은 양수여야 합니다')
    estimated = TerraClient.cost(args.input_token_estimate, args.max_output_tokens)
    print(f'예상 최대 비용(입력 추정 기준): ${estimated}; 이전 사용액: ${args.previous_spend_usd}')
    if args.previous_spend_usd < 0 or args.budget_usd <= 0 or args.previous_spend_usd + estimated > args.budget_usd:
        p.error('예상 누적 비용이 예산을 초과합니다')
    if not args.execute and not args.preflight:
        print('dry-run: DB 연결과 API 호출을 수행하지 않았습니다')
        return 0
    load_dotenv()
    session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False,
        sensitive_log_keys=(*QueryLogger.DEFAULT_SENSITIVE_KEYS, *RAW_RESPONSE_LOG_KEYS))
    try:
        if args.preflight:
            preflight(session, args, estimated)
            return 0
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
