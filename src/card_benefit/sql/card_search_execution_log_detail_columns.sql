-- Existing request-level app_log extension only; never renames or recreates tables.
BEGIN;

DO $preflight$
DECLARE
    column_info record;
BEGIN
    IF to_regclass('db_pipeline.app_log') IS NULL THEN
        RAISE EXCEPTION 'Expected existing table db_pipeline.app_log';
    END IF;

    FOR column_info IN
        SELECT column_name, data_type, is_nullable
          FROM information_schema.columns
         WHERE table_schema = 'db_pipeline'
           AND table_name = 'app_log'
           AND column_name IN ('detail_text', 'pdf_evidence_text')
    LOOP
        IF column_info.data_type <> 'text' OR column_info.is_nullable <> 'YES' THEN
            RAISE EXCEPTION 'Unexpected existing app_log column definition: % % %',
                column_info.column_name, column_info.data_type, column_info.is_nullable;
        END IF;
    END LOOP;
END
$preflight$;

ALTER TABLE db_pipeline.app_log
    ADD COLUMN IF NOT EXISTS detail_text TEXT;
ALTER TABLE db_pipeline.app_log
    ADD COLUMN IF NOT EXISTS pdf_evidence_text TEXT;

COMMIT;
