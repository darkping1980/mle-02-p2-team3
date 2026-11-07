import json
from pathlib import Path
import tempfile
import unittest

from payment_card.file_pipeline.extraction.review.review_auto_audit import audit_review_sheet


def _make_fixture(root: Path, position: str = "4~8", excerpt: str = "5% 할인", rate: str = "5%", method: str = "DISCOUNT", checked: bool = True):
    chunks = root / "chunks"
    traces = root / "trace"
    chunks.mkdir()
    traces.mkdir()
    text = "혜택 5% 할인, 월 최대 1만원"
    chunk_id = "doc123-p0001-c01"
    (chunks / "doc123.chunks.json").write_text(json.dumps({
        "doc_id": "doc123", "doc_sha256": "a" * 64, "file_path": "hana_all/test.pdf",
        "chunks": [{"chunk_id": chunk_id, "page_no": 1, "start_pos": 1,
                    "end_pos": len(text), "text": text}],
    }), encoding="utf-8")
    (traces / "doc123.json").write_text(json.dumps({
        "pages": [{"page_no": 1, "text": text}],
    }), encoding="utf-8")
    sheet = root / "review.md"
    sheet.write_text(
        "# 검토표\n\n## 청크 doc123-p0001-c01\n\n- 문서 ID: doc123\n- 페이지: 1\n\n"
        "### 원문\n\n```text\n" + text + "\n```\n\n### benefits\n\n"
        "| 이름 | 방법 | 비율 | 금액 | 인용문 | 위치 | 위치 확인용 청크 부분 | 대조 |\n"
        "|---|---|---|---|---|---|---|---|\n"
        f"| 혜택 | {method} | {rate} | — | 5% 할인 | {position} | {excerpt} | [{'x' if checked else ' '}] 원문과 일치 [ ] 값 오류 [ ] 누락 있음 [ ] 환각 |\n",
        encoding="utf-8",
    )
    return sheet, chunks, traces


class ReviewAutoAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_review_auto_audit_checks_page_location_and_compares_human_mark(self):
        sheet, chunks, traces = _make_fixture(self.root)

        report = audit_review_sheet(sheet, chunks, traces)

        row = report["rows"][0]
        self.assertEqual(row["automated_flags"], [])
        self.assertEqual(row["human_label"], "match")
        self.assertEqual(report["human_comparison"]["true_negative"], 1)
        self.assertEqual(report["summary"]["mechanically_supported"], 1)

    def test_review_auto_audit_flags_location_mismatch_against_page_text(self):
        sheet, chunks, traces = _make_fixture(self.root, position="1~3", excerpt="혜택", checked=False)

        report = audit_review_sheet(sheet, chunks, traces)

        row = report["rows"][0]
        self.assertIn("position_quote_mismatch", row["automated_flags"])
        self.assertEqual(report["summary"]["flagged_unreviewed_rows"], 1)
        self.assertEqual(report["summary"]["human_confirmation_rows"], 1)

    def test_review_auto_audit_flags_numeric_value_missing_from_quote(self):
        sheet, chunks, traces = _make_fixture(self.root, rate="10%")

        report = audit_review_sheet(sheet, chunks, traces)

        self.assertIn("numeric_value_not_in_quote", report["rows"][0]["automated_flags"])

    def test_review_auto_audit_queues_unset_benefit_method_for_human(self):
        sheet, chunks, traces = _make_fixture(self.root, method="—", checked=False)

        report = audit_review_sheet(sheet, chunks, traces)

        self.assertIn("benefit_method_unspecified", report["rows"][0]["automated_flags"])
        self.assertEqual(report["summary"]["human_confirmation_rows"], 1)

    def test_review_auto_audit_ignores_empty_section_placeholder(self):
        sheet, chunks, traces = _make_fixture(self.root)
        with sheet.open("a", encoding="utf-8") as stream:
            stream.write("\n### limits\n\n| 텍스트 | 기간 | 금액 | 무제한 | 공유 | 인용문 | 위치 | 위치 확인용 청크 부분 | 대조 |\n")
            stream.write("|---|---|---|---|---|---|---|---|---|\n| 항목 없음 | | | | | | | | |\n")

        report = audit_review_sheet(sheet, chunks, traces)

        self.assertEqual(report["summary"]["rows"], 1)

    def test_review_auto_audit_checks_relation_endpoints_when_results_are_supplied(self):
        sheet, chunks, traces = _make_fixture(self.root)
        with sheet.open("a", encoding="utf-8") as stream:
            stream.write("\n### relations\n\n| source → type → target | 인용문 | 위치 | 위치 확인용 청크 부분 | 대조 |\n")
            stream.write("|---|---|---|---|---|\n")
            stream.write("| b1 → HAS_CONDITION → missing | 5% 할인 | 4~8 | 5% 할인 | [ ] 원문과 일치 [ ] 값 오류 [ ] 누락 있음 [ ] 환각 |\n")
        results = self.root / "results"
        results.mkdir()
        extraction = {key: [] for key in ("benefits", "conditions", "limits", "targets", "relations")}
        extraction["benefits"] = [{"id": "b1", "name": "혜택", "method": "DISCOUNT", "evidence": [{"text": "5% 할인"}]}]
        extraction["relations"] = [{"source": "b1", "target": "missing", "type": "HAS_CONDITION", "evidence": [{"text": "5% 할인"}]}]
        (results / "doc123-p0001-c01.result.json").write_text(json.dumps({"chunk_id": "doc123-p0001-c01", "extraction": extraction}), encoding="utf-8")

        report = audit_review_sheet(sheet, chunks, traces, result_dir=results)

        relation = next(row for row in report["rows"] if row["section"] == "relations")
        self.assertIn("relation_target_missing", relation["automated_flags"])


if __name__ == "__main__":
    unittest.main()

