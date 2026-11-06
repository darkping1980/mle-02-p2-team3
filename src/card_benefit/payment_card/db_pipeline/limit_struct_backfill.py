"""Read-only preview of the three GraphRAG limit-structure corrections.

This module intentionally has no write path. It reads the current PostgreSQL
rows, derives the proposed ``item_data`` and RULE/COND evidence links from the
reviewed extraction fixtures with the same P1 helpers as registration, then
prints before/after JSON plus a rollback-oriented preimage snapshot.

Run from ``src/card_benefit`` with ``python -m payment_card.db_pipeline.limit_struct_backfill --dry-run``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
    rows_by_key = {(int(row["card_id"]), str(row["card_product_item_id"])): row for row in current_rows}
    present_links = {(int(row["card_id"]), str(row["card_product_item_id"]), row.get("rule_key"),
                      row.get("ev_item_cd"), row.get("ev_item_key"), str(row["evidence_id"]))
                     for row in current_links}
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
        item_data = json_value(current.get("item_data")) or {}
        if not isinstance(item_data, dict):
            raise ValueError(f"Current item_data is not an object: {key}")
        before = dict(item_data)
        after = {**before, **proposed["item_data_patch"]}
        conflicts = {name for name in proposed["item_data_patch"]
                     if name in before and canonical(before[name]) != canonical(proposed["item_data_patch"][name])}
        result_rows.append({
            **proposed,
            "item_name": current.get("item_nm"),
            "item_type_cd": current.get("item_type_cd"),
            "item_data_before": before,
            "item_data_after_preview": after,
            "item_data_changed": canonical(before) != canonical(after),
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
            "notes": ["No UPDATE/INSERT/DELETE/DDL path exists in this tool.",
                      "The backup_preimage is a preview payload only; a separately approved, durable backup is required before any later correction."]}


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
    parser.add_argument("--dry-run", action="store_true", required=True,
                        help="required: this preview tool does not implement writes")
    parser.parse_args()
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    rows, links = read_live_rows()
    print(json.dumps(compose_preview(fixtures, rows, links), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
