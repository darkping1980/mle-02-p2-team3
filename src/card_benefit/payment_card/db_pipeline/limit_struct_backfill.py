"""Preview or explicitly apply the three GraphRAG limit-structure corrections.

No flags means read-only dry-run. The write path requires ``--apply``, an exact
confirmation token, expected PostgreSQL database/server identity, and a new
absolute durable preimage path. It must only be used after separate user
approval. Every write is allowlisted, guarded by row locks and compare-and-swap,
and committed as one transaction after post-write checks.

Run from ``src/card_benefit`` with ``python -m payment_card.db_pipeline.limit_struct_backfill``
for the default read-only preview.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

from payment_card.db_pipeline.extraction_service import (
    check_limit_struct,
    limit_struct,
    limit_tiers_from_extraction,
)
from payment_card.db_pipeline.product_benefit_service import ProductBenefitService

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures_limit_struct.json"
TARGETS = ((22, "20261105_000099"), (23, "20261105_000100"), (20, "20261105_000092"))
EXPECTED_EVIDENCE_LINKS = 8
APPLY_CONFIRMATION = "APPLY_GRAPH_LIMIT_BACKFILL_22_23_20"
ROLLBACK_CONFIRMATION = "ROLLBACK_GRAPH_LIMIT_BACKFILL_22_23_20"


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def json_value(value: Any) -> Any:
    """Convert driver JSON values to ordinary dict/list objects for stable output."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def derive_fixture_patches(fixtures: dict) -> tuple[list[dict], list[dict]]:
    """Rebuild proposed structures and condition links from reviewed source fixtures."""
    previews, links = [], []
    for card_id, item_id in TARGETS:
        case = fixtures[f"{card_id}/{item_id}"]
        raw, rules, evidence = case["stg_raw_item"], case["rule_list"], case["evidence"]
        located = ProductBenefitService._located(evidence)
        rule_keys = [rule["rule_key"] for rule in rules]
        structure = limit_struct(raw, rule_keys, ProductBenefitService._limit_evidence(raw, located))
        issues = check_limit_struct(raw, rule_keys, structure)
        if issues:
            raise ValueError(f"Fixture {card_id}/{item_id} failed structure validation: {issues}")
        tiers = limit_tiers_from_extraction(rules, structure,
                                            ProductBenefitService._cond_evidence(raw, rules, located))
        patch = {"schema_ver": "BENEFIT_V1", **structure} if structure else {}
        if tiers:
            patch["limit_tiers"] = tiers
        previews.append({"card_id": card_id, "card_product_item_id": item_id,
                         "source_stg_id": case["card_extr_stg_id"], "item_data_patch": patch})
        for (rule_key, atom_key), evidence_ids in ProductBenefitService._cond_evidence(raw, rules, located).items():
            for evidence_id in evidence_ids:
                links.append({"card_id": card_id, "card_product_item_id": item_id,
                              "rule_key": rule_key, "ev_item_cd": "COND",
                              "ev_item_key": atom_key, "evidence_id": evidence_id})
    return previews, links


def compose_preview(fixtures: dict, current_rows: list[dict], current_links: list[dict]) -> dict:
    """Join derived changes with live SELECT results; fail closed on incomplete targets."""
    derived, expected_links = derive_fixture_patches(fixtures)
    if len(expected_links) != EXPECTED_EVIDENCE_LINKS:
        raise ValueError(f"Reviewed fixture must produce exactly {EXPECTED_EVIDENCE_LINKS} evidence links; "
                         f"found {len(expected_links)}")
    rows_by_key = {(int(row["card_id"]), str(row["card_product_item_id"])): row for row in current_rows}
    expected_keys = {(int(card_id), str(item_id)) for card_id, item_id in TARGETS}
    if set(rows_by_key) != expected_keys:
        raise ValueError(f"PostgreSQL target PK set differs from allowlist: {sorted(set(rows_by_key) ^ expected_keys)}")
    if len(rows_by_key) != len(current_rows) or len(current_rows) != len(TARGETS):
        raise ValueError(f"Expected exactly {len(TARGETS)} unique target rows, found {len(current_rows)}")
    present_links = {(int(row["card_id"]), str(row["card_product_item_id"]), row.get("rule_key"),
                      row.get("ev_item_cd"), row.get("ev_item_key"), str(row["evidence_id"]))
                     for row in current_links
                     if row.get("ev_subject_cd", "RULE") == "RULE" and row.get("relation_key") is None}
    result_rows = []
    for proposed in derived:
        key = (proposed["card_id"], proposed["card_product_item_id"])
        current = rows_by_key.get(key)
        if current is None:
            raise ValueError(f"Live PostgreSQL target missing: {key}")
        if current.get("item_type_cd") != "BENEFIT":
            raise ValueError(f"Live PostgreSQL target is not a BENEFIT: {key}")
        fixture = fixtures[f"{key[0]}/{key[1]}"]
        if current.get("item_nm") != fixture["stg_raw_item"].get("bnft_nm"):
            raise ValueError(f"Live PostgreSQL benefit name differs from fixture: {key}")
        current_rule_hash = hashlib.sha256(canonical(json_value(current.get("rule_list"))).encode("utf-8")).hexdigest()
        fixture_rule_hash = hashlib.sha256(canonical(json_value(fixture.get("rule_list"))).encode("utf-8")).hexdigest()
        if current_rule_hash != fixture_rule_hash:
            raise ValueError(f"Live PostgreSQL rule_list differs from fixture: {key}")
        item_data = json_value(current.get("item_data"))
        if not isinstance(item_data, dict):
            raise ValueError(f"Current item_data is not an object: {key}")
        before = dict(item_data)
        after = {**before, **proposed["item_data_patch"]}
        conflicts = {name for name in proposed["item_data_patch"]
                     if name in before and canonical(before[name]) != canonical(proposed["item_data_patch"][name])}
        before_lines = json.dumps(before, ensure_ascii=False, sort_keys=True, indent=2).splitlines()
        after_lines = json.dumps(after, ensure_ascii=False, sort_keys=True, indent=2).splitlines()
        result_rows.append({
            **proposed,
            "item_name": current.get("item_nm"),
            "item_type_cd": current.get("item_type_cd"),
            "item_data_before": before,
            "item_data_after_preview": after,
            "item_data_changed": canonical(before) != canonical(after),
            "item_data_json_diff": "\n".join(difflib.unified_diff(
                before_lines, after_lines, fromfile="item_data_before", tofile="item_data_after")),
            "overlapping_keys_with_different_values": sorted(conflicts),
            "item_data_before_sha256": hashlib.sha256(canonical(before).encode("utf-8")).hexdigest(),
            "rule_list_sha256": current_rule_hash,
            "unchanged_fields_preimage": {
                "item_limit_txt": current.get("item_limit_txt"),
                "item_search_txt_sha256": hashlib.sha256(str(current.get("item_search_txt") or "").encode("utf-8")).hexdigest(),
                "item_embedding_sha256": hashlib.sha256(str(current.get("item_embedding") or "").encode("utf-8")).hexdigest(),
            },
        })
    result_links = []
    for link in expected_links:
        identity = (link["card_id"], link["card_product_item_id"], link["rule_key"],
                    link["ev_item_cd"], link["ev_item_key"], link["evidence_id"])
        result_links.append({**link, "already_exists": identity in present_links})
    expected_link_keys = [(item["card_id"], item["card_product_item_id"], item["rule_key"],
                           item["ev_item_cd"], item["ev_item_key"], item["evidence_id"])
                          for item in expected_links]
    if len(set(expected_link_keys)) != len(expected_link_keys):
        raise ValueError("Fixture generated duplicate evidence-link natural keys")
    return {"mode": "READ_ONLY_DRY_RUN", "database_writes": 0,
            "targets": result_rows,
            "evidence_links": result_links,
            "evidence_link_summary": {"planned": len(result_links),
                                      "already_exists": sum(item["already_exists"] for item in result_links),
                                      "would_add": sum(not item["already_exists"] for item in result_links)},
            "backup_preimage": [{"card_id": row["card_id"], "card_product_item_id": row["card_product_item_id"],
                                 "item_data": row["item_data_before"], "item_limit_txt": row["unchanged_fields_preimage"]["item_limit_txt"],
                                 "rule_list_sha256": row["rule_list_sha256"],
                                 "item_data_sha256": row["item_data_before_sha256"],
                                 "existing_rule_cond_links": [link for link in current_links
                                     if int(link["card_id"]) == row["card_id"]
                                     and str(link["card_product_item_id"]) == row["card_product_item_id"]]} for row in result_rows],
            "notes": ["This payload is preview output; a durable preimage is required before any approved correction."]}


def write_preimage_exclusive(path: Path, payload: dict) -> None:
    """Persist a durable preimage without replacing an existing backup file."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError("Preimage path must be absolute")
    if not path.parent.is_dir():
        raise ValueError(f"Preimage directory does not exist: {path.parent}")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def rewrite_manifest(path: Path, payload: dict) -> None:
    """Atomically update a preimage manifest; never use this for the initial exclusive capture."""
    path = Path(path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent,
                                     prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
        temp_path = Path(stream.name)
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp_path, path)


def apply_corrections(connection, fixtures: dict, *, expected_database: str, expected_server_address: str,
                      preimage_path: Path) -> dict:
    """Apply the allowlisted item_data/link plan in one transaction.

    This function must only be called by the explicit CLI apply path after separate approval.
    Any mismatch or verification error raises inside the transaction and causes rollback.
    """
    with connection.transaction():
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute("SHOW transaction_read_only")
            read_only_row = cur.fetchone()
            read_only = str(next(iter(read_only_row.values())) if isinstance(read_only_row, dict) else read_only_row[0]).lower()
            if read_only not in {"off", "false"}:
                raise RuntimeError("PostgreSQL transaction is read-only; refusing correction")
            cur.execute("SELECT current_database() AS database_name, inet_server_addr()::text AS server_address")
            identity = cur.fetchone()
            if identity["database_name"] != expected_database:
                raise RuntimeError("Connected PostgreSQL database does not match --expected-database")
            if identity["server_address"] != expected_server_address:
                raise RuntimeError("Connected PostgreSQL server address does not match --expected-server-address")

            pairs_sql = ",".join(["(%s, %s)"] * len(TARGETS))
            params = tuple(value for pair in TARGETS for value in pair)
            cur.execute(f"""SELECT card_id, card_product_item_id, item_type_cd, item_nm, item_data,
                                      rule_list, item_limit_txt, item_search_txt, item_embedding
                               FROM db_pipeline.card_product_item
                               WHERE (card_id, card_product_item_id) IN ({pairs_sql})
                               ORDER BY card_id, card_product_item_id FOR UPDATE""", params)
            rows = cur.fetchall()
            cur.execute(f"""SELECT card_id, card_product_item_id, rule_key, ev_subject_cd, relation_key,
                                      ev_item_cd, ev_item_key, evidence_id, evidence_link_id
                               FROM db_pipeline.card_evidence_link
                               WHERE (card_id, card_product_item_id) IN ({pairs_sql})
                                 AND ev_subject_cd = 'RULE' AND ev_item_cd = 'COND'
                               ORDER BY card_id, rule_key, ev_item_key, evidence_id""", params)
            links = cur.fetchall()
            preview = compose_preview(fixtures, rows, links)
            conflicts = [(row["card_id"], row["card_product_item_id"], row["overlapping_keys_with_different_values"])
                         for row in preview["targets"] if row["overlapping_keys_with_different_values"]]
            if conflicts:
                raise ValueError(f"Existing item_data conflicts with reviewed patch: {conflicts}")

            expected_link_ids = list(dict.fromkeys(link["evidence_id"] for link in preview["evidence_links"]))
            cur.execute("""SELECT evidence_id, card_doc_id, page_no, card_doc_chunk_id, card_extr_stg_id,
                                  start_pos, end_pos, quote_txt
                           FROM db_pipeline.card_source_evidence WHERE evidence_id = ANY(%s)""", (expected_link_ids,))
            evidence_rows = cur.fetchall()
            evidence_by_id = {str(row["evidence_id"]): row for row in evidence_rows}
            if len(evidence_by_id) != len(expected_link_ids):
                raise ValueError("One or more reviewed condition evidence IDs are missing or duplicated")
            fixtures_by_evidence = {}
            evidence_owner = {}
            for card_id, item_id in TARGETS:
                case = fixtures[f"{card_id}/{item_id}"]
                for evidence in case["evidence"]:
                    evidence_id = str(evidence["evidence_id"])
                    if evidence_id in expected_link_ids:
                        if evidence_id in fixtures_by_evidence:
                            raise ValueError(f"Duplicate fixture evidence ID: {evidence_id}")
                        fixtures_by_evidence[evidence_id] = evidence
                        evidence_owner[evidence_id] = (card_id, item_id, case["card_extr_stg_id"])
            for evidence_id in expected_link_ids:
                expected = fixtures_by_evidence.get(evidence_id)
                actual = evidence_by_id[evidence_id]
                owner = evidence_owner.get(evidence_id)
                if expected is None or owner is None:
                    raise ValueError(f"Evidence ID is not present in the reviewed fixture: {evidence_id}")
                if actual["card_extr_stg_id"] != owner[2]:
                    raise ValueError(f"Evidence {evidence_id} is not from the reviewed extraction row")
                for field in ("start_pos", "end_pos", "quote_txt"):
                    if actual[field] != expected.get(field):
                        raise ValueError(f"Evidence {evidence_id} {field} differs from reviewed fixture")

            manifest = {
                "format": "GRAPHRAG_LIMIT_BACKFILL_PREIMAGE_V1",
                "state": "PREIMAGE_CAPTURED",
                "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                "database": identity,
                "targets": preview["targets"],
                "evidence_links_expected": preview["evidence_links"],
                "evidence_links_preimage": links,
                "evidence_source_preimage": evidence_rows,
                "rollback_policy": [
                    "Delete only evidence_link_id values recorded as inserted by this transaction, after verifying natural key.",
                    "Restore item_data_before only when current item_data still equals item_data_after_preview.",
                    "Do not restore or overwrite rule_list, item_limit_txt, item_search_txt, or item_embedding.",
                    "If commit outcome is ambiguous, inspect the database before retrying or rolling back."
                ]
            }
            write_preimage_exclusive(preimage_path, manifest)

            updated_rows = []
            for row in preview["targets"]:
                if not row["item_data_changed"]:
                    continue
                cur.execute("""UPDATE db_pipeline.card_product_item
                               SET item_data = %s::jsonb
                               WHERE card_id = %s AND card_product_item_id = %s AND item_data = %s::jsonb
                               RETURNING card_id, card_product_item_id""",
                            (canonical(row["item_data_after_preview"]), row["card_id"], row["card_product_item_id"],
                             canonical(row["item_data_before"])))
                changed = cur.fetchone()
                if changed is None:
                    raise RuntimeError(f"Compare-and-swap UPDATE failed for {(row['card_id'], row['card_product_item_id'])}")
                updated_rows.append((changed["card_id"], changed["card_product_item_id"]))

            inserted_links, existing_link_ids = [], []
            for link in preview["evidence_links"]:
                if link["already_exists"]:
                    existing_link_ids.append({"natural_key": link, "evidence_link_id": next(
                        str(item["evidence_link_id"]) for item in links
                        if int(item["card_id"]) == link["card_id"]
                        and str(item["card_product_item_id"]) == link["card_product_item_id"]
                        and item["ev_subject_cd"] == "RULE" and item["relation_key"] is None
                        and item["rule_key"] == link["rule_key"] and item["ev_item_cd"] == "COND"
                        and item["ev_item_key"] == link["ev_item_key"] and str(item["evidence_id"]) == link["evidence_id"])})
                    continue
                cur.execute("""INSERT INTO db_pipeline.card_evidence_link
                                 (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id,
                                  ev_subject_cd, card_product_item_id, rule_key, ev_item_cd, ev_item_key)
                               SELECT e.card_doc_id, e.page_no, e.card_doc_chunk_id, e.evidence_id, %s,
                                      'RULE', %s, %s, 'COND', %s
                               FROM db_pipeline.card_source_evidence e WHERE e.evidence_id = %s
                               ON CONFLICT ON CONSTRAINT card_evidence_link_natural_key DO NOTHING
                               RETURNING evidence_link_id""",
                            (link["card_id"], link["card_product_item_id"], link["rule_key"],
                             link["ev_item_key"], link["evidence_id"]))
                inserted = cur.fetchone()
                if inserted is None:
                    cur.execute("""SELECT evidence_link_id FROM db_pipeline.card_evidence_link
                                   WHERE card_id = %s AND card_product_item_id = %s AND ev_subject_cd = 'RULE'
                                     AND relation_key IS NULL AND rule_key = %s AND ev_item_cd = 'COND'
                                     AND ev_item_key = %s AND evidence_id = %s""",
                                (link["card_id"], link["card_product_item_id"], link["rule_key"],
                                 link["ev_item_key"], link["evidence_id"]))
                    inserted = cur.fetchone()
                    if inserted is None:
                        raise RuntimeError(f"Evidence-link insert did not create or find its natural key: {link}")
                    existing_link_ids.append({"natural_key": link, "evidence_link_id": str(inserted["evidence_link_id"])})
                else:
                    inserted_links.append({"natural_key": link, "evidence_link_id": str(inserted["evidence_link_id"])})

            cur.execute(f"""SELECT card_id, card_product_item_id, item_data
                           FROM db_pipeline.card_product_item
                           WHERE (card_id, card_product_item_id) IN ({pairs_sql})""", params)
            after_rows = {(int(row["card_id"]), str(row["card_product_item_id"])): json_value(row["item_data"])
                          for row in cur.fetchall()}
            for expected in preview["targets"]:
                key = (expected["card_id"], expected["card_product_item_id"])
                if after_rows.get(key) != expected["item_data_after_preview"]:
                    raise RuntimeError(f"Post-update item_data verification failed for {key}")
            cur.execute(f"""SELECT card_id, card_product_item_id, rule_key, ev_subject_cd, relation_key,
                                      ev_item_cd, ev_item_key, evidence_id, evidence_link_id
                               FROM db_pipeline.card_evidence_link
                               WHERE (card_id, card_product_item_id) IN ({pairs_sql})
                                 AND ev_subject_cd = 'RULE' AND ev_item_cd = 'COND'""", params)
            final_links = cur.fetchall()
            final_preview = compose_preview(fixtures, rows, final_links)
            missing = [link for link in final_preview["evidence_links"] if not link["already_exists"]]
            if missing:
                raise RuntimeError(f"Post-insert RULE/COND verification failed: {missing}")

            report = {"mode": "APPLY_TRANSACTION", "state": "VALIDATED_PENDING_COMMIT",
                      "database": identity, "preimage_path": str(Path(preimage_path)),
                      "item_data_updated": updated_rows, "item_data_update_count": len(updated_rows),
                      "evidence_links_inserted": inserted_links,
                      "evidence_links_already_present": existing_link_ids,
                      "evidence_link_insert_count": len(inserted_links),
                      "post_update_item_data_verified": len(after_rows) == len(TARGETS),
                      "expected_rule_cond_links_verified": len(final_preview["evidence_links"])}
            manifest["state"] = "VALIDATED_PENDING_COMMIT"
            manifest["transaction_result_pending_commit"] = report
            rewrite_manifest(preimage_path, manifest)
            return report


def rollback_corrections(connection, *, expected_database: str, expected_server_address: str,
                         preimage_path: Path) -> dict:
    """Restore the exact recorded item_data preimage and delete only links inserted by this run."""
    preimage_path = Path(preimage_path)
    manifest = json.loads(preimage_path.read_text(encoding="utf-8"))
    if manifest.get("format") != "GRAPHRAG_LIMIT_BACKFILL_PREIMAGE_V1":
        raise ValueError("Unsupported rollback preimage format")
    if manifest.get("state") not in {"COMMITTED", "ROLLBACK_PENDING"}:
        raise ValueError(f"Rollback requires a committed preimage, found state={manifest.get('state')}")
    apply_result = manifest.get("transaction_result_pending_commit") or {}
    inserted_links = apply_result.get("evidence_links_inserted") or []
    if not isinstance(apply_result, dict):
        raise ValueError("Preimage does not contain an apply result")
    expected_target_keys = {(int(card), str(item_id)) for card, item_id in TARGETS}
    manifest_target_keys = {(int(target["card_id"]), str(target["card_product_item_id"]))
                            for target in manifest.get("targets", [])}
    if manifest_target_keys != expected_target_keys or len(manifest.get("targets", [])) != len(TARGETS):
        raise ValueError("Rollback preimage target PK set differs from the correction allowlist")
    expected_links = manifest.get("evidence_links_expected") or []
    expected_natural_keys = {
        (int(item["card_id"]), str(item["card_product_item_id"]), item["rule_key"],
         item["ev_item_cd"], item["ev_item_key"], str(item["evidence_id"]))
        for item in expected_links
    }
    inserted_ids, inserted_natural_keys = set(), set()
    for record in inserted_links:
        natural = record["natural_key"]
        natural_key = (int(natural["card_id"]), str(natural["card_product_item_id"]), natural["rule_key"],
                       natural["ev_item_cd"], natural["ev_item_key"], str(natural["evidence_id"]))
        link_id = str(record["evidence_link_id"])
        if natural_key not in expected_natural_keys or natural_key in inserted_natural_keys or link_id in inserted_ids:
            raise ValueError("Rollback preimage contains an unexpected or duplicate inserted evidence link")
        inserted_natural_keys.add(natural_key)
        inserted_ids.add(link_id)

    with connection.transaction():
        with connection.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute("SHOW transaction_read_only")
            read_only_row = cur.fetchone()
            read_only = str(next(iter(read_only_row.values())) if isinstance(read_only_row, dict) else read_only_row[0]).lower()
            if read_only not in {"off", "false"}:
                raise RuntimeError("PostgreSQL transaction is read-only; refusing rollback")
            cur.execute("SELECT current_database() AS database_name, inet_server_addr()::text AS server_address")
            identity = cur.fetchone()
            if identity["database_name"] != expected_database:
                raise RuntimeError("Connected PostgreSQL database does not match --expected-database")
            if identity["server_address"] != expected_server_address:
                raise RuntimeError("Connected PostgreSQL server address does not match --expected-server-address")
            if manifest.get("database") != identity:
                raise RuntimeError("Rollback preimage belongs to a different PostgreSQL database/server")

            pairs_sql = ",".join(["(%s, %s)"] * len(TARGETS))
            params = tuple(value for pair in TARGETS for value in pair)
            cur.execute(f"""SELECT card_id, card_product_item_id, item_type_cd, item_nm, item_data,
                                      rule_list, item_limit_txt, item_search_txt, item_embedding
                               FROM db_pipeline.card_product_item
                               WHERE (card_id, card_product_item_id) IN ({pairs_sql})
                               ORDER BY card_id, card_product_item_id FOR UPDATE""", params)
            rows = cur.fetchall()
            by_key = {(int(row["card_id"]), str(row["card_product_item_id"])): row for row in rows}
            if len(by_key) != len(TARGETS) or set(by_key) != {(card, item) for card, item in TARGETS}:
                raise RuntimeError("Rollback target PK set differs from the recorded allowlist")

            manifest["state"] = "ROLLBACK_PENDING"
            manifest["rollback_started_at_utc"] = datetime.now(timezone.utc).isoformat()
            rewrite_manifest(preimage_path, manifest)

            restored_rows = []
            for target in manifest["targets"]:
                key = (int(target["card_id"]), str(target["card_product_item_id"]))
                current = json_value(by_key[key].get("item_data"))
                before, after = target["item_data_before"], target["item_data_after_preview"]
                before_hash = hashlib.sha256(canonical(before).encode("utf-8")).hexdigest()
                if before_hash != target.get("item_data_before_sha256"):
                    raise RuntimeError(f"Rollback preimage hash mismatch for {key}")
                if current == before:
                    continue
                if current != after:
                    raise RuntimeError(f"Rollback stopped: current item_data differs from recorded after-image for {key}")
                cur.execute("""UPDATE db_pipeline.card_product_item
                               SET item_data = %s::jsonb
                               WHERE card_id = %s AND card_product_item_id = %s AND item_data = %s::jsonb
                               RETURNING card_id, card_product_item_id""",
                            (canonical(before), key[0], key[1], canonical(after)))
                restored = cur.fetchone()
                if restored is None:
                    raise RuntimeError(f"Compare-and-swap rollback UPDATE failed for {key}")
                restored_rows.append(key)

            deleted_links, absent_links = [], []
            for record in inserted_links:
                natural = record["natural_key"]
                link_id = record["evidence_link_id"]
                cur.execute("""DELETE FROM db_pipeline.card_evidence_link
                               WHERE evidence_link_id = %s AND card_id = %s AND card_product_item_id = %s
                                 AND ev_subject_cd = 'RULE' AND relation_key IS NULL AND rule_key = %s
                                 AND ev_item_cd = 'COND' AND ev_item_key = %s AND evidence_id = %s
                               RETURNING evidence_link_id""",
                            (link_id, natural["card_id"], natural["card_product_item_id"], natural["rule_key"],
                             natural["ev_item_key"], natural["evidence_id"]))
                deleted = cur.fetchone()
                if deleted:
                    deleted_links.append(str(deleted["evidence_link_id"]))
                    continue
                cur.execute("""SELECT card_id, card_product_item_id, rule_key, ev_subject_cd, relation_key,
                                    ev_item_cd, ev_item_key, evidence_id, evidence_link_id
                             FROM db_pipeline.card_evidence_link WHERE evidence_link_id = %s""", (link_id,))
                remaining = cur.fetchone()
                if remaining is not None:
                    raise RuntimeError(f"Rollback refused to delete link ID with a different natural key: {link_id}")
                absent_links.append(str(link_id))

            cur.execute(f"""SELECT card_id, card_product_item_id, item_data
                           FROM db_pipeline.card_product_item
                           WHERE (card_id, card_product_item_id) IN ({pairs_sql})""", params)
            after_rows = {(int(row["card_id"]), str(row["card_product_item_id"])): json_value(row["item_data"])
                          for row in cur.fetchall()}
            for target in manifest["targets"]:
                key = (int(target["card_id"]), str(target["card_product_item_id"]))
                if after_rows.get(key) != target["item_data_before"]:
                    raise RuntimeError(f"Post-rollback item_data verification failed for {key}")
            cur.execute("SELECT evidence_link_id FROM db_pipeline.card_evidence_link WHERE evidence_link_id = ANY(%s)",
                        ([record["evidence_link_id"] for record in inserted_links],))
            remaining_ids = cur.fetchall()
            if remaining_ids:
                raise RuntimeError("Post-rollback check found correction links that still exist")

            result = {"mode": "ROLLBACK_TRANSACTION", "state": "VALIDATED_PENDING_COMMIT",
                      "database": identity, "preimage_path": str(preimage_path),
                      "item_data_restored": restored_rows,
                      "evidence_link_ids_deleted": deleted_links,
                      "evidence_link_ids_already_absent": absent_links,
                      "post_rollback_item_data_verified": len(after_rows) == len(TARGETS),
                      "inserted_link_ids_absent": True}
            manifest["rollback_result_pending_commit"] = result
            rewrite_manifest(preimage_path, manifest)
            return result


def read_live_rows() -> tuple[list[dict], list[dict]]:
    """Read target rows and matching evidence links with server-enforced read-only mode."""
    load_dotenv()
    url = os.getenv("DB_URL")
    if not url:
        raise RuntimeError("DB_URL is not configured")
    with psycopg.connect(url, connect_timeout=10, options="-c default_transaction_read_only=on") as conn:
        conn.execute("SET default_transaction_read_only = on")
        if str(conn.execute("SHOW default_transaction_read_only").fetchone()[0]).lower() not in {"on", "true"}:
            raise RuntimeError("PostgreSQL session is not read-only")
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            pairs_sql = ",".join(["(%s, %s)"] * len(TARGETS))
            params = tuple(value for pair in TARGETS for value in pair)
            cur.execute(f"""SELECT card_id, card_product_item_id, item_type_cd, item_nm, item_data,
                                      rule_list, item_limit_txt, item_search_txt, item_embedding
                               FROM db_pipeline.card_product_item
                               WHERE (card_id, card_product_item_id) IN ({pairs_sql})""", params)
            rows = cur.fetchall()
            cur.execute(f"""SELECT card_id, card_product_item_id, rule_key, ev_item_cd, ev_item_key, evidence_id
                               FROM db_pipeline.card_evidence_link
                               WHERE (card_id, card_product_item_id) IN ({pairs_sql})
                                 AND ev_subject_cd = 'RULE' AND ev_item_cd = 'COND'""", params)
            links = cur.fetchall()
    return rows, links


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="read-only preview (default)")
    parser.add_argument("--apply", action="store_true", help="apply the reviewed allowlist in one PostgreSQL transaction")
    parser.add_argument("--rollback", action="store_true", help="restore a committed run from its preimage manifest")
    parser.add_argument("--confirm-write", help=f"required with --apply: exact value {APPLY_CONFIRMATION}")
    parser.add_argument("--confirm-rollback", help=f"required with --rollback: exact value {ROLLBACK_CONFIRMATION}")
    parser.add_argument("--expected-database", help="required with --apply: exact current_database() value")
    parser.add_argument("--expected-server-address", help="required with --apply: exact inet_server_addr() value")
    parser.add_argument("--preimage-out", type=Path, help="required with --apply: new absolute durable preimage JSON path")
    parser.add_argument("--preimage", type=Path, help="required with --rollback: committed preimage manifest")
    args = parser.parse_args()
    selected = sum((args.dry_run, args.apply, args.rollback))
    if selected > 1:
        parser.error("choose only one of --dry-run, --apply, or --rollback")
    if not args.apply and not args.rollback:
        if any((args.confirm_write, args.confirm_rollback, args.expected_database,
                args.expected_server_address, args.preimage_out, args.preimage)):
            parser.error("confirmation and target flags are accepted only with --apply or --rollback")
    elif args.apply:
        if args.confirm_rollback or args.preimage:
            parser.error("rollback flags cannot be used with --apply")
        if args.confirm_write != APPLY_CONFIRMATION:
            parser.error("--apply requires the exact --confirm-write value")
        if not args.expected_database or not args.expected_server_address or args.preimage_out is None:
            parser.error("--apply requires --expected-database, --expected-server-address, and --preimage-out")
        if not args.preimage_out.is_absolute():
            parser.error("--preimage-out must be an absolute path")
    else:
        if args.confirm_write or args.preimage_out:
            parser.error("write flags cannot be used with --rollback")
        if args.confirm_rollback != ROLLBACK_CONFIRMATION:
            parser.error("--rollback requires the exact --confirm-rollback value")
        if not args.expected_database or not args.expected_server_address or args.preimage is None:
            parser.error("--rollback requires --expected-database, --expected-server-address, and --preimage")
        if not args.preimage.is_absolute():
            parser.error("--preimage must be an absolute path")

    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if not args.apply and not args.rollback:
        rows, links = read_live_rows()
        print(json.dumps(compose_preview(fixtures, rows, links), ensure_ascii=False, indent=2, default=str))
        return

    load_dotenv()
    url = os.getenv("DB_URL")
    if not url:
        raise RuntimeError("DB_URL is not configured")
    with psycopg.connect(url, connect_timeout=10) as conn:
        if args.apply:
            report = apply_corrections(conn, fixtures, expected_database=args.expected_database,
                                       expected_server_address=args.expected_server_address,
                                       preimage_path=args.preimage_out)
            manifest_path = args.preimage_out
            final_state = "COMMITTED"
            time_field = "committed_at_utc"
        else:
            report = rollback_corrections(conn, expected_database=args.expected_database,
                                          expected_server_address=args.expected_server_address,
                                          preimage_path=args.preimage)
            manifest_path = args.preimage
            final_state = "ROLLED_BACK"
            time_field = "rolled_back_at_utc"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["state"] = final_state
    manifest[time_field] = datetime.now(timezone.utc).isoformat()
    rewrite_manifest(manifest_path, manifest)
    report["state"] = final_state
    report["preimage_state"] = manifest["state"]
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
