# _connection_util 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.tools._connection_util`
- **소스:** [recipe_recommender/tools/_connection_util.py](../../../../recipe_recommender/tools/_connection_util.py)
- **역할:** 단독 연결 점검 도구가 공유하는 경로 준비와 오류 메시지 정리 함수.
- **주요 호출자:** 명시적으로 실행한 관리 CLI
- **정의:** 클래스 0개, 모듈 함수 2개

- **직접 의존:** `recipe_recommender.config`

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [initialize](#function-initialize) | `None` | 단독 실행 도구가 패키지 경로와 환경변수를 읽도록 준비한다. |
| [safe_error](#function-safe_error) | `str` | 오류의 원인은 유지하면서 설정된 자격 증명과 URL 사용자 정보를 가린다. |

## Function initialize

```python
def initialize() -> None:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `None`. 단독 실행 도구가 패키지 경로와 환경변수를 읽도록 준비한다.
- **원본:** [_connection_util.py](../../../../recipe_recommender/tools/_connection_util.py) (10행)

## Function safe_error

```python
def safe_error(error: Exception) -> str:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `str`. 오류의 원인은 유지하면서 설정된 자격 증명과 URL 사용자 정보를 가린다.
- **원본:** [_connection_util.py](../../../../recipe_recommender/tools/_connection_util.py) (16행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `error` | `Exception` | 화면이나 CLI에 표시할 연결 오류. |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
