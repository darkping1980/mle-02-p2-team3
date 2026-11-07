from __future__ import annotations

import json
import unittest

from payment_card.file_pipeline.extraction.runner import run_chunk
from payment_card.file_pipeline.extraction.prompt import (
    ENUM_DESCRIPTIONS, EXAMPLE_OUTPUT, build_prompt, enum_values_from_schema,
)
from payment_card.file_pipeline.extraction.schema import (
    ALLOWED_RELATIONS, Benefit, Condition, ConditionKind, Extraction, Limit, Relation, Target, TargetKind,
)
from typing import Literal, get_args, get_origin


DOC_SHA256 = "a" * 64
CHUNK = {"chunk_id": "ignored-as-key", "page_no": 3, "start_pos": 11,
         "text": "식비 5% 할인"}


def response(quote: str = "식비 5% 할인") -> str:
    return json.dumps({
        "schema_ver": "ONTOLOGY_V1",
        "benefits": [{"id": "b1", "name": "식비 할인", "rate": "5%",
                      "evidence": [{"text": quote}]}],
    }, ensure_ascii=False)


class ExtractionRunnerTest(unittest.TestCase):
    def test_prompt_example_matches_extraction_schema(self):
        self.assertIsInstance(Extraction.model_validate(EXAMPLE_OUTPUT), Extraction)

    def test_prompt_explicitly_requires_evidence_objects_and_includes_example(self):
        prompt = build_prompt(CHUNK)
        self.assertIn("evidence는 반드시 객체의 목록: 문자열이나 문자열 목록은 안 됨", prompt)
        self.assertIn(json.dumps(EXAMPLE_OUTPUT, ensure_ascii=False, indent=2), prompt)

    def test_prompt_uses_simple_ascii_ids_for_entities(self):
        prompt = build_prompt(CHUNK)
        self.assertIn("Benefit은 b1, b2", prompt)
        self.assertIn("Condition은 c1, c2", prompt)
        self.assertIn("Limit은 l1, l2", prompt)
        self.assertIn("Target은 t1, t2", prompt)
        self.assertIn("관계 source와 target에는 해당 엔티티의 id를 그대로 복사", prompt)

    def test_prompt_prefers_unique_distinctive_quote_within_one_sentence(self):
        prompt = build_prompt(CHUNK)
        self.assertIn("같은 인용문이 청크 안에 두 번 이상 나오지 않도록", prompt)
        self.assertIn("금액·업종명·혜택명", prompt)
        self.assertIn("한 문장 안에서", prompt)

    def test_prompt_clarifies_channel_is_target_only_kind(self):
        prompt = build_prompt(CHUNK)
        rule = (
            "CHANNEL 은 Target(대상)의 kind 전용 값이다. Condition(조건)의 kind 에는 쓰지 말고, "
            "온라인/오프라인·앱 결제 같은 채널성 조건은 PAYMENT 또는 USAGE 로, 가맹점 조건은 "
            "MERCHANT 로, 해당하지 않으면 OTHER 로 분류하라."
        )
        self.assertIn(rule, prompt)

        condition_kinds = set(get_args(ConditionKind))
        target_kinds = set(get_args(TargetKind))
        self.assertNotIn("CHANNEL", condition_kinds)
        self.assertIn("CHANNEL", target_kinds)
        self.assertTrue({"PAYMENT", "USAGE", "MERCHANT", "OTHER"} <= condition_kinds)

    def test_prompt_clarifies_limit_amount_is_integer_and_converted(self):
        prompt = build_prompt(CHUNK)
        self.assertIn("Limit.amount 는 정수 타입이므로 금액은 원, 횟수는 횟수 단위로 환산한 숫자만 쓰세요.", prompt)
        self.assertIn("3만원 → 30000", prompt)
        self.assertIn("Condition.amount는 원문 문자열을 허용하지만 Limit.amount에는 문자열을 넣지 마세요.", prompt)
        self.assertEqual(Limit.model_fields["amount"].annotation, int | None)

    def test_prompt_clarifies_target_kind_values_and_condition_only_kinds(self):
        prompt = build_prompt(CHUNK)
        target_kinds = set(get_args(TargetKind))
        self.assertNotIn("PAYMENT", target_kinds)
        self.assertIn("Target.kind 허용값은 MERCHANT, INDUSTRY, CHANNEL, SERVICE, OTHER뿐입니다.", prompt)
        self.assertIn("PAYMENT, USAGE, SPEND_REQ, EXCLUDE는 Condition 전용이므로 Target.kind에 쓰지 마세요.", prompt)

    def test_prompt_lists_schema_fields_and_literal_values(self):
        prompt = build_prompt(CHUNK)
        for model in (Benefit, Condition, Limit, Target, Relation):
            for name, field in model.model_fields.items():
                self.assertIn(name, prompt)
                self.assertIn("필수" if field.is_required() else "선택", prompt)
                for value in self._literal_values(field.annotation):
                    self.assertIn(value, prompt)
        for name, (source, target) in ALLOWED_RELATIONS.items():
            self.assertIn(f"{name}: {source}→{target}", prompt)
        for rule in ("shared=true", "method=None", "kind=EXCLUDE", "확실하지 않으면 연결하지 마세요"):
            self.assertIn(rule, prompt)
        self.assertIn("목록 밖의 값을 만들지 마세요", prompt)

    def test_every_schema_enum_has_exactly_one_description(self):
        self.assertEqual(set(ENUM_DESCRIPTIONS), enum_values_from_schema())
        self.assertTrue(all(description.strip() for description in ENUM_DESCRIPTIONS.values()))

    @classmethod
    def _literal_values(cls, annotation):
        if get_origin(annotation) is Literal:
            return [str(value) for value in get_args(annotation)]
        return [value for arg in get_args(annotation) for value in cls._literal_values(arg)]

    def test_normal_response_adds_page_based_location(self):
        prompts = []
        result = run_chunk(CHUNK, DOC_SHA256, lambda prompt: prompts.append(prompt) or response())
        location = result["extraction"]["benefits"][0]["evidence"][0]["location"]
        self.assertEqual((location["doc_sha256"], location["page_no"]), (DOC_SHA256, 3))
        self.assertEqual((location["start_pos"], location["end_pos"]), (11, 18))
        self.assertEqual(result["chunk_length"], len(CHUNK["text"]))
        self.assertIn(CHUNK["text"], prompts[0])
        self.assertEqual(result["failures"], [])

    def test_broken_json_is_structured_failure(self):
        result = run_chunk(CHUNK, DOC_SHA256, lambda _: "{")
        self.assertEqual(result["failures"][0]["code"], "json_parse_failure")

    def test_json_fence_is_stripped_and_recorded_in_notes(self):
        result = run_chunk(CHUNK, DOC_SHA256, lambda _: f"```json\n{response()}\n```")
        self.assertIsNotNone(result["extraction"])
        self.assertEqual(result["failures"], [])
        self.assertTrue(any("코드 펜스" in note for note in result["notes"]))

    def test_json_fence_with_explanation_remains_parse_failure(self):
        result = run_chunk(CHUNK, DOC_SHA256, lambda _: f"설명\n```json\n{response()}\n```")
        self.assertEqual(result["failures"][0]["code"], "json_parse_failure")

    def test_schema_violation_is_structured_failure(self):
        result = run_chunk(CHUNK, DOC_SHA256, lambda _: '{"benefits":[{"id":"b"}]}')
        self.assertEqual(result["failures"][0]["code"], "schema_validation_failure")

    def test_quote_not_found_is_retained_without_location(self):
        result = run_chunk(CHUNK, DOC_SHA256, lambda _: response("원문에 없는 문장"))
        quote = result["extraction"]["benefits"][0]["evidence"][0]
        self.assertEqual(quote["text"], "원문에 없는 문장")
        self.assertIsNone(quote["location"])
        self.assertEqual(result["failures"][0]["code"], "quote_location_failure")

    def test_duplicate_quote_is_ambiguous(self):
        chunk = {**CHUNK, "text": "식비 5% 할인, 식비 5% 할인"}
        result = run_chunk(chunk, DOC_SHA256, lambda _: response())
        quote = result["extraction"]["benefits"][0]["evidence"][0]
        self.assertIsNone(quote["location"])
        ambiguous = [f for f in result["failures"] if f["code"] == "quote_location_ambiguous"]
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0]["occurrences"], 2)


if __name__ == "__main__":
    unittest.main()
