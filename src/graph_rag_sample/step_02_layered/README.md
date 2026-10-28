# Step 2 — Layered: Main → Service → Repository → Session

## 학습 목적과 호출 구조

Step 1의 직접 Session 호출을 자동차 검색 프로젝트와 같은 계층으로 나눕니다. RegisterService는 테스트 데이터 준비와 정리를, SearchService는 조회 조합을 담당합니다.

~~~text
GraphRagSample
 ├─ GraphRagSampleRegisterService
 └─ GraphRagSampleSearchService
      ├─ GraphRagSamplePostgresRepository → PostgresDbSession → graph_rag_sample.sql
      └─ GraphRagSampleNeo4jRepository    → Neo4jDbSession   → graph_rag_sample.cypher
~~~

Main은 Service만 호출합니다. Service는 Repository를 호출하고, Repository는 QuerySession의 공통 메서드와 이름 있는 Mapper statement만 사용합니다. PostgreSQL과 Neo4j의 쿼리 문법은 각 Mapper에 남아 있습니다.

## 파일별 역할

- graph_rag_sample.py: 환경설정, Driver/Session과 계층 객체 생성, 결과 출력.
- graph_rag_sample_register_service.py: 테스트 데이터 등록 → 조회 → 해당 test_run_id 데이터 삭제 → 잔여 확인.
- graph_rag_sample_search_service.py: 일반·키워드·벡터·Hybrid·그래프 조회.
- graph_rag_sample_postgres_repository.py: SQL Mapper와 PostgreSQL QuerySession 호출.
- graph_rag_sample_neo4j_repository.py: Cypher Mapper와 Neo4j QuerySession 호출.
- graph_rag_sample.sql, graph_rag_sample.cypher: 외부 Named Query.
- tests/test_layered.py: Mapper, Repository, Hybrid Mock 테스트와 명시적 통합 테스트.

## 검색 예제

PostgreSQL 임시 테이블에 같은 item_id를 가진 두 문서와 벡터를 준비합니다. 고정 벡터 Python [1, 0, 0], Neo4j [0.8, 0.2, 0]은 의미 임베딩이 아닌 3차원 거리 계산 예제입니다.

키워드 검색은 lower()와 position()을 사용한 대소문자 무시 부분 문자열 조건입니다. 단순 Hybrid는 키워드 결과를 먼저 추가하고, 벡터 결과를 뒤에 더하면서 item_id 중복을 제거합니다. 각 행의 source 필드에서 keyword/vector 출처를 볼 수 있습니다. 점수 결합, RRF, reranking은 하지 않습니다.

## 실행

기본 실행은 DB에 연결하거나 쓰지 않습니다.

~~~powershell
uv run python -m graph_rag_sample.step_02_layered.graph_rag_sample
~~~

DB 등록·조회·삭제를 직접 확인하려면 .env 또는 환경변수를 설정하고 명시적으로 실행합니다.

~~~powershell
uv run python -m graph_rag_sample.step_02_layered.graph_rag_sample --run-db
~~~

필요 환경 변수: DB_URL, NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD. NEO4J_DATABASE는 선택입니다. 값은 출력되지 않습니다. mapper_root는 이 Main 파일 위치에서 구하므로 다른 CWD에서도 Mapper를 찾습니다.

## 트랜잭션과 데이터 정리

PostgreSQL 임시 테이블은 ON COMMIT DROP입니다. 같은 transaction 블록 안에서 임시 테이블 생성, 등록, 일반·키워드·벡터·Hybrid 검색, test_run_id 행 삭제와 잔여 확인을 끝냅니다. Commit 시 임시 테이블도 없어집니다. Neo4j는 다른 트랜잭션에서 실행 ID가 붙은 노드·관계만 만들고 삭제합니다. 예외가 블록 밖으로 전달되면 Session이 Rollback합니다.

예상 결과는 일반 행 2개, Python 키워드 1개, 벡터 2개, 관계 2개이며, 정리 후 PostgreSQL 테스트 행 0개와 Neo4j 테스트 노드·관계 0개입니다. 이는 예시 기대값이며 실제 DB 실행 결과는 아닙니다.

예상 출력 예시:

~~~text
PostgreSQL keyword: [item_id=python, source=keyword]
PostgreSQL hybrid: [python/keyword, neo4j/vector]
PostgreSQL remaining rows: 0
Neo4j remaining nodes/relationships: 0 / 0
~~~

## 오프라인 테스트

~~~powershell
uv run python -m unittest discover -s src/graph_rag_sample/step_02_layered/tests -p "test_*.py"
~~~

실 DB 통합 테스트는 RUN_GRAPH_RAG_SAMPLE_INTEGRATION=1을 설정했을 때만 포함됩니다. Step 2는 LLM, 실제 임베딩 API, Agent, 고급 Hybrid 검색을 사용하지 않습니다.
