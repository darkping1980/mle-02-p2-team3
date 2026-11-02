"""개발 V7의 Python 공통 혜택 서비스를 시험하고 항상 롤백한다.

--run-with-rollback이 없으면 접속하지 않는다. 기존 카드에 짧은 행 잠금이 걸릴 수 있고,
PostgreSQL 시퀀스는 롤백되지 않는다. 테스트 원문과 추출 후보는 모두 합성 데이터다.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sys
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--run-with-rollback', action='store_true')
if not parser.parse_args().run_with_rollback:
    raise SystemExit('실제 DB 시험은 --run-with-rollback을 지정해야 합니다.')

root = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(root / 'src'), str(root / 'src/card_benefit')]
load_dotenv(root / '.env')
from common.postgres_db_session import PostgresDbSession
from payment_card.db_pipeline.common_benefit_service import CommonBenefitService
from payment_card.db_pipeline.document_repository import MAPPER_ROOT


class SavepointSession:
    """실서비스 SQL mapper를 쓰되 바깥 트랜잭션을 보존한다."""
    def __init__(self, session, conn):
        self.session, self.conn = session, conn

    @contextmanager
    def transaction(self):
        with self.conn.transaction():
            yield self

    def __getattr__(self, name):
        return getattr(self.session, name)


def counts(conn):
    names = [r['relname'] for r in conn.execute("select relname from pg_class where relnamespace='db_pipeline'::regnamespace and relkind='r' order by relname")]
    result = {}
    for name in names:
        result[name] = conn.execute(psycopg.sql.SQL('select count(*) AS n from db_pipeline.{}').format(psycopg.sql.Identifier(name))).fetchone()['n']
    return result


def fixture(conn, token, family, version, card_names, *, with_limit, benefit_name):
    """합성 PDF 페이지·AI 이력·staging·근거를 명시적 ID로 준비한다."""
    suffix = uuid4().hex[:10].upper()
    doc, chunk, run, stg = ('D'+suffix, 'C'+suffix, 'R'+suffix, 'S'+suffix)
    applicability = f'VISA SIGNATURE 선택서비스 02 {card_names[0]} {card_names[1]} 2026년 1월 1일 ~ 12월 31일'
    benefit_quote = f'{benefit_name} 혜택'
    rule_quote = f'{benefit_name} 무료 서비스 제공'
    limit_quote = '회원 카드 단위 가족카드 합산 월 2회'
    items = [('APPLICABILITY', None, applicability), ('BNFT', None, benefit_quote), ('RULE', 'R1', rule_quote)]
    if with_limit: items.append(('LIMIT', 'L1', limit_quote))
    page = '\n'.join(x[2] for x in items)
    digest = hashlib.sha256(page.encode()).hexdigest()
    raw = {
        'item_key':'fixture', 'bnft_nm':benefit_name, 'bnft_type_cd':'SERVICE', 'certainty':'HIGH',
        'brand_txt':'VISA', 'service_grade_txt':'SIGNATURE', 'selection_service_txt':'선택서비스 02',
        'applicable_cards':card_names, 'excluded_cards':[], 'validity_period_txt':'2026년 1월 1일 ~ 12월 31일',
        'evidence':[{'quote_txt':q,'supports':kind,'support_key':key,'link_basis':'SAME_TEXT'} for kind,key,q in items],
    }
    rule = {'rule_key':'R1','cond_expr':None,'predicate_state_cd':'PENDING_REVIEW','target_list':[],
            'calc_method_cd':'FREE_SERVICE','method_ver':1,'value_num':None,'value_unit_cd':None,
            'payout_unit_cd':'SERVICE','basis_amt':None,'calc_params':None,'rule_priority':None,
            'rule_status_cd':'DRAFT','pool_refs':[{'pool_id':'L1','pool_role_cd':'CONSUME'}] if with_limit else []}
    normalized = {'bnft_nm':benefit_name,'bnft_type_cd':'SERVICE','bnft_cond_expr':None,
                  'rule_list':[rule],'relation_list':[],
                  'limit_list':[{'pool_key':'L1','pool_scope_cd':'BENEFIT','period_cd':'MONTH','cap_unit_cd':'COUNT',
                                 'aggregation_key_cd':None,'limit_num':2}] if with_limit else [],
                  'checks':{'value_check_cd':'OK'},'merge':{'source_refs':[{'page_no':1}]}}
    conn.execute("""INSERT INTO db_pipeline.card_doc(card_doc_id,doc_cd,doc_family_cd,doc_type_cd,doc_title,doc_file_nm,doc_file_size,doc_sha256,doc_page_cnt,doc_collect_date,doc_version_no,create_user_id,update_user_id)
        VALUES (%s,%s,%s,'BRAND_SERVICE','합성 시험 문서','test-only.pdf',1,%s,1,now(),%s,'V7_TEST','V7_TEST')""",
        (doc,'TEST_'+suffix,family,hashlib.sha256((page+suffix).encode()).hexdigest(),version))
    conn.execute("""INSERT INTO db_pipeline.card_doc_page(card_doc_id,page_no,page_raw_txt,page_char_cnt,page_txt_sha256,page_layer_cd,page_extractor_nm,page_extractor_ver,create_user_id,update_user_id)
        VALUES(%s,1,%s,%s,%s,'TEXT','TEST','1','V7_TEST','V7_TEST')""",(doc,page,len(page),digest))
    conn.execute("""INSERT INTO db_pipeline.card_doc_chunk(card_doc_id,page_no,card_doc_chunk_id,chunk_seq,chunk_start_pos,chunk_end_pos,chunk_raw_txt,chunk_split_rule_ver,create_user_id,update_user_id)
        VALUES(%s,1,%s,1,1,%s,%s,'PAGE_V1','V7_TEST','V7_TEST')""",(doc,chunk,len(page),page))
    conn.execute("""INSERT INTO db_pipeline.card_ai_run(card_ai_run_id,run_stage_cd,run_call_mthd_cd,run_model_nm,run_prompt_ver,run_prompt_txt,run_target_card_doc_id,run_status,run_end_date,create_user_id,update_user_id)
        VALUES(%s,'EXTRACT','PYTHON_RELAY','mock','test','synthetic',%s,'SUCCEEDED',now(),'V7_TEST','V7_TEST')""",(run,doc))
    conn.execute("""INSERT INTO db_pipeline.card_ai_call(card_ai_run_id,card_doc_id,page_no,card_doc_chunk_id,call_seq,call_input_sha256,call_status,call_resp_json,create_user_id,update_user_id)
        VALUES(%s,%s,1,%s,1,%s,'SUCCEEDED','{}','V7_TEST','V7_TEST')""",(run,doc,chunk,digest))
    conn.execute("""INSERT INTO db_pipeline.card_extr_stg(card_ai_run_id,card_doc_id,page_no,card_doc_chunk_id,call_seq,card_extr_stg_id,stg_item_seq,card_id,stg_kind_cd,stg_raw_item,stg_normalized_item,stg_evidence_txt,stg_evidence_start_pos,stg_evidence_end_pos,stg_sql_check_cd,create_user_id,update_user_id)
        VALUES(%s,%s,1,%s,1,%s,1,NULL,'BENEFIT',%s,%s,%s,1,%s,'LINK_REVIEW','V7_TEST','V7_TEST')""",
        (run,doc,chunk,stg,Jsonb(raw),Jsonb(normalized),applicability,len(applicability)))
    evidence_ids = {}
    for index,(kind,key,quote) in enumerate(items):
        eid=f'E{suffix}{index}'
        start=page.index(quote)+1
        conn.execute("""INSERT INTO db_pipeline.card_source_evidence(evidence_id,card_doc_id,page_no,card_doc_chunk_id,card_extr_stg_id,quote_txt,start_pos,end_pos,approval_status_cd)
          VALUES(%s,%s,1,%s,%s,%s,%s,%s,'PENDING')""",(eid,doc,chunk,stg,quote,start,start+len(quote)-1))
        evidence_ids[kind]=eid
    # 다른 후보가 같은 문구를 인용해도 선택되어서는 안 된다.
    decoy='X'+suffix
    conn.execute("""INSERT INTO db_pipeline.card_extr_stg(card_ai_run_id,card_doc_id,page_no,card_doc_chunk_id,call_seq,card_extr_stg_id,stg_item_seq,card_id,stg_kind_cd,stg_raw_item,stg_evidence_txt,create_user_id,update_user_id)
        VALUES(%s,%s,1,%s,1,%s,2,NULL,'BENEFIT','{}','시험','V7_TEST','V7_TEST')""",(run,doc,chunk,decoy))
    decoy_id='Z'+suffix
    offset=page.index(rule_quote)+1
    conn.execute("""INSERT INTO db_pipeline.card_source_evidence(evidence_id,card_doc_id,page_no,card_doc_chunk_id,card_extr_stg_id,quote_txt,start_pos,end_pos,approval_status_cd)
        VALUES(%s,%s,1,%s,%s,%s,%s,%s,'PENDING')""",(decoy_id,doc,chunk,decoy,rule_quote,offset,offset+len(rule_quote)-1))
    return {'doc':doc,'run':run,'stg':stg,'evidence':evidence_ids,'decoy':decoy_id}


token=uuid4().hex[:10].upper()
card_names=[f'TEST_{token}_A',f'TEST_{token}_B']
options=[{'brand_opt_cd':'VISA02','brand_opt_nm':'Visa Signature 02','brand_cd':'VISA',
          'service_grade_cd':'SIGNATURE','service_type_cd':'02','brand_opt_status_cd':'ACTIVE'}]
session=PostgresDbSession(mapper_root=MAPPER_ROOT,camel_case_keys=False,sql_log_mode='none')
before=None
try:
    with psycopg.connect(os.environ['DB_URL'],connect_timeout=15,row_factory=dict_row) as conn:
        try:
            conn.execute("SET LOCAL lock_timeout='5s'")
            conn.execute("SET LOCAL statement_timeout='60s'")
            before=counts(conn)
            session._active_connection=conn
            service=CommonBenefitService(SavepointSession(session,conn),user_id='V7_TEST')
            card_a=service.register_card({'product_cd':card_names[0],'product_nm':card_names[0],'issuer':'TEST',
                                          'card_kind_cd':'CREDIT','brand_opt_list':options})
            card_b=service.register_card({'product_cd':card_names[1],'product_nm':card_names[1],'issuer':'TEST',
                                          'card_kind_cd':'CREDIT','brand_opt_list':options})
            first=fixture(conn,token,'TEST_MAIN_'+token,1,card_names,with_limit=True,benefit_name='합성 발레')
            ids={first['stg']:'test-main'}
            bases={(first['stg'],'L1'):{'aggregation_key_cd':'CARD_MEMBER','basis_txt':'회원 카드 단위 가족카드 합산'}}
            a=[r for r in service.path_a(card_a,ids,bases) if r.stg_id==first['stg']]
            b=[r for r in service.path_b(first['run'],ids,bases) if r.card_id in (card_a,card_b)]
            repeated=[r for r in service.path_b(first['run'],ids,bases) if r.card_id in (card_a,card_b)]
            assert [x.status for x in a]==['INSERTED'], a
            assert {x.card_id:x.status for x in b}=={card_a:'UNCHANGED',card_b:'INSERTED'}, b
            assert {x.card_id:x.status for x in repeated}=={card_a:'UNCHANGED',card_b:'UNCHANGED'}, repeated
            join=conn.execute("""SELECT b.card_id,b.card_bnft_id,b.verification_status_cd,r.rule_key,p.pool_id,p.aggregation_key_cd
              FROM db_pipeline.card_bnft b JOIN db_pipeline.card_bnft_rule_pool r USING(card_id,card_bnft_id)
              JOIN db_pipeline.card_limit_pool p USING(card_id,pool_id) WHERE b.card_id=ANY(%s) ORDER BY b.card_id""",([card_a,card_b],)).fetchall()
            assert len(join)==2 and all(r['rule_key']=='R1' and r['verification_status_cd']=='PENDING_REVIEW' for r in join),join
            links=conn.execute("""SELECT l.card_id,l.ev_subject_cd,l.rule_key,l.evidence_id,e.card_extr_stg_id,e.approval_status_cd
              FROM db_pipeline.card_evidence_link l JOIN db_pipeline.card_source_evidence e USING(evidence_id)
              WHERE l.card_id=ANY(%s) AND e.card_doc_id=%s ORDER BY l.card_id,l.ev_subject_cd,l.evidence_id""",([card_a,card_b],first['doc'])).fetchall()
            expected={('BNFT',first['evidence']['APPLICABILITY']),('BNFT',first['evidence']['BNFT']),
                      ('RULE',first['evidence']['RULE']),('POOL',first['evidence']['LIMIT'])}
            for card in (card_a,card_b):
                rows=[r for r in links if r['card_id']==card]
                assert {(r['ev_subject_cd'],r['evidence_id']) for r in rows}==expected,rows
                assert all(r['card_extr_stg_id']==first['stg'] and r['approval_status_cd']=='PENDING' for r in rows)
                assert all(r['rule_key']=='R1' for r in rows if r['ev_subject_cd']=='RULE')
            assert not any(r['evidence_id']==first['decoy'] for r in links)
            assert conn.execute('select stg_status from db_pipeline.card_extr_stg where card_extr_stg_id=%s',(first['stg'],)).fetchone()['stg_status']=='PENDING_REVIEW'
            # 한도 없는 동일 업무 혜택의 개정판만 기존 수동 변경을 보존하며 UPDATE한다.
            family='TEST_REV_'+token
            old=fixture(conn,token,family,1,card_names,with_limit=False,benefit_name='합성 이전')
            assert service.apply_run(card_a,old['run'],{old['stg']:'test-revision'})[0].status=='INSERTED'
            new=fixture(conn,token,family,2,card_names,with_limit=False,benefit_name='합성 변경')
            revised=service.apply_run(card_a,new['run'],{new['stg']:'test-revision'})[0]
            assert revised.status=='UPDATED',revised
            saved=conn.execute('select bnft_nm,verification_status_cd from db_pipeline.card_bnft where card_id=%s and card_bnft_id=%s',(card_a,revised.card_bnft_id)).fetchone()
            assert saved=={'bnft_nm':'합성 변경','verification_status_cd':'PENDING_REVIEW'},saved
            print('경로 A/B:',[x.status for x in a],{x.card_id:x.status for x in b},'반복:',[x.status for x in repeated],flush=True)
            print('직접 JOIN:',len(join),'행; 카드별 규칙 1건·한도 1건·관계 1건, 동일 evidence ID 공유',flush=True)
            print('원문 연결: 카드별 BNFT 2, RULE 1, POOL 1; 다른 후보의 동일 문구 제외; 모두 PENDING',flush=True)
            print('개정 UPDATE:',revised.status,'상태:',saved['verification_status_cd'],flush=True)
        finally:
            session._active_connection=None
            conn.rollback()
            print('테스트 트랜잭션 ROLLBACK',flush=True)
    if before is not None:
        with psycopg.connect(os.environ['DB_URL'],connect_timeout=15,row_factory=dict_row) as conn:
            conn.read_only=True
            after=counts(conn)
            remaining=conn.execute("select count(*) AS n from db_pipeline.card_product where product_cd=ANY(%s)",(card_names,)).fetchone()['n']
            if before != after or remaining:
                raise RuntimeError('롤백 전후 건수 또는 시험 카드 잔존 확인 실패')
            print('새 연결 확인: 전체 16개 테이블 행 수 동일, 시험 카드 0건',flush=True)
finally:
    session.database_manager.close()
