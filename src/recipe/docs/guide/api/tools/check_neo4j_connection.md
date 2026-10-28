# check_neo4j_connection 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.tools.check_neo4j_connection`
- **소스:** [recipe_recommender/tools/check_neo4j_connection.py](../../../../recipe_recommender/tools/check_neo4j_connection.py)
- **역할:** 기존 환경변수로 Neo4j 연결과 읽기 쿼리를 확인하는 단독 실행 도구.
- **주요 호출자:** 명시적으로 실행한 관리 CLI
- **정의:** 클래스 0개, 모듈 함수 1개

- **직접 의존:** `recipe_recommender.tools._connection_util`

- **실행:** `python -m recipe_recommender.tools.check_neo4j_connection`

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [main](#function-main) | `int` | Neo4j에 연결해 읽기 쿼리 한 건으로 연결 상태를 확인한다. |

## Function main

```python
def main() -> int:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `int`. Neo4j에 연결해 읽기 쿼리 한 건으로 연결 상태를 확인한다.
- **원본:** [check_neo4j_connection.py](../../../../recipe_recommender/tools/check_neo4j_connection.py) (19행)

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
