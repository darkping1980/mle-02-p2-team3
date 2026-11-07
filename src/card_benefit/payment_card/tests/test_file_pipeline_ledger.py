import hashlib
import json
from pathlib import Path

import pytest

from payment_card.file_pipeline.ledger import plan as ledger


def fixture(tmp_path, *, text="합성 텍스트", role="product_guide", pages=1):
    index = tmp_path / "documents.csv"
    index.write_text(
        "issuer,doc_id,sha256,file_path,doc_role,canonical,pages,title,source_url\n"
        f"hana,doc-a,{hashlib.sha256(b'pdf').hexdigest()},folder/a.pdf,{role},Y,{pages},합성 제목,https://invalid.example\n",
        encoding="utf-8",
    )
    trace_dir, chunk_dir = tmp_path / "trace", tmp_path / "chunks"
    trace_dir.mkdir(exist_ok=True); chunk_dir.mkdir(exist_ok=True)
    sha = hashlib.sha256(text.encode()).hexdigest()
    trace = {"pages": [{"page_no": 1, "text": text, "quality": {"extractor": "PyMuPDF", "extractor_ver": "1.0", "has_visual": False}}]}
    chunks = {"chunks": [{"page_no": 1, "start_pos": 1, "end_pos": len(text), "text": text, "chunk_id": "c1", "heading": None}]}
    (trace_dir / "doc-a.json").write_text(json.dumps(trace), encoding="utf-8")
    (chunk_dir / "doc-a.chunks.json").write_text(json.dumps(chunks), encoding="utf-8")
    return index, trace_dir, chunk_dir


def make_plan(tmp_path, **kwargs):
    index, trace, chunks = fixture(tmp_path, **kwargs)
    return ledger.build_plan(index, trace, chunks, "hana", "tester", "2026-11-05T00:00:00Z")


def test_column_mapping_and_codes_are_seed_values(tmp_path):
    p = make_plan(tmp_path)
    d, page, chunk = p["docs"][0], p["pages"][0], p["chunks"][0]
    assert d["doc_type_cd"] == "PRODUCT_GUIDE"
    assert d["card_doc_id"].startswith("D") and d["doc_cd"].startswith("DOC-")
    assert page["char_count"] == len(page["text"])
    assert page["sha"] == hashlib.sha256(page["text"].encode()).hexdigest()
    assert page["layer"] in ledger.SEED_CODES["PAGE_LAYER"]
    assert page["extractor"] == "PyMuPDF" and page["extractor_ver"] == "1.0"
    assert chunk["start"] == 1 and chunk["end"] == len(chunk["text"])
    assert "BODY" in ledger.SEED_CODES["CHUNK_TYPE"] and "RAW" in ledger.SEED_CODES["CHUNK_STATUS"]


def test_code_mapping_rejects_unknown_role(tmp_path):
    assert any("DOC_TYPE 매핑 불가" in x for x in make_plan(tmp_path, role="mystery")["errors"])


def test_deterministic_ids_and_source_scheme(tmp_path):
    one = make_plan(tmp_path)
    two = make_plan(tmp_path)
    assert one["docs"][0]["card_doc_id"] == two["docs"][0]["card_doc_id"]
    assert one["chunks"][0]["chunk_id"] == two["chunks"][0]["chunk_id"]
    assert ledger._id("D", "irrelevant", "source", "doc-a") == "Ddoc-a"


def test_required_collected_date_and_user_are_checked(tmp_path):
    index, trace, chunks = fixture(tmp_path)
    plan = ledger.build_plan(index, trace, chunks, "hana", "", None)
    assert any("--collected-at 필요" in x for x in plan["errors"])
    assert any("--create-user-id" in x for x in plan["errors"])


def test_duplicate_sha_and_page_count_mismatch_are_reported(tmp_path):
    index, trace, chunks = fixture(tmp_path, pages=2)
    with index.open("a") as f:
        f.write(index.read_text(encoding="utf-8").splitlines()[1] + "\n")
    plan = ledger.build_plan(index, trace, chunks, "hana", "tester", "2026-11-05Z")
    assert any("중복 doc_sha256" in x for x in plan["errors"])
    assert any("쪽 수 불일치" in x for x in plan["errors"])


def test_chunk_range_and_nul_are_rejected(tmp_path):
    index, trace, chunks = fixture(tmp_path)
    payload = json.loads((chunks / "doc-a.chunks.json").read_text())
    payload["chunks"][0]["end_pos"] = 999
    (chunks / "doc-a.chunks.json").write_text(json.dumps(payload))
    plan = ledger.build_plan(index, trace, chunks, "hana", "tester", "2026-11-05Z")
    assert any("청크 위치 범위 오류" in x for x in plan["errors"])
    with pytest.raises(ValueError, match="NUL"):
        ledger._literal("a\x00b")
    with pytest.raises(ValueError, match="NUL"):
        ledger._dollar_quote("a\x00b")


def test_sql_escape_tags_conflict_and_order_transaction(tmp_path):
    text = "quote ' slash \\ dollar $ledger$"
    plan = make_plan(tmp_path, text=text)
    sql = ledger.sql_text(plan)
    assert "$ledger1$" + text + "$ledger1$" in sql
    assert "ON CONFLICT DO NOTHING" in sql
    assert sql.index("INSERT INTO file_pipeline.card_doc ") < sql.index("INSERT INTO file_pipeline.card_doc_page ") < sql.index("INSERT INTO file_pipeline.card_doc_chunk ")
    assert sql.startswith("-- 드라이런") and "BEGIN;" in sql and sql.endswith("COMMIT;\n")
    assert max(map(len, sql.splitlines())) < 100_000


def test_output_path_guard(tmp_path):
    with pytest.raises(SystemExit):
        ledger.main(["--issuer", "hana", "--index", str(tmp_path), "--trace-dir", str(tmp_path), "--chunk-dir", str(tmp_path), "--create-user-id", "u", "--collected-at", "2026-11-05Z", "--sql-out", str(ledger.REPO_ROOT / "bad.sql")])


def test_schema_csv_comparison_is_synthetic():
    rows = [{"table_name": "card_doc", "column_name": "doc_sha256"}]
    assert ledger.compare_schema_csv(rows, {"card_doc": {"doc_sha256", "doc_cd"}}) == ["card_doc: missing=['doc_cd'], extra=[]"]


def test_no_database_connector_or_db_environment_imports():
    source = Path(ledger.__file__).read_text(encoding="utf-8")
    assert "psycopg" not in source
    assert "os.environ" not in source


def test_single_insert_size_is_bounded():
    with pytest.raises(ValueError, match="제한"):
        ledger._insert("card_doc_page", ("page_raw_txt",), [ledger._dollar_quote("x" * ledger.MAX_INSERT_BYTES)])
