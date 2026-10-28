# 레시피 PostgreSQL 전체 재구축 사전 조사와 실행 계획

> **이력 문서.** 2026-10-22 목표 모델 전환 전의 전체 재구축 사전 조사(판단 B로 실행됨)이다. 현재 구조는 `recipe_target_schema.sql`·`recipe_table_definition.md`, 전환 기록은 `recipe_target_rebuild_runbook.md`를 따른다.

상태: **조사·계획 전용**. 2026-10-22 저장소와 PostgreSQL `recipe` 스키마를 읽기 전용으로 확인했다. DDL/DML 실행, Neo4j 변경, 기존 코드·문서 수정은 하지 않았다. 이 문서는 `ingredient_category_impact_analysis.md`, `ingredient_category_validation.sql`, `recipe_multi_category_target.sql`, `recipe_multi_category_design.md`, `recipe_multi_category_validation.sql`, `recipe_multi_category_target_validation.sql`의 결과를 출발점으로 삼는다.

## 최종 판단 — B. 일부 데이터 백업·이관 후 전체 재구축 가능

**CSV와 현행 코드만 실행해서는 현재 DB를 100% 동일하게 복원할 수 없다.** CSV와 시드·파서는 레시피 내용과 최종 식재료 매핑을 재현하지만, `rcp_id`, `ingr_id`, `ingr_als_id`, `rcp_ingr_stg_id`, 분류 ID, 수집 회차 ID는 날짜+시퀀스 발급으로 다시 만들어져 동일하다고 보장할 수 없다. 생성·수정 시각과 보류 검토 메모 같은 운영 상태도 CSV만으로는 복원되지 않는다. 현행 데이터에 수동 승인 건은 확인되지 않았지만, 이를 이유로 상태 백업을 생략하면 안 된다.

권고하는 방식은 **격리된 환경에서 새 DDL·수정된 ETL로 CSV 기반 행을 생성하되, 기존 업무 ID와 상태·매핑을 백업 스냅샷에서 명시적으로 이관하고 전후 집합을 비교하는 것**이다. 목표 구조를 그대로 생성할 DDL과 ETL은 아직 없고, 이전 `recipe_multi_category_target.sql`은 식재료 분류를 유지하므로 실행용 최종 DDL로 사용할 수 없다. 격리 재구축과 복구 연습이 통과하기 전에는 운영 스키마를 삭제하지 않는다.

## 1. 실제 입력과 현재 파이프라인

`src/data/COOKRCP01.csv`가 존재한다. 파일은 1,739,442바이트, UTF-8 BOM, **55개 헤더·1,156행**, `RCP_SEQ` 1,156개 유일값이다. 조사 시 SHA-256은 `3f58fd2f16869553248df5990b41be9828c5313a2041cb82395644edb20305d3`였다. `RCP_PAT2` 요리 분류와 `RCP_WAY2` 조리 방법은 각각 6개 값이다. `RecipeRegisterService.SOURCE_COLUMNS`의 55개 헤더와 일치하고, `rcp_raw`의 원본 필드에도 모두 대응한다. CSV에는 `rcp_raw_id`, `rcp_raw_seq`, 내부 레시피·식재료 ID, 식재료 분류·별칭, 승인 상태가 없다.

`register_recipe_csv.py.DEFAULT_CSV_PATH`는 `project_root()/src/data/COOKRCP01.csv`를 가리킨다. `project_root()`는 파일 위치에서 상위의 `.git` 또는 `.env`를 찾으므로 **기본 CSV 경로 자체는 현재 작업 디렉터리에 의존하지 않는다.** 반면 `--csv`에 상대경로를 주면 실행 디렉터리에 따라 해석되고, `python -m recipe_recommender...`의 모듈 검색에는 과제 폴더를 작업 디렉터리 또는 Python 경로에 두어야 한다. `README_recipe.md`의 과거 `C:\graph-rag` 경로는 현재 경로가 아니라 예시다.

| 순서 | 파일·구성 요소 | 입력 → 결과 | 재구축 시 판단 |
|---|---|---|---|
| 1 | `recipe_recommender/sql/001_create_recipe_schema.sql` | `recipe` 스키마만 생성 | 테이블 DDL 아님 |
| 2 | `docs/db/recipe_schema_review.sql` | 기존 7개 시퀀스·`fn_get_biz_id`·11개 테이블·제약·COMMENT | **현행 구조 전용**. 목표 DDL로 교체 필요 |
| 3 | `docs/db/recipe_schema_rebuild.sql`, `tools/rebuild_recipe_schema.py` | 기존 객체 검사 → 명시적 `DROP ... RESTRICT` → 현행 11개 테이블 재생성 | 확인 플래그가 있어도 현행 모델을 다시 만듦. 이번 목표에 사용 불가 |
| 4 | `register_recipe_csv.py`, `config.py`, `database.py` | CSV 경로·옵션·DB 세션 → 등록 Service | 기본은 dry-run, `--full`은 실제 쓰기 |
| 5 | `recipe_register_service.py`, `recipe_ingredient_parser.py` | CSV 55열 → 원본·레시피·조리 단계·재료 staging 후보; 영양 검증 | PK 및 분류 관계 변경, ID 보존 입력 경로 필요 |
| 6 | `data/ingr_cat_seed.csv`, `data/ingr_seed.csv` | 19개 식품군·275개 표준명·71개 별칭 → 마스터 | 분류 시드는 목표에서 제외. 표준명·별칭 시드는 보존 |
| 7 | `recipe_repository.py`, `recipe.sql` | 등록·조회·UPSERT, 정확 일치 자동 승인, 최종 관계 중복 제거 | 모든 복합 키·조인·충돌 조건 수정 |
| 8 | `docs/db/recipe_integrity_checks.sql`, `recipe_data_review.sql` | 현행 데이터 검증 | 목표 키에 맞춰 새 검증 필요 |
| 9 | `search_recipe.py`, `recipe_search_service.py` | 레시피·식재료 조회 CLI 및 Service | 다중 분류 결과 중복, 단독 식재료 키 반영 |
| 10 | `recipe_graph_source_repository.py`, `recipe_graph_load_service.py`, `recipe_graph_repository.py`, `load_recipe_graph.py`, `recipe_graph_*.cypher` | PostgreSQL 스냅샷 → Neo4j 노드·관계 | PostgreSQL 목표 구조와 그래프 키를 함께 개정. 이번 단계에는 미실행 |

`docs/db/recipe_data_reset.sql`·`tools/reset_recipe_data.py`는 기존 11개 테이블을 TRUNCATE하고 시퀀스를 재시작한다. 데이터 보존 기능이 없으므로 목표 재구축 경로에 넣지 않는다. `recipe_schema_migration.sql`, `recipe_schema_before_final_recreation.sql`, `recipe_import_batch_option.sql`은 과거안·대안이지 현재 실행 진입점이 아니다. 조사한 과제 Notebook에서는 별도 레시피 PostgreSQL 적재 진입점을 찾지 못했다.

현재 등록 순서는 CSV 검증 → 요리 분류·조리 방법 코드 → 식재료 사전(분류→표준명→별칭) → 원본 회차·`rcp_raw` → `rcp`·`rcp_step` → `rcp_ingr_stg` → 이름 정확 일치 자동 승인 → `rcp_ingr`다. `rcp_ingr_stg`는 `rcp_raw` 행의 자식이며, `rcp_ingr`는 승인 staging의 식재료를 레시피별로 DISTINCT 처리한다. `recipe.sql`이 모든 등록·조회 SQL을 보유한다.

## 2. CSV·시드·DB의 재현성 검증

읽기 전용으로 CSV 55개 원본 필드를 행 순번별 `rcp_raw` 1,156행과 대조했다. **그대로 비교하면 3,276개 필드 차이**가 있었다. 차이는 `RCP_PARTS_DTLS`, `MANUAL01`~`MANUAL06`, `RCP_NA_TIP`의 `CRLF` 대 `LF` 줄바꿈뿐이었다. 양쪽 줄바꿈을 LF로 정규화하면 **차이 0개**다. 이는 파일의 내용상 동일성을 뒷받침하지만, 저장된 원본 바이트까지 CSV 재적재로 똑같이 만들 수 있다는 뜻은 아니다. 현행 `resolve_batch()`는 55개 필드를 *그대로* 비교하므로 이 CSV를 기존 DB에 재실행하면 같은 회차로 인식하지 못하고 **새 원본 수집 회차를 발급할 위험**이 있다.

| 확인 항목 | 결과 | 재현 판단 |
|---|---:|---|
| 현행 `rcp_raw` 수집 회차 / 행 | 1 / 1,156 | CSV 내용 재생성 가능; 회차 ID·시각은 보존 필요 |
| `rcp_cat` / `common_code_grp` / `common_cd` | 6 / 1 / 6 | CSV의 고유 `RCP_PAT2`·`RCP_WAY2`로 값 생성 가능; 기존 분류 ID 보존 필요 |
| `rcp` / `rcp_step` | 1,156 / 6,717 | 원본·파서로 생성 가능; 기존 `rcp_id` 및 상태 대조 필요 |
| `ingr_cat` / `ingr` / `ingr_als` | 19 / 275 / 71 | 시드의 표준명·별칭 집합과 DB가 각각 정확히 일치; ID 보존 필요 |
| `rcp_ingr_stg` | 13,080 | 현재 파서 재실행 후보 13,080개, 키 누락·내용 차이 0 |
| staging `AUTO_APPROVED` / `PENDING_REVIEW` | 10,611 / 2,469 | 수동 승인·거절 0; 현재 코드·시드의 자동 승인 예상 10,611 |
| `rcp_ingr` | 10,428 | CSV+파서+시드로 재계산한 `(rcp_seq, ingr_nm)` 집합 10,428개가 현행 DB 집합과 **차이 0** |

현재 staging의 `MANUAL_APPROVED`·`REJECTED`는 각 0건이고, staging/레시피의 생성·수정 사용자 중 `system` 이외도 0건이었다. 따라서 *현재 스냅샷*에서 별도 수동 승인에 의존하는 최종 관계는 확인되지 않았다. `rcp`의 영양 상태는 `VALID` 1,071건, `REVIEW_REQUIRED` 85건이다. 보류 staging 2,469건의 원문·파싱·검토 메모는 보호 대상으로 취급한다. 현재 수치가 장래의 수동 변경 부재를 보증하지는 않는다.

### CSV 없이 `rcp_raw`만 사용할 수 있는가?

`rcp_raw`에는 55개 원본 컬럼과 행 순번이 있으므로 **원본 레시피 입력은 재구성 가능**하다. 하지만 현행 CLI는 CSV 파일을 읽도록 작성되어 있어 DB 원본을 입력으로 쓰는 어댑터가 필요하다. 또한 `rcp_raw`에는 표준 식재료 275개, 별칭 71개, 분류·식재료 업무 ID, 승인 상태·관리 이력이 없다. 원본만으로 100% 복원은 불가능하다. 현재는 CSV와 시드가 모두 있으므로 원본 텍스트의 별도 소스도 확보돼 있다.

### 보존해야 할 DB 전용 데이터

- `rcp_raw_id`와 `rcp_raw_seq` 대응, 기존 `rcp_cat_id`, `rcp_id`, `ingr_id`, `ingr_als_id`, `rcp_ingr_stg_id`. `rcp_raw_seq`는 CSV 행 순서로, 나머지 업무 ID는 `YYYYMMDD_000001` 형식의 각 시퀀스로 발급된다. 재생성 시 날짜·순서·시퀀스 소비량에 따라 업무 ID가 달라질 수 있으므로 명시적 이관이 필요하다.
- 레시피–기존 분류 `(rcp_id, rcp_cat_id)` 1,156개, 별칭–식재료 연결 71개, staging–원본·식재료 연결, 최종 `(rcp_id, ingr_id)` 10,428개와 `rcp_raw_id` 근거. 새 목표의 `rcp_cat_rel`은 기존 1,156개를 먼저 정확히 옮긴다. CSV에 없는 '중식' 등은 추가하지 않는다.
- `create_date`, `update_date`, 사용자 ID, 영양 검토 메모, staging 검토 메모·승인 시각·승인자·상태. 파서로 현재 내용을 재현할 수 있어도 **역사적 시각과 승인 이력**은 다시 생성할 수 없다.
- `common_code_grp`·`common_cd`의 실제 코드 ID/명칭, 기존 요리 분류 ID, 모든 시퀀스의 `last_value`·`is_called`과 객체 정의. 명시적 ID 복원 후에는 후속 자동 발급이 기존 키와 충돌하지 않도록 시퀀스 상태를 설계해야 한다. `CYCLE` 설정도 충돌 가능성을 별도 검토한다.

현재 비교는 원본 전체, staging 파싱 주요 필드, 최종 관계 **업무 매핑 집합**에 대한 것이다. 모든 관리 컬럼과 영양·단계의 행별 완전 동일성까지 증명한 것은 아니다. 그러므로 **전체 테이블 백업과 복원 가능성 검증**을 필수 조건으로 둔다.

## 3. 확정 목표와 코드 수정 범위

| 엔티티 | 목표와 필요한 처리 |
|---|---|
| `rcp_raw` | 기존 PK `(rcp_raw_id, rcp_raw_seq)` 유지; 원본·회차 이력 보존 |
| `rcp_cat` | 기존 `rcp_cat_id` 유지, 다중 분류 기준 컬럼·공통코드 운영 정책 확정 |
| `rcp_cat_rel` | 신규 `(rcp_id, rcp_cat_id)`; 초기 1,156개 기존 연결 복원, 분류 선두 역방향 인덱스 |
| `common_code_grp`, `common_cd` | 조리 방법과 요리 분류 기준 코드에 재사용; 기존 복합 코드 PK 유지 |
| `rcp`, `rcp_step` | 각각 `(rcp_id)`, `(rcp_id, step_no)`; `rcp_cat_id`를 레시피 본체·단계 키에서 제거 |
| `ingr` | `ingr_cat` 제거, 기존 `VARCHAR(20)`·`seq_ingr` 유지, `(ingr_id)` PK |
| `ingr_als` | 별칭 엔티티·`ingr_als_id`·나머지 컬럼 유지. **기존 PK `(ingr_cat_id, ingr_id, ingr_als_id)`를 문자 그대로 유지하는 것은 `ingr_cat_id` 제거와 모순**이므로 목표 PK는 식재료 부모의 새 PK 전체와 기존 별칭 ID를 승계한 `(ingr_id, ingr_als_id)`로 해석한다. `UNIQUE (ingr_id, ingr_als_nm)` 유지 |
| `rcp_ingr_stg` | 원본 행 기반 PK `(rcp_raw_id, rcp_raw_seq, rcp_ingr_stg_id)`·검토 기록 유지; nullable 매핑은 `ingr_id`로 변경 |
| `rcp_ingr` | `(rcp_id, ingr_id)` PK, 기존 `rcp_raw_id` 근거 유지; 식재료 선두 역방향 조회 인덱스 검토 |

`recipe_multi_category_target.sql`은 현재 `ingr_cat` 및 `ingr_cat_id` 복합 키를 유지하고 있으므로 확정 목표의 실행 DDL이 아니다. `recipe_multi_category_target_validation.sql`과 앞선 분석 문서도 새 식재료 키와 별칭 PK 정책으로 개정해야 하지만 **이번에는 기존 여섯 산출물을 수정하지 않았다.**

수정 대상은 새 통합 DDL·재구축 스크립트, `recipe.sql`의 INSERT/UPSERT/`ON CONFLICT`·JOIN·검색·검증, `RecipeRepository`·`RecipeRegisterService`·`RecipeSearchService`, `register_recipe_csv.py`의 출력·입력 정책, 관련 테스트와 문서다. `recipe_graph_source_repository.py`, `recipe_graph_load_service.py`, `recipe_graph_repository.py`, `recipe_graph_constraints.cypher`, `recipe_graph_load.cypher`, `recipe_graph_validation.cypher`, `recipe_graph_queries.cypher`도 레시피 단독 키, 식재료 단독 키, 다중 요리 분류 관계에 맞춰야 한다. 기존 그래프는 복합 키·식재료 분류 노드/관계를 사용하므로 PostgreSQL만 바꾼 상태에서 기존 Neo4j 적재 프로그램을 실행하면 안 된다.

## 4. 안전한 전체 재구축 계획

1. **범위 고정:** 대상 DB·스키마·소유 객체, 애플리케이션·Neo4j 의존, 뷰·FK·트리거·함수·시퀀스와 외부 사용처를 다시 읽기 전용으로 점검한다. 현재 카탈로그에서는 `recipe` 뷰 0, 사용자 트리거 0, `recipe` 관련 물리 FK 0이었다. 이것만으로 외부 프로그램 의존이 없다는 뜻은 아니다.
2. **복구 가능한 스냅샷:** 스키마 정의, 11개 테이블 전 행, 시퀀스 상태, 접근 권한·COMMENT 및 CSV/시드 파일의 버전·해시를 보관한다. 백업을 별도 환경에 실제 복원해 키·건수·집합을 검증한다. ID·검토 이력은 자동 생성에 맡기지 말고 스냅샷에서 이관할 계획을 확정한다.
3. **격리 검증:** 별도 테스트 DB가 우선이다. 현재 DDL과 SQL은 `recipe.`를 직접 지정하므로 단순히 `search_path`를 바꿔 테스트 스키마에 적재할 수 없다. 테스트 스키마를 쓰려면 모든 DDL·SQL·프로그램의 스키마 지정을 명시적으로 매개화해야 한다. 운영 DB의 기존 `recipe` 스키마는 유지한다.
4. **목표 코드 완성:** 식재료 분류 없는 통합 DDL, 한글 COMMENT, 필요한 PK·UNIQUE·인덱스, 논리 참조 검증을 작성한다. 재적재 ETL에는 기존 ID·상태를 스냅샷에서 매칭해 넣는 경로와 새 레시피 분류 관계 등록 경로를 추가한다. 원본 `RCP_PAT2`의 6개 분류만 초기 관계로 넣고 임의 추론은 금지한다.
5. **격리 적재 및 대조:** CSV와 시드로 원본·정제 결과를 재현하고, 보존 ID·상태를 이관한다. 전후 `rcp_seq→rcp_id`, `ingr_nm→ingr_id`, `(ingr_id, ingr_als_nm)→ingr_als_id`, 원본 행→staging ID, `(rcp_id, rcp_cat_id)`, `(rcp_id, ingr_id)` 집합을 양방향 비교한다. 1,156/275/71/13,080/10,428 같은 건수는 보조 지표로 사용한다.
6. **실패·롤백 연습:** 적재 중단, 제약 실패, 시퀀스 충돌, 조회 프로그램 오류를 별도 DB에서 재현하고 복원 시간과 절차를 확인한다. Neo4j 변경은 별도 계획으로 분리하며, PostgreSQL 전환 동안 기존 그래프 적재 작업을 중지한다.
7. **운영 전환 결정:** 위 검증이 모두 통과하고 백업 시점 이후 쓰기 변경분을 처리할 동결·동기화 계획이 있을 때만 운영 전환을 검토한다. 운영 객체를 지워야 한다면 사전 확인된 프로젝트 객체만 명시적으로 다루고 외부 의존을 다시 검사한다. `DROP SCHEMA CASCADE`는 광범위한 외부 의존 객체를 함께 제거할 수 있으므로 계획에 포함하지 않는다. 기존 `recipe_schema_rebuild.sql`도 현행 모델을 재생성하고 데이터를 보존하지 않으므로 그대로 사용하지 않는다.

## 5. 적용 전 검증과 중단 조건

- **ID 집합:** 이전/이후 내부 ID 자체와 원본 번호·표준명·별칭의 매핑이 동일해야 한다. 날짜+시퀀스의 새 발급 결과가 우연히 같다고 가정하지 않는다.
- **관계 집합:** 기존 레시피 분류 1,156개와 최종 식재료 관계 10,428개의 양방향 차이가 0이어야 한다. 다중 분류를 새로 생성하지 않는다.
- **상태·이력:** staging 13,080건의 상태·검토 메모·승인자·시각, 영양 검토 상태, 원본 수집 회차 근거를 보존한다. 수동 데이터가 이후 추가됐으면 별도 추출·검토한다.
- **구조:** 새 PK·UNIQUE 충돌 0, 고아 참조 0, 분류 누락 0, 조회·ETL·그래프 원천 쿼리의 목표 스키마 호환성을 확인한다.
- **복구:** 격리 환경에서 백업 복원과 서비스 재연결이 성공하지 않으면 운영 삭제·전환을 진행하지 않는다. 최종 전환 이후 실패 시 이전 스키마와 데이터·시퀀스·프로그램 버전을 한 세트로 되돌린다.

**현재 상태:** 원본·시드·파서로 핵심 *내용과 관계*는 재현 가능하다. 하지만 목표 DDL·ETL의 개정, 업무 ID와 상태 이관, 격리 재구축·복구 검증이 남아 있으므로 지금 바로 전체 재구축을 실행할 준비는 되지 않았다.
