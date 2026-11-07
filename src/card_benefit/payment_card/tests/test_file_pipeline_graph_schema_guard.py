"""Static guard for the deliberately unexecuted graph SQL and CSV contract."""
import re
from pathlib import Path

from payment_card.file_pipeline.graph.export import CSV_COLUMNS

SCHEMA = Path(__file__).resolve().parents[1] / "file_pipeline" / "graph" / "schema.sql"
MIGRATION = SCHEMA.with_name("migrate_pf_to_fp.sql")


def test_schema_object_names_are_prefixed_and_no_destructive_ddl():
    sql = SCHEMA.read_text(encoding="utf-8")
    creates = re.findall(r"\bcreate\s+(?:or\s+replace\s+)?(table|index|function|trigger|view)\s+(?:if\s+not\s+exists\s+)?(?:public\.)?([\w]+)", sql, re.I)
    assert creates
    assert all(name.lower().startswith("fp_") for _, name in creates)
    assert not re.search(r"\b(?:drop|truncate|delete)\b|\balter\s+\w+\s+drop\b", sql, re.I)
    assert not re.search(r"\b(?:from|join|into|update|on|references)\s+(?:public\.)?(?:nodes|edges)\b", sql, re.I)


def test_every_created_table_enables_rls_and_no_policy_is_created():
    sql = SCHEMA.read_text(encoding="utf-8")
    tables = re.findall(r"\bcreate\s+table\s+if\s+not\s+exists\s+(?:public\.)?(fp_\w+)", sql, re.I)
    enabled = set(re.findall(r"\balter\s+table\s+(?:public\.)?(fp_\w+)\s+enable\s+row\s+level\s+security", sql, re.I))
    assert set(tables) <= enabled
    assert not re.search(r"\bcreate\s+policy\b", sql, re.I)


def test_export_load_csv_columns_match_sql_tables():
    sql = SCHEMA.read_text(encoding="utf-8")
    for table, exported in CSV_COLUMNS.items():
        match = re.search(rf"create\s+table\s+if\s+not\s+exists\s+public\.{table}\s*\((.*?)\n\);", sql, re.I | re.S)
        assert match, table
        sql_columns = []
        for line in match.group(1).splitlines():
            column = re.match(r"\s{2}([a-z_]\w*)\s+", line, re.I)
            if not column:
                continue
            name = column.group(1)
            if name.lower() not in {"constraint", "primary", "unique", "check", "foreign"}:
                sql_columns.append(name)
        if table == "fp_evidence":
            sql_columns = [name for name in sql_columns if name != "id"]
        assert exported == sql_columns, table


def test_pf_to_fp_migration_is_safe_and_covers_schema_objects():
    sql = MIGRATION.read_text(encoding="utf-8")
    schema = SCHEMA.read_text(encoding="utf-8")

    assert not re.search(r"\bdrop\s+table\b|\btruncate\b|\bdelete\s+from\b|\bdrop\s+schema\b", sql, re.I)
    assert re.search(r"\bbegin\s*;", sql, re.I)
    assert re.search(r"\bcommit\s*;", sql, re.I)

    tables = re.findall(r"\bcreate\s+table\s+if\s+not\s+exists\s+public\.(fp_\w+)", schema, re.I)
    constraints = re.findall(r"\bconstraint\s+(fp_\w+)", schema, re.I)
    indexes = re.findall(r"\bcreate\s+index\s+if\s+not\s+exists\s+(fp_\w+)", schema, re.I)
    assert len(tables) == 4
    for name in [*tables, *indexes]:
        old_name = "pf_" + name[3:]
        assert re.search(rf"\b{re.escape(old_name)}\b", sql, re.I), old_name
        assert re.search(rf"\b{re.escape(name)}\b", sql, re.I), name

    assert "c.conname like 'pf\\_%' escape '\\'" in sql
    assert "new_name := 'fp_' || substr(r.conname, 4)" in sql
    assert constraints
    assert all("fp_" + name[3:] == name for name in constraints)
    assert re.search(
        r"alter\s+sequence\s+if\s+exists\s+public\.pf_evidence_id_seq\s+rename\s+to\s+fp_evidence_id_seq",
        sql,
        re.I,
    )
