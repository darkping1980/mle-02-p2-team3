"""LLM이 낸 인용문을 청크 원문에서 찾아 쪽 기준 위치로 바꾼다.

원문에는 공백, 제로폭 문자(U+200B~U+200D, U+FEFF), 제어 문자(U+0000~U+001F, 벨 U+0007 포함)가 섞여 있다.
우리카드 글머리표 뒤의 U+0001·U+0003이 그 예다. 인용문은 이것이 빠져 나오기 쉬우므로
찾을 때는 이 문자들을 무시하되, 찾은 위치는 청크 원문의 글자 위치로 되돌린다.
위치는 쪽 원문 기준이다: 청크의 start_pos(1부터)에 청크 안 인덱스를 더한다. 끝 글자를 포함한다.
"""

from __future__ import annotations

from dataclasses import dataclass

IGNORED = set("​‌‍﻿\u0007")


@dataclass(frozen=True)
class Located:
    start_pos: int   # 쪽 원문 기준, 1부터
    end_pos: int     # 쪽 원문 기준, 끝 글자 포함
    matched: str     # 청크 원문에서 잘라낸 글 (인용문과 글자가 다를 수 있다)
    occurrences: int  # 같은 인용문이 청크에 나온 횟수 (2 이상이면 첫 번째를 쓴다)


def _squeeze(text: str) -> tuple[str, list[int]]:
    """무시 문자와 공백을 뺀 글과, 각 글자의 청크 안 인덱스를 돌려준다."""
    chars, index = [], []
    for i, ch in enumerate(text):
        if ch.isspace() or ch in IGNORED or ord(ch) < 0x20:
            continue
        chars.append(ch)
        index.append(i)
    return "".join(chars), index


def locate_quote(chunk_text: str, chunk_start_pos: int, quote: str) -> Located | None:
    """인용문을 청크 원문에서 찾는다. 없으면 None. 빈 인용문은 오류다."""
    key, _ = _squeeze(quote)
    if not key:
        raise ValueError("빈 인용문은 위치를 찾을 수 없습니다.")
    text_key, index = _squeeze(chunk_text)
    first = text_key.find(key)
    if first < 0:
        return None
    occurrences = _count_all(text_key, key)
    first_index = index[first]
    last_index = index[first + len(key) - 1]
    return Located(
        start_pos=chunk_start_pos + first_index,
        end_pos=chunk_start_pos + last_index,
        matched=chunk_text[first_index:last_index + 1],
        occurrences=occurrences,
    )


def _count_all(haystack: str, needle: str) -> int:
    count, pos = 0, haystack.find(needle)
    while pos >= 0:
        count += 1
        pos = haystack.find(needle, pos + 1)
    return count
