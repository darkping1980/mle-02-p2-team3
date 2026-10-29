--=========================================================
-- 카드 상품 등록·조회 mapper (namespace: payment_card)
--   테이블은 card_benefit/sql/schema.sql로 미리 만들어 둔다(이 mapper는 DDL을 실행하지 않는다).
--   INSERT ... RETURNING은 등록한 행을 결과 행으로 돌려주므로 접미사 없이 선언했다.
--=========================================================

-- name: insert_card
INSERT INTO payment_card.card_product (issuer, card_name, card_type)
VALUES (:issuer, :card_name, :card_type)
RETURNING card_id, issuer, card_name, card_type, created_at;

-- name: list_cards
SELECT card_id, issuer, card_name, card_type, created_at
FROM payment_card.card_product
ORDER BY card_id;

-- name: find_card
SELECT card_id, issuer, card_name, card_type, created_at
FROM payment_card.card_product
WHERE card_id = :card_id;
