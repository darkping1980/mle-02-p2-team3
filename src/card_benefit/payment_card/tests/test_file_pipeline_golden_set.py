import importlib.util,csv
from pathlib import Path
CHAT=Path(__file__).resolve().parents[1]/'file_pipeline'/'chat'
spec=importlib.util.spec_from_file_location('golden_set_test',CHAT / 'eval' / 'golden_set.py'); gs=importlib.util.module_from_spec(spec);spec.loader.exec_module(gs)
def row(**kw):
 d={k:'' for k in gs.HEADERS};d.update({'id':'x','카드사':'하나','유형':'혜택조회','질문':'합성 질문','기대핵심사실1':'합성 사실','근거문서':'synthetic.pdf','근거쪽':'1','정답없음':'아니오','이미지문서유래':'아니오','문서가 있는 그래프':'우리','작성자':'합성 작성','검수자':'합성 검수'});d.update(kw);return d
def save(p,rows):
 with p.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=gs.HEADERS);w.writeheader();w.writerows(rows)
def test_mapping_and_no_answer_rules(tmp_path):
 p=tmp_path/'g.csv';save(p,[row(),row(id='n',유형='정답없음',정답없음='예',기대핵심사실1='')]);q=gs.convert(p);assert q[0]['type']=='card_benefits' and q[1]['no_answer'] and q[1]['expected']==[]
 assert gs.TYPE_MAP['숫자정확도']=='benefit_limit' and gs.ISSUERS['우리']=='woori'
def test_collects_all_row_errors_and_output_guard(tmp_path):
 p=tmp_path/'g.csv';save(p,[row(카드사='XX',유형='XX',정답없음='XX',이미지문서유래='XX',**{'문서가 있는 그래프':'XX','검수자':''}),row(id='x',정답없음='예',기대핵심사실1='남음')])
 try:gs.convert(p);assert False
 except ValueError as e:assert '2행' in str(e) and '3행' in str(e) and 'id 중복' in str(e)
 try:gs.safe_output(Path(__file__));assert False
 except ValueError:pass
def test_stratification_is_deterministic_and_summary():
 qs=[{'id':str(i),'issuer':'hana','type':'benefit_limit','no_answer':False,'from_image_doc':i%2==0} for i in range(10)]
 a,b=gs.stratified_split(qs,.5,7);a2,b2=gs.stratified_split(qs,.5,7);assert a==a2 and b==b2 and len(a)==5 and len(b)==5
 assert sum(x['count'] for x in gs.summary(a,'dev'))==5
