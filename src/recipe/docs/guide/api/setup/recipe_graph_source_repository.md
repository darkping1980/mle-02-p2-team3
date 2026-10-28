# recipe_graph_source_repository 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.setup.recipe_graph_source_repository`
- **소스:** [recipe_recommender/setup/recipe_graph_source_repository.py](../../../../recipe_recommender/setup/recipe_graph_source_repository.py)
- **역할:** 그래프 적재에 필요한 PostgreSQL 목표 모델을 한 시점의 스냅샷으로 읽는다.
- **주요 호출자:** `RecipeGraphLoadService.prepare`
- **정의:** 클래스 2개, 모듈 함수 1개

- **직접 의존:** `..config`, `..sql_schema`

- **관련 API:** [recipe_graph_load_service](recipe_graph_load_service.md), [database_manager](../common/database_manager.md)

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [GraphSourceSnapshot](#graphsourcesnapshot) | dataclass DTO | 한 읽기 트랜잭션의 원천 테이블·카탈로그 조회값을 묶는 DTO. |
| [RecipeGraphSourceRepository](#recipegraphsourcerepository) | 클래스 | PostgreSQL SELECT 전용 DAO. 데이터와 스키마를 변경하지 않는다. |

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [recipe_graph_row](#function-recipe_graph_row) | `dict` | Neo4j 드라이버가 받도록 PostgreSQL Decimal을 float로 바꾼 레시피 dict를 만든다. |

## GraphSourceSnapshot

**dataclass DTO.** 한 읽기 트랜잭션의 원천 테이블·카탈로그 조회값을 묶는 DTO.

- **정의:** [recipe_graph_source_repository.py](../../../../recipe_recommender/setup/recipe_graph_source_repository.py) (14행)
- **생성 위치:** `RecipeGraphSourceRepository.read_snapshot`이 한 트랜잭션의 조회 결과로 만든다.

`@dataclass`는 필드 기반 생성자 등을 만드는 Python 장식자다. Java Record와 비슷한 DTO 용도지만 `frozen=True`여도 내부 리스트까지 불변으로 만들지는 않는다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `observed_at` | `datetime` | 스냅샷을 읽은 DB 시각. |
| `database` | `str` | 조회 대상 PostgreSQL 데이터베이스명. |
| `role` | `str` | 원천 조회에 사용한 DB 사용자. |
| `recipe_categories` | `list[dict]` | 레시피 분류 노드 원천 행. |
| `ingredients` | `list[dict]` | 표준 식재료 노드 원천 행. |
| `recipes` | `list[dict]` | 레시피 노드 원천 행. |
| `recipe_category_links` | `list[dict]` | 레시피와 분류의 관계 원천 행. |
| `aliases` | `list[dict]` | 식재료 별칭; 정합성 검사에 사용한다. |
| `uses` | `list[dict]` | 레시피의 식재료 사용 관계 원천 행. |
| `steps` | `list[dict]` | 조리 단계(rcp_step) 노드·RCP_HAS_STEP 관계 원천 행. (rcp_id, step_no) 순서. |
| `raw_refs` | `list[dict]` | 식약처 원본 ID와 번호 참조 행. |
| `stage_status` | `list[dict]` | 식재료 중간 적재 상태별 건수. |
| `pk_definitions` | `dict[str, list[str]]` | 테이블별 기본 키 컬럼 순서. |
| `column_types` | `dict[tuple[str, str], tuple[str, bool]]` | (테이블, 컬럼)별 DB 타입·NOT NULL 여부. |
| `code_groups` | `list[dict]` | 조리 방법 등 공통코드 그룹 검증 원천. |
| `counts` | `dict[str, int]` | `@property`로 계산되는 읽기 속성; [counts 상세](#graphsourcesnapshot-counts-getter) 참조 |

### Constructor Summary

명시적 생성자는 없다. `@dataclass`가 선언된 필드 순서로 생성자를 만든다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [counts (getter)](#graphsourcesnapshot-counts-getter) | `dict[str, int]` | 노드·관계별 원천 행 수를 적재 후 그래프 건수 비교용으로 계산한다. |

### GraphSourceSnapshot counts getter

```python
@property
def counts(self) -> dict[str, int]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict[str, int]`. 노드·관계별 원천 행 수를 적재 후 그래프 건수 비교용으로 계산한다.
- **원본:** [recipe_graph_source_repository.py](../../../../recipe_recommender/setup/recipe_graph_source_repository.py) (38행)

## RecipeGraphSourceRepository

**클래스.** PostgreSQL SELECT 전용 DAO. 데이터와 스키마를 변경하지 않는다.

- **정의:** [recipe_graph_source_repository.py](../../../../recipe_recommender/setup/recipe_graph_source_repository.py) (51행)
- **생성 위치:** `setup.load_recipe_graph.main`에서 만든다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `schema` | `타입 힌트 없음` | 생성자 59행에서 설정; PostgreSQL SELECT 전용 DAO. 데이터와 스키마를 변경하지 않는다. |

### Constructor Summary

`def __init__(self, schema: str | None=None):` — 명시한 스키마 또는 환경 설정에서 조회 스키마를 결정한다.

생성·주입 경로: `setup.load_recipe_graph.main`에서 만든다.. 세부 매개변수와 처리 내용은 [RecipeGraphSourceRepository.__init__](#recipegraphsourcerepository-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#recipegraphsourcerepository-__init__) | `타입 힌트 없음` | 명시한 스키마 또는 환경 설정에서 조회 스키마를 결정한다. |
| [read_snapshot](#recipegraphsourcerepository-read_snapshot) | `GraphSourceSnapshot` | REPEATABLE READ READ ONLY 트랜잭션에서 노드·관계 원천을 함께 읽는다. |

### RecipeGraphSourceRepository __init__

```python
def __init__(self, schema: str | None=None):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 명시한 스키마 또는 환경 설정에서 조회 스키마를 결정한다.
- **원본:** [recipe_graph_source_repository.py](../../../../recipe_recommender/setup/recipe_graph_source_repository.py) (57행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `schema` | `str \| None` | PostgreSQL 대상 스키마 |

### RecipeGraphSourceRepository read_snapshot

```python
def read_snapshot(self) -> GraphSourceSnapshot:
```

- **주요 호출자:** `RecipeGraphLoadService.prepare`
- **반환:** `GraphSourceSnapshot`. REPEATABLE READ READ ONLY 트랜잭션에서 노드·관계 원천을 함께 읽는다.
- **원본:** [recipe_graph_source_repository.py](../../../../recipe_recommender/setup/recipe_graph_source_repository.py) (61행)

**처리 흐름:** PostgreSQL REPEATABLE READ READ ONLY 트랜잭션으로 노드·관계·카탈로그 행을 같은 시점에 읽고 롤백으로 연결을 정리한다.

**관련 API:** [recipe_graph_load_service](recipe_graph_load_service.md), [database_manager](../common/database_manager.md)

## Function recipe_graph_row

```python
def recipe_graph_row(row: dict) -> dict:
```

- **호출자:** `RecipeGraphLoadService.prepare`
- **반환:** `dict`. Neo4j 드라이버가 받도록 PostgreSQL Decimal을 float로 바꾼 레시피 dict를 만든다.
- **원본:** [recipe_graph_source_repository.py](../../../../recipe_recommender/setup/recipe_graph_source_repository.py) (145행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `row` | `dict` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
