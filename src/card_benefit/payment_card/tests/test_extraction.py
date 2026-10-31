"""AI 추출 단위 테스트. Mock LLM만 쓰며 DB와 외부 API에 접속하지 않는다.

실행(src/card_benefit 폴더에서):
    uv run python -m unittest discover -s payment_card/tests -v
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import psycopg
from pydantic import ValidationError
import pymupdf

from common.postgres_db_session import PostgresDbSession
from payment_card.db_pipeline.document_repository import MAPPER_ROOT
from payment_card.db_pipeline.extraction_schema import PageExtraction, RuleItem
from payment_card.db_pipeline.extraction_service import (
    ExtractionError,
    ExtractionService,
    LlmResponse,
    PageResult,
    StoredItem,
    amounts_in,
    check_benefit,
    check_condition,
    counts_in,
    json_number,
    locate_quote,
    make_item_key,
    merge_pages,
    rates_in,
)

# 표의 값이 줄 단위로 흩어진 ONE PICK STYLE 원문 형식을 본뜬 시험용 페이지. 실제 PDF 값이 아니다.
PAGE1 = """서비스 영역
대상 가맹점
대중교통
버스, 지하철
월 1천원
5%
캐시백
10만원
쇼핑
다이소
일 1회
/ 월 30회
월 5천원
일 1회
/ 월 10회
"""
PAGE2 = """서비스 제공 안내
대중교통 서비스는 지난달 실적 10만원 이상 시 제공
모든 서비스는 상품권 구매 시 제외
"""


def quote(text, supports, key=None, basis="TABLE_IMAGE"):
    return {"quote_txt": text, "supports": supports, "support_key": key, "link_basis": basis}


def benefit(name="대중교통", value=5, raw="5%", limit=1000, limit_raw="월 1천원", **overrides):
    item = {
        "item_key": "ANY",
        "bnft_nm": name,
        "bnft_type_cd": "CASHBACK",
        "certainty": "HIGH",
        "targets": [{"target_type_cd": "INDUSTRY", "target_nm": "버스, 지하철"}],
        "rules": [{
            "rule_key": "RATE", "calc_method_cd": "PERCENT_OF_TXN", "value_num": value, "value_raw_txt": raw,
            "value_unit_cd": "PERCENT", "payout_unit_cd": "KRW", "limit_keys": ["MONTH_KRW"],
        }],
        "limits": [{
            "limit_key": "MONTH_KRW", "period_cd": "MONTH", "cap_unit_cd": "KRW",
            "limit_num": limit, "limit_raw_txt": limit_raw,
        }],
        "evidence": [quote(raw, "RULE", "RATE"), quote(limit_raw, "LIMIT", "MONTH_KRW")],
    }
    item.update(overrides)
    return item


def condition(raw="지난달 실적 10만원 이상", scope="NAMED_BENEFITS", names=("대중교통",), **overrides):
    item = {
        "cond_key": "PREV_SPEND", "cond_type_cd": "SPEND_REQ", "cond_basis_cd": "PREV_MONTH_SPEND",
        "cond_min_amt": 100000, "cond_raw_txt": raw, "scope": scope, "target_benefit_nms": list(names),
        "evidence": [quote(raw, "COND", "PREV_SPEND", "SAME_TEXT")],
    }
    item.update(overrides)
    return item


def page_json(page_no=1, benefits=(), conditions=(), role="DETAIL"):
    return {"page_no": page_no, "page_role": role, "benefits": list(benefits), "card_conditions": list(conditions)}


def checked_page(page_no, text, payload, chunk_id=None):
    """Mock 응답을 검증까지 마친 페이지 결과로 만든다."""
    extraction = PageExtraction.model_validate(payload)
    page = PageResult(page_no, chunk_id or f"C{page_no}", text, extraction)
    seq = 0
    for item in extraction.benefits:
        seq += 1
        page.benefits.append(StoredItem(f"S{page_no}{seq}", seq, item, check_benefit(item, page)))
    for item in extraction.card_conditions:
        seq += 1
        page.conditions.append(StoredItem(f"S{page_no}{seq}", seq, item, check_condition(item, page)))
    return page


class FakeSession:
    """mapper 호출을 기록하는 세션. 트랜잭션이 실패하면 그 안의 기록을 버린다."""

    def __init__(self, card=True, doc=None, chunks=None, blocked=()):
        self.card = card
        self.doc = doc
        self.chunks = chunks or []
        self.blocked = list(blocked)
        self.rows: list[tuple[str, dict]] = []
        self.ids = 0
        self.fail_statement = None
        self.run_ids = iter(("RUN1", "RUN2", "RUN3"))

    @contextmanager
    def transaction(self):
        mark = len(self.rows)
        try:
            yield self
        except BaseException:
            del self.rows[mark:]
            raise

    def calls(self, name):
        return [parameters for statement, parameters in self.rows if statement == name]

    def select_one(self, statement_id, parameters=None):
        name = statement_id.split(".")[1]
        if name == "select_card_product":
            return {"card_id": 1} if self.card else None
        return self.doc

    def select_list(self, statement_id, parameters=None):
        name = statement_id.split(".")[1]
        if name == "select_ai_input_chunks":
            return self.chunks
        return [{"page_no": page_no} for page_no in self.blocked]

    def execute(self, statement_id, parameters=None):
        name = statement_id.split(".")[1]
        if name == self.fail_statement:
            raise psycopg.OperationalError("save failed")
        self.rows.append((name, parameters))
        if name == "insert_run":
            return [{"card_ai_run_id": next(self.run_ids)}]
        if name == "insert_stg":
            self.ids += 1
            return [{"card_extr_stg_id": f"STG{self.ids}"}]
        return None

    def execute_many(self, statement_id, parameters_list):
        if statement_id.split(".")[1] == self.fail_statement:
            raise psycopg.OperationalError("save failed")
        self.rows.extend((statement_id.split(".")[1], item) for item in parameters_list)
        return len(parameters_list)


class FakeLlm:
    """페이지 번호별 응답을 돌려주는 Mock LLM."""

    model_nm = "mock-model"

    def __init__(self, responses):
        self.responses = responses
        self.inputs = []

    def extract(self, page_input):
        self.inputs.append(page_input)
        response = self.responses[page_input.page_no]
        if isinstance(response, Exception):
            raise response
        text = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
        return LlmResponse(text, 100, 50)


class ServiceCase(unittest.TestCase):
    """임시 PDF로 실행 흐름을 시험한다."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / "hana_all"
        self.root.mkdir()
        with pymupdf.open() as document:
            document.new_page().insert_text((72, 72), "page one")
            document.new_page().insert_text((72, 72), "page two")
            content = document.tobytes()
        (self.root / "a.pdf").write_bytes(content)
        self.doc = {"card_doc_id": "D1", "doc_file_nm": "hana_all/a.pdf", "doc_sha256": hashlib.sha256(content).hexdigest()}
        self.chunks = [
            {"card_doc_id": "D1", "page_no": 1, "card_doc_chunk_id": "C1", "chunk_raw_txt": PAGE1},
            {"card_doc_id": "D1", "page_no": 2, "card_doc_chunk_id": "C2", "chunk_raw_txt": PAGE2},
        ]

    def service(self, responses, **options):
        session = FakeSession(doc=self.doc, chunks=self.chunks, **options)
        return session, ExtractionService(session, FakeLlm(responses), data_root=self.root)


class HelperTests(unittest.TestCase):
    def test_amounts_counts_rates_are_read_from_korean_text(self):
        self.assertEqual(amounts_in("월 1만 5천원, 100원, 10만원"), {15000, 100, 100000})
        self.assertEqual(amounts_in("1,000원"), {1000})
        self.assertEqual(counts_in("일 1회 / 월 30회"), {1, 30})
        self.assertEqual(rates_in("1.5% 와 50%"), {Decimal("1.5"), Decimal("50")})

    def test_quote_positions_are_one_based_and_inclusive(self):
        self.assertEqual(locate_quote("abc def", "def"), (5, 7))

    def test_quote_is_found_across_line_breaks_with_source_positions(self):
        text = "가\n버스,  지하철\n나"
        start, end = locate_quote(text, "버스, 지하철")
        self.assertEqual(text[start - 1:end], "버스,  지하철")

    def test_missing_quote_has_no_position(self):
        self.assertIsNone(locate_quote("abc", "xyz"))
        self.assertIsNone(locate_quote("abc", ""))

    def test_json_number_is_a_number_not_a_string(self):
        self.assertEqual(json.dumps([json_number(Decimal("0.5")), json_number(Decimal("5")), json_number(3000)]), "[0.5, 5, 3000]")
        self.assertIsNone(json_number(None))

    def test_item_key_is_stable_and_ignores_spacing(self):
        self.assertEqual(make_item_key("BNFT", "ONE MORE 대중교통"), make_item_key("BNFT", "ONEMORE  대중교통"))
        self.assertRegex(make_item_key("BNFT", "한글"), r"^[A-Za-z0-9_.:-]{1,40}$")


class SchemaTests(unittest.TestCase):
    def test_valid_response_is_parsed(self):
        page = PageExtraction.model_validate(page_json(benefits=[benefit(value=0.5, raw="0.5%")]))
        self.assertEqual(page.benefits[0].rules[0].value_num, Decimal("0.5"))

    def test_amount_and_count_must_be_integers(self):
        with self.assertRaises(ValidationError):
            PageExtraction.model_validate(page_json(benefits=[benefit(limit=1000.5)]))

    def test_unknown_field_and_code_are_rejected(self):
        for overrides in ({"card_id": 1}, {"bnft_type_cd": "NEW"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                PageExtraction.model_validate(page_json(benefits=[benefit(**overrides)]))

    def test_llm_schema_shows_decimal_as_number(self):
        self.assertIn({"type": "number"}, RuleItem.model_json_schema()["properties"]["value_num"]["anyOf"])


class CheckTests(unittest.TestCase):
    def merged(self, *pages):
        return merge_pages(list(pages))

    def test_normal_table_item_has_correct_values_but_needs_link_review(self):
        benefits, _ = self.merged(checked_page(1, PAGE1, page_json(benefits=[benefit()])))
        self.assertEqual(benefits[0].check.value_check_cd, "OK")
        self.assertEqual(benefits[0].check.link_check_cd, "NEEDS_REVIEW")
        self.assertEqual(benefits[0].sql_check_cd, "LINK_REVIEW")

    def test_text_sentence_can_confirm_link(self):
        text = "대중교통 5% 캐시백 월 1천원"
        item = benefit(evidence=[quote(text, "RULE", "RATE", "SAME_TEXT"), quote(text, "LIMIT", "MONTH_KRW", "SAME_TEXT")])
        benefits, _ = self.merged(checked_page(1, text + " 버스, 지하철", page_json(benefits=[item])))
        self.assertEqual(benefits[0].sql_check_cd, "OK")

    def test_claimed_same_text_without_benefit_name_is_not_trusted(self):
        item = benefit(evidence=[quote("5%", "RULE", "RATE", "SAME_TEXT"), quote("월 1천원", "LIMIT", "MONTH_KRW", "SAME_TEXT")])
        benefits, _ = self.merged(checked_page(1, PAGE1, page_json(benefits=[item])))
        self.assertEqual(benefits[0].sql_check_cd, "LINK_REVIEW")

    def test_table_number_on_wrong_benefit_cannot_pass_as_ok(self):
        # 월 10회는 쇼핑 표의 값이지만 대중교통에 잘못 연결했다. 값은 원문에 있어 값 검증은 통과한다.
        item = benefit(limits=[{
            "limit_key": "MONTH_COUNT", "period_cd": "MONTH", "cap_unit_cd": "COUNT", "limit_num": 10, "limit_raw_txt": "월 10회",
        }], evidence=[quote("5%", "RULE", "RATE"), quote("/ 월 10회", "LIMIT", "MONTH_COUNT")])
        item["rules"][0]["limit_keys"] = ["MONTH_COUNT"]
        benefits, _ = self.merged(checked_page(1, PAGE1, page_json(benefits=[item])))
        self.assertEqual(benefits[0].check.value_check_cd, "OK")
        self.assertEqual(benefits[0].check.link_check_cd, "NEEDS_REVIEW")
        self.assertEqual(benefits[0].sql_check_cd, "LINK_REVIEW")

    def test_rate_not_in_source_is_rejected(self):
        item = benefit(value=7, raw="7%", evidence=[quote("7%", "RULE", "RATE"), quote("월 1천원", "LIMIT", "MONTH_KRW")])
        benefits, _ = self.merged(checked_page(1, PAGE1, page_json(benefits=[item])))
        self.assertEqual(benefits[0].sql_check_cd, "QUOTE_NOT_FOUND")

    def test_number_different_from_raw_text_is_rejected(self):
        benefits, _ = self.merged(checked_page(1, PAGE1, page_json(benefits=[benefit(value=7, raw="5%")])))
        self.assertEqual(benefits[0].sql_check_cd, "VALUE_PARSE_DIFF")

    def test_value_outside_quote_is_rejected(self):
        item = benefit(evidence=[quote("캐시백", "RULE", "RATE"), quote("월 1천원", "LIMIT", "MONTH_KRW")])
        benefits, _ = self.merged(checked_page(1, PAGE1, page_json(benefits=[item])))
        self.assertEqual(benefits[0].sql_check_cd, "VALUE_NOT_IN_QUOTE")

    def test_value_without_evidence_is_rejected(self):
        benefits, _ = self.merged(checked_page(1, PAGE1, page_json(benefits=[benefit(evidence=[])])))
        self.assertEqual(benefits[0].sql_check_cd, "NO_EVIDENCE")

    def test_target_not_in_source_is_rejected(self):
        item = benefit(targets=[{"target_type_cd": "MERCHANT", "target_nm": "없는 가맹점"}])
        benefits, _ = self.merged(checked_page(1, PAGE1, page_json(benefits=[item])))
        self.assertEqual(benefits[0].sql_check_cd, "QUOTE_NOT_FOUND")

    def test_evidence_positions_are_kept_per_quote(self):
        page = checked_page(1, PAGE1, page_json(benefits=[benefit()]))
        evidence = page.benefits[0].check.evidence
        self.assertEqual(len(evidence), 2)
        for item in evidence:
            self.assertEqual(PAGE1[item.start_pos - 1:item.end_pos], item.quote_txt)

    def test_low_certainty_needs_review(self):
        text = "대중교통 5% 캐시백 월 1천원 버스, 지하철"
        item = benefit(certainty="LOW", evidence=[
            quote("대중교통 5%", "RULE", "RATE", "SAME_TEXT"), quote("대중교통 5% 캐시백 월 1천원", "LIMIT", "MONTH_KRW", "SAME_TEXT"),
        ])
        benefits, _ = self.merged(checked_page(1, text, page_json(benefits=[item])))
        self.assertEqual(benefits[0].sql_check_cd, "LINK_REVIEW")


class MergeTests(unittest.TestCase):
    def test_condition_on_other_page_is_linked_to_benefit(self):
        raw = "지난달 실적 10만원 이상"
        benefits, conditions = merge_pages([
            checked_page(1, PAGE1, page_json(1, benefits=[benefit()])),
            checked_page(2, PAGE2, page_json(2, conditions=[condition(raw)])),
        ])
        key = benefits[0].merge.item_key
        self.assertEqual(conditions[0].applies_to_item_keys, [key])
        self.assertEqual(conditions[0].sql_check_cd, "OK")
        atoms = benefits[0].normalized["bnft_cond_expr"]["branches"][0]["atoms"]
        self.assertEqual((atoms[0]["cond_min_amt"], atoms[0]["cond_basis_cd"]), (100000, "PREV_MONTH_SPEND"))

    def test_all_benefit_condition_stays_card_level(self):
        raw = "모든 서비스는 상품권 구매 시 제외"
        item = condition(raw, "ALL_BENEFITS", (), cond_type_cd="BNFT_EXCL", cond_basis_cd=None, cond_min_amt=None,
                         excl_raw_txt="상품권 구매")
        benefits, conditions = merge_pages([
            checked_page(1, PAGE1, page_json(1, benefits=[benefit()])),
            checked_page(2, PAGE2, page_json(2, conditions=[item])),
        ])
        self.assertEqual((conditions[0].scope_cd, conditions[0].applies_to_item_keys), ("ALL_BENEFITS", []))
        self.assertIsNone(benefits[0].normalized["bnft_cond_expr"])

    def test_condition_for_unknown_benefit_is_unresolved(self):
        _, conditions = merge_pages([checked_page(2, PAGE2, page_json(2, conditions=[
            condition("지난달 실적 10만원 이상", names=("없는 혜택",)),
        ]))])
        self.assertEqual((conditions[0].sql_check_cd, conditions[0].scope_cd), ("SCOPE_UNRESOLVED", "UNRESOLVED"))

    def test_exact_name_wins_over_partial_name(self):
        benefits, conditions = merge_pages([
            checked_page(1, PAGE1, page_json(1, benefits=[benefit("ONE PICK"), benefit("ONE PICK STYLE")])),
            checked_page(2, PAGE2, page_json(2, conditions=[condition("지난달 실적 10만원 이상", names=("ONE PICK",))])),
        ])
        exact = next(item for item in benefits if item.normalized["bnft_nm"] == "ONE PICK")
        self.assertEqual(conditions[0].applies_to_item_keys, [exact.merge.item_key])

    def test_ambiguous_partial_name_is_unresolved(self):
        _, conditions = merge_pages([
            checked_page(1, PAGE1, page_json(1, benefits=[benefit("ONE PICK 편의점"), benefit("ONE PICK 카페")])),
            checked_page(2, PAGE2, page_json(2, conditions=[condition("지난달 실적 10만원 이상", names=("ONE PICK",))])),
        ])
        self.assertEqual(conditions[0].sql_check_cd, "SCOPE_UNRESOLVED")

    def test_same_benefit_on_two_pages_merges_with_all_sources(self):
        benefits, _ = merge_pages([
            checked_page(1, PAGE1, page_json(1, benefits=[benefit()], role="SUMMARY")),
            checked_page(2, PAGE1, page_json(2, benefits=[benefit("대중교통 ")])),
        ])
        self.assertEqual(len(benefits), 1)
        self.assertEqual(benefits[0].merge.source_pages, [1, 2])
        self.assertEqual(benefits[0].merge.source_refs[0].page_no, 2)     # 상세 페이지가 대표 행이다
        self.assertEqual(benefits[0].merge.conflicts, [])
        self.assertEqual(len(benefits[0].check.evidence), 4)              # 위치별 근거를 모두 보존한다

    def test_conflicting_values_between_pages_are_not_resolved(self):
        benefits, _ = merge_pages([
            checked_page(1, PAGE1, page_json(1, benefits=[benefit()])),
            checked_page(2, PAGE1, page_json(2, benefits=[benefit(limit=5000, limit_raw="월 5천원", evidence=[
                quote("5%", "RULE", "RATE"), quote("월 5천원", "LIMIT", "MONTH_KRW"),
            ])])),
        ])
        self.assertEqual(benefits[0].sql_check_cd, "MERGE_CONFLICT")
        self.assertTrue(benefits[0].merge.conflicts)

    def test_equal_values_do_not_become_shared_limit(self):
        benefits, _ = merge_pages([checked_page(1, PAGE1, page_json(1, benefits=[benefit("대중교통"), benefit("쇼핑")]))])
        self.assertEqual({item["pool_scope_cd"] for bnft in benefits for item in bnft.normalized["limit_list"]}, {"BENEFIT"})

    def test_explicit_shared_limit_is_marked(self):
        item = benefit()
        item["limits"][0]["shared_scope_txt"] = "대상 가맹점 합산"
        benefits, _ = merge_pages([checked_page(1, PAGE1, page_json(1, benefits=[item]))])
        self.assertEqual(benefits[0].normalized["limit_list"][0]["pool_scope_cd"], "BENEFIT_GROUP")

    def test_relation_across_pages_uses_benefit_key(self):
        relation = {"relation_key": "REL1", "rel_type_cd": "MUTUALLY_EXCLUSIVE", "to_benefit_nm": "쇼핑"}
        benefits, _ = merge_pages([
            checked_page(1, PAGE1, page_json(1, benefits=[benefit(relations=[relation])])),
            checked_page(2, PAGE1, page_json(2, benefits=[benefit("쇼핑")])),
        ])
        source = next(item for item in benefits if item.normalized["bnft_nm"] == "대중교통")
        target = next(item for item in benefits if item.normalized["bnft_nm"] == "쇼핑")
        self.assertEqual(source.normalized["relation_list"][0]["to_bnft_id"], target.merge.item_key)

    def test_relation_to_unknown_benefit_is_unresolved(self):
        relation = {"relation_key": "REL1", "rel_type_cd": "OVERRIDES", "to_benefit_nm": "없는 혜택"}
        benefits, _ = merge_pages([checked_page(1, PAGE1, page_json(1, benefits=[benefit(relations=[relation])]))])
        self.assertEqual(benefits[0].sql_check_cd, "SCOPE_UNRESOLVED")


class NormalizationTests(unittest.TestCase):
    def normalized(self, item):
        return merge_pages([checked_page(1, PAGE1, page_json(1, benefits=[item]))])[0][0]

    def test_rule_matches_v6_contract_shape(self):
        rule = self.normalized(benefit()).normalized["rule_list"][0]
        self.assertEqual(rule["predicate_state_cd"], "PENDING_REVIEW")
        self.assertIsNone(rule["cond_expr"])
        self.assertEqual(rule["pool_refs"], [{"pool_id": "MONTH_KRW", "pool_role_cd": "CONSUME"}])
        self.assertEqual(rule["value_num"], 5)
        self.assertIsInstance(rule["value_num"], int)

    def test_missing_condition_is_never_marked_unconditional(self):
        result = self.normalized(benefit(no_condition_stated=True))
        self.assertEqual(result.normalized["rule_list"][0]["predicate_state_cd"], "PENDING_REVIEW")

    def test_contract_failures_are_reported(self):
        no_basis = benefit(conditions=[{**condition("10만원"), "cond_basis_cd": None}])
        bad_range = benefit(conditions=[{**condition("10만원"), "cond_max_amt_excl": 100000}])
        no_limit = benefit(limit=None)
        unknown_method = benefit()
        unknown_method["rules"][0]["calc_method_cd"] = "UNKNOWN"
        bad_pool = benefit()
        bad_pool["rules"][0]["limit_keys"] = ["NOT_DEFINED"]
        for item in (no_basis, bad_range, no_limit, unknown_method, bad_pool):
            with self.subTest(item=item["rules"][0]["calc_method_cd"]):
                self.assertEqual(self.normalized(item).sql_check_cd, "CONTRACT_INVALID")

    def test_decimal_rule_stays_numeric_in_json(self):
        text = "대중교통 0.5% 월 1천원 버스, 지하철"
        item = benefit(value=0.5, raw="0.5%", evidence=[
            quote("0.5%", "RULE", "RATE"), quote("월 1천원", "LIMIT", "MONTH_KRW"),
        ])
        value = merge_pages([checked_page(1, text, page_json(1, benefits=[item]))])[0][0].normalized["rule_list"][0]["value_num"]
        self.assertEqual(json.loads(json.dumps(value)), 0.5)


class RunTests(ServiceCase):
    RESPONSES = {
        1: page_json(1, benefits=[benefit()]),
        2: page_json(2, conditions=[condition("지난달 실적 10만원 이상")]),
    }

    def test_run_stores_history_raw_items_and_merge(self):
        session, service = self.service(self.RESPONSES)
        result = service.run("D1", 1)
        self.assertEqual((result.status, result.pages_ok, result.merged), ("SUCCEEDED", 2, True))
        calls = session.calls("insert_call")
        self.assertEqual([call["CALL_STATUS"] for call in calls], ["SUCCEEDED", "SUCCEEDED"])
        self.assertTrue(calls[0]["CALL_RESP_RAW"])
        self.assertEqual([row["STG_KIND_CD"] for row in session.calls("insert_stg")], ["BENEFIT", "CONDITION"])
        self.assertEqual(len(session.calls("insert_evidence")), 3)
        merges = session.calls("update_stg_merge")
        self.assertEqual(merges[0]["STG_SQL_CHECK_CD"], "LINK_REVIEW")
        self.assertEqual(merges[1]["STG_PARENT_CARD_EXTR_STG_ID"], "STG1")   # 2쪽 조건이 1쪽 혜택을 가리킨다
        self.assertEqual(session.calls("finish_run")[0]["RUN_STATUS"], "SUCCEEDED")

    def test_input_has_page_text_png_image_and_run_param(self):
        session, service = self.service(self.RESPONSES)
        service.run("D1", 1)
        page_input = service.llm_client.inputs[0]
        self.assertEqual(page_input.page_text, PAGE1)
        self.assertTrue(page_input.image_png.startswith(b"\x89PNG"))
        self.assertEqual(session.calls("insert_call")[0]["CALL_INPUT_SHA256"], page_input.input_sha256)
        run_param = session.calls("insert_run")[0]["RUN_PARAM"].obj
        self.assertEqual((run_param["input_mode"], run_param["split_rule_ver"]), ("TEXT_IMAGE", "PAGE_V1"))

    def test_missing_product_stops_before_llm(self):
        session, service = self.service(self.RESPONSES)
        session.card = False
        with self.assertRaisesRegex(ExtractionError, "card_product"):
            service.run("D1", 1)
        self.assertEqual(service.llm_client.inputs, [])
        self.assertEqual(session.rows, [])

    def test_no_input_pages_stops_before_llm(self):
        session, service = self.service(self.RESPONSES)
        session.chunks = []
        with self.assertRaisesRegex(ExtractionError, "입력"):
            service.run("D1", 1)
        self.assertEqual(service.llm_client.inputs, [])

    def test_changed_local_pdf_stops_before_llm(self):
        session, service = self.service(self.RESPONSES)
        (self.root / "a.pdf").write_bytes(b"%PDF-changed")
        with self.assertRaisesRegex(ExtractionError, "HASH_MISMATCH"):
            service.run("D1", 1)
        self.assertEqual(session.rows, [])

    def test_blocked_pages_are_recorded(self):
        session, service = self.service(self.RESPONSES, blocked=[3])
        result = service.run("D1", 1)
        self.assertIn("[3]", result.note)
        self.assertEqual((result.status, result.merged), ("PARTIAL", True))
        self.assertEqual(session.calls("finish_run")[0]["RUN_STATUS"], "PARTIAL")

    def test_selected_page_is_partial_and_preserves_call(self):
        session, service = self.service(self.RESPONSES)
        result = service.run("D1", 1, page_numbers={1})
        self.assertEqual([p.page_no for p in service.llm_client.inputs], [1])
        self.assertEqual(result.status, "PARTIAL")
        self.assertEqual(len(session.calls("insert_call")), 1)
        self.assertIn("[2]", result.note)

    def test_second_page_runs_separately(self):
        session, service = self.service(self.RESPONSES)
        first = service.run("D1", 1, page_numbers={1})
        second = service.run("D1", 1, page_numbers={2})
        self.assertNotEqual(first.card_ai_run_id, second.card_ai_run_id)
        self.assertEqual([p.page_no for p in service.llm_client.inputs], [1, 2])
        self.assertEqual(len(session.calls("insert_call")), 2)

    def test_invalid_json_is_kept_as_parse_error_without_merge(self):
        session, service = self.service({1: "not json", 2: self.RESPONSES[2]})
        result = service.run("D1", 1)
        call = session.calls("insert_call")[0]
        self.assertEqual((call["CALL_STATUS"], call["CALL_RESP_RAW"]), ("PARSE_ERROR", "not json"))
        self.assertEqual((result.status, result.merged), ("PARTIAL", False))
        self.assertEqual(session.calls("update_stg_merge"), [])

    def test_wrong_page_number_is_parse_error(self):
        session, service = self.service({1: page_json(9), 2: self.RESPONSES[2]})
        service.run("D1", 1)
        self.assertEqual(session.calls("insert_call")[0]["CALL_STATUS"], "PARSE_ERROR")

    def test_llm_error_keeps_only_error_type(self):
        session, service = self.service({1: RuntimeError("secret-in-message"), 2: self.RESPONSES[2]})
        service.run("D1", 1)
        call = session.calls("insert_call")[0]
        self.assertEqual((call["CALL_STATUS"], call["CALL_ERROR_MSG"]), ("FAILED", "RuntimeError"))

    def test_all_pages_failed_is_failed_run(self):
        session, service = self.service({1: "x", 2: "x"})
        self.assertEqual(service.run("D1", 1).status, "FAILED")

    def test_retry_increases_call_seq(self):
        session, service = self.service({1: "x", 2: self.RESPONSES[2]})
        service.max_attempts = 2
        service.run("D1", 1)
        self.assertEqual([call["CALL_SEQ"] for call in session.calls("insert_call") if call["PAGE_NO"] == 1], [1, 2])

    def test_page_save_failure_rolls_back_items_but_keeps_call(self):
        session, service = self.service(self.RESPONSES)
        session.fail_statement = "insert_evidence"
        result = service.run("D1", 1)
        self.assertEqual(session.calls("insert_stg"), [])
        self.assertEqual(len(session.calls("insert_call")), 2)               # 비용이 든 응답은 남는다
        self.assertEqual((result.status, result.merged), ("FAILED", False))

    def test_merge_save_failure_rolls_back_merge_but_keeps_pages(self):
        session, service = self.service(self.RESPONSES)
        session.fail_statement = "update_stg_merge"
        result = service.run("D1", 1)
        self.assertEqual(len(session.calls("insert_stg")), 2)
        self.assertEqual(session.calls("update_stg_merge"), [])
        self.assertEqual((result.status, result.merged), ("PARTIAL", False))
        self.assertIn("통합", result.note)

    def test_unexpected_error_does_not_leave_run_running(self):
        session, service = self.service(self.RESPONSES)
        with patch("payment_card.db_pipeline.extraction_service.merge_pages", side_effect=KeyError("x")):
            with self.assertRaises(KeyError):
                service.run("D1", 1)
        self.assertEqual(session.calls("finish_run")[0]["RUN_STATUS"], "FAILED")

    def test_rerun_uses_new_run_id_and_keeps_previous_rows(self):
        session, service = self.service(self.RESPONSES)
        first = service.run("D1", 1)
        before = len(session.rows)
        second = service.run("D1", 1)
        self.assertEqual((first.card_ai_run_id, second.card_ai_run_id), ("RUN1", "RUN2"))
        self.assertEqual({row["CARD_AI_RUN_ID"] for row in session.calls("insert_stg")}, {"RUN1", "RUN2"})
        self.assertGreater(len(session.rows), before)


class MapperTests(unittest.TestCase):
    def test_every_statement_is_loaded_and_names_the_schema(self):
        session = PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")
        names = [name for name in session.mappers["extraction_repository"].available_queries if not name.endswith("_cursor")]
        self.assertEqual(len(names), 20)
        for name in names:
            self.assertIn("db_pipeline.", session._query(f"extraction_repository.{name}").sql, name)
        self.assertEqual(session.database_manager._pools, {})


if __name__ == "__main__":
    unittest.main()
