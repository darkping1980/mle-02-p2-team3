# rebuild_recipe_schema 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.tools.rebuild_recipe_schema`
- **소스:** [recipe_recommender/tools/rebuild_recipe_schema.py](../../../../recipe_recommender/tools/rebuild_recipe_schema.py)
- **역할:** 기존 모델 전용 스키마 재생성 도구. `--confirm-rebuild`는 현재 차단되며, 인자 없이 현황만 조회한다.
- **주요 호출자:** 명시적으로 실행한 관리 CLI
- **정의:** 클래스 0개, 모듈 함수 1개

- **직접 의존:** `recipe_recommender.tools._sql_script`

- **실행:** `python -m recipe_recommender.tools.rebuild_recipe_schema`

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [main](#function-main) | `int` | 기존 모델 전용 스키마 재생성 진입점의 실행 차단 조건을 적용한다. |

## Function main

```python
def main(argv=None) -> int:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `int`. 기존 모델 전용 스키마 재생성 진입점의 실행 차단 조건을 적용한다.
- **원본:** [rebuild_recipe_schema.py](../../../../recipe_recommender/tools/rebuild_recipe_schema.py) (26행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `argv` | `타입 힌트 없음` | CLI 인자 목록; 생략하면 프로세스 인자를 사용 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
