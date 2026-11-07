import json
from pathlib import Path

import pytest

from payment_card.file_pipeline.extraction.review.accuracy_review import auto_check, main, prepare, tally


def _inputs(tmp_path, lengths=(100, 1100, 2100, 4100)):
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    result_dir = tmp_path / "results"
    result_dir.mkdir()
    chunk_rows = []
    for index, length in enumerate(lengths):
        chunk_id = f"chunk-{index}"
        chunk_rows.append({"chunk_id": chunk_id, "text": "s" * length, "page_no": index + 1})
        result = {"chunk_id": chunk_id, "page_no": index + 1, "chunk_length": length,
                  "extraction": {"benefits": [{"name": "synthetic benefit", "rate": "10%", "method": "할인"}],
                                 "conditions": [], "limits": [], "targets": [], "relations": []}}
        (result_dir / f"{chunk_id}.result.json").write_text(json.dumps(result), encoding="utf-8")
    (chunks / "sample.chunks.json").write_text(json.dumps({"chunks": chunk_rows}), encoding="utf-8")
    return result_dir, chunks


def test_prepare_samples_reproducibly_by_length_bin_and_seed(tmp_path):
    results, chunks = _inputs(tmp_path, (100, 200, 300, 400, 1100, 1200, 1300, 1400,
                                          2100, 2200, 2300, 2400, 4100, 4200, 4300, 4400))
    first = prepare(results, chunks, tmp_path / "one", size=8, seed=41)
    again = prepare(results, chunks, tmp_path / "two", size=8, seed=41)
    changed = prepare(results, chunks, tmp_path / "three", size=8, seed=42)
    assert first["selected"] == again["selected"]
    assert first["selected"] != changed["selected"]
    assert first["bin_counts"] == {"<=999": 2, "1000-1999": 2, "2000-3999": 2, ">=4000": 2}


def test_prepare_handles_empty_bins_and_caps_to_population(tmp_path):
    results, chunks = _inputs(tmp_path, (100, 200, 300))
    prepared = prepare(results, chunks, tmp_path / "review", size=10, seed=1)
    assert len(prepared["selected"]) == 3
    assert prepared["bin_counts"] == {"<=999": 3, "1000-1999": 0, "2000-3999": 0, ">=4000": 0}


def test_prepare_rejects_repo_output_and_protects_existing_files(tmp_path):
    results, chunks = _inputs(tmp_path)
    with pytest.raises(ValueError, match="저장소 밖"):
        prepare(results, chunks, Path(__file__).parents[3] / "unsafe")
    output = tmp_path / "review"
    prepare(results, chunks, output)
    with pytest.raises(FileExistsError):
        prepare(results, chunks, output)
    stale = output / "accuracy_view" / "99_old.txt"
    stale.write_text("old", encoding="utf-8")
    prepare(results, chunks, output, overwrite=True)
    assert not stale.exists()


def test_prepare_sanitizes_chunk_id_in_view_filename(tmp_path):
    results, chunks = _inputs(tmp_path, (100,))
    result_path = results / "chunk-0.result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")); result["chunk_id"] = "a/../unsafe"
    result_path.unlink(); (results / "unsafe.result.json").write_text(json.dumps(result), encoding="utf-8")
    chunk_path = chunks / "sample.chunks.json"
    data = json.loads(chunk_path.read_text(encoding="utf-8")); data["chunks"][0]["chunk_id"] = "a/../unsafe"
    chunk_path.write_text(json.dumps(data), encoding="utf-8")
    prepared = prepare(results, chunks, tmp_path / "review")
    assert Path(prepared["views"][0]).name == "01_a____unsafe.txt"


def test_tally_reads_verdict_only_and_json_excludes_memo(tmp_path, capsys):
    sheet = tmp_path / "accuracy_verdicts.md"
    sheet.write_text("""| N | chunk_id | page | length | counts | view | verdict | memo |
|---|---|---|---|---|---|---|---|
| 1 | alpha-long-chunk-id | 3 | 4 | b1 | a.txt | [X] 맞음 [ ] 틀림 [ ] 일부 누락 | [x] 틀림 |
| 2 | beta | 5 | 4 | b1 | b.txt | [ x ] 틀림 [ ] 맞음 | note with [x] 일부 누락 |
| 3 | gamma | 6 | 4 | b1 | c.txt | [✓] 일부 누락 [ ] 맞음 | secret source wording |
| 4 | delta | 7 | 4 | b1 | d.txt | [v] 맞음 [x] 틀림 | memo |
| 5 | epsilon | 8 | 4 | b1 | e.txt | [ ] 맞음 [ ] 틀림 [ ] 일부 누락 | undecided |
""", encoding="utf-8")
    result = tally(sheet)
    assert result["counts"] == {"맞음": 1, "틀림": 1, "일부 누락": 1, "미판정": 1, "중복": 1}
    assert result["precision"] == 1 / 3
    assert result["wrong"] == [("beta", "5")]
    json_out = tmp_path / "decisions.json"
    main(["tally", "--sheet", str(sheet), "--json-out", str(json_out)])
    out = json_out.read_text(encoding="utf-8")
    assert "secret source wording" not in out and "memo" not in out and "beta" in out
    assert len(capsys.readouterr().out.splitlines()) == 3


def test_auto_check_empty_item_rules_and_source_value_matching():
    extraction = {
        "benefits": [{"name": "혜택"}, {"name": "", "rate": None, "method": None, "amount": None}],
        "conditions": [{"kind": "SPEND_REQ"}, {"kind": "OTHER", "text": "결제", "min_amount": None}],
        "limits": [{"text": "", "amount": None, "period": None, "unlimited": None},
                   {"text": "월 3만원", "amount": 30000, "period": "MONTH", "unlimited": False}],
        "targets": [{"kind": "OTHER", "text": ""}, {"kind": "MERCHANT", "name": "가맹점"}],
    }
    result = auto_check(extraction, "결제 시 월 30,000원 한도 가맹점")
    assert result["empty_items"] == {
        "groups": {"benefits": 1, "conditions": 1, "limits": 1, "targets": 1},
        "total": 4, "item_total": 8,
    }
    assert result["values_not_in_text"]["checked"] == 1
    assert result["values_not_in_text"]["found"] == 1
    assert result["values_not_in_text"]["missing"] == 0
    assert result["values_not_in_text"]["items"] == []
    assert result["candidate"] == "숫자 이상 없음"


@pytest.mark.parametrize(("value", "source"), [
    (400000, "지난달 40만원 이상"), ("40만원", "이용 기준 400,000원"),
    (15000, "1만5천원"), (100000, "10만 원"),
    (1, "직전 6개월 연속 1원 이상 이용"), (10000, "가족카드당 1만원 캐시백"),
    (30000, "월 30,000원"), (5, "5% 할인"), (0.5, "0.5% 적립"),
])
def test_auto_check_matches_numeric_values_and_korean_units(value, source):
    extraction = {"benefits": [], "conditions": [{"min_amount": value}],
                  "limits": [], "targets": []}
    report = auto_check(extraction, source)
    assert report["values_not_in_text"]["missing"] == 0


def test_auto_check_does_not_match_one_inside_ten_thousand():
    extraction = {"benefits": [], "conditions": [{"min_amount": 1}],
                  "limits": [], "targets": []}
    report = auto_check(extraction, "가족카드당 1만원 캐시백")
    assert report["values_not_in_text"]["missing"] == 1


def test_prepare_view_has_reading_guide_and_evidence_locations(tmp_path):
    results, chunks = _inputs(tmp_path, (100,))
    result_path = results / "chunk-0.result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["extraction"]["benefits"][0]["evidence"] = [{"text": "합성 근거 문장"}, {"text": "없는 근거"}]
    result["extraction"]["relations"] = [{"source": "b1", "type": "HAS_LIMIT", "target": "l1",
                                           "evidence": [{"text": "합성 근거 문장"}]}]
    result_path.write_text(json.dumps(result), encoding="utf-8")
    chunk_path = chunks / "sample.chunks.json"
    chunk_data = json.loads(chunk_path.read_text(encoding="utf-8"))
    chunk_data["chunks"][0]["text"] = "첫 줄\n합성 근거 문장\n끝"
    chunk_path.write_text(json.dumps(chunk_data), encoding="utf-8")
    view = Path(prepare(results, chunks, tmp_path / "review")["views"][0]).read_text(encoding="utf-8")
    assert "읽는 방법" in view
    assert "1 요약 읽기" in view and "5 판정표에 체크" in view
    assert "빈 항목은 틀림이 아닙니다" in view
    assert '근거(L2): "합성 근거 문장"' in view
    assert '근거(위치 못 찾음): "없는 근거"' in view


def test_prepare_tag_isolated_and_same_seed_preserves_sample(tmp_path):
    results, chunks = _inputs(tmp_path, (100, 200, 300, 400))
    first = prepare(results, chunks, tmp_path / "review", size=2, seed=9, tag="v2")
    same = prepare(results, chunks, tmp_path / "other", size=2, seed=9, tag="v2")
    assert first["selected"] == same["selected"]
    assert Path(first["sheet"]).name == "accuracy_verdicts_v2.md"
    assert Path(first["views"][0]).parent.name == "accuracy_view_v2"
    prepare(results, chunks, tmp_path / "review", size=2, seed=9)


def test_tag_cli_and_thirty_sample_reproducibility(tmp_path, capsys):
    results, chunks = _inputs(tmp_path, tuple(range(100, 140)))
    tagged = tmp_path / "tagged"
    assert main(["prepare", "--result-dir", str(results), "--chunk-dir", str(chunks),
                 "--output-dir", str(tagged), "--size", "30", "--seed", "20261104", "--tag", "v2"]) == 0
    first = json.loads(capsys.readouterr().out)["selected"]
    other = prepare(results, chunks, tmp_path / "other", size=30, seed=20261104)["selected"]
    assert [row["chunk_id"] for row in first] == [row["chunk_id"] for row in other]
    assert len(first) == 30


def test_tagged_and_legacy_tally_empty_ratio(tmp_path):
    for name, header in (("old.md", "| N | chunk_id | page | length | counts | view | verdict | memo |"),
                         ("new.md", "| 번호 | chunk_id | page | length | 항목수 | 빈 항목 | 미발견 값 | 자동 후보 | 열람 파일 | 판정 | 메모 |")):
        sheet = tmp_path / name
        row = ("| 1 | alpha | 2 | 40 | 1/0/0/0 | 1 | 0 | 숫자 이상 없음 | a.txt | "
               "[x] 맞음 [ ] 틀림 [ ] 일부 누락 | note |" if name == "new.md" else
               "| 1 | alpha | 2 | 40 | b1 | a.txt | [x] 맞음 [ ] 틀림 [ ] 일부 누락 | note |")
        sheet.write_text(f"{header}\n|---|---|---|---|---|---|---|---|\n{row}\n", encoding="utf-8")
        result = tally(sheet)
        assert result["precision"] == 1
        if name == "new.md":
            assert result["empty_items"] == {"empty": 1, "items": 1, "ratio": 1.0}
            assert result["report"][3] == "빈 항목: 1개 / 전체 항목 1개 (100.0%)"
        else:
            assert "empty_items" not in result
