# PostgreSQL → Neo4j 전체 재구축 기록

## 목표와 원천 DB

이 문서는 2026-11-06에 수행한 db_pipeline 원장 기준 dp_ 그래프 재구축의 실제 실행 기록입니다. PostgreSQL은 원장으로 유지하고 Neo4j는 질문 검색과 관계 탐색에 쓰는 읽기 모델로 구성했습니다. PostgreSQL 스키마는 변경하지 않았습니다.

실제 PostgreSQL은 postgres, PostgreSQL 17.11이며 db_pipeline에 기본 테이블 20개와 뷰 8개가 있습니다. 모든 기본 테이블에서 PK를 확인했고 선언된 FK는 없습니다. 실행 로그 app_log, app_log_event_archive는 원천 PostgreSQL에 남기고 그래프에서 제외했습니다. 나머지 기본 테이블 18개, 4,359행은 전부 그래프 모델에 반영했습니다. 테이블별 PK·행 수·관계 표는 POSTGRESQL_TO_NEO4J_SCHEMA_MAPPING.md에 기록했습니다.

## 그래프 모델

일반 원장 테이블은 dp_<table> 노드로, 순수 연결 테이블은 원본 행 전체를 source_json에 보존하는 Relationship으로 옮겼습니다. 모든 노드는 dp_node와 테이블별 라벨을 함께 가집니다. 복합 PK를 포함한 원래 PK 의미는 정규 JSON 배열 문자열 key로 유지하고, 원본 전체 행은 source_json, 원본 NULL 컬럼 목록은 null_columns_json에 저장합니다. Neo4j 속성으로 직접 저장할 수 없는 복합 자료형은 JSON 직렬화했습니다.

18개 관계 유형:

dp_applies_to, dp_backup_of_card, dp_belongs_to, dp_called_in_run, dp_called_on_chunk, dp_child_of_candidate, dp_code_in_group, dp_extracted_by_call, dp_extracted_for_card, dp_from_extraction, dp_has_document, dp_has_item, dp_in_chunk, dp_in_document, dp_on_page, dp_supported_by, dp_supported_by_extraction, dp_targets_document.

직접 선언 FK가 없는 DB이므로 관계는 실제 컬럼 값과 대상 PK를 대조한 FK 등가 매핑입니다. 연결 컬럼이 비어 있으면 관계를 만들지 않고, 값이 있는데 정확한 대상이 없거나 여러 개인 경우 적재를 중단하게 했습니다. 관계 테이블 card_evidence_link는 ev_subject_cd를 확인해 카드 또는 card_product_item 소유자에서 card_source_evidence로 연결하고 rule_key, ev_subject_cd 등 원본 속성을 보존합니다.

card_product_item은 dp_card_product_item 한 노드입니다. item_data, rule_list, relation_list, item_cond_expr JSON을 원본 값 그대로 보존하며 dp_card_bnft, dp_bnft_rule, dp_cond_expr, dp_cond_branch, dp_cond_atom, dp_rule_target 노드를 생성하지 않습니다. 검색 텍스트는 원장 컬럼에서 투영하고 원본 1,536차원 벡터를 재사용했습니다.

관계 추출 원장에 근거 소유 링크가 직접 없는 경우에도, 직접 연결된 근거의 card_extr_stg_id와 동일한 staging ID를 가진 Evidence만 같은 혜택 근거로 확장합니다. 파생 관계는 원천 행, 직접 연결 anchor, 근거 출처를 관계 source_json에 함께 보존합니다. 이 경로로 POINT II의 근거 20261105_002745(60만원 조건)와 20261105_002740(2만원 한도)가 동일 staging ID에서 혜택 문맥으로 함께 조회됩니다. 관련 staging 검토 상태 LINK_REVIEW는 원천 값 그대로 유지되어 수동 검수가 필요한 상태입니다.

공통 혜택 PDF 연결은 직접 FK가 없으므로 공통 서비스 문서, 정확히 일치하는 추출 혜택명, staging ID, Evidence를 모두 확인한 경우에만 파생 관계를 만들었습니다. 관계 파생 근거는 source_table의 derived: 표시와 관계 source_json으로 추적합니다.

## 적재·검증 실행 순서

코드의 실행 절차는 아래와 같습니다. 실제 실행은 이 작업에서 완료했습니다.

```powershell
.\.venv\Scripts\python.exe -m src.card_benefit.payment_card.db_pipeline.neo4j_dry_run --schema-only
.\.venv\Scripts\python.exe -m src.card_benefit.payment_card.db_pipeline.neo4j_dry_run --dry-run
.\.venv\Scripts\python.exe -m src.card_benefit.payment_card.db_pipeline.neo4j_load_draft
.\.venv\Scripts\python.exe -m src.card_benefit.payment_card.db_pipeline.neo4j_load_draft --apply --confirm APPROVED_DP_POSTGRES_REBUILD
.\.venv\Scripts\python.exe -m src.card_benefit.payment_card.db_pipeline.neo4j_validate
```

재구축은 PostgreSQL repeatable-read, read-only snapshot을 사용합니다. 쓰기 전 DB 이름과 프로젝트 Neo4j database 식별자를 대조하고, 기존 dp_ 그래프에 외부 관계가 있으면 중단합니다. 기존 그래프 백업을 확인한 뒤 dp_ label 노드·관계·제약·인덱스만 제거하고, Neo4j 데이터베이스 자체는 삭제하지 않습니다. 새 노드/관계 적재 후 원천 snapshot과 각 노드·관계 속성의 정확한 비교를 수행합니다.

## 실제 재구축 결과

- Neo4j database: 6ac1f0f8 (프로젝트 설정의 기존 DB와 일치).
- 기존 dp_ 그래프 사전 백업: tmp/neo4j_dp_backup_20261106.json.gz, 1,635 노드, 2,702 관계, 15 제약, 19 인덱스; SHA-256 2d639a26cce270aa679b418b401b45c245ce7681675dffb92740cf3648102189.
- 삭제 전 프로젝트 외부 관계: 0. 다른 프로젝트 label/relationship은 삭제하지 않았습니다.
- 새 적재: 4,359 노드, 8,648 관계. 모든 18개 비로그 테이블의 4,359행을 반영했습니다.
- Label: 공통 dp_node와 14개 테이블별 노드 유형.
- 제약조건: 15개. 원본 PK 제약이 모두 생성됐습니다.
- 인덱스: 19개, 모두 ONLINE; 키워드 Fulltext 인덱스와 원본 1,536차원 cosine 벡터 인덱스가 정상입니다.
- 검증: 원천과 Neo4j의 노드, 관계, 속성 차이 0; 누락·추가 노드/관계 0; 외부 관계 0; 전체 검증 ok=true.
- 5개 고립 노드는 card_ai_run 실행 원장 행이며 대상 문서 키가 NULL 또는 미일치여서 연결할 원천 참조가 없었습니다. 원장 행은 삭제하지 않았습니다.

삭제 전 백업은 재구축 전 상태의 Neo4j JSON export입니다. 이 파일은 Neo4j native backup이 아니므로 기존 DB 복구 시에는 별도 복원 코드/절차가 필요합니다. 재구축 apply는 원천 스냅샷 생성 이후 수행하므로 실패 시 원천 PostgreSQL에서 다시 적재할 수 있습니다.

## 검색 및 답변 경로

기본 Streamlit 검색 모드는 N이며 Neo4jBenefitSearch만 사용합니다. 질문 실행 시 PostgreSQL 업무 원장을 조회하지 않습니다. 흐름은 interpret → retrieve → answer → finish입니다.

- interpret: Neo4j 카드·혜택 카탈로그, 키워드 및 1,536차원 벡터 검색을 결합하고 Reciprocal Rank Fusion으로 후보를 정리합니다.
- retrieve: 선택한 dp_card_product_item 또는 dp_card_common_bnft 원장 노드, 카드, 전체 JSON 텍스트, 연결된 PDF Evidence/페이지/청크/문서와 동일 staging 원문을 가져옵니다.
- answer: 조회 문맥과 PDF 원문을 모델에 전달합니다. 별도 할인 계산 엔진은 만들지 않았습니다.
- validate: 답변 숫자와 조건 연결을 텍스트 및 PDF 근거로 검증하고, 원문에서 관계가 확인되지 않으면 확정 답변으로 표시하지 않습니다.

### POINT II 근거 회귀 확인

질문: “카드의정석 POINT II에서 전월 실적이 60만원이면 특별·추가 적립의 통합 월 한도는 얼마야?”

Neo4j에는 카드 상품 ID 23과 혜택 원장 ID 20261105_000100이 dp_has_item으로 연결되어 있습니다. 원문 PDF의 3페이지 동일 행은 “전월 국내가맹점 이용실적 60만원 이상 | 특별/추가 적립 | 2만원”입니다. card_extr_stg의 r2.conditions.c2 / limit_keys=[l2] / l2.limit_num=20000도 600,000→20,000 대응을 담고 있습니다. Evidence 20261105_002745는 조건, 20261105_002740은 금액을 인용하며 둘 다 문서 20261105_000043, p.3, chunk 20261105_000176에 있습니다. 파생 텍스트는 해당 조건·한도 대응을 표시하되 stg_sql_check_cd=LINK_REVIEW 상태도 노출해 수동 검수가 필요함을 숨기지 않습니다.

실제 GraphRAG live read 통합 probe는 키워드·벡터·RRF 후보를 반환하고 대상 카드/혜택을 선택했으며, 혜택 상세에 다음 연결을 구성했습니다: 30만원 이상→1만원, 60만원 이상→2만원, 120만원 이상→5만원. 벡터 검색은 원장에 저장된 기존 벡터를 입력으로 사용해 새 임베딩을 생성하지 않았습니다. 이 probe는 GraphRAG 검색·retrieve 검증이며 LLM answer 생성 또는 브라우저 UI 테스트를 뜻하지 않습니다.

## 수정 파일과 범위

- 변환/모델: db_pipeline/neo4j_relational_model.py, neo4j_dry_run.py, neo4j_load_draft.py, neo4j_validate.py, neo4j_validation.sql, neo4j_validation.cypher.
- 구형 점진 적재 경로: neo4j_relation_sync.py, neo4j_search_projection_sync.py는 사용하지 못하도록 차단해 구형 label 재생성을 막습니다.
- 조회/GraphRAG: db_pipeline_origin_search/graph_questions.cypher, neo4j_search.py, neo4j_hybrid_search.py, card_graphrag.py, benefit_search_text.py, execution_log.py.
- 회귀 테스트: 변환, dry-run, load guard, validate, legacy sync guard, hybrid search, limit tier 테스트를 새 데이터 계약에 맞췄습니다.

## 테스트, 제약 및 남은 확인

- 로컬 회귀 테스트: 13개 관련 테스트 파일, 65 passed, 3 skipped.
- 실제 Neo4j read-only 원천 비교/인덱스/관계 검증: 성공, 4,359 노드와 8,648 관계.
- 실제 Neo4j 읽기 통합: 25 passed. 키워드/배치 키워드/공통 혜택/후보 관계, POINT II Evidence 페이지·청크, 1홉/2홉 쿼리를 확인했습니다.
- Streamlit AppTest: 실제 form input과 submit을 동일 rerun으로 수행했습니다. N GraphRAG의 keyword/vector/RRF 검색, POINT II 혜택 ID `20261105_000100`, PDF Evidence 18건, 응답 `2만원`, 상태 `ANSWERED`, 검증 `RAW_MATCH`를 확인했습니다. 답변 근거는 조건 Evidence `20261105_002745`, 금액 `20261105_002740`, 한도 `20261105_002742`, 혜택 유형 `20261105_002743`이며 모두 PDF 3페이지입니다. 파생 staging 데이터가 `LINK_REVIEW`인 점을 알리는 경고도 남았습니다.
- AppTest 첫 하네스는 PowerShell stdin 인코딩으로 한글 버튼명 비교가 실패했고, 두 번째는 Streamlit form 값을 제출 전에 별도로 rerun해 초기화했습니다. `st.form_submit_button` 자체나 Streamlit UI 코드는 고치지 않고, 파일 인코딩이 유지되는 테스트 스크립트에서 입력·버튼 click을 한 run으로 묶었습니다.
- 수정 전 실제 `interpret` 쿼리는 종료 세미콜론 때문에 실패했습니다. 이를 제거하고 retrieve 쿼리의 `rule_key` 반환열을 추가했습니다. 이 수정 경로를 반영한 이후의 실시간 AppTest는 정상 답변을 반환했습니다. 상세 Cypher 오류는 작업 이력에 남겼습니다.
- 실제 카드 간 자연어 비교 질문과 전체 평가셋 의미 정확도는 별도 실행 검수가 남아 있습니다. 1홉/2홉 read query는 live 테스트로 실행했고 사용자 답변 품질의 전 문항 검수와는 구분합니다.
