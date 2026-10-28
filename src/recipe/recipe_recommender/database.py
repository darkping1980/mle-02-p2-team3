"""레시피 프로젝트의 PostgreSQL 연결과 SQL mapper 경로를 구성한다.

등록·조회 진입점이 이 모듈의 세션 팩토리를 사용한다.
"""

from __future__ import annotations

import os
import atexit
import shutil
import tempfile
from pathlib import Path
from threading import Lock
from contextlib import contextmanager
from typing import Iterator

from recipe_recommender.config import PACKAGE_DIR, configure_query_logging, load_project_environment, prepare_common_imports, prepare_imports
from recipe_recommender.sql_schema import DEFAULT_SCHEMA, configured_schema, render_schema_sql

# region 1. 연결 관리자 생명주기와 Pooler 구분
# =========================================================
# 프로세스에서 공유하는 DatabaseManager와 종료 정리
# =========================================================
_MANAGER = None
_MANAGER_LOCK = Lock()
_RENDERED_MAPPER_DIRS: list[str] = []


def classify_pool_mode(host: str | None, port: int | None) -> str:
    """호스트·포트를 노출하지 않고 Supabase 풀러 유형을 분류한다.

    Returns:
        str: ``transaction_pooler``, ``session_pooler``, ``direct_or_other`` 중 하나.
    """
    is_pooler = bool(host and host.lower().endswith(".pooler.supabase.com"))
    if is_pooler and port == 6543:
        return "transaction_pooler"
    if is_pooler and port == 5432:
        return "session_pooler"
    return "direct_or_other"


def get_pool_mode() -> str:
    """환경변수 ``DB_URL``에서 첫 호스트·포트를 읽어 연결 유형을 반환한다."""
    load_project_environment()
    from psycopg.conninfo import conninfo_to_dict

    conninfo = conninfo_to_dict(os.getenv("DB_URL", ""))
    host = (conninfo.get("host") or "").split(",", 1)[0]
    try:
        port = int((conninfo.get("port") or "").split(",", 1)[0])
    except ValueError:
        port = None
    return classify_pool_mode(host, port)


def _get_manager():
    """호출 프로세스에서 재사용할 PostgreSQL 연결 관리자를 준비한다."""
    global _MANAGER
    if _MANAGER is None:
        with _MANAGER_LOCK:
            if _MANAGER is None:
                prepare_imports()
                from common.database_manager import DatabaseManager

                _MANAGER = DatabaseManager()
    return _MANAGER


@atexit.register
def _close_manager() -> None:
    """프로세스 종료 시 캐시된 연결 관리자를 닫는다."""
    if _MANAGER is not None:
        _MANAGER.close()
    for folder in _RENDERED_MAPPER_DIRS:
        shutil.rmtree(folder, ignore_errors=True)


# endregion
# region 2. recipe.sql Mapper 경로와 세션 생성
# =========================================================
# 프로젝트 설정 → common.PostgresDbSession 연결
# =========================================================
def _mapper_root_for(schema: str) -> Path:
    """기본 스키마면 패키지 폴더, 아니면 ``recipe.`` 한정자를 바꾼 ``recipe.sql`` 사본 폴더."""
    if schema == DEFAULT_SCHEMA:
        return PACKAGE_DIR
    folder = tempfile.mkdtemp(prefix=f"recipe_mapper_{schema}_")
    _RENDERED_MAPPER_DIRS.append(folder)
    source = (PACKAGE_DIR / "recipe.sql").read_text(encoding="utf-8")
    (Path(folder) / "recipe.sql").write_text(render_schema_sql(source, schema), encoding="utf-8")
    return Path(folder)


def create_recipe_sql_session(*, sql_log: bool | None = None, schema: str | None = None):
    """``recipe.sql`` mapper를 등록한 공통 ``PostgresDbSession`` 을 만든다.

    mapper 검색 시작점은 이 패키지 폴더(``Path(__file__)`` 기준)이므로 실행 위치와 무관하다.
    ``PostgresDbSession`` 은 하위 폴더까지 ``-- name:`` 이 있는 ``*.sql`` 만 등록하며,
    ``sql/001_create_recipe_schema.sql`` 같은 수동 실행 스크립트는 건너뛴다.
    ``schema`` (또는 환경변수 ``RECIPE_DB_SCHEMA``)가 ``recipe`` 가 아니면 그 스키마를 가리키는
    mapper 사본을 등록한다(격리 리허설 스키마 적재·조회용). ``session.recipe_schema`` 에 대상 스키마를 남긴다.
    사용이 끝나면 ``session.database_manager.close()`` 로 pool을 닫는다.
    ``sql_log`` 를 생략(None)하면 환경변수 ``RECIPE_QUERY_LOG`` 를 따른다(기본 꺼짐). 켜져 있으면
    INFO 로깅도 설정해 바인딩 값이 채워진 SQL(combined)을 터미널에 출력한다. 명시한 True/False가 우선한다.
    """
    prepare_common_imports()
    load_project_environment()
    from common.postgres_db_session import PostgresDbSession

    if sql_log is None:
        sql_log = configure_query_logging()
    target = configured_schema(schema)
    session = PostgresDbSession(mapper_root=_mapper_root_for(target), sql_log_mode="combined" if sql_log else "none")
    session.recipe_schema = target
    return session


# endregion
# region 3. 관리 도구용 PostgreSQL 연결 컨텍스트
# =========================================================
# with 블록의 연결 획득·반납과 search_path 설정
# =========================================================
@contextmanager
def recipe_connection() -> Iterator[object]:
    """레시피 스키마를 search_path로 설정한 연결을 ``with`` 블록에 제공한다.

    Transaction Pooler에서는 현재 트랜잭션에만 적용되는 ``SET LOCAL``을 쓰고
    자동 prepared statement를 끈다. 다른 연결 방식은 세션 수준으로 설정한다.
    ``@contextmanager``의 ``yield`` 전후가 Java의 자원 획득·반납에 해당한다.

    Yields:
        object: ``common.DatabaseManager``에서 빌린 psycopg 연결.
    """
    prepare_imports()
    load_project_environment()
    mode = get_pool_mode()
    schema = configured_schema()
    manager = _get_manager()
    with manager.connect(camel_case_keys=False) as connection:
        if mode == "transaction_pooler":
            connection.prepare_threshold = None
            with connection.transaction():
                connection.execute(f"SET LOCAL search_path TO {schema}, public")
                yield connection
        else:
            connection.execute(f"SET search_path TO {schema}, public")
            yield connection

# endregion

