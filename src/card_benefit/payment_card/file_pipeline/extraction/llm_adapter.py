"""저장소의 OpenAI/LangChain 관례에 맞춘 지연 로딩 LLM 어댑터."""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any


def _safe_error_details(error: Exception, api_key: str) -> str:
    """Return exception type/metadata only; never render exception messages."""
    chain: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(type(current).__name__)
        current = current.__cause__ or current.__context__

    details = [" <- ".join(chain)]
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, (int, str)):
        details.append(f"status_code={status_code}")
    for field in ("code", "type"):
        value = getattr(error, field, None)
        if isinstance(value, (str, int, float)):
            details.append(f"{field}={value}")

    result = ", ".join(details)
    if api_key:
        result = result.replace(api_key, "[REDACTED]")
    return re.sub(r"sk-[^\s,;]+", "[REDACTED]", result)


def _classify_error(error: Exception, api_key: str) -> tuple[int | None, str | None, bool]:
    status = getattr(error, "status_code", None)
    status = status if isinstance(status, int) else None
    body = getattr(error, "body", None)
    err = body.get("error") if isinstance(body, dict) else None
    code = err.get("code") if isinstance(err, dict) else getattr(error, "code", None)
    code = str(code) if code is not None and isinstance(code, (str, int)) else None
    if code is not None and (not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", code) or (api_key and api_key in code)):
        code = None
    retryable = status in {408, 409, 429} or (status is not None and status >= 500)
    if status is None:
        retryable = isinstance(error, (ConnectionError, TimeoutError)) or "timeout" in type(error).__name__.lower() or "connection" in type(error).__name__.lower()
    return status, code, retryable


def create_llm_call(model: str, api_key_env: str = "OPENAI_API_KEY", *,
                    client_factory: Callable[..., Any] | None = None,
                    temperature: float | None = None) -> Callable[[str], str]:
    """모델 호출 함수를 만든다. 키 값은 환경변수에서만 읽고 표시하지 않는다.

    기본 클라이언트는 저장소의 `ChatOpenAI(model=..., api_key=...)` 관례다.
    client_factory는 테스트에서 가짜 클라이언트를 주입하기 위한 선택 인자다.
    """
    if not model:
        raise ValueError("모델 이름을 지정해야 합니다.")
    # CRLF .env를 source하면 키 끝에 \r이 붙어 HTTP 헤더 오류가 나므로 앞뒤 공백과 개행을 제거한다.
    api_key = (os.environ.get(api_key_env) or "").strip()
    if not api_key:
        raise RuntimeError(f"환경변수 {api_key_env}에 API 키를 설정해야 합니다.")
    if client_factory is None:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as error:
            raise RuntimeError("OpenAI 호출에 필요한 langchain-openai SDK가 설치되어 있지 않습니다.") from None
        client_factory = ChatOpenAI
    try:
        client_args = {"model": model, "api_key": api_key}
        if temperature is not None:
            client_args["temperature"] = temperature
        client = client_factory(**client_args)
    except Exception as error:
        raise RuntimeError(f"LLM 클라이언트 생성 실패 ({type(error).__name__}).") from None

    def llm_call(prompt: str) -> str:
        try:
            response = client.invoke(prompt)
        except Exception as error:
            # SDK 예외에는 요청 정보가 포함될 수 있어 원문 메시지를 전달하지 않는다.
            details = _safe_error_details(error, api_key)
            wrapped = RuntimeError(f"LLM 호출 실패 ({details}).")
            wrapped.status_code, wrapped.error_code, wrapped.retryable = _classify_error(error, api_key)
            raise wrapped from None
        content = getattr(response, "content", response)
        if not isinstance(content, str):
            raise RuntimeError("LLM 응답 본문이 문자열이 아닙니다.")
        return content

    return llm_call
