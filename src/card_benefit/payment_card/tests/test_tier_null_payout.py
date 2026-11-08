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
from card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import (AnswerPoint, CardAnswer, rule_conflicts, tier_token)

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

class NullPayoutConflictTests(unittest.TestCase):
    def setUp(self):
        self.conflicts = rule_conflicts([simple_monthly_benefit()], None)

    def test_explicit_cap_mapping_and_approval_amount_do_not_create_payout_conflict(self):
        benefit = simple_monthly_benefit()
        benefit["limit_tiers"] = [
            {"min_amt": 300000, "max_amt": 800000, "cap": {"amount": 10000}},
            {"min_amt": 800000, "max_amt": None, "cap": {"amount": 15000}},
        ]
        self.assertEqual(rule_conflicts([benefit], None), [])

    def test_tiers_are_kept_with_payout_state(self):
        self.assertEqual(len(self.conflicts), 1)
        tiers = self.conflicts[0]["tiers"]
        self.assertEqual([tier["rule_key"] for tier in tiers], ["r3", "r1", "r2"])     # 구간을 지우지 않는다
        self.assertEqual([tier["min_amt"] for tier in tiers], [None, 300000, 800000])
        self.assertEqual([tier["max_amt"] for tier in tiers], [None, 800000, None])
        self.assertEqual({tier["payout_known"] for tier in tiers}, {False})
        self.assertEqual({tier["value"] for tier in tiers}, {None})                     # 0으로 바꾸지 않는다
        self.assertEqual(self.conflicts[0]["applicable_rule_keys"], [])               # 전월 실적 구간은 결제 금액으로 판정하지 않는다
