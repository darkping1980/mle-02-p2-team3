# Neo4j Aura 운영 스키마 (실시간 조회)

- 조회 시각: **2026-11-05T17:35:54+09:00 (KST)** / `2026-11-05T08:35:54+00:00 (UTC)`
- 데이터베이스: `6ac1f0f8`
- 전체 노드 수: **937**
- 전체 관계 수: **1,297**
- 조회 기준: Neo4j Aura에서 Python 드라이버의 읽기 라우팅 트랜잭션으로 직접 조회. 속성 값은 출력하지 않고 속성명·타입·출현 수만 기록.

## 노드 라벨 및 라벨별 노드 수

라벨은 중첩될 수 있습니다. 따라서 아래 라벨별 수의 합은 고유 전체 노드 수와 같지 않을 수 있습니다.

| 라벨 | 노드 수 |
|---|---:|
| `dp_bnft_rule` | 49 |
| `dp_card_bnft` | 34 |
| `dp_card_common` | 14 |
| `dp_card_common_bnft` | 82 |
| `dp_card_doc` | 30 |
| `dp_card_doc_chunk` | 95 |
| `dp_card_doc_page` | 86 |
| `dp_card_product` | 10 |
| `dp_card_product_item` | 51 |
| `dp_card_source_evidence` | 201 |
| `dp_cond_atom` | 117 |
| `dp_cond_branch` | 50 |
| `dp_cond_expr` | 49 |
| `dp_node` | 937 |
| `dp_rule_target` | 103 |

## 노드 속성명 및 관측 데이터 타입

타입은 실제 노드 속성값에 `valueType()`을 적용한 결과입니다. 속성의 출현 수는 해당 라벨 노드 중 그 타입의 속성을 가진 노드 수입니다. 같은 속성에 여러 타입이 관측되면 별도 행으로 표시했습니다.

### `dp_bnft_rule`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `card_bnft_id` | `STRING NOT NULL` | 49 |
| `card_id` | `INTEGER NOT NULL` | 49 |
| `key` | `STRING NOT NULL` | 49 |
| `rule_key` | `STRING NOT NULL` | 49 |
| `source_json` | `STRING NOT NULL` | 49 |
| `value_num` | `FLOAT NOT NULL` | 9 |
| `value_num` | `INTEGER NOT NULL` | 28 |

### `dp_card_bnft`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `bnft_cd` | `STRING NOT NULL` | 34 |
| `bnft_type_cd` | `STRING NOT NULL` | 34 |
| `bnft_valid_from` | `STRING NOT NULL` | 1 |
| `bnft_valid_to_excl` | `STRING NOT NULL` | 1 |
| `card_bnft_id` | `STRING NOT NULL` | 34 |
| `card_id` | `INTEGER NOT NULL` | 34 |
| `card_product_item_id` | `STRING NOT NULL` | 34 |
| `item_type_cd` | `STRING NOT NULL` | 34 |
| `key` | `STRING NOT NULL` | 34 |
| `limit_text` | `STRING NOT NULL` | 20 |
| `name` | `STRING NOT NULL` | 34 |
| `rule_text` | `STRING NOT NULL` | 33 |
| `source_json` | `STRING NOT NULL` | 34 |
| `verification_status` | `STRING NOT NULL` | 34 |

### `dp_card_common`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `brand_cd` | `STRING NOT NULL` | 14 |
| `card_common_id` | `INTEGER NOT NULL` | 14 |
| `common_cd` | `STRING NOT NULL` | 14 |
| `common_nm` | `STRING NOT NULL` | 14 |
| `key` | `STRING NOT NULL` | 14 |
| `service_grade_cd` | `STRING NOT NULL` | 14 |
| `source_json` | `STRING NOT NULL` | 14 |

### `dp_card_common_bnft`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `bnft_cd` | `STRING NOT NULL` | 82 |
| `bnft_type_cd` | `STRING NOT NULL` | 82 |
| `bnft_valid_from` | `STRING NOT NULL` | 81 |
| `bnft_valid_to_excl` | `STRING NOT NULL` | 81 |
| `card_common_bnft_id` | `STRING NOT NULL` | 82 |
| `card_common_id` | `INTEGER NOT NULL` | 82 |
| `key` | `STRING NOT NULL` | 82 |
| `limit_text` | `STRING NOT NULL` | 11 |
| `name` | `STRING NOT NULL` | 82 |
| `rule_text` | `STRING NOT NULL` | 82 |
| `service_type_cd` | `STRING NOT NULL` | 82 |
| `source_json` | `STRING NOT NULL` | 82 |

### `dp_card_doc`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `card_doc_id` | `STRING NOT NULL` | 30 |
| `doc_title` | `STRING NOT NULL` | 30 |
| `doc_type_cd` | `STRING NOT NULL` | 30 |
| `key` | `STRING NOT NULL` | 30 |
| `source_json` | `STRING NOT NULL` | 30 |

### `dp_card_doc_chunk`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `card_doc_chunk_id` | `STRING NOT NULL` | 95 |
| `card_doc_id` | `STRING NOT NULL` | 95 |
| `key` | `STRING NOT NULL` | 95 |
| `page_no` | `INTEGER NOT NULL` | 95 |
| `source_json` | `STRING NOT NULL` | 95 |

### `dp_card_doc_page`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `card_doc_id` | `STRING NOT NULL` | 86 |
| `key` | `STRING NOT NULL` | 86 |
| `page_no` | `INTEGER NOT NULL` | 86 |
| `source_json` | `STRING NOT NULL` | 86 |

### `dp_card_product`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `card_cond_status` | `STRING NOT NULL` | 10 |
| `card_id` | `INTEGER NOT NULL` | 10 |
| `card_kind_cd` | `STRING NOT NULL` | 10 |
| `key` | `STRING NOT NULL` | 10 |
| `product_cd` | `STRING NOT NULL` | 10 |
| `product_nm` | `STRING NOT NULL` | 10 |
| `source_json` | `STRING NOT NULL` | 10 |

### `dp_card_product_item`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `bnft_cd` | `STRING NOT NULL` | 34 |
| `bnft_type_cd` | `STRING NOT NULL` | 34 |
| `bnft_valid_from` | `STRING NOT NULL` | 1 |
| `bnft_valid_to_excl` | `STRING NOT NULL` | 1 |
| `card_bnft_id` | `STRING NOT NULL` | 34 |
| `card_id` | `INTEGER NOT NULL` | 51 |
| `card_product_item_id` | `STRING NOT NULL` | 51 |
| `item_cd` | `STRING NOT NULL` | 17 |
| `item_type_cd` | `STRING NOT NULL` | 51 |
| `key` | `STRING NOT NULL` | 51 |
| `limit_text` | `STRING NOT NULL` | 20 |
| `name` | `STRING NOT NULL` | 51 |
| `rule_text` | `STRING NOT NULL` | 50 |
| `source_json` | `STRING NOT NULL` | 51 |
| `verification_status` | `STRING NOT NULL` | 51 |

### `dp_card_source_evidence`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `approval_status` | `STRING NOT NULL` | 201 |
| `card_doc_chunk_id` | `STRING NOT NULL` | 201 |
| `card_doc_id` | `STRING NOT NULL` | 201 |
| `end_pos` | `INTEGER NOT NULL` | 201 |
| `evidence_id` | `STRING NOT NULL` | 201 |
| `key` | `STRING NOT NULL` | 201 |
| `page_no` | `INTEGER NOT NULL` | 201 |
| `source_json` | `STRING NOT NULL` | 201 |
| `start_pos` | `INTEGER NOT NULL` | 201 |

### `dp_cond_atom`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `atom_key` | `STRING NOT NULL` | 117 |
| `atom_seq` | `INTEGER NOT NULL` | 117 |
| `branch_no` | `INTEGER NOT NULL` | 117 |
| `excl_raw_txt` | `STRING NOT NULL` | 34 |
| `expr_key` | `STRING NOT NULL` | 117 |
| `key` | `STRING NOT NULL` | 117 |
| `key_name` | `STRING NOT NULL` | 117 |
| `kind` | `STRING NOT NULL` | 117 |
| `min_amt` | `INTEGER NOT NULL` | 39 |
| `negate` | `BOOLEAN NOT NULL` | 117 |
| `raw_text` | `STRING NOT NULL` | 117 |
| `source_json` | `STRING NOT NULL` | 117 |

### `dp_cond_branch`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `branch_no` | `INTEGER NOT NULL` | 50 |
| `expr_key` | `STRING NOT NULL` | 50 |
| `key` | `STRING NOT NULL` | 50 |
| `source_json` | `STRING NOT NULL` | 50 |

### `dp_cond_expr`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `expr_key` | `STRING NOT NULL` | 49 |
| `key` | `STRING NOT NULL` | 49 |
| `source_json` | `STRING NOT NULL` | 49 |

### `dp_node`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `approval_status` | `STRING NOT NULL` | 201 |
| `atom_key` | `STRING NOT NULL` | 117 |
| `atom_seq` | `INTEGER NOT NULL` | 117 |
| `bnft_cd` | `STRING NOT NULL` | 116 |
| `bnft_type_cd` | `STRING NOT NULL` | 116 |
| `bnft_valid_from` | `STRING NOT NULL` | 82 |
| `bnft_valid_to_excl` | `STRING NOT NULL` | 82 |
| `branch_no` | `INTEGER NOT NULL` | 167 |
| `brand_cd` | `STRING NOT NULL` | 14 |
| `card_bnft_id` | `STRING NOT NULL` | 83 |
| `card_common_bnft_id` | `STRING NOT NULL` | 82 |
| `card_common_id` | `INTEGER NOT NULL` | 96 |
| `card_cond_status` | `STRING NOT NULL` | 10 |
| `card_doc_chunk_id` | `STRING NOT NULL` | 296 |
| `card_doc_id` | `STRING NOT NULL` | 412 |
| `card_id` | `INTEGER NOT NULL` | 110 |
| `card_kind_cd` | `STRING NOT NULL` | 10 |
| `card_product_item_id` | `STRING NOT NULL` | 51 |
| `common_cd` | `STRING NOT NULL` | 14 |
| `common_nm` | `STRING NOT NULL` | 14 |
| `doc_title` | `STRING NOT NULL` | 30 |
| `doc_type_cd` | `STRING NOT NULL` | 30 |
| `end_pos` | `INTEGER NOT NULL` | 201 |
| `evidence_id` | `STRING NOT NULL` | 201 |
| `excl_raw_txt` | `STRING NOT NULL` | 34 |
| `expr_key` | `STRING NOT NULL` | 216 |
| `item_cd` | `STRING NOT NULL` | 17 |
| `item_type_cd` | `STRING NOT NULL` | 51 |
| `key` | `STRING NOT NULL` | 937 |
| `key_name` | `STRING NOT NULL` | 117 |
| `kind` | `STRING NOT NULL` | 117 |
| `limit_text` | `STRING NOT NULL` | 31 |
| `min_amt` | `INTEGER NOT NULL` | 39 |
| `name` | `STRING NOT NULL` | 133 |
| `negate` | `BOOLEAN NOT NULL` | 117 |
| `page_no` | `INTEGER NOT NULL` | 382 |
| `product_cd` | `STRING NOT NULL` | 10 |
| `product_nm` | `STRING NOT NULL` | 10 |
| `raw_text` | `STRING NOT NULL` | 117 |
| `rule_key` | `STRING NOT NULL` | 49 |
| `rule_text` | `STRING NOT NULL` | 132 |
| `service_grade_cd` | `STRING NOT NULL` | 14 |
| `service_type_cd` | `STRING NOT NULL` | 82 |
| `source_json` | `STRING NOT NULL` | 937 |
| `start_pos` | `INTEGER NOT NULL` | 201 |
| `target_key` | `STRING NOT NULL` | 103 |
| `target_nm` | `STRING NOT NULL` | 103 |
| `target_type_cd` | `STRING NOT NULL` | 103 |
| `value_num` | `FLOAT NOT NULL` | 9 |
| `value_num` | `INTEGER NOT NULL` | 28 |
| `verification_status` | `STRING NOT NULL` | 51 |

### `dp_rule_target`

| 속성명 | 실제 관측 타입 | 해당 타입 출현 수 |
|---|---|---:|
| `key` | `STRING NOT NULL` | 103 |
| `source_json` | `STRING NOT NULL` | 103 |
| `target_key` | `STRING NOT NULL` | 103 |
| `target_nm` | `STRING NOT NULL` | 103 |
| `target_type_cd` | `STRING NOT NULL` | 103 |

## 관계 타입, 시작·종료 라벨 및 건수

시작/종료 라벨은 관계 양 끝 노드가 가진 전체 라벨 목록입니다. 같은 관계 타입도 서로 다른 라벨 조합이면 행을 나눴습니다.

| 관계 타입 | 시작 노드 라벨 | 종료 노드 라벨 | 관계 수 |
|---|---|---|---:|
| `dp_belongs_to` | `dp_card_common_bnft`, `dp_node` | `dp_card_common`, `dp_node` | 82 |
| `dp_has_atom` | `dp_cond_branch`, `dp_node` | `dp_cond_atom`, `dp_node` | 117 |
| `dp_has_benefit` | `dp_card_product`, `dp_node` | `dp_card_bnft`, `dp_card_product_item`, `dp_node` | 34 |
| `dp_has_branch` | `dp_cond_expr`, `dp_node` | `dp_cond_branch`, `dp_node` | 50 |
| `dp_has_common_benefit` | `dp_card_product`, `dp_node` | `dp_card_common_bnft`, `dp_node` | 1 |
| `dp_has_document` | `dp_card_common`, `dp_node` | `dp_card_doc`, `dp_node` | 19 |
| `dp_has_document` | `dp_card_product`, `dp_node` | `dp_card_doc`, `dp_node` | 11 |
| `dp_has_expr` | `dp_bnft_rule`, `dp_node` | `dp_cond_expr`, `dp_node` | 24 |
| `dp_has_expr` | `dp_card_bnft`, `dp_card_product_item`, `dp_node` | `dp_cond_expr`, `dp_node` | 24 |
| `dp_has_expr` | `dp_card_product`, `dp_node` | `dp_cond_expr`, `dp_node` | 1 |
| `dp_has_item` | `dp_card_product`, `dp_node` | `dp_card_product_item`, `dp_node` | 17 |
| `dp_has_rule` | `dp_card_bnft`, `dp_card_product_item`, `dp_node` | `dp_bnft_rule`, `dp_node` | 49 |
| `dp_in_chunk` | `dp_card_source_evidence`, `dp_node` | `dp_card_doc_chunk`, `dp_node` | 201 |
| `dp_in_document` | `dp_card_doc_page`, `dp_node` | `dp_card_doc`, `dp_node` | 86 |
| `dp_on_page` | `dp_card_doc_chunk`, `dp_node` | `dp_card_doc_page`, `dp_node` | 95 |
| `dp_same_as` | `dp_card_bnft`, `dp_card_product_item`, `dp_node` | `dp_card_common_bnft`, `dp_node` | 1 |
| `dp_supported_by` | `dp_bnft_rule`, `dp_node` | `dp_card_source_evidence`, `dp_node` | 55 |
| `dp_supported_by` | `dp_card_bnft`, `dp_card_product_item`, `dp_node` | `dp_card_source_evidence`, `dp_node` | 154 |
| `dp_supported_by` | `dp_card_product`, `dp_node` | `dp_card_source_evidence`, `dp_node` | 9 |
| `dp_supported_by` | `dp_card_product_item`, `dp_node` | `dp_card_source_evidence`, `dp_node` | 32 |
| `dp_targets` | `dp_bnft_rule`, `dp_node` | `dp_node`, `dp_rule_target` | 235 |

## 제약조건

`SHOW CONSTRAINTS` 조회 결과입니다. 관계 제약조건도 포함해 전체 결과를 나열합니다.

| 이름 | 종류 | 대상 | 라벨/관계 타입 | 속성 |
|---|---|---|---|---|
| `dp_bnft_rule_pk` | `NODE_KEY` | NODE | `dp_bnft_rule` | `card_id`, `card_bnft_id`, `rule_key` |
| `dp_card_bnft_pk` | `NODE_KEY` | NODE | `dp_card_bnft` | `card_id`, `card_bnft_id` |
| `dp_card_common_pk` | `NODE_KEY` | NODE | `dp_card_common` | `card_common_id` |
| `dp_card_common_bnft_pk` | `NODE_KEY` | NODE | `dp_card_common_bnft` | `card_common_id`, `card_common_bnft_id` |
| `dp_card_doc_pk` | `NODE_KEY` | NODE | `dp_card_doc` | `card_doc_id` |
| `dp_card_doc_chunk_pk` | `NODE_KEY` | NODE | `dp_card_doc_chunk` | `card_doc_id`, `page_no`, `card_doc_chunk_id` |
| `dp_card_doc_page_pk` | `NODE_KEY` | NODE | `dp_card_doc_page` | `card_doc_id`, `page_no` |
| `dp_card_product_pk` | `NODE_KEY` | NODE | `dp_card_product` | `card_id` |
| `dp_card_product_item_pk` | `NODE_KEY` | NODE | `dp_card_product_item` | `card_id`, `card_product_item_id` |
| `dp_card_source_evidence_pk` | `NODE_KEY` | NODE | `dp_card_source_evidence` | `evidence_id` |
| `dp_cond_atom_pk` | `NODE_KEY` | NODE | `dp_cond_atom` | `expr_key`, `branch_no`, `atom_key` |
| `dp_cond_branch_pk` | `NODE_KEY` | NODE | `dp_cond_branch` | `expr_key`, `branch_no` |
| `dp_cond_expr_pk` | `NODE_KEY` | NODE | `dp_cond_expr` | `expr_key` |
| `dp_node_key` | `NODE_PROPERTY_UNIQUENESS` | NODE | `dp_node` | `key` |
| `dp_rule_target_pk` | `NODE_KEY` | NODE | `dp_rule_target` | `target_type_cd`, `target_key` |

## 추출 범위 및 해석

- 실제 노드: 937개, 실제 관계: 1,297개.
- 노드 라벨 15종, 관계 타입·끝점 라벨 조합 21행, 제약조건 15개.
- `source_json`을 포함한 속성 값은 조회 결과에 포함하지 않았습니다.
