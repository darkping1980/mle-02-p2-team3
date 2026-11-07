import csv, importlib.util, json, sys
from pathlib import Path

CHAT=Path(__file__).parents[1]/'file_pipeline'/'chat'
spec=importlib.util.spec_from_file_location('golden_eval_test',CHAT / 'eval' / 'golden_eval.py',submodule_search_locations=[str(CHAT / 'eval')])
# use package imports with configured PYTHONPATH
import importlib
mod=importlib.import_module('card_benefit.payment_card.file_pipeline.chat.eval.golden_eval')

def test_overlap_groups_and_bootstrap_reproducible():
 assert mod.bootstrap([0,1,1],7)==mod.bootstrap([0,1,1],7)
 assert 0<=mod.bootstrap([0,1],7)['low']<=mod.bootstrap([0,1],7)['high']<=1
 per,stats=mod.aggregate_runs([{'a':{'success':True,'group':'g'},'b':{'success':False,'group':'g'}},{'a':{'success':False,'group':'g'},'b':{'success':False,'group':'g'}}],True)
 assert stats['n']==1 and [x['rate'] for x in per]==[.5,0]
 wins,ci=mod.compare_runs([{'a':False}],[{'a':True}]);assert wins[0]['outcome']=='win' and ci['mean']==1

def test_synthetic_eval_direct_edge_weak_truncation_and_no_answer():
 g={'q':{'id':'q','facts':['12,000원'],'doc':'sha','page':'1','start':10,'end':14,'spans':[],'no_answer':False}}
 nodes={'fp':{'id':'fp','name':'카드','props':{'amount':'12000원'}}}
 edges={'e':{'id':'e','source_id':'fp','target_id':'other'}}
 ev=[{'node_id':'fp','edge_id':'','doc_sha256':'sha','page_no':'1','start_pos':'14','end_pos':'20','quote_status':'located'}]
 rec=[{'id':'q','answer':'12,000원','retrieved_node_ids':[mod.review_sheet.uuidish('fp')],'subgraph_node_count':40}]
 row=mod.evaluate(g,rec,nodes,edges,ev)[0]
 assert row['hit'] and row['truncated_possible'] and row['evidence_hit_kind']=='strong'
 refused=mod.evaluate({'n':{'id':'n','no_answer':True,'facts':[]}},[{'id':'n','answer':'정보가 없습니다'}],nodes,edges,[])[0]
 assert refused['abstained'] and refused['all_facts_matched']

def test_alias_loading_and_repo_output_guard(tmp_path):
 f=tmp_path/'g.csv'
 with f.open('w',encoding='utf-8-sig',newline='') as s:
  w=csv.DictWriter(s,fieldnames=['id','질문','기대핵심사실1']);w.writeheader();w.writerow({'id':'x','질문':'q','기대핵심사실1':'f'})
 assert mod.load_golden(f)[0]['facts']==['f']
 try:mod.safe_output(Path(__file__))
 except ValueError:pass
 else:assert False
 assert not {'db','rag','llm'} & set(sys.modules)
