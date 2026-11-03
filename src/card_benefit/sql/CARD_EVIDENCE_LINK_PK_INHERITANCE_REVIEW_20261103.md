# [변경 검토 / 개발 DB 적용 완료] CARD_EVIDENCE_LINK 원문 근거 PK 전체 승계

- 작성일: 2026-11-03
- 상태: **2026-11-03 사용자 승인(복합 FK 없이) 후 개발 Supabase에 적용 완료.** 프로그램·설계 파일도 반영했다. 적용 결과는 9절. 1~8절은 적용 전 검토 내용이다.
- 선행 변경: `CARD_SOURCE_EVIDENCE_PK_INHERITANCE_REVIEW_20261103.md` (원문 근거 PK 승계·컬럼 순서, 적용 완료)

## 1. 변경 전·후 구조

| 구분 | 변경 전 (실제 DB) | 변경 후 |
|---|---|---|
| 컬럼 순서 | card_id, ev_link_id, ev_subject_cd, card_bnft_id, rule_key, relation_key, ev_item_cd, ev_item_key, evidence_id | **card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id**, card_bnft_id, ev_subject_cd, rule_key, relation_key, ev_item_cd, ev_item_key |
| PK | `card_evidence_link_pkey (card_id, ev_link_id)` | `card_evidence_link_pkey (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id)` |
| UNIQUE | `card_evidence_link_natural_key` | `card_evidence_link_natural_key`(정의 동일), `card_evidence_link_id_key (card_id, evidence_link_id)` |
| CHECK | `_ck_1`, `_ck_2` | 동일 |
| 인덱스 | `ix_card_evidence_link_evidence (evidence_id)`, `ix_card_evidence_link_subject (card_id, ev_subject_cd, card_bnft_id, rule_key)` | 동일 |
| 연결 ID | `ev_link_id` DEFAULT `fn_get_biz_id('card_evidence_link')` | `evidence_link_id`, 같은 기본값·같은 값 |
| 물리 FK | 없음 | 없음 (6절) |

`evidence_id`는 PDF 원문 근거 식별자, `evidence_link_id`는 그 근거를 카드·혜택·규칙에 연결하는 관계 식별자다.

## 2. 실제 DB 사전 조사 (읽기 전용, 2026-11-03)

| 항목 | 결과 |
|---|---|
| 데이터 | 57건: CARD 9, BNFT 37, RULE 11, REL 0. CARD 9건은 모두 `card_bnft_id` NULL |
| 정합성 | 원문 근거 없는 연결 0, `(card_id, ev_link_id)` 중복 0, `ev_link_id` 전체 중복 0 |
| 이관 가능성 | 원문 근거 JOIN 결과 57건(누락·중복 없음). 새 6컬럼 PK 중복 0. 원문 근거 `UNIQUE(evidence_id)`가 있어 1:1로 상위키를 얻는다 |
| 종속 객체 | 뷰 2개: `v_card_integrity_issue`(`ev_link_id` 사용, `v_common_cd_usage`도 참조), `v_common_cd_usage`. 함수·트리거·정책·규칙·발행·컬럼 권한 없음. 행 타입 의존 없음 |
| 속성 | 소유자 postgres, ACL NULL, RLS 꺼짐. 테이블·컬럼 주석 있음. 이전에 지운 컬럼 흔적 2개(attnum 2, 8)는 재생성으로 사라진다 |
| 시퀀스 | `seq_card_evidence_link` (주석이 `ev_link_id`를 가리킴 → 함께 갱신) |
| 행 지문 | 기존 9개 값 기준 `5d61e2d4f0da12be237b9f30af6f2f0f` |

## 3. 설계상 유의사항

이번 PK는 식별에 필요한 최소 후보키가 아니다. `(card_id, evidence_link_id)`만으로 유일하며, 이를 `card_evidence_link_id_key`로 별도 보장한다. 상위키 승계는 원문 근거의 소속을 ERD에 드러내기 위한 설계 선택이다.

| 항목 | 내용 |
|---|---|
| 데이터 중복 | `card_doc_id`, `page_no`, `card_doc_chunk_id`는 `evidence_id`로 정해지는 값이다(함수 종속 evidence_id → 문서·페이지·청크). 연결 테이블에 같은 값이 다시 저장된다 |
| 정규화 | 위 종속 때문에 연결 테이블 기준으로는 3정규형이 아니다(PK 일부에 대한 종속). 의도한 비정규화다 |
| 갱신 이상 | 원문 근거의 문서·페이지·청크가 바뀌면 연결의 승계 컬럼도 함께 바꿔야 한다. 현재 원문 근거 키를 바꾸는 프로그램은 없고 식별자라 사실상 불변이다. 불일치는 사후 검증 P08과 같은 검사로 찾는다 |
| 삽입 이상 | 등록 SQL이 상위키를 직접 받지 않고 원문 근거에서 조회해 넣으므로, 프로그램 경로에서는 불일치가 생기지 않는다. 직접 SQL로 넣으면 막을 장치가 없다(6절) |
| 인덱스 | PK 인덱스가 6컬럼으로 넓어지고 `card_evidence_link_id_key` 인덱스가 하나 늘어 인덱스가 5개가 된다. 현재 57행이라 저장·쓰기 비용은 무시할 수준이다. `evidence_id` 단독 조회는 기존 `ix_card_evidence_link_evidence`가 계속 맡는다 |
| 자연키 | `card_evidence_link_natural_key`는 그대로다. 등록 SQL의 `ON CONFLICT ON CONSTRAINT card_evidence_link_natural_key` 동작이 바뀌지 않는다 |

## 4. 생성한 SQL

| 파일 | 내용 | 실제 DB |
|---|---|---|
| `db_pipeline_card_evidence_link_pk_inheritance_precheck.sql` | C01~C14 차단 조건, I01~I06 기준값 | SELECT만 실행 가능 |
| `db_pipeline_card_evidence_link_pk_inheritance.sql` | 변경 | **미실행** |
| `db_pipeline_card_evidence_link_pk_inheritance_postcheck.sql` | P01~P10, I01~I06 비교, 유형별 JOIN | SELECT만 |
| `db_pipeline_card_evidence_link_pk_inheritance_rollback.sql` | 되돌리기 | **미실행** |

변경 스크립트(한 트랜잭션)의 처리 순서:

1. 근거 연결과 두 뷰를 ACCESS EXCLUSIVE로, 원문 근거를 SHARE로 잠근다(5초 제한).
2. 상태를 판정한다. 이미 변경됐으면 아무것도 하지 않고, 예상과 다른 구성이면 중단한다.
3. 차단 조건을 검사한다. 두 뷰 외 종속 객체, 고아 연결, ID 중복, 원문 근거 UNIQUE 부재가 있으면 중단한다.
4. `ev_link_id` → `evidence_link_id`로 이름을 바꾼다. 뷰 정의는 컬럼 번호로 저장되므로 새 이름을 따라가고, 뷰의 출력 컬럼 이름은 바뀌지 않는다.
5. 뷰 정의와 결과를 기록한 뒤 뷰를 삭제한다(CASCADE 없음).
6. 기존 테이블 이름을 바꾸고 새 테이블을 만든다. 원문 근거와 `evidence_id`로 JOIN해 복사한다.
7. 제약과 인덱스를 만든 뒤 기존 테이블을 삭제한다(CASCADE 없음).
8. 주석, 소유자, 권한, 시퀀스 주석을 복원하고 뷰를 재생성한다.
9. 검증한다: 컬럼 순서, PK·UNIQUE, CHECK·자연키, 인덱스, 기본값, 테이블 속성, 컬럼 주석, 행 지문·유형별 건수, 상위키와 원문 근거의 일치, 뷰 정의·결과. 하나라도 다르면 전체를 ROLLBACK한다.

되돌리기 스크립트는 같은 방식으로 원래 구조로 되돌린다. 승계 컬럼은 원문 근거에서 다시 얻을 수 있는 값이라 버린다. 승계 컬럼이 원문 근거와 다른 행이 있으면 그 상태를 숨기지 않도록 중단한다.

## 5. 격리 시험 (PGlite, PostgreSQL 16.4) — 31개 모두 통과

환경은 현재 V7 DDL, 실제 DB에서 읽은 뷰 정의 2개, 실제 원문 근거 35건·연결 57건·청크 10건이다.

| 구분 | 확인 내용 |
|---|---|
| 변경 | 사전 검증 C01~C14 통과 → 변경 → 사후 검증 P01~P10 통과. 건수·지문·유형별 건수·CARD NULL 9건·정합성 뷰 결과·원문 근거 지문이 동일 |
| 뷰 | 결과는 동일하고, 정의는 `evidence_link_id`로 갱신됨 |
| 재실행 | 변경 재실행·되돌리기 재실행 모두 변경 없음, 되돌린 뒤 재변경 가능 |
| 등록 (패치 SQL) | BNFT·RULE 등록 시 `evidence_link_id` 반환, 상위키가 원문 근거 값과 같음. 재등록은 `ON CONFLICT`로 중복 없음. 없는 원문 근거는 연결하지 않음 |
| 유형별 제약 | CARD 등록(`card_bnft_id` NULL), REL은 관계 키가 있으면 등록되고 없으면 `ck_2`가 차단 |
| 유일성 | `(card_id, evidence_link_id)` 중복은 원문 근거가 달라도 `card_evidence_link_id_key`가 차단. 자연키 중복은 `natural_key`가 차단 |
| 잘못된 상위키 | 물리 FK가 없어 직접 SQL로 넣으면 DB가 막지 않음. 사후 검증 P08이 검출함(6절의 판단 근거) |
| 조회 | `select_card_bnft_evidence`(ONE PICK 11건), 패치한 `neo4j_validation.evidence_links` 57건, 카드 자체 근거 9건이 4컬럼 상위키로 원문과 JOIN |
| Neo4j | 패치한 적재 쿼리가 변경 전 `SELECT *`와 같은 행을 돌려줌 → 그래프 동일, 재적재 불필요 |
| 되돌리기 | 구조·제약·뷰 정의·뷰 결과·`SELECT *` 결과가 처음과 같음 |
| 차단 | 원문 근거 없는 연결, 다른 뷰, 행 타입 함수, 예상과 다른 컬럼, 원문 근거 UNIQUE 없음. 모두 아무것도 바꾸지 않고 중단 |
| 실패 시 | 복사 후 행이 빠지도록 고친 사본은 검증에 실패해 전체 ROLLBACK됨. 승계 키가 틀린 행이 있으면 되돌리기도 차단됨 |
| 설계 원본 | 패치한 V7 DDL로 새로 만든 테이블이 변경 스크립트 결과와 컬럼 순서·제약이 같음 |

시험하지 못한 것: Supabase 이벤트 트리거(PGlite에 없음. `ensure_rls`는 public 스키마만 대상이라 영향 없음), 다른 세션의 잠금 대기, 실제 DB(17.11)에서의 실행.

## 6. 복합 FK 도입 검토

검토 대상: `FOREIGN KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id) REFERENCES card_source_evidence (card_doc_id, page_no, card_doc_chunk_id, evidence_id)`

| 관점 | FK 도입 | 논리 관계 유지 (현재) |
|---|---|---|
| 정합성 | 승계 키가 실제 원문 근거와 다르거나 원문이 없으면 DB가 거부한다 | 등록 SQL이 원문 근거에서 키를 읽어 넣어 프로그램 경로는 안전하다. 직접 SQL·이관 스크립트는 막지 못하며, 사후 검사(P08)와 정합성 뷰로 찾는다 |
| 프로젝트 정책 | 스키마 전체 물리 FK 0개 정책과 `v_card_integrity_issue`("물리 FK가 없으므로 게이트로 검증")의 전제가 바뀐다 | 정책과 일치 |
| 등록 | 정상 경로는 그대로 통과한다. 원문 근거 행에 공유 잠금이 걸린다 | 변화 없음 |
| 삭제 | 원문 근거 삭제 전에 연결을 먼저 지워야 한다(RESTRICT). CASCADE를 정하면 원문 삭제가 연결 삭제로 번진다 | 원문을 지우면 고아 연결이 남고 게이트가 잡는다 |
| 재적재·복구 | 원문 근거 → 연결 순서를 지켜야 한다. 원문 근거 테이블 재생성(이번 컬럼 순서 변경 같은 작업)은 FK를 먼저 풀고 다시 만들어야 한다. 기존 이관·롤백 SQL(V7↔V6 등)도 순서 점검이 필요하다 | 순서 제약 없음 |
| Neo4j | 영향 없음 | 영향 없음 |

**판단: 이번에는 도입하지 않는다(승인 필요 사항).**

- **이유:** 정상 등록 경로는 이미 키를 원문에서 가져온다. 물리 FK는 프로젝트 정책 전체를 바꾸는 결정이고, 원문 근거 재생성·복구 절차에 제약을 만든다.
- **대안:** 정합성 뷰에 "승계 키가 원문 근거와 다른 연결" 게이트(P08과 같은 조건)를 추가하는 방안을 권한다. 뷰 정의를 바꾸는 일이라 이번 범위에서는 하지 않았다.
- **도입 조건:** FK를 넣기로 하면 기존 데이터는 이미 일치하므로(P08=0) `ADD CONSTRAINT ... NOT VALID` 후 `VALIDATE CONSTRAINT`로 추가할 수 있다.

## 7. 프로그램 영향과 준비한 수정 (승인 후 적용)

패치는 `cel_patch.py`(작업 스크립트) 하나로 적용하며, 7개 파일에 걸친다. 1단계에서는 사본에만 적용해 시험했다.

| 파일 | 수정 | 이유 |
|---|---|---|
| `payment_card/db_pipeline/common_benefit_repository.sql` `insert_evidence_link`, `insert_rule_evidence_link` | `INSERT ... SELECT`로 원문 근거에서 상위키 3개를 읽어 넣고 `RETURNING evidence_link_id` | 새 NOT NULL 컬럼, 이름 변경. 원문이 없으면 연결하지 않음 |
| `payment_card/db_pipeline/neo4j_dry_run.py:109` | `SELECT *` → 기존 9개 컬럼 명시, `evidence_link_id AS ev_link_id` | Neo4j 관계 속성 이름(`ev_link_id`)과 원본 JSON을 그대로 유지해 재적재 없이 그래프와 일치 |
| `payment_card/db_pipeline/neo4j_validation.sql` `evidence_links` | `l.evidence_link_id AS ev_link_id` | 위와 같은 매핑 |
| `payment_card/tests/test_v7_sql_files.py:84` | 기대 PK를 6컬럼 PK와 `UNIQUE (card_id, evidence_link_id)`로 | 설계 변경 |
| `sql/db_pipeline_schemaV7_draft.sql` | 테이블 정의·주석·시퀀스 주석, 정합성 뷰의 `l.ev_link_id` 4곳 | 설계 원본 동기화 |
| `sql/db_pipeline_schemaV7_draft.dbml` | 테이블 컬럼·PK·UNIQUE, 원문 근거 Ref를 4컬럼 논리 관계로 | ERD 동기화 |
| `sql/db_pipeline_card_source_evidence_pk_inheritance_precheck.sql` | 원인 조회의 `l.ev_link_id` 2곳 | 컬럼 이름 변경 |

Python 서비스(`product_benefit_service.py:85-89`)는 `EVIDENCE_ID`만 넘기고 반환값을 쓰지 않아 수정하지 않는다. 그 밖에 수정이 필요 없는 부분:
- **CARD·REL 연결 등록:** 이를 등록하는 실행 코드는 없다. 기존 CARD 9건은 이관 SQL로 들어갔다.
- **조회 SQL:** `embedding_repository.select_card_bnft_evidence`, `common_benefit_repository`의 CARD 근거 조회는 `ev_link_id`를 쓰지 않는다.
- **GraphRAG A/B/C와 Streamlit:** 근거를 Neo4j(A/C)나 위 조회 SQL(B)로 읽어 영향이 없다.

적용 후 갱신할 문서:
- `docs/guide/CARD_DATA_REGISTRATION_VALIDATION_DETAIL.md:110`: 연결 등록 시 상위키 승계 설명 추가
- `docs/neo4j/Neo4j_DF_ERD_속성상세_설명.md`: Neo4j 관계 속성 `ev_link_id`는 그대로라 변경하지 않음

**Neo4j 구조 변경은 이번에 하지 않는다.** 관계 속성을 `evidence_link_id`로 바꾸려면 재적재와 함께 다음을 바꿔야 한다: `neo4j_load_draft.py:92`, `neo4j_validation.cypher:80`, `neo4j_validate.py:21`, 시험, ERD 문서. 별도 작업으로 권한다.

## 8. 2단계 (승인 후) 절차

1. 접속 대상 확인: PostgreSQL 17.11, DB `postgres`, 스키마 `db_pipeline`. 문서에 개발/공유 Supabase로 함께 기록된 대상이다.
2. 새 백업 생성과 복구 확인: 연결·원문 근거 행, 테이블·뷰 정의.
3. `_precheck.sql`로 C01~C14 통과를 확인하고 I01~I06을 기록한다.
4. `db_pipeline_card_evidence_link_pk_inheritance.sql`을 1회 실행한다. 실패하면 ROLLBACK하고 재시도하지 않는다.
5. `_postcheck.sql`로 P01~P10 통과와 I01~I06 동일을 확인한다.
6. 프로그램·설계 패치를 적용하고, 카드 테스트 전체, `neo4j_validate`(재적재 없이 `ok: true` 기대), 조회 SQL을 확인한다.

**되돌리기:** `_rollback.sql`을 실행해 원래 구조로 되돌린 뒤 같은 패치를 역적용한다. 저장소 파일은 Git으로 되돌린다.

## 9. 적용 결과 (2026-11-03, 개발 Supabase)

| 단계 | 결과 |
|---|---|
| 승인 | 사용자 승인: 적용, 복합 FK 없음 |
| 백업 | `src/data/backup/pre_card_evidence_link_pk_inheritance_20261103/backup.json` (연결 57행, 원문 근거 35행, 연결 테이블 정의·제약·인덱스·주석, 시퀀스 주석, 뷰 2개 정의). 이 파일만으로 복원해 지문이 같음을 확인 |
| 사전 검증 | C01~C14 통과. I01=57, I02=`5d61e2d4f0da12be237b9f30af6f2f0f`, I03=BNFT 37·CARD 9·RULE 11, I04=9, I05=`evidence_not_approved=35`, I06=원문 근거 35건 `9ef45cf7…` |
| 적용 | 1회 실행, 재시도 없음. `근거 연결 PK 승계 완료. 연결 57건 … PK 6컬럼, UNIQUE(card_id, evidence_link_id), 제약 5개, 인덱스 2개, 뷰 2개 복원` |
| 사후 검증 | P01~P10 통과, I01~I06 적용 전과 동일. 유형별 JOIN: BNFT 37/37, CARD 9/9(혜택 ID NULL 9), RULE 11/11. 임시 객체 잔여 0 |
| 뷰 | 두 뷰의 소유자·주석 동일. 정의는 `l.ev_link_id`가 `l.evidence_link_id`로 바뀐 것 외에 동일 |
| 프로그램 | 7절의 패치 7개 파일 적용. `CARD_DATA_REGISTRATION_VALIDATION_DETAIL.md:110`에 상위키 승계 설명 추가 |
| 회귀 시험 | 카드 시험 242건 + 126건 통과(1건 skip, Neo4j 실제 조회 포함). 오프라인 전체 시험 HEAD 대비 새 실패 0 |
| Neo4j | 패치한 적재 코드로 `neo4j_validate` 읽기 전용 대조 `ok: true` (노드 124·관계 196 차이 0, 근거 연결 57=57). 재적재하지 않았다 |
| 조회 | 혜택 5건 근거 조회, 근거 연결 대조 57건, 최근 추출 근거 조회 정상 |

남은 사항
- 패치한 등록 SQL(`insert_evidence_link`, `insert_rule_evidence_link`)은 격리 DB에서만 실행했다. 실제 DB에 시험 데이터를 남기지 않기 위해 실제 등록은 하지 않았다.
- Neo4j 관계 속성은 `ev_link_id` 그대로다. 이름을 맞추려면 7절의 별도 작업과 재적재가 필요하다.
- 정합성 뷰에 승계 키 불일치 게이트를 추가할지는 별도 결정 사항이다(6절).
