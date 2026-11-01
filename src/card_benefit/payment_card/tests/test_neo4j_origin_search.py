import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from src.card_benefit.payment_card.db_pipeline_origin_search import neo4j_search

APP = str(Path(__file__).resolve().parents[1] / "db_pipeline_origin_search" / "streamlit_app.py")


class FakeDriver:
    def close(self): pass


class EmptySearch:
    driver = FakeDriver()
    def list_benefits(self, keyword): return []


class SearchTests(unittest.TestCase):
    def test_queries_are_scoped_and_parameterized(self):
        for query in neo4j_search.QUERIES.values():
            self.assertIn("$ns", query)
            self.assertNotIn("DELETE ", query.upper())
            self.assertNotIn("CREATE ", query.upper())
        self.assertIn("$keyword", neo4j_search.LIST_QUERY)

    def test_source_preserves_unknown(self):
        self.assertEqual(neo4j_search.source({"source_json": '{"rule_select_cd": null}'}), {"rule_select_cd": None})

    def test_empty_search_ui(self):
        with patch.object(neo4j_search, "connect", return_value=EmptySearch()):
            app = AppTest.from_file(APP).run()
        self.assertFalse(app.exception)
        self.assertTrue(any("일치하는" in x.value for x in app.info))

    def test_connection_error_is_sanitized(self):
        with patch.object(neo4j_search, "connect", side_effect=RuntimeError("SECRET_VALUE")):
            app = AppTest.from_file(APP).run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertNotIn("SECRET_VALUE", app.error[0].value)


if __name__ == "__main__":
    unittest.main()
