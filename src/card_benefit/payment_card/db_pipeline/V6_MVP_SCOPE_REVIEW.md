# 카드 혜택 GraphRAG — PostgreSQL V6 MVP 범위 검토

## 1. 검토 목적과 MVP 범위

기준은 [PROJECT_SCOPE.md](../PROJECT_SCOPE.md)의 발급 전 카드 검색·비교·추천이다. 혜택률·정액·실적 기준·면제·예외·제외·한도와 PDF 근거를 설명하며, 사용자 질문에 주어진 관심사를 비교 조건으로 쓴다. 개인 이용내역 저장, 개인별 지급·정산, 거래별 실행 엔진 및 개인 등록일을 계산하는 handler는 MVP 필수가 아니다. **실행하지 않더라도 계산 규칙과 조건의 의미·관계는 보존해야 한다.**

추천: **당장은 V6를 유지하고 A7-2에서 의미와 검증을 시험한다.** 테이블 21개 중 유지 15, 조건부 유지 6, 테이블 제거 확정 0이다. `card_method_catalog.handler_key`는 실행 엔진 중심의 **컬럼 단순화 후보**지만 현재 NOT NULL이며 변경을 실행하지 않는다. 표의 분류는 MVP 논리 역할을 기준으로 한 검토안이며 삭제 승인이나 물리 변경 지시가 아니다.

## 2. 분석 기준과 확인 범위

- 파일: [V6 DDL](../../sql/db_pipeline_schemaV6_draft.sql), [DBML](../../sql/db_pipeline_schemaV6_draft.dbml), [공통코드 Seed](../../sql/db_pipeline_common_code_seedV6.sql), [구현 현황](PROJECT_STATUS.md), [실제 카드 매핑 검토](ONE_PICK_STYLE_V6_MAPPING_REVIEW.md), `db_pipeline/`의 Python·SQL Mapper. `src/`의 Python·SQL에서 `handler_key`, `param_schema`, 카탈로그 참조도 검색했다.
- 개발 Supabase를 `SET TRANSACTION READ ONLY` 후 조회: 실제 `db_pipeline` 테이블 **21개**, 물리 FK **0개**, VIEW **13개**, `card_method_catalog` **0행**, `v_card_integrity_issue` **0행**. 실제 카탈로그의 카탈로그 테이블 컬럼·타입·NOT NULL도 확인했다.
- **기준 분리:** DB의 테이블 이름·수, 위 카탈로그 컬럼·행·뷰 목록은 이번 실제 조회 결과다. 각 테이블의 상세 구조·함수·게이트의 해석은 V6 파일과 소스 기준이며, 실제 DB의 모든 컬럼·CHECK·함수·뷰 정의를 파일과 전수 비교하지 않았다. DB 변경 여부 및 데이터 사용량은 시점에 따라 다시 확인해야 한다.
- [매핑 검토](ONE_PICK_STYLE_V6_MAPPING_REVIEW.md)는 실제 ONE PICK STYLE 1쪽의 원문·후보를 확인했다. 현재 정규화된 교통 유예가 전월 실적과 잘못 AND로 묶여 있다. 정합성 뷰 0행은 아직 미적재 후보의 의미 정확성을 입증하지 않는다.

## 3. V6 21개 테이블 전체 분류

표의 ‘그래프’는 향후 변환할 수 있는 의미이지 구현 완료를 뜻하지 않는다. ‘대안/손실’은 제거·통합을 가정한 영향이며 자동으로 권고하는 변경이 아니다.

| 테이블 | 분류 | 현재 역할과 MVP·검증·그래프 기여 | 대안 / 제거 시 손실 |
|---|---|---|---|
| `common_code_grp` | 유지 | 공통코드 그룹; 조건·단위 등의 분류와 그룹 정합성 검증, 그래프 관계 유형의 기준 | 고정 enum·외부 사전 가능하나 코드 소속·변경 추적과 `common_code_grp_empty` 검사 재구현 필요 |
| `common_cd` | 유지 | 계산·조건·상태·한도 코드 사전; `v_common_cd_usage`와 유효 코드 검사, 그래프 변환의 의미 표준 | 문자열/코드상수로 통합 가능하나 `common_cd_invalid` 및 일관성 검사 대체 필요 |
| `card_product` | 유지 | 상품 식별·카드 비교의 출발점, 혜택의 부모, 그래프 Card | 문서 JSON에 합치면 문서판과 상품 식별·여러 문서 관계 관리가 어려워짐 |
| `card_policy_version` | 유지 | 상품별 정책 기간·공통 조건·원천 문서 목록. 현재/과거를 구별하고 혜택·근거의 부모 | 상품에 합치면 개정 이력·시점·근거가 섞이고 overlap 검사 상실. 단 실제 `valid_from`을 임의로 채우면 안 됨 |
| `card_product_doc` | 유지 | 상품↔문서 N:M, 역할·승인·적용 기간, 그래프 상품 출처 | JSON로 통합 가능하나 다대다 조회·승인·기간·중복 및 브랜드 적용 검증을 재작성해야 함 |
| `card_bnft` | 유지 | 상품 정책의 혜택, 규칙·대상·조건·관계 JSON. 비교 및 그래프 Benefit의 핵심 | staging만 사용하면 승인된 혜택의 안정 키·조건·원본 후보 분리가 약화 |
| `card_limit_pool` | 유지 | 금액/횟수·기간별 한도와 `tier_list`, 여러 규칙의 공유 풀 식별 | 규칙 JSON에 복제하면 동일 금액과 공유 풀의 차이·고아 검사·집계 의미가 손실 |
| `card_policy_evidence` | 유지 | 정책/혜택/규칙/풀/관계 및 조건·대상·구간 키를 승인된 근거에 연결, 그래프 출처 경로 | 본문 JSON에 근거 ID를 넣으면 대상 키·승인·고아 검사와 다중 근거 조회를 다시 구현해야 함 |
| `card_doc` | 유지 | PDF 문서판, 해시·출처·상태; 원문 추적의 시작 | 상품에 합치면 공통 문서와 여러 버전의 독립 관리가 손실 |
| `card_doc_page` | 유지 | 페이지 원문과 해시·추출 상태; PDF 페이지 인용·OCR 검증 | 문서 본문으로 합치면 쪽 단위 위치·검증과 재추출 비교가 약화 |
| `card_doc_chunk` | 유지 | PAGE_V1 입력·청크 원문과 상태, 근거 좌표의 부모 | 현재 1페이지=1청크이므로 page와 합칠 수 있으나 청크 버전·분할 확장·evidence 참조·기존 pipeline을 이행해야 함 |
| `card_ai_run` | 유지 | 추출 모델·프롬프트·실행 상태·재현 정보, 검토 결과 출처 | 호출 JSON에 합치면 실행 단위 재시도·비교·상태와 추출 이력 관리 손실 |
| `card_ai_call` | 유지 | 페이지별 원본 응답·토큰·실패, 재시도 이력; 후보의 출처 | run에 합치면 페이지·재호출별 원문 보존과 실패 추적이 복잡해짐 |
| `card_extr_stg` | 유지 | 혜택/조건 원본 JSON, 정규화·검증·승인 후보, 업무 확정 전 검토 | call JSON에만 두면 항목별 상태·근거·중복 병합·SQL 검증을 별도 재구현해야 함 |
| `card_source_evidence` | 유지 | 문서·쪽·청크·인용 위치·승인 상태. 답변 출처와 후보 검증 | staging에 내장 가능하나 동일 근거의 다중 연결·승인·위치 참조 및 증거 고아 검사 약화 |
| `card_excl_item` | 조건부 유지 | 표준 제외 개념; 같은 의미의 제외 비교·조건 atom 참조 정합성 | 원문 문자열만 보존 가능하나 별칭/동의어 차이로 카드 간 비교와 `excl_item_unknown` 검사 약화. 실제 표준화 필요성 검증 |
| `card_common_bnft` | 조건부 유지 | 독립 공통 혜택의 정체성; 동일 정책을 공유하는 카드 간 그래프 연결 | 상품 혜택에 복제하면 구현은 단순하나 정책 동일성·중복·공통 개정 추적 및 공유 탐색 손실. 이름/PDF 공유만으로 동일 정책 추정 금지 |
| `card_common_policy_version` | 조건부 유지 | 공통 혜택별 기간·규칙·대상·한도; 공통 개정 이력 | 상품별 복제 가능하나 버전 간 불일치·공통 근거 관리 손실. 실제 공통 정책 사례로 판단 |
| `card_bnft_common` | 조건부 유지 | 상품 혜택↔공통 정책판 연결·승인. 공유 정책 그래프 관계 | 상품 JSON 참조로 대체 시 고아·승인·기간 중복 게이트와 N:M 조회 재구현 필요 |
| `card_common_rule_evidence` | 조건부 유지 | 공통 규칙·조건·대상·한도 키↔원문 근거, 공통 답변 출처 | 상품 근거 관계에 합치면 공통 개체에 상품 ID를 억지로 부여하거나 다형 참조 검증을 다시 설계해야 함 |
| `card_method_catalog` | 조건부 유지 | 계산/술어 코드·버전과 계약 메타데이터; 현재 계산 코드+버전 존재 검사에 사용 | 코드 사전으로 단순화 가능하나 버전별 카탈로그 존재 검사와 계약 정보를 대체해야 함. 아래 영향 분석 참조 |

## 4. `card_method_catalog` 집중 분석

| 컬럼 | 현재 역할 | MVP 판단 |
|---|---|---|
| `method_kind_cd` | CALC/PREDICATE 구분 | 설명용 분류는 필요할 수 있으나 공통코드 그룹과 중복 관리 가능성 검토 |
| `method_cd` | 계산·술어 방법 코드 | 규칙의 의미 보존에 필요. `common_cd`의 CALC_METHOD/PREDICATE_METHOD로 코드 존재를 관리할 수 있음 |
| `method_ver` | 방법별 버전, 복합 PK와 규칙의 버전 참조 | 실행 없이도 코드의 의미·계약이 바뀌면 과거 데이터 해석에 유용. 하나의 정의만 쓰는 MVP에서는 이익과 관리 비용을 시험 후 판단 |
| `param_schema` | 유형별 파라미터 JSON 스키마로 의도됨 | **현재 V6 CHECK는 값이 JSON 객체인지 확인할 뿐**, 실제 `calc_params`/`cond_params`를 이 스키마로 검증하지 않는다. 별도 검증기 연결 전에는 형식 계약을 저장하는 메타데이터다 |
| `handler_key` | 실행 함수 식별자 | `src/`의 Python·SQL 검색에서 현행 V6 DDL·COMMENT 외 실행 참조는 발견하지 못함. 개인별 실행 제외 MVP에서는 불필요한 필수값일 가능성이 높아 nullable 또는 제거 후보. 미검색 외부 도구는 추가 확인 |
| `method_status_cd` | 카탈로그 방법 상태 | 승인·폐기 기준으로 유용할 수 있으나 현재 `method_not_in_catalog`은 카탈로그 행의 상태를 검사하지 않음 |

실제 DB에서 카탈로그는 비어 있다. V6 `v_card_integrity_issue`의 `method_not_in_catalog`은 **상품 및 공통 계산 규칙의 `(CALC, calc_method_cd, method_ver)` 존재**를 검사한다. 이 게이트는 predicate 버전이나 handler 실행을 검사하지 않는다. `catalog_method_not_in_code`는 카탈로그의 방법 코드가 유형에 따른 공통코드 그룹에 있는지 역방향으로 검사한다. `v_common_cd_usage`도 카탈로그의 kind/status 사용을 포함한다. 따라서 빈 카탈로그에서 계산 규칙을 확정 테이블에 넣으면 method 게이트가 발생할 수 있다.

**제거 가능성:** MVP의 코드 명칭·종류만 필요하면 `common_cd`로 대체하는 방안을 검토할 수 있다. 다만 공통코드는 현재 method 버전별 계약의 대체물이 아니므로 `method_not_in_catalog`을 코드+버전 규약으로 대체하거나 버전 검증을 포기해야 한다. 역방향 게이트와 `v_common_cd_usage`의 카탈로그 참조도 변경해야 한다. `param_schema` 검증을 향후 구현할 계획을 포기하면 파라미터별 자동 검증 가능성이 줄어든다. 현재 JSON 객체 여부 외에 스키마별 검증은 없으므로 **이미 제공되는 검증을 잃는다고 과장하지 않는다.**

추천은 **카탈로그 테이블의 즉시 삭제 보류**, `handler_key NOT NULL`의 불필요성은 별도 변경 후보로 기록하는 것이다. MVP에서 handler를 호출하지 않아도 현 V6의 NOT NULL 및 게이트는 그대로 적용된다. 값만 맞추기 위해 존재하지 않는 handler를 등록하지 않는다.

## 5. 계산 실행과 정책 데이터

| 보존할 데이터 | 개인별 실행 엔진과의 관계 |
|---|---|
| 계산 방식·비율·금액·단위·건당 금액 기준 | 카드 비교와 3천원/1만원 구간의 설명에 필요. 실제 거래에 적용해 지급액을 계산할 필요는 없음 |
| 전월 실적, 최초 등록 유예, AND/OR/NOT·예외 범위 | 조건의 설명·필터·근거 보존에 필요. 개인 등록일을 받아 유예를 판정하는 handler는 MVP 밖 |
| 공유/개별 풀과 금액·횟수·주기 | 여러 혜택이 같은 한도를 쓰는지 설명·관계 탐색하는 데 필요. 개인의 한도 소진 계산은 제외 |
| 정책 버전·적용 기간·원문 근거 | 과거·현행 문서 혼동을 방지. 확인되지 않은 적용 시작일은 만들지 않음 |

## 6. JSONB 유지와 단순화

| 구조 | MVP에서 유지할 의미 | 단순화·검증 시 주의 |
|---|---|---|
| `card_bnft.rule_list` | 계산 방식·`value_num`/단위·`cond_expr`·대상·`pool_refs`·우선순위 | 실행 관련 미사용 파라미터는 보류 가능하나 값과 조건 연결을 제거하지 않음. `v_card_rule`, `v_card_rule_target`, `v_card_rule_pool` 의존 |
| `card_bnft.bnft_cond_expr` | 혜택 공통 조건과 예외. branch OR, branch 내부 AND, `negate_yn` NOT | 현재 `build_cond_expr`는 단일 AND branch만 생성. 교통 실적 OR 유예를 잘못 묶는 사례는 [매핑 검토 7절](ONE_PICK_STYLE_V6_MAPPING_REVIEW.md) 참조 |
| `card_bnft.relation_list` | 명시된 중복 불가·우선·대체 관계 | 개인 정산이 없어도 비교 설명과 공유관계에 유용할 수 있음. 존재하지 않는 관계를 추론해 생성하지 않음 |
| `card_policy_version.policy_cond_expr` | 해당 정책 전체에 적용되는 조건·제외 | 혜택별 실적 조건이나 실적 산정 제외를 무조건 전 거래 공통 제외로 바꾸지 않음 |
| `card_limit_pool.tier_list` | 같은 풀의 실적 구간별 금액/횟수 한도·조건 | 구간과 공유 ID는 그래프에 보존. 동일 금액은 공유 증거가 아님 |
| 공통 정책 `rule_list`, 내부 `limit_list` | 여러 상품이 공유하는 검증된 정책·한도와 근거 | 실제 정책 동일성이 확인될 때 사용. 같은 PDF 또는 이름만으로 병합 금지 |

V6는 JSONB CHECK와 행 투영 VIEW를 결합한다. 형식 검증은 조건식의 branch·atom·키, 타입·범위와 참조 형태를 검사하지만, **OR 유예가 AND로 잘못 묶인 후보도 통과할 수 있다.** `fn_cond_spend_bound`는 OR·복수 실적 atom에서 NULL이므로 단일 숫자만으로 ‘실적 없음’을 판정하지 않는다. `no_condition_stated=false`와 미추출 상태도 구분해야 한다. 그래프 변환은 branch 번호, atom 키·부정, 정책판, 원문 근거를 잃지 않아야 한다.

## 7. SQL 정합성 검증 영향

V6 CHECK에는 `fn_valid_cond_expr`, `fn_valid_rule_list`, `fn_valid_target_list`, `fn_valid_tier_list`, `fn_valid_limit_list`, `fn_valid_relation_list`, `fn_valid_doc_ref_list` 등이 있다. 코드 정의와 상세 의미는 DDL이 기준이며 DB와의 전체 정의 동등성은 미검증이다.

| 검증 계열 | 현재 기여 / 변경 영향 |
|---|---|
| 정책·상품·혜택 부모 및 정책 기간 | `policy_without_product`, `bnft_without_policy`, `policy_period_overlap` 등. 정책 테이블을 합치면 부모·시점 검사를 대체해야 함 |
| 풀·관계 | `pool_without_policy`, `pool_ref_orphan`, `rel_to_bnft_orphan`, `rel_trigger_pool_orphan`, 양방향 중복·fallback cycle. 공유 풀을 JSON에 복제하면 동일 공유 ID의 고아 검사·범위 관리 약화 |
| 공통 정책·브랜드 | `common_link_orphan`, `common_link_without_link`, 기간 중복, `common_pool_key_conflict`, 브랜드 선택지 참조. 공통 구조를 보류하더라도 삭제 전에 동등 검증 필요 |
| 코드·방법 | `common_cd_invalid`, 그룹 고아/빈 그룹, `method_not_in_catalog`, `catalog_method_not_in_code`. 카탈로그 제거 시 두 방법 게이트와 코드 사용 뷰 수정 및 버전 대체 결정 필요 |
| 원문 근거 | evidence source orphan, 승인되지 않은 근거, subject/item 키 고아. 통합 시 조건·규칙·대상·한도별 참조와 승인 검증을 보전해야 함 |
| 형식 외 의미 | PDF 표의 행 연결, 10만원 OR 등록 유예, 정책 적용 시작일, `1인 1매`, 금액 기준의 실질 의미는 CHECK나 게이트 0행만으로 보장되지 않음. 사람의 PDF 대조와 사례 기반 검사 필요 |

`catalog_method_not_in_code`는 카탈로그→공통코드 방향이며 공통코드의 모든 항목에 카탈로그가 있다는 뜻이 아니다. `v_card_integrity_issue`는 실제 승인 전 실행할 게이트이지 물리 FK나 자동 트리거가 아니다. 0행은 현재 저장된 데이터 범위에 대해서만 의미가 있다.

## 8. GraphRAG 질문에서 역추적한 데이터

정책 데이터의 설명과 비교를 대상으로 하며 개인별 지급액을 판정하지 않는다. 그래프와 SQL 모두 동일한 확인·승인·기간 조건 및 PDF evidence를 가져야 한다.

| 질문 | 필요한 V6 경로 및 주의 |
|---|---|
| 전월 실적 없이 혜택을 받을 수 있는 카드? | `card_product`→`card_policy_version`→`card_bnft.bnft_cond_expr` 및 `rule_list[].cond_expr`→`v_card_cond_atom`; **실적 요건이 없다고 검증된 상태**와 누락/NULL을 구분. 다른 혜택 조건은 남을 수 있음 |
| 대중교통 할인율이 높은 카드? | 상품→혜택→`v_card_bnft_rule_effective`/`v_card_rule`의 `calc_method_cd`, `value_num`, `value_unit_cd`, `payout_unit_cd`→`v_card_rule_target.target_key`; 5%와 정액·마일리지·한도·조건을 구분 |
| 월 캐시백 한도가 높은 카드? | CASHBACK 혜택→`v_card_rule_pool`→`card_limit_pool`/`v_card_limit_tier`의 MONTH, KRW, `limit_num`, `cond_expr`; 공통 정책은 `v_card_common_limit`. 대상·조건·공유 범위가 다르면 단순 숫자 순위 주의 |
| 비슷한 혜택이나 제외 조건이 다른 카드? | `v_card_rule_target` 또는 대상 분류로 후보→`v_card_cond_atom`의 `cond_type_cd`, `excl_raw_txt`, `card_excl_item_id`→`card_excl_item` 및 증거. 실적 산정 제외와 혜택 적용 제외 분리 |
| 3천원과 1만원 결제에 다른 캐시백 규칙? | `rule_list[].cond_expr`의 TXN_AMT 하한·상한과 `value_num`, `rule_select_cd`, 원문 근거. ONE PICK 규칙 겹침은 선택 방식이 검증되기 전 보류 |
| 여러 혜택이 같은 월 한도를 공유? | 여러 `v_card_rule_pool` 행이 같은 `(card_id, policy_ver_id, pool_id)`를 참조→MONTH의 `card_limit_pool`·tier. 금액만 같은 서로 다른 풀은 공유가 아님 |
| ONE PICK STYLE 신규 등록 유예는? | 상품→교통 혜택→`bnft_cond_expr.branches`의 전월 실적 OR GRACE→`card_policy_evidence`→`card_source_evidence`→청크·쪽. 조건식 오류를 바로잡기 전 확정 결과로 제공 금지 |

단일 상품의 수치·조건 조회는 SQL로도 가능하다. 그래프는 여러 카드가 공유하는 한도·조건·근거와 변경 영향처럼 여러 관계를 연속 탐색하는 질문에서 장점을 시험할 수 있다. Neo4j 사용만으로 벡터 RAG보다 정확하다고 단정하지 않고 같은 자료·질문·근거 평가로 비교한다.

## 9. 제거·통합 후보와 영향

| 후보 | 제거 가능 근거 / 현 의존 | 대체·손실 및 판단 |
|---|---|---|
| `card_method_catalog.handler_key` | 실제 handler 실행이 MVP 밖이며 `src` Python에서 현 참조 미발견. 현 DDL은 NOT NULL | nullable/제거 시 컬럼 CHECK·COMMENT·DB 도구·외부 소비자 확인. handler 연결 계약을 포기하거나 후속 확장으로 옮김. **컬럼 단순화 후보**, 실행하지 않음 |
| `card_method_catalog` 전체 | 코드 자체는 `common_cd`로 표현 가능. 현재 catalog 0행 | `method_not_in_catalog`, `catalog_method_not_in_code`, `v_common_cd_usage`, 규칙 `method_ver`, 버전별 param 계약을 대체해야 함. 현재 버전 존재 검증 손실. **조건부 유지** |
| `card_doc_chunk`와 page 통합 | 현재 PAGE_V1은 1페이지 1청크 | `document_service`, repository, `card_ai_call`, `card_extr_stg`, `card_source_evidence`, OCR 승인·청크 위치, evidence 고아 게이트의 변경 필요. 분할 확장·원문 위치 이행 위험. **유지** |
| 공통 혜택 4개 테이블 | 상품별 복제로 MVP 구현 가능할 수 있음 | 공통 정책의 독립 키·버전·공유 관계·근거와 common 게이트를 대체해야 함. 실제 사례로 동일성이 입증되고 질의 요구가 확인될 때 판단. **조건부 유지** |
| `card_excl_item` | 원문 텍스트를 직접 보존해 검색 가능 | 제외 개념 ID·`excl_item_unknown`·표기 정규화 손실. 실제 비교 품질로 판단. **조건부 유지** |

## 10. 현재 유지안과 최소 변경안

| 기준 | 현재 V6 유지 | 최소 변경 검토안 |
|---|---|---|
| 구조 | 21개 테이블·기존 CHECK·게이트 유지 | 실험 결과에 따라 `handler_key` 필수성 등 실행 전용 계약만 조정; 아직 DDL 없음 |
| A7-2 | 기존 게이트에 맞는 코드·방법 계약이 필요하며 카탈로그가 비어 있음을 명시 | 카탈로그를 변경하면 게이트·뷰·버전 정책과 비교 기준이 바뀌므로 영향 분석과 별도 승인 필요 |
| 장점 | 기존 자료·추적·정합성 자산 재사용, 실측의 기준선 확보 | 실행 엔진에 종속된 불필요한 입력 부담 완화 가능 |
| 주의 | 데이터 의미와 원문이 맞는지 별도 검토 필요 | 정합성 검증을 없앤 것인지 이전한 것인지 확인해야 하며 새 설계가 더 정확하다는 보장은 없음 |

## 11. A7-2에 미치는 영향

**V6를 먼저 유지하고, 승인된 롤백 시험으로 표현력·게이트와 사람 검증 범위를 관찰**한다. 이전에 확인된 실적 OR 유예의 의미 오류, 일별 한도 근거 연결, 100/500원 규칙 선택, 1인 1매, 풀 집계 기준과 `valid_from` 미확인은 먼저 매핑안에서 해결하거나 명시적으로 보류해야 한다. 확인되지 않은 날짜·handler·기간을 채워 넣고 성공으로 보고하지 않는다.

필요하다면 격리된 예시값을 **가상값으로 명시한 구조 전용 롤백 실험**은 실제 카드의 확정 가능성 검증과 분리한다. 실제 카드 기준 시험을 위해 필요한 원문·코드·근거가 없으면 해당 항목은 진행하지 않는다. `card_method_catalog`이 비어 있어 기존 게이트를 통과하려면 코드+버전 계약을 어떻게 준비할지 결정해야 한다. 개인별 handler를 구현하라는 의미는 아니다. 테스트 시 자동 게이트가 발견한 문제와 PDF 대조에서만 발견한 문제를 따로 기록한다. 시퀀스 증가는 ROLLBACK되지 않는다.

## 12. 최종 권고와 미확인 사항

MVP에는 **상품·버전·혜택·조건·계산 수치·개별/공유 한도·원문 근거·검토 이력**이 필요하다. 개인별 거래 실행 기능과 그 필수 입력은 별도로 판단한다. 지금은 V6의 테이블 삭제를 확정하지 않고 A7-2 결과를 확보한 다음 `handler_key` 등 실행 중심 필드와 공통 정책·방법 카탈로그의 실제 사용 가치를 비교한다.

미확인: 실제 DB의 전체 DDL·함수·뷰와 파일의 전수 일치, 외부 프로그램의 `handler_key` 사용, 20종 적재 시 공통 정책 동일성 및 적용 기간, 그래프 변환 구현, 실제 비교 질의 성능·정확도, 카탈로그 파라미터 스키마 적용 계획. 확인 전의 단순화는 검증 능력을 줄일 수 있다. 이번 문서는 분석만 수행하며 DDL·DB·기존 소스를 변경하지 않았다.
