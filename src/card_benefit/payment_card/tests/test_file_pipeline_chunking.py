from __future__ import annotations

import unittest

from payment_card.file_pipeline.chunking.build import build_doc_chunks, build_page_chunks, check_pieces
from payment_card.file_pipeline.chunking.headings import find_heading_offsets, inside_any
from payment_card.file_pipeline.chunking.split import split_page


def long_text(parts: int = 5, size: int = 1000) -> tuple[str, list[int]]:
    """제목 줄이 parts개 있는 긴 글과 제목 시작 위치를 만든다."""
    text, offsets = "", []
    for number in range(parts):
        offsets.append(len(text))
        text += f"제목{number}\n" + ("가" * (size - 6)) + "\n"
    return text, offsets


class SplitPageTests(unittest.TestCase):
    def test_empty_page_has_no_pieces(self):
        self.assertEqual(split_page("  \n ", [0]), [])

    def test_short_page_is_one_piece_covering_all_text(self):
        text = "가" * 100 + "\n"
        self.assertEqual(split_page(text, [10, 50]), [(0, len(text))])

    def test_long_page_is_cut_before_headings_and_pieces_join_back(self):
        text, offsets = long_text()
        spans = split_page(text, offsets)
        self.assertGreater(len(spans), 1)
        self.assertEqual("".join(text[s:e] for s, e in spans), text)
        for start, _ in spans[1:]:
            self.assertIn(start, offsets)

    def test_no_cut_until_enough_text_has_piled_up(self):
        text, offsets = long_text(parts=6, size=1000)
        # 제목 간격이 1000자이고 최소 조각이 2500자이면 세 번째 제목부터 자를 수 있다
        spans = split_page(text, offsets, over=100, min_chars=2500)
        self.assertEqual(spans[0][1], offsets[3])

    def test_short_last_piece_is_merged_into_previous(self):
        text, offsets = long_text(parts=3, size=1000)
        text += "끝"          # 마지막 조각이 매우 짧아지도록 제목 하나를 끝에 둔다
        offsets.append(len(text) - 1)
        spans = split_page(text, offsets, over=100, min_chars=400)
        self.assertEqual(spans[-1][1], len(text))
        self.assertGreaterEqual(spans[-1][1] - spans[-1][0], 400)

    def test_heading_at_start_is_ignored_and_no_headings_keeps_one_piece(self):
        text, _ = long_text()
        self.assertEqual(split_page(text, [0]), [(0, len(text))])
        self.assertEqual(split_page(text, []), [(0, len(text))])


class HeadingTests(unittest.TestCase):
    def test_inside_any(self):
        rects = [(0, 0, 10, 10)]
        self.assertTrue(inside_any((5, 5), rects))
        self.assertFalse(inside_any((11, 5), rects))
        self.assertFalse(inside_any((5, 5), []))

    def test_find_heading_offsets_uses_font_size_and_page_text_position(self):
        import pymupdf

        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 60), "Big Heading", fontsize=16)
        for number in range(12):
            page.insert_text((72, 100 + number * 14), f"body line number {number}", fontsize=8)
        page.insert_text((72, 300), "Second Heading", fontsize=16)
        text = page.get_text()
        found = find_heading_offsets(page, text)
        self.assertEqual([t for _, t in found], ["Big Heading", "Second Heading"])
        for offset, heading in found:
            self.assertEqual(text[offset:offset + len(heading)], heading)


class BuildTests(unittest.TestCase):
    def test_chunk_positions_are_one_based_inclusive_and_match_text(self):
        text, offsets = long_text()   # 4000자 넘는 쪽
        headings = [(o, f"제목{i}") for i, o in enumerate(offsets)]
        chunks = build_page_chunks("abc", 2, text, headings)
        for chunk in chunks:
            self.assertEqual(text[chunk["start_pos"] - 1:chunk["end_pos"]], chunk["text"])
        self.assertEqual(chunks[0]["chunk_id"], "abc-p0002-c01")
        self.assertEqual(chunks[0]["start_pos"], 1)
        self.assertEqual(chunks[-1]["end_pos"], len(text))

    def test_check_pieces_rejects_mismatch_and_chunks_on_empty_page(self):
        with self.assertRaises(ValueError):
            check_pieces("가나다", [(0, 2)])
        with self.assertRaises(ValueError):
            check_pieces("  ", [(0, 2)])
        check_pieces("  ", [])

    def make_trace(self, sha="s1"):
        long_page, _ = long_text(parts=6, size=1000)
        return {"document": {"sha256": sha}, "pages": [
            {"page_no": 1, "text": "짧은 쪽\n"},
            {"page_no": 2, "text": ""},
            {"page_no": 3, "text": long_page},
        ]}

    def test_doc_chunks_skip_empty_page_and_call_finder_only_for_long_pages(self):
        calls = []
        long_page, offsets = long_text(parts=6, size=1000)

        def finder(page_no, text):
            calls.append(page_no)
            return [(o, f"제목{i}") for i, o in enumerate(offsets)]

        row = {"doc_id": "d1", "sha256": "s1", "file_path": "x_all/credit/a.pdf"}
        products = [{"product_name": "A", "product_ids": {"product_code": "1"}}]
        result = build_doc_chunks(row, self.make_trace(), products, finder)
        self.assertEqual(calls, [3])
        self.assertEqual({c["page_no"] for c in result["chunks"]}, {1, 3})
        self.assertEqual(result["doc_sha256"], "s1")
        self.assertEqual(result["products"], products)
        self.assertEqual(result["chunks"][0]["text"], "짧은 쪽\n")

    def test_doc_chunks_reject_sha_mismatch(self):
        row = {"doc_id": "d1", "sha256": "other", "file_path": "x"}
        with self.assertRaises(ValueError):
            build_doc_chunks(row, self.make_trace(), [], lambda *_: [])


if __name__ == "__main__":
    unittest.main()
