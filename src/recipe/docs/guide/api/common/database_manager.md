# database_manager 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `common.database_manager`
- **소스:** [common/database_manager.py](../../../../common/database_manager.py)
- **역할:** PostgreSQL connection pool 관리 모듈.
- **주요 호출자:** `recipe_recommender.database`와 `RecipeGraphSourceRepository`
- **정의:** 클래스 1개, 모듈 함수 3개

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [DatabaseManager](#databasemanager) | 클래스 | DatabaseManager는 psycopg connection pool을 관리하고 대여한 연결을 제공한다. |

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [_configure_connection](#function-_configure_connection) | `None` | 새 physical connection에 pgvector 어댑터를 등록하고 idle 상태로 둔다. |
| [snake_to_camel](#function-snake_to_camel) | `str` | 밑줄로 구분된 컬럼명을 camelCase 문자열로 변환한다. |
| [camel_dict_row](#function-camel_dict_row) | `RowMaker[dict[str, Any]]` | psycopg 행을 camelCase 키를 가진 dict로 만드는 row factory를 반환한다. |

## DatabaseManager

**클래스.** DatabaseManager는 psycopg connection pool을 관리하고 대여한 연결을 제공한다.

- **정의:** [database_manager.py](../../../../common/database_manager.py) (107행)
- **생성 위치:** `recipe_recommender.database`와 `RecipeGraphSourceRepository`가 사용한다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `Any` | 마지막으로 생성한 DB 연결 |
| `_pools` | `dict[bool, ConnectionPool]` | 생성자 142행에서 설정; DatabaseManager는 psycopg connection pool을 관리하고 대여한 연결을 제공한다. |
| `_pool_lock` | `타입 힌트 없음` | 생성자 143행에서 설정; DatabaseManager는 psycopg connection pool을 관리하고 대여한 연결을 제공한다. |

### Constructor Summary

`def __init__(self, connection: Any=None) -> None:` — ``.env`` 를 읽고 빈 pool 저장소를 준비한다. 이 시점에는 DB에 접속하지 않는다.

생성·주입 경로: `recipe_recommender.database`와 `RecipeGraphSourceRepository`가 사용한다.. 세부 매개변수와 처리 내용은 [DatabaseManager.__init__](#databasemanager-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#databasemanager-__init__) | `None` | ``.env`` 를 읽고 빈 pool 저장소를 준비한다. 이 시점에는 DB에 접속하지 않는다. |
| [_get_pool](#databasemanager-_get_pool) | `ConnectionPool` | 요청한 row_factory에 맞는 pool을 처음 만들고 이후 계속 재사용한다. |
| [warmup](#databasemanager-warmup) | `None` | 지정 row_factory pool과 최소 연결을 미리 준비한다. 반복 호출해도 안전하다. |
| [connect](#databasemanager-connect) | `타입 힌트 없음` | 요청한 row_factory pool에서 connection을 대여하고 종료 시 반환한다. |
| [close](#databasemanager-close) | `None` | 앱 종료 등 명시적인 정리 시 모든 pool을 닫는다. |

### DatabaseManager __init__

```python
def __init__(self, connection: Any=None) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. ``.env`` 를 읽고 빈 pool 저장소를 준비한다. 이 시점에는 DB에 접속하지 않는다.
- **원본:** [database_manager.py](../../../../common/database_manager.py) (137행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `Any` | 현재 DB 연결 |

### DatabaseManager _get_pool

```python
def _get_pool(self, camel_case_keys: bool) -> ConnectionPool:
```

- **주요 호출자:** `DatabaseManager.connect`, `DatabaseManager.warmup`
- **반환:** `ConnectionPool`. 요청한 row_factory에 맞는 pool을 처음 만들고 이후 계속 재사용한다.
- **원본:** [database_manager.py](../../../../common/database_manager.py) (146행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `camel_case_keys` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

**예외:** ValueError: ``DB_POOL_MIN_SIZE`` / ``DB_POOL_MAX_SIZE`` 값의 범위가 잘못된 경우.<br>    Exception: pool 초기 연결 준비(``pool.wait()``)가 실패한 경우. 실패한 pool은 보관하지 않는다.

### DatabaseManager warmup

```python
def warmup(self, camel_case_keys: bool=True) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 지정 row_factory pool과 최소 연결을 미리 준비한다. 반복 호출해도 안전하다.
- **원본:** [database_manager.py](../../../../common/database_manager.py) (193행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `camel_case_keys` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### DatabaseManager connect

```python
@contextmanager
def connect(self, camel_case_keys: bool=True):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 요청한 row_factory pool에서 connection을 대여하고 종료 시 반환한다.
- **원본:** [database_manager.py](../../../../common/database_manager.py) (212행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `camel_case_keys` | `bool` | True면 결과 key를 camelCase로, False면 컬럼명 그대로 받는 pool을 사용한다. |

### DatabaseManager close

```python
def close(self) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 앱 종료 등 명시적인 정리 시 모든 pool을 닫는다.
- **원본:** [database_manager.py](../../../../common/database_manager.py) (229행)

## Function _configure_connection

```python
def _configure_connection(connection: psycopg.Connection) -> None:
```

- **호출자:** `recipe_recommender.database`와 `RecipeGraphSourceRepository`
- **반환:** `None`. 새 physical connection에 pgvector 어댑터를 등록하고 idle 상태로 둔다.
- **원본:** [database_manager.py](../../../../common/database_manager.py) (24행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `psycopg.Connection` | 현재 DB 연결 |

## Function snake_to_camel

```python
def snake_to_camel(name: str) -> str:
```

- **호출자:** `recipe_recommender.database`와 `RecipeGraphSourceRepository`
- **반환:** `str`. 밑줄로 구분된 컬럼명을 camelCase 문자열로 변환한다.
- **원본:** [database_manager.py](../../../../common/database_manager.py) (33행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `name` | `str` | 변환할 컬럼명 또는 SQL 결과 컬럼의 별칭. |

## Function camel_dict_row

```python
def camel_dict_row(cursor: psycopg.Cursor[Any]) -> RowMaker[dict[str, Any]]:
```

- **호출자:** `recipe_recommender.database`와 `RecipeGraphSourceRepository`
- **반환:** `RowMaker[dict[str, Any]]`. psycopg 행을 camelCase 키를 가진 dict로 만드는 row factory를 반환한다.
- **원본:** [database_manager.py](../../../../common/database_manager.py) (60행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `cursor` | `psycopg.Cursor[Any]` | ``description`` 에 결과 컬럼 정보가 들어 있는 psycopg 커서. |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
