# query_logger 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `common.query_logger`
- **소스:** [common/query_logger.py](../../../../common/query_logger.py)
- **역할:** PostgreSQL / Neo4j 세션이 함께 쓰는 쿼리 로그 포매터.
- **주요 호출자:** `PostgresDbSession`, `Neo4jDbSession`
- **정의:** 클래스 1개, 모듈 함수 2개

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [QueryLogger](#querylogger) | 클래스 | 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [_normalize_key](#function-_normalize_key) | `str` | 민감 키 비교용으로 소문자화하고 영숫자만 남긴다. 예: ``"DB_Password"`` → ``"dbpassword"``. |
| [is_numeric_sequence](#function-is_numeric_sequence) | `bool` | bool을 제외한 int/float만 담긴 긴 list/tuple인지 확인한다 (벡터 판정 기준). |

## QueryLogger

**클래스.** 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다.

- **정의:** [query_logger.py](../../../../common/query_logger.py) (56행)
- **생성 위치:** 직접 생성 호출은 주요 진입 경로에서 확인되지 않음; 정의와 호출 코드를 참조한다.

### Field Summary

| 속성 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `LOG_MODES` | `ClassVar[tuple[str, ...]]` | 허용하는 로그 모드 |
| `RESULT_LOG_COLUMN_WIDTH` | `ClassVar[int]` | 표의 컬럼별 최대 표시 폭 |
| `VECTOR_LOG_PREVIEW_COUNT` | `ClassVar[int]` | 로그에 표시할 벡터 앞부분 값 개수 |
| `VECTOR_LOG_SEQUENCE_MIN_LENGTH` | `ClassVar[int]` | 숫자 시퀀스를 벡터로 취급할 최소 길이 |
| `BATCH_LOG_LIMIT` | `ClassVar[int]` | 배치 로그에 표시할 최대 파라미터 건수 |
| `DEFAULT_SENSITIVE_KEYS` | `ClassVar[tuple[str, ...]]` | 권장 마스킹 키 목록 |
| `logger` | `타입 힌트 없음` | 생성자 106행에서 설정; 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |
| `mode_option_name` | `타입 힌트 없음` | 생성자 107행에서 설정; 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |
| `query_label` | `타입 힌트 없음` | 생성자 108행에서 설정; 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |
| `vector_types` | `타입 힌트 없음` | 생성자 109행에서 설정; 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |
| `value_formatter` | `타입 힌트 없음` | 생성자 110행에서 설정; 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |
| `combined_params_line` | `타입 힌트 없음` | 생성자 111행에서 설정; 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |
| `sensitive_keys` | `타입 힌트 없음` | 생성자 112행에서 설정; 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |
| `log_mode` | `타입 힌트 없음` | 생성자 113행에서 설정; 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |
| `result_log_limit` | `타입 힌트 없음` | 생성자 114행에서 설정; 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |
| `result_log` | `타입 힌트 없음` | 생성자 115행에서 설정; 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |
| `log_mode` | `str` | `@property`로 계산되는 읽기 속성; [log_mode 상세](#querylogger-log_mode-getter) 참조 |
| `result_log_limit` | `int` | `@property`로 계산되는 읽기 속성; [result_log_limit 상세](#querylogger-result_log_limit-getter) 참조 |
| `sensitive_keys` | `tuple[str, ...]` | `@property`로 계산되는 읽기 속성; [sensitive_keys 상세](#querylogger-sensitive_keys-getter) 참조 |

### Constructor Summary

`def __init__(self, logger: logging.Logger, *, log_mode: str='combined', result_log: bool=False, result_log_limit: int=100, mode_option_name: str='log_mode', query_label: str='SQL', vector_types: tuple[type, ...]=(), sensitive_keys: Collection[str] | None=None, value_formatter: Callable[[Any], str] | None=None, combined_params_line: bool=True) -> None:` — 로그 설정을 검증해 보관한다. 잘못된 ``log_mode`` / ``result_log_limit`` 은 ``ValueError``.

생성·주입 경로: `PostgresDbSession`, `Neo4jDbSession`. 세부 매개변수와 처리 내용은 [QueryLogger.__init__](#querylogger-__init__)을 참조한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [__init__](#querylogger-__init__) | `None` | 로그 설정을 검증해 보관한다. 잘못된 ``log_mode`` / ``result_log_limit`` 은 ``ValueError``. |
| [log_mode (getter)](#querylogger-log_mode-getter) | `str` | 현재 쿼리 로그 모드. |
| [log_mode (setter)](#querylogger-log_mode-setter) | `None` | 쿼리 로그 출력 모드를 읽거나 검증해 설정한다. |
| [result_log_limit (getter)](#querylogger-result_log_limit-getter) | `int` | 결과 표에 표시할 최대 행 수. |
| [result_log_limit (setter)](#querylogger-result_log_limit-setter) | `None` | 결과 로그의 최대 행 수를 읽거나 검증해 설정한다. |
| [sensitive_keys (getter)](#querylogger-sensitive_keys-getter) | `tuple[str, ...]` | 마스킹할 키 이름 목록(설정한 원래 표기). |
| [sensitive_keys (setter)](#querylogger-sensitive_keys-setter) | `None` | 로그에서 숨길 매개변수 키 목록을 읽거나 설정한다. |
| [enabled](#querylogger-enabled) | `bool` | 상세 로그가 출력되는 레벨인지 확인한다. 꺼져 있으면 렌더링 비용을 쓰지 않는다. |
| [is_sensitive_key](#querylogger-is_sensitive_key) | `bool` | 키가 민감 키 목록과 완전 일치하거나, 6자 이상 항목으로 끝나면 True를 반환한다. |
| [format_vector_preview](#querylogger-format_vector_preview) | `str` | 벡터 앞부분만 표시할 로그 문자열을 만든다. |
| [sanitize](#querylogger-sanitize) | `Any` | 로그용 복사본에서 벡터는 앞부분과 차원만, 민감한 키는 마스킹 값으로 표시한다. |
| [mask](#querylogger-mask) | `Any` | 민감한 키만 마스킹한다. 바꿀 키가 없으면 원본 객체를 그대로 돌려준다 (복사 없음). |
| [effective_mode](#querylogger-effective_mode) | `str` | ``force`` 와 설정 모드를 고려해 이번 로그에 실제로 적용할 모드를 반환한다. |
| [log_query](#querylogger-log_query) | `None` | 쿼리 상세 로그를 출력한다. |
| [log_batch_query](#querylogger-log_batch_query) | `None` | 배치 쿼리와 앞의 최대 ``BATCH_LOG_LIMIT`` 건 로그용 파라미터를 실행 전에 기록한다. |
| [log_summary](#querylogger-log_summary) | `None` | ``EVENT [id] key=value ...`` 한 줄을 출력한다. float는 소수 첫째 자리까지 표시한다. |
| [display_width](#querylogger-display_width) | `int` | 터미널 표시 폭을 계산한다. 한글 전각 문자는 두 칸으로 센다. |
| [format_result_cell](#querylogger-format_result_cell) | `str` | 표시용 값만 문자열로 바꾸고 긴 값은 컬럼 폭에 맞게 줄인다. |
| [format_result_table](#querylogger-format_result_table) | `str` | 반환된 행을 원본 변경 없이 한글 표시 폭을 고려한 ASCII 표로 만든다. |
| [log_result_data](#querylogger-log_result_data) | `None` | ``result_log`` 가 켜진 경우 반환 데이터를 최대 ``result_log_limit`` 행까지 표로 출력한다. |
| [log_transaction](#querylogger-log_transaction) | `None` | ``TRANSACTION BEGIN`` / ``COMMIT`` / ``ROLLBACK`` 을 출력한다. |
| [log_transaction_failure](#querylogger-log_transaction_failure) | `None` | commit 실패 등 트랜잭션 단계 실패를 ERROR로 남긴다. 예외 전파는 호출자가 담당한다. |
| [log_rollback_failure](#querylogger-log_rollback_failure) | `None` | rollback 실패를 traceback과 함께 남긴다. ``except`` 블록 안에서 호출해야 한다. |
| [_log_failure](#querylogger-_log_failure) | `None` | 로그 출력 실패를 WARNING으로 남긴다. 이 경고 출력마저 실패하면 조용히 무시한다. |

### QueryLogger __init__

```python
def __init__(self, logger: logging.Logger, *, log_mode: str='combined', result_log: bool=False, result_log_limit: int=100, mode_option_name: str='log_mode', query_label: str='SQL', vector_types: tuple[type, ...]=(), sensitive_keys: Collection[str] | None=None, value_formatter: Callable[[Any], str] | None=None, combined_params_line: bool=True) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 로그 설정을 검증해 보관한다. 잘못된 ``log_mode`` / ``result_log_limit`` 은 ``ValueError``.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (90행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `logger` | `logging.Logger` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `log_mode` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `result_log` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `result_log_limit` | `int` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `mode_option_name` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `query_label` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `vector_types` | `tuple[type, ...]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `sensitive_keys` | `Collection[str] \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `value_formatter` | `Callable[[Any], str] \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `combined_params_line` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### QueryLogger log_mode getter

```python
@property
def log_mode(self) -> str:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `str`. 현재 쿼리 로그 모드.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (130행)

### QueryLogger log_mode setter

```python
@log_mode.setter
def log_mode(self, value: str) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 쿼리 로그 출력 모드를 읽거나 검증해 설정한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (130행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `str` | 처리하거나 설정할 값 |

### QueryLogger result_log_limit getter

```python
@property
def result_log_limit(self) -> int:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `int`. 결과 표에 표시할 최대 행 수.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (142행)

### QueryLogger result_log_limit setter

```python
@result_log_limit.setter
def result_log_limit(self, value: int) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 결과 로그의 최대 행 수를 읽거나 검증해 설정한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (142행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `int` | 처리하거나 설정할 값 |

### QueryLogger sensitive_keys getter

```python
@property
def sensitive_keys(self) -> tuple[str, ...]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `tuple[str, ...]`. 마스킹할 키 이름 목록(설정한 원래 표기).
- **원본:** [query_logger.py](../../../../common/query_logger.py) (155행)

### QueryLogger sensitive_keys setter

```python
@sensitive_keys.setter
def sensitive_keys(self, value: Collection[str] | None) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 로그에서 숨길 매개변수 키 목록을 읽거나 설정한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (155행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `Collection[str] \| None` | 처리하거나 설정할 값 |

### QueryLogger enabled

```python
def enabled(self) -> bool:
```

- **주요 호출자:** `QueryLogger.log_batch_query`, `QueryLogger.log_query`, `QueryLogger.log_result_data`, `QueryLogger.log_summary`
- **반환:** `bool`. 상세 로그가 출력되는 레벨인지 확인한다. 꺼져 있으면 렌더링 비용을 쓰지 않는다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (166행)

### QueryLogger is_sensitive_key

```python
def is_sensitive_key(self, key: Any) -> bool:
```

- **주요 호출자:** `QueryLogger.mask`, `QueryLogger.sanitize`
- **반환:** `bool`. 키가 민감 키 목록과 완전 일치하거나, 6자 이상 항목으로 끝나면 True를 반환한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (173행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `key` | `Any` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### QueryLogger format_vector_preview

```python
def format_vector_preview(self, values: list | tuple, dimension: int) -> str:
```

- **주요 호출자:** `QueryLogger.sanitize`
- **반환:** `str`. 벡터 앞부분만 표시할 로그 문자열을 만든다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (181행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `values` | `list \| tuple` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `dimension` | `int` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### QueryLogger sanitize

```python
def sanitize(self, value: Any) -> Any:
```

- **주요 호출자:** `QueryLogger.log_batch_query`, `QueryLogger.log_query`, `QueryLogger.sanitize`
- **반환:** `Any`. 로그용 복사본에서 벡터는 앞부분과 차원만, 민감한 키는 마스킹 값으로 표시한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (188행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `Any` | 처리하거나 설정할 값 |

### QueryLogger mask

```python
def mask(self, value: Any) -> Any:
```

- **주요 호출자:** `QueryLogger.mask`
- **반환:** `Any`. 민감한 키만 마스킹한다. 바꿀 키가 없으면 원본 객체를 그대로 돌려준다 (복사 없음).
- **원본:** [query_logger.py](../../../../common/query_logger.py) (216행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `Any` | 처리하거나 설정할 값 |

### QueryLogger effective_mode

```python
def effective_mode(self, force: bool=False) -> str:
```

- **주요 호출자:** `QueryLogger.log_query`
- **반환:** `str`. ``force`` 와 설정 모드를 고려해 이번 로그에 실제로 적용할 모드를 반환한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (240행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `force` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### QueryLogger log_query

```python
def log_query(self, statement_id: str, query: str, parameters: Any, *, render_combined: Callable[[Any], str] | None=None, force: bool=False) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 쿼리 상세 로그를 출력한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (245행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `query` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `parameters` | `Any` | 쿼리에 바인딩할 매개변수 |
| `render_combined` | `Callable[[Any], str] \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `force` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### QueryLogger log_batch_query

```python
def log_batch_query(self, statement_id: str, query: str, parameters_list: list, *, force: bool=False) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. 배치 쿼리와 앞의 최대 ``BATCH_LOG_LIMIT`` 건 로그용 파라미터를 실행 전에 기록한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (295행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `query` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `parameters_list` | `list` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `force` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### QueryLogger log_summary

```python
def log_summary(self, event: str, statement_id: str, **fields: Any) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. ``EVENT [id] key=value ...`` 한 줄을 출력한다. float는 소수 첫째 자리까지 표시한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (333행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `event` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |

### QueryLogger display_width

```python
def display_width(self, value: str) -> int:
```

- **주요 호출자:** `QueryLogger.format_result_cell`, `QueryLogger.format_result_table`
- **반환:** `int`. 터미널 표시 폭을 계산한다. 한글 전각 문자는 두 칸으로 센다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (357행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `str` | 처리하거나 설정할 값 |

### QueryLogger format_result_cell

```python
def format_result_cell(self, value: Any) -> str:
```

- **주요 호출자:** `QueryLogger.format_result_table`
- **반환:** `str`. 표시용 값만 문자열로 바꾸고 긴 값은 컬럼 폭에 맞게 줄인다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (366행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `Any` | 처리하거나 설정할 값 |

### QueryLogger format_result_table

```python
def format_result_table(self, rows: list) -> str:
```

- **주요 호출자:** `QueryLogger.log_result_data`
- **반환:** `str`. 반환된 행을 원본 변경 없이 한글 표시 폭을 고려한 ASCII 표로 만든다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (395행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rows` | `list` | 조회 또는 적재 대상 행 목록 |

### QueryLogger log_result_data

```python
def log_result_data(self, statement_id: str, result: Any, *, log_scalar: bool=True) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. ``result_log`` 가 켜진 경우 반환 데이터를 최대 ``result_log_limit`` 행까지 표로 출력한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (425행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `result` | `Any` | 조회 또는 추천 결과 |
| `log_scalar` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### QueryLogger log_transaction

```python
def log_transaction(self, event: str) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. ``TRANSACTION BEGIN`` / ``COMMIT`` / ``ROLLBACK`` 을 출력한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (464행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `event` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### QueryLogger log_transaction_failure

```python
def log_transaction_failure(self, event: str, exc: BaseException) -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. commit 실패 등 트랜잭션 단계 실패를 ERROR로 남긴다. 예외 전파는 호출자가 담당한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (471행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `event` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `exc` | `BaseException` | 전파 또는 로깅할 예외 |

### QueryLogger log_rollback_failure

```python
def log_rollback_failure(self, message: str='TRANSACTION ROLLBACK FAILED') -> None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `None`. rollback 실패를 traceback과 함께 남긴다. ``except`` 블록 안에서 호출해야 한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (478행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `message` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

### QueryLogger _log_failure

```python
def _log_failure(self, kind: str, statement_id: str, exc: Exception) -> None:
```

- **주요 호출자:** `QueryLogger.log_batch_query`, `QueryLogger.log_query`, `QueryLogger.log_result_data`, `QueryLogger.log_summary`
- **반환:** `None`. 로그 출력 실패를 WARNING으로 남긴다. 이 경고 출력마저 실패하면 조용히 무시한다.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (485행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `kind` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `exc` | `Exception` | 전파 또는 로깅할 예외 |

## Function _normalize_key

```python
def _normalize_key(key: Any) -> str:
```

- **호출자:** `PostgresDbSession`, `Neo4jDbSession`
- **반환:** `str`. 민감 키 비교용으로 소문자화하고 영숫자만 남긴다. 예: ``"DB_Password"`` → ``"dbpassword"``.
- **원본:** [query_logger.py](../../../../common/query_logger.py) (37행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `key` | `Any` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function is_numeric_sequence

```python
def is_numeric_sequence(value: Any, min_length: int) -> bool:
```

- **호출자:** `PostgresDbSession`, `Neo4jDbSession`
- **반환:** `bool`. bool을 제외한 int/float만 담긴 긴 list/tuple인지 확인한다 (벡터 판정 기준).
- **원본:** [query_logger.py](../../../../common/query_logger.py) (42행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `value` | `Any` | 처리하거나 설정할 값 |
| `min_length` | `int` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
