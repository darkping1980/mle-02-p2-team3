# card_benefit 아키텍처

1절~3절은 **현재 실제 구현**(카드 등록·조회 CLI), 4절~5절은 **향후 설계 방향(확정 아님)** 입니다.
파일별 상세는 [directory_structure.md](directory_structure.md), 담당자는 [development_roles.md](development_roles.md)를 봅니다.

## 1. 현재 구현 범위 ✅

PostgreSQL 카드 상품 등록·조회 CLI뿐입니다. PDF 파싱, 추출, 정제·검증, Neo4j는 구현되어 있지 않습니다.

| 구성 | 역할 |
|---|---|
| `payment_card/main.py` | CLI (`register` / `list` / `get`), 세션 생성·종료 |
| `payment_card/models.py` | `NewCard`(입력 검증), `Card`(조회 결과) |
| `payment_card/repository.py` | `CardRepository`: `payment_card.*` statement 실행 |
| `payment_card/payment_card.sql` | Named SQL Mapper |
| `sql/schema.sql` | `payment_card.card_product` DDL (수동 실행) |
| `src/common` | `PostgresDbSession`(SQL 실행·트랜잭션), `DatabaseManager`(Connection Pool) — 그대로 재사용 |

## 2. 테이블

`payment_card.card_product`

| 컬럼 | 타입 | 의미 |
|---|---|---|
| `card_id` | `BIGINT IDENTITY` PK | 카드 상품 식별자 |
| `issuer` | `TEXT` | 카드사 |
| `card_name` | `TEXT` | 카드 상품명 |
| `card_type` | `TEXT` CHECK (`CREDIT`, `DEBIT`) | 신용카드 / 체크카드 |
| `created_at` | `TIMESTAMPTZ` 기본 `now()` | 등록일시 |

## 3. 현재 호출 흐름

```text
main.main(argv)
  → parse_args → NewCard(...)                 입력 검증 (실패 시 종료 코드 1, DB 세션을 만들지 않음)
  → PostgresDbSession(mapper_root=payment_card/, camel_case_keys=False, sql_log_mode="none")
        └ DatabaseManager (pool은 첫 SQL 실행 때 생성)
  → CardRepository(sql_session)
        register → execute("payment_card.insert_card", {...})            INSERT ... RETURNING → Card
        list     → select_list("payment_card.list_cards")                 → list[Card]
        get      → select_one("payment_card.find_card", {"card_id": ...}) → Card | None
  → finally: sql_session.database_manager.close()
```

- 값은 `:issuer` 같은 바인딩 파라미터로 전달됩니다(SQL 문자열 연결 없음).
- 트랜잭션 밖에서 실행한 SQL은 호출 단위로 commit됩니다(`DatabaseManager.connect()` 동작).
  여러 SQL을 하나로 묶을 때는 `with sql_session.transaction():` 을 사용합니다.
- `camel_case_keys=False` 로 결과 행의 key를 컬럼명 그대로 받아 `Card(**row)` 로 만듭니다.

## 4. 향후 개발 예정 범위 ⏳ (설계 방향, 확정 아님)

두 사람이 **같은 원천 문서를 서로 다른 방식으로 처리**하고, 각자 AI 추출과 검증까지 수행한 뒤 결과를 비교합니다.
한 사람의 출력이 다른 사람의 입력이 되는 순차 파이프라인이 아닙니다. 담당 범위는 [development_roles.md](development_roles.md)를 봅니다.

```text
              카드 상품설명서 PDF / 원천 문서
                           |
              +------------+------------+
              |                         |
              v                         v
       [이현근 담당]              [김병주 담당]
       파일 기반 방식              PostgreSQL 기반 방식
       extraction/                ingestion/
              |                         |
        Python 파싱               원본 데이터 DB 저장
              |                         |
        정규식 전처리              SQL 기반 전처리
              |                         |
        Python + LLM               DB 데이터 기반 AI 추출
              |                         |
        Python 검증               SQL 정제 및 검증
              |                         |
        추출 결과 A                추출 결과 B
              |                         |
              +------------+------------+
                           |
                           v
                  공통 데이터 형식 비교        [공동]
                           |
                           v
                추출 정확도 및 근거 검증        [공동]
                           |
                           v
                최종 데이터 확정 (향후)
                           |
                           v
                 Neo4j / GraphRAG
```

- 두 방식을 반드시 하나의 구현으로 합치지 않습니다. 같은 원문과 평가 기준으로 비교할 수 있는 구조를 지향합니다.
- 비교가 가능하려면 공통 데이터 계약(문서 ID·원문 위치, 공통 JSON, 판정 기준 등)이 먼저 필요합니다([development_roles.md](development_roles.md) 4절).
- 단계별 모듈, 테이블, JSON 필드, 비교 코드 위치, 실행 진입점은 아직 정해지지 않았습니다.
  현재 `CardRepository`·`payment_card.card_product` 의 재사용 여부도 테이블 설계 때 결정합니다.

### 기술 검토 사항 ❓ (구현 전 확인)

| 항목 | 내용 |
|---|---|
| PostgreSQL 방식의 원문 확보 | PostgreSQL은 PDF를 직접 파싱하지 않습니다. DB에 넣을 텍스트·메타데이터를 DB 밖에서 확보해야 합니다. 이현근의 파싱 결과를 공유하면 **AI 추출·검증 방식만** 비교하게 되고, 각자 파싱하면 **파싱부터 전체 방식**을 비교하게 됩니다. 어느 쪽을 비교할지 정해야 합니다 |
| DB에서 AI 호출 | 후보: `pgai` 등 PostgreSQL 확장, DB 함수에서 외부 AI API 호출, Supabase Edge Functions, Python이 LLM 호출만 중계. 사용 중인 Supabase/PostgreSQL에서 지원 여부를 확인하기 전까지 미확정 |
| 결과 B 내보내기 | DB에 저장된 결과 B를 공통 JSON 형식으로 내보내는 방법 |
| 비교 위치 | 결과 A·B를 파일에서 비교할지, 결과 A도 DB에 넣어 SQL로 비교할지 |
| 비교 기준 | 추출 정확도(정상·누락·오탐), 처리 시간, API 비용. 정답 기준(정답셋) 작성 방법 |

## 5. 세 가지 검증의 차이

통과 기준과 잡아내는 오류가 서로 다르므로, 하나를 통과했다고 다른 검증을 생략할 수 없습니다.
두 방식은 각자 자기 결과를 검증하고(4절 그림의 "Python 검증" / "SQL 정제 및 검증"), 원문 의미는 비교 단계에서 공동으로 확인합니다.

| 검증 | 확인하는 것 | 예시 | 잡지 못하는 것 | 수행 위치 |
|---|---|---|---|---|
| **JSON 형식 검증** | 필수 필드, 타입, 허용값 | `card_type` 이 `CREDIT`/`DEBIT` 인가, 필수 값이 비어 있지 않은가 | 값이 원문과 맞는지 | 각자 결과를 공통 JSON으로 낼 때 (이현근: Python, 김병주: 내보내기 시) |
| **DB 정합성 검증** | 제약조건, 중복, 참조 무결성, 원본↔추출 결과 연결 | 같은 혜택이 두 번 저장되지 않았는가, 추출 결과가 존재하는 원본을 가리키는가 | 형식·관계가 맞아도 의미가 틀린 값 | 김병주 방식 내부 (SQL만으로 가능) |
| **원문 의미 검증** | 추출값이 문서 원문의 의미와 일치하는지 | "간편결제 제외"가 카드 전체에 적용되는지 특정 혜택에만 적용되는지 | — | SQL로는 불가. LLM 또는 사람 확인 필요. 결과 A·B 비교 시 공동 수행 ❓ 방법 미정 |

현재 구현에서 해당하는 부분은 형식 검증의 `NewCard.__post_init__` 과 DB 정합성 측면의 `card_type` CHECK·PK 제약뿐입니다.
LLM 추출값은 형식·DB 검증을 모두 통과해도 원문 의미가 틀릴 수 있으므로, 두 방식 모두 원문 근거를 보존해 대조할 수 있어야 합니다.
