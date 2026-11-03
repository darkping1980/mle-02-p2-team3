"""Terra 페이지 추출 어댑터. 비용은 추정치이며 공급자의 청구 상한이 아니다."""
from __future__ import annotations

import base64
from decimal import Decimal

from openai.lib._pydantic import to_strict_json_schema
from .extraction_schema import PageExtraction
from .extraction_service import LlmResponse, PageInput


class BudgetExceeded(Exception):
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
        input_price, output_price = cls.PRICES[model_nm]
        return (input_tokens * input_price + output_tokens * output_price) / Decimal(1000000)

    @property
    def reuse_config(self):
        return {"adapter": "terra_v1", "reasoning": self.reasoning_effort, "image_detail": "high",
                "max_output_tokens": self.max_output_tokens}

    def extract(self, page_input: PageInput) -> LlmResponse:
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
