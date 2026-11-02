# 카드 V6 → V7 변경 보고서

> **후속 변경:** 한도 풀 구조는 2026-11-02 TEXT 단순화로 제거 대상이 되었다. `V7_BNFT_TEXT_SIMPLIFY_STATUS.md`를 함께 본다. 아래는 해당 변경 이전의 기록이다.

**상태:** DB 설계, DDL, 이관 SQL, SQL 정합성 검증 완료. **실제 PostgreSQL과 운영 그래프는 아직 V6이다.** 실제 적용은 별도 승인 후 실행한다.

**범위:** 카드별 정책 버전 계층 제거, 공통 혜택 4개 테이블 제거, `card_method_catalog` 제거, `card_product_doc` 간소화. V6 파일과 공통코드 설명 작업 결과는 보존했다.

**2단계 대기:** 공통 혜택 구조 제거에 필요한 Python·Neo4j 프로그램 변경은 12절에 정리했고 아직 하지 않았다.

## 1. 변경 요약

```text
V6: card_product → card_policy_version → card_bnft / card_limit_pool / card_bnft_common / card_policy_evidence
                                         card_bnft_common → card_common_policy_version → card_common_bnft

V7: card_product → card_bnft / card_limit_pool / card_evidence_link
    card_product → card_product_doc → card_doc → card_doc_page → card_doc_chunk
    card_evidence_link → card_source_evidence → card_doc_chunk
```

| 항목 | V6 파일 | V7 1차 | V7 2차 | V7 최종 |
|---|---:|---:|---:|---:|
| 테이블 | 21 | 20 | 16 | **15** |
| 컬럼 | 247 | 234 | 211 | **205** |
| 뷰 | 13 | 12 | 10 | **10** |
| 시퀀스 | 13 | 12 | 10 | **10** |
| 함수 | 10 | 9 | 8 | **8** |
| 인덱스 | 61 | 56 | 45 | **44** |
| PK / UNIQUE / CHECK | 21 / 13 / 40 | 20 / 12 / 36 | 16 / 10 / 33 | **15 / 10 / 31** |
| 공통코드 그룹 / 코드 | 44 / 162 | 44 / 162 | 43 / 158 | **41 / 154** |
| 공통코드 설명 | 204 | 204 | 199 | **193** (그룹 41, 코드 152) |
| 정합성 게이트 | 29 | 29 | 30 | **32** |

설명이 11건 줄어든 이유는 삭제된 코드의 설명이기 때문이다(`POLICY_STATUS` 4건, `EV_ITEM.LIMIT` 1건, `METHOD_KIND`·`METHOD_STATUS` 6건). 33건은 구조 변경에 맞춰 고쳤고 160건은 V6과 같다. 보류 2건(`REL_TYPE.OVERRIDES`, `SERVICE_GRADE.PRESTIGE`)은 NULL 그대로다.

## 2. 변경 전후 테이블·PK

| 테이블 | V6 PK | V7 | 변경 내용 |
|---|---|---|---|
| `card_policy_version` | `(card_id, policy_ver_id)` | **삭제** | 조건은 `card_product.card_cond_expr`로 이관 |
| `card_common_bnft` | `(common_bnft_id)` | **삭제** | 0건 |
| `card_common_policy_version` | `(common_bnft_id, common_ver_id)` | **삭제** | 0건 |
| `card_bnft_common` | `(card_id, policy_ver_id, card_bnft_id, common_bnft_id, common_ver_id)` | **삭제** | 0건 |
| `card_common_rule_evidence` | `(common_bnft_id, common_ver_id, rule_key, evidence_id, ev_item_cd, ev_item_key)` | **삭제** | 0건 |
| `card_method_catalog` | `(method_kind_cd, method_cd, method_ver)` | **삭제** | 시험용 2행. 17절 참고 |
| `card_product` | `(card_id)` | 동일 | `card_cond_expr`, `card_cond_status_cd` 추가 |
| `card_product_doc` | `(card_id, card_doc_id)` | 동일 | `effective_*` 삭제, 11개 컬럼 |
| `card_bnft` | `(card_id, policy_ver_id, card_bnft_id)` | `(card_id, card_bnft_id)` | UNIQUE `(card_id, bnft_cd)`, `bnft_valid_from`, `bnft_valid_to_excl` 추가, ck_5 재설계, ck_6 추가 |
| `card_limit_pool` | `(card_id, policy_ver_id, pool_id)` | `(card_id, pool_id)` | |
| `card_policy_evidence` | `(card_id, policy_ver_id, ev_link_id)` | `card_evidence_link (card_id, ev_link_id)` | 이름 변경, `POLICY`→`CARD` |
| `card_extr_stg` | 변경 없음 | 동일 | **`card_id` NULL 허용** |
| `card_source_evidence` | `(evidence_id)` | 동일 | 변경 없음 |
| `card_doc`, `card_doc_page`, `card_doc_chunk`, `card_ai_run`, `card_ai_call` | | 동일 | 변경 없음 |

**유지:** `common_code_grp`, `common_cd`(설명 컬럼 포함), `card_excl_item`.

## 3. 삭제된 공통 정책 구조의 대체 설계

| V6 공통 구조 | V7 대체 |
|---|---|
| 공통 혜택 정체성 `card_common_bnft` | 카드별 `card_bnft` 행. `bnft_origin_cd = BRAND_SERVICE`, 브랜드는 `bnft_brand_opt_cds` → `brand_opt_list` |
| 버전별 규칙 `card_common_policy_version.rule_list` | 카드별 `card_bnft.rule_list` |
| 공통 규칙 내장 한도 `limit_list` | 카드별 `card_limit_pool` |
| 카드와 공통 정책 연결 `card_bnft_common` | `card_product_doc`(카드↔공통 PDF) + `card_evidence_link`(혜택↔근거) |
| 공통 규칙 근거 `card_common_rule_evidence` | `card_evidence_link`. 여러 카드가 같은 `evidence_id` 참조 |
| 공통 정책 적용 기간 | `card_bnft.bnft_valid_from`, `bnft_valid_to_excl` |

```text
공통 PDF 1건  card_doc (card_id NULL, doc_type_cd = BRAND_SERVICE)
  → card_doc_page → card_doc_chunk → card_ai_run → card_ai_call
  → card_extr_stg (card_id NULL = 카드 미연결 후보)
  → card_source_evidence E001 1건

카드 A: card_product_doc(BRAND_SERVICE, brand_opt_cds) + card_bnft + card_evidence_link → E001
카드 B: card_product_doc(BRAND_SERVICE, brand_opt_cds) + card_bnft + card_evidence_link → E001
```

**역할 구분:** AI 추출은 문서에 속하고 최종 혜택은 카드에 속한다.

## 4. 설계 결정

| 쟁점 | 결정 | 근거 |
|---|---|---|
| `card_extr_stg.card_id` | **NULL 허용** | 확정 사항. PK·UNIQUE·CHECK·인덱스 어디에도 포함되지 않아 구조 영향이 없다. `card_bnft.card_id`의 NOT NULL은 유지 |
| NULL의 의미 | **카드에 연결되지 않은 후보** | NULL이어도 위반이 아니고 공통 혜택 확정도 아니다. 게이트는 값이 있을 때 그 카드가 문서에 연결됐는지만 검사한다 |
| `COMMON_LINK` | **`BRAND_SERVICE`로 교체** | 공통 정책 연결이 사라져 의미가 틀려진다. 코드명도 `브랜드 공통 서비스`로 변경. `LOCAL` 코드명은 `상품 고유 혜택`으로 수정 |
| `card_bnft_ck_5` | **`BRAND_SERVICE`면 `bnft_scope_cd = BRAND`** | 기존 조건(규칙 없음)은 의미가 뒤집힌다. 브랜드 혜택이 선택지 없이 상품 전체에 붙는 것을 막는다 |
| 서비스 기간 | **`card_bnft`에 날짜 2개 추가** | 15절 참고 |
| `fn_valid_rule_list` | **2인자 시그니처 유지** | `extraction_repository.sql`이 호출한다. COMMON 분기만 제거했고 `p_owner`는 `LOCAL`만 허용 |
| 코드 삭제 | `POLICY_STATUS`, `METHOD_KIND`, `METHOD_STATUS` 그룹, `EV_ITEM.LIMIT` | 삭제된 테이블로 사용처가 없다. 다른 그룹(`BRAND`, `SERVICE_GRADE`, `SERVICE_TYPE`, `APPROVAL_STATUS`)은 사용 중이라 유지 |
| 공통 테이블 데이터 | **행이 있으면 이관 중단** | 카드별 변환 규칙이 정의되지 않아 지우지 않는다 |
| `card_cond_status_cd` | `ITEM_STATUS`, `NOT NULL DEFAULT 'DRAFT'` | 1차 결정 유지 |
| `method_ver`, `predicate_method_ver` | 유지, 표현 계약 버전 | 현재 1 고정. 어떤 실행 엔진과도 대조되지 않으며 버전 검증 기능이 아니다 |

## 5. 실제 DB와 V6 파일의 차이

전체 카탈로그를 비교했고 차이는 `card_product_doc` 하나뿐이다. `effective_*`, period CHECK, `current_idx`와 함께 **`card_product_doc_approved_check`까지 실제 DB에서 사라졌다.** 지금은 적용 근거 없이도 `APPROVED`가 가능하다. V7은 시작일 조건만 뺀 CHECK로 복구한다. 이관 SQL은 두 상태를 모두 처리한다.

## 6. 함수·시퀀스·뷰·인덱스

| 구분 | 내용 |
|---|---|
| 함수 삭제 | `fn_valid_doc_ref_list`, `fn_valid_limit_list` |
| 함수 수정 | `fn_valid_rule_list` (COMMON 분기와 `limit_list` 처리 제거) |
| 시퀀스 삭제 | `seq_card_policy_version`, `seq_card_common_bnft`, `seq_card_common_policy_version` |
| 시퀀스 이름 변경 | `seq_card_policy_evidence` → `seq_card_evidence_link` |
| 뷰 삭제 | `v_card_policy_doc`, `v_card_common_rule`, `v_card_common_limit` |
| 뷰 재정의 | `v_card_rule`, `v_card_rule_pool`, `v_card_bnft_rel`, `v_card_rule_target`, `v_card_limit_tier`, `v_card_cond_atom`, `v_card_bnft_rule_effective`, `v_common_cd_usage`, `v_card_integrity_issue` |
| 뷰 유지 | `v_card_brand_opt` |
| 인덱스 삭제 | 정책 2, 공통 5, `card_product_doc_current_idx` |

`v_card_bnft_rule_effective`는 혜택과 규칙을 합친 뷰로 단순해졌고 `bnft_origin_cd`, 제공 기간을 함께 낸다. 기간은 걸러내지 않는다. `rule_source_cd`, `common_*` 컬럼은 없어졌다.

## 7. 정합성 게이트

**검사를 지워 0건으로 만들지 않았다.** 삭제는 대상 구조가 없어진 경우만이다.

| 구분 | V6 게이트 | V7 게이트 | 사유 |
|---|---|---|---|
| 삭제 | `policy_without_product`, `policy_period_overlap` | | 정책판 없음 |
| 삭제 | `common_link_orphan`, `common_link_without_link`, `common_link_multi_approved_same_period`, `common_pool_key_conflict`, `common_evidence_subject_orphan`, `common_evidence_item_key_missing` | | 공통 테이블 없음. 근거·문서 검증은 아래 신규 게이트가 맡는다 |
| 대체 | `bnft_without_policy` | `bnft_without_product` | 상위가 카드 |
| 대체 | `pool_without_policy` | `pool_without_product` | 상위가 카드 |
| 대체 | `policy_doc_orphan` | `product_doc_orphan` | `source_doc_list` 대체 |
| 신규 | | `product_doc_without_product` | 문서 연결의 상품 존재 |
| 신규 | | `evidence_doc_not_linked` | 근거 문서가 그 카드에 연결됨 |
| 신규 | | `product_doc_role_type_mismatch` | 브랜드 역할로 다른 유형 문서를 연결 |
| 신규 | | `shared_doc_bound_to_card` | 브랜드·약관 문서가 특정 카드에 고정됨 |
| 신규 | | `brand_doc_option_conflict` | 한 공통 문서가 서로 다른 브랜드·등급·유형에 연결됨 |
| 신규 | | `brand_bnft_doc_not_linked` | 브랜드 혜택의 선택지에 문서 연결이 없음 |
| 신규 | | `brand_bnft_confirmed_without_evidence` | 근거 없는 확정 브랜드 혜택 |
| 신규 | | `evidence_brand_opt_mismatch` | 다른 브랜드 선택지 문서의 근거를 연결 |
| 신규 | | `stg_card_not_linked` | 추출 항목의 카드가 문서에 연결되지 않음. **NULL은 대상 아님** |
| 대체 | `method_not_in_catalog`, `catalog_method_not_in_code` | `rule_method_value_missing`, `rule_method_value_pending` | 코드 존재는 `common_cd_invalid`가 이미 검사. 방식별 필수값 검사로 대체 |
| 신규 | | `predicate_params_missing`, `predicate_params_pending` | 필수 파라미터가 정해진 판정 방식만 검사 |
| 수정 | `local_confirmed_without_rule` | 같음 | 모든 출처의 혜택이 규칙을 가지므로 LOCAL 제한 제거 |
| 수정 | `evidence_not_approved` | 같음 | 공통 테이블 union 제거 |

## 8. DB 정합성 시험 결과

| 8절 검증 항목 | 결과 | 근거 |
|---|---|---|
| 공통 PDF를 카드 없이 등록·추출 | **가능** | `card_doc.card_id` NULL, `card_extr_stg.card_id` NULL로 문서→청크→실행→호출→추출→근거 등록 통과 |
| 여러 카드가 한 문서 참조 | **가능** | PK `(card_id, card_doc_id)`, 카드 2장 연결 |
| 다른 카드 혜택이 같은 근거 참조 | **가능** | 연결 2행, 원문 1행. 복제 없음 |
| 카드별 PK·UNIQUE 충돌 | **없음** | 같은 `bnft_cd`를 두 카드에 등록 가능. 같은 카드 중복, 같은 근거 연결 중복은 거부 |
| 대상이 아닌 카드의 잘못된 등록 | **검출** | Mastercard 카드의 Visa 혜택과 근거를 게이트가 검출. 13절 한계 참고 |
| 공통 4개 제거 후 뷰·함수·게이트 | **정상** | 카탈로그 차이 0, 게이트 동작 확인 |
| 혜택 4, 한도 9, 근거 31, 연결 62 | **보존** | 아래 표 |

| 시험 | 환경 | 결과 |
|---|---|---|
| 이관 결과와 새 V7의 카탈로그 비교 | 격리 DB (실제 DB 형태, V6 파일 형태) | **차이 0** |
| 공통코드·설명이 V7 시드와 일치 | 격리 DB | 일치. 41 / 154 / 193, NULL 2 |
| 혜택 4, 한도 9, 근거 31, 연결 62 | 격리 DB | 의도한 변경 외 전 컬럼 동일. 제공 기간은 전부 NULL |
| 추출 항목 8 | 격리 DB | 변경 없음. `card_id` 2 유지 |
| 조건 15, 규칙 6, 구간 9, 규칙↔한도 15 | 격리 DB | 뷰 결과 동일 (삭제 컬럼 제외) |
| 카드 공통 조건 | 격리 DB | atom 3개, 원본과 동일 |
| 롤백 후 재이관 | 격리 DB | 데이터·카탈로그 차이 0, 재이관 성공 |
| 복수 정책판, 문서 누락, 공통 데이터 존재, 실행 가능 방법 계약 존재 | 격리 DB | 각각 자기 조건으로 변경 없이 중단 |
| V7 전용 데이터가 있을 때 롤백 | 격리 DB | 중단 |
| 양성·음성 무결성 시험 | 격리 DB, 실제 DB 트랜잭션 | 게이트 29건, 거부·구조 13건, 정상 항목 오탐 없음 |
| 이관 전체 실행 | **실제 DB 트랜잭션 후 ROLLBACK** | 성공. PostgreSQL 17.11, 테이블 15, 뷰 10, 게이트 31건 유지 |
| 롤백 후 실제 DB | 새 연결로 확인 | V6 그대로, 백업 스키마 없음 |
| 파일 계약·관련 테스트 | 오프라인 | 304 통과, 13 건너뜀 |
| DBML 파싱 | | 성공. 테이블 15, 컬럼 205, 관계 22 |

`evidence_not_approved` 31건은 V6과 같다. 근거 상태를 바꾸지 않았다. 격리 DB는 PostgreSQL 16.4이고 실제 17.11의 동작은 트랜잭션 실행으로 확인했다.

## 9. 공통코드 변경

| 코드 | 변경 |
|---|---|
| `EV_SUBJECT.POLICY` | `CARD`로 교체 |
| `BNFT_ORIGIN.COMMON_LINK` | `BRAND_SERVICE`로 교체 |
| `BNFT_ORIGIN.LOCAL` | 코드명만 `상품 고유 혜택`으로 수정 |
| `POLICY_STATUS` 그룹과 코드 3개 | 삭제 |
| `METHOD_KIND`, `METHOD_STATUS` 그룹과 코드 4개 | 삭제 |
| `EV_ITEM.LIMIT` | 삭제 |

## 10. Neo4j 1차 설계

Card 중심 설계와 코드는 1차 작업에 반영됐고 이번 단계에서 수정하지 않았다. 새 스키마 스냅샷으로 기존 변환 코드를 실행한 결과 107노드, 198관계, 끊어진 관계 0이다. **이번 단계에서 Neo4j에는 쓰지 않았다.**

1차의 그래프 구조, Cypher 변경, 시험 적재 결과(107/198, 차이 0, SQL↔Cypher 일치)와 GraphRAG 질문 조회 결과는 샘플 카드 기준으로 그대로 유효하다. 샘플에 공통 PDF가 없어 **공통 PDF 공유 구조의 그래프는 시험되지 않았다.**

## 11. 샘플 데이터의 남은 의미 문제

구조 변경으로 해결되지 않았고 값을 임의로 고치지 않았다.

| # | 문제 | 내용 |
|---:|---|---|
| 1 | 전월 실적 없음의 표현 | ONE PICK, STYLE의 `bnft_cond_expr`가 NULL이다. 실적 조건 없음이 구조값이 아니라 원문 근거로만 남아 있다 |
| 2 | 100원·500원 선택 | `rule_select_cd` NULL. 1만원 결제에 두 규칙이 모두 해당 |
| 3 | 원문 근거 미승인 | 31건 모두 PENDING |
| 4 | 대중교통 조건식 | 실적 AND NOT(제외) OR 유예. 제외 NOT의 범위 미확정 |
| 5 | `CARD_MEMBER` | 9개 풀 모두 가정값 |
| 6 | 1인 1매 | `ETC`로 원문만 보존 |
| 7 | 카드 공통 조건 | 제외 문구가 atom 2개에 겹쳐 있음 |

## 12. 2단계 Python·Neo4j 수정 목록

아직 수정하지 않았다.

**문서 등록과 추출**

| 파일 | 필요한 변경 |
|---|---|
| `document_service.py:165` | `doc_type_cd`가 `PRODUCT_GUIDE`로 고정. 브랜드·약관 문서를 `card_id` 없이 등록해야 한다 |
| `extraction_service.py:668~` | `run(card_doc_id, card_id)`의 `card_id`가 필수이고 상품 존재를 검사한다. 선택값으로 바꿔야 한다 |
| `extraction_service.py:832~`, `extraction_repository.sql:137,152` | `card_id` NULL 저장 |
| `extraction_service.py:523,525` | `bnft_origin_cd`, `bnft_scope_cd`가 `LOCAL`, `PRODUCT`로 고정 |
| `extraction_service.py:534` | 공통 PDF의 공유 한도 처리 확인 |
| `extraction_schema.py:116~` | 혜택 제공 기간, 적용 대상, 선택서비스 유형 추출 필드 |
| `extraction_repository.sql:295` | `fn_valid_rule_list` 호출 유지. 정리는 선택 |
| 신규 | 같은 문서의 재추출 방지. DB는 문서 해시만 막는다 |
| 신규 | 후보를 카드에 적용하는 등록 절차: `card_product_doc` 연결 → 카드별 `card_bnft` 생성 → `card_evidence_link` 연결 |

**Neo4j와 GraphRAG**

| 파일 | 필요한 변경 |
|---|---|
| `neo4j_dry_run.py:16~17, 66~74` | `CARD_ID`, `DOC_ID` 고정. 카드 여러 장과 문서 여러 건을 읽어야 한다 |
| `neo4j_dry_run.py` `build` | `one(product_doc)`, `one(document)` 가정 제거. 공유 문서·근거 노드는 1개, 관계는 카드별로 |
| `neo4j_dry_run.py:114` | 모든 풀에 `aggregation_is_assumption=True` 고정 |
| `neo4j_load_draft.py` | 기대 건수 상수, 제공 기간 속성, REL 처리 결정 |
| `neo4j_validation.sql`, `.cypher` | `card_id = 2` 고정, 다중 카드 대조 |
| `graph_questions.cypher` | 카드 지정, 브랜드 선택지 필터, 기준일로 제공 기간 판정 |
| `neo4j_search.py`, `card_graphrag.py` | 카탈로그의 카드 구분, 제공 기간과 적용 선택지 표시, 미확정 안내 |
| 테스트 | 공유 문서·근거, 기간 만료, 대상 외 카드 시나리오 |

## 13. 남은 설계 문제

| # | 문제 | 내용 | 제안 |
|---:|---|---|---|
| 1 | 대상카드 판정의 한계 | 게이트는 브랜드·선택지와 문서의 일치만 본다. 안내서 대상카드 표에 그 상품이 실제로 있는지는 DB가 판정할 수 없다. 근거는 `applicability_basis_txt`, 승인 상태, 근거 연결이다 | 2단계 등록 절차에서 대상카드 표 인용을 필수로 |
| 2 | 후보→혜택 추적 | `card_bnft`에 추출 항목 참조가 없다. `card_evidence_link` → `card_source_evidence.card_extr_stg_id`로만 추적된다 | 근거 없는 등록은 이미 확정 시 게이트로 검출. 컬럼 추가는 보류 |
| 3 | 중복 등록 방지 | UNIQUE `(card_id, bnft_cd)`가 막으려면 같은 혜택의 `bnft_cd`가 일정해야 한다 | 문서 코드와 항목 키로 만드는 규칙을 2단계에서 정의 |
| 4 | 기간 NULL | NULL은 무기한이 아니라 미표기·미확인이다. 원문이 종료일만 주면 시작일은 NULL이다 | 조회 시 미확인으로 표시. `~27.6.30`은 `2027-07-01`로 저장 |
| 5 | 월중 반복 기간 | `매월 1일~15일`은 날짜 컬럼으로 표현할 수 없다 | 조건식에 원문 보존. 판정 방식은 2단계 결정 |
| 6 | 혜택 안의 규칙별 기간 차이 | 기간은 혜택 단위다 | 규칙별로 다르면 혜택을 나눈다 |
| 7 | 문서 개정 | 같은 계열의 개정판(VP001 2023, 2026)이 있다. 이력 관리가 없으므로 새 판이 나오면 연결과 근거를 교체해야 한다. `SUPERSEDED` 문서에 연결된 혜택을 막는 게이트는 없다 | 재적재 절차 확정 후 게이트 추가 판단 |
| 8 | `brand_doc_option_conflict` 전제 | 수집 브랜드 문서 16건이 문서당 1개 조합이라는 확인에 근거한다. 예외 문서가 나오면 오탐이 된다 | 전체 적재 때 재확인 |
| 9 | 혜택 관계의 그래프 투영 | `relation_list`는 Neo4j에 없고 REL 근거가 생기면 변환이 멈춘다 | 2단계에서 결정 |
| 10 | 코드 그룹명 | `DOC_ROLE`의 이름이 `상품·정책에서 문서 역할`로 남아 있다 | 필요하면 별도 지시로 변경 |
| 11 | 포인트 정액의 입력 단위 | `VALUE_UNIT`에 `HANAMONEY`, `WALLET_POINT`가 없다. 건당 하나머니 규칙은 `value_unit_cd`를 비워 둘 수 있고 단위는 `payout_unit_cd`에 남는다 | 코드를 임의로 추가하지 않았다. 전체 적재 때 코드 보완 여부 판단 |
| 12 | 방식 등록 통제 | `common_cd`에 코드를 넣으면 유효한 방식이 된다. 새 방식의 필수값은 게이트에 직접 추가해야 검사된다 | 새 방식을 추가할 때 게이트 함께 검토 |

## 14. 실제 적용 절차 (승인 후)

**2단계 완료 전에는 실행하지 않는다.** 작업 트리의 그래프·검색 코드는 V7 기준이므로 코드, DB, 그래프를 함께 옮겨야 한다.

1. 전체 테이블을 `src/data/backup/`에 백업
2. `db_pipeline_migration_V6_to_V7.sql` 실행
3. `db_pipeline_v7_integrity_test.sql`과 게이트 확인
4. Neo4j `df_one_pick_style` 삭제 후 재적재
5. `neo4j_validate`로 전체 대조

**삭제 대상:** 테이블 6개(`card_policy_version` 1행, 공통 4개 0행, `card_method_catalog` 시험용 2행), `policy_ver_id` 컬럼 3개와 근거 연결의 1개, 함수 2개, 시퀀스 3개, 뷰 3개, 공통코드 그룹 3개와 코드 8개, Neo4j 운영 그래프 108노드 189관계.

**복구:** `db_pipeline_migration_V7_to_V6_rollback.sql`. 이관이 `db_pipeline_v6_backup` 스키마에 삭제 값을 남기고 롤백이 이를 사용한다. `policy_ver_id`는 테이블 끝 컬럼으로 복구되지만 값과 키, 제약조건은 같다. 브랜드 혜택, 제공 기간, 카드 미연결 추출 항목이 생긴 뒤에는 V6에 담을 수 없어 롤백이 중단된다.

## 15. 서비스 기간과 적용 대상

수집 브랜드 안내서 16건을 확인했다.

| 정보 | 원문 형태 | V7 저장 위치 |
|---|---|---|
| 브랜드·등급 공통서비스 | `Visa Infinite 등급 카드 소지자에게 공통으로 제공` | `bnft_scope_cd = BRAND`, `bnft_brand_opt_cds` → `brand_opt_list` (`COMMON`) |
| 상품별 선택서비스 | `상품유형 Mastercard World 03 / 대상카드 JADE Classic` | 브랜드 선택지의 `service_type_cd`, 대상 카드에만 `card_bnft` 등록 |
| 카드별 이용 제외 | 안내 문구 | 대상이면 등록 안 함, 조건이면 `bnft_cond_expr`의 `BNFT_EXCL` |
| 개별 혜택 기간 | `숙박기간: ~27.6.30` (문서당 최대 17건) | **`bnft_valid_to_excl`** |
| 안내서 전체 기간 | `2026년 1월 1일 ~ 12월 31일` | **`bnft_valid_from`, `bnft_valid_to_excl`** (개별 기간이 없는 혜택) |
| 월중 반복 조건 | `매월 1일~15일` | 조건식 |

**날짜 컬럼을 추가한 이유:** `card_bnft`, `rule_list`, `bnft_cond_expr`에는 날짜형 값이 없다. 원문을 조건 문자열로만 두면 현재 유효한 혜택을 SQL로 구분할 수 없다. 혜택 행의 속성이며 이력을 쌓는 구조가 아니다. 근거는 기존 근거 연결로 추적한다.

## 16. 결과물

| 파일 (`src/card_benefit/sql/`) | 내용 |
|---|---|
| `db_pipeline_schemaV7_draft.sql`, `.dbml` | 최종 V7 DDL, ERD 원본 |
| `db_pipeline_common_code_seedV7.sql`, `db_pipeline_common_code_descV7.sql` | V7 시드와 설명 |
| `db_pipeline_migration_V6_to_V7.sql` | 이관 SQL |
| `db_pipeline_migration_V7_to_V6_rollback.sql` | 롤백 SQL |
| `db_pipeline_v7_integrity_test.sql` | 양성·음성 무결성 시험, 항상 ROLLBACK |

`payment_card/tests/test_v7_sql_files.py`는 V7 SQL 파일 계약 검사라서 이번 변경에 맞춰 갱신했다. 그 외 Python과 Cypher 파일은 이번 단계에서 변경하지 않았다.

**새 DB 구성 순서:** DDL → seedV7 → descV7

## 17. `card_method_catalog` 제거

사용자 승인(2026-11-02)에 따라 제거했다. 실제 역할은 코드·버전 존재 확인뿐이었고 `param_schema`, `handler_key`, `method_status_cd`를 검사하거나 실행하는 곳이 없었다. 저장 행 2건은 `TEST_NOT_IMPLEMENTED` 자리표시였다. 프로그램 참조는 없다.

| 기능 | 처리 |
|---|---|
| 계산·판정 방식 코드 유효성 | 기존 `common_cd_invalid`가 검사 |
| 계산·판정 구분 | `CALC_METHOD`, `PREDICATE_METHOD` 그룹 |
| `(방식, 버전)` 존재 확인 | 제거. 버전이 1뿐이라 실효 없음 |
| 실행 핸들러, 파라미터 스키마, 실행 상태 | 제거. 실행 엔진이 없다 |
| 등록되지 않은 방식 검출 | 제거. 방식별 필수값 검사로 대체 |
| 혜택 수치, 파라미터, 조건, 대상, 한도, 근거 | **변경 없음** |

**`method_ver`, `predicate_method_ver`:** JSON 키, 검증 함수, 뷰 컬럼을 그대로 둔다. 현재 1을 쓰는 표현 계약 버전이다. 실행 엔진이나 카탈로그와 대조되지 않으므로 버전 검증 기능으로 보면 안 된다.

**방식별 필수값 (`rule_value_gap`)**

| 계산 방식 | 필수값 | 단위 검사 |
|---|---|---|
| `PERCENT_OF_TXN` | `value_num` | `value_unit_cd = PERCENT`. 지급 단위는 제한하지 않음 |
| `FIXED_PER_TXN` | `value_num` | 비율·배수만 거부. **KRW로 제한하지 않음** |
| `UNITS_PER_AMOUNT` | `value_num`, `basis_amt` | 비율·배수만 거부 |
| `MULTIPLY_EXTERNAL_POINTS` | `value_num` | `value_unit_cd = MULTIPLIER` |
| `FREE_SERVICE` | 없음 | 없음 |

**판정 방식 필수값 (`predicate_param_gap`):** `EVERY_MONTH_MIN_SPEND`는 `cond_min_amt`, `window_months`, `MONTH_IN`은 비어 있지 않은 `months`를 요구한다. 조건 전체나 다른 방식에 `cond_params`를 강제하지 않는다.

**확정 전 누락과 무결성 위반의 구분**

| 상태 | 게이트 | 의미 |
|---|---|---|
| 규칙 또는 혜택이 `CONFIRMED` | `rule_method_value_missing` | 확정 데이터의 무결성 위반 |
| 조건 또는 조건식이 `CONFIRMED` | `predicate_params_missing` | 확정 데이터의 무결성 위반 |
| 그 외 확정 전 | `rule_method_value_pending`, `predicate_params_pending` | 값 누락, 검토 대기 |
| `RETIRED` | 검사 안 함 | 폐기 항목 |

게이트는 드러내기만 하고 값을 채우지 않는다. 이관 사후 검사는 `*_missing`이면 중단하고 `*_pending`은 통과시킨다. 현재 샘플은 네 게이트 모두 0건이다.
