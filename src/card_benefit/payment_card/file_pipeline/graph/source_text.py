"""Attach evidence-backed source excerpts to Benefit nodes in graph CSVs."""
from __future__ import annotations
import argparse, csv, json, re, shutil, statistics, sys
from collections import Counter, defaultdict
from pathlib import Path

from .export import CSV_COLUMNS

ROOT = Path(__file__).resolve().parents[5]
EDGE_TYPES = {"HAS_CONDITION", "HAS_LIMIT", "APPLIES_TO", "EXCLUDES"}
TABLES = ("fp_nodes", "fp_edges", "fp_evidence", "fp_load_runs")
HANA03_ID = "01c44066b8df1688-p0001-c01:b1"

def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
def write_csv(path, table, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        w=csv.DictWriter(f, fieldnames=CSV_COLUMNS[table]); w.writeheader(); w.writerows(rows)
def pdf_path(doc, index):
    fp=Path(doc.get("file_path", ""))
    if fp.is_absolute(): return fp
    candidates=[ROOT/"src/data"/fp, ROOT/"src/card_benefit/data"/fp, ROOT/"src/card_benefit/data/raw"/fp, index.parent.parent/fp, index.parent/fp]
    return next((p for p in candidates if p.is_file()), candidates[0])
def normalize(s): return " ".join(s.split())
def extract_text(page, start, end, margin_lines):
    text=page.get_text(); a=start-1; b=end
    if a<0 or b>len(text) or a>=b: raise ValueError("invalid_slice")
    lo=a; hi=b
    for _ in range(margin_lines):
        n=text.rfind("\n",0,lo)
        if n<0: lo=0; break
        lo=n+1
    for _ in range(margin_lines):
        n=text.find("\n",hi)
        if n<0: hi=len(text); break
        hi=n
    return normalize(text[lo:hi])
def centered_cut(s, limit):
    if len(s)<=limit: return s,False
    if limit<=1: return "…"[:limit],True
    budget=limit-2
    start=max(0,(len(s)-budget)//2)
    return "…"+s[start:start+budget]+"…",True

def merge_windows(windows):
    merged=[]
    for start,end in sorted(windows):
        if merged and start<=merged[-1][1]: merged[-1]=(merged[-1][0],max(merged[-1][1],end))
        else: merged.append((start,end))
    return merged

def _render_page_windows(page_text, page_no, windows):
    pieces=[]; cursor=0
    for start,end in windows:
        if start>cursor: pieces.append(" … ")
        pieces.append(page_text[start:end]); cursor=end
    return f"(p.{page_no}) "+"".join(pieces)

def anchored_cut(page_texts, limits, conditions, benefit_positions, limit, margin_before=80, margin_after=80):
    """Keep Limit evidence windows first, then spend requirements and benefit evidence."""
    if not any(limits) and not any(conditions):
        whole=normalize(" ".join(f"(p.{p}) {t}" for p,t in page_texts))
        return (whole,False) if len(whole)<=limit else (whole[:limit-1]+"…",True)
    texts={}; labels={}
    for item in page_texts:
        if len(item)==3: key,page_no,text=item
        else: key,text=item; page_no=key
        texts[key]=text; labels[key]=page_no
    # Positions are 1-based inclusive; window offsets are 0-based half-open.
    anchor={p:[] for p in texts}
    for group in limits:
        for p,start,end in group:
            if p in texts: anchor[p].append((max(0,start-1-margin_before),min(len(texts[p]),end+margin_after)))
    selected={p:merge_windows(w) for p,w in anchor.items()}
    def value():
        return normalize(" ".join(_render_page_windows(texts[p],labels[p],selected[p]) for p in texts if selected[p]))
    # If expanded windows do not fit, preserve evidence spans and reduce margins.
    if len(value())>limit:
        selected={p:merge_windows((max(0,s-1),min(len(texts[p]),e)) for q,s,e in [item for grp in limits for item in grp] if q==p) for p in texts}
    # Add each SPEND_REQ window only when it fits the shared page-independent cap.
    for p,start,end in conditions:
        if p not in texts: continue
        candidate=merge_windows([*selected[p],(max(0,start-1-margin_before),min(len(texts[p]),end+margin_after))])
        old=selected[p]; selected[p]=candidate
        if len(value())>limit: selected[p]=old
    # Fill remaining budget from the beginning of the Benefit evidence window.
    for p,start,end in benefit_positions:
        if p not in texts: continue
        win=(max(0,start-1-margin_before),min(len(texts[p]),end+margin_after))
        old=selected[p]; selected[p]=merge_windows([*old,win])
        if len(value())>limit:
            selected[p]=old
    # Add benefit evidence from its leading edge, using only remaining space.
    for p,start,end in benefit_positions:
        if p not in texts: continue
        begin=max(0,start-1-margin_before)
        available=max(0,limit-len(value())-8)
        if available:
            selected[p]=merge_windows([*selected[p],(begin,min(len(texts[p]),begin+available))])
        if len(value())>limit: selected[p]=merge_windows([w for w in selected[p] if w!=(begin,min(len(texts[p]),begin+available))])
    result=value()
    if len(result)>limit:
        result=result[:max(0,limit-3)]+" … "
    full=normalize(" ".join(f"(p.{labels[p]}) {t}" for p,t in texts.items()))
    return result,len(full)>len(result)

def _money_values(text):
    pattern=re.compile(r"(?<!\d)(?:(\d+(?:\.\d+)?)\s*만\s*(?:(\d+(?:\.\d+)?)\s*천)?\s*원?|([\d,]+(?:\.\d+)?)\s*천\s*원|([\d,]+(?:\.\d+)?)\s*원)")
    values=set()
    for match in pattern.finditer(text):
        ten_thousands,thousands,thousand_won,won=match.groups()
        if ten_thousands:
            value=float(ten_thousands.replace(",",""))*10000
            if thousands: value+=float(thousands.replace(",",""))*1000
        elif thousand_won: value=float(thousand_won.replace(",",""))*1000
        else: value=float(won.replace(",",""))
        values.add(round(value))
    return values

def _amount_in_text(amount,text,money_values):
    value=round(float(amount))
    if value>99: return value in money_values
    return re.search(r"(?<!\d)"+str(value)+r"(?!\d)",text) is not None

def _quality_report(nodes,edges,attached_lengths,max_chars,truncated):
    byid={n["id"]:n for n in nodes}; limits=defaultdict(list)
    for edge in edges:
        if edge["edge_type"]!="HAS_LIMIT" or edge["source_id"] not in byid or edge["target_id"] not in byid: continue
        try: amount=json.loads(byid[edge["target_id"]]["props"] or "{}").get("amount")
        except (TypeError,ValueError): amount=None
        if amount in (None,0,"0"): continue
        try: limits[edge["source_id"]].append(round(float(amount)))
        except (TypeError,ValueError): continue
    cohorts=[]
    for benefit_id,amounts in limits.items():
        distinct=sorted(set(amounts))
        if len(distinct)<2: continue
        props=json.loads(byid[benefit_id]["props"] or "{}")
        source=props.get("source_text","")
        money=_money_values(source)
        complete=all(_amount_in_text(amount,source,money) for amount in distinct)
        cohorts.append((benefit_id,distinct,complete))
    hana_props=json.loads(byid[HANA03_ID]["props"] or "{}") if HANA03_ID in byid else {}
    hana_source=hana_props.get("source_text","")
    mean=round(statistics.mean(attached_lengths),1) if attached_lengths else 0
    return {
        "amount_coverage": {"rule":"Benefit에 연결된 Limit amount 중 0/None을 제외하고, 서로 다른 정수 amount가 2개 이상인 Benefit만 분모로 함. 쉼표와 원/천원/만원/만 N천원 표기를 정규화하고 100 미만 값은 숫자 경계 일치로 판정.","eligible_benefits":len(cohorts),"all_amounts_present":sum(ok for _,_,ok in cohorts),"ratio":round(sum(ok for _,_,ok in cohorts)/len(cohorts),4) if cohorts else None,"target_ratio":{"hana":0.90,"woori":0.85},"failed_benefit_ids":[bid for bid,_,ok in cohorts if not ok]},
        "truncation":{"count":truncated,"attached_benefits":len(attached_lengths),"ratio":round(truncated/len(attached_lengths),4) if attached_lengths else 0},
        "hana_03":{"benefit_id":HANA03_ID,"present":{"12,000원":"12,000" in hana_source,"19,000원":"19,000" in hana_source,"30만원 이상":"30만원 이상" in hana_source,"100만원 이상":"100만원 이상" in hana_source},"length_chars":len(hana_source)},
        "context_estimate":{"max_chars_per_node":max_chars,"node_count":40,"max_sum_chars":max_chars*40,"average_source_text_chars":mean,"average_sum_chars_for_40_nodes":round(mean*40,1)},
        "previous_reference":{"hana":"81/88 (about 92%)","woori":"73/88 (about 83%)"}
    }

def build(csv_dir, issuer, documents, output_dir, max_chars=700, margin_lines=1, run_id_suffix="", margin_before=80, margin_after=80, trace_dir=None):
    import fitz
    csv_dir=Path(csv_dir).resolve(); out=Path(output_dir).expanduser().resolve()
    if ROOT==out or ROOT in out.parents or Path("/tmp").resolve() not in out.parents: raise ValueError("출력은 저장소 밖 /tmp 아래만 허용됩니다.")
    if not 400<=max_chars<=1200 or margin_lines<0 or margin_before<0 or margin_after<0: raise ValueError("invalid limits")
    nodes=read_csv(csv_dir/"fp_nodes.csv"); edges=read_csv(csv_dir/"fp_edges.csv"); evs=read_csv(csv_dir/"fp_evidence.csv"); runs=read_csv(csv_dir/"fp_load_runs.csv")
    docs={r["sha256"]:r for r in read_csv(documents) if r.get("canonical", "Y").upper()=="Y"}
    trace_docs={}
    if trace_dir is not None:
        trace_root=Path(trace_dir).expanduser()
        for trace_path in (trace_root/issuer).glob("*.json"):
            try:
                trace_data=json.loads(trace_path.read_text(encoding="utf-8"))
                document=trace_data.get("document",{})
                trace_sha=document.get("sha256") or document.get("doc_sha256") or trace_data.get("doc_sha256")
                if trace_sha: trace_docs[trace_sha]=trace_data
            except (OSError,ValueError,AttributeError): continue
    byid={n["id"]:n for n in nodes}; edgeby={e["id"]:e for e in edges}; evidence=defaultdict(list)
    for ev in evs:
        if ev["quote_status"]!="located": continue
        ids=[ev["node_id"]] if ev["node_id"] else ([edgeby[ev["edge_id"]][k] for k in ("source_id","target_id")] if ev["edge_id"] in edgeby else [])
        for nid in ids: evidence[nid].append(ev)
    related=defaultdict(set)
    for e in edges:
        if e["edge_type"] not in EDGE_TYPES: continue
        s,t=e["source_id"],e["target_id"]
        if byid.get(s,{}).get("node_type")=="Benefit": related[s].add(t)
        if byid.get(t,{}).get("node_type")=="Benefit": related[t].add(s)
    reason=Counter(); source_counts=Counter(); lengths=[]; truncated=0; spill=0; attached=0
    for b in (n for n in nodes if n["node_type"]=="Benefit"):
        props=json.loads(b["props"] or "{}")
        if any(k in props for k in ("source_text","source_text_pages","source_text_truncated")): raise ValueError("source_text property collision")
        relevant=[b["id"],*related[b["id"]]]
        positions=[]
        for nid in relevant:
            positions.extend(evidence[nid])
        if not positions:
            statuses=[x["quote_status"] for nid in relevant for x in evs if x["node_id"]==nid]
            failure="ambiguous" if "ambiguous" in statuses else "missing"
            reason[failure]+=1; source_counts[f"unattached:{failure}"]+=1; continue
        grouped=defaultdict(list)
        for x in positions: grouped[(x["doc_sha256"],int(x["page_no"]))].append(x)
        pages=[]; fallback_pages=[]; failures=[]; used_sources=set(); limit_groups=[]; condition_positions=[]; benefit_positions=[]
        limit_ids={nid for nid in related[b['id']] if byid.get(nid,{}).get('node_type')=='Limit'}
        condition_ids={nid for nid in related[b['id']] if byid.get(nid,{}).get('node_type')=='Condition' and json.loads(byid[nid]['props'] or '{}').get('kind')=='SPEND_REQ'}
        limit_evidence=[x for nid in limit_ids for x in evidence[nid]]
        condition_evidence=[x for nid in condition_ids for x in evidence[nid]]
        benefit_evidence=evidence[b['id']]
        for (sha,page_no), group in sorted(grouped.items(), key=lambda z:(z[0][0],z[0][1])):
            doc=docs.get(sha)
            if not doc: failures.append("document_missing"); continue
            pp=pdf_path(doc,Path(documents))
            try:
                with fitz.open(pp) as pdf:
                    start=min(int(x["start_pos"]) for x in group); end=max(int(x["end_pos"]) for x in group)
                    pdf_page=pdf[page_no-1] if page_no<=len(pdf) else None
                    page_text=pdf_page.get_text() if pdf_page is not None else ""
                    trace_text=None
                    trace_data=trace_docs.get(sha)
                    if trace_data:
                        trace_pages=trace_data.get("pages",[])
                        trace_page=next((p for p in trace_pages if int(p.get("page_no",0))==page_no),None)
                        if trace_page is not None: trace_text=trace_page.get("text","")
                    use_trace=trace_text is not None and (not page_text or end>len(page_text) or page_text!=trace_text)
                    if use_trace:
                        page_text=trace_text
                        trace_page_obj=type("TracePage",(),{"get_text":lambda self:page_text})()
                        snippet=extract_text(trace_page_obj,start,end,margin_lines)
                        used_sources.add("trace")
                    else:
                        if pdf_page is None: raise ValueError("page_missing")
                        snippet=extract_text(pdf_page,start,end,margin_lines)
                        used_sources.add("pdf")
                page_key=(sha,page_no)
                pages.append((page_key,page_no,page_text))
                fallback_pages.append((page_no,snippet))
                limit_rows=[x for x in limit_evidence if x['doc_sha256']==sha and int(x['page_no'])==page_no]
                if limit_rows: limit_groups.append([(page_key,int(x['start_pos']),int(x['end_pos'])) for x in limit_rows])
                condition_positions.extend((page_key,int(x['start_pos']),int(x['end_pos'])) for x in condition_evidence if x['doc_sha256']==sha and int(x['page_no'])==page_no)
                benefit_positions.extend((page_key,int(x['start_pos']),int(x['end_pos'])) for x in benefit_evidence if x['doc_sha256']==sha and int(x['page_no'])==page_no)
            except Exception: failures.append("pdf_unreadable")
        if not pages:
            failure=failures[0] if failures else "pdf_unreadable"
            reason[failure]+=1; source_counts[f"unattached:{failure}"]+=1; continue
        if len(pages)>1: spill+=1
        if len(pages)>3: pages=pages[:3]
        if len(pages)>3: pages=pages[:3]
        if limit_evidence or condition_evidence:
            value,cut=anchored_cut(pages,limit_groups,condition_positions,benefit_positions,max_chars,margin_before,margin_after)
        else:
            value=normalize(" ".join(f"(p.{p}) {s}" for p,s in fallback_pages[:3]))
            value,cut=(value,False) if len(value)<=max_chars else (value[:max_chars-1]+"…",True)
        truncated+=cut
        props.update(source_text=value,source_text_pages=",".join(str(item[1]) for item in pages),source_text_truncated=cut)
        source_counts["trace" if "trace" in used_sources else "pdf"]+=1
        b["props"]=json.dumps(props,ensure_ascii=False,separators=(",",":")); attached+=1; lengths.append(len(value))
    out.mkdir(parents=True,exist_ok=True)
    for table,rows in (("fp_nodes",nodes),("fp_edges",edges),("fp_evidence",evs),("fp_load_runs",runs)):
        if table in {"fp_edges", "fp_evidence"} and not run_id_suffix:
            shutil.copy2(csv_dir/f"{table}.csv",out/f"{table}.csv")
            continue
        for row in rows:
            if run_id_suffix and "run_id" in row: row["run_id"]+=run_id_suffix
        write_csv(out/f"{table}.csv",table,rows)
    p=lambda q: round(statistics.quantiles(lengths,n=100,method="inclusive")[q-1]) if len(lengths)>=2 else (lengths[0] if lengths else 0)
    report={"issuer":issuer,"benefits":sum(n["node_type"]=="Benefit" for n in nodes),"attached":attached,"unattached_by_reason":dict(reason),"source_counts":{"pdf":source_counts["pdf"],"trace":source_counts["trace"],"unattached":{k.removeprefix("unattached:"):v for k,v in source_counts.items() if k.startswith("unattached:")}},"length_chars":{"p50":p(50),"p90":p(90),"max":max(lengths,default=0)},"truncated":truncated,"multi_page":spill}
    report.update(_quality_report(nodes,edges,lengths,max_chars,truncated))
    (out/"source_text_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--csv-dir",required=True); p.add_argument("--issuer",required=True); p.add_argument("--documents",required=True); p.add_argument("--output-dir",required=True); p.add_argument("--max-chars",type=int,default=700); p.add_argument("--margin-lines",type=int,default=1); p.add_argument("--margin-before",type=int,default=80); p.add_argument("--margin-after",type=int,default=80); p.add_argument("--run-id-suffix",default=""); p.add_argument("--trace-dir")
    args=list(sys.argv[1:] if argv is None else argv)
    if "--run-id-suffix" in args:
        i=args.index("--run-id-suffix")
        if i+1<len(args) and args[i+1].startswith("-"):
            args[i]="--run-id-suffix="+args[i+1]; del args[i+1]
    a=p.parse_args(args); print(json.dumps(build(a.csv_dir,a.issuer,a.documents,a.output_dir,a.max_chars,a.margin_lines,a.run_id_suffix,a.margin_before,a.margin_after,a.trace_dir),ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
