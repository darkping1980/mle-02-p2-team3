# 1. PDF 원문 등록

[목차](README.md)

<details><summary>1.1 프로세스 개요 — CLI → 파일 검사 → 중복 판정 → 등록/검증 → 선택 연결</summary>

진입점은 [`main.py`](../../payment_card/db_pipeline/main.py)의 `main()`이다. 이 단계는 LLM을 호출하지 않는다. 신규 문서 apply 경로는 `card_doc` → 페이지 → 청크를 한 트랜잭션에 넣고 검증한 뒤 선택적으로 상품/공통서비스에 연결한다. 별도 추출 실행은 [2장](02_AI_EXTRACTION.md)이다.

<details><summary>1.1.1 parse_args()와 links()</summary>

- 소스: [parse_args() 로컬 (L50)](../../payment_card/db_pipeline/main.py#L50) · [GitHub](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/main.py#L50), [links() 로컬 (L87)](../../payment_card/db_pipeline/main.py#L87) · [GitHub](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/main.py#L87).
- `--pdf` 필수. `--apply` 없으면 dry-run. `--card-id`에는 `--basis`, `--common-cd`에는 `--common-nm`이 필요하며 둘은 동시 지정할 수 없다.
- 타사 manifest-less PDF는 issuer/document 메타데이터 네 항목을 모두 받아야 한다. 하나라도 불완전하면 argparse 오류로 진입을 막는다.
- `links()`는 상품 링크 또는 공통 문서 링크 객체 하나만 만들어 `RegisterService.register()`로 전달한다.
</details>

<details><summary>1.1.2 main()</summary>

- 호출자: 모듈 실행 (`python -m payment_card.db_pipeline.main`). 입력: argv. 반환/종료: 정상 `0`, 입력/검증 실패 `1`, argparse `2`, psycopg 오류 `3`.
- 실행 순서: 인자 파싱 → `PostgresDbSession(mapper_root=MAPPER_ROOT)` → 필요할 때만 OCR 엔진 생성 → `DocumentService` 구성 → [`RegisterService.register()`](../../payment_card/db_pipeline/register_service.py) 호출 → 결과 출력 → DB manager close.
- 세션 생성 이후 예외는 유형별로 처리한다. DB 오류를 사용자 입력 오류와 구분한다. `finally`에서 연결 자원을 닫는다.
- 소스: [main() 로컬 (L125)](../../payment_card/db_pipeline/main.py#L125) · [GitHub 원본](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/main.py#L125).
</details>
</details>

<details><summary>1.2 RegisterService.register() — 검사와 분기</summary>

소스: [`RegisterService` 로컬 (L76)](../../payment_card/db_pipeline/register_service.py#L76) · [GitHub 기준 커밋 (L76)](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/register_service.py#L76).

<details><summary>1.2.1 호출·입출력·순서</summary>

- 메서드: [RegisterService.register() 로컬 (L88)](../../payment_card/db_pipeline/register_service.py#L88) · [GitHub 기준 커밋 (L88)](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/register_service.py#L88).
- 입력: PDF 경로, `apply`, 선택적인 `ProductDocLink` 또는 `CommonDocLink`. 둘 다 있으면 즉시 `RegisterError`.
- 파일 검사: 실제 `DocumentService`이면 `inspect()`로 우선 메타데이터/해시만 읽는다. 테스트 대체 객체면 `read()`를 호출한다. 연결 종류와 `doc_type_cd` 불일치는 거부한다.
- 중복 조회: [`DocRepository.find_doc()`](../../payment_card/db_pipeline/document_repository.py) → `document_repository.select_doc_by_sha256_or_cd`.
- 같은 SHA-256: 신규 INSERT 없이 저장 상태 검증과 건수 조회. `apply`와 새 연결 요청이 모두 있을 때만 `_link()`를 트랜잭션에서 실행.
- 같은 `doc_cd`만 존재(해시 상이): 충돌로 거부.
- 신규 dry-run: 페이지가 없으면 `DocumentService.read()`로 파싱하되 DB 변경은 하지 않는다. `DRY_RUN` 반환.
- 신규 apply: `inspect()`와 `read()` 사이 해시가 바뀌면 중단. 이후 `_insert()`에서 등록 및 검증.
- 반환 상태: `DRY_RUN`, `REGISTERED`, `ALREADY_REGISTERED`. 기존 저장 검증에서 ERROR면 예외로 반환하지 않는다.
</details>

<details><summary>1.2.2 _insert() 트랜잭션과 순서</summary>

- 호출자: `register()`의 신규 apply 분기. 입력은 파싱된 문서와 선택 링크.
- `with sql_session.transaction()` 안에서 문서 INSERT, 각 페이지 INSERT, 각 청크 INSERT, 저장 후 `verify_doc()` 실행, DB 페이지 해시와 로컬 PDF 페이지 해시 대조, 선택 연결을 차례로 처리한다.
- SQL 검사 결과 `ERROR`가 하나라도 있거나 해시/구조 검증에서 실패하면 예외가 발생하여 컨텍스트 매니저가 rollback한다. 정상 종료하면 컨텍스트 매니저가 commit한다.
- 상품 링크는 기존 `card_product` 존재 확인 후 `card_product_doc`에 대기 상태 연결. 이 경로에서 카드 상품 자체를 만들지 않는다.
- 공통 링크는 `CommonBenefitService.ensure_common()`으로 공통 엔티티를 확인/생성하고, 문서 종류가 `BRAND_SERVICE`인 경우 `link_doc()`로 연결한다.
- 소스: [`_insert()` 로컬 (L187)](../../payment_card/db_pipeline/register_service.py#L187) · [GitHub 기준 커밋](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/register_service.py#L187), [`_link()` 로컬 (L157)](../../payment_card/db_pipeline/register_service.py#L157) · [GitHub 기준 커밋](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/register_service.py#L157).
</details>
</details>

<details><summary>1.3 PDF 파싱·품질 검증</summary>

[`DocumentService`](../../payment_card/db_pipeline/document_service.py)는 DB에 접근하지 않고 경로/manifest, PDF 형식과 해시, 페이지 텍스트·OCR·청크를 처리한다. `inspect()`는 중복 판정용 얕은 검사, `read()`는 페이지 데이터까지 만든다. 빈 텍스트·차단된 페이지·manifest 페이지 수 불일치 등은 읽기 결과의 품질 항목으로 나타나며, OCR을 지정하지 않은 문제 페이지는 등록을 거부할 수 있다. 세부 PDF 품질 규칙은 [기존 등록 검증 가이드](../guide/CARD_DATA_REGISTRATION_VALIDATION_DETAIL.md)와 소스 [`document_service.py`](../../payment_card/db_pipeline/document_service.py)를 함께 참조한다.

관련 mapper: [`document_repository.sql`](../../payment_card/db_pipeline/document_repository.sql)의 `insert_doc`, `insert_doc_page!`, `insert_doc_chunk!`, `verify_doc`, `select_table_counts`. 조회/INSERT는 [`DocRepository`](../../payment_card/db_pipeline/document_repository.py)가 `PostgresDbSession.select_*`/`execute`로 전달한다. 실제 statement 연결 표는 [10장](10_EXECUTION_REFERENCE.md).
</details>

<details><summary>1.4 스키마 및 검토 경계</summary>

주요 테이블: `db_pipeline.card_doc`, `card_doc_page`, `card_doc_chunk`; 선택적으로 `card_product_doc`, `card_common`, `card_common_doc`. 컬럼과 DDL 출처는 [6장](06_POSTGRESQL_SCHEMA.md). 저장소 DDL과 migration은 운영 DB 적용 증거가 아니므로 운영 스키마는 **운영 DB 적용 여부 미확인**이다.
</details>

[목차](README.md) · [AI 추출 →](02_AI_EXTRACTION.md)

