"""상품설명서 추출 후보를 ``card_bnft`` 에 등록한다.

검토 전 상태인 PENDING_REVIEW로만 등록하고 승인하지 않는다. 같은 혜택 코드가 있으면 수정하지 않는다.
검색 텍스트와 임베딩은 등록을 커밋한 뒤 ``EmbeddingService.embed_new`` 가 처리하므로, 실패해도 등록은 남는다.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from .common_benefit_service import CommonBenefitRepository, compact, quote_text
from .extraction_service import strip_calc_atoms, strip_calc_rule


@dataclass(frozen=True)
class ProductDecision:
    """후보 1건의 판정. status는 INSERTED, UNCHANGED, REVIEW, EXCLUDED 중 하나다."""
    card_id: int
    stg_id: str
    status: str
    reason: str
    bnft_cd: str | None = None
    card_bnft_id: str | None = None


class ProductBenefitService:
    def __init__(self, session, embedding_service=None):
        self.session = session
        self.repo = CommonBenefitRepository(session)
        self.embedding_service = embedding_service

    def register_run(self, card_id: int, run_id: str) -> list[ProductDecision]:
        """실행의 혜택 후보를 등록한다. 정합성 위반이 새로 생기면 전체를 되돌린다."""
        results = []
        with self.session.transaction():
            before = self._errors()
            if not self.repo.one('lock_card', CARD_ID=card_id):
                raise ValueError('카드가 없습니다')
            rows = self.repo.rows('list_product_candidates', RUN_ID=run_id, CARD_ID=card_id)
            for candidate in self.repo.attach_normalized(run_id, rows):
                evidence = self.repo.rows('candidate_evidence', STG_ID=candidate['card_extr_stg_id'])
                results.append(self._register(card_id, candidate, evidence))
            new = self._errors() - before
            if new:
                raise ValueError('신규 정합성 위반으로 트랜잭션을 롤백합니다: ' + ', '.join(sorted({g for g, _ in new})))
        inserted = [item.card_bnft_id for item in results if item.status == 'INSERTED']
        if inserted and self.embedding_service is not None:
            self.embedding_service.embed_new('card_bnft', inserted)
        return results

    def _errors(self):
        return Counter((r['gate_cd'], r['issue_key']) for r in self.repo.rows('integrity_errors'))

    def _register(self, card_id, candidate, evidence) -> ProductDecision:
        stg_id = candidate['card_extr_stg_id']
        def review(reason, status='REVIEW'):
            return ProductDecision(card_id, stg_id, status, reason)
        raw, norm = candidate['stg_raw_item'], candidate.get('normalized')
        if norm is None:
            return review('추출 원본에서 등록 형태를 다시 만들 수 없습니다')
        code = norm.get('bnft_cd')
        existing = self.repo.one('find_benefit', CARD_ID=card_id, BNFT_CD=code)
        if existing:
            return ProductDecision(card_id, stg_id, 'UNCHANGED', '등록된 혜택은 수정하지 않습니다', code, existing['card_bnft_id'])
        if candidate['stg_status'] in ('REJECTED', 'RETIRED'):
            return review('제외된 후보입니다', 'EXCLUDED')
        # check_cd는 저장된 검증 코드를 현재 계약으로 다시 판단한 값이다(계산 구조 정리 전 CONTRACT_INVALID 재판정).
        if candidate.get('check_cd') not in ('OK', 'LINK_REVIEW'):
            return review(f"후보 검증이 필요합니다: {candidate.get('check_cd')}")
        if norm.get('is_common_candidate'):
            return review('공통서비스 후보는 카드별 혜택으로 등록하지 않습니다')
        if norm.get('relation_list'):
            return review('혜택 간 관계의 ID 연결을 확인해야 합니다')
        # 이전 추출 이력의 계산 실행용 키(method_ver·pool_refs 등)는 저장하지 않는다.
        rules = [strip_calc_rule(rule) for rule in norm.get('rule_list', [])]
        bnft_cond = strip_calc_atoms(norm.get('bnft_cond_expr'))
        if not rules or any(rule.get('rule_status_cd') != 'DRAFT' for rule in rules):
            return review('규칙이 없거나 상태가 불명확합니다')
        links, problem = self._links(raw, rules, evidence)
        if problem:
            return review(problem)
        evidence_items = raw.get('evidence', [])
        inserted = self.repo.write(
            'insert_local_benefit', CARD_ID=card_id, BNFT_CD=code, BNFT_NM=norm['bnft_nm'], BNFT_TYPE=norm['bnft_type_cd'],
            COND=Jsonb(bnft_cond) if bnft_cond is not None else None, RULES=Jsonb(rules),
            RULE_TXT=quote_text(evidence_items, 'RULE'), LIMIT_TXT=quote_text(evidence_items, 'LIMIT'))
        if not inserted:
            raise ValueError('동시 등록 충돌: 전체 트랜잭션을 롤백합니다')
        benefit_id = inserted[0]['card_bnft_id']
        for key, evidence_id in links:
            if key is None:
                self.repo.write('insert_evidence_link', CARD_ID=card_id, BNFT_ID=benefit_id, EVIDENCE_ID=evidence_id)
            else:
                self.repo.write('insert_rule_evidence_link', CARD_ID=card_id, BNFT_ID=benefit_id, RULE_KEY=key, EVIDENCE_ID=evidence_id)
        return ProductDecision(card_id, stg_id, 'INSERTED', '검토 대기', code, benefit_id)

    @staticmethod
    def _links(raw, rules, evidence):
        """원문 인용을 혜택·규칙 근거로 연결한다. 위치가 확인된 인용만 연결한다."""
        located = [e for e in evidence if e['start_pos'] is not None and e['end_pos'] is not None
                   and e.get('source_txt') is not None and compact(e['source_txt']) == compact(e['quote_txt'])]
        rule_keys = {rule['rule_key'] for rule in rules}
        links = []
        for item in raw.get('evidence', []):
            supports, key = item.get('supports'), item.get('support_key')
            if supports == 'RULE' and key not in rule_keys:
                return [], '근거의 규칙을 확인해야 합니다'
            matches = [e for e in located if compact(e['quote_txt']) == compact(item.get('quote_txt') or '')]
            if not matches:
                return [], '원문 위치가 확인되지 않은 근거가 있습니다'
            links.append((key if supports == 'RULE' else None, matches[0]['evidence_id']))
        unique = list(dict.fromkeys(links))
        if not any(key is None for key, _ in unique) or not rule_keys <= {key for key, _ in unique}:
            return [], '혜택 또는 계산 규칙을 뒷받침하는 근거가 없습니다'
        return unique, None
