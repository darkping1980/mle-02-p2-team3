# 레시피 GraphRAG Neo4j 모델 (PostgreSQL 목표 모델 기준)

## 기준과 목적

- 원천: PostgreSQL `postgres` DB의 `recipe` 스키마 **목표 모델**(2026-10-22 전환, `docs/db/recipe_target_schema.sql`).
  `rcp(rcp_id)`, `ingr(ingr_id)` 단독 PK, 레시피·요리 분류 N:M `rcp_cat_rel(rcp_id, rcp_cat_id)`, 식재료 분류 없음.
- Neo4j: AuraDB Free 사용자 DB `6ac1f0f8`(Neo4j Kernel `5.27-aura`). 다른 실습의 제약조건 6개가 함께 있는 공용 DB이므로
  프로젝트 객체를 다른 실습 객체와 구분한다. 노드 라벨은 PostgreSQL `recipe` 스키마 테이블명과 같고(`rcp`, `ingr`, `rcp_cat`),
  관계 유형은 `RCP_`, 제약조건·인덱스 이름은 `rcp_`/`ingr_` 접두어를 쓴다. 다른 실습 객체는 읽지도 바꾸지도 않는다.
- 목표 경로: `rcp -[:RCP_USES]-> ingr <-[:RCP_USES]- rcp`. 이름이 같은 다른 업무 엔티티를 합치지 않는다.
- PostgreSQL 원본·staging·승인 이력은 그래프로 복제하지 않는다. `RCP_USES`는 승인·검증된 최종 `recipe.rcp_ingr`만 사용한다.
- 실행용 Named Cypher Mapper: `recipe_recommender/recipe_graph_constraints.cypher`, `recipe_graph_load.cypher`,
  `recipe_graph_validation.cypher`, `recipe_graph_queries.cypher`. `docs/neo4j/`는 설계·직접 검증 안내용이다.

## 노드와 관계

| 노드 라벨 | 원천 | 식별 조건 (`MERGE`) | 주요 속성 | 예상 수 |
|---|---|---|---|---:|
| `rcp` | `recipe.rcp` | `rcp_id` | `rcp_seq`, `rcp_nm`, `cook_mthd_cd`, `cook_mthd_nm`, `rcp_energy_kcal`, `rcp_nutrition_status`, `rcp_image_url` | 1,156 |
| `ingr` | `recipe.ingr` + `ingr_als` | `ingr_id` | `ingr_nm`, `ingr_nm_norm`, `alias_names`, `alias_names_norm` | 275 |
| `rcp_cat` | `recipe.rcp_cat` | `rcp_cat_id` | `rcp_cat_nm` | 6 |

| 관계 유형 | 방향 | 원천 | 질의 역할 | 예상 수 |
|---|---|---|---|---:|
| `RCP_USES` | `rcp` → `ingr` | `recipe.rcp_ingr` 1행 → 1개 | 재료 검색, 공통 재료, 보유 재료 추천 | 10,428 |
| `RCP_IN_RECIPE_CATEGORY` | `rcp` → `rcp_cat` | `recipe.rcp_cat_rel` 1행 → 1개 | 요리 분류 제한 검색. 레시피당 1개 이상(다중 분류 가능) | 1,156 |

목표 총계는 **노드 1,437개, 관계 11,584개**다. 현재 데이터는 레시피마다 분류가 하나다(`RCP_PAT2`). 다중 분류는 PostgreSQL
`rcp_cat_rel`에 승인된 행이 생길 때만 그래프에 나타나며, 그래프에서 임의로 만들지 않는다. 재료 연결이 없는 레시피 8개도
요리 분류 검색·상세 조회에서 빠지지 않도록 `rcp`로 적재한다.

별칭 71개는 Sol 설계대로 `ingr`의 목록 속성(`alias_names`, 정규화 `alias_names_norm`)으로 둔다.
사용자 입력은 ETL과 같은 규칙(양끝 공백 제거·소문자화)으로 정규화해 표준명 또는 별칭 목록과 정확히 비교한다.
예: `계란` → 표준 `달걀`. 유사 이름(`두부`/`연두부`)은 합치지 않는다.

## Sol 설계에서 바꾼 부분과 이유

| 항목 | 이전(Sol) | 목표 | 이유 |
|---|---|---|---|
| 레시피 식별 | `(rcp_cat_id, rcp_id)` 복합 키, 제약 `rcp_recipe_composite_key` | `rcp_id`, 제약 `rcp_key` | PostgreSQL PK가 `rcp_id` 단독. 다중 분류에서는 분류가 레시피 키의 일부일 수 없다 |
| 식재료 식별 | `(ingr_cat_id, ingr_id)` 복합 키, 제약 `rcp_ingredient_composite_key` | `ingr_id`, 제약 `ingr_key` | Sol은 `ingr_id` 단독 UNIQUE가 없어 복합 키를 택했다. 목표 DDL에서 `ingr_id`가 PK가 되어 근거가 해소됐다 |
| 식재료 분류 | `RcpIngredientCategory` 노드 19, `RCP_IN_INGREDIENT_CATEGORY` 275, 제약 `rcp_ingredient_category_key` | 없음 | 원천 `ingr_cat` 제거. 명명 질의 중 이를 조건으로 쓰는 것이 없었다 |
| 레시피 분류 관계 원천 | `rcp.rcp_cat_id`(레시피당 정확히 1개) | `rcp_cat_rel` 행(1개 이상) | N:M. 검증 규칙도 "정확히 1개"에서 "1개 이상 + 원천 관계 집합과 일치"로 바뀜 |
| 노드 속성 | `RcpRecipe.rcp_cat_id`, `RcpIngredient.ingr_cat_id` | 없음 | 분류는 관계로만 표현. 다중 분류에서 단일 속성은 오해를 만든다 |
| 질의 파라미터 | `$rcp_cat_id + $rcp_id`, `$ingr_cat_id + $ingr_id` | `$rcp_id`, `$ingr_id` | 키 변경 |
| `graphrag_context` | `category` 하나 | `categories` 목록 | 다중 분류 |
| 질의 추가 | — | `recipes_by_ingredient_term`, `recipes_with_all_ingredients`, `recipes_in_category` | 과제의 식재료 기반 검색(단일·모두 포함·분류) |

유지한 것(2026-10-22 전환 시점 기준. 노드 라벨·제약/인덱스 이름은 아래 2026-10-23 명칭 통일로 바뀜): 라벨·관계 이름, `Rcp`/`RCP_`/`rcp_` 접두어, 별칭 목록 속성과 정규화 규칙, `rcp_recipe_source_seq`·
`rcp_recipe_category_key` 제약, 이름 RANGE 인덱스 2개, 적재 순서, 배치 사전 매칭 검사, 키만 `MERGE`하고 속성은 `SET`,
두 번 적재로 멱등성 확인, 삭제 동기화 미구현 정책.

## 2026-10-23 노드 라벨 명칭 통일

데이터 모델 변경 없이 노드 라벨을 PostgreSQL `recipe` 스키마 테이블명과 맞췄다. 새 라벨을 부여하고 기존 라벨을 제거했으므로
노드·속성·관계·`elementId`는 그대로다. 관계 유형 `RCP_USES`·`RCP_IN_RECIPE_CATEGORY`와 방향, 별칭 목록 속성은 바꾸지 않았다.
`rcp_ingr`·`rcp_cat_rel`은 계속 관계로 표현한다. 실행 기록: `neo4j_label_rename_20261023.md`.

| 이전 라벨 | 현재 라벨 | 이전 제약조건·인덱스 | 현재 제약조건·인덱스 |
|---|---|---|---|
| `RcpRecipe` | `rcp` | `rcp_recipe_key`, `rcp_recipe_source_seq`, `rcp_recipe_name_idx` | `rcp_key`, `rcp_seq_key`, `rcp_nm_idx` |
| `RcpIngredient` | `ingr` | `rcp_ingredient_key`, `rcp_ingredient_name_norm_idx` | `ingr_key`, `ingr_nm_norm_idx` |
| `RcpRecipeCategory` | `rcp_cat` | `rcp_recipe_category_key` | `rcp_cat_key` |

적재 프로그램은 이전 라벨(`Rcp` 접두어)이나 이전 제약조건·인덱스 이름이 남아 있으면 쓰기 전에 중단한다.

## PostgreSQL → 그래프 매핑 및 제외

| PostgreSQL | 그래프 반영 |
|---|---|
| `rcp_cat`, `rcp_cat_rel`, `rcp` | 분류·레시피 노드와 `RCP_IN_RECIPE_CATEGORY`. `cook_mthd_cd`(6자리 코드, 예: `000004`)는 `common_cd`의 `COOK_MTHD` 그룹과 조인해 명칭을 `cook_mthd_nm`(예: `찌기`) 속성으로 넣는다 |
| `ingr`, `ingr_als` | 표준 식재료 노드. 별칭은 `ingr_id`로 조인해 목록 속성으로 넣는다 |
| `rcp_ingr` | `RCP_USES`. 수량·원문·등장 순서는 이 테이블에 없으므로 만들지 않는다 |
| `rcp_step`, `rcp_raw`, `rcp_ingr_stg`, 공통코드 테이블 | 제외. 상세·이력은 PostgreSQL에서 조회한다. 보류 staging 2,469건은 추정 연결하지 않는다 |

## 적재 및 재적재 정책

1. Python ETL이 PostgreSQL을 `REPEATABLE READ READ ONLY` 스냅샷으로 읽고(`RECIPE_DB_SCHEMA`로 스키마 지정 가능)
   PK·컬럼 형식이 목표 모델과 같은지, 키 중복·부모 참조·분류 없는 레시피·별칭 충돌을 사전 검증한다.
2. 그래프 사전 점검에서 프로젝트 접두어의 알 수 없는 라벨·관계나 **이전 모델 제약조건**이 있으면 쓰기 전에 중단한다.
3. 분류 → 식재료/레시피 → 분류 관계 → `RCP_USES` 순서, 배치(기본 500행)별 트랜잭션. 관계 배치는 전송 행 수와
   부모 매칭 수가 다르면 쓰지 않는다.
4. 동일 스냅샷으로 두 번 적재해 노드·관계 수가 같음을 확인한다(멱등성). 원천에서 사라진 행의 삭제는 별도 승인 정책이다.

## 적재 상태

2026-10-22 사용자 승인으로 DB를 전체 초기화하고 이 모델로 새로 적재했다(노드 1,437, 관계 11,584, PostgreSQL과 집합 일치).
2026-10-23 노드 라벨을 `rcp`·`ingr`·`rcp_cat`으로 바꿨다(수·속성·관계 동일, 재적재 없음).
실행 기록: `neo4j_target_model_migration.md`, 실제 구조: `neo4j_actual_schema.json`.
