# postgres_db_session 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `common.postgres_db_session`
- **소스:** [common/postgres_db_session.py](../../../../common/postgres_db_session.py)
- **역할:** PostgreSQL용 ``QuerySession`` 구현 모듈.
- **주요 호출자:** `recipe_recommender.database.create_recipe_sql_session`
- **정의:** 클래스 1개, 모듈 함수 0개

- **직접 의존:** `.database_manager`, `.query_logger`, `.query_session`

- **관련 API:** [database_manager](database_manager.md), [query_logger](query_logger.md)

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [PostgresDbSession](#postgresdbsession) | 클래스 | SQL mapper를 등록하고 statement ID로 동기식 쿼리를 실행한다. |

## PostgresDbSession

**클래스.** SQL mapper를 등록하고 statement ID로 동기식 쿼리를 실행한다.

- **정의:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (42행)
- **생성 위치:** `recipe_recommender.database.create_recipe_sql_session`이 만든다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `SQL_LOG_MODES` | `ClassVar[tuple[str, ...]]` | 허용하는 SQL 로그 모드 |
| `RESULT_LOG_COLUMN_WIDTH` | `ClassVar[int]` | 표의 컬럼별 최대 표시 폭 |
| `VECTOR_LOG_PREVIEW_COUNT` | `ClassVar[int]` | 로그에 표시할 벡터 앞부분 값 개수 |
| `VECTOR_LOG_SEQUENCE_MIN_LENGTH` | `ClassVar[int]` | 숫자 시퀀스를 벡터로 취급할 최소 길이 |
| `camel_case_keys` | `bool` | 조회 결과 camelCase 변환 여부 |
| `database_manager` | `DatabaseManager` | DB 연결 관리자 |
| `query_logger` | `QueryLogger` | SQL/결과 로그 설정과 출력 (result_log 등은 property로 위임) |
| `mappers` | `dict[str, Queries]` | namespace별 SQL mapper |
| `mapper_paths` | `dict[str, Path]` | namespace별 SQL 파일 경로 |
| `_active_connection` | `psycopg.Connection \| None` | 트랜잭션 중 재사용할 연결 |
| `_pg_engine` | `'PGEngine \| None'` | PGVector 엔진 지연 생성 캐시 |
| `mapper_root` | `타입 힌트 없음` | 생성자 144행에서 설정; SQL mapper를 등록하고 statement ID로 동기식 쿼리를 실행한다. |
| `sql_log_mode` | `str` | `@property`로 계산되는 읽기 속성; [sql_log_mode 상세](#postgresdbsession-sql_log_mode-getter) 참조 |
| `result_log` | `bool` | `@property`로 계산되는 읽기 속성; [result_log 상세](#postgresdbsession-result_log-getter) 참조 |
| `result_log_limit` | `int` | `@property`로 계산되는 읽기 속성; [result_log_limit 상세](#postgresdbsession-result_log_limit-getter) 참조 |

### Constructor Summary

`def __init__(self, camel_case_keys: bool=True, database_manager: DatabaseManager | None=None, sql_log_mode: str='combined', result_log: bool=False, result_log_limit: int=100, *, mapper_root: str | Path, sensitive_log_keys: Collection[str] | None=None) -> None:` — 연결 관리자와 SQL/결과 로그 옵션을 설정하고 mapper를 등록한다.

생성·주입 경로: `recipe_recommender.database.create_recipe_sql_session`이 만든다.. 세부 매개변수와 처리 내용은 [PostgresDbSession.__init__](#postgresdbsession-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#postgresdbsession-__init__) | `None` | 연결 관리자와 SQL/결과 로그 옵션을 설정하고 mapper를 등록한다. |
| [sql_log_mode (getter)](#postgresdbsession-sql_log_mode-getter) | `str` | 현재 SQL 상세 로그 모드(combined / separate / none). |
| [sql_log_mode (setter)](#postgresdbsession-sql_log_mode-setter) | `None` | SQL 로그 출력 방식을 QueryLogger에 위임한다. |
| [result_log (getter)](#postgresdbsession-result_log-getter) | `bool` | 조회/실행 결과를 표 형태로 로그에 남길지 여부. |
| [result_log (setter)](#postgresdbsession-result_log-setter) | `None` | 조회 결과 로깅 설정을 QueryLogger에 위임한다. |
| [result_log_limit (getter)](#postgresdbsession-result_log_limit-getter) | `int` | 결과 표 로그에 표시할 최대 행 수. 0 이상의 정수만 허용한다. |
| [result_log_limit (setter)](#postgresdbsession-result_log_limit-setter) | `None` | 로그에 표시할 조회 결과 건수 제한을 QueryLogger에 위임한다. |
| [_log_query](#postgresdbsession-_log_query) | `None` | 실행과 별개로 SQL 상세 로그를 출력한다. 형식과 모드 판단은 QueryLogger가 맡는다. |
| [_render_notes](#postgresdbsession-_render_notes) | `list[str]` | mogrify 결과가 실제 실행 값과 달라지는 경우의 ``--`` 주석 줄 목록(로그 전용). |
| [_contains_vector](#postgresdbsession-_contains_vector) | `bool` | 로그에서 미리보기로 바뀌는 값(pgvector 타입, 긴 숫자 list/tuple)이 들어 있는지 재귀로 확인한다. |
| [register_mappers](#postgresdbsession-register_mappers) | `Self` | 검색 범위의 SQL mapper 파일을 현재 세션에 등록한다. |
| [_query](#postgresdbsession-_query) | `타입 힌트 없음` | ``namespace.statement`` ID에 해당하는 aiosql 함수를 찾는다. |
| [_connection](#postgresdbsession-_connection) | `Generator[psycopg.Connection]` | 트랜잭션 중이면 그 연결을, 아니면 pool에서 새로 빌린 연결을 with 블록에 제공한다. |
| [transaction](#postgresdbsession-transaction) | `Generator[Self]` | 여러 mapper 호출을 하나의 PostgreSQL 트랜잭션으로 묶는다. |
| [select_list](#postgresdbsession-select_list) | `list[dict]` | mapper SELECT를 실행하고 모든 결과 행을 dict 목록으로 반환한다. |
| [select_one](#postgresdbsession-select_one) | `dict \| None` | mapper 조회 결과의 첫 행 또는 ``None`` 을 반환한다. |
| [execute](#postgresdbsession-execute) | `타입 힌트 없음` | mapper의 변경 SQL 또는 기타 SQL 명령을 실행한다. |
| [execute_many](#postgresdbsession-execute_many) | `타입 힌트 없음` | 같은 변경 SQL을 여러 파라미터에 적용해 배치 실행한다. |
| [get_pg_engine](#postgresdbsession-get_pg_engine) | `'PGEngine'` | ``DB_URL`` 로 PGVector용 ``PGEngine`` 을 지연 생성하고 재사용한다. |

### PostgresDbSession __init__

```python
def __init__(self, camel_case_keys: bool=True, database_manager: DatabaseManager | None=None, sql_log_mode: str='combined', result_log: bool=False, result_log_limit: int=100, *, mapper_root: str | Path, sensitive_log_keys: Collection[str] | None=None) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 연결 관리자와 SQL/결과 로그 옵션을 설정하고 mapper를 등록한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (114행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `camel_case_keys` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `database_manager` | `DatabaseManager \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `sql_log_mode` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `result_log` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `result_log_limit` | `int` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `mapper_root` | `str \| Path` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `sensitive_log_keys` | `Collection[str] \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

**예외:** ValueError: 로그 설정 값이 잘못되었거나 mapper namespace/statement가 중복된 경우.<br>    FileNotFoundError: ``mapper_root`` 가 없거나 디렉터리가 아닌 경우.

### PostgresDbSession sql_log_mode getter

```python
@property
def sql_log_mode(self) -> str:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `str`. 현재 SQL 상세 로그 모드(combined / separate / none).
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (180행)

### PostgresDbSession sql_log_mode setter

```python
@sql_log_mode.setter
def sql_log_mode(self, value: str) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. SQL 로그 출력 방식을 QueryLogger에 위임한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (180행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `str` | 처리하거나 설정할 값 |

### PostgresDbSession result_log getter

```python
@property
def result_log(self) -> bool:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `bool`. 조회/실행 결과를 표 형태로 로그에 남길지 여부.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (193행)

### PostgresDbSession result_log setter

```python
@result_log.setter
def result_log(self, value: bool) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 조회 결과 로깅 설정을 QueryLogger에 위임한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (193행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `bool` | 처리하거나 설정할 값 |

### PostgresDbSession result_log_limit getter

```python
@property
def result_log_limit(self) -> int:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `int`. 결과 표 로그에 표시할 최대 행 수. 0 이상의 정수만 허용한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (203행)

### PostgresDbSession result_log_limit setter

```python
@result_log_limit.setter
def result_log_limit(self, value: int) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 로그에 표시할 조회 결과 건수 제한을 QueryLogger에 위임한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (203행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `int` | 처리하거나 설정할 값 |

### PostgresDbSession _render_notes

```python
def _render_notes(self, parameters, full_vector_sql: bool) -> list[str]:
```

- **주요 호출자:** `_log_query`의 `render_sql`(combined 렌더링 직후)
- **반환:** `list[str]`. 마스킹이 적용되면 `-- NOT REPRODUCIBLE AS-IS: masked values ...`, `execute()` 경로(`full_vector_sql=False`)에서 벡터가 미리보기로 렌더링되면 `-- NOT REPRODUCIBLE AS-IS: vector values ...`. 렌더링 SQL 위에 붙는다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (248행)

### PostgresDbSession _contains_vector

```python
def _contains_vector(self, value) -> bool:
```

- **주요 호출자:** `_render_notes`
- **반환:** `bool`. `vector_types` 인스턴스나 `VECTOR_LOG_SEQUENCE_MIN_LENGTH` 이상의 숫자 list/tuple이 dict·list 안 어디든 있으면 True.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (262행)

### PostgresDbSession _log_query

```python
def _log_query(self, statement_id: str, sql: str, parameters, connection: psycopg.Connection, *, force: bool=False, full_vector_sql: bool=False) -> None:
```

- **주요 호출자:** `PostgresDbSession.execute`, `PostgresDbSession.select_list`
- **반환:** `None`. 실행과 별개로 SQL 상세 로그를 출력한다. 형식과 모드 판단은 QueryLogger가 맡는다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (210행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | 로그에 표시할 ``namespace.statement`` ID. |
| `sql` | `str` | aiosql이 변환한 SQL(``%(name)s`` 형식 placeholder). |
| `parameters` | `타입 힌트 없음` | 실제 실행에 쓰는 원본 파라미터 dict. |
| `connection` | `psycopg.Connection` | ``mogrify()`` 렌더링에 사용할 현재 연결. 이 메서드는 SQL을 실행하지 않는다. |
| `force` | `bool` | True면 ``sql_log_mode="none"`` 이어도 combined 형식으로 출력한다(``execute()`` 기존 정책). |
| `full_vector_sql` | `bool` | True면 QUERY 본문에 벡터 전체를 렌더링한다(``select_list()`` 전용). |

### PostgresDbSession register_mappers

```python
def register_mappers(self) -> Self:
```

- **주요 호출자:** `PostgresDbSession.__init__`
- **반환:** `Self`. 검색 범위의 SQL mapper 파일을 현재 세션에 등록한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (277행)

**예외:** ValueError: namespace가 중복되거나 SQLLoadException이 발생한 경우.<br>        오류 메시지에 관련 SQL 파일 경로를 포함한다.

### PostgresDbSession _query

```python
def _query(self, statement_id: str):
```

- **주요 호출자:** `PostgresDbSession.execute_many`, `PostgresDbSession.execute`, `PostgresDbSession.select_list`
- **반환:** `타입 힌트 없음`. ``namespace.statement`` ID에 해당하는 aiosql 함수를 찾는다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (341행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | 예: ``"document.select_documents"``. |

**예외:** ValueError: ID 형식이 잘못된 경우.<br>    LookupError: namespace 또는 statement가 없는 경우.

### PostgresDbSession _connection

```python
@contextmanager
def _connection(self) -> Generator[psycopg.Connection]:
```

- **주요 호출자:** `PostgresDbSession.execute_many`, `PostgresDbSession.execute`, `PostgresDbSession.select_list`
- **반환:** `Generator[psycopg.Connection]`. 트랜잭션 중이면 그 연결을, 아니면 pool에서 새로 빌린 연결을 with 블록에 제공한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (393행)

### PostgresDbSession transaction

```python
@contextmanager
def transaction(self) -> Generator[Self]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `Generator[Self]`. 여러 mapper 호출을 하나의 PostgreSQL 트랜잭션으로 묶는다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (420행)

**처리 흐름:** `with` 블록에 같은 연결을 재사용하고 정상 종료 시 commit, 예외 시 rollback한다. 연결은 블록을 빠져나오며 풀에 반환한다.

**관련 API:** [database_manager](database_manager.md), [query_logger](query_logger.md)

**예외:** RuntimeError: 같은 세션에서 이미 트랜잭션이 활성화된 경우.<br>    BaseException: 블록에서 발생한 예외를 rollback 후 다시 전파한다.

### PostgresDbSession select_list

```python
def select_list(self, statement_id: str, parameters=None) -> list[dict]:
```

- **주요 호출자:** `PostgresDbSession.select_one`
- **반환:** `list[dict]`. mapper SELECT를 실행하고 모든 결과 행을 dict 목록으로 반환한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (486행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `parameters` | `타입 힌트 없음` | 쿼리에 바인딩할 매개변수 |

**처리 흐름:** Named SQL을 mapper에서 찾고 현재 트랜잭션 연결 또는 독립 연결로 실행한 뒤 모든 행을 dict 목록으로 바꾼다.

**관련 API:** [database_manager](database_manager.md), [query_logger](query_logger.md)

### PostgresDbSession select_one

```python
def select_one(self, statement_id: str, parameters=None) -> dict | None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict | None`. mapper 조회 결과의 첫 행 또는 ``None`` 을 반환한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (534행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | ``namespace.statement`` 형식의 mapper ID. |
| `parameters` | `타입 힌트 없음` | SQL에 전달할 이름 있는 파라미터의 매핑. ``None`` 이면 |

**예외:** ValueError: statement ID 형식이 잘못된 경우.<br>    LookupError: namespace 또는 statement가 없는 경우.<br>    Exception: 연결 또는 SQL 실행 중 발생한 예외를 전파한다.

### PostgresDbSession execute

```python
def execute(self, statement_id: str, parameters=None):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. mapper의 변경 SQL 또는 기타 SQL 명령을 실행한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (570행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | ``namespace.statement`` 형식의 mapper ID. |
| `parameters` | `타입 힌트 없음` | SQL에 전달할 이름 있는 파라미터의 매핑. ``None`` 이면 |

**처리 흐름:** Named SQL을 실행하고 트랜잭션 범위와 로그 설정에 따라 결과·변경 건수를 처리한다.

**관련 API:** [database_manager](database_manager.md), [query_logger](query_logger.md)

**예외:** ValueError: statement ID 형식이 잘못된 경우.<br>    LookupError: namespace 또는 statement가 없는 경우.<br>    Exception: 연결 또는 SQL 실행 중 발생한 예외를 전파한다.

**부작용:** 호출 경로와 트랜잭션 조건에 따라 DB 상태를 변경한다. 상세 조건은 소스와 [실행 흐름](../../04_execution_flow.md)을 확인한다.

### PostgresDbSession execute_many

```python
def execute_many(self, statement_id: str, parameters_list: list[dict]):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 같은 변경 SQL을 여러 파라미터에 적용해 배치 실행한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (628행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | ``namespace.statement`` 형식의 mapper ID. |
| `parameters_list` | `list[dict]` | SQL의 이름 있는 파라미터에 대응하는 dict 목록. |

**처리 흐름:** 동일 Named SQL과 매개변수 목록을 배치로 실행한다. 호출자는 전체 작업의 트랜잭션 경계를 확인해야 한다.

**관련 API:** [database_manager](database_manager.md), [query_logger](query_logger.md)

**예외:** ValueError: statement ID 형식이 잘못된 경우.<br>    LookupError: namespace 또는 statement가 없는 경우.<br>    Exception: 연결 또는 배치 SQL 실행 중 발생한 예외를 전파한다.

**부작용:** 호출 경로와 트랜잭션 조건에 따라 DB 상태를 변경한다. 상세 조건은 소스와 [실행 흐름](../../04_execution_flow.md)을 확인한다.

### PostgresDbSession get_pg_engine

```python
def get_pg_engine(self) -> 'PGEngine':
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `'PGEngine'`. ``DB_URL`` 로 PGVector용 ``PGEngine`` 을 지연 생성하고 재사용한다.
- **원본:** [postgres_db_session.py](../../../../common/postgres_db_session.py) (729행)

**예외:** ValueError: ``DB_URL`` 환경변수가 비어 있는 경우.<br>    ModuleNotFoundError: ``langchain-postgres`` 가 설치되지 않은 경우.

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
