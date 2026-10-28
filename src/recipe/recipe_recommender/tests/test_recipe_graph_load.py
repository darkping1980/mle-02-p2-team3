"""Small isolated tests; no live PostgreSQL or Neo4j writes."""

from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

from recipe_recommender.setup.recipe_graph_load_service import (
    EXPECTED_INDEXES, EXPECTED_PKS, EXPECTED_SCHEMA, STAGES, RecipeGraphLoadService,
)
from recipe_recommender.recipe_graph_repository import RecipeGraphRepository, SCHEMA_NAMES
from recipe_recommender.setup.recipe_graph_source_repository import GraphSourceSnapshot


def sample_snapshot() -> GraphSourceSnapshot:
    core = {
        (table, column): ("character varying(20)", True)
        for table, column in (
            ("rcp", "rcp_id"), ("ingr", "ingr_id"), ("rcp_cat", "rcp_cat_id"),
            ("rcp_cat_rel", "rcp_id"), ("rcp_cat_rel", "rcp_cat_id"),
            ("rcp_ingr", "rcp_id"), ("rcp_ingr", "ingr_id"),
        )
    }
    core.update({
        ("rcp", "rcp_seq"): ("text", True),
        ("rcp", "cook_mthd_cd"): ("character varying(20)", True),
        ("rcp", "rcp_energy_kcal"): ("numeric(10,2)", False),
        ("rcp", "rcp_image_url"): ("text", False),
        ("rcp_step", "rcp_id"): ("character varying(20)", True),
        ("rcp_step", "step_no"): ("smallint", True),
        ("rcp_step", "rcp_step_instruction_txt"): ("text", True),
        ("rcp_step", "rcp_step_image_url"): ("text", False),
    })
    return GraphSourceSnapshot(
        observed_at=datetime.now(timezone.utc), database="postgres", role="reader",
        recipe_categories=[{"rcp_cat_id": "cat", "rcp_cat_nm": "category"},
                           {"rcp_cat_id": "cat2", "rcp_cat_nm": "category 2"}],
        ingredients=[{"ingr_id": "i1", "ingr_nm": "egg"}],
        recipes=[{"rcp_id": "r1", "rcp_seq": "28", "rcp_raw_id": "raw1",
                  "rcp_nm": "recipe", "cook_mthd_cd": "000002", "cook_mthd_nm": "끓이기",
                  "rcp_energy_kcal": None, "rcp_nutrition_status": "VALID", "rcp_image_url": None}],
        recipe_category_links=[{"rcp_id": "r1", "rcp_cat_id": "cat"}, {"rcp_id": "r1", "rcp_cat_id": "cat2"}],
        aliases=[{"ingr_id": "i1", "ingr_als_nm": "eggs"}],
        uses=[{"rcp_id": "r1", "ingr_id": "i1", "rcp_raw_id": "raw1"}],
        # 원본 번호 2가 비어 있는 단계(1, 3)와 이미지가 없는 단계를 함께 둔다.
        steps=[{"rcp_id": "r1", "step_no": 3, "rcp_step_instruction_txt": "그릇에 담는다.",
                "rcp_step_image_url": "  "},
               {"rcp_id": "r1", "step_no": 1, "rcp_step_instruction_txt": "달걀을 푼다.",
                "rcp_step_image_url": "http://www.foodsafetykorea.go.kr/uploadimg/cook/20_00028_1.png"}],
        raw_refs=[{"rcp_raw_id": "raw1", "rcp_seq": "28"}], stage_status=[],
        pk_definitions=EXPECTED_PKS.copy(), column_types=core,
        code_groups=[{"common_code_grp_id": "COOK_MTHD", "common_code_grp_nm": "method"}],
    )


class PrepareTests(unittest.TestCase):
    def prepare(self, snapshot):
        return RecipeGraphLoadService(Mock(read_snapshot=Mock(return_value=snapshot)), Mock()).prepare()

    def test_valid_source_and_alias_mapping(self):
        prepared = self.prepare(sample_snapshot())
        self.assertEqual(prepared.expected_counts["RCP_USES"], 1)
        self.assertEqual(prepared.expected_counts["RCP_IN_RECIPE_CATEGORY"], 2)    # 다중 분류
        self.assertNotIn("RcpIngredientCategory", prepared.expected_counts)
        self.assertEqual(prepared.stages["ingredients"][0]["alias_names_norm"], ["eggs"])
        self.assertEqual(prepared.stages["uses"], [{"rcp_id": "r1", "ingr_id": "i1"}])

    def test_recipe_without_category_rejected(self):
        snapshot = sample_snapshot()
        snapshot.recipe_category_links.clear()
        with self.assertRaisesRegex(ValueError, "category"):
            self.prepare(snapshot)

    def test_category_relation_orphan_rejected(self):
        snapshot = sample_snapshot()
        snapshot.recipe_category_links[1]["rcp_cat_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "orphan"):
            self.prepare(snapshot)

    def test_legacy_pk_model_rejected(self):
        snapshot = sample_snapshot()
        snapshot.pk_definitions["rcp"] = ["rcp_cat_id", "rcp_id"]
        with self.assertRaisesRegex(ValueError, "target model"):
            self.prepare(snapshot)

    def test_null_key_rejected(self):
        snapshot = sample_snapshot()
        snapshot.recipes[0]["rcp_id"] = None
        with self.assertRaisesRegex(ValueError, "key"):
            self.prepare(snapshot)

    def test_duplicate_relationship_rejected(self):
        snapshot = sample_snapshot()
        snapshot.uses.append(snapshot.uses[0].copy())
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.prepare(snapshot)

    def test_orphan_relationship_rejected(self):
        snapshot = sample_snapshot()
        snapshot.uses[0]["ingr_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "orphan"):
            self.prepare(snapshot)

    def test_wrong_method_group_rejected(self):
        snapshot = sample_snapshot()
        snapshot.recipes[0]["cook_mthd_nm"] = None
        with self.assertRaisesRegex(ValueError, "COOK_MTHD"):
            self.prepare(snapshot)

    def test_missing_alias_parent_rejected(self):
        snapshot = sample_snapshot()
        snapshot.aliases[0]["ingr_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "alias"):
            self.prepare(snapshot)

    def test_steps_keep_source_number_order_and_blank_image_is_omitted(self):
        prepared = self.prepare(sample_snapshot())
        self.assertEqual(prepared.expected_counts["rcp_step"], 2)
        self.assertEqual(prepared.expected_counts["RCP_HAS_STEP"], 2)        # 단계 한 행 = 노드 + 관계
        steps = prepared.stages["steps"]
        self.assertEqual([(row["rcp_id"], row["step_no"]) for row in steps], [("r1", 1), ("r1", 3)])
        self.assertEqual(steps[0]["rcp_step_instruction_txt"], "달걀을 푼다.")      # 원문 그대로
        self.assertTrue(steps[0]["rcp_step_image_url"].startswith("http://"))    # 저장값은 바꾸지 않는다
        self.assertIsNone(steps[1]["rcp_step_image_url"])                        # 빈 URL → 속성 생략

    def test_invalid_steps_are_rejected(self):
        cases = (
            ("orphan", {"rcp_id": "missing"}),
            ("range", {"step_no": 21}),
            ("range", {"step_no": True}),
            ("instruction", {"rcp_step_instruction_txt": "  "}),
        )
        for message, change in cases:
            with self.subTest(change=change):
                snapshot = sample_snapshot()
                snapshot.steps[0].update(change)
                with self.assertRaisesRegex(ValueError, message):
                    self.prepare(snapshot)
        snapshot = sample_snapshot()
        snapshot.steps.append(snapshot.steps[0].copy())
        with self.assertRaisesRegex(ValueError, "Duplicate key in rcp_step"):
            self.prepare(snapshot)

    def test_step_column_type_change_is_rejected(self):
        snapshot = sample_snapshot()
        snapshot.column_types[("rcp_step", "step_no")] = ("integer", True)
        with self.assertRaisesRegex(ValueError, "rcp_step.step_no"):
            self.prepare(snapshot)


class StepAdditionPreflightTests(unittest.TestCase):
    """조리 단계가 없는 현재 그래프에 단계만 추가 적재할 수 있는지(쓰기 없이 Mock으로) 확인한다."""

    def graph(self, step_rows=()):
        rows = {
            "rcp_cat": [{"rcp_cat_id": "cat"}, {"rcp_cat_id": "cat2"}], "ingr": [{"ingr_id": "i1"}],
            "rcp": [{"rcp_id": "r1", "rcp_seq": "28"}],
            "RCP_IN_RECIPE_CATEGORY": [{"rcp_id": "r1", "rcp_cat_id": "cat"}, {"rcp_id": "r1", "rcp_cat_id": "cat2"}],
            "RCP_USES": [{"rcp_id": "r1", "ingr_id": "i1"}],
            "rcp_step": list(step_rows), "RCP_HAS_STEP": list(step_rows),
        }
        graph = Mock()
        graph.inspect.return_value = {"unknown_labels": [], "unknown_relationships": [], "total_nodes": 4,
                                      "total_relationships": 3, "constraints": [], "indexes": []}
        graph.project_rows.return_value = rows
        graph.project_counts.return_value = {name: len(items) for name, items in rows.items()}
        return graph

    def service(self, graph):
        return RecipeGraphLoadService(Mock(read_snapshot=Mock(return_value=sample_snapshot())), graph)

    def test_existing_graph_without_steps_passes_preflight(self):
        service = self.service(self.graph())
        service.preflight_graph(service.prepare())

    def test_step_absent_from_source_blocks_load(self):
        service = self.service(self.graph([{"rcp_id": "r1", "step_no": 9}]))
        with self.assertRaisesRegex(ValueError, "Existing rcp_step keys differ"):
            service.preflight_graph(service.prepare())

    def test_verify_requires_loaded_steps_and_owner_check(self):
        steps = [{"rcp_id": "r1", "step_no": 1}, {"rcp_id": "r1", "step_no": 3}]
        graph = self.graph(steps)
        graph.validation_count.side_effect = lambda name: 0
        service = self.service(graph)
        verified = service.verify(service.prepare())
        self.assertEqual((verified["rcp_step"], verified["RCP_HAS_STEP"]), (2, 2))
        self.assertEqual(verified["total_project_nodes"], 2 + 1 + 1 + 2)
        self.assertEqual(verified["total_project_relationships"], 2 + 1 + 2)
        graph.validation_count.side_effect = lambda name: 1 if name == "step_link_errors" else 0
        with self.assertRaisesRegex(ValueError, "owning recipe"):
            service.verify(service.prepare())
        with self.assertRaisesRegex(ValueError, "rcp_step"):
            self.service(self.graph()).verify(service.prepare())               # 단계 미적재 그래프는 검증 실패

    def test_steps_stage_runs_last_with_parent_check(self):
        self.assertEqual(STAGES[-1], ("load_recipe_steps", "steps", "check_recipe_step_batch_matches"))
        graph = self.graph()
        graph.inspect.side_effect = [graph.inspect.return_value, {
            **graph.inspect.return_value,
            "constraints": [{"name": name, "type": kind, "labelsOrTypes": labels, "properties": props}
                            for name, (kind, labels, props) in EXPECTED_SCHEMA.items()],
            "indexes": [{"name": name, "type": kind, "labelsOrTypes": labels, "properties": props,
                         "owningConstraint": None} for name, (kind, labels, props) in EXPECTED_INDEXES.items()],
        }]
        service = self.service(graph)
        with patch.object(service, "verify", return_value={}):
            report = service.apply(service.prepare())
        calls = [call.args for call in graph.write_batch.call_args_list]
        self.assertEqual(calls[-1][0], "load_recipe_steps")
        self.assertEqual(calls[-1][2], "check_recipe_step_batch_matches")
        self.assertEqual([row["step_no"] for row in calls[-1][1]], [1, 3])
        self.assertEqual(report["completed"]["load_recipe_steps"], 2)


class SearchScenarioTests(unittest.TestCase):
    """식재료 검색 질의 결과를 스냅샷 기대값과 비교하는 검증 로직(그래프는 Mock)."""

    def snapshot(self):
        snapshot = sample_snapshot()
        snapshot.ingredients.extend([{"ingr_id": "i2", "ingr_nm": "두부"}, {"ingr_id": "i3", "ingr_nm": "양파"}])
        snapshot.recipes.append({**snapshot.recipes[0], "rcp_id": "r2", "rcp_seq": "29"})
        snapshot.recipe_category_links.append({"rcp_id": "r2", "rcp_cat_id": "cat"})
        snapshot.raw_refs.append({"rcp_raw_id": "raw1", "rcp_seq": "29"})
        snapshot.uses.extend([{"rcp_id": "r1", "ingr_id": "i2", "rcp_raw_id": "raw1"},
                              {"rcp_id": "r2", "ingr_id": "i2", "rcp_raw_id": "raw1"},
                              {"rcp_id": "r2", "ingr_id": "i3", "rcp_raw_id": "raw1"}])
        return snapshot

    def graph_answers(self, wrong_alias=False):
        def query(name, params):
            if name == "recipes_by_ingredient_term":
                table = {"eggs": [("i1", "egg", "r1")], "두부": [("i2", "두부", "r1"), ("i2", "두부", "r2")],
                         "양파": [("i3", "양파", "r2")]}
                rows = table.get(params["term_norm"], [])
                if wrong_alias and params["term_norm"] == "eggs":
                    rows = []
                return [{"ingr_id": i, "ingredient": n, "rcp_id": r} for i, n, r in rows]
            if name == "recipes_with_all_ingredients":
                return [{"rcp_id": "r1", "rcp_nm": "recipe"}]
            if name == "pantry_recommendations":
                return [{"rcp_id": "r1", "rcp_nm": "recipe", "matched_count": 2, "missing_count": 0},
                        {"rcp_id": "r2", "rcp_nm": "recipe", "matched_count": 2, "missing_count": 0}]
            if name == "recipes_in_category":
                return [{"rcp_id": "r1"}, {"rcp_id": "r2"}]
            raise AssertionError(name)
        return Mock(query_example=Mock(side_effect=query))

    def run_scenarios(self, graph):
        service = RecipeGraphLoadService(Mock(read_snapshot=Mock(return_value=self.snapshot())), graph)
        return service.verify_search_scenarios(service.prepare(), pantry_terms=("eggs", "두부", "양파"),
                                               both_terms=("eggs", "두부"), category_name="category")

    def test_alias_resolves_to_standard_ingredient(self):
        results = self.run_scenarios(self.graph_answers())
        self.assertEqual(results["by_term:eggs"], {"ingredients": ["egg"], "recipes": 1})   # 별칭 → 표준명
        self.assertEqual(results["all:eggs+두부"]["recipes"], 1)
        self.assertEqual(results["category:category"], {"recipes": 2})

    def test_alias_search_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Ingredient search mismatch"):
            self.run_scenarios(self.graph_answers(wrong_alias=True))


class RepositoryTests(unittest.TestCase):
    @staticmethod
    @contextmanager
    def transaction():
        yield

    def test_validation_queries_use_named_mapper(self):
        repository = RecipeGraphRepository(driver=Mock(), database="neo4j")
        package_dir = Path(__file__).resolve().parents[1]
        self.assertEqual(repository.mapper.mapper_root, package_dir)
        self.assertEqual(len(repository.mapper.mappers), 55)
        self.assertEqual({path.parent for path in repository.mapper.mapper_paths.values()}, {package_dir})
        self.assertEqual(
            {namespace: sum(key.startswith(namespace + ".") for key in repository.mapper.mappers)
             for namespace in (
                 "graph_questions", "pantry_graphrag", "recipe_graph_constraints", "recipe_graph_load",
                 "recipe_graph_queries", "recipe_graph_validation",
             )},
            {"graph_questions": 4, "pantry_graphrag": 2, "recipe_graph_constraints": 7, "recipe_graph_load": 9,
             "recipe_graph_queries": 12, "recipe_graph_validation": 21},
        )
        for name in SCHEMA_NAMES:
            self.assertIn(f"recipe_graph_constraints.{name}", repository.mapper.mappers)
        for statement, _, check in STAGES:
            self.assertIn(f"recipe_graph_load.{statement}", repository.mapper.mappers)
            if check:
                self.assertIn(f"recipe_graph_load.{check}", repository.mapper.mappers)
        self.assertIn("recipe_graph_validation.project_counts", repository.mapper.mappers)
        self.assertIn("recipe_graph_validation.sample_recipe", repository.mapper.mappers)
        self.assertIn("recipe_graph_load.link_uses", repository.mapper.mappers)
        for name in ("recipe_step_keys", "recipe_step_links", "step_link_errors"):
            self.assertIn(f"recipe_graph_validation.{name}", repository.mapper.mappers)
        self.assertIn("recipe_graph_queries.recipe_steps", repository.mapper.mappers)

    def test_project_counts_calls_named_mapper(self):
        repository = object.__new__(RecipeGraphRepository)
        repository.mapper = Mock()
        repository.mapper.select_one.return_value = {"rcp": 1156}
        self.assertEqual(repository.project_counts(), {"rcp": 1156})
        repository.mapper.select_one.assert_called_once_with("recipe_graph_validation.project_counts")

    def test_load_explain_uses_named_statements_without_writes(self):
        repository = object.__new__(RecipeGraphRepository)
        repository.database = "neo4j"
        repository.mapper = Mock()
        repository.mapper._query.return_value = "RETURN 1"
        repository.driver = MagicMock()
        session = repository.driver.session.return_value.__enter__.return_value
        tx = MagicMock()
        session.execute_read.side_effect = lambda callback: callback(tx)
        self.assertEqual(repository.explain_load_statements(), 9)
        self.assertEqual(repository.mapper._query.call_count, 9)
        self.assertEqual(tx.run.call_count, 9)
        self.assertTrue(all(call.args[0] == "EXPLAIN\nRETURN 1" for call in tx.run.call_args_list))
        repository.mapper.execute.assert_not_called()

    def test_parent_mismatch_blocks_write(self):
        repository = object.__new__(RecipeGraphRepository)
        repository.mapper = Mock()
        repository.mapper.transaction.side_effect = self.transaction
        repository.mapper.select_one.return_value = {"input_rows": 1, "matched_rows": 0}
        with self.assertRaisesRegex(ValueError, "Parent match failure"):
            repository.write_batch("link_uses", [{"x": 1}], "check_uses_batch_matches")
        repository.mapper.execute.assert_not_called()

    def test_matching_parent_writes_once(self):
        repository = object.__new__(RecipeGraphRepository)
        repository.mapper = Mock()
        repository.mapper.transaction.side_effect = self.transaction
        repository.mapper.select_one.return_value = {"input_rows": 1, "matched_rows": 1}
        repository.write_batch("link_uses", [{"x": 1}], "check_uses_batch_matches")
        repository.mapper.execute.assert_called_once()

    def test_category_parent_mismatch_blocks_write(self):
        for statement, check in (
            ("link_recipe_categories", "check_recipe_category_batch_matches"),
        ):
            with self.subTest(statement=statement):
                repository = object.__new__(RecipeGraphRepository)
                repository.mapper = Mock()
                repository.mapper.transaction.side_effect = self.transaction
                repository.mapper.select_one.return_value = {"input_rows": 1, "matched_rows": 0}
                with self.assertRaisesRegex(ValueError, "Parent match failure"):
                    repository.write_batch(statement, [{"x": 1}], check)
                repository.mapper.execute.assert_not_called()

    def test_schema_name_conflict_rejected(self):
        service = RecipeGraphLoadService(Mock(), Mock())
        inspection = {
            "constraints": [{"name": "rcp_key", "type": "NODE_PROPERTY_UNIQUENESS",
                             "labelsOrTypes": ["Other"], "properties": ["x"]}],
            "indexes": [],
        }
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            service._check_schema_names(inspection, require_all=False)

    def test_legacy_graph_schema_blocks_load(self):
        service = RecipeGraphLoadService(Mock(), Mock())
        inspection = {
            "constraints": [{"name": "rcp_recipe_composite_key", "type": "NODE_PROPERTY_UNIQUENESS",
                             "labelsOrTypes": ["RcpRecipe"], "properties": ["rcp_cat_id", "rcp_id"]}],
            "indexes": [],
        }
        with self.assertRaisesRegex(ValueError, "Legacy"):
            service._check_schema_names(inspection, require_all=False)

    def test_old_rcp_label_schema_blocks_load(self):
        service = RecipeGraphLoadService(Mock(), Mock())
        inspection = {
            "constraints": [{"name": "rcp_recipe_key", "type": "NODE_PROPERTY_UNIQUENESS",
                             "labelsOrTypes": ["RcpRecipe"], "properties": ["rcp_id"]}],
            "indexes": [],
        }
        with self.assertRaisesRegex(ValueError, "Legacy"):
            service._check_schema_names(inspection, require_all=False)


@unittest.skipUnless(os.getenv("DB_URL"), "DB_URL is not configured")
class LiveStepSourceTests(unittest.TestCase):
    """실제 PostgreSQL을 READ ONLY 트랜잭션으로 읽어 조리 단계 적재 입력을 만든다(Neo4j 미사용, 쓰기 없음)."""

    def test_rcp_step_source_prepares_without_writes(self):
        from recipe_recommender.setup.recipe_graph_source_repository import RecipeGraphSourceRepository

        prepared = RecipeGraphLoadService(RecipeGraphSourceRepository(), Mock()).prepare()
        steps = prepared.stages["steps"]
        self.assertEqual(prepared.expected_counts["rcp_step"], len(prepared.source.steps))
        self.assertGreater(len(steps), 0)
        self.assertEqual(steps, sorted(steps, key=lambda row: (row["rcp_id"], row["step_no"])))
        recipe = next(row for row in prepared.source.recipes if row["rcp_seq"] == "28")
        numbers = [row["step_no"] for row in steps if row["rcp_id"] == recipe["rcp_id"]]
        self.assertTrue(numbers)
        self.assertEqual(numbers, sorted(numbers))


class Neo4jTlsSettingsTests(unittest.TestCase):
    """neo4j+s는 검증 TLS를 유지한 채 신뢰 CA 번들만 명시한다(네트워크 접속 없음)."""

    def test_verified_scheme_keeps_encryption_with_custom_ca(self):
        from neo4j import TrustCustomCAs
        from recipe_recommender.neo4j_connection import driver_arguments

        uri, settings = driver_arguments("neo4j+s://abc.databases.neo4j.io")
        self.assertEqual(uri, "neo4j://abc.databases.neo4j.io")
        self.assertIs(settings["encrypted"], True)
        self.assertIsInstance(settings["trusted_certificates"], TrustCustomCAs)
        self.assertEqual(driver_arguments("bolt+s://h:7687")[0], "bolt://h:7687")

    def test_unverified_scheme_is_rejected_and_local_uri_unchanged(self):
        from recipe_recommender.neo4j_connection import driver_arguments

        for uri in ("neo4j+ssc://h", "bolt+ssc://h"):
            with self.subTest(uri=uri), self.assertRaisesRegex(ValueError, "verification"):
                driver_arguments(uri)
        self.assertEqual(driver_arguments("neo4j://localhost:7687"), ("neo4j://localhost:7687", {}))

    def test_configured_ca_file_must_exist(self):
        from recipe_recommender.neo4j_connection import CA_FILE_ENV_NAME, trusted_ca_file

        with patch.dict("os.environ", {CA_FILE_ENV_NAME: "Z:/no/such/ca.pem"}):
            with self.assertRaises(FileNotFoundError):
                trusted_ca_file()
        with patch.dict("os.environ", {CA_FILE_ENV_NAME: ""}):
            self.assertTrue(Path(trusted_ca_file()).is_file())        # 기본: certifi 번들


class CliTests(unittest.TestCase):
    def test_default_is_dry_run(self):
        with patch("recipe_recommender.setup.load_recipe_graph.RecipeGraphRepository") as graph_type, \
             patch("recipe_recommender.setup.load_recipe_graph.RecipeGraphSourceRepository"), \
             patch("recipe_recommender.setup.load_recipe_graph.RecipeGraphLoadService") as service_type:
            service = service_type.return_value
            prepared = sample_snapshot()
            service.prepare.return_value = Mock(source=prepared, expected_counts=prepared.counts)
            service.preflight_graph.return_value = {
                "database": "test", "version": {}, "total_nodes": 0,
                "total_relationships": 0, "constraints": [], "indexes": [],
            }
            from recipe_recommender.setup.load_recipe_graph import main
            with patch("sys.stdout", new_callable=StringIO):
                self.assertEqual(main([]), 0)
            service.apply.assert_not_called()
            graph_type.return_value.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
