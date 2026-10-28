# check_supabase_connection 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.tools.check_supabase_connection`
- **소스:** [recipe_recommender/tools/check_supabase_connection.py](../../../../recipe_recommender/tools/check_supabase_connection.py)
- **역할:** 기존 ``DB_URL``로 PostgreSQL 읽기 연결을 확인하는 단독 실행 도구.
- **주요 호출자:** 명시적으로 실행한 관리 CLI
- **정의:** 클래스 0개, 모듈 함수 3개

- **직접 의존:** `recipe_recommender.tools._connection_util`

- **실행:** `python -m recipe_recommender.tools.check_supabase_connection`

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [_run_query](#function-_run_query) | `타입 힌트 없음` | 공통 연결 관리자로 SELECT를 실행하고 의존 패키지가 없을 때 psycopg를 쓴다. |
| [_target_label](#function-_target_label) | `str` | ``DB_URL`` 호스트와 설정값을 기준으로 확인한 대상의 표시명을 고른다. |
| [main](#function-main) | `int` | PostgreSQL에 연결해 SELECT 한 건으로 연결 상태를 확인한다. |

## Function _run_query

```python
def _run_query():
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `타입 힌트 없음`. 공통 연결 관리자로 SELECT를 실행하고 의존 패키지가 없을 때 psycopg를 쓴다.
- **원본:** [check_supabase_connection.py](../../../../recipe_recommender/tools/check_supabase_connection.py) (19행)

## Function _target_label

```python
def _target_label() -> str:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `str`. ``DB_URL`` 호스트와 설정값을 기준으로 확인한 대상의 표시명을 고른다.
- **원본:** [check_supabase_connection.py](../../../../recipe_recommender/tools/check_supabase_connection.py) (43행)

## Function main

```python
def main() -> int:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `int`. PostgreSQL에 연결해 SELECT 한 건으로 연결 상태를 확인한다.
- **원본:** [check_supabase_connection.py](../../../../recipe_recommender/tools/check_supabase_connection.py) (55행)

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
