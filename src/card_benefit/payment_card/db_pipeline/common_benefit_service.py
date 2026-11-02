"""V7 공통 문서 후보를 카드별 DRAFT 혜택으로 적용한다.

식별자 및 한도 집계 기준은 호출자가 근거를 검토해 제공한다. 자동 승인은 하지 않는다.
"""
from __future__ import annotations

from copy import deepcopy
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import re

from psycopg.types.json import Jsonb


def compact(value: str) -> str:
    return "".join(value.casefold().split())


def benefit_code(family: str, identity: str) -> str:
    """문서 계열과 검토된 업무 식별자만 사용한다. 문서 버전과 혜택명은 사용하지 않는다."""
    if not family or not identity or len(identity) > 200:
        raise ValueError("문서 계열과 검토된 혜택 식별자가 필요합니다")
    key = (family + "\0" + identity).encode("utf-8")
    return "BRAND_" + hashlib.sha256(key).hexdigest().upper()


def period(raw: str | None):
    if raw is None or not raw.strip():
        return None, None
    match = re.fullmatch(r"\s*(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*[~～-]\s*(?:(\d{4})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*", raw)
    if not match:
        raise ValueError("제공 기간을 안전하게 해석할 수 없습니다")
    y, m, d, y2, m2, d2 = match.groups()
    start = date(int(y), int(m), int(d))
    end = date(int(y2 or y), int(m2), int(d2)) + timedelta(days=1)
    if end <= start:
        raise ValueError("제공 기간이 올바르지 않습니다")
    return start, end


@dataclass(frozen=True)
class Decision:
    card_id: int
    stg_id: str
    status: str
    reason: str
    bnft_cd: str | None = None
    card_bnft_id: str | None = None


class CommonBenefitRepository:
    """기존 세션과 mapper를 이용한다. 연결과 트랜잭션은 호출자가 관리한다."""
    def __init__(self, session):
        self.session = session

    def rows(self, name, **params):
        return self.session.select_list('common_benefit_repository.' + name, params)

    def one(self, name, **params):
        return self.session.select_one('common_benefit_repository.' + name, params)

    def write(self, name, **params):
        return self.session.execute('common_benefit_repository.' + name, params) or []


class CommonBenefitService:
    """A/B가 공유하는 후보 판정과 등록. 상태 승격 및 기존 혜택 삭제는 하지 않는다."""
    def __init__(self, session, user_id='SYSTEM'):
        self.session = session
        self.repo = CommonBenefitRepository(session)
        self.user_id = user_id

    def register_card(self, product: dict) -> int:
        """상품 코드가 같으면 입력 정보도 일치해야 한다."""
        values = {k: product[k] for k in ('product_cd', 'product_nm', 'issuer', 'card_kind_cd', 'brand_opt_list')}
        with self.session.transaction():
            before = self._integrity_errors()
            self.repo.write('insert_card', PRODUCT_CD=values['product_cd'], PRODUCT_NM=values['product_nm'],
                            ISSUER=values['issuer'], CARD_KIND_CD=values['card_kind_cd'],
                            BRAND_OPT_LIST=Jsonb(values['brand_opt_list']), USER_ID=self.user_id)
            row = self.repo.one('find_card_by_code', PRODUCT_CD=values['product_cd'])
            if not row or any(row[k] != v for k, v in values.items()):
                raise ValueError('기존 상품 코드의 정보가 입력과 다릅니다')
            self._assert_no_new_errors(before)
            return row['card_id']

    def path_a(self, card_id: int, identities: dict, pool_bases: dict | None = None):
        """기존 공통 문서 실행을 검색한다. AI 추출을 호출하지 않는다."""
        results = []
        for run in self.repo.rows('list_runs'):
            results.extend(self.apply_run(card_id, run['card_ai_run_id'], identities, pool_bases))
        return results

    def register_card_and_apply(self, product: dict, identities: dict, pool_bases: dict | None = None):
        card_id = self.register_card(product)
        return card_id, self.path_a(card_id, identities, pool_bases)

    def path_b(self, run_id: str, identities: dict, pool_bases: dict | None = None):
        """이미 등록·추출된 문서의 기존 카드들을 같은 적용 로직으로 처리한다."""
        results = []
        for card in self.repo.rows('list_cards'):
            results.extend(self.apply_run(card['card_id'], run_id, identities, pool_bases))
        return results

    def register_document_and_apply(self, pdf, register_service, extraction_service, identities: dict, pool_bases: dict | None = None):
        """문서 등록·추출은 기존 서비스를 재사용한다. 호출자가 LLM 실행을 명시적으로 선택해야 한다."""
        registration = register_service.register(pdf, apply=True)
        if not registration.card_doc_id:
            raise ValueError('문서 ID가 없습니다')
        extraction = extraction_service.run(registration.card_doc_id, card_id=None)
        if extraction.status != 'SUCCEEDED':
            raise ValueError('문서 추출이 완료되지 않아 혜택을 적용하지 않습니다')
        return registration, extraction, self.path_b(extraction.card_ai_run_id, identities, pool_bases)

    def apply_run(self, card_id: int, run_id: str, identities: dict, pool_bases: dict | None = None):
        results = []
        # 카드 행 잠금으로 카드별 중복 검사, 풀 생성, 혜택 및 근거 연결을 직렬화한다.
        with self.session.transaction():
            before = self._integrity_errors()
            card = self.repo.one('lock_card', CARD_ID=card_id)
            if not card:
                raise ValueError('카드가 없습니다')
            for candidate in self.repo.rows('list_candidates', RUN_ID=run_id):
                evidence = self.repo.rows('candidate_evidence', STG_ID=candidate['card_extr_stg_id'])
                results.append(self._apply_candidate(card, candidate, evidence, identities, pool_bases or {}))
            self._assert_no_new_errors(before)
        return results

    def _integrity_errors(self):
        return Counter((r['gate_cd'], r['issue_key']) for r in self.repo.rows('integrity_errors'))

    def _assert_no_new_errors(self, before):
        new = self._integrity_errors() - before
        if new:
            raise ValueError('신규 정합성 위반으로 트랜잭션을 롤백합니다: ' + ', '.join(sorted({g for g, _ in new})))

    def _apply_candidate(self, card, candidate, evidence, identities, pool_bases):
        card_id, stg_id = card['card_id'], candidate['card_extr_stg_id']
        def review(reason, status='REVIEW'):
            return Decision(card_id, stg_id, status, reason)
        raw, norm = candidate['stg_raw_item'], candidate['stg_normalized_item']
        if card['product_status_cd'] != 'ACTIVE':
            return review('활성 카드가 아닙니다', 'EXCLUDED')
        if candidate['stg_status'] in ('REJECTED', 'RETIRED'):
            return review('제외된 후보입니다', 'EXCLUDED')
        if candidate['stg_sql_check_cd'] not in ('OK', 'LINK_REVIEW') or norm.get('checks', {}).get('value_check_cd') != 'OK':
            return review('후보 값 또는 구조 검증이 필요합니다')
        if len(norm.get('merge', {}).get('source_refs', [])) != 1:
            return review('이름 기준 다중 항목 병합을 별도 검토해야 합니다')
        if norm.get('relation_list'):
            return review('혜택 간 관계의 카드별 ID 연결을 확인해야 합니다')
        located = [e for e in evidence if e['start_pos'] is not None and e['end_pos'] is not None
                   and e.get('approval_status_cd') in ('PENDING','APPROVED')
                   and e.get('source_txt') is not None and compact(e['source_txt']) == compact(e['quote_txt'])]
        quotes = [compact(e['quote_txt']) for e in located]
        def supported(value):
            return bool(value) and any(compact(value) in quote for quote in quotes)
        applicability_quotes = [compact(e['quote_txt']) for e in raw.get('evidence', [])
                                if e.get('supports') == 'APPLICABILITY']
        def applies_supported(value):
            return bool(value) and any(q in quotes and compact(value) in q for q in applicability_quotes)
        names = raw.get('applicable_cards') or []
        exclusions = raw.get('excluded_cards') or []
        if any(not applies_supported(v) for v in [*names, *exclusions]):
            return review('대상 또는 제외 카드의 원문 근거를 확인해야 합니다')
        card_names = {compact(card['product_cd']), compact(card['product_nm'])}
        if any(compact(v) in card_names for v in exclusions):
            return review('문서에서 제외한 카드입니다', 'EXCLUDED')
        if names and not any(compact(v) in card_names for v in names):
            return review('대상 카드 목록에서 해당 상품을 확인하지 못했습니다')
        brand, grade = raw.get('brand_txt'), raw.get('service_grade_txt')
        selection = raw.get('selection_service_txt')
        if not all(applies_supported(v) for v in (brand, grade)):
            return review('브랜드와 등급의 적용 근거가 불명확합니다')
        if selection and not applies_supported(selection):
            return review('선택서비스의 적용 근거가 불명확합니다')
        selection_codes = set(re.findall(r'(?<!\d)(0[1-4])(?!\d)', selection or ''))
        if selection and len(selection_codes) != 1:
            return review('선택서비스 번호가 하나로 확인되지 않습니다')
        options = [o for o in card['brand_opt_list'] if o.get('brand_opt_status_cd') == 'ACTIVE'
                   and compact(o.get('brand_cd', '')) == compact(brand)
                   and compact(o.get('service_grade_cd', '')) == compact(grade)
                   and (not selection or o.get('service_type_cd') in selection_codes)]
        if len(options) != 1:
            return review('브랜드·등급·선택서비스 선택지가 하나로 확인되지 않습니다')
        product_basis = None
        if not names:
            # 등급 전체 공통서비스는 안내서의 명시적 공통 범위와 상품설명서의
            # 해당 카드 브랜드·등급 근거를 둘 다 확인한다. 선택서비스에는 쓰지 않는다.
            broad = next((e['quote_txt'] for e in located if compact(e['quote_txt']) in applicability_quotes
                          and all(compact(t) in compact(e['quote_txt']) for t in (brand, grade, '등급카드', '소지자에게공통으로제공됩니다'))), None)
            if selection or not broad:
                return review('명시적 전체 등급 공통서비스 또는 대상 카드 근거가 없습니다')
            for proof in self.repo.rows('product_brand_evidence', CARD_ID=card_id):
                quote = proof.get('quote_txt') or ''
                source = proof.get('source_txt') or ''
                service_type = options[0].get('service_type_cd')
                if (compact(card['product_nm'] + ' 상품설명서') == compact(proof.get('doc_title') or '')
                        and compact(quote) == compact(source)
                        and compact(brand) in compact(quote) and compact(grade) in compact(quote)
                        and (service_type in ('NONE', 'COMMON') or service_type in re.findall(r'(?<!\d)(0[1-4])(?!\d)',quote))):
                    product_basis = quote
                    break
            if not product_basis:
                return review('상품설명서에서 카드의 브랜드·등급을 확인해야 합니다')
        elif not selection and options[0].get('service_type_cd') != 'NONE':
            return review('선택서비스 여부가 확인되지 않았습니다')
        validity = raw.get('validity_period_txt')
        if validity and not applies_supported(validity):
            return review('제공 기간의 원문 근거가 없습니다')
        try:
            start, end = period(validity)
            code = benefit_code(candidate.get('doc_family_cd'), identities.get(stg_id))
        except (ValueError, OverflowError) as error:
            return review(str(error))
        if product_basis:
            basis = broad + ' / 상품설명서: ' + product_basis
        else:
            basis = next(e['quote_txt'] for e in located if compact(card['product_nm']) in compact(e['quote_txt'])
                         or compact(card['product_cd']) in compact(e['quote_txt']))
        opts = [options[0]['brand_opt_cd']]
        existing = self.repo.one('find_benefit', CARD_ID=card_id, BNFT_CD=code)
        limits = norm.get('limit_list', [])
        rules = deepcopy(norm.get('rule_list', []))
        planned_rules = deepcopy(rules)
        if existing and (existing['verification_status_cd'] != 'PENDING_REVIEW' or existing['rule_select_cd'] is not None):
            return Decision(card_id, stg_id, 'CHANGE_REVIEW', '확정 상태 또는 별도 규칙 선택이 있는 기존 혜택은 수정하지 않습니다', code, existing['card_bnft_id'])
        if any(rule.get('rule_status_cd') != 'DRAFT' for rule in rules):
            return review('확정되었거나 상태가 불명확한 규칙은 자동 복사하지 않습니다')
        # 원천 테이블에는 supports/support_key가 없으므로 원문 인용이 유일하게
        # 하나의 대상에 대응할 때만 연결한다. 중복 인용은 임의로 배정하지 않는다.
        kinds = {'BNFT': 'BNFT', 'APPLICABILITY': 'BNFT', 'RULE': 'RULE', 'LIMIT': 'POOL'}
        source_targets = {}
        rule_keys = {r['rule_key'] for r in rules}
        pool_keys = {p['pool_key'] for p in limits}
        for item in raw.get('evidence', []):
            kind = kinds.get(item.get('supports'))
            key = item.get('support_key') if kind in ('RULE', 'POOL') else None
            if kind is None or (kind == 'RULE' and key not in rule_keys) or (kind == 'POOL' and key not in pool_keys):
                return review('근거가 어떤 혜택·규칙·한도에 속하는지 확인해야 합니다')
            quote = compact(item.get('quote_txt') or '')
            matches = [e for e in located if compact(e['quote_txt']) == quote]
            if not quote or len(matches) != 1:
                return review('원문 근거가 없거나 동일한 인용이 중복되어 대상이 모호합니다')
            target = (kind, key)
            if quote in source_targets and source_targets[quote][0] != target:
                return review('동일 인용이 여러 대상에 사용되어 근거 연결을 검토해야 합니다')
            source_targets[quote] = (target, matches[0]['evidence_id'])
        targets = {target for target, _ in source_targets.values()}
        if ('BNFT', None) not in targets or any(('RULE', k) not in targets for k in rule_keys):
            return review('혜택 또는 계산 규칙을 뒷받침하는 근거가 없습니다')
        for limit in limits:
            spec = pool_bases.get((stg_id, limit['pool_key']))
            source_quotes = [compact(e['quote_txt']) for e in raw.get('evidence', [])
                             if e.get('supports') == 'LIMIT' and e.get('support_key') == limit['pool_key']]
            if (not spec or not spec.get('aggregation_key_cd') or not supported(spec.get('basis_txt'))
                    or not self.repo.one('valid_aggregation', CODE=spec['aggregation_key_cd'])
                    or not any(q in quotes for q in source_quotes)
                    or limit.get('limit_num') is None or limit.get('period_cd') in (None, 'UNKNOWN')
                    or limit.get('cap_unit_cd') in (None, 'UNKNOWN')):
                return review('한도 집계 기준 또는 값의 원문 검토가 필요합니다')
        needs_update = False
        pool_ids = {}
        if existing:
            # 기존 카드별 조건이나 수동 수정 여부를 추정하지 않는다.
            comparable = (existing['bnft_nm'] == norm['bnft_nm'] and existing['bnft_type_cd'] == norm['bnft_type_cd']
                          and existing['bnft_origin_cd'] == 'BRAND_SERVICE' and existing['bnft_scope_cd'] == 'BRAND'
                          and existing['bnft_brand_opt_cds'] == opts and existing['bnft_cond_expr'] == norm.get('bnft_cond_expr')
                          and existing['bnft_valid_from'] == start and existing['bnft_valid_to_excl'] == end
                          and self._same_rules_and_pools(card_id, existing['card_bnft_id'], stg_id, rules, limits, pool_bases, existing['rule_list'])
                          and not existing['relation_list'])
            if not comparable:
                needs_update = self._can_update(card_id, candidate['doc_family_cd'], candidate['doc_version_no'], existing, limits, opts)
                if not needs_update:
                    return Decision(card_id, stg_id, 'CHANGE_REVIEW', '카드별 변경 또는 출처를 안전하게 비교할 수 없어 자동 갱신하지 않습니다', code, existing['card_bnft_id'])
        # 기존 연결의 선택지와 충돌하면 변경하지 않는다.
        link = self.repo.one('get_product_doc', CARD_ID=card_id, DOC_ID=candidate['card_doc_id'])
        if link and (link['doc_role_cd'] != 'BRAND_SERVICE' or link['approval_status_cd'] == 'REJECTED'
                     or not set(opts).issubset(link['brand_opt_cds'] or [])):
            return review('기존 문서 연결의 브랜드 선택지와 충돌합니다')
        if not link:
            self.repo.write('insert_product_doc', CARD_ID=card_id, DOC_ID=candidate['card_doc_id'],
                            BRAND_OPTS=opts, BASIS=basis, USER_ID=self.user_id)
        if existing:
            benefit_id = existing['card_bnft_id']
            if limits:
                links = self.repo.rows('get_rule_pools', CARD_ID=card_id, BNFT_ID=benefit_id)
                for rule in planned_rules:
                    for ref in rule.get('pool_refs', []):
                        matches = [x['pool_id'] for x in links if x['rule_key'] == rule['rule_key']
                                   and x['pool_role_cd'] == ref['pool_role_cd']]
                        if len(matches) != 1 or (ref['pool_id'] in pool_ids and pool_ids[ref['pool_id']] != matches[0]):
                            raise ValueError('기존 한도 근거의 연결 대상을 하나로 확인할 수 없습니다')
                        pool_ids[ref['pool_id']] = matches[0]
            if needs_update:
                for rule in rules:
                    rule.pop('pool_refs', None)
                changed = self.repo.write('update_benefit', CARD_ID=card_id, BNFT_ID=benefit_id,
                    BNFT_NM=norm['bnft_nm'], BNFT_TYPE=norm['bnft_type_cd'],
                    COND=Jsonb(norm['bnft_cond_expr']) if norm.get('bnft_cond_expr') is not None else None,
                    RULES=Jsonb(rules), VALID_FROM=start, VALID_TO=end)
                if not changed:
                    raise ValueError('기존 혜택 상태가 변경되어 갱신을 중단합니다')
        else:
            for limit in limits:
                spec = pool_bases[(stg_id, limit['pool_key'])]
                tiers = [{'tier_key': 'TIER1', 'tier_priority': 1, 'predicate_state_cd': 'PENDING_REVIEW',
                          'limit_num': limit['limit_num']}]
                row = self.repo.write('insert_pool', CARD_ID=card_id, POOL_SCOPE=limit['pool_scope_cd'],
                    PERIOD=limit['period_cd'], CAP_UNIT=limit['cap_unit_cd'], AGGREGATION=spec['aggregation_key_cd'], TIERS=Jsonb(tiers))
                pool_ids[limit['pool_key']] = row[0]['pool_id']
            relationships = []
            for rule in rules:
                for ref in rule.pop('pool_refs', []):
                    if ref['pool_id'] not in pool_ids:
                        raise ValueError('한도 참조가 없습니다')
                    relationships.append((rule['rule_key'], pool_ids[ref['pool_id']], ref['pool_role_cd']))
            inserted = self.repo.write('insert_benefit', CARD_ID=card_id, BNFT_CD=code, BNFT_NM=norm['bnft_nm'],
                BNFT_TYPE=norm['bnft_type_cd'], BRAND_OPTS=opts,
                COND=Jsonb(norm['bnft_cond_expr']) if norm.get('bnft_cond_expr') is not None else None,
                RULES=Jsonb(rules), VALID_FROM=start, VALID_TO=end)
            if not inserted:
                raise ValueError('동시 등록 충돌: 전체 트랜잭션을 롤백합니다')
            benefit_id = inserted[0]['card_bnft_id']
            for rule_key, pool_id, role in relationships:
                self.repo.write('insert_rule_pool', CARD_ID=card_id, BNFT_ID=benefit_id,
                                RULE_KEY=rule_key, POOL_ID=pool_id, POOL_ROLE=role)
        for (kind, key), evidence_id in source_targets.values():
            if kind == 'BNFT':
                self.repo.write('insert_evidence_link', CARD_ID=card_id, BNFT_ID=benefit_id, EVIDENCE_ID=evidence_id)
            elif kind == 'RULE':
                self.repo.write('insert_rule_evidence_link', CARD_ID=card_id, BNFT_ID=benefit_id,
                                RULE_KEY=key, EVIDENCE_ID=evidence_id)
            else:
                if key not in pool_ids:
                    raise ValueError('한도 근거의 연결 대상을 확인할 수 없습니다')
                self.repo.write('insert_pool_evidence_link', CARD_ID=card_id, POOL_ID=pool_ids[key], EVIDENCE_ID=evidence_id)
        return Decision(card_id, stg_id, 'UPDATED' if needs_update else ('UNCHANGED' if existing else 'INSERTED'), '검토 대기', code, benefit_id)

    def _can_update(self, card_id, family, version, existing, limits, options):
        """이전 원문 후보와 현재 행이 같을 때만 한도 없는 검토 대기 혜택을 갱신한다."""
        if (limits or existing['verification_status_cd'] != 'PENDING_REVIEW'
                or existing['bnft_origin_cd'] != 'BRAND_SERVICE' or existing['bnft_scope_cd'] != 'BRAND'
                or existing['bnft_brand_opt_cds'] != options or existing['relation_list']):
            return False
        sources = self.repo.rows('prior_sources', CARD_ID=card_id, BNFT_ID=existing['card_bnft_id'])
        same_family = [s for s in sources if s['doc_family_cd'] == family]
        if not same_family or version is None or any(s['doc_version_no'] >= version for s in same_family):
            return False
        for source in same_family:
            old = source['stg_normalized_item']
            if source['doc_family_cd'] != family or old.get('limit_list') or old.get('relation_list'):
                continue
            try:
                start, end = period(source['stg_raw_item'].get('validity_period_txt'))
            except (ValueError, OverflowError):
                continue
            if (existing['bnft_nm'] == old.get('bnft_nm') and existing['bnft_type_cd'] == old.get('bnft_type_cd')
                    and existing['bnft_cond_expr'] == old.get('bnft_cond_expr') and
                    existing['rule_list'] == [{k:v for k,v in r.items() if k != 'pool_refs'} for r in old.get('rule_list', [])]
                    and existing['bnft_valid_from'] == start and existing['bnft_valid_to_excl'] == end):
                return True
        return False

    def _same_rules_and_pools(self, card_id, benefit_id, stg_id, rules, limits, bases, existing_rules):
        if len(rules) != len(existing_rules):
            return False
        links = self.repo.rows('get_rule_pools', CARD_ID=card_id, BNFT_ID=benefit_id)
        expected = []
        existing_by_key = {r['rule_key']: r for r in existing_rules}
        for rule in rules:
            other = existing_by_key.get(rule['rule_key'])
            refs = rule.pop('pool_refs', [])
            if not other or rule != other:
                return False
            expected.extend((rule['rule_key'], ref['pool_id'], ref['pool_role_cd']) for ref in refs)
        if len(links) != len(expected) or {key for _,key,_ in expected} != {limit['pool_key'] for limit in limits}:
            return False
        mapped = {}
        for limit in limits:
            tiers = [{'tier_key':'TIER1','tier_priority':1,'predicate_state_cd':'PENDING_REVIEW','limit_num':limit['limit_num']}]
            matches = []
            for pool_id in {link['pool_id'] for link in links}:
                pool = self.repo.one('get_pool', CARD_ID=card_id, POOL_ID=pool_id)
                if pool and (pool['pool_scope_cd'],pool['period_cd'],pool['cap_unit_cd'],pool['aggregation_key_cd'],pool['tier_list']) == (
                    limit['pool_scope_cd'],limit['period_cd'],limit['cap_unit_cd'],bases[(stg_id,limit['pool_key'])]['aggregation_key_cd'],tiers):
                    matches.append(pool_id)
            if len(matches) != 1:
                return False
            mapped[limit['pool_key']] = matches[0]
        return {(r, mapped[k], role) for r,k,role in expected} == {(r['rule_key'],r['pool_id'],r['pool_role_cd']) for r in links}
