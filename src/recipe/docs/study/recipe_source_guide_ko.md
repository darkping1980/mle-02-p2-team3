# 레시피 프로젝트 소스 읽기 안내

이 문서는 **현재 코드의 실행 경로**를 설명한다. 아래 명령은 `common/`과 `recipe_recommender/`가 나란히 있는 과제 폴더에서 PowerShell로 실행한다. 저장소 최상위의 오래된 scaffold 안내보다 실제 CLI와 메서드를 기준으로 한다.

## 1. 폴더와 진입점

| 경로 | 역할 |
| --- | --- |
| `recipe_recommender/main.py` | 초기 scaffold 확인 메시지만 출력한다. 등록·조회·적재의 통합 진입점이 아니다. |
| `recipe_recommender/setup/register_recipe_csv.py` | PostgreSQL CSV 등록 CLI. `parse_args()` → `main()` → `RecipeRegisterService.register()` |
| `search_recipe.py` | PostgreSQL 읽기 전용 조회 CLI. `main()` → `RecipeSearchService` |
| `recipe_recommender/setup/load_recipe_graph.py` | PostgreSQL 스냅샷으로 Neo4j를 검사하거나 적재하는 CLI. 일반 검색 CLI는 아니다. |
| `setup/recipe_register_service.py`, `setup/recipe_ingredient_parser.py` | 등록 순서·검증·트랜잭션 및 재료 원문 분해 |
| `recipe_search_service.py`, `recipe_repository.py`, `recipe.sql` | SQL 조회·등록 업무 조건, DAO, 명명 SQL mapper |
| `setup/recipe_graph_source_repository.py` | PostgreSQL을 `REPEATABLE READ READ ONLY`로 읽어 `GraphSourceSnapshot` 생성 |
| `setup/recipe_graph_load_service.py`, `recipe_graph_repository.py` | 그래프 입력 검증·배치 순서·결과 대조 및 공용 Cypher DAO |
| `name_normalization.py` | 추천과 그래프 적재가 공유하는 `normalize_name()` |
| `recipe_graph_constraints.cypher`, `recipe_graph_load.cypher`, `recipe_graph_validation.cypher`, `recipe_graph_queries.cypher` | 제약·적재·검증·탐색 명명 Cypher |
| `config.py`, `database.py`, `sql_schema.py`, `neo4j_connection.py`, `__init__.py` | 경로·환경변수·PostgreSQL 세션·스키마 선택·Neo4j 연결·패키지 import 준비 |
| `data/ingr_seed.csv`, `data/cook_mthd_cd_seed.csv` | 검토된 표준 식재료/별칭, 확정 조리방법 코드 |
| `sql/001_create_recipe_schema.sql`, `docs/db/` | 초기 namespace 및 목표 모델/변경 이력/검증 자료. 현재 등록 CLI의 mapper가 아니다. |
| `tools/` | 연결 점검과 스키마 재구축·초기화 등 별도 운영 도구. 이 학습 명령에서는 재구축·초기화를 실행하지 않는다. |
| `tests/`, `common/tests/` | 단위·통합 테스트. 일부 통합 테스트는 DB에 임시 INSERT 후 ROLLBACK한다. |
| `common/database_manager.py`, `common/postgres_db_session.py`, `common/neo4j_db_session.py`, `common/query_session.py`, `common/query_logger.py` | 연결 풀, 명명 쿼리 실행, 트랜잭션, 공통 계약·로그. `common/storage_manager.py`, `common/document_reader.py`는 레시피 세 경로의 직접 호출 대상이 아니다. |

`docs/db/recipe_target_schema.sql`이 목표 PostgreSQL 모델이고, `docs/neo4j/`는 그래프 설계·검증 기록이다. `README_recipe.md` 앞부분의 “scaffold” 및 일부 깨진 예시는 현재 구현 상태와 다르므로 실행 명령은 아래와 CLI의 `--help`를 따른다.

## 2. PostgreSQL CSV 등록: 실제 호출 경로

```text
python -m recipe_recommender.setup.register_recipe_csv [옵션]
 → register_recipe_csv.main() / parse_args()
 → database.create_recipe_sql_session() / RecipeRegisterService(sql_session)
 → RecipeRegisterService.register(csv_path, limit, dry_run, rehearse)
 → RecipeRepository(sql_session)의 메서드
 → PostgresDbSession.select_one/select_list/execute/execute_many("recipe.<statement>")
 → recipe.sql의 -- name: <statement> → psycopg / PostgreSQL
 → RecipeLoadResult → register_recipe_csv.print_report() → 종료 코드
```

CSV 기본 경로는 `register_recipe_csv.DEFAULT_CSV_PATH`: `project_root()/src/data/COOKRCP01.csv`다. `config.project_root()`는 `Path(__file__)`에서 올라가 `.git` 또는 `.env`를 찾으므로 터미널의 현재 디렉터리와 독립적이다. `read_csv()`는 UTF-8 BOM, 헤더 55개·중복·누락·추가·컬럼 수를 검사하고 전체 행에 6자리 `RCP_RAW_SEQ`를 만든다. `validate_rows()`는 전체 1,156행, `RCP_SEQ` 공란·중복, 필수 명칭을 검사한다. **`--limit`도 전체 CSV를 먼저 검증한 뒤 앞 N행만 계획에 쓴다.**

`load_ingredient_seed()`는 표준명·별칭 중복을, `load_cook_method_seed()`는 6자리 코드와 명칭 중복을 검사한다. `resolve_cook_method_map()`은 DB의 `COOK_MTHD`와 확정 코드표가 충돌하는지 확인한다. 원본 `RCP_WAY2` 명칭을 코드표의 코드로 바꿔 `rcp.cook_mthd_cd`에 저장하며 임의 코드를 만들지 않는다. `build_plan()`은 `rcp_raw`, `rcp`, `rcp_cat_rel`, `rcp_step`, `rcp_ingr_stg` 후보와 검토 목록을 메모리의 `RecipeLoadPlan`에 모은다. `evaluate_nutrition()`은 `Decimal` 변환과 검토 상태를 정하고 원본 이상값을 덮어쓰지 않는다. `RecipeIngredientParser.parse()`는 `RCP_PARTS_DTLS`를 등장 순서별 후보로 분해한다.

| 단계와 Service 메서드 | Repository 메서드 → `recipe.sql` 이름 | 결과 |
| --- | --- | --- |
| 목표 모델 검사 `check_target_model()` | `find_schema_model()` → `find_schema_model` | `rcp_cat_rel` 존재·옛 `ingr_cat` 부재 검사 |
| 마스터 `register_reference_masters()` | `list_recipe_category_map`, `insert_recipe_categories` → `list_recipe_categories`, `insert_recipe_category`; `upsert_cook_method_codes` → `upsert_common_code_group`, `upsert_common_code` | `rcp_cat`, `common_code_grp`, `common_cd` 등록 건수 |
| 사전 `register_ingredient_master()` | `list_ingredient_map`, `insert_ingredients`, `list_ingredient_alias_keys`, `insert_ingredient_aliases` → `list_ingredients`, `insert_ingredient`, `list_ingredient_alias_keys`, `insert_ingredient_alias` | `ingr`, `ingr_als` 신규 수와 충돌 목록 |
| 회차 `resolve_batch()` | `find_latest_raw_batch`, `list_raw_rows_by_batch`, 필요시 `find_next_rcp_raw_id` | 기존/신규 `rcp_raw_id`와 회차 상태 |
| 본문 `write_plan()` | `insert_recipe_raws`, `insert_recipes`, `update_recipes`, `insert_recipe_category_relations`, `upsert_recipe_steps` → 대응 `insert_recipe_raw`, `insert_recipe`, `update_recipe`, `insert_recipe_category_relation`, `upsert_recipe_step` | 새 원본·레시피·분류관계·단계 건수 |
| 재료 `write_plan()` | `insert_recipe_ingredient_stagings`, `update_staging_verified_matches`, `insert_recipe_ingredient_relations` → 같은 이름의 SQL | staging, 자동 승인, 최종 `rcp_ingr` 건수 |
| 검증 `_verify_written()` 및 `register()` | `count_batch_rows`, `count_recipe_tables`, `count_integrity_violations` | 기대 건수·정합성 위반 수 |

쓰기 순서는 `rcp_cat`/공통코드 → `ingr`/`ingr_als` → `rcp_raw` → `rcp` → `rcp_cat_rel` → `rcp_step` → `rcp_ingr_stg` → 자동 승인 → `rcp_ingr`다. `recipe.sql.update_staging_verified_matches`는 파싱 상태가 OK/PARTIAL이고 **표준명 또는 별칭과 정확히 일치하며 한 식재료만 가리킬 때** 승인한다. 유사어는 승인하지 않는다. `insert_recipe_ingredient_relations`는 승인 staging을 원본 행·같은 회차의 레시피에 연결하고 `(rcp_id, ingr_id)`를 DISTINCT로 합친다. 따라서 staging 등장 건수와 관계 건수는 다를 수 있다.

트랜잭션 경계는 `register()`의 `with self.sql_session.transaction():`이다. `common.PostgresDbSession.transaction()`이 연결 하나를 빌려 정상 종료 시 `commit()`, 예외 시 `rollback()`하고 `finally`로 활성 연결을 지운다. `--dry-run`은 이 블록 전에 반환하여 SELECT만 수행한다. `--rehearse`는 블록 안에서 `RehearsalRollback`을 던져 전체를 되돌리지만 **PostgreSQL 시퀀스 소비는 롤백되지 않을 수 있으므로 순수 읽기 전용이 아니다.** 재실행은 최신 회차의 저장 원문 비교, 기존 키 조회, SQL의 `ON CONFLICT`와 변경 시에만 UPDATE로 중복을 막는다. 새 회차에서는 실제 변경이 필요할 수 있다.

## 3. PostgreSQL 조회: 실제 호출 경로

```text
python -m recipe_recommender.search_recipe --rcp-seq 28
 → search_recipe.main() → RecipeSearchService.get_recipe_detail()
 → RecipeRepository.find_recipe_detail() → recipe.sql.find_recipe_detail
 → rcp_id로 list_recipe_steps / list_recipe_ingredients / list_recipe_unmatched_stagings
 → 각각 recipe.sql의 동명 SELECT → {recipe, steps, ingredients, unmatchedIngredients}
 → search_recipe.print_detail()
```

| CLI 조건 | Service → Repository → `recipe.sql` | 반환 |
| --- | --- | --- |
| `--rcp-seq` 또는 `--rcp-id` | `get_recipe_detail` → `find_recipe_detail`, `list_recipe_steps`, `list_recipe_ingredients`, `list_recipe_unmatched_stagings` → 동명 SELECT | 상세 dict 또는 `None` |
| `--name`, `--category`, `--cook-method`, 보조 `--and-category`, `--and-cook-method` | `search_recipes` → `count_recipes`, `list_recipes` → 동명 SELECT | `{totalCount,page,pageSize,items}` |
| `--ingredient` | `search_recipes_by_ingredient` → `find_ingredient` → `find_ingredient_by_name`, `list_ingredient_aliases`; 이어 `count_recipes_by_ingredient`, `list_recipes_by_ingredient` → 동명 SELECT | 식재료·별칭·레시피 페이지 또는 `None` |

`list_recipes`는 레시피명에 대소문자 무시 부분 일치, 분류명에 `EXISTS`, 조리방법에 코드 **또는 코드명**을 적용한다. 분류 `EXISTS`는 다중 분류 레시피의 목록 중복을 피한다. 식재료명/별칭은 정확히 일치해야 하며 여러 표준 식재료에 걸리면 Service가 오류를 낸다. `_paging()`은 1부터 시작하는 page를 `LIMIT`/`OFFSET`으로 바꾸고 page size를 1~100으로 제한한다. 목록과 건수는 별도 SELECT이므로 동시 갱신 중에는 한 시점 스냅샷을 보장하는 구현은 아니다.

## 4. Neo4j 적재와 검증

```text
python -m recipe_recommender.setup.load_recipe_graph --verify-only
 → load_recipe_graph.main() → RecipeGraphLoadService.prepare()
 → RecipeGraphSourceRepository.read_snapshot() → PostgreSQL SELECT → GraphSourceSnapshot
 → RecipeGraphLoadService.preflight_graph()/verify()/verify_examples()/verify_query_examples()/verify_search_scenarios()
 → RecipeGraphRepository.inspect()/project_rows()/query_example()
 → recipe_graph_validation.cypher / recipe_graph_queries.cypher → 검증 JSON

--apply 추가 경로:
 → RecipeGraphLoadService.apply() → RecipeGraphRepository.create_schema()/write_batch()
 → recipe_graph_constraints.cypher / recipe_graph_load.cypher → Neo4j
 → verify() → 두 번째 apply() → 조회 예제 검증 JSON
```

`read_snapshot()`은 `rcp_cat`, `ingr`, `ingr_als`, `rcp`, `rcp_cat_rel`, `rcp_ingr`, 원본 참조·상태 및 스키마 메타데이터를 한 PostgreSQL 읽기 트랜잭션에서 가져온다. `prepare()`는 PK, 타입, 공통코드, 원본 참조, 부모 키, 중복, 이름/별칭 충돌을 검사한다. `Decimal` 열량은 Neo4j 드라이버 입력을 위해 `float`로 변환한다. `STAGES` 순서는 분류 노드 → 식재료 노드 → 레시피 노드 → 분류 관계 → 사용 관계다.

| PostgreSQL | Neo4j | 의미 |
| --- | --- | --- |
| `rcp(rcp_id)` | `(:rcp {rcp_id, rcp_seq, rcp_nm, cook_mthd_cd, ...})` | 레시피 노드. `rcp_seq`도 유일성 제약 |
| `ingr(ingr_id)` + `ingr_als` | `(:ingr {ingr_id, ingr_nm, alias_names, ...})` | 표준 식재료와 검색용 별칭 배열 |
| `rcp_cat(rcp_cat_id)` | `(:rcp_cat {rcp_cat_id, rcp_cat_nm})` | 요리 분류 노드 |
| `rcp_cat_rel(rcp_id,rcp_cat_id)` | `(rcp)-[:RCP_IN_RECIPE_CATEGORY]->(rcp_cat)` | 레시피 다중 분류 |
| `rcp_ingr(rcp_id,ingr_id)` | `(rcp)-[:RCP_USES]->(ingr)` | 승인된 식재료 관계 |

`rcp_step`, 미승인 `rcp_ingr_stg`, 식재료 분류 노드는 그래프에 적재하지 않는다. `recipe_graph_constraints.cypher`는 키 유일성과 이름 검색 인덱스를 만들고, `recipe_graph_load.cypher`는 키로 `MERGE`해 재실행 중복을 피한다. 관계 배치 직전 부모 매칭 건수를 확인한다. `preflight_graph()`는 낯선 라벨/관계/옛 제약과 PostgreSQL에 없는 키를 거부한다. `verify()`는 키 집합과 건수, 분류 누락, 식재료 미연결 레시피 수를 확인한다. `--apply`는 같은 스냅샷을 두 번 적재해 멱등성을 검사한다. **Neo4j 전체 적재는 단일 트랜잭션이 아니다.** `write_batch()`별로 확정되므로 중간 실패 시 이미 확정된 배치가 남을 수 있다.

## 5. 그래프 탐색의 구현 단계

`recipe_graph_queries.cypher`의 각 `// name:`은 `Neo4jDbSession`이 등록하는 statement ID다. Python에서는 `RecipeGraphRepository.query_example(name, parameters)`가 `recipe_graph_queries.<name>`을 호출한다. 아래 질의는 **Cypher로 구현**되었고, `load_recipe_graph.py --verify-only`의 검증 경로에서 Python이 실제 호출한다. 개별 검색어를 받는 Neo4j 사용자 CLI는 없다.

| 명명 Cypher | 그래프 경로/기능 | Python 호출 위치 |
| --- | --- | --- |
| `find_recipe_by_name`, `recipe_ingredients` | 이름으로 ID 선택, `rcp → ingr` 조회 | `verify_query_examples()` |
| `ingredient_name_candidates`, `recipes_by_ingredient_term` | 표준명·별칭 후보, 식재료로 레시피 검색 | `verify_query_examples()`, `verify_search_scenarios()` |
| `recipes_using_ingredient` | 선택한 식재료를 쓰는 다른 레시피, ID 제외 조건 | `verify_query_examples()` |
| `similar_recipes` | `rcp → ingr ← rcp`의 공통 재료, Jaccard. 두 관계를 지나는 탐색 | `verify_query_examples()` |
| `recipes_with_all_ingredients` | 입력한 모든 식재료 조건 만족 | `verify_search_scenarios()` |
| `pantry_recommendations` | 보유 재료와 부족한 재료 수로 추천 정렬 | 두 검증 메서드 |
| `recipes_in_category`, `category_and_ingredient` | 분류, 분류+재료 조건 | 각각 `verify_search_scenarios()`, `verify_query_examples()` |
| `graphrag_context` | 레시피의 분류·재료·방법을 구조화한 dict | `verify_query_examples()` |

`rcp → ingr ← 다른 rcp → rcp_cat`처럼 세 관계를 따라가는 경로는 모델상 가능하지만 **전용 3홉 명명 질의/CLI는 현재 없다.** `category_and_ingredient`는 한 레시피의 분류 관계와 재료 관계를 함께 검사한다. `graphrag_context`는 LLM에 전달할 수 있는 **근거 추출 쿼리**만 구현한다. 자연어 파싱, LLM 호출, 응답 생성, LangGraph 연결은 구현되지 않았다. `load_recipe_graph.py`의 기본 인자 없음은 사전 점검만, `--verify-only`는 실제 그래프와 예제 쿼리까지 읽기 검증, `--apply`는 쓰기다.

## 6. VS Code 터미널 실행 예제

먼저 PowerShell에서 다음 두 줄을 실행한다. `$task`를 현재 과제 폴더의 실제 경로로 정하고 `$py`는 저장소 가상환경 Python을 사용한다.

```powershell
$task = 'C:\graph-rag\src\graph_rag\2_graphrag\과제_공공데이터로-그래프-만들기_금요일까지'
Set-Location $task
$py = 'C:\graph-rag\.venv\Scripts\python.exe'
```

저장소 `.env` 또는 프로세스 환경에 PostgreSQL `DB_URL`, Neo4j `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`가 필요하다. 선택 항목은 `RECIPE_DB_SCHEMA`(기본 `recipe`), `NEO4J_DATABASE`, `NEO4J_TRUSTED_CA_FILE`이다. 실제 비밀값을 터미널 출력이나 문서에 적지 않는다. 아래 조회/등록 CLI의 `--schema`가 환경변수보다 우선한다. 그래프 적재 CLI에는 `--schema` 옵션이 없고 원천 Repository가 환경변수를 사용한다.

### 읽기 전용

```powershell
& $py -m recipe_recommender.setup.register_recipe_csv --dry-run --show 5
& $py -m recipe_recommender.search_recipe --rcp-seq 28
& $py -m recipe_recommender.search_recipe --name '양배추롤' --page 1 --page-size 10
& $py -m recipe_recommender.search_recipe --ingredient '계란'
& $py -m recipe_recommender.search_recipe --cook-method 000004
& $py -m recipe_recommender.search_recipe --category '반찬' --and-cook-method '찌기'
& $py -m recipe_recommender.setup.load_recipe_graph --verify-only
```

첫 명령은 전체 CSV를 검사해 후보·검토 수와 현재 테이블 건수를 보여 주며 DB를 변경하지 않는다. 상세는 레시피·단계·승인 식재료·미연결 원문, 검색은 `totalCount`와 페이지 행을 출력한다. `계란`은 사전의 별칭이며 정확히 매칭되는 표준 식재료를 거친다. `000004`는 코드 **문자열**이며 앞의 0을 유지한다. `--verify-only`는 PostgreSQL 스냅샷과 Neo4j 키·건수·대표 질의의 JSON 보고서를 출력한다. 현재 그래프가 원천과 다르면 오류로 끝날 수 있다.

Neo4j Browser에서 직접 실행할 대표 **읽기 Cypher**는 다음과 같다. 이는 `recipes_by_ingredient_term`과 같은 경로이며 `계란` 별칭을 해석한다.

```cypher
MATCH (i:ingr)
WHERE i.ingr_nm_norm = '계란' OR '계란' IN coalesce(i.alias_names_norm, [])
MATCH (r:rcp)-[:RCP_USES]->(i)
RETURN i.ingr_nm AS ingredient, r.rcp_id AS rcp_id, r.rcp_nm AS rcp_nm
ORDER BY r.rcp_nm, r.rcp_id;
```

다른 질의는 `recipe_graph_queries.cypher`의 해당 `// name:` 아래 블록을 Browser에 복사하고 `$rcp_id`, `$term_norm`, `$terms_norm` 등 파라미터에 실제 값을 지정해 실행한다. 명명 쿼리 파일 자체는 Python mapper 입력이며 전체 파일을 한 문장으로 실행하는 스크립트가 아니다.

### DB를 변경하는 명령: 이 학습 작업에서는 실행하지 않음

```powershell
& $py -m recipe_recommender.setup.register_recipe_csv --limit 10
& $py -m recipe_recommender.setup.register_recipe_csv --full
& $py -m recipe_recommender.setup.load_recipe_graph --apply --batch-size 500
```

`--limit N`은 앞 N행 적재, `--full`은 전체 적재다. 등록은 한 PostgreSQL 트랜잭션에서 COMMIT 또는 ROLLBACK한다. `--apply`는 Neo4j 제약·노드·관계를 배치별로 기록한다. `--rehearse`는 최종 ROLLBACK하지만 시퀀스 소비 가능성이 있어 읽기 전용 예제로 분류하지 않는다.

## 7. Java 개발자를 위한 Python 읽기 포인트

| Python 코드 | Java에 가까운 비교와 차이 |
| --- | --- |
| `python -m recipe_recommender.search_recipe` / `if __name__ == "__main__"` | 모듈을 패키지로 실행한 경우만 `main()`을 호출한다. import 시에는 함수·클래스 정의가 로드되지만 하단 실행 분기는 건너뛴다. Java `public static void main`과 진입 역할은 비슷하다. |
| `argparse.ArgumentParser`, `parse_args(argv)` | CLI 문자열을 파싱해 `Namespace` 속성으로 넘긴다. `argv=None`이면 실제 프로세스 인자를 쓴다. `--name`은 `args.name`, `dest`는 속성명을 바꾼다. |
| `from .recipe_repository import ...`, `__init__.py` | `.`는 현재 패키지 기준 상대 import다. `__init__.py`는 패키지 초기화 파일이며 import 과정에서 실행될 수 있다. 일반 파일 직접 실행보다 `-m`이 상대 import에 맞다. |
| `Path(__file__).resolve().parent` | 실행 중인 **소스 파일**의 절대 경로 기준이다. `Path.cwd()`(현재 터미널 위치)와 다르다. `/`는 Path 객체의 경로 결합 연산자다. |
| `class`, `__init__`, `self` | 생성자·인스턴스 참조와 비슷하다. Service 생성자에서 Repository 객체를 만들고 같은 세션을 전달하므로 DB 연결/트랜잭션을 공유한다. Java DI 프레임워크의 자동 주입은 아니다. |
| `str | None`, `list[dict]`, `tuple[int,int]` | 선택값과 컬렉션 **타입 힌트**다. 일반적으로 런타임 검증을 자동 수행하지 않는다. `None`은 Java의 `null`에 가깝다. |
| `@dataclass`, `field(default_factory=list)`, `@property` | 데이터 객체의 생성자 등을 자동 생성한다. `default_factory`는 인스턴스마다 새 가변 리스트를 만들고, `@property`는 메서드를 읽기 속성처럼 노출한다. `frozen=True`는 필드 재할당을 막지만 내부 리스트까지 깊게 불변화하지 않는다. |
| `dict`, `list`, `tuple`, `set` | 각각 Map, List, 고정 구조의 순서형 값, 중복 없는 집합에 가깝다. `RecipeLoadPlan`은 dict 목록을 들고, `STAGES`는 tuple, 중복 키 검사는 set을 쓴다. |
| `{key: value for ...}`, `[x for ...]`, `(x for ...)` | dict/list comprehension, generator expression이다. `list_recipe_key_map()`은 dict를 만들고 `SOURCE_COLUMNS`의 `*(name for ...)`는 단계 컬럼들을 tuple 안에 펼친다. generator는 순회할 때 값을 낸다. |
| `*`, `**` | `register(..., *, limit=...)`의 단독 `*`는 이후 인자를 이름으로만 받게 한다. `{**row, **extra}`는 dict 내용을 펼쳐 결합하고, `*aliases`는 iterable을 펼친다. `_key(row, *columns)`의 `*columns`는 여러 위치 인자를 tuple로 받는다. `**kwargs`를 억지로 쓰는 경로는 없다. |
| `try/except/finally`, `with session.transaction()` | 예외 처리/항상 실행되는 정리와 컨텍스트 매니저다. Java `try-with-resources`와 유사하지만 `with` 진입·종료 구현이 COMMIT/ROLLBACK까지 결정한다. `RehearsalRollback`도 예외를 이용해 ROLLBACK을 요구한다. |
| `Repository`/mapper | Java Service → DAO → MyBatis XML/JDBC에 가깝다. 여기서는 `recipe.sql`의 `-- name:`과 Cypher의 `// name:`을 세션이 등록해 문자열 ID로 실행한다. Python의 dict 결과와 DB row 이름 변환은 `PostgresDbSession`이 담당한다. |

`common.PostgresDbSession`의 `register_mappers()`/`_query()`는 `recipe.find_recipe_detail`을 SQL로 해석한다. `Neo4jDbSession`도 `recipe_graph_queries.similar_recipes`처럼 파일명·명명 블록을 해석한다. 두 Repository를 구분해서 읽으면 SQL 조회 구현과 그래프 조회 구현을 혼동하지 않는다.

## 8. 확인된 한계와 잠재 문제

- `main.py`는 현재 구현된 세 CLI를 묶지 않는 scaffold다.
- Neo4j의 사용자 검색 CLI, 전용 3홉 질의, 자연어·LLM 응답 생성은 현재 없다. GraphRAG 컨텍스트 Cypher는 검증 경로에서만 사용된다.
- `RecipeRegisterService.resolve_batch()`는 최신 회차에 **저장된 행이 모두** 현재 CSV와 같은지 검사한다. 저장 회차가 일부 행만 포함할 때, 그 밖의 CSV 행이 바뀌어도 같은 회차로 판단될 가능성이 있다. 현행 재실행 정책의 경계로 검토가 필요하다.
- `recipe_graph_queries.recipes_using_ingredient`는 `LIMIT 30`인데 `verify_query_examples()`는 PostgreSQL 전체 사용 건수와 반환 길이를 비교한다. 해당 식재료의 사용 레시피가 30건을 넘으면 검증이 실패할 수 있다.
- `--rehearse`와 DB 통합 테스트의 ROLLBACK은 데이터 행을 되돌려도 시퀀스 값을 되돌리지 않는다. 테스트 실행 전 개별 테스트의 DB 호출·시퀀스 사용 여부를 확인해야 한다.

## 9. 가장 빠른 학습 순서

1. `register_recipe_csv.py`의 `parse_args()`와 `main()`, 이어 `recipe_register_service.py`의 `register()`를 읽어 dry-run과 트랜잭션 경계를 잡는다.
2. `read_csv()` → `validate_rows()` → `build_plan()` → `recipe_ingredient_parser.py`를 따라 CSV 한 행이 어떤 후보로 바뀌는지 본다.
3. `register_reference_masters()` → `register_ingredient_master()` → `resolve_batch()` → `write_plan()`을 읽고 각 Repository 호출 문자열을 `recipe.sql`의 `-- name:`에서 찾는다.
4. `common/postgres_db_session.py`의 `transaction()`, `select_one()`, `execute_many()`를 확인해 COMMIT/ROLLBACK과 mapper 실행 방식을 연결한다.
5. `search_recipe.py` → `RecipeSearchService` → `RecipeRepository` → `recipe.sql` 순으로 상세·검색·식재료 별칭 조회를 추적한다.
6. `load_recipe_graph.py` → `RecipeGraphLoadService.prepare()/apply()/verify()` → 두 그래프 Repository → Cypher 파일을 읽는다. `STAGES`와 `rcp_ingr`/`rcp_cat_rel` 매핑을 먼저 본다.
7. 마지막으로 `recipe_graph_queries.cypher`의 한 질의를 Neo4j Browser에서 읽기 실행하고 `verify_query_examples()`의 Python 호출과 비교한다.
