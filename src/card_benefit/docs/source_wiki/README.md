# 카드 GraphRAG 소스 분석 위키

> 프로젝트 실행 흐름을 실제 Python, SQL Mapper, Cypher 및 저장소 DDL에 따라 정리한 탐색 문서다. 상위 항목은 `<details>`로 접혀 있다.

## 문서 목차

<details><summary>등록 및 데이터 준비</summary>

1. [PDF 원문 등록](01_PDF_REGISTRATION.md)
2. [AI 추출](02_AI_EXTRACTION.md)
3. [혜택 등록 및 카드 적용](03_BENEFIT_REGISTRATION.md)
4. [근거 검증과 검토 보류](04_EVIDENCE_VALIDATION.md)
5. [검색 텍스트와 임베딩](05_EMBEDDING.md)
</details>

<details><summary>DB·검색·답변</summary>

6. [PostgreSQL 스키마](06_POSTGRESQL_SCHEMA.md)
7. [Neo4j 동기화](07_NEO4J_SYNC.md)
8. [GraphRAG 조회](08_GRAPHRAG_QUERY.md)
9. [답변 검증](09_ANSWER_VALIDATION.md)
10. [실행·파일·SQL 참조](10_EXECUTION_REFERENCE.md)
</details>

## 분석 기준

기준 커밋: [`7b37de03b17a9671d703f183ec83b386c78d98f7`](https://github.com/darkping1980/mle-02-p2-team3/commit/7b37de03b17a9671d703f183ec83b386c78d98f7) (문서 생성 시점의 `HEAD`). GitHub 줄 번호는 이 커밋의 파일 내용에 대응하며, 후속 변경으로 이동할 수 있다. 각 문서에는 로컬 상대 파일 링크와 GitHub 줄 링크를 함께 둔다.

로컬 링크는 현재 checkout 기준 상대 경로와 `#L줄번호`를 쓴다. VS Code 기본 Markdown 링크 처리기는 이런 숫자 fragment를 편집기 선택 범위로 변환한다. 이 checkout의 `HEAD`는 기준 커밋과 다른 `e9dd06ddd131fd2edd677d05d828890f8938dac9`이므로 로컬 줄은 현재 파일, GitHub 줄은 고정 커밋을 기준으로 별도로 점검한다. VS Code 링크 위치는 workspace 설정에서 오른쪽 그룹(`beside`)으로 연다.

저장소 코드·DDL·마이그레이션을 정적으로 읽었다. 운영 PostgreSQL/Neo4j 접속, 데이터 적재, LLM 호출은 하지 않았다. 따라서 실제 운영 반영 상태는 **운영 DB 적용 여부 미확인**이다. 샘플 덤프, DDL 초안, 마이그레이션 파일은 각각 증거의 성격이 다르므로 실제 운영 스키마와 동일시하지 않는다.

각 세부 항목은 소스에 적힌 동작만 기술한다. Service→Repository→`PostgresDbSession`/`Neo4jDbSession`→Mapper→SQL/Cypher 경로는 [실행 참조](10_EXECUTION_REFERENCE.md)에 모았다.

## 정적 점검 결과

- 생성 문서: 본 README와 주제 문서 10개. README 목차에서 주제 문서 10개로 모두 이동 가능.
- Python 파일: 문서에서 직접 연결한 소스 21개(등록·추출·혜택·임베딩·Neo4j 적재·조회/UI 및 공통 세션).
- 클래스·메서드/함수 줄 링크: 현재 소스 정의를 가리키는 로컬 링크 21개와 고정 기준 커밋의 GitHub 링크 21개. 별도 SQL 선언 GitHub 링크 1개.
- SQL/Cypher Mapper: PostgreSQL mapper 4개(`document_repository.sql`, `extraction_repository.sql`, `common_benefit_repository.sql`, `embedding_repository.sql`)와 Neo4j Cypher mapper 1개(`graph_questions.cypher`), 총 5개 연결.
- DB 테이블: 스키마 문서에 핵심 16개 테이블을 연결. 이는 저장소 DDL/SQL에서 확인한 참조 대상 수이며 운영 DB 카탈로그 조회 수가 아니다.
- SQL/Cypher 위치 링크: 고유 PostgreSQL statement 21개(로컬 링크 22개, `insert_doc` 참조 1회 중복), Cypher statement 4개.
- 링크 검사: Markdown 상대 링크 0건 실패. Python·SQL·Cypher 대상 파일과 줄 범위, 우선 검증 대상의 symbol/`-- name:` 선언 위치를 정적 확인.
- VS Code 확장: 설치하지 않음. 기본 Markdown Preview가 `#L숫자` fragment를 로컬 파일 편집기 선택 범위로 해석하므로 Code Reference (InContext)는 필수 아님. Marketplace 설명은 참고만 했으며 호환 확인용 설치는 하지 않음.
- VS Code 배치 설정: `.vscode/settings.json`에 `markdown.links.openLocation: beside` 추가. 현재 `.gitignore`가 `.vscode/` 전체를 무시하므로 로컬 설정이며 Git 변경 목록에는 나타나지 않는다.
- 비교 중 확인한 소스/가이드 차이: 현재 embedding mapper는 상품별 혜택을 `card_bnft` 독립 테이블이 아니라 `card_product_item`에서 `item_type_cd='BENEFIT'`로 조회한다. 과거/일반 명칭인 `card_bnft`와 현재 물리 저장 경로를 혼용하지 않도록 5·6·8장에 구분해 기록했다. 단계도 별도 CLI로 실행되는 점을 1·2·3장에 명시.
- 운영 확인: PostgreSQL/Neo4j 접속 및 DDL 적용 여부 검증은 하지 않음. **운영 DB 적용 여부 미확인**.
- 프로그램/기존 문서/DB 변경: 없음. 기존 변경사항 보존. 새 `source_wiki` Markdown만 생성.

## 빠른 이동

[처음으로](README.md) · [스키마](06_POSTGRESQL_SCHEMA.md) · [조회](08_GRAPHRAG_QUERY.md) · [실행 참조](10_EXECUTION_REFERENCE.md)

