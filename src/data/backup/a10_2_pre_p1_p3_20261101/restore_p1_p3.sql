-- Restores the pre A10-2 state of P1, P2, P3. Review before running.
BEGIN;
DELETE FROM db_pipeline.card_policy_evidence WHERE ev_link_id IN ('20261101_000042', '20261101_000043', '20261101_000044', '20261101_000045', '20261101_000046', '20261101_000047', '20261101_000048', '20261101_000049', '20261101_000050', '20261101_000051', '20261101_000052', '20261101_000053', '20261101_000054');
UPDATE db_pipeline.card_bnft SET bnft_cond_expr = jsonb_set(bnft_cond_expr, '{branches,0,atoms,1,cond_type_cd}', '"GRACE"') WHERE card_id=2 AND card_bnft_id='20261101_000004';
UPDATE db_pipeline.card_bnft SET bnft_cond_expr = jsonb_set(bnft_cond_expr, '{branches,0,atoms,0,cond_raw_txt}', '"지난달 실적\n대중교통\n버스, 지하철\n월 1천원\n5%\n캐시백\n10만원"') WHERE card_id=2 AND card_bnft_id='20261101_000003';
COMMIT;
