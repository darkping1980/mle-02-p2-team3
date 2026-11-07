from __future__ import annotations

import csv
import json
from pathlib import Path

import pymupdf

from payment_card.file_pipeline.chunking.cli import main, run


def make_inputs(root: Path) -> tuple[Path, Path, Path]:
    data_root = root / "data"
    index_dir = root / "index"
    trace_dir = root / "trace"
    issuer = "hana"
    issuer_index = index_dir / issuer
    (data_root / "docs").mkdir(parents=True)
    issuer_index.mkdir(parents=True)
    (trace_dir / issuer).mkdir(parents=True)

    fields = ["doc_id", "sha256", "file_path", "canonical", "doc_role", "card_type", "ocr_needed"]
    rows = [
        {"doc_id": "plain", "sha256": "plain-hash", "file_path": "docs/plain.pdf", "canonical": "Y",
         "doc_role": "product_guide", "card_type": "credit", "ocr_needed": "N"},
        {"doc_id": "ocr", "sha256": "ocr-hash", "file_path": "docs/ocr.pdf", "canonical": "Y",
         "doc_role": "product_guide", "card_type": "credit", "ocr_needed": "Y"},
    ]
    with (issuer_index / "documents.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with (issuer_index / "product_docs.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["doc_id", "product_name", "product_ids"])
        writer.writeheader()
        writer.writerow({"doc_id": "ocr", "product_name": "Synthetic", "product_ids": '{"product_code":"x1"}'})

    for row in rows:
        pdf = pymupdf.open()
        page = pdf.new_page(width=100, height=100)
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4), 0)
        pixmap.clear_with(255)
        page.insert_image(page.rect, stream=pixmap.tobytes("png"))  # image-only PDF, no text layer
        pdf.save(data_root / row["file_path"])
        pdf.close()
        trace = {
            "document": {"sha256": row["sha256"]},
            "pages": [{"page_no": 1, "text": f"synthetic {row['doc_id']} page\n"}],
        }
        (trace_dir / issuer / f"{row['doc_id']}.json").write_text(
            json.dumps(trace), encoding="utf-8"
        )
    return data_root, index_dir, trace_dir


def test_default_run_skips_ocr_documents_and_keeps_existing_args_compatible(tmp_path: Path) -> None:
    data_root, index_dir, trace_dir = make_inputs(tmp_path)

    summary = run("hana", data_root, index_dir, trace_dir, tmp_path / "out-default", False)

    assert [item["file_path"] for item in summary["done"]] == ["docs/plain.pdf"]
    assert summary["skipped"] == [{"file_path": "docs/ocr.pdf", "reason": "OCR 필요(이미지 PDF)"}]
    assert summary["included_ocr"] == 0
    assert not (tmp_path / "out-default" / "hana" / "ocr.chunks.json").exists()


def test_include_ocr_chunks_ocr_traceability_json(tmp_path: Path) -> None:
    data_root, index_dir, trace_dir = make_inputs(tmp_path)
    output_dir = tmp_path / "out-ocr"

    summary = run("hana", data_root, index_dir, trace_dir, output_dir, False, include_ocr=True)

    chunk_path = output_dir / "hana" / "ocr.chunks.json"
    chunk_result = json.loads(chunk_path.read_text(encoding="utf-8"))
    assert {item["file_path"] for item in summary["done"]} == {"docs/plain.pdf", "docs/ocr.pdf"}
    assert summary["skipped"] == []
    assert summary["included_ocr"] == 1
    assert chunk_result["doc_id"] == "ocr"
    assert chunk_result["chunks"][0]["text"] == "synthetic ocr page\n"


def test_cli_summary_reports_ocr_counts(tmp_path: Path, monkeypatch, capsys) -> None:
    data_root, index_dir, trace_dir = make_inputs(tmp_path)
    monkeypatch.setattr("sys.argv", [
        "chunking", "--issuer", "hana", "--trace-dir", str(trace_dir),
        "--output-dir", str(tmp_path / "out"), "--data-root", str(data_root),
        "--index-dir", str(index_dir), "--include-ocr",
    ])

    assert main() == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["skipped_ocr"] == 0
    assert summary["included_ocr"] == 1
