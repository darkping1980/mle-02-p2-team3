# V7 DDL·DBML 변경안 (계산 구조 정리) — 2026-11-03 반영 완료

**반영 상태(2026-11-03)**: 아래 편집을 모두 설계 파일에 반영했다. 추가로 `stg_normalized_item` 컬럼·CHECK 조건, `seq_card_excl_item`, `fn_valid_rule_list`의 `rule_priority`·`calc_params` 검사, 공통코드 seed 10그룹·32코드도 뺐다. 검증: `test_v7_sql_files.py`, PGlite로 V7 DDL+seed+설명 SQL 실행, DBML 파싱(13테이블).

공유 DB에 `sql/db_pipeline_calc_structure_cleanup.sql`을 적용할 때 함께 반영할 설계 파일 변경이다.
실제 실행 정의는 정리 SQL이 기준이며(실제 DB 정의에서 생성), 아래는 설계 파일을 같은 상태로 맞추는 편집 목록이다.
줄 번호는 2026-11-03 기준이다.

## 1. `sql/db_pipeline_schemaV7_draft.sql`

| 위치(줄) | 현재 | 변경 |
|---|---|---|
| 14~22 JSONB 계약 주석 | atom에 `predicate_method_cd`·`predicate_method_ver`·`cond_params`·`card_excl_item_id`·`link_role_cd`, rule_list에 `predicate_state_cd`·`calc_method_cd`·`method_ver`·`payout_unit_cd`·`basis_amt`·`calc_params`·`rule_priority` | atom: `atom_seq, atom_key, negate_yn, cond_type_cd, cond_basis_cd, cond_min_amt, cond_max_amt_excl, excl_raw_txt, cond_raw_txt, cond_status_cd` / rule_list: `rule_key, cond_expr, target_list, value_num, value_unit_cd, rule_status_cd` |
| 26~27 | method_ver 설명 | 삭제. "계산 방법·지급 단위·기준 금액은 저장하지 않는다(값·단위는 답변 수치 확인용 설명 값)"로 교체 |
| 145 `fn_valid_cond_expr` | `coalesce(card_excl_item_id, excl_raw_txt)` | `coalesce(excl_raw_txt, '')` |
| `fn_valid_cond_expr` 끝부분 | 술어 방법 코드·버전 짝 검사, `cond_params` 형식 검사 | 삭제 |
| `fn_valid_rule_list` | `calc_method_cd`·`payout_unit_cd` 필수, `method_ver` 숫자·1 이상, `basis_amt` 형식·음수 검사, `predicate_state_cd` 필수와 CONDITIONAL/VERIFIED_UNCONDITIONAL 검사 | 삭제. rule_key 형식·중복, `rule_status_cd` 필수, `value_num` 숫자·0 이상, `cond_expr`·`target_list` 검증, CONFIRMED 대상 필수, `pool_refs` 불허, owner=LOCAL 유지. 주석 교체 |
| 169~182 | `fn_cond_spend_bound` 정의·주석 | 삭제 |
| 542, 573 | `card_bnft.rule_select_cd` 컬럼·주석 | 삭제 |
| `card_bnft.rule_list` 주석 | '계산 규칙 목록' | '혜택 규칙 목록(값·단위·대상·조건)' |
| 858, 891 | `card_extr_stg.card_excl_item_id` 컬럼·주석 | 삭제 |
| 904~927, 975~979 | `card_excl_item` 테이블·주석·PK·UNIQUE | 삭제 |
| 373~381 | `seq_card_excl_item` | 유지 여부 결정 필요(정리 SQL은 지우지 않음). 설계에서 지우면 정리 SQL에 `DROP SEQUENCE` 추가 |
| 996, 1000, 1024 | `ix_card_excl_item_concept_key`, `ix_card_extr_stg_excl_item_key`, `ix_card_excl_item_alias_gin` | 삭제 |
| 1053~1054 등 `v_card_rule` | `spend_min_amt`, `spend_max_amt_excl`, `predicate_state_cd`, `calc_method_cd`, `method_ver`, `payout_unit_cd`, `basis_amt`, `calc_params`, `rule_priority` | 9개 열 삭제, 주석 교체 |
| 1129 등 `v_card_cond_atom` | `predicate_method_cd`, `predicate_method_ver`, `cond_params`, `card_excl_item_id`, `link_role_cd` | 5개 열 삭제, 주석 교체 |
| 1140~1150 | `v_card_bnft_rule_effective` | 삭제 |
| 1177~1178, 1240~1249 `v_common_cd_usage` | `rule_select_cd`(RULE_SELECT), `predicate_state_cd`(PREDICATE_STATE), `calc_method_cd`(CALC_METHOD), `payout_unit_cd`(PAYOUT_UNIT), atom `predicate_method_cd`(PREDICATE_METHOD) 가지 | 5개 가지 삭제. `value_unit_cd`(VALUE_UNIT) 유지 |
| 1282~1300, 1369~1380 `v_card_integrity_issue` | CTE `rule_value_gap`·`predicate_param_gap`, 게이트 `rule_method_value_*`·`predicate_params_*`·`excl_item_unknown`, atoms CTE의 5개 열 | 삭제 |

## 2. `sql/db_pipeline_common_code_descV7.sql`

공통코드 그룹 10개(`PREDICATE_STATE`, `PREDICATE_METHOD`, `RULE_SELECT`, `LIMIT_PERIOD`, `LIMIT_UNIT`, `LIMIT_SCOPE`, `LIMIT_AGG`, `POOL_ROLE`, `CALC_METHOD`, `PAYOUT_UNIT`)와 코드 32개의 설명 행(52곳)을 삭제한다. `VALUE_UNIT` 설명 중 PAYOUT_UNIT·계산 방법 언급은 "값의 단위(답변 표기용)"로 고친다.

## 3. `sql/db_pipeline_schemaV7_draft.dbml`

| 위치(줄) | 변경 |
|---|---|
| 7 `rule_list[].calc_method_cd -> common_cd (CALC_METHOD)` | `rule_list[].value_unit_cd -> common_cd (VALUE_UNIT)`로 교체 |
| 8 method_ver 설명 | 삭제 |
| 80 `rule_select_cd` | 삭제 |
| 81 `rule_list` note | '혜택 규칙 목록(값·단위·대상·조건)' |
| 256 `card_extr_stg.card_excl_item_id` | 삭제 |
| 274~ `Table db_pipeline.card_excl_item` | 삭제 |
| 306 `Ref: card_excl_item.card_excl_item_id < card_extr_stg.card_excl_item_id` | 삭제 |
| 339 TableGroup ai_parsing의 `db_pipeline.card_excl_item` | 삭제 |

## 4. 함께 맞출 문서·시험

- `payment_card/tests/test_v7_sql_files.py`, `test_rule_pool_sql.py`: V7 설계 DDL과 과거 마이그레이션 문자열을 검사한다. 설계 DDL을 바꾸면 해당 기대값을 새 정의로 갱신한다.
- `payment_card/tests/test_live_registration.py`(실제 DB, 기본 skip): 규칙 시험 데이터에서 `method_ver`·`predicate_state_cd`·`calc_method_cd`·`payout_unit_cd` 제거.
- ERD 이미지(`docs/ERD/신용카드_체크카드_V7_수정판_ERD.png`)는 DBML 반영 후 다시 생성한다.
