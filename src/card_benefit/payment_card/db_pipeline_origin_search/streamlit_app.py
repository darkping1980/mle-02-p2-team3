"""카드 혜택 GraphRAG 안내 화면. 개발자 모드에서만 단계별 개발 검증과 내부 진단 정보를 보여 준다."""
import re

from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag, verify_view
from card_benefit.payment_card.db_pipeline_origin_search.benefit_search_service import MODE_LABELS
from card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import GRAPH_PREFIX, QUERIES, connect
import streamlit as st

EXAMPLES = [
    "ONE PICK STYLE 카드의 대중교통 혜택은?",
    "전월 실적이 없어도 대중교통 캐시백을 받을 수 있어?",
    "ONE PICK과 STYLE 혜택의 차이는?",
    "놀이공원 할인율과 이용 횟수 제한은?",
    "1만원 이상 결제하면 캐시백은 얼마인가?",
    "JADE Classic의 브랜드별 연회비는?",
    "세 카드의 본인 연회비를 비교해 줘.",
    "우리카드 카드의정석 SHOPPING 온라인 쇼핑 10% 혜택과 연회비를 함께 알려줘.",
]
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

card_graphrag.configure_card_logging()      # 재실행마다 호출해도 handler는 공통 함수가 한 번만 붙인다.


@st.cache_resource(show_spinner=False)
def get_pipeline(search_mode: str = "A"):
    """재실행 사이에 모드별 드라이버와 그래프를 재사용한다. 예외는 캐시되지 않는다."""
    search = connect()
    benefit_search = None if search_mode == "A" else card_graphrag.create_benefit_search(search)
    return card_graphrag.CardGraphRAG(search, *card_graphrag.create_llms(), benefit_search=benefit_search,
                                      search_mode=search_mode)


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


def show_text(text: str) -> None:
    """원문 기호를 이스케이프하고, 한 줄 바꿈도 화면에서 줄이 바뀌게 표시한다."""
    cleaned = customer_text(text)
    if cleaned:
        st.markdown("\n\n".join(plain(part).replace("\n", "  \n") for part in cleaned.split("\n\n")))


def dev_mode() -> bool:
    return bool(st.session_state.get("dev_mode"))


def use_example() -> None:
    """예시 선택은 입력창만 채운다. LLM은 호출하지 않는다."""
    if st.session_state.example:
        st.session_state.question = st.session_state.example


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
    """마지막 실행 결과를 표시한다. 위젯 재실행은 이 저장값만 읽는다."""
    answer = outcome["answer"]
    evidence = outcome.get("evidence") or []
    pages = {item["evidence_id"]: item["page_no"] for item in evidence}
    st.subheader(CUSTOMER_TITLES.get(answer["status"], "검색 결과"), anchor=False)
    st.caption(f"질문: {outcome['question']}")
    if answer["status"] == "ERROR":
        st.error(ERROR_TEXT)
    elif answer["message"]:
        message = CUSTOMER_MESSAGES.get(answer["message"]) or customer_text(answer["message"])
        if message:
            st.info(plain(message))
    ambiguity = (outcome.get("search_parameters") or {}).get("ambiguity")
    if ambiguity and answer["points"]:
        st.info("참고: " + plain(ambiguity))
    if answer.get("answer_text"):
        show_text(answer["answer_text"])
    elif answer["conclusion"]:
        conclusion = customer_text(answer["conclusion"])
        if conclusion:
            st.markdown(f"**{plain(conclusion)}**")
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
    if not dev_mode():
        return
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


st.set_page_config(page_title="카드 혜택 안내", layout="wide")
st.title("카드 혜택 안내", anchor=False)
st.caption("카드 상품설명서(PDF)에 근거해 혜택과 연회비를 안내합니다. 실제 적용 조건은 카드사 안내를 함께 확인해 주세요.")

with st.sidebar:
    st.toggle("개발자 모드", key="dev_mode", help="내부 검증 상태, LLM 호출 정보, 단계별 개발 검증 화면을 표시합니다.")
    if dev_mode():
        st.warning("개발용 미승인 자료입니다. 실제 카드 혜택으로 사용하지 마세요.")
        run_mode = st.radio("실행 모드", ("자동 실행", "개발 검증"), key="run_mode")
        force = st.checkbox("같은 질문도 다시 실행 (API 비용 발생)", key="force_rerun")
    else:
        run_mode, force = "자동 실행", False

if run_mode == "개발 검증":
    verify_view.render(get_pipeline, show_outcome)
    st.stop()

search_mode = st.radio("검색 방식", list(MODE_LABELS), format_func=lambda mode: f"{mode}: {MODE_LABELS[mode]}",
                       horizontal=True, key="search_mode")
st.pills("예시 질문", EXAMPLES, key="example", on_change=use_example)
with st.form("question_form"):
    question = st.text_area("질문", key="question", max_chars=card_graphrag.MAX_QUESTION_CHARS, height=80,
                            placeholder="카드 혜택이나 연회비를 자연어로 물어보세요.")
    submitted = st.form_submit_button("질문하기", type="primary")

if submitted:
    question = question.strip()
    last = st.session_state.get("outcome")
    if not question:
        st.warning("질문을 입력하세요.")
    elif (last and last["question"] == question and last.get("search_mode") == search_mode
          and not last.get("error") and not force):
        if dev_mode():
            st.info("같은 질문이라 API를 호출하지 않고 이전 결과를 표시합니다.")
        st.session_state.outcome = {**last, "reused": True}
    else:
        try:
            pipeline = get_pipeline(search_mode)
            with st.spinner("카드 혜택을 찾아 답변을 준비하고 있습니다..."):
                st.session_state.outcome = {**pipeline.run(question), "search_mode": search_mode}
        except Exception:
            st.session_state.outcome = None
            st.error(ERROR_TEXT)
            if dev_mode():
                st.caption("실행 준비에 실패했습니다. Neo4j 연결 설정을 확인하세요.")

if st.session_state.get("outcome"):
    show_outcome(st.session_state.outcome)
