"""기존 ``DB_URL``로 PostgreSQL 읽기 연결을 확인하는 단독 실행 도구."""

from __future__ import annotations

import os
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from recipe_recommender.tools._connection_util import initialize, safe_error


QUERY = "SELECT 1 AS value;"


# region 1. PostgreSQL 읽기 연결 및 대상 식별
# =========================================================
# 공통 DB 관리자 또는 의존 패키지 부재 시 직접 연결
# =========================================================

def _run_query():
    """공통 연결 관리자로 SELECT를 실행하고 의존 패키지가 없을 때 psycopg를 쓴다."""
    try:
        from common.database_manager import DatabaseManager
    except ModuleNotFoundError as error:
        # DatabaseManager의 pgvector 의존성과 무관하게 SELECT 연결만 확인하려고 psycopg를 사용한다.
        if error.name not in {"pgvector", "psycopg_pool"}:
            raise
        import psycopg

        with psycopg.connect(os.environ["DB_URL"], connect_timeout=10) as connection:
            row = connection.execute(QUERY).fetchone()
            return row[0], "direct psycopg fallback (common module dependency unavailable)"

    manager = DatabaseManager()
    try:
        with manager.connect(camel_case_keys=False) as connection:
            row = connection.execute(QUERY).fetchone()
            value = row["value"] if isinstance(row, dict) else row[0]
        return value, "common.DatabaseManager"
    finally:
        manager.close()


def _target_label() -> str:
    """``DB_URL`` 호스트와 설정값을 기준으로 확인한 대상의 표시명을 고른다."""
    from urllib.parse import urlparse

    host = urlparse(os.getenv("DB_URL", "")).hostname or ""
    if host.endswith(".supabase.co") or host.endswith(".supabase.com"):
        return "Supabase PostgreSQL"
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SECRET_KEY"):
        return "PostgreSQL via DB_URL (Supabase target not independently verified)"
    return "PostgreSQL via DB_URL (Supabase configuration not found)"


# endregion


# region 2. 연결 점검 CLI
# =========================================================
# SELECT 1 결과와 종료 코드 결정
# =========================================================

def main() -> int:
    """PostgreSQL에 연결해 SELECT 한 건으로 연결 상태를 확인한다."""
    initialize()
    print("[Supabase PostgreSQL Connection Test]")
    if not os.getenv("DB_URL"):
        print("Configuration : NOT TESTED (DB_URL is not configured)")
        print("Connection    : NOT TESTED")
        print(f"Query         : {QUERY}")
        print("Status        : NOT TESTED")
        return 2

    print("Configuration : OK")
    try:
        value, method = _run_query()
        print(f"Target        : {_target_label()}")
        print(f"Connection    : OK ({method})")
        print(f"Query         : {QUERY}")
        print(f"Result        : {value}")
        status = value == 1
        print("Status        : " + ("SUCCESS" if status else "FAILED"))
        return 0 if status else 1
    except Exception as error:
        print(f"Target        : {_target_label()}")
        print("Connection    : FAILED")
        print(f"Query         : {QUERY}")
        print(f"Error         : {type(error).__name__}: {safe_error(error)}")
        print("Status        : FAILED")
        return 1


# =========================================================
# 직접 실행 진입점
# =========================================================
if __name__ == "__main__":
    raise SystemExit(main())

# endregion

