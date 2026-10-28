# query_session 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `common.query_session`
- **소스:** [common/query_session.py](../../../../common/query_session.py)
- **역할:** DB 종류와 무관한 동기식 쿼리 세션 계약(인터페이스).
- **주요 호출자:** 레시피 Repository와 DB 연결 팩토리; 일부 유틸은 다른 예제에서도 사용
- **정의:** 클래스 1개, 모듈 함수 0개

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [QuerySession](#querysession) | 클래스 | DB별 쿼리 세션이 공통으로 제공하는 최소 계약. |

## QuerySession

**클래스.** DB별 쿼리 세션이 공통으로 제공하는 최소 계약.

- **정의:** [query_session.py](../../../../common/query_session.py) (26행)
- **생성 위치:** 직접 생성 호출은 주요 진입 경로에서 확인되지 않음; 정의와 호출 코드를 참조한다.

### Constructor Summary

명시적 `__init__`가 없다. 상위 클래스 또는 Python 기본 생성자를 사용한다.

### Method Summary

| 메서드 | 반환형 | 설명 |
| --- | --- | --- |
| [select_list](#querysession-select_list) | `list[dict[str, Any]]` | 조회 결과의 모든 레코드를 dict 목록으로 반환한다. |
| [select_one](#querysession-select_one) | `dict[str, Any] \| None` | 조회 결과의 첫 레코드를 반환하고, 레코드가 없으면 ``None`` 을 반환한다. |
| [execute](#querysession-execute) | `Any` | DB별 statement 하나를 실행하고 해당 DB 고유의 결과를 그대로 반환한다. |
| [execute_many](#querysession-execute_many) | `Any` | 같은 statement를 여러 파라미터 묶음에 적용한다. |
| [transaction](#querysession-transaction) | `AbstractContextManager['QuerySession']` | 블록 전체를 원자적으로 commit 또는 rollback하는 context manager를 반환한다. |

### QuerySession select_list

```python
@abstractmethod
def select_list(self, statement_id: str, parameters: Mapping[str, Any] | None=None) -> list[dict[str, Any]]:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `list[dict[str, Any]]`. 조회 결과의 모든 레코드를 dict 목록으로 반환한다.
- **원본:** [query_session.py](../../../../common/query_session.py) (35행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `parameters` | `Mapping[str, Any] \| None` | 쿼리에 바인딩할 매개변수 |

### QuerySession select_one

```python
@abstractmethod
def select_one(self, statement_id: str, parameters: Mapping[str, Any] | None=None) -> dict[str, Any] | None:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `dict[str, Any] | None`. 조회 결과의 첫 레코드를 반환하고, 레코드가 없으면 ``None`` 을 반환한다.
- **원본:** [query_session.py](../../../../common/query_session.py) (43행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `parameters` | `Mapping[str, Any] \| None` | 쿼리에 바인딩할 매개변수 |

### QuerySession execute

```python
@abstractmethod
def execute(self, statement_id: str, parameters: Mapping[str, Any] | None=None) -> Any:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `Any`. DB별 statement 하나를 실행하고 해당 DB 고유의 결과를 그대로 반환한다.
- **원본:** [query_session.py](../../../../common/query_session.py) (51행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `parameters` | `Mapping[str, Any] \| None` | 쿼리에 바인딩할 매개변수 |

**부작용:** 호출 경로와 트랜잭션 조건에 따라 DB 상태를 변경한다. 상세 조건은 소스와 [실행 흐름](../../04_execution_flow.md)을 확인한다.

### QuerySession execute_many

```python
@abstractmethod
def execute_many(self, statement_id: str, parameters_list: Sequence[Mapping[str, Any]]) -> Any:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `Any`. 같은 statement를 여러 파라미터 묶음에 적용한다.
- **원본:** [query_session.py](../../../../common/query_session.py) (59행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `statement_id` | `str` | mapper의 명명 쿼리 식별자 |
| `parameters_list` | `Sequence[Mapping[str, Any]]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

**부작용:** 호출 경로와 트랜잭션 조건에 따라 DB 상태를 변경한다. 상세 조건은 소스와 [실행 흐름](../../04_execution_flow.md)을 확인한다.

### QuerySession transaction

```python
@abstractmethod
def transaction(self) -> AbstractContextManager['QuerySession']:
```

- **주요 호출자:** 외부/프레임워크 호출 또는 직접 생성 경로; 원본 소스와 Module Summary의 진입 경로 참조
- **반환:** `AbstractContextManager['QuerySession']`. 블록 전체를 원자적으로 commit 또는 rollback하는 context manager를 반환한다.
- **원본:** [query_session.py](../../../../common/query_session.py) (67행)

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
