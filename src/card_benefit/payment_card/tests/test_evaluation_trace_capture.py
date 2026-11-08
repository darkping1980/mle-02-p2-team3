"""Local evaluation trace capture remains independent from app_log persistence."""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from card_benefit.payment_card.db_pipeline_origin_search import execution_log
from card_benefit.payment_card.db_pipeline_origin_search.card_graphrag import CardGraphRAG

RUNNER_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "evaluation" / "run_questionnaire_evaluation.py"
)
SPEC = importlib.util.spec_from_file_location("run_questionnaire_evaluation", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(RUNNER)


class EvaluationTraceGateTests(unittest.TestCase):
    def test_local_trace_is_enabled_with_database_logging_off(self):
        with patch.dict(os.environ, {
            "APP_ENV": "development",
            "APP_EVALUATION_TRACE_ENABLED": "1",
            "APP_DB_LOG_ENABLED": "off",
            "APP_DB_LLM_TRACE_ENABLED": "0",
        }, clear=False):
            self.assertFalse(execution_log.app_db_log_enabled())
            self.assertFalse(execution_log.app_db_llm_trace_enabled())
            self.assertTrue(execution_log.evaluation_llm_trace_enabled())
            instance = CardGraphRAG.__new__(CardGraphRAG)
            instance.model = "stub-model"
            state = instance._initial_state(
                "synthetic question", request_id="request-1", question_id="Q-1",
                capture_diagnostics=True,
            )
            self.assertTrue(state["diagnostics_enabled"])
            self.assertEqual(state["question_id"], "Q-1")

    def test_local_trace_is_off_without_explicit_dev_opt_in(self):
        with patch.dict(os.environ, {
            "APP_ENV": "production",
            "APP_EVALUATION_TRACE_ENABLED": "1",
            "APP_DB_LOG_ENABLED": "off",
        }, clear=False):
            self.assertFalse(execution_log.evaluation_llm_trace_enabled())
        with patch.dict(os.environ, {
            "APP_ENV": "development",
            "APP_EVALUATION_TRACE_ENABLED": "0",
            "APP_DB_LOG_ENABLED": "on",
        }, clear=False):
            self.assertFalse(execution_log.evaluation_llm_trace_enabled())


class EvaluationTracePersistenceTests(unittest.TestCase):
    def test_trace_redaction_hash_and_stage_validation_use_saved_prompt(self):
        event = execution_log.sanitize_llm_trace_event({
            "stage": "ANSWER",
            "question_id": "Q-2",
            "prompt_text": "Contact test.user@example.com; token Bearer abcdef1234567890",
            "raw_output": {"answer": "call 010-1234-5678", "api_key": "secret-value"},
            "input_snapshot": {"access_token": "secret-value", "evidence": ["public quote"]},
        })
        self.assertTrue(event["prompt_redacted"])
        self.assertNotIn("test.user@example.com", event["prompt_text"])
        self.assertEqual(
            event["prompt_sha256"],
            __import__("hashlib").sha256(event["prompt_text"].encode("utf-8")).hexdigest(),
        )
        self.assertNotIn("010-1234-5678", json.dumps(event, ensure_ascii=False))
        self.assertNotIn("secret-value", json.dumps(event, ensure_ascii=False))
        check = RUNNER._trace_validation([event], ["ANSWER"])
        self.assertEqual(check["status"], "COMPLETE")
        retrieve = {
            "stage": "RETRIEVE",
            "input_snapshot": {"selected_benefit_ids": ["B1"]},
            "output_snapshot": {"evidence": [{"evidence_id": "E1", "page_no": 1}]},
        }
        combined = RUNNER._trace_validation([event, retrieve], ["ANSWER", "RETRIEVE"])
        self.assertEqual(combined["status"], "COMPLETE")
        missing = RUNNER._trace_validation([event], ["INTERPRET", "RETRIEVE", "ANSWER"])
        self.assertEqual(missing["missing_stages"], ["INTERPRET", "RETRIEVE"])

    def test_atomic_trace_file_contains_only_explicit_trace_document(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temp:
            path = Path(temp) / "trace.json"
            RUNNER._atomic_write_json(path, {"run_id": "r-1", "traces": [{"question_id": "Q-1"}]})
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["traces"][0]["question_id"], "Q-1")
            self.assertEqual(list(Path(temp).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
