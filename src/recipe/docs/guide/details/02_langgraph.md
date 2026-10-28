# LangGraph와 답변 검증 상세

[메인](../README.md) · [실행 흐름](../04_execution_flow.md) · [데이터 흐름](../05_data_flow.md)

원본: [pantry_graphrag.py](../../../recipe_recommender/pantry_graphrag.py). `PantryState`는 `TypedDict(total=False)`로 선언한 dict 타입이다. 필드: `question: str`, `limit: int`, `sort: str`, `terms: list[str]`, `term_source: str`, `result: PantryResult`, `answer: dict`, `warnings: list[str]`. `total=False`는 모든 키가 처음부터 필수인 것은 아니라는 타입 표기다. Node는 전체 State를 받아 **변경할 키만 있는 dict**를 반환한다.

```mermaid
flowchart LR
 START --> interpret --> retrieve --> answer --> END
```

조건 Edge는 없다. [`PantryGraphRAG.__init__`/`_build()`](../../../recipe_recommender/pantry_graphrag.py)는 Service·LLM을 필드에 저장하고 `StateGraph(PantryState)`에 bound method 셋을 Node로 등록한다. `compile()`은 실행 가능한 그래프를 만든다. [`run(question, limit=5, sort='coverage')`](../../../recipe_recommender/pantry_graphrag.py)는 `graph.invoke(initial_dict)`를 호출해 최종 State를 반환한다. Java 메서드 체인과 비슷하게 이해할 수 있지만, Node 간 호출은 `interpret()`가 `retrieve()`를 직접 호출하는 방식이 아니라 컴파일된 그래프의 Edge가 결정한다.

| Node/도우미 | 입력 → 반환 | 내부 순서·예외 |
| --- | --- | --- |
| [`interpret(state)`](../../../recipe_recommender/pantry_graphrag.py) | `PantryState` → `{terms,term_source,warnings}` | `split_terms(question)` → 각 항목이 10자 이하·공백 없음이면 `rule`. 문장이면 `IngredientTerms` 구조화 LLM 호출 → `terms_in_question`으로 원문 포함 확인. 실패/빈 결과는 `_interpret_without_llm`. LLM 예외만 잡아 경고; 어휘 DB 오류는 전파. |
| [`_interpret_without_llm(question,rule_terms,warnings)`](../../../recipe_recommender/pantry_graphrag.py) | 문자열·목록 → State 일부 | `service.vocabulary()` → `scan_vocabulary_terms`. 발견 시 `vocabulary`, 아니면 `rule`. 어휘 스캔은 2글자 이상 DB 이름·별칭을 긴 순서로 찾는다. |
| [`retrieve(state)`](../../../recipe_recommender/pantry_graphrag.py) | State → `{result: PantryResult}` | `service.recommend(state['terms'], limit, sort)` 직접 호출. DB 예외를 여기서 처리하지 않는다. |
| [`answer(state)`](../../../recipe_recommender/pantry_graphrag.py) | State → `{answer,warnings}` | 우선 `grounded_summary/reason` 생성. 추천 없음·LLM 없음이면 대체값. 그 외 `build_context` → JSON 프롬프트 → `PantryAnswer` 구조화 LLM → `validate_answer`. LLM 호출 예외는 `failed`, `llm_error`에 예외 **타입명**만 저장. |
| [`create_llm()`](../../../recipe_recommender/pantry_graphrag.py) | 없음 → `ChatOpenAI` 또는 `None` | API 키가 있을 때만 import/생성. 모델은 `OPENAI_MODEL` 또는 `DEFAULT_MODEL`; timeout 60, max_retries 1. 실제 API 호출은 Node의 `invoke` 시점. |

`IngredientTerms(BaseModel)`는 `terms: list[str]`; `PantryAnswer(BaseModel)`는 `summary: str`, `recipes: list[RecipeReason]`; `RecipeReason`은 `rcp_id`와 `reason` 문자열이다. `with_structured_output(...).invoke(prompt)`는 이 형태의 파싱 결과를 요청한다. Pydantic 클래스는 SQL row나 LangGraph State와 별개다.

[`validate_answer(raw,result,vocabulary)`](../../../recipe_recommender/pantry_graphrag.py)는 `(answer: dict, warnings: list[str])`를 반환한다. 먼저 `rcp_id`가 추천 목록에 없는 이유를 버리고 중복 ID를 건너뛴다. 레시피별 허용 집합은 전체 재료·별칭과 보유 재료·입력어다. `foreign_ingredients`는 레시피명을 가리고 허용어를 지운 뒤 **DB 어휘 중 2글자 이상** 남은 이름을 찾아 해당 이유를 `grounded_reason`으로 교체한다. 누락된 이유도 대체한다. 요약은 전체 추천의 허용어를 기준으로 검사하고 빈 요약도 대체한다. 하나라도 대체되면 `partial`, 아니면 `ok`다. `terms_in_question`은 추출어가 사용자 문장에 있는지 공백 없는 정규화 문자열로 검사한다.

제약: 검증은 DB 어휘와 텍스트 포함 여부를 비교한다. DB 어휘에 없는 재료 표현이나 근거 밖 조리 주장 전체를 탐지하는 의미 검증으로 확대 해석하면 안 된다. `answer()`가 추천이 없는 경우 LLM 객체가 있으면 `llm_status='skipped'`를 반환할 수 있다. 현재 UI는 이 상태의 알림을 별도로 표시하지 않는다.
