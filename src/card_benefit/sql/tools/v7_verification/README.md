# V7 검증 도구

## 혜택·한도 TEXT 단순화 검증

`card_limit_pool`, `card_bnft_rule_pool` 제거 이관을 메모리 PostgreSQL에서 시험한다. 실제 DB에 쓰지 않는다.

```bash
../../../../../.venv/Scripts/python export_simplify_rows.py   # 읽기 전용. 결과는 Git 제외 폴더 .work/
node verify_bnft_text.mjs real                                # 내려받은 행
node verify_bnft_text.mjs                                     # 합성 행
```

기준 구조는 커밋 `bdb94bc`의 V7이다. 사전 검증, 가드 음성 시험 9종, 새 V7과 카탈로그 비교, 재실행, 복구, 복구 재실행, 재이관을 확인한다. `real`을 **이관 전 DB에서** 내려받아야 한다. 이관 후에는 다시 받을 수 없고 사후 검증 SQL을 쓴다.

`verify_v6_path.mjs`는 V6 → V7 → TEXT 단순화까지 이어서 최종 DDL과 비교하고, `migrate_test.mjs`와 함께 V7 비교 기준을 `bdb94bc`로 고정했다. `verify_rule_pool.mjs`, `live_rollback_dryrun.py`, `neo4j_isolated_test.py`는 단순화 이전 구조용 기록이며 현재 구조에 실행하지 않는다.

## 규칙·한도 연결 테이블 변경 검증 (단순화 이전 기록)

기존 `pool_refs`를 `card_bnft_rule_pool`로 이관하는 변경은 다음 메모리 PostgreSQL 시험으로 확인한다. 실제 DB에 접속하지 않는다. 먼저 이 폴더의 PGlite 의존성을 설치한다.

```bash
node verify_rule_pool.mjs
node verify_v6_path.mjs
node verify_integrity.mjs
```

첫 시험은 Git 커밋 `0b17489`의 이전 V7 DDL을 이용해 이관·고아·중복·V7 복구를 검증한다. 두 번째는 V6 이관·복구·재이관과 새 V7 카탈로그를 비교한다. 세 번째는 최종 V7 SQL 무결성 시험이다. 추출 staging의 임시 `pool_refs`와 최종 테이블은 별도이며, 운영 DB 또는 Neo4j에 쓰지 않는다.

V7 이관, 롤백, 정합성 검증을 다시 실행하기 위한 도구다.

**설계의 기준은 `src/card_benefit/sql/`의 최종 V7 SQL 파일이다.** 이 폴더의 도구는 그 파일을 검증할 뿐 대체하지 않는다. 특히 `reference/gen_v7_reference.py`는 참고용 기록이며, 여기서 나온 결과로 V7 파일을 덮어쓰면 안 된다.

**개발 PostgreSQL은 연결 테이블이 포함된 V7이고 운영 Neo4j는 V6이다.** 아래 V6 데이터 내보내기·이관 절차는 V6 전용 격리 원본에서만 사용한다. 현재 개발 DB에 `export_live_rows.py` 또는 `live_rollback_dryrun.py`를 사용해 V6 시험 입력을 만들지 않는다. 이 폴더에는 운영 적용 도구가 없다.

## 도구와 위험도

| 파일 | 용도 | 접속 대상 | 실제 변경 | 기본 실행 |
|---|---|---|---|---|
| `export_live_rows.py` | V6 원본 행을 `.work/`로 내려받기 | 설정된 DB, 읽기 전용 | 없음 | V6 원본에서만 실행 |
| `catalog_dump.mjs` | SQL 파일로 만든 메모리 DB의 카탈로그 추출 | 없음 | 없음 | 바로 실행 |
| `catalog_diff.py` | 실제 DB와 카탈로그 비교 | 실제 DB, 읽기 전용 | 없음 | 바로 실행 |
| `migrate_test.mjs` | 이관, 롤백, 재이관, 안전장치 시험 | 없음 (메모리 DB) | 없음 | 바로 실행 |
| `live_rollback_dryrun.py` | 실제 DB 트랜잭션에서 이관 후 ROLLBACK | **실제 DB** | 없음. 항상 ROLLBACK, **실행 중 테이블 잠금** | **거부.** `--run-with-rollback` 필요 |
| `neo4j_isolated_test.py` | 격리 네임스페이스 적재·조회·삭제 | **공유 Neo4j** | **`df_v7_test`에 쓰고 지움** | **거부.** `--write-test-namespace` 필요 |
| `reference/gen_v7_reference.py` | V6에서 V7까지의 변경 기록 (**참고용**) | 없음 | `--out` 폴더에만 씀 | **거부.** `--out` 필수 |

## 의존성

- 저장소 루트의 `.venv`와 `.env`. 접속 정보는 `.env`에서만 읽고 출력하지 않는다.
- Node.js. 이 폴더에서 `npm install`을 한 번 실행한다. `@electric-sql/pglite` 0.2.17(PostgreSQL 16.4 메모리 DB), `@dbml/core` 3.9.5를 쓴다.
- `psql`, `pg_dump`는 필요 없다.

`.work/`, `node_modules/`, `package-lock.json`은 Git에서 제외된다. `.work/`에는 내려받은 실제 행과 시험 결과가 저장되므로 복사하거나 공유하지 않는다.

## 격리 검증 (기본 절차)

아래 명령은 이 폴더에서 실행한다. Python은 저장소 루트의 `.venv`를 쓴다.

```bash
cd src/card_benefit/sql/tools/v7_verification
npm install

# 1. 실제 행 내려받기 (읽기 전용)
../../../../../.venv/Scripts/python export_live_rows.py

# 2. 이관, 롤백, 재이관 시험 (메모리 DB)
node migrate_test.mjs live
node migrate_test.mjs file
```

| 실행 인자 | 의미 |
|---|---|
| `live` | 실제 DB 상태처럼 `card_product_doc`의 `effective_*`를 지운 V6. **기준 시험** |
| `file` | V6 파일 그대로. 롤백 시 `effective_*` 차이가 나오는 것이 정상이다 |

**`live` 합격 기준**

- `catalog fresh-V7 vs migrated diffs: 0`
- 공통코드와 그룹이 V7 시드와 같음
- 데이터 비교가 모두 `SAME`, `UNEXPECTED change` 없음
- `integrity test`가 두 줄 모두 `PASS`
- `rollback catalog diffs: 0`, `ROLLBACK data diff` 없음
- `re-migrate after rollback: OK`
- 각 guard가 **자기 조건의 메시지로** 중단. 다른 메시지로 멈추면 그 안전장치는 검증된 것이 아니다

`migrate_test.mjs`의 기대값은 현재 샘플 데이터(혜택 4, 한도 9, 근거 31, 연결 62)와 V6→V7 이관을 전제로 한다. V7 적용 후나 데이터가 바뀐 뒤에는 그대로 쓸 수 없다.

## 카탈로그 비교

```bash
# V6 파일과 실제 DB의 차이 (읽기 전용)
node catalog_dump.mjs .work/v6_catalog.json ../../db_pipeline_schemaV6_draft.sql ../../db_pipeline_common_code_seedV6.sql ../../db_pipeline_common_code_descV6.sql
../../../../../.venv/Scripts/python catalog_diff.py .work/v6_catalog.json
```

현재 정상 결과는 `card_product_doc`의 컬럼 2개, CHECK 2개, 인덱스 1개 차이다.

## DBML 파싱

```bash
node -e "const {Parser}=require('@dbml/core');const t=new Parser().parse(require('fs').readFileSync('../../db_pipeline_schemaV7_draft.dbml','utf8'),'dbml').schemas.flatMap(x=>x.tables);console.log(t.length,t.reduce((a,x)=>a+x.fields.length,0))"
```

TEXT 단순화 후 기대값은 테이블 14, 컬럼 199다.

## 실제 DB 트랜잭션 시험

**사용자 승인 후 실행한다.** 이관을 트랜잭션 안에서 실행하고 무결성 시험까지 마친 뒤 항상 ROLLBACK한다. 코드에 COMMIT 경로는 없지만, 실행 중에는 대상 테이블이 잠겨 다른 팀원의 작업이 대기할 수 있다. 재실행 전에 다른 작업이 없는지 확인한다.

```bash
../../../../../.venv/Scripts/python live_rollback_dryrun.py --run-with-rollback
```

`ROLLED BACK`과 `live intact ... (True, True, True)`가 출력되어야 한다. 이관 스냅샷은 `.work/v7_snapshot.pkl`에 저장된다. 실제 DB가 V7이 된 뒤에는 쓰지 않는다.

## Neo4j 격리 시험

**사용자 승인 후 실행한다.** 공유 Aura DB에 쓴다.

```bash
../../../../../.venv/Scripts/python neo4j_isolated_test.py --write-test-namespace
```

- 먼저 `live_rollback_dryrun.py`로 `.work/v7_snapshot.pkl`을 만든다.
- 쓰기와 삭제는 `namespace = df_v7_test`로 한정되고 운영 네임스페이스 `df_one_pick_style`은 전후 해시만 비교한다.
- 시험 네임스페이스에 데이터가 남아 있으면 시작하지 않는다.
- 시험 중에는 다른 사람의 `neo4j_validate`가 `outside_scope` 위반을 볼 수 있다.
- `neo4j_load_draft.py`의 `--confirm` 승인 절차를 거치지 않고 쓰기 함수를 직접 호출한다. 운영 적재에 이 도구를 쓰면 안 된다.
- 샘플 카드 1장 구조만 다룬다. 2단계 다중 카드 구현 후에는 함께 수정해야 한다.
- 마지막 실행은 V7 1차 스키마 시점이다. 최종 스키마로는 실행하지 않았다.

## 참고용 생성기

`reference/gen_v7_reference.py`는 V6 원본에 V7 변경을 1차(정책 버전), 2차(공통 혜택), 3차(방법 카탈로그) 순서로 적용한 기록이다. 어떤 문자열이 왜 바뀌었는지 볼 때 쓴다.

```bash
../../../../../.venv/Scripts/python reference/gen_v7_reference.py --out .work/gen
```

- `--out`이 없으면 실행되지 않고, 최종 SQL 폴더를 지정하면 거부한다.
- 이 생성기는 연결 테이블 도입 전 V7을 재현한다. 현재 최종 V7 SQL과 다르며 현재 파일을 덮어쓰면 안 된다.
- **V7 파일을 직접 고치면 이 출력과 달라진다. 그때는 V7 파일이 맞다.** 생성기를 고쳐 맞추거나 생성기 결과로 V7을 덮어쓰지 않는다.
- V6 파일을 읽어 정확히 일치하는 문자열만 치환한다. V6 파일이 바뀌면 중단될 수 있다.
- V7의 `db_pipeline_v7_integrity_test.sql`, `db_pipeline_V7_change_report.md`, `tests/test_v7_sql_files.py`는 생성 대상이 아니다.

## 이 폴더에 없는 것

- **실제 전환 도구:** 이관 SQL 실행, 전체 백업, 운영 Neo4j 교체 도구는 없다. 절차는 `../../V7_CODEX_HANDOFF.md`를 따르고 사용자 승인 후 진행한다.
- **일회성 스크립트:** 파일 패치, 조사, 이미 끝난 공통코드 적용 스크립트는 보존하지 않았다.
