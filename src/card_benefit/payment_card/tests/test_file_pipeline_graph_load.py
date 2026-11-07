import csv
import json

from payment_card.file_pipeline.graph import load


def _csv(path, headers, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers); w.writeheader(); w.writerows(rows)


def _files(tmp_path):
    _csv(tmp_path / "fp_load_runs.csv", ["run_id", "input_folder_name", "model_name", "started_at", "node_count", "edge_count"],
         [{"run_id": "r1", "input_folder_name": "in", "model_name": "m", "started_at": "2026-01-01T00:00:00+00:00", "node_count": 2, "edge_count": 1}])
    _csv(tmp_path / "fp_nodes.csv", ["id", "node_type", "props", "chunk_id", "run_id"],
         [{"id": "a", "node_type": "Benefit", "props": json.dumps({}), "chunk_id": "c", "run_id": "r1"}, {"id": "b", "node_type": "Condition", "props": "{}", "chunk_id": "c", "run_id": "r1"}])
    _csv(tmp_path / "fp_edges.csv", ["id", "source_id", "target_id", "edge_type", "run_id"],
         [{"id": "e", "source_id": "a", "target_id": "b", "edge_type": "HAS_CONDITION", "run_id": "r1"}])
    _csv(tmp_path / "fp_evidence.csv", ["node_id", "edge_id", "doc_sha256", "page_no", "start_pos", "end_pos", "quote_status"], [])


def test_dry_run_never_connects(tmp_path, monkeypatch, capsys):
    _files(tmp_path)
    monkeypatch.setattr(load, "_connect", lambda _: (_ for _ in ()).throw(AssertionError("connected")))
    assert load.main(["--csv-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == '{"counts": {"fp_edges": 1, "fp_evidence": 0, "fp_load_runs": 1, "fp_nodes": 2}, "mode": "dry_run"}\n'


class FakeCursor:
    def __init__(self, duplicate=False, existing_nodes=None): self.calls=[]; self.batch_calls=[]; self.duplicate=duplicate; self.counts=[]; self.existing_nodes=existing_nodes or []
    def execute(self, sql, params=None):
        self.calls.append((sql, params))
    def executemany(self, sql, rows): self.batch_calls.append((sql, list(rows)))
    def fetchone(self):
        if self.counts: return (self.counts.pop(0),)
        if self.calls and self.calls[-1][0].startswith("SELECT COUNT"): return (0,)
        return (1,) if self.duplicate else None
    def fetchall(self):
        if self.calls and self.calls[-1][0].startswith("SELECT id, node_type"):
            return list(self.existing_nodes)
        return [(n,) for n in self.counts]
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def close(self): pass


class FakeConn:
    def __init__(self, duplicate=False, fail=False, existing_nodes=None): self.cur=FakeCursor(duplicate, existing_nodes); self.events=[]; self.fail=fail
    def cursor(self): return self.cur
    def commit(self): self.events.append("commit")
    def rollback(self): self.events.append("rollback")
    def close(self): self.events.append("close")


def test_execute_inserts_in_allowlisted_order_and_duplicate_rolls_back(tmp_path, monkeypatch):
    _files(tmp_path)
    conn=FakeConn(); monkeypatch.setattr(load, "_connect", lambda url: conn); monkeypatch.setenv("FP_DATABASE_URL", "secret")
    load.load_csvs(tmp_path, execute=True)
    tables=[load._table_for_sql(sql) for sql, _ in conn.cur.batch_calls]
    assert tables == ["fp_load_runs", "fp_nodes", "fp_edges"]
    assert conn.events == ["commit", "close"]
    dup=FakeConn(duplicate=True); monkeypatch.setattr(load, "_connect", lambda url: dup)
    try: load.load_csvs(tmp_path, execute=True)
    except load.DuplicateRunError: pass
    else: assert False, "duplicate must reject"
    assert dup.events == ["rollback", "close"]


def test_execute_failure_rolls_back_and_never_prints_database_url(tmp_path, monkeypatch, capsys):
    _files(tmp_path)
    class FailingCursor(FakeCursor):
        def executemany(self, sql, rows):
            super().executemany(sql, rows)
            if sql.startswith("INSERT INTO public.fp_nodes"):
                error = RuntimeError("secret connection contents")
                error.sqlstate = "XX001"
                raise error
    class FailingConn(FakeConn):
        def __init__(self): super().__init__(); self.cur=FailingCursor()
    conn=FailingConn(); monkeypatch.setattr(load, "_connect", lambda url: conn); monkeypatch.setenv("FP_DATABASE_URL", "secret-dsn")
    assert load.main(["--csv-dir", str(tmp_path), "--execute"]) == 1
    output=capsys.readouterr().err
    assert "secret-dsn" not in output and "secret connection contents" not in output
    assert "RuntimeError" in output and "XX001" in output
    assert conn.events == ["rollback", "close"]


def test_execute_batches_rows_by_1000_and_preserves_table_order(tmp_path, monkeypatch):
    _files(tmp_path)
    rows = []
    for i in range(2500):
        rows.append({"id": f"n{i}", "node_type": "Benefit", "props": "{}", "chunk_id": "c", "run_id": "r1"})
    _csv(tmp_path / "fp_nodes.csv", ["id", "node_type", "props", "chunk_id", "run_id"], rows)
    _csv(tmp_path / "fp_load_runs.csv", ["run_id", "input_folder_name", "model_name", "started_at", "node_count", "edge_count"],
         [{"run_id": "r1", "input_folder_name": "in", "model_name": "m", "started_at": "2026-01-01T00:00:00+00:00", "node_count": 2500, "edge_count": 0}])
    _csv(tmp_path / "fp_edges.csv", ["id", "source_id", "target_id", "edge_type", "run_id"], [])
    conn = FakeConn(); monkeypatch.setattr(load, "_connect", lambda _: conn); monkeypatch.setenv("FP_DATABASE_URL", "unused")
    result = load.load_csvs(tmp_path, execute=True)
    assert result == {"mode": "execute", "counts": {"fp_load_runs": 1, "fp_nodes": 2500, "fp_edges": 0, "fp_evidence": 0}}
    assert [(load._table_for_sql(sql), len(batch)) for sql, batch in conn.cur.batch_calls] == [
        ("fp_load_runs", 1), ("fp_nodes", 1000), ("fp_nodes", 1000), ("fp_nodes", 500)
    ]
    assert conn.events == ["commit", "close"]


def test_delete_run_dry_run_only_counts(tmp_path, monkeypatch):
    conn = FakeConn(); conn.cur.counts = [2, 3, 4, 5]
    monkeypatch.setattr(load, "_connect", lambda _: conn); monkeypatch.setenv("FP_DATABASE_URL", "unused")
    assert load.delete_run("r1") == {"mode": "dry_run", "counts": {"fp_evidence": 2, "fp_edges": 3, "fp_nodes": 4, "fp_load_runs": 5}}
    assert all(not sql.startswith("DELETE") for sql, _ in conn.cur.calls)
    assert conn.events == ["close"]


def test_delete_run_execute_order_parameters_and_unknown_run(tmp_path, monkeypatch):
    conn = FakeConn(); monkeypatch.setattr(load, "_connect", lambda _: conn); monkeypatch.setenv("FP_DATABASE_URL", "unused")
    assert load.delete_run("r1", execute=True)["mode"] == "execute"
    deletes = [(sql, params) for sql, params in conn.cur.calls if sql.startswith("DELETE")]
    assert [sql.split(" public.")[1].split()[0] for sql, _ in deletes] == ["fp_evidence", "fp_edges", "fp_nodes", "fp_load_runs"]
    assert all(params == ("r1", "r1") if sql.startswith("DELETE FROM public.fp_evidence") else params == ("r1",) for sql, params in deletes)
    assert conn.events == ["commit", "close"]
    unknown = FakeConn(); monkeypatch.setattr(load, "_connect", lambda _: unknown)
    assert load.delete_run("absent")["counts"] == {"fp_evidence": 0, "fp_edges": 0, "fp_nodes": 0, "fp_load_runs": 0}


def test_unallowlisted_csv_is_rejected(tmp_path):
    _files(tmp_path)
    (tmp_path / "public_nodes.csv").write_text("id\n", encoding="utf-8")
    try:
        load.validate_csvs(tmp_path)
    except ValueError as exc:
        assert "allowlist" in str(exc)
    else:
        assert False, "unallowlisted table file must be rejected"


def test_execute_converts_empty_evidence_targets_and_chunk_id_to_null(tmp_path, monkeypatch):
    """CSV 빈 칸이 '' 로 DB 에 들어가면 fp_evidence_exactly_one_target 체크 위반이 된다(실제 적재에서 발생)."""
    _files(tmp_path)
    sha = "a" * 64
    _csv(tmp_path / "fp_nodes.csv", ["id", "node_type", "props", "chunk_id", "run_id"],
         [{"id": "a", "node_type": "Benefit", "props": "{}", "chunk_id": "", "run_id": "r1"},
          {"id": "b", "node_type": "Condition", "props": "{}", "chunk_id": "c", "run_id": "r1"}])
    _csv(tmp_path / "fp_evidence.csv", ["node_id", "edge_id", "doc_sha256", "page_no", "start_pos", "end_pos", "quote_status"],
         [{"node_id": "a", "edge_id": "", "doc_sha256": sha, "page_no": 1, "start_pos": 1, "end_pos": 2, "quote_status": "located"},
          {"node_id": "", "edge_id": "e", "doc_sha256": sha, "page_no": "", "start_pos": "", "end_pos": "", "quote_status": "missing"}])
    conn = FakeConn(); monkeypatch.setattr(load, "_connect", lambda url: conn); monkeypatch.setenv("FP_DATABASE_URL", "secret")
    load.load_csvs(tmp_path, execute=True)
    by_table = {load._table_for_sql(sql): rows for sql, rows in conn.cur.batch_calls}
    assert by_table["fp_nodes"][0][3] is None and by_table["fp_nodes"][1][3] == "c"
    ev = by_table["fp_evidence"]
    assert ev[0][0] == "a" and ev[0][1] is None
    assert ev[1][0] is None and ev[1][1] == "e"
    assert all((row[0] is None) != (row[1] is None) for row in ev)


def _card_graph_files(tmp_path, benefit_type="Benefit"):
    _csv(tmp_path / "fp_load_runs.csv", ["run_id", "input_folder_name", "model_name", "started_at", "node_count", "edge_count"],
         [{"run_id": "r1", "input_folder_name": "in", "model_name": "m", "started_at": "2026-01-01T00:00:00+00:00", "node_count": 2, "edge_count": 1}])
    _csv(tmp_path / "fp_nodes.csv", ["id", "node_type", "props", "chunk_id", "run_id"],
         [{"id": "card-1", "node_type": "Card", "props": "{}", "chunk_id": "c", "run_id": "r1"},
          {"id": "benefit-1", "node_type": benefit_type, "props": "{}", "chunk_id": "c", "run_id": "r1"}])
    _csv(tmp_path / "fp_edges.csv", ["id", "source_id", "target_id", "edge_type", "run_id"],
         [{"id": "offer-1", "source_id": "card-1", "target_id": "benefit-1", "edge_type": "OFFERS", "run_id": "r1"}])
    _csv(tmp_path / "fp_evidence.csv", ["node_id", "edge_id", "doc_sha256", "page_no", "start_pos", "end_pos", "quote_status"],
         [{"node_id": "benefit-1", "edge_id": "", "doc_sha256": "a" * 64, "page_no": 1, "start_pos": 1, "end_pos": 2, "quote_status": "located"}])


def test_skip_existing_nodes_inserts_only_new_nodes_and_preserves_other_rows(tmp_path, monkeypatch):
    _card_graph_files(tmp_path)
    conn = FakeConn(existing_nodes=[("card-1", "Card")])
    monkeypatch.setattr(load, "_connect", lambda _: conn)
    monkeypatch.setenv("FP_DATABASE_URL", "unused")

    result = load.load_csvs(tmp_path, execute=True, skip_existing_nodes=True)

    tables = [load._table_for_sql(sql) for sql, _ in conn.cur.batch_calls]
    by_table = {load._table_for_sql(sql): batch for sql, batch in conn.cur.batch_calls}
    assert tables == ["fp_load_runs", "fp_nodes", "fp_edges", "fp_evidence"]
    assert [row[0] for row in by_table["fp_nodes"]] == ["benefit-1"]
    assert by_table["fp_edges"][0][0] == "offer-1"
    assert by_table["fp_evidence"][0][0] == "benefit-1"
    assert result["counts"]["fp_nodes"] == 2
    assert result["csv_node_count"] == 2
    assert result["actual_new_run_node_count"] == 1
    assert result["skipped_existing_node_count"] == 1
    assert result["skipped_existing_node_ids"] == ["card-1"]
    assert conn.cur.calls.count(("SELECT id, node_type FROM public.fp_nodes WHERE id = ANY(%s)", (["card-1", "benefit-1"],))) == 1


def test_skip_existing_nodes_rejects_non_card_overlap_before_inserts(tmp_path, monkeypatch):
    _card_graph_files(tmp_path, benefit_type="Benefit")
    conn = FakeConn(existing_nodes=[("benefit-1", "Benefit")])
    monkeypatch.setattr(load, "_connect", lambda _: conn)
    monkeypatch.setenv("FP_DATABASE_URL", "unused")

    try:
        load.load_csvs(tmp_path, execute=True, skip_existing_nodes=True)
    except load.ExistingNodeConflictError:
        pass
    else:
        assert False, "existing non-Card nodes must reject the load"

    assert conn.cur.batch_calls == []
    assert conn.events == ["rollback", "close"]


def test_skip_existing_nodes_rejects_node_type_mismatch_before_inserts(tmp_path, monkeypatch):
    _card_graph_files(tmp_path)
    conn = FakeConn(existing_nodes=[("card-1", "Benefit")])
    monkeypatch.setattr(load, "_connect", lambda _: conn)
    monkeypatch.setenv("FP_DATABASE_URL", "unused")

    try:
        load.load_csvs(tmp_path, execute=True, skip_existing_nodes=True)
    except load.ExistingNodeConflictError:
        pass
    else:
        assert False, "node_type mismatch must reject the load"

    assert conn.cur.batch_calls == []
    assert conn.events == ["rollback", "close"]


def test_skip_existing_nodes_without_overlaps_inserts_same_rows(tmp_path, monkeypatch):
    _card_graph_files(tmp_path)
    conn = FakeConn()
    monkeypatch.setattr(load, "_connect", lambda _: conn)
    monkeypatch.setenv("FP_DATABASE_URL", "unused")

    load.load_csvs(tmp_path, execute=True, skip_existing_nodes=True)

    tables = [load._table_for_sql(sql) for sql, _ in conn.cur.batch_calls]
    by_table = {load._table_for_sql(sql): batch for sql, batch in conn.cur.batch_calls}
    assert tables == ["fp_load_runs", "fp_nodes", "fp_edges", "fp_evidence"]
    assert [row[0] for row in by_table["fp_nodes"]] == ["card-1", "benefit-1"]
    assert by_table["fp_edges"][0][0] == "offer-1"
    assert by_table["fp_evidence"][0][0] == "benefit-1"


def test_skip_existing_nodes_dry_run_has_note_and_never_connects(tmp_path, monkeypatch):
    _card_graph_files(tmp_path)
    monkeypatch.setattr(load, "_connect", lambda _: (_ for _ in ()).throw(AssertionError("connected")))

    result = load.load_csvs(tmp_path, skip_existing_nodes=True)

    assert result["mode"] == "dry_run"
    assert result["skip_existing_nodes_note"] == "Skip targets will be determined by DB lookup at execution time."
