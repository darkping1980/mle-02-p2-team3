# 레시피 PostgreSQL 목표 모델 재구축 절차서·실행 기록

상태: **2026-10-22 적용 완료.** 개발·테스트용 Supabase DB(`aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres`)의
`recipe` 스키마를 목표 모델로 전환했다. 기존 모델은 `recipe_legacy_20261022` 스키마에 그대로 보존되어 있다.
Neo4j는 변경하지 않았다(코드만 목표 모델에 맞춤).

## 1. 산출물

| 구분 | 파일 | 역할 |
|---|---|---|
| 목표 DDL | `docs/db/recipe_target_schema.sql` | 최종 11개 테이블·6개 시퀀스·업무 ID 함수·인덱스·COMMENT. `recipe_multi_category_target.sql`(식재료 분류 유지 초안)을 대체 |
| 이관 | `docs/db/recipe_target_migration.sql` | 기존 모델 → 목표 모델. 업무 ID·이력 컬럼을 값 그대로 복사, 시퀀스 위치 보정 |
| 검증 | `docs/db/recipe_target_validation.sql` | 65개 항목 SELECT 하나(건수·양방향 행 차이·정보 손실·고아·중복·183건 설명·시퀀스) |
| 도구 | `recipe_recommender/tools/recipe_rebuild.py` | inspect / backup / verify-backup / restore-test / build / validate / drop-schema / cutover / rollback-cutover |
| 스키마 지정 | `recipe_recommender/sql_schema.py` | `recipe.`·`recipe_src.` 한정자 치환(격리 스키마 실행용) |

DDL·이관 SQL은 `recipe.`(대상)·`recipe_src.`(원본) 한정자로 작성되어 있고 도구가 실제 스키마 이름으로 치환한다.
직접 SQL 클라이언트에서 실행하지 않는다.

## 2. 목표 구조

| 테이블 | PK | 기존 대비 |
|---|---|---|
| `rcp_raw` | `(rcp_raw_id, rcp_raw_seq)` | 변경 없음 |
| `rcp_cat` | `(rcp_cat_id)`, UNIQUE `rcp_cat_nm` | 변경 없음 |
| `rcp_cat_rel` | `(rcp_id, rcp_cat_id)` + 역방향 인덱스 `(rcp_cat_id, rcp_id)` | **신규** N:M |
| `common_code_grp` / `common_cd` | `(common_code_grp_id)` / `(common_code_grp_id, common_cd)` | 변경 없음 |
| `rcp` | `(rcp_id)`, UNIQUE `rcp_seq` | `rcp_cat_id` 컬럼·`uq_rcp_rcp_id` 제거 |
| `rcp_step` | `(rcp_id, step_no)` | `rcp_cat_id` 제거 |
| `ingr` | `(ingr_id)`, UNIQUE `ingr_nm` | `ingr_cat_id` 제거 |
| `ingr_als` | `(ingr_id, ingr_als_id)`, UNIQUE `(ingr_id, ingr_als_nm)` | `ingr_cat_id` 제거, **별칭 ID·데이터 유지** |
| `rcp_ingr_stg` | `(rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id)` + 인덱스 `(ingr_id)` | 매핑 컬럼 `ingr_id` 하나 |
| `rcp_ingr` | `(rcp_id, ingr_id)` + 역방향 인덱스 `(ingr_id, rcp_id)` | 분류 키 2개 제거 |
| `ingr_cat`, `seq_ingr_cat` | — | **제거** (보존 스키마·백업 파일에만 존재) |

유지한 관례: `VARCHAR(20)` `YYYYMMDD_000001` 업무 ID와 `fn_get_biz_id` DEFAULT, 물리 FK 없음, 관계 테이블의
부모 PK 승계 복합 PK, 모든 테이블·컬럼 한글 COMMENT. `fn_get_biz_id`는 시퀀스 위치를 렌더링된 스키마 한정자로
고정한다(`search_path` 비의존). `rcp_cat`의 분류 기준 축 컬럼(`rcp_cat_axis_cd`)은 코드 정책이 정해지지 않아
도입하지 않았다.

## 3. 실행 순서 (2026-10-22 실제 수행 기록)

모든 쓰기 명령은 `--confirm-db <host>/<dbname>`이 실제 연결 대상과 같아야 실행된다.

```text
python -m recipe_recommender.tools.recipe_rebuild inspect
python -m recipe_recommender.tools.recipe_rebuild backup --source recipe --out D:/Bootcamp/vscode/workspace/graph-rag-db-backups/recipe_20261022_pre_target_model
python -m recipe_recommender.tools.recipe_rebuild verify-backup --dir <백업> --live
python -m recipe_recommender.tools.recipe_rebuild restore-test --dir <백업> --schema recipe_restore_chk --confirm-db H/D
python -m recipe_recommender.tools.recipe_rebuild build --source recipe --target recipe_v2 --confirm-db H/D
python -m recipe_recommender.setup.register_recipe_csv --full --rehearse --schema recipe_v2
python -m recipe_recommender.tools.recipe_rebuild cutover --legacy-schema recipe_legacy_20261022 --backup-dir <백업> --confirm-cutover --confirm-db H/D
python -m recipe_recommender.tools.recipe_rebuild validate --source recipe_legacy_20261022 --target recipe
python -m recipe_recommender.setup.register_recipe_csv --full --rehearse
python -m recipe_recommender.setup.register_recipe_csv --full
python -m recipe_recommender.tools.recipe_rebuild validate --source recipe_legacy_20261022 --target recipe
python -m recipe_recommender.tools.recipe_rebuild drop-schema --schema recipe_v2 --confirm-schema recipe_v2 --confirm-db H/D
```

| 단계 | 결과 |
|---|---|
| 대상 확인 | Supabase session pooler, DB `postgres`, PostgreSQL 17.6. `recipe%` 스키마는 `recipe` 하나 |
| 백업 | 11개 테이블 CSV(전 컬럼, NULL/빈 문자열 구분, PK 순), `catalog.json`(컬럼·제약·인덱스·COMMENT·함수 정의·시퀀스 상태), `manifest.json`(SHA-256, 행 수, 행 md5, CSV·시드·기존 DDL 해시). REPEATABLE READ READ ONLY 단일 스냅샷 |
| 백업 검증 | 파일 해시·레코드 수 일치, 현재 DB 행 md5 일치 |
| 복원 시험 | 기존 모델 DDL로 임시 스키마 생성 → COPY 복원 → 11개 테이블 행 md5·7개 시퀀스·PK 일치 → ROLLBACK |
| 격리 리허설 `recipe_v2` | 구조 검사 OK, 검증 65/65 |
| ETL 리허설(`recipe_v2`) | CRLF CSV가 `SAME_BATCH_RERUN`, 전 테이블 신규·변경 0, 정합성 0 → ROLLBACK |
| 전환 | 한 트랜잭션: 백업 재확인 → 기존 모델 ACCESS EXCLUSIVE 잠금 → `recipe`→`recipe_legacy_20261022` 이름 변경 → 새 `recipe` DDL·이관 → 구조 검사 OK·검증 65/65 → COMMIT |
| 전환 후 | 재검증 65/65, ETL 리허설 변경 0, 실제 `--full` 재적재 변경 0(COMMIT), 재검증 65/65, `recipe_v2` 삭제 |
| 테스트 | 104개 전부 통과(DB 테스트 포함, Neo4j 연결 차단) |

## 4. 업무 ID·이력 보존 방법

- CSV에서 다시 만들지 않고 **기존 스키마에서 같은 DB 안 `INSERT … SELECT`로 직접 이관**했다. 모든 ID 컬럼을 명시
  복사하므로 DEFAULT(시퀀스)가 한 번도 호출되지 않는다. `rcp_id` 1,156, `ingr_id` 275, `ingr_als_id` 71,
  `rcp_ingr_stg_id` 13,080, `rcp_cat_id` 6, `rcp_raw_id` 1개 회차가 그대로다.
- `create_date/user`, `update_date/user`, 영양 검토 상태·메모, staging 상태·메모·승인 일시·승인자·파서 버전을 값 그대로 복사했다.
  검증의 `diff_*` 항목은 이 컬럼들을 포함한 **행 전체**를 양방향 `EXCEPT ALL`로 비교한다.
- `rcp_cat_rel`은 기존 `rcp.rcp_cat_id`에서 1,156건을 만들었다. 관계의 생성·수정 값은 레시피 최초 등록 값
  (`rcp.create_date/create_user_id`)이다. 원본에 없는 분류는 추가하지 않았다.
- 제거한 분류 컬럼이 부모 값과 달라 정보가 사라지는 행이 없는지 `lost_*` 5개 항목으로 확인했다(모두 0).
  식재료 분류 19건 자체는 `recipe_legacy_20261022.ingr_cat`과 백업 `ingr_cat.csv`에 남아 있다.
- 시퀀스는 `max(원본 last_value, 이관된 ID 일련번호 최댓값)`으로 맞췄다(`seq_behind_*` 0). 전환 직후
  `seq_rcp` 1171, `seq_ingr` 280, `seq_ingr_als` 76, `seq_rcp_ingr_stg` 13140이었다. 이후 DB 테스트가
  ROLLBACK 전에 소비한 번호만큼(현재 1174/281/77/13152) 증가했으며, 롤백된 번호는 재사용되지 않는다.

## 5. 자동 승인 10,611건과 최종 관계 10,428건의 차이 183건

`insert_recipe_ingredient_relations`는 승인 staging을 `(rcp_id, ingr_id)` 기준 `DISTINCT`로 한 건씩만 만든다.
한 레시피의 재료 원문에 같은 표준 식재료가 여러 구획(주재료·양념·고명 등)에 반복 등장하면 staging은 등장마다 남고
관계는 하나다. 기존 DB에서 승인 10,611행의 서로 다른 `(레시피, 식재료)` 쌍은 10,428개였다. 181개 쌍이 2회 이상
등장했고, 그중 2개 쌍은 3회 등장했다: 179×1 + 2×2 = 183. 검증 항목으로 다음을 확인했다.

- `gap_unexplained` = (승인 행 − 관계 행) − (승인 행 − 서로 다른 쌍) = **0**: 차이는 반복 등장으로만 설명된다
- `orphan_approved_staging_without_relation` = 0, `orphan_relation_without_approved_staging` = 0
- `gap_src_tgt_approved_differs` = 0: 원본·대상의 승인 매핑 다중집합이 같다

## 6. ETL 변경 요약

- `recipe.sql`·`RecipeRepository`: 단독 키 조인, `rcp_cat_rel` 등록(`ON CONFLICT DO NOTHING`), 분류 조건은
  `EXISTS`로 걸어 목록·건수 중복을 막음, 식재료 분류 SQL 제거, 정합성 검사 갱신, 목표 모델 확인 쿼리 추가
- `RecipeRegisterService`: 식재료 시드는 `ingr_seed.csv(ingr_nm, ingr_als_nms)`만 사용(`ingr_cat_seed.csv` 삭제),
  기존 레시피의 원본 분류가 등록 관계와 다르면 관계를 추가·삭제하지 않고 보고, 대상 스키마가 목표 모델이 아니면 중단,
  `--rehearse`(쓰기·검증 후 ROLLBACK)
- **CRLF/LF**: 원인은 Git `core.autocrlf=true`로 CSV가 CRLF로 체크아웃되는 것이었다(인덱스는 LF, DB는 LF).
  회차 판정은 줄바꿈 종류만 무시하고 비교하며, 정제 컬럼(레시피·단계·staging 원문)은 LF로 통일한다.
  `rcp_raw`에는 CSV 값을 그대로 저장한다. CSV 파일은 변경하지 않았다.
- 스키마 지정: `create_recipe_sql_session(schema=…)`·`--schema`·`RECIPE_DB_SCHEMA`
- Neo4j 적재 코드: `RcpRecipe{rcp_id}`, `RcpIngredient{ingr_id}`, `RCP_IN_RECIPE_CATEGORY`는 `rcp_cat_rel` 행 단위,
  식재료 분류 노드·관계 제거. 이전 모델의 그래프 제약(`rcp_recipe_composite_key` 등)이나 `RcpIngredientCategory`
  라벨이 남아 있으면 쓰기 전에 중단한다.
- 기존 모델 전용 도구(`rebuild_recipe_schema`, `reset_recipe_data`)는 `--confirm-*`을 거부하도록 막았다.

## 7. 복구 절차

| 상황 | 방법 |
|---|---|
| 전환 트랜잭션 중 실패 | 자동 ROLLBACK. 이름 변경까지 취소되어 기존 `recipe`가 그대로 남는다 |
| 전환 후 되돌리기 | `recipe_rebuild rollback-cutover --legacy-schema recipe_legacy_20261022 --confirm-rollback --confirm-db H/D` — 한 트랜잭션에서 새 `recipe`를 `recipe_failed_<시각>`으로, 보존 스키마를 `recipe`로 이름만 바꾼다(삭제 없음). 이전 커밋의 프로그램으로 함께 되돌려야 한다 |
| 보존 스키마도 손상 | 백업 폴더에서 `restore-test`와 같은 방식(기존 DDL + COPY)으로 복원. 백업 `manifest.json`의 행 md5로 결과를 확인 |

보존 스키마 `recipe_legacy_20261022`의 `fn_get_biz_id`는 이름이 `recipe`로 하드코딩되어 있으므로, 보존 상태에서는
그 스키마에 새 행을 넣지 않는다(읽기 전용 보관). 복구로 이름이 `recipe`로 돌아오면 원래대로 동작한다.

## 8. 남은 위험·후속 작업

- (완료) Neo4j는 2026-10-22 승인에 따라 초기화 후 목표 모델로 재적재했다(`docs/neo4j/neo4j_target_model_migration.md`).
- `docs/db/recipe_table_definition.md`, `recipe_erd.mmd`, `recipe_integrity_checks.sql`,
  `recipe_data_review.sql`은 기존 모델 기준 문서로 남아 있다.
- 보존 스키마 `recipe_legacy_20261022`와 백업 폴더의 삭제 시점은 사용자가 정한다(삭제 시 CASCADE 금지).
- (해결) `common/postgres_db_session.py`의 `langchain_postgres` import를 PGVector 엔진을 만드는 `get_pg_engine()` 안으로 옮겼다.
  `langchain-postgres`는 모든 버전이 `pgvector<0.4`를 요구해 프로젝트의 `pgvector>=0.5.1`과 함께 설치할 수 없고, 레시피 ETL은 이 메서드를
  쓰지 않는다. 정식 `.venv`에서 대체 모듈 없이 전체 테스트를 통과했다.
- 새 원본 회차에서 `RCP_PAT2`가 바뀐 레시피는 자동으로 관계를 바꾸지 않고 검토 목록으로만 보고된다.
