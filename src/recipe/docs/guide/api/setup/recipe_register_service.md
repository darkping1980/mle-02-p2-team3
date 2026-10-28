# recipe_register_service 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.setup.recipe_register_service`
- **소스:** [recipe_recommender/setup/recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py)
- **역할:** 식약처 ``COOKRCP01.csv`` 를 recipe 스키마에 적재하는 Service 모듈.
- **주요 호출자:** `setup.register_recipe_csv.main`
- **정의:** 클래스 6개, 모듈 함수 9개

- **직접 의존:** `common.database_manager`, `common.postgres_db_session`, `.recipe_ingredient_parser`, `..recipe_repository`

- **관련 API:** [recipe_repository](../recipe_recommender/recipe_repository.md), [recipe_ingredient_parser](recipe_ingredient_parser.md)

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [RecipeLoadError](#recipeloaderror) | 예외 클래스 | 적재를 중단해야 하는 데이터·구조 오류. 메시지에 원인 목록을 담는다. |
| [RehearsalRollback](#rehearsalrollback) | 예외 클래스 | 리허설 적재 마지막에 던져 전체 트랜잭션을 ROLLBACK시키는 표식 예외. |
| [IngredientSeed](#ingredientseed) | dataclass DTO | 검토된 식재료 사전. ingredients: [(표준명, (별칭...))]. |
| [RecipeLoadPlan](#recipeloadplan) | dataclass DTO | CSV에서 만든 DB 등록 후보와 검증 결과. DB에는 아직 아무것도 쓰지 않은 상태다. |
| [RecipeLoadResult](#recipeloadresult) | dataclass DTO | 적재 실행 결과. dry-run이면 DB 관련 값은 비어 있다. |
| [RecipeRegisterService](#reciperegisterservice) | 클래스 | 레시피 CSV 적재 파이프라인을 실행하는 Service. |

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [normalize_newlines](#function-normalize_newlines) | `str \| None` | CRLF·CR을 LF로 바꾼다. 원본 저장값은 바꾸지 않고 비교·정제 값에만 쓴다. |
| [_null_if_empty](#function-_null_if_empty) | `str \| None` | CSV에는 NULL 개념이 없으므로 빈 문자열만 NULL로 저장한다. 그 외 값은 공백 포함 원형 그대로. |
| [_clean_text](#function-_clean_text) | `str \| None` | 정제 컬럼용: 줄바꿈을 LF로 맞추고 앞뒤 공백만 제거하며 비면 NULL. |
| [raw_seq_for](#function-raw_seq_for) | `str` | CSV 행 위치(1부터)를 회차 내 원본 행 순번 문자열로 만든다. 999,999 초과는 오류. |
| [strip_step_prefix](#function-strip_step_prefix) | `str` | 조리 설명 앞의 '1. ' 같은 번호가 단계 번호와 같을 때만 제거한다. 나머지 원문은 유지한다. |
| [evaluate_nutrition](#function-evaluate_nutrition) | `tuple[dict[str, Decimal \| None], str, str \| None]` | 영양정보를 Decimal로 변환하고 자동 검증 상태를 정한다. |
| [load_ingredient_seed](#function-load_ingredient_seed) | `IngredientSeed` | 식재료 표준명·별칭 사전을 읽고 모순을 검사한다. |
| [load_cook_method_seed](#function-load_cook_method_seed) | `dict[str, str]` | 조리 방법 확정 코드표를 읽는다. Returns ``{common_cd: common_cd_nm}`` (파일 순서). |
| [resolve_cook_method_map](#function-resolve_cook_method_map) | `dict[str, str]` | DB의 COOK_MTHD 코드와 확정 코드표를 합쳐 ``{common_cd_nm: common_cd}`` 를 만든다. |

## RecipeLoadError

**예외 클래스.** 적재를 중단해야 하는 데이터·구조 오류. 메시지에 원인 목록을 담는다.

- **정의:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (87행)
- **생성 위치:** 직접 생성 호출은 주요 진입 경로에서 확인되지 않음; 정의와 호출 코드를 참조한다.

### Constructor Summary

명시적 `__init__`가 없다. 상위 클래스 또는 Python 기본 생성자를 사용한다.

## RehearsalRollback

**예외 클래스.** 리허설 적재 마지막에 던져 전체 트랜잭션을 ROLLBACK시키는 표식 예외.

- **정의:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (91행)
- **생성 위치:** 직접 생성 호출은 주요 진입 경로에서 확인되지 않음; 정의와 호출 코드를 참조한다.

### Constructor Summary

명시적 `__init__`가 없다. 상위 클래스 또는 Python 기본 생성자를 사용한다.

## IngredientSeed

**dataclass DTO.** 검토된 식재료 사전. ingredients: [(표준명, (별칭...))].

- **정의:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (96행)
- **생성 위치:** 직접 생성 호출은 주요 진입 경로에서 확인되지 않음; 정의와 호출 코드를 참조한다.

`@dataclass`는 필드 기반 생성자 등을 만드는 Python 장식자다. Java Record와 비슷한 DTO 용도지만 `frozen=True`여도 내부 리스트까지 불변으로 만들지는 않는다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `ingredients` | `tuple[tuple[str, tuple[str, ...]], ...]` | 검토된 표준명과 별칭 묶음; 등록 전 사전 검증에 쓴다. |
| `alias_count` | `int` | `@property`로 계산되는 읽기 속성; [alias_count 상세](#ingredientseed-alias_count-getter) 참조 |

### Constructor Summary

명시적 생성자는 없다. `@dataclass`가 선언된 필드 순서로 생성자를 만든다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [alias_count (getter)](#ingredientseed-alias_count-getter) | `int` | 검토된 식재료 사전에 포함된 별칭 총수를 계산한다. |

### IngredientSeed alias_count getter

```python
@property
def alias_count(self) -> int:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `int`. 검토된 식재료 사전에 포함된 별칭 총수를 계산한다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (102행)

## RecipeLoadPlan

**dataclass DTO.** CSV에서 만든 DB 등록 후보와 검증 결과. DB에는 아직 아무것도 쓰지 않은 상태다.

- **정의:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (108행)
- **생성 위치:** `RecipeRegisterService`가 CSV 검증·등록 후보를 모아 만든다.

`@dataclass`는 필드 기반 생성자 등을 만드는 Python 장식자다. Java Record와 비슷한 DTO 용도지만 `frozen=True`여도 내부 리스트까지 불변으로 만들지는 않는다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `source_row_count` | `int` | 읽은 CSV 데이터 행 수. |
| `raw_rows` | `list[dict]` | 원본 테이블 등록 후보. |
| `recipes` | `list[dict]` | 정제 레시피 등록 후보. |
| `steps` | `list[dict]` | 조리 단계 등록 후보. |
| `stagings` | `list[dict]` | 재료 원문 파싱 staging 후보. |
| `category_relations` | `list[dict]` | 레시피·분류 관계 후보. |
| `blocking_errors` | `list[str]` | 쓰기를 중단해야 할 검증 오류. |
| `category_conflicts` | `list[str]` | 분류 매핑 충돌 보고. |
| `nutrition_reviews` | `list[str]` | 영양값 검토 필요 사유. |
| `step_issues` | `list[str]` | 단계 원문 누락·불일치 문제. |
| `recipes_without_parts` | `list[str]` | 재료 원문이 없는 레시피. |
| `parse_status_counts` | `dict[str, int]` | 파싱 상태별 후보 건수. |

### Constructor Summary

명시적 생성자는 없다. `@dataclass`가 선언된 필드 순서로 생성자를 만든다.

## RecipeLoadResult

**dataclass DTO.** 적재 실행 결과. dry-run이면 DB 관련 값은 비어 있다.

- **정의:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (126행)
- **생성 위치:** `RecipeRegisterService.register`가 적재 결과를 담아 반환한다.

`@dataclass`는 필드 기반 생성자 등을 만드는 Python 장식자다. Java Record와 비슷한 DTO 용도지만 `frozen=True`여도 내부 리스트까지 불변으로 만들지는 않는다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `plan` | `RecipeLoadPlan` | 실행에 사용한 사전 검증·등록 후보. |
| `dry_run` | `bool` | True면 DB에 쓰지 않고 후보와 검증 결과만 반환한다. |
| `rcp_raw_id` | `str \| None` | 사용한 수집 회차 ID; dry-run이면 None. |
| `batch_mode` | `str \| None` | NEW_BATCH / SAME_BATCH_RERUN |
| `written` | `dict[str, int]` | 테이블별 실제 등록 건수. |
| `ingredient_conflicts` | `list[str]` | 표준 재료 충돌 목록. |
| `batch_counts` | `dict \| None` | 현재 수집 회차의 테이블별 건수; 미실행 시 None. |
| `table_counts_before` | `dict \| None` | 쓰기 전 전체 테이블 건수. |
| `table_counts_after` | `dict \| None` | 쓰기 후 전체 테이블 건수. |
| `integrity` | `dict \| None` | 참조 정합성 검사 결과; 미실행 시 None. |
| `stale_steps` | `list[str]` | 재실행 때 원본과 어긋난 기존 단계. |
| `rolled_back` | `bool` | --rehearse: 쓰기·검증 후 ROLLBACK됨 |

### Constructor Summary

명시적 생성자는 없다. `@dataclass`가 선언된 필드 순서로 생성자를 만든다.

## RecipeRegisterService

**클래스.** 레시피 CSV 적재 파이프라인을 실행하는 Service.

- **정의:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (293행)
- **생성 위치:** `setup.register_recipe_csv.main`에서 SQL 세션을 전달해 만든다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `sql_session` | `PostgresDbSession` | 등록 트랜잭션과 Named SQL 실행 세션. |
| `repository` | `RecipeRepository` | 테이블별 등록·조회 DAO. |
| `ingredient_parser` | `RecipeIngredientParser` | 원문 재료의 staging 후보 생성기. |

### Constructor Summary

`def __init__(self, sql_session, user_id=SYSTEM_USER_ID):` — PostgreSQL 세션을 받아 등록 DAO와 재료 파서를 준비한다.

생성·주입 경로: `setup.register_recipe_csv.main`에서 SQL 세션을 전달해 만든다.. 세부 매개변수와 처리 내용은 [RecipeRegisterService.__init__](#reciperegisterservice-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#reciperegisterservice-__init__) | `타입 힌트 없음` | PostgreSQL 세션을 받아 등록 DAO와 재료 파서를 준비한다. |
| [read_csv](#reciperegisterservice-read_csv) | `list[dict[str, str]]` | CSV를 읽어 행 dict 목록을 돌려준다. 파일은 읽기만 하고 변경하지 않는다. |
| [validate_rows](#reciperegisterservice-validate_rows) | `list[str]` | 행 수, RCP_SEQ 공란·중복, 레시피명·분류·조리 방법 공란을 검사한다. Returns 차단 오류 목록. |
| [build_plan](#reciperegisterservice-build_plan) | `RecipeLoadPlan` | CSV 행을 테이블별 등록 후보로 바꾸고 매핑·충돌·품질 문제를 분류한다. |
| [cook_method_map](#reciperegisterservice-cook_method_map) | `dict[str, str]` | 현재 DB 코드와 확정 코드표를 검증해 합친 조리 방법명 → 코드 dict. |
| [register_reference_masters](#reciperegisterservice-register_reference_masters) | `dict[str, int]` | CSV 실제 고유값으로 요리 종류를, 확정 코드표로 조리 방법 공통코드를 등록한다. 기존 행은 지우지 않는다. |
| [register_ingredient_master](#reciperegisterservice-register_ingredient_master) | `tuple[dict[str, int], list[str]]` | 식재료 사전을 ingr → ingr_als 순서로 등록한다. 새 행만 INSERT하고 기존 ID는 그대로 둔다. |
| [resolve_batch](#reciperegisterservice-resolve_batch) | `tuple[str, str]` | 같은 수집 회차 재실행이면 기존 rcp_raw_id를, 아니면 새 rcp_raw_id를 돌려준다. |
| [_raw_row_matches](#reciperegisterservice-_raw_row_matches) | `bool` | 저장된 원본 행이 같은 행 순번의 CSV 행과 55개 컬럼까지 같은지 확인한다(줄바꿈 종류만 무시). |
| [write_plan](#reciperegisterservice-write_plan) | `dict[str, int]` | 등록 후보를 순서대로 DB에 쓴다. 반드시 ``sql_session.transaction()`` 안에서 호출한다. |
| [_verify_written](#reciperegisterservice-_verify_written) | `None` | 트랜잭션 안에서 이번 회차 결과를 다시 세어 기대치보다 적으면 예외로 ROLLBACK시킨다. |
| [check_target_model](#reciperegisterservice-check_target_model) | `None` | 연결 스키마가 목표 모델인지 확인한다. 기존 모델 스키마에 새 SQL로 쓰지 않기 위한 가드. |
| [register](#reciperegisterservice-register) | `RecipeLoadResult` | CSV 검증부터 DB 등록과 사후 정합성 검사까지 실행한다. |

### RecipeRegisterService __init__

```python
def __init__(self, sql_session, user_id=SYSTEM_USER_ID):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. PostgreSQL 세션을 받아 등록 DAO와 재료 파서를 준비한다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (304행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `sql_session` | `타입 힌트 없음` | Named SQL 실행 세션 |
| `user_id` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRegisterService read_csv

```python
@staticmethod
def read_csv(csv_path: str | Path) -> list[dict[str, str]]:
```

- **주요 호출자:** `RecipeRegisterService.register`
- **반환:** `list[dict[str, str]]`. CSV를 읽어 행 dict 목록을 돌려준다. 파일은 읽기만 하고 변경하지 않는다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (314행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `csv_path` | `str \| Path` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

**예외:** RecipeLoadError: 헤더 누락·중복·추가, 행 길이 불일치, 999,999행 초과.

### RecipeRegisterService validate_rows

```python
@staticmethod
def validate_rows(rows: list[dict[str, str]], expected_count: int | None=EXPECTED_SOURCE_ROW_COUNT) -> list[str]:
```

- **주요 호출자:** `RecipeRegisterService.register`
- **반환:** `list[str]`. 행 수, RCP_SEQ 공란·중복, 레시피명·분류·조리 방법 공란을 검사한다. Returns 차단 오류 목록.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (352행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rows` | `list[dict[str, str]]` | 조회 또는 적재 대상 행 목록 |
| `expected_count` | `int \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRegisterService build_plan

```python
def build_plan(self, rows, category_map, cook_method_map, existing_recipe_keys, existing_category_relations=None) -> RecipeLoadPlan:
```

- **주요 호출자:** `RecipeRegisterService.register`
- **반환:** `RecipeLoadPlan`. CSV 행을 테이블별 등록 후보로 바꾸고 매핑·충돌·품질 문제를 분류한다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (376행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rows` | `타입 힌트 없음` | 적재 대상 CSV 행(``--limit`` 적용 후, ``RCP_RAW_SEQ`` 포함). |
| `category_map` | `타입 힌트 없음` | 요리 종류명 → rcp_cat_id. |
| `cook_method_map` | `타입 힌트 없음` | 조리 방법명(common_cd_nm) → COOK_MTHD 코드(common_cd). |
| `existing_recipe_keys` | `타입 힌트 없음` | 이미 등록된 rcp_seq → (rcp_id, rcp_raw_id). |
| `existing_category_relations` | `타입 힌트 없음` | 이미 등록된 rcp_id → 요리 분류 ID 집합. |

**처리 흐름:** CSV 각 행을 원본, 정제 레시피, 단계, 재료 staging, 분류 관계 후보로 나누고 등록 차단 오류와 검토 항목을 모은다.

**관련 API:** [recipe_repository](../recipe_recommender/recipe_repository.md), [recipe_ingredient_parser](recipe_ingredient_parser.md)

### RecipeRegisterService cook_method_map

```python
def cook_method_map(self, seed: dict[str, str] | None=None) -> dict[str, str]:
```

- **주요 호출자:** `RecipeRegisterService.register_reference_masters`, `RecipeRegisterService.register`
- **반환:** `dict[str, str]`. 현재 DB 코드와 확정 코드표를 검증해 합친 조리 방법명 → 코드 dict.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (480행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `seed` | `dict[str, str] \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRegisterService register_reference_masters

```python
def register_reference_masters(self, source_rows, cook_method_seed: dict[str, str] | None=None) -> dict[str, int]:
```

- **주요 호출자:** `RecipeRegisterService.register`
- **반환:** `dict[str, int]`. CSV 실제 고유값으로 요리 종류를, 확정 코드표로 조리 방법 공통코드를 등록한다. 기존 행은 지우지 않는다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (484행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `source_rows` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `cook_method_seed` | `dict[str, str] \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRegisterService register_ingredient_master

```python
def register_ingredient_master(self, seed: IngredientSeed) -> tuple[dict[str, int], list[str]]:
```

- **주요 호출자:** `RecipeRegisterService.register`
- **반환:** `tuple[dict[str, int], list[str]]`. 식재료 사전을 ingr → ingr_als 순서로 등록한다. 새 행만 INSERT하고 기존 ID는 그대로 둔다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (500행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `seed` | `IngredientSeed` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRegisterService resolve_batch

```python
def resolve_batch(self, source_rows) -> tuple[str, str]:
```

- **주요 호출자:** `RecipeRegisterService.register`
- **반환:** `tuple[str, str]`. 같은 수집 회차 재실행이면 기존 rcp_raw_id를, 아니면 새 rcp_raw_id를 돌려준다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (529행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `source_rows` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRegisterService _raw_row_matches

```python
@staticmethod
def _raw_row_matches(stored: dict, source: dict | None) -> bool:
```

- **주요 호출자:** `RecipeRegisterService.resolve_batch`
- **반환:** `bool`. 저장된 원본 행이 같은 행 순번의 CSV 행과 55개 컬럼까지 같은지 확인한다(줄바꿈 종류만 무시).
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (545행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `stored` | `dict` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `source` | `dict \| None` | PostgreSQL 원천 또는 원천 Repository |

### RecipeRegisterService write_plan

```python
def write_plan(self, plan: RecipeLoadPlan, rcp_raw_id: str) -> dict[str, int]:
```

- **주요 호출자:** `RecipeRegisterService.register`
- **반환:** `dict[str, int]`. 등록 후보를 순서대로 DB에 쓴다. 반드시 ``sql_session.transaction()`` 안에서 호출한다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (552행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `plan` | `RecipeLoadPlan` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `rcp_raw_id` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

**처리 흐름:** 마스터와 원본을 먼저 쓰고 레시피·관계·단계·staging을 순서대로 기록한다. 상위 `register`의 트랜잭션 안에서만 호출한다.

**관련 API:** [recipe_repository](../recipe_recommender/recipe_repository.md), [recipe_ingredient_parser](recipe_ingredient_parser.md)

### RecipeRegisterService _verify_written

```python
def _verify_written(self, plan: RecipeLoadPlan, rcp_raw_id: str) -> None:
```

- **주요 호출자:** `RecipeRegisterService.write_plan`
- **반환:** `None`. 트랜잭션 안에서 이번 회차 결과를 다시 세어 기대치보다 적으면 예외로 ROLLBACK시킨다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (590행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `plan` | `RecipeLoadPlan` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `rcp_raw_id` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeRegisterService check_target_model

```python
def check_target_model(self) -> None:
```

- **주요 호출자:** `RecipeRegisterService.register`
- **반환:** `None`. 연결 스키마가 목표 모델인지 확인한다. 기존 모델 스키마에 새 SQL로 쓰지 않기 위한 가드.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (607행)

### RecipeRegisterService register

```python
def register(self, csv_path, *, limit: int | None=None, dry_run: bool=True, seed: IngredientSeed | None=None, rehearse: bool=False) -> RecipeLoadResult:
```

- **주요 호출자:** `setup.register_recipe_csv.main`
- **반환:** `RecipeLoadResult`. CSV 검증부터 DB 등록과 사후 정합성 검사까지 실행한다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (614행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `csv_path` | `타입 힌트 없음` | 원본 CSV 경로. |
| `limit` | `int \| None` | 앞에서부터 N건만 적재. None이면 전체. |
| `dry_run` | `bool` | True면 읽기 전용 조회만 하고 DB를 변경하지 않는다. |
| `seed` | `IngredientSeed \| None` | 식재료 사전. None이면 ``data/`` 의 기본 사전을 읽는다. |
| `rehearse` | `bool` | True면 실제와 같이 쓰고 집계·정합성 검사까지 한 뒤 전체를 ROLLBACK한다. |

**처리 흐름:** CSV 등록 계획을 확인하고 원본·정제·단계·재료 staging을 하나의 PostgreSQL 트랜잭션에 기록한다.

**관련 API:** [recipe_repository](../recipe_recommender/recipe_repository.md), [recipe_ingredient_parser](recipe_ingredient_parser.md)

**예외:** RecipeLoadError: 구조·매핑 오류가 있어 적재하면 안 되는 경우(dry-run 포함).

**부작용:** 호출 경로와 트랜잭션 조건에 따라 DB 상태를 변경한다. 상세 조건은 소스와 [실행 흐름](../../04_execution_flow.md)을 확인한다.

## Function normalize_newlines

```python
def normalize_newlines(value: str | None) -> str | None:
```

- **호출자:** `setup.register_recipe_csv.main`
- **반환:** `str | None`. CRLF·CR을 LF로 바꾼다. 원본 저장값은 바꾸지 않고 비교·정제 값에만 쓴다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (143행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `str \| None` | 처리하거나 설정할 값 |

## Function _null_if_empty

```python
def _null_if_empty(value: str | None) -> str | None:
```

- **호출자:** `setup.register_recipe_csv.main`
- **반환:** `str | None`. CSV에는 NULL 개념이 없으므로 빈 문자열만 NULL로 저장한다. 그 외 값은 공백 포함 원형 그대로.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (148행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `str \| None` | 처리하거나 설정할 값 |

## Function _clean_text

```python
def _clean_text(value: str | None) -> str | None:
```

- **호출자:** `setup.register_recipe_csv.main`
- **반환:** `str | None`. 정제 컬럼용: 줄바꿈을 LF로 맞추고 앞뒤 공백만 제거하며 비면 NULL.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (153행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `str \| None` | 처리하거나 설정할 값 |

## Function raw_seq_for

```python
def raw_seq_for(position: int) -> str:
```

- **호출자:** `setup.register_recipe_csv.main`
- **반환:** `str`. CSV 행 위치(1부터)를 회차 내 원본 행 순번 문자열로 만든다. 999,999 초과는 오류.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (161행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `position` | `int` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function strip_step_prefix

```python
def strip_step_prefix(text: str, step_no: int) -> str:
```

- **호출자:** `setup.register_recipe_csv.main`
- **반환:** `str`. 조리 설명 앞의 '1. ' 같은 번호가 단계 번호와 같을 때만 제거한다. 나머지 원문은 유지한다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (168행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `text` | `str` | 처리할 입력 문자열 |
| `step_no` | `int` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function evaluate_nutrition

```python
def evaluate_nutrition(row: dict[str, str]) -> tuple[dict[str, Decimal | None], str, str | None]:
```

- **호출자:** `setup.register_recipe_csv.main`
- **반환:** `tuple[dict[str, Decimal | None], str, str | None]`. 영양정보를 Decimal로 변환하고 자동 검증 상태를 정한다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (173행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `row` | `dict[str, str]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function load_ingredient_seed

```python
def load_ingredient_seed(ingredient_path: Path=INGR_SEED_PATH) -> IngredientSeed:
```

- **호출자:** `setup.register_recipe_csv.main`
- **반환:** `IngredientSeed`. 식재료 표준명·별칭 사전을 읽고 모순을 검사한다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (222행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `ingredient_path` | `Path` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

**예외:** RecipeLoadError: 헤더 불일치, 표준명 중복, 별칭이 다른 표준명/별칭과 겹치는 경우.

## Function load_cook_method_seed

```python
def load_cook_method_seed(path: Path=COOK_MTHD_SEED_PATH) -> dict[str, str]:
```

- **호출자:** `setup.register_recipe_csv.main`
- **반환:** `dict[str, str]`. 조리 방법 확정 코드표를 읽는다. Returns ``{common_cd: common_cd_nm}`` (파일 순서).
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (251행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `path` | `Path` | 읽거나 쓸 파일 경로 |

**예외:** RecipeLoadError: 헤더 불일치, 6자리 숫자 문자열이 아닌 코드, 코드·명칭 공란·중복.

## Function resolve_cook_method_map

```python
def resolve_cook_method_map(db_codes: dict[str, str], seed: dict[str, str]) -> dict[str, str]:
```

- **호출자:** `setup.register_recipe_csv.main`
- **반환:** `dict[str, str]`. DB의 COOK_MTHD 코드와 확정 코드표를 합쳐 ``{common_cd_nm: common_cd}`` 를 만든다.
- **원본:** [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) (272행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `db_codes` | `dict[str, str]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `seed` | `dict[str, str]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
