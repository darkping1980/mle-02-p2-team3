"""검색 텍스트, 임베딩 재처리, 상품 혜택 등록, 검색 통합. DB·API 없이 메모리 Mock으로 실행한다."""
from contextlib import contextmanager
import json

from card_benefit.payment_card.db_pipeline import register_service
from card_benefit.payment_card.db_pipeline.common_benefit_service import compare_brand_bnft
from card_benefit.payment_card.db_pipeline.benefit_search_text import (
    build_card_bnft_text, build_common_bnft_text, money,
)
from card_benefit.payment_card.db_pipeline.embedding_service import EmbeddingError, EmbeddingService, vector_literal
from card_benefit.payment_card.db_pipeline.product_benefit_service import ProductBenefitService
from card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import enforce_exclusions, find_exclusions
from card_benefit.payment_card.db_pipeline_origin_search.benefit_search_service import (
    BenefitSearchService, card_hit, common_hit, merge_duplicates, search_terms,
)
import pytest


def rule(key, value, unit, method, minimum=None, targets=("CU", "GS25"), target_type="MERCHANT", excl=None):
    atoms = []
    if minimum:
        atoms.append({"cond_type_cd": "SPEND_REQ", "cond_basis_cd": "TXN_AMT", "negate_yn": False, "cond_min_amt": minimum})
    if excl:
        atoms.append({"cond_type_cd": "BNFT_EXCL", "negate_yn": True, "excl_raw_txt": excl})
    # method는 이전 호출 형식을 위해 받지만 저장하지 않는다(계산 방법 코드는 2026-11-03 정리에서 제거).
    return {"rule_key": key, "value_num": value, "value_unit_cd": unit, "rule_status_cd": "DRAFT",
            "cond_expr": {"branches": [{"atoms": atoms}]} if atoms else None,
            "target_list": [{"target_nm": name, "target_type_cd": target_type} for name in targets]}


ONE_PICK = {"bnft_nm": "ONE PICK 편의점·카페 캐시백", "bnft_type_cd": "CASHBACK", "bnft_type_nm": "캐시백",
            "rule_list": [rule("a", 100, "KRW", "FIXED_PER_TXN", 3000), rule("b", 500, "KRW", "FIXED_PER_TXN", 10000)]}


def test_card_text_matches_confirmed_format_and_dedupes_targets():
    assert build_card_bnft_text(ONE_PICK).text == (
        "혜택명: ONE PICK 편의점·카페 캐시백\n혜택 유형: 캐시백\n이용처: CU, GS25\n"
        "혜택 내용: 결제 건당 3천원 이상 시 100원, 1만원 이상 시 500원 캐시백")


def test_value_text_uses_unit_and_falls_back_to_source_text():
    """계산 방법 없이 값의 단위로 표기한다. 수치로 표기할 수 없는 규칙(무상 서비스 등)은 혜택 원문을 쓴다."""
    old_shape = {**ONE_PICK, "rule_list": [{**r, "calc_method_cd": "FIXED_PER_TXN", "payout_unit_cd": "KRW", "basis_amt": None}
                                           for r in ONE_PICK["rule_list"]]}
    assert build_card_bnft_text(old_shape).text == build_card_bnft_text(ONE_PICK).text      # 이전 형식과 같은 텍스트
    free = {"bnft_nm": "특급호텔 발렛파킹", "bnft_type_cd": "SERVICE", "bnft_rule_txt": "국내 주요 특급호텔 무료 발렛파킹 서비스 제공",
            "rule_list": [rule("v", None, None, "FREE_SERVICE", targets=("특급호텔",), target_type="SERVICE")]}
    built = build_card_bnft_text(free)
    assert "혜택 내용: 국내 주요 특급호텔 무료 발렛파킹 서비스 제공" in built.text


def test_transit_exclusion_is_not_positive_target_or_content():
    benefit = {"bnft_nm": "ONE MORE 대중교통 캐시백", "bnft_type_cd": "CASHBACK", "bnft_type_nm": "캐시백",
               "bnft_rule_txt": "- 대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외 / 5% 캐시백",
               "rule_list": [rule("t", 5, "PERCENT", "PERCENT_OF_TXN", targets=("버스", "지하철"), target_type="SERVICE",
                                  excl="시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외")]}
    built = build_card_bnft_text(benefit)
    assert "서비스 대상: 버스, 지하철" in built.text and "혜택 내용: 5% 캐시백" in built.text
    assert not any(word in built.text for word in ("시외버스", "고속버스", "KTX", "제외")) and not built.review


def test_target_listed_as_excluded_is_removed_and_reported():
    benefit = {**ONE_PICK, "rule_list": [rule("t", 5, "PERCENT", "PERCENT_OF_TXN", targets=("버스", "고속버스"), excl="고속버스 제외")]}
    built = build_card_bnft_text(benefit)
    assert "고속버스" not in built.text and built.review == ["대상과 제외 문구가 겹침: 고속버스"]


def test_spend_exclusion_is_a_different_scope():
    benefit = dict(ONE_PICK)
    benefit["bnft_cond_expr"] = {"branches": [{"atoms": [{"cond_type_cd": "SPEND_EXCL", "excl_raw_txt": "CU 제외"}]}]}
    assert "이용처: CU, GS25" in build_card_bnft_text(benefit).text


def test_mixed_source_text_is_not_guessed_and_unknown_rule_is_reported():
    built = build_card_bnft_text({"bnft_nm": "x", "rule_list": [], "bnft_rule_txt": "버스 5% / 고속버스는 제외"})
    assert built.text == "혜택명: x" and built.review
    unknown = build_card_bnft_text({"bnft_nm": "x", "rule_list": [rule("a", 3, "UNKNOWN", "OTHER")]})
    assert "혜택 내용" not in unknown.text and unknown.review == ["규칙 해석 불가: a"]


def test_common_text_omits_nulls_and_has_no_card_name():
    built = build_common_bnft_text({"common_nm": "Visa Signature", "brand_nm": "Visa", "service_grade_nm": None,
                                    "bnft_nm": "Visa 컨시어지", "bnft_type_nm": "서비스 제공", "bnft_rule_txt": "Visa 컨시어지제공",
                                    "product_nm": "JADE Classic"})
    assert built.text == ("공통서비스: Visa Signature\n브랜드: Visa\n혜택명: Visa 컨시어지\n"
                          "혜택 유형: 서비스 제공\n혜택 내용: Visa 컨시어지제공")


def test_money_keeps_source_style():
    assert [money(v) for v in (100, 3000, 10000, 1500, 15000)] == ["100원", "3천원", "1만원", "1,500원", "15,000원"]


class EmbedRepo:
    """테이블 1건 메모리 저장소."""
    def __init__(self, model="m"):
        self.row = {**ONE_PICK, "card_id": 1, "card_bnft_id": "B1", "bnft_search_txt": None, "has_embedding": False}
        self.vector, self.runs, self.finished, self.model = None, [], [], model

    def rows(self, name, **p):
        if name == "select_card_bnft_rows":
            return [dict(self.row)]
        assert name == "select_common_bnft_rows"
        return []

    def one(self, name, **p):
        return {"run_model_nm": self.model} if self.runs or self.model != "m" else None

    def write(self, name, **p):
        if name == "update_card_bnft_text":
            self.row.update(bnft_search_txt=p["BNFT_SEARCH_TXT"], has_embedding=False)
            self.vector = None
            return [{}]
        if name == "update_card_bnft_embedding":
            if p["BNFT_SEARCH_TXT"] != self.row["bnft_search_txt"]:
                return []
            self.vector = p["BNFT_EMBEDDING"]
            self.row["has_embedding"] = True
            return [{}]
        if name == "insert_embedding_run":
            self.runs.append(p)
            return [{"card_ai_run_id": "R1"}]
        if name == "finish_embedding_run":
            self.finished.append(p)
            return 1
        raise AssertionError(name)


class Embedder:
    model_nm = "m"

    def __init__(self, failures=0):
        self.calls, self.failures, self.inputs = 0, failures, []

    def embed(self, texts):
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError("secret")
        self.inputs.extend(texts)
        return [[0.1, 0.2] for _ in texts]


def service(repo, embedder=None, attempts=2):
    item = EmbeddingService(None, embedder, max_attempts=attempts, retry_seconds=0)
    item.repository = repo
    return item


def test_dry_run_writes_nothing_and_stored_text_equals_model_input():
    repo, embedder = EmbedRepo(), Embedder()
    assert service(repo, embedder).sync().reports[0].targets == 1 and repo.row["bnft_search_txt"] is None
    assert service(repo, embedder).sync(apply=True).ok
    assert embedder.inputs == [repo.row["bnft_search_txt"]] and repo.vector == vector_literal([0.1, 0.2])


def test_same_text_skips_api_and_force_or_text_change_regenerates():
    repo, embedder = EmbedRepo(), Embedder()
    item = service(repo, embedder)
    item.sync(apply=True)
    assert item.sync(apply=True).reports[0].skipped == 1 and embedder.calls == 1
    item.sync(force=True, apply=True)
    assert embedder.calls == 2
    repo.row["bnft_nm"] = "변경"
    item.sync(apply=True)
    assert embedder.calls == 3 and embedder.inputs[-1].startswith("혜택명: 변경")


def test_failure_keeps_text_is_recorded_and_retry_recovers():
    repo, embedder = EmbedRepo(), Embedder(failures=9)
    result = service(repo, embedder).sync(apply=True)
    assert not result.ok and repo.vector is None and repo.row["bnft_search_txt"]
    assert repo.finished[0]["RUN_STATUS"] == "FAILED" and "secret" not in str(repo.finished[0]["RUN_RESULT"].obj)
    assert result.reports[0].failed == [{"id": "B1", "error": "RuntimeError"}]
    assert service(repo, Embedder()).sync(apply=True).reports[0].embedded == 1


def test_transient_failure_is_retried():
    repo, embedder = EmbedRepo(), Embedder(failures=1)
    assert service(repo, embedder).sync(apply=True).reports[0].embedded == 1 and embedder.calls == 2


def test_text_only_makes_no_call_and_model_change_needs_force():
    repo = EmbedRepo(model="old")
    item = service(repo, Embedder())
    assert item.sync(text_only=True, apply=True).run_id is None and repo.row["bnft_search_txt"]
    with pytest.raises(EmbeddingError):
        item.sync(apply=True)
    assert item.sync(force=True, apply=True).ok


def test_embed_new_never_raises_after_registration():
    repo = EmbedRepo(model="old")
    assert service(repo, Embedder()).embed_new("card_bnft", ["B1"]) is None


class Session:
    @contextmanager
    def transaction(self):
        yield self


class ProductRepo:
    def __init__(self):
        self.benefits, self.links = {}, []
        quote = {"evidence_id": "E1", "quote_txt": "5% 캐시백", "source_txt": "5% 캐시백", "start_pos": 1, "end_pos": 6}
        self.evidence = [quote]
        self.candidate = {"card_extr_stg_id": "S1", "stg_status": "PENDING_REVIEW", "stg_sql_check_cd": "OK",
                          "stg_raw_item": {"evidence": [{"supports": "BNFT", "quote_txt": "5% 캐시백"},
                                                        {"supports": "RULE", "support_key": "r", "quote_txt": "5% 캐시백"}]},
                          "check_cd": "OK", "source_cnt": 1, "conflicts": [],
                          "normalized": {"bnft_cd": "C1", "bnft_nm": "n", "bnft_type_cd": "CASHBACK",
                                                  "relation_list": [], "bnft_cond_expr": None,
                                                  "rule_list": [{"rule_key": "r", "rule_status_cd": "DRAFT", "pool_refs": [1]}]}}

    def rows(self, name, **p):
        return {"integrity_errors": [], "list_product_candidates": [self.candidate], "candidate_evidence": self.evidence}[name]

    def attach_normalized(self, run_id, rows):
        return rows

    def one(self, name, **p):
        if name == "lock_card":
            return {"card_id": 1}
        return self.benefits.get(p["BNFT_CD"])

    def write(self, name, **p):
        if name == "insert_local_benefit":
            self.benefits[p["BNFT_CD"]] = {"card_bnft_id": "B9", "rules": p["RULES"].obj}
            return [{"card_bnft_id": "B9"}]
        self.links.append((name, p["EVIDENCE_ID"]))
        return [{}]


class Recorder:
    def __init__(self):
        self.calls = []

    def embed_new(self, table, ids):
        self.calls.append((table, ids))


def test_product_registration_is_idempotent_and_embeds_only_new():
    recorder = Recorder()
    item = ProductBenefitService(Session(), recorder)
    item.repo = ProductRepo()
    assert item.register_run(1, "R")[0].status == "INSERTED"
    assert item.register_run(1, "R")[0].status == "UNCHANGED"
    assert recorder.calls == [("card_bnft", ["B9"])]
    assert "pool_refs" not in item.repo.benefits["C1"]["rules"][0]
    assert {name for name, _ in item.repo.links} == {"insert_evidence_link", "insert_rule_evidence_link"}


def test_product_candidate_blockers_are_reviewed():
    item = ProductBenefitService(Session())
    item.repo = ProductRepo()
    item.repo.candidate["check_cd"] = "NO_EVIDENCE"
    assert item.register_run(1, "R")[0].status == "REVIEW" and not item.repo.benefits
    item.repo.candidate["check_cd"] = "OK"
    item.repo.candidate["normalized"]["is_common_candidate"] = True
    assert item.register_run(1, "R")[0].status == "REVIEW" and not item.repo.benefits


def test_register_rejects_wrong_path_for_document_type():
    class Doc:
        doc_cd, doc_type_cd = "X", "PRODUCT_GUIDE"
        pages, chunks = (), ()

    class Reader(register_service.DocumentService):
        def __init__(self):
            pass

        def inspect(self, pdf):
            return Doc()

    item = register_service.RegisterService(None, Reader())
    with pytest.raises(register_service.RegisterError):
        item.register("x.pdf", apply=True, common_link=register_service.CommonDocLink("C", "n"))
    with pytest.raises(register_service.RegisterError):
        item.register("x.pdf", product_link=register_service.ProductDocLink(1, "b"),
                      common_link=register_service.CommonDocLink("C", "n"))


CARD_ROW = {"card_id": 5, "card_bnft_id": "B1", "bnft_cd": "BRAND_X", "bnft_nm": "Visa 컨시어지", "bnft_type_cd": "SERVICE",
            "product_nm": "JADE Classic", "similarity": 0.5, "bnft_origin_cd": "BRAND_SERVICE"}
COMMON_ROW = {"card_common_id": 1, "card_common_bnft_id": "C1", "bnft_cd": "BRAND_X", "bnft_nm": "Visa 컨시어지",
              "bnft_type_cd": "SERVICE", "apply_cards": [{"card_id": 5, "product_nm": "JADE Classic"}], "similarity": 0.6}


def test_common_duplicate_is_merged_only_when_pair_is_confirmed():
    kept, merged = merge_duplicates([card_hit(CARD_ROW), common_hit(COMMON_ROW)], {("card_bnft:5:B1", "card_common_bnft:1:C1")})
    assert [hit.source for hit in kept] == ["CARD_COMMON_BNFT"] and len(merged) == 1
    kept, merged = merge_duplicates([card_hit(CARD_ROW), common_hit(COMMON_ROW)], set())
    assert len(kept) == 2 and not merged


class CompareService:
    def __init__(self, rows):
        self.rows = rows

    def compare_brand_benefits(self):
        return self.rows


def test_unconfirmed_pair_keeps_both_and_warns():
    item = BenefitSearchService(None, Embedder())
    item.repository = SearchRepo(COMMON_ROW)
    item.common_service = CompareService([{"card_id": 5, "card_bnft_id": "B1", "card_common_id": 1, "card_common_bnft_id": "C1",
                                           "status": "REVIEW", "issues": ["유효기간"]}])
    outcome = item.search("컨시어지", "B")
    assert len(outcome.hits) == 2 and not outcome.merged_duplicates and "유효기간" in outcome.warnings[0]
    item.common_service = CompareService([{"card_id": 5, "card_bnft_id": "B1", "card_common_id": 1, "card_common_bnft_id": "C1",
                                           "status": "SAME", "issues": []}])
    assert [hit.source for hit in item.search("컨시어지", "B").hits] == ["CARD_COMMON_BNFT"]


def same_row(**changes):
    row = dict(card_id=5, card_bnft_id="B1", bnft_cd="X", bnft_nm="n", bnft_type_cd="SERVICE", bnft_valid_from=None,
               bnft_valid_to_excl=None, bnft_rule_txt=None, bnft_limit_txt=None, brand_grades=["VISA/SIGNATURE"],
               evidence_ids=["E1"], doc_ids=["D1"], card_common_bnft_id="C1", common_bnft_nm="n", common_bnft_type_cd="SERVICE",
               common_valid_from=None, common_valid_to_excl=None, common_rule_txt="원문", common_limit_txt=None,
               common_brand_grade="VISA/SIGNATURE", common_doc_ids=["D1"], common_evidence_ids=["E1", "E2"], applied=True)
    return {**row, **changes}


@pytest.mark.parametrize("changes,label", [
    (dict(common_bnft_nm="m"), "혜택명·유형"), (dict(common_doc_ids=["D2"]), "출처 문서"),
    (dict(common_brand_grade="VISA/WORLD"), "브랜드·등급"), (dict(applied=False), "적용 카드"),
    (dict(bnft_valid_to_excl="2027-01-01"), "유효기간"), (dict(bnft_rule_txt="다른 내용"), "혜택 내용"),
    (dict(common_evidence_ids=["E9"]), "원문 근거"), (dict(doc_ids=None), "출처 문서"),
])
def test_any_difference_stays_in_review(changes, label):
    status, issues = compare_brand_bnft(same_row(**changes))
    assert status == "REVIEW" and label in issues


def test_full_match_is_same_and_missing_common_is_reported():
    assert compare_brand_bnft(same_row()) == ("SAME", [])
    assert compare_brand_bnft(same_row(card_common_bnft_id=None))[0] == "NO_COMMON"


class SearchRepo:
    def __init__(self, common):
        self.common = common

    def one(self, name, **p):
        return {"run_model_nm": "m"}

    def rows(self, name, **p):
        return {"search_card_bnft": [CARD_ROW], "search_common_bnft": [self.common],
                "keyword_card_bnft": [{**CARD_ROW, "keyword_score": 1}], "keyword_common_bnft": [{**self.common, "keyword_score": 0}]}[name]


@pytest.mark.parametrize("mode", ["B", "C"])
def test_unapplied_common_benefit_is_flagged_not_assumed(mode):
    item = BenefitSearchService(None, Embedder())
    item.repository = SearchRepo({**COMMON_ROW, "bnft_cd": "OTHER", "apply_cards": []})
    item.common_service = CompareService([])
    outcome = item.search("컨시어지", mode)
    hit = next(hit for hit in outcome.hits if hit.source == "CARD_COMMON_BNFT")
    assert hit.applied is False and hit.cards == [] and outcome.warnings


def test_mode_a_does_not_call_embedding_and_model_mismatch_blocks_vector():
    item = BenefitSearchService(None, None)
    item.repository = SearchRepo(COMMON_ROW)
    assert item.search("컨시어지", "A").hits[0].source == "CARD_BNFT"
    other = Embedder()
    other.model_nm = "other"
    item = BenefitSearchService(None, other)
    item.repository = SearchRepo(COMMON_ROW)
    with pytest.raises(ValueError):
        item.search("컨시어지", "B")


class GraphStub:
    def candidate_relations(self, ids):
        return {"card_bnft:1:T": {"key": '["card_bnft",1,"T"]', "id": "T", "cards": ["c"], "targets": ["버스", "지하철"], "common_nm": None,
                      "exclusions": ["시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외"]}}


def transit_hit():
    return card_hit({"card_id": 1, "card_bnft_id": "T", "bnft_cd": "T", "bnft_nm": "대중교통", "bnft_type_cd": "CASHBACK", "product_nm": "c"})


def other_hit():
    return card_hit({"card_id": 1, "card_bnft_id": "O", "bnft_cd": "O", "bnft_nm": "다른 혜택", "bnft_type_cd": "CASHBACK", "product_nm": "c"})


def test_graph_moves_excluded_candidate_back_and_marks_terms():
    item = BenefitSearchService(None, None, GraphStub())
    hits = item._rank_with_graph("고속버스 캐시백", [transit_hit(), other_hit()], [])
    assert [hit.benefit_id for hit in hits] == ["O", "T"] and hits[1].excluded_terms == ["고속버스"]
    hits = item._rank_with_graph("KTX도 되나요", [transit_hit()], [])
    assert hits[0].excluded_terms == ["ktx"]
    hits = item._rank_with_graph("버스 혜택", [other_hit(), transit_hit()], [])
    assert hits[0].benefit_id == "T" and hits[0].target_terms == ["버스"] and not hits[0].excluded_terms


def detail_with(rule_list, cond=None):
    benefit = {"card_bnft_id": "T", "bnft_nm": "대중교통", "rule_list": rule_list, "bnft_cond_expr": cond}
    return {"context": {"benefit": {"source_json": json.dumps(benefit, ensure_ascii=False)}}}


TRANSIT_RULE = rule("t", 5, "PERCENT", "PERCENT_OF_TXN", targets=("버스", "지하철"), target_type="SERVICE",
                    excl="시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외")


def test_exclusion_is_verified_from_postgres_row_when_available():
    details = [{"context": {"benefit": {"source_json": json.dumps({"card_id": 2, "card_bnft_id": "T", "bnft_nm": "대중교통"})}}}]
    found = find_exclusions("고속버스 캐시백 받을 수 있어?", details, lambda card, bnft: {"rule_list": [TRANSIT_RULE]})
    assert found[0]["terms"] == ["고속버스"] and found[0]["verified_by"] == "postgresql"
    assert find_exclusions("지하철 캐시백", details, lambda card, bnft: {"rule_list": [TRANSIT_RULE]}) == []


def test_bus_target_is_not_excluded_by_substring():
    assert find_exclusions("버스 캐시백", [detail_with([TRANSIT_RULE])]) == []
    assert find_exclusions("KTX도 대중교통 캐시백 돼?", [detail_with([TRANSIT_RULE])])[0]["terms"] == ["KTX"]


def test_enforced_conclusion_blocks_positive_answer():
    answer = {"status": "ANSWERED", "conclusion": "고속버스도 5% 캐시백입니다.", "uncertain": [], "message": None,
              "points": [{"text": "고속버스도 5% 캐시백입니다.", "evidence_ids": ["E1"], "benefit_id": "T", "origin": "llm",
                          "benefit_name": "대중교통", "verification": "RAW_MATCH"},
                         {"text": "월 한도는 1천원입니다.", "evidence_ids": ["E2"], "benefit_id": "T", "origin": "llm",
                          "benefit_name": "대중교통", "verification": "RAW_MATCH"}]}
    fixed, warnings = enforce_exclusions(answer, [{"benefit_id": "T", "name": "대중교통", "terms": ["고속버스"], "verified_by": "postgresql"}],
                                         [{"evidence_id": "E9", "quote": "시외버스, 고속버스 제외"}])
    assert "고속버스는" in fixed["answer_text"] and "받을 수 없습니다" in fixed["conclusion"] and warnings
    assert fixed["answer_source"] == "program_exclusion"
    assert all("5% 캐시백" not in point["text"] for point in fixed["points"])
    assert fixed["points"][0]["evidence_ids"] == ["E9"] and fixed["points"][0]["origin"] == "system"


def test_search_terms_drop_stopwords_and_particles():
    assert search_terms("GS25 혜택이 있는 카드") == ["GS25"]
    assert "놀이공원" in search_terms("놀이공원을 가는")


# region B/C 모드 ID 충돌(2026-11-04 우리카드 card_bnft 11건 ↔ MP004 card_common_bnft 11건, 같은 ID 문자열)
SAME_ID = "20261104_000013"
WOORI_ROW = {"card_id": 6, "card_bnft_id": SAME_ID, "bnft_cd": "BNFT_WOORI", "bnft_nm": "온라인 쇼핑 10% 청구할인",
             "bnft_type_cd": "DISCOUNT", "product_nm": "카드의정석 SHOPPING", "similarity": 0.7, "bnft_origin_cd": "LOCAL",
             "bnft_search_txt": "혜택명: 온라인 쇼핑 10% 청구할인\n이용처: 온라인 업종"}
MP004_ROW = {"card_common_id": 9, "card_common_bnft_id": SAME_ID, "bnft_cd": "BNFT_QATAR", "bnft_nm": "Qatar Airways 항공권 할인",
             "bnft_type_cd": "DISCOUNT", "apply_cards": [], "similarity": 0.6, "bnft_search_txt": "혜택명: Qatar Airways 항공권 할인"}
WOORI_KEY = json.dumps(["card_bnft", 6, SAME_ID])
MP004_KEY = json.dumps(["card_common_bnft", 9, SAME_ID])


class CollisionRepo:
    def one(self, name, **p):
        return {"run_model_nm": "m"}

    def rows(self, name, **p):
        return {"search_card_bnft": [WOORI_ROW], "search_common_bnft": [MP004_ROW],
                "keyword_card_bnft": [{**WOORI_ROW, "keyword_score": 1}],
                "keyword_common_bnft": [{**MP004_ROW, "keyword_score": 0}]}[name]


class CollisionGraph:
    """실제 Neo4jSearch와 같은 계약: 관계는 참조별로, 목록·카탈로그 행은 key와 id를 함께 준다."""
    def __init__(self):
        self.list_calls = 0

    def candidate_relations(self, ids):
        return {"card_bnft:6:" + SAME_ID: {"key": WOORI_KEY, "id": SAME_ID, "cards": ["카드의정석 SHOPPING"],
                                           "targets": ["온라인 업종"], "exclusions": [], "common_nm": None},
                "card_common_bnft:9:" + SAME_ID: {"key": MP004_KEY, "id": SAME_ID, "cards": [], "targets": ["카타르항공"],
                                                  "exclusions": ["온라인 쇼핑 제외"], "common_nm": "Mastercard"}}

    def list_benefits(self, keyword):
        self.list_calls += 1
        return [{"key": MP004_KEY, "id": SAME_ID, "name": "Qatar Airways 항공권 할인", "status": None}]


GRAPH_CATALOG = [
    {"key": WOORI_KEY, "id": SAME_ID, "name": "온라인 쇼핑 10% 청구할인", "card": "카드의정석 SHOPPING", "status": "PENDING_REVIEW",
     "targets": ["온라인 업종"], "payment_min_amounts": []},
    {"key": MP004_KEY, "id": SAME_ID, "name": "Qatar Airways 항공권 할인", "card": "적용 카드 미확인", "status": None,
     "targets": ["카타르항공"], "payment_min_amounts": []},
]


def collision_service():
    item = BenefitSearchService(None, Embedder(), CollisionGraph())
    item.repository = CollisionRepo()
    item.common_service = CompareService([])
    return item


@pytest.mark.parametrize("mode", ["B", "C"])
def test_same_id_card_and_common_hits_stay_separate(mode):
    outcome = collision_service().search("온라인 쇼핑 할인", mode, top_k=5)
    keys = sorted(hit.key for hit in outcome.hits)
    assert keys == [f"pg:CARD_BNFT:6:{SAME_ID}", f"pg:CARD_COMMON_BNFT:9:{SAME_ID}"]
    assert not outcome.merged_duplicates


@pytest.mark.parametrize("mode", ["B", "C"])
def test_catalog_rows_join_graph_by_reference_not_id(mode):
    rows, _ = collision_service().catalog_rows("온라인 쇼핑 할인", mode, GRAPH_CATALOG)
    by_key = {row["key"]: row for row in rows}
    assert by_key[WOORI_KEY]["name"] == "온라인 쇼핑 10% 청구할인" and by_key[WOORI_KEY]["card"] == "카드의정석 SHOPPING"
    assert by_key[MP004_KEY]["name"] == "Qatar Airways 항공권 할인" and by_key[MP004_KEY]["card"] == "적용 카드 미확인"
    assert len(rows) == 2


def test_graph_relations_do_not_cross_same_id():
    hits = collision_service()._rank_with_graph("온라인 쇼핑", [card_hit(WOORI_ROW), common_hit(MP004_ROW)], [])
    woori = next(hit for hit in hits if hit.source == "CARD_BNFT")
    qatar = next(hit for hit in hits if hit.source == "CARD_COMMON_BNFT")
    assert woori.graph_targets == ["온라인 업종"] and not woori.excluded_terms
    assert qatar.graph_targets == ["카타르항공"]


def test_neo4j_name_score_only_counts_matching_entity():
    item = collision_service()
    hits = item._keyword("Qatar 항공권", [])
    scores = {hit.source: hit.keyword_score for hit in hits}
    # 카드 혜택은 SQL 점수 1 그대로, 공통 혜택만 Neo4j 혜택명 일치로 점수를 받는다(같은 ID여도 섞이지 않음).
    assert scores["CARD_BNFT"] == 1 and scores["CARD_COMMON_BNFT"] == item.neo4j_search.list_calls


def test_confirmed_pair_needs_owner_reference():
    hits = [card_hit(WOORI_ROW), common_hit(MP004_ROW)]
    # 다른 카드(5)의 같은 ID 쌍이 확인돼도 우리카드(6) 혜택을 합치지 않는다.
    kept, merged = merge_duplicates(hits, {(f"card_bnft:5:{SAME_ID}", f"card_common_bnft:9:{SAME_ID}")})
    assert len(kept) == 2 and not merged
    kept, merged = merge_duplicates(hits, {(f"card_bnft:6:{SAME_ID}", f"card_common_bnft:1:{SAME_ID}")})
    assert len(kept) == 2 and not merged
# endregion
