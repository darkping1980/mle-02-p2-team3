# 인계: `stg_normalized_item` 제거·계산 구조 단순화 (2026-11-03, 집 PC 야간 작업 반영)

## 1. 현재 상태 요약

| 구분 | 상태 |
|---|---|
| 소스: 정제본 쓰기·읽기 제거, 원본(`stg_raw_item`)에서 재생성 | **완료**(학원 PC, 커밋 6893be0) |
| 등록 검증 수정(근거 공유·등급 비교·TARGET 근거·USD 한도) | **완료**(학원 PC) |
| 프롬프트 EXTRACT_V8 / 스키마 EXTRACT_SCHEMA_V3 | **완료**(학원 PC). 실제 LLM 재추출은 **미실행**(유료, 승인 필요) |
| 정리 SQL에 `stg_normalized_item` 삭제·CHECK 교체·`seq_card_excl_item` 삭제 추가, 복구 SQL 확장 | **완료**(집 PC) |
| **Supabase `db_pipeline` 실DB 적용** | **완료·COMMIT**(집 PC, 사용자 승인). 23/23 검증 통과, `live_apply_result_20261103.txt` |
| V7 설계 DDL·DBML·공통코드 seed/설명 SQL 동기화 | **완료**(집 PC) |
| Neo4j 재적재(1차, 재추출 전) | **완료**(집 PC). 214 노드·277 관계, PostgreSQL과 차이 0, `neo4j_reload_result_20261103.txt` |
| Stage 5(데이터 초기화·재등록) | **미실행**(사용자 승인 필요) |

## 2. 설계 결정(검증 근거)

- 정제본에만 있는 업무 정보는 없다. 실행 20건, 대표 혜택 342건을 원본에서 다시 만들어 비교했고 342/342가 같았다(학원 PC).
- 통합 정보는 `stg_parent_card_extr_stg_id`(중복 행 → 대표 행)와 `stg_sql_check_cd`로 보존한다. 충돌·적용 대상·조건 연결은 `normalize_stored_run`이 다시 계산한다.
- 저장된 `CONTRACT_INVALID`는 계약이 바뀌었으므로 `effective_check_cd`로 다시 판정한다. 값·근거 검증 코드는 저장값을 따른다.
- 새 CHECK `card_extr_stg_check1`: 승인 행은 `stg_sql_check_cd='OK'`·근거 위치·근거 문장이 필요하다(정제본 존재 조건만 뺐다).
- 정제본 값 350건은 Git에 넣지 않는다. 백업 폴더의 `restore_stg_normalized_item.sql`로만 복구한다.

## 3. 오늘(집 PC) 수정한 파일

- `docs/schema_cleanup/tools/`
  - `gen_cleanup_sql.py`: 학원 PC 절대경로 제거(파일 위치 기준), 최신 백업 자동 선택·백업과 입력 일치 확인,
    정제본 지문·의존 객체·CHECK 정의 사전 조건, 보존 컬럼 지문(15개 테이블) 사전·사후 비교, 정제본 컬럼 삭제와 CHECK 교체,
    `seq_card_excl_item` 삭제·복구, `rule_priority`·`calc_params` 형식 검사 제거, `v_card_cond_atom`을 원래 표기로 복구(아래 5절)
  - `backup_db_pipeline.py`(신규): 읽기 전용 전체 백업과 실DB 행 단위 대조(`--verify`), 정제본 복구 SQL 생성
  - `apply_cleanup.py`(신규): precheck / rehearse(항상 ROLLBACK) / apply(검증 통과 시에만 COMMIT) / postcheck
  - `renormalize_run.py`: 실제 `CommonBenefitService.register_run`을 READ ONLY로 시뮬레이션(쓰기 SQL 가로채기)
- `sql/db_pipeline_calc_structure_cleanup.sql`, `..._rollback.sql`: 생성기로 다시 만들었다.
- `sql/db_pipeline_schemaV7_draft.sql`·`.dbml`, `db_pipeline_common_code_seedV7.sql`·`descV7.sql`: 적용 후 구조로 동기화
- `tests/test_v7_sql_files.py`: 계산 구조가 "없어야 한다"는 계약으로 갱신. `tests/test_live_registration.py`, `sql/tools/v7_verification/live_common_service_rollback.py`: 정제본 컬럼·계산 키 제거
- 문서: `payment_card/db_pipeline/README.md`, `docs/db_dictionary/card_ai_call.md`, `docs/schema_cleanup/README.md`, `v7_ddl_dbml_change_proposal.md`
- `.gitignore`: `/src/data/backup/pre_calc_cleanup_*/`

## 4. 테스트 결과(집 PC, 실제 실행분만)

| 테스트 | 결과 |
|---|---|
| `pytest payment_card/tests`(Mock LLM 추출 포함) | 421 passed, 1 failed(기존 `test_answer_text::test_unresolved_tier_cannot_be_decided_in_natural_text`, 시작 시점에도 실패), 18 skipped |
| `RUN_NEO4J_INTEGRATION=1` GraphRAG·Neo4j 읽기(Mock LLM) | 179 passed(실 Neo4j 읽기 16건 포함). 그래프는 재적재 전 상태 |
| V7 DDL+seed+설명 SQL 실행(PGlite, 문법 확인용) / DBML 파싱 | 통과 / 13테이블·18관계 |
| 실DB 적용 트랜잭션(`apply_cleanup.py apply`) | 23/23 PASS → COMMIT |
| COMMIT 후 `postcheck`(읽기 전용) | 6/6 PASS |
| Run 31 등록 시뮬레이션(읽기 전용) | 후보 53 → 등록 가능 45 / REVIEW 8(VALUE_PARSE_DIFF 5, 기간 3). 인계 기대값(29 + 등급 11 + 근거 공유 5 = 45)과 같음 |
| 건너뜀 | `test_live_registration` 2건(유료 임베딩·실DB 쓰기), `test_payment_card` 1건(별도 시험 DB URL 없음) |

## 5. 리허설 불일치 2건(해결)

1. 복구 후 뷰 정의 차이: 출력된 뷰 정의를 다시 만들면 `v_card_cond_atom` UNION 2·3번째 가지의 상수 열이 `AS text` 별칭을 얻는다(복구 SQL 문제).
   원래 표기(캐스트 없는 상수)로 생성기를 고쳤고, 실DB 적용 트랜잭션 안의 복구 실증에서 정의가 정리 전과 같았다.
2. 다른 스키마 지문 차이: 정리 SQL의 `SET LOCAL search_path = pg_catalog` 이후 `format_type`이 `vector` → `extensions.vector`로 바뀐 검사 방법 문제.
   READ ONLY에서 재현했고, 같은 search_path 기준 비교 + `pg_locks`(이 트랜잭션이 잠근 다른 스키마 객체) 검사로 바꿨다. 둘 다 통과.

## 6. MP004 확인(실DB 읽기, run 20261103_000031)

- USD 한도: 원본 `limit_raw_txt`에 'USD 30'(Agoda·Rakuten), 'USD 50', 'USD 100'이 보존돼 있다. 이 실행은 V5 추출이라 저장 검증 코드
  VALUE_PARSE_DIFF가 남아 REVIEW다. USD 한도 OK 여부는 EXTRACT_V8 재추출 후 확인한다(단위 테스트 `limit_values_in("최대 USD 100")` 통과).
- 8%·6%: `value_num` 8·6, `value_unit_cd` PERCENT 보존. Mastercard 등급: `Mastercard Platinum`·`Platinum04` 후보가 등록 가능으로 바뀌었다.
- 예약·숙박·여행 기간: 원본 `validity_period_txt`에 개별 보존. 하나로 해석할 수 없는 3건은 REVIEW(검증 완화 없음).
- 근거 공유 5건 등록 가능, 계산 방법 없는 규칙 INSERT 가능(실DB, SAVEPOINT 되돌림), 값 불일치 5건은 계속 검출.

## 7. 복구 절차(COMMIT 이후 필요 시)

1. `python src/card_benefit/docs/schema_cleanup/tools/backup_db_pipeline.py`로 현재 상태를 먼저 백업한다.
2. `sql/db_pipeline_calc_structure_cleanup_rollback.sql` 실행(구조·JSON·공통코드, 정제본 컬럼은 CHECK NOT VALID).
3. `src/data/backup/pre_calc_cleanup_20261103_224545/restore_stg_normalized_item.sql` 실행(정제본 350건, 지문 확인 후 VALIDATE).
   - 적용 후 새로 승인(AUTO/MANUAL_APPROVED)한 행이 있으면 3단계의 VALIDATE가 실패한다. 그때는 해당 행을 먼저 검토한다.
4. 이 순서는 적용 트랜잭션 안에서 실DB로 실증했다(데이터·정의가 백업과 같음).

## 8. 내일(학원 PC) 남은 작업

1. `git pull` 후 `pytest payment_card/tests` 실행(기대: 기존 실패 1건).
2. Neo4j 1차 반영은 완료했다(재추출 전 데이터). Stage 5 재등록 후 같은 명령으로 다시 적재한다.
   고아 문서 `card_doc 20261103_000012`(JCB JP002)는 PostgreSQL에서 공통서비스 연결을 정한 뒤 해소된다(Neo4j에서 지우지 않음).
3. (승인 후) EXTRACT_V8 실제 추출은 별도 실행 ID로 한 문서(MP004, doc 20261103_000014)만 실행해 USD 한도 OK를 확인한다.
4. (승인 후) Stage 4~6 데이터 초기화·재등록. 공통 등록은 `register_run` → `apply_run`.
5. `test_live_registration.py`의 시험 원본을 추출 스키마 형식으로 바꾼 뒤 실행(유료 임베딩 포함).
6. ERD 이미지 재생성(DBML 반영분).
7. 선택: 실DB 공통코드 설명(`common_cd_desc`)의 VALUE_UNIT 등 일부 문구는 삭제한 코드 그룹(PAYOUT_UNIT 등)을 언급한다.
   갱신된 `db_pipeline_common_code_descV7.sql`을 다시 실행하면 맞춰진다(이번 적용 범위 밖이라 실행하지 않음).

## 9. PDF·MD

이번 작업에는 PDF 변환 MD가 필요하지 않아 재생성하지 않았다(코드·SQL·실DB 검증만으로 완료).
