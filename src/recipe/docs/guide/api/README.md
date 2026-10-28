# 레시피 GraphRAG API Reference

[개발자 가이드](../README.md) · [파일 인덱스](../02_file_structure.md)

VS Code 기본 Markdown Preview에서 **패키지 → 모듈 → 클래스/함수 → 메서드 → Python 소스** 순서로 이동한다. 표의 이름을 클릭하면 상세 항목으로 이동한다. 검색은 VS Code의 Markdown 검색을 사용한다.

## 패키지와 실행 모듈

| 분류 | 실제 종류 | 역할 | 모듈 수 |
| --- | --- | --- | ---: |
| [recipe_recommender](recipe_recommender/README.md) | Python 패키지 | 추천, PostgreSQL 조회, Repository와 연결 설정을 담는 실제 Python 패키지 | 13 |
| [recipe_recommender.setup](setup/README.md) | Python 패키지 | CSV 등록과 PostgreSQL 원천 검증, Neo4j 초기 적재를 담는 실제 하위 패키지 | 6 |
| [recipe_recommender.tools](tools/README.md) | Python 패키지 | 연결 점검, 스키마 재구축·초기화 도구를 담는 실제 하위 패키지 | 7 |
| [common](common/README.md) | Python 패키지 | PostgreSQL·Neo4j 세션, 쿼리 로그와 공통 도우미를 담는 실제 Python 패키지 | 7 |
| [streamlit_app.py](streamlit_app.md) | 독립 실행 모듈 | 패키지 밖 웹 실행 모듈. Streamlit이 파일을 직접 재실행한다. | 1 |

## 전체 색인

- [Class Index (39개)](class_index.md)
- [Function Index (148개)](function_index.md)

`sql/`, `data/`, `docs/`는 Python 패키지가 아니다. SQL·Cypher mapper는 Repository와 DB 세션에서 이름으로 호출한다.

## 흐름을 함께 읽기

- [컴포넌트 의존 관계](../03_component_structure.md)
- [웹·등록·적재 실행 흐름](../04_execution_flow.md)
- [State·DTO 데이터 흐름](../05_data_flow.md)
- [업무별 상세 가이드](../details/01_streamlit.md)
