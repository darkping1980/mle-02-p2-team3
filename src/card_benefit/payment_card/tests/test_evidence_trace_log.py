import json
from unittest.mock import patch
from card_benefit.payment_card.db_pipeline_origin_search.execution_log import outcome_pdf_evidence_text, outcome_detail_text


def test_provenance_preserves_owners_locations_and_original_fields():
    old = {"evidence_id": "E", "page_no": 1, "quote": "abc", "benefit_ids": ["B"], "subjects": [], "items": [], "benefits": [], "rule_keys": []}
    evidence = {"key": "e-key", "start_pos": 2, "end_pos": 4, "source_json": '{"evidence_id":"E"}'}
    def row(owner, chunk):
        return {"owner_labels": [owner], "owner": {"key": owner, "name": owner}, "evidence_labels": ["dp_card_source_evidence"], "link": {"key": owner}, "evidence": evidence,
                "chunk": {"key": chunk, "source_json": json.dumps({"card_doc_chunk_id": chunk, "chunk_seq": 1, "chunk_start_pos": 9, "chunk_end_pos": 20})},
                "page": {"page_no": 1}, "document": {"source_json": json.dumps({"card_doc_id": chunk, "doc_file_nm": None})}}
    outcome = {"evidence": [old], "retrieved_data": [{"evidence": [row("benefit", "C1"), row("rule", "C2"), row("benefit", "C1")]}], "answer": {"points": [{"text": "answer", "evidence_ids": ["E"]}]}}
    logged = json.loads(outcome_pdf_evidence_text(outcome))[0]
    assert all(logged[k] == v for k, v in old.items())
    assert len(logged["owners"]) == 2 and len(logged["locations"]) == 2
    assert logged["locations"][0]["start_pos"] == 2 and logged["locations"][0]["chunk_start_pos"] == 9
    assert logged["locations"][0]["doc_file_nm"] is None
    assert json.loads(outcome_detail_text(outcome))["points"][0]["evidence_ids"] == [logged["evidence_id"]]
    assert outcome["evidence"] == [old]


def test_provenance_failure_falls_back_to_existing_log():
    outcome = {"evidence": [{"evidence_id": "E"}], "retrieved_data": [{"evidence": [None]}]}
    assert json.loads(outcome_pdf_evidence_text(outcome)) == outcome["evidence"]
