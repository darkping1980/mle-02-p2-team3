from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from payment_card.file_pipeline.extraction.cli import main
from payment_card.file_pipeline.extraction.llm_adapter import create_llm_call


class ExtractionCliTest(unittest.TestCase):
    def test_adapter_uses_injected_client_without_exposing_key(self):
        captured = {}

        class FakeResponse:
            content = "응답"

        class FakeClient:
            def invoke(self, prompt):
                captured["prompt"] = prompt
                return FakeResponse()

        def factory(**kwargs):
            captured.update(kwargs)
            return FakeClient()

        with patch.dict(os.environ, {"TEST_LLM_KEY": "secret-value"}):
            call = create_llm_call("test-model", "TEST_LLM_KEY", client_factory=factory)
        self.assertEqual(call("질문"), "응답")
        self.assertEqual(captured, {"model": "test-model", "api_key": "secret-value", "prompt": "질문"})

    def test_key_whitespace_and_carriage_return_are_stripped(self):
        captured = {}

        class FakeClient:
            def invoke(self, prompt):
                return "응답"

        def factory(**kwargs):
            captured.update(kwargs)
            return FakeClient()

        with patch.dict(os.environ, {"TEST_LLM_KEY": " secret-value\r\n"}):
            create_llm_call("test-model", "TEST_LLM_KEY", client_factory=factory)
        self.assertEqual(captured["api_key"], "secret-value")

    def test_missing_key_error_names_variable_but_not_value(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "TEST_LLM_KEY") as caught:
                create_llm_call("test-model", "TEST_LLM_KEY")
        self.assertNotIn("secret", str(caught.exception))

    def test_sdk_exception_is_sanitized(self):
        class FakeClient:
            def invoke(self, prompt):
                raise RuntimeError("secret-value leaked by SDK")

        with patch.dict(os.environ, {"TEST_LLM_KEY": "secret-value"}):
            call = create_llm_call("test-model", "TEST_LLM_KEY", client_factory=lambda **_: FakeClient())
        with self.assertRaises(RuntimeError) as caught:
            call("질문")
        self.assertNotIn("secret-value", str(caught.exception))

    def test_sdk_exception_includes_safe_chain_and_metadata(self):
        class ConnectError(Exception):
            pass

        class APIConnectionError(Exception):
            status_code = 503
            code = "connection_error"
            type = "api_error"

        root = ConnectError("sk-root-secret")
        error = APIConnectionError("api_key=secret-value")
        error.__cause__ = root

        class FakeClient:
            def invoke(self, prompt):
                raise error

        with patch.dict(os.environ, {"TEST_LLM_KEY": "secret-value"}):
            call = create_llm_call("test-model", "TEST_LLM_KEY", client_factory=lambda **_: FakeClient())
        with self.assertRaises(RuntimeError) as caught:
            call("질문")

        message = str(caught.exception)
        self.assertIn("APIConnectionError", message)
        self.assertIn("ConnectError", message)
        self.assertIn("503", message)
        self.assertIn("connection_error", message)
        self.assertIn("api_error", message)
        self.assertNotIn("sk-", message)
        self.assertNotIn("secret-value", message)

    def test_run_dry_run_does_not_create_output_and_rejects_repo_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chunks = root / "chunks"
            chunks.mkdir()
            (chunks / "doc.chunks.json").write_text('{"chunks": []}', encoding="utf-8")
            self.assertEqual(main(["run", "--chunk-dir", str(chunks), "--output-dir", str(root / "out")]), 0)
        repo_root = Path(__file__).resolve().parents[4]
        self.assertEqual(main(["run", "--chunk-dir", ".", "--output-dir", str(repo_root / "unsafe")]), 2)

    def test_summarize_reaggregates_saved_results_without_llm_calls(self):
        import json

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chunk_dir = root / "chunks"
            result_dir = root / "results"
            chunk_dir.mkdir()
            result_dir.mkdir()
            document = {
                "doc_id": "doc1",
                "doc_sha256": "a" * 64,
                "chunks": [{"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": "혜택"}],
            }
            (chunk_dir / "doc1.chunks.json").write_text(json.dumps(document), encoding="utf-8")
            result = {
                "doc_sha256": "a" * 64,
                "page_no": 1,
                "chunk_id": "doc1-c1",
                "chunk_length": 2,
                "extraction": {"benefits": [{"evidence": [{"location": None}]}]},
                "failures": [{"code": "quote_location_ambiguous", "path": "benefits[0].evidence[0]"}],
                "notes": [],
            }
            (result_dir / "doc1-c1.result.json").write_text(json.dumps(result), encoding="utf-8")

            self.assertEqual(main(["summarize", "--chunk-dir", str(chunk_dir), "--output-dir", str(result_dir)]), 0)

            summary = json.loads((result_dir / "doc1.summary.json").read_text(encoding="utf-8"))
            self.assertEqual((summary["succeeded"], summary["failed"], summary["review_required"]), (1, 0, 1))
            self.assertEqual(summary["quote_locations"], {"success": 0, "failure": 0, "ambiguous": 1})
            self.assertEqual(summary["missing_results"], 0)

    def test_summarize_rejects_chunk_ids_missing_from_chunk_files(self):
        import json

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chunk_dir = root / "chunks"
            result_dir = root / "results"
            chunk_dir.mkdir()
            result_dir.mkdir()
            document = {
                "doc_id": "doc1",
                "doc_sha256": "a" * 64,
                "chunks": [{"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": "혜택"}],
            }
            (chunk_dir / "doc1.chunks.json").write_text(json.dumps(document), encoding="utf-8")
            wanted_ids = root / "wanted.json"
            wanted_ids.write_text(json.dumps(["missing-c1"]), encoding="utf-8")

            self.assertEqual(main([
                "summarize", "--chunk-dir", str(chunk_dir), "--output-dir", str(result_dir),
                "--chunk-ids", str(wanted_ids),
            ]), 2)
            self.assertFalse((result_dir / "doc1.summary.json").exists())


if __name__ == "__main__":
    unittest.main()
