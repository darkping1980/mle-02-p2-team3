"""Read-only preview tool contract tests; no PostgreSQL connection is opened."""
from __future__ import annotations

import json
import copy
from contextlib import contextmanager
from pathlib import Path

from payment_card.db_pipeline.limit_struct_backfill import (
    TARGETS,
    apply_corrections,
    compose_preview,
    derive_fixture_patches,
    rollback_corrections,
)


FIXTURES = json.loads(Path(__file__).with_name("fixtures_limit_struct.json").read_text(encoding="utf-8"))


def _live_rows():
    return [{"card_id": card_id, "card_product_item_id": item_id, "item_type_cd": "BENEFIT",
             "item_nm": FIXTURES[f"{card_id}/{item_id}"]["stg_raw_item"]["bnft_nm"],
             "item_data": {}, "rule_list": FIXTURES[f"{card_id}/{item_id}"]["rule_list"],
             "item_limit_txt": "unchanged", "item_search_txt": "unchanged", "item_embedding": None}
            for card_id, item_id in TARGETS]


def test_preview_derives_three_target_shapes_and_eight_condition_links():
    rows, links = derive_fixture_patches(FIXTURES)
    assert len(rows) == 3
    assert len(links) == 8
    by_card = {row["card_id"]: row["item_data_patch"] for row in rows}
    assert [cap["amount"] for cap in by_card[22]["limit_tiers"]["own"]["caps"].values()] == [10000, 15000]
    assert "limit_tiers" not in by_card[23]  # Unapproved upper bounds are not inferred.
    assert "limit_tiers" not in by_card[20]  # Cumulative "additional" cap is not an exclusive tier.
    assert any(link["card_id"] == 22 and link["evidence_id"] == "20261105_002687" for link in links)


def test_preview_merges_existing_data_and_reports_duplicate_links_without_writing():
    proposed, expected_links = derive_fixture_patches(FIXTURES)
    already_linked = [{**link} for link in expected_links[:2]]
    preview = compose_preview(FIXTURES, _live_rows(), already_linked)
    assert preview["mode"] == "READ_ONLY_DRY_RUN"
    assert preview["database_writes"] == 0
    assert preview["evidence_link_summary"] == {"planned": 8, "already_exists": 2, "would_add": 6}
    row22 = next(row for row in preview["targets"] if row["card_id"] == 22)
    assert row22["item_data_before"] == {}
    assert row22["item_data_after_preview"] == proposed[0]["item_data_patch"]
    assert row22["unchanged_fields_preimage"]["item_limit_txt"] == "unchanged"
    assert len(preview["backup_preimage"]) == 3


def test_preview_fails_closed_if_any_live_target_is_missing():
    try:
        compose_preview(FIXTURES, _live_rows()[:-1], [])
    except ValueError as error:
        assert "target PK set differs from allowlist" in str(error)
    else:
        raise AssertionError("missing live target must block preview")


def test_preview_includes_json_diff_and_rejects_duplicate_target_pk():
    preview = compose_preview(FIXTURES, _live_rows(), [])
    row22 = next(row for row in preview["targets"] if row["card_id"] == 22)
    assert "--- item_data_before" in row22["item_data_json_diff"]
    assert "+  \"limits\"" in row22["item_data_json_diff"]
    try:
        compose_preview(FIXTURES, [*_live_rows(), _live_rows()[0]], [])
    except ValueError as error:
        assert "unique target rows" in str(error)
    else:
        raise AssertionError("duplicate target PK must block preview")


def test_preview_does_not_treat_non_null_relation_key_as_the_expected_rule_link():
    _, expected_links = derive_fixture_patches(FIXTURES)
    unrelated = {**expected_links[0], "relation_key": "OTHER_RELATION"}
    preview = compose_preview(FIXTURES, _live_rows(), [unrelated])
    first = next(link for link in preview["evidence_links"]
                 if link["evidence_id"] == expected_links[0]["evidence_id"])
    assert first["already_exists"] is False


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
        self.one = None
        self.connection.write_statements = getattr(self.connection, "write_statements", [])

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.one, self.rows = None, []
        if normalized == "SHOW transaction_read_only":
            self.one = {"transaction_read_only": self.connection.read_only}
        elif "SELECT current_database()" in normalized:
            self.one = {"database_name": self.connection.database,
                        "server_address": self.connection.server_address}
        elif "FROM db_pipeline.card_product_item" in normalized and "FOR UPDATE" in normalized:
            self.rows = copy.deepcopy(self.connection.items)
        elif "FROM db_pipeline.card_evidence_link" in normalized and "ORDER BY" in normalized:
            self.rows = copy.deepcopy(self.connection.links)
        elif "FROM db_pipeline.card_source_evidence" in normalized and "ANY(%s)" in normalized:
            ids = set(params[0])
            self.rows = [copy.deepcopy(row) for key, row in self.connection.source_evidence.items() if key in ids]
        elif normalized.startswith("UPDATE db_pipeline.card_product_item"):
            self.connection.write_statements.append("UPDATE")
            new_data, card_id, item_id, before = params
            row = next((item for item in self.connection.items
                        if item["card_id"] == card_id and item["card_product_item_id"] == item_id), None)
            if row and json.dumps(row["item_data"], ensure_ascii=False, sort_keys=True,
                                  separators=(",", ":")) == before:
                row["item_data"] = json.loads(new_data)
                self.one = {"card_id": card_id, "card_product_item_id": item_id}
        elif normalized.startswith("INSERT INTO db_pipeline.card_evidence_link"):
            self.connection.write_statements.append("INSERT")
            if self.connection.fail_on_insert:
                raise RuntimeError("injected insert failure")
            card_id, item_id, rule_key, atom_key, evidence_id = params
            natural = (card_id, item_id, rule_key, atom_key, evidence_id)
            existing = next((row for row in self.connection.links if
                             (row["card_id"], row["card_product_item_id"], row["rule_key"],
                              row["ev_item_key"], row["evidence_id"]) == natural), None)
            if existing is None:
                link_id = f"L{len(self.connection.links) + 1}"
                existing = {"card_id": card_id, "card_product_item_id": item_id,
                            "rule_key": rule_key, "ev_subject_cd": "RULE", "relation_key": None,
                            "ev_item_cd": "COND", "ev_item_key": atom_key, "evidence_id": evidence_id,
                            "evidence_link_id": link_id}
                self.connection.links.append(existing)
                self.one = {"evidence_link_id": link_id}
        elif normalized.startswith("DELETE FROM db_pipeline.card_evidence_link"):
            self.connection.write_statements.append("DELETE")
            link_id, card_id, item_id, rule_key, atom_key, evidence_id = params
            existing = next((row for row in self.connection.links if
                             (row["evidence_link_id"], row["card_id"], row["card_product_item_id"],
                              row["rule_key"], row["ev_item_key"], row["evidence_id"]) ==
                             (link_id, card_id, item_id, rule_key, atom_key, evidence_id)), None)
            if existing:
                self.connection.links.remove(existing)
                self.one = {"evidence_link_id": link_id}
        elif "FROM db_pipeline.card_evidence_link WHERE evidence_link_id = ANY(%s)" in normalized:
            ids = set(params[0])
            self.rows = [{"evidence_link_id": row["evidence_link_id"]} for row in self.connection.links
                         if row["evidence_link_id"] in ids]
        elif "FROM db_pipeline.card_evidence_link WHERE evidence_link_id = %s" in normalized:
            link_id = params[0]
            found = next((row for row in self.connection.links if row["evidence_link_id"] == link_id), None)
            self.one = copy.deepcopy(found)
        elif normalized.startswith("SELECT evidence_link_id FROM db_pipeline.card_evidence_link"):
            card_id, item_id, rule_key, atom_key, evidence_id = params
            found = next((row for row in self.connection.links if
                          (row["card_id"], row["card_product_item_id"], row["rule_key"],
                           row["ev_item_key"], row["evidence_id"]) ==
                          (card_id, item_id, rule_key, atom_key, evidence_id)), None)
            self.one = {"evidence_link_id": found["evidence_link_id"]} if found else None
        elif "FROM db_pipeline.card_product_item" in normalized:
            self.rows = [{"card_id": row["card_id"], "card_product_item_id": row["card_product_item_id"],
                          "item_data": copy.deepcopy(row["item_data"])} for row in self.connection.items]
        elif "FROM db_pipeline.card_evidence_link" in normalized:
            self.rows = copy.deepcopy(self.connection.links)
        else:
            raise AssertionError(f"Unexpected SQL in fake connection: {normalized}")

    def fetchone(self):
        return copy.deepcopy(self.one)

    def fetchall(self):
        return copy.deepcopy(self.rows)


class FakeConnection:
    def __init__(self, *, read_only="off", database="db_pipeline", server_address="10.0.0.1",
                 fail_on_insert=False, existing_links=None):
        self.items = _live_rows()
        self.links = copy.deepcopy(existing_links or [])
        self.source_evidence = {}
        for key, fixture in FIXTURES.items():
            for evidence in fixture["evidence"]:
                self.source_evidence[str(evidence["evidence_id"])] = {
                    "evidence_id": str(evidence["evidence_id"]), "card_doc_id": "doc",
                    "page_no": 1, "card_doc_chunk_id": "chunk",
                    "card_extr_stg_id": fixture["card_extr_stg_id"],
                    "start_pos": evidence.get("start_pos"), "end_pos": evidence.get("end_pos"),
                    "quote_txt": evidence.get("quote_txt")}
        self.read_only, self.database, self.server_address = read_only, database, server_address
        self.fail_on_insert = fail_on_insert
        self.write_statements = []
        self.rollback_count = 0
        self.commit_count = 0

    def cursor(self, row_factory=None):
        return FakeCursor(self)

    @contextmanager
    def transaction(self):
        before = copy.deepcopy((self.items, self.links))
        try:
            yield
        except Exception:
            self.items, self.links = before
            self.rollback_count += 1
            raise
        else:
            self.commit_count += 1


def test_apply_writer_updates_three_rows_and_inserts_eight_links_atomically(tmp_path):
    conn = FakeConnection()
    preimage = (tmp_path / "approved_preimage.json").resolve()
    result = apply_corrections(conn, FIXTURES, expected_database="db_pipeline",
                               expected_server_address="10.0.0.1", preimage_path=preimage)
    manifest = json.loads(preimage.read_text(encoding="utf-8"))
    assert result["state"] == "VALIDATED_PENDING_COMMIT"
    assert result["item_data_update_count"] == 3
    assert result["evidence_link_insert_count"] == 8
    assert manifest["state"] == "VALIDATED_PENDING_COMMIT"
    assert len(manifest["evidence_links_expected"]) == 8
    assert len(manifest["transaction_result_pending_commit"]["evidence_links_inserted"]) == 8
    assert len(conn.links) == 8 and conn.rollback_count == 0 and conn.commit_count == 1
    assert conn.write_statements.count("UPDATE") == 3
    assert conn.write_statements.count("INSERT") == 8


def test_apply_retry_is_idempotent_and_does_not_duplicate_links(tmp_path):
    conn = FakeConnection()
    first = tmp_path / "first.json"
    apply_corrections(conn, FIXTURES, expected_database="db_pipeline",
                      expected_server_address="10.0.0.1", preimage_path=first.resolve())
    before = copy.deepcopy(conn.links)
    second = tmp_path / "second.json"
    result = apply_corrections(conn, FIXTURES, expected_database="db_pipeline",
                               expected_server_address="10.0.0.1", preimage_path=second.resolve())
    assert result["item_data_update_count"] == 0
    assert result["evidence_link_insert_count"] == 0
    assert len(result["evidence_links_already_present"]) == 8
    assert conn.links == before


def test_apply_failure_rolls_back_all_rows_and_links_but_keeps_preimage(tmp_path):
    conn = FakeConnection(fail_on_insert=True)
    before_items, before_links = copy.deepcopy((conn.items, conn.links))
    preimage = (tmp_path / "failed_attempt_preimage.json").resolve()
    try:
        apply_corrections(conn, FIXTURES, expected_database="db_pipeline",
                          expected_server_address="10.0.0.1", preimage_path=preimage)
    except RuntimeError as error:
        assert "injected insert failure" in str(error)
    else:
        raise AssertionError("injected write error must fail the transaction")
    assert conn.items == before_items and conn.links == before_links
    assert conn.rollback_count == 1 and conn.commit_count == 0
    manifest = json.loads(preimage.read_text(encoding="utf-8"))
    assert manifest["state"] == "PREIMAGE_CAPTURED"


def test_apply_refuses_wrong_database_read_only_session_and_existing_preimage(tmp_path):
    preimage = (tmp_path / "preimage.json").resolve()
    for conn, db, server in ((FakeConnection(database="other"), "db_pipeline", "10.0.0.1"),
                             (FakeConnection(read_only="on"), "db_pipeline", "10.0.0.1"),
                             (FakeConnection(), "db_pipeline", "10.0.0.2")):
        try:
            apply_corrections(conn, FIXTURES, expected_database=db,
                              expected_server_address=server, preimage_path=preimage)
        except RuntimeError:
            pass
        else:
            raise AssertionError("target mismatch or read-only transaction must refuse writes")
        assert not conn.write_statements
        assert conn.rollback_count == 1
    preimage.write_text("existing", encoding="utf-8")
    try:
        apply_corrections(FakeConnection(), FIXTURES, expected_database="db_pipeline",
                          expected_server_address="10.0.0.1", preimage_path=preimage)
    except FileExistsError:
        pass
    else:
        raise AssertionError("writer must never overwrite an existing preimage")


def test_rollback_restores_preimage_and_deletes_only_links_inserted_by_run(tmp_path):
    conn = FakeConnection()
    before_items, before_links = copy.deepcopy((conn.items, conn.links))
    manifest_path = (tmp_path / "rollback_preimage.json").resolve()
    apply_corrections(conn, FIXTURES, expected_database="db_pipeline",
                      expected_server_address="10.0.0.1", preimage_path=manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["state"] = "COMMITTED"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = rollback_corrections(conn, expected_database="db_pipeline",
                                  expected_server_address="10.0.0.1", preimage_path=manifest_path)
    assert result["state"] == "VALIDATED_PENDING_COMMIT"
    assert conn.items == before_items and conn.links == before_links
    assert result["post_rollback_item_data_verified"] is True
    assert result["inserted_link_ids_absent"] is True
    assert len(result["evidence_link_ids_deleted"]) == 8
    assert conn.rollback_count == 0 and conn.commit_count == 2


def test_rollback_restores_rows_when_all_expected_links_preexisted(tmp_path):
    _, expected = derive_fixture_patches(FIXTURES)
    existing = [{**link, "ev_subject_cd": "RULE", "relation_key": None,
                 "evidence_link_id": f"E{index}"} for index, link in enumerate(expected, start=1)]
    conn = FakeConnection(existing_links=existing)
    before_items = copy.deepcopy(conn.items)
    manifest_path = (tmp_path / "preexisting_links_preimage.json").resolve()
    result = apply_corrections(conn, FIXTURES, expected_database="db_pipeline",
                               expected_server_address="10.0.0.1", preimage_path=manifest_path)
    assert result["item_data_update_count"] == 3
    assert result["evidence_link_insert_count"] == 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["state"] = "COMMITTED"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    rollback = rollback_corrections(conn, expected_database="db_pipeline",
                                    expected_server_address="10.0.0.1", preimage_path=manifest_path)
    assert conn.items == before_items
    assert conn.links == existing
    assert rollback["evidence_link_ids_deleted"] == []
    assert rollback["inserted_link_ids_absent"] is True


def test_rollback_failure_rolls_back_restores_and_does_not_delete_partial_links(tmp_path):
    conn = FakeConnection()
    manifest_path = (tmp_path / "rollback_failure_preimage.json").resolve()
    apply_corrections(conn, FIXTURES, expected_database="db_pipeline",
                      expected_server_address="10.0.0.1", preimage_path=manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["state"] = "COMMITTED"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    # Simulate an intervening edit. The rollback must stop before deleting links or overwrite that value.
    conn.items[0]["item_data"] = {"unexpected": True}
    before = copy.deepcopy((conn.items, conn.links))
    try:
        rollback_corrections(conn, expected_database="db_pipeline",
                             expected_server_address="10.0.0.1", preimage_path=manifest_path)
    except RuntimeError as error:
        assert "differs from recorded after-image" in str(error)
    else:
        raise AssertionError("rollback must refuse an intervening item_data edit")
    assert (conn.items, conn.links) == before
    assert conn.rollback_count == 1
