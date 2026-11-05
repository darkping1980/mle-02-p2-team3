"""사람 검토 보정 대장과 개별 혜택 등록의 관계·근거 처리(2026-11-05). DB를 쓰지 않는다."""
import copy
import json

import pytest

from payment_card.db_pipeline.benefit_review_patch import apply_patch, load_patches, provenance, usable
from payment_card.db_pipeline.product_benefit_service import ProductBenefitService


def raw_item():
    return {"item_key": "b1", "bnft_nm": "국내외 가맹점 청구할인", "bnft_type_cd": "DISCOUNT", "certainty": "HIGH",
            "targets": [{"target_type_cd": "UNKNOWN", "target_nm": "국내외 가맹점"}],
            "rules": [{"rule_key": "r1", "value_raw_txt": "0.8%", "value_num": "0.8", "value_unit_cd": "PERCENT"}],
            "relations": [{"relation_key": "to_group", "rel_type_cd": "OVERRIDES", "to_benefit_nm": "특별할인"}],
            "evidence": [{"quote_txt": "국내외 가맹점 0.8% 청구할인", "supports": "BNFT", "support_key": None, "link_basis": "SAME_TEXT"}]}


def patch(*ops, status="APPROVED"):
    return {"patch_id": "P1", "run_id": "R1", "card_extr_stg_id": "S1", "status": status, "reason": "시험", "ops": list(ops), "ledger": "t.json"}


def test_patch_ops_change_only_a_copy_and_record_new_quotes():
    original = raw_item()
    snapshot = copy.deepcopy(original)
    out, quotes, _ = apply_patch(original, patch(
        {"op": "SET_TARGET_TYPE", "target_nm": "국내외 가맹점", "target_type_cd": "CHANNEL"},
        {"op": "ADD_EVIDENCE", "supports": "RULE", "support_key": "r1", "quote_txt": "※ 매출 건당 1만원 이상"},
        {"op": "DROP_RELATION", "relation_key": "to_group", "reason": "묶음 이름 대상"},
        {"op": "ADD_RELATION", "relation": {"relation_key": "fb", "rel_type_cd": "FALLBACK_AFTER_CAP", "to_benefit_nm": "기본"},
         "quote_txt": "한도 초과 시 기본할인"}))
    assert original == snapshot                                            # 추출 원본은 바뀌지 않음
    assert out["targets"][0]["target_type_cd"] == "CHANNEL"
    assert [r["relation_key"] for r in out["relations"]] == ["fb"]
    assert {(e["supports"], e["support_key"]) for e in out["evidence"]} >= {("RULE", "r1"), ("REL", "fb")}
    assert quotes == ["※ 매출 건당 1만원 이상", "한도 초과 시 기본할인"]


@pytest.mark.parametrize("op", [
    {"op": "SET_TARGET_TYPE", "target_nm": "없는 대상", "target_type_cd": "CHANNEL"},
    {"op": "SET_TARGET_TYPE", "target_nm": "국내외 가맹점", "target_type_cd": "NOT_A_TYPE"},   # 추출 스키마 밖 값
    {"op": "ADD_EVIDENCE", "supports": "RULE", "support_key": "r9", "quote_txt": "x"},
    {"op": "ADD_EVIDENCE", "supports": "BNFT", "quote_txt": ""},
    {"op": "DROP_RELATION", "relation_key": "none", "reason": "x"},
    {"op": "DROP_RELATION", "relation_key": "to_group"},                                       # 사유 없음
    {"op": "ADD_RELATION", "relation": {"relation_key": "to_group", "rel_type_cd": "OVERRIDES", "to_benefit_nm": "x"}, "quote_txt": "x"},
])
def test_invalid_patch_ops_are_rejected(op):
    with pytest.raises(Exception):
        apply_patch(raw_item(), patch(op))


def test_ledger_validation_and_draft_gating(tmp_path):
    good = {"ledger_version": 1, "kind": "BENEFIT_REVIEW_PATCH", "patches": [
        {**patch({"op": "SET_TARGET_TYPE", "target_nm": "국내외 가맹점", "target_type_cd": "CHANNEL"}), "status": "DRAFT_PENDING_USER_REVIEW"},
        {**patch({"op": "ADD_EVIDENCE", "supports": "BNFT", "quote_txt": "x"}), "card_extr_stg_id": "S2"}]}
    for p in good["patches"]:
        p.pop("ledger")
    path = tmp_path / "ok.json"
    path.write_text(json.dumps(good, ensure_ascii=False), encoding="utf-8")
    loaded = load_patches([path])
    assert set(usable(loaded, "R1", allow_draft=False)) == {"S2"}           # 운영 기본: APPROVED만
    assert set(usable(loaded, "R1", allow_draft=True)) == {"S1", "S2"}
    assert provenance(loaded[0])["ops"] == ["SET_TARGET_TYPE"]
    for broken in ({**good, "kind": "OTHER"},
                   {**good, "patches": [{**good["patches"][0], "status": "SOMETHING"}]},
                   {**good, "patches": [{**good["patches"][0], "ops": [{"op": "DELETE_ALL"}]}]},
                   {**good, "patches": [good["patches"][0], good["patches"][0]]}):      # 같은 후보 두 번
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ValueError):
            load_patches([bad])


def located(evidence_id, quote):
    return {"evidence_id": evidence_id, "quote_txt": quote, "start_pos": 1, "end_pos": len(quote), "source_txt": quote}


def test_relation_quotes_link_as_rel_only_for_stored_relations():
    raw = {"evidence": [{"supports": "BNFT", "quote_txt": "혜택"}, {"supports": "RULE", "support_key": "r1", "quote_txt": "1%"},
                        {"supports": "REL", "support_key": "fb", "quote_txt": "한도 초과 시 기본할인"}]}
    evidence = [located("E1", "혜택"), located("E2", "1%"), located("E3", "한도 초과 시 기본할인")]
    links, problem = ProductBenefitService._links(raw, [{"rule_key": "r1"}], evidence, {"fb"})
    assert problem is None and links == [(None, "E1"), ("r1", "E2"), (("REL", "fb"), "E3")]
    legacy, _ = ProductBenefitService._links(raw, [{"rule_key": "r1"}], evidence)          # 저장하지 않는 관계 → 예전처럼 혜택 근거
    assert legacy == [(None, "E1"), ("r1", "E2"), (None, "E3")]


class Repo:
    def __init__(self, rows):
        self.rows_by_cd = rows

    def one(self, name, **params):
        assert name == "find_benefit"
        return self.rows_by_cd.get((params["CARD_ID"], params["BNFT_CD"]))


def test_relations_resolve_only_to_registered_benefits_of_the_same_card():
    service = ProductBenefitService(session=object())
    service.repo = Repo({(42, "BNFT_BASIC"): {"card_bnft_id": "I146", "item_type_cd": "BENEFIT"},
                         (42, "TERMS_X"): {"card_bnft_id": "I200", "item_type_cd": "TERMS"},
                         (7, "BNFT_OTHER"): {"card_bnft_id": "I300", "item_type_cd": "BENEFIT"}})
    rel = {"relation_key": "fb", "to_bnft_id": "BNFT_BASIC", "rel_type_cd": "FALLBACK_AFTER_CAP", "trigger_limit_key": None, "rel_priority": None}
    resolved, problem = service._resolve_relations(42, [rel])
    assert problem is None and resolved == [{"relation_key": "fb", "to_bnft_id": "I146", "rel_type_cd": "FALLBACK_AFTER_CAP", "rel_priority": None}]
    for target in ("BNFT_MISSING", "TERMS_X", "BNFT_OTHER"):                                # 미등록, 혜택 아님, 다른 카드
        resolved, problem = service._resolve_relations(42, [{**rel, "to_bnft_id": target}])
        assert resolved is None and problem


# region 규칙 대상 묶음·한도 구간·공유 한도(2026-11-05)
from payment_card.db_pipeline.benefit_review_patch import (  # noqa: E402
    check_limit_tiers, extracted_shared_members, limit_tiers_text, restrict_rule_targets, shared_limit_problems,
)

TABLE = ("월 할인한도\n전월실적\nA 할인\nB 할인\n통합 할인한도\n50만원 이상 100만원 미만\n3,000원\n5,000원\n8,000원\n"
         "100만원 이상\n6,000원\n11,000원")
A, B = "A 영역 5% 청구할인", "B 50% 청구할인"


def cond(key, text, **extra):
    return {"scope": "THIS_BENEFIT", "cond_key": key, "cond_type_cd": "MERCHANT_RULE", "negate_yn": False,
            "cond_raw_txt": text, "target_benefit_nms": [],
            "evidence": [{"supports": "COND", "quote_txt": text, "support_key": key, "link_basis": "SAME_TEXT"}], **extra}


def grouped_item():
    tier = cond("tier50", "50만원 이상 100만원 미만", cond_type_cd="SPEND_REQ", cond_basis_cd="PREV_MONTH_SPEND", cond_min_amt=500000)
    return {"item_key": "a", "bnft_nm": A, "bnft_type_cd": "DISCOUNT", "certainty": "HIGH",
            "targets": [{"target_type_cd": "MERCHANT", "target_nm": n} for n in ("가", "나", "다", "라")],
            "rules": [{"rule_key": "r50", "value_raw_txt": "5%", "value_num": "5", "value_unit_cd": "PERCENT",
                       "limit_keys": ["cap50"], "conditions": [tier]},
                      {"rule_key": "r100", "value_raw_txt": "5%", "value_num": "5", "value_unit_cd": "PERCENT"}],
            "conditions": [cond("min_txn", "매출 건당 3만원 이상(단, 라는 조건 없음)"), cond("ga_only", "가 앱 결제 건에 한함")],
            "limits": [{"limit_key": "cap50", "limit_num": 8000, "period_cd": "MONTH", "cap_unit_cd": "KRW", "limit_raw_txt": "8,000원",
                        "shared_scope_txt": "통합 할인한도", "applies_to_benefit_nms": [A, B]}],
            "evidence": [{"quote_txt": "A 영역 5%", "supports": "RULE", "support_key": "r50", "link_basis": "SAME_TEXT"},
                         {"quote_txt": "A 영역 5%", "supports": "RULE", "support_key": "r100", "link_basis": "SAME_TEXT"}]}


TIERS = [{"tier_key": "t1", "label": "50만원 이상 100만원 미만", "min_amt": 500000, "max_amt_excl": 1000000},
         {"tier_key": "t2", "label": "100만원 이상", "min_amt": 1000000, "max_amt_excl": None}]


def columns(b_merged=True, total_t2="11,000원"):
    b = {"column": "B 할인", "caps": {"t1": "5,000원", "t2": "5,000원"}}
    if b_merged:
        b["merged_cell"] = True
    return [{"column": "A 할인", "caps": {"t1": "3,000원", "t2": "6,000원"}}, b,
            {"column": "통합 할인한도", "caps": {"t1": "8,000원", "t2": total_t2}}]


def tiers_op(own, **extra):
    base = {"op": "SET_LIMIT_TIERS", "table_quote": TABLE, "basis_cd": "PREV_MONTH_SPEND", "tiers": TIERS, "columns": columns(),
            "own_column": own, "shared": [{"group_key": "DOC:통합", "column": "통합 할인한도", "member_benefit_nms": [A, B]}]}
    base.update(extra)
    return base


def split_ops():
    return [{"op": "DROP_RULE", "rule_key": "r100", "reason": "구간별 복제 규칙"},
            {"op": "SPLIT_RULE", "rule_key": "r50", "source_conditions": "DROP", "reason": "구간 조건은 한도 구간으로 기록",
             "into": [{"rule_key": "g.ga", "target_nms": ["가"]}, {"rule_key": "g.na", "target_nms": ["나", "다"]},
                      {"rule_key": "g.ra", "target_nms": ["라"]}]},
            {"op": "MOVE_CONDITION", "cond_key": "ga_only", "rule_keys": ["g.ga"], "for_targets": ["가"]},
            {"op": "MOVE_CONDITION", "cond_key": "min_txn", "rule_keys": ["g.ga", "g.na"], "for_targets": ["가", "나", "다"]}]


def test_split_rule_binds_each_rule_to_its_own_targets_and_conditions():
    original = grouped_item()
    out, quotes, extras = apply_patch(original, patch(*split_ops(), tiers_op("A 할인")))
    assert original == grouped_item()                                                  # 원본 불변
    rules = {r["rule_key"]: r for r in out["rules"]}
    assert list(rules) == ["g.ga", "g.na", "g.ra"]
    assert extras["rule_targets"] == {"g.ga": ["가"], "g.na": ["나", "다"], "g.ra": ["라"]}
    conds = {k: [c["cond_key"] for c in r.get("conditions", [])] for k, r in rules.items()}
    assert conds == {"g.ga": ["g.ga.ga_only", "g.ga.min_txn"], "g.na": ["g.na.min_txn"], "g.ra": []}   # 라: 건당 조건 제외
    assert out["conditions"] == []                                                     # 영역 조건이 혜택 전체에 남지 않음
    assert all(r["value_num"] == "5" and r["limit_keys"] == [] for r in rules.values())
    assert {e["support_key"] for e in out["evidence"] if e["supports"] == "RULE"} == {"g.ga", "g.na", "g.ra"}
    assert TABLE in quotes and extras["limit_tiers"]["own"]["column"] == "A 할인"
    # 정규화가 모든 대상을 모든 규칙에 넣어도, 규칙별 대상만 남긴다
    rule_list = [{"rule_key": k, "target_list": [{"target_nm": n} for n in "가나다라"]} for k in rules]
    narrowed = {r["rule_key"]: [t["target_nm"] for t in r["target_list"]]
                for r in restrict_rule_targets(rule_list, extras["rule_targets"])}
    assert narrowed == {"g.ga": ["가"], "g.na": ["나", "다"], "g.ra": ["라"]}


def _split_into(into):
    return {**split_ops()[1], "into": into}


@pytest.mark.parametrize("ops", [
    # 조건 적용 대상과 옮길 규칙의 대상이 다름(다른 영역 조건이 붙는 경우)
    split_ops()[:2] + [{"op": "MOVE_CONDITION", "cond_key": "ga_only", "rule_keys": ["g.ga", "g.na"], "for_targets": ["가"]}],
    # 대상이 빠짐(라 누락)
    [split_ops()[0], _split_into([{"rule_key": "g.ga", "target_nms": ["가"]}, {"rule_key": "g.na", "target_nms": ["나", "다"]}])],
    # 대상이 겹침
    [split_ops()[0], _split_into([{"rule_key": "g.ga", "target_nms": ["가", "나"]}, {"rule_key": "g.na", "target_nms": ["나", "다", "라"]}])],
    # 혜택 대상에 없는 이름
    [split_ops()[0], _split_into([{"rule_key": "g.ga", "target_nms": ["가", "나", "다"]}, {"rule_key": "g.x", "target_nms": ["마", "라"]}])],
    # 원 규칙 조건 버림 사유 없음
    [split_ops()[0], {k: v for k, v in split_ops()[1].items() if k != "reason"}],
    # 대상을 한정한 규칙과 한정하지 않은 규칙이 섞임(r100을 남김)
    [split_ops()[1]],
    [{"op": "DROP_RULE", "rule_key": "r100"}],                                         # 사유 없음
    [{"op": "SET_RULE_TARGETS", "rule_key": "r50", "target_nms": ["가", "가"]}],
])
def test_invalid_rule_target_patches_are_rejected(ops):
    with pytest.raises(ValueError):
        apply_patch(grouped_item(), patch(*ops))


def test_limit_tiers_are_checked_cell_by_cell_against_the_table():
    good = check_limit_tiers(tiers_op("B 할인"), B)
    assert good["own"] == {"column": "B 할인", "merged_cell": True,
                           "caps": {"t1": {"raw": "5,000원", "amount": 5000}, "t2": {"raw": "5,000원", "amount": 5000}}}
    assert good["shared"][0]["caps"]["t2"] == {"raw": "11,000원", "amount": 11000}
    assert "100만원 이상: B 할인 5,000원, 통합 할인한도 11,000원" in limit_tiers_text(good)
    bad_specs = [
        tiers_op("A 할인", columns=columns(b_merged=False)),                          # 병합 칸을 병합으로 표시하지 않음
        tiers_op("A 할인", columns=columns(total_t2="17,000원")),                     # 공유 한도 값이 표와 다름
        tiers_op("A 할인", tiers=[{**TIERS[0], "max_amt_excl": 2000000}, TIERS[1]]),   # 구간 금액이 표기와 다름
        tiers_op("C 할인"),                                                           # 없는 열
        tiers_op("A 할인", shared=[{"group_key": "DOC:통합", "column": "통합 할인한도", "member_benefit_nms": [B]}]),
        tiers_op("A 할인", table_quote=TABLE.replace("6,000원", "6,500원")),
    ]
    for spec in bad_specs:
        with pytest.raises(ValueError):
            check_limit_tiers(spec, A)


def test_shared_limit_omission_is_detected_regression():
    """회귀: 정기결제 쪽에 통합 할인한도가 빠진 채(5천원만) 등록되던 문제."""
    a, b = check_limit_tiers(tiers_op("A 할인"), A), check_limit_tiers(tiers_op("B 할인"), B)
    required = extracted_shared_members(grouped_item())
    assert required == [frozenset({A, B})]
    assert shared_limit_problems({A: a, B: b}, required) == {}
    assert set(shared_limit_problems({A: a, B: None}, required)) == {A, B}             # 상대 혜택에 공유 한도 없음
    assert set(shared_limit_problems({A: a, B: None})) == {A, B}                       # 추출 단서 없이도 보정 선언만으로 검출
    assert set(shared_limit_problems({A: None, B: None}, required)) == {A, B}          # 추출이 밝힌 공유 한도를 아무도 기록 안 함
    assert set(shared_limit_problems({A: a}, required)) == {A, B}                      # 상대 혜택이 등록 대상에 없음
    different = check_limit_tiers(tiers_op("B 할인"), B)
    different["shared"][0]["caps"]["t2"]["amount"] = 17000                            # 구성원끼리 한도가 다름
    assert set(shared_limit_problems({A: a, B: different}, required)) == {A, B}


def test_service_marks_shared_limit_problem_by_benefit_name():
    candidates = [{"card_extr_stg_id": "S1", "stg_raw_item": grouped_item(), "normalized": {"bnft_nm": A}, "limit_tiers": None},
                  {"card_extr_stg_id": "S2", "stg_raw_item": {"bnft_nm": B}, "normalized": {"bnft_nm": B}, "limit_tiers": None},
                  {"card_extr_stg_id": "S3", "stg_raw_item": {"bnft_nm": "기본"}, "normalized": {"bnft_nm": "기본"}}]
    marked = {c["card_extr_stg_id"]: c.get("shared_limit_problem")
              for c in ProductBenefitService._mark_shared_limit_problems(candidates)}
    assert marked["S1"] and marked["S2"] and marked["S3"] is None
# endregion
