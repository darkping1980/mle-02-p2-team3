# 신용·체크카드 GraphRAG 기술 적용 타당성 및 3일 MVP

- 작성자: Codex
- 작성일: 2026-10-28
- 조사 목적: 확정된 카드 비교 주제에서 실제 PDF 관계를 이용한 GraphRAG 설계와 3일 MVP 범위 검증
- 문서 버전: v1, 신규 독립 보고서
- 검증 상태: **PDF 페이지별 텍스트와 기존 소스 정적 열람**. PDF 페이지 이미지·표의 독립 시각 대조, 현재 판매 및 문서 최신성, Cypher 실제 실행, 3일 개발 실측은 하지 않았다.
- 검증된 사실: 아래 세 카드사 공식 상품설명서에서 OTT 결제조건·선택 팩·실적 제외를 페이지별 텍스트로 확인했다. 기존 레시피 소스에 Streamlit, LangGraph 흐름, 서비스·저장소, Neo4j 연결 및 테스트가 존재한다.
- 가설: 승인된 관계를 탐색 경로와 함께 제시하면 조건 비교와 교육 시연에 도움이 된다. SQL 대비 이해도·정확도·속도 우위와 3일 실현성은 측정하지 않았다.

## 1. GraphRAG 적용 최종 판정

**B. GraphRAG 교육 목적상 적합.** 정식 PDF에서 실증한 핵심 예시는 KB Youth Club 체크의 **OTT A팩과 통신 B팩의 월별 선택 제약**과, 하나 JADE Classic 및 KB Youth Club의 OTT별 결제 경로 제한이다. 여러 조항을 연결해 조건 적용 대상을 설명하는 1~3홉 탐색과 근거 검토는 교육 시연에 의미가 있다. 하지만 정규화된 SQL도 같은 결과를 만들 수 있으며, Neo4j가 더 빠르거나 정확하다는 실증은 없다.

**실행 조건:** 3일 시작 전 신용·체크 각 2종 이상, 2개 카드사의 허용 PDF를 확보해 페이지 이미지와 표를 대조하고 질문별 필수 관계를 승인해야 한다. 현재 본 보고서에서 독립적으로 텍스트를 확인한 것은 신용 2종 + 체크 1종, 2개사다. [KB 첵첵 체크 설명서](https://img2.kbcard.com/obj/card/download/01914__prdctOpmn_20260818.pdf)는 공식 링크의 3쪽 PDF에서 카드·쇼핑·간편결제 조건을 확인했으므로 **최소 4종 후보**로 쓸 수 있다. 다만 4종 모두 페이지 이미지 대조와 해당 질문의 전 관계 승인 전까지 데이터셋 완성은 아니다. 6종은 목표일 뿐, 검수 품질을 확보한 다음 추가한다.

## 2. 실제 카드 PDF 관계 분석

페이지는 PDF 파일 기준이다. 공식 원문에서 웹 추출된 텍스트를 확인했으며 시각 대조 전 관계는 ‘검토 후보’다. 발급 가능·현재 유효성은 미확인이다.

| 카드·원천 | PDF 원문에 근거한 관계 | 범위·주의 |
|---|---|---|
| [KB Youth Club 체크, 정식 상품설명서](https://img2.kbcard.com/obj/card/download/04124__prdctOpmn_20260330.pdf), 3쪽 | **1쪽** A팩 OTT는 넷플릭스·유튜브·티빙·스포티파이, 공식 홈페이지 정기결제, 인앱 제외; B팩은 이동통신 자동납부 및 패션 온라인몰. **2쪽** 두 팩 중 선택한 옵션만 제공·변경은 다음 달 1일 적용 | A팩 OTT와 B팩 통신은 **같은 월에 선택 팩을 통해 동시에 제공 불가**라는 문서 기반 추론. 영구 선택 불가나 카드의 모든 혜택 중복 금지가 아님. 1쪽 전월 20만원 조건·유예도 표시 |
| 같은 PDF, 2쪽 | 가맹점이 PG·간편결제 전용 가맹점으로 확인되는 경우 할인 대상 제외 | 가맹점 **분류 조건**이 붙은 공통 할인 규칙. 모든 간편결제 이용을 무조건 제외한다고 확대하지 않는다. 1쪽 편의점 혜택은 오히려 KB Pay 이용 요구 |
| [하나 JADE Classic, 상품설명서](https://m.hanacard.co.kr/leaflet/14/14955_20260609.pdf), 6쪽 | **4쪽** 디지털 콘텐츠 자동납부·넷플릭스 등, 간편결제·앱스토어 결제 제외, 지난달 50만원 조건. **3쪽** 지정 온라인몰 공식 홈페이지·앱 조건 및 몰 이동 제외 | 해당 제외는 디지털 콘텐츠 혜택 범위. 문서 제목에 상품설명서 명시. 공식 경로는 `/leaflet/`이므로 담당 강사에게 허용 여부를 확인하고 별도 약관과 최신성을 확인한다 |
| [KB NEED Pay, 정식 상품설명서](https://img2.kbcard.com/obj/card/download/09800__prdctOpmn_20260330.pdf), 4쪽 | **1쪽** 디지털 콘텐츠·멤버십 공식 홈페이지 정기결제, 인앱·단건 제외, 간편결제 원칙적 제외 및 세 멤버십별 지정 페이 예외. **2쪽** 해당 카드 할인 적용 매출 실적 제외 | 예외의 대상 서비스와 페이의 쌍을 그대로 보존한다. 할인 적용 매출 전체 제외 규칙을 JADE나 체크카드에 전파하지 않는다 |
| [KB 첵첵 체크, 정식 상품설명서](https://img2.kbcard.com/obj/card/download/01914__prdctOpmn_20260818.pdf), 3쪽 | **1쪽** 텐바이텐 쇼핑은 직영 온라인몰/매장, 온라인 간편결제는 네이버·카카오·SSG페이, QR/바코드 등 제외; 전월 30만원 기준 | OTT 관련 조항이 없다고 전체 카드의 무혜택을 단정하지 않는다. 1쪽 표 구조 이미지 대조 필요 |

기존 자료의 WE:SH All+는 이미지 위주라 이번 조사에서 주요 조건을 독립적으로 판독하지 못했다. 따라서 사용하지 않는다. BC ZONE·동행은 공식 **리플릿**으로서 별도 상품설명서·약관 확인을 안내하므로, 강사가 별도 허용하기 전 MVP 근거에서 제외한다.

## 3. GraphRAG에 가장 적합한 사용자 질문

**Q1**이 가장 설득력 있다. Youth의 OTT와 통신을 따로 검색해 각 항목이 있다는 결과만 표시하면 같은 달 두 혜택이 함께 제공되는 것처럼 오해할 수 있다. A/B 팩 소속과 선택 제한을 함께 찾아 설명해야 한다. 다만 실제로 ‘두 혜택이 동시에 되는 후보’를 확정하기 위해서는 별도의 동시 제공 근거도 필요하다. **제약이 검색되지 않았다는 이유로 동시 가능이라고 표시하지 않는다.**

| 질문 | 공식 PDF·연결·경로 | SQL / 그래프의 역할 | 3일 시연 |
|---|---|---|---|
| Q1 OTT+통신·간편결제 | Youth의 OTT→A, 통신→B, A/B 선택 1개는 1~3홉의 개별 경로 조합. 체크 1카드의 제한은 확인; 조건을 모두 충족하는 신용 대안은 미검증 | SQL의 benefit·pack·selection_group 조인도 동일. 그래프는 두 팩 소속과 제한의 경로를 설명 | 1개 카드의 충돌은 가능; 복수 카드 동시 가능 비교는 승인 근거 확보 후 |
| Q2 신용→체크 | JADE 온라인몰·OTT와 Youth B팩 온라인몰·A팩 OTT는 각 2~3홉. 사용 중인 신용카드 미지정이면 개인의 유지 여부 불가 | SQL도 동등. 그래프는 공통 서비스와 서로 다른 팩 조건을 연결해 제시 | 정식 2문서의 제한적 비교 가능, 4종 완성은 검수 필요 |
| Q3 할인과 실적 제외 | NEED Pay 할인 적용 매출→전월실적 제외는 2~3홉. 다른 카드가 미기재라고 인정된다고 판단 불가 | SQL의 실적 규칙·범위 조인으로 동일. 그래프의 이점은 영향 받은 혜택과 원문 관계 표시 | NEED Pay 단일 문서의 설명 가능; 카드 간 차이 확정은 추가 검수 |
| Q4 선택·결제 충돌 | Youth A/B의 월별 택1, JADE 디지털 콘텐츠 간편결제 제외는 각각 실증. 서로 다른 충돌 유형·시점 구분 | SQL도 선택 그룹과 scoped rule로 동등. 그래프는 충돌 경로 설명 | 2가지 고정 사례만 가능 |
| Q5 신용·체크 OTT 인앱 제한 | JADE 디지털 콘텐츠, Youth A팩 OTT, NEED Pay 디지털 콘텐츠는 혜택별 인앱 제외. 각 카드→혜택→조건/결제방식 2~3홉 | SQL의 benefit·rule·method 조인으로 같은 표. 그래프는 공통 개념에서 혜택별 근거로 확장 | **최소 문서 2개**로 비교 시연 가능. 사례별 PDF 확인 아래 8절 |

Q1에서 ‘혜택 소속 팩이 다르다’는 것만으로 배타성을 확정하지 않는다. 별도의 선택 그룹 `max_selected=1`, 시점 `month`에 관한 승인 근거가 존재해야 충돌이다. Q5는 실증된 신용·체크 공통 질문을 완성형으로 보여 주기 쉽다. 따라서 **핵심 그래프 특징은 Q1의 팩 제약**, **끝까지 제시하는 비교 예시는 Q5**다.

## 4. Neo4j 노드·관계 설계

- `Card {id,name,kind,issuer}`: 이름·유형은 속성.
- `Benefit {id,name,category}`: 카드별 혜택 단위. 같은 OTT라도 카드마다 다른 노드로 범위를 분리.
- `Concept {id,name,kind}`: 반복 비교가 필요한 서비스·결제방식(예: 인앱결제, 넷플릭스)만 표준화.
- `Rule {id,kind,scope,qualifier,text}`: 제한·허용 예외·실적 규칙의 독립 주장. `scope`는 카드 전체가 아니라 `benefit`, `discount_group` 등으로 지정.
- `Pack {id,name}`와 `SelectionGroup {id,max_selected,period}`: Youth와 같은 실제 선택 제약에 한해 사용.
- `SourcePage {doc_id,url,sha256,page,quote,version}`: 문서 ID·페이지·원문 위치·버전 기록. 이미지 재검수 전 hash·version은 실제 취득값으로 채움.

관계: `Card-[:PROVIDES]->Benefit`, `Benefit-[:APPLIES_TO]->Concept`, `Benefit-[:HAS_RULE]->Rule`, `Rule-[:ABOUT]->Concept`, `Benefit-[:IN_PACK]->Pack`, `Pack-[:IN_GROUP]->SelectionGroup`, `Card-[:HAS_RULE]->Rule`. 각 사실 관계에 `approved=true`, `source_id`, `quote`를 두고 `source_id`로 `SourcePage`에 결합한다. Neo4j에서는 **관계가 다른 관계를 직접 가리킬 수 없으므로** 별도 사실 노드를 도입하지 않는 MVP에서는 관계 속성의 source_id와 페이지 노드 키를 결합한다. 각 edge에 독립 출처가 필요하다. 복합 사실이 출처 여러 개를 가져야 할 때는 `source_ids` 배열 또는 별도 Assertion 노드로 확장한다.

**범위:** JADE의 디지털 콘텐츠 인앱 제외는 `Benefit→Rule→인앱`으로 표현한다. Youth의 PG·페이 전용 가맹점 분류에 따른 공통 할인 제외는 `Card→Rule→가맹점 분류`이며 qualifier에 분류 전제를 기록한다. 공통 규칙과 혜택 규칙을 모두 함께 출력하되, 둘을 일반적인 ‘간편결제 무조건 제외’로 합치지 않는다.

**선택 제약:** Youth의 A·B를 동일 `SelectionGroup(max_selected=1, period='month')`에 넣고 2쪽 원문으로 각 소속·그룹 규칙을 증명한다. A OTT와 B 통신의 소속은 1쪽으로 각각 증명한다. 팩 간 `MUTUALLY_EXCLUSIVE_WITH`는 독립 사실처럼 임의 생성하지 않고 그룹 제한에서 계산한다. A/B 팩이 각자 공통으로 가진 편의점 혜택은 별도 혜택 노드로 표현한다. 사용자의 선택·기간이 미입력일 때 실제 선택을 단정하지 않는다.

`Card→Benefit→Rule→Concept`은 3홉, `Card→Benefit→Pack→SelectionGroup`은 3홉이다. 공통 노드를 거쳐 두 카드를 연결하는 전체 경로가 4홉 이상이면 이를 억지로 3홉이라고 부르지 않는다. 카드별 2~3홉 결과를 애플리케이션에서 합친다. 비교 결과에서 직접 카드 간 관계는 새로 만들지 않는다.

## 5. 실제 Cypher 탐색 예시

아래는 **설계 예시**이고 Neo4j에 적재·실행하지 않았다. 각 관계의 승인 속성과 source_id를 저장한 상태를 전제로 한다. 결과가 없으면 ‘없음’이 아니라 ‘승인 근거 미확인’이다.

### 혜택별 인앱 제외: 카드→혜택→규칙→결제방식, 3홉

```cypher
MATCH (c:Card)-[p:PROVIDES]->(b:Benefit)-[h:HAS_RULE]->(r:Rule)-[a:ABOUT]->(m:Concept {id: 'in_app'})
WHERE p.approved = true AND h.approved = true AND a.approved = true
  AND b.category = 'OTT' AND r.kind = 'EXCLUDES'
MATCH (sp:SourcePage {id: p.source_id})
MATCH (sh:SourcePage {id: h.source_id})
MATCH (sa:SourcePage {id: a.source_id})
RETURN c.name AS card, c.kind AS card_type, b.name AS benefit,
       r.text AS restriction, r.scope AS scope,
       sp.url AS benefit_url, sp.page AS benefit_page,
       sh.url AS rule_url, sh.page AS rule_page,
       sa.url AS method_url, sa.page AS method_page
ORDER BY card
```

상기 표준 `in_app`과 각 연결은 검토자가 실제 PDF의 앱스토어 또는 인앱 문구를 승인했을 때만 적재한다. `Rule.text`에 ‘자동납부’, 예외 등의 관련 맥락을 유지한다.

### Youth A/B 월별 선택 제약: 3홉 경로 두 개의 결합

```cypher
MATCH (c:Card {id: 'kb_youth'})-[p1:PROVIDES]->(a:Benefit {category:'OTT'})
      -[i1:IN_PACK]->(pa:Pack)-[g1:IN_GROUP]->(g:SelectionGroup)
MATCH (c)-[p2:PROVIDES]->(b:Benefit {category:'통신'})
      -[i2:IN_PACK]->(pb:Pack)-[g2:IN_GROUP]->(g)
WHERE pa.id <> pb.id AND g.max_selected = 1 AND g.period = 'month'
  AND all(x IN [p1,i1,g1,p2,i2,g2] WHERE x.approved = true)
MATCH (s1:SourcePage {id:i1.source_id})
MATCH (s2:SourcePage {id:i2.source_id})
MATCH (sg:SourcePage {id:g1.source_id})
MATCH (sg2:SourcePage {id:g2.source_id})
RETURN c.name, a.name, pa.name, b.name, pb.name,
       g.period, g.max_selected,
       s1.url, s1.page, s2.url, s2.page, sg.url, sg.page, sg2.url, sg2.page
```

팩 소속은 [Youth 1쪽](https://img2.kbcard.com/obj/card/download/04124__prdctOpmn_20260330.pdf), 선택·월별 변경은 2쪽이다. `PROVIDES`의 출처도 별도로 조회해 반환하도록 구현해야 한다. 이 쿼리는 검증된 **충돌**만 찾고, 결과가 없으면 동시 가능 여부는 미확인이다. 참고: [Neo4j OPTIONAL MATCH 공식 문서](https://neo4j.com/docs/cypher-manual/current/clauses/optional-match/).

## 6. 일반 RAG·SQL·GraphRAG 비교

같은 승인된 문서와 Q1/Q5를 기준으로 한다. 일반 RAG는 PDF 조각 검색과 LLM 답변, SQL·GraphRAG는 같은 사람이 승인한 구조화 사실과 페이지를 사용한다고 가정한다. 이 비교는 설계 평가이며 벤치마크가 아니다.

| 기준 | 일반 PDF RAG | 정규화 SQL + 조건 검색 | Neo4j GraphRAG |
|---|---|---|---|
| 정확성 | 관련 청크·팩 선택 조항이 함께 검색되는지와 답변 검증이 중요 | 범위·그룹·출처를 명시하면 규칙을 정확하게 조회 가능 | 같은 승인 데이터라면 SQL과 동일한 논리·정확도 가능. 추출·표현 오류는 여전히 존재 |
| 관계 표현 | 조각에 흩어진 팩 소속·제약을 조합해야 함 | 관계 테이블과 제약 그룹·조인·재귀 질의로 표현 | 카드→혜택→팩→선택 그룹의 경로가 모델에 직접 드러남 |
| 질문 확장 | 검색·프롬프트 및 평가셋 조정 | 조인·뷰·질의 추가; 재귀 SQL 가능 | 경로 패턴·조회 쿼리 추가. 자동으로 모든 질문 해결되지는 않음 |
| 출처 추적 | 청크와 페이지 메타데이터 | 사실·문서페이지 연결 테이블 | 관계별 source_id·페이지 노드; SQL도 동등하게 가능 |
| 복잡성·유지 | 간단한 입력 경로, 조합 답변 검증 부담 | 테이블·마이그레이션·승인 데이터 유지 | 그래프·제약·드라이버·승인 파이프라인 추가 |
| 3일 비용 | 상대적으로 낮음 | 중간, 팀 SQL 숙련도에 좌우 | 비교적 높음; 기존 Neo4j·LangGraph 구조 재사용과 사전 문서 검수에 의존 |
| 사용자 가치 | 설명 제공 가능 | 동일 근거 기반 비교표 제공 가능 | 탐색 경로 시각화·조건 출처를 보여줄 수 있음. 실제 이해 개선은 미측정 |

**개발 관점:** Neo4j 선택 이유는 데이터의 정확도·성능 우위가 아니라, 승인된 카드·혜택·팩·제약을 경로로 모델링하고 질문별로 추적·설명하는 교육 목표다. **사용자 관점:** A팩 OTT와 B팩 통신이 선택 그룹에서 만나 충돌한다는 경로 및 각 문서 쪽을 직관적으로 제시할 가능성이다. SQL도 같은 표와 설명을 생성할 수 있고, 동일 결과가 바람직하다. 두 방식의 실제 정확도·소요시간 비교는 수행하지 않았다.

## 7. LangGraph 처리 흐름과 사람 승인 설계

`PDF 로딩 → 후보 추출 → 원문 위치 확인 → 검토 대기 → 승인/수정/거절 → 승인 항목 저장 → 질문 분류 → 고정 Cypher → 근거 점검 → 답변`.

- **LangGraph:** 추출 성공·원문 매칭 실패·사람 검토 대기의 상태 전이와 분기. 검토 중 interrupt, 승인 후 같은 `thread_id`로 `Command(resume=...)` 재개. [LangGraph 공식 interrupts 문서](https://docs.langchain.com/oss/python/langgraph/interrupts/). 노드는 재개 시 처음부터 재실행될 수 있으므로 interrupt 전 쓰기 부작용을 피하고 이후 idempotent 키로 저장한다.
- **Checkpointer:** Streamlit 재실행이나 프로세스 재시작을 넘어 대기를 이어가려면 영속 checkpointer 필요. 단일 시연 세션만 보장하면 메모리 checkpointer도 가능하나 재시작 복구는 안 된다. 배포형 영속 체크포인터 구축은 3일 위험으로 보고 여건에 따라 선택한다.
- **Python:** 파일 해시, PDF 페이지 관리, 스키마 검증, SQL/그래프 쿼리 파라미터, 출처 일치 확인, 승격 트랜잭션과 템플릿 렌더링. 멀티에이전트 불필요.
- **LangChain:** PDF 로더·구조화 출력 모델·프롬프트 연결. 이미지 PDF는 OCR 결과를 후보 텍스트로 취급한다.
- **LLM:** 엔티티·관계·출처 후보와 정성 질문 범주 추출, 조회된 승인 근거만 사용한 설명 초안. 실제 출처·페이지의 진위와 조건 충족을 확정하지 않는다.
- **사람:** 페이지 이미지·표·단서의 수식 범위·문서 종류와 버전을 보고 승인·수정·거절. 수정 결과도 원문 대조 후 승인. 승인하지 않은 관계는 검색 DB에 저장하지 않는다.
- **Neo4j:** 승인된 사실과 출처를 보관하고 고정된 1~3홉 질의를 수행한다. 검토 대기 후보는 별도 JSON/SQLite 등에 저장하며 Neo4j에 미승인 관계가 들어가지 않도록 한다. 승인·적재는 문서 버전 및 idempotency key로 중복 방지한다.

## 8. 질문 1개에 대한 완성형 탐색·답변 시나리오

**선정 Q5 원문:** “OTT 혜택이 있는 신용·체크카드 중 인앱결제 제한이 있는 카드를 찾아서, 어떤 서비스에 적용되는 제한인지 비교해 줘.”

1. 질문 해석: `category=OTT`, `types=[신용,체크]`, `method=인앱`, `rule=제외`. 실제 소비·거래 금액 없음.
2. 5절 첫 쿼리로 `Card→Benefit→Rule→Concept(in_app)` 3홉을 각 카드별 탐색한다. 승인된 혜택명, 적용 대상, 원문 페이지를 모두 반환한다. `APPLIES_TO`로 각 혜택의 서비스 목록도 별도 조회해 근거를 연결한다.
3. **실제 문서에서 기대되는 결과(실제 DB 조회 결과 아님):**
   - JADE Classic 신용: 디지털 콘텐츠 자동납부의 넷플릭스·유튜브 프리미엄 등; 앱스토어 인앱과 간편결제 제외. [정식 PDF 4쪽](https://m.hanacard.co.kr/leaflet/14/14955_20260609.pdf).
   - Youth Club 체크: **A팩 OTT** 넷플릭스·유튜브·티빙·스포티파이, 공식 홈페이지 정기결제, 인앱 제외. B팩 통신과는 같은 달 택1. [정식 PDF 1~2쪽](https://img2.kbcard.com/obj/card/download/04124__prdctOpmn_20260330.pdf).
   - NEED Pay 신용: 디지털 콘텐츠·멤버십 정기결제의 인앱 제외와 지정 멤버십·페이의 간편결제 예외. [정식 PDF 1쪽](https://img2.kbcard.com/obj/card/download/09800__prdctOpmn_20260330.pdf). 예외는 간편결제 관련이며 인앱 예외로 바꾸지 않는다.
4. **충돌:** Youth는 A팩 OTT와 B팩 통신을 같은 달 함께 선택할 수 없다. JADE의 디지털 콘텐츠 간편결제 제외는 해당 혜택에 국한한다. 세 카드 모두 개인 결제의 실제 승인·할인 여부는 알 수 없다.
5. LLM에 전달할 구조화 결과 예시(원문 근거를 바탕으로 사람이 승인했다고 **가정**한 데이터, 아직 적재되지 않음):

```json
{"question":"OTT 인앱결제 제한 비교","results":[
 {"card":"JADE Classic","type":"신용","benefit":"디지털 콘텐츠","rule":"인앱결제 제외","scope":"디지털 콘텐츠","source":{"page":4,"url":"https://m.hanacard.co.kr/leaflet/14/14955_20260609.pdf"}},
 {"card":"KB Youth Club","type":"체크","benefit":"A팩 OTT","rule":"인앱결제 제외","scope":"A팩 OTT","source":{"page":1,"url":"https://img2.kbcard.com/obj/card/download/04124__prdctOpmn_20260330.pdf"}}
],"limits":["현재 판매 여부 미확인","PDF 이미지 대조·관계 승인 전"]}
```

이 JSON은 출력 스키마의 축약 예시이며 실제 구현에서는 각 혜택 대상·조건마다 개별 source_id·URL·페이지와 NEED Pay 예외를 추가한다. 누락된 조건을 LLM이 채우지 않도록 한다.
6. **최종 답변 예시:** “확인한 상품설명서에서 JADE Classic의 디지털 콘텐츠 적립과 Youth Club 체크의 A팩 OTT 할인은 모두 인앱결제 제한이 있습니다. JADE는 자동납부가 조건이고 앱스토어·간편결제 건을 해당 디지털 혜택에서 제외합니다. Youth는 공식 홈페이지 정기결제 조건이며, OTT가 A팩이라 통신 혜택이 있는 B팩과 같은 달 동시에 선택할 수 없습니다. 각 조건은 [JADE 4쪽](https://m.hanacard.co.kr/leaflet/14/14955_20260609.pdf), [Youth 1~2쪽](https://img2.kbcard.com/obj/card/download/04124__prdctOpmn_20260330.pdf)을 확인하세요. 이는 문서상 비교이며 현재 발급 여부나 개인 거래의 실제 혜택 적용을 뜻하지 않습니다.”
7. 표시 링크는 PDF URL과 파일 기준 페이지 번호를 함께 보여 주고, UI는 원문 발췌·버전·확인일을 연결한다. PDF 뷰어의 페이지 프래그먼트 지원 여부에 의존하지 않는다. 원본 표 이미지 대조 후 승인해야 시연 데이터로 쓸 수 있다.
8. 일반 RAG도 두 문서의 관련 구절을 검색해 같은 답을 만들 수 있으며, SQL도 관계와 페이지를 조인해 동일한 구조화 결과를 반환한다. 그래프는 각 혜택→제한 경로를 보여 주는 교육적 표현의 차이가 있다. 정확성 우위는 실험 전 미확인이다.

## 9. 기존 공통 구조 재사용 가능성

`C:\graph-rag\src\graph_rag\2_graphrag\과제_공공데이터로-그래프-만들기_금요일까지`를 읽기 전용으로 조사했다. 실행·테스트는 하지 않았다.

| 확인된 자산 | 재사용 가능성·신규 작업 |
|---|---|
| [streamlit_app.py](C:/graph-rag/src/graph_rag/2_graphrag/과제_공공데이터로-그래프-만들기_금요일까지/streamlit_app.py)와 Streamlit 테스트 | 화면 구성·서비스 주입 패턴 참고. 카드 질문·검토 UI·출처 표시 새로 필요 |
| [pantry_graphrag.py](C:/graph-rag/src/graph_rag/2_graphrag/과제_공공데이터로-그래프-만들기_금요일까지/recipe_recommender/pantry_graphrag.py) | `StateGraph` 입력 해석→조회→설명 패턴 존재. 후보 추출·승인 interrupt·checkpoint는 새로 설계; 기존 코드에 있다고 주장하지 않음 |
| [graph_question_service.py](C:/graph-rag/src/graph_rag/2_graphrag/과제_공공데이터로-그래프-만들기_금요일까지/recipe_recommender/graph_question_service.py), [recipe_graph_repository.py](C:/graph-rag/src/graph_rag/2_graphrag/과제_공공데이터로-그래프-만들기_금요일까지/recipe_recommender/recipe_graph_repository.py) | 고정 읽기 전용 Cypher, Service/Repository 패턴 참고. 레시피 스키마와 질의는 카드용으로 교체 필요 |
| [neo4j_connection.py](C:/graph-rag/src/graph_rag/2_graphrag/과제_공공데이터로-그래프-만들기_금요일까지/recipe_recommender/neo4j_connection.py), [config.py](C:/graph-rag/src/graph_rag/2_graphrag/과제_공공데이터로-그래프-만들기_금요일까지/recipe_recommender/config.py) | Neo4j 드라이버·TLS·환경 설정 패턴 확인. 환경·자격증명은 별도 설정 |
| `tests/test_pantry_graphrag.py`, `tests/test_graph_questions.py`, `tests/test_streamlit_app.py` | 단위 테스트·UI 테스트 구조 참고. PDF 승인 범위·출처·미승인 격리·선택제약의 새 테스트 필요 |
| 레시피 CSV/DB 로더 | CSV·기존 데이터 적재는 확인. 카드 공식 PDF 로더·OCR·표 검증·승인 워크플로가 구현됐다는 근거는 없음 |

기존 구조는 참고 또는 별도 복사 기반으로 재사용할 수 있으나 실제 호환성·실행 가능성은 미검증이다. 기존 소스는 수정하지 않았다.

## 10. 3일 MVP 구현 범위

**필수 기능 1개:** 정성 질문에 대해 승인된 여러 카드의 혜택·조건·예외를 탐색하고 페이지 근거와 함께 비교한다. **보조 기능 최대 2개:** 신용/체크 필터, 선택 팩 충돌 표시. 그래프 시각화는 필수 경로 설명을 간단한 텍스트로 대신하고 별도 기능에서 제외한다.

| 일차 | 구현·역할(2~3명) | 완료 기준·테스트 | 실패 위험 및 축소 |
|---|---|---|---|
| 1일 | A: 4 PDF 원문·페이지 이미지 검수, B: 그래프 스키마·연결, C: 추출 JSON·승인 UI(2명일 경우 A/C 병행) | 신용 2·체크 2, 2개사 문서 유형 확정; Q5 및 Youth 택1의 근거를 사람이 대조. 이미지 텍스트 추출의 행열·페이지 확인 | 이미지·폰트·2개사 부족 시 카드 수 4 유지하면서 질문 범위를 좁히고 데이터 검수에 시간을 쓴다. 4종이 안 되면 목표 미달을 명시 |
| 2일 | A: LLM 후보 추출과 검토, B: LangGraph 대기·승인 적재 및 1~3홉, C: Streamlit 질문 | 미승인·거절이 Neo4j에 없음; 수정 승인·중복 재개가 안전; Q5 두 유형을 페이지별 조회 | interrupt/영속 checkpoint 불안정 시 같은 세션의 메모리 checkpoint 또는 검토 대기 파일을 사용하고 재시작 지속성 미지원 명시 |
| 3일 | A: 원문 대조와 평가셋, B: 경로·출처 응답, C: UI·시연 | Q5와 Youth 택1 답변의 페이지·적용범위 확인. NEED Pay 인앱 vs 지정 멤버십 페이 예외, 미기재/누락, 다른 카드에 제외 전파 금지, 승인·거절 테스트 | LLM 실패 시 승인된 수동 후보 JSON을 사용한 탐색 데모. **자동 추출 성공으로 표현하지 않음**; 필수 LLM 추출의 미완료를 명시 |

OCR·폰트 문제가 있으면 로컬 PDF 렌더 → OCR 후보 → 사람이 페이지 이미지·표 행열 대조한다. OCR 실패 시 사람 수동 기록 후 같은 승인 절차를 사용한다. 이는 관계 탐색의 백업 시연이지 LLM 추출 요건의 충족이 아니다. 실제·가상 소비금액, 실적 판정, 절약액 계산, 결제 배분, 마이데이터, 런타임 크롤링, 멀티에이전트는 제외한다.

## 11. 기술적 위험과 대응책

- **문서 최신성:** 수집일·URL·해시·문서 종류·페이지를 남기고 현행 여부 미확인 표시. 정식 설명서와 리플릿 허용 여부는 강사에게 확인. 기존 OpenDART-only 제약도 별도 확인.
- **표·문맥 왜곡:** PDF 1쪽 표와 2쪽 팩 규칙을 시각 대조; 할인·적립·혜택 범위·유예·월별 선택을 각각 보존한다.
- **정보 부재:** 관계가 없어도 ‘없음/동시 가능’으로 추론 금지. 해당 문서와 범위에서 검수되지 않은 사실은 미확인.
- **승인과 재개:** 재시도 중 동일 관계의 중복·부분 적재 방지. 승인자·원문·판단을 후보 기록과 별도로 보존하고 승인 후 원자적 쓰기.
- **LLM 환각:** 결과의 모든 주장에 승인 출처가 있는지 기계적으로 확인하고 원문 없는 문장은 제외한다. 텍스트에 없는 보장이나 순위는 생성하지 않는다.
- **일정:** 이 보고서의 Cypher·LangGraph 설계는 구현·실행하지 않았다. 장비·모델·Neo4j 및 체크포인터가 준비되지 않았다면 3일 완료는 불확실하다.

## 12. 강사에게 설명할 GraphRAG 사용 근거 5문장

1. Youth Club 체크의 상품설명서는 OTT와 통신을 각각 다른 팩에 두고 월별로 한 팩만 선택하도록 규정한다.
2. 이 관계를 카드에서 혜택·팩·선택 그룹으로 따라가면 단순 혜택 검색에서 놓칠 수 있는 동시 선택 제한을 출처와 함께 설명할 수 있다.
3. JADE와 Youth의 OTT 인앱결제 제한도 각 카드의 해당 혜택에만 연결해 적용 범위를 보존할 수 있다.
4. SQL도 같은 결과를 만들 수 있으며 Neo4j의 교육적 선택 이유는 관계 추출·승인·경로 탐색과 근거 추적을 직접 시연하는 데 있다.
5. 3일 MVP는 검수된 신용·체크 최소 4종의 정성 비교와 사람 승인에 한정하며, LLM 추출과 PDF 페이지 검수가 완료되지 않은 부분은 그대로 미완료로 표시한다.
