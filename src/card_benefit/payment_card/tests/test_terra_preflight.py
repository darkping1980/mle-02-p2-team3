from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pymupdf
import pytest

from payment_card.db_pipeline import terra_main
from payment_card.db_pipeline.extraction_service import PageInput


def item(**overrides):
    return dict(card_id=1, card_doc_id='D1', doc_file_nm='test.pdf', doc_sha256='a'*64,
                doc_status='ACTIVE', approval_status_cd='PENDING', card_doc_chunk_id='C1',
                chunk_raw_txt='page text', chunk_status='RAW', chunk_split_rule_ver='PAGE_V1',
                page_raw_txt='page text', page_note=None, **overrides)


def args():
    return SimpleNamespace(card_id=1, doc_id='D1', page=1, previous_spend_usd=Decimal(0),
                           input_token_estimate=10000, max_output_tokens=8000, budget_usd=Decimal(1))


class Connection:
    def __init__(self, rows, unknown=0):
        self.rows = rows
        self.unknown = unknown
        self.queries = []

    def execute(self, sql, params=None):
        self.queries.append(sql.strip())
        if 'FROM db_pipeline.card_product p' in sql:
            return SimpleNamespace(fetchall=lambda: self.rows)
        if 'FROM db_pipeline.card_ai_run r' in sql:
            return SimpleNamespace(fetchone=lambda: dict(input_tokens=0, output_tokens=0, unknown_calls=self.unknown))
        return None


def session_for(connection):
    @contextmanager
    def connect(**kwargs):
        yield connection
    return SimpleNamespace(database_manager=SimpleNamespace(connect=connect))


def test_preflight_builds_mock_request_without_api(monkeypatch, capsys):
    doc = pymupdf.open()
    page = doc.new_page()
    png = page.get_pixmap().tobytes('png')
    doc.close()
    service = Mock()
    service._local_pdf.return_value = 'local.pdf'
    service.build_input.return_value = PageInput('prompt', 1, 'page text', png, 'hash')
    monkeypatch.setattr(terra_main, 'ExtractionService', lambda *a, **k: service)
    connection = Connection([item()])
    terra_main.preflight(session_for(connection), args(), Decimal('0.05'))
    assert connection.queries[0] == 'SET TRANSACTION READ ONLY'
    assert 'preflight OK' in capsys.readouterr().out
    service.build_input.assert_called_once()


@pytest.mark.parametrize('change', [
    {'page_note': 'OCR_REVIEW pending'}, {'chunk_status': 'EXCLUDED'},
    {'chunk_split_rule_ver': 'OTHER'}, {'page_raw_txt': 'different'},
])
def test_preflight_rejects_invalid_page(change):
    row = item()
    row.update(change)
    with pytest.raises(ValueError):
        terra_main.preflight(session_for(Connection([row])), args(), Decimal('0.05'))


def test_preflight_rejects_missing_relation_and_unknown_usage():
    with pytest.raises(ValueError):
        terra_main.preflight(session_for(Connection([])), args(), Decimal('0.05'))
    with pytest.raises(ValueError):
        terra_main.preflight(session_for(Connection([item()], unknown=1)), args(), Decimal('0.05'))
