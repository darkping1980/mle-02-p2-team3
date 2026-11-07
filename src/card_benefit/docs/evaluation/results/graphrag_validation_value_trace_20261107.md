# GraphRAG 답변 검증 값 추적 — CARD10-032 / CARD10-056

> 기준: 2026-11-07 작업 트리의 평가 결과 JSON과 card_graphrag.py를 읽기 전용으로 대조했다. GraphRAG·LLM API·PostgreSQL·Neo4j를 실행하거나 변경하지 않았다.

## 1. 증거 수준 및 분석 범위

- **기록값**: 평가 JSON에 그대로 보존된 값
- **코드로 확인**: warning과 현재 코드 분기로 발생 지점을 확인한 내용
- **추론 / 미확인**: 중간 LangGraph 상태가 저장되지 않아 직접 값을 볼 수 없는 내용

기준 자료:

- 평가: src/card_benefit/docs/evaluation/results/graphrag_evaluation_50_20261107_adjudicated.json
- 이전 실패 분석: src/card_benefit/docs/evaluation/results/graphrag_evaluation_50_20261107_failure_analysis.md
- 실행 코드: src/card_benefit/payment_card/db_pipeline_origin_search/card_graphrag.py

평가 JSON에는 전체 state, retrieved_data, context, state의 exclusions, tier_mappings, limit_tiers, limit_text, excluded_terms가 없다. 따라서 누락된 내부 값은 임의로 채우지 않았다. JSON의 answer_diagnostics.validated는 validate_answer()만 끝난 시점의 값도 아니다. answer()가 validate_answer(), transaction_tier_fallback(), enforce_exclusions()를 모두 실행한 뒤 저장한다.

## 2. Python과 LangGraph를 Java에 대응해 이해하기

| Python | Java에 가까운 표현 | 설명 |
|---|---|---|
| dict | Map<String, Object> | state, context, answer 같은 키-값 데이터 |
| list | List<T> / ArrayList<T> | 혜택, Evidence, 답변 point의 목록 |
| state["question"] | state.get("question")와 유사 | 키가 없으면 Python은 예외를 냄 |
| state.get("exclusions", []) | getOrDefault("exclusions", List.of()) | 키가 없을 때 빈 목록을 사용 |
| parsed | 파싱된 DTO | Answer LLM이 만든 원본 CardAnswer |
| answer | 검증 후 사용자에게 전달할 Map | 원본을 검사해 새 결과를 만드는 변수 |
| {**context, ...} | 새 HashMap에 기존 값과 추가 필드를 복사 | 바깥쪽 Map을 합치는 문법 |

LangGraph의 CardState는 타입 설명이고, 실제 실행 데이터는 dict 형태다. 노드는 변경한 값들을 반환하고 LangGraph가 다음 단계에 전달할 상태를 병합한다. run()은 _initial_state()로 시작 상태를 만들고 graph.invoke()로 그래프 전체를 실행한다([_initial_state / run](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2374)).

실제 LLM 호출은 _call_llm() 안의 invoke(prompt)에서 일어난다([_call_llm](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2416)). 그 전까지는 검색 결과와 프롬프트를 구성하는 Python 코드이며, 응답 뒤 validate_answer(), transaction_tier_fallback(), enforce_exclusions()는 Python 조건문이다. 본 분석에서는 API를 다시 호출하지 않았다.

---

## 3. CARD10-032 — 4대 PAY 추가할인이 제외로 뒤집힘

### 질문 / 검색 기록

질문: **카드의정석 SHOPPING의 4대 PAY 추가 할인은 기본 할인과 한도를 공유하니?**

평가 JSON 기록값:

| 항목 | 실제 값 |
|---|---|
| Hybrid 후보 ID | 20261104_000017, 20261104_000018, 20261104_000015, 20261104_000016, 20261104_000013, 20261104_000020, 20261104_000022, 20261105_000100 |
| 선택된 참조 | card_product_item:6:20261104_000017, card_product_item:6:20261104_000013 |
| 혜택명 | 온라인 업종 4대 PAY 결제 시 5% 추가할인; 온라인 쇼핑 10% 청구할인 |
| 추가 PAY retrieve | rule 1, condition 3, limit 1, Evidence 16 |
| 온라인 쇼핑 retrieve | rule 1, condition 0, limit 1, Evidence 9 |

전체 retrieved_data/context["benefits"]는 저장되지 않았다.

### Answer LLM 원본

answer_diagnostics.raw에 기록된 parsed 값:

- conclusion: “네. 4대 PAY 추가 할인은 온라인 쇼핑 할인과 온라인 월 통합 할인한도를 공유합니다.”
- answer_text: “네, 4대 PAY 추가 할인은 온라인 쇼핑 할인과 온라인 업종 월 통합 할인한도를 공유합니다. 한도는 전월 국내 가맹점 이용금액 30만원 이상 70만원 미만이면 월 4천원, 70만원 이상 120만원 미만이면 월 8천원, 120만원 이상이면 월 1만6천원입니다.”
- point benefit_id: card_product_item:6:20261104_000017
- point: “4대 PAY 추가 할인은 온라인 쇼핑 할인과 온라인 업종 월 통합 할인한도를 공유하며, 전월 국내 가맹점 이용금액 30만원 이상 70만원 미만은 월 4천원, 70만원 이상 120만원 미만은 월 8천원, 120만원 이상은 월 1만6천원입니다.”
- evidence_ids: 20261104_001728, 20261104_001795, 20261104_001798

원본에는 “할인을 받을 수 없다”는 내용이 없다.

### 실제 Evidence 인용

| Evidence ID | 페이지 | 인용문 | 연결 혜택 |
|---|---:|---|---|
| 20261104_001724 | 2 | 온라인 업종 4대 PAY 결제 시 5% 추가할인 | 추가 PAY |
| 20261104_001728 | 2 | 온라인 업종 통합 할인한도 내에서 할인 적용 | 추가 PAY |
| 20261104_001729 | 2 | 전월 국내 가맹점 이용금액 30만원 이상 시 할인 | 추가 PAY |
| 20261104_001730 | 2 | 추가 청구할인은 4대 간편결제에 본 카드를 등록하여 온라인에서 사용한 경우에 제공 | 추가 PAY |
| 20261104_001731 | 2 | Two-in-One 결제서비스(체크매출) 이용 시 추가 캐시백 미제공 | 추가 PAY |
| 20261104_001795 | 3 | 전월 실적 구간: 30만원 이상/70만원 미만, 70만원 이상/120만원 미만, 120만원 이상 | 추가 PAY |
| 20261104_001796 | 3 | 온라인 / 4천원 / 8천원 / 16천원 | 추가 PAY |
| 20261104_001797 | 3 | 합계 / 1만원 / 2만원 / 4만원 | 추가 PAY |
| 20261104_001798 | 2 | 온라인 업종 통합 할인한도 내에서 할인 적용 | 추가 PAY |
| 20261104_001799 | 4 | 단, 온라인 업종 4대 PAY 결제로 추가할인 적용 시 (10%＋5%) 할인 (최대 7,500원 할인) | 추가 PAY |
| 20261104_001800 | 4 | 매출 건당 5만원까지 할인 | 추가 PAY |

### 실행 흐름

answer()는 retrieved_data에서 중복 혜택을 정리하고 선택 혜택의 Evidence와 benefit_context를 모아 프롬프트를 만든다([answer](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2634)). 이후 아래 순서다([후처리 호출부](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2720)).

    answer, warnings = validate_answer(parsed, merged_context, question)
    answer, unresolved_tier_note = transaction_tier_fallback(answer, context, question)
    answer, guarded = enforce_exclusions(answer, state.get("exclusions", []), evidence)

### 1) _call_llm()

_call_llm()은 구조화 응답으로 LLM을 호출하고 parsed CardAnswer와 메트릭을 돌려준다([_call_llm](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2416)). 위에 옮긴 원본 answer가 실제 기록값이다. 여기까지는 모델 출력이고, 이 뒤부터 프로그램이 결과를 변경할 수 있다.

### 2) validate_answer()와 한도 검사

validate_answer()는 raw.points를 순회하며 benefit ID와 Evidence 소유권을 확인하고, 한도 주장은 limit_tier_answer_problem()으로 검사한다([validate_answer](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:1715)).

실제 warning:

> 자연어 답변 대신 검증된 문장을 표시합니다: monthly cap is not a single fixed value in this benefit's limit text

이 영어 문자열은 limit_tier_answer_problem()의 다음 return과 일치한다([limit 검사](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2012)).

    claimed_caps = _monthly_cap_claim_values(text)
    if claimed_caps:
        for item in targets:
            fixed_caps = _fixed_monthly_cap_values(item)
            if not fixed_caps or not claimed_caps.issubset(fixed_caps):
                return "monthly cap is not a single fixed value in this benefit's limit text"

뜻은 답변의 월 한도 값들을 혜택의 단일 고정 한도 값과 비교한다는 것이다. 평가 JSON에 claimed_caps, fixed_caps, targets 값은 없으므로 집합 원소는 확인 불가다. 경고 문자열을 통해 이 오류 분기가 실제로 발생한 사실은 확인된다.

answer_text_problem()도 자연어 답변을 검사하며 같은 한도 함수를 호출한다([answer_text_problem](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2259)). 결과 JSON에 “point를 버렸다”는 warning은 없고 “자연어 답변 대신 검증된 문장” warning이 있다. 그러므로 point는 통과하고 answer_text만 대체된 것으로 보인다. 다만 당시 context가 없어 validate 직후 딕셔너리를 완전 재현할 수는 없다.

### 3) transaction_tier_fallback()

이 함수는 결제 금액별 지급 구간이 모호할 때 답변을 보류한다([transaction_tier_fallback](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:1403)). 이 문항에는 “Unresolved transaction amount mapping...” 경고가 없다. 따라서 변경하지 않은 것으로 보이나, conflicts와 즉시 반환값은 기록되지 않았다.

### 4) find_exclusions() / enforce_exclusions()

find_exclusions()는 질문의 search terms와 혜택 원본의 excluded tokens를 맞춰 제외 레코드를 찾는다([find_exclusions](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:478)). 평가 JSON에는 state["exclusions"] 원본이 없다. 단, 실제 warning은 다음과 같다.

> 제외 대상을 적용으로 쓴 문장을 버렸습니다: 추가

따라서 enforce_exclusions() 입력의 terms에 “추가”가 포함됐고 정상 point에도 “추가”가 있었다는 점은 알 수 있다. exclusion 딕셔너리 전체는 알 수 없다.

enforce_exclusions()의 실제 필터([코드](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:506)):

    kept = [point for point in points
            if not any(term in point["text"] for term in item["terms"])
            or EXCLUSION_WORDS.search(point["text"])]

이 조건은 point에 제외 term이 없거나 문장 자체가 제외 표현일 때 남긴다. 원본 point는 “추가 할인”이라는 긍정 문장이다. term “추가”가 포함돼 첫 조건은 False이고, 제외 표현은 없어 두 번째도 False다. 따라서 point가 삭제됐다.

그 다음 함수는 term이 들어 있는 Evidence quote를 찾는다. Evidence 001724의 “온라인 업종 4대 PAY 결제 시 5% 추가할인”은 긍정적인 혜택 제목이지만 “추가”가 포함되어 선택됐다. 코드는 인용문의 의미가 실제 제외를 뒷받침하는지 검사하지 않았다. 이후 다음 system point를 만든다.

> 추가는 온라인 업종 4대 PAY 결제 시 5% 추가할인의 제외 대상이라 이 혜택을 받을 수 없습니다.

최종 point에는 evidence_ids=[20261104_001724], origin=system, verification=NOT_CHECKED가 기록됐다.

### 단계별 비교

| 단계 | 값 | 이유 |
|---|---|---|
| Answer LLM 원본 | 한도 공유, 구간별 4천/8천/1만6천원 | 평가 JSON raw |
| validate_answer 직후 | 즉시 dict 미저장. 한도 자연어 대체 warning은 기록됨 | 고정 한도 검증 오류. point 통과는 warning 부재에 근거한 추론 |
| transaction fallback 직후 | 값 미저장, transaction warning 없음 | 변경 없었던 것으로 보임 |
| enforce_exclusions 직후 | 정상 point 삭제, 제외 system point 생성 | “추가” warning, 최종 point와 001724로 확인 |
| 최종 응답 | “추가는 ... 제외 대상이라 이 혜택을 받을 수 없습니다.”, ANSWERED | 실제 결과 JSON |

직접 원인은 enforce_exclusions()의 부분 문자열 검사다. ANSWERED는 의미상 제외 판단이 검증됐다는 뜻이 아니다. 시스템 point가 남아 기존 상태를 유지한 코드 흐름과 일치한다.

---

## 4. CARD10-056 — 전월 실적 구간별 한도 매핑 삭제

### 질문 / Retrieve 데이터

질문: **카드의정석 SHOPPING 오프라인 쇼핑은 전월 실적 구간별 월 한도와 건당 할인 대상 금액 한도가 어떻게 돼?**

- 선택 혜택: card_product_item:6:20261104_000015, 오프라인 쇼핑 10% 청구할인
- Retrieve: rule 1, condition 0, limit 1, Evidence 9
- Evidence 001790, p.3: 실적 구간 30만원 이상/70만원 미만, 70만원 이상/120만원 미만, 120만원 이상
- Evidence 001791, p.3: 오프라인 / 6천원 / 12천원 / 24천원
- Evidence 001793, p.4: 이마트에서 10만원 결제 시 5만원에 대해서만 10% 할인 적용(5,000원 할인)

context의 전체 benefits와 tier_mappings, limit_tiers, limit_text는 저장되지 않았다.

### Answer LLM 원본

- conclusion: “오프라인 월 할인한도는 전월 실적 구간에 따라 6천원·1만 2천원·2만 4천원이고, 건당 할인 대상 금액은 5만원입니다.”
- answer_text: “전월 국내 가맹점 이용금액이 30만원 이상 70만원 미만이면 오프라인 월 할인한도는 6천원, 70만원 이상 120만원 미만이면 1만 2천원, 120만원 이상이면 2만 4천원입니다. 건당 할인 대상 금액은 5만원까지이며, 예시에서는 10만원 결제 시 5만원에 대해서만 할인을 적용합니다.”
- point 1: 위 세 전월실적 구간과 각각 6천원, 1만2천원, 2만4천원을 연결함. evidence_ids=[20261104_001790, 20261104_001791]
- point 2: 건당 할인 대상 5만원, 10만원 결제 사례. evidence_ids=[20261104_001793]

### 검증 함수의 분기

실제 warning:

> monthly cap is not a single fixed value in this benefit's limit text: 전월 국내 가맹점 이용금액 30만원 이상 70만원 미만 구간의 오프라인 월 할인한도는 6천원, 70만원 이상

> 자연어 답변 대신 검증된 문장을 표시합니다: monthly cap is not a single fixed value in this benefit's limit text

첫 오류 문자열은 limit_tier_answer_problem()에서 다음 조건으로 발생한다([함수](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2012)).

    claimed_caps = _monthly_cap_claim_values(text)
    if claimed_caps:
        fixed_caps = _fixed_monthly_cap_values(item)
        if not fixed_caps or not claimed_caps.issubset(fixed_caps):
            return "monthly cap is not a single fixed value in this benefit's limit text"

질문에 월 한도가 있으므로 한도 질문 가드는 통과했다. warning이 기록됐으므로 claimed_caps가 있고, fixed_caps가 없거나 주장값 집합을 포함하지 못한 것도 함수 분기상 확인된다.

이 검증은 고정 월 한도를 검사하는 분기다. 이 데이터는 실적별로 다른 한도를 가진다. 원문 표는 구간 행과 금액 행으로 나뉘어 저장되어 있으므로, 그 행 관계가 구조화 tier mapping으로 인식되어 앞선 구조화 처리에서 끝났는지 여부가 핵심이다. 그러나 평가 JSON에는 _has_structured_limit_tiers()의 실제 반환값이나 mapping이 없다. 따라서 구조화 tier가 False였다는 것은 추론이고 직접 관측값은 아니다.

validate_answer()는 각 point에서 한도 문제를 받으면 drop()을 호출하고 continue한다([point 검사](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:1752)). 원본에는 두 point가 있었지만 최종에는 5만원 예시 point만 남았다. 경고와 adjudication failure_stage=validate_answer도 일치한다. 구간별 point는 탈락한 것으로 판단할 수 있다.

### answer_text_problem()이 바꾼 문자열

answer_text_problem()도 전체 answer_text에 limit_tier_answer_problem()을 적용한다([answer_text_problem](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2259)). 문제가 있으면 validate_answer()는 원본 자유형 문장을 쓰지 않고 conclusion과 검증 통과 point를 합친다([validate_answer의 텍스트 구성](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:1881)).

    body = " ".join(dict.fromkeys(
        point["text"] for point in points if point["text"] != conclusion
    ))
    answer_text = "\n\n".join(part for part in (conclusion, body) if part)
    source_cd = "validated_sentences"

한도 point는 points에서 빠졌지만, conclusion은 남을 수 있다. 그래서 최종 answer_text에는 세 한도 금액 요약이 보이지만, point와 인용 근거에는 한도 연결이 남지 않았다.

### 후속 함수와 최종 응답

transaction_tier_fallback()은 결제 건당 지급구간의 모호성을 다루므로 전월 실적별 월 한도 오류의 직접 원인으로 보이지 않는다. 해당 경고도 없다. enforce_exclusions()에서 내용을 바꾼 흔적은 없으나 exclusions state가 저장되지 않아 완전 확정은 불가하다.

최종 평가 JSON:

- status=PARTIAL
- answer_source=validated_sentences
- conclusion은 “전월 실적 구간에 따라 6천원·1만 2천원·2만 4천원”이라는 요약과 건당 5만원을 언급
- answer_text에는 위 conclusion과 10만원 결제 시 5만원에 대해서만 10% 할인하는 예시
- 최종 points에는 건당 할인 대상 point만 남음
- 최종 cited evidence는 001793. 월 한도 point에 있었던 001790/001791은 인용 목록에 없음

validate_answer()는 point가 남아도 하나 이상의 point가 탈락했으면 PARTIAL을 반환한다([상태 판정](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:1872)).

### 단계별 비교

| 단계 | 값 | 이유 |
|---|---|---|
| Answer LLM 원본 | 세 실적 구간과 월 한도를 연결한 point, 5만원 건당 예시 point | 평가 JSON raw |
| validate_answer 직후 | 구간 point 제거, 건당 point 유지, 자유형 answer_text 대체 | warning과 코드 분기에서 확인; 즉시 dict 자체는 미기록 |
| transaction fallback 직후 | 값 미저장, 관련 warning 없음 | 변경 없었던 것으로 보임 |
| enforce_exclusions 직후 | 최종에 제외 문구 없음 | 변경 없는 것으로 보이나 입력 exclusions 미기록 |
| 최종 응답 | 월 한도 요약은 conclusion에 남았으나 월 한도 point/Evidence는 없음, PARTIAL | 최종 JSON |

---

## 5. 실제 결과로 확인되는 핵심 차이

| 문항 | 직접 변경 함수 | 조건 | 결과 |
|---|---|---|---|
| CARD10-032 | enforce_exclusions() | term “추가”가 긍정 point와 Evidence 제목에 포함 | 정상 답변 삭제, 5% 추가할인 혜택을 제외로 오답 생성 |
| CARD10-056 | limit_tier_answer_problem() → validate_answer() | 구간별 월 한도 주장을 단일 fixed cap 검증으로 평가 | 구간 매핑 point와 001790/001791 제거, PARTIAL |

첫 문항에서 Answer LLM 응답을 반대 의미로 만든 직접 원인은 exclusion 후처리다. 두 번째는 실적 구간별 한도 mapping을 검증하는 분기가 원본 답변을 point 단위로 거부한 문제다.

## 6. 무엇이 실제로 기록됐고, 무엇이 없는가

| 데이터 | CARD10-032 | CARD10-056 |
|---|---|---|
| 질문 / Answer 원본 | 기록 | 기록 |
| 선택 혜택 ID / retrieve 개수 | 기록 | 기록 |
| Evidence 인용 / 페이지 / ID | 기록 | 기록 |
| 최종 answer / status / warnings | 기록 | 기록 |
| 전체 State / retrieved_data | 없음 | 없음 |
| 전체 context benefits/evidence | 없음 | 없음 |
| exclusions 객체 | 없음. warning에서 term “추가”는 확인 | 없음 |
| tier mapping / limit text / 구조화 판정 bool | 없음 | 없음 |
| validate 직후 return값 | 없음 | 없음 |
| fallback 직후 return값 | 없음 | 없음 |

누락된 context와 exclusions를 당시 그대로 재주입할 수 없으므로 완전한 오프라인 재현은 불가능하다. 이 문서는 원본/최종 저장값과 소스 분기를 연결했다. 추정한 객체 값을 관측값처럼 쓰지 않았다.

## 7. 발표용 1–2분 요약

> 두 평가 문항은 LLM 이후 Python 검증 코드가 답을 바꿀 수 있다는 점을 보여줍니다. CARD10-032에서 LLM은 4대 PAY 추가 할인이 온라인 통합 한도를 공유한다고 답했습니다. 하지만 제외 검사 코드는 “추가”라는 단어가 답에 있는지만 확인했습니다. “추가 할인”의 추가를 제외 용어로 오인해 정상 답변을 지우고, 같은 단어가 든 혜택 제목을 근거로 붙여 “혜택을 받을 수 없다”고 바꿨습니다.
>
> CARD10-056에서는 LLM이 전월 실적별 6천원, 1만2천원, 2만4천원 한도를 정확히 연결했습니다. 검증 함수가 이를 단일 고정 월 한도 관점으로 검사해 구간 point와 PDF 근거를 제거했습니다. 답변 일부가 남았지만 핵심 관계의 근거가 사라져 PARTIAL이 됐습니다.
>
> 교훈은 LLM 원본만 보면 오류 위치를 찾을 수 없다는 것입니다. 검증 전후의 상태와 조건문을 함께 기록해야 합니다. 이번 평가 결과에는 원본과 최종 결과는 있지만 함수별 직후 State가 없어 일부 내부값을 복원할 수 없다는 관측성 한계도 확인됐습니다.

## 8. 추가 검증이 필요한 지점

1. CARD10-032의 실제 state["exclusions"], excluded_tokens() 결과와 후보 Evidence 전체는 저장되지 않았다. term “추가”만 warning에서 확인된다.
2. 두 문항 모두 validate 직후, transaction fallback 직후, exclusion 직후 dict가 저장되지 않았다.
3. CARD10-056의 claimed_caps, fixed_caps, _has_structured_limit_tiers() 반환값은 저장되지 않았다.
4. answer_diagnostics.validated는 검증만 거친 값으로 오해할 수 있지만 실제로는 두 후속 함수까지 실행된 뒤 저장된다.
5. 이 작업은 분석 전용이므로 실행 코드 변경, API/DB 호출, 데이터 변경은 수행하지 않았다.

## 9. 관련 함수 위치

- [find_exclusions() / enforce_exclusions()](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:478)
- [transaction_tier_fallback()](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:1403)
- [validate_answer()](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:1715)
- [limit_tier_answer_problem()](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2012)
- [answer_text_problem()](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2259)
- [_call_llm()](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2416)
- [answer() 문맥 구성](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2634)
- [answer() 후처리와 diagnostics 저장](../../../payment_card/db_pipeline_origin_search/card_graphrag.py:2720)

