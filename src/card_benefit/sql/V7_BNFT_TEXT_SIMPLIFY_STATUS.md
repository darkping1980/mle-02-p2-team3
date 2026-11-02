# V7 혜택·한도 TEXT 단순화 작업 상태

`card_limit_pool`, `card_bnft_rule_pool`을 제거하고 혜택 설명과 한도를 `card_bnft`의 TEXT 컬럼으로 통합한다.

**실제 Supabase에는 DDL/DML을 실행하지 않았다.** 읽기 전용 조회만 했다. DROP은 사용자가 DBeaver에서 직접 실행한다. Git 커밋도 하지 않았다.

| 단계 | 상태 |
|---|---|
| V7 DDL·프로그램 의존성 분석 | 완료 |
| 이관·복구·사전·사후 검증 SQL | 완료 |
| 실제 DB 사전 검증(읽기 전용) | 완료, 21개 항목 PASS |
| 격리 이관·재실행·복구·재이관 시험 | 완료 |
| Python·Cypher 수정과 오프라인 테스트 | 완료 |
| 실제 DB 이관 | **사용자 실행 대기** |
| 사후 검증 SQL 실행 | **이관 후 사용자 실행** |
| Neo4j 재적재 | **미실행**, 별도 승인 필요 |
| 공통코드 정리 | **미실행**, 결정 필요 |

## 실행 순서 (DBeaver, 스크립트 전체 실행 Alt+X)

1. `db_pipeline_v7_bnft_text_precheck.sql`: 첫 결과에서 C99가 PASS인지 확인한다.
2. `db_pipeline_migration_v7_bnft_text.sql`: 가드 실패 시 아무것도 바뀌지 않는다.
3. `db_pipeline_v7_bnft_text_postcheck.sql`: C99가 PASS인지 확인한다.
4. 프로그램 변경을 커밋하고 배포한다.
5. 별도 승인 후 Neo4j를 비우고 재적재한다. 기대값은 98노드, 165관계다.

복구: `db_pipeline_migration_v7_bnft_text_rollback.sql` 실행 후 프로그램도 이전 커밋으로 되돌린다.

## 삭제 객체

| 종류 | 대상 |
|---|---|
| 테이블 | `card_limit_pool`, `card_bnft_rule_pool` |
| 뷰 | `v_card_limit_tier`, `v_card_rule_pool` |
| 시퀀스 | `seq_card_limit_pool` |
| 함수 | `fn_valid_tier_list(jsonb)` |
| 컬럼 | `card_evidence_link.pool_id` |
| 행 | `card_evidence_link`의 POOL 근거 9건 |
| 인덱스 | 두 테이블의 PK 인덱스(테이블과 함께 삭제) |

## 수정 객체

| 객체 | 변경 |
|---|---|
| `card_evidence_link` | 자연키에서 `pool_id` 제거(이름 유지), `ck_2`에서 POOL 대상 제거 |
| `fn_valid_relation_list` | `trigger_pool_id` 필수 조건 제거, 해당 키 거부 |
| `v_card_bnft_rel` | `trigger_pool_id` 컬럼 제거 |
| `v_card_cond_atom` | POOL_TIER 분기, `pool_id`, `item_key` 컬럼 제거 |
| `v_common_cd_usage` | 두 테이블 사용처 6행 제거 |
| `v_card_integrity_issue` | 풀 게이트 6종 제거, POOL·TIER 검사 제거, `bnft_txt_without_evidence` 추가 |

## 데이터 이관 상태

| 항목 | 전 | 후 |
|---|---:|---:|
| 테이블 / 뷰 / 시퀀스 / 함수 | 16 / 10 / 10 / 8 | 14 / 8 / 9 / 7 |
| `card_evidence_link` | 66 | 57 |
| `card_bnft` | 5 | 5, TEXT 포함 모든 값 동일 |
| TEXT 채워진 혜택 | 4 | 4 |
| TEXT NULL 혜택 | 1 (CARD_ID=5 Visa 컨시어지) | 1 |
| 정합성 게이트 | `evidence_not_approved` 35 | 동일 |
| 검증 상태 | 전부 `PENDING_REVIEW` | 동일 |

백업 `db_pipeline_backup`의 4개 테이블은 유지한다. 이관 시 `seq_card_limit_pool_20261102`가 추가된다.

## 검증 결과

| 시험 | 대상 | 결과 |
|---|---|---|
| 사전 검증 21항목 | 실제 DB, 읽기 전용 | 전부 PASS, POOL 근거 TOTAL 9 / LINKED 9 / MISSING 0 |
| 실제 DB 카탈로그와 `bdb94bc` DDL | 실제 DB, 읽기 전용 | TEXT 컬럼 2개 외 차이 없음 |
| TEXT 세그먼트 16개 원문 대조 | 실제 DB, 읽기 전용 | 전부 연결 원문에 있음 |
| 이관, 새 V7과 카탈로그 비교 | PGlite 16.4, 실제 행 복사본 | 차이 0 |
| 재실행, 복구, 복구 재실행, 재이관 | 같음 | 구조·데이터 차이 0 |
| 가드 음성 시험 | 같음 | 9종 모두 중단, 무변경 |
| V6 → V7 → 단순화 → 복구 | PGlite, 합성 행 | 통과 |
| Python 테스트 | 오프라인 | 332 통과, 13 건너뜀(실제 DB·Neo4j 통합 시험 포함) |
| `migrate_test.mjs`, `live_common_service_rollback.py` | 없음 | **미실행.** 각각 V6 원본 행, 이관 후 실제 DB가 필요하다 |
| Neo4j 실제 적재, LLM 답변 | 없음 | **미실행.** 그래프 변환은 실제 행으로 98/165 확인 |

PGlite는 PostgreSQL 16.4이고 실제 DB는 17.11이다. 이관 SQL은 실제 DB에서 한 번도 실행되지 않았다.

## 남은 위험과 결정 사항

1. **수치 비교 불가:** 한도가 TEXT가 되어 `월 한도 큰 순` 같은 SQL 정렬·집계가 불가능하다. 답변 검증은 TEXT의 값을 읽어 유지했다.
2. **구조 정보 소실:** `pool_scope_cd`, `aggregation_key_cd`, 규칙별 풀 대응은 현재 테이블에서 사라지고 백업에만 남는다. 현재 데이터는 전부 `BENEFIT` 범위이고 공유 풀과 규칙별 차이가 없다(S01, S02 PASS). `CARD_MEMBER`는 원래 가정값이다. 영역+통합 한도 같은 카드는 TEXT로만 표현된다.
3. **순서 의존:** 코드는 이관 후 구조 기준이다. 이관 전에는 `neo4j_dry_run`이 POOL 근거에서 중단하고, 이관 후 옛 코드는 풀 테이블이 없어 실패한다. 이관과 배포를 함께 한다.
4. **Neo4j:** 재적재 전 그래프에는 `limit_text`가 없어 한도 조회가 빈 결과를 낸다. 로더는 기존 키가 스냅샷과 다르면 중단하므로 `df_one_pick_style`을 먼저 비우고 적재한다.
5. **공통코드 잔존:** `POOL_ROLE`, `LIMIT_AGG`, `EV_SUBJECT.POOL`, `EV_ITEM.TIER`는 사용처가 없어지고, `LIMIT_SCOPE/PERIOD/UNIT`은 추출 staging만 쓴다. 지침상 다른 테이블을 유지하므로 지우지 않았다. `db_pipeline_common_code_descV7.sql`의 해당 설명은 이전 구조를 가리킨다.
6. **staging:** `card_extr_stg`의 `limit_list`, `pool_refs`는 후보 JSON이라 유지했다. 최종 저장 시 `pool_refs`를 제거한다.
7. **미갱신 문서:** `src/card_benefit/docs/neo4j/`의 ERD와 `db_pipeline/*.md` 작업 기록은 이전 구조다.
