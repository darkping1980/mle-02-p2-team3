-- Phase-1 read-only validation and illustrative rows, 2026-10-31.
-- Do not run the companion DDL or insert sample data in this task.
-- Queries against NEW tables become runnable only after separately approved DDL.
-- Replace demo filters in each params CTE for a product, document, or as-of date.
-- Evidence: existing schema backup src/data/backup/dump-postgres-202610311136.sql.
-- Hana public page confirms brand-dependent service type (VISA/Mastercard 01):
-- https://m.hanacard.co.kr/MKCDCM1000M.web?CD_PD_SEQ=10120
-- Drive common-doc folder was inaccessible. Its named JADE/AMEX03,
-- Mastercard 01/04, VP001 editions and terms are UNVERIFIED APPLICATIONS here.

-- 0. Existing schema baseline. Can run now: catalog-only, no new tables needed.
SELECT c.relname AS table_name,
       pg_get_constraintdef(k.oid) AS constraint_definition
FROM pg_catalog.pg_constraint k
JOIN pg_catalog.pg_class c ON c.oid = k.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'db_pipeline'
  AND c.relname IN ('card_doc','card_bnft','card_cond')
  AND k.contype IN ('p','u','c')
ORDER BY c.relname, k.contype, k.conname;

-- 1. Logical sample rows only. All IDs and dates in this CTE are artificial;
-- 'OBSERVED_DOCUMENT' means title/PDF context only, NOT application approval.
-- A1: one product + one dedicated guide (JADE title from local 20-card report).
-- A2: one product + two revisions (VP001 years from user scenario; no approval).
-- A3: two products + same terms document (shared-term relationship is illustrative).
-- A4: JADE + AMEX Platinum 03 (user scenario, product applicability unverified).
-- A5: Mastercard Platinum 01 vs 04 (same brand/grade, two service variants).
-- A6: VP001 2023 vs 2026 (two card_doc IDs, one family; demo periods only).
WITH sample_product(card_id,product_nm,source_state) AS (
    VALUES (101::bigint,'JADE Classic','LOCAL_PDF_PRODUCT_NAME'),
           (102::bigint,'가상 체크 상품','ILLUSTRATIVE'),
           (103::bigint,'가상 Mastercard 01 상품','ILLUSTRATIVE'),
           (104::bigint,'가상 Mastercard 04 상품','ILLUSTRATIVE'),
           (105::bigint,'가상 VP001 상품','ILLUSTRATIVE')
), sample_variant(card_id,variant_id,brand_cd,grade_cd,service_type_cd) AS (
    VALUES (101::bigint,'V-AMEX03','AMEX','PLATINUM','PLATINUM_03'),
           (103::bigint,'V-MC01','MASTERCARD','PLATINUM','PLATINUM_01'),
           (104::bigint,'V-MC04','MASTERCARD','PLATINUM','PLATINUM_04'),
           (105::bigint,'V-VP001','VISA','PLATINUM','VP001')
), sample_doc(card_doc_id,doc_family_cd,doc_version_no,doc_title,source_state) AS (
    VALUES ('DOC-JADE-2026','JADE_GUIDE',1,'JADE Classic 상품설명서','LOCAL_PDF_TITLE'),
           ('DOC-TERMS-X','COMMON_TERMS_X',1,'공통 회원약관 예시','DRIVE_UNVERIFIED'),
           ('DOC-AMEX03','AMEX_PLATINUM03',1,'AMEX Platinum 03 서비스 안내서','DRIVE_UNVERIFIED'),
           ('DOC-MC01','MASTERCARD_PLATINUM01',1,'Mastercard Platinum 01 안내서','DRIVE_UNVERIFIED'),
           ('DOC-MC04','MASTERCARD_PLATINUM04',1,'Mastercard Platinum 04 안내서','DRIVE_UNVERIFIED'),
           ('DOC-VP001-2023','VISA_VP001',1,'VP001 2023 판 예시','DRIVE_UNVERIFIED'),
           ('DOC-VP001-2026','VISA_VP001',2,'VP001 2026 판 예시','DRIVE_UNVERIFIED')
), sample_link(card_id,variant_id,card_doc_id,link_scope,from_date,to_date_excl,application_state) AS (
    VALUES (101::bigint,NULL::text,'DOC-JADE-2026','PRODUCT',NULL::date,NULL::date,'PRODUCT_GUIDE_TO_VERIFY'),
           (101::bigint,NULL::text,'DOC-TERMS-X','PRODUCT',NULL::date,NULL::date,'PENDING_EVIDENCE'),
           (102::bigint,NULL::text,'DOC-TERMS-X','PRODUCT',NULL::date,NULL::date,'PENDING_EVIDENCE'),
           (101::bigint,'V-AMEX03','DOC-AMEX03','VARIANT',NULL::date,NULL::date,'PENDING_EVIDENCE'),
           (103::bigint,'V-MC01','DOC-MC01','VARIANT',NULL::date,NULL::date,'PENDING_EVIDENCE'),
           (104::bigint,'V-MC04','DOC-MC04','VARIANT',NULL::date,NULL::date,'PENDING_EVIDENCE'),
           (105::bigint,'V-VP001','DOC-VP001-2023','VARIANT',DATE '2023-01-01',DATE '2026-01-01','DEMO_DATES_ONLY'),
           (105::bigint,'V-VP001','DOC-VP001-2026','VARIANT',DATE '2026-01-01',NULL::date,'DEMO_DATES_ONLY')
)
SELECT p.card_id, p.product_nm, v.brand_cd, v.grade_cd, v.service_type_cd,
       d.card_doc_id, d.doc_family_cd, d.doc_version_no,
       l.link_scope, l.from_date, l.to_date_excl,
       d.source_state AS document_evidence,
       l.application_state AS applicability_evidence
FROM sample_link l
JOIN sample_product p ON p.card_id = l.card_id
LEFT JOIN sample_variant v
  ON v.card_id = l.card_id AND v.variant_id = l.variant_id
JOIN sample_doc d ON d.card_doc_id = l.card_doc_id
ORDER BY p.card_id, l.link_scope, d.doc_family_cd, d.doc_version_no;

-- 2. Product's complete document history (product-wide + variant-specific).
-- Set params.card_id to one ID to narrow; NULL lists all. No status=ACTIVE filter:
-- a SUPERSEDED document may remain valid for an earlier as-of date.
WITH params AS (SELECT NULL::bigint AS card_id),
links AS (
    SELECT l.card_id, NULL::varchar(20) AS card_variant_id, l.card_doc_id,
           l.doc_role_cd, l.effective_from, l.effective_to_excl,
           l.approval_status_cd, 'PRODUCT'::text AS link_scope
    FROM db_pipeline.card_product_doc l
    UNION ALL
    SELECT l.card_id, l.card_variant_id, l.card_doc_id,
           l.doc_role_cd, l.effective_from, l.effective_to_excl,
           l.approval_status_cd, 'VARIANT'::text AS link_scope
    FROM db_pipeline.card_product_variant_doc l
)
SELECT p.card_id, p.product_nm, l.link_scope, l.card_variant_id,
       v.brand_cd, v.service_grade_cd, v.service_type_cd,
       d.card_doc_id, d.doc_family_cd, d.doc_version_no,
       d.doc_title, d.doc_type_cd, d.doc_status,
       l.doc_role_cd, l.approval_status_cd,
       l.effective_from, l.effective_to_excl
FROM links l
JOIN db_pipeline.card_product p ON p.card_id = l.card_id
JOIN db_pipeline.card_doc d ON d.card_doc_id = l.card_doc_id
LEFT JOIN db_pipeline.card_product_variant v
  ON v.card_id = l.card_id AND v.card_variant_id = l.card_variant_id
CROSS JOIN params q
WHERE q.card_id IS NULL OR l.card_id = q.card_id
ORDER BY p.card_id, l.link_scope, l.card_variant_id,
         d.doc_family_cd, l.effective_from, d.doc_version_no;

-- 3. Products sharing one document. Set params.doc_id to an actual ID.
WITH params AS (SELECT NULL::varchar(20) AS doc_id),
refs AS (
    SELECT card_id, NULL::varchar(20) AS card_variant_id,
           card_doc_id, 'PRODUCT'::text AS link_scope
    FROM db_pipeline.card_product_doc
    UNION ALL
    SELECT card_id, card_variant_id, card_doc_id, 'VARIANT'::text
    FROM db_pipeline.card_product_variant_doc
)
SELECT d.card_doc_id, d.doc_title, r.link_scope,
       p.card_id, p.product_nm, r.card_variant_id
FROM refs r
JOIN db_pipeline.card_doc d ON d.card_doc_id = r.card_doc_id
JOIN db_pipeline.card_product p ON p.card_id = r.card_id
CROSS JOIN params q
WHERE q.doc_id IS NULL OR r.card_doc_id = q.doc_id
ORDER BY d.card_doc_id, p.card_id, r.card_variant_id;

-- 4. Approved document editions valid at a point in time. For a physical
-- issued card, pass BOTH card_id and variant_id; product-wide docs still apply.
-- NULL variant_id shows product-wide documents only, avoiding accidental
-- union of mutually exclusive brand-service booklets.
WITH params AS (
    SELECT NULL::bigint AS card_id,
           NULL::varchar(20) AS variant_id,
           CURRENT_DATE AS as_of_date
), links AS (
    SELECT l.card_id, NULL::varchar(20) AS card_variant_id, l.card_doc_id,
           l.effective_from, l.effective_to_excl, 'PRODUCT'::text AS scope
    FROM db_pipeline.card_product_doc l
    WHERE l.approval_status_cd = 'APPROVED'
    UNION ALL
    SELECT l.card_id, l.card_variant_id, l.card_doc_id,
           l.effective_from, l.effective_to_excl, 'VARIANT'::text
    FROM db_pipeline.card_product_variant_doc l
    WHERE l.approval_status_cd = 'APPROVED'
)
SELECT l.card_id, l.card_variant_id, l.scope, d.card_doc_id,
       d.doc_family_cd, d.doc_version_no, d.doc_title,
       l.effective_from, l.effective_to_excl
FROM links l
JOIN db_pipeline.card_doc d ON d.card_doc_id = l.card_doc_id
CROSS JOIN params q
WHERE d.doc_status <> 'EXCLUDED'
  AND q.as_of_date >= l.effective_from
  AND (l.effective_to_excl IS NULL OR q.as_of_date < l.effective_to_excl)
  AND (q.card_id IS NULL OR l.card_id = q.card_id)
  AND ((q.variant_id IS NULL AND l.card_variant_id IS NULL)
    OR (q.variant_id IS NOT NULL AND
       (l.card_variant_id IS NULL OR l.card_variant_id = q.variant_id)))
ORDER BY l.card_id, l.card_variant_id, d.doc_family_cd, d.doc_version_no;

-- 5. Orphan endpoints, important because physical FKs are deliberately absent.
SELECT 'PRODUCT_DOC_PRODUCT' AS issue, l.card_id, NULL::varchar(20) AS card_variant_id, l.card_doc_id
FROM db_pipeline.card_product_doc l
LEFT JOIN db_pipeline.card_product p ON p.card_id = l.card_id
WHERE p.card_id IS NULL
UNION ALL
SELECT 'PRODUCT_DOC_DOCUMENT', l.card_id, NULL::varchar(20), l.card_doc_id
FROM db_pipeline.card_product_doc l
LEFT JOIN db_pipeline.card_doc d ON d.card_doc_id = l.card_doc_id
WHERE d.card_doc_id IS NULL
UNION ALL
SELECT 'VARIANT_DOC_VARIANT', l.card_id, l.card_variant_id, l.card_doc_id
FROM db_pipeline.card_product_variant_doc l
LEFT JOIN db_pipeline.card_product_variant v
  ON (v.card_id,v.card_variant_id)=(l.card_id,l.card_variant_id)
WHERE v.card_variant_id IS NULL
UNION ALL
SELECT 'VARIANT_DOC_DOCUMENT', l.card_id, l.card_variant_id, l.card_doc_id
FROM db_pipeline.card_product_variant_doc l
LEFT JOIN db_pipeline.card_doc d ON d.card_doc_id = l.card_doc_id
WHERE d.card_doc_id IS NULL
UNION ALL
SELECT 'VARIANT_PRODUCT', v.card_id, v.card_variant_id, NULL::varchar(20)
FROM db_pipeline.card_product_variant v
LEFT JOIN db_pipeline.card_product p ON p.card_id = v.card_id
WHERE p.card_id IS NULL;

-- 6. Duplicate exact relationship is prevented by the two PKs. Detect a
-- product-wide and variant-specific copy of the SAME doc that overlap in time.
SELECT p.card_id, v.card_variant_id, p.card_doc_id,
       p.effective_from AS product_from, v.effective_from AS variant_from
FROM db_pipeline.card_product_doc p
JOIN db_pipeline.card_product_variant_doc v
  ON v.card_id = p.card_id AND v.card_doc_id = p.card_doc_id
WHERE p.approval_status_cd = 'APPROVED'
  AND v.approval_status_cd = 'APPROVED'
  AND daterange(p.effective_from,p.effective_to_excl,'[)')
      && daterange(v.effective_from,v.effective_to_excl,'[)');

-- 7. Two approved editions of one family overlapping for the same scope.
-- These are review candidates, not automatically invalid: some guides may
-- intentionally coexist. Compare role, brand variant, and actual evidence.
WITH links AS (
    SELECT card_id, NULL::varchar(20) AS variant_id, card_doc_id,
           doc_role_cd, effective_from, effective_to_excl
    FROM db_pipeline.card_product_doc WHERE approval_status_cd='APPROVED'
    UNION ALL
    SELECT card_id, card_variant_id, card_doc_id,
           doc_role_cd, effective_from, effective_to_excl
    FROM db_pipeline.card_product_variant_doc WHERE approval_status_cd='APPROVED'
)
SELECT x.card_id, x.variant_id, d1.doc_family_cd, x.doc_role_cd,
       x.card_doc_id AS first_doc_id, y.card_doc_id AS second_doc_id,
       x.effective_from AS first_from, y.effective_from AS second_from
FROM links x
JOIN links y ON y.card_id=x.card_id
 AND y.variant_id IS NOT DISTINCT FROM x.variant_id
 AND y.doc_role_cd=x.doc_role_cd
 AND y.card_doc_id>x.card_doc_id
JOIN db_pipeline.card_doc d1 ON d1.card_doc_id=x.card_doc_id
JOIN db_pipeline.card_doc d2 ON d2.card_doc_id=y.card_doc_id
 AND d2.doc_family_cd=d1.doc_family_cd
WHERE d1.doc_family_cd IS NOT NULL
  AND daterange(x.effective_from,x.effective_to_excl,'[)')
      && daterange(y.effective_from,y.effective_to_excl,'[)');

-- 8. Edition history: gap/overlap candidate after a revision. Review GAP
-- against actual applicability documents; a gap is not automatically an error.
WITH links AS (
    SELECT card_id, NULL::varchar(20) AS variant_id,
           card_doc_id, doc_role_cd, effective_from, effective_to_excl
    FROM db_pipeline.card_product_doc WHERE approval_status_cd='APPROVED'
    UNION ALL
    SELECT card_id, card_variant_id, card_doc_id,
           doc_role_cd, effective_from, effective_to_excl
    FROM db_pipeline.card_product_variant_doc WHERE approval_status_cd='APPROVED'
), editions AS (
    SELECT l.*, d.doc_family_cd, d.doc_version_no,
           lead(l.card_doc_id) OVER w AS next_doc_id,
           lead(l.effective_from) OVER w AS next_from,
           lead(d.doc_version_no) OVER w AS next_version
    FROM links l
    JOIN db_pipeline.card_doc d ON d.card_doc_id=l.card_doc_id
    WHERE d.doc_family_cd IS NOT NULL
    WINDOW w AS (PARTITION BY l.card_id,l.variant_id,l.doc_role_cd,d.doc_family_cd
                 ORDER BY l.effective_from,l.card_doc_id)
)
SELECT card_id, variant_id, doc_family_cd, doc_role_cd,
       card_doc_id, doc_version_no, effective_from, effective_to_excl,
       next_doc_id, next_version, next_from,
       CASE WHEN effective_to_excl IS NULL THEN 'OPEN_ENDED_BEFORE_NEXT'
            WHEN effective_to_excl > next_from THEN 'OVERLAP'
            WHEN effective_to_excl < next_from THEN 'GAP_REVIEW'
            WHEN next_version <= doc_version_no THEN 'VERSION_ORDER_REVIEW'
       END AS review_issue
FROM editions
WHERE next_doc_id IS NOT NULL
  AND (effective_to_excl IS NULL OR effective_to_excl <> next_from
       OR next_version <= doc_version_no);

-- 9. Migration preflight for legacy card_doc.card_id (can run now).
-- Repeated card IDs are expected; identify the products to backfill. Existing
-- card_doc.card_id is not evidence that common documents apply only there.
SELECT d.card_id, count(*) AS legacy_document_rows,
       count(*) FILTER (WHERE d.doc_type_cd='TERMS') AS terms_rows,
       min(d.doc_release_date) AS oldest_release,
       max(d.doc_release_date) AS newest_release
FROM db_pipeline.card_doc d
GROUP BY d.card_id
ORDER BY d.card_id;

-- 10. Approval gate before service/Neo4j export: approved link must have a
-- real endpoint, non-excluded doc, evidence, valid date, and appropriate role.
-- Relationship approval is separate from document collection or PDF existence.
WITH links AS (
    SELECT card_id, NULL::varchar(20) AS variant_id, card_doc_id,
           doc_role_cd, effective_from, applicability_basis_txt, 'PRODUCT' AS scope
    FROM db_pipeline.card_product_doc WHERE approval_status_cd='APPROVED'
    UNION ALL
    SELECT card_id, card_variant_id, card_doc_id,
           doc_role_cd, effective_from, applicability_basis_txt, 'VARIANT'
    FROM db_pipeline.card_product_variant_doc WHERE approval_status_cd='APPROVED'
)
SELECT l.card_id, l.variant_id, l.card_doc_id, l.scope,
       CASE WHEN p.card_id IS NULL THEN 'MISSING_PRODUCT'
            WHEN d.card_doc_id IS NULL THEN 'MISSING_DOCUMENT'
            WHEN d.doc_status='EXCLUDED' THEN 'EXCLUDED_DOCUMENT'
            WHEN l.scope='VARIANT' AND v.card_variant_id IS NULL THEN 'MISSING_VARIANT'
            WHEN l.effective_from IS NULL THEN 'MISSING_START'
            WHEN length(trim(l.applicability_basis_txt))=0 THEN 'MISSING_EVIDENCE'
            WHEN l.doc_role_cd='BRAND_SERVICE' AND d.doc_type_cd<>'BRAND_SERVICE'
                 THEN 'ROLE_TYPE_MISMATCH'
       END AS issue
FROM links l
LEFT JOIN db_pipeline.card_product p ON p.card_id=l.card_id
LEFT JOIN db_pipeline.card_doc d ON d.card_doc_id=l.card_doc_id
LEFT JOIN db_pipeline.card_product_variant v
  ON (v.card_id,v.card_variant_id)=(l.card_id,l.variant_id)
WHERE p.card_id IS NULL OR d.card_doc_id IS NULL OR d.doc_status='EXCLUDED'
   OR (l.scope='VARIANT' AND v.card_variant_id IS NULL)
   OR l.effective_from IS NULL OR length(trim(l.applicability_basis_txt))=0
   OR (l.doc_role_cd='BRAND_SERVICE' AND d.doc_type_cd<>'BRAND_SERVICE');

-- Deferred phase-2 gate: card_bnft/card_cond still have card_doc_id + card_id.
-- If one shared document is linked to two products, these child rows cannot
-- safely imply one product scope. Define product/variant-specific policy links
-- or separately approved common policy identity before shared extraction.

-- 11. Post-backfill review: legacy card_doc.card_id with no approved or pending
-- product/variant relationship. Run only after phase-1 DDL and link backfill.
-- Do not auto-approve the missing relationship from legacy card_id alone.
SELECT d.card_doc_id, d.card_id AS legacy_card_id, d.doc_title
FROM db_pipeline.card_doc d
WHERE d.card_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM db_pipeline.card_product_doc l
      WHERE l.card_doc_id=d.card_doc_id AND l.card_id=d.card_id
  )
  AND NOT EXISTS (
      SELECT 1 FROM db_pipeline.card_product_variant_doc l
      WHERE l.card_doc_id=d.card_doc_id AND l.card_id=d.card_id
  );
