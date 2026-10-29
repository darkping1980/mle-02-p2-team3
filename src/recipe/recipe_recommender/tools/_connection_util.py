"""단독 연결 점검 도구가 공유하는 경로 준비와 오류 메시지 정리 함수."""

from __future__ import annotations

import re

from recipe_recommender.config import load_project_environment, prepare_common_imports


def initialize() -> None:
    """단독 실행 도구가 패키지 경로와 환경변수를 읽도록 준비한다."""
    prepare_common_imports()
    load_project_environment()


def safe_error(error: Exception) -> str:
    """오류의 원인은 유지하면서 설정된 자격 증명과 URL 사용자 정보를 가린다.

    Args:
        error (Exception): 화면이나 CLI에 표시할 연결 오류.

    Returns:
        str: 비밀 값이 치환된 오류 메시지.
    """
    import os

    message = str(error)
    for name in ("DB_URL", "NEO4J_PASSWORD", "SUPABASE_SECRET_KEY"):
        value = os.getenv(name)
        if value:
            message = message.replace(value, "[REDACTED]")
    message = re.sub(r"(\w+://)[^/@\s]+@", r"\1[REDACTED]@", message)
    return message or "No additional error details"

