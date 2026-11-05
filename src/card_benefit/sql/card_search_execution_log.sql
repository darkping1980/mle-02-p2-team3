-- Streamlit GraphRAG 로그를 이벤트별 행에서 질문별 1행으로 옮기는 승인 대기용 마이그레이션이다.
-- 기존 app_log는 app_log_event_archive로 이름만 바꾸어 모든 원본 행과 ID를 보존한다.
-- 새 app_log에는 기존 이벤트를 request_id별로 합친 스냅샷을 채운다.
-- 이 파일은 앱에서 자동 실행하지 않으며 별도 승인 전 운영 DB에 실행하지 않는다.

BEGIN;

DO $migration$
BEGIN
    IF to_regclass('db_pipeline.app_log') IS NULL THEN
        RAISE EXCEPTION 'Expected existing table db_pipeline.app_log';
    END IF;
    IF to_regclass('db_pipeline.app_log_event_archive') IS NOT NULL THEN
        RAISE EXCEPTION 'Archive table db_pipeline.app_log_event_archive already exists; inspect before migration';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'db_pipeline' AND table_name = 'app_log' AND column_name = 'log_type'
    ) OR NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'db_pipeline' AND table_name = 'app_log' AND column_name = 'log_message'
    ) THEN
        RAISE EXCEPTION 'db_pipeline.app_log is not the expected event-row layout';
    END IF;
    IF pg_get_serial_sequence('db_pipeline.app_log', 'app_log_id') IS NULL THEN
        RAISE EXCEPTION 'db_pipeline.app_log.app_log_id identity sequence was not found';
    END IF;
END
$migration$;

LOCK TABLE db_pipeline.app_log IN ACCESS EXCLUSIVE MODE;

ALTER TABLE db_pipeline.app_log RENAME TO app_log_event_archive;
ALTER TABLE db_pipeline.app_log_event_archive
    RENAME CONSTRAINT app_log_pkey TO app_log_event_archive_pkey;
ALTER TABLE db_pipeline.app_log_event_archive
    RENAME CONSTRAINT app_log_type_ck TO app_log_event_archive_type_ck;
DO $sequence$
DECLARE
    identity_sequence text;
BEGIN
    identity_sequence := pg_get_serial_sequence('db_pipeline.app_log_event_archive', 'app_log_id');
    EXECUTE format('ALTER SEQUENCE %s RENAME TO %I',
                   identity_sequence, 'app_log_event_archive_app_log_id_seq');
END
$sequence$;
ALTER INDEX db_pipeline.ix_app_log_session_created
    RENAME TO ix_app_log_event_archive_session_created;
ALTER INDEX db_pipeline.ix_app_log_request_created
    RENAME TO ix_app_log_event_archive_request_created;

CREATE TABLE db_pipeline.app_log (
    app_log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id uuid NOT NULL,
    request_id uuid NOT NULL,
    client_ip inet,
    request_text text NOT NULL,
    execution_log text NOT NULL DEFAULT '',
    response_text text NOT NULL DEFAULT '',
    error_text text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT app_log_session_request_uk UNIQUE (session_id, request_id)
);

-- 기존 이벤트 전체는 archive에 그대로 두고, 새 테이블에는 요청당 한 행으로 집계한다.
INSERT INTO db_pipeline.app_log
    (session_id, request_id, client_ip, request_text, execution_log,
     response_text, error_text, created_at)
SELECT session_id,
       request_id,
       (array_agg(client_ip ORDER BY created_at, app_log_id)
           FILTER (WHERE client_ip IS NOT NULL))[1],
       COALESCE(string_agg(log_message, E'\n\n' ORDER BY created_at, app_log_id)
           FILTER (WHERE log_type = 'REQUEST'), ''),
       COALESCE(string_agg(log_message, E'\n\n' ORDER BY created_at, app_log_id)
           FILTER (WHERE log_type = 'QUERY'), ''),
       COALESCE(string_agg(log_message, E'\n\n' ORDER BY created_at, app_log_id)
           FILTER (WHERE log_type = 'RESPONSE'), ''),
       NULLIF(string_agg(log_message, E'\n\n' ORDER BY created_at, app_log_id)
           FILTER (WHERE log_type = 'ERROR'), ''),
       COALESCE(min(created_at) FILTER (WHERE log_type = 'REQUEST'), min(created_at))
  FROM db_pipeline.app_log_event_archive
 GROUP BY session_id, request_id;

DO $verify_migration$
DECLARE
    expected_rows bigint;
    actual_rows bigint;
BEGIN
    SELECT count(*) INTO expected_rows
      FROM (SELECT session_id, request_id
              FROM db_pipeline.app_log_event_archive
             GROUP BY session_id, request_id) AS request_groups;
    SELECT count(*) INTO actual_rows FROM db_pipeline.app_log;
    IF actual_rows <> expected_rows THEN
        RAISE EXCEPTION 'Request log migration count mismatch: expected %, got %',
                        expected_rows, actual_rows;
    END IF;
END
$verify_migration$;

CREATE INDEX ix_app_log_session_created
    ON db_pipeline.app_log (session_id, created_at DESC);
CREATE INDEX ix_app_log_request_created
    ON db_pipeline.app_log (request_id, created_at DESC);

COMMENT ON TABLE db_pipeline.app_log IS 'Streamlit GraphRAG 질문별 요청·SQL/Cypher·응답·오류 로그';
COMMENT ON TABLE db_pipeline.app_log_event_archive IS '질문별 app_log로 전환하기 전 이벤트 행 원본 보관';
COMMENT ON COLUMN db_pipeline.app_log.app_log_id IS '질문 로그 행 ID';
COMMENT ON COLUMN db_pipeline.app_log.session_id IS 'Streamlit 브라우저 세션 UUID';
COMMENT ON COLUMN db_pipeline.app_log.request_id IS '질문 제출별 요청 UUID';
COMMENT ON COLUMN db_pipeline.app_log.client_ip IS '신뢰할 수 있는 클라이언트 IP(확인 불가하면 NULL)';
COMMENT ON COLUMN db_pipeline.app_log.request_text IS '사용자가 제출한 질문';
COMMENT ON COLUMN db_pipeline.app_log.execution_log IS '실행 순서대로 줄바꿈 결합한 SQL/Cypher 로그';
COMMENT ON COLUMN db_pipeline.app_log.response_text IS '최종 사용자 응답 본문';
COMMENT ON COLUMN db_pipeline.app_log.error_text IS '발생한 오류의 안전한 요약';
COMMENT ON COLUMN db_pipeline.app_log.created_at IS '질문 요청 시각';

COMMIT;
