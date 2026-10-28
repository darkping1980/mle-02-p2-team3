# PostgreSQL 등록·조회와 그래프 적재 상세

[메인](../README.md) · [실행 흐름](../04_execution_flow.md) · [Neo4j Repository](04_neo4j_repository.md)

## 1. CSV → PostgreSQL 등록

진입점 [register_recipe_csv.main(argv=None) -> int](../../../recipe_recommender/setup/register_recipe_csv.py)은 인자 파싱, 환경 로드, 세션·Service 생성, 보고·종료 코드 변환을 맡는다. 인자가 없으면 `parse_args`가 dry-run으로 바꾼다. `--limit N`/`--full`은 쓰기 범위이며 `--dry-run`을 함께 줄 수 있다. `--rehearse`는 쓰기 후 rollback하므로 순수 읽기 전용은 아니다. 기본 CSV 경로는 **Git 루트**의 `src/data/COOKRCP01.csv`다. Service 오류는 코드 1, 기타 DB 오류는 2, 집계 위반은 3, 정상은 0이다. 세션 pool은 `finally`에서 닫는다.

| 정의 위치·함수 | 매개변수 → 반환 | 처리 순서·호출·예외 |
| --- | --- | --- |
| [`RecipeRegisterService.__init__(sql_session,user_id)`](../../../recipe_recommender/setup/recipe_register_service.py) | 세션·사용자 ID → 객체 | `RecipeRepository`와 `RecipeIngredientParser` 생성. |
| [`read_csv(csv_path)`](../../../recipe_recommender/setup/recipe_register_service.py) | `str|Path` → `list[dict[str,str]]` | `utf-8-sig`, 헤더/행 길이 검증, `RCP_RAW_SEQ` 추가. 구조 오류 `RecipeLoadError`. |
| [`validate_rows(rows,expected_count)`](../../../recipe_recommender/setup/recipe_register_service.py) | 행 목록 → 차단 오류 목록 | 전체 건수·키·필수 필드 확인. `--limit` 적용 전 호출. |
| [`build_plan(...)`](../../../recipe_recommender/setup/recipe_register_service.py) | CSV 행·마스터/키 map → `RecipeLoadPlan` | 원본·정제 레시피·분류 관계·조리 단계·재료 staging 후보 생성. `RecipeIngredientParser.parse` 호출. 쓰기 전에 자리표시 ID로, 트랜잭션 안에서는 실제 ID로 재호출. |
| [`register(csv_path,limit,dry_run,seed,rehearse)`](../../../recipe_recommender/setup/recipe_register_service.py) | 경로·옵션 → `RecipeLoadResult` | 목표 스키마 확인 → 전체 CSV/seed/코드 검사 → 계획. dry-run 즉시 반환. 쓰기는 `sql_session.transaction()`에서 아래 메서드와 사후 집계. 오류는 상위 전파. |
| [`register_reference_masters(source_rows,...)`](../../../recipe_recommender/setup/recipe_register_service.py) | 원본 행 → 등록 건수 dict | 요리 분류·확정 조리 코드 등록. Repository의 마스터 SQL. |
| [`register_ingredient_master(seed)`](../../../recipe_recommender/setup/recipe_register_service.py) | `IngredientSeed` → `(건수 dict, 충돌 list)` | 표준 식재료 후 별칭 등록. 충돌 별칭은 건너뛰고 보고. |
| [`resolve_batch(source_rows)`](../../../recipe_recommender/setup/recipe_register_service.py) | 원본 행 → `(rcp_raw_id,batch_mode)` | 최근 회차 원본과 비교해 재사용 또는 새 ID 발급. |
| [`write_plan(plan,rcp_raw_id)`](../../../recipe_recommender/setup/recipe_register_service.py) | 계획·회차 → 건수 dict | 활성 트랜잭션 필수. `RecipeRepository`를 통해 원본→레시피→분류 관계→단계→staging→정확 일치 승인→`rcp_ingr`; `_verify_written`로 건수 확인. |

실제 SQL은 [RecipeRepository](../../../recipe_recommender/recipe_repository.py)가 `PostgresDbSession.select_list/select_one/execute/execute_many('recipe.<name>')`로 [recipe.sql](../../../recipe_recommender/recipe.sql)의 `-- name:` 블록에 위임한다. `create_recipe_sql_session()`은 [database.py](../../../recipe_recommender/database.py)에 있고, 기본 이외 스키마면 SQL 한정자를 바꾼 임시 mapper 사본을 등록한다. [sql_schema.py](../../../recipe_recommender/sql_schema.py)가 스키마명을 검증한다. `PostgresDbSession.transaction()`은 정상 종료 commit, 예외 rollback이다. 운영용 [수동 DDL](../../../recipe_recommender/sql/001_create_recipe_schema.sql)은 이 mapper로 자동 실행되지 않는다.

`RecipeLoadPlan`은 계획 후보와 검토 목록, `RecipeLoadResult`는 계획·실제 쓰기 건수·정합성·rollback 여부를 담는다. 재료 원문은 [RecipeIngredientParser.parse](../../../recipe_recommender/setup/recipe_ingredient_parser.py)에서 `ParsedIngredient`로 분해된다. 정확히 확인된 표준명/별칭만 staging 자동 승인 SQL을 통과한다. 기존 관계·단계를 무조건 삭제하는 경로가 아니다.

## 2. PostgreSQL 조회 CLI

진입점 [search_recipe.main(argv=None) -> int](../../../recipe_recommender/search_recipe.py)은 `--rcp-seq|--rcp-id|--name|--category|--cook-method|--ingredient` 중 하나를 받는다. `create_recipe_sql_session()` 후 [`RecipeSearchService`](../../../recipe_recommender/recipe_search_service.py)를 만든다.

| Service 메서드 | 인자 → 반환 | Repository/SQL과 분기 |
| --- | --- | --- |
| `get_recipe_detail(rcp_seq=None,rcp_id=None)` | 둘 중 하나 → `{recipe,steps,ingredients,unmatchedIngredients}` 또는 `None` | `find_recipe_detail` → 찾은 `rcpId`로 세 목록 SELECT. |
| `search_recipes(name,category,cook_method,page,page_size)` | 조건·페이지 → `{totalCount,page,pageSize,items}` | 조건·페이지 검증 → `count_recipes`, `list_recipes`. |
| `find_ingredient(name)` | 표준명/별칭 → `{ingredient,aliases}` 또는 `None` | `find_ingredient_by_name`; 서로 다른 식재료 ID가 여럿이면 `RecipeSearchError`. |
| `search_recipes_by_ingredient(name,page,page_size)` | 이름·페이지 → 식재료/별칭과 count/items 또는 `None` | `find_ingredient` → `count_recipes_by_ingredient`, `list_recipes_by_ingredient`. |

`RecipeSearchError`만 CLI에서 코드 1로 처리한다. 상세/식재료가 없으면 3, 그 밖 정상은 0. `finally`는 pool을 닫는다. SQL 반환 키는 `rcpId`, `totalCount` 같은 camelCase다. 조회 SQL은 [recipe.sql](../../../recipe_recommender/recipe.sql) 하단에 있다. 이 CLI는 Neo4j를 호출하지 않는다.

## 3. PostgreSQL 스냅샷 → Neo4j

진입점 [load_recipe_graph.main(argv=None) -> int](../../../recipe_recommender/setup/load_recipe_graph.py)은 기본 사전 점검, `--verify-only` 검증, `--apply` 적재다. 인자 범위는 `batch_size` 1~1000. `RecipeGraphRepository`를 소유하고 `finally`에서 닫는다.

| 정의 위치·함수 | 인자 → 반환 | 처리·예외·부작용 |
| --- | --- | --- |
| [`RecipeGraphSourceRepository.read_snapshot()`](../../../recipe_recommender/setup/recipe_graph_source_repository.py) | 없음 → `GraphSourceSnapshot` | PostgreSQL `REPEATABLE READ READ ONLY` 트랜잭션에서 노드·관계·스키마 근거를 SELECT. `finally`에서 rollback/manager.close. |
| [`RecipeGraphLoadService.prepare()`](../../../recipe_recommender/setup/recipe_graph_load_service.py) | 없음 → `PreparedGraph` | 스냅샷 PK·필수 필드·부모 참조·별칭 충돌 검증, 6개 `stages` 구성. `recipe_graph_row`가 `Decimal` 열량을 float로 변환. `_step_rows`가 `rcp_step`의 키 중복·부모 누락·번호 1~20·빈 설명을 거부하고 빈 이미지 URL만 `None`으로 바꾼다(원본 번호 공백 허용). |
| [`preflight_graph(prepared)`](../../../recipe_recommender/setup/recipe_graph_load_service.py) | 준비 객체 → inspection dict | `graph.inspect/project_rows/project_counts`; 예상 밖 라벨·관계·기존 키·스키마 충돌을 거부. 읽기 경로. |
| [`apply(prepared,batch_size)`](../../../recipe_recommender/setup/recipe_graph_load_service.py) | 준비 객체·크기 → 완료 건수·검증 dict | 재점검, 적재 쿼리 EXPLAIN, 스키마 생성, `STAGES` 순서로 `write_batch`, `verify`. 배치마다 commit. 실패는 완료 배치를 포함한 `RuntimeError`. |
| [`verify(prepared)`](../../../recipe_recommender/setup/recipe_graph_load_service.py) | 준비 객체 → 건수 dict | 키 집합·건수·분류/미연결 레시피·`step_link_errors`(부모가 정확히 하나가 아닌 단계) 확인. `verify_query_examples`는 대표 레시피(원본 28번)의 `recipe_steps` 결과가 PostgreSQL `rcp_step`과 순서·설명·URL까지 같은지도 비교한다. `verify_examples`, `verify_query_examples`, `verify_search_scenarios`는 CLI가 별도 호출. |

조리 단계는 `STAGES` 마지막의 `load_recipe_steps`로 적재한다. 기존 `rcp`·`ingr`·`rcp_cat` 노드와 두 관계는 같은 키로 `MERGE`되어 건수가 바뀌지 않고, `rcp_step` 노드와 `RCP_HAS_STEP` 관계만 늘어난다(2026-10-24 원천 기준 각 6,717). 사전 점검은 단계가 없는 기존 그래프를 원천의 부분집합으로 통과시키므로 초기화 없이 추가 적재할 수 있다. 반대로 `--verify-only`는 단계 적재 전에는 `rcp_step` 건수 불일치로 실패한다.

`--apply`의 `main`은 `apply`를 두 번 호출해 두 번째에도 검증 건수가 같은지 비교한다. 이는 동일 스냅샷에 대한 `MERGE` 재실행 검사다. `RecipeGraphRepository.write_batch`의 부모 수 검사와 쓰기는 **한 배치의 트랜잭션**이며, 전체 적재를 하나로 묶지 않는다. 중간 실패 시 앞 배치의 데이터가 남을 수 있다. 적재 노드·관계와 Cypher는 [Neo4j 상세](04_neo4j_repository.md)에 있다.

## 주변 파일과 검증 범위

[tools/recipe_rebuild.py](../../../recipe_recommender/tools/recipe_rebuild.py), [reset_recipe_data.py](../../../recipe_recommender/tools/reset_recipe_data.py), [rebuild_recipe_schema.py](../../../recipe_recommender/tools/rebuild_recipe_schema.py)는 별도 운영 작업이다. [연결 점검 도구](../../../recipe_recommender/tools/check_neo4j_connection.py)도 주 실행 경로와 별개다. [레시피 테스트](../../../recipe_recommender/tests/)와 [공통 세션 테스트](../../../common/tests/)에는 가짜 의존성 테스트뿐 아니라 DB 연동/쓰기 후 rollback을 확인하는 테스트도 있다. 이 문서 작성에서는 테스트·DB·API를 실행하지 않았다.

설계 배경은 [PostgreSQL 목표 모델](../../db/recipe_target_rebuild_runbook.md), [Neo4j 모델](../../neo4j/neo4j_model_design.md), [기존 소스 가이드](../../study/recipe_source_guide_ko.md)를 참고할 수 있다. 실제 호출 관계는 위 소스 링크를 우선한다.
