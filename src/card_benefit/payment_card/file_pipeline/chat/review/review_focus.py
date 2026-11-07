"""검수 시트 집중 보기: 정답 문장이 든 근거를 위로 올리고, 줄 번호·형광 표시·그래프 경로를 붙인다.

review_sheet.py 의 수집 함수를 재사용하고, 출력은 /tmp 아래 HTML 한 파일만 만든다.
PDF 원문 발췌가 들어가므로 만든 파일은 저장소에 올리지 않는다.
"""
from __future__ import annotations

import html
import json
import re
from collections import deque
from pathlib import Path
from urllib.parse import unquote, urlparse

from .review_sheet import collect_evidence, load_sources, safe_output, uuidish

CONTEXT_LINES = 2          # 근거 위아래로 같이 보여 줄 줄 수
RELEVANT_SCORE = 0.5       # 이 점수 이상이면 "정답 문장이 들어 있음"으로 본다
SHOW_TOP = 3               # 펼쳐서 보여 줄 근거 수
WINDOW_MAX = 1500          # 한 근거에 보여 줄 최대 글자 수
PATH_MAX_HOPS = 4


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _grams(text: str, n: int = 3) -> set[str]:
    t = _norm(text)
    if len(t) <= n:
        return {t} if t else set()
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def overlap_score(expected: str, window: str) -> float:
    """정답 문장의 3글자 조각 중 근거 글에 들어 있는 비율(0~1)."""
    ne = _norm(expected)
    if not ne:
        return 0.0
    if len(ne) <= 3:                       # 짧은 정답은 조각으로 나누지 않고 포함 여부로 본다
        return 1.0 if ne in _norm(window) else 0.0
    e = _grams(expected)
    return len(e & _grams(window)) / len(e)


def _pdf_path_from_link(link: str) -> Path:
    return Path(unquote(urlparse(link.split("#")[0]).path))


def span_window(page_text: str, start: int, end: int, context: int = CONTEXT_LINES):
    """(줄 시작, 줄 끝, 앞 글, 구간 글, 뒤 글). start·end 는 1부터 세는 글자 위치이며 end 글자도 포함."""
    s0 = max(start - 1, 0)
    e0 = max(min(end, len(page_text)), s0)
    line_start = page_text.count("\n", 0, s0) + 1
    line_end = page_text.count("\n", 0, max(e0 - 1, s0)) + 1
    starts = [0] + [i + 1 for i, ch in enumerate(page_text) if ch == "\n"]
    first = max(line_start - 1 - context, 0)
    last = min(line_end + context, len(starts) - 1)
    w0 = starts[first]
    w1 = starts[last + 1] - 1 if last + 1 < len(starts) else len(page_text)
    if w1 - w0 > WINDOW_MAX:                       # 구간이 너무 길면 구간 시작 주변만 자른다
        w0 = max(s0 - 200, w0)
        w1 = min(max(e0, s0 + 600) + 200, w1)
    return line_start, line_end, page_text[w0:s0], page_text[s0:e0], page_text[e0:w1]


def graph_paths(record, nodes, edges, seed_names):
    """검색된 노드 사이에서 시드로부터 각 노드까지 가장 짧은 경로(글)를 만든다."""
    ids = set(record.get("retrieved_node_ids") or [])
    fp_by_view = {uuidish(i): i for i in nodes}
    fpids = {fp_by_view[x] for x in ids if x in fp_by_view}
    adj: dict[str, list] = {i: [] for i in fpids}
    for e in edges:
        a, b = e.get("source_id"), e.get("target_id")
        if a in fpids and b in fpids:
            adj[a].append((b, e.get("edge_type", ""), "→"))
            adj[b].append((a, e.get("edge_type", ""), "←"))
    seeds = [i for i in fpids if nodes[i]["_name"] in seed_names]
    parent: dict[str, tuple | None] = {s: None for s in seeds}
    queue = deque(seeds)
    while queue:
        cur = queue.popleft()
        for nxt, etype, arrow in adj.get(cur, []):
            if nxt not in parent:
                parent[nxt] = (cur, etype, arrow)
                queue.append(nxt)

    def label(i):
        n = nodes[i]
        return f"{n['_name'][:40]}({n.get('node_type', '')})"

    def path_of(node_id):
        if node_id not in parent:
            return None
        hops, cur = [], node_id
        while parent[cur] is not None:
            prev, etype, arrow = parent[cur]
            hops.append((prev, etype, arrow, cur))
            cur = prev
        hops.reverse()
        if not hops:
            return label(node_id) + " (시드)"
        if len(hops) > PATH_MAX_HOPS:
            return f"{label(hops[0][0])} … {len(hops)}단계 … {label(node_id)}"
        parts = [label(hops[0][0])]
        for _, etype, arrow, cur in hops:
            parts.append(f"—{etype}{arrow} {label(cur)}")
        return " ".join(parts)

    return path_of, fpids


def _evidence_rows(record, q, nodes, edges, evidences, docs, documents, cache):
    """합쳐진 근거 목록. 같은 쪽·같은 구간은 하나로 묶고 노드 이름을 모은다."""
    items, _, _ = collect_evidence(record, nodes, edges, evidences, docs, documents, 10 ** 6, False)
    path_of, _ = graph_paths(record, nodes, edges, set(map(str, record.get("selected_seed_names") or [])))
    name_to_ids = {}
    for i, n in nodes.items():
        name_to_ids.setdefault((n["_issuer"], n["_name"], n.get("node_type", "")), []).append(i)
    expected = list(map(str, q.get("expected", [])))
    merged: dict[tuple, dict] = {}
    for it in items:
        key = (it["document"], it["page"], it["start"], it["end"])
        row = merged.setdefault(key, {"it": it, "nodes": [], "paths": []})
        row["nodes"].append(f"{it['node_name'][:60]} ({it['node_type']})")
        for nid in name_to_ids.get((it["issuer"], it["node_name"], it["node_type"]), []):
            p = path_of(nid)
            if p and p not in row["paths"]:
                row["paths"].append(p)
    rows = []
    for key, row in merged.items():
        it = row["it"]
        out = {"issuer": it["issuer"], "document": it["document"], "page": it["page"], "link": it["pdf_link"],
               "nodes": row["nodes"], "paths": row["paths"][:2], "status": it["quote_status"],
               "score": 0.0, "near": 0.0, "lines": "", "before": "", "span": "", "after": ""}
        if it["quote_status"] == "located" and str(it["page"]).isdigit():
            try:
                import fitz
                pdf_path = _pdf_path_from_link(it["pdf_link"])
                if not pdf_path.is_file():
                    out["status"] = "PDF 없음"
                    rows.append(out)
                    continue
                if pdf_path not in cache:
                    cache[pdf_path] = fitz.open(pdf_path)
                doc = cache[pdf_path]
                page = int(it["page"])
                if 1 <= page <= len(doc):
                    ls, le, before, span, after = span_window(doc[page - 1].get_text(), int(it["start"]), int(it["end"]))
                    if span:
                        out.update(lines=f"{ls}줄" if ls == le else f"{ls}~{le}줄", before=before, span=span, after=after)
                        # 점수는 구간 자체 기준. 앞뒤 줄은 "근처에 있음"으로만 따로 센다(옆 줄 근거가 위로 올라오지 않게).
                        out["score"] = max((overlap_score(e, span) for e in expected), default=0.0)
                        out["near"] = max((overlap_score(e, before + span + after) for e in expected), default=0.0)
                    else:
                        out["status"] = "위치 불일치"
                else:
                    out["status"] = "위치 불일치"
            except FileNotFoundError:
                out["status"] = "PDF 없음"
            except Exception:
                out["status"] = "위치 불일치"
        rows.append(out)
    rows.sort(key=lambda r: (-r["score"], -r["near"], str(r["page"]).zfill(4), r["lines"]))
    return rows


CSS = """:root{color-scheme:light dark}body{font:15px system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 16px;line-height:1.55}
article{border:1px solid #8885;border-radius:8px;padding:12px 16px;margin:18px 0}article.miss{border-color:#c33}
h2{margin:.2em 0}.k{font-weight:600}.box{background:#8881;border-radius:6px;padding:8px 12px;margin:6px 0;white-space:pre-wrap}
.ev{border-left:4px solid #8886;padding:6px 12px;margin:10px 0}.ev.hit{border-color:#2a8}.ev.low{border-color:#c80}
.src{white-space:pre-wrap;font-family:ui-monospace,monospace;font-size:13px;background:#8881;padding:8px;border-radius:6px}
mark{background:#fd0;color:#000;padding:0 1px}.muted{color:#888}.tag{font-size:12px;border-radius:4px;padding:1px 6px;background:#8883}
details{margin:8px 0}table{border-collapse:collapse}td,th{border:1px solid #8885;padding:3px 8px}"""


def _ev_html(r, esc, idx, hit):
    cls = "hit" if hit else "low"
    if hit:
        badge = f"★ 정답 문장 포함(겹침 {r['score']:.0%})"
    elif r["near"] >= RELEVANT_SCORE:
        badge = f"근처 줄에 정답 문장(겹침 {r['near']:.0%}, 이 구간 {r['score']:.0%})"
    else:
        badge = f"겹침 {r['score']:.0%}"
    pos = f"p.{esc(r['page'])} · {esc(r['lines'])}" if r["lines"] else f"p.{esc(r['page'])} · {esc(r['status'])}"
    out = [f'<div class="ev {cls}"><div><span class="tag">{esc(badge)}</span> <b>{esc(r["document"])}</b> · {pos} · '
           f'<a href="{esc(r["link"])}">PDF 열기</a></div>']
    out.append(f'<div class="muted">노드: {esc(" / ".join(r["nodes"][:3]))}</div>')
    for p in r["paths"]:
        out.append(f'<div class="muted">그래프 경로: {esc(p)}</div>')
    if r["span"]:
        out.append(f'<div class="src">{esc(r["before"])}<mark>{esc(r["span"])}</mark>{esc(r["after"])}</div>')
    out.append("</div>")
    return "".join(out)


def _build_focus_sheet(results_path, questions_path, csv_dirs, documents, output, cache):
    out = safe_output(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    questions = {q.get("id"): q for q in json.loads(Path(questions_path).read_text(encoding="utf-8")).get("questions", [])}
    results = [json.loads(x) for x in Path(results_path).read_text(encoding="utf-8").splitlines() if x.strip()]
    nodes, edges, evidences, docs = load_sources(csv_dirs, documents)
    esc = lambda x: html.escape(str(x if x is not None else ""), quote=True)
    parts = [f'<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
             f'<title>집중 검수 시트</title><style>{CSS}</style><body><h1>집중 검수 시트</h1>'
             '<p class="muted">정답 문장과 겹치는 근거를 위에 둡니다. 형광 부분이 그래프가 가리키는 원문 위치입니다. '
             '줄 번호는 PDF 글을 읽어 센 페이지 안의 줄이며 뷰어 화면의 줄과 다를 수 있습니다.</p>']
    summary = []
    cards = []
    for rec in results:
        q = questions.get(rec.get("id"), rec.get("question") or {})
        rows = _evidence_rows(rec, q, nodes, edges, evidences, docs, documents, cache)
        hits = [r for r in rows if r["score"] >= RELEVANT_SCORE]
        shown = hits[:SHOW_TOP] if hits else rows[:SHOW_TOP]
        rest = [r for r in rows if r not in shown]
        status = rec.get("classification") or ("error" if rec.get("status") == "error" else "")
        summary.append((q.get("id"), status, len(hits), len(rows)))
        card = [f'<article class="{"miss" if status != "search_hit_answer_hit" else ""}"><h2>{esc(q.get("id"))} · {esc(status)}</h2>',
                f'<div><span class="k">질문</span> {esc(q.get("question"))}</div>',
                f'<div><span class="k">정답 문장</span></div><div class="box">{esc(" / ".join(map(str, q.get("expected", []))))}</div>',
                f'<div><span class="k">모델 답변</span></div><div class="box">{esc(rec.get("answer"))}</div>']
        if hits:
            card.append(f'<p class="k">근거 {len(rows)}곳 중 정답 문장이 들어 있는 곳 {len(hits)}곳</p>')
        elif any(r["near"] >= RELEVANT_SCORE for r in rows):
            near = sum(r["near"] >= RELEVANT_SCORE for r in rows)
            card.append(f'<p class="k" style="color:#c80">근거 {len(rows)}곳 중 구간 자체에는 정답 문장이 없고, 앞뒤 줄에 있는 곳이 {near}곳 '
                        '(정답 문장이 여러 줄·표에 걸쳐 있으면 이렇게 보입니다. 형광 주변을 확인하세요)</p>')
        else:
            card.append(f'<p class="k" style="color:#c33">근거 {len(rows)}곳 중 정답 문장이 들어 있는 곳이 없습니다 '
                        '(검색 문제이거나 정답 문장이 원문과 다를 수 있음)</p>')
        card.extend(_ev_html(r, esc, i, r["score"] >= RELEVANT_SCORE) for i, r in enumerate(shown))
        if rest:
            card.append(f'<details><summary>나머지 근거 {len(rest)}곳</summary>' +
                        "".join(_ev_html(r, esc, i, False) for i, r in enumerate(rest[:30])) +
                        (f'<p class="muted">… {len(rest) - 30}곳 더</p>' if len(rest) > 30 else "") + "</details>")
        card.append("</article>")
        cards.append("".join(card))
    parts.append("<table><tr><th>문항</th><th>분류</th><th>정답 문장 포함 근거</th><th>전체 근거</th></tr>" +
                 "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in summary) + "</table>")
    parts.extend(cards)
    parts.append("</body></html>")
    out.write_text("".join(parts), encoding="utf-8")
    return out


def make_focus_sheet(results_path, questions_path, csv_dirs, documents, output):
    """집중 보기 HTML 을 만든다. 도중에 예외가 나도 열어 둔 PDF 는 닫는다."""
    cache: dict = {}
    try:
        return _build_focus_sheet(results_path, questions_path, csv_dirs, documents, output, cache)
    finally:
        for doc in cache.values():
            doc.close()
