# PostgreSQL → Neo4j 변환·적재 및 GraphRAG 조회 구조 정밀 감사

- 작성일: 2026-11-06
- 작성: Claude (읽기 전용 분석. 소스·DB·기존 문서 변경 없음)
- 선행 문서: [20261106_tier_value_none_typeerror.md](20261106_tier_value_none_typeerror.md) — `float(None)` 직접 원인 분석
- 대상 DB: PostgreSQL `db_pipeline`(Supabase), Neo4j DB `6ac1f0f8`
- 실행한 조회: PostgreSQL `SELECT`만(세션 `read_only=True`), Neo4j `READ_ACCESS` 세션의 `execute_read`만. 유료 LLM 호출 0건, 임베딩 호출 0건.

---

## 요약 (먼저 읽을 결론)

| 질문 | 판정 | 근거 요약 |
|---|---|---|
| `dp_card_bnft`는 과거 구조인가 | **아니다(정상 구조).** 현재 `card_product_item`의 `BENEFIT` 행을 표현하는 현행 라벨이다 | `neo4j_dry_run.load_snapshot`이 `card_product_item WHERE item_type_cd='BENEFIT'`를 예전 `card_bnft` 컬럼명 별칭으로 읽어 `dp_card_bnft` 노드를 만든다 |
| `dp_card_product_item`과의 관계 | **같은 노드에 붙는 두 번째 라벨 + 혜택이 아닌 항목 전용 노드.** 서로 다른 엔터티가 아니다 | 혜택 34개 노드는 `dp_card_bnft`+`dp_card_product_item` 두 라벨을 함께 가진다. TERMS 14·ANNUAL_FEE 3은 `dp_card_product_item`만 가진다 |
| 구형 노드·관계 잔존 | **없다.** | PG 원천으로 다시 만든 기대 그래프와 Neo4j가 노드 1,635·관계 2,702로 일치, 차이 0건(`neo4j_validate` 읽기 전용 실행) |
| 적재 누락·매핑 오류 | **확정 1건**: 혜택 노드에 `item_data`(한도 구간 `limit_tiers` 포함)가 적재되지 않는다. 그 외 값 손실 없음 | `load_snapshot`의 benefits SELECT에 `item_data`가 없다. Neo4j 혜택 노드 중 `limit_tiers` 보유 0건(PG는 2건) |
| Cypher 오조회 | **잘못 조회하는 쿼리는 없다.** 다만 검증기 자기참조, 속성 잔존 가능성 등 잠재 위험이 있다 | 라벨·관계·속성 참조가 실제 스키마와 일치. 다대다 중복 없음 |
| 10,000원·15,000원과 구간 연결 손실 위치 | **PostgreSQL 등록(정규화) 단계.** Neo4j 적재·검색 단계가 아니다 | 추출 원본 `card_extr_stg 20261105_000619`에는 `limits[l1=10000,l2=15000]`과 `r1.limit_keys=[l1]`, `r2.limit_keys=[l2]`가 있었으나 `build_rule()`/`normalize_benefit()`이 버리고 평문 `item_limit_txt`만 남겼다 |
| 직접 예외 | `tier_token()`의 `float(None)` — 금액이 없는 문장에서도 발생 | 실제 Neo4j 상세 행으로 오프라인 재현: `distorts_tier("자동납부 시 할인됩니다.")`도 `TypeError` |

---

## 1. 감사 목적과 범위

### 1.1 목적

`float(None)` 예외의 배경이 된 데이터 구조와 변환·검색 설계를 원천부터 검증한다. 특히 (1) `dp_card_bnft`와 `dp_card_product_item`이 설계 버전 혼재인지, (2) PostgreSQL → Neo4j 변환에서 값이 손실되는지, (3) 월 할인 한도와 전월 실적 구간의 연결이 어느 단계에서 끊겼는지를 판정한다.

### 1.2 범위와 방법

| 단계 | 확인 대상 | 방법 |
|---|---|---|
| 원문 | `card_doc_chunk 20261105_000173`(더 심플 하나카드 상품설명서 p1) | PG SELECT로 원문 텍스트 확인 |
| AI 추출 | `card_extr_stg`(stg_raw_item) | PG SELECT |
| 등록·정규화 | `extraction_service.py`, `product_benefit_service.py`, `benefit_review_patch.py` | 소스 정독 |
| PG 저장 | `card_product_item`, `card_evidence_link`, `card_source_evidence`, 제약·검증 함수 | 카탈로그·데이터 SELECT |
| Neo4j 변환·적재 | `neo4j_dry_run.py`, `neo4j_load_draft.py`, `neo4j_search_projection_sync.py`, `neo4j_validate.py` | 소스 정독 + `neo4j_validate` 읽기 전용 실행 |
| Neo4j 실제 상태 | 라벨·관계·제약·인덱스·속성 | 읽기 전용 Cypher |
| 검색·상세 조회 | `graph_questions.cypher`, `neo4j_search.py`, `neo4j_hybrid_search.py` | 소스 정독 + 실제 실행(임베딩 없이 키워드 채널만) |
| 답변 검증 | `card_graphrag.py` | 소스 정독 + 실제 Neo4j 상세 행으로 오프라인 재현(LLM 없음) |

임시 조회 스크립트는 프로젝트 밖 세션 임시 폴더에만 두었다. 프로젝트 파일은 이 보고서 1건만 새로 만들었다.

---

## 2. 현재 PostgreSQL 스키마 구조

2026-11-06 `information_schema` 조회 기준 `db_pipeline`에는 테이블 20개, 뷰 8개가 있다. 물리 FK는 없다(이전 확인과 동일).

### 2.1 카드·혜택 관련 핵심 테이블

| 테이블 | PK | 역할 | 행 수(11-06) |
|---|---|---|---:|
| `card_product` | `card_id` | 카드 상품 | 10 |
| `card_product_item` | `(card_id, card_product_item_id)` | 카드 상품 항목. `item_type_cd`로 BENEFIT/ANNUAL_FEE/TERMS 구분 | BENEFIT 34, TERMS 14, ANNUAL_FEE 3 |
| `backup_card_bnft` | — | 2026-11-04 전환 전 `card_bnft` 보관본(카드 2·5·6) | 16 |
| `card_common`, `card_common_bnft`, `card_common_bnft_apply` | 각 PK | 브랜드 공통서비스와 적용 카드 | 14 / 82 / 1 |
| `card_doc`, `card_doc_page`, `card_doc_chunk` | 문서 계층 PK | PDF 원문 | 30 / 86 / 95 |
| `card_source_evidence` | `evidence_id`(UNIQUE) | 원문 인용 위치 | 2,959 |
| `card_evidence_link` | 6컬럼 PK | 인용 ↔ 카드·혜택·규칙·관계·항목 연결 | 250 |
| `card_extr_stg` | — | LLM 추출 원본(`stg_raw_item` JSONB) | — |

`card_product_item` 컬럼(실제 카탈로그): `card_id, card_product_item_id, item_type_cd, item_cd, item_nm, item_subtype_cd, item_origin_cd, item_scope_cd, item_brand_opt_cds, item_cond_expr(jsonb), rule_list(jsonb), relation_list(jsonb), item_data(jsonb), verification_status_cd, item_valid_from, item_valid_to_excl, item_rule_txt, item_limit_txt, item_search_txt, item_embedding(vector), item_ref, create/update_*`.

### 2.2 JSONB 계약 (`rule_list`, `cond_expr`, `target_list`)

`fn_valid_rule_list(rule_list, 'LOCAL')`(CHECK `card_product_item_rule_ck`) 정의를 직접 조회했다.

- 규칙 키: `rule_key`(필수·고유), `rule_status_cd`(필수), `value_num`(number 또는 null, 0 이상), `cond_expr`(`fn_valid_cond_expr`), `target_list`(`fn_valid_target_list`), CONFIRMED면 target 1건 이상.
- 실제 저장된 49개 규칙의 키는 정확히 `cond_expr, rule_key, rule_status_cd, target_list, value_num, value_unit_cd` 6개뿐이다. **규칙 단위 한도 필드는 스키마에 없다.**
- `value_unit_cd` 분포: PERCENT 32, KRW 5, NULL 12.

이 구조는 2026-11-03 `sql/db_pipeline_calc_structure_cleanup.sql`의 의도된 결과다. 그 파일 머리말은 `calc_params, payout_unit_cd, basis_amt` 등 규칙 키와 공통코드 그룹 `LIMIT_PERIOD, LIMIT_UNIT, LIMIT_SCOPE, LIMIT_AGG, POOL_ROLE`을 제거하고, **"유지: value_num·value_unit_cd(답변 수치 검증·검색 텍스트·Neo4j) … bnft_rule_txt·bnft_limit_txt"** 라고 적는다. 즉 한도는 이때부터 **원문 인용 텍스트로만** 보관하도록 설계가 바뀌었다.

### 2.3 한도 구간을 구조로 담는 후속 수단: `item_data.limit_tiers`

`benefit_review_patch.py`의 보정 연산 `SET_LIMIT_TIERS`(29·48·92행)는 원문 표를 검사해 `item_data.limit_tiers`(schema `BENEFIT_V1`)를 만든다. `product_benefit_service.py` 332행은 이 값이 있으면 `item_data`에 구조로 저장하고 `item_limit_txt`를 `limit_tiers_text()`로 생성한다. 현재 이 구조를 가진 혜택은 **카드 42(카드의정석2 DAILY)의 179·180 두 건뿐**이다.

---

## 3. 현재 Neo4j 노드·관계 구조

### 3.1 라벨 조합 (실측)

| 라벨 조합 | 노드 수 | PG 원천 |
|---|---:|---|
| `dp_node, dp_card_source_evidence` | 899 | `card_source_evidence` 중 연결된 근거 + 공통 혜택 근거 |
| `dp_node, dp_cond_atom` | 117 | `cond_expr.branches[].atoms[]` |
| `dp_node, dp_rule_target` | 103 | `rule_list[].target_list[]`(카드 간 공유, `(target_type_cd,target_key)`) |
| `dp_node, dp_card_doc_chunk` | 95 | `card_doc_chunk` |
| `dp_node, dp_card_doc_page` | 86 | `card_doc_page` |
| `dp_node, dp_card_common_bnft` | 82 | `card_common_bnft` |
| `dp_node, dp_cond_branch` | 50 | `cond_expr.branches[]` |
| `dp_node, dp_cond_expr` | 49 | 카드·혜택·규칙의 `cond_expr` |
| `dp_node, dp_bnft_rule` | 49 | `rule_list[]` |
| **`dp_node, dp_card_bnft, dp_card_product_item`** | **34** | `card_product_item` (`item_type_cd='BENEFIT'`) |
| `dp_node, dp_card_doc` | 30 | `card_doc` |
| **`dp_node, dp_card_product_item`** | **17** | `card_product_item` (TERMS 14, ANNUAL_FEE 3) |
| `dp_node, dp_card_common` | 14 | `card_common` |
| `dp_node, dp_card_product` | 10 | `card_product` |

`dp_` 접두사 밖의 노드·관계는 이 DB에 없다(`outside_scope = 0`, 다른 그래프 `fp_` 0).

### 3.2 관계 (실측)

| 관계 | 건수 | 방향 |
|---|---:|---|
| `dp_supported_by` | 951 | 카드·혜택·규칙·항목·공통혜택 → 근거 |
| `dp_in_chunk` / `dp_on_page` / `dp_in_document` | 899 / 95 / 86 | 근거 → 청크 → 페이지 → 문서 |
| `dp_targets` | 235 | 규칙 → 대상 |
| `dp_has_atom` / `dp_has_branch` / `dp_has_expr` | 117 / 50 / 49 | 조건식 계층 |
| `dp_has_rule` | 49 | 혜택 → 규칙 |
| `dp_has_benefit` | 34 | 카드 → 혜택(`dp_card_bnft`) |
| `dp_has_item` | 17 | 카드 → 혜택 외 항목(TERMS·ANNUAL_FEE) |
| `dp_belongs_to` | 82 | 공통 혜택 → 공통서비스 |
| `dp_has_document` | 30 | 카드(11)·공통서비스(19) → 문서 |
| `dp_related_to` | 6 | 혜택 → 혜택(`relation_list`) |
| `dp_has_common_benefit` / `dp_same_as` | 1 / 1 | 카드 → 공통 혜택 / 혜택 → 공통 혜택 |

### 3.3 제약·인덱스

`dp_card_bnft_pk (card_id, card_bnft_id)`와 `dp_card_product_item_pk (card_id, card_product_item_id)` NODE KEY가 둘 다 있다. 혜택 노드는 두 라벨을 가지므로 두 제약을 모두 만족해야 하며, 적재기가 `card_product_item_id = card_bnft_id`를 함께 기록한다(실측 불일치 0건). 벡터 인덱스는 `dp_card_bnft_embedding`, `dp_card_common_bnft_embedding` 두 개다.

---

## 4. `dp_card_bnft`와 `dp_card_product_item`의 역할 비교

### 4.1 변환 코드 근거

`payment_card/db_pipeline/neo4j_dry_run.py`

```python
# load_snapshot (178행 부근)
"benefits": ("SELECT card_id, card_product_item_id AS card_bnft_id, item_cd AS bnft_cd, item_nm AS bnft_nm, "
             "item_subtype_cd AS bnft_type_cd, ... item_limit_txt AS bnft_limit_txt, ... "
             "FROM db_pipeline.card_product_item WHERE item_type_cd = 'BENEFIT' ..."),
"items": ("SELECT card_id, card_product_item_id, item_type_cd, ..., item_data, ... "
          "FROM db_pipeline.card_product_item WHERE item_type_cd <> 'BENEFIT' ..."),
# build
b = g.node("card_bnft", [card_id, bnft_id], row)                 # 366행
items[(card_id, item_id)] = g.node("card_product_item", ...)       # 402행
```

`payment_card/db_pipeline/neo4j_load_draft.py`

```python
extra = f", n:{ITEM_LABEL}" if label == PREFIX + "card_bnft" else ""     # 132행
... MERGE (n:{label} {pk}) SET n:dp_node{extra}, n += $props            # 133행
# node_properties: 혜택이면 card_product_item_id = card_bnft_id, item_type_cd = 'BENEFIT'
```

### 4.2 판정

| 항목 | `dp_card_bnft` | `dp_card_product_item` |
|---|---|---|
| PG 원천 | `card_product_item` BENEFIT 행 (컬럼은 예전 `card_bnft` 이름으로 별칭) | 같은 테이블의 BENEFIT 외 행 + **혜택 노드의 보조 라벨** |
| 노드 key | `["card_bnft", card_id, id]` (2026-11-04 전 key 유지) | `["card_product_item", card_id, id]` (TERMS·연회비) |
| 카드 연결 | `dp_has_benefit` | `dp_has_item` (혜택 노드에는 없음) |
| 하위 구조 | 규칙·조건식·대상·관계·근거·임베딩 | 근거(`ev_subject_cd = ITEM`), `item_data` |

1. **과거 구조가 아니다.** 2026-11-04 `card_bnft` 테이블은 `card_product_item`으로 이관되고 `backup_card_bnft`로 이름이 바뀌었지만, 그래프는 근거 연결·임베딩·관계 key를 깨지 않으려고 혜택 key와 `dp_card_bnft` 라벨을 의도적으로 유지했다(`neo4j_dry_run.py` 머리말 주석, `neo4j_search.entity_ref`의 `ITEM_KINDS`).
2. **두 노드가 따로 있는 것이 아니다.** 혜택 1건 = 노드 1개이고, 그 노드에 라벨 2개가 붙는다. 업무상으로도 "혜택은 카드 상품 항목의 한 유형"이라는 모델을 그대로 반영한다.
3. **매핑**: 혜택 → `card_product_item`(BENEFIT), 연회비·TERMS → `card_product_item`(그 외). `backup_card_bnft`는 적재기와 런타임 코드 어디서도 읽지 않는다(Grep 결과, 테스트 1개 예외는 12절).
4. **중복 표현 없음**: 혜택 노드 34 = PG BENEFIT 34, `dp_has_item` 17 = TERMS 14 + 연회비 3. 같은 혜택이 두 노드로 존재하지 않는다.
5. **설계 버전 혼재 없음**: 모든 혜택 조회는 `dp_card_bnft`를, 혜택 외 항목 조회는 `dp_card_product_item` + `item_type_cd` 필터(`item_catalog`: `<> 'BENEFIT' AND <> 'TERMS'`, `TERMS_QUERY`: `{item_type_cd:'TERMS'}`)를 쓴다. `benefit_context`만 세 라벨을 모두 허용하는데 key로 1건을 찾으므로 중복이 없다.

**설계상 주의점(잠재 위험)**: 혜택 노드도 `dp_card_product_item` 라벨을 가지므로, 앞으로 `MATCH (i:dp_card_product_item)`을 `item_type_cd` 필터 없이 쓰면 혜택 34건이 함께 잡힌다. 현재 쿼리에는 해당 사례가 없다.

---

## 5. 과거 노드·관계 잔존 여부

| 점검 | 결과 | 판정 |
|---|---|---|
| PG 재생성 기대 그래프 vs Neo4j (`neo4j_validate` 읽기 전용 실행) | 기대 1,635/2,702 = 실제 1,635/2,702. `nodes_missing·extra·labels_changed·properties_changed·relationships_*` 모두 0 | 정상 |
| SQL ↔ Cypher 비교 5종 | 조건 구조 117=117, 근거 연결 250=250, 공통 근거 701=701, 공통 적용 1=1, 규칙 대상 235=235 | 정상 |
| 고아 노드 | `["card_doc","20261103_000012"]` 1건(JCB JP002 공통 연결 보류, 2026-11-05부터 알려진 항목). 검증기 `ok=false`의 유일한 원인 | 정상(알려진 보류) |
| 구형 라벨 노드(`dp_` 밖, `dp_node` 없는 `dp_*`) | 0 | 정상 |
| `backup_card_bnft` 16행 | `card_product_item`의 같은 ID 행과 `rule_list`·`bnft_limit_txt` 모두 동일. 그래프·런타임 미사용 | 정상(보관본) |
| 재적재 시 잔존 방지 | `neo4j_load_draft.main`은 원천에 없는 `dp_` 노드가 있으면 **적재를 중단**(188행), 자동 삭제 없음 | 정상(노드 단위) |

**결론: 과거 설계의 노드·관계가 남아 새 데이터와 섞이거나 중복 집계되는 현상은 없다.** 따라서 노드 삭제나 라벨 재설계는 근거가 없다.

---

## 6. PostgreSQL → Neo4j 필드 매핑표

`neo4j_load_draft.node_properties()`(68행)의 규칙: 노드에는 `key`, `source_json`(원천 행 전체 JSON), PK 속성, `SCALAR_FIELDS`(55행)·`ALIASES`(60행)에 있는 **스칼라 값 중 NULL이 아닌 것만** 속성으로 올린다. NULL은 속성이 생기지 않고 `source_json`에만 `null`로 남는다.

### 6.1 혜택 (`card_product_item` BENEFIT → `dp_card_bnft:dp_card_product_item`)

| PG 원천 컬럼 | 변환(별칭) | Neo4j 속성 | `source_json` | 사용하는 조회 |
|---|---|---|---|---|
| `card_id` | 그대로 | `card_id`(PK) | O | 전반 |
| `card_product_item_id` | `AS card_bnft_id` | `card_bnft_id`(PK), `card_product_item_id`(동일 값) | O | `catalog`, `candidate_relations`, hybrid |
| `item_cd` | `AS bnft_cd` | `bnft_cd` | O | hybrid |
| `item_nm` | `AS bnft_nm` | `name` | O | `catalog`, `list_benefits`, hybrid |
| `item_subtype_cd` | `AS bnft_type_cd` | `bnft_type_cd` | O | hybrid |
| `item_origin_cd` | `AS bnft_origin_cd` | — | O | hybrid(`apoc.convert.fromJsonMap(...)`) |
| `item_scope_cd`, `item_brand_opt_cds` | 별칭 | — | O | — |
| `item_cond_expr` | `AS bnft_cond_expr` | — (→ `dp_cond_expr` 노드) | O | `benefit_conditions` |
| `rule_list` | 그대로 | — (→ `dp_bnft_rule` 노드) | O | `benefit_rules` |
| `relation_list` | 그대로 | — (→ `dp_related_to`) | O | `benefit_relations` |
| `verification_status_cd` | 그대로 | `verification_status` | O | `catalog` |
| `item_valid_from/to_excl` | `AS bnft_valid_*` | 값이 있을 때만 | O | hybrid(유효기간 필터) |
| `item_rule_txt` | `AS bnft_rule_txt` | `rule_text` | O | `benefit_context`→`benefit_context()` |
| `item_limit_txt` | `AS bnft_limit_txt` | `limit_text` | O | `benefit_limits` |
| `item_search_txt` | 원행에서 제거 → 투영 | `search_text` | X | hybrid |
| `item_embedding` | 원행에서 제거 → 투영 | `embedding` (+dim·model·run_id) | X | hybrid(코사인) |
| — (`brand_bnft_compare`) | 투영 | `brand_compare_*` | X | hybrid |
| **`item_data`** | **SELECT 안 함** | **없음** | **없음** | — |
| `item_ref`, `item_type_cd`, `create/update_*` | SELECT 안 함 | `item_type_cd='BENEFIT'`만 상수로 기록 | 없음 | — |

### 6.2 규칙 (`rule_list[]` → `dp_bnft_rule`)

| JSON 키 | Neo4j 속성 | `source_json` | 사용 |
|---|---|---|---|
| `rule_key` | `rule_key`(PK, `card_id`·`card_bnft_id`와 함께) | O | `benefit_rules` |
| `value_num` | `value_num` — **NULL이면 속성 없음** | O | `hop2_card_rules`(속성), `benefit_context()`(source_json) |
| `value_unit_cd` | **항상 속성 없음**(`SCALAR_FIELDS`에 없음) | O | `benefit_context()`(source_json) |
| `rule_status_cd` | 없음 | O | `benefit_context()` |
| `target_list[]` | → `dp_rule_target` + `dp_targets`(관계 `source_json`에 원 항목) | O | `benefit_rules`, `catalog`, hybrid |
| `cond_expr` | → `dp_cond_expr`(key `RULE:card:id:rule`) | O | `benefit_conditions`, `catalog` |

Neo4j 서버는 `r.value_unit_cd`를 속성으로 조회하면 `01N52 property key does not exist` 알림을 보낸다(이번 점검 조회에서 실제 수신). 오류가 아니라 알림이며, 프로젝트 Cypher는 이 속성을 참조하지 않는다.

### 6.3 조건 atom (`cond_expr.branches[].atoms[]` → `dp_cond_atom`)

| JSON 키 | Neo4j 속성 | 사용 |
|---|---|---|
| `atom_key` | `key_name`(PK는 `expr_key, branch_no, atom_key`) | — |
| `cond_type_cd` | `kind` | `catalog`(`SPEND_REQ`·`USAGE_REQ`), hybrid(`BNFT_EXCL`) |
| `cond_min_amt` | `min_amt`(NULL이면 없음) | `catalog` |
| `cond_raw_txt` | `raw_text` | — |
| `negate_yn` | `negate` | — |
| `excl_raw_txt` | `excl_raw_txt` | `candidate_relations`, hybrid |
| `atom_seq` | `atom_seq` | `benefit_conditions` 정렬 |
| `cond_max_amt_excl`, `cond_basis_cd`, `cond_status_cd` | 없음(source_json만) | `condition_groups()`(source_json), `catalog`(`source_json CONTAINS '"cond_basis_cd":"TXN_AMT"'`) |

### 6.4 혜택 외 항목·근거

| PG 원천 | Neo4j | 비고 |
|---|---|---|
| `card_product_item`(TERMS·ANNUAL_FEE) 전체 컬럼(임베딩 제외) | `dp_card_product_item` 노드, `item_data`는 source_json | `item_catalog`, `TERMS_QUERY`, `fee_answer` |
| `card_evidence_link` | `dp_supported_by`(관계 속성 `ev_link_id` 등) | 근거 주체 CARD/BNFT/RULE/ITEM/REL |
| `card_source_evidence` | `dp_card_source_evidence` — **연결된 근거만**(`linked_evidence()` 244행) + 공통 혜택 근거 | PG 2,959건 중 연결 201건 + 공통 근거 전용 → 899노드 |

### 6.5 NULL 보존

PG `rule_list[].value_num = null` → Neo4j `source_json`의 `"value_num": null`, 속성 없음 → `properties(r)`에 `value_num` 키 없음 → `benefit_context()`는 `source(item["rule"]).get("value_num")`로 `None`. **NULL은 단계별로 그대로 NULL로 전달된다(값을 만들거나 바꾸지 않음).**

---

## 7. 변환 및 적재 과정의 정합성

### 7.1 동작 방식

- **전체 스냅샷 방식**: `load_snapshot`은 REPEATABLE READ READ ONLY 트랜잭션 하나에서 원천 전체를 읽는다. 증분 적재는 없다(`neo4j_load_draft.py` 머리말).
- **MERGE 전용**: 노드는 라벨+PK로 `MERGE … SET n += $props`, 관계는 key로 `MERGE`. 같은 원천을 재실행해도 중복이 생기지 않는다.
- **사후 검증**: 같은 쓰기 트랜잭션 안에서 노드·관계 key 집합이 원천과 같아야 commit된다.
- **잔존 노드 차단**: Neo4j에 원천에 없는 `dp_` 노드가 있으면 적재를 중단한다(자동 삭제 없음).
- **투영 동기화**(`neo4j_search_projection_sync.py`): 임베딩·검색 텍스트·브랜드 판정 속성과 공통 혜택 근거(`link_source='COMMON_STG'`)만 갱신·삭제할 수 있고, 그 밖의 차이가 있으면 쓰지 않는다.

### 7.2 확인된 문제

| # | 내용 | 등급 | 근거 |
|---|---|---|---|
| L1 | 혜택 행의 `item_data`가 그래프에 적재되지 않는다. PG에서 `item_data.limit_tiers`를 가진 혜택 2건(42/179, 42/180)이 Neo4j에서는 0건이다 | **확정 결함** | `neo4j_dry_run.py` benefits SELECT 목록에 `item_data` 없음. Neo4j `source_json CONTAINS 'limit_tiers'` 혜택 0건. TERMS·연회비 노드 17건은 `item_data` 보유 |
| L2 | `neo4j_validate`는 같은 `load_snapshot`으로 기대 그래프를 만든다. 그래서 SELECT에서 빠진 컬럼(L1)은 "차이 0"으로 통과한다. 검증이 PG 컬럼 대비 완전성을 보장하지 않는다 | **확정 결함**(검증 사각지대) | `neo4j_validate.run`이 `build(load_snapshot(conn))` 사용. L1이 있는데도 차이 0 |
| L3 | `SET n += $props`는 속성을 지우지 않는다. 원천 값이 나중에 NULL이 되면(예: `value_num` 삭제) 재적재 후 `source_json`은 null인데 예전 속성은 남는다. 적재 사후 확인은 key만 비교하므로 commit된다 | **잠재 결함** | `neo4j_load_draft.py` 133행, `write_transaction` 사후 확인. 현재는 `compare_graph`가 속성 차이 0이라 실제 사례 없음. `neo4j_validate`를 돌리면 감지는 된다 |
| L4 | 혜택 key와 `card_bnft_id` 속성 등 예전 이름 유지 | **정상 구조** | 근거·임베딩·관계 key 안정성을 위한 의도된 별칭 |
| L5 | 연결되지 않은 근거 2,758건은 그래프에 올리지 않는다 | **정상 구조**(의도) — 단 9절의 구간 연결 근거 손실과 맞물림 | `linked_evidence()` docstring: 검토 전 후보를 확정 데이터처럼 보이지 않게 하려는 정책 |

L1의 현재 영향은 제한적이다. DAILY 179·180은 `item_limit_txt` 자체를 `limit_tiers_text()`로 만들었기 때문에 구간별 금액이 문장으로 `limit_text`에 들어 있다. 그러나 구조 데이터(`tiers`, `caps.amount`)는 GraphRAG가 받을 수 없다.

---

## 8. GraphRAG 검색·상세 조회 쿼리 점검

### 8.1 실행 경로

Streamlit(N 모드) → `Neo4jBenefitSearch.search`(`card.hybrid_search`) → `CardGraphRAG.interpret`(LLM이 후보 중 선택) → `Neo4jSearch.get_details`(`card.detail_batch` = `card.context` + `card.rules` + `card.conditions` + `card.limits` + `card.evidence`|`card.item_evidence`|`card.common_evidence`를 `CALL (key) {…}`로 묶은 한 문장) → `card.terms` → `benefit_context()` → LLM → `validate_answer()`.

실패한 요청(`app_log` 198)의 `card.detail_batch` 파라미터는 `['["card_bnft",22,"20261105_000099"]', '["card_bnft",42,"20261105_000180"]']`이고, `card.terms`는 `card_ids [22, 42]`였다.

### 8.2 쿼리별 점검

| 쿼리 | 조회 경로 | 스키마 일치 | NULL·중복 위험 | 판정 |
|---|---|---|---|---|
| `card.hybrid_search` | `dp_card_bnft`/`dp_card_common_bnft` 풀 + 카드·공통서비스·적용카드·대상·`BNFT_EXCL` | 일치. `b.embedding`, `b.search_text`, `brand_compare_*`는 투영 속성으로 실재 | `collect`로 집계해 다대다 중복 없음. 유효기간은 `bnft_valid_to_excl` 속성(NULL이면 유효로 봄) | 정상 |
| `card.catalog` | 카드→혜택→규칙→대상, 규칙→조건 atom | 일치 | `OPTIONAL MATCH … WHERE`가 마지막 OPTIONAL MATCH에만 걸리는 정상 용법. `cond_basis_cd`를 `source_json` 문자열 `CONTAINS`로 찾는 것은 JSON 직렬화 형식(공백 없음, 키 정렬)에 의존 | 정상(취약점 경미) |
| `card.item_catalog` | 카드→`dp_has_item`→항목 | 일치 | 혜택 노드는 `dp_has_item`이 없고 `item_type_cd` 필터도 있어 중복 없음 | 정상 |
| `card.context` | `dp_node {key}` + 카드(`has_benefit|has_common_benefit|has_item`) + 공통서비스·문서 | 일치 | 적용 카드가 0·여러 개면 `head(cards)`가 대표값이지만 `_finish_context`가 표시명을 다시 만든다 | 정상 |
| `card.rules` | 혜택→규칙→대상 | 일치 | `properties(r)`에 `value_num` 키가 없을 수 있다 → Python에서 `None`. **NULL 계약이 Python에 정의되어 있지 않음**(9·10절) | 데이터 계약 결함 |
| `card.conditions` | 카드·혜택·규칙 각각의 조건식 | 일치 | `UNWIND` 뒤 일반 `MATCH`라 조건식 없는 소유자는 행이 없다(의도) | 정상 |
| `card.limits` | 혜택·공통혜택 `limit_text` | 일치 | 원문 텍스트 1개만 반환. 구간 구조는 없음 | 정상(표현 한계는 10절) |
| `card.evidence` | 카드·혜택·규칙 → 근거 → 청크 → 페이지 → 문서 | 일치 | 카드 단위 근거가 같은 카드의 혜택마다 반복된다(Python `collect_evidence`에서 근거 ID로 합침) | 정상 |
| `card.terms` | 카드→TERMS→ITEM 근거 | 일치 | 실제 데이터로 `attach_terms` 재현: DAILY 11건이 179·180에 정상 부착 | 정상 |
| `card.detail_batch` | 위 named query 본문을 `CALL (key)`/`OPTIONAL CALL (key)`로 감쌈 | 일치 | 섹션별 `WHERE x.<필수열> IS NOT NULL`로 OPTIONAL 결과의 빈 행을 제거 | 정상 |

- **카드명·ID 연결**: 카드 ID 22 = `더 심플 하나카드`, 42 = `카드의정석2 DAILY`(PG·Neo4j 동일). hybrid의 카드 식별 결과도 `identified_cards [22, 42]`였다.
- **적용 범위·공통 혜택 구분**: `dp_card_bnft`(`is_card`)와 `dp_card_common_bnft`를 key 접두사·라벨로 구분하고, `dp_same_as`·`brand_compare_status`로 병합한다. 이번 질문의 두 카드에는 공통 혜택이 없다.
- **전월 실적 조건과 월 할인 한도 구분**: 조건(`SPEND_REQ`, `PREV_MONTH_SPEND`)과 한도(`limit_text`)는 서로 다른 경로로 조회되며 쿼리 단계에서 섞이지 않는다. 하지만 **둘을 이어 주는 데이터가 없다**(9절).
- **Deprecation·오류 구분**: 이번 점검에서 프로젝트 쿼리(`detail_batch`, `hybrid_search`, `terms`, `catalog`)를 실행했을 때 서버 알림(deprecation 포함)은 0건이었다. 유일한 알림은 점검용 조회에서 일부러 `value_unit_cd` 속성을 참조했을 때의 `01N52`였다. 실제 실행 오류는 Neo4j가 아니라 Python `float(None)`이다.

### 8.3 검색 후보와 상세 조회의 일관성 (잠재 결함)

임베딩 없이 키워드 채널만으로 같은 질문을 `Neo4jBenefitSearch.search`에 실행했다(LLM·임베딩 미사용). top_k 5 후보는 `22/099 월납 요금 청구할인`, `42/180 정기결제 50%`, **`42/179 고정소비 영역 5%`**, `42/178 국내외 1%`, `6/015`였다. 42/179에는 `telecom` 규칙(SKT·KT·LG U+ 5%)이 있고 180과 **통합 할인한도를 공유**한다(`item_limit_txt`의 "통합 할인한도 공유: 고정소비 영역 5% 청구할인, 정기결제 50% 청구할인").

실패 요청은 상세 조회에서 179를 조회하지 않았다. 따라서 "휴대전화 요금 + 통합 한도" 질문에 DAILY의 통신 5% 할인과 공유 한도 구성이 빠진 채 답변이 만들어졌을 가능성이 있다. 실제 실행의 벡터 채널 순위와 interpret LLM 출력은 로그에 남지 않아 **원인(검색 순위 vs LLM 선택)은 미확인**이다. 또한 "휴대전화"라는 낱말은 규칙 대상명(SKT·KT·LG U+)과 일치하지 않아 관계 보정 점수에 반영되지 않는다.

---

## 9. 카드 22번 월납 요금 할인 사례 분석

### 9.1 단계별 대조

| 단계 | 위치 | 10,000원 / 15,000원 | 30만~80만 / 80만~ 구간 | 구간↔한도 연결 |
|---|---|---|---|---|
| 원문 | `card_doc 20261105_000042`(신용_더심플하나카드_상품설명서) p1, 청크 `20261105_000173` | 있음 | 있음 | 표로 있음(텍스트 추출 순서는 뒤섞임) |
| AI 추출 | `card_extr_stg 20261105_000619`(`stg_sql_check_cd = LINK_REVIEW`) | `limits: l1 {limit_num 10000, MONTH, KRW}`, `l2 {15000}` | `r1.c1 SPEND_REQ 300000~800000`, `r2.c2 800000~` | **있음**: `r1.limit_keys=[l1]`, `r2.limit_keys=[l2]`, `r3=[l1,l2]` |
| PG 등록 | `card_product_item 22/20261105_000099` | `item_limit_txt = "10,000원 / 15,000원 / ※ 횟수 제한 없이 월 할인 한도 내에서 합산 할인"`, `item_data = {}` | `rule_list` r1·r2 `cond_expr` | **없음**: 규칙에 한도 키 없음, `value_num`·`value_unit_cd` null |
| PG 근거 | `card_evidence_link` | `10,000원`(002681)·`15,000원`(002682)은 **BNFT 단위**로 연결 | r1·r2 근거는 둘 다 `월납 요금 청구할인`(002677) | **없음**: 구간과 금액을 함께 인용한 `80만원 이상⏎15,000원`(002686), `30만원 이상⏎80만원 미만`(002685)은 **연결되지 않음** |
| Neo4j | `dp_card_bnft` / `dp_bnft_rule` / `dp_cond_atom` | 혜택 `limit_text` 동일 문자열 | atom `min_amt` 300000/800000, `max_amt_excl`은 source_json | **없음**. 002685·002686 근거 노드는 그래프에 없음(`linked_evidence` 정책) |
| 검색 | `card.rules`/`card.conditions`/`card.limits`/`card.evidence` | 그대로 반환 | 그대로 반환 | 없음 |
| Python | `benefit_context()` → `rule_conflicts()` | `limits[0].text` | tier `min_amt` 300000/800000 | tier `value`/`unit` = None |

원문 청크(발췌): `서비스 대상 / 월 할인 한도 / 지난달 실적 / 10,000원 / 30만원 이상 / 80만원 미만 / 80만원 이상 / 15,000원 / 월납 요금 대상 가맹점 / 자동납부 시`. PDF 표가 텍스트로 풀리며 순서가 섞였지만, 추출 LLM은 표 이미지 근거(`link_basis: TABLE_IMAGE`)로 올바르게 짝지었다.

### 9.2 손실 지점 (소스)

1. **`extraction_service.build_rule()`(473행)** — 반환 dict가 `rule_key, cond_expr, target_list, value_num, value_unit_cd, rule_status_cd`뿐이다. `rule.limit_keys`를 버린다.
2. **`extraction_service.normalize_benefit()`(608행, 646행 주석)** — `"한도는 원문 인용(bnft_limit_txt)으로 보관한다. 한도 풀(limit_list·pool_refs) 정규화는 제거했다."` `item.limits`(limit_num 포함)를 정규화 결과에 넣지 않는다.
3. **`product_benefit_service` 등록부(325행)** — `limit_txt = quote_text(evidence_items, 'LIMIT')`: LIMIT 인용을 ` / `로 이어 붙인 평문을 만든다. 어떤 인용이 어떤 limit_key·규칙의 것인지 정보가 사라진다.
4. **`product_benefit_service._links()`(485행)** — `raw['evidence']`(최상위 인용)만 연결하고, RULE이 아닌 인용(LIMIT 포함)은 `link_key = None`, 즉 혜택 단위로 연결한다. 규칙 조건 안에 들어 있는 인용(`rules[].conditions[].evidence`)은 처리하지 않는다. 그래서 구간과 금액을 함께 보여 주는 002686이 연결되지 않았다.
5. 구간 한도를 구조로 복원하는 `SET_LIMIT_TIERS` 보정은 DAILY(BP 대장)에만 적용됐고 카드 22에는 적용되지 않았다.

### 9.3 Python 오프라인 재현 (실제 Neo4j 상세 행, LLM 없음)

```text
rule_selection_open(22/099) = True        # r1·r2·r3 대상 20개 동일
CONFLICTS tiers = [r3 {value None, min None}, r1 {value None, min 300000, max 800000, PREV_MONTH_SPEND},
                   r2 {value None, min 800000}]   applicable_rule_keys = []
distorts_tier("전월 실적 30만원 이상이면 할인됩니다.") -> TypeError float() ... 'NoneType'
distorts_tier("자동납부 시 할인됩니다.")            -> TypeError (금액이 없는 문장도)
tier_text(conflict)                                 -> TypeError
tier_is_quoted(conflict, [])                        -> TypeError
picks_single_tier("30만원 이상", conflicts)         -> None (적용 규칙이 없어 tier_token 미호출)
```

`distorts_tier()`는 문장을 보기 전에 `values = {tier_token(tier) …}`를 먼저 만든다. 그래서 **답변 포인트가 검증 단계까지 오면 문장 내용과 관계없이** 예외가 난다. 선행 문서의 "LLM 문장에 따라 재현 여부가 달라질 수 있다"는 표현보다 재현 조건이 넓다. `validate_answer()`가 유효 포인트 1개 이상에서 1282행을 호출하면 항상 실패한다.

### 9.4 판정 (A~G)

- **A. 원본에 10,000원·15,000원이 있는가** — **있다.** 청크 `20261105_000173`의 표: 30만 원 이상~80만 원 미만 10,000원, 80만 원 이상 15,000원.
- **B. PostgreSQL 저장 형태** — 추출 단계 `card_extr_stg.stg_raw_item`에는 구조(`limits`, `limit_keys`)로 있다. 등록본 `card_product_item.item_limit_txt`에는 평문 `"10,000원 / 15,000원 / ※ …"`만 있다. `rule_list`에는 금액이 없다(`value_num`·`value_unit_cd` null). 근거 002681·002682는 혜택 단위로 연결되어 있다.
- **C. Neo4j 저장 형태** — `dp_card_bnft.limit_text` 속성(PG와 동일 문자열), 근거 노드 002681·002682(BNFT `dp_supported_by`). 규칙 노드에는 금액 속성이 없고 `source_json`에 null이 있다.
- **D. r1·r2와 한도 금액의 연결이 보존되었는가** — **아니다.** PG 등록 단계에서 끊겼고 Neo4j는 끊긴 상태를 그대로 옮겼다.
- **E. 현재 모델로 구간별 한도를 정확히 표현할 수 있는가** — `rule_list` 계약(6개 키)으로는 **표현할 수 없다.** 수단은 `item_data.limit_tiers`(`BENEFIT_V1`)가 이미 있으나 ① 카드 22에는 적용되지 않았고 ② 혜택 노드에 적재되지 않으며(L1) ③ GraphRAG가 읽지 않는다(`card_graphrag.py`에 `limit_tiers` 참조 0건).
- **F. 현재 GraphRAG가 원문 근거로 구간별 한도를 정확히 답할 수 있는가** — **구조적으로 보장할 수 없다.** LLM은 `limit_text "10,000원 / 15,000원"`과 조건 `30만원 이상⏎80만원 미만`, `80만원 이상`을 따로 받아 순서로 추론해야 한다. 구간과 금액을 함께 인용한 근거(002686)는 그래프에 없다. 검증기는 `known_values()`(1049행)가 limit 텍스트의 10,000·15,000을 "근거 있는 값"으로 인정할 뿐, 어느 구간의 금액인지는 검사하지 않는다. `distorts_tier()`는 규칙 지급값만 tier 값으로 쓰기 때문에 한도 금액의 구간 오배정을 잡지 못한다. 크래시를 고쳐도 "30만 원 이상 구간 15,000원" 같은 뒤바뀐 답을 걸러낼 장치가 없다(코드 경로 분석. 유료 LLM 재현은 하지 않음).
- **G. 문제가 시작된 단계** — **정규화·등록(PG 적재 전 변환)** 단계에서 시작됐다. 추출은 올바르고, Neo4j 적재·검색은 받은 그대로 충실히 옮겼다. 답변 검증 단계는 그 결과(값 없는 tier)를 숫자로 가정하다가 예외를 냈다. 배경에는 2026-11-03 계산 구조 정리에서 "한도는 원문 인용 텍스트로 보관"하기로 한 설계 결정이 있다. 그 결정이 구간별 한도(구간마다 금액이 다른 경우)를 담지 못하는 한계를 등록·검증 쪽이 처리하지 않았다.

### 9.5 규칙 r3의 의미

r3(`ETC`, `TXN_AMT`, "월납 요금 승인 금액이 할인 한도보다 적을 경우" → "승인 금액만큼 할인")는 지급 구간이 아니라 계산 방식 설명이다. 그런데 r1·r2와 같은 대상 20개를 가진 규칙으로 저장되어 `rule_selection_open()`과 `rule_conflicts()`의 tier에 포함된다. 규칙 수를 부풀려 "규칙 선택 미확정"으로 보이게 만드는 **잠재 결함**이다(정규화 단계의 모델링 문제).

---

## 10. NULL 지급액 및 할인 한도 표현 문제

### 10.1 `value_num`·`value_unit_cd`의 업무 정의

`build_rule()` docstring: "값과 단위는 답변의 수치 확인과 검색 텍스트에 쓰는 설명 값이다. 계산 방법·지급 단위·기준 금액은 저장하지 않는다. 보상액을 계산하지 않는다." PG 검증 함수도 `value_num`에 null을 허용한다. 즉 **null은 계약상 합법적인 값**이다(정액·정률이 없는 혜택: 라운지, 주차, 연회비 면제, 결제 기능, "승인 금액만큼").

카드 22의 r1·r2에서 null 자체는 업무적으로 틀리지 않다. 할인율이 정해져 있지 않고 승인 금액만큼 할인하기 때문이다. 문제는 **구간을 구별하는 값이 지급값이 아니라 월 한도인데, 그 값을 둘 곳이 규칙에 없다**는 점이다.

### 10.2 Python 데이터 계약 결함

| 위치 | 가정 | 실제 |
|---|---|---|
| `benefit_context()` | `value`·`unit`을 그대로 전달 | None 가능, 문서화 없음 |
| `rule_conflicts()`(984행) | 규칙 = 지급 tier | 지급값 없는 규칙·계산 설명 규칙(r3)도 tier가 됨 |
| `tier_token()`(1011행) | `value`는 숫자 | None → TypeError |
| `known_values()`(1049행) | `value is not None`일 때만 추가 | 여기는 안전 |

현재 `known_values()`만 None을 처리하고 tier 계열 함수는 처리하지 않는다. 같은 파일 안에서 계약이 일관되지 않다(**확정 결함**).

---

## 11. 다른 카드에 대한 영향 범위

### 11.1 집계 (PG = Neo4j 일치 확인)

| 항목 | 건수 | 내용 |
|---|---:|---|
| 혜택 / 규칙 | 34 / 49 | 규칙 없는 혜택 1건(5/20261102_000008 Visa 컨시어지, `rule_list = []`) |
| `value_num` NULL 규칙 | 12 (혜택 10건) | 5/105, 6/022, 6/023, 20/093, 20/094, 21/096, **22/099 r1·r2·r3**, 23/101, 23/102, 40/103 |
| `value_unit_cd` NULL 규칙 | 12 | 위와 동일 |
| NULL 지급 + 전월 실적 구간(`SPEND_REQ min_amt`) 규칙 | **2 (22/099 r1·r2)** | **현재 `float(None)`을 일으킬 수 있는 유일한 데이터** |
| 전월 실적 구간 atom이 2개 이상인 혜택 | 2 | 22/099(2), 23/100(3) |
| 규칙 하나에 `SPEND_REQ` atom이 2개 이상 | 0 | `rule_conflicts`의 dict 덮어쓰기 위험은 현재 데이터에 없음 |
| 그 밖 NULL 지급 혜택 | 규칙 1개 | `rule_selection_open() = False`라 tier 경로에 들어가지 않음 |

### 11.2 구간별 한도가 등록 단계에서 사라진 혜택 (추출 원본 대조)

`card_extr_stg`에서 규칙마다 서로 다른 `limit_keys`를 가졌던 혜택을 등록본과 대조했다.

| 혜택 | 추출 원본 | 등록본 | 상태 |
|---|---|---|---|
| **22/099 월납 요금 청구할인** | r1→10,000원, r2→15,000원 | `"10,000원 / 15,000원 / …"` | **연결 손실** + 크래시 |
| **23/100 주요 간편결제 모아포인트 추가적립** | r1→1만, r2→2만, r3→5만(월) | `"1만원 / 2만원 / 5만원 / 통합 월 적립 한도 / …"` | **연결 손실**. r1·r2·r3 `cond_max_amt_excl`도 비어 있어 구간이 서로 겹친다(30만~, 60만~, 120만~). 지급값이 3%로 모두 같아 `tier_text`는 "30만원 이상 시 3%, 60만원 이상 시 3%, 120만원 이상 시 3%"가 되고, 한도 차이는 보이지 않는다 |
| 20/092 골프/프리미엄 아울렛 50% | 기본 10만, 추가 10만(누적 2,400만/3,600만) | `"보너스 할인 한도 10만원 제공 / … 추가 제공"` | 연결 손실이지만 금액이 같아 영향이 작다 |
| 42/179, 42/180 | 구간별 고정소비·통합 한도 | `item_data.limit_tiers` + 구간 문장 | **보정(SET_LIMIT_TIERS)으로 복원됨.** 단 그래프에는 텍스트만 있다(L1) |
| 6/013, 6/015, 6/017 | 추출 limits 없음(표가 텍스트로 풀림) | `"…30만원 이상 70만원 미만 70만원 이상 120만원 미만 120만원 이상 / 온라인 4천원 8천원 16천원 / 합계 1만원 2만원 4…"` | **텍스트 전용**. 구간과 금액은 위치로만 대응한다. 규칙에 전월 실적 atom이 없어 tier 경로에는 들어가지 않는다 |

### 11.3 PG ↔ Neo4j 개체별 건수

| 개체 | PG | Neo4j | 판단 |
|---|---:|---:|---|
| 카드 | 10 | 10 | 일치 |
| 혜택(BENEFIT) | 34 | 34 | 일치 |
| 혜택 외 항목 | 17 | 17 | 일치 |
| 규칙 | 49 | 49 | 일치 |
| 공통 혜택 / 공통서비스 | 82 / 14 | 82 / 14 | 일치 |
| 원문 근거 | 2,959 | 899 | **정상 차이**: 연결된 근거 + 공통 혜택 근거만 적재(L5) |
| 근거 연결 | 250 + 공통 701 | `dp_supported_by` 951 | 검증기 SQL↔Cypher 비교 일치 |

---

## 12. 확인된 결함과 잠재적 위험

### 확정 결함

| ID | 결함 | 위치 | 영향 |
|---|---|---|---|
| D1 | 구간별 한도 연결(`limits`, `rule.limit_keys`)을 정규화에서 버리고 평문만 저장 | `extraction_service.build_rule()`·`normalize_benefit()`, `product_benefit_service` 325행 | 22/099, 23/100, 20/092의 구간↔한도 연결 소실 |
| D2 | 구간과 금액을 함께 담은 규칙 조건 인용을 근거로 연결하지 않음. LIMIT 인용도 혜택 단위로만 연결 | `product_benefit_service._links()` | 002685·002686이 그래프에 없음. LLM이 구간별 한도를 원문으로 확인할 길이 없음 |
| D3 | tier 계열 함수가 nullable 지급값을 숫자로 가정 | `card_graphrag.tier_token()`과 호출부(`distorts_tier`, `tier_label`/`tier_text`, `tier_is_quoted`, `tier_answer`, `picks_single_tier`, `fixed_conclusion`, `validate_answer` 1282·1299행, `answer_text_problem`) | 22/099가 상세 조회에 포함되면 답변 실패. 금액 없는 문장에서도 발생 |
| D4 | 혜택 노드에 `item_data`(limit_tiers) 미적재 | `neo4j_dry_run.load_snapshot` benefits SELECT | 구조화된 구간 한도를 Neo4j 단일 검색에서 쓸 수 없음 |
| D5 | 적재 검증이 같은 스냅샷 함수를 써서 누락 컬럼을 감지하지 못함 | `neo4j_validate.run` | D4가 "차이 0"으로 통과 |
| D6 | GraphRAG가 구간별 한도를 검증하지 않음(한도 금액을 값 존재 여부로만 확인) | `known_values()`, `distorts_tier()` | 구간 오배정 답변을 통과시킬 수 있음 |

### 잠재 결함

| ID | 위험 | 추가 확인 |
|---|---|---|
| P1 | 계산 설명(r3)이 규칙으로 저장되어 규칙 선택 미확정·tier에 섞임 | 다른 혜택의 `ETC` 단독 규칙 전수 |
| P2 | `SET n += $props`가 속성을 지우지 않아 값이 NULL로 바뀌면 속성 잔존 | 재적재 후 `neo4j_validate`로 감지 가능 |
| P3 | 질문 관련 혜택(42/179 통신 5%, 180과 통합 한도 공유)이 상세 조회에서 빠짐 | interpret 출력·벡터 순위 로그 필요 |
| P4 | 혜택 노드의 `dp_card_product_item` 보조 라벨 때문에, 필터 없는 `MATCH (:dp_card_product_item)`가 혜택까지 잡을 수 있음 | 신규 쿼리 리뷰 규칙 |
| P5 | `catalog`가 `cond_basis_cd`를 `source_json` 문자열 일치로 찾음(직렬화 형식 의존) | `canonical()` 변경 시 회귀 |
| P6 | `rule_conflicts()`가 규칙당 `SPEND_REQ` atom 하나만 유지(dict 덮어쓰기) | 현재 데이터 0건 |
| P7 | 23/100 구간 상한(`cond_max_amt_excl`) 누락으로 구간이 겹침 | 원문 대조 후 보정 |
| P8 | `tests/test_live_registration.py`가 존재하지 않는 `db_pipeline.card_bnft`를 조회 | 라이브 테스트 실행 시 실패 예상(실행하지 않음) |

### 정상 구조 (오해하기 쉬운 부분)

- `dp_card_bnft` 라벨·`["card_bnft",…]` key·`card_bnft_id` 속성: 현행 혜택 표현(4절).
- 혜택 노드의 이중 라벨: 의도된 모델. 중복 노드 아님.
- `value_unit_cd`가 Neo4j 속성으로 없음: `source_json`으로만 제공. `01N52` 알림은 오류가 아님.
- NULL이 속성으로 생기지 않음: 적재 계약(`node_properties` docstring).
- 원문 근거 2,959 vs 899: 연결된 근거만 적재하는 정책.
- 고아 문서 `20261103_000012`: 알려진 보류 항목.

### 미확인

- 실패 요청에서 LLM이 생성한 실제 답변 포인트와 interpret 선택 이유(로그에 결과 행·LLM 출력 없음).
- 벡터 채널을 포함한 실제 hybrid 순위(임베딩 호출을 하지 않음).
- 배포 환경 Neo4j가 이 DB(`6ac1f0f8`)와 동일한지(로컬 `.env` 기준으로만 조회).
- PDF 원본 파일 자체 대조(청크 텍스트로 대조함. 표 이미지는 보지 않음).

---

## 13. 권장 수정 순서 및 대안 (제안만, 수정하지 않음)

| 순위 | 조치 | 대상 | 비고 |
|---|---|---|---|
| **1** | tier 함수의 nullable 계약 정리: 지급값이 숫자인 tier만 지급 비교에 쓰고, 값 없는 tier는 "지급값 미확정"으로 보존. 포인트 단위 예외 격리 | `card_graphrag.py`(D3) | 선행 문서 11절 방향과 동일. None→0 치환 금지. 가장 빨리 장애를 없앰 |
| **2** | 카드 22/099에 `SET_LIMIT_TIERS` 보정 적용(구간 2개, 열 "월 할인 한도", 10,000원/15,000원). 근거 002685·002686은 `ADD_EVIDENCE` 등으로 연결 | 보정 대장 + `benefit_review_patch`/등록 재실행 | DAILY에서 이미 검증된 경로. DB 변경이라 사용자 승인 필요 |
| 3 | 23/100 보정(구간 상한 추가, 1만/2만/5만 `limit_tiers`), 20/092 검토 | 보정 대장 | 원문 대조 후 |
| 4 | 혜택 스냅샷에 `item_data` 포함 → 노드 `source_json`에 반영. 필요하면 `limit_tiers`를 별도 속성(JSON 문자열)으로 투영 | `neo4j_dry_run.load_snapshot`, `neo4j_load_draft`, `test_neo4j_*` | 재적재 필요(승인). 기존 key·라벨 변경 없음 |
| 5 | 검증기에 PG 컬럼 대비 완전성 검사 추가(예: 혜택 컬럼 목록 중 그래프로 가지 않는 컬럼을 명시 허용 목록으로 관리) | `neo4j_validate.py` | D5 |
| 6 | GraphRAG가 `limit_tiers`를 `benefit_context`에 담고, 구간별 한도 문장을 프로그램이 쓰거나(연회비 `fee_answer`와 같은 방식) 구간↔한도 관계를 검증 | `card_graphrag.py`(D6) | 4 이후 |
| 7 | 정규화 개선: 규칙별 `limit_keys`가 서로 다르고 전월 실적 조건이 있으면 `limit_tiers` 후보를 자동 생성해 검토로 보냄. `_links()`가 규칙 조건 인용을 RULE/COND로 연결 | `extraction_service.py`, `product_benefit_service.py`(D1·D2) | 신규 등록분 재발 방지 |
| 8 | 계산 설명 규칙(r3류)을 규칙이 아닌 혜택 조건·설명으로 옮기는 기준 수립 | 정규화·보정 | P1 |
| 9 | 적재 시 NULL이 된 속성 제거(예: 스칼라 필드 목록에 대해 명시적 REMOVE) | `neo4j_load_draft.py` | P2. 쓰기 로직이라 dry-run·테스트 선행 |
| 10 | interpret 단계의 "통합 한도" 질문에서 공유 한도 그룹 구성원을 함께 조회하도록 보완 검토 | `card_graphrag.interpret`/`retrieve` | P3. 로그로 원인 먼저 확인 |

**권장하지 않음**: `dp_card_bnft` 라벨 삭제·이름 변경, 혜택 노드 재생성, 대규모 그래프 재설계. 이번 감사에서 이 구조가 오류의 원인이라는 증거가 없다. 바꾸면 NODE KEY 제약, 벡터 인덱스, 근거 관계 key, `entity_ref`가 함께 깨진다.

---

## 14. 회귀 검증 계획

1. **단위(오프라인, LLM 없음)**: 실제 22/099 구조(`value=None`, `unit=None`, `min_amt` 300000/800000, r3 `min_amt=None`)로 `distorts_tier`(금액 있는 문장·없는 문장), `tier_text`, `tier_is_quoted`, `tier_answer`, `picks_single_tier`, `fixed_conclusion`, `validate_answer`, `answer_text_problem`이 예외 없이 돌고, 미확정 상태를 0원으로 바꾸지 않는지 확인.
2. **기존 회귀**: `tests/test_card_graphrag.py`의 숫자 tier 테스트(827~847행 부근)가 그대로 통과.
3. **혼합**: 지급값 있는 tier와 없는 tier가 섞여도 정상 tier의 구간 왜곡 판정이 유지되는지 확인.
4. **보정 후 데이터(2·3번 조치 시)**: PG `item_data.limit_tiers` 존재, `item_limit_txt`가 구간 문장으로 바뀜, 근거 연결 추가 건수, 재실행 시 UNCHANGED.
5. **적재(4번 조치 시)**: `neo4j_dry_run --dry-run` 오류 0. `neo4j_load_draft` 미리보기 노드·관계 수 불변(속성만 증가). 적재 후 `neo4j_validate` 차이 0. Neo4j `source_json CONTAINS 'limit_tiers'` 혜택 수 = PG 수.
6. **읽기 전용 Cypher 점검**: 혜택 라벨 조합 34, `dp_has_item` 17, `card_product_item_id <> card_bnft_id` 0, NULL 지급 + `SPEND_REQ` 규칙 수(현재 2), 고아 노드 1.
7. **GraphRAG 질문 세트(stub LLM)**: 이번 비교 질문, 22번 단일 질문("30만 원 실적이면 월 한도는?"), 23/100 구간 질문, DAILY 통합 한도 질문, 연회비 질문. 구간별 금액이 원문과 일치하고 뒤바뀐 금액은 검증에서 걸리는지 확인.
8. **실제 LLM 확인(승인 시 소수)**: 위 질문 중 3~5개만 실행.

---

## 15. 최종 결론 및 미확인 사항

1. **`dp_card_bnft`는 현재 필요한 구조다.** `card_product_item` BENEFIT 행의 현행 그래프 표현이며, 같은 노드에 `dp_card_product_item` 라벨이 함께 붙는다. `dp_card_product_item` 단독 노드는 TERMS·연회비다. 두 라벨은 설계 버전 혼재가 아니라 의도된 이중 라벨이다.
2. **구형 노드·관계는 남아 있지 않다.** PG 재생성 그래프와 Neo4j 차이 0건(1,635/2,702)이고, 중복 노드·중복 집계도 없다.
3. **PostgreSQL → Neo4j 적재는 받은 값을 충실히 옮긴다.** 단 혜택 행의 `item_data`를 적재하지 않는 확정 누락(D4)이 있고, 검증기가 이를 감지하지 못하는 구조(D5)다.
4. **Cypher가 잘못 조회하는 부분은 없다.** 문제는 쿼리가 아니라, 쿼리가 돌려주는 데이터에 구간↔한도 연결이 없다는 점과 Python의 NULL 계약이다.
5. **10,000원·15,000원과 전월 실적 구간의 연결은 PostgreSQL 등록(정규화) 단계에서 사라졌다.** 추출 원본에는 `r1→l1(10,000원)`, `r2→l2(15,000원)`로 정확히 있었다. `build_rule`/`normalize_benefit`이 한도 구조를 버렸고, 등록부가 평문 `item_limit_txt`만 만들었으며, 구간과 금액을 함께 인용한 근거는 연결되지 않아 그래프에 오지 않았다.
6. **`float(None)`은 이 데이터 손실과 "규칙 = 숫자 지급 tier"라는 검증 로직의 가정이 만난 지점**이다. 금액이 없는 문장에서도 발생한다. 현재 데이터에서 이 조건을 만족하는 것은 22/099 r1·r2뿐이다. 같은 손실 유형(구간 한도 소실)은 23/100, 20/092에도 있다.

**수정이 필요한 주요 파일·DB 객체**: `card_graphrag.py`(tier 계열·`benefit_context`), `extraction_service.py`(`build_rule`, `normalize_benefit`), `product_benefit_service.py`(한도 텍스트·`_links`), `neo4j_dry_run.py`(`load_snapshot` benefits SELECT), `neo4j_validate.py`, PG `card_product_item` 22/20261105_000099·23/20261105_000100(보정), `card_evidence_link`(근거 002685·002686 연결 여부 결정), 보정 대장 `docs/identity_registry/benefit_patch/`.

**미확인**: 실패 요청의 실제 LLM 답변·interpret 선택 근거, 벡터 채널 순위, 배포 Neo4j와 로컬 대상 DB의 동일성, PDF 표 이미지 직접 대조.
