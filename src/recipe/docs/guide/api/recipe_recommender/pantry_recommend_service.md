# pantry_recommend_service 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.pantry_recommend_service`
- **소스:** [recipe_recommender/pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py)
- **역할:** 냉장고 재료 기반 레시피 추천 Service (Neo4j 읽기 전용, LLM 없음).
- **주요 호출자:** `PantryGraphRAG.retrieve`와 `interpret`의 DB 어휘 대체 경로
- **정의:** 클래스 5개, 모듈 함수 2개

- **직접 의존:** `.name_normalization`

- **관련 API:** [pantry_graphrag](pantry_graphrag.md), [recipe_graph_repository](recipe_graph_repository.md)

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [RecipeStep](#recipestep) | dataclass DTO | 식약처 원본 조리 과정 한 단계(MANUAL01~20)의 Neo4j 조회값. |
| [TermResolution](#termresolution) | dataclass DTO | 입력어 하나의 해석 결과. ``matches`` 가 비면 DB에 없는 재료, 2개 이상이면 모호한 별칭. |
| [Recommendation](#recommendation) | dataclass DTO | 추천 한 건의 Neo4j 조회 근거; ``recommend``가 만들고 화면과 LLM 검증이 읽는다. |
| [PantryResult](#pantryresult) | dataclass DTO | 입력 해석과 추천 목록을 묶어 LangGraph의 ``result``에 담는 DTO. |
| [PantryRecommendService](#pantryrecommendservice) | 클래스 | 보유 식재료 → 추천 레시피·사용/부족 재료·근거를 Neo4j에서 조회한다. |

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [display_image_url](#function-display_image_url) | `str \| None` | 식약처 이미지 URL을 화면에 표시할 수 있는 형태로 바꾼다. 표시할 수 없으면 ``None``. |
| [split_terms](#function-split_terms) | `list[str]` | ``'계란, 두부, 양파'`` → ``['계란', '두부', '양파']``. 중복(정규화 기준)은 처음 것만 남긴다. |

## RecipeStep

**dataclass DTO.** 식약처 원본 조리 과정 한 단계(MANUAL01~20)의 Neo4j 조회값.

- **정의:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (91행)
- **생성 위치:** `PantryRecommendService._attach_steps`가 `recipe_steps` 조회 행마다 만든다.

`@dataclass`는 필드 기반 생성자 등을 만드는 Python 장식자다. Java Record와 비슷한 DTO 용도지만 `frozen=True`여도 내부 리스트까지 불변으로 만들지는 않는다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `step_no` | `int` | 원본 MANUAL 번호; 중간 번호가 비어 있을 수 있어 화면에도 이 번호를 그대로 쓴다. |
| `instruction_txt` | `str` | 원본 조리 설명(LLM이 만들거나 고치지 않는다). |
| `image_url` | `str \| None` | 원본 단계 이미지 URL; 없으면 None. |

### Constructor Summary

명시적 생성자는 없다. `@dataclass`가 선언된 필드 순서로 생성자를 만든다.

## TermResolution

**dataclass DTO.** 입력어 하나의 해석 결과. ``matches`` 가 비면 DB에 없는 재료, 2개 이상이면 모호한 별칭.

- **정의:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (100행)
- **생성 위치:** `PantryRecommendService.resolve_terms`가 입력어마다 만든다.

`@dataclass`는 필드 기반 생성자 등을 만드는 Python 장식자다. Java Record와 비슷한 DTO 용도지만 `frozen=True`여도 내부 리스트까지 불변으로 만들지는 않는다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `term` | `str` | 사용자 원문의 재료명; 화면에서 매칭 전 입력을 보여 준다. |
| `matches` | `list[dict]` | [{ingr_id, ingr_nm, matched_by: 'name'\|'alias'}] |

### Constructor Summary

명시적 생성자는 없다. `@dataclass`가 선언된 필드 순서로 생성자를 만든다.

## Recommendation

**dataclass DTO.** 추천 한 건의 Neo4j 조회 근거; ``recommend``가 만들고 화면과 LLM 검증이 읽는다.

- **정의:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (108행)
- **생성 위치:** `PantryRecommendService.recommend`가 조회 행마다 만든다.

`@dataclass`는 필드 기반 생성자 등을 만드는 Python 장식자다. Java Record와 비슷한 DTO 용도지만 `frozen=True`여도 내부 리스트까지 불변으로 만들지는 않는다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_id` | `str` | 그래프의 레시피 ID; LLM 설명과 조회 결과를 연결한다. |
| `rcp_nm` | `str` | 화면에 표시할 레시피명. |
| `rcp_seq` | `str \| None` | 식약처 원본 번호; 근거 조회에 없으면 None. |
| `categories` | `list[str]` | 그래프에서 조회한 분류명 목록. |
| `method` | `str \| None` | 조리 방법; 등록되지 않았으면 None. |
| `energy_kcal` | `float \| None` | 열량; 등록되지 않았으면 None. |
| `matched_ingredients` | `list[str]` | 사용자 보유 재료 중 레시피가 사용하는 표준명. |
| `missing_ingredients` | `list[str]` | 레시피에 필요하지만 보유하지 않은 재료명. |
| `matched_count` | `int` | 보유 재료 사용 개수; 화면에 표시한다. |
| `missing_count` | `int` | 추가 필요 재료 개수; 화면에 표시한다. |
| `all_ingredients` | `list[str]` | LLM 설명 검증에 쓰는 전체 재료 근거. |
| `image_url` | `str \| None` | 식약처 대표 이미지 원본 URL(rcp.rcp_image_url); 화면 표시용. 기본값 None. |
| `steps` | `list[RecipeStep]` | 원본 번호 순 조리 과정; 그래프에 없으면 빈 목록(기본값). |

### Constructor Summary

명시적 생성자는 없다. `@dataclass`가 선언된 필드 순서로 생성자를 만든다.

## PantryResult

**dataclass DTO.** 입력 해석과 추천 목록을 묶어 LangGraph의 ``result``에 담는 DTO.

- **정의:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (127행)
- **생성 위치:** `PantryRecommendService.recommend`가 만들고 LangGraph State에 담는다.

`@dataclass`는 필드 기반 생성자 등을 만드는 Python 장식자다. Java Record와 비슷한 DTO 용도지만 `frozen=True`여도 내부 리스트까지 불변으로 만들지는 않는다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `terms` | `list[str]` | 추천에 사용한 정제 입력어; 입력 순서를 유지한다. |
| `resolutions` | `list[TermResolution]` | 입력어별 DB 표준명·별칭 조회 결과. |
| `recommendations` | `list[Recommendation]` | 정렬된 추천 목록; 조회 불가 시 빈 목록. |
| `step_error` | `str \| None` | 조리 과정 조회 실패 시 예외 이름; 추천 목록은 그대로 유지된다. 기본값 None. |
| `resolved_terms` | `list[str]` | `@property`로 계산되는 읽기 속성; [resolved_terms 상세](#pantryresult-resolved_terms-getter) 참조 |
| `unknown_terms` | `list[str]` | `@property`로 계산되는 읽기 속성; [unknown_terms 상세](#pantryresult-unknown_terms-getter) 참조 |
| `owned_ingredients` | `list[str]` | `@property`로 계산되는 읽기 속성; [owned_ingredients 상세](#pantryresult-owned_ingredients-getter) 참조 |

### Constructor Summary

명시적 생성자는 없다. `@dataclass`가 선언된 필드 순서로 생성자를 만든다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [resolved_terms (getter)](#pantryresult-resolved_terms-getter) | `list[str]` | ``@property``로 호출 괄호 없이 읽는, DB에 일치한 원문 입력어 목록. |
| [unknown_terms (getter)](#pantryresult-unknown_terms-getter) | `list[str]` | DB에 일치 항목이 없어 추천 조회에서 제외된 입력어 목록. |
| [owned_ingredients (getter)](#pantryresult-owned_ingredients-getter) | `list[str]` | 해석된 표준 식재료명(중복 제거, 입력 순서). |
| [to_dict](#pantryresult-to_dict) | `dict` | Streamlit Session State 표시용으로 중첩 dataclass를 dict로 변환한다. |

### PantryResult resolved_terms getter

```python
@property
def resolved_terms(self) -> list[str]:
```

- **주요 호출자:** 현재 업무 소스에서는 직접 읽지 않는다. 입력어 매칭 상태를 외부에 제공하는 계산 속성이다.
- **반환:** `list[str]`. ``@property``로 호출 괄호 없이 읽는, DB에 일치한 원문 입력어 목록.
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (136행)

### PantryResult unknown_terms getter

```python
@property
def unknown_terms(self) -> list[str]:
```

- **주요 호출자:** `streamlit_app.run_pipeline`, `PantryGraphRAG.answer`
- **반환:** `list[str]`. DB에 일치 항목이 없어 추천 조회에서 제외된 입력어 목록.
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (141행)

### PantryResult owned_ingredients getter

```python
@property
def owned_ingredients(self) -> list[str]:
```

- **주요 호출자:** `streamlit_app.run_pipeline`, `grounded_summary`, `validate_answer`, `PantryGraphRAG.answer`
- **반환:** `list[str]`. 해석된 표준 식재료명(중복 제거, 입력 순서).
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (146행)

### PantryResult to_dict

```python
def to_dict(self) -> dict:
```

- **주요 호출자:** `streamlit_app.run_pipeline`이 Session State에 넣을 결과를 직렬화할 때 호출한다.
- **반환:** `dict`. Streamlit Session State 표시용으로 중첩 dataclass를 dict로 변환한다.
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (155행)

## PantryRecommendService

**클래스.** 보유 식재료 → 추천 레시피·사용/부족 재료·근거를 Neo4j에서 조회한다.

- **정의:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (161행)
- **생성 위치:** `streamlit_app.get_pipeline`에서 `RecipeGraphRepository`를 주입해 만든다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `graph` | `타입 힌트 없음` | 생성자 166행에서 설정; 보유 식재료 → 추천 레시피·사용/부족 재료·근거를 Neo4j에서 조회한다. |
| `_vocabulary` | `list[dict] \| None` | 생성자 167행에서 설정; 보유 식재료 → 추천 레시피·사용/부족 재료·근거를 Neo4j에서 조회한다. |

### Constructor Summary

`def __init__(self, graph):` — ``graph`` 는 ``RecipeGraphRepository`` (또는 같은 ``query_example`` 을 가진 객체).

생성·주입 경로: `streamlit_app.get_pipeline`에서 `RecipeGraphRepository`를 주입해 만든다.. 세부 매개변수와 처리 내용은 [PantryRecommendService.__init__](#pantryrecommendservice-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#pantryrecommendservice-__init__) | `타입 힌트 없음` | ``graph`` 는 ``RecipeGraphRepository`` (또는 같은 ``query_example`` 을 가진 객체). |
| [_query](#pantryrecommendservice-_query) | `list[dict]` | 허용된 Named Cypher만 namespace에 맞는 조회 API로 실행한다. |
| [resolve_terms](#pantryrecommendservice-resolve_terms) | `list[TermResolution]` | 입력어마다 표준명 또는 별칭으로 표준 식재료를 찾는다(ETL과 같은 정규화, 정확 일치만). |
| [recommend](#pantryrecommendservice-recommend) | `PantryResult` | 입력어를 표준 재료에 매칭하고 추천 및 레시피별 근거를 조회한다. |
| [_attach_steps](#pantryrecommendservice-_attach_steps) | `None` | 추천이 확정된 레시피에 조리 과정을 한 번의 조회로 붙인다(추천 순서·건수는 바꾸지 않는다). |
| [vocabulary](#pantryrecommendservice-vocabulary) | `list[dict]` | ``[{ingr_id, ingr_nm, alias_names}]`` 전체 식재료 어휘(한 번만 조회). |

### PantryRecommendService __init__

```python
def __init__(self, graph):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. ``graph`` 는 ``RecipeGraphRepository`` (또는 같은 ``query_example`` 을 가진 객체).
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (164행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `graph` | `타입 힌트 없음` | Neo4j 조회·쓰기 Repository |

### PantryRecommendService _query

```python
def _query(self, statement: str, parameters: dict) -> list[dict]:
```

- **주요 호출자:** `PantryRecommendService.recommend`, `PantryRecommendService.resolve_terms`, `PantryRecommendService._attach_steps`, `PantryRecommendService.vocabulary`
- **반환:** `list[dict]`. 허용된 Named Cypher만 namespace에 맞는 조회 API로 실행한다.
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (169행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement` | `str` | ``namespace.name`` 형식의 쿼리 식별자. |
| `parameters` | `dict` | Cypher 바인딩 값. |

**예외:** ValueError: 읽기 허용 목록에 없는 식별자일 때.

### PantryRecommendService resolve_terms

```python
def resolve_terms(self, terms: list[str]) -> list[TermResolution]:
```

- **주요 호출자:** `PantryRecommendService.recommend`
- **반환:** `list[TermResolution]`. 입력어마다 표준명 또는 별칭으로 표준 식재료를 찾는다(ETL과 같은 정규화, 정확 일치만).
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (189행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `terms` | `list[str]` | 입력에서 추출한 재료명 목록 |

### PantryRecommendService recommend

```python
def recommend(self, terms: list[str], limit: int=5, sort: str='coverage') -> PantryResult:
```

- **주요 호출자:** `PantryGraphRAG.retrieve`
- **반환:** `PantryResult`. 입력어를 표준 재료에 매칭하고 추천 및 레시피별 근거를 조회한다.
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (201행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `terms` | `list[str]` | ``interpret``가 추출한 원문 재료명. |
| `limit` | `int` | 반환할 추천 개수. |
| `sort` | `str` | ``coverage`` 또는 ``missing``. |

**처리 흐름:** 입력어를 표준 재료에 매칭하고, 정렬 방식에 따른 Named Cypher로 추천을 읽은 뒤 레시피별 근거(대표 이미지 URL 포함)를 추가하고, 마지막에 `_attach_steps`로 조리 과정을 붙인다.

**관련 API:** [pantry_graphrag](pantry_graphrag.md), [recipe_graph_repository](recipe_graph_repository.md)

**예외:** ValueError: 지원하지 않는 정렬 방식일 때.

### PantryRecommendService _attach_steps

```python
def _attach_steps(self, result: PantryResult) -> None:
```

- **주요 호출자:** `PantryRecommendService.recommend`
- **반환:** `None`. 추천이 확정된 레시피에 조리 과정을 한 번의 조회로 붙인다(추천 순서·건수는 바꾸지 않는다).
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (244행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `result` | `PantryResult` | ``recommend`` 가 만든 추천 결과(제자리에서 갱신). |

**처리 흐름:** `recipe_graph_queries.recipe_steps`에 추천 레시피 ID 목록을 넘겨 한 번 조회하고, 레시피별 `RecipeStep`을 `step_no` 순으로 정렬해 `Recommendation.steps`에 넣는다.

**예외:** 조회 예외는 밖으로 던지지 않는다. `result.step_error`에 예외 이름을 남기고 모든 `steps`를 빈 목록으로 둔다.

### PantryRecommendService vocabulary

```python
def vocabulary(self) -> list[dict]:
```

- **주요 호출자:** `PantryGraphRAG._interpret_without_llm`, `PantryGraphRAG.answer`
- **반환:** `list[dict]`. ``[{ingr_id, ingr_nm, alias_names}]`` 전체 식재료 어휘(한 번만 조회).
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (270행)

## Function display_image_url

```python
def display_image_url(url: str | None) -> str | None:
```

- **호출자:** `streamlit_app.show_image`, `streamlit_app.show_steps`
- **반환:** `str | None`. 식약처 이미지 URL을 화면에 표시할 수 있는 형태로 바꾼다. 표시할 수 없으면 ``None``.
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (62행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `url` | `str \| None` | Neo4j에 적재된 원본 URL. |

**처리 흐름:** 비었거나 http/https가 아니면(상대 경로·`javascript:` 등) `None`. `HTTPS_UPGRADE_HOSTS`(식약처 이미지 서버, http 요청을 https로 302 리다이렉트)의 `http://`는 같은 경로의 `https://`로 바꾼다. 그 밖의 URL은 그대로 둔다. DB 값은 바꾸지 않는다.

## Function split_terms

```python
def split_terms(text: str) -> list[str]:
```

- **호출자:** `PantryGraphRAG.retrieve`와 `interpret`의 DB 어휘 대체 경로
- **반환:** `list[str]`. ``'계란, 두부, 양파'`` → ``['계란', '두부', '양파']``. 중복(정규화 기준)은 처음 것만 남긴다.
- **원본:** [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) (51행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `text` | `str` | 처리할 입력 문자열 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
