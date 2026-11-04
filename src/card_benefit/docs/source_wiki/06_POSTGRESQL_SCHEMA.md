# 6. PostgreSQL 스키마와 제약

[목차](README.md) · [임베딩](05_EMBEDDING.md)

> 범위 주의: 아래는 저장소의 DDL/Mapper가 사용한다고 명시한 구조다. **운영 DB 적용 여부 미확인**. DB에 접속하거나 스키마를 변경하지 않았다.

<details><summary>6.1 증거의 종류와 버전</summary>

1. 기준 DDL 초안: [`db_pipeline_schemaV7_draft.sql`](../../sql/db_pipeline_schemaV7_draft.sql). 프로젝트가 기대하는 스키마의 설계 자료다.
2. 변경 절차: [`sql/` 마이그레이션 파일 목록](../../sql/) 중 `db_pipeline_migration_V6_to_V7.sql`, V7 embedding/text/rule-pool 마이그레이션 및 rollback/precheck/postcheck 파일. 절차와 guard를 설명하지만 운영에서 실제 실행됐음을 단독 증명하지 않는다.
3. 샘플 덤프: [`sample_dump-postgres-202610292124.sql`](../../sql/sample_dump-postgres-202610292124.sql)은 이름 그대로 특정 시점 샘플이며 현재 운영 스키마로 단정할 수 없다.
4. 실제 운영 catalog 확인: 이번 작업은 하지 않음.

V7 초안과 후속 migration이 다루는 구조를 한 상태로 합쳐 단정하지 말고 각 파일을 대조해야 한다. 주요 변경 파일은 [프로젝트 SQL 디렉터리](../../sql/)와 [V7 변경 보고서](../../sql/db_pipeline_V7_change_report.md).
</details>

<details><summary>6.2 Service → Session → Mapper 경로</summary>

PostgreSQL 세션은 공통 [`PostgresDbSession`](../../../common/postgres_db_session.py) 기반으로 만들어진다(프로젝트 경로/사용처 기준). 각 Repository는 Mapper 이름을 `select_one`, `select_list`, `execute`로 전달한다. `!`가 붙은 statement는 RETURNING 결과를 사용하는 쓰기 query 이름 관례다.

대표 흐름:

- 등록: `RegisterService` → `DocRepository` → `PostgresDbSession` → `document_repository.sql` → `card_doc`, `card_doc_page`, `card_doc_chunk`.
- 추출: `ExtractionService` → `ExtractionRepository` → `extraction_repository.sql` → `card_ai_run`, `card_ai_call`, `card_extr_stg`, `card_source_evidence`.
- 혜택: Product/Common service → repository → `common_benefit_repository.sql` → `card_product_item`, `card_common_bnft`, 연결/근거 테이블.
- 검색: `BenefitSearchService` → `EmbeddingRepository`/SQL session → `embedding_repository.sql` → 혜택 텍스트·벡터·카탈로그.

호출 statement별 자세한 맵은 [10장](10_EXECUTION_REFERENCE.md).
</details>

<details><summary>6.3 핵심 테이블과 키 흐름</summary>

| 그룹 | 테이블 | 용도 및 핵심 컬럼 예 | 키/관계 설명 |
|---|---|---|---|
| 원문 | `card_doc` | 문서 ID/code/type, 파일명·크기·SHA-256, 제목/출처 | 문서 루트 |
| 원문 | `card_doc_page` | 문서 ID, 페이지 번호, 페이지 텍스트/해시/품질 | 문서 ID를 상위 키로 사용 |
| 원문 | `card_doc_chunk` | 문서 ID, chunk ID, 페이지 범위·텍스트 | 페이지/문서 원문 단위 |
| 추출 | `card_ai_run`, `card_ai_call` | run 상태·stage·model·호출/응답 정보 | AI 실행 및 호출 이력 |
| 추출 | `card_extr_stg` | 후보 종류, raw JSON, 검증/merge 상태 | run/문서에 연결된 staging |
| 근거 | `card_source_evidence` | evidence ID, quote, page/chunk/staging 참조, approval 상태 | PK 상속 변경 SQL은 별도 migration 확인 필요 |
| 상품 | `card_product`, `card_product_doc` | 카드와 상품설명서 연결, 적용 근거/승인 상태 | 카드 상품은 별도 존재해야 연결 가능 |
| 혜택 | `card_product_item` | 상품 항목 ID/type/name, rule/condition/search text/vector | 혜택은 type BENEFIT로 저장되는 현행 경로 |
| 공통 | `card_common`, `card_common_doc` | 브랜드 서비스 및 문서 연결 | 공통 서비스 master |
| 공통 | `card_common_bnft`, `card_common_bnft_apply` | 공통 혜택과 카드 적용 | 카드별 apply relation |
| 근거 연결 | `card_evidence_link` | 혜택/규칙과 evidence 연결 | 세부 복합키는 버전 DDL/migration 기준 |
| 코드 | `common_cd` | 그룹별 공통 코드/명칭 | code group + code lookup |

정확한 데이터 타입, PK/UNIQUE/CHECK/FK 선언은 [V7 DDL 초안](../../sql/db_pipeline_schemaV7_draft.sql)과 각 전환 migration에서 확인한다. 이 문서는 일부 PK/FK 컬럼 구성을 요약하며, mapper에서 조인한다는 사실만으로 DB FK 제약이 존재한다고 보지 않는다. 반드시 DDL에 `FOREIGN KEY`가 선언된 경우에만 실제 선언으로 기록해야 한다.
</details>

<details><summary>6.4 DDL 제약과 업무 gate 구분</summary>

DB의 PK/UNIQUE/CHECK는 물리 제약이며 Python 서비스의 허용 상태, evidence sufficiency, 적용 자격은 업무 검증이다. SQL `ON CONFLICT DO NOTHING`은 해당 statement가 충돌을 무시하는 동작이지, 서비스 승인을 뜻하지 않는다. 테이블별 DDL 정의와 서비스 검증을 대조할 때는 컬럼 이름/제약을 원문에서 확인한다. 운영 DB 확인 전에는 실제 적용 제약으로 기술하지 않는다.
</details>

<details><summary>6.5 사용 SQL 종류</summary>

등록은 SELECT와 INSERT 및 검증 SELECT, 추출은 INSERT/UPDATE와 조회, 혜택 반영은 INSERT/UPDATE 및 lock/integrity SELECT, 임베딩은 검색 텍스트/벡터 UPDATE와 SELECT를 쓴다. 각 Mapper의 `-- name:` 항목 및 호출 서비스는 [10장](10_EXECUTION_REFERENCE.md)에 연결한다. 소스에 선언되지 않은 DELETE를 운영 경로로 추정하지 않는다.
</details>

[Neo4j 동기화 →](07_NEO4J_SYNC.md) · [실행 참조 →](10_EXECUTION_REFERENCE.md)

