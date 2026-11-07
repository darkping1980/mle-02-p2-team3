import importlib.util,csv,json
from pathlib import Path
CHAT=Path(__file__).resolve().parents[1]/'file_pipeline'/'chat'
spec=importlib.util.spec_from_file_location('review_sheet_test',CHAT / 'review' / 'review_sheet.py');rs=importlib.util.module_from_spec(spec);spec.loader.exec_module(rs)
def wr(p,rows):
 with p.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def test_collects_direct_and_edge_dedup_limits_and_view_mapping(tmp_path):
 d=tmp_path/'fp-check-hana';d.mkdir();sha='a'*64
 wr(d/'fp_nodes.csv',[{'id':'n1','node_type':'Benefit','props':'{"name":"<script>"}'},{'id':'n2','node_type':'Limit','props':'{"amount":3}'}])
 wr(d/'fp_edges.csv',[{'id':'e','source_id':'n1','target_id':'n2','edge_type':'HAS_LIMIT'}])
 wr(d/'fp_evidence.csv',[{'node_id':'n1','edge_id':'','doc_sha256':sha,'page_no':'1','start_pos':'2','end_pos':'4','quote_status':'located'},{'node_id':'','edge_id':'e','doc_sha256':sha,'page_no':'1','start_pos':'2','end_pos':'4','quote_status':'located'}])
 nodes,edges,ev,docs=rs.load_sources([d],[]); rec={'retrieved_node_ids':[rs.uuidish('n1')]};found,more,_=rs.collect_evidence(rec,nodes,edges,ev,docs,[],limit=1)
 assert len(found)==1 and more==1 and found[0]['node_name']=='<script>' and found[0]['pdf_link'].startswith('file:///')
def test_excerpt_one_based_inclusive_and_html_escape(tmp_path,monkeypatch):
 class Page:
  def get_text(self):return 'abcdef'
 class Doc:
  def __enter__(self):return self
  def __exit__(self,*x):pass
  def __len__(self):return 1
  def __getitem__(self,i):return Page()
 import fitz;monkeypatch.setattr(fitz,'open',lambda p:Doc())
 d=tmp_path/'fp-check-hana';d.mkdir();sha='b'*64
 wr(d/'fp_nodes.csv',[{'id':'n','node_type':'Benefit','props':'{"name":"<script>alert(1)</script>"}'}]);wr(d/'fp_edges.csv',[{'id':'e','source_id':'n','target_id':'n','edge_type':'X'}]);wr(d/'fp_evidence.csv',[{'node_id':'n','edge_id':'','doc_sha256':sha,'page_no':'1','start_pos':'2','end_pos':'4','quote_status':'located'}])
 doc=tmp_path/'documents.csv';wr(doc,[{'sha256':sha,'file_path':'fake.pdf'}]);q=tmp_path/'q.json';q.write_text(json.dumps({'questions':[{'id':'q','question':'synth','expected':[],'no_answer':True,'issuer':'hana'}]}));r=tmp_path/'r.jsonl';r.write_text(json.dumps({'id':'q','answer':'모르겠습니다','refusal':True,'retrieved_node_ids':[rs.uuidish('n')],'selected_seed_names':[]})+'\n');out=tmp_path/'out.html'
 (tmp_path/'fake.pdf').write_bytes(b'synthetic')
 rs.make_sheet(r,q,[d],[doc],out,with_excerpt=True);text=out.read_text();assert 'bcd' in text and '&lt;script&gt;' in text and '<script>alert' not in text and '정답없음 거절' in text
