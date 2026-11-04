# 9. 답변 검증

[목차](README.md) · [GraphRAG 조회](08_GRAPHRAG_QUERY.md)

<details><summary>9.1 검증 단계와 결과 상태</summary>

검증 구현은 [`card_graphrag.py`](../../payment_card/db_pipeline_origin_search/card_graphrag.py)의 `verify_interpret()`, `verify_retrieve()`, `verify_answer()`, answer 생성 후 검증 경로다. 최종 상태는 `ANSWERED`, `PARTIAL`, `NOT_ANSWERABLE`, `ERROR` 계열로 UI가 표시한다. 내부 status를 화면 문구로 매핑하는 것은 [`streamlit_app.py`](../../payment_card/db_pipeline_origin_search/streamlit_app.py)의 presentation 로직이다.

<details><summary>9.1.1 Point 근거와 사실 검증</summary>

- 생성 스키마는 각 사실(point)에 `evidence_id`를 붙이도록 요구한다. evidence는 retrieve에서 받은 대상 혜택/근거 집합에 속해야 한다.
- 인용 quote, 숫자/금액, 대상/혜택 관계가 근거 및 구조화 데이터와 맞는지 검사한다. 문장 단위로 검증 실패한 사실은 답변에서 제외하거나 `PARTIAL` 결과로 제한한다.
- 계산형 표현은 확인된 같은 단위 값에서 계산 가능한 범위로만 허용한다. 검색 결과 밖 우선순위/중복 적용 규칙을 만들어내지 않는다.
- 근거를 제시할 수 없는 문장은 채택하지 않는다. 근거 자체가 없거나 질문을 풀 수 없는 경우에는 거부/제한 이유를 둔다.
- 소스: [verify_answer() 로컬 (L1396)](../../payment_card/db_pipeline_origin_search/card_graphrag.py#L1396) · [GitHub 기준 커밋](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline_origin_search/card_graphrag.py#L1396), [ANSWER_PROMPT 로컬](../../payment_card/db_pipeline_origin_search/card_graphrag.py).
</details>
</details>

<details><summary>9.2 답변 거부·부분 답변 경로</summary>

- 해석 불가/지원 범위 밖: target이 없거나 UNKNOWN이면 retrieval/answer를 skip하도록 edge가 분기한다.
- 근거 부족: evidence가 비어 있거나 point를 grounding할 수 없으면 답변 불가 결과를 만든다.
- LLM 실패: 호출/파싱 오류는 정상 답변으로 취급하지 않고 오류 또는 fallback 결과에 기록한다.
- 검증 실패 문장: 통과 문장만 유지할 수 있어 부분 답변이 된다. 연회비처럼 `item_data`에서 프로그램이 만든 고정 정보는 LLM 문장과 별도로 표시될 수 있다.
- UI 텍스트 정리는 내부 상태 표현을 숨기거나 고객용 문구로 바꾸며 State의 검증 판정을 수정하지 않는다.
</details>

<details><summary>9.3 상태와 운영 DB 검증</summary>

답변 검증은 조회 시점에 검색된 근거/구조화 데이터에 대한 로직이다. 운영 자료 전체의 정합성이나 PostgreSQL/Neo4j 동기화 완전성을 증명하지 않는다. 통합 검증은 기존 [조회 검증 가이드](../guide/CARD_GRAPHRAG_QUERY_VALIDATION_DETAIL.md)도 참고하되 현재 구현과 차이가 있으면 소스를 우선한다.
</details>

[조회로 돌아가기](08_GRAPHRAG_QUERY.md) · [목차](README.md)

