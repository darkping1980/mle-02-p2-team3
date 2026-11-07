import csv
import hashlib
import json
from pathlib import Path
import fitz
import pytest
from payment_card.file_pipeline.graph import source_text
from payment_card.file_pipeline.graph.load import validate_csvs
from payment_card.file_pipeline.graph.export import CSV_COLUMNS

def setup_case(tmp_path, located=True):
    source=tmp_path/'input'; source.mkdir(); pdfpath=tmp_path/'synthetic.pdf'
    pdf=fitz.open(); page=pdf.new_page(); page.insert_text((72,72),'혜택 안내\n월 12,000원 할인\n월 19,000원 할인\n'); pdf.save(pdfpath); pdf.close()
    sha=hashlib.sha256(b'doc').hexdigest(); docs=tmp_path/'documents.csv'
    with docs.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['sha256','file_path','canonical']); w.writeheader(); w.writerow({'sha256':sha,'file_path':str(pdfpath),'canonical':'Y'})
    nodes=[{'id':'b','node_type':'Benefit','props':'{"name":"test"}','chunk_id':'c','run_id':'r'}, {'id':'l','node_type':'Limit','props':'{}','chunk_id':'c','run_id':'r'}]
    edges=[{'id':'e','source_id':'b','target_id':'l','edge_type':'HAS_LIMIT','run_id':'r'}]
    ev=[{'node_id':'b','edge_id':'','doc_sha256':sha,'page_no':'1','start_pos':'1','end_pos':'12','quote_status':'located' if located else 'missing'}, {'node_id':'l','edge_id':'','doc_sha256':sha,'page_no':'1','start_pos':'14','end_pos':'29','quote_status':'located' if located else 'missing'}]
    runs=[{'run_id':'r','input_folder_name':'x','model_name':'','started_at':'','node_count':'2','edge_count':'1'}]
    for name,rows in [('fp_nodes',nodes),('fp_edges',edges),('fp_evidence',ev),('fp_load_runs',runs)]:
        with (source/f'{name}.csv').open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=CSV_COLUMNS[name]); w.writeheader(); w.writerows(rows)
    return source,docs

def test_build_attaches_and_validates_with_suffix(tmp_path):
    source,docs=setup_case(tmp_path); out=tmp_path/'result'
    report=source_text.build(source,'hana',docs,out,run_id_suffix='-st')
    assert report['attached']==1
    props=json.loads(next(r for r in source_text.read_csv(out/'fp_nodes.csv') if r['id']=='b')['props'])
    assert props['name']=='test' and '12,000' in props['source_text'] and '19,000' in props['source_text']
    assert props['source_text_pages']=='1' and props['source_text_truncated'] is False
    assert all(r['run_id']=='r-st' for table in ('fp_nodes','fp_edges','fp_load_runs') for r in source_text.read_csv(out/f'{table}.csv'))
    validate_csvs(out)
    assert source_text.read_csv(source/'fp_nodes.csv')[0]['run_id']=='r'

def test_missing_evidence_is_not_attached(tmp_path):
    source,docs=setup_case(tmp_path,located=False); out=tmp_path/'result'
    report=source_text.build(source,'hana',docs,out)
    assert report['attached']==0 and report['unattached_by_reason']['missing']==1

def test_property_collision_and_store_output_guard(tmp_path):
    source,docs=setup_case(tmp_path); rows=source_text.read_csv(source/'fp_nodes.csv'); rows[0]['props']='{"source_text":"old"}'
    source_text.write_csv(source/'fp_nodes.csv','fp_nodes',rows)
    with pytest.raises(ValueError,match='collision'): source_text.build(source,'hana',docs,tmp_path/'result')
    with pytest.raises(ValueError,match='/tmp'): source_text.build(source,'hana',docs,Path.cwd()/'bad-output')

def test_center_cut_and_slice_inclusive():
    assert source_text.centered_cut('가나다라마바사',5)==('…다라마…',True)
    page=type('P',(),{'get_text':lambda self:'앞\n중간 내용\n끝'})()
    assert source_text.extract_text(page,3,6,0)=='중간 내'

def test_anchor_windows_merge_and_keep_end_limit():
    assert source_text.merge_windows([(0,10),(9,20),(20,30)])==[(0,30)]
    text='앞'*500+'30만원 이상'+'중'*150+'월 12,000원'+'뒤'*500
    start=text.index('30만원 이상')+1; end=start+len('30만원 이상')-1
    start2=text.index('월 12,000원')+1; end2=start2+len('월 12,000원')-1
    value,cut=source_text.anchored_cut([(1,text)],[[(1,start,end),(1,start2,end2)]],[],[(1,1,10)],400,20,20)
    assert cut and len(value)<=400
    assert '30만원 이상' in value and '월 12,000원' in value
    assert ' … ' in value

def test_all_limit_windows_are_retained_when_separated():
    text='가'*700+'한도 12,000원'+'나'*700+'한도 19,000원'+'다'*700
    positions=[]
    for phrase in ('한도 12,000원','한도 19,000원'):
        start=text.index(phrase)+1; positions.append((1,start,start+len(phrase)-1))
    value,cut=source_text.anchored_cut([(1,text)],[positions],[],[],700,20,20)
    assert cut and len(value)<=700
    assert all(s in value for s in ('한도 12,000원','한도 19,000원'))

def test_secondary_condition_and_korean_safe_cut():
    text='x'*500+'실적 30만원 이상'+'y'*500+'월 한도 19,000원'+'z'*500
    limit=text.index('월 한도')+1
    cond=text.index('실적 30만원')+1
    value,cut=source_text.anchored_cut([(1,text)],[[(1,limit,limit+len('월 한도 19,000원')-1)]],[(1,cond,cond+len('실적 30만원 이상')-1)],[],400,15,15)
    assert cut and len(value)<=400
    assert '월 한도 19,000원' in value and '실적 30만원 이상' in value
    korean,was_cut=source_text.centered_cut('혜택가나다라마바사끝',8)
    assert was_cut and len(korean)==8 and '�' not in korean

def test_unanchored_benefit_uses_front_fallback_and_limits_validate(tmp_path):
    text='앞부분 혜택 내용 '+('뒷부분 '*200)
    value,cut=source_text.anchored_cut([(1,text)],[],[],[(1,1,8)],400)
    assert cut and len(value)<=400 and value.startswith('(p.1) 앞부분 혜택')
    source,docs=setup_case(tmp_path)
    with pytest.raises(ValueError,match='invalid limits'):
        source_text.build(source,'hana',docs,tmp_path/'too-short',max_chars=399)
