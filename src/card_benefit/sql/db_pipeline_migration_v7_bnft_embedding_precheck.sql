-- 혜택 임베딩 컬럼 추가 전 읽기 전용 점검. 기준: db_pipeline-postgres-202611030524.sql
-- 기대값: 1) vector 설치 2) 추가 컬럼 0건 3) 대상 행은 정보용 4) 잠금 0건 5) 정합성 게이트는 evidence_not_approved만

-- 1. pgvector 설치 위치. migration은 extensions 스키마를 전제로 한다.
SELECT e.extname, e.extversion, n.nspname
FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
WHERE e.extname = 'vector';

-- 2. 추가할 컬럼이 이미 있는지
SELECT table_name, column_name, udt_name
FROM information_schema.columns
WHERE table_schema = 'db_pipeline'
  AND table_name IN ('card_bnft', 'card_common_bnft')
  AND column_name IN ('bnft_search_txt', 'bnft_embedding');

-- 3. 변경 대상 건수
SELECT 'card_bnft' AS table_nm, count(*) AS row_cnt FROM db_pipeline.card_bnft
UNION ALL
SELECT 'card_common_bnft', count(*) FROM db_pipeline.card_common_bnft;

-- 4. 다른 세션의 잠금과 실행 중 쿼리
SELECT a.application_name, a.state, l.mode, c.relname
FROM pg_locks l
JOIN pg_class c ON c.oid = l.relation
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_stat_activity a ON a.pid = l.pid
WHERE n.nspname = 'db_pipeline' AND a.pid <> pg_backend_pid();

-- 5. 변경 전 정합성 게이트
SELECT gate_cd, count(*) AS issue_cnt FROM db_pipeline.v_card_integrity_issue GROUP BY gate_cd ORDER BY gate_cd;
