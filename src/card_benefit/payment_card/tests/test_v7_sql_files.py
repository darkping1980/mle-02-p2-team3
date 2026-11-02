"""V7 SQL 파일의 구조 계약을 DB 없이 검사한다. 실제 이관 검증은 db_pipeline_v7_integrity_test.sql이 맡는다."""
import re
import unittest
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"


def read(name: str) -> str:
    return (SQL_DIR / name).read_text(encoding="utf-8")


def rows_of(text: str, table: str) -> list[str]:
    """``INSERT INTO <table>`` 뒤 VALUES 목록의 행을 돌려준다."""
    block = text.split(f"INSERT INTO {table}", 1)[1].split(";\n", 1)[0]
    return re.findall(r"^    \((.*)\)[,]?$", block, flags=re.M)


class SchemaV7Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ddl = read("db_pipeline_schemaV7_draft.sql")

    def test_policy_version_layer_is_gone(self):
        for token in ("policy_ver_id", "card_policy_version", "card_policy_evidence", "v_card_policy_doc",
                      "policy_cond_expr", "source_doc_list", "fn_valid_doc_ref_list", "seq_card_policy_version"):
            self.assertNotIn(token, self.ddl, token)

    def test_common_benefit_tables_are_gone(self):
        for token in ("card_common_", "card_bnft_common", "common_bnft_id", "common_ver_id", "COMMON_LINK",
                      "fn_valid_limit_list", "v_card_common_", "limit_list"):
            self.assertNotIn(token, self.ddl, token)

    def test_method_catalog_is_gone_and_versions_stay_as_representation_contract(self):
        for token in ("card_method_catalog", "method_not_in_catalog", "catalog_method_not_in_code", "handler_key", "param_schema"):
            self.assertNotIn(token, self.ddl, token)
        self.assertIn("method_ver and predicate_method_ver are representation contract versions, currently 1.", self.ddl)
        self.assertIn("(v_rule->>'method_ver')::integer < 1", self.ddl)

    def test_method_gates_do_not_force_a_payout_unit_or_params_on_every_method(self):
        rule_gap = self.ddl.split("rule_value_gap AS (", 1)[1].split("predicate_param_gap AS (", 1)[0]
        param_gap = self.ddl.split("predicate_param_gap AS (", 1)[1].split("fallback AS (", 1)[0]
        self.assertNotIn("'KRW'", rule_gap)
        self.assertNotIn("payout_unit_cd", rule_gap)
        self.assertIn("r.value_unit_cd IN ('PERCENT', 'MULTIPLIER')", rule_gap)
        self.assertIn("a.predicate_method_cd = 'EVERY_MONTH_MIN_SPEND'", param_gap)
        self.assertIn("a.predicate_method_cd = 'MONTH_IN'", param_gap)
        self.assertNotIn("a.predicate_method_cd IS NOT NULL", param_gap)

    def test_pending_and_final_gaps_have_different_gate_codes(self):
        for gate in ("rule_method_value_missing", "rule_method_value_pending", "predicate_params_missing", "predicate_params_pending"):
            self.assertIn(gate, self.ddl)

    def test_rule_validator_keeps_signature_used_by_the_extraction_mapper(self):
        self.assertIn("CREATE FUNCTION db_pipeline.fn_valid_rule_list(p_list jsonb, p_owner text)", self.ddl)
        self.assertIn("fn_valid_rule_list(rule_list, 'LOCAL')", self.ddl)

    def test_extraction_candidate_may_have_no_card_but_final_benefit_must(self):
        stg = self.ddl.split("CREATE TABLE db_pipeline.card_extr_stg (", 1)[1].split("\n);", 1)[0]
        bnft = self.ddl.split("CREATE TABLE db_pipeline.card_bnft (", 1)[1].split("\n);", 1)[0]
        self.assertRegex(stg, r"\n    card_id bigint,\n")
        self.assertRegex(bnft, r"\n    card_id bigint NOT NULL,\n")

    def test_brand_benefit_needs_brand_scope_and_period_is_optional(self):
        self.assertIn("CHECK (bnft_origin_cd <> 'BRAND_SERVICE' OR bnft_scope_cd = 'BRAND')", self.ddl)
        self.assertIn("bnft_valid_from date,", self.ddl)
        self.assertIn("bnft_valid_to_excl date,", self.ddl)

    def test_keys_attach_directly_to_card(self):
        for key in ("PRIMARY KEY (card_id, card_bnft_id)", "UNIQUE (card_id, bnft_cd)",
                    "PRIMARY KEY (card_id, ev_link_id)"):
            self.assertIn(key, self.ddl)

    def test_card_condition_reuses_condition_contract(self):
        self.assertIn("card_cond_expr jsonb,", self.ddl)
        self.assertIn("card_cond_status_cd varchar(20) NOT NULL DEFAULT 'DRAFT'", self.ddl)
        self.assertIn("CHECK (db_pipeline.fn_valid_cond_expr(card_cond_expr))", self.ddl)
        self.assertIn("'card_product.card_cond_status_cd'::text AS source_nm, 'ITEM_STATUS'", self.ddl)

    def test_product_doc_keeps_basis_check_without_period(self):
        table = self.ddl.split("CREATE TABLE db_pipeline.card_product_doc (", 1)[1].split("\n);", 1)[0]
        self.assertNotIn("effective_", self.ddl)
        self.assertEqual(len(re.findall(r"^    (?!CONSTRAINT|\()\w+ ", table, flags=re.M)), 11)
        self.assertIn("(approval_status_cd <> 'APPROVED' OR length(trim(applicability_basis_txt)) > 0)", table)
        self.assertIn("card_product_doc_brand_check", table)

    def test_evidence_subject_uses_card(self):
        self.assertIn("WHEN 'CARD' THEN num_nonnulls(card_bnft_id, rule_key, relation_key) = 0", self.ddl)
        self.assertNotIn("'POLICY'", self.ddl)

    def test_limit_pool_structure_is_gone_and_text_stays_on_benefit(self):
        for token in ("card_limit_pool", "card_bnft_rule_pool", "v_card_limit_tier", "v_card_rule_pool", "fn_valid_tier_list",
                      "tier_list", "POOL_TIER", "'POOL'", "'TIER'", "s.pool_id", "item_key,\n"):
            self.assertNotIn(token, self.ddl.replace("ev_item_key,\n", ""), token)
        self.assertIn("bnft_rule_txt text,", self.ddl)
        self.assertIn("bnft_limit_txt text,", self.ddl)

    def test_relation_contract_rejects_pool_reference(self):
        self.assertIn("OR v_rel ? 'trigger_pool_id' THEN", self.ddl)
        self.assertNotIn("x.value->>'trigger_pool_id'", self.ddl)

    def test_replaced_gates_exist_and_removed_gates_are_only_the_policy_ones(self):
        gates = set(re.findall(r"^SELECT '(\w+)'(?: AS gate_cd)?,", self.ddl.split("CREATE VIEW db_pipeline.v_card_integrity_issue", 1)[1], flags=re.M))
        self.assertLessEqual({"bnft_without_product", "bnft_txt_without_evidence", "product_doc_without_product",
                              "product_doc_orphan", "evidence_doc_not_linked", "evidence_not_approved",
                              "evidence_subject_orphan", "evidence_item_key_missing", "common_cd_invalid",
                              "brand_bnft_doc_not_linked", "brand_bnft_confirmed_without_evidence",
                              "evidence_brand_opt_mismatch", "brand_doc_option_conflict",
                              "product_doc_role_type_mismatch", "shared_doc_bound_to_card", "stg_card_not_linked"}, gates)
        self.assertFalse(gates & {"policy_without_product", "bnft_without_policy", "pool_without_policy",
                                  "policy_period_overlap", "policy_doc_orphan", "pool_without_product", "pool_ref_orphan",
                                  "rule_pool_product_orphan", "rule_pool_benefit_orphan", "rule_pool_rule_orphan",
                                  "rel_trigger_pool_orphan"})

    def test_common_code_description_columns_are_kept(self):
        self.assertIn("common_code_grp_desc text,", self.ddl)
        self.assertIn("common_cd_desc text,", self.ddl)


class CommonCodeV7Tests(unittest.TestCase):
    def test_seed_changes_only_the_listed_codes(self):
        v6 = rows_of(read("db_pipeline_common_code_seedV6.sql"), "db_pipeline.common_cd")
        v7 = rows_of(read("db_pipeline_common_code_seedV7.sql"), "db_pipeline.common_cd")
        groups = rows_of(read("db_pipeline_common_code_seedV7.sql"), "db_pipeline.common_code_grp")
        self.assertEqual((len(v6), len(v7), len(groups)), (162, 154, 41))
        removed = {tuple(re.findall(r"'([^']*)'", row)[:2]) for row in set(v6) - set(v7)}
        added = {tuple(re.findall(r"'([^']*)'", row)[:2]) for row in set(v7) - set(v6)}
        self.assertEqual(removed, {("EV_SUBJECT", "POLICY"), ("BNFT_ORIGIN", "LOCAL"), ("BNFT_ORIGIN", "COMMON_LINK"),
                                   ("POLICY_STATUS", "DRAFT"), ("POLICY_STATUS", "APPROVED"), ("POLICY_STATUS", "RETIRED"),
                                   ("EV_ITEM", "LIMIT"), ("METHOD_KIND", "CALC"), ("METHOD_KIND", "PREDICATE"),
                                   ("METHOD_STATUS", "ACTIVE"), ("METHOD_STATUS", "UNEXECUTABLE")})
        self.assertEqual(added, {("EV_SUBJECT", "CARD"), ("BNFT_ORIGIN", "LOCAL"), ("BNFT_ORIGIN", "BRAND_SERVICE")})

    def test_descriptions_match_the_codes_and_two_codes_stay_held(self):
        text = read("db_pipeline_common_code_descV7.sql")
        groups = rows_of(text, "tmp_common_code_grp_desc")
        codes = rows_of(text, "tmp_common_cd_desc")
        self.assertEqual((len(groups), len(codes)), (41, 152))
        keys = {tuple(re.findall(r"'([^']*)'", row)[:2]) for row in codes}
        self.assertNotIn(("REL_TYPE", "OVERRIDES"), keys)
        self.assertNotIn(("SERVICE_GRADE", "PRESTIGE"), keys)
        self.assertLessEqual({("EV_SUBJECT", "CARD"), ("BNFT_ORIGIN", "BRAND_SERVICE")}, keys)
        self.assertNotIn("POLICY_STATUS", text.split("BEGIN;", 1)[1])
        self.assertNotIn("card_method_catalog", text)
        self.assertIn("표현 계약 버전", text)
        self.assertLessEqual({("CALC_METHOD", "FIXED_PER_TXN"), ("PREDICATE_METHOD", "MONTH_IN")}, keys)


class MigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = read("db_pipeline_migration_V6_to_V7.sql")

    def test_runs_in_one_transaction(self):
        self.assertEqual(self.migration.count("\nBEGIN;\n"), 1)
        self.assertTrue(self.migration.rstrip().endswith("COMMIT;"))

    def test_multiple_policies_stop_instead_of_merging(self):
        self.assertIn("HAVING count(*) > 1", self.migration)
        self.assertIn("자동 병합하지 않습니다", self.migration)

    def test_common_rows_stop_instead_of_being_deleted(self):
        self.assertIn("공통 혜택 데이터가 있어 삭제하지 않습니다", self.migration)
        guard = self.migration.index("공통 혜택 데이터가 있어 삭제하지 않습니다")
        self.assertLess(guard, self.migration.index("DROP TABLE db_pipeline.card_common_bnft"))

    def test_executable_method_contract_stops_the_migration(self):
        guard = self.migration.index("실행 가능한 방법 계약이 있어 card_method_catalog를 삭제하지 않습니다")
        self.assertLess(guard, self.migration.index("DROP TABLE db_pipeline.card_method_catalog"))

    def test_pending_gaps_do_not_fail_the_migration_but_violations_do(self):
        self.assertIn("gate_cd NOT IN ('evidence_not_approved', 'rule_method_value_pending', 'predicate_params_pending')", self.migration)

    def test_status_is_never_promoted_and_dates_are_not_moved(self):
        self.assertNotRegex(self.migration, r"SET\s+approval_status_cd")
        self.assertNotRegex(self.migration, r"launched_on\s*=")
        self.assertIn("WHEN 'DRAFT' THEN 'DRAFT'", self.migration)

    def test_drop_happens_after_backup_and_data_move(self):
        backup = self.migration.index("CREATE TABLE db_pipeline_v6_backup.card_policy_version")
        moved = self.migration.index("SET card_cond_expr = v.policy_cond_expr")
        dropped = self.migration.index("DROP TABLE db_pipeline.card_policy_version")
        self.assertLess(backup, moved)
        self.assertLess(moved, dropped)


    def test_rollback_restores_policy_table_from_backup(self):
        rollback = read("db_pipeline_migration_V7_to_V6_rollback.sql")
        self.assertIn("INSERT INTO db_pipeline.card_policy_version SELECT * FROM db_pipeline_v6_backup.card_policy_version;", rollback)
        self.assertIn("UPDATE db_pipeline.card_policy_evidence SET ev_subject_cd = 'POLICY' WHERE ev_subject_cd = 'CARD';", rollback)
        self.assertIn("CREATE TABLE db_pipeline.card_common_bnft (", rollback)
        self.assertIn("INSERT INTO db_pipeline.common_cd SELECT * FROM db_pipeline_v6_backup.common_cd;", rollback)
        self.assertIn("V6에 담을 수 없는 카드 미연결 추출 항목이 있습니다", rollback)
        self.assertIn("INSERT INTO db_pipeline.card_method_catalog SELECT * FROM db_pipeline_v6_backup.card_method_catalog;", rollback)


class BnftTextMigrationTests(unittest.TestCase):
    """V6 -> V7 이관 파일은 TEXT 단순화 직전 구조에서 멈춘다. 최종 구조는 이 이관까지 적용한 결과다."""
    @classmethod
    def setUpClass(cls):
        cls.forward = read("db_pipeline_migration_v7_bnft_text.sql")
        cls.rollback = read("db_pipeline_migration_v7_bnft_text_rollback.sql")
        cls.precheck = read("db_pipeline_v7_bnft_text_precheck.sql")
        cls.postcheck = read("db_pipeline_v7_bnft_text_postcheck.sql")

    def test_views_are_the_ddl_definitions(self):
        ddl = read("db_pipeline_schemaV7_draft.sql")
        for name in ("v_card_bnft_rel", "v_card_cond_atom", "v_common_cd_usage", "v_card_integrity_issue"):
            pattern = rf"CREATE VIEW db_pipeline\.{name} AS\n.*?;\n\nCOMMENT ON VIEW"
            self.assertEqual(re.search(pattern, ddl, re.S).group(0), re.search(pattern, self.forward, re.S).group(0))

    def test_no_cascade_and_single_transaction(self):
        for text in (self.forward, self.rollback):
            self.assertNotRegex(text, r"(?i)\bCASCADE\b(?! ?를)")
            self.assertEqual(text.count("\nBEGIN;\n"), 1)
            self.assertTrue(text.rstrip().endswith("COMMIT;"))
            self.assertNotRegex(text, r"(?i)FOREIGN\s+KEY")

    def test_guard_runs_before_anything_is_removed(self):
        guard = self.forward.index("사전 조건 실패로 중단합니다")
        for statement in ("DROP VIEW IF EXISTS", "DELETE FROM db_pipeline.card_evidence_link", "DROP TABLE IF EXISTS db_pipeline.card_limit_pool"):
            self.assertLess(guard, self.forward.index(statement), statement)

    def test_natural_key_keeps_its_name_for_on_conflict(self):
        self.assertIn("ADD CONSTRAINT card_evidence_link_natural_key UNIQUE NULLS NOT DISTINCT", self.forward)

    def test_precheck_and_migration_share_every_check(self):
        codes = set(re.findall(r"^SELECT '([BTEJSOG]\d\d)'", self.precheck, flags=re.M))
        self.assertEqual(len(codes), 21)
        self.assertEqual(codes, set(re.findall(r"^SELECT '([BTEJSOG]\d\d)'", self.forward, flags=re.M)))

    def test_checks_are_read_only_and_safe_for_dbeaver(self):
        for text in (self.precheck, self.postcheck):
            self.assertNotRegex(re.sub(r"--.*", "", text), r"(?i)\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE)\b")
        for text in (self.precheck, self.postcheck, self.forward, self.rollback):
            outside = re.sub(r"\$_?\$.*?\$_?\$", "", re.sub(r"--.*", "", text), flags=re.S)
            self.assertNotIn(" ? ", outside)  # JDBC가 파라미터로 오인한다.


class V6IsPreservedTests(unittest.TestCase):
    def test_v6_keeps_policy_layer_and_description_columns(self):
        ddl = read("db_pipeline_schemaV6_draft.sql")
        self.assertIn("CREATE TABLE db_pipeline.card_policy_version (", ddl)
        self.assertIn("common_cd_desc text,", ddl)


if __name__ == "__main__":
    unittest.main()
