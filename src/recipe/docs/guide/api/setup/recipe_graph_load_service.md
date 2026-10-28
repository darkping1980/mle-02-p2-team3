# recipe_graph_load_service 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.setup.recipe_graph_load_service`
- **소스:** [recipe_recommender/setup/recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py)
- **역할:** PostgreSQL 목표 모델을 검증하고 Neo4j 레시피 그래프에 적재·대조한다.
- **주요 호출자:** `setup.load_recipe_graph.main`
- **정의:** 클래스 2개, 모듈 함수 3개

- **직접 의존:** `..recipe_graph_repository`, `..name_normalization`, `.recipe_graph_source_repository`

- **관련 API:** [recipe_graph_source_repository](recipe_graph_source_repository.md), [recipe_graph_repository](../recipe_recommender/recipe_graph_repository.md)

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [PreparedGraph](#preparedgraph) | dataclass DTO | 검증된 원천과 적재 단계별 입력 행을 묶는 불변 필드 DTO. |
| [RecipeGraphLoadService](#recipegraphloadservice) | 클래스 | 원천 검증, 적재 순서, 결과 비교를 조정하는 Service. |

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [_key](#function-_key) | `tuple` | 행에서 지정한 컬럼 값을 순서대로 뽑아 비교용 복합 키를 만든다. |
| [_unique_keys](#function-_unique_keys) | `set[tuple]` | 적재 전 원천 키의 빈 값·타입·중복을 검사하고 키 집합을 반환한다. |
| [_step_rows](#function-_step_rows) | `list[dict]` | 조리 단계 원천을 검사하고 Neo4j 적재 행으로 바꾼다. |

## PreparedGraph

**dataclass DTO.** 검증된 원천과 적재 단계별 입력 행을 묶는 불변 필드 DTO.

- **정의:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (134행)
- **생성 위치:** `RecipeGraphLoadService.prepare`가 검증된 스냅샷과 적재 행을 묶어 만든다.

`@dataclass`는 필드 기반 생성자 등을 만드는 Python 장식자다. Java Record와 비슷한 DTO 용도지만 `frozen=True`여도 내부 리스트까지 불변으로 만들지는 않는다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `source` | `GraphSourceSnapshot` | 같은 읽기 시점의 PostgreSQL 원천과 스키마 정보. |
| `stages` | `dict[str, list[dict]]` | STAGES의 단계명별 Neo4j MERGE 입력 행. |
| `expected_counts` | `dict[str, int]` | `@property`로 계산되는 읽기 속성; [expected_counts 상세](#preparedgraph-expected_counts-getter) 참조 |

### Constructor Summary

명시적 생성자는 없다. `@dataclass`가 선언된 필드 순서로 생성자를 만든다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [expected_counts (getter)](#preparedgraph-expected_counts-getter) | `dict[str, int]` | 적재 후 그래프와 비교할 원천 노드·관계 건수. |

### PreparedGraph expected_counts getter

```python
@property
def expected_counts(self) -> dict[str, int]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict[str, int]`. 적재 후 그래프와 비교할 원천 노드·관계 건수.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (140행)

## RecipeGraphLoadService

**클래스.** 원천 검증, 적재 순서, 결과 비교를 조정하는 Service.

- **정의:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (145행)
- **생성 위치:** `setup.load_recipe_graph.main`에서 두 Repository를 전달해 만든다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `source` | `타입 힌트 없음` | 생성자 153행에서 설정; 원천 검증, 적재 순서, 결과 비교를 조정하는 Service. |
| `graph` | `타입 힌트 없음` | 생성자 154행에서 설정; 원천 검증, 적재 순서, 결과 비교를 조정하는 Service. |

### Constructor Summary

`def __init__(self, source: RecipeGraphSourceRepository, graph: RecipeGraphRepository):` — 원천 조회 DAO와 그래프 DAO를 적재 절차에 주입한다.

생성·주입 경로: `setup.load_recipe_graph.main`에서 두 Repository를 전달해 만든다.. 세부 매개변수와 처리 내용은 [RecipeGraphLoadService.__init__](#recipegraphloadservice-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#recipegraphloadservice-__init__) | `타입 힌트 없음` | 원천 조회 DAO와 그래프 DAO를 적재 절차에 주입한다. |
| [prepare](#recipegraphloadservice-prepare) | `PreparedGraph` | PostgreSQL 한 시점의 데이터를 읽고 키·참조·코드·별칭을 검사해 배치 입력으로 변환한다. |
| [_check_schema_names](#recipegraphloadservice-_check_schema_names) | `None` | 실제 Neo4j 제약·인덱스 이름이 목표 모델과 맞는지 확인한다. |
| [_expected_sets](#recipegraphloadservice-_expected_sets) | `dict[str, set[tuple]]` | 준비된 PostgreSQL 원천을 노드·관계별 비교 키 집합으로 바꾼다. |
| [_actual_sets](#recipegraphloadservice-_actual_sets) | `dict[str, set[tuple]]` | Neo4j 조회 행을 원천과 비교할 키 집합으로 바꾼다. |
| [preflight_graph](#recipegraphloadservice-preflight_graph) | `dict` | 쓰기 전에 기존 그래프가 이번 PostgreSQL 원천의 부분집합인지 확인한다. |
| [apply](#recipegraphloadservice-apply) | `dict` | 제약조건을 확인하고 노드 3종 다음 관계 2종을 배치별로 적재·검증한다. |
| [verify](#recipegraphloadservice-verify) | `dict` | Neo4j 키 집합과 건수를 원천 스냅샷과 비교한다(읽기 전용). |
| [verify_examples](#recipegraphloadservice-verify_examples) | `dict` | 대표 레시피·재료의 그래프 조회값을 준비된 원천과 대조한다. |
| [verify_query_examples](#recipegraphloadservice-verify_query_examples) | `dict` | 추천 조회용 Named Cypher의 결과 예시를 원천과 대조한다. |
| [verify_search_scenarios](#recipegraphloadservice-verify_search_scenarios) | `dict` | 식재료 기반 검색 질의 결과를 같은 PostgreSQL 스냅샷에서 계산한 기대값과 비교한다(읽기 전용). |

### RecipeGraphLoadService __init__

```python
def __init__(self, source: RecipeGraphSourceRepository, graph: RecipeGraphRepository):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 원천 조회 DAO와 그래프 DAO를 적재 절차에 주입한다.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (151행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `source` | `RecipeGraphSourceRepository` | PostgreSQL 원천 또는 원천 Repository |
| `graph` | `RecipeGraphRepository` | Neo4j 조회·쓰기 Repository |

### RecipeGraphLoadService prepare

```python
def prepare(self) -> PreparedGraph:
```

- **주요 호출자:** `setup.load_recipe_graph.main`
- **반환:** `PreparedGraph`. PostgreSQL 한 시점의 데이터를 읽고 키·참조·코드·별칭을 검사해 배치 입력으로 변환한다.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (156행)

**처리 흐름:** 스냅샷의 키·참조·타입·코드·별칭을 검증한 뒤 Neo4j 단계별 배치 행을 준비한다.

**관련 API:** [recipe_graph_source_repository](recipe_graph_source_repository.md), [recipe_graph_repository](../recipe_recommender/recipe_graph_repository.md)

### RecipeGraphLoadService _check_schema_names

```python
def _check_schema_names(self, inspection: dict, *, require_all: bool) -> None:
```

- **주요 호출자:** `RecipeGraphLoadService.apply`, `RecipeGraphLoadService.preflight_graph`
- **반환:** `None`. 실제 Neo4j 제약·인덱스 이름이 목표 모델과 맞는지 확인한다.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (254행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `inspection` | `dict` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `require_all` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### RecipeGraphLoadService _expected_sets

```python
def _expected_sets(self, prepared: PreparedGraph) -> dict[str, set[tuple]]:
```

- **주요 호출자:** `RecipeGraphLoadService.preflight_graph`, `RecipeGraphLoadService.verify`
- **반환:** `dict[str, set[tuple]]`. 준비된 PostgreSQL 원천을 노드·관계별 비교 키 집합으로 바꾼다.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (285행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `prepared` | `PreparedGraph` | 검증을 마친 그래프 적재 입력 |

### RecipeGraphLoadService _actual_sets

```python
def _actual_sets(self, rows: dict[str, list[dict]]) -> dict[str, set[tuple]]:
```

- **주요 호출자:** `RecipeGraphLoadService.preflight_graph`, `RecipeGraphLoadService.verify`
- **반환:** `dict[str, set[tuple]]`. Neo4j 조회 행을 원천과 비교할 키 집합으로 바꾼다.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (295행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rows` | `dict[str, list[dict]]` | 조회 또는 적재 대상 행 목록 |

### RecipeGraphLoadService preflight_graph

```python
def preflight_graph(self, prepared: PreparedGraph) -> dict:
```

- **주요 호출자:** `RecipeGraphLoadService.apply`
- **반환:** `dict`. 쓰기 전에 기존 그래프가 이번 PostgreSQL 원천의 부분집합인지 확인한다.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (299행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `prepared` | `PreparedGraph` | 검증을 마친 그래프 적재 입력 |

**처리 흐름:** 쓰기 전에 실제 그래프의 스키마 이름과 키 집합이 목표 모델 및 원천과 충돌하지 않는지 확인한다.

**관련 API:** [recipe_graph_source_repository](recipe_graph_source_repository.md), [recipe_graph_repository](../recipe_recommender/recipe_graph_repository.md)

### RecipeGraphLoadService apply

```python
def apply(self, prepared: PreparedGraph, batch_size: int=500) -> dict:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict`. 제약조건을 확인하고 노드 3종 다음 관계 2종을 배치별로 적재·검증한다.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (320행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `prepared` | `PreparedGraph` | 검증을 마친 그래프 적재 입력 |
| `batch_size` | `int` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

**처리 흐름:** 사전 점검 후 제약을 확인하고 분류·식재료·레시피 노드, 두 관계 순으로 배치 적재한다. 완료 후 원천과 대조한다.

**관련 API:** [recipe_graph_source_repository](recipe_graph_source_repository.md), [recipe_graph_repository](../recipe_recommender/recipe_graph_repository.md)

**부작용:** 호출 경로와 트랜잭션 조건에 따라 DB 상태를 변경한다. 상세 조건은 소스와 [실행 흐름](../../04_execution_flow.md)을 확인한다.

### RecipeGraphLoadService verify

```python
def verify(self, prepared: PreparedGraph) -> dict:
```

- **주요 호출자:** `RecipeGraphLoadService.apply`
- **반환:** `dict`. Neo4j 키 집합과 건수를 원천 스냅샷과 비교한다(읽기 전용).
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (347행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `prepared` | `PreparedGraph` | 검증을 마친 그래프 적재 입력 |

**처리 흐름:** 읽기 쿼리로 그래프 키와 건수를 다시 수집해 준비된 PostgreSQL 스냅샷과 비교한다.

**관련 API:** [recipe_graph_source_repository](recipe_graph_source_repository.md), [recipe_graph_repository](../recipe_recommender/recipe_graph_repository.md)

### RecipeGraphLoadService verify_examples

```python
def verify_examples(self, prepared: PreparedGraph) -> dict:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict`. 대표 레시피·재료의 그래프 조회값을 준비된 원천과 대조한다.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (372행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `prepared` | `PreparedGraph` | 검증을 마친 그래프 적재 입력 |

### RecipeGraphLoadService verify_query_examples

```python
def verify_query_examples(self, prepared: PreparedGraph) -> dict:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict`. 추천 조회용 Named Cypher의 결과 예시를 원천과 대조한다.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (405행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `prepared` | `PreparedGraph` | 검증을 마친 그래프 적재 입력 |

### RecipeGraphLoadService verify_search_scenarios

```python
def verify_search_scenarios(self, prepared: PreparedGraph, *, pantry_terms=('계란', '두부', '양파'), both_terms=('계란', '두부'), category_name='반찬') -> dict:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict`. 식재료 기반 검색 질의 결과를 같은 PostgreSQL 스냅샷에서 계산한 기대값과 비교한다(읽기 전용).
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (466행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `prepared` | `PreparedGraph` | 검증을 마친 그래프 적재 입력 |
| `pantry_terms` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `both_terms` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `category_name` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _key

```python
def _key(row: dict, *columns: str) -> tuple:
```

- **호출자:** `setup.load_recipe_graph.main`
- **반환:** `tuple`. 행에서 지정한 컬럼 값을 순서대로 뽑아 비교용 복합 키를 만든다.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (71행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `row` | `dict` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _unique_keys

```python
def _unique_keys(rows: list[dict], columns: tuple[str, ...], label: str) -> set[tuple]:
```

- **호출자:** `setup.load_recipe_graph.main`
- **반환:** `set[tuple]`. 적재 전 원천 키의 빈 값·타입·중복을 검사하고 키 집합을 반환한다.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (76행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rows` | `list[dict]` | 조회 또는 적재 대상 행 목록 |
| `columns` | `tuple[str, ...]` | 행에서 사용할 컬럼 이름 |
| `label` | `str` | 검증 오류에 표시할 대상 이름 |

**예외:** ValueError: 키가 비었거나 문자열이 아니거나 중복될 때.

## Function _step_rows

```python
def _step_rows(steps: list[dict], recipe_keys: set[tuple]) -> list[dict]:
```

- **호출자:** `RecipeGraphLoadService.prepare`
- **반환:** `list[dict]`. ``(rcp_id, step_no)`` 순서의 ``load_recipe_steps`` 입력 행.
- **원본:** [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) (93행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `steps` | `list[dict]` | ``recipe.rcp_step`` SELECT 결과. |
| `recipe_keys` | `set[tuple]` | 검증을 마친 레시피 키 집합. |

**처리 흐름:** 단계 번호는 원본 MANUAL 번호를 그대로 쓰므로 중간 번호가 비어 있어도 허용한다. 설명은 그대로 두고, 이미지 URL은 빈 문자열만 `None`으로 바꿔 Neo4j 속성을 생략하게 한다.

**예외:** ValueError: 키 중복·부모 누락·번호 범위(1~20)·빈 설명이 있을 때.

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
