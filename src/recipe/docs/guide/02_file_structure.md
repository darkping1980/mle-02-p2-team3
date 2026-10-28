# 02. 패키지·모듈 탐색 인덱스

[개발자 가이드](README.md) · [API 전체 목차](api/README.md)

## 문서 개요와 탐색 방법

이 문서는 파일을 패키지별로 찾는 출발점이다. **패키지 요약 → 모듈 상세 → 클래스·메서드 상세 → 원본 Python 소스** 순서로 링크를 따라간다. 업무 처리 순서는 [실행 흐름](04_execution_flow.md), 값의 전달은 [데이터 흐름](05_data_flow.md)에서 확인한다.

## 패키지별 목차

| 분류 | 실제 종류 | 역할 | 주요 모듈 수 | 상세 |
| --- | --- | --- | ---: | --- |
| `recipe_recommender` | Python 패키지 | 추천, PostgreSQL 조회, Repository와 연결 설정을 담는 실제 Python 패키지 | 13 | [API 상세](api/recipe_recommender/README.md) |
| `recipe_recommender.setup` | Python 패키지 | CSV 등록과 PostgreSQL 원천 검증, Neo4j 초기 적재를 담는 실제 하위 패키지 | 6 | [API 상세](api/setup/README.md) |
| `recipe_recommender.tools` | Python 패키지 | 연결 점검, 스키마 재구축·초기화 도구를 담는 실제 하위 패키지 | 7 | [API 상세](api/tools/README.md) |
| `common` | Python 패키지 | PostgreSQL·Neo4j 세션, 쿼리 로그와 공통 도우미를 담는 실제 Python 패키지 | 7 | [API 상세](api/common/README.md) |
| `streamlit_app.py` | 독립 실행 모듈 | 패키지 밖 웹 실행 모듈. Streamlit이 파일을 직접 재실행한다. | 1 | [API 상세](api/streamlit_app.md) |

## recipe_recommender

[Package Summary](api/recipe_recommender/README.md)

| 주요 모듈 | 책임 | 원본 소스 |
| --- | --- | --- |
| [config](api/recipe_recommender/config.md) | 과제 경로와 환경변수 로딩을 준비하는 공통 설정 도우미. | [config.py](../../recipe_recommender/config.py) |
| [graph_question_service](api/recipe_recommender/graph_question_service.md) | 그래프 관계 탐색 Service — 과제 질문 Q1~Q5(1·2·3-hop)를 고정 Named Cypher로 답한다 (Neo4j 읽기 전용, LLM 없음). | [graph_question_service.py](../../recipe_recommender/graph_question_service.py) |
| [database](api/recipe_recommender/database.md) | 레시피 프로젝트의 PostgreSQL 연결과 SQL mapper 경로를 구성한다. | [database.py](../../recipe_recommender/database.py) |
| [main](api/recipe_recommender/main.md) | 현재는 scaffold 준비 문구만 출력하는 진입점이다. 검색 Service로 위임하지 않는다. | [main.py](../../recipe_recommender/main.py) |
| [name_normalization](api/recipe_recommender/name_normalization.md) | 적재와 추천 Service가 공유하는 식재료명 비교 규칙. | [name_normalization.py](../../recipe_recommender/name_normalization.py) |
| [neo4j_connection](api/recipe_recommender/neo4j_connection.md) | Neo4j 드라이버 생성 — TLS 인증서 검증을 유지하면서 신뢰할 CA 번들을 명시한다. | [neo4j_connection.py](../../recipe_recommender/neo4j_connection.py) |
| [pantry_graphrag](api/recipe_recommender/pantry_graphrag.md) | 냉장고 재료 추천 GraphRAG — LangGraph 흐름: 입력 해석 → Neo4j 조회 → 근거 기반 답변. | [pantry_graphrag.py](../../recipe_recommender/pantry_graphrag.py) |
| [pantry_recommend_service](api/recipe_recommender/pantry_recommend_service.md) | 냉장고 재료 기반 레시피 추천 Service (Neo4j 읽기 전용, LLM 없음). | [pantry_recommend_service.py](../../recipe_recommender/pantry_recommend_service.py) |
| [recipe_graph_repository](api/recipe_recommender/recipe_graph_repository.md) | Neo4j mapper를 호출하는 그래프 DAO. 업무 검증은 적재 Service가 담당한다. | [recipe_graph_repository.py](../../recipe_recommender/recipe_graph_repository.py) |
| [recipe_repository](api/recipe_recommender/recipe_repository.md) | 레시피(recipe 스키마) 등록·조회 공용 Repository 모듈. | [recipe_repository.py](../../recipe_recommender/recipe_repository.py) |
| [recipe_search_service](api/recipe_recommender/recipe_search_service.md) | 레시피 조회 Service 모듈 (PostgreSQL 기반 MVP). | [recipe_search_service.py](../../recipe_recommender/recipe_search_service.py) |
| [search_recipe](api/recipe_recommender/search_recipe.md) | 레시피 조회 CLI 진입점 (읽기 전용). | [search_recipe.py](../../recipe_recommender/search_recipe.py) |
| [sql_schema](api/recipe_recommender/sql_schema.md) | 레시피 SQL의 대상 스키마 지정 도우미. | [sql_schema.py](../../recipe_recommender/sql_schema.py) |

## recipe_recommender.setup

[Package Summary](api/setup/README.md)

| 주요 모듈 | 책임 | 원본 소스 |
| --- | --- | --- |
| [load_recipe_graph](api/setup/load_recipe_graph.md) | PostgreSQL 스냅샷과 Neo4j를 대조하는 CLI 진입점. | [load_recipe_graph.py](../../recipe_recommender/setup/load_recipe_graph.py) |
| [recipe_graph_load_service](api/setup/recipe_graph_load_service.md) | PostgreSQL 목표 모델을 검증하고 Neo4j 레시피 그래프에 적재·대조한다. | [recipe_graph_load_service.py](../../recipe_recommender/setup/recipe_graph_load_service.py) |
| [recipe_graph_source_repository](api/setup/recipe_graph_source_repository.md) | 그래프 적재에 필요한 PostgreSQL 목표 모델을 한 시점의 스냅샷으로 읽는다. | [recipe_graph_source_repository.py](../../recipe_recommender/setup/recipe_graph_source_repository.py) |
| [recipe_ingredient_parser](api/setup/recipe_ingredient_parser.md) | ``RCP_PARTS_DTLS`` 재료 원문을 staging 행 후보로 나누는 보수적 파서. | [recipe_ingredient_parser.py](../../recipe_recommender/setup/recipe_ingredient_parser.py) |
| [recipe_register_service](api/setup/recipe_register_service.md) | 식약처 ``COOKRCP01.csv`` 를 recipe 스키마에 적재하는 Service 모듈. | [recipe_register_service.py](../../recipe_recommender/setup/recipe_register_service.py) |
| [register_recipe_csv](api/setup/register_recipe_csv.md) | 식약처 레시피 CSV 등록 CLI 진입점. | [register_recipe_csv.py](../../recipe_recommender/setup/register_recipe_csv.py) |

## recipe_recommender.tools

[Package Summary](api/tools/README.md)

| 주요 모듈 | 책임 | 원본 소스 |
| --- | --- | --- |
| [_connection_util](api/tools/_connection_util.md) | 단독 연결 점검 도구가 공유하는 경로 준비와 오류 메시지 정리 함수. | [_connection_util.py](../../recipe_recommender/tools/_connection_util.py) |
| [_sql_script](api/tools/_sql_script.md) | BEGIN/COMMIT을 포함한 관리용 SQL 스크립트(재생성·초기화)를 실행하는 공통 도우미. | [_sql_script.py](../../recipe_recommender/tools/_sql_script.py) |
| [check_neo4j_connection](api/tools/check_neo4j_connection.md) | 기존 환경변수로 Neo4j 연결과 읽기 쿼리를 확인하는 단독 실행 도구. | [check_neo4j_connection.py](../../recipe_recommender/tools/check_neo4j_connection.py) |
| [check_supabase_connection](api/tools/check_supabase_connection.md) | 기존 ``DB_URL``로 PostgreSQL 읽기 연결을 확인하는 단독 실행 도구. | [check_supabase_connection.py](../../recipe_recommender/tools/check_supabase_connection.py) |
| [rebuild_recipe_schema](api/tools/rebuild_recipe_schema.md) | 기존 모델 전용 스키마 재생성 도구. `--confirm-rebuild`는 현재 차단되며, 인자 없이 현황만 조회한다. | [rebuild_recipe_schema.py](../../recipe_recommender/tools/rebuild_recipe_schema.py) |
| [recipe_rebuild](api/tools/recipe_rebuild.md) | 레시피 PostgreSQL 목표 모델 재구축 도구(백업 → 복원 시험 → 격리 리허설 → 전환 → 복구). | [recipe_rebuild.py](../../recipe_recommender/tools/recipe_rebuild.py) |
| [reset_recipe_data](api/tools/reset_recipe_data.md) | 기존 모델 전용 초기화 도구. `--confirm-reset`은 현재 차단되며, 인자 없이 현황만 조회한다. | [reset_recipe_data.py](../../recipe_recommender/tools/reset_recipe_data.py) |

## common

[Package Summary](api/common/README.md)

| 주요 모듈 | 책임 | 원본 소스 |
| --- | --- | --- |
| [database_manager](api/common/database_manager.md) | PostgreSQL connection pool 관리 모듈. | [database_manager.py](../../common/database_manager.py) |
| [document_reader](api/common/document_reader.md) | PDF/CSV 문서를 읽어 페이지별 텍스트 목록으로 만드는 도우미 모듈. | [document_reader.py](../../common/document_reader.py) |
| [neo4j_db_session](api/common/neo4j_db_session.md) | 외부에서 주입한 Neo4j 공식 드라이버로 Cypher를 실행하는 ``QuerySession`` 구현 모듈. | [neo4j_db_session.py](../../common/neo4j_db_session.py) |
| [postgres_db_session](api/common/postgres_db_session.md) | PostgreSQL용 ``QuerySession`` 구현 모듈. | [postgres_db_session.py](../../common/postgres_db_session.py) |
| [query_logger](api/common/query_logger.md) | PostgreSQL / Neo4j 세션이 함께 쓰는 쿼리 로그 포매터. | [query_logger.py](../../common/query_logger.py) |
| [query_session](api/common/query_session.md) | DB 종류와 무관한 동기식 쿼리 세션 계약(인터페이스). | [query_session.py](../../common/query_session.py) |
| [storage_manager](api/common/storage_manager.md) | Supabase Storage 이미지 업로드 모듈. | [storage_manager.py](../../common/storage_manager.py) |

## streamlit_app.py

Streamlit이 직접 실행하는 패키지 밖 모듈.

| 주요 모듈 | 책임 | 원본 소스 |
| --- | --- | --- |
| [streamlit_app](api/streamlit_app.md) | 냉장고 재료 추천 GraphRAG 웹 화면 (Streamlit). 모드 A 추천 / 모드 B 그래프 관계 탐색. 로컬 로그 ON에서 첫 추천의 PostgreSQL 상세를 추가 SELECT해 SQL을 기록한다. | [streamlit_app.py](../../streamlit_app.py) |

## 전체 클래스·함수 색인

- [Class Index (39개)](api/class_index.md)
- [Function Index (148개)](api/function_index.md)

## 기존 개발자 가이드와 실행 흐름

- [물리적 폴더 구조](01_directory_structure.md)
- [클래스 의존 관계](03_component_structure.md)
- [실제 호출 흐름](04_execution_flow.md)
- [데이터 전달 구조](05_data_flow.md)
- [업무 중심 상세 가이드](details/05_data_pipeline.md)

`sql/`, `data/`, `docs/`는 Python 패키지가 아니다. 과제 제출물(질문지·결과·검증 보고·노트북)은 [docs/assignment](../assignment/README.md)에 있다. SQL·Cypher 파일의 호출 경로는 Repository 상세와 실행 흐름을 참조한다.
