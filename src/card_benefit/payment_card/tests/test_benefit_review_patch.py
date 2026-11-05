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
    out, quotes = apply_patch(original, patch(
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
