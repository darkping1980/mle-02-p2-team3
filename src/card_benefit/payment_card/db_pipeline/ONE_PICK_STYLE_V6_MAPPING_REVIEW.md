# ONE PICK STYLE 1페이지 추출 결과와 V6 매핑 검토

## 1. 범위와 근거

개발 Supabase `db_pipeline`을 **읽기 전용**으로 조회했다. 대상은 `card_id=1`, `card_doc_id=20261031_000001`, `card_ai_run_id=20261031_000001`이다. `card_ai_run`, `card_ai_call`, `card_extr_stg`, `card_source_evidence`, `card_doc_page`, `card_doc_chunk`, 코드 사전·함수·게이트를 확인했다. 파일 기준은 [V6 DDL](../../sql/db_pipeline_schemaV6_draft.sql), [DBML](../../sql/db_pipeline_schemaV6_draft.dbml), [추출 스키마](extraction_schema.py), [정규화 서비스](extraction_service.py), [Repository SQL](extraction_repository.sql)과 [프로젝트 현황](PROJECT_STATUS.md)이다.

원문: `data/raw/hana_all/debit/체크_ONEPICKSTYLE하나체크카드_상품설명서(공식PDF,URL추정확인)_15650_20260429.pdf`(프로젝트 `src/card_benefit/` 기준), 1쪽 표와 안내, 2쪽 부가서비스 유지 안내. 1쪽의 저장 텍스트와 렌더링 이미지를 함께 대조했다. 공식 서버 문서지만 상품 페이지의 직접 링크 및 최신판은 미확인이다.

실행 `PARTIAL`, `gpt-6.1-terra`, 1쪽 호출 1건 `SUCCEEDED`. `card_extr_stg`: 혜택 4건, 카드 조건 4건, 모두 `PENDING_REVIEW`; 근거 30건 모두 `PENDING`, 30건 위치 존재. 페이지·청크는 1쪽 `20261031_000010`, 2쪽 `20261031_000011`, 두 청크 모두 `RAW`/`PAGE_V1`. 2쪽 LLM 추출은 수행하지 않았다. `card_method_catalog` 조회 결과 0건이다. 현재 `v_card_integrity_issue`는 0행이지만 확정 후보에 대한 시험 적재를 하지 않았으므로 적재 가능성을 입증하지 않는다.

## 2. 원문·추출·정규화 검토

아래 위치는 PDF **1쪽**. 증거 ID는 `card_source_evidence`; 위치는 PAGE_V1 텍스트의 1부터 시작하는 문자 위치다. 값과 표 행 연결은 서로 다른 검증이다.

| 혜택 | PDF 원문 및 시각적 연결 | LLM 원본과 정규화 후보 | 검증 판단 |
|---|---|---|---|
| ONE PICK | 편의점·카페 행: `일 1회 / 월 30회`, `월 5천원`; 공통 계산 셀 `3천원 이상 시 100원 / 1만원 이상 시 500원`; 상단 `지난달 실적 조건 없는 서비스` | 혜택 1번. 일 1회·월 30회·월 5,000원, 두 금액과 가맹점이 일치. `no_condition_stated=false`, `bnft_cond_expr=null` | **값·행 연결 일치**. 일별 키 `one_pick_day`의 직접 근거 누락으로 `NO_EVIDENCE`; 실적 없음의 구조화 의미 미확정 |
| STYLE | 쇼핑·서점/문구·패션 행: `일 1회 / 월 10회`, `월 5천원`; 동일 계산 셀·실적 없음 | 혜택 2번. 일 1회·월 10회·월 5,000원과 두 금액 일치. `no_condition_stated=false`, `bnft_cond_expr=null` | **값·행 연결 일치**. `style_day` 직접 근거 누락으로 `NO_EVIDENCE` |
| ONE MORE 대중교통 | 버스·지하철 `5% 캐시백`, `월 1천원`, 지난달 10만원; 최초 사용 등록일부터 다음 달 말일까지 실적 10만원 미만이어도 제공 | 혜택 3번. 수치·대상은 일치. `transit_spend`, `transit_grace`, `transit_exclusions` 포함 | 값·행 연결 일치. `VALUE_NOT_IN_QUOTE`: `cond_raw_txt`에 `지난달 실적`을 앞에 붙였지만 인용 구절은 그 결합 문자열이 아님. 현재 정규화의 실적 AND 유예는 원문 예외와 다름 |
| ONE MORE 놀이공원 | 에버랜드·롯데월드 `50% 현장할인(1인 1매)`, `월 1회 / 연 2회`, 전월 20만원, `최초 발급 월에는 서비스 미제공` | 혜택 4번. 금액·횟수·대상·발급월 제외 추출. `amusement_person`은 숫자 1, 기간 `UNKNOWN` | 값·행 연결 일치. `amusement_month`, `amusement_person` 직접 근거 부족 및 기간 미확정으로 `NO_EVIDENCE`; 1인 1매를 월·연 횟수로 바꾸면 안 됨 |

### 근거 연결의 구체적 문제

1. ONE PICK의 일·월 한도는 같은 원문 `일 1회 / 월 30회`를 공유하지만 원본 evidence의 `support_key`는 `one_pick_month_count`만 가리킨다. STYLE도 `style_month_count`만 가리킨다. **값이 원문에 없다는 뜻이 아니라 일별 키와 인용의 연결이 누락**됐다. 원문 1쪽의 근거는 각각 evidence `20261031_000006` 위치 2257–2268, `20261031_000012` 위치 1609–1620이다.
2. `no_condition_stated=false`는 실적 조건이 있다는 뜻으로 단정할 수 없다. 실적 없음은 조건의 한 유형에 관한 명시이며, 가맹점·결제·공통 제외 조건이 없는 것은 아니다. 이 필드는 V6 `card_bnft`의 독립 컬럼으로 옮겨지지 않는다. 근거와 검증 상태를 보존하고 필드 정의·적재 규약을 확정해야 한다.
3. 정규화된 두 정액 규칙은 `TXN_AMT >= 3000`과 `>=10000`으로 겹치며 `rule_select_cd=null`이다. LLM도 1만원 이상에서 두 금액의 중복·우선 적용을 `unresolved`로 남겼다. 원문은 두 금액을 제시하지만 경계·선택 정책을 명시적으로 설명하지 않으므로 `MAX_BENEFIT_VALUE`, 배타 범위, 합산을 임의로 확정하지 않는다.
4. 놀이공원의 `월 1회 / 연 2회` 인용 evidence `20261031_000023`은 연간 한도 키에만 연결됐다. `1인 1매`는 할인 규칙 인용 evidence `20261031_000022`에 있으나 `amusement_person`에 연결되지 않았다.
5. 두 `월 5천원` 근거 evidence `20261031_000007`, `20261031_000013`은 동일 텍스트 위치 1622–1626을 가리킨다. 텍스트에서 첫 일치 항목을 찾은 결과다. 이미지에는 혜택별 별도 셀이 보이므로 **같은 위치를 찾았다는 사실이 공유 한도의 근거는 아니다**. 원문 표의 반복 셀과 혜택 연결은 이미지 검토를 보존한다.
6. 1쪽 공통 조건 4건: 서비스 제외, 공식 채널 및 매장 조건, 전월 실적 제외, 가맹점 분류. `OK`는 문자열·계약 검사 결과일 뿐 의미·범위 승인이 아니다. 상품권 구매의 실적 제외와 서비스 제외를 다른 역할로 보존한다. 결제 취소 반영, 매출일 기준 5영업일 이내 캐시백, 무승인 교통 거래 접수월 반영 등 안내는 4건의 카드 조건에 독립 항목으로 정규화됐다고 확인되지 않았다. 원본 응답·문서와 대조해 범위를 결정한다.

## 3. V6 매핑 명세 및 표현 한계

아래는 **논리적 후보**이며 실제 INSERT나 승인값이 아니다. `[원문]`은 PDF 1쪽, `[DB]`는 위 추출·정규화 조회다. JSON의 키·ID는 예시 또는 기존 추출 후보 키이며 확정 ID가 아니다.

| 추출 정보 | V6 대상 | 컬럼·JSONB 키 및 변환 규칙 | 근거 / 상태 / 문제점 |
|---|---|---|---|
| 상품·정책판 | `card_policy_version` | 상품 PK `card_id=1` 상속, `policy_ver_id` 발급, `policy_ver_no`, `source_doc_list`에 문서 ID·역할 | [DB] 상품 존재. **`valid_from NOT NULL`**: 카드 출시일·PDF 심의일은 정책 적용 시작일의 증거가 아니므로 임의값 불가. 확인 전 시범 정책 행도 정확한 값으로 만들 수 없음 |
| 4개 혜택 정체성 | `card_bnft` | 상품·정책 PK 상속, 혜택별 `bnft_cd`, `bnft_nm`, `bnft_type_cd`, `bnft_origin_cd=LOCAL`, `bnft_scope_cd`, `verification_status_cd` | [원문·DB] 4개 식별 가능. 고유 키는 발급·매핑 필요. 승인 전 상태로 유지하고 원본 항목과 연결 |
| 대상 가맹점 | `card_bnft.rule_list[].target_list[]` | `target_type_cd`, `target_key`, `target_nm`; 규칙마다 올바른 대상 연결 | [원문] ONE PICK 6곳, STYLE 9곳, 교통 2개 유형, 놀이공원 2곳. 문자열 기반 키의 동일성·중복 확인 |
| 3천/1만원, 100/500원 | `card_bnft.rule_list[]` | 각각 `FIXED_PER_TXN`, `value_num=100/500`, `value_unit_cd=KRW`, `payout_unit_cd=KRW`; `cond_expr`에 건당 하한 | [원문·DB] 값 존재. 후보 하한이 겹쳐 선택 의미 미해결. `rule_select_cd` 임의 확정 금지 |
| 실적 없음 | `card_bnft.bnft_cond_expr` 및 근거 | `null`은 조건식 미입력과 실적 없음의 확인을 구별하지 못함. 확인된 범위를 원문 근거와 검토 결과로 보존 | [원문] 실적만 없음. 구조화 신호가 충분한지 판단 전 확정 금지 |
| 대중교통 5%·놀이공원 50% | `card_bnft.rule_list[]` | `PERCENT_OF_TXN`, `value_num=5/50`, `value_unit_cd=PERCENT`, 적절한 `payout_unit_cd`; `bnft_type_cd`는 각각 CASHBACK/DISCOUNT | [원문] 50%는 현장할인. 대상·거래 정보는 계산 실행 때 별도로 필요 |
| 전월 실적·신규 예외 | `card_bnft.bnft_cond_expr` | DNF: branch 간 OR, 각 branch 내 AND. 교통은 `(전월 10만원 이상 OR 최초 등록 유예)`와 적용 제외 조건을 결합해야 함 | [원문] 유예는 10만원 조건의 예외. 현재 `build_cond_expr`의 단일 branch AND는 의미 오류. OR에서 같은 atom_key 재사용도 함수가 금지하므로 각 branch 키 설계 필요. 날짜 계산용 술어 코드·파라미터·실행 규약은 **미확정** |
| 놀이공원 실적·발급월 | `card_bnft.bnft_cond_expr` | 전월 20만원과 발급월 미제공을 각각 검증 가능한 조건으로 표현 | [원문] 발급월 부정은 추출됐으나 시간 술어의 코드·기준·계산 로직은 미정. `GRACE` 텍스트만으로 기계 계산 불가 |
| 제외·공통 채널 | `card_policy_version.policy_cond_expr` 또는 각 `card_bnft.bnft_cond_expr` | 적용 범위 검증 후 AND 결합. 실적 산정 제외는 전월 실적 계산의 입력 범위, 혜택 제외는 거래 적용 대상 | [원문·DB] 범위별 후보가 있지만 `build_cond_expr`는 나열된 조건을 모두 AND로 처리. 제외 조건의 `negate_yn`과 술어 뜻의 이중 부정·OR/예외는 별도 의미 검증 필수 |
| 일·월·연 횟수와 월 금액 | `card_limit_pool` 및 `card_bnft.rule_list[].pool_refs[]` | 혜택별 독립 풀, `period_cd` DAY/MONTH/YEAR, `cap_unit_cd` COUNT/KRW, `tier_list[].limit_num`; 생성된 **실제 `pool_id`**를 각 rule의 `pool_refs`로 치환 | [원문] ONE PICK과 STYLE의 5천원은 각각 별도. 교통 월 1천원, 놀이공원 월 1회·연 2회. 동일 액수만으로 공유하지 않음. [DB] 현재 후보 `pool_id`는 `one_pick_day` 등 임시 키이며 실제 부모 풀 없음 |
| 1인 1매 | 보류: `card_limit_pool` 또는 조건·계산 방법 확장 검토 | V6 풀은 `period_cd`, `aggregation_key_cd` 필수. 원문은 사람당 매수 1매이고 결제건·일·월·연 기간을 명시하지 않음 | [원문] 값은 보존 가능. 현 Seed의 LIMIT_PERIOD는 TXN/DAY/MONTH/YEAR, LIMIT_AGG는 CARD_MEMBER뿐이라 **의미를 그대로 검증 가능한 코드로 확정 불가**. 임의 기간이나 회원 카드 합산 부여 금지. 원문·staging에 보류하고 코드/술어 계약 추가 필요성 검토 |
| 계산 방법 계약 | `card_method_catalog` | CALC/PREDICATE 코드·버전별 `param_schema`, `handler_key`, 상태 | [DB] 현재 0건. 코드 Seed 존재만으로 handler·계산 검증이 구현된 것은 아님. 필요한 계약과 Python 실행 로직 검토 |
| 원문 근거 | `card_source_evidence`, `card_policy_evidence` | 승인된 evidence ID를 `ev_subject_cd=POLICY/BNFT/RULE/POOL/REL`, 필요 시 `ev_item_cd=COND/TARGET/TIER` 및 해당 키에 연결 | [DB] 30건 전부 `PENDING`. 단일 인용이 다수 키를 뒷받침할 경우 각각 근거 관계 필요. 위치 일치만으로 표 행 의미가 검증되지는 않음 |
| 혜택 간 관계 | `card_bnft.relation_list[]` | 상대 혜택의 **실제** `to_bnft_id`와 명시된 관계만 연결 | [원문] 네 혜택 사이에 별도 우선/대체 관계는 확인되지 않음. 규칙 선택 문제를 혜택 간 관계로 꾸며 넣지 않음 |

### 표현 손실과 확정 보류

- `normalize_benefit`는 `limit_list`에 `aggregation_key_cd=CARD_MEMBER`를 일괄 입력한다. 1쪽의 한도별 회원·가족카드 합산 기준이 확인되지 않았으므로 해당 후보값을 사실로 확정할 수 없다. 정책·한도의 필수 코드 때문에 정확한 근거가 확보되지 않은 풀의 확정 적재는 보류한다.
- 현재 후보는 `limit_list`를 `card_bnft`의 실제 컬럼에 바로 넣을 수 없다. 별도 `card_limit_pool` 행과 `tier_list`로 재구성하고 임시 키를 풀 ID에 매핑해야 한다. 원본 인용·검토 사유·`unresolved`는 rule JSON만으로 전달되지 않으므로 staging과 근거를 함께 유지한다.
- `cond_expr` 구조가 OR를 지원한다는 것과 유예 날짜를 기계적으로 계산할 수 있다는 것은 별개다. 현재 정규화의 유예 atom은 `predicate_method_cd`, `predicate_method_ver`, `cond_params`가 모두 NULL이다. 날짜 술어 해석기와 예외 규약 확인 전 의미 보존을 확정할 수 없다.
- 원문은 `1인 1매`를 명시하지만 이 문서 기준 V6의 기존 기간·집계 코드에 정확한 대응을 확인하지 못했다. 새 코드·술어·별도 구조 중 어떤 변경이 적절한지는 시범 매핑 검토 후 결정한다. 현 시점에서 DDL 변경을 결정하지 않는다.

## 4. SQL 계약과 정합성 검증

읽기 전용으로 [Mapper `select_contract_check`](extraction_repository.sql)를 구성하는 실제 함수를 현재 8건에 실행했다. 혜택 4건의 `fn_valid_rule_list`, `fn_valid_cond_expr`, `fn_valid_relation_list`와 카드 조건 4건의 `fn_valid_cond_expr`가 모두 `true`였다. **이 결과는 구조 계약 통과만 의미한다.** 교통 실적·유예가 잘못 AND로 묶인 후보도 통과했고, 임시 `pool_id`의 실제 부모 존재 여부는 이 함수만으로 판정하지 않는다. 실제 문서 의미·표 셀 연결·정책 적용 시작일도 검증하지 못한다.

`fn_valid_cond_expr`는 branch/atom 형식·키 중복·금액 경계·제외 항목과 술어 코드/버전 쌍을 검사한다. `fn_valid_rule_list`는 규칙·대상·수치 및 풀 참조 JSON의 형태를 검사한다. `fn_valid_tier_list`는 풀 구간 수치·키·조건 상태 형태를 검사한다. `v_card_integrity_issue`는 승인 게이트로 부모·풀 참조·공통코드·근거 대상을 포함한 논리 정합성을 점검한다. **빈 게이트는 미적재 데이터의 정확성 판정이 아니다.** 공통 코드 존재와 `card_method_catalog` 계약/handler 존재도 따로 확인한다.

추가로 아래와 같은 **SELECT만** 실행해 후보를 재검토할 수 있다. staging은 실제 `card_bnft` 컬럼이 아니므로 JSON 함수 결과만 검토하고 승인 판단을 대신하지 않는다.

```sql
SELECT stg_item_seq, stg_kind_cd, stg_status, stg_sql_check_cd,
       stg_normalized_item->'checks' AS checks,
       stg_normalized_item->'bnft_cond_expr' AS benefit_conditions,
       stg_normalized_item->'rule_list' AS rules,
       stg_normalized_item->'limit_list' AS candidate_limits
FROM db_pipeline.card_extr_stg
WHERE card_ai_run_id = '20261031_000001'
ORDER BY stg_item_seq;

SELECT s.stg_item_seq, e.evidence_id, e.page_no, e.start_pos, e.end_pos,
       e.approval_status_cd, e.quote_txt
FROM db_pipeline.card_extr_stg s
JOIN db_pipeline.card_source_evidence e ON e.card_extr_stg_id = s.card_extr_stg_id
WHERE s.card_ai_run_id = '20261031_000001'
ORDER BY s.stg_item_seq, e.start_pos;

SELECT gate_cd, count(*) FROM db_pipeline.v_card_integrity_issue GROUP BY gate_cd;
```

향후 시험 시에는 `v_card_rule_pool`의 풀 고아, 원문 근거 subject/item 키, DNF 분기별 의미, 실효 기간 중첩, 단위·기간·범위, 공통 제외의 적용 위치, 규칙 선택의 겹침, 코드 카탈로그와 승인 상태를 추가 검사한다. 테스트 데이터도 승인 전 원문 위치와 함께 점검한다.

## 5. 수동 시험 적재 전 선행 조건과 순서

**현재 상태는 확정 적재 준비 미완료다.** 네 혜택의 이름·주요 수치와 기본 대상은 후보로 표현 가능하지만, 현 정규화본을 그대로 넣어 네 혜택을 정확하게 실행 가능한 정책으로 표현할 수 있다는 근거는 없다. 적용 시작일 미확인, 교통 유예의 OR, 규칙 중첩, 근거 키 누락, 한도 집계 범위 및 1인 1매가 남아 있다. `PENDING_REVIEW`·`PENDING`은 바꾸지 않았다.

1. 1쪽 이미지·근거 ID·행별 값과 공통 제외 범위를 사람이 검토하고 누락된 직접 근거 링크를 설계한다. 기존 원본 JSON은 보존한다.
2. 2쪽은 부가서비스 유지·변경, 해외 결제 등 문서 공통 안내가 있으므로 정책 적용·조건·예외와 충돌 또는 추가 정보가 있는지 사람이 원문 확인한다. 2쪽 LLM 호출이 모든 항목에 필수라고 단정하지 않는다. 문서 전체에 걸친 확정 판단은 2쪽 확인이 선행돼야 한다.
3. 교통 실적/유예의 OR, 룰 선택, 실적 제외의 계산 범위, 집계 기준, 1인 1매의 의미·코드, 정책 `valid_from`, 근거·승인 규약을 확정한다. 원문 미확인 시 보류한다.
4. 별도 승인된 개발·시험 환경에서 트랜잭션을 열고 정책판→혜택→개별 한도 풀→규칙 내 실제 풀 ID 치환→검증된 근거 연결 순으로 **수동 시험**한다. 필요한 방법 카탈로그 계약과 코드 정합성도 함께 준비한다. 순서는 논리 참조를 위한 것이며 FK 자동 검증이 아니다.
5. JSON 함수와 정합성 게이트, 고아/중복/범위 검증, 실측 원문 비교를 실행하고 결과를 확인한다. 별도 승인이 없는 시험은 `ROLLBACK`; 운영 데이터에 COMMIT하지 않는다. 시퀀스 사용은 롤백되지 않는다.

1·2쪽을 별도 실행하면 다른 실행 ID를 사용하며 현재 코드에서 자동으로 합쳐지지 않는다. 모델 호출 없이 기존 DB 페이지 2의 원문 검토는 가능하다. 유료 2쪽 호출, staging 수정, 승인 변경 및 시험 적재는 별도 승인 대상이다.

## 6. Neo4j 변환 고려

승인된 상품·정책판·혜택을 노드로, 규칙/대상/조건·풀·원문 evidence를 식별 가능한 관계 또는 노드로 내보낸다. JSON의 `rule_key`, `atom_key`, 실제 `pool_id`, `evidence_id`와 정책판을 함께 유지해 서로 다른 카드·개정판의 같은 이름과 금액을 합치지 않는다. 교통 유예의 OR 분기와 NOT, 실적 산정 제외와 혜택 제외, 한도 범위·단위·기간, `PENDING`/승인 상태와 원문 쪽·청크를 잃지 않아야 한다. 그래프 적재 규약과 실제 조회 구현은 미확정이다.

## 7. 대중교통 전월 실적·최초 등록 유예 수정안

### 7.1 원문과 확인 범위

`card_doc_id=20261031_000001`의 저장 페이지 1·2를 읽기 전용으로 확인했다. PDF `15650_20260429.pdf` 1쪽과 PAGE_V1 청크 `20261031_000010`의 근거 위치는 1부터 시작하며 끝 위치를 포함한다.

| 위치 | 원문 근거 | 해석 |
|---|---|---|
| 1쪽 2342–2371, evidence `20261031_000017` | `대중교통 / 버스, 지하철 / 월 1천원 / 5% 캐시백 / 10만원` | 표의 대중교통 행은 전월 10만원 이상 기준, 버스·지하철 5% 캐시백, 월 1천원 한도를 연결한다. 표 이미지로 행을 확인했다. |
| 1쪽 435–504, evidence `20261031_000018` | `지난달 1일부터 말일(승인 시점 기준)까지 국내외 일시불 이용금액 10만원/20만원 이상 시 ONE MORE 서비스 제공` | 표의 대중교통 행에 따라 10만원을 적용한다. 산정 시 제외 항목은 별도로 적용한다. |
| 1쪽 807–895, evidence `20261031_000019` | `ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공` | **최초 카드 사용 등록일 포함부터 등록일이 속한 달의 다음 달 말일 포함까지** 실적 미충족이어도 교통 혜택을 10만원 이상 기준으로 제공한다. 발급일이 아닌 사용 등록일이다. |
| 1쪽 385–424, evidence `20261031_000020` | `대중교통 : 시외버스, 고속버스, 철도(KTX/SRT/ITX)는 제외` | 유예가 있어도 혜택 대상 제외가 사라지는 근거는 없다. 공통 서비스 제외도 별도로 확인한다. |

페이지 2의 저장 원문 전체에서 `대중교통`, `ONE MORE`, `최초 카드 사용 등록일`, `10만원`, `지난달 실적`은 발견되지 않았다. 2쪽에는 부가서비스 유지·변경 안내와 출시일 등 일반 안내가 있지만 이 검색과 원문 검토 범위에서 교통 유예의 추가 기간은 발견하지 못했다. 이것이 문서 외부의 추가 약관 부재나 문서 최신성을 보증하지는 않는다. 모든 evidence는 현재 `PENDING`이다.

### 7.2 현재 JSON과 문제

실제 DB의 `card_extr_stg_id=20261031_000003` 원본 조건은 `transit_spend`, `transit_grace`, `transit_exclusions`이고, 문서 통합 시 `spend_exclusions`도 결합됐다. 아래는 저장된 `stg_normalized_item.bnft_cond_expr`의 **실제 키와 구조를 보여 주는 발췌**이며 설명을 위해 다른 atom 속성은 생략했다.

```json
{"expr_status_cd":"DRAFT","branches":[{"branch_no":1,"atoms":[
  {"atom_seq":1,"atom_key":"transit_spend","cond_type_cd":"SPEND_REQ","cond_basis_cd":"PREV_MONTH_SPEND","cond_min_amt":100000,"negate_yn":false},
  {"atom_seq":2,"atom_key":"transit_grace","cond_type_cd":"GRACE","negate_yn":false,"predicate_method_cd":null,"predicate_method_ver":null,"cond_params":null},
  {"atom_seq":3,"atom_key":"transit_exclusions","cond_type_cd":"BNFT_EXCL","negate_yn":true},
  {"atom_seq":4,"atom_key":"spend_exclusions","cond_type_cd":"SPEND_EXCL","negate_yn":true}
]}]}
```

V6 계약은 branch 사이 OR, 하나의 branch 안 atom 사이 AND다. `extraction_service.py`의 `build_cond_expr`가 조건 목록 전체를 하나의 branch로 만들므로 실적 충족과 유예를 함께 요구하게 된다. 그 결과 실적 미충족이지만 유예 기간인 손님과 실적 충족이지만 유예가 지난 손님을 모두 잘못 제외할 수 있다. 또한 `spend_exclusions`는 전월 실적을 **계산할 때** 빼는 항목인데 현재의 평평한 Boolean AND는 이를 현재 거래의 할인 제외로 오해할 위험이 있다. `BNFT_EXCL`의 술어 자체가 제외 대상 여부인지, 이미 제외를 적용한 결과인지 확정되지 않아 `negate_yn=true`를 기계적으로 해석해서도 안 된다.

### 7.3 원문에 근거한 논리와 수정 제안

원문의 실적 기준 충족 여부만 먼저 정의한다. `S`는 **전월 1일~말일의 승인 시점 기준 국내외 일시불 금액에서 실적 제외 항목을 제거한 합계**가 100,000원 이상인지다. `G`는 **기준 이용일이 최초 카드 사용 등록일 이상이고 그 등록일이 속한 다음 달 말일 이하**인지다. 정확한 기준 이용 시점·시간대와 무승인 거래의 운영 적용 방식은 별도 확인이 필요하다.

```text
실적 자격 = S OR G
교통 혜택 후보 = 실적 자격 AND 해당 교통 이용 대상 AND 공통·교통 서비스 제외에 해당하지 않음
               AND 그 밖의 확인된 적용 조건·한도
```

유예는 실적 자격의 대안이지 다른 서비스 제외를 면제하는 분기가 아니다. 실적 산정 제외는 `S`의 합계 계산 규칙이며 현재 거래 제외 조건과 구분한다. 5% 및 월 1천원은 별도의 계산 규칙·한도이며 위 Boolean 결과가 곧 최종 캐시백 금액은 아니다.

V6가 서로 다른 레이어의 조건식을 AND로 합치는 규약을 이용하면 `card_bnft.bnft_cond_expr`에 **실적 자격의 OR만**, 별도로 확인된 공통·거래 적용 조건은 적절한 policy 또는 rule 조건식에 둘 수 있다. 다만 실제 배치 위치는 다른 혜택에 대한 공통 조건 범위와 제외 술어 의미를 확인한 뒤 정한다. 아래는 저장된 두 atom을 복사해 분기만 바꾼 **DRAFT 형식 예시**다. 분리된 나머지 조건은 삭제하거나 무시하라는 뜻이 아니다.

```json
{
  "expr_status_cd": "DRAFT",
  "branches": [
    {"branch_no": 1, "atoms": [{
      "atom_seq": 1, "atom_key": "transit_spend", "negate_yn": false,
      "cond_type_cd": "SPEND_REQ", "cond_basis_cd": "PREV_MONTH_SPEND",
      "cond_min_amt": 100000, "cond_max_amt_excl": null,
      "predicate_method_cd": null, "predicate_method_ver": null, "cond_params": null,
      "card_excl_item_id": null, "excl_raw_txt": null,
      "cond_raw_txt": "지난달 실적\n대중교통\n버스, 지하철\n월 1천원\n5%\n캐시백\n10만원",
      "link_role_cd": null, "cond_status_cd": "DRAFT"
    }]},
    {"branch_no": 2, "atoms": [{
      "atom_seq": 1, "atom_key": "transit_grace", "negate_yn": false,
      "cond_type_cd": "GRACE", "cond_basis_cd": "PREV_MONTH_SPEND",
      "cond_min_amt": null, "cond_max_amt_excl": null,
      "predicate_method_cd": null, "predicate_method_ver": null, "cond_params": null,
      "card_excl_item_id": null, "excl_raw_txt": null,
      "cond_raw_txt": "- ONE MORE 대중교통 서비스는 최초 카드 사용 등록일로부터 다음 달 말일까지 지난달 카드 실적\n 10만원 미만 이어도 10만원 이상 기준으로 서비스 제공",
      "link_role_cd": null, "cond_status_cd": "DRAFT"
    }]}
  ]
}
```

위 예시는 **실제 DB의 `fn_valid_cond_expr`에 SELECT로 전달해 `true`를 확인**했다. 이것은 JSON 구조와 키의 유효성에 한정된다. `transit_spend.cond_raw_txt`는 저장된 추출값 그대로이므로 앞의 `지난달 실적`이 해당 인용에 없어 기존 `VALUE_NOT_IN_QUOTE` 문제가 남는다. 인용 범위를 올바르게 연결하는 것은 별도 검토다.

각 branch의 `atom_key`는 전체 식에서 유일해야 한다. 공통 조건을 두 branch에 복제한다면 branch별로 다른 atom 키와 각각의 근거 연결이 필요하다. 위 예시는 기존 두 키를 서로 다른 branch에 한 번씩 사용한다. 현재 PREDICATE_METHOD 공통코드는 `EVERY_MONTH_MIN_SPEND`, `MONTH_IN`이며 `card_method_catalog`의 PREDICATE 행은 0건이다. `GRACE`의 날짜 계산 코드·버전·필수 파라미터와 handler는 확인되지 않았다. **OR 구조는 DDL 변경 없이 표현되지만 유예 기간을 자동으로 정확히 평가하는 구현까지 현재 가능하다고 확인된 것은 아니다.** 임의 코드나 미정 JSON 키를 확정하지 않는다.

### 7.4 원문 기준 시나리오

다음은 `S OR G`의 실적 자격만 평가한다. 날짜가 유효하고 버스·지하철 대상, 제외·한도 등 다른 조건이 모두 충족된다는 가정이다. 해당 가정이 충족되지 않으면 표의 결과만으로 실제 혜택 제공을 확정할 수 없다.

| 전월 실적 `S` | 등록 유예 `G` | 실적 자격 기대 결과 |
|---|---|---|
| 충족 | 아님 | 충족 — 유예 종료가 실적 충족자를 배제하지 않음 |
| 미충족 | 해당 | 충족 — 유예 예외 적용 |
| 미충족 | 아님 | 미충족 |
| 충족 | 해당 | 충족 |
| 미충족 | 다음 달 말일이 지난 직후 | 미충족 — 유예 종료 후에는 통상 실적 기준 적용 |

경계 예: 최초 사용 등록일이 3월 16일이면 날짜 기준 유예는 3월 16일부터 **4월 30일까지 포함**, 5월 1일부터 제외한다. 3월 15일은 유예에 포함되지 않는다. 최초 등록일 미상 또는 실적 미상은 거짓으로 임의 처리하지 말고 미확정으로 둔다.

### 7.5 A7-2 이전 검증 및 남은 장애

1. `fn_valid_cond_expr`의 true는 AND/OR 의미, `GRACE` 날짜 계산, 조건별 evidence 승인까지 검증하지 않는다. 위 후보의 실제 사용자 입력·날짜·제외 처리에 대한 **실행 검증은 아직 하지 않았다**.
2. `v_card_cond_atom`과 `card_policy_evidence`에서 두 분기의 `atom_key`, 증거 ID 및 `PENDING`/승인 상태를 연결하고, 정책·혜택·규칙 레이어의 AND가 유예와 제외를 올바른 범위에 적용하는지 검증한다. `fn_cond_spend_bound`는 OR식에서 NULL이므로 단일 실적 컬럼만 보고 조건을 판정하지 않는다.
3. `v_card_integrity_issue`와 코드 사전·메서드 카탈로그 검사는 실제 승인·적재 시험 데이터에 대해 수행해야 한다. 현재 게이트 0행이나 후보 JSON 구조 통과는 시험 적재의 성공을 증명하지 않는다.
4. 실적 제외를 합계 계산에서 처리하고, 교통·공통 제외를 거래 적용에서 처리하는 술어 의미와 NOT 방향을 확정한다. 유예 시작·종료 경계와 등록일 누락, 월말·연말, 전월 미충족 및 실적 충족 사례를 SQL과 계산기에서 검증한다.
5. 실적 원문 인용 불일치, GRACE 코드·버전·파라미터·handler, 정책 `valid_from`, 근거 승인 및 검토 절차는 미해결이다. V6 조건식의 OR 구조는 제안 가능하지만 **확정 데이터 및 자동 판정으로 승인할 단계는 아니다**. DB 추출 데이터와 업무 테이블은 이번 검토에서 수정하지 않았다.

## 8. A7-3 실제 등록 데이터 의미 정합성 재검토 (2026-11-01)

### 8.1 확인 범위와 현재 상태

이 절은 초기화 전 ID를 사용하는 위 1~7절의 이력에 대한 **현재 데이터 보완**이다. `card_id=2`, `card_doc_id=20261101_000002`, 재생 실행 `card_ai_run_id=20261101_000002`, 정책 `20261101_000001`을 읽기 전용으로 조회했다. 실행의 원본은 최초 유료 응답의 재생이며 새로운 모델 호출이 아니다. PDF `체크_ONEPICKSTYLE하나체크카드_상품설명서(공식PDF,URL추정확인)_15650_20260429.pdf`의 SHA-256은 DB 문서 해시와 일치했고, PDF에서 추출한 1·2쪽 텍스트가 각각 DB `card_doc_page`와 일치했다. 두 페이지 이미지를 직접 검토했다. DB 문서 메모상 상품 페이지 직접 연결과 문서 최신성은 미확인이다.

DB에서 정책은 `DRAFT`, 혜택 4건은 `PENDING_REVIEW`, 규칙 6건은 `DRAFT`이다. 정책-문서 관계는 `PENDING`이고 정합성 게이트는 `evidence_not_approved` 30건을 반환했다. staging 8건도 모두 `PENDING_REVIEW`다. SQL 형식 검증이나 텍스트 일치는 원문 의미의 승인에 해당하지 않는다. 아래 변경은 **제안**이며 DB 수정·승인은 수행하지 않았다.

### 8.2 원문과 저장값 대조 및 보정 방향

| 항목 | PDF에서 확인된 사실 | 실제 staging / V6 저장과 문제 | 수정 제안·필요 여부 및 Neo4j 영향 |
|---|---|---|---|
| 대중교통 실적·유예 | 1쪽 서비스 제공 안내: 전월 실적 10만원 이상. 최초 카드 **사용 등록일**부터 다음 달 말일까지는 10만원 미만이어도 제공. 시외·고속버스와 KTX/SRT/ITX 제외 | staging 3번은 `transit_spend`, `transit_grace`, `transit_exclusions`, `spend_exclusions`를 한 branch의 AND로 저장. V6 혜택 조건은 `[transit_spend AND spend_exclusions] OR [transit_grace]`, 교통 제외는 규칙 조건에 별도 저장 | 재등록 전에 staging의 AND가 그대로 확정 경로에 들어가지 않도록 차단·사람 검토가 필요하다. 논리상 실적 자격은 **산정 제외를 반영한 전월 실적 ≥10만원 OR 유예**이며, 교통 대상·서비스 제외는 양쪽 분기에 공통 적용한다. V6의 `spend_exclusions`를 단순 현재 거래의 불리언 제외로 해석하면 안 된다. NOT 방향과 공통 조건 범위는 미확정이다. 그래프에는 OR 분기와 실적 산정 제외의 범위를 보존해야 한다. |
| 원본과 정정 이력 | 원문은 위와 같고 추출 응답의 정정은 원문 자체의 변경이 아니다 | `card_ai_call` 원본 응답과 staging `stg_raw_item`을 보존하고 `stg_normalized_item`은 기존 mapper에서 갱신할 수 있다. `stg_review_note`, 승인 일시·사용자 컬럼은 있지만 자동 불변 이력이라는 근거는 없다 | 원본·기존 후보를 덮어쓰지 않고 새 검토 결과에 원본 실행·항목·근거, 정정 전후, 사유, 검토자·시각을 연결하는 절차를 설계한다. 기존 필드/별도 실행만으로 누락 없이 이력을 남길 수 있는지는 구현 확인이 필요하다. 실제 정정·재등록은 별도 승인 후 수행한다. 그래프 출처에 원본과 검토 결과를 구별한다. |
| 100원·500원 | 1쪽 표에 결제 건당 3천원 이상 100원 / 1만원 이상 500원. 선택·합산 우선순위의 명시 문구는 찾지 못함 | 두 혜택의 각 rule은 최소값 3,000 / 10,000이고 상한 NULL, `rule_select_cd` 및 우선순위 NULL. 1만원 이상에서 두 조건이 겹침 | 중복·최대값 우선·배타적 구간 어느 쪽도 확정하지 않는다. 별도 상품 약관 또는 카드사 확인 후 경계·선택 규약과 근거를 보완해야 한다. 그 전에는 그래프가 두 금액을 합산하거나 500원 확정으로 계산하지 않도록 미해결 관계를 유지한다. |
| 개별·공유 한도 | 1쪽 표에서 ONE PICK은 일 1회·월 30회·월 5천원, STYLE은 일 1회·월 10회·월 5천원. 교통은 월 1천원, 놀이공원은 월 1회·연 2회 | 각 혜택에 별도 풀 3·3·1·2건으로 연결돼 표와 부합한다. 두 규칙이 각 혜택의 같은 풀을 참조하는 것은 해당 혜택의 한도를 공유한다는 뜻이며, 두 혜택 간 5천원 통합 풀을 뜻하지 않는다. 9개 풀 모두 `aggregation_key_cd=CARD_MEMBER`는 시험 가정 | 별도 풀 연결은 유지하되 합산 대상·가족카드 범위를 확인할 때까지 `CARD_MEMBER`를 사실로 표시하지 않는다. 1일 횟수와 놀이공원 일부의 직접 근거 누락, 반복된 5천원의 표 행 연결을 사람 검토·근거 보완해야 한다. 그래프에서 동일 금액의 풀을 병합하지 않는다. |
| 1인 1매 | 1쪽 놀이공원 50% **현장할인** 표에 `(1인 1매)` | 혜택 조건의 `amusement_per_person`은 `ETC` 및 `cond_raw_txt`로 보존되고 정형 숫자·사람 단위는 확정되지 않았다. 월·연 횟수는 별도 풀 | 1인 1매 원문을 잃지 않되 원문에 없는 TXN/DAY 등 기간과 `CARD_MEMBER` 집계를 부여하지 않는다. 표현 계약·근거 연결을 검토한 후 필요한 데이터 수정 여부를 결정한다. 그래프에는 원문이 붙은 미정형 조건으로 보존하고 월·연 풀과 혼동하지 않는다. |
| 정책 시작일 | 2쪽은 신규 출시일 2026-03-30과 부가서비스 3년 이상 유지 및 명시된 변경 예외를 기술한다. 준법심의일은 2026-04-29 | `valid_from=2026-03-30`은 NOT NULL 시험 가정. 출시일·심의일이 이 정책판의 실제 적용 시작일이라는 별도 근거는 확인되지 않았다 | 문서판 적용일의 신뢰 가능한 근거 확보 전 승인·서비스 사용을 보류한다. 현재 DRAFT 값 정정에는 DB 변경 승인이 필요하다. 그래프에서 이 날짜를 승인된 적용일로 내보내지 않는다. |
| 2쪽의 영향 | 부가서비스 유지·변경 사유와 고지, 해외 결제 수수료·환율, 결제 안내를 기술한다 | 이 문서 2쪽에서 1쪽 네 혜택의 별도 실적 기준이나 교통 유예 기간을 추가하는 문구는 발견하지 못했다. 2쪽 LLM 추출은 미실행 | 부가서비스 변경 가능성과 고지 규정은 문서 공통 정책 맥락으로 유지하고 3년간 예외 없는 보장으로 답하지 않는다. 해외 수수료를 캐시백 조건으로 혼동하지 않는다. 다른 문서의 추가 조건 부재까지 증명하지는 않는다. |

1쪽에는 공통 서비스 제외와 별도로 전월 **실적 산정 제외**가 있고, 후불교통 등 무승인 거래의 이용금액 반영 시점 안내도 있다. 놀이공원은 최초 발급 월 미제공이며 교통 유예를 놀이공원에 전파하면 안 된다. PDF 표에서 ONE PICK·STYLE은 지난달 실적 조건이 없는 서비스이나 다른 대상·제외·한도까지 없다는 뜻은 아니다.

### 8.3 재등록 방지와 상태 필터 제안

`extraction_service.py`의 `build_cond_expr`는 조건 목록을 단일 AND branch로 만든다. 따라서 현재 후보를 자동 재생성하면 교통 AND 오류가 재현될 수 있다. 우선 이 항목은 자동 확정 적재를 차단하고, 원본 응답은 그대로 둔 채 사람 검토 결과의 OR와 실적 산정 제외·서비스 제외 범위를 명시적으로 대조해야 한다. 신규 테스트나 코드 변경은 이번 검토에서 수행하지 않았다. `VALUE_NOT_IN_QUOTE`, 두 일 한도와 놀이공원 일부의 `NO_EVIDENCE`, 표 셀 및 근거 연결도 별도 검토 대상이다. 유예 기간은 텍스트로 표현돼 있으나 기계 판정 술어와 파라미터는 확정되지 않았으며 MVP에 개인별 실행 handler를 요구하지 않는다.

실제 `v_card_bnft_rule_effective`의 LOCAL 경로는 정책·혜택·규칙 상태를 걸러내지 않는다. 향후 Neo4j 내보내기와 답변 검색은 최소한 (1) 상품에 연결된 정책판의 `policy_status_cd=APPROVED`, 기준일에 `valid_from <= 기준일` 및 `valid_to_excl IS NULL OR 기준일 < valid_to_excl`, (2) 혜택과 규칙의 **실제 코드 사전에 정의된 승인·검증 완료 상태**, (3) 필요한 문서 적용 관계와 원문 evidence 승인 및 무결성 검사, (4) 미해결 조건·근거에 대한 사람 검토를 모두 확인해야 한다. 공통 혜택은 공통 정책판과 적용 관계의 승인·기간도 별도 확인한다. 구체적인 허용 코드와 근거 범위는 검토 규약과 실제 코드값 확정 후 구현한다. NULL·미확인은 자동 승인이나 무조건 혜택으로 취급하지 않는다. 이미 내보낸 그래프가 있다면 정정 전·폐기된 노드와 관계의 동기화 및 제거 정책도 필요하다. 현재 그래프 적재 여부는 확인하지 않았다.

**결론:** 지금은 4개 혜택 모두 시험용 DRAFT로만 보존한다. 자동 재등록 방지와 의미·근거 검토가 선행돼야 하며, 데이터 수정·상태 변경은 변경 대상과 영향 확인 후 별도 승인받는다. 현재 DB, DDL, 코드, LLM 원본은 변경하지 않았다.

### 8.4 A7-4 후속

사용자의 후속 등록 승인에 따라 2쪽의 부가서비스 유지·변경·고지 문구를 기존 정책에 PENDING 원문 근거로 연결했다. 새 evidence `20261101_000061`, 연결 `20261101_000041`; 승인과 LLM 원본은 변경하지 않았다. 현재 evidence 31건, 정책 근거 연결 41건이며 게이트의 미승인 근거도 31건이다. 위 A7-3의 의미 검토와 미확정 사항은 그대로다. 조회와 그래프 전환 초안은 [구조 비교](POSTGRESQL_TO_NEO4J_STRUCTURE_COMPARISON.md)를 참조한다.

2026-11-01 최종 재조회에서도 교통 V6 OR는 유지되고 staging AND 재생성 위험은 남았다. 형식 오류는 발견되지 않았고 근거 위치 31/31이 일치했으나 사람 검토 완료를 뜻하지 않는다. PDF 전체는 원문으로 보존됐으며 해외 이용 수수료와 2쪽 부가서비스 고지의 세부 구조화는 미완료다. 별도 의미 확인 없이 staging 후보나 시험 가정값을 확정하지 않는다.
