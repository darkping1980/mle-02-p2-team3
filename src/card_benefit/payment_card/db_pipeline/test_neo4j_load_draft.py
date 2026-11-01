import unittest

from src.card_benefit.payment_card.db_pipeline.neo4j_dry_run import NS, Preview
from src.card_benefit.payment_card.db_pipeline.neo4j_load_draft import prepare, write_transaction


class Result:
    def __init__(self, rows=None): self.rows = rows or []
    def single(self, strict=True):
        return {"n": 1}
    def __iter__(self): return iter(self.rows)


class FakeTx:
    def __init__(self): self.calls = []
    def run(self, query, **params):
        self.calls.append((query, params))
        if "RETURN n.key AS key" in query: return Result([{"key": "one"}])
        if "RETURN r.key AS key" in query: return Result([{"key": "r"}])
        return Result()


class LoaderTests(unittest.TestCase):
    def test_transaction_uses_only_dedicated_scope(self):
        tx = FakeTx()
        nodes = [{"label": "A8Card", "props": {"key": "one", "namespace": NS}}]
        rels = [{"type": "A8_HAS_POLICY", "start": "one", "end": "two", "key": "r", "source_json": "{}"}]
        self.assertEqual(write_transaction(tx, nodes, rels), (1, 1))
        self.assertTrue(all("A8Test" in query for query, _ in tx.calls))
        self.assertTrue(all(params.get("namespace", params.get("ns")) == NS for _, params in tx.calls))

    def test_preview_count_guard(self):
        graph = Preview(); graph.node("Card", [2], {})
        with self.assertRaises(ValueError): prepare(graph)


if __name__ == "__main__":
    unittest.main()
