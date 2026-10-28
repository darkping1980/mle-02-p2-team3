"""DB에 쓰기를 시도하는 테스트를 기본 실행에서 제외하고 recipe_recommender/tests를 실행하는 도구.

제외 대상은 트랜잭션을 롤백하더라도 실제 INSERT(시퀀스 소비)를 실행하는 3건이다.
제외한 테스트는 통과로 세지 않고 "실행하지 않음"으로 따로 표시한다.
쓰기 테스트까지 실행하려면 ``--include-db-write`` 를 명시한다.

실행 예(src/recipe에서):
    .venv\\Scripts\\python.exe -m recipe_recommender.tools.run_safe_tests
    .venv\\Scripts\\python.exe -m recipe_recommender.tools.run_safe_tests -v
"""

from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))


# region 1. 기본 실행에서 제외하는 DB 쓰기 테스트
# =========================================================
# 롤백 전에 실제 INSERT를 실행하는 RecipeRepositoryDatabaseTests 3건
# =========================================================
DB_WRITE_TESTS = frozenset({
    "recipe_recommender.tests.test_recipe_register.RecipeRepositoryDatabaseTests.test_load_rerun_relations_and_integrity",
    "recipe_recommender.tests.test_recipe_register.RecipeRepositoryDatabaseTests.test_ambiguous_alias_is_not_auto_approved",
    "recipe_recommender.tests.test_recipe_register.RecipeRepositoryDatabaseTests.test_failure_inside_transaction_rolls_back",
})


# endregion
# region 2. 테스트 수집과 실행
# =========================================================
# 제외 대상이 모두 수집되었는지 확인한 뒤 나머지만 실행
# =========================================================
def _flatten(suite: unittest.TestSuite):
    """중첩된 TestSuite를 개별 테스트로 편다."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


def main(argv: list[str] | None = None) -> int:
    """테스트를 수집해 DB 쓰기 테스트를 뺀 나머지를 실행하고 결과 코드(0 = 모두 통과)를 돌려준다."""
    parser = argparse.ArgumentParser(description="DB 쓰기 테스트를 제외하고 recipe 테스트를 실행한다.")
    parser.add_argument("--include-db-write", action="store_true",
                        help="롤백 전에 실제 INSERT를 실행하는 테스트 3건도 실행한다(운영 DB에서는 쓰지 않는다)")
    parser.add_argument("-v", "--verbose", action="store_true", help="테스트별 결과를 출력한다")
    args = parser.parse_args(argv)

    loaded = unittest.defaultTestLoader.discover(str(TASK_DIR / "recipe_recommender" / "tests"),
                                                 top_level_dir=str(TASK_DIR))
    tests = list(_flatten(loaded))
    found = {test.id() for test in tests} & DB_WRITE_TESTS
    missing = sorted(DB_WRITE_TESTS - found)
    if missing:
        # 이름이 바뀌어 제외 목록이 맞지 않으면 쓰기 테스트가 섞여 실행될 수 있으므로 아무것도 실행하지 않는다.
        print("제외 대상 테스트를 찾지 못해 실행을 중단합니다(DB_WRITE_TESTS를 확인하세요):")
        for test_id in missing:
            print("  -", test_id)
        return 2

    excluded = [] if args.include_db_write else sorted(found)
    selected = [test for test in tests if test.id() not in excluded]
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(unittest.TestSuite(selected))

    print(f"\n수집 {len(tests)} / 실행 {result.testsRun} / 실패 {len(result.failures)} / 오류 {len(result.errors)} "
          f"/ 건너뜀 {len(result.skipped)} / 실행하지 않음(DB 쓰기) {len(excluded)}")
    for test_id in excluded:
        print("  실행하지 않음:", test_id)
    return 0 if result.wasSuccessful() else 1


# endregion
if __name__ == "__main__":
    raise SystemExit(main())
