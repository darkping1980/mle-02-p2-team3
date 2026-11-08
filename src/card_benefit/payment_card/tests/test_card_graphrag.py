"""카드 GraphRAG 테스트. LLM은 항상 Mock이고, Neo4j는 RUN_NEO4J_INTEGRATION=1 일 때만 읽기 조회를 실행한다."""
import json
import hashlib
import logging
import os
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import streamlit as st
from streamlit.testing.v1 import AppTest

from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag, execution_log, neo4j_search
from card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import (
    AnswerPoint, CardAnswer, CardGraphRAG, Interpretation, rule_conflicts, value_tokens)

APP = str(Path(__file__).resolve().parents[1] / "db_pipeline_origin_search" / "streamlit_app.py")
BENEFIT_ID = "B3"
KEY = '["x","Benefit","B3"]'


def js(value):
    return json.dumps(value, ensure_ascii=False)


def evidence_row(evidence_id, subject="BNFT", quote="월 1천원 5% 캐시백"):
    return {"owner_labels": ["dp_card_bnft"],
            "link": {"ev_subject_cd": subject, "ev_item_key": "-"},
            "evidence": {"source_json": js({"evidence_id": evidence_id, "page_no": 1, "approval_status_cd": "PENDING",
                                            "quote_txt": quote})}}


def detail(evidence=None):
    rule = {"rule_key": "transit_rate", "value_num": 5, "value_unit_cd": "PERCENT", "calc_method_cd": "PERCENT_OF_TXN",
            "rule_status_cd": "DRAFT"}
    atom = {"atom_key": "transit_exclusions", "negate_yn": True, "cond_raw_txt": "시외버스 제외", "cond_type_cd": "BNFT_EXCL"}
    return {
        "context": {"card": {"source_json": js({"product_nm": "테스트 카드"})},
                    "benefit": {"name": "ONE MORE 대중교통 캐시백",
                                "source_json": js({"card_bnft_id": BENEFIT_ID, "bnft_nm": "ONE MORE 대중교통 캐시백",
                                                   "bnft_rule_txt": "5% 캐시백"})}},
        "rules": [{"rule": {"rule_key": "transit_rate", "source_json": js(rule)}, "targets": ["버스", "지하철"]}],
        "conditions": [{"owner_cd": "RULE", "rule_key": "transit_rate", "expression": {"key": "e1"}, "branch_no": 1,
                        "atom": {"key_name": "transit_exclusions", "source_json": js(atom)}}],
        "limits": [{"limit_text": "월 1천원"}],
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

    def catalog_rows(self, question, graph_catalog, top_k=8):
        from card_benefit.payment_card.db_pipeline_origin_search.search_contract import SearchOutcome
        return list(graph_catalog), SearchOutcome("N", [], 0.0, engines=["neo4j_hybrid"])

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


def card_answer(points=(), conclusion="결론입니다.", uncertain=(), reason=None, answer_text=None):
    return CardAnswer(answer_text=answer_text if answer_text is not None else conclusion, conclusion=conclusion, points=list(points),
                      uncertain=list(uncertain), cannot_answer_reason=reason)


def answer_llm(text="월 1000원 한도입니다.", ids=("E1",), uncertain=(), reason=None):
    return FakeLLM(card_answer([point(text, ids)], uncertain=uncertain, reason=reason, answer_text=text))


def tier_benefit(benefit_id, name, month_count, targets):
    """ONE PICK·STYLE과 같은 형태의 조회 결과를 만든 혜택 문맥."""
    def rule(key, value, min_amt):
        return {"rule_key": key, "value": value, "unit": "KRW", "calc_method": "FIXED_PER_TXN", "basis_amt": None,
                "status": "DRAFT", "targets": targets}, {
            "scope": key, "branches": [{"branch_no": 1, "atoms": [{"atom_key": f"MIN_{key}", "negate": False,
                                                                   "type": "SPEND_REQ", "min_amt": min_amt, "basis": "TXN_AMT",
                                                                   "text": "결제 건당 이상 시", "status": "DRAFT"}]}]}
    low, low_condition = rule(f"{benefit_id}_100", 100, 3000)
    high, high_condition = rule(f"{benefit_id}_500", 500, 10000)
    return {"benefit_id": benefit_id, "name": name, "card": "카드", "type": "CASHBACK", "verification_status": "PENDING_REVIEW",
            "rule_select": None, "rules": [low, high], "conditions": [low_condition, high_condition],
            "limits": [{"text": f"월 5천원 / 일 1회 / 월 {month_count}회"}]}


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


def run(search=None, first=None, second=None, question="test transit benefit?"):
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

    def test_prototype_preserves_raw_answer_without_validation_or_fallback(self):
        original = card_answer([point("LLM original wording with 30000 and 5%", ("E1",), BENEFIT_ID)],
                               conclusion="original conclusion", uncertain=["original uncertainty"], reason="original reason",
                               answer_text="original answer text exactly")
        state, _, _ = run(second=FakeLLM(original))
        self.assertEqual(state["answer"]["answer_text"], original.answer_text)
        self.assertEqual(state["answer"]["conclusion"], original.conclusion)
        self.assertEqual(state["answer"]["points"][0]["evidence_ids"], ["E1"])
        self.assertEqual(state["answer"]["uncertain"], original.uncertain)
        self.assertEqual(state["answer_diagnostics"]["raw"], state["answer_diagnostics"]["final"])

    def test_normal_mode_remains_default_and_still_validates(self):
        state, _, _ = run()
        self.assertEqual(state["answer"]["answer_source"], "llm")
        self.assertEqual(state["answer"]["status"], "ANSWERED")
        self.assertNotIn("answer_mode", state)

    def test_prototype_uses_same_context_and_prompt_as_normal_mode(self):
        parsed = card_answer([point("A source-backed answer", ("E1",), BENEFIT_ID)])
        llm = FakeLLM(parsed)
        state, _, _ = run(second=llm)
        self.assertIn('"evidence"', llm.prompts[0])
        self.assertEqual(state["context"]["evidence"][0]["evidence_id"], "E1")

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

    def test_unmatched_evidence_id_is_passed_through(self):
        state, _, _ = run(second=answer_llm(ids=("FAKE",)))
        self.assertEqual(state["answer"]["status"], "ANSWERED")
        self.assertEqual(state["answer"]["points"][0]["evidence_ids"], ["FAKE"])

    def test_answer_number_is_passed_through(self):
        state, _, _ = run(second=answer_llm(text="7777 KRW cashback"))
        self.assertIn("7777", state["answer"]["answer_text"])
        self.assertEqual(state["answer_diagnostics"]["raw"], state["answer_diagnostics"]["final"])

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
        self.assertEqual(benefit["limits"], [{"text": "월 1천원"}])
        self.assertEqual(benefit["rule_text"], "5% 캐시백")
        self.assertTrue(benefit["conditions"][0]["branches"][0]["atoms"][0]["negate"])
        self.assertIn("evidence_id", second.prompts[0])

    def test_unresolved_found_without_llm(self):
        state, _, _ = run()
        text = " ".join(state["unresolved"])
        for word in ("개발용", "제외 조건"):
            self.assertIn(word, text)

    def test_two_rules_mark_nested_selection_unresolved(self):
        data = detail()
        data["rules"] = data["rules"] + [{"rule": {"rule_key": "second"}, "targets": []}]
        data["rules"][0]["rule"]["rule_key"] = "first"
        self.assertTrue(any("금액 구간" in text for text in card_graphrag.find_unresolved([data])))

    def test_rules_split_by_disjoint_targets_are_not_selection_unresolved(self):
        """대상 묶음별로 나뉜 규칙은 대상이 규칙을 정하므로 미확정이 아니다(2026-11-05 DAILY 고정소비 회귀)."""
        data = detail()
        data["rules"] = [{"rule": {"rule_key": "food.delivery"}, "targets": ["배달의민족", "쿠팡이츠"]},
                         {"rule": {"rule_key": "transit.taxi"}, "targets": ["택시 업종"]},
                         {"rule": {"rule_key": "transit.kakaot"}, "targets": ["카카오T(택시)"]}]
        self.assertFalse(any("금액 구간" in text for text in card_graphrag.find_unresolved([data])))
        benefit = {"benefit_id": "B", "name": "고정소비", "rule_text": "5%", "conditions": [],
                   "rules": [{"rule_key": r["rule"]["rule_key"], "value": 5, "unit": "PERCENT", "targets": r["targets"]}
                             for r in data["rules"]]}
        self.assertEqual(card_graphrag.rule_conflicts([benefit], 30000), [])
        for shared in (["배달의민족"], []):     # 대상이 겹치거나 대상 없는 규칙이 있으면 기존처럼 미확정
            data["rules"][1]["targets"] = shared
            self.assertTrue(any("금액 구간" in text for text in card_graphrag.find_unresolved([data])))
            benefit["rules"][1]["targets"] = shared
            self.assertEqual(len(card_graphrag.rule_conflicts([benefit], 30000)), 1)

    def test_limit_intent_keeps_conditions_for_unresolved_items(self):
        search = FakeSearch()
        state, _, _ = run(search, interpret_llm("BENEFIT_LIMIT"))
        self.assertEqual(search.calls[1][1], ("evidence",))
        self.assertTrue(state["retrieved_data"][0]["conditions"])
        self.assertTrue(any("제외 조건" in text for text in state["unresolved"]))

    def test_rule_evidence_merges_into_benefit_evidence(self):
        rows = [evidence_row("E1", "BNFT"), {**evidence_row("E1", "RULE"), "rule_key": "transit_rate"}]
        evidence = card_graphrag.collect_evidence([detail(evidence=rows)], "BENEFIT_DETAIL")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["subjects"], ["BNFT", "RULE"])
        self.assertEqual(evidence[0]["rule_keys"], ["transit_rate"])

    def test_limit_intent_drops_card_evidence_and_merges_duplicates(self):
        rows = [evidence_row("E1", "CARD"), evidence_row("E2", "BNFT"), evidence_row("E2", "BNFT"), evidence_row("E3", "RULE")]
        evidence = card_graphrag.collect_evidence([detail(evidence=rows)], "BENEFIT_LIMIT")
        self.assertEqual([item["evidence_id"] for item in evidence], ["E2"])
        self.assertEqual(evidence[0]["subjects"], ["BNFT"])

    def test_cost_estimate(self):
        self.assertAlmostEqual(card_graphrag.estimate_cost("gpt-6-luna", 1000, 200, 100), 0.000191)
        self.assertIsNone(card_graphrag.estimate_cost("other", 1, 1))
        self.assertIsNone(card_graphrag.estimate_cost("gpt-6-luna", None, 1))

COMMON_KEY = '["card_common_bnft",15,"C5"]'


class BenefitIdCollisionTests(unittest.TestCase):
    """카드 혜택과 공통 혜택의 ID 문자열이 같아도 종류·소유자로 따로 식별한다(2026-11-04 우리카드·MP004 11쌍)."""
    CARD_KEY = json.dumps(["card_bnft", 6, "20261104_000013"])
    COMMON_KEY = json.dumps(["card_common_bnft", 9, "20261104_000013"])

    def run_with(self, chosen):
        search = FakeSearch(detail([evidence_row("E1")]))
        search.catalog = [
            {"id": "20261104_000013", "key": self.CARD_KEY, "name": "온라인 쇼핑 10% 청구할인", "card": "카드의정석 SHOPPING",
             "targets": [], "payment_min_amounts": []},
            {"id": "20261104_000013", "key": self.COMMON_KEY, "name": "Qatar Airways 항공권 할인", "card": "적용 카드 미확인",
             "targets": [], "payment_min_amounts": []}]
        return CardGraphRAG(search, interpret_llm(ids=chosen), answer_llm("온라인 쇼핑 10% 할인입니다.", ("E1",))).run("온라인 쇼핑 할인?")

    def test_entity_ref_keeps_kind_and_owner(self):
        self.assertEqual(card_graphrag.entity_ref(self.CARD_KEY), "card_product_item:6:20261104_000013")
        self.assertEqual(card_graphrag.entity_ref(self.COMMON_KEY), "card_common_bnft:9:20261104_000013")
        self.assertEqual(card_graphrag.entity_ref("not-a-key", "X"), "X")

    def test_catalog_offers_distinct_ids_to_llm(self):
        state = self.run_with(("card_product_item:6:20261104_000013",))
        self.assertEqual([row["id"] for row in state["catalog"]],
                         ["card_product_item:6:20261104_000013", "card_common_bnft:9:20261104_000013"])

    def test_card_and_common_benefit_resolve_independently(self):
        card = self.run_with(("card_product_item:6:20261104_000013",))
        self.assertEqual(card["search_parameters"]["benefit_keys"], [self.CARD_KEY])
        self.assertEqual(card["search_parameters"]["benefit_names"], ["온라인 쇼핑 10% 청구할인"])
        common = self.run_with(("card_common_bnft:9:20261104_000013",))
        self.assertEqual(common["search_parameters"]["benefit_keys"], [self.COMMON_KEY])
        self.assertEqual(common["search_parameters"]["benefit_names"], ["Qatar Airways 항공권 할인"])

    def test_bare_id_is_dropped_not_guessed(self):
        state = self.run_with(("20261104_000013",))
        self.assertEqual(state["search_parameters"]["benefit_keys"], [])
        self.assertTrue(any("버렸습니다" in warning for warning in state["warnings"]))

    def test_evidence_scope_uses_reference(self):
        state = self.run_with(("card_product_item:6:20261104_000013",))
        self.assertEqual(state["evidence"][0]["benefit_ids"], ["card_product_item:6:20261104_000013"])


class CommonEvidenceFallbackTests(unittest.TestCase):
    def common_run(self, graph_evidence, key=COMMON_KEY):
        search = FakeSearch(detail(graph_evidence))
        search.catalog = [{"id": "C5", "key": key, "name": "Travel common benefit", "card": "Travel card",
                           "targets": [], "payment_min_amounts": []}]
        second = answer_llm("?? 15% ?????.", ("E1",))
        state = CardGraphRAG(search, interpret_llm(ids=(card_graphrag.entity_ref(key, "C5"),)), second).run("?? ???")
        return state, second

    def test_graph_evidence_is_used_from_neo4j(self):
        state, _ = self.common_run([evidence_row("E1", quote="?? 15% ??")])
        self.assertEqual(state["answer"]["status"], "ANSWERED")
        self.assertEqual([item["evidence_id"] for item in state["evidence"]], ["E1"])

    def test_no_graph_evidence_stays_not_answerable(self):
        state, second = self.common_run([])
        self.assertEqual(state["answer"]["status"], "NOT_ANSWERABLE")
        self.assertEqual(second.prompts, [])

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


class RuleConflictTests(unittest.TestCase):
    q5 = "1만원 이상 결제하면 캐시백은 얼마인가?"

    def test_applicable_tiers_follow_amount(self):
        self.assertEqual([len(c["applicable_rule_keys"]) for c in tier_context(10000)["rule_selection_unresolved"]], [2, 2])
        self.assertEqual([len(c["applicable_rule_keys"]) for c in tier_context(5000)["rule_selection_unresolved"]], [1, 1])

    def test_no_conflict_keeps_conclusion(self):
        answer, _ = run()[0]["answer"], None
        self.assertEqual(answer["conclusion"], "결론입니다.")


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

    def test_compare_answer_prompt_requires_each_selected_benefit(self):
        state, _, answer_llm_instance = run(
            self.search(), interpret_llm("BENEFIT_COMPARE", ("P1", "T1")),
            question="ONE PICK style card comparison")
        prompt = answer_llm_instance.prompts[0]
        self.assertIn("COMPARISON COMPLETENESS CHECK", prompt)
        checklist = prompt.split("COMPARISON COMPLETENESS CHECK:", 1)[1]
        for benefit in state["context"]["benefits"]:
            self.assertIn(f'"benefit_id": "{benefit["benefit_id"]}"', checklist)
        self.assertIn("transaction or previous-month-spend conditions", prompt)
        self.assertIn("monthly/shared cap", prompt)
        self.assertEqual(state["answer"]["status"], "ANSWERED")

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


def amusement_detail():
    """놀이공원 혜택과 같은 형태의 조회 결과. 1인 1매 조건과 근거 연결을 포함한다."""
    atom = {"atom_key": "amusement_per_person", "negate_yn": False, "cond_raw_txt": "1인 1매", "cond_type_cd": "ETC"}
    row = evidence_row("E52", quote="50% \n현장할인\n(1인 1매)")
    row["link"]["ev_item_key"] = "amusement_per_person"
    data = detail(evidence=[row, evidence_row("E53", quote="월 1회 \n/ 연 2회")])
    data["context"]["benefit"]["name"] = "놀이공원"
    data["context"]["benefit"]["source_json"] = js({"card_bnft_id": BENEFIT_ID, "bnft_nm": "놀이공원", "bnft_rule_txt": "50% 현장할인 (1인 1매)"})
    data["conditions"] = [{"owner_cd": "BNFT", "rule_key": None, "expression": {"key": "e1"}, "branch_no": 1,
                           "atom": {"key_name": "amusement_per_person", "source_json": js(atom)}}]
    data["limits"] = [{"limit_text": "월 1회 / 연 2회"}]
    return data


class UnresolvedScopeTests(unittest.TestCase):
    """미확정 사항이 질문에 영향을 줄 때만 고객 화면과 답변 LLM에 전달되는지 확인한다."""
    limit_question = "놀이공원 할인율과 이용 횟수 제한은?"

    def ask(self, data, question, intent="BENEFIT_LIMIT", raw=None):
        return run(FakeSearch(data), interpret_llm(intent), FakeLLM(raw or card_answer([point("50% 현장할인입니다.", ("E52",))])),
                   question=question)

    def test_per_person_is_shown_for_limit_question_with_pdf_text_and_evidence(self):
        state, _, second = self.ask(amusement_detail(), self.limit_question)
        item = state["open_conditions"][0]
        self.assertEqual((item["topic"], item["confirmed"], item["evidence_ids"]), ("1인 1매", "50% 현장할인 (1인 1매)", ["E52"]))
        self.assertIn("확인되지 않습니다", item["open"])
        self.assertIn('"open_conditions": [{"topic": "1인 1매"', second.prompts[0])
        self.assertEqual(state["other_unresolved"], [])

    def test_per_person_is_hidden_for_unrelated_condition_question_but_kept_for_developer(self):
        state, _, second = self.ask(amusement_detail(), "놀이공원 지난달 실적 조건은?", "BENEFIT_CONDITION")
        self.assertEqual(state["open_conditions"], [])
        self.assertIn("'1인 1매'의 적용 범위는 아직 확정되지 않았습니다.", state["unresolved"])
        self.assertEqual(state["other_unresolved"], ["'1인 1매'의 적용 범위는 아직 확정되지 않았습니다."])
        self.assertNotIn("적용 범위는 아직", second.prompts[0])

    def test_per_person_is_shown_when_condition_question_asks_about_it(self):
        state, _, _ = self.ask(amusement_detail(), "놀이공원 할인 동반 가족도 받을 수 있어?", "BENEFIT_CONDITION")
        self.assertEqual([item["topic"] for item in state["open_conditions"]], ["1인 1매"])

    def test_transit_exclusion_review_item_stays_with_developer(self):
        state, _, second = self.ask(detail(), "대중교통 혜택은?", "BENEFIT_DETAIL")
        self.assertEqual(state["open_conditions"], [])
        self.assertTrue(any("제외 조건" in text for text in state["other_unresolved"]))
        self.assertNotIn("세부 적용 범위", second.prompts[0])
        self.assertIn("시외버스 제외", second.prompts[0])

    def test_review_item_never_reaches_customer_even_for_unlisted_vehicle(self):
        state, _, _ = self.ask(detail(), "광역버스도 캐시백 돼?", "BENEFIT_CONDITION")
        self.assertEqual(state["open_conditions"], [])
        self.assertTrue(state["other_unresolved"])

    def test_data_status_is_separate_from_card_conditions(self):
        state, _, second = self.ask(amusement_detail(), self.limit_question)
        self.assertEqual(state["data_notices"], [card_graphrag.DATA_STATUS_NOTICE])
        self.assertNotIn(card_graphrag.DATA_STATUS_NOTICE, second.prompts[0])

    def tier_details(self):
        def benefit(name):
            data = detail()
            source = json.loads(data["context"]["benefit"]["source_json"])
            data["context"]["benefit"]["source_json"] = js({**source, "bnft_nm": name})
            data["rules"] = [{"rule": {"rule_key": "low"}, "targets": []}, {"rule": {"rule_key": "high"}, "targets": []}]
            data["conditions"], data["evidence"] = [], [{**evidence_row("E34", "RULE"), "rule_key": "low"}]
            return data
        return [benefit("ONE PICK"), benefit("STYLE")]

    def test_same_tier_issue_is_merged_for_payment_question(self):
        conditions, _, others = card_graphrag.split_unresolved(self.tier_details(), "1만원 결제하면?", "BENEFIT_CONDITION", 10000)
        self.assertEqual(len(conditions), 1)
        self.assertEqual(conditions[0]["benefits"], ["ONE PICK", "STYLE"])
        self.assertEqual(conditions[0]["evidence_ids"], ["E34"])
        self.assertEqual(others, [])

    def test_tier_payout_uncertainty_is_not_shown_for_monthly_limit_question(self):
        question = "더 심플 하나카드의 월 할인 한도는 실적 구간에 따라 어떻게 달라져?"
        conditions, _, others = card_graphrag.split_unresolved(self.tier_details(), question, "BENEFIT_LIMIT", None)
        self.assertEqual(conditions, [])
        self.assertTrue(any(card_graphrag.TIER_OPEN in text for text in others))

    def test_tier_issue_is_not_shown_for_count_limit_question(self):
        conditions, _, others = card_graphrag.split_unresolved(self.tier_details(), "ONE PICK 월 몇 번?", "BENEFIT_LIMIT", None)
        self.assertEqual(conditions, [])
        self.assertEqual(len(others), 2)


class GenericRuleTests(unittest.TestCase):
    """ONE PICK과 값·단위·기준이 다른 가상 카드로, 판정이 조회 데이터에서만 나오는지 확인한다."""

    def context(self, amount, tiers=((50000, 2000, "KRW"), (200000, 7000, "KRW")), basis="TXN_AMT", maxima=None, quote=None, status_name="주유 할인"):
        rules, conditions = [], []
        for index, (minimum, value, unit) in enumerate(tiers):
            key = f"rule_{index}"
            rules.append({"rule_key": key, "value": value, "unit": unit, "calc_method": None, "basis_amt": None,
                          "status": "DRAFT", "targets": ["주유소"]})
            conditions.append({"scope": key, "branches": [{"branch_no": 1, "atoms": [{
                "atom_key": f"min_{key}", "negate": False, "type": "SPEND_REQ", "min_amt": minimum, "basis": basis,
                "max_amt": (maxima or {}).get(index), "text": "기준 금액 이상", "status": "DRAFT"}]}]})
        benefit = {"benefit_id": "G1", "name": status_name, "card": "가상 카드", "type": "DISCOUNT", "verification_status": "PENDING_REVIEW",
                   "rule_select": None, "rules": rules, "conditions": conditions, "limits": []}
        if quote is None:
            quote = "3,000원 100원 / 10,000원 500원"
        evidence = [{"evidence_id": "Q", "page_no": 3, "approval_status": "PENDING", "quote": quote, "benefit_ids": ["G1"]}] if quote else []
        return {"benefits": [benefit], "payment_amount": amount, "rule_selection_unresolved": rule_conflicts([benefit], amount), "evidence": evidence}

    def conflicts(self, *args, **options):
        return self.context(*args, **options)["rule_selection_unresolved"]

    def test_code_has_no_card_specific_values(self):
        code = Path(card_graphrag.__file__).read_text(encoding="utf-8")
        for word in ("100원", "500원", "3천원", "1만원", "20만원", "ONE PICK", "ONE MORE", "STYLE", "놀이공원", "에버랜드", "1인 1매", "시외버스", "amusement"):
            self.assertNotIn(word, code)

    def test_applicable_tiers_follow_retrieved_amounts(self):
        for amount, expected in ((30000, 0), (50000, 1), (100000, 1), (200000, 2), (300000, 2)):
            self.assertEqual(len(self.conflicts(amount)[0]["applicable_rule_keys"]), expected, amount)

    def test_raw_only_condition_of_other_card_is_found_from_code_type(self):
        atom = {"atom_key": "any_key", "negate_yn": False, "cond_raw_txt": "동반 1인 무료", "cond_type_cd": "ETC"}
        data = amusement_detail()
        data["conditions"][0]["atom"] = {"key_name": "any_key", "source_json": js(atom)}
        conditions, _, _ = card_graphrag.split_unresolved([data], "무료 입장 한도는?", "BENEFIT_LIMIT", None)
        self.assertEqual([item["topic"] for item in conditions], ["동반 1인 무료"])
        self.assertIn("동반 1인 무료", conditions[0]["open"])
        self.assertEqual(card_graphrag.split_unresolved([data], "실적 조건은?", "BENEFIT_CONDITION", None)[0], [])

    def test_tier_question_is_detected_from_retrieved_value(self):
        data = self_tier = detail()
        source_json = json.loads(data["context"]["benefit"]["source_json"])
        data["context"]["benefit"]["source_json"] = js({**source_json, "bnft_rule_txt": "5만원 이상 시 2천원 / 20만원 이상 시 7천원"})
        data["rules"] = [{"rule": {"rule_key": "low"}, "targets": []}, {"rule": {"rule_key": "high"}, "targets": []}]
        data["conditions"] = []
        self.assertTrue(card_graphrag.split_unresolved([self_tier], "7천원 조건은?", "BENEFIT_CONDITION", None)[0])
        self.assertFalse(card_graphrag.split_unresolved([self_tier], "9천원 조건은?", "BENEFIT_CONDITION", None)[0])


class VerificationStepTests(unittest.TestCase):
    def pipeline(self, search=None, first=None, second=None):
        self.search, self.first, self.second = search or FakeSearch(), first or interpret_llm(), second or answer_llm()
        return CardGraphRAG(self.search, self.first, self.second)

    def test_interpret_stops_before_detail_queries_and_answer(self):
        rag = self.pipeline()
        state = rag.verify_interpret("대중교통 혜택은?")
        self.assertEqual(state["path"], ["interpret"])
        self.assertEqual(self.search.calls, ["catalog"])
        self.assertEqual(self.second.prompts, [])
        self.assertEqual(card_graphrag.next_step(state), "retrieve")
        self.assertEqual(state["catalog"][0]["id"], BENEFIT_ID)

    def test_retrieve_stops_before_answer(self):
        rag = self.pipeline()
        state = rag.verify_retrieve(rag.verify_interpret("대중교통 혜택은?"))
        self.assertEqual(state["path"], ["interpret", "retrieve"])
        self.assertEqual(len(self.search.calls), 2)
        self.assertEqual(self.second.prompts, [])
        self.assertEqual(card_graphrag.next_step(state), "answer")

    def test_full_steps_match_automatic_run(self):
        rag = self.pipeline()
        state = rag.verify_answer(rag.verify_retrieve(rag.verify_interpret("대중교통 혜택은?")))
        automatic = self.pipeline().run("대중교통 혜택은?")
        self.assertEqual(state["path"], automatic["path"])
        for key in ("intent", "search_parameters", "statements", "unresolved", "evidence", "answer", "error", "warnings"):
            self.assertEqual(state[key], automatic[key], key)
        self.assertEqual([c["node"] for c in state["llm_calls"]], [c["node"] for c in automatic["llm_calls"]])

    def test_repeated_steps_do_not_call_again(self):
        rag = self.pipeline()
        state = rag.verify_retrieve(rag.verify_interpret("대중교통 혜택은?"))
        self.assertIs(rag.verify_retrieve(state), state)
        done = rag.verify_answer(state)
        self.assertIs(rag.verify_answer(done), done)
        self.assertIs(rag.verify_retrieve(done), done)
        self.assertEqual((len(self.first.prompts), len(self.second.prompts), len(self.search.calls)), (1, 1, 2))

    def test_changed_parameters_block_answer(self):
        rag = self.pipeline()
        state = rag.verify_retrieve(rag.verify_interpret("대중교통 혜택은?"))
        stale = {**state, "search_parameters": {**state["search_parameters"], "benefit_ids": ["OTHER"]}}
        with self.assertRaises(ValueError):
            rag.verify_answer(stale)
        self.assertEqual(self.second.prompts, [])

    def test_unknown_question_finishes_at_first_step(self):
        rag = self.pipeline(first=interpret_llm("UNKNOWN", ()))
        state = rag.verify_interpret("날씨")
        self.assertEqual(state["path"], ["interpret", "finish"])
        self.assertEqual(card_graphrag.next_step(state), "done")
        self.assertIs(rag.verify_retrieve(state), state)

    def test_no_evidence_finishes_after_retrieve(self):
        rag = self.pipeline(search=FakeSearch(result=detail(evidence=[])))
        state = rag.verify_retrieve(rag.verify_interpret("대중교통 혜택은?"))
        self.assertEqual(state["path"][-1], "finish")
        self.assertEqual(self.second.prompts, [])

    def test_plan_lists_catalog_and_detail_statements(self):
        state = self.pipeline().verify_interpret("대중교통 혜택은?")
        plan = card_graphrag.verification_plan(state)
        self.assertEqual([p["statement_id"] for p in plan], ["card.detail_batch"])
        self.assertEqual(plan[0]["parameters"]["keys"], [KEY])
        self.assertEqual(card_graphrag.catalog_plan()["statement_id"], "card.catalog_batch")

    def test_step_logs_detail_and_automatic_run_does_not(self):
        with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
            state = self.pipeline().verify_interpret("대중교통 혜택은?")
        self.assertIn("mode=verify", logs.output[0])
        with self.assertLogs(neo4j_search.CARD_LOGGER_NAME, "INFO") as logs:
            run()
        self.assertNotIn("mode=", logs.output[0])
        self.assertEqual(state["error"], None)


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

    def effective_level(self, env):
        logger = logging.getLogger(neo4j_search.CARD_LOGGER_NAME)
        parent = logging.getLogger("car_search_rag.neo4j")
        before = list(parent.handlers), parent.level, parent.propagate, logger.level
        try:
            with patch.dict(os.environ, env), patch.object(card_graphrag, "load_project_environment"), \
                 patch.object(card_graphrag, "is_local_dev", return_value=True):
                for name in ("DB_QUERY_LOG", "CARD_SEARCH_LOG_LEVEL"):
                    if name not in env:
                        os.environ.pop(name, None)
                card_graphrag.configure_card_logging()
                return logger.level
        finally:
            parent.handlers[:], parent.level, parent.propagate = before[0], before[1], before[2]
            logger.setLevel(before[3])

    def test_debug_is_default_without_environment_variable(self):
        self.assertEqual(self.effective_level({"DB_QUERY_LOG": "1"}), logging.DEBUG)

    def test_info_overrides_default(self):
        self.assertEqual(self.effective_level({"DB_QUERY_LOG": "1", "CARD_SEARCH_LOG_LEVEL": "INFO"}), logging.NOTSET)

    def test_common_log_switch_still_turns_detail_off(self):
        self.assertEqual(self.effective_level({"DB_QUERY_LOG": "0"}), logging.NOTSET)

    def test_recipe_switch_does_not_change_card_logging(self):
        self.assertEqual(self.effective_level({"RECIPE_QUERY_LOG": "0"}), logging.DEBUG)
        self.assertEqual(self.effective_level({"RECIPE_QUERY_LOG": "1", "DB_QUERY_LOG": "0"}), logging.NOTSET)

    def test_local_default_is_on_and_cloud_default_is_off(self):
        self.assertEqual(self.effective_level({}), logging.DEBUG)
        with patch.object(card_graphrag, "is_local_dev", return_value=False):
            parent = logging.getLogger("car_search_rag.neo4j")
            self.addCleanup(logging.getLogger(neo4j_search.CARD_LOGGER_NAME).setLevel, logging.NOTSET)
            with patch.dict(os.environ, {}), patch.object(card_graphrag, "load_project_environment"):
                os.environ.pop("DB_QUERY_LOG", None)
                card_graphrag.configure_card_logging()
            self.assertEqual(logging.getLogger(neo4j_search.CARD_LOGGER_NAME).level, logging.NOTSET)
            self.assertFalse(any(getattr(h, "common_query_log", False) for h in parent.handlers))

    def test_off_during_session_stops_card_output(self):
        """실행 중 .env에 OFF를 넣고 화면이 재실행되는 경우: handler, 레벨, 전파를 처음 상태로 돌린다."""
        parent = logging.getLogger("car_search_rag.neo4j")
        logger = logging.getLogger(neo4j_search.CARD_LOGGER_NAME)
        before = list(parent.handlers), parent.level, parent.propagate, logger.level
        try:
            parent.handlers.clear()
            with patch.object(card_graphrag, "load_project_environment"):
                with patch.dict(os.environ, {"DB_QUERY_LOG": "1"}):
                    card_graphrag.configure_card_logging()
                self.assertTrue(logger.isEnabledFor(logging.DEBUG))
                with patch.dict(os.environ, {"DB_QUERY_LOG": "0"}):
                    card_graphrag.configure_card_logging()
                self.assertEqual((parent.handlers, parent.level, parent.propagate, logger.level), ([], logging.NOTSET, True, logging.NOTSET))
                self.assertFalse(logger.isEnabledFor(logging.INFO))
                with patch.dict(os.environ, {"DB_QUERY_LOG": "1"}):
                    card_graphrag.configure_card_logging()
                self.assertEqual(len(parent.handlers), 1)
        finally:
            parent.handlers[:], parent.level, parent.propagate = before[0], before[1], before[2]
            logger.setLevel(before[3])

    def test_common_handler_not_duplicated_on_rerun(self):
        parent = logging.getLogger("car_search_rag.neo4j")
        before = list(parent.handlers), parent.level, parent.propagate
        try:
            with patch.dict(os.environ, {"DB_QUERY_LOG": "1"}):
                for _ in range(3):
                    card_graphrag.configure_card_logging()
            self.assertEqual(sum(getattr(h, "common_query_log", False) for h in parent.handlers), 1)
            self.assertEqual(logging.getLogger(neo4j_search.CARD_LOGGER_NAME).handlers, [])
        finally:
            parent.handlers[:], parent.level, parent.propagate = before[0], before[1], before[2]


class ConditionGroupTests(unittest.TestCase):
    def rows(self, owner, rule_key=None):
        return [{"owner_cd": owner, "rule_key": rule_key, "expression": {"key": owner}, "branch_no": 1,
                 "atom": {"source_json": js({"atom_key": "a", "negate_yn": False})}}]

    def test_scope_comes_from_owner_code(self):
        rows = self.rows("BNFT") + self.rows("CARD") + self.rows("RULE", "rule_1")
        self.assertEqual([group["scope"] for group in card_graphrag.condition_groups(rows)], ["혜택", "카드 공통", "rule_1"])


class RebuiltGraphContractTests(unittest.TestCase):
    def test_answer_evidence_is_capped_per_benefit_without_cross_owner_leak(self):
        from card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import answer_evidence_rows

        rows = [{"evidence_id": f"a{i}", "page_no": 1, "quote": "혜택 적용 조건", "benefit_ids": ["A"]}
                for i in range(18)]
        rows += [{"evidence_id": f"b{i}", "page_no": 2, "quote": "월 할인한도", "benefit_ids": ["B"]}
                 for i in range(18)]
        answer_rows = answer_evidence_rows(rows, [{"benefit_id": "A", "name": "대중교통"},
                                                  {"benefit_id": "B", "name": "정기결제"}])
        self.assertEqual(len(answer_rows), 24)
        self.assertEqual(sum("A" in row["benefit_ids"] for row in answer_rows), 12)
        self.assertEqual(sum("B" in row["benefit_ids"] for row in answer_rows), 12)

    def test_prompt_context_keeps_contract_and_omits_repeated_text_projections(self):
        from card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import compact_answer_context

        benefit = {"benefit_id": "A", "name": "혜택", "rules": [{"rule_key": "r1", "value": 10}],
                   "conditions": [{"scope": "r1", "branches": [{"branch_no": 1,
                       "atoms": [{"type": "SPEND_REQ", "text": "전월 실적", "min_amt": 300000}]}]}],
                   "limit_tiers": [{"label": "30만원 이상", "cap": {"amount": 10000}}],
                   "limit_text": "30만원 이상 1만원", "limits": [{"text": "30만원 이상 1만원"}],
                   "condition_text": "전월 실적", "exclusion_text": "제외", "targets": ["대상"]}
        compact = compact_answer_context({"benefits": [benefit], "evidence": [{"evidence_id": "E1"}]})
        row = compact["benefits"][0]
        self.assertEqual(row["rules"], benefit["rules"])
        self.assertEqual(row["conditions"][0]["branches"][0]["atoms"][0]["min_amt"], 300000)
        self.assertEqual(row["limit_tiers"], benefit["limit_tiers"])
        self.assertNotIn("condition_text", row)
        self.assertNotIn("limits", row)
        self.assertNotIn("exclusion_text", row)
        self.assertNotIn("targets", row)

    def detail(self, spend=True):
        from card_benefit.payment_card.db_pipeline_origin_search import neo4j_search
        rules = [{"rule_key": "r30", "value_num": 10000, "value_unit_cd": "KRW",
                  "target_list": [{"target_nm": "같은 가맹점"}],
                  "cond_expr": {"branches": [{"branch_no": 1, "atoms": [{
                      "atom_key": "spend30", "cond_type_cd": "SPEND_REQ", "cond_basis_cd": "PREV_MONTH_SPEND",
                      "cond_min_amt": 300000, "cond_raw_txt": "전월 30만원 이상"}]}]}},
                 {"rule_key": "r60", "value_num": 20000, "value_unit_cd": "KRW",
                  "target_list": [{"target_nm": "같은 가맹점"}],
                  "cond_expr": {"branches": [{"branch_no": 1, "atoms": [{
                      "atom_key": "spend60", "cond_type_cd": "SPEND_REQ", "cond_basis_cd": "PREV_MONTH_SPEND",
                      "cond_min_amt": 600000, "cond_raw_txt": "전월 60만원 이상"}]}]}}] if spend else []
        benefit = {"card_product_item_id": "20261105_000100", "card_id": 23, "item_type_cd": "BENEFIT",
                   "item_nm": "특별·추가 적립", "item_rule_txt": "실적에 따라 적립", "item_limit_txt": "통합 월 한도",
                   "source_json": "{}", "rule_list": json.dumps(rules, ensure_ascii=False), "item_data": "{}",
                   "item_cond_expr": json.dumps({"branches": []}, ensure_ascii=False)}
        context = {"benefit": benefit, "card": {"source_json": '{"product_nm":"카드의정석 POINT II"}'},
                   "card_sources": [], "common": None, "extraction_sources": []}
        detail = {"context": context, "evidence": [], "limits": [], "entity_ref": "card_product_item:23:20261105_000100"}
        detail.update(neo4j_search._normalize_item_contract(neo4j_search.source(benefit)))
        return detail

    def test_new_rule_list_conditions_reach_answer_context_and_terms_scope(self):
        detail = self.detail()
        context = card_graphrag.benefit_context(detail, previous_spend=600000)
        spend_atoms = [atom for group in context["conditions"] for branch in group["branches"] for atom in branch["atoms"]
                       if atom["type"] == "SPEND_REQ"]
        self.assertEqual({atom["min_amt"] for atom in spend_atoms}, {300000, 600000})
        self.assertTrue(card_graphrag.unresolved_items([detail]))
        terms, _ = card_graphrag.attach_terms([detail], [{
            "card_id": 23, "card_product_item_id": "terms1", "item_nm": "이용 유의사항",
            "product_nm": "카드의정석 POINT II", "item_data": {"terms_kind_cd": "NOTICE",
                "scope": {"scope_cd": "PERFORMANCE"}, "source": {"txt": "전월 실적 안내"}, "footnotes": []},
            "item_rule_txt": "전월 실적 안내", "evidence": []}])
        self.assertEqual(len(terms), 1)
        self.assertEqual(terms[0]["benefit_ids"], ["card_product_item:23:20261105_000100"])

    def test_terms_evidence_page_metadata_is_carried_to_final_evidence_list(self):
        final_evidence = [{"evidence_id": "EV1", "page_no": 2, "quote": "실적 기준", "benefit_ids": ["B1"]}]
        terms_evidence = [{"evidence_id": "EV2", "page_no": 2, "quote": "원문 인용", "benefit_ids": ["B1"]}]

        card_graphrag.merge_terms_evidence(final_evidence, terms_evidence)

        self.assertEqual(final_evidence[-1]["page_no"], 2)
        self.assertEqual(final_evidence[-1]["quote"], "원문 인용")
        self.assertEqual(final_evidence[-1]["benefit_ids"], ["B1"])

    def test_catalog_payment_filter_uses_only_explicit_transaction_minimums(self):
        from card_benefit.payment_card.db_pipeline_origin_search import neo4j_search
        rows = neo4j_search.catalog_rows([{
            "key": '["card_product_item",2,"x"]', "name": "편의점", "id": "x", "status": None,
            "card_source": '{"card_id":2,"product_nm":"ONE PICK STYLE"}',
            "rule_list": json.dumps([{"rule_key": "r", "target_list": [], "cond_expr": {"branches": [
                {"atoms": [{"cond_type_cd": "SPEND_REQ", "cond_basis_cd": "TXN_AMT", "cond_min_amt": 3000},
                           {"cond_type_cd": "SPEND_REQ", "cond_basis_cd": "PREV_MONTH_SPEND", "cond_min_amt": 100000}]}]}}], ensure_ascii=False),
            "item_cond_expr": "{}"}], [], [])
        self.assertEqual(rows[0]["payment_min_amounts"], [3000])
        selected, filtered = card_graphrag.filter_by_payment([rows[0]["key"]], {rows[0]["key"]: rows[0]}, 3000, "BENEFIT_DETAIL")
        self.assertEqual((selected, filtered), ([rows[0]["key"]], []))


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
                       "answer_text": "", "uncertain": [], "cannot_answer_reason": None})
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


def streamlit_error_text() -> str:
    """앱 모듈은 import하면 화면이 실행되므로 상수만 소스에서 읽는다."""
    import ast
    tree = ast.parse(Path(APP).read_text(encoding="utf-8"))
    return next(node.value.value for node in tree.body if isinstance(node, ast.Assign)
                and getattr(node.targets[0], "id", None) == "ERROR_TEXT")


class FakeNeo4jBenefitSearch:
    """화면 기본 경로(N)의 Neo4jBenefitSearch 대역. 임베딩·Neo4j 없이 그래프 카탈로그 후보를 그대로 돌려준다."""
    engine, reads_postgresql_source = "neo4j", False

    def __init__(self):
        self.calls = []

    def catalog_rows(self, question, graph_catalog, top_k=8):
        from card_benefit.payment_card.db_pipeline_origin_search.search_contract import SearchOutcome
        self.calls.append(question)
        return list(graph_catalog), SearchOutcome("N", [], 0.0, engines=["neo4j_hybrid"])

    def get_detail(self, key, sections):
        return None


class StreamlitTests(unittest.TestCase):
    def test_partial_answer_is_visible_in_default_streamlit_view(self):
        self.second.parsed = card_answer([point("Supported sentence.", ("E1",)), point("Unsupported sentence.", ("MISSING",))],
                                         answer_text="Supported sentence. Unsupported sentence.")
        app = self.ask(AppTest.from_file(APP).run(timeout=30))
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["outcome"]["answer"]["status"], "ANSWERED")
        self.assertIn("Unsupported sentence.", app.session_state["outcome"]["answer"]["answer_text"])

    def setUp(self):
        self._developer_ui_original = os.environ.get("CARD_GRAPHRAG_ENABLE_DEVELOPER_UI")
        os.environ["CARD_GRAPHRAG_ENABLE_DEVELOPER_UI"] = "1"
        st.cache_resource.clear()
        self.first, self.second = interpret_llm(), answer_llm()
        self.neo_search = FakeNeo4jBenefitSearch()
        self.patches = [patch.object(neo4j_search, "connect", return_value=FakeSearch()),
                        patch.object(card_graphrag, "create_llms", return_value=(self.first, self.second)),
                        patch.object(card_graphrag, "create_neo4j_benefit_search", return_value=self.neo_search),
                        patch.object(card_graphrag, "configure_card_logging")]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        st.cache_resource.clear()
        if self._developer_ui_original is None:
            os.environ.pop("CARD_GRAPHRAG_ENABLE_DEVELOPER_UI", None)
        else:
            os.environ["CARD_GRAPHRAG_ENABLE_DEVELOPER_UI"] = self._developer_ui_original

    def ask(self, app, question="대중교통 혜택은?"):
        app.text_area(key="question").set_value(question)
        return app.button[0].click().run(timeout=30)

    def dev(self, app):
        """개발자 모드를 켠다. 내부 검증 정보는 이 모드에서만 보인다."""
        return app.toggle(key="dev_mode").set_value(True).run(timeout=30)

    def test_stub_streamlit_request_passes_graph_traces_to_shared_app_log_writer(self):
        with patch.dict(os.environ, {"APP_ENV": "development", "APP_DB_LLM_TRACE_ENABLED": "1", "APP_DB_LOG_ENABLED": "1"}), \
             patch.object(execution_log, "persist_app_logs") as persist:
            app = self.ask(AppTest.from_file(APP).run(timeout=30))
        self.assertFalse(app.exception)
        trace_events = persist.call_args.kwargs["llm_trace_events"]
        self.assertEqual([event["stage"] for event in trace_events], ["INTERPRET", "RETRIEVE", "ANSWER"])
        self.assertIn("candidate_search", trace_events[0]["input_snapshot"])
        self.assertTrue(trace_events[-1]["input_snapshot"]["evidence"])
        self.assertEqual(trace_events[-1]["output_snapshot"]["final_answer"]["answer_text"], app.session_state["outcome"]["answer"]["answer_text"])

    def test_load_makes_no_llm_or_db_call(self):
        app = AppTest.from_file(APP).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "카드 혜택 안내")
        self.assertFalse(app.warning)
        self.assertEqual(self.first.prompts, [])
        neo4j_search.connect.assert_not_called()

    def test_no_search_mode_selector_is_present(self):
        app = AppTest.from_file(APP).run(timeout=30)
        self.assertFalse(any(item.key == "search_mode" or item.label == "검색 방식" for item in app.radio))
        app = self.dev(app)
        self.assertEqual([item.key for item in app.radio], ["run_mode"])     # 개발자 모드에도 검색 방식 선택은 없다

    def test_developer_controls_are_hidden_without_explicit_environment_flag(self):
        os.environ.pop("CARD_GRAPHRAG_ENABLE_DEVELOPER_UI", None)
        try:
            app = AppTest.from_file(APP).run(timeout=30)
        finally:
            os.environ["CARD_GRAPHRAG_ENABLE_DEVELOPER_UI"] = "1"
        self.assertFalse(app.exception)
        self.assertFalse(any(item.label == "개발자 모드" for item in app.toggle))
        self.assertFalse(any(item.key == "run_mode" for item in app.radio))

    def test_question_uses_neo4j_only_search_by_default(self):
        app = self.ask(AppTest.from_file(APP).run(timeout=30))
        self.assertFalse(app.exception)
        self.assertEqual(self.neo_search.calls, ["대중교통 혜택은?"])
        self.assertEqual(app.session_state["outcome"]["candidate_search"]["engines"], ["neo4j_hybrid"])

    def test_default_view_hides_internal_status(self):
        self.second.parsed = card_answer([point("source-backed point", ("E1",))],
                                         answer_text="PENDING_REVIEW must remain in the LLM sentence.")
        app = self.ask(AppTest.from_file(APP).run(timeout=30))
        self.assertFalse(app.exception)
        self.assertTrue(any("PENDING_REVIEW must remain in the LLM sentence." in item.value for item in app.markdown))

    def test_answer_markdown_is_rendered_without_escaping_formatting(self):
        self.second.parsed = card_answer([point("**더 심플 하나카드** 혜택 안내입니다.", ("E1",))],
                                         conclusion="혜택 안내입니다.",
                                         answer_text="**더 심플 하나카드** 혜택 안내입니다.")
        app = self.ask(AppTest.from_file(APP).run(timeout=30))
        self.assertFalse(app.exception)
        rendered_sources = [item.value for item in app.markdown]
        self.assertTrue(any("**더 심플 하나카드**" in value for value in rendered_sources))
        self.assertFalse(any(r"\*\*더 심플 하나카드\*\*" in value for value in rendered_sources))
        self.assertTrue(any(item.value == "카드 혜택 안내" for item in app.subheader))

    def test_answer_evidence_and_developer_info(self):
        app = self.ask(self.dev(AppTest.from_file(APP).run(timeout=30)))
        self.assertFalse(app.exception)
        outcome = app.session_state["outcome"]
        self.assertEqual(outcome["answer"]["points"][0]["evidence_ids"], ["E1"])
        self.assertTrue(any("E1" in item.value for item in app.markdown))
        self.assertTrue(any("답변 생성 정보" in item.label for item in app.expander))

    def test_open_items_separate_card_conditions_from_data_status(self):
        neo4j_search.connect.return_value = FakeSearch(amusement_detail())
        self.second.parsed = card_answer([point("one visit", ("E53",))], answer_text="Member benefit details stay unchanged.")
        app = self.ask(self.dev(AppTest.from_file(APP).run(timeout=30)), "amusement benefit limit?")
        self.assertFalse(app.exception)
        captions = [item.value for item in app.caption]
        self.assertTrue(any("PDF 확인" in value and "E52 (1쪽)" in value for value in captions))
        self.assertIn("Member benefit details stay unchanged.", " ".join(item.value for item in app.markdown))

    def test_unrelated_unresolved_is_only_in_developer_info(self):
        app = self.ask(self.dev(AppTest.from_file(APP).run(timeout=30)))
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["outcome"]["answer"]["answer_text"], self.second.parsed.answer_text)

    def test_rerun_and_same_question_do_not_call_llm_again(self):
        app = self.ask(self.dev(AppTest.from_file(APP).run(timeout=30)))
        app.run(timeout=30)
        app = self.ask(app)
        self.assertEqual((len(self.first.prompts), len(self.second.prompts)), (1, 1))
        self.assertTrue(any("API를 호출하지 않고" in item.value for item in app.info))
        app.checkbox(key="force_rerun").check()
        self.ask(app)
        self.assertEqual(len(self.first.prompts), 2)

    def test_example_only_fills_input(self):
        app = AppTest.from_file(APP).run(timeout=30)
        app.button_group(key="example").set_value("ONE PICK 대중교통").run(timeout=30)
        self.assertEqual(app.text_area(key="question").value, "ONE PICK STYLE 카드의 대중교통 혜택은?")
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
        self.assertEqual(app.error[0].value, streamlit_error_text())
        self.assertNotIn("Neo4j", app.error[0].value)

    def verify_app(self):
        app = self.dev(AppTest.from_file(APP).run(timeout=30))
        app.radio(key="run_mode").set_value("개발 검증").run(timeout=30)
        app.text_area(key="verify_question").set_value("대중교통 혜택은?").run(timeout=30)
        return app

    def test_verify_mode_makes_no_call_until_button(self):
        app = self.verify_app()
        self.assertFalse(app.exception)
        self.assertEqual(self.first.prompts, [])
        neo4j_search.connect.assert_not_called()

    def test_verify_steps_show_cypher_records_and_answer(self):
        search = neo4j_search.connect.return_value
        app = self.verify_app()
        app.button(key="verify_interpret").click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(search.calls, ["catalog"])
        codes = " ".join(block.value for block in app.code)
        self.assertIn("dp_card_product_item", codes)
        self.assertNotIn("dp_card_bnft", codes)
        self.assertNotIn("$key", codes)
        self.assertEqual(self.second.prompts, [])

        app.button(key="verify_retrieve").click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(len(search.calls), 2)
        self.assertNotIn("verify_retrieve", [item.key for item in app.button])
        page = " ".join(item.value for item in app.markdown)
        self.assertIn("card.evidence", page)
        self.assertEqual(self.second.prompts, [])

        app.button(key="verify_answer").click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual((len(self.first.prompts), len(self.second.prompts), len(search.calls)), (1, 1, 2))
        self.assertNotIn("verify_answer", [item.key for item in app.button])
        self.assertTrue(any("1000원" in item.value for item in app.markdown))
        app.run(timeout=30)
        self.assertEqual((len(self.first.prompts), len(self.second.prompts)), (1, 1))

    def test_verify_question_change_clears_previous_result(self):
        app = self.verify_app()
        app.button(key="verify_interpret").click().run(timeout=30)
        app.text_area(key="verify_question").set_value("다른 질문").run(timeout=30)
        self.assertIsNone(app.session_state["verify"])
        self.assertTrue(any("이전 검증 결과" in item.value for item in app.info))
        self.assertEqual(len(self.first.prompts), 1)

    def test_verify_connection_failure_is_sanitized(self):
        neo4j_search.connect.side_effect = RuntimeError("SECRET_VALUE")
        app = self.verify_app()
        app.button(key="verify_interpret").click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertNotIn("SECRET_VALUE", app.error[0].value)

    def test_failed_question_can_run_again(self):
        neo4j_search.connect.return_value = FakeSearch(catalog_fail=OSError("x"))
        app = self.ask(AppTest.from_file(APP).run(timeout=30))
        neo4j_search.connect.return_value.catalog_fail = None
        self.ask(app)
        self.assertEqual(len(self.first.prompts), 1)


class NewContractRegressionTests(unittest.TestCase):
    def test_answer_prompt_requires_shared_frequency_conditions(self):
        self.assertIn("혜택별로 근거가 확인된 일·월 이용 횟수", card_graphrag.ANSWER_PROMPT)

    def test_item_and_common_use_distinct_name_and_rule_fields(self):
        item_detail = detail()
        name = "\ud1b5\uc2e0\uc694\uae08 \ud560\uc778"
        rule_text = "\uc804\uc6d4 \uc2e4\uc801\uc5d0 \ub530\ub978 \ud55c\ub3c4"
        item = {"card_product_item_id": "I1", "item_nm": name, "item_rule_txt": rule_text,
                "source_json": js({"card_product_item_id": "I1", "item_nm": name, "item_rule_txt": rule_text})}
        item_detail["context"]["benefit"] = item
        item_detail["rules"] = [
            {"rule": {"rule_key": "low", "value_num": 1}, "targets": ["\ud1b5\uc2e0\uc694\uae08"]},
            {"rule": {"rule_key": "high", "value_num": 2}, "targets": []},
        ]
        unresolved = card_graphrag.unresolved_items([item_detail])
        tier = next(row for row in unresolved if row.get("topic") == card_graphrag.TIER_NAME)
        self.assertEqual(tier["benefit"], name)
        self.assertEqual(tier["confirmed"], rule_text)
        conditions, _, _ = card_graphrag.split_unresolved([item_detail], "\ud55c\ub3c4\ub294?", "BENEFIT_COMPARE", None)
        self.assertNotIn(None, conditions[0]["benefits"])

        common_detail = detail()
        common_name = "\uacf5\ud1b5 \ud61c\ud0dd"
        common_rule = "\uacf5\ud1b5 \uaddc\uce59"
        common_detail["context"]["benefit"] = {"card_common_bnft_id": "C1", "bnft_nm": common_name,
            "bnft_rule_txt": common_rule, "source_json": js({"card_common_bnft_id": "C1", "bnft_nm": common_name,
                                                                  "bnft_rule_txt": common_rule})}
        self.assertEqual(card_graphrag.benefit_context(common_detail)["name"], common_name)

    def test_only_disjoint_previous_month_ranges_are_proven_non_overlapping(self):
        rules = [
            {"rule": {"rule_key": "30_80", "value_num": 1,
                       "cond_expr": {"branches": [{"atoms": [{"cond_type_cd": "SPEND_REQ", "cond_basis_cd": "PREV_MONTH_SPEND",
                           "cond_min_amt": 300000, "cond_max_amt_excl": 800000}]}]}}, "targets": ["\uc790\ub3d9\ub0a9\ubd80"]},
            {"rule": {"rule_key": "80_plus", "value_num": 2,
                       "cond_expr": {"branches": [{"atoms": [{"cond_type_cd": "SPEND_REQ", "cond_basis_cd": "PREV_MONTH_SPEND",
                           "cond_min_amt": 800000}]}]}}, "targets": ["\uc790\ub3d9\ub0a9\ubd80"]},
        ]
        self.assertFalse(card_graphrag.rule_selection_open(rules))
        transaction_rules = [{**row, "rule": {**row["rule"], "cond_expr": {"branches": [{"atoms": [
            {"cond_type_cd": "SPEND_REQ", "cond_basis_cd": "TXN_AMT", "cond_min_amt": 3000,
             "cond_max_amt_excl": 8000 if row["rule"]["rule_key"] == "30_80" else None}]}]}}} for row in rules]
        self.assertTrue(card_graphrag.rule_selection_open(transaction_rules))

    def test_answer_keeps_source_exclusion_conditions_without_token_override(self):
        self.assertFalse(hasattr(card_graphrag, "find_exclusions"))
        self.assertFalse(hasattr(card_graphrag, "enforce_exclusions"))
        self.assertNotIn("exclusions", card_graphrag.CardState.__annotations__)
        response = "\ucd94\uac00 \uc801\ub9bd 5% \uce90\uc2dc\ubc31\uc785\ub2c8\ub2e4."
        quote = "\ucd94\uac00 \uc801\ub9bd 5% \uce90\uc2dc\ubc31, \uc6d4 1\ucc9c\uc6d0"
        data = detail(evidence=[evidence_row("E1", quote=quote)])
        benefit = {"card_product_item_id": "I3", "card_id": 2, "item_type_cd": "BENEFIT",
                   "item_nm": "\ucd94\uac00 \uc801\ub9bd", "item_rule_txt": response,
                   "item_limit_txt": "\uc6d4 1\ucc9c\uc6d0", "item_data": {}, "rule_list": [],
                   "source_json": js({"card_product_item_id": "I3", "card_id": 2, "item_type_cd": "BENEFIT",
                                       "item_nm": "\ucd94\uac00 \uc801\ub9bd", "item_rule_txt": response,
                                       "item_limit_txt": "\uc6d4 1\ucc9c\uc6d0", "item_data": {}, "rule_list": []})}
        data["context"]["benefit"] = benefit
        data["entity_ref"] = "card_product_item:2:I3"
        atom = {"atom_key": "bonus_exclusion", "negate_yn": True,
                "cond_raw_txt": "\ucd94\uac00 \uc801\ub9bd \uc11c\ube44\uc2a4\ub294 \uc81c\uc678", "cond_type_cd": "BNFT_EXCL"}
        data["conditions"] = [{"owner_cd": "RULE", "rule_key": "bonus", "expression": {"key": "e1"},
                               "branch_no": 1, "atom": {"key_name": "bonus_exclusion", "source_json": js(atom)}}]
        llm = FakeLLM(card_answer([point(response, ("E1",), "card_product_item:2:I3")],
                                  conclusion=response, answer_text=response))

        state, _, _ = run(FakeSearch(result=data), second=llm, question="\ucd94\uac00 \uc801\ub9bd \ud61c\ud0dd\uc740?")

        self.assertIn("\ucd94\uac00 \uc801\ub9bd \uc11c\ube44\uc2a4\ub294 \uc81c\uc678", llm.prompts[0])
        self.assertNotIn("excluded_terms", llm.prompts[0])
        self.assertEqual(state["answer"]["answer_source"], "llm")
        self.assertEqual(state["answer"]["status"], "ANSWERED")
        self.assertEqual(state["answer"]["answer_text"], response)
        self.assertNotEqual(state["answer"].get("answer_source"), "program_exclusion")
        self.assertNotIn("exclusions", state)

    def test_interpret_supplements_named_card_topics_from_catalog_when_hybrid_top_k_misses_one(self):
        from card_benefit.payment_card.db_pipeline_origin_search.search_contract import SearchOutcome

        question = "\ud734\ub300\uc804\ud654 \uc694\uae08\uacfc \uc815\uae30 \uad6c\ub3c5\uc744 \uc790\ub3d9\ub0a9\ubd80\ud558\ub294 \uace0\uac1d\uc5d0\uac8c \ub354 \uc2ec\ud50c \ud558\ub098\uce74\ub4dc\uc640 \uce74\ub4dc\uc758\uc815\uc11d2 DAILY\uc758 \uc801\uc6a9 \uac00\ub2a5 \ud560\uc778\uacfc \ud1b5\ud569 \ud55c\ub3c4\ub97c \ube44\uad50\ud574 \uc918"
        graph_rows = [
            {"key": '["card_product_item",22,"simple"]', "id": "simple", "name": "\uc6d4\ub0a9 \uc694\uae08 \uccad\uad6c\ud560\uc778",
             "card": "\ub354 \uc2ec\ud50c \ud558\ub098\uce74\ub4dc", "card_id": 22, "targets": [], "payment_min_amounts": [],
             "item_rule_txt": "\ud1b5\uc2e0\uc694\uae08 \uc6d4\ub0a9 \uc790\ub3d9\ub0a9\ubd80", "item_limit_txt": "\uc6d4 \ud55c\ub3c4",
             "condition_text": ["\uc6d4\ub0a9 \uc694\uae08 \ub300\uc0c1 \uac00\ub9f9\uc810 \uc790\ub3d9\ub0a9\ubd80 \uc2dc"],
             "search_text": "\ud1b5\uc2e0\uc694\uae08 \uc11c\ube44\uc2a4 \ub300\uc0c1: Netflix, Youtube Premium, \uc6d4\ub0a9 \uc694\uae08 \uc790\ub3d9\ub0a9\ubd80"},
            {"key": '["card_product_item",42,"telecom"]', "id": "telecom", "name": "\uace0\uc815\uc18c\ube44 5% \uccad\uad6c\ud560\uc778",
             "card": "\uce74\ub4dc\uc758\uc815\uc11d2 DAILY", "card_id": 42, "targets": ["SKT", "KT", "LG U+"],
             "payment_min_amounts": [], "item_rule_txt": "\ud1b5\uc2e0\uc694\uae08 5%", "item_limit_txt": "\ud1b5\ud569 \uc6d4 \ud55c\ub3c4",
             "condition_text": ["\ud1b5\uc2e0\uc694\uae08 \uc790\ub3d9\ub0a9\ubd80"], "search_text": "\ud1b5\uc2e0\uc694\uae08 \uc790\ub3d9\ub0a9\ubd80"},
            {"key": '["card_product_item",42,"subscription"]', "id": "subscription", "name": "\uc815\uae30\uacb0\uc81c 50% \uccad\uad6c\ud560\uc778",
             "card": "\uce74\ub4dc\uc758\uc815\uc11d2 DAILY", "card_id": 42, "targets": [], "payment_min_amounts": [],
             "item_rule_txt": "\uc815\uae30\uacb0\uc81c 50%", "item_limit_txt": "\uc6d4 \ud55c\ub3c4",
             "condition_text": ["\uc815\uae30\uacb0\uc81c(\uad6c\ub3c5)"], "search_text": "\uc815\uae30\uacb0\uc81c \uad6c\ub3c5"},
        ]
        search = FakeSearch()
        search.catalog = graph_rows

        class CandidateSearch:
            def catalog_rows(self, question, graph_catalog, top_k=8):
                from types import SimpleNamespace
                selected = graph_catalog[1:]
                hits = [SimpleNamespace(source="CARD_BNFT", key=row["key"], benefit_id=row["id"],
                                        bnft_nm=row["name"], similarity=0.6,
                                        cards=[{"product_nm": row["card"]}], applied=True,
                                        graph_targets=row["targets"], target_terms=[], excluded_terms=[])
                        for row in selected]
                return selected, SearchOutcome("N", hits, 1.0, engines=["neo4j_hybrid"])

        rag = CardGraphRAG(search, interpret_llm("BENEFIT_COMPARE", ()), answer_llm(),
                           candidate_search=CandidateSearch())
        state = rag.interpret({"request_id": "topic-fallback-test", "question": question})
        simple_ref = "card_product_item:22:simple"
        self.assertIn(simple_ref, state["search_parameters"]["benefit_ids"])
        self.assertIn(simple_ref, state["candidate_search"]["topic_supplement_ids"])
        self.assertIn(simple_ref, state["candidate_search"]["supplemented_ids"])
        self.assertEqual(state["candidate_search"]["coverage_gaps"], [])
        self.assertFalse(any("no matching benefit" in warning for warning in state.get("warnings", [])))

    def test_candidate_topic_matching_uses_conditions_and_targets_without_ids(self):
        question = "\ud734\ub300\uc804\ud654 \uc694\uae08\uacfc \uc815\uae30 \uad6c\ub3c5\uc744 \uc790\ub3d9\ub0a9\ubd80\ud558\ub294 \uace0\uac1d\uc5d0\uac8c \ub450 \uce74\ub4dc \ud61c\ud0dd\uc744 \ube44\uad50\ud574 \uc918"
        self.assertEqual(set(card_graphrag._requested_benefit_topics(question)), {"telecom", "subscription"})
        telecom = {"name": "\uace0\uc815\uc18c\ube44 \uc601\uc5ed 5% \uccad\uad6c\ud560\uc778", "targets": ["SKT", "KT", "LG U+"],
                   "condition_text": ["\ud1b5\uc2e0\uc694\uae08 \uc790\ub3d9\ub0a9\ubd80 \uac74\uc5d0 \ud55c\ud558\uc5ec \ud560\uc778 \uc81c\uacf5"]}
        subscription = {"name": "\uc815\uae30\uacb0\uc81c 50% \uccad\uad6c\ud560\uc778", "condition_text": ["\uc815\uae30 \uad6c\ub3c5 \uacb0\uc81c"]}
        monthly_services = {"name": "\uc6d4\ub0a9 \uc694\uae08 \uccad\uad6c\ud560\uc778",
                            "rule_text": "\uc6d4\ub0a9 \uc694\uae08 \ub300\uc0c1 \uac00\ub9f9\uc810 \uc790\ub3d9\ub0a9\ubd80 \uc2dc",
                            "search_text": "\uc11c\ube44\uc2a4 \ub300\uc0c1: Netflix, Youtube Premium"}
        self.assertTrue(card_graphrag._candidate_matches_topic(telecom, "telecom"))
        self.assertTrue(card_graphrag._candidate_matches_topic(subscription, "subscription"))
        monthly_services["search_text"] += " \uc11c\ube44\uc2a4 \ub300\uc0c1 \uc6d4\ub0a9 \uc790\ub3d9\ub0a9\ubd80"
        self.assertTrue(card_graphrag._candidate_matches_topic(monthly_services, "subscription"))


@unittest.skipUnless(os.getenv("RUN_NEO4J_INTEGRATION") == "1", "실제 Neo4j 읽기 테스트는 명시적으로 켠다")
class LiveAccuracyTests(unittest.TestCase):
    """실제 Neo4j 조회 + Mock LLM. A9-3 실제 응답을 Mock으로 재생해 검증기를 시험한다."""

    @classmethod
    def setUpClass(cls):
        cls.search = neo4j_search.connect()
        from card_benefit.payment_card.db_pipeline_origin_search.neo4j_hybrid_search import Neo4jBenefitSearch
        cls.candidate_search = Neo4jBenefitSearch(cls.search, embedder=None)
        # 질문 해석 LLM은 ID 단독이 아니라 종류·소유자 포함 참조를 고른다.
        cls.ids = {row["name"]: card_graphrag.entity_ref(row["key"], row["id"]) for row in cls.search.list_catalog()}

    @classmethod
    def tearDownClass(cls):
        cls.search.driver.close()

    def benefit(self, word):
        return next(value for name, value in self.ids.items() if word in name)

    def ask(self, question, intent, ids, parsed):
        return CardGraphRAG(self.search, interpret_llm(intent, ids), FakeLLM(parsed), candidate_search=self.candidate_search).run(question)

    def read_items(self, ids):
        catalog = self.search.list_catalog()
        rows = {row["id"]: row for row in catalog if row.get("id") in ids}
        self.assertEqual(set(rows), set(ids))
        return rows, self.search.get_details([rows[item]["key"] for item in ids])

    def test_live_simple_tiers_are_linked_to_previous_month_spend(self):
        ids = ["20261105_000099"]
        rows, details = self.read_items(ids)
        detail_row = details[rows[ids[0]]["key"]]
        context = card_graphrag.benefit_context(detail_row)
        tiers = context["limit_tiers"]
        self.assertEqual([(tier["min_amt"], tier["max_amt"], tier["cap"]["amount"])
                          for tier in tiers], [(300000, 800000, 10000), (800000, None, 15000)])
        self.assertTrue(all(tier["basis"] == "PREV_MONTH_SPEND" for tier in tiers))
        self.assertFalse(any(item.get("topic") == card_graphrag.TIER_NAME
                             for item in card_graphrag.unresolved_items([detail_row])))
        evidence = {item["evidence_id"]: item for item in card_graphrag.collect_evidence([detail_row], "BENEFIT_COMPARE")}
        self.assertEqual(evidence["20261105_002681"]["page_no"], 1)
        self.assertEqual(evidence["20261105_002682"]["page_no"], 1)

    def test_live_daily_telecom_subscription_and_shared_tier_evidence(self):
        ids = ["20261105_000179", "20261105_000180"]
        rows, details_by_key = self.read_items(ids)
        details = [details_by_key[rows[item]["key"]] for item in ids]
        contexts = [card_graphrag.benefit_context(item) for item in details]
        telecom, recurring = contexts
        telecom_text = " ".join(atom["text"] or "" for group in telecom["conditions"]
                                for branch in group["branches"] for atom in branch["atoms"])
        recurring_text = " ".join(atom["text"] or "" for group in recurring["conditions"]
                                  for branch in group["branches"] for atom in branch["atoms"])
        self.assertIn("\ud1b5\uc2e0\uc694\uae08 \uc790\ub3d9\ub0a9\ubd80", telecom_text)
        self.assertIn("\uc815\uae30\uacb0\uc81c(\uad6c\ub3c5)", recurring_text)
        self.assertEqual([tier["shared"][0]["amount"] for tier in recurring["limit_tiers"]], [8000, 11000, 17000])
        self.assertEqual([tier["min_amt"] for tier in recurring["limit_tiers"]], [500000, 1000000, 2000000])
        evidence = card_graphrag.collect_evidence(details, "BENEFIT_COMPARE")
        answer_rows = card_graphrag.answer_evidence_rows(evidence, contexts)
        by_id = {row["evidence_id"]: row for row in answer_rows}
        self.assertIn("20261105_003034", by_id)
        self.assertEqual(by_id["20261105_003034"]["page_no"], 2)
        quote = by_id["20261105_003034"]["quote"]
        self.assertIn("8,000", quote)
        self.assertIn("17,000", quote)

    def test_verify_steps_with_real_neo4j(self):
        transit = self.benefit("대중교통")
        raw = card_answer([point("월 1,000원 한도입니다.", ("20261101_000046",), transit)], conclusion="대중교통 혜택입니다.")
        first, second = interpret_llm("BENEFIT_DETAIL", (transit,)), FakeLLM(raw)
        rag = CardGraphRAG(self.search, first, second, candidate_search=self.candidate_search)
        state = rag.verify_interpret("대중교통 혜택은?")
        plan = card_graphrag.verification_plan(state)
        self.assertEqual(len(plan), 1)
        state = rag.verify_retrieve(state)
        detail_row = state["retrieved_data"][0]
        self.assertEqual((len(detail_row["rules"]), len(detail_row["conditions"]), len(detail_row["limits"])), (1, 4, 1))
        condition_types = {neo4j_search.source(row["atom"]).get("cond_type_cd") for row in detail_row["conditions"]}
        self.assertTrue({"SPEND_REQ", "SPEND_EXCL", "BNFT_EXCL", "GRACE"} <= condition_types)
        self.assertEqual(second.prompts, [])
        state = rag.verify_answer(state)
        self.assertEqual(state["answer"]["status"], "ANSWERED")
        self.assertEqual((len(first.prompts), len(second.prompts)), (1, 1))

    def test_catalog_payment_minimums_come_only_from_transaction_spend_atoms(self):
        rows = {row["name"]: sorted(row["payment_min_amounts"]) for row in self.search.list_catalog()}
        self.assertEqual(next(value for name, value in rows.items() if "ONE PICK" in name), [3000])
        self.assertEqual(next(value for name, value in rows.items() if name.startswith("STYLE")), [10000])
        self.assertEqual(next(value for name, value in rows.items() if "1%" in name), [10000])
        self.assertTrue(all(amount > 0 for values in rows.values() for amount in values))

    def test_q5_replay(self):
        one_pick, style, transit = self.benefit("ONE PICK"), self.benefit("STYLE"), self.benefit("대중교통")
        raw = card_answer([point("ONE PICK 편의점·카페는 결제 건당 3천원 이상 시 100원 캐시백입니다.",
                                 ("20261107_003042",), one_pick),
                           point("STYLE 쇼핑은 결제 건당 1만원 이상 시 500원 캐시백입니다.",
                                 ("20261107_003043",), style)],
                          conclusion="ONE PICK 편의점·카페는 건당 3천원 이상 결제 시 100원, STYLE 쇼핑은 건당 1만원 이상 결제 시 500원입니다.")
        state = self.ask("1만원 이상 결제하면 캐시백은 얼마인가?", "BENEFIT_DETAIL", (one_pick, style, transit), raw)
        self.assertEqual(state["search_parameters"]["benefit_ids"], [one_pick, style])
        answer = state["answer"]
        self.assertEqual(answer["status"], "ANSWERED")
        self.assertEqual(sorted(p["benefit_id"] for p in answer["points"]), sorted([one_pick, style]))
        self.assertEqual({p["verification"] for p in answer["points"]}, {"RAW_MATCH"})
        cited = {p["benefit_id"]: p["evidence_ids"] for p in answer["points"]}
        evidence = {item["evidence_id"]: item for item in state["evidence"]}
        self.assertEqual(cited[one_pick], ["20261107_003042"])
        self.assertEqual(cited[style], ["20261107_003043"])
        for benefit_id, evidence_ids in cited.items():
            for evidence_id in evidence_ids:
                self.assertIn(benefit_id, evidence[evidence_id]["benefit_ids"])
        self.assertEqual(answer["uncertain"], [])
        self.assertNotIn("대중교통 제외", " ".join(state["unresolved"]))

    def test_q3_replay_keeps_facts_and_separates_status(self):
        one_pick, style = self.benefit("ONE PICK"), self.benefit("STYLE")
        raw = card_answer([point("ONE PICK은 일 1회·월 30회까지이며 월 한도는 5천원입니다.",
                                 ("20261101_000036", "20261101_000037"), one_pick),
                           point("STYLE은 일 1회·월 10회까지이며 월 한도는 5천원입니다.",
                                 ("20261101_000042", "20261101_000043"), style),
                           point("ONE PICK 편의점·카페는 결제 건당 3천원 이상 시 100원입니다.",
                                 ("20261107_003042",), one_pick),
                           point("STYLE 쇼핑은 결제 건당 1만원 이상 시 500원입니다.",
                                 ("20261107_003043",), style)],
                          conclusion="두 혜택의 대상과 결제 건당 캐시백 기준은 서로 다릅니다.")
        state = self.ask("ONE PICK과 STYLE 혜택의 차이는?", "BENEFIT_COMPARE", (one_pick, style), raw)
        answer = state["answer"]
        self.assertEqual(len(answer["points"]), 4)
        self.assertEqual(answer["status"], "ANSWERED")
        self.assertEqual([p["verification"] for p in answer["points"]], ["RAW_MATCH"] * 4)

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


# region 연회비(ANNUAL_FEE): 금액은 등록 값으로 프로그램이 쓰고, 다른 카드·없는 줄을 추론하지 않는다.
def fee_detail(card_nm, lines, ref_key, links=()):
    item = {"item_type_cd": "ANNUAL_FEE", "item_data": {"schema_ver": "ANNUAL_FEE_V1", "fee_lines": lines}}
    evidence = [{"link": {"ev_item_cd": cd, "ev_item_key": key}, "evidence": {"source_json": json.dumps({"evidence_id": ev})}}
                for cd, key, ev in links]
    return {"context": {"benefit": {"name": "연회비", "source_json": json.dumps(item)},
                        "card": {"source_json": json.dumps({"product_nm": card_nm})}},
            "evidence": evidence, "entity_ref": ref_key}


WOORI_LINES = [
    {"line_key": "P_MV", "holder_type_cd": "PRINCIPAL", "brand_txt": "해외겸용 (Mastercard, VISA)", "basic_fee_amt": 5000,
     "affiliate_fee_amt": 7000, "total_fee_amt": 12000, "line_status_cd": "REVIEW", "review_note": "브랜드 옵션 미등록"},
    {"line_key": "F_ALL", "holder_type_cd": "FAMILY", "total_fee_amt": 0, "line_status_cd": "DRAFT",
     "same_fact_item_ref": "card_product_item:6:B23"}]


class AnnualFeeTests(unittest.TestCase):
    def test_same_fact_benefit_is_dropped_when_fee_is_present(self):
        fee = fee_detail("카드의정석 SHOPPING", WOORI_LINES, "card_product_item:6:F1")
        benefit = {"context": {"benefit": {"name": "가족카드 연회비 면제", "source_json": json.dumps({"item_type_cd": None})}},
                   "entity_ref": "card_product_item:6:B23"}
        kept, dropped = card_graphrag.drop_duplicate_benefits([benefit, fee])
        self.assertEqual(kept, [fee])
        self.assertEqual(dropped, ["가족카드 연회비 면제"])

    def test_fee_choice_swaps_same_fact_benefit_and_blocks_other_cards(self):
        catalog = [{"id": "card_product_item:6:B23", "name": "가족카드 연회비 면제", "card": "카드의정석 SHOPPING", "item_type": "BENEFIT"},
                   {"id": "card_product_item:6:F1", "name": "연회비", "card": "카드의정석 SHOPPING", "issuer": "우리카드",
                    "item_type": "ANNUAL_FEE", "same_fact_refs": ["card_product_item:6:B23"]},
                   {"id": "card_product_item:5:F2", "name": "연회비", "card": "JADE Classic", "issuer": "하나카드", "item_type": "ANNUAL_FEE"}]
        by_id = {row["id"]: row for row in catalog}
        chosen, _ = card_graphrag.resolve_fee_choice("우리카드 가족카드 연회비는?", ["card_product_item:6:B23"], by_id, catalog)
        self.assertEqual(chosen, ["card_product_item:6:F1"])
        chosen, warnings = card_graphrag.resolve_fee_choice("토스뱅크 Wide 연회비는?", ["card_product_item:5:F2"], by_id, catalog)
        self.assertEqual(chosen, [])
        self.assertTrue(warnings)
        chosen, _ = card_graphrag.resolve_fee_choice("세 카드의 연회비 비교", ["card_product_item:6:F1", "card_product_item:5:F2"], by_id, catalog)
        self.assertEqual(len(chosen), 2)

    def test_fee_of_card_chosen_by_benefit_is_kept_when_issuer_is_named(self):
        catalog = [{"id": "B1", "name": "STYLE 캐시백", "card": "ONE PICK STYLE 하나 체크카드", "item_type": "BENEFIT"},
                   {"id": "F2", "name": "연회비", "card": "ONE PICK STYLE 하나 체크카드", "issuer": "하나카드", "item_type": "ANNUAL_FEE"},
                   {"id": "F5", "name": "연회비", "card": "JADE Classic", "issuer": "하나카드", "item_type": "ANNUAL_FEE"}]
        by_id = {row["id"]: row for row in catalog}
        chosen, _ = card_graphrag.resolve_fee_choice("하나카드와 우리카드 중 연회비까지 비교", ["B1", "F2", "F5"], by_id, catalog)
        self.assertEqual(chosen, ["B1", "F2"])          # 혜택으로 정해진 카드의 연회비만, 같은 발급사의 다른 카드는 아님
        chosen, _ = card_graphrag.resolve_fee_choice("우리카드 연회비 비교", ["B1", "F2"], by_id, catalog)
        self.assertEqual(chosen, ["B1"])                # 발급사 이름이 없으면 인정하지 않음
        chosen, warnings = card_graphrag.resolve_fee_choice("하나카드와 우리카드 중 어느 카드가 유리해? 연회비 포함", ["F2"], by_id, catalog)
        self.assertEqual(chosen, ["F2"])                # 발급사 이름 + 그 발급사 연회비를 하나만 고름 → 인정하고 해석을 알림
        self.assertTrue(any("해석" in w for w in warnings))

# endregion


class TracePersistenceTests(unittest.TestCase):
    def test_persist_masks_payload_before_hashing_exact_stored_prompt(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (1036,)
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        manager = MagicMock()
        manager.connect.return_value.__enter__.return_value = connection
        trace = {"stage": "ANSWER", "question_id": "SYNTH-1",
                 "prompt_text": "Contact alice@example.com. Authorization: Bearer superSecretToken123456.",
                 "prompt_sha256": "unmasked-hash", "input_snapshot": {"email": "alice@example.com", "embedding": [0.1]},
                 "raw_output": {"phone": "01012345678", "api_key": "sk-abcdefghijklmnopqrstuvwxyz"},
                 "output_snapshot": {"authorization": "Bearer anotherSecretToken123456"}}
        with patch.dict(os.environ, {"APP_ENV": "development", "APP_DB_LLM_TRACE_ENABLED": "1", "APP_DB_LOG_ENABLED": "1"}), \
             patch.object(execution_log, "_log_database_manager", return_value=manager):
            execution_log.persist_app_logs("session-stub", "request-stub", [("REQUEST", "synthetic question", datetime.now())],
                                           llm_trace_events=[trace])
        insert = next(call for call in cursor.execute.call_args_list if "INSERT INTO db_pipeline.app_log_llm_trace" in call.args[0])
        params = insert.args[1]
        stored_prompt = params[7]
        self.assertNotIn("alice@example.com", stored_prompt)
        self.assertNotIn("superSecretToken123456", stored_prompt)
        self.assertEqual(params[8], hashlib.sha256(stored_prompt.encode("utf-8")).hexdigest())
        snapshot = json.loads(params[10])
        raw = json.loads(params[11])
        output = json.loads(params[12])
        self.assertNotIn("embedding", snapshot)
        self.assertEqual(snapshot["email"], "[REDACTED_EMAIL]")
        self.assertEqual(raw["phone"], "[REDACTED_PHONE]")
        self.assertEqual(raw["api_key"], "[REDACTED_SECRET]")
        self.assertEqual(output["authorization"], "[REDACTED_SECRET]")
        self.assertTrue(params[9])
        self.assertTrue(params[4])
