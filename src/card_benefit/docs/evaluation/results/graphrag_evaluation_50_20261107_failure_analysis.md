# GraphRAG 50문항 평가 실패 원인 분석

작성일: 2026-11-07
분석 범위: 실제 API·Neo4j 평가 결과만 사후 분석. GraphRAG 실행, API 재호출, 평가 데이터 수정, DB 변경 및 애플리케이션 소스 수정은 하지 않았다.

## 1. 분석 기준과 요약

| 항목 | 기준 |
|---|---|
| 실행 결과 | [`graphrag_evaluation_50_20261107.json`](graphrag_evaluation_50_20261107.json), [`graphrag_evaluation_50_20261107_adjudicated.json`](graphrag_evaluation_50_20261107_adjudicated.json) |
| 기존 실행 요약 | [`graphrag_evaluation_50_20261107_report.md`](graphrag_evaluation_50_20261107_report.md) |
| 실행 HEAD | `4f050387415f68ab3cd6c84aa9e1c04804134d13`; 실행 당시 `card_graphrag.py` SHA-256 `3059DA101883CD81A0D99E94F131C7E824DF45106C78D3DFC035389739329FCA` |
| 전체 판정 | CORRECT 33, PARTIAL 9, WRONG 7, EXECUTION_ERROR 0, JUDGMENT_HOLD 1. CARD10-030은 분모에서 제외했다. |

우선 확인할 검증 문제는 단순한 답변 거부가 아니다. CARD10-032에서 Answer LLM의 정답 포인트가 월 한도 표현 검사에 걸려 탈락했고, 이후 별도의 제외 강제 로직이 질문의 `추가`라는 단어를 제외 매치로 오인해 반대 의미의 문장을 새로 만들었다. CARD10-056에서는 맞는 구간·한도 포인트를 검증기가 구조화된 티어 정보가 없다는 이유로 제거했다. `transaction_tier_fallback()`은 두 문항의 관측된 변환 원인이 아니다.

## 2. CARD10-032 — 정답 포인트 제거 후 의미가 반전됨

질문은 “카드의정석 SHOPPING의 4대 PAY 추가 할인은 기본 할인과 한도를 공유하니?”이다. 검색 및 선택은 성공했다.

| 단계 | 실제 기록 |
|---|---|
| Hybrid 후보 | `20261104_000017`(온라인 업종 4대 PAY 5% 추가할인), `20261104_000013`(온라인 쇼핑 10% 할인) 모두 후보에 포함 |
| Interpret 선택 | `card_product_item:6:20261104_000017`, `card_product_item:6:20261104_000013` |
| Retrieve | 두 혜택을 조회. 5% 혜택 evidence 16건, 온라인 쇼핑 evidence 9건 |
| Answer LLM point | “4대 PAY 추가 할인은 온라인 쇼핑 할인과 온라인 업종 월 통합 할인한도를 공유하며, 전월 국내 가맹점 이용금액 30만원 이상 70만원 미만은 월 4천원, 70만원 이상 120만원 미만은 월 8천원, 120만원 이상은 월 1만6천원입니다.” Evidence `20261104_001728`, `20261104_001795`, `20261104_001798` |
| validate 이후 | 위 positive point는 사라지고, “추가는 온라인 업종 4대 PAY 결제 시 5% 추가할인의 제외 대상이라 이 혜택을 받을 수 없습니다.”라는 system point가 남음. 최종 상태는 잘못 `ANSWERED` |

### 호출 순서와 실제 변환 조건

현재 파일의 호출 흐름은 `CardGraphRAG.answer()`(`card_graphrag.py:2623`)에서 Answer LLM 응답을 받은 다음 `validate_answer()`(`:1704`)를 호출하고, 반환 후 `transaction_tier_fallback()`(`:1392`), `enforce_exclusions()`(`:495`)를 순서대로 호출한다(`answer()`의 호출부 `:2713–2718`). 따라서 검증기 뒤에서 답변 의미를 바꿀 수 있는 제외 강제 함수도 판정 대상이다.

1. `validate_answer()`는 각 point에 대해 근거 소유권을 확인한 뒤 `limit_tier_answer_problem()`을 호출한다(`:1742–1746`). 이 질문은 한도 질문으로 분류된다. 선택된 5% 혜택은 실행 결과에서 구조화 `limit_tiers`가 확인되지 않고, `item_limit_txt`/한도 텍스트에는 여러 실적 구간 금액이 있어 단일 고정 한도로 볼 수 없다.
2. `limit_tier_answer_problem()`(`:2001–2053`)의 티어 구조 검사에서 이 경우 고정 한도 집합이 비어 반환된다. `claimed_caps`가 존재하고 `_fixed_monthly_cap_values()`가 하나의 단일값을 주지 못하자 `:2051–2053`에서 정확히 `monthly cap is not a single fixed value in this benefit's limit text`를 반환한다. `validate_answer()`(`:1742–1746`)가 point 전체를 버린다. 진단 경고에 이 원인이 기록됐다.
3. 그 다음 `find_exclusions()`(`:467–485`)가 질문의 검색 토큰과 혜택의 `excluded_tokens`를 겹침 비교한다(`:469–482`). 평가 산출물은 이 단계의 원본 제외 목록을 따로 저장하지 않았지만, 최종 경고 `제외 대상을 적용으로 쓴 문장을 버렸습니다: 추가`는 `enforce_exclusions()`가 실제로 `terms=["추가"]`를 받았음을 증명한다.
4. `enforce_exclusions()`(`:495–509`)는 제외 매치된 용어가 point 문장에 포함되면 positive point를 제거하고(`:504–508`), “{term}은 … 제외 대상이라 … 받을 수 없습니다”라는 반대 문장을 만든다(`:501–503`). 인용문에서 해당 단어가 들어간 첫 quote를 찾아 system point로 붙인다(`:509–511`). 실제 최종 Evidence `20261104_001724`는 “온라인 업종 4대 PAY 결제 시 5% 추가할인”이라는 **혜택 적용** 문구이지 제외 근거가 아니다.

따라서 반전은 `validate_answer()` 한 함수 안에서 일어난 것이 아니다. 검증기의 한도 오탐이 정상 point를 제거했고, 후속 `enforce_exclusions()`의 단어 매칭이 `추가`를 부정적 적용 제외로 오인해 사용자 답변을 뒤집었다. 결과 JSON에는 `transaction_tier_fallback()` 경고가 없으며 실행된 fallback이 최종 반전의 원인은 아니다.

### PDF 사실 및 영향 범위

공식 카드의정석 SHOPPING PDF 문서 ID `20261104_000023`의 2페이지에는 4대 PAY 온라인 결제 5% 추가할인, 온라인 업종 통합 한도 내 적용, 전월 국내 가맹점 30만원 이상, 간편결제 등록 후 온라인 사용 조건이 있다. 3페이지의 온라인 한도 표는 30만~70만원 미만 4천원, 70만~120만원 미만 8천원, 120만원 이상 1만6천원이다. 4페이지에는 10%+5%와 최대 7,500원 설명이 있다. 공식 원문은 추가 할인을 제외 대상으로 규정하지 않는다.

현재 방식은 `추가` 같은 일반 단어가 혜택명·질문에 포함된 다른 카드 혜택에도 반전 문장을 만들 수 있다. 특히 “추가 적립/할인”, “추가 혜택” 질문과 제외 키워드를 가진 혜택 조합에서 오탐 위험이 있다. 첫 번째로 발견된 Evidence의 단어 포함만으로 부정 결론을 만들므로 실제 제외 문구의 의미와도 일치하지 않을 수 있다.

### 최소 수정 방향과 회귀 테스트 제안

- 제외 적용 가능성은 단어 포함이 아니라 실제 제외 술어·문구와 질문 조건의 의미 관계로 확인하고, 제외가 확정되지 않으면 답변을 반전하지 않는다.
- 제외를 강제할 때도 Evidence quote가 해당 행위를 **제외한다고 명시**하고, 같은 benefit 소유인지 확인한다. 긍정 혜택 제목만 포함한 quote는 제외 근거로 쓰지 않는다.
- 실적 구간 한도 문장은 단일 고정 월 한도 검사와 분리하고, 조건·한도 행 매핑이 구조화되거나 PDF 원문 행을 검증한 경우에만 관계를 통과시킨다.
- 테스트: (a) 4대 PAY 추가 5%와 공유 한도 질문은 원 의미 유지, (b) “추가”가 포함된 진짜 제외 질문은 실제 제외 Evidence가 있을 때만 제외 문장 생성, (c) 한도 Evidence가 여러 구간일 때 정상 구간 쌍 통과, (d) 소유권이 다른 Evidence 및 근거 없는 구간 쌍은 차단, (e) 후속 exclusion guard가 검증된 positive point를 뒤집지 않음.

## 3. CARD10-056 — 올바른 구간·한도 point 탈락

질문은 SHOPPING 오프라인 월 한도와 건당 할인 대상액을 묻는다. Hybrid 후보에 혜택 `20261104_000015`가 있고 Interpret가 `card_product_item:6:20261104_000015`를 선택했다. Retrieve는 benefit 상세와 Evidence를 반환했다.

### 검증 전·후

**Answer LLM 원본:**

> 전월 국내 가맹점 이용금액이 30만원 이상 70만원 미만이면 오프라인 월 할인한도는 6천원, 70만원 이상 120만원 미만이면 1만 2천원, 120만원 이상이면 2만 4천원입니다. 건당 할인 대상 금액은 5만원까지이며, 예시에서는 10만원 결제 시 5만원에 대해서만 할인을 적용합니다.

첫 번째 point는 30만~70만원 미만→6천원, 70만~120만원 미만→1만2천원, 120만원 이상→2만4천원을 명시하고 Evidence `20261104_001790`(실적 구간)과 `20261104_001791`(오프라인 한도)을 인용했다. 두 번째 point는 건당 5만원 대상액을 `20261104_001793`(10만원 결제 시 5만원만 10% 할인)으로 뒷받침했다.

**검증 후:**

> 오프라인 월 할인한도는 전월 실적 구간에 따라 6천원·1만 2천원·2만 4천원이고, 건당 할인 대상 금액은 5만원입니다.
> 건당 할인 대상 매출액은 5만원이며, 10만원 결제 시 5만원에 대해서만 10% 할인을 적용하는 예시가 있습니다.

첫 번째 구간별 한도 point는 제거됐다. 결론에는 한도 금액 목록만 남았지만 각 실적 구간과 어느 한도가 대응되는지 보존되지 않았다. 최종 points에는 5만원 건당 대상액만 남았고 최종 근거 ID도 `20261104_001793`뿐이다. 최종 상태는 PARTIAL이다.

### 실제 조건 및 영향

탈락 조건은 CARD10-032와 같은 `limit_tier_answer_problem()` 경로다(`validate_answer():1742–1746`, `limit_tier_answer_problem():2001–2053`). 현재 Benefit 표현에는 이 항목의 `tier_mappings`/구조화 `limit_tiers`가 없다. 월 한도 텍스트 안 여러 금액은 단일 고정 한도 집합으로 추출되지 않으므로 `:2048–2053`의 동일 오류를 반환한다. 검증 결과 경고에는 `monthly cap is not a single fixed value in this benefit's limit text`가 실제로 기록됐다.

Evidence 행은 조건과 금액이 따로 분리된 quote지만, 같은 PDF 3페이지의 표에서 열·행 대응을 확인할 수 있고 평가의 Golden Answer도 그 쌍을 검증했다. 따라서 이 사례는 잘못된 LLM 답이 아니라, 표현 구조가 없는 표의 관계를 검증기가 읽지 못해 정상 point를 버린 사례다. 비구조화 다중 구간 한도 표를 쓰는 다른 카드에도 동일한 오탐 거부가 생길 수 있다. `transaction_tier_fallback()`은 결제 금액별 캐시백 규칙에 대한 함수이며 이 문항 결과에는 fallback 경고가 없어 직접 원인이 아니다.

**최소 수정 방향:** 검증기가 한도 문장 안의 각 조건·한도 연결을 검증할 수 있게 구조화 표 매핑을 제공하거나, 질문 단계에서 실제 PDF 행/열의 연결을 확인한 근거가 있을 때 그 관계를 검사 대상으로 사용한다. 여러 금액을 단순히 한 benefit의 값 집합에 넣어 매핑이 확인된 것으로 간주하면 안 된다.

**회귀 테스트 제안:** 위 세 구간의 정확한 대응 및 5만원 건당 할인 대상액을 독립 검증; 다른 카드의 구간 한도 mapping 테스트 유지; 금액을 서로 바꾼 잘못된 쌍, 혜택 간 Evidence 도용, 전월실적과 거래 금액 혼동은 계속 거부; 검증 후 point·answer_text·Evidence ID의 일관성 확인.

## 4. 후보 검색 및 Interpret 실패

| 문항 | Hybrid 후보 → Interpret | Retrieve / Answer | 확인된 실패 단계와 한계 |
|---|---|---|---|
| CARD10-001 | top-8에 평가 기대 혜택 4개 모두 포함: ONE PICK 편의점·카페 `20261101_000001`, STYLE 쇼핑 `20261101_000002`, ONE MORE 대중교통 `20261101_000003`, 놀이공원 `20261101_000004`. 그 외 기본적립 2개, POINT II 추가적립, Two-in-One도 후보. 이번 전체 실행에서 Interpret가 선택한 ID는 빈 목록. | `retrieval_trace=[]`, Evidence 없음, Answer LLM 호출 없음. Interpret 호출만 기록(입력 3,363 / 출력 80 tokens). | 이번 전체 실행의 실제 실패는 **검색 후보 누락이 아니라 Interpret 선택 누락**이다. 앞선 2문항 시험에서는 후보 4개가 선택됐지만 Answer가 하나만 설명했다는 결과가 이전 대화에 보고되어 있다. 그 smoke 실행의 원시 Interpret 응답·후보·선택 ID는 현재 저장 파일에 없어 두 호출의 세부 입력·sampling 설정 차이는 입증할 수 없다. 확인 가능한 차이는 새 LLM 호출의 선택 결과다. 모델 기반 다중 항목 질문 응답이 호출마다 달라진 관측이며, 전체 목록을 빠짐없이 선택하라는 보장/후속 완전성 검사가 약한 것이 우선 점검 지점이다. |
| CARD10-051 | 후보에 ONE PICK의 4개 혜택 노드는 포함되지만 카드 결제계좌 요건은 후보 설명으로 나타나지 않음. Interpret 선택은 빈 목록. | Retrieve와 Answer 없음. PDF Evidence 없음. | 질문 사실은 상품 설명서의 카드 수준 메타데이터(“하나은행 계좌에 한하여 이용”)다. 혜택 노드 중심 top-8 후보에 카드 수준 속성이 노출되지 않아 발견되지 않았다. Hybrid candidate/catalog 데이터 계약에 카드 속성이 있는지 또는 전용 TERMS 경로가 이 질문을 다루는지 점검할 필요가 있다. |
| CARD10-058 | 후보에는 EVERY WON POINT 기본 적립 `20261105_000104`가 포함되며 이를 선택했다. 온라인 간편결제 추가 2% 혜택은 후보에 없었다. | 기본적립 상세만 Retrieve(규칙 1, 조건 1, 한도 1, Evidence 5). raw Answer는 “추가 적립 대상 확인 불가”, points 0, 인용 없음. | 평가 세트의 `benefit_id`는 null, `benefit_ids=[]`다. 따라서 0.8% 기본 적립 ID를 질문의 정답 ID로 잘못 기입한 것이 아니다. Golden의 읽기 전용 cross-check는 ID `20261105_000104`가 기본 적립이며 Evidence `20261105_002778`도 추가 2%가 아니라 기본 적립 한도라고 명시한다. 공식 PDF p.2는 추가 2%·대상·40만원 조건·1만/2만 포인트를 확인한다. 다만 저장된 DB snapshot은 추가 적립에 연결된 별도 원장/Neo4j Benefit ID가 없음을 보여 줄 뿐, PostgreSQL 실제 원장에 미연결 별도 행 자체가 없는지까지 입증하지 않는다. 원천 혜택 행과 Evidence 링크 확인 전 별도 ID를 추정하면 안 된다. 분류는 검색 실패 + DB 매핑 미확정이며, 평가 ID null은 이 불확실성을 표시한 것으로 보인다. |
| CARD10-059 | top-8은 라운지, 컨시어지, 골프/아울렛 등이며 JADE Classic 프리미엄 바우처가 없음. Interpret는 아무 혜택도 선택하지 않음. | Retrieve/Answer/Evidence 없음. | 공식 PDF p.2에는 바우처 5종 중 연 1회 선택, 1차년도 발급 후 50만원, 이후 제공기간 직전 1년 600만원 조건이 직접 확인된다. 검색 결과에서 바우처가 누락된 것은 확실하지만, 저장된 상위 8건만으로 Neo4j 노드가 아예 없는지 또는 top-8 밖으로 밀렸는지 결정할 수 없다. 전 카탈로그 조회 자료를 보존해 이 둘을 분리해야 한다. |

현재 N-mode 코드에서 후보는 `neo4j_hybrid_search.py:90`의 `search()` 경로로 전달되고, `CardGraphRAG.interpret()`에서 후보 카탈로그를 prompt로 만들고(`card_graphrag.py:2429` 이후), LLM이 반환한 ID 중 실제 catalog에 있는 것만 유지한다(`:2472–2511`). 선택된 key가 없으면 `after_interpret()`이 Retrieve 대신 finish로 보낸다(`:2570–2574`). 이 경로 때문에 001/051/059는 답변 LLM을 호출할 기회도 얻지 못했다.

## 5. 평가 데이터 문제와 애플리케이션 문제 분리

### CARD10-015 — Golden 대상 결제 수단 목록 오류

- Golden JSON(`golden_answer_set_50.json`, CARD10-015)의 `expected_answer`는 `우리WON페이·네이버페이·카카오페이·SSGPAY`이고 `expected_facts.must_include.TARGET`/`eligible_targets`도 같은 목록이다.
- Golden에 첨부한 공식 POINT II PDF 문서 `20261105_000043`, SHA-256 `0a4da23acb9a331182f15aa2591314cb2116a5a7ea40092b57932004612e973d`, 3페이지 원문은 “네이버페이, 카카오페이, PAYCO, SSGPAY”라고 한다. Evidence `20261105_002738`도 동일 목록이다.
- 따라서 Golden에서 `우리WON페이`는 제거하고 `PAYCO`를 넣어야 한다. 정정 대상 필드: `expected_answer`, `expected_facts.must_include.TARGET`, `expected_facts.targets`, 상위 `eligible_targets`. 이번 분석 단계에서는 수정하지 않았다.
- 실행 답변은 네이버페이·카카오페이·PAYCO·SSGPAY를 출력해 PDF와 일치한다. 기존 판정 CORRECT는 공식 PDF 기준으로 타당하며, 이것은 평가 데이터 결함이지 애플리케이션 오류가 아니다.

### CARD10-058 — 질문 Benefit ID 미확정

- 질문 세트의 `benefit_id=null`, `benefit_ids=[]`; Gold도 같은 null 값이다. 질문은 추가 2% 적립을 요구하지만 유일하게 확인된 기존 ID `20261105_000104`는 기본 0.8% 적립이다.
- Gold cross-check에는 추가 적립에 매핑된 Neo4j Evidence가 없고, `20261105_002778`은 기본 적립 근거라고 적혀 있다. 공식 PDF에서 답 자체는 VERIFIED지만 source data→benefit 연결은 미확정이다.
- 분류: 평가 행의 ID를 잘못 기입한 오류로 단정할 수 없다. 현재는 “원장/Neo4j에 연결 가능한 혜택 ID를 확정하지 못해 null로 보류한 평가 매핑”이다. 동시에 실행기는 잘못된 기본적립 후보를 선택하고 추가 2% 질문에 맞는 관련 후보를 검색하지 못했다. 실제 DB에서 별도 혜택 행이 없다는 결론은 이 결과 파일만으로 낼 수 없다.

## 6. PARTIAL 9건 / WRONG 7건 전체 분류

복수 원인이 가능한 표다. `Answer`는 생성된 내용·질문 범위 누락, `검증`은 정상 point 변형/탈락, `검색·선택`은 후보/Interpret 단계, `평가·데이터`는 Gold/ID/원장 연결, `Evidence 의미`는 인용문이 사실의 진위를 의미적으로 뒷받침하는지 가리킨다.

| 문항 | 판정·기록된 실패 단계 | 원인 유형 및 확인 내용 |
|---|---|---|
| CARD10-008 | PARTIAL · answer_content | Answer 범위 누락: 1.5%/200만원은 설명했지만 Golden의 국내 가맹점 적용 범위가 빠짐. 인용 연결 구조는 통과했다. |
| CARD10-011 | PARTIAL · answer_and_validation | Answer에 온라인 10%·4PAY 추가 5%·15% 합산 사실이 있었으나 최종에서 추가할인 point가 제거됨. 진단에는 근거 없는 15% 판정 및 한도 point 문제 경고가 남음. |
| CARD10-019 | PARTIAL · answer_content | 국내외 0.8%와 Two-in-One 체크 0.3%를 제시했지만 “0.8% 또는 0.3%, 나머지는 미확정”으로 일반 결제의 규칙을 모호하게 표현. Gold/PDF에는 기본 할인과 체크매출 예외가 구분됨. |
| CARD10-024 | PARTIAL · fee_answer_path | 연회비 대체 경로가 가족카드 연회비만 출력하고, 질문 및 Gold가 요구한 본인/가족·브랜드별 총액 전체를 제공하지 않음. 평가 PDF 추출 행 일부는 검토 대기 상태. 답변 범위/fee 데이터 완전성 문제. |
| CARD10-032 | WRONG · validate_answer | 검증 단계에서 올바른 답변 포인트 탈락, 후속 exclusion 강제에서 의미 반전. 2절의 상세 분석 참조. |
| CARD10-034 | PARTIAL · answer_content | PDF는 가족카드 연회비 미청구만 명시한다. Answer의 “별도 적용 조건 없음”은 부재를 확정하는 표현이며 원문 인용이 그 부재까지 입증하지 않음. 상태/조건 사실 과잉 추론. |
| CARD10-035 | PARTIAL · answer_content | 30·60·120만원 threshold와 1·2·5만원 caps를 나열했으나 30~60 미만, 60~120 미만의 upper bound가 빠짐. PDF 표와 Gold에서 경계 구간이 중요함. 개별 수치는 Evidence가 있으나 답변 구간 완전성이 부족. |
| CARD10-038 | PARTIAL · answer_and_evidence | 답변 내용은 앱 결제, 건당 3만원, 전월 50만원, 5%, 한도까지 말했으나 인용 `20261105_002826`는 제외 조항 문구(멤버십/테이블오더/물품 구매 제외)다. 3만원/앱 결제의 positive 사실을 그 quote가 직접 뒷받침하지 않는 semantic citation mismatch. |
| CARD10-040 | PARTIAL · answer_content_and_validation | 0.8%, Two-in-One 0.3%, 실적/한도 없음은 근거가 있으나 “둘 중 어느 것이 적용되는지는 미확정”을 추가해 확정 가능한 기본/예외 관계를 불필요하게 보류. 검증기의 unresolved 표현 처리와 Answer의 모호화가 함께 작용. |
| CARD10-051 | WRONG · hybrid_candidate_miss | 카드 수준 결제계좌 속성이 혜택 top-8 candidate에 없고, Interpret 선택·Retrieve·Evidence가 모두 비어 있음. |
| CARD10-056 | PARTIAL · validate_answer | 정확한 tier-to-cap point가 `limit_tier_answer_problem()`의 비구조화 다중 cap 조건에서 제거됨. 3절 참조. |
| CARD10-058 | WRONG · hybrid_candidate_and_benchmark_mapping | 추가 2% benefit candidate/Evidence 연결 미확인. 실행은 기본 적립 ID 104만 검색·선택. Gold ID는 null이므로 ID를 임의 부여한 오류는 아니나 원장 매핑 자체가 해결되지 않음. |
| CARD10-059 | WRONG · hybrid_candidate_miss | 공식 PDF에는 바우처 답이 있으나 top-8에 관련 혜택이 없고 Interpret가 비선택. 노드 부재와 순위 밖은 현재 기록만으로 구분 불가. |
| CARD10-001 | WRONG · interpret_selection | 네 개 기대 혜택 모두 후보에 있었으나 전체 시험 Interpret 선택 0건. 이전 smoke에서 Answer가 1개만 설명한 문제와 함께 다중 혜택 완전성 보장 부족. |
| CARD10-010 | WRONG · interpret_selection | 연회비 질문에 top-8에서 연회비 대상이 확인되지 않아 선택·Retrieve·Answer가 없음. |
| CARD10-020 | WRONG · interpret_selection | 연회비 질문에서 적합한 연회비 후보를 선택하지 못해 Retrieve/Answer가 발생하지 않음. |

### 유형별 빈도 (중복 집계)

| 유형 | 해당 문항 |
|---|---|
| 검색 후보 누락/후보 단계 부족 | CARD10-051, 058, 059 |
| Interpret 선택 누락 | CARD10-001, 010, 020 |
| Retrieve 상세/Evidence 부족 또는 fact와 소유자 불일치 | CARD10-038, 058; CARD10-051/059는 선택 전 단계에서 중단 |
| Answer 내용 누락·모호화·범위 오류 | CARD10-008, 011, 019, 024, 034, 035, 038, 040 |
| validate/후처리가 정상 point를 훼손 | CARD10-011, 032, 040, 056 |
| Golden/평가 ID 문제 | CARD10-058은 미확정 ID 매핑(의도적 null), CARD10-024는 검토대기 fee 추출 범위 부족. CARD10-015의 Golden 오류는 기존 CORRECT 1건에서 발견됐고 실패 16건에는 포함되지 않음 |
| PDF Evidence의 의미상 불일치 | CARD10-032 반대 결론에 긍정 제목 quote 사용, CARD10-038 조건·금액 문장에 제외 quote 인용 |

구조 검사는 전체 인용 166개에서 ID·소유자·페이지·quote 연결 오류가 0건이라고 기록했다. 이는 ID/benefit owner 구조 일치를 의미하며, CARD10-032·038처럼 인용의 의미가 답변 사실을 지지한다는 보장은 아니다.

## 7. 우선 개선 권고

1. **P0 — 의미 반전 방지:** 제외 토큰 단순 겹침이 정답 point를 제거하고 부정 결론을 새로 만드는 경로부터 차단. validate 후 exclusion guard가 원래 의미를 뒤집지 않는 불변조건 테스트 필요.
2. **P0 — 표의 구간 매핑 검증:** `limit_tier_answer_problem()`의 단일 고정 한도 검사와 구간별 한도를 분리. 조건 행/금액 행이 별도 quote여도 검증 가능한 provenance mapping을 가져야 한다. 잘못된 매핑은 계속 거부.
3. **P1 — 질문 대상 coverage 보장:** 카드 혜택 목록형 질문에서 Interpret 선택의 completeness 검사, 카드 수준 속성(결제 계좌) 검색 가능성, 전체 catalog와 top-k 미포함의 구분, PDF Evidence 소유자 미매핑을 각각 계측.
4. **P1 — 근거의 의미 검증 및 답변 완전성:** positive/negative 인용 기능 구분, question 필수 fact 및 반복 구간의 경계 포함 여부 검증.
5. **P1 — 평가 자료 정정은 별도 승인:** CARD10-015 Golden target 필드 정정. CARD10-058은 원장 원천 행 및 Evidence 관계 확인 전 ID를 채우지 말 것.

## 8. Git/실행 변경 관련 주의

50문항 실행 당시 기준과 본 분석 당시 기준을 혼동하지 않는다. 평가 시점 소스 SHA는 위 1절의 평가 JSON에 기록된 값이다. 실행 후 `card_graphrag.py`에는 함수 독스트링 추가와 module docstring/주석 보강이 반영됐다(분석 시점 HEAD `78d8fb6`). Git diff는 독스트링·주석 추가/정정뿐이며 실행 로직 변경은 확인되지 않았다. 이 보고서는 실제 실행 결과를 그 변경 이후 재현한 것으로 간주하지 않는다. 이 문서 작성은 애플리케이션 로직, 평가 JSON/Golden, PostgreSQL 또는 Neo4j를 수정하지 않는다.
