"""읽기 전용: 저장된 LLM 응답(card_ai_call)을 새 코드로 다시 검증·통합하고 등록 판정을 계산한다. API·DB 쓰기 없음."""
import sys, collections
sys.path[:0] = ['src', 'src/card_benefit']; sys.stdout.reconfigure(encoding='utf-8')
from common.query_log_config import load_project_environment; load_project_environment()
from common.postgres_db_session import PostgresDbSession
from psycopg.rows import dict_row
from payment_card.db_pipeline.document_repository import MAPPER_ROOT
from payment_card.db_pipeline.extraction_schema import PageExtraction
from payment_card.db_pipeline.extraction_service import PageResult, StoredItem, check_benefit, check_condition, merge_pages
from payment_card.db_pipeline.common_benefit_service import CommonBenefitService, brand_key, compact, candidate_period, service_type_of
run_id = sys.argv[1]
session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode='none'); svc = CommonBenefitService(session)
try:
    with session.transaction():
        conn = session._active_connection; conn.execute('SET TRANSACTION READ ONLY')
        cur = conn.cursor(row_factory=dict_row)
        cur.execute("""SELECT a.card_doc_chunk_id, a.call_seq, a.call_resp_json, c.chunk_raw_txt, c.chunk_seq, c.page_no, c.card_doc_id, c.chunk_split_rule_ver
                       FROM db_pipeline.card_ai_call a JOIN db_pipeline.card_doc_chunk c USING (card_doc_id, page_no, card_doc_chunk_id)
                       WHERE a.card_ai_run_id = %s AND a.call_status = 'SUCCEEDED' ORDER BY c.chunk_seq""", (run_id,))
        calls = cur.fetchall()
        cur.execute("""SELECT card_doc_chunk_id, page_no, chunk_raw_txt FROM db_pipeline.card_doc_chunk
                       WHERE card_doc_id = %s AND chunk_split_rule_ver = %s AND chunk_type_cd = 'NOTICE'""", (calls[0]['card_doc_id'], calls[0]['chunk_split_rule_ver']))
        notices = cur.fetchall()
        cur.execute("""SELECT card_extr_stg_id, card_doc_chunk_id, stg_item_seq, stg_sql_check_cd, stg_raw_item FROM db_pipeline.card_extr_stg WHERE card_ai_run_id = %s""", (run_id,))
        stg = {(r['card_doc_chunk_id'], r['stg_item_seq']): r for r in cur.fetchall()}
        cur.execute("SELECT d.card_doc_id, d.doc_family_cd FROM db_pipeline.card_doc d WHERE card_doc_id = %s", (calls[0]['card_doc_id'],))
        doc = cur.fetchone()
        pages = []
        for call in calls:
            context = [(n['card_doc_chunk_id'], n['chunk_raw_txt']) for n in notices if n['page_no'] == call['page_no'] and n['card_doc_chunk_id'] != call['card_doc_chunk_id']]
            page = PageResult(call['page_no'], call['card_doc_chunk_id'], call['chunk_raw_txt'], PageExtraction.model_validate(call['call_resp_json']),
                              chunk_seq=call['chunk_seq'], context=context)
            seq = 0
            for item in page.extraction.benefits:
                seq += 1; page.benefits.append(StoredItem(stg[(call['card_doc_chunk_id'], seq)]['card_extr_stg_id'], seq, item, check_benefit(item, page)))
            for item in page.extraction.card_conditions:
                seq += 1; page.conditions.append(StoredItem(stg[(call['card_doc_chunk_id'], seq)]['card_extr_stg_id'], seq, item, check_condition(item, page)))
            pages.append(page)
        benefits, _ = merge_pages(pages)
        lookup = {(p.chunk_id, s.seq): s.stg_id for p in pages for s in (*p.benefits, *p.conditions)}
        old_new = collections.Counter(); stages = collections.Counter(); rows = []
        for b in benefits:
            ref = b.merge.source_refs[0]; stg_id = lookup[(ref.card_doc_chunk_id, ref.stg_item_seq)]
            old = next(r for r in stg.values() if r['card_extr_stg_id'] == stg_id)
            old_new[(old['stg_sql_check_cd'], b.sql_check_cd)] += 1
            cand = {'card_extr_stg_id': stg_id, 'stg_raw_item': old['stg_raw_item'], 'stg_normalized_item': b.normalized, 'stg_status': 'PENDING_REVIEW',
                    'stg_sql_check_cd': b.sql_check_cd, 'card_doc_id': doc['card_doc_id'], 'doc_family_cd': doc['doc_family_cd']}
            raw = old['stg_raw_item']
            stage = svc._candidate_problem(cand)
            if not stage:
                cm = svc.repo.rows('common_of_doc', DOC_ID=doc['card_doc_id'])[0]
                g, br = raw.get('service_grade_txt'), raw.get('brand_txt')
                if (br and brand_key(br) != brand_key(cm.get('brand_cd'))) or (g and compact(g) != compact(cm.get('service_grade_cd') or '')):
                    stage = '브랜드·등급 불일치'
            if not stage and service_type_of(raw.get('selection_service_txt')) is None: stage = '선택서비스 불명'
            if not stage:
                try: candidate_period(raw)
                except ValueError: stage = '기간'
            if not stage:
                _, prob = svc._evidence_ids(raw, b.normalized, svc._located(svc.repo.rows('candidate_evidence', STG_ID=stg_id)))
                stage = '근거: ' + prob if prob else 'REGISTRABLE'
            stages[stage if not stage.startswith('후보') else f'후보:{b.sql_check_cd}'] += 1
            rows.append((b.normalized['bnft_nm'], old['stg_sql_check_cd'], b.sql_check_cd, stage))
        conn.rollback()
finally:
    session.database_manager.close()
print('benefits', len(benefits), '| stored→new sql_check', dict(old_new))
print('registration (new contract, existing extraction):', stages.most_common())
for r in rows:
    if r[3] != 'REGISTRABLE': print('  ', r[3][:40], '|', r[0][:30], '|', r[1], '→', r[2])
