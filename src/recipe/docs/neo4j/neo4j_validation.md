# Neo4j 적재 전후 검증 결과와 재검증 쿼리

> **이전(Sol) 모델 기록.** 이 문서는 복합 키·식재료 분류 모델로 2026-10-22에 적재한 결과다. PostgreSQL 목표 모델 기준의
> 목표 모델 초기화·재적재 기록과 정합성·검색 검증은 `neo4j_target_model_migration.md`, 목표 설계는 `neo4j_model_design.md`를 따른다.

## 2026-10-22 실제 적재 결과

`python -m recipe_recommender.setup.load_recipe_graph --apply`로 현재 AuraDB에 적용했다. 동일 PostgreSQL 스냅샷으로 두 번 적재했으며 양쪽 모두 아래 수치와 일치했다. 이어서 `--verify-only`를 독립 실행해 같은 결과를 읽기 전용으로 재확인했다.

프로젝트 폴더에서 실행하는 명령:

```powershell
python -m recipe_recommender.setup.load_recipe_graph
python -m recipe_recommender.setup.load_recipe_graph --verify-only
python -m recipe_recommender.setup.load_recipe_graph --apply
```

첫 명령은 기본 dry-run이다. `--apply`는 프로젝트 전용 제약조건·인덱스를 확인하고 복합 키 `MERGE`를 실행한다. PostgreSQL은 기존 `DatabaseManager` 연결 풀을 재사용하며, 데이터 추출은 명시적인 `REPEATABLE READ READ ONLY` 트랜잭션에서 수행한다. 완전 동기화를 위한 삭제는 구현하지 않았다.

| 대상 | 실제 건수 |
|---|---:|
| `RcpRecipe` | 1,156 |
| `RcpIngredient` | 275 |
| `RcpRecipeCategory` | 6 |
| `RcpIngredientCategory` | 19 |
| `RCP_USES` | 10,428 |
| `RCP_IN_RECIPE_CATEGORY` | 1,156 |
| `RCP_IN_INGREDIENT_CATEGORY` | 275 |
| 프로젝트 노드 / 관계 합계 | 1,456 / 11,859 |

분류 관계 누락·잘못된 분류 키 0건, 사용 식재료가 없는 레시피 8개. 실제 복합 키 집합과 관계 키 집합을 PostgreSQL 스냅샷과 대조해 중복·누락을 검사했다. 레시피 28의 재료 7종, 298/536의 5종·17종, 788/919의 각 9종, 칵테일새우 사용 레시피 17개가 일치했다. 원래 실습 제약조건·인덱스는 보존했고 프로젝트 제약조건 5개와 인덱스 7개가 추가됐다. DBeaver 조회용 쿼리는 `neo4j_user_verification.md`에 있다.

아래 표의 0건은 적재 전 기준 기록이다. 현재 상태는 위 실제 결과를 따른다.

## 실제 읽기 전용 조회 결과

2026-10-22 15:33:46 KST PostgreSQL `REPEATABLE READ READ ONLY` 스냅샷과 같은 시점의 AuraDB 조회다. 동시 적재 중일 수 있으므로 적재 직전 동일 쿼리로 새 기준값을 기록한다.

| 항목 | 적재 전 PostgreSQL | 적재 전 Neo4j | 실제 적재 후 Neo4j |
|---|---:|---:|---:|
| `rcp` / `RcpRecipe` | 1,156 | 0 | 1,156 |
| `ingr` / `RcpIngredient` | 275 | 0 | 275 |
| `rcp_cat` / `RcpRecipeCategory` | 6 | 0 | 6 |
| `ingr_cat` / `RcpIngredientCategory` | 19 | 0 | 19 |
| `rcp_ingr` / `RCP_USES` | 10,428 | 0 | 10,428 |
| 레시피·분류 관계 | 1,156 | 0 | 1,156 |
| 식재료·분류 관계 | 275 | 0 | 275 |

보조 현황: `rcp_raw` 1,156, `common_code_grp` 1, `common_cd` 6, `rcp_step` 6,717, `ingr_als` 71, `rcp_ingr_stg` 13,080. 재료가 연결된 레시피 1,148개, 연결되지 않은 레시피 8개. 사용된 식재료 275개. staging `AUTO_APPROVED` 10,611개, `PENDING_REVIEW` 2,469개. 승인 건수와 최종 관계 건수는 원본 중복 제거 때문에 같을 필요가 없다.

실제 PostgreSQL 검사에서 `rcp_ingr`의 레시피·식재료 고아 참조 0, 복합 관계 중복 0이었다. `rcp`의 요리 종류·조리 방법, `rcp_step`의 레시피, `ingr_als`의 식재료 고아 참조도 0이었다. 정규화한 표준명/별칭이 서로 다른 식재료를 가리키는 경우도 0이었다. 이는 해당 조회 시점에만 유효하다.

AuraDB는 `5.27-aura`, Edition 응답 `enterprise`다. 기존 UNIQUE 6개(`article_id`, `case_id`, `law_name`, `movie_title`, `person_name`, `rule_name`)와 RANGE 6개·LOOKUP 2개, 합계 인덱스 8개가 있었다. 모두 이번 프로젝트의 객체가 아니므로 유지한다. GDS 이름의 프로시저 462개가 조회됐지만 사용 가능 권한·알고리즘 성능은 테스트하지 않았다.

적재 전 `recipe_recommender/recipe_graph_queries.cypher`의 읽기 질의 8개는 빈 AuraDB에서 `EXPLAIN` 구문 검증을 통과했다. 적재 후 같은 8개 질의를 실제 데이터로 실행해 레시피 28의 재료 7종, 칵테일새우 연결 레시피 17개, 재료명 후보·유사 레시피·보유 재료 추천·분류 검색·GraphRAG 컨텍스트 반환을 확인했다. 추천 순위의 품질과 성능은 별도 평가 대상이다.

## 적재 전에 PostgreSQL에서 다시 실행할 SELECT

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT now() AS observed_at, current_database(), current_user;
SELECT count(*) FROM recipe.rcp;
SELECT count(*) FROM recipe.ingr;
SELECT count(*) FROM recipe.rcp_cat;
SELECT count(*) FROM recipe.ingr_cat;
SELECT count(*) FROM recipe.rcp_ingr;
SELECT count(*) FROM recipe.rcp_ingr ri
LEFT JOIN recipe.rcp r ON (ri.rcp_cat_id, ri.rcp_id) = (r.rcp_cat_id, r.rcp_id)
WHERE r.rcp_id IS NULL;
SELECT count(*) FROM recipe.rcp_ingr ri
LEFT JOIN recipe.ingr i ON (ri.ingr_cat_id, ri.ingr_id) = (i.ingr_cat_id, i.ingr_id)
WHERE i.ingr_id IS NULL;
SELECT ingr_cat_id, ingr_id, rcp_cat_id, rcp_id, count(*)
FROM recipe.rcp_ingr GROUP BY 1,2,3,4 HAVING count(*) > 1;
ROLLBACK;
```

카탈로그의 PK·UNIQUE·NOT NULL·컬럼 타입도 실제 조회했다. 노드 키 대응: `rcp` PK `(rcp_cat_id, rcp_id)`, `ingr` PK `(ingr_cat_id, ingr_id)`, 분류 테이블 각 단일 PK. `rcp.rcp_id`와 `rcp.rcp_seq`는 독립 UNIQUE, `ingr.ingr_id` 단독 UNIQUE는 없다. 그래프 ETL은 모든 부모 조인에 복합 키 전체를 사용한다.

## 적재 후 Neo4j에서 실행할 읽기 전용 Cypher

아래 문장은 Neo4j Browser 또는 드라이버에서 각각 개별 실행한다.

```cypher
MATCH (n:RcpRecipe) RETURN count(n) AS recipes;
MATCH (n:RcpIngredient) RETURN count(n) AS ingredients;
MATCH (n:RcpRecipeCategory) RETURN count(n) AS recipe_categories;
MATCH (n:RcpIngredientCategory) RETURN count(n) AS ingredient_categories;
MATCH (:RcpRecipe)-[u:RCP_USES]->(:RcpIngredient) RETURN count(u) AS uses;
MATCH (:RcpRecipe)-[e:RCP_IN_RECIPE_CATEGORY]->(:RcpRecipeCategory)
RETURN count(e) AS recipe_category_links;
MATCH (:RcpIngredient)-[e:RCP_IN_INGREDIENT_CATEGORY]->(:RcpIngredientCategory)
RETURN count(e) AS ingredient_category_links;
```

다음 결과는 모두 **0행 또는 0**이어야 한다.

```cypher
// 같은 복합 키의 노드 중복
MATCH (r:RcpRecipe)
WITH r.rcp_cat_id AS cat, r.rcp_id AS id, count(*) AS n
WHERE n > 1 RETURN cat, id, n;
MATCH (i:RcpIngredient)
WITH i.ingr_cat_id AS cat, i.ingr_id AS id, count(*) AS n
WHERE n > 1 RETURN cat, id, n;

// 동일 레시피·식재료 관계 중복
MATCH (r:RcpRecipe)-[u:RCP_USES]->(i:RcpIngredient)
WITH r, i, count(u) AS n WHERE n > 1
RETURN r.rcp_cat_id, r.rcp_id, i.ingr_cat_id, i.ingr_id, n;

// 부모 관계 누락·잘못된 대상 라벨
MATCH (r:RcpRecipe)
WHERE NOT (r)-[:RCP_IN_RECIPE_CATEGORY]->(:RcpRecipeCategory)
RETURN r.rcp_cat_id, r.rcp_id;
MATCH (i:RcpIngredient)
WHERE NOT (i)-[:RCP_IN_INGREDIENT_CATEGORY]->(:RcpIngredientCategory)
RETURN i.ingr_cat_id, i.ingr_id;
MATCH (a)-[u:RCP_USES]->(b)
WHERE NOT (a:RcpRecipe AND b:RcpIngredient)
RETURN count(u) AS wrong_endpoint_count;
```

Neo4j 관계는 삭제된 노드를 참조하는 상태로 남을 수 없으므로 여기서의 고아 검사는 **정상 라벨·업무 키·부모 관계와 원천 매핑 불일치**에 초점을 둔다. 표본 레시피를 복합 키로 조회하여 PostgreSQL과 식재료 이름 집합을 비교한다. 예: 현재 `rcp_seq='277'`의 `나가사키부대찌개`는 PostgreSQL에서 식재료 22개다. 이름만으로 키를 확정하지 말고 `rcp_seq`로 확인한다.

같은 PostgreSQL 스냅샷을 두 번 적재했고 노드 4종과 관계 3종의 건수가 그대로였다. 단순 건수뿐 아니라 복합 키·관계 키의 전체 집합을 원천과 대조했다. 미래 원천 변경 시에는 새 스냅샷으로 다시 검증해야 한다.

## 질의 검증 기준

1. 레시피 재료 조회: `rcp_seq='277'`에 대해 22개 식재료와 원천 복합 키 집합이 일치한다.
2. 특정 식재료 역조회: 현재 `양파`는 443개 레시피와 연결된다. 정규화된 별칭 후보가 여러 키를 반환하면 자동 병합하지 않는다.
3. 공통 재료 및 Jaccard: 자기 자신을 제외하고 교집합 수가 1 이상이며 점수는 0~1 범위다.
4. 보유 식재료 추천: 입력 중복과 동의어는 한 식재료로 센다. `matched_count + missing_count`가 해당 레시피의 최종 `USES` 수와 같다.
5. 요리 종류 필터: `RCP_IN_RECIPE_CATEGORY` 관계를 타며 레시피의 `rcp_cat_id`와 카테고리 키가 일치한다.
6. 성능: 이 데이터 크기에서 기본 Cypher부터 실행한다. 적재 후 `PROFILE`과 실제 응답 시간으로 인덱스를 재평가한다. 빈 그래프의 실행계획은 성능 근거가 아니다.

제약조건·인덱스 생성용 Named Mapper는 `recipe_recommender/recipe_graph_constraints.cypher`에 있다. Neo4j 5는 복합 속성 유일성 제약과 `IF NOT EXISTS`를 지원하며, 생성되는 유일성 인덱스와 같은 키의 일반 인덱스는 중복하지 않는다. [Neo4j 5 제약조건 문서](https://neo4j.com/docs/cypher-manual/5/constraints/create-constraints/), [Neo4j 5 인덱스 문서](https://neo4j.com/docs/cypher-manual/5/indexes/search-performance-indexes/)
