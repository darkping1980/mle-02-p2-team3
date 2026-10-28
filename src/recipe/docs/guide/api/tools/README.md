# recipe_recommender.tools Package Summary

[API 전체 목차](../README.md) · [파일 인덱스](../../02_file_structure.md)

연결 점검, 스키마 재구축·초기화 도구를 담는 실제 하위 패키지. 모듈 7개를 다룬다.

## Module Summary

| 모듈 상세 | 소스 | 역할 |
| --- | --- | --- |
| [_connection_util](_connection_util.md) | [_connection_util.py](../../../../recipe_recommender/tools/_connection_util.py) | 단독 연결 점검 도구가 공유하는 경로 준비와 오류 메시지 정리 함수. |
| [_sql_script](_sql_script.md) | [_sql_script.py](../../../../recipe_recommender/tools/_sql_script.py) | BEGIN/COMMIT을 포함한 관리용 SQL 스크립트(재생성·초기화)를 실행하는 공통 도우미. |
| [check_neo4j_connection](check_neo4j_connection.md) | [check_neo4j_connection.py](../../../../recipe_recommender/tools/check_neo4j_connection.py) | 기존 환경변수로 Neo4j 연결과 읽기 쿼리를 확인하는 단독 실행 도구. |
| [check_supabase_connection](check_supabase_connection.md) | [check_supabase_connection.py](../../../../recipe_recommender/tools/check_supabase_connection.py) | 기존 ``DB_URL``로 PostgreSQL 읽기 연결을 확인하는 단독 실행 도구. |
| [rebuild_recipe_schema](rebuild_recipe_schema.md) | [rebuild_recipe_schema.py](../../../../recipe_recommender/tools/rebuild_recipe_schema.py) | 기존 모델 전용 스키마 재생성 도구. `--confirm-rebuild`는 현재 차단되며, 인자 없이 현황만 조회한다. |
| [recipe_rebuild](recipe_rebuild.md) | [recipe_rebuild.py](../../../../recipe_recommender/tools/recipe_rebuild.py) | 레시피 PostgreSQL 목표 모델 재구축 도구(백업 → 복원 시험 → 격리 리허설 → 전환 → 복구). |
| [reset_recipe_data](reset_recipe_data.md) | [reset_recipe_data.py](../../../../recipe_recommender/tools/reset_recipe_data.py) | 기존 모델 전용 초기화 도구. `--confirm-reset`은 현재 차단되며, 인자 없이 현황만 조회한다. |

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [RebuildError](recipe_rebuild.md#rebuilderror) | 예외 클래스 | 재구축을 중단해야 하는 사전 조건·검증 실패. |

## Data Model Summary

이 패키지에는 최상위 TypedDict·Pydantic 모델·dataclass DTO가 없다. 관리 명령의 입력과 결과는 각 모듈의 Function Detail에서 확인한다.

## Function Summary

| 모듈 함수 | 설명 |
| --- | --- |
| [_connection_util.initialize](_connection_util.md#function-initialize) | 단독 실행 도구가 패키지 경로와 환경변수를 읽도록 준비한다. |
| [_connection_util.safe_error](_connection_util.md#function-safe_error) | 오류의 원인은 유지하면서 설정된 자격 증명과 URL 사용자 정보를 가린다. |
| [_sql_script.print_state](_sql_script.md#function-print_state) | recipe 스키마 객체와 테이블 행 수, 시퀀스 현재값을 출력한다(읽기 전용). |
| [_sql_script.run_sql_script](_sql_script.md#function-run_sql_script) | 스크립트 실행 전후 상태를 출력하고, ``confirmed`` 일 때만 실제로 실행한다. Returns 종료 코드. |
| [check_neo4j_connection.main](check_neo4j_connection.md#function-main) | Neo4j에 연결해 읽기 쿼리 한 건으로 연결 상태를 확인한다. |
| [check_supabase_connection._run_query](check_supabase_connection.md#function-_run_query) | 공통 연결 관리자로 SELECT를 실행하고 의존 패키지가 없을 때 psycopg를 쓴다. |
| [check_supabase_connection._target_label](check_supabase_connection.md#function-_target_label) | ``DB_URL`` 호스트와 설정값을 기준으로 확인한 대상의 표시명을 고른다. |
| [check_supabase_connection.main](check_supabase_connection.md#function-main) | PostgreSQL에 연결해 SELECT 한 건으로 연결 상태를 확인한다. |
| [rebuild_recipe_schema.main](rebuild_recipe_schema.md#function-main) | 기존 모델 전용 스키마 재생성 진입점의 실행 차단 조건을 적용한다. |
| [recipe_rebuild.connect](recipe_rebuild.md#function-connect) | ``DB_URL`` 로 단독 연결을 연다(pool 미사용, 자동 prepared statement 끔: pooler 호환). |
| [recipe_rebuild.read_only](recipe_rebuild.md#function-read_only) | 하나의 스냅샷으로 읽는 READ ONLY 트랜잭션. 끝나면 항상 ROLLBACK한다. |
| [recipe_rebuild.describe_target](recipe_rebuild.md#function-describe_target) | 비밀번호를 제외한 실제 연결 대상. |
| [recipe_rebuild.target_label](recipe_rebuild.md#function-target_label) | DB 식별 정보를 사람이 확인할 대상 문자열로 표현한다. |
| [recipe_rebuild.require_confirmed_db](recipe_rebuild.md#function-require_confirmed_db) | ``--confirm-db`` 가 실제 ``host/dbname`` 과 정확히 같을 때만 쓰기를 허용한다. |
| [recipe_rebuild.schema_exists](recipe_rebuild.md#function-schema_exists) | 지정한 PostgreSQL 스키마의 존재 여부를 카탈로그에서 조회한다. |
| [recipe_rebuild.schema_comment](recipe_rebuild.md#function-schema_comment) | 스키마의 소유 표식으로 쓰는 COMMENT를 조회한다. |
| [recipe_rebuild.catalog_pks](recipe_rebuild.md#function-catalog_pks) | 카탈로그에서 테이블별 기본 키 컬럼을 읽는다. |
| [recipe_rebuild.catalog_tables](recipe_rebuild.md#function-catalog_tables) | 스키마의 테이블 이름을 카탈로그에서 읽는다. |
| [recipe_rebuild.catalog_objects](recipe_rebuild.md#function-catalog_objects) | 스키마 안의 테이블·시퀀스·뷰 등 관계 객체(인덱스 제외)와 함수. |
| [recipe_rebuild.catalog_columns](recipe_rebuild.md#function-catalog_columns) | 스키마 컬럼의 타입과 NULL 허용 여부를 읽는다. |
| [recipe_rebuild.table_fingerprints](recipe_rebuild.md#function-table_fingerprints) | 테이블별 행 수와 PK 순서 행 텍스트의 md5(같은 세션 설정에서 비교용). |
| [recipe_rebuild.check_legacy_source](recipe_rebuild.md#function-check_legacy_source) | 이전 모델 원천의 구조가 전환 조건을 만족하는지 검증한다. |
| [recipe_rebuild.check_target_structure](recipe_rebuild.md#function-check_target_structure) | 대상 스키마가 목표 설계(PK·테이블·시퀀스·인덱스·컬럼·COMMENT)대로 만들어졌는지 검사한다. |
| [recipe_rebuild.run_validation](recipe_rebuild.md#function-run_validation) | 검증 SQL 결과를 기대값과 비교한다. cnt_* 는 기준 건수(baseline=False면 원본 건수), 나머지는 0. |
| [recipe_rebuild.print_validation](recipe_rebuild.md#function-print_validation) | 검증 항목과 실패 여부를 콘솔에 출력한다. |
| [recipe_rebuild._sha256](recipe_rebuild.md#function-_sha256) | 백업 파일의 SHA-256 해시를 계산한다. |
| [recipe_rebuild.backup](recipe_rebuild.md#function-backup) | 원본 스키마 전체(전 테이블 행, 시퀀스 상태, 정의·COMMENT)를 한 스냅샷으로 파일에 남긴다(읽기 전용). |
| [recipe_rebuild.load_manifest](recipe_rebuild.md#function-load_manifest) | 백업 폴더의 manifest를 읽어 복원 검증에 전달한다. |
| [recipe_rebuild.verify_backup_files](recipe_rebuild.md#function-verify_backup_files) | 파일 해시와 CSV 레코드 수가 manifest와 같은지 확인한다(DB 불필요). Returns 문제 목록. |
| [recipe_rebuild.verify_backup_live](recipe_rebuild.md#function-verify_backup_live) | 백업 이후 원본 스키마가 바뀌지 않았는지(행 수·행 md5) 확인한다(읽기 전용). |
| [recipe_rebuild.restore_test](recipe_rebuild.md#function-restore_test) | 백업 파일을 기존 모델 DDL로 만든 임시 스키마에 COPY로 복원해 원본 md5와 비교한다. |
| [recipe_rebuild._lock_source](recipe_rebuild.md#function-_lock_source) | 전환 도중 원천 스키마의 동시 변경을 막도록 잠근다. |
| [recipe_rebuild.build_target](recipe_rebuild.md#function-build_target) | 열린 트랜잭션 안에서 대상 스키마 생성 → DDL → 이관 → 구조·데이터 검증. 실패 시 RebuildError. |
| [recipe_rebuild.build](recipe_rebuild.md#function-build) | 목표 스키마를 구축하고 검증 결과를 확인한다. |
| [recipe_rebuild.validate](recipe_rebuild.md#function-validate) | 원천과 목표 스키마의 데이터 정합성을 검사한다. |
| [recipe_rebuild.drop_schema](recipe_rebuild.md#function-drop_schema) | 이 도구가 만든 리허설·복원 시험 스키마만 개별 객체 DROP 후 DROP SCHEMA RESTRICT로 지운다. |
| [recipe_rebuild.cutover](recipe_rebuild.md#function-cutover) | 운영 ``recipe`` 를 ``legacy_schema`` 로 이름만 바꿔 보존하고, 그 데이터로 새 ``recipe`` 를 만든다. |
| [recipe_rebuild.rollback_cutover](recipe_rebuild.md#function-rollback_cutover) | 전환을 되돌린다: 새 ``recipe`` 를 ``recipe_failed_<시각>`` 으로, 보존 스키마를 ``recipe`` 로 이름만 바꾼다. |
| [recipe_rebuild.parse_args](recipe_rebuild.md#function-parse_args) | 백업·구축·전환·복구 명령과 필수 확인 인자를 파싱한다. |
| [recipe_rebuild.inspect](recipe_rebuild.md#function-inspect) | 대상 DB와 스키마 상태를 변경 없이 출력한다. |
| [recipe_rebuild.main](recipe_rebuild.md#function-main) | 선택한 재구축 명령을 실행하고 성공 또는 실패 종료 코드를 반환한다. |
| [reset_recipe_data.main](reset_recipe_data.md#function-main) | 기존 모델 전용 데이터 초기화 진입점의 실행 차단 조건을 적용한다. |

## 관련 가이드

- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
