# 카드 GraphRAG 소스 분석 위키

> 프로젝트 실행 흐름을 실제 Python, SQL Mapper, Cypher 및 저장소 DDL에 따라 정리한 탐색 문서다. 상위 항목은 `<details>`로 접혀 있다.

## 문서 목차

<details><summary>▼ 등록 및 데이터 준비</summary>

1. [PDF 원문 등록](01_PDF_REGISTRATION.md)
2. [AI 추출](02_AI_EXTRACTION.md)
3. [혜택 등록 및 카드 적용](03_BENEFIT_REGISTRATION.md)
4. [근거 검증과 검토 보류](04_EVIDENCE_VALIDATION.md)
5. [검색 텍스트와 임베딩](05_EMBEDDING.md)
</details>

<details><summary>▼ DB·검색·답변</summary>

6. [PostgreSQL 스키마](06_POSTGRESQL_SCHEMA.md)
7. [Neo4j 동기화](07_NEO4J_SYNC.md)
8. [GraphRAG 조회](08_GRAPHRAG_QUERY.md)
9. [답변 검증](09_ANSWER_VALIDATION.md)
10. [실행·파일·SQL 참조](10_EXECUTION_REFERENCE.md)
</details>

## 분석 기준

기준 커밋: [`7b37de03b17a9671d703f183ec83b386c78d98f7`](https://github.com/darkping1980/mle-02-p2-team3/commit/7b37de03b17a9671d703f183ec83b386c78d98f7) (문서 생성 시점의 `HEAD`). GitHub 줄 번호는 이 커밋의 파일 내용에 대응하며, 후속 변경으로 이동할 수 있다. 각 문서에는 로컬 상대 파일 링크와 GitHub 줄 링크를 함께 둔다.

저장소 코드·DDL·마이그레이션을 정적으로 읽었다. 운영 PostgreSQL/Neo4j 접속, 데이터 적재, LLM 호출은 하지 않았다. 따라서 실제 운영 반영 상태는 **운영 DB 적용 여부 미확인**이다. 샘플 덤프, DDL 초안, 마이그레이션 파일은 각각 증거의 성격이 다르므로 실제 운영 스키마와 동일시하지 않는다.

각 세부 항목은 소스에 적힌 동작만 기술한다. Service→Repository→`PostgresDbSession`/`Neo4jDbSession`→Mapper→SQL/Cypher 경로는 [실행 참조](10_EXECUTION_REFERENCE.md)에 모았다.

## 정적 점검 결과

- 생성 문서: 본 README와 주제 문서 10개. README 목차에서 주제 문서 10개로 모두 이동 가능.
- Python 파일: 문서에서 직접 연결한 소스 21개(등록·추출·혜택·임베딩·Neo4j 적재·조회/UI 및 공통 세션).
- 클래스·메서드/함수 줄 링크: GitHub 줄 링크 19개. 현재 checkout에서 대상 선언 줄을 대조했다. URL은 기준 커밋 SHA를 고정한다.
- SQL/Cypher Mapper: PostgreSQL mapper 4개(`document_repository.sql`, `extraction_repository.sql`, `common_benefit_repository.sql`, `embedding_repository.sql`)와 Neo4j Cypher mapper 1개(`graph_questions.cypher`), 총 5개 연결.
- DB 테이블: 스키마 문서에 핵심 16개 테이블을 연결. 이는 저장소 DDL/SQL에서 확인한 참조 대상 수이며 운영 DB 카탈로그 조회 수가 아니다.
- 링크 검사: 모든 Markdown 상대 링크 대상 파일 존재 검사 통과(0 실패). GitHub 줄 링크 19개 확인.
- 비교 중 확인한 소스/가이드 차이: 현재 embedding mapper는 상품별 혜택을 `card_bnft` 독립 테이블이 아니라 `card_product_item`에서 `item_type_cd='BENEFIT'`로 조회한다. 과거/일반 명칭인 `card_bnft`와 현재 물리 저장 경로를 혼용하지 않도록 5·6·8장에 구분해 기록했다. 단계도 별도 CLI로 실행되는 점을 1·2·3장에 명시.
- 운영 확인: PostgreSQL/Neo4j 접속 및 DDL 적용 여부 검증은 하지 않음. **운영 DB 적용 여부 미확인**.
- 프로그램/기존 문서/DB 변경: 없음. 기존 변경사항 보존. 새 `source_wiki` Markdown만 생성.

## 빠른 이동

[처음으로](README.md) · [스키마](06_POSTGRESQL_SCHEMA.md) · [조회](08_GRAPHRAG_QUERY.md) · [실행 참조](10_EXECUTION_REFERENCE.md)

