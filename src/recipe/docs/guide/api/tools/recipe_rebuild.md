# recipe_rebuild 모듈

[API 전체 목차](../README.md) · [패키지 요약](README.md) · [파일 인덱스](../../02_file_structure.md)

## Module Summary

- **모듈:** `recipe_recommender.tools.recipe_rebuild`
- **소스:** [recipe_recommender/tools/recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py)
- **역할:** 레시피 PostgreSQL 목표 모델 재구축 도구(백업 → 복원 시험 → 격리 리허설 → 전환 → 복구).
- **주요 호출자:** 명시적으로 실행한 관리 CLI
- **정의:** 클래스 1개, 모듈 함수 32개

- **직접 의존:** `recipe_recommender.config`, `recipe_recommender.sql_schema`, `recipe_recommender.tools._connection_util`

- **실행:** `python -m recipe_recommender.tools.recipe_rebuild`

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [RebuildError](#rebuilderror) | 예외 클래스 | 재구축을 중단해야 하는 사전 조건·검증 실패. |

## Function Summary

| 함수 | 반환형 | 설명 |
| --- | --- | --- |
| [connect](#function-connect) | `타입 힌트 없음` | ``DB_URL`` 로 단독 연결을 연다(pool 미사용, 자동 prepared statement 끔: pooler 호환). |
| [read_only](#function-read_only) | `타입 힌트 없음` | 하나의 스냅샷으로 읽는 READ ONLY 트랜잭션. 끝나면 항상 ROLLBACK한다. |
| [describe_target](#function-describe_target) | `dict` | 비밀번호를 제외한 실제 연결 대상. |
| [target_label](#function-target_label) | `str` | DB 식별 정보를 사람이 확인할 대상 문자열로 표현한다. |
| [require_confirmed_db](#function-require_confirmed_db) | `dict` | ``--confirm-db`` 가 실제 ``host/dbname`` 과 정확히 같을 때만 쓰기를 허용한다. |
| [schema_exists](#function-schema_exists) | `bool` | 지정한 PostgreSQL 스키마의 존재 여부를 카탈로그에서 조회한다. |
| [schema_comment](#function-schema_comment) | `str \| None` | 스키마의 소유 표식으로 쓰는 COMMENT를 조회한다. |
| [catalog_pks](#function-catalog_pks) | `dict[str, list[str]]` | 카탈로그에서 테이블별 기본 키 컬럼을 읽는다. |
| [catalog_tables](#function-catalog_tables) | `list[str]` | 스키마의 테이블 이름을 카탈로그에서 읽는다. |
| [catalog_objects](#function-catalog_objects) | `list[dict]` | 스키마 안의 테이블·시퀀스·뷰 등 관계 객체(인덱스 제외)와 함수. |
| [catalog_columns](#function-catalog_columns) | `dict[tuple[str, str], tuple[str, bool]]` | 스키마 컬럼의 타입과 NULL 허용 여부를 읽는다. |
| [table_fingerprints](#function-table_fingerprints) | `dict[str, dict]` | 테이블별 행 수와 PK 순서 행 텍스트의 md5(같은 세션 설정에서 비교용). |
| [check_legacy_source](#function-check_legacy_source) | `None` | 이전 모델 원천의 구조가 전환 조건을 만족하는지 검증한다. |
| [check_target_structure](#function-check_target_structure) | `list[str]` | 대상 스키마가 목표 설계(PK·테이블·시퀀스·인덱스·컬럼·COMMENT)대로 만들어졌는지 검사한다. |
| [run_validation](#function-run_validation) | `list[dict]` | 검증 SQL 결과를 기대값과 비교한다. cnt_* 는 기준 건수(baseline=False면 원본 건수), 나머지는 0. |
| [print_validation](#function-print_validation) | `bool` | 검증 항목과 실패 여부를 콘솔에 출력한다. |
| [_sha256](#function-_sha256) | `str` | 백업 파일의 SHA-256 해시를 계산한다. |
| [backup](#function-backup) | `dict` | 원본 스키마 전체(전 테이블 행, 시퀀스 상태, 정의·COMMENT)를 한 스냅샷으로 파일에 남긴다(읽기 전용). |
| [load_manifest](#function-load_manifest) | `dict` | 백업 폴더의 manifest를 읽어 복원 검증에 전달한다. |
| [verify_backup_files](#function-verify_backup_files) | `list[str]` | 파일 해시와 CSV 레코드 수가 manifest와 같은지 확인한다(DB 불필요). Returns 문제 목록. |
| [verify_backup_live](#function-verify_backup_live) | `list[str]` | 백업 이후 원본 스키마가 바뀌지 않았는지(행 수·행 md5) 확인한다(읽기 전용). |
| [restore_test](#function-restore_test) | `list[str]` | 백업 파일을 기존 모델 DDL로 만든 임시 스키마에 COPY로 복원해 원본 md5와 비교한다. |
| [_lock_source](#function-_lock_source) | `None` | 전환 도중 원천 스키마의 동시 변경을 막도록 잠근다. |
| [build_target](#function-build_target) | `list[dict]` | 열린 트랜잭션 안에서 대상 스키마 생성 → DDL → 이관 → 구조·데이터 검증. 실패 시 RebuildError. |
| [build](#function-build) | `None` | 목표 스키마를 구축하고 검증 결과를 확인한다. |
| [validate](#function-validate) | `bool` | 원천과 목표 스키마의 데이터 정합성을 검사한다. |
| [drop_schema](#function-drop_schema) | `None` | 이 도구가 만든 리허설·복원 시험 스키마만 개별 객체 DROP 후 DROP SCHEMA RESTRICT로 지운다. |
| [cutover](#function-cutover) | `None` | 운영 ``recipe`` 를 ``legacy_schema`` 로 이름만 바꿔 보존하고, 그 데이터로 새 ``recipe`` 를 만든다. |
| [rollback_cutover](#function-rollback_cutover) | `str` | 전환을 되돌린다: 새 ``recipe`` 를 ``recipe_failed_<시각>`` 으로, 보존 스키마를 ``recipe`` 로 이름만 바꾼다. |
| [parse_args](#function-parse_args) | `argparse.Namespace` | 백업·구축·전환·복구 명령과 필수 확인 인자를 파싱한다. |
| [inspect](#function-inspect) | `None` | 대상 DB와 스키마 상태를 변경 없이 출력한다. |
| [main](#function-main) | `int` | 선택한 재구축 명령을 실행하고 성공 또는 실패 종료 코드를 반환한다. |

## RebuildError

**예외 클래스.** 재구축을 중단해야 하는 사전 조건·검증 실패.

- **정의:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (98행)
- **생성 위치:** 직접 생성 호출은 주요 진입 경로에서 확인되지 않음; 정의와 호출 코드를 참조한다.

### Constructor Summary

명시적 `__init__`가 없다. 상위 클래스 또는 Python 기본 생성자를 사용한다.

## Function connect

```python
def connect():
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `타입 힌트 없음`. ``DB_URL`` 로 단독 연결을 연다(pool 미사용, 자동 prepared statement 끔: pooler 호환).
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (105행)

## Function read_only

```python
@contextmanager
def read_only(connection):
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `타입 힌트 없음`. 하나의 스냅샷으로 읽는 READ ONLY 트랜잭션. 끝나면 항상 ROLLBACK한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (119행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |

## Function describe_target

```python
def describe_target(connection) -> dict:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `dict`. 비밀번호를 제외한 실제 연결 대상.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (128행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |

## Function target_label

```python
def target_label(target: dict) -> str:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `str`. DB 식별 정보를 사람이 확인할 대상 문자열로 표현한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (137행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `target` | `dict` | 대상 스키마 또는 대상 정보 |

## Function require_confirmed_db

```python
def require_confirmed_db(connection, confirm_db: str | None) -> dict:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `dict`. ``--confirm-db`` 가 실제 ``host/dbname`` 과 정확히 같을 때만 쓰기를 허용한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (142행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `confirm_db` | `str \| None` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function schema_exists

```python
def schema_exists(connection, schema: str) -> bool:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `bool`. 지정한 PostgreSQL 스키마의 존재 여부를 카탈로그에서 조회한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (155행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `schema` | `str` | PostgreSQL 대상 스키마 |

## Function schema_comment

```python
def schema_comment(connection, schema: str) -> str | None:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `str | None`. 스키마의 소유 표식으로 쓰는 COMMENT를 조회한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (160행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `schema` | `str` | PostgreSQL 대상 스키마 |

## Function catalog_pks

```python
def catalog_pks(connection, schema: str) -> dict[str, list[str]]:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `dict[str, list[str]]`. 카탈로그에서 테이블별 기본 키 컬럼을 읽는다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (167행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `schema` | `str` | PostgreSQL 대상 스키마 |

## Function catalog_tables

```python
def catalog_tables(connection, schema: str) -> list[str]:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `list[str]`. 스키마의 테이블 이름을 카탈로그에서 읽는다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (183행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `schema` | `str` | PostgreSQL 대상 스키마 |

## Function catalog_objects

```python
def catalog_objects(connection, schema: str) -> list[dict]:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `list[dict]`. 스키마 안의 테이블·시퀀스·뷰 등 관계 객체(인덱스 제외)와 함수.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (190행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `schema` | `str` | PostgreSQL 대상 스키마 |

## Function catalog_columns

```python
def catalog_columns(connection, schema: str) -> dict[tuple[str, str], tuple[str, bool]]:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `dict[tuple[str, str], tuple[str, bool]]`. 스키마 컬럼의 타입과 NULL 허용 여부를 읽는다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (201행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `schema` | `str` | PostgreSQL 대상 스키마 |

## Function table_fingerprints

```python
def table_fingerprints(connection, schema: str, pks: dict[str, list[str]]) -> dict[str, dict]:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `dict[str, dict]`. 테이블별 행 수와 PK 순서 행 텍스트의 md5(같은 세션 설정에서 비교용).
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (211행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `schema` | `str` | PostgreSQL 대상 스키마 |
| `pks` | `dict[str, list[str]]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function check_legacy_source

```python
def check_legacy_source(connection, source: str) -> None:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `None`. 이전 모델 원천의 구조가 전환 조건을 만족하는지 검증한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (223행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `source` | `str` | PostgreSQL 원천 또는 원천 Repository |

## Function check_target_structure

```python
def check_target_structure(connection, target: str, source: str) -> list[str]:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `list[str]`. 대상 스키마가 목표 설계(PK·테이블·시퀀스·인덱스·컬럼·COMMENT)대로 만들어졌는지 검사한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (230행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `target` | `str` | 대상 스키마 또는 대상 정보 |
| `source` | `str` | PostgreSQL 원천 또는 원천 Repository |

## Function run_validation

```python
def run_validation(connection, source: str, target: str, *, baseline: bool=True) -> list[dict]:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `list[dict]`. 검증 SQL 결과를 기대값과 비교한다. cnt_* 는 기준 건수(baseline=False면 원본 건수), 나머지는 0.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (276행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `source` | `str` | PostgreSQL 원천 또는 원천 Repository |
| `target` | `str` | 대상 스키마 또는 대상 정보 |
| `baseline` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function print_validation

```python
def print_validation(results: list[dict]) -> bool:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `bool`. 검증 항목과 실패 여부를 콘솔에 출력한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (291행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `results` | `list[dict]` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _sha256

```python
def _sha256(path: Path) -> str:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `str`. 백업 파일의 SHA-256 해시를 계산한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (305행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `path` | `Path` | 읽거나 쓸 파일 경로 |

## Function backup

```python
def backup(connection, source: str, out_dir: Path) -> dict:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `dict`. 원본 스키마 전체(전 테이블 행, 시퀀스 상태, 정의·COMMENT)를 한 스냅샷으로 파일에 남긴다(읽기 전용).
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (314행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `source` | `str` | PostgreSQL 원천 또는 원천 Repository |
| `out_dir` | `Path` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function load_manifest

```python
def load_manifest(backup_dir: Path) -> dict:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `dict`. 백업 폴더의 manifest를 읽어 복원 검증에 전달한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (391행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `backup_dir` | `Path` | 백업 파일이 있는 폴더 |

## Function verify_backup_files

```python
def verify_backup_files(backup_dir: Path) -> list[str]:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `list[str]`. 파일 해시와 CSV 레코드 수가 manifest와 같은지 확인한다(DB 불필요). Returns 문제 목록.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (399행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `backup_dir` | `Path` | 백업 파일이 있는 폴더 |

## Function verify_backup_live

```python
def verify_backup_live(connection, backup_dir: Path) -> list[str]:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `list[str]`. 백업 이후 원본 스키마가 바뀌지 않았는지(행 수·행 md5) 확인한다(읽기 전용).
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (421행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `backup_dir` | `Path` | 백업 파일이 있는 폴더 |

## Function restore_test

```python
def restore_test(connection, backup_dir: Path, schema: str, *, keep: bool=False) -> list[str]:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `list[str]`. 백업 파일을 기존 모델 DDL로 만든 임시 스키마에 COPY로 복원해 원본 md5와 비교한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (437행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `backup_dir` | `Path` | 백업 파일이 있는 폴더 |
| `schema` | `str` | PostgreSQL 대상 스키마 |
| `keep` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function _lock_source

```python
def _lock_source(connection, source: str, mode: str) -> None:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `None`. 전환 도중 원천 스키마의 동시 변경을 막도록 잠근다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (483행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `source` | `str` | PostgreSQL 원천 또는 원천 Repository |
| `mode` | `str` | 실행 또는 로그 방식 |

## Function build_target

```python
def build_target(connection, source: str, target: str, *, baseline: bool, marker: str) -> list[dict]:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `list[dict]`. 열린 트랜잭션 안에서 대상 스키마 생성 → DDL → 이관 → 구조·데이터 검증. 실패 시 RebuildError.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (489행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `source` | `str` | PostgreSQL 원천 또는 원천 Repository |
| `target` | `str` | 대상 스키마 또는 대상 정보 |
| `baseline` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `marker` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function build

```python
def build(connection, source: str, target: str, *, baseline: bool) -> None:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `None`. 목표 스키마를 구축하고 검증 결과를 확인한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (512행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `source` | `str` | PostgreSQL 원천 또는 원천 Repository |
| `target` | `str` | 대상 스키마 또는 대상 정보 |
| `baseline` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function validate

```python
def validate(connection, source: str, target: str, *, baseline: bool) -> bool:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `bool`. 원천과 목표 스키마의 데이터 정합성을 검사한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (521행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `source` | `str` | PostgreSQL 원천 또는 원천 Repository |
| `target` | `str` | 대상 스키마 또는 대상 정보 |
| `baseline` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function drop_schema

```python
def drop_schema(connection, schema: str) -> None:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `None`. 이 도구가 만든 리허설·복원 시험 스키마만 개별 객체 DROP 후 DROP SCHEMA RESTRICT로 지운다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (530행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `schema` | `str` | PostgreSQL 대상 스키마 |

## Function cutover

```python
def cutover(connection, legacy_schema: str, backup_dir: Path, *, baseline: bool) -> None:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `None`. 운영 ``recipe`` 를 ``legacy_schema`` 로 이름만 바꿔 보존하고, 그 데이터로 새 ``recipe`` 를 만든다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (554행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `legacy_schema` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |
| `backup_dir` | `Path` | 백업 파일이 있는 폴더 |
| `baseline` | `bool` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function rollback_cutover

```python
def rollback_cutover(connection, legacy_schema: str) -> str:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `str`. 전환을 되돌린다: 새 ``recipe`` 를 ``recipe_failed_<시각>`` 으로, 보존 스키마를 ``recipe`` 로 이름만 바꾼다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (582행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |
| `legacy_schema` | `str` | 호출자가 전달하는 값; 세부 제약은 Docstring과 소스 참조 |

## Function parse_args

```python
def parse_args(argv=None) -> argparse.Namespace:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `argparse.Namespace`. 백업·구축·전환·복구 명령과 필수 확인 인자를 파싱한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (601행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `argv` | `타입 힌트 없음` | CLI 인자 목록; 생략하면 프로세스 인자를 사용 |

## Function inspect

```python
def inspect(connection) -> None:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `None`. 대상 DB와 스키마 상태를 변경 없이 출력한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (644행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `connection` | `타입 힌트 없음` | 현재 DB 연결 |

## Function main

```python
def main(argv=None) -> int:
```

- **호출자:** 명시적으로 실행한 관리 CLI
- **반환:** `int`. 선택한 재구축 명령을 실행하고 성공 또는 실패 종료 코드를 반환한다.
- **원본:** [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) (657행)

| 매개변수 | 타입 힌트 | 의미 |
| --- | --- | --- |
| `argv` | `타입 힌트 없음` | CLI 인자 목록; 생략하면 프로세스 인자를 사용 |

## 관련 가이드

- [컴포넌트 관계](../../03_component_structure.md)
- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
