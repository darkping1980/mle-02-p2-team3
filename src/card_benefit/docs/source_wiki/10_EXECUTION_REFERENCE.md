# 10. 실행·파일·SQL 참조

[목차](README.md)

<details><summary>▼ 10.1 진입점별 호출 관계</summary>

| 실행/진입 | 핵심 호출 | 목적 |
|---|---|---|
| [`db_pipeline.main`](../../payment_card/db_pipeline/main.py) | `RegisterService.register` → `DocumentService` / `DocRepository` | PDF 원문 등록 및 선택 연결 |
| [`terra_main`](../../payment_card/db_pipeline/terra_main.py) | `ExtractionService.run` → `ExtractionRepository` | AI 후보·근거 추출 |
| [`benefit_main`](../../payment_card/db_pipeline/benefit_main.py) | Product/Common benefit services | 혜택 확정 등록 및 공통 카드 적용 |
| [`embedding_main`](../../payment_card/db_pipeline/embedding_main.py) | `EmbeddingService.sync` → `EmbeddingRepository` | 검색 텍스트와 벡터 생성 |
| [`streamlit_app`](../../payment_card/db_pipeline_origin_search/streamlit_app.py) | `get_pipeline` → `CardGraphRAG.run` | 조회·답변 UI |
| [`neo4j_load_draft`](../../payment_card/db_pipeline/neo4j_load_draft.py) | PostgreSQL export/Neo4j write helpers | 그래프 동기화 구현/운영 도구 경로 |

각 단계를 한 프로세스가 반드시 연속 실행하는 구조는 아니다. CLI 선택과 작업자가 지정하는 run/IDs에 따라 독립적으로 실행한다.
</details>

<details><summary>▼ 10.2 SQL Mapper 연결표</summary>

Python에서 실제 statement 이름은 Repository 메서드의 호출 문자열과 Mapper의 `-- name:`를 대조한다.

| Mapper | 주요 statement | 주요 테이블 |
|---|---|---|
| [`document_repository.sql`](../../payment_card/db_pipeline/document_repository.sql) | `select_doc_by_sha256_or_cd`, `insert_doc`, `insert_doc_page!`, `insert_doc_chunk!`, `verify_doc`, `select_table_counts`, `insert_product_doc_link` | `card_doc`, `card_doc_page`, `card_doc_chunk`, `card_product_doc`, `card_product` |
| [`extraction_repository.sql`](../../payment_card/db_pipeline/extraction_repository.sql) | `select_ai_input_chunks`, `select_blocked_pages`, `insert_run`, `insert_call!`, `insert_stg`, `insert_evidence!`, `update_stg_merge!`, `finish_run!` | `card_doc*`, `card_ai_run`, `card_ai_call`, `card_extr_stg`, `card_source_evidence` |
| [`common_benefit_repository.sql`](../../payment_card/db_pipeline/common_benefit_repository.sql) | `lock_card`, `integrity_errors`, `select_merged_benefits`, `insert_local_benefit`, `insert_evidence_link`, `insert_common`, `insert_common_bnft`, `insert_common_apply` | `card_product_item`, `card_common*`, evidence/link tables |
| [`embedding_repository.sql`](../../payment_card/db_pipeline/embedding_repository.sql) | `select_*_rows`, `update_*_text`, `update_*_embedding!`, `start_embedding_run`, `finish_embedding_run!`, `search_*`, `keyword_*`, `select_*_detail` | `card_product_item`, `card_common_bnft`, `card_ai_run`, `card_product`, rule target/evidence views |

Mapper 파일 내 statement 선언 위치는 VS Code 링크로 열어 `-- name:`을 찾는다. 줄 링크는 `#L` URL 규칙으로 고정하되 실제 statement line을 기계적으로 확인한 링크만 메서드 수준 링크로 제공한다. SQL/DDL은 [6장](06_POSTGRESQL_SCHEMA.md).
</details>

<details><summary>▼ 10.3 Cypher Mapper 참조</summary>

[`graph_questions.cypher`](../../payment_card/db_pipeline_origin_search/graph_questions.cypher)의 `// name:` 쿼리를 [`neo4j_search.py`](../../payment_card/db_pipeline_origin_search/neo4j_search.py)에서 로드한다. 주요 대응:

| Statement | 호출 지점 |
|---|---|
| `catalog`, `item_catalog`, `common_catalog` | `Neo4jSearch.list_catalog()` |
| `list_benefits` | `list_benefits()` |
| `candidate_relations` | `candidate_relations()` |
| `benefit_context`, `benefit_rules`, `benefit_conditions`, `benefit_limits`, evidence 계열 | `get_detail()` |
| `hop*` | `hop()` 및 검증 경로; 일반 GraphRAG retrieve에서 호출되는지와 구분 |

실행은 READ_ACCESS/`execute_read`. 쿼리는 [7장](07_NEO4J_SYNC.md).
</details>

<details><summary>▼ 10.4 분석 범위·한계 및 점검 집계</summary>

- 기준 커밋: `7b37de03b17a9671d703f183ec83b386c78d98f7`.
- 운영 DB 접속, SQL 실행, 그래프 적재, 임베딩/LLM API 호출: 수행하지 않음.
- 아래 수치와 링크 검사 결과는 문서 전체 생성 후 소스 AST/Mapper/링크를 실제 점검해 확정한다. 소스 파일 수는 10개 핵심 모듈 기준이며 프로젝트 전체 파일 수로 오인하지 않는다.
- DDL, migration, sample dump 간 schema drift 및 운영 반영 여부: 운영 DB 적용 여부 미확인.

</details>

[목차](README.md) · [PDF 등록](01_PDF_REGISTRATION.md) · [조회](08_GRAPHRAG_QUERY.md)

