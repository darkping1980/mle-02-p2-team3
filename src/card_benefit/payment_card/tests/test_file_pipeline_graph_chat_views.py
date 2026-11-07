"""fp_chat 뷰 SQL의 오프라인 정적 안전성 검사."""
import hashlib
import re
import uuid
from pathlib import Path


SQL_PATH = (
    Path(__file__).resolve().parents[1]
    / "file_pipeline"
    / "graph"
    / "chat_views.sql"
)


def test_chat_views_sql_is_read_only_and_uses_expected_views():
    sql = SQL_PATH.read_text(encoding="utf-8").lower()
    sql = re.sub(r"--[^\n]*", "", sql)

    for forbidden in ("drop schema", "truncate", "delete from", "cascade"):
        assert forbidden not in sql

    assert re.search(r"create\s+or\s+replace\s+view\s+fp_chat\.nodes\b", sql)
    assert re.search(r"create\s+or\s+replace\s+view\s+fp_chat\.edges\b", sql)
    assert "md5(" in sql and "::uuid" in sql
    assert "document" in sql
    assert "supported_by" in sql

    referenced_tables = re.findall(
        r"\b(?:from|join)\s+([a-z_][a-z_0-9]*\.[a-z_][a-z_0-9]*)",
        sql,
    )
    assert referenced_tables
    assert all(table.startswith("public.fp_") for table in referenced_tables)


def test_md5_text_uuid_mapping_is_deterministic():
    value = "doc:" + ("a" * 64)
    first = uuid.UUID(hashlib.md5(value.encode("utf-8")).hexdigest())
    second = uuid.UUID(hashlib.md5(value.encode("utf-8")).hexdigest())
    assert first == second
