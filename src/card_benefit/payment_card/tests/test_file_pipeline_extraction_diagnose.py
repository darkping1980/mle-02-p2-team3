from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from payment_card.file_pipeline.extraction.diagnose import diagnose_empty_results


class ExtractionDiagnoseTest(unittest.TestCase):
    def test_empty_chunks_are_classified_without_writing_raw_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chunks = root / "chunks"
            results = root / "results"
            output = root / "diagnosis"
            chunks.mkdir()
            results.mkdir()
            raw = "비밀 원문 할인 5%"
            (chunks / "doc.chunks.json").write_text(json.dumps({"chunks": [
                {"chunk_id": "c1", "text": raw, "title": "혜택 안내"},
                {"chunk_id": "c2", "text": "다른 청크"},
            ]}, ensure_ascii=False), encoding="utf-8")
            (results / "c1.result.json").write_text(json.dumps({
                "chunk_id": "c1", "failures": [{"code": "empty_result"}], "extraction": {},
            }), encoding="utf-8")
            (results / "c2.result.json").write_text(json.dumps({
                "chunk_id": "c2", "failures": [], "extraction": {"benefits": [{}]},
            }), encoding="utf-8")

            result = diagnose_empty_results(results, chunks, output)
            saved = (output / "empty_result_diagnosis.json").read_text(encoding="utf-8")
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["items"][0]["title"], "혜택 안내")
            self.assertEqual(result["items"][0]["length"], len(raw))
            self.assertEqual(result["items"][0]["keyword_counts"]["할인"], 1)
            self.assertNotIn(raw, saved)


if __name__ == "__main__":
    unittest.main()
