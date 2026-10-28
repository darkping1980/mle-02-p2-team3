"""레시피 CLI 골격의 준비 상태만 출력하는 독립 실행 모듈.

``search_recipe``에 실행을 위임하지 않는다. 실제 PostgreSQL 조회 CLI는
``recipe_recommender.search_recipe``를 직접 실행해야 한다.
"""

import sys
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[1]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from recipe_recommender.config import prepare_imports


# region 1. CLI 준비 상태 출력
# =========================================================
# 골격 CLI 실행 및 종료 코드 반환
# =========================================================

def main() -> int:
    """import 경로를 준비하고 골격 안내문을 출력한 뒤 0을 반환한다."""
    prepare_imports()
    print("Recipe recommender scaffold is ready. Recipe behavior is not implemented.")
    return 0


# =========================================================
# 직접 실행 진입점: import만 할 때는 main()을 호출하지 않는다.
# =========================================================
if __name__ == "__main__":
    raise SystemExit(main())

# endregion

