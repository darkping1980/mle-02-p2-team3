"""공통 문서 등록·추출·자동 승인 판정·공통 혜택 등록 연결.

승인과 혜택 등록은 별도 단계다. LINK_REVIEW는 승인하지 않지만 기존 공통 등록
서비스가 근거를 검증하여 등록할 수 있다. DB·LLM·등록 서비스는 주입한다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import re
import unicodedata

from .auto_approval_policy import check_auto_approval
from .common_benefit_service import benefit_code, compact


@dataclass
class PipelineResult:
    status: str = "RUNNING"
    document_id: str | None = None
    run_id: str | None = None
    stages: list[dict] = field(default_factory=list)
    approvals: list[dict] = field(default_factory=list)
    benefits: list[dict] = field(default_factory=list)


def identity_for(candidate: dict, evidence: list[dict]) -> str | None:
    """원문에서 확인된 고유한 혜택명만 식별자로 쓴다. 이름만으로 유사명 병합하지 않는다."""
    raw = candidate.get('stg_raw_item') or {}
    name = unicodedata.normalize('NFKC', (candidate.get('stg_normalized_item') or {}).get('bnft_nm') or '').strip()
    if (not name or len(name) > 160 or raw.get('certainty') != 'HIGH' or raw.get('uncertainty_note')
            or not re.search(r'[가-힣A-Za-z0-9]', name)):
        return None
    if not any(item.get('start_pos') is not None and item.get('end_pos') is not None
               and item.get('source_txt') is not None and compact(item.get('source_txt') or '') == compact(item.get('quote_txt') or '')
               and compact(name) in compact(item.get('quote_txt') or '') for item in evidence):
        return None
    return 'NAME_V1_' + hashlib.sha256(compact(name).encode('utf-8')).hexdigest().upper()


class CommonAutoPipeline:
    def __init__(self, registration, extraction, common, approval):
        self.registration, self.extraction, self.common, self.approval = registration, extraction, common, approval

    def run(self, pdf, common_link=None) -> PipelineResult:
        result = PipelineResult()
        stage = 'document'
        try:
            doc = self.registration.register(pdf, apply=True, common_link=common_link)
            result.document_id = doc.card_doc_id
            result.stages.append({'stage': stage, 'status': doc.status, 'document_id': doc.card_doc_id})
            if not doc.card_doc_id or doc.document.doc_type_cd != 'BRAND_SERVICE':
                raise ValueError('공통서비스 문서 ID가 필요합니다')
            stage = 'extraction'
            extracted = self.extraction.run(doc.card_doc_id, card_id=None)
            result.run_id = extracted.card_ai_run_id
            result.stages.append({'stage': stage, 'status': extracted.status, 'reused': extracted.reused,
                                  'pages_ok': extracted.pages_ok, 'pages_failed': extracted.pages_failed, 'note': extracted.note})
            if extracted.status != 'SUCCEEDED':
                result.status = 'REVIEW'
                return result
            stage = 'approval'
            result.approvals, identities = self.approval.process(result.run_id)
            result.stages.append({'stage': stage, 'status': 'COMPLETED', 'identities': len(identities)})
            stage = 'common_benefit'
            result.benefits = [asdict(item) for item in self.common.register_run(result.run_id, identities)]
            result.stages.append({'stage': stage, 'status': 'COMPLETED'})
            result.status = 'REVIEW' if any(item['status'] in ('REVIEW', 'CHANGE_REVIEW', 'EXCLUDED') for item in result.benefits) else 'SUCCEEDED'
        except Exception as error:
            result.status = 'ERROR'
            result.stages.append({'stage': stage, 'status': 'ERROR', 'error_type': type(error).__name__, 'message': str(error)})
        return result


class PostgresCommonApproval:
    """행 잠금과 재조회 후 조건부 승인. 등록 판단은 기존 CommonBenefitService가 담당한다."""
    def __init__(self, session, common):
        self.session, self.common = session, common

    def process(self, run_id: str):
        results, identities = [], {}
        with self.session.transaction():
            conn = self.session._active_connection
            run = conn.execute("select card_ai_run_id,run_target_card_doc_id,run_status from db_pipeline.card_ai_run where card_ai_run_id=%s and run_stage_cd='EXTRACT' for update", (run_id,)).fetchone()
            if not run or run['run_status'] != 'SUCCEEDED':
                raise ValueError('완료된 추출 실행이 아닙니다')
            doc = conn.execute("select card_doc_id,doc_type_cd,doc_status from db_pipeline.card_doc where card_doc_id=%s for update", (run['run_target_card_doc_id'],)).fetchone()
            if not doc or doc['doc_type_cd'] != 'BRAND_SERVICE' or doc['doc_status'] != 'ACTIVE':
                raise ValueError('활성 공통 문서가 아닙니다')
            conn.execute('select page_no from db_pipeline.card_doc_page where card_doc_id=%s for update', (doc['card_doc_id'],)).fetchall()
            conn.execute('select card_doc_chunk_id from db_pipeline.card_doc_chunk where card_doc_id=%s for update', (doc['card_doc_id'],)).fetchall()
            conn.execute('select card_common_id from db_pipeline.card_common_doc where card_doc_id=%s for update', (doc['card_doc_id'],)).fetchall()
            candidates = conn.execute("""select s.*,d.doc_family_cd,d.doc_version_no from db_pipeline.card_extr_stg s
                join db_pipeline.card_doc d on d.card_doc_id=s.card_doc_id
                where s.card_ai_run_id=%s and s.card_doc_id=%s and s.card_id is null and s.stg_kind_cd='BENEFIT'
                and s.stg_normalized_item is not null for update of s""", (run_id, doc['card_doc_id'])).fetchall()
            before = self.common._integrity_errors()
            commons = self.common.repo.rows('common_of_doc', DOC_ID=doc['card_doc_id'])
            if len(commons) == 1:
                self.common.repo.one('lock_common', COMMON_ID=commons[0]['card_common_id'])
            names = [compact((item['stg_normalized_item'].get('bnft_nm') or '')) for item in candidates]
            for candidate in candidates:
                stg_id = candidate['card_extr_stg_id']
                conn.execute('select evidence_id from db_pipeline.card_source_evidence where card_extr_stg_id=%s for update', (stg_id,)).fetchall()
                evidence = self.common.repo.rows('candidate_evidence', STG_ID=stg_id)
                identity = identity_for(candidate, evidence)
                unique = names.count(compact(candidate['stg_normalized_item'].get('bnft_nm') or '')) == 1
                existing = []
                if len(commons) == 1 and identity:
                    code = benefit_code(candidate['doc_family_cd'], identity)
                    existing = conn.execute('select bnft_cd,bnft_nm from db_pipeline.card_common_bnft where card_common_id=%s and bnft_nm=%s for update',
                                            (commons[0]['card_common_id'], candidate['stg_normalized_item']['bnft_nm'])).fetchall()
                    unique = unique and all(row['bnft_cd'] == code for row in existing)
                if identity and unique and len(commons) == 1:
                    identities[stg_id] = identity
                located = self.common._located(evidence)
                _, proof_problem = self.common._evidence_ids(candidate['stg_raw_item'], candidate['stg_normalized_item'], located)
                parent_ok = len(commons) == 1 and not self.common._candidate_problem(candidate) and not proof_problem
                decision = check_auto_approval(candidate, evidence, parent_integrity_ok=parent_ok, duplicate_free=bool(identity and unique))
                if decision.eligible and candidate['stg_status'] == 'PENDING_REVIEW':
                    changed = conn.execute("update db_pipeline.card_extr_stg set stg_status='AUTO_APPROVED',update_date=now(),update_user_id='SYSTEM' where card_extr_stg_id=%s and stg_status='PENDING_REVIEW' returning card_extr_stg_id", (stg_id,)).fetchone()
                    if not changed:
                        raise ValueError('후보 상태가 변경되었습니다')
                results.append({'stg_id': stg_id, 'status': 'AUTO_APPROVED' if decision.eligible else 'REVIEW', 'reasons': list(decision.reasons)})
            self.common._assert_no_new_errors(before)
        return results, identities
