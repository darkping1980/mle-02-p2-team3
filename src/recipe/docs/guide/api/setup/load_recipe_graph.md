# load_recipe_graph 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.setup.load_recipe_graph`
- **소스:** [recipe_recommender/setup/load_recipe_graph.py](../../../../recipe_recommender/setup/load_recipe_graph.py)
- **역할:** PostgreSQL 스냅샷과 Neo4j를 대조하는 CLI 진입점.
- **주요 호출자:** `python -m recipe_recommender.setup.load_recipe_graph`
- **정의:** 클래스 0개, 모듈 함수 1개

- **직접 의존:** `recipe_recommender.config`, `recipe_recommender.setup.recipe_graph_load_service`, `recipe_recommender.recipe_graph_repository`, `recipe_recommender.setup.recipe_graph_source_repository`, `recipe_recommender.tools._connection_util`

- **실행:** `python -m recipe_recommender.setup.load_recipe_graph`

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [main](#function-main) | `int` | CLI 인자를 해석해 Source/Graph Repository를 Service에 주입하고 보고서를 반환한다. |

## Function main

```python
def main(argv: list[str] | None=None) -> int:
```

- **호출자:** `python -m recipe_recommender.setup.load_recipe_graph`
- **반환:** `int`. CLI 인자를 해석해 Source/Graph Repository를 Service에 주입하고 보고서를 반환한다.
- **원본:** [load_recipe_graph.py](../../../../recipe_recommender/setup/load_recipe_graph.py) (26행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `argv` | `list[str] \| None` | CLI 인자 목록; 생략하면 프로세스 인자를 사용 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
