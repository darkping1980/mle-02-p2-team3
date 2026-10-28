# neo4j_connection 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.neo4j_connection`
- **소스:** [recipe_recommender/neo4j_connection.py](../../../../recipe_recommender/neo4j_connection.py)
- **역할:** Neo4j 드라이버 생성 — TLS 인증서 검증을 유지하면서 신뢰할 CA 번들을 명시한다.
- **주요 호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **정의:** 클래스 0개, 모듈 함수 3개

- **직접 의존:** `.config`

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [trusted_ca_file](#function-trusted_ca_file) | `str` | 신뢰할 CA 번들 PEM 경로. 지정 파일이 없으면 오류(조용히 검증을 끄지 않는다). |
| [driver_arguments](#function-driver_arguments) | `tuple[str, dict]` | ``GraphDatabase.driver`` 에 넘길 URI와 TLS 설정. 검증하는 TLS 스킴만 CA 번들을 명시한다. |
| [create_neo4j_driver](#function-create_neo4j_driver) | `타입 힌트 없음` | 저장소 ``.env`` 의 ``NEO4J_URI`` / ``NEO4J_USERNAME`` / ``NEO4J_PASSWORD`` 로 드라이버를 만든다. |

## Function trusted_ca_file

```python
def trusted_ca_file() -> str:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `str`. 신뢰할 CA 번들 PEM 경로. 지정 파일이 없으면 오류(조용히 검증을 끄지 않는다).
- **원본:** [neo4j_connection.py](../../../../recipe_recommender/neo4j_connection.py) (26행)

## Function driver_arguments

```python
def driver_arguments(uri: str) -> tuple[str, dict]:
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `tuple[str, dict]`. ``GraphDatabase.driver`` 에 넘길 URI와 TLS 설정. 검증하는 TLS 스킴만 CA 번들을 명시한다.
- **원본:** [neo4j_connection.py](../../../../recipe_recommender/neo4j_connection.py) (40행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `uri` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function create_neo4j_driver

```python
def create_neo4j_driver():
```

- **호출자:** 웹 진입점, 조회 CLI, 초기 구축 프로그램
- **반환:** `타입 힌트 없음`. 저장소 ``.env`` 의 ``NEO4J_URI`` / ``NEO4J_USERNAME`` / ``NEO4J_PASSWORD`` 로 드라이버를 만든다.
- **원본:** [neo4j_connection.py](../../../../recipe_recommender/neo4j_connection.py) (58행)

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
