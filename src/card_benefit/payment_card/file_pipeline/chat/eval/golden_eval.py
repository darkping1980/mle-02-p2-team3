"""LLM/DB 접속 없이 골든 근거와 저장된 fp_chat 결과를 평가한다."""
from __future__ import annotations
import argparse, csv, json, random, statistics
from collections import defaultdict
from pathlib import Path

from ..answer import answer_eval
from ..review import review_sheet

ROOT = Path(__file__).resolve().parents[6]
ALIASES = {'id': ('id',), 'issuer': ('카드사','issuer'), 'type': ('유형','type'), 'question': ('질문','question'), 'no_answer': ('정답없음','no_answer'), 'from_image_doc': ('이미지문서유래','from_image_doc'), 'difficulty': ('난이도','difficulty'), 'tier': ('구간한도필요','tier_required'), 'issuer_in_question': ('카드사명포함','issuer_in_question'), 'slice_tag': ('슬라이스태그','slice_tag'), 'group': ('변형그룹id','group_id'), 'facts': ('기대핵심사실','expected'), 'doc': ('근거문서','evidence_doc'), 'page': ('근거쪽','evidence_page'), 'start': ('근거시작','evidence_start'), 'end': ('근거끝','evidence_end'), 'spans': ('근거위치JSON','evidence_spans')}

def safe_output(path):
 p=Path(path).expanduser().resolve()
 if p==ROOT or ROOT in p.parents or Path('/tmp').resolve() not in p.parents: raise ValueError('출력은 저장소 밖 /tmp 아래만 허용됩니다.')
 return p

def _read(path):
 with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def load_golden(path):
 rows=[]
 for raw in _read(path):
  r={k:next((raw.get(a) for a in aliases if raw.get(a) not in (None,'')), '') for k,aliases in ALIASES.items()}
  r['facts']=[raw.get(f'기대핵심사실{i}','') for i in range(1,4) if raw.get(f'기대핵심사실{i}','').strip()] if not isinstance(r['facts'],list) else r['facts']
  if isinstance(r['facts'],str):
   try:r['facts']=json.loads(r['facts'])
   except ValueError:r['facts']=[r['facts']] if r['facts'] else []
  try:r['spans']=json.loads(r['spans']) if r['spans'] else []
  except ValueError:r['spans']=[]
  r['no_answer']=str(r['no_answer']).strip() in ('예','true','True','1')
  rows.append(r)
 return rows

def _span_list(q):
 spans=[]
 for s in q.get('spans',[]):
  if isinstance(s,dict): spans.append({'fact':str(s.get('fact','')),'doc':str(s.get('doc_sha256') or s.get('doc') or ''),'page':str(s.get('page_no') or s.get('page') or q.get('page','')),'start':_int(s.get('start',s.get('start_pos'))),'end':_int(s.get('end',s.get('end_pos')))})
 if not spans and q.get('doc') and q.get('page'):
  spans=[{'fact':f,'doc':q['doc'],'page':q['page'],'start':_int(q['start']),'end':_int(q['end'])} for f in q['facts']] or [{'fact':'','doc':q['doc'],'page':q['page'],'start':_int(q['start']),'end':_int(q['end'])}]
 return spans

def _int(v):
 try:return int(v)
 except (TypeError,ValueError):return None

def load_graph(dirs):
 nodes={}; edges={}; evidence=[]
 for folder in map(Path,dirs):
  for row in _read(folder/'fp_nodes.csv'):
   try:props=json.loads(row.get('props') or '{}')
   except ValueError:props={}
   nodes[row['id']]={**row,'props':props,'name':str(props.get('name') or props.get('text') or props.get('product_name') or row['id'])}
  for e in _read(folder/'fp_edges.csv'):edges[e['id']]=e
  evidence.extend(_read(folder/'fp_evidence.csv'))
 return nodes,edges,evidence

def evaluate(golden, results, nodes, edges, evidence, *, strict_node_evidence=False, overlap='any', min_overlap=.5):
 out=[]; view={review_sheet.uuidish(i):i for i in nodes}
 for rec in results:
  q=golden.get(str(rec.get('id')), rec.get('question') or {}); answer=str(rec.get('answer','')); no=bool(q.get('no_answer',q.get('no_answer') is True))
  if isinstance(q.get('no_answer'),str):no=q['no_answer'] in ('예','true','True','1')
  fpids={view[x] for x in rec.get('retrieved_node_ids',[]) if x in view}
  found=[]
  for ev in evidence:
   edge=edges.get(ev.get('edge_id'))
   direct=ev.get('node_id') in fpids
   linked=bool(edge and not strict_node_evidence and ({edge.get('source_id'),edge.get('target_id')} & fpids))
   if direct or linked: found.append(ev)
  spans=_span_list(q); hits=[]; weak=0
  for sp in spans:
   matches=[]
   for ev in found:
    if sp['doc'] and sp['doc']!=ev.get('doc_sha256'):continue
    if sp['page'] and sp['page']!=ev.get('page_no'):continue
    a,b=_int(ev.get('start_pos')),_int(ev.get('end_pos'))
    if sp['start'] is not None and sp['end'] is not None and a is not None and b is not None:
     inter=max(0,min(sp['end'],b)-max(sp['start'],a)+1); denom=max(1,sp['end']-sp['start']+1)
     if (inter>0 if overlap=='any' else inter/denom>=min_overlap):matches.append(ev)
    elif sp['doc'] and sp['page']:matches.append(ev)
   strong=any(_int(m.get('start_pos')) is not None and sp['start'] is not None and _int(m.get('end_pos')) is not None and sp['end'] is not None for m in matches)
   hits.append(bool(matches)); weak+=bool(matches) and not strong
  kind='strong' if any(h and not (i < weak) for i,h in enumerate(hits)) else ('weak' if weak else 'none')
  context=' '.join(_context(n) for i,n in nodes.items() if i in fpids)
  facts=[]
  for fact in q.get('facts',[]):
   matched,mk,_=answer_eval._value_match(answer,str(fact),str(q.get('type','')))
   facts.append({'fact':str(fact),'matched':matched,'match_kind':mk})
  refusal=answer_eval._refusal(answer)
  abstained=refusal if no else None
  all_matched=bool(abstained) if no else (all(x['matched'] for x in facts) if facts else None)
  ungrounded=[]
  if answer and not refusal:
   for val,unit,a,b in answer_eval._number_candidates(answer):
    token=answer[a:b]
    if token not in context and not _date_context(answer,a):ungrounded.append(token)
  tier=(_tier_linked(answer) if str(q.get('tier',''))=='예' else None)
  out.append({'id':str(rec.get('id')),'hit':bool(any(hits)) if not no else None,'span_recall':sum(hits)/len(hits) if hits and not no else None,'retrieved_evidence_count':len(found),'evidence_hit_kind':kind,'evidence_reason':'span overlap' if kind=='strong' else ('document/page only; ambiguous or missing position' if kind=='weak' else 'no matching evidence'), 'truncated_possible':_int(rec.get('subgraph_node_count')) is not None and int(rec.get('subgraph_node_count'))>=40,'facts':facts,'all_facts_matched':all_matched,'abstained':abstained,'grounded':('n.a.' if refusal or not answer or not answer_eval._number_candidates(answer) else not bool(ungrounded)),'ungrounded_numbers':ungrounded,'tier_linked':tier,'refusal':refusal,'cost_usd':rec.get('cost_usd'),'group':q.get('변형그룹id',q.get('group_id',q.get('id'))),'question':q})
 return out

def _context(n):
 vals=[n.get('name','')]
 def walk(x):
  if isinstance(x,dict):
   for v in x.values():walk(v)
  elif isinstance(x,(list,tuple)): 
   for v in x:walk(v)
  elif isinstance(x,(str,int,float)):vals.append(str(x))
 walk(n.get('props',{})); return ' '.join(vals)
def _date_context(answer,pos):return any(m.start()<=pos<m.end() for m in __import__('re').finditer(r'\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일',answer))
def _tier_linked(answer):
 import re
 return any(re.search(r'\d[\d,]*\s*(?:만|천)?\s*원\s*이상',s) and re.search(r'\d[\d,]*\s*원',s) for s in re.split(r'[.\n]+',answer))

def bootstrap(values, seed=7, iterations=2000):
 vals=list(values)
 if not vals:return {'mean':None,'low':None,'high':None,'n':0}
 rng=random.Random(seed); means=[sum(rng.choice(vals) for _ in vals)/len(vals) for _ in range(iterations)]; means.sort()
 return {'mean':sum(vals)/len(vals),'low':means[int(.025*iterations)],'high':means[min(iterations-1,int(.975*iterations))],'n':len(vals)}
def aggregate_runs(runs, cluster=True, seed=7):
 ids=sorted(set().union(*(r.keys() for r in runs))); per=[]
 for i in ids:
  vals=[r.get(i,False) for r in runs]; good=[bool(v.get('success')) if isinstance(v,dict) else bool(v) for v in vals]; per.append({'id':i,'successes':sum(good),'runs':len(vals),'rate':sum(good)/len(vals) if vals else None,'group':next(((r[i].get('group',i) if isinstance(r[i],dict) else i) for r in runs if i in r),i)})
 sample=defaultdict(list)
 for x in per:sample[x['group'] if cluster else x['id']].append(x['rate'])
 unit=[sum(v)/len(v) for v in sample.values()]; stats=bootstrap(unit,seed)
 if len(unit)>1:
  import math
  stats['stddev']=statistics.stdev(unit)
 else:stats['stddev']=0.0
 return per,stats
def compare_runs(a,b,cluster=True,seed=7):
 def means(rs):return {k:sum(v.get(k,False) for v in rs)/len(rs) for k in set().union(*(r.keys() for r in rs))}
 am,bm=means(a),means(b); keys=sorted(set(am)&set(bm)); wins=[]
 for k in keys:wins.append({'id':k,'a':am[k],'b':bm[k],'outcome':'win' if bm[k]>am[k] else ('loss' if bm[k]<am[k] else 'tie'),'group':next(((x.get(k,{}).get('group',k) if isinstance(x.get(k),dict) else k) for x in a if k in x),k)})
 grouped=defaultdict(list)
 for x in wins:grouped[x['group'] if cluster else x['id']].append(x['b']-x['a'])
 ci=bootstrap([sum(v)/len(v) for v in grouped.values()],seed)
 return wins,ci

def _write_jsonl(path,rows):path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
def _read_jsonl(paths):return [[json.loads(x) for x in Path(p).read_text(encoding='utf-8').splitlines() if x.strip()] for p in paths]
def run(args):
 gold_rows=load_golden(args.golden); golden={str(q['id']):q for q in gold_rows}; nodes,edges,evidence=load_graph(args.csv_dir); results=_read_jsonl(args.results); all_rows=[]
 for ix,rs in enumerate(results):all_rows.extend(evaluate(golden,rs,nodes,edges,evidence,strict_node_evidence=args.strict_node_evidence,overlap=args.overlap))
 out=safe_output(args.output_dir);out.mkdir(parents=True,exist_ok=True);_write_jsonl(out/'per_question.jsonl',all_rows)
 slices=[]
 for field in ('issuer','type','difficulty','tier','issuer_in_question','no_answer','from_image_doc','slice_tag'):
  for val in sorted({str(q.get(field,'')) for q in gold_rows}):
   ids={str(q['id']) for q in gold_rows if str(q.get(field,''))==val}; rr=[x for x in all_rows if x['id'] in ids]; n=len(rr); row={'slice':field,'value':val,'n':n,'sample_status':'표본 부족' if n<5 else '','hit':_avg([x['hit'] for x in rr if x['hit'] is not None]),'span_recall':_avg([x['span_recall'] for x in rr if x['span_recall'] is not None]),'all_facts_matched':_avg([x['all_facts_matched'] for x in rr if x['all_facts_matched'] is not None]),'grounded':_avg([x['grounded'] for x in rr if isinstance(x['grounded'],bool)]),'refusal_rate':_avg([x['refusal'] for x in rr]),'avg_cost_usd':_avg([float(x['cost_usd']) for x in rr if x['cost_usd'] not in (None,'')])};slices.append(row)
 with (out/'slices.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(slices[0]) if slices else ['slice']);w.writeheader();w.writerows(slices)
 counts={'questions':len(gold_rows),'records':len(all_rows),'search_hit':_avg([x['hit'] for x in all_rows if x['hit'] is not None]),'fact_match':_avg([x['all_facts_matched'] for x in all_rows if isinstance(x['all_facts_matched'],bool)]),'grounded':_avg([x['grounded'] for x in all_rows if isinstance(x['grounded'],bool)])}
 (out/'summary.md').write_text('자동 판정이며 사람 판정이 아님. 독립 문항 n개일 때 비율 p의 대략적인 95% 오차 폭은 1.96√(p(1-p)/n)입니다.\n\n'+json.dumps(counts,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 if len(results)>1:
  qmap={str(q['id']):q for q in gold_rows};runs=[{x['id']:bool(x['all_facts_matched']) for x in rr if x['all_facts_matched'] is not None} for rr in [all_rows[i*len(gold_rows):(i+1)*len(gold_rows)] for i in range(len(results))]]
  per,stats=aggregate_runs(runs,not args.no_cluster,args.seed)
  with (out/'repeat.csv').open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(per[0]) if per else ['id']);w.writeheader();w.writerows(per)
  (out/'summary.md').open('a',encoding='utf-8').write('\nRepeat: '+json.dumps(stats,ensure_ascii=False)+'\n')
 print(json.dumps(counts,ensure_ascii=False));return 0
def _avg(xs):return sum(xs)/len(xs) if xs else None

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--golden',required=True);p.add_argument('--results',nargs='+',required=True);p.add_argument('--csv-dir',action='append',required=True);p.add_argument('--output-dir',required=True);p.add_argument('--strict-node-evidence',action='store_true');p.add_argument('--overlap',choices=('any','50'),default='any');p.add_argument('--compare-a',nargs='+');p.add_argument('--compare-b',nargs='+');p.add_argument('--no-cluster',action='store_true');p.add_argument('--seed',type=int,default=7);a=p.parse_args(argv);return run(a)
if __name__=='__main__':raise SystemExit(main())
