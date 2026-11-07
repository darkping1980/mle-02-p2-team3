from __future__ import annotations

import csv
from pathlib import Path
import tempfile
import unittest

from payment_card.file_pipeline.doc_index.adapters import hana, woori
from payment_card.file_pipeline.doc_index.core import build_index


def fake_measure(sha_by_path: dict, chars: int = 1000, pages: int = 2):
    def measure(path: Path) -> dict:
        key = path.name
        if key not in sha_by_path:
            return {"exists": False}
        return {"exists": True, "sha256": sha_by_path[key].ljust(64, "0"), "pages": pages, "text_chars": chars}

    return measure


def entry(path, product, role="product_guide", origin="official_download", board_date=""):
    return {
        "file_path": path, "manifest_sha256": "", "doc_role": role, "origin": origin,
        "source_url": "", "board_date": board_date, "product_name": product,
        "product_ids": {"id": product}, "review_reasons": [],
    }


class BuildIndexTests(unittest.TestCase):
    def build(self, entries, shas, card_type_overrides=None, **kwargs):
        return build_index(
            "x", Path("/none"), entries, fake_measure(shas, **kwargs), card_type_overrides
        )

    def test_same_hash_keeps_one_canonical_preferring_official_over_existing(self):
        entries = [
            entry("credit/a.pdf", "A", origin="existing_unverified"),
            entry("credit/신용_A_공식.pdf", "A"),
        ]
        docs, _, summary = self.build(entries, {"a.pdf": "aa", "신용_A_공식.pdf": "aa"})
        by_path = {d["file_path"]: d for d in docs}
        self.assertEqual(by_path["x_all/credit/신용_A_공식.pdf"]["canonical"], "Y")
        self.assertEqual(by_path["x_all/credit/a.pdf"]["canonical"], "N")
        self.assertEqual(by_path["x_all/credit/a.pdf"]["duplicate_of"], "x_all/credit/신용_A_공식.pdf")
        self.assertEqual(summary["bad_canonical_groups"], [])

    def test_web_capture_loses_when_official_guide_exists(self):
        entries = [
            entry("credit/g.pdf", "A"),
            entry("credit/w.pdf", "A", role="web_capture", origin="web_capture"),
            entry("credit/w2.pdf", "B", role="web_capture", origin="web_capture"),
        ]
        docs, _, summary = self.build(entries, {"g.pdf": "01", "w.pdf": "02", "w2.pdf": "03"})
        canonical = {d["file_path"].rsplit("/", 1)[1]: d["canonical"] for d in docs}
        self.assertEqual(canonical, {"g.pdf": "Y", "w.pdf": "N", "w2.pdf": "Y"})
        only_web = next(d for d in docs if d["file_path"].endswith("w2.pdf"))
        self.assertEqual(only_web["needs_review"], "Y")
        self.assertEqual(summary["bad_canonical_groups"], [])

    def test_shared_content_across_products_is_shared_guide(self):
        entries = [entry("credit/p1.pdf", "P1"), entry("credit/p2.pdf", "P2"), entry("credit/o.pdf", "O")]
        _, links, _ = self.build(entries, {"p1.pdf": "11", "p2.pdf": "11", "o.pdf": "22"})
        relation = {link["product_name"]: link["relation"] for link in links}
        self.assertEqual(relation, {"P1": "shared_guide", "P2": "shared_guide", "O": "primary_guide"})

    def test_human_card_type_override_replaces_folder_and_clears_reason(self):
        e = entry("credit/c.pdf", "체크상품")
        e["review_reasons"] = ["카드 구분 확인 필요(상품명에 체크 포함)", "다른 사유"]
        docs, links, _ = self.build([e], {"c.pdf": "aa"}, card_type_overrides={"체크상품": "debit"})
        self.assertEqual(docs[0]["card_type"], "debit")
        self.assertEqual(docs[0]["review_reason"], "다른 사유")
        self.assertEqual(links[0]["card_type"], "debit")

    def test_review_decision_clears_name_reason_and_marks_image_content(self):
        e = entry("credit/c.pdf", "상품")
        e["review_reasons"] = ["PDF 내 상품명 자동 확인 실패", "다른 사유"]
        decisions = {"aa".ljust(16, "0"): {"name_ok": True, "content_image": True}}
        docs, _, summary = build_index(
            "x", Path("/none"), [e], fake_measure({"c.pdf": "aa"}), None, decisions
        )
        self.assertEqual(docs[0]["review_reason"], "다른 사유")
        self.assertEqual(docs[0]["ocr_needed"], "Y")
        self.assertEqual(summary["ocr_needed"], 1)

    def test_review_decision_with_name_ok_only_keeps_ocr_flag(self):
        e = entry("credit/c.pdf", "상품")
        e["review_reasons"] = ["PDF 내 상품명 자동 확인 실패"]
        decisions = {"aa".ljust(16, "0"): {"name_ok": True, "content_image": False}}
        docs, _, _ = build_index("x", Path("/none"), [e], fake_measure({"c.pdf": "aa"}), None, decisions)
        self.assertEqual((docs[0]["needs_review"], docs[0]["ocr_needed"]), ("N", "N"))

    def test_missing_file_is_reported_not_indexed(self):
        docs, links, summary = self.build([entry("credit/none.pdf", "A")], {})
        self.assertEqual((docs, links), ([], []))
        self.assertEqual(summary["missing_files"], ["credit/none.pdf"])

    def test_ocr_needed_by_chars_per_page_and_unclassified_needs_review(self):
        docs, _, _ = self.build([entry("credit/i.pdf", "A", role="unclassified")], {"i.pdf": "aa"}, chars=10, pages=2)
        self.assertEqual(docs[0]["ocr_needed"], "Y")
        self.assertEqual(docs[0]["needs_review"], "Y")


class AdapterTests(unittest.TestCase):
    def write_csv(self, root: Path, rows: list[dict]):
        with (root / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def test_woori_paths_roles_and_inherited_role_for_existing_file(self):
        base = {k: "" for k in [
            "record_type", "product_name", "product_code", "source_slot", "board_date", "file_path",
            "sha256", "name_in_pdf", "verify_note", "pdf_source_path", "download_result", "fail_reason"]}
        rows = [
            {**base, "record_type": "OFFICIAL_COLLECTED", "product_name": "A", "product_code": "1", "source_slot": "g1",
             "file_path": "collection/credit/new.pdf", "sha256": "s1", "board_date": "2025100100"},
            {**base, "record_type": "OFFICIAL_COLLECTED", "product_name": "A", "product_code": "1", "source_slot": "g2",
             "file_path": "../common/b.pdf", "sha256": "s2"},
            {**base, "record_type": "EXISTING_FILE", "product_name": "A", "file_path": "old.pdf", "sha256": "s1"},
            {**base, "record_type": "EXISTING_FILE", "product_name": "Z", "file_path": "unk.pdf", "sha256": "s9"},
            {**base, "record_type": "OFFICIAL_COLLECTED", "product_name": "F", "download_result": "실패", "fail_reason": "DRM"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_csv(root, rows)
            entries, extra = woori.load_entries(root)
        got = {e["file_path"]: (e["doc_role"], e["origin"]) for e in entries}
        self.assertEqual(got["credit/collection/credit/new.pdf"], ("product_guide", "official_download"))
        self.assertEqual(got["common/b.pdf"], ("brand_service", "official_download"))
        self.assertEqual(got["credit/old.pdf"], ("product_guide", "existing_unverified"))
        self.assertEqual(got["credit/unk.pdf"], ("unclassified", "existing_unverified"))
        self.assertEqual(len(extra["skipped_rows"]), 1)

    def test_split_products_pairs_names_with_codes(self):
        got = woori.split_products("A; B 협회 ; C", "1; 2; 3")
        self.assertEqual(got, [("A", "1"), ("B 협회", "2"), ("C", "3")])
        # 개수가 다르면 코드는 믿지 않고 비운다
        self.assertEqual(woori.split_products("A; B", "1"), [("A", ""), ("B", "")])
        self.assertEqual(woori.split_products("단독", "9"), [("단독", "9")])
        # 상품 이름이 없어도 파일이 사라지면 안 된다
        self.assertEqual(woori.split_products("", ""), [("", "")])

    def test_hana_scope_roles_and_origin(self):
        cols = ["카드상품명", "문서종류", "문서구분", "파일경로", "SHA256", "PDF원본URL", "모바일상세URL",
                "PDF내 상품명확인", "다운로드결과", "실패사유", "CD_ID", "PC_SEQ", "모바일_CD_NO", "디자인코드"]
        base = {c: "" for c in cols}
        rows = [
            {**base, "카드상품명": "A", "문서종류": "상품설명서(공식PDF)", "문서구분": "공식 원본 PDF(URL 추정 확인)",
             "파일경로": "credit/a_20250703.pdf", "CD_ID": "9"},
            {**base, "카드상품명": "A", "문서종류": "상품상세 웹페이지(펼침 영역 포함)", "문서구분": "웹페이지 변환 PDF",
             "파일경로": "credit/w.pdf"},
            {**base, "카드상품명": "C", "문서종류": "상품설명서(공식PDF)", "문서구분": "공식 원본 PDF",
             "파일경로": "debit/c.pdf"},
            {**base, "카드상품명": "T", "문서종류": "공통약관: 표준약관", "문서구분": "공식 원본 PDF",
             "파일경로": "common/t.pdf"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.write_csv(root, rows)
            entries, _ = hana.load_entries(root)
        got = {e["file_path"]: (e["doc_role"], e["origin"], e["board_date"]) for e in entries}
        self.assertEqual(set(got), {"credit/a_20250703.pdf", "credit/w.pdf", "common/t.pdf"})
        self.assertEqual(got["credit/a_20250703.pdf"], ("product_guide", "official_url_inferred", "20250703"))
        self.assertEqual(got["credit/w.pdf"][:2], ("web_capture", "web_capture"))
        self.assertEqual(got["common/t.pdf"][0], "terms")


if __name__ == "__main__":
    unittest.main()


class BatchTests(unittest.TestCase):
    def test_selects_only_canonical_target_roles_and_skips_ocr(self):
        from payment_card.file_pipeline.doc_index.batch import select_documents

        def row(path, role="product_guide", canonical="Y", ocr="N", card="credit"):
            return {"file_path": path, "doc_role": role, "canonical": canonical, "ocr_needed": ocr, "card_type": card}

        targets, skipped = select_documents([
            row("ok.pdf"), row("dup.pdf", canonical="N"), row("terms.pdf", role="terms"),
            row("img.pdf", ocr="Y"), row("brand.pdf", role="brand_service", card="common"),
            row("chk.pdf", card="debit"),
        ])
        self.assertEqual([t["file_path"] for t in targets], ["ok.pdf", "brand.pdf"])
        self.assertEqual([s["file_path"] for s in skipped], ["img.pdf"])

    def test_failure_of_one_file_does_not_stop_the_batch(self):
        from payment_card.file_pipeline.doc_index.batch import run_batch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "idx" / "x").mkdir(parents=True)
            cols = ["doc_id", "sha256", "file_path", "doc_role", "canonical", "ocr_needed", "pages", "card_type"]
            with (root / "idx" / "x" / "documents.csv").open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=cols)
                writer.writeheader()
                writer.writerow(dict(zip(cols, ["d1", "s1", "x_all/a.pdf", "product_guide", "Y", "N", "2", "credit"])))
                writer.writerow(dict(zip(cols, ["d2", "s2", "x_all/b.pdf", "product_guide", "Y", "N", "1", "credit"])))

            def convert(path, expected_sha256=None, expected_page_count=None):
                if path.name == "b.pdf":
                    raise ValueError("SHA-256이 다릅니다")
                return {"chunks": [1, 2], "pages": []}

            summary = run_batch("x", root / "data", root / "idx", root / "out", convert=convert)
            self.assertEqual([d["file_path"] for d in summary["done"]], ["x_all/a.pdf"])
            self.assertEqual(len(summary["failed"]), 1)
            self.assertTrue((root / "out" / "x" / "d1.json").is_file())


class TablesTests(unittest.TestCase):
    def test_compact_row_drops_empty_cells_and_newlines(self):
        from payment_card.file_pipeline.doc_index.tables import compact_row

        self.assertEqual(compact_row(["2건", "", None, "2000원\n ,", ""]), ["2건", "2000원 ,"])

    def test_good_table_is_usable(self):
        from payment_card.file_pipeline.doc_index.tables import check_table

        rows = [["당월 결제 건수", "할인 금액"], ["2건", "2,000원"], ["3건", "3,000원"]]
        plain = "당월 결제 건수 | 할인 금액 | 2건 | 2,000원 | 3건 | 3,000원"
        self.assertEqual(check_table(rows, plain), (True, ""))

    def test_split_characters_and_tiny_tables_are_rejected(self):
        from payment_card.file_pipeline.doc_index.tables import check_table

        broken = [["스", "파이크 서비스", "10000원"], ["서", "브 서비스", "5000원"], ["구", "분", "금액"]]
        self.assertFalse(check_table(broken, "스파이크서비스10000원서브서비스5000원구분금액")[0])
        self.assertFalse(check_table([["연회비", "12,000원"]], "연회비 12,000원")[0])

    def test_char_count_mismatch_is_rejected(self):
        from payment_card.file_pipeline.doc_index.tables import check_table

        rows = [["항목", "내용"], ["가나다", "라마바"]]
        self.assertFalse(check_table(rows, "항목 내용 가나다 라마바 " + "추가문장" * 20)[0])
