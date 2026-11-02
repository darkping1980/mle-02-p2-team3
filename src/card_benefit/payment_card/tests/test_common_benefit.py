"""공통 적용 판단과 두 경로의 동작. 저장소는 메모리 Mock이다."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date

from payment_card.db_pipeline.common_benefit_service import CommonBenefitService, benefit_code, period


class Session:
    @contextmanager
    def transaction(self):
        yield self


class Repo:
    def __init__(self, cards, candidate, evidence):
        self.cards = {c['card_id']: c for c in cards}
        self.candidate, self.evidence = candidate, evidence
        self.benefits, self.docs, self.links = {}, {}, set()
        self.pools = {}
        self.rule_pools = []
        self.prior = []
        self.product_evidence = []

    def rows(self, name, **p):
        if name == 'integrity_errors': return []
        if name == 'list_runs': return [{'card_ai_run_id': 'R1'}]
        if name == 'list_cards': return [{'card_id': x} for x in self.cards]
        if name == 'list_candidates': return [self.candidate]
        if name == 'candidate_evidence': return self.evidence
        if name == 'prior_sources': return self.prior
        if name == 'product_brand_evidence': return self.product_evidence
        if name == 'get_rule_pools': return [r for r in self.rule_pools if r['card_id']==p['CARD_ID'] and r['card_bnft_id']==p['BNFT_ID']]
        raise AssertionError(name)

    def one(self, name, **p):
        if name == 'lock_card': return self.cards.get(p['CARD_ID'])
        if name == 'find_benefit': return self.benefits.get((p['CARD_ID'], p['BNFT_CD']))
        if name == 'get_product_doc': return self.docs.get((p['CARD_ID'], p['DOC_ID']))
        if name == 'valid_aggregation': return {'common_cd':p['CODE']} if p['CODE'] == 'CARD_MEMBER' else None
        if name == 'get_pool': return self.pools.get((p['CARD_ID'],p['POOL_ID']))
        raise AssertionError(name)

    def write(self, name, **p):
        if name == 'insert_product_doc':
            self.docs[(p['CARD_ID'], p['DOC_ID'])] = {'doc_role_cd': 'BRAND_SERVICE', 'brand_opt_cds': p['BRAND_OPTS'], 'approval_status_cd': 'PENDING'}
            return [{'card_id': p['CARD_ID']}]
        if name == 'insert_benefit':
            row = {'card_bnft_id': f"B{p['CARD_ID']}", 'bnft_nm': p['BNFT_NM'], 'bnft_type_cd': p['BNFT_TYPE'],
                   'bnft_origin_cd': 'BRAND_SERVICE', 'bnft_scope_cd': 'BRAND', 'bnft_brand_opt_cds': p['BRAND_OPTS'],
                   'bnft_cond_expr': p['COND'], 'bnft_valid_from': p['VALID_FROM'], 'bnft_valid_to_excl': p['VALID_TO'],
                   'rule_list': p['RULES'].obj, 'rule_select_cd': None, 'relation_list': [], 'verification_status_cd': 'PENDING_REVIEW'}
            self.benefits[(p['CARD_ID'], p['BNFT_CD'])] = row
            return [{'card_bnft_id': row['card_bnft_id']}]
        if name == 'insert_evidence_link':
            self.links.add((p['CARD_ID'], p['BNFT_ID'], p['EVIDENCE_ID']))
            return []
        if name == 'insert_rule_evidence_link':
            self.links.add((p['CARD_ID'],p['RULE_KEY'],p['EVIDENCE_ID']))
            return []
        if name == 'insert_pool_evidence_link':
            self.links.add((p['CARD_ID'],p['POOL_ID'],p['EVIDENCE_ID']))
            return []
        if name == 'insert_pool':
            pool_id = f"P{p['CARD_ID']}"
            self.pools[(p['CARD_ID'],pool_id)] = {'pool_scope_cd':p['POOL_SCOPE'],'period_cd':p['PERIOD'],
                'cap_unit_cd':p['CAP_UNIT'],'aggregation_key_cd':p['AGGREGATION'],'tier_list':p['TIERS'].obj}
            return [{'pool_id':pool_id}]
        if name == 'insert_rule_pool':
            self.rule_pools.append({'card_id':p['CARD_ID'],'card_bnft_id':p['BNFT_ID'],'rule_key':p['RULE_KEY'],
                                    'pool_id':p['POOL_ID'],'pool_role_cd':p['POOL_ROLE']})
            return [{'pool_id':p['POOL_ID']}]
        if name == 'update_benefit':
            row = next(r for (card, _), r in self.benefits.items() if card == p['CARD_ID'] and r['card_bnft_id'] == p['BNFT_ID'])
            row.update(bnft_nm=p['BNFT_NM'],bnft_type_cd=p['BNFT_TYPE'],bnft_cond_expr=p['COND'],
                       rule_list=p['RULES'].obj,bnft_valid_from=p['VALID_FROM'],bnft_valid_to_excl=p['VALID_TO'])
            return [{'card_bnft_id': row['card_bnft_id']}]
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
                   'rule_list':[],'relation_list':[],'limit_list':[],
                   'checks':{'value_check_cd':'OK'},'merge':{'source_refs':[{'page_no':1}]}}}
    evidence = [dict(evidence_id='E1',quote_txt=quote,source_txt=quote,start_pos=1,end_pos=len(quote),approval_status_cd='PENDING')]
    service = CommonBenefitService(Session())
    service.repo = Repo(cards, candidate, evidence)
    return service


def test_paths_share_evidence_and_are_idempotent():
    a = fixture()
    assert a.path_a(1, {'S1':'valet-identity'})[0].status == 'INSERTED'
    statuses = [r.status for r in a.path_b('R1', {'S1':'valet-identity'})]
    assert statuses == ['UNCHANGED','INSERTED','REVIEW']
    assert a.path_a(1, {'S1':'valet-identity'})[0].status == 'UNCHANGED'
    assert {e[2] for e in a.repo.links} == {'E1'} and len(a.repo.links) == 2
    assert all(x['verification_status_cd'] == 'PENDING_REVIEW' for x in a.repo.benefits.values())
    assert all(x['approval_status_cd'] == 'PENDING' for x in a.repo.docs.values())
    b = fixture()
    b.path_b('R1', {'S1':'valet-identity'})
    b.path_a(1, {'S1':'valet-identity'})
    assert a.repo.benefits == b.repo.benefits and a.repo.links == b.repo.links


def test_ambiguous_identity_target_and_changed_candidate_are_not_written():
    service = fixture()
    assert service.path_a(1, {})[0].status == 'REVIEW'
    service.path_a(1, {'S1':'valet-identity'})
    service.repo.candidate['stg_normalized_item']['bnft_nm'] = 'changed'
    assert service.path_a(1, {'S1':'valet-identity'})[0].status == 'CHANGE_REVIEW'
    assert len(service.repo.benefits) == 1
    ambiguous = fixture()
    ambiguous.repo.candidate['stg_raw_item']['selection_service_txt'] = 'UNSUPPORTED'
    assert ambiguous.path_a(1, {'S1':'x'})[0].status == 'REVIEW'
    assert not ambiguous.repo.benefits


def test_identity_is_family_scoped_and_period_is_end_exclusive():
    assert benefit_code('family','key') == benefit_code('family','key')
    assert benefit_code('family','key') != benefit_code('other','key')
    assert period('2026년 1월 1일 ~ 12월 31일') == (date(2026,1,1), date(2027,1,1))


def test_revision_updates_only_unmodified_pending_source():
    service = fixture()
    service.path_a(1, {'S1':'valet-identity'})
    old = deepcopy(service.repo.candidate)
    service.repo.prior = [{'doc_family_cd':old['doc_family_cd'], 'doc_version_no':1, 'stg_raw_item':old['stg_raw_item'],
                           'stg_normalized_item':old['stg_normalized_item']}]
    service.repo.candidate['card_doc_id'] = 'D2'
    service.repo.candidate['doc_version_no'] = 2
    service.repo.evidence[0]['evidence_id'] = 'E2'
    service.repo.candidate['stg_normalized_item']['bnft_nm'] = '발레 변경'
    assert service.path_a(1, {'S1':'valet-identity'})[0].status == 'UPDATED'
    assert next(iter(service.repo.benefits.values()))['bnft_nm'] == '발레 변경'
    assert {key[2] for key in service.repo.links} == {'E1','E2'}
    assert len(service.repo.docs) == 2
    new = deepcopy(service.repo.candidate)
    service.repo.prior = [{'doc_family_cd':new['doc_family_cd'], 'doc_version_no':2,
                           'stg_raw_item':new['stg_raw_item'], 'stg_normalized_item':new['stg_normalized_item']}]
    service.repo.candidate = old
    assert service.path_a(1, {'S1':'valet-identity'})[0].status == 'CHANGE_REVIEW'


def test_limit_requires_reviewed_basis_and_is_idempotent():
    service = fixture()
    raw = service.repo.candidate['stg_raw_item']
    norm = service.repo.candidate['stg_normalized_item']
    raw['evidence'].append({'supports':'LIMIT','support_key':'L1','quote_txt':'회원 카드 월 2회'})
    raw['evidence'].append({'supports':'RULE','support_key':'R','quote_txt':'발레 무료 제공'})
    service.repo.evidence.append({'evidence_id':'E2','quote_txt':'회원 카드 월 2회','source_txt':'회원 카드 월 2회',
        'start_pos':1,'end_pos':10,'approval_status_cd':'PENDING'})
    service.repo.evidence.append({'evidence_id':'E3','quote_txt':'발레 무료 제공','source_txt':'발레 무료 제공',
        'start_pos':1,'end_pos':8,'approval_status_cd':'PENDING'})
    norm['limit_list'] = [{'pool_key':'L1','pool_scope_cd':'BENEFIT','period_cd':'MONTH','cap_unit_cd':'COUNT','limit_num':2}]
    norm['rule_list'] = [{'rule_key':'R','rule_status_cd':'DRAFT','pool_refs':[{'pool_id':'L1','pool_role_cd':'CONSUME'}]}]
    assert service.path_a(1, {'S1':'id'})[0].status == 'REVIEW'
    bases = {('S1','L1'):{'aggregation_key_cd':'CARD_MEMBER','basis_txt':'회원 카드'}}
    assert service.path_a(1, {'S1':'id'}, bases)[0].status == 'INSERTED'
    assert service.path_a(1, {'S1':'id'}, bases)[0].status == 'UNCHANGED'
    assert len(service.repo.pools) == 1 and (1,'P1','E2') in service.repo.links
    assert (1,'R','E3') in service.repo.links and (1,'B1','E3') not in service.repo.links


def test_same_quote_for_different_targets_is_reviewed():
    service = fixture()
    raw = service.repo.candidate['stg_raw_item']
    norm = service.repo.candidate['stg_normalized_item']
    norm['rule_list'] = [{'rule_key':'R','rule_status_cd':'DRAFT','pool_refs':[]}]
    raw['evidence'].append({'supports':'RULE','support_key':'R','quote_txt':raw['evidence'][0]['quote_txt']})
    assert service.path_a(1, {'S1':'id'})[0].status == 'REVIEW'
    assert not service.repo.benefits


def test_explicit_grade_common_requires_product_document_evidence():
    service=fixture()
    raw=service.repo.candidate['stg_raw_item']
    quote='Visa Signature 등급카드 소지자에게 공통으로 제공됩니다'
    raw.update(brand_txt='Visa',service_grade_txt='Signature',selection_service_txt=None,
               applicable_cards=[],validity_period_txt=None,
               evidence=[{'supports':'APPLICABILITY','quote_txt':quote}])
    service.repo.evidence=[dict(evidence_id='E1',quote_txt=quote,source_txt=quote,start_pos=1,end_pos=len(quote),approval_status_cd='PENDING')]
    assert service.path_a(1,{'S1':'identity'})[0].status=='REVIEW'
    proof='Visa : Visa Signature 02 유형'
    service.repo.product_evidence=[dict(doc_title='JADE Classic 상품설명서',quote_txt=proof,source_txt=proof,approval_status_cd='PENDING')]
    assert service.path_a(1,{'S1':'identity'})[0].status=='INSERTED'
