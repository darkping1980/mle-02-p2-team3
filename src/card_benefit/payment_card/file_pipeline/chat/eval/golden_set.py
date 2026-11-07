"""사람이 작성한 CSV 골든셋을 하네스 질문 JSON으로 변환한다."""
from __future__ import annotations
import argparse, csv, json, random, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
HEADERS = ['id','카드사','유형','질문','기대핵심사실1','기대핵심사실2','기대핵심사실3','근거문서','근거쪽','정답없음','이미지문서유래','문서가 있는 그래프','작성자','검수자','비고','시드엔티티']
TYPE_MAP = {'혜택조회':'card_benefits','조건':'benefit_condition','한도':'benefit_limit','제외':'benefit_excludes','숫자정확도':'benefit_limit','비교':'comparison','정답없음':'no_answer'}
ISSUERS = {'하나':'hana','우리':'woori'}
YESNO = {'예','아니오'}

def safe_output(path):
    p=Path(path).expanduser().resolve()
    if p == ROOT or ROOT in p.parents or Path('/tmp').resolve() not in p.parents: raise ValueError('출력은 저장소 밖 /tmp 아래만 허용됩니다.')
    return p

def load_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))

def convert(path, warning_output=None):
    rows=load_csv(path); issues=[]; warnings=[]; questions=[]
    for i,row in enumerate(rows, start=2):
        def err(message): issues.append(f'{i}행: {message}')
        for key in ('id','카드사','유형','질문','근거문서','근거쪽','정답없음','이미지문서유래','문서가 있는 그래프','작성자'):
            if not (row.get(key) or '').strip(): err(f'{key} 필수')
        if row.get('카드사') not in ISSUERS: err('카드사 값은 하나/우리여야 함')
        if row.get('유형') not in TYPE_MAP: err('유형 값이 허용 목록에 없음')
        if row.get('정답없음') not in YESNO: err('정답없음 값은 예/아니오여야 함')
        if row.get('이미지문서유래') not in YESNO: err('이미지문서유래 값은 예/아니오여야 함')
        if row.get('문서가 있는 그래프') not in ('우리','팀원','둘다'): err('문서가 있는 그래프 값이 허용 목록에 없음')
        facts=[(row.get(f'기대핵심사실{k}') or '').strip() for k in range(1,4)]
        if row.get('정답없음')=='예' and any(facts): err('정답없음=예이면 기대핵심사실은 비워야 함')
        if row.get('정답없음')=='아니오' and not any(facts): err('정답없음=아니오이면 기대핵심사실이 1개 이상 필요')
        if (row.get('근거쪽') or '').strip() and not (row['근거쪽'].strip().isdigit() and int(row['근거쪽'])>0): err('근거쪽은 양의 정수여야 함')
        if not (row.get('검수자') or '').strip(): warnings.append(f'{i}행: 검수자 비어 있음')
        if row.get('id','').strip(): questions.append((i,row,facts))
    counts=Counter((r.get('id') or '').strip() for _,r,_ in questions)
    for i,row,_ in questions:
        if counts[(row.get('id') or '').strip()]>1: issues.append(f'{i}행: id 중복 ({row.get("id","")})')
    if issues: raise ValueError('\n'.join(issues))
    out=[]
    for _,r,facts in questions:
        no=r['정답없음']=='예'
        out.append({'id':r['id'].strip(),'type':TYPE_MAP[r['유형']],'question':r['질문'].strip(),'seed_entities':[x.strip() for x in (r.get('시드엔티티') or '').split(';') if x.strip()], 'expected':[] if no else [x for x in facts if x], 'issuer':ISSUERS[r['카드사']], 'evidence_doc':(r.get('근거문서') or '').strip(), 'evidence_page':int(r['근거쪽']) if (r.get('근거쪽') or '').strip() else None,'no_answer':no,'from_image_doc':r['이미지문서유래']=='예','graph_coverage':r['문서가 있는 그래프'],'author':r['작성자'].strip(),'reviewer':(r.get('검수자') or '').strip()})
    if warning_output is not None: warning_output.extend(warnings)
    return out

def stratified_split(questions, ratio, seed):
    rng=random.Random(seed); groups=defaultdict(list)
    for q in questions: groups[(q['issuer'],q['type'])].append(q)
    dev=[]; final=[]
    for key,items in sorted(groups.items()):
        items=list(items); rng.shuffle(items); n=round(len(items)*ratio)
        dev.extend(items[:n]); final.extend(items[n:])
    return dev,final

def summary(rows, split):
    c=Counter((q['issuer'],q['type'],q['no_answer'],q['from_image_doc'],split) for q in rows)
    return [{'issuer':a,'type':b,'no_answer':d,'from_image_doc':e,'split':s,'count':n} for (a,b,d,e,s),n in sorted(c.items())]

def write(path, rows):
    p=safe_output(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps({'questions':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('csv'); p.add_argument('--output',required=True); p.add_argument('--split-dev-ratio',type=float); p.add_argument('--seed',type=int,default=7); a=p.parse_args(argv)
    if a.split_dev_ratio is not None and not 0<=a.split_dev_ratio<=1: p.error('--split-dev-ratio는 0~1이어야 합니다')
    warnings=[]
    try: qs=convert(a.csv,warnings)
    except ValueError as e: print(str(e),file=sys.stderr); return 2
    for warning in warnings: print(f'경고: {warning}',file=sys.stderr)
    if a.split_dev_ratio is None: write(a.output,qs); return 0
    base=safe_output(a.output); dev,final=stratified_split(qs,a.split_dev_ratio,a.seed)
    write(base.with_name(base.stem+'-dev'+base.suffix),dev); write(base.with_name(base.stem+'-final'+base.suffix),final)
    print('카드사\t유형\t정답없음\t이미지유래\t분할\t건수')
    for r in summary(dev,'dev')+summary(final,'final'): print(f"{r['issuer']}\t{r['type']}\t{r['no_answer']}\t{r['from_image_doc']}\t{r['split']}\t{r['count']}")
    return 0
if __name__=='__main__': raise SystemExit(main())
