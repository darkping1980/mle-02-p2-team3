# 하나카드 GraphRAG — PostgreSQL·Neo4j 구조 및 데이터 비교 분석

- 작성일: 2026-11-03
- 분석 대상: 개발 PostgreSQL `db_pipeline` 스키마(PostgreSQL 17.11, Supabase), Neo4j DB `6ac1f0f8`의 `dp_` 그래프
- 분석 방식: 실제 카탈로그, 실제 데이터, 실행 소스를 읽기 전용으로 조회했습니다. INSERT·UPDATE·DELETE, DDL, Neo4j 적재·제약 변경, 소스 수정은 하지 않았습니다.
- 기준 우선순위: 실제 DB와 실행 소스를 먼저 봤고, V6 문서와 기존 비교 문서(`db_pipeline/POSTGRESQL_TO_NEO4J_STRUCTURE_COMPARISON.md`)는 참고만 했습니다.

> **조회 시점 주의.** 분석하는 동안 다른 세션에서 공통 문서 AI 추출(`card_ai_run` 20261103_000014~16)이 실행되고 있었습니다. 그래서 PostgreSQL의 `card_source_evidence`·`card_extr_stg` 건수가 조회할 때마다 늘었습니다(원문 근거 82 → 160 → 274건). 이 문서의 PostgreSQL 수치는 **2026-11-03 15:10 KST 스냅샷**이고, 그 밖의 시점에 조회한 값은 시각을 따로 적었습니다. Neo4j는 조회하는 동안 바뀌지 않았습니다.

---

## 0. 요약

| 항목 | 결과 |
|---|---|
| 업무 노드 라벨 | 13개(`dp_node` 공통 라벨 제외). PostgreSQL 테이블에서 온 라벨 8개, JSONB를 분해한 라벨 5개 |
| 관계 유형 | 14개. 연결 테이블 4개, 부모·자식 PK 포함 관계, JSONB 내부 구조, 동일성 비교 결과에서 만든다 |
| Neo4j 현재 건수 | 노드 200개, 관계 263개 |
| PostgreSQL 기준 예상(15:10) | 노드 439개, 관계 502개(`neo4j_validate` 계산값) |
| 차이 | 원문 근거 노드 239개와 `dp_in_chunk` 관계 239개 누락. 모두 Neo4j 적재 뒤 새로 추출된 공통 문서 원문 근거 |
| 공통으로 있는 노드·관계 | 노드 200개·관계 263개의 키, 라벨, 원본 JSON, 끝점이 PostgreSQL과 **모두 일치**(changed 0, extra 0) |
| 근거 연결 | `card_evidence_link` 57건 = `dp_supported_by` 57개, 값 일치 |
| 고아 노드 | 1개(`card_doc` 20261103_000012: 소유 상품·공통서비스 없음) |
| 실제 GraphRAG 조회 | 실제 Neo4j와 Mock LLM 통합 테스트 7건 통과. 조회에 쓰는 노드·관계·속성은 모두 존재 |

결론: 이미 적재된 범위에서는 구조와 값이 PostgreSQL과 같습니다. 차이는 크게 세 가지입니다.
- **동기화 지연**: 수동 적재 뒤 PostgreSQL에 새로 들어온 원문 근거가 Neo4j에 없습니다.
- **소유자 없는 문서 1건**: 소유 상품·공통서비스가 없는 문서가 있습니다.
- **재적재 시 검증 규칙과 데이터의 충돌**: 연결 없는 원문 근거가 늘어서, 다시 적재하면 검증 규칙과 맞지 않게 됩니다.

자세한 평가는 7절에 있습니다.

---

## 1. 분석 근거와 실행한 조회

### 1.1 소스

| 구분 | 파일 | 주요 함수·이름 |
|---|---|---|
| 변환 | `src/card_benefit/payment_card/db_pipeline/neo4j_dry_run.py` | `PK_FIELDS`(30–44), `load_snapshot`(98–136), `expr_key`(139), `expressions_of`(144), `expected_counts`(154), `build`(178–326), `Preview.node/edge/validate`(69–95) |
| 적재 | `neo4j_load_draft.py` | `CREATE_CONSTRAINTS`(31–36), `SCALAR_FIELDS`(37–41), `ALIASES`(42–45), `node_properties`(48–60), `prepare`(63–76), `write_transaction`(79–105), `prepare_schema`(108–116), `main`(119–143) |
| 대조 | `neo4j_validate.py` | `COMPARED`(18–24), `compare_graph`(34–51), `graph_ok`(54–57), `run`(60–93) |
| 대조 SQL | `neo4j_validation.sql` | `condition_structure`, `evidence_links`(8–13), `common_applies`, `rule_targets` |
| 대조 Cypher | `neo4j_validation.cypher` | `orphan_nodes`(53–67), `evidence_links`(77–81) 외 |
| 동일성 판정 | `common_benefit_service.py` | `compare_brand_bnft`, SQL `common_benefit_repository.brand_bnft_compare` |
| GraphRAG 조회 | `db_pipeline_origin_search/graph_questions.cypher`, `neo4j_search.py` | `STATEMENTS`(47–65), `source`(72–75), `Neo4jSearch.get_detail`(163–177) |
| GraphRAG 처리 | `db_pipeline_origin_search/card_graphrag.py` | `collect_evidence`(306–328), `find_exclusions`(331–350), `benefit_context`(401–421), `retrieve`(1128–1169) |
| PostgreSQL 검색 | `db_pipeline/embedding_repository.sql` | `search_card_bnft`, `select_card_bnft_detail`, `select_common_bnft_evidence`(187–198) |

### 1.2 실행한 읽기 전용 조회

| 대상 | 내용 | 방식 |
|---|---|---|
| PostgreSQL | 테이블·뷰 주석, 컬럼·자료형·NOT NULL·주석, PK·UNIQUE, 테이블별 건수 | `pg_class`, `pg_attribute`, `pg_constraint`, `count(*)`. 세션 `default_transaction_read_only=on`, `REPEATABLE READ READ ONLY` |
| PostgreSQL | 문서별 페이지·청크·근거·연결 수, 원문 근거 그룹, AI 실행 상태, JSONB 키 목록, 정합성 뷰 | 같은 방식 |
| Neo4j | `SHOW CONSTRAINTS`, `SHOW INDEXES`, 라벨별 속성·자료형, 관계 유형별 속성, 시작·끝 라벨, 중복, 고아 | `READ_ACCESS` 세션, MATCH·SHOW만 |
| 양쪽 | `python -m card_benefit.payment_card.db_pipeline.neo4j_validate` | 원본 프로그램 그대로(읽기 전용) |
| 양쪽 | Neo4j 승격 속성과 `source_json` 값의 일치, 같은 쌍 사이 `dp_supported_by` 병렬 관계 확인 | 별도 읽기 스크립트 |
| GraphRAG | `RUN_NEO4J_INTEGRATION=1 python -m unittest ...test_card_graphrag.LiveAccuracyTests` | 실제 Neo4j와 Mock LLM, 유료 호출 없음 |

---

## 2. 전체 구조 비교 (4.1)

### 2.1 테이블 ↔ 노드·관계 대응표

PostgreSQL 건수는 15:10 KST 기준, Neo4j 건수는 현재값입니다. `dp_node`는 모든 노드에 붙는 보조 라벨이라 집계하지 않았습니다.

| PostgreSQL 테이블 (한글명) | 건수 | Neo4j 노드·관계 (한글명) | 건수 | 변환 방식 | 변환 함수 | 구조적 차이와 이유 |
|---|---|---|---|---|---|---|
| `card_product` (카드 상품) | 2 | `dp_card_product` (카드 상품) | 2 | 행 → 노드 | `build` 199–203 | `brand_opt_list`·`card_cond_expr` JSONB는 `source_json`에만 남는다. 조건식은 별도 노드로 분해 |
| `card_bnft` (카드 혜택) | 5 | `dp_card_bnft` + `dp_has_benefit` | 5 / 5 | 행 → 노드, `card_id` → 관계 | `build` 234–242 | 검색 컬럼(`bnft_search_txt`, `bnft_embedding`)을 뺀다(`load_snapshot` 124–127). `rule_list`·`bnft_cond_expr`는 노드로 분해 |
| `card_bnft.rule_list` (계산 규칙 목록, JSONB) | 6 규칙 | `dp_bnft_rule` + `dp_has_rule` | 6 / 6 | JSONB 배열 원소 → 노드 | `build` 243–249 | PostgreSQL에는 테이블이 없다. 규칙마다 탐색하려고 분해 |
| `rule_list[].target_list` (규칙 대상) | 34 행 | `dp_rule_target` + `dp_targets` | 19 / 34 | 원소 → 공유 노드 + 관계 | `build` 250–254 | `(target_type_cd, target_key)`가 같으면 카드·규칙 사이에서 노드 하나를 공유한다(역탐색용, 251행 주석) |
| `card_cond_expr`, `bnft_cond_expr`, `rule_list[].cond_expr` (조건식, JSONB) | 8 식 | `dp_cond_expr` / `dp_cond_branch` / `dp_cond_atom` + `dp_has_expr` / `dp_has_branch` / `dp_has_atom` | 8 / 9 / 15 노드, 8 / 9 / 15 관계 | JSONB 트리 → 3단 노드 | `build.expression` 183–197 | OR(분기)·AND(조건)·NOT 구조를 경로로 표현 |
| `card_doc` (카드 관련 문서) | 17 | `dp_card_doc` | 17 | 행 → 노드 | `build` 204–205 | 파일·심의 정보는 `source_json`에만 남는다 |
| `card_doc_page` (문서 페이지) | 37 | `dp_card_doc_page` + `dp_in_document` | 37 / 37 | 행 → 노드, PK 앞부분 → 관계 | `build` 211–217 | `page_raw_txt`는 `source_json`에만 남는다 |
| `card_doc_chunk` (문서 청크) | 37 | `dp_card_doc_chunk` + `dp_on_page` | 37 / 37 | 같음 | `build` 218–225 | `chunk_raw_txt`는 `source_json`에만 남는다 |
| `card_source_evidence` (원문 근거) | **274** | `dp_card_source_evidence` + `dp_in_chunk` | **35** / 35 | 행 → 노드, 상위 PK 3개 → 관계 | `build` 226–232 | **동기화 차이 239건**(5.1절). NODE KEY는 `evidence_id` 하나(4.1절) |
| `card_evidence_link` (카드 근거 관계) | 57 | `dp_supported_by` | 57 | 연결 행 → 관계 | `build` 288–302 | 주체(CARD/BNFT/RULE)에 따라 시작 노드가 다르다. 상위키 4개는 관계 속성이 아니라 경로로 표현 |
| `card_product_doc` (상품별 문서 관계) | 3 | `dp_has_document` (상품 → 문서) | 3 | 연결 행 → 관계 | `build` 206–210 | `doc_role_cd`·`approval_status_cd`를 관계 속성으로 올린다 |
| `card_common` (브랜드 공통서비스) | 9 | `dp_card_common` | 9 | 행 → 노드 | `build` 258–259 | 없음 |
| `card_common_doc` (공통서비스별 원천 문서) | 14 | `dp_has_document` (공통서비스 → 문서) | 14 | 연결 행 → 관계 | `build` 260–264 | 상품 문서와 같은 관계 유형을 쓰고, 시작 라벨로 구분한다 |
| `card_common_bnft` (공통서비스 혜택) | 1 | `dp_card_common_bnft` + `dp_belongs_to` | 1 / 1 | 행 → 노드, `card_common_id` → 관계 | `build` 265–271 | 검색 컬럼을 뺀다 |
| `card_common_bnft_apply` (공통 혜택 적용) | 1 | `dp_has_common_benefit` | 1 | 연결 행 → 관계 | `build` 272–277 | 없음 |
| (테이블 없음) 동일성 판정 결과 | SAME 1 | `dp_same_as` | 1 | `compare_brand_bnft` 결과가 SAME인 행만 관계로 만든다 | `load_snapshot` 128–135, `build` 279–286 | Neo4j에만 있는 파생 관계. REVIEW·NO_COMMON은 만들지 않는다 |
| `card_ai_run` (AI 실행 이력) | 9 | 없음 | – | 변환 안 함 | `PK_FIELDS`에 없음 | 처리 이력은 조회 대상이 아니라 의도적으로 제외(5.4절) |
| `card_ai_call` (AI 호출 이력) | 9 이상 | 없음 | – | 변환 안 함 | – | 같음 |
| `card_extr_stg` (AI 추출 항목) | 65 | 없음 | – | 변환 안 함 | – | 같음. 원문 근거의 `card_extr_stg_id`는 `source_json`에만 남는다 |
| `card_excl_item` (제외 항목 사전) | 0 | 없음 | – | 변환 안 함 | – | 데이터가 없는 보류 테이블 |
| `common_code_grp` / `common_cd` (공통코드) | 41 / 155 | 없음 | – | 변환 안 함 | – | 코드값은 문자열 속성으로만 남는다. 코드명 노드 없음 |

PostgreSQL 뷰 8개(`v_card_cond_atom`, `v_card_rule`, `v_card_rule_target`, `v_card_bnft_rel`, `v_card_brand_opt`, `v_card_bnft_rule_effective`, `v_card_integrity_issue`, `v_common_cd_usage`)는 Neo4j로 옮기지 않습니다. 이 중 `v_card_cond_atom`과 `v_card_rule_target`은 `neo4j_validation.sql`에서 대조 기준으로 씁니다.

### 2.2 건수 집계

| 구분 | PostgreSQL에서 계산한 예상 (15:10) | Neo4j 실제 | 차이 |
|---|---|---|---|
| 노드 | 439 | 200 | −239(`dp_card_source_evidence`만) |
| 관계 | 502 | 263 | −239(`dp_in_chunk`만) |

예상 건수는 `expected_counts`(154–175)가 원천 행만으로 따로 계산합니다. 이 함수는 `build` 결과와도 대조됩니다(306–307).

---

## 3. 컬럼과 속성 비교 (4.2)

### 3.1 공통 변환 규칙 (`neo4j_load_draft.node_properties`, 48–60)

| 규칙 | 내용 | 결과 |
|---|---|---|
| 식별 속성 | `PK_FIELDS`의 필드를 그대로 속성으로 둔다 | NODE KEY 대상 |
| 내부 키 `key` | `canonical([label, *pk])` JSON 문자열(`neo4j_dry_run.key`, 59–61). 예: `["card_bnft",2,"20261101_000001"]` | **Neo4j에만 있음**. `dp_node_key` 고유 제약 |
| 원본 `source_json` | 행 전체(검색 컬럼 제외)를 키 정렬 JSON 문자열로 보관 | **Neo4j에만 있음**. 모든 원본 컬럼을 여기서 복원할 수 있다 |
| 스칼라 승격 | `SCALAR_FIELDS` 32개 중 값이 str·int·float·bool인 것만 같은 이름으로 올린다 | 직접 매핑 |
| 이름 변경 | `ALIASES` 11개: `bnft_nm→name`, `verification_status_cd→verification_status`, `bnft_rule_txt→rule_text`, `bnft_limit_txt→limit_text`, `atom_key→key_name`, `cond_type_cd→kind`, `cond_raw_txt→raw_text`, `negate_yn→negate`, `cond_min_amt→min_amt`, `approval_status_cd→approval_status`, `card_cond_status_cd→card_cond_status` | 이름 변경. 원래 이름은 `source_json`에 남는다 |
| NULL | 속성을 만들지 않는다 | 예: `dp_card_bnft.limit_text`는 5개 중 4개만 있다(공통 혜택과 같은 Visa 컨시어지 행은 NULL) |
| 날짜·시각 | `canonical(default=str)`로 직렬화한 문자열 | `bnft_valid_from`이 PostgreSQL `date`에서 Neo4j `STRING`이 된다 |
| JSONB | 별도 노드로 분해하거나 `source_json`에만 남긴다 | 6절 |
| 검색·벡터 | `bnft_search_txt`, `bnft_embedding`은 옮기지 않는다 | 의도된 생략 |

**값 대조 결과(실측)**:
- Neo4j 노드 200개의 승격 속성을 같은 노드의 `source_json` 값(이름 변경 반영)과 비교했고, **불일치 0건**입니다.
- `neo4j_validate`가 노드 200개·관계 263개의 `source_json`을 현재 PostgreSQL 원천과 비교했고, `nodes_changed 0`, `relationships_changed 0`입니다.
- 따라서 적재된 범위의 모든 속성 값은 PostgreSQL 현재 값과 같습니다.

### 3.2 PK와 NODE KEY

| PostgreSQL 테이블 | PostgreSQL PK (+UNIQUE) | Neo4j 라벨 | NODE KEY (`SHOW CONSTRAINTS` 실측) | 일치 |
|---|---|---|---|---|
| card_product | (card_id) +UQ(product_cd) | dp_card_product | (card_id) | 같음 |
| card_bnft | (card_id, card_bnft_id) +UQ(card_id, bnft_cd) | dp_card_bnft | (card_id, card_bnft_id) | 같음 |
| card_common | (card_common_id) +UQ(common_cd) | dp_card_common | (card_common_id) | 같음 |
| card_common_bnft | (card_common_id, card_common_bnft_id) | dp_card_common_bnft | 같음 | 같음 |
| card_doc | (card_doc_id) +UQ(doc_cd), UQ(doc_sha256) | dp_card_doc | (card_doc_id) | 같음 |
| card_doc_page | (card_doc_id, page_no) | dp_card_doc_page | 같음 | 같음 |
| card_doc_chunk | (card_doc_id, page_no, card_doc_chunk_id) +UQ(card_doc_chunk_id) | dp_card_doc_chunk | 같음 | 같음 |
| **card_source_evidence** | **(card_doc_id, page_no, card_doc_chunk_id, evidence_id)** +UQ(evidence_id) | dp_card_source_evidence | **(evidence_id)** | **다름**(5.2절) |
| (JSONB) rule_list | 없음 | dp_bnft_rule | (card_id, card_bnft_id, rule_key) | Neo4j에만 있음 |
| (JSONB) target_list | 없음 | dp_rule_target | (target_type_cd, target_key) | Neo4j에만 있음 |
| (JSONB) cond_expr | 없음 | dp_cond_expr | (expr_key) | Neo4j에만 있음 |
| (JSONB) branches | 없음 | dp_cond_branch | (expr_key, branch_no) | Neo4j에만 있음 |
| (JSONB) atoms | 없음 | dp_cond_atom | (expr_key, branch_no, atom_key) | Neo4j에만 있음 |
| (모든 노드) | – | dp_node | `key` UNIQUE (`dp_node_key`) | Neo4j에만 있음 |
| card_evidence_link | (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id) +UQ(card_id, evidence_link_id) +UQ NULLS NOT DISTINCT 자연키 8컬럼 | dp_supported_by (관계) | 관계 제약 없음. `r.key` = 내부 간선 키의 SHA-256 | 다름(5.3절) |

모든 NODE KEY 제약에는 RANGE 인덱스가 붙어 있습니다(`SHOW INDEXES`, owningConstraint). `CREATE_CONSTRAINTS`(31–36)는 `PK_FIELDS`에서 제약을 만들기 때문에, 위 표의 NODE KEY는 소스 정의와 실제 DB가 같습니다.

`expr_key`는 소유자 PK로 만든 문자열입니다(`expr_key`, 139–141). 형식은 `CARD:2`, `BNFT:2:20261101_000003`, `RULE:2:20261101_000001:one_pick_100`이고, PostgreSQL에는 없는 그래프 전용 식별자입니다.

### 3.3 라벨별 속성 비교

Neo4j 자료형은 `valueType()` 실측값입니다. "source_json만"은 Neo4j 속성으로 올리지 않고 원본 JSON 문자열 안에만 있는 컬럼입니다.

#### dp_card_product ← card_product

| PostgreSQL 컬럼 (주석) | 자료형 | Neo4j 속성 | 자료형 | 처리 |
|---|---|---|---|---|
| card_id (카드 아이디) | bigint | card_id | INTEGER | PK·직접 |
| product_cd (상품 코드) | varchar(80) | product_cd | STRING | 직접 |
| product_nm (상품명) | text | product_nm | STRING | 직접 |
| card_kind_cd (카드 구분) | varchar(10) | card_kind_cd | STRING | 직접 |
| card_cond_status_cd (카드 공통 조건 상태) | varchar(20) | card_cond_status | STRING | 이름 변경 |
| card_cond_expr (카드 공통 조건) | jsonb | – | – | JSONB 분해(`dp_cond_expr`) + source_json |
| brand_opt_list (브랜드 선택지 목록) | jsonb | – | – | **source_json만**(노드화 안 함) |
| issuer, product_status_cd, launched_on, discontinued_on, 감사 컬럼 4개 | – | – | – | source_json만 |

#### dp_card_bnft ← card_bnft

| PostgreSQL 컬럼 (주석) | 자료형 | Neo4j 속성 | 자료형 | 처리 |
|---|---|---|---|---|
| card_id, card_bnft_id | bigint, varchar(20) | card_id, card_bnft_id | INTEGER, STRING | PK·직접 |
| bnft_cd (혜택 코드) | varchar(80) | bnft_cd | STRING | 직접 |
| bnft_nm (혜택명) | text | name | STRING | 이름 변경 |
| bnft_type_cd (혜택 유형) | varchar(20) | bnft_type_cd | STRING | 직접 |
| verification_status_cd (혜택 검증 상태) | varchar(25) | verification_status | STRING | 이름 변경 |
| bnft_rule_txt (계산 규칙 안내) | text | rule_text | STRING | 이름 변경(NULL이면 없음) |
| bnft_limit_txt (혜택별 한도) | text | limit_text | STRING | 이름 변경(NULL이면 없음) |
| bnft_valid_from / bnft_valid_to_excl | date | 같은 이름 | **STRING** | 값 변환(날짜 → 문자열) |
| rule_list (계산 규칙 목록) | jsonb | – | – | JSONB 분해(`dp_bnft_rule`) + source_json |
| bnft_cond_expr (혜택 적용 조건) | jsonb | – | – | JSONB 분해(`dp_cond_expr`) + source_json |
| relation_list (혜택 관계 목록) | jsonb | – | – | **source_json만**(6.4절) |
| bnft_origin_cd, bnft_scope_cd, bnft_brand_opt_cds(text[]), rule_select_cd | – | – | – | source_json만 |
| bnft_search_txt, bnft_embedding(vector(1536)) | – | – | – | **생략**(source_json에도 없음) |

#### dp_card_source_evidence ← card_source_evidence

| PostgreSQL 컬럼 (주석) | 자료형 | Neo4j 속성 | 자료형 | 처리 |
|---|---|---|---|---|
| card_doc_id, page_no, card_doc_chunk_id | varchar(20), smallint, varchar(20) | 같은 이름 | STRING, INTEGER, STRING | 직접(NODE KEY 아님) + `dp_in_chunk` 경로 |
| evidence_id (원문 근거 아이디) | varchar(20) | evidence_id | STRING | **NODE KEY** |
| start_pos / end_pos (인용 위치) | integer | 같은 이름 | INTEGER | 직접 |
| approval_status_cd (승인 상태) | varchar(20) | approval_status | STRING | 이름 변경 |
| quote_txt (원문 인용 문장) | text | – | – | **source_json만**. GraphRAG는 `source()`로 읽는다(`collect_evidence` 318–321) |
| card_extr_stg_id (추출 항목 아이디) | varchar(20) | – | – | source_json만 |

#### dp_card_doc / dp_card_doc_page / dp_card_doc_chunk

| 라벨 | Neo4j 속성(실측) | source_json에만 있는 주요 컬럼 |
|---|---|---|
| dp_card_doc | card_doc_id, doc_title, doc_type_cd | doc_cd, doc_sha256, doc_file_nm, doc_source_url, doc_review_no, doc_status, doc_page_cnt 외 |
| dp_card_doc_page | card_doc_id, page_no | page_raw_txt, page_char_cnt, page_txt_sha256, page_layer_cd, page_extractor_nm 외 |
| dp_card_doc_chunk | card_doc_id, page_no, card_doc_chunk_id | chunk_seq, chunk_section_nm, chunk_type_cd, chunk_raw_txt, chunk_clean_txt, chunk_start_pos/end_pos 외 |

#### dp_card_common / dp_card_common_bnft

| 라벨 | Neo4j 속성(실측) | source_json에만 있는 컬럼 |
|---|---|---|
| dp_card_common | card_common_id, common_cd, common_nm, brand_cd, service_grade_cd | common_note, 감사 컬럼 |
| dp_card_common_bnft | card_common_id, card_common_bnft_id, bnft_cd, name, bnft_type_cd, service_type_cd, rule_text, bnft_valid_from, bnft_valid_to_excl | bnft_limit_txt(현재 NULL), 감사 컬럼 |

#### JSONB 분해 노드

| 라벨 | Neo4j 속성(실측) | source_json에만 있는 JSONB 키 |
|---|---|---|
| dp_bnft_rule | card_id, card_bnft_id, rule_key, value_num(INTEGER) | calc_method_cd, value_unit_cd, payout_unit_cd, basis_amt, calc_params, rule_status_cd, predicate_state_cd, rule_priority, method_ver, cond_expr, target_list |
| dp_rule_target | target_type_cd, target_key, target_nm | 없음(세 필드만 저장, `build` 252–253) |
| dp_cond_expr | expr_key | branches, expr_status_cd |
| dp_cond_branch | expr_key, branch_no | atoms |
| dp_cond_atom | expr_key, branch_no, atom_key, atom_seq, key_name, kind, negate(BOOLEAN), raw_text, min_amt(6/15), excl_raw_txt(6/15) | cond_basis_cd, cond_max_amt_excl, cond_status_cd, cond_params, card_excl_item_id, link_role_cd, predicate_method_cd, predicate_method_ver |

`dp_cond_atom`에는 `atom_key`(PK)와 `key_name`(이름 변경)이 같은 값으로 함께 있습니다. PK로 한 번, `ALIASES`로 한 번 올라가기 때문입니다.

### 3.4 관계 속성 (실측)

| 관계 | 속성 | 원천 |
|---|---|---|
| 모든 관계 | `key`, `source_json` | `key`는 내부 간선 키의 SHA-256(`prepare` 75), `source_json`은 원천 행 또는 `{}` |
| dp_supported_by | ev_link_id, ev_subject_cd, ev_item_cd, ev_item_key | `write_transaction` 91–93의 허용 목록 |
| dp_has_document (상품 → 문서) | doc_role_cd, approval_status_cd | card_product_doc |
| dp_has_document (공통 → 문서) | 없음 | card_common_doc에 PK 외 컬럼이 없다 |
| dp_has_atom | atom_seq | JSONB 원소 순번 |
| dp_same_as | status, bnft_cd | 동일성 판정 결과 |

---

## 4. 관계 구조 비교 (4.3)

### 4.1 관계별 생성 조건·방향·식별키

| PostgreSQL 논리 관계 | Neo4j 관계 (방향) | 생성 조건 (`build`) | 식별 | 관계 속성 | 건수 PG / Neo4j |
|---|---|---|---|---|---|
| CARD_PRODUCT 1:N CARD_BNFT (`card_bnft.card_id`) | `(dp_card_product)-[:dp_has_benefit]->(dp_card_bnft)` | 혜택의 상품이 있으면 생성, 없으면 오류로 중단(236–241) | 양 끝 PK | 없음 | 5 / 5 |
| CARD_PRODUCT_DOC | `(dp_card_product)-[:dp_has_document]->(dp_card_doc)` | 상품·문서가 모두 있을 때. 없으면 오류(206–210) | (card_id, card_doc_id) | doc_role_cd, approval_status_cd | 3 / 3 |
| CARD_COMMON_DOC | `(dp_card_common)-[:dp_has_document]->(dp_card_doc)` | 공통서비스·문서가 모두 있을 때(260–264) | (card_common_id, card_doc_id) | 없음 | 14 / 14 |
| CARD_COMMON_BNFT_APPLY | `(dp_card_product)-[:dp_has_common_benefit]->(dp_card_common_bnft)` | 공통 혜택·상품이 모두 있을 때(272–277) | (card_common_id, card_common_bnft_id, card_id) | 없음 | 1 / 1 |
| CARD_COMMON 1:N CARD_COMMON_BNFT | `(dp_card_common_bnft)-[:dp_belongs_to]->(dp_card_common)` | 265–271 | 양 끝 PK | 없음 | 1 / 1 |
| CARD_EVIDENCE_LINK | `(CARD\|BNFT\|RULE 노드)-[:dp_supported_by]->(dp_card_source_evidence)` | `ev_subject_cd`에 따라 시작 노드를 고른다(288–302). 주체·근거가 없으면 오류 | 연결 행 하나 = 관계 하나 | ev_link_id, ev_subject_cd, ev_item_cd, ev_item_key | 57 / 57 |
| CARD_SOURCE_EVIDENCE → CARD_DOC_CHUNK (PK 앞 3컬럼) | `(dp_card_source_evidence)-[:dp_in_chunk]->(dp_card_doc_chunk)` | 근거의 청크가 있을 때(226–232) | 근거 PK | 없음 | 274 / 35 |
| CARD_DOC_CHUNK → CARD_DOC_PAGE | `(dp_card_doc_chunk)-[:dp_on_page]->(dp_card_doc_page)` | 218–225 | – | 없음 | 37 / 37 |
| CARD_DOC_PAGE → CARD_DOC | `(dp_card_doc_page)-[:dp_in_document]->(dp_card_doc)` | 211–217 | – | 없음 | 37 / 37 |
| RULE_LIST (JSONB) | `(dp_card_bnft)-[:dp_has_rule]->(dp_bnft_rule)` | `rule_list` 원소마다(243–249) | (card_id, card_bnft_id, rule_key) | 없음 | 6 / 6 |
| RULE_LIST[].TARGET_LIST | `(dp_bnft_rule)-[:dp_targets]->(dp_rule_target)` | 대상 원소마다. 대상 노드는 공유(250–254) | 관계 key에 원소 JSON 포함 | 없음(원소는 source_json) | 34 / 34 |
| BNFT_COND_EXPR 등 | `(소유자)-[:dp_has_expr]->(dp_cond_expr)-[:dp_has_branch]->(dp_cond_branch)-[:dp_has_atom]->(dp_cond_atom)` | 조건식이 NULL이 아닐 때(183–197) | expr_key / branch_no / atom_key | has_atom.atom_seq | 8·9·15 / 8·9·15 |
| (파생) 동일성 SAME | `(dp_card_bnft)-[:dp_same_as]->(dp_card_common_bnft)` | `compare_brand_bnft` status가 SAME인 행만(279–286) | – | status, bnft_cd | 1 / 1 |

모든 관계는 MERGE 키 `{key:$key}`로 만듭니다(`write_transaction` 94–96). 관계 key는 `("relationship", 유형, 시작 key, 끝 key, 원천 JSON)`의 SHA-256입니다. 그래서 같은 두 노드 사이에도 원천 행이 다르면 관계가 따로 생깁니다.

### 4.2 `dp_supported_by`의 병렬 관계 (중복 여부)

같은 (소유자, 원문 근거) 쌍에 관계가 2개인 경우가 13쌍 있습니다. 실측 결과 13쌍 모두 `ev_item_cd = SELF`(혜택 자체 근거) 1개와 `COND`(조건 근거, `ev_item_key` = 조건 atom 키) 1개로 이루어져 있습니다. 예: card 2 ↔ 20261101_000056은 `SELF/-`와 `COND/common_service_exclusion`입니다. PostgreSQL에서도 자연키가 다른 별개의 연결 행이므로 **중복이 아닙니다**. 관계 key 중복은 0, 노드 key 중복은 0입니다.

### 4.3 PostgreSQL에서의 관계 강제 수준

- PostgreSQL에는 물리 FK가 하나도 없습니다(카탈로그에서 contype `f` 0건). 관계는 `v_card_integrity_issue` 게이트로만 검증합니다.
- Neo4j 변환기는 끝점이 없으면 건너뛰지 않고 **오류를 모아 적재를 중단**합니다(`build` 전반, `GraphValidationError`). `Preview.validate`(86–95)가 끊어진 관계도 거부합니다.
- 따라서 Neo4j 쪽 참조 무결성은 적재 시점에 PostgreSQL보다 강하게 확인됩니다.
- 15:10 시점 `v_card_integrity_issue`에는 `evidence_not_approved` 35건만 있습니다(연결된 원문 근거가 모두 PENDING). 이는 승인 상태 문제이지 구조 문제가 아닙니다.

---

## 5. 실제 데이터 비교 (4.4)

### 5.1 전체 대조 (`neo4j_validate`, 15:10 KST)

```text
expected  {'nodes': 439, 'relationships': 502}
neo4j     {'nodes': 200, 'relationships': 263}
differences {'nodes_missing': 239, 'nodes_extra': 0, 'nodes_changed': 0,
             'relationships_missing': 239, 'relationships_extra': 0, 'relationships_changed': 0}
orphan_nodes [{'key': '["card_doc","20261103_000012"]'}]
sql_cypher {'condition_structure': [15, 15, True], 'evidence_links': [57, 57, True],
            'common_applies': [1, 1, True], 'rule_targets': [34, 34, True]}
outside_scope {'outside_nodes': 0, 'outside_relationships': 0}
ok False
```

| 비교 항목 | 결과 |
|---|---|
| 노드 키 일치 | Neo4j에 있는 200개는 모두 PostgreSQL에서 만든 키와 같다. 남는 노드 0 |
| 누락 | `card_source_evidence` 239개(20261103_000070 ~ 20261103_000308)와 각각의 `dp_in_chunk` |
| 속성 값 | 공통 노드·관계의 `source_json`이 모두 같다(changed 0). 승격 속성과 `source_json`도 모두 같다(3.1절) |
| 원문 근거 연결 | 57 = 57. ev_link_id, 주체, 항목, 근거, 위치가 SQL과 Cypher에서 같다 |
| 조건식 | atom 15 = 15(소유자, 분기, 순번, 유형, NOT, 금액, 원문 일치) |
| 규칙 대상 | 34 = 34 |
| 공통 혜택 적용 | 1 = 1 |
| 고아 | 1개(`card_doc` 20261103_000012, 5.4절) |
| 중복 | 노드 key 0, 관계 key 0, 병렬 관계 13쌍은 중복 아님(4.2절) |
| dp_ 범위 밖 | 0. 다른 프로젝트(`fp_`) 노드도 0 |
| **판정** | **ok False**. 원인은 동기화 누락 239건과 고아 문서 1건 |

시간에 따른 누락 건수(같은 프로그램 기준):

| 시각 (KST) | PostgreSQL 원문 근거 | Neo4j 원문 근거 | 누락 |
|---|---|---|---|
| 약 15:05 | 82 | 35 | 47 |
| 15:07 | 160 | 35 | (미측정) |
| 15:10 | 274 | 35 | 239 |

### 5.2 누락 데이터의 성격 (15:10)

| 문서 | 원문 근거 | 연결(`card_evidence_link`) | 추출 상태 |
|---|---|---|---|
| 20261101_000002 (ONE PICK STYLE 상품설명서) | 31 | 53(모든 근거 연결) | Neo4j 반영됨 |
| 20261102_000003 (JADE Classic 상품설명서) | 1 | 1 | 반영됨 |
| 20261102_000004 (Visa 브랜드서비스 VS002) | 3 | 3 | 반영됨 |
| 20261103_000009 / 000010 / 000019 / 000011 외 (AMEX·UnionPay 등 공통 문서) | 239 이상(증가 중) | **0** | 추출 실행 중(PENDING_REVIEW) |

- 누락된 239건은 모두 공통 문서에서 AI 추출로 새로 생긴 원문 근거입니다. 승인 상태는 PENDING이고 `card_extr_stg`(BENEFIT)에만 연결되며, 근거 연결은 0건입니다.
- 원인은 등록 파이프라인이 Neo4j를 갱신하지 않는다는 데 있습니다.
  - `common_auto_pipeline.py`, `common_benefit_service.py`, `product_benefit_service.py`에는 Neo4j 호출이 없습니다(소스 검색으로 확인).
  - Neo4j 반영은 수동 `neo4j_load_draft --apply --confirm APPROVED_DP_HANA_CARD`뿐입니다.

### 5.3 카드 한 건 상세 비교 — card 2 `ONE PICK STYLE 하나 체크카드`

card 2는 이번 추출 작업과 관계가 없어 조회하는 동안 바뀌지 않았습니다.

| 항목 | PostgreSQL | Neo4j | 일치 |
|---|---|---|---|
| 상품 | card_product 1행, `card_cond_status_cd = DRAFT` | dp_card_product 1개, `card_cond_status = DRAFT` | 같음 |
| 혜택 | card_bnft 4행(000001~000004) | dp_card_bnft 4개 | 같음 |
| 계산 규칙 | rule_list 원소 6개(one_pick_100/500, style_100/500, transit_rate, amusement_rate) | dp_bnft_rule 6개 | 같음 |
| 규칙 대상 | target_list 원소 34개(6+6+9+9+2+2) | dp_targets 34개 → dp_rule_target 19개(100/500 규칙이 공유하는 대상 15개) | 같음(공유는 의도) |
| 조건식 | CARD:2 1식, BNFT 000003·000004 2식, RULE 5식(amusement_rate는 `cond_expr` NULL) = 8식 | dp_cond_expr 8개 | 같음 |
| 분기·조건 | 분기 9, atom 15 | 9 / 15 | 같음 |
| 근거 연결 | 53행(CARD 8, BNFT 34, RULE 11) | dp_supported_by 53개 | 같음 |
| 원문 근거 | 문서 20261101_000002의 31건, 모두 연결됨 | 31개 | 같음 |
| 문서 경로 | 페이지 2, 청크 2 | dp_card_doc_page 2, dp_card_doc_chunk 2 | 같음 |

**혜택 1건 값 비교 — `ONE PICK 편의점·카페 캐시백` (card_bnft_id 20261101_000001)**

| PostgreSQL | 값 | Neo4j | 값 |
|---|---|---|---|
| card_bnft.bnft_nm | ONE PICK 편의점·카페 캐시백 | dp_card_bnft.name | 같음 |
| bnft_type_cd | CASHBACK | bnft_type_cd | 같음 |
| verification_status_cd | PENDING_REVIEW | verification_status | 같음 |
| bnft_rule_txt | 결제 건당 3천원 이상 시 100원 / 결제 건당 1만원 이상 시 500원 | rule_text | 같음 |
| bnft_limit_txt | 월 5천원 / 일 1회 / 월 30회 | limit_text | 같음 |
| rule_list[0].rule_key / value_num / calc_method_cd | one_pick_100 / 100 / FIXED_PER_TXN | dp_bnft_rule.rule_key / value_num / source_json | 같음 |
| rule_list[0].cond_expr.branches[0].atoms[0] | atom_key MIN_one_pick_100, cond_type_cd SPEND_REQ, cond_basis_cd TXN_AMT, cond_min_amt 3000, cond_raw_txt "결제 건당\n3천원 이상 시" | dp_cond_atom (expr_key `RULE:2:20261101_000001:one_pick_100`) key_name, kind, min_amt, raw_text, cond_basis_cd(source_json) | 같음 |
| card_source_evidence 20261101_000031 | 문서 20261101_000002, 1페이지, 청크 20261101_000012, end_pos 1678, PENDING | 같은 노드 속성. `-[:dp_in_chunk]->` 청크 20261101_000012 | 같음 |

### 5.4 고아 노드 — card_doc 20261103_000012

- PostgreSQL에서 `공통_JCB브랜드서비스_JP002_20260326`(BRAND_SERVICE, 1페이지)은 `card_product_doc`과 `card_common_doc` 어디에도 연결되지 않았습니다. `card_common`에 JCB 공통서비스 행이 없습니다(9개 공통서비스 중 JCB 없음).
- Neo4j에서는 같은 문서가 `dp_has_document` 없이 존재합니다. `orphan_nodes` 규칙(65행)에 걸려 `neo4j_validate`가 실패하는 직접 원인입니다.
- `v_card_integrity_issue`에는 "소유자 없는 문서"를 잡는 게이트가 없어 PostgreSQL 쪽에서는 드러나지 않습니다.
- 등록 과정이 끝나지 않은 상태인지(JCB 공통서비스 등록 예정) 실제 누락인지는 **추가 확인이 필요합니다**. 15:10 기준으로 이 문서를 대상으로 한 `card_ai_run`은 없습니다.

---

## 6. JSONB → 그래프 변환 분석 (4.5)

| JSONB | PostgreSQL 위치 | Neo4j 변환 | 코드 | 현재 데이터 |
|---|---|---|---|---|
| RULE_LIST | `card_bnft.rule_list` | 원소 → `dp_bnft_rule` 노드 + `dp_has_rule`. 내부 `target_list` → `dp_rule_target`(공유) + `dp_targets`. 내부 `cond_expr` → 조건식 노드 | `build` 243–256 | 규칙 6, 대상 원소 34 |
| BNFT_COND_EXPR | `card_bnft.bnft_cond_expr` | `dp_cond_expr` → `dp_cond_branch` → `dp_cond_atom` | `build.expression` 183–197 | 2식 |
| CARD_COND_EXPR | `card_product.card_cond_expr` | 같음. 소유자는 `dp_card_product`. 단 `card_cond_status_cd`가 DRAFT가 아니면 오류로 중단(200–201) | 199–203 | 1식 |
| RELATION_LIST | `card_bnft.relation_list` | **변환하지 않음.** `source_json` 문자열에만 남는다 | `build`에 처리 코드 없음 | 5행 모두 빈 배열, `v_card_bnft_rel` 0행 |
| BRAND_OPT_LIST | `card_product.brand_opt_list` | **변환하지 않음.** `source_json`에만 남는다 | 처리 코드 없음 | card 2: 2개, card 5: 4개 |

### 6.1 RULE_LIST

- 노드가 되는 단위는 규칙 원소입니다. NODE KEY `(card_id, card_bnft_id, rule_key)`가 rule_key 고유성을 강제합니다.
- PostgreSQL에서는 JSONB 안이라 rule_key 중복을 DB가 막지 않습니다. 변환기에서 같은 키에 다른 값이 오면 `conflicting node`로 중단합니다(`Preview.node`, 75–76).
- 노드에 올리는 스칼라는 `value_num` 하나입니다. `calc_method_cd`, `value_unit_cd`, `basis_amt`, `calc_params`, `rule_status_cd` 등은 `source_json`에만 있습니다. GraphRAG는 `source(item["rule"])`로 이 값들을 읽습니다(`benefit_context` 405–410).
- 변환 뒤 `build`(309–313)가 각 규칙 노드의 `source_json`과 원본 JSON의 동일성을 다시 확인합니다.

### 6.2 조건식(BNFT_COND_EXPR / CARD_COND_EXPR / rule cond_expr)

| JSONB 경로 | Neo4j | 식별 |
|---|---|---|
| `{expr_status_cd, branches}` | dp_cond_expr | expr_key = 소유자 PK 문자열 |
| `branches[i]` `{branch_no, atoms}` | dp_cond_branch | (expr_key, branch_no) |
| `branches[i].atoms[j]` | dp_cond_atom, 관계 `dp_has_atom.atom_seq` | (expr_key, branch_no, atom_key) |

- 분기 사이는 OR, 분기 안의 atom 사이는 AND이고, `negate_yn`이 NOT입니다.
- 이 의미는 Neo4j에서 노드 구조와 `negate` 속성으로 유지되며, `neo4j_validation.cypher` `condition_structure`가 PostgreSQL `v_card_cond_atom`과 대조합니다(15 = 15).
- atom의 `card_excl_item_id`(제외 항목 사전 참조)는 `source_json`에만 남고 관계로 만들지 않습니다. `card_excl_item`이 0행이고 그래프 범위 밖이기 때문입니다.

### 6.3 BRAND_OPT_LIST

- 상품별 브랜드 선택지는 노드나 관계가 아닙니다. 그래서 "이 카드의 Mastercard World 선택지" 같은 경로를 Neo4j에서 탐색할 수 없습니다.
- 브랜드 혜택은 대신 `card_common_bnft_apply` → `dp_has_common_benefit`와 `dp_card_common.brand_cd/service_grade_cd`로 표현됩니다.
- 혜택 쪽 `bnft_brand_opt_cds`(text[])와 상품 문서 쪽 `brand_opt_cds`도 `source_json`에만 있습니다.
- GraphRAG의 Cypher 중 브랜드 선택지를 읽는 것은 없습니다(`graph_questions.cypher` 전체 확인).

### 6.4 RELATION_LIST

- 혜택 사이 관계(예: MUTUALLY_EXCLUSIVE)는 PostgreSQL에서 `v_card_bnft_rel`로 행 복원만 됩니다. Neo4j 변환 코드는 없습니다.
- 현재 데이터가 0건이라 차이가 드러나지 않습니다.
- 이후 관계 데이터가 들어오면 그래프에서 혜택 간 배타·중복 관계를 탐색할 수 없습니다. 근거 연결의 `relation_key` 주체(ev_subject_cd = RELATION)도 `build` 296–298에서 "지원하지 않는 근거 주체" 오류가 되어 **적재가 중단됩니다**. 이는 소스 기준 판단이며, 실제로 그런 데이터로 시험하지는 않았습니다.

---

## 7. 구조 차이 및 정합성 문제 (4.6)

각 항목은 다음 순서로 정리합니다: ① 비교 대상, ② PostgreSQL, ③ Neo4j, ④ 데이터 결과, ⑤ 코드, ⑥ 차이, ⑦ 원인, ⑧ 영향도, ⑨ 수정 필요 여부.

### 7.1 PostgreSQL 복합 PK와 Neo4j NODE KEY

1. **비교 대상**: 테이블 PK 8종과 NODE KEY 13종
2. **PostgreSQL**: 3.2절 표. `pg_constraint` contype `p`/`u` 실측
3. **Neo4j**: `SHOW CONSTRAINTS` 결과, NODE_KEY 13개와 `dp_node_key` UNIQUE 1개
4. **데이터**: 노드 key 중복 0, NODE KEY 위반 없음(제약이 있으므로 위반 행이 존재할 수 없음)
5. **코드**: `neo4j_dry_run.PK_FIELDS`(30–44), `neo4j_load_draft.CREATE_CONSTRAINTS`(31–36), MERGE 패턴(84)
6. **차이**:
   - 7개 테이블은 PK와 NODE KEY가 같습니다. 원문 근거만 다릅니다(7.2절).
   - JSONB 노드 5종은 PostgreSQL에 PK가 없고 Neo4j에만 NODE KEY가 있습니다.
   - 모든 노드에 내부 `key`가 따로 있습니다.
   - PostgreSQL의 UNIQUE(`product_cd`, `bnft_cd`, `doc_cd`, `doc_sha256`, `chunk_seq` 등)는 Neo4j에 제약이 없습니다.
7. **원인**:
   - 노드 식별을 PostgreSQL PK와 맞추는 것이 설계 원칙입니다(파일 머리말 3행).
   - 내부 `key`는 라벨이 서로 다른 노드를 `dp_node` 하나로 MATCH해 관계를 만들기 위한 것입니다(94행).
   - 보조 UNIQUE는 원천에서 이미 보장되므로 옮기지 않았습니다.
8. **영향도**: 낮음. 그래프 쪽이 JSONB 키 고유성까지 강제해서 더 엄격합니다.
9. **수정 필요 여부**: 불필요. **분류: 의도된 모델링 차이**

### 7.2 CARD_SOURCE_EVIDENCE의 PK 구조

1. **비교 대상**: 원문 근거의 식별
2. **PostgreSQL**: `PRIMARY KEY (card_doc_id, page_no, card_doc_chunk_id, evidence_id)` + `UNIQUE (evidence_id)`(2026-11-03 PK 승계 적용)
3. **Neo4j**: `dp_card_source_evidence_pk` NODE KEY `(evidence_id)`. 상위 3키는 일반 속성이고 `-[:dp_in_chunk]->(dp_card_doc_chunk)` 경로로도 표현됩니다.
4. **데이터**:
   - 적재된 35개 노드의 상위키 속성이 `source_json`과 같습니다.
   - `dp_in_chunk` 대상 청크가 노드 상위키와 같은지는 키 대조로 확인했습니다(relationships_changed 0).
   - PostgreSQL 연결 상위키 불일치는 0건입니다.
5. **코드**: `PK_FIELDS["card_source_evidence"] = ("evidence_id",)`(38), `build` 226–232
6. **차이**: PostgreSQL 4컬럼 PK와 Neo4j 1컬럼 NODE KEY
7. **원인**:
   - `evidence_id`가 전역 UNIQUE라 1컬럼으로 식별이 충분합니다.
   - PostgreSQL PK 승계는 하위 테이블(`card_evidence_link`)이 상위키를 물려받게 하려는 관계형 설계입니다.
   - 그래프에서는 소속을 관계로 표현합니다.
   - `PK_FIELDS`는 PK 승계 이전 정의를 유지하고 있습니다.
8. **영향도**:
   - 낮음. GraphRAG는 `evidence_id`로 근거를 합치고(`collect_evidence` 319), 문서·페이지는 경로로 읽습니다.
   - 다만 소스 머리말의 "식별자는 실제 PK를 그대로 쓴다"는 원칙과는 문자 그대로 일치하지 않습니다.
9. **수정 필요 여부**:
   - 기능상 불필요합니다.
   - NODE KEY를 4컬럼으로 바꾸려면 제약 재생성과 재적재가 필요합니다. 이 경우 내부 `key` 형식이 바뀌어 기존 노드가 stale 노드가 되고, `main` 139–142에서 적재가 중단됩니다. 그래서 따로 설계 결정이 필요합니다.
   - **분류: 의도된 모델링 차이**(문서화 권장)

### 7.3 PostgreSQL `evidence_link_id`와 Neo4j `ev_link_id`

1. **비교 대상**: 근거 연결 식별자
2. **PostgreSQL**:
   - 컬럼 `evidence_link_id varchar(20)`. 2026-11-03에 `ev_link_id`에서 이름이 바뀌었습니다.
   - PK는 6컬럼 `(card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id, evidence_link_id)`이고, UNIQUE `(card_id, evidence_link_id)`와 자연키 UNIQUE가 있습니다.
3. **Neo4j**:
   - 관계 속성 `ev_link_id`(57/57, STRING)에 관계 제약은 없습니다.
   - 관계 식별은 `r.key`(SHA-256)입니다.
   - 상위키 4개는 관계 속성으로 두지 않습니다(source_json에도 없음).
4. **데이터**: SQL `evidence_link_id AS ev_link_id`와 Cypher `l.ev_link_id`를 비교한 결과 57 = 57로 같습니다(`sql_cypher.evidence_links`).
5. **코드**:
   - `load_snapshot` 109–111: 별칭과 9컬럼만 선택하고, 상위키 3개는 의도적으로 제외합니다(109행 주석).
   - `neo4j_validation.sql` 9–13, `write_transaction` 91–93
6. **차이**: 이름이 다르고, 고유성을 강제하는 주체가 다르며, 관계에 상위키가 없습니다.
7. **원인**:
   - 재적재 없이 PostgreSQL 컬럼명만 바꿨기 때문에, Neo4j 속성명과 그래프 key를 유지하려고 별칭을 썼습니다(코드 주석 "재적재 전까지").
   - 상위키는 이미 `dp_supported_by → dp_card_source_evidence → dp_in_chunk` 경로로 표현됩니다.
8. **영향도**:
   - 낮음. GraphRAG는 `link.ev_subject_cd`, `ev_item_key`만 읽고 `ev_link_id`는 읽지 않습니다(`collect_evidence`, `unresolved_items`).
   - 명명 불일치는 유지보수 혼동의 위험이 있습니다.
9. **수정 필요 여부**:
   - 지금은 불필요합니다.
   - 다음 재적재 때 속성명을 `evidence_link_id`로 바꿀지 결정해야 합니다. 바꾸면 `source_json`이 바뀌어 기존 관계 key가 모두 달라지므로, 재적재 방식(삭제 후 적재)도 함께 결정해야 합니다.
   - **분류: 스키마·매핑 불일치(의도적·임시)**

### 7.4 PostgreSQL에만 있는 AI 추출 이력 테이블

1. **비교 대상**: `card_ai_run`, `card_ai_call`, `card_extr_stg`, `card_excl_item`, `common_code_grp`, `common_cd`
2. **PostgreSQL**: 실행 이력 9건, 호출 이력, 추출 항목 65건(15:10, 증가 중), 제외 사전 0, 공통코드 그룹 41·코드 155
3. **Neo4j**: 대응하는 라벨 없음
4. **데이터**: `card_source_evidence.card_extr_stg_id`만 `source_json`에 남습니다.
5. **코드**:
   - `PK_FIELDS`·`NODE_LABELS`에 없습니다.
   - `prepare`(67–75)가 허용 목록 밖 라벨을 거부합니다(`unexpected node scope`).
6. **차이**: AI 처리 이력과 검토 대기 후보가 그래프에 없습니다.
7. **원인**: 그래프는 답변용 확정·초안 데이터만 담고, 처리 이력과 승인 전 후보는 PostgreSQL이 관리한다는 범위 결정입니다.
8. **영향도**: 없음. GraphRAG 조회는 이 테이블을 쓰지 않습니다. 단, PostgreSQL 공통 혜택 근거 조회(`select_common_bnft_evidence`)는 `card_extr_stg`를 경유합니다(7.6절).
9. **수정 필요 여부**: 불필요. **분류: 의도된 모델링 차이**

### 7.5 Neo4j에만 있는 JSONB 분해 노드

1. **비교 대상**: `dp_bnft_rule`, `dp_rule_target`, `dp_cond_expr`, `dp_cond_branch`, `dp_cond_atom`, 관계 `dp_same_as`
2. **PostgreSQL**: JSONB 컬럼과 복원 뷰(`v_card_rule`, `v_card_rule_target`, `v_card_cond_atom`)
3. **Neo4j**: 노드 57개(6 + 19 + 8 + 9 + 15)와 관계(has_rule 6, targets 34, has_expr 8, has_branch 9, has_atom 15, same_as 1)
4. **데이터**: SQL 뷰와 Cypher의 대조가 같습니다(조건식 15 = 15, 대상 34 = 34). JSON 원본 동일성은 `build` 309–317에서 재확인합니다.
5. **코드**: `build.expression` 183–197, 243–256, 279–286
6. **차이**: PostgreSQL은 문서형(JSONB)으로, Neo4j는 경로형으로 표현합니다. `dp_rule_target`은 원소 34개를 노드 19개로 공유합니다.
7. **원인**:
   - 다중 홉 질의를 위한 설계입니다. 예: `hop3_card_targets`, `hop3_target_cards` 역탐색, 조건 OR/AND 탐색.
   - 대상 공유는 "이용처 → 카드" 역탐색을 위한 것입니다(`build` 251 주석).
8. **영향도**: 긍정적. GraphRAG의 catalog, candidate_relations, benefit_conditions, hop 조회가 이 노드들을 씁니다.
9. **수정 필요 여부**: 불필요. **분류: 의도된 모델링 차이**

### 7.6 신규 PostgreSQL 등록 데이터의 Neo4j 미반영

1. **비교 대상**: 2026-11-03 오후 공통 문서 추출로 생긴 원문 근거
2. **PostgreSQL**: 원문 근거 274건(15:10). 35건 이후 239건이 새로 생겼고 모두 PENDING, 연결 0건
3. **Neo4j**: 원문 근거 35개(적재 이후 변경 없음)
4. **데이터**: `nodes_missing 239`, `relationships_missing 239`(모두 원문 근거와 `dp_in_chunk`). 이미 적재된 노드는 변경 0
5. **코드**:
   - 반영 수단은 `neo4j_load_draft.main`(`--apply`와 확인 문구 필수)뿐입니다. 등록 서비스에는 Neo4j 호출이 없습니다.
   - GraphRAG는 그래프에 없는 혜택을 `pg:` 키로 PostgreSQL에서 읽습니다(`retrieve` 1139–1141).
6. **차이**: PostgreSQL이 먼저 바뀌고 Neo4j는 수동 적재 시점의 스냅샷입니다.
7. **원인**: 적재가 승인 절차를 거치는 수동 배치로 설계되어 있습니다(`EXPECTED_DB`, `CONFIRM`). 지금도 추출이 진행 중입니다(15:10 run 20261103_000016 RUNNING).
8. **영향도**:
   - **현재 GraphRAG 답변에는 영향이 없습니다.**
     - Neo4j의 근거 조회는 `dp_supported_by`(상품·혜택·규칙)나 `dp_same_as`를 거쳐서만 원문 근거에 닿습니다(`benefit_evidence`, `common_benefit_evidence`).
     - 누락된 239건은 연결이 0건이라 적재되더라도 이 경로로는 조회되지 않습니다.
   - **재적재하면 검증이 실패합니다.**
     - `orphan_nodes`(62행)는 모든 원문 근거에 `dp_supported_by`가 있어야 한다고 봅니다. 이 데이터를 그대로 적재하면 239건 이상이 고아로 판정되어 `neo4j_validate`가 실패합니다.
     - 반면 `build`는 연결 없는 근거를 오류가 아니라 통계(`unlinked_evidence`)로만 보고합니다(320–322).
     - 즉 변환기와 검증 규칙의 기준이 다릅니다. 이는 소스로 판단한 것이며, 실제로 재적재해서 확인하지는 않았습니다.
   - **공통 혜택 근거 조회 경로가 두 엔진에서 다릅니다.**
     - PostgreSQL `select_common_bnft_evidence`(187–198)는 `card_common_doc → card_extr_stg(bnft_nm 일치) → card_source_evidence`로 찾습니다. 새 근거도 혜택명이 일치하면 조회됩니다.
     - Neo4j는 `dp_same_as`가 있는 경우에만 찾습니다.
     - 그래서 같은 공통 혜택이라도 엔진에 따라 근거 결과가 다를 수 있습니다. 실제 질문으로는 비교하지 않았습니다.
9. **수정 필요 여부**:
   - **조치 필요(운영 절차)**: 추출과 등록이 끝난 뒤 승인을 받아 재적재하고, 그 전에 다음을 결정해야 합니다.
     - (a) 연결 없는 원문 근거를 적재할지, 아니면 연결된 근거만 적재할지
     - (b) `orphan_nodes`의 원문 근거 규칙을 그에 맞출지
   - **분류: 데이터 동기화 차이**(검증 규칙과 데이터의 충돌은 **추가 확인 필요**)

### 7.7 고아 문서 card_doc 20261103_000012

1. **비교 대상**: 소유 관계가 없는 문서
2. **PostgreSQL**: `card_product_doc`과 `card_common_doc`에 없습니다. JCB `card_common`도 없습니다.
3. **Neo4j**: `dp_card_doc` 노드에 `dp_has_document`가 없습니다.
4. **데이터**: `orphan_nodes` 1건 → `ok False`
5. **코드**: `neo4j_validation.cypher` 65행. 변환기는 문서 노드를 소유 여부와 상관없이 만듭니다(`build` 204–205).
6. **차이**: 없음. 두 DB 상태는 같고, Neo4j 검증 규칙만 이를 문제로 판정합니다.
7. **원인**: JCB 공통서비스가 등록되기 전에 문서만 등록된 것으로 보입니다(추정). PostgreSQL 정합성 뷰에는 해당 게이트가 없습니다.
8. **영향도**: 낮음. GraphRAG는 소유자에서 문서 방향으로만 탐색하므로 이 문서에 닿지 않습니다. 다만 `neo4j_validate` 전체 판정이 계속 실패합니다.
9. **수정 필요 여부**:
   - 등록 담당자가 의도를 확인해야 합니다. JCB 공통서비스를 등록할지, 문서를 보류 상태로 둘지 정해야 합니다.
   - PostgreSQL에 "소유자 없는 문서" 게이트를 둘지는 별도 검토 대상입니다.
   - **분류: 실제 정합성 문제(추가 확인 필요)**

### 7.8 실제 조회 프로그램과의 일치

1. **비교 대상**: `graph_questions.cypher`의 statement 16개가 쓰는 라벨·관계·속성
2. **PostgreSQL**: GraphRAG가 PostgreSQL에서 쓰는 것
   - 후보 검색: `search_card_bnft`·`keyword_card_bnft` 등, pgvector와 문자열
   - 그래프에 없는 혜택의 상세: `select_card_bnft_detail`
   - 제외 판정 원본: `find_exclusions`의 `read_source`
3. **Neo4j**: 사용하는 라벨 13개와 관계 14개, 승격 속성
   - 혜택: `name`, `verification_status`, `limit_text`, `card_bnft_id`, `card_common_bnft_id`, `bnft_valid_from/to_excl`
   - 상품·공통서비스·문서: `product_nm`, `common_nm`, `brand_cd`, `service_grade_cd`, `doc_title`, `card_doc_id`
   - 조건 atom: `kind`, `min_amt`, `excl_raw_txt`, `key_name`
   - 규칙·대상·근거: `rule_key`, `value_num`, `target_nm`, `page_no`, `start_pos`, `evidence_id`
   - 관계: `ev_subject_cd`, `ev_item_key`
4. **데이터**:
   - 위 속성은 모두 Neo4j 실측 속성 목록에 있습니다(3.3절).
   - `common_catalog`는 공통 혜택에 없는 `verification_status` 대신 `null AS status`를 씁니다. `list_benefits`의 `b.verification_status`는 공통 혜택이면 null이 됩니다.
   - `LiveAccuracyTests` 7건 통과(실제 Neo4j, Mock LLM, 20.2초)
5. **코드**:
   - 조회문: `graph_questions.cypher`
   - 실행과 표시: `neo4j_search.py`. `source()` 72–75, `flatten_record` 78–93의 `SOURCE_FIELDS`가 `quote_txt`, `calc_method_cd` 등을 `source_json`에서 꺼냅니다.
   - 답변 데이터: `card_graphrag.benefit_context` 401–421, `condition_groups` 384–398. `cond_basis_cd`, `cond_max_amt_excl`, `cond_status_cd`를 `source_json`에서 읽습니다.
6. **차이**:
   - GraphRAG는 경로 탐색에 승격 속성을 쓰고, 답변 값 대부분은 `source_json`을 해석해 씁니다.
   - 그래서 승격하지 않은 컬럼(`quote_txt`, `calc_method_cd` 등)이 없어도 기능에 문제가 없습니다.
7. **원인**:
   - 속성은 조회 조건에 필요한 것만 올리고, 원본 보존과 검증은 `source_json` 하나로 하는 설계입니다.
   - `node_properties` 머리말에 "NULL은 source_json에만 남는다"고 적혀 있습니다.
8. **영향도**:
   - 낮음. 조회 구조는 실제 데이터와 맞습니다.
   - 다만 `source_json`이 문자열이라 Cypher에서 그 안의 값으로 필터링할 수 없습니다. 예: `calc_method_cd`로 규칙 검색이 불가능합니다. 새로운 질문 유형을 추가하면 승격 속성을 늘려야 할 수 있습니다.
9. **수정 필요 여부**: 현재는 불필요. **분류: 의도된 모델링 차이**(질문 유형 확장 시 재검토)

### 7.9 그 밖의 관찰

| 항목 | 내용 | 분류 |
|---|---|---|
| 날짜형 | `date`가 Neo4j `STRING`이 되어 Cypher 날짜 함수를 바로 쓸 수 없다. 현재 Cypher에서 날짜를 비교하는 곳은 없다(`hop2_card_common`은 반환만 한다) | 의도된 모델링 차이(값 변환) |
| 유효기간 필터 | PostgreSQL 검색 SQL은 `bnft_valid_to_excl > CURRENT_DATE`로 거르지만 Neo4j 조회문에는 유효기간 조건이 없다. 현재 데이터는 모두 유효(종료일 NULL 또는 2027-01-01) | 추가 확인 필요(기간이 지난 혜택이 생길 때) |
| 근거 주체 제한 | `ev_subject_cd`가 CARD/BNFT/RULE 밖(예: RELATION)이면 변환이 중단된다(`build` 296–298). 현재 데이터 0건 | 추가 확인 필요(관계 데이터 도입 시) |
| 카드 조건 상태 | `card_cond_status_cd`가 DRAFT가 아니면 변환이 오류가 된다(200–201). 승인(APPROVED 등) 상태가 생기면 적재가 막힌다 | 추가 확인 필요(현재 의도는 초안 데이터만 적재하는 것으로 보이며, 추정) |
| 공통 혜택 직접 근거 | `card_evidence_link`는 공통 혜택을 주체로 담지 못한다(`select_common_bnft_evidence` 주석). 그래서 Neo4j 공통 혜택에는 `dp_supported_by`가 없다 | 의도된 모델링 차이(설계 한계) |

---

## 8. 최종 요약

| 구분 | 비교 항목 | 분석 결과 | 차이 유형 | 영향도 | 조치 필요 여부 |
|---|---|---|---|---|---|
| 구조 | PK / NODE KEY | 7개 테이블 PK = NODE KEY. 원문 근거만 4컬럼 PK와 `(evidence_id)` NODE KEY로 다름(`evidence_id` 전역 UNIQUE라 식별은 동등). JSONB 노드 5종은 Neo4j에만 NODE KEY | 의도된 모델링 차이 | 낮음 | 불필요(원문 근거 키 차이는 문서화 권장, 변경 시 재적재 설계 필요) |
| 구조 | JSONB 변환 | RULE_LIST·조건식 3종 → 노드·관계로 분해(값·구조 대조 일치). RELATION_LIST·BRAND_OPT_LIST는 변환하지 않고 `source_json`에만 둠(RELATION_LIST 현재 0건) | 의도된 모델링 차이 / RELATION·브랜드 선택지는 추가 확인 필요 | 현재 낮음, 관계 데이터 도입 시 중간 | 현재 불필요. 관계 데이터 도입 전 변환 설계 필요 |
| 관계 | 원문 근거 연결 | `card_evidence_link` 57 = `dp_supported_by` 57, 값 일치. 병렬 13쌍은 SELF/COND 별개 행. 속성명 `ev_link_id` ≠ 컬럼명 `evidence_link_id`(별칭으로 대조) | 스키마·매핑 불일치(의도적·임시) | 낮음 | 다음 재적재 때 속성명 통일 여부 결정 |
| 데이터 | 노드·관계 건수 | Neo4j 200/263, PostgreSQL 예상 439/502(15:10). 공통 범위는 키·값 모두 일치, 원문 근거 239개 누락, 고아 문서 1개 → `neo4j_validate ok False` | 데이터 동기화 차이 + 실제 정합성 문제(고아 문서) | 중간(검증 실패 지속), 답변 영향 없음 | 고아 문서 의도 확인 필요 |
| 동기화 | 신규 문서 반영 | 등록 파이프라인은 Neo4j를 갱신하지 않음(수동 승인 적재). 공통 문서 추출이 진행 중이라 차이가 계속 늘어남. 연결 없는 근거를 적재하면 `orphan_nodes` 규칙과 충돌 | 데이터 동기화 차이 / 검증 규칙은 추가 확인 필요 | 중간 | 필요: 추출·등록이 끝난 뒤 승인 재적재. 그 전에 연결 없는 근거의 적재 범위와 고아 규칙 결정 |
| 조회 | GraphRAG 사용 구조 | 조회문 16개가 쓰는 라벨·관계·속성이 모두 존재. 답변 값은 `source_json`에서 읽음. 실제 Neo4j 통합 테스트 7건 통과. 그래프에 없는 혜택은 PostgreSQL로 대체 조회 | 의도된 모델링 차이 | 낮음 | 불필요(질문 유형 확장 시 승격 속성 재검토) |

### 종합 평가 — GraphRAG 조회 목적에 적합한가

**적합합니다. 다만 현재 Neo4j는 PostgreSQL의 최신 상태가 아닙니다.**

근거는 다음과 같습니다.

1. **식별과 무결성**
   - 노드 식별은 PostgreSQL PK를 그대로 씁니다. 원문 근거만 예외로, 전역 UNIQUE 키 하나를 씁니다.
   - 변환기가 끝점 누락, 키 충돌, JSON 불일치를 만나면 적재를 중단합니다.
   - 물리 FK가 없는 PostgreSQL보다 그래프 쪽 참조 무결성이 적재 시점에 더 강하게 확인됩니다.
2. **값 일치**
   - 적재된 노드 200개와 관계 263개는 `source_json`이 현재 PostgreSQL과 같습니다.
   - 승격 속성도 원본과 모두 같습니다.
   - 조건식, 근거 연결, 규칙 대상, 공통 혜택 적용은 SQL과 Cypher 대조에서 같습니다.
3. **질의 구조**
   - JSONB 규칙·조건식을 노드로 분해해 GraphRAG가 쓰는 탐색이 Cypher 경로로 직접 표현됩니다.
     - 다중 홉: 카드 → 혜택 → 규칙 → 대상
     - 역탐색: 대상 → 카드
     - 조건: OR/AND/NOT
     - 근거: 혜택·규칙 → 원문 근거 → 청크 → 페이지 → 문서
   - 실제 조회문이 쓰는 속성은 모두 있고, 통합 테스트도 통과했습니다.
4. **한계와 미해결 사항**
   - 수동 적재라 최신성이 떨어집니다. 현재 원문 근거 239건 이상이 빠져 있지만, 연결이 없는 근거라 답변에는 영향이 없습니다.
   - 연결 없는 근거를 적재할 때 고아 검증 규칙과 충돌합니다.
   - 소유자 없는 문서 1건 때문에 검증이 계속 실패합니다.
   - RELATION_LIST, 브랜드 선택지, 유효기간 필터, RELATION 근거 주체는 그래프에 없거나 조회에 없습니다.
   - 공통 혜택 근거 경로가 PostgreSQL(추출 항목 경유)과 Neo4j(동일성 관계 경유)에서 다릅니다.

이 차이들은 대부분 의도된 모델링 차이이거나 동기화 운영 문제이고, 설계 오류로 볼 근거는 확인하지 못했습니다. 우선 확인할 것은 두 가지입니다.
- 고아 문서 20261103_000012를 어떻게 처리할지
- 추출이 끝난 뒤 재적재할 때 연결 없는 원문 근거의 처리 기준(변환기와 `orphan_nodes` 규칙을 일치시키는 방향)

---

## 부록 A. 미확인·추정 항목

| 항목 | 상태 |
|---|---|
| 연결 없는 원문 근거를 재적재했을 때 `orphan_nodes`가 실패한다 | 소스 기준 판단(재적재 시험 안 함, 금지 범위) |
| RELATION 주체 연결이 생기면 변환이 중단된다 | 소스 기준 판단(해당 데이터 없음) |
| 공통 혜택 근거 결과가 PostgreSQL과 Neo4j에서 달라진다 | 소스 기준 판단(실제 질문 비교 안 함, B·C 모드는 유료 임베딩 필요) |
| 고아 문서 20261103_000012가 등록 진행 중 상태인지 | 추정(등록 담당자 확인 필요) |
| Neo4j 마지막 적재 시각 | 미확인(그래프에 적재 시각 속성 없음). 현재 그래프는 문서 17건(20261103_000022까지)과 원문 근거 35건(20261102_000065까지) 기준 |
| 15:10 이후 PostgreSQL 건수 | 미확인(추출 진행 중이라 계속 바뀜) |

## 부록 B. 재현용 읽기 전용 조회

```sql
-- PostgreSQL: 원문 근거의 문서·연결 현황
SELECT e.card_doc_id, count(*) AS evidence, count(l.evidence_id) AS linked
FROM db_pipeline.card_source_evidence e
LEFT JOIN (SELECT DISTINCT evidence_id FROM db_pipeline.card_evidence_link) l ON l.evidence_id = e.evidence_id
GROUP BY e.card_doc_id ORDER BY 1;

-- PostgreSQL: 소유자 없는 문서
SELECT d.card_doc_id, d.doc_title FROM db_pipeline.card_doc d
WHERE NOT EXISTS (SELECT 1 FROM db_pipeline.card_product_doc p WHERE p.card_doc_id = d.card_doc_id)
  AND NOT EXISTS (SELECT 1 FROM db_pipeline.card_common_doc c WHERE c.card_doc_id = d.card_doc_id);
```

```cypher
// Neo4j: 라벨별 속성과 자료형
MATCH (n:dp_node) WITH [l IN labels(n) WHERE l <> 'dp_node'][0] AS label, n
UNWIND keys(n) AS k RETURN label, k, count(*) AS n, collect(DISTINCT valueType(n[k]))[0..3] AS types ORDER BY label, k;

// Neo4j: 같은 쌍 사이 근거 연결 병렬 관계
MATCH (a:dp_node)-[r:dp_supported_by]->(b) WITH a, b, collect(r) AS rs WHERE size(rs) > 1
RETURN b.evidence_id, [x IN rs | [x.ev_link_id, x.ev_item_cd, x.ev_item_key]];
```

```text
# 전체 대조 (읽기 전용)
PYTHONPATH=src python -m card_benefit.payment_card.db_pipeline.neo4j_validate
# 실제 Neo4j + Mock LLM GraphRAG 통합 테스트
RUN_NEO4J_INTEGRATION=1 PYTHONPATH=src python -m unittest card_benefit.payment_card.tests.test_card_graphrag.LiveAccuracyTests
```
