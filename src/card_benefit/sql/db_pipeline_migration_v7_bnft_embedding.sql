-- CARD_BNFT, CARD_COMMON_BNFT에 혜택 검색 텍스트와 임베딩 컬럼을 추가한다.
-- 기존 행의 값, PK, UNIQUE, CHECK, 뷰는 바꾸지 않는다. 벡터 인덱스는 실험 단계라 만들지 않는다.
-- 임베딩 실행 이력은 새 컬럼이나 테이블 없이 CARD_AI_RUN에 남기며, 이를 위해 RUN_STAGE=EMBED 코드 1건을 추가한다.
-- 재실행해도 결과가 같다. 되돌리기: db_pipeline_migration_v7_bnft_embedding_rollback.sql
BEGIN;

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
        WHERE e.extname = 'vector' AND n.nspname = 'extensions'
    ) THEN
        RAISE EXCEPTION 'extensions 스키마에 pgvector가 없습니다';
    END IF;
END;
$$;

ALTER TABLE db_pipeline.card_bnft
    ADD COLUMN IF NOT EXISTS bnft_search_txt text,
    ADD COLUMN IF NOT EXISTS bnft_embedding extensions.vector(1536);

ALTER TABLE db_pipeline.card_common_bnft
    ADD COLUMN IF NOT EXISTS bnft_search_txt text,
    ADD COLUMN IF NOT EXISTS bnft_embedding extensions.vector(1536);

COMMENT ON COLUMN db_pipeline.card_bnft.bnft_search_txt IS '혜택 검색 텍스트. 임베딩 모델에 전달한 입력과 동일. 카드명 미포함';
COMMENT ON COLUMN db_pipeline.card_bnft.bnft_embedding IS '혜택 검색 텍스트 임베딩. 실제 적용 여부 판단에는 사용하지 않음';
COMMENT ON COLUMN db_pipeline.card_common_bnft.bnft_search_txt IS '공통 혜택 검색 텍스트. 임베딩 모델에 전달한 입력과 동일. 카드명 미포함';
COMMENT ON COLUMN db_pipeline.card_common_bnft.bnft_embedding IS '공통 혜택 검색 텍스트 임베딩. 카드 적용 관계는 card_common_bnft_apply로 확인';

INSERT INTO db_pipeline.common_cd (common_code_grp_id, common_cd, common_cd_nm, common_cd_desc, create_user_id, update_user_id)
VALUES ('RUN_STAGE', 'EMBED', '임베딩', '혜택 검색 텍스트 임베딩 생성 실행', 'SYSTEM', 'SYSTEM')
ON CONFLICT ON CONSTRAINT pk_common_cd DO NOTHING;

COMMIT;
