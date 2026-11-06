"""AI 추출 흐름을 담당하는 Service 모듈. LLM 호출 → 응답 검증 → 페이지 저장 → 문서 통합 순서로 처리한다.

LLM 클라이언트는 주입받는다. 이 모듈은 특정 모델이나 제공자에 의존하지 않는다.
값 검증은 두 가지를 구분한다. 값이 원문에 있는지(``value_check_cd``)와
그 값이 이 혜택의 값인지(``link_check_cd``)다. 표에서 읽은 연결은 텍스트로 증명할 수 없어 사람이 확인한다.

[등록 파이프라인에서의 위치] 2단계: 청크 → LLM 추출 → 검증 → 중간 테이블(card_ai_run/call, card_extr_stg,
card_source_evidence) 저장. 여기서 만든 결과는 아직 "후보"이며, 카드 혜택(card_product_item)·공통 혜택
(card_common_bnft) 등록은 3단계 product_benefit_service / common_benefit_service가 한다.

처리 흐름 (``ExtractionService.run``)
    1. 상품·문서·AI 입력 청크 조회(select_card_product, select_doc, select_ai_input_chunks)
    2. 분리 규칙·페이지·청크 필터, 로컬 PDF 해시 확인(_local_pdf → document_storage.resolve_local_pdf)
    3. 재사용 판정: 같은 입력 지문(fingerprint)의 성공 실행이 완전히 남아 있으면 LLM을 다시 부르지 않고 반환
    4. card_ai_run INSERT(RUNNING) → ``_run_pages``
    5. 청크마다 ``_process_chunk``:
         build_input(텍스트 + 페이지 이미지) → _call_llm(LLM 호출, card_ai_call INSERT — 즉시 커밋)
         → _parse(Pydantic PageExtraction 검증) → [트랜잭션] _store_page(check_benefit/check_condition 검증 후
         card_extr_stg + card_source_evidence INSERT)
    6. 모든 청크가 성공하면 ``_store_merge``: merge_pages(문서 단위 통합) → [트랜잭션] card_extr_stg UPDATE
       (대표 행 검증 코드·중복 행의 상위 행 연결)
    7. finish_run(SUCCEEDED / PARTIAL / FAILED)

트랜잭션 경계 (중요)
    - card_ai_run INSERT, card_ai_call INSERT, finish_run은 트랜잭션 밖에서 실행되어 SQL마다 바로 커밋된다.
      비용이 든 LLM 응답 원문이 뒤 단계 오류로 사라지지 않게 하기 위해서다.
    - 페이지 항목 저장(_store_page)은 청크마다 1트랜잭션, 문서 통합(_store_merge)은 문서당 1트랜잭션이다.

LLM 호출: 이 모듈은 ``LlmClient.extract`` 만 부른다. 실제 구현은 terra_client.TerraClient(OpenAI Responses API).
         ``llm_client=None`` 으로 만들면(terra_main --preflight 등) 입력 구성만 하고 호출하지 않는다.

호출하는 곳: terra_main.py, common_auto_main.py / common_auto_pipeline.py(공통 문서),
            common_benefit_service(normalize_stored_run), product_benefit_service(locate_quote, strip_calc_*)
관련 SQL: extraction_repository.sql (ExtractionRepository 경유)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import json
import logging
from pathlib import Path
import re
from time import perf_counter
from typing import Any, Protocol

from common.postgres_db_session import PostgresDbSession
from pydantic import ValidationError
import psycopg
import pymupdf

from .document_service import DATA_ROOT, SPLIT_RULE_VER
from .document_storage import resolve_local_pdf
from .extraction_repository import ExtractionRepository
from .extraction_schema import (
    SCHEMA_VER,
    MERGE_VER,
    BenefitItem,
    ConditionItem,
    EvidenceCheck,
    EvidenceQuote,
    ItemCheck,
    MergedBenefit,
    MergedCondition,
    MergeInfo,
    PageExtraction,
    SourceRef,
)

extraction_logger = logging.getLogger("card_benefit.extraction")

PROMPT_VER = "EXTRACT_V8"
IMAGE_DPI = 150
INPUT_MODE = "TEXT_IMAGE"
KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")

# 값 검증 코드. 앞에 있을수록 심각하다.
VALUE_CHECK_ORDER = ("NO_EVIDENCE", "QUOTE_NOT_FOUND", "VALUE_NOT_IN_QUOTE", "VALUE_PARSE_DIFF", "OK")

AMOUNT_PATTERN = re.compile(r"(?:(\d[\d,]*)만)?(?:(\d[\d,]*)천)?(\d[\d,]*)?원")
COUNT_PATTERN = re.compile(r"(\d[\d,]*)회")
RATE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)%")
# 외화 한도(예: "최대 USD 100", "$30", "50달러"). 공백을 지운 문자열에서 읽는다.
FOREIGN_AMOUNT_PATTERN = re.compile(r"(?:USD|US\$|\$)(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)(?:USD|달러)", re.IGNORECASE)

# region LLM 프롬프트 (변경 시 PROMPT_VER도 올려야 재사용 판정·이력 비교가 맞는다)
# PROMPT_TXT는 card_ai_run.run_prompt_txt에 저장되고, 입력 해시(input_sha256)와 재사용 지문에도 들어간다.
PROMPT_TXT = """당신은 카드 상품설명서에서 혜택 정보를 구조화하는 추출기입니다.
입력은 페이지 전체 텍스트와 같은 페이지의 이미지입니다.

역할을 구분합니다.
- 텍스트: 혜택명, 금액, 비율, 횟수, 조건의 값을 확인합니다.
- 이미지: 표의 행과 열을 보고 어떤 값이 어떤 혜택에 속하는지 판단합니다.

규칙:
1. 값은 페이지 텍스트에 있는 것만 씁니다. 이미지에서만 보이는 값은 unresolved에 적습니다.
2. 원문에 없는 값, 구간, 우선순위를 추정하지 않습니다. 모르면 null 또는 UNKNOWN입니다.
3. evidence.quote_txt는 페이지 텍스트를 그대로 복사합니다. 요약하거나 고치지 않습니다.
4. 금액과 횟수는 정수로 씁니다. 예: 3천원은 3000, 월 30회는 30입니다. 원문 표기는 *_raw_txt에 그대로 둡니다.
5. 표에서 읽은 값의 근거는 link_basis를 TABLE_IMAGE로 씁니다. 값과 혜택이 같은 문장에 있으면 SAME_TEXT입니다.
6. 조건이 적용되는 범위를 scope로 구분합니다. 판단할 수 없으면 UNKNOWN입니다.
7. 값이 같다는 이유로 한도를 공유한다고 판단하지 않습니다. 원문에 공유 표현이 있을 때만 shared_scope_txt를 씁니다.
8. 해석하지 못한 문구는 버리지 말고 unresolved에 사유와 함께 적습니다.
9. 공통 브랜드 안내서는 혜택별 브랜드, 등급, 대상 카드, 선택서비스, 제외 카드와 제공 기간을 원문 그대로 기록합니다. 적용 대상과 기간을 뒷받침하는 인용은 APPLICABILITY 근거로 남깁니다. 문서에 없거나 다른 페이지와의 연결이 불명확하면 추정하지 말고 검토 대상으로 남깁니다.
10. 규칙(rules)마다 supports=RULE, support_key=그 rule_key인 근거를 반드시 남깁니다. quote_txt는 그 규칙의 value_raw_txt가 들어 있는 가장 짧은 원문 구간입니다.
    한 문장에 여러 규칙의 값이 있으면 규칙마다 자기 값이 있는 구간을 나눠 인용합니다. 예: "Trip.com 호텔 6%" / "항공 3%" / "액티비티 5% 할인".
    혜택 전체를 소개하는 문장을 BNFT 근거로만 남기고 규칙 근거를 생략하지 않습니다. 원문에서 값을 찾을 수 없으면 규칙을 만들지 말고 unresolved에 적습니다.
11. 한도(limits)마다 supports=LIMIT, support_key=그 limit_key인 근거를 남깁니다. 인용에는 limit_raw_txt가 들어 있어야 합니다.
12. 입력이 [추출 대상]과 [같은 페이지 유의사항 문맥]으로 나뉘어 있으면 혜택과 조건은 [추출 대상]에서만 추출합니다.
    [같은 페이지 유의사항 문맥]은 적용 대상·제공 기간을 뒷받침하는 APPLICABILITY 인용에만 사용하고, 그 안의 내용으로 혜택을 새로 만들지 않습니다.
13. 규칙의 value_num·value_unit_cd는 원문 값(%, 원, 배)을 그대로 옮긴 설명 값입니다. 보상액이나 지급 방식은 판단하지 않습니다.
    단위를 원문에서 확인할 수 없으면 value_unit_cd=UNKNOWN입니다.
14. 수치 하나로 쓸 수 없는 혜택(예: 조식 제공, 그린피 면제, 멤버십 무료 가입, 수수료 무료, 1+1, 포인트 지급)도 규칙으로 남깁니다.
    이때 value_num=null, value_unit_cd=null이고 value_raw_txt에는 "조식 제공", "1+1"처럼 원문 표현을 그대로 씁니다.
15. 한도의 period_cd는 원문 표현으로 정합니다. 일·월·연 표현이 있으면 DAY·MONTH·YEAR, "건당", "1회 결제 시", "예약 시"처럼 결제 1건에만
    적용되는 상한이거나 할인율 바로 뒤의 "(최대 N원)"처럼 해당 결제 1건의 할인 상한이면 TXN입니다. 판단할 수 없으면 UNKNOWN입니다.
    한도 단위가 원화·하나머니·횟수가 아니면(예: USD) cap_unit_cd=UNKNOWN으로 두고 값을 환산하지 않습니다.
16. targets[].target_nm은 원문에 적힌 가맹점·서비스 이름을 그대로 복사합니다. 혜택 설명을 덧붙이거나 여러 표현을 합쳐 새 이름을 만들지 않습니다.
17. 모든 조건(benefits[].conditions, rules[].conditions, card_conditions)에는 evidence를 1건 이상 남깁니다. quote_txt는 그 조건의
    cond_raw_txt가 들어 있는 원문 구간을 그대로 복사하고, supports=COND, support_key=그 cond_key입니다.
    원문에서 인용할 수 없는 조건은 만들지 말고 unresolved에 적습니다.
18. bnft_nm은 혜택 내용(서비스혜택·할인 내용) 문장에서 정합니다. 주변 제목과 내용이 서로 다른 서비스를 가리키면 내용을 따르고,
    uncertainty_note에 제목과 내용이 다르다고 적으며 certainty=LOW로 둡니다.
"""
# endregion


# region 데이터 클래스 (LLM 입력·응답, 페이지 결과, 실행 결과)
class ExtractionError(Exception):
    """추출을 시작할 수 없는 경우."""


@dataclass(frozen=True)
class PageInput:
    """LLM 입력 1건."""

    prompt_txt: str
    page_no: int
    page_text: str
    image_png: bytes | None       # 청크가 페이지 일부이면 None이다. 이미지는 페이지 전체를 보여 다른 청크 항목이 섞이기 때문이다.
    input_sha256: str


@dataclass(frozen=True)
class LlmResponse:
    """LLM 응답 원문과 사용량."""

    raw_text: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LlmClient(Protocol):
    """LLM 클라이언트 계약. 실제 구현과 Mock이 같은 형태를 따른다."""

    model_nm: str

    def extract(self, page_input: PageInput) -> LlmResponse:
        """페이지 입력을 보내고 응답을 반환한다."""


@dataclass
class StoredItem:
    """저장된 페이지 항목. 통합 뒤 ``stg_id`` 로 결과를 기록한다."""

    stg_id: str | None
    seq: int
    item: BenefitItem | ConditionItem
    check: ItemCheck


@dataclass
class PageResult:
    """호출에 성공한 페이지의 추출 결과."""

    page_no: int
    chunk_id: str
    text: str
    extraction: PageExtraction
    benefits: list[StoredItem] = field(default_factory=list)
    conditions: list[StoredItem] = field(default_factory=list)
    chunk_seq: int = 0
    # 같은 페이지 유의사항 청크 ``(청크 ID, 원문)``. 인용이 대상 청크에 없을 때만 여기서 위치를 찾는다.
    context: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class RunResult:
    """실행 결과 요약."""

    card_ai_run_id: str
    status: str
    pages_ok: int
    pages_failed: int
    merged: bool
    note: str | None = None
    reused: bool = False
# endregion


# region 문자열·숫자 도우미
# =========================================================
# 문자열·숫자 도우미
# =========================================================
def compact(text: str) -> str:
    """공백을 모두 지운 문자열. PDF 텍스트의 줄바꿈 차이를 무시하고 비교할 때 쓴다."""
    return "".join(text.split())


def locate_quote(text: str, quote: str) -> tuple[int, int] | None:
    """인용문의 원문 위치를 찾는다. 위치는 1부터이고 종료 위치를 포함한다.

    정확히 찾지 못하면 공백만 무시하고 찾으며, 위치는 항상 원문 기준이다.
    """
    index = text.find(quote) if quote else -1
    if index >= 0:
        return index + 1, index + len(quote)
    target = compact(quote)
    if not target:
        return None
    positions = [position for position, char in enumerate(text) if not char.isspace()]
    found = "".join(text[position] for position in positions).find(target)
    if found < 0:
        return None
    return positions[found] + 1, positions[found + len(target) - 1] + 1


def amounts_in(text: str) -> set[int]:
    """문자열의 금액 표기를 원 단위 정수로 읽는다. 예: ``1만 5천원`` 은 15000이다."""
    amounts = set()
    for man, cheon, won in AMOUNT_PATTERN.findall(compact(text)):
        if man or cheon or won:
            to_int = lambda value: int(value.replace(",", "")) if value else 0  # noqa: E731
            amounts.add(to_int(man) * 10000 + to_int(cheon) * 1000 + to_int(won))
    return amounts


def foreign_amounts_in(text: str) -> set[Decimal]:
    """문자열의 외화(달러) 금액 표기를 읽는다. 환산하지 않고 표기된 숫자만 돌려준다."""
    return {Decimal((before or after).replace(",", "")) for before, after in FOREIGN_AMOUNT_PATTERN.findall(compact(text))}


def limit_values_in(text: str) -> set:
    """단위를 정하지 못한 한도 값. 원화와 외화 표기를 모두 읽는다(원문 숫자 대조용이며 환산하지 않는다)."""
    return amounts_in(text) | foreign_amounts_in(text)


def counts_in(text: str) -> set[int]:
    """문자열의 횟수 표기를 정수로 읽는다."""
    return {int(value.replace(",", "")) for value in COUNT_PATTERN.findall(compact(text))}


def rates_in(text: str) -> set[Decimal]:
    """문자열의 비율 표기를 읽는다."""
    return {Decimal(value) for value in RATE_PATTERN.findall(compact(text))}


def json_number(value: Decimal | int | None) -> int | float | None:
    """JSONB에 숫자 타입으로 저장되도록 바꾼다. V6 계약 함수는 문자열 숫자를 거부한다."""
    if value is None or isinstance(value, int):
        return value
    return int(value) if value == value.to_integral_value() else float(value)


def rule_of(chunk: dict) -> str:
    """청크의 분리 규칙. 값이 없는 이전 형식은 PAGE_V1이다."""
    return chunk.get("chunk_split_rule_ver") or SPLIT_RULE_VER


def make_item_key(prefix: str, name: str) -> str:
    """혜택명으로 실행마다 같은 키를 만든다. LLM이 준 키는 실행마다 달라질 수 있어 쓰지 않는다."""
    digest = hashlib.sha256(compact(name).lower().encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}_{digest}"


def worst_value_check(codes: list[str]) -> str:
    """값 검증 코드 중 가장 심각한 것을 고른다."""
    return min(codes, key=VALUE_CHECK_ORDER.index) if codes else "OK"
# endregion


# region 원문 대조 (LLM 응답 검증: 인용 위치 찾기, 값이 인용에 있는지, 대상 연결 확인)
# =========================================================
# 원문 대조
# =========================================================
# 호출 순서: _store_page → check_benefit / check_condition → locate_evidence(위치) → check_values(값) → link_check(연결)
# 결과 ItemCheck.value_check_cd는 VALUE_CHECK_ORDER 중 가장 심각한 값, link_check_cd는 TEXT_CONFIRMED/NEEDS_REVIEW다.
def locate_evidence(quotes: list[EvidenceQuote], page: PageResult) -> list[EvidenceCheck]:
    """인용문을 원문에서 찾아 위치를 채운다. 대상 청크에 없으면 같은 페이지 유의사항 청크에서 찾고 그 청크를 기록한다."""
    checks = []
    for quote in quotes:
        chunk_id, position = page.chunk_id, locate_quote(page.text, quote.quote_txt)
        for context_id, context_text in page.context if position is None else ():
            position = locate_quote(context_text, quote.quote_txt)
            if position is not None:
                chunk_id = context_id
                break
        checks.append(EvidenceCheck(
            quote_txt=quote.quote_txt,
            supports=quote.supports,
            support_key=quote.support_key,
            link_basis=quote.link_basis,
            page_no=page.page_no,
            card_doc_chunk_id=chunk_id,
            start_pos=position[0] if position else None,
            end_pos=position[1] if position else None,
        ))
    return checks


def check_values(
    label: str,
    evidence: list[EvidenceCheck],
    raw_txt: str,
    expected: set | None,
    parse,
) -> tuple[str, list[str]]:
    """값 1건을 근거와 대조한다.

    Args:
        label: 오류 설명에 쓸 항목 이름.
        evidence: 이 값을 뒷받침하는 근거.
        raw_txt: LLM이 옮긴 원문 표기.
        expected: 확인할 숫자. 숫자가 없는 값이면 ``None`` 이다.
        parse: 문자열에서 숫자를 읽는 함수.
    """
    if not evidence:
        return "NO_EVIDENCE", [f"{label}: 근거 없음"]
    located = [item for item in evidence if item.located]
    if not located:
        return "QUOTE_NOT_FOUND", [f"{label}: 인용을 원문에서 찾지 못함"]
    joined = compact(" ".join(item.quote_txt for item in located))
    if compact(raw_txt) not in joined:
        return "VALUE_NOT_IN_QUOTE", [f"{label}: 원문 표기가 인용에 없음"]
    if expected is not None:
        if not expected <= parse(raw_txt):
            return "VALUE_PARSE_DIFF", [f"{label}: 숫자와 원문 표기가 다름"]
        if not expected <= parse(joined):
            return "VALUE_NOT_IN_QUOTE", [f"{label}: 숫자가 인용에 없음"]
    return "OK", []


def check_condition(condition: ConditionItem, page: PageResult) -> ItemCheck:
    """조건 1건의 근거와 금액을 확인한다."""
    evidence = locate_evidence(condition.evidence, page)
    amounts = {value for value in (condition.cond_min_amt, condition.cond_max_amt_excl) if value is not None}
    code, issues = check_values(condition.cond_key, evidence, condition.cond_raw_txt, amounts or None, amounts_in)
    return ItemCheck(value_check_cd=code, link_check_cd=link_check(evidence, []), issues=issues, evidence=evidence)


def link_check(evidence: list[EvidenceCheck], names: list[str]) -> str:
    """값과 대상의 연결을 판단한다. 표·불확실 근거는 사람 확인이 필요하다.

    ``SAME_TEXT`` 라고 답해도 인용 안에 대상 이름이 없으면 믿지 않는다.
    """
    if not evidence or any(item.link_basis != "SAME_TEXT" for item in evidence):
        return "NEEDS_REVIEW"
    if names:
        joined = compact(" ".join(item.quote_txt for item in evidence))
        if not any(compact(name) in joined for name in names):
            return "NEEDS_REVIEW"
    return "TEXT_CONFIRMED"


def check_benefit(benefit: BenefitItem, page: PageResult) -> ItemCheck:
    """혜택 1건의 규칙·한도·조건을 원문과 대조한다."""
    evidence = locate_evidence(benefit.evidence, page)
    codes: list[str] = []
    issues: list[str] = []
    supporting = lambda kind, key: [  # noqa: E731
        item for item in evidence if item.supports == kind and item.support_key == key
    ]

    def add(result: tuple[str, list[str]]) -> None:
        codes.append(result[0])
        issues.extend(result[1])

    for rule in benefit.rules:
        quotes = supporting("RULE", rule.rule_key)
        if rule.value_unit_cd == "PERCENT":
            add(check_values(rule.rule_key, quotes, rule.value_raw_txt,
                             None if rule.value_num is None else {rule.value_num}, rates_in))
        else:
            expected = None if rule.value_num is None or rule.value_unit_cd != "KRW" else {int(rule.value_num)}
            add(check_values(rule.rule_key, quotes, rule.value_raw_txt, expected, amounts_in))
        if rule.min_txn_amt is not None:
            add(check_values(f"{rule.rule_key}.min_txn", quotes, rule.min_txn_raw_txt or "", {rule.min_txn_amt}, amounts_in))
        for condition in rule.conditions:
            result = check_condition(condition, page)
            add((result.value_check_cd, result.issues))
            evidence.extend(result.evidence)
    for limit in benefit.limits:
        quotes = supporting("LIMIT", limit.limit_key)
        expected = None if limit.limit_num is None else {limit.limit_num}
        parse = {"COUNT": counts_in, "KRW": amounts_in, "HANAMONEY": amounts_in}.get(limit.cap_unit_cd, limit_values_in)
        add(check_values(limit.limit_key, quotes, limit.limit_raw_txt, expected, parse))
    for condition in benefit.conditions:
        result = check_condition(condition, page)
        add((result.value_check_cd, result.issues))
        evidence.extend(result.evidence)
    for target in benefit.targets:
        if compact(target.target_nm) not in compact(page.text):
            add(("QUOTE_NOT_FOUND", [f"{target.target_nm}: 대상이 원문에 없음"]))

    applicability = [benefit.brand_txt, benefit.service_grade_txt, benefit.selection_service_txt,
                     benefit.validity_period_txt, *benefit.applicable_cards, *benefit.excluded_cards]
    applicability = [value for value in applicability if value]
    quotes = " ".join(e.quote_txt for e in evidence if e.supports == "APPLICABILITY" and e.located)
    for value in applicability:
        if compact(value) not in compact(quotes):
            add(("VALUE_NOT_IN_QUOTE", [f"적용 정보: 근거에서 확인되지 않음 ({value})"]))

    value_evidence = [item for item in evidence if item.supports in ("RULE", "LIMIT")]
    names = [benefit.bnft_nm, *(target.target_nm for target in benefit.targets)]
    link = link_check(value_evidence, names) if value_evidence else "NEEDS_REVIEW"
    if benefit.certainty == "LOW" or benefit.is_common_candidate or applicability:
        link = "NEEDS_REVIEW"
    return ItemCheck(value_check_cd=worst_value_check(codes), link_check_cd=link, issues=issues, evidence=evidence)
# endregion


# region V6 계약 정규화 (LLM 항목 → 등록용 JSON: 조건식·rule_list)
# =========================================================
# V6 계약 정규화
# =========================================================
def build_cond_expr(conditions: list[ConditionItem]) -> dict | None:
    """조건 목록을 V6 조건식으로 만든다. 한 branch의 atom은 AND다."""
    if not conditions:
        return None
    atoms = [
        {
            "atom_seq": seq,
            "atom_key": condition.cond_key,
            "negate_yn": condition.negate_yn,
            "cond_type_cd": condition.cond_type_cd,
            "cond_basis_cd": condition.cond_basis_cd,
            "cond_min_amt": condition.cond_min_amt,
            "cond_max_amt_excl": condition.cond_max_amt_excl,
            "excl_raw_txt": condition.excl_raw_txt,
            "cond_raw_txt": condition.cond_raw_txt,
            "cond_status_cd": "DRAFT",
        }
        for seq, condition in enumerate(conditions, start=1)
    ]
    return {"expr_status_cd": "DRAFT", "branches": [{"branch_no": 1, "atoms": atoms}]}


# 2026-11-03 계산 구조 정리에서 제거한 키. 이전 추출 이력(card_extr_stg)에는 남아 있어 등록할 때 걸러낸다.
REMOVED_RULE_KEYS = ("predicate_state_cd", "method_ver", "calc_params", "rule_priority", "pool_refs",
                     "calc_method_cd", "payout_unit_cd", "basis_amt")
REMOVED_ATOM_KEYS = ("predicate_method_cd", "predicate_method_ver", "cond_params", "card_excl_item_id", "link_role_cd")


def strip_calc_atoms(expr: dict | None) -> dict | None:
    """조건식 atom에서 계산 실행용 키를 뺀다. 조건 원문·유형·금액은 그대로 둔다."""
    if not isinstance(expr, dict):
        return expr
    return {**expr, "branches": [{**branch, "atoms": [{k: v for k, v in atom.items() if k not in REMOVED_ATOM_KEYS}
                                                     for atom in branch.get("atoms", [])]}
                                 for branch in expr.get("branches", [])]}


def strip_calc_rule(rule: dict) -> dict:
    """규칙에서 계산 실행용 키를 뺀다. 값·단위·대상·조건은 설명 정보로 남긴다."""
    cleaned = {k: v for k, v in rule.items() if k not in REMOVED_RULE_KEYS}
    if "cond_expr" in cleaned:
        cleaned["cond_expr"] = strip_calc_atoms(cleaned["cond_expr"])
    return cleaned


# region 한도 구조 보존 (2026-11-06) — 추출 원본(stg_raw_item)의 limits·rules[].limit_keys를 item_data에 해석 없이 남긴다.
# rule_list 계약(6개 키)과 value_num·value_unit_cd·item_limit_txt의 의미는 바꾸지 않는다. 한도는 보상액 계산에 쓰지 않는다.
# 배경: 더 심플 하나카드 월납 요금(r1→10,000원, r2→15,000원)처럼 구간별 한도 연결이 등록에서 사라졌다.
LIMIT_FIELDS = ("limit_key", "limit_num", "cap_unit_cd", "period_cd", "limit_raw_txt", "shared_scope_txt", "applies_to_benefit_nms")
LIMIT_TIERS_SCHEMA = "LIMIT_TIERS_V1"
PERIOD_COLUMNS = {"MONTH": "월 한도", "YEAR": "연 한도", "DAY": "일 한도"}   # 자동 생성 구간 표의 열 이름(원문 열 이름이 아님)
TIER_EXCLUDED_BASIS = ("TXN_AMT",)                                          # 결제 1건 기준은 실적 구간이 아니다


def limit_struct(raw: dict, rule_keys: list[str], limit_evidence: dict[str, list[str]]) -> dict:
    """추출 한도와 규칙별 한도 연결을 그대로 옮긴다. 한도가 없으면 빈 dict.

    Args:
        raw: 추출 원본(stg_raw_item, 보정 적용 후).
        rule_keys: 등록할 규칙 키(rule_list 순서). 등록하지 않는 규칙의 연결은 남기지 않는다.
        limit_evidence: limit_key → 위치가 확인된 LIMIT 근거 evidence_id 목록.

    Returns:
        ``{"limits": [...], "rule_limits": {rule_key: [limit_key, ...]}}`` 또는 ``{}``.
        값은 추출 원본의 값이며 계산·추론·환산하지 않는다.
    """
    limits = [item for item in raw.get("limits") or [] if item.get("limit_key")]
    if not limits:
        return {}
    known = {item["limit_key"] for item in limits}
    by_rule = {rule.get("rule_key"): rule for rule in raw.get("rules") or []}
    rule_limits = {}
    for key in rule_keys:
        keys = [k for k in (by_rule.get(key) or {}).get("limit_keys") or [] if k in known]
        if keys:
            rule_limits[key] = list(dict.fromkeys(keys))
    return {"limits": [{**{field: item.get(field) for field in LIMIT_FIELDS},
                        "evidence_ids": list(limit_evidence.get(item["limit_key"], []))} for item in limits],
            "rule_limits": rule_limits}


def check_limit_struct(raw: dict, rule_keys: list[str], struct: dict) -> list[str]:
    """보존 결과가 추출 원본과 같은지 검사한다(한도 키·수치·규칙별 연결). 문제 목록, 없으면 빈 목록."""
    issues = []
    raw_limits = {item["limit_key"]: item for item in raw.get("limits") or [] if item.get("limit_key")}
    kept = {item["limit_key"]: item for item in struct.get("limits", [])}
    if set(raw_limits) != set(kept):
        issues.append(f"한도 키가 추출 원본과 다릅니다: {sorted(raw_limits)} != {sorted(kept)}")
    for key in set(raw_limits) & set(kept):
        if any(raw_limits[key].get(field) != kept[key].get(field) for field in LIMIT_FIELDS):
            issues.append(f"한도 값이 추출 원본과 다릅니다: {key}")
    by_rule = {rule.get("rule_key"): rule for rule in raw.get("rules") or []}
    for key in rule_keys:
        expected = [k for k in (by_rule.get(key) or {}).get("limit_keys") or [] if k in raw_limits]
        if list(dict.fromkeys(expected)) != struct.get("rule_limits", {}).get(key, []):
            issues.append(f"규칙 {key}의 한도 연결이 추출 원본과 다릅니다")
    if set(struct.get("rule_limits", {})) - set(rule_keys):
        issues.append("등록하지 않는 규칙의 한도 연결이 있습니다")
    return issues


def _spend_atoms(rule: dict) -> list[dict]:
    return [atom for branch in (rule.get("cond_expr") or {}).get("branches", []) for atom in branch.get("atoms", [])
            if atom.get("cond_type_cd") == "SPEND_REQ"]


def limit_tiers_from_extraction(rules: list[dict], struct: dict, cond_evidence: dict[tuple, list[str]]) -> dict | None:
    """실적 구간별 한도가 원문 추출에서 하나씩 명확히 대응할 때만 ``item_data.limit_tiers`` 를 만든다. 아니면 None.

    조건(모두 충족해야 한다. 하나라도 어기면 구간 표로 단정하지 않고 limits·rule_limits만 남긴다):
        1. 실적 조건(SPEND_REQ, 결제 1건 기준 제외)이 있는 규칙이 2개 이상이고, 규칙마다 그 atom이 정확히 1개이며 기준이 모두 같다.
        2. 구간 규칙마다 원화 금액(limit_num 있음) 한도가 정확히 1개이고, 한도 키가 구간마다 다르며 기간이 같고 확정(UNKNOWN 아님)이다.
           (같은 한도를 여러 구간이 공유하거나 기간이 불명확하면 구간별 한도가 아니다.)
        3. 구간이 겹치지 않는다. 상한(max_amt_excl)이 없는 구간은 가장 높은 구간 하나뿐이다.
           원문에 상한이 없어 구간이 겹치면(예: 30만원 이상 / 60만원 이상) 상한을 추론하지 않는다.
        4. 한도마다 LIMIT 근거, 구간마다 조건(COND) 근거가 위치 확인된 상태로 있다.
    누적형 한도("10만원 추가 제공")는 구간 상한이 없고 기간이 불명확해 2·3에서 걸러진다.

    Args:
        rules: 등록할 rule_list.
        struct: limit_struct 결과.
        cond_evidence: (rule_key, atom_key) → 위치가 확인된 조건 근거 evidence_id 목록.
    """
    limits = {item["limit_key"]: item for item in struct.get("limits", [])}
    rule_limits = struct.get("rule_limits", {})
    tiers = []
    for rule in rules:
        atoms = [atom for atom in _spend_atoms(rule) if atom.get("cond_basis_cd") not in TIER_EXCLUDED_BASIS]
        if not atoms:
            continue
        if len(atoms) != 1 or atoms[0].get("cond_min_amt") is None or not atoms[0].get("cond_basis_cd"):
            return None
        caps = [limits[k] for k in rule_limits.get(rule["rule_key"], [])
                if limits[k].get("cap_unit_cd") == "KRW" and limits[k].get("limit_num") is not None]
        if len(caps) != 1:
            return None
        tiers.append((rule["rule_key"], atoms[0], caps[0]))
    if len(tiers) < 2:
        return None
    if len({atom["cond_basis_cd"] for _, atom, _ in tiers}) != 1:
        return None
    if len({cap["limit_key"] for _, _, cap in tiers}) != len(tiers):
        return None
    periods = {cap.get("period_cd") for _, _, cap in tiers}
    if len(periods) != 1 or next(iter(periods)) not in PERIOD_COLUMNS:
        return None
    tiers.sort(key=lambda item: item[1]["cond_min_amt"])
    for n, (_, atom, _) in enumerate(tiers):
        upper = atom.get("cond_max_amt_excl")
        if n + 1 < len(tiers) and (upper is None or upper > tiers[n + 1][1]["cond_min_amt"]):
            return None
        if upper is not None and upper <= atom["cond_min_amt"]:
            return None
    for rule_key, atom, cap in tiers:
        if not cap.get("evidence_ids") or not cond_evidence.get((rule_key, atom.get("atom_key"))):
            return None
    period = next(iter(periods))
    return {
        "schema_ver": LIMIT_TIERS_SCHEMA, "source": "EXTRACTION", "basis_cd": tiers[0][1]["cond_basis_cd"],
        "tiers": [{"tier_key": rule_key, "rule_key": rule_key, "label": " ".join((atom.get("cond_raw_txt") or "").split()),
                   "min_amt": atom["cond_min_amt"], "max_amt_excl": atom.get("cond_max_amt_excl"),
                   "evidence_ids": list(cond_evidence[(rule_key, atom.get("atom_key"))])} for rule_key, atom, _ in tiers],
        "own": {"column": PERIOD_COLUMNS[period], "column_source": "PERIOD_CD", "merged_cell": False,
                "caps": {rule_key: {"raw": cap.get("limit_raw_txt"), "amount": cap["limit_num"], "limit_key": cap["limit_key"]}
                         for rule_key, _, cap in tiers}},
        "shared": [],
    }
# endregion


def build_rule(rule, targets: list[dict]) -> dict:
    """규칙 1건을 ``rule_list`` 항목으로 만든다. 건당 최소 금액은 규칙 조건이다.

    값과 단위(value_num·value_unit_cd)는 답변의 수치 확인과 검색 텍스트에 쓰는 설명 값이다. 계산 방법·지급 단위·기준 금액은
    저장하지 않는다(LLM 응답에는 추출 확인용으로 남는다). 보상액을 계산하지 않는다.
    """
    conditions = list(rule.conditions)
    if rule.min_txn_amt is not None:
        conditions.append(ConditionItem(
            cond_key=f"MIN_{rule.rule_key}"[:40],
            cond_type_cd="SPEND_REQ",
            cond_basis_cd="TXN_AMT",
            cond_min_amt=rule.min_txn_amt,
            cond_raw_txt=rule.min_txn_raw_txt or "",
            scope="THIS_BENEFIT",
            evidence=[],
        ))
    cond_expr = build_cond_expr(conditions)
    return {
        "rule_key": rule.rule_key,
        "cond_expr": cond_expr,
        "target_list": targets,
        "value_num": json_number(rule.value_num),
        "value_unit_cd": rule.value_unit_cd,
        "rule_status_cd": "DRAFT",
    }


def contract_issues(conditions: list[ConditionItem], normalized: dict) -> list[str]:
    """JSONB 계약에 맞지 않는 구조를 찾는다. 최종 판정은 DB의 ``fn_valid_*`` 와 같아야 한다.

    계산 방법·지급 단위가 UNKNOWN인 것은 문제로 보지 않는다(2026-11-03 계산 구조 정리). 혜택 내용은 원문 근거로 검증한다.
    """
    issues = []
    for condition in conditions:
        if not KEY_PATTERN.match(condition.cond_key):
            issues.append(f"{condition.cond_key}: atom_key 형식 오류")
        if condition.cond_type_cd == "UNKNOWN":
            issues.append(f"{condition.cond_key}: 조건 유형 미확정")
        if condition.cond_type_cd == "SPEND_REQ" and condition.cond_basis_cd in (None, "UNKNOWN"):
            issues.append(f"{condition.cond_key}: 실적 조건의 기준 없음")
        if condition.cond_type_cd in ("SPEND_EXCL", "BNFT_EXCL") and not condition.excl_raw_txt:
            issues.append(f"{condition.cond_key}: 제외 항목 없음")
        low, high = condition.cond_min_amt, condition.cond_max_amt_excl
        if (low is not None and low < 0) or (low is not None and high is not None and high <= low):
            issues.append(f"{condition.cond_key}: 금액 구간 오류")
    if len({condition.cond_key for condition in conditions}) != len(conditions):
        issues.append("조건 키 중복")
    for rule in normalized.get("rule_list", []):
        if not KEY_PATTERN.match(rule["rule_key"]):
            issues.append(f"{rule['rule_key']}: rule_key 형식 오류")
    if len({rule["rule_key"] for rule in normalized.get("rule_list", [])}) != len(normalized.get("rule_list", [])):
        issues.append("rule_key 중복")
    if normalized.get("bnft_type_cd") == "UNKNOWN":
        issues.append("혜택 유형 미확정")
    return issues


def sql_check_code(check: ItemCheck, conflicts: list[str], unresolved: bool, invalid: list[str]) -> str:
    """검증 결과를 ``stg_sql_check_cd`` 하나로 요약한다. ``OK`` 가 아니면 V6 CHECK가 승인을 막는다."""
    if check.value_check_cd != "OK":
        return check.value_check_cd
    if invalid:
        return "CONTRACT_INVALID"
    if conflicts:
        return "MERGE_CONFLICT"
    if unresolved:
        return "SCOPE_UNRESOLVED"
    if check.link_check_cd != "TEXT_CONFIRMED":
        return "LINK_REVIEW"
    return "OK"
# endregion


# region 문서 단위 통합 (페이지별 항목을 혜택명 기준으로 합침. DB·LLM 미사용)
# =========================================================
# 문서 단위 통합
# =========================================================
# 같은 혜택이 요약 페이지와 상세 페이지에 반복되므로, 혜택명(공백 제거·소문자)이 같은 항목을 한 그룹으로 묶는다.
# 그룹의 대표(상세 페이지 우선)가 card_extr_stg의 "대표 행"이 되고, 나머지는 대표 행을 상위 행으로 가리킨다.
def find_benefit_key(name: str, item_keys: dict[str, str]) -> str | None:
    """혜택명으로 문서의 혜택을 찾는다. 같은 이름을 우선하고, 부분 일치는 후보가 하나일 때만 인정한다.

    ``ONE PICK`` 이 ``ONE PICK STYLE`` 에 잘못 연결되지 않게 하기 위한 규칙이다.
    """
    target = compact(name).lower()
    if not target:
        return None
    normalized = {compact(benefit_nm).lower(): key for benefit_nm, key in item_keys.items()}
    if target in normalized:
        return normalized[target]
    partial = [key for benefit_nm, key in normalized.items() if target in benefit_nm or benefit_nm in target]
    return partial[0] if len(partial) == 1 else None


def merge_benefit_group(group: list[tuple[PageResult, StoredItem]]) -> tuple[BenefitItem, list[str]]:
    """같은 혜택의 페이지별 항목을 합친다. 대표는 상세 페이지를 우선한다. 값이 다르면 충돌로 남긴다."""
    ordered = sorted(group, key=page_order)
    return merge_items([(page.page_no, stored.item) for page, stored in ordered])


def merge_items(ordered: list[tuple[int, BenefitItem]]) -> tuple[BenefitItem, list[str]]:
    """대표 순서로 정렬된 ``(페이지, 혜택 항목)`` 을 합친다. 첫 항목이 대표다. DB·LLM을 쓰지 않는다.

    추출 직후 통합과 저장된 추출 원본(stg_raw_item)에서 다시 만드는 통합이 같은 함수를 쓴다.
    """
    base = ordered[0][1].model_copy(deep=True)
    conflicts: list[str] = []
    rule_sign = lambda rule: (rule.value_num, rule.value_unit_cd, rule.min_txn_amt)  # noqa: E731
    base_rules = {rule_sign(rule) for rule in base.rules}
    for page_no, other in ordered[1:]:
        other_rules = {rule_sign(rule) for rule in other.rules}
        if base_rules and other_rules and other_rules != base_rules:
            conflicts.append(f"규칙 값이 페이지 {ordered[0][0]}와 {page_no}에서 다름")
        elif not base_rules:
            base.rules = list(other.rules)
            base_rules = other_rules
        limits = {(limit.period_cd, limit.cap_unit_cd): limit for limit in base.limits}
        for limit in other.limits:
            current = limits.get((limit.period_cd, limit.cap_unit_cd))
            if current is None:
                base.limits.append(limit)
            elif current.limit_num != limit.limit_num:
                conflicts.append(f"{limit.period_cd} {limit.cap_unit_cd} 한도가 페이지별로 다름")
        names = {(target.target_type_cd, compact(target.target_nm)) for target in base.targets}
        base.targets.extend(
            target for target in other.targets if (target.target_type_cd, compact(target.target_nm)) not in names
        )
        known = {condition.cond_key for condition in base.conditions}
        base.conditions.extend(condition for condition in other.conditions if condition.cond_key not in known)
        relation_keys = {relation.relation_key for relation in base.relations}
        base.relations.extend(relation for relation in other.relations if relation.relation_key not in relation_keys)
    return base, conflicts


def normalize_benefit(
    item: BenefitItem,
    bnft_cd: str,
    extra_conditions: list[ConditionItem],
    item_keys: dict[str, str],
) -> tuple[dict, list[str], bool]:
    """혜택을 V6 계약 형태로 만든다. ``(정제본, 계약 문제, 관계 미해결 여부)`` 를 반환한다."""
    targets = [
        {"target_type_cd": target.target_type_cd, "target_key": target.target_nm, "target_nm": target.target_nm}
        for target in item.targets
    ]
    relations = []
    unresolved = False
    for relation in item.relations:
        to_key = find_benefit_key(relation.to_benefit_nm, item_keys)
        if to_key is None or to_key == bnft_cd:
            unresolved = True
            continue
        relations.append({
            "relation_key": relation.relation_key,
            "to_bnft_id": to_key,
            "rel_type_cd": relation.rel_type_cd,
            "trigger_limit_key": relation.trigger_limit_key,  # 후보 검토용. 최종 relation_list에는 넣지 않는다.
            "rel_priority": None,
        })
    conditions = [*item.conditions, *extra_conditions]
    normalized = {
        "schema_ver": SCHEMA_VER,
        "bnft_cd": bnft_cd,
        "bnft_nm": item.bnft_nm,
        "bnft_type_cd": item.bnft_type_cd,
        "bnft_origin_cd": None,
        "is_common_candidate": item.is_common_candidate,
        "bnft_scope_cd": None,
        "bnft_brand_opt_cds": None,
        "bnft_cond_expr": build_cond_expr(conditions),
        "rule_list": [build_rule(rule, targets) for rule in item.rules],
        "relation_list": relations,
        # 한도는 원문 인용(bnft_limit_txt)으로 보관한다. 한도 풀(limit_list·pool_refs) 정규화는 제거했다.
        "verification_status_cd": "PENDING_REVIEW",
    }
    rule_conditions = [condition for rule in item.rules for condition in rule.conditions]
    return normalized, contract_issues([*conditions, *rule_conditions], normalized), unresolved


def combine_checks(checks: list[ItemCheck]) -> ItemCheck:
    """같은 혜택으로 합친 항목의 검증 결과를 합친다."""
    link = "TEXT_CONFIRMED" if all(check.link_check_cd == "TEXT_CONFIRMED" for check in checks) else "NEEDS_REVIEW"
    return ItemCheck(
        value_check_cd=worst_value_check([check.value_check_cd for check in checks]),
        link_check_cd=link,
        issues=[issue for check in checks for issue in check.issues],
        evidence=[item for check in checks for item in check.evidence],
    )


def page_order(pair: tuple[PageResult, StoredItem]) -> tuple[bool, int, int]:
    """대표 항목 선택 순서. 상세 페이지를 요약 페이지보다 먼저 보고, 같은 페이지는 청크 순번을 따른다."""
    return pair[0].extraction.page_role == "SUMMARY", pair[0].page_no, pair[0].chunk_seq


def source_refs(group: list[tuple[PageResult, StoredItem]]) -> list[SourceRef]:
    """통합 결과가 온 페이지 항목 목록. 첫 항목이 대표 행이다."""
    return [SourceRef(page_no=page.page_no, card_doc_chunk_id=page.chunk_id, stg_item_seq=stored.seq)
            for page, stored in group]


def merge_pages(pages: list[PageResult]) -> tuple[list[MergedBenefit], list[MergedCondition]]:
    """페이지별 결과를 문서 단위로 합친다. DB와 LLM을 쓰지 않아 다시 실행해도 결과가 같다."""
    benefit_groups: dict[str, list[tuple[PageResult, StoredItem]]] = {}
    condition_groups: dict[str, list[tuple[PageResult, StoredItem]]] = {}
    for page in pages:
        for stored in page.benefits:
            benefit_groups.setdefault(compact(stored.item.bnft_nm).lower(), []).append((page, stored))
        for stored in page.conditions:
            sign = compact(stored.item.cond_raw_txt).lower() + stored.item.cond_type_cd
            condition_groups.setdefault(sign, []).append((page, stored))
    groups = [sorted(group, key=page_order) for group in benefit_groups.values()]
    item_keys = {group[0][1].item.bnft_nm: make_item_key("BNFT", group[0][1].item.bnft_nm) for group in groups}

    # 특정 혜택 조건은 페이지가 달라도 혜택명으로 찾아 그 혜택의 조건식에 넣는다.
    resolved: list[tuple[list, list[str], bool]] = []
    extra: dict[str, list[ConditionItem]] = {}
    for group in condition_groups.values():
        ordered = sorted(group, key=page_order)
        condition = ordered[0][1].item
        found = [find_benefit_key(target, item_keys) for target in condition.target_benefit_nms]
        matched = list(dict.fromkeys(key for key in found if key))
        unresolved = condition.scope == "UNKNOWN" or (
            condition.scope == "NAMED_BENEFITS" and (not found or None in found)
        )
        resolved.append((ordered, matched, unresolved))
        for key in matched:
            extra.setdefault(key, []).append(condition)

    merged_benefits = []
    for group in groups:
        item, conflicts = merge_benefit_group(group)
        bnft_cd = item_keys[group[0][1].item.bnft_nm]
        normalized, invalid, unresolved = normalize_benefit(item, bnft_cd, extra.get(bnft_cd, []), item_keys)
        check = combine_checks([stored.check for _, stored in group])
        code = sql_check_code(check, conflicts, unresolved, invalid)
        check.issues.extend(invalid)
        info = MergeInfo(
            item_key=bnft_cd,
            source_refs=source_refs(group),
            source_pages=sorted({page.page_no for page, _ in group}),
            conflicts=conflicts,
        )
        normalized["merge"] = info.model_dump(mode="json")
        normalized["checks"] = check.model_dump(mode="json", exclude={"evidence"})
        merged_benefits.append(MergedBenefit(merge=info, check=check, normalized=normalized, sql_check_cd=code))

    merged_conditions = []
    for group, matched, unresolved in resolved:
        condition = group[0][1].item
        check = combine_checks([stored.check for _, stored in group])
        invalid = contract_issues([condition], {})
        code = sql_check_code(check, [], unresolved, invalid)
        check.issues.extend(invalid)
        info = MergeInfo(
            item_key=make_item_key("COND", compact(condition.cond_raw_txt) + condition.cond_type_cd),
            source_refs=source_refs(group),
            source_pages=sorted({page.page_no for page, _ in group}),
        )
        scope_cd = "UNRESOLVED" if unresolved else condition.scope
        normalized = {
            "schema_ver": SCHEMA_VER,
            "scope_cd": scope_cd,
            "applies_to_item_keys": matched,
            "cond_expr": build_cond_expr([condition]),
            "merge": info.model_dump(mode="json"),
            "checks": check.model_dump(mode="json", exclude={"evidence"}),
        }
        merged_conditions.append(MergedCondition(
            merge=info, check=check, scope_cd=scope_cd, applies_to_item_keys=matched,
            normalized=normalized, sql_check_cd=code,
        ))
    return merged_benefits, merged_conditions
# endregion


# region 저장된 추출 원본에서 등록용 혜택 만들기 (3단계 등록 서비스가 사용)
# =========================================================
# 저장된 추출 원본에서 등록용 혜택 만들기
# =========================================================
# 정제본(normalized)은 DB에 저장하지 않는다. 등록 시 CommonBenefitRepository.stored_run이
# list_run_items 결과를 normalize_stored_run에 넣어 merge_pages와 같은 규칙으로 다시 만든다.
@dataclass
class StoredCandidate:
    """통합 대표 행 1건을 추출 원본(stg_raw_item)에서 다시 만든 결과. DB에 저장하지 않는다."""

    stg_id: str
    normalized: dict
    invalid: list[str]
    conflicts: list[str]
    unresolved: bool
    source_cnt: int
    check_cd: str | None        # 현재 계약으로 다시 판단한 검증 코드(effective_check_cd)


def effective_check_cd(stored: str | None, invalid: list[str], conflicts: list[str], unresolved: bool) -> str | None:
    """저장된 검증 코드를 현재 계약으로 다시 판단한다.

    값·근거 검증(NO_EVIDENCE 등)과 병합·연결 판정은 저장된 결과를 따른다. 계약 오류(CONTRACT_INVALID)는
    계약 기준이 바뀌었으므로(2026-11-03 계산 구조 정리) 다시 계산하며, 대상 연결 확인 여부는 알 수 없어 LINK_REVIEW로 둔다.
    """
    if stored != "CONTRACT_INVALID":
        return stored
    if invalid:
        return "CONTRACT_INVALID"
    if conflicts:
        return "MERGE_CONFLICT"
    if unresolved:
        return "SCOPE_UNRESOLVED"
    return "LINK_REVIEW"


def normalize_stored_run(rows: list[dict]) -> dict[str, StoredCandidate]:
    """실행 1건의 저장 행으로 통합 혜택을 다시 만든다. ``merge_pages`` 와 같은 규칙이다.

    ``rows`` 는 같은 실행의 card_extr_stg 행이며 card_extr_stg_id, stg_kind_cd, stg_raw_item,
    stg_parent_card_extr_stg_id, stg_sql_check_cd, page_no, chunk_seq, stg_item_seq, page_role 키가 있어야 한다.
    통합 대표는 검증 코드가 있고 상위 행이 없는 혜택이며, 같은 이름으로 합쳐진 행은 대표를 상위 행으로 가리킨다.
    """
    by_id = {row["card_extr_stg_id"]: row for row in rows}
    order = lambda row: (row.get("page_role") == "SUMMARY", row["page_no"], row.get("chunk_seq") or 0, row["stg_item_seq"])  # noqa: E731
    found = lambda row: (row.get("chunk_seq") or 0, row["stg_item_seq"])  # noqa: E731
    children: dict[str, list[dict]] = {}
    for row in rows:
        parent = row.get("stg_parent_card_extr_stg_id")
        if parent and parent in by_id and by_id[parent]["stg_kind_cd"] == row["stg_kind_cd"]:
            children.setdefault(parent, []).append(row)
    canon = lambda kind: [row for row in rows if row["stg_kind_cd"] == kind and row.get("stg_sql_check_cd")  # noqa: E731
                          and not (row.get("stg_parent_card_extr_stg_id") in by_id
                                   and by_id[row["stg_parent_card_extr_stg_id"]]["stg_kind_cd"] == kind)]
    benefits = canon("BENEFIT")
    item_keys = {row["stg_raw_item"]["bnft_nm"]: make_item_key("BNFT", row["stg_raw_item"]["bnft_nm"]) for row in benefits}
    extra: dict[str, list[ConditionItem]] = {}
    # 문서 단위 조건은 추출 직후 통합과 같은 순서(처리 순서상 처음 나온 위치)로 혜택 조건식에 붙인다.
    for row in sorted(canon("CONDITION"), key=lambda r: min(found(x) for x in [r, *children.get(r["card_extr_stg_id"], [])])):
        condition = ConditionItem.model_validate(row["stg_raw_item"])
        keys = [find_benefit_key(name, item_keys) for name in condition.target_benefit_nms]
        for key in dict.fromkeys(key for key in keys if key):
            extra.setdefault(key, []).append(condition)
    out = {}
    for row in benefits:
        group = sorted([row, *children.get(row["card_extr_stg_id"], [])], key=order)
        item, conflicts = merge_items([(member["page_no"], BenefitItem.model_validate(member["stg_raw_item"])) for member in group])
        bnft_cd = item_keys[row["stg_raw_item"]["bnft_nm"]]
        normalized, invalid, unresolved = normalize_benefit(item, bnft_cd, extra.get(bnft_cd, []), item_keys)
        out[row["card_extr_stg_id"]] = StoredCandidate(
            row["card_extr_stg_id"], normalized, invalid, conflicts, unresolved, len(group),
            effective_check_cd(row.get("stg_sql_check_cd"), invalid, conflicts, unresolved))
    return out
# endregion


# region 실행 흐름 (ExtractionService: 실행 등록 → 청크별 LLM 호출·저장 → 문서 통합 저장)
# =========================================================
# 실행 흐름
# =========================================================
class ExtractionService:
    """문서 1건의 AI 추출을 실행하고 결과를 V6 중간 테이블에 저장한다.

    저장은 세 단계로 나눈다. 호출 이력은 비용이 든 응답을 잃지 않도록 바로 커밋하고,
    페이지 항목과 문서 통합은 각각 트랜잭션으로 묶는다. 어느 단계가 실패해도 그때까지의 이력은 남는다.
    """

    def __init__(
        self,
        sql_session: PostgresDbSession,
        llm_client: LlmClient,
        data_root: Path = DATA_ROOT,
        max_attempts: int = 1,
    ):
        self.sql_session = sql_session
        self.llm_client = llm_client
        self.repository = ExtractionRepository(sql_session)
        self.data_root = Path(data_root)
        self.max_attempts = max_attempts

    def run(self, card_doc_id: str, card_id: int | None = None, page_numbers: set[int] | None = None,
            split_rule_ver: str | None = None, chunk_ids: set[str] | None = None) -> RunResult:
        """문서를 추출한다. 실행할 때마다 새 ``card_ai_run_id`` 를 만들고 이전 결과는 바꾸지 않는다.

        한 문서에 분리 규칙이 다른 청크가 함께 있으면(예: PAGE_V1과 BLOCK_V1) ``split_rule_ver`` 로 하나를 고른다.
        같은 원문을 두 번 추출하지 않기 위해서다. ``chunk_ids`` 는 일부 청크만 시험할 때 쓰며, 그 실행은 항상 PARTIAL이고
        재사용되지 않는다.

        Args:
            card_doc_id: 추출할 card_doc.card_doc_id.
            card_id: 상품설명서면 card_product.card_id. ``None`` 이면 BRAND_SERVICE(공통 안내서)만 허용한다.
            page_numbers: 일부 페이지만 실행할 때의 페이지 번호 집합.
            split_rule_ver: PAGE_V1 / BLOCK_V1 중 사용할 청크 규칙.
            chunk_ids: 일부 청크만 실행할 때의 card_doc_chunk_id 집합.

        Returns:
            RunResult(card_ai_run_id, status, 성공·실패 청크 수, 통합 저장 여부, 비고, 재사용 여부).

        부작용:
            card_ai_run INSERT/UPDATE, card_ai_call INSERT(호출마다), card_extr_stg·card_source_evidence INSERT,
            card_extr_stg UPDATE(통합). LLM 유료 호출(``llm_client.extract``)이 청크 수만큼 일어난다.

        Raises:
            ExtractionError: 상품·문서·입력 페이지·로컬 PDF가 준비되지 않은 경우.
        """
        # region 입력 검증과 대상 청크 선택 (DB 조회만, 변경 없음)
        if card_id is not None and self.repository.select_card_product(card_id) is None:
            raise ExtractionError(f"card_product가 없습니다: {card_id}")
        document = self.repository.select_doc(card_doc_id)
        if document is None:
            raise ExtractionError(f"card_doc이 없습니다: {card_doc_id}")
        if card_id is None and document.get("doc_type_cd") != "BRAND_SERVICE":
            raise ExtractionError("카드 없는 추출은 BRAND_SERVICE 문서만 지원합니다")
        chunks = self.repository.select_ai_input_chunks(card_doc_id)
        if split_rule_ver is not None:
            chunks = [c for c in chunks if rule_of(c) == split_rule_ver]
        elif len({rule_of(c) for c in chunks}) > 1:
            raise ExtractionError("분리 규칙이 다른 청크가 함께 있어 split_rule_ver를 지정해야 합니다")
        if not chunks:
            raise ExtractionError(f"AI 입력 페이지가 없습니다: {card_doc_id}")
        omitted = []
        if page_numbers is not None:
            if not page_numbers or not page_numbers.issubset({c['page_no'] for c in chunks}):
                raise ExtractionError("요청 페이지가 AI 입력 대상에 없습니다")
            omitted = [c['page_no'] for c in chunks if c['page_no'] not in page_numbers]
            chunks = [c for c in chunks if c['page_no'] in page_numbers]
        omitted_chunks = []
        if chunk_ids is not None:
            if not chunk_ids or not chunk_ids.issubset({c['card_doc_chunk_id'] for c in chunks}):
                raise ExtractionError("요청 청크가 AI 입력 대상에 없습니다")
            omitted_chunks = [c['card_doc_chunk_id'] for c in chunks if c['card_doc_chunk_id'] not in chunk_ids]
            chunks = [c for c in chunks if c['card_doc_chunk_id'] in chunk_ids]
        # 이미지 렌더링에 쓸 로컬 PDF. 해시가 card_doc.doc_sha256과 다르거나 파일이 없으면 ExtractionError.
        pdf_path = self._local_pdf(document)
        # blocked: 내용이 있지만 AI 입력에서 빠진 페이지(OCR 검토 대기 등) + 이번 실행에서 제외한 페이지.
        blocked = sorted(set(self.repository.select_blocked_pages(card_doc_id)) | set(omitted))
        params = self._run_param()
        params["split_rule_ver"] = rule_of(chunks[0])
        if chunk_ids is not None:
            params["chunk_ids"] = sorted(chunk_ids)
        # endregion

        # region 이전 실행 재사용 판정 (중복 LLM 호출 방지)
        # 입력 전체(문서 해시·청크·파라미터·모델 설정·프롬프트 해시·렌더러 버전)를 SHA-256 지문으로 만들고,
        # 같은 지문의 SUCCEEDED 실행이 있으며 _complete_reuse가 통과하면 새 실행 없이 그 run_id를 반환한다.
        # 부분 실행, 제외 페이지 또는 알려지지 않은 모델 설정은 재사용하지 않는다.
        config = getattr(self.llm_client, "reuse_config", None)
        if card_id is None and page_numbers is None and chunk_ids is None and not blocked and isinstance(config, dict):
            payload = {"doc_sha256": document["doc_sha256"], "card_id": card_id,
                       "chunks": chunks, "params": params, "model_config": config,
                       "prompt_sha256": hashlib.sha256(PROMPT_TXT.encode()).hexdigest(),
                       "renderer": pymupdf.VersionBind}
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                                    default=str).encode()).hexdigest()
            params["reuse_fingerprint"] = fingerprint
            for candidate in self.repository.select_reusable_runs(card_doc_id, self.llm_client.model_nm,
                                                                  PROMPT_VER, fingerprint):
                run_id = candidate["card_ai_run_id"]
                if self._complete_reuse(run_id, chunks):
                    return RunResult(run_id, "SUCCEEDED", len(chunks), 0, True, reused=True)
        # endregion

        # 새 실행 등록. 트랜잭션 밖이라 바로 커밋되고, DB가 card_ai_run_id(PK)를 발급한다.
        # 이 run_id가 이후 card_ai_call·card_extr_stg의 FK 값이 된다. 매 실행 새 ID라 이전 결과는 바뀌지 않는다.
        run_id = self.repository.insert_run(self.llm_client.model_nm, PROMPT_VER, PROMPT_TXT, params, card_doc_id)

        # 오류 처리: 처리 중 어떤 예외든 실행을 FAILED로 기록한 뒤 다시 던진다.
        try:
            return self._run_pages(run_id, card_id, chunks, pdf_path, blocked, omitted_chunks)
        except Exception:
            self.repository.finish_run(run_id, "FAILED", "처리 중 오류")     # RUNNING으로 남지 않게 한다
            raise

    def _complete_reuse(self, run_id: str, chunks: list[dict]) -> bool:
        """호출 응답과 후보·근거가 모두 남아 있는 성공 실행만 재사용한다."""
        calls = self.repository.select_run_calls(run_id)
        rows = self.repository.select_reuse_items(run_id)
        expected_ids = {c["card_doc_chunk_id"] for c in chunks}
        selected = {}
        for call in calls:
            if call["call_status"] == "SUCCEEDED":
                selected[call["card_doc_chunk_id"]] = call
        if set(selected) != expected_ids:
            return False
        expected = []
        try:
            for chunk_id, call in selected.items():
                page = PageExtraction.model_validate(call["call_resp_json"])
                if page.page_no != call["page_no"]:
                    return False
                for seq, item in enumerate([*page.benefits, *page.card_conditions], 1):
                    quotes = [e.quote_txt for e in item.evidence]
                    if isinstance(item, BenefitItem):
                        quotes += [e.quote_txt for c in item.conditions for e in c.evidence]
                        quotes += [e.quote_txt for r in item.rules for c in r.conditions for e in c.evidence]
                    kind = "BENEFIT" if isinstance(item, BenefitItem) else "CONDITION"
                    expected.append((chunk_id, call["call_seq"], seq, kind, item.model_dump(mode="json"), sorted(quotes)))
            if len(rows) != len(expected):
                return False
            indexed = {(r["card_doc_chunk_id"], r["call_seq"], r["stg_item_seq"]): r for r in rows}
            for chunk_id, call_seq, seq, kind, raw, quotes in expected:
                row = indexed.get((chunk_id, call_seq, seq))
                if (not row or row["card_id"] is not None or row["stg_kind_cd"] != kind or
                        row["stg_raw_item"] != raw or sorted(row["evidence_quotes"]) != quotes
                        or not row["stg_sql_check_cd"]):
                    return False
        except (ValidationError, KeyError, TypeError):
            return False
        return True

    def _run_pages(self, run_id: str, card_id: int, chunks: list[dict], pdf_path: Path, blocked: list[int],
                   omitted_chunks: list[str] = ()) -> RunResult:
        """페이지를 차례로 처리하고 모두 성공했을 때만 문서 통합을 저장한다.

        상태 결정:
            SUCCEEDED = 통합 저장 성공 + 제외 페이지·제외 청크 없음
            PARTIAL   = 성공한 청크가 하나라도 있으나 위 조건을 못 채움
            FAILED    = 성공한 청크가 없음
        마지막에 finish_run으로 card_ai_run 상태를 UPDATE한다(트랜잭션 밖, 즉시 커밋).
        """
        pages: list[PageResult] = []
        failed = 0
        # 같은 페이지의 다른 청크(특히 NOTICE)를 문맥으로 함께 보내기 위해 페이지별 청크 목록을 만든다.
        per_page: dict[int, list[dict]] = {}
        for chunk in self.repository.select_ai_input_chunks(chunks[0]["card_doc_id"]):
            if rule_of(chunk) == rule_of(chunks[0]):
                per_page.setdefault(chunk["page_no"], []).append(chunk)
        for chunk in chunks:
            siblings = per_page.get(chunk["page_no"], [chunk])
            context = [(c["card_doc_chunk_id"], c["chunk_raw_txt"]) for c in siblings
                       if c.get("chunk_type_cd") == "NOTICE" and c["card_doc_chunk_id"] != chunk["card_doc_chunk_id"]]
            page = self._process_chunk(run_id, card_id, chunk, pdf_path, context, whole_page=len(siblings) == 1)
            if page is None:
                failed += 1
            else:
                pages.append(page)

        merged = False
        notes = [f"AI 입력 제외 페이지: {blocked}"] if blocked else []
        if omitted_chunks:
            notes.append(f"AI 입력 제외 청크: {len(omitted_chunks)}건")
        # 분기: 한 청크라도 실패하면 문서 단위 통합을 하지 않는다(페이지 원본 행은 이미 저장되어 남는다).
        if failed:
            notes.append("실패한 페이지가 있어 문서 통합을 하지 않음")
        else:
            merged = self._store_merge(pages)
            if not merged:
                notes.append("문서 통합 저장 실패")
        status = "SUCCEEDED" if merged and not blocked and not omitted_chunks else ("PARTIAL" if pages else "FAILED")
        note = " / ".join(notes) or None
        self.repository.finish_run(run_id, status, note)
        extraction_logger.info("EXTRACT %s run=%s pages_ok=%d pages_failed=%d", status, run_id, len(pages), failed)
        return RunResult(run_id, status, len(pages), failed, merged, note)

    def _run_param(self) -> dict:
        """실행 재현에 필요한 값을 ``run_param`` 으로 만든다."""
        schema = json.dumps(PageExtraction.model_json_schema(), sort_keys=True, ensure_ascii=False)
        return {
            "schema_ver": SCHEMA_VER,
            "merge_ver": MERGE_VER,
            "schema_sha256": hashlib.sha256(schema.encode("utf-8")).hexdigest(),
            "input_mode": INPUT_MODE,
            "image_dpi": IMAGE_DPI,
            "split_rule_ver": SPLIT_RULE_VER,
        }

    def _local_pdf(self, document: dict) -> Path:
        """로컬 PDF를 확인한다. 추출은 Storage에 접속하지 않는다."""
        path = self.data_root.parent / document["doc_file_nm"]
        resolved = resolve_local_pdf(path, document["doc_sha256"])
        if not resolved.usable:
            raise ExtractionError(f"로컬 PDF를 쓸 수 없습니다: {resolved.source}")
        return path

    def build_input(self, chunk: dict, pdf_path: Path, context: list[tuple[str, str]] = (),
                    whole_page: bool = True) -> PageInput:
        """LLM 입력을 만든다. 이미지는 저장하지 않는다.

        청크가 페이지 전체이면 기존처럼 페이지 텍스트와 이미지를 보낸다. 페이지 일부이면 이미지를 빼고
        대상 청크와 같은 페이지 유의사항 청크를 구분해 보낸다. 추출은 대상 청크에서만 한다.
        """
        image = None
        if whole_page:
            with pymupdf.open(pdf_path) as document:
                image = document[chunk["page_no"] - 1].get_pixmap(dpi=IMAGE_DPI).tobytes("png")
            text = chunk["chunk_raw_txt"]
        else:
            text = f"[추출 대상: 청크 {chunk['chunk_seq']}]\n{chunk['chunk_raw_txt']}"
            if context:
                text += "\n\n[같은 페이지 유의사항 문맥: 인용 전용]\n" + "\n".join(body for _, body in context)
        digest = hashlib.sha256()
        for part in (PROMPT_TXT.encode("utf-8"), text.encode("utf-8"), image or b""):
            digest.update(part)
        return PageInput(PROMPT_TXT, chunk["page_no"], text, image, digest.hexdigest())

    def _process_chunk(self, run_id: str, card_id: int, chunk: dict, pdf_path: Path,
                       context: list[tuple[str, str]] = (), whole_page: bool = True) -> PageResult | None:
        """청크 1건을 호출하고 저장한다. 실패하면 ``None`` 을 반환하고 다음 청크를 계속 처리한다.

        처리 순서: build_input → (max_attempts회까지) _call_llm → 성공 응답이면 PageResult 생성
        → [트랜잭션] _store_page(검증 + card_extr_stg·card_source_evidence INSERT) → commit

        오류 처리: LLM 응답 파싱 실패는 다음 시도로 넘어가고(기본 max_attempts=1이면 바로 None),
        저장 중 psycopg.Error는 이 청크의 INSERT만 rollback되고 ``None`` 을 반환한다.
        """
        page_input = self.build_input(chunk, pdf_path, context, whole_page)
        # call_seq는 같은 청크의 재시도 번호다. card_ai_call·card_extr_stg 식별자의 일부로 저장된다.
        for call_seq in range(1, self.max_attempts + 1):
            extraction = self._call_llm(run_id, chunk, call_seq, page_input)
            if extraction is None:
                continue
            page = PageResult(chunk["page_no"], chunk["card_doc_chunk_id"], chunk["chunk_raw_txt"], extraction,
                              chunk_seq=chunk.get("chunk_seq", 0), context=list(context))
            try:
                # 트랜잭션 시작: 이 청크의 항목·근거 INSERT를 한 단위로 묶는다.
                with self.sql_session.transaction():
                    self._store_page(run_id, card_id, chunk, call_seq, page)
            except psycopg.Error as error:
                extraction_logger.error("EXTRACT PAGE SAVE FAILED page=%d: %s", chunk["page_no"], type(error).__name__)
                return None
            return page
        return None

    def _call_llm(self, run_id: str, chunk: dict, call_seq: int, page_input: PageInput) -> PageExtraction | None:
        """LLM을 호출해 호출 이력을 남기고 검증된 응답을 반환한다.

        성공·실패와 관계없이 card_ai_call 1행을 INSERT한다. 트랜잭션 밖에서 실행되므로 바로 커밋된다.
        CALL_STATUS: FAILED(호출 예외) / PARSE_ERROR(JSON·스키마·page_no 불일치) / SUCCEEDED.

        Returns:
            검증된 ``PageExtraction``. 호출 실패·파싱 실패면 ``None``.
        """
        started = perf_counter()
        # card_ai_call INSERT 파라미터. 기본값 FAILED로 시작해 결과에 따라 채운다.
        call = {
            "CARD_AI_RUN_ID": run_id,
            "CARD_DOC_ID": chunk["card_doc_id"],
            "PAGE_NO": chunk["page_no"],
            "CARD_DOC_CHUNK_ID": chunk["card_doc_chunk_id"],
            "CALL_SEQ": call_seq,
            "CALL_INPUT_SHA256": page_input.input_sha256,
            "CALL_STATUS": "FAILED",
            "CALL_RESP_RAW": None,
            "CALL_RESP_JSON": None,
            "CALL_ERROR_MSG": None,
            "CALL_INPUT_TOKEN_CNT": None,
            "CALL_OUTPUT_TOKEN_CNT": None,
            "CALL_LATENCY_MS": None,
        }
        extraction = None
        try:
            response = self.llm_client.extract(page_input)
        except Exception as error:
            call["CALL_ERROR_MSG"] = type(error).__name__        # 응답 본문이나 키가 섞이지 않도록 유형만 남긴다
        else:
            call.update(
                CALL_RESP_RAW=response.raw_text,
                CALL_INPUT_TOKEN_CNT=response.input_tokens,
                CALL_OUTPUT_TOKEN_CNT=response.output_tokens,
            )
            extraction = self._parse(response.raw_text, chunk["page_no"], call)
        call["CALL_LATENCY_MS"] = int((perf_counter() - started) * 1000)
        # 비용이 든 응답을 잃지 않도록 트랜잭션 없이 바로 저장(커밋)한다.
        self.repository.insert_call(call)
        return extraction

    @staticmethod
    def _parse(raw_text: str, page_no: int, call: dict) -> PageExtraction | None:
        """응답을 Pydantic으로 검증한다. 실패하면 ``call`` 에 PARSE_ERROR를 기록한다."""
        try:
            extraction = PageExtraction.model_validate(json.loads(raw_text))
        except (json.JSONDecodeError, ValidationError) as error:
            call.update(CALL_STATUS="PARSE_ERROR", CALL_ERROR_MSG=type(error).__name__)
            return None
        if extraction.page_no != page_no:
            call.update(CALL_STATUS="PARSE_ERROR", CALL_ERROR_MSG=f"page_no 불일치: {extraction.page_no}")
            return None
        call.update(CALL_STATUS="SUCCEEDED", CALL_RESP_JSON=extraction.model_dump(mode="json"))
        return extraction

    def _store_page(self, run_id: str, card_id: int, chunk: dict, call_seq: int, page: PageResult) -> None:
        """페이지 항목과 근거를 저장한다. 호출자가 트랜잭션을 연다.

        혜택(benefits) → 카드 조건(card_conditions) 순서로 항목 순번(stg_item_seq)을 1부터 매긴다.
        각 항목은 저장 전에 원문 대조(check_benefit / check_condition)를 거치고, 결과 ItemCheck를 PageResult에 보관해
        뒤의 문서 통합(merge_pages)에서 검증 코드 계산에 쓴다.
        """
        seq = 0
        for benefit in page.extraction.benefits:
            seq += 1
            check = check_benefit(benefit, page)
            stg_id = self._store_item(run_id, card_id, chunk, call_seq, seq, "BENEFIT", benefit, check)
            page.benefits.append(StoredItem(stg_id, seq, benefit, check))
        for condition in page.extraction.card_conditions:
            seq += 1
            check = check_condition(condition, page)
            stg_id = self._store_item(run_id, card_id, chunk, call_seq, seq, "CONDITION", condition, check)
            page.conditions.append(StoredItem(stg_id, seq, condition, check))

    def _store_item(self, run_id, card_id, chunk, call_seq, seq, kind, item, check: ItemCheck) -> str:
        """항목 1건과 근거를 저장한다. 위치를 찾은 첫 근거가 대표 근거다.

        1) card_extr_stg INSERT → DB가 card_extr_stg_id(PK) 발급
        2) 그 ID를 FK(card_extr_stg_id)로 넣어 card_source_evidence에 근거 전체를 일괄 INSERT
           (위치를 못 찾은 근거도 start_pos/end_pos=NULL로 저장된다)

        Returns:
            발급된 card_extr_stg_id.
        """
        primary = next((evidence for evidence in check.evidence if evidence.located), None)
        first = primary or (check.evidence[0] if check.evidence else None)
        # stg_raw_item에는 LLM 항목 원본(JSON)을 그대로 저장한다. 등록용 정제본은 저장하지 않는다.
        stg_id = self.repository.insert_stg({
            "CARD_AI_RUN_ID": run_id,
            "CARD_DOC_ID": chunk["card_doc_id"],
            "PAGE_NO": chunk["page_no"],
            "CARD_DOC_CHUNK_ID": chunk["card_doc_chunk_id"],
            "CALL_SEQ": call_seq,
            "STG_ITEM_SEQ": seq,
            "CARD_ID": card_id,
            "STG_KIND_CD": kind,
            "STG_RAW_ITEM": item.model_dump(mode="json"),
            "STG_EVIDENCE_TXT": first.quote_txt if first else "",
            "STG_EVIDENCE_START_POS": primary.start_pos if primary else None,
            "STG_EVIDENCE_END_POS": primary.end_pos if primary else None,
        })
        self.repository.insert_evidence([
            {
                "CARD_DOC_ID": chunk["card_doc_id"],
                "PAGE_NO": evidence.page_no,
                "CARD_DOC_CHUNK_ID": evidence.card_doc_chunk_id,
                "CARD_EXTR_STG_ID": stg_id,
                "QUOTE_TXT": evidence.quote_txt,
                "START_POS": evidence.start_pos,
                "END_POS": evidence.end_pos,
            }
            for evidence in check.evidence
        ])
        return stg_id

    def _store_merge(self, pages: list[PageResult]) -> bool:
        """문서 통합 결과를 한 트랜잭션으로 저장한다. 실패해도 페이지 원본은 남는다."""
        benefits, conditions = merge_pages(pages)
        # 한 페이지에 청크가 여럿이면 항목 순번이 청크마다 1부터 시작한다. 청크 ID로 구분한다.
        lookup = {
            (page.chunk_id, stored.seq): stored.stg_id
            for page in pages for stored in (*page.benefits, *page.conditions)
        }
        benefit_ids = {
            benefit.merge.item_key: lookup[(benefit.merge.source_refs[0].card_doc_chunk_id,
                                            benefit.merge.source_refs[0].stg_item_seq)]
            for benefit in benefits
        }
        try:
            # 트랜잭션 시작: 통합 결과 UPDATE를 문서 단위로 한 번에 commit/rollback한다.
            with self.sql_session.transaction():
                for benefit in benefits:
                    self._store_group(benefit.merge, benefit.sql_check_cd, None, lookup)
                # 조건이 혜택 하나에만 적용되면 그 혜택 대표 행을 상위 행으로 연결한다.
                for condition in conditions:
                    keys = condition.applies_to_item_keys
                    parent = benefit_ids[keys[0]] if len(keys) == 1 else None
                    self._store_group(condition.merge, condition.sql_check_cd, parent, lookup)
        except psycopg.Error as error:
            extraction_logger.error("EXTRACT MERGE SAVE FAILED: %s", type(error).__name__)
            return False
        return True

    def _store_group(self, merge: MergeInfo, check_cd: str, parent: str | None, lookup: dict) -> None:
        """대표 행에 검증 코드를 쓰고 나머지 행은 대표 행을 가리키게 한다.

        등록용 정제본은 저장하지 않는다. 등록할 때 ``normalize_stored_run`` 이 원본 행과 이 연결로 다시 만든다.
        """
        first, *others = merge.source_refs
        canonical = lookup[(first.card_doc_chunk_id, first.stg_item_seq)]
        self.repository.update_stg_merge(canonical, parent, check_cd)
        duplicate_cd = "MERGE_CONFLICT" if merge.conflicts else "MERGED_DUP"
        # 중복 행: stg_parent_card_extr_stg_id = 대표 행 ID (같은 테이블 자기 참조). 등록 단계는 상위 행이 없는 대표만 읽는다.
        for ref in others:
            self.repository.update_stg_merge(lookup[(ref.card_doc_chunk_id, ref.stg_item_seq)], canonical, duplicate_cd)
# endregion
