from __future__ import annotations

import unittest

from pydantic import ValidationError

from payment_card.file_pipeline.extraction.evidence import locate_quote
from payment_card.file_pipeline.extraction.schema import Extraction, all_quotes

# 실제 청크 t1_p0002_001~005에서 가져온 발췌. U+200C(제로폭)와 U+0007(벨)이 원문 그대로 들어 있다.
EXCERPT = "바\n※ ‌\x07음식점 매장이 백화점/할인점 등에 입점된 매장인 경우는 할인 제외\n식비\n음식점/주점 업종, 배달의민족, 쿠팡이츠, 요기요\n5%"
PAGE_PREFIX = "앞글"          # 쪽 원문에서 청크 앞에 붙는 글
CHUNK_START = len(PAGE_PREFIX) + 1   # 쪽 원문 기준 1부터
PAGE = PAGE_PREFIX + EXCERPT


def example_extraction() -> dict:
    return {
        "benefits": [{
            "id": "b_food",
            "name": "식비 할인",
            "rate": "5%",
            "evidence": [{"text": "식비 음식점/주점 업종, 배달의민족, 쿠팡이츠, 요기요 5%"}],
        }],
        "conditions": [{
            "id": "c_excl",
            "text": "백화점/할인점 입점 음식점은 제외",
            "kind": "EXCLUDE",
            "evidence": [{"text": "※ 음식점 매장이 백화점/할인점 등에 입점된 매장인 경우는 할인 제외"}],
        }],
        "targets": [{
            "id": "t_food",
            "text": "음식점/주점 업종, 배달의민족, 쿠팡이츠, 요기요",
            "kind": "MERCHANT",
            "evidence": [{"text": "음식점/주점 업종, 배달의민족, 쿠팡이츠, 요기요"}],
        }],
        "relations": [
            {"source": "b_food", "target": "c_excl", "type": "HAS_CONDITION",
             "evidence": [{"text": "※ 음식점 매장이 백화점/할인점 등에 입점된 매장인 경우는 할인 제외"}]},
            {"source": "b_food", "target": "t_food", "type": "APPLIES_TO",
             "evidence": [{"text": "음식점/주점 업종, 배달의민족, 쿠팡이츠, 요기요"}]},
        ],
    }


class LocateQuoteTest(unittest.TestCase):
    def test_real_case_zero_width_and_bell_are_found_and_mapped_back(self):
        quote = "※ 음식점 매장이 백화점/할인점 등에 입점된 매장인 경우는 할인 제외"
        loc = locate_quote(EXCERPT, CHUNK_START, quote)
        self.assertIsNotNone(loc)
        self.assertEqual(PAGE[loc.start_pos - 1:loc.end_pos], loc.matched)
        self.assertIn("‌", loc.matched)     # 원문 글자 그대로 돌려준다
        self.assertEqual(loc.occurrences, 1)

    def test_line_break_difference_is_ignored(self):
        loc = locate_quote(EXCERPT, CHUNK_START, "식비 음식점/주점 업종, 배달의민족, 쿠팡이츠, 요기요 5%")
        self.assertIsNotNone(loc)
        self.assertEqual(PAGE[loc.start_pos - 1:loc.end_pos], loc.matched)
        self.assertTrue(loc.matched.startswith("식비"))
        self.assertTrue(loc.matched.endswith("5%"))

    def test_other_control_characters_after_bullet_are_ignored(self):
        # 우리카드 청크 8af8617177f0f472-p0001-c01, 9d762a0fffd6037e-p0002-c01의 글머리표 뒤 U+0001·U+0003. 발췌다.
        for text, quote, tail in (
            (" • \x01결제계좌 개설기관의 영업 마감시간(16시) 이후 결제계좌에 입금된 금액에 대해서는",
             "• 결제계좌 개설기관의 영업 마감시간(16시) 이후", "이후"),
            ("• \x03‘우리WON멤버스’ 회원은 ‘우리WON꿀머니’로, 비회원은 ‘모아포인트’로",
             "• ‘우리WON멤버스’ 회원은", "회원은"),
        ):
            loc = locate_quote(text, 5, quote)
            self.assertIsNotNone(loc, quote)
            self.assertTrue(loc.matched.startswith("•"))
            self.assertTrue(loc.matched.endswith(tail))
            self.assertEqual(text[loc.start_pos - 5:loc.end_pos - 5 + 1], loc.matched)  # 쪽 5번째 글자부터

    def test_missing_quote_returns_none(self):
        self.assertIsNone(locate_quote(EXCERPT, CHUNK_START, "이 문장은 청크에 없습니다"))

    def test_empty_quote_is_an_error(self):
        with self.assertRaises(ValueError):
            locate_quote(EXCERPT, CHUNK_START, "  ‌ ")

    def test_repeated_quote_reports_count_and_uses_first(self):
        text = "5% 할인, 5% 할인"
        loc = locate_quote(text, 10, "5% 할인")
        self.assertEqual(loc.occurrences, 2)
        self.assertEqual(loc.start_pos, 10)
        self.assertEqual(loc.matched, "5% 할인")

    def test_positions_are_page_based_inclusive(self):
        loc = locate_quote("ABCDE", 7, "CD")
        self.assertEqual((loc.start_pos, loc.end_pos), (9, 10))
        self.assertEqual("xxxxxxABCDE"[loc.start_pos - 1:loc.end_pos], "CD")  # 청크는 쪽 7번째 글자부터 시작


class SchemaTest(unittest.TestCase):
    def test_example_passes_and_every_quote_is_located(self):
        ex = Extraction.model_validate(example_extraction())
        quotes = all_quotes(ex)
        self.assertGreaterEqual(len(quotes), 4)
        for quote in quotes:
            loc = locate_quote(EXCERPT, CHUNK_START, quote)
            self.assertIsNotNone(loc, quote)
            self.assertEqual(PAGE[loc.start_pos - 1:loc.end_pos], loc.matched)

    def test_entity_without_evidence_is_rejected(self):
        data = example_extraction()
        data["benefits"][0]["evidence"] = []
        with self.assertRaises(ValidationError):
            Extraction.model_validate(data)

    def test_position_fields_from_llm_are_rejected(self):
        data = example_extraction()
        data["benefits"][0]["start_pos"] = 1
        with self.assertRaises(ValidationError):
            Extraction.model_validate(data)
        data = example_extraction()
        data["benefits"][0]["evidence"][0]["start_pos"] = 1
        with self.assertRaises(ValidationError):
            Extraction.model_validate(data)

    def test_relation_to_unknown_id_is_rejected(self):
        data = example_extraction()
        data["relations"][0]["target"] = "nope"
        with self.assertRaises(ValidationError):
            Extraction.model_validate(data)

    def test_relation_with_wrong_entity_kinds_is_rejected(self):
        data = example_extraction()
        data["relations"][0] = {"source": "c_excl", "target": "b_food", "type": "HAS_CONDITION",
                                "evidence": [{"text": "x"}]}
        with self.assertRaises(ValidationError):
            Extraction.model_validate(data)

    def test_duplicate_id_is_rejected(self):
        data = example_extraction()
        data["targets"][0]["id"] = "b_food"
        with self.assertRaises(ValidationError):
            Extraction.model_validate(data)

    def test_unknown_condition_kind_is_rejected(self):
        data = example_extraction()
        data["conditions"][0]["kind"] = "SOMETHING"
        with self.assertRaises(ValidationError):
            Extraction.model_validate(data)

    def test_condition_min_amount_is_integer_and_not_negative(self):
        data = example_extraction()
        data["conditions"][0]["min_amount"] = 300000
        self.assertEqual(Extraction.model_validate(data).conditions[0].min_amount, 300000)
        data["conditions"][0]["min_amount"] = -1
        with self.assertRaises(ValidationError):
            Extraction.model_validate(data)

    def test_limit_unlimited_and_shared(self):
        data = example_extraction()
        quote = [{"text": "할인한도 제한 없음"}]
        data["limits"] = [{"id": "l_free", "text": "할인한도 제한 없음", "period": "MONTH", "unlimited": True, "evidence": quote},
                          {"id": "l_cap", "text": "통합 월 2회", "period": "MONTH", "amount": 2, "shared": True, "evidence": quote}]
        limits = Extraction.model_validate(data).limits
        self.assertTrue(limits[0].unlimited)
        self.assertTrue(limits[1].shared)
        data["limits"][0]["amount"] = 5
        with self.assertRaises(ValidationError):
            Extraction.model_validate(data)

    def test_mutually_exclusive_links_two_benefits_only(self):
        data = example_extraction()
        data["benefits"].append({"id": "b_inst", "name": "장기할부 청구할인", "evidence": [{"text": "장기할부 청구할인"}]})
        link = {"source": "b_food", "target": "b_inst", "type": "MUTUALLY_EXCLUSIVE", "evidence": [{"text": "중복 제공 안됨"}]}
        data["relations"].append(link)
        Extraction.model_validate(data)
        data["relations"][-1] = {**link, "target": "c_excl"}      # 혜택-조건은 허용하지 않는다
        with self.assertRaises(ValidationError):
            Extraction.model_validate(data)
        data["relations"][-1] = {**link, "target": "b_food"}      # 자기 자신도 안 된다
        with self.assertRaises(ValidationError):
            Extraction.model_validate(data)


if __name__ == "__main__":
    unittest.main()
