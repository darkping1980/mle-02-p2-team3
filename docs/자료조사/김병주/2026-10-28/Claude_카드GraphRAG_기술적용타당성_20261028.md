# 카드 GraphRAG — 기술 적용 타당성 및 3일 MVP 설계

| 항목 | 내용 |
|---|---|
| 작성자 | Claude (Opus 5.5, Claude Code) |
| 작성일 | 2026-10-28 |
| 문서 버전 | v1 |
| 범위 | GraphRAG 적용 방식만 평가한다. 주제 채택 여부, 시장, 경쟁 서비스는 다시 다루지 않는다 |
| 소스 코드 | 수정하지 않았다. 기존 레시피 프로젝트는 읽기만 했다 |

**검증된 사실과 가설의 구분**

- **검증된 사실(V)**: 아래 6종 상품설명서 PDF를 2026-10-28에 카드사 공식 링크에서 내려받았다. 원문을 텍스트 추출과 페이지 이미지로 대조해 확인했다. 관계 표의 쪽수는 PDF 실제 페이지다.
- **가설(H)**: 사용자 체감 가치, LLM 추출 정확도, 3일 일정, LangGraph interrupt와 Streamlit의 연동 난이도. 실행으로 확인하지 않았다.
- **설계 예시(D)**: 노드·관계 이름, Cypher, SQL 스키마, LangGraph 흐름. 실제 PDF 사실을 담았지만 아직 구현하거나 실행하지 않았다.
- **다른 AI 보고서**: Codex 보고서는 PDF 후보(NEED Pay, KB ALL)를 찾는 단서로만 썼다. 관계는 모두 원본 PDF로 다시 확인했다.

---

## 1. GraphRAG 적용 최종 판정

**판정: B. GraphRAG 교육 목적상 적합 (A에 가까운 요소 포함)**

- **SQL로도 같은 답을 만들 수 있다.** 6종 카드, 수십 개 관계 규모에서 Q1~Q5의 정답은 정규화한 관계형 테이블과 조인으로 똑같이 나온다. 성능이나 정확도에서 GraphRAG가 우월하다는 근거는 없다.
- **그래도 이 데이터에는 그래프로 다루기 자연스러운 구조가 실제로 있다.** 모두 PDF로 확인했다.
  1. **월 단위 택1 선택 제약**
     - KB Youth Club: A팩/B팩
     - KB NEED Pay: 간편결제 4종 중 택1
  2. **같은 '간편결제 제외'라도 적용 범위가 다르다**
     - Youth Club: 카드 전체 할인
     - KB ALL·WE:SH All+: 쇼핑멤버십·OTT만
     - NEED Pay: 디지털콘텐츠·멤버십만
  3. **예외의 예외**
     - NEED Pay: 디지털콘텐츠·멤버십은 간편결제 시 제외지만, "네이버플러스–네이버페이, 컬리멤버스–컬리페이, 배민클럽–배민페이"는 혜택을 준다.
  4. **같은 '할인 적용 매출 실적 제외'라도 범위가 다르다**
     - NEED Pay: 카드의 할인 적용 매출 전체
     - KB ALL·WE:SH All+: 자동납부 할인분만
     - 나머지 3종: 미기재
- 이 구조는 **혜택 → 규칙 → 결제수단·서비스**로 이어지는 1~3-Hop 경로가 된다. 경로 자체가 "왜 이 조건이 걸리는지"에 대한 설명이자 출처 사슬이다.
- 또 관계 하나하나를 사람이 승인하는 과제 요구와 일대일로 맞는다. 그래서 **관계 추출 → 사람 검수 → 그래프 탐색 → 근거 추적**을 교육의 핵심으로 삼을 근거가 충분하다.
- A(적극 권장)가 아닌 이유는 두 가지다. 그래프가 SQL보다 답을 더 잘 만든다는 증거가 없고, 관계 규모가 작다.

---

## 2. 실제 카드 PDF 관계 분석

### 2.1 사용할 카드 (정식 상품설명서만)

| # | 카드 | 유형 | 공식 PDF | 쪽 | 문서 표기 | 텍스트 레이어 | SHA-256(16) |
|---|---|---|---|---|---|---|---|
| 1 | KB NEED Pay | 신용 | https://img2.kbcard.com/obj/card/download/09800__prdctOpmn_20260330.pdf | 4 | (상품설명서) A-20260227-9641-00775-00, 출시 2026-02-27 | **양호** | 711855dcb47b38ac |
| 2 | KB WE:SH All+ | 신용 | https://img2.kbcard.com/obj/card/download/09297__prdctOpmn_20260626.pdf | 3 | (상품설명서) A-20250331-9641-00722-01 | **이미지** | 3685543211b28b2c |
| 3 | KB ALL | 신용 | https://img2.kbcard.com/obj/card/download/09922__prdctOpmn_20260415.pdf | 3 | (상품설명서) A-20221226-9120-00632-02 | **이미지** | 81e48ca26c3ee189 |
| 4 | 하나 JADE Classic | 신용 | https://m.hanacard.co.kr/leaflet/14/14955_20260609.pdf | 6 | 1쪽 "제이드 클래식 상품설명서" (사이트 버튼명은 '상품약관보기') | 양호 | 1b4dcf06fca042f2 |
| 5 | KB Youth Club 체크 | 체크 | https://img2.kbcard.com/obj/card/download/04124__prdctOpmn_20260330.pdf | 3 | (상품설명서) B-20251208-9641-00763-00 | 양호 | 97174be2c9a7af2e |
| 6 | KB국민 첵첵 체크 | 체크 | https://img2.kbcard.com/obj/card/download/01914__prdctOpmn_20260818.pdf | 3 | (상품설명서) B-20200608-9162-00529-07 | 양호(1·2쪽) | bfcf0537973ff291 |

**사용하지 않는 문서**

- **BC 바로 ZONE·바로 동행:** 문서 제목이 '리플렛'이다. MVP 데이터에서 뺀다. 강사가 허용하면 보조로만 쓴다.
- **KB 노리2 Play·Global:** 이번에 원문을 확인하지 않았으므로 **미검증**이다.

### 2.2 그래프에 넣을 핵심 관계 (V)

| ID | 카드 | 관계 | 원문(발췌) | 쪽 | 확인 |
|---|---|---|---|---|---|
| N1 | NEED Pay | 간편결제 할인 → **4개 Pay 중 택1**(KB Pay 15%, 네이버·카카오·토스페이 10%) | "4개Pay 중 택1" | 1 | 텍스트+이미지 |
| N2 | NEED Pay | 선택서비스 → 월 단위, 월 1회 변경 | "선택서비스 변경 시 신청일 기준 다음달 1일부터 적용 (월 단위로 제공되며, 월 1회 변경 가능)" | 2 | 텍스트+이미지 |
| N3 | NEED Pay | 디지털콘텐츠/멤버십 30% → 대상 → 넷플릭스·유튜브·디즈니플러스·티빙·웨이브·스포티파이 / 네이버플러스·컬리멤버스·배민클럽 | 할인대상 표 | 1 | 텍스트+이미지 |
| N4 | NEED Pay | 디지털콘텐츠/멤버십 → 요구 → 공식 홈페이지 정기 이용권 / 제외 → 인앱·단건·포인트 충전 / 제외 → 간편결제 이용 시 | "인앱결제, 단건결제, 포인트 충전 등은 제외", "결제수단에 해당 카드 등록 후 결제 시 제공 (간편결제 이용 시 제외)" | 1 | 텍스트+이미지 |
| N5 | NEED Pay | N4의 간편결제 제외 → **예외** → (네이버플러스, 네이버페이), (컬리멤버스, 컬리페이), (배민클럽, 배민페이) | "단, 네이버플러스 멤버십–네이버페이, 컬리멤버스–컬리페이, 배민클럽–배민페이를 이용한 정기 결제 건은 간편결제 시에도 혜택 제공" | 1 | 텍스트+이미지 |
| N6 | NEED Pay | 네이버플러스를 네이버페이로 결제 → 간편결제 할인(네이버페이)과 **중복 가능** | "네이버플러스 멤버십을 네이버페이로 결제 시 자주 쓰는 간편결제 할인(네이버페이)과 중복 적용 가능" | 1 | 텍스트+이미지 |
| N7 | NEED Pay | 온라인패션몰 5% → 요구 → KB Pay / 간편결제 할인(KB Pay)과 **중복 가능** | "무신사, 지그재그, W컨셉, 29CM, 에이블리에서 KB Pay로 결제한 이용 건", "자주 쓰는 간편결제 할인(KB Pay)과 중복 적용 가능" | 1 | 텍스트+이미지 |
| N8 | NEED Pay | 전월실적 제외 → **카드의 할인 적용 매출 전체** | "'KB NEED Pay 카드' 할인 적용 받은 매출, (부분)무이자할부 이용금액, …" | 2 | 텍스트+이미지 |
| W1 | WE:SH All+ | 쇼핑멤버십 50%·OTT 10%·이동통신 5% → 같은 자동납부 묶음, 통합 월 한도 5천원, 전월 40만원 | "통합 월 할인한도: 5천원 (전월 이용실적 40만원 이상 시 제공)" | 1 | 이미지 |
| W2 | WE:SH All+ | 간편결제·인앱 제외 → **쇼핑멤버십·OTT에만** | "쇼핑 멤버십/OTT는 공식 홈페이지를 통한 정기 결제 건에 한함 (간편결제 및 인앱결제 등은 할인 제외)" | 1 | 이미지 |
| W3 | WE:SH All+ | 이동통신 → 제외 → 결합상품 | "이동통신 할인은 인터넷, IPTV 등 결합상품 할인 제외" | 1 | 이미지 |
| W4 | WE:SH All+ | 전월실적 제외 → **자동납부(쇼핑멤버십/OTT/이동통신) 할인분만** | "'KB WE:SH All+ 카드' 자동납부(쇼핑멤버십/OTT/이동통신) 할인 적용 받은 매출" | 2 | 이미지 |
| L1 | KB ALL | W1~W3과 같은 구조, 통합 월 한도 **3천원**, 전월 40만원 | "통합 월 할인한도: 3천원 (전월 이용실적 40만원 이상 시 제공)", "쇼핑 멤버십/OTT는 … (간편결제 및 인앱결제 등은 할인 제외)" | 1 | 이미지 |
| L2 | KB ALL | 전월실적 제외 → 자동납부 할인분만 | "KB ALL 카드 자동납부(쇼핑멤버십/OTT/이동통신) 할인 적용 받은 전체 이용금액" | 1 | 이미지 |
| J1 | JADE Classic | 디지털컨텐츠 50% **적립** → 대상 → 넷플릭스 등 9개 / 요구 → 자동납부 / 제외 → 간편결제·앱스토어(인앱)·개별 결제 | "자동납부 결제 건만 서비스 제공되며, … 간편결제 및 앱스토어를 통한 결제건(인앱결제)은 서비스 제외됨" | 4 | 텍스트+이미지 |
| J2 | JADE Classic | 특별적립 ↔ 기본적립 **중복 불가** | "특별 적립과 기본 적립은 중복 제공되지 않음" | 3 | 텍스트+이미지 |
| J3 | JADE Classic | 실적 제외 목록에 적립 적용 건 **미기재** | [공통] 실적 제외 대상 | 5 | 텍스트+이미지 |
| Y1 | Youth Club | OTT 50%는 **A팩**, 통신 30%·쇼핑멤버십 50%·온라인몰 20%는 **B팩** | 선택형(A팩/B팩) 표 | 1 | 텍스트+이미지 |
| Y2 | Youth Club | A팩 ↔ B팩 **월 단위 택1** | "서비스팩 2종 중 선택한 옵션에 대한 혜택만 제공", "월 단위로 제공되며, 매월 변경 가능" | 2 | 텍스트 |
| Y3 | Youth Club | OTT → 요구 → 공식 홈페이지 정기결제 / 제외 → 인앱·단건·충전 | "(인앱 결제, 단건 결제, 포인트 및 캐시 충전 등은 제외)" | 1 | 텍스트+이미지 |
| Y4 | Youth Club | **카드 전체 할인** → 제외 → PG·간편결제 전용 가맹점으로 분류된 결제 | "각 할인서비스는 … 결제대행업체(PG) 또는 간편결제 전용 가맹점으로 확인되는 경우 … 할인대상에서 제외됩니다" | 2 | 텍스트 |
| Y5 | Youth Club | 편의점 20% → **요구** → KB Pay | "오프라인 매장에서 KB Pay로 이용 시 제공" | 1 | 텍스트+이미지 |
| Y6 | Youth Club | 실적 제외 목록에 할인 적용 건 미기재 | 전월 이용실적 제외 대상 | 2 | 텍스트 |
| C1 | 첵첵 | 간편결제 영역 → 대상 → 네이버·카카오·SSG페이(온라인만) / 제외 → QR·바코드 등 | "온라인 가맹점 이용분만 할인(QR/바코드 결제, 카카오T, 택시 등 제외)" | 1 | 텍스트+이미지 |
| C2 | 첵첵 | **카드 전체 할인** → 제외될 수 있음 → PG·'할인 대상이 아닌 타' 간편결제 | "PG(결제대행) 업체 또는 할인서비스로 제공하지 않는 타 간편결제를 통한 결제 … 제외될 수 있습니다" | 2 | 텍스트 |
| C3 | 첵첵 | OTT·통신 혜택 **없음**, 실적 제외에 할인 적용 건 미기재 | 할인 표, 실적 제외 대상 | 1, 2 | 텍스트+이미지 |

**같은 단어가 다른 범위로 쓰이는 사례(V)**

| 표현 | 카드 전체에 적용 | 특정 혜택에만 적용 | 혜택의 조건으로 쓰임 |
|---|---|---|---|
| 간편결제 | Y4(Youth Club), C2(첵첵, '타' 간편결제) | W2·L1(쇼핑멤버십·OTT), N4(디지털·멤버십), J1(디지털컨텐츠) | Y5(편의점은 KB Pay 필수), N1(Pay 4종이 할인 대상), N7(패션몰은 KB Pay 필수), C1(간편결제 할인 대상) |
| 할인 적용 매출 실적 제외 | N8(NEED Pay) | W4·L2(자동납부 할인분) | — |

**설계 원칙:** 이 표가 이번 설계의 핵심 근거다. "간편결제 제외"를 카드 속성 하나로 저장하면 틀린 답이 나온다. 규칙마다 적용 범위를 따로 저장해야 한다.

---

## 3. GraphRAG에 가장 적합한 사용자 질문

| 질문 | PDF만으로 답 | 관계 연결 | 핵심 경로(Hop) | SQL 구조 | GraphRAG 추가 가치 | 3일 시연 |
|---|---|---|---|---|---|---|
| **Q1 복수 관심사 + 동시 선택 제약 + 간편결제** | **가능**(카드 6종) | 택1, 범위 있는 결제수단 제외, 예외의 예외, 통합 한도 묶음 | Card→Benefit→Choice←Benefit (3), Card→Rule→PaymentMethod + Rule→Benefit (2), Rule→Exception→Service/PaymentMethod (3) | `benefit`, `choice_option`, `rule`, `rule_scope`, `rule_target`, `rule_exception` 조인 | 충돌 이유와 예외를 **경로로 설명**, 관계마다 출처 | **가능(최우선)** |
| Q2 신용 → 체크 | 가능(다른 상품 간 비교. 보유 카드 미지정이므로 개인의 유지 여부는 판정 안 함) | 공통 Service 노드로 신용·체크 연결 | Card(신용)→Benefit→Service←Benefit←Card(체크) (4, 비교용 공통 노드) | 같은 service_id로 조인 | 보통. 비교표면 충분 | 가능 |
| **Q3 할인분 실적 제외 범위** | **가능**(명시 3: NEED Pay·WE:SH All+·KB ALL / 미기재 3) | 실적 제외 규칙의 범위(카드 전체 vs 자동납부 묶음) | Card→Rule(실적 제외)→Benefit (2) | `rule` + `rule_scope` | 범위 차이를 같은 패턴으로 보여줌 | **가능(보조)** |
| Q4 조건 충돌 | 가능(Youth 팩, NEED Pay Pay 택1, JADE 중복 불가, N6·N7 중복 허용) | Choice·중복 규칙 | Benefit→Choice←Benefit (2) | `choice_option` 자기조인 | Q1의 하위 기능 | Q1에 포함 |
| Q5 인앱 제한 비교 | 가능(WE:SH All+, KB ALL, NEED Pay, JADE, Youth의 OTT/디지털) | Rule→PaymentMethod(인앱), Rule→Benefit | Card→Benefit←Rule→PaymentMethod (2) | 단순 조인 | 거의 없음(SQL 동등) | 쉬움 |

**선정: Q1.** 택1 제약, 범위가 다른 결제수단 제외, 예외의 예외가 한 질문 안에서 동시에 필요하다. 그래서 그래프 경로 설명의 가치가 가장 잘 드러난다. Q3은 "규칙 범위"를 보여주는 보조 시나리오로 쓴다.

---

## 4. Neo4j 노드·관계 설계 (D)

### 4.1 최소 스키마

```
(:Card {card_id, name, issuer, card_type:'신용'|'체크', doc_id})
(:Document {doc_id, url, sha256, doc_kind:'상품설명서', revised, page_count})
(:Benefit {benefit_id, name, category:'OTT'|'통신'|'쇼핑멤버십'|'온라인쇼핑'|'간편결제'|…,
           kind:'할인'|'적립'|'환급할인', rate_text, cap_text, min_perf_text})
(:Service {name})            // 넷플릭스, 유튜브 프리미엄, SKT, 네이버플러스 멤버십, 무신사 …  (카드 간 공유)
(:PaymentMethod {name})      // 간편결제(일반), KB Pay, 네이버페이, 컬리페이, 배민페이, 인앱결제, 공식 홈페이지 정기결제, 자동납부, PG
(:Choice {choice_id, rule_text:'월 1개 선택', period:'월'})          // 택1 묶음
(:Rule {rule_id, kind:'결제수단 제외'|'결제수단 요구'|'실적 제외'|'중복 허용'|'중복 불가',
        scope:'card'|'benefits', certainty:'명시'|'될 수 있음', note})

(:Card)-[:DESCRIBED_IN]->(:Document)
(:Card)-[:OFFERS]->(:Benefit)
(:Benefit)-[:APPLIES_TO]->(:Service)
(:Benefit)-[:OPTION_OF {option:'A팩'|'KB Pay'|…}]->(:Choice)
(:Card)-[:HAS_RULE]->(:Rule)
(:Rule)-[:SCOPED_TO]->(:Benefit)           // scope='benefits'일 때만. scope='card'면 간선 없음
(:Rule)-[:TARGETS]->(:PaymentMethod)       // 제외·요구 대상 결제수단
(:Rule)-[:HAS_EXCEPTION]->(:Rule {kind:'예외 허용'})
(:Rule {kind:'예외 허용'})-[:FOR_SERVICE]->(:Service)
(:Rule {kind:'예외 허용'})-[:TARGETS]->(:PaymentMethod)
```

**출처와 승인 상태**

- 모든 Benefit·Rule·Choice 노드와 OFFERS·APPLIES_TO·OPTION_OF·SCOPED_TO·TARGETS 간선에 다음 속성을 붙인다.
  - `{doc_id, page, quote, status:'approved', extracted_by:'llm'|'manual', reviewer, reviewed_at}`
- 승인 전 후보는 Neo4j에 넣지 않는다. 후보 저장소(JSONL 또는 PostgreSQL)에만 둔다.
- 조회 Cypher에는 항상 `status='approved'` 조건을 건다.

**설계 판단**

- **속성으로 둔 것:** 할인율, 한도, 실적 금액, 연회비. 계산을 하지 않으므로 문서 문자열 그대로 저장한다.
- **만들지 않은 것:** SourcePage 노드. 페이지는 속성으로 충분하다. 노드로 만들면 Hop만 늘어나고 의미가 없다.
- **카드 간 직접 관계는 만들지 않는다.** 여러 카드에 같은 조건이 있다는 비교는 공통 Service·PaymentMethod 노드를 거쳐 조회한다.
- **택1은 Choice 노드로 표현한다.** 쌍마다 MUTUALLY_EXCLUSIVE 간선을 두면 NEED Pay의 Pay 4종만으로 6개 간선이 생긴다. Choice 하나에 OPTION_OF로 붙이면 4개 간선이면 된다. Youth Club은 A팩·B팩 혜택 12개가 Choice 하나에 `option` 속성으로 붙는다. 두 혜택이 같은 Choice에서 서로 다른 option이면 "동시 불가"로 판정한다.
- **적용 범위는 Rule.scope와 SCOPED_TO 간선으로 구분한다.**

| PDF 사례 | 그래프 표현 |
|---|---|
| Y4(Youth Club, 카드 전체) | `Rule{kind:'결제수단 제외', scope:'card'}`, TARGETS→`PaymentMethod{간편결제}`, `PaymentMethod{PG}`. SCOPED_TO 간선 없음 |
| W2(WE:SH All+, 일부 혜택) | `Rule{scope:'benefits'}`, SCOPED_TO→쇼핑멤버십 혜택, SCOPED_TO→OTT 혜택. **이동통신 혜택에는 간선 없음** |
| N5(NEED Pay, 예외의 예외) | 제외 Rule → HAS_EXCEPTION → `Rule{kind:'예외 허용'}` 3개. 각각 FOR_SERVICE(네이버플러스 등)와 TARGETS(네이버페이 등) |
| Y5·N7(조건으로 쓰이는 간편결제) | `Rule{kind:'결제수단 요구'}`, SCOPED_TO→편의점 혜택(또는 패션몰 혜택), TARGETS→KB Pay |

### 4.2 표준화

- **Service 이름은 표준화한다.** 예: "유튜브"와 "유튜브 프리미엄"은 승인 단계에서 같은 노드로 합친다. 원문 표기는 간선의 `quote`에 남는다.
- **PaymentMethod의 '간편결제(일반)'와 개별 Pay(KB Pay, 네이버페이 등)는 서로 다른 노드로 둔다.**
  - "간편결제 이용 시 제외"는 '간편결제(일반)'을 가리킨다.
  - "KB Pay로 결제 시 제공"은 'KB Pay'를 가리킨다.
  - 두 노드를 같은 것으로 합치면 Y5와 Y4를 구분할 수 없다.
  - 문서가 둘의 포함 관계를 정의하지 않으므로 **추론 간선(KB Pay IS_A 간편결제)도 만들지 않는다.**

---

## 5. 실제 Cypher 탐색 예시 (D, 실제 PDF 사실 기반)

**① Q1 — OTT와 통신을 같은 달에 함께 받을 수 있는가**

```cypher
MATCH (c:Card)-[:OFFERS]->(b1:Benefit {category:'OTT', status:'approved'}),
      (c)-[:OFFERS]->(b2:Benefit {category:'통신', status:'approved'})
OPTIONAL MATCH (b1)-[o1:OPTION_OF]->(ch:Choice)<-[o2:OPTION_OF]-(b2)
RETURN c.name AS card, c.card_type AS type, b1.name AS ott, b2.name AS telco,
       CASE WHEN ch IS NOT NULL AND o1.option <> o2.option
            THEN '동시 불가: ' + o1.option + ' vs ' + o2.option + ' (' + ch.rule_text + ')'
            ELSE '문서상 선택 제약 없음' END AS together,
       [b1.page, b2.page, ch.page] AS pages
```

예상 결과(PDF 사실 기준):

| 카드 | 결과 | 근거 |
|---|---|---|
| WE:SH All+ | 문서상 선택 제약 없음 | p1. 통합 월 한도 5천원은 별도 속성 |
| KB ALL | 문서상 선택 제약 없음 | p1. 통합 월 한도 3천원 |
| Youth Club | 동시 불가(A팩 vs B팩, 월 1개 선택) | p1, p2 |

OTT만 있는 NEED Pay·JADE, 둘 다 없는 첵첵은 이 MATCH에 걸리지 않는다. 별도 질의로 "통신 혜택 없음"이라고 표시한다.

**② Q1 — 간편결제 사용자에게 OTT 혜택에 걸리는 규칙과 예외 (범위 구분 포함)**

```cypher
MATCH (c:Card)-[:OFFERS]->(b:Benefit {category:'OTT'})
MATCH (c)-[:HAS_RULE]->(r:Rule {kind:'결제수단 제외'})-[:TARGETS]->(p:PaymentMethod)
WHERE p.name IN ['간편결제(일반)','PG','인앱결제']
  AND (r.scope = 'card' OR (r)-[:SCOPED_TO]->(b))
OPTIONAL MATCH (r)-[:HAS_EXCEPTION]->(x:Rule)-[:FOR_SERVICE]->(s:Service),
               (x)-[:TARGETS]->(pm:PaymentMethod)
RETURN c.name, b.name, p.name AS excluded, r.scope, r.certainty,
       r.page, r.quote, collect(DISTINCT s.name + '–' + pm.name) AS exceptions
```

- `r.scope='card'`인 Youth Club(Y4)과 첵첵(C2)은 카드 전체 규칙으로 잡힌다.
- `scope='benefits'`인 WE:SH All+·KB ALL·NEED Pay·JADE는 SCOPED_TO 간선이 OTT 혜택에 닿을 때만 잡힌다.
- NEED Pay는 `exceptions`에 "네이버플러스 멤버십–네이버페이" 등이 붙는다. 단 이 예외는 멤버십 서비스에 대한 것이고, OTT 서비스 자체에 대한 예외는 아니다. 답변에서 이 점을 구분해 보여준다.

**③ Q3 — 할인 적용분 실적 제외의 범위**

```cypher
MATCH (c:Card)
OPTIONAL MATCH (c)-[:HAS_RULE]->(r:Rule {kind:'실적 제외', target:'할인 적용 매출'})
OPTIONAL MATCH (r)-[:SCOPED_TO]->(b:Benefit)
RETURN c.name, c.card_type,
       CASE WHEN r IS NULL THEN '문서에 미기재'
            WHEN r.scope = 'card' THEN '카드의 할인 적용 매출 전체'
            ELSE '일부 혜택: ' + reduce(s='', n IN collect(b.name) | s + n + ' ') END AS scope,
       r.page, r.quote
```

예상 결과:

| 결과 | 카드 |
|---|---|
| 카드 전체 | NEED Pay(p2) |
| 일부 혜택(자동납부 쇼핑멤버십·OTT·이동통신) | WE:SH All+(p2), KB ALL(p1) |
| 미기재 | JADE(p5), Youth Club(p2), 첵첵(p2) |

---

## 6. 일반 RAG·SQL·GraphRAG 비교

같은 6종 PDF와 같은 Q1~Q5를 전제로 비교한다. SQL은 정규화, 관계 테이블, 자기조인, 필요하면 재귀 CTE까지 쓴다고 가정했다.

**SQL 대응 스키마(D)**

```
card, benefit, service, benefit_service, payment_method
choice(choice_id, rule_text), choice_option(choice_id, benefit_id, option)
rule(rule_id, card_id, kind, scope, target, certainty, page, quote, status)
rule_scope(rule_id, benefit_id), rule_payment(rule_id, payment_method_id)
rule_exception(rule_id, exception_rule_id), exception_service(exception_rule_id, service_id)
```

이 구조로 ①~③과 같은 결과를 조인으로 만들 수 있다.

| 평가 기준 | A. 일반 PDF RAG | B. SQL | C. GraphRAG(Neo4j) |
|---|---|---|---|
| 정확성(예외·범위 연결) | **낮음.** 청크마다 범위 문맥이 끊긴다. 예: "간편결제 이용 시 제외"와 "단, 네이버플러스–네이버페이…"가 다른 청크로 나뉠 수 있다. '미기재'를 '인정'으로 말할 위험도 있다 | **높음.** 승인된 행만 조회 | **높음.** 승인된 간선만 조회. **B와 같은 답** |
| 관계 표현 | 표현 없음 | 가능. 규칙 종류가 늘 때마다 연결 테이블이 늘어난다(6~8개) | 노드 7종·간선 9종으로 같은 내용. 예외의 예외는 간선을 하나 더 잇는 것으로 표현 |
| 질문 확장 | 프롬프트만 수정 | 새 규칙 유형 → 테이블·조인 추가 | 새 규칙 유형 → 간선 타입 추가, 기존 질의는 대부분 유지 |
| 출처 추적 | 청크 단위 | 행 단위(규칙·연결 행마다 page, quote) | 간선 단위. 질의가 반환하는 **경로 자체가 근거 사슬**이다 |
| 복잡성 | 가장 낮음 | 중간(조인이 많음) | 중간(Cypher 학습 필요) |
| 유지보수(카드 추가) | PDF 추가 후 재임베딩 | 추출 → 승인 → INSERT | 추출 → 승인 → MERGE. 공통 Service·PaymentMethod 노드에 자동 연결 |
| 3일 개발 비용 | 가장 쉬움 | 쉬움 | 중간. 기존 레시피 프로젝트의 Neo4j 코드를 재사용하면 줄어든다(9절) |
| 사용자 가치 | 답이 그럴듯하지만 근거·범위가 불안정 | 정확한 비교표 | 정확한 비교표 + "왜 안 되는지"를 경로로 보여주는 설명 |

**SQL로도 동일한 답을 만들 수 있다.** 아래 이유는 정확도나 속도가 아니다.

**Neo4j를 도입할 실질적인 이유 — 개발 관점**

1. **이질적인 규칙을 다루기 쉽다.** 이 데이터의 핵심은 혜택이 아니라 규칙이다. 택1, 범위가 있는 제외, 예외의 예외, 중복 허용·불가가 있고, 카드를 추가할 때마다 새 유형이 나올 수 있다. 예: 6종 중 NEED Pay에서만 예외의 예외가 나왔다. 그래프에서는 간선 타입을 추가하면 되고, 관계형에서는 연결 테이블과 조인을 추가해야 한다.
2. **사람 검수 단위와 저장 단위가 같다.** LLM이 만든 후보 "주어–관계–목적어 + 쪽 + 원문"을 승인하면 간선 하나가 된다. SQL은 후보 하나를 여러 테이블 행으로 나눠 넣어야 한다.
3. **경로를 그대로 반환할 수 있다.** 질의 결과인 `path`가 혜택 → 규칙 → 결제수단 → 예외의 순서를 담고 있어서, 답변 설명과 근거 표시에 바로 쓸 수 있다.

**Neo4j를 도입할 실질적인 이유 — 사용자 관점**

- 사용자는 DB 종류를 알지 못한다. 사용자에게 의미 있는 것은 "OTT와 통신을 같이 못 받는 이유: A팩–택1–B팩(p1·p2)"처럼 **조건이 연결된 이유를 원문 쪽수와 함께 보는 것**이다.
- 이 설명은 SQL로도 만들 수 있다. 다만 그래프는 경로 시각화(노드–간선 그림)를 같은 데이터로 바로 보여줄 수 있다. **이 시각화가 시연과 교육에서의 추가 가치다.**

---

## 7. LangGraph 처리 흐름과 사람 승인 설계 (D)

### 7.1 그래프 2개로 나눈다

**적재 그래프 (문서 1건 = 실행 1회, thread_id = doc_id)**

```
load_pages → extract_candidates → verify_quotes ─┬─(실패 다수)→ mark_manual → human_review
                                                  └─────────────────────────→ human_review
human_review (interrupt) → save_approved → END
```

**질의 그래프 (기존 레시피 PantryGraphRAG 구조를 재사용)**

```
interpret → retrieve → check_constraints → answer → validate_answer ─┬─(근거 이탈)→ fallback_template
                                                                       └→ END
```

### 7.2 역할 분담

| 작업 | 담당 | 이유 |
|---|---|---|
| PDF 페이지 텍스트 | Python(pypdf, 기존 `DocumentReader`) | 결정적 작업 |
| 이미지 페이지 처리 | 사람 전사 또는 비전 LLM. 결과에 `extracted_by` 표시 | WE:SH All+·KB ALL은 텍스트가 없다 |
| 관계 후보 추출 | LLM(LangChain `with_structured_output` + Pydantic 스키마) | 원문 → 구조화 |
| 원문 검증 | Python. `quote`가 해당 페이지 텍스트에 실제로 있는지 정규화 후 부분 문자열 비교 | LLM 환각 차단 |
| 범위(scope)·택1·예외 판정 | **사람이 반드시 검토** | 2.2절 표처럼 같은 단어가 범위만 다르다. LLM 오류가 가장 치명적인 부분 |
| 승인·수정·거절 | 사람(Streamlit `data_editor`) | 과제 요구 |
| 저장 | Neo4j(MERGE, 제약조건) | — |
| 질문 해석 | LLM + 어휘 사전(Service·PaymentMethod·category 목록으로 제한) | 레시피 프로젝트의 interpret 패턴 |
| 탐색 | Neo4j Cypher 템플릿(①~③) | 결정적 질의. LLM이 Cypher를 생성하지 않는다 |
| 제약 판정 | Python(`check_constraints`). Choice 옵션 비교, scope 필터 | 규칙 기반 |
| 답변 문장 | LLM. 구조화된 결과만 입력 | — |
| 답변 검증 | Python. 답변이 인용한 rule_id·benefit_id가 조회 결과 안에 있는지 확인. 없으면 템플릿 답변으로 대체 | 레시피 `validate_answer` 패턴 |

### 7.3 interrupt / checkpointer 평가

- **필요성은 있다.** 사람 승인 중에 실행이 멈춰야 한다. 또 Streamlit은 위젯을 조작할 때마다 스크립트 전체를 다시 실행한다. 그래서 상태를 체크포인터에 두고 `interrupt()` → `Command(resume=승인결과)`로 재개하는 구조가 맞다.
  - 개발용 체크포인터: `InMemorySaver`
  - 영속이 필요하면 의존성에 이미 있는 `langgraph-checkpoint-postgres`를 쓴다.
- **3일 대안(H):** interrupt와 Streamlit 연동이 1일 안에 안정되지 않을 수 있다. 그 경우 다음처럼 대체하고, 보고서에 사실대로 적는다.
  - 후보를 JSONL로 저장하고 `status` 열로 승인한다.
  - 승인 후 `save_approved` 함수만 호출한다.
- **멀티에이전트는 쓰지 않는다.**

---

## 8. Q1 완성형 탐색·답변 시나리오

모든 사실은 2.2절의 확인된 PDF 관계다. 쪽수는 PDF 페이지다. Neo4j 실행 결과가 아니라 **승인 데이터가 적재됐을 때의 예상 결과**다.

**1. 사용자 입력**

> "OTT와 통신비 혜택이 모두 필요한데, 두 혜택을 동시에 이용할 수 있는 신용카드나 체크카드를 알려줘. 간편결제를 자주 사용하는 경우 주의할 조건도 궁금해."

**2. 해석 결과**

```json
{"categories":["OTT","통신"], "require_together":true,
 "payment_habits":["간편결제(일반)"], "card_types":["신용","체크"]}
```

**3. 탐색 대상:** Card–OFFERS–Benefit(OTT·통신), Benefit–OPTION_OF–Choice, Card–HAS_RULE–Rule–SCOPED_TO/TARGETS, Rule–HAS_EXCEPTION.

**4. Cypher:** 5절의 ①과 ②.

**5. 검색된 관계와 출처**

| 카드 | OTT | 통신 | 동시 이용 | 간편결제 관련 규칙 | 출처 |
|---|---|---|---|---|---|
| KB WE:SH All+(신용) | 10% | 5% | 문서상 제약 없음. 쇼핑멤버십·OTT·이동통신 통합 월 한도 5천원 | 쇼핑멤버십·OTT만 간편결제·인앱 제외(통신에는 해당 문구 없음). 통신은 결합상품 제외 | p1 |
| KB ALL(신용) | 10% | 5% | 문서상 제약 없음. 통합 월 한도 3천원 | WE:SH All+와 같은 문구 | p1 |
| KB Youth Club(체크) | 50%(A팩) | 30%(B팩) | **동시 불가.** 월 1개 팩 선택 | 카드 전체: PG·간편결제 전용 가맹점으로 분류된 결제 제외. OTT: 인앱·단건·충전 제외 | p1, p2 |
| KB NEED Pay(신용) | 30%(디지털콘텐츠/멤버십) | **없음** | 해당 없음 | 디지털콘텐츠·멤버십: 간편결제 이용 시 제외. **단 멤버십 3종은 지정 Pay 정기결제 시 예외.** 간편결제 할인은 4개 Pay 중 택1 | p1, p2 |
| 하나 JADE Classic(신용) | 50% **적립** | **없음** | 해당 없음 | 디지털컨텐츠: 간편결제·인앱 제외 | p4 |
| KB 첵첵(체크) | **없음** | **없음** | 해당 없음 | 간편결제 자체가 할인 대상(네이버·카카오·SSG페이 온라인) | p1 |

**6. 충돌·제약**

- Youth Club: OTT와 통신이 서로 다른 팩이다. 같은 Choice에 다른 option으로 붙어 있으므로 "동시 불가"로 판정한다.
- WE:SH All+·KB ALL: 통합 한도를 공유한다. 이는 문서 조건으로만 표시하고, 금액은 계산하지 않는다.

**7. LLM 입력(구조화)**

```json
{"question_intent":{"categories":["OTT","통신"],"together":true,"habits":["간편결제(일반)"]},
 "rows":[
  {"card":"KB Youth Club 체크","type":"체크","ott":"b_y_ott","telco":"b_y_tel",
   "together":{"ok":false,"choice":"ch_y_pack","options":["A팩","B팩"],"pages":[1,2]},
   "rules":[{"rule_id":"r_y_pg","scope":"card","targets":["PG","간편결제(일반)"],"page":2,
             "quote":"결제대행업체(PG) 또는 간편결제 전용 가맹점으로 확인되는 경우 … 할인대상에서 제외"}]},
  {"card":"KB WE:SH All+","type":"신용","together":{"ok":true},
   "rules":[{"rule_id":"r_w_pay","scope":"benefits","scoped_to":["쇼핑멤버십","OTT"],
             "targets":["간편결제(일반)","인앱결제"],"page":1,
             "quote":"쇼핑 멤버십/OTT는 공식 홈페이지를 통한 정기 결제 건에 한함 (간편결제 및 인앱결제 등은 할인 제외)"}]}
 ],
 "not_offering_both":["KB NEED Pay(통신 없음)","하나 JADE Classic(통신 없음)","KB 첵첵(둘 다 없음)"],
 "rules_for_answer":["표에 없는 조건을 만들지 말 것","미기재는 '문서에 없음'으로 표현","금액 계산 금지"]}
```

**8. 사용자에게 보여줄 답변 예시**

> **OTT와 통신 혜택을 같은 달에 함께 받을 수 있는 카드(확보한 상품설명서 6종 기준)**
> - **신용카드: KB WE:SH All+, KB ALL.** 두 혜택이 같은 자동납부 할인 묶음에 있고, 문서상 선택 제약이 없습니다. 다만 쇼핑멤버십·OTT·이동통신이 통합 월 한도를 함께 씁니다(WE:SH All+ 5천원, KB ALL 3천원 / 각 p1).
> - **체크카드: 해당 카드 없음.** KB Youth Club 체크는 OTT(A팩)와 통신(B팩)이 서로 다른 팩이라 매달 하나만 선택할 수 있습니다(p1 표, p2 "서비스팩 2종 중 선택한 옵션에 대한 혜택만 제공").
>
> **간편결제를 자주 쓰신다면**
> - WE:SH All+·KB ALL의 OTT 할인은 공식 홈페이지 정기결제만 해당되고, **간편결제·인앱결제는 제외**됩니다. 통신 할인에는 이 문구가 없지만, 인터넷·IPTV 결합상품은 제외됩니다(p1).
> - Youth Club은 **모든 할인**에서 PG·간편결제 전용 가맹점으로 분류된 결제를 제외합니다(p2). 반대로 편의점 할인은 KB Pay로 결제해야 받습니다(p1).
> - 참고로 OTT만 필요하다면 KB NEED Pay도 있습니다. 디지털콘텐츠 결제는 간편결제 시 제외되지만, 네이버플러스·컬리멤버스·배민클럽을 각각 네이버페이·컬리페이·배민페이로 정기결제할 때는 예외입니다(p1).
>
> *할인 금액과 실적 충족 여부는 계산하지 않았습니다. 이 내용은 2026-10-28에 받은 상품설명서 기준입니다.*

**9. 원문 연결:** 답변의 각 문장 끝 쪽수 표시는 간선의 `doc_id`와 `page`에서 만든다. 클릭하면 PDF URL에 `#page=N`을 붙여 열고, `quote`를 함께 보여준다.

**10. 다른 방식과의 차이**

- **일반 RAG:** "Youth Club은 OTT와 통신 할인이 있다"까지는 찾는다. 그러나 p2의 택1 조항이 같은 청크에 없으면 "동시 이용 가능"으로 잘못 답할 위험이 크다. "간편결제 제외"의 범위(카드 전체 vs OTT만)도 섞기 쉽다.
- **SQL:** 같은 표를 만든다. 차이는 그래프가 경로(혜택 → 택1 ← 혜택, 규칙 → 범위 → 결제수단)를 그대로 돌려줘서 설명과 시각화에 바로 쓸 수 있다는 것뿐이다.

**부족한 관계(완성도 한계)**

- 통신 혜택이 있는 체크카드가 Youth Club 1종뿐이다. "체크카드 중 동시 이용 가능"이라는 답이 0건으로 나오는 것은 **데이터 범위의 한계**다. 시장 전체에 대한 결론이 아니라는 점을 답변에 반드시 표시해야 한다.

---

## 9. 기존 공통 구조 재사용 가능성

**확인 대상:** `src/graph_rag/2_graphrag/과제_공공데이터로-그래프-만들기_금요일까지/`. main 브랜치의 현재 파일을 읽기만 했고, 실행하지는 않았다.

| 구성 | 실제 파일 | 재사용 판단 |
|---|---|---|
| PDF 로더 | `common/document_reader.py` — pypdf로 `{"page_no", "text"}` 페이지 목록 생성 | **그대로 재사용.** 이미지 페이지는 별도 처리가 필요하다 |
| Neo4j 연결 | `recipe_recommender/neo4j_connection.py`(드라이버·CA), `common/neo4j_db_session.py`(쿼리 로깅 세션) | **재사용** |
| 쿼리 로그 | `common/query_logger.py` + tests | 재사용 |
| LangGraph 패턴 | `recipe_recommender/pantry_graphrag.py` — `PantryState`(TypedDict), `interpret → retrieve → answer` StateGraph, `create_llm()`, Pydantic 출력, `validate_answer`(근거 이탈 검사) | **구조 재사용, 내용 새로 작성.** 질의 그래프의 뼈대. interrupt·체크포인터는 기존에 없으므로 새로 만든다 |
| Repository/Service 계층 | `recipe_graph_repository.py`, `graph_question_service.py`, `*.cypher` 파일 분리 | 패턴 재사용. 카드 도메인 Cypher는 새로 작성 |
| Streamlit | `streamlit_app.py` — `@st.cache_resource` 파이프라인, 그래프 질문 탐색 화면, `session_state` 결과 유지 | 레이아웃·캐시 패턴 재사용. 승인 화면(`data_editor`)은 새로 작성 |
| 테스트 | `recipe_recommender/tests/*`(graph_questions, pantry_graphrag, streamlit_app 등) | 구조 재사용. 골든 질의 테스트를 새로 작성 |
| 설정 | `recipe_recommender/config.py`, `.env` 방식 | 재사용 |

**새로 만들어야 할 것**

- 카드 스키마·제약 Cypher
- 추출 Pydantic 스키마와 프롬프트
- 원문 검증 함수
- 승인 UI와 interrupt 흐름
- Q1·Q3 Cypher 템플릿
- `check_constraints`
- 이미지 페이지 전사 절차

**주의(V)**

- 메모 기록상 Streamlit은 venv에만 설치되어 있다.
- 페이지 렌더링용 PyMuPDF는 프로젝트 의존성에 없다(이번 검증은 별도 임시 환경에서 수행).

---

## 10. 3일 MVP 구현 범위

| 구분 | 기능 |
|---|---|
| **필수** | 정성적 관심사 질문 → 여러 카드의 혜택·조건·예외 관계 탐색 → PDF 쪽 근거와 함께 비교 답변(Q1 중심, Q3·Q5 템플릿 포함) |
| 보조 1 | **조건 충돌·동시 선택 제한 설명**(Choice와 범위 규칙) |
| 보조 2 | **관계 경로와 PDF 출처 시각화**(질의 결과 서브그래프 + 간선 클릭 시 원문) |
| 제외 | 금액 입력·계산, 실적 판정, 결제 배분, 마이데이터, 크롤링, 멀티에이전트, 카드 유형별 비교 화면(Q2는 질의로만 처리) |

**카드 범위**

- **최소 4종(텍스트 양호):** NEED Pay, JADE, Youth Club, 첵첵. 신용 2·체크 2, 카드사 2곳.
- **목표 6종:** + WE:SH All+, KB ALL(이미지 PDF, 전사 필요). Q1의 "동시 이용 가능" 결과는 이 두 카드가 있어야 나오므로, **최소 1종(WE:SH All+)은 1일차에 전사한다.**

**팀 역할(2~3명)**

| 역할 | 담당 |
|---|---|
| A | 데이터·추출·검수 |
| B | 그래프·질의 |
| C | Streamlit·LangGraph |

2명이면 B와 C를 합친다.

| 일차 | 구현 대상 | 담당 | 완료 기준 | 테스트 | 실패 위험 | 축소안 |
|---|---|---|---|---|---|---|
| **1일** | PDF 6종 고정(URL·해시·수집일) / 텍스트 4종 페이지 추출 / WE:SH All+ p1·p2 전사(`extracted_by:'manual'`) / Neo4j 스키마·제약 / 추출 Pydantic 스키마·프롬프트 / NEED Pay·Youth Club 후보 추출 | A: 추출·전사, B: 스키마, C: 승인 화면 골격 | 2개 문서 후보 생성, 원문 검증 통과율 기록 | `quote` 부분 문자열 검증 단위 테스트, 스키마 검증 | LLM이 범위(scope)를 틀리거나 택1을 놓침 | 2.2절 관계를 사람이 직접 JSON으로 작성(약 40개). 화면·보고서에 '수동 작성' 표시 |
| **2일** | 나머지 문서 추출 / 승인 UI(승인·수정·거절) / 적재 LangGraph(interrupt) / 승인분 MERGE / Cypher ①~③ / `check_constraints` | A: 검수, B: Cypher·골든 테스트, C: interrupt 연동 | 4종 이상 승인 적재, ①~③이 5절의 예상 결과와 일치 | 골든 질의 테스트(Q1·Q3·Q5 기대 행) | interrupt와 Streamlit 재실행 충돌 | JSONL + status 열 방식으로 대체(사실대로 기록) |
| **3일** | 질의 LangGraph(interpret → retrieve → check → answer → validate) / 답변·근거·경로 시각화 / 시연 리허설 / README에 자동·수동 구분 기록 | B: 질의 그래프, C: 화면, A: 시연 시나리오·검수 기록 | Q1·Q3 시연 성공, 모든 문장에 쪽수 | 답변 검증(인용 id ⊂ 조회 결과), 시나리오 3회 리허설 | LLM 답변이 표에 없는 조건을 추가 | 템플릿 답변(LLM 없이 표 + 고정 문장)으로 시연 |

**PDF 이미지·폰트 문제 대응**

- 페이지별 텍스트 길이로 이미지 페이지를 자동 판별한다. 예: 200자 미만이면 이미지 페이지.
- 이미지 페이지는 렌더링 이미지를 사람이 보고 전사하거나, 비전 LLM으로 후보를 만든 뒤 반드시 사람이 승인한다.
- 전사·비전 경로는 `extracted_by`로 구분하고, 화면에 표시한다.

**최소 대안**

- LLM 추출이 실패해도 사람이 검증한 관계 JSON으로 적재해 Q1·Q3를 시연할 수 있다.
- 이 경우 "자동 추출 성공"으로 소개하지 않는다. "추출 파이프라인은 n건 중 m건 성공, 나머지는 수동 검수 데이터"처럼 수치로 보고한다.

---

## 11. 기술적 위험과 대응책

| 위험 | 영향 | 대응 |
|---|---|---|
| 범위(scope) 오추출 | 가장 치명적. "간편결제 제외"가 카드 전체로 번지면 답이 틀린다 | scope·SCOPED_TO는 사람 승인 필수 항목. 골든 테스트에 Y4(카드 전체)와 W2(일부 혜택)를 함께 넣는다 |
| 이미지 PDF(WE:SH All+, KB ALL) | Q1 "동시 가능" 사례가 사라진다 | 1일차에 WE:SH All+ 전사 완료를 완료 기준에 넣는다 |
| 미기재를 인정으로 말함 | 오정보 | 미기재는 간선을 만들지 않는다. 답변 템플릿에 "문서에 없음" 문구를 고정한다 |
| Service·PaymentMethod 표준화 오류 | "간편결제(일반)"과 "KB Pay"를 합치면 Y4와 Y5가 충돌한다 | 사전(seed CSV)을 두고 승인 단계에서 매핑. 포함 관계 간선은 만들지 않는다 |
| interrupt와 Streamlit 연동 | 2일차 지연 | JSONL 승인 방식으로 대체 |
| 표 병합 셀(JADE p3) | 적립률과 대상이 잘못 연결된다 | 이미지 대조 체크리스트 |
| 데이터 범위 착시 | "체크카드 중 없음"을 일반화한다 | 모든 답변에 "확보한 상품설명서 N종 기준"을 고정 표시 |
| 문서 최신성 | 혜택이 개정된다 | `Document.revised`·`sha256`·수집일을 저장하고 화면에 표시 |

---

## 12. 강사에게 설명할 GraphRAG 사용 근거 5문장

1. 공식 상품설명서 6종을 대조해 보니, 카드 조건의 핵심은 혜택 목록이 아니라 혜택에 걸린 규칙이었습니다. 월 단위 택1(Youth Club A/B팩, NEED Pay Pay 4종), 범위가 다른 간편결제 제외, 예외의 예외(NEED Pay 멤버십–지정 Pay)가 그 예입니다.
2. 같은 "간편결제 제외"가 Youth Club에서는 카드 전체, KB ALL·WE:SH All+에서는 쇼핑멤버십·OTT에만 적용됩니다. 그래서 규칙과 그 적용 범위를 관계로 저장해야 정확한 답이 나옵니다.
3. 정답 자체는 SQL로도 똑같이 만들 수 있다는 점을 인정합니다. 그래프를 쓰는 이유는 속도나 정확도가 아니라 세 가지입니다. 규칙 유형이 늘어도 간선만 추가하면 되고, 사람이 승인한 관계 하나가 그대로 저장 단위가 되며, 조회 경로가 곧 "왜 안 되는지"에 대한 설명과 출처 사슬이 됩니다.
4. LangGraph는 추출 → 원문 대조 → 사람 승인(중단·재개) → 적재, 그리고 질문 해석 → 그래프 탐색 → 답변 근거 검증의 두 흐름을 관리합니다. 범위·택1·예외 판정은 반드시 사람이 승인합니다.
5. 3일 MVP는 텍스트가 양호한 4종에 이미지 PDF 1~2종을 사람이 전사해 더하고, "OTT와 통신을 함께 받을 수 있는 카드와 간편결제 주의 조건" 질문을 PDF 쪽 근거와 관계 경로로 시연합니다. 자동 추출과 수동 검수의 비율은 그대로 공개합니다.
