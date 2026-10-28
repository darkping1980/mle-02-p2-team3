# Recipe PostgreSQL 최종 설계 검토 (11개 테이블)

> **이력 문서.** 2026-10-22 목표 모델 전환 전의 복합 키 11개 테이블 설계 검토이다. 현재 구조는 `recipe_target_schema.sql`·`recipe_table_definition.md`, 전환 기록은 `recipe_target_rebuild_runbook.md`를 따른다.

정의서: `recipe_table_definition.md` · DDL: `recipe_schema_review.sql` · 재생성: `recipe_schema_rebuild.sql`

## 2026-10-22 최종 변경 요약

| 변경 | 이전 | 최종 |
|---|---|---|
| 원본 PK | `rcp_raw (batch_id, rcp_seq)` | `rcp_raw (rcp_raw_id, rcp_raw_seq)`, UNIQUE `(rcp_raw_id, rcp_seq)` |
| 레시피 PK | `rcp (rcp_cat_id, rcp_seq)` | `rcp (rcp_cat_id, rcp_id)`, UNIQUE `(rcp_id)`, `(rcp_seq)` |
| 조리 단계 PK | `(rcp_cat_id, rcp_seq, step_no)` | `(rcp_cat_id, rcp_id, step_no)` |
| 사용 식재료 PK | `(ingr_cat_id, ingr_id, rcp_cat_id, rcp_seq)` | `(ingr_cat_id, ingr_id, rcp_cat_id, rcp_id)` |
| 별칭 PK | `(ingr_cat_id, ingr_id, ingr_als_nm)` | `(ingr_cat_id, ingr_id, ingr_als_id)`, UNIQUE `(ingr_cat_id, ingr_id, ingr_als_nm)` |
| staging PK | `(batch_id, rcp_seq, rcp_ingr_line_no)` | `(rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id)`, UNIQUE `(rcp_raw_id, rcp_raw_seq, rcp_ingr_line_no)` |
| 공통코드 | `cmn_cd (cd_grp, cd)` | `common_code_grp (common_code_grp_id)` + `common_cd (common_code_grp_id, common_cd)` |
| 회차 컬럼명 | `batch_id` | `rcp_raw_id` (`rcp`, `rcp_ingr`도 같은 의미이므로 통일; PK 불포함) |
| 시퀀스 | 4개 | 7개 (`seq_rcp`, `seq_ingr_als`, `seq_rcp_ingr_stg` 추가) |

## 설계 근거

- 원본 레시피 번호 `rcp_seq`는 외부 기관 값이므로 PK에서 내리고 일반 속성 + UNIQUE로 보존합니다. 내부 `rcp_id`가 레시피 정체성을 담당하며, 재실행 시 `rcp_seq`로 기존 `rcp_id`를 찾아 재사용합니다.
- 원본 행은 "어느 회차의 몇 번째 행"으로 식별합니다(`rcp_raw_id`, `rcp_raw_seq`). 같은 회차 안의 원본 번호 중복은 UNIQUE `(rcp_raw_id, rcp_seq)`가 막습니다.
- staging은 원본 행의 자식이므로 `(rcp_raw_id, rcp_raw_seq)`를 승계하고 자체 ID `rcp_ingr_stg_id`를 붙입니다. 재료 등장 순번 `rcp_ingr_line_no`는 일반 속성이며 UNIQUE로 같은 순번 중복 적재를 막습니다.
- 별칭은 자체 ID를 갖고, 같은 표준 식재료 안에서만 이름 중복을 금지합니다. 한 별칭이 여러 식재료를 가리키는 경우 자동 승인 SQL이 대상을 하나로 정할 수 없으므로 승인하지 않습니다.
- 조리 방법은 PK에 포함하지 않는 일반 코드 속성이며 `common_code_grp_id='COOK_MTHD'` 조건과 함께 조인합니다.
- 물리 FK는 두지 않고, 부모 존재·복합 PK 전체 일치·중복을 적재기와 검증 SQL에서 확인합니다.

## 실행 결과 (Supabase `postgres` / `recipe`)

- 2026-10-22 사전 검사: `recipe` 스키마에는 프로젝트 테이블 10개, 시퀀스 4개, 함수 1개뿐이고 외부 FK·view·trigger·RLS 정책·다른 스키마 함수 참조가 없었습니다.
- `recipe_schema_rebuild.sql`을 단일 트랜잭션으로 실행해 기존 10개 테이블(`rcp_raw`, `rcp_cat`, `cmn_cd`, `rcp`, `rcp_step`, `ingr_cat`, `ingr`, `ingr_als`, `rcp_ingr_stg`, `rcp_ingr`)과 시퀀스·함수를 RESTRICT로 삭제하고 최종 11개 테이블을 생성했습니다. 사후 검증(11개 테이블, 7개 시퀀스, FK 0, COMMENT 누락 0) 통과 후 COMMIT했습니다.
- CSV 적재 결과는 `recipe_data_review.sql`로 확인합니다. 원본·정제 1,156건, 조리 단계 6,717건, staging 13,080건, 표준 식재료 275건, 별칭 71건, 사용 식재료 관계 10,428건이며 논리 정합성 검사는 모두 0건입니다.
