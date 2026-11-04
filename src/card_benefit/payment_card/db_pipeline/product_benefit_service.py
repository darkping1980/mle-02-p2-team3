"""상품설명서 추출 후보를 ``card_bnft`` 에 등록한다.

검토 전 상태인 PENDING_REVIEW로만 등록하고 승인하지 않는다. 같은 혜택 코드가 있으면 수정하지 않는다.
검색 텍스트와 임베딩은 등록을 커밋한 뒤 ``EmbeddingService.embed_new`` 가 처리하므로, 실패해도 등록은 남는다.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from .common_benefit_service import CommonBenefitRepository, compact, quote_text
from .extraction_service import locate_quote, strip_calc_atoms, strip_calc_rule
from .unresolved_review import APPROVED, BLOCK_REGISTRATION, PENDING, PENDING_SCOPE_NOTE, validate_review_sources


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

    def register_run(self, card_id: int, run_id: str, *, exclude_stg_ids: set[str] | None = None) -> list[ProductDecision]:
        """실행의 혜택 후보를 등록한다. 정합성 위반이 새로 생기면 전체를 되돌린다."""
        results = []
        with self.session.transaction():
            before = self._errors()
            if not self.repo.one('lock_card', CARD_ID=card_id):
                raise ValueError('카드가 없습니다')
            rows = self.repo.rows('list_product_candidates', RUN_ID=run_id, CARD_ID=card_id)
            for candidate in self.repo.attach_normalized(run_id, rows):
                if candidate['card_extr_stg_id'] in (exclude_stg_ids or set()):
                    results.append(ProductDecision(card_id, candidate['card_extr_stg_id'], 'EXCLUDED',
                                                   '명시적 중복 제외 대상; 원본 추출 상태는 변경하지 않음'))
                    continue
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

    def unresolved_review_queue(self, run_id: str) -> list[dict]:
        """Return saved unresolved LLM items with separate human review status."""
        return self.repo.unresolved_review_queue(run_id)

    def _register(self, card_id, candidate, evidence) -> ProductDecision:
        stg_id = candidate['card_extr_stg_id']
        def review(reason, status='REVIEW'):
            return ProductDecision(card_id, stg_id, status, reason)
        raw, norm = candidate['stg_raw_item'], candidate.get('normalized')
        if norm is None:
            return review('추출 원본에서 등록 형태를 다시 만들 수 없습니다')
        reviewed_links = candidate.get('reviewed_unresolved_links', [])
        blocking_links = [link for link in reviewed_links
                          if link.get('review_status') != APPROVED and not (
                              link.get('review_status') == PENDING
                              and link.get('registration_effect') == PENDING_SCOPE_NOTE)]
        if blocking_links:
            return review('연결된 미해결 항목의 사람 검토가 완료되지 않았습니다')
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
        try:
            approved_links = [link for link in reviewed_links if link.get('review_status') == APPROVED]
            pending_scope_links = [link for link in reviewed_links
                                   if link.get('review_status') == PENDING
                                   and link.get('registration_effect') == PENDING_SCOPE_NOTE]
            raw, evidence, limit_notes = self._materialize_reviewed_evidence(
                candidate, raw, evidence, approved_links)
            raw, evidence, pending_notes = self._materialize_pending_scope_evidence(
                candidate, raw, evidence, pending_scope_links)
        except ValueError as error:
            return review(f'검토된 원문 근거 확인 필요: {error}')
        links, problem = self._links(raw, rules, evidence)
        if problem:
            return review(problem)
        evidence_items = raw.get('evidence', [])
        limit_txt = quote_text(evidence_items, 'LIMIT')
        all_notes = list(dict.fromkeys([*limit_notes, *pending_notes]))
        if all_notes:
            limit_txt = ' / '.join(item for item in (limit_txt, ' / '.join(all_notes)) if item)
        inserted = self.repo.write(
            'insert_local_benefit', CARD_ID=card_id, BNFT_CD=code, BNFT_NM=norm['bnft_nm'], BNFT_TYPE=norm['bnft_type_cd'],
            COND=Jsonb(bnft_cond) if bnft_cond is not None else None, RULES=Jsonb(rules),
            RULE_TXT=quote_text(evidence_items, 'RULE'), LIMIT_TXT=limit_txt)
        if not inserted:
            raise ValueError('동시 등록 충돌: 전체 트랜잭션을 롤백합니다')
        benefit_id = inserted[0]['card_bnft_id']
        for key, evidence_id in links:
            if key is None:
                self.repo.write('insert_evidence_link', CARD_ID=card_id, BNFT_ID=benefit_id, EVIDENCE_ID=evidence_id)
            else:
                self.repo.write('insert_rule_evidence_link', CARD_ID=card_id, BNFT_ID=benefit_id, RULE_KEY=key, EVIDENCE_ID=evidence_id)
        return ProductDecision(card_id, stg_id, 'INSERTED', '검토 대기', code, benefit_id)

    def _materialize_reviewed_evidence(self, candidate, raw, evidence, reviewed_links):
        """Append approved, exact-position source evidence without rewriting extraction history."""
        if not reviewed_links:
            return raw, evidence, []
        document_id = candidate.get('card_doc_id')
        source_texts = {}
        sources_by_link = []
        for link in reviewed_links:
            if link.get('review_status') != APPROVED:
                raise ValueError('사람 검토 승인 상태가 아닙니다')
            sources = []
            for source in link.get('evidence', []):
                if source.get('card_doc_id') != document_id:
                    raise ValueError('원문 문서 ID가 혜택 문서와 다릅니다')
                key = (source['card_doc_id'], source['page_no'], source['card_doc_chunk_id'])
                if key not in source_texts:
                    chunk = self.repo.one('select_review_source_chunk', CARD_DOC_ID=key[0], PAGE_NO=key[1],
                                          CARD_DOC_CHUNK_ID=key[2])
                    if not chunk:
                        raise ValueError('원문 청크를 찾을 수 없습니다')
                    source_texts[key] = chunk['chunk_raw_txt']
                span = locate_quote(source_texts[key], source['quote_txt'])
                if span is None:
                    raise ValueError('검토된 인용이 원문 청크와 일치하지 않습니다')
                sources.append({**source, 'start_pos': span[0], 'end_pos': span[1]})
            validate_review_sources(link, document_id, source_texts)
            sources_by_link.append((link, sources))

        augmented_raw = dict(raw)
        augmented_raw['evidence'] = list(raw.get('evidence', []))
        augmented_evidence = list(evidence)
        notes = []
        for link, sources in sources_by_link:
            if link.get('limit_scope_note'):
                notes.append(link['limit_scope_note'])
            for source in sources:
                inserted = self.repo.write(
                    'insert_review_evidence', STG_ID=candidate['card_extr_stg_id'],
                    CARD_DOC_ID=source['card_doc_id'], PAGE_NO=source['page_no'],
                    CARD_DOC_CHUNK_ID=source['card_doc_chunk_id'], QUOTE_TXT=source['quote_txt'],
                    START_POS=source['start_pos'], END_POS=source['end_pos'])
                if not inserted or not inserted[0].get('evidence_id'):
                    raise ValueError('검토 근거 저장에 실패했습니다')
                evidence_id = inserted[0]['evidence_id']
                augmented_raw['evidence'].append({
                    'supports': 'LIMIT', 'support_key': None, 'link_basis': 'TABLE_IMAGE',
                    'quote_txt': source['quote_txt'],
                })
                augmented_evidence.append({
                    'evidence_id': evidence_id, 'quote_txt': source['quote_txt'],
                    'start_pos': source['start_pos'], 'end_pos': source['end_pos'],
                    'approval_status_cd': 'PENDING', 'card_doc_id': source['card_doc_id'],
                    'page_no': source['page_no'], 'card_doc_chunk_id': source['card_doc_chunk_id'],
                    'source_txt': source['quote_txt'],
                })
        return augmented_raw, augmented_evidence, notes

    def _materialize_pending_scope_evidence(self, candidate, raw, evidence, pending_links):
        """Preserve unresolved applicability as pending evidence without claiming it applies."""
        if not pending_links:
            return raw, evidence, []
        document_id = candidate.get('card_doc_id')
        source_texts = {}
        additions = []
        notes = []
        for link in pending_links:
            if link.get('review_status') != PENDING or link.get('registration_effect') != PENDING_SCOPE_NOTE:
                raise ValueError('non-blocking scope note is not a pending review')
            if not link.get('unresolved_scope_note'):
                raise ValueError('pending scope note text is required')
            notes.append(link['unresolved_scope_note'])
            for source in link.get('evidence', []):
                if source.get('card_doc_id') != document_id:
                    raise ValueError('pending scope evidence document does not match benefit document')
                key = (source['card_doc_id'], source['page_no'], source['card_doc_chunk_id'])
                if key not in source_texts:
                    chunk = self.repo.one('select_review_source_chunk', CARD_DOC_ID=key[0], PAGE_NO=key[1],
                                          CARD_DOC_CHUNK_ID=key[2])
                    if not chunk:
                        raise ValueError('pending scope source chunk was not found')
                    source_texts[key] = chunk['chunk_raw_txt']
                span = locate_quote(source_texts[key], source['quote_txt'])
                if span is None:
                    raise ValueError('pending scope quote does not match the source chunk')
                additions.append({**source, 'start_pos': span[0], 'end_pos': span[1]})

        augmented_raw = dict(raw)
        augmented_raw['evidence'] = list(raw.get('evidence', []))
        augmented_evidence = list(evidence)
        for source in additions:
            inserted = self.repo.write(
                'insert_review_evidence', STG_ID=candidate['card_extr_stg_id'],
                CARD_DOC_ID=source['card_doc_id'], PAGE_NO=source['page_no'],
                CARD_DOC_CHUNK_ID=source['card_doc_chunk_id'], QUOTE_TXT=source['quote_txt'],
                START_POS=source['start_pos'], END_POS=source['end_pos'])
            if not inserted or not inserted[0].get('evidence_id'):
                raise ValueError('pending scope evidence could not be saved')
            evidence_id = inserted[0]['evidence_id']
            augmented_raw['evidence'].append({
                'supports': 'UNRESOLVED_SCOPE', 'support_key': None,
                'link_basis': 'PENDING_SCOPE_REVIEW', 'quote_txt': source['quote_txt'],
            })
            augmented_evidence.append({
                'evidence_id': evidence_id, 'quote_txt': source['quote_txt'],
                'start_pos': source['start_pos'], 'end_pos': source['end_pos'],
                'approval_status_cd': PENDING, 'card_doc_id': source['card_doc_id'],
                'page_no': source['page_no'], 'card_doc_chunk_id': source['card_doc_chunk_id'],
                'source_txt': source['quote_txt'],
            })
        return augmented_raw, augmented_evidence, list(dict.fromkeys(notes))

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
