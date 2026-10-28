"""냉장고 재료 추천 GraphRAG — LangGraph 흐름: 입력 해석 → Neo4j 조회 → 근거 기반 답변.

    interpret  사용자 문장에서 식재료 입력어를 뽑는다(LLM 구조화 출력, 없으면 구분자 규칙).
               LLM이 뽑은 말 중 사용자 문장에 실제로 없는 것은 버린다(재료를 지어내지 않게).
               LLM이 없거나 실패한 문장형 입력은 DB 표준명·별칭을 문장에서 직접 찾는다(term_source='vocabulary').
    retrieve   PantryRecommendService로 별칭 해석·추천 레시피·사용/부족 재료·근거를 Neo4j에서 조회한다.
    answer     조회한 근거(JSON)만 주고 LLM이 추천 이유를 쓴다. 검증에 실패한 문장은 근거로 만든 문장으로 바꾼다.

LLM이 만드는 것은 설명 문장뿐이다. 레시피 목록·사용 재료·부족 재료는 화면에 Neo4j 조회값을 그대로 쓴다.
답변 검증 규칙:
    - 근거에 없는 rcp_id에 대한 이유는 버린다.
    - 이유 문장에 DB 식재료 어휘 중 그 레시피 재료·보유 재료가 아닌 이름이 나오면 그 문장을 버린다.
      단, 레시피명 속 낱말(예: '닭고기김치찌개'의 '닭고기')은 재료가 아니므로 레시피명을 먼저 지우고 검사한다.
    - 요약 문장에 근거 밖 식재료가 나오면 요약을 근거 기반 문장으로 바꾼다.
LLM 키가 없거나 호출이 실패해도 규칙 해석과 근거 기반 문장으로 동작한다.
답변의 ``llm_status`` 로 화면에서 출처를 구분한다:
    ok        LLM 설명을 검증 후 그대로 사용
    partial   LLM 설명 일부가 검증에 걸려 근거 문장으로 교체됨
    failed    LLM 호출 실패 → 전체 근거(규칙) 문장
    disabled  LLM 미설정(OPENAI_API_KEY 없음) → 전체 근거(규칙) 문장
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import TypedDict

from pydantic import BaseModel, Field

from .pantry_recommend_service import PantryRecommendService, PantryResult, split_terms
from .name_normalization import normalize_name

# region 1. LLM 설정과 State·출력 모델
logger = logging.getLogger("recipe_recommender.pantry_graphrag")

DEFAULT_MODEL = "gpt-6-luna"
MIN_VOCAB_LENGTH = 2        # 한 글자 이름(예: '파', '물')은 다른 낱말 속에 흔해 검사에서 제외한다
MAX_MISSING_IN_SENTENCE = 5  # 근거 문장에 나열할 부족 재료 수(나머지는 "외 N개", 전체 목록은 화면에서 펼쳐 본다)


# =========================================================
# LLM 구조화 출력 형식
# =========================================================
class IngredientTerms(BaseModel):
    """입력 해석 LLM의 구조화 출력; Pydantic이 재료 목록의 형태를 검증한다."""
    # 원문에서 추출한 이름 목록; interpret가 실제 질문에 있는 단어만 남긴다.
    terms: list[str] = Field(description="사용자가 가지고 있다고 말한 식재료 이름. 사용자가 쓴 표현 그대로, 수량·단위 제외")


class RecipeReason(BaseModel):
    """레시피 ID와 해당 레시피의 LLM 추천 이유 한 건을 검증한다."""
    # 조회 결과의 ID여야 하며 validate_answer에서 실제 추천 목록과 대조한다.
    rcp_id: str = Field(description="근거 JSON의 rcp_id 그대로")
    # 근거 밖 재료가 언급되면 해당 이유는 규칙 기반 설명으로 대체한다.
    reason: str = Field(description="이 레시피를 추천하는 이유 1~2문장. 근거 JSON의 재료·분류·조리 방법만 사용")


class PantryAnswer(BaseModel):
    """설명 LLM의 구조화 출력; ``validate_answer``가 DB 근거와 다시 대조한다."""
    # 전체 추천 요약; 검증에 실패하면 grounded_summary로 대체한다.
    summary: str = Field(description="전체 추천 요약 1~2문장")
    recipes: list[RecipeReason]  # 추천 ID별 이유; 실제 조회 목록과의 일치는 후속 검증에서 확인한다.


INTERPRET_PROMPT = """사용자 문장에서 사용자가 가지고 있는 식재료 이름만 뽑아라.
- 사용자가 쓴 표현을 그대로 쓴다(예: '계란'을 '달걀'로 바꾸지 않는다). 수량·단위·조리 상태는 뺀다.
- 문장에 없는 재료를 추가하지 않는다. 재료가 없으면 빈 목록.

사용자 문장:
{question}"""

ANSWER_PROMPT = """너는 냉장고 재료로 만들 수 있는 레시피를 설명하는 도우미다.
아래 근거 JSON은 레시피 그래프 DB(Neo4j)에서 조회한 결과다. 반드시 이 근거만 사용한다.

규칙:
- 근거 JSON에 있는 레시피(rcp_id)만 설명한다. 새 레시피·요리를 만들지 않는다.
- 재료는 각 레시피의 used_ingredients, missing_ingredients, all_ingredients에 있는 이름만 쓴다.
  근거에 없는 재료(소금·후추 등 일반 양념 포함)를 덧붙이지 않는다.
- 조리 단계·조리 시간·맛 평가처럼 근거에 없는 내용은 쓰지 않는다.
- recipes에는 근거의 모든 레시피를 같은 순서로 한 번씩 넣는다. 한국어로 쓴다.

사용자 질문: {question}
보유 재료(DB 표준명): {owned}
DB에 없는 입력 재료: {unknown}

근거 JSON:
{context}"""


class PantryState(TypedDict, total=False):
    """LangGraph 노드가 공유하는 상태의 키와 값 형식.

    ``total=False``는 정적 타입에서 키 생략을 허용한다는 뜻이다. 실행 시에는
    ``run``의 초기 입력과 앞선 Node가 만든 키를 다음 Node가 실제로 요구한다.
    각 Node는 변경한 키만 반환하고 LangGraph가 이를 기존 State에 병합한다.
    """

    question: str  # run 입력; interpret가 읽고 answer의 LLM 프롬프트에도 사용한다.
    limit: int  # run 입력; retrieve가 사용하며 누락 시 기본값 5.
    sort: str  # run 입력; retrieve가 coverage/missing 정렬에 사용하며 누락 시 coverage.
    terms: list[str]  # interpret가 추출; retrieve가 식재료 조회에 사용한다.
    term_source: str  # interpret가 기록한 'llm'|'rule'|'vocabulary'; 화면의 해석 출처.
    result: PantryResult  # retrieve가 만든 결과; answer가 설명의 근거로 사용한다.
    answer: dict  # answer가 생성; summary, reasons, sources, llm_status 등을 화면이 읽는다.
    warnings: list[str]  # run에서 빈 목록으로 시작; interpret와 answer가 새 목록으로 누적한다.


def create_llm():
    """API 키가 있을 때만 Streamlit 파이프라인용 ChatOpenAI를 생성한다.

    Returns:
        ChatOpenAI | None: 설정된 모델 클라이언트 또는 LLM 비활성 상태.
    """
    if not os.getenv("OPENAI_API_KEY"):
        return None
    from langchain_openai import ChatOpenAI

    # gpt-6-luna는 temperature 기본값(1)만 받으므로 지정하지 않는다.
    return ChatOpenAI(model=os.getenv("OPENAI_MODEL") or DEFAULT_MODEL, timeout=60, max_retries=1)


# endregion
# region 2. 입력어와 답변의 근거 검증
# =========================================================
# 검증 도우미 (DB 무관, 테스트 대상)
# =========================================================
def terms_in_question(terms: list[str], question: str) -> list[str]:
    """LLM이 뽑은 입력어 중 사용자 문장에 실제로 있는 것만 남긴다(정규화·공백 무시 비교, 중복 제거)."""
    compact = normalize_name(question).replace(" ", "")
    kept, seen = [], set()
    for term in terms:
        key = normalize_name(term)
        if key and key.replace(" ", "") in compact and key not in seen:
            seen.add(key)
            kept.append(term.strip())
    return kept


def mask_phrases(text: str, phrases) -> str:
    """``phrases`` (레시피명 등)를 지운다. 띄어쓰기만 다른 표기('닭고기 김치찌개')도 함께 지운다."""
    for phrase in sorted({p for p in phrases if p}, key=len, reverse=True):
        letters = [re.escape(ch) for ch in phrase if not ch.isspace()]
        if letters:
            text = re.sub(r"\s*".join(letters), " ", text)
    return text


def scan_vocabulary_terms(question: str, vocabulary: list[dict]) -> list[str]:
    """문장에 들어 있는 DB 표준명·별칭을 긴 이름부터 찾아 문장 순서로 돌려준다(LLM 없는 문장 해석 대체 규칙).

    긴 이름을 먼저 지우므로 '양파' 속 '파' 같은 짧은 이름은 다시 잡지 않는다. 한 글자 이름은 제외한다.
    """
    names = sorted({name for row in vocabulary for name in (row["ingr_nm"], *row["alias_names"])
                    if name and len(name) >= MIN_VOCAB_LENGTH}, key=len, reverse=True)
    remaining, found = question, []
    for name in names:
        position = remaining.find(name)
        if position >= 0:
            found.append((position, name))
            remaining = remaining.replace(name, " " * len(name))    # 길이를 유지해 위치 비교가 가능하게 지운다
    return [name for _, name in sorted(found)]


def foreign_ingredients(text: str, allowed: set[str], vocabulary: set[str], ignore=()) -> list[str]:
    """``text`` 에 나온 DB 식재료 이름 중 ``allowed`` 가 아닌 것.

    ``ignore`` (레시피명 등 재료가 아닌 고유 이름)와 허용 이름을 먼저 지운 뒤 찾는다.
    그래서 '양파' 속의 '파'나 '닭고기김치찌개' 속의 '닭고기'처럼 다른 이름 안에 든 낱말은 잡지 않는다.
    """
    masked = mask_phrases(text, ignore)
    for name in sorted(allowed, key=len, reverse=True):
        if name:
            masked = masked.replace(name, " ")
    return sorted(name for name in vocabulary
                  if len(name) >= MIN_VOCAB_LENGTH and name not in allowed and name in masked)


# endregion
# region 3. 근거 기반 문장과 LLM 답변 검증
# =========================================================
# 근거 기반 문장 (LLM 실패·검증 실패 시 대체)
# =========================================================
def has_final_consonant(word: str) -> bool | None:
    """마지막 글자가 한글이면 받침 여부, 숫자면 읽는 소리 기준, 그 밖(영문 등)은 None."""
    word = (word or "").strip()
    if not word:
        return None
    last = word[-1]
    if "가" <= last <= "힣":
        return (ord(last) - ord("가")) % 28 != 0
    if last.isdigit():
        return last in "0136780"          # 영·일·삼·육·칠·팔·공(0)은 받침이 있다
    return None


def josa(word: str, with_final: str, without_final: str) -> str:
    """``word`` 뒤에 붙을 조사. ``josa('두부', '을', '를')`` → ``'두부를'``. 판단할 수 없으면 '을(를)' 형태."""
    final = has_final_consonant(word)
    if final is None:
        return f"{word}{with_final}({without_final})"
    return word + (with_final if final else without_final)


def josa_ro(word: str) -> str:
    """'으로/로': 받침이 없거나 ㄹ 받침이면 '로'."""
    word = (word or "").strip()
    if word and "가" <= word[-1] <= "힣" and (ord(word[-1]) - ord("가")) % 28 == 8:
        return word + "로"
    final = has_final_consonant(word)
    if final is None:
        return f"{word}(으)로"
    return word + ("으로" if final else "로")


def list_text(items: list[str], limit: int | None = None) -> str:
    """``['a','b','c']`` → ``'a, b, c'``. ``limit`` 을 넘으면 ``'a, b 외 N개'``."""
    if limit is not None and len(items) > limit:
        return f"{', '.join(items[:limit])} 외 {len(items) - limit}개"
    return ", ".join(items)


def grounded_reason(rec) -> str:
    """근거만으로 만든 추천 이유(LLM 실패·검증 실패 시 대체 문장)."""
    used = list_text(rec.matched_ingredients)
    category = "·".join(rec.categories) or "분류 미지정"
    method = f" 조리 방법은 '{rec.method}'입니다." if rec.method else ""
    if rec.missing_ingredients:
        missing = (f" 추가로 {rec.missing_count}가지 재료"
                   f"({list_text(rec.missing_ingredients, MAX_MISSING_IN_SENTENCE)})가 필요합니다.")
    else:
        missing = " 추가로 필요한 재료가 없습니다."
    return f"보유 재료 {josa(used, '을', '를')} 사용하는 {category} 레시피입니다.{method}{missing}"


def grounded_summary(result: PantryResult) -> str:
    """추천 결과의 첫 레시피와 보유 재료로 LLM 없이 요약 문장을 만든다."""
    if not result.recommendations:
        return "입력한 재료로 찾을 수 있는 레시피가 없습니다."
    top = result.recommendations[0]
    owned = josa_ro(list_text(result.owned_ingredients))
    head = josa(top.rcp_nm, "은", "는")
    return (f"보유 재료 {owned} 만들 수 있는 레시피 {len(result.recommendations)}개를 찾았습니다. "
            f"{head} 보유 재료 {top.matched_count}개를 쓰고 {top.missing_count}개가 더 필요합니다.")


def build_context(result: PantryResult) -> list[dict]:
    """Neo4j 추천 DTO에서 LLM에 전달할 근거 필드만 추린다.

    Args:
        result (PantryResult): ``retrieve``가 만든 추천 결과.

    Returns:
        list[dict]: 순서를 유지한 레시피 ID, 재료, 분류, 조리 방법 등의 근거.
    """
    return [{
        "rcp_id": rec.rcp_id, "name": rec.rcp_nm, "categories": rec.categories, "method": rec.method,
        "energy_kcal": rec.energy_kcal, "used_ingredients": rec.matched_ingredients,
        "missing_ingredients": rec.missing_ingredients, "all_ingredients": rec.all_ingredients,
    } for rec in result.recommendations]


def validate_answer(raw: PantryAnswer, result: PantryResult, vocabulary: list[dict]) -> tuple[dict, list[str]]:
    """LLM 답변의 레시피 ID와 재료명을 조회 근거와 대조한다.

    없는 ID는 버리고, 근거 밖 식재료가 든 이유·요약은 해당 부분만 규칙 문장으로
    바꾼다. 빠진 레시피의 이유도 근거 문장으로 채워 화면 목록을 보존한다.

    Args:
        raw (PantryAnswer): Pydantic으로 형태를 검증한 LLM 출력.
        result (PantryResult): Neo4j 조회를 담은 변경 불가 근거.
        vocabulary (list[dict]): 근거 밖 식재료 탐지에 쓰는 DB 표준명·별칭.

    Returns:
        tuple[dict, list[str]]: 화면용 설명·출처·상태와 교체 사유 목록.
    """
    names = {row["ingr_nm"] for row in vocabulary} | {a for row in vocabulary for a in row["alias_names"]}
    aliases = {row["ingr_nm"]: set(row["alias_names"]) for row in vocabulary}
    owned = set(result.owned_ingredients) | set(result.terms)
    with_aliases = lambda items: set(items) | {a for item in items for a in aliases.get(item, ())}  # noqa: E731
    warnings: list[str] = []
    by_id = {rec.rcp_id: rec for rec in result.recommendations}
    reasons, sources = {}, {}
    for item in raw.recipes:
        rec = by_id.get(item.rcp_id)
        if rec is None:
            warnings.append(f"근거에 없는 레시피 ID '{item.rcp_id}'에 대한 LLM 설명을 버렸습니다.")
            continue
        if item.rcp_id in reasons:
            continue
        foreign = foreign_ingredients(item.reason, with_aliases(rec.all_ingredients) | owned, names,
                                      ignore=[rec.rcp_nm])
        if foreign:
            warnings.append(f"'{rec.rcp_nm}' 설명에 근거 밖 재료 {foreign}가 있어 근거 문장으로 바꿨습니다.")
            continue
        reasons[item.rcp_id], sources[item.rcp_id] = item.reason.strip(), "llm"
    for rec in result.recommendations:
        if rec.rcp_id not in reasons:
            reasons[rec.rcp_id], sources[rec.rcp_id] = grounded_reason(rec), "grounded"
    all_allowed = owned | {name for rec in result.recommendations for name in with_aliases(rec.all_ingredients)}
    summary, summary_source = raw.summary.strip(), "llm"
    foreign = foreign_ingredients(summary, all_allowed, names,
                                  ignore=[rec.rcp_nm for rec in result.recommendations])
    if foreign or not summary:
        if foreign:
            warnings.append(f"요약에 근거 밖 재료 {foreign}가 있어 근거 문장으로 바꿨습니다.")
        summary, summary_source = grounded_summary(result), "grounded"
    replaced = summary_source == "grounded" or any(source == "grounded" for source in sources.values())
    return {"summary": summary, "summary_source": summary_source, "reasons": reasons, "sources": sources,
            "llm_status": "partial" if replaced else "ok", "llm_error": None}, warnings


# endregion
# region 4. LangGraph 생성과 State 노드 실행
# =========================================================
# LangGraph 노드 및 State 처리
# =========================================================
class PantryGraphRAG:
    """입력 해석, Neo4j 추천 조회, 근거 설명을 LangGraph로 연결한다.

    Streamlit 진입점이 Service와 선택적 LLM을 주입해 생성한다. Java Service의
    단계별 호출을 StateGraph의 Node와 Edge로 선언한 형태다.
    ``llm=None``이면 규칙 해석과 근거 문장만 사용한다.
    """

    def __init__(self, service: PantryRecommendService, llm=None):
        """추천 Service와 LLM을 보관하고 실행 가능한 그래프를 컴파일한다."""
        self.service = service
        self.llm = llm
        self.graph = self._build()

    def _build(self):
        """세 Node를 순서대로 잇고 ``invoke`` 가능한 그래프로 컴파일한다."""
        from langgraph.graph import END, START, StateGraph

        builder = StateGraph(PantryState)
        builder.add_node("interpret", self.interpret)
        builder.add_node("retrieve", self.retrieve)
        builder.add_node("answer", self.answer)
        # 고정 Edge 순서로 각 Node의 부분 dict를 State에 병합한다. 여기에는 조건부 Edge가 없다.
        builder.add_edge(START, "interpret")
        builder.add_edge("interpret", "retrieve")
        builder.add_edge("retrieve", "answer")
        builder.add_edge("answer", END)
        return builder.compile()

    def run(self, question: str, limit: int = 5, sort: str = "coverage") -> PantryState:
        """질문과 정렬 조건으로 State를 초기화하고 그래프를 한 번 실행한다.

        Args:
            question (str): 사용자 재료 목록 또는 문장.
            limit (int): 표시할 추천 건수.
            sort (str): ``coverage`` 또는 ``missing``.

        Returns:
            PantryState: Node의 부분 업데이트가 병합된 최종 상태.
        """
        return self.graph.invoke({"question": question, "limit": limit, "sort": sort, "warnings": []})

    def interpret(self, state: PantryState) -> PantryState:
        """구분 입력은 규칙으로, 문장은 LLM 또는 DB 어휘로 해석한다.

        Args:
            state (PantryState): 질문과 기존 경고를 담은 상태.

        Returns:
            PantryState: terms, term_source, warnings의 부분 업데이트.
        """
        question = state["question"]
        rule_terms = split_terms(question)
        warnings = list(state.get("warnings", []))
        # 구분자로 나눈 짧은 목록('계란, 두부')은 그대로 쓴다. 문장형 입력만 LLM으로 해석한다.
        if all(len(term) <= 10 and " " not in term.strip() for term in rule_terms):
            return {"terms": rule_terms, "term_source": "rule", "warnings": warnings}
        if self.llm is None:
            return self._interpret_without_llm(question, rule_terms, warnings)
        try:
            extracted = self.llm.with_structured_output(IngredientTerms).invoke(
                INTERPRET_PROMPT.format(question=question))
            terms = terms_in_question(extracted.terms, question)
            dropped = [t for t in extracted.terms if t.strip() and t.strip() not in terms]
            if dropped:
                warnings.append(f"입력 문장에 없는 재료로 해석된 {dropped}는 제외했습니다.")
            if terms:
                return {"terms": terms, "term_source": "llm", "warnings": warnings}
        except Exception as error:                       # LLM 장애 시 규칙 해석으로 계속한다
            logger.warning("interpret LLM failed: %s", type(error).__name__)
            warnings.append("LLM 입력 해석에 실패했습니다.")
        return self._interpret_without_llm(question, rule_terms, warnings)

    def _interpret_without_llm(self, question: str, rule_terms: list[str], warnings: list[str]) -> PantryState:
        """문장형 입력을 LLM 없이 해석한다: 문장에서 DB 식재료명·별칭을 찾고, 없으면 구분자 규칙 결과를 쓴다."""
        terms = scan_vocabulary_terms(question, self.service.vocabulary())
        if terms:
            warnings.append(f"LLM 없이 문장에서 DB 식재료명을 찾아 {terms}로 해석했습니다.")
            return {"terms": terms, "term_source": "vocabulary", "warnings": warnings}
        return {"terms": rule_terms, "term_source": "rule", "warnings": warnings}

    def retrieve(self, state: PantryState) -> PantryState:
        """해석된 재료를 Service에 전달해 Neo4j 추천 결과를 추가한다.

        Args:
            state (PantryState): interpret가 만든 terms와 초기 limit, sort.

        Returns:
            PantryState: result 키를 담은 부분 업데이트.
        """
        return {"result": self.service.recommend(state["terms"], limit=state.get("limit", 5),
                                                 sort=state.get("sort", "coverage"))}

    def answer(self, state: PantryState) -> PantryState:
        """조회 근거로 설명을 만들고 LLM 실패 시 근거 문장으로 대체한다.

        Args:
            state (PantryState): retrieve 결과와 원문 질문, 이전 경고.

        Returns:
            PantryState: answer와 누적 warnings의 부분 업데이트.
        """
        result: PantryResult = state["result"]
        warnings = list(state.get("warnings", []))
        fallback = {"summary": grounded_summary(result), "summary_source": "grounded",
                    "reasons": {rec.rcp_id: grounded_reason(rec) for rec in result.recommendations},
                    "sources": {rec.rcp_id: "grounded" for rec in result.recommendations},
                    "llm_status": "disabled" if self.llm is None else "skipped", "llm_error": None}
        if not result.recommendations or self.llm is None:
            return {"answer": fallback, "warnings": warnings}
        prompt = ANSWER_PROMPT.format(
            question=state["question"], owned=", ".join(result.owned_ingredients),
            unknown=", ".join(result.unknown_terms) or "없음",
            context=json.dumps(build_context(result), ensure_ascii=False, indent=1))
        try:
            raw = self.llm.with_structured_output(PantryAnswer).invoke(prompt)
        except Exception as error:
            logger.warning("answer LLM failed: %s", type(error).__name__)
            warnings.append("LLM 답변 생성에 실패해 근거 데이터로 만든 설명을 표시합니다.")
            return {"answer": {**fallback, "llm_status": "failed", "llm_error": type(error).__name__},
                    "warnings": warnings}
        answer, problems = validate_answer(raw, result, self.service.vocabulary())
        return {"answer": answer, "warnings": warnings + problems}

# endregion
