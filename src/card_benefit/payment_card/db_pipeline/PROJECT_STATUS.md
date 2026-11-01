# 카드 혜택 GraphRAG — db_pipeline 개발 현황

이 문서는 현재 코드, 테스트와 개발 DB의 읽기 전용 조회를 기준으로 한 인수인계 문서다. 작업을 진행하면 완료 상태와 미확정 사항을 함께 갱신한다. 실행 및 운영 사용법은 [README](README.md)를 참고한다.

## 1. 목적과 처리 경로

카드 PDF에서 혜택, 대상, 조건, 한도와 혜택 간 관계를 추출하고 원문 근거와 함께 검증한다. PostgreSQL `db_pipeline` V6은 원문·추출 후보·검증 결과와 향후 확정 업무 데이터를 관리한다. 검증된 관계를 Neo4j로 변환하여 GraphRAG에 활용하는 것은 **향후 작업**이다. PostgreSQL 검색과 Neo4j 검색도 각각 별도로 구현하고 비교할 계획이다.

`db_pipeline`은 원문과 결과를 PostgreSQL 중심으로 처리한다. 팀원의 `file_pipeline`은 같은 원천 문서를 별도 경로로 처리하는 독립 구현이며 서로의 처리 결과를 입력으로 쓰지 않는다.

```text
PDF + manifest → 문서·페이지·PAGE_V1 청크 → 텍스트 + 페이지 이미지
  → Terra / PageExtraction → 원문·값·연결 검증 → staging·근거·통합 결과
  → [향후 검토·승인] 확정 업무 데이터 → [향후] Neo4j·검색
```

## 2. 구현된 구성과 파일

아래 경로는 이 문서가 있는 `db_pipeline/` 기준이다. Python Repository가 호출하는 SQL은 같은 이름의 Named SQL Mapper다. 파일명은 Mapper namespace가 된다.

| 경로 | 현재 역할 |
|---|---|
| [main.py](main.py), [register_service.py](register_service.py) | PDF 문서 등록 CLI와 중복 확인·등록·검증 트랜잭션. `--apply` 없이는 등록하지 않음 |
| [document_service.py](document_service.py) | PDF와 manifest 확인, PyMuPDF 텍스트 추출, 페이지·청크 생성 |
| [document_repository.py](document_repository.py), [document_repository.sql](document_repository.sql) | 문서·페이지·청크 저장과 OCR 검토, AI 입력 조회 |
| [document_storage.py](document_storage.py), [storage_main.py](storage_main.py) | 원본 PDF를 별도 Storage 경로 `pdf/{doc_sha256}.pdf`로 관리. 해시 검사·조회·업로드·복원. 페이지 이미지는 저장하지 않음 |
| [extraction_schema.py](extraction_schema.py) | 페이지 단위 `PageExtraction`과 근거·검증·문서 통합 Pydantic 모델. `EXTRACT_SCHEMA_V1`, `MERGE_V1` |
| [extraction_service.py](extraction_service.py) | 페이지 입력 생성, 호출 결과 검증, 원문 위치·값·혜택 연결 검사, 페이지 항목 저장과 실행 내 문서 통합·V6 JSONB 정규화 |
| [extraction_repository.py](extraction_repository.py), [extraction_repository.sql](extraction_repository.sql) | AI 실행·호출·후보·근거 저장과 검토 큐·정규화 결과 조회 |
| [terra_client.py](terra_client.py) | 주입받은 OpenAI 클라이언트로 `gpt-6.1-terra`, `medium`, 이미지·텍스트와 Pydantic 기반 strict JSON Schema 전송; 토큰 기반 비용 계산 |
| [terra_main.py](terra_main.py) | 페이지별 CLI. 기본은 비용 dry-run, `--preflight`는 DB 읽기 전용 입력 검사, `--execute`는 실제 호출과 중간 데이터 저장 |
| [one_pick_style_product_insert_draft.sql](one_pick_style_product_insert_draft.sql) | A3 수동 등록 SQL. Named SQL Mapper가 아님 |
| [V6 DDL](../../sql/db_pipeline_schemaV6_draft.sql), [공통코드 Seed](../../sql/db_pipeline_common_code_seedV6.sql) | 스키마 정의와 공통코드. 실제 DB와의 차이는 변경 전 별도 확인 |

`PAGE_V1`은 내용이 있는 페이지마다 페이지 전체 텍스트를 청크 1건으로 저장한다. AI 입력 시 로컬 PDF 해시를 대조하고 페이지를 150 DPI PNG로 렌더링한다. OCR 검토가 필요한 페이지는 `page_note`에 `OCR_REVIEW`를 남기고 청크를 `EXCLUDED`로 두어 AI 입력에서 제외한다. 검토 후의 승인 흐름은 문서 Mapper에 있다. OCR 문구 자체를 수정한 뒤 페이지와 청크를 다시 구성하는 기능은 미구현이다.

`ExtractionService`는 호출 이력, 페이지 항목·근거, 문서 통합을 별도 단계로 저장한다. `card_ai_call`의 원본 응답과 토큰을 보존하고, `card_extr_stg`의 원본 JSON과 정규화 JSON을 분리한다. 여러 근거는 `card_source_evidence`에 연결한다. 제외 페이지가 있으면 실행을 `PARTIAL`로 기록한다. 각 실행의 결과는 이전 실행을 덮어쓰지 않는다.

## 3. 유지할 설계와 운영 원칙

- V6 DDL은 별도 승인 없이 변경하지 않는다. 현재 설계는 물리 FK 없이 논리 관계와 SQL 정합성 검증을 사용한다.
- LLM은 원문을 바탕으로 `PageExtraction`을 반환한다. DB ID와 V6 내부 조건식은 LLM이 만들지 않고 Python이 검증·정규화한다.
- 원문에 값이 있는지와 그 값이 어떤 혜택에 연결되는지는 별도로 검사한다. 표 이미지에 의존하는 연결은 사람이 검토한다.
- 미검토 추출 후보를 `card_bnft`, `card_limit_pool` 등 확정 업무 데이터에 반영하지 않는다. 실제 API 호출과 DB 변경은 별도 승인 후 수행한다.
- 예산 검사는 입력 토큰 추정, 최대 출력과 기록된 사용량을 이용한다. 이미지 토큰 추정과 실제 청구액이 다를 수 있으므로 목표 예산 $1은 절대적인 청구 상한이 아니다. 사용량이 없는 기존 호출은 후속 실행을 막는다.
- 상품·문서 관계 `PENDING`과 추출 항목 `PENDING_REVIEW`는 승인 완료를 뜻하지 않는다. 원천 문서의 최신판 여부도 별도 확인한다.

## 4. A3 초기 상품 등록 이력

초기 A3 등록 이력이다. A7-2 초기화 후 아래 ID는 더 이상 현재 DB의 상품·문서 ID가 아니다. 현재 상태는 8절을 참고한다.

| 항목 | 확인값 |
|---|---|
| `card_id` / `product_cd` | `1` / `HANA_DEBIT_ONE_PICK_STYLE` |
| 상품명 | ONE PICK STYLE 하나 체크카드 |
| `card_doc_id` | `20261031_000001` |
| 상품·문서 관계 | `PRODUCT_GUIDE` / `PENDING` |
| 기존 `card_doc.card_id` | `NULL` |

출시일은 분석 PDF 2쪽에 기재된 2026-03-30이다. 상품 `ACTIVE`는 2026-10-30 수집 당시 발급 가능 기록을 근거로 한 개발 데이터이며 실시간 발급 상태를 보증하지 않는다. PDF는 공식 서버에서 확인됐으나 상품 페이지의 해당 PDF 직접 링크와 최신판 여부는 미확인이다.

## 5. Terra 1페이지 최초 실측 이력

초기화 전 개발 DB에서 확인한 최초 실측 이력이다. 원본은 백업됐고 현재 DB에는 재생 실행이 저장돼 있다(8절). 모델 설정은 코드의 `medium`이며, 실행 이력의 `run_param`에는 reasoning effort가 별도 필드로 기록돼 있지 않다.

| 항목 | 결과 |
|---|---|
| 모델 / AI 실행 ID | `gpt-6.1-terra` / `20261031_000001` |
| 실행 상태 / 호출 범위 | `PARTIAL`; 1쪽 1회, 2쪽 제외 기록 |
| 호출 | `card_ai_call` 1건 `SUCCEEDED`; 원문 응답 및 파싱 JSON 존재 |
| 입력 / 출력 | 6,794 / 6,815 토큰 |
| 계산 비용 | $0.040869. 토큰과 단가에 따른 계산값이며 청구서 실측액은 미확인 |
| Pydantic | 파싱 성공; 페이지 번호 일치 |
| `card_extr_stg` | 혜택 4건, 카드 조건 4건. 모두 `PENDING_REVIEW` |
| `card_source_evidence` | 30건, 위치 미확인 0건. 근거 승인 대기 |
| 확정 업무 데이터 | `card_id=1`의 `card_bnft`, `card_limit_pool` 0건 확인 |

2026-10-31 최초 실행 원본은 초기화 전 로컬 백업에 남아 있고 현재 DB는 새 실행 ID의 재생 결과다. 실행 ID와 문서 ID가 같은 문자열이어도 서로 다른 테이블의 독립 식별자다. 조회용 Named SQL은 [extraction_repository.sql](extraction_repository.sql)의 `select_run_calls`, `select_review_queue`, `select_merged_benefits`, `select_merged_rules`, `select_merged_limits`, `select_merged_conditions`, `select_item_evidence`, `select_contract_check`를 참고한다.

## 6. 정확도와 검토 필요 항목

PDF 1쪽 표 이미지와 추출 결과를 대조한 결과, ONE PICK→월 30회와 STYLE→월 10회의 **혜택 연결이 맞다**. 각 혜택의 일 1회, 월 5천원, 3천원 이상 100원·1만원 이상 500원 캐시백도 추출됐다. ONE MORE 대중교통 5% 캐시백과 놀이공원 50% 현장할인도 구분했다. 이 확인은 해당 사례의 대조이며 전체 정확도를 뜻하지 않는다.

| 검토 필요 사항 | 현재 관찰 |
|---|---|
| 일별 한도 근거 | ONE PICK과 STYLE의 일 1회 값은 맞지만 일별 한도 키에 직접 연결된 근거가 없어 두 혜택 모두 `NO_EVIDENCE` |
| 실적 조건 없음 | 원문 문구는 인용했으나 두 혜택의 `no_condition_stated`는 `false`; 해당 필드의 의미와 표현 방법 검토 필요 |
| 100원·500원 관계 | 1만원 이상에서 두 규칙의 중복 또는 우선 적용 여부를 모델이 `unresolved`로 보류. 원문 추가 확인 필요 |
| 대중교통 | 조건 원문 표기와 인용의 일치 검사에서 `VALUE_NOT_IN_QUOTE` |
| 놀이공원 | 일부 한도에 직접 연결된 근거가 없어 `NO_EVIDENCE`; 1인 1매의 기간·단위 표현도 검토 필요 |
| 표 및 반복 문구 | 네 혜택의 연결은 사람 검토 대상. 반복되는 `월 5천원`은 텍스트 위치만으로 표의 어느 행인지 확정하기 어려움 |

4개 카드 조건은 SQL 검사에서 `OK`였지만 이 역시 승인 상태는 아니다. 실적 산정 제외와 서비스 적용 제외는 원문상 다른 범위이므로 정규화 결과에서 계속 구별한다.

## 7. 테스트와 다음 단계

현재 추출·Terra·사전 검증 테스트를 로컬에서 실행한 결과 **63개 통과, 7개 subtest 통과**다. Mock 및 단위 테스트이므로 실제 모델의 전체 정확도나 운영 DB 적재를 보장하지 않는다.

1. 1페이지 원본 JSON, 근거 위치, 표 행과 혜택 관계를 정밀 검토한다.
2. 일별 한도의 근거 연결, 실적 조건 없음의 구조화, 인용 검증 및 반복 문구 문제를 분석한다.
3. 별도 승인 후 2페이지 Terra 추출 여부를 결정한다. 1쪽과 2쪽을 별도 실행하면 실행 ID가 달라 **서로 다른 실행 결과는 자동 문서 병합되지 않는다.**
4. 페이지별 결과의 문서 단위 병합과 충돌·누락 검증 방식을 결정한다.
5. 중간 데이터의 사람 검토·승인 후 확정 업무 테이블에 반영하는 절차를 구현한다.
6. 검증된 데이터의 Neo4j 그래프 모델과 변환을 구현한다.
7. PostgreSQL과 Neo4j 검색을 각각 구현하고 비교한다.

README의 ‘실제 모델 연결 전’이라는 기존 문구는 이번 상태 문서 작성 시점의 Terra 연결·1쪽 실측 결과보다 오래된 설명이다. README 본문 수정은 별도 범위에서 정리한다.

## 8. A7-2 개발 DB DRAFT 적재 시험

사용자 승인 후 19개 테이블을 초기화하고 공통코드·시퀀스·Storage는 유지했다. 상품 `card_id=2`, 문서 `20261101_000002`를 재등록하고, 기존 응답을 네트워크 없는 Mock으로 재생한 AI 실행 `20261101_000002`을 생성했다. 재생 모델명은 `REPLAY:gpt-6.1-terra`이며 기록된 토큰은 원래 실측 사용량이다. 최초 이력 CSV 백업은 비상용으로 보관하며 전체 CSV 복원 실행은 하지 않았다.

정책 `20261101_000001` DRAFT 1건, 혜택 PENDING_REVIEW 4건, 한도 9건, 방법 UNEXECUTABLE 2건, 근거 관계 40건을 시험 등록했다. **`valid_from=2026-03-30`과 한도 집계 `CARD_MEMBER`는 원문으로 확정되지 않은 테스트 가정이다.** 현재 게이트는 source evidence 미승인 `evidence_not_approved` 30건이다. `method_not_in_catalog` 2건을 확인 후 설명용 방법 2건으로 해소했고, 풀 고아·공통코드 오류는 SAVEPOINT 오류 주입 후 롤백으로 검출을 확인했다. 상세·한계는 [A7-2 실제 적재 검증](A7_2_V6_ACTUAL_LOAD_TEST.md)을 참고한다.

이 데이터는 검토·승인되지 않은 시험 데이터다. `v_card_bnft_rule_effective`는 LOCAL DRAFT를 자동으로 배제하지 않으므로 소비 시 승인·검증 상태를 별도 검사해야 한다. 기존 Terra 비용 조회는 REPLAY 모델명을 집계하지 않아 과거 실제 비용 $0.040869를 후속 실측 예산에서 별도로 고려해야 한다. Neo4j 확정 변환은 보류한다.

## 9. A7-4 정책 원문 근거 보완

2026-11-01 개발 DB에서 PDF 2쪽 부가서비스 유지·변경·고지 원문을 PENDING source evidence `20261101_000061`과 정책 연결 `20261101_000041`로 추가했다. 현재 원문 근거 31건, 정책 근거 연결 41건이며 `evidence_not_approved` 31건이다. 나머지 혜택 4건·규칙 6건·풀 9건은 DRAFT 시험 상태 그대로다. 2쪽 전체는 이미 페이지·청크로 저장됐지만 각 조항의 업무 구조화와 업무 승인 완료는 아니다. 상세 조회·그래프 초안은 [PostgreSQL과 Neo4j 구조 비교](POSTGRESQL_TO_NEO4J_STRUCTURE_COMPARISON.md)를 참조한다. Neo4j 실제 적재는 별도 승인 전 미실행이다.

최종 재조회에서 구조 검증은 구현된 게이트 범위에서 완료, 원문 의미 검증은 부분 완료로 판정했다. 해외 수수료·부가서비스 고지 등은 원문 보존만 됐으며 MVP 전체 구조화는 미완료다. staging AND 재전파 차단과 정정 이력 절차도 아직 미구현이다. Neo4j는 DRAFT 격리 시험 후보이며 실제 적재 및 서비스 사용은 승인되지 않았다.

## 10. A8 Neo4j 개발 시험 적재

사용자 승인으로 Aura `6ac1f0f8`의 레시피 노드 8,154·관계 18,301 및 레시피 전용 제약 5·독립 인덱스 2를 백업 대조 후 삭제했다. 레시피 백업의 실제 복원 시험은 미실시다. ONE PICK STYLE DRAFT를 카드 전용 고유성 제약과 함께 노드 108·관계 168개 적재했고 같은 데이터를 순차 재실행해 중복 없이 동일 건수임을 확인했다. PostgreSQL 스냅샷과 노드·관계의 키·원본 JSON 및 관계 끝점 비교는 불일치 0건이다. 실제 조회 예시와 시험 데이터 한계는 [구조 비교](POSTGRESQL_TO_NEO4J_STRUCTURE_COMPARISON.md) 참조. 사용자용 승인 데이터는 아니며 GraphRAG·벡터 RAG 비교와 팀원 계정 접속은 미검증이다.
