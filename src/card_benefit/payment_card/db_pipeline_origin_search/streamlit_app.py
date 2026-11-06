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
         그 외 → get_pipeline(SEARCH_MODE).run(question) → 결과 State를 session_state.outcome에 저장
    5. 검색 결과는 요청당 한 번 로그에 저장하고, 일반 화면에는 최종 답변만 출력
       (개발자 모드에서는 기존 상세 내용·PDF 근거와 진단 정보도 표시)

호출 관계
    get_pipeline → neo4j_search.connect, card_graphrag.create_llms, (N) card_graphrag.create_neo4j_benefit_search
                   (A/B/C 경로는 회귀 검증용으로 get_pipeline("A"|"B"|"C")에 남아 있으며 화면에서는 고를 수 없다)
    show_outcome → show_text / show_open_items / show_evidence / show_generation (화면 출력 전용, DB·LLM 미사용)
    화면 문구 정리(customer_text 등)는 표시만 바꾸며 결과 State의 값은 바꾸지 않는다.
"""
import re
import sys
from pathlib import Path
from uuid import uuid4

# Cloud dependency installs do not install the project in editable mode.
_SRC_DIR = Path(__file__).resolve().parents[3]
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag, verify_view
from card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import CARD_LOGGER_NAME, GRAPH_PREFIX, QUERIES, connect
from card_benefit.payment_card.db_pipeline_origin_search.execution_log import (
    app_db_log_enabled, capture_request_queries, configure_application_logging, error_message,
    log_event, outcome_detail_text, outcome_pdf_evidence_text, outcome_neo4j_summary,
    outcome_pdf_evidence_summary, persist_app_logs, request_pipeline,
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
STATUS_LABELS = {"ANSWERED": "답변", "PARTIAL": "일부 답변 (검증 실패 문장 제외 또는 검토 필요 항목 포함)",
                 "NOT_ANSWERABLE": "답변 불가", "ERROR": "실행 오류"}   # 개발자 정보에서만 쓴다.
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
VERIFICATION_LABELS = {"RAW_MATCH": "값이 인용 원문과 일치", "STRUCTURED_ONLY": "값이 구조화 데이터와 일치, 인용 원문에서는 미확인",
                       "CALCULATED": "인용 원문 값으로 계산한 차이", "NOT_CHECKED": "값이 없는 문장, 내용 일치 미검사"}
APPROVAL_LABELS = {"PENDING": "검토 대기", "APPROVED": "승인", "REJECTED": "반려"}
SOURCE_LABELS = {"llm": "LLM이 작성한 문장을 그대로 표시", "validated_sentences": "LLM 문장이 검증을 통과하지 못해 근거 확인 문장을 표시",
                 "program_exclusion": "제외 대상이라 프로그램 고정 문구로 표시",
                 "program_tier": "LLM 문장이 금액 구간 검증을 통과하지 못해 조회 값으로 만든 구간 안내를 표시",
                 "program_fee": "연회비는 등록 값(item_data)으로 프로그램이 작성. LLM 미사용", "none": "답변 문장 없음"}
NODE_LABELS = {"interpret": "질문 해석", "answer": "답변 생성"}
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+\-.!|~$:])")
# 사용자 화면에서만 지우는 내부 검증 표현. 판정·로그·결과 JSON은 그대로다.
_FEE_REVIEW_SUFFIX = re.compile(r"\s*—\s*검토 필요:[^\n]*")
_STATUS_CODE = re.compile(r"(?<![A-Za-z_])(?:PENDING_REVIEW|PENDING|DRAFT|REVIEW)(?![A-Za-z_])")
_STATUS_PHRASE = re.compile(r"일부 답변|검토 필요 항목 포함|검증 실패 문장 제외|원문 추출\s*\(검토 대기\)|검토 대기|검토 필요"
                            r"|담당자 검토|개발용|미승인")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_FACT = re.compile(r"\d")
# endregion

card_graphrag.configure_card_logging()      # 재실행마다 호출해도 handler는 공통 함수가 한 번만 붙인다.
APP_DB_LOG_ENABLED = app_db_log_enabled()
configure_application_logging(APP_DB_LOG_ENABLED, CARD_LOGGER_NAME)
st.session_state.setdefault("execution_log_session_id", str(uuid4()))


# region 파이프라인 생성 (모드별 캐시)
SEARCH_MODE = "N"   # 화면 기본 검색 경로: Neo4j 단일 GraphRAG 검색

@st.cache_resource(show_spinner=False)
def get_pipeline(search_mode: str = SEARCH_MODE):
    """재실행 사이에 모드별 드라이버와 그래프를 재사용한다. 예외는 캐시되지 않는다.

    ``search_mode`` 값마다 CardGraphRAG 인스턴스가 하나씩 캐시된다(인자가 캐시 키).

    Args:
        search_mode: N(기본, Neo4j 단일 하이브리드 검색). A/B/C는 회귀 검증용으로만 남긴다.

    Returns:
        CardGraphRAG. N은 Neo4jBenefitSearch(Neo4j + 질문 임베딩)만 쓰고 PostgreSQL 업무 데이터를 조회하지 않는다.
        A는 benefit_search=None이라 PostgreSQL에 접속하지 않는다. B·C는 BenefitSearchService(PostgreSQL + OpenAI 임베딩 + Neo4j)를 함께 넘긴다.
        OPENAI_API_KEY가 없으면 create_llms가 (None, None)을 돌려주고, 질문 시 LLM_NOT_CONFIGURED로 끝난다.
    """
    search = connect()
    if search_mode == "N":
        benefit_search = card_graphrag.create_neo4j_benefit_search(search)
    else:
        benefit_search = None if search_mode == "A" else card_graphrag.create_benefit_search(search)
    return card_graphrag.CardGraphRAG(search, *card_graphrag.create_llms(), benefit_search=benefit_search,
                                      search_mode=search_mode)
# endregion


# region 표시용 문자열 정리 (값을 바꾸지 않고 화면 문구만 정리)
def plain(text: str) -> str:
    """원문의 기호가 마크다운 서식으로 바뀌지 않게 한다."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def customer_sentence(sentence: str) -> str:
    """내부 상태 표현이 든 문장을 정리한다.

    숫자(금액·비율·횟수)가 있는 문장은 사실을 지우지 않고 상태 표현만 뺀다.
    숫자 없이 자료 상태만 말하는 문장(예: 담당자 검토 전 안내)은 혜택 사실이 아니므로 통째로 뺀다.
    """
    if not (_STATUS_CODE.search(sentence) or _STATUS_PHRASE.search(sentence)):
        return sentence
    if not _FACT.search(sentence):
        return ""
    text = _STATUS_PHRASE.sub("", _STATUS_CODE.sub("", sentence))
    text = re.sub(r"\(\s*[,·/]?\s*\)|\[\s*\]", "", text)      # 비어 버린 괄호
    text = re.sub(r"\s*[—·,]\s*(?=[.!?]?$)", "", text)        # 끝에 남은 구분 기호
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def customer_text(text: str) -> str:
    """사용자에게 보여 줄 답변 본문. 줄 구조는 유지하고 내부 검증 문구만 정리한다."""
    lines = []
    for line in _FEE_REVIEW_SUFFIX.sub("", text or "").split("\n"):
        if not line.strip():
            lines.append("")
            continue
        kept = " ".join(item for item in (customer_sentence(part) for part in _SENTENCE_END.split(line)) if item)
        if kept:
            lines.append(kept)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def customer_response_for_log(outcome: dict) -> str:
    """저장되는 응답 본문을 최종 답변 전체 우선으로 선택한다."""
    answer = outcome.get("answer") or {}
    if answer.get("status") == "ERROR":
        return ""
    final_text = answer.get("answer_text") or answer.get("conclusion")
    if final_text:
        return customer_text(str(final_text))
    message = answer.get("message")
    if message:
        return CUSTOMER_MESSAGES.get(message) or customer_text(message)
    return customer_text(response_message(outcome))


def show_text(text: str) -> None:
    """원문 기호를 이스케이프하고, 한 줄 바꿈도 화면에서 줄이 바뀌게 표시한다."""
    cleaned = customer_text(text)
    if cleaned:
        st.markdown("\n\n".join(plain(part).replace("\n", "  \n") for part in cleaned.split("\n\n")))
# endregion


# region 결과 화면 출력 (show_outcome과 하위 출력 함수)
def dev_mode() -> bool:
    """사이드바 '개발자 모드' 토글 값(session_state['dev_mode'])."""
    return bool(st.session_state.get("dev_mode"))


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
    source = (outcome.get("answer") or {}).get("answer_source", "none")
    lines.append(f"답변 문장: {SOURCE_LABELS.get(source, source)} · 다른 모델로 전환 없음 · 재시도 0회")
    with st.expander("답변 생성 정보 (API 호출·캐시)"):
        for line in lines:
            st.text(line)


def show_open_items(outcome: dict, pages: dict) -> None:
    """미확정 카드 이용 조건과 자료 검토 상태를 구분해 표시한다."""
    conditions = outcome.get("open_conditions") or []
    uncertain = outcome["answer"]["uncertain"]
    notices = outcome.get("data_notices") or []
    uncertain = [text for text in dict.fromkeys(customer_text(item) for item in uncertain) if text]
    if not (conditions or uncertain or (notices and dev_mode())):
        return
    st.subheader("확인이 필요한 사항", anchor=False)
    if conditions or uncertain:
        st.markdown("**카드 이용 조건**")
    for item in conditions:
        st.markdown(f"- **{plain(item['topic'])}** ({plain(', '.join(item['benefits']))}): {plain(customer_text(item['open']))}")
        cited = ", ".join(f"{evidence_id} ({pages[evidence_id]}쪽)" for evidence_id in item["evidence_ids"] if evidence_id in pages)
        st.caption(f"PDF 표기: {plain(item['confirmed'])}" + (f" · 근거: {cited}" if cited else ""))
    for text in uncertain:
        st.markdown("- " + plain(text))
    if notices and dev_mode():
        st.markdown("**자료 검토 상태** (카드 이용 조건이 아닌 개발 자료 안내)")
        for text in notices:
            st.caption(plain(text))


def show_outcome(outcome: dict) -> None:
    """마지막 실행 결과를 표시한다. 위젯 재실행은 이 저장값만 읽는다.

    Args:
        outcome: CardGraphRAG.run이 돌려준 최종 CardState(dict) + search_mode(+ 재사용 시 reused).
            주로 읽는 키: answer(status·message·answer_text·conclusion·points·fee_rows·uncertain),
            evidence, open_conditions, data_notices, search_parameters, (개발자) llm_calls·path·context 등.

    일반 화면은 답변 본문(answer_text, 없으면 conclusion)과 실행 오류·답변 불가 안내만 표시한다.
    개발자 모드에서는 기존 연회비·상세 내용·확인 필요 사항·PDF 근거와 진단 정보를 계속 표시한다.
    """
    answer = outcome["answer"]
    # evidence_id → 페이지 번호. 문장 출처와 근거 목록에 쪽수를 붙일 때 쓴다.
    evidence = outcome.get("evidence") or []
    pages = {item["evidence_id"]: item["page_no"] for item in evidence}
    st.subheader(CUSTOMER_TITLES.get(answer["status"], "검색 결과"), anchor=False)
    if dev_mode():
        st.caption(f"질문: {outcome['question']}")
    if answer["status"] == "ERROR":
        st.error(ERROR_TEXT)
    elif answer["message"]:
        message = CUSTOMER_MESSAGES.get(answer["message"]) or customer_text(answer["message"])
        if message:
            st.info(plain(message))
    ambiguity = (outcome.get("search_parameters") or {}).get("ambiguity")
    if dev_mode() and ambiguity and answer["points"]:
        st.info("참고: " + plain(ambiguity))
    if answer.get("answer_text"):
        show_text(answer["answer_text"])
    elif answer["conclusion"]:
        conclusion = customer_text(answer["conclusion"])
        if conclusion:
            st.markdown(f"**{plain(conclusion)}**")
    if not dev_mode():
        return
    if answer.get("fee_rows"):
        st.subheader("연회비", anchor=False)
        st.dataframe(answer["fee_rows"], hide_index=True)   # '상태' 열을 포함해 표는 그대로 보여 준다.
        st.caption("금액은 카드 상품설명서의 연회비 표를 기준으로 합니다. 원문에 없는 금액은 '-'로 표시합니다. "
                   "항목별 확인 상태는 '상태' 열을 참고해 주세요.")
    names = list(dict.fromkeys(point["benefit_name"] for point in answer["points"]))
    if names:
        st.subheader("상세 내용", anchor=False)
    for name in names:
        if len(names) > 1 or name:
            st.markdown(f"**{plain(name or '혜택 공통')}**")
        for point in (item for item in answer["points"] if item["benefit_name"] == name):
            text = customer_text(point["text"])
            if text:
                st.markdown(plain(text))
            source_text = "출처: " + ", ".join(f"{item} ({pages[item]}쪽)" for item in point["evidence_ids"])
            if dev_mode():
                origin = " · 프로그램이 조회 값으로 작성" if point["origin"] == "system" else ""
                source_text += f" · {VERIFICATION_LABELS[point['verification']]}{origin}"
            st.caption(source_text)
    show_open_items(outcome, pages)
    # PDF 근거를 "답변 문장이 인용한 근거"와 "조회는 됐지만 인용되지 않은 근거"로 나눠 보여 준다.
    cited = {item for point in answer["points"] for item in point["evidence_ids"]}
    cited.update(item for condition in outcome.get("open_conditions") or [] for item in condition["evidence_ids"])
    used = [item for item in evidence if item["evidence_id"] in cited]
    others = [item for item in evidence if item["evidence_id"] not in cited]
    if evidence:
        st.subheader(f"PDF 근거 ({len(used)})", anchor=False)
        for item in used:
            show_evidence(item)
        with st.expander(f"그 밖의 관련 원문 ({len(others)})"):
            for item in others:
                show_evidence(item)
    show_generation(outcome)
    with st.expander("개발자 정보"):
        st.markdown(f"**판정** `{answer['status']}` ({plain(STATUS_LABELS.get(answer['status'], answer['status']))}) · "
                    f"**요청** `{outcome['request_id']}` · **유형** `{outcome.get('intent')}` · "
                    f"**실행 경로** `{' → '.join(outcome['path'])}`")
        if answer.get("message"):
            st.caption("원래 안내 문구: " + plain(answer["message"]))
        if outcome.get("error"):
            st.json(outcome["error"])
        for warning in outcome["warnings"]:
            st.warning(warning)
        if outcome.get("other_unresolved"):
            st.markdown("**고객 화면에서 뺀 미확정 사항** (이번 질문과 직접 관련 없음)")
            for text in outcome["other_unresolved"]:
                st.caption(plain(text))
        st.markdown("**LLM 호출과 토큰**")
        st.dataframe(outcome["llm_calls"], hide_index=True)
        total = sum(call["cost_usd"] or 0 for call in outcome["llm_calls"])
        st.caption(f"추정 비용 합계 USD {total:.6f}")
        if outcome.get("candidate_search"):
            st.markdown("**후보 검색 결과** (유사도는 후보 선정에만 사용)")
            st.dataframe(outcome["candidate_search"]["hits"], hide_index=True)
            st.caption(f"엔진 {outcome['candidate_search'].get('engines')} · {outcome['candidate_search']['elapsed_ms']:.0f} ms")
        if outcome.get("retrieval_trace"):
            st.markdown("**혜택별 상세 조회 엔진**")
            st.dataframe(outcome["retrieval_trace"], hide_index=True)
        st.markdown("**검색 조건**")
        st.json(outcome.get("search_parameters") or {})
        st.markdown(f"**실행한 Cypher** (라벨 접두사 `{GRAPH_PREFIX}`)")
        st.write(outcome.get("statements") or [])
        st.markdown("**LLM에 전달한 검색 결과**")
        st.json(outcome.get("context") or {}, expanded=False)
        st.markdown("**Neo4j 조회 원본**")
        st.json(outcome.get("retrieved_data") or [], expanded=False)
        st.markdown("**Cypher 템플릿**")
        for name, query in QUERIES.items():
            st.caption(name)
            st.code(query, language="cypher")
# endregion


# region 페이지 본문 (Streamlit 재실행마다 위에서부터 실행되는 진입점)
st.set_page_config(page_title="카드 혜택 안내", layout="wide")
st.title("카드 혜택 안내", anchor=False)
st.caption("하나·우리카드 상품설명서의 근거로 혜택과 연회비를 안내합니다. 실제 적용 조건은 카드사 안내를 함께 확인해 주세요.")
with st.expander("지원 카드 10종 보기", expanded=False):
    card_columns = st.columns(2)
    for column, (issuer, cards) in zip(card_columns, SUPPORTED_CARDS.items()):
        with column:
            st.markdown(f"**{issuer}**")
            for card in cards:
                st.markdown(f"- {card}")
st.caption("카드를 선택하지 않아도 됩니다. 카드 혜택 추천·비교를 포함해 자유롭게 질문해 주세요.")

with st.sidebar:
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

search_mode = SEARCH_MODE   # 화면에서 검색 방식을 고르지 않는다(Neo4j 단일 검색 고정)
st.pills("예시 질문", EXAMPLES, key="example", on_change=use_example)
with st.form("question_form"):
    question = st.text_area("질문", key="question", max_chars=card_graphrag.MAX_QUESTION_CHARS, height=80,
                            placeholder="카드 혜택이나 연회비를 자연어로 물어보세요.")
    submitted = st.form_submit_button("질문하기", type="primary")

# 질문 제출 처리. submitted는 폼 버튼을 누른 그 재실행에서만 True다.
if submitted:
    question = question.strip()
    session_id = st.session_state.execution_log_session_id
    request_id = str(uuid4())
    last = st.session_state.get("outcome")
    if not question:
        st.warning("질문을 입력하세요.")
    # 분기: 직전과 같은 질문·모드이고 오류가 없었으면 LLM 비용을 쓰지 않고 이전 결과를 재사용한다.
    elif (last and last["question"] == question and last.get("search_mode") == search_mode
          and not last.get("error") and not force):
        request_event = log_event("REQUEST", question)
        if dev_mode():
            st.info("같은 질문이라 API를 호출하지 않고 이전 결과를 표시합니다.")
        st.session_state.outcome = {**last, "reused": True}
        if APP_DB_LOG_ENABLED:
            events = [request_event,
                      log_event("RESPONSE", customer_response_for_log(st.session_state.outcome))]
            persist_app_logs(session_id, request_id, events,
                             detail_text=outcome_detail_text(st.session_state.outcome),
                             pdf_evidence_text=outcome_pdf_evidence_text(st.session_state.outcome),
                             neo4j_summary=outcome_neo4j_summary(st.session_state.outcome),
                             pdf_evidence_summary=outcome_pdf_evidence_summary(st.session_state.outcome))
    else:
        request_event = log_event("REQUEST", question)
        cleanup = lambda: None
        query_events = []
        outcome_for_log = None
        try:
            base_pipeline = get_pipeline(search_mode)
            if APP_DB_LOG_ENABLED:
                pipeline, cleanup = request_pipeline(base_pipeline, search_mode)
            else:
                pipeline = base_pipeline
            with st.spinner("카드 혜택을 찾아 답변을 준비하고 있습니다..."):
                # GraphRAG 실행: interpret → (retrieve → answer) → finish. 반환값은 최종 State(dict)다.
                # 노드가 직접 잡는 실패(LLM·Neo4j·후보 검색)는 예외가 아니라 State의 error와 answer.status=ERROR로 돌아온다.
                with capture_request_queries() as query_events:
                    st.session_state.outcome = {**pipeline.run(question), "search_mode": search_mode}
                outcome_for_log = st.session_state.outcome
        except Exception as e:
            import traceback
            traceback.print_exc()

            st.session_state.outcome = None
            st.error(ERROR_TEXT)
            if dev_mode():
                st.exception(e)
        finally:
            cleanup()
            if APP_DB_LOG_ENABLED:
                events = [request_event, *query_events]
                error = error_message(outcome_for_log)
                if error:
                    events.append(log_event("ERROR", error))
                else:
                    events.append(log_event("RESPONSE", customer_response_for_log(outcome_for_log or {})))
                persist_app_logs(session_id, request_id, events,
                                 detail_text=outcome_detail_text(outcome_for_log),
                                 pdf_evidence_text=outcome_pdf_evidence_text(outcome_for_log),
                                 neo4j_summary=outcome_neo4j_summary(outcome_for_log),
                                 pdf_evidence_summary=outcome_pdf_evidence_summary(outcome_for_log))

# 재실행마다 저장된 마지막 결과를 다시 그린다(위젯 조작만 해도 결과가 화면에 남는 이유).
if st.session_state.get("outcome"):
    show_outcome(st.session_state.outcome)
# endregion
