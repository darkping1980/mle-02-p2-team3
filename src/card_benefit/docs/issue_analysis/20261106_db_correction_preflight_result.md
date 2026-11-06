# DB 보정 및 Neo4j 재적재 사전 안전성 검증

작성일: 2026-11-06  
범위: 운영 데이터 변경 없이 테스트 실패 원인, PostgreSQL 백업·롤백 준비, 세 카드 데이터 보정 범위와 Neo4j 전체 재적재 위험을 검증했다.

## 1. 결론 요약

- 기존 전체 회귀 결과는 **682 통과, 2 실패, 20 건너뜀**이었다. 실패한 두 테스트를 HEAD(`fcb2a5111dfad4eec17ec6431fd314f22bbeb451`)의 임시 추출본에서도 재실행한 결과 **같은 두 테스트가 같은 이유로 실패**했다. 이번 미커밋 P0–P2 변경에서 새로 발생한 실패라는 증거는 없다.
- PostgreSQL 백업 도구는 현재 스키마에서 실행되었고, 테이블별 행 대조가 `VERIFY OK`였다. 백업은 `src/data/backup/pre_calc_cleanup_20261106_140723/`에 있다. 이 경로는 `.gitignore` 대상이다.
- 읽기 전용 보정 미리보기는 세 행의 현재 `item_data`가 모두 `{}`임을 확인했다. 근거 링크 8건은 기존 링크가 0건이어서 중복 없이 신규 대상이다.
- **카드 22/099**는 명시된 30만~80만원 미만 / 80만원 이상 구간과 월 한도 1만원 / 1만5천원을 복구할 수 있다. `limit_tiers` 생성 결과는 6개 항목이며, 이를 원문 규칙의 완전한 구간 목록과 동일시하지 말고 적용 전 diff와 근거 연결을 재검토해야 한다.
- **카드 20/092**는 누적형 보너스 할인 한도(기본 10만원, 추가 10만원)를 유지하는 구조만 복구 가능하다. 서로 배타적인 구간으로 만들지 않는다.
- **카드 23/100**은 월 한도 구조를 복구할 수 있지만, 각 1만/2만/5만원이 어떤 적립 범위와 공유되는지 미확정이다. 별도 업무 판단 전에는 카드 23의 행 업데이트와 근거 링크 3건을 실행 대상에서 제외한다. 상한이 명시되지 않은 조건에 `limit_tiers`를 생성하지 않는다.
- PostgreSQL·Neo4j에 쓰기 작업, 재적재, 스키마 변경은 수행하지 않았다. Git commit/push도 하지 않았다.

## 2. 테스트 실패 두 건

### Failure cause detail (HEAD baseline)

- `test_unresolved_tier_cannot_be_decided_in_natural_text`: `validate_answer()` first falls back to `validated_sentences`, then calls `tier_answer(conflicts, payment_amount, evidence)`. When that helper returns a sentence, the code replaces the answer and sets `answer_source="program_tier"`. The test's payment amount (10,000) satisfies both 3,000 and 10,000 minimums; the tier selector returns a program-generated result, conflicting with the test's expected source. This mismatch is present at HEAD. Whether the tier choice is correct for the product wording remains a separate answer-quality question.
- `test_example_only_fills_input`: the app uses `st.pills(..., key="example", on_change=use_example)` and the callback assigns `st.session_state.question`. The failing AppTest `button_group.set_value(...).run()` path does not expose that assignment through the `question` text area. This is reproducible at HEAD and indicates an existing AppTest/widget-callback mismatch; it does not establish that deployed users see the same issue.

### 2.1 HEAD 기준 재검증

작업 디렉터리와 미커밋 파일은 건드리지 않았다. `git archive HEAD`로 현재 HEAD만 임시 디렉터리에 추출하고, 저장소 가상환경의 pytest로 실패했던 두 테스트만 실행했다. 임시 디렉터리는 테스트 종료 후 제거됐다.

| 테스트 | HEAD 결과 | 실패 내용 | 판단 |
|---|---:|---|---|
| `payment_card/tests/test_answer_text.py::test_unresolved_tier_cannot_be_decided_in_natural_text` | 실패 | `validate_answer()` 결과의 `answer_source`는 `validated_sentences`여야 한다는 기대와 달리 `program_tier` | HEAD에서도 같은 assertion 실패. 미커밋 변경에 의해 새로 생긴 실패가 아님 |
| `payment_card/tests/test_card_graphrag.py::StreamlitTests::test_example_only_fills_input` | 실패 | AppTest에서 `button_group[0].set_value(...)` 실행 후 `question` text area가 빈 문자열 | HEAD에서도 같은 assertion 실패. 미커밋 변경에 의해 새로 생긴 실패가 아님 |

HEAD 재현 결과는 `2 failed in 3.90s`였다. 두 실패 모두 코드 경로상 테스트 기대값과 현행 HEAD 동작이 이미 불일치한다. 따라서 “P0·P1 기준 기존 실패”라는 과거 분류를 증명하는 역사 로그는 없지만, 적어도 현재 작업 트리 변경 전인 HEAD에서도 실패한다는 비교 근거를 확보했다. 어느 커밋에서 처음 생겼는지는 별도 과거 커밋 bisect 없이 확정하지 않았다.

전체 회귀 테스트의 기존 기록은 **682 passed, 2 failed, 20 skipped, 99 subtests passed**이다. 이 작업에서는 전체 회귀를 다시 돌리지 않았다. 두 실패 외에 P2 변경으로 새 실패가 생겼는지는 전체 테스트의 변경 전 기준 로그가 없어 수치로 비교할 수 없지만, HEAD에서 재현한 두 실패는 신규 회귀가 아니다. P0·P1·P2 집중 테스트의 기존 기록은 **48 passed, 1 skipped**이며, 이 후속 작업에서 해당 테스트는 재실행하지 않았다.

## 3. PostgreSQL 백업 확인

### 3.1 실행한 백업과 범위

도구 위치는 `src/card_benefit/docs/schema_cleanup/tools/backup_db_pipeline.py`다. 과거 인수 문서에 “도구가 없다”고 적힌 내용은 잘못된 기록이었다. 실제 도구를 현재 PostgreSQL `db_pipeline`에 실행했고, 2026-11-06 백업 결과를 아래 위치에서 확인했다.

```text
src/data/backup/pre_calc_cleanup_20261106_140723/
  postgres_db_pipeline.json
  catalog.json
  schema_ddl.sql
```

결과 요약: 테이블 20개, 행 4,864건, catalog의 view 8개 / function 7개 / constraint 77개 / index 62개 / sequence 13개. 백업 저장 후 행 단위 대조 결과는 `VERIFY OK`였다. `stg_normalized_item`은 2026-11-03 스키마 정리 때 제거된 컬럼이라 현재 백업에 없으며, 이 컬럼의 복구 SQL은 생성·실행하지 않았다.

이 백업은 전체 `db_pipeline` 데이터와 스키마 카탈로그를 보존하는 **읽기 백업**이다. 복구 동작 자체를 실제 운영 DB에 실행하지 않았으므로, 이 검증은 파일 생성과 행 대조까지이며 복원 리허설까지 완료했다는 의미는 아니다. 백업 디렉터리는 Git에 추가하지 않는다.

### 3.2 대상 행의 복구 식별자와 preimage

| 카드 / 상품 항목 | PK | 현재 `item_data` | 보정 후보 |
|---|---|---|---|
| 22/099 | `(card_id=22, card_product_item_id='20261105_000099')` | `{}` | `schema_ver`, `limits`, `rule_limits`, `limit_tiers` |
| 23/100 | `(card_id=23, card_product_item_id='20261105_000100')` | `{}` | `schema_ver`, `limits`, `rule_limits`; 상한 미확정이므로 `limit_tiers` 없음 |
| 20/092 | `(card_id=20, card_product_item_id='20261105_000092')` | `{}` | `schema_ver`, `limits`, `rule_limits`; 누적 한도이며 `limit_tiers` 없음 |

변경 전 `rule_list`, `item_limit_txt`, `item_search_txt`, `item_embedding`은 백업 스냅샷에 원본값 그대로 보존되어 있다. dry-run preimage에는 `rule_list`와 기존 JSON의 SHA-256, `item_search_txt` 및 `item_embedding`의 SHA-256도 생성된다. 롤백 전에는 백업값·PK뿐 아니라 실행 직전 값과도 대조해야 하며, 동시 변경이 감지되면 롤백을 중단해야 한다.

### 3.3 근거 연결 식별자

사전 조회에서 아래 여덟 evidence ID 각각은 `card_source_evidence`에 원문 근거 1건씩 존재했고, 어느 기존 `card_evidence_link`에도 연결되지 않았다. dry-run의 natural key 중복도 0건이다.

| 카드 PK | 규칙 / 조건 | 근거 ID | 원문 위치(스냅샷) |
|---|---|---|---|
| 22 / `20261105_000099` | `r1` / `c1` | `20261105_002685` | 문서 `20261105_000042`, 1쪽, 청크 `20261105_000173`, 위치 3727–3741 |
| 22 / `20261105_000099` | `r2` / `c2` | `20261105_002686` | 문서 `20261105_000042`, 1쪽, 청크 `20261105_000173`, 위치 3743–3757 |
| 22 / `20261105_000099` | `r3` / `c3` | `20261105_002687` | 문서 `20261105_000042`, 1쪽, 청크 `20261105_000173`, 위치 3182–3223 |
| 23 / `20261105_000100` | `r1` / `c1` | `20261105_002744` | 문서 `20261105_000043`, 3쪽, 청크 `20261105_000176`, 위치 362–383 |
| 23 / `20261105_000100` | `r2` / `c2` | `20261105_002745` | 문서 `20261105_000043`, 3쪽, 청크 `20261105_000176`, 위치 419–440 |
| 23 / `20261105_000100` | `r3` / `c3` | `20261105_002746` | 문서 `20261105_000043`, 3쪽, 청크 `20261105_000176`, 위치 476–498 |
| 20 / `20261105_000092` | `bonus_base_discount` / `bonus_spend_24m` | `20261105_002453` | 문서 `20261105_000040`, 3쪽, 청크 `20261105_000159`, 위치 684–710 |
| 20 / `20261105_000092` | `bonus_additional_cap_discount` / `bonus_spend_36m` | `20261105_002454` | 문서 `20261105_000040`, 3쪽, 청크 `20261105_000159`, 위치 733–747 |

백업 JSON에서 이 여덟 ID는 연결 관계가 0개였다. 계획된 삽입 시 `evidence_link_id`는 DB sequence가 할당하므로 미리 만들거나 추정하지 말고, 승인된 실행 때 `INSERT ... RETURNING evidence_link_id` 결과를 별도 실행 기록에 보존해야 한다.

## 4. 보정 범위와 예상 결과

### 4.1 읽기 전용 미리보기 결과

`limit_struct_backfill.py`는 `--dry-run`만 허용하고, PostgreSQL 접속에서 `default_transaction_read_only=on`을 강제한다. 2026-11-06 재실행 결과:

```text
mode = READ_ONLY_DRY_RUN
database_writes = 0
planned evidence links = 8
already exists = 0
would add = 8
```

세 행 모두 현재 `item_data={}`이며 변경 충돌 키가 없었다.

### 4.2 카드별 판단

**22/099 — 즉시 보정 후보**

- 추출 원문과 규칙 조건에 전월 실적 30만원 이상 80만원 미만, 80만원 이상이 명시되어 있다.
- `item_limit_txt`에 월 할인 한도 10,000원 / 15,000원이 표시되고, 세 근거 ID가 각각 룰 조건 또는 한도 설명을 지원한다.
- 예상 패치는 `limits`, `rule_limits`, `limit_tiers`를 포함한다. 현재 생성된 `limit_tiers`는 6개 항목이므로, 승인 직전 사람 검토에서 세 룰과 한도 대응 및 002687 한도 적용 설명의 연결을 확인해야 한다.
- 적용 시 대상 행 1건 변경, evidence link 3건 추가가 예상된다. `item_search_txt`와 임베딩은 변경 대상이 아니다.

**20/092 — 누적 한도 형태를 보존하는 보정 후보**

- 원문은 “보너스 할인 한도 10만원 제공” 및 “보너스 할인 한도 10만원 추가 제공”으로, 2,400만원 / 3,600만원 조건과 연계된 누적형 설명이다.
- `limits`, `rule_limits` 및 evidence link 2건만 보정한다. 배타 구간이나 `limit_tiers`를 생성하지 않는다.
- 적용 시 대상 행 1건 변경, evidence link 2건 추가가 예상된다. “추가 제공”의 합산 의미를 보존하고 기존 상품 규칙을 바꾸지 않는지 원문 대조를 최종 승인 전에 수행한다.

**23/100 — 업무 판단 보류**

- 세 실적 기준(30만/60만/120만원 이상)과 월 적립 한도 1만/2만/5만원은 추출 자료에 존재한다. 상한 조건은 원문에 없으므로 `limit_tiers`를 만들지 않는다.
- 추출 원문에는 `shared_scope_txt="특별/추가 적립"`으로 된 한도와 별도 “통합 월 적립 한도” 표현이 있고, 한도 항목들의 `applies_to_benefit_nms`는 비어 있다. 이 근거만으로 1만/2만/5만원이 이 혜택의 각 실적 구간 한도인지, 여러 특별·추가 적립 혜택이 공유하는 통합 한도인지 확정할 수 없다.
- 카드 상품 원문에서 통합 한도의 적용 대상 전체를 읽기 전까지 해당 행의 업데이트와 근거 link 3건을 실행 대상에서 제외한다. 공유 범위가 확인된 뒤에는 제한 범위대로 구조를 보정하되, 원문에 없는 실적 상한은 계속 생성하지 않는다.

### 4.3 예상 영향 표

| 실행 범위 | `card_product_item` UPDATE | `card_evidence_link` INSERT | 비고 |
|---|---:|---:|---|
| 22/099만 | 1 | 3 | 현재 가장 명확한 후보 |
| 22/099 + 20/092 | 2 | 5 | 20/092 누적형 구조를 유지하는 승인 필요 |
| 23/100 포함 | 추가 1 | 추가 3 | 공유 범위 업무 승인 전 제외 |
| 세 항목 모두(기존 제안 총량) | 3 | 8 | 현재 승인 가능한 실행안으로 보지 않음 |

범위 변경은 행 수를 바꾸지 않는다. 근거 link PK는 sequence가 생성하므로 예상 INSERT 8건은 식별 관계의 수이며, 실제 PK 값은 승인된 실행 후에만 알 수 있다.

## 5. 백업·롤백 준비와 절차

### 5.1 준비 상태

- 전체 PostgreSQL `db_pipeline` snapshot, catalog, 생성된 DDL 파일을 보유하고 행 대조를 마쳤다.
- 대상 행 PK, 변경 전 `item_data={}`, 기존 규칙·검색·임베딩 값은 snapshot에서 회수 가능하다.
- 여덟 근거 ID의 문서·페이지·청크·문자 위치와 현재 링크 부재를 기록했다.
- **선택적 롤백 SQL은 실행하지 않았으며 실제 복원 리허설도 하지 않았다.** 운영 적용 전에 백업 파일을 별도 보관 위치에 복사하고, 실제 대상 서버에서 복원 가능한지 격리 환경에서 리허설해야 한다.

### 5.2 승인 후 실행 때의 안전 절차

1. 실행 직전 백업을 새로 만들고 `--verify`로 행 지문 대조를 완료한다. 사전 스냅샷과 직전 스냅샷의 대상 PK/`item_data`/규칙 지문/링크 natural key가 예상과 다르면 중단한다.
2. 확정된 카드만 선택해 단일 PostgreSQL 트랜잭션에서 처리한다. UPDATE는 `(card_id, card_product_item_id)`를 PK 조건으로 하고, 현재 `item_data`가 검토한 preimage와 일치하는지 확인한다. 각 링크 삽입 직전 같은 natural key를 재조회하고, 중복은 삽입하지 않는다.
3. UPDATE·INSERT 건수를 기대값과 대조하고, 삽입된 `evidence_link_id`를 `RETURNING`으로 기록한다. 실패 또는 개수 불일치이면 트랜잭션을 commit하지 않고 rollback한다.
4. commit 후 같은 트랜잭션 밖에서 대상 JSON 구조와 근거 연결 3/5/8건, 원문 근거 PK, 대상 외 행 미변경 여부를 읽기 검증한다.
5. 별도 사고 롤백이 승인되면 변경 후 현재 값이 승인된 기대값과 일치하는 경우에만 단일 트랜잭션으로 새 링크 PK를 삭제하고 백업 preimage의 `item_data`를 복원한다. `item_search_txt`, `item_embedding`, `rule_list` 등 이번 변경 대상이 아닌 필드는 업데이트하지 않는다. 예상치 못한 후속 수정이 있으면 덮어쓰지 않고 중단한다.

롤백 대상을 natural key만으로 무차별 삭제하지 않는다. 실행에서 반환받은 정확한 `evidence_link_id`와 6개 natural key `(card_id, card_product_item_id, rule_key, ev_item_cd, ev_item_key, evidence_id)`를 함께 대조한다. 백업 전체 복원은 단순 행 롤백보다 영향 범위가 커서 선택적 롤백으로 해결할 수 없는 장애에 한정하고 별도 승인 및 격리 복원 검증이 필요하다.

## 6. Neo4j 재적재 사전 검증

### 6.1 현재 상태와 증가 근거

기존 읽기 전용 검증에서 Neo4j는 **1,635개 노드, 2,702개 관계**였다. PostgreSQL 원천과의 차이는 `item_data` 속성 차이 34건이며, 앞선 P2 검증에서 이 차이는 새 적재 로직이 추가됐지만 Neo4j에 재적재되지 않은 상태와 일치했다. 1,643/2,718은 재적재 전 예상치이지 현재 관측 결과가 아니다.

현재 dry-run의 세 UPDATE는 기존 혜택 노드의 `item_data` 속성만 바꾸므로 그 자체로 노드나 관계를 늘리지 않는다. 계획 근거 ID 여덟 개는 모두 PostgreSQL 원천에는 존재하지만 기존 `card_evidence_link`가 0개다. `neo4j_dry_run.py`는 연결된 근거만 그래프에 포함한다. 승인된 여덟 연결이 모두 신규라면 그래프 구성에서 각 근거 노드 1개와 `dp_in_chunk` 1개, `dp_supported_by` 1개씩을 추가하므로 **조건부로 +8 노드, +16 관계**가 예상된다. 따라서 현재 수치에 더하면 1,643 노드 / 2,718 관계다. 실제 반영 전 dry-run에서 그래프 전체 key 집합을 다시 생성하고 예상 수치를 확인해야 한다.

카드 23을 보류하면 해당 근거 3개는 link로 연결되지 않으므로 이 증분은 **카드 22만 적용 시 +3 노드 / +6 관계**, 카드 22와 20 적용 시 **+5 노드 / +10 관계**가 된다. 이 계산은 기존 Neo4j에 해당 evidence key가 없고, 모두 동일 청크의 유효한 원문 근거로 검증되는 조건부 기대다.

### 6.2 전체 MERGE의 위험과 보호 장치

`neo4j_load_draft.py`는 PG 전체 snapshot으로 그래프를 만들고 전체 `dp_` 노드와 관계를 `MERGE`한다. 노드는 라벨+PK로 매칭하며 모든 노드에 `dp_node.key`를 부여한다. 현재 원천과 같은 key는 유지되는 것이 설계 의도다. 관계는 endpoint와 관계 key로 `MERGE`한다.

- `SET n += $props`는 전달된 속성을 덮어쓴다. 누락된 예전 속성을 제거하는 완전한 동기화 방식은 아니므로, 구 버전 속성 잔존 가능성과 현재 key 외 extra property를 별도 비교해야 한다.
- 혜택 임베딩/검색 필드는 LLM 호출이나 새 임베딩 생성 없이 PostgreSQL 검색 projection에서 snapshot으로 옮긴다. 이 작업은 재생성이 아니라 값의 재투영이다. 다만 모델명, run ID, 벡터 차원, null 개수, key별 벡터 해시를 전·후 비교해야 한다. 세 카드 보정은 이 필드를 수정하지 않는다.
- 원천에 없는 `dp_` 노드는 쓰기 전에 stale 검사로 중단한다. 이 자동 정리 기능은 없다.
- 관계 사후 검증은 DB의 관계 key 목록이 기대 key 집합과 일치하는지 확인한다. stale 관계도 이 검증을 실패시켜 데이터 쓰기 트랜잭션을 rollback해야 한다. stale 관계를 사전 삭제하지는 않는다.
- `prepare_schema()`는 데이터 트랜잭션 전에 `CREATE CONSTRAINT IF NOT EXISTS`를 실행한다. 따라서 이후 데이터 적재 트랜잭션이 실패해도 이 단계에서 새로 생성된 제약은 남을 수 있다.
- 같은 key로 재시도할 때 중복 방지를 의도하지만, 전체 데이터를 다시 덮어쓰는 작업이므로 잘못된 PG 원천, 잘못된 DB 접속, 검색 projection 차이, 기대 관계 목록의 불일치가 기존 그래프 속성을 바꿀 수 있다. `--apply`, 승인 확인 문자열, 예상 Neo4j database ID 확인은 필요조건이지 백업이나 승인 대체가 아니다.
- 데이터 write는 `session.execute_write(write_transaction, ...)`의 한 트랜잭션으로 수행되고 후조건 실패 시 rollback하도록 구현되어 있다. 단, 네트워크 단절 등 commit 결과가 모호한 경우를 포함한 복구 연습은 따로 필요하다.

### 6.3 재적재 전에 필요한 검증과 복구 준비

현재 구현만으로 Neo4j의 기존 속성·임베딩·인덱스까지 되돌리는 복구 자료를 확인하지 못했다. 따라서 다음 조건이 준비되기 전 전체 재적재를 시작하지 않는다.

1. 현재 Neo4j 인스턴스와 DB ID를 재확인한다.
2. 재적재 직전 운영 정책에 맞는 Neo4j 전체 백업을 생성하고, 백업 무결성과 별도 격리 DB 복원 가능성을 검증한다. 단순 key/건수 보고서는 데이터 복구용 백업을 대신하지 않는다.
3. 전체 `neo4j_dry_run` 결과에서 노드·관계 key set, labels/types별 수, stale key, 중복 key, orphan endpoint, source JSON, target item_data, 검색 projection(벡터 차원·모델·run ID·해시)을 승인된 기대값과 비교한다.
4. 증분 8/16 또는 보류 반영 3/6·5/10과 별도로, 전체 그래프의 현행/예상 건수 차이를 설명한다. 불일치가 있으면 적재하지 않는다.
5. 제한된 사전 검증 후 `neo4j_validate`로 노드 및 관계 key set, property 차이, `item_data`, 임베딩 수·차원·모델, 해당 8개 evidence의 owner→evidence→chunk→page→document 경로를 확인한다.
6. 오류 발생 시 자동 재시도 전에 DB 상태와 트랜잭션 commit 여부를 읽기 전용 검증한다. 트랜잭션 rollback이 확인되면 원인을 제거한 후 재시도하고, 비정상 commit 또는 상태 모호성은 격리 DB에서 검증된 사전 백업 복원 절차로 복구한다. 백업 복원을 실제 운영에서 시험하지 않았다면 복구 가능성을 확정 보고하지 않는다.

## 7. 실제 변경 여부

- PostgreSQL: 보정 `UPDATE/INSERT/DELETE/DDL` 0건. dry-run에서 연결은 `default_transaction_read_only=on`으로 설정됐다. 백업 도구는 읽기 전용 연결로 데이터 파일을 만들었다.
- Neo4j: 변경/재적재 0건.
- Streamlit 배포, LLM 호출, Git commit/push: 모두 0건.
- 기존 작업 디렉터리의 미커밋 소스 변경은 보존했다. 이번 문서 작업 외에 기존 Python 소스는 수정하지 않았다.

## 8. 실행 전 사용자 승인 항목 및 다음 단계

실제 데이터 변경 전 아래를 업무 및 운영 담당자가 승인해야 한다.

1. 22/099의 한도·구간 연결과 6개 `limit_tiers` 결과.
2. 20/092의 두 한도가 누적 제공 구조라는 원문 해석 및 이를 tiers로 분할하지 않는 점.
3. 23/100의 통합 월 적립 한도 공유 대상과 적용 범위. 확인 전 해당 항목은 변경안에서 제외한다.
4. 적용할 카드 집합(22만, 22+20, 또는 나중에 23 포함)과 정확한 UPDATE/INSERT 건수.
5. 최신 PostgreSQL 백업 보존 위치, 격리 복원 리허설, 선택적 rollback 절차와 롤백 승인자.
6. Neo4j 전체 백업·복원 리허설, 사전/사후 key·임베딩 검증 결과, 적재 시간대와 장애 복구 책임자.
7. DB write와 Neo4j 재적재 각각에 대한 별도 실행 승인. 이번 작업 지시만으로는 어느 것도 승인되지 않았다.

권장 순서: (a) 카드 22 및 20 원문·미리보기 승인, (b) 카드 23 공유 범위 문서 확인 후 포함 여부 판단, (c) 승인된 카드만 제한적 PostgreSQL 보정, (d) PostgreSQL post-check와 백업 검증, (e) Neo4j 백업/복원 사전 점검, (f) dry-run 전체 key/property/projection 검토, (g) 별도 승인 후 재적재, (h) `neo4j_validate` 및 PDF evidence 경로 사후 검증.
