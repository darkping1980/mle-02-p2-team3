# streamlit_app 모듈

[API 전체 목차](README.md) · [패키지 요약](README.md) · [파일 인덱스](../02_file_structure.md)

## Module Summary

- **모듈:** `streamlit_app.py` (패키지 밖 실행 파일)
- **소스:** [streamlit_app.py](../../../streamlit_app.py)
- **역할:** 냉장고 재료 추천 GraphRAG 웹 화면 (Streamlit).
- **주요 호출자:** Streamlit 실행기; 폼 제출 시 `run_pipeline`
- **정의:** 클래스 0개, 모듈 함수 16개

- **직접 의존:** `recipe_recommender.config`, `recipe_recommender.graph_question_service`, `recipe_recommender.pantry_graphrag`, `recipe_recommender.pantry_recommend_service`, `recipe_recommender.tools._connection_util`

- **관련 API:** [pantry_graphrag](recipe_recommender/pantry_graphrag.md), [pantry_recommend_service](recipe_recommender/pantry_recommend_service.md), [recipe_graph_repository](recipe_recommender/recipe_graph_repository.md)

화면 상단 `사용 모드`(`st.segmented_control`, key `app_mode`)가 `pantry`(모드 A, 기존 추천)와 `graph`(모드 B, 그래프 관계 탐색)를 고른다. 모드 B는 `show_graph_explorer()` 후 `st.stop()`으로 끝나 모드 A 코드를 실행하지 않는다. 시작 시 `configure_query_logging(default=local_dev_query_log_default())`을 호출한다. 저장소 루트에 `.env`가 있는 로컬 실행은 기본 ON, `.env`가 없는 Streamlit Cloud는 기본 OFF이며 `RECIPE_QUERY_LOG`가 우선한다. 모드 A의 추천 결과는 Neo4j가 만들고, 로그 ON에서만 첫 추천 레시피를 PostgreSQL로 추가 조회해 SQL을 터미널에 남긴다. Streamlit은 위젯 조작마다 이 파일을 재실행한다. `get_pipeline`의 리소스 캐시와 `session_state.outcome`이 연결 객체와 마지막 결과를 유지한다.

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [get_pipeline](#function-get_pipeline) | `타입 힌트 없음` | 화면 재실행 사이에 재사용할 GraphRAG 파이프라인을 생성한다. |
| [get_log_check_search_service](#function-get_log_check_search_service) | `타입 힌트 없음` | 로그 ON에서 쓰는 PostgreSQL 상세 조회 Service를 캐시한다. |
| [run_postgres_log_check](#function-run_postgres_log_check) | `None` | 첫 추천 레시피를 조회해 SQL 로그를 검증하며 추천 결과는 바꾸지 않는다. |
| [run_pipeline](#function-run_pipeline) | `dict` | 폼 제출 시 GraphRAG를 실행하고 화면 보관용 값으로 직렬화한다. |
| [show_llm_status](#function-show_llm_status) | `None` | ``answer.llm_status``에 따라 LLM 검증 또는 대체 응답 상태를 표시한다. |
| [source_badge](#function-source_badge) | `None` | 요약과 레시피 이유가 LLM 또는 근거 규칙 중 어디서 왔는지 표시한다. |
| [escape_markdown](#function-escape_markdown) | `str` | 원본 문장을 Markdown 서식 없이 글자 그대로 보이도록 특수 문자를 이스케이프한다. |
| [show_image](#function-show_image) | `bool` | 식약처 이미지 URL을 표시한다. 표시할 수 없으면 아무것도 그리지 않고 ``False`` 를 반환한다. |
| [show_steps](#function-show_steps) | `None` | 레시피의 식약처 원본 조리 과정을 펼침 영역에 번호 순서대로 보여 준다. |
| [get_graph_question_service](#function-get_graph_question_service) | `GraphQuestionService` | 추천 파이프라인의 ``RecipeGraphRepository`` 를 재사용하는 그래프 탐색 Service를 만든다. |
| [graph_inputs](#function-graph_inputs) | `dict` | 질문에 필요한 대상(식재료·레시피·분류)과 조건 위젯을 그리고 선택값을 돌려준다. |
| [run_graph_question](#function-run_graph_question) | `GraphAnswer` | 선택한 질문에 맞는 Service 메서드를 호출한다. DB 예외는 호출자에게 전달한다. |
| [graph_table](#function-graph_table) | `list[dict]` | 조회 행을 화면 열 이름으로 바꾼다(값은 바꾸지 않고 목록만 쉼표로 잇는다. 이미지는 표시용 URL). |
| [graph_summary](#function-graph_summary) | `str \| None` | 조회 행만으로 만든 한 줄 결과 요약(LLM 미사용). 결과가 없으면 ``None``. |
| [show_graph_answer](#function-show_graph_answer) | `None` | 질문 문장·hop·관계 경로·조회 결과 표를 보여 준다. |
| [show_graph_explorer](#function-show_graph_explorer) | `None` | 모드 B: 과제 질문 Q1~Q5를 고르고 대상을 정해 Neo4j를 조회한다(읽기 전용, LLM 미사용). |

## Function get_pipeline

```python
@st.cache_resource(show_spinner='Neo4j AuraDB와 LLM 연결을 준비하는 중입니다...')
def get_pipeline():
```

- **호출자:** Streamlit 실행기; 폼 제출 시 `run_pipeline`
- **반환:** `타입 힌트 없음`. 화면 재실행 사이에 재사용할 GraphRAG 파이프라인을 생성한다.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (90행)

**예외:** Exception: Neo4j 연결 검증 또는 의존 객체 생성에 실패하면 화면으로 전파한다.

## Function get_log_check_search_service

```python
@st.cache_resource(show_spinner=False)
def get_log_check_search_service():
```

- **호출자:** `run_postgres_log_check`(로그 ON이며 추천 결과가 있을 때).
- **반환:** 타입 힌트 없음. `RecipeSearchService` 인스턴스.
- **처리:** `create_recipe_sql_session()`을 기본 인자로 호출하고 세션의 `DatabaseManager.close`를 `atexit`에 등록한 뒤 Service에 주입한다. Streamlit 리소스 캐시가 재실행 사이에 객체를 재사용한다. SQL 세션은 실제 조회 때 연결된다.
- **관련 API:** [RecipeSearchService](recipe_recommender/recipe_search_service.md), [create_recipe_sql_session](recipe_recommender/database.md#function-create_recipe_sql_session).
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (110행)

## Function run_postgres_log_check

```python
def run_postgres_log_check(outcome: dict) -> None:
```

- **호출자:** 모드 A 추천 폼 제출 블록에서 `run_pipeline`이 성공한 직후.
- **매개변수:** `outcome`은 `run_pipeline`이 만든 화면 결과 `dict`이며 `result.recommendations[0].rcp_id`를 읽는다.
- **반환:** `None`. 조회한 PostgreSQL 상세 결과는 화면·Session State에 쓰지 않는다.
- **처리:** `query_logging_active()`가 거짓이거나 추천이 비면 즉시 반환한다. 그 외에는 첫 추천 ID로 `RecipeSearchService.get_recipe_detail()`을 호출한다. 내부에서 상세·단계·재료·미등록 재료의 Named SQL SELECT 4개를 실행하고 공통 SQL logger가 렌더링한다.
- **예외·부작용:** PostgreSQL 조회 실패나 결과 없음은 경고 로그만 남긴다. Neo4j 추천 결과는 유지된다. 로그 OFF에서는 PostgreSQL 세션도 만들지 않는다.
- **관련 API:** [query_logging_active](recipe_recommender/config.md#function-query_logging_active), [RecipeSearchService](recipe_recommender/recipe_search_service.md), [검증 기록](../details/07_query_log_verification.md#12-인수인계-최종-검증).
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (129행)

## Function run_pipeline

```python
def run_pipeline(rag: PantryGraphRAG, question: str, limit: int, sort: str) -> dict:
```

- **호출자:** Streamlit 실행기; 폼 제출 시 `run_pipeline`
- **반환:** `dict`. 폼 제출 시 GraphRAG를 실행하고 화면 보관용 값으로 직렬화한다.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (109행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rag` | `PantryGraphRAG` | 캐시된 추천 파이프라인. |
| `question` | `str` | 사용자가 입력한 재료 또는 문장. |
| `limit` | `int` | 표시할 추천 건수. |
| `sort` | `str` | ``coverage`` 또는 ``missing`` 정렬 방식. |

**처리 흐름:** GraphRAG 최종 State의 DTO를 dict로 바꿔 Streamlit Session State에 저장할 결과를 만든다.

**관련 API:** [pantry_graphrag](recipe_recommender/pantry_graphrag.md), [pantry_recommend_service](recipe_recommender/pantry_recommend_service.md), [recipe_graph_repository](recipe_recommender/recipe_graph_repository.md)

## Function show_llm_status

```python
def show_llm_status(answer: dict) -> None:
```

- **호출자:** Streamlit 실행기; 폼 제출 시 `run_pipeline`
- **반환:** `None`. ``answer.llm_status``에 따라 LLM 검증 또는 대체 응답 상태를 표시한다.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (130행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `answer` | `dict` | ``PantryGraphRAG.answer``가 만든 설명과 상태값. |

## Function source_badge

```python
def source_badge(source: str) -> None:
```

- **호출자:** Streamlit 실행기; 폼 제출 시 `run_pipeline`
- **반환:** `None`. 요약과 레시피 이유가 LLM 또는 근거 규칙 중 어디서 왔는지 표시한다.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (152행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `source` | `str` | ``llm``이면 LLM 배지, 그 밖에는 규칙 기반 배지. |

## Function escape_markdown

```python
def escape_markdown(text: str) -> str:
```

- **호출자:** `show_steps`
- **반환:** `str`. 원본 문장을 Markdown 서식 없이 글자 그대로 보이도록 특수 문자를 이스케이프한다.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (164행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `text` | `str` | 식약처 원본 조리 설명. |

## Function show_image

```python
def show_image(url: str | None, *, alt: str, width: int | str) -> bool:
```

- **호출자:** 추천 카드(대표 이미지), `show_steps`(단계 이미지)
- **반환:** `bool`. 식약처 이미지 URL을 표시한다. 표시할 수 없으면 아무것도 그리지 않고 ``False`` 를 반환한다.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (169행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `url` | `str \| None` | Neo4j에 적재된 원본 이미지 URL. |
| `alt` | `str` | 보조 기술용 이미지 이름. |
| `width` | `int \| str` | ``st.image`` 의 ``width``. |

**처리 흐름:** `display_image_url`로 표시 가능 여부를 확인한 뒤 `st.image(url)`을 만든다. URL 문자열은 Streamlit 서버가 내려받지 않고 브라우저가 직접 받으므로 원격 서버 장애는 그 이미지 칸에만 영향을 준다. 요소 생성 예외는 잡아서 로그만 남긴다.

## Function show_steps

```python
def show_steps(rec: dict, step_error: str | None) -> None:
```

- **호출자:** 추천 카드 렌더링(레시피마다 한 번)
- **반환:** `None`. 레시피의 식약처 원본 조리 과정을 펼침 영역에 번호 순서대로 보여 준다.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (194행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rec` | `dict` | ``Recommendation`` 을 dict로 바꾼 값(``steps`` 포함). |
| `step_error` | `str \| None` | 조리 과정 조회 실패 사유. 있으면 안내 문구만 보여 준다. |

**처리 흐름:** 단계가 있으면 `st.expander("조리 과정 N단계 보기")` 안에 `**번호.** 설명`을 표시하고, 단계 이미지가 있으면 `st.columns([3, 2])` 오른쪽에 둔다. 단계가 없으면 오류가 없을 때만 "조리 과정 데이터가 없습니다" 캡션을 표시한다.

## Function get_graph_question_service

```python
@st.cache_resource(show_spinner='그래프 탐색 선택지를 준비하는 중입니다...')
def get_graph_question_service() -> GraphQuestionService:
```

- **호출자:** `show_graph_explorer`
- **반환:** `GraphQuestionService`. 새 드라이버를 만들지 않고 `get_pipeline()`이 연결 검증을 마친 Repository를 주입한다.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (222행)

## Function graph_inputs

```python
def graph_inputs(service: GraphQuestionService, key: str) -> dict:
```

- **호출자:** `show_graph_explorer`(폼 안)
- **반환:** `dict`. Q1 `{term}`(text_input key `graph_term`, 기본 두부), Q2·Q5 `{rcp_id}`(selectbox key `graph_recipe`, 기본 된장 두부찌개), Q3 `{rcp_id, min_common}`(number_input key `graph_min_common`, 기본 3), Q4 `{rcp_cat_nm, limit}`(기본 반찬·20).
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (233행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `service` | `GraphQuestionService` | 선택지를 조회할 Service. |
| `key` | `str` | 'Q1'~'Q5'. |

## Function run_graph_question

```python
def run_graph_question(service: GraphQuestionService, key: str, params: dict) -> GraphAnswer:
```

- **호출자:** `show_graph_explorer`(제출 시)
- **반환:** `GraphAnswer`. 질문 키에 맞는 Service 메서드 하나를 호출한다.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (266행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `service` | `GraphQuestionService` | 그래프 탐색 Service. |
| `key` | `str` | 'Q1'~'Q5'. |
| `params` | `dict` | ``graph_inputs`` 가 돌려준 값. |

## Function graph_table

```python
def graph_table(answer: GraphAnswer) -> list[dict]:
```

- **호출자:** `show_graph_answer`
- **반환:** `list[dict]`. `GRAPH_COLUMNS[질문]` 순서의 한국어 열 이름. 목록은 쉼표로 잇고, 실수는 소수 셋째 자리, Q5 이미지는 `display_image_url`(https) 값.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (287행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `answer` | `GraphAnswer` | 표시할 조회 결과. |

## Function graph_summary

```python
def graph_summary(answer: GraphAnswer) -> str | None:
```

- **호출자:** `show_graph_answer`
- **반환:** `str | None`. 조회 행의 수·첫 행 값으로 만든 결정적 문장. LLM을 부르지 않는다.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (305행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `answer` | `GraphAnswer` | 표시할 조회 결과. |

## Function show_graph_answer

```python
def show_graph_answer(answer: GraphAnswer) -> None:
```

- **호출자:** `show_graph_explorer`
- **반환:** `None`. 질문 문장, `Qn · n-hop`·`Neo4j 조회 결과 (LLM 미사용)`·`N건` 배지, 관계 경로 코드, 안내(`not_found`는 warning, 그 밖은 info), 요약 캡션, `st.dataframe`(Q5는 `ImageColumn`). 실행 Cypher·바인딩 파라미터는 화면에 표시하지 않는다(개발 중에는 `RECIPE_QUERY_LOG=1` 터미널 로그).
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (328행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `answer` | `GraphAnswer` | 표시할 조회 결과. |

## Function show_graph_explorer

```python
def show_graph_explorer() -> None:
```

- **호출자:** 최상위 화면 코드(모드 `graph`)
- **반환:** `None`. 질문 라디오(key `graph_question`) → 폼(`graph_inputs`) → 제출 시 `run_graph_question` 결과를 `st.session_state.graph_answer`에 저장 → `show_graph_answer`. 연결·조회 예외는 `st.error`로 보여 주고 끝낸다(앱은 멈추지 않음). 다른 질문을 고르면 이전 결과를 숨긴다.
- **원본:** [streamlit_app.py](../../../streamlit_app.py) (359행)

## 관련 가이드

- [컴포넌트 관계](../03_component_structure.md)
- [실행 흐름](../04_execution_flow.md)
- [데이터 흐름](../05_data_flow.md)
