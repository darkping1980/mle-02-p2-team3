"""BEGIN/COMMIT을 포함한 관리용 SQL 스크립트(재생성·초기화)를 실행하는 공통 도우미.

공통 ``DatabaseManager`` 의 연결을 빌려 스크립트를 그대로 실행한다. 스크립트 자체가
트랜잭션과 사전·사후 검증을 포함하므로, 실패하면 ROLLBACK하고 오류를 보고한다.
"""

from __future__ import annotations

from pathlib import Path

from recipe_recommender.config import load_project_environment, prepare_common_imports

# region 1. 스키마 상태 조회
# =========================================================
# 스크립트 실행 전후의 recipe 스키마 확인
# =========================================================

OBJECTS_SQL = """
SELECT c.relname AS object_nm,
       CASE c.relkind WHEN 'r' THEN 'table' WHEN 'S' THEN 'sequence' ELSE c.relkind::text END AS object_type
FROM pg_class AS c
WHERE c.relnamespace = 'recipe'::regnamespace AND c.relkind IN ('r', 'S', 'v', 'm', 'p', 'f')
ORDER BY 2, 1
"""


def print_state(connection, title: str) -> None:
    """recipe 스키마 객체와 테이블 행 수, 시퀀스 현재값을 출력한다(읽기 전용)."""
    print(f"[{title}] database={connection.execute('SELECT current_database() AS db').fetchone()['db']}")
    for row in connection.execute(OBJECTS_SQL).fetchall():
        line = f"  {row['object_type']:<8} recipe.{row['object_nm']}"
        if row["object_type"] == "table":
            count = connection.execute(f'SELECT count(*) AS n FROM recipe."{row["object_nm"]}"').fetchone()["n"]
            line += f"  rows={count}"
        elif row["object_type"] == "sequence":
            value = connection.execute(
                f'SELECT last_value, is_called FROM recipe."{row["object_nm"]}"').fetchone()
            line += f"  last_value={value['last_value']} is_called={value['is_called']}"
        print(line)
    for row in connection.execute(
            "SELECT p.oid::regprocedure::text AS fn FROM pg_proc AS p WHERE p.pronamespace = 'recipe'::regnamespace"):
        print(f"  function {row['fn']}")
    connection.rollback()


# endregion


# region 2. 명시적 확인 후 SQL 스크립트 실행
# =========================================================
# SQL 파일 자체의 트랜잭션 경계에 실행 제어권 전달
# =========================================================

def run_sql_script(script_path: Path, *, confirmed: bool, confirm_flag: str) -> int:
    """스크립트 실행 전후 상태를 출력하고, ``confirmed`` 일 때만 실제로 실행한다. Returns 종료 코드."""
    prepare_common_imports()
    load_project_environment()
    from common.database_manager import DatabaseManager

    manager = DatabaseManager()
    try:
        with manager.connect(camel_case_keys=False) as connection:
            print_state(connection, "BEFORE")
            if not confirmed:
                print(f"{confirm_flag} 가 없어 변경하지 않았습니다.")
                return 0
            notices: list[str] = []
            connection.add_notice_handler(lambda diag: notices.append(diag.message_primary))
            connection.autocommit = True        # 스크립트의 BEGIN/COMMIT이 트랜잭션을 제어한다.
            try:
                connection.execute(script_path.read_text(encoding="utf-8"))
            except Exception as error:
                if not connection.closed:
                    connection.execute("ROLLBACK")
                for message in notices:
                    print(f"  NOTICE: {message}")
                print(f"[ROLLBACK] {script_path.name} 실패: {error}")
                return 1
            finally:
                connection.autocommit = False
            for message in notices:
                print(f"  NOTICE: {message}")
            print(f"[COMMIT] {script_path.name} 완료")
            print_state(connection, "AFTER")
    finally:
        manager.close()
    return 0

# endregion
