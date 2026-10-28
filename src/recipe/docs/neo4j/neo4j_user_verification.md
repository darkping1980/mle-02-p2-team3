# DBeaver에서 레시피 그래프 직접 확인

대상은 현재 AuraDB 사용자 데이터베이스 `6ac1f0f8`이다. PostgreSQL의 `recipe` 스키마와 달리 Neo4j에는 별도 스키마가 없다. 아래 Cypher를 **각각 개별 실행**한다. 결과 그리드와 그래프 표시 방식은 DBeaver의 Neo4j 연결 설정에 따라 다를 수 있다. `RETURN p` 쿼리는 경로 객체를 돌려주므로 그래프 보기를 선택할 수 있다.

이 문서는 DBeaver에서 직접 실행하는 예제다. Python Repository가 호출하는 실행용 Named Cypher Mapper는 `recipe_recommender/recipe_graph_*.cypher`에 있다.

아래 "정상 결과"는 PostgreSQL 목표 모델 기준이며, 2026-10-22 초기화·재적재 후 모든 질의를 실제 실행해 확인했다(노드 1,437, 관계 11,584).
2026-10-23 노드 라벨을 PostgreSQL 테이블명(`rcp`, `ingr`, `rcp_cat`)으로 통일한 뒤 모든 질의를 다시 실행해 같은 결과를 확인했다(`neo4j_label_rename_20261023.md`).
기존 실습 데이터는 같은 날 정리되어 현재 DB에는 레시피 프로젝트 객체만 있다. 상세: `neo4j_target_model_migration.md`.

## 1. 노드 유형별 건수

```cypher
MATCH (n)
WHERE n:rcp OR n:ingr OR n:rcp_cat
UNWIND labels(n) AS label
WITH label WHERE label IN ['rcp', 'ingr', 'rcp_cat']
RETURN label, count(*) AS node_count
ORDER BY label;
```

정상 결과: `rcp` 1,156, `ingr` 275, `rcp_cat` 6. 라벨은 PostgreSQL `recipe` 스키마 테이블명과 같다. 식재료 분류 노드는 목표 모델에 없다.
이전 라벨(`RcpRecipe`, `RcpIngredient`, `RcpRecipeCategory`) 노드는 2026-10-23 명칭 통일 후 0건이어야 한다.

## 2. 관계 유형별 건수

```cypher
MATCH ()-[rel]->()
WHERE type(rel) STARTS WITH 'RCP_'
RETURN type(rel) AS relationship_type, count(*) AS relationship_count
ORDER BY relationship_type;
```

정상 결과: `RCP_USES` 10,428, `RCP_IN_RECIPE_CATEGORY` 1,156(`rcp_cat_rel` 행 수).

## 3. 레시피 28의 관계 그래프

```cypher
MATCH p=(r:rcp)-[:RCP_USES]->(i:ingr)
WHERE r.rcp_seq = '28'
RETURN p;
```

정상 결과: `새우 두부 계란찜` 레시피 노드 하나에서 표준 식재료 **7종**으로 이어지는 경로 7개. `rcp_seq`는 식약처 원본 번호이며 노드의 `rcp_id`와 다르다.

요리 종류 관계를 함께 보려면 다음을 별도 실행한다.

```cypher
MATCH p=(r:rcp)-[:RCP_IN_RECIPE_CATEGORY]->(c:rcp_cat)
WHERE r.rcp_seq = '28'
RETURN p;
```

정상 결과: 요리 분류 경로 1개(현재 데이터는 레시피당 분류 1개, 다중 분류 가능 구조).

## 4. 레시피 이름 검색과 동일 이름의 다른 레시피

```cypher
MATCH (r:rcp)
WHERE r.rcp_nm IN ['양배추롤', '버섯 리조또']
RETURN r.rcp_nm AS name, r.rcp_seq AS source_seq,
       r.rcp_id AS recipe_id
ORDER BY name, source_seq;
```

정상 결과: `양배추롤`은 원본 번호 **298, 536**, `버섯 리조또`는 **788, 919**로 각각 별도 노드다. 이름을 노드 식별자로 사용하지 않는다.

## 5. 식재료 이름에서 레시피 탐색

```cypher
MATCH (r:rcp)-[:RCP_USES]->(i:ingr)
WHERE i.ingr_nm = '칵테일새우'
RETURN i.ingr_id AS ingredient_id, i.ingr_nm AS ingredient,
       r.rcp_seq AS source_seq, r.rcp_nm AS recipe
ORDER BY source_seq;
```

정상 결과: `칵테일새우` 표준 식재료 키 `20261022_000180`에서 **17개 레시피**가 조회된다. 다른 새우 식재료와 이름 유사성만으로 병합하지 않는다.

## 6. 두 레시피의 공통 식재료

```cypher
MATCH (a:rcp {rcp_seq:'788'})-[:RCP_USES]->(i:ingr)<-[:RCP_USES]-(b:rcp {rcp_seq:'919'})
RETURN a.rcp_nm AS recipe_a, b.rcp_nm AS recipe_b,
       i.ingr_id AS ingredient_id, i.ingr_nm AS common_ingredient
ORDER BY common_ingredient;
```

두 `버섯 리조또`는 별도 레시피이며 각각 식재료 9종이다. 실제 조회에서 공통 식재료도 **9종**이었다. 이 쿼리는 교집합만 보여준다.

## 7. 제약조건과 인덱스

```cypher
SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties
WHERE name STARTS WITH 'rcp_' OR name STARTS WITH 'ingr_'
RETURN name, type, labelsOrTypes, properties ORDER BY name;
```

```cypher
SHOW INDEXES YIELD name, type, labelsOrTypes, properties, owningConstraint
WHERE name STARTS WITH 'rcp_' OR name STARTS WITH 'ingr_'
RETURN name, type, labelsOrTypes, properties, owningConstraint ORDER BY name;
```

정상 결과: 프로젝트 제약조건 **4개**(`rcp_key`, `ingr_key`, `rcp_cat_key`, `rcp_seq_key`).
인덱스는 제약조건 소유 RANGE 4개와 이름 검색용 RANGE 2개, 합계 **6개**다. 그 밖에는 Neo4j 기본 LOOKUP 인덱스 2개만 있다(다른 실습 제약조건은 2026-10-22 초기화 때 정리됨).

## 8. 중복과 분류 관계 누락

```cypher
MATCH (r:rcp)-[u:RCP_USES]->(i:ingr)
WITH r, i, count(u) AS n
WHERE n > 1
RETURN r.rcp_seq AS source_seq, i.ingr_nm AS ingredient, n;
```

```cypher
MATCH (r:rcp)
WHERE NOT (r)-[:RCP_IN_RECIPE_CATEGORY]->(:rcp_cat)
RETURN r.rcp_seq AS source_seq;
```

```cypher
MATCH (r:rcp)-[e:RCP_IN_RECIPE_CATEGORY]->(c:rcp_cat)
WITH r, c, count(e) AS n
WHERE n > 1
RETURN r.rcp_seq AS source_seq, c.rcp_cat_nm AS category, n;
```

정상 결과: 세 쿼리 모두 **0행**. 레시피는 요리 분류 관계가 1개 이상이어야 하고(다중 분류 허용), 같은 레시피·식재료/분류 쌍의 관계는 하나여야 한다.

## 9. 식재료 기반 검색(별칭 포함)

입력어는 앱과 같은 규칙(양끝 공백 제거·소문자화)으로 표준명 `ingr_nm_norm` 또는 별칭 `alias_names_norm`과 정확히 비교한다.

```cypher
// 계란이 들어가는 레시피: 별칭 '계란' → 표준 '달걀'
MATCH (i:ingr)
WHERE i.ingr_nm_norm = '계란' OR '계란' IN coalesce(i.alias_names_norm, [])
MATCH (r:rcp)-[:RCP_USES]->(i)
RETURN i.ingr_nm AS ingredient, count(r) AS recipes;
```

정상 결과: `달걀` **186**. 같은 쿼리에서 `'두부'`는 `두부` **110**(별도 식재료 `연두부`는 포함하지 않음), `'양파'`는 **443**.

```cypher
// 계란과 두부가 모두 들어가는 레시피
WITH ['계란', '두부'] AS terms
MATCH (r:rcp)
WHERE all(term IN terms WHERE EXISTS {
    MATCH (r)-[:RCP_USES]->(i:ingr)
    WHERE i.ingr_nm_norm = term OR term IN coalesce(i.alias_names_norm, [])
})
RETURN r.rcp_seq AS source_seq, r.rcp_nm AS recipe
ORDER BY recipe;
```

정상 결과: **18행**.

```cypher
// 계란·두부·양파 보유 시 부족 재료가 적은 레시피
UNWIND ['계란', '두부', '양파'] AS term
MATCH (i:ingr)
WHERE i.ingr_nm_norm = term OR term IN coalesce(i.alias_names_norm, [])
WITH collect(DISTINCT i) AS pantry
UNWIND pantry AS owned
MATCH (r:rcp)-[:RCP_USES]->(owned)
WITH r, pantry, collect(DISTINCT owned) AS matched
MATCH (r)-[:RCP_USES]->(needed:ingr)
WITH r, pantry, matched, collect(DISTINCT needed) AS all_ingredients
RETURN r.rcp_nm AS recipe, size(matched) AS matched_count,
       size(all_ingredients) - size(matched) AS missing_count,
       [x IN all_ingredients WHERE NOT (x IN pantry) | x.ingr_nm] AS missing
ORDER BY missing_count, matched_count DESC, recipe
LIMIT 20;
```

정상 결과: 후보 레시피 616개 중 부족 재료가 가장 적은(2개) 레시피부터 20행.

```cypher
// 특정 요리 분류(반찬)에 속한 레시피 수
MATCH (c:rcp_cat {rcp_cat_nm: '반찬'})<-[:RCP_IN_RECIPE_CATEGORY]-(r:rcp)
RETURN count(r) AS recipes;
```

정상 결과: **574**.
