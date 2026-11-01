-- Removes the A10-3 condition evidence links. Review before running.
DELETE FROM db_pipeline.card_policy_evidence WHERE ev_link_id IN ('20261101_000055', '20261101_000056', '20261101_000057', '20261101_000058', '20261101_000059', '20261101_000060', '20261101_000061', '20261101_000062');
