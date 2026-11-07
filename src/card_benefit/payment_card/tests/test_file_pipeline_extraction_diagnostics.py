from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from payment_card.file_pipeline.extraction.locate_diagnose import diagnose_locations
from payment_card.file_pipeline.extraction.locate_diagnose import classify_quote
from payment_card.file_pipeline.extraction.relocate import relocate_results
from payment_card.file_pipeline.extraction.eval.variance import compare_variance
from payment_card.file_pipeline.extraction.llm_adapter import create_llm_call
from payment_card.file_pipeline.extraction.cli import main


class DiagnosticModulesTest(unittest.TestCase):
    def test_all_quote_failure_classes(self):
        source = "가나다라마바사, 할인 적용합니다."
        self.assertEqual(classify_quote(source, "가나다\n라마바사")[0], "a")
        self.assertEqual(classify_quote(source, "가나다라마바사 할인 적용합니다")[0], "b")
        self.assertEqual(classify_quote(source, "가나다…적용합니다")[0], "c")
        self.assertEqual(classify_quote(source, "가나다라마바사, 할인 적용합니다. 추가 문장")[0], "d")
        self.assertEqual(classify_quote(source, "완전히 무관한 긴 인용문")[0], "e")

    def test_classifies_and_relocates_only_unique_tolerant_quote(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); chunks = root / 'chunks'; results = root / 'results'
            chunks.mkdir(); results.mkdir()
            source = '첫 문장, 할인 5% 적용.'
            (chunks / 'd.chunks.json').write_text(json.dumps({'chunks': [
                {'chunk_id': 'c1', 'page_no': 2, 'start_pos': 101, 'text': source}
            ]}), encoding='utf-8')
            (results / 'c1.result.json').write_text(json.dumps({
                'chunk_id': 'c1', 'page_no': 2, 'extraction': {'benefits': [
                    {'evidence': [{'text': '할인\n5% 적용', 'location': None}, {'text': '전혀 다른 내용', 'location': None}]}
                ]}, 'failures': [{'code': 'quote_location_failure', 'path': 'benefits[0].evidence[0]', 'quote': '할인\n5% 적용'},
                              {'code': 'quote_location_failure', 'path': 'benefits[0].evidence[1]', 'quote': '전혀 다른 내용'}], 'notes': []
            }, ensure_ascii=False), encoding='utf-8')
            diag = diagnose_locations(results, chunks, root / 'diag')
            self.assertEqual(diag['by_type']['a'], 1)
            self.assertEqual(diag['by_type']['e'], 1)
            output = root / 'relocated'
            summary = relocate_results(results, chunks, output)
            saved = json.loads((output / 'c1.result.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['recovered'], 1)
            quote = saved['extraction']['benefits'][0]['evidence'][0]
            self.assertEqual((quote['location']['start_pos'], quote['location']['end_pos']), (107, 114))
            self.assertEqual(source[quote['location']['start_pos'] - 101:quote['location']['end_pos'] - 100], '할인 5% 적용')
            self.assertIn('relocated_tolerant', saved['notes'])
            self.assertIsNone(saved['extraction']['benefits'][0]['evidence'][1]['location'])

    def test_variance_uses_entity_keys_and_numeric_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); dirs = [root / 'r1', root / 'r2']
            for d in dirs: d.mkdir()
            base = {'chunk_id': 'c', 'extraction': {'benefits': [{'name': ' 할인 ', 'text': '5%'}]}, 'failures': []}
            (dirs[0] / 'c.result.json').write_text(json.dumps(base), encoding='utf-8')
            other = {'chunk_id': 'c', 'extraction': {'benefits': []}, 'failures': [{'code': 'empty_result'}]}
            (dirs[1] / 'c.result.json').write_text(json.dumps(other), encoding='utf-8')
            summary = compare_variance(dirs, root / 'variance')
            row = json.loads((root / 'variance' / 'variance.json').read_text(encoding='utf-8'))[0]
            self.assertEqual(summary['chunks'], 1)
            self.assertEqual(row['item_count_min'], 0)
            self.assertEqual(row['item_count_max'], 1)
            self.assertEqual(row['success_agreement'], 0.5)
            self.assertNotIn('name', json.dumps(row))

    def test_temperature_is_optional_and_sdk_error_is_sanitized(self):
        captured = {}
        class APIValidationError(Exception):
            status_code = 400
            code = 'unsupported_parameter'
        class Client:
            def invoke(self, prompt): raise APIValidationError('secret-key rejected')
        with patch.dict(os.environ, {'TEST_KEY': 'secret-key'}):
            call = create_llm_call('model', 'TEST_KEY', client_factory=lambda **kw: (captured.update(kw) or Client()), temperature=0)
        self.assertEqual(captured['temperature'], 0)
        with self.assertRaises(RuntimeError) as caught: call('prompt')
        self.assertIn('APIValidationError', str(caught.exception))
        self.assertIn('status_code=400', str(caught.exception))
        self.assertIn('unsupported_parameter', str(caught.exception))
        self.assertNotIn('secret-key', str(caught.exception))
        self.assertEqual((caught.exception.status_code, caught.exception.error_code, caught.exception.retryable), (400, 'unsupported_parameter', False))

    def test_prompt_contains_verbatim_evidence_rules(self):
        from payment_card.file_pipeline.extraction.prompt import build_prompt
        prompt = build_prompt({'page_no': 1, 'start_pos': 1, 'text': 'x'})
        self.assertIn('공백과 문장부호도 그대로 유지', prompt)
        self.assertIn('여러 문장을 이어 붙이지 마세요', prompt)
        self.assertIn('같은 문장에서 나온 항목은 합치세요', prompt)

    def test_nonretryable_short_circuit_and_retryable_retry(self):
        from payment_card.file_pipeline.extraction.parallel import process_chunks
        chunks = [{'page_no': 1, 'start_pos': 1, 'chunk_id': 'c', 'text': 'x'}]
        calls = []
        def bad400(_):
            calls.append(1)
            error = RuntimeError('safe')
            error.status_code, error.error_code, error.retryable = 400, 'unsupported_value', False
            raise error
        result = process_chunks(chunks, 'sha', bad400, retries=2)
        self.assertEqual(len(calls), 1)
        self.assertFalse(result[0]['failures'][0]['retryable'])
        calls.clear()
        def transient(_):
            calls.append(1)
            if len(calls) < 2:
                error = RuntimeError('safe')
                error.status_code, error.error_code, error.retryable = 429, 'rate_limit', True
                raise error
            return '{}'
        process_chunks(chunks, 'sha', transient, retries=2)
        self.assertEqual(len(calls), 2)

    def test_fail_fast_leaves_unstarted_chunks_without_results(self):
        from payment_card.file_pipeline.extraction.parallel import process_chunks
        chunks = [{'page_no': 1, 'start_pos': 1, 'chunk_id': str(i), 'text': 'x'} for i in range(5)]
        called = []
        def bad400(_):
            called.append(1)
            error = RuntimeError('safe')
            error.status_code, error.error_code, error.retryable = 400, 'unsupported_value', False
            raise error
        result = process_chunks(chunks, 'sha', bad400, retries=2, fail_fast_threshold=3)
        self.assertEqual(len(called), 3)
        self.assertEqual(result.started, 3)
        self.assertEqual(result.stopped_reason, 'non-retryable error repeated 3 times (code=unsupported_value)')
        self.assertEqual(result[3:], [None, None])

    def test_temperature_none_is_not_passed(self):
        captured = {}
        class Client:
            def invoke(self, prompt): return 'ok'
        with patch.dict(os.environ, {'TEST_KEY': 'secret-key'}):
            create_llm_call('model', 'TEST_KEY', client_factory=lambda **kw: (captured.update(kw) or Client()))
        self.assertEqual(captured, {'model': 'model', 'api_key': 'secret-key'})

    def test_run_cli_accepts_temperature_without_changing_dry_run(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); chunks = root / 'chunks'; chunks.mkdir()
            (chunks / 'd.chunks.json').write_text(json.dumps({'chunks': []}), encoding='utf-8')
            self.assertEqual(main(['run', '--chunk-dir', str(chunks), '--output-dir', str(root / 'out'), '--temperature', '0']), 0)


if __name__ == '__main__': unittest.main()
