"""레시피 프로젝트의 PostgreSQL 세션과 SQL mapper 경로를 구성한다.

등록·조회 진입점이 이 모듈의 세션 팩토리를 사용한다.
Connection Pool 생성·대여·반환·종료는 세션이 소유한 ``common.DatabaseManager`` 가 담당한다.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from recipe_recommender.config import PACKAGE_DIR, configure_query_logging, load_project_environment
from recipe_recommender.sql_schema import DEFAULT_SCHEMA, configured_schema, render_schema_sql


# region 1. recipe.sql Mapper 경로와 세션 생성
# =========================================================
# 프로젝트 설정 → common.PostgresDbSession 연결
# =========================================================
def _mapper_root_for(schema: str) -> Path:
    """기본 스키마면 패키지 폴더, 아니면 ``recipe.`` 한정자를 바꾼 ``recipe.sql`` 사본을 둔 임시 폴더.

    임시 폴더 삭제는 호출자가 맡는다(``create_recipe_sql_session`` 은 mapper 등록 직후 지운다).
    """
    if schema == DEFAULT_SCHEMA:
        return PACKAGE_DIR
    folder = Path(tempfile.mkdtemp(prefix=f"recipe_mapper_{schema}_"))
    source = (PACKAGE_DIR / "recipe.sql").read_text(encoding="utf-8")
    (folder / "recipe.sql").write_text(render_schema_sql(source, schema), encoding="utf-8")
    return folder


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
    load_project_environment()
    from common.postgres_db_session import PostgresDbSession

    if sql_log is None:
        sql_log = configure_query_logging()
    target = configured_schema(schema)
    mapper_root = _mapper_root_for(target)
    try:
        session = PostgresDbSession(mapper_root=mapper_root, sql_log_mode="combined" if sql_log else "none")
    finally:
        # 생성자가 aiosql로 SQL 본문을 모두 읽어 두므로 스키마 사본 폴더는 바로 지운다.
        if mapper_root != PACKAGE_DIR:
            shutil.rmtree(mapper_root, ignore_errors=True)
    session.recipe_schema = target
    return session

# endregion
