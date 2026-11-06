import copy
import json
from unittest.mock import patch

from card_benefit.payment_card.db_pipeline_origin_search.execution_log import outcome_detail_text


def detail(key, labels, name):
    from card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import entity_ref
    return {"entity_ref": entity_ref(key), "context": {"benefit": {"key": key, "name": name}, "benefit_labels": labels}}


def point(ref):
    return {"text": "월 한도는 1천 원입니다.", "benefit_id": ref, "benefit_name": "동명 혜택", "evidence_ids": ["20261101_000045"], "verification": "RAW_MATCH", "origin": "llm"}


def test_detail_refs_identify_nodes_without_mutating_answer():
    key1, key2 = '["card_bnft",2,"20261101_000003"]', '["card_bnft",3,"20261101_000003"]'
    labels = ["dp_node", "dp_card_bnft", "dp_card_product_item"]
    one, two = detail(key1, labels, "동명 혜택"), detail(key2, labels, "동명 혜택")
    common = detail('["card_common_bnft",7,"C"]', ["dp_node", "dp_card_common_bnft"], "공통 혜택")
    fee = detail('["card_product_item",2,"F"]', ["dp_node", "dp_card_product_item"], "연회비")
    points = [point(one["entity_ref"]), point(one["entity_ref"]), point(two["entity_ref"]), point(None), point(common["entity_ref"]), point(fee["entity_ref"]), point("missing")]
    outcome = {"answer": {"points": points}, "retrieved_data": [one, two, common, fee]}
    before = copy.deepcopy(outcome)
    result = json.loads(outcome_detail_text(outcome))["points"]
    assert outcome == before
    assert result[0]["neo4j_ref"] == result[1]["neo4j_ref"] == {"labels": labels, "key": key1, "name": "동명 혜택"}
    assert result[2]["neo4j_ref"]["key"] == key2
    assert result[3]["neo4j_ref"] is None and result[6]["neo4j_ref"] is None
    assert result[4]["neo4j_ref"]["labels"] == ["dp_node", "dp_card_common_bnft"]
    assert result[5]["neo4j_ref"]["key"] == '["card_product_item",2,"F"]'
    for old, new in zip(points, result):
        assert all(new[k] == v for k, v in old.items())


def test_ambiguous_conflicting_or_missing_identity_is_not_inferred():
    one = detail('["card_bnft",2,"B"]', ["dp_node", "dp_card_bnft"], "same")
    ambiguous = detail('["card_product_item",2,"B"]', ["dp_node", "dp_card_product_item"], "same")
    mismatch = detail('["card_bnft",9,"X"]', ["dp_node"], "same")
    mismatch["entity_ref"] = "different"
    missing_labels = detail('["card_bnft",10,"X"]', None, "same")
    rows = [one, ambiguous, mismatch, missing_labels]
    points = [point(one["entity_ref"]), point("different"), point(missing_labels["entity_ref"])]
    result = json.loads(outcome_detail_text({"answer": {"points": points}, "retrieved_data": rows}))["points"]
    assert all(p["neo4j_ref"] is None for p in result)


def test_log_failure_falls_back_without_mutating_answer():
    original = point("card_product_item:2:B")
    outcome = {"answer": {"points": [original]}, "retrieved_data": [None]}
    logged = json.loads(outcome_detail_text(outcome))["points"][0]
    assert logged == {**original, "neo4j_ref": None}
    assert "neo4j_ref" not in original


def test_serialization_error_does_not_escape():
    outcome = {"answer": {"points": [point(None)]}}
    with patch("card_benefit.payment_card.db_pipeline_origin_search.execution_log.json.dumps", side_effect=RuntimeError):
        assert outcome_detail_text(outcome) is None
