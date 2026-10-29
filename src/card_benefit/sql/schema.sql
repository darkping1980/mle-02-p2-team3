--=========================================================
-- payment_card 카드 상품 테이블 DDL (수동 실행 전용)
--   애플리케이션과 테스트는 이 파일을 자동 실행하지 않는다.
--   기존 테이블과 겹치지 않도록 별도 스키마 payment_card를 사용한다.
--   IF NOT EXISTS만 사용하므로 다시 실행해도 기존 데이터를 지우지 않는다.
--=========================================================

CREATE SCHEMA IF NOT EXISTS payment_card;

CREATE TABLE IF NOT EXISTS payment_card.card_product (
    card_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issuer     TEXT        NOT NULL,                      -- 카드사
    card_name  TEXT        NOT NULL,                      -- 카드 상품명
    card_type  TEXT        NOT NULL
               CHECK (card_type IN ('CREDIT', 'DEBIT')),  -- CREDIT: 신용카드, DEBIT: 체크카드
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()         -- 등록일시
);
