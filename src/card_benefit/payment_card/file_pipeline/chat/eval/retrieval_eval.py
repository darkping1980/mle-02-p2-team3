"""LLM-free retrieval evaluation for fp_chat, backed by CSV by default.

REACH_SQL has LIMIT 40 with no ORDER BY: PostgreSQL chooses plan-dependent rows.
CSV traversal uses stable input order (fp_nodes/fp_edges CSV order) as a reproducible
approximation; seeds are fetched separately first, as in rag._explore, then reach rows
are appended and the combined set is truncated to 40.
"""
from __future__ import annotations
import argparse, csv, json, hashlib, time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
MAX_NODES=40

def safe_output(path):
    p=Path(path).expanduser().resolve()
    if ROOT == p or ROOT in p.parents or Path('/tmp').resolve() not in p.parents:
        raise ValueError('output must be outside repository under /tmp')
    return p

def props(row):
    try:
        x=json.loads(row.get('props') or '{}'); return x if isinstance(x,dict) else {}
    except (ValueError,TypeError): return {}

def load_csv(folders):
    raw=[]; edges=[]; evid=[]
    for folder in folders:
        folder=Path(folder)
        with (folder/'fp_nodes.csv').open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                p=props(r); name=str(p.get('name') or p.get('text') or p.get('product_name') or r['id'])
                name=' '.join(name.split())[:80]
                raw.append({'id':str(uuidish(r['id'])),'name':name,'label':r['node_type'],'props':{k:v for k,v in p.items() if k!='name' and isinstance(v,(str,int,float,bool))},'_fp_id':r['id']})
        for filename,target in [('fp_edges.csv',edges),('fp_evidence.csv',evid)]:
            with (folder/filename).open(encoding='utf-8-sig',newline='') as f: target.extend(csv.DictReader(f))
    byfp={n['_fp_id']:n for n in raw}; docs={}
    for e in evid:
        sha=e.get('doc_sha256','')
        if sha: docs.setdefault(sha,[]).append(e)
    doc_nodes=[]
    for sha, rows in docs.items():
        located=[r for r in rows if r.get('quote_status')=='located']
        page=min((int(r['page_no']) for r in located if r.get('page_no','').isdigit()),default=None)
        doc_nodes.append({'id':uuidish('doc:'+sha),'name':'문서 '+sha[:8],'label':'Document','props':{'summary':f"문서 해시 {sha[:8]}, 쪽 {page if page is not None else '미상'}…",'fp_id':'doc:'+sha}})
    raw.extend(doc_nodes)
    links=defaultdict(list)
    def link(fp_id,sha,status):
        if fp_id and sha: links[fp_id].append((sha,status))
    byedge={e['id']:e for e in edges}
    for e in evid:
        if e.get('node_id'): link(e['node_id'],e.get('doc_sha256'),e.get('quote_status'))
        if e.get('edge_id') in byedge:
            edge=byedge[e['edge_id']]
            for endpoint in (edge['source_id'],edge['target_id']): link(endpoint,e.get('doc_sha256'),e.get('quote_status'))
    outedges=[]
    for e in edges:
        if e['source_id'] in byfp and e['target_id'] in byfp:
            outedges.append({'source':byfp[e['source_id']]['id'],'target':byfp[e['target_id']]['id'],'type':e['edge_type']})
    docid={d['name'][3:]:d['id'] for d in doc_nodes}
    for fp_id, vals in links.items():
        pref={}
        for sha,status in vals:
            pref[sha]= 'located' if status=='located' or pref.get(sha)=='located' else status
        chosen=sorted(pref,key=lambda s:(pref[s]!='located',s))[:3]
        for sha in chosen:
            if fp_id in byfp and sha[:8] in docid:
                outedges.append({'source':byfp[fp_id]['id'],'target':docid[sha[:8]],'type':'SUPPORTED_BY'})
    # PostgreSQL md5(text)::uuid uses first 128 bits with UUID formatting.
    return raw,outedges

def uuidish(value):
    h=hashlib.md5(str(value).encode()).hexdigest()
    return f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}'

def select_seeds(nodes,question,mode='contains',n=3):
    if mode=='oracle': return list(dict.fromkeys(map(str,question.get('seed_entities',[]))))
    if mode!='contains': raise ValueError('seed mode must be contains or oracle')
    q=question.get('question','')
    names={x['name'] for x in nodes if x['label']!='Document' and len(x['name'])>=2 and x['name'] in q}
    return sorted(names,key=lambda x:(-len(x),x))[:n]

def traverse(nodes,edges,names,hops=2,limit=MAX_NODES):
    byid={n['id']:n for n in nodes}; seeds=[n for n in nodes if n['name'] in names]
    adj=defaultdict(list)
    for e in edges: adj[e['source']].append(e['target']); adj[e['target']].append(e['source'])
    found={n['id']:0 for n in seeds}; frontier=[n['id'] for n in seeds]
    for depth in range(hops):
        nxt=[]
        for nodeid in frontier:
            for other in adj[nodeid]:
                if other not in found: found[other]=depth+1; nxt.append(other)
        frontier=nxt
    reach=[n for n in nodes if n['id'] in found]
    ordered=[]
    for n in seeds+reach:
        if all(x['id']!=n['id'] for x in ordered): ordered.append(n)
    truncated=len(ordered)>limit
    picked=ordered[:limit]; ids={n['id'] for n in picked}
    return {'nodes':picked,'edges':[e for e in edges if e['source'] in ids and e['target'] in ids], 'seeds':[n['id'] for n in seeds if n['id'] in ids], 'truncated':truncated}

def question_metrics(q,sub,elapsed,max_nodes=MAX_NODES,selected_seeds=(),nodes_all=()):
    nodes=sub['nodes']; expected=list(map(str,q.get('expected',[]))); expected_names=list(map(str,q.get('expected_node_names',[])))
    # Partial match: expected value is a substring of a node name or scalar property string.
    hay=[str(n.get('name',''))+' '+ ' '.join(map(str,n.get('props',{}).values())) for n in nodes]
    found=[v for v in expected if any(v in h for h in hay)]
    expected_seeds=list(map(str,q.get('seed_entities',[]))); selected=set(selected_seeds)
    name_hits=sum(x in selected for x in expected_seeds)
    counts=defaultdict(int)
    for n in nodes_all: counts[n['name']]+=1
    ambiguous=int(any(counts.get(name,0)>1 for name in selected))
    return {'seed_hits':name_hits,'seed_expected':len(expected_seeds),'ambiguous_question':ambiguous,'expected_node_recall':len(found)/len(expected) if expected else 0.0,'expected_hits':len(found),'expected_count':len(expected),'full_recall':int(len(found)==len(expected)) if expected else 0,'nodes':len(nodes),'edges':len(sub['edges']),'truncated':int(sub.get('truncated',False) or len(nodes)>=max_nodes),'source_display':int(any(n['label']=='Document' for n in nodes)),'elapsed_seconds':elapsed,'ambiguous_seed_nodes':len(sub['seeds'])}

def aggregate(rows):
    total={}
    for key in ('seed_hits','seed_expected','expected_hits','expected_count','nodes','edges','truncated','source_display','full_recall','elapsed_seconds','ambiguous_seed_nodes'):
        total[key]=sum(r[key] for r in rows)
    correct=sum(r.get('seed_correct_count',r['seed_hits']) for r in rows)
    selected=sum(r.get('selected_seed_count',0) for r in rows)
    total.update(questions=len(rows),seed_hit_rate=total['seed_hits']/total['seed_expected'] if total['seed_expected'] else 0,seed_precision=correct/selected if selected else 0,avg_wrong_seeds=sum(r.get('wrong_seed_count',0) for r in rows)/len(rows) if rows else 0,expected_node_recall=total['expected_hits']/total['expected_count'] if total['expected_count'] else 0,full_recall_rate=total['full_recall']/len(rows) if rows else 0,avg_nodes=total['nodes']/len(rows) if rows else 0,avg_edges=total['edges']/len(rows) if rows else 0,truncation_rate=total['truncated']/len(rows) if rows else 0,source_display_rate=total['source_display']/len(rows) if rows else 0,avg_seconds=total['elapsed_seconds']/len(rows) if rows else 0)
    return total

def evaluate(questions,nodes,edges,seed_mode='contains',hops=2,n=3,seed_threshold=0.15):
    matcher = None
    if seed_mode == 'fuzzy':
        try:
            from .seed_matcher import SeedMatcher
        except ImportError:
            from eval.seed_matcher import SeedMatcher
        matcher = SeedMatcher(nodes)
    out=[]
    for q in questions:
        start=time.perf_counter(); seeds=matcher.select(q.get('question',''),n,threshold=seed_threshold) if matcher else select_seeds(nodes,q,seed_mode,n); sub=traverse(nodes,edges,seeds,hops); metric=question_metrics(q,sub,time.perf_counter()-start,selected_seeds=seeds,nodes_all=nodes)
        expected=set(map(str,q.get('seed_entities',[])))
        metric['seed_correct_count']=len(expected.intersection(seeds))
        metric['selected_seed_count']=len(seeds)
        metric['seed_precision']=metric['seed_correct_count']/len(seeds) if seeds else 0.0
        metric['wrong_seed_count']=len(set(seeds)-expected)
        out.append({'id':q.get('id'),'type':q.get('type'),'metrics':metric,'seeds':seeds})
    return out

def run_retrieval(args):
    qpath=Path(args.questions).expanduser().resolve()
    if Path('/tmp').resolve() not in qpath.parents or ROOT in qpath.parents: raise ValueError('questions must be under /tmp')
    qs=json.loads(qpath.read_text(encoding='utf-8')).get('questions',[])
    if args.source=='db' and not args.execute:
        print(json.dumps({'mode':'dry-run','source':'db','question_count':len(qs),'would_connect':False}))
        return 0
    nodes,edges=load_csv(args.csv_dir) if args.source=='csv' else load_db()
    rows=evaluate(qs,nodes,edges,args.seed_mode,args.hops,args.seed_count,args.seed_threshold)
    out=safe_output(args.output); summary=safe_output(args.summary); out.parent.mkdir(parents=True,exist_ok=True); summary.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    bytype={t:aggregate([r['metrics'] for r in rows if r['type']==t]) for t in sorted({r['type'] for r in rows})}
    all_metrics=[r['metrics'] for r in rows]
    amb=[m for m in all_metrics if m['ambiguous_question']]
    unamb=[m for m in all_metrics if not m['ambiguous_question']]
    overall=aggregate(all_metrics)
    overall['ambiguous_question_rate']=len(amb)/len(all_metrics) if all_metrics else 0
    overall['ambiguous_recall']=aggregate(amb)['expected_node_recall'] if amb else 0
    overall['unambiguous_recall']=aggregate(unamb)['expected_node_recall'] if unamb else 0
    overall['ambiguous_recall_difference']=(overall['ambiguous_recall']-overall['unambiguous_recall']) if amb and unamb else None
    result={'overall':overall,'by_type':bytype,'seed_mode':args.seed_mode,'hops':args.hops}
    summary.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('id\ttype\tseed_hit\texpected_recall\tfull\tnodes\tedges\ttruncated\tsource\tseconds')
    for r in rows:
        m=r['metrics']; print(f"{r['id']}\t{r['type']}\t{m['seed_hits']}/{m['seed_expected']}\t{m['expected_node_recall']:.3f}\t{m['full_recall']}\t{m['nodes']}\t{m['edges']}\t{m['truncated']}\t{m['source_display']}\t{m['elapsed_seconds']:.4f}")
    print(json.dumps(result,ensure_ascii=False))
    return 0

def load_db(schema='fp_chat'):
    # Opt-in only. Imports the team's db module only (read-only run_query); rag/llm are NOT imported,
    # so no LLM package or API key is needed for this retrieval-only evaluation.
    import re
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',schema): raise ValueError('invalid schema')
    db=__import__('db')
    db.SCHEMA=schema; db.NODES=f'{schema}.nodes'; db.EDGES=f'{schema}.edges'
    nodes=db.run_query(f'select id::text as id,name,label,props from {db.NODES}')
    edges=db.run_query(f'select source::text as source,target::text as target,type from {db.EDGES}')
    return [dict(r) for r in nodes], [dict(r) for r in edges]

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('questions',nargs='?'); p.add_argument('--make-questions',action='store_true'); p.add_argument('--hana',default='/tmp/fp-check-hana'); p.add_argument('--woori',default='/tmp/fp-check-woori'); p.add_argument('--source',choices=['csv','db'],default='csv'); p.add_argument('--csv-dir',action='append',default=[]); p.add_argument('--seed-mode',choices=['contains','fuzzy','oracle'],default='contains'); p.add_argument('--seed-count',type=int,default=3); p.add_argument('--seed-threshold',type=float,default=0.15); p.add_argument('--hops',type=int,choices=[1,2,3],default=2); p.add_argument('--execute',action='store_true'); p.add_argument('--output',default='/tmp/fp-retrieval.jsonl'); p.add_argument('--summary',default='/tmp/fp-retrieval-summary.json'); a=p.parse_args(argv)
    if a.make_questions:
        from eval.eval_questions import write_questions
        questions,_=write_questions([a.hana,a.woori],'/tmp/fp-retrieval-questions.json',per_type=10)
        print(json.dumps({'output':'/tmp/fp-retrieval-questions.json','count':len(questions),'by_type':{t:sum(q['type']==t for q in questions) for t in sorted({q['type'] for q in questions})}})); return 0
    if not a.questions: p.error('questions JSON is required')
    if a.source=='csv' and not a.csv_dir: a.csv_dir=[a.hana,a.woori]
    return run_retrieval(a)
if __name__=='__main__': raise SystemExit(main())
