import json

from card_benefit.payment_card.db_pipeline_origin_search.execution_log import (
    outcome_neo4j_summary,
    outcome_pdf_evidence_summary,
    summaries_from_stored_app_log,
)


def test_neo4j_summary_shows_only_final_point_refs_and_cited_relationships():
    from card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import entity_ref

    key = '["card_bnft",23,"20261105_000100"]'
    outcome = {
        "answer": {"status": "STRUCTURED_ONLY", "points": [
            {"text": "주요 간편결제 모아포인트 추가적립", "benefit_name": "주요 간편결제 모아포인트 추가적립",
             "benefit_id": entity_ref(key), "evidence_ids": [
                 "20261105_002740", "20261105_002742", "20261105_002743"],
             "verification_status": "STRUCTURED_ONLY"}
        ]},
        "retrieved_data": [{"entity_ref": entity_ref(key), "context": {
            "benefit": {"key": key, "name": "주요 간편결제 모아포인트 추가적립"},
            "benefit_labels": ["dp_node", "dp_card_bnft", "dp_card_product_item"]}}],
    }
    summary = outcome_neo4j_summary(outcome)
    assert "주요 간편결제 모아포인트 추가적립" in summary
    assert key in summary
    assert "20261105_002740" in summary and "20261105_002742" in summary and "20261105_002743" in summary
    assert "STRUCTURED_ONLY" in summary


def test_pdf_summary_uses_answer_points_and_preserves_quotes_and_multiple_locations():
    from unittest.mock import patch
    rows = [
        {"evidence_id": "20261105_002740", "quote_txt": "2만원", "locations": [
            {"doc_title": "카드의정석 POINT II 상품안내장", "doc_file_nm": "woori_all/credit/상품안내장_카드의정석 POINT II_260901.pdf",
             "card_doc_id": "20261105_000043", "page_no": 3, "card_doc_chunk_id": "20261105_000176"}]},
        {"evidence_id": "20261105_002742", "quote_txt": "통합 월 적립 한도", "locations": [
            {"doc_title": "카드의정석 POINT II 상품안내장", "card_doc_id": "20261105_000043", "page_no": 3,
             "card_doc_chunk_id": "20261105_000176"}]},
        {"evidence_id": "20261105_002743", "quote_txt": "특별/추가 적립", "locations": [
            {"doc_title": "카드의정석 POINT II 상품안내장", "card_doc_id": "20261105_000043", "page_no": 3,
             "card_doc_chunk_id": "20261105_000176"}]},
        {"evidence_id": "E-UNUSED", "quote_txt": "검색만 됨", "locations": [{"page_no": 4}]},
    ]
    outcome = {"answer": {"points": [{"evidence_ids": ["20261105_002740", "20261105_002742", "20261105_002743"]}]}}
    with patch("card_benefit.payment_card.db_pipeline_origin_search.execution_log.outcome_pdf_evidence_text",
               return_value=json.dumps(rows, ensure_ascii=False)):
        summary = outcome_pdf_evidence_summary(outcome)
    assert "답변에 실제 사용된 PDF 근거" in summary
    assert "페이지: 3" in summary and "청크 ID: 20261105_000176" in summary
    assert "원문: \"2만원\"" in summary
    assert "검색되었으나 답변에서 인용하지 않은 근거" in summary and "E-UNUSED" in summary
    assert "20261105_002740" in summary and "20261105_002742" in summary and "20261105_002743" in summary


def test_summary_handles_missing_null_malformed_outcomes_and_program_derived_without_ref():
    assert outcome_neo4j_summary(None) is None
    assert outcome_pdf_evidence_summary({"evidence": None, "answer": None}) is None
    outcome = {"answer": {"points": [{"text": "계산 결과", "origin": "PROGRAM_DERIVED",
                                       "benefit_id": "derived-only", "evidence_ids": []}]}}
    summary = outcome_neo4j_summary(outcome)
    assert "프로그램 계산 결과" in summary
    assert "노드 Key" not in summary
    assert outcome_pdf_evidence_summary({"answer": {"points": None}}) in (None, "[답변에 실제 사용된 PDF 근거]")


def test_multiple_benefits_render_as_separate_entries():
    from card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import entity_ref
    keys = ['["card_bnft",23,"20261105_000100"]', '["card_bnft",24,"20261105_000101"]']
    outcome = {"answer": {"points": [
        {"text": "혜택 하나", "benefit_id": entity_ref(keys[0]), "evidence_ids": ["E1"]},
        {"text": "혜택 둘", "benefit_id": entity_ref(keys[1]), "evidence_ids": ["E2"]},
    ]}, "retrieved_data": [
        {"entity_ref": entity_ref(keys[0]), "context": {"benefit": {"key": keys[0]}, "benefit_labels": ["dp_card_bnft"]}},
        {"entity_ref": entity_ref(keys[1]), "context": {"benefit": {"key": keys[1]}, "benefit_labels": ["dp_card_bnft"]}},
    ]}
    summary = outcome_neo4j_summary(outcome)
    assert summary.index("혜택 하나") < summary.index("혜택 둘")
    assert summary.count("노드 Key:") == 2


def test_historical_json_reconstruction_uses_only_stored_fields():
    from card_benefit.payment_card.db_pipeline_origin_search.neo4j_search import entity_ref
    key = '["card_bnft",23,"20261105_000100"]'
    detail = {"status": "STRUCTURED_ONLY", "points": [{
        "text": "주요 간편결제 모아포인트 추가적립", "benefit_name": "주요 간편결제 모아포인트 추가적립",
        "benefit_id": entity_ref(key), "evidence_ids": ["20261105_002740"],
        "neo4j_ref": {"labels": ["dp_card_bnft"], "key": key,
                      "name": "주요 간편결제 모아포인트 추가적립"}}]}
    evidence = [{"evidence_id": "20261105_002740", "quote_txt": "2만원", "locations": [
        {"doc_title": "카드의정석 POINT II 상품안내장", "page_no": 3,
         "card_doc_chunk_id": "20261105_000176"}]}]
    neo, pdf = summaries_from_stored_app_log(json.dumps(detail, ensure_ascii=False),
                                             json.dumps(evidence, ensure_ascii=False))
    assert "20261105_000100" in neo
    assert "20261105_002740" in pdf and "2만원" in pdf
    assert "페이지: 3" in pdf and "20261105_000176" in pdf
    assert summaries_from_stored_app_log("{broken", "null") == (None, None)
