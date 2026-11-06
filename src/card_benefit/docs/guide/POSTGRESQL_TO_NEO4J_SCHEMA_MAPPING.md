# PostgreSQL → Neo4j 스키마 매핑

## 원천 확인 기준

2026-11-06 실제 연결을 읽기 전용으로 조사했습니다. DB는 PostgreSQL `postgres`, 버전 17.11입니다. `db_pipeline`에는 20개 기본 테이블과 8개 뷰가 있으며, 모든 기본 테이블에 선언된 PK가 있습니다. PostgreSQL에 선언된 FK는 **0개**입니다. 따라서 아래의 일반 테이블 간 연결은 DDL FK가 아니라 실제 PK 행을 대조하는 명시적 컬럼 매핑이며, 원본 참조 값이 있지만 정확히 대응하는 PK 행이 없으면 변환을 실패시킵니다.

뷰는 저장된 원장 행이 아니므로 Neo4j 노드로 복제하지 않습니다. `app_log`와 `app_log_event_archive`는 실행 로그라 사용자 지시대로 제외합니다. 나머지 18개 기본 테이블은 빠짐없이 노드 또는 관계로 매핑합니다.

## 테이블별 매핑

| PostgreSQL 테이블 | PK | Neo4j 매핑 | 행 수 | 비고 |
|---|---|---|---:|---|
| `app_log` | `app_log_id` | 제외 | 131 | 운영 로그는 PostgreSQL 유지 |
| `app_log_event_archive` | `app_log_id` | 제외 | 97 | 실행 로그 아카이브 |
| `backup_card_bnft` | `(card_id, card_bnft_id)` | `dp_backup_card_bnft` 노드 | 16 | 카드로 `dp_backup_of_card` 연결 |
| `card_ai_call` | `(card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq)` | `dp_card_ai_call` 노드 | 122 | 실행 및 청크 연결 |
| `card_ai_run` | `(card_ai_run_id)` | `dp_card_ai_run` 노드 | 43 | 대상 문서 값이 매칭되면 연결 |
| `card_common` | `(card_common_id)` | `dp_card_common` 노드 | 14 | 공통 서비스 원장 |
| `card_common_bnft` | `(card_common_id, card_common_bnft_id)` | `dp_card_common_bnft` 노드 | 82 | 혜택 텍스트·JSON·임베딩 원형 유지 |
| `card_common_bnft_apply` | `(card_common_id, card_common_bnft_id, card_id)` | `dp_applies_to` 관계 | 1 | 관계 속성 `source_json`에 PK 포함 전체 행 보존 |
| `card_common_doc` | `(card_common_id, card_doc_id)` | `dp_has_document` 관계 | 19 | 공통 서비스와 문서 연결 |
| `card_doc` | `(card_doc_id)` | `dp_card_doc` 노드 | 30 | PDF 문서 원장 |
| `card_doc_chunk` | `(card_doc_id, page_no, card_doc_chunk_id)` | `dp_card_doc_chunk` 노드 | 95 | 페이지로 연결 |
| `card_doc_page` | `(card_doc_id, page_no)` | `dp_card_doc_page` 노드 | 86 | 문서로 연결 |
| `card_evidence_link` | `(card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id)` | `dp_supported_by` 관계 | 250 | 소유자·근거 연결 행의 모든 원본 컬럼 보존. `rule_key`, `ev_subject_cd` 포함 |
| `card_extr_stg` | `(card_ai_run_id, card_doc_id, page_no, card_doc_chunk_id, call_seq, card_extr_stg_id)` | `dp_card_extr_stg` 노드 | 686 | 추출 호출·카드·부모 staging 연결 |
| `card_product` | `(card_id)` | `dp_card_product` 노드 | 10 | 상품 행 전체 복제 |
| `card_product_doc` | `(card_id, card_doc_id)` | `dp_has_document` 관계 | 11 | 카드와 문서 연결 |
| `card_product_item` | `(card_id, card_product_item_id)` | `dp_card_product_item` 노드 | 51 | BENEFIT/TERMS/ANNUAL_FEE 등 원장 행 그대로, `dp_card_bnft` 대체 노드 없음 |
| `card_source_evidence` | `(card_doc_id, page_no, card_doc_chunk_id, evidence_id)` | `dp_card_source_evidence` 노드 | 2,959 | 인용문·위치 필드와 전체 원본 행 유지 |
| `common_cd` | `(common_code_grp_id, common_cd)` | `dp_common_cd` 노드 | 132 | 그룹으로 연결 |
| `common_code_grp` | `(common_code_grp_id)` | `dp_common_code_grp` 노드 | 33 | 코드 그룹 원장 |

뷰(노드로 복제하지 않음): `v_card_bnft_rel`, `v_card_brand_opt`, `v_card_cond_atom`, `v_card_integrity_issue`, `v_card_product_item_evidence`, `v_card_rule`, `v_card_rule_target`, `v_common_cd_usage`.

## PK/FK에 준하는 관계 매핑

아래는 실제 DB의 컬럼과 대상 PK를 확인해 구성한 FK 등가 연결입니다. `fk_constraint` 속성은 `inferred-columns:` 접두어를 사용해 선언 FK와 구분합니다.

| 시작 노드 | 끝 노드 | Relationship | 일치 키 |
|---|---|---|---|
| `dp_card_product` | `dp_card_product_item` | `dp_has_item` | `card_id` |
| `dp_card_common_bnft` | `dp_card_common` | `dp_belongs_to` | `card_common_id` |
| `dp_card_doc_page` | `dp_card_doc` | `dp_in_document` | `card_doc_id` |
| `dp_card_doc_chunk` | `dp_card_doc_page` | `dp_on_page` | `(card_doc_id, page_no)` |
| `dp_card_source_evidence` | `dp_card_doc_chunk` | `dp_in_chunk` | `(card_doc_id, page_no, card_doc_chunk_id)` |
| `dp_card_source_evidence` | `dp_card_extr_stg` | `dp_from_extraction` | `card_extr_stg_id` |
| `dp_card_ai_call` | `dp_card_ai_run` | `dp_called_in_run` | `card_ai_run_id` |
| `dp_card_ai_call` | `dp_card_doc_chunk` | `dp_called_on_chunk` | 문서·페이지·청크 복합키 |
| `dp_card_extr_stg` | `dp_card_product` | `dp_extracted_for_card` | `card_id` |
| `dp_card_extr_stg` | `dp_card_ai_call` | `dp_extracted_by_call` | run·문서·페이지·청크·호출순번 |
| `dp_card_extr_stg` | `dp_card_extr_stg` | `dp_child_of_candidate` | 부모 staging ID |
| `dp_card_ai_run` | `dp_card_doc` | `dp_targets_document` | `run_target_card_doc_id` |
| `dp_backup_card_bnft` | `dp_card_product` | `dp_backup_of_card` | `card_id` |
| `dp_common_cd` | `dp_common_code_grp` | `dp_code_in_group` | `common_code_grp_id` |

관계 테이블은 노드로 복제하지 않습니다. 각 Relationship은 `key`, `source_table`, `source_json`과 원본 관계 행의 비NULL 컬럼을 속성으로 가집니다. 관계의 복합 PK 역시 `source_json` 안에서 보존됩니다.

공통 혜택과 PDF 근거 사이에는 직접 링크 테이블이 없습니다. 아래 네 원천 연결이 모두 정확히 일치할 때만 `dp_supported_by`를 구성합니다: `card_common_bnft` → `card_common_doc`의 문서 → `card_extr_stg`의 성공한 최상위 `BENEFIT` 항목 및 정확히 같은 혜택명 → `card_source_evidence`의 `card_extr_stg_id`. 생성 관계의 `source_table`은 `derived:`로 시작하고 각 원천 행을 `source_json` 계보로 보존합니다. 이 관계를 단순히 이름이 비슷하다는 이유로 만들지 않습니다.

상품/공통 혜택의 근거가 같은 추출 staging 행에서 추가로 추출된 경우에도 인용을 잃지 않도록 다음 연결을 사용합니다. 직접 `card_evidence_link`로 연결된 근거 → 해당 근거의 정확한 `card_extr_stg_id` → 같은 ID의 `card_extr_stg` → 같은 staging ID를 가진 형제 `card_source_evidence`. 형제 인용은 `dp_supported_by`로 확장되며, 파생 연결 원천과 앵커 근거를 Relationship `source_json`에 보존합니다. 혜택에서 staging 행으로 가는 `dp_supported_by_extraction`은 답변 문맥에서 원본 `stg_raw_item`을 읽도록 하는 추적 경로입니다. 이는 혜택명 유사도만으로 만든 소유 관계가 아닙니다.

## 보존 정책

- 각 노드에 원래 PK의 JSON 배열 문자열인 `key`, 테이블별 라벨, `source_table`, 전체 원본 `source_json`, 원본 NULL 컬럼을 나열한 `null_columns_json`을 저장합니다.
- Neo4j 속성 형식으로 직접 저장할 수 없는 JSON/배열/복합 값은 JSON 문자열로 직렬화합니다. NULL 컬럼은 생략하고 `null_columns_json`에 기록하여 원래 NULL 여부를 보존합니다.
- `card_product_item`과 `card_common_bnft`의 벡터는 원장 임베딩만 재사용합니다. 검색 속성 `embedding`과 원본 컬럼(`item_embedding`/`bnft_embedding`)을 모두 보존합니다. 새 임베딩은 만들지 않습니다.
- 상품 혜택은 `dp_card_product_item` 한 노드에 남고, `item_data`, `rule_list`, `relation_list`, `item_cond_expr`는 JSON 원문 그대로 보존합니다. RULE/COND 파생 노드는 만들지 않습니다.

## 생성 Cypher 요약

```cypher
CREATE CONSTRAINT dp_node_key IF NOT EXISTS
FOR (n:dp_node) REQUIRE n.key IS UNIQUE;

CREATE CONSTRAINT dp_card_product_item_pk IF NOT EXISTS
FOR (n:dp_card_product_item)
REQUIRE (n.card_id, n.card_product_item_id) IS NODE KEY;

CREATE FULLTEXT INDEX dp_card_product_item_text IF NOT EXISTS
FOR (n:dp_card_product_item)
ON EACH [n.item_nm, n.item_rule_txt, n.item_limit_txt, n.item_search_txt];

MATCH (p:dp_card_product {key:$card_key}),
      (i:dp_card_product_item {key:$item_key})
MERGE (p)-[:dp_has_item {key:$relationship_key}]->(i);
```

실제 실행은 `neo4j_load_draft.py`가 테이블별 제약조건과 인덱스를 만들고 노드·관계 행을 일괄 적재합니다. 각 소스 PK와 원본 행은 `neo4j_validate.py`로 비교합니다.
