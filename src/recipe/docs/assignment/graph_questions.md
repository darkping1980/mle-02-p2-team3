# 그래프 질문지 — 1·2·3-hop

[과제 요약](README.md) · [Cypher와 실제 결과](query_results.md) · [검증 보고](test_report.md)

## 판정 기준

- **Hop = Cypher 패턴에서 건너가는 Neo4j 관계 수**입니다. LangGraph Node 실행 횟수가 아닙니다.
- 식재료 이름·별칭으로 시작 노드를 찾는 것(`ingr_nm_norm = $term_norm OR $term_norm IN alias_names_norm`)은 **노드 속성 비교**라 hop에 넣지 않습니다.
- 확정 대상은 2026-10-24 운영 AuraDB를 읽기 전용으로 조회해 데이터가 있고 의미 있는 결과가 나오는 것으로 골랐습니다.
  기준 레시피는 `된장 두부찌개`(식약처 원본 137번, 분류 국&찌개, 식재료 8개, 조리 단계 3개)입니다.

| 그래프 | 노드 | 관계 |
|---|---|---|
| 실측(2026-10-24) | `rcp` 1,156 · `ingr` 275 · `rcp_cat` 6 · `rcp_step` 6,717 (총 8,154) | `RCP_USES` 10,428 · `RCP_IN_RECIPE_CATEGORY` 1,156 · `RCP_HAS_STEP` 6,717 (총 18,301) |

초안 대비 바뀐 점: Q2·Q3·Q5의 "특정 레시피"를 `된장 두부찌개`로 정했고, Q3에 **공통 재료 3개 이상** 조건을 더했습니다
(1개 이상이면 소금·대파 같은 흔한 재료 하나로 공통 레시피 428개가 잡혀 분류 분포가 레시피 총수 분포와 비슷해짐).

---

## Q1 · 1-hop — 두부를 사용하는 레시피는 무엇인가?

| 항목 | 내용 |
|---|---|
| 목적 | 식재료 하나로 그 재료를 쓰는 레시피 전체를 찾는다(별칭 해석 포함) |
| 시작 → 도착 | `ingr`(두부) → `rcp` |
| 관계 경로 | `(:ingr)<-[:RCP_USES]-(:rcp)` |
| Hop 판정 | 1 — `RCP_USES` 1개. 별칭 해석은 속성 비교 |
| 실행 Cypher | 기존 `recipe_graph_queries.recipes_by_ingredient_term` (파라미터 `term_norm='두부'`) |
| 실제 결과 | 110행(레시피 110개, 중복 0). 별칭 `계란` → 표준 `달걀` 186행 |
| 결과 해석 | `연두부`(12)·`순두부`(11)는 별도 식재료 노드라 포함되지 않음 |
| 원본 검증 | PostgreSQL `rcp_ingr` + `ingr`/`ingr_als`에서 같은 정규화로 계산한 레시피 집합과 비교(`LiveGraphQuestionTests.test_q1_matches_postgres_including_alias`) |
| 정렬 | 레시피명, 레시피 ID |

## Q2 · 2-hop — 된장 두부찌개와 공통 재료를 사용하는 다른 레시피는 무엇인가?

| 항목 | 내용 |
|---|---|
| 목적 | 재료가 겹치는 비슷한 레시피를 찾는다 |
| 시작 → 도착 | `rcp`(된장 두부찌개) → `ingr` → 다른 `rcp` |
| 관계 경로 | `(:rcp)-[:RCP_USES]->(:ingr)<-[:RCP_USES]-(:rcp)` |
| Hop 판정 | 2 — `RCP_USES`를 두 번(레시피→재료, 재료←다른 레시피) |
| 실행 Cypher | 기존 `recipe_graph_queries.similar_recipes` (파라미터 `rcp_id`) |
| 중복 처리 | 다른 레시피별 `count(DISTINCT shared)` 집계 → 공통 재료가 5개여도 레시피는 1행 |
| 정렬 | 공통 재료 수 ↓, Jaccard ↓, 레시피 ID — 상위 20개 |
| 실제 결과 | 20행. 1위 `부대된장찌개`(공통 5, Jaccard 0.357), 2위 `들깨된장육개장`(공통 5, 0.294) |
| 결과 해석 | 상위 10개가 모두 찌개·국 — 두부·대파·청양고추·김치·된장을 함께 씀 |
| 원본 검증 | PostgreSQL `rcp_ingr`에서 공통 재료 수·Jaccard를 계산해 상위 20개 순서·공통 재료 집합까지 비교(`test_q2_matches_postgres_top20_order`) |

## Q3 · 3-hop — 된장 두부찌개와 공통 재료(3개 이상)를 사용하는 다른 레시피들은 어떤 요리 분류에 속하는가?

| 항목 | 내용 |
|---|---|
| 목적 | 비슷한 레시피들이 어느 분류에 모이는지 본다 |
| 시작 → 도착 | `rcp` → `ingr` → 다른 `rcp` → `rcp_cat` |
| 관계 경로 | `(:rcp)-[:RCP_USES]->(:ingr)<-[:RCP_USES]-(:rcp)-[:RCP_IN_RECIPE_CATEGORY]->(:rcp_cat)` |
| Hop 판정 | 3 — `RCP_USES` 2개 + `RCP_IN_RECIPE_CATEGORY` 1개 |
| 실행 Cypher | **신규** `graph_questions.similar_recipe_categories` (파라미터 `rcp_id`, `min_common=3`) |
| 중복 처리 | 다른 레시피는 `count(DISTINCT shared)`로 1회 집계 후 조건 적용, 분류별 `count(DISTINCT other)` |
| 정렬 | 분류별 레시피 수 ↓, 분류명. 예시 레시피는 공통 재료 수 ↓, 이름, ID 순 최대 5개 |
| 실제 결과 | 5행: 국&찌개 26 · 반찬 10 · 밥 4 · 일품 3 · 기타 1 (합계 44개 레시피) |
| 결과 해석 | 재료를 많이 공유할수록 같은 분류(국&찌개)에 모인다. `min_common=1`이면 1위가 반찬 236으로 바뀜 |
| 원본 검증 | PostgreSQL `rcp_ingr`·`rcp_cat_rel`로 같은 계산(k=1, 3) 비교 + 예시 레시피마다 3-hop 경로가 실제로 있는지(`length(p)=3`) 확인. 노트북에서 pandas로도 같은 표 |

## Q4 · 2-hop — 반찬으로 분류된 레시피에서 사용하는 식재료는 무엇인가?

| 항목 | 내용 |
|---|---|
| 목적 | 분류별로 많이 쓰는 식재료를 본다 |
| 시작 → 도착 | `rcp_cat`(반찬) → `rcp` → `ingr` |
| 관계 경로 | `(:rcp_cat)<-[:RCP_IN_RECIPE_CATEGORY]-(:rcp)-[:RCP_USES]->(:ingr)` |
| Hop 판정 | 2 — `RCP_IN_RECIPE_CATEGORY` 1개 + `RCP_USES` 1개 |
| 실행 Cypher | **신규** `graph_questions.category_ingredients` (파라미터 `rcp_cat_nm='반찬'`, `limit`) |
| 중복 처리 | 식재료별 `count(DISTINCT r)` |
| 정렬 | 사용 레시피 수 ↓, 식재료명 — 상위 `limit`개(화면 기본 20) |
| 실제 결과 | 반찬 574개 레시피가 263종 사용. 양파 227 · 소금 200 · 설탕 186 · 다진 마늘 133 · 마늘 133 |
| 결과 해석 | 기본 채소·양념이 상위. `다진 마늘`과 `마늘`은 사전상 다른 표준명 |
| 원본 검증 | PostgreSQL 비교(`test_q4_matches_postgres`) + **노트북 pandas 대조**(상위 50개 완전 일치) |

## Q5 · 1-hop — 된장 두부찌개의 조리 단계와 순서는 무엇인가?

| 항목 | 내용 |
|---|---|
| 목적 | 레시피의 식약처 원본 조리 과정을 순서대로 본다 |
| 시작 → 도착 | `rcp` → `rcp_step` |
| 관계 경로 | `(:rcp)-[:RCP_HAS_STEP]->(:rcp_step)` |
| Hop 판정 | 1 — `RCP_HAS_STEP` 1개 |
| 실행 Cypher | 기존 `recipe_graph_queries.recipe_steps` (파라미터 `rcp_ids=[rcp_id]`) |
| 정렬 | 원본 MANUAL 번호(`step_no`) — 번호를 다시 매기지 않음 |
| 실제 결과 | 3행(1·2·3단계), 단계 사진 URL 3개 |
| 결과 해석 | 원본 `MANUAL01~03`과 칸 수·문장이 같음. 사진 URL은 원본 `http://`(화면에서만 `https://`) |
| 원본 검증 | PostgreSQL `rcp_step` 번호·문장 비교(`test_q5_matches_postgres_step_order_and_text`) + 노트북에서 `rcp_raw.manual01~20` 칸 수 대조 |
