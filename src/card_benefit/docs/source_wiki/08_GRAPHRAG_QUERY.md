# 8. GraphRAG 조회

[목차](README.md) · [Neo4j 동기화](07_NEO4J_SYNC.md)

<details><summary>▼ 8.1 UI → 그래프 생성 → 실행</summary>

Streamlit 진입은 [`streamlit_app.py`](../../payment_card/db_pipeline_origin_search/streamlit_app.py). `get_pipeline(search_mode)`가 캐시된 검색 객체/LLM과 [`CardGraphRAG`](../../payment_card/db_pipeline_origin_search/card_graphrag.py)를 조합한다. 질문 제출 시 `.run(question)`을 부르고 State를 세션에 저장한다. 동일 질문/모드 결과 재사용 등 UI 동작은 화면 코드에 있으며 파이프라인 판정을 수정하지 않는다.

<details><summary>▼ 8.1.1 CardState와 LangGraph 순서</summary>

소스 [`card_graphrag.py`](../../payment_card/db_pipeline_origin_search/card_graphrag.py), [`CardState`](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline_origin_search/card_graphrag.py#L269), [`CardGraphRAG`](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline_origin_search/card_graphrag.py#L1319).

- `_initial_state()`가 request ID, 질문, 검색 모드, 초기 결과 필드를 구성한다.
- `_build()`가 StateGraph에 `interpret → (retrieve 또는 finish) → (answer 또는 finish) → finish`를 연결한다. 조건 분기는 각 `after_*()`가 상태/유형을 보고 고른다.
- `run()`은 초기 State에 대해 compiled graph를 실행하고 완료 State를 반환한다. `_step()`은 노드 호출을 추적하고 실패 상태/시간 정보를 관리한다.
- State의 키는 `CardState` 정의를 기준으로 하며 노드가 반환한 일부 누적 필드는 reducer를 사용한다. 실제 입출력은 `interpret`, `retrieve`, `answer` 함수의 반환 dict를 확인한다.
- exact graph edge와 분기 코드는 [`_build()`](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline_origin_search/card_graphrag.py#L1340), [`run()`](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline_origin_search/card_graphrag.py#L1366), [`interpret()`](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline_origin_search/card_graphrag.py#L1441), [`retrieve()`](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline_origin_search/card_graphrag.py#L1551), [`answer()`](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline_origin_search/card_graphrag.py#L1626).
</details>
</details>

<details><summary>▼ 8.2 interpret 노드와 검색 모드</summary>

`interpret()`는 Neo4j `list_catalog()`로 카드/혜택/상품 항목/공통 혜택 목록을 읽고, LLM structured output으로 질문 유형 및 대상 ID를 고른다. 프롬프트는 `INTERPRET_PROMPT`, 출력 schema는 소스의 Pydantic model이다. 목록 밖 ID는 허용하지 않는 후처리/검증 경로가 있다.

| 모드 | 구현상 후보 획득 |
|---|---|
| A | Neo4j 전체 catalog 기반. PostgreSQL `BenefitSearchService` 없음 |
| B | PostgreSQL 벡터 임베딩 후보를 보조 검색에 사용 |
| C | PostgreSQL keyword 검색과 벡터 검색 결과를 결합하는 hybrid 후보 경로 |

B/C의 SQL은 [`embedding_repository.sql`](../../payment_card/db_pipeline/embedding_repository.sql), Python은 [`benefit_search_service.py`](../../payment_card/db_pipeline_origin_search/benefit_search_service.py). 정확한 score 결합/중복 제거는 해당 서비스 구현을 기준으로 한다. 사용자 요청으로 LLM은 호출하지 않았다.
</details>

<details><summary>▼ 8.3 retrieve — 후보 → 상세 → 근거</summary>

`retrieve()`는 해석 결과에서 대상 후보를 만들고 필요한 경우 `BenefitSearchService`로 PostgreSQL 보조 후보/상세를 가져온다. Neo4j `candidate_relations()`로 후보 혜택과 규칙의 관계/대상 문구를 확인하고, 각 그래프 key에 `get_detail()`을 호출한다. detail은 context, rules, conditions, limits, evidence section 순이다.

- Neo4j SQL 아닌 조회: `graph_questions.cypher` mapper의 `catalog`, `item_catalog`, `common_catalog`, `candidate_relations`, `benefit_context`, `benefit_rules`, `benefit_conditions`, `benefit_limits`, evidence statement.
- PostgreSQL 검색: 모드 B/C 후보 검색과 Neo4j에 상세가 없는 일부 혜택 fallback. SQL은 embedding mapper의 `search_*`, `keyword_*`, `select_*_detail`, `select_*_evidence`.
- 결과가 없거나 상세/근거 경로가 실패하면 후속 route가 answer를 건너뛰거나 불가/오류 상태를 선택한다. 상태 코드/route는 `after_retrieve()`를 참조한다.
</details>

<details><summary>▼ 8.4 answer와 LLM 호출</summary>

`answer()`는 retrieve 결과를 JSON context로 `ANSWER_PROMPT`에 넣고 구조화 응답을 요청한다. 응답 schema에는 답변 텍스트, 결론, 근거가 붙은 points, 불확실 항목, 답변 불가 이유 등이 포함된다. LLM helper는 `_call_llm()`이며 API 미설정, timeout/예외, parse/schema 문제는 결과 상태로 변환된다. 생성 후 [9장](09_ANSWER_VALIDATION.md)의 검증을 통과해야 사용자 문장으로 채택된다.
</details>

[답변 검증 →](09_ANSWER_VALIDATION.md) · [실행 참조 →](10_EXECUTION_REFERENCE.md)

