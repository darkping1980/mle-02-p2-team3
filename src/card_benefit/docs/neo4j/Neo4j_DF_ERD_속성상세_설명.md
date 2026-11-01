# Neo4j DF ERD — 속성 전체 표시

기준: `encore-ai-campus/mle-02-p2-team3` GitHub main의 `src/card_benefit/payment_card/db_pipeline/NEO4J_DF_PF_DESIGN.md` (4, 5, 6, 18절), `neo4j_load_draft.py`.

- DF 업무 레이블 **13종**, 인스턴스 **108개**, 관계 유형 **12종**, 관계 연결 형태 **17종**, 관계 **189개**.
- 별도 공통 식별 레이블 `df_node`는 모든 업무 노드에 함께 적용되며, 엔티티로 따로 그리지 않음.
- 모든 노드에 `namespace`, `key`, `source_json`이 있음. `df_node_key` 제약은 `(namespace, key)` 조합의 고유성을 강제.
- 각 노드 박스는 공통 속성과 문서가 열거한 **직접 저장된 개별 속성** 전체를 표시함. `source_json` 내 필드까지 펼치지는 않음.
- `df_cond_atom.min_amt`는 15건 중 6건에만 존재.
- 모든 관계에도 `namespace`, `key`, `source_json`이 있음. `df_has_atom` 관계 추가 속성은 `atom_seq`, `df_supported_by`는 `ev_link_id`, `ev_subject_cd`, `ev_item_cd`, `ev_item_key`.
- `source_json`의 중첩 필드와 PostgreSQL 테이블 컬럼은 Neo4j에서 별도 속성으로 지정되지 않은 경우 박스에 추가하지 않음.
- 노드 속성은 PK/FK가 아니라 **Neo4j 속성**임. 키 유일성은 상기 제약만 강제됨.
- PF는 실제 그래프 0건으로 제외.
- 원본 설계 문서 기준 그림이며 Neo4j 서버를 현재 시점에 직접 조회하지 않음.

## 관계 형태 및 건수

| 시작 노드 | 관계 유형 | 끝 노드 | 건수 |
|---|---|---|---:|
| `df_card_product` | `df_has_policy` | `df_card_policy_version` | 1 |
| `df_card_policy_version` | `df_has_benefit` | `df_card_bnft` | 4 |
| `df_card_bnft` | `df_has_rule` | `df_bnft_rule` | 6 |
| `df_card_policy_version` | `df_has_expr` | `df_cond_expr` | 1 |
| `df_card_bnft` | `df_has_expr` | `df_cond_expr` | 2 |
| `df_bnft_rule` | `df_has_expr` | `df_cond_expr` | 5 |
| `df_cond_expr` | `df_has_branch` | `df_cond_branch` | 9 |
| `df_cond_branch` | `df_has_atom` | `df_cond_atom` | 15 |
| `df_bnft_rule` | `df_targets` | `df_rule_target` | 34 |
| `df_bnft_rule` | `df_consumes` | `df_card_limit_pool` | 15 |
| `df_card_policy_version` | `df_supported_by` | `df_card_source_evidence` | 8 |
| `df_card_bnft` | `df_supported_by` | `df_card_source_evidence` | 34 |
| `df_bnft_rule` | `df_supported_by` | `df_card_source_evidence` | 11 |
| `df_card_limit_pool` | `df_supported_by` | `df_card_source_evidence` | 9 |
| `df_card_source_evidence` | `df_in_chunk` | `df_card_doc_chunk` | 31 |
| `df_card_doc_chunk` | `df_on_page` | `df_card_doc_page` | 2 |
| `df_card_doc_page` | `df_in_document` | `df_card_doc` | 2 |

## 노드 속성

| 레이블 | 한글 | 인스턴스 | 직접 저장 속성 |
|---|---|---:|---|
| `df_card_product` | 카드 상품 | 1 | `namespace`, `key`, `source_json`, `card_id` |
| `df_card_policy_version` | 카드 정책 버전 | 1 | `namespace`, `key`, `source_json`, `card_id`, `policy_ver_id`, `valid_from_is_assumption` |
| `df_card_bnft` | 카드 혜택 | 4 | `namespace`, `key`, `source_json`, `card_id`, `policy_ver_id`, `card_bnft_id`, `name`, `verification_status` |
| `df_bnft_rule` | 혜택 계산 규칙 | 6 | `namespace`, `key`, `source_json`, `rule_key`, `value_num` |
| `df_cond_expr` | 조건식 | 8 | `namespace`, `key`, `source_json` |
| `df_cond_branch` | 조건 분기 (OR) | 9 | `namespace`, `key`, `source_json`, `branch_no` |
| `df_cond_atom` | 조건 원자 (AND / NOT) | 15 | `namespace`, `key`, `source_json`, `atom_seq`, `key_name`, `kind`, `negate`, `min_amt  [일부 6건]`, `raw_text` |
| `df_rule_target` | 규칙 적용 대상 | 19 | `namespace`, `key`, `source_json`, `target_nm` |
| `df_card_limit_pool` | 한도 풀 | 9 | `namespace`, `key`, `source_json`, `card_id`, `policy_ver_id`, `pool_id`, `period`, `unit`, `value`, `aggregation_is_assumption` |
| `df_card_source_evidence` | 원문 근거 | 31 | `namespace`, `key`, `source_json`, `evidence_id`, `page_no`, `start_pos`, `end_pos`, `approval_status` |
| `df_card_doc_chunk` | 문서 청크 | 2 | `namespace`, `key`, `source_json`, `page_no` |
| `df_card_doc_page` | 문서 페이지 | 2 | `namespace`, `key`, `source_json`, `page_no` |
| `df_card_doc` | 카드 문서 | 1 | `namespace`, `key`, `source_json` |
