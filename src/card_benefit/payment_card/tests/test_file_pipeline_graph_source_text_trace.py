import csv
import hashlib
import json

import fitz

from payment_card.file_pipeline.graph import source_text
from payment_card.file_pipeline.graph.export import CSV_COLUMNS


def make_case(tmp_path, pdf_text, trace_text):
    csv_dir = tmp_path / "csv"
    csv_dir.mkdir(parents=True)
    pdf_path = tmp_path / "synthetic.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    if pdf_text:
        page.insert_text((72, 72), pdf_text)
    pdf.save(pdf_path)
    pdf.close()

    sha = hashlib.sha256(b"synthetic document").hexdigest()
    documents = tmp_path / "documents.csv"
    with documents.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["sha256", "file_path", "canonical"])
        writer.writeheader()
        writer.writerow({"sha256": sha, "file_path": str(pdf_path), "canonical": "Y"})

    tables = {
        "fp_nodes": [{"id": "b", "node_type": "Benefit", "props": "{}", "chunk_id": "c", "run_id": "r"}],
        "fp_edges": [],
        "fp_evidence": [{"node_id": "b", "edge_id": "", "doc_sha256": sha, "page_no": "1", "start_pos": "1", "end_pos": "8", "quote_status": "located"}],
        "fp_load_runs": [{"run_id": "r", "input_folder_name": "synthetic", "model_name": "", "started_at": "", "node_count": "1", "edge_count": "0"}],
    }
    for table, rows in tables.items():
        with (csv_dir / f"{table}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS[table])
            writer.writeheader()
            writer.writerows(rows)

    trace_dir = tmp_path / "trace"
    trace_issuer = trace_dir / "issuer"
    trace_issuer.mkdir(parents=True)
    if trace_text is not None:
        (trace_issuer / "doc-id.json").write_text(json.dumps({
            "document": {"sha256": sha},
            "pages": [] if trace_text == "__missing_page__" else [{"page_no": 1, "text": trace_text}],
        }), encoding="utf-8")
    return csv_dir, documents, trace_dir


def read_benefit(out):
    nodes = source_text.read_csv(out / "fp_nodes.csv")
    return json.loads(next(row for row in nodes if row["id"] == "b")["props"])


def test_trace_fallback_and_default_pdf_behavior(tmp_path):
    text = "Synthetic benefit text"

    csv_dir, documents, trace_dir = make_case(tmp_path / "default", "", text)
    default_out = tmp_path / "default-out"
    default_report = source_text.build(csv_dir, "issuer", documents, default_out)
    assert default_report["attached"] == 0
    assert default_report["unattached_by_reason"] == {"pdf_unreadable": 1}

    csv_dir, documents, trace_dir = make_case(tmp_path / "empty", "", text)
    trace_out = tmp_path / "trace-out"
    trace_report = source_text.build(csv_dir, "issuer", documents, trace_out, trace_dir=trace_dir)
    assert trace_report["attached"] == 1
    assert trace_report["source_counts"] == {"pdf": 0, "trace": 1, "unattached": {}}
    assert "(p.1)" in read_benefit(trace_out)["source_text"]
    assert text in read_benefit(trace_out)["source_text"]

    csv_dir, documents, trace_dir = make_case(tmp_path / "normal", text, text + "\n")
    normal_out = tmp_path / "normal-out"
    normal_report = source_text.build(csv_dir, "issuer", documents, normal_out, trace_dir=trace_dir)
    assert normal_report["source_counts"]["pdf"] == 1
    assert normal_report["source_counts"]["trace"] == 0
    assert text in read_benefit(normal_out)["source_text"]


def test_missing_trace_page_reports_pdf_unreadable(tmp_path):
    csv_dir, documents, trace_dir = make_case(tmp_path, "", "__missing_page__")
    out = tmp_path / "out"
    report = source_text.build(csv_dir, "issuer", documents, out, trace_dir=trace_dir)
    assert report["attached"] == 0
    assert report["source_counts"] == {"pdf": 0, "trace": 0, "unattached": {"pdf_unreadable": 1}}
