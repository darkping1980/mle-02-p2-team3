"""AI 추출 흐름을 담당하는 Service 모듈. LLM 호출 → 응답 검증 → 페이지 저장 → 문서 통합 순서로 처리한다.

LLM 클라이언트는 주입받는다. 이 모듈은 특정 모델이나 제공자에 의존하지 않는다.
값 검증은 두 가지를 구분한다. 값이 원문에 있는지(``value_check_cd``)와
그 값이 이 혜택의 값인지(``link_check_cd``)다. 표에서 읽은 연결은 텍스트로 증명할 수 없어 사람이 확인한다.
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

PROMPT_VER = "EXTRACT_V1"
IMAGE_DPI = 150
INPUT_MODE = "TEXT_IMAGE"
KEY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")

# 값 검증 코드. 앞에 있을수록 심각하다.
VALUE_CHECK_ORDER = ("NO_EVIDENCE", "QUOTE_NOT_FOUND", "VALUE_NOT_IN_QUOTE", "VALUE_PARSE_DIFF", "OK")

AMOUNT_PATTERN = re.compile(r"(?:(\d[\d,]*)만)?(?:(\d[\d,]*)천)?(\d[\d,]*)?원")
COUNT_PATTERN = re.compile(r"(\d[\d,]*)회")
RATE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)%")

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
"""


class ExtractionError(Exception):
    """추출을 시작할 수 없는 경우."""


@dataclass(frozen=True)
class PageInput:
    """LLM 입력 1건."""

    prompt_txt: str
    page_no: int
    page_text: str
    image_png: bytes
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


@dataclass
class RunResult:
    """실행 결과 요약."""

    card_ai_run_id: str
    status: str
    pages_ok: int
    pages_failed: int
    merged: bool
    note: str | None = None


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


def make_item_key(prefix: str, name: str) -> str:
    """혜택명으로 실행마다 같은 키를 만든다. LLM이 준 키는 실행마다 달라질 수 있어 쓰지 않는다."""
    digest = hashlib.sha256(compact(name).lower().encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}_{digest}"


def worst_value_check(codes: list[str]) -> str:
    """값 검증 코드 중 가장 심각한 것을 고른다."""
    return min(codes, key=VALUE_CHECK_ORDER.index) if codes else "OK"


# =========================================================
# 원문 대조
# =========================================================
def locate_evidence(quotes: list[EvidenceQuote], page: PageResult) -> list[EvidenceCheck]:
    """인용문을 원문에서 찾아 위치를 채운다."""
    checks = []
    for quote in quotes:
        position = locate_quote(page.text, quote.quote_txt)
        checks.append(EvidenceCheck(
            quote_txt=quote.quote_txt,
            supports=quote.supports,
            support_key=quote.support_key,
            link_basis=quote.link_basis,
            page_no=page.page_no,
            card_doc_chunk_id=page.chunk_id,
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
        add(check_values(limit.limit_key, quotes, limit.limit_raw_txt, expected,
                         counts_in if limit.cap_unit_cd == "COUNT" else amounts_in))
    for condition in benefit.conditions:
        result = check_condition(condition, page)
        add((result.value_check_cd, result.issues))
        evidence.extend(result.evidence)
    for target in benefit.targets:
        if compact(target.target_nm) not in compact(page.text):
            add(("QUOTE_NOT_FOUND", [f"{target.target_nm}: 대상이 원문에 없음"]))

    value_evidence = [item for item in evidence if item.supports in ("RULE", "LIMIT")]
    names = [benefit.bnft_nm, *(target.target_nm for target in benefit.targets)]
    link = link_check(value_evidence, names) if value_evidence else "NEEDS_REVIEW"
    if benefit.certainty == "LOW" or benefit.is_common_candidate:
        link = "NEEDS_REVIEW"
    return ItemCheck(value_check_cd=worst_value_check(codes), link_check_cd=link, issues=issues, evidence=evidence)


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
            "predicate_method_cd": None,
            "predicate_method_ver": None,
            "cond_params": None,
            "card_excl_item_id": None,
            "excl_raw_txt": condition.excl_raw_txt,
            "cond_raw_txt": condition.cond_raw_txt,
            "link_role_cd": None,
            "cond_status_cd": "DRAFT",
        }
        for seq, condition in enumerate(conditions, start=1)
    ]
    return {"expr_status_cd": "DRAFT", "branches": [{"branch_no": 1, "atoms": atoms}]}


def build_rule(rule, targets: list[dict]) -> dict:
    """규칙 1건을 ``rule_list`` 항목으로 만든다. 건당 최소 금액은 규칙 조건이다."""
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
        "predicate_state_cd": "CONDITIONAL" if cond_expr else "PENDING_REVIEW",
        "target_list": targets,
        "calc_method_cd": rule.calc_method_cd,
        "method_ver": 1,
        "value_num": json_number(rule.value_num),
        "value_unit_cd": rule.value_unit_cd,
        "payout_unit_cd": rule.payout_unit_cd,
        "basis_amt": None,
        "calc_params": None,
        "rule_priority": None,
        "rule_status_cd": "DRAFT",
        "pool_refs": [{"pool_id": key, "pool_role_cd": "CONSUME"} for key in rule.limit_keys],
    }


def contract_issues(conditions: list[ConditionItem], normalized: dict) -> list[str]:
    """V6 JSONB 계약에 맞지 않는 값을 찾는다. 최종 판정은 DB의 ``fn_valid_*`` 와 같아야 한다."""
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
        if rule["calc_method_cd"] == "UNKNOWN" or rule["payout_unit_cd"] in (None, "UNKNOWN"):
            issues.append(f"{rule['rule_key']}: 계산 방법 미확정")
    pool_keys = {pool["pool_key"] for pool in normalized.get("limit_list", [])}
    for rule in normalized.get("rule_list", []):
        for ref in rule["pool_refs"]:
            if ref["pool_id"] not in pool_keys:
                issues.append(f"{rule['rule_key']}: 없는 한도 참조 {ref['pool_id']}")
    for pool in normalized.get("limit_list", []):
        if pool["limit_num"] is None or pool["period_cd"] == "UNKNOWN" or pool["cap_unit_cd"] == "UNKNOWN":
            issues.append(f"{pool['pool_key']}: 한도 값 미확정")
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


# =========================================================
# 문서 단위 통합
# =========================================================
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
    ordered = sorted(group, key=lambda pair: (pair[0].extraction.page_role == "SUMMARY", pair[0].page_no))
    base = ordered[0][1].item.model_copy(deep=True)
    conflicts: list[str] = []
    rule_sign = lambda rule: (rule.calc_method_cd, rule.value_num, rule.value_unit_cd, rule.min_txn_amt)  # noqa: E731
    base_rules = {rule_sign(rule) for rule in base.rules}
    for page, stored in ordered[1:]:
        other = stored.item
        other_rules = {rule_sign(rule) for rule in other.rules}
        if base_rules and other_rules and other_rules != base_rules:
            conflicts.append(f"규칙 값이 페이지 {ordered[0][0].page_no}와 {page.page_no}에서 다름")
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
            "trigger_pool_id": relation.trigger_limit_key,
            "rel_priority": None,
        })
    conditions = [*item.conditions, *extra_conditions]
    normalized = {
        "schema_ver": SCHEMA_VER,
        "bnft_cd": bnft_cd,
        "bnft_nm": item.bnft_nm,
        "bnft_type_cd": item.bnft_type_cd,
        "bnft_origin_cd": "LOCAL",
        "is_common_candidate": item.is_common_candidate,
        "bnft_scope_cd": "PRODUCT",
        "bnft_brand_opt_cds": None,
        "bnft_cond_expr": build_cond_expr(conditions),
        "rule_select_cd": None,
        "rule_list": [build_rule(rule, targets) for rule in item.rules],
        "relation_list": relations,
        "limit_list": [
            {
                "pool_key": limit.limit_key,
                "pool_scope_cd": "BENEFIT_GROUP" if limit.shared_scope_txt else "BENEFIT",
                "period_cd": limit.period_cd,
                "cap_unit_cd": limit.cap_unit_cd,
                "aggregation_key_cd": "CARD_MEMBER",
                "limit_num": json_number(limit.limit_num),
                "shared_scope_txt": limit.shared_scope_txt,
            }
            for limit in item.limits
        ],
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


def page_order(pair: tuple[PageResult, StoredItem]) -> tuple[bool, int]:
    """대표 항목 선택 순서. 상세 페이지를 요약 페이지보다 먼저 본다."""
    return pair[0].extraction.page_role == "SUMMARY", pair[0].page_no


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

    def run(self, card_doc_id: str, card_id: int, page_numbers: set[int] | None = None) -> RunResult:
        """문서를 추출한다. 실행할 때마다 새 ``card_ai_run_id`` 를 만들고 이전 결과는 바꾸지 않는다.

        Raises:
            ExtractionError: 상품·문서·입력 페이지·로컬 PDF가 준비되지 않은 경우.
        """
        if self.repository.select_card_product(card_id) is None:
            raise ExtractionError(f"card_product가 없습니다: {card_id}")
        document = self.repository.select_doc(card_doc_id)
        if document is None:
            raise ExtractionError(f"card_doc이 없습니다: {card_doc_id}")
        chunks = self.repository.select_ai_input_chunks(card_doc_id)
        if not chunks:
            raise ExtractionError(f"AI 입력 페이지가 없습니다: {card_doc_id}")
        omitted = []
        if page_numbers is not None:
            if not page_numbers or not page_numbers.issubset({c['page_no'] for c in chunks}):
                raise ExtractionError("요청 페이지가 AI 입력 대상에 없습니다")
            omitted = [c['page_no'] for c in chunks if c['page_no'] not in page_numbers]
            chunks = [c for c in chunks if c['page_no'] in page_numbers]
        pdf_path = self._local_pdf(document)
        blocked = sorted(set(self.repository.select_blocked_pages(card_doc_id)) | set(omitted))
        run_id = self.repository.insert_run(
            self.llm_client.model_nm, PROMPT_VER, PROMPT_TXT, self._run_param(), card_doc_id,
        )

        try:
            return self._run_pages(run_id, card_id, chunks, pdf_path, blocked)
        except Exception:
            self.repository.finish_run(run_id, "FAILED", "처리 중 오류")     # RUNNING으로 남지 않게 한다
            raise

    def _run_pages(self, run_id: str, card_id: int, chunks: list[dict], pdf_path: Path, blocked: list[int]) -> RunResult:
        """페이지를 차례로 처리하고 모두 성공했을 때만 문서 통합을 저장한다."""
        pages: list[PageResult] = []
        failed = 0
        for chunk in chunks:
            page = self._process_chunk(run_id, card_id, chunk, pdf_path)
            if page is None:
                failed += 1
            else:
                pages.append(page)

        merged = False
        notes = [f"AI 입력 제외 페이지: {blocked}"] if blocked else []
        if failed:
            notes.append("실패한 페이지가 있어 문서 통합을 하지 않음")
        else:
            merged = self._store_merge(pages)
            if not merged:
                notes.append("문서 통합 저장 실패")
        status = "SUCCEEDED" if merged and not blocked else ("PARTIAL" if pages else "FAILED")
        note = " / ".join(notes) or None
        self.repository.finish_run(run_id, status, note)
        extraction_logger.info("EXTRACT %s run=%s pages_ok=%d pages_failed=%d", status, run_id, len(pages), failed)
        return RunResult(run_id, status, len(pages), failed, merged, note)

    def _run_param(self) -> dict:
        """실행 재현에 필요한 값을 ``run_param`` 으로 만든다."""
        schema = json.dumps(PageExtraction.model_json_schema(), sort_keys=True, ensure_ascii=False)
        return {
            "schema_ver": SCHEMA_VER,
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

    def build_input(self, chunk: dict, pdf_path: Path) -> PageInput:
        """페이지 전체 텍스트와 페이지 이미지로 LLM 입력을 만든다. 이미지는 저장하지 않는다."""
        with pymupdf.open(pdf_path) as document:
            image = document[chunk["page_no"] - 1].get_pixmap(dpi=IMAGE_DPI).tobytes("png")
        digest = hashlib.sha256()
        for part in (PROMPT_TXT.encode("utf-8"), chunk["chunk_raw_txt"].encode("utf-8"), image):
            digest.update(part)
        return PageInput(PROMPT_TXT, chunk["page_no"], chunk["chunk_raw_txt"], image, digest.hexdigest())

    def _process_chunk(self, run_id: str, card_id: int, chunk: dict, pdf_path: Path) -> PageResult | None:
        """청크 1건을 호출하고 저장한다. 실패하면 ``None`` 을 반환하고 다음 페이지를 계속 처리한다."""
        page_input = self.build_input(chunk, pdf_path)
        for call_seq in range(1, self.max_attempts + 1):
            extraction = self._call_llm(run_id, chunk, call_seq, page_input)
            if extraction is None:
                continue
            page = PageResult(chunk["page_no"], chunk["card_doc_chunk_id"], chunk["chunk_raw_txt"], extraction)
            try:
                with self.sql_session.transaction():
                    self._store_page(run_id, card_id, chunk, call_seq, page)
            except psycopg.Error as error:
                extraction_logger.error("EXTRACT PAGE SAVE FAILED page=%d: %s", chunk["page_no"], type(error).__name__)
                return None
            return page
        return None

    def _call_llm(self, run_id: str, chunk: dict, call_seq: int, page_input: PageInput) -> PageExtraction | None:
        """LLM을 호출해 호출 이력을 남기고 검증된 응답을 반환한다."""
        started = perf_counter()
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
        """페이지 항목과 근거를 저장한다. 호출자가 트랜잭션을 연다."""
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
        """항목 1건과 근거를 저장한다. 위치를 찾은 첫 근거가 대표 근거다."""
        primary = next((evidence for evidence in check.evidence if evidence.located), None)
        first = primary or (check.evidence[0] if check.evidence else None)
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
        lookup = {
            (page.page_no, stored.seq): stored.stg_id
            for page in pages for stored in (*page.benefits, *page.conditions)
        }
        benefit_ids = {
            benefit.merge.item_key: lookup[(benefit.merge.source_refs[0].page_no, benefit.merge.source_refs[0].stg_item_seq)]
            for benefit in benefits
        }
        try:
            with self.sql_session.transaction():
                for benefit in benefits:
                    self._store_group(benefit.merge, benefit.normalized, benefit.sql_check_cd, None, lookup)
                for condition in conditions:
                    keys = condition.applies_to_item_keys
                    parent = benefit_ids[keys[0]] if len(keys) == 1 else None
                    self._store_group(condition.merge, condition.normalized, condition.sql_check_cd, parent, lookup)
        except psycopg.Error as error:
            extraction_logger.error("EXTRACT MERGE SAVE FAILED: %s", type(error).__name__)
            return False
        return True

    def _store_group(self, merge: MergeInfo, normalized: dict, check_cd: str, parent: str | None, lookup: dict) -> None:
        """대표 행에 정제본을 쓰고 나머지 행은 대표 행을 가리키게 한다."""
        first, *others = merge.source_refs
        canonical = lookup[(first.page_no, first.stg_item_seq)]
        self.repository.update_stg_merge(canonical, normalized, parent, check_cd)
        duplicate_cd = "MERGE_CONFLICT" if merge.conflicts else "MERGED_DUP"
        for ref in others:
            self.repository.update_stg_merge(lookup[(ref.page_no, ref.stg_item_seq)], None, canonical, duplicate_cd)
