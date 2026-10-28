"""레시피 조회(RecipeSearchService)와 평면 패키지 구조 테스트.

조회 테스트는 실제 적재된 식약처 데이터를 읽기만 한다(데이터가 없으면 건너뜀).
데이터 초기화·재적재는 테스트가 하지 않는다(tools/reset_recipe_data.py 전용).
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

import recipe_recommender  # noqa: E402  (패키지 import가 common 경로와 pgvector 별칭을 준비한다)
from recipe_recommender.config import PACKAGE_DIR, load_project_environment  # noqa: E402
from recipe_recommender.recipe_search_service import MAX_PAGE_SIZE, RecipeSearchError, RecipeSearchService  # noqa: E402

load_project_environment()
PYTHON_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


class PackageLayoutTests(unittest.TestCase):
    def test_setup_and_runtime_modules_are_separated(self):
        for name in ("recipe.sql", "recipe_repository.py", "recipe_search_service.py", "search_recipe.py",
                     "setup/__init__.py", "setup/recipe_register_service.py",
                     "setup/recipe_ingredient_parser.py", "setup/register_recipe_csv.py",
                     "setup/load_recipe_graph.py", "setup/recipe_graph_load_service.py",
                     "setup/recipe_graph_source_repository.py", "name_normalization.py",
                     "data/ingr_seed.csv", "sql_schema.py", "tools/recipe_rebuild.py",
                     "tools/rebuild_recipe_schema.py", "tools/reset_recipe_data.py"):
            with self.subTest(name=name):
                self.assertTrue((PACKAGE_DIR / name).is_file())
        self.assertFalse((PACKAGE_DIR / "recipe_register").exists())
        self.assertEqual(sorted(path.name for path in PACKAGE_DIR.rglob("recipe.sql")), ["recipe.sql"])
        self.assertFalse((PACKAGE_DIR / "data" / "ingr_cat_seed.csv").exists())    # 식재료 분류 사전 제거

    def test_services_share_one_repository_class(self):
        from recipe_recommender.setup.recipe_register_service import RecipeRegisterService
        from recipe_recommender.recipe_repository import RecipeRepository

        self.assertIs(type(RecipeRegisterService(None).repository), RecipeRepository)
        self.assertIs(type(RecipeSearchService(None).repository), RecipeRepository)

    def test_common_session_is_the_shared_src_common(self):
        # team-project-prototype 이관 후 common은 과제 폴더 복사본이 아니라 src/recipe와 나란한 공용 src/common이다.
        from common.postgres_db_session import PostgresDbSession

        self.assertEqual(Path(sys.modules[PostgresDbSession.__module__].__file__).resolve().parent,
                         (TASK_DIR.parent / "common").resolve())
        self.assertFalse((TASK_DIR / "common").exists())     # 레시피 폴더 안에 중복 common을 두지 않는다

    def test_dry_run_cli_runs_with_python_m(self):
        result = subprocess.run([sys.executable, "-m", "recipe_recommender.setup.register_recipe_csv", "--limit", "3",
                                 "--dry-run", "--show", "0"], cwd=TASK_DIR, capture_output=True, text=True,
                                encoding="utf-8", env=PYTHON_ENV, check=False, timeout=180)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DRY-RUN", result.stdout)

    def test_search_cli_rejects_invalid_page_size(self):
        result = subprocess.run([sys.executable, "-m", "recipe_recommender.search_recipe", "--name", "x",
                                 "--page-size", str(MAX_PAGE_SIZE + 1)], cwd=TASK_DIR, capture_output=True,
                                text=True, encoding="utf-8", env=PYTHON_ENV, check=False, timeout=180)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("page_size", result.stdout)


class SearchValidationTests(unittest.TestCase):
    def setUp(self):
        self.service = RecipeSearchService(sql_session=None)     # 검증 단계에서 DB를 쓰지 않는다

    def test_detail_needs_exactly_one_key(self):
        with self.assertRaises(RecipeSearchError):
            self.service.get_recipe_detail()
        with self.assertRaises(RecipeSearchError):
            self.service.get_recipe_detail(rcp_seq="28", rcp_id="X")

    def test_search_needs_condition_and_valid_paging(self):
        with self.assertRaises(RecipeSearchError):
            self.service.search_recipes(name="  ")
        with self.assertRaises(RecipeSearchError):
            self.service.search_recipes(name="롤", page=0)
        with self.assertRaises(RecipeSearchError):
            self.service.search_recipes(name="롤", page_size=MAX_PAGE_SIZE + 1)


@unittest.skipUnless(os.getenv("DB_URL"), "DB_URL is not configured")
class RecipeSearchDatabaseTests(unittest.TestCase):
    """실제 적재 데이터 기준 조회 검증(읽기 전용)."""

    @classmethod
    def setUpClass(cls):
        from recipe_recommender.database import create_recipe_sql_session

        cls.session = create_recipe_sql_session()
        cls.service = RecipeSearchService(sql_session=cls.session)
        cls.repository = cls.service.repository
        if cls.repository.count_recipe_tables()["rcp"] == 0:
            cls.session.database_manager.close()
            raise unittest.SkipTest("recipe data is not loaded")
        cls.counts_before = cls.repository.count_recipe_tables()

    @classmethod
    def tearDownClass(cls):
        cls.session.database_manager.close()

    def test_zz_search_does_not_change_data(self):
        self.assertEqual(self.repository.count_recipe_tables(), self.counts_before)

    def test_recipe_28_detail(self):
        detail = self.service.get_recipe_detail(rcp_seq="28")
        recipe = detail["recipe"]
        self.assertEqual((recipe["rcpNm"], recipe["rcpCatNm"], recipe["cookMthdCd"], recipe["cookMthdNm"]),
                         ("새우 두부 계란찜", "반찬", "000004", "찌기"))
        self.assertNotEqual(recipe["rcpId"], recipe["rcpSeq"])
        self.assertEqual([step["stepNo"] for step in detail["steps"]], [1, 2, 3])
        self.assertEqual(sorted(i["ingrNm"] for i in detail["ingredients"]),
                         sorted(["연두부", "칵테일새우", "달걀", "생크림", "설탕", "무염버터", "시금치"]))
        self.assertEqual(detail["unmatchedIngredients"], [])
        by_id = self.service.get_recipe_detail(rcp_id=recipe["rcpId"])
        self.assertEqual(by_id["recipe"]["rcpSeq"], "28")           # 원본 번호 ↔ 내부 ID 1:1

    def test_same_name_recipes_stay_separate(self):
        result = self.service.search_recipes(name="양배추롤")
        exact = {row["rcpSeq"]: row for row in result["items"] if row["rcpNm"] == "양배추롤"}
        self.assertEqual(set(exact), {"298", "536"})
        self.assertNotEqual(exact["298"]["rcpId"], exact["536"]["rcpId"])
        self.assertEqual((exact["298"]["ingredientCount"], exact["536"]["ingredientCount"]), (5, 17))

    def test_risotto_pair_has_same_ingredients_but_own_ids(self):
        first = self.service.get_recipe_detail(rcp_seq="788")
        second = self.service.get_recipe_detail(rcp_seq="919")
        self.assertNotEqual(first["recipe"]["rcpId"], second["recipe"]["rcpId"])
        names = lambda detail: sorted(i["ingrNm"] for i in detail["ingredients"])  # noqa: E731
        self.assertEqual(len(names(first)), 9)
        self.assertEqual(names(first), names(second))
        self.assertNotEqual([s["rcpStepInstructionTxt"] for s in first["steps"]],
                            [s["rcpStepInstructionTxt"] for s in second["steps"]])

    def test_category_and_cook_method_search(self):
        side = self.service.search_recipes(category="반찬", page_size=5)
        self.assertEqual(side["totalCount"], 574)
        self.assertEqual(len(side["items"]), 5)
        steamed_side = self.service.search_recipes(category="반찬", cook_method="찌기")
        self.assertGreater(steamed_side["totalCount"], 0)
        self.assertTrue(all(row["rcpCatNm"] == "반찬" and (row["cookMthdCd"], row["cookMthdNm"]) == ("000004", "찌기")
                            for row in steamed_side["items"]))
        by_code = self.service.search_recipes(category="반찬", cook_method="000004")
        self.assertEqual(by_code["totalCount"], steamed_side["totalCount"])
        self.assertEqual(self.service.search_recipes(cook_method="삶기")["totalCount"], 0)
        page2 = self.service.search_recipes(category="반찬", page=2, page_size=5)
        self.assertFalse({r["rcpId"] for r in side["items"]} & {r["rcpId"] for r in page2["items"]})

    def test_ingredient_by_name_and_alias(self):
        shrimp = self.service.search_recipes_by_ingredient("칵테일새우", page_size=100)
        self.assertNotIn("ingrCatId", shrimp["ingredient"])
        self.assertIn("28", {row["rcpSeq"] for row in shrimp["items"]})
        self.assertEqual(shrimp["totalCount"], len(shrimp["items"]))
        self.assertGreater(shrimp["totalCount"], 1)
        egg = self.service.find_ingredient("계란")
        self.assertEqual((egg["ingredient"]["ingrNm"], egg["ingredient"]["matchedBy"]), ("달걀", "alias"))
        self.assertIn("계란", [alias["ingrAlsNm"] for alias in egg["aliases"]])
        self.assertTrue(all(alias["ingrAlsId"] for alias in egg["aliases"]))
        self.assertIsNone(self.service.find_ingredient("존재하지않는재료"))

    def test_steps_and_ingredients_by_seq(self):
        self.assertEqual([s["stepNo"] for s in self.service.list_recipe_steps("33")], [2, 3, 5])
        self.assertEqual(len(self.service.list_recipe_ingredients("28")), 7)
        self.assertEqual(self.service.list_recipe_steps("NO-SUCH"), [])

    def test_single_key_join_matches_relation_rows(self):
        # 레시피 PK(rcp_id)로 조인한 사용 식재료 수 = rcp_ingr 행 수 (조인 누락·중복 없음)
        detail = self.service.get_recipe_detail(rcp_seq="536")
        self.assertEqual(len(self.repository.list_recipe_ingredients(detail["recipe"]["rcpId"])), 17)
        integrity = self.repository.count_integrity_violations()
        self.assertEqual({k: v for k, v in integrity.items() if v}, {})

    def test_loaded_table_counts(self):
        self.assertEqual(self.repository.count_recipe_tables(), {
            "rcpRaw": 1156, "rcpCat": 6, "rcpCatRel": 1156, "commonCodeGrp": 1, "commonCd": 6, "rcp": 1156,
            "rcpStep": 6717, "ingr": 275, "ingrAls": 71, "rcpIngrStg": 13080, "rcpIngr": 10428,
        })


if __name__ == "__main__":
    unittest.main()
