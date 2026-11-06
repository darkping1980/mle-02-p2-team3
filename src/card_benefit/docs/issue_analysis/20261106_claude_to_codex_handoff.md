# Claude → Codex 인수인계: GraphRAG 지급값 NULL 오류·한도 데이터 손실 수정

- 작성일: 2026-11-06
- 작성: Claude (크레딧 부족으로 Codex에 이관)
- 대상: `C:\myproject\workspace\mle-02-p2-team3\src\card_benefit\`
- **DB 상태**: PostgreSQL·Neo4j 모두 이 작업에서 **한 번도 쓰지 않았다**(SELECT·읽기 전용 Cypher만). 재적재·배포·커밋·Push도 하지 않았다. 유료 LLM 호출 0건.

## 0. 먼저 읽을 문서 (모두 `src/card_benefit/docs/issue_analysis/`)

| 문서 | 내용 | Git |
|---|---|---|
| `20261106_tier_value_none_typeerror.md` | 최초 `float(None)` 직접 원인(다른 AI 작성) | 커밋됨 |
| `20261106_postgresql_neo4j_mapping_query_audit.md` | PG→Neo4j 전체 감사, 손실 위치 확정 | 커밋됨(fcb2a51) |
| `20261106_graphrag_data_loss_fix_plan.md` | P0~P2·데이터 보정 설계 | **미커밋(untracked)** |
| `20261106_graphrag_p0_p1_implementation_result.md` | P0·P1 구현 결과 | **미커밋(untracked)** |
| 이 문서 | 인수인계 | 미커밋 |

---

## 1. 확정된 원인 요약 (재조사 불필요)

1. **직접 예외**: `card_graphrag.tier_token()`의 `float(tier["value"])`에서 발생한다. 더 심플 하나카드(card 22) `월납 요금 청구할인`(20261105_000099)의 규칙 r1·r2·r3는 `value_num`과 `value_unit_cd`가 NULL이다. 그런데 r1·r2에는 전월 실적 구간(30만~80만, 80만~)이 있어서 tier로 만들어진다. 금액이 없는 문장("자동납부 시 할인됩니다.")에서도 예외가 났다.
2. **데이터 손실 위치**: PG 등록 단계에서 사라졌다.
   - 추출 원본 `card_extr_stg 20261105_000619`에는 `limits l1=10000, l2=15000`과 `r1.limit_keys=[l1]`, `r2.limit_keys=[l2]`가 있었다.
   - `build_rule()`·`normalize_benefit()`이 이 구조를 버렸고, 등록부는 평문 `item_limit_txt`만 저장했다.
   - 구간과 금액을 함께 인용한 근거(002685·002686)는 연결되지 않았다.
3. **적재 누락**: `neo4j_dry_run.load_snapshot` 혜택 SELECT에 `item_data`가 없었다. `neo4j_validate`도 같은 스냅샷으로 기대값을 만들어서 이 누락을 감지하지 못했다.
4. **정상 구조(바꾸지 말 것)**: `dp_card_bnft` 라벨은 현행 혜택 표현이다(노드에 `dp_card_product_item` 라벨이 함께 붙음). 구형 노드 잔존은 없다. Cypher 오조회도 없다.

---

## 2. 완료한 작업

### 2.1 P0 — NULL 지급값 안전 처리: **구현 완료 및 테스트 통과**

`payment_card/db_pipeline_origin_search/card_graphrag.py`

| 함수 | 변경 |
|---|---|
| `tier_token` | `-> tuple[str, float] \| None`. 값이 int/float(bool 제외)이고 단위가 `UNIT_KINDS`일 때만 토큰, 아니면 None. 0은 정상 값 |
| `rule_conflicts` | tier마다 `payout_known` 추가. 구간을 지우지 않고 value는 None 그대로 |
| `tier_label` | 미확정이면 "지급액 정보 없음"으로 표기 |
| `distorts_tier` | 기준액은 모든 tier로 모으고, 지급 비교는 `payout_known` tier만 |
| `picks_single_tier`, `tier_is_quoted` | None 토큰과 `min_amt` None 방어 |
| `validate_answer` | 결제 금액 구간 시스템 문장: 확인된 지급값이 없으면 문장을 만들지 않고 경고 |
| 답변 LLM 지시문 | `payout_known=false` 구간 지급액 금지 문구 1줄 |

try/except는 쓰지 않았다. 테스트: `payment_card/tests/test_tier_null_payout.py`(14 통과, Neo4j 읽기 전용 통합 1건은 `RUN_NEO4J_INTEGRATION=1`일 때 통과 확인).

### 2.2 P1 — 신규 등록 시 한도 구조 보존: **구현 완료 및 테스트 통과**

| 파일 | 함수 | 변경 |
|---|---|---|
| `db_pipeline/extraction_service.py` | 신규 `limit_struct`, `check_limit_struct`, `limit_tiers_from_extraction`, `_spend_atoms` | 추출 원본 `limits`·`rules[].limit_keys`를 해석 없이 보존. 구간 표는 엄격한 조건(구간 2개 이상, 구간별 KRW 한도 1개, 서로 다른 키, 확정 기간, 겹치지 않음, 근거 위치 확인)에서만 생성 |
| `db_pipeline/product_benefit_service.py` | `_register`, `_links`, 신규 `_located`·`_match`·`_limit_evidence`·`_cond_evidence` | `item_data`에 `limits`·`rule_limits`(·`limit_tiers`) 저장. 규칙 조건 인용을 `('COND', rule_key, atom_key)`로 연결. 사람 보정 `SET_LIMIT_TIERS`가 우선이고, 자동 경로는 `item_limit_txt`를 바꾸지 않음 |
| `db_pipeline/common_benefit_repository.sql` | 신규 `insert_rule_cond_evidence_link` | `RULE/COND` 근거 연결 INSERT(자연 키 `DO NOTHING`) |

- 설계와 다른 점: `normalize_benefit()` 출력이 아니라 `_register`에서 `stg_raw_item`으로부터 만든다(공통 혜택 경로·기존 테스트 영향 회피). `build_rule`·`normalize_benefit`은 변경하지 않았다.
- 테스트: `payment_card/tests/test_limit_struct.py`(14 통과). fixture는 `payment_card/tests/fixtures_limit_struct.json`(22/099·23/100·20/092 실제 추출 원본, 읽기 전용으로 옮김).
- 기존 등록 행은 등록 프로그램이 `UNCHANGED`로 건너뛰므로 **기존 3건 DB 데이터에는 반영되지 않았다**(4절 보정 필요).

### 2.3 P0·P1 회귀 결과 (실행함)

- 수정 전 기준선: 625 통과 / 11 실패 / 19 건너뜀.
- P0·P1 후: **653 통과 / 11 실패 / 20 건너뜀**. 실패 11건은 수정 전과 같다(7절).

---

## 3. P2 상태 (항목별)

| # | 항목 | 상태 | 파일·함수 | 비고 |
|---|---|---|---|---|
| 1 | Neo4j BENEFIT 적재 SELECT에 `item_data` 추가 | **구현 완료 및 테스트 통과** | `neo4j_dry_run.py`: `BENEFIT_COLUMNS`·`ITEM_COLUMNS`·`LINK_COLUMNS`, `select_sql`, `BENEFITS_SQL`/`ITEMS_SQL`/`LINKS_SQL`, `load_snapshot`이 이를 사용 | SELECT를 컬럼 표에서 생성. **items·links SQL은 기존과 같은 열**(테스트로 문자열 고정). `item_data`는 dict라 노드 속성은 생기지 않고 `source_json`에만 들어감. Cypher 변경 불필요(`card.context`가 source_json 반환) |
| 2 | PG 원천 컬럼 완전성 검증 | **구현 완료 및 테스트 통과** | `neo4j_dry_run.column_coverage`, `SOURCE_EXCLUDED`(사유 포함), `SNAPSHOT_COLUMNS`. SQL `neo4j_validation.source_columns`. `neo4j_validate.source_column_map` | `information_schema`에서 읽어 미분류 컬럼, 원천에 없는 매핑, 스냅샷 행에 없는 매핑 컬럼을 실패로 처리. P2 이전 SELECT(item_data 없음)를 재현하면 검출됨(테스트) |
| 3 | PG ↔ Neo4j 독립 `item_data` 비교 | **구현 완료 및 테스트 통과** | `neo4j_validate.compare_item_data`. SQL `neo4j_validation.benefit_item_data`. Cypher `neo4j_validation.benefit_item_data`. `run()`의 `ok`에 `column_coverage`·`item_data_mismatch` 반영 | **실제 읽기 전용 실행 결과**: 노드 1,635·관계 2,702가 일치하는데도 `item_data_mismatch 34`(모두 "Neo4j source_json에 item_data 키 없음"), `node_properties_changed 34`(source_json), `column_coverage []`, `ok=false`. 재적재 전이라 기대된 검출이다 |
| 4 | GraphRAG 상세 문맥에 `limit_tiers` 전달 | **구현 완료 및 테스트 통과** | `card_graphrag.benefit_context`, 신규 `limit_tier_view`, `known_values`(구간 하한·cap 추가), LLM 지시문 1줄 | limit_tiers가 없으면 키를 넣지 않음(기존 문맥 불변). 공유 한도(shared, DAILY 통합 할인한도)도 전달 |
| 5 | 구간별 월 한도 오배정 검증 | **구현 완료 및 테스트 통과** | 신규 `card_graphrag.distorts_limit_tier`. `validate_answer`(포인트·결론), `answer_text_problem`에서 호출 | "N원 이상"의 N이 구간 하한이면 현재 구간으로 둔다. 그 혜택의 다른 구간에만 있는 cap이 나오면 차단. 경계 금액, 다른 혜택에만 있는 금액, limit_tiers 없는 혜택은 판정하지 않음(비교 질문 오탐 방지). P0의 `distorts_tier`와 독립 |
| 6 | 단위 테스트 | **구현 완료 및 테스트 통과** | `payment_card/tests/test_p2_limit_tiers.py`(17 통과), fixture `payment_card/tests/fixtures_limit_tiers_daily.json`(42/179·180 실제 limit_tiers) | 22(P1 helper 생성값), 23·20(limit_tiers 없음 → 판정 안 함), DAILY 공유 한도, 오탐 방지, validate_answer·answer_text_problem |
| 6' | P2 전체 회귀 | **구현 완료 및 테스트 통과** | | 670 통과 / 11 실패(전부 기존) / 20 건너뜀. 신규 실패 0(7.2절) |

**주의**
- 22/099의 `limit_tiers`는 아직 DB에 없다. P2 테스트는 P1 helper가 추출 원본에서 만드는 값으로 시험했다. 실서비스 효과는 4절 보정과 Neo4j 재적재 뒤에 생긴다.
- 지금 상태에서 `neo4j_validate`를 돌리면 `ok=false`(34건)가 정상이다. 재적재 후 0이 되어야 한다. 고아 문서 `["card_doc","20261103_000012"]` 1건은 예전부터 알려진 항목이다.
- `SOURCE_EXCLUDED["items"]["item_origin_cd"]`는 "혜택 외 항목은 현재 모두 LOCAL, 추가하면 항목 노드 source_json이 바뀌므로 별도 결정"으로 제외해 두었다. 의도적 보류다.

---

## 4. 미해결 데이터 보정 (DB 쓰기, 승인 필요)

### 4.1 대상과 내용 (읽기 전용으로 확정)

| 혜택 | item_data에 넣을 값 | 근거 연결 INSERT(`RULE`/`COND`, 모두 현재 미존재 확인) |
|---|---|---|
| 22/20261105_000099 | `limits`(l1 10000/002681, l2 15000/002682), `rule_limits`(r1→l1, r2→l2, r3→l1·l2), `limit_tiers`(r1 30만~80만→10,000원/근거 002685, r2 80만~→15,000원/근거 002686) | (r1,c1,002685), (r2,c2,002686), (r3,c3,002687) |
| 23/20261105_000100 | `limits`(1만/002739, 2만/002740, 5만/002741), `rule_limits`(r1→l1, r2→l2, r3→l3). **limit_tiers 없음**(상한 B2안 승인 보류) | (r1,c1,002744), (r2,c2,002745), (r3,c3,002746) |
| 20/20261105_000092 | `limits`(bonus_base_cap 10만, bonus_additional_cap 10만, 기간 UNKNOWN, 근거 002447·002448), `rule_limits` 1:1. **limit_tiers 만들지 않음**(누적형). 합계 계산 금지 | (bonus_base_discount, bonus_spend_24m, 002453), (bonus_additional_cap_discount, bonus_spend_36m, 002454). atom key 일치 확인 완료 |

- **근거 INSERT 총 8건**(신규, 기존 0건).
- 값은 P1 helper를 실제 PG 데이터(청크 원문으로 위치 재확인, 13/13·16/16·19/19 위치 확인)에 돌려 계산했다.
- 바꾸지 않는 것: `item_limit_txt`, `rule_list`, 검색 텍스트, 임베딩, ID.

### 4.2 7건 → 8건으로 바뀐 이유 (확정)

- 설계 문서(fix_plan 5절)는 22에서 구간 표기 인용 2건(r1·r2)만 셌다: 2+3+2 = 7.
- P1에서 구현한 `_cond_evidence`는 등록 규칙의 **모든 규칙 조건 인용**을 연결한다. 그래서 22의 r3 조건(ETC, "월납 요금 승인 금액이 할인 한도보다 적을 경우", 근거 002687)도 포함된다: 3+3+2 = **8**.
- 신규 등록 동작과 같은 규칙으로 보정해야 하므로 8건이 맞다. r3 연결을 빼려면 별도 결정이 필요하다.
- **Neo4j 영향 수치도 함께 바뀐다**: 8개 근거 노드가 그래프에 없음을 확인했다. 보정 후 재적재 시 예상 결과는 노드 1,635→**1,643**, 관계 2,702→**2,718**(in_chunk 8 + supported_by 8)이다. 설계 문서의 1,642/2,716은 낡은 값이다. 미리보기 수치로 최종 확인한다.

### 4.3 보정 실행 전 필요사항 (미구현)

- **보정 도구는 아직 만들지 않았다.** 설계 fix_plan 5.1절대로 `payment_card/db_pipeline/limit_struct_backfill.py`와 대장 `docs/identity_registry/benefit_patch/LIMIT_STRUCT_BACKFILL_20261106.json`을 새로 만든다.
  - 기본은 미리보기, `--apply --confirm` 확인 문구, `--rollback`.
  - P1 helper(`limit_struct`, `check_limit_struct`, `limit_tiers_from_extraction`, `ProductBenefitService._located/_limit_evidence/_cond_evidence`)를 재사용한다.
  - UPDATE 조건: `item_data = '{}'::jsonb AND md5(rule_list::text) = :fp`.
  - 근거는 `insert_rule_cond_evidence_link`로 넣는다.
- 기존 등록 프로그램으로는 고칠 수 없다(`UNCHANGED`). 삭제 후 재등록은 ID가 바뀌므로 금지.
- **사용자 승인 항목**: ① UPDATE 3행 ② INSERT 8건 ③ 23/100 B2안(규칙은 그대로, `limit_tiers.max_amt_excl`에 다음 구간 하한 + `max_basis: "NEXT_TIER_MIN"`) 여부 ④ 23/100 "통합 월 적립 한도"(근거 002742)가 이 혜택 전용인지 공유인지 원문 확인.
- **백업**: `backup_db_pipeline.py`가 삭제된 `stg_normalized_item` 지문을 조회해 그대로는 실패한다는 기록이 있다(메모리 기준). 실행 전 확인이 필요하다.
- **롤백**: 도구가 실행 결과 파일(이전 `item_data`, 생성된 `evidence_link_id`)을 남기고 `--rollback`으로 복원한다.
- **Neo4j 재적재 승인**: `neo4j_load_draft --apply --confirm APPROVED_DP_HANA_CARD`(전체 MERGE, 삭제 없음, `NEO4J_DATABASE=6ac1f0f8`). 재적재 전 Neo4j 백업, 이후 `neo4j_validate` 차이 0, `neo4j_search_projection_sync` 미리보기 차단 0을 확인한다. 임베딩은 저장값을 다시 SET하므로 재생성하지 않는다.

---

## 5. 별도 QA 이슈 — ONE PICK STYLE 캐시백 구간 답변

- 요청받은 별도 문서 `20261106_onepick_style_cashback_tier_qa_issue.md`는 **작성하지 못했다**(인수인계 우선). 아래는 이미 확인한 사실과 미확인 사항이다.
- **현상**(사용자 제보): CARD10-021 등에서 "1만원 이상 결제는 두 금액 구간에 모두 해당하지만, 어떤 캐시백 금액이 적용되는지는 아직 확정되지 않았습니다."라고 답한다.

### 5.1 확인된 사실 (감사·코드 정독 중 확인)

- PG 규칙(card 2): `one_pick_100`(100원, KRW)과 `one_pick_500`(500원)이 같은 대상이다. 각 규칙 조건은 `SPEND_REQ`, `TXN_AMT` 기준이고 하한이 3,000원/10,000원이며 **상한(`cond_max_amt_excl`)이 없다**(atom key `MIN_one_pick_100/500`). STYLE도 같은 구조다(`style_100/500`).
- 원인은 추출의 `min_txn_amt`가 `build_rule()`에서 `MIN_<rule>` SPEND_REQ 조건으로 바뀌면서 상한이 없는 것이다.
- Python 경로: 규칙 2개가 대상을 공유하므로 `rule_selection_open() = True` → `rule_conflicts()`의 `applicable_rule_keys`가 결제 1만원에서 두 규칙 모두가 된다(`tier_applies`: `amount >= min`이고 max 없음) → `fixed_conclusion()`/`tier_answer()`가 위 고정 문구를 만든다. **이 문구는 프로그램이 만든 문장이다**(LLM 생성 아님).
- 기존 테스트(`test_card_graphrag.py`의 `tier_context`, ONE PICK·STYLE 형태)는 이 동작을 **의도된 동작으로 고정**하고 있다. 예: "1만원 결제는 100원 구간과 500원 구간에 모두 해당" 허용. 2026-11-05 이전 설계에서 "원문에 우선 규칙이 없으면 단정하지 않는다"로 정했다는 뜻이다.
- **P2(limit_tiers)와는 무관하다.** 결제 1건 기준(`TXN_AMT`)은 `limit_tiers_from_extraction`의 `TIER_EXCLUDED_BASIS`로 구간 표 대상에서 제외된다. P0 변경도 이 혜택(지급값이 모두 있음)의 동작을 바꾸지 않는다.

### 5.2 미확인 (Codex가 확인할 것)

- 공식 상품설명서 원문(card 2 문서, `card_doc_chunk`)이 "1만원 이상 결제 시 500원"처럼 상위 구간 우선(배타적)을 명시하는지, 표 형식으로만 적혀 있는지는 이번 작업에서 **원문을 다시 대조하지 않았다**. 사용자 제보의 원문 요약(건당 3,000원 이상 100원, 10,000원 이상 500원)만 있다.
- 원문이 구간표(사다리)로만 적혀 있다면 "상위 구간 적용"은 일반적인 해석이지만 원문 명시는 아니다. 사실과 해석을 구분해 사용자 결정을 받아야 한다. **원문에 없는 우선순위를 임의로 확정하지 말 것.**

### 5.3 권고

- 별도 이슈로 다룬다(P2와 분리).
- 결정 후보:
  - (a) 현행 유지: 원문 명시가 없으면 미확정.
  - (b) 원문이 사다리 표임을 근거로 사용자 승인 후 구간 상한을 기록(23/100 B2안과 같은 방식, `max_basis` 표시).
  - (c) 답변 문구만 완화.
- 경계값 회귀 테스트 제안: 결제 2,999원(해당 없음)·3,000원(100원)·9,999원(100원)·10,000원(현행: 두 구간 / 결정 후: 500원)·10,001원. ONE PICK(일 1회·월 30회·월 5,000원)과 STYLE(일 1회·월 10회·월 5,000원)의 한도는 구간과 무관하게 유지. "지난달 실적 조건 없음"을 미확정으로 쓰지 않는지도 확인.

---

## 6. 다른 미해결 이슈

| 이슈 | 상태 | 메모 |
|---|---|---|
| DAILY 42/179(통신 5%, 180과 통합 한도 공유)가 검색 후보(키워드 채널 3위)에는 있었지만 상세 조회에서 빠짐 | **원인 미확정**, 수정 안 함 | 조사 방법은 fix_plan 8절. interpret LLM 출력·hybrid hits 로그가 필요한데 `streamlit_app.py`·`execution_log.py`(Codex 소유)와 관련됨 |
| `StreamlitTests` 10건 실패 | 수정 전부터 존재 | 로컬 Neo4j·로그 DB 연결 시도와 함께 실패(환경 영향 추정). 이번 작업과 무관 |
| `test_answer_text.py::test_unresolved_tier_cannot_be_decided_in_natural_text` | 수정 전부터 존재 | 기대 `validated_sentences`, 실제 `program_tier`. 원인 미조사 |
| 혜택 단위 조건 인용(BNFT/COND) 근거 연결 | 범위 밖으로 둠 | P1은 규칙 조건(RULE/COND)만 |
| `neo4j_load_draft`의 `SET n += $props`가 속성을 지우지 않음 | 잠재 결함, 수정 안 함 | 감사 문서 L3 |
| `tests/test_live_registration.py`가 없는 `db_pipeline.card_bnft` 참조 | 잠재, 미실행 | 감사 문서 P8 |

**작업 충돌 주의**: `streamlit_app.py`, `execution_log.py`, `card_search_execution_log.sql`은 Codex 담당 파일이다. Claude는 이 세 파일을 수정하지 않았다.

---

## 7. Git·코드 상태

### 7.1 Git

- 브랜치: `main`
- HEAD: `fcb2a51 오류 발생 원인 클로드 가 정리`
- **모든 변경이 미커밋이다.** Claude는 커밋·Push를 하지 않았다.

| 상태 | 파일 | 역할 | 작성 |
|---|---|---|---|
| M | `payment_card/db_pipeline_origin_search/card_graphrag.py` | P0(tier NULL) + P2(limit_tiers 문맥·distorts_limit_tier) | Claude |
| M | `payment_card/db_pipeline/extraction_service.py` | P1 helper | Claude |
| M | `payment_card/db_pipeline/product_benefit_service.py` | P1 등록·근거 연결 | Claude |
| M | `payment_card/db_pipeline/common_benefit_repository.sql` | P1 `insert_rule_cond_evidence_link` | Claude |
| M | `payment_card/db_pipeline/neo4j_dry_run.py` | P2 컬럼 표·SELECT 생성·`column_coverage` | Claude |
| M | `payment_card/db_pipeline/neo4j_validate.py` | P2 컬럼 완전성·item_data 대조 | Claude |
| M | `payment_card/db_pipeline/neo4j_validation.sql` | P2 `source_columns`, `benefit_item_data` | Claude |
| M | `payment_card/db_pipeline/neo4j_validation.cypher` | P2 `benefit_item_data` | Claude |
| ?? | `payment_card/tests/test_tier_null_payout.py` | P0 테스트 | Claude |
| ?? | `payment_card/tests/test_limit_struct.py`, `fixtures_limit_struct.json` | P1 테스트·fixture | Claude |
| ?? | `payment_card/tests/test_p2_limit_tiers.py`, `fixtures_limit_tiers_daily.json` | P2 테스트·fixture | Claude |
| ?? | `docs/issue_analysis/20261106_graphrag_data_loss_fix_plan.md`, `..._p0_p1_implementation_result.md`, 이 문서 | 문서 | Claude |

(경로는 `src/card_benefit/` 기준.) 다른 작업자가 같은 시점에 수정 중인 파일은 `git status`에 나타나지 않았다. 작업 시작 시점 트리는 clean이었다.

**미완료 코드**: 없다. P2 코드는 모두 동작하는 상태로 남겼다. 미구현은 보정 도구(4.3)와 ONE PICK 이슈 문서·수정(5)이다.

### 7.2 테스트 명령과 결과

공통 명령(오프라인, 실제 연결 변수 차단). `src/card_benefit`에서 Git Bash로 실행한다.

```bash
cd /c/myproject/workspace/mle-02-p2-team3/src/card_benefit
export PYTHONIOENCODING=utf-8 DB_URL= NEO4J_URI= NEO4J_USERNAME= NEO4J_PASSWORD= OPENAI_API_KEY= SUPABASE_URL= SUPABASE_SECRET_KEY=
PYTHONPATH="../;." ../../.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider payment_card/tests payment_card/db_pipeline
# 신규 테스트만
PYTHONPATH="../;." ../../.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider \
  payment_card/tests/test_tier_null_payout.py payment_card/tests/test_limit_struct.py payment_card/tests/test_p2_limit_tiers.py
# Neo4j 읽기 전용 통합(실제 .env 필요, export로 비운 변수를 다시 채운 셸에서)
RUN_NEO4J_INTEGRATION=1 PYTHONPATH="../;." ../../.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider \
  "payment_card/tests/test_tier_null_payout.py::LiveSimpleMonthlyTests"
```

검증기 읽기 전용 실행(프로젝트 루트에서, `.env` 필요):

```bash
cd /c/myproject/workspace/mle-02-p2-team3
PYTHONIOENCODING=utf-8 PYTHONPATH="src;src/card_benefit" .venv/Scripts/python.exe -m payment_card.db_pipeline.neo4j_validate
```

| 실행 | 결과 |
|---|---|
| 기준선(수정 전) | 625 통과 / 11 실패 / 19 건너뜀 |
| P0·P1 후 | 653 통과 / 11 실패 / 20 건너뜀 |
| P2 신규 테스트 `test_p2_limit_tiers.py` | 17 통과 |
| P2 후 전체 회귀 | **670 통과 / 11 실패 / 20 건너뜀**(+17 = P2 신규). 실패 11건은 기준선과 같은 목록(StreamlitTests 10 + test_answer_text 1), 신규 실패 0 |
| `neo4j_validate`(P2 코드, 읽기 전용) | `ok=false`: item_data_mismatch 34, node_properties_changed 34, column_coverage [] — 재적재 전 기대 결과 |

---

## 8. Codex 실행 순서

1. **변경 보존**: `git status`가 7.1 표와 같은지 확인한다. 필요하면 작업 브랜치를 만들어 P0·P1·P2를 나눠 커밋한다(사용자 지시 시). 다른 파일을 되돌리지 않는다.
2. **P0·P1·P2 확인**: 7.2의 신규 테스트 명령을 실행한다. 완료 조건: 신규 48건(14+14+17, 통합 1건 건너뜀 제외) 통과, 전체 회귀에서 실패 목록이 7절의 기존 11건과 같음.
3. **P2 잔여**: 코드 구현은 완료다. 원하면 `item_origin_cd`(items) 포함 여부만 결정한다.
4. **보정 도구 구현**: `limit_struct_backfill.py` + 대장(4.3). 단위 테스트는 fixture `fixtures_limit_struct.json` 재사용, 가짜 repo로 UPDATE 3·INSERT 8 계획과 멱등성, 롤백을 검증한다.
5. **보정 미리보기**(읽기 전용): 대상 3행 현재 `item_data`가 `{}`이고 `md5(rule_list)` 지문 일치, 계산값이 4.1 표와 같음, INSERT 8건, 대상 외 지문 불변.
6. **사용자 승인 요청**: 4.3의 ①~④, 백업 방법.
7. **승인 후 PG 보정**: 도구 `--apply`. 사후 검사(item_data 3행 일치, 근거 +8, 다른 컬럼·행 불변, `v_card_integrity_issue` 증가 없음). 실패 시 `--rollback`.
8. **승인 후 Neo4j 재적재**:
   - `neo4j_dry_run --dry-run` 오류 0.
   - `neo4j_load_draft` 미리보기: 노드 1,643·관계 2,718 예상.
   - Neo4j 백업 → `--apply --confirm APPROVED_DP_HANA_CARD`.
   - `neo4j_validate`: 차이 0, `item_data_mismatch` 0, `column_coverage` [], 고아 문서 1건만.
   - `neo4j_search_projection_sync` 미리보기 차단 0.
9. **GraphRAG 재검증**:
   - stub LLM 질문 세트(fix_plan 10절 T21~T22) 후, 승인 시 실제 LLM 3~5회로 원 질문("휴대전화 요금과 정기 구독을 자동납부하는 고객에게 더 심플 하나카드와 카드의정석2 DAILY의 적용 가능 할인과 통합 한도를 비교해 줘.")과 22 단일 질문을 돌린다.
   - 확인 사항: 예외 없음, "30만원 이상 80만원 미만 월 10,000원 / 80만원 이상 월 15,000원"이 원문과 일치, 오배정 문장은 경고와 함께 제거.
   - Notion QA(CARD10-021 등)를 재검증한다. ONE PICK 이슈는 5절 결정 후 별도로 진행한다.

---

## 9. 지켜야 할 원칙 (사용자 지시)

- DB(PostgreSQL·Neo4j) 쓰기·재적재·배포는 항상 사전 승인을 받는다.
- 다른 AI·팀원 문서와 Codex 소유 파일은 덮어쓰지 않는다. 새 문서는 경로 확인 후 작성한다.
- `value_num`에 한도를 넣지 않는다. NULL을 0으로 바꾸지 않는다. 원문에 없는 상한·우선순위·합계를 만들지 않는다.
- `dp_card_bnft` 라벨 제거나 그래프 재설계는 하지 않는다.
