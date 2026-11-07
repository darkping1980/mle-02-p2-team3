import json
from pathlib import Path
import tempfile
import unittest

from payment_card.file_pipeline.extraction.review.review_sheet import generate_review_sheet


def fixture_result(chunk_id, length, extraction=None, failures=None):
    return {"chunk_id": chunk_id, "page_no": 2, "chunk_length": length,
            "extraction": extraction, "failures": failures or []}


class ReviewSheetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.results, self.chunks, self.out = (self.root / "results", self.root / "chunks", self.root / "out")
        self.results.mkdir(); self.chunks.mkdir(); self.out.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, chunk_id, result, text="prefix BENEFIT suffix", start=101):
        chunk = {"chunk_id": chunk_id, "page_no": 2, "start_pos": start, "end_pos": start + len(text) - 1, "text": text}
        (self.chunks / "doc.chunks.json").write_text(json.dumps({"doc_id": "doc", "chunks": [chunk]}), encoding="utf-8")
        (self.results / f"{chunk_id}.result.json").write_text(json.dumps(result), encoding="utf-8")

    @staticmethod
    def extraction(location=True):
        evidence = {"text": "BENEFIT"}
        if location:
            evidence["location"] = {"start_pos": 108, "end_pos": 114}
        return {"benefits": [{"id": "b1", "name": "혜택", "method": "DISCOUNT", "rate": "5%", "amount": None,
                              "evidence": [evidence]}], "conditions": [], "limits": [], "targets": [], "relations": []}

    def test_only_extraction_successes_selected(self):
        self.save("good", fixture_result("good", 12, self.extraction()))
        for bad, extraction in (("none", None), ("empty", {key: [] for key in ("benefits", "conditions", "limits", "targets", "relations")})):
            (self.results / f"{bad}.result.json").write_text(json.dumps(fixture_result(bad, 4, extraction)), encoding="utf-8")
        report = generate_review_sheet(self.results, self.chunks, self.out / "sheet.md", count=5)
        self.assertEqual(report["chunk_ids"], ["good"])

    def test_seed_reproducibility(self):
        for i in range(12):
            chunk_id = f"c{i}"
            self.save(chunk_id, fixture_result(chunk_id, i + 1, self.extraction()))
        first = generate_review_sheet(self.results, self.chunks, self.out / "a.md", count=5)
        second = generate_review_sheet(self.results, self.chunks, self.out / "b.md", count=5)
        self.assertEqual(first["chunk_ids"], second["chunk_ids"])

    def test_reject_repository_output(self):
        repo = Path(__file__).resolve().parents[4]
        with self.assertRaises(ValueError):
            generate_review_sheet(self.results, self.chunks, repo / "bad.md")

    def test_position_helper_uses_page_to_chunk_offset(self):
        self.save("located", fixture_result("located", 20, self.extraction()))
        path = self.out / "sheet.md"
        generate_review_sheet(self.results, self.chunks, path)
        self.assertIn("108~114", path.read_text(encoding="utf-8"))
        self.assertIn("BENEFIT", path.read_text(encoding="utf-8"))

    def test_missing_position_is_marked(self):
        self.save("missing", fixture_result("missing", 20, self.extraction(location=False)))
        path = self.out / "sheet.md"
        generate_review_sheet(self.results, self.chunks, path)
        self.assertIn("위치 없음", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
