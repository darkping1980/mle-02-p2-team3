-- P3: card_evidence_link·뷰의 항목 ID 컬럼을 card_product_item 기준으로 정리하고, 혜택이 아닌 항목의 근거 주체 ITEM을 추가한다.
-- 근거 연결 행의 값은 바꾸지 않는다(컬럼 이름만 변경). backup_card_bnft는 건드리지 않는다.
BEGIN;

ALTER TABLE db_pipeline.card_evidence_link RENAME COLUMN card_bnft_id TO card_product_item_id;
COMMENT ON COLUMN db_pipeline.card_evidence_link.card_product_item_id IS
    '근거 주체 카드 상품 항목 ID(card_product_item.card_product_item_id). BNFT·RULE·REL은 혜택 항목, ITEM은 혜택이 아닌 항목(연회비 등)';

-- 근거 주체: 기존 CARD/BNFT/RULE/REL + ITEM(혜택이 아닌 상품 항목 자체 또는 그 안의 줄)
ALTER TABLE db_pipeline.card_evidence_link DROP CONSTRAINT card_evidence_link_ck_2;
ALTER TABLE db_pipeline.card_evidence_link ADD CONSTRAINT card_evidence_link_ck_2 CHECK (
CASE ev_subject_cd
    WHEN 'CARD' THEN num_nonnulls(card_product_item_id, rule_key, relation_key) = 0
    WHEN 'BNFT' THEN card_product_item_id IS NOT NULL AND num_nonnulls(rule_key, relation_key) = 0
    WHEN 'RULE' THEN card_product_item_id IS NOT NULL AND rule_key IS NOT NULL AND relation_key IS NULL
    WHEN 'REL'  THEN card_product_item_id IS NOT NULL AND relation_key IS NOT NULL AND rule_key IS NULL
    WHEN 'ITEM' THEN card_product_item_id IS NOT NULL AND num_nonnulls(rule_key, relation_key) = 0
    ELSE false
END);

INSERT INTO db_pipeline.common_cd (common_code_grp_id, common_cd, common_cd_nm, create_user_id, update_user_id, common_cd_desc)
VALUES ('EV_SUBJECT', 'ITEM', '상품 항목', 'P1_PRODUCT_ITEM', 'P1_PRODUCT_ITEM',
        '근거가 혜택이 아닌 카드 상품 항목(연회비 등)을 가리키는 경우. card_product_item_id 필수, 줄 단위는 ev_item_cd로 구분')
ON CONFLICT (common_code_grp_id, common_cd) DO NOTHING;

-- 뷰 출력 컬럼: 항목 ID는 card_product_item_id로 부른다. 혜택 관계 뷰(v_card_bnft_rel)의 from/to_bnft_id는 혜택 전용 의미라 유지
ALTER VIEW db_pipeline.v_card_rule RENAME COLUMN card_bnft_id TO card_product_item_id;
ALTER VIEW db_pipeline.v_card_rule_target RENAME COLUMN card_bnft_id TO card_product_item_id;
ALTER VIEW db_pipeline.v_card_cond_atom RENAME COLUMN card_bnft_id TO card_product_item_id;

COMMIT;
