"""식약처 공공데이터 레시피 프로젝트 패키지.

등록·조회 구성 (자동차 매뉴얼 프로그램과 같은 평면 배치):
    recipe.sql                  등록·조회 SQL mapper (namespace: recipe)
    recipe_repository.py        RecipeRepository — mapper 호출(DAO), 등록·조회 공용
    recipe_ingredient_parser.py RecipeIngredientParser — 재료 원문 파싱 규칙(DB 무관)
    recipe_register_service.py  RecipeRegisterService — CSV 등록 업무 흐름·트랜잭션
    recipe_search_service.py    RecipeSearchService — 조회 조건 검증·결과 구성(읽기 전용)
    setup/register_recipe_csv.py      등록 CLI   (python -m recipe_recommender.setup.register_recipe_csv)
    search_recipe.py            조회 CLI   (python -m recipe_recommender.search_recipe)

패키지를 import하면 과제 폴더의 ``common`` 을 import할 수 있게 경로를 준비하고,
pgvector 0.5의 모듈 경로 차이를 별칭으로 맞춘다(``common`` 소스는 수정하지 않음).
"""

from .config import prepare_common_imports

prepare_common_imports()
