-- 실행 전 별도 승인 필요. 실제 실행하지 않은 등록안.
BEGIN;
-- 동일 코드/상품명, 문서 상태·해시, 기존 card_id를 검증한다.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM db_pipeline.card_product
             WHERE product_cd = 'HANA_DEBIT_ONE_PICK_STYLE'
                OR product_nm = 'ONE PICK STYLE 하나 체크카드') THEN
    RAISE EXCEPTION '상품 중복';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM db_pipeline.card_doc
                 WHERE card_doc_id = '20261031_000001' AND card_id IS NULL
                   AND doc_status = 'ACTIVE'
                   AND doc_sha256 = '6ec9641c2e318ce9429a916f5d01c0468ccc3cffb238eb1162a43b280e25c6d2') THEN
    RAISE EXCEPTION '문서 불일치';
  END IF;
END $$;

WITH product AS (
  INSERT INTO db_pipeline.card_product
    (product_cd, product_nm, issuer, card_kind_cd, product_status_cd, launched_on,
     brand_opt_list, create_user_id, update_user_id)
  VALUES ('HANA_DEBIT_ONE_PICK_STYLE', 'ONE PICK STYLE 하나 체크카드', '하나카드',
          'DEBIT', 'ACTIVE', DATE '2026-03-30',
          '[{"brand_opt_cd":"LOCAL","brand_opt_nm":"국내전용","brand_cd":"LOCAL","service_grade_cd":"NONE","service_type_cd":"NONE","brand_opt_status_cd":"ACTIVE"},{"brand_opt_cd":"MASTERCARD","brand_opt_nm":"Mastercard","brand_cd":"MASTERCARD","service_grade_cd":"NONE","service_type_cd":"NONE","brand_opt_status_cd":"ACTIVE"}]'::jsonb,
          'SYSTEM', 'SYSTEM')
  RETURNING card_id
)
INSERT INTO db_pipeline.card_product_doc
  (card_id, card_doc_id, doc_role_cd, approval_status_cd, applicability_basis_txt, create_user_id, update_user_id)
SELECT card_id, '20261031_000001', 'PRODUCT_GUIDE', 'PENDING',
       'PDF 상품명 일치; 공식 서버 URL 추정 확인, 적용 승인 대기', 'SYSTEM', 'SYSTEM'
FROM product;

-- 승인된 실행자가 결과를 확인한 뒤 COMMIT 또는 ROLLBACK을 직접 선택한다.
SELECT p.card_id, p.product_cd, p.product_nm, p.card_kind_cd, p.launched_on, p.product_status_cd,
       p.brand_opt_list, pd.card_doc_id, pd.doc_role_cd, pd.approval_status_cd, d.card_id AS doc_card_id
FROM db_pipeline.card_product p
JOIN db_pipeline.card_product_doc pd ON pd.card_id = p.card_id
JOIN db_pipeline.card_doc d ON d.card_doc_id = pd.card_doc_id
WHERE p.product_cd = 'HANA_DEBIT_ONE_PICK_STYLE';
-- COMMIT;
-- ROLLBACK;
