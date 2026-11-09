from pathlib import Path
import re, zipfile, xml.etree.ElementTree as ET
import fitz

root = Path(__file__).resolve().parents[1]
source = root / 'src/card_benefit/docs/presentation/카드혜택_GraphRAG_최종_활용방안_AI협업회고_18장.pptx'
output = source.with_name('카드혜택_GraphRAG_최종_18장_LangGraph수정.pptx')
svg = (root / 'artifacts/langgraph_slide.svg').read_text(encoding='utf8')
svg = svg.replace('#f7faf8', '#f1eeea').replace('font-size="23"', 'font-size="25"').replace('font-size="19"', 'font-size="22"')
svg = svg.replace('<text x="310" y="716"', '<path d="M513 457 L525 465 L513 473 Z M938 457 L950 465 L938 473 Z M1448 457 L1460 465 L1448 473 Z" fill="#245b4b"/><path d="M1617 597 L1625 585 L1633 597 Z" fill="#bd8254"/><text x="310" y="716"')
svg = svg.replace('M685 585V645H1625', 'M685 585V645H1575V585').replace('<text x="310" y="716"', '<path d="M1567 597 L1575 585 L1583 597 Z" fill="#bd8254"/><text x="310" y="716"')
doc = fitz.open(stream=svg.encode('utf8'), filetype='svg')
png = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes('png')
(root / 'artifacts/langgraph_16_slide.png').write_bytes(png)
P='http://schemas.openxmlformats.org/presentationml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL='http://schemas.openxmlformats.org/package/2006/relationships'
for prefix,uri in [('p',P),('a',A),('r',R)]: ET.register_namespace(prefix,uri)
ET.register_namespace('',REL)
with zipfile.ZipFile(source) as src:
    pres=ET.fromstring(src.read('ppt/presentation.xml'))
    assert len(pres.find(f'{{{P}}}sldIdLst')) == 18
    dims=pres.find(f'{{{P}}}sldSz'); cx,cy=dims.attrib['cx'],dims.attrib['cy']
    slide=ET.fromstring(src.read('ppt/slides/slide16.xml'))
    tree=slide.find(f'{{{P}}}cSld/{{{P}}}spTree')
    for child in list(tree):
        if child.tag not in (f'{{{P}}}nvGrpSpPr',f'{{{P}}}grpSpPr'): tree.remove(child)
    pic=ET.fromstring(f'''<p:pic xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:nvPicPr><p:cNvPr id="1000" name="LangGraph 실행 구조"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rIdLangGraph"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>''')
    tree.append(pic)
    rels=ET.fromstring(src.read('ppt/slides/_rels/slide16.xml.rels'))
    ET.SubElement(rels,f'{{{REL}}}Relationship',{'Id':'rIdLangGraph','Type':R+'/image','Target':'../media/langgraph_slide16.png'})
    with zipfile.ZipFile(output,'w') as out:
        for item in src.infolist():
            data=src.read(item.filename)
            if item.filename=='ppt/slides/slide16.xml': data=ET.tostring(slide,encoding='utf-8',xml_declaration=True)
            if item.filename=='ppt/slides/_rels/slide16.xml.rels': data=ET.tostring(rels,encoding='utf-8',xml_declaration=True)
            out.writestr(item,data)
        out.writestr('ppt/media/langgraph_slide16.png',png,compress_type=zipfile.ZIP_DEFLATED)
print(output)
