# recipe_repository 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.recipe_repository`
- **소스:** [recipe_recommender/recipe_repository.py](../../../../recipe_recommender/recipe_repository.py)
- **역할:** 레시피(recipe 스키마) 등록·조회 공용 Repository 모듈.
- **주요 호출자:** `RecipeSearchService`, `RecipeRegisterService`
- **정의:** 클래스 1개, 모듈 함수 0개

- **직접 의존:** `common.postgres_db_session`

- **관련 API:** [postgres_db_session](../common/postgres_db_session.md), [recipe_search_service](recipe_search_service.md), [recipe_register_service](../setup/recipe_register_service.md)

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [RecipeRepository](#reciperepository) | 클래스 | 레시피 원본·마스터·정제·staging·관계의 등록·조회 SQL을 호출하는 Repository(DAO). |

## RecipeRepository

**클래스.** 레시피 원본·마스터·정제·staging·관계의 등록·조회 SQL을 호출하는 Repository(DAO).

- **정의:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (16행)
- **생성 위치:** `RecipeSearchService.__init__`과 `RecipeRegisterService.__init__`에서 만든다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `sql_session` | `PostgresDbSession` | 레시피 SQL 실행에 사용하는 데이터베이스 세션 |
| `user_id` | `타입 힌트 없음` | 생성자 29행에서 설정; 레시피 원본·마스터·정제·staging·관계의 등록·조회 SQL을 호출하는 Repository(DAO). |

### Constructor Summary

`def __init__(self, sql_session, user_id=SYSTEM_USER_ID):` — SQL 실행에 사용할 세션과 관리 컬럼에 기록할 사용자 ID를 주입받는다.

생성·주입 경로: `RecipeSearchService.__init__`과 `RecipeRegisterService.__init__`에서 만든다.. 세부 매개변수와 처리 내용은 [RecipeRepository.__init__](#reciperepository-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#reciperepository-__init__) | `타입 힌트 없음` | SQL 실행에 사용할 세션과 관리 컬럼에 기록할 사용자 ID를 주입받는다. |
| [_with_user](#reciperepository-_with_user) | `타입 힌트 없음` | 등록·수정 mapper 행마다 시스템 사용자와 공통 매개변수를 합친다. |
| [find_schema_model](#reciperepository-find_schema_model) | `타입 힌트 없음` | 대상 스키마의 모델 표식 ``{"hasRcpCatRel", "hasIngrCat"}``. |
| [find_next_rcp_raw_id](#reciperepository-find_next_rcp_raw_id) | `타입 힌트 없음` | DB 함수 ``recipe.fn_get_biz_id('import_batch')`` 로 새 원본 수집 회차 ID를 발급받는다. |
| [find_latest_raw_batch](#reciperepository-find_latest_raw_batch) | `타입 힌트 없음` | 가장 최근 원본 회차 ``{"rcpRawId", "rawCount", "lastCreateDate"}`` 또는 None. |
| [list_raw_rows_by_batch](#reciperepository-list_raw_rows_by_batch) | `타입 힌트 없음` | 지정 회차 원본 행 목록. key는 camelCase(예: ``rcpRawSeq``, ``manualImg01``). |
| [find_recipe_category](#reciperepository-find_recipe_category) | `타입 힌트 없음` | 요리 종류명으로 ``{"rcpCatId", "rcpCatNm"}`` 를 조회한다. 없으면 None. |
| [insert_recipe_categories](#reciperepository-insert_recipe_categories) | `타입 힌트 없음` | 요리 종류를 등록한다. Returns 새로 등록된 행 수. |
| [upsert_cook_method_codes](#reciperepository-upsert_cook_method_codes) | `타입 힌트 없음` | 조리 방법 그룹과 상세 코드를 확정 코드표 ``{common_cd: common_cd_nm}`` 로 등록한다. |
| [list_cook_method_codes](#reciperepository-list_cook_method_codes) | `타입 힌트 없음` | ``COOK_MTHD`` 그룹의 ``{common_cd: common_cd_nm}``. |
| [list_recipe_key_map](#reciperepository-list_recipe_key_map) | `타입 힌트 없음` | 원본 레시피 번호(rcp_seq) → ``(rcp_id, rcp_raw_id)`` dict. |
| [list_recipe_category_map](#reciperepository-list_recipe_category_map) | `타입 힌트 없음` | 요리 종류명 → 요리 종류 ID dict. |
| [list_recipe_category_relations](#reciperepository-list_recipe_category_relations) | `타입 힌트 없음` | 레시피 ID → 등록된 요리 분류 ID 집합 dict. |
| [list_recipe_step_keys](#reciperepository-list_recipe_step_keys) | `타입 힌트 없음` | 등록된 조리 단계 키 ``(rcp_id, step_no)`` 집합. |
| [list_staging_keys](#reciperepository-list_staging_keys) | `타입 힌트 없음` | 지정 회차에 이미 있는 staging ``(rcp_raw_seq, rcp_ingr_line_no)`` 집합. |
| [insert_recipe_raws](#reciperepository-insert_recipe_raws) | `타입 힌트 없음` | 원본 55개 컬럼 + 행 순번 dict 목록을 batch insert한다. Returns 새로 등록된 행 수. |
| [insert_recipes](#reciperepository-insert_recipes) | `타입 힌트 없음` | 새 정제 레시피를 등록한다(rcp_id는 DB 발급). Returns 등록 행 수. |
| [update_recipes](#reciperepository-update_recipes) | `타입 힌트 없음` | 기존 정제 레시피를 PK로 갱신한다(``RCP_ID`` 포함). Returns 값이 바뀐 행 수. |
| [insert_recipe_category_relations](#reciperepository-insert_recipe_category_relations) | `타입 힌트 없음` | ``[{"RCP_ID", "RCP_CAT_ID"}]`` 레시피·요리 분류 관계를 등록한다. Returns 새로 등록된 행 수. |
| [upsert_recipe_steps](#reciperepository-upsert_recipe_steps) | `타입 힌트 없음` | 조리 단계 목록을 등록·갱신한다. Returns 등록되거나 내용이 바뀐 행 수. |
| [insert_recipe_ingredient_stagings](#reciperepository-insert_recipe_ingredient_stagings) | `타입 힌트 없음` | 재료 파싱 후보 목록을 staging에 등록한다(rcp_ingr_stg_id는 DB 발급). Returns 등록 행 수. |
| [list_ingredient_map](#reciperepository-list_ingredient_map) | `타입 힌트 없음` | 표준 식재료명 → ingr_id dict. |
| [insert_ingredients](#reciperepository-insert_ingredients) | `타입 힌트 없음` | ``[{"INGR_NM"}]`` 를 등록한다. Returns 등록 행 수. |
| [list_ingredient_alias_keys](#reciperepository-list_ingredient_alias_keys) | `타입 힌트 없음` | 등록된 별칭 ``(ingr_id, ingr_als_nm)`` 집합. |
| [insert_ingredient_aliases](#reciperepository-insert_ingredient_aliases) | `타입 힌트 없음` | ``[{"INGR_ID", "INGR_ALS_NM"}]`` 를 등록한다. Returns 등록 행 수. |
| [update_staging_verified_matches](#reciperepository-update_staging_verified_matches) | `타입 힌트 없음` | 표준 식재료명/별칭과 정확히 일치하는 staging 행을 자동 승인한다. Returns 승인 행 수. |
| [insert_recipe_ingredient_relations](#reciperepository-insert_recipe_ingredient_relations) | `타입 힌트 없음` | 승인된 staging 행으로 레시피별 사용 식재료 관계를 만든다. Returns 등록·갱신 행 수. |
| [find_recipe_detail](#reciperepository-find_recipe_detail) | `타입 힌트 없음` | 원본 레시피 번호 또는 내부 레시피 ID로 레시피 한 건을 조회한다. 없으면 None. |
| [list_recipes](#reciperepository-list_recipes) | `타입 힌트 없음` | 레시피명(부분 일치)·요리 종류명·조리 방법 코드로 레시피 목록을 조회한다. |
| [count_recipes](#reciperepository-count_recipes) | `타입 힌트 없음` | ``list_recipes()`` 와 같은 조건의 전체 건수. |
| [list_recipe_steps](#reciperepository-list_recipe_steps) | `타입 힌트 없음` | 레시피 PK로 조리 단계 목록을 조회한다. |
| [list_recipe_ingredients](#reciperepository-list_recipe_ingredients) | `타입 힌트 없음` | 레시피 PK로 사용 표준 식재료 목록을 조회한다. |
| [list_recipe_unmatched_stagings](#reciperepository-list_recipe_unmatched_stagings) | `타입 힌트 없음` | 레시피 재료 원문 중 표준 식재료에 연결되지 않은 staging 행. |
| [find_ingredient_by_name](#reciperepository-find_ingredient_by_name) | `타입 힌트 없음` | 표준 식재료명 또는 별칭과 정확히 일치하는 표준 식재료 목록(보통 0~1건). |
| [list_ingredient_aliases](#reciperepository-list_ingredient_aliases) | `타입 힌트 없음` | 표준 식재료 PK로 별칭 목록을 조회한다. |
| [list_recipes_by_ingredient](#reciperepository-list_recipes_by_ingredient) | `타입 힌트 없음` | 표준 식재료 PK로 그 식재료를 사용하는 레시피 목록을 조회한다. |
| [count_recipes_by_ingredient](#reciperepository-count_recipes_by_ingredient) | `타입 힌트 없음` | 표준 식재료를 사용하는 레시피 수. |
| [count_recipe_tables](#reciperepository-count_recipe_tables) | `타입 힌트 없음` | 목표 모델 11개 테이블 전체 행 수 dict. |
| [count_batch_rows](#reciperepository-count_batch_rows) | `타입 힌트 없음` | 지정 회차 기준 테이블별 행 수 dict. |
| [count_integrity_violations](#reciperepository-count_integrity_violations) | `타입 힌트 없음` | 정합성 검사 항목별 위반 건수 dict. 모든 값이 0이어야 정상이다. |

### RecipeRepository __init__

```python
def __init__(self, sql_session, user_id=SYSTEM_USER_ID):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. SQL 실행에 사용할 세션과 관리 컬럼에 기록할 사용자 ID를 주입받는다.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (26행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `sql_session` | `타입 힌트 없음` | Named SQL 실행 세션 |
| `user_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository _with_user

```python
def _with_user(self, rows, **extra):
```

- **주요 호출자:** `RecipeRepository.insert_ingredient_aliases`, `RecipeRepository.insert_ingredients`, `RecipeRepository.insert_recipe_categories`, `RecipeRepository.insert_recipe_category_relations`, `RecipeRepository.insert_recipe_ingredient_stagings`, `RecipeRepository.insert_recipe_raws`, `RecipeRepository.insert_recipes`, `RecipeRepository.update_recipes`, `RecipeRepository.upsert_cook_method_codes`, `RecipeRepository.upsert_recipe_steps`
- **반환:** `타입 힌트 없음`. 등록·수정 mapper 행마다 시스템 사용자와 공통 매개변수를 합친다.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (31행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rows` | `타입 힌트 없음` | 조회 또는 적재 대상 행 목록 |

### RecipeRepository find_schema_model

```python
def find_schema_model(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 대상 스키마의 모델 표식 ``{"hasRcpCatRel", "hasIngrCat"}``.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (35행)

### RecipeRepository find_next_rcp_raw_id

```python
def find_next_rcp_raw_id(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. DB 함수 ``recipe.fn_get_biz_id('import_batch')`` 로 새 원본 수집 회차 ID를 발급받는다.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (42행)

### RecipeRepository find_latest_raw_batch

```python
def find_latest_raw_batch(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 가장 최근 원본 회차 ``{"rcpRawId", "rawCount", "lastCreateDate"}`` 또는 None.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (46행)

### RecipeRepository list_raw_rows_by_batch

```python
def list_raw_rows_by_batch(self, rcp_raw_id):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 지정 회차 원본 행 목록. key는 camelCase(예: ``rcpRawSeq``, ``manualImg01``).
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (50행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_raw_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository find_recipe_category

```python
def find_recipe_category(self, category_name):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 요리 종류명으로 ``{"rcpCatId", "rcpCatNm"}`` 를 조회한다. 없으면 None.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (57행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `category_name` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository insert_recipe_categories

```python
def insert_recipe_categories(self, category_names):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 요리 종류를 등록한다. Returns 새로 등록된 행 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (61행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `category_names` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository upsert_cook_method_codes

```python
def upsert_cook_method_codes(self, cook_method_codes):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 조리 방법 그룹과 상세 코드를 확정 코드표 ``{common_cd: common_cd_nm}`` 로 등록한다.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (68행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `cook_method_codes` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository list_cook_method_codes

```python
def list_cook_method_codes(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. ``COOK_MTHD`` 그룹의 ``{common_cd: common_cd_nm}``.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (87행)

### RecipeRepository list_recipe_key_map

```python
def list_recipe_key_map(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 원본 레시피 번호(rcp_seq) → ``(rcp_id, rcp_raw_id)`` dict.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (95행)

### RecipeRepository list_recipe_category_map

```python
def list_recipe_category_map(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 요리 종류명 → 요리 종류 ID dict.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (100행)

### RecipeRepository list_recipe_category_relations

```python
def list_recipe_category_relations(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 레시피 ID → 등록된 요리 분류 ID 집합 dict.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (105행)

### RecipeRepository list_recipe_step_keys

```python
def list_recipe_step_keys(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 등록된 조리 단계 키 ``(rcp_id, step_no)`` 집합.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (112행)

### RecipeRepository list_staging_keys

```python
def list_staging_keys(self, rcp_raw_id):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 지정 회차에 이미 있는 staging ``(rcp_raw_seq, rcp_ingr_line_no)`` 집합.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (117행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_raw_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository insert_recipe_raws

```python
def insert_recipe_raws(self, rcp_raw_id, raw_rows):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 원본 55개 컬럼 + 행 순번 dict 목록을 batch insert한다. Returns 새로 등록된 행 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (125행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_raw_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `raw_rows` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository insert_recipes

```python
def insert_recipes(self, rcp_raw_id, recipes):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 새 정제 레시피를 등록한다(rcp_id는 DB 발급). Returns 등록 행 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (130행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_raw_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `recipes` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository update_recipes

```python
def update_recipes(self, rcp_raw_id, recipes):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 기존 정제 레시피를 PK로 갱신한다(``RCP_ID`` 포함). Returns 값이 바뀐 행 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (135행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_raw_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `recipes` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository insert_recipe_category_relations

```python
def insert_recipe_category_relations(self, relations):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. ``[{"RCP_ID", "RCP_CAT_ID"}]`` 레시피·요리 분류 관계를 등록한다. Returns 새로 등록된 행 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (140행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `relations` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository upsert_recipe_steps

```python
def upsert_recipe_steps(self, steps):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 조리 단계 목록을 등록·갱신한다. Returns 등록되거나 내용이 바뀐 행 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (144행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `steps` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository insert_recipe_ingredient_stagings

```python
def insert_recipe_ingredient_stagings(self, rcp_raw_id, stagings):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 재료 파싱 후보 목록을 staging에 등록한다(rcp_ingr_stg_id는 DB 발급). Returns 등록 행 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (148행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_raw_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `stagings` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository list_ingredient_map

```python
def list_ingredient_map(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 표준 식재료명 → ingr_id dict.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (156행)

### RecipeRepository insert_ingredients

```python
def insert_ingredients(self, ingredients):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. ``[{"INGR_NM"}]`` 를 등록한다. Returns 등록 행 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (161행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `ingredients` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository list_ingredient_alias_keys

```python
def list_ingredient_alias_keys(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 등록된 별칭 ``(ingr_id, ingr_als_nm)`` 집합.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (165행)

### RecipeRepository insert_ingredient_aliases

```python
def insert_ingredient_aliases(self, aliases):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. ``[{"INGR_ID", "INGR_ALS_NM"}]`` 를 등록한다. Returns 등록 행 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (170행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `aliases` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository update_staging_verified_matches

```python
def update_staging_verified_matches(self, rcp_raw_id):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 표준 식재료명/별칭과 정확히 일치하는 staging 행을 자동 승인한다. Returns 승인 행 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (174행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_raw_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository insert_recipe_ingredient_relations

```python
def insert_recipe_ingredient_relations(self, rcp_raw_id):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 승인된 staging 행으로 레시피별 사용 식재료 관계를 만든다. Returns 등록·갱신 행 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (179행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_raw_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository find_recipe_detail

```python
def find_recipe_detail(self, rcp_seq=None, rcp_id=None):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 원본 레시피 번호 또는 내부 레시피 ID로 레시피 한 건을 조회한다. 없으면 None.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (187행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_seq` | `타입 힌트 없음` | 식약처 원본 레시피 번호 |
| `rcp_id` | `타입 힌트 없음` | 정제 레시피 ID |

### RecipeRepository list_recipes

```python
def list_recipes(self, rcp_nm=None, rcp_cat_nm=None, cook_mthd_cd=None, limit=20, offset=0):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 레시피명(부분 일치)·요리 종류명·조리 방법 코드로 레시피 목록을 조회한다.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (191행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_nm` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `rcp_cat_nm` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `cook_mthd_cd` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `limit` | `타입 힌트 없음` | 반환하거나 표시할 최대 건수 |
| `offset` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository count_recipes

```python
def count_recipes(self, rcp_nm=None, rcp_cat_nm=None, cook_mthd_cd=None):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. ``list_recipes()`` 와 같은 조건의 전체 건수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (198행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_nm` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `rcp_cat_nm` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `cook_mthd_cd` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository list_recipe_steps

```python
def list_recipe_steps(self, rcp_id):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 레시피 PK로 조리 단계 목록을 조회한다.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (205행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_id` | `타입 힌트 없음` | 정제 레시피 ID |

### RecipeRepository list_recipe_ingredients

```python
def list_recipe_ingredients(self, rcp_id):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 레시피 PK로 사용 표준 식재료 목록을 조회한다.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (209행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_id` | `타입 힌트 없음` | 정제 레시피 ID |

### RecipeRepository list_recipe_unmatched_stagings

```python
def list_recipe_unmatched_stagings(self, rcp_id):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 레시피 재료 원문 중 표준 식재료에 연결되지 않은 staging 행.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (213행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_id` | `타입 힌트 없음` | 정제 레시피 ID |

### RecipeRepository find_ingredient_by_name

```python
def find_ingredient_by_name(self, ingr_nm):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 표준 식재료명 또는 별칭과 정확히 일치하는 표준 식재료 목록(보통 0~1건).
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (217행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `ingr_nm` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository list_ingredient_aliases

```python
def list_ingredient_aliases(self, ingr_id):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 표준 식재료 PK로 별칭 목록을 조회한다.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (221행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `ingr_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository list_recipes_by_ingredient

```python
def list_recipes_by_ingredient(self, ingr_id, limit=20, offset=0):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 표준 식재료 PK로 그 식재료를 사용하는 레시피 목록을 조회한다.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (225행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `ingr_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `limit` | `타입 힌트 없음` | 반환하거나 표시할 최대 건수 |
| `offset` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository count_recipes_by_ingredient

```python
def count_recipes_by_ingredient(self, ingr_id):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 표준 식재료를 사용하는 레시피 수.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (231행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `ingr_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository count_recipe_tables

```python
def count_recipe_tables(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 목표 모델 11개 테이블 전체 행 수 dict.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (239행)

### RecipeRepository count_batch_rows

```python
def count_batch_rows(self, rcp_raw_id):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 지정 회차 기준 테이블별 행 수 dict.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (243행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rcp_raw_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRepository count_integrity_violations

```python
def count_integrity_violations(self):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 정합성 검사 항목별 위반 건수 dict. 모든 값이 0이어야 정상이다.
- **원본:** [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) (247행)

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
