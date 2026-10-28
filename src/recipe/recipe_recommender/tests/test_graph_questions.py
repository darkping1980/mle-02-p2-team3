"""그래프 관계 탐색(과제 질문 Q1~Q5, 1·2·3-hop) 테스트.

    Mock 기반          ``FakeQuestionGraph`` 로 Service 분기(중복 제거·0건·대상 없음·별칭·예외 전파)와
                       허용 쿼리·hop 선언, Streamlit 모드 B 화면을 검증한다. DB 연결 없음.
    실제 DB(읽기 전용)  ``LiveGraphQuestionTests`` 가 AuraDB 조회 결과를 같은 시점의 PostgreSQL 스냅샷
                       (READ ONLY 트랜잭션)에서 계산한 기대값과 대조한다. ``NEO4J_URI``·``DB_URL`` 필요.
    고정 값(시점 의존)  ``LiveSnapshotValueTests`` 는 2026-10-24 적재 데이터의 실제 값을 확인한다.
                       데이터를 다시 적재하면 바뀔 수 있으므로 실패하면 먼저 데이터 변경 여부를 확인한다.
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from recipe_recommender.config import PACKAGE_DIR, load_project_environment  # noqa: E402
from recipe_recommender.graph_question_service import (  # noqa: E402
    ALLOWED_STATEMENTS, QUESTIONS, GraphQuestionService,
)
from recipe_recommender.name_normalization import normalize_name  # noqa: E402
from recipe_recommender.recipe_graph_repository import RecipeGraphRepository  # noqa: E402
from recipe_recommender.tests.test_pantry_graphrag import INGREDIENTS, RECIPES, STEPS, FakeGraph  # noqa: E402

load_project_environment()
APP_PATH = str(TASK_DIR / "streamlit_app.py")
TIMEOUT = 60
CATEGORY_IDS = {"국&찌개": "c1", "밥": "c2"}
_MAPPER = RecipeGraphRepository(driver=Mock(), database="neo4j")      # Cypher 원문 조회 전용(연결 없음)


class FakeQuestionGraph(FakeGraph):
    """``FakeGraph`` (추천용)에 그래프 탐색 쿼리를 더한 가짜 Repository. 데이터는 r1·r2 두 레시피다.

    ``duplicate_rows`` 이면 Q1 쿼리가 같은 레시피를 두 번 돌려준다(한 입력어가 두 식재료에 걸린 상황).
    ``fail`` 이면 그래프 탐색 쿼리가 ``ConnectionError`` 를 낸다.
    """

    def __init__(self, duplicate_rows: bool = False, fail: bool = False):
        super().__init__()
        self.duplicate_rows = duplicate_rows
        self.fail = fail
        self.driver = Mock()
        self.mapper.select_list = self._select_list_with_questions

    def close(self):
        pass

    def statement_text(self, statement):
        return _MAPPER.statement_text(statement)

    @staticmethod
    def _uses(rcp_id):
        return set(RECIPES[rcp_id]["ingredients"])

    def query_example(self, name, parameters):
        if self.fail and name != "ingredient_name_candidates":
            raise ConnectionError("graph unavailable")
        if name == "recipes_by_ingredient_term":
            matches = self._matches(parameters["term_norm"])
            rows = [{"ingr_id": ingr_id, "ingredient": nm, "rcp_id": rcp_id, "rcp_seq": rec["rcp_seq"],
                     "rcp_nm": rec["rcp_nm"]}
                    for ingr_id, nm, _ in matches for rcp_id, rec in RECIPES.items() if nm in rec["ingredients"]]
            rows.sort(key=lambda row: (row["rcp_nm"], row["rcp_id"]))
            self.calls.append(f"recipe_graph_queries.{name}")
            return rows + rows if self.duplicate_rows else rows
        if name == "similar_recipes":
            self.calls.append(f"recipe_graph_queries.{name}")
            base = parameters["rcp_id"]
            rows = []
            for other in RECIPES:
                shared = self._uses(base) & self._uses(other)
                if other != base and shared:
                    union = len(self._uses(base) | self._uses(other))
                    rows.append({"rcp_id": other, "rcp_nm": RECIPES[other]["rcp_nm"], "common_count": len(shared),
                                 "common_ingredients": sorted(shared), "jaccard": len(shared) / union})
            return sorted(rows, key=lambda r: (-r["common_count"], -r["jaccard"], r["rcp_id"]))
        return super().query_example(name, parameters)

    def _select_list_with_questions(self, statement, parameters):
        if self.fail and statement.startswith("graph_questions.") and statement not in (
                "graph_questions.recipe_options", "graph_questions.category_options"):
            raise ConnectionError("graph unavailable")
        if statement == "graph_questions.recipe_options":
            self.calls.append(statement)
            return sorted(({"rcp_id": rcp_id, "rcp_nm": rec["rcp_nm"], "rcp_seq": rec["rcp_seq"]}
                           for rcp_id, rec in RECIPES.items()), key=lambda r: (r["rcp_nm"], r["rcp_seq"]))
        if statement == "graph_questions.category_options":
            self.calls.append(statement)
            return [{"rcp_cat_id": cid, "rcp_cat_nm": nm} for nm, cid in sorted(CATEGORY_IDS.items())]
        if statement == "graph_questions.similar_recipe_categories":
            self.calls.append(statement)
            base, counts = parameters["rcp_id"], {}
            for other, rec in RECIPES.items():
                common = len(self._uses(base) & self._uses(other))
                if other != base and common >= parameters["min_common"]:
                    for category in rec["categories"]:
                        entry = counts.setdefault(category, [0, 0, []])
                        entry[0] += 1
                        entry[1] = max(entry[1], common)
                        entry[2].append(rec["rcp_nm"])
            return [{"rcp_cat_nm": c, "recipe_count": n, "max_common_count": m, "sample_recipes": names[:5]}
                    for c, (n, m, names) in sorted(counts.items(), key=lambda kv: (-kv[1][0], kv[0]))]
        if statement == "graph_questions.category_ingredients":
            self.calls.append(statement)
            members = [rec for rec in RECIPES.values() if parameters["rcp_cat_nm"] in rec["categories"]]
            counts: dict[str, int] = {}
            for rec in members:
                for name in set(rec["ingredients"]):
                    counts[name] = counts.get(name, 0) + 1
            ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            return [{"ingr_nm": n, "recipe_count": c, "category_recipe_count": len(members),
                     "category_ingredient_count": len(ranked)} for n, c in ranked[:parameters["limit"]]]
        return self._select_list(statement, parameters)


def service(**kwargs) -> tuple[GraphQuestionService, FakeQuestionGraph]:
    graph = FakeQuestionGraph(**kwargs)
    return GraphQuestionService(graph), graph


# =====================================================================
# Mock 기반: Service 분기
# =====================================================================
class GraphQuestionServiceTests(unittest.TestCase):
    def test_q1_one_hop_recipes_using_ingredient(self):
        svc, graph = service()
        answer = svc.recipes_using_ingredient("두부")
        self.assertEqual((answer.status, answer.row_count), ("ok", 2))
        self.assertEqual([row["rcp_nm"] for row in answer.rows], ["닭고기김치찌개", "두부달걀덮밥"])   # 이름 순
        self.assertEqual(answer.resolved, [{"ingr_id": "i2", "ingr_nm": "두부", "matched_by": "name"}])
        self.assertEqual(answer.question_text, "두부를 사용하는 레시피는 무엇인가?")
        self.assertIn("recipe_graph_queries.ingredient_name_candidates", graph.calls)

    def test_q1_alias_resolves_to_standard_ingredient(self):
        answer = service()[0].recipes_using_ingredient(" 계란 ")
        self.assertEqual(answer.resolved[0]["ingr_nm"], "달걀")
        self.assertEqual(answer.resolved[0]["matched_by"], "alias")
        self.assertIn("별칭", answer.message)
        self.assertEqual(answer.parameters, {"term_norm": "계란"})
        self.assertEqual({row["ingredient"] for row in answer.rows}, {"달걀"})

    def test_q1_duplicate_recipe_rows_are_removed(self):
        answer = service(duplicate_rows=True)[0].recipes_using_ingredient("두부")
        self.assertEqual([row["rcp_id"] for row in answer.rows], ["r1", "r2"])            # 4행 → 2행

    def test_q1_unknown_or_blank_ingredient_is_not_found_without_recipe_query(self):
        for term in ("망고스틴", "   "):
            with self.subTest(term=term):
                svc, graph = service()
                answer = svc.recipes_using_ingredient(term)
                self.assertEqual((answer.status, answer.rows), ("not_found", []))
                self.assertNotIn("recipe_graph_queries.recipes_by_ingredient_term", graph.calls)

    def test_q2_two_hop_similar_recipes(self):
        answer = service()[0].similar_recipes("r1")
        self.assertEqual(answer.status, "ok")
        self.assertEqual(answer.rows[0]["rcp_id"], "r2")
        self.assertEqual(answer.rows[0]["common_count"], 3)                     # 달걀·두부·양파, 레시피는 한 번만
        self.assertAlmostEqual(answer.rows[0]["jaccard"], 3 / 7)
        self.assertEqual(answer.question_text, "닭고기김치찌개와 공통 재료를 사용하는 다른 레시피는 무엇인가?")

    def test_q3_three_hop_categories_and_threshold(self):
        svc = service()[0]
        answer = svc.similar_recipe_categories("r1", 3)
        self.assertEqual(answer.rows, [{"rcp_cat_nm": "밥", "recipe_count": 1, "max_common_count": 3,
                                        "sample_recipes": ["두부달걀덮밥"]}])
        empty = svc.similar_recipe_categories("r1", 4)                         # 공통 재료 4개 이상인 레시피 없음
        self.assertEqual((empty.status, empty.rows), ("empty", []))
        self.assertIn("4개 이상", empty.message)
        self.assertEqual(svc.similar_recipe_categories("r1", 0).parameters["min_common"], 1)   # 최소 1로 보정

    def test_q4_two_hop_category_ingredients(self):
        svc = service()[0]
        answer = svc.category_ingredients("밥", 2)
        self.assertEqual([row["ingr_nm"] for row in answer.rows], ["달걀", "두부"])         # 같은 수면 이름 순
        self.assertEqual(answer.rows[0]["category_ingredient_count"], 4)                  # 자르기 전 전체
        self.assertEqual(svc.category_ingredients("밥", 999).parameters["limit"], 50)      # 상한 50
        missing = svc.category_ingredients("없는분류")
        self.assertEqual(missing.status, "not_found")

    def test_q5_one_hop_steps_in_source_order_and_empty(self):
        svc = service()[0]
        answer = svc.recipe_steps("r1")
        # Service는 Cypher 결과 순서를 바꾸지 않는다(원본 번호 정렬은 recipe_steps의 ORDER BY 담당, 실제 DB 테스트로 확인).
        self.assertEqual([row["step_no"] for row in answer.rows], [3, 1])
        self.assertEqual(svc.recipe_steps("r2").status, "empty")           # 단계 데이터 없음
        self.assertEqual(svc.recipe_steps("r9").status, "not_found")       # 없는 레시피

    def test_unknown_recipe_is_not_found_for_recipe_questions(self):
        svc, graph = service()
        for method in (svc.similar_recipes, svc.similar_recipe_categories, svc.recipe_steps):
            with self.subTest(method=method.__name__):
                self.assertEqual(method("missing").status, "not_found")
        self.assertNotIn("recipe_graph_queries.similar_recipes", graph.calls)

    def test_db_errors_propagate_to_caller(self):
        svc = service(fail=True)[0]
        with self.assertRaises(ConnectionError):
            svc.recipes_using_ingredient("두부")
        with self.assertRaises(ConnectionError):
            svc.similar_recipe_categories("r1")

    def test_disallowed_statement_is_rejected(self):
        with self.assertRaises(ValueError):
            service()[0]._query("recipe_graph_load.link_uses", {})


# =====================================================================
# Mock 기반: Cypher 정의 · hop 선언
# =====================================================================
class GraphQuestionDefinitionTests(unittest.TestCase):
    WRITE_CLAUSE = re.compile(r"\b(CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b|apoc\.", re.I)

    def test_allowed_statements_exist_and_are_read_only(self):
        for statement in ALLOWED_STATEMENTS:
            with self.subTest(statement=statement):
                code = "\n".join(line for line in _MAPPER.statement_text(statement).splitlines()
                                 if not line.lstrip().startswith("//"))
                self.assertIsNone(self.WRITE_CLAUSE.search(code), code)

    def test_each_question_runs_an_allowed_statement(self):
        self.assertEqual(sorted(QUESTIONS), ["Q1", "Q2", "Q3", "Q4", "Q5"])
        for question in QUESTIONS.values():
            self.assertIn(question.statement, ALLOWED_STATEMENTS)

    def test_declared_hop_matches_path_and_cypher(self):
        expected = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 2, "Q5": 1}
        for key, question in QUESTIONS.items():
            with self.subTest(key=key):
                rel_types = re.findall(r"\[:(\w+)\]", question.path)
                self.assertEqual(question.hop, expected[key])
                self.assertEqual(len(rel_types), question.hop)                       # 경로의 관계 수 = hop
                code = _MAPPER.statement_text(question.statement)
                for rel_type in rel_types:
                    self.assertIn(f"[:{rel_type}]", code)                            # 실행 Cypher가 그 관계를 건넌다

    def test_three_hop_cypher_traverses_uses_twice_then_category(self):
        code = _MAPPER.statement_text("graph_questions.similar_recipe_categories")
        self.assertIn("(base:rcp {rcp_id: $rcp_id})-[:RCP_USES]->(shared:ingr)<-[:RCP_USES]-(other:rcp)", code)
        self.assertIn("(other)-[:RCP_IN_RECIPE_CATEGORY]->(c:rcp_cat)", code)
        self.assertIn("count(DISTINCT shared)", code)                                # 공통 재료가 여러 개여도 1회
        self.assertIn("count(DISTINCT other)", code)


# =====================================================================
# Mock 기반: Streamlit 모드 B · 모드 A 회귀
# =====================================================================
def texts(at) -> str:
    parts = []
    for group in (at.markdown, at.success, at.info, at.warning, at.error, at.caption):
        parts.extend(str(element.value) for element in group)
    parts.extend(str(getattr(element, "proto", element)) for element in at.get("badge"))
    return "\n".join(parts)


class GraphExplorerAppTests(unittest.TestCase):
    def setUp(self):
        st.cache_resource.clear()

    def open_graph_mode(self, graph_factory=FakeQuestionGraph):
        with patch("recipe_recommender.recipe_graph_repository.RecipeGraphRepository", graph_factory), \
             patch("recipe_recommender.pantry_graphrag.create_llm", return_value=None):
            at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT).run()
            at.segmented_control(key="app_mode").set_value("graph").run()
        return at

    def ask(self, at, key, graph_factory=FakeQuestionGraph, **inputs):
        with patch("recipe_recommender.recipe_graph_repository.RecipeGraphRepository", graph_factory), \
             patch("recipe_recommender.pantry_graphrag.create_llm", return_value=None):
            at.radio(key="graph_question").set_value(key).run()
            if "graph_term" in inputs:
                at.text_input(key="graph_term").set_value(inputs["graph_term"])
            if "graph_min_common" in inputs:
                at.number_input(key="graph_min_common").set_value(inputs["graph_min_common"])
            at.form_submit_button[0].click().run()
        return at

    def test_mode_b_hides_pantry_form_and_lists_five_questions(self):
        at = self.open_graph_mode()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.text_area), 0)                                    # 냉장고 재료 입력란 없음
        self.assertEqual(len(at.radio(key="graph_question").options), 5)
        self.assertIn("대상을 고르고", texts(at))

    def test_q1_shows_hop_path_and_neo4j_rows(self):
        at = self.ask(self.open_graph_mode(), "Q1")
        self.assertFalse(at.exception)
        body = texts(at)
        self.assertIn("두부를 사용하는 레시피는 무엇인가?", body)
        self.assertIn("Q1 · 1-hop", body)
        self.assertIn("LLM 미사용", body)
        self.assertEqual(at.code[0].value, QUESTIONS["Q1"].path)
        table = at.dataframe[0].value
        self.assertEqual(list(table["레시피"]), ["닭고기김치찌개", "두부달걀덮밥"])
        # 실행 Cypher·파라미터는 화면에 보이지 않는다(개발 중에는 RECIPE_QUERY_LOG 터미널 로그로 확인).
        self.assertEqual(len(at.code), 1)
        self.assertFalse(any("실행 Cypher" in e.label for e in at.expander))
        self.assertNotIn("$term_norm", texts(at))

    def test_q3_three_hop_table(self):
        at = self.ask(self.open_graph_mode(), "Q3", graph_min_common=3)
        self.assertFalse(at.exception)
        self.assertIn("Q3 · 3-hop", texts(at))
        table = at.dataframe[0].value
        self.assertEqual(table.iloc[0]["요리 분류"], "밥")
        self.assertEqual(int(table.iloc[0]["레시피 수"]), 1)

    def test_q5_steps_table_uses_https_image_urls(self):
        at = self.ask(self.open_graph_mode(), "Q5")
        urls = list(at.dataframe[0].value["단계 이미지"])
        self.assertTrue(any(str(url).startswith("https://www.foodsafetykorea.go.kr/") for url in urls))   # http → https
        self.assertFalse(any(str(url).startswith("http://") for url in urls))

    def test_unknown_ingredient_and_empty_result_are_explained(self):
        at = self.ask(self.open_graph_mode(), "Q1", graph_term="망고스틴")
        self.assertTrue(any("DB의 표준 식재료명·별칭에 없습니다" in w.value for w in at.warning))
        self.assertEqual(len(at.dataframe), 0)
        at = self.ask(at, "Q3", graph_min_common=10)
        self.assertTrue(any("10개 이상인 다른 레시피가 없습니다" in i.value for i in at.info))
        self.assertIn("0건", texts(at))

    def test_graph_db_error_is_shown_without_crash(self):
        failing = lambda: FakeQuestionGraph(fail=True)  # noqa: E731
        at = self.ask(self.open_graph_mode(failing), "Q2", graph_factory=failing)
        self.assertFalse(at.exception)
        self.assertTrue(any("ConnectionError" in e.value for e in at.error))

    def test_pantry_mode_is_unchanged(self):
        with patch("recipe_recommender.recipe_graph_repository.RecipeGraphRepository", FakeQuestionGraph), \
             patch("recipe_recommender.pantry_graphrag.create_llm", return_value=None):
            at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT).run()
            at.form_submit_button[0].click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.segmented_control(key="app_mode").value, "pantry")
        self.assertIn("1. 두부달걀덮밥", texts(at))
        self.assertTrue(any(e.label.startswith("조리 과정") for e in at.expander))     # 조리 단계 표시 유지
        self.assertTrue(at.image)                                                    # 대표 이미지 유지


# =====================================================================
# 실제 Neo4j (읽기 전용) — 같은 시점 PostgreSQL 스냅샷과 대조
# =====================================================================
@unittest.skipUnless(os.getenv("NEO4J_URI") and os.getenv("DB_URL"), "NEO4J_URI and DB_URL are required")
class LiveGraphQuestionTests(unittest.TestCase):
    """AuraDB 결과를 PostgreSQL ``recipe`` 원천(READ ONLY)에서 Python으로 계산한 기대값과 비교한다."""

    BASE_SEQ = "137"           # 된장 두부찌개

    @classmethod
    def setUpClass(cls):
        from recipe_recommender.setup.recipe_graph_source_repository import RecipeGraphSourceRepository

        cls.snapshot = RecipeGraphSourceRepository().read_snapshot()
        cls.graph = RecipeGraphRepository()
        cls.service = GraphQuestionService(cls.graph)
        snap = cls.snapshot
        cls.uses: dict[str, set[str]] = {}
        for row in snap.uses:
            cls.uses.setdefault(row["rcp_id"], set()).add(row["ingr_id"])
        cls.recipes = {row["rcp_id"]: row for row in snap.recipes}
        cls.ingredient_names = {row["ingr_id"]: row["ingr_nm"] for row in snap.ingredients}
        cat_names = {row["rcp_cat_id"]: row["rcp_cat_nm"] for row in snap.recipe_categories}
        cls.categories: dict[str, set[str]] = {}
        for row in snap.recipe_category_links:
            cls.categories.setdefault(row["rcp_id"], set()).add(cat_names[row["rcp_cat_id"]])
        cls.base = next(row["rcp_id"] for row in snap.recipes if row["rcp_seq"] == cls.BASE_SEQ)

    @classmethod
    def tearDownClass(cls):
        cls.graph.close()

    def resolve(self, term):
        names = {row["ingr_id"]: {normalize_name(row["ingr_nm"])} for row in self.snapshot.ingredients}
        for row in self.snapshot.aliases:
            names[row["ingr_id"]].add(normalize_name(row["ingr_als_nm"]))
        return {ingr_id for ingr_id, values in names.items() if normalize_name(term) in values}

    def common(self, other):
        return self.uses.get(self.base, set()) & self.uses.get(other, set())

    def test_q1_matches_postgres_including_alias(self):
        for term in ("두부", "계란"):
            with self.subTest(term=term):
                ids = self.resolve(term)
                expected = {rcp_id for rcp_id, ingr in self.uses.items() if ingr & ids}
                answer = self.service.recipes_using_ingredient(term)
                actual = [row["rcp_id"] for row in answer.rows]
                self.assertEqual(len(actual), len(set(actual)))                    # 중복 없음
                self.assertEqual(set(actual), expected)
                names = [row["rcp_nm"] for row in answer.rows]
                self.assertEqual(names, sorted(names))                             # 레시피명 순

    def test_q1_unknown_ingredient(self):
        self.assertEqual(self.service.recipes_using_ingredient("존재하지않는재료").status, "not_found")

    def test_q2_matches_postgres_top20_order(self):
        base_total = len(self.uses[self.base])
        expected = []
        for other, ingr in self.uses.items():
            shared = self.common(other)
            if other != self.base and shared:
                jaccard = len(shared) / (base_total + len(ingr) - len(shared))
                expected.append((other, len(shared), jaccard))
        expected.sort(key=lambda item: (-item[1], -item[2], item[0]))
        rows = self.service.similar_recipes(self.base).rows
        self.assertEqual([(r["rcp_id"], r["common_count"]) for r in rows], [(e[0], e[1]) for e in expected[:20]])
        for row, item in zip(rows, expected):
            self.assertAlmostEqual(row["jaccard"], item[2])
            names = {self.ingredient_names[i] for i in self.common(row["rcp_id"])}
            self.assertEqual(set(row["common_ingredients"]), names)              # 공통 재료가 실제로 겹친다

    def test_q3_matches_postgres_category_counts(self):
        for k in (1, 3):
            with self.subTest(min_common=k):
                expected: dict[str, list[int]] = {}
                for other in self.uses:
                    n = len(self.common(other))
                    if other != self.base and n >= k:
                        for category in self.categories[other]:
                            entry = expected.setdefault(category, [0, 0])
                            entry[0] += 1
                            entry[1] = max(entry[1], n)
                rows = self.service.similar_recipe_categories(self.base, k).rows
                self.assertEqual({r["rcp_cat_nm"]: [r["recipe_count"], r["max_common_count"]] for r in rows}, expected)
                counts = [r["recipe_count"] for r in rows]
                self.assertEqual(counts, sorted(counts, reverse=True))

    def test_q3_sample_recipes_really_have_three_hop_paths(self):
        from neo4j import READ_ACCESS

        rows = self.service.similar_recipe_categories(self.base, 3).rows
        cypher = ("MATCH p = (b:rcp {rcp_id: $base})-[:RCP_USES]->(:ingr)<-[:RCP_USES]-(o:rcp {rcp_nm: $name})"
                  "-[:RCP_IN_RECIPE_CATEGORY]->(:rcp_cat {rcp_cat_nm: $cat}) RETURN DISTINCT length(p) AS hops")
        with self.graph.driver.session(database=self.graph.database, default_access_mode=READ_ACCESS) as session:
            for row in rows:
                for name in row["sample_recipes"]:
                    hops = session.execute_read(lambda tx: [r["hops"] for r in tx.run(
                        cypher, base=self.base, name=name, cat=row["rcp_cat_nm"])])
                    self.assertEqual(hops, [3], (row["rcp_cat_nm"], name))

    def test_q4_matches_postgres(self):
        members = {rcp_id for rcp_id, cats in self.categories.items() if "반찬" in cats}
        counts: dict[str, int] = {}
        for rcp_id in members:
            for ingr_id in self.uses.get(rcp_id, ()):
                name = self.ingredient_names[ingr_id]
                counts[name] = counts.get(name, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        rows = self.service.category_ingredients("반찬", 20).rows
        self.assertEqual([(r["ingr_nm"], r["recipe_count"]) for r in rows], ranked[:20])
        self.assertEqual(rows[0]["category_recipe_count"], len(members))
        self.assertEqual(rows[0]["category_ingredient_count"], len(counts))

    def test_q5_matches_postgres_step_order_and_text(self):
        expected = sorted((row["step_no"], row["rcp_step_instruction_txt"])
                          for row in self.snapshot.steps if row["rcp_id"] == self.base)
        rows = self.service.recipe_steps(self.base).rows
        self.assertEqual([(r["step_no"], r["instruction_txt"]) for r in rows], expected)

    def test_recipe_options_cover_all_recipes(self):
        self.assertEqual({row["rcp_id"] for row in self.service.recipe_options()}, set(self.recipes))


@unittest.skipUnless(os.getenv("NEO4J_URI"), "NEO4J_URI is not configured")
class LiveGraphExplorerAppTests(unittest.TestCase):
    """실제 AuraDB를 읽는 Streamlit 모드 B 화면(LLM 미사용). 기본 대상(된장 두부찌개)으로 5개 질문을 모두 조회한다."""

    def test_all_five_questions_render_real_rows(self):
        st.cache_resource.clear()
        with patch("recipe_recommender.pantry_graphrag.create_llm", return_value=None):
            at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT).run()
            at.segmented_control(key="app_mode").set_value("graph").run()
            for key in QUESTIONS:
                with self.subTest(key=key):
                    at.radio(key="graph_question").set_value(key).run()
                    at.form_submit_button[0].click().run()
                    self.assertFalse(at.exception)
                    self.assertIn(f"{key} · {QUESTIONS[key].hop}-hop", texts(at))
                    self.assertGreater(len(at.dataframe[0].value), 0)
            at.radio(key="graph_question").set_value("Q3").run()
            at.form_submit_button[0].click().run()
            self.assertEqual(at.dataframe[0].value.iloc[0]["요리 분류"], "국&찌개")      # 시점 의존(2026-10-24)
        st.cache_resource.clear()


@unittest.skipUnless(os.getenv("NEO4J_URI"), "NEO4J_URI is not configured")
class LiveSnapshotValueTests(unittest.TestCase):
    """2026-10-24 AuraDB 적재 데이터의 실제 값(시점 의존). 데이터를 다시 적재하면 갱신이 필요할 수 있다."""

    @classmethod
    def setUpClass(cls):
        cls.graph = RecipeGraphRepository()
        cls.service = GraphQuestionService(cls.graph)
        cls.base = next(r["rcp_id"] for r in cls.service.recipe_options() if r["rcp_seq"] == "137")

    @classmethod
    def tearDownClass(cls):
        cls.graph.close()

    def test_recorded_values(self):
        self.assertEqual(self.service.recipes_using_ingredient("두부").row_count, 110)
        self.assertEqual(self.service.recipes_using_ingredient("계란").row_count, 186)       # 별칭 → 달걀
        top = self.service.similar_recipes(self.base).rows[0]
        self.assertEqual((top["rcp_nm"], top["common_count"]), ("부대된장찌개", 5))
        q3 = self.service.similar_recipe_categories(self.base, 3).rows
        self.assertEqual([(r["rcp_cat_nm"], r["recipe_count"]) for r in q3],
                         [("국&찌개", 26), ("반찬", 10), ("밥", 4), ("일품", 3), ("기타", 1)])
        q4 = self.service.category_ingredients("반찬", 3).rows
        self.assertEqual([(r["ingr_nm"], r["recipe_count"]) for r in q4], [("양파", 227), ("소금", 200), ("설탕", 186)])
        self.assertEqual((q4[0]["category_recipe_count"], q4[0]["category_ingredient_count"]), (574, 263))
        self.assertEqual([r["step_no"] for r in self.service.recipe_steps(self.base).rows], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
