# GraphRAG P0·P1 구현 결과

- 작성일: 2026-11-06
- 작성: Claude
- 기준 설계: [20261106_graphrag_data_loss_fix_plan.md](20261106_graphrag_data_loss_fix_plan.md) 3·4절
- 범위: P0(답변 검증의 NULL 지급값 처리), P1(신규 등록의 추출 한도 구조 보존)
- **변경하지 않은 것**: PostgreSQL 데이터·스키마, Neo4j 데이터·스키마, 재적재, 기존 카드 데이터 보정, P2 적재·검증 코드, `streamlit_app.py`, `execution_log.py`, Git Commit/Push. DB 접근은 fixture 작성용 SELECT(읽기 전용 세션)와 Neo4j 읽기 전용 통합 테스트 1건뿐이다. 유료 LLM 호출은 0건이다.

---

## 1. 수정된 파일 및 함수

| 파일 | 함수·객체 | 단계 |
|---|---|---|
| `payment_card/db_pipeline_origin_search/card_graphrag.py` | `tier_token`, `rule_conflicts`, `tier_label`, `distorts_tier`, `picks_single_tier`, `tier_is_quoted`, `validate_answer`(결제 금액 구간 시스템 문장 블록), 답변 LLM 지시문 1줄 | P0 |
| `payment_card/db_pipeline/extraction_service.py` | 신규 `limit_struct`, `check_limit_struct`, `limit_tiers_from_extraction`, `_spend_atoms`, 상수 `LIMIT_FIELDS`·`PERIOD_COLUMNS`·`TIER_EXCLUDED_BASIS` | P1 |
| `payment_card/db_pipeline/product_benefit_service.py` | `_register`(item_data 구성, COND 근거 연결 분기), `_links`(규칙 조건 근거 추가), 신규 `_located`, `_match`, `_limit_evidence`, `_cond_evidence` | P1 |
| `payment_card/db_pipeline/common_benefit_repository.sql` | 신규 `insert_rule_cond_evidence_link` | P1 |
| `payment_card/tests/test_tier_null_payout.py` (신규) | P0 테스트 15건(오프라인 14 + Neo4j 읽기 전용 통합 1) | P0 |
| `payment_card/tests/test_limit_struct.py` (신규) | P1 테스트 14건 | P1 |
| `payment_card/tests/fixtures_limit_struct.json` (신규) | 22/099·23/100·20/092의 실제 추출 원본·등록 규칙·원문 근거(읽기 전용으로 옮김) | P1 |

**설계와 다르게 구현한 점 1가지**: 설계 4.4절은 `normalize_benefit()`의 출력에 `limit_struct`를 넣는 방식이었다. 실제 구현은 등록 시점(`_register`)에 추출 원본 `stg_raw_item`에서 바로 만든다.
- 이유 1: `normalize_benefit()` 결과는 공통 혜택 경로(`common_benefit_service.attach_normalized`)와 기존 테스트가 함께 쓴다. 키를 추가하면 영향 범위가 넓어진다.
- 이유 2: 등록부는 이미 `item_limit_txt`·근거 연결을 같은 `stg_raw_item`(보정 적용본)에서 만든다. 같은 원천을 쓰는 편이 일관된다.
- 보존되는 정보(limits, 규칙별 limit_keys, 근거 ID)는 설계와 같다.
- `build_rule()`·`normalize_benefit()`은 변경하지 않았다.

---

## 2. 실제 변경 내용

### 2.1 P0 — `card_graphrag.py`

- **`tier_token(tier) -> tuple[str, float] | None`**: `value`가 int/float(bool 제외)이고 `unit`이 `UNIT_KINDS`(KRW·PERCENT·COUNT)일 때만 토큰을 반환한다. 그 밖에는 `None`(지급액 미확정)이다. `0`은 정상 값 `("MONEY", 0.0)`이다.
- **`rule_conflicts()`**: 구간을 지우지 않고 각 tier에 `payout_known`(bool)을 추가한다. `value`·`unit`은 원값(None 포함) 그대로 둔다.
- **`tier_label()`**: 지급액을 모르면 `"지급액 정보 없음"`이라고 쓴다. 금액을 만들지 않는다.
- **`distorts_tier()`**: 구간 기준액(`minimums`)은 모든 구간에서 모으고, 지급액 비교(`values`와 관계 검사)는 지급값이 확인된 구간만 쓴다.
- **`picks_single_tier()`**: 미확정 구간은 지급액으로 언급될 수 없게 했다. 기준액 비교 전에 `min_amt`가 None인지 확인한다.
- **`tier_is_quoted()`**: 미확정 구간은 기준액만 원문에 있으면 된다(없는 지급액을 요구하지 않음).
- **`validate_answer()`**: 결제 금액이 여러 구간에 해당할 때 만드는 시스템 문장에서, 확인된 지급값이 하나도 없으면 문장을 만들지 않고 경고를 남긴다. 빈 값 집합 때문에 "이미 답함"으로 오판하는 것을 막는다.
- **답변 LLM 지시문**: "`payout_known`이 false인 구간은 지급액을 쓰지 말고 기준 금액만 쓴다. 한도 금액을 그 구간의 지급액으로 옮겨 쓰지 않는다" 1줄을 추가했다.
- try/except는 추가하지 않았다. `tier_text`, `tier_answer`, `fixed_conclusion`, `answer_text_problem`은 위 helper만 통해 지급값에 접근하므로 본문을 바꾸지 않았다(호출부 전수 확인: `tier_token` 호출 7곳, `distorts_tier`·`picks_single_tier` 호출 6곳).

### 2.2 P1 — 추출 한도 구조 보존

`_register()`가 `card_product_item.item_data`(BENEFIT_V1)에 다음을 추가한다.

```json
"limits": [{"limit_key", "limit_num", "cap_unit_cd", "period_cd", "limit_raw_txt", "shared_scope_txt",
            "applies_to_benefit_nms", "evidence_ids": [...]}],
"rule_limits": {"<rule_key>": ["<limit_key>", ...]},
"limit_tiers": { ... }   // 아래 조건을 모두 만족할 때만
```

- `limits`·`rule_limits`: 추출 원본을 해석 없이 복사한다. 등록하지 않는 규칙의 연결은 남기지 않는다. 등록 직후 `check_limit_struct()`로 추출 원본과 키·수치·연결이 같은지 확인하고, 다르면 REVIEW로 둔다.
- `limit_tiers`(`source: "EXTRACTION"`)는 다음을 **모두** 만족할 때만 만든다. 하나라도 어기면 만들지 않는다.
  1. 실적 조건(SPEND_REQ, 결제 1건 기준 `TXN_AMT` 제외)이 있는 규칙이 2개 이상이고, 규칙마다 그 atom이 정확히 1개이며 기준이 같다.
  2. 구간마다 원화 한도가 정확히 1개이고, 한도 키가 구간마다 다르며, 기간이 같고 확정(MONTH·YEAR·DAY)이다.
  3. 구간이 겹치지 않는다. 상한이 없는 구간은 최상위 하나뿐이다. **원문에 없는 상한은 추론하지 않는다.**
  4. 한도마다 LIMIT 근거, 구간마다 조건 근거가 위치 확인된 상태로 있다.
- 구간마다 `rule_key`·`evidence_ids`, cap마다 `limit_key`를 보존한다. 열 이름은 원문 표 머리가 아니라 기간 코드에서 만든 값(`"월 한도"`)이며, `column_source: "PERIOD_CD"`로 표시한다.
- 사람 보정(`SET_LIMIT_TIERS`)이 있으면 그것이 우선이다. 자동 생성은 `item_limit_txt`를 바꾸지 않는다. 사람 보정이 있을 때만 기존처럼 `limit_tiers_text()`로 바꾼다.
- `_links()`: 기존 성공 판정 뒤에, 등록 규칙의 조건식에 실제로 있는 atom의 추출 조건 인용을 `('COND', rule_key, atom_key)`로 추가한다. 위치를 못 찾은 조건 인용은 건너뛴다(기존 등록 판정 불변). `_register`는 이를 신규 SQL `insert_rule_cond_evidence_link`로 기록한다. 기존 데이터의 RULE/COND 형식(`ev_item_cd='COND'`, `ev_item_key=atom_key`)과 같고, 자연 키 충돌 시 `DO NOTHING`이다.
- `rule_list`(6개 키), `value_num`, `value_unit_cd`, `item_limit_txt`(자동 경로)의 의미와 값은 바뀌지 않는다. DDL·새 컬럼은 없다(`fn_valid_item_data`는 BENEFIT에 대해 `schema_ver`만 검사).

---

## 3. NULL 처리 전후 동작

실제 데이터 형태(22/20261105_000099, r1·r2·r3 지급값·단위 NULL, r1 300,000~800,000, r2 800,000~)로 확인했다.

| 호출 | 수정 전 | 수정 후 |
|---|---|---|
| `distorts_tier("자동납부 시 할인됩니다.")` | TypeError | False |
| `distorts_tier("전월 실적 30만원 이상이면 할인됩니다.")` | TypeError | False |
| `tier_text(conflict)` | TypeError | "30만원 이상 시 지급액 정보 없음, 80만원 이상 시 지급액 정보 없음 구간이 기재되어 있습니다." |
| `tier_is_quoted(conflict, …)` | TypeError | 30만·80만 기준이 한 인용에 있으면 True, 아니면 False |
| `rule_conflicts()` tier | `value: None` | `value: None`, `payout_known: False` (0으로 바꾸지 않음, 구간 유지) |
| `validate_answer()` | 유효 포인트가 하나라도 있으면 TypeError로 전체 실패 | 정상 포인트 유지, 근거 없는 금액(예: 20,000원) 문장은 기존 값 검증으로 버림 |
| 실제 Neo4j 상세 행(읽기 전용) | TypeError | 예외 없음(통합 테스트 통과) |

**예외가 나지 않는 것과 답변이 정확한 것은 다르다.**
- 수정 후에도 LLM이 `limit_text`의 10,000원·15,000원을 다른 구간에 잘못 배정하면 걸러내지 못한다. 두 금액 모두 근거에 있는 값이고, 구간별 지급값이 없어 구간 관계 검증 대상이 아니기 때문이다(설계 D6).
- 답변 지시문으로 위험을 줄였을 뿐이다. 구간별 한도가 Neo4j로 전달되고 검증이 추가되는 P2(설계 7.4절) 전까지는 정확성을 보장하지 않는다.
- 실제 LLM으로 원 질문을 다시 돌려 보지는 않았다(유료 호출 금지).

---

## 4. 구간별 한도 데이터 보존 결과 (실제 추출 이력 fixture)

| 혜택 | `limits` | `rule_limits` | `limit_tiers` | 조건 근거 연결 |
|---|---|---|---|---|
| 22/099 월납 요금 | l1 10,000(MONTH, 근거 002681), l2 15,000(MONTH, 근거 002682) | r1→l1, r2→l2, r3→l1·l2 | **생성**: r1 30만~80만→10,000원(근거 002685), r2 80만~(상한 없음, 최상위)→15,000원(근거 002686) | (r1,c1,002685), (r2,c2,002686), (r3,c3,002687) |
| 23/100 간편결제 추가적립 | l1 1만(002739), l2 2만(002740), l3 5만(002741) | r1→l1, r2→l2, r3→l3 | **생성 안 함**: 구간 상한이 원문에 없어 겹침(상한을 추론하지 않음) | 위치 확인된 조건 인용 연결 |
| 20/092 골프/아울렛 | bonus_base_cap 10만, bonus_additional_cap 10만(기간 UNKNOWN) | 규칙별 1:1 | **생성 안 함**: 누적형(상한 없음·기간 불명확). 합계(20만 원)를 만들지 않음 | 위치 확인된 조건 인용 연결 |
| 한도 없는 혜택 | 없음 | 없음 | 없음 | `item_data = {}` 그대로, 쓰기 순서도 기존과 동일 |

이 결과는 **새로 등록하는 경우**에 적용된다. 기존 3건의 DB 행은 바뀌지 않았다. 등록 프로그램은 이미 등록된 혜택을 `UNCHANGED`로 건너뛰므로, 기존 행 보정은 별도 승인 단계(설계 5절)가 필요하다.

---

## 5. 테스트 목록 및 결과

실행 명령: `src/card_benefit`에서 `PYTHONPATH="../;."`로 `pytest payment_card/tests payment_card/db_pipeline`. 실제 연결 변수(`DB_URL`, `NEO4J_*`, `OPENAI_API_KEY`, `SUPABASE_*`)는 빈 값으로 막았다.

| 실행 | 통과 | 실패 | 건너뜀 |
|---|---:|---:|---:|
| 수정 전 기준선 | 625 | 11 | 19 |
| 수정 후 전체 | **653** | **11** | 20 |
| 신규 `test_tier_null_payout.py` | 14 | 0 | 1(통합) |
| 신규 `test_limit_struct.py` | 14 | 0 | 0 |
| 통합 `LiveSimpleMonthlyTests`(`RUN_NEO4J_INTEGRATION=1`, Neo4j 읽기 전용) | 1 | 0 | 0 |

### 신규 테스트가 다루는 항목

- **P0**: `value_num=None`·`value_unit_cd=None`(따로 및 함께), `value_num=0`(KRW·PERCENT), 정상 숫자, 문자열·bool 거부, 전월 실적 구간 2개 이상, 숫자 없는 문장, 금액이 잘못된 문장(확인된 구간의 왜곡은 계속 차단, 근거 없는 20,000원은 버림), 값 있는 구간과 없는 구간 혼합, 0원 구간의 왜곡 검출, 결제 건 기준 두 구간에 모두 해당하는데 지급값이 없는 경우, `answer_text_problem` 경로, 기존 정상 구간 검증(기존 `test_card_graphrag.py` 구간 테스트 전부 통과).
- **P1**: 22 r1→10,000원·r2→15,000원 보존과 구간 표 생성, 23 1만·2만·5만 보존과 상한 미추론, 20 누적형을 배타적 구간으로 바꾸지 않음, 추출 원본과 규칙 key 일치(등록하지 않는 규칙 제외, 변조 감지), 규칙·한도·구간별 근거 ID 유지, 구간 근거가 없으면 구간 표를 만들지 않음, 조건 근거 연결(RULE/COND)과 위치 없는 인용 건너뜀, 사람 보정 우선, 한도 없는 혜택의 기존 동작, `value_num` 불변.

### 실패 11건의 분류 — 모두 수정 전부터 존재

| 테스트 | 분류 | 내용 |
|---|---|---|
| `test_card_graphrag.py::StreamlitTests` 10건 | **수정 전부터 존재 / 환경 영향** | Streamlit AppTest 화면 테스트. 기준선에서도 같은 10건이 실패했다. 실행 중 Neo4j 연결 시도(`NEO4J_FAILED type=OSError`)와 실행 로그 DB 풀 연결 시간 초과 로그가 함께 나온다. `streamlit_app.py`·`execution_log.py`(변경 금지 파일)와 로컬 환경에 의존하며 이번 수정과 관계가 없다 |
| `test_answer_text.py::test_unresolved_tier_cannot_be_decided_in_natural_text` | **수정 전부터 존재** | 기준선에서도 `answer_source`가 기대값 `validated_sentences`가 아니라 `program_tier`로 나와 실패했다. 수정 후에도 같은 이유로 실패한다(실패 양상 동일) |

**이번 수정으로 새로 생긴 실패는 0건이다.** 실패 목록 11건은 수정 전후에 정확히 같다.

---

## 6. 기존 기능 영향

- **정상 숫자 구간 검증**: 동작이 같다. 기존 구간 테스트 전부 통과. 데이터에서 `value`만 있고 `unit`이 없는 규칙은 0건이라, 단위 조건 추가가 기존 판정을 바꾸지 않는다.
- **LLM 문맥**: `rule_selection_unresolved`의 tier에 `payout_known` 키가 하나 늘었다. 답변 지시문은 1줄 추가.
- **등록**
  - 한도가 있는 신규 혜택의 `item_data`에 `limits`·`rule_limits`(조건 충족 시 `limit_tiers`)가 추가된다.
  - 규칙 조건 근거 연결(`RULE/COND`) 행이 추가로 기록된다.
  - 한도가 없는 혜택, 기존 행(`UNCHANGED`), 사람 보정 경로는 기존과 같다.
- **Neo4j**: 아직 영향 없음. 적재 SELECT가 혜택 `item_data`를 읽지 않으므로(P2 미적용) 새 구조는 다시 적재해도 그래프에 들어가지 않는다. 새 조건 근거 연결은 다음 적재 때 `dp_supported_by`·근거 노드로 반영된다.
- **공유 한도 검사**(`shared_limit_problems`), 공통 혜택 등록 경로: 변경 없음.

---

## 7. 아직 해결되지 않은 문제

1. **D6**: 답변 검증이 한도 금액의 구간 배정을 검사하지 않는다. 예외는 사라졌지만 22의 구간별 한도가 정확히 답변되는지는 보장하지 않는다.
2. **기존 데이터 3건**(22/099, 23/100, 20/092): DB의 `item_data`에 한도 구조가 없고, 조건 근거(002685·002686 등)가 연결되지 않은 상태 그대로다.
3. **D4·D5**: Neo4j 적재가 혜택 `item_data`를 읽지 않고, 검증기는 이 누락을 감지하지 못한다.
4. **23/100 구간 상한**: B2안(규칙은 그대로 두고 `limit_tiers`에만 다음 구간 하한을 상한으로 기록)은 승인 전이라 반영하지 않았다.
5. **혜택 단위 조건 인용**(BNFT/COND)의 근거 연결은 이번 범위(규칙 조건)에 넣지 않았다.
6. **DAILY 179 검색 품질 문제**: 별도 조사 대상(설계 8절), 변경 없음.
7. 기존 실패 테스트 11건(5절)은 이번 작업과 별개로 남아 있다.

---

## 8. P2 및 기존 데이터 보정 전 선행 조건

1. 이번 P0·P1 변경의 코드 리뷰와 커밋. 사용자가 진행한다(이번 작업에서는 커밋하지 않음).
2. **기존 데이터 보정(DB 쓰기) 승인 항목**
   - PG `card_product_item` UPDATE 3행(`item_data`만, ID·`rule_list`·`item_limit_txt`·임베딩 불변): 22/20261105_000099, 23/20261105_000100, 20/20261105_000092.
   - `card_evidence_link` INSERT: 22 (r1,c1,002685)·(r2,c2,002686)·(r3,c3,002687), 23 r1~r3 조건 근거 3건(002744~002746), 20 조건 근거 2건(002453·002454). 20의 atom key는 보정 도구 미리보기에서 확인한다.
   - 23/100 구간 상한 B2안 승인 여부.
   - 23/100 "통합 월 적립 한도"가 이 혜택 전용인지, 다른 특별 적립과 공유하는지에 대한 원문 확인.
   - 보정 도구는 이번에 구현한 `limit_struct`·`check_limit_struct`·`limit_tiers_from_extraction`·`_cond_evidence`를 재사용해 같은 결과를 계산해야 한다(설계 5.1절). 실행 전 백업 스크립트를 현재 스키마에서 그대로 실행할 수 있는지 확인한다.
3. **P2 승인 항목**
   - `neo4j_dry_run.load_snapshot` 혜택 SELECT에 `item_data` 추가, `neo4j_validate`의 컬럼 완전성·직접 값 대조.
   - Neo4j 전체 MERGE 재적재(`APPROVED_DP_HANA_CARD`).
   - 이후 `benefit_context`의 `limit_tiers` 전달과 한도 구간 검증(D6).
