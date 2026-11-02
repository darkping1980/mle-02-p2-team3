"""연결 테이블 이관 파일 보존과 TEXT 단순화 이후 계약."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2] / 'sql'


def test_rule_pool_structure_is_removed_from_final_ddl():
    ddl = (ROOT / 'db_pipeline_schemaV7_draft.sql').read_text(encoding='utf-8')
    assert 'card_bnft_rule_pool' not in ddl and 'card_limit_pool' not in ddl
    assert not re.search(r'\bFOREIGN\s+KEY\s*\(', ddl, re.I)
    assert "v_rule ? 'pool_refs'" in ddl


def test_v7_migration_and_rollback_preserve_data_and_use_no_foreign_keys():
    forward = (ROOT / 'db_pipeline_migration_v7_rule_pool.sql').read_text(encoding='utf-8')
    rollback = (ROOT / 'db_pipeline_migration_v7_rule_pool_rollback.sql').read_text(encoding='utf-8')
    assert 'EXCEPT ALL' in forward
    assert 'v7_rule_list_before_pool_split' in forward and 'v7_rule_list_before_pool_split' in rollback
    assert not re.search(r'\bFOREIGN\s+KEY\s*\(', forward + rollback, re.I)
    assert 'COMMIT;' in forward and 'COMMIT;' in rollback


def test_runtime_code_has_no_pool_table_reference():
    base = ROOT.parent / 'payment_card'
    names = ('common_benefit_service.py', 'common_benefit_repository.sql', 'neo4j_dry_run.py', 'neo4j_validate.py',
             'neo4j_validation.sql', 'neo4j_validation.cypher')
    files = [base / 'db_pipeline' / name for name in names]
    files += [base / 'db_pipeline_origin_search' / name for name in ('card_graphrag.py', 'neo4j_search.py', 'graph_questions.cypher')]
    for path in files:
        text = path.read_text(encoding='utf-8')
        assert not re.search(r'pool_id|card_limit_pool|card_bnft_rule_pool|df_consumes|df_has_pool|\[.pools.\]', text), path.name


def test_dbml_matches_text_structure():
    dbml = (ROOT / 'db_pipeline_schemaV7_draft.dbml').read_text(encoding='utf-8')
    assert 'Ref lines are logical only; SQL has 0 FKs' in dbml
    assert 'card_bnft_rule_pool' not in dbml and 'card_limit_pool' not in dbml and 'pool_id' not in dbml
    assert "bnft_limit_txt text" in dbml and "bnft_rule_txt text" in dbml
