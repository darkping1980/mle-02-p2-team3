-- Review/apply manually only after confirming the target database and current table definition.
-- Adds nullable display columns only; existing columns and rows are preserved.
ALTER TABLE db_pipeline.app_log
    ADD COLUMN IF NOT EXISTS neo4j_summary TEXT,
    ADD COLUMN IF NOT EXISTS pdf_evidence_summary TEXT;

COMMENT ON COLUMN db_pipeline.app_log.neo4j_summary IS 'Human-readable Neo4j provenance derived from the stored final outcome';
COMMENT ON COLUMN db_pipeline.app_log.pdf_evidence_summary IS 'Human-readable PDF evidence and citation summary derived from the stored final outcome';

-- Rollback (only if these columns remain unused):
-- ALTER TABLE db_pipeline.app_log
--     DROP COLUMN IF EXISTS neo4j_summary,
--     DROP COLUMN IF EXISTS pdf_evidence_summary;
