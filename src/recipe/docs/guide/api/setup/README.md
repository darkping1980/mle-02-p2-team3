# recipe_recommender.setup Package Summary

[API 전체 목차](../README.md) · [파일 인덱스](../../02_file_structure.md)

CSV 등록과 PostgreSQL 원천 검증, Neo4j 초기 적재를 담는 실제 하위 패키지. 모듈 6개를 다룬다.

## Module Summary

| 모듈 상세 | 소스 | 역할 |
| --- | --- | --- |
| [load_recipe_graph](load_recipe_graph.md) | [load_recipe_graph.py](../../../../recipe_recommender/setup/load_recipe_graph.py) | PostgreSQL 스냅샷과 Neo4j를 대조하는 CLI 진입점. |
| [recipe_graph_load_service](recipe_graph_load_service.md) | [recipe_graph_load_service.py](../../../../recipe_recommender/setup/recipe_graph_load_service.py) | PostgreSQL 목표 모델을 검증하고 Neo4j 레시피 그래프에 적재·대조한다. |
| [recipe_graph_source_repository](recipe_graph_source_repository.md) | [recipe_graph_source_repository.py](../../../../recipe_recommender/setup/recipe_graph_source_repository.py) | 그래프 적재에 필요한 PostgreSQL 목표 모델을 한 시점의 스냅샷으로 읽는다. |
| [recipe_ingredient_parser](recipe_ingredient_parser.md) | [recipe_ingredient_parser.py](../../../../recipe_recommender/setup/recipe_ingredient_parser.py) | ``RCP_PARTS_DTLS`` 재료 원문을 staging 행 후보로 나누는 보수적 파서. |
| [recipe_register_service](recipe_register_service.md) | [recipe_register_service.py](../../../../recipe_recommender/setup/recipe_register_service.py) | 식약처 ``COOKRCP01.csv`` 를 recipe 스키마에 적재하는 Service 모듈. |
| [register_recipe_csv](register_recipe_csv.md) | [register_recipe_csv.py](../../../../recipe_recommender/setup/register_recipe_csv.py) | 식약처 레시피 CSV 등록 CLI 진입점. |

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [PreparedGraph](recipe_graph_load_service.md#preparedgraph) | dataclass DTO | 검증된 원천과 적재 단계별 입력 행을 묶는 불변 필드 DTO. |
| [RecipeGraphLoadService](recipe_graph_load_service.md#recipegraphloadservice) | 클래스 | 원천 검증, 적재 순서, 결과 비교를 조정하는 Service. |
| [GraphSourceSnapshot](recipe_graph_source_repository.md#graphsourcesnapshot) | dataclass DTO | 한 읽기 트랜잭션의 원천 테이블·카탈로그 조회값을 묶는 DTO. |
| [RecipeGraphSourceRepository](recipe_graph_source_repository.md#recipegraphsourcerepository) | 클래스 | PostgreSQL SELECT 전용 DAO. 데이터와 스키마를 변경하지 않는다. |
| [ParsedIngredient](recipe_ingredient_parser.md#parsedingredient) | dataclass DTO | 원문 재료 한 항목의 파싱 후보; 등록 Service가 staging 행에 사용한다. |
| [RecipeIngredientParser](recipe_ingredient_parser.md#recipeingredientparser) | 클래스 | 재료 원문 파서. DB와 무관한 순수 업무 규칙이며 ``RecipeRegisterService`` 가 주입받아 사용한다. |
| [RecipeLoadError](recipe_register_service.md#recipeloaderror) | 예외 클래스 | 적재를 중단해야 하는 데이터·구조 오류. 메시지에 원인 목록을 담는다. |
| [RehearsalRollback](recipe_register_service.md#rehearsalrollback) | 예외 클래스 | 리허설 적재 마지막에 던져 전체 트랜잭션을 ROLLBACK시키는 표식 예외. |
| [IngredientSeed](recipe_register_service.md#ingredientseed) | dataclass DTO | 검토된 식재료 사전. ingredients: [(표준명, (별칭...))]. |
| [RecipeLoadPlan](recipe_register_service.md#recipeloadplan) | dataclass DTO | CSV에서 만든 DB 등록 후보와 검증 결과. DB에는 아직 아무것도 쓰지 않은 상태다. |
| [RecipeLoadResult](recipe_register_service.md#recipeloadresult) | dataclass DTO | 적재 실행 결과. dry-run이면 DB 관련 값은 비어 있다. |
| [RecipeRegisterService](recipe_register_service.md#reciperegisterservice) | 클래스 | 레시피 CSV 적재 파이프라인을 실행하는 Service. |

## Data Model Summary

TypedDict, Pydantic 모델, dataclass 및 결과 DTO를 클래스 상세의 Field Summary에서 확인한다.

| 데이터 모델 | 종류 |
| --- | --- |
| [PreparedGraph](recipe_graph_load_service.md#preparedgraph) | dataclass DTO |
| [GraphSourceSnapshot](recipe_graph_source_repository.md#graphsourcesnapshot) | dataclass DTO |
| [ParsedIngredient](recipe_ingredient_parser.md#parsedingredient) | dataclass DTO |
| [IngredientSeed](recipe_register_service.md#ingredientseed) | dataclass DTO |
| [RecipeLoadPlan](recipe_register_service.md#recipeloadplan) | dataclass DTO |
| [RecipeLoadResult](recipe_register_service.md#recipeloadresult) | dataclass DTO |

## Function Summary

| 모듈 함수 | 설명 |
| --- | --- |
| [load_recipe_graph.main](load_recipe_graph.md#function-main) | CLI 인자를 해석해 Source/Graph Repository를 Service에 주입하고 보고서를 반환한다. |
| [recipe_graph_load_service._key](recipe_graph_load_service.md#function-_key) | 행에서 지정한 컬럼 값을 순서대로 뽑아 비교용 복합 키를 만든다. |
| [recipe_graph_load_service._unique_keys](recipe_graph_load_service.md#function-_unique_keys) | 적재 전 원천 키의 빈 값·타입·중복을 검사하고 키 집합을 반환한다. |
| [recipe_graph_source_repository.recipe_graph_row](recipe_graph_source_repository.md#function-recipe_graph_row) | Neo4j 드라이버가 받도록 PostgreSQL Decimal을 float로 바꾼 레시피 dict를 만든다. |
| [recipe_ingredient_parser.parse_quantity](recipe_ingredient_parser.md#function-parse_quantity) | '75', '0.5', '1/2', '½', '1½' 를 Decimal(소수 3자리)로 바꾼다. 해석할 수 없으면 None. |
| [recipe_ingredient_parser.split_items](recipe_ingredient_parser.md#function-split_items) | 괄호 밖의 쉼표로만 나눈다. '참치(캔, 30g)' 안의 쉼표는 유지한다. |
| [recipe_ingredient_parser._split_header](recipe_ingredient_parser.md#function-_split_header) | 줄 앞의 구획 머리글을 분리한다. Returns ``(section, serving_note, rest)``. |
| [recipe_ingredient_parser._choose_amount](recipe_ingredient_parser.md#function-_choose_amount) | 분량 후보 문자열 목록에서 대표 분량을 고른다. 미터법 단위를 우선한다. |
| [recipe_ingredient_parser._status_for_name](recipe_ingredient_parser.md#function-_status_for_name) | 후보 재료명의 불확실성을 확인해 검토 상태와 사유를 조정한다. |
| [recipe_ingredient_parser.parse_item](recipe_ingredient_parser.md#function-parse_item) | 재료 항목 하나를 ``(name, qty, unit, status, notes)`` 로 분리한다. |
| [recipe_ingredient_parser._split_inline_sections](recipe_ingredient_parser.md#function-_split_inline_sections) | 줄 나머지를 ``(바뀐 구획 또는 None, 재료 항목 또는 None)`` 목록으로 나눈다. |
| [recipe_ingredient_parser._split_item_headers](recipe_ingredient_parser.md#function-_split_item_headers) | 한 재료 조각 안의 구획 머리글을 분리한다. |
| [recipe_ingredient_parser.parse_ingredient_text](recipe_ingredient_parser.md#function-parse_ingredient_text) | 재료 원문 전체를 등장 순서대로 ``ParsedIngredient`` 목록으로 만든다. |
| [recipe_register_service.normalize_newlines](recipe_register_service.md#function-normalize_newlines) | CRLF·CR을 LF로 바꾼다. 원본 저장값은 바꾸지 않고 비교·정제 값에만 쓴다. |
| [recipe_register_service._null_if_empty](recipe_register_service.md#function-_null_if_empty) | CSV에는 NULL 개념이 없으므로 빈 문자열만 NULL로 저장한다. 그 외 값은 공백 포함 원형 그대로. |
| [recipe_register_service._clean_text](recipe_register_service.md#function-_clean_text) | 정제 컬럼용: 줄바꿈을 LF로 맞추고 앞뒤 공백만 제거하며 비면 NULL. |
| [recipe_register_service.raw_seq_for](recipe_register_service.md#function-raw_seq_for) | CSV 행 위치(1부터)를 회차 내 원본 행 순번 문자열로 만든다. 999,999 초과는 오류. |
| [recipe_register_service.strip_step_prefix](recipe_register_service.md#function-strip_step_prefix) | 조리 설명 앞의 '1. ' 같은 번호가 단계 번호와 같을 때만 제거한다. 나머지 원문은 유지한다. |
| [recipe_register_service.evaluate_nutrition](recipe_register_service.md#function-evaluate_nutrition) | 영양정보를 Decimal로 변환하고 자동 검증 상태를 정한다. |
| [recipe_register_service.load_ingredient_seed](recipe_register_service.md#function-load_ingredient_seed) | 식재료 표준명·별칭 사전을 읽고 모순을 검사한다. |
| [recipe_register_service.load_cook_method_seed](recipe_register_service.md#function-load_cook_method_seed) | 조리 방법 확정 코드표를 읽는다. Returns ``{common_cd: common_cd_nm}`` (파일 순서). |
| [recipe_register_service.resolve_cook_method_map](recipe_register_service.md#function-resolve_cook_method_map) | DB의 COOK_MTHD 코드와 확정 코드표를 합쳐 ``{common_cd_nm: common_cd}`` 를 만든다. |
| [register_recipe_csv.parse_args](register_recipe_csv.md#function-parse_args) | CSV 경로와 적재·리허설 옵션을 CLI에서 읽는다. |
| [register_recipe_csv._print_list](register_recipe_csv.md#function-_print_list) | 검토 항목의 제목과 지정한 개수만큼의 예시를 출력한다. |
| [register_recipe_csv.print_report](register_recipe_csv.md#function-print_report) | 검증 계획과 등록 결과의 건수·오류를 콘솔에 출력한다. |
| [register_recipe_csv.main](register_recipe_csv.md#function-main) | CSV 적재 Service를 실행하고 결과에 따른 종료 코드를 반환한다. |

## 관련 가이드

- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
