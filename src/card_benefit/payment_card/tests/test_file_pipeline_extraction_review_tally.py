import json
from pathlib import Path
import tempfile
import unittest

from payment_card.file_pipeline.extraction.review.review_tally import tally


class ReviewTallyTests(unittest.TestCase):
    def test_partly_filled_sheet_counts_marks_by_chunk_and_section(self):
        sheet = """## 청크 c-1
### benefits
| row | [x] 원문과 일치 [ ] 값 오류 [ ] 누락 있음 [ ] 환각 |
| row | [ ] 원문과 일치 [ ] 값 오류 [ ] 누락 있음 [ ] 환각 |
| row | [x] 원문과 일치 [x] 값 오류 [ ] 누락 있음 [ ] 환각 |
### limits
| row | [ ] 원문과 일치 [x] 값 오류 [ ] 누락 있음 [ ] 환각 |
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sheet.md"
            path.write_text(sheet, encoding="utf-8")
            result = tally(path)
        benefits = result["chunks"]["c-1"]["benefits"]
        self.assertEqual((benefits["match"], benefits["unchecked"], benefits["ambiguous"]), (1, 1, 1))
        self.assertEqual(benefits["accuracy"], 1.0)
        self.assertEqual(result["sections"]["limits"]["value_error"], 1)
        self.assertEqual(result["sections"]["limits"]["ratios_among_checked"]["value_error"], 1.0)


if __name__ == "__main__":
    unittest.main()
