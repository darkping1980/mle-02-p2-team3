"""레시피 SQL의 대상 스키마 지정 도우미.

DDL·mapper·검증 SQL은 사람이 읽기 쉽도록 ``recipe.`` 를 명시해 작성한다. 다른 스키마(격리 리허설
``recipe_v2`` 등)에서 실행할 때는 이 모듈이 스키마 한정자만 바꿔 쓴다. ``search_path`` 에 의존하지 않는다.

    recipe.      → 대상 스키마 (target)
    recipe_src.  → 이관 원본 스키마 (source, 이관·검증 SQL에서만 사용)

스키마 이름은 소문자 식별자만 허용하므로 따옴표 없이 SQL에 넣어도 안전하다.
"""

from __future__ import annotations

import os
import re

DEFAULT_SCHEMA = "recipe"
SCHEMA_ENV_NAME = "RECIPE_DB_SCHEMA"

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
# 앞에 단어 문자나 점이 없는 ``recipe.`` 뒤에 영문 식별자가 오는 경우만 스키마 한정자로 본다.
_QUALIFIER = re.compile(r"(?<![\w.])recipe(_src)?\.(?=[A-Za-z_])")
_SOURCE_QUALIFIER = re.compile(r"(?<![\w.])recipe_src\.(?=[A-Za-z_])")


def validate_schema_name(name: str) -> str:
    """소문자 PostgreSQL 식별자인지 검사하고 그대로 돌려준다."""
    if not isinstance(name, str) or not _IDENTIFIER.match(name) or name.startswith("pg_"):
        raise ValueError(f"Invalid schema name: {name!r} (lowercase identifier only)")
    return name


def configured_schema(schema: str | None = None) -> str:
    """명시 인자 → 환경변수 ``RECIPE_DB_SCHEMA`` → 기본 ``recipe`` 순서로 대상 스키마를 정한다."""
    return validate_schema_name(schema or os.getenv(SCHEMA_ENV_NAME) or DEFAULT_SCHEMA)


def render_schema_sql(sql: str, target: str, source: str | None = None) -> str:
    """``recipe.`` 한정자를 ``target.`` 으로, ``recipe_src.`` 를 ``source.`` 로 바꾼다."""
    target = validate_schema_name(target)
    if _SOURCE_QUALIFIER.search(sql):
        if source is None:
            raise ValueError("SQL references recipe_src. but no source schema was given")
        source = validate_schema_name(source)
        if source == target:
            raise ValueError("source and target schema must differ")
    # 한 번에 치환한다. 원본 스키마가 ``recipe`` 인 경우 순차 치환하면 원본까지 대상으로 바뀐다.
    return _QUALIFIER.sub(lambda match: (source if match.group(1) else target) + ".", sql)
