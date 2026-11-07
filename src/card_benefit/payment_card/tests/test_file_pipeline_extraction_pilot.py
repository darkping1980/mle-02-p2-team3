from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from payment_card.file_pipeline.extraction.pilot import estimate_prompt_size, select_pilot_chunks


class ExtractionPilotTest(unittest.TestCase):
    def test_selection_is_seeded_spread_and_excludes_ocr_docs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index = root / "documents.csv"
            fields = ["issuer", "doc_id", "canonical", "doc_role", "ocr_needed", "card_type"]
            with index.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=fields)
                writer.writeheader()
                writer.writerows([
                    {"issuer": "hana", "doc_id": "a", "canonical": "Y", "doc_role": "product_guide", "ocr_needed": "N", "card_type": "credit"},
                    {"issuer": "hana", "doc_id": "b", "canonical": "Y", "doc_role": "product_guide", "ocr_needed": "Y", "card_type": "credit"},
                ])
            chunks = root / "chunks"
            chunks.mkdir()
            for doc_id, content in {
                "a": [{"chunk_id": "a1", "text": "짧은 혜택"},
                      {"chunk_id": "a2", "text": "택1" + " 설명" * 300},
                      {"chunk_id": "a3", "text": "|월|한도|" + " 할인" * 1200}],
                "b": [{"chunk_id": "b1", "text": "OCR에서 제외되어야 함"}],
            }.items():
                (chunks / f"{doc_id}.chunks.json").write_text(json.dumps({"chunks": content}), encoding="utf-8")
            first = select_pilot_chunks(index, chunks, 3, seed=5)
            self.assertEqual(first, select_pilot_chunks(index, chunks, 3, seed=5))
            self.assertEqual(len(first), 3)
            self.assertNotIn("b1", first)
            self.assertIn("a2", first)

    def test_estimate_counts_built_prompt_and_coarse_tokens(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            chunk = {"chunk_id": "c1", "page_no": 1, "start_pos": 1, "text": "할인"}
            (folder / "d.chunks.json").write_text(json.dumps({"chunks": [chunk]}), encoding="utf-8")
            result = estimate_prompt_size(["c1"], folder)
            self.assertEqual(result["chunks"], 1)
            self.assertGreater(result["prompt_characters"], len("할인"))
            self.assertEqual(result["estimated_tokens"], (result["prompt_characters"] + 1) // 2)


if __name__ == "__main__":
    unittest.main()
