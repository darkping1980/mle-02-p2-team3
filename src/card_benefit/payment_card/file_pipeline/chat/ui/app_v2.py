"""Opt-in v2 screen for the card-benefit GraphRAG chatbot."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import uuid

import streamlit as st

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[5]
CHATBOT_DIR = REPO_ROOT / "src" / "graphrag_chatbot"
if str(CHATBOT_DIR) not in sys.path:
    sys.path.insert(0, str(CHATBOT_DIR))
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import rag
from ui import ui_v2


def _k(prefix: str, name: str) -> str:
    return f"{prefix}_{name}"


def _render_sources(sources: list[dict]) -> None:
    if not sources:
        st.write("자료에서 확인하지 못함")
        return
    for source in sources:
        title = source.get("title") or "자료에서 확인하지 못함"
        pages = source.get("pages", "자료에서 확인하지 못함")
        page_text = ", ".join(map(str, pages)) if isinstance(pages, list) and pages else str(pages)
        st.markdown(f"**{title}** · 쪽 {page_text}")
        if source.get("text"):
            st.caption(source["text"])
        if source.get("truncated"):
            st.caption("원문 구간이 일부 생략되었습니다.")


def _render_graph(subgraph: dict) -> None:
    try:
        import streamlit.components.v1 as components
        from graph_view import build_html
        html = build_html(json.dumps(subgraph, ensure_ascii=False, sort_keys=True))
        if hasattr(st, "iframe"):
            st.iframe(html, height=420)
        else:
            components.html(html, height=420)
    except Exception:
        st.caption("근거 그래프를 표시하지 못했습니다.")


def _render_turn(turn: dict, index: int, key_prefix: str) -> None:
    with st.chat_message("user"):
        st.write(turn["question"])
    with st.chat_message("assistant"):
        st.markdown(turn["answer"])
        with st.expander("근거", expanded=False):
            _render_sources(turn.get("sources", []))
        table = turn.get("compare_table")
        if table:
            st.table(table["rows"])
        if st.session_state[_k(key_prefix, "developer_mode")]:
            with st.expander("검색 과정", expanded=False):
                st.write("분석 질문:", turn.get("analysis_question", turn["question"]))
                st.write("선택 엔티티:", ", ".join(turn.get("selected_entities", [])) or "자료에서 확인하지 못함")
                st.json(turn.get("search_process", {}))
                st.write("지연 시간(ms):", turn.get("latency_ms", {}))
                if turn.get("subgraph", {}).get("nodes"):
                    with st.expander("근거 그래프", expanded=False):
                        _render_graph(turn["subgraph"])
                if os.environ.get("FP_QA_LOG"):
                    st.caption(f"Q/A 로그: {os.environ['FP_QA_LOG']}")


def _write_qa_log(question: str, answer: str, subgraph: dict, selected_entities: list[str], latency_ms: dict, timing_segments: dict) -> None:
    path = os.environ.get("FP_QA_LOG")
    if not path:
        return
    refs, evidence_error = [], None
    try:
        import db
        fp_ids = [str(node.get("props", {}).get("fp_id")) for node in subgraph.get("nodes", [])
                  if node.get("props", {}).get("fp_id") and not str(node["props"]["fp_id"]).startswith("doc:")]
        refs = db.run_query(
            "select distinct e.node_id, e.edge_id, e.doc_sha256, e.page_no, e.start_pos, e.end_pos, e.quote_status "
            "from public.fp_evidence e left join public.fp_edges edge on edge.id = e.edge_id "
            "where e.node_id = any(%(node_ids)s) "
            "or (edge.source_id = any(%(node_ids)s) and edge.target_id = any(%(node_ids)s)) "
            "order by e.doc_sha256, e.page_no, e.start_pos limit 1000",
            {"node_ids": fp_ids},
        )
    except Exception:
        refs, evidence_error = [], "source_refs_query_error"
    try:
        import llm
        from answer.answer_format import get_answer_format_version
        from answer import answer_eval
        import qa_log
        result = {"answer": answer, "subgraph": subgraph, "selected_entities": selected_entities}
        record = qa_log.build_record(
            question=question, answer=answer, result=result,
            model=getattr(llm, "MODEL", None), usage=timing_segments.get("usage"),
            latency_ms=latency_ms,
            answer_format_version="legacy" if os.environ.get("FP_ANSWER_FORMAT", "v2").strip().lower() == "legacy" else get_answer_format_version(),
            graph_schema=os.environ.get("FP_GRAPH_SCHEMA", "fp_chat"), source_refs=refs,
            evidence_error=evidence_error,
            app_version=os.environ.get("GIT_COMMIT") or os.environ.get("GITHUB_SHA"),
        )
        record["refusal"] = answer_eval._refusal(answer)
        qa_log.write_record(record)
    except Exception:
        pass


def _run_turn(question: str, conversation: dict) -> None:
    turn_started = time.perf_counter()
    previous_turns = conversation["turns"]
    history = [(turn["question"], turn["answer"]) for turn in previous_turns]
    last_entities = previous_turns[-1].get("selected_entities", []) if previous_turns else []
    analysis_question = ui_v2.build_analysis_question(question, previous_turns, last_entities)
    latency_ms: dict[str, float | None] = {}
    search_process: dict[str, object] = {}
    subgraph = {"nodes": [], "edges": [], "seeds": []}
    selected_entities: list[str] = []
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        try:
            with st.status("질문 이해 중", expanded=True) as status:
                started = time.perf_counter()
                entities = rag.list_entities()
                latency_ms["entities_db"] = (time.perf_counter() - started) * 1000
                started = time.perf_counter()
                analysis = rag.analyze(analysis_question, entities)
                latency_ms["analyze_llm"] = (time.perf_counter() - started) * 1000
                selected_entities = list(getattr(analysis, "entities", []) or [])
                search_process["질문 이해"] = {"entities": selected_entities, "intent": getattr(analysis, "intent", "")}
                status.write("질문 이해 중 · 완료")
                status.update(label="그래프 탐색 중")
                started = time.perf_counter()
                subgraph = rag.explore(analysis)
                latency_ms["explore_db"] = (time.perf_counter() - started) * 1000
                search_process["그래프 탐색"] = {
                    "hops": getattr(analysis, "hops", 1),
                    "nodes": len(subgraph.get("nodes", [])),
                    "edges": len(subgraph.get("edges", [])),
                }
                status.write("그래프 탐색 중 · 완료")
                status.update(label="답변 작성 중")
                import llm
                usage_before = llm.usage_totals() if callable(getattr(llm, "usage_totals", None)) else None
                started = time.perf_counter()
                first_chunk = None

                def measured_stream():
                    nonlocal first_chunk
                    for chunk in rag.generate_stream(question, subgraph, history):
                        if first_chunk is None:
                            first_chunk = time.perf_counter()
                            latency_ms["first_token"] = (first_chunk - started) * 1000
                        yield chunk

                answer = st.write_stream(measured_stream())
                latency_ms["total"] = (time.perf_counter() - turn_started) * 1000
                if first_chunk is None:
                    latency_ms["first_token"] = None
                usage_after = llm.usage_totals() if callable(getattr(llm, "usage_totals", None)) else None
                usage = None
                if usage_after is not None:
                    usage = {key: max(0, usage_after.get(key, 0) - (usage_before or {}).get(key, 0))
                             for key in ("prompt_tokens", "completion_tokens", "cost_usd")}
                search_process["답변 작성"] = "완료"
                status.update(label="답변 작성 완료", state="complete", expanded=False)
        except Exception as exc:
            st.error(f"처리 중 오류가 발생했습니다 ({type(exc).__name__}).")
            return
        sources = ui_v2.collect_sources(subgraph)
        compare_table = ui_v2.build_compare_table(subgraph)
        merged_groups = [node for node in subgraph.get("nodes", []) if node.get("merged_member_count", 1) > 1]
        if merged_groups:
            st.caption(f"중복 연결로 묶은 그룹 {len(merged_groups)}개 · 멤버 노드 {sum(node['merged_member_count'] for node in merged_groups)}개")
        turn = {
            "question": question,
            "analysis_question": analysis_question,
            "answer": str(answer),
            "sources": sources,
            "compare_table": compare_table,
            "selected_entities": selected_entities,
            "latency_ms": latency_ms,
            "search_process": search_process,
            "entity_dedupe": {"groups": len(merged_groups), "members": sum(node["merged_member_count"] for node in merged_groups)},
            "subgraph": subgraph,
        }
        with st.expander("근거", expanded=False):
            _render_sources(sources)
        if compare_table:
            st.table(compare_table["rows"])
    conversation["turns"].append(turn)
    _write_qa_log(question, str(answer), subgraph, selected_entities, latency_ms, {"usage": usage})


def render(*, key_prefix: str = "v2") -> None:
    """화면 본문을 그린다. 페이지 설정은 호출한 쪽(호스트 또는 단독 실행)이 맡는다."""
    ss = st.session_state
    conversations_key = _k(key_prefix, "conversations")
    current_key = _k(key_prefix, "current")
    ss.setdefault(conversations_key, {})
    ss.setdefault(current_key, None)
    ss.setdefault(_k(key_prefix, "developer_mode"), False)

    with st.container():
        new_chat_column, developer_mode_column = st.columns(2)
        with new_chat_column:
            if st.button("새 대화", key=_k(key_prefix, "new_chat"), use_container_width=True):
                ss[current_key] = None
                st.rerun()
        with developer_mode_column:
            st.toggle("개발자 모드", key=_k(key_prefix, "developer_mode"))

    st.markdown("<h2 style='margin-bottom:0.2rem'>카드 혜택 도우미</h2>", unsafe_allow_html=True)
    st.caption("하나·우리카드 신용카드 상품설명서 기준")

    conversation = ss[conversations_key].get(ss[current_key])
    turns = conversation["turns"] if conversation else []
    if not turns:
        st.write("카드 혜택이나 이용 조건을 질문해 주세요.")
        columns = st.columns(2)
        for index, example in enumerate(ui_v2.EXAMPLE_QUESTIONS):
            if columns[index % 2].button(example, key=_k(key_prefix, f"example_{index}"), use_container_width=True):
                ss[_k(key_prefix, "pending_question")] = example

    for index, turn in enumerate(turns):
        _render_turn(turn, index, key_prefix)

    question = st.chat_input("카드 혜택을 질문해 보세요", key=_k(key_prefix, "chat_input"))
    pending = ss.pop(_k(key_prefix, "pending_question"), None)
    if question and question.strip():
        pending = question.strip()
    if pending:
        target = conversation or {"title": pending[:32], "turns": []}
        _run_turn(pending, target)
        if not turns:
            conversation_id = uuid.uuid4().hex[:10]
            ss[conversations_key][conversation_id] = target
            ss[current_key] = conversation_id
        else:
            ss[conversations_key][ss[current_key]] = target
        st.rerun()


if __name__ == "__main__":
    st.set_page_config(page_title="카드 혜택 챗봇", layout="centered")
    render(key_prefix="v2")
