# recipe_search_service 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.recipe_search_service`
- **소스:** [recipe_recommender/recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py)
- **역할:** 레시피 조회 Service 모듈 (PostgreSQL 기반 MVP).
- **주요 호출자:** `search_recipe.main`
- **정의:** 클래스 2개, 모듈 함수 0개

- **직접 의존:** `common.postgres_db_session`, `.recipe_repository`

- **관련 API:** [recipe_repository](recipe_repository.md), [search_recipe](search_recipe.md)

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [RecipeSearchError](#recipesearcherror) | 예외 클래스 | 조회 조건이 잘못된 경우의 오류. |
| [RecipeSearchService](#recipesearchservice) | 클래스 | 레시피·조리 단계·사용 식재료·표준 식재료를 조회하는 Service. |

## RecipeSearchError

**예외 클래스.** 조회 조건이 잘못된 경우의 오류.

- **정의:** [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) (19행)
- **생성 위치:** 직접 생성 호출은 주요 진입 경로에서 확인되지 않음; 정의와 호출 코드를 참조한다.

### Constructor Summary

명시적 `__init__`가 없다. 상위 클래스 또는 Python 기본 생성자를 사용한다.

## RecipeSearchService

**클래스.** 레시피·조리 단계·사용 식재료·표준 식재료를 조회하는 Service.

- **정의:** [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) (23행)
- **생성 위치:** `search_recipe.main`에서 SQL 세션을 전달해 만든다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `sql_session` | `PostgresDbSession` | Named SQL 실행에 사용하는 공통 세션. |
| `repository` | `RecipeRepository` | 조회 SQL을 묶은 DAO; 생성자에서 만든다. |

### Constructor Summary

`def __init__(self, sql_session):` — 조회 SQL 세션을 받아 Repository를 생성한다.

생성·주입 경로: `search_recipe.main`에서 SQL 세션을 전달해 만든다.. 세부 매개변수와 처리 내용은 [RecipeSearchService.__init__](#recipesearchservice-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#recipesearchservice-__init__) | `타입 힌트 없음` | 조회 SQL 세션을 받아 Repository를 생성한다. |
| [_text](#recipesearchservice-_text) | `str \| None` | 앞뒤 공백을 제거하고, 비어 있으면 '조건 없음'(None)으로 본다. |
| [_paging](#recipesearchservice-_paging) | `tuple[int, int]` | 페이지 번호(1부터)와 크기를 검증해 ``(limit, offset)`` 으로 바꾼다. |
| [get_recipe_detail](#recipesearchservice-get_recipe_detail) | `dict \| None` | 원본 레시피 번호 또는 내부 레시피 ID로 레시피 상세를 조회한다. |
| [search_recipes](#recipesearchservice-search_recipes) | `dict` | 레시피명(부분 일치)·요리 종류명·조리 방법으로 레시피를 검색한다. |
| [list_recipe_steps](#recipesearchservice-list_recipe_steps) | `list[dict]` | 원본 레시피 번호로 조리 단계 목록을 조회한다. 레시피가 없으면 빈 목록. |
| [list_recipe_ingredients](#recipesearchservice-list_recipe_ingredients) | `list[dict]` | 원본 레시피 번호로 사용 표준 식재료 목록을 조회한다. 레시피가 없으면 빈 목록. |
| [find_ingredient](#recipesearchservice-find_ingredient) | `dict \| None` | 표준 식재료명 또는 별칭으로 표준 식재료와 별칭 목록을 조회한다. |
| [search_recipes_by_ingredient](#recipesearchservice-search_recipes_by_ingredient) | `dict \| None` | 표준 식재료명 또는 별칭으로 그 식재료를 사용하는 레시피를 조회한다. |

### RecipeSearchService __init__

```python
def __init__(self, sql_session):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 조회 SQL 세션을 받아 Repository를 생성한다.
- **원본:** [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) (33행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `sql_session` | `타입 힌트 없음` | Named SQL을 실행할 공통 세션. |

### RecipeSearchService _text

```python
@staticmethod
def _text(value: str | None) -> str | None:
```

- **주요 호출자:** `RecipeSearchService.find_ingredient`, `RecipeSearchService.get_recipe_detail`, `RecipeSearchService.list_recipe_ingredients`, `RecipeSearchService.list_recipe_steps`, `RecipeSearchService.search_recipes`
- **반환:** `str | None`. 앞뒤 공백을 제거하고, 비어 있으면 '조건 없음'(None)으로 본다.
- **원본:** [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) (46행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `str \| None` | 처리하거나 설정할 값 |

### RecipeSearchService _paging

```python
@staticmethod
def _paging(page: int, page_size: int) -> tuple[int, int]:
```

- **주요 호출자:** `RecipeSearchService.search_recipes_by_ingredient`, `RecipeSearchService.search_recipes`
- **반환:** `tuple[int, int]`. 페이지 번호(1부터)와 크기를 검증해 ``(limit, offset)`` 으로 바꾼다.
- **원본:** [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) (54행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `page` | `int` | 1부터 시작하는 페이지 번호 |
| `page_size` | `int` | 페이지당 조회 건수 |

### RecipeSearchService get_recipe_detail

```python
def get_recipe_detail(self, rcp_seq: str | None=None, rcp_id: str | None=None) -> dict | None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict | None`. 원본 레시피 번호 또는 내부 레시피 ID로 레시피 상세를 조회한다.
- **원본:** [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) (65행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_seq` | `str \| None` | 식약처 원본 레시피 번호 |
| `rcp_id` | `str \| None` | 정제 레시피 ID |

**처리 흐름:** 원본 번호 또는 내부 ID를 검증해 레시피를 찾고 단계, 재료, 미매칭 staging을 묶는다.

**관련 API:** [recipe_repository](recipe_repository.md), [search_recipe](search_recipe.md)

### RecipeSearchService search_recipes

```python
def search_recipes(self, name: str | None=None, category: str | None=None, cook_method: str | None=None, page: int=1, page_size: int=DEFAULT_PAGE_SIZE) -> dict:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict`. 레시피명(부분 일치)·요리 종류명·조리 방법으로 레시피를 검색한다.
- **원본:** [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) (88행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `name` | `str \| None` | 조회할 이름 또는 식별자 |
| `category` | `str \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `cook_method` | `str \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `page` | `int` | 1부터 시작하는 페이지 번호 |
| `page_size` | `int` | 페이지당 조회 건수 |

**처리 흐름:** 텍스트·분류·페이징 조건을 검증하고 Repository 목록/건수 조회를 조합한다.

**관련 API:** [recipe_repository](recipe_repository.md), [search_recipe](search_recipe.md)

### RecipeSearchService list_recipe_steps

```python
def list_recipe_steps(self, rcp_seq: str) -> list[dict]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `list[dict]`. 원본 레시피 번호로 조리 단계 목록을 조회한다. 레시피가 없으면 빈 목록.
- **원본:** [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) (108행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_seq` | `str` | 식약처 원본 레시피 번호 |

### RecipeSearchService list_recipe_ingredients

```python
def list_recipe_ingredients(self, rcp_seq: str) -> list[dict]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `list[dict]`. 원본 레시피 번호로 사용 표준 식재료 목록을 조회한다. 레시피가 없으면 빈 목록.
- **원본:** [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) (113행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_seq` | `str` | 식약처 원본 레시피 번호 |

### RecipeSearchService find_ingredient

```python
def find_ingredient(self, name: str) -> dict | None:
```

- **주요 호출자:** `RecipeSearchService.search_recipes_by_ingredient`
- **반환:** `dict | None`. 표준 식재료명 또는 별칭으로 표준 식재료와 별칭 목록을 조회한다.
- **원본:** [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) (121행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `name` | `str` | 조회할 이름 또는 식별자 |

**예외:** RecipeSearchError: 이름이 비었거나, 별칭이 둘 이상의 표준 식재료를 가리키는 경우.

### RecipeSearchService search_recipes_by_ingredient

```python
def search_recipes_by_ingredient(self, name: str, page: int=1, page_size: int=DEFAULT_PAGE_SIZE) -> dict | None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict | None`. 표준 식재료명 또는 별칭으로 그 식재료를 사용하는 레시피를 조회한다.
- **원본:** [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) (144행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `name` | `str` | 조회할 이름 또는 식별자 |
| `page` | `int` | 1부터 시작하는 페이지 번호 |
| `page_size` | `int` | 페이지당 조회 건수 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
