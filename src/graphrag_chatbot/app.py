"""GraphRAG 챗봇 UI (Streamlit). 실행: streamlit run app.py"""
import json
import uuid

import streamlit as st
import streamlit.components.v1 as components

import rag
import timing
from graph_view import build_html

st.set_page_config(page_title="GraphRAG 챗봇", layout="centered")

SUGGESTIONS = [
    "결제 API에 장애가 나면 영향받는 서비스는?",
    "결제 API 담당 팀은 어디야?",
]

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap');
html, body, .stMarkdown, .stTextInput input, .stButton button, .stCaption {
    font-family: 'Noto Sans KR', sans-serif;
}
#MainMenu, footer { visibility: hidden; }
.stTextInput input { border-radius: 24px; padding: 0.75rem 1.2rem; }
[data-testid="stChatMessage"] { border-radius: 12px; }
</style>
""",
    unsafe_allow_html=True,
)

ss = st.session_state
ss.setdefault("convs", {})  # {대화 id: {"title": str, "turns": [turn, ...]}}
ss.setdefault("current", None)
ss.setdefault("show_graph", True)


def show_html(html: str, height: int) -> None:
    """pyvis HTML을 화면에 넣습니다. 최신 Streamlit은 st.iframe, 구버전은 components.html."""
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        components.html(html, height=height)


def render_evidence(turn: dict) -> None:
    sub = turn["subgraph"]
    if ss.show_graph and sub["nodes"]:
        with st.expander("근거 그래프", expanded=True):
            st.caption(f"노드 {len(sub['nodes'])}개 · 관계 {len(sub['edges'])}개 · 빨간 테두리는 질문에서 찾은 엔티티")
            html = build_html(json.dumps(sub, ensure_ascii=False, sort_keys=True))
            show_html(html, height=420)
    if turn["sources"]:
        lines = [
            f"- {s['title']}" + (f" · {s['note']}" if s["note"] else "")
            for s in turn["sources"]
        ]
        st.markdown("**출처**\n" + "\n".join(lines))


def render_turn(turn: dict) -> None:
    with st.chat_message("user"):
        st.write(turn["q"])
    with st.chat_message("assistant"):
        with st.expander("검색 과정"):
            st.text("\n".join(turn["steps"]))
        st.write(turn["answer"])
        render_evidence(turn)


def run_turn(question: str, conv: dict) -> bool:
    """질문 하나를 처리하면서 화면에 단계와 답변을 실시간으로 보여줍니다."""
    history = [(t["q"], t["answer"]) for t in conv["turns"]]
    with st.chat_message("user"):
        st.write(question)
    timing.start(question)
    with st.chat_message("assistant"):
        try:
            with st.status("질의 분석 중…", expanded=True) as status:
                analysis = rag.analyze(question, rag.list_entities())
                st.write(
                    f"엔티티: {', '.join(analysis.entities) or '없음'} · 의도: {analysis.intent or '-'}"
                )
                status.update(label="그래프 탐색 중…")
                sub = rag.explore(analysis)
                st.write(f"{analysis.hops}-hop · 노드 {len(sub['nodes'])}개 · 관계 {len(sub['edges'])}개")
                status.update(label="검색 완료", state="complete", expanded=False)
            text = st.write_stream(rag.generate_stream(question, sub, history))
        except Exception as e:  # 환경 변수 누락, 연결 실패 등
            timing.finish(ok=False, error=type(e).__name__)
            st.error(f"처리 중 오류가 발생했습니다: {e}")
            return False
        turn = {
            "q": question,
            "answer": text,
            "subgraph": sub,
            "sources": rag.sources(sub),
            "steps": rag.steps_text(analysis, sub),
        }
        render_evidence(turn)
    conv["turns"].append(turn)
    return True


# ---- 사이드바: 새 대화, 대화 기록, 표시 옵션 ----
with st.sidebar:
    if st.button("+ 새 대화", use_container_width=True, type="primary"):
        ss.current = None
    st.caption("대화 기록")
    for cid, c in reversed(list(ss.convs.items())):
        mark = "● " if cid == ss.current else ""
        if st.button(mark + c["title"], key=f"h_{cid}", use_container_width=True):
            ss.current = cid
            st.rerun()
    st.divider()
    st.checkbox("근거 그래프 표시", key="show_graph")
    st.caption("그래프 범례")
    st.markdown(
        "<div style='line-height:1.9'>"
        "<span style='background:#dbeafe;border:2px solid #1e5a96;padding:0 8px;border-radius:4px'>&nbsp;</span> Service<br>"
        "<span style='background:#dcf3e4;border:2px solid #1f7a45;padding:0 8px;border-radius:4px'>&nbsp;</span> Team<br>"
        "<span style='background:#fdf0d0;border:2px solid #8a5a00;padding:0 8px;border-radius:4px'>&nbsp;</span> Document"
        "</div>",
        unsafe_allow_html=True,
    )

# ---- 본문 ----
conv = ss.convs.get(ss.current)
turns = conv["turns"] if conv else []
compact = bool(turns)

size = "1.9rem" if compact else "3.4rem"
top = "0.5rem" if compact else "5rem"
st.markdown(
    f"<h1 style='text-align:center;font-size:{size};margin:{top} 0 1.2rem;padding:0'>"
    "<span style='color:#d62f2f'>Graph</span>RAG 챗봇</h1>",
    unsafe_allow_html=True,
)

question = None
with st.form("ask", clear_on_submit=True, border=False):
    c1, c2 = st.columns([6, 1], vertical_alignment="bottom")
    text = c1.text_input("질문", placeholder="무엇이든 물어보세요", label_visibility="collapsed")
    sent = c2.form_submit_button("보내기", use_container_width=True)
if sent and text.strip():
    question = text.strip()

if not compact:
    for col, s in zip(st.columns(len(SUGGESTIONS)), SUGGESTIONS):
        if col.button(s, use_container_width=True):
            question = s

for t in turns:
    render_turn(t)

if question:
    target = conv or {"title": question[:24], "turns": []}
    if run_turn(question, target):
        if conv is None:
            cid = uuid.uuid4().hex[:8]
            ss.convs[cid] = target
            ss.current = cid
        st.rerun()  # 첫 질문 뒤에 화면을 대화 모드(작은 로고)로 전환합니다.
