"""LLM 호출 모듈. 다른 LLM으로 바꾸려면 이 파일의 두 함수만 수정하면 됩니다."""
import os
from functools import lru_cache
from typing import Iterator

from anthropic import Anthropic

MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")


@lru_cache(maxsize=1)
def _client() -> Anthropic:
    # ANTHROPIC_API_KEY 환경 변수를 사용합니다.
    return Anthropic()


def complete(system: str, user: str, max_tokens: int = 400) -> str:
    """한 번에 결과를 받는 호출 (질의 분석용)."""
    resp = _client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in resp.content if block.type == "text")


def stream(system: str, messages: list[dict], max_tokens: int = 800) -> Iterator[str]:
    """토큰을 실시간으로 내보내는 호출 (답변 생성용)."""
    with _client().messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    ) as s:
        yield from s.text_stream
