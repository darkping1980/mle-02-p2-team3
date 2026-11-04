# 2. AI 추출

[목차](README.md) · [PDF 등록](01_PDF_REGISTRATION.md)

<details><summary>2.1 실행 경계 — 별도 추출 CLI</summary>

진입점 [`terra_main.py`](../../payment_card/db_pipeline/terra_main.py)의 `main()`이 `ExtractionService.run()`을 호출한다. PDF 등록 CLI가 추출을 자동 실행하지 않는다. `--preflight`는 연결/대상 사전 점검, `--execute`는 LLM 포함 실행 경로다. 실행 인자와 반환 코드는 [실행 참조](10_EXECUTION_REFERENCE.md)를 확인한다.

<details><summary>2.1.1 ExtractionService.run()</summary>

소스: [`ExtractionService.run()` 로컬 (L850)](../../payment_card/db_pipeline/extraction_service.py#L850) · [GitHub 기준 커밋](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/extraction_service.py#L850). 입력은 카드/문서 식별자, AI 설정과 선택 페이지 집합이며 세부 인자는 CLI에서 구성한다.

- 사전 조건을 확인하고 `ExtractionRepository`로 문서·대상 청크·차단 페이지·재사용 가능한 이전 성공 실행을 조회한다.
- 추출 대상 페이지별로 AI 입력(페이지 텍스트/이미지와 프롬프트)을 준비하고 LLM을 호출한다. AI 응답은 스키마/Pydantic 검증 후 페이지 번호와 원문 위치를 점검한다.
- 실패 페이지는 호출/파싱 실패 상태와 원인을 기록하고 가능한 다음 페이지로 진행한다. 모든 페이지가 성공하지 않으면 문서 전체 merge로 진행하지 않는다.
- 전체 성공 후 페이지 후보를 합치고 중복/충돌 상태를 정리한 뒤 `card_extr_stg` 및 `card_source_evidence`에 저장한다. run 최종 상태는 성공 페이지/전체 실패 결과를 기준으로 `SUCCEEDED`, `PARTIAL`, `FAILED`가 된다.
- 정확한 SQL은 [`extraction_repository.sql`](../../payment_card/db_pipeline/extraction_repository.sql)의 `insert_run`, `insert_call!`, `insert_stg`, `insert_evidence!`, `update_stg_merge!`, `finish_run!`이다. Repository 래퍼는 [`extraction_repository.py`](../../payment_card/db_pipeline/extraction_repository.py).
- 추출, 호출 이력, staging/evidence 쓰기의 세부 트랜잭션 경계는 SQL 세션 transaction 컨텍스트와 메서드 내부의 `transaction()` 위치를 기준으로 한다. 각 페이지 실패가 다른 페이지와 같은 transaction인지 임의로 확대 해석하지 않는다.
</details>
</details>

<details><summary>2.2 입력·응답 구조와 값 검증</summary>

응답 스키마 정의는 [`extraction_schema.py`](../../payment_card/db_pipeline/extraction_schema.py). 추출 결과는 raw staging JSON과 정규화된 필드, 근거를 포함한다. 검사 코드는 [`extraction_service.py`](../../payment_card/db_pipeline/extraction_service.py)의 `check_values()`, `link_check()` 및 merge 관련 메서드에 있다.

- 값 검증은 인용문과 추출된 값의 일치 여부를 다룬다. 코드에 정의된 진단은 `NO_EVIDENCE`, `QUOTE_NOT_FOUND`, `VALUE_NOT_IN_QUOTE`, `VALUE_PARSE_DIFF` 등이다.
- 연결 검증은 문서·페이지에서 찾은 근거가 후보 혜택/규칙에 충분히 연결되는지 판별한다. 단순 근거 문장 유사성만으로 승인 상태를 만들지 않는다.
- 페이지 파싱 오류나 잘못된 JSON은 실패 기록 경로로 간다. 자동화 판정이 불충분하면 검토 대상으로 남는다.
- 프롬프트와 실제 AI adapter는 소스의 입력 구성 함수와 client 생성부를 따라 확인해야 하며, 이 정적 분석에서는 API를 호출하지 않았다.
</details>

<details><summary>2.3 후보 → 근거 → 검토 큐</summary>

`card_extr_stg`는 검토 가능한 추출 후보를 보관하고, `card_source_evidence`는 페이지/청크와 연결된 원문 인용 증거를 보관한다. merge 후보는 중복 또는 충돌을 `MERGED_DUP`, `MERGE_CONFLICT` 등으로 표현한다. SQL 저장·조회 경로는 [10장](10_EXECUTION_REFERENCE.md), 실제 컬럼 정의는 [6장](06_POSTGRESQL_SCHEMA.md).

추출 성공은 카드에 혜택을 등록했다는 뜻이 아니다. 이후 검토 및 [혜택 등록 단계](03_BENEFIT_REGISTRATION.md)가 별도다. 기존 가이드와의 차이: 현재 소스에서 PDF 등록·AI 추출·혜택 반영은 각각 독립 CLI/단계이며, 통합 자동 처리라고 설명하지 않는다.
</details>

[근거 검증 →](04_EVIDENCE_VALIDATION.md) · [실행 참조](10_EXECUTION_REFERENCE.md)

