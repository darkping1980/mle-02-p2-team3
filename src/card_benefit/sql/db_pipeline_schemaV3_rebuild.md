# db_pipeline V3 재생성 절차 (개발·테스트 DB 전용)

대상 DDL: `db_pipeline_schemaV3.sql`. 이 문서는 **실행 절차**이며, 작성 과정에서 공유 Supabase DB의 스키마를 삭제하거나 DDL을 실행하지 않았다. V3 SQL은 `CREATE SCHEMA db_pipeline`을 포함하며 `DROP`은 포함하지 않는다. PostgreSQL 17 백업을 기준으로 작성했다. 기존 11개 테이블과 신규 4개, 총 15개다.

## 1. 대상 확인 및 삭제 전 중단 조건

`psql`의 접속 인자는 **개발·테스트 DB**의 별도 접속 정보로 지정한다. 운영/공유 Supabase 접속 문자열이나 `.env`를 사용하지 않는다. `\conninfo`와 아래 결과를 사람이 확인한 후에만 2단계로 진행한다.

```sql
\conninfo
SELECT current_database() AS db_name, current_user AS db_user,
       inet_server_addr() AS server_addr, inet_server_port() AS server_port,
       to_regnamespace('db_pipeline') AS target_schema;
SELECT table_schema, count(*) AS table_count
FROM information_schema.tables
WHERE table_schema='db_pipeline' AND table_type='BASE TABLE'
GROUP BY table_schema;
SELECT schemaname, tablename FROM pg_catalog.pg_tables
WHERE schemaname='db_pipeline' ORDER BY tablename;
```

**중단 조건:** 접속 대상이 공유 Supabase이거나, DB명·서버·소유자·스키마가 예정된 일회성 개발 DB와 일치하지 않거나, 보존할 데이터/객체가 있으면 삭제하지 않는다. 스키마가 이미 없으면 `DROP`은 생략한다. `DROP SCHEMA ... CASCADE`는 하위 테이블, 함수, 시퀀스, 인덱스와 데이터를 모두 삭제한다.

## 2. 별도 세션에서 재생성

대상을 확인한 뒤 개발·테스트 DB에서만 다음을 **별도의 명시적 단계**로 실행한다. V3에는 `BEGIN ... COMMIT`과 `CREATE SCHEMA`가 있으므로 외부에서 스키마를 다시 만들지 않는다. `psql`은 `ON_ERROR_STOP=1`로 실행하고 오류가 나면 완료된 것으로 보고하지 않는다. SQL 파일은 해당 폴더를 현재 작업 디렉터리로 하여 `\i db_pipeline_schemaV3.sql`로 읽거나 `psql -X -v ON_ERROR_STOP=1 -d <확인한_개발DB> -f src/card_benefit/sql/db_pipeline_schemaV3.sql`로 실행한다.

```sql
-- 사람이 1단계 결과를 확인하고, 오직 일회성 개발/테스트 DB에서 직접 실행.
DROP SCHEMA IF EXISTS db_pipeline CASCADE;
-- 이어서 별도 파일 db_pipeline_schemaV3.sql 실행.
```

V3은 함수→기존 테이블→기존 시퀀스/제약/인덱스→신규 시퀀스→신규 테이블 순이다. `fn_get_biz_id()`는 테이블 정의 시 실행되지 않고 첫 INSERT에서 시퀀스를 조회한다. 따라서 전체 DDL 실행이 끝난 후 ID 기본값을 시험한다. 기존 함수와 8개 기존 시퀀스의 6자리 발급 옵션을 보존했고, 신규 `seq_card_product_variant`도 `START 1, INCREMENT 1, MAXVALUE 999999, CACHE 1, CYCLE`이다. `card_id bigint`의 `seq_card_product`는 6자리 문자 ID 함수와 무관한 bigint `nextval`이다.

## 3. 생성 결과 검사

아래 결과는 테이블 **15**, 시퀀스 **10**, PK **15**, 물리 FK **0**이어야 한다. 누락·초과 객체와 컬럼 수도 함께 살펴본다.

```sql
SELECT count(*) AS tables FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='db_pipeline' AND c.relkind='r';

WITH expected(tablename) AS (VALUES
 ('card_ai_call'),('card_ai_run'),('card_bnft'),('card_bnft_cond'),
 ('card_cond'),('card_doc'),('card_doc_chunk'),('card_doc_page'),
 ('card_excl_item'),('card_excl_item_als'),('card_extr_stg'),
 ('card_product'),('card_product_variant'),('card_product_doc'),
 ('card_product_variant_doc'))
SELECT e.tablename, to_regclass('db_pipeline.'||e.tablename) AS created
FROM expected e ORDER BY e.tablename;

SELECT c.relname AS table_name, count(a.attnum) AS column_count
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
WHERE n.nspname='db_pipeline' AND c.relkind='r'
  AND a.attnum>0 AND NOT a.attisdropped
GROUP BY c.relname ORDER BY c.relname;

SELECT k.contype, count(*) AS constraint_count
FROM pg_catalog.pg_constraint k
JOIN pg_catalog.pg_namespace n ON n.oid=k.connamespace
WHERE n.nspname='db_pipeline'
GROUP BY k.contype ORDER BY k.contype;
-- contype p=PK, u=UNIQUE, c=CHECK; f=physical FK must be absent.

SELECT c.relname AS table_name, k.conname, pg_get_constraintdef(k.oid) AS definition
FROM pg_catalog.pg_constraint k
JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='db_pipeline' AND k.contype='p'
ORDER BY c.relname;

SELECT sequencename, start_value, increment_by, max_value, cache_size, cycle
FROM pg_catalog.pg_sequences
WHERE schemaname='db_pipeline' ORDER BY sequencename;
WITH expected(seqname) AS (VALUES
 ('seq_card_ai_run'),('seq_card_bnft'),('seq_card_cond'),('seq_card_doc'),
 ('seq_card_doc_chunk'),('seq_card_excl_item'),('seq_card_excl_item_als'),
 ('seq_card_extr_stg'),('seq_card_product'),('seq_card_product_variant'))
SELECT seqname, to_regclass('db_pipeline.'||seqname) AS actual_sequence
FROM expected ORDER BY seqname;
SELECT to_regprocedure('db_pipeline.fn_get_biz_id(text)') AS id_function;
SELECT tablename, indexname, indexdef FROM pg_catalog.pg_indexes
WHERE schemaname='db_pipeline' ORDER BY tablename,indexname;
```

특히 네 복합 PK를 확인한다: `card_product_variant(card_id,card_variant_id)`, `card_product_doc(card_id,card_doc_id)`, `card_product_variant_doc(card_id,card_variant_id,card_doc_id)`, 기존 `card_bnft_cond(card_doc_id,card_bnft_id,card_cond_id)`. 기존 `card_bnft`/`card_cond`는 문서 중심 PK를 그대로 유지한다. `card_doc`에는 상품별 UNIQUE와 부분 UNIQUE `uq_card_doc_active`가 없어야 한다.

## 4. 첫 INSERT·공유 문서·중복 검사 (일회성 개발 DB에서만)

아래 블록은 샘플 행을 **롤백**한다. `nextval` 증가 자체는 롤백되지 않으므로 완전히 폐기할 개발 DB에서만 수행한다. 상품 두 행이 같은 `card_doc_id`를 참조하고, 신규 문자열 PK가 `YYYYMMDD_000001` 형식인지 확인한다. 문서의 `card_id`는 NULL이다. `doc_sha256`은 샘플용 64자리 값이며 실제 파일의 해시가 아니다.

```sql
BEGIN;
INSERT INTO db_pipeline.card_product
    (product_cd, product_nm, issuer, card_kind_cd, create_user_id, update_user_id)
VALUES ('TEST_CREDIT','테스트 신용','HANA','CREDIT','v3_test','v3_test'),
       ('TEST_DEBIT','테스트 체크','HANA','DEBIT','v3_test','v3_test');

INSERT INTO db_pipeline.card_product_variant
    (card_id,variant_cd,variant_nm,brand_cd,service_grade_cd,service_type_cd,
     create_user_id,update_user_id)
SELECT card_id, 'VISA_VP001','테스트 발급형','VISA','PLATINUM','VP001',
       'v3_test','v3_test'
FROM db_pipeline.card_product WHERE product_cd='TEST_CREDIT';

INSERT INTO db_pipeline.card_doc
    (doc_cd,doc_family_cd,doc_type_cd,doc_title,doc_file_nm,doc_sha256,
     doc_collect_date,create_user_id,update_user_id)
VALUES ('TEST_COMMON_TERMS','TEST_TERMS','TERMS','테스트 공통 약관',
        'test.pdf',repeat('a',64),now(),'v3_test','v3_test');

INSERT INTO db_pipeline.card_product_doc
    (card_id,card_doc_id,doc_role_cd,effective_from,approval_status_cd,
     applicability_basis_txt,create_user_id,update_user_id)
SELECT p.card_id,d.card_doc_id,'COMMON_TERMS',DATE '2026-01-01',
       'APPROVED','테스트용 가상 적용 근거','v3_test','v3_test'
FROM db_pipeline.card_product p CROSS JOIN db_pipeline.card_doc d
WHERE p.product_cd IN ('TEST_CREDIT','TEST_DEBIT')
  AND d.doc_cd='TEST_COMMON_TERMS';

SELECT p.product_cd, d.card_doc_id, d.card_id AS doc_legacy_card_id,
       v.card_variant_id,
       (d.card_doc_id ~ '^[0-9]{8}_[0-9]{6}$') AS doc_id_format_ok,
       (v.card_variant_id ~ '^[0-9]{8}_[0-9]{6}$') AS variant_id_format_ok
FROM db_pipeline.card_product p
JOIN db_pipeline.card_product_doc l ON l.card_id=p.card_id
JOIN db_pipeline.card_doc d ON d.card_doc_id=l.card_doc_id
LEFT JOIN db_pipeline.card_product_variant v ON v.card_id=p.card_id
WHERE d.doc_cd='TEST_COMMON_TERMS'
ORDER BY p.product_cd;
-- 기대: 상품 2행, 같은 card_doc_id, doc_legacy_card_id NULL,
-- 테스트 신용의 발급형 ID 형식 true.

-- 이미 연결된 PK를 다시 삽입하면 0행. PK/UNIQUE 위반을 숨기는 운영 패턴이 아님.
WITH duplicate AS (
  INSERT INTO db_pipeline.card_product_doc
      (card_id,card_doc_id,doc_role_cd,effective_from,approval_status_cd,
       applicability_basis_txt,create_user_id,update_user_id)
  SELECT card_id,card_doc_id,doc_role_cd,effective_from,approval_status_cd,
         applicability_basis_txt,create_user_id,update_user_id
  FROM db_pipeline.card_product_doc WHERE true LIMIT 1
  ON CONFLICT (card_id,card_doc_id) DO NOTHING RETURNING 1
)
SELECT count(*) AS duplicate_inserted_rows FROM duplicate;
-- 기대 0.
ROLLBACK;
```

## 5. 시퀀스 소진·중복의 의미

`fn_get_biz_id`는 날짜 8자리와 시퀀스 6자리로 ID를 만든다. 백업의 8개 문자열 시퀀스와 신규 발급형 시퀀스 모두 `MAXVALUE 999999 CYCLE`이다. 같은 서울 날짜에 999999회 이상 발급하면 다음 값이 000001로 순환해 **중복될 수 있다**. V3은 기존 규칙을 임의 변경하지 않았으며, 발급형에는 별도 `UNIQUE(card_variant_id)`를 두어 중복을 거부한다. 기존 다른 문자열 업무 ID의 고유 제약도 그대로 보존한다. 소진 상황을 운영 시퀀스의 `setval`로 시험하지 않는다.

일회성 로컬 DB에서 순환 동작만 확인하려면 별도 임시 시퀀스를 사용한다. 아래는 ID 발급 함수를 호출하지 않으며 영구 시퀀스 값도 바꾸지 않는다.

```sql
CREATE TEMP SEQUENCE v3_cycle_probe
    START WITH 1 INCREMENT BY 1 NO MINVALUE MAXVALUE 999999 CACHE 1 CYCLE;
SELECT setval('v3_cycle_probe',999998,true);
SELECT nextval('v3_cycle_probe') AS last_six_digits;
SELECT nextval('v3_cycle_probe') AS wrapped_six_digits;
-- 기대 999999, 1. 같은 날짜 접두부와 결합하면 두 번째 1은 과거 1과 충돌.
```

실제 사용량이 하루 999999건에 가까워지면 `CYCLE` 정책·ID 자릿수의 별도 설계 변경이 필요하다. `seq_card_product`는 bigint로 `NO CYCLE`이며 이 6자리 제한에 속하지 않는다.

## 6. ERD 검토

`db_pipeline_schemaV3.dbml`을 DBML을 지원하는 ERD 도구(dbdiagram.io 등)에 **파일 내용으로 가져오면** 논리 관계선이 표시된다. DBML의 `Ref`는 물리 FK가 아니다. 상품→발급형, 상품/발급형↔문서, 문서→페이지→청크→AI 호출→후보, 문서→기존 혜택/조건 관계를 확인한다. `card_doc.card_id`는 적용 관계선이 아닌 기존 힌트이며, `card_bnft`·`card_cond`의 문서 중심 PK는 이후 변경 대상으로 표시했다.

## 7. 작성 시 검증 결과와 남은 시험

백업과 V3의 SQL 정의를 정적으로 비교했다. 기존 11개 테이블 중 `card_doc` 외 10개의 `CREATE TABLE` 본문은 줄바꿈을 제외하고 동일하다. `card_doc`는 `card_id` NULL 허용, `doc_family_cd`, `BRAND_SERVICE` 문서 유형을 반영했고 PK 및 `doc_cd`·`doc_sha256` UNIQUE를 최종 `CREATE TABLE` 안에 넣었다. 기존 상품별 문서 UNIQUE와 `uq_card_doc_active`만 제거했다. 기존 `fn_get_biz_id` 함수 본문과 8개 문자열 시퀀스 옵션은 보존됐다. V3에는 테이블 15, PK 15, 시퀀스 10, 명시적 인덱스 20, 물리 FK 0이 정의된다. DBML은 15개 테이블의 237개 컬럼을 모두 포함한다.

작성 환경에는 실행 가능한 로컬 `psql`·Docker·PostgreSQL 서버가 없고 WSL 배포판도 설치되지 않아 **실제 DDL 실행과 INSERT 시험은 수행하지 못했다**. 2~5단계는 일회성 PostgreSQL 17 개발 DB에서 사람이 실행하고 결과를 확인해야 한다. 정적 비교가 실행 성공을 보증하지는 않는다.
