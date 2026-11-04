-- card_product_item: 카드 상품 항목(BENEFIT, ANNUAL_FEE …) 테이블 생성 + card_bnft BENEFIT 이관 (P1+P2, 2026-11-04)
-- 기존 card_bnft·card_evidence_link는 읽기만 한다(DELETE/UPDATE 없음). 한 트랜잭션으로 실행하고 실패하면 전부 롤백한다.
-- 되돌리기: db_pipeline_card_product_item_rollback.sql
-- 물리 FK는 두지 않는다(스키마 전체 정책). 근거 연결은 v_card_product_item_evidence 로 card_bnft_id = card_product_item_id 매핑을 제공한다.

BEGIN;

-- 1. ID 시퀀스. 형식은 기존과 같은 YYYYMMDD_nnnnnn(fn_get_biz_id).
--    기존 card_bnft 순번 다음부터 발급해 이관된 ID와 새 ID가 같은 테이블 안에서 겹치지 않게 한다.
CREATE SEQUENCE db_pipeline.seq_card_product_item AS bigint START 1 INCREMENT 1 MINVALUE 1 MAXVALUE 999999 CACHE 1 CYCLE;
SELECT setval('db_pipeline.seq_card_product_item', (SELECT last_value FROM db_pipeline.seq_card_bnft), true);
COMMENT ON SEQUENCE db_pipeline.seq_card_product_item IS '카드 상품 항목 ID 발급. 이관 시 seq_card_bnft 마지막 값 다음부터 시작';

-- 2. 유형별 item_data 검증. BENEFIT은 비었거나 BENEFIT_V1, ANNUAL_FEE는 ANNUAL_FEE_V1 줄 목록.
CREATE OR REPLACE FUNCTION db_pipeline.fn_valid_item_data(p_type text, p_data jsonb)
RETURNS boolean
LANGUAGE plpgsql IMMUTABLE
SET search_path TO 'pg_catalog'
AS $function$
DECLARE
    v_line jsonb;
    v_keys text[] := '{}';
    v_basic numeric; v_aff numeric; v_total numeric;
BEGIN
    IF p_data IS NULL OR jsonb_typeof(p_data) <> 'object' THEN
        RETURN false;
    END IF;
    IF p_type = 'BENEFIT' THEN
        RETURN NOT (p_data ? 'schema_ver') OR p_data->>'schema_ver' = 'BENEFIT_V1';
    END IF;
    IF p_type = 'ANNUAL_FEE' THEN
        IF p_data->>'schema_ver' IS DISTINCT FROM 'ANNUAL_FEE_V1'
           OR jsonb_typeof(p_data->'fee_lines') IS DISTINCT FROM 'array'
           OR jsonb_array_length(p_data->'fee_lines') = 0 THEN
            RETURN false;
        END IF;
        FOR v_line IN SELECT value FROM jsonb_array_elements(p_data->'fee_lines') LOOP
            IF jsonb_typeof(v_line) <> 'object'
               OR coalesce(v_line->>'line_key', '') = ''
               OR (v_line->>'line_key') = ANY (v_keys)
               OR coalesce(v_line->>'holder_type_cd', '') NOT IN ('PRINCIPAL', 'FAMILY') THEN
                RETURN false;
            END IF;
            v_keys := v_keys || (v_line->>'line_key');
            -- 금액은 없거나 0 이상 정수
            IF EXISTS (SELECT 1 FROM unnest(ARRAY['basic_fee_amt', 'affiliate_fee_amt', 'total_fee_amt']) AS f(k)
                       WHERE v_line ? f.k AND jsonb_typeof(v_line->f.k) <> 'null'
                         AND (jsonb_typeof(v_line->f.k) <> 'number' OR (v_line->>f.k)::numeric < 0
                              OR (v_line->>f.k)::numeric <> trunc((v_line->>f.k)::numeric))) THEN
                RETURN false;
            END IF;
            v_basic := (v_line->>'basic_fee_amt')::numeric;
            v_aff := (v_line->>'affiliate_fee_amt')::numeric;
            v_total := (v_line->>'total_fee_amt')::numeric;
            IF v_basic IS NOT NULL AND v_aff IS NOT NULL AND v_total IS NOT NULL AND v_basic + v_aff <> v_total THEN
                RETURN false;
            END IF;
            -- 브랜드 옵션: null(전 브랜드) 또는 비어 있지 않은 문자열 배열
            IF v_line ? 'brand_opt_cds' AND jsonb_typeof(v_line->'brand_opt_cds') <> 'null'
               AND (jsonb_typeof(v_line->'brand_opt_cds') <> 'array' OR jsonb_array_length(v_line->'brand_opt_cds') = 0
                    OR EXISTS (SELECT 1 FROM jsonb_array_elements(v_line->'brand_opt_cds') b WHERE jsonb_typeof(b) <> 'string')) THEN
                RETURN false;
            END IF;
        END LOOP;
        RETURN true;
    END IF;
    RETURN false;   -- 아직 지원하지 않는 유형
END;
$function$;
COMMENT ON FUNCTION db_pipeline.fn_valid_item_data(text, jsonb) IS
    '카드 상품 항목 item_data 계약 검증. BENEFIT: {} 또는 schema_ver=BENEFIT_V1. ANNUAL_FEE: schema_ver=ANNUAL_FEE_V1, fee_lines 1줄 이상(line_key 유일, holder_type_cd PRINCIPAL/FAMILY, 금액 0 이상 정수, basic+affiliate=total, brand_opt_cds null 또는 비지 않은 배열)';

-- 3. 테이블. 혜택의 조건식·규칙·관계는 기존 검증 함수·뷰·근거 RULE/REL 주체와 맞추려고 별도 컬럼으로 둔다.
CREATE TABLE db_pipeline.card_product_item (
    card_id                bigint       NOT NULL,
    card_product_item_id   varchar(20)  NOT NULL DEFAULT db_pipeline.fn_get_biz_id('card_product_item'),
    item_type_cd           varchar(20)  NOT NULL,
    item_cd                varchar(80)  NOT NULL,
    item_nm                text         NOT NULL,
    item_subtype_cd        varchar(20),
    item_origin_cd         varchar(20)  NOT NULL DEFAULT 'LOCAL',
    item_scope_cd          varchar(20)  NOT NULL DEFAULT 'PRODUCT',
    item_brand_opt_cds     text[],
    item_cond_expr         jsonb,
    rule_list              jsonb        NOT NULL DEFAULT '[]'::jsonb,
    relation_list          jsonb        NOT NULL DEFAULT '[]'::jsonb,
    item_data              jsonb        NOT NULL DEFAULT '{}'::jsonb,
    verification_status_cd varchar(25)  NOT NULL DEFAULT 'PENDING_REVIEW',
    item_valid_from        date,
    item_valid_to_excl     date,
    item_rule_txt          text,
    item_limit_txt         text,
    item_search_txt        text,
    item_embedding         extensions.vector(1536),
    item_ref               text GENERATED ALWAYS AS
                           ('card_product_item:' || card_id::text || ':' || card_product_item_id::text) STORED,
    create_date            timestamptz  NOT NULL DEFAULT now(),
    create_user_id         varchar(50)  NOT NULL,
    update_date            timestamptz  NOT NULL DEFAULT now(),
    update_user_id         varchar(50)  NOT NULL,
    CONSTRAINT card_product_item_pkey PRIMARY KEY (card_id, card_product_item_id),
    CONSTRAINT card_product_item_cd_key UNIQUE (card_id, item_cd),
    CONSTRAINT card_product_item_ref_key UNIQUE (item_ref),
    CONSTRAINT card_product_item_type_ck CHECK (item_type_cd IN ('BENEFIT', 'ANNUAL_FEE')),
    CONSTRAINT card_product_item_subtype_ck CHECK ((item_type_cd = 'BENEFIT') = (item_subtype_cd IS NOT NULL)),
    CONSTRAINT card_product_item_nonbnft_ck CHECK (item_type_cd = 'BENEFIT'
        OR (rule_list = '[]'::jsonb AND relation_list = '[]'::jsonb AND item_cond_expr IS NULL)),
    CONSTRAINT card_product_item_scope_ck CHECK (
        (item_scope_cd = 'PRODUCT' AND item_brand_opt_cds IS NULL)
     OR (item_scope_cd <> 'PRODUCT' AND coalesce(cardinality(item_brand_opt_cds), 0) > 0)),
    CONSTRAINT card_product_item_origin_ck CHECK (item_origin_cd <> 'BRAND_SERVICE' OR item_scope_cd = 'BRAND'),
    CONSTRAINT card_product_item_cond_ck CHECK (db_pipeline.fn_valid_cond_expr(item_cond_expr)),
    CONSTRAINT card_product_item_rule_ck CHECK (db_pipeline.fn_valid_rule_list(rule_list, 'LOCAL'::text)),
    CONSTRAINT card_product_item_rel_ck CHECK (db_pipeline.fn_valid_relation_list(relation_list, card_product_item_id::text)),
    CONSTRAINT card_product_item_date_ck CHECK (item_valid_to_excl IS NULL OR item_valid_from IS NULL
                                                OR item_valid_to_excl > item_valid_from),
    CONSTRAINT card_product_item_data_ck CHECK (db_pipeline.fn_valid_item_data(item_type_cd, item_data))
);
CREATE INDEX ix_card_product_item_type ON db_pipeline.card_product_item (card_id, item_type_cd);
CREATE INDEX ix_card_product_item_cond_gin ON db_pipeline.card_product_item USING gin (item_cond_expr jsonb_path_ops);
CREATE INDEX ix_card_product_item_rule_gin ON db_pipeline.card_product_item USING gin (rule_list jsonb_path_ops);
CREATE INDEX ix_card_product_item_rel_gin ON db_pipeline.card_product_item USING gin (relation_list jsonb_path_ops);
CREATE INDEX ix_card_product_item_brand_gin ON db_pipeline.card_product_item USING gin (item_brand_opt_cds);
CREATE INDEX ix_card_product_item_data_gin ON db_pipeline.card_product_item USING gin (item_data jsonb_path_ops);

COMMENT ON TABLE db_pipeline.card_product_item IS '카드 상품 항목(card_product 1:N). item_type_cd로 혜택·연회비 등을 구분. card_bnft의 후속 구조이며 기존 card_bnft_id를 card_product_item_id로 승계';
COMMENT ON COLUMN db_pipeline.card_product_item.card_product_item_id IS '항목 ID. BENEFIT 이관분은 card_bnft_id와 같은 값(근거 연결·관계 JSON·Neo4j key 승계)';
COMMENT ON COLUMN db_pipeline.card_product_item.item_type_cd IS '항목 유형(ITEM_TYPE): BENEFIT, ANNUAL_FEE. TERMS/FEE/ETC는 코드만 예약';
COMMENT ON COLUMN db_pipeline.card_product_item.item_cd IS '카드 안 업무 식별자(재등록 중복 방지). BENEFIT 이관분은 bnft_cd';
COMMENT ON COLUMN db_pipeline.card_product_item.item_subtype_cd IS 'BENEFIT의 혜택 유형(BNFT_TYPE). 다른 유형은 NULL';
COMMENT ON COLUMN db_pipeline.card_product_item.item_data IS '유형별 상세. BENEFIT: {} 또는 BENEFIT_V1, ANNUAL_FEE: ANNUAL_FEE_V1 fee_lines(본인/가족·브랜드·기본/제휴/합계 금액)';
COMMENT ON COLUMN db_pipeline.card_product_item.item_ref IS '검색·화면·LLM용 종류·소유자 포함 참조 card_product_item:{card_id}:{id}. ID 단독 식별 금지';

-- 4. 공통코드
INSERT INTO db_pipeline.common_code_grp (common_code_grp_id, common_code_grp_nm, create_user_id, update_user_id, common_code_grp_desc)
VALUES ('ITEM_TYPE', '카드 상품 항목 유형', 'P1_PRODUCT_ITEM', 'P1_PRODUCT_ITEM', 'card_product_item.item_type_cd. BENEFIT·ANNUAL_FEE 사용, TERMS·FEE·ETC 예약'),
       ('FEE_HOLDER', '연회비 대상 회원', 'P1_PRODUCT_ITEM', 'P1_PRODUCT_ITEM', 'ANNUAL_FEE item_data.fee_lines[].holder_type_cd')
ON CONFLICT (common_code_grp_id) DO NOTHING;
INSERT INTO db_pipeline.common_cd (common_code_grp_id, common_cd, common_cd_nm, create_user_id, update_user_id, common_cd_desc)
VALUES ('ITEM_TYPE', 'BENEFIT', '혜택', 'P1_PRODUCT_ITEM', 'P1_PRODUCT_ITEM', '기존 card_bnft 혜택'),
       ('ITEM_TYPE', 'ANNUAL_FEE', '연회비', 'P1_PRODUCT_ITEM', 'P1_PRODUCT_ITEM', '본인·가족, 브랜드별 기본·제휴 연회비'),
       ('ITEM_TYPE', 'TERMS', '약관(예약)', 'P1_PRODUCT_ITEM', 'P1_PRODUCT_ITEM', '예약 코드. CHECK 미허용'),
       ('ITEM_TYPE', 'FEE', '수수료(예약)', 'P1_PRODUCT_ITEM', 'P1_PRODUCT_ITEM', '예약 코드. CHECK 미허용'),
       ('ITEM_TYPE', 'ETC', '기타(예약)', 'P1_PRODUCT_ITEM', 'P1_PRODUCT_ITEM', '예약 코드. CHECK 미허용'),
       ('FEE_HOLDER', 'PRINCIPAL', '본인', 'P1_PRODUCT_ITEM', 'P1_PRODUCT_ITEM', '본인 회원 카드'),
       ('FEE_HOLDER', 'FAMILY', '가족', 'P1_PRODUCT_ITEM', 'P1_PRODUCT_ITEM', '가족 회원 카드'),
       ('EV_ITEM', 'FEE_LINE', '연회비 줄', 'P1_PRODUCT_ITEM', 'P1_PRODUCT_ITEM', '근거가 ANNUAL_FEE item_data.fee_lines의 한 줄을 가리키는 경우. ev_item_key에 line_key')
ON CONFLICT (common_code_grp_id, common_cd) DO NOTHING;

-- 5. card_bnft → card_product_item (BENEFIT). ID·조건식·규칙·관계·텍스트·임베딩을 그대로 복사한다.
INSERT INTO db_pipeline.card_product_item (
    card_id, card_product_item_id, item_type_cd, item_cd, item_nm, item_subtype_cd, item_origin_cd, item_scope_cd,
    item_brand_opt_cds, item_cond_expr, rule_list, relation_list, item_data, verification_status_cd,
    item_valid_from, item_valid_to_excl, item_rule_txt, item_limit_txt, item_search_txt, item_embedding,
    create_user_id, update_user_id)
SELECT b.card_id, b.card_bnft_id, 'BENEFIT', b.bnft_cd, b.bnft_nm, b.bnft_type_cd, b.bnft_origin_cd, b.bnft_scope_cd,
       b.bnft_brand_opt_cds, b.bnft_cond_expr, b.rule_list, b.relation_list, '{}'::jsonb, b.verification_status_cd,
       b.bnft_valid_from, b.bnft_valid_to_excl, b.bnft_rule_txt, b.bnft_limit_txt, b.bnft_search_txt, b.bnft_embedding,
       'P2_MIGRATION', 'P2_MIGRATION'
FROM db_pipeline.card_bnft b
ON CONFLICT (card_id, card_product_item_id) DO NOTHING;   -- 재실행 시 이미 이관된 행은 건너뛴다(덮어쓰지 않음)

-- 6. 근거 연결 매핑(읽기 전용 뷰). card_evidence_link 원본은 바꾸지 않고, 항목 ID로 찾아갈 수 있게 한다.
CREATE VIEW db_pipeline.v_card_product_item_evidence AS
SELECT l.evidence_link_id, l.card_id, i.card_product_item_id, i.item_type_cd, i.item_ref,
       l.ev_subject_cd, l.rule_key, l.relation_key, l.ev_item_cd, l.ev_item_key,
       l.evidence_id, l.card_doc_id, l.page_no, l.card_doc_chunk_id
FROM db_pipeline.card_evidence_link l
JOIN db_pipeline.card_product_item i
  ON i.card_id = l.card_id AND i.card_product_item_id = l.card_bnft_id
WHERE l.card_bnft_id IS NOT NULL;
COMMENT ON VIEW db_pipeline.v_card_product_item_evidence IS
    'card_evidence_link(card_bnft_id 기준)를 card_product_item에 연결한 매핑. P3에서 링크 컬럼 전환 전까지 사용';

COMMIT;
