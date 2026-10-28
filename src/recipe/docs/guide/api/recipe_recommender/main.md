# main 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.main`
- **소스:** [recipe_recommender/main.py](../../../../recipe_recommender/main.py)
- **역할:** 현재는 scaffold 준비 문구만 출력하는 진입점이다. 검색 Service로 위임하지 않는다.
- **주요 호출자:** `python -m recipe_recommender.main` 또는 직접 `main()` 호출; 현재 scaffold 안내만 출력
- **정의:** 클래스 0개, 모듈 함수 1개

- **직접 의존:** `recipe_recommender.config`

- **실행:** `python -m recipe_recommender.main`

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [main](#function-main) | `int` | import 경로를 준비하고 scaffold 안내 문구를 출력한 뒤 0을 반환한다. 레시피 검색은 실행하지 않는다. |

## Function main

```python
def main() -> int:
```

- **호출자:** `python -m recipe_recommender.main` 또는 직접 `main()` 호출; 현재 scaffold 안내만 출력
- **반환:** `int`. import 경로를 준비하고 scaffold 안내 문구를 출력한 뒤 0을 반환한다. 레시피 검색은 실행하지 않는다.
- **원본:** [main.py](../../../../recipe_recommender/main.py) (13행)

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
