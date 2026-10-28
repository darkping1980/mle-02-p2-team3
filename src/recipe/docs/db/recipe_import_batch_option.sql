-- OPTIONAL REVIEW DRAFT ONLY. Not part of the baseline 10-table DDL.
-- Do not execute against Supabase as part of this design task.
-- No physical FK is defined; rcp_raw.batch_id is a logical reference.

CREATE TABLE recipe.import_batch (
    batch_id varchar(20) NOT NULL,
    import_source_file_nm text NOT NULL,
    import_source_nm text NOT NULL,
    import_file_sha256 char(64),
    import_collected_at timestamptz NOT NULL DEFAULT now(),
    import_total_record_count integer,
    import_status varchar(20) NOT NULL,
    import_error_txt text,
    create_date timestamptz NOT NULL DEFAULT now(),
    create_user_id varchar(50) NOT NULL,
    update_date timestamptz NOT NULL DEFAULT now(),
    update_user_id varchar(50) NOT NULL,
    CONSTRAINT pk_import_batch PRIMARY KEY (batch_id),
    CONSTRAINT uq_import_batch_file_sha256 UNIQUE (import_file_sha256),
    CONSTRAINT ck_import_batch_total_count CHECK (import_total_record_count IS NULL OR import_total_record_count >= 0),
    CONSTRAINT ck_import_batch_status CHECK (import_status IN ('STARTED','SUCCEEDED','FAILED','PARTIAL'))
);

COMMENT ON TABLE recipe.import_batch IS '선택 설계안: 수집 파일과 처리 회차 메타데이터';
COMMENT ON COLUMN recipe.import_batch.batch_id IS 'recipe.fn_get_biz_id(''import_batch'')로 batch당 한 번 발급하는 VARCHAR(20) ID; 행별 DEFAULT 없음';
COMMENT ON COLUMN recipe.import_batch.import_source_file_nm IS '수집 원본 파일명';
COMMENT ON COLUMN recipe.import_batch.import_source_nm IS '데이터 출처 식별자';
COMMENT ON COLUMN recipe.import_batch.import_file_sha256 IS '원본 파일 SHA-256 해시; 동일 파일 재실행 식별 후보';
COMMENT ON COLUMN recipe.import_batch.import_collected_at IS '파일 수집 일시';
COMMENT ON COLUMN recipe.import_batch.import_total_record_count IS '원본 레코드 수';
COMMENT ON COLUMN recipe.import_batch.import_status IS 'ETL 처리 상태';
COMMENT ON COLUMN recipe.import_batch.import_error_txt IS '요약 오류 정보; 비밀정보를 저장하지 않음';
COMMENT ON COLUMN recipe.import_batch.create_date IS '최초 생성 일시';
COMMENT ON COLUMN recipe.import_batch.create_user_id IS '최초 생성 사용자 식별자';
COMMENT ON COLUMN recipe.import_batch.update_date IS '최종 수정 일시; UPDATE 시 ETL이 명시적으로 갱신';
COMMENT ON COLUMN recipe.import_batch.update_user_id IS '최종 수정 사용자 식별자';
