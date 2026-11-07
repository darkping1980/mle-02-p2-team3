import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from payment_card.file_pipeline.extraction.parallel import process_chunks
from payment_card.file_pipeline.extraction.verify import verify_results
from payment_card.file_pipeline.extraction.pilot_run import run_pilot


class ParallelTests(unittest.TestCase):
    def test_results_preserved_and_retry_then_success(self):
        chunks = [{"chunk_id": f"c{i}", "page_no": 1, "start_pos": 1, "text": "x"} for i in range(3)]
        attempts = 0
        def call(_):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("temporary")
            return '{"schema_ver":"ONTOLOGY_V1","benefits":[],"conditions":[],"limits":[],"targets":[],"relations":[]}'
        with patch("payment_card.file_pipeline.extraction.parallel.time.sleep"):
            result = process_chunks(chunks, "sha", call, workers=1)
        self.assertEqual(len(result), 3)
        self.assertEqual([r["chunk_id"] for r in result], ["c0", "c1", "c2"])
        self.assertEqual(attempts, 4)

    def test_retry_count_and_failure_recorded(self):
        chunk = {"chunk_id": "c", "page_no": 1, "start_pos": 1, "text": "x"}
        calls = 0
        def fail(_):
            nonlocal calls
            calls += 1
            raise RuntimeError("offline")
        with patch("payment_card.file_pipeline.extraction.parallel.time.sleep"):
            result = process_chunks([chunk], "sha", fail, retries=2)
        self.assertEqual(calls, 3)
        self.assertEqual(result[0]["failures"][0]["code"], "llm_call_failure")


class VerifyTests(unittest.TestCase):
    def test_shared_keyword_mismatch_flags_only_heuristic_conflicts(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); chunks = root / "chunks"; results = root / "results"; out = root / "out"
            chunks.mkdir(); results.mkdir()
            (chunks / "d.chunks.json").write_text(json.dumps({"chunks": [{"chunk_id": "c", "text": "x"}]}))
            extraction = {
                "benefits": [], "conditions": [], "targets": [], "relations": [],
                "limits": [
                    {"id": "l1", "shared": False, "evidence": [{"text": "합산 한도", "location": {}}]},
                    {"id": "l2", "shared": True, "evidence": [{"text": "월 한도", "location": {}}]},
                    {"id": "l3", "shared": False, "evidence": [{"text": "월 한도", "location": {}}]},
                    {"id": "l4", "shared": True, "evidence": [{"text": "공동 한도", "location": {}}]},
                ],
            }
            (results / "c.result.json").write_text(json.dumps({"chunk_id": "c", "extraction": extraction}))
            verify_results(results, chunks, out)
            payload = json.loads(next(out.glob("*.verify.json")).read_text())
            self.assertEqual(
                [(f["item_id"], f["code"]) for f in payload["flags"]],
                [("l1", "shared_keyword_mismatch"), ("l1", "unlinked_item"),
                 ("l2", "shared_flag_without_keyword"), ("l2", "unlinked_item"),
                 ("l3", "unlinked_item"), ("l4", "unlinked_item")],
            )
            new_flags = [f for f in payload["flags"] if f["code"].startswith("shared_")]
            self.assertTrue(all(set(flag) == {"item_id", "code"} for flag in new_flags))

    def test_numeric_unlinked_and_quote_ratio_flags_without_quotes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); chunks = root / "chunks"; results = root / "results"; out = root / "out"
            chunks.mkdir(); results.mkdir()
            (chunks / "d.chunks.json").write_text(json.dumps({"chunks": [{"chunk_id": "c", "text": "3만원", "page_no": 1}]}))
            extraction = {"benefits": [{"id": "b1", "rate": "5%", "amount": None, "evidence": [{"text": "3만원", "location": None}]}],
                          "conditions": [{"id": "c1", "min_amount": 50000, "evidence": [{"text": "5천원", "location": {}}]}],
                          "limits": [], "targets": [], "relations": []}
            (results / "c.result.json").write_text(json.dumps({"chunk_id": "c", "extraction": extraction}))
            summary = verify_results(results, chunks, out)
            self.assertEqual(summary["chunks_with_flags"], 1)
            codes = summary["flags_by_code"]
            self.assertEqual(codes["numeric_not_in_quote"], 2)
            self.assertEqual(codes["unlinked_item"], 2)
            self.assertEqual(codes["ambiguous_or_missing_quotes"], 1)
            payload = json.loads(next(out.glob("*.verify.json")).read_text())
            self.assertNotIn("3만원", json.dumps(payload))


class PilotRunTests(unittest.TestCase):
    def test_plan_mode_never_builds_llm_call(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); chunks = root / "chunks"; chunks.mkdir()
            (chunks / "d.chunks.json").write_text(json.dumps({"doc_id": "d1", "doc_sha256": "sha", "chunks": [{"chunk_id": "c1", "text": "x", "page_no": 1, "start_pos": 1}]}))
            index = root / "documents.csv"; index.write_text("doc_id,canonical,ocr_needed,doc_role,card_type\nd1,Y,N,product_guide,credit\n")
            with patch("payment_card.file_pipeline.extraction.llm_adapter.create_llm_call", side_effect=AssertionError):
                plan = run_pilot(index, chunks, root / "work", 1, "fake", execute=False)
            self.assertEqual(plan["selected_chunks"], 1)
            self.assertTrue((root / "work" / "plan.json").is_file())


class CostGuardTests(unittest.TestCase):
    def test_refuses_large_estimate_and_allow_large_lifts_guard(self):
        from payment_card.file_pipeline.extraction import cli
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); chunks = root / "chunks"; chunks.mkdir()
            (chunks / "d.chunks.json").write_text(json.dumps({"doc_id": "d", "doc_sha256": "sha", "chunks": [{"chunk_id": "c1", "text": "x", "page_no": 1, "start_pos": 1}]}))
            args = ["run", "--chunk-dir", str(chunks), "--output-dir", str(root / "out"), "--model", "fake", "--execute"]
            with patch.object(cli, "estimate_prompt_size", return_value={"estimated_tokens": 200001}), \
                 patch.object(cli, "create_llm_call", side_effect=AssertionError("must refuse")):
                self.assertEqual(cli.main(args), 2)
            fake = lambda _: '{"schema_ver":"ONTOLOGY_V1","benefits":[],"conditions":[],"limits":[],"targets":[],"relations":[]}'
            with patch.object(cli, "estimate_prompt_size", return_value={"estimated_tokens": 200001}), \
                 patch.object(cli, "create_llm_call", return_value=fake):
                self.assertEqual(cli.main(args + ["--allow-large"]), 0)


if __name__ == "__main__":
    unittest.main()
