# A7-2 — ONE PICK STYLE V6 시험 적재 사전 준비

## 1. 작업 목적과 범위

이 문서는 발급 전 카드 혜택 검색·비교 GraphRAG를 위한 **시험 적재 준비안**이다. 실제 DB INSERT, UPDATE, DELETE, DDL, 시퀀스 호출 및 시험 SQL 실행은 하지 않았다. 아래 SQL은 **별도 승인 전 실행 금지**이며 `<...>`는 미확정 자리표시자라 의도적으로 실행되지 않는다. 실제 카드 정책을 완성·승인했다는 뜻이 아니다.

기준 자료: [프로젝트 범위](../PROJECT_SCOPE.md), [구현 현황](PROJECT_STATUS.md), [ONE PICK STYLE 매핑·대중교통 OR 검토](ONE_PICK_STYLE_V6_MAPPING_REVIEW.md), [V6 MVP 검토](V6_MVP_SCOPE_REVIEW.md), [V6 DDL](../../sql/db_pipeline_schemaV6_draft.sql), [DBML](../../sql/db_pipeline_schemaV6_draft.dbml), [공통코드 Seed](../../sql/db_pipeline_common_code_seedV6.sql), [추출 서비스](extraction_service.py) 및 [조회 Mapper](extraction_repository.sql). 원문 근거와 혜택·조건의 의미를 보존한다. 개인별 거래 계산 handler는 MVP 범위 밖이다.

## 2. 실제 DB·DDL 확인 결과

개발 Supabase `db_pipeline`을 `SET TRANSACTION READ ONLY`로 조회했다. 13개 대상 테이블의 **컬럼 이름과 순서**는 로컬 V6 DDL과 일치했으며, `card_policy_version`, `card_bnft`, `card_limit_pool`, `card_method_catalog`, `card_policy_evidence`의 실제 PK·UNIQUE·CHECK 정의를 조회해 로컬 정의와 대조했다. **모든 타입·기본값·함수·뷰의 전수 동등성은 확인하지 않았다.** 나머지 분석은 로컬 DDL과 별도 명시한 실제 조회를 구분한다.

| 실제 DB 조회 | 결과 |
|---|---|
| 상품·문서 | `card_product` 1건, `card_product_doc` 1건. 상품 1 ↔ 문서 `20261031_000001`, 관계 `PENDING` |
| 확정 정책·혜택·한도 | `card_policy_version`, `card_bnft`, `card_limit_pool` 각각 0건 |
| 방법·제외 사전 | `card_method_catalog`, `card_excl_item` 각각 0건 |
| 공통 혜택 | `card_common_bnft`, `card_common_policy_version`, `card_bnft_common`, `card_common_rule_evidence` 각각 0건 |
| 후보·근거 | 1쪽 `card_extr_stg` 혜택 4건·카드 조건 4건 `PENDING_REVIEW`; `card_source_evidence` 30건 `PENDING`; `card_policy_evidence` 0건 |
| 정합성 게이트 | `v_card_integrity_issue` 0행. **현재 확정 정책이 비어 있으므로 시험 후보의 정확성을 입증하지 않음** |
| 공통코드 | `FIXED_PER_TXN`, `PERCENT_OF_TXN`, `PREDICATE_STATE`의 `CONDITIONAL`/`PENDING_REVIEW`/`VERIFIED_UNCONDITIONAL`, 기간 DAY/MONTH/TXN/YEAR, 단위 COUNT/KRW, `LIMIT_AGG=CARD_MEMBER`, `METHOD_STATUS=UNEXECUTABLE` 존재 |

2쪽은 페이지 텍스트가 등록됐지만 LLM 추출되지 않았다. 실제 정책 전체를 1쪽만으로 확정하지 않는다. 데이터·코드는 실행 직전 다시 읽기 전용으로 확인한다.

## 3. 시험 적재 선행 데이터

| 대상 | 존재 / 시험 필요 | 필수 컬럼·관계 및 원문 근거 | 현재 가능성과 차단 사항 |
|---|---|---|---|
| `card_product` | 1건 존재, 재삽입 불필요 | `card_id=1`; 상품·문서 이름 확인 | 사용 가능. 상품이나 문서를 수정하지 않음 |
| `card_product_doc` | 1건 존재, 재삽입 불필요 | `(1,20261031_000001)`, 역할 PRODUCT_GUIDE, 승인 PENDING | 문서 관계 존재와 **승인 완료는 다르다**. 시험 참조 가능 여부는 승인 범위에서 결정 |
| `card_policy_version` | 0건; 실제 정책 시험에 1건 필요 | `(card_id,policy_ver_id)`, `policy_ver_no`, `valid_from NOT NULL`, `policy_status_cd`, `source_doc_list` | 적용 시작일 근거 미확인. 출시일·심의일을 대체하지 않음. 실제 정책 행의 정확한 생성 차단 |
| `card_bnft` | 0건; 4건 후보 | 정책 PK·혜택 ID, 코드·명칭·유형·출처·범위·검증 상태, `rule_list`, `bnft_cond_expr`, `relation_list` | 수치·대상은 1쪽에서 확인. 현재 후보 그대로는 OR·규칙 선택·근거 문제로 확정 불가 |
| `card_limit_pool` | 0건; 혜택별 여러 독립 풀 필요 | 정책 PK·pool ID, `pool_scope_cd`, `period_cd`, `cap_unit_cd`, `aggregation_key_cd`, `tier_list` | `CARD_MEMBER`는 현재 추출기가 일괄 대입한 후보이며 원문으로 합산 범위 미확인. 1인 1매는 기간/사람 단위 미해결 |
| `card_method_catalog` | 0건; 실제 규칙의 게이트 통과를 위해 CALC 2개 코드·버전 후보 | `(method_kind_cd,method_cd,method_ver)`, `param_schema`, `handler_key NOT NULL`, `method_status_cd` | `method_not_in_catalog`는 실제 행을 요구. handler 계약·상태·설명용 메타데이터 규약 미정. 빈 값·가짜 실행 가능 handler를 확정하지 않음 |
| `card_source_evidence` | 기존 30건 PENDING; 변경 불필요 | evidence ID ↔ 문서·페이지·청크·원문 위치 | 근거 자체는 있으나 승인되지 않음. 현 게이트는 연결된 PENDING 근거를 `evidence_not_approved`로 표시 |
| `card_policy_evidence` | 0건; 정책·규칙·조건·풀을 입증하려면 연결 행 필요 | 정책 PK·`ev_link_id`·`ev_subject_cd`·해당 혜택/규칙/풀 키·`ev_item_cd`/키·기존 evidence ID | 근거 승인 및 subject/item 연결 검토가 선행. PENDING을 APPROVED로 가장하거나 업데이트하지 않음 |
| `card_excl_item` | 0건; 반드시 신규 행이 필요한지는 미정 | 원문별 제외 개념과 ID. V6 조건의 `card_excl_item_id` 또는 `excl_raw_txt` | `excl_raw_txt`로 후보 표현 가능. 표준 제외 사전 구축은 별도 검토; 실적 산정 제외와 서비스 제외의 범위 구분 필수 |
| 공통 혜택 관련 4개 테이블 | 모두 0건 | 공통 정책 정체성·버전·상품 연결·근거 | 대상 4개 혜택이 공통 정책이라는 근거 없음. 단순 동일 문서/금액을 이유로 삽입하지 않음 |

## 4. 적재 순서와 키

물리 FK는 없지만 실제 논리 참조 순서는 **정책판 → 한도 풀과 혜택·규칙 → 규칙의 풀 참조 → 정책 근거 관계**다. 카탈로그는 규칙 게이트 검사 전에 준비되어야 한다. 혜택의 `rule_list`에 풀 ID가 들어가므로 삽입 시점에 풀 ID를 알고 있어야 한다. 데이터 설계 후 `card_limit_pool`을 `card_bnft`보다 먼저 삽입하면 혜택 JSON을 UPDATE하지 않고 작성할 수 있다.

기존 30개 source evidence는 그대로 사용하되 `card_policy_evidence`를 연결하는 순간 현 게이트의 `evidence_not_approved`를 예상한다. 승인 상태를 변조하지 않는 롤백 시험에서는 이 이슈를 **예상된 미통과**로 기록한다. 게이트를 0으로 만들기 위해 원문 승인이나 방법 실행 상태를 꾸미지 않는다.

## 5. 혜택별 매핑 후보

모든 값은 PDF `15650_20260429.pdf` 1쪽과 현재 staging의 대조 후보. source evidence ID와 원문의 전체 인용은 [매핑 검토](ONE_PICK_STYLE_V6_MAPPING_REVIEW.md) 2절·7절을 기준으로 한다. 예시 이름·키는 후보 식별자이지 확정 PK가 아니다.

| 혜택 후보 | 대상 / 계산 규칙 | 조건 JSON 및 한도 | 근거·상태 |
|---|---|---|---|
| ONE PICK | CU·GS25·세븐일레븐·메가MGC커피·이디야·컴포즈. `FIXED_PER_TXN` v1: 3천원 이상 100원, 1만원 이상 500원 | rule별 `cond_expr`의 TXN_AMT 하한. 일 1회, 월 30회, 월 5천원 **각 독립 한도**. 전월 실적 조건 없음은 원문과 근거를 보존 | 인용상 표 행·값 일치. `NO_EVIDENCE`: `one_pick_day` 직접 키 연결 부족. 100/500 규칙의 겹침과 선택 방식 미해결 |
| STYLE | 다이소·올리브영·교보문고·영풍문고·알라딘·yes24·아트박스·무신사·에이블리. 위와 같은 두 정액 규칙 | 일 1회, 월 10회, 월 5천원 **ONE PICK과 구별된 풀**. 전월 실적 조건 없음 | 행 연결 확인. `style_day` 직접 근거 부족. 두 5천원 인용이 같은 텍스트 위치를 가리켜 표 이미지 대조 필요 |
| ONE MORE 대중교통 | 버스·지하철. `PERCENT_OF_TXN` v1, 5% 캐시백 | **전월 실적 10만원 이상 OR 최초 카드 사용 등록일~다음 달 말일**. 별도로 시외·고속버스 및 철도 제외, 월 1천원 풀. 실적 제외는 실적 계산 범위 | 1쪽 evidence `20261031_000017`·`000018`·`000019`·`000020`. `VALUE_NOT_IN_QUOTE`; 현재 정규화 JSON의 AND를 그대로 적재 금지. handler 없이 원문 예외를 설명하는 DRAFT 표현만 우선 검토 |
| ONE MORE 놀이공원 | 에버랜드·롯데월드. `PERCENT_OF_TXN` v1, 50% **현장할인** | 전월 20만원 이상, 최초 발급월 미제공. 월 1회, 연 2회, **1인 1매** | 1쪽 evidence `20261031_000021`~`000025`; 월 한도·1인 1매의 직접 키 근거 부족. 1인 1매는 임의 월/연 기간 부여 금지 |

원문의 유예는 실적 자격의 OR 분기이며 공통 서비스 제외와 교통 제외를 면제하지 않는다. 전월 실적 산정 제외는 현재 이용 거래의 서비스 제외와 다른 의미다. 2쪽 일반 약관을 포함해 정책 전체를 사람이 확인해야 하며, 2쪽 LLM 호출 자체를必須 조건으로 단정하지 않는다.

## 6. 미해결 필수값과 근거

1. `card_policy_version.valid_from`: NOT NULL이지만 정책의 실제 적용 시작일 근거 미확인. PDF 2쪽 출시일 `2026-03-30`과 문서 심의일은 자동 대체값이 아니다.
2. `card_limit_pool.aggregation_key_cd`: 현재 후보의 `CARD_MEMBER`는 소스에서 생성한 기본값. 회원·가족카드 합산 범위를 원문으로 확정하지 못했다. `period_cd=UNKNOWN`인 1인 1매도 유효한 기존 주기 코드로 임의 대체하지 않는다.
3. `card_method_catalog.handler_key`와 `param_schema`·상태: V6는 handler_key NOT NULL. 실행 handler 없이 설명 데이터만 보존하는 계약을 별도 결정해야 한다. 개인별 날짜 계산 handler는 MVP에서 필수가 아니다.
4. 추출 상태·근거 승인: 4개 혜택 모두 `NO_EVIDENCE` 또는 `VALUE_NOT_IN_QUOTE`, 근거 모두 PENDING. 값의 수동 대조와 키 연결, 승인 근거 없이 `CONFIRMED`/`APPROVED`로 바꾸지 않는다.
5. 100/500원 중복·우선, GRACE OR 및 공통 제외 범위, `no_condition_stated=false`와 실적 없음의 의미를 정리한다. `fn_valid_*`의 true는 이러한 의미 검증이 아니다.

## 7. `card_method_catalog` 선행 조건

1쪽의 정규화 규칙은 `FIXED_PER_TXN` v1과 `PERCENT_OF_TXN` v1을 요구한다. 실제 `common_cd`에는 두 코드가 있지만 `card_method_catalog`는 0건이다. 현행 `v_card_integrity_issue.method_not_in_catalog`은 로컬·공통 규칙의 `(CALC, calc_method_cd, method_ver)` 존재를 검사하므로, 다른 모든 조건이 같다면 해당 규칙을 넣은 후 **두 코드/버전이 게이트 결과에 나타날 것으로 예상**한다. 실제 시험은 하지 않았다.

반대 방향 `catalog_method_not_in_code`는 카탈로그 코드가 해당 공통코드 그룹에 속하는지 검사한다. 현재 게이트는 handler의 실제 구현·활성 상태나 `param_schema`가 실제 params와 맞는지 검증하지 않는다. Seed에 `UNEXECUTABLE` 상태는 존재하지만 **어떤 handler_key, param_schema와 상태 조합이 설명 전용 계약으로 적합한지 아직 결정되지 않았다.** `UNEXECUTABLE`이라는 코드가 존재한다는 사실만으로 임의 문자열 handler가 승인되는 것은 아니다. 코드·수치·원문을 데이터로 보존하는 것과 실제 개인별 계산을 실행하는 것은 별개다. 카탈로그 삽입·수정은 이번에 하지 않는다.

## 8. 향후 시험 SQL 초안 — 승인 전 실행 금지

아래는 **설명용 비실행 골격**이다. `<...>`는 SQL 리터럴이 아니며 미확정 사항이다. PostgreSQL 구문·함수는 원칙적으로 V6 컬럼 기준이지만, 완성된 실행 스크립트나 승인된 데이터가 아니다. `BEGIN`은 향후 실제 승인된 격리 시험에서만 열고 **COMMIT 없이 ROLLBACK**한다. 다음 INSERT 문장들은 순서를 보여 주기 위한 초안으로, 이번에는 실행하지 않았다.

### 8.1 선행 조회와 시퀀스 없는 ID 충돌 확인

```sql
-- 읽기 전용 사전 확인: 실제 승인 전에도 SELECT만 허용
SELECT p.card_id, p.product_cd, pd.card_doc_id, pd.approval_status_cd,
       d.card_id AS doc_card_id, d.doc_status
FROM db_pipeline.card_product p
JOIN db_pipeline.card_product_doc pd ON pd.card_id=p.card_id
JOIN db_pipeline.card_doc d ON d.card_doc_id=pd.card_doc_id
WHERE p.card_id=1 AND d.card_doc_id='20261031_000001';

SELECT method_kind_cd,method_cd,method_ver,method_status_cd
FROM db_pipeline.card_method_catalog
WHERE method_kind_cd='CALC' AND method_cd IN ('FIXED_PER_TXN','PERCENT_OF_TXN');
SELECT common_code_grp_id,common_cd FROM db_pipeline.common_cd
WHERE common_code_grp_id='CALC_METHOD'
  AND common_cd IN ('FIXED_PER_TXN','PERCENT_OF_TXN');

SELECT stg_item_seq,stg_kind_cd,stg_status,stg_sql_check_cd,
       stg_normalized_item->'checks' AS checks
FROM db_pipeline.card_extr_stg
WHERE card_ai_run_id='20261031_000001' ORDER BY stg_item_seq;
SELECT approval_status_cd,count(*) FROM db_pipeline.card_source_evidence
WHERE card_doc_id='20261031_000001' GROUP BY approval_status_cd;

-- 아래 ID 값은 별도 지정·검토; 실제 테이블의 기존 전체 키와 충돌이 없는지 확인.
SELECT card_id,policy_ver_id FROM db_pipeline.card_policy_version
WHERE card_id=1 AND (policy_ver_id=<policy_ver_id> OR policy_ver_no=<policy_ver_no>);
SELECT card_id,policy_ver_id,card_bnft_id,bnft_cd FROM db_pipeline.card_bnft
WHERE card_id=1 AND policy_ver_id=<policy_ver_id>
  AND (card_bnft_id IN (<bnft_id_1>,<bnft_id_2>,<bnft_id_3>,<bnft_id_4>)
       OR bnft_cd IN (<bnft_cd_1>,<bnft_cd_2>,<bnft_cd_3>,<bnft_cd_4>));
SELECT card_id,policy_ver_id,pool_id FROM db_pipeline.card_limit_pool
WHERE card_id=1 AND policy_ver_id=<policy_ver_id> AND pool_id IN (<all_pool_ids>);
```

### 8.2 INSERT 초안: 순서와 누락 금지 항목

각 `<...>` 값, 각 정책 조건·룰·풀 JSON과 증거 링크는 사람 검토 후 명시한다. 데이터가 없는 현재 상태에서는 실제 카드에 대한 `valid_from`, `aggregation_key_cd`, method 계약, 증거 승인 등이 확정되지 않아 실행하면 안 된다. 4개 혜택의 JSON을 통째로 staging에서 복사하면 임시 풀 ID와 잘못된 AND가 그대로 남는다.

```sql
-- 승인 전 실행 금지. 각 괄호는 설명용 자리표시자다.
BEGIN;

-- [선택적 선행] 방법 계약이 별도로 검토·승인된 경우에만 두 행.
-- handler_key는 NOT NULL. 실제 실행 가능한 handler라고 암시하는 값을 만들지 않는다.
INSERT INTO db_pipeline.card_method_catalog
  (method_kind_cd,method_cd,method_ver,param_schema,handler_key,method_status_cd)
VALUES
  ('CALC','FIXED_PER_TXN',1,<validated_param_schema_jsonb>,<reviewed_handler_key>,<reviewed_method_status>),
  ('CALC','PERCENT_OF_TXN',1,<validated_param_schema_jsonb>,<reviewed_handler_key>,<reviewed_method_status>);

INSERT INTO db_pipeline.card_policy_version
  (card_id,policy_ver_id,policy_ver_no,policy_cond_expr,source_doc_list,
   valid_from,valid_to_excl,approved_at,policy_status_cd)
VALUES
  (1,<policy_ver_id>,<policy_ver_no>,<reviewed_policy_expr_jsonb>,<reviewed_doc_list_jsonb>,
   <evidence_based_valid_from>,<valid_to_excl_or_null>,NULL,<reviewed_draft_policy_status>);

-- 한도당 1행. pool_id는 명시적 시험 ID; `tier_list`의 실제 JSON 계약을 검토.
-- ONE PICK/STYLE 각 일·월 횟수/월 금액, 교통 월 금액, 놀이공원 월·연 횟수.
-- 1인 1매의 기간·집계 코드가 확정되기 전 별도 풀 생성 금지.
INSERT INTO db_pipeline.card_limit_pool
  (card_id,policy_ver_id,pool_id,pool_scope_cd,period_cd,cap_unit_cd,aggregation_key_cd,tier_list)
VALUES (1,<policy_ver_id>,<pool_id>,<reviewed_scope>,<day_month_year>,
        <count_or_krw>,<evidence_based_aggregation>,<reviewed_tier_list_jsonb>);
-- 나머지 풀별로 반복. 같은 5천원이라도 다른 혜택의 풀 ID를 합치지 않는다.

-- 혜택별 4행. 모든 rule의 pool_refs[].pool_id는 실제 위 pool_id로 교체한다.
INSERT INTO db_pipeline.card_bnft
  (card_id,policy_ver_id,card_bnft_id,bnft_cd,bnft_nm,bnft_type_cd,bnft_origin_cd,
   bnft_scope_cd,bnft_brand_opt_cds,bnft_cond_expr,rule_select_cd,rule_list,relation_list,verification_status_cd)
VALUES
 (1,<policy_ver_id>,<bnft_id_1>,<bnft_cd_1>,<one_pick_name>,'CASHBACK','LOCAL','PRODUCT',NULL,<expr_1>,<unresolved_selection_1>,<reviewed_rules_1>,'[]'::jsonb,<reviewed_status>),
 (1,<policy_ver_id>,<bnft_id_2>,<bnft_cd_2>,<style_name>,'CASHBACK','LOCAL','PRODUCT',NULL,<expr_2>,<unresolved_selection_2>,<reviewed_rules_2>,'[]'::jsonb,<reviewed_status>),
 (1,<policy_ver_id>,<bnft_id_3>,<bnft_cd_3>,<transit_name>,'CASHBACK','LOCAL','PRODUCT',NULL,<spend_or_grace_expr>,<selection_3>,<reviewed_rules_3>,'[]'::jsonb,<reviewed_status>),
 (1,<policy_ver_id>,<bnft_id_4>,<bnft_cd_4>,<amusement_name>,'DISCOUNT','LOCAL','PRODUCT',NULL,<expr_4>,<selection_4>,<reviewed_rules_4>,'[]'::jsonb,<reviewed_status>);

-- evidence 승인 상태는 변경하지 않는다. 미승인 연결은 게이트 결과에 드러나야 한다.
INSERT INTO db_pipeline.card_policy_evidence
  (card_id,policy_ver_id,ev_link_id,ev_subject_cd,card_bnft_id,rule_key,relation_key,pool_id,
   ev_item_cd,ev_item_key,evidence_id)
VALUES (1,<policy_ver_id>,<ev_link_id>,<subject>,<bnft_id_or_null>,<rule_key_or_null>,
        <relation_key_or_null>,<pool_id_or_null>,<item_type>,<item_key>,<existing_evidence_id>);
-- subject별 허용 NULL 조합과 item 키를 검사하고 근거별 반복한다.

-- 확인 후 반드시 ROLLBACK. 아래는 초안이며 이번에 실행하지 않았다.
ROLLBACK;
```

`card_policy_evidence`의 subject는 POLICY/BNFT/RULE/POOL/REL별로 허용되는 키가 다르고 `SELF`일 때 `ev_item_key='-'`여야 한다. 유효한 조건 atom·target·tier 키가 참조 대상에 실재하는지도 확인해야 한다. `card_source_evidence`는 기존 PENDING 행을 UPDATE하지 않는다. 실제 시험 시 단순 구조 연습이라면 가상 상품·가상 날짜를 **명시적으로 구별한 격리 DB**에서 하고 실제 상품 데이터의 정확성 근거로 사용하지 않는다.

### 8.3 INSERT 후 확인 SELECT와 함수

```sql
-- 별도 승인된 시험 트랜잭션 안에서만 실행할 확인 예시
SELECT card_id,policy_ver_id,valid_from,valid_to_excl,policy_status_cd
FROM db_pipeline.card_policy_version WHERE card_id=1 AND policy_ver_id=<policy_ver_id>;
SELECT card_bnft_id,bnft_nm,bnft_cond_expr,rule_select_cd,rule_list,verification_status_cd,
       db_pipeline.fn_valid_cond_expr(bnft_cond_expr) AS cond_ok,
       db_pipeline.fn_valid_rule_list(rule_list,'LOCAL') AS rule_ok,
       db_pipeline.fn_valid_relation_list(relation_list,card_bnft_id) AS relation_ok
FROM db_pipeline.card_bnft WHERE card_id=1 AND policy_ver_id=<policy_ver_id>;
SELECT pool_id,period_cd,cap_unit_cd,aggregation_key_cd,tier_list,
       db_pipeline.fn_valid_tier_list(tier_list) AS tier_ok
FROM db_pipeline.card_limit_pool WHERE card_id=1 AND policy_ver_id=<policy_ver_id>;
SELECT * FROM db_pipeline.v_card_rule_pool WHERE card_id=1 AND policy_ver_id=<policy_ver_id>;
SELECT * FROM db_pipeline.card_policy_evidence WHERE card_id=1 AND policy_ver_id=<policy_ver_id>;
SELECT gate_cd,count(*) AS n FROM db_pipeline.v_card_integrity_issue GROUP BY gate_cd ORDER BY gate_cd;
```

실제 SELECT의 함수 결과와 게이트 결과는 시험 시 확인한다. evidence가 PENDING이면 `evidence_not_approved`, catalog가 비면 `method_not_in_catalog`, 임시 풀 키를 실제 ID로 바꾸지 않으면 `pool_ref_orphan`이 예상된다. 예상 오류와 추가 오류를 구분한다.

로컬 DDL의 `fn_valid_tier_list`는 `VERIFIED_UNCONDITIONAL`에서 `t.value->'cond_expr' IS NULL`을 검사한다. JSON에서 키가 없는 경우와 키 값이 JSON `null`인 경우가 다르므로, `"cond_expr": null`을 무조건 허용한다고 가정하지 않는다. 실제 DB 함수 정의와 승인된 시험 환경에서 키 생략·JSON null의 동작을 별도 확인한다.

## 9. SQL 정합성 게이트 시나리오

현행 실제 DB의 관련 CHECK와 로컬 V6 뷰 정의를 확인했지만, **아래 실패 사례를 실제로 삽입해 시험하지 않았다.** CHECK는 문장 실행 시 막고, VIEW는 SELECT 시 문제 행을 반환하며 자동 롤백·승인을 수행하지 않는다.

| 시나리오 | 예상 검출 위치 | 한계 |
|---|---|---|
| 없는 정책의 혜택·풀 | `bnft_without_policy`, `pool_without_policy` | 물리 FK 없음. VIEW 조회 전 삽입 자체는 가능할 수 있음 |
| 없는 혜택 참조 | `rel_to_bnft_orphan`, `evidence_subject_orphan` 등 관계별 검사 | 모든 임의의 JSON 문자열 참조를 일반적으로 검출하는 것은 아님 |
| 없는 풀 참조 | `pool_ref_orphan`, 관계의 `rel_trigger_pool_orphan` | 실제 적재 후 조회 필요. staging 임시 키는 대상 풀로 변환해야 함 |
| 없는 계산 방법/버전 | `method_not_in_catalog` | 계산 규칙의 CALC 코드·버전 존재 검사. handler 실행 가능성·상태는 검사하지 않음 |
| JSONB 구조 오류 | `fn_valid_cond_expr`, `fn_valid_rule_list`, `fn_valid_tier_list`, 관련 CHECK | 올바른 JSON 형식이 원문 의미까지 맞는다는 뜻은 아님 |
| 잘못된 조건·기타 코드 | `v_common_cd_usage` 경유 `common_cd_invalid` | 함수 자체는 모든 코드의 사전 소속을 검증하지 않음. 표현된 코드 경로만 대상 |
| 중복 규칙/ID | `fn_valid_rule_list`의 규칙 키 중복, 각 테이블 PK/UNIQUE | 뜻은 같은데 키가 다른 중복·날짜별 중복 전체는 별도 검토 |
| 원문 근거 불일치 | `evidence_source_orphan`, `evidence_not_approved`, `evidence_subject_orphan`, `evidence_item_key_missing` | 인용이 그 혜택 행의 참뜻인지와 이미지 표 위치까지 자동 판정하지 않음 |
| 정책 적용 기간 | CHECK의 `valid_to_excl > valid_from`, `policy_period_overlap` | overlap 게이트는 APPROVED 간 충돌. 실제 시작일이 사실인지 확인하지 않음 |
| 공유 한도 오류 | 풀 고아 게이트 및 `common_pool_key_conflict` 등 | 사용된 한도들이 원문에서 실제로 공유되는지는 PDF·범위 검토 필요 |

## 10. SQL 자동 검출과 원문 검출 구분

| 사례 | 분류 | 이유 |
|---|---|---|
| 실제 풀 없는 `pool_refs` | SQL 자동 검출 가능 | 확정 행을 넣고 `v_card_integrity_issue` 조회 시 `pool_ref_orphan` 예상; 미실행 |
| 카탈로그 없는 CALC 방법 v1 | SQL 자동 검출 가능 | 현 게이트 정의상 `method_not_in_catalog`; 미실행 |
| `rule_key` 중복 또는 잘못된 JSON 타입 | SQL 자동 검출 가능 | `fn_valid_rule_list`·CHECK. 문장 결과는 시험하지 않음 |
| 교통 실적 AND 유예 | 원문 검토 필요 | 현재 형식 함수는 잘못된 AND 후보도 통과. PDF와 대조해 OR 발견 |
| ONE PICK 월 30회·STYLE 월 10회 연결 | 원문 검토 필요 | PDF 표 행/이미지에 의존. 텍스트에 두 숫자가 있다는 것만으로는 부족 |
| 반복 `월 5천원`과 공유 여부 | 원문 검토 필요 | 두 인용이 같은 텍스트 위치를 가리킴. 실제 표 셀은 혜택별로 구분 |
| 1인 1매의 정확한 기간·집계 | 추가 검증 필요 | 현재 필수 기간/집계 코드로 원문 의미를 임의 확정할 수 없음 |
| SQL 함수의 모든 오류 처리와 handler·파라미터 검증 | 추가 검증 필요 | 실제 실패 주입을 실행하지 않았고 `param_schema` 적용 검증 구현도 확인되지 않음 |

## 11. ROLLBACK 절차 및 시퀀스 주의

별도 승인 이후에만 대상 DB·스키마·백업·트랜잭션 범위와 동시 작업을 확인한다. 자동 커밋을 끄고 연결 하나에서 `BEGIN`→사전 조회→승인 범위의 INSERT→함수·게이트·원문 대조→**반드시 `ROLLBACK`**한다. 오류 발생 시 트랜잭션은 실패 상태가 되므로 `ROLLBACK` 또는 승인된 SAVEPOINT 복구 후에만 조회를 이어간다. 사후에는 별도 읽기 전용 조회로 시험 행이 없음을 확인한다. 예상 PENDING 근거/미비 카탈로그는 억지로 0행으로 만들지 않고 기록한다.

PostgreSQL `nextval()`은 롤백되지 않는다. 실행 금지인 이번 단계에서는 시퀀스를 조회로 증가시키거나 재설정하지 않았다. 향후 시험에는 **모든 생성 ID를 명시적으로 지정하여 DEFAULT를 호출하지 않는 방안**을 우선 검토한다. 예시 가상 ID는 실제 업무 ID와 구별하고 `varchar(20)`·키 형식 및 모든 PK/UNIQUE·JSON 참조·다른 테이블과 충돌을 사전 검사한다. 동시 적재가 있으면 사전 조회만으로 충돌 방지를 보장하지 못하므로 격리 DB 또는 작업 중지·트랜잭션 보호가 필요하다. 가상 ID 형식을 쓰면 기존 `YYYYMMDD_000001` 발급 규칙 자체는 시험되지 않는다. DEFAULT/시퀀스 시험이 필요하면 폐기 가능한 별도 DB에서만 별도 승인 후 진행하고, 공유 DB의 시퀀스를 되돌리는 조작은 하지 않는다.

## 12. A7-2 실행 가능 여부

| 구분 | 항목 |
|---|---|
| **실제 카드의 정확한 시험 적재를 차단** | 근거 있는 `valid_from`, 풀 집계 범위·1인 1매 표현, 교통 OR와 제외 적용 의미, 규칙 선택과 승인되지 않은 근거·방법 계약. 문서 2쪽을 포함한 정책 확인도 필요 |
| **부분 시험은 가능하나 미해결 유지** | 승인된 격리 DB에서 가상 정책·ID·날짜를 명확히 표시한 구조 전용 ROLLBACK 실험. 실제 카드의 정책 정확성·승인 완료로 간주하지 않음. 1쪽 값만 다루는 범위도 문서 전체 확정이 아님 |
| **A7-2 이후 Neo4j 전 해결 가능** | 실제 그래프 적재·검색 성능과 벡터 RAG 비교. 다만 변환할 OR·풀·근거 의미와 안정 키는 적재 전부터 보존해야 함 |

따라서 **이번 작업만으로 실제 ROLLBACK 시험은 승인되지 않았고, 실제 카드의 완전한 정확성 시험은 준비 미완료**다. 다음 검토에서 미확정 값의 근거·시범 범위와 방법 계약을 결정한 뒤 별도 승인을 받는다.
