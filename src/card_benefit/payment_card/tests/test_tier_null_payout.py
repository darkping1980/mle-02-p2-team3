"""금액 구간의 지급값 NULL 처리(P0, 2026-11-06).

재현 대상: 더 심플 하나카드(card 22) '월납 요금 청구할인'(20261105_000099)의 규칙 r1·r2는 전월 실적 구간
(30만원 이상 80만원 미만 / 80만원 이상)은 있지만 value_num·value_unit_cd가 NULL이다. 이전에는 tier_token()의
float(None) 때문에 답변 검증 전체가 TypeError로 중단됐다.

규약: 지급값을 모르면 None(미확정)으로 두고 0으로 바꾸지 않는다. 구간 기준액 검증은 모든 구간으로, 지급액 비교는
지급값이 확인된 구간으로만 한다. LLM은 Mock이고, 실제 Neo4j 읽기는 RUN_NEO4J_INTEGRATION=1일 때만 한다.
"""
import os
import unittest

from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag
from card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import (
    AnswerPoint, CardAnswer, distorts_tier, picks_single_tier, rule_conflicts, tier_is_quoted, tier_label, tier_text,
    tier_token, validate_answer)

TARGETS = ["SKT", "KT", "LG U+", "넷플릭스"]


def spend_condition(rule_key, atom_key, min_amt, max_amt, text, basis="PREV_MONTH_SPEND"):
    return {"scope": rule_key, "branches": [{"branch_no": 1, "atoms": [
        {"atom_key": atom_key, "negate": False, "type": "SPEND_REQ", "min_amt": min_amt, "max_amt": max_amt,
         "basis": basis, "text": text, "status": "DRAFT"}]}]}


def simple_monthly_benefit():
    """benefit_context()가 실제 Neo4j 상세 행(22/20261105_000099)에서 만드는 것과 같은 형태."""
    rules = [{"rule_key": key, "value": None, "unit": None, "status": "DRAFT", "targets": TARGETS} for key in ("r1", "r2", "r3")]
    conditions = [spend_condition("r1", "c1", 300000, 800000, "30만원 이상\n80만원 미만"),
                  spend_condition("r2", "c2", 800000, None, "80만원 이상"),
                  {"scope": "r3", "branches": [{"branch_no": 1, "atoms": [
                      {"atom_key": "c3", "negate": False, "type": "ETC", "min_amt": None, "max_amt": None, "basis": "TXN_AMT",
                       "text": "월납 요금 승인 금액이 할인 한도보다 적을 경우", "status": "DRAFT"}]}]}]
    return {"benefit_id": "card_product_item:22:20261105_000099", "name": "월납 요금 청구할인", "card": "더 심플 하나카드",
            "type": "DISCOUNT", "verification_status": "PENDING_REVIEW", "rule_text": "월납 요금 청구할인 / 승인 금액만큼 할인 적용",
            "rules": rules, "conditions": conditions,
            "limits": [{"text": "10,000원 / 15,000원 / ※ 횟수 제한 없이 월 할인 한도 내에서 합산 할인"}]}


def paid_tier_benefit(values=(100, 500), unit="KRW", basis="TXN_AMT"):
    """지급값이 있는 결제 건 구간(ONE PICK 형태). values의 원소가 None이면 그 구간만 미확정이다."""
    rules, conditions = [], []
    for key, value, min_amt in (("low", values[0], 3000), ("high", values[1], 10000)):
        rules.append({"rule_key": key, "value": value, "unit": unit if value is not None else None, "status": "DRAFT",
                      "targets": ["CU"]})
        conditions.append(spend_condition(key, f"MIN_{key}", min_amt, None, "결제 건당 이상 시", basis))
    return {"benefit_id": "P1", "name": "ONE PICK 캐시백", "card": "카드", "type": "CASHBACK", "verification_status": "PENDING_REVIEW",
            "rule_text": None, "rules": rules, "conditions": conditions, "limits": [{"text": "월 5천원"}]}


def point(text, ids, benefit_id):
    return AnswerPoint(text=text, evidence_ids=list(ids), benefit_id=benefit_id)


def answer(points, conclusion="결론입니다."):
    return CardAnswer(answer_text=conclusion, conclusion=conclusion, points=list(points), uncertain=[], cannot_answer_reason=None)


class TierTokenContractTests(unittest.TestCase):
    def test_null_value_and_null_unit_are_unknown_not_zero(self):
        self.assertIsNone(tier_token({"value": None, "unit": None}))
        self.assertIsNone(tier_token({"value": None, "unit": "KRW"}))       # 단위만 있고 값 없음
        self.assertIsNone(tier_token({"value": 500, "unit": None}))        # 값만 있고 단위 없음
        self.assertIsNone(tier_token({"value": True, "unit": "KRW"}))       # bool은 숫자로 보지 않는다
        self.assertIsNone(tier_token({"value": "500", "unit": "KRW"}))      # 문자열은 계약 밖이다

    def test_zero_is_a_known_value(self):
        self.assertEqual(tier_token({"value": 0, "unit": "KRW"}), ("MONEY", 0.0))
        self.assertEqual(tier_token({"value": 0.0, "unit": "PERCENT"}), ("RATE", 0.0))

    def test_normal_values(self):
        self.assertEqual(tier_token({"value": 500, "unit": "KRW"}), ("MONEY", 500.0))
        self.assertEqual(tier_token({"value": 3, "unit": "PERCENT"}), ("RATE", 3.0))

    def test_label_never_invents_an_amount(self):
        unknown = {"value": None, "unit": None, "min_amt": 300000, "basis": "PREV_MONTH_SPEND"}
        self.assertEqual(tier_label(unknown), "30만원 이상 시 지급액 정보 없음")
        self.assertEqual(tier_label({"value": 0, "unit": "KRW", "min_amt": 3000, "basis": "TXN_AMT"}), "결제 건당 3천원 이상 시 0원")


class NullPayoutConflictTests(unittest.TestCase):
    def setUp(self):
        self.conflicts = rule_conflicts([simple_monthly_benefit()], None)

    def test_tiers_are_kept_with_payout_state(self):
        self.assertEqual(len(self.conflicts), 1)
        tiers = self.conflicts[0]["tiers"]
        self.assertEqual([tier["rule_key"] for tier in tiers], ["r3", "r1", "r2"])     # 구간을 지우지 않는다
        self.assertEqual([tier["min_amt"] for tier in tiers], [None, 300000, 800000])
        self.assertEqual([tier["max_amt"] for tier in tiers], [None, 800000, None])
        self.assertEqual({tier["payout_known"] for tier in tiers}, {False})
        self.assertEqual({tier["value"] for tier in tiers}, {None})                     # 0으로 바꾸지 않는다
        self.assertEqual(self.conflicts[0]["applicable_rule_keys"], [])               # 전월 실적 구간은 결제 금액으로 판정하지 않는다

    def test_original_type_error_case(self):
        """원래 TypeError를 내던 문장들. 금액이 없는 문장도 포함한다."""
        for text in ("자동납부 시 할인됩니다.", "전월 실적 30만원 이상이면 할인됩니다.",
                     "전월 실적 30만원 이상 80만원 미만, 80만원 이상 구간으로 나뉩니다."):
            self.assertFalse(distorts_tier(text, self.conflicts), text)

    def test_amount_used_as_minimum_is_not_judged_without_payout(self):
        """지급값을 모르면 지급액 기준의 '왜곡' 판정은 하지 않는다(통과/차단을 단정하지 않음). 값 검증은 unknown_values가 맡는다."""
        self.assertFalse(distorts_tier("10,000원 이상이면 할인됩니다.", self.conflicts))

    def test_other_tier_helpers_do_not_raise(self):
        conflict = self.conflicts[0]
        self.assertEqual(tier_text(conflict),
                         "30만원 이상 시 지급액 정보 없음, 80만원 이상 시 지급액 정보 없음 구간이 기재되어 있습니다.")
        self.assertIsNone(picks_single_tier("30만원 이상", self.conflicts))
        only_high = [{"evidence_id": "E86", "quote": "80만원 이상\n15,000원", "benefit_ids": [conflict["benefit_id"]]}]
        self.assertFalse(tier_is_quoted(conflict, only_high))        # 30만원 기준이 인용에 없다
        both = [{"evidence_id": "E85", "quote": "30만원 이상\n80만원 미만", "benefit_ids": [conflict["benefit_id"]]}]
        self.assertTrue(tier_is_quoted(conflict, both))              # 지급액이 없으면 두 기준액만 원문에 있으면 된다

    def test_validate_answer_keeps_valid_points_and_drops_unbacked_amounts(self):
        benefit = simple_monthly_benefit()
        bid = benefit["benefit_id"]
        evidence = [{"evidence_id": "E77", "page_no": 1, "approval_status": "PENDING", "quote": "월납 요금 청구할인", "benefit_ids": [bid]},
                    {"evidence_id": "E81", "page_no": 1, "approval_status": "PENDING", "quote": "10,000원", "benefit_ids": [bid]},
                    {"evidence_id": "E82", "page_no": 1, "approval_status": "PENDING", "quote": "15,000원", "benefit_ids": [bid]}]
        context = {"benefits": [benefit], "payment_amount": None, "rule_selection_unresolved": rule_conflicts([benefit], None),
                   "unresolved": [], "evidence": evidence}
        raw = answer([point("월납 요금 대상 가맹점을 자동납부 시 할인됩니다.", ("E77",), bid),
                      point("월 할인 한도는 10,000원 / 15,000원입니다.", ("E81", "E82"), bid),
                      point("전월 실적에 따라 20,000원까지 할인됩니다.", ("E77",), bid)])     # 근거에 없는 금액
        result, warnings = validate_answer(raw, context, "휴대전화 요금 자동납부 할인 한도는?")
        texts = [item["text"] for item in result["points"]]
        self.assertIn("월납 요금 대상 가맹점을 자동납부 시 할인됩니다.", texts)
        self.assertIn("월 할인 한도는 10,000원 / 15,000원입니다.", texts)
        self.assertNotIn("전월 실적에 따라 20,000원까지 할인됩니다.", texts)
        self.assertTrue(any("20000" in warning or "2만" in warning or "20,000" in warning for warning in warnings), warnings)

    def test_answer_text_problem_does_not_raise(self):
        benefit = simple_monthly_benefit()
        context = {"benefits": [benefit], "payment_amount": None, "rule_selection_unresolved": rule_conflicts([benefit], None),
                   "unresolved": [], "evidence": []}
        known = card_graphrag.known_values(context, "", None)
        self.assertIsNone(card_graphrag.answer_text_problem("자동납부 시 할인됩니다.", context, "", known, set()))


class MixedAndPaidTierTests(unittest.TestCase):
    def test_paid_tiers_still_detect_wrong_pairs(self):
        conflicts = rule_conflicts([paid_tier_benefit()], 10000)
        self.assertEqual({tier["payout_known"] for tier in conflicts[0]["tiers"]}, {True})
        self.assertTrue(distorts_tier("3천원 이상 시 500원입니다.", conflicts))
        self.assertTrue(distorts_tier("5천원 결제 시 500원입니다.", conflicts))
        self.assertFalse(distorts_tier("결제 건당 3,000원 이상 100원, 10,000원 이상 500원입니다.", conflicts))

    def test_zero_payout_is_compared_like_any_value(self):
        conflicts = rule_conflicts([paid_tier_benefit(values=(0, 500))], 10000)
        self.assertTrue(conflicts[0]["tiers"][0]["payout_known"])
        self.assertFalse(distorts_tier("3천원 이상 0원, 1만원 이상 500원입니다.", conflicts))
        self.assertTrue(distorts_tier("1만원 이상 시 0원입니다.", conflicts))   # 0원은 3천원 구간의 값이다

    def test_mixed_tiers_compare_only_known_payouts(self):
        conflicts = rule_conflicts([paid_tier_benefit(values=(None, 500))], 10000)
        self.assertEqual([tier["payout_known"] for tier in conflicts[0]["tiers"]], [False, True])
        self.assertFalse(distorts_tier("1만원 이상 시 500원입니다.", conflicts))
        self.assertTrue(distorts_tier("5천원 결제 시 500원입니다.", conflicts))          # 확인된 구간의 왜곡은 계속 잡는다
        self.assertEqual(tier_text(conflicts[0]), "결제 건당 3천원 이상 시 지급액 정보 없음, 결제 건당 1만원 이상 시 500원 구간이 기재되어 있습니다.")
        # 1만원 결제는 두 구간에 해당한다. 500원만 쓰고 3천원 구간을 빠뜨리면 일부 구간만 답한 문장이다.
        self.assertEqual(picks_single_tier("1만원이면 500원입니다.", conflicts), "ONE PICK 캐시백")
        self.assertIsNone(picks_single_tier("3천원 이상 구간과 1만원 이상 500원 구간에 해당합니다.", conflicts))

    def test_validate_answer_with_unknown_payouts_and_two_applicable_tiers(self):
        """결제 건 기준 두 구간에 모두 해당하지만 지급값이 둘 다 없으면 시스템 구간 문장을 만들지 않는다(빈 값 집합 오판 방지)."""
        benefit = paid_tier_benefit(values=(None, None))
        context = {"benefits": [benefit], "payment_amount": 10000, "rule_selection_unresolved": rule_conflicts([benefit], 10000),
                   "unresolved": [], "evidence": [{"evidence_id": "EP", "page_no": 1, "approval_status": "PENDING",
                                                   "quote": "결제 건당 3천원 이상 / 1만원 이상", "benefit_ids": ["P1"]}]}
        self.assertEqual(context["rule_selection_unresolved"][0]["applicable_rule_keys"], ["low", "high"])
        result, warnings = validate_answer(answer([point("결제 건당 3천원 이상과 1만원 이상 구간이 있습니다.", ("EP",), "P1")],
                                                  conclusion="어떤 금액이 적용되는지는 아직 확정되지 않았습니다."),
                                           context, "1만원 결제하면?")
        self.assertFalse(any(item["origin"] == "system" for item in result["points"]))
        self.assertTrue(any("구간 지급액이 조회 자료에 없어" in warning for warning in warnings), warnings)
        self.assertNotIn("0원", result["answer_text"] or "")


@unittest.skipUnless(os.getenv("RUN_NEO4J_INTEGRATION") == "1", "실제 Neo4j 읽기 테스트는 명시적으로 켠다")
class LiveSimpleMonthlyTests(unittest.TestCase):
    """실제 Neo4j(읽기 전용)의 22/20261105_000099 상세 행으로 원래 오류 경로를 재현한다."""

    def test_real_detail_rows_do_not_raise(self):
        from card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import connect
        key = '["card_bnft",22,"20261105_000099"]'
        search = connect()
        try:
            detail = search.get_details([key])[key]
        finally:
            search.driver.close()
        benefit = card_graphrag.benefit_context(detail)
        self.assertEqual([rule["value"] for rule in benefit["rules"]], [None, None, None])   # 데이터 상태 확인(보정 전)
        conflicts = rule_conflicts([benefit], None)
        self.assertEqual([tier["payout_known"] for tier in conflicts[0]["tiers"]], [False, False, False])
        self.assertFalse(distorts_tier("자동납부 시 할인됩니다.", conflicts))
        self.assertIn("지급액 정보 없음", tier_text(conflicts[0]))


if __name__ == "__main__":
    unittest.main()
