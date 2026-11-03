"""공통 혜택 등록과 카드 적용 판단. 저장소는 메모리 Mock이다."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date

from payment_card.db_pipeline.common_benefit_service import CommonBenefitService, benefit_code, brand_key, candidate_period, common_texts, period, quote_text
import pytest


class Session:
    @contextmanager
    def transaction(self):
        yield self


class Repo:
    def __init__(self, cards, candidate, evidence):
        self.cards = {c['card_id']: c for c in cards}
        self.candidate, self.evidence = candidate, evidence
        self.common_bnft, self.applies, self.docs = {}, set(), {'D1': 'BRAND_SERVICE'}
        self.commons = [{'card_common_id': 7, 'brand_cd': 'VISA', 'service_grade_cd': 'SIGNATURE'}]
        self.prior, self.product_evidence, self.legacy = [], [], None
        self.card_bnft_writes = 0

    def rows(self, name, **p):
        if name in ('integrity_errors', 'common_integrity_errors'): return []
        if name == 'list_runs': return [{'card_ai_run_id': 'R1'}]
        if name == 'list_cards': return [{'card_id': x} for x in self.cards]
        if name == 'list_candidates': return [self.candidate]
        if name == 'candidate_evidence': return self.evidence
        if name == 'common_of_doc': return self.commons
        if name == 'prior_common_sources': return self.prior
        if name == 'product_brand_evidence': return self.product_evidence
        raise AssertionError(name)

    def one(self, name, **p):
        if name == 'lock_card': return self.cards.get(p['CARD_ID'])
        if name == 'lock_common': return {'card_common_id': p['COMMON_ID']}
        if name == 'find_common_bnft': return self.common_bnft.get((p['COMMON_ID'], p['BNFT_CD']))
        if name == 'find_benefit': return self.legacy
        raise AssertionError(name)

    def write(self, name, **p):
        if name == 'insert_common_bnft':
            row = dict(card_common_id=p['COMMON_ID'], card_common_bnft_id='C1', bnft_nm=p['BNFT_NM'], bnft_type_cd=p['BNFT_TYPE'],
                       service_type_cd=p['SERVICE_TYPE'], bnft_rule_txt=p['RULE_TXT'], bnft_limit_txt=p['LIMIT_TXT'],
                       bnft_valid_from=p['VALID_FROM'], bnft_valid_to_excl=p['VALID_TO'])
            self.common_bnft[(p['COMMON_ID'], p['BNFT_CD'])] = row
            return [{'card_common_bnft_id': 'C1'}]
        if name == 'update_common_bnft':
            row = next(iter(self.common_bnft.values()))
            row.update(bnft_nm=p['BNFT_NM'], bnft_rule_txt=p['RULE_TXT'], bnft_limit_txt=p['LIMIT_TXT'])
            return [{}]
        if name == 'insert_common_apply':
            key = (p['COMMON_ID'], p['BNFT_ID'], p['CARD_ID'])
            if key in self.applies: return []
            self.applies.add(key)
            return [{'card_id': p['CARD_ID']}]
        self.card_bnft_writes += 1
        raise AssertionError(name)


def fixture():
    options = [{'brand_opt_cd':'VISA', 'brand_cd':'VISA', 'service_grade_cd':'SIGNATURE',
                'service_type_cd':'02', 'brand_opt_status_cd':'ACTIVE'}]
    cards = [dict(card_id=i, product_cd='CARD_'+str(i), product_nm=name, product_status_cd='ACTIVE', brand_opt_list=options)
             for i,name in [(1,'JADE Classic'),(2,'JADE Prime'),(3,'Other')]]
    quote = 'VISA SIGNATURE 선택서비스 02 JADE Classic JADE Prime 2026년 1월 1일 ~ 12월 31일'
    raw = {'brand_txt':'VISA','service_grade_txt':'SIGNATURE','selection_service_txt':'선택서비스 02',
           'applicable_cards':['JADE Classic','JADE Prime'],'excluded_cards':[],
           'validity_period_txt':'2026년 1월 1일 ~ 12월 31일',
           'evidence':[{'supports':'APPLICABILITY','quote_txt':quote}]}
    candidate = {'card_extr_stg_id':'S1','card_doc_id':'D1','doc_family_cd':'VISA_SIG', 'doc_version_no':1, 'stg_raw_item':raw,
                 'stg_status':'PENDING_REVIEW','stg_sql_check_cd':'LINK_REVIEW',
                 'stg_normalized_item':{'bnft_nm':'발레','bnft_type_cd':'SERVICE','bnft_cond_expr':None,
                   'rule_list':[],'relation_list':[],
                   'checks':{'value_check_cd':'OK'},'merge':{'source_refs':[{'page_no':1}]}}}
    evidence = [dict(evidence_id='E1',quote_txt=quote,source_txt=quote,start_pos=1,end_pos=len(quote),approval_status_cd='PENDING')]
    service = CommonBenefitService(Session())
    service.repo = Repo(cards, candidate, evidence)
    return service


IDS = {'S1': 'valet-identity'}


def test_unionpay_names_match_upi_without_matching_other_brands():
    assert brand_key('UPI') == brand_key('UnionPay') == brand_key('유니온페이')
    assert brand_key('VISA') != brand_key('UPI')


def test_common_benefit_is_stored_once_and_applied_only_to_listed_cards():
    a = fixture()
    assert a.register_run('R1', IDS)[0].status == 'INSERTED'
    assert a.register_run('R1', IDS)[0].status == 'UNCHANGED'
    assert a.path_a(1, IDS)[0].status == 'INSERTED'
    assert [r.status for r in a.path_b('R1', IDS)] == ['UNCHANGED', 'INSERTED', 'REVIEW']
    assert a.path_a(1, IDS)[0].status == 'UNCHANGED'
    assert a.repo.applies == {(7, 'C1', 1), (7, 'C1', 2)} and len(a.repo.common_bnft) == 1
    assert a.repo.card_bnft_writes == 0


def test_apply_requires_registered_common_benefit():
    service = fixture()
    assert service.path_a(1, IDS)[0].reason == '공통 혜택이 먼저 등록되어야 합니다'
    assert not service.repo.applies


def test_register_needs_identity_single_common_and_matching_grade():
    service = fixture()
    assert service.register_run('R1', {})[0].status == 'REVIEW'
    service.repo.commons = []
    assert service.register_run('R1', IDS)[0].reason == '문서의 공통서비스가 하나로 확인되지 않습니다'
    service = fixture()
    service.repo.commons[0]['service_grade_cd'] = 'WORLD'
    assert service.register_run('R1', IDS)[0].reason == '후보의 브랜드·등급이 공통서비스와 다릅니다'
    assert not service.repo.common_bnft


def test_changed_candidate_is_not_overwritten_and_unsupported_selection_is_reviewed():
    service = fixture()
    service.register_run('R1', IDS)
    service.repo.candidate['stg_normalized_item']['bnft_nm'] = 'changed'
    assert service.register_run('R1', IDS)[0].status == 'CHANGE_REVIEW'
    assert next(iter(service.repo.common_bnft.values()))['bnft_nm'] == '발레'
    ambiguous = fixture()
    ambiguous.repo.candidate['stg_raw_item']['selection_service_txt'] = 'UNSUPPORTED'
    assert ambiguous.register_run('R1', {'S1': 'x'})[0].reason == '선택서비스 번호가 하나로 확인되지 않습니다'


def test_identity_is_family_scoped_and_period_is_end_exclusive():
    assert benefit_code('family','key') == benefit_code('family','key')
    assert benefit_code('family','key') != benefit_code('other','key')
    assert period('2026년 1월 1일 ~ 12월 31일') == (date(2026,1,1), date(2027,1,1))


DEFAULT_PERIOD = '이용기간 별도 표기한 경우 외에는 2026년 1월 1일 ~ 12월 31일'


def test_default_period_applies_only_without_own_period():
    def raw(quote):
        return {'validity_period_txt': DEFAULT_PERIOD,
                'evidence': [{'supports': 'RULE', 'quote_txt': quote},
                             {'supports': 'APPLICABILITY', 'quote_txt': '* 본 서비스는 ' + DEFAULT_PERIOD + '까지 제공됩니다.'}]}
    assert candidate_period(raw('· 국내 특급호텔 식음료 매장 5~15% 할인')) == (date(2026,1,1), date(2027,1,1))
    for own in ('· 글로벌 원심 무료 이용 서비스 제공 (4.1~)', '· 현대면세점 할인 (4월 중 오픈 예정)', '· 멤버십 혜택 3개월간 제공'):
        with pytest.raises(ValueError):
            candidate_period(raw(own))
    assert candidate_period({'validity_period_txt': '2026년 1월 1일 ~ 12월 31일'}) == (date(2026,1,1), date(2027,1,1))
    with pytest.raises(ValueError):
        candidate_period({'validity_period_txt': '별도 공지 시까지'})


def test_other_default_period_wordings_and_trailing_kkaji():
    expected = (date(2026,1,1), date(2027,1,1))
    assert period('2026년 1월 1일 ~ 12월 31일까지') == expected
    for text in ('기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지', '기간이따로명시되지않은한 2026년1월1일~ 12월31일'):
        assert candidate_period({'validity_period_txt': text, 'evidence': [{'supports': 'RULE', 'quote_txt': 'Trip.com 호텔 6%'}]}) == expected
        with pytest.raises(ValueError):
            candidate_period({'validity_period_txt': text, 'evidence': [{'supports': 'RULE', 'quote_txt': '그린피 25% 할인 (~6.30)'}]})
    with pytest.raises(ValueError):
        period('2026년 1월 1일 ~ 12월 31일까지 예정')


def test_register_uses_default_period_without_own_period():
    service = fixture()
    service.repo.candidate['stg_raw_item']['validity_period_txt'] = DEFAULT_PERIOD
    assert service.register_run('R1', IDS)[0].status == 'INSERTED'
    assert next(iter(service.repo.common_bnft.values()))['bnft_valid_to_excl'] == date(2027,1,1)


def test_same_span_stored_twice_is_one_source_but_other_position_stays_ambiguous():
    raw = {'evidence': [{'supports': 'RULE', 'support_key': 'r1', 'quote_txt': '그린피 본인 면제'},
                        {'supports': 'APPLICABILITY', 'quote_txt': '등급 카드 소지자에게 공통으로 제공'}]}
    norm = {'rule_list': [{'rule_key': 'r1'}]}
    def row(evidence_id, quote, start, chunk='C1'):
        return dict(evidence_id=evidence_id, quote_txt=quote, card_doc_chunk_id=chunk, start_pos=start, end_pos=start + len(quote) - 1)
    base = [row('E1', '그린피 본인 면제', 10), row('E3', '등급 카드 소지자에게 공통으로 제공', 100, 'N1')]
    # 규칙과 조건이 같은 구절을 인용해 같은 위치의 행이 두 번 저장된 경우
    ids, problem = CommonBenefitService._evidence_ids(raw, norm, [*base, row('E2', '그린피 본인 면제', 10)])
    assert problem is None and ids == ['E1', 'E3']
    # 같은 문자열이 다른 위치에도 있으면 어느 구간인지 모호하다
    ids, problem = CommonBenefitService._evidence_ids(raw, norm, [*base, row('E2', '그린피 본인 면제', 50)])
    assert ids == [] and '모호' in problem


def test_original_visa_code_is_reproduced():
    assert benefit_code('HANA_VS002', 'VISA_SIGNATURE_CONCIERGE') == (
        'BRAND_7F12FC9CF2DC6811E91AE8A18EB1B6CE1379238A4FA2599FB407442C5F046BB9')


def test_revision_updates_only_unmodified_prior_version():
    service = fixture()
    service.register_run('R1', IDS)
    old = deepcopy(service.repo.candidate)
    service.repo.prior = [{'doc_family_cd':old['doc_family_cd'], 'doc_version_no':1, 'stg_raw_item':old['stg_raw_item'],
                           'stg_normalized_item':old['stg_normalized_item']}]
    service.repo.candidate['card_doc_id'] = 'D2'
    service.repo.candidate['doc_version_no'] = 2
    service.repo.candidate['stg_normalized_item']['bnft_nm'] = '발레 변경'
    assert service.register_run('R1', IDS)[0].status == 'UPDATED'
    assert next(iter(service.repo.common_bnft.values()))['bnft_nm'] == '발레 변경'
    new = deepcopy(service.repo.candidate)
    service.repo.prior = [{'doc_family_cd':new['doc_family_cd'], 'doc_version_no':2,
                           'stg_raw_item':new['stg_raw_item'], 'stg_normalized_item':new['stg_normalized_item']}]
    service.repo.candidate = old
    assert service.register_run('R1', IDS)[0].status == 'CHANGE_REVIEW'


def with_limit(service):
    raw = service.repo.candidate['stg_raw_item']
    norm = service.repo.candidate['stg_normalized_item']
    raw['evidence'].append({'supports':'LIMIT','support_key':'L1','quote_txt':'월\n2회'})
    raw['evidence'].append({'supports':'RULE','support_key':'R','quote_txt':'발레 무료 제공'})
    service.repo.evidence.append({'evidence_id':'E2','quote_txt':'월\n2회','source_txt':'월\n2회',
        'start_pos':1,'end_pos':4,'approval_status_cd':'PENDING'})
    service.repo.evidence.append({'evidence_id':'E3','quote_txt':'발레 무료 제공','source_txt':'발레 무료 제공',
        'start_pos':1,'end_pos':8,'approval_status_cd':'PENDING'})
    # 한도는 추출 원본(limits[].limit_key)으로 근거를 확인한다. 한도 풀 정규화는 2026-11-03에 제거했다.
    raw['limits'] = [{'limit_key':'L1','period_cd':'MONTH','cap_unit_cd':'COUNT','limit_num':2,'limit_raw_txt':'월 2회'}]
    norm['rule_list'] = [{'rule_key':'R','rule_status_cd':'DRAFT'}]
    return raw, norm


def test_limit_and_rule_are_quoted_text_and_evidence_is_returned():
    service = fixture()
    with_limit(service)
    decision = service.register_run('R1', IDS)[0]
    assert decision.status == 'INSERTED' and set(decision.evidence_ids) == {'E1', 'E2', 'E3'}
    assert service.register_run('R1', IDS)[0].status == 'UNCHANGED'
    row = next(iter(service.repo.common_bnft.values()))
    assert (row['bnft_rule_txt'], row['bnft_limit_txt']) == ('발레 무료 제공', '월 2회')


def test_condition_quote_is_preserved_in_limit_text():
    raw = {'evidence': [{'supports': 'BNFT', 'quote_txt': '발렛 제공'}]}
    norm = {'bnft_cond_expr': {'branches': [{'atoms': [{'cond_raw_txt': '지난달\n50만원 이상'}]}]}}
    assert common_texts(raw, norm) == ('발렛 제공', '지난달 50만원 이상')


def test_limit_without_located_quote_is_reviewed():
    service = fixture()
    with_limit(service)
    service.repo.evidence = [e for e in service.repo.evidence if e['evidence_id'] != 'E2']
    assert service.register_run('R1', IDS)[0].status == 'REVIEW'
    assert not service.repo.common_bnft
    service = fixture()
    raw, _ = with_limit(service)
    raw['evidence'][1]['support_key'] = 'OTHER'
    assert service.register_run('R1', IDS)[0].status == 'REVIEW'


def test_quote_text_only_joins_source_quotes_without_duplicates():
    items = [{'supports':'LIMIT','quote_txt':'일 1회\n/ 월 30회'}, {'supports':'LIMIT','quote_txt':'월 5천원'},
             {'supports':'LIMIT','quote_txt':'월  5천원'}, {'supports':'RULE','quote_txt':'100원'}]
    assert quote_text(items, 'LIMIT') == '일 1회 / 월 30회 / 월 5천원'
    assert quote_text(items, 'BNFT') is None


def test_same_quote_for_different_targets_is_reviewed():
    service = fixture()
    raw = service.repo.candidate['stg_raw_item']
    norm = service.repo.candidate['stg_normalized_item']
    norm['rule_list'] = [{'rule_key':'R','rule_status_cd':'DRAFT'}]
    raw['evidence'].append({'supports':'RULE','support_key':'R','quote_txt':raw['evidence'][0]['quote_txt']})
    assert service.register_run('R1', IDS)[0].status == 'REVIEW'
    assert not service.repo.common_bnft


def test_explicit_grade_common_requires_product_document_evidence():
    service=fixture()
    raw=service.repo.candidate['stg_raw_item']
    quote='Visa Signature 등급카드 소지자에게 공통으로 제공됩니다'
    raw.update(brand_txt='Visa',service_grade_txt='Signature',selection_service_txt=None,
               applicable_cards=[],validity_period_txt=None,
               evidence=[{'supports':'APPLICABILITY','quote_txt':quote}])
    service.repo.evidence=[dict(evidence_id='E1',quote_txt=quote,source_txt=quote,start_pos=1,end_pos=len(quote),approval_status_cd='PENDING')]
    assert service.register_run('R1',{'S1':'identity'})[0].status=='INSERTED'
    assert service.path_a(1,{'S1':'identity'})[0].status=='REVIEW'
    proof='Visa : Visa Signature 02 유형'
    service.repo.product_evidence=[dict(doc_title='JADE Classic 상품설명서',quote_txt=proof,source_txt=proof,approval_status_cd='PENDING')]
    assert service.path_a(1,{'S1':'identity'})[0].status=='INSERTED'


def test_link_doc_rejects_other_document_types():
    service = fixture()
    service.repo.one = lambda name, **p: {'doc_type_cd': 'PRODUCT_GUIDE'}
    with pytest.raises(ValueError):
        service.link_doc(7, 'D1')


def test_existing_card_benefit_is_reported_not_changed():
    service = fixture()
    service.register_run('R1', IDS)
    service.repo.legacy = {'card_bnft_id': 'OLD'}
    decision = service.path_a(1, IDS)[0]
    assert decision.card_bnft_id == 'OLD' and service.repo.card_bnft_writes == 0
