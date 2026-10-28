# GraphRAG 학습 샘플

이 패키지는 두 데이터베이스와 RAG 애플리케이션의 책임 분리를 단계별로 비교합니다. 모든 단계는 독립 실행되며 src/common의 QuerySession만 공유합니다.

## 세 단계 비교

| 기능 | Step 1 — Basic | Step 2 — Layered | Step 3 — LLM RAG |
|---|---|---|---|
| PostgreSQL 일반 등록·조회 | 직접 Session | Repository/Service | Repository/Service |
| pgvector 등록·유사도 검색 | 직접 Session | Repository/Service | Repository/Service |
| PostgreSQL 키워드 검색 | 없음 | 대소문자 무시 부분 문자열 | 대소문자 무시 부분 문자열 |
| 단순 Hybrid 검색 | 없음 | Keyword 우선 + Vector 결합, item_id 중복 제거 | Step 2 방식 |
| Neo4j 노드·관계 조회 | 직접 Session | Repository/Service | Repository/Service |
| Service/Repository 계층 | 없음 | 있음 | 있음 |
| LlmService | 없음 | 없음 | 별도 클래스 |
| 기본 실행 | DB 접속 없음 | DB 접속 없음 | DB/API 접속 없음 |
| 실제 LLM 선택 실행 | 없음 | 없음 | --run-db --use-openai 명시 시 |

## 추천 학습 순서와 실행

1. Step 1에서 Session 메서드, namespace.statement, Python dict/list, transaction과 Mapper를 읽습니다.
2. Step 2에서 동일한 등록·조회 동작을 Main → Service → Repository 계층으로 비교합니다.
3. Step 3에서 검색 결과를 Context/Prompt로 바꾸고 Mock 또는 선택한 ChatOpenAI 응답을 확인합니다.

~~~powershell
uv run python -m graph_rag_sample.step_01_basic.main
uv run python -m graph_rag_sample.step_02_layered.graph_rag_sample
uv run python -m graph_rag_sample.step_03_llm.graph_rag_sample
~~~

기본 명령은 DB 쓰기나 외부 API 호출을 하지 않습니다. 실제 소량 DB 실습은 각 단계에 --run-db를 붙여 실행합니다. Step 3의 OpenAI 호출은 --run-db --use-openai를 모두 줘야 활성화됩니다. 환경 변수와 실제 출력 예시는 각 단계 README를 참고하세요.

## 공통 샘플 데이터와 안전

각 단계는 Project A의 Python/Neo4j 예시와 같은 질문을 사용합니다. 3차원 고정 벡터는 거리 계산 실습용 좌표이며 실제 Embedding이 아닙니다. 각 DB 테스트 데이터에는 고유 test_run_id가 붙습니다. PostgreSQL 임시 테이블은 하나의 트랜잭션에서 생성·사용·삭제하며 Commit 시 제거됩니다. Neo4j는 해당 실행 ID가 포함된 데이터만 삭제합니다. 차량 매뉴얼, Supabase, 다른 프로젝트 데이터는 사용하지 않습니다.

## 테스트

~~~powershell
uv run python -m unittest discover -s src/graph_rag_sample/step_01_basic/tests -p "test_*.py"
uv run python -m unittest discover -s src/graph_rag_sample/step_02_layered/tests -p "test_*.py"
uv run python -m unittest discover -s src/graph_rag_sample/step_03_llm/tests -p "test_*.py"
~~~

기본 테스트는 오프라인 Mock 테스트입니다. 각 계층의 DB 통합 테스트는 RUN_GRAPH_RAG_SAMPLE_INTEGRATION=1일 때만 실행됩니다. 이는 실제 DB에 쓰는 명시적 opt-in입니다. 세 단계 상세 실행, 파일 역할, 예상 출력, 환경 변수는 하위 README에 있습니다.
