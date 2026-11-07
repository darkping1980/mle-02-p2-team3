from __future__ import annotations

import unittest

from payment_card.file_pipeline.extraction.eval.enum_violation_report import analyze_runs
from payment_card.file_pipeline.extraction.eval.prompt_version_compare import compare_runs


class EnumViolationReportTest(unittest.TestCase):
    def test_aggregates_paths_and_hides_non_ascii_inputs(self):
        runs = {"out5a": [{"chunk_id": "c1", "extraction": None, "failures": [
            {"code": "schema_validation_failure", "message": "conditions.8.kind\n  Input should be 'SPEND_REQ', 'EXCLUDE', 'USAGE', 'PAYMENT', 'MERCHANT' or 'OTHER' [type=literal_error, input_value='SPEND_REQ_EXTRA', input_type=str]"},
            {"code": "schema_validation_failure", "message": "conditions.9.kind\n  Input should be one of [type=literal_error, input_value='조건 문장', input_type=str]"},
        ]}]}
        report = analyze_runs(runs)
        self.assertEqual(report["field_counts"], {"conditions.8.kind": 1, "conditions.9.kind": 1})
        self.assertEqual(report["value_counts"], {"SPEND_REQ_EXTRA": 1})
        self.assertEqual(report["non_ascii_values"], 1)
        self.assertEqual(report["run_counts"]["out5a"]["violations"], 2)
        self.assertNotIn("조건 문장", str(report))


class PromptVersionCompareTest(unittest.TestCase):
    def test_counts_sections_evidence_and_directions(self):
        base = {"chunk_id": "c1", "extraction": {"benefits": [{"evidence": [{"text": "x"}]}],
                "conditions": [{"evidence": [{"text": "y"}, {"text": "z"}]}]}}
        later = {"chunk_id": "c1", "extraction": {"benefits": [{"evidence": [{"text": "x"}]}]}}
        report = compare_runs({"out3": [base], "out4": [later]})
        self.assertEqual(report["versions"]["out3"]["sections"]["conditions"]["items_total"], 1)
        self.assertEqual(report["versions"]["out3"]["sections"]["conditions"]["evidence_total"], 2)
        self.assertEqual(report["directions"]["out3->out4"]["conditions"], {"increase": 0, "decrease": 1, "same": 0})
        self.assertEqual(report["versions"]["out4"]["empty_result_chunks"], [])
