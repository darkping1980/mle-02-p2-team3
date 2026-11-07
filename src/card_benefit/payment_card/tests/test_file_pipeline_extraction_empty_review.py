import json
from pathlib import Path

import pytest

from payment_card.file_pipeline.extraction.review.empty_review import main, prepare, tally


def _inputs(tmp_path):
    chunks = tmp_path / "chunks"; chunks.mkdir()
    chunk_rows = [
        {"chunk_id": "b", "text": "할인 10%", "page_no": 2},
        {"chunk_id": "a", "text": "원 적립", "page_no": 1},
        {"chunk_id": "c", "text": "면제 포인트 캐시백", "page_no": 3},
    ]
    (chunks / "sample.chunks.json").write_text(json.dumps({"chunks": chunk_rows}), encoding="utf-8")
    dirs = []
    for name, ids in (("a", {"a", "b", "c"}), ("b", {"a", "b"})):
        directory = tmp_path / name; directory.mkdir(); dirs.append(directory)
        for row in chunk_rows:
            (directory / f"{row['chunk_id']}.result.json").write_text(json.dumps({
                "chunk_id": row["chunk_id"], "page_no": row["page_no"],
                "extraction": {"benefits": []} if row["chunk_id"] in ids else {"benefits": [{"name": "synthetic"}]},
            }), encoding="utf-8")
    return dirs[0], dirs[1], chunks


def test_prepare_intersects_empty_runs_sorts_signal_count_and_ties(tmp_path):
    a, b, chunks = _inputs(tmp_path)
    output = tmp_path / "review"
    result = prepare(a, b, chunks, output, top=2)
    assert result["selected"] == [{"chunk_id": "a", "signals": 2}, {"chunk_id": "b", "signals": 2}]
    assert "원 적립" not in (output / "empty_verdicts.md").read_text(encoding="utf-8")
    assert "원 적립" in Path(result["views"][0]).read_text(encoding="utf-8")


def test_prepare_refuses_repository_output(tmp_path):
    a, b, chunks = _inputs(tmp_path)
    with pytest.raises(ValueError, match="저장소 밖"):
        prepare(a, b, chunks, Path(__file__).parents[3] / "unsafe")


def test_prepare_protects_existing_sheet(tmp_path):
    a, b, chunks = _inputs(tmp_path)
    output = tmp_path / "review"
    prepare(a, b, chunks, output)
    with pytest.raises(FileExistsError):
        prepare(a, b, chunks, output)


def test_tally_counts_single_duplicate_unmarked_and_json_is_source_free(tmp_path):
    sheet = tmp_path / "sheet.md"
    sheet.write_text("""| N | chunk_id | length | density | signals | page | file | verdict | memo |
|---|---|---|---|---|---|---|---|---|
| 1 | alpha-long-id-12345 | 4 | low | 2 | 1 | a.txt | [x] 정상 [ ] 놓침 [ ] 애매 | note |
| 2 | beta | 4 | low | 1 | 2 | b.txt | [x] 놓침 [x] 애매 [ ] 정상 | source body secret |
| 3 | gamma | 4 | low | 0 | 3 | c.txt | [ ] 정상 [ ] 놓침 [ ] 애매 | memo |
""", encoding="utf-8")
    result = tally(sheet)
    assert result["counts"]["정상"] == 1
    assert result["counts"]["중복"] == 1
    assert result["counts"]["미판정"] == 1
    json_out = tmp_path / "out.json"
    assert main(["tally", "--sheet", str(sheet), "--json-out", str(json_out)]) == 0
    assert "source body secret" not in json_out.read_text(encoding="utf-8")
    assert "memo" not in json_out.read_text(encoding="utf-8")


def test_prepare_protects_existing_views_even_without_sheet(tmp_path):
    a, b, chunks = _inputs(tmp_path)
    output = tmp_path / "review"
    view_dir = output / "empty_view"
    view_dir.mkdir(parents=True)
    protected = view_dir / "01_keep.txt"
    protected.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        prepare(a, b, chunks, output)
    assert protected.read_text(encoding="utf-8") == "keep"
    prepare(a, b, chunks, output, overwrite=True)
    assert not protected.exists()


def test_tally_ignores_header_text_and_memo_marks_and_counts_judged_rows(tmp_path):
    sheet = tmp_path / "sheet.md"
    sheet.write_text("""| label | chunk_id | length | density | signals | page | file | verdict | memo |
|---|---|---|---|---|---|---|---|---|
| 1 | alpha | 4 | low | 2 | 1 | a.txt | [✓] 정상 [ ] 놓침 [ ] 애매 | [x] 놓침 |
| 2 | beta | 4 | low | 1 | 2 | b.txt | [ x ] 놓침 [ ] 정상 [ ] 애매 | note |
""", encoding="utf-8")
    result = tally(sheet)
    assert result["counts"]["정상"] == 1
    assert result["counts"]["놓침"] == 1
    assert result["report"][0].startswith("2개 중:")


def test_prepare_sanitizes_chunk_id_in_view_filename(tmp_path):
    a, b, chunks = _inputs(tmp_path)
    for directory in (a, b):
        source = directory / "a.result.json"
        row = json.loads(source.read_text(encoding="utf-8")); row["chunk_id"] = "a/../unsafe"
        source.unlink()
        (directory / "unsafe.result.json").write_text(json.dumps(row), encoding="utf-8")
    chunk_path = chunks / "sample.chunks.json"
    chunk_data = json.loads(chunk_path.read_text(encoding="utf-8")); chunk_data["chunks"][1]["chunk_id"] = "a/../unsafe"
    chunk_path.write_text(json.dumps(chunk_data), encoding="utf-8")
    result = prepare(a, b, chunks, tmp_path / "safe")
    assert Path(result["views"][0]).name == "01_a____unsafe.txt"
