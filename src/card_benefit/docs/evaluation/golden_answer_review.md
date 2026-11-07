# Golden Answer 검토 메모

## 원천 및 읽기 전용 확인

- 지정 Notion 질문지를 직접 확인했습니다. 기존 CARD10-001~040의 질문 문구는 보존했고, CARD10-041~050의 3-hop은 제외했습니다.
- PostgreSQL read-only snapshot: `postgres`, PostgreSQL 17.11, `db_pipeline`; 카드 10, 문서 11, item 51, Evidence link 242. Neo4j read-only snapshot에서 51개 item을 확인했습니다.
- 최신 스키마 기준은 `src/card_benefit/docs/issue_analysis/postgresql_current_schema_20261107.sql`입니다. DB 식별 정보와 스키마 구조는 이 DDL 및 읽기 전용 원장 스냅샷과 함께 확인했습니다.
- 원장의 `doc_file_nm`을 기준으로 공식 PRODUCT_GUIDE PDF 10개를 찾고 SHA-256을 대조했습니다. 10/10 해시 일치.
- 카드의정석2 SIMPLE PDF는 추출 텍스트층이 없어 페이지 이미지를 직접 확인했습니다. Evidence 존재만으로 검증하지 않고 인용문을 대조했습니다.

## 집계

- 질문/정답: 50/50
- 1-hop 25 / 2-hop 25
- 신규 1-hop 5 / 신규 2-hop 5
- 상태: VERIFIED 40, NEEDS_REVIEW 10, NOT_IN_SOURCE 0
- 원장 item은 PENDING_REVIEW이며 PDF 기반 정답 검증 상태와 구분했습니다.

## NEEDS_REVIEW

- **CARD10-019** — PDF에서 시각 확인했으나 추출·원장에는 Two-in-One 0.3% 할인/캐시백 표기가 혼재하며 item 검토상태 PENDING_REVIEW.
- **CARD10-020** — PDF 이미지에서 확인했으나 현재 원장에 연회비 item/Evidence link가 없음.
- **CARD10-026** — PDF p.6의 50만원은 확인되나 PostgreSQL Evidence link가 서비스/횟수에 집중되어 조건 문구의 직접 귀속 확인 필요.
- **CARD10-030** — Evidence 002684는 대상 가맹점 일부를 인용. 제외 방식은 PDF에서 직접 확인했지만 Evidence 귀속/범위를 보완 검토해야 함.
- **CARD10-035** — PDF p.3 표의 행·열을 직접 확인. Evidence 추출은 셀 조각으로 나뉘어 표를 다시 펼쳐 확인해야 함.
- **CARD10-038** — PDF p.2 이미지에는 건당 3만원 이상, 전월 50만원 이상, 앱 내 카드결제가 직접 보이나 extracted Evidence link가 최소 거래조건에 연결되지 않아 수동 검토 필요.
- **CARD10-039** — PDF 이미지에서 전체 카테고리를 육안 대조했으나 OCR Evidence에 글자 오인식이 있어 원문 인용/연결을 수동 검수 대상으로 유지.
- **CARD10-040** — PDF 시각 판독상 0.3%는 청구할인, 일부 원장 문구는 캐시백으로 표현하여 지급방식 확인 필요.
- **CARD10-058** -- PDF p.2에서 직접 확인했습니다. 기존 Evidence 20261105_002778은 기본 적립의 무제한 한도를 인용하므로 이 답의 Evidence로 사용하지 않았습니다. 추가 적립의 원장/Neo4j 소유 관계는 별도 검토가 필요합니다.
- **CARD10-059** — PDF p.2에서 바우처 선택 횟수와 연차별 실적 조건을 확인했습니다. 현재 원장 Evidence의 바우처 혜택 소유 관계는 추가 확인이 필요합니다.

## PDF와 DB/Evidence 불일치

- CARD10-051 ONE PICK STYLE 결제계좌: PDF p.1에는 하나은행 계좌만 가능하다고 표시되나, 현재 PostgreSQL 상품 속성 및 Evidence 관계에는 이 안내가 별도 항목으로 등록되지 않아 PDF 근거로만 정답을 검증했습니다.
- CARD10-002 및 CARD10-004: 원장 PDF Evidence ID는 확인되지만 현재 Neo4j read-only snapshot에서 해당 연회비 Evidence와 카드 혜택 item의 관계가 반환되지 않았습니다. 답은 PDF로 확인했으며 Neo4j 근거 연결은 별도 점검이 필요합니다.
- CARD10-010 더 심플 연회비: PDF p.1에서 25,000원을 확인했으나 원장에 연회비 item/Evidence link가 없습니다.
- CARD10-020 카드의정석2 SIMPLE 연회비: PDF p.1 이미지에 본인 7,000원(국내전용/Mastercard), 가족카드 없음. 원장 item/Evidence link 누락.
- CARD10-019/039/040 SIMPLE: 이미지 기반 PDF이며 OCR 글자 오류가 있어 제외 조건의 세부 문구와 Two-in-One 0.3%의 지급방식은 수동 확인 대상입니다.
- CARD10-026 JADE First 주차: PDF p.6에는 50만원 조건과 월 2회가 직접 보이나 조건 Evidence의 관계 귀속은 보완 검토가 필요합니다.
- CARD10-030 더 심플 월납: 대상 가맹점 Evidence는 있지만 제외 결제방식 전부를 직접 입증하는 연결은 확인되지 않습니다.
- CARD10-035 POINT II: 30/60/120만원→1/2/5만원의 대응은 PDF 표 행·열을 직접 확인했습니다. 추출 Evidence는 각각 분리돼 수동 표 재검수 필요.
- CARD10-038 DAILY 배달앱: PDF p.2 이미지에서 매출 건당 3만원 이상, 전월 실적 50만원 이상, 공식 앱 내 카드결제 조건을 확인했습니다. 원장에는 food.delivery 규칙이 있지만 최소 거래금액 Evidence link가 보이지 않고 item이 PENDING_REVIEW여서 귀속 보완이 필요합니다.
- CARD10-058 EVERY WON POINT 온라인 간편결제 2% 추가적립: PDF에서 확인되나 PG item/Evidence는 기본 적립 중심이므로 별도 소유 연결을 검토해야 합니다.
- CARD10-059 JADE Classic 바우처: PDF p.2에서 연 1회/실적 조건 확인; 원장 Evidence 소유관계 추가 확인 필요.
- 이 산출물은 PDF 정답 기준이며 GraphRAG 실행 결과나 앱 품질 테스트가 아닙니다. 앱/LLM/DB write는 실행하지 않았습니다.

## 신규 문항

- `CARD10-051` (1-hop): ONE PICK STYLE 체크카드의 결제계좌는 어느 은행 계좌를 사용해야 해?
- `CARD10-052` (1-hop): 카드의정석 SHOPPING의 주말 주유 청구할인 금액은 얼마야?
- `CARD10-053` (1-hop): 카드의정석 POINT II의 가족카드 연회비 정책은 어떻게 돼?
- `CARD10-054` (1-hop): 카드의정석 SHOPPING의 브랜드별 연회비는 얼마야?
- `CARD10-055` (1-hop): 카드의정석2 DAILY의 국내외 가맹점 기본 할인은 얼마야?
- `CARD10-056` (2-hop): 카드의정석 SHOPPING 오프라인 쇼핑은 전월 실적 구간별 월 한도와 건당 할인 대상 금액 한도가 어떻게 돼?
- `CARD10-057` (2-hop): JADE Prime에서 월 적립 한도 소진 후의 1.0% 적립은 어떤 조건으로 적용돼?
- `CARD10-058` (2-hop): EVERY WON POINT의 국내 온라인 간편결제 추가 적립 대상과 전월 실적·월 한도는 어떻게 돼?
- `CARD10-059` (2-hop): JADE Classic 프리미엄 바우처는 몇 회 선택할 수 있고, 1차년도와 이후 연도의 실적 조건은 어떻게 돼?
- `CARD10-060` (2-hop): ONE PICK STYLE의 놀이공원 현장할인에 필요한 전월 실적과 월·연 이용 횟수는 어떻게 돼?

## 자동 무결성 검사

아래 항목은 실제 앱·GraphRAG 질문·LLM·DB 쓰기 없이 산출 JSON과 로컬 원문 PDF로 검사했습니다. 모두 통과했습니다.
- 평가 질문 50개, 정답 50개; question_id 50개 고유, 질문/정답 ID 집합 1:1 일치.
- 1-hop 25개, 2-hop 25개; 신규 1-hop 5개와 신규 2-hop 5개.
- 신규 문항의 기존 40문항 대비 정규화 완전일치 없음; 주제 중복도 수동 점검해 기존 질문이 다루지 않은 혜택/속성을 선택했습니다.
- 두 JSON 파일 파싱 성공; 모든 50개 레코드에 PDF 문서 메타데이터·SHA-256·페이지/인용문이 연결됨.
- PDF 파일 SHA-256은 원장 기록과 10/10 일치하며, Golden Answer의 파일 경로/해시도 문서별 확인했습니다.
- VERIFIED 40개는 문서 ID, 페이지, 인용 문자열이 존재합니다. 표·이미지/OCR/원장 연결에 제한이 있는 10개는 NEEDS_REVIEW로 유지했습니다. NOT_IN_SOURCE는 0개입니다.
- PostgreSQL Evidence link와 Neo4j Evidence 관계는 ID/혜택 단위로 대조했습니다. CARD10-002·004의 일부 연회비 Evidence 관계 부재는 불일치로 기록했습니다.

