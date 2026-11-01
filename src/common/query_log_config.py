"""프로젝트가 함께 쓰는 ``.env`` 로딩과 SQL/Cypher 터미널 로그 설정.

어떤 값을 켤지는 각 프로젝트가 정하고, 이 모듈은 환경변수 판정과 표준 ``logging`` 설정만 맡는다.
로그 형식과 DB 실행은 바꾸지 않는다.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

QUERY_LOG_ON_VALUES = frozenset({"1", "true", "yes", "on"})
# common 세션이 쓰는 logger 이름(PostgresDbSession / Neo4jDbSession).
QUERY_LOGGER_NAMES = ("car_search_rag.sql", "car_search_rag.neo4j")
QUERY_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_HANDLER_MARK = "common_query_log"          # 이 모듈이 붙인 handler 표시


# region 1. 저장소 환경변수
def project_root() -> Path:
    """현재 작업 디렉터리와 무관하게 .git 또는 .env가 있는 저장소 루트를 찾는다."""
    package_dir = Path(__file__).resolve().parent
    for candidate in package_dir.parents:
        if (candidate / ".git").exists() or (candidate / ".env").is_file():
            return candidate
    return package_dir.parent


def load_project_environment() -> None:
    """저장소의 .env를 읽되 이미 설정된 프로세스 환경변수는 덮어쓰지 않는다."""
    from dotenv import load_dotenv

    env_file = project_root() / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=False)


def is_local_dev() -> bool:
    """저장소 루트에 ``.env`` 가 있으면 로컬 개발 환경으로 본다(``.env`` 는 커밋하지 않으므로 Cloud에는 없다)."""
    return (project_root() / ".env").is_file()


# endregion
# region 2. 쿼리 로그 스위치와 handler
def query_log_switch(env_names: tuple[str, ...], default: bool = False) -> bool:
    """환경변수를 순서대로 보고 처음 값이 있는 변수로 판정한다. 모두 비어 있으면 ``default``.

    Args:
        env_names (tuple[str, ...]): 우선순위가 높은 순서의 환경변수 이름.
        default (bool): 모든 환경변수가 비어 있을 때의 값.

    Returns:
        bool: ``1``·``true``·``yes``·``on`` 이면 True, 그 밖의 값이면 False.
    """
    for name in env_names:
        raw = os.getenv(name, "").strip().lower()
        if raw:
            return raw in QUERY_LOG_ON_VALUES
    return default


def attach_query_log_handlers() -> None:
    """공통 SQL/Cypher logger를 INFO 레벨로 터미널(stderr)에 출력한다.

    Streamlit은 위젯 조작마다 스크립트를 다시 실행하므로 handler는 logger마다 한 번만 붙인다.
    상위 logger로 전파하지 않아 같은 줄이 두 번 찍히지 않게 한다.
    """
    for name in QUERY_LOGGER_NAMES:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        if not any(getattr(handler, _HANDLER_MARK, False) for handler in logger.handlers):
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter(QUERY_LOG_FORMAT))
            setattr(handler, _HANDLER_MARK, True)
            logger.addHandler(handler)
        logger.propagate = False


def detach_query_log_handlers() -> None:
    """``attach_query_log_handlers`` 가 켠 logger만 표준 기본값으로 되돌린다.

    붙인 적이 없는 최초 실행에서는 아무것도 바꾸지 않아, CLI가 직접 정한 logger 레벨을 건드리지 않는다.
    """
    for name in QUERY_LOGGER_NAMES:
        logger = logging.getLogger(name)
        handlers = [handler for handler in logger.handlers if getattr(handler, _HANDLER_MARK, False)]
        if not handlers:
            continue
        for handler in handlers:
            logger.removeHandler(handler)
        logger.setLevel(logging.NOTSET)
        logger.propagate = True

# endregion
