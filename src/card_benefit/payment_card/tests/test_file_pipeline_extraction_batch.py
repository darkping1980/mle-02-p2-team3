from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from payment_card.file_pipeline.extraction.batch import _summarize, run_batch, summarize_batch


DOC_SHA256 = "a" * 64


def write_document(folder: Path, doc_id: str, chunks: list[dict]) -> Path:
    path = folder / f"{doc_id}.chunks.json"
    path.write_text(json.dumps({
        "schema_version": "chunks-v1", "doc_id": doc_id,
        "doc_sha256": DOC_SHA256, "chunks": chunks,
    }), encoding="utf-8")
    return path


def valid_response(quote: str) -> str:
    return json.dumps({
        "schema_ver": "ONTOLOGY_V1",
        "benefits": [{"id": "b1", "name": "할인", "evidence": [{"text": quote}]}],
    }, ensure_ascii=False)


class ExtractionBatchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "results"

    def tearDown(self):
        self.temp.cleanup()

    def test_runs_chunks_and_saves_chunk_and_document_results(self):
        source = write_document(self.root, "doc1", [
            {"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": "식비 할인"},
            {"chunk_id": "doc1-c2", "page_no": 2, "start_pos": 1, "text": "교통 할인"},
        ])
        result = run_batch(source, lambda _: valid_response("식비 할인"), self.output)

        self.assertEqual(result["documents"][0]["summary"]["chunks"], 2)
        self.assertEqual(len(list(self.output.glob("*.result.json"))), 2)
        saved = json.loads((self.output / "doc1-c1.result.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["doc_sha256"], DOC_SHA256)
        self.assertTrue((self.output / "doc1.summary.json").exists())

    def test_llm_exception_is_recorded_and_following_chunk_runs(self):
        source = write_document(self.root, "doc1", [
            {"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": "첫 혜택"},
            {"chunk_id": "doc1-c2", "page_no": 2, "start_pos": 1, "text": "둘째 혜택"},
        ])
        prompts = []

        def llm_call(prompt):
            prompts.append(prompt)
            if "첫 혜택" in prompt:
                raise RuntimeError("연결 오류")
            return valid_response("둘째 혜택")

        run_batch(source, llm_call, self.output)
        failure = json.loads((self.output / "doc1-c1.result.json").read_text(encoding="utf-8"))
        success = json.loads((self.output / "doc1-c2.result.json").read_text(encoding="utf-8"))
        self.assertEqual(failure["failures"][0]["code"], "llm_call_failure")
        self.assertEqual(failure["failures"][0]["exception_type"], "RuntimeError")
        self.assertIn("연결 오류", failure["failures"][0]["message"])
        self.assertIsNone(failure["extraction"])
        self.assertEqual(success["failures"], [])
        self.assertEqual(len(prompts), 4)  # one initial attempt plus two retries for the failed chunk

    def test_resume_skips_existing_chunk_result(self):
        source = write_document(self.root, "doc1", [
            {"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": "혜택"},
        ])
        self.output.mkdir()
        existing = {"doc_sha256": DOC_SHA256, "page_no": 1, "chunk_id": "doc1-c1",
                    "chunk_length": 2, "extraction": None, "failures": [], "notes": []}
        (self.output / "doc1-c1.result.json").write_text(json.dumps(existing), encoding="utf-8")
        called = []

        result = run_batch(source, lambda prompt: called.append(prompt) or valid_response("혜택"), self.output)

        self.assertEqual(called, [])
        self.assertEqual(result["documents"][0]["summary"]["skipped"], 1)
        self.assertEqual(json.loads((self.output / "doc1-c1.result.json").read_text(encoding="utf-8")), existing)

    def test_resume_retries_llm_call_failure(self):
        source = write_document(self.root, "doc1", [
            {"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": "혜택"},
        ])
        self.output.mkdir()
        failed = {"doc_sha256": DOC_SHA256, "page_no": 1, "chunk_id": "doc1-c1", "chunk_length": 2,
                  "extraction": None, "notes": [],
                  "failures": [{"code": "llm_call_failure", "message": "시간 초과", "exception_type": "TimeoutError"}]}
        (self.output / "doc1-c1.result.json").write_text(json.dumps(failed), encoding="utf-8")
        called = []

        result = run_batch(source, lambda prompt: called.append(prompt) or valid_response("혜택"), self.output)

        self.assertEqual(len(called), 1)
        self.assertEqual(result["documents"][0]["summary"]["skipped"], 0)

    def test_max_chunks_limits_the_selected_chunks(self):
        source = write_document(self.root, "doc1", [
            {"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": "첫"},
            {"chunk_id": "doc1-c2", "page_no": 2, "start_pos": 1, "text": "둘"},
        ])
        run_batch(source, lambda _: "{}", self.output, resume=False, max_chunks=1)
        self.assertTrue((self.output / "doc1-c1.result.json").exists())
        self.assertFalse((self.output / "doc1-c2.result.json").exists())

    def test_max_chunks_counts_only_new_calls_when_resuming(self):
        source = write_document(self.root, "doc1", [
            {"chunk_id": f"doc1-c{i}", "page_no": i, "start_pos": 1, "text": f"혜택{i}"}
            for i in range(1, 4)
        ])
        self.output.mkdir()
        existing = {"doc_sha256": DOC_SHA256, "page_no": 1, "chunk_id": "doc1-c1",
                    "chunk_length": 3, "extraction": None, "failures": [], "notes": []}
        (self.output / "doc1-c1.result.json").write_text(json.dumps(existing), encoding="utf-8")
        called = []
        result = run_batch(source, lambda prompt: called.append(prompt) or "{}", self.output, max_chunks=1)
        self.assertEqual(len(called), 1)
        self.assertEqual(result["documents"][0]["summary"]["skipped"], 1)
        self.assertTrue((self.output / "doc1-c2.result.json").exists())
        self.assertFalse((self.output / "doc1-c3.result.json").exists())

    def test_corrupt_existing_result_is_retried_with_note(self):
        source = write_document(self.root, "doc1", [
            {"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": "혜택"},
        ])
        self.output.mkdir()
        (self.output / "doc1-c1.result.json").write_text("{깨짐", encoding="utf-8")
        called = []
        run_batch(source, lambda prompt: called.append(prompt) or valid_response("혜택"), self.output)
        saved = json.loads((self.output / "doc1-c1.result.json").read_text(encoding="utf-8"))
        self.assertEqual(len(called), 1)
        self.assertTrue(any("기존 결과를 읽지 못해 다시 처리" in note for note in saved["notes"]))

    def test_incomplete_existing_result_object_is_retried(self):
        source = write_document(self.root, "doc1", [
            {"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": "혜택"},
        ])
        self.output.mkdir()
        (self.output / "doc1-c1.result.json").write_text('{"chunk_id":"doc1-c1"}', encoding="utf-8")
        run_batch(source, lambda _: valid_response("혜택"), self.output)
        saved = json.loads((self.output / "doc1-c1.result.json").read_text(encoding="utf-8"))
        self.assertTrue(any("필수 필드가 없습니다" in note for note in saved["notes"]))

    def test_repository_output_directory_is_rejected(self):
        source = write_document(self.root, "doc1", [])
        repo_root = Path(__file__).resolve().parents[4]
        with self.assertRaises(ValueError):
            run_batch(source, lambda _: "{}", repo_root / "batch-output")
        self.assertFalse((repo_root / "batch-output").exists())

    def test_summary_counts_failures_quote_locations_and_long_chunks(self):
        long_text = "혜택" + "가" * 3999
        source = write_document(self.root, "doc1", [
            {"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": long_text},
            {"chunk_id": "doc1-c2", "page_no": 2, "start_pos": 1, "text": "다음"},
        ])

        def llm_call(prompt):
            if "다음" in prompt:
                raise ValueError("호출 실패")
            return valid_response("혜택")

        result = run_batch(source, llm_call, self.output, resume=False)
        summary = result["documents"][0]["summary"]
        self.assertEqual(summary["chunks"], 2)
        self.assertEqual((summary["succeeded"], summary["failed"], summary["skipped"]), (1, 1, 0))
        self.assertEqual(summary["failures_by_code"], {"llm_call_failure": 1})
        self.assertEqual(summary["quote_locations"], {"success": 1, "failure": 0, "ambiguous": 0})
        self.assertEqual(summary["over_4000"], 1)

    def test_ambiguous_quote_is_warning_and_hard_failures_remain_failures(self):
        source = write_document(self.root, "doc1", [
            {"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": "혜택 혜택"},
            {"chunk_id": "doc1-c2", "page_no": 2, "start_pos": 1, "text": "호출 오류"},
        ])
        def llm_call(prompt):
            if "호출 오류" in prompt:
                raise RuntimeError("호출 실패")
            return valid_response("혜택")
        run_batch(source, llm_call, self.output, resume=False)
        result_path = self.output / "doc1-c1.result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        result["failures"] = [{"code": "quote_location_ambiguous", "message": "중복", "path": "benefits[0].evidence[0]"}]
        result_path.write_text(json.dumps(result), encoding="utf-8")
        summary = summarize_batch([source], self.output)["documents"][0]["summary"]
        self.assertEqual((summary["succeeded"], summary["failed"], summary["with_warnings"]), (1, 1, 1))
        self.assertEqual(summary["warnings_by_code"], {"quote_location_ambiguous": 1})
        self.assertEqual(summary["failures_by_code"], {"llm_call_failure": 1, "quote_location_ambiguous": 1})

    def test_quote_location_only_failure_counts_as_failed_and_partial(self):
        summary = _summarize([
            {"chunk_length": 12, "extraction": {"benefits": [], "conditions": [], "limits": [],
             "targets": [], "relations": []},
             "failures": [{"code": "quote_location_failure"}]},
        ], skipped=0)
        self.assertEqual((summary["succeeded"], summary["failed"], summary["partial"]), (0, 1, 1))

    def test_summarize_batch_never_calls_llm(self):
        source = write_document(self.root, "doc1", [
            {"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1, "text": "혜택"},
        ])
        run_batch(source, lambda _: valid_response("혜택"), self.output)
        result = summarize_batch([source], self.output)
        self.assertEqual(result["documents"][0]["summary"]["succeeded"], 1)

    def test_ambiguous_quote_is_successful_extraction_but_requires_review(self):
        source = write_document(self.root, "doc1", [
            {"chunk_id": "doc1-c1", "page_no": 1, "start_pos": 1,
             "text": "식비 할인, 식비 할인"},
        ])

        result = run_batch(source, lambda _: valid_response("식비 할인"), self.output, resume=False)

        summary = result["documents"][0]["summary"]
        self.assertEqual((summary["succeeded"], summary["failed"], summary["review_required"]), (1, 0, 1))
        self.assertEqual(summary["quote_locations"], {"success": 0, "failure": 0, "ambiguous": 1})


if __name__ == "__main__":
    unittest.main()
