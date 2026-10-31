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
    input_price = Decimal('1')
    output_price = Decimal('5')

    def __init__(self, client, *, input_token_estimate: int, max_output_tokens: int = 8000,
                 budget_usd: Decimal = Decimal('1'), spent_usd: Decimal = Decimal('0')):
        if input_token_estimate <= 0 or max_output_tokens <= 0 or budget_usd <= 0 or spent_usd < 0:
            raise ValueError('비용 및 토큰 값은 양수여야 합니다')
        self.client = client
        self.input_token_estimate = input_token_estimate
        self.max_output_tokens = max_output_tokens
        self.budget_usd = Decimal(budget_usd)
        self.spent_usd = Decimal(spent_usd)
        self.usage_uncertain = False

    @classmethod
    def cost(cls, input_tokens: int, output_tokens: int) -> Decimal:
        return (input_tokens * cls.input_price + output_tokens * cls.output_price) / Decimal(1000000)

    def extract(self, page_input: PageInput) -> LlmResponse:
        if self.usage_uncertain or self.spent_usd + self.cost(self.input_token_estimate, self.max_output_tokens) > self.budget_usd:
            raise BudgetExceeded('예산 또는 사용량 미확인으로 호출 차단')
        image = base64.b64encode(page_input.image_png).decode('ascii')
        try:
            response = self.client.responses.create(
                model=self.model_nm, reasoning={'effort': 'medium'}, max_output_tokens=self.max_output_tokens,
                input=[{'role': 'user', 'content': [
                    {'type': 'input_text', 'text': page_input.prompt_txt + '\n\nPAGE ' + str(page_input.page_no) + '\n' + page_input.page_text},
                    {'type': 'input_image', 'image_url': 'data:image/png;base64,' + image, 'detail': 'high'},
                ]}],
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
        self.spent_usd += self.cost(usage.input_tokens, usage.output_tokens)
        return LlmResponse(response.output_text or '', usage.input_tokens, usage.output_tokens)
