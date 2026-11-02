-- Remove the legacy single-product hint from CARD_DOC.
-- Apply only after reviewing db_pipeline_migration_v7_drop_card_doc_card_id_precheck.sql.
-- The transaction preserves all rows in CARD_DOC and CARD_PRODUCT_DOC.
BEGIN;

DO $$
BEGIN
    IF to_regclass('db_pipeline.card_doc') IS NULL THEN
        RAISE EXCEPTION 'db_pipeline.card_doc does not exist';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'db_pipeline' AND table_name = 'card_doc' AND column_name = 'card_id'
    ) THEN
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
    END IF;
END;
$$;

-- The V7 integrity view used the legacy CARD_DOC.CARD_ID hint as a gate.
-- Remove only that obsolete branch while preserving the existing view contract.
DO $$
DECLARE
    v_view_definition text;
BEGIN
    IF to_regclass('db_pipeline.v_card_integrity_issue') IS NOT NULL THEN
        SELECT pg_get_viewdef('db_pipeline.v_card_integrity_issue'::regclass, true)
          INTO v_view_definition;
        v_view_definition := regexp_replace(
            v_view_definition,
            E'UNION ALL\s+SELECT ''shared_doc_bound_to_card''.*?WHERE d\.card_id IS NOT NULL[^\n]*\n',
            '',
            'ns'
        );
        IF position('shared_doc_bound_to_card' IN v_view_definition) > 0 THEN
            RAISE EXCEPTION 'Could not remove the legacy shared-document gate from v_card_integrity_issue';
        END IF;
        EXECUTE 'CREATE OR REPLACE VIEW db_pipeline.v_card_integrity_issue AS ' || v_view_definition;
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
