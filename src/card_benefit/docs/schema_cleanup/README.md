# 계산 구조 정리 기록 (2026-11-03)

## 1. 목적과 원칙

이 프로젝트는 고객 실적을 계산하거나 할인액을 산출하지 않는다. 카드 상품설명서·브랜드 안내서의 혜택을 원문 근거와 함께 추출해
GraphRAG로 검색·답변한다. 따라서 **계산 실행을 위해 설계했지만 검색·답변에 쓰이지 않는 구조**를 DB와 소스에서 제거했다.

유지 원칙: PDF·페이지 원문, BLOCK_V1 청크, 혜택명·원문 혜택 설명(`bnft_rule_txt`), 조건·제외·적용 기간의 업무 의미,
`stg_evidence_txt`와 원문 근거 연결, 브랜드·등급·상품 적용 관계, 검색 텍스트·임베딩, 공통서비스·상품 데이터, 추출 이력(V3~V5).
이름에 RULE·CONDITION이 있다는 이유로 지우지 않았다. 2차 정리(같은 날)에서 계산 방법·지급 단위·기준 금액도 저장하지 않게 했고,
값과 단위(`value_num`·`value_unit_cd`)는 GraphRAG 답변의 수치 확인·금액 구간 답변·검색 텍스트·Neo4j 조회에 쓰여 유지했다.

## 2. 적용 상태

| 대상 | 상태 |
|---|---|
| 소스(Python·SQL mapper·프롬프트·테스트) | **반영함** |
| DB DDL `sql/db_pipeline_calc_structure_cleanup.sql` | **격리 로컬 DB(PGlite)에서만 실행·검증.** 공유 Supabase DB에는 적용하지 않음 |
| V7 설계 DDL(`db_pipeline_schemaV7_draft.sql`)·DBML | 미변경(공유 DB 적용 승인 후 동기화) |
| Neo4j | 미변경(DDL 적용 후 재적재 필요) |

## 3. 객체 분류 (유지 / 삭제 / 대체)

| 분류 | 객체 | 실제 사용처(정리 전) | 사유 |
|---|---|---|---|
| 삭제 | VIEW `v_card_bnft_rule_effective` | 프로그램 사용 없음(과거 마이그레이션 SQL·테스트 문서만) | 계산 결과 출력용("정책 후보값") |
| 삭제 | FUNCTION `fn_cond_spend_bound` | `v_card_rule.spend_min_amt/max_amt_excl`만 | 실적 구간 계산 |
| 삭제 | TABLE `card_excl_item` + 인덱스 4개(PK·UQ 포함) | 정합성 게이트 `excl_item_unknown`만. 0행, "보류" | 제외 항목 사전(제외 판정 계산). 제외 조건은 `excl_raw_txt` 원문으로 유지 |
| 삭제 | COLUMN `card_extr_stg.card_excl_item_id` | 없음(값 0건) | 위 사전 참조 |
| 삭제 | COLUMN `card_bnft.rule_select_cd`, 코드 `RULE_SELECT` | GraphRAG 미확정 문구 조건(값이 모두 NULL이라 결과 동일), 상세 SQL | 규칙 선택(택일·중첩) 계산 |
| 삭제 | rule_list 키 `predicate_state_cd`, `method_ver`, `calc_params`, `rule_priority`, `pool_refs` | 추출 정규화, `fn_valid_rule_list`, GraphRAG 문맥(`calc_params`, 값 항상 NULL) | 판정 상태·계산 엔진 버전·파라미터·우선순위·한도 풀 |
| 삭제(2차) | rule_list 키 `calc_method_cd`, `payout_unit_cd`, `basis_amt`, `v_card_rule`의 같은 열 3개, 공통코드 `CALC_METHOD`(5)·`PAYOUT_UNIT`(5), `v_common_cd_usage` 가지 2개, `fn_valid_rule_list`의 `basis_amt` 검사 | `calc_method_cd`: 검색 텍스트 수치 표기와 답변 문맥만(단위로 대체, 결과 동일). `payout_unit_cd`: 실행 사용처 없음. `basis_amt`: 저장값 모두 NULL, 추출도 항상 NULL | 계산 방법·보상 지급 형태·기준 금액 분류. LLM 응답 스키마에는 추출 확인용으로 남김(저장 안 함) |
| 삭제 | 조건 atom 키 `predicate_method_cd/ver`, `cond_params`, `card_excl_item_id`, `link_role_cd` | 추출 정규화, `fn_valid_cond_expr`, `v_card_cond_atom` (값 모두 NULL) | 조건 판정(술어) 실행 |
| 삭제 | 정규화 `limit_list`(pool_key·pool_scope_cd·aggregation_key_cd 등) | 추출 정규화, 등록 근거 검증, 검토용 SQL | 한도 풀 계산. 한도는 `bnft_limit_txt` 원문으로 유지 |
| 삭제 | 공통코드 그룹 `PREDICATE_STATE`, `PREDICATE_METHOD`, `RULE_SELECT`, `LIMIT_PERIOD`, `LIMIT_UNIT`, `LIMIT_SCOPE`, `LIMIT_AGG`, `POOL_ROLE` (그룹 8, 코드 22; 2차 포함 합계 그룹 10, 코드 32) | `v_common_cd_usage` 2가지(PREDICATE_STATE·PREDICATE_METHOD·RULE_SELECT), 나머지 사용처 없음 | 위 계산 구조의 코드 |
| 삭제 | 정합성 게이트 `rule_method_value_missing/pending`, `predicate_params_missing/pending`, `excl_item_unknown` | `v_card_integrity_issue`, 등록 정합성 SQL 제외 목록 | 계산 완결성 검사 |
| 대체 | VIEW `v_card_rule` | `v_card_rule_target`, `v_card_cond_atom`, 정합성 뷰, 코드 사용처 뷰 | 계산 열 9개 제거, 값·단위·대상·조건·상태 열 유지 |
| 대체 | VIEW `v_card_cond_atom` | Neo4j 대조 SQL `condition_structure`, 정합성 뷰 | 술어·사전·역할 열 5개 제거 |
| 대체 | VIEW `v_common_cd_usage`, `v_card_integrity_issue` | 등록 정합성 검사, 문서 검증 | 삭제한 필드의 가지 제거. 나머지 게이트 결과 동일 |
| 대체 | FUNCTION `fn_valid_rule_list` | `card_bnft_ck_3`, 추출 계약 검사 SQL | 계산 방법·지급 단위·방법 버전·판정 상태 필수 제거. rule_key·상태·대상·조건식·pool_refs 불허는 유지 |
| 대체 | FUNCTION `fn_valid_cond_expr` | `card_bnft_ck_2`, `card_product` CHECK | 술어 방법 짝 검사 제거, 제외 조건은 `excl_raw_txt` 필수 |
| 대체 | 추출 계약 검사 `contract_issues` | 추출 정규화 → `stg_sql_check_cd` | 계산 방법·지급 단위·한도 풀 검사 제거. 조건 구조·키 형식 검사 유지 |
| 유지 | rule_list `value_num`, `value_unit_cd`, 코드 `VALUE_UNIT` | GraphRAG 금액 구간 답변·답변 수치 검증(`card_graphrag.py` 556·573·616행), 검색 텍스트, Neo4j `dp_bnft_rule.value_num`·hop2 조회 | 혜택 값을 설명·검증하는 정보 |
| 유지 | 실제 컬럼 `card_extr_stg.stg_normalized_item` | 공통·개별 등록 입력(정제 혜택·검증 결과·통합 정보), 검토 SQL | 등록 파이프라인. 안의 이전 키(limit_list 등)는 추출 이력으로 보존 |
| 유지 | `rule_status_cd`, `target_list`, 조건 원문·유형·금액, `relation_list`, `bnft_rule_txt`, `bnft_limit_txt` | 검색·답변·등록 | 업무 의미 |
| 유지 | 값·한도의 **숫자와 원문 대조** 검증 | 추출 검증 | 계산이 아니라 추출 오류 검출. USD 한도는 계속 검토 대상 |

## 4. 파일

| 파일 | 내용 |
|---|---|
| `sql/db_pipeline_calc_structure_cleanup.sql` | 정리 SQL(한 트랜잭션, CASCADE 없음, 사전 조건·사후 검증 포함) |
| `sql/db_pipeline_calc_structure_cleanup_rollback.sql` | 복구 SQL(정리 전 정의·JSON 원본·공통코드 행 그대로) |
| `docs/schema_cleanup/pre_cleanup_catalog.json` | 정리 전 실제 DB 뷰·함수·제약·인덱스·컬럼·코드 그룹·소유자 |
| `docs/schema_cleanup/pre_cleanup_ddl.sql` | 정리·대체 대상의 정리 전 DDL(읽기용) |
| `docs/schema_cleanup/pre_cleanup_data.json` | 정리로 바뀌는 값(card_bnft 5행 JSON, card_product 조건식 2행, 코드 그룹 8·코드 22) |
| `src/data/backup/pre_calc_cleanup_20261103/` | 전체 백업(PostgreSQL 18개 테이블 + Neo4j dp_ 그래프) |
| `docs/schema_cleanup/isolated_test_result.txt` | 격리 시험 결과(20/20, 인덱스 정의 복구 포함) |
| `docs/schema_cleanup/v7_ddl_dbml_change_proposal.md` | V7 DDL·DBML·코드 설명 SQL 변경안(미적용) |
| `docs/schema_cleanup/registration_recheck_run31.txt` | 기존 추출(run 31) 재검증 결과 |
| `docs/schema_cleanup/tools/` | SQL 생성기, 격리 시험, 재검증 스크립트 |

## 5. 소스 변경

| 파일 | 변경 |
|---|---|
| `db_pipeline/extraction_service.py` | `build_rule`·`build_cond_expr`에서 계산 키 제거(2차: `calc_method_cd`·`payout_unit_cd`·`basis_amt` 포함), `limit_list`·`rule_select_cd` 정규화 제거, `contract_issues`의 계산 방법·지급 단위·한도 풀 검사 제거(rule_key 중복 검사 추가), `strip_calc_rule`·`strip_calc_atoms` 추가, 프롬프트 13번 정리(`EXTRACT_V7`) |
| `db_pipeline/benefit_search_text.py` | 수치 표기를 계산 방법 대신 값의 단위로 결정, 표기할 수 없는 규칙은 혜택 원문 사용. 저장된 11건의 검색 텍스트와 결과 동일 |
| `db_pipeline/common_benefit_service.py` | 한도 근거 검증을 추출 원본 `limits[].limit_key` 기준으로 변경 |
| `db_pipeline/product_benefit_service.py` | 등록 시 이전 이력의 계산 키 제거(`strip_calc_rule`·`strip_calc_atoms`) |
| `db_pipeline/common_benefit_repository.sql` | 정합성 조회 제외 목록에서 삭제된 게이트 이름 제거 |
| `db_pipeline/extraction_repository.sql` | `select_merged_rules`의 판정 상태·계산 방법·지급 단위 열 제거, `select_merged_limits` 삭제, `select_run_compare`에서 `limit_list` 제거 |
| `db_pipeline/embedding_repository.sql` | `select_card_bnft_detail`에서 `rule_select_cd` 제거 |
| `db_pipeline_origin_search/card_graphrag.py` | 답변 문맥의 `calc_params`·`rule_select`·`calc_method`·`basis_amt` 제거, 규칙 2개 이상 미확정 안내 조건 단순화(결과 동일) |
| `db_pipeline_origin_search/benefit_search_service.py`, `neo4j_search.py` | `rule_select_cd`·`calc_method_cd` 참조 제거 |
| 테스트 6개 | 새 계약 기준으로 수정·추가(계산 단위 UNKNOWN 허용, 근거·수치 검증 유지, 계산 키 없음, 단위 기반 검색 텍스트·원문 대체) |

## 6. 검증 결과

| 항목 | 결과 |
|---|---|
| 1. PDF 원문·청크 유지 | 정리 SQL은 문서·페이지·청크·근거 테이블을 바꾸지 않음. 격리 시험에서 행·값 지문 동일 |
| 2. 혜택 설명·조건 원문 보존 | `bnft_rule_txt`·`bnft_limit_txt`·조건 원문·유형·금액 유지. 규칙 6건의 값·단위·대상 유지 |
| 3. 계산 단위 UNKNOWN 혜택 등록 | 새 계약에서 허용(DB 함수·추출 검사·개별 카드 INSERT 시험). 기존 run 31 응답을 새 코드로 재검증하면 등록 가능 7 → **29/53**. 근거 없음·수치 불일치·USD 한도·기간은 계속 REVIEW |
| 4. 공통서비스·개별 카드 등록 | 등록 SQL 15개가 정리 후 스키마에서 실행됨. 공통 등록 회귀(UP001 기존 5건만 통과) 유지 |
| 5. 브랜드·등급·상품 연결 | 관련 테이블·뷰(`v_card_brand_opt`) 미변경, 정합성 게이트 결과 동일 |
| 6. 임베딩·Neo4j | 새 코드로 만든 검색 텍스트가 저장된 텍스트와 11건 모두 같음(재임베딩 불필요). 공유 DB 기준 neo4j_validate: 기존 노드 200·관계 263 변경 0, SQL↔Cypher 4종 일치. 정리 후 스키마에서 Neo4j 대조 SQL 4종 실행됨 |
| 7. GraphRAG 원문 근거 답변 | 실제 Neo4j + Mock LLM 통합 테스트 12건 통과 |
| 8. 삭제 객체 참조 코드 | 실행 코드에 없음(주석·제거 키 목록·이력 호환 처리만). 남은 참조는 과거 마이그레이션 SQL, V7 설계 DDL 시험, 실제 DB용 라이브 테스트(아래 주의) |
| 회귀 테스트 | 455 통과, 1 실패(`test_answer_text::test_unresolved_tier_cannot_be_decided_in_natural_text`, 정리 전 HEAD에서도 실패). 실제 Neo4j 통합 12 통과 |

## 7. 주의 사항

- **공유 DB에 DDL을 적용하기 전에는 개별 카드 혜택 등록(card_bnft INSERT)이 실패한다.** 현재 공유 DB의 `fn_valid_rule_list`는 `method_ver`·`predicate_state_cd`를 요구하지만 새 코드는 저장하지 않는다. DDL과 소스를 함께 적용해야 한다(Stage 5 보류 중이라 현재 영향 없음).
- 이미 저장된 추출 이력의 `stg_sql_check_cd`(CONTRACT_INVALID)는 바뀌지 않는다. 29건을 실제로 등록하려면 저장된 응답을 새 코드로 다시 통합(LLM 재호출 없음)하거나 새로 추출해야 한다.
- DDL 적용 후 card_bnft JSON이 바뀌므로 Neo4j는 재적재가 필요하다(`dp_card_bnft`·`dp_bnft_rule`·조건 노드의 source_json).
- 복구 시 `card_bnft.rule_select_cd`, `card_extr_stg.card_excl_item_id`는 테이블 맨 뒤 열로 추가된다(값은 정리 전에도 모두 NULL). 시퀀스 `seq_card_excl_item`은 지우지 않았다.
- `tests/test_live_registration.py`(실제 DB 시험, 기본 skip)는 현재 공유 DB 계약에 맞춰 두었다. DDL 적용 후 새 규칙 형식으로 바꿔야 한다.
