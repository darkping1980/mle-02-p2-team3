"""페이지 원문을 의미 단위 청크로 나눈다(BLOCK_V1). DB와 PDF에 접근하지 않는 순수 함수다.

원칙
- 청크는 ``card_doc_page`` 원문의 연속 구간이다. 청크를 이어 붙이면 페이지 원문과 정확히 같다.
  근거 위치는 항상 원문 기준이며, Markdown 등 재배열한 문자열의 위치를 쓰지 않는다.
- ``·`` 로 시작하는 줄이 혜택 항목 1건이다. 들여쓴 다음 줄은 같은 항목의 이어지는 줄로 본다.
  항목을 가운데에서 자르지 않는다.
- ``*`` ``※`` ``•`` 로 시작하는 줄과 그 이어지는 줄은 유의사항(NOTICE)이다. 같은 페이지의 다른 청크를
  추출할 때 적용 대상·제공 기간의 근거로 함께 보낸다.
- 항목 줄이 없는 페이지(표 위주 등)는 나누지 않고 페이지 전체를 청크 1건으로 둔다.
"""
from __future__ import annotations

from dataclasses import dataclass

SPLIT_RULE_BLOCK = "BLOCK_V1"
MAX_ITEMS = 8                     # BODY 청크 1건의 최대 혜택 항목 수. 출력 토큰 한도 안에 들도록 정한다.
ITEM_MARKS = ("·",)
NOTICE_MARKS = ("*", "※", "•")
LABEL_MAX_CHARS = 12              # 숫자 없는 짧은 줄은 구역 이름(Hotel, 서비스 등)으로 본다


@dataclass(frozen=True)
class Block:
    """청크 1건. ``start_pos`` 와 ``end_pos`` 는 페이지 원문 기준 1부터이고 종료 문자를 포함한다."""

    page_no: int
    start_pos: int
    end_pos: int
    text: str
    chunk_type_cd: str            # CHUNK_TYPE 공통코드: BODY, NOTICE
    item_cnt: int


def _kind(line: str, has_unit: bool) -> str:
    stripped = line.strip()
    if not stripped:
        return "blank"
    if line[0].isspace() and has_unit:
        return "cont"
    if stripped.startswith(ITEM_MARKS):
        return "item"
    if stripped.startswith(NOTICE_MARKS):
        return "notice"
    compacted = "".join(stripped.split())
    if len(compacted) <= LABEL_MAX_CHARS and not any(char.isdigit() for char in compacted):
        return "label"
    return "text"


def split_blocks(page_no: int, text: str, max_items: int = MAX_ITEMS) -> list[Block]:
    """페이지 원문을 BODY·NOTICE 청크로 나눈다. 항목 줄이 없으면 페이지 전체 1건이다."""
    if max_items < 1:
        raise ValueError("max_items는 1 이상이어야 합니다")
    lines = text.splitlines(keepends=True)
    units: list[list] = []                 # [kind, start, end]  (0부터, end 미포함)
    offset = 0
    for line in lines:
        kind = _kind(line, bool(units))
        end = offset + len(line)
        if kind in ("cont", "blank") and units:
            units[-1][2] = end
        else:
            units.append([kind if kind not in ("cont", "blank") else "text", offset, end])
        offset = end
    if not any(kind == "item" for kind, _, _ in units):
        return [Block(page_no, 1, len(text), text, "BODY", 0)] if text.strip() else []

    chunks: list[dict] = []
    for kind, start, end in units:
        current = chunks[-1] if chunks else None
        wanted = "NOTICE" if kind == "notice" else "BODY" if kind == "item" else None
        new = current is None or (wanted is not None and (
            wanted != current["type"] or (wanted == "BODY" and current["items"] >= max_items)))
        if new:
            chunks.append({"type": wanted or "BODY", "start": start, "end": end, "items": int(kind == "item")})
        else:
            current["end"] = end
            current["items"] += int(kind == "item")
    return [Block(page_no, c["start"] + 1, c["end"], text[c["start"]:c["end"]], c["type"], c["items"])
            for c in chunks if c["end"] > c["start"]]
