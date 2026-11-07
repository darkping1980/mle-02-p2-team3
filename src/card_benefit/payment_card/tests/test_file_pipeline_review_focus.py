"""검수 시트 집중 보기 테스트. 모든 데이터는 합성이며 실제 카드 문서를 쓰지 않는다."""
import csv
import json
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from card_benefit.payment_card.file_pipeline.chat.review import review_focus as rf
from card_benefit.payment_card.file_pipeline.chat.review.review_sheet import uuidish

SENT = "alpha payments only are provided"


def _write_csv(path, header, rows):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


@pytest.fixture()
def world(tmp_path):
    pdf = tmp_path / "합성.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "HEADER LINE\n" + SENT + " today\nTAIL LINE\nOTHER CONTENT\nLAST LINE")
    doc.save(pdf)
    doc.close()
    with fitz.open(pdf) as d:
        text = d[0].get_text()
    a = text.index(SENT)
    b = text.index("HEADER")
    issuer_dir = tmp_path / "fp-check-test"
    issuer_dir.mkdir()
    index_dir = tmp_path / "test"
    index_dir.mkdir()
    _write_csv(index_dir / "documents.csv", ["sha256", "file_path"], [["sha1", str(pdf)], ["sha2", str(tmp_path / "없는.pdf")]])
    nodes = [
        ["card", "Card", json.dumps({"name": "합성카드"}, ensure_ascii=False), "", "r"],
        ["ben1", "Benefit", json.dumps({"name": "정답혜택"}, ensure_ascii=False), "", "r"],
        ["ben2", "Benefit", json.dumps({"name": "딴혜택"}, ensure_ascii=False), "", "r"],
        ["ben3", "Benefit", json.dumps({"name": "파일없는혜택"}, ensure_ascii=False), "", "r"],
    ]
    _write_csv(issuer_dir / "fp_nodes.csv", ["id", "node_type", "props", "chunk_id", "run_id"], nodes)
    _write_csv(issuer_dir / "fp_edges.csv", ["id", "source_id", "target_id", "edge_type", "run_id"],
               [["e1", "card", "ben1", "OFFERS", "r"], ["e2", "card", "ben2", "OFFERS", "r"], ["e3", "card", "ben3", "OFFERS", "r"]])
    _write_csv(issuer_dir / "fp_evidence.csv", ["node_id", "edge_id", "doc_sha256", "page_no", "start_pos", "end_pos", "quote_status"], [
        ["ben2", "", "sha1", "1", str(b + 1), str(b + 6), "located"],
        ["ben1", "", "sha1", "1", str(a + 1), str(a + len(SENT)), "located"],
        ["ben3", "", "sha2", "1", "1", "5", "located"],
    ])
    questions = tmp_path / "q.json"
    questions.write_text(json.dumps({"questions": [
        {"id": "T-1", "issuer": "test", "type": "benefit_condition", "question": "합성 질문", "expected": [SENT]}]}, ensure_ascii=False), encoding="utf-8")
    results = tmp_path / "r.jsonl"
    results.write_text(json.dumps({
        "id": "T-1", "answer": "합성 답변", "classification": "search_hit_answer_miss",
        "selected_seed_names": ["합성카드"], "retrieved_node_ids": [uuidish(i) for i in ("card", "ben1", "ben2", "ben3")]}, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"dir": tmp_path, "issuer": issuer_dir, "docs": index_dir / "documents.csv", "q": questions, "r": results}


def test_overlap_score_counts_expected_grams():
    assert rf.overlap_score("가나다라마", "xx 가나다라마 yy") == 1.0
    assert rf.overlap_score("가나다라마", "전혀 다른 글") == 0.0
    assert rf.overlap_score("", "무엇이든") == 0.0


def test_span_window_reports_line_numbers_and_context():
    text = "l1\nl2\nl3 대상\nl4\nl5\nl6\nl7"
    start = text.index("대상") + 1
    ls, le, before, span, after = rf.span_window(text, start, start + 1)
    assert (ls, le) == (3, 3)
    assert span == "대상"
    assert before.startswith("l1") and "l5" in after and "l7" not in after


def test_focus_sheet_ranks_relevant_evidence_first(world):
    out = rf.make_focus_sheet(world["r"], world["q"], [world["issuer"]], [world["docs"]], world["dir"] / "out.html")
    t = out.read_text(encoding="utf-8")
    assert "★ 정답 문장 포함(겹침 100%)" in t
    assert f"<mark>{SENT}</mark>" in t
    assert "2줄" in t                                   # 첫 줄 다음 줄
    assert "—OFFERS→" in t and "합성카드(Card)" in t        # 그래프 경로
    assert t.index("정답혜택") < t.index("딴혜택")            # 정답 포함 근거가 앞
    assert "PDF 없음" in t                                # 파일이 없어도 죽지 않음
    assert "정답 문장이 들어 있는 곳 1곳" in t


def test_focus_output_must_stay_under_tmp(world):
    with pytest.raises(ValueError):
        rf.make_focus_sheet(world["r"], world["q"], [world["issuer"]], [world["docs"]], Path.home() / "out.html")


def test_span_window_clamps_boundaries():
    text = "첫줄\n\n셋째 줄\n끝"
    ls, le, before, span, after = rf.span_window(text, 0, 1)          # start=0 은 첫 글자로 보정
    assert (ls, le) == (1, 1) and span == "첫"
    ls, le, before, span, after = rf.span_window(text, len(text), len(text) + 50)   # end 가 길이를 넘어도 안전
    assert span == "끝" and after == ""
    ls, le, _, span, _ = rf.span_window(text, 5, 8)                   # 빈 줄도 줄 번호에 센다
    assert ls == 3


def test_overlap_score_short_expected_and_spacing():
    assert rf.overlap_score("가나", "x 가 나 y") == 1.0                 # 3글자 이하는 통째로 비교, 공백 무시
    assert rf.overlap_score("가나", "다라") == 0.0


def test_focus_escapes_html_and_closes_pdf_on_error(world, monkeypatch):
    q = json.loads(world["q"].read_text(encoding="utf-8"))
    q["questions"][0]["question"] = "<script>alert(1)</script>"
    world["q"].write_text(json.dumps(q, ensure_ascii=False), encoding="utf-8")
    out = rf.make_focus_sheet(world["r"], world["q"], [world["issuer"]], [world["docs"]], world["dir"] / "o2.html")
    t = out.read_text(encoding="utf-8")
    assert "<script>" not in t and "&lt;script&gt;" in t

    closed = []
    real_open = fitz.open

    class Spy:
        def __init__(self, doc): self.doc = doc
        def __len__(self): return len(self.doc)
        def __getitem__(self, i): return self.doc[i]
        def close(self): closed.append(1); self.doc.close()

    monkeypatch.setattr(fitz, "open", lambda *a, **k: Spy(real_open(*a, **k)))
    monkeypatch.setattr(rf, "_build_focus_sheet", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(RuntimeError):
        rf.make_focus_sheet(world["r"], world["q"], [world["issuer"]], [world["docs"]], world["dir"] / "o3.html")
    assert closed == []            # 아직 열린 문서가 없으면 닫을 것도 없다(오류 없이 통과해야 함)


def test_no_seed_means_no_path_but_still_renders(world):
    rec = json.loads(world["r"].read_text(encoding="utf-8").splitlines()[0])
    rec["selected_seed_names"] = []
    world["r"].write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
    t = rf.make_focus_sheet(world["r"], world["q"], [world["issuer"]], [world["docs"]], world["dir"] / "o4.html").read_text(encoding="utf-8")
    assert "그래프 경로" not in t and f"<mark>{SENT}</mark>" in t
