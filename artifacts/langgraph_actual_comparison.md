# 실제 그래프와 16장 비교

`CardGraphRAG(search=object(), candidate_search=object())`로 실제 인스턴스를 생성한 뒤 `rag.graph.get_graph().draw_mermaid()`를 호출했다. 그래프를 실행하지 않았고 DB와 LLM API를 호출하지 않았다. Mermaid 원문은 `langgraph_actual.mmd`에 그대로 저장했다. 로컬 Mermaid CLI로 SVG를 생성했으며 표시 크기와 색상 설정만 적용했다.

| 비교 항목 | 결과 |
|---|---|
| START → interpret | 일치. 16장은 START를 상단 실행 시작 영역에 표현한다. |
| interpret → retrieve / finish | 일치. 실제 Mermaid의 점선 두 개가 after_interpret 조건부 경로에 대응한다. |
| retrieve → answer / finish | 일치. 실제 Mermaid의 점선 두 개가 after_retrieve 조건부 경로에 대응한다. |
| answer → finish → END | 일치. 16장은 END를 finish 상자 안의 텍스트로 표현한다. |
| 정상 및 조기 종료 | 정상 경로와 두 조기 종료 경로가 모두 일치한다. |

표현 차이: 자동 출력은 조건의 구체적인 판단식이나 라우팅 함수 이름을 표시하지 않고 조건부 간선만 점선으로 표시한다. 16장은 조건과 State 전달 및 그래프 외부 처리까지 설명한다. START와 END는 자동 그래프에서 별도의 표식이고 16장에서는 텍스트로 표현한다. 16장 이미지 자체의 페이지 번호는 원본 보존을 위해 `16`으로 유지했다. 다른 기존 페이지의 분모와 목차 페이지 범위는 19장 기준으로 갱신했다.

소스: `src/card_benefit/payment_card/db_pipeline_origin_search/card_graphrag.py`의 `_build()` 및 `after_interpret()`, `after_retrieve()`.
