import unittest

from openai.lib._pydantic import to_strict_json_schema

from card_benefit.payment_card.db_pipeline.extraction_schema import PageExtraction


class ExtractionDescriptionsTests(unittest.TestCase):
    def test_every_strict_schema_property_has_a_description(self):
        schema = to_strict_json_schema(PageExtraction)
        for name, model in [("PageExtraction", schema), *schema["$defs"].items()]:
            for field, definition in model.get("properties", {}).items():
                with self.subTest(model=name, field=field):
                    self.assertTrue(definition.get("description"))

    def test_existing_minimal_response_and_defaults_validate(self):
        page = PageExtraction.model_validate({"page_no": 1, "page_role": "DETAIL"})
        self.assertEqual(page.benefits, [])
        self.assertIsNone(page.product)
        self.assertEqual(page.card_conditions, [])


if __name__ == "__main__":
    unittest.main()
