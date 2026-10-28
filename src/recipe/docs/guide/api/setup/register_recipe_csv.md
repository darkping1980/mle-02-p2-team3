# register_recipe_csv 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.setup.register_recipe_csv`
- **소스:** [recipe_recommender/setup/register_recipe_csv.py](../../../../recipe_recommender/setup/register_recipe_csv.py)
- **역할:** 식약처 레시피 CSV 등록 CLI 진입점.
- **주요 호출자:** `python -m recipe_recommender.setup.register_recipe_csv`
- **정의:** 클래스 0개, 모듈 함수 4개

- **직접 의존:** `..config`, `..database`, `.recipe_register_service`

- **실행:** `python -m recipe_recommender.setup.register_recipe_csv`

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [parse_args](#function-parse_args) | `argparse.Namespace` | CSV 경로와 적재·리허설 옵션을 CLI에서 읽는다. |
| [_print_list](#function-_print_list) | `None` | 검토 항목의 제목과 지정한 개수만큼의 예시를 출력한다. |
| [print_report](#function-print_report) | `None` | 검증 계획과 등록 결과의 건수·오류를 콘솔에 출력한다. |
| [main](#function-main) | `int` | CSV 적재 Service를 실행하고 결과에 따른 종료 코드를 반환한다. |

## Function parse_args

```python
def parse_args(argv=None) -> argparse.Namespace:
```

- **호출자:** `python -m recipe_recommender.setup.register_recipe_csv`
- **반환:** `argparse.Namespace`. CSV 경로와 적재·리허설 옵션을 CLI에서 읽는다.
- **원본:** [register_recipe_csv.py](../../../../recipe_recommender/setup/register_recipe_csv.py) (32행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `argv` | `타입 힌트 없음` | CLI 인자 목록; 생략하면 프로세스 인자를 사용 |

## Function _print_list

```python
def _print_list(title: str, items: list[str], show: int) -> None:
```

- **호출자:** `python -m recipe_recommender.setup.register_recipe_csv`
- **반환:** `None`. 검토 항목의 제목과 지정한 개수만큼의 예시를 출력한다.
- **원본:** [register_recipe_csv.py](../../../../recipe_recommender/setup/register_recipe_csv.py) (56행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `title` | `str` | 출력할 제목 |
| `items` | `list[str]` | 처리할 항목 목록 |
| `show` | `int` | 화면에 보여 줄 최대 항목 수 |

## Function print_report

```python
def print_report(result: RecipeLoadResult, show: int) -> None:
```

- **호출자:** `python -m recipe_recommender.setup.register_recipe_csv`
- **반환:** `None`. 검증 계획과 등록 결과의 건수·오류를 콘솔에 출력한다.
- **원본:** [register_recipe_csv.py](../../../../recipe_recommender/setup/register_recipe_csv.py) (65행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `result` | `RecipeLoadResult` | 조회 또는 추천 결과 |
| `show` | `int` | 화면에 보여 줄 최대 항목 수 |

## Function main

```python
def main(argv=None) -> int:
```

- **호출자:** `python -m recipe_recommender.setup.register_recipe_csv`
- **반환:** `int`. CSV 적재 Service를 실행하고 결과에 따른 종료 코드를 반환한다.
- **원본:** [register_recipe_csv.py](../../../../recipe_recommender/setup/register_recipe_csv.py) (114행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `argv` | `타입 힌트 없음` | CLI 인자 목록; 생략하면 프로세스 인자를 사용 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
