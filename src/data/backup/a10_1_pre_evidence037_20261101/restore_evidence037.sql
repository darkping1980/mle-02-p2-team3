-- Restores the pre-correction position of evidence 20261101_000037. Review before running.
UPDATE db_pipeline.card_source_evidence SET start_pos=1622, end_pos=1626
WHERE evidence_id='20261101_000037' AND start_pos=2270 AND end_pos=2274;
