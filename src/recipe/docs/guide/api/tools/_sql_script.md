# _sql_script 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.tools._sql_script`
- **소스:** [recipe_recommender/tools/_sql_script.py](../../../../recipe_recommender/tools/_sql_script.py)
- **역할:** BEGIN/COMMIT을 포함한 관리용 SQL 스크립트(재생성·초기화)를 실행하는 공통 도우미.
- **주요 호출자:** 명시적으로 실행한 관리 CLI
- **정의:** 클래스 0개, 모듈 함수 2개

- **직접 의존:** `recipe_recommender.config`

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [print_state](#function-print_state) | `None` | recipe 스키마 객체와 테이블 행 수, 시퀀스 현재값을 출력한다(읽기 전용). |
| [run_sql_script](#function-run_sql_script) | `int` | 스크립트 실행 전후 상태를 출력하고, ``confirmed`` 일 때만 실제로 실행한다. Returns 종료 코드. |

## Function print_state

```python
def print_state(connection, title: str) -> None:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `None`. recipe 스키마 객체와 테이블 행 수, 시퀀스 현재값을 출력한다(읽기 전용).
- **원본:** [_sql_script.py](../../../../recipe_recommender/tools/_sql_script.py) (22행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `title` | `str` | 출력할 제목 |

## Function run_sql_script

```python
def run_sql_script(script_path: Path, *, confirmed: bool, confirm_flag: str) -> int:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `int`. 스크립트 실행 전후 상태를 출력하고, ``confirmed`` 일 때만 실제로 실행한다. Returns 종료 코드.
- **원본:** [_sql_script.py](../../../../recipe_recommender/tools/_sql_script.py) (41행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `script_path` | `Path` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `confirmed` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `confirm_flag` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
