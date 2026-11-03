"""V7 SQL 파일의 구조 계약을 DB 없이 검사한다. 실제 이관 검증은 db_pipeline_v7_integrity_test.sql이 맡는다."""
import re
import unittest
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
CALC_GROUPS = {"PREDICATE_STATE", "PREDICATE_METHOD", "RULE_SELECT", "LIMIT_PERIOD", "LIMIT_UNIT", "LIMIT_SCOPE", "LIMIT_AGG",
               "POOL_ROLE", "CALC_METHOD", "PAYOUT_UNIT"}      # 2026-11-03 계산 구조 정리로 삭제한 공통코드 그룹


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

    def test_card_doc_has_no_product_key_and_dbml_uses_product_doc_relation(self):
        table = self.ddl.split("CREATE TABLE db_pipeline.card_doc (", 1)[1].split("\n);", 1)[0]
        self.assertNotRegex(table, r"(?m)^\s*card_id\s+")
        dbml = read("db_pipeline_schemaV7_draft.dbml")
        self.assertNotIn("Ref: db_pipeline.card_product.card_id < db_pipeline.card_doc.card_id", dbml)
        self.assertIn("Ref: db_pipeline.card_doc.card_doc_id < db_pipeline.card_product_doc.card_doc_id", dbml)

    def test_drop_migration_replaces_obsolete_view_gate_without_cascade(self):
        migration = read("db_pipeline_migration_v7_drop_card_doc_card_id.sql")
        self.assertIn("CREATE OR REPLACE VIEW db_pipeline.v_card_integrity_issue", migration)
        self.assertIn("DROP COLUMN IF EXISTS card_id", migration)
        self.assertNotRegex(migration, r"(?i)DROP\s+COLUMN\s+card_id\s+CASCADE")

    def test_method_catalog_is_gone(self):
        for token in ("card_method_catalog", "method_not_in_catalog", "catalog_method_not_in_code", "handler_key", "param_schema"):
            self.assertNotIn(token, self.ddl, token)

    def test_calc_structure_is_gone_and_value_unit_stays(self):
        """2026-11-03 계산 구조 정리: 계산 실행용 키·열·게이트·함수·제외 사전·정제본이 없다(주석 제외)."""
        code = re.sub(r"--[^\n]*", "", self.ddl)
        for token in ("calc_method_cd", "payout_unit_cd", "method_ver", "basis_amt", "calc_params", "rule_priority",
                      "predicate_state_cd", "predicate_method", "cond_params", "link_role_cd", "rule_select_cd",
                      "card_excl_item", "fn_cond_spend_bound", "spend_min_amt", "v_card_bnft_rule_effective",
                      "rule_value_gap", "predicate_param_gap", "rule_method_value_", "predicate_params_", "excl_item_unknown",
                      "stg_normalized_item"):
            self.assertNotIn(token, code, token)
        rule_view = code.split("CREATE VIEW db_pipeline.v_card_rule AS", 1)[1].split(";", 1)[0]
        for col in ("value_num", "value_unit_cd", "target_list", "cond_expr", "rule_status_cd"):
            self.assertIn(f"AS {col}", rule_view, col)
        self.assertIn("'card_bnft.rule_list[].value_unit_cd', 'VALUE_UNIT'", code)

    def test_extraction_stage_keeps_raw_item_and_approval_check_without_normalized_copy(self):
        stg = self.ddl.split("CREATE TABLE db_pipeline.card_extr_stg (", 1)[1].split("\n);", 1)[0]
        self.assertIn("stg_raw_item jsonb NOT NULL,", stg)
        self.assertIn("stg_parent_card_extr_stg_id character varying(20),", stg)
        self.assertIn("CONSTRAINT card_extr_stg_check1 CHECK ((((stg_status)::text <> ALL ((ARRAY['AUTO_APPROVED'::character varying, "
                      "'MANUAL_APPROVED'::character varying])::text[])) OR ((NOT ((stg_sql_check_cd)::text IS DISTINCT FROM 'OK'::text))", stg)

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
                    "PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id)",
                    "UNIQUE (card_id, evidence_link_id)"):
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
                              "product_doc_role_type_mismatch", "stg_card_not_linked"}, gates)
        self.assertNotIn("shared_doc_bound_to_card", gates)
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
        # 2026-11-03 계산 구조 정리로 10그룹·32코드를 더 뺐다(V7 41그룹·154코드 → 31그룹·122코드).
        self.assertEqual((len(v6), len(v7), len(groups)), (162, 122, 31))
        removed = {tuple(re.findall(r"'([^']*)'", row)[:2]) for row in set(v6) - set(v7)}
        added = {tuple(re.findall(r"'([^']*)'", row)[:2]) for row in set(v7) - set(v6)}
        calc = {key for key in removed if key[0] in CALC_GROUPS}
        self.assertEqual(len(calc), 32)
        self.assertEqual(removed - calc, {("EV_SUBJECT", "POLICY"), ("BNFT_ORIGIN", "LOCAL"), ("BNFT_ORIGIN", "COMMON_LINK"),
                                          ("POLICY_STATUS", "DRAFT"), ("POLICY_STATUS", "APPROVED"), ("POLICY_STATUS", "RETIRED"),
                                          ("EV_ITEM", "LIMIT"), ("METHOD_KIND", "CALC"), ("METHOD_KIND", "PREDICATE"),
                                          ("METHOD_STATUS", "ACTIVE"), ("METHOD_STATUS", "UNEXECUTABLE")})
        self.assertFalse({re.findall(r"'([^']*)'", row)[0] for row in groups} & CALC_GROUPS)
        self.assertEqual(added, {("EV_SUBJECT", "CARD"), ("BNFT_ORIGIN", "LOCAL"), ("BNFT_ORIGIN", "BRAND_SERVICE")})

    def test_descriptions_match_the_codes_and_two_codes_stay_held(self):
        text = read("db_pipeline_common_code_descV7.sql")
        groups = rows_of(text, "tmp_common_code_grp_desc")
        codes = rows_of(text, "tmp_common_cd_desc")
        self.assertEqual((len(groups), len(codes)), (31, 120))
        keys = {tuple(re.findall(r"'([^']*)'", row)[:2]) for row in codes}
        self.assertNotIn(("REL_TYPE", "OVERRIDES"), keys)
        self.assertNotIn(("SERVICE_GRADE", "PRESTIGE"), keys)
        self.assertLessEqual({("EV_SUBJECT", "CARD"), ("BNFT_ORIGIN", "BRAND_SERVICE")}, keys)
        self.assertNotIn("POLICY_STATUS", text.split("BEGIN;", 1)[1])
        self.assertNotIn("card_method_catalog", text)
        body = text.split("BEGIN;", 1)[1]
        self.assertFalse({key[0] for key in keys} & CALC_GROUPS)
        for token in sorted(CALC_GROUPS) + ["card_excl_item_id", "stg_normalized_item", "predicate_method_cd"]:
            self.assertNotIn(token, body, token)
        self.assertLessEqual({("VALUE_UNIT", "PERCENT"), ("VALUE_UNIT", "KRW")}, keys)


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
        removed = ("predicate_", "cond_params", "card_excl_item_id", "link_role_cd", "rule_select_cd", "calc_method_cd", "payout_unit_cd")
        for name in ("v_card_bnft_rel", "v_card_cond_atom", "v_common_cd_usage"):
            pattern = rf"CREATE VIEW db_pipeline\.{name} AS\n.*?;\n\nCOMMENT ON VIEW"
            expected = re.search(pattern, self.forward, re.S).group(0)
            # 이후 계산 구조 정리(2026-11-03)가 지운 열·코드 사용처 가지만 빼면 같아야 한다
            expected = "\nUNION ALL\n".join(b for b in expected.split("\nUNION ALL\n") if name != "v_common_cd_usage" or not any(t in b for t in removed))
            expected = "\n".join(line for line in expected.split("\n") if name != "v_card_cond_atom" or not any(t in line for t in removed))
            self.assertEqual(re.search(pattern, ddl, re.S).group(0), expected, name)
        self.assertIn("shared_doc_bound_to_card", self.forward)
        self.assertNotIn("shared_doc_bound_to_card", ddl)

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
