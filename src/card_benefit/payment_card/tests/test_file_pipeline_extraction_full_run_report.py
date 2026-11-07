import json
from pathlib import Path

from card_benefit.payment_card.file_pipeline.extraction.report.full_run_report import build_report


def test_build_report_aggregates_without_serializing_source_text(tmp_path: Path):
    result_dir = tmp_path / "results"
    chunk_dir = tmp_path / "chunks"
    output_dir = tmp_path / "reports"
    result_dir.mkdir()
    chunk_dir.mkdir()
    chunks = [
        {"chunk_id": "c1", "text": "혜택 안내 문장으로만 구성된 길고 설명적인 문단을 반복해 표 밀도 점수를 낮춥니다.\n" * 5, "start_pos": 0},
        {"chunk_id": "c2", "text": ("민감원문 1  2  3  4\n" * 1500), "start_pos": 1},
        {"chunk_id": "c3", "text": "실적 30만원 이상", "start_pos": 2},
    ]
    (chunk_dir / "doc.chunks.json").write_text(json.dumps({"chunks": chunks}), encoding="utf-8")
    success = {
        "chunk_id": "c1", "failures": [],
        "extraction": {
            "benefits": [{"id": "b1", "evidence": [{"text": "할인 5%", "location": {"page": 1}}], "rate": "5%"}],
            "conditions": [], "limits": [], "targets": [],
            "relations": [{"evidence": [{"text": "할인 5%", "location": None}]}],
        },
    }
    empty = {"chunk_id": "c2", "failures": [{"code": "empty_result"}],
             "extraction": {"benefits": [], "conditions": [], "limits": [], "targets": [], "relations": []}}
    partial = {"chunk_id": "c3", "failures": [{"code": "quote_location_ambiguous", "path": "conditions[0].evidence[0]"}],
               "extraction": {"benefits": [], "conditions": [{"id": "cond1", "evidence": [{"text": "실적 30만원 이상", "location": None}]}], "limits": [], "targets": [], "relations": []}}
    failed = {"chunk_id": "c4", "failures": [{
        "code": "schema_validation_failure",
        "message": "1 validation error for Extraction\nbenefits.0.method\n  Input should be 'DISCOUNT', 'CASHBACK', 'POINT'",
    }], "extraction": None}
    for i, row in enumerate((success, empty, partial, failed)):
        (result_dir / f"{i}.result.json").write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")

    report = build_report(result_dir, chunk_dir, output_dir)
    serialized = json.dumps(report, ensure_ascii=False)
    assert report["chunks"] == 4
    assert report["success_chunks"] == 3
    assert report["failure_chunks"] == 1
    assert report["empty_chunks"] == 1
    assert report["partial_chunks"] == 1
    assert report["failures_by_code"]["empty_result"] == 1
    assert report["location_evidence"]["success"] == 1
    assert report["location_evidence"]["ambiguous"] == 2
    assert report["schema_violations"]["by_path"]["benefits[0].method"] == 1
    assert report["schema_violations"]["enum_names"] == {"CASHBACK": 1, "DISCOUNT": 1, "POINT": 1}
    assert report["groups"]["benefits"]["items"] == 1
    assert report["groups"]["benefits"]["evidence"] == 1
    assert report["long_chunks"]["count"] == 1
    assert report["empty_high_density_chunk_ids"] == ["c2"]
    assert "민감원문" not in serialized
    assert "할인 5%" not in serialized
    assert (output_dir / "full_run_report.json").exists()


def test_cli_writes_json_outside_repository(tmp_path: Path):
    from card_benefit.payment_card.file_pipeline.extraction.report.full_run_report import main

    result_dir = tmp_path / "results"
    chunk_dir = tmp_path / "chunks"
    result_dir.mkdir()
    chunk_dir.mkdir()
    (result_dir / "one.result.json").write_text(json.dumps({"chunk_id": "x", "extraction": None, "failures": []}), encoding="utf-8")
    destination = tmp_path / "report.json"
    assert main(["--result-dir", str(result_dir), "--chunk-dir", str(chunk_dir), "--output-json", str(destination)]) == 0
    assert json.loads(destination.read_text(encoding="utf-8"))["chunks"] == 1
