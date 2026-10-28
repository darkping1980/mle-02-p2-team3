"""Streamlit 화면 테스트(AppTest, 브라우저 없이 실행).

가짜 그래프·가짜 LLM을 주입해 LLM 설명과 규칙 기반 대체 응답이 화면에서 구분되는지 확인한다.
``LiveStreamlitAppTests`` 는 실제 Neo4j AuraDB를 읽기 전용으로 조회한다(LLM 미사용, ``NEO4J_URI`` 필요).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

TASK_DIR = Path(__file__).resolve().parents[2]
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from recipe_recommender.config import load_project_environment  # noqa: E402
from recipe_recommender.pantry_graphrag import PantryAnswer, RecipeReason  # noqa: E402
from recipe_recommender.tests.test_pantry_graphrag import FakeGraph, FakeLLM  # noqa: E402

load_project_environment()
APP_PATH = str(TASK_DIR / "streamlit_app.py")
TIMEOUT = 60


class _ConnectedFakeGraph(FakeGraph):
    def __init__(self, fail_steps: bool = False):
        super().__init__(fail_steps=fail_steps)
        self.driver = Mock()

    def close(self):
        pass


class _StepFailingGraph(_ConnectedFakeGraph):
    """조리 과정 조회만 실패하는 그래프."""

    def __init__(self):
        super().__init__(fail_steps=True)


def texts(at) -> str:
    """화면의 Markdown·알림·배지·캡션 텍스트를 한 문자열로 모은다."""
    parts = []
    for group in (at.markdown, at.success, at.info, at.warning, at.error, at.caption):
        parts.extend(str(element.value) for element in group)
    parts.extend(str(getattr(element, "proto", element)) for element in at.get("badge"))
    return "\n".join(parts)


class StreamlitAppTests(unittest.TestCase):
    def setUp(self):
        st.cache_resource.clear()

    def run_app(self, llm=None, graph_factory=_ConnectedFakeGraph, question=None):
        with patch("recipe_recommender.recipe_graph_repository.RecipeGraphRepository", graph_factory), \
             patch("recipe_recommender.pantry_graphrag.create_llm", return_value=llm):
            at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT).run()
            if question is not None:
                at.text_area[0].set_value(question)
            at.form_submit_button[0].click().run()
        return at

    def test_initial_screen_has_default_input_and_no_result(self):
        with patch("recipe_recommender.recipe_graph_repository.RecipeGraphRepository", _ConnectedFakeGraph), \
             patch("recipe_recommender.pantry_graphrag.create_llm", return_value=None):
            at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT).run()
        self.assertFalse(at.exception)
        self.assertEqual(at.text_area[0].value, "계란, 두부, 양파")
        self.assertIn("레시피 추천", texts(at))

    def test_rule_based_answer_when_llm_is_not_configured(self):
        at = self.run_app(llm=None)
        self.assertFalse(at.exception)
        self.assertEqual(at.info[0].value.startswith("LLM이 설정되지 않아"), True)
        body = texts(at)
        self.assertIn("1. 두부달걀덮밥", body)
        self.assertIn("2. 닭고기김치찌개", body)
        self.assertIn("규칙 기반 설명", body)
        self.assertNotIn("LLM 설명\"", body)
        table = at.table[0].value
        self.assertIn("달걀", table.to_string())                 # 계란 → 달걀(별칭)
        self.assertIn("별칭", table.to_string())

    def test_llm_answer_is_marked_as_llm(self):
        answer = PantryAnswer(summary="달걀과 두부를 모두 쓰는 레시피입니다.", recipes=[
            RecipeReason(rcp_id="r2", reason="두부달걀덮밥은 보유한 달걀, 두부, 양파를 모두 씁니다."),
            RecipeReason(rcp_id="r1", reason="닭고기김치찌개는 김치와 닭가슴살만 더하면 됩니다."),
        ])
        at = self.run_app(llm=FakeLLM({"PantryAnswer": answer}))
        self.assertFalse(at.exception)
        self.assertEqual(len(at.success), 1)
        body = texts(at)
        self.assertIn("두부달걀덮밥은 보유한 달걀, 두부, 양파를 모두 씁니다.", body)
        self.assertIn("LLM 설명", body)
        self.assertNotIn("규칙 기반 설명", body)

    def test_partially_replaced_llm_answer_shows_both_sources(self):
        answer = PantryAnswer(summary="추천합니다.", recipes=[
            RecipeReason(rcp_id="r2", reason="두부달걀덮밥에 닭고기를 넣습니다."),
            RecipeReason(rcp_id="r1", reason="닭고기김치찌개는 김치를 씁니다."),
        ])
        at = self.run_app(llm=FakeLLM({"PantryAnswer": answer}))
        self.assertTrue(any("규칙 기반 설명으로 바꿨습니다" in w.value for w in at.warning))
        body = texts(at)
        self.assertIn("LLM 설명", body)
        self.assertIn("규칙 기반 설명", body)

    def test_llm_failure_shows_rule_based_fallback(self):
        at = self.run_app(llm=FakeLLM({"PantryAnswer": TimeoutError("timeout")}))
        self.assertFalse(at.exception)
        self.assertEqual(len(at.error), 1)
        self.assertIn("TimeoutError", at.error[0].value)
        self.assertIn("규칙 기반 설명", texts(at))
        self.assertIn("1. 두부달걀덮밥", texts(at))              # 추천 자체는 정상 표시

    def test_unknown_ingredient_is_reported(self):
        at = self.run_app(llm=None, question="망고, 파인애플")
        self.assertIn("DB에 없음", at.table[0].value.to_string())
        self.assertIn("추천할 레시피가 없습니다", texts(at))

    def test_recipe_images_and_steps_are_shown(self):
        at = self.run_app(llm=None)
        self.assertFalse(at.exception)
        urls = [url for image in at.image for url in image.value]
        # 대표 이미지(r1)와 1단계 이미지만 있다. 식약처 http URL은 https로 바꿔 표시한다.
        self.assertEqual(urls, ["https://www.foodsafetykorea.go.kr/uploadimg/cook/10_00101_2.png",
                                "https://www.foodsafetykorea.go.kr/uploadimg/cook/20_00101_1.png"])
        self.assertEqual([expander.label for expander in at.expander
                          if expander.label.startswith("조리 과정")], ["조리 과정 2단계 보기"])
        steps = next(expander for expander in at.expander if expander.label.startswith("조리 과정"))
        step_texts = [str(element.value) for element in steps.markdown]
        # 원본 번호를 그대로 쓰고, 설명의 '*'·'.'은 서식이 아닌 글자로 보이게 이스케이프한다.
        self.assertEqual(step_texts, ["**1.** 닭가슴살을 한입 크기로 썬다\\.",
                                      "**3.** 대파를 넣고 \\*한소끔\\* 끓인다\\."])
        self.assertEqual([url for image in steps.image for url in image.value],
                         ["https://www.foodsafetykorea.go.kr/uploadimg/cook/20_00101_1.png"])   # 3단계는 이미지 생략
        self.assertIn("이 레시피는 조리 과정 데이터가 없습니다.", texts(at))       # r2: 단계 없음, 설명만 생략

    def test_step_query_failure_keeps_recommendations(self):
        at = self.run_app(llm=None, graph_factory=_StepFailingGraph)
        self.assertFalse(at.exception)
        self.assertTrue(any("조리 과정을 불러오지 못했습니다(ConnectionError)" in w.value for w in at.warning))
        body = texts(at)
        self.assertIn("1. 두부달걀덮밥", body)
        self.assertIn("2. 닭고기김치찌개", body)
        self.assertEqual([e.label for e in at.expander if e.label.startswith("조리 과정")], [])
        self.assertNotIn("조리 과정 데이터가 없습니다", body)                     # 장애와 데이터 없음을 구분

    def test_neo4j_connection_failure_is_shown(self):
        def broken():
            raise ConnectionError("AuraDB unreachable")

        at = self.run_app(llm=None, graph_factory=broken)
        self.assertEqual(len(at.error), 1)
        self.assertIn("AuraDB unreachable", at.error[0].value)
        self.assertEqual(len(at.markdown), 0)


@unittest.skipUnless(os.getenv("NEO4J_URI"), "NEO4J_URI is not configured")
class LiveStreamlitAppTests(unittest.TestCase):
    def test_default_input_queries_real_auradb(self):
        st.cache_resource.clear()
        with patch("recipe_recommender.pantry_graphrag.create_llm", return_value=None):
            at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT).run()
            at.form_submit_button[0].click().run()
        self.assertFalse(at.exception)
        body = texts(at)
        self.assertIn("1. 두부해물완자", body)                     # 보유 재료 3개를 모두 쓰는 레시피 우선
        self.assertIn("Neo4j AuraDB 연결됨", body)
        st.cache_resource.clear()                                  # 드라이버를 프로세스 종료 전에 놓아 준다


if __name__ == "__main__":
    unittest.main()
