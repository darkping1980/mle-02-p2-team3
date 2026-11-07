"""답변 결과와 CSV 그래프 근거를 연결한 로컬 검수 HTML/CSV를 만든다."""
from __future__ import annotations
import argparse,csv,hashlib,html,json
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[6]
MEANINGFUL={'Benefit','Condition','Limit','Target','Card'}
def safe_output(path):
 p=Path(path).expanduser().resolve()
 if p==ROOT or ROOT in p.parents or Path('/tmp').resolve() not in p.parents: raise ValueError('출력은 저장소 밖 /tmp 아래만 허용됩니다.')
 return p
def uuidish(value):
 h=hashlib.md5(str(value).encode()).hexdigest(); return f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}'
def read(path):
 with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def node_name(row):
 try:p=json.loads(row.get('props') or '{}')
 except Exception:p={}
 return str(p.get('name') or p.get('text') or p.get('product_name') or row.get('id',''))
def load_sources(dirs,documents):
 nodes={}; edges=[]; ev=[]; issuers={}; docs={}
 for folder in map(Path,dirs):
  issuer=folder.name.replace('fp-check-','')
  for n in read(folder/'fp_nodes.csv'):
   n['_name']=node_name(n); n['_issuer']=issuer; nodes[n['id']]=n; issuers[n['id']]=issuer
  edges.extend([{**e,'_issuer':issuer} for e in read(folder/'fp_edges.csv')])
  ev.extend([{**e,'_issuer':issuer} for e in read(folder/'fp_evidence.csv')])
 for path in map(Path,documents):
  for d in read(path): docs[d.get('sha256','')]=d
 return nodes,edges,ev,docs

def pdf_path(doc,doc_index):
 fp=Path(doc.get('file_path',''))
 if fp.is_absolute(): return fp.resolve()
 candidates=[ROOT/'src/data'/fp, ROOT/'src/card_benefit/data'/fp, ROOT/'src/card_benefit/data/raw'/fp, doc_index.parent.parent/fp, doc_index.parent/fp]
 return next((p.resolve() for p in candidates if p.exists()), candidates[0].resolve())
def collect_evidence(record,nodes,edges,evidences,docs,doc_indexes,limit=12,with_excerpt=False):
 q=record.get('question') or {}; issuer=q.get('issuer') or record.get('issuer')
 ids=set(record.get('retrieved_node_ids') or [])
 # DB/view IDs map back to the exact CSV fp IDs via md5(fp id)::uuid.
 fp_by_view={uuidish(i):i for i in nodes}
 fpids={fp_by_view[x] for x in ids if x in fp_by_view}
 picked=[nodes[i] for i in fpids if nodes[i].get('node_type') in MEANINGFUL]
 target=set(fpids)
 edge_by_id={e['id']:e for e in edges}
 for e in edges:
  if e['source_id'] in fpids or e['target_id'] in fpids: target.add(e['source_id']);target.add(e['target_id'])
 result=[]; seen=set()
 for ev in evidences:
  targets=[]
  if ev.get('node_id'):targets=[ev['node_id']]
  elif ev.get('edge_id') in edge_by_id:
   e=edge_by_id[ev['edge_id']];targets=[e['source_id'],e['target_id']]
  for tid in targets:
   n=nodes.get(tid)
   if not n or n.get('node_type') not in MEANINGFUL or tid not in target:continue
   if issuer and ev['_issuer']!=issuer:continue
   key=(ev['_issuer'],ev.get('doc_sha256'),ev.get('page_no'),ev.get('start_pos'),ev.get('end_pos'),tid,ev.get('quote_status'))
   if key in seen:continue
   seen.add(key); doc=docs.get(ev.get('doc_sha256',''),{}); doc_index=next((p for p in map(Path,doc_indexes) if p.parent.name in (ev['_issuer'],ev['_issuer']+'_all') or p.parent.parent.name==ev['_issuer']),Path(doc_indexes[0]) if doc_indexes else Path('/tmp'))
   pp=pdf_path(doc,doc_index) if doc else Path('/missing.pdf')
   item={'issuer':ev['_issuer'],'document':Path(doc.get('file_path','')).name or ev.get('doc_sha256',''),'page':ev.get('page_no',''),'start':ev.get('start_pos',''),'end':ev.get('end_pos',''),'quote_status':ev.get('quote_status','missing'),'node_name':n['_name'],'node_type':n.get('node_type',''),'pdf_link':pp.as_uri()+(f"#page={ev['page_no']}" if ev.get('page_no','').isdigit() else '')}
   if with_excerpt and item['quote_status']=='located':
    try:
     import fitz
     if not pp.is_file():
      item['excerpt']='PDF 없음';item['quote_status']='PDF 없음';result.append(item);continue
     with fitz.open(pp) as pdf:
      page=int(item['page'])
      if page<1 or page>len(pdf):raise IndexError
      txt=pdf[page-1].get_text(); start=int(item['start']);end=int(item['end']); excerpt=txt[start-1:end]
      item['excerpt']=excerpt[:160] if excerpt else '위치 불일치'
      if not excerpt:item['quote_status']='위치 불일치'
    except FileNotFoundError:item['excerpt']='PDF 없음';item['quote_status']='PDF 없음'
    except Exception:item['excerpt']='위치 불일치';item['quote_status']='위치 불일치'
   result.append(item)
 return result[:limit],max(0,len(result)-limit),picked

def make_sheet(results_path,questions_path,csv_dirs,documents,output,*,with_excerpt=False,limit=12):
 out=safe_output(output);out.parent.mkdir(parents=True,exist_ok=True)
 questions={q.get('id'):q for q in json.loads(Path(questions_path).read_text(encoding='utf-8')).get('questions',[])}
 results=[json.loads(x) for x in Path(results_path).read_text(encoding='utf-8').splitlines() if x.strip()]
 nodes,edges,evidences,docs=load_sources(csv_dirs,documents); cards=[]
 for rec in results:
  q=questions.get(rec.get('id'),rec.get('question') or {}); rec['question']=q
  evidence,more,picked=collect_evidence(rec,nodes,edges,evidences,docs,documents,limit,with_excerpt)
  classification=rec.get('classification','error' if rec.get('status')=='error' else '')
  no_answer=bool(q.get('no_answer'))
  status=('정답없음 거절' if rec.get('refusal') else '정답없음 답변') if no_answer else {'search_hit_answer_hit':'정답 포함','search_hit_answer_miss':'검색 성공·답변 실패','search_miss':'검색 실패'}.get(classification,classification or '판정 미상')
  cards.append({'record':rec,'q':q,'evidence':evidence,'more':more,'picked':picked,'status':status,'miss':status in ('검색 성공·답변 실패','검색 실패','정답없음 답변')})
 all_n=len(cards); missed=sum(c['miss'] for c in cards)
 bytype=defaultdict(int);byissuer=defaultdict(int)
 for c in cards:bytype[c['q'].get('type','')]+=1;byissuer[c['q'].get('issuer','')]+=1
 esc=lambda x:html.escape(str(x or ''),quote=True)
 def table(title,items):return '<h2>'+esc(title)+'</h2><table><tr><th>구분</th><th>건수</th></tr>'+''.join(f'<tr><td>{esc(k)}</td><td>{v}</td></tr>' for k,v in sorted(items.items()))+'</table>'
 chunks=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>답변 검수 시트</title><style>:root{color-scheme:light dark}body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;background:Canvas;color:CanvasText}.card{border:1px solid #888;border-left:6px solid #287a4b;border-radius:8px;padding:1rem;margin:1rem 0}.miss{border-left-color:#c33}.muted{opacity:.8}table{border-collapse:collapse}td,th{border:1px solid #888;padding:.4rem}.answer{white-space:pre-wrap}.ev{border-top:1px solid #888;padding:.5rem}a{color:LinkText}button{padding:.5rem}</style><h1>답변 검수 시트</h1>',f'<p>전체 {all_n}건 · 틀리거나 놓침 {missed}건</p>',table('유형별',bytype),table('카드사별',byissuer),'<button onclick="document.body.classList.toggle(\'miss-only\')">틀린/놓친 문항만 보기</button><style>body.miss-only .card:not(.miss){display:none}</style>']
 for c in cards:
  r=c['record'];q=c['q'];cls='miss' if c['miss'] else ''
  chunks.append(f'<article class="card {cls}"><h2>{esc(q.get("id"))} · {esc(c["status"])}</h2><p><b>질문</b>: {esc(q.get("question"))}</p><p><b>기대 핵심 사실</b>: {esc(" / ".join(map(str,q.get("expected",[]))))}</p><p><b>답변</b></p><div class="answer">{esc(r.get("answer"))}</div><p>자동 분류: {esc(c["status"])} · 시드: {esc(", ".join(r.get("selected_seed_names",[])))}</p><h3>답변 근거 위치 ({len(c["evidence"])}건){f' · 외 {c["more"]}건' if c['more'] else ''}</h3>')
  for ev in c['evidence']:
   chunks.append(f'<div class="ev">{esc(ev["issuer"])} · {esc(ev["document"])} · p.{esc(ev["page"])} · {esc(ev["start"])}~{esc(ev["end"])} · {esc(ev["quote_status"])} · {esc(ev["node_name"])} ({esc(ev["node_type"])}) · <a href="{esc(ev["pdf_link"])}">PDF 열기</a>{"<p>"+esc(ev.get("excerpt"))+"</p>" if with_excerpt else ""}</div>')
  if not c['evidence']:chunks.append('<p class="muted">연결된 근거 위치 없음</p>')
  chunks.append('</article>')
 chunks.append('</html>');out.write_text(''.join(chunks),encoding='utf-8')
 csvout=out.with_suffix('.csv'); fields=['id','issuer','type','question','expected','answer','classification','selected_seed_names','evidence_count','more_evidence','evidence_locations']
 with csvout.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for c in cards:
   r=c['record'];q=c['q'];w.writerow({'id':q.get('id'),'issuer':q.get('issuer'),'type':q.get('type'),'question':q.get('question'),'expected':' | '.join(map(str,q.get('expected',[]))),'answer':r.get('answer'),'classification':c['status'],'selected_seed_names':' | '.join(r.get('selected_seed_names',[])),'evidence_count':len(c['evidence']),'more_evidence':c['more'],'evidence_locations':json.dumps(c['evidence'],ensure_ascii=False)})
 return out,csvout,cards

def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--results',required=True);p.add_argument('--questions',required=True);p.add_argument('--csv-dir',action='append',required=True);p.add_argument('--documents',action='append',required=True);p.add_argument('--output',required=True);p.add_argument('--with-excerpt',action='store_true');p.add_argument('--max-evidence',type=int,default=12);p.add_argument('--focus',action='store_true',help='정답 문장이 든 근거를 위로, 줄 번호·형광·그래프 경로를 붙인 집중 보기 HTML만 만든다');a=p.parse_args(argv)
 if a.focus:
  from .review_focus import make_focus_sheet
  h=make_focus_sheet(a.results,a.questions,a.csv_dir,a.documents,a.output);print(json.dumps({'html':str(h)},ensure_ascii=False));return 0
 h,c,_=make_sheet(a.results,a.questions,a.csv_dir,a.documents,a.output,with_excerpt=a.with_excerpt,limit=a.max_evidence);print(json.dumps({'html':str(h),'csv':str(c)},ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
