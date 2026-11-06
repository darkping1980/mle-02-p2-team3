"""상품설명서 추출 후보를 카드 혜택으로 등록한다.

저장 테이블은 ``card_product_item`` (item_type_cd='BENEFIT')이다. 2026-11-04 전환 이전 이름이 ``card_bnft`` 라서
코드·결과 필드에는 ``card_bnft_id`` / ``bnft_cd`` 이름이 남아 있다(SQL에서 card_product_item_id·item_cd를 별칭으로 돌려준다).

검토 전 상태인 PENDING_REVIEW로만 등록하고 승인하지 않는다. 같은 혜택 코드가 있으면 수정하지 않는다.
검색 텍스트와 임베딩은 등록을 커밋한 뒤 ``EmbeddingService.embed_new`` 가 처리하므로, 실패해도 등록은 남는다.

[등록 파이프라인에서의 위치] 3단계(상품설명서). 입력은 2단계가 남긴 card_extr_stg 대표 행이다.

처리 흐름 (``register_run``, 전체가 1트랜잭션)
    1. 정합성 위반 기준선(v_card_integrity_issue) 조회 → card_product 행 잠금(SELECT ... FOR UPDATE)
    2. list_product_candidates: 해당 실행·카드의 대표 혜택 후보(상위 행 없음, 검증 코드 있음)
    3. attach_normalized: 추출 원본에서 등록 형태(normalized)를 다시 만들고 사람 검토 기록(unresolved_links.json)을 붙임
    4. 후보마다 ``_register``: 판정 → (통과 시) 검토 근거 추가 → card_product_item INSERT → card_evidence_link INSERT
    5. 정합성 위반이 새로 생겼으면 ValueError → 전체 rollback, 아니면 commit
    6. (커밋 후) 새로 INSERT한 항목만 임베딩

중복 등록 방지: find_benefit로 (card_id, item_cd) 존재 확인 → 있으면 UNCHANGED.
               INSERT도 ``ON CONFLICT (card_id,item_cd) DO NOTHING`` 이라 동시 실행 시 빈 결과 → 예외로 rollback.
식별자: item_cd(bnft_cd)는 extraction_service.make_item_key("BNFT", 혜택명)가 만든 해시 코드,
       card_product_item_id(PK)는 DB가 발급한다.

관련 테이블: card_product, card_extr_stg, card_source_evidence, card_doc_chunk, card_product_item, card_evidence_link
SQL: common_benefit_repository.sql (CommonBenefitRepository 경유)
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from psycopg.types.json import Jsonb

from .common_benefit_service import CommonBenefitRepository, compact, quote_text
from .extraction_service import (check_limit_struct, limit_struct, limit_tiers_from_extraction, locate_quote,
                                 strip_calc_atoms, strip_calc_rule)
from .unresolved_review import APPROVED, BLOCK_REGISTRATION, PENDING, PENDING_SCOPE_NOTE, validate_review_sources
from .benefit_review_patch import (apply_patch, extracted_shared_members, limit_tiers_text, provenance,
                                   restrict_rule_targets, shared_limit_problems, usable)
from .extraction_schema import BenefitItem
from .extraction_service import PageResult, check_benefit, normalize_stored_run, sql_check_code


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
    """상품설명서 추출 후보 → 카드 혜택(card_product_item BENEFIT) 등록 서비스. 호출: benefit_main product."""

    def __init__(self, session, embedding_service=None, patches: list[dict] | None = None, allow_draft_patches: bool = False):
        """patches: benefit_review_patch.load_patches 결과. 기본은 APPROVED 보정만 적용한다.
        allow_draft_patches는 사람 검토 전 보정을 ROLLBACK 시험에서 확인할 때만 쓴다(호출자가 커밋하지 않아야 함)."""
        self.session = session
        self.repo = CommonBenefitRepository(session)
        self.embedding_service = embedding_service
        self.patches = list(patches or [])
        self.allow_draft_patches = allow_draft_patches

    def _register_isolated(self, card_id, candidate, baseline):
        """① 후보 1건을 저장점(SAVEPOINT) 안에서 등록한다. 이 후보 때문에 정합성 위반이 새로 생기면 이 후보만 되돌리고
        REVIEW로 남긴다(다른 후보의 등록은 유지). 실제 DB 연결이 없는 세션(테스트용)에서는 저장점 없이 등록한다.

        Returns:
            (판정, 다음 후보의 정합성 기준선)
        """
        conn = getattr(self.session, '_active_connection', None)
        evidence = self.repo.rows('candidate_evidence', STG_ID=candidate['card_extr_stg_id'])
        if conn is None:
            return self._register(card_id, candidate, evidence), baseline
        conn.execute('SAVEPOINT product_candidate')
        try:
            decision = self._register(card_id, candidate, evidence)
        except Exception:
            conn.execute('ROLLBACK TO SAVEPOINT product_candidate')
            raise
        if decision.status == 'INSERTED':
            now = self._errors()
            new = now - baseline
            if new:
                conn.execute('ROLLBACK TO SAVEPOINT product_candidate')
                conn.execute('RELEASE SAVEPOINT product_candidate')
                return ProductDecision(card_id, candidate['card_extr_stg_id'], 'REVIEW',
                                       '정합성 검사 위반으로 이 후보만 되돌렸습니다: ' + ', '.join(sorted({g for g, _ in new}))), baseline
            baseline = now
        conn.execute('RELEASE SAVEPOINT product_candidate')
        return decision, baseline

    def _apply_patches(self, run_id, candidates, patches):
        """② 보정 대상 후보의 추출 원본에 보정을 적용하고, 추출 단계와 같은 함수로 등록 형태와 검증 코드를 다시 만든다.

        보정 대상이 아닌 후보는 그대로 둔다. 보정한 후보에는 review_patch·patch_quotes를 붙인다.
        """
        run_rows = self.repo.rows('list_run_items', RUN_ID=run_id)
        by_id = {row['card_extr_stg_id']: row for row in run_rows}
        patched_quotes, patched_extras = {}, {}
        for stg_id, patch in patches.items():
            if stg_id not in by_id:
                raise ValueError(f"보정 {patch['patch_id']}의 후보가 이 실행에 없습니다: {stg_id}")
            raw, quotes, extras = apply_patch(by_id[stg_id]['stg_raw_item'], patch)
            by_id[stg_id] = {**by_id[stg_id], 'stg_raw_item': raw}
            patched_quotes[stg_id], patched_extras[stg_id] = quotes, extras
        stored = normalize_stored_run(list(by_id.values()))
        out = []
        for candidate in candidates:
            stg_id = candidate['card_extr_stg_id']
            if stg_id not in patches:
                out.append(candidate)
                continue
            item = stored.get(stg_id)
            if item is None:
                raise ValueError(f'보정한 후보를 다시 만들 수 없습니다: {stg_id}')
            raw = by_id[stg_id]['stg_raw_item']
            chunk = self.repo.one('select_review_source_chunk', CARD_DOC_ID=candidate['card_doc_id'],
                                  PAGE_NO=by_id[stg_id]['page_no'], CARD_DOC_CHUNK_ID=candidate.get('card_doc_chunk_id')
                                  or self._chunk_of(stg_id))
            page = PageResult(page_no=by_id[stg_id]['page_no'], chunk_id=chunk['card_doc_chunk_id'],
                              text=chunk['chunk_raw_txt'], extraction=None)
            check = check_benefit(BenefitItem.model_validate(raw), page)
            code = sql_check_code(check, item.conflicts, item.unresolved, item.invalid)
            extras = patched_extras[stg_id]
            normalized = item.normalized
            if normalized is not None and extras['rule_targets']:
                # 정규화는 혜택 대상을 모든 규칙에 넣는다. 보정이 정한 규칙별 대상만 남긴다.
                normalized = {**normalized, 'rule_list': restrict_rule_targets(normalized['rule_list'], extras['rule_targets'])}
            out.append({**candidate, 'stg_raw_item': raw, 'normalized': normalized, 'check_cd': code,
                        'source_cnt': item.source_cnt, 'conflicts': item.conflicts,
                        'review_patch': provenance(patches[stg_id]), 'patch_quotes': patched_quotes[stg_id],
                        'limit_tiers': extras['limit_tiers'], 'patch_check_issues': check.issues})
        return out

    def _chunk_of(self, stg_id):
        row = self.repo.one('select_stg_chunk', STG_ID=stg_id)
        if not row:
            raise ValueError(f'후보의 청크를 찾을 수 없습니다: {stg_id}')
        return row['card_doc_chunk_id']

    def _materialize_patch_evidence(self, candidate, evidence):
        """보정으로 추가한 인용을 후보 청크 원문에서 찾아 card_source_evidence(PENDING)로 저장한다. 위치를 못 찾으면 실패."""
        quotes = candidate.get('patch_quotes') or []
        if not quotes:
            return evidence
        chunk_id = self._chunk_of(candidate['card_extr_stg_id'])
        page_no = self.repo.one('select_stg_chunk', STG_ID=candidate['card_extr_stg_id'])['page_no']
        chunk = self.repo.one('select_review_source_chunk', CARD_DOC_ID=candidate['card_doc_id'], PAGE_NO=page_no,
                              CARD_DOC_CHUNK_ID=chunk_id)
        augmented = list(evidence)
        for text in quotes:
            if any(compact(e['quote_txt']) == compact(text) and e.get('start_pos') is not None for e in augmented):
                continue
            span = locate_quote(chunk['chunk_raw_txt'], text)
            if span is None:
                raise ValueError('보정 인용을 원문에서 찾지 못했습니다')
            inserted = self.repo.write('insert_review_evidence', STG_ID=candidate['card_extr_stg_id'],
                                       CARD_DOC_ID=candidate['card_doc_id'], PAGE_NO=page_no, CARD_DOC_CHUNK_ID=chunk_id,
                                       QUOTE_TXT=text, START_POS=span[0], END_POS=span[1])
            if not inserted or not inserted[0].get('evidence_id'):
                raise ValueError('보정 근거 저장에 실패했습니다')
            augmented.append({'evidence_id': inserted[0]['evidence_id'], 'quote_txt': text, 'start_pos': span[0],
                              'end_pos': span[1], 'approval_status_cd': PENDING, 'card_doc_id': candidate['card_doc_id'],
                              'page_no': page_no, 'card_doc_chunk_id': chunk_id,
                              'source_txt': chunk['chunk_raw_txt'][span[0] - 1:span[1]]})
        return augmented

    def _resolve_relations(self, card_id, relation_list):
        """③ 관계 대상(추출 키 BNFT_…)을 같은 카드에 이미 등록된 혜택 ID로 바꾼다. 하나라도 없으면 (None, 사유)."""
        resolved = []
        for relation in relation_list:
            target = self.repo.one('find_benefit', CARD_ID=card_id, BNFT_CD=relation['to_bnft_id'])
            if not target or target.get('item_type_cd') != 'BENEFIT':
                return None, f"관계 대상 혜택이 이 카드에 아직 등록되지 않았습니다: {relation['to_bnft_id']}"
            resolved.append({'relation_key': relation['relation_key'], 'to_bnft_id': target['card_bnft_id'],
                             'rel_type_cd': relation['rel_type_cd'], 'rel_priority': relation.get('rel_priority')})
        return resolved, None

    def register_run(self, card_id: int, run_id: str, *, exclude_stg_ids: set[str] | None = None) -> list[ProductDecision]:
        """실행의 혜택 후보를 등록한다. 정합성 위반이 새로 생기면 전체를 되돌린다.

        Args:
            card_id: 등록 대상 card_product.card_id.
            run_id: 2단계 추출 실행 card_ai_run_id.
            exclude_stg_ids: 명시적으로 제외할 card_extr_stg_id. 원본 추출 행은 바꾸지 않는다.

        Returns:
            후보별 ProductDecision(INSERTED / UNCHANGED / REVIEW / EXCLUDED).

        Raises:
            ValueError: 카드가 없거나, 신규 정합성 위반, 동시 등록 충돌. 모두 트랜잭션 전체 rollback.
        """
        results = []
        # 트랜잭션 시작: 이 블록 안의 모든 INSERT(혜택·근거·근거 연결)가 한 번에 commit 또는 rollback된다.
        with self.session.transaction():
            # 등록 전 정합성 위반 목록을 기준선으로 저장한다. 끝에서 새로 생긴 위반만 비교한다.
            before = self._errors()
            # 카드 행 잠금(FOR UPDATE): 같은 카드에 대한 동시 등록을 직렬화한다.
            if not self.repo.one('lock_card', CARD_ID=card_id):
                raise ValueError('카드가 없습니다')
            rows = self.repo.rows('list_product_candidates', RUN_ID=run_id, CARD_ID=card_id)
            candidates = self.repo.attach_normalized(run_id, rows)
            # ② 사람 검토 보정(예외 수단): 보정한 후보는 추출 검증을 다시 통과해야 한다. 원본 추출 행은 바꾸지 않는다.
            patches = usable(self.patches, run_id, self.allow_draft_patches)
            if patches:
                candidates = self._apply_patches(run_id, candidates, patches)
            # 공유 한도 누락·불일치 검출: 추출이 밝힌 공유 한도와 보정한 한도 구간을 같은 실행의 혜택끼리 대조한다.
            candidates = self._mark_shared_limit_problems(candidates)
            # ③ 관계가 없는 후보를 먼저 등록한다. 같은 실행 안의 관계 대상 혜택이 먼저 생기게 한다(그 밖의 순서 유지).
            candidates = sorted(candidates, key=lambda c: bool((c.get('normalized') or {}).get('relation_list')))
            baseline = before
            for candidate in candidates:
                if candidate['card_extr_stg_id'] in (exclude_stg_ids or set()):
                    results.append(ProductDecision(card_id, candidate['card_extr_stg_id'], 'EXCLUDED',
                                                   '명시적 중복 제외 대상; 원본 추출 상태는 변경하지 않음'))
                    continue
                decision, baseline = self._register_isolated(card_id, candidate, baseline)
                results.append(decision)
            new = self._errors() - before
            if new:
                raise ValueError('신규 정합성 위반으로 트랜잭션을 롤백합니다: ' + ', '.join(sorted({g for g, _ in new})))
        # 트랜잭션 종료(commit) 후: 새로 등록한 항목만 임베딩한다. 여기서 실패해도 등록은 이미 커밋되어 있다.
        inserted = [item.card_bnft_id for item in results if item.status == 'INSERTED']
        if inserted and self.embedding_service is not None:
            self.embedding_service.embed_new('card_bnft', inserted)
        return results

    @staticmethod
    def _mark_shared_limit_problems(candidates):
        """공유 한도 문제가 있는 후보에 shared_limit_problem 사유를 붙인다(등록 단계에서 REVIEW로 남김)."""
        declared, required = {}, []
        for candidate in candidates:
            name = (candidate.get('normalized') or {}).get('bnft_nm') or (candidate.get('stg_raw_item') or {}).get('bnft_nm')
            if not name:
                continue
            declared[name] = candidate.get('limit_tiers')
            required += [m for m in extracted_shared_members(candidate.get('stg_raw_item') or {}) if m not in required]
        problems = shared_limit_problems(declared, required)
        if not problems:
            return candidates
        return [{**c, 'shared_limit_problem': problems.get((c.get('normalized') or {}).get('bnft_nm')
                                                            or (c.get('stg_raw_item') or {}).get('bnft_nm'))}
                for c in candidates]

    def _errors(self):
        """v_card_integrity_issue의 현재 위반을 (gate_cd, issue_key) 개수로 센다. 등록 전후 차이 비교용."""
        return Counter((r['gate_cd'], r['issue_key']) for r in self.repo.rows('integrity_errors'))

    def unresolved_review_queue(self, run_id: str) -> list[dict]:
        """Return saved unresolved LLM items with separate human review status."""
        return self.repo.unresolved_review_queue(run_id)

    def _register(self, card_id, candidate, evidence) -> ProductDecision:
        """후보 1건을 판정하고, 모든 조건을 통과하면 등록한다. 호출자(register_run)의 트랜잭션 안에서 실행된다.

        판정 순서(앞에서 걸리면 INSERT 없이 판정만 반환):
            등록 형태 재생성 실패 → 미완료 사람 검토 → 이미 등록(UNCHANGED) → 제외 상태(EXCLUDED)
            → 검증 코드가 OK·LINK_REVIEW 아님 → 공통서비스 후보 → 혜택 간 관계 있음 → 규칙 없음/DRAFT 아님
            → 검토 근거 추가 실패 → 근거 연결(_links) 실패
        통과 시 DB 변경:
            (검토 근거가 있으면) card_source_evidence INSERT → card_product_item INSERT(PENDING_REVIEW)
            → card_evidence_link INSERT(혜택 근거 ev_subject_cd='BNFT', 규칙 근거 'RULE')

        Args:
            evidence: candidate_evidence SQL 결과. 근거 위치로 잘라낸 원문(source_txt)을 포함한다.
        """
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
        # 중복 등록 방지: 같은 카드에 같은 item_cd가 있으면 기존 행을 수정하지 않는다.
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
        if candidate.get('shared_limit_problem'):
            return review(candidate['shared_limit_problem'])
        # ③ 혜택 간 관계: 대상이 같은 카드에 이미 등록된 혜택일 때만 등록한다(대상 키 → card_product_item_id).
        relations = []
        if norm.get('relation_list'):
            relations, problem = self._resolve_relations(card_id, norm['relation_list'])
            if problem:
                return review(problem)
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
            # ② 보정으로 추가한 인용도 원문 위치를 확인해 근거로 저장한다.
            evidence = self._materialize_patch_evidence(candidate, evidence)
        except ValueError as error:
            return review(f'검토된 원문 근거 확인 필요: {error}')
        links, problem = self._links(raw, rules, evidence, {rel['relation_key'] for rel in relations})
        if problem:
            return review(problem)
        evidence_items = raw.get('evidence', [])
        limit_txt = quote_text(evidence_items, 'LIMIT')
        all_notes = list(dict.fromkeys([*limit_notes, *pending_notes]))
        if all_notes:
            limit_txt = ' / '.join(item for item in (limit_txt, ' / '.join(all_notes)) if item)
        data = {}
        if candidate.get('review_patch'):
            data = {'schema_ver': 'BENEFIT_V1', 'review_patch': candidate['review_patch']}
        # 추출 한도 구조 보존(2026-11-06): limits·규칙별 limit_keys를 해석 없이 item_data에 둔다. item_limit_txt는 그대로다.
        located = self._located(evidence)
        rule_keys = [rule['rule_key'] for rule in rules]
        struct = limit_struct(raw, rule_keys, self._limit_evidence(raw, located))
        if struct:
            issues = check_limit_struct(raw, rule_keys, struct)
            if issues:
                return review(f"추출 한도 구조를 보존하지 못했습니다: {issues[0]}")
            data = {**data, 'schema_ver': 'BENEFIT_V1', **struct}
            # 구간별 한도가 명확할 때만 구간 표를 만든다. 사람 보정(SET_LIMIT_TIERS)이 있으면 그것을 쓴다.
            derived = None if candidate.get('limit_tiers') else limit_tiers_from_extraction(
                rules, struct, self._cond_evidence(raw, rules, located))
            if derived:
                data['limit_tiers'] = derived
        if candidate.get('limit_tiers'):
            # 한도 구간(공유 한도 포함)은 item_data에 구조로, item_limit_txt에 원문 표기로 남긴다.
            data = {**data, 'schema_ver': 'BENEFIT_V1', 'limit_tiers': candidate['limit_tiers']}
            limit_txt = limit_tiers_text(candidate['limit_tiers'])
        # card_product_item INSERT. 조건식·규칙은 JSONB, 혜택 내용·한도는 원문 인용을 이어 붙인 TEXT다.
        inserted = self.repo.write(
            'insert_local_benefit', CARD_ID=card_id, BNFT_CD=code, BNFT_NM=norm['bnft_nm'], BNFT_TYPE=norm['bnft_type_cd'],
            COND=Jsonb(bnft_cond) if bnft_cond is not None else None, RULES=Jsonb(rules), RELS=Jsonb(relations),
            DATA=Jsonb(data),
            RULE_TXT=quote_text(evidence_items, 'RULE'), LIMIT_TXT=limit_txt)
        # ON CONFLICT DO NOTHING으로 빈 결과면 위 find_benefit 이후 다른 실행이 먼저 넣은 것이다.
        if not inserted:
            raise ValueError('동시 등록 충돌: 전체 트랜잭션을 롤백합니다')
        # DB가 발급한 card_product_item_id(SQL 별칭 card_bnft_id)를 근거 연결의 FK 값으로 쓴다.
        benefit_id = inserted[0]['card_bnft_id']
        # key=None이면 혜택 전체 근거(BNFT), 값이 있으면 그 rule_key의 규칙 근거(RULE)다.
        for key, evidence_id in links:
            if key is None:
                self.repo.write('insert_evidence_link', CARD_ID=card_id, BNFT_ID=benefit_id, EVIDENCE_ID=evidence_id)
            elif isinstance(key, tuple) and key[0] == 'COND':   # ('COND', rule_key, atom_key): 규칙 조건(구간 표기 등)의 근거
                self.repo.write('insert_rule_cond_evidence_link', CARD_ID=card_id, BNFT_ID=benefit_id, RULE_KEY=key[1],
                                ATOM_KEY=key[2], EVIDENCE_ID=evidence_id)
            elif isinstance(key, tuple):   # ('REL', relation_key): 혜택 간 관계의 근거
                self.repo.write('insert_rel_evidence_link', CARD_ID=card_id, BNFT_ID=benefit_id, RELATION_KEY=key[1],
                                EVIDENCE_ID=evidence_id)
            else:
                self.repo.write('insert_rule_evidence_link', CARD_ID=card_id, BNFT_ID=benefit_id, RULE_KEY=key, EVIDENCE_ID=evidence_id)
        return ProductDecision(card_id, stg_id, 'INSERTED', '검토 대기', code, benefit_id)

    def _materialize_reviewed_evidence(self, candidate, raw, evidence, reviewed_links):
        """Append approved, exact-position source evidence without rewriting extraction history.

        사람 검토에서 APPROVED된 미해결 연결(unresolved_links.json)의 인용을 원문 청크에서 다시 찾아
        card_source_evidence에 PENDING으로 INSERT하고, 메모리의 raw·evidence 목록에 LIMIT 근거로 추가한다.
        card_extr_stg 원본 행은 바꾸지 않는다. 인용 위치를 못 찾으면 ValueError(호출자가 REVIEW로 바꾼다).

        Returns:
            (근거가 추가된 raw, 추가된 evidence 목록, 한도 범위 메모 목록)
        """
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
        """Preserve unresolved applicability as pending evidence without claiming it applies.

        registration_effect=PENDING_SCOPE_NOTE인 검토 대기 항목은 등록을 막지 않는 대신, 인용을
        card_source_evidence(PENDING)로 저장하고 supports='UNRESOLVED_SCOPE'로 표시해 한도 TEXT에 메모만 남긴다.

        Returns:
            (근거가 추가된 raw, 추가된 evidence 목록, 미해결 범위 메모 목록)
        """
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
    def _links(raw, rules, evidence, relation_keys=frozenset()):
        """원문 인용을 혜택·규칙 근거로 연결한다. 위치가 확인된 인용만 연결한다.

        LLM 원본(raw['evidence'])의 인용마다 DB 근거(evidence) 중 위치가 있고 원문과 글자가 같은 행을 찾는다.

        Returns:
            ``([(rule_key 또는 None, evidence_id), ...], None)`` 또는 실패 시 ``([], 검토 사유)``.
            혜택 근거(None)가 1건 이상이고 모든 rule_key에 근거가 있어야 성공이다.
            relation_keys에 있는 관계의 근거(supports='REL')는 ('REL', relation_key) 키로 돌려준다(③, 2026-11-05).
            저장하지 않는 관계의 REL 인용은 예전처럼 혜택 근거로 연결한다.
        """
        located = ProductBenefitService._located(evidence)
        rule_keys = {rule['rule_key'] for rule in rules}
        links = []
        for item in raw.get('evidence', []):
            supports, key = item.get('supports'), item.get('support_key')
            if supports == 'RULE' and key not in rule_keys:
                return [], '근거의 규칙을 확인해야 합니다'
            matches = [e for e in located if compact(e['quote_txt']) == compact(item.get('quote_txt') or '')]
            if not matches:
                return [], '원문 위치가 확인되지 않은 근거가 있습니다'
            if supports == 'RULE':
                link_key = key
            elif supports == 'REL' and key in relation_keys:
                link_key = ('REL', key)
            else:
                link_key = None
            links.append((link_key, matches[0]['evidence_id']))
        unique = list(dict.fromkeys(links))
        if not any(key is None for key, _ in unique) or not rule_keys <= {key for key, _ in unique}:
            return [], '혜택 또는 계산 규칙을 뒷받침하는 근거가 없습니다'
        # 규칙 조건 안의 인용(예: '80만원 이상⏎15,000원' 구간 표기)을 기존 RULE/COND 형식으로 연결한다(2026-11-06).
        # 위치를 못 찾은 조건 인용은 건너뛴다. 위 성공 판정(혜택·규칙 근거)은 바꾸지 않는다.
        for (rule_key, atom_key), evidence_ids in ProductBenefitService._cond_evidence(raw, rules, located).items():
            unique.append((('COND', rule_key, atom_key), evidence_ids[0]))
        return list(dict.fromkeys(unique)), None

    @staticmethod
    def _located(evidence):
        """원문 위치가 확인되고 잘라낸 원문이 인용과 같은 근거 행."""
        return [e for e in evidence if e.get('start_pos') is not None and e.get('end_pos') is not None
                and e.get('source_txt') is not None and compact(e['source_txt']) == compact(e['quote_txt'])]

    @staticmethod
    def _match(located, quote):
        """인용 문자열과 같은 위치 확인 근거의 evidence_id 목록(근거 행 순서)."""
        return [e['evidence_id'] for e in located if compact(e['quote_txt']) == compact(quote or '')]

    @staticmethod
    def _limit_evidence(raw, located) -> dict[str, list[str]]:
        """limit_key → 위치가 확인된 LIMIT 근거 evidence_id 목록(인용마다 첫 일치 행)."""
        out: dict[str, list[str]] = {}
        for item in raw.get('evidence', []):
            if item.get('supports') == 'LIMIT' and item.get('support_key'):
                ids = ProductBenefitService._match(located, item.get('quote_txt'))
                if ids:
                    out.setdefault(item['support_key'], [])
                    if ids[0] not in out[item['support_key']]:
                        out[item['support_key']].append(ids[0])
        return out

    @staticmethod
    def _cond_evidence(raw, rules, located) -> dict[tuple, list[str]]:
        """(rule_key, atom_key) → 위치가 확인된 규칙 조건 근거 evidence_id 목록.

        등록할 규칙의 조건식에 실제로 있는 atom_key(=추출 cond_key)만 대상으로 한다.
        """
        atoms = {(rule['rule_key'], atom.get('atom_key')) for rule in rules
                 for branch in (rule.get('cond_expr') or {}).get('branches', []) for atom in branch.get('atoms', [])}
        out: dict[tuple, list[str]] = {}
        for rule in raw.get('rules', []):
            for condition in rule.get('conditions') or []:
                key = (rule.get('rule_key'), condition.get('cond_key'))
                if key not in atoms:
                    continue
                for item in condition.get('evidence') or []:
                    ids = ProductBenefitService._match(located, item.get('quote_txt'))
                    if ids and ids[0] not in out.get(key, []):
                        out.setdefault(key, []).append(ids[0])
        return out
