import json
from pathlib import Path
import re
import sqlite3
import unittest


QUERY_FILE = Path(__file__).parents[1] / "file_pipeline" / "graph" / "queries.sql"
SQL = QUERY_FILE.read_text(encoding="utf-8")


class GraphQueryTests(unittest.TestCase):
    def test_queries_are_read_only_and_reference_only_fp_tables(self):
        statements = re.sub(r"--[^\n]*", "", SQL)
        self.assertFalse(re.search(r"\b(insert|update|delete|drop|truncate)\b", statements, re.I))
        tables = re.findall(r"\b(?:from|join)\s+([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?)", statements, re.I)
        self.assertTrue(tables)
        ctes = set(re.findall(r"\bwith\s+recursive\s+([a-z_][a-z0-9_]*)", statements, re.I))
        for table in tables:
            self.assertTrue(table.split(".")[-1].startswith("fp_") or table in ctes, table)
        self.assertEqual(len([part for part in re.split(r";\s*(?:\n|$)", SQL) if part.strip()]), 5)

    def test_queries_execute_against_synthetic_export_shaped_sqlite_data(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE fp_nodes (id TEXT, node_type TEXT, props TEXT, chunk_id TEXT, run_id TEXT);
            CREATE TABLE fp_edges (id TEXT, source_id TEXT, target_id TEXT, edge_type TEXT, run_id TEXT);
            CREATE TABLE fp_evidence (id INTEGER, node_id TEXT, edge_id TEXT, doc_sha256 TEXT,
                page_no INTEGER, start_pos INTEGER, end_pos INTEGER, quote_status TEXT);
        """)
        nodes = [
            ("card:bank:1", "Card", {"product_name": "Sample Card", "issuer": "Bank"}),
            ("b1", "Benefit", {"name": "Cashback"}),
            ("b2", "Benefit", {"name": "Points"}),
            ("cond1", "Condition", {"text": "minimum spend"}),
            ("lim1", "Limit", {"text": "monthly cap", "shared": True}),
            ("target1", "Target", {"text": "online"}),
        ]
        connection.executemany("INSERT INTO fp_nodes VALUES (?, ?, ?, 'chunk-1', 'run-1')",
                               [(i, t, json.dumps(p)) for i, t, p in nodes])
        edges = [("o1", "card:bank:1", "b1", "OFFERS"), ("o2", "card:bank:1", "b2", "OFFERS"),
                 ("e1", "b1", "b2", "MUTUALLY_EXCLUSIVE"), ("c1", "b1", "cond1", "HAS_CONDITION"),
                 ("l1", "b1", "lim1", "HAS_LIMIT"), ("a1", "b1", "target1", "APPLIES_TO")]
        connection.executemany("INSERT INTO fp_edges VALUES (?, ?, ?, ?, 'run-1')", edges)
        connection.execute("INSERT INTO fp_evidence VALUES (1, 'b1', NULL, ?, 2, 10, 20, 'located')", ("a" * 64,))
        statements = [part.strip() for part in re.split(r";\s*(?:\n|$)", SQL) if part.strip()]
        results = [connection.execute(statement, {"card_name": "sample", "benefit_id": "b1",
                                                   "start_node_id": "card:bank:1", "max_hops": 2}).fetchall()
                   for statement in statements]
        self.assertEqual(len(results), 5)
        self.assertTrue(any(row["benefit_id"] == "b1" and row["condition_id"] == "cond1" for row in results[0]))
        self.assertEqual((results[1][0]["page_no"], results[1][0]["start_pos"], results[1][0]["end_pos"]), (2, 10, 20))
        self.assertEqual(len(results[2]), 1)
        self.assertTrue(any(row["limit_id"] == "lim1" for row in results[3]))
        self.assertTrue(any(row["hop"] == 2 for row in results[4]))


if __name__ == "__main__":
    unittest.main()
