"""레시피 CSV 등록(RecipeRegisterService·RecipeRepository·파서) 테스트.

순수 로직 테스트는 DB 없이 실행한다. DB 테스트는 ``PostgresDbSession.transaction()`` 안에서
가상 행을 쓰고 검증한 뒤 일부러 예외를 던져 ROLLBACK하므로 운영 테이블에 행이 남지 않는다.
가상 행은 실제 데이터와 겹치지 않는 ``ZZTEST-*`` 레시피 번호와 ``TEST_*`` 회차 ID를 사용한다.
(rcp_id·rcp_ingr_stg_id DEFAULT가 소비한 시퀀스 번호는 rollback되어도 돌아오지 않는다.)
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from recipe_recommender.config import load_project_environment, prepare_common_imports, project_root

prepare_common_imports()
load_project_environment()

from common.database_manager import snake_to_camel  # noqa: E402
from recipe_recommender.setup.recipe_ingredient_parser import parse_ingredient_text, parse_quantity  # noqa: E402
from recipe_recommender.setup.recipe_register_service import (  # noqa: E402
    SOURCE_COLUMNS,
    RecipeLoadError,
    RecipeRegisterService,
    evaluate_nutrition,
    load_cook_method_seed,
    load_ingredient_seed,
    resolve_cook_method_map,
    normalize_newlines,
    raw_seq_for,
    strip_step_prefix,
)

CSV_PATH = project_root() / "src" / "data" / "COOKRCP01.csv"
DOCS_DB = TASK_DIR / "docs" / "db"
TEST_RAW_ID = "TEST_BATCH_000001"
CATEGORIES = {"반찬": "CAT_SIDE", "밥": "CAT_RICE"}
COOK_METHODS = {"찌기": "000004", "끓이기": "000002"}


def make_row(seq: str, raw_seq: str = "000001", **values: str) -> dict[str, str]:
    """55개 컬럼과 회차 내 행 순번을 가진 가상 CSV 행."""
    row = {column: "" for column in SOURCE_COLUMNS}
    row.update({
        "RCP_SEQ": seq, "RCP_NM": f"테스트 {seq}", "RCP_WAY2": "찌기", "RCP_PAT2": "반찬",
        "INFO_ENG": "100", "INFO_CAR": "10", "INFO_PRO": "5", "INFO_FAT": "4", "INFO_NA": "200",
        "RCP_PARTS_DTLS": "두부 50g(1/4모), 소금 1g\n양념\n소금 0.5g, 간장(5g)",
        "MANUAL01": "1. 두부를 썬다.", "MANUAL_IMG01": "http://example.invalid/1.png",
        "MANUAL02": "2. 찐다.",
    })
    row.update(values)
    row["RCP_RAW_SEQ"] = raw_seq
    return row


class _Rollback(Exception):
    """DB 테스트 마지막에 던져 transaction()을 ROLLBACK시키는 표식 예외."""


# =========================================================
# 순수 로직 (DB 불필요)
# =========================================================
class CsvSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = RecipeRegisterService.read_csv(CSV_PATH)

    def test_bom_header_and_55_columns(self):
        self.assertEqual([key for key in self.rows[0] if key != "RCP_RAW_SEQ"], list(SOURCE_COLUMNS))
        self.assertEqual(len(SOURCE_COLUMNS), 55)
        self.assertNotIn("﻿RCP_SEQ", self.rows[0])

    def test_source_row_count_and_unique_seq(self):
        self.assertEqual(len(self.rows), 1156)
        self.assertEqual(RecipeRegisterService.validate_rows(self.rows), [])

    def test_raw_seq_follows_csv_order(self):
        self.assertEqual(self.rows[0]["RCP_RAW_SEQ"], "000001")
        self.assertEqual(self.rows[-1]["RCP_RAW_SEQ"], "001156")
        self.assertEqual([row["RCP_RAW_SEQ"] for row in self.rows], [f"{i:06d}" for i in range(1, 1157)])
        again = RecipeRegisterService.read_csv(CSV_PATH)
        self.assertEqual([(r["RCP_RAW_SEQ"], r["RCP_SEQ"]) for r in again],
                         [(r["RCP_RAW_SEQ"], r["RCP_SEQ"]) for r in self.rows])

    def test_raw_seq_limit_is_an_error_not_truncation(self):
        self.assertEqual(raw_seq_for(999_999), "999999")
        with self.assertRaises(RecipeLoadError):
            raw_seq_for(1_000_000)
        with self.assertRaises(RecipeLoadError):
            raw_seq_for(0)

    def test_multiline_quoted_fields_are_preserved(self):
        row = next(row for row in self.rows if row["RCP_SEQ"] == "28")
        # 따옴표 안 줄바꿈 보존. 체크아웃 방식(core.autocrlf)에 따라 CRLF일 수 있어 LF로 맞춰 비교한다.
        parts = normalize_newlines(row["RCP_PARTS_DTLS"])
        self.assertIn("\n고명\n", parts)
        self.assertTrue(parts.startswith("새우두부계란찜\n연두부 75g(3/4모)"))

    def test_external_id_kept_as_string(self):
        self.assertTrue(all(isinstance(row["RCP_SEQ"], str) for row in self.rows))
        self.assertIn("28", {row["RCP_SEQ"] for row in self.rows})

    def test_header_problems_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.csv"
            header = list(SOURCE_COLUMNS[:-1]) + ["RCP_SEQ"]       # RCP_NA_TIP 누락 + RCP_SEQ 중복
            path.write_text(",".join(header) + "\n", encoding="utf-8-sig")
            with self.assertRaises(RecipeLoadError) as caught:
                RecipeRegisterService.read_csv(path)
        self.assertIn("중복 헤더", str(caught.exception))
        self.assertIn("누락 헤더", str(caught.exception))

    def test_duplicate_seq_is_blocking(self):
        errors = RecipeRegisterService.validate_rows([make_row("1"), make_row("1", "000002")], expected_count=None)
        self.assertTrue(any("RCP_SEQ 중복" in error for error in errors))


class SchemaFileTests(unittest.TestCase):
    def test_rebuild_script_contains_final_ddl_unchanged(self):
        review = (DOCS_DB / "recipe_schema_review.sql").read_text(encoding="utf-8")
        rebuild = (DOCS_DB / "recipe_schema_rebuild.sql").read_text(encoding="utf-8")
        self.assertIn(review, rebuild)
        self.assertIn("BEGIN;", rebuild)
        self.assertTrue(rebuild.rstrip().endswith("COMMIT;"))
        statements = "\n".join(line for line in rebuild.splitlines() if not line.lstrip().startswith("--")).upper()
        self.assertNotIn("DROP SCHEMA", statements)
        self.assertNotIn("CASCADE", statements)


class IngredientSeedTests(unittest.TestCase):
    def test_default_seed_is_consistent(self):
        seed = load_ingredient_seed()
        names = [name for name, _ in seed.ingredients]
        self.assertEqual((len(names), seed.alias_count), (275, 71))     # 기존 DB의 표준명·별칭 수와 같다
        self.assertEqual(len(names), len(set(names)))
        mapping = dict(seed.ingredients)
        self.assertIn("계란", mapping["달걀"])
        self.assertNotIn("칵테일새우", mapping["새우"])       # 유사 이름은 별칭으로 합치지 않는다

    def test_alias_conflict_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            ingr = Path(folder) / "ingr.csv"
            ingr.write_text("ingr_nm,ingr_als_nms\n새우,칵테일새우\n칵테일새우,\n", encoding="utf-8")
            with self.assertRaises(RecipeLoadError):
                load_ingredient_seed(ingr)

    def test_category_column_seed_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            ingr = Path(folder) / "ingr.csv"
            ingr.write_text("ingr_cat_nm,ingr_nm,ingr_als_nms\n어패류,새우,\n", encoding="utf-8")
            with self.assertRaises(RecipeLoadError):
                load_ingredient_seed(ingr)


class CookMethodCodeTests(unittest.TestCase):
    def test_default_seed_is_the_confirmed_code_table(self):
        self.assertEqual(load_cook_method_seed(), {
            "000001": "굽기", "000002": "끓이기", "000003": "볶기",
            "000004": "찌기", "000005": "튀기기", "000006": "기타",
        })

    def test_every_source_method_maps_to_a_code(self):
        mapping = resolve_cook_method_map({}, load_cook_method_seed())
        source = {row["RCP_WAY2"] for row in RecipeRegisterService.read_csv(CSV_PATH)}
        self.assertEqual(source - set(mapping), set())
        self.assertTrue(all(code != name for name, code in mapping.items()))     # 코드값 = 명칭 금지

    def test_bad_seed_is_rejected(self):
        for body in ("common_cd,common_cd_nm\n1,굽기\n",                       # 6자리 아님
                     "common_cd,common_cd_nm\n굽기,굽기\n",                    # 한글 코드
                     "common_cd,common_cd_nm\n000001,굽기\n000001,볶기\n",    # 코드 중복
                     "common_cd,common_cd_nm\n000001,굽기\n000002,굽기\n"):   # 명칭 중복
            with self.subTest(body=body), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "cook.csv"
                path.write_text(body, encoding="utf-8")
                with self.assertRaises(RecipeLoadError):
                    load_cook_method_seed(path)

    def test_db_conflicts_are_rejected_not_renumbered(self):
        seed = {"000001": "굽기", "000002": "끓이기"}
        self.assertEqual(resolve_cook_method_map({"000001": "굽기"}, seed), {"굽기": "000001", "끓이기": "000002"})
        self.assertEqual(resolve_cook_method_map({"000007": "삶기"}, seed)["삶기"], "000007")  # 기존 추가 코드 유지
        for db_codes in ({"굽기": "굽기"},                 # 이전 방식 한글 코드 잔존
                         {"000001": "볶기"},               # 같은 코드에 다른 명칭(재번호화)
                         {"000009": "굽기"}):              # 같은 명칭에 다른 코드
            with self.subTest(db_codes=db_codes), self.assertRaises(RecipeLoadError):
                resolve_cook_method_map(db_codes, seed)

    def test_unknown_cook_method_is_blocking_without_new_code(self):
        plan = RecipeRegisterService(sql_session=None).build_plan(
            [make_row("A1", RCP_WAY2="삶기")], CATEGORIES, COOK_METHODS, {})
        self.assertEqual(plan.recipes, [])
        self.assertTrue(any("삶기" in error and "COOK_MTHD 코드표에 없음" in error for error in plan.blocking_errors))


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.service = RecipeRegisterService(sql_session=None)

    def plan(self, rows, existing=None, relations=None):
        return self.service.build_plan(rows, CATEGORIES, COOK_METHODS, existing or {}, relations or {})

    def test_category_and_cook_method_mapping(self):
        plan = self.plan([make_row("A1"), make_row("A2", "000002", RCP_PAT2="밥", RCP_WAY2="끓이기")])
        self.assertEqual([r["COOK_MTHD_CD"] for r in plan.recipes], ["000004", "000002"])
        self.assertTrue(all("RCP_CAT_ID" not in r for r in plan.recipes))       # 분류는 rcp 컬럼이 아니다
        self.assertEqual(plan.category_relations, [{"RCP_SEQ": "A1", "RCP_CAT_ID": "CAT_SIDE"},
                                                   {"RCP_SEQ": "A2", "RCP_CAT_ID": "CAT_RICE"}])
        self.assertTrue(all("RCP_CAT_ID" not in step for step in plan.steps))

    def test_unknown_master_values_block_load(self):
        plan = self.plan([make_row("A1", RCP_PAT2="없는분류"), make_row("A2", "000002", RCP_WAY2="삶기")])
        self.assertEqual(len(plan.blocking_errors), 2)
        self.assertEqual(plan.recipes, [])

    def test_raw_and_staging_carry_raw_seq(self):
        plan = self.plan([make_row("A1", "000007")])
        self.assertEqual(plan.raw_rows[0]["RCP_RAW_SEQ"], "000007")
        self.assertEqual(plan.raw_rows[0]["RCP_SEQ"], "A1")
        self.assertEqual({s["RCP_RAW_SEQ"] for s in plan.stagings}, {"000007"})
        self.assertEqual([s["RCP_INGR_LINE_NO"] for s in plan.stagings], [1, 2, 3, 4])

    def test_raw_keeps_original_text_and_empty_as_null(self):
        plan = self.plan([make_row("A1", HASH_TAG="  공백 포함 ")])
        raw = plan.raw_rows[0]
        self.assertEqual(raw["HASH_TAG"], "  공백 포함 ")
        self.assertIsNone(raw["MANUAL20"])
        self.assertEqual(raw["MANUAL01"], "1. 두부를 썬다.")
        self.assertEqual(plan.recipes[0]["RCP_HASH_TAG"], "공백 포함")

    def test_step_numbers_are_not_renumbered(self):
        row = make_row("A1", MANUAL01="", MANUAL_IMG01="", MANUAL02="2. 둘", MANUAL03="3. 셋", MANUAL05="5. 다섯")
        plan = self.plan([row])
        self.assertEqual([s["STEP_NO"] for s in plan.steps], [2, 3, 5])
        self.assertEqual(plan.steps[0]["RCP_STEP_INSTRUCTION_TXT"], "둘")
        self.assertTrue(any("단계 번호 공백" in issue for issue in plan.step_issues))

    def test_step_prefix_removed_only_when_number_matches(self):
        self.assertEqual(strip_step_prefix("1. 손질된 새우를 데친다.a", 1), "손질된 새우를 데친다.a")
        self.assertEqual(strip_step_prefix("2. 다른 번호", 1), "2. 다른 번호")

    def test_changed_source_category_is_reported_not_relinked(self):
        plan = self.plan([make_row("A1")], existing={"A1": ("RCP_X", "OLD")}, relations={"RCP_X": {"CAT_RICE"}})
        self.assertEqual(len(plan.recipes), 1)              # 레시피 본문은 갱신 대상
        self.assertEqual(plan.category_relations, [])       # 관계는 임의로 추가·삭제하지 않는다
        self.assertEqual(len(plan.category_conflicts), 1)
        self.assertEqual(len(plan.raw_rows), 1)             # 원본 이력은 보존한다

    def test_existing_relation_is_kept_as_candidate(self):
        plan = self.plan([make_row("A1")], existing={"A1": ("RCP_X", "OLD")}, relations={"RCP_X": {"CAT_SIDE"}})
        self.assertEqual(plan.category_conflicts, [])
        self.assertEqual(plan.category_relations, [{"RCP_SEQ": "A1", "RCP_CAT_ID": "CAT_SIDE"}])

    def test_crlf_checkout_builds_the_same_refined_values(self):
        lf = make_row("A1", RCP_NA_TIP="첫 줄\n둘째 줄", MANUAL01="1. 두부를\n썬다.")
        crlf = {key: value.replace("\n", "\r\n") if isinstance(value, str) else value for key, value in lf.items()}
        plan_lf, plan_crlf = self.plan([lf]), self.plan([crlf])
        self.assertEqual(plan_lf.recipes, plan_crlf.recipes)
        self.assertEqual(plan_lf.steps, plan_crlf.steps)
        self.assertEqual(plan_lf.stagings, plan_crlf.stagings)
        self.assertEqual(plan_crlf.raw_rows[0]["RCP_NA_TIP"], "첫 줄\r\n둘째 줄")     # 원본 저장값은 그대로

    def test_same_batch_rerun_detection_uses_raw_seq(self):
        source = make_row("A1", "000003")
        stored = {snake_to_camel(column.lower()): (source[column] or None) for column in SOURCE_COLUMNS}
        stored["rcpRawSeq"] = "000003"
        self.assertTrue(RecipeRegisterService._raw_row_matches(stored, source))
        stored["rcpNm"] = "변경된 이름"
        self.assertFalse(RecipeRegisterService._raw_row_matches(stored, source))
        self.assertFalse(RecipeRegisterService._raw_row_matches(stored, None))

    def test_same_batch_rerun_ignores_only_line_ending_kind(self):
        source = make_row("A1", "000001", RCP_PARTS_DTLS="두부 50g\r\n양념\r\n소금 1g")
        stored = {snake_to_camel(column.lower()): (source[column] or None) for column in SOURCE_COLUMNS}
        stored["rcpPartsDtls"] = "두부 50g\n양념\n소금 1g"           # DB에는 LF로 저장된 같은 원본
        self.assertTrue(RecipeRegisterService._raw_row_matches(stored, source))
        stored["rcpPartsDtls"] = "두부 60g\n양념\n소금 1g"
        self.assertFalse(RecipeRegisterService._raw_row_matches(stored, source))


class NutritionTests(unittest.TestCase):
    def test_valid_values_are_converted(self):
        values, status, _ = evaluate_nutrition(make_row("N1"))
        self.assertEqual(status, "VALID")
        self.assertEqual(values["RCP_ENERGY_KCAL"], Decimal("100"))
        self.assertIsNone(values["RCP_SERVING_WEIGHT_VALUE"])

    def test_conversion_failure_is_review_not_guess(self):
        values, status, note = evaluate_nutrition(make_row("N1", INFO_NA="약 200"))
        self.assertEqual(status, "REVIEW_REQUIRED")
        self.assertIsNone(values["RCP_SODIUM_MG"])
        self.assertIn("INFO_NA 숫자 변환 실패", note)

    def test_energy_mismatch_is_flagged_and_kept(self):
        values, status, note = evaluate_nutrition(make_row("N1", INFO_ENG="900"))
        self.assertEqual(status, "REVIEW_REQUIRED")
        self.assertEqual(values["RCP_ENERGY_KCAL"], Decimal("900"))
        self.assertIn("열량 불일치", note)


class IngredientParserTests(unittest.TestCase):
    def test_recipe_28_items_sections_and_quantities(self):
        text = ("새우두부계란찜\n연두부 75g(3/4모), 칵테일새우 20g(5마리), 달걀 30g(1/2개), "
                "생크림 13g(1큰술), 설탕 5g(1작은술), 무염버터 5g(1작은술)\n고명\n시금치 10g(3줄기)")
        items = parse_ingredient_text(text, "새우 두부 계란찜")
        self.assertEqual([item.parsed_nm for item in items],
                         ["연두부", "칵테일새우", "달걀", "생크림", "설탕", "무염버터", "시금치"])
        self.assertEqual([item.line_no for item in items], list(range(1, 8)))
        self.assertEqual((items[0].qty, items[0].unit_nm), (Decimal("75.000"), "g"))
        self.assertIn("보조분량=3/4모", items[0].note)
        self.assertEqual(items[-1].section_txt, "고명")
        self.assertTrue(all(item.parse_status == "OK" for item in items))

    def test_repeated_ingredient_is_kept_per_occurrence(self):
        items = parse_ingredient_text("소금 1g, 두부 50g\n양념\n소금 0.5g", "x")
        salts = [item for item in items if item.parsed_nm == "소금"]
        self.assertEqual([(s.line_no, s.qty, s.section_txt) for s in salts],
                         [(1, Decimal("1.000"), None), (3, Decimal("0.500"), "양념")])

    def test_parenthesised_amount_and_fraction(self):
        items = parse_ingredient_text("참치(캔, 30g), 양파(½개), 꽈리고추(2줌=100g)", "x")
        self.assertEqual([(i.parsed_nm, i.qty, i.unit_nm) for i in items],
                         [("참치", Decimal("30.000"), "g"), ("양파", Decimal("0.500"), "개"),
                          ("꽈리고추", Decimal("100.000"), "g")])
        self.assertEqual(parse_quantity("1½"), Decimal("1.500"))

    def test_uncertain_text_is_not_forced(self):
        items = parse_ingredient_text("잣 1g 설탕시럼 설탕과 물을 동량으로 하여 중불에서 서서히 녹인다.", "x")
        self.assertEqual(items[0].parse_status, "FAILED")
        self.assertIsNone(items[0].parsed_nm)
        ambiguous = parse_ingredient_text("달래무침 달래(10g)", "x")[0]
        self.assertEqual(ambiguous.parse_status, "AMBIGUOUS")

    def test_inline_section_marker_is_split(self):
        items = parse_ingredient_text("소금적당량 [바질 페스토] 잣 10g", "x")
        self.assertEqual([(i.parsed_nm, i.section_txt) for i in items], [("소금", None), ("잣", "바질 페스토")])

    def test_empty_parts_produce_no_rows(self):
        self.assertEqual(parse_ingredient_text("", "x"), [])


# =========================================================
# DB 테스트 (트랜잭션 ROLLBACK)
# =========================================================
@unittest.skipUnless(os.getenv("DB_URL"), "DB_URL is not configured")
class RecipeRepositoryDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from recipe_recommender.database import create_recipe_sql_session

        cls.session = create_recipe_sql_session()
        cls.service = RecipeRegisterService(sql_session=cls.session)
        cls.repository = cls.service.repository

    @classmethod
    def tearDownClass(cls):
        cls.session.database_manager.close()

    def tearDown(self):
        # 어떤 테스트도 가상 행을 남기지 않았는지 매 테스트 후 확인한다.
        counts = self.repository.count_batch_rows(TEST_RAW_ID)
        self.assertEqual(counts["rawCount"] + counts["recipeCount"] + counts["stagingCount"], 0)
        self.assertNotIn("ZZTEST-1", self.repository.list_recipe_key_map())

    def _run_and_rollback(self, body):
        with self.assertRaises(_Rollback):
            with self.session.transaction():
                body(self.session._active_connection)
                raise _Rollback

    def _rows(self):
        return [
            make_row("ZZTEST-1", "000001"),
            make_row("ZZTEST-2", "000002", RCP_PAT2="밥", MANUAL01="", MANUAL_IMG01="", MANUAL03="3. 셋"),
        ]

    def test_mapper_is_registered(self):
        mapper = self.session.mappers["recipe"]
        for query_id in ("find_next_rcp_raw_id", "insert_recipe_raw", "insert_recipe", "update_recipe",
                         "upsert_recipe_step", "upsert_common_code", "insert_ingredient_alias",
                         "insert_recipe_ingredient_staging", "insert_recipe_ingredient_relations", "count_integrity_violations"):
            self.assertIn(query_id, mapper.available_queries)

    def test_load_rerun_relations_and_integrity(self):
        rows = self._rows()
        seed = load_ingredient_seed()

        def body(connection):
            self.service.register_reference_masters(rows)
            self.service.register_ingredient_master(seed)
            category_map = self.repository.list_recipe_category_map()
            plan = self.service.build_plan(rows, category_map, self.service.cook_method_map(),
                                           self.repository.list_recipe_key_map(),
                                           self.repository.list_recipe_category_relations())
            written = self.service.write_plan(plan, TEST_RAW_ID)
            self.assertEqual((written["rcp_raw"], written["rcp_insert"], written["rcp_cat_rel"], written["rcp_step"]),
                             (2, 2, 2, 4))
            self.assertEqual(written["rcp_ingr_stg"], 8)
            # 소금 4행·두부 2행·간장 2행이 표준명과 정확히 일치 → 자동 승인
            self.assertEqual(written["rcp_ingr_stg_auto_approved"], 8)
            # 레시피 2개 × (두부, 소금, 간장) — 소금 2회 등장은 1건으로 합쳐진다
            self.assertEqual(written["rcp_ingr"], 6)

            raw = connection.execute("SELECT rcp_raw_seq, rcp_seq FROM recipe.rcp_raw WHERE rcp_raw_id = %s"
                                     " ORDER BY rcp_raw_seq", (TEST_RAW_ID,)).fetchall()
            self.assertEqual([(r["rcpRawSeq"], r["rcpSeq"]) for r in raw], [("000001", "ZZTEST-1"), ("000002", "ZZTEST-2")])
            keys = self.repository.list_recipe_key_map()
            first_rcp_id = keys["ZZTEST-2"][0]
            self.assertEqual(self.repository.list_recipe_category_relations()[first_rcp_id], {category_map["밥"]})
            self.assertNotEqual(first_rcp_id, "ZZTEST-2")      # 원본 번호와 내부 ID는 다르다
            steps = connection.execute("SELECT step_no FROM recipe.rcp_step WHERE rcp_id = %s"
                                       " ORDER BY step_no", (first_rcp_id,)).fetchall()
            self.assertEqual([s["stepNo"] for s in steps], [2, 3])
            stg_ids = connection.execute("SELECT rcp_ingr_stg_id FROM recipe.rcp_ingr_stg WHERE rcp_raw_id = %s",
                                         (TEST_RAW_ID,)).fetchall()
            self.assertEqual(len({s["rcpIngrStgId"] for s in stg_ids}), 8)

            # 같은 회차 재실행: 새 rcp_id·staging ID를 발급하지 않고 변경 0건
            again = self.service.write_plan(plan, TEST_RAW_ID)
            self.assertEqual((again["rcp_raw"], again["rcp_insert"], again["rcp_update"], again["rcp_cat_rel"],
                              again["rcp_step"], again["rcp_ingr_stg"], again["rcp_ingr"]), (0, 0, 0, 0, 0, 0, 0))
            self.assertEqual(self.repository.list_recipe_key_map()["ZZTEST-2"][0], first_rcp_id)
            self.assertEqual(self.service.register_ingredient_master(seed)[0], {"ingr": 0, "ingr_als": 0})

            integrity = self.repository.count_integrity_violations()
            self.assertEqual({k: v for k, v in integrity.items() if v}, {})

            # 논리 고아 참조 검출
            connection.execute("INSERT INTO recipe.rcp_step (rcp_id, step_no, rcp_step_instruction_txt,"
                               " create_user_id, update_user_id) VALUES ('NO_RCP', 1, 'x', 'test', 'test')")
            connection.execute("INSERT INTO recipe.rcp_ingr_stg (rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id, rcp_ingr_line_no,"
                               " rcp_ingr_raw_txt, create_user_id, update_user_id)"
                               " VALUES ('NO_RAW', '000001', 'TEST_STG', 1, 'x', 'test', 'test')")
            integrity = self.repository.count_integrity_violations()
            self.assertEqual((integrity["stepWithoutRecipe"], integrity["stagingWithoutRaw"]), (1, 1))

        self._run_and_rollback(body)

    def test_ambiguous_alias_is_not_auto_approved(self):
        rows = self._rows()[:1]

        def body(connection):
            self.service.register_reference_masters(rows)
            self.service.register_ingredient_master(load_ingredient_seed())
            # '두부'를 다른 가상 식재료의 별칭으로도 등록하면 대상이 둘이 되어 자동 승인하지 않는다.
            self.repository.insert_ingredients([{"INGR_NM": "ZZTEST콩"}])
            other = self.repository.list_ingredient_map()["ZZTEST콩"]
            self.repository.insert_ingredient_aliases([{"INGR_ID": other, "INGR_ALS_NM": "두부"}])
            plan = self.service.build_plan(rows, self.repository.list_recipe_category_map(),
                                           self.service.cook_method_map(), {})
            self.service.write_plan(plan, TEST_RAW_ID)
            statuses = connection.execute("SELECT rcp_ingr_parsed_nm, rcp_ingr_status FROM recipe.rcp_ingr_stg"
                                          " WHERE rcp_raw_id = %s ORDER BY rcp_ingr_line_no", (TEST_RAW_ID,)).fetchall()
            self.assertEqual(statuses[0], {"rcpIngrParsedNm": "두부", "rcpIngrStatus": "PENDING_REVIEW"})
            self.assertEqual(statuses[1]["rcpIngrStatus"], "AUTO_APPROVED")

        self._run_and_rollback(body)

    def test_failure_inside_transaction_rolls_back(self):
        rows = self._rows()[:1]
        original = self.repository.insert_recipes

        def failing_insert(*args, **kwargs):
            raise RuntimeError("simulated failure after rcp_raw insert")

        self.repository.insert_recipes = failing_insert
        try:
            with self.assertRaises(RuntimeError):
                with self.session.transaction():
                    self.service.register_reference_masters(rows)
                    plan = self.service.build_plan(rows, self.repository.list_recipe_category_map(),
                                                   self.service.cook_method_map(), {})
                    self.service.write_plan(plan, TEST_RAW_ID)
        finally:
            self.repository.insert_recipes = original
        self.assertEqual(self.repository.count_batch_rows(TEST_RAW_ID)["rawCount"], 0)

    def test_write_plan_requires_transaction(self):
        plan = self.service.build_plan(self._rows()[:1], CATEGORIES, COOK_METHODS, {})
        with self.assertRaises(RuntimeError):
            self.service.write_plan(plan, TEST_RAW_ID)

    def test_register_dry_run_reads_real_csv_without_writing(self):
        before = self.repository.count_recipe_tables()
        result = self.service.register(CSV_PATH, dry_run=True)
        self.assertEqual(result.plan.source_row_count, 1156)
        self.assertEqual(len(result.plan.raw_rows), 1156)
        self.assertIsNone(result.rcp_raw_id)
        self.assertEqual(self.repository.count_recipe_tables(), before)


if __name__ == "__main__":
    unittest.main()
