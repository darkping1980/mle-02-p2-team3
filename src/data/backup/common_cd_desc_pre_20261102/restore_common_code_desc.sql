-- Removes the description columns added on 2026-11-02. Existing columns and rows were not changed.
-- The CSV files hold the rows as they were before the change. Review before running.
BEGIN;
ALTER TABLE db_pipeline.common_code_grp DROP COLUMN IF EXISTS common_code_grp_desc;
ALTER TABLE db_pipeline.common_cd DROP COLUMN IF EXISTS common_cd_desc;
COMMIT;
