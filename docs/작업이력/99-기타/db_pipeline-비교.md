# db_pipeline 조사: file_pipeline과의 비교

- 작성일: 2026-11-02
- 방식: **읽기 전용 조사.** `db_pipeline` 코드·SQL·공용 문서를 수정하지 않았고, DB·Storage에 접속하지 않았으며, `.env`와 접속 정보는 열지 않았다.
- 목적: 5단계 이후를 이중으로 만들지 않고, 결과 A(file_pipeline)와 결과 B(db_pipeline)를 같은 기준으로 비교할 수 있게 한다.
- 상대 폴더에 대한 제안은 수정이 아니라 **질문**(5절)으로만 적었다.

## 0. 읽은 범위와 읽지 않은 범위

| 읽음 | 읽지 않음 (이 문서가 말하지 못하는 것) |
|---|---|
| `db_pipeline/README.md` 전체 | `document_repository.sql`의 SQL 본문, `register_service.py` 본문, `main.py`, `storage_*` |
| `extraction_schema.py` 전체 | `sql/hana_card_db_design.md`, V6 DDL의 컬럼 상세 |
| `document_service.py` 핵심(`read`, `_read_pages`, `_split_pages`) | 온톨로지·Neo4j 관련 문서 내용 (파일 위치만 확인) |
| DDL V2 머리말, V6 테이블 목록 | `graphrag_chatbot` 코드, 테스트 파일 |
| `docs/architecture.md`, `docs/development_roles.md` | |

## 1. db_pipeline이 지금 하는 일

```mermaid
flowchart LR
    PDF[PDF + manifest<br/>src/card_benefit/data/raw/hana_all] --> DS[document_service<br/>읽기·검증·쪽·청크]
    DS --> RS[register_service<br/>중복 확인·등록·검증]
    RS --> DB[(db_pipeline<br/>card_doc / page / chunk)]
    ST[document_storage<br/>원본 PDF 보관] -.pdf/doc_sha256.pdf.-> DB
    EX[extraction_schema.py<br/>AI 추출 스키마 설계] -.아직 호출하는 코드 없음.-> DB
```

| 항목 | 상태 | 근거 |
|---|---|---|
| PDF 읽기, 쪽·청크 구성, DB 등록, 등록 후 SQL 검증 | **구현됨** | README, `document_service.py` |
| OCR 검토 흐름(`OCR_REVIEW` → 승인 → `RAW`) | 구현됨 | README |
| 원본 PDF Storage 업로드·검증·복원 | 구현됨 | README |
| AI 호출·추출, 추출 결과 저장 | **개발 예정** | README "개발 예정" |
| `extraction_schema.py`(AI 추출 스키마 V1) | **설계됨, 호출하는 코드가 아직 없음** | `grep`으로 다른 파일의 import가 없음을 확인 |
| 대상 카드사 | **하나만** | 파일명 규칙(`_디자인코드_날짜.pdf`)과 manifest 열이 하나 형식에 고정, `doc_cd`가 `HANA_…` |

## 2. 같은 점 (비교가 가능한 이유)

| 항목 | file_pipeline | db_pipeline | 판정 |
|---|---|---|---|
| 대상 문서 | `src/data/hana_all` | `src/card_benefit/data/raw/hana_all` | manifest의 열과 해시 185개가 **완전히 같음** (직접 비교) |
| 쪽 원문을 읽는 도구 | `common.document_reader` | `common.document_reader` | 같음 |
| 위치 규칙 | 쪽 원문 기준 1부터, 끝 글자 포함 | 같음 (`DocChunk` 설명) | 같음 |
| 문서 키 | `sha256` | `doc_sha256` | 같음 (우리 `doc_id`는 앞 16자) |
| 청크가 쪽 하나일 때 위치 | `start_pos=1`, `end_pos=len(text)` | `1`, `char_cnt` | 같음 |
| 빈 쪽 | 청크 없음 | 청크 없음 | 같음 |
| 해시·쪽수 검증 | 인덱스 생성 시 manifest와 대조 | manifest 해시·크기·쪽수와 대조 | 비슷함 |

## 3. 다른 점

| 항목 | file_pipeline | db_pipeline | 영향 |
|---|---|---|---|
| 청크 단위 | 쪽 4000자 이하는 쪽, 초과는 제목 기준(계획) | `PAGE_V1`: 쪽당 1개 (표가 청크에서 갈라지지 않게) | **각자 한다고 정함.** 비교는 (해시, 쪽, 글자 범위)로 |
| 이미지·깨진 쪽 | 건너뜀(`ocr_needed=Y`) | `SUSPECT`/`GARBLED`/`OCR_REQUIRED` 쪽이 있으면 **등록 거부**, OCR을 거치면 `OCR_REVIEW`로 청크 제외 | 비교 대상에서 이미지 PDF를 제외할지 정해야 함 |
| 문서 범위 | 하나 + 우리 | 하나만 | 우리카드는 결과 B가 없어 비교 불가 |
| NUL 문자 | 처리 없음 | 같은 길이의 `�`로 바꿔 위치 유지 | DB에 넣을 때만 필요. 우리는 파일이라 해당 없음 |
| 청크 번호 | 쪽 단위 `p0001` | 문서 전체 순번 | 비교에 쓰지 않음 |
| 공유 문서 | 상품 목록을 문서에 붙임 | 공유 상품을 `doc_note`에 문자열로 기록 | 형식이 다름 |
| 이름 규칙 | `doc_id`는 해시 앞 16자 | `doc_cd = HANA_{디자인코드}_{날짜}` | 문서 키는 `doc_sha256`로 통일 |

## 4. 추출 스키마(EXTRACT_SCHEMA_V1)와 우리 5단계

LLM은 **쪽 하나(`PageExtraction`)** 에 대해 응답하고, 이후 Python이 문서 단위로 통합·정규화한다. 이미 있는 틀을 우리 단독으로 다시 만들면 비교가 어려워진다.

| 스키마 요소 | 담고 있는 것 | 우리 5단계에서 필요한가 |
|---|---|---|
| `BenefitItem` | 혜택명, 유형(할인·적립 등), 확신도, 대상, 규칙, 한도, 조건, 관계, 근거 | 필요 |
| `RuleItem` | 계산 방법(비율·정액 등), 값, 단위, 지급 단위, 최소 결제액 | 필요 |
| `ConditionItem` | 조건 종류(전월 실적 등), 기준, 최소·최대 금액, 부정 여부, 원문 | 필요 |
| `LimitItem` | 기간·단위별 한도, 공유 범위 | 필요 |
| `RelationItem` | 혜택 간 관계(배타, 상한 후 대체 등) | 필요 (그래프 관계로 이어짐) |
| `TargetItem` | 가맹점·업종·채널 | 필요 |
| `EvidenceQuote` | 원문 그대로의 인용과 근거 종류 | **필수** (근거 없는 결과 거르기) |
| `ProductMention` | 상품명, 발급사, 연회비 등 | 인덱스에서 이미 확보 |
| `UnresolvedItem` | LLM이 판단을 보류한 문구 | 필요 |
| 통합·검증(`Merged*`, `ItemCheck`, `EvidenceCheck`) | 쪽 결과를 문서 단위로 합침, 값이 원문에 있는지·이 혜택의 값인지 | 검증 단계(6~7)에서 참고 |

- `LLM은 DB ID와 조건식 트리를 만들지 않는다`는 원칙이 파일 머리에 있다. 같은 원칙을 쓰면 결과 A와 B가 같은 "원문 표기와 값" 수준에서 비교된다.
- 근거 위치(`start_pos`, `end_pos`)는 Python이 원문에서 찾아 채우고, 못 찾으면 비어 있다.
- 이 스키마는 아직 어느 코드도 부르지 않는다. 그래서 **우리가 같은 스키마를 써도 상대 코드와 충돌하지 않는다.** 소유와 변경 절차를 정하는 것이 먼저다(5절 질문).

### 위치 변환 주의
`EvidenceCheck`의 위치는 "청크 원문 기준"이고, 그쪽 청크는 쪽 전체라 곧 쪽 기준이다. 우리가 쪽 안을 쪼갠 청크에서 근거를 찾으면 **청크 위치에 청크 시작 위치 - 1을 더해 쪽 기준으로 바꿔** 내보내야 비교가 맞는다.

## 5. 합의 또는 확인이 필요한 질문

| # | 질문 | 이유 | 대상 |
|---|---|---|---|
| 1 | 결과 A·B를 내보낼 때 같은 필드 이름과 위치 규칙(`doc_sha256`, `page_no`, `start_pos`, `end_pos`, 쪽 기준 1부터 끝 포함)을 쓰나? | 비교의 기준 | 김병주 |
| 2 | `EXTRACT_SCHEMA_V1`을 공통 계약으로 쓰나? 소유자와 변경 절차는? | 이중 설계 방지 | 김병주 |
| 3 | 이미지 PDF·OCR 필요 문서는 비교 대상에서 제외하나? | 그쪽은 등록 거부, 우리는 건너뜀 | 공동 |
| 4 | 우리카드는 결과 B가 없다. 비교는 하나로만 하나? 우리카드 확장은 누가? | 범위 | 공동 |
| 5 | 공통 상품 마스터는 `card_benefit.card_product`인가 `db_pipeline.card_product`인가? | **문서가 서로 다름** (아래) | 김병주 |
| 6 | 개발용과 운영용 DB가 따로 있나? 계정을 나눌 수 있나? | DB 충돌 방지 | 김병주 |
| 7 | 그래프 저장소는 Neo4j인가 PostgreSQL `graphrag` 스키마인가? | 문서마다 다름 | 공동 |

**문서 간 불일치 (사실 확인 결과)**
- DDL V2 머리말: 스키마를 `card_benefit`(공통 카드 마스터) / `file_pipeline` / `db_pipeline`으로 나누고 `card_benefit.card_product`는 변경하지 않는다고 적혀 있다.
- `db_pipeline/README.md`와 V6 DDL: 카드 상품은 `db_pipeline.card_product`를 쓰고 이전 `card_benefit.card_product`는 사용하지 않는다고 적혀 있다.
- `docs/architecture.md`, `docs/development_roles.md`: "두 폴더에 Python 코드가 없다", "PDF 파싱·추출은 구현 안 됨"이라고 적혀 있어 현재와 다르다. **수정 제안만 한다** (두 사람 공용 문서).

## 6. file_pipeline이 그대로 쓸 수 있는 것, 따라 하지 않을 것

| 쓸 수 있는 것 | 이유 |
|---|---|
| 위치 규칙, `doc_sha256` 키 | 이미 같음 |
| `EXTRACT_SCHEMA_V1`의 틀(혜택·규칙·조건·한도·관계·근거) | 5단계 설명서의 출발점. 합의 후 사용 |
| "LLM은 ID와 조건식 트리를 만들지 않는다" 원칙 | 비교 가능성 |
| manifest 대조 검증(해시, 크기, 쪽수) | 우리 인덱스도 같은 방식 |
| `--apply`가 없으면 조회만 | 실수 방지 관례 |

| 따라 하지 않을 것 | 이유 |
|---|---|
| 쪽당 청크 1개 | 우리 청킹 방식을 비교 변수로 두기로 함 |
| 이미지 쪽이 있으면 등록 거부 | 우리는 해당 문서만 건너뛰고 나머지는 계속 진행 |
| DB에 사본 적재 | 이번에는 읽기만 하고 새 테이블을 만들지 않기로 함 |

## 7. 이 조사로 바뀌는 계획

- 5단계는 "스키마 설계"가 아니라 **"`EXTRACT_SCHEMA_V1`을 공통 계약으로 쓸지 결정하고 file_pipeline 입력·출력에 맞춤"** 으로 바뀐다.
- 청크와 모든 결과에 전체 `doc_sha256`을 넣는다(청킹 계획서에 반영 완료).
- 근거 위치는 쪽 기준으로 변환해 내보낸다.
- 비교는 하나 문서로 시작한다.
