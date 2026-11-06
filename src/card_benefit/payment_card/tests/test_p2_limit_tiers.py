"""P2(2026-11-06): 혜택 item_data의 Neo4j 적재·원천 컬럼 완전성 검사·구간별 한도 답변 검증. DB를 쓰지 않는다.

fixture
    fixtures_limit_struct.json       22/099·23/100·20/092 실제 추출 원본·등록 규칙·근거(P1과 공용)
    fixtures_limit_tiers_daily.json  42/179·42/180 실제 item_data.limit_tiers(SET_LIMIT_TIERS 보정본, 읽기 전용으로 옮김)
22/099의 limit_tiers는 DB에 아직 없다(기존 데이터 보정 전). P1 helper가 추출 원본에서 만드는 값으로 시험한다.
"""
import copy
import json
from pathlib import Path

from card_benefit.payment_card.db_pipeline import neo4j_dry_run as dry
from card_benefit.payment_card.db_pipeline.extraction_service import limit_struct, limit_tiers_from_extraction
from card_benefit.payment_card.db_pipeline.neo4j_load_draft import node_properties
from card_benefit.payment_card.db_pipeline.neo4j_validate import compare_item_data, source_column_map
from card_benefit.payment_card.db_pipeline.product_benefit_service import ProductBenefitService
from card_benefit.payment_card.db_pipeline_origin_search import card_graphrag as g
from card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import AnswerPoint, CardAnswer, rule_conflicts

HERE = Path(__file__).parent
STRUCT = json.loads((HERE / "fixtures_limit_struct.json").read_text(encoding="utf-8"))
DAILY = json.loads((HERE / "fixtures_limit_tiers_daily.json").read_text(encoding="utf-8"))
# 2026-11-06 information_schema.columns 실제 값(읽기 전용 조회)
PRODUCT_ITEM_COLUMNS = ["card_id", "card_product_item_id", "item_type_cd", "item_cd", "item_nm", "item_subtype_cd", "item_origin_cd",
                        "item_scope_cd", "item_brand_opt_cds", "item_cond_expr", "rule_list", "relation_list", "item_data",
                        "verification_status_cd", "item_valid_from", "item_valid_to_excl", "item_rule_txt", "item_limit_txt",
                        "item_search_txt", "item_embedding", "item_ref", "create_date", "create_user_id", "update_date", "update_user_id"]
EVIDENCE_LINK_COLUMNS = ["card_doc_id", "page_no", "card_doc_chunk_id", "evidence_id", "card_id", "evidence_link_id",
                         "card_product_item_id", "ev_subject_cd", "rule_key", "relation_key", "ev_item_cd", "ev_item_key"]
SOURCE = {"card_product_item": PRODUCT_ITEM_COLUMNS, "card_evidence_link": EVIDENCE_LINK_COLUMNS}


def simple_item_data():
    """22/099: P1 helper가 실제 추출 원본에서 만드는 item_data(보정 후 DB에 들어갈 형태)."""
    case = copy.deepcopy(STRUCT["22/20261105_000099"])
    raw, rules, evidence = case["stg_raw_item"], case["rule_list"], case["evidence"]
    located = ProductBenefitService._located(evidence)
    struct = limit_struct(raw, [r["rule_key"] for r in rules], ProductBenefitService._limit_evidence(raw, located))
    tiers = limit_tiers_from_extraction(rules, struct, ProductBenefitService._cond_evidence(raw, rules, located))
    return {"schema_ver": "BENEFIT_V1", **struct, "limit_tiers": tiers}


def detail(card, item_id, name, item_data, rules, conditions=(), limit_text=None):
    """Neo4j 상세 조회(card.detail_batch) 결과 형태."""
    benefit = {"card_bnft_id": item_id, "bnft_nm": name, "item_data": item_data, "bnft_rule_txt": None}
    return {"context": {"card": {"source_json": json.dumps({"product_nm": card}, ensure_ascii=False)},
                        "benefit": {"source_json": json.dumps(benefit, ensure_ascii=False)}},
            "rules": [{"rule": {"source_json": json.dumps(rule, ensure_ascii=False)}, "targets": ["SKT"]} for rule in rules],
            "conditions": list(conditions), "limits": [{"limit_text": limit_text}] if limit_text else [], "evidence": []}


def simple_context_benefit():
    case = STRUCT["22/20261105_000099"]
    data = simple_item_data()
    item = detail("더 심플 하나카드", "20261105_000099", "월납 요금 청구할인", data, case["rule_list"], limit_text=case["item_limit_txt"])
    benefit = g.benefit_context(item)
    # 조건 묶음은 Neo4j 조건 행에서 만든다. 여기서는 benefit_context 결과 형태를 직접 채운다(구간 검증에 필요한 부분).
    benefit["conditions"] = [{"scope": rk, "branches": [{"branch_no": 1, "atoms": [
        {"atom_key": ak, "negate": False, "type": "SPEND_REQ", "min_amt": lo, "max_amt": hi, "basis": "PREV_MONTH_SPEND",
         "text": txt, "status": "DRAFT"}]}]} for rk, ak, lo, hi, txt in
        (("r1", "c1", 300000, 800000, "30만원 이상\n80만원 미만"), ("r2", "c2", 800000, None, "80만원 이상"))]
    return benefit


def daily_benefit(item_id, name):
    case = DAILY[f"42/{item_id}"]
    item = detail("카드의정석2 DAILY", item_id, name, case["item_data"],
                  [{"rule_key": "r", "value_num": 5, "value_unit_cd": "PERCENT", "rule_status_cd": "DRAFT"}],
                  limit_text=case["item_limit_txt"])
    return g.benefit_context(item)


# region 적재(neo4j_dry_run): BENEFIT item_data
class TestSnapshotItemData:
    def test_benefit_select_includes_item_data_and_keeps_other_columns(self):
        assert "item_data FROM db_pipeline.card_product_item WHERE item_type_cd = 'BENEFIT'" in dry.BENEFITS_SQL
        for part in ("card_product_item_id AS card_bnft_id", "item_limit_txt AS bnft_limit_txt", "item_embedding AS bnft_embedding"):
            assert part in dry.BENEFITS_SQL
        # 혜택 외 항목·근거 연결 SELECT는 기존과 같은 열이다(노드·관계 source_json 불변).
        assert dry.ITEMS_SQL == ("SELECT card_id, card_product_item_id, item_type_cd, item_cd, item_nm, item_scope_cd, item_brand_opt_cds, "
                                 "item_data, verification_status_cd, item_valid_from, item_valid_to_excl, item_rule_txt, item_limit_txt "
                                 "FROM db_pipeline.card_product_item WHERE item_type_cd <> 'BENEFIT' ORDER BY card_id, card_product_item_id")
        assert dry.LINKS_SQL == ("SELECT card_id, evidence_link_id AS ev_link_id, ev_subject_cd, card_product_item_id AS card_bnft_id, rule_key, "
                                 "relation_key, ev_item_cd, ev_item_key, evidence_id FROM db_pipeline.card_evidence_link "
                                 "ORDER BY card_id, evidence_link_id")

    def test_item_data_goes_to_source_json_not_to_properties(self):
        data = simple_item_data()
        snapshot = {"products": [{"card_id": 22, "card_cond_status_cd": "DRAFT"}], "product_docs": [], "documents": [], "pages": [],
                    "chunks": [], "evidence": [], "links": [], "items": [], "commons": [], "common_docs": [],
                    "common_benefits": [], "common_applies": [], "brand_compare": [],
                    "benefits": [{"card_id": 22, "card_bnft_id": "B1", "bnft_nm": "월납 요금 청구할인", "bnft_cond_expr": None,
                                  "rule_list": [], "relation_list": [], "item_data": data, "bnft_limit_txt": "10,000원 / 15,000원"}]}
        graph, _ = dry.build(snapshot)
        node = graph.nodes[dry.key("card_bnft", 22, "B1")]
        assert json.loads(node["source_json"])["item_data"] == json.loads(json.dumps(data))
        props = node_properties(node)
        assert "item_data" not in props and props["limit_text"] == "10,000원 / 15,000원"
        # 상세 조회는 source_json을 그대로 돌려주므로 GraphRAG가 읽을 수 있다.
        assert g.limit_tier_view(json.loads(props["source_json"])["item_data"])[0]["cap"]["amount"] == 10000
# endregion


# region 검증(neo4j_validate): 원천 컬럼 완전성·item_data 직접 대조
class TestColumnCoverage:
    def test_current_mapping_covers_all_source_columns(self):
        assert dry.column_coverage(SOURCE) == []

    def test_old_select_without_item_data_is_detected(self):
        """P2 이전 SELECT(item_data 없음)를 재현하면 검출되어야 한다(노드·관계 수와 무관)."""
        old = {k: v for k, v in dry.BENEFIT_COLUMNS.items() if k != "item_data"}
        original = dry.SNAPSHOT_COLUMNS["benefits"]
        try:
            dry.SNAPSHOT_COLUMNS["benefits"] = old
            problems = dry.column_coverage(SOURCE)
        finally:
            dry.SNAPSHOT_COLUMNS["benefits"] = original
        assert any("benefits" in p and "item_data" in p for p in problems), problems

    def test_new_source_column_must_be_classified(self):
        source = {**SOURCE, "card_product_item": PRODUCT_ITEM_COLUMNS + ["item_new_col"]}
        problems = dry.column_coverage(source)
        assert any("item_new_col" in p and p.startswith("benefits") for p in problems)
        assert any("item_new_col" in p and p.startswith("items") for p in problems)

    def test_snapshot_rows_must_carry_mapped_columns(self):
        row = {alias: None for column, alias in dry.BENEFIT_COLUMNS.items() if column not in ("item_search_txt", "item_embedding")}
        assert dry.column_coverage(SOURCE, {"benefits": [row]}) == []
        row.pop("item_data")
        assert any("스냅샷 행에 없는 매핑 컬럼" in p and "item_data" in p for p in dry.column_coverage(SOURCE, {"benefits": [row]}))

    def test_source_column_map(self):
        rows = [{"table_name": "t", "column_name": "a"}, {"table_name": "t", "column_name": "b"}]
        assert source_column_map(rows) == {"t": ["a", "b"]}


class TestItemDataCompare:
    def test_missing_key_value_change_and_match(self):
        pg = [{"card_id": 22, "card_bnft_id": "A", "item_data": {}},
              {"card_id": 42, "card_bnft_id": "B", "item_data": {"limit_tiers": {"x": 1}}},
              {"card_id": 42, "card_bnft_id": "C", "item_data": '{"schema_ver": "BENEFIT_V1"}'}]
        graph = [{"card_id": 22, "card_bnft_id": "A", "has_item_data": False, "item_data": None},     # 적재 전 상태
                 {"card_id": 42, "card_bnft_id": "B", "has_item_data": True, "item_data": {"limit_tiers": {"x": 2}}},
                 {"card_id": 42, "card_bnft_id": "C", "has_item_data": True, "item_data": {"schema_ver": "BENEFIT_V1"}},
                 {"card_id": 9, "card_bnft_id": "Z", "has_item_data": True, "item_data": {}}]
        problems = {tuple(p["key"]): p["problem"] for p in compare_item_data(pg, graph)}
        assert problems == {(22, "A"): "Neo4j source_json에 item_data 키 없음", (42, "B"): "item_data 값 다름",
                            (9, "Z"): "PostgreSQL에 없는 Neo4j 혜택"}
# endregion


# region GraphRAG: limit_tiers 전달과 구간별 한도 배정 검증
class TestLimitTierContext:
    def test_simple_monthly_tiers_reach_context_without_touching_rule_values(self):
        benefit = simple_context_benefit()
        assert [(t["label"], t["min_amt"], t["max_amt"], t["cap"]["amount"]) for t in benefit["limit_tiers"]] == [
            ("30만원 이상 80만원 미만", 300000, 800000, 10000), ("80만원 이상", 800000, None, 15000)]
        assert [r["value"] for r in benefit["rules"]] == [None, None, None]        # 한도는 지급값이 아니다
        tiers = rule_conflicts([benefit], None)[0]["tiers"]
        assert {t["payout_known"] for t in tiers} == {False}                      # P0 계약 유지

    def test_no_limit_tiers_keeps_old_context(self):
        for name in ("23/20261105_000100", "20/20261105_000092"):
            case = STRUCT[name]
            benefit = g.benefit_context(detail("카드", name.split("/")[1], "x", {}, case["rule_list"], limit_text=case["item_limit_txt"]))
            assert "limit_tiers" not in benefit
        assert g.limit_tier_view({"limits": [], "rule_limits": {}}) == []
        assert g.limit_tier_view(None) == []

    def test_daily_shared_caps_are_exposed(self):
        fixed = daily_benefit("20261105_000179", "고정소비 영역 5% 청구할인")
        assert [(t["min_amt"], t["cap"]["amount"], [s["amount"] for s in t["shared"]]) for t in fixed["limit_tiers"]] == [
            (500000, 3000, [8000]), (1000000, 6000, [11000]), (2000000, 12000, [17000])]


class TestDistortsLimitTier:
    def test_simple_monthly_correct_and_swapped_pairs(self):
        benefits = [simple_context_benefit()]
        for text in ("전월 실적 30만원 이상 80만원 미만이면 월 10,000원, 80만원 이상이면 월 15,000원까지 할인됩니다.",
                     "30만원 이상 구간 한도는 10,000원입니다.", "자동납부 시 할인됩니다.", "월 할인 한도는 10,000원 / 15,000원입니다."):
            assert not g.distorts_limit_tier(text, benefits), text
        for text in ("전월 실적 80만원 이상이면 월 10,000원까지 할인됩니다.",
                     "30만원 이상 80만원 미만은 15,000원 한도입니다.",
                     "30만원 이상이면 15,000원, 80만원 이상이면 10,000원입니다."):
            assert g.distorts_limit_tier(text, benefits), text

    def test_daily_tier_and_shared_caps(self):
        benefits = [daily_benefit("20261105_000179", "고정소비 영역 5% 청구할인"), daily_benefit("20261105_000180", "정기결제 50% 청구할인")]
        assert not g.distorts_limit_tier("50만원 이상 100만원 미만은 고정소비 3,000원, 통합 8,000원입니다.", benefits)
        assert not g.distorts_limit_tier("100만원 이상 200만원 미만이면 정기결제 5,000원, 통합 할인한도 11,000원입니다.", benefits)
        assert g.distorts_limit_tier("100만원 이상이면 통합 할인한도 8,000원입니다.", benefits)
        assert g.distorts_limit_tier("200만원 이상이면 고정소비 할인 6,000원입니다.", benefits)

    def test_comparison_sentence_with_other_card_amounts_is_not_flagged(self):
        benefits = [simple_context_benefit(), daily_benefit("20261105_000180", "정기결제 50% 청구할인")]
        text = "더 심플은 30만원 이상 80만원 미만 월 10,000원이고, DAILY 정기결제는 월 5,000원입니다."
        assert not g.distorts_limit_tier(text, benefits)        # 5,000원은 더 심플의 한도가 아니므로 판정하지 않는다

    def test_benefits_without_limit_tiers_are_not_judged(self):
        case = STRUCT["23/20261105_000100"]
        benefit = g.benefit_context(detail("카드", "20261105_000100", "x", {}, case["rule_list"], limit_text=case["item_limit_txt"]))
        assert not g.distorts_limit_tier("30만원 이상이면 5만원입니다.", [benefit])     # 구간 표가 없으면 판단 근거가 없다


class TestValidateAnswerWithLimitTiers:
    def context(self):
        benefit = simple_context_benefit()
        bid = benefit["benefit_id"]
        evidence = [{"evidence_id": eid, "page_no": 1, "approval_status": "PENDING", "quote": quote, "benefit_ids": [bid]}
                    for eid, quote in (("E81", "10,000원"), ("E82", "15,000원"), ("E85", "30만원 이상\n80만원 미만"),
                                       ("E86", "80만원 이상\n15,000원"))]
        return {"benefits": [benefit], "payment_amount": None, "rule_selection_unresolved": rule_conflicts([benefit], None),
                "unresolved": [], "evidence": evidence}, bid

    def test_wrong_pair_is_dropped_and_correct_pair_kept(self):
        context, bid = self.context()
        good = "전월 실적 30만원 이상 80만원 미만이면 월 10,000원까지 할인됩니다."
        bad = "전월 실적 80만원 이상이면 월 10,000원까지 할인됩니다."
        raw = CardAnswer(answer_text=good, conclusion="", uncertain=[], cannot_answer_reason=None,
                         points=[AnswerPoint(text=good, evidence_ids=["E81", "E85"], benefit_id=bid),
                                 AnswerPoint(text=bad, evidence_ids=["E81", "E86"], benefit_id=bid)])
        answer, warnings = g.validate_answer(raw, context, "휴대전화 요금 자동납부 할인 한도는?")
        texts = [p["text"] for p in answer["points"]]
        assert good in texts and bad not in texts
        assert any("한도 금액의 짝" in w for w in warnings)

    def test_answer_text_problem_reports_wrong_pair(self):
        context, _ = self.context()
        known = g.known_values(context, "", None)
        numbers = g.numbers_in(json.dumps(context, ensure_ascii=False))
        assert g.answer_text_problem("80만원 이상이면 월 10,000원까지 할인됩니다. 다만 적용 방식은 미확정입니다.", context, "", known, numbers) \
            == "실적 구간과 한도 금액의 짝이 원문과 다릅니다"
# endregion
