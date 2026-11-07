import csv
import json
from pathlib import Path

import pytest


def _write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _graph(directory, sha):
    directory.mkdir()
    _write_csv(directory / "fp_nodes.csv", ["id", "node_type", "props", "chunk_id", "run_id"], [
        {"id": f"{sha[:16]}-p0001-c001:b", "node_type": "Benefit", "props": "{}", "chunk_id": "x", "run_id": "r"},
        {"id": f"{sha[:16]}-p0001-c001:c", "node_type": "Condition", "props": "{}", "chunk_id": "x", "run_id": "r"},
        {"id": f"{sha[:16]}-p0001-c001:l", "node_type": "Limit", "props": "{}", "chunk_id": "x", "run_id": "r"},
        {"id": f"{sha[:16]}-p0002-c001:t", "node_type": "Target", "props": "{}", "chunk_id": "x", "run_id": "r"},
        {"id": f"{sha[:16]}-p0001-c001:target-missing", "node_type": "Target", "props": "{}", "chunk_id": "x", "run_id": "r"},
        {"id": f"{sha[:16]}-p0001-c001:missing", "node_type": "Condition", "props": "{}", "chunk_id": "x", "run_id": "r"},
    ])
    _write_csv(directory / "fp_edges.csv", ["id", "source_id", "target_id", "edge_type", "run_id"], [
        {"id": "e1", "source_id": f"{sha[:16]}-p0001-c001:b", "target_id": f"{sha[:16]}-p0001-c001:c", "edge_type": "HAS_CONDITION", "run_id": "r"},
    ])
    _write_csv(directory / "fp_evidence.csv", ["node_id", "edge_id", "doc_sha256", "page_no", "start_pos", "end_pos", "quote_status"], [
        {"node_id": f"{sha[:16]}-p0001-c001:b", "edge_id": "", "doc_sha256": sha, "page_no": 1, "start_pos": 10, "end_pos": 20, "quote_status": "located"},
        {"node_id": f"{sha[:16]}-p0001-c001:c", "edge_id": "", "doc_sha256": sha, "page_no": 1, "start_pos": 20, "end_pos": 30, "quote_status": "located"},
        {"node_id": f"{sha[:16]}-p0001-c001:l", "edge_id": "", "doc_sha256": sha, "page_no": 1, "start_pos": 60, "end_pos": 70, "quote_status": "located"},
        {"node_id": f"{sha[:16]}-p0001-c001:missing", "edge_id": "", "doc_sha256": sha, "page_no": "", "start_pos": "", "end_pos": "", "quote_status": "missing"},
        {"node_id": f"{sha[:16]}-p0001-c001:target-missing", "edge_id": "", "doc_sha256": sha, "page_no": "", "start_pos": "", "end_pos": "", "quote_status": "missing"},
    ])


def _inputs(tmp_path):
    from payment_card.file_pipeline.extraction.eval.label_eval import evaluate

    data = tmp_path / "data"; (data / "pdf").mkdir(parents=True)
    pdf = data / "pdf" / "sample.pdf"; pdf.write_bytes(b"synthetic-pdf")
    (data / "pdf" / "other.pdf").write_bytes(b"other-synthetic-pdf")
    sha = __import__("hashlib").sha256(b"synthetic-pdf").hexdigest()
    _graph(tmp_path / "graph", sha)
    labels = tmp_path / "labels.csv"
    _write_csv(labels, ["id", "issuer", "pid", "kind", "text", "start", "end", "parent_id", "relation"], [
        {"id": "b", "issuer": "issuer", "pid": "p1", "kind": "Benefit", "text": "NEVER_READ", "start": 10, "end": 20, "parent_id": "", "relation": ""},
        {"id": "c", "issuer": "issuer", "pid": "p1", "kind": "Condition", "text": "NEVER_READ", "start": 26, "end": 35, "parent_id": "b", "relation": "HAS_CONDITION"},
        {"id": "one", "issuer": "issuer", "pid": "p1", "kind": "Condition", "text": "NEVER_READ", "start": 30, "end": 39, "parent_id": "", "relation": ""},
        {"id": "l", "issuer": "issuer", "pid": "p1", "kind": "Limit", "text": "NEVER_READ", "start": 80, "end": 90, "parent_id": "b", "relation": "HAS_LIMIT"},
        {"id": "t", "issuer": "issuer", "pid": "p1", "kind": "Target", "text": "NEVER_READ", "start": 1, "end": 3, "parent_id": "", "relation": ""},
        {"id": "n", "issuer": "issuer", "pid": "p3", "kind": "Target", "text": "NEVER_READ", "start": 1, "end": 3, "parent_id": "", "relation": ""},
        {"id": "d", "issuer": "issuer", "pid": "p2", "kind": "Benefit", "text": "NEVER_READ", "start": 1, "end": 2, "parent_id": "", "relation": ""},
    ])
    pool = tmp_path / "pool.json"
    pool.write_text(json.dumps([{"pid": "p1", "issuer": "issuer", "path": "pdf/sample.pdf", "page": 1, "text": "NEVER_READ"}, {"pid": "p2", "issuer": "issuer", "path": "pdf/other.pdf", "page": 1, "text": "NEVER_READ"}, {"pid": "p3", "issuer": "issuer", "path": "pdf/sample.pdf", "page": 3, "text": "NEVER_READ"}]), encoding="utf-8")
    return evaluate, labels, pool, data, tmp_path / "graph"


def test_evaluate_scores_hits_misses_relations_and_unlabeled_nodes(tmp_path, capsys):
    evaluate, labels, pool, data, graph = _inputs(tmp_path)
    summary = evaluate(labels, pool, [f"issuer={graph}"], data, tmp_path / "out", overlap="50")
    assert summary["labels"]["all"]["by_kind"]["Benefit"] == {"hits": 1, "total": 2, "recall": 0.5, "sample_note": "표본 부족"}
    assert summary["relations"]["all"]["by_type"]["HAS_CONDITION"]["hits"] == 1
    assert summary["unlabeled_nodes"]["Limit"] == 1
    reasons = {row["id"]: row["reason"] for row in csv.DictReader((tmp_path / "out" / "misses.csv").open(encoding="utf-8"))}
    assert reasons == {"one": "node_on_page_no_overlap", "l": "node_on_page_no_overlap", "t": "evidence_not_located", "n": "no_node_on_page", "d": "document_not_in_graph"}
    assert "정밀도 아님, 라벨 표본 한계" in capsys.readouterr().out


def test_overlap_accepts_one_character_and_fifty_percent_boundary(tmp_path):
    evaluate, labels, pool, data, graph = _inputs(tmp_path)
    any_summary = evaluate(labels, pool, [f"issuer={graph}"], data, tmp_path / "any", overlap="any")
    half_summary = evaluate(labels, pool, [f"issuer={graph}"], data, tmp_path / "half", overlap="50")
    assert any_summary["labels"]["all"]["by_kind"]["Condition"]["hits"] == 2
    assert half_summary["labels"]["all"]["by_kind"]["Condition"]["hits"] == 1


def test_evaluate_rejects_output_outside_tmp(tmp_path):
    evaluate, labels, pool, data, graph = _inputs(tmp_path)
    with pytest.raises(ValueError, match="/tmp"):
        evaluate(labels, pool, [f"issuer={graph}"], data, Path(__file__).parent / "unsafe")


def _evaluate_single_label(tmp_path, start, end, kind="Limit", near_chars=30):
    evaluate, labels, pool, data, graph = _inputs(tmp_path)
    _write_csv(labels, ["id", "issuer", "pid", "kind", "text", "start", "end", "parent_id", "relation"], [
        {"id": "miss", "issuer": "issuer", "pid": "p1", "kind": kind,
         "text": "SYNTHETIC", "start": start, "end": end, "parent_id": "", "relation": ""}
    ])
    summary = evaluate(labels, pool, [f"issuer={graph}"], data, tmp_path / "out", near_chars=near_chars)
    with (tmp_path / "out" / "misses.csv").open(encoding="utf-8") as stream:
        miss = next(csv.DictReader(stream))
    return summary, miss


def test_miss_analysis_classifies_boundary_gap_and_counts_near_hit(tmp_path):
    summary, miss = _evaluate_single_label(tmp_path, 81, 90)
    assert miss["detail"] == "boundary_near"
    assert miss["other_kind"] == ""
    assert miss["nearest_gap"] == ""
    assert summary["near_hits"]["Limit"] == 1
    assert summary["miss_detail_counts"]["boundary_near"]["Limit"] == 1
    assert "near는 hit으로 계산하지 않음" in summary["note"]


def test_miss_analysis_classifies_nearby_different_kind(tmp_path):
    summary, miss = _evaluate_single_label(tmp_path, 10, 20)
    assert miss["detail"] == "wrong_kind_nearby"
    assert miss["other_kind"] == "Benefit"
    assert miss["nearest_gap"] == ""
    assert summary["miss_detail_counts"]["wrong_kind_nearby"]["Limit"] == 1


def test_miss_analysis_classifies_true_missing_and_records_gap(tmp_path):
    summary, miss = _evaluate_single_label(tmp_path, 271, 280)
    assert miss["detail"] == "true_missing_candidate"
    assert miss["other_kind"] == ""
    assert miss["nearest_gap"] == "200"
    assert summary["miss_detail_counts"]["true_missing_candidate"]["Limit"] == 1


def test_near_threshold_changes_boundary_detail_without_changing_hit_judgement(tmp_path):
    summary_near, miss_near = _evaluate_single_label(tmp_path / "near", 81, 90, near_chars=10)
    summary_far, miss_far = _evaluate_single_label(tmp_path / "far", 81, 90, near_chars=9)
    assert miss_near["detail"] == "boundary_near"
    assert miss_far["detail"] == "true_missing_candidate"
    assert summary_near["labels"]["all"]["by_kind"]["Limit"]["hits"] == 0
    assert summary_far["labels"]["all"]["by_kind"]["Limit"]["hits"] == 0
