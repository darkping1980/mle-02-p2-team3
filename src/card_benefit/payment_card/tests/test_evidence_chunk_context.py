"""Offline tests for evidence-linked raw chunk context."""
import json

import pytest

from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag as g
from test_card_graphrag import FakeSearch, answer_llm, detail, evidence_row, interpret_llm


def chunk_row(evidence_id, chunk_id='C1', text='대중교통 5% 캐시백\n전월 30만원 이상\n편의점 100원', doc='D1'):
    row = evidence_row(evidence_id)
    row['chunk'] = {'chunk_id': chunk_id, 'page_no': 3, 'source_json': json.dumps({
        'card_doc_chunk_id': chunk_id, 'card_doc_id': doc, 'chunk_raw_txt': text}, ensure_ascii=False)}
    row['document'] = {'source_json': json.dumps({'card_doc_id': doc, 'doc_title': '상품설명서'}, ensure_ascii=False)}
    return row


@pytest.mark.parametrize('question', [
    'ONE PICK STYLE의 대중교통 5% 캐시백과 조건은?',
    'ONE PICK STYLE 편의점 100원 캐시백과 한도는?',
    '더 심플 하나카드 월납 요금 할인 조건은?',
    '카드의정석2 DAILY 통신요금 5% 할인은?',
    '두 카드의 통신요금 혜택을 비교해줘',
])
def test_mock_answer_receives_linked_context(question):
    first, second = interpret_llm(), answer_llm()
    result = g.CardGraphRAG(FakeSearch(result=detail([chunk_row('E1'), chunk_row('E2')])), first, second).run(question)
    assert result['answer']['status'] == 'ANSWERED'
    chunks = result['context']['chunks']
    assert len(chunks) == 1
    assert {link['evidence_id'] for link in chunks[0]['links']} == {'E1', 'E2'}
    assert all(link['benefit_id'] == 'B3' for link in chunks[0]['links'])
    assert '전월 30만원 이상' in second.prompts[0]
    assert '다른 혜택을 섞지 않는다' in second.prompts[0]


def test_missing_oversized_and_cross_benefit_chunks():
    one = detail([chunk_row('E1', text='표 전체')]); one['entity_ref'] = 'A'
    two = detail([chunk_row('E2', chunk_id='C2', text='다른 혜택'), chunk_row('E3', chunk_id='C3', text='x'*6001)])
    two['entity_ref'] = 'B'
    selected = [{'evidence_id':'E1','benefit_ids':['A']}, {'evidence_id':'E2','benefit_ids':['A']},
                {'evidence_id':'E3','benefit_ids':['B']}]
    chunks, omitted = g.linked_answer_chunks([one, two], selected)
    assert [c['text'] for c in chunks] == ['표 전체']
    assert chunks[0]['links'] == [{'benefit_id':'A', 'evidence_id':'E1'}]
    assert omitted == 1
    assert g.linked_answer_chunks([detail([evidence_row('E1')])], [{'evidence_id':'E1','benefit_ids':['B3']}]) == ([], 0)


def test_total_budget_never_truncates_chunks():
    d = detail([chunk_row(str(i), chunk_id=str(i), text='x'*5000) for i in range(6)])
    selected = [{'evidence_id':str(i),'benefit_ids':['B3']} for i in range(6)]
    chunks, omitted = g.linked_answer_chunks([d], selected)
    assert len(chunks) == 4 and omitted == 2
    assert all(len(item['text']) == 5000 for item in chunks)
