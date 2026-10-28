# Cypher와 실제 조회 결과

[과제 요약](README.md) · [질문지](graph_questions.md) · [검증 보고](test_report.md)

- **조회 시점·대상**: 2026-10-24. 운영 AuraDB(읽기 전용 세션)와, 같은 PostgreSQL 스냅샷을 프로젝트 ETL로 넣은 로컬 테스트 Neo4j 양쪽에서 실행했습니다. 아래 결과는 두 DB에서 같았습니다(`collect()` 목록은 원소 순서만 정렬해 비교).
- Cypher는 서비스가 실행하는 `.cypher` 파일 원문입니다. 주석은 줄였습니다. 원문: [recipe_graph_queries.cypher](../../recipe_recommender/recipe_graph_queries.cypher), [graph_questions.cypher](../../recipe_recommender/graph_questions.cypher).
- 표는 상위 일부만 옮겼습니다. 전체 결과는 [제출용 노트북](김병주_34과제.ipynb)의 출력에 있습니다.

## Q1 · 1-hop — `recipe_graph_queries.recipes_by_ingredient_term`

```cypher
MATCH (i:ingr)
WHERE i.ingr_nm_norm = $term_norm OR $term_norm IN coalesce(i.alias_names_norm, [])
MATCH (r:rcp)-[:RCP_USES]->(i)
RETURN i.ingr_id AS ingr_id, i.ingr_nm AS ingredient,
       r.rcp_id AS rcp_id, r.rcp_seq AS rcp_seq, r.rcp_nm AS rcp_nm
ORDER BY r.rcp_nm, r.rcp_id;
```

파라미터 `{term_norm: '두부'}` → **110행**(레시피 110개, 중복 0). `{term_norm: '계란'}` → 표준 식재료 `달걀`, **186행**.

| rcp_nm | rcp_seq | ingredient |
|---|---|---|
| 가지 탕수육 | 3246 | 두부 |
| 가지볶음밥 | 215 | 두부 |
| 간편콩국수 | 342 | 두부 |
| 감자느타리버섯국 | 674 | 두부 |
| 겨자아욱쌈밥 | 615 | 두부 |
| 견과류들깨해장탕 | 264 | 두부 |
| 고구마순나물 | 3005 | 두부 |
| 곤약함박스테이크 | 296 | 두부 |
| 관자해장국 | 263 | 두부 |
| 굴 두부 국 | 875 | 두부 |

해석: 표준명 `두부`만 찾습니다. `연두부`·`순두부`는 다른 노드라 빠집니다.

## Q2 · 2-hop — `recipe_graph_queries.similar_recipes`

```cypher
MATCH (base:rcp {rcp_id: $rcp_id})
MATCH (base)-[:RCP_USES]->(shared:ingr)<-[:RCP_USES]-(candidate:rcp)
WHERE candidate <> base
WITH base, candidate, count(DISTINCT shared) AS common_count,
     collect(DISTINCT shared.ingr_nm) AS common_ingredients
WITH candidate, common_count, common_ingredients,
     size([(base)-[:RCP_USES]->() | 1]) AS base_total,
     size([(candidate)-[:RCP_USES]->() | 1]) AS candidate_total
RETURN candidate.rcp_id AS rcp_id,
       candidate.rcp_nm AS rcp_nm, common_count, common_ingredients,
       toFloat(common_count) / (base_total + candidate_total - common_count) AS jaccard
ORDER BY common_count DESC, jaccard DESC, rcp_id
LIMIT 20;
```

파라미터 `{rcp_id: <된장 두부찌개>}` → **20행**, 중복 레시피 0.

| rcp_nm | common_count | common_ingredients | jaccard |
|---|---|---|---|
| 부대된장찌개 | 5 | 김치, 대파, 두부, 청양고추, 홍고추 | 0.357 |
| 들깨된장육개장 | 5 | 고춧가루, 대파, 돼지고기, 된장, 청양고추 | 0.294 |
| 완자김치찌개 | 4 | 김치, 대파, 두부, 홍고추 | 0.308 |
| 배추된장국 | 4 | 대파, 된장, 두부, 청양고추 | 0.308 |
| 쑥갓부대찌개 | 4 | 고춧가루, 김치, 두부, 청양고추 | 0.250 |
| 오징어김치찌개 | 4 | 김치, 대파, 두부, 홍고추 | 0.211 |
| 닭고기김치찌개 | 4 | 김치, 대파, 두부, 청양고추 | 0.190 |
| 굴림만두된장국 | 4 | 대파, 돼지고기, 두부, 홍고추 | 0.190 |
| 삼계부대찌개 | 4 | 고춧가루, 김치, 대파, 홍고추 | 0.182 |
| 된장국 | 3 | 대파, 된장, 두부 | 0.273 |

해석: 상위가 모두 찌개·국입니다. `common_ingredients`는 `collect()` 결과라 원소 순서가 실행마다 다를 수 있어 이 표에서는 이름순으로 적었습니다.

## Q3 · 3-hop — `graph_questions.similar_recipe_categories` (신규)

```cypher
MATCH (base:rcp {rcp_id: $rcp_id})-[:RCP_USES]->(shared:ingr)<-[:RCP_USES]-(other:rcp)
WHERE other <> base
WITH other, count(DISTINCT shared) AS common_count
WHERE common_count >= $min_common
MATCH (other)-[:RCP_IN_RECIPE_CATEGORY]->(c:rcp_cat)
WITH c, other, common_count
ORDER BY common_count DESC, other.rcp_nm, other.rcp_id
RETURN c.rcp_cat_nm AS rcp_cat_nm, count(DISTINCT other) AS recipe_count,
       max(common_count) AS max_common_count, collect(other.rcp_nm)[0..5] AS sample_recipes
ORDER BY recipe_count DESC, rcp_cat_nm;
```

파라미터 `{rcp_id: <된장 두부찌개>, min_common: 3}` → **5행**(레시피 44개).

| rcp_cat_nm | recipe_count | max_common_count | sample_recipes |
|---|---|---|---|
| 국&찌개 | 26 | 5 | 들깨된장육개장, 부대된장찌개, 굴림만두된장국, 닭고기김치찌개, 배추된장국 |
| 반찬 | 10 | 3 | 가지겉절이, 골뱅이과일무침, 논우렁순무섞박지, 단호박제육볶음, 맥적구이 |
| 밥 | 4 | 3 | 꽃밥, 봄주먹밥, 오이냉국을 곁들인 오색쌈밥, 죽순콩나물밥 |
| 일품 | 3 | 3 | 낙지볶음면, 돈수육, 해물냉채, 숙주라면 |
| 기타 | 1 | 3 | 돼지고기 포두부 파스타 |

`min_common: 1`이면 6행: 반찬 236 · 국&찌개 70 · 일품 66 · 밥 41 · 후식 9 · 기타 6 (레시피 428개).

해석: 재료를 3개 이상 공유하는 레시피는 국&찌개에 모입니다(59%). 조건을 1개로 낮추면 흔한 재료 때문에 레시피가 가장 많은 반찬이 1위가 됩니다.
pandas 대조(노트북): PostgreSQL 표를 세 번 이어 붙인 결과와 `rcp_cat_nm · recipe_count · max_common_count`가 같음.

## Q4 · 2-hop — `graph_questions.category_ingredients` (신규)

```cypher
MATCH (c:rcp_cat {rcp_cat_nm: $rcp_cat_nm})<-[:RCP_IN_RECIPE_CATEGORY]-(r:rcp)
WITH c, count(r) AS category_recipe_count
MATCH (c)<-[:RCP_IN_RECIPE_CATEGORY]-(r:rcp)-[:RCP_USES]->(i:ingr)
WITH category_recipe_count, i, count(DISTINCT r) AS recipe_count
ORDER BY recipe_count DESC, i.ingr_nm
WITH category_recipe_count, collect({ingr_nm: i.ingr_nm, recipe_count: recipe_count}) AS ranked
UNWIND ranked[0..$limit] AS row
RETURN row.ingr_nm AS ingr_nm, row.recipe_count AS recipe_count,
       category_recipe_count, size(ranked) AS category_ingredient_count
ORDER BY recipe_count DESC, ingr_nm;
```

파라미터 `{rcp_cat_nm: '반찬', limit: 50}` → **50행**. `category_recipe_count` 574, `category_ingredient_count` 263.

| ingr_nm | recipe_count |
|---|---|
| 양파 | 227 |
| 소금 | 200 |
| 설탕 | 186 |
| 다진 마늘 | 133 |
| 마늘 | 133 |
| 식초 | 130 |
| 당근 | 121 |
| 후춧가루 | 109 |
| 참기름 | 98 |
| 물 | 94 |

해석: 반찬의 약 40%가 양파를 씁니다. **pandas 대조**: `rcp_cat`·`rcp_cat_rel`·`rcp_ingr`·`ingr`을 이어 붙여 같은 정렬로 계산한 상위 50개가 Cypher 결과와 `DataFrame.equals`로 같았습니다(재료가 연결된 반찬 레시피 569개 + 재료 없는 반찬 5개 = 574).

## Q5 · 1-hop — `recipe_graph_queries.recipe_steps`

```cypher
UNWIND $rcp_ids AS id
MATCH (r:rcp {rcp_id: id})-[:RCP_HAS_STEP]->(s:rcp_step)
RETURN r.rcp_id AS rcp_id, s.step_no AS step_no,
       s.rcp_step_instruction_txt AS instruction_txt, s.rcp_step_image_url AS image_url
ORDER BY rcp_id, step_no;
```

파라미터 `{rcp_ids: [<된장 두부찌개>]}` → **3행**.

| step_no | instruction_txt | image_url |
|---|---|---|
| 1 | 두부에 쌀뜨물을 넣고 갈아준다. | http://www.foodsafetykorea.go.kr/uploadimg/cook/20_00137_1.png |
| 2 | 돼지고기는 썰고 김치는 물에 씻어 양념을 제거하고 3×3cm로 썬다. | http://www.foodsafetykorea.go.kr/uploadimg/cook/20_00137_2.png |
| 3 | 냄비에 돼지고기와 김치를 함께 볶은 후, 망에 거른 된장과 1의 두부, 고춧가루, 청양고추, 홍고추를 넣어 끓이다가 대파를 넣어 완성한다. | http://www.foodsafetykorea.go.kr/uploadimg/cook/20_00137_3.png |

해석: 원본 `MANUAL01~03`과 같은 3단계입니다. 설명·URL은 식약처 원본이며 LLM이 만들지 않았습니다.
