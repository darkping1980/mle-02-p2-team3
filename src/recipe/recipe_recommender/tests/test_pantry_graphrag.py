"""냉장고 재료 추천 GraphRAG MVP 테스트.

가짜 Repository·가짜 LLM으로 입력 분리, 별칭 해석, 근거 밖 레시피·재료 차단, LLM 성공/실패 구분을 검증한다.
실제 Neo4j 조회 테스트(``LivePantryGraphTests``)는 읽기 전용이며 ``NEO4J_URI`` 가 있을 때만 실행한다(LLM 미사용).
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

from recipe_recommender.config import PACKAGE_DIR, load_project_environment  # noqa: E402
from recipe_recommender.pantry_graphrag import (  # noqa: E402
    PantryAnswer, PantryGraphRAG, RecipeReason, foreign_ingredients, grounded_reason, grounded_summary,
    josa, josa_ro, terms_in_question, validate_answer,
)
from recipe_recommender.pantry_graphrag import build_context  # noqa: E402
from recipe_recommender.pantry_recommend_service import (  # noqa: E402
    ALLOWED_STATEMENTS, PantryRecommendService, RecipeStep, display_image_url, split_terms,
)

load_project_environment()

# ---------------------------------------------------------------------
# 가짜 그래프 데이터 (Neo4j 조회 결과와 같은 형식)
# ---------------------------------------------------------------------
INGREDIENTS = {
    "i1": ("달걀", ["계란"]), "i2": ("두부", []), "i3": ("양파", []), "i4": ("닭가슴살", []),
    "i5": ("김치", []), "i6": ("대파", []), "i7": ("닭고기", []), "i8": ("소금", []), "i9": ("다진 마늘", ["다진마늘"]),
}
RECIPES = {
    "r1": {"rcp_nm": "닭고기김치찌개", "rcp_seq": "101", "categories": ["국&찌개"], "method": "끓이기",
           "energy_kcal": 320.0, "ingredients": ["달걀", "두부", "양파", "닭가슴살", "김치", "대파"]},
    "r2": {"rcp_nm": "두부달걀덮밥", "rcp_seq": "102", "categories": ["밥"], "method": "끓이기",
           "energy_kcal": 410.0, "ingredients": ["달걀", "두부", "양파", "소금"]},
}
IMAGE_URLS = {"r1": "http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00101_2.png", "r2": None}
# recipe_steps 조회 결과(식약처 원본). 순서를 일부러 섞고 원본 번호 2를 비워 정렬·번호 유지를 확인한다.
# r1의 3단계는 이미지가 없다. r2는 조리 단계가 없다.
STEPS = [
    {"rcp_id": "r1", "step_no": 3, "instruction_txt": "대파를 넣고 *한소끔* 끓인다.", "image_url": None},
    {"rcp_id": "r1", "step_no": 1, "instruction_txt": "닭가슴살을 한입 크기로 썬다.",
     "image_url": "http://www.foodsafetykorea.go.kr/uploadimg/cook/20_00101_1.png"},
]


def _norm(value: str) -> str:
    return value.strip().lower()


class FakeGraph:
    """``RecipeGraphRepository`` 의 ``query_example`` / ``mapper.select_list`` 만 흉내 낸다."""

    def __init__(self, fail_steps: bool = False):
        self.calls: list[str] = []
        self.fail_steps = fail_steps            # True면 recipe_steps 조회가 실패한다(단계 데이터 장애 재현)
        self.mapper = SimpleNamespace(select_list=self._select_list)

    def _matches(self, term_norm):
        return [(ingr_id, nm, aliases) for ingr_id, (nm, aliases) in INGREDIENTS.items()
                if _norm(nm) == term_norm or term_norm in [_norm(a) for a in aliases]]

    def query_example(self, name, parameters):
        self.calls.append(f"recipe_graph_queries.{name}")
        if name == "ingredient_name_candidates":
            return [{"ingr_id": i, "ingr_nm": nm, "alias_names": a} for i, nm, a in self._matches(parameters["term_norm"])]
        if name == "pantry_recommendations":
            return self._recommend(parameters["names_norm"], by_coverage=False)
        if name == "graphrag_context":
            rec = RECIPES[parameters["rcp_id"]]
            return [{"context": {"rcp_id": parameters["rcp_id"], "rcp_seq": rec["rcp_seq"], "name": rec["rcp_nm"],
                                 "categories": rec["categories"], "method": rec["method"],
                                 "energy_kcal": rec["energy_kcal"], "image_url": IMAGE_URLS[parameters["rcp_id"]],
                                 "ingredients": rec["ingredients"]}}]
        if name == "recipe_steps":
            if self.fail_steps:
                raise ConnectionError("step query unavailable")
            return [dict(row) for row in STEPS if row["rcp_id"] in parameters["rcp_ids"]]
        raise AssertionError(name)

    def _select_list(self, statement, parameters):
        self.calls.append(statement)
        if statement == "pantry_graphrag.ingredient_vocabulary":
            return [{"ingr_id": i, "ingr_nm": nm, "alias_names": a} for i, (nm, a) in INGREDIENTS.items()]
        if statement == "pantry_graphrag.pantry_recommendations_by_coverage":
            return self._recommend(parameters["names_norm"], by_coverage=True)[:parameters["limit"]]
        raise AssertionError(statement)

    def _recommend(self, names_norm, by_coverage):
        owned = {nm for term in names_norm for _, nm, _ in self._matches(term)}
        rows = []
        for rcp_id, rec in RECIPES.items():
            matched = sorted(set(rec["ingredients"]) & owned)
            if matched:
                rows.append({"rcp_id": rcp_id, "rcp_nm": rec["rcp_nm"], "matched_count": len(matched),
                             "missing_count": len(rec["ingredients"]) - len(matched), "matched_ingredients": matched,
                             "missing_ingredients": sorted(set(rec["ingredients"]) - owned)})
        key = (lambda r: (-r["matched_count"], r["missing_count"], r["rcp_id"])) if by_coverage else \
              (lambda r: (r["missing_count"], -r["matched_count"], r["rcp_id"]))
        return sorted(rows, key=key)


class FakeLLM:
    """``with_structured_output(schema).invoke(prompt)`` 에 미리 정한 응답을 돌려준다(예외면 raise)."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.prompts: list[str] = []

    def with_structured_output(self, schema):
        def invoke(prompt):
            self.prompts.append(prompt)
            response = self.responses.get(schema.__name__)
            if isinstance(response, Exception):
                raise response
            if response is None:
                raise RuntimeError(f"no fake response for {schema.__name__}")
            return response
        return SimpleNamespace(invoke=invoke)


def run(question="계란, 두부, 양파", llm=None, limit=5, sort="coverage", fail_steps=False):
    graph = FakeGraph(fail_steps=fail_steps)
    state = PantryGraphRAG(PantryRecommendService(graph), llm).run(question, limit=limit, sort=sort)
    return state, graph


# =====================================================================
# 입력 분리 · 별칭 해석
# =====================================================================
class TermParsingTests(unittest.TestCase):
    def test_split_terms_uses_separators_not_spaces(self):
        self.assertEqual(split_terms("계란, 두부\n양파 / 다진 마늘 ;계란"), ["계란", "두부", "양파", "다진 마늘"])
        self.assertEqual(split_terms(" , ,"), [])

    def test_llm_terms_must_appear_in_question(self):
        question = "냉장고에 계란 몇 개랑 두부 반 모가 있어"
        self.assertEqual(terms_in_question(["계란", "두부", "양파", "계란"], question), ["계란", "두부"])

    def test_alias_resolves_to_standard_ingredient_and_unknown_is_reported(self):
        state, _ = run("계란, 두부, 망고")
        result = state["result"]
        egg = result.resolutions[0]
        self.assertEqual(egg.matches[0]["ingr_nm"], "달걀")
        self.assertEqual(egg.matches[0]["matched_by"], "alias")
        self.assertEqual(result.owned_ingredients, ["달걀", "두부"])
        self.assertEqual(result.unknown_terms, ["망고"])
        self.assertEqual(state["term_source"], "rule")

    def test_no_known_ingredient_returns_no_recommendation(self):
        state, graph = run("망고, 파인애플")
        self.assertEqual(state["result"].recommendations, [])
        self.assertEqual(state["answer"]["summary"], "입력한 재료로 찾을 수 있는 레시피가 없습니다.")
        self.assertNotIn("pantry_graphrag.pantry_recommendations_by_coverage", graph.calls)


# =====================================================================
# 추천 · 근거 문장
# =====================================================================
class RecommendationTests(unittest.TestCase):
    def test_sort_options_and_evidence_fields(self):
        coverage, _ = run(sort="coverage")
        missing, _ = run(sort="missing")
        self.assertEqual([r.rcp_id for r in coverage["result"].recommendations], ["r2", "r1"])
        self.assertEqual(coverage["result"].recommendations[0].matched_ingredients, ["달걀", "두부", "양파"])
        self.assertEqual(missing["result"].recommendations[0].missing_count, 1)
        first = coverage["result"].recommendations[1]
        self.assertEqual((first.categories, first.method, first.energy_kcal), (["국&찌개"], "끓이기", 320.0))

    def test_unknown_sort_and_disallowed_statement_are_rejected(self):
        service = PantryRecommendService(FakeGraph())
        with self.assertRaises(ValueError):
            service.recommend(["두부"], sort="random")
        with self.assertRaises(ValueError):
            service._query("recipe_graph_load.link_uses", {})

    def test_korean_particles_follow_final_consonant(self):
        self.assertEqual(josa("두부", "을", "를"), "두부를")
        self.assertEqual(josa("달걀, 두부, 양파", "을", "를"), "달걀, 두부, 양파를")
        self.assertEqual(josa("닭고기김치찌개", "은", "는"), "닭고기김치찌개는")
        self.assertEqual(josa("파스타 소스", "을", "를"), "파스타 소스를")
        self.assertEqual(josa("BLT", "은", "는"), "BLT은(는)")
        self.assertEqual((josa_ro("달걀"), josa_ro("양파"), josa_ro("두부밥")), ("달걀로", "양파로", "두부밥으로"))

    def test_grounded_sentences_are_natural_and_truncate_long_missing_list(self):
        state, _ = run()
        rec = state["result"].recommendations[1]
        reason = grounded_reason(rec)
        self.assertNotIn("(를)", reason)
        self.assertIn("달걀, 두부, 양파를 사용하는 국&찌개 레시피입니다.", reason)
        self.assertIn("조리 방법은 '끓이기'입니다.", reason)
        long_rec = SimpleNamespace(**{**vars(rec), "missing_ingredients": list("가나다라마바사"), "missing_count": 7})
        self.assertIn("외 2개", grounded_reason(long_rec))
        summary = grounded_summary(state["result"])
        self.assertTrue(summary.startswith("보유 재료 달걀, 두부, 양파로 만들 수 있는 레시피 2개를 찾았습니다."))
        self.assertNotIn("(는)", summary)


# =====================================================================
# 대표 이미지 · 조리 과정 (식약처 원본, 표시용)
# =====================================================================
class RecipeStepTests(unittest.TestCase):
    def test_steps_are_attached_in_source_number_order(self):
        state, graph = run()
        by_id = {rec.rcp_id: rec for rec in state["result"].recommendations}
        self.assertEqual([step.step_no for step in by_id["r1"].steps], [1, 3])     # 원본 번호(2 없음) 그대로
        self.assertEqual(by_id["r1"].steps[0], RecipeStep(
            1, "닭가슴살을 한입 크기로 썬다.", "http://www.foodsafetykorea.go.kr/uploadimg/cook/20_00101_1.png"))
        self.assertEqual(by_id["r1"].steps[1].instruction_txt, "대파를 넣고 *한소끔* 끓인다.")   # 원문 그대로
        self.assertIsNone(by_id["r1"].steps[1].image_url)                         # 단계 이미지 없음
        self.assertEqual(by_id["r2"].steps, [])                                   # 단계 데이터 없음
        self.assertEqual(graph.calls.count("recipe_graph_queries.recipe_steps"), 1)  # 추천 전체를 한 번에 조회

    def test_representative_image_url_is_kept_as_stored(self):
        state, _ = run()
        by_id = {rec.rcp_id: rec for rec in state["result"].recommendations}
        self.assertEqual(by_id["r1"].image_url, IMAGE_URLS["r1"])
        self.assertIsNone(by_id["r2"].image_url)

    def test_step_failure_keeps_recommendations_unchanged(self):
        normal, _ = run(sort="missing")
        failed, _ = run(sort="missing", fail_steps=True)
        self.assertEqual(failed["result"].step_error, "ConnectionError")
        self.assertIsNone(normal["result"].step_error)
        strip = lambda result: [{k: v for k, v in vars(rec).items() if k != "steps"}  # noqa: E731
                                for rec in result.recommendations]
        self.assertEqual(strip(failed["result"]), strip(normal["result"]))         # 순서·재료·근거 동일
        self.assertTrue(all(rec.steps == [] for rec in failed["result"].recommendations))
        self.assertEqual(failed["answer"], normal["answer"])                       # 규칙 기반 설명도 동일

    def test_steps_and_images_are_not_sent_to_llm(self):
        llm = FakeLLM({"PantryAnswer": GraphFlowTests.ANSWER})
        state, _ = run(llm=llm)
        context = build_context(state["result"])
        self.assertTrue(all("steps" not in item and "image_url" not in item for item in context))
        self.assertNotIn("한입 크기로", llm.prompts[0])
        self.assertNotIn("uploadimg", llm.prompts[0])
        self.assertEqual(state["answer"]["llm_status"], "ok")

    def test_result_dict_contains_steps_for_screen(self):
        state, _ = run()
        data = state["result"].to_dict()
        first = next(rec for rec in data["recommendations"] if rec["rcp_id"] == "r1")
        self.assertEqual(first["steps"][0]["step_no"], 1)
        self.assertIsNone(data["step_error"])

    def test_display_image_url(self):
        self.assertEqual(display_image_url("http://www.foodsafetykorea.go.kr/uploadimg/cook/a.png"),
                         "https://www.foodsafetykorea.go.kr/uploadimg/cook/a.png")      # 식약처 http → https
        self.assertEqual(display_image_url(" https://www.foodsafetykorea.go.kr/a.jpg "),
                         "https://www.foodsafetykorea.go.kr/a.jpg")
        self.assertEqual(display_image_url("http://example.com/a.png"), "http://example.com/a.png")
        for value in (None, "", "   ", "javascript:alert(1)", "/uploadimg/a.png", "ftp://x/a.png", "http://", 3):
            with self.subTest(value=value):
                self.assertIsNone(display_image_url(value))


# =====================================================================
# LLM 답변 검증
# =====================================================================
class AnswerValidationTests(unittest.TestCase):
    def setUp(self):
        state, graph = run()
        self.result = state["result"]
        self.vocabulary = PantryRecommendService(graph).vocabulary()

    def validate(self, summary, reasons):
        raw = PantryAnswer(summary=summary, recipes=[RecipeReason(rcp_id=i, reason=t) for i, t in reasons])
        return validate_answer(raw, self.result, self.vocabulary)

    def test_recipe_name_containing_ingredient_is_not_a_false_positive(self):
        answer, warnings = self.validate("두부와 달걀을 쓰는 레시피를 골랐습니다.", [
            ("r2", "두부달걀덮밥은 달걀과 두부, 양파를 그대로 쓰는 밥 요리입니다."),
            ("r1", "닭고기김치찌개는 닭가슴살과 김치에 두부와 달걀을 더하는 찌개입니다."),
            ("r1", "중복 설명은 무시됩니다."),
        ])
        self.assertEqual(warnings, [])
        self.assertEqual(answer["sources"], {"r2": "llm", "r1": "llm"})
        self.assertEqual(answer["llm_status"], "ok")
        self.assertIn("닭가슴살", answer["reasons"]["r1"])

    def test_spacing_variant_of_recipe_name_is_also_ignored(self):
        _, warnings = self.validate("추천합니다.", [("r2", "두부달걀덮밥입니다."),
                                                  ("r1", "닭고기 김치찌개는 김치가 들어갑니다.")])
        self.assertEqual(warnings, [])

    def test_out_of_evidence_ingredient_and_recipe_are_replaced(self):
        answer, warnings = self.validate("닭고기와 대파로 만듭니다.", [
            ("r2", "두부달걀덮밥에 닭고기를 넣으면 좋습니다."),     # 닭고기는 r2 재료·보유 재료가 아님
            ("r1", "닭고기김치찌개는 대파와 김치를 씁니다."),
            ("r9", "지어낸 레시피입니다."),
        ])
        self.assertEqual(answer["sources"], {"r1": "llm", "r2": "grounded"})
        self.assertEqual(answer["reasons"]["r2"], grounded_reason(self.result.recommendations[0]))
        self.assertEqual(answer["summary_source"], "grounded")       # 요약의 '닭고기'는 어떤 근거에도 없다
        self.assertEqual(answer["llm_status"], "partial")
        self.assertEqual(len(warnings), 3)
        self.assertTrue(any("r9" in w for w in warnings))

    def test_alias_of_used_ingredient_is_allowed(self):
        answer, warnings = self.validate("계란과 두부가 있으면 됩니다.", [("r2", "계란과 두부를 씁니다."),
                                                                     ("r1", "계란과 김치를 씁니다.")])
        self.assertEqual((warnings, answer["llm_status"]), ([], "ok"))

    def test_single_letter_vocabulary_is_ignored(self):
        self.assertEqual(foreign_ingredients("파를 썰어 물에 담급니다.", {"양파"}, {"파", "물", "대파"}), [])


# =====================================================================
# LangGraph 흐름: LLM 성공 / 실패 / 미설정 구분
# =====================================================================
class GraphFlowTests(unittest.TestCase):
    ANSWER = PantryAnswer(summary="달걀과 두부를 모두 활용할 수 있습니다.", recipes=[
        RecipeReason(rcp_id="r2", reason="두부달걀덮밥은 보유한 달걀, 두부, 양파를 모두 씁니다."),
        RecipeReason(rcp_id="r1", reason="닭고기김치찌개는 김치와 닭가슴살을 더하면 됩니다."),
    ])

    def test_llm_answer_is_used_when_valid(self):
        llm = FakeLLM({"PantryAnswer": self.ANSWER})
        state, _ = run(llm=llm)
        self.assertEqual(state["answer"]["llm_status"], "ok")
        self.assertEqual(set(state["answer"]["sources"].values()), {"llm"})
        self.assertEqual(state["answer"]["summary_source"], "llm")
        self.assertIn('"rcp_id": "r1"', llm.prompts[0])               # 근거 JSON을 프롬프트로 전달
        self.assertEqual(state["term_source"], "rule")                 # 짧은 목록 입력은 LLM 해석을 쓰지 않는다

    def test_llm_failure_falls_back_to_grounded_answer(self):
        state, _ = run(llm=FakeLLM({"PantryAnswer": TimeoutError("timeout")}))
        answer = state["answer"]
        self.assertEqual((answer["llm_status"], answer["llm_error"]), ("failed", "TimeoutError"))
        self.assertEqual(set(answer["sources"].values()), {"grounded"})
        self.assertIn("LLM 답변 생성에 실패해 근거 데이터로 만든 설명을 표시합니다.", state["warnings"])
        self.assertEqual(len(state["result"].recommendations), 2)       # 추천 자체는 Neo4j 결과 그대로

    def test_without_llm_is_disabled_and_grounded(self):
        state, _ = run(llm=None)
        self.assertEqual(state["answer"]["llm_status"], "disabled")
        self.assertEqual(state["warnings"], [])

    def test_sentence_input_uses_llm_terms_and_drops_invented_ones(self):
        llm = FakeLLM({"IngredientTerms": SimpleNamespace(terms=["계란", "두부", "버터"]),
                       "PantryAnswer": self.ANSWER})
        state, _ = run("냉장고에 계란 몇 개랑 두부 반 모가 남았는데 뭐 해먹지?", llm=llm)
        self.assertEqual(state["term_source"], "llm")
        self.assertEqual(state["terms"], ["계란", "두부"])
        self.assertTrue(any("버터" in w for w in state["warnings"]))

    def test_sentence_input_falls_back_to_rule_when_llm_interpretation_fails(self):
        llm = FakeLLM({"IngredientTerms": RuntimeError("down"), "PantryAnswer": RuntimeError("down")})
        state, _ = run("계란 두부 양파 있어요, 뭐 해먹지", llm=llm)
        self.assertEqual(state["term_source"], "vocabulary")             # DB 어휘로 문장에서 재료를 찾는다
        self.assertEqual(state["terms"], ["계란", "두부", "양파"])
        self.assertEqual(state["answer"]["llm_status"], "failed")
        self.assertEqual(len(state["result"].recommendations), 2)

    def test_sentence_input_without_llm_scans_vocabulary(self):
        state, _ = run("냉장고에 다진마늘이랑 대파, 양파가 있어요", llm=None)
        self.assertEqual(state["term_source"], "vocabulary")
        self.assertEqual(state["terms"], ["다진마늘", "대파", "양파"])      # '양파' 속 '파'는 다시 잡지 않는다
        self.assertEqual(state["answer"]["llm_status"], "disabled")


# =====================================================================
# 허용 쿼리는 읽기 전용
# =====================================================================
class ReadOnlyQueryTests(unittest.TestCase):
    WRITE_CLAUSE = re.compile(r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b|apoc\.", re.I)

    def statements(self):
        blocks = {}
        for path in PACKAGE_DIR.glob("*.cypher"):
            for chunk in path.read_text(encoding="utf-8").split("// name: ")[1:]:
                name, _, body = chunk.partition("\n")
                code = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("//"))
                blocks[f"{path.stem}.{name.strip()}"] = code
        return blocks

    def test_allowed_statements_exist_and_have_no_write_clause(self):
        blocks = self.statements()
        for statement in ALLOWED_STATEMENTS:
            with self.subTest(statement=statement):
                self.assertIn(statement, blocks)
                self.assertIsNone(self.WRITE_CLAUSE.search(blocks[statement]), blocks[statement])


# =====================================================================
# 실제 Neo4j (읽기 전용, LLM 미사용)
# =====================================================================
@unittest.skipUnless(os.getenv("NEO4J_URI"), "NEO4J_URI is not configured")
class LivePantryGraphTests(unittest.TestCase):
    def test_egg_tofu_onion_from_auradb(self):
        from recipe_recommender.recipe_graph_repository import RecipeGraphRepository

        graph = RecipeGraphRepository()
        try:
            state = PantryGraphRAG(PantryRecommendService(graph), llm=None).run("계란, 두부, 양파", limit=3)
        finally:
            graph.close()
        result = state["result"]
        self.assertEqual(result.owned_ingredients, ["달걀", "두부", "양파"])
        self.assertEqual(result.resolutions[0].matches[0]["matched_by"], "alias")      # 계란 → 달걀
        self.assertEqual(len(result.recommendations), 3)
        self.assertTrue(all(rec.matched_count == 3 for rec in result.recommendations))
        self.assertTrue(all(rec.rcp_id and rec.categories and rec.all_ingredients for rec in result.recommendations))
        self.assertEqual(state["answer"]["llm_status"], "disabled")
        # 대표 이미지는 기존 rcp.rcp_image_url, 조리 과정은 rcp_step 적재 전이면 빈 목록(오류 아님)이다.
        self.assertTrue(all(display_image_url(rec.image_url) for rec in result.recommendations))
        self.assertIsNone(result.step_error)
        for rec in result.recommendations:
            numbers = [step.step_no for step in rec.steps]
            self.assertEqual(numbers, sorted(numbers))


if __name__ == "__main__":
    unittest.main()
