# Step 3 — LLM RAG: 검색 근거에서 답변 생성

## 학습 목적과 호출 구조

Step 2와 같은 DB 계층에 별도 GraphRagSampleLlmService를 더합니다.

~~~text
GraphRagSample Main
 ├─ RegisterService + SearchService → PostgreSQL/Neo4j Session → Mapper
 └─ LlmService
      검색 결과 → 출처가 있는 Context → ChatPromptTemplate
      → Mock Runnable 또는 ChatOpenAI → StrOutputParser → 답변
~~~

GraphRagSample.ask()는 먼저 양쪽 DB 트랜잭션을 마치고 테스트 데이터를 정리합니다. 그 뒤 materialized 검색 결과를 LlmService로 전달합니다. OpenAI 응답을 기다리는 동안 DB 트랜잭션을 열어 두지 않습니다.

## 파일별 역할

Step 2의 Main, RegisterService, SearchService, 두 Repository 및 두 Mapper를 독립 폴더에 복제해 단계 간 import 의존성을 없앴습니다. Step 3 변경점은 graph_rag_sample_llm_service.py와 Main의 ask 흐름입니다. tests/test_llm.py는 Step 2 검색 검증에 더해 Context, Prompt, Mock 출력, 검색 결과 없음, 트랜잭션 종료 순서를 검사합니다.

## 검색 근거와 Prompt

동일한 샘플 데이터, 질문, 3차원 고정 벡터를 씁니다. Context에는 다음 출처가 구분됩니다.

- PostgreSQL Keyword: 실제 content 문자열.
- PostgreSQL Vector: DB가 반환한 항목명과 유사도.
- Neo4j Graph: 조회된 프로젝트 → 관계 → 기술 이름.

검색 결과가 없으면 Context에 No retrieved evidence가 들어가며 Prompt는 근거가 없는 사실을 추측하지 않도록 지시합니다. Prompt 원문과 답변은 실행 출력에서 구분해 볼 수 있습니다.

고정 벡터는 검색 알고리즘 설명용 좌표이며 의미 임베딩이 아닙니다. 현재 흐름은 질문 → 미리 정한 고정 3차원 검색 벡터 → pgvector입니다. 향후 실제 RAG의 질문 → Embedding Model → pgvector와 다릅니다.

Mock 모드 예상 출력의 핵심:

~~~text
Question: What technologies does Project A use?
Context: [PostgreSQL - Keyword] ... [PostgreSQL - Vector] ... [Neo4j - Graph] ...
Answer: Mock 답변: 검색 근거에서 Project A가 Python과 Neo4j를 사용하는 것을 확인했습니다.
LLM mode: mock
~~~

## 실행과 LLM 설정

기본은 오프라인 안내 출력이며 어떤 DB/API도 호출하지 않습니다.

~~~powershell
uv run python -m graph_rag_sample.step_03_llm.graph_rag_sample
~~~

실제 DB 검색과 기본 Mock LLM을 실행하려면 명시적으로 DB 쓰기 옵션을 줍니다.

~~~powershell
uv run python -m graph_rag_sample.step_03_llm.graph_rag_sample --run-db
~~~

실제 OpenAI 호출을 선택하려면 다음 변수와 두 번째 명시 옵션을 함께 줍니다.

~~~powershell
$env:OPENAI_API_KEY = "..."
$env:OPENAI_MODEL = "gpt-4o-mini"
uv run python -m graph_rag_sample.step_03_llm.graph_rag_sample --run-db --use-openai
~~~

OPENAI_API_KEY는 출력하지 않습니다. 실제 모델은 최대 256 토큰 응답으로 설정했습니다. 키가 없거나 API가 실패하면 예외를 숨기지 않고 명령이 실패합니다. --use-openai 없이 실행하면 결정적인 Mock Runnable이 기본이며 외부 비용이 발생하지 않습니다.

필요 DB 변수는 Step 2와 같습니다: DB_URL, NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD. Session의 Mapper 범위는 Step 3 폴더 하나입니다.

## 테스트

~~~powershell
uv run python -m unittest discover -s src/graph_rag_sample/step_03_llm/tests -p "test_*.py"
~~~

기본 테스트는 DB/OpenAI 호출이 없습니다. DB 통합 테스트는 RUN_GRAPH_RAG_SAMPLE_INTEGRATION=1일 때만 포함됩니다. 테스트 후 생성 데이터는 해당 run ID 범위에서만 정리됩니다.

## 이번 단계에서 제외한 기능

실제 Embedding Model, 스트리밍, Agent/Tool Calling, LangGraph, 대화 기록, Text2Cypher, Reranking, 이미지 검색은 포함하지 않습니다.
