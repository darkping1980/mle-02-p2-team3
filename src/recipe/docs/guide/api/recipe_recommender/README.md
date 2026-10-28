# recipe_recommender Package Summary

[API 전체 목차](../README.md) · [파일 인덱스](../../02_file_structure.md)

추천, PostgreSQL 조회, Repository와 연결 설정을 담는 실제 Python 패키지. 모듈 13개를 다룬다.

## Module Summary

| 모듈 상세 | 소스 | 역할 |
| --- | --- | --- |
| [config](config.md) | [config.py](../../../../recipe_recommender/config.py) | 과제 경로와 환경변수 로딩을 준비하는 공통 설정 도우미. |
| [graph_question_service](graph_question_service.md) | [graph_question_service.py](../../../../recipe_recommender/graph_question_service.py) | 그래프 관계 탐색 Service — 과제 질문 Q1~Q5를 고정 Named Cypher로 답한다 (Neo4j 읽기 전용, LLM 없음). |
| [database](database.md) | [database.py](../../../../recipe_recommender/database.py) | 레시피 프로젝트의 PostgreSQL 연결과 SQL mapper 경로를 구성한다. |
| [main](main.md) | [main.py](../../../../recipe_recommender/main.py) | 현재는 scaffold 준비 문구만 출력하는 진입점이다. 검색 Service로 위임하지 않는다. |
| [name_normalization](name_normalization.md) | [name_normalization.py](../../../../recipe_recommender/name_normalization.py) | 적재와 추천 Service가 공유하는 식재료명 비교 규칙. |
| [neo4j_connection](neo4j_connection.md) | [neo4j_connection.py](../../../../recipe_recommender/neo4j_connection.py) | Neo4j 드라이버 생성 — TLS 인증서 검증을 유지하면서 신뢰할 CA 번들을 명시한다. |
| [pantry_graphrag](pantry_graphrag.md) | [pantry_graphrag.py](../../../../recipe_recommender/pantry_graphrag.py) | 냉장고 재료 추천 GraphRAG — LangGraph 흐름: 입력 해석 → Neo4j 조회 → 근거 기반 답변. |
| [pantry_recommend_service](pantry_recommend_service.md) | [pantry_recommend_service.py](../../../../recipe_recommender/pantry_recommend_service.py) | 냉장고 재료 기반 레시피 추천 Service (Neo4j 읽기 전용, LLM 없음). |
| [recipe_graph_repository](recipe_graph_repository.md) | [recipe_graph_repository.py](../../../../recipe_recommender/recipe_graph_repository.py) | Neo4j mapper를 호출하는 그래프 DAO. 업무 검증은 적재 Service가 담당한다. |
| [recipe_repository](recipe_repository.md) | [recipe_repository.py](../../../../recipe_recommender/recipe_repository.py) | 레시피(recipe 스키마) 등록·조회 공용 Repository 모듈. |
| [recipe_search_service](recipe_search_service.md) | [recipe_search_service.py](../../../../recipe_recommender/recipe_search_service.py) | 레시피 조회 Service 모듈 (PostgreSQL 기반 MVP). |
| [search_recipe](search_recipe.md) | [search_recipe.py](../../../../recipe_recommender/search_recipe.py) | 레시피 조회 CLI 진입점 (읽기 전용). |
| [sql_schema](sql_schema.md) | [sql_schema.py](../../../../recipe_recommender/sql_schema.py) | 레시피 SQL의 대상 스키마 지정 도우미. |

## Class Summary

| 클래스 | 종류 | 설명 |
| --- | --- | --- |
| [IngredientTerms](pantry_graphrag.md#ingredientterms) | Pydantic BaseModel | 입력 해석 LLM의 구조화 출력; Pydantic이 재료 목록의 형태를 검증한다. |
| [RecipeReason](pantry_graphrag.md#recipereason) | Pydantic BaseModel | 레시피 ID와 해당 레시피의 LLM 추천 이유 한 건을 검증한다. |
| [PantryAnswer](pantry_graphrag.md#pantryanswer) | Pydantic BaseModel | 설명 LLM의 구조화 출력; ``validate_answer``가 DB 근거와 다시 대조한다. |
| [PantryState](pantry_graphrag.md#pantrystate) | TypedDict / LangGraph State | LangGraph 노드가 공유하는 상태의 키와 값 형식. |
| [PantryGraphRAG](pantry_graphrag.md#pantrygraphrag) | 클래스 | 입력 해석, Neo4j 추천 조회, 근거 설명을 LangGraph로 연결한다. |
| [GraphQuestion](graph_question_service.md#graphquestion) | dataclass DTO | 화면에 보여 줄 과제 질문 한 개의 정의(질문·hop·관계 경로·실행 Cypher). |
| [GraphAnswer](graph_question_service.md#graphanswer) | dataclass DTO | 질문 한 번의 Neo4j 조회 결과. ``rows`` 는 Cypher 반환 행 그대로(Q1만 중복 제거). |
| [GraphQuestionService](graph_question_service.md#graphquestionservice) | 클래스 | 과제 질문 Q1~Q5를 허용된 읽기 전용 Named Cypher로 실행한다. |
| [RecipeStep](pantry_recommend_service.md#recipestep) | dataclass DTO | 식약처 원본 조리 과정 한 단계(MANUAL01~20)의 Neo4j 조회값. |
| [TermResolution](pantry_recommend_service.md#termresolution) | dataclass DTO | 입력어 하나의 해석 결과. ``matches`` 가 비면 DB에 없는 재료, 2개 이상이면 모호한 별칭. |
| [Recommendation](pantry_recommend_service.md#recommendation) | dataclass DTO | 추천 한 건의 Neo4j 조회 근거; ``recommend``가 만들고 화면과 LLM 검증이 읽는다. |
| [PantryResult](pantry_recommend_service.md#pantryresult) | dataclass DTO | 입력 해석과 추천 목록을 묶어 LangGraph의 ``result``에 담는 DTO. |
| [PantryRecommendService](pantry_recommend_service.md#pantryrecommendservice) | 클래스 | 보유 식재료 → 추천 레시피·사용/부족 재료·근거를 Neo4j에서 조회한다. |
| [RecipeGraphRepository](recipe_graph_repository.md#recipegraphrepository) | 클래스 | Cypher 파일의 ``namespace.statement``를 Neo4jDbSession에 전달하는 DAO. |
| [RecipeRepository](recipe_repository.md#reciperepository) | 클래스 | 레시피 원본·마스터·정제·staging·관계의 등록·조회 SQL을 호출하는 Repository(DAO). |
| [RecipeSearchError](recipe_search_service.md#recipesearcherror) | 예외 클래스 | 조회 조건이 잘못된 경우의 오류. |
| [RecipeSearchService](recipe_search_service.md#recipesearchservice) | 클래스 | 레시피·조리 단계·사용 식재료·표준 식재료를 조회하는 Service. |

## Data Model Summary

TypedDict, Pydantic 모델, dataclass 및 결과 DTO를 클래스 상세의 Field Summary에서 확인한다.

| 데이터 모델 | 종류 |
| --- | --- |
| [IngredientTerms](pantry_graphrag.md#ingredientterms) | Pydantic BaseModel |
| [RecipeReason](pantry_graphrag.md#recipereason) | Pydantic BaseModel |
| [PantryAnswer](pantry_graphrag.md#pantryanswer) | Pydantic BaseModel |
| [PantryState](pantry_graphrag.md#pantrystate) | TypedDict / LangGraph State |
| [TermResolution](pantry_recommend_service.md#termresolution) | dataclass DTO |
| [Recommendation](pantry_recommend_service.md#recommendation) | dataclass DTO |
| [PantryResult](pantry_recommend_service.md#pantryresult) | dataclass DTO |

## Function Summary

| 모듈 함수 | 설명 |
| --- | --- |
| [config.project_root](config.md#function-project_root) | 현재 작업 디렉터리와 무관하게 .git 또는 .env가 있는 저장소 루트를 찾는다. |
| [config.prepare_imports](config.md#function-prepare_imports) | 과제 폴더를 import 경로에 넣어 같은 수준의 ``common``을 찾게 한다. |
| [config.prepare_common_imports](config.md#function-prepare_common_imports) | ``common`` import를 준비하고 pgvector의 이전 import 경로를 보완한다. |
| [config.load_project_environment](config.md#function-load_project_environment) | 저장소의 .env를 읽되 이미 설정된 프로세스 환경변수는 덮어쓰지 않는다. |
| [database.classify_pool_mode](database.md#function-classify_pool_mode) | 호스트·포트를 노출하지 않고 Supabase 풀러 유형을 분류한다. |
| [database.get_pool_mode](database.md#function-get_pool_mode) | 환경변수 ``DB_URL``에서 첫 호스트·포트를 읽어 연결 유형을 반환한다. |
| [database._get_manager](database.md#function-_get_manager) | 호출 프로세스에서 재사용할 PostgreSQL 연결 관리자를 준비한다. |
| [database._close_manager](database.md#function-_close_manager) | 프로세스 종료 시 캐시된 연결 관리자를 닫는다. |
| [database._mapper_root_for](database.md#function-_mapper_root_for) | 기본 스키마면 패키지 폴더, 아니면 ``recipe.`` 한정자를 바꾼 ``recipe.sql`` 사본 폴더. |
| [database.create_recipe_sql_session](database.md#function-create_recipe_sql_session) | ``recipe.sql`` mapper를 등록한 공통 ``PostgresDbSession`` 을 만든다. |
| [database.recipe_connection](database.md#function-recipe_connection) | 레시피 스키마를 search_path로 설정한 연결을 ``with`` 블록에 제공한다. |
| [main.main](main.md#function-main) | import 경로를 준비하고 scaffold 안내 문구를 출력한 뒤 0을 반환한다. 레시피 검색은 실행하지 않는다. |
| [name_normalization.normalize_name](name_normalization.md#function-normalize_name) | 식재료명 매칭과 중복 제거에 쓸 비교 문자열로 정규화한다. |
| [neo4j_connection.trusted_ca_file](neo4j_connection.md#function-trusted_ca_file) | 신뢰할 CA 번들 PEM 경로. 지정 파일이 없으면 오류(조용히 검증을 끄지 않는다). |
| [neo4j_connection.driver_arguments](neo4j_connection.md#function-driver_arguments) | ``GraphDatabase.driver`` 에 넘길 URI와 TLS 설정. 검증하는 TLS 스킴만 CA 번들을 명시한다. |
| [neo4j_connection.create_neo4j_driver](neo4j_connection.md#function-create_neo4j_driver) | 저장소 ``.env`` 의 ``NEO4J_URI`` / ``NEO4J_USERNAME`` / ``NEO4J_PASSWORD`` 로 드라이버를 만든다. |
| [pantry_graphrag.create_llm](pantry_graphrag.md#function-create_llm) | API 키가 있을 때만 Streamlit 파이프라인용 ChatOpenAI를 생성한다. |
| [pantry_graphrag.terms_in_question](pantry_graphrag.md#function-terms_in_question) | LLM이 뽑은 입력어 중 사용자 문장에 실제로 있는 것만 남긴다(정규화·공백 무시 비교, 중복 제거). |
| [pantry_graphrag.mask_phrases](pantry_graphrag.md#function-mask_phrases) | ``phrases`` (레시피명 등)를 지운다. 띄어쓰기만 다른 표기('닭고기 김치찌개')도 함께 지운다. |
| [pantry_graphrag.scan_vocabulary_terms](pantry_graphrag.md#function-scan_vocabulary_terms) | 문장에 들어 있는 DB 표준명·별칭을 긴 이름부터 찾아 문장 순서로 돌려준다(LLM 없는 문장 해석 대체 규칙). |
| [pantry_graphrag.foreign_ingredients](pantry_graphrag.md#function-foreign_ingredients) | ``text`` 에 나온 DB 식재료 이름 중 ``allowed`` 가 아닌 것. |
| [pantry_graphrag.has_final_consonant](pantry_graphrag.md#function-has_final_consonant) | 마지막 글자가 한글이면 받침 여부, 숫자면 읽는 소리 기준, 그 밖(영문 등)은 None. |
| [pantry_graphrag.josa](pantry_graphrag.md#function-josa) | ``word`` 뒤에 붙을 조사. ``josa('두부', '을', '를')`` → ``'두부를'``. 판단할 수 없으면 '을(를)' 형태. |
| [pantry_graphrag.josa_ro](pantry_graphrag.md#function-josa_ro) | '으로/로': 받침이 없거나 ㄹ 받침이면 '로'. |
| [pantry_graphrag.list_text](pantry_graphrag.md#function-list_text) | ``['a','b','c']`` → ``'a, b, c'``. ``limit`` 을 넘으면 ``'a, b 외 N개'``. |
| [pantry_graphrag.grounded_reason](pantry_graphrag.md#function-grounded_reason) | 근거만으로 만든 추천 이유(LLM 실패·검증 실패 시 대체 문장). |
| [pantry_graphrag.grounded_summary](pantry_graphrag.md#function-grounded_summary) | 추천 결과의 첫 레시피와 보유 재료로 LLM 없이 요약 문장을 만든다. |
| [pantry_graphrag.build_context](pantry_graphrag.md#function-build_context) | Neo4j 추천 DTO에서 LLM에 전달할 근거 필드만 추린다. |
| [pantry_graphrag.validate_answer](pantry_graphrag.md#function-validate_answer) | LLM 답변의 레시피 ID와 재료명을 조회 근거와 대조한다. |
| [pantry_recommend_service.split_terms](pantry_recommend_service.md#function-split_terms) | ``'계란, 두부, 양파'`` → ``['계란', '두부', '양파']``. 중복(정규화 기준)은 처음 것만 남긴다. |
| [search_recipe.parse_args](search_recipe.md#function-parse_args) | CLI 조회 조건과 출력 옵션을 파싱한다. |
| [search_recipe._print_rows](search_recipe.md#function-_print_rows) | 조회 행에서 요청한 컬럼만 골라 콘솔에 출력한다. |
| [search_recipe.print_detail](search_recipe.md#function-print_detail) | 레시피 상세와 단계·재료 목록을 콘솔에 출력한다. |
| [search_recipe.print_page](search_recipe.md#function-print_page) | 페이지형 조회 결과의 행과 건수 정보를 출력한다. |
| [search_recipe.main](search_recipe.md#function-main) | 조회 세션과 Service를 만들고 CLI 요청을 실행한 뒤 종료 코드를 반환한다. |
| [sql_schema.validate_schema_name](sql_schema.md#function-validate_schema_name) | 소문자 PostgreSQL 식별자인지 검사하고 그대로 돌려준다. |
| [sql_schema.configured_schema](sql_schema.md#function-configured_schema) | 명시 인자 → 환경변수 ``RECIPE_DB_SCHEMA`` → 기본 ``recipe`` 순서로 대상 스키마를 정한다. |
| [sql_schema.render_schema_sql](sql_schema.md#function-render_schema_sql) | ``recipe.`` 한정자를 ``target.`` 으로, ``recipe_src.`` 를 ``source.`` 로 바꾼다. |

## 관련 가이드

- [실행 흐름](../../04_execution_flow.md)
- [데이터 흐름](../../05_data_flow.md)
