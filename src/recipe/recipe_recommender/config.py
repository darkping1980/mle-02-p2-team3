"""과제 경로와 환경변수 로딩을 준비하는 공통 설정 도우미.

CLI와 Repository가 단독 실행될 때 저장소 루트와 ``common`` 패키지를 찾도록 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path


# region 1. 프로젝트 경로와 SQL·Cypher 로그 설정값
PACKAGE_DIR = Path(__file__).resolve().parent
TASK_DIR = PACKAGE_DIR.parent
# 개발용 SQL/Cypher 상세 로그 스위치. 레시피 전용 값이 공통 값보다 우선한다.
QUERY_LOG_ENV = "RECIPE_QUERY_LOG"
SHARED_QUERY_LOG_ENV = "DB_QUERY_LOG"
# streamlit_app.py의 DB 진단 스위치도 쓰는 값. 판정 기준은 common.query_log_config와 같다.
QUERY_LOG_ON_VALUES = frozenset({"1", "true", "yes", "on"})
# 소스 설정값: 환경변수를 정하지 않았을 때 로컬 개발(저장소 루트에 .env가 있는 PC)의 Streamlit 앱은 로그를 켠다.
# .env는 .gitignore 대상이라 Streamlit Cloud에는 없으므로 운영에서는 기본 꺼짐이 된다. CLI는 이 기본값을 쓰지 않는다.
LOCAL_DEV_QUERY_LOG_DEFAULT = True
_query_log_active = False          # configure_query_logging()이 이 프로세스에서 로그를 켰는지


# endregion
# region 2. import 경로와 로컬 환경변수 준비
# ``recipe_recommender`` 패키지가 이 모듈을 먼저 읽으므로 ``common`` 은 함수 안에서 가져온다.
def project_root() -> Path:
    """현재 작업 디렉터리와 무관하게 .git 또는 .env가 있는 저장소 루트를 찾는다."""
    from common.query_log_config import project_root as shared_project_root

    return shared_project_root()


def prepare_common_imports() -> None:
    """과제 폴더를 import 경로에 넣어 같은 수준의 ``common``을 찾게 한다.

    pgvector 버전별 ``Vector`` 위치 차이는 ``common.postgres_db_session`` 이 직접 처리한다.
    """
    task_path = str(TASK_DIR)
    if task_path not in sys.path:
        sys.path.insert(0, task_path)


def load_project_environment() -> None:
    """저장소의 .env를 읽되 이미 설정된 프로세스 환경변수는 덮어쓰지 않는다."""
    from common.query_log_config import load_project_environment as load_shared_environment

    load_shared_environment()


# endregion
# region 3. 개발용 쿼리 로그 활성화
# =========================================================
# Streamlit·Repository·DB 세션이 공유하는 로그 스위치
# =========================================================
def is_local_dev() -> bool:
    """저장소 루트에 ``.env`` 가 있으면 로컬 개발 환경으로 본다(``.env`` 는 커밋하지 않으므로 Cloud에는 없다)."""
    from common.query_log_config import is_local_dev as shared_is_local_dev

    return shared_is_local_dev()


def local_dev_query_log_default() -> bool:
    """Streamlit 앱이 쓰는 기본값: 로컬 개발이고 소스 설정값이 켜져 있을 때만 True."""
    return LOCAL_DEV_QUERY_LOG_DEFAULT and is_local_dev()


def query_logging_active() -> bool:
    """이 프로세스에서 ``configure_query_logging()`` 이 상세 로그를 켰는지(로그 검증 모드 여부)."""
    return _query_log_active


def query_log_enabled(default: bool = False) -> bool:
    """개발용 SQL/Cypher 상세 로그를 켤지 판단한다.

    ``RECIPE_QUERY_LOG`` → ``DB_QUERY_LOG`` 순서로 값이 있는 첫 변수를 따른다(``1``·``true``·``yes``·``on`` 만 켜짐,
    ``0`` 등 그 밖의 값은 꺼짐). 둘 다 비어 있으면 ``default`` 를 따른다.

    Args:
        default (bool): 환경변수가 없을 때의 값. Streamlit 앱은 ``local_dev_query_log_default()`` 를 넘긴다.
    """
    from common.query_log_config import query_log_switch

    return query_log_switch((QUERY_LOG_ENV, SHARED_QUERY_LOG_ENV), default)


def configure_query_logging(default: bool = False) -> bool:
    """스위치가 켜져 있으면 공통 SQL/Cypher logger를 INFO 레벨로 터미널(stderr)에 출력한다.

    기존 ``QueryLogger`` 의 출력을 보이게 하는 표준 ``logging`` 설정만 한다(로그 형식·DB 실행은 바꾸지 않음).

    Args:
        default (bool): 환경변수가 없을 때의 값(``query_log_enabled`` 참고). 이미 이 프로세스에서 켰다면
            Repository·세션이 같은 결정을 따르도록 True로 본다.

    Returns:
        bool: 로그를 켰으면 True. 꺼져 있으면 False이며, 앞서 켠 handler가 있을 때만 제거한다.
    """
    global _query_log_active
    from common.query_log_config import attach_query_log_handlers, detach_query_log_handlers

    if not query_log_enabled(default or _query_log_active):
        # Streamlit 재실행 사이에 명시적으로 OFF가 되면 PostgreSQL 로그 검증 조회와 터미널 출력을 함께 멈춘다.
        _query_log_active = False
        detach_query_log_handlers()
        return False
    _query_log_active = True
    attach_query_log_handlers()
    return True

# endregion

