-- Remove the legacy single-product hint from CARD_DOC.
-- Run only after reviewing the preflight queries below. This file does not
-- connect to or execute against any database automatically.

-- Preflight 1: inspect dependent constraints, indexes, views, and rules.
-- Any unreviewed dependency will make the ALTER fail safely; CASCADE is not used.
SELECT
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint c
JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = 'db_pipeline'
  AND t.relname = 'card_doc'
  AND pg_get_constraintdef(c.oid) ILIKE '%card_id%';

SELECT schemaname, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'db_pipeline'
  AND tablename = 'card_doc'
  AND indexdef ILIKE '%card_id%';

-- Preflight 2: report legacy links that are absent from the authoritative
-- relation table. Do not infer or insert these links automatically.
SELECT d.card_doc_id, d.card_id AS legacy_card_id, d.doc_type_cd, d.doc_title
FROM db_pipeline.card_doc d
WHERE d.card_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM db_pipeline.card_product_doc p
      WHERE p.card_doc_id = d.card_doc_id
        AND p.card_id = d.card_id
  )
ORDER BY d.card_doc_id;

-- Preflight 3: summarize values before removal. This query is read-only.
SELECT count(*) AS document_count,
       count(*) FILTER (WHERE card_id IS NOT NULL) AS nonnull_card_id_count
FROM db_pipeline.card_doc;

-- Apply only after the preflight returned no unresolved legacy links and all
-- reported dependencies were reviewed. The transaction preserves all rows in
-- CARD_DOC and CARD_PRODUCT_DOC. IF EXISTS permits safe reruns after success.
BEGIN;

DO $$
BEGIN
    IF to_regclass('db_pipeline.card_doc') IS NULL THEN
        RAISE EXCEPTION 'db_pipeline.card_doc does not exist';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM db_pipeline.card_doc d
        WHERE d.card_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM db_pipeline.card_product_doc p
              WHERE p.card_doc_id = d.card_doc_id
                AND p.card_id = d.card_id
          )
    ) THEN
        RAISE EXCEPTION 'Unlinked non-NULL card_doc.card_id values exist; review the preflight result before migration';
    END IF;
END;
$$;

-- Known legacy indexes/constraint from earlier schema revisions.
ALTER TABLE db_pipeline.card_doc
    DROP CONSTRAINT IF EXISTS card_doc_card_id_doc_type_cd_doc_version_no_key;
DROP INDEX IF EXISTS db_pipeline.uq_card_doc_active;

ALTER TABLE db_pipeline.card_doc
    DROP COLUMN IF EXISTS card_id;

COMMIT;
