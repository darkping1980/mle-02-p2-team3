import json
import unittest

from .neo4j_relational_model import _normalize, _normalize_vector, build


def table(name, pk, columns):
    return {"name": name, "type": "BASE TABLE", "pk": pk,
            "columns": [{"column_name": c, "udt_name": "jsonb" if c.endswith("_json") else "text"}
                        for c in columns], "fks": []}


def snapshot():
    tables = [
        table("card_product", ["card_id"], ["card_id", "product_nm", "nullable_txt"]),
        table("card_product_item", ["card_id", "card_product_item_id"],
              ["card_id", "card_product_item_id", "item_type_cd", "item_nm", "item_rule_txt", "item_limit_txt",
               "item_search_txt", "item_embedding", "item_data"]),
        table("card_product_doc", ["card_id", "card_doc_id"], ["card_id", "card_doc_id"]),
        table("card_doc", ["card_doc_id"], ["card_doc_id", "doc_title"]),
    ]
    rows = {
        "card_product": [{"card_id": 4, "product_nm": "카드 A", "nullable_txt": None}],
        "card_product_item": [{"card_id": 4, "card_product_item_id": 9, "item_type_cd": "BENEFIT",
                               "item_nm": "교통", "item_rule_txt": "월 1회", "item_limit_txt": None,
                               "item_search_txt": "버스", "item_embedding": [0.1, 0.2],
                               "item_data": {"rules": [{"amount": 1000}]}}],
        "card_product_doc": [{"card_id": 4, "card_doc_id": 7}],
        "card_doc": [{"card_doc_id": 7, "doc_title": "안내장"}],
    }
    return {"tables": tables, "rows": rows, "counts": {k: len(v) for k, v in rows.items()}}


class RelationalModelTests(unittest.TestCase):
    def test_pgvector_text_is_parsed_as_numeric_components(self):
        self.assertEqual(_normalize_vector("[0.1, -2, 3e-2]"), [0.1, -2.0, 0.03])

    def test_nested_json_arrays_stay_structured_for_source_json(self):
        value = {"branches": [{"atoms": [{"cond_min_amt": 600000}]}]}
        normalized = _normalize(value)
        self.assertIsInstance(normalized["branches"][0], dict)
        self.assertEqual(json.loads(json.dumps(normalized))["branches"][0]["atoms"][0]["cond_min_amt"], 600000)

    def test_preserves_table_rows_pk_json_null_and_embedding(self):
        model = build(snapshot())
        item = next(n for n in model["nodes"] if n["table"] == "card_product_item")
        self.assertEqual(item["pk"], {"card_id": 4, "card_product_item_id": 9})
        self.assertEqual(json.loads(item["props"]["source_json"])["item_data"], {"rules": [{"amount": 1000}]})
        self.assertIn("item_limit_txt", json.loads(item["props"]["null_columns_json"]))
        self.assertEqual(item["props"]["embedding"], [0.1, 0.2])
        self.assertNotIn("dp_card_bnft", {node["label"] for node in model["nodes"]})
        self.assertEqual(model["stats"]["node_count"], 3)

    def test_relationship_table_becomes_relationship_with_source_pk(self):
        model = build(snapshot())
        edge = next(e for e in model["relationships"] if e["source_table"] == "card_product_doc")
        self.assertEqual(edge["type"], "dp_has_document")
        self.assertEqual(json.loads(edge["props"]["source_json"]), {"card_id": 4, "card_doc_id": 7})
        self.assertEqual(len(model["relationships"]), 2)

    def test_unresolved_inferred_reference_fails_closed(self):
        data = snapshot()
        data["rows"]["card_product_item"][0]["card_id"] = 999
        with self.assertRaisesRegex(ValueError, "unresolved source reference"):
            build(data)


if __name__ == "__main__":
    unittest.main()
