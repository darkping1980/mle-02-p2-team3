# [변경 검토 / 개발 DB 적용 완료] CARD_SOURCE_EVIDENCE PK 승계 변경 검토 결과

- 작성일: 2026-11-03
- 기준 설계안: `CARD_SOURCE_EVIDENCE_PK_INHERITANCE_PROPOSAL_20261103.md` (수정하지 않음)
- 상태: **2026-11-03 개발 Supabase `db_pipeline`에 적용 완료** (사용자 승인 후). 적용 결과는 6절. 1~5절은 적용 전 검토 내용이다.
- 결론: 차단 요인 없이 적용했고 데이터·근거 연결·Neo4j 대조가 적용 전과 같다.

## 1. 변경 전·후 구조

| 구분 | 변경 전 (실제 DB) | 변경 후 |
|---|---|---|
| PK | `card_source_evidence_pkey PRIMARY KEY (evidence_id)` | `card_source_evidence_pkey PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id)` |
| UNIQUE | 없음 | `card_source_evidence_evidence_id_key UNIQUE (evidence_id)` |
| CHECK | `card_source_evidence_ck_1`, `_ck_2` | 변경 없음 |
| 인덱스 | PK 인덱스, `ix_card_source_evidence_lookup (card_doc_id, page_no, card_doc_chunk_id)` | PK 인덱스(복합), UNIQUE 인덱스, lookup 인덱스 유지 |
| 컬럼·행 | 9개 컬럼, 35행 | 변경 없음 |
| `evidence_id` 생성 | `DEFAULT db_pipeline.fn_get_biz_id('card_source_evidence')` | 변경 없음 |

## 2. 실제 DB 확인 결과

PostgreSQL 17.11, `db_pipeline` 스키마. 2026-11-03에 읽기 전용 트랜잭션으로 조회했다.

| 번호 | 확인 항목 | 결과 |
|---|---|---|
| 1 | 현재 PK·UNIQUE | PK `(evidence_id)` 하나, UNIQUE 없음. DDL 파일(`db_pipeline_schemaV7_draft.sql:931`)과 05:24 백업이 실제 DB와 같다 |
| 2 | 이 테이블을 참조하는 물리 FK | **0건.** `db_pipeline` 스키마 전체의 물리 FK도 0건 |
| 2-1 | PK 제약에 의존하는 객체 | 자기 인덱스 1건뿐. GROUP BY 함수 종속으로 PK에 기대는 뷰 없음 |
| 3 | 상위 `CARD_DOC_CHUNK`가 없는 근거 | 0건 |
| 4 | `EVIDENCE_ID` 중복 / 새 복합 PK 중복 / PK 컬럼 NULL | 0 / 0 / 0. 네 컬럼 모두 NOT NULL |
| 5 | `CARD_EVIDENCE_LINK` 정합성 | 57행 중 원문 없는 연결 0건. 근거 35건 모두 1건 이상 연결. BNFT 37·CARD 9·RULE 11 |
| 6 | 데이터 건수 | 35건 (문서 `20261101_000002` 31건, `20261102_000003` 1건, `20261102_000004` 3건). 행 지문 `9ef45cf74b2219b9bb5ce61c48b553f6` |
| 7 | 트리거·정책·발행 | 없음. 테이블 크기 80 kB |
| 8 | 의존 뷰 | `v_card_integrity_issue`, `v_common_cd_usage`. 둘 다 컬럼만 참조해 키 제약 변경의 영향 없음. 현재 게이트 결과 `evidence_not_approved=35` |

### 설계안과 다른 점

1. **설계안에 없던 인덱스** `ix_card_source_evidence_lookup (card_doc_id, page_no, card_doc_chunk_id)`가 있다. 변경 후에는 새 PK 인덱스의 앞부분과 겹친다. 이번 범위가 PK·UNIQUE뿐이라 유지했다. 삭제할지는 별도로 결정한다.
2. **의존 뷰 2개**가 있다. 영향이 없음을 확인했다(2-1, 8).
3. `CARD_DOC_CHUNK`는 PK 외에 `UNIQUE (card_doc_chunk_id)`가 있어 청크 ID만으로도 유일하다. 새 PK의 유일성은 그대로 `evidence_id`가 보장한다. 이번 변경은 식별 관계를 표현하기 위한 것이다.
4. 설계안이 주의한 물리 FK는 실제로 없다. 그래도 스크립트는 FK가 있으면 중단한다.
5. 설계안의 DDL에 없던 안전장치를 추가했다: 상태 판정, 사전 잠금, 잠금 상태에서의 재검증, 전후 행 지문 비교, 재실행 안전성.

## 3. 생성한 SQL

| 파일 | 내용 | 실제 DB 실행 |
|---|---|---|
| `db_pipeline_card_source_evidence_pk_inheritance_precheck.sql` | 차단 조건 C01~C13, 비교 기준 I01~I06, 원인 행 조회. READ ONLY 후 ROLLBACK | SELECT만 실행함. **C01~C13 모두 통과** |
| `db_pipeline_card_source_evidence_pk_inheritance.sql` | PK 변경 | **실행하지 않음** |
| `db_pipeline_card_source_evidence_pk_inheritance_postcheck.sql` | 변경 결과 P01~P08, I01~I05 비교, 근거 3종 JOIN, 문서→청크→근거 경로 | SELECT만 실행함. 변경 전이라 P01·P03 false가 정상 |
| `db_pipeline_card_source_evidence_pk_inheritance_rollback.sql` | 되돌리기 | **실행하지 않음** |

변경 스크립트의 처리 순서:

1. `BEGIN`, `lock_timeout 5s`, `statement_timeout 60s`
2. `LOCK TABLE ... ACCESS EXCLUSIVE`
3. 상태 판정: 이미 변경됨이면 `NOTICE` 후 종료하고, 변경 전 상태가 아니면 오류
4. 잠금 상태에서 차단 조건 재검증: FK, PK 의존 객체, 이름 충돌, NULL, 중복, 상위 청크, 근거 연결
5. 건수·행 지문 기록
6. `ADD UNIQUE (evidence_id)` → `DROP CONSTRAINT card_source_evidence_pkey`(CASCADE 없음) → `ADD PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id)`
7. 목표 구조와 건수·행 지문을 비교해 다르면 오류
8. `COMMIT`

오류가 나면 트랜잭션이 중단되어 `COMMIT`이 `ROLLBACK`으로 처리된다. 되돌리기 스크립트도 같은 구조다. 변경 후 이 테이블을 참조하는 FK나 PK·UNIQUE에 의존하는 객체가 생겼으면 중단한다.

### 격리 시험 결과 (PGlite, PostgreSQL 16.4)

실제 DB와 같은 테이블 정의, 실제 35행·청크 10행·링크 57행 사본으로 실행했다. 사본의 행 지문이 실제 DB와 같다. **19개 시나리오가 모두 통과했다.**

- **정상 경로:** 사전 검증 통과 → 변경 → 사후 검증 P01~P08 통과 → 건수·행 지문·링크 JOIN·뷰 결과가 사전 값과 동일 → lookup 인덱스 유지
- **재실행:** 변경 재실행과 되돌리기 재실행 모두 아무것도 바꾸지 않았다. 되돌린 뒤 다시 변경할 수 있었다.
- **변경 후 동작:** 기존 `insert_evidence` 형태의 INSERT(`evidence_id` 기본값 생성)가 그대로 동작했다. 다른 청크에 같은 `EVIDENCE_ID`를 넣으면 새 UNIQUE가 거부했다.
- **되돌리기:** 원래 PK로 돌아갔고 행 지문이 같았다.
- **변경 차단 (키 구조와 데이터 그대로 유지):** 상위 청크 없는 근거, 원문 없는 근거 연결, 기존 PK를 참조하는 FK, PK 함수 종속 뷰, 같은 이름의 객체, 예상과 다른 PK
- **되돌리기 차단:** 변경 후 새 UNIQUE를 참조하는 FK가 생긴 경우

시험 스크립트는 저장소에 넣지 않았다. 다른 세션의 잠금 대기(`lock_timeout`)는 단일 세션 환경이라 시험하지 못했다.

## 4. 프로그램 영향 분석

결론: **프로그램 수정은 필요 없다.** 문서와 DDL 원본은 적용 후 갱신해야 한다(4-2).

### 4-1. 실행 코드 (모두 영향 없음)

| 대상 | 위치 | 판단 근거 |
|---|---|---|
| INSERT | `payment_card/db_pipeline/extraction_repository.sql:181` (`insert_evidence`), 호출 `extraction_service.py:916` | `evidence_id`를 넣지 않고 DB 기본값으로 생성한다. 새 PK의 네 컬럼은 모두 값이 들어간다 |
| UPDATE·DELETE | 실행 코드에 없음 | `src/data/backup/.../restore_evidence037.sql`의 과거 복구용 UPDATE 1건만 있다(위치 컬럼만 변경) |
| UPSERT·`ON CONFLICT` | 이 테이블 대상 없음 | `ON CONFLICT ON CONSTRAINT`는 `pk_common_cd`, `card_evidence_link_natural_key`만 사용 (`common_benefit_repository.sql:127`, `:132`) |
| PK 제약명 의존 | 실행 코드에 없음 | `card_source_evidence_pkey`를 쓰는 곳은 백업 덤프와 설계안뿐. 변경 후에도 같은 이름을 유지한다 |
| `EVIDENCE_ID` 단독 SELECT·JOIN | `embedding_repository.sql:182`, `common_benefit_repository.sql:54`, `:102`, `neo4j_validation.sql:12`, 뷰 2개 | 새 UNIQUE 인덱스가 같은 조회를 지원한다 |
| `CARD_EXTR_STG_ID` 기준 조회 | `extraction_repository.sql:57`, `:300`, `common_benefit_repository.sql:81`, `:113`, `embedding_repository.sql:195` | 키 제약과 무관 |
| `CARD_EVIDENCE_LINK` 연결 | `product_benefit_service.py:85-89`, `common_benefit_service.py:265-298` | `evidence_id` 값으로 연결하며 구조 변경 없음 |
| Neo4j 적재 | `neo4j_dry_run.py:38` `"card_source_evidence": ("evidence_id",)`, `:229` | 노드 키가 코드에 `evidence_id`로 고정돼 있고 DB 카탈로그의 PK를 읽지 않는다. 데이터가 같으므로 재적재 불필요 |
| Neo4j 조회 | `db_pipeline_origin_search/neo4j_search.py:60`, `:62` | 관계 경로로만 조회 |
| 시험 | `tests/test_live_registration.py:82`, `:185` | `evidence_id` 없이 INSERT, `evidence_id`로 조회. 영향 없음 |

### 4-2. 적용 후 갱신할 문서·원본 (6절에서 V7 SQL·DBML 반영)

| 파일 | 내용 |
|---|---|
| `db_pipeline_schemaV7_draft.sql:931` | `PRIMARY KEY (evidence_id)` → 복합 PK + UNIQUE. 이 파일로 새로 만들면 기존 PK가 된다 |
| `db_pipeline_schemaV7_draft.dbml:95` | `evidence_id`의 `pk` 표시를 복합 인덱스 정의로 변경 |
| `tools/v7_verification/` 카탈로그 비교 도구 | 실제 DB와 V7 파일을 비교하면 이 차이가 새로 나타난다 |
| ERD·속성 문서 (`docs/neo4j/Neo4j_DF_ERD_*`, `CARD_DATA_REGISTRATION_VALIDATION_DETAIL.md` 등) | 식별 관계 표시. 그래프 구조는 바뀌지 않는다 |

## 5. 확인되지 않은 위험과 적용 전 선행 조건

| 항목 | 내용 | 대응 |
|---|---|---|
| 잠금 | `ACCESS EXCLUSIVE`를 짧게 잡는다. 조회 시점에 다른 세션 11개가 있었다 | `_precheck.sql` 2-4로 오래된 트랜잭션을 확인한다. 5초를 넘기면 오류로 끝나며 다시 실행하면 된다 |
| 버전 차이 | 격리 시험은 PostgreSQL 16.4, 실제 DB는 17.11 | 사용한 구문은 두 버전에 공통이다. 실제 적용은 실행하지 않았으므로 미검증 |
| 겹치는 인덱스 | lookup 인덱스가 새 PK의 앞부분과 같다 | 기능 영향은 없다. 쓰기 비용을 줄이려면 별도 승인 후 삭제 |
| 데이터 변동 | 확인 시점 35건 | 적용 직전에 `_precheck.sql`을 다시 실행해 C01~C13과 I01~I06을 기록한다 |
| 백업 | 05:24 백업은 이 시점 데이터와 같다고 확인하지 않았다 | 적용 전에 새 백업을 만든다 |
| 다음 단계 | `CARD_EVIDENCE_LINK`가 복합 PK를 물리적으로 참조하게 하려면 링크에 문서·페이지·청크 컬럼이 필요하다 | 현재는 `UNIQUE (evidence_id)`로 단독 참조를 유지한다. 링크 구조는 다음 단계에서 검토 |
| 미검증 | 실제 DB 적용, 적용 후 GraphRAG·Streamlit 근거 표시, Neo4j 검증(`neo4j_validate`) | 적용 후 `_postcheck.sql`과 기존 회귀 시험으로 확인 |

### 적용 절차 (승인 후)

1. 새 백업을 만든다.
2. `_precheck.sql`을 실행해 C01~C13이 모두 true인지 보고 I01~I06을 기록한다.
3. `db_pipeline_card_source_evidence_pk_inheritance.sql`을 실행해 `NOTICE 변경 완료. 근거 N건, 행 지문 ...`을 확인한다.
4. `_postcheck.sql`을 실행해 P01~P08이 true이고 I01~I04가 2번의 값과 같은지 확인한다.
5. 문제가 있으면 `_rollback.sql`을 실행하고 `_precheck.sql`의 C01~C03, `_postcheck.sql`의 I01~I04로 원래 상태를 확인한다.
6. 4-2의 문서와 DDL 원본을 갱신한다.

## 6. 적용 결과 (2026-11-03, 개발 Supabase)

| 단계 | 결과 |
|---|---|
| 대상 | PostgreSQL 17.11, DB `postgres`, 스키마 `db_pipeline`. 문서에 "개발 Supabase"와 "공유 Supabase"로 함께 기록돼 있어 사용자에게 확인한 뒤 적용했다 |
| 백업 | `src/data/backup/pre_card_source_evidence_pk_inheritance_20261103/backup.json`. 사전 검증과 같은 읽기 스냅샷에서 근거 35행, 근거 연결 57행, 청크 키 10행, 제약·인덱스·컬럼 정의를 저장했다. 이 파일만으로 메모리 PostgreSQL에 복원해 행 지문이 같음을 확인했다 |
| 사전 검증 | C01~C13 모두 통과. I01=35, I02=`9ef45cf74b2219b9bb5ce61c48b553f6`, I03=57/57, I04=`evidence_not_approved=35`. 장기 트랜잭션 없음 |
| 적용 | 변경 SQL 1회 실행, 재시도 없음. `NOTICE 변경 완료. 근거 35건, 행 지문 9ef45cf7…` |
| 사후 검증 | P01~P08 모두 통과. I01~I04 적용 전과 동일. 근거 연결 BNFT 37·CARD 9·RULE 11 모두 JOIN됨 |
| 조회 | `EVIDENCE_ID` 단독 조회가 새 `card_source_evidence_evidence_id_key` 인덱스를 사용. `select_card_bnft_evidence` 혜택 5건, `neo4j_validation.evidence_links` 57건 정상 |
| Neo4j | `neo4j_validate` 읽기 전용 대조 `ok: true` (노드 124·관계 196 차이 0, 근거 연결 57=57). 재적재하지 않았다 |
| 설계 원본 | `db_pipeline_schemaV7_draft.sql`의 CREATE TABLE에 복합 PK와 `UNIQUE (evidence_id)`를 실제 DB와 같은 제약명으로 반영. `db_pipeline_schemaV7_draft.dbml`에 복합 PK 인덱스와 `evidence_id` unique를 반영. 청크와의 Ref는 기존 논리 관계 그대로 두고 물리 FK가 없음을 테이블 설명에 적었다 |
| 프로그램 | 수정하지 않았다. 4-1의 근거와 아래 시험으로 확인 |

수정한 V7 DDL로 메모리 PostgreSQL에 스키마를 새로 만들어, 실제 저장소 SQL 문장으로 15개 항목을 시험했고 모두 통과했다.
- **생성 구조:** PK·UNIQUE·컬럼이 실제 DB와 같다. 변경 SQL을 다시 실행하면 아무것도 바꾸지 않는다.
- **원문 근거 등록:** `extraction_repository.insert_evidence`로 기본값 ID 생성, 같은 청크 여러 건, 다른 청크 등록이 된다. 같은 `EVIDENCE_ID`는 같은 청크면 PK, 다른 청크면 UNIQUE가 막는다.
- **근거 연결:** `common_benefit_repository.insert_evidence_link`·`insert_rule_evidence_link`로 등록되고, 다시 실행해도 `ON CONFLICT` 때문에 중복이 생기지 않는다.
- **조회:** `embedding_repository.select_card_bnft_evidence`, `neo4j_validation.evidence_links`(CARD·BNFT·RULE)가 결과를 돌려준다. 정합성 뷰의 원문·청크 고아 게이트는 0건이다.
- **물리 FK 없음:** 복합 PK는 물리 FK가 아니어서 없는 청크를 가리키는 행을 DB가 막지 않는다. 이런 행은 정합성 뷰 `evidence_source_orphan`이 잡는다.

남은 사항
- `ix_card_source_evidence_lookup`은 새 PK 인덱스의 앞부분과 겹친다. 유지할지 따로 결정한다.
- `DEVELOPMENT_HANDOFF_20261103.md:236`의 "PK evidence_id" 표기는 작성 시점의 기록이라 수정하지 않았다.
- `tools/v7_verification`의 카탈로그 비교 도구와 기준 파일(`reference/`)은 다시 생성하지 않았다.
- `test_live_registration.py`(개발 DB ROLLBACK 등록 시험)는 실제 임베딩 API를 호출하고 시퀀스 번호를 소비해 실행하지 않았다.

## 7. 컬럼 순서 변경 (2026-11-03, 개발 Supabase 적용 완료)

PostgreSQL은 컬럼 순서를 바꾸는 문법이 없어 테이블을 다시 만들었다. PK·UNIQUE 정의는 6절과 같다.

| 구분 | 컬럼 순서 |
|---|---|
| 변경 전 | evidence_id, card_doc_id, page_no, card_doc_chunk_id, card_extr_stg_id, quote_txt, start_pos, end_pos, approval_status_cd |
| 변경 후 | **card_doc_id, page_no, card_doc_chunk_id, evidence_id**, card_extr_stg_id, quote_txt, start_pos, end_pos, approval_status_cd |

### 사전 조사 (실제 DB, 읽기 전용)

| 항목 | 결과 |
|---|---|
| 의존 객체 | 뷰 2개뿐. `v_card_integrity_issue`가 `v_common_cd_usage`도 참조한다(뷰 간 의존). 다른 스키마의 의존 객체 없음 |
| 행 타입 의존 | 자기 배열 타입뿐. 행 타입을 인자·반환으로 쓰는 함수 없음 |
| 권한·RLS·트리거·정책·규칙·발행·상속·컬럼 권한 | 모두 없음. 테이블·뷰 ACL은 NULL(소유자 postgres 기본) |
| 복원 대상 | 테이블 주석, 컬럼 주석 9개, `evidence_id` 기본값 `fn_get_biz_id`, 제약 4개, 비제약 인덱스 1개, 뷰 2개의 정의·주석·소유자 |
| Supabase 이벤트 트리거 | `ensure_rls`는 `public` 스키마만 대상이라 `db_pipeline`에 영향 없음(함수 본문 확인). `pgrst_ddl_watch`·`pgrst_drop_watch`는 PostgREST 재조회 알림만 보낸다 |

### 스크립트

- `db_pipeline_card_source_evidence_column_order.sql` (변경), `db_pipeline_card_source_evidence_column_order_rollback.sql` (되돌리기). 둘은 컬럼 순서 배열만 다르다.
- **잠금과 정의 읽기:** 한 트랜잭션에서 테이블과 두 뷰를 잠근다(5초 제한). `search_path`를 `pg_catalog`로 고정하고 정의를 그 자리에서 읽는다.
- **중단 조건:** 두 뷰 외의 종속 객체가 있거나 예상과 다른 컬럼 구성이면 중단한다. 이미 목표 순서면 아무것도 하지 않는다.
- **교체 순서:**
  1. 뷰를 의존 역순으로 삭제
  2. 기존 테이블 이름 변경
  3. 새 테이블 생성 후 컬럼 이름을 지정해 복사
  4. 제약·인덱스 생성
  5. 기존 테이블 삭제
  6. 주석·소유자·권한·RLS 복원
  7. 뷰를 의존 순서로 재생성
- **CASCADE 미사용:** 뷰 삭제와 기존 테이블 삭제 모두 CASCADE 없이 한다. 다른 종속 객체가 생겼다면 오류로 멈춘다.
- **검증:** 컬럼 정의, 제약, 인덱스, 테이블 속성, 데이터 지문, 뷰 정의 문자열·속성·결과를 변경 전과 비교한다. 하나라도 다르면 전체 ROLLBACK한다.
- **데이터 지문:** 최초 컬럼 순서로 행을 만들어 계산하므로 컬럼 배치와 무관하다. `_precheck.sql`·`_postcheck.sql`의 I02도 같은 식으로 바꿨으며, 값은 이전과 같다.

### 격리 시험 (PGlite, PostgreSQL 16.4)

환경은 현재 V7 DDL, 실제 DB에서 읽은 두 뷰 정의, 실제 근거 35행·연결 57행이다. 20개 시나리오가 모두 통과했다.
- **정상 경로:** 변경 → 모든 항목 동일 → 재실행 시 변경 없음
- **변경 후 동작:** 등록, 중복 차단, 연결 JOIN 57건
- **되돌리기:** 되돌린 결과가 원래와 동일, 되돌리기 재실행 시 변경 없음, 되돌린 뒤 재변경 가능
- **차단 7종:** 다른 뷰(테이블 참조·뷰 참조), 행 타입 함수, 트리거, 정책, 컬럼 권한, 다른 컬럼 구성. 모두 아무것도 바꾸지 않고 멈췄다.
- **검증 실패:** 복사 후 데이터를 일부러 바꾼 사본에서 검증이 실패했고, 테이블·뷰가 모두 원래대로 돌아왔다.

첫 시험에서 종속 객체 검사가 테이블 자신의 행 타입까지 막는 오류를 찾아 고쳤다.

### 적용 결과

| 단계 | 결과 |
|---|---|
| 백업 | `src/data/backup/pre_card_source_evidence_column_order_20261103/backup.json`. 테이블 정의·주석·제약·인덱스, 뷰 2개의 정의·주석·소유자, 근거 35행·연결 57행·청크 키 10행, 뷰 결과 지문. 이 파일만으로 복원해 지문이 같음을 확인 |
| 적용 직전 | P01~P08 통과, 다른 트랜잭션·잠금 없음 |
| 적용 | 1회 실행, 재시도 없음. `컬럼 순서 변경 완료 … 근거 35건, 지문 9ef45cf7…, 제약 4개, 인덱스 1개, 뷰 2개 복원` |
| 컬럼 순서 | `pg_attribute`와 `information_schema.columns`(DBeaver 표시 기준) 모두 card_doc_id(1), page_no(2), card_doc_chunk_id(3), evidence_id(4) … |
| 보존 | 컬럼 정의·기본값·주석, PK·UNIQUE·CHECK 2개, 인덱스 3개, 소유자·ACL·RLS, 뷰 정의·주석·소유자·뷰 간 의존, `v_card_integrity_issue` 35행·`v_common_cd_usage` 392행 결과 지문이 변경 전과 같다. 임시 객체 잔여 0 |
| 사후 검증 | P01~P08 통과, I01~I05 변경 전과 동일. 근거 연결 BNFT 37·CARD 9·RULE 11 |
| 조회·Neo4j | 혜택 5건 근거 조회, 연결 57건, `EVIDENCE_ID` 단독 조회는 UNIQUE 인덱스 사용. `neo4j_validate` `ok: true` (차이 0). 재적재하지 않았다 |
| 프로그램 | 수정 없음. 실행 코드의 INSERT는 모두 컬럼을 지정한다. `SELECT *`를 쓰는 Neo4j 적재(`neo4j_dry_run.py:110`)는 행을 이름으로 다루고 `sort_keys=True`로 직렬화(`:56`)해 컬럼 순서와 무관하다 |
| 설계 원본 | `db_pipeline_schemaV7_draft.sql`의 CREATE TABLE 컬럼 순서와 컬럼 주석 순서, `db_pipeline_schemaV7_draft.dbml`의 컬럼 순서를 실제 DB와 맞췄다. 이 DDL로 새로 만든 테이블의 컬럼 순서·제약이 실제 DB와 같음을 격리 시험으로 확인했다 |

남은 사항
- 테이블을 다시 만들었으므로 테이블 OID가 바뀌었다. OID를 저장해 쓰는 프로그램은 저장소에 없다.
- 통계는 `ANALYZE`로 다시 수집했다. 이전 누적 통계(행 갱신 횟수 등)는 초기화됐다.
- 테이블 재생성은 PGlite(16.4)에서 시험했고, 실제 DB(17.11)에서는 한 번 적용해 결과를 확인했다. 되돌리기 스크립트는 실제 DB에서 실행하지 않았다.
