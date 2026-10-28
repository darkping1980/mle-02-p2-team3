"""[기존 모델 전용·실행 차단] recipe 스키마 전체 재생성(명시적 rebuild 전용, 데이터 보존 없음).

``docs/db/recipe_schema_rebuild.sql`` 을 그대로 실행한다. 스크립트 자체가 BEGIN/COMMIT과
사전·사후 검증을 포함하므로 실패하면 전체 ROLLBACK된다.
일반 CSV 등록(``register_recipe_csv``)은 이 도구를 호출하지 않는다.

    python -m recipe_recommender.tools.rebuild_recipe_schema                     # 현재 객체·건수만 출력
    python -m recipe_recommender.tools.rebuild_recipe_schema --confirm-rebuild   # 실제 삭제·재생성
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from recipe_recommender.tools._sql_script import run_sql_script  # noqa: E402

REBUILD_SQL = TASK_DIR / "docs" / "db" / "recipe_schema_rebuild.sql"


# region 1. 기존 모델 전용 스키마 도구 진입점
# =========================================================
# 확인 옵션이 있어도 현재 모델에서는 재생성을 차단
# =========================================================

def main(argv=None) -> int:
    """기존 모델 전용 스키마 재생성 진입점의 실행 차단 조건을 적용한다."""
    parser = argparse.ArgumentParser(description="recipe 스키마 전체 삭제·재생성")
    parser.add_argument("--confirm-rebuild", action="store_true", help="실제로 삭제·재생성한다(데이터 삭제)")
    args = parser.parse_args(argv)
    if args.confirm_rebuild:
        # 기존(복합 키·식재료 분류) 모델 전용 스크립트다. 목표 모델 전환 이후 실행하면 새 구조와 충돌하므로 막는다.
        print("[중단] 기존 모델 전용 도구입니다. 목표 모델 재구축·복구는 tools/recipe_rebuild.py 를 사용하세요.")
        return 1
    return run_sql_script(REBUILD_SQL, confirmed=args.confirm_rebuild, confirm_flag="--confirm-rebuild")


# =========================================================
# 직접 실행 진입점
# =========================================================
if __name__ == "__main__":
    raise SystemExit(main())

# endregion
