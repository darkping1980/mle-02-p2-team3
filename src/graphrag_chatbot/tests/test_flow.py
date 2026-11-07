"""오프라인 시험: 실제 DB와 LLM 없이 흐름, 스키마 이름, 측정 로그를 확인합니다.

실행 (graphrag-chatbot 폴더에서):  python -m unittest discover -s tests -t . -v
DB_URL, API 키가 설정돼 있어도 쓰지 않습니다. (DB와 LLM 호출 함수를 가짜로 바꿔서 시험합니다)
이 시험은 실제 Supabase/Claude 동작을 증명하지 않습니다.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import llm  # noqa: E402
import rag  # noqa: E402
import timing  # noqa: E402

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"


def fake_query(calls):
    def run(query, params=None):
        calls.append(query)
        if "limit 500" in query:
            return [{"name": "결제 API", "label": "Service"}]
        if "recursive" in query:
            return [
                {"id": A, "name": "결제 API", "label": "Service", "props": {}},
                {"id": B, "name": "주문 서비스", "label": "Service", "props": {}},
            ]
        if "from graphrag.edges" in query:
            return [{"source": B, "target": A, "type": "CALLS"}]
        return [{"id": A, "name": "결제 API", "label": "Service", "props": {}}]

    return run


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.log_dir = tempfile.mkdtemp()
        patches = [
            mock.patch.object(db, "run_query", fake_query(self.calls)),
            mock.patch.object(
                llm, "complete",
                lambda s, u, max_tokens=400: '{"entities": ["결제 API"], "hops": 2, "intent": "영향 범위"}',
            ),
            mock.patch.object(llm, "stream", lambda s, m, max_tokens=800: iter(["답", "변"])),
            mock.patch.dict(os.environ, {"TIMING_LOG_DIR": self.log_dir}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_answer_flow(self):
        result = rag.answer("결제 API 장애 영향은?")
        self.assertEqual(result["answer"], "답변")
        self.assertEqual(len(result["subgraph"]["nodes"]), 2)
        self.assertEqual(len(result["subgraph"]["edges"]), 1)
        self.assertEqual(result["subgraph"]["seeds"], [A])
        self.assertIn("2-hop", result["steps"][1])

    def test_queries_use_graphrag_schema_only(self):
        rag.answer("결제 API 장애 영향은?")
        self.assertTrue(self.calls)
        for q in self.calls:
            self.assertIn("graphrag.", q)
            self.assertNotIn(" public.", q)
            self.assertNotRegex(q, r"\b(from|join)\s+(nodes|edges)\b")

    def test_unknown_entity_gives_empty_graph_without_db_walk(self):
        with mock.patch.object(
            llm, "complete", lambda s, u, max_tokens=400: '{"entities": ["없는 이름"], "hops": 1}'
        ):
            result = rag.answer("전혀 상관없는 질문")
        self.assertEqual(result["subgraph"]["nodes"], [])
        self.assertIn("찾지 못했습니다", result["answer"])

    def test_timing_log_written_with_all_stages(self):
        rag.answer("결제 API 장애 영향은?")
        lines = Path(self.log_dir, "timing.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        rec = json.loads(lines[0])
        for stage in ("entities_db", "analyze_llm", "explore_db", "first_token", "stream"):
            self.assertIn(stage, rec["stages_ms"])
        self.assertTrue(rec["ok"])
        self.assertLessEqual(len(rec["question"]), 40)

    def test_timing_failure_does_not_break_answer(self):
        with mock.patch.dict(os.environ, {"TIMING_LOG_DIR": "/proc/not-writable"}):
            result = rag.answer("결제 API 장애 영향은?")
        self.assertEqual(result["answer"], "답변")

    def test_timing_is_silent_without_start(self):
        timing._local.trace = None
        with timing.stage("x"):
            pass
        self.assertIsNone(timing.finish())


if __name__ == "__main__":
    unittest.main()
