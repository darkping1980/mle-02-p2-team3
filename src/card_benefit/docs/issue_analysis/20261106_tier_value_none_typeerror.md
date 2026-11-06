# GraphRAG 오류 분석 — tier.value None TypeError

## 1. 이슈 개요

비교 질문 처리 중 Python이 `float(None)`을 실행해 요청 전체가 중단되는 오류다. 직접적인 오류 지점은 [card_graphrag.py](../../payment_card/db_pipeline_origin_search/card_graphrag.py)의 `tier_token()`이다. 다만 `tier_token()`이 고립된 채 잘못 호출된 것이 아니라, 실제 Neo4j 규칙 조회 결과에 지급 값이 없는 규칙이 포함될 수 있는데 검증 로직이 이를 숫자라고 가정하는 것이 근본 원인이다.

2026-11-06 현재 저장소 기준 핵심 위치는 다음과 같다.

| 함수 | 줄 | 역할 |
|---|---:|---|
| `rule_conflicts()` | 984–1001 | 혜택 규칙과 실적 구간으로 비교 검증용 tier 구성 |
| `tier_token()` | 1011–1013 | 지급 단위·값을 `(kind, float(value))`로 변환 |
| `tier_label()` / `tier_text()` | 1016–1026 | 구간을 사람이 읽는 문구로 생성 |
| `distorts_tier()` | 1106–1129 | 문장에 쓴 구간 기준액과 지급액 관계 검증 |
| `picks_single_tier()` | 1138–1147 | 복수 구간 중 일부만 답했는지 확인 |
| `tier_is_quoted()` / `tier_answer()` | 1160–1193 | 원문에 구간이 있는지 확인하고 프로그램 답변 구성 |
| `validate_answer()` | 1209 이후, 특히 1282–1308 | LLM 문장을 검증하고 유효 답변 생성 |
| `answer_text_problem()` | 1391 이후, 특히 1408–1410 | 답변 문구의 자체 검증 |

## 2. 오류 발생 환경

제보된 발생 환경은 실제 배포 Streamlit과 로컬 Streamlit, Neo4j 단일 검색 모드 `N`이다. 애플리케이션은 [streamlit_app.py](../../payment_card/db_pipeline_origin_search/streamlit_app.py)에서 `SEARCH_MODE = "N"`을 고정하고, `get_pipeline()`에서 Neo4j 검색 객체를 사용한다(98–119행, 질문 제출·실행 383–445행).

PostgreSQL `db_pipeline.app_log`는 읽기 전용으로 확인했다. ID 194–198의 다섯 행은 동일 질문, `error_text = "검색 실행 중 처리 오류"`, 상세 실행 로그에 `card.detail_batch` 조회 포함을 기록하고 있다. 로그에는 Python traceback이 저장되어 있지 않아 예외 위치 자체는 사용자가 제공한 로컬 traceback 및 현재 소스 호출 경로와 대조했다. app_log가 남기는 오류는 안전 요약이므로 실제 예외 메시지를 대신하지 않는다.

## 3. 재현 질문 및 증상

> 휴대전화 요금과 정기 구독을 자동납부하는 고객에게 더 심플 하나카드와 카드의정석2 DAILY의 적용 가능 할인과 통합 한도를 비교해 줘.

화면에는 “일시적인 문제로 답변을 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.”가 표시되고, DB 오류 필드는 “검색 실행 중 처리 오류”를 기록한다. 사용자가 제공한 로컬 Traceback은 `TypeError: float() argument must be a string or a real number, not 'NoneType'`이며 호출 순서는 `answer() → validate_answer() → distorts_tier() → tier_token()`이다.

## 4. 실제 오류 로그와 Traceback

확인된 예외는 다음 변환에서 발생한다.

```python
def tier_token(tier: dict) -> tuple[str | None, float]:
    return UNIT_KINDS.get(tier["unit"]), float(tier["value"])
```

`unit`이 `None`이면 `UNIT_KINDS.get()`은 `None`을 반환할 수 있고, 이는 이 줄에서 오류가 아니다. 오류는 `tier["value"] is None`일 때 `float(None)`을 실행하는 부분이다.

Traceback의 현재 소스상 줄 위치는 다음과 같다.

```text
card_graphrag.py: answer()             1840행  validate_answer(...) 호출
card_graphrag.py: validate_answer()    1282행  distorts_tier(text, conflicts)
card_graphrag.py: distorts_tier()      1112행  tier_token(tier) 목록 구성
card_graphrag.py: tier_token()         1013행  float(tier["value"])
```

DB의 다섯 로그 행은 질문 처리와 상세 Neo4j 조회가 시작된 사실 및 요약 오류를 입증하지만, `tier_token()`에 들어간 실제 dictionary는 담지 않는다. 실제 사전 값은 아래 Neo4j 읽기 전용 조회에서 별도로 확인했다.

## 5. 전체 실행 흐름 및 호출 관계

```mermaid
flowchart TD
    A[Streamlit 질문 제출] --> B[CardGraphRAG.run / graph.invoke]
    B --> C[interpret: 카드·혜택 식별 및 Neo4j key 결정]
    C --> D[retrieve: get_details로 Neo4j 규칙·조건·근거 조회]
    D --> E[benefit_context: value_num, value_unit_cd 매핑]
    E --> F[rule_conflicts: tier 생성]
    F --> G[answer: LLM 구조화 응답]
    G --> H[validate_answer]
    H --> I[distorts_tier]
    I --> J[tier_token]
    J -->|float(None) TypeError| K[LangGraph invoke 예외 전파]
    K --> L[Streamlit 최상위 예외 처리 및 일반 오류 표시]
```

`CardGraphRAG._build()`(1477행 부근)는 `START → interpret → retrieve → answer → finish → END` 조건부 그래프를 구성한다. `run()`(1503행)은 `graph.invoke()`를 호출한다. `after_interpret()`가 조회 대상이 있으면 `retrieve`로 보내고, `after_retrieve()`는 오류가 없고 근거가 있을 때 `answer`로 보낸다. `answer()`(1774행)는 검색 자료로 LLM context를 만들고 LLM의 구조화 결과를 받은 뒤, 1840행에서 `validate_answer()`를 직접 호출한다.

`answer()`의 `try/except`는 `_call_llm()` 호출을 감싸지만, 그 다음의 `validate_answer()`는 그 블록 바깥에 있다. 따라서 검증 중 발생하는 `TypeError`를 `answer()`의 LLM 오류 처리로 바꾸지 않는다. LangGraph 호출은 노드 예외를 최종 State의 `error`로 변환하지 않고 호출자에게 전파한다. Streamlit의 바깥 `try/except`가 이를 받아 일반 화면 오류를 표시한다. 이 예외는 정상적인 `answer` 반환이 아니므로 `finish()`의 요약 처리까지 도달하지 않는다.

현재 작업 트리의 `streamlit_app.py`에는 `traceback.print_exc()`를 추가한 미커밋 변경이 이미 있다. 이 분석에서는 해당 상태를 그대로 관찰했으며 파일은 수정하지 않았다.

## 6. 직접적인 오류 발생 코드

`validate_answer()`는 답변 포인트별로 여러 선행 검증을 통과한 다음 1282행에서 `distorts_tier()`를 호출한다. 이 호출은 특정 문장에서 tier 값을 먼저 사용해 보겠다는 조건문 안에 있지 않다. 즉 포인트가 비어 있지 않고, 상태 문장이 아니며, 유효한 근거 ID가 있고, 선행 값 검증 등을 통과하면 해당 문장 내용과 무관하게 tier 검증을 시작한다.

`distorts_tier()`는 비교 대상으로 다음과 같이 tier 목록을 만든다.

```python
tiers = [tier for conflict in conflicts for tier in conflict["tiers"]
         if tier["min_amt"] is not None]
minimums = {float(tier["min_amt"]) for tier in tiers}
values = {tier_token(tier) for tier in tiers}
```

여기서는 `min_amt`가 있는 tier만 걸러내지만 `value`가 있는지는 확인하지 않는다. 따라서 `min_amt`가 숫자이고 `value`가 `None`인 tier는 `tier_token()`으로 전달되어 오류를 낸다. 주어진 Traceback의 호출 순서와 정확히 일치한다.

## 7. Neo4j 규칙 데이터 전달 구조

검색은 다음 순서로 값을 만든다.

1. `graph_questions.cypher`의 `benefit_rules` 조회는 `(b:dp_card_bnft)-[:dp_has_rule]->(r:dp_bnft_rule)`에서 `properties(r) AS rule`을 반환한다. Neo4j `properties(r)`에는 `source_json`과 실제 그래프 속성이 포함된다.
2. `neo4j_search.py`의 `get_detail()`/`get_details()`는 반환된 `rule` 맵을 상세 결과에 담는다.
3. `card_graphrag.py`의 `benefit_context()`(712행 부근)는 `source(item["rule"])`로 `source_json`을 풀고 아래처럼 업무용 구조에 매핑한다.

```python
rules.append({
    "rule_key": rule.get("rule_key"),
    "value": rule.get("value_num"),
    "unit": rule.get("value_unit_cd"),
    "status": rule.get("rule_status_cd"),
    "targets": item["targets"],
})
```

4. `condition_groups()`는 조회된 condition atom의 `cond_min_amt`, `cond_max_amt_excl`, `cond_basis_cd`를 `min_amt`, `max_amt`, `basis`로 변환한다(약 508행). `rule_conflicts()`는 `SPEND_REQ` atom을 rule key별로 모아 tier의 구간 기준액을 채운다.

따라서 `rule["value"]`와 `rule["unit"]`은 규칙 노드의 `source_json.value_num` 및 `source_json.value_unit_cd`에서 온다. `rule["min_amt"]`는 규칙의 지급 값이 아니라 연결된 조건 atom의 `source_json.cond_min_amt`에서 온다. 이 데이터들은 서로 다른 의미와 경로다.

### 실제 Neo4j에서 확인한 규칙

읽기 전용 Neo4j 조회에서 카드 ID 22의 실제 카드명은 `더 심플 하나카드`이고, 혜택 노드는 다음과 같았다.

- 혜택: `월납 요금 청구할인`
- 혜택 key: `["card_bnft",22,"20261105_000099"]`
- 규칙 `r1` key: `["bnft_rule",22,"20261105_000099","r1"]`
- 규칙 `r2` key: `["bnft_rule",22,"20261105_000099","r2"]`
- `r1`: `value_num = null`, `value_unit_cd = null`; 연결된 `SPEND_REQ`의 `cond_min_amt = 300000`, 기준 `PREV_MONTH_SPEND`
- `r2`: `value_num = null`, `value_unit_cd = null`; 연결된 `SPEND_REQ`의 `cond_min_amt = 800000`, 기준 `PREV_MONTH_SPEND`
- 두 규칙의 `dp_targets` 목록은 동일한 휴대전화·구독 등 대상 목록으로 겹친다.
- 규칙 `r3`도 지급 값과 단위가 `null`이며 연결 atom은 `ETC`이고 `cond_min_amt = null`이다.

`rule_selection_open()`은 규칙이 둘 이상일 때 적용 대상이 비어 있거나 target 집합이 겹치면 선택 방식을 미확정으로 본다. `r1`과 `r2`는 같은 대상을 포함하므로 이 혜택은 미확정 규칙 집합으로 취급될 수 있다. 그 상태에서 구간별 `min_amt`를 가진 `r1`, `r2`가 `rule_conflicts()`의 tier가 된다. 비교 질문에는 결제 금액이 명시되지 않아 `applicable_rule_keys`가 비어 있을 수 있지만, `distorts_tier()`는 `min_amt`가 있는 모든 tier를 사용하므로 현재 예외 조건과 양립한다.

### None의 의미와 확인 범위

`None`은 실제 Neo4j `source_json`에 저장된 값이며 파이썬이 잘못 변환해 만든 값이 아니다. 다만 이것이 의도된 “지급 값 미확정”인지, 원천 문서 추출·등록 과정에서 지급액이 누락된 것인지는 이 조회만으로 단정할 수 없다. 조회된 규칙 상태는 `DRAFT`이고, 정기 구독 할인 등 지급률이 존재하는 다른 규칙과 대비되지만, 그것만으로 원천 데이터 누락을 확정할 수 없다. 상품설명서 원문과 등록 이력, 해당 혜택의 `bnft_rule_txt`·`limit_text`·인용 근거를 대조해야 데이터 결함인지 정상적인 미확정 표현인지 판단할 수 있다.

`value_num`과 `value_unit_cd`는 nullable한 저장 값으로 확인됐다. 따라서 같은 결합 형태를 가진 다른 카드·규칙에서도 잠재적으로 발생할 수 있다. 전 카드의 모든 rule을 대상으로 `value_num IS NULL`과 조건 구간의 조합을 점검하는 정량 감사는 이번 분석에서 수행하지 않았다.

## 8. 근본 원인 분석

**확인된 사실**

- 사용자 traceback의 예외는 `float(None)`과 일치한다.
- 코드의 `tier_token()`은 `tier["value"]`를 무조건 `float()`로 변환한다.
- `benefit_context()`는 Neo4j `value_num`을 nullable 검증 없이 `value`로 전달한다.
- `rule_conflicts()`는 `value`가 `None`인 규칙도 tier에 넣고, 구간 기준액만 별도로 가져온다.
- 실제 `더 심플 하나카드 / 월납 요금 청구할인`의 `r1`, `r2`에 `value_num`·단위가 `null`이며, 각각 30만 원·80만 원의 전월 실적 구간이 실제로 연결되어 있다.
- `distorts_tier()`는 구간 기준액이 있는 tier를 지급 값의 유효성 확인 없이 `tier_token()`에 넘긴다.

**결론**

실제 지급 값이 비어 있는 규칙을 정상적인 구간 tier와 동일한 자료 구조로 넘긴 뒤, 문장 검증 함수가 지급 값은 항상 숫자라는 가정을 적용한 것이 직접적인 원인이다. 특정 비교 질문만의 파서 오류가 아니라 nullable 데이터와 무조건적인 수치 변환 사이의 계약 불일치다.

## 9. 관련 함수 및 영향 범위

| 함수 | 현재 동작 및 위험 |
|---|---|
| `rule_conflicts()` | `rule_selection_open()`인 혜택의 모든 규칙을 tier로 복사한다. `value`, `unit`, `min_amt`의 완전성을 검사하지 않는다. |
| `tier_token()` | 직접 오류 발생 함수. `None`뿐 아니라 숫자가 아닌 문자열이면 `ValueError`도 가능하다. |
| `tier_label()` | `tier_token()`을 호출한 후 지급 문구를 만든다. 불완전 tier도 호출되면 같은 오류다. |
| `tier_text()` | 구간 기준액이 있는 tier를 `tier_label()`에 전달하므로 지급값이 비었을 때 위험하다. |
| `distorts_tier()` | 최소 금액만 있는 tier를 모아 `tier_token()`을 호출한다. 이번 traceback의 직접 호출부다. |
| `picks_single_tier()` | 적용 규칙만 추린 뒤 `tier_token()`을 호출한다. 적용 규칙에 지급 값이 빠졌으면 위험하다. |
| `tier_is_quoted()` | 최소 구간만 기준으로 필터링하고 각 지급 `tier_token()`을 구성한다. 구간 원문 검사 중 같은 위험이 있다. |
| `tier_answer()` | `tier_is_quoted()`와 `tier_label()`을 거쳐 프로그램 답변을 만든다. 적용 구간이 여러 개인 상황에서 위험하다. |
| `fixed_conclusion()` | `picks_single_tier()`와 `distorts_tier()`를 호출해 결론을 교체할지 판단한다. 결론 검증 경로에서 위험을 전파할 수 있다. |
| `validate_answer()` | 각 유효 포인트에서 `distorts_tier()`를 호출한다(1282행). 아래에서 `picks_single_tier()`와 적용 규칙 조건의 `tier_token()` 집합 생성(1299행)도 있다. 결론 처리 중 `fixed_conclusion()`을 거친다. |
| `answer_text_problem()` | 답변 텍스트 자체 검증 과정에서도 `picks_single_tier()` 및 `distorts_tier()`를 호출한다(1408–1410행). |

이 오류는 복수 카드 비교에 한정되지 않는다. 규칙 충돌이 조회된 단일 카드 혜택도 규칙이 중복·겹침 상태로 구성돼 있으면 같은 helper 호출 경로에 들어갈 수 있다. 지급액·할인율을 직접 묻는 질문뿐 아니라, 답변 포인트가 해당 혜택의 구간 충돌 검증에 도달하면 한도나 적용 가능 여부 질문도 영향을 받을 수 있다. 다만 실제로 질문 종류별 재현을 실행하지 않았으므로 이는 코드 경로에 따른 가능성이다.

LLM 응답은 일부 영향을 준다. 빈 답변, 상태 문장, 근거가 없는 문장 등은 해당 위치에서 건너뛸 수 있다. 반면 선행 검증을 통과한 유효 포인트가 하나라도 있으면 `distorts_tier()`가 문장 내용과 관계없이 호출된다. 따라서 LLM 문장과 근거 ID에 따라 재현 여부가 달라질 수 있다. 검증 함수 예외는 포인트 단위로 격리되지 않으므로 한 문장의 데이터 오류가 전체 GraphRAG 실행을 중단시킨다. 앞에서 생성된 다른 유효 포인트도 최종 반환 전에 버려질 수 있다.

## 10. 수정 방안 비교

| 방안 | 장점 | 한계·주의점 |
|---|---|---|
| `rule_conflicts()`에서 미지급 규칙 분류 | 불완전 규칙을 초기 단계에서 명시적으로 표시할 수 있고 지급 tier와 조건 구간을 구분하기 좋다. | 규칙 자체를 통째로 제거하면 적용 대상·실적 조건·미확정 사유까지 잃을 수 있다. 규칙과 근거는 보존하고 지급 값 상태만 분리해야 한다. |
| `tier_token()`에서 `None` 안전 처리 | 모든 직접 호출부를 한 지점에서 보호할 수 있다. | 반환 타입을 optional로 바꾸면 집합·포맷·비교 연산자 전체가 optional을 처리해야 한다. 임의로 `(unit, 0)`을 반환하면 허위 할인액이 만들어지고 검증이 성공한 것처럼 보일 수 있다. |
| `distorts_tier()`에서 숫자 검증 가능한 구간만 비교 | 이번 Traceback의 정확한 경로를 좁게 차단하면서 정상 숫자 tier 검증을 유지할 수 있다. | 다른 호출부(`picks_single_tier`, `tier_is_quoted`, `tier_label`, `validate_answer`의 1299행 등)에는 별도 방어가 필요하다. |
| 미확정 지급 정보를 보존 | 원 규칙, 구간, 근거를 잃지 않고 사용자에게 “할인액 확인 불가” 같은 미확정 상태로 안내할 수 있다. | `None`을 0원이나 검증 성공으로 취급하지 않도록 답변 생성·문장 검증의 계약이 명확해야 한다. |

## 11. 권장 수정 방향

수정은 규칙 정규화와 비교 함수 방어를 함께 적용하는 것이 적절하다.

1. `rule_conflicts()`가 규칙·실적 조건을 모두 유지하면서 지급 값의 유효성을 별도 상태로 표현한다. 예: 지급 값이 숫자이고 단위가 허용되는지 나타내는 내부 플래그 또는 `payout_known` 목록. 불완전 규칙은 삭제하지 않고 미확정 규칙으로 보존한다.
2. 숫자 지급 비교는 유효한 숫자와 지원 단위가 있는 tier만 대상으로 한다. `tier_token()` 또는 그 대체 helper는 `None`·비숫자 값을 명시적으로 반환/거절하도록 하고, 모든 호출부가 그 결과를 검사하도록 한다.
3. `distorts_tier()`는 검증 가능한 지급 tier만 관계를 비교하고, 기준액 자체의 검증은 기존처럼 유지한다. 지급 값을 확인할 수 없는 tier를 기준으로 답변이 틀렸다고 판정하거나 맞다고 판정하지 않는다.
4. `picks_single_tier()`, `tier_is_quoted()`, `tier_label()`/`tier_text()`, `tier_answer()`, `fixed_conclusion()`, `validate_answer()`의 직접 집합 생성, `answer_text_problem()`도 같은 유효성 규약을 사용한다. 한 helper만 고쳐 다른 호출부에서 다시 `float(None)`이 나오는 상황을 피한다.
5. 미확정 지급액은 근거와 함께 unresolved/uncertain으로 남긴다. 관련 문장을 검증할 수 없다는 이유만으로 다른 독립적으로 검증된 포인트까지 버리지 않도록, 가능한 범위에서 포인트 단위 오류 격리 또는 안전한 검증 결과를 반환한다. 격리는 오류를 숨기지 않도록 경고·진단에도 남겨야 한다.

`None → 0` 변환, 원문에 없는 지급액 생성, 비교할 수 없는 값을 검증 성공 처리하는 방식은 금지한다. 정상 값 tier의 구간 비교와 기존 근거 검증은 그대로 회귀 테스트해야 한다.

## 12. 수정 후 검증할 테스트 목록

1. 실제 구조의 `value=None`, `unit=None`, `min_amt=300000` 및 `800000` tier를 넣어 `distorts_tier()`, `validate_answer()`가 예외 없이 처리하고 미확정 사실을 유지하는지 검사한다.
2. `tier_token()`의 정상 금액·할인율 값은 기존 토큰으로 변환되고, `None`·숫자가 아닌 문자열은 허위 0값 없이 미확정/비교 불가로 처리되는지 확인한다.
3. 각 호출 경로를 점검한다: `tier_label()`/`tier_text()`, `distorts_tier()`, `picks_single_tier()`, `tier_is_quoted()`/`tier_answer()`, `fixed_conclusion()`, `validate_answer()`(포인트 경로 및 1299행), `answer_text_problem()`.
4. 다른 카드 비교와 단일 카드 질문, 통신비·정기 구독, 할인 금액·할인율·통합 한도 질문을 stub LLM으로 검증한다. 유료 LLM을 사용하지 않는다.
5. 기존 정상 숫자 구간(복수 tier), 적용 최소 실적, 결제액 기준, 겹치지 않는 target, 원문에 구간이 모두 있는 경우의 기대 검증 결과를 유지한다.
6. 지급값이 없는 tier와 정상 tier가 함께 있을 때 불완전 tier 때문에 정상 tier 비교가 무력화되지 않는지 확인한다.
7. 여러 문장 중 한 문장에만 미확정 tier가 있어도 다른 근거 있는 답변 포인트가 가능한 한 유지되는지 확인한다.
8. 실제 Neo4j 읽기 전용 fixture에서 더 심플 카드 ID 22의 혜택 `20261105_000099`, 규칙 `r1`·`r2` nullable 지급 값 구조를 재현하고, 어떤 결과도 할인액 0원 또는 임의 지급액으로 바뀌지 않는지 확인한다.

## 13. 미확인 사항 및 추가 조사 항목

- `app_log` 194–198에는 요약 오류만 있고 traceback이 없다. 실제 예외 프레임은 사용자 제공 로컬 Traceback을 기준으로 했다.
- Neo4j 읽기 전용으로 `더 심플 하나카드`(card_id 22), `월납 요금 청구할인`(benefit key `20261105_000099`), `r1`·`r2`의 `value_num/value_unit_cd = null`과 각각의 300,000/800,000 전월 실적 구간, 동일 target 목록을 확인했다. 이 규칙들이 제보 질문에서 실제 검색 결과에 포함된 각 실행의 상세 행까지 로그와 연결해 재구성한 것은 아니다. 로그의 Cypher 문자열에 조회가 있었음은 확인했으나 결과 행 자체는 기록되지 않는다.
- null 지급 값이 원문에 없는 상태인지, 상품설명서 원문·별도 한도 속성·근거 문장에 표현되어 있는데 구조화 필드로 옮겨지지 않은 것인지는 미확인이다. PDF 근거 및 등록 원본과 대조해야 한다.
- `카드의정석2 DAILY` 등 대상 카드의 전체 혜택 규칙을 대상으로 nullable payout 전수 검사는 수행하지 않았다. 실제 발생 원인 규칙으로는 더 심플 카드의 r1/r2를 확인했으며 다른 잠재 규칙은 추정만 가능하다.
- 특정 질문에 대한 실패 여부는 LLM 문장·인용 ID와 해당 실행의 조회 자료에 좌우될 수 있다. 실제 유료 LLM 재현은 수행하지 않았다.
- 단일 카드, 각 질문 종류의 재현은 호출 구조에 따른 영향 가능성 분석이며 별도 실행 검증은 아니다.

## 14. 분석 결론

직접적인 예외는 `tier_token()`의 `float(tier["value"])`이며, 확인된 실제 입력 원천은 더 심플 하나카드의 `월납 요금 청구할인` 규칙 `r1`, `r2`다. 두 규칙은 Neo4j의 `source_json.value_num`과 `value_unit_cd`가 `null`인 반면 조건 atom에는 300,000원·800,000원의 전월 실적 구간이 있어 `rule_conflicts()`가 `min_amt`가 존재하는 tier를 만들 수 있다. `distorts_tier()`가 `min_amt`만 검사해 이를 `tier_token()`에 전달하면서 `float(None)`이 발생한다.

수정 시 데이터 불완전성을 유지한 채 숫자 비교 가능한 지급 tier만 검사하고, 모든 `tier_token()` 호출부가 같은 nullable 규약을 따르게 해야 한다. 검증할 수 없는 금액은 불확정으로 남기고, 전체 요청이 불필요하게 실패하지 않도록 포인트 단위로 안전하게 다루는 것이 권장된다. 이번 작업에서는 소스나 DB를 변경하지 않았다.
