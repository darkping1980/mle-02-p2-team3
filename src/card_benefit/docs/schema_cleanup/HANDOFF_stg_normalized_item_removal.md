# 인계: `stg_normalized_item` 제거·계산 구조 단순화 (2026-11-03)

## 1. 현재 상태 요약

| 구분 | 상태 |
|---|---|
| 소스: 정제본 쓰기·읽기 제거, 원본(`stg_raw_item`)에서 재생성 | **완료**(단위 테스트 통과) |
| 등록 검증 수정(근거 공유·등급 비교·TARGET 근거·USD 한도) | **완료**(단위 테스트 통과) |
| 프롬프트 EXTRACT_V8 / 스키마 EXTRACT_SCHEMA_V3(계산 방법·지급 단위 제거) | **완료** |
| `stg_normalized_item` 컬럼 **실제 삭제** | **미실행**. 공유 DB와 로컬 DB 모두 컬럼이 그대로 있다. 코드는 컬럼을 쓰지 않으므로 컬럼이 있어도 동작한다 |
| 컬럼 삭제 DDL·복구 SQL 생성 | **미완료**(생성기 확장 전) |
| PGlite 격리 DB 삭제·복구·등록 통합 테스트, GraphRAG 실DB 회귀 | **미실행** |

## 2. 설계 결정(검증 근거)

- 정제본에만 있는 업무 정보는 없다. 실행 20건, 대표 혜택 342건을 원본에서 다시 만들어 비교했고 342/342가 같았다. 통합 출처 수 불일치 0건, 실패 0건(읽기 전용, `scratchpad/equivalence_check.py`).
- 통합 정보는 `stg_parent_card_extr_stg_id`(중복 행 → 대표 행)와 `stg_sql_check_cd`로 보존한다.
  - 대표 행은 검증 코드가 있고, 같은 종류의 부모가 없는 행이다.
  - 충돌·적용 대상·조건 연결은 `normalize_stored_run`이 다시 계산한다.
- 저장된 `CONTRACT_INVALID`는 계약이 바뀌었으므로 `effective_check_cd`로 다시 판정한다.
  - 값·근거 검증 코드(NO_EVIDENCE, VALUE_PARSE_DIFF 등)는 저장값을 그대로 따른다.
  - 대상 연결 확인 여부를 알 수 없어 최선의 결과도 LINK_REVIEW다. 따라서 자동 승인은 되지 않는다.
- 혜택이 자기 기간을 가진 경우(7건)는 계속 REVIEW다. 검증을 완화하지 않았다.

## 3. 수정한 파일

- `payment_card/db_pipeline/`
  - `extraction_schema.py`: RuleItem에서 calc_method_cd·payout_unit_cd를 뺐다. 이전 응답의 키는 무시한다.
  - `extraction_service.py`
    - 프롬프트 13·14를 고치고 V8로 올렸다. 정제본을 저장하지 않는다.
    - `merge_items`, `StoredCandidate`, `effective_check_cd`, `normalize_stored_run`을 추가했다.
    - USD 한도 대조용 `foreign_amounts_in`, `limit_values_in`을 추가했다.
    - 재사용 판정에서 정제본 조건을 뺐다.
  - `extraction_repository.py/.sql`
    - `update_stg_merge`에서 정제본을 뺐다.
    - `select_contract_check`, `select_run_compare`를 지우고, `select_merged_*`는 원본 기준으로 고쳤다(statement 19개).
  - `common_benefit_repository.sql`
    - `list_run_items`를 추가했다.
    - 후보·이전판·근거 조회를 원본 + 대표 행 조건으로 바꿨다.
  - `embedding_repository.sql`: 공통 혜택 근거 조회를 원본 bnft_nm + 대표 행 조건으로 바꿨다.
  - `common_benefit_service.py`
    - `CommonBenefitRepository.stored_run/attach_normalized`를 추가했다.
    - `grade_key`를 추가했다(브랜드 접두어와 선택서비스 번호 01~04 제거).
    - `_evidence_ids`를 고쳤다.
      - BNFT·TARGET·RULE이 같은 인용을 쓰는 것은 규칙이 1개일 때만 허용한다.
      - 서로 다른 RULE끼리, APPLICABILITY·LIMIT과 공유하는 것은 계속 막는다.
      - TARGET은 혜택 근거로 본다.
  - `product_benefit_service.py`, `auto_approval_policy.py`, `common_auto_pipeline.py`: 원본에서 재생성한 값(`normalized`, `check_cd`, `source_cnt`, `conflicts`)을 쓴다.
- 테스트: `test_extraction.py`(추출 통합 = 등록 재생성 동등성 테스트 포함), `test_common_benefit.py`, `test_auto_approval_policy.py`, `test_common_auto_pipeline.py`, `test_benefit_embedding.py`

## 4. 테스트 결과

- `src/card_benefit`에서 `pytest payment_card/tests`를 실행했다: **421 passed, 1 failed, 18 skipped**.
- 실패 `test_answer_text.py::test_unresolved_tier_cannot_be_decided_in_natural_text`는 HEAD에서도 실패하던 것으로, 이번 변경과 무관하다.
- 실DB가 필요한 테스트(skip 18)와 GraphRAG 실DB 회귀(`RUN_NEO4J_INTEGRATION=1`)는 실행하지 않았다.

## 5. 삭제 DDL·복구 SQL

- 기존 계산 구조 정리 SQL은 다음 두 파일이다. 둘 다 `stg_normalized_item`을 아직 다루지 않는다.
  - `sql/db_pipeline_calc_structure_cleanup.sql`
  - `sql/db_pipeline_calc_structure_cleanup_rollback.sql`
- 생성기는 `docs/schema_cleanup/tools/gen_cleanup_sql.py`, 격리 테스트는 `tools/cleanup_test.mjs`(PGlite)다.
- 추가해야 할 내용:
  1. 정리 SQL
     - `ALTER TABLE db_pipeline.card_extr_stg DROP CONSTRAINT card_extr_stg_check1;`
     - 정제본 조건을 뺀 새 CHECK를 추가한다: `stg_status NOT IN ('AUTO_APPROVED','MANUAL_APPROVED') OR (stg_sql_check_cd='OK' AND 근거 위치·문장 조건)`.
     - `ALTER TABLE db_pipeline.card_extr_stg DROP COLUMN stg_normalized_item;`
     - 사전 조건: 정제본 값의 건수·md5 지문이 생성 시점과 같을 때만 진행한다(복구 데이터 일치 보장).
  2. 복구 SQL
     - 컬럼을 추가한다(jsonb, 주석 '정제 항목'). 컬럼은 테이블 맨 뒤에 붙는다.
     - 값을 UPDATE로 되살리고, 원래 CHECK를 복구한다.
  3. 값 원본
     - `src/data/backup/pre_calc_cleanup_20261103/postgres_db_pipeline.json`의 `card_extr_stg.stg_normalized_item`(375행 중 350행 non-null)을 쓴다.
     - 적용 직전에 백업을 다시 떠서 생성기를 재실행한다.
- 뷰·함수 중 이 컬럼을 참조하는 것은 없다(카탈로그 확인). 참조하는 것은 CHECK `card_extr_stg_check1`과 컬럼 주석뿐이다.
- 기타 남은 참조(문서·과거 스키마·도구)도 함께 정리한다.
  - `test_live_registration.py`(실DB, skip)
  - `sql/tools/v7_verification/live_common_service_rollback.py`
  - `docs/schema_cleanup/tools/renormalize_run.py`
  - V7 설계 DDL/DBML(`v7_ddl_dbml_change_proposal.md`에 반영할 것)

## 6. 공유 Supabase DB 반영 전 확인

1. 격리 DB에서 정리 → 검증 → 런타임 SQL → 복구 → 정의·데이터 비교가 모두 통과해야 한다.
2. 적용 직전에 백업하고, 정제본 지문을 비교한다.
3. 이번 코드가 먼저 배포되어 있어야 한다. 구 코드는 컬럼을 읽으므로 컬럼 삭제 후 실패한다.
4. 공통서비스 데이터와 추출 이력 V3~V5는 보존한다. DROP CASCADE는 쓰지 않는다.
5. 사용자 승인 후에만 실행한다.

## 7. Stage 5 등록까지 남은 작업

1. 위 DDL·복구 SQL 생성 및 PGlite 격리 테스트를 한다.
   - `scratchpad/pglite_local` 소켓 서버로 공통 `register_run`/`apply_run`을 실행한다.
   - 상품 등록은 트랜잭션 안에서 실행한다.
2. 기존 실행 31을 재등록 시뮬레이션한다. 기대값:
   - 등급 정규화로 11건, 근거 공유로 5건이 추가 등록 가능해야 한다.
   - VALUE_PARSE_DIFF 5건은 저장 코드가 남아 재추출 전까지 REVIEW로 남는다.
3. GraphRAG 회귀(`RUN_NEO4J_INTEGRATION=1`, A/B/C)를 실행한다.
4. Stage 4~6(데이터 초기화·재등록)은 사용자 승인 후 진행한다.

## 8. EXTRACT_V8 추출·등록 테스트 절차

1. 무료 Mock LLM으로 `ExtractionService.run(doc_id, card_id=None)`을 실행한다(단위 테스트의 FakeLlm 방식). 유료 호출은 승인 후에만 한다.
2. 실행 행을 `list_run_items`로 읽어 `normalize_stored_run`으로 확인한다. `CommonBenefitService.register_run(run_id, identities)` → `apply_run`의 Decision 사유 분포를 기록한다.
3. 실제 LLM 추출은 승인을 받은 뒤 한 문서(Mastercard Platinum, doc 20261103_000014)만 실행한다. USD 한도가 OK로 나오는지 확인한다.

## 9. 다음 세션 실행 순서

1. `git log -1`로 이 커밋을 확인하고 `pytest payment_card/tests`를 실행한다(기대: 실패 1건, 기존 실패).
2. `gen_cleanup_sql.py`에 5절의 제약·컬럼 삭제·복구를 추가하고 SQL을 다시 생성한다.
3. `cleanup_test.mjs`에 컬럼 삭제·복구 검사를 추가하고 실행한다.
4. PGlite 소켓으로 등록 통합 테스트를 하고, GraphRAG 회귀를 실행한다.
5. README, V7 DDL/DBML 변경안, 이 문서를 갱신한다.

## 10. 커밋

- 커밋 메시지: `refactor: GraphRAG 카드 혜택 추출·검증·등록 구조 단순화`
- 해시는 커밋 후 `git log -1 --format=%H`로 확인한다(이 문서는 그 커밋에 포함된다).
