"""PDF의 글자 크기로 제목 줄을 찾아, 쪽 원문 안의 위치로 바꾼다."""

from __future__ import annotations

from collections import Counter

HEADING_EXTRA_SIZE = 1.5   # 쪽 본문 글자 크기보다 이만큼 이상 크면 제목 후보로 본다


def inside_any(point: tuple[float, float], rects: list[tuple[float, float, float, float]]) -> bool:
    """점이 사각형 목록 중 하나 안에 있는지 본다. 사각형은 (왼쪽, 위, 오른쪽, 아래)다."""
    x, y = point
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in rects)


def body_size(lines: list[tuple[str, float, tuple]]) -> float:
    """글자 수가 가장 많은 글자 크기를 본문 크기로 본다."""
    count = Counter()
    for text, size, _ in lines:
        count[round(size, 1)] += len(text)
    return count.most_common(1)[0][0] if count else 0.0


def page_lines(page) -> list[tuple[str, float, tuple]]:
    """쪽의 줄을 (글, 가장 큰 글자 크기, 줄 사각형) 목록으로 읽는다. 순서는 get_text()와 같다."""
    lines = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if spans:
                text = "".join(s["text"] for s in spans).strip()
                lines.append((text, max(s["size"] for s in spans), tuple(line["bbox"])))
    return lines


def find_heading_offsets(page, page_text: str) -> list[tuple[int, str]]:
    """제목 줄의 (쪽 원문 안 시작 위치, 제목 글) 목록을 돌려준다. 표 안의 제목은 뺀다.

    모든 줄을 쪽 원문에서 앞에서부터 차례로 찾아 위치를 정한다. 같은 글이 앞에 또 있어도 줄 순서대로
    따라가므로 엉뚱한 곳을 가리키지 않는다. 원문에서 못 찾은 줄은 건너뛴다.
    """
    lines = page_lines(page)
    base = body_size(lines)
    tables = [tuple(t.bbox) for t in page.find_tables().tables]
    found = []
    cursor = 0
    for text, size, bbox in lines:
        index = page_text.find(text, cursor)
        if index < 0:
            continue
        cursor = index + len(text)
        is_heading = size >= base + HEADING_EXTRA_SIZE
        if is_heading and not inside_any((bbox[0], bbox[1]), tables):
            found.append((index, text))
    return found
