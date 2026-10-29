# card_benefit 디렉터리 구조와 파일 역할

현재 로컬 소스(2026-10-29 기준)를 그대로 옮긴 문서입니다. 표기: ✅ 구현됨 · ⏳ 개발 예정(폴더만 있음) · ❓ 미확정.
담당자별 범위는 [development_roles.md](development_roles.md), 실행 흐름은 [architecture.md](architecture.md)에 있습니다.

## 1. 전체 트리

```text
src/card_benefit/                     프로젝트 루트 = 실행 위치, import 기준 폴더
├── README.md                         실행 가이드
├── docs/
│   ├── architecture.md               현재 흐름 + 향후 파이프라인 방향
│   ├── directory_structure.md        이 문서
│   └── development_roles.md          담당자·협업 기준
├── sql/
│   └── schema.sql                    ✅ PostgreSQL DDL (수동 실행 전용)
├── data/
│   └── README.md                     ⏳ 샘플 데이터 위치 (데이터 파일 없음)
└── payment_card/                     Python 패키지
    ├── __init__.py                   ✅ 패키지 설명 docstring만 있음
    ├── main.py                       ✅ 공통: 현재 실행 진입점 (CLI)
    ├── models.py                     ✅ 공통: 카드 데이터 모델·입력 검증 (추출 결과 계약은 ⏳ 예정)
    ├── repository.py                 ✅ 공통: 카드 등록·조회 (CardRepository)
    ├── payment_card.sql              ✅ 공통: Named SQL Mapper
    ├── file_pipeline/
    │   └── README.md                 ⏳ 이현근: 파일 기반 파싱·LLM 추출·검증 (Python 파일 없음, __init__.py 없음)
    ├── db_pipeline/
    │   └── README.md                 ⏳ 김병주: PostgreSQL 기반 저장·AI 추출·검증 (Python 파일 없음, __init__.py 없음)
    └── tests/
        └── test_payment_card.py      ✅ 단위 테스트 + 조건부 통합 테스트
```

## 2. 폴더별 목적

| 폴더 | 목적 | 현재 상태 |
|---|---|---|
| `card_benefit/` | 프로젝트 루트. CLI·테스트를 이 폴더에서 실행해 `payment_card` 를 import한다 | ✅ |
| `payment_card/` | Python 업무 소스. 최상위 파일은 두 방식이 함께 쓰는 공통 영역(모델·계약·등록·조회·SQL·진입점, 공동 관리) | ✅ |
| `payment_card/file_pipeline/` | **이현근 방식**: 문서 파일을 Python으로 읽어 전처리·정규식·LLM 추출·Python 검증까지 수행 | ⏳ README만 |
| `payment_card/db_pipeline/` | **김병주 방식**: 원본을 PostgreSQL에 저장하고 SQL 전처리·DB 데이터 기반 AI 추출·SQL 검증까지 수행 | ⏳ README만 |
| `payment_card/tests/` | 단위 테스트 (`unittest`) | ✅ |
| `sql/` | 테이블 생성·변경 DDL. 애플리케이션이 자동 실행하지 않음 | ✅ |
| `data/` | 샘플 PDF·입력 데이터 | ⏳ README만 |
| `docs/` | 프로젝트 문서 | ✅ |

## 3. Python 파일의 실제 기능

### `payment_card/models.py`

| 이름 | 종류 | 실제 동작 |
|---|---|---|
| `CARD_TYPES` | 상수 | `("CREDIT", "DEBIT")`. `NewCard` 검증과 CLI `--card-type` 선택지에서 사용 |
| `NewCard` | dataclass | 등록 입력(`issuer`, `card_name`, `card_type`). `__post_init__` 이 빈 값·`None` 을 `ValueError` 로 거부하고 앞뒤 공백을 제거하며, `card_type` 이 `CARD_TYPES` 밖이면 거부한다(대소문자 구분) |
| `Card` | dataclass | 조회 결과 한 행(`card_id`, `issuer`, `card_name`, `card_type`, `created_at`). 검증 없음 |

### `payment_card/repository.py`

| 이름 | 실제 동작 |
|---|---|
| `MAPPER_ROOT` | `payment_card/` 폴더 경로. `PostgresDbSession(mapper_root=...)` 에 전달 |
| `CardRepository(sql_session)` | 주입받은 세션으로 SQL만 실행한다. 연결·트랜잭션·종료는 세션 책임 |
| `.insert_card(NewCard) -> Card` | `sql_session.execute("payment_card.insert_card", asdict(card))` → 결과 첫 행으로 `Card` 생성 |
| `.list_cards() -> list[Card]` | `sql_session.select_list("payment_card.list_cards")` |
| `.find_card(card_id) -> Card \| None` | `sql_session.select_one("payment_card.find_card", {"card_id": ...})` |

### `payment_card/main.py`

| 이름 | 실제 동작 |
|---|---|
| `parse_args(argv)` | 하위 명령 `register`(`--issuer`, `--card-name`, `--card-type`) / `list` / `get`(`--card-id`) |
| `format_card(card)` | `card_id`, `card_type`, `issuer`, `card_name`, `created_at` 을 탭으로 이은 한 줄 |
| `main(argv) -> int` | `register` 면 `NewCard` 검증 → `PostgresDbSession(mapper_root=MAPPER_ROOT, camel_case_keys=False, sql_log_mode="none")` 생성 → `CardRepository` 호출 → `finally` 에서 `database_manager.close()`. 종료 코드 0 성공 / 1 입력 오류·대상 없음 / 2 인자 오류 / 3 `psycopg.Error` |

### `payment_card/tests/test_payment_card.py`

| 테스트 클래스 | 확인 내용 | DB 접속 |
|---|---|---|
| `NewCardValidationTests` | CREDIT/DEBIT 허용, 잘못된 유형·필수값 누락 거부 | 없음 |
| `MapperCompatibilityTests` | 실제 `PostgresDbSession` 이 `payment_card` namespace만 등록, pool 미생성, 바인딩 파라미터 변환 | 없음 |
| `CardRepositoryTests` | statement ID·파라미터 전달, 결과 → `Card` 변환 | 없음 (가짜 세션) |
| `CliTests` | 도움말, 등록 출력, 입력 오류 시 세션 미생성, 대상 없음, pool 종료 | 없음 (가짜 세션) |
| `TestDatabaseIntegrationTests` | 등록→단건→목록 후 rollback | `PAYMENT_CARD_TEST_DB_URL` 이 있을 때만 |

## 4. SQL Mapper — `payment_card/payment_card.sql`

- 위치: `repository.py` 와 같은 폴더. 파일명 stem `payment_card` 가 namespace 다.
- statement: `insert_card`(INSERT … RETURNING, 접미사 없음), `list_cards`, `find_card`. 모두 `card_benefit.card_product` 대상.
- `PostgresDbSession` 은 `MAPPER_ROOT`(= `payment_card/`) **하위 폴더까지** `-- name:` 이 있는 `*.sql` 을 모두 등록한다.
  따라서 파이프라인 폴더에 `.sql` 을 두면 별도 설정 없이 자동 등록되며, 파일명이 다른 `.sql` 과 같으면 중복 오류가 난다.
- 이 파일은 두 방식이 공통으로 쓰는 카드 등록·조회 SQL이다. 한 방식에서만 쓰는 SQL은 그 파이프라인 폴더에 둔다.
  예: DB 방식 전용 SQL → `payment_card/db_pipeline/db_pipeline.sql` (namespace `db_pipeline`). 별도 `mappers/` 폴더는 만들지 않는다.
- 전용 SQL 파일을 추가하는 시점에 파일명(namespace)과 statement 이름이 기존 것과 겹치지 않는지 확인한다(아직 추가된 전용 SQL 없음).

## 5. PostgreSQL DDL — `sql/schema.sql`

- `CREATE SCHEMA IF NOT EXISTS card_benefit` + `CREATE TABLE IF NOT EXISTS card_benefit.card_product`. 하나카드 수집·정제·검증 테이블(`hana_card_schema_draft.sql`)도 같은 `card_benefit` 스키마를 쓴다.
- 컬럼: `card_id`(BIGINT IDENTITY PK), `issuer`, `card_name`, `card_type`(CHECK CREDIT/DEBIT), `created_at`(TIMESTAMPTZ 기본 `now()`).
- 애플리케이션·테스트가 자동 실행하지 않는다. `-- name:` 이 없고 `MAPPER_ROOT` 밖에 있어 mapper로 등록되지도 않는다.

## 6. `src/common` 과의 연결 지점

card_benefit이 직접 사용하는 것은 아래 두 가지뿐이다. 공통 모듈 자체 설명은 `src/common` 소스와 `docs/TEAM_START_HERE.md` 를 본다.

| 연결 지점 | 사용 위치 |
|---|---|
| `common.postgres_db_session.PostgresDbSession` | `main.py`(생성·종료), `repository.py`(타입·호출), 테스트 |
| `PostgresDbSession.database_manager` (`common.DatabaseManager`) | `main.py` 의 `finally` 에서 `close()` |

- `DB_URL` 은 `DatabaseManager` 가 저장소 루트 `.env` 에서 읽는다. card_benefit에는 환경변수 로딩 코드가 없다.
- `common` 은 저장소 editable 설치(`uv sync`)로 import된다. `payment_card` 는 설치 대상이 아니므로 `src/card_benefit` 에서 실행해야 import된다.

## 7. `src/recipe` 와 다른 부분과 이유

| 항목 | recipe | card_benefit | 이유 |
|---|---|---|---|
| 세션 생성 | `database.py` 의 `create_recipe_sql_session()` | `main.py` 에서 `PostgresDbSession` 직접 생성 | 스키마 전환·로그 설정 같은 프로젝트 고유 처리가 아직 없어 별도 모듈이 필요 없음 |
| 경로·환경 설정 | `config.py`(`sys.path`, `.env`, 쿼리 로그) | 없음 | 실행 위치 규칙 + `DatabaseManager` 의 `.env` 로딩으로 충분 |
| DDL 위치 | 패키지 안 `recipe_recommender/sql/` | 프로젝트 루트 `sql/` | 업무 소스와 DB 스크립트를 분리하기로 함 |
| 문서 위치 | `src/recipe/docs/` | `src/card_benefit/docs/` | 같음 (프로젝트 루트 아래 docs) |
| Mapper 위치 | 패키지 폴더의 `recipe.sql` | 패키지 폴더의 `payment_card.sql` | 같음 |
| 영역 구분 | `setup/`(적재), `tools/`(점검) | `file_pipeline/`, `db_pipeline/` | 같은 원천 문서를 서로 다른 방식으로 처리하는 담당자별 독립 영역 |
| 저장소 테스트 실행기 | `run_offline_tests.py` 에 포함 | 포함되지 않음 | 루트 스크립트를 변경하지 않음. 별도 명령으로 실행 |
| Neo4j·Streamlit | 있음 | 없음 | 아직 범위 밖 |

## 8. 기능 확장 시 소스 배치 원칙

1. 파일 기반 방식(이현근)의 전용 처리 로직은 `file_pipeline/`, PostgreSQL 기반 방식(김병주)의 전용 처리 로직·SQL은 `db_pipeline/` 에 둔다.
   두 폴더는 서로 import하지 않는다.
2. 두 방식이 함께 쓰는 모델·추출 결과 계약·등록·조회·SQL은 `payment_card/` 최상위에 두고, 각 파이프라인에 복사하지 않는다.
   추출 결과 계약은 `models.py` 에 추가할 예정이다(⏳, 4절 합의 후). 결과 A·B 비교 코드의 위치는 미정이다 ❓.
3. `file_pipeline/` 또는 `db_pipeline/` 에 첫 Python 모듈을 추가할 때 그 폴더의 `__init__.py` 도 함께 만든다.
4. Named SQL은 `payment_card/` 아래 `.sql` 로 두고, 파일명(namespace)이 겹치지 않게 한다. DDL은 `sql/` 에 둔다.
5. 테스트는 `payment_card/tests/test_*.py` 에 둔다. 현재 실행 명령(`discover -s payment_card/tests`)은 이 폴더만 찾는다.
6. 샘플 데이터는 `data/`, 문서는 `docs/` 에 둔다. 저작권·개인정보가 있는 원본은 커밋하지 않는다.
7. 미구현 기능을 위한 빈 Python 파일은 만들지 않는다.

## 9. 폴더 이름 변경 이력

- 2026-10-29: `extraction/` → `file_pipeline/`, `ingestion/` → `db_pipeline/`.
- 이유: 두 사람의 차이는 작업 단계(추출 → 적재)가 아니라 **구현 방식(파일 기반 / PostgreSQL 기반)** 이다.
  `ingestion`(적재)은 AI 추출·검증까지 하는 역할보다 좁고, `extraction` 은 두 방식 모두에 해당해 구분이 되지 않았다.
- 변경 당시 두 폴더에는 README만 있어 Python import 변경은 없었다.
