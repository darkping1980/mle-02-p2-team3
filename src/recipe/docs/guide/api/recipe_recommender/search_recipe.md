# search_recipe 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.search_recipe`
- **소스:** [recipe_recommender/search_recipe.py](../../../../recipe_recommender/search_recipe.py)
- **역할:** 레시피 조회 CLI 진입점 (읽기 전용).
- **주요 호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **정의:** 클래스 0개, 모듈 함수 5개

- **직접 의존:** `.database`, `.recipe_search_service`

- **실행:** `python -m recipe_recommender.search_recipe`

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [parse_args](#function-parse_args) | `argparse.Namespace` | CLI 조회 조건과 출력 옵션을 파싱한다. |
| [_print_rows](#function-_print_rows) | `None` | 조회 행에서 요청한 컬럼만 골라 콘솔에 출력한다. |
| [print_detail](#function-print_detail) | `None` | 레시피 상세와 단계·재료 목록을 콘솔에 출력한다. |
| [print_page](#function-print_page) | `None` | 페이지형 조회 결과의 행과 건수 정보를 출력한다. |
| [main](#function-main) | `int` | 조회 세션과 Service를 만들고 CLI 요청을 실행한 뒤 종료 코드를 반환한다. |

## Function parse_args

```python
def parse_args(argv=None) -> argparse.Namespace:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `argparse.Namespace`. CLI 조회 조건과 출력 옵션을 파싱한다.
- **원본:** [search_recipe.py](../../../../recipe_recommender/search_recipe.py) (22행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `argv` | `타입 힌트 없음` | CLI 인자 목록; 생략하면 프로세스 인자를 사용 |

## Function _print_rows

```python
def _print_rows(rows: list[dict], columns: list[str]) -> None:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `None`. 조회 행에서 요청한 컬럼만 골라 콘솔에 출력한다.
- **원본:** [search_recipe.py](../../../../recipe_recommender/search_recipe.py) (40행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `rows` | `list[dict]` | 조회 또는 적재 대상 행 목록 |
| `columns` | `list[str]` | 행에서 사용할 컬럼 이름 |

## Function print_detail

```python
def print_detail(detail: dict) -> None:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `None`. 레시피 상세와 단계·재료 목록을 콘솔에 출력한다.
- **원본:** [search_recipe.py](../../../../recipe_recommender/search_recipe.py) (46행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `detail` | `dict` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function print_page

```python
def print_page(result: dict, columns: list[str]) -> None:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `None`. 페이지형 조회 결과의 행과 건수 정보를 출력한다.
- **원본:** [search_recipe.py](../../../../recipe_recommender/search_recipe.py) (62행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `result` | `dict` | 조회 또는 추천 결과 |
| `columns` | `list[str]` | 행에서 사용할 컬럼 이름 |

## Function main

```python
def main(argv=None) -> int:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `int`. 조회 세션과 Service를 만들고 CLI 요청을 실행한 뒤 종료 코드를 반환한다.
- **원본:** [search_recipe.py](../../../../recipe_recommender/search_recipe.py) (68행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `argv` | `타입 힌트 없음` | CLI 인자 목록; 생략하면 프로세스 인자를 사용 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
