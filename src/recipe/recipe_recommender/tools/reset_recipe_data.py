"""[기존 모델 전용·실행 차단] recipe 스키마 11개 테이블의 업무 데이터 전체 초기화(구조 유지, 명시적 실행 전용).

``docs/db/recipe_data_reset.sql`` 을 실행한다: 사전 검증 → TRUNCATE ... RESTRICT → 0건 확인
→ 프로젝트 시퀀스 7개 재시작 → COMMIT. 단위 테스트와 일반 CSV 등록은 이 도구를 호출하지 않는다.

    python -m recipe_recommender.tools.reset_recipe_data                   # 현재 객체·건수만 출력
    python -m recipe_recommender.tools.reset_recipe_data --confirm-reset   # 실제 데이터 삭제
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from recipe_recommender.tools._sql_script import run_sql_script  # noqa: E402

RESET_SQL = TASK_DIR / "docs" / "db" / "recipe_data_reset.sql"


# region 1. 기존 모델 전용 초기화 도구 진입점
# =========================================================
# 확인 옵션이 있어도 현재 모델에서는 데이터 초기화를 차단
# =========================================================

def main(argv=None) -> int:
    """기존 모델 전용 데이터 초기화 진입점의 실행 차단 조건을 적용한다."""
    parser = argparse.ArgumentParser(description="recipe 스키마 업무 데이터 전체 초기화")
    parser.add_argument("--confirm-reset", action="store_true", help="실제로 11개 테이블 데이터를 삭제한다")
    args = parser.parse_args(argv)
    if args.confirm_reset:
        # 기존(복합 키·식재료 분류) 모델 전용 스크립트다. 목표 모델 전환 이후 실행하면 새 구조와 충돌하므로 막는다.
        print("[중단] 기존 모델 전용 도구입니다. 목표 모델 재구축·복구는 tools/recipe_rebuild.py 를 사용하세요.")
        return 1
    return run_sql_script(RESET_SQL, confirmed=args.confirm_reset, confirm_flag="--confirm-reset")


# =========================================================
# 직접 실행 진입점
# =========================================================
if __name__ == "__main__":
    raise SystemExit(main())

# endregion
