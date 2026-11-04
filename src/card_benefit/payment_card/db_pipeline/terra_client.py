"""Terra 페이지 추출 어댑터. 비용은 추정치이며 공급자의 청구 상한이 아니다.

[등록 파이프라인에서의 위치] 2단계 "LLM 추출"의 실제 외부 호출부. extraction_service.LlmClient 계약
(``model_nm`` 속성 + ``extract(PageInput) -> LlmResponse``)을 구현한다(Java의 interface 구현체에 해당).

처리 흐름 (``extract``)
    1. 예산 확인: 누적 사용액 + (입력 추정 + 최대 출력) 비용이 예산을 넘거나 이전 사용량이 불명이면 BudgetExceeded
    2. 요청 구성: 프롬프트 + "PAGE n" + 페이지 텍스트, 페이지 이미지(PNG base64, 있을 때만)
    3. ``client.responses.create`` 호출 — strict JSON Schema(PageExtraction)로 응답 형식 강제
    4. 응답 usage로 누적 사용액 갱신. usage가 없거나 호출 예외면 usage_uncertain=True로 이후 호출 차단

호출하는 곳: terra_main.py, common_auto_main.py (OpenAI 클라이언트를 주입해 생성)
DB 접근 없음. 이 클래스가 호출 이력을 저장하지 않으며, 저장은 ExtractionService._call_llm이 한다.
"""
from __future__ import annotations

import base64
from decimal import Decimal

from openai.lib._pydantic import to_strict_json_schema
from .extraction_schema import PageExtraction
from .extraction_service import LlmResponse, PageInput


class BudgetExceeded(Exception):
    """예산 초과 또는 사용량 미확인으로 호출을 막을 때 낸다. ExtractionService._call_llm에서는 호출 실패(FAILED)로 기록된다."""
    pass


class TerraClient:
    model_nm = 'gpt-6.1-terra'
    # 백만 토큰당 USD (입력, 출력). 추정용이며 청구액이 아니다. Sol은 공개 보도 기준 단가다.
    PRICES = {'gpt-6.1-terra': (Decimal('1'), Decimal('5')), 'gpt-6.1-sol': (Decimal('2'), Decimal('10'))}
    REASONING = ('low', 'medium', 'high')

    def __init__(self, client, *, input_token_estimate: int, max_output_tokens: int = 8000,
                 budget_usd: Decimal = Decimal('1'), spent_usd: Decimal = Decimal('0'),
                 model_nm: str = 'gpt-6.1-terra', reasoning_effort: str = 'medium'):
        if input_token_estimate <= 0 or max_output_tokens <= 0 or budget_usd <= 0 or spent_usd < 0:
            raise ValueError('비용 및 토큰 값은 양수여야 합니다')
        if model_nm not in self.PRICES or reasoning_effort not in self.REASONING:
            raise ValueError('단가가 등록되지 않은 모델 또는 지원하지 않는 추론 수준입니다')
        self.client = client
        self.model_nm = model_nm                # card_ai_run.run_model_nm과 재사용 판정에 쓰인다
        self.reasoning_effort = reasoning_effort
        self.input_token_estimate = input_token_estimate
        self.max_output_tokens = max_output_tokens
        self.budget_usd = Decimal(budget_usd)
        self.spent_usd = Decimal(spent_usd)
        self.usage_uncertain = False

    @classmethod
    def cost(cls, input_tokens: int, output_tokens: int, model_nm: str = 'gpt-6.1-terra') -> Decimal:
        """토큰 수와 PRICES 단가(백만 토큰당 USD)로 추정 비용을 계산한다. 실제 청구액이 아니다."""
        input_price, output_price = cls.PRICES[model_nm]
        return (input_tokens * input_price + output_tokens * output_price) / Decimal(1000000)

    @property
    def reuse_config(self):
        """ExtractionService.run의 재사용 지문에 들어가는 모델 설정. 값이 다르면 이전 실행을 재사용하지 않는다."""
        return {"adapter": "terra_v1", "reasoning": self.reasoning_effort, "image_detail": "high",
                "max_output_tokens": self.max_output_tokens}

    def extract(self, page_input: PageInput) -> LlmResponse:
        """페이지 입력 1건으로 LLM을 호출한다(유료 API 호출).

        Returns:
            LlmResponse(응답 원문, 입력·출력 토큰 수). 사용량을 알 수 없으면 토큰 수는 None.

        Raises:
            BudgetExceeded: 호출 전 예산 검사에 걸린 경우(호출하지 않음).
            Exception: API 호출 예외를 그대로 전파한다. 이때 usage_uncertain=True가 되어 이후 호출이 막힌다.
        """
        # 호출 전 예산 검사: 최대 비용 기준으로 넘으면 호출하지 않는다.
        if self.usage_uncertain or self.spent_usd + self.cost(self.input_token_estimate, self.max_output_tokens, self.model_nm) > self.budget_usd:
            raise BudgetExceeded('예산 또는 사용량 미확인으로 호출 차단')
        content = [{'type': 'input_text', 'text': page_input.prompt_txt + '\n\nPAGE ' + str(page_input.page_no) + '\n' + page_input.page_text}]
        if page_input.image_png is not None:      # 페이지 일부 청크는 이미지 없이 보낸다
            image = base64.b64encode(page_input.image_png).decode('ascii')
            content.append({'type': 'input_image', 'image_url': 'data:image/png;base64,' + image, 'detail': 'high'})
        try:
            response = self.client.responses.create(
                model=self.model_nm, reasoning={'effort': self.reasoning_effort}, max_output_tokens=self.max_output_tokens,
                input=[{'role': 'user', 'content': content}],
                text={'format': {'type': 'json_schema', 'name': 'page_extraction', 'strict': True,
                                 'schema': to_strict_json_schema(PageExtraction)}},
            )
        except Exception:
            # 서버 처리 후 전송 오류이면 요금이 발생했을 수 있다. 후속 호출을 차단한다.
            self.usage_uncertain = True
            raise
        usage = response.usage
        if usage is None or usage.input_tokens is None or usage.output_tokens is None:
            self.usage_uncertain = True
            return LlmResponse(response.output_text or '', None, None)
        self.spent_usd += self.cost(usage.input_tokens, usage.output_tokens, self.model_nm)
        return LlmResponse(response.output_text or '', usage.input_tokens, usage.output_tokens)
