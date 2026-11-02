"""혜택 검색 텍스트(B안)를 만든다. DB와 API에 접근하지 않는다.

혜택명 + 혜택 유형 + 이용처 또는 서비스 대상 + 핵심 혜택 내용만 쓴다. 카드명, 조건식, 한도, 원본 JSON은 넣지 않는다.
제외 대상은 구조화된 값에서 구분하고, 구분할 수 없는 문구는 만들어 넣지 않고 ``review`` 로 돌려준다.
규칙을 바꾸면 ``SEARCH_TEXT_RULE_VER`` 를 올린다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

SEARCH_TEXT_RULE_VER = "BNFT_SEARCH_TXT_V1"

EXCLUSION_WORDS = re.compile(r"제외|미제공|불가|대상\s*아님|적용되지\s*않")
TOKEN_SPLIT = re.compile(r"[\s,/()·\[\]:]+")
TARGET_LABELS = {"SERVICE": "서비스 대상"}      # 그 외 대상 유형은 이용처로 표시한다.
PAYOUT_WORDS = {"CASHBACK": "캐시백", "DISCOUNT": "할인"}


@dataclass(frozen=True)
class SearchText:
    """검색 텍스트와 사람이 확인할 사항."""

    text: str
    review: list[str] = field(default_factory=list)


def money(value) -> str:
    """금액을 원문 표기에 가깝게 쓴다. 예: 3000은 3천원, 10000은 1만원."""
    amount = int(value)
    if amount >= 10000 and amount % 10000 == 0:
        return f"{amount // 10000}만원"
    if 1000 <= amount < 10000 and amount % 1000 == 0:
        return f"{amount // 1000}천원"
    return f"{amount:,}원"


def number(value) -> str:
    """불필요한 소수점을 뺀다."""
    return f"{float(value):g}"


def rule_value(rule: dict) -> str | None:
    """규칙의 수치를 표기한다. 의미를 확정할 수 없는 조합은 ``None`` 이다."""
    method, value, unit = rule.get("calc_method_cd"), rule.get("value_num"), rule.get("value_unit_cd")
    if method == "FREE_SERVICE":
        return "무상 서비스 제공"
    if value is None:
        return None
    if method == "FIXED_PER_TXN" and unit == "KRW":
        return money(value)
    if method == "PERCENT_OF_TXN" and unit == "PERCENT":
        return f"{number(value)}%"
    if method == "MULTIPLY_EXTERNAL_POINTS" and unit == "MULTIPLIER":
        return f"{number(value)}배"
    if method == "UNITS_PER_AMOUNT" and rule.get("basis_amt") and unit in ("KRW", "UNIMILE"):
        unit_nm = "원" if unit == "KRW" else " UniMile"
        return f"{money(rule['basis_amt'])}당 {number(value)}{unit_nm}"
    return None


def cond_atoms(rule: dict) -> list[dict]:
    """규칙 조건식의 atom 목록. 여러 branch(OR)이면 빈 목록을 돌려 조건을 단정하지 않는다."""
    branches = ((rule.get("cond_expr") or {}).get("branches")) or []
    return branches[0].get("atoms", []) if len(branches) == 1 else []


def min_txn_amount(rule: dict):
    """결제 건당 최소 금액. 전월 실적 조건은 혜택 내용이 아니므로 읽지 않는다."""
    for atom in cond_atoms(rule):
        if (atom.get("cond_type_cd") == "SPEND_REQ" and atom.get("cond_basis_cd") == "TXN_AMT"
                and not atom.get("negate_yn") and atom.get("cond_min_amt") is not None):
            return atom["cond_min_amt"]
    return None


def exclusion_tokens(text: str | None) -> set[str]:
    """제외 문구를 낱말로 나눈다. 부분 문자열이 아니라 낱말로 비교해야 '버스'가 '고속버스'에 걸리지 않는다."""
    return set(TOKEN_SPLIT.split((text or "").casefold())) - {""}


def excluded_tokens(benefit: dict) -> set[str]:
    """혜택 적용 제외 문구의 낱말. 실적 산정 제외(SPEND_EXCL)는 다른 범위라 보지 않는다."""
    expressions = [benefit.get("bnft_cond_expr"), *(rule.get("cond_expr") for rule in benefit.get("rule_list") or [])]
    tokens: set[str] = set()
    for expression in expressions:
        for branch in (expression or {}).get("branches", []):
            for atom in branch.get("atoms", []):
                if atom.get("cond_type_cd") == "BNFT_EXCL":
                    tokens |= exclusion_tokens(atom.get("excl_raw_txt"))
    return tokens


def active_rules(benefit: dict) -> list[dict]:
    return [rule for rule in benefit.get("rule_list") or [] if rule.get("rule_status_cd") != "RETIRED"]


def target_lines(benefit: dict, review: list[str]) -> list[str]:
    """규칙의 대상을 중복 없이 모은다. 제외 문구의 낱말과 정확히 같은 대상은 넣지 않고 검토로 남긴다."""
    excluded = excluded_tokens(benefit)
    groups: dict[str, list[str]] = {}
    for rule in active_rules(benefit):
        for target in rule.get("target_list") or []:
            name = (target.get("target_nm") or "").strip()
            if not name:
                continue
            if name.casefold() in excluded:
                review.append(f"대상과 제외 문구가 겹침: {name}")
                continue
            names = groups.setdefault(TARGET_LABELS.get(target.get("target_type_cd"), "이용처"), [])
            if name not in names:
                names.append(name)
    return [f"{label}: {', '.join(names)}" for label, names in groups.items()]


def rules_content(benefit: dict, review: list[str]) -> str | None:
    """규칙을 자연어로 쓴다. 해석할 수 없는 규칙이 하나라도 있으면 일부만 단정하지 않는다."""
    parts: list[str] = []
    for rule in active_rules(benefit):
        value = rule_value(rule)
        if value is None:
            review.append(f"규칙 해석 불가: {rule.get('rule_key')}")
            return None
        minimum = min_txn_amount(rule)
        prefix = "" if minimum is None else f"{'' if parts else '결제 건당 '}{money(minimum)} 이상 시 "
        part = prefix + value
        if part not in parts:
            parts.append(part)
    if not parts:
        return None
    word = PAYOUT_WORDS.get(benefit.get("bnft_type_cd"))
    return f"{', '.join(parts)} {word}" if word else ", ".join(parts)


def source_text_content(text: str | None, review: list[str]) -> str | None:
    """구조화 규칙이 없을 때의 원문 안내. 제외 문구가 섞여 있으면 어느 쪽인지 판단하지 않는다."""
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return None
    if EXCLUSION_WORDS.search(cleaned):
        review.append("혜택 내용과 제외 문구가 섞여 있어 혜택 내용을 생략함")
        return None
    return cleaned


def build_card_bnft_text(benefit: dict) -> SearchText:
    """``card_bnft`` 행의 검색 텍스트. ``bnft_type_nm`` 은 공통코드 이름이다."""
    review: list[str] = []
    lines = [f"혜택명: {benefit['bnft_nm']}"]
    if benefit.get("bnft_type_nm"):
        lines.append(f"혜택 유형: {benefit['bnft_type_nm']}")
    lines.extend(target_lines(benefit, review))
    content = rules_content(benefit, review)
    if content is None and not active_rules(benefit):
        content = source_text_content(benefit.get("bnft_rule_txt"), review)
    if content:
        lines.append(f"혜택 내용: {content}")
    return SearchText("\n".join(lines), review)


def build_common_bnft_text(benefit: dict) -> SearchText:
    """``card_common_bnft`` 행의 검색 텍스트. 적용 카드명은 넣지 않고 ``card_common_bnft_apply`` 로 관리한다."""
    review: list[str] = []
    pairs = [("공통서비스", benefit.get("common_nm")), ("브랜드", benefit.get("brand_nm")),
             ("서비스 등급", benefit.get("service_grade_nm")), ("혜택명", benefit.get("bnft_nm")),
             ("혜택 유형", benefit.get("bnft_type_nm")), ("서비스 구분", benefit.get("service_type_nm")),
             ("혜택 내용", source_text_content(benefit.get("bnft_rule_txt"), review))]
    return SearchText("\n".join(f"{label}: {value}" for label, value in pairs if value), review)
