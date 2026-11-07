import csv
import json

import pytest

from payment_card.file_pipeline.extraction import ocr_review_sheet as review


def _inputs(tmp_path, monkeypatch, text="연회비 10,000원 5% 3개월 <script>alert(1)</script>"):
    pymupdf = pytest.importorskip("pymupdf")
    pdf = tmp_path / "한글 (문서).pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "synthetic")
    doc.new_page().insert_text((50, 100), "second page")
    doc.save(pdf)
    doc.close()
    ocr_dir = tmp_path / "ocr"
    ocr_dir.mkdir()
    doc_id = "d1"
    (ocr_dir / f"{doc_id}.json").write_text(json.dumps({"pages": [
        {"page_no": 1, "text": text}, {"page_no": 2, "text": "월 2회"}
    ]}), encoding="utf-8")
    (ocr_dir / f"{doc_id}.ocr.json").write_text(json.dumps({"pages": [
        {"page_no": 1, "mean_confidence": 72, "words": [
            {"text": "연회비", "confidence": 99}, {"text": "10,000원", "confidence": 40},
            {"text": "5%", "confidence": 60}, {"text": "3개월", "confidence": 90},
        ]}, {"page_no": 2, "mean_confidence": 30, "words": [
            {"text": "월", "confidence": 80}, {"text": "2회", "confidence": 20}
        ]}
    ]}), encoding="utf-8")
    tsv = ocr_dir / "numeric_tokens.csv"
    with tsv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["doc_id", "page_no", "token", "confidence", "context", "low_confidence_rank"])
        w.writeheader()
        w.writerow({"doc_id": doc_id, "page_no": 1, "token": "10,000원", "confidence": 40, "context": text[:30]})
    index = tmp_path / "docs.csv"
    index.write_text("doc_id,file_path,doc_role,pages\nd1,한글 (문서).pdf,terms,2\n", encoding="utf-8")
    monkeypatch.setattr(review, "REPO_ROOT", tmp_path / "not-repo")
    return ocr_dir, index, tmp_path


def test_html_tiers_escaping_mapping_priority_and_encoded_pdf_link(tmp_path, monkeypatch):
    ocr_dir, index, root = _inputs(tmp_path, monkeypatch)
    out = review.generate_review_html(ocr_dir, index, root, tmp_path / "out.html", priority=None)
    html = out.read_text(encoding="utf-8")
    assert "data-tier=\"red\"" in html
    assert "data-tier=\"yellow\"" in html
    assert "data-tier=\"green\"" in html
    assert 'data-conf="40.00"' in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert "file:///" in html and "%ED%95%9C%EA%B8%80%20%28%EB%AC%B8%EC%84%9C%29.pdf#page=1" in html
    assert 'data-page="2"' in html
    priority = review.generate_review_html(ocr_dir, index, root, tmp_path / "priority.html", priority=1)
    assert 'data-page="1"' in priority.read_text(encoding="utf-8")
    assert 'data-page="2"' not in priority.read_text(encoding="utf-8")


def test_size_cap_and_repo_output_rejection(tmp_path, monkeypatch):
    ocr_dir, index, root = _inputs(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="용량"):
        review.generate_review_html(ocr_dir, index, root, tmp_path / "large.html", max_size_bytes=10)
    monkeypatch.setattr(review, "REPO_ROOT", tmp_path.resolve())
    with pytest.raises(ValueError, match="저장소"):
        review.generate_review_html(ocr_dir, index, root, tmp_path / "inside.html")
