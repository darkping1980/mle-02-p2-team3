-- 혜택 임베딩 컬럼 추가를 되돌린다. 검색 텍스트와 벡터만 사라지고 혜택 원본 값은 그대로다.
-- 임베딩 실행 이력(CARD_AI_RUN)은 삭제하지 않는다. 이력이 남아 있으면 EMBED 코드도 유지해 정합성 게이트를 깨지 않는다.
BEGIN;

SET LOCAL lock_timeout = '5s';

ALTER TABLE db_pipeline.card_bnft
    DROP COLUMN IF EXISTS bnft_embedding,
    DROP COLUMN IF EXISTS bnft_search_txt;

ALTER TABLE db_pipeline.card_common_bnft
    DROP COLUMN IF EXISTS bnft_embedding,
    DROP COLUMN IF EXISTS bnft_search_txt;

DELETE FROM db_pipeline.common_cd c
WHERE c.common_code_grp_id = 'RUN_STAGE'
  AND c.common_cd = 'EMBED'
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_ai_run r WHERE r.run_stage_cd = 'EMBED');

COMMIT;
