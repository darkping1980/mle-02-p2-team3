"""과제 경로와 환경변수 로딩을 준비하는 공통 설정 도우미.

CLI와 Repository가 단독 실행될 때 저장소 루트와 ``common`` 패키지를 찾도록 한다.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


# region 1. 프로젝트 경로와 SQL·Cypher 로그 설정값
PACKAGE_DIR = Path(__file__).resolve().parent
TASK_DIR = PACKAGE_DIR.parent
# 개발용 SQL/Cypher 상세 로그 스위치. 값을 명시하면(1/true/yes/on 또는 그 밖의 값) 그 값이 우선한다.
QUERY_LOG_ENV = "RECIPE_QUERY_LOG"
QUERY_LOG_ON_VALUES = frozenset({"1", "true", "yes", "on"})
# 소스 설정값: 환경변수를 정하지 않았을 때 로컬 개발(저장소 루트에 .env가 있는 PC)의 Streamlit 앱은 로그를 켠다.
# .env는 .gitignore 대상이라 Streamlit Cloud에는 없으므로 운영에서는 기본 꺼짐이 된다. CLI는 이 기본값을 쓰지 않는다.
LOCAL_DEV_QUERY_LOG_DEFAULT = True
_query_log_active = False          # configure_query_logging()이 이 프로세스에서 로그를 켰는지
# common 세션이 쓰는 logger 이름(PostgresDbSession / Neo4jDbSession).
QUERY_LOGGER_NAMES = ("car_search_rag.sql", "car_search_rag.neo4j")
QUERY_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


# endregion
# region 2. import 경로와 로컬 환경변수 준비
def project_root() -> Path:
    """현재 작업 디렉터리와 무관하게 .git 또는 .env가 있는 저장소 루트를 찾는다."""
    for candidate in TASK_DIR.parents:
        if (candidate / ".git").exists() or (candidate / ".env").is_file():
            return candidate
    return TASK_DIR


def prepare_common_imports() -> None:
    """과제 폴더를 import 경로에 넣어 같은 수준의 ``common``을 찾게 한다.

    pgvector 버전별 ``Vector`` 위치 차이는 ``common.postgres_db_session`` 이 직접 처리한다.
    """
    task_path = str(TASK_DIR)
    if task_path not in sys.path:
        sys.path.insert(0, task_path)


def load_project_environment() -> None:
    """저장소의 .env를 읽되 이미 설정된 프로세스 환경변수는 덮어쓰지 않는다."""
    from dotenv import load_dotenv

    env_file = project_root() / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=False)


# endregion
# region 3. 개발용 쿼리 로그 활성화
# =========================================================
# Streamlit·Repository·DB 세션이 공유하는 로그 스위치
# =========================================================
def is_local_dev() -> bool:
    """저장소 루트에 ``.env`` 가 있으면 로컬 개발 환경으로 본다(``.env`` 는 커밋하지 않으므로 Cloud에는 없다)."""
    return (project_root() / ".env").is_file()


def local_dev_query_log_default() -> bool:
    """Streamlit 앱이 쓰는 기본값: 로컬 개발이고 소스 설정값이 켜져 있을 때만 True."""
    return LOCAL_DEV_QUERY_LOG_DEFAULT and is_local_dev()


def query_logging_active() -> bool:
    """이 프로세스에서 ``configure_query_logging()`` 이 상세 로그를 켰는지(로그 검증 모드 여부)."""
    return _query_log_active


def query_log_enabled(default: bool = False) -> bool:
    """개발용 SQL/Cypher 상세 로그를 켤지 판단한다.

    환경변수 ``RECIPE_QUERY_LOG`` 에 값이 있으면 그 값이 우선한다(``1``·``true``·``yes``·``on`` 만 켜짐,
    ``0`` 등 그 밖의 값은 꺼짐). 비어 있으면 ``default`` 를 따른다.

    Args:
        default (bool): 환경변수가 없을 때의 값. Streamlit 앱은 ``local_dev_query_log_default()`` 를 넘긴다.
    """
    raw = os.getenv(QUERY_LOG_ENV, "").strip().lower()
    return raw in QUERY_LOG_ON_VALUES if raw else default


def configure_query_logging(default: bool = False) -> bool:
    """``RECIPE_QUERY_LOG`` 가 켜져 있으면 공통 SQL/Cypher logger를 INFO 레벨로 터미널(stderr)에 출력한다.

    기존 ``QueryLogger`` 의 출력을 보이게 하는 표준 ``logging`` 설정만 한다(로그 형식·DB 실행은 바꾸지 않음).
    Streamlit은 위젯 조작마다 스크립트를 다시 실행하므로 handler는 logger마다 한 번만 붙인다.
    상위 logger로 전파하지 않아 같은 줄이 두 번 찍히지 않게 한다.

    Args:
        default (bool): 환경변수가 없을 때의 값(``query_log_enabled`` 참고). 이미 이 프로세스에서 켰다면
            Repository·세션이 같은 결정을 따르도록 True로 본다.

    Returns:
        bool: 로그를 켰으면 True, 꺼져 있으면 아무것도 바꾸지 않고 False.
    """
    global _query_log_active
    if not query_log_enabled(default or _query_log_active):
        # Streamlit 재실행 사이에 명시적으로 OFF가 되면 PostgreSQL 로그 검증 조회도 멈춘다.
        _query_log_active = False
        return False
    _query_log_active = True
    for name in QUERY_LOGGER_NAMES:
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        if not any(getattr(handler, "recipe_query_log", False) for handler in logger.handlers):
            handler = logging.StreamHandler(sys.stderr)
            handler.setFormatter(logging.Formatter(QUERY_LOG_FORMAT))
            handler.recipe_query_log = True          # 이 함수가 붙인 handler 표시(중복 방지)
            logger.addHandler(handler)
        logger.propagate = False
    return True

# endregion

