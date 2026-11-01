"""개발 검증 모드 화면. 버튼을 누른 단계만 실행하고 결과는 session_state에 둔다."""
import streamlit as st

from . import card_graphrag
from .neo4j_search import SECTION_QUERIES, STATEMENTS, flatten_record


def _reset() -> None:
    """검증 결과를 비운다."""
    st.session_state.verify = None


def _show_statement(item: dict) -> None:
    """실행할 Cypher를 복사 가능한 형태로 표시한다."""
    st.markdown(f"**`{item['statement_id']}`**")
    st.caption(item["path"])
    st.code(item["browser_cypher"], language="cypher")
    st.json(item["parameters"], expanded=False)


def _show_records(statement_id: str, rows: list[dict]) -> None:
    """Cypher가 돌려준 레코드를 표로 표시한다."""
    st.markdown(f"**`{statement_id}`** · {len(rows)}건")
    st.caption(STATEMENTS[statement_id][1])
    if rows:
        st.dataframe([flatten_record(row) for row in rows], hide_index=True)


def _show_interpret(state: dict) -> None:
    """1단계 결과를 표시한다."""
    st.subheader("1단계 결과: 질문 해석", anchor=False)
    parameters = state.get("search_parameters") or {}
    st.markdown(f"**유형** `{state.get('intent')}` · **요청** `{state['request_id']}`")
    st.json({"benefit_ids": parameters.get("benefit_ids"), "benefit_names": parameters.get("benefit_names"),
             "sections": parameters.get("sections"), "payment_amount": parameters.get("payment_amount"),
             "ambiguity": parameters.get("ambiguity")})
    st.dataframe(state["llm_calls"], hide_index=True)
    for warning in state["warnings"]:
        st.warning(warning)
    if state.get("catalog"):
        with st.expander("Interpret 전에 실행한 카탈로그 조회"):
            _show_statement(card_graphrag.catalog_plan())
            st.dataframe([{**row, "targets": ", ".join(row["targets"])} for row in state["catalog"]], hide_index=True)


def _show_plan(state: dict) -> None:
    """2단계: 실행 예정 Cypher. 아직 DB에서 실행하지 않는다."""
    plan = card_graphrag.verification_plan(state)
    st.subheader(f"2단계: 실행 예정 Cypher ({len(plan)}건)", anchor=False)
    st.caption("코드 블록의 복사 버튼으로 Neo4j Browser에 붙여넣어 실행할 수 있습니다. 값이 들어간 읽기 전용 Cypher입니다.")
    names = dict(zip(state["search_parameters"]["benefit_keys"], state["search_parameters"]["benefit_names"]))
    current = None
    for item in plan:
        key = item["parameters"]["key"]
        if key != current:
            st.markdown(f"#### {names[key]}")
            current = key
        _show_statement(item)


def _show_results(state: dict) -> None:
    """3단계 결과: 실제 반환 레코드."""
    st.subheader("3단계 결과: Neo4j 조회", anchor=False)
    sections = state["search_parameters"]["sections"]
    for detail in state.get("retrieved_data") or []:
        st.markdown(f"#### {detail['context']['benefit'].get('name')}")
        _show_records("card.context", [detail["context"]])
        for name in SECTION_QUERIES:
            if name in sections:
                _show_records(f"card.{name}", detail[name])
    with st.expander("Neo4j 조회 원본 JSON"):
        st.json(state.get("retrieved_data") or [], expanded=False)
    evidence = state.get("evidence") or []
    st.markdown(f"**답변에 전달될 근거 {len(evidence)}건** (`evidence_id`로 합친 결과)")
    st.dataframe([{key: item[key] for key in ("evidence_id", "page_no", "approval_status", "subjects", "items", "rule_keys", "quote")}
                  for item in evidence], hide_index=True)
    st.markdown("**미확정 사항**")
    for text in state.get("unresolved") or []:
        st.text(text)


def render(get_pipeline, show_outcome) -> None:
    """단계별 검증 화면. 자동 실행과 같은 노드 함수를 쓰고 LangGraph 흐름만 사용자가 진행한다."""
    st.info("버튼을 누른 단계만 실행합니다. 질문 해석과 답변 생성은 유료 API를 각 1회 호출합니다. DB 조회는 읽기 전용입니다.")
    question = st.text_area("질문", key="verify_question", max_chars=card_graphrag.MAX_QUESTION_CHARS, height=80,
                            placeholder="카드 혜택을 자연어로 물어보세요.").strip()
    state = st.session_state.get("verify")
    if state and state["question"] != question:
        _reset()
        state = None
        st.info("질문이 바뀌어 이전 검증 결과를 지웠습니다.")

    with st.container(horizontal=True):
        run = st.button("1. 질문 해석 실행", key="verify_interpret", type="primary", disabled=state is not None)
        st.button("다시 시작", key="verify_reset", on_click=_reset, disabled=state is None)
    if run:
        if not question:
            st.warning("질문을 입력하세요.")
            return
        try:
            pipeline = get_pipeline()
            with st.spinner("카탈로그를 읽고 질문을 해석하는 중입니다..."):
                st.session_state.verify = state = pipeline.verify_interpret(question)
        except Exception:
            st.error("실행 준비에 실패했습니다. Neo4j 연결 설정을 확인하세요.")
            return
    if not state:
        return

    _show_interpret(state)
    step = card_graphrag.next_step(state)
    if (state.get("search_parameters") or {}).get("benefit_keys"):
        _show_plan(state)
    if step == "retrieve" and st.button("3. DB 조회 실행", key="verify_retrieve", type="primary"):
        with st.spinner("Neo4j를 조회하는 중입니다..."):
            st.session_state.verify = get_pipeline().verify_retrieve(state)
        st.rerun()                      # 실행한 단계의 버튼이 화면에 남지 않게 한다
    if "retrieve" in state["path"]:
        _show_results(state)
    if step == "answer" and st.button("4. LLM 답변 생성", key="verify_answer", type="primary"):
        with st.spinner("조회 결과로 답변을 생성하는 중입니다..."):
            st.session_state.verify = get_pipeline().verify_answer(state)
        st.rerun()
    if step == "done":
        show_outcome(state)
