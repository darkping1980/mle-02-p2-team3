# ingestion — PostgreSQL 등록·정제·검증 영역 (미구현)

`extraction/`의 추출 결과를 정제·검증해 PostgreSQL에 등록하는 코드를 둡니다.

- SQL 실행은 기존 `CardRepository`(`../repository.py`)와 `../payment_card.sql`을 사용하거나 확장합니다.
  이 영역 전용 SQL이 필요하면 이 폴더에 `-- name:` 형식의 `.sql`을 두면 `PostgresDbSession`이 함께 등록합니다(파일명이 namespace).
- DB 연결·트랜잭션은 `src/common`의 `PostgresDbSession`을 그대로 사용합니다.
- 테이블 변경 DDL은 `src/card_benefit/sql/`에 둡니다.
