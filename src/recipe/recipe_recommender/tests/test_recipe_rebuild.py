"""목표 모델 재구축 산출물(DDL·이관·검증 SQL·도구) 정적 테스트. DB에 연결하지 않는다."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from recipe_recommender.sql_schema import render_schema_sql, validate_schema_name  # noqa: E402
from recipe_recommender.tools import recipe_rebuild  # noqa: E402
from recipe_recommender.tools.recipe_rebuild import (  # noqa: E402
    BASELINE, LEGACY_PKS, TARGET_PKS, TARGET_SEQUENCES, RebuildError,
)

DDL = recipe_rebuild.TARGET_DDL_PATH.read_text(encoding="utf-8")
MIGRATION = recipe_rebuild.MIGRATION_SQL_PATH.read_text(encoding="utf-8")
VALIDATION = recipe_rebuild.VALIDATION_SQL_PATH.read_text(encoding="utf-8")
_COLUMN = re.compile(r"(?:^\s+|,\s*)([a-z][a-z0-9_]*) (?:varchar|text|numeric|smallint|timestamptz)", re.M)


def statements(sql: str) -> str:
    """주석 줄을 뺀 SQL 본문."""
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def ddl_tables(sql: str = DDL) -> dict[str, dict]:
    """CREATE TABLE 블록별 컬럼 목록과 PK 컬럼."""
    tables = {}
    for match in re.finditer(r"CREATE TABLE recipe\.(\w+) \((.*?)\n\);", sql, re.S):
        body = match.group(2)
        columns = _COLUMN.findall("\n".join(line for line in body.splitlines() if "CONSTRAINT" not in line))
        pk = re.search(r"CONSTRAINT pk_\w+ PRIMARY KEY \(([^)]*)\)", body).group(1)
        tables[match.group(1)] = {"columns": columns, "pk": [c.strip() for c in pk.split(",")]}
    return tables


class SchemaRenderTests(unittest.TestCase):
    def test_qualifiers_and_literals_are_rendered(self):
        sql = "SELECT * FROM recipe.rcp r JOIN recipe_src.rcp s ON true; SELECT to_regclass('recipe.seq_rcp');"
        rendered = render_schema_sql(sql, "recipe_v2", "recipe")
        self.assertEqual(rendered, "SELECT * FROM recipe_v2.rcp r JOIN recipe.rcp s ON true; "
                                   "SELECT to_regclass('recipe_v2.seq_rcp');")

    def test_source_recipe_is_not_rewritten_to_target(self):
        rendered = render_schema_sql(MIGRATION, "recipe_v2", "recipe")
        self.assertIn("FROM recipe.rcp;", rendered)
        self.assertIn("INSERT INTO recipe_v2.rcp (", rendered)
        self.assertNotIn("recipe_src.", statements(rendered))

    def test_non_qualifier_words_are_untouched(self):
        sql = "-- recipe.쿼리이름\nSELECT my_recipe.x, recipe_rcp.y, 'recipe' FROM t"
        self.assertEqual(render_schema_sql(sql, "zz"), sql)

    def test_invalid_names_and_missing_source_rejected(self):
        for name in ("Recipe", "recipe;drop", "pg_temp", "", "1abc"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_schema_name(name)
        with self.assertRaises(ValueError):
            render_schema_sql("SELECT 1 FROM recipe_src.rcp", "recipe_v2")
        with self.assertRaises(ValueError):
            render_schema_sql("SELECT 1 FROM recipe_src.rcp", "recipe_v2", "recipe_v2")


class TargetDdlTests(unittest.TestCase):
    def test_tables_and_primary_keys_match_target(self):
        tables = ddl_tables()
        self.assertEqual({name: item["pk"] for name, item in tables.items()}, TARGET_PKS)

    def test_ingredient_category_is_removed(self):
        body = statements(DDL)
        self.assertNotIn("ingr_cat", body)
        self.assertNotIn("seq_ingr_cat", body)
        for name, item in ddl_tables().items():
            if name not in ("rcp_cat", "rcp_cat_rel"):
                self.assertNotIn("rcp_cat_id", item["columns"], name)

    def test_alias_keeps_id_and_parent_unique_name(self):
        alias = ddl_tables()["ingr_als"]
        self.assertEqual(alias["columns"][:3], ["ingr_id", "ingr_als_id", "ingr_als_nm"])
        self.assertIn("CONSTRAINT uq_ingr_als_ingr_als_nm UNIQUE (ingr_id, ingr_als_nm)", DDL)
        self.assertIn("ingr_als_id varchar(20) NOT NULL DEFAULT recipe.fn_get_biz_id('ingr_als')", DDL)

    def test_sequences_function_and_no_destructive_statement(self):
        self.assertEqual(set(re.findall(r"CREATE SEQUENCE recipe\.(\w+)", DDL)), TARGET_SEQUENCES)
        body = statements(DDL).upper()
        for word in ("DROP ", "TRUNCATE", "DELETE ", "CASCADE", "CREATE SCHEMA", "OR REPLACE"):
            self.assertNotIn(word, body)
        self.assertIn("to_regclass('recipe.seq_' || lower(p_tbl_nm))", DDL)

    def test_every_table_and_column_has_comment(self):
        for table, item in ddl_tables().items():
            self.assertIn(f"COMMENT ON TABLE recipe.{table} IS", DDL)
            for column in item["columns"]:
                with self.subTest(column=f"{table}.{column}"):
                    self.assertIn(f"COMMENT ON COLUMN recipe.{table}.{column} IS", DDL)

    def test_rendered_ddl_has_no_default_schema_left(self):
        rendered = statements(render_schema_sql(DDL, "zz_rebuild_test"))
        self.assertNotRegex(rendered, r"(?<![\w.])recipe\.")
        self.assertIn("to_regclass('zz_rebuild_test.seq_' || lower(p_tbl_nm))", rendered)


class MigrationSqlTests(unittest.TestCase):
    def test_every_target_column_is_copied_explicitly(self):
        tables = ddl_tables()
        inserted = {m.group(1): [c.strip() for c in m.group(2).replace("\n", " ").split(",")]
                    for m in re.finditer(r"INSERT INTO recipe\.(\w+) \((.*?)\)\s*SELECT", MIGRATION, re.S)}
        self.assertEqual(set(inserted), set(tables))
        for table, item in tables.items():
            with self.subTest(table=table):
                self.assertEqual(inserted[table], item["columns"])     # ID 포함 전 컬럼 → DEFAULT 발급 없음

    def test_source_is_only_read(self):
        body = statements(MIGRATION)
        for match in re.finditer(r"(INSERT INTO|UPDATE|DELETE FROM|ALTER TABLE|DROP \w+|TRUNCATE)\s+recipe_src\.", body):
            self.fail(f"source schema is modified: {match.group(0)}")
        self.assertEqual(set(re.findall(r"setval\('recipe\.(\w+)'", MIGRATION)), TARGET_SEQUENCES)

    def test_category_relation_is_built_from_existing_recipe_category(self):
        self.assertRegex(MIGRATION, r"(?s)INSERT INTO recipe\.rcp_cat_rel \(.*?\)\s*SELECT\s+rcp_id, rcp_cat_id,.*?"
                                    r"FROM recipe_src\.rcp;")


class ValidationSqlTests(unittest.TestCase):
    def setUp(self):
        self.names = re.findall(r"\('([a-z_]+)', ", VALIDATION)

    def test_check_names_are_unique_and_baseline_matches(self):
        self.assertEqual(len(self.names), len(set(self.names)))
        self.assertEqual({name for name in self.names if name.startswith("cnt_")}, set(BASELINE))
        self.assertEqual((BASELINE["cnt_rcp"], BASELINE["cnt_ingr"], BASELINE["cnt_rcp_ingr_stg"],
                          BASELINE["cnt_stg_auto_approved"], BASELINE["cnt_rcp_ingr"]), (1156, 275, 13080, 10611, 10428))
        self.assertEqual(BASELINE["cnt_stg_auto_approved"] - BASELINE["cnt_rcp_ingr"], BASELINE["cnt_approved_minus_relation"])

    def test_every_target_table_is_compared_both_ways(self):
        for table in TARGET_PKS:
            with self.subTest(table=table):
                self.assertIn(f"diff_{table}_src_only", self.names)
                self.assertIn(f"diff_{table}_tgt_only", self.names)

    def test_dropped_columns_are_checked_for_information_loss(self):
        for name in ("lost_rcp_step_rcp_cat_id", "lost_rcp_ingr_rcp_cat_id", "lost_rcp_ingr_ingr_cat_id",
                     "lost_ingr_als_ingr_cat_id", "lost_stg_ingr_cat_id", "gap_unexplained", "seq_behind_max_id"):
            self.assertIn(name, self.names)

    def test_validation_is_select_only(self):
        body = statements(VALIDATION).upper()
        for word in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ", "CREATE ", "SETVAL"):
            self.assertNotIn(word, body)


class RebuildToolTests(unittest.TestCase):
    def test_default_command_is_read_only_inspect(self):
        self.assertEqual(recipe_rebuild.parse_args([]).command, "inspect")

    def test_write_requires_matching_database_label(self):
        connection = MagicMock()
        connection.info.host, connection.info.port = "db.example", 5432
        connection.execute.return_value.fetchone.return_value = {
            "dbname": "postgres", "db_user": "u", "server_port": 5432, "server_version": "17"}
        with patch("builtins.print"):
            self.assertEqual(recipe_rebuild.require_confirmed_db(connection, "db.example/postgres")["dbname"], "postgres")
            with self.assertRaises(RebuildError):
                recipe_rebuild.require_confirmed_db(connection, "other/postgres")
            with self.assertRaises(RebuildError):
                recipe_rebuild.require_confirmed_db(connection, None)

    def test_drop_refuses_production_and_unmarked_schemas(self):
        connection = MagicMock()
        for schema, comment in (("recipe", "recipe-rebuild:rehearsal"), ("recipe_v2", None),
                                ("recipe_legacy_x", "recipe-rebuild:legacy:...")):
            with self.subTest(schema=schema), patch.object(recipe_rebuild, "schema_comment", return_value=comment):
                with self.assertRaises(RebuildError):
                    recipe_rebuild.drop_schema(connection, schema)
        connection.transaction.assert_not_called()

    def test_build_refuses_production_target(self):
        with self.assertRaises(RebuildError):
            recipe_rebuild.build(MagicMock(), "recipe", "recipe", baseline=True)

    def test_build_target_refuses_existing_target_before_writing(self):
        connection = MagicMock()
        with patch.object(recipe_rebuild, "check_legacy_source"), \
             patch.object(recipe_rebuild, "schema_exists", return_value=True):
            with self.assertRaises(RebuildError):
                recipe_rebuild.build_target(connection, "recipe", "recipe_v2", baseline=True, marker="rehearsal")
        connection.execute.assert_not_called()

    def test_cutover_requires_valid_backup(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(recipe_rebuild, "schema_exists", return_value=False):
            with self.assertRaises(RebuildError):
                recipe_rebuild.cutover(MagicMock(), "recipe_legacy_test", Path(folder), baseline=True)

    def test_cli_without_confirmation_does_not_write(self):
        with patch.object(recipe_rebuild, "connect") as connect, patch("builtins.print"):
            self.assertEqual(recipe_rebuild.main(["cutover", "--legacy-schema", "recipe_legacy_x",
                                                  "--backup-dir", "x"]), 1)
            self.assertEqual(recipe_rebuild.main(["rollback-cutover", "--legacy-schema", "recipe_legacy_x"]), 1)
        connection = connect.return_value.__enter__.return_value
        connection.transaction.assert_not_called()

    def test_backup_file_verification_detects_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            backup_dir = Path(folder)
            files = {}
            for table in LEGACY_PKS:
                path = backup_dir / f"{table}.csv"
                with path.open("w", encoding="utf-8", newline="") as file:
                    writer = csv.writer(file, quoting=csv.QUOTE_ALL)
                    writer.writerow(["a", "b"])
                    writer.writerow(["1", "줄1\n줄2"])            # 따옴표 안 줄바꿈도 레코드 1개
                files[path.name] = {"table": table, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                    "rows": 1, "md5": "x"}
            (backup_dir / "catalog.json").write_text("{}", encoding="utf-8")
            manifest = {"source_schema": "recipe", "files": files,
                        "catalog_sha256": hashlib.sha256(b"{}").hexdigest()}
            (backup_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(recipe_rebuild.verify_backup_files(backup_dir), [])
            (backup_dir / "rcp.csv").write_text("changed", encoding="utf-8")
            self.assertTrue(recipe_rebuild.verify_backup_files(backup_dir))


class LegacyToolGuardTests(unittest.TestCase):
    def test_legacy_destructive_tools_refuse_confirmation(self):
        from recipe_recommender.tools import rebuild_recipe_schema, reset_recipe_data

        for module, flag in ((rebuild_recipe_schema, "--confirm-rebuild"), (reset_recipe_data, "--confirm-reset")):
            with self.subTest(module=module.__name__), patch.object(module, "run_sql_script") as run, \
                 patch("builtins.print"):
                self.assertEqual(module.main([flag]), 1)
                run.assert_not_called()


class SchemaSelectionTests(unittest.TestCase):
    def test_mapper_copy_targets_requested_schema(self):
        from recipe_recommender.database import _mapper_root_for
        from recipe_recommender.config import PACKAGE_DIR

        self.assertEqual(_mapper_root_for("recipe"), PACKAGE_DIR)
        rendered = (_mapper_root_for("recipe_v2") / "recipe.sql").read_text(encoding="utf-8")
        self.assertNotRegex(statements(rendered), r"(?<![\w.])recipe\.")
        self.assertIn("INSERT INTO recipe_v2.rcp_cat_rel", rendered)
        self.assertIn("to_regclass('recipe_v2.rcp_cat_rel')", rendered)

    def test_register_cli_rehearse_rules(self):
        from recipe_recommender.setup.register_recipe_csv import parse_args

        self.assertTrue(parse_args(["--full", "--rehearse"]).rehearse)
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            parse_args(["--rehearse"])
        with patch("sys.stderr"), self.assertRaises(SystemExit):
            parse_args(["--full", "--rehearse", "--dry-run"])


if __name__ == "__main__":
    unittest.main()
