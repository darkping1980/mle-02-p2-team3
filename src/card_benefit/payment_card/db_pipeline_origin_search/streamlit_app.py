"""카드 혜택 GraphRAG 로컬 개발 화면. 질문 실행 버튼을 눌렀을 때만 LangGraph를 실행한다."""
from pathlib import Path
import re
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.card_benefit.payment_card.db_pipeline_origin_search import card_graphrag  # noqa: E402
from src.card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import NAMESPACE, QUERIES, connect  # noqa: E402

EXAMPLES = [
    "ONE PICK STYLE 카드의 대중교통 혜택은?",
    "전월 실적이 없어도 대중교통 캐시백을 받을 수 있어?",
    "ONE PICK과 STYLE 혜택의 차이는?",
    "놀이공원 할인율과 이용 횟수 제한은?",
    "1만원 이상 결제하면 캐시백은 얼마인가?",
]
STATUS_LABELS = {"ANSWERED": "답변", "PARTIAL": "일부 답변 (검증 실패 문장 제외)",
                 "NOT_ANSWERABLE": "답변 불가", "ERROR": "실행 오류"}
VERIFICATION_LABELS = {"RAW_MATCH": "값이 인용 원문과 일치", "STRUCTURED_ONLY": "값이 구조화 데이터와 일치, 인용 원문에서는 미확인",
                       "CALCULATED": "인용 원문 값으로 계산한 차이", "NOT_CHECKED": "값이 없는 문장, 내용 일치 미검사"}
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+\-.!|~$:])")

card_graphrag.configure_card_logging()      # 재실행마다 호출해도 handler는 공통 함수가 한 번만 붙인다.


@st.cache_resource(show_spinner=False)
def get_pipeline():
    """재실행 사이에 Neo4j 드라이버와 그래프를 재사용한다. 예외는 캐시되지 않는다."""
    return card_graphrag.CardGraphRAG(connect(), *card_graphrag.create_llms())


def plain(text: str) -> str:
    """원문의 기호가 마크다운 서식으로 바뀌지 않게 한다."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def use_example() -> None:
    """예시 선택은 입력창만 채운다. LLM은 호출하지 않는다."""
    if st.session_state.example:
        st.session_state.question = st.session_state.example


def show_evidence(item: dict) -> None:
    """근거 한 건을 페이지·상태·ID와 원문 그대로 표시한다."""
    st.markdown(f"**{item['page_no']}쪽** · {item['approval_status']} · `{item['evidence_id']}`")
    st.text(item["quote"])


def show_outcome(outcome: dict) -> None:
    """마지막 실행 결과를 표시한다. 위젯 재실행은 이 저장값만 읽는다."""
    answer = outcome["answer"]
    evidence = outcome.get("evidence") or []
    pages = {item["evidence_id"]: item["page_no"] for item in evidence}
    st.subheader(STATUS_LABELS[answer["status"]], anchor=False)
    st.caption(f"질문: {outcome['question']}")
    if answer["status"] == "ERROR":
        st.error(answer["message"])
    elif answer["message"]:
        st.info(answer["message"])
    ambiguity = (outcome.get("search_parameters") or {}).get("ambiguity")
    if ambiguity and answer["points"]:
        st.info("질문에서 불명확한 점: " + plain(ambiguity))
    if answer["conclusion"]:
        st.markdown(f"**{plain(answer['conclusion'])}**")
    names = list(dict.fromkeys(point["benefit_name"] for point in answer["points"]))
    for name in names:
        if len(names) > 1 or name:
            st.markdown(f"**{plain(name or '혜택 공통')}**")
        for point in (item for item in answer["points"] if item["benefit_name"] == name):
            st.markdown(plain(point["text"]))
            origin = " · 프로그램이 조회 값으로 작성" if point["origin"] == "system" else ""
            st.caption("근거: " + ", ".join(f"{item} ({pages[item]}쪽)" for item in point["evidence_ids"])
                       + f" · {VERIFICATION_LABELS[point['verification']]}{origin}")
    unresolved = [*answer["uncertain"], *(outcome.get("unresolved") or [])]
    if unresolved:
        st.subheader("미확정 사항", anchor=False)
        for text in dict.fromkeys(unresolved):
            st.markdown("- " + plain(text))
    cited = {item for point in answer["points"] for item in point["evidence_ids"]}
    used = [item for item in evidence if item["evidence_id"] in cited]
    others = [item for item in evidence if item["evidence_id"] not in cited]
    if evidence:
        st.subheader(f"PDF 근거 ({len(used)})", anchor=False)
        for item in used:
            show_evidence(item)
        with st.expander(f"답변에 인용되지 않은 조회 근거 ({len(others)})"):
            for item in others:
                show_evidence(item)
    with st.expander("개발자 정보"):
        st.markdown(f"**요청** `{outcome['request_id']}` · **유형** `{outcome.get('intent')}` · "
                    f"**실행 경로** `{' → '.join(outcome['path'])}`")
        if outcome.get("error"):
            st.json(outcome["error"])
        for warning in outcome["warnings"]:
            st.warning(warning)
        st.markdown("**LLM 호출과 토큰**")
        st.dataframe(outcome["llm_calls"], hide_index=True)
        total = sum(call["cost_usd"] or 0 for call in outcome["llm_calls"])
        st.caption(f"추정 비용 합계 USD {total:.6f}")
        st.markdown("**검색 조건**")
        st.json(outcome.get("search_parameters") or {})
        st.markdown(f"**실행한 Cypher** (namespace `{NAMESPACE}`)")
        st.write(outcome.get("statements") or [])
        st.markdown("**LLM에 전달한 검색 결과**")
        st.json(outcome.get("context") or {}, expanded=False)
        st.markdown("**Neo4j 조회 원본**")
        st.json(outcome.get("retrieved_data") or [], expanded=False)
        st.markdown("**Cypher 템플릿**")
        for name, query in QUERIES.items():
            st.caption(name)
            st.code(query, language="cypher")


st.set_page_config(page_title="카드 혜택 GraphRAG", layout="wide")
st.title("카드 혜택 GraphRAG — 개발 테스트", anchor=False)
st.warning("ONE PICK STYLE 개발용 DRAFT·미승인 데이터입니다. 실제 카드 혜택으로 사용하지 마세요.")

st.pills("예시 질문", EXAMPLES, key="example", on_change=use_example)
with st.form("question_form"):
    question = st.text_area("질문", key="question", max_chars=card_graphrag.MAX_QUESTION_CHARS, height=80,
                            placeholder="카드 혜택을 자연어로 물어보세요.")
    force = st.checkbox("같은 질문도 다시 실행 (API 비용 발생)", key="force_rerun")
    submitted = st.form_submit_button("질문 실행", type="primary")

if submitted:
    question = question.strip()
    last = st.session_state.get("outcome")
    if not question:
        st.warning("질문을 입력하세요.")
    elif last and last["question"] == question and not last.get("error") and not force:
        st.info("같은 질문이라 API를 호출하지 않고 이전 결과를 표시합니다.")
    else:
        try:
            pipeline = get_pipeline()
            with st.spinner("질문 해석, Neo4j 조회, 답변 생성을 실행하는 중입니다..."):
                st.session_state.outcome = pipeline.run(question)
        except Exception:
            st.session_state.outcome = None
            st.error("실행 준비에 실패했습니다. Neo4j 연결 설정을 확인하세요.")

if st.session_state.get("outcome"):
    show_outcome(st.session_state.outcome)
