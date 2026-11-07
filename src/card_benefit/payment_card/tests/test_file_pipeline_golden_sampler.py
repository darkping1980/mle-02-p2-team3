import csv
from pathlib import Path

import fitz
import pytest

from payment_card.file_pipeline.chat.eval import golden_sampler as sampler
from payment_card.file_pipeline.chat.eval.golden_set import convert


HEADERS = ["id", "issuer", "doc_id", "sha256", "file_path", "card_type", "doc_role",
           "canonical", "duplicate_of", "pages", "text_chars", "ocr_needed"]


def make_pdf(path: Path, page_texts: list[str]) -> None:
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def make_index(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def docrow(file: Path, *, sha: str, role: str, canonical="Y", ocr="N"):
    return {"id": sha, "issuer": "hana", "doc_id": "shared", "sha256": sha,
            "file_path": str(file), "card_type": "credit", "doc_role": role,
            "canonical": canonical, "duplicate_of": "", "pages": "3", "text_chars": "100",
            "ocr_needed": ocr}


@pytest.fixture
def fixture_data(tmp_path):
    a, b, scanned, duplicate = (tmp_path / n for n in ("a.pdf", "b.pdf", "ocr.pdf", "dup.pdf"))
    make_pdf(a, ["A" * 120, "B" * 120, "tiny"])
    make_pdf(b, ["C" * 120, "D" * 120])
    make_pdf(scanned, ["O" * 120])
    make_pdf(duplicate, ["X" * 120])
    index = tmp_path / "documents.csv"
    make_index(index, [docrow(a, sha="a", role="product_guide"),
                       docrow(b, sha="b", role="product_guide"),
                       docrow(scanned, sha="ocr", role="terms", ocr="Y"),
                       docrow(duplicate, sha="dup", role="terms", canonical="N")])
    return index


def run(index, count=3, seed=7, **kwargs):
    return sampler.sample({"hana": index}, count=count, seed=seed,
                          template_path=sampler.TEMPLATE, **kwargs)


def test_deterministic_and_seed_changes_pages(fixture_data):
    rows1, _ = run(fixture_data)
    rows2, _ = run(fixture_data)
    rows3, _ = run(fixture_data, seed=9)
    assert rows1 == rows2
    assert [(r["근거문서"], r["근거쪽"]) for r in rows1] != [(r["근거문서"], r["근거쪽"]) for r in rows3]


def test_strata_minimum_cap_short_pages_and_canonical_only(fixture_data):
    rows, summary = run(fixture_data, count=3)
    pages = [r for r in rows if r["정답없음"] == "아니오"]
    assert len(pages) == 3
    assert {r["근거문서"] for r in pages} == {"a.pdf", "b.pdf"}
    assert max(sum(r["근거문서"] == name for r in pages) for name in ("a.pdf", "b.pdf")) <= 2
    assert all(r["근거쪽"] != "3" for r in pages)
    assert all(r["근거문서"] != "dup.pdf" for r in pages)
    assert {r["doc_role"] for r in summary if r["pages"]} == {"product_guide"}
    assert all(r["excluded_short"] == 1 for r in summary)


def test_ocr_excluded_by_default_and_included_is_marked(fixture_data):
    rows, _ = run(fixture_data, count=3)
    assert all(r["근거문서"] != "ocr.pdf" for r in rows)
    rows, _ = run(fixture_data, count=3, include_ocr=True)
    assert any(r["근거문서"] == "ocr.pdf" and r["이미지문서유래"] == "예" for r in rows)


def test_slots_and_encoded_file_link(fixture_data):
    rows, _ = run(fixture_data, count=4)
    slots = [r for r in rows if r["정답없음"] == "예"]
    assert len(slots) == 1
    assert slots[0]["근거쪽"] == slots[0]["질문"] == ""
    assert "정답 없음 질문:" in slots[0]["비고"]
    regular = next(r for r in rows if r["정답없음"] == "아니오")
    encoded = sampler.pdf_link(Path("/tmp/안내 (샘플).pdf"), 2)
    assert "%EC" in encoded
    assert "%20%28" in encoded
    assert "(" not in encoded


def test_output_refuses_repo_and_csv_loads_but_converter_rejects_unwritten_draft(tmp_path):
    with pytest.raises(ValueError):
        sampler.safe_output(sampler.ROOT / "draft.csv")
    row = {h: "" for h in sampler.read_csv(sampler.TEMPLATE)[0]}
    row.update({"id": "G-H-001", "카드사": "하나", "근거문서": "a.pdf", "근거쪽": "1",
                "정답없음": "아니오", "이미지문서유래": "아니오"})
    path = tmp_path / "draft.csv"
    sampler.write_csv(path, [row])
    loaded = sampler.read_csv(path)
    assert loaded[0]["질문"] == ""
    # Empty question/type/facts are the normal pre-writing state; conversion is for completed rows.
    with pytest.raises(ValueError, match="유형 값이 허용 목록에 없음"):
        convert(path)


def test_sampler_source_does_not_open_extraction_artifacts():
    source = Path(sampler.__file__).read_text(encoding="utf-8")
    assert "graph" not in source.lower() or "문서가 있는 그래프" in source
    assert "chunks" not in source.lower()
    assert "extraction.json" not in source.lower()
