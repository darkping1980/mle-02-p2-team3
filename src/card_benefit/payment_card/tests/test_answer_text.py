"""고객용 자연어 답변의 검증. LLM은 Mock이다."""
from card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import (
    AnswerPoint, CardAnswer, enforce_exclusions, topic_marker, validate_answer,
)


def context(conflicts=()):
    return {"evidence": [{"evidence_id": "E1", "quote": "월 1천원", "benefit_ids": ["B1"], "page_no": 1}],
            "benefits": [{"benefit_id": "B1", "name": "대중교통", "rules": [], "rule_text": None, "limits": [{"text": "월 1천원"}], "conditions": []}],
            "unresolved": [], "rule_selection_unresolved": list(conflicts), "payment_amount": None}


def raw(text, points=True, uncertain=()):
    items = [AnswerPoint(text="월 1천원 한도입니다.", evidence_ids=["E1"], benefit_id="B1")] if points else []
    return CardAnswer(answer_text=text, conclusion="한도는 월 1천원입니다.", points=items, uncertain=list(uncertain), cannot_answer_reason=None)


def test_natural_text_that_passes_validation_is_shown_as_llm():
    answer, _ = validate_answer(raw("네, 대중교통 혜택은 한 달에 1천원까지 받으실 수 있습니다."), context(), "대중교통 한도")
    assert answer["answer_source"] == "llm" and answer["answer_text"].startswith("네,")


def test_value_outside_results_falls_back_to_verified_sentences():
    answer, warnings = validate_answer(raw("한 달에 5천원까지 받으실 수 있습니다."), context(), "대중교통 한도")
    assert answer["answer_source"] == "validated_sentences" and "5천원" not in answer["answer_text"]
    assert "월 1천원" in answer["answer_text"] and warnings


def test_internal_code_or_id_is_not_shown():
    for text in ("이 혜택은 PENDING_REVIEW 상태로 월 1천원입니다.", "bnft_limit_txt에 월 1천원입니다.", "근거 20261101_000049에 월 1천원입니다."):
        answer, _ = validate_answer(raw(text), context(), "대중교통 한도")
        assert answer["answer_source"] == "validated_sentences", text


def test_uncertain_codes_become_natural_words():
    answer, _ = validate_answer(raw("한 달에 1천원입니다.", uncertain=["혜택은 PENDING_REVIEW 상태입니다."]), context(), "질문")
    assert answer["uncertain"] == ["혜택은 검토 대기 상태입니다."]


def test_no_grounded_point_means_no_natural_answer():
    answer, _ = validate_answer(raw("한 달에 1천원입니다.", points=False), context(), "질문")
    assert answer["status"] == "NOT_ANSWERABLE" and answer["answer_text"] == "" and answer["answer_source"] == "none"


def test_unresolved_tier_cannot_be_decided_in_natural_text():
    conflict = {"benefit_id": "B1", "name": "대중교통", "applicable_rule_keys": ["a", "b"],
                "tiers": [{"rule_key": "a", "value": 100, "unit": "KRW", "min_amt": 3000}, {"rule_key": "b", "value": 500, "unit": "KRW", "min_amt": 10000}]}
    item = context([conflict])
    item["payment_amount"] = 10000
    item["benefits"][0]["limits"] = [{"text": "100원 500원 월 1천원"}]
    answer, _ = validate_answer(raw("1만원을 결제하면 500원을 받습니다."), item, "1만원 결제")
    assert answer["answer_source"] == "validated_sentences"


def test_exclusion_overrides_llm_text():
    answer = {"status": "ANSWERED", "conclusion": "됩니다.", "answer_text": "KTX도 됩니다.", "answer_source": "llm", "points": [], "uncertain": [], "message": None}
    fixed, _ = enforce_exclusions(answer, [{"benefit_id": "T", "name": "대중교통", "terms": ["KTX"], "verified_by": "postgresql"}],
                                  [{"evidence_id": "E", "quote": "KTX 제외"}])
    assert fixed["answer_text"] == "KTX는 대중교통의 제외 대상이라 이 혜택을 받을 수 없습니다."


def test_topic_marker():
    assert (topic_marker("고속버스"), topic_marker("지하철"), topic_marker("KTX")) == ("는", "은", "는")
