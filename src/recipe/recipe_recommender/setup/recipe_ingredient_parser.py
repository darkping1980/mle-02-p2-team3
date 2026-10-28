"""``RCP_PARTS_DTLS`` 재료 원문을 staging 행 후보로 나누는 보수적 파서.

이 모듈은 DB에 접근하지 않는 순수 함수만 제공한다. 결과는 언제나 *후보* 이며
표준 식재료로 확정하지 않는다. 확실하지 않은 항목은 원문을 그대로 남기고
``parse_status`` 를 PARTIAL / AMBIGUOUS / FAILED 로 표시해 검토 대상으로 둔다.

parse_status 의미:
    OK        : 재료명과 수량(또는 '적당량' 같은 분량 표현)을 규칙대로 분리했다.
    PARTIAL   : 재료명만 분리했고 수량·단위가 없거나 단위 없이 숫자만 있다.
    AMBIGUOUS : 분리는 했지만 구획명이 재료명에 섞였거나 여러 분량이 있어 사람이 봐야 한다.
    FAILED    : 문장형·복합 서술이라 재료명을 신뢰성 있게 분리하지 못했다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# region 1. 원문 패턴과 허용 단위
PARSER_VERSION = "rcp-ingr-parser-v1"

# 줄 앞에 붙는 장식 기호. 구획 머리글 판정 전에 제거한다.
_BULLET_PATTERN = re.compile(r"^[●■□◆◇▶▷•·\-*]+\s*")
# "주재료 : ...", "- 소스 : ...", "●누룽지: ..." 형태의 구획 머리글.
_COLON_HEADER_PATTERN = re.compile(r"^(?P<header>[^,()\[\]:：>\d]{1,15}?)\s*[:：>]\s*(?P<rest>.*)$")
# 한 줄 중간의 "[바질 페스토]" 같은 구획 표기. 앞뒤를 별도 조각으로 나눠 구획을 바꾼다.
_INLINE_SECTION_PATTERN = re.compile(r"\[\s*([^\[\]]{1,20}?)\s*\]")
_HTML_BREAK_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)
# "(반죽재료) ...", "[ 2인분 ] ..." 형태의 괄호 머리글.
_BRACKET_HEADER_PATTERN = re.compile(r"^[(\[]\s*(?P<header>[^()\[\]]{1,15}?)\s*[)\]]\s*(?P<rest>.*)$")
_SERVING_PATTERN = re.compile(r"^\d+(?:\.\d+)?\s*인분$")
# 줄 맨 앞에 공백으로 이어지는 대표 구획어: "재료 현미(50g)", "양념 맛술(10g)".
_SECTION_WORDS = ("주재료", "부재료", "재료", "양념장", "양념", "소스", "육수", "고명", "드레싱", "토핑", "속재료", "반죽")
_LEADING_SECTION_PATTERN = re.compile(r"^(?P<header>" + "|".join(_SECTION_WORDS) + r")\s+(?P<rest>\S.*)$")
# 재료명 앞 단어가 구획처럼 보이는 경우("토마토소스 토마토", "달래무침 달래")를 표시한다.
_SECTION_LIKE_SUFFIX = ("소스", "양념", "양념장", "무침", "육수", "드레싱", "재료", "반죽")

_FRACTION_CHARS = {"½": "0.5", "⅓": "0.333", "⅔": "0.667", "¼": "0.25", "¾": "0.75", "⅛": "0.125"}
_NUMBER = r"(?:\d+(?:\.\d+)?\s*/\s*\d+|\d*[½⅓⅔¼¾⅛]|\d+(?:\.\d+)?)"
# 단위는 실제 원문에서 확인한 목록만 인정한다(임의 글자를 단위로 삼으면 재료명을 삼킨다). 긴 것부터 비교.
_UNITS = (
    "작은술", "큰술", "숟가락", "스푼", "꼬집", "방울", "송이", "봉지", "포기", "조각", "토막", "뿌리", "줄기", "공기",
    "덩이", "묶음", "국자", "마리", "Tbsp", "tsp", "kg", "mg", "ml", "mL", "cc", "cm", "Ts", "ts",
    "개", "컵", "모", "장", "줄", "쪽", "대", "줌", "캔", "봉", "톨", "알", "근", "통", "단", "잎", "팩", "병", "판",
    "g", "L", "l", "T", "t", "㎖", "㎗", "ℓ", "㎏", "㎎", "㎝",
)
_UNIT = "(?:" + "|".join(re.escape(unit) for unit in sorted(_UNITS, key=len, reverse=True)) + ")"
_AMOUNT_PATTERN = re.compile(r"^(?P<qty>" + _NUMBER + r")\s*(?P<unit>" + _UNIT + r")?$")
# 이름 뒤에 분량이 붙는 형태: "연두부 75g(3/4모)", "쌀 70g", "타임다진것 0.5", "한돈(사태) 30g".
_NAME_AMOUNT_PATTERN = re.compile(
    r"^(?P<name>[^\d()]+?)\s*(?:\((?P<desc>[^()\d]+)\)\s*)?(?P<amount>" + _NUMBER + r"\s*(?:" + _UNIT + r")?)\s*(?:\((?P<alt>[^()]*)\))?$"
)
# 이름 뒤 괄호 안에 분량이 있는 형태: "현미(50g)", "참치(캔, 30g)".
_NAME_PAREN_PATTERN = re.compile(r"^(?P<name>[^()]+?)\s*\((?P<inner>[^()]*)\)$")
# 수량 대신 쓰는 분량 표현: "소금적당량", "후추 약간".
_VAGUE_AMOUNTS = ("적당량", "적량", "약간", "조금", "소량")
_VAGUE_PATTERN = re.compile(r"^(?P<name>.+?)\s*(?P<unit>" + "|".join(_VAGUE_AMOUNTS) + r")$")
_METRIC_UNITS = {"g", "kg", "mg", "ml", "mL", "L", "l", "cc", "㎖", "ℓ", "㎏", "㎎"}
_SECTION_MARK_CHARS = re.compile(r"[\[\]<>:：]")
_PLAIN_NAME_PATTERN = re.compile(r"^[가-힣A-Za-z][가-힣A-Za-z\s]{0,19}$")
_SENTENCE_HINT = re.compile(r"(다\.|요\.|한다|넣고|하여|만든다)")


# endregion
# region 2. 파싱 후보 DTO와 항목별 해석
# =========================================================
# 불확실한 항목은 원문과 검토 상태를 함께 보존
# =========================================================
@dataclass(frozen=True)
class ParsedIngredient:
    """원문 재료 한 항목의 파싱 후보; 등록 Service가 staging 행에 사용한다.

    ``@dataclass(frozen=True)``는 필드 재할당을 막는다. 검토 전 후보이므로
    ``parsed_nm``이나 분량이 ``None``이어도 원문과 상태를 함께 보존한다.
    """

    line_no: int  # 원문에서 발견한 순번; 1부터 시작한다.
    raw_txt: str  # 손실 없이 보존할 원문 재료 조각.
    parsed_nm: str | None  # 분리한 후보 재료명; 실패 시 None.
    qty: Decimal | None  # 수량 후보; 해석 불가 또는 미기재 시 None.
    unit_nm: str | None  # 수량 단위 또는 분량 표현; 없으면 None.
    section_txt: str | None  # 주재료·양념 등 원문 구획; 없으면 None.
    parse_status: str  # OK, PARTIAL, AMBIGUOUS, FAILED 중 검토 상태.
    note: str  # 사람이 검토할 때 참고할 불확실성 설명; 없으면 빈 문자열.

    @property
    def review_note(self) -> str:
        """staging ``rcp_ingr_review_note`` 에 저장할 문자열. 항상 ``parse=상태`` 로 시작한다."""
        return f"parse={self.parse_status}" + (f"; {self.note}" if self.note else "")


def parse_quantity(text: str) -> Decimal | None:
    """'75', '0.5', '1/2', '½', '1½' 를 Decimal(소수 3자리)로 바꾼다. 해석할 수 없으면 None."""
    value = text.replace(" ", "")
    if not value:
        return None
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            if Decimal(denominator) == 0:
                return None
            result = Decimal(numerator) / Decimal(denominator)
        elif value[-1] in _FRACTION_CHARS:
            whole = Decimal(value[:-1]) if value[:-1] else Decimal(0)
            result = whole + Decimal(_FRACTION_CHARS[value[-1]])
        else:
            result = Decimal(value)
    except ArithmeticError:
        return None
    return result.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def split_items(line: str) -> list[str]:
    """괄호 밖의 쉼표로만 나눈다. '참치(캔, 30g)' 안의 쉼표는 유지한다."""
    items, depth, current = [], 0, []
    for char in line:
        if char in "([":
            depth += 1
        elif char in ")]":
            depth = max(depth - 1, 0)
        if char in ",，" and depth == 0:
            items.append("".join(current))
            current = []
            continue
        current.append(char)
    items.append("".join(current))
    return [item.strip() for item in items if item.strip()]


def _split_header(line: str, recipe_name: str) -> tuple[str | None, str | None, str]:
    """줄 앞의 구획 머리글을 분리한다. Returns ``(section, serving_note, rest)``."""
    text = _BULLET_PATTERN.sub("", line).strip()
    compact = re.sub(r"\s+", "", text)
    if compact and compact == re.sub(r"\s+", "", recipe_name):
        return text, None, ""                       # 첫 줄의 요리명 표기(예: 새우두부계란찜)
    if text in _SECTION_WORDS or (
        not re.search(r"[\d,()]", text) and any(text.endswith(word) for word in _SECTION_WORDS) and len(text) <= 10
    ):
        return text, None, ""                       # 단독 구획 줄(예: 고명, 양념장)
    match = _BRACKET_HEADER_PATTERN.match(text)
    if match:
        header = match.group("header").strip()
        if _SERVING_PATTERN.match(header):
            return None, header, match.group("rest")
        return header, None, match.group("rest")
    match = _COLON_HEADER_PATTERN.match(text)
    if match:
        return match.group("header").strip(), None, match.group("rest")
    match = _LEADING_SECTION_PATTERN.match(text)
    if match:
        return match.group("header"), None, match.group("rest")
    return None, None, text


def _choose_amount(parts: list[str]) -> tuple[Decimal | None, str | None, list[str], int]:
    """분량 후보 문자열 목록에서 대표 분량을 고른다. 미터법 단위를 우선한다.

    Returns: ``(qty, unit, 나머지 설명, 분량으로 해석된 개수)``.
    """
    amounts, others = [], []
    for part in parts:
        for piece in re.split(r"\s*=\s*", part.strip()):
            match = _AMOUNT_PATTERN.match(piece.strip())
            if match:
                amounts.append((parse_quantity(match.group("qty")), match.group("unit"), piece.strip()))
            elif piece.strip():
                others.append(piece.strip())
    if not amounts:
        return None, None, others, 0
    chosen = next((amount for amount in amounts if amount[1] in _METRIC_UNITS), amounts[0])
    others.extend(amount[2] for amount in amounts if amount is not chosen)
    return chosen[0], chosen[1], others, len(amounts)


def _status_for_name(name: str, base_status: str, notes: list[str]) -> str:
    """후보 재료명의 불확실성을 확인해 검토 상태와 사유를 조정한다."""
    if _SECTION_MARK_CHARS.search(name):
        notes.append("구획 표기 문자 포함")
        return "AMBIGUOUS"
    first_word = name.split()[0] if " " in name else ""
    if first_word and any(first_word.endswith(suffix) for suffix in _SECTION_LIKE_SUFFIX):
        notes.append(f"구획명 혼재 가능: '{first_word}'")
        return "AMBIGUOUS"
    return base_status


def parse_item(item: str) -> tuple[str | None, Decimal | None, str | None, str, list[str]]:
    """재료 항목 하나를 ``(name, qty, unit, status, notes)`` 로 분리한다."""
    text = item.strip().strip(",").strip()
    notes: list[str] = []
    if len(text) > 40 or _SENTENCE_HINT.search(text):
        return None, None, None, "FAILED", ["문장형 원문"]

    match = _NAME_AMOUNT_PATTERN.match(text)
    if match:
        name = match.group("name").strip()
        qty, unit, others, _ = _choose_amount([match.group("amount")])
        if match.group("desc"):
            notes.append(f"괄호설명={match.group('desc').strip()}")
        if match.group("alt"):
            notes.append(f"보조분량={match.group('alt').strip()}")
        if others:
            notes.append("기타=" + ", ".join(others))
        status = "OK" if unit else "PARTIAL"
        if not unit:
            notes.append("단위 없음")
        return name, qty, unit, _status_for_name(name, status, notes), notes

    match = _NAME_PAREN_PATTERN.match(text)
    if match:
        name = match.group("name").strip()
        inner_parts = [part for part in split_items(match.group("inner"))]
        qty, unit, others, amount_count = _choose_amount(inner_parts)
        if others:
            notes.append("괄호설명=" + ", ".join(others))
        if amount_count == 0:
            vague = next((v for v in _VAGUE_AMOUNTS if any(v in part for part in inner_parts)), None)
            if vague:
                return name, None, vague, _status_for_name(name, "OK", notes), notes
            notes.append("수량 없음")
            return name, None, None, _status_for_name(name, "PARTIAL", notes), notes
        status = "OK" if unit else "PARTIAL"
        if not unit:
            notes.append("단위 없음")
        if amount_count > 1:
            notes.append("분량 여러 개")
        return name, qty, unit, _status_for_name(name, status, notes), notes

    match = _VAGUE_PATTERN.match(text)
    if match and not re.search(r"[\d()]", text):
        name = match.group("name").strip()
        return name, None, match.group("unit"), _status_for_name(name, "OK", notes), notes

    if _PLAIN_NAME_PATTERN.match(text):
        notes.append("수량 없음")
        return text, None, None, _status_for_name(text, "PARTIAL", notes), notes

    return None, None, None, "FAILED", ["규칙 불일치"]


# endregion
# region 3. 구획 분리와 staging 후보 생성
# =========================================================
# RCP_PARTS_DTLS 전체 텍스트 → ParsedIngredient 목록
# =========================================================
def _split_inline_sections(text: str) -> list[tuple[str | None, str | None]]:
    """줄 나머지를 ``(바뀐 구획 또는 None, 재료 항목 또는 None)`` 목록으로 나눈다.

    "소금적당량 [바질 페스토] 잣 10g" → [(None, "소금적당량"), ("바질 페스토", None), (None, "잣 10g")].
    쉼표 뒤에 이어진 "- 양념장 : 된장 2g" 같은 구획 머리글도 분리한다.
    """
    pieces: list[tuple[str | None, str | None]] = []
    position = 0
    for match in _INLINE_SECTION_PATTERN.finditer(text):
        pieces.extend(_split_item_headers(text[position:match.start()]))
        pieces.append((match.group(1).strip(), None))
        position = match.end()
    pieces.extend(_split_item_headers(text[position:]))
    return pieces


def _split_item_headers(text: str) -> list[tuple[str | None, str | None]]:
    """한 재료 조각 안의 구획 머리글을 분리한다."""
    pieces: list[tuple[str | None, str | None]] = []
    for item in split_items(text):
        match = _COLON_HEADER_PATTERN.match(_BULLET_PATTERN.sub("", item).strip())
        if match and match.group("rest").strip():
            pieces.append((match.group("header").strip(), None))
            pieces.append((None, match.group("rest").strip()))
        else:
            pieces.append((None, item))
    return pieces


def parse_ingredient_text(parts_text: str | None, recipe_name: str = "") -> list[ParsedIngredient]:
    """재료 원문 전체를 등장 순서대로 ``ParsedIngredient`` 목록으로 만든다.

    구획 머리글은 행으로 만들지 않고 뒤따르는 항목의 ``section_txt`` 로 남긴다.
    같은 재료가 여러 번 나오면 각각 별도 항목으로 보존한다.
    """
    if not parts_text or not parts_text.strip():
        return []
    results: list[ParsedIngredient] = []
    section: str | None = None
    for raw_line in _HTML_BREAK_PATTERN.sub("\n", parts_text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header, serving_note, rest = _split_header(line, recipe_name)
        if header is not None:
            section = header
        for segment_section, item in _split_inline_sections(rest):
            if segment_section is not None:
                section = segment_section
            if item is None:
                continue
            name, qty, unit, status, notes = parse_item(item)
            if serving_note:
                notes.append(f"분량기준={serving_note}")
            results.append(
                ParsedIngredient(
                    line_no=len(results) + 1,
                    raw_txt=item,
                    parsed_nm=name,
                    qty=qty,
                    unit_nm=unit,
                    section_txt=section,
                    parse_status=status,
                    note="; ".join(notes),
                )
            )
    return results


class RecipeIngredientParser:
    """재료 원문 파서. DB와 무관한 순수 업무 규칙이며 ``RecipeRegisterService`` 가 주입받아 사용한다.

    Example:
        .. code-block:: python

            parser = RecipeIngredientParser()
            items = parser.parse("연두부 75g(3/4모), 칵테일새우 20g", "새우 두부 계란찜")
    """

    version: str = PARSER_VERSION   # staging rcp_ingr_parser_version에 기록할 파서 버전

    def parse(self, parts_text: str | None, recipe_name: str = "") -> list[ParsedIngredient]:
        """``parse_ingredient_text()`` 와 같다. 원문 등장 순서대로 후보 목록을 돌려준다."""
        return parse_ingredient_text(parts_text, recipe_name)

# endregion
