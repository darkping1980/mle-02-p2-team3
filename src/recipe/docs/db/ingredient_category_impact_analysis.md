# 식재료 분류 마스터 필요성 및 제거 영향 분석

> **이력 문서.** 2026-10-22 목표 모델 전환 전의 식재료 분류 제거 영향 분석(결론 A가 채택되어 적용됨)이다. 현재 구조는 `recipe_target_schema.sql`·`recipe_table_definition.md`, 전환 기록은 `recipe_target_rebuild_runbook.md`를 따른다.

분석 범위: 2026-10-22 현재 저장소의 DDL·SQL·Python·Cypher와 PostgreSQL `recipe` 스키마의 읽기 전용 조회. 기존 파일과 DB는 변경하지 않았다. 검증 SELECT는 `ingredient_category_validation.sql`에 있다.

## 결론 — A. 식재료 분류 제거 권장

이 프로젝트의 현재 핵심 경로인 보유 식재료 검색, 이름 표준화, 레시피–식재료 N:M 탐색은 **식재료 분류 없이도 같은 식재료 ID로 구현할 수 있다.** 구현된 PostgreSQL 검색과 Neo4j 질의에는 “채소류가 들어가는 레시피”처럼 식재료 분류명을 조건으로 사용하는 기능이 없다. 현재 분류는 표준 식재료 사전의 조직, 복합 키, 상세 화면의 분류명 표시·정렬, 그래프 분류 노드와 관계의 적재에 사용된다. 이 사용처는 실제 코드에 존재하지만 핵심 검색 요구사항의 필수 조건은 아니다.

따라서 **다음 통합 모델 전환에서 제거하는 설계**를 권장한다. 이는 즉시 테이블을 삭제하자는 뜻이 아니다. 현행 ETL·검색·그래프는 복합 키를 넓게 사용하므로 레시피 다중 분류 전환과 함께 키, 조회, 적재, 검증을 일괄 설계하고 데이터 보존을 확인해야 한다. 분류별 검색이나 식품군 통계가 제품 요구사항으로 확정되면 결론을 다시 검토한다.

## 실제 모델과 데이터

| 테이블 | 현행 PK | 레시피 다중 분류 목표 DDL의 PK | 분류 제거 검토 PK |
|---|---|---|---|
| `ingr_cat` | `(ingr_cat_id)` | 동일 | 테이블 제거 검토 |
| `ingr` | `(ingr_cat_id, ingr_id)` | 동일 | `(ingr_id)` |
| `ingr_als` | `(ingr_cat_id, ingr_id, ingr_als_id)` | 동일 | 우선 `(ingr_id, ingr_als_nm)` |
| `rcp_ingr_stg` | `(rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id)` | 동일 | 동일 |
| `rcp_ingr` | `(ingr_cat_id, ingr_id, rcp_cat_id, rcp_id)` | `(ingr_cat_id, ingr_id, rcp_id)` | `(rcp_id, ingr_id)` |
| `rcp_raw` | `(rcp_raw_id, rcp_raw_seq)` | 동일 | 동일 |

현행 DB의 `ingr_cat_id` 컬럼은 `ingr_cat`, `ingr`, `ingr_als`, `rcp_ingr`에서 NOT NULL이고 `rcp_ingr_stg`에서 NULL 허용이다. `rcp_raw`에는 없다. `ingr.ingr_id`는 `VARCHAR(20) NOT NULL DEFAULT recipe.fn_get_biz_id('ingr')`이며 현재 **단독 UNIQUE 제약은 없다.** 현행 식재료명은 `UNIQUE (ingr_nm)`, 별칭명은 부모 안에서 `UNIQUE (ingr_cat_id, ingr_id, ingr_als_nm)`이다. `rcp_ingr_stg`의 승인된 식재료 매핑은 분류·식재료 ID 두 값을 같이 저장한다. 물리 FK는 현행·목표 모두 없다.

읽기 전용 조회 결과:

| 검증 항목 | 결과 |
|---|---:|
| 표준 식재료 / 서로 다른 `ingr_id` | 275 / 275 |
| `ingr_id` 중복, 분류 부모 누락 | 0 / 0 |
| 별칭 / 별칭이 있는 식재료 / 서로 다른 별칭명 | 71 / 55 / 71 |
| `(ingr_id, ingr_als_nm)` 중복, 별칭 부모 누락 | 0 / 0 |
| 표준명·별칭이 서로 다른 식재료 ID로 연결되는 정확 일치 충돌 | 0 |
| trim·소문자 정규화 후 서로 다른 식재료 ID 충돌 | 0 |
| 레시피–식재료 관계 / 서로 다른 `(rcp_id, ingr_id)` | 10,428 / 10,428 |
| 분류 제거 후 관계 PK 충돌 / 식재료 부모 누락 | 0 / 0 |
| staging 전체 / 식재료 ID 매핑 / 분류 ID만 있는 불완전 쌍 | 13,080 / 10,611 / 0 |
| staging에 매핑된 식재료 부모 누락 | 0 |

이 결과는 **현재 ID와 연결의 보존 가능성**을 보여 준다. 장래 데이터의 단독 ID 유일성을 보장하지는 않으므로 모델 적용 시 단독 PK로 강제해야 한다. `ingr_id` 275개를 재발급하거나 관계 10,428건을 재적재할 필요가 없는 방향으로 설계할 수 있다. 실제 전환 절차는 별도 검토가 필요하다.

### 분류별 표준 식재료 수

| 분류 | 수 | 분류 | 수 |
|---|---:|---|---:|
| 감자 및 전분류 | 8 | 견과 및 종실류 | 16 |
| 곡류 및 그 제품 | 23 | 과일류 | 19 |
| 기타 | 4 | 난류 | 4 |
| 당류 | 10 | 두류 | 8 |
| 버섯류 | 7 | 어패류 | 17 |
| 우유 및 유제품류 | 9 | 유지류 | 8 |
| 육류 | 12 | 음료류 | 4 |
| 조리가공식품류 | 3 | 조미료류 | 44 |
| 주류 | 4 | 채소류 | 71 |
| 해조류 | 4 |  |  |

19개 분류 모두 식재료가 있으며 합계는 275건이다. 분류값과 설명은 `recipe_recommender/data/ingr_cat_seed.csv`의 식품군 사전에서 왔다.

## 업무 질문별 판단

### Q1. 분류를 레시피 검색에 실제 사용하는가?

**분류명 조건 검색은 구현되어 있지 않다.** `recipe.sql`의 `find_ingredient_by_name`은 표준명·별칭으로 찾고 분류명을 결과에 붙인다. `list_recipe_ingredients`는 분류명을 표시하고 그 이름으로 정렬한다. `list_recipes_by_ingredient`와 `count_recipes_by_ingredient`의 `ingr_cat_id` 조건은 사용자가 선택한 **복합 식재료 식별자**를 맞추기 위한 것이며 “식재료 분류별 레시피” 조건이 아니다. `RecipeSearchService`에도 분류명 입력 조건은 없다. 그래프의 `category_and_ingredient` 질의는 *요리 분류* `RcpRecipeCategory`를 사용한다. `RcpIngredientCategory`를 검색 조건으로 쓰는 명명 Cypher는 없다.

분류 제거 시 사라지는 현재 기능은 식재료 상세의 분류명 표시·분류명 정렬, 사전의 분류별 조직, 그래프의 식재료 분류 노드·연결이다. 채소류·육류별 레시피 검색과 식품군 통계는 **현재 구현되지 않은 잠재 기능**이다.

### Q2. 표준화에 분류가 반드시 필요한가?

현재 파서는 `RCP_PARTS_DTLS`에서 이름·수량·단위·구획을 분리하고 분류를 사용하지 않는다. `update_staging_verified_matches`는 표준명과 별칭을 합쳐 후보명 정확 일치 및 대상 1개 여부로 자동 승인한다. `ingr_cat_id`는 현재 대상 식재료의 복합 키를 완성하고 결과에 저장하기 위해 사용된다. `ingr_id`를 단독 PK로 만들면 같은 판정은 `count(DISTINCT ingr_id)=1`로 할 수 있다. 현재 자료에서 분류로 동명이의 식재료를 구분해야 하는 사례는 발견되지 않았다. 사전 로더는 오히려 표준명 중복과 다른 식재료에 걸친 별칭 충돌을 막는다.

분류를 버리더라도 이름 충돌 검사는 유지해야 한다. 분류 제거 자체가 동의어 매핑을 해결하지는 않는다.

### Q3. 원본 데이터에 식재료 분류나 별칭이 있는가?

저장소에는 원본 `COOKRCP01.csv` 파일이 없어 파일 자체의 헤더를 직접 대조하지 못했다. 다만 `RecipeRegisterService.SOURCE_COLUMNS`가 허용하는 55개 원본 컬럼과 저장된 `rcp_raw` 컬럼에는 `RCP_PARTS_DTLS` 원문만 있고, 독립적인 식재료 분류·별칭 컬럼은 없다. CSV 읽기는 정의되지 않은 헤더를 오류로 처리한다. `ingr_cat_seed.csv` 및 `ingr_seed.csv`는 프로젝트의 별도 사전이며, 원본 레시피 CSV의 독립 필드가 아니다. 식재료 분류는 이 사전에서, 별칭은 `ingr_seed.csv`의 `ingr_als_nms`에서 공급된다.

### Q4. 19개 분류의 가치가 있는가?

사전 정리·표시·정렬과 그래프 탐색 가능성에는 가치가 있다. 그러나 현재 추천 경로는 식재료 **개체**와 별칭을 사용한다. 분류 기반 추천 조건, 식품군 통계, 분류별 레시피 검색의 확인된 요구사항이나 구현은 없다. 따라서 유지 비용과 복합 키 전파 비용에 비해 지금 필수 엔티티라는 근거가 부족하다.

## 식재료 별칭은 유지

실제 DB에 `계란 → 달걀`, `녹말 → 전분`, `검은깨 → 흑임자` 매핑이 있다. `다진마늘 → 다진 마늘`과 같은 공백 변형도 있으며, 이 둘은 역할이 다르다. 수량 제거와 구획 분리는 파서의 문자열 전처리이고, 별칭은 서로 다른 입력 이름을 동일한 표준 식재료로 연결하는 사전 데이터다. 현재 71개 별칭 중에는 진정한 동의어와 단순 표기 변형이 함께 있다.

`update_staging_verified_matches`가 남긴 검토 메모에서 정확한 별칭 일치 자동 승인은 **619건**, 표준명 정확 일치는 **9,992건**이었다. 두 수의 합은 식재료 ID가 있는 staging 10,611건과 같다. `find_ingredient_by_name`과 `RecipeSearchService.search_recipes_by_ingredient`도 별칭을 입력 검색에 사용한다. Neo4j 적재는 별칭을 `RcpIngredient.alias_names` 및 정규화 목록으로 두고, 보유 식재료 추천 질의가 이를 사용한다. 따라서 별칭은 현재 기능에 직접 기여한다.

제안 PK `(ingr_id, ingr_als_nm)`는 기존 부모별 별칭명 UNIQUE를 분류 ID 없이 유지하면서 식재료 부모의 단독 PK를 승계한다. 단, 별칭 문자열 변경이 PK 변경이 된다는 단점이 있다. 기존 `ingr_als_id`는 발급·조회되는 ID이므로 이관 시 재발급하지 않고 일반 속성 또는 별도 UNIQUE로 남길지 결정한다. 현재 DB는 같은 별칭명이 다른 식재료에 매핑된 경우 0건이지만, 기존 UNIQUE는 부모별이므로 미래 충돌은 사전 검사와 검증으로 막아야 한다.

## 분류 제거 시 목표 구조와 영향

- `ingr`: `ingr_id VARCHAR(20)` 단독 PK. `seq_ingr`와 `fn_get_biz_id('ingr')`는 유지한다. `ingr_nm` UNIQUE도 유지한다.
- `ingr_als`: `ingr_cat_id` 제거, `ingr_id`와 별칭명을 부모별 식별자로 사용한다. `ingr_als_id` 보존·제약 정책은 적용 설계에서 정한다.
- `rcp_ingr`: 레시피 다중 분류 목표의 `rcp_id` 단독 PK와 식재료 `ingr_id` 단독 PK를 모두 승계해 `(rcp_id, ingr_id)`를 PK로 한다. 원본 회차 `rcp_raw_id`는 기존처럼 일반 속성이다. `rcp_id` 선두 PK라 레시피별 조회는 지원하고, 식재료별 역방향 조회에는 `(ingr_id, rcp_id)` 인덱스를 검토한다.
- `rcp_ingr_stg`: PK와 원문·파싱·검토 상태·관리 컬럼은 유지한다. 매핑 대상은 nullable `ingr_id` 하나로 표현하고, 기존 `ingr_cat_id`를 제거한다. 승인 시 `ingr_id` 부모 존재를 논리 검증한다. 기존 `ix_rcp_ingr_stg_ingr_key (ingr_cat_id, ingr_id)`는 `(ingr_id)`로 바꾼다.
- `rcp_raw`: 변경 없음. 원본 문자열과 수집 회차를 그대로 보존한다.
- `ingr_cat` 및 `seq_ingr_cat`: 통합 설계에서 제거 대상. 실제 제거 전에 다른 참조가 없는지 다시 확인한다.

현행 `recipe_schema_review.sql`과 앞서 만든 `recipe_multi_category_target.sql`은 모두 식재료 분류와 복합 식재료 키를 **유지**한다. 따라서 본 권고를 채택하면 다중 분류 목표 DDL의 식재료 관련 테이블·인덱스·COMMENT와 설계·검증 문서를 별도로 개정해야 한다. 레시피의 `rcp`·`rcp_cat`·`rcp_cat_rel` 목표는 유지한다. 이번 분석에서 기존 DDL·코드는 수정하지 않았다.

### 코드 영향

| 영역 | 필요한 전환 |
|---|---|
| 등록 사전 | `RecipeRegisterService.register_ingredient_master`의 분류 우선 등록, 분류 충돌 검사, `ingr_cat_seed.csv` 의존 제거 검토. `ingr_seed.csv`는 표준명·별칭 중심으로 재구성. |
| 승인·최종 관계 | `recipe.sql`의 정확 일치 대상 집계, staging 매핑, 최종 관계 중복 제거·조인에서 `ingr_cat_id` 제거. 승인·검토 내역은 보존. |
| 검색 | `find_ingredient_by_name`, 별칭 목록, 레시피 식재료 상세·역조회, `RecipeSearchService`와 Repository 인자를 단독 `ingr_id`로 전환. 분류명 출력·정렬의 대체 표시 기준 결정. |
| 검증 | 식재료 분류 부모 검사 대신 단독 `ingr_id` 유일성·부모 존재·별칭 충돌·관계 중복 검사. |
| 레시피 다중 분류 | `rcp_ingr` PK를 `(rcp_id, ingr_id)`로 맞추고 양쪽 모델 전환 순서를 함께 설계. |

## Neo4j 영향

현재 저장소 설계와 적재 코드는 `RcpIngredientCategory` 노드, `RCP_IN_INGREDIENT_CATEGORY` 관계, `RcpIngredient(ingr_cat_id, ingr_id)` 복합 식별자 및 제약조건을 정의한다. 과거 `neo4j_model_design.md`에는 적재 후 식재료 분류 노드 19개, 분류 관계 275개, 식재료 노드 275개, `RCP_USES` 10,428개가 기록되어 있다. **이번 작업의 실시간 Neo4j 조회는 연결 설정 `NEO4J_URI`가 현 세션에 없어 수행하지 못했다.** 따라서 현재 그래프가 비었는지, 기록된 수가 유지되는지는 확인되지 않았다.

분류를 제거하면 `recipe_graph_source_repository.py`의 분류 조회, `recipe_graph_load_service.py`의 분류 키·단계·검증·예상 건수, `recipe_graph_load.cypher`의 노드·분류 관계 적재, `recipe_graph_constraints.cypher`의 분류 제약을 후속 전환에서 수정해야 한다. `recipe_graph_validation.cypher`, `recipe_graph_queries.cypher`와 그래프 설계·사용자 검증 문서도 복합 식재료 키를 `ingr_id`로 바꿔야 한다. `RCP_USES`의 원천은 계속 `rcp_ingr`이고, 별칭은 `RcpIngredient`의 `alias_names` 및 정규화 검색 속성으로 유지할 수 있다. 분류 노드가 사라지면 `RCP_IN_INGREDIENT_CATEGORY` 경유 식품군 탐색은 할 수 없지만, 현재 명명된 추천 질의 중 이를 조건으로 사용하는 것은 없다.

기존 그래프가 적재되어 있다면 단순히 새 단독 키로 `MERGE`하는 것만으로 오래된 분류 노드·관계가 사라지지 않는다. 기존 그래프의 정리·동기화 정책을 별도 승인과 검증 하에 설계해야 한다. 이번에는 Neo4j 쓰기를 하지 않았다.

## 적용 전 조건

1. 최종 목표가 식재료 분류 없는 모델임을 확정하고 분류명 표시 및 미래 식품군 검색 요구사항을 결정한다.
2. 현행 `ingr_id` 275개, 별칭 71개, 관계 10,428개, 매핑된 staging 10,611개의 식별자·연결 스냅샷을 확보한다. 전환 전후 ID와 부모 대응, 건수, 집합 차이를 비교한다.
3. 목표 PK 중복 0, 부모 누락 0, 별칭명 충돌 0을 다시 확인한다. 새로운 단독 PK·인덱스와 프로그램·그래프 적재를 같은 전환 계획에 넣는다.
4. 물리 FK가 없으므로 ETL과 검증 SELECT의 부모 참조 검사를 유지한다. 기존 그래프가 존재하는지 확인하고 정리 정책을 별도로 정한다.

이 문서는 제거 대안의 영향 분석이며 실행 가능한 삭제·데이터 변경 SQL을 포함하지 않는다.
