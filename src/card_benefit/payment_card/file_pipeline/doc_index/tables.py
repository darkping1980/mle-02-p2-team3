"""PDF 쪽에서 표를 찾아 읽기 쉬운 보조본으로 만든다.

원문(쪽 평문)을 대체하지 않는다. 표 추출은 병합 셀을 빈칸으로 내거나 글자를 쪼개 놓기도 해서,
평문과 맞는지 검사한 표만 usable=True로 표시한다. LLM에는 평문을 기준으로 주고 표는 참고로 붙인다.
"""

from __future__ import annotations

import re

# 표 글자 수가 평문의 이 범위를 벗어나면 글자가 빠졌거나 다른 곳이 섞인 것으로 본다.
CHAR_RATIO_RANGE = (0.8, 1.2)
# 한 글자짜리 셀이 이 비율을 넘으면 글자가 셀마다 쪼개진 표로 본다.
MAX_SINGLE_CHAR_CELL_RATIO = 0.1


def compact_row(row: list) -> list[str]:
    """병합 셀 때문에 생긴 빈 칸을 버리고, 줄바꿈과 겹친 공백을 공백 한 칸으로 만든다."""
    cells = [" ".join((cell or "").split()) for cell in row]
    return [cell for cell in cells if cell]


def _only_letters(text: str) -> str:
    """공백, 쉼표, 문장부호를 뺀 글자만 남긴다. 표와 평문의 글자 수 비교에 쓴다."""
    return re.sub(r"[\s,.·•※*:;|()\[\]'\"‘’“”-]", "", text)


def check_table(rows: list[list[str]], plain_text: str) -> tuple[bool, str]:
    """(쓸 수 있는지, 사유)를 돌려준다. rows는 compact_row를 거친 행 목록이다."""
    cells = [cell for row in rows for cell in row]
    if len(rows) < 2 or len(cells) < 4:
        return False, "표가 너무 작음(행 2개 미만 또는 칸 4개 미만)"
    single = sum(len(cell) == 1 for cell in cells)
    if single / len(cells) > MAX_SINGLE_CHAR_CELL_RATIO:
        return False, "한 글자 셀이 많음(글자가 쪼개졌을 가능성)"
    plain_len = len(_only_letters(plain_text))
    if plain_len == 0:
        return False, "표 영역에 평문이 없음(그림 속 표일 수 있음)"
    ratio = len(_only_letters("".join(cells))) / plain_len
    if not CHAR_RATIO_RANGE[0] <= ratio <= CHAR_RATIO_RANGE[1]:
        return False, f"표와 평문의 글자 수가 다름(비율 {ratio:.2f})"
    return True, ""


def to_markdown(rows: list[list[str]]) -> str:
    """행마다 칸 수가 다를 수 있어서 ' | '로 이어 붙인 줄 목록으로 만든다."""
    return "\n".join(" | ".join(row) for row in rows)


def extract_page_tables(page) -> list[dict]:
    """PyMuPDF 쪽 하나에서 표를 모두 꺼낸다. 순서는 쪽 위에서 아래다."""
    import pymupdf

    result = []
    for number, table in enumerate(page.find_tables().tables, start=1):
        rows = [r for r in (compact_row(raw) for raw in table.extract()) if r]
        plain = page.get_text(clip=pymupdf.Rect(table.bbox))
        usable, reason = check_table(rows, plain)
        result.append({
            "table_no": number,
            "bbox": [round(v, 1) for v in table.bbox],
            "rows": rows,
            "markdown": to_markdown(rows),
            "usable": usable,
            "reason": reason,
        })
    return result
