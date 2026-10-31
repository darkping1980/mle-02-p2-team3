from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from payment_card.db_pipeline.extraction_service import PageInput
from payment_card.db_pipeline.terra_client import BudgetExceeded, TerraClient


def page():
    return PageInput('prompt', 1, 'page text', b'png', 'hash')


def test_structured_request_and_usage():
    responses = Mock()
    responses.create.return_value = SimpleNamespace(output_text='{}', usage=SimpleNamespace(input_tokens=1000, output_tokens=500))
    adapter = TerraClient(SimpleNamespace(responses=responses), input_token_estimate=10000)
    result = adapter.extract(page())
    request = responses.create.call_args.kwargs
    assert request['model'] == 'gpt-6.1-terra'
    assert request['reasoning'] == {'effort': 'medium'}
    assert request['text']['format']['strict'] is True
    assert request['input'][0]['content'][1]['image_url'].startswith('data:image/png;base64,')
    assert (result.input_tokens, result.output_tokens) == (1000, 500)
    assert adapter.spent_usd == Decimal('0.0035')


def test_budget_blocks_before_call():
    responses = Mock()
    adapter = TerraClient(SimpleNamespace(responses=responses), input_token_estimate=10000,
                          budget_usd=Decimal('0.01'))
    with pytest.raises(BudgetExceeded):
        adapter.extract(page())
    responses.create.assert_not_called()


def test_unknown_usage_and_api_failure_block_next_call():
    responses = Mock()
    responses.create.return_value = SimpleNamespace(output_text='{}', usage=None)
    adapter = TerraClient(SimpleNamespace(responses=responses), input_token_estimate=10000)
    assert adapter.extract(page()).input_tokens is None
    with pytest.raises(BudgetExceeded):
        adapter.extract(page())
    responses.create.side_effect = RuntimeError('api')
    adapter = TerraClient(SimpleNamespace(responses=responses), input_token_estimate=10000)
    with pytest.raises(RuntimeError):
        adapter.extract(page())
    with pytest.raises(BudgetExceeded):
        adapter.extract(page())
