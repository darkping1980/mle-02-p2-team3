-- Read-only checks for the CARD_DOC.CARD_ID migration.
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

SELECT DISTINCT vn.nspname AS view_schema, v.relname AS view_name
FROM pg_depend dep
JOIN pg_rewrite rw ON rw.oid = dep.objid
JOIN pg_class v ON v.oid = rw.ev_class
JOIN pg_namespace vn ON vn.oid = v.relnamespace
JOIN pg_class t ON t.oid = dep.refobjid
JOIN pg_namespace tn ON tn.oid = t.relnamespace
WHERE tn.nspname = 'db_pipeline'
  AND t.relname = 'card_doc'
  AND v.relkind = 'v';

SELECT d.card_doc_id, d.card_id AS legacy_card_id, d.doc_type_cd, d.doc_title
FROM db_pipeline.card_doc d
WHERE d.card_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM db_pipeline.card_product_doc p
      WHERE p.card_doc_id = d.card_doc_id AND p.card_id = d.card_id
  )
ORDER BY d.card_doc_id;

SELECT count(*) AS document_count,
       count(*) FILTER (WHERE card_id IS NOT NULL) AS nonnull_card_id_count
FROM db_pipeline.card_doc;

SELECT (SELECT count(*) FROM db_pipeline.card_doc) AS document_count,
       (SELECT count(*) FROM db_pipeline.card_product_doc) AS relation_count,
       (SELECT count(*) FROM db_pipeline.card_product_doc l
         JOIN db_pipeline.card_doc d USING (card_doc_id)) AS valid_relation_count;
