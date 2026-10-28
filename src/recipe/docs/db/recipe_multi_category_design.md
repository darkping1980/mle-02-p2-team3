# 레시피 다중 분류 목표 모델 설계 초안

> **이력 문서.** 2026-10-22 목표 모델 전환 전의 다중 분류 설계 초안(최종 DDL에 통합됨)이다. 현재 구조는 `recipe_target_schema.sql`·`recipe_table_definition.md`, 전환 기록은 `recipe_target_rebuild_runbook.md`를 따른다.

상태: 설계 및 DDL 초안. `recipe_multi_category_target.sql`은 **빈 recipe 스키마에 처음부터 생성할 때의 목표 DDL**이며 현행 DB에 실행할 마이그레이션 스크립트가 아니다. 현행 DDL `recipe_schema_review.sql`과 2026-10-22 DB 메타데이터를 대조했다.

## 현행 확인

| 테이블 | 현행 PK | 목표 PK | 변경 |
|---|---|---|---|
| `rcp_raw` | `(rcp_raw_id, rcp_raw_seq)` | 동일 | 없음 |
| `rcp_cat` | `(rcp_cat_id)` | 동일 | 분류 기준 컬럼 추가 |
| `common_code_grp` | `(common_code_grp_id)` | 동일 | 구조 변경 없음 |
| `common_cd` | `(common_code_grp_id, common_cd)` | 동일 | 구조 변경 없음 |
| `rcp` | `(rcp_cat_id, rcp_id)` | `(rcp_id)` | 분류 ID 제거 |
| `rcp_step` | `(rcp_cat_id, rcp_id, step_no)` | `(rcp_id, step_no)` | 레시피 PK만 승계 |
| `ingr_cat` | `(ingr_cat_id)` | 동일 | 없음 |
| `ingr` | `(ingr_cat_id, ingr_id)` | 동일 | 없음 |
| `ingr_als` | `(ingr_cat_id, ingr_id, ingr_als_id)` | 동일 | 없음 |
| `rcp_ingr_stg` | `(rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id)` | 동일 | 원본 행의 자식으로 유지 |
| `rcp_ingr` | `(ingr_cat_id, ingr_id, rcp_cat_id, rcp_id)` | `(ingr_cat_id, ingr_id, rcp_id)` | 두 부모 PK 전체를 승계 |
| `rcp_cat_rel` | 없음 | `(rcp_id, rcp_cat_id)` | N:M 관계 신설 |

현행 `rcp.rcp_id`는 이미 `VARCHAR(20) NOT NULL`, `recipe.fn_get_biz_id('rcp')` 기본값, UNIQUE이고 `rcp_seq TEXT NOT NULL`은 식약처 원본 번호로 별도 UNIQUE이다. `rcp_raw_id`는 최종 반영 원본 수집 회차 ID다. 두 ID를 혼동하지 않는다. 기존 시퀀스 7개와 함수, 원본·식재료 모델, 관리 컬럼, NULL 정책은 목표 DDL에서 유지한다. 현행 물리 FK는 없고 목표에도 만들지 않는다.

현행 추가 인덱스는 `ix_rcp_ingr_rcp_key (rcp_cat_id, rcp_id)`, `ix_rcp_ingr_stg_ingr_key (ingr_cat_id, ingr_id)` 두 개다. 목표에서는 첫 인덱스를 `(rcp_id)`로 바꾸고 `rcp_cat_rel (rcp_cat_id, rcp_id)` 역방향 조회 인덱스를 더한다. 각 PK와 UNIQUE도 인덱스를 생성한다.

읽기 전용 DB 조회 당시 건수는 `rcp_raw` 1,156, `rcp_cat` 6, `rcp` 1,156, `rcp_step` 6,717, `ingr` 275, `rcp_ingr_stg` 13,080, `rcp_ingr` 10,428이었다. `rcp_id` 중복, 단계·식재료 관계의 레시피 부모 누락, 레시피의 분류 부모 누락, 초기 관계 조합 중복은 모두 0건이었다. `recipe` 스키마 뷰는 0개였다. 이는 해당 시점의 제한된 조회 결과이며 전체 검증 SQL 결과를 뜻하지 않는다.

## 목표 관계와 분류 기준

- `rcp`의 단독 PK는 `rcp_id`. 분류가 바뀌어도 레시피 ID는 유지한다.
- 기존 `rcp_cat`을 분류 마스터로 재사용한다. `rcp_cat_axis_cd VARCHAR(20) NOT NULL`로 분류 기준을 구분한다. 예를 들어 요리 형태와 음식 계통은 서로 다른 코드가 된다. 코드 정의는 기존 `common_code_grp`/`common_cd`의 `RCP_CAT_AXIS` 그룹을 논리적으로 사용하며, 목표 DDL은 코드값을 임의 생성하지 않는다. 분류명의 유일성은 기준 내 `(rcp_cat_axis_cd, rcp_cat_nm)`로 둔다.
- `rcp_cat_rel`은 `(rcp_id, rcp_cat_id)` 복합 PK로 레시피와 분류를 연결한다. 별도 ID와 물리 FK는 없다. 동일 조합 중복은 PK로 막는다. 레시피당 0개 이상의 관계를 허용하는 DDL이며, 적어도 하나가 필요한 업무 정책은 적재 검증으로 확인한다.
- `rcp_step`은 레시피 PK와 단계 번호를 합쳐 식별한다. `rcp_ingr`는 표준 식재료의 기존 복합 PK 전체 `(ingr_cat_id, ingr_id)`와 레시피 PK `rcp_id`를 합친다. `rcp_ingr_stg`는 원본 행을 부모로 삼으므로 분류 변경과 무관하다.

현재 `rcp_cat` 6건은 식약처 `RCP_PAT2`에서 온 값이다. 각각 어떤 분류 기준에 속하는지 원본 의미를 확인하고 승인한 뒤 코드와 관계를 부여해야 한다. '중식'처럼 원본에 없는 값은 이 설계에서 생성하거나 추론하지 않는다. `common_cd`는 분류 기준 코드에만 쓰고 요리 분류값 자체는 `rcp_cat`에서 관리한다.

## 현행 프로그램 영향

`recipe_recommender/recipe.sql`의 등록·수정·검색·무결성 조회가 `rcp.rcp_cat_id` 또는 `(rcp_cat_id, rcp_id)` 조인을 사용한다. 등록 시 분류 관계를 따로 저장하고 검색은 `rcp_cat_rel`을 통해 필터링해야 한다. 여러 분류와 조인한 검색 목록에는 동일 레시피 중복이 생길 수 있으므로 레시피 ID 기준 집계·페이지네이션을 재설계해야 한다. `recipe_repository.py`, 등록/검색 서비스, `recipe_graph_source_repository.py`, `recipe_graph_load_service.py`의 키 정의와 스냅샷 검증도 영향받는다. 현재 Neo4j 적재는 레시피 복합 키와 단일 분류 관계를 가정한다. 향후 `Recipe → IN_CATEGORY → Category` 관계를 각 `rcp_cat_rel` 행에서 만들 수 있으며 관계 행을 노드로 만들 필요는 없다. 이번 단계에서는 코드와 그래프를 수정하거나 적재하지 않았다.

## 별도 승인 후 마이그레이션 설계 순서

1. 현행 스키마, 데이터, 시퀀스 값, 프로그램 버전과 연결된 외부 객체를 백업하고 복구 절차를 마련한다. `recipe_multi_category_validation.sql`의 현행 조회를 실행해 단독 ID·목표 자식 PK 중복 및 논리 참조를 검사한다.
2. 기존 6개 분류의 기준을 원본과 대조해 결정하고 `RCP_CAT_AXIS` 공통코드 그룹·코드 운영 정책을 확정한다. 추가 분류는 근거와 승인 후 별도 등록한다.
3. 전환 중 쓰기를 통제하고, 기존 `rcp.rcp_cat_id`와 `rcp.rcp_id`를 보존해 관계 행으로 대응시킬 작업안을 만든다. 예상 초기 관계 수는 현행 레시피당 분류 1개라면 1,156건이지만 실제 전환 전 재확인한다.
4. 자식 `rcp_step` 및 `rcp_ingr`에서 기존 복합 레시피 키를 단독 `rcp_id`로 대응시킨다. 기존 `rcp_id`는 재발급하지 않는다. PK·인덱스 변경 전에 충돌 여부를 확인한다. `rcp_ingr_stg`와 원본 데이터는 유지한다.
5. 적용 계획을 트랜잭션·잠금 시간·롤백 가능성까지 검토한 후에만 목표 제약과 인덱스를 적용한다. 프로그램의 읽기·쓰기 쿼리와 Neo4j 적재 경로를 같은 전환에 맞춘다. 기존 분류 관계, 10,428건 식재료 관계, 6,717건 조리 단계의 보존과 전후 키 대응을 대조한다.
6. `recipe_multi_category_target_validation.sql`을 실행하고 레시피당 관계 누락, 중복, 부모 누락, 분류 기준 코드 누락을 확인한다. 전환 결과를 확인한 뒤 구 모델의 분류 컬럼 정리를 결정한다.

위 순서는 설계안이다. 실행 가능한 데이터 변경·삭제 SQL은 작성하지 않았다. 위험 요소는 분류 기준의 의미 오판, 애플리케이션의 복합 키 의존, 다중 분류 조인에 따른 결과 중복, 물리 FK 부재로 인한 고아 관계, PK 교체 시 잠금과 인덱스 재구축이다.

## 남은 결정

- 기존 `RCP_PAT2` 6개 값이 한 분류 기준에 모두 속하는지, 기준 코드의 실제 명칭과 운영 책임.
- 새 분류값의 승인·출처·변경 이력 정책. 이 초안은 관계 속성이나 이력 테이블을 추가하지 않았다.
- 분류가 0개인 레시피를 임시 허용할지, 운영 적재 단계에서 반드시 1개 이상 요구할지.
- 여러 수집 회차에서 동일 `rcp_seq`의 원본 추적과 `rcp_raw_id` 갱신 정책은 기존 방식 유지가 전제이며 전환 시 재확인.
