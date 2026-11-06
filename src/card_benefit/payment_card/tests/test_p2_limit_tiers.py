"""Regression checks for source-row tier context and relation-aware answer validation."""
import json

from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag as g


def detail(item_data):
    benefit = {"card_id": 23, "card_product_item_id": "20261105_000100",
               "item_type_cd": "BENEFIT", "item_nm": "특별·추가 적립",
               "item_rule_txt": "특별 및 추가 적립", "item_limit_txt": "통합 월 적립 한도",
               "item_data": item_data, "item_cond_expr": None, "rule_list": [], "relation_list": []}
    return {"context": {"card": {"source_json": json.dumps({"card_id": 23, "product_nm": "카드의정석 POINT II"})},
                        "benefit": {"source_json": json.dumps(benefit)}, "common": None},
            "rules": [], "conditions": [], "limits": [], "evidence": []}


def tiers():
    return {"limit_tiers": {"basis_cd": "PREV_MONTH_SPEND", "own": {"column": "own_cap", "caps": {
        "t30": {"raw": "1만원", "amount": 10000}, "t60": {"raw": "2만원", "amount": 20000},
        "t120": {"raw": "5만원", "amount": 50000}}}, "tiers": [
            {"tier_key": "t30", "label": "30만원 이상", "min_amt": 300000},
            {"tier_key": "t60", "label": "60만원 이상", "min_amt": 600000},
            {"tier_key": "t120", "label": "120만원 이상", "min_amt": 1200000}]}}


def test_original_item_data_is_carried_to_context_without_creating_payment_rules():
    benefit = g.benefit_context(detail(tiers()))
    assert benefit["benefit_id"] == "20261105_000100"
    assert benefit["name"] == "특별·추가 적립"
    assert [(row["min_amt"], row["cap"]["amount"]) for row in benefit["limit_tiers"]] == [
        (300000, 10000), (600000, 20000), (1200000, 50000)]
    assert benefit["rules"] == []


def test_limit_tier_validator_rejects_a_wrong_spend_to_cap_pair():
    benefit = g.benefit_context(detail(tiers()))
    assert not g.distorts_limit_tier("전월 실적 60만원 이상이면 통합 월 한도 2만원입니다.", [benefit])
    assert g.distorts_limit_tier("전월 실적 60만원 이상이면 통합 월 한도 1만원입니다.", [benefit])


def test_previous_month_spend_parser_does_not_treat_payment_as_spend():
    assert g.previous_month_spend("전월 실적 60만원이면 한도는?") == 600000
    assert g.previous_month_spend("60만원 결제하면?") is None


def test_extraction_stage_explicit_keys_preserve_spend_to_limit_pair_and_evidence_ids():
    condition_quote = "전월 국내가맹점 이용실적 60만원 이상"
    cap_quote = "2만원"
    raw = {"stg_sql_check_cd": "LINK_REVIEW", "stg_raw_item": json.dumps({
        "rules": [
            {"rule_key": "r1", "conditions": [{"cond_key": "c1", "cond_type_cd": "SPEND_REQ", "cond_basis_cd": "PREV_MONTH_SPEND",
                         "cond_min_amt": 300000, "cond_raw_txt": "전월 실적 30만원 이상"}], "limit_keys": ["l1"]},
            {"rule_key": "r2", "conditions": [{"cond_key": "c2", "cond_type_cd": "SPEND_REQ",
                         "cond_basis_cd": "PREV_MONTH_SPEND", "cond_min_amt": 600000, "cond_raw_txt": condition_quote}], "limit_keys": ["l2"]},
            {"rule_key": "r3", "conditions": [{"cond_key": "c3", "cond_type_cd": "SPEND_REQ", "cond_basis_cd": "PREV_MONTH_SPEND",
                         "cond_min_amt": 1200000, "cond_raw_txt": "전월 실적 120만원 이상"}], "limit_keys": ["l3"]}],
        "limits": [{"limit_key": "l1", "limit_num": 10000, "cap_unit_cd": "KRW", "limit_raw_txt": "1만원"},
                   {"limit_key": "l2", "limit_num": 20000, "cap_unit_cd": "KRW", "limit_raw_txt": cap_quote},
                   {"limit_key": "l3", "limit_num": 50000, "cap_unit_cd": "KRW", "limit_raw_txt": "5만원"}]})}
    extraction_sources = [json.dumps(raw)]
    evidence = [{"evidence": {"source_json": json.dumps({"evidence_id": "COND_EVIDENCE", "quote_txt": condition_quote})}},
                {"evidence": {"source_json": json.dumps({"evidence_id": "CAP_EVIDENCE", "quote_txt": cap_quote})}}]
    mapping = g.extraction_limit_tier_view(extraction_sources, evidence)
    tier = next(row for row in mapping if row["min_amt"] == 600000)
    assert (tier["min_amt"], tier["cap"]["amount"]) == (600000, 20000)
    assert tier["evidence_ids"] == ["COND_EVIDENCE", "CAP_EVIDENCE"]
    assert tier["review_status"] == "LINK_REVIEW"
    benefit = {"benefit_id": "card_product_item:23:POINT2", "limit_tiers": mapping}
    assert not g.distorts_limit_tier("전월 실적 60만원 이상이면 2만원 한도입니다.", [benefit])
    assert g.distorts_limit_tier("전월 실적 60만원 이상이면 1만원 한도입니다.", [benefit])


def test_extraction_stage_sibling_evidence_is_kept_for_limit_answers():
    detail_row = {"context": {"benefit": {"source_json": json.dumps({"card_product_item_id": "POINT2",
                                                                        "item_nm": "특별·추가 적립"})}},
                  "evidence": [{"link": {"source_table": "derived:card_evidence_link+card_source_evidence+card_extr_stg"},
                                "evidence": {"source_json": json.dumps({"evidence_id": "20261105_002745",
                                                                         "page_no": 3, "quote_txt": "60만원 이상"})}}]}
    evidence = g.collect_evidence([detail_row], "BENEFIT_LIMIT")
    assert [row["evidence_id"] for row in evidence] == ["20261105_002745"]
    assert evidence[0]["subjects"] == ["EXTRACTION_STAGE"]
