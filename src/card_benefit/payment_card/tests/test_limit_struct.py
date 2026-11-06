"""추출 한도 구조 보존(P1, 2026-11-06). DB를 쓰지 않는다.

fixture(fixtures_limit_struct.json)는 실제 추출 이력(card_extr_stg)·등록 규칙(card_product_item.rule_list)·원문 근거
(card_source_evidence)를 읽기 전용으로 옮긴 것이다. source_txt는 위치 확인을 통과한 상태를 재현하려고 quote_txt와 같게 두었다.
    22/20261105_000099 더 심플 하나카드 월납 요금: 전월 실적 구간 r1(30만~80만)→10,000원, r2(80만~)→15,000원
    23/20261105_000100 카드의정석 POINT II 간편결제 추가적립: 30만·60만·120만원 '이상'(상한 없음)→1만·2만·5만원
    20/20261105_000092 JADE First 골프/아울렛: 2,400만원 시 10만원, 3,600만원 시 10만원 '추가'(누적형)
"""
import copy
import json
from pathlib import Path

import pytest

from payment_card.db_pipeline.extraction_service import check_limit_struct, limit_struct, limit_tiers_from_extraction
from payment_card.db_pipeline.product_benefit_service import ProductBenefitService

FIXTURES = json.loads((Path(__file__).with_name("fixtures_limit_struct.json")).read_text(encoding="utf-8"))
SIMPLE, POINT2, JADE = "22/20261105_000099", "23/20261105_000100", "20/20261105_000092"


def parts(name):
    case = copy.deepcopy(FIXTURES[name])
    return case["stg_raw_item"], case["rule_list"], case["evidence"]


def build(name):
    raw, rules, evidence = parts(name)
    located = ProductBenefitService._located(evidence)
    keys = [rule["rule_key"] for rule in rules]
    struct = limit_struct(raw, keys, ProductBenefitService._limit_evidence(raw, located))
    tiers = limit_tiers_from_extraction(rules, struct, ProductBenefitService._cond_evidence(raw, rules, located))
    return raw, rules, struct, tiers


def test_simple_monthly_tiers_keep_rule_to_cap_mapping():
    raw, rules, struct, tiers = build(SIMPLE)
    assert [(item["limit_key"], item["limit_num"], item["cap_unit_cd"], item["period_cd"]) for item in struct["limits"]] == [
        ("l1", 10000, "KRW", "MONTH"), ("l2", 15000, "KRW", "MONTH")]
    assert struct["limits"][0]["evidence_ids"] == ["20261105_002681"]          # '10,000원'
    assert struct["limits"][1]["evidence_ids"] == ["20261105_002682"]          # '15,000원'
    assert struct["rule_limits"] == {"r1": ["l1"], "r2": ["l2"], "r3": ["l1", "l2"]}
    assert check_limit_struct(raw, [r["rule_key"] for r in rules], struct) == []
    assert tiers is not None and tiers["source"] == "EXTRACTION" and tiers["basis_cd"] == "PREV_MONTH_SPEND"
    assert [(t["rule_key"], t["min_amt"], t["max_amt_excl"], t["label"]) for t in tiers["tiers"]] == [
        ("r1", 300000, 800000, "30만원 이상 80만원 미만"), ("r2", 800000, None, "80만원 이상")]   # 최상위 구간만 상한 없음
    assert [t["evidence_ids"] for t in tiers["tiers"]] == [["20261105_002685"], ["20261105_002686"]]
    assert {k: (v["amount"], v["raw"], v["limit_key"]) for k, v in tiers["own"]["caps"].items()} == {
        "r1": (10000, "10,000원", "l1"), "r2": (15000, "15,000원", "l2")}


def test_rule_values_are_not_replaced_by_limits():
    """한도와 지급액은 다른 의미다. 등록 규칙의 value_num·value_unit_cd는 그대로 null이다."""
    _, rules, struct, _ = build(SIMPLE)
    assert [(rule["value_num"], rule["value_unit_cd"]) for rule in rules] == [(None, None)] * 3
    assert all(set(rule) == {"rule_key", "cond_expr", "target_list", "value_num", "value_unit_cd", "rule_status_cd"} for rule in rules)
    assert "limits" not in json.dumps(rules)


def test_overlapping_tiers_without_upper_bound_keep_caps_but_no_tier_table():
    """23/100: 원문 구간 표기에 상한이 없어 구간이 겹친다. 한도·연결은 보존하고 상한은 추론하지 않는다."""
    raw, rules, struct, tiers = build(POINT2)
    assert [(item["limit_key"], item["limit_num"]) for item in struct["limits"]] == [("l1", 10000), ("l2", 20000), ("l3", 50000)]
    assert [item["evidence_ids"] for item in struct["limits"]] == [["20261105_002739"], ["20261105_002740"], ["20261105_002741"]]
    assert struct["rule_limits"] == {"r1": ["l1"], "r2": ["l2"], "r3": ["l3"]}
    assert check_limit_struct(raw, [r["rule_key"] for r in rules], struct) == []
    assert tiers is None
    assert all(atom["cond_max_amt_excl"] is None for rule in rules for b in rule["cond_expr"]["branches"] for atom in b["atoms"])


def test_cumulative_bonus_caps_are_not_turned_into_exclusive_tiers():
    """20/092: '10만원 제공 / 10만원 추가 제공'은 누적형이다. 구간 표(limit_tiers)를 만들지 않는다."""
    raw, rules, struct, tiers = build(JADE)
    assert [(item["limit_key"], item["limit_num"], item["period_cd"]) for item in struct["limits"]] == [
        ("bonus_base_cap", 100000, "UNKNOWN"), ("bonus_additional_cap", 100000, "UNKNOWN")]
    assert struct["rule_limits"] == {"bonus_base_discount": ["bonus_base_cap"],
                                     "bonus_additional_cap_discount": ["bonus_additional_cap"]}
    assert tiers is None
    assert "합계" not in json.dumps(struct, ensure_ascii=False) and 200000 not in [i["limit_num"] for i in struct["limits"]]


def test_rule_keys_match_extraction_and_unregistered_rules_are_dropped():
    raw, rules, _ = parts(SIMPLE)
    struct = limit_struct(raw, ["r1", "r2"], {})                    # r3를 등록하지 않는 경우
    assert struct["rule_limits"] == {"r1": ["l1"], "r2": ["l2"]}
    assert check_limit_struct(raw, ["r1", "r2"], struct) == []
    broken = copy.deepcopy(struct)
    broken["rule_limits"]["r1"] = ["l2"]
    broken["limits"][0]["limit_num"] = 15000
    issues = check_limit_struct(raw, ["r1", "r2"], broken)
    assert any("한도 값" in item for item in issues) and any("r1" in item for item in issues)


def test_benefit_without_limits_keeps_empty_structure():
    raw = {"bnft_nm": "기본적립", "rules": [{"rule_key": "r1", "limit_keys": []}], "evidence": []}
    assert limit_struct(raw, ["r1"], {}) == {}


def test_tier_table_requires_evidence_for_every_tier():
    raw, rules, evidence = parts(SIMPLE)
    evidence = [e for e in evidence if e["evidence_id"] != "20261105_002686"]   # 80만원 구간 근거가 없으면
    located = ProductBenefitService._located(evidence)
    struct = limit_struct(raw, [r["rule_key"] for r in rules], ProductBenefitService._limit_evidence(raw, located))
    assert limit_tiers_from_extraction(rules, struct, ProductBenefitService._cond_evidence(raw, rules, located)) is None
    assert struct["rule_limits"]["r2"] == ["l2"]                      # 구조 보존은 그대로


def test_links_add_rule_condition_evidence_in_existing_rule_cond_form():
    raw, rules, evidence = parts(SIMPLE)
    links, problem = ProductBenefitService._links(raw, rules, evidence)
    assert problem is None
    assert (("COND", "r1", "c1"), "20261105_002685") in links
    assert (("COND", "r2", "c2"), "20261105_002686") in links
    assert (("COND", "r3", "c3"), "20261105_002687") in links
    assert (None, "20261105_002681") in links and (None, "20261105_002682") in links   # 기존 혜택 근거는 그대로
    assert ("r1", "20261105_002677") in links and ("r2", "20261105_002677") in links


def test_links_skip_condition_quotes_without_location_and_keep_old_result():
    raw, rules, evidence = parts(SIMPLE)
    unlocated = [e for e in evidence if e["evidence_id"] not in ("20261105_002685", "20261105_002686", "20261105_002687")]
    links, problem = ProductBenefitService._links(raw, rules, unlocated)
    assert problem is None
    assert not any(isinstance(key, tuple) and key[0] == "COND" for key, _ in links)


class Repo:
    def __init__(self):
        self.writes = []

    def one(self, name, **params):
        assert name == "find_benefit"
        return None

    def write(self, name, **params):
        self.writes.append((name, params))
        return [{"card_bnft_id": "NEW1"}] if name == "insert_local_benefit" else []


def candidate(name, **extra):
    raw, rules, _ = parts(name)
    return {"card_extr_stg_id": FIXTURES[name]["card_extr_stg_id"], "card_doc_id": "D", "stg_status": "PENDING_REVIEW",
            "check_cd": "LINK_REVIEW", "stg_raw_item": raw, "reviewed_unresolved_links": [],
            "normalized": {"bnft_cd": "BNFT_X", "bnft_nm": raw["bnft_nm"], "bnft_type_cd": "DISCOUNT", "is_common_candidate": False,
                           "relation_list": [], "bnft_cond_expr": None, "rule_list": rules}, **extra}


def register(name, **extra):
    service = ProductBenefitService(session=object())
    service.repo = Repo()
    decision = service._register(22, candidate(name, **extra), parts(name)[2])
    return decision, service.repo.writes


def test_register_stores_structure_in_item_data_and_keeps_limit_text():
    decision, writes = register(SIMPLE)
    assert decision.status == "INSERTED"
    params = next(p for n, p in writes if n == "insert_local_benefit")
    data = params["DATA"].obj
    assert data["schema_ver"] == "BENEFIT_V1"
    assert data["rule_limits"] == {"r1": ["l1"], "r2": ["l2"], "r3": ["l1", "l2"]}
    assert [t["rule_key"] for t in data["limit_tiers"]["tiers"]] == ["r1", "r2"]
    assert params["LIMIT_TXT"] == FIXTURES[SIMPLE]["item_limit_txt"]                # 원문 인용 텍스트는 바뀌지 않는다
    assert [r["value_num"] for r in params["RULES"].obj] == [None, None, None]
    cond = [p for n, p in writes if n == "insert_rule_cond_evidence_link"]
    assert {(p["RULE_KEY"], p["ATOM_KEY"], p["EVIDENCE_ID"]) for p in cond} >= {
        ("r1", "c1", "20261105_002685"), ("r2", "c2", "20261105_002686")}


def test_register_keeps_human_limit_tiers_patch_first():
    patch_tiers = {"schema_ver": "LIMIT_TIERS_V1", "basis_cd": "PREV_MONTH_SPEND", "table_quote": "표",
                   "tiers": [{"tier_key": "t1", "label": "30만원 이상", "min_amt": 300000, "max_amt_excl": None}],
                   "own": {"column": "월 할인 한도", "merged_cell": False, "caps": {"t1": {"raw": "10,000원", "amount": 10000}}},
                   "shared": []}
    decision, writes = register(SIMPLE, limit_tiers=patch_tiers)
    params = next(p for n, p in writes if n == "insert_local_benefit")
    assert params["DATA"].obj["limit_tiers"] == patch_tiers
    assert params["LIMIT_TXT"] == "30만원 이상: 월 할인 한도 10,000원"                 # 기존 사람 보정 동작 유지
    assert params["DATA"].obj["rule_limits"]["r1"] == ["l1"]


@pytest.mark.parametrize("name", [POINT2, JADE])
def test_register_without_clear_tiers_stores_limits_only(name):
    decision, writes = register(name)
    assert decision.status == "INSERTED"
    data = next(p for n, p in writes if n == "insert_local_benefit")["DATA"].obj
    assert "limit_tiers" not in data and data["limits"] and data["rule_limits"]


def test_register_benefit_without_limits_keeps_old_item_data():
    raw = {"bnft_nm": "기본적립", "rules": [{"rule_key": "r1", "limit_keys": []}],
           "evidence": [{"supports": "BNFT", "quote_txt": "기본적립"}, {"supports": "RULE", "support_key": "r1", "quote_txt": "0.8%"}]}
    evidence = [{"evidence_id": "E1", "quote_txt": "기본적립", "start_pos": 1, "end_pos": 4, "source_txt": "기본적립"},
                {"evidence_id": "E2", "quote_txt": "0.8%", "start_pos": 5, "end_pos": 8, "source_txt": "0.8%"}]
    rules = [{"rule_key": "r1", "cond_expr": None, "target_list": [], "value_num": 0.8, "value_unit_cd": "PERCENT", "rule_status_cd": "DRAFT"}]
    item = {"card_extr_stg_id": "S", "card_doc_id": "D", "stg_status": "PENDING_REVIEW", "check_cd": "OK", "stg_raw_item": raw,
            "reviewed_unresolved_links": [], "normalized": {"bnft_cd": "B", "bnft_nm": "기본적립", "bnft_type_cd": "POINT",
                                                            "is_common_candidate": False, "relation_list": [], "bnft_cond_expr": None,
                                                            "rule_list": rules}}
    service = ProductBenefitService(session=object())
    service.repo = Repo()
    assert service._register(40, item, evidence).status == "INSERTED"
    params = next(p for n, p in service.repo.writes if n == "insert_local_benefit")
    assert params["DATA"].obj == {}
    assert [n for n, _ in service.repo.writes] == ["insert_local_benefit", "insert_evidence_link", "insert_rule_evidence_link"]
