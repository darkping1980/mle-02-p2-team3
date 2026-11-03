from types import SimpleNamespace
from contextlib import contextmanager

from payment_card.db_pipeline.auto_approval_policy import check_auto_approval
from payment_card.db_pipeline.common_auto_pipeline import CommonAutoPipeline, PostgresCommonApproval, identity_for
from payment_card.db_pipeline.extraction_service import PageResult, StoredItem, check_benefit, merge_pages
from payment_card.db_pipeline.extraction_schema import PageExtraction
from payment_card.tests.test_common_benefit import fixture
from payment_card.tests.test_extraction import FakeLlm


def make_pipeline(link_review):
    source = '카페 10% 할인'
    payload = {'page_no': 1, 'page_role': 'DETAIL', 'benefits': [{
        'item_key': 'K', 'bnft_nm': '카페', 'bnft_type_cd': 'DISCOUNT', 'certainty': 'HIGH',
        'rules': [{'rule_key': 'R', 'calc_method_cd': 'PERCENT_OF_TXN', 'value_num': 10,
                   'value_raw_txt': '10%', 'value_unit_cd': 'PERCENT', 'payout_unit_cd': 'KRW'}],
        'evidence': [{'quote_txt': '카페', 'supports': 'BNFT', 'support_key': None, 'link_basis': 'SAME_TEXT'},
                     {'quote_txt': source, 'supports': 'RULE', 'support_key': 'R', 'link_basis': 'SAME_TEXT'}]}]}
    llm = FakeLlm({1: payload})
    item = PageExtraction.model_validate_json(llm.extract(SimpleNamespace(page_no=1)).raw_text).benefits[0]
    page = PageResult(1, 'C1', source, PageExtraction.model_validate(payload))
    page.benefits.append(StoredItem('S1', 1, item, check_benefit(item, page)))
    merged = merge_pages([page])[0][0]
    service = fixture()
    raw = item.model_dump(mode='json')
    norm = merged.normalized
    candidate = service.repo.candidate
    code = 'LINK_REVIEW' if link_review else merged.sql_check_cd
    candidate.update(stg_raw_item=raw, normalized=norm, check_cd=code, source_cnt=1, conflicts=[], stg_kind_cd='BENEFIT',
                     stg_status='PENDING_REVIEW', stg_sql_check_cd=code)
    service.repo.evidence = [dict(evidence_id='E1', quote_txt='카페', source_txt='카페', start_pos=1, end_pos=2, approval_status_cd='PENDING'),
                             dict(evidence_id='E2', quote_txt=source, source_txt=source, start_pos=1, end_pos=len(source), approval_status_cd='PENDING')]

    class Registration:
        def register(self, *args, **kwargs):
            return SimpleNamespace(status='ALREADY_REGISTERED', card_doc_id='D1', document=SimpleNamespace(doc_type_cd='BRAND_SERVICE'))

    class Extraction:
        calls = 0
        def run(self, *args, **kwargs):
            self.calls += 1
            return SimpleNamespace(card_ai_run_id='R1', status='SUCCEEDED', reused=self.calls > 1,
                                   pages_ok=1, pages_failed=0, note=None)

    class Result:
        def __init__(self, rows): self.rows = rows
        def fetchone(self): return self.rows[0] if self.rows else None
        def fetchall(self): return self.rows

    class Connection:
        def execute(self, sql, params):
            if 'from db_pipeline.card_ai_run' in sql:
                return Result([{'run_target_card_doc_id': 'D1', 'run_status': 'SUCCEEDED'}])
            if 'select card_doc_id,doc_type_cd' in sql:
                return Result([{'card_doc_id': 'D1', 'doc_type_cd': 'BRAND_SERVICE', 'doc_status': 'ACTIVE'}])
            if 'select s.*,d.doc_family_cd' in sql:
                return Result([candidate])
            if 'select bnft_cd,bnft_nm' in sql:
                return Result([{'bnft_cd': code, 'bnft_nm': row['bnft_nm']} for (_, code), row in service.repo.common_bnft.items()
                               if row['bnft_nm'] == params[1]])
            if sql.startswith('update db_pipeline.card_extr_stg'):
                candidate['stg_status'] = 'AUTO_APPROVED'
                return Result([{'card_extr_stg_id': 'S1'}])
            return Result([])

    class Session:
        @contextmanager
        def transaction(self):
            self._active_connection = Connection()
            yield self
            self._active_connection = None

    approval = PostgresCommonApproval(Session(), service)
    return CommonAutoPipeline(Registration(), Extraction(), service, approval), llm, merged


def test_mock_llm_approval_and_common_registration_are_distinct_and_idempotent():
    pipeline, llm, merged = make_pipeline(False)
    assert merged.sql_check_cd == 'OK'
    first = pipeline.run('common/example.pdf')
    second = pipeline.run('common/example.pdf')
    assert first.approvals[0]['status'] == 'AUTO_APPROVED'
    assert first.benefits[0]['status'] == 'INSERTED'
    assert second.benefits[0]['status'] == 'UNCHANGED'
    assert second.stages[1]['reused'] is True
    assert len(llm.inputs) == 1


def test_link_review_is_not_approved_but_existing_registration_can_accept_it():
    pipeline, _, _ = make_pipeline(True)
    result = pipeline.run('common/example.pdf')
    assert result.approvals[0]['status'] == 'REVIEW'
    assert result.benefits[0]['status'] == 'INSERTED'
    assert pipeline.common.repo.candidate['stg_status'] == 'PENDING_REVIEW'
