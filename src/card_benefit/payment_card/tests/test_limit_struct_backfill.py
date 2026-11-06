"""Read-only preview tool contract tests; no PostgreSQL connection is opened."""
from __future__ import annotations

import json
from pathlib import Path

from payment_card.db_pipeline.limit_struct_backfill import (
    TARGETS,
    compose_preview,
    derive_fixture_patches,
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
        assert "Live PostgreSQL target missing" in str(error)
    else:
        raise AssertionError("missing live target must block preview")
