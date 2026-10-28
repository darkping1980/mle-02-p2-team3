"""레시피 조회 Service 모듈 (PostgreSQL 기반 MVP).

조회 조건을 검증하고 ``RecipeRepository`` 의 조회 메서드를 호출해 화면·CLI가 쓰기 쉬운
dict 결과를 구성한다. 데이터를 변경하지 않으며 SQL은 ``recipe.sql`` 에만 있다.
Neo4j 추천과는 별도의 PostgreSQL 일반 조회 경로다. CLI가 사용하며, 현재 호출부가
주석 처리된 개발용 로그 검증 함수도 재활성화하면 이 Service를 사용한다.
"""

from __future__ import annotations

from common.postgres_db_session import PostgresDbSession

from .recipe_repository import RecipeRepository


DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


# region 1. 조회 조건과 PostgreSQL 조회 Service
# =========================================================
# 입력 검증 → RecipeRepository → PostgresDbSession
# =========================================================
class RecipeSearchError(ValueError):
    """조회 조건이 잘못된 경우의 오류."""


class RecipeSearchService:
    """레시피·조리 단계·사용 식재료·표준 식재료를 조회하는 Service.

    의존 관계: ``RecipeRepository`` (등록 Service와 같은 Repository·mapper 사용).
    모든 메서드는 읽기 전용이며 결과 dict의 key는 세션 설정에 따라 camelCase다.
    """

    sql_session: PostgresDbSession  # Named SQL 실행에 사용하는 공통 세션.
    repository: RecipeRepository  # 조회 SQL을 묶은 DAO; 생성자에서 만든다.

    def __init__(self, sql_session):
        """조회 SQL 세션을 받아 Repository를 생성한다.

        Args:
            sql_session (PostgresDbSession): Named SQL을 실행할 공통 세션.
        """
        self.sql_session = sql_session
        self.repository = RecipeRepository(sql_session=sql_session)

    # =========================================================
    # 조건 검증
    # =========================================================
    @staticmethod
    def _text(value: str | None) -> str | None:
        """앞뒤 공백을 제거하고, 비어 있으면 '조건 없음'(None)으로 본다."""
        if value is None:
            return None
        value = value.strip()
        return value or None

    @staticmethod
    def _paging(page: int, page_size: int) -> tuple[int, int]:
        """페이지 번호(1부터)와 크기를 검증해 ``(limit, offset)`` 으로 바꾼다."""
        if page < 1:
            raise RecipeSearchError("page는 1 이상이어야 합니다.")
        if not 1 <= page_size <= MAX_PAGE_SIZE:
            raise RecipeSearchError(f"page_size는 1~{MAX_PAGE_SIZE} 사이여야 합니다.")
        return page_size, (page - 1) * page_size

    # =========================================================
    # 레시피
    # =========================================================
    def get_recipe_detail(self, rcp_seq: str | None = None, rcp_id: str | None = None) -> dict | None:
        """원본 레시피 번호 또는 내부 레시피 ID로 레시피 상세를 조회한다.

        Returns:
            ``{"recipe", "steps", "ingredients", "unmatchedIngredients"}`` 또는 레시피가 없으면 None.
            조리 단계와 사용 식재료는 레시피 PK ``rcp_id`` 로 조회한다. 요리 분류는 여러 개일 수 있으며
            ``recipe["rcpCatNm"]`` 에 이름순으로 합쳐 있다.
        """
        rcp_seq, rcp_id = self._text(rcp_seq), self._text(rcp_id)
        # 두 bool의 동등 비교: 둘 다 비었거나 둘 다 있으면 잘못된 요청이다.
        if (rcp_seq is None) == (rcp_id is None):
            raise RecipeSearchError("rcp_seq와 rcp_id 중 하나만 지정해야 합니다.")
        recipe = self.repository.find_recipe_detail(rcp_seq=rcp_seq, rcp_id=rcp_id)
        if recipe is None:
            return None
        rcp_id = recipe["rcpId"]
        return {
            "recipe": recipe,
            "steps": self.repository.list_recipe_steps(rcp_id),
            "ingredients": self.repository.list_recipe_ingredients(rcp_id),
            "unmatchedIngredients": self.repository.list_recipe_unmatched_stagings(rcp_id),
        }

    def search_recipes(self, name: str | None = None, category: str | None = None,
                       cook_method: str | None = None, page: int = 1,
                       page_size: int = DEFAULT_PAGE_SIZE) -> dict:
        """레시피명(부분 일치)·요리 종류명·조리 방법으로 레시피를 검색한다.

        조리 방법은 COOK_MTHD 코드(예: ``000004``) 또는 코드명(예: ``찌기``)을 받는다.

        Returns: ``{"totalCount", "page", "pageSize", "items"}``.
        """
        name, category, cook_method = self._text(name), self._text(category), self._text(cook_method)
        if name is None and category is None and cook_method is None:
            raise RecipeSearchError("레시피명, 요리 종류, 조리 방법 중 하나 이상을 지정해야 합니다.")
        limit, offset = self._paging(page, page_size)
        return {
            "totalCount": self.repository.count_recipes(name, category, cook_method),
            "page": page,
            "pageSize": page_size,
            "items": self.repository.list_recipes(name, category, cook_method, limit, offset),
        }

    def list_recipe_steps(self, rcp_seq: str) -> list[dict]:
        """원본 레시피 번호로 조리 단계 목록을 조회한다. 레시피가 없으면 빈 목록."""
        recipe = self.repository.find_recipe_detail(rcp_seq=self._text(rcp_seq))
        return [] if recipe is None else self.repository.list_recipe_steps(recipe["rcpId"])

    def list_recipe_ingredients(self, rcp_seq: str) -> list[dict]:
        """원본 레시피 번호로 사용 표준 식재료 목록을 조회한다. 레시피가 없으면 빈 목록."""
        recipe = self.repository.find_recipe_detail(rcp_seq=self._text(rcp_seq))
        return [] if recipe is None else self.repository.list_recipe_ingredients(recipe["rcpId"])

    # =========================================================
    # 식재료
    # =========================================================
    def find_ingredient(self, name: str) -> dict | None:
        """표준 식재료명 또는 별칭으로 표준 식재료와 별칭 목록을 조회한다.

        Returns: ``{"ingredient", "aliases"}`` 또는 일치하는 표준 식재료가 없으면 None.

        Raises:
            RecipeSearchError: 이름이 비었거나, 별칭이 둘 이상의 표준 식재료를 가리키는 경우.
        """
        name = self._text(name)
        if name is None:
            raise RecipeSearchError("식재료명을 지정해야 합니다.")
        matches = self.repository.find_ingredient_by_name(name)
        if not matches:
            return None
        if len({row["ingrId"] for row in matches}) > 1:
            # set comprehension으로 서로 다른 PK만 센다. 별칭 충돌을 임의로 한쪽에 연결하지 않는다.
            raise RecipeSearchError(f"'{name}' 이(가) 여러 표준 식재료와 일치합니다: {[row['ingrNm'] for row in matches]}")
        ingredient = matches[0]
        return {
            "ingredient": ingredient,
            "aliases": self.repository.list_ingredient_aliases(ingredient["ingrId"]),
        }

    def search_recipes_by_ingredient(self, name: str, page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict | None:
        """표준 식재료명 또는 별칭으로 그 식재료를 사용하는 레시피를 조회한다.

        Returns: ``{"ingredient", "aliases", "totalCount", "page", "pageSize", "items"}`` 또는 None.
        """
        limit, offset = self._paging(page, page_size)
        found = self.find_ingredient(name)
        if found is None:
            return None
        ingr_id = found["ingredient"]["ingrId"]
        return {
            **found,
            "totalCount": self.repository.count_recipes_by_ingredient(ingr_id),
            "page": page,
            "pageSize": page_size,
            "items": self.repository.list_recipes_by_ingredient(ingr_id, limit, offset),
        }

# endregion
