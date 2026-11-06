-- Run read-only in the intended environment before reviewing the DDL.
SELECT current_database() AS database_name,
       current_user AS connected_user,
       inet_server_addr() AS server_address,
       inet_server_port() AS server_port,
       current_setting('server_version') AS server_version;

SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'db_pipeline' AND table_name = 'app_log'
ORDER BY ordinal_position;

-- Run only after the new columns exist; this reports the backfill target count.
SELECT count(*) AS rows_with_missing_summaries
FROM db_pipeline.app_log
WHERE neo4j_summary IS NULL OR pdf_evidence_summary IS NULL;

-- Review examples before any separately approved UPDATE.
SELECT app_log_id, detail_text, pdf_evidence_text
FROM db_pipeline.app_log
WHERE neo4j_summary IS NULL OR pdf_evidence_summary IS NULL
ORDER BY app_log_id
LIMIT 5;
