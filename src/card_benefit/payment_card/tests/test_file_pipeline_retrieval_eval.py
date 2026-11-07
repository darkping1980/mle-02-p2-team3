import importlib.util
import json
from pathlib import Path

CHAT = Path(__file__).resolve().parents[1] / "file_pipeline" / "chat"
def load(name):
    spec = importlib.util.spec_from_file_location(name, next((p for p in (next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py"), CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py", CHAT / "retrieval" / f"{name}.py", CHAT / "answer" / f"{name}.py") if p.exists()), next((p for p in (CHAT / f"{name}.py", CHAT / "eval" / f"{name}.py", CHAT / "review" / f"{name}.py") if p.exists()), CHAT / f"{name}.py")))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

reval = load("retrieval_eval")


def graph():
    nodes = [
        {"id": str(i), "name": n, "label": l, "props": p}
        for i, n, l, p in [(1,"Card One","Card",{}),(2,"Benefit Two","Benefit",{}),(3,"Target Three","Target",{}),(4,"문서 abcdef12","Document",{"summary":"x"})]
    ]
    edges = [{"source":"1","target":"2","type":"OFFERS"},{"source":"2","target":"3","type":"APPLIES_TO"},{"source":"3","target":"4","type":"SUPPORTED_BY"}]
    return nodes, edges


def test_deterministic_seed_modes_duplicates_and_hops():
    nodes, edges = graph(); nodes.append({"id":"5","name":"Card One","label":"Card","props":{}})
    q = {"question":"Card One Benefit Two", "seed_entities":["Benefit Two"]}
    assert reval.select_seeds(nodes,q,"contains",3)==["Benefit Two","Card One"]
    assert reval.select_seeds(nodes,q,"oracle",3)==["Benefit Two"]
    sub = reval.traverse(nodes,edges,["Card One"],1,40)
    assert len(sub["seeds"])==2 and {n["id"] for n in sub["nodes"]}=={"1","2","5"}
    assert len(reval.traverse(nodes,edges,["Card One"],2,40)["nodes"])==4


def test_metrics_and_truncation():
    nodes, edges = graph()
    sub = reval.traverse(nodes,edges,["Card One"],2,2)
    assert sub["truncated"]
    m = reval.question_metrics({"expected":["Benefit Two","absent"],"expected_node_names":["Card One","Benefit Two"]},sub,1.0,40)
    assert m["expected_node_recall"]==0.5 and m["full_recall"]==0 and m["source_display"]==0


def test_output_repo_guard():
    try: reval.safe_output(Path(__file__).resolve())
    except ValueError: pass
    else: assert False


def test_run_eval_retrieval_path():
    run = load("run_eval")
    assert "retrieval" in run.__doc__ or callable(getattr(run,"run_retrieval",None))


def test_csv_document_derivation_and_three_doc_cap(tmp_path):
    import csv
    folder=tmp_path/'csv'; folder.mkdir()
    def put(name,cols,rows):
        with (folder/name).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(rows)
    put('fp_nodes.csv',['id','node_type','props'],[{'id':'n','node_type':'Benefit','props':json.dumps({'name':' Benefit   Name ','amount':3})}])
    put('fp_edges.csv',['id','source_id','target_id','edge_type'],[])
    put('fp_evidence.csv',['node_id','edge_id','doc_sha256','quote_status','page_no'],[{'node_id':'n','edge_id':'','doc_sha256':str(i)*64,'quote_status':'located' if i==2 else 'missing','page_no':1} for i in range(1,6)])
    nodes,edges=reval.load_csv([folder])
    assert nodes[0]['name']=='Benefit Name' and len([e for e in edges if e['type']=='SUPPORTED_BY'])==3
    assert all(nodes[0]['id']==e['source'] for e in edges)


def test_openai_adapter_fake_client_and_cost_estimate(monkeypatch,capsys):
    import sys, types
    calls=[]
    class C:
        def create(self,**kw):
            calls.append(kw)
            if kw.get('stream'): return [types.SimpleNamespace(choices=[types.SimpleNamespace(delta=types.SimpleNamespace(content='chunk'))])]
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='ok'))])
    fake=types.SimpleNamespace(chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=C().create)))
    monkeypatch.setitem(sys.modules,'llm',types.SimpleNamespace(complete=None,stream=None))
    patch=load('openai_llm_patch'); llm=patch.apply(client=fake)
    assert llm.complete('sys','user')=='ok'
    assert list(llm.stream('sys',[{'role':'user','content':'q'}]))==['chunk']
    assert calls[0]['model']=='gpt-6-luna' and 'temperature' not in calls[0]
    assert patch.estimate(60)['label']=='estimate'
    assert 'api_key' not in capsys.readouterr().out


def test_load_db_does_not_import_rag_or_llm(monkeypatch):
    """LLM 없는 시험이므로 anthropic 을 가져오는 rag/llm 모듈을 불러오면 안 된다."""
    import sys, types
    from payment_card.file_pipeline.chat.eval import retrieval_eval
    calls = []
    fake = types.SimpleNamespace(run_query=lambda q, p=None: calls.append(q) or [])
    monkeypatch.setitem(sys.modules, "db", fake)
    for name in ("rag", "llm"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    nodes, edges = retrieval_eval.load_db()
    assert (nodes, edges) == ([], [])
    assert fake.NODES == "fp_chat.nodes" and fake.EDGES == "fp_chat.edges"
    assert "rag" not in sys.modules and "llm" not in sys.modules
    assert all("select" in q and "fp_chat." in q for q in calls) and len(calls) == 2
