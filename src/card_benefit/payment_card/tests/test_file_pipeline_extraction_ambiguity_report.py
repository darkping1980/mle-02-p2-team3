from __future__ import annotations

import json

from payment_card.file_pipeline.extraction.report.ambiguity_report import ambiguity_report


def test_ambiguity_report_counts_metadata_and_omits_quote_text(tmp_path):
    results = tmp_path / "results"
    chunks = tmp_path / "chunks"
    output = tmp_path / "report"
    results.mkdir()
    chunks.mkdir()
    (chunks / "doc.chunks.json").write_text(json.dumps({"chunks": [{
        "chunk_id": "chunk-1", "start_pos": 1,
        "text": "식비 5% 할인 적용. 식비 5% 할인 적용.",
    }]}), encoding="utf-8")
    (results / "chunk-1.result.json").write_text(json.dumps({
        "chunk_id": "chunk-1",
        "extraction": {"benefits": [
            {"evidence": [{"text": "식비 5% 할인 적용"}]},
            {"evidence": [{"text": "식비 5% 할인 적용"}]},
        ]},
        "failures": [{"code": "quote_location_ambiguous", "path": "benefits[0].evidence[0]"}],
    }), encoding="utf-8")

    summary = ambiguity_report(results, chunks, output)
    assert summary["count"] == 1
    assert summary["by_section"]["benefits"] == 1
    assert summary["by_length_bucket"]["11-20"] == 1
    assert summary["by_occurrence_count"] == {2: 1}
    row = json.loads((output / "ambiguity_report.json").read_text(encoding="utf-8"))[0]
    assert row == {
        "chunk_id": "chunk-1", "item_path": "benefits[0].evidence[0]", "length": 11,
        "occurrence_count": 2, "section": "benefits", "reused_by_other_item": True,
    }
    serialized = json.dumps(row, ensure_ascii=False)
    assert "식비" not in serialized
    assert set(row) == {"chunk_id", "item_path", "length", "occurrence_count", "section", "reused_by_other_item"}


def test_ambiguity_report_handles_empty_ambiguous_set(tmp_path):
    results = tmp_path / "results"
    chunks = tmp_path / "chunks"
    results.mkdir()
    chunks.mkdir()
    summary = ambiguity_report(results, chunks, tmp_path / "out")
    assert summary["count"] == 0
    assert summary["by_occurrence_count"] == {}
