"""카드 GraphRAG 테스트. LLM은 항상 Mock이고, Neo4j는 RUN_NEO4J_INTEGRATION=1 일 때만 읽기 조회를 실행한다."""
import json
import logging
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from src.card_benefit.payment_card.db_pipeline_origin_search import card_graphrag, neo4j_search
from src.card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import (
    AnswerPoint, CardAnswer, CardGraphRAG, Interpretation, rule_conflicts, validate_answer, value_tokens)

APP = str(Path(__file__).resolve().parents[1] / "db_pipeline_origin_search" / "streamlit_app.py")
BENEFIT_ID = "B3"
KEY = '["x","Benefit","B3"]'


def js(value):
    return json.dumps(value, ensure_ascii=False)


def evidence_row(evidence_id, subject="BNFT", quote="월 1천원 5% 캐시백"):
    return {"owner_labels": ["A8Benefit"], "pool_id": None,
            "link": {"ev_subject_cd": subject, "ev_item_key": "-"},
            "evidence": {"source_json": js({"evidence_id": evidence_id, "page_no": 1, "approval_status_cd": "PENDING",
                                            "quote_txt": quote})}}


def detail(evidence=None):
    rule = {"rule_key": "transit_rate", "value_num": 5, "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN",
            "rule_status_cd": "DRAFT"}
    atom = {"atom_key": "transit_exclusions", "negate_yn": True, "cond_raw_txt": "시외버스 제외", "cond_type_cd": "BNFT_EXCL"}
    return {
        "context": {"card": {"source_json": js({"product_nm": "테스트 카드"})},
                    "policy": {"valid_from_is_assumption": True, "source_json": "{}"},
                    "benefit": {"name": "ONE MORE 대중교통 캐시백",
                                "source_json": js({"card_bnft_id": BENEFIT_ID, "bnft_nm": "ONE MORE 대중교통 캐시백",
                                                   "rule_select_cd": None})}},
        "rules": [{"rule": {"rule_key": "transit_rate", "source_json": js(rule)}, "targets": ["버스", "지하철"]}],
        "conditions": [{"owner_labels": ["A8Rule"], "rule_key": "transit_rate", "expression": {"key": "e1"}, "branch_no": 1,
                        "atom": {"key_name": "transit_exclusions", "source_json": js(atom)}}],
        "limits": [{"pool": {"period": "MONTH", "value": 1000, "unit": "KRW", "aggregation_is_assumption": True},
                    "rule_keys": ["transit_rate"]}],
        "evidence": [evidence_row("E1")] if evidence is None else evidence}


class FakeSearch:
    driver = SimpleNamespace(close=lambda: None)

    def __init__(self, result=None, fail=None, catalog_fail=None):
        self.result = detail() if result is None else result
        self.fail, self.catalog_fail, self.catalog = fail, catalog_fail, None
        self.calls = []

    def list_catalog(self):
        self.calls.append("catalog")
        if self.catalog_fail:
            raise self.catalog_fail
        return self.catalog or [{"id": BENEFIT_ID, "key": KEY, "name": "ONE MORE 대중교통 캐시백", "card": "테스트 카드",
                                 "targets": ["버스"], "payment_min_amounts": []}]

    def get_detail(self, key, sections=neo4j_search.ALL_SECTIONS):
        self.calls.append((key, sections))
        if self.fail:
            raise self.fail
        return None if self.result == "missing" else self.result


class FakeLLM:
    """include_raw 구조화 출력과 usage_metadata를 흉내 낸다."""

    def __init__(self, parsed=None, error=None, parsing_error=None):
        self.parsed, self.error, self.parsing_error = parsed, error, parsing_error
        self.prompts, self.options = [], []

    def with_structured_output(self, schema, **options):
        self.options.append(options)

        def invoke(prompt):
            self.prompts.append(prompt)
            if self.error:
                raise self.error
            raw = SimpleNamespace(usage_metadata={"input_tokens": 1000, "output_tokens": 200,
                                                  "input_token_details": {"cache_read": 100},
                                                  "output_token_details": {"reasoning": 50}},
                                  response_metadata={"model_name": "gpt-6-luna-test"})
            return {"raw": raw, "parsed": self.parsed, "parsing_error": self.parsing_error}
        return SimpleNamespace(invoke=invoke)


def interpret_llm(intent="BENEFIT_DETAIL", ids=(BENEFIT_ID,), ambiguity=None):
    return FakeLLM(Interpretation(intent=intent, benefit_ids=list(ids), ambiguity=ambiguity))


def point(text, ids=("E1",), benefit_id=None):
    return AnswerPoint(text=text, evidence_ids=list(ids), benefit_id=benefit_id)


def card_answer(points=(), conclusion="결론입니다.", uncertain=(), reason=None):
    return CardAnswer(conclusion=conclusion, points=list(points), uncertain=list(uncertain), cannot_answer_reason=reason)


def answer_llm(text="월 1000원 한도입니다.", ids=("E1",), uncertain=(), reason=None):
    return FakeLLM(card_answer([point(text, ids)], uncertain=uncertain, reason=reason))


def tier_benefit(benefit_id, name, month_count, targets):
    """ONE PICK·STYLE과 같은 형태의 조회 결과를 만든 혜택 문맥."""
    def rule(key, value, min_amt):
        return {"rule_key": key, "value": value, "unit": "KRW", "calc_method": "FIXED_PER_TXN", "basis_amt": None,
                "calc_params": None, "status": "DRAFT", "targets": targets}, {
            "scope": key, "branches": [{"branch_no": 1, "atoms": [{"atom_key": f"MIN_{key}", "negate": False,
                                                                   "type": "SPEND_REQ", "min_amt": min_amt,
                                                                   "text": "결제 건당 이상 시", "status": "DRAFT"}]}]}
    low, low_condition = rule(f"{benefit_id}_100", 100, 3000)
    high, high_condition = rule(f"{benefit_id}_500", 500, 10000)
    return {"benefit_id": benefit_id, "name": name, "card": "카드", "type": "CASHBACK", "verification_status": "PENDING_REVIEW",
            "rule_select": None, "rules": [low, high], "conditions": [low_condition, high_condition],
            "limits": [{"period": "MONTH", "value": month_count, "unit": "COUNT", "rule_keys": [], "aggregation_is_assumption": True},
                       {"period": "DAY", "value": 1, "unit": "COUNT", "rule_keys": [], "aggregation_is_assumption": True},
                       {"period": "MONTH", "value": 5000, "unit": "KRW", "rule_keys": [], "aggregation_is_assumption": True}]}


def tier_context(amount=None):
    """Q3·Q5 형태의 문맥. 금액 표 근거는 혜택별로 따로 있다."""
    benefits = [tier_benefit("P1", "ONE PICK 캐시백", 30, ["CU"]), tier_benefit("S1", "STYLE 캐시백", 10, ["다이소"])]
    quote = "결제 건당\n3천원 이상 시 \n100원\n/\n결제 건당\n1만원 이상 시 \n500원"
    evidence = [{"evidence_id": "EP", "page_no": 1, "approval_status": "PENDING", "quote": quote, "benefit_ids": ["P1"]},
                {"evidence_id": "EPL", "page_no": 1, "approval_status": "PENDING", "quote": "일 1회\n/ 월 30회", "benefit_ids": ["P1"]},
                {"evidence_id": "ES", "page_no": 1, "approval_status": "PENDING", "quote": quote, "benefit_ids": ["S1"]},
                {"evidence_id": "ESL", "page_no": 1, "approval_status": "PENDING", "quote": "일 1회\n/ 월 10회", "benefit_ids": ["S1"]},
                {"evidence_id": "EC", "page_no": 1, "approval_status": "PENDING", "quote": "공통 안내", "benefit_ids": ["P1", "S1"]}]
    return {"benefits": benefits, "payment_amount": amount, "rule_selection_unresolved": rule_conflicts(benefits, amount),
            "unresolved": ["개발용 DRAFT 데이터이며 혜택은 PENDING_REVIEW, 원문 근거는 PENDING입니다.",
                           "ONE PICK 캐시백: 규칙 P1_100, P1_500의 중첩 선택 방식은 미확정입니다."], "evidence": evidence}


def run(search=None, first=None, second=None, question="대중교통 혜택은?"):
    first, second = first or interpret_llm(), second or answer_llm()
    return CardGraphRAG(search or FakeSearch(), first, second).run(question), first, second


class GraphTests(unittest.TestCase):
    def test_normal_flow_order_state_and_one_call_each(self):
        state, first, second = run()
        self.assertEqual(state["path"], ["interpret", "retrieve", "answer", "finish"])
        self.assertEqual(state["intent"], "BENEFIT_DETAIL")
        self.assertEqual(state["search_parameters"]["benefit_keys"], [KEY])
        self.assertEqual(state["answer"]["status"], "ANSWERED")
        self.assertEqual(state["answer"]["points"][0]["evidence_ids"], ["E1"])
        self.assertEqual(state["evidence"][0]["page_no"], 1)
        self.assertEqual((len(first.prompts), len(second.prompts)), (1, 1))
        self.assertEqual([call["node"] for call in state["llm_calls"]], ["interpret", "answer"])

    def test_graph_is_compiled_state_graph(self):
        graph = CardGraphRAG(FakeSearch(), None, None).graph.get_graph()
        self.assertTrue({"interpret", "retrieve", "answer", "finish"} <= set(graph.nodes))

    def test_structured_output_options(self):
        _, first, _ = run()
        self.assertEqual(first.options[0], {"method": "json_schema", "strict": True, "include_raw": True})

    def test_unknown_skips_retrieve_and_answer(self):
        search = FakeSearch()
        state, _, second = run(search, interpret_llm("UNKNOWN", ()))
        self.assertEqual(state["path"], ["interpret", "finish"])
        self.assertEqual(state["answer"]["status"], "NOT_ANSWERABLE")
        self.assertEqual(second.prompts, [])
        self.assertEqual(search.calls, ["catalog"])

    def test_invented_benefit_is_not_searched(self):
        search = FakeSearch()
        state, _, second = run(search, interpret_llm("BENEFIT_DETAIL", ("NOPE",)))
        self.assertEqual(state["path"], ["interpret", "finish"])
        self.assertEqual(search.calls, ["catalog"])
        self.assertTrue(any("NOPE" in warning for warning in state["warnings"]))
        self.assertEqual(second.prompts, [])

    def test_interpret_parse_failure_keeps_usage(self):
        state, _, second = run(first=FakeLLM(parsing_error=ValueError("bad")))
        self.assertEqual(state["error"]["code"], "LLM_FAILED")
        self.assertEqual(state["llm_calls"][0]["input_tokens"], 1000)
        self.assertEqual(second.prompts, [])

    def test_llm_api_error_no_retry_and_hides_message(self):
        first = FakeLLM(error=RuntimeError("sk-SECRET"))
        with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "ERROR") as logs:
            state, _, _ = run(first=first)
        self.assertEqual(len(first.prompts), 1)
        self.assertEqual(state["error"], {"stage": "interpret", "code": "LLM_FAILED", "type": "RuntimeError"})
        self.assertNotIn("SECRET", " ".join(logs.output) + state["answer"]["message"])

    def test_answer_api_error(self):
        second = FakeLLM(error=RuntimeError("x"))
        state, _, _ = run(second=second)
        self.assertEqual(state["error"]["stage"], "answer")
        self.assertEqual(state["answer"]["status"], "ERROR")
        self.assertEqual(state["path"][-1], "finish")
        self.assertIsNone(state["llm_calls"][-1]["cost_usd"])
        self.assertTrue(any("비용" in warning for warning in state["warnings"]))

    def test_neo4j_catalog_failure_spends_no_llm(self):
        first = interpret_llm()
        state, _, _ = run(FakeSearch(catalog_fail=OSError("uri")), first)
        self.assertEqual(state["error"]["code"], "NEO4J_FAILED")
        self.assertEqual(first.prompts, [])

    def test_retrieve_failure_skips_answer(self):
        state, _, second = run(FakeSearch(fail=OSError("down")))
        self.assertEqual(state["error"]["stage"], "retrieve")
        self.assertEqual(second.prompts, [])

    def test_no_result_skips_answer(self):
        state, _, second = run(FakeSearch(result="missing"))
        self.assertEqual(state["answer"]["message"], card_graphrag.MESSAGES["NO_RESULT"])
        self.assertEqual(second.prompts, [])

    def test_no_evidence_skips_answer(self):
        state, _, second = run(FakeSearch(result=detail(evidence=[])))
        self.assertEqual(state["answer"]["message"], card_graphrag.MESSAGES["NO_EVIDENCE"])
        self.assertEqual(second.prompts, [])

    def test_answer_without_valid_evidence_is_removed(self):
        state, _, _ = run(second=answer_llm(ids=("FAKE",)))
        self.assertEqual(state["answer"]["status"], "NOT_ANSWERABLE")
        self.assertEqual(state["answer"]["points"], [])
        self.assertTrue(state["warnings"])

    def test_invented_number_is_removed(self):
        state, _, _ = run(second=answer_llm(text="월 7777원 캐시백입니다."))
        self.assertEqual(state["answer"]["points"], [])
        self.assertTrue(any("7777" in warning for warning in state["warnings"]))

    def test_question_too_long_spends_nothing(self):
        first = interpret_llm()
        search = FakeSearch()
        state, _, _ = run(search, first, question="가" * 501)
        self.assertEqual(state["error"]["code"], "QUESTION_TOO_LONG")
        self.assertEqual((first.prompts, search.calls), ([], []))

    def test_missing_api_key_message(self):
        state = CardGraphRAG(FakeSearch(), None, None).run("질문")
        self.assertEqual(state["error"]["code"], "LLM_NOT_CONFIGURED")

    def test_context_sent_to_llm_keeps_rule_limit_and_not(self):
        state, _, second = run()
        benefit = state["context"]["benefits"][0]
        self.assertEqual(benefit["rules"][0]["value"], 5)
        self.assertEqual(benefit["limits"][0]["value"], 1000)
        self.assertTrue(benefit["conditions"][0]["branches"][0]["atoms"][0]["negate"])
        self.assertIn("evidence_id", second.prompts[0])

    def test_unresolved_found_without_llm(self):
        state, _, _ = run()
        text = " ".join(state["unresolved"])
        for word in ("DRAFT", "valid_from", "CARD_MEMBER", "NOT"):
            self.assertIn(word, text)

    def test_two_rules_mark_nested_selection_unresolved(self):
        data = detail()
        data["rules"] = data["rules"] + [{"rule": {"rule_key": "second"}, "targets": []}]
        data["rules"][0]["rule"]["rule_key"] = "first"
        self.assertTrue(any("first, second" in text for text in card_graphrag.find_unresolved([data])))

    def test_limit_intent_keeps_conditions_for_unresolved_items(self):
        search = FakeSearch()
        state, _, _ = run(search, interpret_llm("BENEFIT_LIMIT"))
        self.assertIn("conditions", search.calls[1][1])
        self.assertTrue(any("NOT" in text for text in state["unresolved"]))

    def test_rule_evidence_merges_into_benefit_evidence(self):
        rows = [evidence_row("E1", "BNFT"), {**evidence_row("E1", "RULE"), "rule_key": "transit_rate"}]
        evidence = card_graphrag.collect_evidence([detail(evidence=rows)], "BENEFIT_DETAIL")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["subjects"], ["BNFT", "RULE"])
        self.assertEqual(evidence[0]["rule_keys"], ["transit_rate"])

    def test_limit_intent_drops_policy_evidence_and_merges_duplicates(self):
        rows = [evidence_row("E1", "POLICY"), evidence_row("E2", "BNFT"), evidence_row("E2", "POOL")]
        evidence = card_graphrag.collect_evidence([detail(evidence=rows)], "BENEFIT_LIMIT")
        self.assertEqual([item["evidence_id"] for item in evidence], ["E2"])
        self.assertEqual(evidence[0]["subjects"], ["BNFT", "POOL"])

    def test_cost_estimate(self):
        self.assertAlmostEqual(card_graphrag.estimate_cost("gpt-6-luna", 1000, 200, 100), 0.000191)
        self.assertIsNone(card_graphrag.estimate_cost("other", 1, 1))
        self.assertIsNone(card_graphrag.estimate_cost("gpt-6-luna", None, 1))

    def test_validate_partial(self):
        raw = card_answer([point("맞음"), point("없음", ())])
        answer, _ = validate_answer(raw, {"evidence": [{"evidence_id": "E1"}]}, "질문")
        self.assertEqual(answer["status"], "PARTIAL")


class ValueParsingTests(unittest.TestCase):
    def test_units_and_periods(self):
        self.assertEqual(value_tokens("월 1천원"), [("MONEY", 1000.0, "MONTH")])
        self.assertEqual(value_tokens("1,000원"), [("MONEY", 1000.0, None)])
        self.assertEqual(value_tokens("10만 원"), [("MONEY", 100000.0, None)])
        self.assertEqual(value_tokens("1만 5천원"), [("MONEY", 15000.0, None)])
        self.assertEqual(value_tokens("5%"), [("RATE", 5.0, None)])
        self.assertEqual(value_tokens("일 1회 / 월 30회"), [("COUNT", 1.0, "DAY"), ("COUNT", 30.0, "MONTH")])
        self.assertEqual(value_tokens("매월 2번"), [("COUNT", 2.0, "MONTH")])
        self.assertEqual(value_tokens("1인 1매"), [("COUNT", 1.0, None)])
        self.assertEqual(value_tokens("연 2회"), [("COUNT", 2.0, "YEAR")])

    def test_non_values_are_ignored(self):
        self.assertEqual(value_tokens("1쪽 원문, 20261101_000034, 2번째, 3개"), [])

    def test_payment_amount_needs_payment_words(self):
        self.assertEqual(card_graphrag.payment_amount("1만원 이상 결제하면?"), 10000)
        self.assertIsNone(card_graphrag.payment_amount("한도 5천원인 혜택은?"))
        self.assertIsNone(card_graphrag.payment_amount("얼마나 결제해야 해?"))


class NumberValidationTests(unittest.TestCase):
    def kept(self, text, ids=("EPL",), benefit_id="P1", question="차이는?", amount=None):
        answer, warnings = validate_answer(card_answer([point(text, ids, benefit_id)]), tier_context(amount), question)
        return bool(answer["points"]), warnings

    def test_unit_changed_amount_is_removed(self):
        self.assertFalse(self.kept("결제 건당 3만원 이상입니다.", ("EP",))[0])

    def test_same_digit_other_unit_is_removed(self):
        self.assertFalse(self.kept("월 30원입니다.")[0])
        self.assertFalse(self.kept("100회 제공됩니다.", ("EP",))[0])

    def test_equivalent_notation_is_kept(self):
        self.assertTrue(self.kept("결제 건당 3,000원 이상 100원, 10,000원 이상 500원입니다.", ("EP",))[0])
        self.assertTrue(self.kept("결제 건당 3천원 이상 100원입니다.", ("EP",))[0])

    def test_wrong_period_is_removed(self):
        self.assertFalse(self.kept("일 30회 제공됩니다.")[0])
        self.assertTrue(self.kept("월 30회 제공됩니다.")[0])

    def test_value_of_other_benefit_is_removed(self):
        self.assertFalse(self.kept("월 10회 제공됩니다.", benefit_id="P1")[0])
        self.assertTrue(self.kept("월 10회 제공됩니다.", ("ESL",), "S1")[0])

    def test_exact_difference_is_kept(self):
        kept, _ = self.kept("ONE PICK 월 30회와 STYLE 월 10회의 차이는 20회입니다.", ("EPL", "ESL"), None)
        self.assertTrue(kept)

    def test_wrong_difference_is_removed(self):
        self.assertFalse(self.kept("ONE PICK 월 30회와 STYLE 월 10회의 차이는 25회입니다.", ("EPL", "ESL"), None)[0])

    def test_difference_needs_both_operands_and_word(self):
        self.assertFalse(self.kept("차이는 20회입니다.", ("EPL", "ESL"), None)[0])
        self.assertFalse(self.kept("월 30회와 월 10회, 총 20회입니다.", ("EPL", "ESL"), None)[0])

    def test_sum_is_not_allowed(self):
        self.assertFalse(self.kept("월 30회와 월 10회를 합치면 40회입니다.", ("EPL", "ESL"), None)[0])

    def test_question_value_is_allowed(self):
        self.assertTrue(self.kept("7천원 결제는 3천원 이상 구간입니다.", ("EP",), "P1", "7천원 결제하면?")[0])

    def test_unitless_number_uses_previous_check(self):
        self.assertFalse(self.kept("혜택은 77개입니다.")[0])
        self.assertTrue(self.kept("혜택은 3개입니다.", ("EP",))[0])


class RuleConflictTests(unittest.TestCase):
    q5 = "1만원 이상 결제하면 캐시백은 얼마인가?"

    def test_applicable_tiers_follow_amount(self):
        self.assertEqual([len(c["applicable_rule_keys"]) for c in tier_context(10000)["rule_selection_unresolved"]], [2, 2])
        self.assertEqual([len(c["applicable_rule_keys"]) for c in tier_context(5000)["rule_selection_unresolved"]], [1, 1])

    def test_a93_q5_answer_is_corrected(self):
        """A9-3 실제 응답: 500원을 답처럼 제시하고 ONE PICK 근거만 인용했다."""
        raw = card_answer([point("검색 결과상 1만원 이상 결제 건은 대상 가맹점에서 건당 500원 캐시백으로 기재되어 있습니다.", ("EP",)),
                           point("다만 이 혜택은 DRAFT이고 근거도 PENDING이므로 확정된 혜택으로 볼 수 없습니다.", ("EP",))],
                          conclusion="1만원 이상이면 건당 500원입니다.")
        answer, warnings = validate_answer(raw, tier_context(10000), self.q5)
        self.assertIn("확정할 수 없습니다", answer["conclusion"])
        self.assertIn("ONE PICK 캐시백", answer["conclusion"])
        self.assertIn("STYLE 캐시백", answer["conclusion"])
        self.assertEqual(answer["status"], "PARTIAL")
        self.assertEqual([(p["benefit_id"], p["origin"], p["evidence_ids"]) for p in answer["points"]],
                         [("P1", "system", ["EP"]), ("S1", "system", ["ES"])])
        self.assertTrue(all("100원" in p["text"] and "500원" in p["text"] for p in answer["points"]))
        self.assertTrue(all(p["verification"] == "RAW_MATCH" for p in answer["points"]))
        self.assertFalse(any("500원 캐시백으로" in p["text"] for p in answer["points"]))
        self.assertTrue(warnings)

    def test_good_q5_answer_is_kept(self):
        raw = card_answer([point("결제 건당 3천원 이상 100원, 1만원 이상 500원이 기재되어 있습니다.", ("EP",), "P1"),
                           point("결제 건당 3천원 이상 100원, 1만원 이상 500원이 기재되어 있습니다.", ("ES",), "S1")],
                          conclusion="1만원 결제의 지급액은 규칙 선택 방식이 미확정이라 확정할 수 없습니다.")
        answer, warnings = validate_answer(raw, tier_context(10000), self.q5)
        self.assertEqual(answer["status"], "ANSWERED")
        self.assertEqual(answer["conclusion"], raw.conclusion)
        self.assertEqual([p["origin"] for p in answer["points"]], ["llm", "llm"])
        self.assertEqual(warnings, [])

    def test_conclusion_with_single_amount_is_replaced_even_if_unresolved_word_exists(self):
        raw = card_answer(conclusion="500원이며 일부는 미확정입니다.")
        answer, _ = validate_answer(raw, tier_context(10000), self.q5)
        self.assertNotIn("500원이며", answer["conclusion"])

    def test_single_tier_amount_is_not_blocked(self):
        raw = card_answer([point("5천원 결제는 100원 구간입니다.", ("EP",), "P1")], conclusion="100원 구간이며 규칙 선택은 미확정입니다.")
        answer, _ = validate_answer(raw, tier_context(5000), "5천원 결제하면?")
        self.assertEqual(len(answer["points"]), 1)

    def test_invented_priority_is_removed(self):
        raw = card_answer([point("500원이 100원보다 우선 적용됩니다.", ("EP",), "P1")], conclusion="규칙 선택은 미확정입니다.")
        answer, warnings = validate_answer(raw, tier_context(), "차이는?")
        self.assertEqual(answer["points"], [])
        self.assertTrue(any("적용 방식" in warning for warning in warnings))

    def test_conclusion_without_unresolved_gets_note(self):
        raw = card_answer([point("월 30회입니다.", ("EPL",), "P1")], conclusion="두 혜택은 대상과 한도가 다릅니다.")
        answer, _ = validate_answer(raw, tier_context(), "ONE PICK과 STYLE 혜택의 차이는?")
        self.assertIn("두 혜택은 대상과 한도가 다릅니다.", answer["conclusion"])
        self.assertIn("규칙 선택 방식은 미확정", answer["conclusion"])

    def test_empty_conclusion_gets_plain_note(self):
        answer, _ = validate_answer(card_answer(conclusion=""), tier_context(), "차이는?")
        self.assertTrue(answer["conclusion"].startswith("ONE PICK 캐시백"))

    def test_no_conflict_keeps_conclusion(self):
        answer, _ = run()[0]["answer"], None
        self.assertEqual(answer["conclusion"], "결론입니다.")


class EvidenceScopeTests(unittest.TestCase):
    def test_other_benefit_evidence_is_removed(self):
        raw = card_answer([point("월 30회입니다.", ("EPL", "ESL"), "P1")], conclusion="규칙 선택은 미확정입니다.")
        answer, warnings = validate_answer(raw, tier_context(), "한도는?")
        self.assertEqual(answer["points"][0]["evidence_ids"], ["EPL"])
        self.assertTrue(any("다른 혜택의 근거" in warning for warning in warnings))

    def test_only_other_benefit_evidence_drops_sentence(self):
        raw = card_answer([point("월 30회입니다.", ("ESL",), "P1")], conclusion="규칙 선택은 미확정입니다.")
        self.assertEqual(validate_answer(raw, tier_context(), "한도는?")[0]["points"], [])

    def test_shared_evidence_is_kept_for_both_benefits(self):
        raw = card_answer([point("공통 안내입니다.", ("EC",), "S1")], conclusion="규칙 선택은 미확정입니다.")
        self.assertEqual(validate_answer(raw, tier_context(), "안내는?")[0]["points"][0]["evidence_ids"], ["EC"])

    def test_unknown_benefit_id_is_cleared(self):
        raw = card_answer([point("월 30회입니다.", ("EPL",), "NOPE")], conclusion="규칙 선택은 미확정입니다.")
        answer, warnings = validate_answer(raw, tier_context(), "한도는?")
        self.assertIsNone(answer["points"][0]["benefit_id"])
        self.assertTrue(any("NOPE" in warning for warning in warnings))

    def test_status_sentence_leaves_points(self):
        """A9-3 Q3 실제 문장: 상태 설명에 금액 근거를 인용했다."""
        text = "이 데이터는 DRAFT이고 혜택 검토 및 근거 확인이 PENDING이며, 100원·500원 규칙의 중첩 선택 방식도 미확정이므로 확정 혜택으로 단정할 수 없습니다."
        raw = card_answer([point("월 30회입니다.", ("EPL",), "P1"), point(text, ("EP", "ES"))], conclusion="규칙 선택은 미확정입니다.")
        answer, warnings = validate_answer(raw, tier_context(), "차이는?")
        self.assertEqual(len(answer["points"]), 1)
        self.assertEqual(answer["status"], "ANSWERED")
        self.assertTrue(any("상태 문장" in warning for warning in warnings))

    def test_status_sentence_not_covered_is_listed(self):
        raw = card_answer(uncertain=["가맹점 범위는 추가 확인이 필요합니다."], conclusion="규칙 선택은 미확정입니다.")
        self.assertEqual(validate_answer(raw, tier_context(), "질문")[0]["uncertain"], ["가맹점 범위는 추가 확인이 필요합니다."])

    def test_duplicate_unresolved_is_hidden(self):
        raw = card_answer(uncertain=["데이터는 DRAFT입니다.", "100원·500원이 함께 적용될 수 있는지는 미확정입니다."], conclusion="규칙 선택은 미확정입니다.")
        self.assertEqual(validate_answer(raw, tier_context(), "질문")[0]["uncertain"], [])

    def test_verification_levels(self):
        raw = card_answer([point("월 30회입니다.", ("EPL",), "P1"), point("월 5,000원입니다.", ("EPL",), "P1"), point("대상은 CU입니다.", ("EP",), "P1")],
                          conclusion="규칙 선택은 미확정입니다.")
        levels = [p["verification"] for p in validate_answer(raw, tier_context(), "한도는?")[0]["points"]]
        self.assertEqual(levels, ["RAW_MATCH", "STRUCTURED_ONLY", "NOT_CHECKED"])

    def test_calculated_level_needs_operands_in_cited_quotes(self):
        text = "월 30회와 월 10회의 차이는 20회입니다."
        raw = card_answer([point(text, ("EPL", "ESL")), point(text, ("EPL",))], conclusion="규칙 선택은 미확정입니다.")
        levels = [p["verification"] for p in validate_answer(raw, tier_context(), "차이는?")[0]["points"]]
        self.assertEqual(levels, ["CALCULATED", "STRUCTURED_ONLY"])

    def test_q2_grace_sentences_are_kept(self):
        """A9-3 Q2·Q1 실제 답변은 그대로 유지되어야 한다."""
        quote = "- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공"
        context = {"benefits": [], "evidence": [{"evidence_id": "G", "quote": quote}, {"evidence_id": "T", "quote": "월 1천원\n5%\n캐시백\n10만원"}]}
        raw = card_answer([point("일반적으로는 지난달 카드 실적 10만 원 이상이 조건으로 기재되어 있어, 실적이 없으면 대중교통 캐시백을 받기 어렵습니다.", ("T",)),
                           point("다만 최초 카드 사용 등록일부터 다음 달 말일까지는 지난달 실적이 10만 원 미만이어도 10만 원 이상 기준으로 서비스를 제공한다고 되어 있습니다.", ("G",)),
                           point("검색된 DRAFT 내용상 버스·지하철 이용액의 5%를 캐시백하며, 월 한도는 1,000원으로 기재되어 있습니다.", ("T",))])
        answer, warnings = validate_answer(raw, context, "전월 실적이 없어도?")
        self.assertEqual(len(answer["points"]), 3)
        self.assertEqual(warnings, [])
        self.assertEqual({p["verification"] for p in answer["points"]}, {"RAW_MATCH"})


class TargetSelectionTests(unittest.TestCase):
    catalog = [{"id": "P1", "key": "kp", "name": "ONE PICK", "card": "ONE PICK STYLE 카드", "targets": ["CU"], "payment_min_amounts": [3000, 10000]},
               {"id": "S1", "key": "ks", "name": "STYLE", "card": "ONE PICK STYLE 카드", "targets": ["다이소"], "payment_min_amounts": [3000, 10000]},
               {"id": "T1", "key": "kt", "name": "대중교통", "card": "ONE PICK STYLE 카드", "targets": ["버스"], "payment_min_amounts": []}]

    def search(self):
        search = FakeSearch()
        search.catalog = self.catalog
        return search

    def test_transit_is_removed_from_payment_tier_question(self):
        search = self.search()
        state, first, _ = run(search, interpret_llm("BENEFIT_DETAIL", ("P1", "S1", "T1")), question="1만원 이상 결제하면 캐시백은 얼마인가?")
        self.assertEqual(state["search_parameters"]["benefit_ids"], ["P1", "S1"])
        self.assertEqual(state["search_parameters"]["payment_amount"], 10000)
        self.assertEqual([call[0] for call in search.calls[1:]], ["kp", "ks"])
        self.assertTrue(any("대중교통" in warning for warning in state["warnings"]))
        self.assertIn("payment_min_amounts", first.prompts[0])

    def test_compare_keeps_multiple_benefits(self):
        state, _, _ = run(self.search(), interpret_llm("BENEFIT_COMPARE", ("P1", "T1")), question="1만원 결제 시 ONE PICK과 대중교통 비교")
        self.assertEqual(state["search_parameters"]["benefit_ids"], ["P1", "T1"])

    def test_only_transit_is_kept(self):
        state, _, _ = run(self.search(), interpret_llm("BENEFIT_DETAIL", ("T1",)), question="버스로 1만원 결제하면 얼마야?")
        self.assertEqual(state["search_parameters"]["benefit_ids"], ["T1"])

    def test_question_without_payment_amount_keeps_selection(self):
        state, _, _ = run(self.search(), interpret_llm("BENEFIT_DETAIL", ("P1", "S1", "T1")), question="이 카드 혜택 전체 알려줘")
        self.assertEqual(len(state["search_parameters"]["benefit_ids"]), 3)

    def test_ambiguous_question_explains_and_skips_answer(self):
        search = self.search()
        state, _, second = run(search, interpret_llm("BENEFIT_DETAIL", (), "어떤 가맹점 결제인지 불명확합니다."), question="캐시백 얼마야?")
        self.assertEqual(state["path"], ["interpret", "finish"])
        self.assertIn("질문 대상이 모호합니다: 어떤 가맹점 결제인지 불명확합니다.", state["answer"]["message"])
        self.assertEqual(second.prompts, [])
        self.assertEqual(search.calls, ["catalog"])

    def test_invented_id_is_blocked_with_real_ids(self):
        state, _, _ = run(self.search(), interpret_llm("BENEFIT_DETAIL", ("P1", "FAKE")))
        self.assertEqual(state["search_parameters"]["benefit_ids"], ["P1"])


class LoggingTests(unittest.TestCase):
    def test_steps_are_logged_without_quote_text(self):
        with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
            run()
        text = "\n".join(logs.output)
        for word in ("REQUEST [", "INTERPRET [", "RETRIEVE START [", "RETRIEVE DONE [", "ANSWER [", "FINAL [",
                     "input_tokens=", "estimated_cost_usd=", "total_ms=", "evidence_ids=['E1']"):
            self.assertIn(word, text)
        self.assertNotIn("월 1천원 5% 캐시백", text)
        self.assertNotIn("LLM PROMPT", text)

    def test_debug_shows_prompt(self):
        logger = logging.getLogger(neo4j_search.CARD_LOGGER_NAME)
        with self.assertLogs(logger, "DEBUG") as logs:
            run()
        self.assertIn("LLM PROMPT", "\n".join(logs.output))

    def test_common_handler_not_duplicated_on_rerun(self):
        parent = logging.getLogger("car_search_rag.neo4j")
        before = list(parent.handlers), parent.level, parent.propagate
        try:
            with patch.dict(os.environ, {"RECIPE_QUERY_LOG": "1"}):
                for _ in range(3):
                    card_graphrag.configure_card_logging()
            self.assertEqual(sum(getattr(h, "recipe_query_log", False) for h in parent.handlers), 1)
            self.assertEqual(logging.getLogger(neo4j_search.CARD_LOGGER_NAME).handlers, [])
        finally:
            parent.handlers[:], parent.level, parent.propagate = before[0], before[1], before[2]


class CreateLlmTests(unittest.TestCase):
    def test_model_from_env_and_cost_limits_in_real_request_payload(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test", "CARD_SEARCH_MODEL": "gpt-6-luna"}):
            first, second = card_graphrag.create_llms()
        self.assertEqual(first.max_retries, 0)
        payload = first._get_request_payload("질문")
        self.assertEqual(payload["model"], "gpt-6-luna")
        self.assertEqual(payload["reasoning_effort"], "low")
        self.assertEqual(payload["max_completion_tokens"], card_graphrag.INTERPRET_MAX_TOKENS)
        self.assertNotIn("temperature", payload)
        self.assertEqual(second.max_tokens, card_graphrag.ANSWER_MAX_TOKENS)

    def test_real_sdk_request_and_usage_parsing_without_network(self):
        """실제 ChatOpenAI를 통과시키고 HTTP 계층만 가로채 요청 본문과 응답 해석을 확인한다."""
        import httpx
        from langchain_openai import ChatOpenAI

        requests = []

        def reply(request):
            body = json.loads(request.content)
            requests.append((request.url.path, body))
            parsed = ({"intent": "BENEFIT_DETAIL", "benefit_ids": [BENEFIT_ID], "ambiguity": None} if len(requests) == 1 else
                      {"conclusion": "월 1000원입니다.", "points": [{"text": "월 1000원 한도입니다.", "evidence_ids": ["E1"],
                                                                 "benefit_id": BENEFIT_ID}],
                       "uncertain": [], "cannot_answer_reason": None})
            return httpx.Response(200, json={
                "id": "x", "object": "chat.completion", "created": 1, "model": "gpt-6-luna-snapshot",
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": json.dumps(parsed)}}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200,
                          "prompt_tokens_details": {"cached_tokens": 100},
                          "completion_tokens_details": {"reasoning_tokens": 50}}})

        client = httpx.Client(transport=httpx.MockTransport(reply))
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test", "CARD_SEARCH_MODEL": ""}),                 patch("langchain_openai.ChatOpenAI", lambda **options: ChatOpenAI(http_client=client, **options)):
            llms = card_graphrag.create_llms()
            state = CardGraphRAG(FakeSearch(), *llms).run("대중교통 혜택은?")
        self.assertEqual(state["answer"]["status"], "ANSWERED")
        self.assertEqual(len(requests), 2)
        path, body = requests[0]
        self.assertTrue(path.endswith("/chat/completions"))
        self.assertEqual(body["model"], "gpt-6-luna")
        self.assertEqual(body["reasoning_effort"], "low")
        self.assertEqual(body["max_completion_tokens"], card_graphrag.INTERPRET_MAX_TOKENS)
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertNotIn("tools", body)
        for schema in (body["response_format"], requests[1][1]["response_format"]):
            definition = schema["json_schema"]["schema"]
            self.assertEqual(set(definition["required"]), set(definition["properties"]))
        self.assertEqual(requests[1][1]["max_completion_tokens"], card_graphrag.ANSWER_MAX_TOKENS)
        call = state["llm_calls"][0]
        self.assertEqual((call["input_tokens"], call["output_tokens"], call["cached_tokens"], call["reasoning_tokens"]),
                         (1000, 200, 100, 50))
        self.assertEqual(call["response_model"], "gpt-6-luna-snapshot")
        self.assertAlmostEqual(call["cost_usd"], 0.000191)

    def test_no_key_no_llm(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch.object(card_graphrag, "load_project_environment"):
            self.assertEqual(card_graphrag.create_llms(), (None, None))


class StreamlitTests(unittest.TestCase):
    def setUp(self):
        st.cache_resource.clear()
        self.first, self.second = interpret_llm(), answer_llm()
        self.patches = [patch.object(neo4j_search, "connect", return_value=FakeSearch()),
                        patch.object(card_graphrag, "create_llms", return_value=(self.first, self.second)),
                        patch.object(card_graphrag, "configure_card_logging")]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        st.cache_resource.clear()

    def ask(self, app, question="대중교통 혜택은?"):
        app.text_area(key="question").set_value(question)
        return app.button[0].click().run(timeout=30)

    def test_load_makes_no_llm_or_db_call(self):
        app = AppTest.from_file(APP).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "카드 혜택 GraphRAG — 개발 테스트")
        self.assertEqual(self.first.prompts, [])
        neo4j_search.connect.assert_not_called()

    def test_answer_evidence_and_developer_info(self):
        app = self.ask(AppTest.from_file(APP).run(timeout=30))
        self.assertFalse(app.exception)
        page = " ".join(item.value for item in app.markdown)
        self.assertIn("1000원", page)
        self.assertIn("E1", page)
        self.assertTrue(any("월 1천원" in item.value for item in app.text))
        self.assertTrue(any("개발자 정보" in item.label for item in app.expander))
        self.assertTrue(any(item.value.startswith("추정 비용") for item in app.caption))

    def test_rerun_and_same_question_do_not_call_llm_again(self):
        app = self.ask(AppTest.from_file(APP).run(timeout=30))
        app.run(timeout=30)
        app = self.ask(app)
        self.assertEqual((len(self.first.prompts), len(self.second.prompts)), (1, 1))
        self.assertTrue(any("API를 호출하지 않고" in item.value for item in app.info))
        app.checkbox(key="force_rerun").check()
        self.ask(app)
        self.assertEqual(len(self.first.prompts), 2)

    def test_example_only_fills_input(self):
        app = AppTest.from_file(APP).run(timeout=30)
        app.button_group[0].set_value("놀이공원 할인율과 이용 횟수 제한은?").run(timeout=30)
        self.assertEqual(app.text_area(key="question").value, "놀이공원 할인율과 이용 횟수 제한은?")
        self.assertEqual(self.first.prompts, [])

    def test_connection_failure_is_sanitized(self):
        neo4j_search.connect.side_effect = RuntimeError("SECRET_VALUE")
        app = self.ask(AppTest.from_file(APP).run(timeout=30))
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertNotIn("SECRET_VALUE", app.error[0].value)

    def test_neo4j_failure_during_question_is_shown(self):
        neo4j_search.connect.return_value = FakeSearch(catalog_fail=OSError("SECRET_VALUE"))
        app = self.ask(AppTest.from_file(APP).run(timeout=30))
        self.assertEqual(app.error[0].value, card_graphrag.MESSAGES["NEO4J_FAILED"])

    def test_failed_question_can_run_again(self):
        neo4j_search.connect.return_value = FakeSearch(catalog_fail=OSError("x"))
        app = self.ask(AppTest.from_file(APP).run(timeout=30))
        neo4j_search.connect.return_value.catalog_fail = None
        self.ask(app)
        self.assertEqual(len(self.first.prompts), 1)


@unittest.skipUnless(os.getenv("RUN_NEO4J_INTEGRATION") == "1", "실제 Neo4j 읽기 테스트는 명시적으로 켠다")
class LiveAccuracyTests(unittest.TestCase):
    """실제 Neo4j 조회 + Mock LLM. A9-3 실제 응답을 Mock으로 재생해 검증기를 시험한다."""

    @classmethod
    def setUpClass(cls):
        cls.search = neo4j_search.connect()
        cls.ids = {row["name"]: row["id"] for row in cls.search.list_catalog()}

    @classmethod
    def tearDownClass(cls):
        cls.search.driver.close()

    def benefit(self, word):
        return next(value for name, value in self.ids.items() if word in name)

    def ask(self, question, intent, ids, parsed):
        return CardGraphRAG(self.search, interpret_llm(intent, ids), FakeLLM(parsed)).run(question)

    def test_catalog_has_payment_minimums_only_for_tier_benefits(self):
        rows = {row["name"]: sorted(row["payment_min_amounts"]) for row in self.search.list_catalog()}
        self.assertEqual({name: value for name, value in rows.items() if value},
                         {name: [3000, 10000] for name in rows if "ONE PICK" in name or "STYLE" in name})

    def test_q5_replay(self):
        one_pick, style, transit = self.benefit("ONE PICK"), self.benefit("STYLE"), self.benefit("대중교통")
        raw = card_answer([point("검색 결과상 1만원 이상 결제 건은 대상 가맹점에서 건당 500원 캐시백으로 기재되어 있습니다.", ("20261101_000034",)),
                           point("다만 이 혜택은 DRAFT이고 근거도 PENDING이므로 확정된 혜택으로 볼 수 없습니다.", ("20261101_000035",))],
                          conclusion="건당 500원입니다.",
                          uncertain=["편의점·카페 혜택과 쇼핑·서점·문구·패션 혜택 모두 1만원 이상 결제 시 500원으로 기재되어 있으나, 각각 해당 대상 가맹점 및 적용 조건을 충족해야 합니다.",
                                     "두 금액 구간 규칙의 중첩 적용 방식은 미확정입니다."])
        state = self.ask("1만원 이상 결제하면 캐시백은 얼마인가?", "BENEFIT_DETAIL", (one_pick, style, transit), raw)
        self.assertEqual(state["search_parameters"]["benefit_ids"], [one_pick, style])
        answer = state["answer"]
        self.assertIn("확정할 수 없습니다", answer["conclusion"])
        self.assertEqual(sorted(p["benefit_id"] for p in answer["points"]), sorted([one_pick, style]))
        self.assertEqual({p["verification"] for p in answer["points"]}, {"RAW_MATCH"})
        cited = {p["benefit_id"]: p["evidence_ids"][0] for p in answer["points"]}
        evidence = {item["evidence_id"]: item for item in state["evidence"]}
        for benefit_id, evidence_id in cited.items():
            self.assertIn(benefit_id, evidence[evidence_id]["benefit_ids"])
        self.assertEqual(answer["uncertain"], [])
        self.assertNotIn("대중교통 제외", " ".join(state["unresolved"]))

    def test_q3_replay_keeps_facts_and_separates_status(self):
        one_pick, style = self.benefit("ONE PICK"), self.benefit("STYLE")
        raw = card_answer([point("표시된 이용 한도는 ONE PICK이 일 1회·월 30회, STYLE이 일 1회·월 10회이며, 두 혜택 모두 월 5천원입니다.",
                                 ("20261101_000036", "20261101_000037", "20261101_000042", "20261101_000043")),
                           point("ONE PICK 월 30회와 STYLE 월 10회의 차이는 20회입니다.", ("20261101_000036", "20261101_000042")),
                           point("두 혜택 모두 결제 건당 3천원 이상이면 100원, 1만원 이상이면 500원으로 표시되어 있습니다.", ("20261101_000034", "20261101_000040")),
                           point("이 데이터는 DRAFT이고 혜택 검토 및 근거 확인이 PENDING이며, 100원·500원 규칙의 중첩 선택 방식도 미확정이므로 확정 혜택으로 단정할 수 없습니다.",
                                 ("20261101_000034", "20261101_000040"))],
                          conclusion="두 혜택은 대상과 월 횟수가 다릅니다.")
        state = self.ask("ONE PICK과 STYLE 혜택의 차이는?", "BENEFIT_COMPARE", (one_pick, style), raw)
        answer = state["answer"]
        self.assertEqual(len(answer["points"]), 3)
        self.assertEqual(answer["status"], "ANSWERED")
        self.assertIn("미확정", answer["conclusion"])
        self.assertEqual([p["verification"] for p in answer["points"]], ["RAW_MATCH", "CALCULATED", "RAW_MATCH"])

    def test_q3_swapped_limit_is_detected(self):
        one_pick, style = self.benefit("ONE PICK"), self.benefit("STYLE")
        raw = card_answer([point("월 10회입니다.", ("20261101_000036",), one_pick)], conclusion="규칙 선택은 미확정입니다.")
        state = self.ask("ONE PICK 한도는?", "BENEFIT_COMPARE", (one_pick, style), raw)
        self.assertEqual(state["answer"]["points"], [])

    def test_q2_replay_keeps_grace_condition(self):
        transit = self.benefit("대중교통")
        raw = card_answer([point("일반적으로는 지난달 카드 실적 10만 원 이상이 조건으로 기재되어 있어, 실적이 없으면 대중교통 캐시백을 받기 어렵습니다.", ("20261101_000044",), transit),
                           point("다만 최초 카드 사용 등록일부터 다음 달 말일까지는 지난달 실적이 10만 원 미만이어도 10만 원 이상 기준으로 서비스를 제공한다고 되어 있습니다.", ("20261101_000049",), transit)],
                          conclusion="원칙은 10만원 조건이지만 유예 기간이 있습니다.")
        state = self.ask("전월 실적이 없어도 대중교통 캐시백을 받을 수 있어?", "BENEFIT_CONDITION", (transit,), raw)
        self.assertEqual(state["answer"]["status"], "ANSWERED")
        self.assertEqual(len(state["answer"]["points"]), 2)
        self.assertEqual(state["warnings"], [])
        benefit = state["context"]["benefits"][0]
        group = next(item for item in benefit["conditions"] if item["scope"] == "혜택")
        self.assertEqual(len(group["branches"]), 2)

    def test_q4_replay_keeps_limits(self):
        park = self.benefit("놀이공원")
        raw = card_answer([point("에버랜드와 롯데월드에서 현장 50% 할인이 안내되어 있습니다.", ("20261101_000051", "20261101_000052"), park),
                           point("이용 횟수는 월 1회, 연 2회로 안내되어 있습니다.", ("20261101_000051", "20261101_000053"), park)],
                          conclusion="50% 할인, 월 1회·연 2회입니다.")
        state = self.ask("놀이공원 할인율과 이용 횟수 제한은?", "BENEFIT_LIMIT", (park,), raw)
        self.assertEqual(state["answer"]["status"], "ANSWERED")
        self.assertEqual({p["verification"] for p in state["answer"]["points"]}, {"RAW_MATCH"})


if __name__ == "__main__":
    unittest.main()
