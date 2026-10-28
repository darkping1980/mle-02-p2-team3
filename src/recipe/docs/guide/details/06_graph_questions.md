# 그래프 관계 탐색 상세 (모드 B)

[메인](../README.md) · [Streamlit](01_streamlit.md) · [Neo4j Repository](04_neo4j_repository.md) · [과제 질문지](../../assignment/graph_questions.md)

원본: [graph_question_service.py](../../../recipe_recommender/graph_question_service.py), [graph_questions.cypher](../../../recipe_recommender/graph_questions.cypher), [streamlit_app.py](../../../streamlit_app.py)의 `show_graph_explorer` 이하. API: [graph_question_service](../api/recipe_recommender/graph_question_service.md).

## 왜 별도 모드인가

모드 A(냉장고 재료 추천)는 입력 문장에서 **식재료**만 뽑아 추천한다. 2026-10-24 실제 앱(AuraDB·LLM)에 과제 질문을 그대로 넣어 본 결과:

| 질문 | 모드 A 결과 | 분류 |
| --- | --- | --- |
| Q1 두부를 사용하는 레시피 | `두부`로 해석, 추천 상위 5개만 표시(110개 전체 아님) | 기존 추천 기능으로만 처리 |
| Q2 된장 두부찌개와 공통 재료 레시피 | 레시피명을 재료 `된장`+`두부`로 해석해 추천 | 잘못된 결과 반환 |
| Q3 공통 재료 레시피들의 분류 | Q2와 같음, 분류 집계 없음 | 잘못된 결과 반환 |
| Q4 반찬 레시피의 식재료 | 문장 전체를 재료 하나로 보고 DB에 없음 → 0건 | 질문 해석 실패 |
| Q5 된장 두부찌개의 조리 단계 | 재료 `된장`+`두부` 추천(카드 하나에 우연히 조리 과정이 있음) | 잘못된 결과 반환 |

그래서 범용 Text-to-Cypher 대신 **질문 5개 × 파라미터화 Cypher**를 고르는 화면을 더했다. LLM은 쓰지 않는다(질문 분류가 필요 없고, LLM이 Cypher를 만들거나 결과를 지어낼 여지를 없앰). LangGraph 흐름도 바꾸지 않았다.

## 질문과 Cypher

| 질문 | Hop | 경로 | Named Cypher | 기존/신규 |
| --- | ---: | --- | --- | --- |
| Q1 | 1 | `(:ingr)<-[:RCP_USES]-(:rcp)` | `recipe_graph_queries.recipes_by_ingredient_term` | 기존 |
| Q2 | 2 | `(:rcp)-[:RCP_USES]->(:ingr)<-[:RCP_USES]-(:rcp)` | `recipe_graph_queries.similar_recipes` | 기존 |
| Q3 | 3 | `(:rcp)-[:RCP_USES]->(:ingr)<-[:RCP_USES]-(:rcp)-[:RCP_IN_RECIPE_CATEGORY]->(:rcp_cat)` | `graph_questions.similar_recipe_categories` | 신규 |
| Q4 | 2 | `(:rcp_cat)<-[:RCP_IN_RECIPE_CATEGORY]-(:rcp)-[:RCP_USES]->(:ingr)` | `graph_questions.category_ingredients` | 신규 |
| Q5 | 1 | `(:rcp)-[:RCP_HAS_STEP]->(:rcp_step)` | `recipe_graph_queries.recipe_steps` | 기존 |

- Hop은 관계를 건너가는 횟수다. 식재료 이름·별칭 해석은 노드 속성 비교라 넣지 않는다.
- 중복: Q2·Q3은 다른 레시피별 `count(DISTINCT shared)`, Q3 분류별 `count(DISTINCT other)`, Q4 `count(DISTINCT r)`, Q1은 Service에서 `rcp_id` 중복 제거.
- 정렬: Q1 레시피명·ID / Q2 공통 재료 수↓·Jaccard↓·ID(상위 20) / Q3 레시피 수↓·분류명 / Q4 레시피 수↓·식재료명 / Q5 원본 단계 번호.
- `graph_questions.recipe_options`·`category_options`는 화면 선택지용(관계 탐색 없음)이다.

## 상태와 오류

| 상황 | `GraphAnswer.status` | 화면 |
| --- | --- | --- |
| 1건 이상 | `ok` | 표 + 요약 캡션. 별칭이면 info로 표준명 안내 |
| 0건(예: Q3 `min_common`이 너무 큼, 단계 없는 레시피) | `empty` | info "…없습니다", 배지 `0건`, 표 없음 |
| 입력한 식재료·레시피·분류가 DB에 없음 | `not_found` | warning, 쿼리는 실행하지 않음 |
| DB 예외 | (예외 전파) | `show_graph_explorer`가 `st.error`로 표시, 앱은 계속 동작 |

## 테스트

[test_graph_questions.py](../../../recipe_recommender/tests/test_graph_questions.py): Mock(`FakeQuestionGraph`) 22건 — Service 분기·중복 제거·0건·대상 없음·별칭·예외 전파·허용 쿼리 읽기 전용·hop 선언·화면 모드 B·모드 A 회귀. 실제 DB 10건 — AuraDB 결과를 같은 시점 PostgreSQL 스냅샷에서 계산한 기대값과 대조(Q1~Q5), Q3 예시 레시피의 3-hop 경로 존재, 실제 DB 화면, 2026-10-24 고정 값(시점 의존).
