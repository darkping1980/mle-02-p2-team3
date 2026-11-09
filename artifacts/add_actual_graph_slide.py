from pathlib import Path
import base64, re, zipfile, xml.etree.ElementTree as E
import fitz

root=Path(__file__).resolve().parents[1]
srcpath=root/'src/card_benefit/docs/presentation/카드혜택_GraphRAG_최종_18장_LangGraph수정.pptx'
dstpath=srcpath.with_name('카드혜택_GraphRAG_최종_19장_실제LangGraph추가.pptx')
graph=(root/'artifacts/actual_graph.png').read_bytes()
im=fitz.Pixmap(graph); w=730*im.width/im.height; x=(1920-w)/2
embedded=base64.b64encode(graph).decode('ascii')
svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><rect width="1920" height="1080" fill="#f1eeea"/><g font-family="Malgun Gothic, sans-serif" fill="#174c3f"><text x="100" y="90" font-size="25">기술 구현 03</text><text x="100" y="158" font-size="50" font-weight="700">LangGraph 실제 실행 그래프</text><text x="100" y="205" font-size="25" fill="#5a786e">card_graphrag.py의 컴파일된 StateGraph에서 자동 추출</text><image x="{x}" y="225" width="{w}" height="730" href="data:image/png;base64,{embedded}"/><rect x="100" y="961" width="1720" height="67" rx="14" fill="#e0f3eb"/><text x="130" y="1005" font-size="25" font-weight="700">실제 등록된 노드와 조건부 Edge를 보여주는 그래프</text><text x="1740" y="1055" font-size="22" fill="#6a746e">17 / 19</text></g></svg>'''
d=fitz.open(stream=svg.encode(),filetype='svg'); pic=d[0].get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).tobytes('png')
P='http://schemas.openxmlformats.org/presentationml/2006/main'; A='http://schemas.openxmlformats.org/drawingml/2006/main'; R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'; REL='http://schemas.openxmlformats.org/package/2006/relationships'; CT='http://schemas.openxmlformats.org/package/2006/content-types'
for p,u in [('p',P),('a',A),('r',R)]: E.register_namespace(p,u)
with zipfile.ZipFile(srcpath) as src:
    present=E.fromstring(src.read('ppt/presentation.xml')); ids=present.find(f'{{{P}}}sldIdLst'); assert len(ids)==18
    dims=present.find(f'{{{P}}}sldSz').attrib
    new=E.Element(f'{{{P}}}sldId',{'id':str(max(int(n.attrib['id']) for n in ids)+1),f'{{{R}}}id':'rIdActualGraph'})
    ids.insert(16,new)
    prels=E.fromstring(src.read('ppt/_rels/presentation.xml.rels')); E.SubElement(prels,f'{{{REL}}}Relationship',{'Id':'rIdActualGraph','Type':R+'/slide','Target':'slides/slide19.xml'})
    cts=E.fromstring(src.read('[Content_Types].xml')); E.SubElement(cts,f'{{{CT}}}Override',{'PartName':'/ppt/slides/slide19.xml','ContentType':'application/vnd.openxmlformats-officedocument.presentationml.slide+xml'})
    slide=E.fromstring(src.read('ppt/slides/slide16.xml')); tree=slide.find(f'{{{P}}}cSld/{{{P}}}spTree')
    for el in list(tree):
        if el.tag not in (f'{{{P}}}nvGrpSpPr',f'{{{P}}}grpSpPr'): tree.remove(el)
    tree.append(E.fromstring(f'''<p:pic xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:nvPicPr><p:cNvPr id="1000" name="실제 Mermaid 그래프"/><p:cNvPicPr/><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rIdGraphImage"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{dims['cx']}" cy="{dims['cy']}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>'''))
    slide_rels=f'''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{REL}"><Relationship Id="rId1" Type="{R}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/><Relationship Id="rIdGraphImage" Type="{R}/image" Target="../media/actual_graph_slide17.png"/></Relationships>'''.encode()
    with zipfile.ZipFile(dstpath,'w') as dst:
        for item in src.infolist():
            name=item.filename; data=src.read(name)
            if name=='ppt/presentation.xml': data=E.tostring(present,encoding='utf-8',xml_declaration=True)
            elif name=='ppt/_rels/presentation.xml.rels':
                E.register_namespace('',REL); data=E.tostring(prels,encoding='utf-8',xml_declaration=True)
            elif name=='[Content_Types].xml':
                E.register_namespace('',CT); data=E.tostring(cts,encoding='utf-8',xml_declaration=True)
            else:
                m=re.fullmatch(r'ppt/slides/slide(\d+)\.xml',name)
                if m:
                    i=int(m.group(1)); newnum=i if i<16 else i+1
                    if i != 16: data=data.replace(f'{i:02d} / 18'.encode(),f'{newnum:02d} / 19'.encode())
                    if i == 2:
                        data=data.replace('12–16'.encode(), '12–17'.encode()).replace('17–18'.encode(), '18–19'.encode())
            dst.writestr(item,data)
        dst.writestr('ppt/slides/slide19.xml',E.tostring(slide,encoding='utf-8',xml_declaration=True),compress_type=zipfile.ZIP_DEFLATED)
        dst.writestr('ppt/slides/_rels/slide19.xml.rels',slide_rels,compress_type=zipfile.ZIP_DEFLATED)
        dst.writestr('ppt/media/actual_graph_slide17.png',pic,compress_type=zipfile.ZIP_DEFLATED)
print(dstpath)
