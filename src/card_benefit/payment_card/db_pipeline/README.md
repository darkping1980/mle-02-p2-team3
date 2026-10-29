# db_pipeline — PostgreSQL 중심 처리 방식 (담당: 김병주, 미구현)

원천 문서의 텍스트·메타데이터를 PostgreSQL에 저장하고, DB 데이터를 대상으로 전처리·AI 추출·검증까지 수행하는 방식입니다.
`file_pipeline/`(이현근)과 **같은 원천 문서를 다른 방식으로 처리하는 독립 구현**이며, 서로의 결과를 입력으로 쓰지 않습니다.

개발 예정:
- 문서 원본 텍스트·메타데이터 DB 등록, SQL 기반 전처리
- PostgreSQL 데이터 기반 AI 호출·추출 → 추출 데이터 저장
- SQL 기반 정제·검증 (중복·무결성·정합성)
- 추출 결과와 원문 근거 관리 → 공통 형식으로 내보낸 결과(**결과 B**)

미확정:
- PostgreSQL은 PDF를 직접 파싱하지 않습니다. DB에 넣을 텍스트를 확보하는 방법은 정해야 합니다.
- DB에서 AI를 호출하는 방식(DB 함수, `pgai`, 외부 LLM 연동 등)은 사용 중인 Supabase/PostgreSQL에서 기술 검증 후 확정합니다.

규칙:
- `file_pipeline/` 을 import하지 않습니다. DB 연결·트랜잭션은 `src/common` 의 `PostgresDbSession` 을 사용합니다.
- 공통 등록·조회 SQL은 `../payment_card.sql`, 이 방식 전용 SQL은 이 폴더의 `db_pipeline.sql` 에 둡니다(`mappers/` 폴더 없음).
  파일명이 namespace가 되므로(`db_pipeline.*`) 추가 시 다른 `.sql` 과 이름이 겹치지 않는지 확인합니다.
- 테이블 DDL은 `src/card_benefit/sql/` 에 둡니다. 첫 Python 모듈을 추가할 때 `__init__.py` 도 함께 만듭니다.

상세: `src/card_benefit/docs/development_roles.md`
