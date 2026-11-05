"""TERMS(할인 제공 유의사항) 등록기의 원문 위치 검증과 GraphRAG 첨부. DB를 쓰지 않는다(2026-11-05)."""
import json

import pytest

from payment_card.db_pipeline.terms_register import (
    TermsError, build_terms, locate, make_span, split_list_entries, strip_evidence_ids, terms_item_cd,
)
from payment_card.db_pipeline_origin_search.card_graphrag import attach_terms, merge_terms_evidence

LIST = "• 할인 제외 : 무이자할부금액, 정부지원금(보육료, 유치원보조비 등), 아파트 관리\n비, 공공요금(공과금)*, 매출취소금액"
FOOT = "* 공공요금(공과금) 내역 : 4대보험, 전기요금"
# 각주는 목록과 떨어져 있다(사이에 다른 문장). 서로 합치지 않고 각자 위치를 가져야 한다.
PAGE = f"머리말\n{LIST}\n• 다른 문장입니다.\n{FOOT}\n• 다른 프로모션과 중복 적용 불가"


def chunks():
    return {2: [{"card_doc_id": "D1", "page_no": 2, "card_doc_chunk_id": "C1", "chunk_raw_txt": PAGE}]}


def seed(**extra):
    base = {"terms_key": "T1", "terms_kind_cd": "BNFT_EXCL", "item_nm": "할인 제외",
            "scope": {"scope_cd": "ALL_BENEFITS", "item_ids": []}, "provenance_stg_ids": ["S1"],
            "source": {"page_no": 2, "txt": LIST}, "entries": {"mode": "LIST_AFTER_PREFIX", "prefix": "할인 제외 :"},
            "footnotes": [{"footnote_key": "f1", "marker": "*", "page_no": 2, "txt": FOOT, "locate": "FIRST_AFTER_SOURCE"}]}
    base.update(extra)
    return base


def test_list_split_keeps_parentheses_and_original_text():
    pieces = split_list_entries(LIST, "할인 제외 :")
    assert [p for p, _ in pieces] == ["무이자할부금액", "정부지원금(보육료, 유치원보조비 등)", "아파트 관리\n비", "공공요금(공과금)*", "매출취소금액"]
    for piece, offset in pieces:
        assert LIST[offset:offset + len(piece)] == piece      # 원문 그대로, 위치 일치


def test_every_span_is_verified_at_its_own_position_and_footnote_is_separate():
    data, source, entries, footnotes = build_terms(seed(), chunks())
    for span in [source, *entries, *footnotes]:
        assert PAGE[span.start_pos - 1:span.end_pos] == span.txt
    assert footnotes[0].start_pos > source.end_pos             # 각주는 본문 뒤 별도 위치
    assert FOOT not in source.txt                              # 떨어진 원문을 한 문자열로 합치지 않음
    assert data["source"]["txt"] == LIST and data["footnotes"][0]["txt"] == FOOT
    assert [e["entry_key"] for e in data["entries"]] == ["e01", "e02", "e03", "e04", "e05"]
    assert all(e["end_pos"] - e["start_pos"] + 1 == len(e["txt"]) for e in [data["source"], *data["entries"], *data["footnotes"]])


def test_text_not_in_original_or_ambiguous_is_rejected():
    with pytest.raises(TermsError):
        build_terms(seed(source={"page_no": 2, "txt": LIST.replace("무이자할부금액", "무이자 할부금액")}), chunks())
    doubled = {2: [{**chunks()[2][0], "chunk_raw_txt": PAGE + "\n" + LIST}]}
    with pytest.raises(TermsError):
        build_terms(seed(), doubled)                           # 같은 본문이 두 곳 → 위치를 정할 수 없음
    with pytest.raises(TermsError):
        build_terms(seed(footnotes=[{"footnote_key": "f1", "marker": "*", "page_no": 2, "txt": "없는 각주", "locate": "UNIQUE"}]), chunks())
    with pytest.raises(TermsError):
        make_span(chunks()[2][0], 0, "다른 글자")


def test_footnote_after_source_picks_the_one_following_its_list():
    page = f"{LIST}\n{FOOT}\n• 전월 실적 제외 : 무이자할부금액, 공공요금(공과금)*\n{FOOT}"
    rows = {2: [{"card_doc_id": "D1", "page_no": 2, "card_doc_chunk_id": "C1", "chunk_raw_txt": page}]}
    _, source, _, footnotes = build_terms(seed(), rows)
    assert footnotes[0].start_pos == source.end_pos + 2        # 바로 뒤의 각주(두 번째 같은 각주가 아님)
    with pytest.raises(TermsError):
        locate(rows[2], FOOT)                                   # 위치 지정 없이는 모호


def test_scope_rules():
    with pytest.raises(TermsError):
        build_terms(seed(scope={"scope_cd": "NAMED_ITEMS", "item_ids": []}), chunks())
    with pytest.raises(TermsError):
        build_terms(seed(scope={"scope_cd": "ALL_BENEFITS", "item_ids": ["X"]}), chunks())
    with pytest.raises(TermsError):
        build_terms(seed(scope={"scope_cd": "EVERYTHING", "item_ids": []}), chunks())


def test_item_cd_is_stable_and_evidence_ids_do_not_break_idempotency():
    assert terms_item_cd("D1", "BNFT_EXCL", LIST) == terms_item_cd("D1", "BNFT_EXCL", LIST.replace("\n", " "))
    assert terms_item_cd("D1", "BNFT_EXCL", LIST) != terms_item_cd("D1", "SPEND_EXCL", LIST)
    data, *_ = build_terms(seed(), chunks())
    stored = json.loads(json.dumps(data))
    stored["source"]["evidence_id"] = "E1"
    stored["footnotes"][0]["evidence_id"] = "E2"
    assert strip_evidence_ids(stored) == strip_evidence_ids(data)


def detail(card_id, item_id, spend=False):
    conditions = [{"atom": {"source_json": json.dumps({"cond_type_cd": "SPEND_REQ"})}}] if spend else []
    return {"entity_ref": f"card_product_item:{card_id}:{item_id}", "conditions": conditions,
            "context": {"benefit": {"name": item_id, "source_json": json.dumps({"item_type_cd": "BENEFIT"})}}}


def terms_row(card_id, item_id, scope_cd, item_ids=(), evidence=("E1",)):
    return {"card_id": card_id, "card_product_item_id": item_id, "item_nm": "할인 제외", "product_nm": "카드",
            "item_data": {"terms_kind_cd": "BNFT_EXCL", "scope": {"scope_cd": scope_cd, "item_ids": list(item_ids)},
                          "source": {"txt": LIST}, "footnotes": [{"txt": FOOT}]},
            "evidence": [{"evidence_id": e, "page_no": 2, "quote_txt": LIST, "approval_status_cd": "PENDING"} for e in evidence]}


def test_attach_terms_follows_scope_and_card():
    details = [detail(42, "B1", spend=True), detail(42, "B2"), detail(7, "B9")]
    rows = [terms_row(42, "T1", "ALL_BENEFITS"), terms_row(42, "T2", "PERFORMANCE", evidence=("E2",)),
            terms_row(42, "T3", "NAMED_ITEMS", ["B2"], evidence=("E3",)), terms_row(99, "T4", "ALL_BENEFITS", evidence=("E4",))]
    terms, evidence = attach_terms(details, rows)
    by_id = {t["terms_id"]: t["benefit_ids"] for t in terms}
    assert by_id == {"card_product_item:42:T1": ["card_product_item:42:B1", "card_product_item:42:B2"],
                     "card_product_item:42:T2": ["card_product_item:42:B1"],          # 전월 실적 조건이 있는 혜택만
                     "card_product_item:42:T3": ["card_product_item:42:B2"]}          # 지정한 혜택만, 다른 카드 TERMS 없음
    assert terms[0]["text"] == LIST and terms[0]["footnotes"] == [FOOT]
    assert {e["evidence_id"] for e in evidence} == {"E1", "E2", "E3"}


def test_merge_terms_evidence_adds_scope_without_duplicates():
    context = [{"evidence_id": "E1", "benefit_ids": ["card_product_item:42:B1"]}]
    merge_terms_evidence(context, [{"evidence_id": "E1", "benefit_ids": ["card_product_item:42:B2"]},
                                   {"evidence_id": "E5", "benefit_ids": ["card_product_item:42:B1"]}])
    assert context == [{"evidence_id": "E1", "benefit_ids": ["card_product_item:42:B1", "card_product_item:42:B2"]},
                       {"evidence_id": "E5", "benefit_ids": ["card_product_item:42:B1"]}]


# region OCR 정정 표기·적용 대상 코드·중복 표시(2026-11-05)
OCR_LIST = "• 할인 제외 : 바우저 이용금액, 내/SH 공공임대료, 매출취소금액"
OCR_PAGE = f"머리말\n{OCR_LIST}\n끝"


def test_ocr_fixes_keep_original_and_store_reviewed_text_per_span():
    rows = {2: [{"card_doc_id": "D1", "page_no": 2, "card_doc_chunk_id": "C1", "chunk_raw_txt": OCR_PAGE}]}
    fixes = [{"from": "바우저", "to": "바우처"}, {"from": "내/SH", "to": "LH/SH"}]
    data, source, entries, _ = build_terms(seed(source={"page_no": 2, "txt": OCR_LIST, "ocr_fixes": fixes,
                                                        "reviewed_txt": "• 할인 제외 : 바우처 이용금액, LH/SH 공공임대료, 매출취소금액"},
                                                footnotes=[]), rows)
    assert data["source"]["txt"] == OCR_LIST == source.txt                        # 원문은 그대로(위치 검증도 원문 기준)
    assert data["source"]["reviewed_txt"] == "• 할인 제외 : 바우처 이용금액, LH/SH 공공임대료, 매출취소금액"
    assert [e.get("reviewed_txt") for e in data["entries"]] == ["바우처 이용금액", "LH/SH 공공임대료", None]
    assert terms_item_cd("D1", "BNFT_EXCL", source.txt) == terms_item_cd("D1", "BNFT_EXCL", OCR_LIST)   # 코드는 원문 기준


@pytest.mark.parametrize("fixes, reviewed", [
    ([{"from": "없는말", "to": "x"}], None),                                       # 원문에 없음
    ([{"from": "금액", "to": "x"}], None),                                         # 여러 번 나옴(위치 모호)
    ([{"from": "바우저", "to": "바우저"}], None),                                   # 같은 값
    ([{"from": "바우저", "to": "바우처"}], "틀린 검토 표기"),                        # reviewed_txt가 정정 결과와 다름
    ([{"from": "바우저 이용", "to": "a"}, {"from": "이용금액,", "to": "b"}], None),  # 겹침
    ([{"from": "금액, 내", "to": "금액, LH"}], None),                              # 목록 항목 경계에 걸침
])
def test_invalid_ocr_fixes_are_rejected(fixes, reviewed):
    rows = {2: [{"card_doc_id": "D1", "page_no": 2, "card_doc_chunk_id": "C1", "chunk_raw_txt": OCR_PAGE}]}
    src = {"page_no": 2, "txt": OCR_LIST, "ocr_fixes": fixes}
    if reviewed:
        src["reviewed_txt"] = reviewed
    with pytest.raises(TermsError):
        build_terms(seed(source=src, footnotes=[]), rows)


class Cur:
    def __init__(self, rows):
        self.rows, self.last = rows, None

    def execute(self, sql, params):
        self.last = self.rows.get(params)
        return self

    def fetchone(self):
        return self.last


def test_named_scope_by_item_cd_resolves_only_registered_benefits():
    from payment_card.db_pipeline.terms_register import resolve_scope
    cur = Cur({(42, "BNFT_A"): {"card_product_item_id": "I1"}, (42, "BNFT_B"): {"card_product_item_id": "I2"}})
    named = seed(scope={"scope_cd": "NAMED_ITEMS", "item_ids": [], "item_cds": ["BNFT_A", "BNFT_B"]})
    assert resolve_scope(cur, 42, named)["scope"]["item_ids"] == ["I1", "I2"]
    with pytest.raises(TermsError):                                                # 하나라도 미등록이면 등록하지 않음
        resolve_scope(cur, 42, seed(scope={"scope_cd": "NAMED_ITEMS", "item_ids": [], "item_cds": ["BNFT_A", "BNFT_X"]}))
    with pytest.raises(TermsError):                                                # 다른 카드의 같은 코드는 쓰지 않음
        resolve_scope(cur, 7, named)


def cond_detail(card_id, item_id, raw_texts):
    conditions = [{"atom": {"source_json": json.dumps({"cond_type_cd": "GRACE", "cond_raw_txt": t})}} for t in raw_texts]
    return {**detail(card_id, item_id), "conditions": conditions}


def test_terms_text_already_in_benefit_conditions_is_not_repeated_but_evidence_stays():
    grace = "• \u200c '특별할인' 서비스는 최초발급*받은 카드 수령일 기준\n다음 달 말일까지 최저 실적 구간 서비스를 제공합니다."
    cond = "'특별할인' 서비스는 최초발급*받은 카드 수령일 기준 \n다음 달 말일까지 최저 실적 구간 서비스를 제공합니다."
    row = terms_row(42, "T9", "NAMED_ITEMS", ["B1", "B2"], evidence=("E9", "E10"))
    row["item_data"]["source"] = {"txt": grace}
    row["item_data"]["footnotes"] = [{"txt": "* 최초 발급 정의"}]
    both = attach_terms([cond_detail(42, "B1", [cond]), cond_detail(42, "B2", [cond])], [row])
    assert both[0][0]["text"] is None and both[0][0]["text_in_conditions"] is True
    assert both[0][0]["footnotes"] == ["* 최초 발급 정의"]                            # 각주는 유지
    assert {e["evidence_id"] for e in both[1]} == {"E9", "E10"}                      # 원문 근거는 유지
    one = attach_terms([cond_detail(42, "B1", [cond]), cond_detail(42, "B2", ["다른 조건"])], [row])[0][0]
    assert one["text"] == grace and one["text_in_conditions_of"] == ["card_product_item:42:B1"]
    partial = attach_terms([cond_detail(42, "B1", ["최초발급*받은 카드"]), cond_detail(42, "B2", [])], [row])[0][0]
    assert partial["text"] == grace and "text_in_conditions_of" not in partial          # 짧은 일부 겹침은 중복 아님


def test_attach_terms_shows_reviewed_text_when_present():
    row = terms_row(42, "T1", "ALL_BENEFITS")
    row["item_data"]["source"] = {"txt": "바우저", "reviewed_txt": "바우처"}
    row["item_data"]["footnotes"] = [{"txt": "전) l요금", "reviewed_txt": "전기요금"}, {"txt": "그대로"}]
    terms, _ = attach_terms([detail(42, "B1")], [row])
    assert terms[0]["text"] == "바우처" and terms[0]["footnotes"] == ["전기요금", "그대로"]
# endregion
