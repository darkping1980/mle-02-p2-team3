# card_benefit

신용카드·체크카드의 혜택·이용 조건을 관리하는 2인 팀 프로젝트입니다.
카드 상품설명서에서 혜택 정보를 AI로 추출·검증하고, 이후 Neo4j GraphRAG와 연동하는 것이 목표입니다.
두 팀원이 같은 원천 문서를 **서로 다른 방식(파일 기반 / PostgreSQL 기반)으로 각자 파싱·추출·검증**한 뒤 결과를 비교합니다.
두 파이프라인은 독립적인 실험·구현이며, 한쪽 결과가 다른 쪽 입력이 되지 않습니다.

## 현재 구현된 기능

- PostgreSQL 카드 상품 등록·목록 조회·단건 조회 CLI (`card_benefit.card_product`)
- DB 연결·SQL 실행은 `src/common` 의 `PostgresDbSession` 을 그대로 사용

PDF 파싱, 정규식·LLM 추출, 정제·검증, Neo4j·GraphRAG는 **아직 구현되지 않았습니다.**

## 디렉터리 요약

```text
card_benefit/                     프로젝트 루트 (실행 위치)
├── payment_card/                 Python 패키지
│   ├── main.py · models.py · repository.py · payment_card.sql   공통 모델·등록·조회·SQL (공동)
│   ├── file_pipeline/            파일 기반 파싱·LLM 추출·검증 (이현근, 미구현)
│   ├── db_pipeline/              PostgreSQL 기반 저장·AI 추출·검증 (김병주, 미구현)
│   └── tests/
├── sql/schema.sql                DDL (수동 실행 전용)
├── data/                         샘플 데이터
└── docs/                         상세 문서
```

## 담당

| 담당자 | 방식 | 영역 |
|---|---|---|
| 이현근 | 파일 기반 | `file_pipeline/` — Python 파싱·전처리, 정규식, Python LLM 호출, Python 검증 → 추출 결과 A |
| 김병주 | PostgreSQL 기반 | `db_pipeline/` — 테이블 설계, 원본 DB 저장, SQL 전처리, DB 데이터 기반 AI 추출(호출 방식 미확정), SQL 검증 → 추출 결과 B |
| 공동 | — | 공통 데이터 계약, 결과 A·B 비교·근거 검증, 통합 테스트, 향후 Neo4j·GraphRAG |

## 준비

저장소 루트 `.env` 에 `DB_URL` 이 있어야 합니다(`common.DatabaseManager` 가 읽음).

```powershell
uv sync --locked
```

`sql/schema.sql` 은 자동 실행되지 않습니다. 대상 DB를 확인한 뒤 직접 적용합니다(psql이 없으면 Supabase SQL Editor 사용).

```powershell
psql "<대상 DB URL>" -f src/card_benefit/sql/schema.sql
```

## 실행

`src/card_benefit` 폴더에서 실행합니다. **`register` 는 `DB_URL` 의 DB에 실제로 행을 추가하므로 대상 DB를 먼저 확인하세요.**

```powershell
cd src/card_benefit
uv run python -m payment_card.main --help
uv run python -m payment_card.main register --issuer 하나카드 --card-name "테스트 신용카드 A" --card-type CREDIT
uv run python -m payment_card.main list
uv run python -m payment_card.main get --card-id 1
```

저장소 루트에서는 `uv --directory src/card_benefit run python -m payment_card.main --help` 로 실행합니다.
종료 코드: 0 성공, 1 입력 오류 또는 대상 없음, 2 인자 오류, 3 DB 오류.

## 테스트

```powershell
cd src/card_benefit
uv run python -m unittest discover -s payment_card/tests -v
```

단위 테스트는 DB에 접속하지 않습니다. 실DB 통합 테스트는 `PAYMENT_CARD_TEST_DB_URL` 에 `schema.sql` 을 적용한
**테스트 전용 DB**를 지정했을 때만 실행되며, 등록·조회 후 rollback합니다(IDENTITY 번호는 소비됨).

## 향후 개발 예정

원천 문서 → (A) 파일 기반 추출·검증 / (B) PostgreSQL 기반 추출·검증 → 공통 형식 비교·근거 검증 → 최종 데이터 확정 → Neo4j / GraphRAG.
설계 방향이며 확정되지 않았습니다. 두 결과를 비교하려면 공통 데이터 계약(문서 ID, 공통 JSON, 판정 기준)이 먼저 정해져야 합니다.

## 문서

- [docs/architecture.md](docs/architecture.md) — 현재 호출 흐름, 병렬 추출·비교 구조, 기술 검토 사항, 세 가지 검증의 차이
- [docs/directory_structure.md](docs/directory_structure.md) — 폴더·파일 역할, common/recipe와의 관계, 배치 원칙, 폴더 이름 변경 이력
- [docs/development_roles.md](docs/development_roles.md) — 담당자별 방식·범위, 공통 데이터 계약, 소유·변경 규칙, 미확정 사항
