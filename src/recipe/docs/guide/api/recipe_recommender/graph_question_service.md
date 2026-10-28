# graph_question_service 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.graph_question_service`
- **소스:** [recipe_recommender/graph_question_service.py](../../../../recipe_recommender/graph_question_service.py)
- **역할:** 그래프 관계 탐색 Service — 과제 질문 Q1~Q5를 고정 Named Cypher로 답한다 (Neo4j 읽기 전용, LLM 없음).
- **주요 호출자:** `streamlit_app.get_graph_question_service`, `streamlit_app.run_graph_question`(모드 B), 제출용 노트북은 같은 Cypher를 직접 실행
- **정의:** 클래스 3개, 모듈 함수 0개

- **직접 의존:** `.name_normalization`, `.pantry_graphrag`(조사 도우미 `josa`·`josa_ro`)

- **관련 API:** [recipe_graph_repository](recipe_graph_repository.md), [pantry_recommend_service](pantry_recommend_service.md)

**Cypher:** [graph_questions.cypher](../../../../recipe_recommender/graph_questions.cypher)(신규 4개)와 [recipe_graph_queries.cypher](../../../../recipe_recommender/recipe_graph_queries.cypher)(기존 4개 재사용). `ALLOWED_STATEMENTS` 8개는 모두 MATCH/RETURN만 쓴다(`GraphQuestionDefinitionTests`가 쓰기 절을 검사).

| 질문 | Hop | 관계 경로 | Named Cypher |
| --- | ---: | --- | --- |
| Q1 | 1 | `(:ingr)<-[:RCP_USES]-(:rcp)` | `recipe_graph_queries.recipes_by_ingredient_term` |
| Q2 | 2 | `(:rcp)-[:RCP_USES]->(:ingr)<-[:RCP_USES]-(:rcp)` | `recipe_graph_queries.similar_recipes` |
| Q3 | 3 | `(:rcp)-[:RCP_USES]->(:ingr)<-[:RCP_USES]-(:rcp)-[:RCP_IN_RECIPE_CATEGORY]->(:rcp_cat)` | `graph_questions.similar_recipe_categories` |
| Q4 | 2 | `(:rcp_cat)<-[:RCP_IN_RECIPE_CATEGORY]-(:rcp)-[:RCP_USES]->(:ingr)` | `graph_questions.category_ingredients` |
| Q5 | 1 | `(:rcp)-[:RCP_HAS_STEP]->(:rcp_step)` | `recipe_graph_queries.recipe_steps` |

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [GraphQuestion](#graphquestion) | dataclass DTO | 화면에 보여 줄 과제 질문 한 개의 정의(질문·hop·관계 경로·실행 Cypher). |
| [GraphAnswer](#graphanswer) | dataclass DTO | 질문 한 번의 Neo4j 조회 결과. ``rows`` 는 Cypher 반환 행 그대로(Q1만 중복 제거). |
| [GraphQuestionService](#graphquestionservice) | 클래스 | 과제 질문 Q1~Q5를 허용된 읽기 전용 Named Cypher로 실행한다. |

## GraphQuestion

**dataclass DTO.** 화면에 보여 줄 과제 질문 한 개의 정의(질문·hop·관계 경로·실행 Cypher).

- **정의:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (43행)
- **생성 위치:** 모듈 상수 `QUESTIONS`(키 'Q1'~'Q5')가 다섯 개를 만든다. `frozen=True`라 필드를 다시 대입할 수 없다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `key` | `str` | 'Q1'~'Q5'; 화면 선택과 테스트의 식별자. |
| `hop` | `int` | 패턴이 건너가는 관계 수. |
| `title` | `str` | 선택지에 보이는 짧은 이름. |
| `question` | `str` | 자연어 질문 형식; ``{target}``·``{eul}``(을/를)·``{gwa}``(과/와)·``{ro}``((으)로) 자리에 대상 이름을 넣는다. |
| `path` | `str` | 실제 Cypher 관계 경로. |
| `statement` | `str` | 실행하는 Named Cypher(``namespace.name``). |
| `parameter` | `str` | 필요한 입력: 'ingredient' \| 'recipe' \| 'category'. |

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [text](#graphquestion-text) | `str` | 대상 이름을 넣고 받침에 맞는 조사를 붙인 자연어 질문을 만든다. |

### GraphQuestion text

```python
def text(self, target: str) -> str:
```

- **주요 호출자:** `GraphQuestionService._answer`, `GraphQuestionService._not_found`
- **반환:** `str`. 예: `QUESTIONS['Q1'].text('두부')` → `'두부를 사용하는 레시피는 무엇인가?'`
- **원본:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (54행)

## GraphAnswer

**dataclass DTO.** 질문 한 번의 Neo4j 조회 결과. ``rows`` 는 Cypher 반환 행 그대로(Q1만 중복 제거).

- **정의:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (78행)
- **생성 위치:** `GraphQuestionService`의 질문 메서드가 만들고, 화면이 `st.session_state.graph_answer`에 보관한다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `question` | `GraphQuestion` | 실행한 질문 정의. |
| `question_text` | `str` | 파라미터를 채운 자연어 질문. |
| `parameters` | `dict` | Cypher에 전달한 바인딩 값. |
| `status` | `str` | 'ok'(1건 이상) \| 'empty'(0건) \| 'not_found'(입력한 식재료·레시피·분류가 DB에 없음) |
| `rows` | `list[dict]` | 표로 보여 줄 조회 행. |
| `message` | `str \| None` | 'empty'·'not_found'·해석 결과 안내 문장. |
| `resolved` | `list[dict]` | Q1 입력어 해석 결과 [{ingr_id, ingr_nm, matched_by}]. |
| `row_count` | `int` | `@property`로 계산되는 읽기 속성: 조회 결과 행 수. |

## GraphQuestionService

**클래스.** 과제 질문 Q1~Q5를 허용된 읽기 전용 Named Cypher로 실행한다.

- **정의:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (95행)
- **생성 위치:** `streamlit_app.get_graph_question_service`가 `get_pipeline().service.graph`(연결 검증을 마친 `RecipeGraphRepository`)를 주입해 만든다. 새 드라이버를 만들지 않는다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `graph` | `타입 힌트 없음` | 생성자 104행에서 설정; `query_example`·`mapper.select_list`·`statement_text`를 가진 Repository. |
| `_recipes` | `list[dict] \| None` | 생성자 105행에서 설정; 레시피 선택지 캐시. |
| `_categories` | `list[dict] \| None` | 생성자 106행에서 설정; 요리 분류 선택지 캐시. |

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#graphquestionservice-__init__) | `타입 힌트 없음` | ``graph`` 는 ``RecipeGraphRepository`` (또는 같은 ``query_example`` / ``mapper`` 를 가진 객체). |
| [_query](#graphquestionservice-_query) | `list[dict]` | 허용된 Named Cypher만 namespace에 맞는 조회 API로 실행한다. |
| [cypher_text](#graphquestionservice-cypher_text) | `str` | 질문이 실행하는 Cypher 원문(현재 화면에서는 사용하지 않음). |
| [recipe_options](#graphquestionservice-recipe_options) | `list[dict]` | ``[{rcp_id, rcp_nm, rcp_seq}]`` 레시피 선택지(이름·원본 번호 순, 한 번만 조회). |
| [category_options](#graphquestionservice-category_options) | `list[dict]` | ``[{rcp_cat_id, rcp_cat_nm}]`` 요리 분류 선택지(한 번만 조회). |
| [recipes_using_ingredient](#graphquestionservice-recipes_using_ingredient) | `GraphAnswer` | Q1 (1-hop) 입력한 식재료(표준명 또는 별칭)를 사용하는 레시피 전체. |
| [similar_recipes](#graphquestionservice-similar_recipes) | `GraphAnswer` | Q2 (2-hop) 기준 레시피와 공통 재료를 쓰는 다른 레시피(공통 재료 수·Jaccard 상위 20개). |
| [similar_recipe_categories](#graphquestionservice-similar_recipe_categories) | `GraphAnswer` | Q3 (3-hop) 공통 재료가 ``min_common`` 개 이상인 다른 레시피들의 요리 분류별 레시피 수. |
| [category_ingredients](#graphquestionservice-category_ingredients) | `GraphAnswer` | Q4 (2-hop) 요리 분류에 속한 레시피들이 사용하는 식재료(사용 레시피 수 상위 ``limit`` 개). |
| [recipe_steps](#graphquestionservice-recipe_steps) | `GraphAnswer` | Q5 (1-hop) 레시피의 식약처 원본 조리 단계(원본 MANUAL 번호 순). |

`_recipe`, `_answer`, `_not_found`는 내부 도우미다(선택지에서 레시피 찾기, `GraphAnswer` 조립).

### GraphQuestionService __init__

```python
def __init__(self, graph):
```

- **주요 호출자:** `streamlit_app.get_graph_question_service`, 테스트
- **원본:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (102행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `graph` | `타입 힌트 없음` | Neo4j 조회 Repository |

### GraphQuestionService _query

```python
def _query(self, statement: str, parameters: dict) -> list[dict]:
```

- **주요 호출자:** 이 클래스의 모든 질문·선택지 메서드
- **반환:** `list[dict]`. `recipe_graph_queries.*`면 `graph.query_example(name, params)`, 그 밖(`graph_questions.*`)이면 `graph.mapper.select_list(full_id, params)`.
- **원본:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (108행)

**예외:** ValueError: 읽기 허용 목록에 없는 식별자일 때. DB 예외는 잡지 않고 호출자에게 전달한다.

### GraphQuestionService cypher_text

```python
def cypher_text(self, key: str) -> str:
```

- **주요 호출자:** `streamlit_app.show_graph_answer`
- **반환:** `str`. `graph.statement_text(QUESTIONS[key].statement)` — 실행하지 않고 원문만 읽는다.
- **원본:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (128행)

### GraphQuestionService recipe_options

```python
def recipe_options(self) -> list[dict]:
```

- **주요 호출자:** `streamlit_app.graph_inputs`, `_recipe`
- **반환:** `list[dict]`. `graph_questions.recipe_options`를 최초 1회 조회해 캐시.
- **원본:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (132행)

### GraphQuestionService category_options

```python
def category_options(self) -> list[dict]:
```

- **주요 호출자:** `streamlit_app.graph_inputs`, `category_ingredients`
- **반환:** `list[dict]`. `graph_questions.category_options`를 최초 1회 조회해 캐시.
- **원본:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (138행)

### GraphQuestionService recipes_using_ingredient

```python
def recipes_using_ingredient(self, term: str) -> GraphAnswer:
```

- **주요 호출자:** `streamlit_app.run_graph_question`(Q1)
- **반환:** `GraphAnswer`. 행 ``{ingr_id, ingredient, rcp_id, rcp_seq, rcp_nm}`` (레시피명·ID 순, 레시피 중복 없음).
- **원본:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (163행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `term` | `str` | 사용자가 입력한 식재료명(예: '두부', 별칭 '계란'). |

**처리 흐름:** `normalize_name`으로 정규화 → `ingredient_name_candidates`로 해석. 없으면 레시피 쿼리 없이 `not_found`. 있으면 `recipes_by_ingredient_term` 실행 후 `rcp_id` 중복 제거. 별칭으로 해석되면 `message`에 표준명을 알린다.

### GraphQuestionService similar_recipes

```python
def similar_recipes(self, rcp_id: str) -> GraphAnswer:
```

- **주요 호출자:** `streamlit_app.run_graph_question`(Q2)
- **반환:** `GraphAnswer`. 행 ``{rcp_id, rcp_nm, common_count, common_ingredients, jaccard}``. `common_ingredients`는 Cypher `collect()` 결과라 원소 순서가 고정되지 않는다.
- **원본:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (199행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_id` | `str` | 기준 레시피 ID. 선택지에 없으면 `not_found`. |

### GraphQuestionService similar_recipe_categories

```python
def similar_recipe_categories(self, rcp_id: str, min_common: int=DEFAULT_MIN_COMMON) -> GraphAnswer:
```

- **주요 호출자:** `streamlit_app.run_graph_question`(Q3)
- **반환:** `GraphAnswer`. 행 ``{rcp_cat_nm, recipe_count, max_common_count, sample_recipes}``.
- **원본:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (215행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_id` | `str` | 기준 레시피 ID. |
| `min_common` | `int` | 공통 재료 최소 개수(1 미만은 1로 보정, 기본 `DEFAULT_MIN_COMMON`=3). |

### GraphQuestionService category_ingredients

```python
def category_ingredients(self, rcp_cat_nm: str, limit: int=DEFAULT_INGREDIENT_LIMIT) -> GraphAnswer:
```

- **주요 호출자:** `streamlit_app.run_graph_question`(Q4)
- **반환:** `GraphAnswer`. 행 ``{ingr_nm, recipe_count, category_recipe_count, category_ingredient_count}``.
- **원본:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (233행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_cat_nm` | `str` | 요리 분류명(예: '반찬'). 선택지에 없으면 `not_found`. |
| `limit` | `int` | 반환할 식재료 수(1~`MAX_INGREDIENT_LIMIT`=50으로 보정). |

### GraphQuestionService recipe_steps

```python
def recipe_steps(self, rcp_id: str) -> GraphAnswer:
```

- **주요 호출자:** `streamlit_app.run_graph_question`(Q5)
- **반환:** `GraphAnswer`. 행 ``{rcp_id, step_no, instruction_txt, image_url}`` — 정렬은 Cypher `ORDER BY step_no`.
- **원본:** [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) (250행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_id` | `str` | 레시피 ID. 단계가 없으면 `empty`. |

## 관련 가이드

- [그래프 관계 탐색 상세](../../details/06_graph_questions.md)
- [실행 흐름](../../04_execution_flow.md)
- [과제 질문지](../../../assignment/graph_questions.md)
