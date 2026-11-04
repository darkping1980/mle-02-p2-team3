from __future__ import annotations

import unittest
from unittest.mock import patch

from payment_card.db_pipeline.common_benefit_service import CommonBenefitRepository
from payment_card.db_pipeline.product_benefit_service import ProductBenefitService
from payment_card.db_pipeline.benefit_main import parse_args
from payment_card.db_pipeline.unresolved_review import (
    APPROVED,
    PENDING,
    links_for_candidate,
    load_registry,
    unresolved_queue,
    validate_review_sources,
    verified_reviews_for_run,
)


REVIEWS = load_registry()
DOC = "20261104_000023"
RUN = "20261104_000032"
HEADER = "전월 국내 가맹점 이용금액\n30만원 이상\n70만원 미만\n70만원 이상\n120만원 미만\n120만원 이상"
ONLINE = "온라인\n4천원\n8천원\n16천원"
OFFLINE = "오프라인\n6천원\n12천원\n24천원"
TOTAL = "합계\n1만원\n2만원\n4만원"
ONLINE_SCOPE = "온라인 업종 통합 할인한도 내에서 할인 적용"


class UnresolvedReviewTests(unittest.TestCase):
    def test_review_queue_is_read_only_command_without_apply_flag(self):
        args = parse_args(["review-queue", "--run-id", RUN])
        self.assertEqual(args.kind, "review-queue")
        self.assertEqual(args.run_id, RUN)
        self.assertFalse(args.apply)

    def test_hana_runs_do_not_query_review_registry_items_or_gain_links(self):
        repo = CommonBenefitRepository(session=object())
        row = {"card_extr_stg_id": "HANA_STG", "card_doc_id": "HANA_DOC", "stg_raw_item": {"bnft_nm": "혜택"}}
        with patch.object(repo, "stored_run", return_value={}), patch.object(repo, "rows", side_effect=AssertionError("unexpected query")):
            result = repo.attach_normalized("HANA_RUN", [row])
        self.assertEqual(result[0]["reviewed_unresolved_links"], [])

    def test_registry_keeps_unresolved_queue_and_explicit_review_state(self):
        rows = [
            {"card_ai_run_id": RUN, "card_doc_id": DOC, "page_no": 2, "card_doc_chunk_id": "20261104_000079",
             "unresolved_ordinal": 1, "raw_txt": ONLINE_SCOPE, "reason": "cross-page scope"},
            {"card_ai_run_id": RUN, "card_doc_id": DOC, "page_no": 3, "card_doc_chunk_id": "20261104_000080",
             "unresolved_ordinal": 1,
             "raw_txt": "구분 \n전월 국내 가맹점 이용금액 \n30만원 이상 \n70만원 미만 \n70만원 이상 \n120만원 미만 \n120만원 이상 \n온라인 \n4천원 \n8천원 \n16천원 \n오프라인 \n6천원 \n12천원 \n24천원 \n합계 \n1만원 \n2만원 \n4만원",
             "reason": "unclear benefit link"},
            {"card_ai_run_id": RUN, "card_doc_id": DOC, "page_no": 3, "card_doc_chunk_id": "20261104_000080",
             "unresolved_ordinal": 2,
             "raw_txt": "할인금액 산정방법  \n= 주유 이용금액 × 리터당 할인금액 / GS칼텍스 휘발유 공시가 \n(경유, 등유 등 기타 유종은 GS칼텍스 휘발유 공시가로 환산 적용)",
             "reason": "formula not represented"},
            {"card_ai_run_id": RUN, "card_doc_id": DOC, "page_no": 4, "card_doc_chunk_id": "20261104_000081",
             "unresolved_ordinal": 2, "raw_txt": "단, 온라인 업종 4대 PAY 결제로 추가할인 적용 시 (10%＋5%) 할인 \n(최대 7,500원 할인)",
             "reason": "benefit link pending"},
            {"card_ai_run_id": RUN, "card_doc_id": DOC, "page_no": 4, "card_doc_chunk_id": "20261104_000081",
             "unresolved_ordinal": 3, "raw_txt": "• 매출 건당 5만원까지 할인", "reason": "scope pending"},
            {"card_ai_run_id": RUN, "card_doc_id": DOC, "page_no": 5, "card_doc_chunk_id": "20261104_000082",
             "unresolved_ordinal": 1,
             "raw_txt": "카드 사용등록일로부터 다음달 말일까지는 이용실적 조건없이 30만원 \n실적구간 서비스를 제공하며, 30만원이 넘는 경우 다음달부터 해당 실적\n구간 서비스가 제공됩니다.",
             "reason": "tier applicability pending"},
        ]
        queue = unresolved_queue(rows, REVIEWS)
        self.assertEqual([item["review_status"] for item in queue], [APPROVED, APPROVED, APPROVED, APPROVED, APPROVED, PENDING])
        self.assertEqual(queue[0]["target_benefit_nms"], [
            "온라인 쇼핑 10% 청구할인", "온라인 업종 4대 PAY 결제 시 5% 추가할인",
        ])
        self.assertEqual(queue[1]["target_benefit_nms"], [
            "온라인 쇼핑 10% 청구할인", "온라인 업종 4대 PAY 결제 시 5% 추가할인",
            "온라인 업종 4대 PAY 결제 시 추가할인 적용 할인", "오프라인 쇼핑 10% 청구할인",
        ])
        self.assertEqual(queue[2]["target_benefit_nms"], ["4대 주유소 주말 주유 청구할인"])
        self.assertEqual([item["review_status"] for item in queue[3:]], [APPROVED, APPROVED, PENDING])
        self.assertIn("온라인 업종 4대 PAY 결제 시 5% 추가할인", queue[3]["target_benefit_nms"])
        self.assertEqual(len(queue[5]["target_benefit_nms"]), 5)

    def test_tier_values_and_scopes_are_not_collapsed(self):
        table_ref = REVIEWS[0]["unresolved_refs"][1]["raw_txt"]
        for value in ("4천원", "8천원", "16천원", "6천원", "12천원", "24천원", "1만원", "2만원", "4만원"):
            self.assertIn(value, table_ref)
        self.assertIn("30만원 이상", table_ref)
        self.assertIn("70만원 미만", table_ref)
        self.assertIn("70만원 이상", table_ref)
        self.assertIn("120만원 미만", table_ref)
        self.assertIn("120만원 이상", table_ref)

        online = links_for_candidate(RUN, DOC, "온라인 쇼핑 10% 청구할인", REVIEWS)[0]
        pay = links_for_candidate(RUN, DOC, "온라인 업종 4대 PAY 결제 시 5% 추가할인", REVIEWS)[0]
        offline = links_for_candidate(RUN, DOC, "오프라인 쇼핑 10% 청구할인", REVIEWS)[0]
        self.assertEqual(online["review_status"], APPROVED)
        self.assertIn("4대 PAY 추가할인과 공유", online["limit_scope_note"])
        self.assertIn("별도 한도가 아니다", pay["limit_scope_note"])
        self.assertIn(PENDING, {item["review_status"] for item in links_for_candidate(
            RUN, DOC, "온라인 업종 4대 PAY 결제 시 5% 추가할인", REVIEWS)})
        page4_pay_links = links_for_candidate(RUN, DOC, "온라인 업종 4대 PAY 결제 시 추가할인 적용 할인", REVIEWS)
        self.assertEqual(page4_pay_links[0]["review_status"], APPROVED)
        self.assertEqual({item["review_status"] for item in page4_pay_links}, {APPROVED})
        self.assertIn("온라인 행과 별도", offline["limit_scope_note"])
        self.assertIn(PENDING, {item["review_status"] for item in links_for_candidate(
            RUN, DOC, "오프라인 쇼핑 10% 청구할인", REVIEWS)})
        for excluded in (
            "온라인 쇼핑 Two-in-One 결제서비스 0.3% 캐시백",
            "오프라인 쇼핑 Two-in-One 결제서비스 0.3% 캐시백",
        ):
            self.assertEqual(links_for_candidate(RUN, DOC, excluded, REVIEWS), [])
        pending_grace = [item for item in links_for_candidate(RUN, DOC, "온라인 쇼핑 10% 청구할인", REVIEWS)
                         if item["review_status"] == PENDING]
        self.assertEqual(pending_grace[0]["registration_effect"], "PENDING_SCOPE_NOTE")

    def test_review_evidence_must_match_the_cited_chunk(self):
        link = links_for_candidate(RUN, DOC, "온라인 쇼핑 10% 청구할인", REVIEWS)[0]
        sources = {
            (DOC, 3, "20261104_000080"): f"{HEADER}\n{ONLINE}\n{OFFLINE}\n{TOTAL}",
            (DOC, 2, "20261104_000079"): ONLINE_SCOPE,
        }
        located = validate_review_sources(link, DOC, sources)
        self.assertEqual(len(located), 4)
        self.assertTrue(all(item["start_pos"] >= 1 and item["end_pos"] >= item["start_pos"] for item in located))
        with self.assertRaisesRegex(ValueError, "not present"):
            validate_review_sources(link, DOC, {(DOC, 3, "20261104_000080"): "different source"})

    def test_changed_unresolved_text_falls_back_to_pending(self):
        ref = REVIEWS[0]["unresolved_refs"][1]
        queue = unresolved_queue([{
            "card_ai_run_id": RUN, "card_doc_id": DOC, "page_no": ref["page_no"],
            "card_doc_chunk_id": ref["card_doc_chunk_id"], "unresolved_ordinal": ref["ordinal"],
            "raw_txt": ref["raw_txt"] + " changed", "reason": "changed source",
        }], REVIEWS)
        self.assertEqual(queue[0]["review_status"], PENDING)
        self.assertEqual(queue[0]["target_benefit_nms"], [])

    def test_partial_review_reference_cannot_keep_approved_status(self):
        table_ref = REVIEWS[0]["unresolved_refs"][1]
        only_table = [{"card_ai_run_id": RUN, "card_doc_id": DOC, "page_no": table_ref["page_no"],
                       "card_doc_chunk_id": table_ref["card_doc_chunk_id"],
                       "unresolved_ordinal": table_ref["ordinal"], "raw_txt": table_ref["raw_txt"], "reason": ""}]
        verified = verified_reviews_for_run(RUN, only_table, REVIEWS)
        table_review = next(item for item in verified if item["review_id"] == REVIEWS[0]["review_id"])
        self.assertEqual(table_review["review_status"], PENDING)
        queue = unresolved_queue(only_table, REVIEWS)
        self.assertEqual(queue[0]["review_status"], PENDING)

    def test_registration_reuses_limit_text_and_links_without_mutating_raw_item(self):
        link = links_for_candidate(RUN, DOC, "온라인 쇼핑 10% 청구할인", REVIEWS)[0]
        page3_text = f"{HEADER}\n{ONLINE}\n{OFFLINE}\n{TOTAL}"
        page2_text = "온라인 쇼핑 10% 청구할인\n10%\n" + ONLINE_SCOPE

        class Repo:
            def __init__(self):
                self.writes = []
                self.eid = 0

            def one(self, name, **params):
                if name == "find_benefit":
                    return None
                if name == "select_review_source_chunk":
                    return {"chunk_raw_txt": page3_text if params["PAGE_NO"] == 3 else page2_text}
                raise AssertionError(name)

            def write(self, name, **params):
                self.writes.append((name, params))
                if name == "insert_review_evidence":
                    self.eid += 1
                    return [{"evidence_id": f"EV{self.eid}"}]
                if name == "insert_local_benefit":
                    return [{"card_bnft_id": "BNFT1"}]
                return []

        original_raw = {
            "bnft_nm": "온라인 쇼핑 10% 청구할인",
            "evidence": [
                {"supports": "BNFT", "quote_txt": "온라인 쇼핑 10% 청구할인"},
                {"supports": "RULE", "support_key": "R1", "quote_txt": "10%"},
            ],
        }
        candidate = {
            "card_extr_stg_id": "STG1", "card_doc_id": DOC, "stg_status": "PENDING_REVIEW", "check_cd": "LINK_REVIEW",
            "stg_raw_item": original_raw, "reviewed_unresolved_links": [link],
            "normalized": {"bnft_cd": "BNFT_X", "bnft_nm": original_raw["bnft_nm"], "bnft_type_cd": "DISCOUNT",
                           "is_common_candidate": False, "relation_list": [], "bnft_cond_expr": None,
                           "rule_list": [{"rule_key": "R1", "rule_status_cd": "DRAFT", "value_num": 10,
                                          "value_unit_cd": "PERCENT", "target_list": []}]},
        }
        evidence = [
            {"evidence_id": "EV_BASE", "quote_txt": "온라인 쇼핑 10% 청구할인", "start_pos": 1, "end_pos": 20,
             "source_txt": "온라인 쇼핑 10% 청구할인"},
            {"evidence_id": "EV_RULE", "quote_txt": "10%", "start_pos": 21, "end_pos": 23, "source_txt": "10%"},
        ]
        service = ProductBenefitService(session=object())
        service.repo = Repo()
        result = service._register(6, candidate, evidence)
        self.assertEqual(result.status, "INSERTED")
        benefit_write = next(params for name, params in service.repo.writes if name == "insert_local_benefit")
        self.assertIn("온라인 4천원 8천원 16천원", benefit_write["LIMIT_TXT"])
        self.assertIn("온라인 업종 통합", benefit_write["LIMIT_TXT"])
        self.assertIn("합계 1만원 2만원 4만원", benefit_write["LIMIT_TXT"])
        self.assertEqual(len(original_raw["evidence"]), 2)
        self.assertEqual(sum(name == "insert_review_evidence" for name, _ in service.repo.writes), 4)
        self.assertEqual(sum(name == "insert_evidence_link" for name, _ in service.repo.writes), 5)

    def test_pending_blocking_review_cannot_register(self):
        pending = dict(links_for_candidate(RUN, DOC, "온라인 쇼핑 10% 청구할인", REVIEWS)[-1])
        pending["registration_effect"] = "BLOCK"
        service = ProductBenefitService(session=object())

        class EmptyRepo:
            def __init__(self):
                self.writes = []

            def one(self, *args, **kwargs):
                raise AssertionError("pending review must stop before DB writes")

            def write(self, *args, **kwargs):
                self.writes.append(args)

        service.repo = EmptyRepo()
        candidate = {"card_extr_stg_id": "STG_GAS", "stg_raw_item": {}, "normalized": {"bnft_cd": "GAS"},
                     "reviewed_unresolved_links": [pending]}
        decision = service._register(6, candidate, [])
        self.assertEqual(decision.status, "REVIEW")
        self.assertEqual(service.repo.writes, [])


if __name__ == "__main__":
    unittest.main()
