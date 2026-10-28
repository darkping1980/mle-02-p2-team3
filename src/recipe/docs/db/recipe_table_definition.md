# 레시피 PostgreSQL 테이블·컬럼 정의서 (목표 모델, 11개 테이블)

DDL: `recipe_target_schema.sql` · 이관: `recipe_target_migration.sql` · 검증: `recipe_target_validation.sql` · ERD: `recipe_erd.mmd`
재구축 절차·실행 기록: `recipe_target_rebuild_runbook.md`. 2026-10-22 전환 이전 모델은 `recipe_legacy_20261022` 스키마에 보존되어 있다.

## 테이블과 키

| 테이블 | 의미 | PK | UNIQUE | 논리 부모 | 건수(2026-10-22) |
|---|---|---|---|---|---:|
| `rcp_raw` | 식약처 레시피 원본(회차별) | `(rcp_raw_id, rcp_raw_seq)` | `(rcp_raw_id, rcp_seq)` | — | 1,156 |
| `rcp_cat` | 요리 분류 | `(rcp_cat_id)` | `(rcp_cat_nm)` | — | 6 |
| `rcp_cat_rel` | 레시피·요리 분류 관계(N:M) | `(rcp_id, rcp_cat_id)` | — | `rcp`, `rcp_cat` | 1,156 |
| `common_code_grp` | 공통코드 그룹 | `(common_code_grp_id)` | — | — | 1 |
| `common_cd` | 공통코드 | `(common_code_grp_id, common_cd)` | — | `common_code_grp` | 6 |
| `rcp` | 정제 레시피 | `(rcp_id)` | `(rcp_seq)` | `common_cd`(COOK_MTHD, 비식별); `rcp_raw`(회차·원본번호, 비식별) | 1,156 |
| `rcp_step` | 레시피 조리 단계 | `(rcp_id, step_no)` | — | `rcp` | 6,717 |
| `ingr` | 표준 식재료 | `(ingr_id)` | `(ingr_nm)` | — | 275 |
| `ingr_als` | 식재료 별칭 | `(ingr_id, ingr_als_id)` | `(ingr_id, ingr_als_nm)` | `ingr` | 71 |
| `rcp_ingr_stg` | 재료 원문 파싱 및 검토 | `(rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id)` | `(rcp_raw_id, rcp_raw_seq, rcp_ingr_line_no)` | `rcp_raw`; 승인 시 `ingr` | 13,080 |
| `rcp_ingr` | 레시피별 사용 식재료(N:M) | `(rcp_id, ingr_id)` | — | `rcp`, `ingr` | 10,428 |

모든 테이블은 부모 식별자를 자식 식별자보다 앞에 두고, 마지막에 관리 컬럼 4개(`create_date`, `create_user_id`, `update_date`, `update_user_id`)를 둔다.
관계 테이블(`rcp_cat_rel`, `rcp_ingr`)은 별도 ID 없이 두 부모 PK 전체를 승계한 복합 PK다. 물리 FK는 0개이며 논리 참조는 ETL 사전 검증과
`recipe_integrity_checks.sql`, `recipe_data_review.sql` [G1]에서 검사한다. 모든 테이블·컬럼에 한글 COMMENT가 있다.

PK·UNIQUE 외 보조 인덱스 3개(PK 선두에 없는 역방향 탐색):

| 인덱스 | 컬럼 | 용도 |
|---|---|---|
| `ix_rcp_cat_rel_cat_key` | `rcp_cat_rel (rcp_cat_id, rcp_id)` | 요리 분류별 레시피 조회 |
| `ix_rcp_ingr_ingr_key` | `rcp_ingr (ingr_id, rcp_id)` | 식재료별 레시피 조회 |
| `ix_rcp_ingr_stg_ingr_key` | `rcp_ingr_stg (ingr_id)` | 표준 식재료 기준 staging 조회 |

이전 모델 대비 제거: `ingr_cat` 테이블과 `seq_ingr_cat`, 모든 `ingr_cat_id` 컬럼, `rcp`·`rcp_step`·`rcp_ingr`의 `rcp_cat_id` 컬럼, `rcp`의 `uq_rcp_rcp_id`.

## 주요 컬럼

| 테이블 | 컬럼 | 형식 | NULL | 설명 |
|---|---|---|---|---|
| `rcp` | `rcp_id` | `varchar(20)` | NOT NULL | 레시피 ID(PK, `fn_get_biz_id('rcp')`) |
| | `rcp_seq` | `text` | NOT NULL | 식약처 원본 레시피 번호(UNIQUE) |
| | `rcp_raw_id` | `varchar(20)` | NOT NULL | 최종 반영 원본 수집 회차 |
| | `rcp_nm` | `text` | NOT NULL | 레시피명 |
| | `cook_mthd_cd` | `varchar(20)` | NOT NULL | 조리 방법 코드(COOK_MTHD 6자리 코드, 예: `000004`). 명칭은 `common_cd_nm` |
| | `rcp_serving_weight_value`, `rcp_energy_kcal`, `rcp_carbs_g`, `rcp_protein_g`, `rcp_fat_g`, `rcp_sodium_mg` | `numeric(10,2)` | NULL | 영양정보(원본 값 변환, 보정 없음) |
| | `rcp_nutrition_status` | `varchar(20)` | NOT NULL | `UNCHECKED`/`VALID`/`REVIEW_REQUIRED`/`REVIEWED_OK` |
| | `rcp_nutrition_review_note`, `rcp_hash_tag`, `rcp_image_url`, `rcp_image_large_url`, `rcp_sodium_reduction_tip_txt` | `text` | NULL | 검토 메모·해시태그·이미지·나트륨 저감 팁 |
| `rcp_cat` | `rcp_cat_id` / `rcp_cat_nm` | `varchar(20)` / `text` | NOT NULL | 요리 분류 ID / 분류명(원본 `RCP_PAT2` 또는 별도 승인 분류) |
| `rcp_cat_rel` | `rcp_id`, `rcp_cat_id` | `varchar(20)` | NOT NULL | 레시피 ↔ 요리 분류. 레시피당 1개 이상(현재 데이터는 모두 1개) |
| `rcp_step` | `step_no` | `smallint` | NOT NULL | 조리 단계 번호(원본 MANUAL 번호, 1~20) |
| | `rcp_step_instruction_txt` / `rcp_step_image_url` | `text` | NOT NULL / NULL | 단계 설명 / 이미지 |
| `ingr` | `ingr_id` / `ingr_nm` | `varchar(20)` / `text` | NOT NULL | 표준 식재료 ID(PK) / 표준명(UNIQUE) |
| `ingr_als` | `ingr_als_id` / `ingr_als_nm` | `varchar(20)` / `text` | NOT NULL | 별칭 ID(기존 발급값 유지) / 별칭명 |
| `rcp_ingr_stg` | `ingr_id` | `varchar(20)` | NULL | 매핑된 표준 식재료(승인 상태면 NOT NULL, CHECK) |
| | `rcp_ingr_raw_txt`, `rcp_ingr_parsed_nm`, `rcp_ingr_qty`, `rcp_ingr_unit_nm`, `rcp_ingr_section_txt` | `text` / `numeric(12,3)` | — | 원문·후보명·수량·단위·구획 |
| | `rcp_ingr_status` | `varchar(20)` | NOT NULL | `PENDING_REVIEW`/`AUTO_APPROVED`/`MANUAL_APPROVED`/`REJECTED` |
| | `rcp_ingr_review_note`, `rcp_ingr_parser_version`, `rcp_ingr_approved_date`, `rcp_ingr_approved_user_id` | — | NULL | 검토 메모·파서 버전·승인 이력 |
| `rcp_ingr` | `rcp_raw_id` | `varchar(20)` | NOT NULL | 관계 생성 근거 원본 수집 회차 |

`rcp_raw`는 원본 CSV 55개 컬럼(`rcp_seq`, `rcp_nm`, `rcp_way2`, `rcp_pat2`, `info_*`, `hash_tag`, `att_file_no_*`, `rcp_parts_dtls`,
`manual01`~`manual20`, `manual_img01`~`manual_img20`, `rcp_na_tip`)을 `text`로 값 그대로 보존한다. 전체 컬럼과 COMMENT는 DDL을 따른다.

## 식별자

| 컬럼 | 형식 | 발급 | 의미 |
|---|---|---|---|
| `rcp_raw_id` | `VARCHAR(20)` `YYYYMMDD_000001` | `fn_get_biz_id('import_batch')`, 회차당 1회 | 원본 수집 회차. `rcp.rcp_raw_id`, `rcp_ingr.rcp_raw_id`도 같은 의미 |
| `rcp_raw_seq` | `VARCHAR(6)` `000001` | Python, CSV 행 순서 | 회차 내 원본 행 순번. 회차마다 000001부터, 999,999 초과는 오류 |
| `rcp_seq` | `TEXT` | 식약처 원본 | 원본 레시피 번호. 일반 속성(내부 ID 아님) |
| `rcp_cat_id` | `VARCHAR(20)` | `fn_get_biz_id('rcp_cat')` DEFAULT | 요리 분류 ID |
| `rcp_id` | `VARCHAR(20)` | `fn_get_biz_id('rcp')` DEFAULT | 내부 레시피 ID. 재실행 시 `rcp_seq`로 찾아 재사용 |
| `ingr_id` / `ingr_als_id` | `VARCHAR(20)` | `fn_get_biz_id('ingr' / 'ingr_als')` DEFAULT | 표준 식재료·별칭 ID |
| `rcp_ingr_stg_id` | `VARCHAR(20)` | `fn_get_biz_id('rcp_ingr_stg')` DEFAULT | 재료 staging 행 ID |
| `rcp_ingr_line_no` | `SMALLINT` | 파서 | 원문 재료 등장 순번(일반 속성) |

시퀀스 6개(`seq_rcp_cat`, `seq_rcp`, `seq_ingr`, `seq_ingr_als`, `seq_import_batch`, `seq_rcp_ingr_stg`)는 모두 `MAXVALUE 999999 CYCLE CACHE 1`이다.
`fn_get_biz_id(p_tbl_nm)`는 같은 스키마의 `seq_<p_tbl_nm>`을 `to_regclass()`로 찾아 Asia/Seoul 날짜를 붙인다(`search_path` 비의존).
서로 다른 시퀀스이므로 다른 테이블의 ID가 같은 문자열일 수 있다(예: `rcp_cat_id`와 `rcp_id` 모두 `20261022_000001`).
2026-10-22 이관에서 기존 업무 ID를 모두 그대로 옮겼고, 시퀀스는 기존 발급 위치 이상으로 맞췄다.

## 조인 경로

- 조리 방법: `rcp.cook_mthd_cd = common_cd.common_cd AND common_cd.common_code_grp_id = 'COOK_MTHD'`
- 요리 분류: `rcp.rcp_id = rcp_cat_rel.rcp_id` → `rcp_cat_rel.rcp_cat_id = rcp_cat.rcp_cat_id` (분류 조건 검색은 `EXISTS`로 걸어 레시피 중복을 막는다)
- 원본 ↔ 정제: `rcp_raw.rcp_raw_id = rcp.rcp_raw_id AND rcp_raw.rcp_seq = rcp.rcp_seq`
- staging → 레시피: `rcp_ingr_stg (rcp_raw_id, rcp_raw_seq)` → `rcp_raw` → `rcp_seq` → `rcp.rcp_id`
- 레시피별 사용 식재료: `rcp_ingr.rcp_id = rcp.rcp_id`, `rcp_ingr.ingr_id = ingr.ingr_id`
- 별칭: `ingr_als.ingr_id = ingr.ingr_id`

## 공통코드 등록 규칙

- 코드(`common_cd`)와 명칭(`common_cd_nm`)은 분리한다. 코드값에 명칭을 넣지 않는다.
- 코드는 6자리 숫자 문자열이다(`000001` 형식). 컬럼은 `varchar(20)` 그대로이며 숫자형으로 바꾸지 않는다.
- 한 번 부여한 코드는 재번호화·개명하지 않는다. 새 조리 방법은 다음 번호(`000007`~)를 코드표에 추가해 등록한다.
- 원본 명칭이 코드표에 없으면 적재기는 코드를 임의로 만들지 않고 검증 오류로 중단한다.
- 적재기는 DB 코드가 코드표와 다른 명칭이거나, 6자리 형식이 아니거나, 한 명칭이 두 코드에 걸리면 쓰기 전에 중단한다.
- 정합성 검사 `invalid_cook_method_code`(6자리 형식 위반)와 `rcp_without_cook_method`(코드 미존재)는 0이어야 한다.
- 레시피 조회의 조리 방법 조건은 코드(`000004`)와 명칭(`찌기`)을 모두 받는다.

`COOK_MTHD` 확정 코드(2026-10-23):

| `common_cd` | `common_cd_nm` | 레시피 수 |
|---|---|---:|
| `000001` | 굽기 | 259 |
| `000002` | 끓이기 | 326 |
| `000003` | 볶기 | 108 |
| `000004` | 찌기 | 82 |
| `000005` | 튀기기 | 71 |
| `000006` | 기타 | 310 |

## 적재 정책 요약

- 요리 종류 마스터(`rcp_cat`)는 CSV 실제 고유값으로 적재기가 등록한다. 공통코드(`common_code_grp`/`common_cd`)의 `COOK_MTHD`는
  확정 코드표 `recipe_recommender/data/cook_mthd_cd_seed.csv`로 등록하고, `RCP_WAY2`(한글 명칭)를 `common_cd_nm`으로 찾아
  `rcp.cook_mthd_cd`에 코드를 저장한다. 아래 "공통코드 등록 규칙"을 따른다.
- `rcp_cat_rel`은 원본 `RCP_PAT2` 분류만 관계로 만든다. 기존 레시피의 원본 분류가 등록 관계와 다르면 관계를 바꾸지 않고 검토 목록으로 보고한다.
- 식재료 마스터는 `recipe_recommender/data/ingr_seed.csv`(표준 식재료 275개, 별칭 71개)를 등록한다. 별칭은 동의어(계란→달걀, 쇠고기→소고기 등)와
  띄어쓰기·어순 변형만 포함하고, 비슷한 이름(새우/칵테일새우/건새우, 두부/연두부, 마늘/다진 마늘)은 별개 식재료로 둔다.
- staging 행은 파싱 결과가 OK/PARTIAL이고 후보명이 표준명 또는 별칭과 정확히 일치하며 대상이 하나일 때만 `AUTO_APPROVED` 된다. 나머지는 `PENDING_REVIEW`로 남는다.
- `rcp_ingr`는 승인 staging만으로 만들고 같은 레시피·식재료는 1건으로 합친다(현재 승인 10,611행 → 관계 10,428건, 반복 등장 183행).
- 재실행 시 기존 키를 먼저 조회해 새 행만 INSERT하므로 업무 ID를 다시 발급하지 않는다. 원본 회차 비교는 줄바꿈 종류(CRLF/LF)를 무시한다.
- 적재기는 대상 스키마가 목표 모델(`rcp_cat_rel` 있음, `ingr_cat` 없음)이 아니면 중단한다. `--schema`/`RECIPE_DB_SCHEMA`로 대상 스키마를 지정한다.
