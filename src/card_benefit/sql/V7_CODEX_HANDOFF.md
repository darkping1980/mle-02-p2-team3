# 하나카드 GraphRAG V7 Codex 인계 문서

> **후속 변경(2026-11-02, TEXT 단순화):** `card_limit_pool`, `card_bnft_rule_pool`을 제거하고 혜택 설명과 한도를 `card_bnft.bnft_rule_txt`, `bnft_limit_txt`로 통합한다. 현재 DDL과 프로그램은 제거 후 구조 기준이다. 실제 DB 적용 여부와 절차는 `V7_BNFT_TEXT_SIMPLIFY_STATUS.md`를 먼저 본다. 아래의 한도 풀 설명은 이전 구조 기록이다.
>
> **후속 변경(2026-11-02):** 아래 내용은 작성 당시 기록이다. 이후 사용자 승인으로 개발 PostgreSQL은 V7으로 이관되었고, `card_bnft_rule_pool` 연결 테이블이 적용되어 현재 `db_pipeline`은 16개 테이블·210개 컬럼이다. 최종 규칙의 `pool_refs`는 제거되었다. 운영 Neo4j는 변경하지 않았다. 현재 기준 SQL은 `db_pipeline_schemaV7_draft.sql`, `db_pipeline_migration_v7_rule_pool.sql` 및 해당 롤백 SQL이다.

**작성일:** 2026-11-02. 아래 상태값은 작성 시점에 실제 파일, Git, 실제 DB, Neo4j를 읽기 전용으로 조회해 확인했다.

**가장 먼저 알아야 할 것**

1. **실제 PostgreSQL과 운영 Neo4j는 V6이다.** V7은 어디에도 적용되지 않았다.
2. **소스는 이미 V7을 향해 수정되어 커밋 `0b17489`에 들어가 있다.** Neo4j 변환·검색 코드는 V7 테이블과 V7 그래프를 읽는다. 따라서 이 코드는 지금의 실제 DB와 운영 그래프에서 동작하지 않는다.
3. **DB 설계는 끝났고 프로그램 구현(2단계)은 시작하지 않았다.** 공통 PDF 경로 A/B는 설계만 있고 코드가 없다.

**Codex가 클라우드에서 실행되면 먼저 확인할 것:** V7 DDL, 이관 SQL, 수정 코드는 커밋 `0b17489`에 있다. 그러나 **이 인계 문서와 `src/card_benefit/sql/tools/`는 작성 시점에 미커밋이다.** 저장소만 복제된 환경에는 없다. 복제 환경에서 작업한다면 HEAD가 `0b17489` 이후인지와 `src/card_benefit/sql/tools/v7_verification/README.md`가 있는지 확인하고, 없으면 작업을 멈추고 사용자에게 알린다.

---

## 1. 프로젝트 목표와 범위

하나카드 공식 상품설명서 PDF를 수집해 혜택, 조건, 한도를 추출하고 PostgreSQL과 Neo4j에 저장한 뒤 GraphRAG로 검색, 비교, 추천한다. 핵심은 **실제 PDF를 근거로 카드 혜택을 정확하게 표현하고 검색하는 것**이다.

**범위 밖:** 개인별 거래내역 수집, 캐시백 실제 정산, 과거 정책 버전 이력 관리, 계산 실행 엔진.

## 2. 현재 환경과 Git 상태

| 항목 | 값 |
|---|---|
| 브랜치 | `main` |
| HEAD | `0b17489be8a9baf04b8949819be8e58be82d5829` (`테이블 정리 및 통합`) |
| 원격 | `origin/main`과 차이 없음 (로컬 원격 참조 기준) |
| 미커밋 | `src/card_benefit/sql/V7_CODEX_HANDOFF.md`, `src/card_benefit/sql/tools/` (미추적) |

Git에 커밋되었다고 V7이 적용된 것은 아니다. **실제 DB와 운영 Neo4j는 여전히 V6이다.** 커밋 `0b17489`는 사용자가 만들었고, 아래 V7 작업 전체가 들어 있다.

**미추적 파일 (작성 시점)**

| 파일 | 내용 |
|---|---|
| `src/card_benefit/sql/V7_CODEX_HANDOFF.md` | 이 문서 |
| `src/card_benefit/sql/tools/v7_verification/` | V7 검증 도구와 README (8.1절) |

**`0b17489`에서 수정된 기존 파일**

| 파일 | 내용 |
|---|---|
| `src/card_benefit/sql/db_pipeline_schemaV6_draft.sql` | 공통코드 설명 컬럼과 COMMENT 추가 |
| `src/card_benefit/sql/db_pipeline_schemaV6_draft.dbml` | 공통코드 설명 컬럼 추가 |
| `src/card_benefit/payment_card/db_pipeline/neo4j_dry_run.py` | Card 중심 그래프 변환 |
| `src/card_benefit/payment_card/db_pipeline/neo4j_load_draft.py` | 라벨·관계 허용 목록, 기대 건수 107/198 |
| `src/card_benefit/payment_card/db_pipeline/neo4j_validation.cypher` | 고아 검사, 조건 소유자 |
| `src/card_benefit/payment_card/db_pipeline/neo4j_validation.sql` | `card_evidence_link`, 정책 조건 제거 |
| `src/card_benefit/payment_card/db_pipeline/test_neo4j_dry_run.py` | V7 구조 테스트 |
| `src/card_benefit/payment_card/db_pipeline/test_neo4j_load_draft.py` | 허용 목록 테스트 |
| `src/card_benefit/payment_card/db_pipeline_origin_search/card_graphrag.py` | `owner_cd = CARD`, `valid_from` 안내 제거 |
| `src/card_benefit/payment_card/db_pipeline_origin_search/graph_questions.cypher` | Card→Benefit 직접 경로 |
| `src/card_benefit/payment_card/db_pipeline_origin_search/neo4j_search.py` | 경로와 표시 필드 |
| `src/card_benefit/payment_card/tests/test_card_graphrag.py` | V7 조건·근거 코드 반영 |

**`0b17489`에서 추가된 파일**

| 파일 | 내용 |
|---|---|
| `src/card_benefit/sql/db_pipeline_schemaV7_draft.sql` | **V7 최종 DDL** |
| `src/card_benefit/sql/db_pipeline_schemaV7_draft.dbml` | V7 ERD 원본 |
| `src/card_benefit/sql/db_pipeline_common_code_seedV7.sql` | V7 공통코드 |
| `src/card_benefit/sql/db_pipeline_common_code_descV7.sql` | V7 공통코드 설명 |
| `src/card_benefit/sql/db_pipeline_migration_V6_to_V7.sql` | 이관 SQL |
| `src/card_benefit/sql/db_pipeline_migration_V7_to_V6_rollback.sql` | 롤백 SQL |
| `src/card_benefit/sql/db_pipeline_v7_integrity_test.sql` | 양성·음성 무결성 시험, 항상 ROLLBACK |
| `src/card_benefit/sql/db_pipeline_V7_change_report.md` | 상세 변경 보고서 |
| `src/card_benefit/sql/db_pipeline_common_code_descV6.sql` | V6 공통코드 설명 (이전 작업) |
| `src/card_benefit/payment_card/tests/test_v7_sql_files.py` | V7 SQL 파일 계약 테스트 |
| `src/data/backup/common_cd_desc_pre_20261102/` | 공통코드 설명 작업 전 백업 |

## 3. 실제 환경 상태

| 대상 | 상태 (작성 시점 조회) |
|---|---|
| PostgreSQL | **V6.** `card_policy_version`, `card_method_catalog` 있음. `card_evidence_link`, `db_pipeline_v6_backup` 없음 |
| 공통코드 | 그룹 44, 코드 162. 설명 컬럼과 204건은 실제 DB에 적용됨 |
| 샘플 데이터 | `card_id = 2` `HANA_DEBIT_ONE_PICK_STYLE`. 상품 1, 혜택 4, 한도 9, 원문 근거 31, 근거 연결 62, 조건 atom 15, 계산 규칙 6, 추출 항목 8 |
| 게이트 | `evidence_not_approved` 31건 |
| Neo4j | **V6.** 네임스페이스 `df_one_pick_style`, `df_node` 108개, `df_card_policy_version` 1개. 시험 네임스페이스는 없음 |

**V6 파일과 실제 DB의 차이:** `card_product_doc` 하나뿐이다. 실제 DB에는 `effective_from`, `effective_to_excl`, period CHECK, `card_product_doc_current_idx`, `card_product_doc_approved_check`가 이미 없다. 즉 **지금 실제 DB는 적용 근거 없이도 `APPROVED`가 가능하다.** V7이 시작일 조건만 뺀 CHECK로 복구한다.

## 4. V6 → V7 설계 변경

| 항목 | V6 파일 | V7 최종 |
|---|---:|---:|
| 테이블 | 21 | **15** |
| 컬럼 | 247 | **205** |
| 뷰 | 13 | **10** |
| 시퀀스 | 13 | **10** |
| 함수 | 10 | **8** |
| 인덱스 | 61 | **44** |
| PK / UNIQUE / CHECK | 21 / 13 / 40 | **15 / 10 / 31** |
| 공통코드 그룹 / 코드 | 44 / 162 | **41 / 154** |
| 공통코드 설명 | 204 | **193** (보류 2건 NULL) |
| 정합성 게이트 | 29 | **32** |

위 값은 V7 파일로 새 DB를 만든 카탈로그에서 집계했다.

**V7 테이블 15개:** `common_code_grp`, `common_cd`, `card_product`, `card_product_doc`, `card_bnft`, `card_limit_pool`, `card_evidence_link`, `card_source_evidence`, `card_doc`, `card_doc_page`, `card_doc_chunk`, `card_ai_run`, `card_ai_call`, `card_extr_stg`, `card_excl_item`.

### 4.1 삭제한 구조

| 테이블 | 실제 행 | 대체 |
|---|---:|---|
| `card_policy_version` | 1 | 조건은 `card_product.card_cond_expr`, 문서는 `card_product_doc` |
| `card_common_bnft` | 0 | 카드별 `card_bnft` |
| `card_common_policy_version` | 0 | 카드별 `card_bnft.rule_list`, 제공 기간은 `bnft_valid_*` |
| `card_bnft_common` | 0 | `card_product_doc` + `card_evidence_link` |
| `card_common_rule_evidence` | 0 | `card_evidence_link` |
| `card_method_catalog` | 2 (시험용) | `common_cd`의 `CALC_METHOD`, `PREDICATE_METHOD` + 방식별 필수값 게이트 |

**함께 삭제:**

- 함수 `fn_valid_doc_ref_list`, `fn_valid_limit_list`
- 뷰 `v_card_policy_doc`, `v_card_common_rule`, `v_card_common_limit`
- 시퀀스 `seq_card_policy_version`, `seq_card_common_bnft`, `seq_card_common_policy_version`
- 공통코드 `POLICY_STATUS`, `METHOD_KIND`, `METHOD_STATUS` 그룹과 `EV_ITEM.LIMIT`

**공통코드 교체:** `EV_SUBJECT.POLICY` → `CARD`, `BNFT_ORIGIN.COMMON_LINK` → `BRAND_SERVICE`. `BNFT_ORIGIN.LOCAL` 코드명은 `상품 고유 혜택`으로 변경.

### 4.2 변경한 구조

| 대상 | V6 | V7 |
|---|---|---|
| `card_product` | 조건 없음 | `card_cond_expr jsonb`, `card_cond_status_cd varchar(20) NOT NULL DEFAULT 'DRAFT'`(`ITEM_STATUS`), `fn_valid_cond_expr` CHECK |
| `card_bnft` PK | `(card_id, policy_ver_id, card_bnft_id)` | `(card_id, card_bnft_id)` |
| `card_bnft` UNIQUE | `(card_id, policy_ver_id, bnft_cd)` | `(card_id, bnft_cd)` |
| `card_bnft` 기간 | 없음 | `bnft_valid_from`, `bnft_valid_to_excl` (NULL 허용, ck_6) |
| `card_bnft_ck_5` | `COMMON_LINK`면 규칙 없음 | `BRAND_SERVICE`면 `bnft_scope_cd = BRAND` |
| `card_limit_pool` PK | `(card_id, policy_ver_id, pool_id)` | `(card_id, pool_id)` |
| `card_policy_evidence` | PK `(card_id, policy_ver_id, ev_link_id)` | **`card_evidence_link`** PK `(card_id, ev_link_id)`, natural key에서 `policy_ver_id` 제거, 대상 `CARD`, `BNFT`, `RULE`, `POOL`, `REL` |
| `card_product_doc` | 13개 컬럼 (파일 기준) | 11개 컬럼. `APPROVED`면 `applicability_basis_txt` 필수 |
| `card_extr_stg.card_id` | NOT NULL | **NULL 허용.** PK, UNIQUE, CHECK, 인덱스에 포함되지 않아 구조 영향 없음 |
| `card_bnft.card_id` | NOT NULL | **NOT NULL 유지** |
| `fn_valid_rule_list` | LOCAL, COMMON | **2인자 시그니처 유지**, `p_owner`는 `LOCAL`만 허용. `extraction_repository.sql:295`가 호출한다 |
| `v_card_bnft_rule_effective` | 상품 + 공통 규칙 | 혜택 + 규칙. 제공 기간을 내보내되 걸러내지 않음 |
| `seq_card_policy_evidence` | | `seq_card_evidence_link`로 이름 변경, 현재 값 유지 |

**참조 관계:** 물리 FK는 V6과 같이 0개다. 참조 무결성은 `v_card_integrity_issue`가 검사한다.

### 4.3 계산 방식과 버전

- 계산·판정 방식의 유효성은 `common_cd_invalid`가 검사한다. `v_common_cd_usage`에 `calc_method_cd`, `predicate_method_cd`가 포함되어 있다.
- `method_ver`, `predicate_method_ver`는 유지했다. **현재 1을 쓰는 표현 계약 버전이며 실행 엔진과 대조되지 않는다.** 버전 검증 기능으로 설명하면 안 된다.
- 삭제된 값: `param_schema`, `handler_key`, `method_status_cd`. 어디서도 쓰이지 않았다.

### 4.4 DRAFT와 CONFIRMED의 구분

| 게이트 | 의미 |
|---|---|
| `rule_method_value_missing`, `predicate_params_missing` | **확정 데이터의 무결성 위반.** 규칙·조건 또는 혜택이 `CONFIRMED` |
| `rule_method_value_pending`, `predicate_params_pending` | **확정 전 값 누락, 검토 대기** |
| `RETIRED` | 검사 안 함 |

게이트는 값을 채우지 않는다. 이관 사후 검사는 `*_missing`에서 중단하고 `*_pending`은 통과시킨다.

| 계산 방식 | 필수값 | 단위 |
|---|---|---|
| `PERCENT_OF_TXN` | `value_num` | `PERCENT`. 지급 단위 제한 없음 |
| `FIXED_PER_TXN` | `value_num` | 비율·배수만 거부. **KRW로 제한하지 않음** |
| `UNITS_PER_AMOUNT` | `value_num`, `basis_amt` | 비율·배수만 거부 |
| `MULTIPLY_EXTERNAL_POINTS` | `value_num` | `MULTIPLIER` |
| `FREE_SERVICE` | 없음 | 없음 |

판정 방식은 `EVERY_MONTH_MIN_SPEND`(`cond_min_amt`, `window_months`), `MONTH_IN`(`months`)만 검사한다. `cond_params`를 일괄 강제하지 않는다.

### 4.5 게이트 32종

`bnft_brand_opt_unknown`, `bnft_without_product`, `brand_bnft_confirmed_without_evidence`, `brand_bnft_doc_not_linked`, `brand_doc_option_conflict`, `common_cd_group_orphan`, `common_cd_invalid`, `common_code_grp_empty`, `doc_brand_opt_unknown`, `evidence_brand_opt_mismatch`, `evidence_doc_not_linked`, `evidence_item_key_missing`, `evidence_not_approved`, `evidence_source_orphan`, `evidence_subject_orphan`, `excl_item_unknown`, `local_confirmed_without_rule`, `pool_ref_orphan`, `pool_without_product`, `predicate_params_missing`, `predicate_params_pending`, `product_doc_orphan`, `product_doc_role_type_mismatch`, `product_doc_without_product`, `rel_fallback_cycle`, `rel_mutual_stored_twice`, `rel_to_bnft_orphan`, `rel_trigger_pool_orphan`, `rule_method_value_missing`, `rule_method_value_pending`, `shared_doc_bound_to_card`, `stg_card_not_linked`.

`stg_card_not_linked`는 값이 있을 때만 검사한다. **`card_extr_stg.card_id` NULL은 위반이 아니다.**

## 5. 확정된 공통 혜택 처리 방식

**공통 PDF는 한 번만 등록·파싱하고, 최종 혜택은 카드별로 등록하며, 원문 근거는 공유한다.** 새로운 공통 혜택 정책 테이블을 만들지 않는다.

```text
공통 PDF 1건
  card_doc (card_id NULL, doc_type_cd = BRAND_SERVICE)
    → card_doc_page → card_doc_chunk
    → card_ai_run → card_ai_call → card_extr_stg (card_id NULL 후보)
    → card_source_evidence E001 (1건만 저장)

카드 A: card_product_doc + card_bnft + card_limit_pool + card_evidence_link → E001
카드 B: card_product_doc + card_bnft + card_limit_pool + card_evidence_link → E001
```

### 5.1 테이블 역할

| 테이블 | 소속 | 역할 |
|---|---|---|
| `card_doc` | 문서 | 원천 PDF 1건. `card_id` NULL 가능. `doc_sha256`, `doc_cd` UNIQUE로 중복 등록 차단 |
| `card_doc_page` | 문서 | 페이지 원문 |
| `card_doc_chunk` | 문서 | 청크 |
| `card_ai_run` | 문서 | AI 실행 이력 |
| `card_ai_call` | 문서 | 호출 원 응답 |
| `card_extr_stg` | 문서 | **추출·검토 후보 저장소.** `card_id` NULL 가능 |
| `card_source_evidence` | 문서 | PDF 청크에 귀속된 독립 원문 근거 |
| `card_product` | 카드 | 상품, `brand_opt_list`, 카드 공통 조건 |
| `card_product_doc` | 카드↔문서 | 카드별 문서 연결. `doc_role_cd`, `brand_opt_cds`, 승인 상태, 적용 근거 |
| `card_bnft` | 카드 | **최종 혜택.** `card_id` 필수, 규칙은 `rule_list` |
| `card_limit_pool` | 카드 | 카드별 한도 |
| `card_evidence_link` | 카드↔근거 | 카드 항목과 `evidence_id` 연결 |

**반드시 지킬 해석**

- 공통 PDF와 AI 추출 후보는 카드 ID 없이 저장할 수 있다.
- `card_extr_stg.card_id` NULL은 **특정 카드에 연결되지 않은 후보**일 뿐이다. NULL이라는 이유로 공통 혜택으로 확정하지 않는다.
- `card_extr_stg`는 후보 저장소이며 **승인된 공통 혜택 마스터가 아니다.**
- 하나의 공통 PDF를 여러 카드가 연결할 수 있다.
- 하나의 `evidence_id`를 여러 카드 혜택이 참조한다. 원문은 복제하지 않는다.
- 카드별 혜택과 근거 연결은 각각 저장한다.
- `card_bnft`에는 추출 항목 참조가 없다. 추적 경로는 `card_evidence_link` → `card_source_evidence.card_extr_stg_id`다.

### 5.2 등록 경로

**경로 A, 신규 카드 등록**

1. 카드 상품 등록
2. 브랜드·등급·상품 정보 확인
3. 이미 파싱된 공통 PDF와 혜택 후보 검색
4. 해당 카드에 적용되는 혜택 선별
5. 카드별 혜택·조건·한도 등록
6. 기존 원문 근거 ID 연결

**경로 B, 공통 PDF 등록 또는 변경**

1. 공통 PDF 등록·파싱
2. 혜택·조건·적용 대상 추출
3. 적용 가능한 기존 카드 검색
4. 카드별 적용 가능 여부 검증
5. 카드별 혜택 INSERT / UPDATE
6. 원문 근거 연결 또는 변경

**공통 요구사항**

- 두 경로는 **같은 적용·검증 로직을 공유**한다.
- 등록 순서가 달라도 중복 혜택이 생기지 않아야 한다(멱등성).
- **공통 PDF가 연결됐다는 이유만으로 혜택을 일괄 적용하지 않는다.** 브랜드·서비스 등급과 함께 PDF에 명시된 대상 카드, 선택서비스, 제외 조건, 제공 기간을 검증한다.

**멱등성 수단:** `(card_id, bnft_cd)` UNIQUE와 `card_evidence_link` natural key를 쓴다. 이를 위해 같은 혜택은 항상 같은 `bnft_cd`가 되어야 한다. `bnft_cd`는 `varchar(80)`이다. 문서 계열과 항목 키로 안정적으로 만드는 규칙이 필요하다.

### 5.3 서비스 기간과 적용 대상의 저장 위치

| 정보 | 저장 위치 |
|---|---|
| 브랜드·등급 | `card_product.brand_opt_list`, `card_bnft.bnft_brand_opt_cds` |
| 선택서비스 유형 | `brand_opt_list[].service_type_cd` |
| 카드별 제외 | 대상 외면 등록하지 않음, 조건이면 `bnft_cond_expr`의 `BNFT_EXCL` |
| 개별·안내서 전체 기간 | `bnft_valid_from`, `bnft_valid_to_excl` |
| 월중 반복 기간 | 조건식에 원문 보존 |

- 기간 NULL은 **무기한이 아니라 미표기·미확인**이다.
- `~27.6.30`은 `bnft_valid_to_excl = 2027-07-01`로 저장한다.
- 수집 브랜드 안내서 16건의 표기: 문서 전체 기간은 `2026년 1월 1일 ~ 12월 31일` 형태이고 혜택별 기간이 문서당 최대 17건 있다.

## 6. 소스코드 상태

### 6.1 V7에 맞춰 이미 수정된 프로그램 (다시 구현하지 말 것)

| 파일 | 함수·대상 | 현재 상태 |
|---|---|---|
| `neo4j_dry_run.py` | `load_snapshot`, `build` | `card_evidence_link` 조회, Card→Benefit, Card→Pool, Card→Document, Card 조건·근거 |
| `neo4j_load_draft.py` | `NODE_LABELS`, `REL_TYPES`, `node_properties` | `df_card_policy_version`, `df_has_policy` 제거, `df_has_pool`, `df_has_document` 추가, 107/198 |
| `neo4j_validation.cypher` | `orphan_nodes`, `condition_structure` | V7 구조 |
| `neo4j_validation.sql` | `condition_structure`, `evidence_links` | V7 구조 |
| `graph_questions.cypher` | `catalog`, `list_benefits`, `benefit_context`, `benefit_conditions`, `benefit_evidence` | 정책 노드 제거 |
| `neo4j_search.py` | `STATEMENTS`, `SOURCE_FIELDS` | V7 경로 |
| `card_graphrag.py` | `condition_groups`, `find_unresolved`, `UNRESOLVED_TOPICS` | `CARD`, `valid_from` 안내 제거 |

파일 위치: `neo4j_*`는 `src/card_benefit/payment_card/db_pipeline/`, `graph_questions.cypher`, `neo4j_search.py`, `card_graphrag.py`는 `src/card_benefit/payment_card/db_pipeline_origin_search/`.

이 수정은 **V7 1차 구조(샘플 카드 1장)** 기준이다. 다중 카드와 공유 문서는 지원하지 않는다.

### 6.2 아직 V6 구조를 참조하는 프로그램

`src/card_benefit/payment_card` 아래 `.py`, `.sql`, `.cypher`에서 삭제된 테이블·컬럼을 실제로 사용하는 코드는 **없다.** 검색 결과는 제거를 확인하는 테스트와 주석뿐이다.

남아 있는 V6 표현은 주석뿐이다.

| 파일 | 내용 |
|---|---|
| `db_pipeline/extraction_schema.py:4` | 문서 설명의 `V6 공통코드` |
| `db_pipeline/extraction_service.py:392` | 문서 설명의 `V6 JSONB 계약` |
| `db_pipeline/register_service.py:37` | `정책 버전은 만들지 않는다` |

단, 6.1 프로그램은 V7을 읽으므로 **현재 V6 DB와 운영 그래프에서는 실행되지 않는다.** `document_*`, `extraction_*`, `terra_*`는 정책 테이블을 쓰지 않아 V6, V7 모두에서 SQL 호환으로 판단된다. 실제 V7 DB에서 실행해 보지는 않았다.

과거 작업 기록 `db_pipeline/*.md`, `db_pipeline_comment_v6*.sql`, `card_product_*_draft.sql`은 V6 시점 기록이므로 수정하지 않는다.

### 6.3 경로 A/B를 위해 새로 수정해야 할 프로그램

**아직 어느 것도 구현되지 않았다.**

| 파일 | 위치 | 필요한 작업 |
|---|---|---|
| `db_pipeline/document_service.py` | `:165` | `doc_type_cd="PRODUCT_GUIDE"` 고정 해제. 브랜드·약관 문서 등록 |
| `db_pipeline/register_service.py` | `RegisterService.register` | 공통 PDF 등록, 해시 중복 시 기존 문서 재사용 |
| `db_pipeline/extraction_service.py` | `:668 run`, `:674` | `card_id` 선택값으로 변경, 상품 존재 검사 분기 |
| 같은 파일 | `:700 _run_pages`, `:753 _process_chunk`, `:818 _store_page`, `:832 _store_item`, `:843` | `card_id` None 전달 |
| 같은 파일 | `:523`, `:525` | `bnft_origin_cd`, `bnft_scope_cd` 고정값. 카드 적용 단계에서 결정 |
| 같은 파일 | `:537` | `aggregation_key_cd = CARD_MEMBER` 일괄 입력. 원문 확인 없이 사실로 만들지 말 것 |
| `db_pipeline/extraction_repository.sql` | `:137`, `:152` | `CARD_ID` NULL 저장 |
| `db_pipeline/extraction_schema.py` | `:116 BenefitItem` | 대상 카드, 선택서비스, 제공 기간, 제외 카드 필드 |
| 같은 파일과 프롬프트 | `extraction_service.py:56 PROMPT_TXT` | 공통 PDF 추출 지시. 프롬프트 변경 시 `PROMPT_VER` 변경 |
| `db_pipeline/terra_main.py` | `:92` | `--card-id` 필수 해제 |
| 신규 모듈 | | 경로 A/B 공유 적용 로직, 후보 검색, 대상 검증, 멱등 등록 |
| 신규 또는 기존 등록 코드 | | `card_product` 등록 시 `brand_opt_list` 입력 흐름 |

**Neo4j와 GraphRAG**

| 파일 | 위치 | 필요한 작업 |
|---|---|---|
| `neo4j_dry_run.py` | `:16~17 CARD_ID, DOC_ID` | 고정값 제거, 다중 카드·문서 |
| 같은 파일 | `load_snapshot :71~74` | `card_doc_id` 고정 조회 변경 |
| 같은 파일 | `build`의 `one(product_doc)`, `one(document)` | 1건 가정 제거. 공유 문서·근거 노드 1개, 관계는 카드별 |
| 같은 파일 | `:114` | 모든 풀의 `aggregation_is_assumption=True` 고정 재검토 |
| 같은 파일 | 관계 처리 | REL 근거에서 멈춤. `relation_list` 투영 결정 필요 |
| `neo4j_load_draft.py` | `EXPECTED_NODES`, `EXPECTED_RELATIONSHIPS` | 고정 상수 재설계, 제공 기간 속성 |
| `neo4j_validation.sql`, `.cypher` | `card_id = 2` | 다중 카드 대조 |
| `graph_questions.cypher` | | 카드 지정, 브랜드 선택지 필터, 기준일 판정 |
| `neo4j_search.py`, `card_graphrag.py` | `list_catalog`, `benefit_context`, `find_unresolved` | 카드 구분, 제공 기간, 적용 선택지 표시 |

### 6.4 현재 구현된 기능

- PDF 등록, 페이지·청크 저장 (`document_*`, `register_service.py`, `main.py`)
- PDF 저장소 업·다운로드 (`document_storage.py`, `storage_main.py`)
- **카드 ID를 지정한** AI 추출, 정규화, 검증, staging 저장 (`extraction_*`, `terra_*`)
- 샘플 카드 1장의 그래프 변환, 적재, 대조 (`neo4j_*`)
- 샘플 카드 GraphRAG 검색과 화면 (`db_pipeline_origin_search/`)

### 6.5 구현되지 않은 기능

- 카드 ID 없는 공통 PDF 추출
- 경로 A, 경로 B, 공유 적용 로직
- **추출 항목을 `card_bnft`로 자동 등록하는 코드.** 샘플은 시험 적재로 등록했다
- 공통 PDF 혜택의 대상 카드 검증
- 근거 공유 그래프, 다중 카드 그래프
- 제공 기간 기준의 현재 혜택 판정
- AI 의미 검증 단계 (`RUN_STAGE.VERIFY`)

### 6.6 검증 여부

| 기능 | 상태 |
|---|---|
| V7 DDL, 시드, 설명으로 새 DB 생성 | **검증됨** (격리) |
| V6→V7 이관, 롤백 | **검증됨** (격리), 이관은 실제 DB 트랜잭션 후 ROLLBACK 확인 |
| 공유 문서·근거, `card_id` NULL 후보의 DB 저장 | **검증됨** (SQL 시험 데이터) |
| 그래프 변환 | **검증됨** (샘플, 최종 스키마, 메모리에서 107/198) |
| Neo4j 실제 적재와 조회 | **부분 검증.** V7 1차 스키마로만 시험 |
| 공통 PDF 그래프 공유 경로 | **미검증** |
| 경로 A/B | **미구현** |
| 실제 공통 PDF의 추출 품질 | **미검증** |
| LLM 답변 생성 | **미검증** |
| V7 실제 DB에서 추출·등록 파이프라인 실행 | **미검증** |

## 7. 검증 결과

**시험 환경과 시점을 구분해서 읽을 것.**

### 7.1 PostgreSQL 이관·롤백 (최종 스키마)

| 시험 | 환경 | 결과 |
|---|---|---|
| 이관 결과와 새 V7의 카탈로그 | PGlite 16.4, 실제 데이터 복사본, 실제 DB 형태와 V6 파일 형태 | 차이 0 |
| 공통코드·설명 | 같음 | V7 시드와 일치, 그룹 41, 코드 154, 설명 193, NULL 2 |
| 혜택 4, 한도 9, 근거 31, 연결 62 | 같음 | 의도한 변경 외 동일 |
| 조건 15, 규칙 6, 구간 9, 규칙↔한도 15 | 같음 | 뷰 결과 동일 |
| 추출 항목 8 | 같음 | 변경 없음, `card_id = 2` 유지 |
| 카드 공통 조건 | 같음 | atom 3개, 원본과 동일 |
| 롤백 | PGlite, 실제 DB 형태 | 데이터·카탈로그 차이 0, 재이관 성공 |
| 안전장치 | PGlite | 복수 정책판, 문서 누락, 공통 데이터 존재, 실행 가능 방법 계약 각각 자기 조건으로 중단. V7 전용 데이터가 있으면 롤백 중단 |
| 이관 전체 | **실제 DB 트랜잭션 후 ROLLBACK**, PostgreSQL 17.11 | 성공, 롤백 후 V6 확인 |

### 7.2 SQL 정합성

`db_pipeline_v7_integrity_test.sql`: 격리 DB의 이관본과 새 V7, 실제 DB 트랜잭션 안에서 통과했다. 게이트 29건, 거부·구조 13건, 정상 항목 오탐 없음. 샘플의 게이트는 `evidence_not_approved` 31건뿐이고 `*_missing`, `*_pending`은 0건이다.

### 7.3 Python 테스트

마지막 실행 결과 **304 통과, 13 건너뜀, 30 subtests 통과.** 대상은 `payment_card/tests`와 `db_pipeline/test_neo4j_*.py`다. 건너뛴 테스트에는 실제 DB·Neo4j가 필요한 통합 테스트가 포함된다. 이 문서 작성 중에는 재실행하지 않았다.

`run_offline_tests.py`는 카드 테스트를 포함하지 않는다. 이전 실행에서 recipe 묶음이 failures 1, errors 19로 실패했고 원인은 분석하지 않았다. 카드 V7 파일을 참조하지 않는다.

### 7.4 Neo4j 격리 시험 (V7 1차 스키마)

**공통 4개 테이블과 카탈로그를 제거하기 전 시점이다.** 그 뒤에는 Neo4j에 쓰지 않았다.

- `df_v7_test` 네임스페이스에 107노드, 198관계 적재 후 삭제
- 그래프 차이 0, 고아 0, SQL↔Cypher 조건 15, 근거 62 일치
- 운영 네임스페이스는 시험 전후 해시 동일
- 샘플 8개 질문의 조회와 근거 경로 확인. **LLM 답변은 미실행**

### 7.5 미해결 문제 (검증 통과 아님)

| 문제 | 현재 상태 |
|---|---|
| 100원·500원 캐시백 규칙의 선택 관계 | `rule_select_cd` NULL. 1만원 결제에 두 규칙이 모두 해당. 원문 근거 없이 정하지 않는다 |
| 대중교통 전월 실적과 최초 등록 유예 | `실적 AND NOT(제외) OR 유예`. 제외 NOT의 범위 미확정, 유예 날짜 자동 판정 불가 |
| PDF 표의 행·열 대응 | 값과 혜택의 표 연결은 사람 검토 필요. `월 5천원` 반복 표기의 행 연결 포함 |
| 원문 근거 31건 | 전부 `PENDING`. 승인된 것처럼 쓰지 않는다 |
| 카드별 혜택 적용 대상 검증 | 게이트는 브랜드 선택지와 문서 일치만 본다. **안내서 대상카드 표에 상품이 있는지는 DB가 판정하지 못한다** |
| 제공 기간과 개정 문서 | 기간 추출 미구현. 개정판 교체 절차 없음. `SUPERSEDED` 문서 연결을 막는 게이트 없음 |
| Neo4j 공통 PDF 공유 경로 | 미검증. 샘플에 공통 PDF 없음 |
| GraphRAG 최종 LLM 답변 | 미검증 |
| `CARD_MEMBER` | 9개 풀 모두 가정값 |
| 전월 실적 없음 표현 | ONE PICK, STYLE의 `bnft_cond_expr` NULL. 구조값이 아니라 원문 근거로만 남음 |
| 1인 1매 | `ETC`로 원문만 보존 |
| `VALUE_UNIT` | `HANAMONEY`, `WALLET_POINT` 없음. 포인트 정액은 `value_unit_cd`가 비고 `payout_unit_cd`에 단위가 남음 |
| 공통코드 보류 | `REL_TYPE.OVERRIDES`, `SERVICE_GRADE.PRESTIGE` 설명 NULL. 임의로 확정하지 않는다 |
| 혜택 폐기 표현 | `VERIFY_STATUS`에 폐기 값이 없다. 경로 B에서 원문에서 사라진 혜택을 어떻게 끝낼지 **사용자 결정 필요** |

## 8. 실행 방법

비밀값은 저장소 루트의 `.env`에 있고 이 문서에 기록하지 않는다. 필요한 키 이름은 `.env.example`을 본다.

**환경:** Windows, `uv`, `.venv`. `psql`과 `pg_dump`는 이 환경에 없어서 그동안 `psycopg`로 SQL을 실행했다.

```bash
# 프로그램 실행 (src/card_benefit 기준)
uv run python -m payment_card.db_pipeline.main --pdf "debit/파일명.pdf"
```

`--apply` 없이 실행하면 dry-run이다.

```bash
# 관련 테스트 (저장소 루트, Git Bash)
PYTHONPATH="src;src/card_benefit" DB_URL= .venv/Scripts/python -m pytest \
  src/card_benefit/payment_card/tests \
  src/card_benefit/payment_card/db_pipeline/test_neo4j_dry_run.py \
  src/card_benefit/payment_card/db_pipeline/test_neo4j_load_draft.py \
  src/card_benefit/payment_card/db_pipeline/test_neo4j_validate.py \
  -q --no-header -p no:cacheprovider
```

Windows의 `PYTHONPATH` 구분자는 `;`다. 경로가 빠지면 `No module named 'payment_card'`로 수집 단계에서 실패한다.

**새 DB 구성 순서:** `db_pipeline_schemaV7_draft.sql` → `db_pipeline_common_code_seedV7.sql` → `db_pipeline_common_code_descV7.sql`

### 8.1 보존된 검증 도구

**최종 V7 SQL 파일이 설계의 기준이다.** 도구는 검증을 재현할 뿐 그 파일을 대체하지 않는다. V7 SQL 파일을 **직접 수정 대상**으로 다룬다. 뷰를 바꾸면 DDL과 이관 SQL에 **똑같이** 반영한다. `test_v7_sql_files.py`가 일부 뷰의 일치를 검사한다.

위치: `src/card_benefit/sql/tools/v7_verification/`. 사용법은 같은 폴더의 `README.md`를 먼저 읽는다.

| 파일 | 용도 | 실제 변경 위험 | 기본 실행 |
|---|---|---|---|
| `export_live_rows.py` | 실제 행을 `.work/`로 내려받기 | 읽기 전용 | 바로 실행 |
| `catalog_dump.mjs` | SQL 파일의 메모리 DB 카탈로그 추출 | 없음 | 바로 실행 |
| `catalog_diff.py` | 실제 DB와 카탈로그 비교 | 읽기 전용 | 바로 실행 |
| `migrate_test.mjs` | 이관, 롤백, 재이관, 안전장치 시험 (메모리 DB) | 없음 | 바로 실행 |
| `live_rollback_dryrun.py` | 실제 DB 트랜잭션 후 ROLLBACK | 항상 ROLLBACK, **실행 중 테이블 잠금** | 거부, `--run-with-rollback` 필요 |
| `neo4j_isolated_test.py` | `df_v7_test` 적재·조회·삭제 | **공유 Neo4j에 쓰고 지움** | 거부, `--write-test-namespace` 필요 |
| `reference/gen_v7_reference.py` | V6→V7 변경 기록, **참고용** | 지정 폴더에만 씀 | 거부, `--out` 필수, 최종 SQL 폴더 거부 |

**사용 시 주의**

- `live_rollback_dryrun.py`와 `neo4j_isolated_test.py`는 **사용자 승인 후** 실행한다. 일상 검증은 `export_live_rows.py` + `migrate_test.mjs live`로 충분하다.
- `gen_v7_reference.py`는 구조 변경 이력을 읽는 참고용이다. 보존 시점에는 최종 V7 SQL 6개와 출력이 같았다. **V7 파일을 직접 고친 뒤에는 달라지며 그때는 V7 파일이 맞다.** 생성기 결과로 V7 파일을 덮어쓰지 않는다.
- `migrate_test.mjs`의 기대값은 현재 샘플 데이터와 V6→V7 이관을 전제로 한다. V7 파일을 바꾸면 합격 기준을 다시 확인한다.
- `neo4j_isolated_test.py`는 샘플 카드 1장 구조만 다룬다. 로더의 `--confirm` 절차를 거치지 않으므로 운영 적재에 쓰면 안 된다. 최종 스키마로 실행한 적이 없다.
- `.work/`에는 내려받은 실제 행이 저장된다. Git에서 제외되어 있고 복사하거나 공유하지 않는다.
- 실제 전환 도구는 없다. 운영 백업과 전환 절차는 9절을 따르고 사용자 승인 후 진행한다.

**재현 확인 (보존 시점):** 새 위치에서 `migrate_test.mjs live`, `catalog_diff.py`, DBML 파싱이 기존 결과와 같았고, 생성기 출력은 최종 V7 SQL 6개와 일치했다. `live_rollback_dryrun.py`와 `neo4j_isolated_test.py`는 플래그 없는 거부 동작만 확인했고 **새 위치에서 실제로 실행하지는 않았다.**

## 9. 다음 작업 계획

### 2단계: 프로그램 구현

| 순서 | 작업 | 수정 예상 파일 | 완료 기준 |
|---:|---|---|---|
| 1 | V7 DDL과 Python 호환성 확인 | 전체 SQL Mapper | 격리 V7 DB에서 mapper 실행 성공, V7 전용 문제 목록 작성 |
| 2 | SQL Mapper와 저장·조회 수정 | `document_repository.*`, `extraction_repository.*` | V7에서 기존 테스트 통과 |
| 3 | 카드 ID 없는 공통 PDF 추출 | `document_service.py`, `register_service.py`, `extraction_service.py`, `extraction_schema.py`, `terra_main.py` | 공통 PDF 1건이 `card_id` NULL로 저장, 같은 해시 재등록 시 신규 생성 없음 |
| 4 | 경로 A | 신규 모듈, 등록 코드 | 후보 중 대상 카드 혜택만 등록, 대상 외 혜택 미등록 |
| 5 | 경로 B | 신규 모듈 | 기존 카드 검색, 카드별 판정, INSERT/UPDATE |
| 6 | 공유 적용·중복 방지 | 신규 모듈 | A 후 B, B 후 A, 반복 실행 결과가 같음 |
| 7 | 근거 공유·연결 검증 | 신규 모듈, 시험 SQL | 원문 1건, 연결 N건, 게이트 신규 위반 0 |
| 8 | Neo4j 노드·관계·적재 | `neo4j_dry_run.py`, `neo4j_load_draft.py` | 공유 문서·근거 노드 1개, 다중 카드 변환 |
| 9 | Cypher·GraphRAG | `graph_questions.cypher`, `neo4j_search.py`, `card_graphrag.py`, `neo4j_validation.*` | 카드 지정, 브랜드 필터, 기간 표시 |
| 10 | 통합 테스트 | 테스트 | 기존 샘플 + 공통 PDF 1건 + 대상 카드 2장 + 대상 외 카드 1장 |

**권장 우선순위:** 1→2→3을 먼저 끝낸다. 4~7을 시작하기 전에 `bnft_cd` 규칙, 대상 카드 검증 방식, 혜택 폐기 방식을 사용자에게 확인한다.

**첫 시험 PDF 후보:** `src/card_benefit/data/raw/hana_all/common/` 아래 안내서. Mastercard World 03은 대상카드가 `JADE Classic`으로 명시되어 있고, AMEX Platinum 03에도 같은 카드가 있어 한 카드가 문서 2건을 쓰는 사례다. 실제 경로는 파일 목록으로 확인한다.

### 3단계: 통합 검증과 실제 전환

1. V7 이관 시험 재실행, 실제 DB 트랜잭션 ROLLBACK 시험
2. 실제 데이터 건수와 정합성 비교
3. Neo4j 공유 문서·근거 관계 시험 (격리 네임스페이스)
4. 실제 질문과 PDF 근거 검증, LLM 답변 포함
5. **사용자 승인 후** 운영 전환

**운영 전환 순서 (승인 후에만):**

1. 전체 테이블을 `src/data/backup/`에 백업
2. `db_pipeline_migration_V6_to_V7.sql` 실행
3. `db_pipeline_v7_integrity_test.sql`과 게이트 확인
4. Neo4j `df_one_pick_style` 삭제 후 재적재. 노드 키가 바뀌어 기존 그래프 위에 적재할 수 없다
5. `neo4j_validate` 실행

**복구:** `db_pipeline_migration_V7_to_V6_rollback.sql`. 이관이 `db_pipeline_v6_backup` 스키마에 남긴 값을 사용한다. 브랜드 혜택, 제공 기간, 카드 미연결 추출 항목이 생기면 V6에 담을 수 없어 롤백이 중단된다.

## 10. 작업 시 주의사항

- **V6 원본을 변경하지 않는다.** `0b17489`의 V6 파일에 포함된 공통코드 설명 변경도 그대로 둔다.
- **미커밋 파일을 보존한다.** 인계 문서와 `tools/`, 이후 Codex 작업분이 미커밋이므로 `git checkout`, `git stash`, `git clean`, `git reset`을 쓰지 않는다.
- **사용자 승인 없이 실제 DB에 적용하지 않는다.** 검증은 격리 DB나 항상 ROLLBACK하는 트랜잭션으로 한다.
- **운영 Neo4j를 임의로 변경하지 않는다.** `neo4j_load_draft.py --apply`를 실행하지 않는다. 시험은 격리 네임스페이스를 쓰고 끝나면 지운다.
- **사용자 지시 없이 Git 커밋과 푸시를 하지 않는다.**
- **관계없는 코드를 수정하지 않는다.** `src/recipe`, `src/common` 포함.
- **카드 혜택 수치나 조건을 임의로 만들지 않는다.** 값이 없으면 NULL 또는 미확정으로 둔다.
- **미승인 근거를 승인된 데이터로 취급하지 않는다.** `DRAFT`, `PENDING`을 임의로 올리지 않는다.
- **게이트를 지워서 통과시키지 않는다.**
- **설계 결함을 발견하면 먼저 보고한다.** 새 테이블이나 코드값을 임의로 추가하지 않는다.
- **`docs/자료조사/`와 `src/card_benefit/docs/`의 다른 AI 문서를 수정하지 않는다.** 새 문서는 경로 존재를 확인하고 쓴다.
- **접속 정보와 비밀값을 출력하거나 기록하지 않는다.**

## 11. 참고 문서

| 문서 | 내용 |
|---|---|
| `src/card_benefit/sql/db_pipeline_V7_change_report.md` | V7 상세 변경, 게이트 대조, 공통 혜택 대체 설계, 2단계 목록 |
| `src/card_benefit/payment_card/db_pipeline/ONE_PICK_STYLE_V6_MAPPING_REVIEW.md` | 샘플 카드 매핑 검토 |
| `src/card_benefit/payment_card/db_pipeline/A10_1_DATA_CORRECTION_PLAN.md` | 샘플 데이터 교정 기록, `CARD_MEMBER` 논의 |
| `src/card_benefit/payment_card/db_pipeline/NEO4J_DF_PF_DESIGN.md` | Neo4j DF 설계 (V6 시점) |
| `docs/자료조사/김병주/2026-10-31/카드혜택_적용규칙_데이터모델_설계결정안.md` | 계산 방식별 값 의미, 조건식 규칙 |
