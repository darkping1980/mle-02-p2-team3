# Neo4j 노드 라벨 명칭 통일 실행 기록 (2026-10-23)

## 결론

AuraDB `6ac1f0f8`의 레시피 그래프 노드 라벨을 PostgreSQL `recipe` 스키마 테이블명과 같게 바꿨다. **데이터 모델 변경이 아니라 명칭 통일**이다.
새 라벨을 부여하고 기존 라벨을 제거하는 방식이라 노드·속성·관계와 `elementId`가 그대로 유지됐다. 전체 초기화·재적재는 하지 않았다.

| 이전 라벨 | 현재 라벨 | 대상 노드 |
|---|---|---:|
| `RcpRecipe` | `rcp` | 1,156 |
| `RcpIngredient` | `ingr` | 275 |
| `RcpRecipeCategory` | `rcp_cat` | 6 |

변경하지 않은 것: 속성명·자료형·값, 업무 ID, 관계 유형 `RCP_USES`(10,428)·`RCP_IN_RECIPE_CATEGORY`(1,156)와 방향,
별칭 목록 속성(`alias_names`, `alias_names_norm`), PostgreSQL 테이블·데이터. `rcp_ingr`·`rcp_cat_rel`은 계속 관계로 표현한다.

## 제약조건·인덱스

새 라벨 기준으로 다시 만들었다. 이름이 같으면 새 제약을 먼저 만들 수 없어 라벨에 맞춰 이름도 바꿨다.

| 이전 | 현재 | 정의 |
|---|---|---|
| `rcp_recipe_key` | `rcp_key` | `rcp.rcp_id` UNIQUE |
| `rcp_recipe_source_seq` | `rcp_seq_key` | `rcp.rcp_seq` UNIQUE |
| `rcp_ingredient_key` | `ingr_key` | `ingr.ingr_id` UNIQUE |
| `rcp_recipe_category_key` | `rcp_cat_key` | `rcp_cat.rcp_cat_id` UNIQUE |
| `rcp_recipe_name_idx` | `rcp_nm_idx` | RANGE `rcp.rcp_nm` |
| `rcp_ingredient_name_norm_idx` | `ingr_nm_norm_idx` | RANGE `ingr.ingr_nm_norm` |

결과: 제약조건 4개, 인덱스 8개(제약 소유 RANGE 4 + 이름 RANGE 2 + Neo4j 기본 LOOKUP 2), 모두 `ONLINE`.
적재 프로그램은 이전 이름의 제약·인덱스나 `Rcp` 접두어 라벨이 남아 있으면 쓰기 전에 중단한다.

## 실행 순서

1. 사전 조회: 라벨 3개(`Rcp*`)만 존재, 노드 1,437·관계 11,584, 다중 라벨 노드 0, 새 라벨 노드 0.
2. 백업(복구 가능): `C:\Users\Playdata\neo4j-backup-20261023-relabel\`
   - `before\graph_backup.json`: 전체 노드(라벨·속성·elementId), 관계(유형·양끝 업무 키), 제약·인덱스 `createStatement`
   - `before\fingerprint.json`: 라벨과 무관한 노드 속성·관계 집합·elementId SHA-256
   - `restore_graph.py`: 빈 그래프에만 복원(`--explain`으로 계획 검증 완료, 실행하지 않음)
3. 새 제약조건·인덱스를 빈 새 라벨에 생성 후 `db.awaitIndexes`.
4. 한 트랜잭션에서 `MATCH (n:RcpRecipe) SET n:rcp REMOVE n:RcpRecipe`(세 라벨 모두). 트랜잭션 안에서 이전 라벨 0건·새 라벨 건수를
   확인하고 다르면 롤백하도록 했다. 결과 `rcp` 1,156, `ingr` 275, `rcp_cat` 6.
5. 이전 인덱스 2개·제약조건 4개 삭제(`DROP ... IF EXISTS`, 이름 지정).

## 검증

| 항목 | 결과 |
|---|---|
| 라벨별 노드 | `rcp` 1,156, `ingr` 275, `rcp_cat` 6 (총 1,437) |
| 관계 | `RCP_USES` 10,428, `RCP_IN_RECIPE_CATEGORY` 1,156 (총 11,584), 패턴 `rcp→ingr`, `rcp→rcp_cat`만 존재 |
| 이전 라벨 노드 | 0 (`db.labels()` = `rcp`, `ingr`, `rcp_cat`) |
| 업무 ID 중복 | `rcp_id`·`rcp_seq`·`ingr_id`·`rcp_cat_id` 모두 0, 같은 양끝·유형 중복 관계 0 |
| 변경 전후 지문 | 노드 속성·관계 집합·elementId SHA-256 모두 동일 |
| PostgreSQL 정합성 | `load_recipe_graph --verify-only`: 노드·관계 업무 키 집합이 PostgreSQL 스냅샷과 일치, 분류 누락 0, 재료 없는 레시피 8(원천과 동일) |
| 별칭 검색 | `계란` → 표준 `달걀`, 레시피 186 |
| 여러 식재료 추천 | `계란+두부` 모두 포함 18, 보유 `계란·두부·양파` 후보 616(상위 20 반환), 분류 `반찬` 574 |
| GraphRAG 컨텍스트 | `graphrag_context` 1건, 재료·분류 수 PostgreSQL과 일치 |
| 재실행 중복 | `load_recipe_graph --apply`(같은 스냅샷 2회 MERGE): 두 번 모두 1,437/11,584, 실행 후 지문도 변경 전과 동일 |
| 단위 테스트 | `recipe_recommender/tests` 110개 통과 |
| DBeaver 예제 | `neo4j_user_verification.md`의 Cypher 16개를 읽기 전용으로 실행해 문서의 정상 결과와 일치 |

실제 구조: `neo4j_actual_schema.json`(실제 Neo4j 조회로 재생성), 구조도: `neo4j_erd.mmd`.
