"""Create a self-contained, offline OCR review sheet for scanned PDFs."""
from __future__ import annotations

import argparse
import base64
import csv
import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

import pymupdf

REPO_ROOT = Path(__file__).resolve().parents[6]
NUMBER = re.compile(r"(?<![\w(])(?:\d[\d,.]*(?:\s*%|\s*(?:원|회|개월|년|월|일|시간|분|배|명|건|매|포인트))?|\d+(?:\.\d+)?\s*%)(?![\w)])")


def _tier(confidence: float) -> str:
    return "green" if confidence >= 80 else "yellow" if confidence >= 50 else "red"


def _kind(token: str) -> str:
    if "%" in token:
        return "ratio"
    if re.search(r"(?:회|명|건|매)$", token):
        return "count"
    if re.search(r"(?:개월|년|월|일|시간|분)$", token):
        return "period"
    return "amount"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _map_words(text: str, words: list[dict]) -> tuple[list[tuple[int, int, float]], int, int]:
    """Align sidecar words, in OCR order, against page text and return spans."""
    spans, cursor, matched = [], 0, 0
    for word in words:
        token = str(word.get("text", ""))
        if not token:
            continue
        match = re.search(re.escape(token), text[cursor:], flags=re.IGNORECASE)
        if not match:
            # OCR sidecars can encode spaces between glyphs; allow whitespace flexibly.
            pattern = re.sub(r"\\ ", r"\\s*", re.escape(token))
            match = re.search(pattern, text[cursor:], flags=re.IGNORECASE)
        if match:
            start = cursor + match.start()
            end = cursor + match.end()
            spans.append((start, end, float(word.get("confidence", 0) or 0)))
            cursor = end
            matched += 1
    return spans, matched, len([w for w in words if w.get("text")])


def _token_confidence(start: int, end: int, spans: list[tuple[int, int, float]]) -> float:
    overlaps = [conf for left, right, conf in spans if left < end and right > start]
    return sum(overlaps) / len(overlaps) if overlaps else 0.0


def _context(text: str, start: int, end: int, width: int = 20) -> str:
    return text[max(0, start - width):start] + "⟦" + text[start:end] + "⟧" + text[end:end + width]


def _safe(value: object) -> str:
    return html.escape(str(value), quote=True)


def _repo_safe_output(output: str | Path) -> Path:
    target = Path(output).expanduser().resolve()
    repo = REPO_ROOT.resolve()
    if target == repo or repo in target.parents:
        raise ValueError("출력 HTML은 저장소 안에 둘 수 없습니다.")
    return target


def generate_review_html(ocr_dir: str | Path, documents: str | Path, data_root: str | Path,
                        output: str | Path, *, only_low_confidence: bool = False,
                        max_pages: int | None = None, dpi: int = 110, priority: int | None = 20,
                        max_size_bytes: int = 250_000_000) -> Path:
    output = _repo_safe_output(output)
    ocr_dir, data_root = Path(ocr_dir), Path(data_root)
    with Path(documents).open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    # The index may contain duplicate aliases; one PDF per doc_id, canonical preferred.
    index = {}
    for row in rows:
        if row.get("canonical", "Y") == "Y" or row["doc_id"] not in index:
            index[row["doc_id"]] = row
    numeric_rows = []
    tsv_path = ocr_dir / "numeric_tokens.csv"
    if tsv_path.exists():
        with tsv_path.open(encoding="utf-8-sig", newline="") as f:
            numeric_rows = list(csv.DictReader(f))
    tsv_by_page = defaultdict(list)
    for row in numeric_rows:
        tsv_by_page[(row.get("doc_id"), int(row.get("page_no") or 0))].append(row)
    documents_data, all_pages = [], []
    mapped_words = total_words = numeric_mapped = numeric_total = tsv_matches = tsv_total = 0
    tier_counts, kind_conf = Counter(), defaultdict(list)
    for doc_id, row in index.items():
        trace_path, side_path = ocr_dir / f"{doc_id}.json", ocr_dir / f"{doc_id}.ocr.json"
        if not trace_path.exists() or not side_path.exists():
            continue
        trace, side = json.loads(trace_path.read_text(encoding="utf-8")), json.loads(side_path.read_text(encoding="utf-8"))
        side_pages = {int(p["page_no"]): p for p in side.get("pages", [])}
        pdf_path = (data_root / row["file_path"]).resolve()
        if not pdf_path.is_file():
            continue
        doc_pages = []
        with pymupdf.open(pdf_path) as pdf:
            for page_data in trace.get("pages", []):
                page_no = int(page_data.get("page_no", 1))
                if page_no > len(pdf):
                    continue
                text = str(page_data.get("text", ""))
                side_page = side_pages.get(page_no, {})
                spans, aligned, count = _map_words(text, side_page.get("words", []))
                mapped_words += aligned
                total_words += count
                token_data = []
                for match in NUMBER.finditer(text):
                    token = match.group()
                    conf = _token_confidence(match.start(), match.end(), spans)
                    numeric_total += 1
                    numeric_mapped += int(any(left < match.end() and right > match.start() for left, right, _ in spans))
                    kind = _kind(token)
                    tier_counts[_tier(conf)] += 1
                    kind_conf[kind].append(conf)
                    token_data.append({"token": token, "confidence": conf, "kind": kind,
                                       "start": match.start(), "end": match.end(),
                                       "context": _context(text, match.start(), match.end())})
                low = [t for t in token_data if t["confidence"] < 80]
                tsv_rows = tsv_by_page.get((doc_id, page_no), [])
                for tsv in tsv_rows:
                    tsv_total += 1
                    if any(t["token"] == tsv.get("token") and
                           _norm(str(tsv.get("context", ""))) in _norm(text[max(0, t["start"]-40):t["end"]+40])
                           for t in token_data):
                        tsv_matches += 1
                pix = pdf[page_no - 1].get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), alpha=False)
                scale = min(1.0, 900 / max(pix.width, 1))
                if scale < 1:
                    pix = pdf[page_no - 1].get_pixmap(matrix=pymupdf.Matrix(dpi / 72 * scale, dpi / 72 * scale), alpha=False)
                image_uri = "data:image/jpeg;base64," + base64.b64encode(pix.tobytes("jpeg", jpg_quality=70)).decode("ascii")
                page = {"doc_id": doc_id, "page_no": page_no, "text": text, "tokens": token_data,
                        "low": low, "confidence": float(side_page.get("mean_confidence", 0) or 0),
                        "image": image_uri, "role": row.get("doc_role", ""), "filename": pdf_path.name,
                        "pdf_url": "file://" + quote(str(pdf_path), safe="/:") + f"#page={page_no}",
                        "page_count": len(pdf)}
                doc_pages.append(page)
                all_pages.append(page)
        if doc_pages:
            documents_data.append({"doc_id": doc_id, "filename": pdf_path.name, "role": row.get("doc_role", ""),
                                   "page_count": len(doc_pages), "pages": doc_pages})
    if only_low_confidence:
        all_pages = [page for page in all_pages if page["low"]]
    if priority is not None and priority > 0:
        all_pages = sorted(all_pages, key=lambda p: (-len(p["low"]), -sum(80-t["confidence"] for t in p["low"]), p["doc_id"], p["page_no"]))[:priority]
    if max_pages is not None:
        all_pages = all_pages[:max_pages]
    tier_counts = Counter(_tier(t["confidence"]) for p in all_pages for t in p["tokens"])
    kind_conf = defaultdict(list)
    for p in all_pages:
        for token in p["tokens"]:
            kind_conf[token["kind"]].append(token["confidence"])
    selected = {(p["doc_id"], p["page_no"]) for p in all_pages}
    cards = []
    for page in all_pages:
        low_items = "".join(f'<li><b>{_safe(t["token"])}</b> · {t["confidence"]:.1f}% · {_safe(t["context"])}</li>' for t in page["low"])
        pieces, cursor = [], 0
        for i, token in enumerate(page["tokens"]):
            pieces.append(_safe(page["text"][cursor:token["start"]]))
            pieces.append(f'<span class="num { _tier(token["confidence"]) }" data-tier="{_tier(token["confidence"])}" title="confidence {token["confidence"]:.1f}%" data-token="{_safe(token["token"])}" data-conf="{token["confidence"]:.2f}" data-kind="{token["kind"]}" data-doc="{page["doc_id"]}" data-page="{page["page_no"]}" data-index="{i}">{_safe(token["token"])}</span>')
            cursor = token["end"]
        pieces.append(_safe(page["text"][cursor:]))
        tokens = "".join(pieces)
        verdicts = "".join(f'<div class="verdict" data-id="{page["doc_id"]}|{page["page_no"]}|{i}"><span>{_safe(t["token"])}</span> <button data-v="correct">정상</button><button data-v="wrong">오류</button><button data-v="unknown" class="active">미확인</button><input aria-label="수정값" placeholder="수정값"></div>' for i, t in enumerate(page["tokens"]))
        cards.append(f'<article class="page-card" data-doc="{page["doc_id"]}" data-page="{page["page_no"]}"><h2>{_safe(page["filename"])} · 역할 {_safe(page["role"])} · {page["page_count"]}페이지</h2><h3>페이지 {page["page_no"]} · 평균 신뢰도 {page["confidence"]:.1f}% · <a href="{_safe(page["pdf_url"])}">PDF 열기</a></h3><ul class="needs"><b>확인 필요</b>{low_items or "<li>없음</li>"}</ul><div class="columns"><img src="{page["image"]}" alt="PDF page {page["page_no"]}"><details open><summary>OCR 전체 텍스트</summary><pre>{tokens}</pre></details></div><details><summary>숫자 판정</summary>{verdicts}</details></article>')
    numeric_count = sum(tier_counts.values())
    mean_by_kind = {k: (sum(v)/len(v) if v else 0) for k, v in kind_conf.items()}
    summary = f'<section class="summary"><b>문서 {len({p["doc_id"] for p in all_pages})} · 페이지 {len(all_pages)} · 숫자 토큰 {numeric_count}</b><p>초록 ≥80: {tier_counts["green"]} · 노랑 50–79: {tier_counts["yellow"]} · 빨강 &lt;50: {tier_counts["red"]}</p><p>종류별 평균: ' + " · ".join(f'{k} {v:.1f}' for k, v in mean_by_kind.items()) + f'</p><p>숫자-신뢰도 매핑: {numeric_mapped}/{numeric_total} ({numeric_mapped/numeric_total*100 if numeric_total else 0:.1f}%) · 단어-본문 정렬: {mapped_words}/{total_words} ({mapped_words/total_words*100 if total_words else 0:.1f}%) · TSV 문맥 일치: {tsv_matches}/{tsv_total} ({tsv_matches/tsv_total*100 if tsv_total else 0:.1f}%)</p></section>'
    js = r'''<script>
const safeStore={get(k){try{return localStorage.getItem(k)}catch(_){return null}},set(k,v){try{localStorage.setItem(k,v)}catch(_){}}};
document.querySelectorAll('.verdict').forEach(row=>{const key='ocr-review:'+row.dataset.id;let v={};try{v=JSON.parse(safeStore.get(key)||'{}')}catch(_){};const saved=v[row.dataset.id];if(saved){row.querySelector(`[data-v="${saved.verdict}"]`)?.classList.add('active');row.querySelector('input').value=saved.value||''}row.querySelectorAll('button').forEach(b=>b.onclick=()=>{row.querySelectorAll('button').forEach(x=>x.classList.remove('active'));b.classList.add('active');save()});row.querySelector('input').oninput=save;function save(){const all={};try{Object.assign(all,JSON.parse(safeStore.get(key)||'{}'))}catch(_){};all[row.dataset.id]={verdict:row.querySelector('.active')?.dataset.v||'unknown',value:row.querySelector('input').value};safeStore.set(key,JSON.stringify(all))}});
document.getElementById('download').onclick=()=>{const rows=[['doc_id','page_no','token','confidence','판정','수정값']];document.querySelectorAll('.num').forEach(n=>{const id=n.dataset.doc+'|'+n.dataset.page+'|'+n.dataset.index,key='ocr-review:'+id;let x={};try{x=JSON.parse(safeStore.get(key)||'{}')[id]||{}}catch(_){};rows.push([n.dataset.doc,n.dataset.page,n.dataset.token,n.dataset.conf,x.verdict||'unknown',x.value||''])});const csv='\ufeff'+rows.map(r=>r.map(x=>'"'+String(x).replaceAll('"','""')+'"').join(',')).join('\r\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));a.download='ocr-review-verdicts.csv';a.click();URL.revokeObjectURL(a.href)};
</script>'''
    document_html = '<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>OCR 대조 시트</title><style>body{font:16px/1.55 system-ui,sans-serif;margin:1rem auto;max-width:1200px;padding:0 1rem;background:#fff;color:#222}@media(prefers-color-scheme:dark){body{background:#171717;color:#eee}a{color:#9cc8ff}.page-card,.summary{background:#252525;border-color:#555}}.summary,.page-card{border:1px solid #bbb;border-radius:9px;padding:1rem;margin:1rem 0;background:#fafafa}.columns{display:grid;grid-template-columns:minmax(280px,1fr) minmax(320px,1fr);gap:1rem;align-items:start}.columns img{width:100%;height:auto;border:1px solid #999}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:75vh;overflow:auto}.num{border-radius:3px;padding:0 2px}.green{background:#bde8c4;color:#123}.yellow{background:#ffe59b;color:#332600}.red{background:#ffb5b5;color:#4a0000}.needs{background:#fff4cc;color:#2a2100;padding:1rem 2rem}.verdict{padding:.25rem;border-bottom:1px solid #ddd}.active{outline:2px solid #2672d8}button,input{font:inherit;margin:.2rem;padding:.25rem}.toolbar{position:sticky;top:0;background:#fff;padding:.7rem;z-index:2}@media(prefers-color-scheme:dark){.toolbar{background:#171717}}@media(max-width:750px){.columns{grid-template-columns:1fr}}</style><header class="toolbar"><h1>OCR 대조 시트</h1><button id="download">판정 CSV 다운로드</button></header>' + summary + ''.join(cards) + js + '</html>'
    encoded = document_html.encode("utf-8")
    if len(encoded) > max_size_bytes:
        raise ValueError(f"생성 용량 {len(encoded)}바이트가 제한 {max_size_bytes}바이트를 초과합니다.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ocr-dir", required=True)
    parser.add_argument("--documents", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--only-low-confidence", action="store_true")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--dpi", type=int, default=110)
    parser.add_argument("--priority", type=int, default=20, help="top low-confidence pages; 0 includes all pages")
    parser.add_argument("--max-size-mb", type=int, default=250)
    args = parser.parse_args(argv)
    output = generate_review_html(args.ocr_dir, args.documents, args.data_root, args.output,
                                  only_low_confidence=args.only_low_confidence, max_pages=args.max_pages,
                                  dpi=args.dpi, priority=args.priority, max_size_bytes=args.max_size_mb*1024*1024)
    print(f"{output} · {output.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
