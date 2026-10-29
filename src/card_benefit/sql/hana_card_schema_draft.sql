--=========================================================
-- 하나카드 상품설명서 PDF 정제·AI 추출·검증 테이블 DDL 초안 (db_pipeline 전용, 수동 실행 전용)
--   상태: 설계 검토용 초안. 대상 DB에 적용하지 않았다. 적용 전 공동 확인 필요(development_roles.md 5절).
--   설계 설명: hana_card_db_design.md
--
--   원칙
--   - 스키마: 카드 마스터(schema.sql의 card_product)와 이 파일의 수집·정제·검증 객체 모두 card_benefit을 쓴다.
--     적용 순서는 schema.sql → 이 파일(물리 FK가 없어 순서를 바꿔도 생성은 된다).
--     fn_get_biz_id는 card_benefit.seq_<테이블명>만 찾는다. card_product는 IDENTITY를 쓰므로 이 함수와 무관하다.
--   - card_benefit.card_product(schema.sql)는 이 파일에서 만들거나 변경하지 않는다. card_id(BIGINT)로 논리 참조만 한다.
--   - 명명·공통 컬럼·업무 ID·제약조건 이름은 recipe 스키마 덤프(sample_dump-postgres-202610292124.sql)의 패턴을 따른다.
--     · 업무 ID: VARCHAR(20) 'YYYYMMDD_000001' (fn_get_biz_id + seq_<테이블명>)
--     · 공통 컬럼: create_date / create_user_id / update_date / update_user_id
--     · 제약조건 이름: pk_<테이블>, uq_<테이블>_<컬럼>, ck_<테이블>_<컬럼>, ix_<테이블>_<키>
--     · 물리 FK 없음. 부모 존재·중복·복합 키 일치는 적재기와 검증 SQL(hana_card_db_design.md 8절)에서 확인한다.
--   - IF NOT EXISTS만 사용하므로 다시 실행해도 기존 데이터를 지우지 않는다(함수만 CREATE OR REPLACE).
--   - 원본 PDF 바이너리는 DB에 저장하지 않는다(재배포 조건 미확인). 출처 URL·파일 해시·추출 텍스트만 저장한다.
--=========================================================

CREATE SCHEMA IF NOT EXISTS card_benefit;

COMMENT ON SCHEMA card_benefit IS '카드 상품설명서 PDF 수집·정제·AI 추출·검증(db_pipeline). 카드 마스터는 card_benefit.card_product';


--=========================================================
-- 1. 업무 ID 발급 함수·시퀀스
--=========================================================

CREATE SEQUENCE IF NOT EXISTS card_benefit.seq_card_doc          START WITH 1 INCREMENT BY 1 MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE IF NOT EXISTS card_benefit.seq_card_doc_chunk    START WITH 1 INCREMENT BY 1 MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE IF NOT EXISTS card_benefit.seq_card_ai_run       START WITH 1 INCREMENT BY 1 MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE IF NOT EXISTS card_benefit.seq_card_extr_stg     START WITH 1 INCREMENT BY 1 MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE IF NOT EXISTS card_benefit.seq_card_excl_item    START WITH 1 INCREMENT BY 1 MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE IF NOT EXISTS card_benefit.seq_card_excl_item_als START WITH 1 INCREMENT BY 1 MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE IF NOT EXISTS card_benefit.seq_card_bnft         START WITH 1 INCREMENT BY 1 MAXVALUE 999999 CACHE 1 CYCLE;
CREATE SEQUENCE IF NOT EXISTS card_benefit.seq_card_cond         START WITH 1 INCREMENT BY 1 MAXVALUE 999999 CACHE 1 CYCLE;

COMMENT ON SEQUENCE card_benefit.seq_card_doc           IS '원본 문서 ID 발급';
COMMENT ON SEQUENCE card_benefit.seq_card_doc_chunk     IS '문서 청크 ID 발급';
COMMENT ON SEQUENCE card_benefit.seq_card_ai_run        IS 'AI 실행 ID 발급';
COMMENT ON SEQUENCE card_benefit.seq_card_extr_stg      IS 'AI 추출 staging ID 발급';
COMMENT ON SEQUENCE card_benefit.seq_card_excl_item     IS '표준 제외 항목 ID 발급';
COMMENT ON SEQUENCE card_benefit.seq_card_excl_item_als IS '제외 항목 별칭 ID 발급';
COMMENT ON SEQUENCE card_benefit.seq_card_bnft          IS '확정 혜택 ID 발급';
COMMENT ON SEQUENCE card_benefit.seq_card_cond          IS '확정 조건 ID 발급';


CREATE OR REPLACE FUNCTION card_benefit.fn_get_biz_id(p_tbl_nm text) RETURNS character varying
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog'
    AS $_$
DECLARE
    v_seq regclass;
BEGIN
    IF p_tbl_nm IS NULL OR p_tbl_nm !~ '^[A-Za-z][A-Za-z0-9_]*$' THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = format('Invalid card_benefit table name for business ID: %s', coalesce(p_tbl_nm, '<NULL>'));
    END IF;

    v_seq := to_regclass('card_benefit.seq_' || lower(p_tbl_nm));
    IF v_seq IS NULL OR NOT EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class AS c
        WHERE c.oid = v_seq
          AND c.relkind = 'S'
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '42P01',
            MESSAGE = format('card_benefit ID sequence does not exist: %s', 'card_benefit.seq_' || lower(p_tbl_nm));
    END IF;

    RETURN to_char((clock_timestamp() AT TIME ZONE 'Asia/Seoul')::date, 'YYYYMMDD')
        || '_' || lpad(nextval(v_seq)::text, 6, '0');
END;
$_$;

COMMENT ON FUNCTION card_benefit.fn_get_biz_id(p_tbl_nm text) IS 'card_benefit.seq_<테이블명> 시퀀스로 YYYYMMDD_000001 형식 업무 ID 발급(Asia/Seoul 기준)';


--=========================================================
-- 2. 원본 문서 계층: card_doc → card_doc_page → card_doc_chunk
--=========================================================

CREATE TABLE IF NOT EXISTS card_benefit.card_doc (
    doc_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_doc'::text) NOT NULL,
    card_id bigint NOT NULL,
    doc_cd character varying(50) NOT NULL,
    doc_type_cd character varying(20) DEFAULT 'PRODUCT_GUIDE'::character varying NOT NULL,
    doc_title text NOT NULL,
    doc_source_url text,
    doc_file_nm text NOT NULL,
    doc_file_size bigint,
    doc_sha256 character varying(64) NOT NULL,
    doc_page_cnt smallint,
    doc_review_no text,
    doc_review_date date,
    doc_release_date date,
    doc_collect_date timestamp with time zone NOT NULL,
    doc_version_no smallint DEFAULT 1 NOT NULL,
    doc_status character varying(20) DEFAULT 'ACTIVE'::character varying NOT NULL,
    doc_note text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT pk_card_doc PRIMARY KEY (doc_id),
    CONSTRAINT uq_card_doc_doc_cd UNIQUE (doc_cd),
    CONSTRAINT uq_card_doc_doc_sha256 UNIQUE (doc_sha256),
    CONSTRAINT uq_card_doc_version UNIQUE (card_id, doc_type_cd, doc_version_no),
    CONSTRAINT ck_card_doc_doc_type_cd CHECK (((doc_type_cd)::text = ANY ((ARRAY['PRODUCT_GUIDE'::character varying, 'TERMS'::character varying, 'ETC'::character varying])::text[]))),
    CONSTRAINT ck_card_doc_doc_sha256 CHECK (((doc_sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_card_doc_doc_page_cnt CHECK ((doc_page_cnt IS NULL) OR (doc_page_cnt > 0)),
    CONSTRAINT ck_card_doc_doc_version_no CHECK ((doc_version_no > 0)),
    CONSTRAINT ck_card_doc_doc_status CHECK (((doc_status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'SUPERSEDED'::character varying, 'EXCLUDED'::character varying])::text[])))
);

-- 카드·문서 유형별 현재 유효(ACTIVE) 문서는 하나만 허용한다.
CREATE UNIQUE INDEX IF NOT EXISTS uq_card_doc_active ON card_benefit.card_doc USING btree (card_id, doc_type_cd) WHERE ((doc_status)::text = 'ACTIVE'::text);

COMMENT ON TABLE card_benefit.card_doc IS '카드 상품설명서 원본 문서(문서 버전 단위)';
COMMENT ON COLUMN card_benefit.card_doc.doc_id IS '원본 문서 ID';
COMMENT ON COLUMN card_benefit.card_doc.card_id IS '카드 상품 ID(card_benefit.card_product.card_id 논리 참조)';
COMMENT ON COLUMN card_benefit.card_doc.doc_cd IS '파이프라인 공통 문서 코드(예: HANA_15650_20260429). 결과 A·B 비교 키 후보';
COMMENT ON COLUMN card_benefit.card_doc.doc_type_cd IS '문서 유형(PRODUCT_GUIDE: 상품설명서, TERMS: 약관, ETC)';
COMMENT ON COLUMN card_benefit.card_doc.doc_title IS '문서 제목';
COMMENT ON COLUMN card_benefit.card_doc.doc_source_url IS '공식 출처 URL';
COMMENT ON COLUMN card_benefit.card_doc.doc_file_nm IS '수집 파일명';
COMMENT ON COLUMN card_benefit.card_doc.doc_file_size IS '수집 파일 크기(바이트)';
COMMENT ON COLUMN card_benefit.card_doc.doc_sha256 IS '수집 파일 SHA-256(소문자 16진수 64자)';
COMMENT ON COLUMN card_benefit.card_doc.doc_page_cnt IS 'PDF 페이지 수';
COMMENT ON COLUMN card_benefit.card_doc.doc_review_no IS '준법심의·여신협회 심의필 번호 원문';
COMMENT ON COLUMN card_benefit.card_doc.doc_review_date IS '심의일';
COMMENT ON COLUMN card_benefit.card_doc.doc_release_date IS '상품 출시일';
COMMENT ON COLUMN card_benefit.card_doc.doc_collect_date IS '파일 수집(다운로드) 일시';
COMMENT ON COLUMN card_benefit.card_doc.doc_version_no IS '카드·문서 유형 내 문서 버전 번호(1부터)';
COMMENT ON COLUMN card_benefit.card_doc.doc_status IS '문서 상태(ACTIVE: 현재 유효, SUPERSEDED: 신규 버전으로 대체, EXCLUDED: 분석 제외)';
COMMENT ON COLUMN card_benefit.card_doc.doc_note IS '문서 범위·확인 사항 메모';
COMMENT ON COLUMN card_benefit.card_doc.create_date IS '생성 일시';
COMMENT ON COLUMN card_benefit.card_doc.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN card_benefit.card_doc.update_date IS '수정 일시';
COMMENT ON COLUMN card_benefit.card_doc.update_user_id IS '수정 사용자 ID';


CREATE TABLE IF NOT EXISTS card_benefit.card_doc_page (
    doc_id character varying(20) NOT NULL,
    page_no smallint NOT NULL,
    page_raw_txt text NOT NULL,
    page_char_cnt integer NOT NULL,
    page_txt_sha256 character varying(64) NOT NULL,
    page_layer_cd character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    page_extractor_nm character varying(50) NOT NULL,
    page_extractor_ver character varying(50),
    page_note text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT pk_card_doc_page PRIMARY KEY (doc_id, page_no),
    CONSTRAINT ck_card_doc_page_page_no CHECK ((page_no > 0)),
    CONSTRAINT ck_card_doc_page_page_char_cnt CHECK ((page_char_cnt >= 0)),
    CONSTRAINT ck_card_doc_page_page_layer_cd CHECK (((page_layer_cd)::text = ANY ((ARRAY['TEXT'::character varying, 'IMAGE'::character varying, 'MIXED'::character varying, 'UNKNOWN'::character varying])::text[])))
);

COMMENT ON TABLE card_benefit.card_doc_page IS '문서 페이지별 추출 원문(정제 전, 적재 후 변경 금지)';
COMMENT ON COLUMN card_benefit.card_doc_page.doc_id IS '원본 문서 ID';
COMMENT ON COLUMN card_benefit.card_doc_page.page_no IS 'PDF 페이지 번호(1부터)';
COMMENT ON COLUMN card_benefit.card_doc_page.page_raw_txt IS '추출기가 반환한 페이지 텍스트 원문(가공 없음)';
COMMENT ON COLUMN card_benefit.card_doc_page.page_char_cnt IS '페이지 원문 문자 수';
COMMENT ON COLUMN card_benefit.card_doc_page.page_txt_sha256 IS '페이지 원문 SHA-256(재추출 시 변경 감지)';
COMMENT ON COLUMN card_benefit.card_doc_page.page_layer_cd IS '텍스트 레이어 유형(TEXT, IMAGE, MIXED: 일부 표가 이미지, UNKNOWN)';
COMMENT ON COLUMN card_benefit.card_doc_page.page_extractor_nm IS '텍스트 추출기명(예: PyMuPDF)';
COMMENT ON COLUMN card_benefit.card_doc_page.page_extractor_ver IS '텍스트 추출기 버전';
COMMENT ON COLUMN card_benefit.card_doc_page.page_note IS '추출 한계·확인 메모(표 미탐지 등)';
COMMENT ON COLUMN card_benefit.card_doc_page.create_date IS '생성 일시';
COMMENT ON COLUMN card_benefit.card_doc_page.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN card_benefit.card_doc_page.update_date IS '수정 일시';
COMMENT ON COLUMN card_benefit.card_doc_page.update_user_id IS '수정 사용자 ID';


CREATE TABLE IF NOT EXISTS card_benefit.card_doc_chunk (
    chunk_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_doc_chunk'::text) NOT NULL,
    doc_id character varying(20) NOT NULL,
    page_no smallint NOT NULL,
    chunk_seq integer NOT NULL,
    chunk_section_nm text,
    chunk_type_cd character varying(20) DEFAULT 'BODY'::character varying NOT NULL,
    chunk_start_pos integer NOT NULL,
    chunk_end_pos integer NOT NULL,
    chunk_raw_txt text NOT NULL,
    chunk_clean_txt text,
    chunk_status character varying(20) DEFAULT 'RAW'::character varying NOT NULL,
    chunk_split_rule_ver character varying(50) NOT NULL,
    chunk_clean_rule_ver character varying(50),
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT pk_card_doc_chunk PRIMARY KEY (chunk_id),
    CONSTRAINT uq_card_doc_chunk_seq UNIQUE (doc_id, chunk_seq),
    CONSTRAINT ck_card_doc_chunk_chunk_seq CHECK ((chunk_seq > 0)),
    CONSTRAINT ck_card_doc_chunk_pos CHECK (((chunk_start_pos >= 1) AND (chunk_end_pos >= chunk_start_pos))),
    CONSTRAINT ck_card_doc_chunk_chunk_type_cd CHECK (((chunk_type_cd)::text = ANY ((ARRAY['BODY'::character varying, 'TABLE'::character varying, 'NOTICE'::character varying, 'HEADER_FOOTER'::character varying, 'ETC'::character varying])::text[]))),
    CONSTRAINT ck_card_doc_chunk_chunk_status CHECK (((chunk_status)::text = ANY ((ARRAY['RAW'::character varying, 'CLEANED'::character varying, 'EXCLUDED'::character varying])::text[]))),
    CONSTRAINT ck_card_doc_chunk_cleaned CHECK ((((chunk_status)::text <> 'CLEANED'::text) OR ((chunk_clean_txt IS NOT NULL) AND (chunk_clean_rule_ver IS NOT NULL))))
);

CREATE INDEX IF NOT EXISTS ix_card_doc_chunk_page_key ON card_benefit.card_doc_chunk USING btree (doc_id, page_no);

COMMENT ON TABLE card_benefit.card_doc_chunk IS '문서 청크(조항·표·안내 단위) 원문과 SQL 정제 결과';
COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_id IS '청크 ID';
COMMENT ON COLUMN card_benefit.card_doc_chunk.doc_id IS '원본 문서 ID';
COMMENT ON COLUMN card_benefit.card_doc_chunk.page_no IS '청크가 속한 페이지 번호(청크는 페이지를 넘지 않음)';
COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_seq IS '문서 내 청크 순번(1부터)';
COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_section_nm IS '원문 절 제목(예: [실적 산정 기준], 서비스 제외 대상)';
COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_type_cd IS '청크 유형(BODY, TABLE, NOTICE: 유의사항, HEADER_FOOTER: 머리말·꼬리말, ETC)';
COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_start_pos IS 'page_raw_txt 내 시작 문자 위치(1부터, PostgreSQL substr 기준)';
COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_end_pos IS 'page_raw_txt 내 끝 문자 위치(포함)';
COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_raw_txt IS '청크 원문(정제 전, page_raw_txt의 부분 문자열)';
COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_clean_txt IS 'SQL 정제 후 텍스트(AI 입력)';
COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_status IS '청크 상태(RAW: 분리만 됨, CLEANED: 정제 완료, EXCLUDED: 추출 대상 제외)';
COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_split_rule_ver IS '청크 분리 규칙 버전';
COMMENT ON COLUMN card_benefit.card_doc_chunk.chunk_clean_rule_ver IS 'SQL 정제 규칙 버전';
COMMENT ON COLUMN card_benefit.card_doc_chunk.create_date IS '생성 일시';
COMMENT ON COLUMN card_benefit.card_doc_chunk.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN card_benefit.card_doc_chunk.update_date IS '수정 일시';
COMMENT ON COLUMN card_benefit.card_doc_chunk.update_user_id IS '수정 사용자 ID';


--=========================================================
-- 3. AI 실행 이력: card_ai_run → card_ai_call
--=========================================================

CREATE TABLE IF NOT EXISTS card_benefit.card_ai_run (
    run_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_ai_run'::text) NOT NULL,
    run_stage_cd character varying(20) NOT NULL,
    run_call_mthd_cd character varying(20) NOT NULL,
    run_model_nm character varying(100) NOT NULL,
    run_prompt_ver character varying(50) NOT NULL,
    run_prompt_txt text NOT NULL,
    run_param jsonb,
    run_target_doc_id character varying(20),
    run_status character varying(20) DEFAULT 'RUNNING'::character varying NOT NULL,
    run_start_date timestamp with time zone DEFAULT now() NOT NULL,
    run_end_date timestamp with time zone,
    run_note text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT pk_card_ai_run PRIMARY KEY (run_id),
    CONSTRAINT ck_card_ai_run_run_stage_cd CHECK (((run_stage_cd)::text = ANY ((ARRAY['EXTRACT'::character varying, 'VERIFY'::character varying])::text[]))),
    CONSTRAINT ck_card_ai_run_run_call_mthd_cd CHECK (((run_call_mthd_cd)::text = ANY ((ARRAY['PYTHON_RELAY'::character varying, 'PGAI'::character varying, 'EDGE_FUNCTION'::character varying, 'ETC'::character varying])::text[]))),
    CONSTRAINT ck_card_ai_run_run_status CHECK (((run_status)::text = ANY ((ARRAY['RUNNING'::character varying, 'SUCCEEDED'::character varying, 'PARTIAL'::character varying, 'FAILED'::character varying])::text[]))),
    CONSTRAINT ck_card_ai_run_run_end_date CHECK (((run_end_date IS NULL) OR (run_end_date >= run_start_date)))
);

CREATE INDEX IF NOT EXISTS ix_card_ai_run_doc_key ON card_benefit.card_ai_run USING btree (run_target_doc_id);

COMMENT ON TABLE card_benefit.card_ai_run IS 'AI 추출·검증 실행 이력(실행 회차 단위)';
COMMENT ON COLUMN card_benefit.card_ai_run.run_id IS 'AI 실행 ID';
COMMENT ON COLUMN card_benefit.card_ai_run.run_stage_cd IS '실행 단계(EXTRACT: 혜택·조건 추출, VERIFY: 추출 결과 의미 검증)';
COMMENT ON COLUMN card_benefit.card_ai_run.run_call_mthd_cd IS 'AI 호출 방식(PYTHON_RELAY, PGAI, EDGE_FUNCTION, ETC). 기술 검증 후 확정';
COMMENT ON COLUMN card_benefit.card_ai_run.run_model_nm IS '사용 모델명';
COMMENT ON COLUMN card_benefit.card_ai_run.run_prompt_ver IS '프롬프트 버전';
COMMENT ON COLUMN card_benefit.card_ai_run.run_prompt_txt IS '실행에 사용한 프롬프트 템플릿 원문';
COMMENT ON COLUMN card_benefit.card_ai_run.run_param IS '모델 호출 파라미터(temperature, 출력 스키마 등)';
COMMENT ON COLUMN card_benefit.card_ai_run.run_target_doc_id IS '대상 원본 문서 ID(여러 문서 실행이면 NULL)';
COMMENT ON COLUMN card_benefit.card_ai_run.run_status IS '실행 상태(RUNNING, SUCCEEDED, PARTIAL: 일부 호출 실패, FAILED)';
COMMENT ON COLUMN card_benefit.card_ai_run.run_start_date IS '실행 시작 일시';
COMMENT ON COLUMN card_benefit.card_ai_run.run_end_date IS '실행 종료 일시';
COMMENT ON COLUMN card_benefit.card_ai_run.run_note IS '실행 메모';
COMMENT ON COLUMN card_benefit.card_ai_run.create_date IS '생성 일시';
COMMENT ON COLUMN card_benefit.card_ai_run.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN card_benefit.card_ai_run.update_date IS '수정 일시';
COMMENT ON COLUMN card_benefit.card_ai_run.update_user_id IS '수정 사용자 ID';


CREATE TABLE IF NOT EXISTS card_benefit.card_ai_call (
    run_id character varying(20) NOT NULL,
    chunk_id character varying(20) NOT NULL,
    call_seq smallint DEFAULT 1 NOT NULL,
    call_input_sha256 character varying(64) NOT NULL,
    call_status character varying(20) NOT NULL,
    call_resp_raw text,
    call_resp_json jsonb,
    call_error_msg text,
    call_input_token_cnt integer,
    call_output_token_cnt integer,
    call_latency_ms integer,
    call_req_date timestamp with time zone DEFAULT now() NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT pk_card_ai_call PRIMARY KEY (run_id, chunk_id, call_seq),
    CONSTRAINT ck_card_ai_call_call_seq CHECK ((call_seq > 0)),
    CONSTRAINT ck_card_ai_call_call_status CHECK (((call_status)::text = ANY ((ARRAY['SUCCEEDED'::character varying, 'FAILED'::character varying, 'PARSE_ERROR'::character varying])::text[]))),
    CONSTRAINT ck_card_ai_call_succeeded CHECK ((((call_status)::text <> 'SUCCEEDED'::text) OR (call_resp_json IS NOT NULL)))
);

CREATE INDEX IF NOT EXISTS ix_card_ai_call_chunk_key ON card_benefit.card_ai_call USING btree (chunk_id);

COMMENT ON TABLE card_benefit.card_ai_call IS 'AI 실행 내 청크별 호출 원 응답(정제 전 AI 출력)';
COMMENT ON COLUMN card_benefit.card_ai_call.run_id IS 'AI 실행 ID';
COMMENT ON COLUMN card_benefit.card_ai_call.chunk_id IS '입력 청크 ID';
COMMENT ON COLUMN card_benefit.card_ai_call.call_seq IS '같은 실행·청크 내 호출 순번(재시도 시 증가)';
COMMENT ON COLUMN card_benefit.card_ai_call.call_input_sha256 IS '실제 입력(프롬프트+청크) SHA-256';
COMMENT ON COLUMN card_benefit.card_ai_call.call_status IS '호출 상태(SUCCEEDED, FAILED: 호출 실패, PARSE_ERROR: JSON 파싱 실패)';
COMMENT ON COLUMN card_benefit.card_ai_call.call_resp_raw IS '모델 응답 원문';
COMMENT ON COLUMN card_benefit.card_ai_call.call_resp_json IS '파싱한 응답 JSON';
COMMENT ON COLUMN card_benefit.card_ai_call.call_error_msg IS '오류 메시지';
COMMENT ON COLUMN card_benefit.card_ai_call.call_input_token_cnt IS '입력 토큰 수';
COMMENT ON COLUMN card_benefit.card_ai_call.call_output_token_cnt IS '출력 토큰 수';
COMMENT ON COLUMN card_benefit.card_ai_call.call_latency_ms IS '응답 시간(밀리초)';
COMMENT ON COLUMN card_benefit.card_ai_call.call_req_date IS '요청 일시';
COMMENT ON COLUMN card_benefit.card_ai_call.create_date IS '생성 일시';
COMMENT ON COLUMN card_benefit.card_ai_call.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN card_benefit.card_ai_call.update_date IS '수정 일시';
COMMENT ON COLUMN card_benefit.card_ai_call.update_user_id IS '수정 사용자 ID';


--=========================================================
-- 4. 표준 제외 항목(정규화 사전): card_excl_item → card_excl_item_als
--=========================================================

CREATE TABLE IF NOT EXISTS card_benefit.card_excl_item (
    excl_item_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_excl_item'::text) NOT NULL,
    issuer text NOT NULL,
    excl_item_nm text NOT NULL,
    excl_concept_cd character varying(50),
    excl_item_desc text,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT pk_card_excl_item PRIMARY KEY (excl_item_id),
    CONSTRAINT uq_card_excl_item_excl_item_nm UNIQUE (issuer, excl_item_nm)
);

CREATE INDEX IF NOT EXISTS ix_card_excl_item_concept_key ON card_benefit.card_excl_item USING btree (excl_concept_cd);

COMMENT ON TABLE card_benefit.card_excl_item IS '표준 제외 항목(카드사 범위 개념, 정책 아님)';
COMMENT ON COLUMN card_benefit.card_excl_item.excl_item_id IS '표준 제외 항목 ID';
COMMENT ON COLUMN card_benefit.card_excl_item.issuer IS '카드사(card_product.issuer와 같은 표기). 병합은 같은 카드사 안에서만';
COMMENT ON COLUMN card_benefit.card_excl_item.excl_item_nm IS '표준 제외 항목명(예: 상품권·기프트카드 구매)';
COMMENT ON COLUMN card_benefit.card_excl_item.excl_concept_cd IS '카드사 공통 분류 개념 코드(예: GIFT_CERT_PURCHASE). 분류용이며 정책 동일을 뜻하지 않음';
COMMENT ON COLUMN card_benefit.card_excl_item.excl_item_desc IS '항목 설명·포함 범위';
COMMENT ON COLUMN card_benefit.card_excl_item.create_date IS '생성 일시';
COMMENT ON COLUMN card_benefit.card_excl_item.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN card_benefit.card_excl_item.update_date IS '수정 일시';
COMMENT ON COLUMN card_benefit.card_excl_item.update_user_id IS '수정 사용자 ID';


CREATE TABLE IF NOT EXISTS card_benefit.card_excl_item_als (
    excl_item_id character varying(20) NOT NULL,
    excl_item_als_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_excl_item_als'::text) NOT NULL,
    excl_item_als_nm text NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT pk_card_excl_item_als PRIMARY KEY (excl_item_id, excl_item_als_id),
    CONSTRAINT uq_card_excl_item_als_excl_item_als_nm UNIQUE (excl_item_id, excl_item_als_nm)
);

COMMENT ON TABLE card_benefit.card_excl_item_als IS '제외 항목 원문 표기 별칭(SQL 정규화 사전)';
COMMENT ON COLUMN card_benefit.card_excl_item_als.excl_item_id IS '표준 제외 항목 ID';
COMMENT ON COLUMN card_benefit.card_excl_item_als.excl_item_als_id IS '제외 항목 별칭 ID';
COMMENT ON COLUMN card_benefit.card_excl_item_als.excl_item_als_nm IS '원문 표기(공백 제거 비교 기준). 의미가 불확실한 표기(예: 상품/)는 등록하지 않음';
COMMENT ON COLUMN card_benefit.card_excl_item_als.create_date IS '생성 일시';
COMMENT ON COLUMN card_benefit.card_excl_item_als.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN card_benefit.card_excl_item_als.update_date IS '수정 일시';
COMMENT ON COLUMN card_benefit.card_excl_item_als.update_user_id IS '수정 사용자 ID';


--=========================================================
-- 5. AI 추출 staging(정제 전 원 항목 + 정제 후 컬럼 + 검증 상태)
--=========================================================

CREATE TABLE IF NOT EXISTS card_benefit.card_extr_stg (
    stg_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_extr_stg'::text) NOT NULL,
    run_id character varying(20) NOT NULL,
    chunk_id character varying(20) NOT NULL,
    call_seq smallint NOT NULL,
    stg_item_seq smallint NOT NULL,
    card_id bigint NOT NULL,
    stg_kind_cd character varying(20) NOT NULL,
    stg_parent_stg_id character varying(20),
    stg_raw_item jsonb NOT NULL,
    stg_bnft_nm text,
    stg_bnft_grp_nm text,
    stg_bnft_type_cd character varying(20),
    stg_cond_type_cd character varying(20),
    stg_apply_lvl_cd character varying(20),
    stg_excl_raw_txt text,
    excl_item_id character varying(20),
    stg_basis_cd character varying(20),
    stg_min_amt numeric(12,0),
    stg_max_amt numeric(12,0),
    stg_rate numeric(6,3),
    stg_amt numeric(12,0),
    stg_limit_amt numeric(12,0),
    stg_limit_cnt integer,
    stg_period_cd character varying(20),
    stg_modality_cd character varying(20),
    stg_value_txt text,
    stg_target_txt text,
    stg_evidence_txt text NOT NULL,
    stg_evidence_start_pos integer,
    stg_evidence_end_pos integer,
    stg_sql_check_cd character varying(30),
    stg_ai_vrfy_cd character varying(20),
    stg_ai_vrfy_run_id character varying(20),
    stg_status character varying(20) DEFAULT 'PENDING_REVIEW'::character varying NOT NULL,
    stg_review_note text,
    stg_approved_date timestamp with time zone,
    stg_approved_user_id character varying(50),
    bnft_id character varying(20),
    cond_id character varying(20),
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT pk_card_extr_stg PRIMARY KEY (stg_id),
    CONSTRAINT uq_card_extr_stg_item_seq UNIQUE (run_id, chunk_id, call_seq, stg_item_seq),
    CONSTRAINT ck_card_extr_stg_stg_item_seq CHECK ((stg_item_seq > 0)),
    CONSTRAINT ck_card_extr_stg_stg_kind_cd CHECK (((stg_kind_cd)::text = ANY ((ARRAY['BENEFIT'::character varying, 'CONDITION'::character varying])::text[]))),
    CONSTRAINT ck_card_extr_stg_kind_required CHECK (((((stg_kind_cd)::text = 'BENEFIT'::text) AND (stg_bnft_nm IS NOT NULL)) OR (((stg_kind_cd)::text = 'CONDITION'::text) AND (stg_cond_type_cd IS NOT NULL)))),
    CONSTRAINT ck_card_extr_stg_stg_bnft_type_cd CHECK (((stg_bnft_type_cd IS NULL) OR ((stg_bnft_type_cd)::text = ANY ((ARRAY['DISCOUNT'::character varying, 'CASHBACK'::character varying, 'POINT'::character varying, 'FEE_WAIVER'::character varying, 'SERVICE'::character varying, 'INSTALLMENT'::character varying, 'ETC'::character varying])::text[])))),
    CONSTRAINT ck_card_extr_stg_stg_cond_type_cd CHECK (((stg_cond_type_cd IS NULL) OR ((stg_cond_type_cd)::text = ANY ((ARRAY['SPEND_REQ'::character varying, 'SPEND_EXCL'::character varying, 'BNFT_EXCL'::character varying, 'LIMIT'::character varying, 'TIER'::character varying, 'USAGE_REQ'::character varying, 'GRACE'::character varying, 'MERCHANT_RULE'::character varying, 'ETC'::character varying])::text[])))),
    CONSTRAINT ck_card_extr_stg_stg_apply_lvl_cd CHECK (((stg_apply_lvl_cd IS NULL) OR ((stg_apply_lvl_cd)::text = ANY ((ARRAY['CARD'::character varying, 'BENEFIT'::character varying])::text[])))),
    CONSTRAINT ck_card_extr_stg_stg_basis_cd CHECK (((stg_basis_cd IS NULL) OR ((stg_basis_cd)::text = ANY ((ARRAY['PREV_MONTH_SPEND'::character varying, 'TXN_AMT'::character varying, 'MONTH_USAGE'::character varying, 'NONE'::character varying])::text[])))),
    CONSTRAINT ck_card_extr_stg_stg_period_cd CHECK (((stg_period_cd IS NULL) OR ((stg_period_cd)::text = ANY ((ARRAY['TXN'::character varying, 'DAY'::character varying, 'MONTH'::character varying, 'YEAR'::character varying, 'NONE'::character varying])::text[])))),
    CONSTRAINT ck_card_extr_stg_stg_modality_cd CHECK (((stg_modality_cd IS NULL) OR ((stg_modality_cd)::text = ANY ((ARRAY['CONFIRMED'::character varying, 'POSSIBLE'::character varying])::text[])))),
    CONSTRAINT ck_card_extr_stg_amt_range CHECK (((stg_min_amt IS NULL) OR (stg_max_amt IS NULL) OR (stg_min_amt <= stg_max_amt))),
    CONSTRAINT ck_card_extr_stg_evidence_pos CHECK (((stg_evidence_start_pos IS NULL) OR ((stg_evidence_start_pos >= 1) AND (stg_evidence_end_pos >= stg_evidence_start_pos)))),
    CONSTRAINT ck_card_extr_stg_stg_ai_vrfy_cd CHECK (((stg_ai_vrfy_cd IS NULL) OR ((stg_ai_vrfy_cd)::text = ANY ((ARRAY['MATCH'::character varying, 'MISMATCH'::character varying, 'UNCERTAIN'::character varying])::text[])))),
    CONSTRAINT ck_card_extr_stg_stg_status CHECK (((stg_status)::text = ANY ((ARRAY['PENDING_REVIEW'::character varying, 'AUTO_APPROVED'::character varying, 'MANUAL_APPROVED'::character varying, 'REJECTED'::character varying])::text[]))),
    CONSTRAINT ck_card_extr_stg_approval CHECK ((((stg_status)::text <> ALL ((ARRAY['AUTO_APPROVED'::character varying, 'MANUAL_APPROVED'::character varying])::text[])) OR (((stg_sql_check_cd)::text = 'OK'::text) AND (stg_evidence_start_pos IS NOT NULL) AND (((stg_cond_type_cd)::text <> ALL ((ARRAY['SPEND_EXCL'::character varying, 'BNFT_EXCL'::character varying])::text[])) OR (stg_cond_type_cd IS NULL) OR (excl_item_id IS NOT NULL)))))
);

CREATE INDEX IF NOT EXISTS ix_card_extr_stg_chunk_key ON card_benefit.card_extr_stg USING btree (chunk_id);
CREATE INDEX IF NOT EXISTS ix_card_extr_stg_status_key ON card_benefit.card_extr_stg USING btree (stg_status, stg_kind_cd);
CREATE INDEX IF NOT EXISTS ix_card_extr_stg_excl_item_key ON card_benefit.card_extr_stg USING btree (excl_item_id);

COMMENT ON TABLE card_benefit.card_extr_stg IS 'AI 추출 혜택·조건 staging(정제 전 원 항목, 정제 후 값, 검증·승인 상태)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_id IS '추출 staging ID';
COMMENT ON COLUMN card_benefit.card_extr_stg.run_id IS 'AI 추출 실행 ID';
COMMENT ON COLUMN card_benefit.card_extr_stg.chunk_id IS '근거 청크 ID';
COMMENT ON COLUMN card_benefit.card_extr_stg.call_seq IS '응답을 만든 호출 순번(card_ai_call)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_item_seq IS '응답 내 항목 순번(1부터)';
COMMENT ON COLUMN card_benefit.card_extr_stg.card_id IS '대상 카드 상품 ID(문서의 card_id)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_kind_cd IS '항목 종류(BENEFIT: 혜택, CONDITION: 조건)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_parent_stg_id IS '조건이 걸린 혜택의 staging ID(카드 전체 조건이면 NULL)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_raw_item IS 'AI 응답의 항목 원본 JSON(정제 전)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_bnft_nm IS '혜택명';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_bnft_grp_nm IS '혜택 서비스 영역명(예: ONE PICK)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_bnft_type_cd IS '혜택 유형(DISCOUNT, CASHBACK, POINT, FEE_WAIVER, SERVICE, INSTALLMENT, ETC)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_cond_type_cd IS '조건 유형(SPEND_REQ: 전월실적 요건, SPEND_EXCL: 실적 산정 제외, BNFT_EXCL: 혜택 적용 제외, LIMIT, TIER, USAGE_REQ, GRACE, MERCHANT_RULE, ETC)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_apply_lvl_cd IS '적용 수준(CARD: 카드 전체, BENEFIT: 특정 혜택)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_excl_raw_txt IS '제외 항목 원문 표기';
COMMENT ON COLUMN card_benefit.card_extr_stg.excl_item_id IS '매핑된 표준 제외 항목 ID(미매핑 NULL)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_basis_cd IS '금액 기준(PREV_MONTH_SPEND: 전월실적, TXN_AMT: 건당 이용금액, MONTH_USAGE: 당월 이용, NONE)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_min_amt IS '구간 하한 금액(원, 이상)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_max_amt IS '구간 상한 금액(원, 미만)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_rate IS '할인·적립률(%)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_amt IS '정액 혜택 금액(원)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_limit_amt IS '한도 금액(원)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_limit_cnt IS '한도 횟수';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_period_cd IS '한도 기간(TXN, DAY, MONTH, YEAR, NONE)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_modality_cd IS '적용 확정성(CONFIRMED: 제외/적용, POSSIBLE: 제외될 수 있음)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_value_txt IS '금액·비율·횟수 원문 표기';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_target_txt IS '대상 가맹점·업종 원문 표기';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_evidence_txt IS 'AI가 제시한 근거 원문 문장';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_evidence_start_pos IS '근거의 chunk_raw_txt 내 시작 위치(SQL 대조 성공 시 채움)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_evidence_end_pos IS '근거의 chunk_raw_txt 내 끝 위치';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_sql_check_cd IS 'SQL 검증 결과(NULL: 미검사, OK, EVIDENCE_NOT_FOUND, SCHEMA_VIOLATION, DUPLICATE, ORPHAN_REF, UNMAPPED_ITEM, VALUE_PARSE_ERROR)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_ai_vrfy_cd IS 'AI 의미 검증 결과(NULL: 미실행, MATCH, MISMATCH, UNCERTAIN)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_ai_vrfy_run_id IS 'AI 의미 검증 실행 ID';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_status IS '검토 상태(PENDING_REVIEW, AUTO_APPROVED, MANUAL_APPROVED, REJECTED)';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_review_note IS '검증 결과 및 검토 메모';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_approved_date IS '승인 일시';
COMMENT ON COLUMN card_benefit.card_extr_stg.stg_approved_user_id IS '승인 사용자 ID';
COMMENT ON COLUMN card_benefit.card_extr_stg.bnft_id IS '확정 반영된 혜택 ID';
COMMENT ON COLUMN card_benefit.card_extr_stg.cond_id IS '확정 반영된 조건 ID';
COMMENT ON COLUMN card_benefit.card_extr_stg.create_date IS '생성 일시';
COMMENT ON COLUMN card_benefit.card_extr_stg.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN card_benefit.card_extr_stg.update_date IS '수정 일시';
COMMENT ON COLUMN card_benefit.card_extr_stg.update_user_id IS '수정 사용자 ID';


--=========================================================
-- 6. 검증 완료(확정) 데이터: card_bnft → card_cond  (db_pipeline 결과 B)
--=========================================================

CREATE TABLE IF NOT EXISTS card_benefit.card_bnft (
    bnft_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_bnft'::text) NOT NULL,
    card_id bigint NOT NULL,
    doc_id character varying(20) NOT NULL,
    bnft_nm text NOT NULL,
    bnft_grp_nm text,
    bnft_type_cd character varying(20) NOT NULL,
    bnft_target_txt text,
    bnft_rate numeric(6,3),
    bnft_amt numeric(12,0),
    bnft_value_txt text,
    chunk_id character varying(20) NOT NULL,
    bnft_evidence_txt text NOT NULL,
    bnft_evidence_start_pos integer NOT NULL,
    bnft_evidence_end_pos integer NOT NULL,
    stg_id character varying(20) NOT NULL,
    bnft_status character varying(20) DEFAULT 'CONFIRMED'::character varying NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT pk_card_bnft PRIMARY KEY (bnft_id),
    CONSTRAINT uq_card_bnft_bnft_nm UNIQUE (doc_id, bnft_nm),
    CONSTRAINT uq_card_bnft_stg_id UNIQUE (stg_id),
    CONSTRAINT ck_card_bnft_bnft_type_cd CHECK (((bnft_type_cd)::text = ANY ((ARRAY['DISCOUNT'::character varying, 'CASHBACK'::character varying, 'POINT'::character varying, 'FEE_WAIVER'::character varying, 'SERVICE'::character varying, 'INSTALLMENT'::character varying, 'ETC'::character varying])::text[]))),
    CONSTRAINT ck_card_bnft_evidence_pos CHECK (((bnft_evidence_start_pos >= 1) AND (bnft_evidence_end_pos >= bnft_evidence_start_pos))),
    CONSTRAINT ck_card_bnft_bnft_status CHECK (((bnft_status)::text = ANY ((ARRAY['CONFIRMED'::character varying, 'RETIRED'::character varying])::text[])))
);

CREATE INDEX IF NOT EXISTS ix_card_bnft_card_key ON card_benefit.card_bnft USING btree (card_id, doc_id);

COMMENT ON TABLE card_benefit.card_bnft IS '검증 완료 혜택(db_pipeline 결과 B, 문서 버전별)';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_id IS '혜택 ID(Neo4j Benefit 노드 키)';
COMMENT ON COLUMN card_benefit.card_bnft.card_id IS '카드 상품 ID(card_doc.card_id와 일치해야 함)';
COMMENT ON COLUMN card_benefit.card_bnft.doc_id IS '근거 원본 문서 ID';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_nm IS '혜택명';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_grp_nm IS '혜택 서비스 영역명(예: ONE PICK, ONE MORE)';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_type_cd IS '혜택 유형(DISCOUNT, CASHBACK, POINT, FEE_WAIVER, SERVICE, INSTALLMENT, ETC)';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_target_txt IS '대상 가맹점·업종 원문 표기';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_rate IS '대표 할인·적립률(%). 구간별 값은 card_cond TIER';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_amt IS '대표 정액 혜택 금액(원)';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_value_txt IS '혜택 값 원문 표기';
COMMENT ON COLUMN card_benefit.card_bnft.chunk_id IS '근거 청크 ID';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_evidence_txt IS '근거 원문 문장';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_evidence_start_pos IS '근거의 chunk_raw_txt 내 시작 위치';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_evidence_end_pos IS '근거의 chunk_raw_txt 내 끝 위치';
COMMENT ON COLUMN card_benefit.card_bnft.stg_id IS '확정 근거 staging ID';
COMMENT ON COLUMN card_benefit.card_bnft.bnft_status IS '상태(CONFIRMED, RETIRED: 신규 문서 버전으로 대체)';
COMMENT ON COLUMN card_benefit.card_bnft.create_date IS '생성 일시';
COMMENT ON COLUMN card_benefit.card_bnft.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN card_benefit.card_bnft.update_date IS '수정 일시';
COMMENT ON COLUMN card_benefit.card_bnft.update_user_id IS '수정 사용자 ID';


CREATE TABLE IF NOT EXISTS card_benefit.card_cond (
    cond_id character varying(20) DEFAULT card_benefit.fn_get_biz_id('card_cond'::text) NOT NULL,
    card_id bigint NOT NULL,
    doc_id character varying(20) NOT NULL,
    bnft_id character varying(20),
    cond_apply_lvl_cd character varying(20) NOT NULL,
    cond_type_cd character varying(20) NOT NULL,
    excl_item_id character varying(20),
    cond_excl_raw_txt text,
    cond_basis_cd character varying(20) DEFAULT 'NONE'::character varying NOT NULL,
    cond_min_amt numeric(12,0),
    cond_max_amt numeric(12,0),
    cond_rate numeric(6,3),
    cond_amt numeric(12,0),
    cond_limit_amt numeric(12,0),
    cond_limit_cnt integer,
    cond_period_cd character varying(20) DEFAULT 'NONE'::character varying NOT NULL,
    cond_modality_cd character varying(20) DEFAULT 'CONFIRMED'::character varying NOT NULL,
    cond_value_txt text,
    cond_target_txt text,
    cond_natural_key character varying(64) NOT NULL,
    cond_policy_cand_key character varying(64),
    chunk_id character varying(20) NOT NULL,
    cond_evidence_txt text NOT NULL,
    cond_evidence_start_pos integer NOT NULL,
    cond_evidence_end_pos integer NOT NULL,
    stg_id character varying(20) NOT NULL,
    cond_status character varying(20) DEFAULT 'CONFIRMED'::character varying NOT NULL,
    create_date timestamp with time zone DEFAULT now() NOT NULL,
    create_user_id character varying(50) NOT NULL,
    update_date timestamp with time zone DEFAULT now() NOT NULL,
    update_user_id character varying(50) NOT NULL,
    CONSTRAINT pk_card_cond PRIMARY KEY (cond_id),
    CONSTRAINT uq_card_cond_natural_key UNIQUE (doc_id, cond_natural_key),
    CONSTRAINT uq_card_cond_stg_id UNIQUE (stg_id),
    CONSTRAINT ck_card_cond_apply_lvl CHECK (((((cond_apply_lvl_cd)::text = 'CARD'::text) AND (bnft_id IS NULL)) OR (((cond_apply_lvl_cd)::text = 'BENEFIT'::text) AND (bnft_id IS NOT NULL)))),
    CONSTRAINT ck_card_cond_cond_type_cd CHECK (((cond_type_cd)::text = ANY ((ARRAY['SPEND_REQ'::character varying, 'SPEND_EXCL'::character varying, 'BNFT_EXCL'::character varying, 'LIMIT'::character varying, 'TIER'::character varying, 'USAGE_REQ'::character varying, 'GRACE'::character varying, 'MERCHANT_RULE'::character varying, 'ETC'::character varying])::text[]))),
    CONSTRAINT ck_card_cond_excl_item CHECK ((((cond_type_cd)::text <> ALL ((ARRAY['SPEND_EXCL'::character varying, 'BNFT_EXCL'::character varying])::text[])) OR ((excl_item_id IS NOT NULL) AND (cond_excl_raw_txt IS NOT NULL)))),
    CONSTRAINT ck_card_cond_cond_basis_cd CHECK (((cond_basis_cd)::text = ANY ((ARRAY['PREV_MONTH_SPEND'::character varying, 'TXN_AMT'::character varying, 'MONTH_USAGE'::character varying, 'NONE'::character varying])::text[]))),
    CONSTRAINT ck_card_cond_cond_period_cd CHECK (((cond_period_cd)::text = ANY ((ARRAY['TXN'::character varying, 'DAY'::character varying, 'MONTH'::character varying, 'YEAR'::character varying, 'NONE'::character varying])::text[]))),
    CONSTRAINT ck_card_cond_cond_modality_cd CHECK (((cond_modality_cd)::text = ANY ((ARRAY['CONFIRMED'::character varying, 'POSSIBLE'::character varying])::text[]))),
    CONSTRAINT ck_card_cond_amt_range CHECK (((cond_min_amt IS NULL) OR (cond_max_amt IS NULL) OR (cond_min_amt <= cond_max_amt))),
    CONSTRAINT ck_card_cond_evidence_pos CHECK (((cond_evidence_start_pos >= 1) AND (cond_evidence_end_pos >= cond_evidence_start_pos))),
    CONSTRAINT ck_card_cond_cond_status CHECK (((cond_status)::text = ANY ((ARRAY['CONFIRMED'::character varying, 'RETIRED'::character varying])::text[])))
);

CREATE INDEX IF NOT EXISTS ix_card_cond_card_key ON card_benefit.card_cond USING btree (card_id, cond_type_cd);
CREATE INDEX IF NOT EXISTS ix_card_cond_bnft_key ON card_benefit.card_cond USING btree (bnft_id);
CREATE INDEX IF NOT EXISTS ix_card_cond_excl_item_key ON card_benefit.card_cond USING btree (excl_item_id, cond_type_cd);
CREATE INDEX IF NOT EXISTS ix_card_cond_policy_key ON card_benefit.card_cond USING btree (cond_policy_cand_key);

COMMENT ON TABLE card_benefit.card_cond IS '검증 완료 조건(전월실적·실적 제외·혜택 제외·한도·구간·예외; 카드·혜택별 정책 인스턴스)';
COMMENT ON COLUMN card_benefit.card_cond.cond_id IS '조건 ID(Neo4j Condition 노드·EXCLUDES 관계 키)';
COMMENT ON COLUMN card_benefit.card_cond.card_id IS '카드 상품 ID(card_doc.card_id와 일치해야 함)';
COMMENT ON COLUMN card_benefit.card_cond.doc_id IS '근거 원본 문서 ID';
COMMENT ON COLUMN card_benefit.card_cond.bnft_id IS '조건이 걸린 혜택 ID(카드 전체 조건이면 NULL)';
COMMENT ON COLUMN card_benefit.card_cond.cond_apply_lvl_cd IS '적용 수준(CARD: 카드 전체, BENEFIT: 특정 혜택)';
COMMENT ON COLUMN card_benefit.card_cond.cond_type_cd IS '조건 유형(SPEND_REQ: 전월실적 요건, SPEND_EXCL: 실적 산정 제외, BNFT_EXCL: 혜택 적용 제외, LIMIT: 한도, TIER: 구간별 혜택률·금액, USAGE_REQ: 건당 이용 요건, GRACE: 유예, MERCHANT_RULE: 가맹점 분류 규칙, ETC)';
COMMENT ON COLUMN card_benefit.card_cond.excl_item_id IS '표준 제외 항목 ID(SPEND_EXCL·BNFT_EXCL 필수)';
COMMENT ON COLUMN card_benefit.card_cond.cond_excl_raw_txt IS '제외 항목 원문 표기';
COMMENT ON COLUMN card_benefit.card_cond.cond_basis_cd IS '금액 기준(PREV_MONTH_SPEND, TXN_AMT, MONTH_USAGE, NONE)';
COMMENT ON COLUMN card_benefit.card_cond.cond_min_amt IS '구간 하한 금액(원, 이상). 실적 무관은 SPEND_REQ + 0';
COMMENT ON COLUMN card_benefit.card_cond.cond_max_amt IS '구간 상한 금액(원, 미만)';
COMMENT ON COLUMN card_benefit.card_cond.cond_rate IS '구간 할인·적립률(%)';
COMMENT ON COLUMN card_benefit.card_cond.cond_amt IS '구간 정액 혜택 금액(원)';
COMMENT ON COLUMN card_benefit.card_cond.cond_limit_amt IS '한도 금액(원)';
COMMENT ON COLUMN card_benefit.card_cond.cond_limit_cnt IS '한도 횟수';
COMMENT ON COLUMN card_benefit.card_cond.cond_period_cd IS '한도 기간(TXN, DAY, MONTH, YEAR, NONE)';
COMMENT ON COLUMN card_benefit.card_cond.cond_modality_cd IS '적용 확정성(CONFIRMED: 확정, POSSIBLE: 제외될 수 있음)';
COMMENT ON COLUMN card_benefit.card_cond.cond_value_txt IS '금액·비율·횟수 원문 표기';
COMMENT ON COLUMN card_benefit.card_cond.cond_target_txt IS '대상 가맹점·업종·거래 원문 표기';
COMMENT ON COLUMN card_benefit.card_cond.cond_natural_key IS '조건 자연키 SHA-256(카드·혜택·유형·제외 항목·기준·값). 재적재 중복 방지';
COMMENT ON COLUMN card_benefit.card_cond.cond_policy_cand_key IS '동일 정책 후보 키 SHA-256(카드사·유형·적용 범위·제외 항목·값, 카드 제외). 자동 병합 근거 아님';
COMMENT ON COLUMN card_benefit.card_cond.chunk_id IS '근거 청크 ID';
COMMENT ON COLUMN card_benefit.card_cond.cond_evidence_txt IS '근거 원문 문장';
COMMENT ON COLUMN card_benefit.card_cond.cond_evidence_start_pos IS '근거의 chunk_raw_txt 내 시작 위치';
COMMENT ON COLUMN card_benefit.card_cond.cond_evidence_end_pos IS '근거의 chunk_raw_txt 내 끝 위치';
COMMENT ON COLUMN card_benefit.card_cond.stg_id IS '확정 근거 staging ID';
COMMENT ON COLUMN card_benefit.card_cond.cond_status IS '상태(CONFIRMED, RETIRED: 신규 문서 버전으로 대체)';
COMMENT ON COLUMN card_benefit.card_cond.create_date IS '생성 일시';
COMMENT ON COLUMN card_benefit.card_cond.create_user_id IS '생성 사용자 ID';
COMMENT ON COLUMN card_benefit.card_cond.update_date IS '수정 일시';
COMMENT ON COLUMN card_benefit.card_cond.update_user_id IS '수정 사용자 ID';
