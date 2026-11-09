"""카드 혜택 GraphRAG 안내 화면. 개발자 모드에서만 단계별 개발 검증과 내부 진단 정보를 보여 준다.

[전체 흐름에서의 위치] 사용자 입력 → (이 파일) → card_graphrag.CardGraphRAG.run → (이 파일) 화면 출력

Streamlit 실행 모델 (Java 개발자 참고)
    Streamlit은 버튼 클릭·입력 변경 같은 이벤트마다 이 스크립트를 "위에서 아래로 다시 실행"한다.
    Servlet처럼 요청마다 핸들러를 부르는 방식이 아니다. 그래서
      - 재실행 사이에 유지할 값은 ``st.session_state`` (세션 저장소)에 둔다. 예: 마지막 결과 ``outcome``
      - 비싼 객체(Neo4j 드라이버, LLM 클라이언트, 그래프)는 ``@st.cache_resource`` 로 프로세스 단위로 재사용한다.

처리 흐름 (파일 맨 아래의 모듈 수준 코드)
    1. 사이드바: 개발자 모드 토글, (개발자 모드일 때) 실행 모드(자동 실행 / 개발 검증)와 강제 재실행 체크
    2. 실행 모드가 "개발 검증"이면 verify_view.render로 단계별 화면을 그리고 st.stop()
    3. 예시 질문, 질문 폼 (검색 방식 선택 없음: 항상 N = Neo4j 단일 검색)
    4. "질문하기" 제출 시:
         같은 질문·같은 모드·이전 오류 없음·강제 재실행 아님 → 이전 결과 재사용(LLM 미호출)
         그 외 → get_pipeline().run(question) → 결과 State를 session_state.outcome에 저장
    5. 검색 결과는 요청당 한 번 로그에 저장하고, 일반 화면에는 최종 답변만 출력
       (개발자 모드에서는 기존 상세 내용·PDF 근거와 진단 정보도 표시)

호출 관계
    get_pipeline → neo4j_search.connect, card_graphrag.create_llms, (N) card_graphrag.create_neo4j_benefit_search
                   (A/B/C 경로는 회귀 검증용으로 get_pipeline("A"|"B"|"C")에 남아 있으며 화면에서는 고를 수 없다)
    show_outcome → show_text / show_open_items / show_evidence / show_generation (화면 출력 전용, DB·LLM 미사용)
"""
import os
import re
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

# Cloud dependency installs do not install the project in editable mode.
_SRC_DIR = Path(__file__).resolve().parents[3]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag, verify_view
from card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import CARD_LOG, CARD_LOGGER_NAME, GRAPH_PREFIX, QUERIES, connect
from card_benefit.payment_card.db_pipeline_origin_search.execution_log import (
    app_db_log_enabled, capture_request_queries, configure_application_logging, error_message,
    log_event, outcome_detail_text, outcome_pdf_evidence_text, outcome_neo4j_summary,
    outcome_pdf_evidence_summary, persist_app_logs,
    response_message,
)
import streamlit as st

# region 화면 상수 (예시 질문, 상태·출처 표시 문구, 사용자 화면에서 지울 내부 표현 정규식)
EXAMPLE_QUESTIONS = {
    "ONE PICK 대중교통": "ONE PICK STYLE 카드의 대중교통 혜택은?",
    "DAILY 배달앱": "카드의정석2 DAILY의 배달앱 5% 할인 조건은?",
    "SIMPLE 제외 항목": "카드의정석2 SIMPLE의 0.8% 할인 제외 항목은?",
    "DAILY 통합 한도": "DAILY 카드의 고정소비·정기결제 통합 할인한도는?",
    "JADE 연회비": "JADE Classic의 브랜드별 연회비는?",
    "연회비 비교": "ONE PICK STYLE과 JADE Classic의 연회비를 비교해 줘.",
}
EXAMPLES = list(EXAMPLE_QUESTIONS)
SUPPORTED_CARDS = {
    "하나카드": ["ONE PICK STYLE", "JADE Classic", "JADE First", "JADE Prime", "더 심플 하나카드"],
    "우리카드": ["카드의정석 SHOPPING", "EVERY WON POINT", "카드의정석 POINT II", "카드의정석2 DAILY", "카드의정석2 SIMPLE"],
}
# 사용자 화면 제목. 판정(status) 값은 바꾸지 않고 표시 문구만 고른다.
CUSTOMER_TITLES = {"ANSWERED": "카드 혜택 안내", "PARTIAL": "카드 혜택 안내", "NOT_ANSWERABLE": "검색 결과", "ERROR": "검색 결과"}
ERROR_TEXT = "일시적인 문제로 답변을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요."
# 개발용 안내 문구를 사용자 화면용 문구로 바꾼다. 원래 문구는 개발자 정보에 남는다.
CUSTOMER_MESSAGES = {
    card_graphrag.MESSAGES["UNSUPPORTED"]: "등록된 카드의 혜택 내용·이용 조건·한도·연회비에 대해 물어봐 주세요.",
    card_graphrag.MESSAGES["NO_TARGET"]: "질문하신 내용에 해당하는 카드 혜택은 확인된 정보가 없습니다.",
    card_graphrag.MESSAGES["NO_RESULT"]: "질문하신 혜택은 확인된 정보가 없습니다.",
    card_graphrag.MESSAGES["NO_EVIDENCE"]: "상품설명서에서 확인된 정보가 없어 답변을 드리기 어렵습니다.",
    card_graphrag.MESSAGES["NO_GROUNDED_POINT"]: "상품설명서에서 질문에 맞는 내용을 확인하지 못했습니다. 아래 원문을 참고해 주세요.",
}
APPROVAL_LABELS = {"PENDING": "검토 대기", "APPROVED": "승인", "REJECTED": "반려"}
NODE_LABELS = {"interpret": "질문 해석", "answer": "답변 생성"}
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+\-.!|~$:])")
# 사용자 화면에서만 지우는 내부 검증 표현. 판정·로그·결과 JSON은 그대로다.
# endregion

card_graphrag.configure_card_logging()      # 재실행마다 호출해도 handler는 공통 함수가 한 번만 붙인다.
APP_DB_LOG_ENABLED = app_db_log_enabled()
DEVELOPER_UI_ENABLED = os.getenv("CARD_GRAPHRAG_ENABLE_DEVELOPER_UI", "").strip() == "1"
configure_application_logging(APP_DB_LOG_ENABLED, CARD_LOGGER_NAME)
st.session_state.setdefault("execution_log_session_id", str(uuid4()))


# region 파이프라인 생성 (모드별 캐시)
@st.cache_resource(show_spinner=False)                    # Spring의 Singleton Bean처럼 앱 전역에서 1회만 초기화하여 재사용(캐싱)
def get_pipeline():
    """Create and cache the sole Neo4j hybrid GraphRAG pipeline."""
    search = connect()                                    # Neo4j 드라이버 연결 및 검색 클라이언트 획득(Connection Pool 역할)
    candidate_search = card_graphrag.create_neo4j_benefit_search(search)  # N 모드용 Neo4j 하이브리드 검색 객체 생성(의존성 주입)
    return card_graphrag.CardGraphRAG(search, *card_graphrag.create_llms(), candidate_search=candidate_search)  # LangGraph 실행 파이프라인 싱글톤 생성 및 반환
# endregion


# region 표시용 문자열 정리 (값을 바꾸지 않고 화면 문구만 정리)
def plain(text: str) -> str:
    """원문의 기호가 마크다운 서식으로 바뀌지 않게 한다."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def customer_response_for_log(outcome: dict) -> str:
    """Return the Answer LLM's final text without rewriting it."""
    answer = outcome.get("answer") or {}
    if answer.get("status") == "ERROR":
        return ""
    final_text = answer.get("answer_text") or answer.get("conclusion")
    if final_text:
        return str(final_text)
    message = answer.get("message")
    if message:
        return CUSTOMER_MESSAGES.get(message) or str(message)
    return response_message(outcome)

def show_text(text: str) -> None:
    """Render the Answer LLM text while preserving its content."""
    if text:
        with st.container(key="answer_content"):
            st.markdown(str(text), unsafe_allow_html=False)

# endregion


# region 결과 화면 출력 (show_outcome과 하위 출력 함수)
def dev_mode() -> bool:
    """개발자 UI가 명시적으로 활성화된 환경에서만 내부 정보를 노출한다."""
    return DEVELOPER_UI_ENABLED and bool(st.session_state.get("dev_mode"))


def use_example() -> None:
    """간단한 예시 버튼을 누르면 전체 질문 문장을 입력창에 채운다."""
    if st.session_state.example:
        st.session_state.question = EXAMPLE_QUESTIONS[st.session_state.example]


def show_evidence(item: dict) -> None:
    """근거 한 건을 페이지·ID와 원문 그대로 표시한다. 검토 상태는 개발자 모드에서만 보인다."""
    status = APPROVAL_LABELS.get(item["approval_status"], item["approval_status"])
    label = f" · {status}" if dev_mode() else ""
    st.markdown(f"**{item['page_no']}쪽**{label} · `{item['evidence_id']}`")
    st.text(item["quote"])


def show_generation(outcome: dict) -> None:
    """이번 답변의 API 호출과 재사용 여부를 표시한다."""
    calls = outcome.get("llm_calls") or []
    lines = []
    if outcome.get("reused"):
        lines.append("이번 실행: API 미호출. 이전 결과를 화면에 다시 표시했습니다. 아래는 그때의 호출 기록입니다.")
    for call in calls:
        name = NODE_LABELS.get(call["node"], call["node"])
        if call["input_tokens"] is None:
            lines.append(f"{name}: {call['model']} 호출 실패 또는 사용량 없음")
            continue
        lines.append(f"{name}: {call['response_model'] or call['model']} 실제 호출 · 입력 {call['input_tokens']:,}토큰"
                     f"(OpenAI 프롬프트 캐시 적중 {call['cached_tokens'] or 0:,}) · 출력 {call['output_tokens']:,}토큰 · "
                     f"{(call['elapsed_ms'] or 0) / 1000:.1f}초")
    if not calls:
        lines.append("LLM 미호출: 호출 전에 종료된 경로입니다.")
    lines.append("답변 문장: Answer LLM 결과를 그대로 사용")
    with st.expander("답변 생성 정보 (API 호출·캐시)"):
        for line in lines:
            st.text(line)


def show_open_items(outcome: dict, pages: dict) -> None:
    """Show retrieved unresolved conditions and LLM uncertainty without rewriting their text."""
    conditions = outcome.get("open_conditions") or []
    uncertain = outcome["answer"].get("uncertain") or []
    notices = outcome.get("data_notices") or []
    if not (conditions or uncertain or (notices and dev_mode())):
        return
    st.subheader("확인이 필요한 사항", anchor=False)
    if conditions or uncertain:
        st.markdown("**카드 이용 조건**")
    for item in conditions:
        st.markdown(f"- **{plain(item['topic'])}** ({plain(', '.join(item['benefits']))}): {plain(item['open'])}")
        cited = ", ".join(f"{evidence_id} ({pages[evidence_id]}쪽)" for evidence_id in item["evidence_ids"] if evidence_id in pages)
        st.caption(f"PDF 확인: {plain(item['confirmed'])}" + (f" · 근거: {cited}" if cited else ""))
    for text in dict.fromkeys(uncertain):
        st.markdown("- " + plain(str(text)))
    if notices and dev_mode():
        st.markdown("**자료 검토 상태**")
        for text in notices:
            st.caption(plain(text))

def show_outcome(outcome: dict) -> None:
    """Render the final answer, its Evidence references, and developer diagnostics."""
    answer = outcome["answer"]
    evidence = outcome.get("evidence") or []
    pages = {item["evidence_id"]: item["page_no"] for item in evidence if item.get("evidence_id")}
    st.subheader(CUSTOMER_TITLES.get(answer["status"], "검색 결과"), anchor=False)
    if dev_mode():
        st.caption(f"질문: {outcome['question']}")
    if answer["status"] == "ERROR":
        st.error(ERROR_TEXT)
    elif answer.get("message"):
        message = CUSTOMER_MESSAGES.get(answer["message"]) or answer["message"]
        if message:
            st.info(plain(message))
    ambiguity = (outcome.get("search_parameters") or {}).get("ambiguity")
    if dev_mode() and ambiguity and answer.get("points"):
        st.info("참고: " + plain(ambiguity))
    if answer.get("answer_text"):
        show_text(answer["answer_text"])
    elif answer.get("conclusion"):
        st.markdown(f"**{plain(answer['conclusion'])}**")
    if dev_mode() or answer.get("uncertain"):
        show_open_items(outcome, pages)
    if not dev_mode():
        return
    benefit_names = {item.get("benefit_id"): item.get("name") for item in (outcome.get("context") or {}).get("benefits", [])}
    points = answer.get("points") or []
    benefit_ids = list(dict.fromkeys(point.get("benefit_id") for point in points))
    if points:
        st.subheader("상세 내용", anchor=False)
    for benefit_id in benefit_ids:
        name = benefit_names.get(benefit_id)
        if len(benefit_ids) > 1 or name:
            st.markdown(f"**{plain(name or benefit_id or '혜택 공통')}**")
        for point in (item for item in points if item.get("benefit_id") == benefit_id):
            if point.get("text"):
                st.markdown(plain(point["text"]))
            cited = point.get("evidence_ids") or []
            if cited:
                st.caption("출처: " + ", ".join(f"{item} ({pages[item]}쪽)" if item in pages else item for item in cited))
    cited_ids = {item for point in points for item in point.get("evidence_ids", [])}
    cited_ids.update(item for condition in outcome.get("open_conditions") or [] for item in condition.get("evidence_ids", []))
    used = [item for item in evidence if item.get("evidence_id") in cited_ids]
    others = [item for item in evidence if item.get("evidence_id") not in cited_ids]
    if evidence:
        st.subheader(f"PDF 근거 ({len(used)})", anchor=False)
        for item in used:
            show_evidence(item)
        with st.expander(f"인용되지 않은 검색 근거 ({len(others)})"):
            for item in others:
                show_evidence(item)
    show_generation(outcome)

# endregion


# region 페이지 본문 (Streamlit 재실행마다 위에서부터 실행되는 진입점)
st.set_page_config(page_title="카드 혜택 안내", layout="wide")

# Keep the answer readable on desktop while preserving left alignment.
st.markdown(
    """
    <style>
    .st-key-answer_content {
        width: 70%;
        max-width: 70%;
        margin-left: 0;
        text-align: left;
    }
    .st-key-answer_content p,
    .st-key-answer_content li {
        overflow-wrap: anywhere;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("카드 혜택 안내", anchor=False)
st.caption("하나·우리카드 상품설명서의 근거로 혜택과 연회비를 안내합니다. 실제 적용 조건은 카드사 안내를 함께 확인해 주세요.")
with st.expander("지원 카드 10종 보기", expanded=False):
    card_columns = st.columns(2)
    for column, (issuer, cards) in zip(card_columns, SUPPORTED_CARDS.items()):
        with column:
            st.markdown(f"**{issuer}**")
            for card in cards:
                st.markdown(f"- {card}")
    st.divider()
st.caption("카드를 선택하지 않아도 됩니다. 카드 혜택 추천·비교를 포함해 자유롭게 질문해 주세요.")

with st.sidebar:
    if DEVELOPER_UI_ENABLED:
        st.toggle("개발자 모드", key="dev_mode", help="내부 검증 상태, LLM 호출 정보, 단계별 개발 검증 화면을 표시합니다.")
    if dev_mode():
        st.warning("개발용 미승인 자료입니다. 실제 카드 혜택으로 사용하지 마세요.")
        run_mode = st.radio("실행 모드", ("자동 실행", "개발 검증"), key="run_mode")
        force = st.checkbox("같은 질문도 다시 실행 (API 비용 발생)", key="force_rerun")
    else:
        run_mode, force = "자동 실행", False

# 분기: 개발 검증 모드는 단계별 버튼 화면(verify_view)을 그리고 이후 자동 실행 화면은 그리지 않는다.
if run_mode == "개발 검증":
    verify_view.render(get_pipeline, show_outcome)
    st.stop()

st.pills("예시 질문", EXAMPLES, key="example", on_change=use_example)

# region 발표 시연용 예시 질문 버튼
DEMO_QUESTIONS = {
    "대중교통 혜택 조회": "ONE PICK STYLE 하나 체크카드의 ONE MORE 대중교통 캐시백 혜택과 적용 조건을 알려줘.",
    "두 카드 혜택 비교": "더 심플 하나카드와 카드의정석2 DAILY의 휴대전화 요금 자동납부 할인 조건과 한도를 비교해 줘.",
}

st.markdown("**🎤 발표 시연용 예시 질문**")
demo_cols = st.columns(2)
for col, (label, demo_q) in zip(demo_cols, DEMO_QUESTIONS.items()):
    with col:
        if st.button(label, key=f"demo_{label}", use_container_width=True):
            st.session_state.question = demo_q
            st.rerun()
# endregion

with st.form("question_form"):
    question = st.text_area("질문", key="question", max_chars=card_graphrag.MAX_QUESTION_CHARS, height=80,
                            placeholder="카드 혜택이나 연회비를 자연어로 물어보세요.")
    submitted = st.form_submit_button("질문하기", type="primary")

# 질문 제출 처리. submitted는 폼 버튼을 누른 그 재실행에서만 True다.
if submitted:                                             # 폼 제출 이벤트 발생 시 처리(HTTP POST 요청 처리와 유사)
    streamlit_request_started = perf_counter()            # 전체 처리 시간 측정을 위한 시작 타임스탬프 기록
    question = question.strip()                           # 사용자 입력 문자열 앞뒤 공백 제거(Java의 String.trim())
    session_id = st.session_state.execution_log_session_id  # 현재 브라우저 세션 ID(HttpSessionId와 유사) 추출
    request_id = str(uuid4())                             # 요청 추적을 위한 고유 트랜잭션 UUID 생성
    outcome_rendered = False
    if not question:                                      # 입력 검증: 빈 문자열 체크
        st.warning("질문을 입력하세요.")                  # 화면에 경고 알림 렌더링
    else:                                                 # 질문이 있으면 항상 파이프라인을 실행한다
        request_event = log_event("REQUEST", question)    # 요청 로그 이벤트 생성
        query_events = []                                 # 실행 도중 캡처될 Cypher/SQL 쿼리 로그 목록 초기화
        outcome_for_log = None                            # 로그 적재를 위한 최종 결과 변수 초기화
        try:
            pipeline = get_pipeline()                     # 싱글톤 파이프라인 인스턴스 획득
            with st.spinner("질문에 맞는 카드 혜택을 찾고 답변을 작성하고 있습니다..."):
                # GraphRAG 실행: interpret → (retrieve → answer) → finish. 반환값은 최종 State(dict)다.
                # 노드가 직접 잡는 실패(LLM·Neo4j·후보 검색)는 예외가 아니라 State의 error와 answer.status=ERROR로 돌아온다.
                with capture_request_queries() as query_events:  # 실행 중 발생한 DB 쿼리 인터셉트 및 수집
                    st.session_state.outcome = pipeline.run(question)  # LangGraph 파이프라인 진입점 호출 및 결과를 세션에 저장
                outcome_for_log = st.session_state.outcome
                if st.session_state.outcome:
                    show_outcome(st.session_state.outcome)
                    outcome_rendered = True
        except Exception as e:                            # 예기치 못한 런타임 예외 발생 시 폴백 처리
            import traceback                              # 스택 트레이스 출력을 위한 모듈 임포트
            traceback.print_exc()                         # 콘솔에 에러 스택 트레이스 로깅

            st.session_state.outcome = None               # 오류 발생 시 세션 결과 초기화
            st.error(ERROR_TEXT)                          # 화면에 사용자 친화적 에러 메시지 렌더링
            if dev_mode():                                # 개발 모드일 경우 세부 예외 정보 추가 렌더링
                st.exception(e)                           # 상세 예외 스택 UI에 출력
        finally:
            if APP_DB_LOG_ENABLED:                        # 요청 완료 후 항상 실행되는 로그 적재 블록
                events = [request_event, *query_events]   # 요청 이벤트와 수집된 쿼리 이벤트 병합
                error = error_message(outcome_for_log)    # 결과 딕셔너리에서 에러 메시지 추출
                if error:
                    events.append(log_event("ERROR", error))  # 에러 이벤트 목록에 추가
                else:
                    events.append(log_event("RESPONSE", customer_response_for_log(outcome_for_log or {})))  # 정상 응답 이벤트 추가
                app_log_started = perf_counter()          # DB 저장 시간 측정 시작
                persist_app_logs(session_id, request_id, events,  # PostgreSQL 원장 테이블에 세션/요청 단위 일괄 로깅
                                 detail_text=outcome_detail_text(outcome_for_log),
                                 pdf_evidence_text=outcome_pdf_evidence_text(outcome_for_log),
                                 neo4j_summary=outcome_neo4j_summary(outcome_for_log),
                                 pdf_evidence_summary=outcome_pdf_evidence_summary(outcome_for_log),
                                 llm_trace_events=(outcome_for_log or {}).get("llm_trace_events"))
                CARD_LOG.log_summary("PERF", (outcome_for_log or {}).get("request_id", request_id), phase="app_log_save",
                                     elapsed_ms=(perf_counter() - app_log_started) * 1000, reused=False)

# 재실행마다 저장된 마지막 결과를 다시 그린다(위젯 조작만 해도 결과가 화면에 남는 이유).
if st.session_state.get("outcome") and not (submitted and outcome_rendered):
    show_outcome(st.session_state.outcome)
if submitted:
    CARD_LOG.log_summary("PERF", (st.session_state.get("outcome") or {}).get("request_id", request_id),
                         phase="streamlit_request_total", elapsed_ms=(perf_counter() - streamlit_request_started) * 1000)
# endregion
