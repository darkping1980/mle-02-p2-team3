"""연결 테이블과 V6 이관·복구 계약."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2] / 'sql'


def test_rule_pool_has_composite_key_without_fk_or_sequence():
    ddl = (ROOT / 'db_pipeline_schemaV7_draft.sql').read_text(encoding='utf-8')
    table = ddl.split('CREATE TABLE db_pipeline.card_bnft_rule_pool (',1)[1].split('\n);',1)[0]
    assert 'PRIMARY KEY (card_id, card_bnft_id, rule_key, pool_id)' in table
    assert all(re.search(rf'\b{name}\b[^\n]*NOT NULL', table) for name in ('card_id','card_bnft_id','rule_key','pool_id','pool_role_cd'))
    assert not re.search(r'\bFOREIGN\s+KEY\s*\(', ddl, re.I)
    assert 'seq_card_bnft_rule_pool' not in ddl
    assert "v_rule ? 'pool_refs'" in ddl


def test_v7_migration_and_rollback_preserve_data_and_use_no_foreign_keys():
    forward = (ROOT / 'db_pipeline_migration_v7_rule_pool.sql').read_text(encoding='utf-8')
    rollback = (ROOT / 'db_pipeline_migration_v7_rule_pool_rollback.sql').read_text(encoding='utf-8')
    assert 'EXCEPT ALL' in forward
    assert 'v7_rule_list_before_pool_split' in forward and 'v7_rule_list_before_pool_split' in rollback
    assert not re.search(r'\bFOREIGN\s+KEY\s*\(', forward + rollback, re.I)
    assert 'COMMIT;' in forward and 'COMMIT;' in rollback


def test_dbml_refs_are_explicitly_logical():
    dbml = (ROOT / 'db_pipeline_schemaV7_draft.dbml').read_text(encoding='utf-8')
    assert 'Ref lines are logical only; SQL has 0 FKs' in dbml
    assert 'card_bnft_rule_pool.(card_id, card_bnft_id)' in dbml
    assert 'card_bnft_rule_pool.(card_id, pool_id)' in dbml
