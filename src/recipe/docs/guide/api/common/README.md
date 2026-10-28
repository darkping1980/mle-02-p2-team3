# common Package Summary

[API 전체 목차](../README.md) · [파일 인덱스](../../02_file_structure.md)

PostgreSQL·Neo4j 세션, 쿼리 로그와 공통 도우미를 담는 실제 Python 패키지. 모듈 7개를 다룬다.

## Module Summary

| 모듈 상세 | 소스 | 역할 |
| --- | --- | --- |
| [database_manager](database_manager.md) | [database_manager.py](../../../../common/database_manager.py) | PostgreSQL connection pool 관리 모듈. |
| [document_reader](document_reader.md) | [document_reader.py](../../../../common/document_reader.py) | PDF/CSV 문서를 읽어 페이지별 텍스트 목록으로 만드는 도우미 모듈. |
| [neo4j_db_session](neo4j_db_session.md) | [neo4j_db_session.py](../../../../common/neo4j_db_session.py) | 외부에서 주입한 Neo4j 공식 드라이버로 Cypher를 실행하는 ``QuerySession`` 구현 모듈. |
| [postgres_db_session](postgres_db_session.md) | [postgres_db_session.py](../../../../common/postgres_db_session.py) | PostgreSQL용 ``QuerySession`` 구현 모듈. |
| [query_logger](query_logger.md) | [query_logger.py](../../../../common/query_logger.py) | PostgreSQL / Neo4j 세션이 함께 쓰는 쿼리 로그 포매터. |
| [query_session](query_session.md) | [query_session.py](../../../../common/query_session.py) | DB 종류와 무관한 동기식 쿼리 세션 계약(인터페이스). |
| [storage_manager](storage_manager.md) | [storage_manager.py](../../../../common/storage_manager.py) | Supabase Storage 이미지 업로드 모듈. |

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [DatabaseManager](database_manager.md#databasemanager) | 클래스 | DatabaseManager는 psycopg connection pool을 관리하고 대여한 연결을 제공한다. |
| [DocumentReader](document_reader.md#documentreader) | 클래스 | 문서 파일 읽기 및 전처리 관리 |
| [_NotCypherLiteral](neo4j_db_session.md#_notcypherliteral) | 예외 클래스 | 파라미터 값을 정확한 Cypher 리터럴로 표현할 수 없을 때 내부적으로 사용하는 예외. |
| [Neo4jDbSession](neo4j_db_session.md#neo4jdbsession) | 클래스 | ``namespace.statement`` 이름의 Cypher를 주입받은 드라이버로 실행한다. |
| [PostgresDbSession](postgres_db_session.md#postgresdbsession) | 클래스 | SQL mapper를 등록하고 statement ID로 동기식 쿼리를 실행한다. |
| [QueryLogger](query_logger.md#querylogger) | 클래스 | 쿼리/배치/결과/트랜잭션 로그를 일관된 형식으로 출력한다. |
| [QuerySession](query_session.md#querysession) | 클래스 | DB별 쿼리 세션이 공통으로 제공하는 최소 계약. |
| [StorageManager](storage_manager.md#storagemanager) | 클래스 | Supabase Storage 이미지 업로드 및 URL 조회 관리 |

## Data Model Summary

이 패키지에는 최상위 TypedDict·Pydantic 모델·dataclass DTO가 없다. DB 세션과 로그 객체의 주요 속성은 각 클래스의 Field Summary에서 확인한다.

## Function Summary

| 모듈 함수 | 설명 |
| --- | --- |
| [database_manager._configure_connection](database_manager.md#function-_configure_connection) | 새 physical connection에 pgvector 어댑터를 등록하고 idle 상태로 둔다. |
| [database_manager.snake_to_camel](database_manager.md#function-snake_to_camel) | 밑줄로 구분된 컬럼명을 camelCase 문자열로 변환한다. |
| [database_manager.camel_dict_row](database_manager.md#function-camel_dict_row) | psycopg 행을 camelCase 키를 가진 dict로 만드는 row factory를 반환한다. |
| [neo4j_db_session._driver_types](neo4j_db_session.md#function-_driver_types) | 로그 표시에 필요한 드라이버 값 타입을 지연 import해 반환한다. neo4j가 없으면 빈 tuple로 채운다. |
| [neo4j_db_session._cypher_name](neo4j_db_session.md#function-_cypher_name) | 식별자 규칙에 맞지 않는 이름을 백틱으로 감싼다. 예: ``a b`` → ```a b```. |
| [neo4j_db_session._cypher_string](neo4j_db_session.md#function-_cypher_string) | Python 문자열을 작은따옴표 Cypher 문자열 리터럴로 이스케이프한다(로그 표시용). |
| [neo4j_db_session._cypher_literal](neo4j_db_session.md#function-_cypher_literal) | 드라이버 파라미터 값을 ``:param`` 줄에 쓸 Cypher 표현식 문자열로 바꾼다. |
| [neo4j_db_session.render_cypher_params](neo4j_db_session.md#function-render_cypher_params) | 로그 출력용으로 ``query`` 앞에 Neo4j Browser의 ``:param`` 줄을 붙인 문자열을 만든다. |
| [neo4j_db_session.format_graph_value](neo4j_db_session.md#function-format_graph_value) | 결과 표 로그용으로 그래프 값을 짧은 문자열로 만든다. 반환 데이터 자체는 바꾸지 않는다. |
| [neo4j_db_session._format_result_cell](neo4j_db_session.md#function-_format_result_cell) | 결과 표 셀 변환 함수. 최상위 문자열은 PostgreSQL 표와 같게 따옴표 없이 둔다. |
| [neo4j_db_session.summary_counters](neo4j_db_session.md#function-summary_counters) | 드라이버 ``ResultSummary.counters`` 중 0이 아닌 정수 값만 dict로 반환한다. |
| [neo4j_db_session._format_counters](neo4j_db_session.md#function-_format_counters) | counter dict를 ``{nodes_created: 1, properties_set: 2}`` 형식 문자열로 만든다. |
| [neo4j_db_session._server_ms](neo4j_db_session.md#function-_server_ms) | summary의 서버 측 시간 속성(ms)을 정수일 때만 반환하고, 없으면 ``None`` 을 반환한다. |
| [query_logger._normalize_key](query_logger.md#function-_normalize_key) | 민감 키 비교용으로 소문자화하고 영숫자만 남긴다. 예: ``"DB_Password"`` → ``"dbpassword"``. |
| [query_logger.is_numeric_sequence](query_logger.md#function-is_numeric_sequence) | bool을 제외한 int/float만 담긴 긴 list/tuple인지 확인한다 (벡터 판정 기준). |

## 관련 가이드

- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
