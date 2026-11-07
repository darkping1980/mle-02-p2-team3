import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from payment_card.file_pipeline.extraction import ocr_pages


TSV = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n" \
      "5\t1\t1\t1\t1\t1\t0\t0\t5\t5\t91.5\t연회비\n" \
      "5\t1\t1\t1\t1\t2\t6\t0\t5\t5\t60\t10,000원\n"


def test_tsv_parsing_and_statistics():
    words = ocr_pages.parse_tsv(TSV)
    assert [word["text"] for word in words] == ["연회비", "10,000원"]
    stats = ocr_pages.page_statistics("연회비 10,000원", words)
    assert stats == {
        "word_count": 2, "char_count": 11, "hangul_count": 4, "digit_count": 5,
        "mean_confidence": 75.75, "low_confidence_ratio": 0.5,
    }


def test_low_word_page_is_retained_as_empty():
    page = ocr_pages.build_page_result(1, "한글 2", [{"text": "한글", "confidence": 90}, {"text": "2", "confidence": 80}])
    assert page["text"] == ""
    assert page["chunk_status"] == "NO_TEXT"
    assert page["quality"]["word_count"] == 2


def test_numeric_tokens_include_confidence_and_short_context():
    records = ocr_pages.extract_numeric_tokens("월 1회 10,000원, 5% 적립 3개월", [
        {"text": "1회", "confidence": 80}, {"text": "10,000원,", "confidence": 61},
        {"text": "5%", "confidence": 90}, {"text": "3개월", "confidence": 70},
    ], "doc-a", 2)
    assert [row["token"] for row in records] == ["1회", "10,000원", "5%", "3개월"]
    assert all(len(row["context"]) <= 40 for row in records)
    assert records[1]["confidence"] == 61


def test_sha_mismatch_and_repo_output_rejected(tmp_path):
    pdf = tmp_path / "fake.pdf"
    pdf.write_bytes(b"%PDF-synthetic")
    with pytest.raises(ValueError, match="SHA-256"):
        ocr_pages.create_ocr_trace(pdf, "wrong", run_tesseract=lambda *_: "")
    with pytest.raises(ValueError, match="저장소 안"):
        ocr_pages.ensure_external_output(Path(__file__).resolve().parents[1] / "output")


def test_dry_run_does_not_call_ocr(tmp_path):
    index = tmp_path / "documents.csv"
    index.write_text("doc_id,sha256,file_path,pages,canonical,ocr_needed\nd1,x,sample.pdf,1,Y,Y\n", encoding="utf-8")
    called = []
    result = ocr_pages.run_index(index, ["d1"], tmp_path / "out", data_root=tmp_path,
                                 execute=False, run_tesseract=lambda *args: called.append(args))
    assert result["planned"] == [{"doc_id": "d1", "pages": 1}]
    assert called == []


def test_trace_is_chunkable(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    pdf = tmp_path / "synthetic.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(pdf)
    document.close()
    chunk_tsv = TSV + "5\t1\t1\t1\t1\t3\t12\t0\t5\t5\t88\t합성\n"
    trace = ocr_pages.create_ocr_trace(pdf, hashlib.sha256(pdf.read_bytes()).hexdigest(),
                                       run_tesseract=lambda *_: chunk_tsv)
    row = {"doc_id": "d1", "sha256": trace["document"]["sha256"], "file_path": "synthetic.pdf"}
    from payment_card.file_pipeline.chunking.build import build_doc_chunks
    chunked = build_doc_chunks(row, trace, [], lambda *_: [])
    assert chunked["chunks"][0]["start_pos"] == 1
    assert chunked["chunks"][0]["end_pos"] == len(trace["pages"][0]["text"])


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract unavailable")
def test_real_tesseract_on_synthetic_pdf(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    pdf = tmp_path / "synthetic.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Synthetic 12345 90 percent", fontsize=24)
    document.save(pdf)
    document.close()
    result = ocr_pages.create_ocr_trace(pdf)
    assert result["pages"][0]["quality"]["word_count"] >= 3



def test_tsv_with_quote_characters_does_not_swallow_following_rows():
    """OCR 이 '"' 글자를 인식해도(따옴표 규칙 없음) 뒤의 행이 한 칸으로 합쳐져 쪽 텍스트에 좌표가 섞이면 안 된다(실제 발생한 버그)."""
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    rows = (
        "5\t1\t1\t1\t1\t1\t0\t0\t5\t5\t90\t\"혜택\n"      # 닫히지 않은 따옴표로 시작하는 단어
        "5\t1\t1\t1\t1\t2\t6\t0\t5\t5\t88\t연회비\n"
        "5\t1\t1\t1\t1\t3\t12\t0\t5\t5\t87\t\"\n"            # 따옴표 한 글자
        "5\t1\t1\t1\t1\t4\t18\t0\t5\t5\t86\t10,000원\n"
    )
    words = ocr_pages.parse_tsv(header + rows)
    assert [w["text"] for w in words] == ['"혜택', "연회비", '"', "10,000원"]
    text = " ".join(w["text"] for w in words)
    assert "\t" not in text and len(text) < 40
