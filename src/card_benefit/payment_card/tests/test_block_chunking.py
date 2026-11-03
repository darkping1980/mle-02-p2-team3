"""BLOCK_V1 다중 청크 단위 테스트. DB·외부 API에 접속하지 않는다."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from payment_card.db_pipeline.block_chunking import SPLIT_RULE_BLOCK, split_blocks
from payment_card.db_pipeline.document_service import page_chunks
from payment_card.db_pipeline.extraction_service import ExtractionError, merge_pages
from payment_card.tests.test_extraction import (
    FakeLlm, FakeSession, ServiceCase, benefit, checked_page, page_json, quote,
)

PAGE = """Mastercard Platinum 공통서비스
· Trip.com 호텔 6%, 항공 3%, 액티비티 5% 할인
· Agoda.com 8% 할인 (최대 USD 30),
  (예약: 26.1.1~26.3.31 / 숙박: 26.1.1~26.12.31)
Travel
* 본 서비스는 기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지
   제공됩니다.
· Trump Hotels 10% 할인
· Outrigger Hotels and Resorts 5% 할인
* 아래의 Mastercard Platinum 서비스는 Mastercard Platinum 등급 카드 소지자에게 공통으로 제공됩니다.
"""


def test_blocks_cover_page_exactly_and_keep_items_whole():
    blocks = split_blocks(1, PAGE, max_items=1)
    assert "".join(b.text for b in blocks) == PAGE
    assert all(PAGE[b.start_pos - 1:b.end_pos] == b.text for b in blocks)
    assert [b.chunk_type_cd for b in blocks] == ["BODY", "BODY", "NOTICE", "BODY", "BODY", "NOTICE"]
    agoda = next(b for b in blocks if "Agoda" in b.text)
    assert "(예약: 26.1.1~26.3.31" in agoda.text and agoda.item_cnt == 1      # 이어지는 줄을 자르지 않는다
    assert "제공됩니다." in blocks[2].text                                    # 유의사항의 이어지는 줄


def test_max_items_groups_items_and_page_without_items_is_one_chunk():
    assert [b.item_cnt for b in split_blocks(1, PAGE) if b.chunk_type_cd == "BODY"] == [2, 2]
    table = "구분\n할인율\n5%\n월 1천원\n"
    assert [(b.start_pos, b.end_pos, b.chunk_type_cd) for b in split_blocks(2, table)] == [(1, len(table), "BODY")]
    assert split_blocks(3, "   \n") == []
    with pytest.raises(ValueError):
        split_blocks(1, PAGE, max_items=0)


def test_page_chunks_numbers_sequence_and_records_rule():
    chunks = page_chunks(1, PAGE, 5, SPLIT_RULE_BLOCK)
    assert [c.seq for c in chunks] == list(range(5, 5 + len(chunks)))
    assert {c.split_rule_ver for c in chunks} == {SPLIT_RULE_BLOCK}
    assert page_chunks(1, PAGE, 1)[0].split_rule_ver == "PAGE_V1"
    with pytest.raises(ValueError):
        page_chunks(1, PAGE, 1, "UNKNOWN_V9")


def test_merge_identifies_items_by_chunk_not_page():
    """같은 페이지 두 청크의 항목 순번이 모두 1이어도 다른 항목이다."""
    first = checked_page(1, "· Trip.com 5%", page_json(1, [benefit("Trip.com", raw="5%", evidence=[quote("5%", "RULE", "RATE")], limits=[], rules=[{
        "rule_key": "RATE", "calc_method_cd": "PERCENT_OF_TXN", "value_num": 5, "value_raw_txt": "5%",
        "value_unit_cd": "PERCENT", "payout_unit_cd": "KRW"}])]), chunk_id="B1")
    second = checked_page(1, "· Agoda 8%", page_json(1, [benefit("Agoda", raw="8%", evidence=[quote("8%", "RULE", "RATE")], limits=[], rules=[{
        "rule_key": "RATE", "calc_method_cd": "PERCENT_OF_TXN", "value_num": 8, "value_raw_txt": "8%",
        "value_unit_cd": "PERCENT", "payout_unit_cd": "KRW"}])]), chunk_id="B2")
    benefits, _ = merge_pages([first, second])
    refs = sorted((b.merge.source_refs[0].card_doc_chunk_id, b.merge.source_refs[0].stg_item_seq) for b in benefits)
    assert refs == [("B1", 1), ("B2", 1)]


class MultiChunkRunTests(ServiceCase):
    def setUp(self):
        super().setUp()
        body, notice = "· Trip.com 호텔 6% 할인\n", "* 기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지 제공됩니다.\n"
        self.body, self.notice = body, notice
        self.chunks = [
            {"card_doc_id": "D1", "page_no": 1, "card_doc_chunk_id": "B1", "chunk_seq": 3, "chunk_raw_txt": body,
             "chunk_split_rule_ver": SPLIT_RULE_BLOCK, "chunk_type_cd": "BODY"},
            {"card_doc_id": "D1", "page_no": 1, "card_doc_chunk_id": "N1", "chunk_seq": 4, "chunk_raw_txt": notice,
             "chunk_split_rule_ver": SPLIT_RULE_BLOCK, "chunk_type_cd": "NOTICE"},
        ]

    def item(self):
        return benefit("Trip.com 호텔", value=6, raw="6%", limits=[], validity_period_txt="2026년 1월 1일 ~ 12월 31일",
                       rules=[{"rule_key": "HOTEL", "calc_method_cd": "PERCENT_OF_TXN", "value_num": 6, "value_raw_txt": "6%",
                               "value_unit_cd": "PERCENT", "payout_unit_cd": "KRW"}],
                       evidence=[quote("Trip.com 호텔 6%", "RULE", "HOTEL", "SAME_TEXT"),
                                 quote("기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지", "APPLICABILITY")])

    def run_service(self, chunks=None):
        test = self

        class TargetLlm(FakeLlm):
            """대상 구간에 Trip.com이 있을 때만 혜택을 돌려준다(유의사항 청크는 혜택 없음)."""
            def extract(self, page_input):
                target = page_input.page_text.split("[같은 페이지")[0]
                self.responses = {1: page_json(1, [test.item()] if "Trip.com" in target else [])}
                return super().extract(page_input)

        session = FakeSession(doc=self.doc, chunks=chunks or self.chunks)
        llm = TargetLlm({})
        from payment_card.db_pipeline.extraction_service import ExtractionService
        service = ExtractionService(session, llm, data_root=self.root)
        with patch.object(service.repository, "select_reusable_runs", return_value=[]):
            return session, llm, service.run("D1", card_id=1)

    def test_partial_chunk_sends_context_without_image_and_locates_evidence_in_notice(self):
        session, llm, result = self.run_service()
        assert result.status == "SUCCEEDED" and result.pages_ok == 2
        body_input = next(i for i in llm.inputs if "[추출 대상: 청크 3]" in i.page_text)
        assert body_input.image_png is None
        assert "[같은 페이지 유의사항 문맥: 인용 전용]" in body_input.page_text and self.notice.strip() in body_input.page_text
        evidence = session.calls("insert_evidence")
        rows = [row for batch in evidence for row in (batch if isinstance(batch, list) else [batch])]
        by_chunk = {row["CARD_DOC_CHUNK_ID"]: row for row in rows}
        assert by_chunk["B1"]["START_POS"] == self.body.index("Trip.com") + 1
        notice_row = by_chunk["N1"]
        assert self.notice[notice_row["START_POS"] - 1:notice_row["END_POS"]] == "기간이 명시되지 않는 한 2026년 1월 1일 ~ 12월 31일까지"

    def test_whole_page_chunk_keeps_image(self):
        whole = [dict(self.chunks[0], chunk_raw_txt=self.body + self.notice, chunk_type_cd="BODY")]
        _, llm, _ = self.run_service(whole)
        assert llm.inputs[0].image_png is not None and llm.inputs[0].page_text == self.body + self.notice

    def test_selected_chunks_run_is_partial_and_records_choice(self):
        session = FakeSession(doc=self.doc, chunks=self.chunks)
        from payment_card.db_pipeline.extraction_service import ExtractionService
        llm = FakeLlm({1: page_json(1)})
        result = ExtractionService(session, llm, data_root=self.root).run("D1", card_id=1, chunk_ids={"B1"})
        assert result.status == "PARTIAL" and len(llm.inputs) == 1 and "AI 입력 제외 청크: 1건" in result.note
        assert session.calls("insert_run")[0]["RUN_PARAM"].obj["chunk_ids"] == ["B1"]
        with pytest.raises(ExtractionError):
            ExtractionService(session, llm, data_root=self.root).run("D1", card_id=1, chunk_ids={"NOPE"})

    def test_mixed_split_rules_require_choice(self):
        mixed = [*self.chunks, {"card_doc_id": "D1", "page_no": 1, "card_doc_chunk_id": "P1", "chunk_seq": 1,
                                "chunk_raw_txt": self.body + self.notice, "chunk_split_rule_ver": "PAGE_V1"}]
        session = FakeSession(doc=self.doc, chunks=mixed)
        from payment_card.db_pipeline.extraction_service import ExtractionService
        with pytest.raises(ExtractionError):
            ExtractionService(session, FakeLlm({1: page_json(1)}), data_root=self.root).run("D1", card_id=1)
