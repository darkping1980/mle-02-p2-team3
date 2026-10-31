-- card_product/document relationship, phase-1 DDL DRAFT (2026-10-31).
-- DO NOT run against Supabase until the owner approves migration/backfill.
-- Baseline: src/data/backup/dump-postgres-202610311136.sql, schema db_pipeline.
-- No physical foreign keys. Logical joins and gates are in card_product_validation_draft.sql.
-- Existing: card_doc PK(card_doc_id), card_bnft PK(card_doc_id,card_bnft_id),
-- card_cond PK(card_doc_id,card_cond_id). Existing card_doc.card_id is bigint NOT NULL;
-- UNIQUE(card_id,doc_type_cd,doc_version_no) and unique partial index
-- uq_card_doc_active(card_id,doc_type_cd) assume one document belongs to one card.
-- Source evidence for the *need* for brand-specific links: Hana Card public card page
-- https://m.hanacard.co.kr/MKCDCM1000M.web?CD_PD_SEQ=10120
-- states VISA Platinum 01 / Mastercard Platinum 01 by chosen brand.
-- The user-supplied Drive folder could not be inspected in this drafting session.
-- JADE/AMEX03, Mastercard01/04, VP001 2023/2026 are validation scenarios,
-- not approved product-document mappings. No policy/benefit sharing is inferred.

BEGIN;

-- Existing card_id columns are bigint. Explicit historic IDs are permitted
-- during backfill; afterwards synchronize seq_card_product above MAX(card_id).
-- The numeric ID uses a sequence directly; fn_get_biz_id returns varchar IDs.
CREATE SEQUENCE db_pipeline.seq_card_product AS bigint;
CREATE TABLE db_pipeline.card_product (
    card_id bigint NOT NULL DEFAULT nextval('db_pipeline.seq_card_product'::regclass),
    product_cd varchar(80) NOT NULL,
    product_nm text NOT NULL,
    card_kind_cd varchar(10) NOT NULL,
    product_status_cd varchar(20) NOT NULL DEFAULT 'ACTIVE',
    launched_on date,
    discontinued_on date,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT card_product_pkey PRIMARY KEY (card_id),
    CONSTRAINT card_product_product_cd_key UNIQUE (product_cd),
    CONSTRAINT card_product_card_kind_cd_check CHECK (card_kind_cd IN ('CREDIT','DEBIT')),
    CONSTRAINT card_product_status_check CHECK (product_status_cd IN ('ACTIVE','DISCONTINUED')),
    CONSTRAINT card_product_dates_check CHECK (
        discontinued_on IS NULL OR launched_on IS NULL OR discontinued_on >= launched_on
    )
);
ALTER SEQUENCE db_pipeline.seq_card_product
    OWNED BY db_pipeline.card_product.card_id;
COMMENT ON TABLE db_pipeline.card_product IS '카드 상품 마스터; 문서/브랜드 발급형의 업무 부모. 1차 설계 초안';
COMMENT ON COLUMN db_pipeline.card_product.card_id IS '기존 card_doc/card_bnft/card_cond.card_id와 타입을 맞춘 상품 ID; 이행 시 기존 값을 명시적으로 보존';
COMMENT ON COLUMN db_pipeline.card_product.product_cd IS '상품의 안정적 업무 코드; PDF 파일명/문서판 번호가 아님';
COMMENT ON COLUMN db_pipeline.card_product.card_kind_cd IS 'CREDIT 또는 DEBIT';
CREATE INDEX card_product_kind_status_idx
    ON db_pipeline.card_product (card_kind_cd, product_status_cd);

-- Same business product may have distinct issued brand/grade/service variants.
-- Parent card_id is inherited into the child's composite PK. A changed service
-- type is a new variant, not an overwrite of an old variant's identity.
CREATE SEQUENCE db_pipeline.seq_card_product_variant AS bigint;
CREATE TABLE db_pipeline.card_product_variant (
    card_id bigint NOT NULL,
    card_variant_id varchar(20) NOT NULL
        DEFAULT db_pipeline.fn_get_biz_id('card_product_variant'),
    variant_cd varchar(80) NOT NULL,
    variant_nm text NOT NULL,
    brand_cd varchar(30) NOT NULL,
    service_grade_cd varchar(30) NOT NULL DEFAULT 'NONE',
    service_type_cd varchar(30) NOT NULL DEFAULT 'NONE',
    variant_status_cd varchar(20) NOT NULL DEFAULT 'ACTIVE',
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT card_product_variant_pkey PRIMARY KEY (card_id, card_variant_id),
    CONSTRAINT card_product_variant_cd_key UNIQUE (card_id, variant_cd),
    CONSTRAINT card_product_variant_status_check
        CHECK (variant_status_cd IN ('ACTIVE','DISCONTINUED')),
    CONSTRAINT card_product_variant_codes_check
        CHECK (length(trim(brand_cd)) > 0 AND length(trim(service_grade_cd)) > 0
           AND length(trim(service_type_cd)) > 0)
);
ALTER SEQUENCE db_pipeline.seq_card_product_variant
    OWNED BY db_pipeline.card_product_variant.card_variant_id;
COMMENT ON TABLE db_pipeline.card_product_variant IS '상품의 브랜드·등급·선택서비스별 발급형; PK가 상품 PK를 상속';
COMMENT ON COLUMN db_pipeline.card_product_variant.service_type_cd IS '예: PLATINUM_01/03/04, VP001. 브랜드·등급만으로 적용 문서를 결정하지 않음';
CREATE INDEX card_product_variant_service_idx
    ON db_pipeline.card_product_variant (brand_cd, service_grade_cd, service_type_cd);

-- card_doc remains a document-edition entity, not a child of one product.
-- Keep legacy card_id nullable for old rows and old pipeline compatibility.
-- New documents, including product-specific ones, should have card_id NULL;
-- applicability lives in links. Backfill existing rows before relying on links.
-- Existing child card_bnft/card_cond.card_id is NOT changed in phase 1.
DROP INDEX db_pipeline.uq_card_doc_active;
ALTER TABLE db_pipeline.card_doc
    ALTER COLUMN card_id DROP NOT NULL,
    DROP CONSTRAINT card_doc_card_id_doc_type_cd_doc_version_no_key,
    ADD COLUMN doc_family_cd varchar(100),
    ADD CONSTRAINT card_doc_family_cd_check
        CHECK (doc_family_cd IS NULL OR doc_family_cd ~ '^[A-Za-z0-9][A-Za-z0-9_.:-]*$');
ALTER TABLE db_pipeline.card_doc
    DROP CONSTRAINT card_doc_doc_type_cd_check,
    ADD CONSTRAINT card_doc_doc_type_cd_check
        CHECK (doc_type_cd IN ('PRODUCT_GUIDE','TERMS','BRAND_SERVICE','ETC'));
COMMENT ON TABLE db_pipeline.card_doc IS '원천 문서의 실제 파일·문서판; 공유 가능하며 상품 적용은 연결 테이블에서 관리';
COMMENT ON COLUMN db_pipeline.card_doc.card_id IS '이행 기간의 기존 단일 상품 힌트; 신규 적용 관계의 권위 있는 키가 아님. 신규 공유 문서는 NULL';
COMMENT ON COLUMN db_pipeline.card_doc.doc_family_cd IS '개정판을 묶는 문서 계열 코드; 같은 계열의 서로 다른 파일/판본은 각각 card_doc_id를 가짐';
COMMENT ON COLUMN db_pipeline.card_doc.doc_version_no IS '문서판 번호; 단독으로 상품/서비스 적용 기간을 뜻하지 않음';
COMMENT ON COLUMN db_pipeline.card_doc.doc_release_date IS '기존 상품 출시일 기록; 공통 문서는 확인된 문서 발행일만 기재, 관계 적용 시작일과 혼동 금지';
COMMENT ON COLUMN db_pipeline.card_doc.doc_status IS '기존 문서 상태; 현재 상품별 적용 여부는 승인된 관계 행의 기간으로 판정. SUPERSEDED도 과거 유효 이력 조회에 포함';
CREATE INDEX card_doc_family_version_idx
    ON db_pipeline.card_doc (doc_family_cd, doc_version_no, doc_release_date);

-- Product-wide relationship: a product guide or common terms can be linked to
-- many products. N:M PK inherits both endpoint IDs. Applies to all variants.
CREATE TABLE db_pipeline.card_product_doc (
    card_id bigint NOT NULL,
    card_doc_id varchar(20) NOT NULL,
    doc_role_cd varchar(20) NOT NULL,
    effective_from date,
    effective_to_excl date,
    approval_status_cd varchar(20) NOT NULL DEFAULT 'PENDING',
    applicability_basis_txt text NOT NULL,
    approval_note text,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT card_product_doc_pkey PRIMARY KEY (card_id, card_doc_id),
    CONSTRAINT card_product_doc_role_check
        CHECK (doc_role_cd IN ('PRODUCT_GUIDE','COMMON_TERMS','OTHER')),
    CONSTRAINT card_product_doc_approval_check
        CHECK (approval_status_cd IN ('PENDING','APPROVED','REJECTED')),
    CONSTRAINT card_product_doc_period_check
        CHECK (effective_to_excl IS NULL OR
               (effective_from IS NOT NULL AND effective_to_excl > effective_from)),
    CONSTRAINT card_product_doc_approved_check
        CHECK (approval_status_cd <> 'APPROVED' OR
               (effective_from IS NOT NULL AND length(trim(applicability_basis_txt)) > 0))
);
COMMENT ON TABLE db_pipeline.card_product_doc IS '상품 전체↔원천 문서판 N:M; PK는 상품/문서 양 부모 키; 승인과 적용 기간은 관계의 사실';
COMMENT ON COLUMN db_pipeline.card_product_doc.effective_to_excl IS '적용 종료일 미포함; [effective_from,effective_to_excl)';
COMMENT ON COLUMN db_pipeline.card_product_doc.applicability_basis_txt IS '해당 상품 적용을 입증한 문구/출처. 확인 전에는 APPROVED 금지';
CREATE INDEX card_product_doc_doc_idx
    ON db_pipeline.card_product_doc (card_doc_id, card_id);
CREATE INDEX card_product_doc_current_idx
    ON db_pipeline.card_product_doc (card_id, effective_from, effective_to_excl)
    WHERE approval_status_cd = 'APPROVED';

-- Issued-variant-specific relationship: brand service booklet and any guide
-- specific to one brand/service variant. The PK inherits (card_id,variant_id)
-- from card_product_variant and card_doc_id from card_doc. A shared booklet may
-- be linked to many variants/products without duplicating its document row.
CREATE TABLE db_pipeline.card_product_variant_doc (
    card_id bigint NOT NULL,
    card_variant_id varchar(20) NOT NULL,
    card_doc_id varchar(20) NOT NULL,
    doc_role_cd varchar(20) NOT NULL DEFAULT 'BRAND_SERVICE',
    effective_from date,
    effective_to_excl date,
    approval_status_cd varchar(20) NOT NULL DEFAULT 'PENDING',
    applicability_basis_txt text NOT NULL,
    approval_note text,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT card_product_variant_doc_pkey
        PRIMARY KEY (card_id, card_variant_id, card_doc_id),
    CONSTRAINT card_product_variant_doc_role_check
        CHECK (doc_role_cd IN ('BRAND_SERVICE','PRODUCT_GUIDE','OTHER')),
    CONSTRAINT card_product_variant_doc_approval_check
        CHECK (approval_status_cd IN ('PENDING','APPROVED','REJECTED')),
    CONSTRAINT card_product_variant_doc_period_check
        CHECK (effective_to_excl IS NULL OR
               (effective_from IS NOT NULL AND effective_to_excl > effective_from)),
    CONSTRAINT card_product_variant_doc_approved_check
        CHECK (approval_status_cd <> 'APPROVED' OR
               (effective_from IS NOT NULL AND length(trim(applicability_basis_txt)) > 0))
);
COMMENT ON TABLE db_pipeline.card_product_variant_doc IS '브랜드·등급·선택서비스 발급형↔문서판 N:M; 상품/발급형 부모 PK를 상속';
COMMENT ON COLUMN db_pipeline.card_product_variant_doc.applicability_basis_txt IS '발급형별 적용 근거; 문서의 존재만으로 상품 적용을 승인하지 않음';
CREATE INDEX card_product_variant_doc_doc_idx
    ON db_pipeline.card_product_variant_doc (card_doc_id, card_id, card_variant_id);
CREATE INDEX card_product_variant_doc_current_idx
    ON db_pipeline.card_product_variant_doc
       (card_id, card_variant_id, effective_from, effective_to_excl)
    WHERE approval_status_cd = 'APPROVED';

COMMIT;

-- Not in phase 1: shared benefit-policy entity, card_bnft/card_cond/card_bnft_rule
-- key migration, historical backfill, and any live data load. A shared PDF is
-- not evidence that its extracted benefit policy can be shared unchanged.
-- Legacy child rows still carry card_doc_id + card_id; for shared documents
-- future confirmed policy rows will need an explicit product/variant scope.
