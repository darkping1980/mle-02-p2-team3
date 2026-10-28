# neo4j_db_session 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `common.neo4j_db_session`
- **소스:** [common/neo4j_db_session.py](../../../../common/neo4j_db_session.py)
- **역할:** 외부에서 주입한 Neo4j 공식 드라이버로 Cypher를 실행하는 ``QuerySession`` 구현 모듈.
- **주요 호출자:** `RecipeGraphRepository`
- **정의:** 클래스 3개, 모듈 함수 14개

- **직접 의존:** `.query_logger`, `.query_session`

- **관련 API:** [query_logger](query_logger.md), [recipe_graph_repository](../recipe_recommender/recipe_graph_repository.md)

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [_NotCypherLiteral](#_notcypherliteral) | 예외 클래스 | 파라미터 값을 정확한 Cypher 리터럴로 표현할 수 없을 때 내부적으로 사용하는 예외. |
| [_CypherScanError](#function-_cypher_parameter_tokens) | 예외 클래스 | 로그용 스캐너가 Cypher 텍스트를 끝까지 해석하지 못했을 때(닫히지 않은 문자열·주석 등). |
| [Neo4jDbSession](#neo4jdbsession) | 클래스 | ``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다. |

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [_driver_types](#function-_driver_types) | `SimpleNamespace` | 로그 표시에 필요한 드라이버 값 타입을 지연 import해 반환한다. neo4j가 없으면 빈 tuple로 채운다. |
| [_cypher_name](#function-_cypher_name) | `str` | 식별자 규칙에 맞지 않는 이름을 백틱으로 감싼다. 예: ``a b`` → ```a b```. |
| [_cypher_string](#function-_cypher_string) | `str` | Python 문자열을 작은따옴표 Cypher 문자열 리터럴로 이스케이프한다(로그 표시용). |
| [_cypher_literal](#function-_cypher_literal) | `str` | 드라이버 파라미터 값을 ``:param`` 줄에 쓸 Cypher 표현식 문자열로 바꾼다. |
| [_cypher_parameter_tokens](#function-_cypher_parameter_tokens) | `list[tuple[int, int, str]]` | Cypher 어휘 규칙으로 실제 파라미터 토큰 ``$name`` 의 위치를 찾는다(로그 전용, 실행에는 쓰지 않음). |
| [_inline_literal](#function-_inline_literal) | `str` | 인라인 위치에 넣을 Cypher 리터럴. 연산자가 포함된 표현(음수, NaN·Infinity)은 괄호로 감싼다. |
| [render_cypher_inline](#function-render_cypher_inline) | `tuple[str \| None, str]` | 로그 출력용으로 ``$name`` 자리에 값 리터럴을 넣은 Cypher 한 덩어리를 만든다(실행에는 쓰지 않음). |
| [render_cypher_log](#function-render_cypher_log) | `str` | combined 로그 본문. 가능하면 인라인 Cypher, 아니면 기존 ``:param`` 줄 + 원문과 재현 제한 주석. |
| [render_cypher_params](#function-render_cypher_params) | `str` | 로그 출력용으로 ``query`` 앞에 Neo4j Browser의 ``:param`` 줄을 붙인 문자열을 만든다. |
| [format_graph_value](#function-format_graph_value) | `str` | 결과 표 로그용으로 그래프 값을 짧은 문자열로 만든다. 반환 데이터 자체는 바꾸지 않는다. |
| [_format_result_cell](#function-_format_result_cell) | `str` | 결과 표 셀 변환 함수. 최상위 문자열은 PostgreSQL 표와 같게 따옴표 없이 둔다. |
| [summary_counters](#function-summary_counters) | `dict[str, int]` | 드라이버 ``ResultSummary.counters`` 중 0이 아닌 정수 값만 dict로 반환한다. |
| [_format_counters](#function-_format_counters) | `str` | counter dict를 ``{nodes_created: 1, properties_set: 2}`` 형식 문자열로 만든다. |
| [_server_ms](#function-_server_ms) | `int \| None` | summary의 서버 측 시간 속성(ms)을 정수일 때만 반환하고, 없으면 ``None`` 을 반환한다. |

## _NotCypherLiteral

**예외 클래스.** 파라미터 값을 정확한 Cypher 리터럴로 표현할 수 없을 때 내부적으로 사용하는 예외.

- **정의:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (73행)
- **생성 위치:** 직접 생성 호출은 주요 진입 경로에서 확인되지 않음; 정의와 호출 코드를 참조한다.

### Constructor Summary

명시적 `__init__`가 없다. 상위 클래스 또는 Python 기본 생성자를 사용한다.

## Neo4jDbSession

**클래스.** ``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다.

- **정의:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (419행)
- **생성 위치:** `RecipeGraphRepository.__init__`이 만든다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `driver` | `타입 힌트 없음` | 생성자 475행에서 설정; ``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다. |
| `mapper_root` | `타입 힌트 없음` | 생성자 476행에서 설정; ``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다. |
| `database` | `타입 힌트 없음` | 생성자 477행에서 설정; ``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다. |
| `query_logger` | `타입 힌트 없음` | 생성자 478행에서 설정; ``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다. |
| `mappers` | `dict[str, str]` | 생성자 489행에서 설정; ``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다. |
| `mapper_paths` | `dict[str, Path]` | 생성자 490행에서 설정; ``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다. |
| `_active_session` | `타입 힌트 없음` | 생성자 491행에서 설정; ``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다. |
| `_active_transaction` | `타입 힌트 없음` | 생성자 492행에서 설정; ``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다. |
| `cypher_log_mode` | `str` | `@property`로 계산되는 읽기 속성; [cypher_log_mode 상세](#neo4jdbsession-cypher_log_mode-getter) 참조 |
| `result_log` | `bool` | `@property`로 계산되는 읽기 속성; [result_log 상세](#neo4jdbsession-result_log-getter) 참조 |
| `result_log_limit` | `int` | `@property`로 계산되는 읽기 속성; [result_log_limit 상세](#neo4jdbsession-result_log_limit-getter) 참조 |

### Constructor Summary

`def __init__(self, *, mapper_root: str | Path, driver=None, database: str | None=None, cypher_log_mode: str='combined', result_log: bool=False, result_log_limit: int=100, sensitive_log_keys: Collection[str] | None=DEFAULT_SENSITIVE_KEYS):` — 드라이버와 로그 설정을 보관하고 Cypher mapper를 등록한다.

생성·주입 경로: `RecipeGraphRepository.__init__`이 만든다.. 세부 매개변수와 처리 내용은 [Neo4jDbSession.__init__](#neo4jdbsession-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#neo4jdbsession-__init__) | `타입 힌트 없음` | 드라이버와 로그 설정을 보관하고 Cypher mapper를 등록한다. |
| [cypher_log_mode (getter)](#neo4jdbsession-cypher_log_mode-getter) | `str` | 현재 Cypher 상세 로그 모드(combined / separate / none). |
| [cypher_log_mode (setter)](#neo4jdbsession-cypher_log_mode-setter) | `None` | Cypher 로그 출력 방식을 QueryLogger에 위임한다. |
| [result_log (getter)](#neo4jdbsession-result_log-getter) | `bool` | 조회/실행 결과를 표 형태로 로그에 남길지 여부. |
| [result_log (setter)](#neo4jdbsession-result_log-setter) | `None` | 조회 결과 로깅 설정을 QueryLogger에 위임한다. |
| [result_log_limit (getter)](#neo4jdbsession-result_log_limit-getter) | `int` | 결과 표 로그에 표시할 최대 행 수. |
| [result_log_limit (setter)](#neo4jdbsession-result_log_limit-setter) | `None` | 로그에 표시할 조회 결과 건수 제한을 QueryLogger에 위임한다. |
| [register_mappers](#neo4jdbsession-register_mappers) | `dict[str, str]` | ``*.cypher`` mapper 파일에서 이름 붙은 쿼리 블록을 읽어 ``self.mappers`` 에 등록한다. |
| [_query](#neo4jdbsession-_query) | `str` | ``namespace.statement`` ID를 검증하고 등록된 Cypher 문자열을 반환한다. |
| [_require_driver](#neo4jdbsession-_require_driver) | `타입 힌트 없음` | 주입된 드라이버를 반환한다. 없으면 ``RuntimeError`` 를 낸다. |
| [_session_options](#neo4jdbsession-_session_options) | `dict[str, Any]` | ``driver.session(**옵션)`` 에 넘길 인자. database가 없으면 서버 기본 DB를 사용한다. |
| [_log_query](#neo4jdbsession-_log_query) | `None` | QUERY 로그를 출력한다. combined 모드의 렌더링 함수로 ``render_cypher_params`` 를 넘긴다. |
| [_consume](#neo4jdbsession-_consume) | `타입 힌트 없음` | ``runner`` (Session 또는 Transaction)로 Cypher를 한 번 실행하고 결과를 모두 읽는다. |
| [_run_and_consume](#neo4jdbsession-_run_and_consume) | `타입 힌트 없음` | statement를 한 번 실행하고 ``(컬럼, 레코드 list, summary)`` 를 반환한다. |
| [_log_done](#neo4jdbsession-_log_done) | `None` | ``RESULT`` / ``DONE`` 요약 줄(행 수, counters, 시간)을 출력한다. 값 변환 실패는 경고만 남긴다. |
| [select_list](#neo4jdbsession-select_list) | `list[dict[str, Any]]` | Neo4j 레코드를 dict 목록으로 반환한다. Node 등 드라이버 그래프 객체는 그대로 유지한다. |
| [select_one](#neo4jdbsession-select_one) | `dict[str, Any] \| None` | 첫 레코드를 반환하고, 결과가 없으면 ``None`` 을 반환한다(LIMIT를 자동 추가하지 않음). |
| [_execute](#neo4jdbsession-_execute) | `타입 힌트 없음` | ``execute()`` 공통 구현. ``(반환값, summary)`` 를 돌려준다. |
| [execute](#neo4jdbsession-execute) | `Any` | Cypher를 한 번 실행한다. 결과 컬럼이 있으면 레코드를, 없으면 드라이버 summary를 반환한다. |
| [execute_many](#neo4jdbsession-execute_many) | `list[Any]` | 같은 Cypher를 파라미터 묶음마다 반복 실행하며, 전체를 하나의 트랜잭션으로 처리한다. |
| [transaction](#neo4jdbsession-transaction) | `Iterator['Neo4jDbSession']` | Neo4j Session 하나와 Transaction 하나를 열고, 블록 종료 시 commit 또는 rollback한다. |
| [_rollback](#neo4jdbsession-_rollback) | `None` | rollback을 시도하고 결과를 로그로 남긴다. rollback 예외는 전파하지 않는다(원래 예외를 보존). |

### Neo4jDbSession __init__

```python
def __init__(self, *, mapper_root: str | Path, driver=None, database: str | None=None, cypher_log_mode: str='combined', result_log: bool=False, result_log_limit: int=100, sensitive_log_keys: Collection[str] | None=DEFAULT_SENSITIVE_KEYS):
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `타입 힌트 없음`. 드라이버와 로그 설정을 보관하고 Cypher mapper를 등록한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (459행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `mapper_root` | `str \| Path` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `driver` | `타입 힌트 없음` | Neo4j 드라이버 |
| `database` | `str \| None` | Neo4j 데이터베이스명 |
| `cypher_log_mode` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `result_log` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `result_log_limit` | `int` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `sensitive_log_keys` | `Collection[str] \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### Neo4jDbSession cypher_log_mode getter

```python
@property
def cypher_log_mode(self) -> str:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `str`. 현재 Cypher 상세 로그 모드(combined / separate / none).
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (502행)

### Neo4jDbSession cypher_log_mode setter

```python
@cypher_log_mode.setter
def cypher_log_mode(self, value: str) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. Cypher 로그 출력 방식을 QueryLogger에 위임한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (502행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `str` | 처리하거나 설정할 값 |

### Neo4jDbSession result_log getter

```python
@property
def result_log(self) -> bool:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `bool`. 조회/실행 결과를 표 형태로 로그에 남길지 여부.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (512행)

### Neo4jDbSession result_log setter

```python
@result_log.setter
def result_log(self, value: bool) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 조회 결과 로깅 설정을 QueryLogger에 위임한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (512행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `bool` | 처리하거나 설정할 값 |

### Neo4jDbSession result_log_limit getter

```python
@property
def result_log_limit(self) -> int:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `int`. 결과 표 로그에 표시할 최대 행 수.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (522행)

### Neo4jDbSession result_log_limit setter

```python
@result_log_limit.setter
def result_log_limit(self, value: int) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 로그에 표시할 조회 결과 건수 제한을 QueryLogger에 위임한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (522행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `int` | 처리하거나 설정할 값 |

### Neo4jDbSession register_mappers

```python
def register_mappers(self) -> dict[str, str]:
```

- **주요 호출자:** `Neo4jDbSession.__init__`
- **반환:** `dict[str, str]`. ``*.cypher`` mapper 파일에서 이름 붙은 쿼리 블록을 읽어 ``self.mappers`` 에 등록한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (526행)

**예외:** FileNotFoundError / NotADirectoryError: ``mapper_root`` 가 없거나 디렉터리가 아닌 경우.<br>    ValueError: 선언이 없는 파일, 잘못된 namespace, 빈 statement, 중복 statement가 있는 경우.

### Neo4jDbSession _query

```python
def _query(self, statement_id: str) -> str:
```

- **주요 호출자:** `Neo4jDbSession._run_and_consume`, `Neo4jDbSession.execute_many`
- **반환:** `str`. ``namespace.statement`` ID를 검증하고 등록된 Cypher 문자열을 반환한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (575행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |

**예외:** ValueError: 점이 정확히 하나가 아니거나 식별자 규칙에 맞지 않는 경우.<br>    LookupError: 등록되지 않은 statement인 경우(원래 KeyError는 ``__cause__`` 로 연결).

### Neo4jDbSession _require_driver

```python
def _require_driver(self):
```

- **주요 호출자:** `Neo4jDbSession._run_and_consume`, `Neo4jDbSession.execute_many`, `Neo4jDbSession.transaction`
- **반환:** `타입 힌트 없음`. 주입된 드라이버를 반환한다. 없으면 ``RuntimeError`` 를 낸다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (596행)

### Neo4jDbSession _session_options

```python
def _session_options(self) -> dict[str, Any]:
```

- **주요 호출자:** `Neo4jDbSession._run_and_consume`, `Neo4jDbSession.transaction`
- **반환:** `dict[str, Any]`. ``driver.session(**옵션)`` 에 넘길 인자. database가 없으면 서버 기본 DB를 사용한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (602행)

### Neo4jDbSession _log_query

```python
def _log_query(self, statement_id: str, query: str, parameters: Mapping[str, Any]) -> None:
```

- **주요 호출자:** `Neo4jDbSession._consume`
- **반환:** `None`. QUERY 로그를 출력한다. combined 모드의 렌더링 함수로 ``render_cypher_params`` 를 넘긴다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (606행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `query` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `parameters` | `Mapping[str, Any]` | 쿼리에 바인딩할 매개변수 |

### Neo4jDbSession _consume

```python
def _consume(self, runner, statement_id: str, query: str, bound_parameters: dict, log_query: bool, timings: dict):
```

- **주요 호출자:** `Neo4jDbSession._run_and_consume`
- **반환:** `타입 힌트 없음`. ``runner`` (Session 또는 Transaction)로 Cypher를 한 번 실행하고 결과를 모두 읽는다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (621행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `runner` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `query` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `bound_parameters` | `dict` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `log_query` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `timings` | `dict` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### Neo4jDbSession _run_and_consume

```python
def _run_and_consume(self, statement_id: str, parameters: Mapping[str, Any] | None=None, *, log_query: bool=True, timings: dict | None=None):
```

- **주요 호출자:** `Neo4jDbSession._execute`, `Neo4jDbSession.select_list`
- **반환:** `타입 힌트 없음`. statement를 한 번 실행하고 ``(컬럼, 레코드 list, summary)`` 를 반환한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (648행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `parameters` | `Mapping[str, Any] \| None` | 쿼리에 바인딩할 매개변수 |
| `log_query` | `bool` | False면 QUERY 로그를 생략한다(``execute_many()`` 의 행별 실행). |
| `timings` | `dict \| None` | 시간 측정값을 기록할 dict. 호출자가 넘기면 같은 dict에 채운다. |

### Neo4jDbSession _log_done

```python
def _log_done(self, event: str, statement_id: str, records: list, summary: Any, timings: dict, started: float) -> None:
```

- **주요 호출자:** `Neo4jDbSession._execute`, `Neo4jDbSession.select_list`
- **반환:** `None`. ``RESULT`` / ``DONE`` 요약 줄(행 수, counters, 시간)을 출력한다. 값 변환 실패는 경고만 남긴다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (679행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `event` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `records` | `list` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `summary` | `Any` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `timings` | `dict` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `started` | `float` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### Neo4jDbSession select_list

```python
def select_list(self, statement_id: str, parameters: Mapping[str, Any] | None=None) -> list[dict[str, Any]]:
```

- **주요 호출자:** `Neo4jDbSession.select_one`
- **반환:** `list[dict[str, Any]]`. Neo4j 레코드를 dict 목록으로 반환한다. Node 등 드라이버 그래프 객체는 그대로 유지한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (702행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `parameters` | `Mapping[str, Any] \| None` | 쿼리에 바인딩할 매개변수 |

**처리 흐름:** Named Cypher를 선택해 읽기 세션에서 실행하고 레코드를 dict 목록으로 반환한다.

**관련 API:** [query_logger](query_logger.md), [recipe_graph_repository](../recipe_recommender/recipe_graph_repository.md)

### Neo4jDbSession select_one

```python
def select_one(self, statement_id: str, parameters: Mapping[str, Any] | None=None) -> dict[str, Any] | None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict[str, Any] | None`. 첫 레코드를 반환하고, 결과가 없으면 ``None`` 을 반환한다(LIMIT를 자동 추가하지 않음).
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (718행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `parameters` | `Mapping[str, Any] \| None` | 쿼리에 바인딩할 매개변수 |

### Neo4jDbSession _execute

```python
def _execute(self, statement_id: str, parameters: Mapping[str, Any] | None, *, batch: bool):
```

- **주요 호출자:** `Neo4jDbSession.execute_many`, `Neo4jDbSession.execute`
- **반환:** `타입 힌트 없음`. ``execute()`` 공통 구현. ``(반환값, summary)`` 를 돌려준다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (723행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `parameters` | `Mapping[str, Any] \| None` | 쿼리에 바인딩할 매개변수 |
| `batch` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### Neo4jDbSession execute

```python
def execute(self, statement_id: str, parameters: Mapping[str, Any] | None=None) -> Any:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `Any`. Cypher를 한 번 실행한다. 결과 컬럼이 있으면 레코드를, 없으면 드라이버 summary를 반환한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (740행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `parameters` | `Mapping[str, Any] \| None` | 쿼리에 바인딩할 매개변수 |

**처리 흐름:** Named Cypher를 한 번 실행한다. 결과 컬럼이 있으면 레코드를, 없으면 summary를 반환한다.

**관련 API:** [query_logger](query_logger.md), [recipe_graph_repository](../recipe_recommender/recipe_graph_repository.md)

**부작용:** 호출 경로와 트랜잭션 조건에 따라 DB 상태를 변경한다. 상세 조건은 소스와 [실행 흐름](../../04_execution_flow.md)을 확인한다.

### Neo4jDbSession execute_many

```python
def execute_many(self, statement_id: str, parameters_list: Sequence[Mapping[str, Any]]) -> list[Any]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `list[Any]`. 같은 Cypher를 파라미터 묶음마다 반복 실행하며, 전체를 하나의 트랜잭션으로 처리한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (750행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `parameters_list` | `Sequence[Mapping[str, Any]]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

**처리 흐름:** 여러 바인딩 묶음에 같은 Cypher를 적용하되 하나의 Neo4j 트랜잭션으로 처리한다.

**관련 API:** [query_logger](query_logger.md), [recipe_graph_repository](../recipe_recommender/recipe_graph_repository.md)

**부작용:** 호출 경로와 트랜잭션 조건에 따라 DB 상태를 변경한다. 상세 조건은 소스와 [실행 흐름](../../04_execution_flow.md)을 확인한다.

### Neo4jDbSession transaction

```python
@contextmanager
def transaction(self) -> Iterator['Neo4jDbSession']:
```

- **주요 호출자:** `Neo4jDbSession.execute_many`
- **반환:** `Iterator['Neo4jDbSession']`. Neo4j Session 하나와 Transaction 하나를 열고, 블록 종료 시 commit 또는 rollback한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (802행)

**처리 흐름:** Neo4j Session과 Transaction을 열어 여러 Cypher 호출에 재사용하고 `with` 블록의 정상 종료/예외에 따라 commit/rollback한다.

**관련 API:** [query_logger](query_logger.md), [recipe_graph_repository](../recipe_recommender/recipe_graph_repository.md)

**예외:** RuntimeError: 이미 트랜잭션이 활성화된 상태에서 다시 호출한 경우(중첩 미지원).

### Neo4jDbSession _rollback

```python
def _rollback(self, transaction, *, after_commit_failure: bool=False) -> None:
```

- **주요 호출자:** `Neo4jDbSession.transaction`
- **반환:** `None`. rollback을 시도하고 결과를 로그로 남긴다. rollback 예외는 전파하지 않는다(원래 예외를 보존).
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (851행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `transaction` | `타입 힌트 없음` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `after_commit_failure` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _driver_types

```python
@lru_cache(maxsize=1)
def _driver_types() -> SimpleNamespace:
```

- **호출자:** `RecipeGraphRepository`
- **반환:** `SimpleNamespace`. 로그 표시에 필요한 드라이버 값 타입을 지연 import해 반환한다. neo4j가 없으면 빈 tuple로 채운다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (60행)

## Function _cypher_name

```python
def _cypher_name(key: Any) -> str:
```

- **호출자:** `RecipeGraphRepository`
- **반환:** `str`. 식별자 규칙에 맞지 않는 이름을 백틱으로 감싼다. 예: ``a b`` → ```a b```.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (77행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `key` | `Any` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _cypher_string

```python
def _cypher_string(text: str) -> str:
```

- **호출자:** `RecipeGraphRepository`
- **반환:** `str`. Python 문자열을 작은따옴표 Cypher 문자열 리터럴로 이스케이프한다(로그 표시용).
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (83행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `text` | `str` | 처리할 입력 문자열 |

## Function _cypher_literal

```python
def _cypher_literal(value: Any, vector_min_length: int) -> str:
```

- **호출자:** `RecipeGraphRepository`
- **반환:** `str`. 드라이버 파라미터 값을 ``:param`` 줄에 쓸 Cypher 표현식 문자열로 바꾼다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (109행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `Any` | 처리하거나 설정할 값 |
| `vector_min_length` | `int` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function render_cypher_params

```python
def render_cypher_params(query_logger: QueryLogger, query: str, parameters: Mapping[str, Any]) -> str:
```

- **호출자:** `RecipeGraphRepository`
- **반환:** `str`. 로그 출력용으로 ``query`` 앞에 Neo4j Browser의 ``:param`` 줄을 붙인 문자열을 만든다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (171행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `query_logger` | `QueryLogger` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `query` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `parameters` | `Mapping[str, Any]` | 쿼리에 바인딩할 매개변수 |

## Function _cypher_parameter_tokens

```python
def _cypher_parameter_tokens(query: str) -> list[tuple[int, int, str]]:
```

- **호출자:** `render_cypher_inline`
- **반환:** `list[tuple[int, int, str]]`. `(시작, 끝, 이름)` 목록.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (204행)

**처리 흐름:** 정규식 치환이 아니라 앞에서부터 읽으며 작은따옴표·큰따옴표 문자열(역슬래시 이스케이프), 백틱 식별자(백틱 두 개 = 백틱 한 글자), `//` 줄 주석, `/* */` 블록 주석을 건너뛴다. 그 밖의 `$`만 파라미터로 보고 식별자 문자를 끝까지 읽어 `$id`와 `$id2`를 구분한다. `$`이름``, `$0`도 처리하고, `$(` 처럼 이름이 이어지지 않는 `$`는 파라미터가 아니다.

**예외:** `_CypherScanError`: 문자열·백틱·블록 주석이 닫히지 않은 경우.

## Function _inline_literal

```python
def _inline_literal(value: Any, vector_min_length: int) -> str:
```

- **호출자:** `render_cypher_inline`
- **반환:** `str`. `_cypher_literal` 결과. 음수·NaN·Infinity처럼 연산자가 든 표현만 괄호로 감싼다(map은 패턴 속성 자리 `(n $props)`에서 괄호식이 허용되지 않아 감싸지 않음).
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (277행)

## Function render_cypher_inline

```python
def render_cypher_inline(query_logger: QueryLogger, query: str, parameters: Mapping[str, Any]) -> tuple[str | None, str]:
```

- **호출자:** `render_cypher_log`
- **반환:** `tuple[str | None, str]`. (인라인 Cypher 또는 None, 대체 사유).
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (287행)

**대체(None) 조건:** 텍스트를 끝까지 해석하지 못함, 쿼리가 쓰는 파라미터가 없음, 정확한 리터럴이 없는 값(벡터 미리보기·bytes·알 수 없는 객체), 민감 키 마스킹 적용(마스킹 값으로는 재현할 수 없음). 쿼리에 파라미터 토큰이 없으면 원문 그대로.

## Function render_cypher_log

```python
def render_cypher_log(query_logger: QueryLogger, query: str, parameters: Mapping[str, Any]) -> str:
```

- **호출자:** `Neo4jDbSession._log_query`(combined 모드의 `render_combined`)
- **반환:** `str`. 인라인이면 `// inline parameter values for log only ...` 주석 + 값이 들어간 Cypher. 대체면 `// NOT REPRODUCIBLE AS-IS: masked ...`(마스킹) 또는 `// inline rendering skipped (사유)` 주석 + 기존 `render_cypher_params` 결과.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (325행)

로그 문자열만 만든다. 실행은 `_consume()`의 `runner.run(query, bound_parameters)` 바인딩 그대로다.

## Function format_graph_value

```python
def format_graph_value(value: Any) -> str:
```

- **호출자:** `RecipeGraphRepository`
- **반환:** `str`. 결과 표 로그용으로 그래프 값을 짧은 문자열로 만든다. 반환 데이터 자체는 바꾸지 않는다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (337행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `Any` | 처리하거나 설정할 값 |

## Function _format_result_cell

```python
def _format_result_cell(value: Any) -> str:
```

- **호출자:** `RecipeGraphRepository`
- **반환:** `str`. 결과 표 셀 변환 함수. 최상위 문자열은 PostgreSQL 표와 같게 따옴표 없이 둔다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (380행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `Any` | 처리하거나 설정할 값 |

## Function summary_counters

```python
def summary_counters(summary: Any) -> dict[str, int]:
```

- **호출자:** `RecipeGraphRepository`
- **반환:** `dict[str, int]`. 드라이버 ``ResultSummary.counters`` 중 0이 아닌 정수 값만 dict로 반환한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (385행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `summary` | `Any` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _format_counters

```python
def _format_counters(counters: Mapping[str, int]) -> str:
```

- **호출자:** `RecipeGraphRepository`
- **반환:** `str`. counter dict를 ``{nodes_created: 1, properties_set: 2}`` 형식 문자열로 만든다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (408행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `counters` | `Mapping[str, int]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _server_ms

```python
def _server_ms(summary: Any, name: str) -> int | None:
```

- **호출자:** `RecipeGraphRepository`
- **반환:** `int | None`. summary의 서버 측 시간 속성(ms)을 정수일 때만 반환하고, 없으면 ``None`` 을 반환한다.
- **원본:** [neo4j_db_session.py](../../../../common/neo4j_db_session.py) (413행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `summary` | `Any` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `name` | `str` | 조회할 이름 또는 식별자 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
