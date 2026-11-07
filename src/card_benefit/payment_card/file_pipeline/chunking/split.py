"""쪽 원문 한 장을 어디서 자를지 정한다. PDF를 열지 않는 순수 함수라 테스트하기 쉽다."""

from __future__ import annotations

# 노트북(notebooks/chunking_explore.ipynb)에서 193개 문서 814쪽으로 비교해 정한 값이다.
SPLIT_OVER = 4000   # 쪽 원문이 이 글자 수 이하이면 쪽 전체가 청크 하나다
MIN_CHARS = 400     # 조각이 이 글자 수 이상 쌓이기 전에는 제목을 만나도 자르지 않는다


def split_page(
    text: str, heading_offsets: list[int], over: int = SPLIT_OVER, min_chars: int = MIN_CHARS
) -> list[tuple[int, int]]:
    """쪽 원문을 (시작, 끝) 조각 목록으로 나눈다. 위치는 0부터이고 끝은 포함하지 않는다.

    heading_offsets는 제목 줄이 시작하는 위치 목록이다. 조각을 이어 붙이면 항상 쪽 원문 전체와 같다.
    글자가 없는 쪽은 조각이 없다(traceability와 같다).
    """
    if not text.strip():
        return []
    if len(text.strip()) <= over:
        return [(0, len(text))]

    cuts = []
    start = 0
    for offset in sorted(heading_offsets):
        # 앞 조각이 충분히 쌓였을 때만 제목 바로 앞에서 자른다
        if offset - start >= min_chars:
            cuts.append(offset)
            start = offset
    # 마지막 조각이 너무 짧으면 앞 조각에 붙인다
    if cuts and len(text) - cuts[-1] < min_chars:
        cuts.pop()

    edges = [0, *cuts, len(text)]
    return list(zip(edges[:-1], edges[1:]))
