# recipe_graph_repository 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.recipe_graph_repository`
- **소스:** [recipe_recommender/recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py)
- **역할:** Neo4j mapper를 호출하는 그래프 DAO. 업무 검증은 적재 Service가 담당한다.
- **주요 호출자:** `streamlit_app.get_pipeline`, `setup.load_recipe_graph`, `RecipeGraphLoadService`
- **정의:** 클래스 1개, 모듈 함수 0개

- **직접 의존:** `.config`, `.neo4j_connection`

- **관련 API:** [neo4j_db_session](../common/neo4j_db_session.md), [recipe_graph_load_service](../setup/recipe_graph_load_service.md)

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [RecipeGraphRepository](#recipegraphrepository) | 클래스 | Cypher 파일의 ``namespace.statement``를 Neo4jDbSession에 전달하는 DAO. |

## RecipeGraphRepository

**클래스.** Cypher 파일의 ``namespace.statement``를 Neo4jDbSession에 전달하는 DAO.

- **정의:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (23행)
- **생성 위치:** `streamlit_app.get_pipeline`과 `setup.load_recipe_graph.main`에서 만든다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `_owns_driver` | `타입 힌트 없음` | 생성자 41행에서 설정; Cypher 파일의 ``namespace.statement``를 Neo4jDbSession에 전달하는 DAO. |
| `driver` | `타입 힌트 없음` | 생성자 44행에서 설정; Cypher 파일의 ``namespace.statement``를 Neo4jDbSession에 전달하는 DAO. |
| `database` | `타입 힌트 없음` | 생성자 45행에서 설정; Cypher 파일의 ``namespace.statement``를 Neo4jDbSession에 전달하는 DAO. |
| `mapper` | `타입 힌트 없음` | 생성자 46행에서 설정; Cypher 파일의 ``namespace.statement``를 Neo4jDbSession에 전달하는 DAO. |

### Constructor Summary

`def __init__(self, driver=None, database: str | None=None):` — 드라이버와 mapper 세션을 준비한다. ``driver`` 생략 시 직접 연결한다.

생성·주입 경로: `streamlit_app.get_pipeline`과 `setup.load_recipe_graph.main`에서 만든다.. 세부 매개변수와 처리 내용은 [RecipeGraphRepository.__init__](#recipegraphrepository-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#recipegraphrepository-__init__) | `타입 힌트 없음` | 드라이버와 mapper 세션을 준비한다. ``driver`` 생략 시 직접 연결한다. |
| [close](#recipegraphrepository-close) | `None` | Repository가 직접 만든 드라이버만 닫는다. |
| [inspect](#recipegraphrepository-inspect) | `dict` | 서버 연결과 스키마·노드·관계 현황을 적재 전 검증용으로 조회한다. |
| [project_rows](#recipegraphrepository-project_rows) | `dict[str, list[dict]]` | 대상 노드와 관계의 키 목록을 종류별로 읽어 원천과 비교하게 한다. |
| [project_counts](#recipegraphrepository-project_counts) | `dict[str, int]` | 대상 그래프의 종류별 건수를 반환한다. |
| [validation_count](#recipegraphrepository-validation_count) | `int` | 검증용 Named Cypher의 ``n`` 값을 읽는다. |
| [sample_recipe](#recipegraphrepository-sample_recipe) | `list[dict]` | 레시피 ID의 노드와 관계 예시를 조회한다. |
| [sample_ingredient](#recipegraphrepository-sample_ingredient) | `list[dict]` | 식재료 ID의 노드와 관계 예시를 조회한다. |
| [create_schema](#recipegraphrepository-create_schema) | `None` | 적재 전 제약과 인덱스를 Named Cypher로 생성한다. |
| [explain_load_statements](#recipegraphrepository-explain_load_statements) | `int` | 읽기 세션에서 적재 Cypher의 EXPLAIN 계획만 확인하고 실행 수를 반환한다. |
| [write_batch](#recipegraphrepository-write_batch) | `None` | 한 배치의 부모 노드 매칭 건수를 확인한 뒤 같은 트랜잭션에서 MERGE한다. |
| [query_example](#recipegraphrepository-query_example) | `list[dict]` | 명명된 읽기 Cypher를 호출한다. 현재 일반 사용자 CLI가 아닌 검증 Service에서 사용한다. |
| [statement_text](#recipegraphrepository-statement_text) | `str` | ``namespace.name`` Named Cypher의 원문을 돌려준다(실행하지 않음). |

### RecipeGraphRepository __init__

```python
def __init__(self, driver=None, database: str | None=None):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 드라이버와 mapper 세션을 준비한다. ``driver`` 생략 시 직접 연결한다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (29행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `driver` | `타입 힌트 없음` | Neo4j 드라이버 |
| `database` | `str \| None` | Neo4j 데이터베이스명 |

### RecipeGraphRepository close

```python
def close(self) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. Repository가 직접 만든 드라이버만 닫는다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (50행)

### RecipeGraphRepository inspect

```python
def inspect(self) -> dict:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict`. 서버 연결과 스키마·노드·관계 현황을 적재 전 검증용으로 조회한다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (55행)

### RecipeGraphRepository project_rows

```python
def project_rows(self) -> dict[str, list[dict]]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict[str, list[dict]]`. 대상 노드와 관계의 키 목록을 종류별로 읽어 원천과 비교하게 한다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (77행)

### RecipeGraphRepository project_counts

```python
def project_counts(self) -> dict[str, int]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict[str, int]`. 대상 그래프의 종류별 건수를 반환한다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (92행)

### RecipeGraphRepository validation_count

```python
def validation_count(self, statement: str) -> int:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `int`. 검증용 Named Cypher의 ``n`` 값을 읽는다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (96행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement` | `str` | Named SQL 또는 Cypher 식별자 |

### RecipeGraphRepository sample_recipe

```python
def sample_recipe(self, recipe_id: str) -> list[dict]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `list[dict]`. 레시피 ID의 노드와 관계 예시를 조회한다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (100행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `recipe_id` | `str` | 레시피 ID |

### RecipeGraphRepository sample_ingredient

```python
def sample_ingredient(self, ingredient_id: str) -> list[dict]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `list[dict]`. 식재료 ID의 노드와 관계 예시를 조회한다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (104행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `ingredient_id` | `str` | 식재료 ID |

### RecipeGraphRepository create_schema

```python
def create_schema(self) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 적재 전 제약과 인덱스를 Named Cypher로 생성한다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (108행)

**부작용:** 호출 경로와 트랜잭션 조건에 따라 DB 상태를 변경한다. 상세 조건은 소스와 [실행 흐름](../../04_execution_flow.md)을 확인한다.

### RecipeGraphRepository explain_load_statements

```python
def explain_load_statements(self) -> int:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `int`. 읽기 세션에서 적재 Cypher의 EXPLAIN 계획만 확인하고 실행 수를 반환한다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (116행)

### RecipeGraphRepository write_batch

```python
def write_batch(self, statement: str, rows: list[dict], check_statement: str | None=None) -> None:
```

- **주요 호출자:** `RecipeGraphLoadService.apply`
- **반환:** `None`. 한 배치의 부모 노드 매칭 건수를 확인한 뒤 같은 트랜잭션에서 MERGE한다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (136행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement` | `str` | Named SQL 또는 Cypher 식별자 |
| `rows` | `list[dict]` | 조회 또는 적재 대상 행 목록 |
| `check_statement` | `str \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

**처리 흐름:** 부모 노드 매칭 건수를 검사하고 같은 Neo4j 트랜잭션 안에서 배치 MERGE를 실행한다.

**관련 API:** [neo4j_db_session](../common/neo4j_db_session.md), [recipe_graph_load_service](../setup/recipe_graph_load_service.md)

**부작용:** 호출 경로와 트랜잭션 조건에 따라 DB 상태를 변경한다. 상세 조건은 소스와 [실행 흐름](../../04_execution_flow.md)을 확인한다.

### RecipeGraphRepository query_example

```python
def query_example(self, name: str, parameters: dict) -> list[dict]:
```

- **주요 호출자:** `PantryRecommendService._query`, `GraphQuestionService._query`와 적재 검증 Service
- **반환:** `list[dict]`. 명명된 읽기 Cypher를 호출한다. 현재 일반 사용자 CLI가 아닌 검증 Service에서 사용한다.
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (145행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `name` | `str` | 조회할 이름 또는 식별자 |
| `parameters` | `dict` | 쿼리에 바인딩할 매개변수 |

### RecipeGraphRepository statement_text

```python
def statement_text(self, statement: str) -> str:
```

- **주요 호출자:** 제출용 노트북(적재·질문 Cypher 원문 출력), `GraphQuestionService.cypher_text`(현재 화면에서는 사용하지 않음)
- **반환:** `str`. ``namespace.name`` Named Cypher의 원문을 돌려준다(실행하지 않음).
- **원본:** [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) (149행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement` | `str` | `recipe_graph_queries.similar_recipes` 같은 전체 식별자 |

**예외:** 없는 식별자면 `Neo4jDbSession._query`의 `ValueError`/`LookupError`.

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
