# sql_schema 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.sql_schema`
- **소스:** [recipe_recommender/sql_schema.py](../../../../recipe_recommender/sql_schema.py)
- **역할:** 레시피 SQL의 대상 스키마 지정 도우미.
- **주요 호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **정의:** 클래스 0개, 모듈 함수 3개

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [validate_schema_name](#function-validate_schema_name) | `str` | 소문자 PostgreSQL 식별자인지 검사하고 그대로 돌려준다. |
| [configured_schema](#function-configured_schema) | `str` | 명시 인자 → 환경변수 ``RECIPE_DB_SCHEMA`` → 기본 ``recipe`` 순서로 대상 스키마를 정한다. |
| [render_schema_sql](#function-render_schema_sql) | `str` | ``recipe.`` 한정자를 ``target.`` 으로, ``recipe_src.`` 를 ``source.`` 로 바꾼다. |

## Function validate_schema_name

```python
def validate_schema_name(name: str) -> str:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `str`. 소문자 PostgreSQL 식별자인지 검사하고 그대로 돌려준다.
- **원본:** [sql_schema.py](../../../../recipe_recommender/sql_schema.py) (26행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `name` | `str` | 조회할 이름 또는 식별자 |

## Function configured_schema

```python
def configured_schema(schema: str | None=None) -> str:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `str`. 명시 인자 → 환경변수 ``RECIPE_DB_SCHEMA`` → 기본 ``recipe`` 순서로 대상 스키마를 정한다.
- **원본:** [sql_schema.py](../../../../recipe_recommender/sql_schema.py) (33행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `schema` | `str \| None` | PostgreSQL 대상 스키마 |

## Function render_schema_sql

```python
def render_schema_sql(sql: str, target: str, source: str | None=None) -> str:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `str`. ``recipe.`` 한정자를 ``target.`` 으로, ``recipe_src.`` 를 ``source.`` 로 바꾼다.
- **원본:** [sql_schema.py](../../../../recipe_recommender/sql_schema.py) (38행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `sql` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `target` | `str` | 대상 스키마 또는 대상 정보 |
| `source` | `str \| None` | PostgreSQL 원천 또는 원천 Repository |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
