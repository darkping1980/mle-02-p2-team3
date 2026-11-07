import json

from payment_card.file_pipeline.extraction.result_a import export_result_a


def test_result_a_separates_unlocated_rows_and_omits_quotes(tmp_path):
    chunks, results, output = (tmp_path / name for name in ("chunks", "results", "out"))
    chunks.mkdir(); results.mkdir()
    (chunks / "doc.chunks.json").write_text(json.dumps({"doc_sha256": "a" * 64, "chunks": [{"chunk_id": "c1", "page_no": 2}]}))
    (results / "c1.result.json").write_text(json.dumps({"chunk_id": "c1", "extraction": {
        "benefits": [{"id": "b1", "name": "n", "evidence": [{"text": "must not leak", "location": {"doc_sha256": "a" * 64, "page_no": 2, "start_pos": 3, "end_pos": 5}}, {"text": "private", "location": None}]}],
        "conditions": [], "limits": [], "targets": [], "relations": []},
        "failures": [{"code": "quote_location_ambiguous", "path": "benefits[0].evidence[1]"}]}))
    assert export_result_a(results, chunks, output) == {"rows": 2, "located": 1, "ambiguous": 1, "missing": 0, "unlocated_file_rows": 1}
    located = (output / "result_a.jsonl").read_text()
    ambiguous = (output / "result_a_unlocated.jsonl").read_text()
    assert "must not leak" not in located + ambiguous and "private" not in located + ambiguous
    assert json.loads(ambiguous)["quote_status"] == "ambiguous"
