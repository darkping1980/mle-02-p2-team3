# database 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.database`
- **소스:** [recipe_recommender/database.py](../../../../recipe_recommender/database.py)
- **역할:** 레시피 프로젝트의 PostgreSQL 연결과 SQL mapper 경로를 구성한다.
- **주요 호출자:** `search_recipe.main`, CSV 등록 CLI와 스키마별 조회 경로
- **정의:** 클래스 0개, 모듈 함수 7개

- **직접 의존:** `recipe_recommender.config`, `recipe_recommender.sql_schema`

- **관련 API:** [database_manager](../common/database_manager.md), [postgres_db_session](../common/postgres_db_session.md)

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [classify_pool_mode](#function-classify_pool_mode) | `str` | 호스트·포트를 노출하지 않고 Supabase 풀러 유형을 분류한다. |
| [get_pool_mode](#function-get_pool_mode) | `str` | 환경변수 ``DB_URL``에서 첫 호스트·포트를 읽어 연결 유형을 반환한다. |
| [_get_manager](#function-_get_manager) | `타입 힌트 없음` | 호출 프로세스에서 재사용할 PostgreSQL 연결 관리자를 준비한다. |
| [_close_manager](#function-_close_manager) | `None` | 프로세스 종료 시 캐시된 연결 관리자를 닫는다. |
| [_mapper_root_for](#function-_mapper_root_for) | `Path` | 기본 스키마면 패키지 폴더, 아니면 ``recipe.`` 한정자를 바꾼 ``recipe.sql`` 사본 폴더. |
| [create_recipe_sql_session](#function-create_recipe_sql_session) | `타입 힌트 없음` | ``recipe.sql`` mapper를 등록한 공통 ``PostgresDbSession`` 을 만든다. |
| [recipe_connection](#function-recipe_connection) | `Iterator[object]` | 레시피 스키마를 search_path로 설정한 연결을 ``with`` 블록에 제공한다. |

## Function classify_pool_mode

```python
def classify_pool_mode(host: str | None, port: int | None) -> str:
```

- **호출자:** `search_recipe.main`, CSV 등록 CLI와 스키마별 조회 경로
- **반환:** `str`. 호스트·포트를 노출하지 않고 Supabase 풀러 유형을 분류한다.
- **원본:** [database.py](../../../../recipe_recommender/database.py) (25행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `host` | `str \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `port` | `int \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function get_pool_mode

```python
def get_pool_mode() -> str:
```

- **호출자:** `search_recipe.main`, CSV 등록 CLI와 스키마별 조회 경로
- **반환:** `str`. 환경변수 ``DB_URL``에서 첫 호스트·포트를 읽어 연결 유형을 반환한다.
- **원본:** [database.py](../../../../recipe_recommender/database.py) (39행)

## Function _get_manager

```python
def _get_manager():
```

- **호출자:** `search_recipe.main`, CSV 등록 CLI와 스키마별 조회 경로
- **반환:** `타입 힌트 없음`. 호출 프로세스에서 재사용할 PostgreSQL 연결 관리자를 준비한다.
- **원본:** [database.py](../../../../recipe_recommender/database.py) (53행)

## Function _close_manager

```python
@atexit.register
def _close_manager() -> None:
```

- **호출자:** `search_recipe.main`, CSV 등록 CLI와 스키마별 조회 경로
- **반환:** `None`. 프로세스 종료 시 캐시된 연결 관리자를 닫는다.
- **원본:** [database.py](../../../../recipe_recommender/database.py) (67행)

## Function _mapper_root_for

```python
def _mapper_root_for(schema: str) -> Path:
```

- **호출자:** `search_recipe.main`, CSV 등록 CLI와 스키마별 조회 경로
- **반환:** `Path`. 기본 스키마면 패키지 폴더, 아니면 ``recipe.`` 한정자를 바꾼 ``recipe.sql`` 사본 폴더.
- **원본:** [database.py](../../../../recipe_recommender/database.py) (75행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `schema` | `str` | PostgreSQL 대상 스키마 |

## Function create_recipe_sql_session

```python
def create_recipe_sql_session(*, sql_log: bool | None=None, schema: str | None=None):
```

- **호출자:** `search_recipe.main`, CSV 등록 CLI와 스키마별 조회 경로
- **반환:** `타입 힌트 없음`. ``recipe.sql`` mapper를 등록한 공통 ``PostgresDbSession`` 을 만든다.
- **원본:** [database.py](../../../../recipe_recommender/database.py) (86행)

`sql_log`를 생략(None)하면 `configure_query_logging()` 결과(환경변수 `RECIPE_QUERY_LOG`, 기본 꺼짐)를 따르고, 켜져 있으면 `sql_log_mode="combined"`로 바인딩 값이 채워진 SQL을 터미널에 출력한다. 명시한 True/False가 우선한다(등록 CLI의 `--sql-log`).

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `sql_log` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `schema` | `str \| None` | PostgreSQL 대상 스키마 |

## Function recipe_connection

```python
@contextmanager
def recipe_connection() -> Iterator[object]:
```

- **호출자:** `search_recipe.main`, CSV 등록 CLI와 스키마별 조회 경로
- **반환:** `Iterator[object]`. 레시피 스키마를 search_path로 설정한 연결을 ``with`` 블록에 제공한다.
- **원본:** [database.py](../../../../recipe_recommender/database.py) (111행)

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
