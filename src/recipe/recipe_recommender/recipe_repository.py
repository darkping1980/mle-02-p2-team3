"""레시피(recipe 스키마) 등록·조회 공용 Repository 모듈.

``RecipeRegisterService`` 와 ``RecipeSearchService`` 가 함께 사용한다. Service 계층이 Python 값으로
호출하면, 이 모듈이 ``recipe.sql`` mapper의 파라미터 이름(대문자 snake_case)으로 바꿔
``PostgresDbSession`` 에 전달한다. SQL 문 자체는 ``recipe.sql`` 에만 있다.
"""

from common.postgres_db_session import PostgresDbSession


SYSTEM_USER_ID = "system"           # 등록·수정자 컬럼에 기록할 시스템 사용자 ID
COOK_METHOD_GROUP_ID = "COOK_MTHD"  # 조리 방법 공통코드 그룹 ID
COOK_METHOD_GROUP_NM = "조리 방법"


# region 1. PostgreSQL Named SQL Repository
# =========================================================
# 등록과 조회 Service가 공유하는 recipe.sql 호출 경계
# =========================================================
class RecipeRepository:
    """레시피 원본·마스터·정제·staging·관계의 등록·조회 SQL을 호출하는 Repository(DAO).

    DB 연결과 트랜잭션은 주입받은 ``sql_session`` 이 관리하며, 이 클래스는 상태를 갖지 않는다.
    조회 결과 dict의 key는 세션의 ``camel_case_keys`` 설정에 따라 ``rcpCatId`` 같은 camelCase가 된다.
    키 구조: 레시피 ``rcp_id`` 단독, 식재료 ``ingr_id`` 단독, 레시피·요리 분류는 ``rcp_cat_rel`` N:M.
    """

    sql_session: PostgresDbSession  # 레시피 SQL 실행에 사용하는 데이터베이스 세션

    def __init__(self, sql_session, user_id=SYSTEM_USER_ID):
        """SQL 실행에 사용할 세션과 관리 컬럼에 기록할 사용자 ID를 주입받는다."""
        self.sql_session = sql_session
        self.user_id = user_id

    def _with_user(self, rows, **extra):
        """등록·수정 mapper 행마다 시스템 사용자와 공통 매개변수를 합친다."""
        return [{**row, **extra, "USER_ID": self.user_id} for row in rows]

    def find_schema_model(self):
        """대상 스키마의 모델 표식 ``{"hasRcpCatRel", "hasIngrCat"}``."""
        return self.sql_session.select_one("recipe.find_schema_model")

    # =========================================================
    # 원본 수집 회차
    # =========================================================
    def find_next_rcp_raw_id(self):
        """DB 함수 ``recipe.fn_get_biz_id('import_batch')`` 로 새 원본 수집 회차 ID를 발급받는다."""
        return self.sql_session.select_one("recipe.find_next_rcp_raw_id")["rcpRawId"]

    def find_latest_raw_batch(self):
        """가장 최근 원본 회차 ``{"rcpRawId", "rawCount", "lastCreateDate"}`` 또는 None."""
        return self.sql_session.select_one("recipe.find_latest_raw_batch")

    def list_raw_rows_by_batch(self, rcp_raw_id):
        """지정 회차 원본 행 목록. key는 camelCase(예: ``rcpRawSeq``, ``manualImg01``)."""
        return self.sql_session.select_list("recipe.list_raw_rows_by_batch", {"RCP_RAW_ID": rcp_raw_id})

    # =========================================================
    # 참조 마스터
    # =========================================================
    def find_recipe_category(self, category_name):
        """요리 종류명으로 ``{"rcpCatId", "rcpCatNm"}`` 를 조회한다. 없으면 None."""
        return self.sql_session.select_one("recipe.find_recipe_category", {"RCP_CAT_NM": category_name})

    def insert_recipe_categories(self, category_names):
        """요리 종류를 등록한다. Returns 새로 등록된 행 수."""
        return self.sql_session.execute_many(
            "recipe.insert_recipe_category",
            self._with_user({"RCP_CAT_NM": name} for name in category_names),
        )

    def upsert_cook_method_codes(self, cook_method_codes):
        """조리 방법 그룹과 상세 코드를 확정 코드표 ``{common_cd: common_cd_nm}`` 로 등록한다.

        Returns: ``(그룹 등록·갱신 수, 코드 등록·갱신 수)``.
        """
        group_count = self.sql_session.execute(
            "recipe.upsert_common_code_group",
            {"COMMON_CODE_GRP_ID": COOK_METHOD_GROUP_ID, "COMMON_CODE_GRP_NM": COOK_METHOD_GROUP_NM,
             "USER_ID": self.user_id},
        )
        code_count = self.sql_session.execute_many(
            "recipe.upsert_common_code",
            self._with_user(
                {"COMMON_CODE_GRP_ID": COOK_METHOD_GROUP_ID, "COMMON_CD": code, "COMMON_CD_NM": name}
                for code, name in cook_method_codes.items()
            ),
        )
        return group_count, code_count

    def list_cook_method_codes(self):
        """``COOK_MTHD`` 그룹의 ``{common_cd: common_cd_nm}``."""
        rows = self.sql_session.select_list("recipe.list_common_codes", {"COMMON_CODE_GRP_ID": COOK_METHOD_GROUP_ID})
        return {row["commonCd"]: row["commonCdNm"] for row in rows}

    # =========================================================
    # 기존 키 조회
    # =========================================================
    def list_recipe_key_map(self):
        """원본 레시피 번호(rcp_seq) → ``(rcp_id, rcp_raw_id)`` dict."""
        rows = self.sql_session.select_list("recipe.list_recipe_keys")
        return {row["rcpSeq"]: (row["rcpId"], row["rcpRawId"]) for row in rows}

    def list_recipe_category_map(self):
        """요리 종류명 → 요리 종류 ID dict."""
        rows = self.sql_session.select_list("recipe.list_recipe_categories")
        return {row["rcpCatNm"]: row["rcpCatId"] for row in rows}

    def list_recipe_category_relations(self):
        """레시피 ID → 등록된 요리 분류 ID 집합 dict."""
        relations: dict[str, set[str]] = {}
        for row in self.sql_session.select_list("recipe.list_recipe_category_relations"):
            relations.setdefault(row["rcpId"], set()).add(row["rcpCatId"])
        return relations

    def list_recipe_step_keys(self):
        """등록된 조리 단계 키 ``(rcp_id, step_no)`` 집합."""
        rows = self.sql_session.select_list("recipe.list_recipe_step_keys")
        return {(row["rcpId"], row["stepNo"]) for row in rows}

    def list_staging_keys(self, rcp_raw_id):
        """지정 회차에 이미 있는 staging ``(rcp_raw_seq, rcp_ingr_line_no)`` 집합."""
        rows = self.sql_session.select_list("recipe.list_staging_keys_by_batch", {"RCP_RAW_ID": rcp_raw_id})
        return {(row["rcpRawSeq"], row["rcpIngrLineNo"]) for row in rows}

    # =========================================================
    # 원본 / 레시피 / 조리 단계 / staging 등록 (batch)
    # =========================================================
    def insert_recipe_raws(self, rcp_raw_id, raw_rows):
        """원본 55개 컬럼 + 행 순번 dict 목록을 batch insert한다. Returns 새로 등록된 행 수."""
        return self.sql_session.execute_many(
            "recipe.insert_recipe_raw", self._with_user(raw_rows, RCP_RAW_ID=rcp_raw_id))

    def insert_recipes(self, rcp_raw_id, recipes):
        """새 정제 레시피를 등록한다(rcp_id는 DB 발급). Returns 등록 행 수."""
        return self.sql_session.execute_many(
            "recipe.insert_recipe", self._with_user(recipes, RCP_RAW_ID=rcp_raw_id))

    def update_recipes(self, rcp_raw_id, recipes):
        """기존 정제 레시피를 PK로 갱신한다(``RCP_ID`` 포함). Returns 값이 바뀐 행 수."""
        return self.sql_session.execute_many(
            "recipe.update_recipe", self._with_user(recipes, RCP_RAW_ID=rcp_raw_id))

    def insert_recipe_category_relations(self, relations):
        """``[{"RCP_ID", "RCP_CAT_ID"}]`` 레시피·요리 분류 관계를 등록한다. Returns 새로 등록된 행 수."""
        return self.sql_session.execute_many("recipe.insert_recipe_category_relation", self._with_user(relations))

    def upsert_recipe_steps(self, steps):
        """조리 단계 목록을 등록·갱신한다. Returns 등록되거나 내용이 바뀐 행 수."""
        return self.sql_session.execute_many("recipe.upsert_recipe_step", self._with_user(steps))

    def insert_recipe_ingredient_stagings(self, rcp_raw_id, stagings):
        """재료 파싱 후보 목록을 staging에 등록한다(rcp_ingr_stg_id는 DB 발급). Returns 등록 행 수."""
        return self.sql_session.execute_many(
            "recipe.insert_recipe_ingredient_staging", self._with_user(stagings, RCP_RAW_ID=rcp_raw_id))

    # =========================================================
    # 식재료 마스터
    # =========================================================
    def list_ingredient_map(self):
        """표준 식재료명 → ingr_id dict."""
        rows = self.sql_session.select_list("recipe.list_ingredients")
        return {row["ingrNm"]: row["ingrId"] for row in rows}

    def insert_ingredients(self, ingredients):
        """``[{"INGR_NM"}]`` 를 등록한다. Returns 등록 행 수."""
        return self.sql_session.execute_many("recipe.insert_ingredient", self._with_user(ingredients))

    def list_ingredient_alias_keys(self):
        """등록된 별칭 ``(ingr_id, ingr_als_nm)`` 집합."""
        rows = self.sql_session.select_list("recipe.list_ingredient_alias_keys")
        return {(row["ingrId"], row["ingrAlsNm"]) for row in rows}

    def insert_ingredient_aliases(self, aliases):
        """``[{"INGR_ID", "INGR_ALS_NM"}]`` 를 등록한다. Returns 등록 행 수."""
        return self.sql_session.execute_many("recipe.insert_ingredient_alias", self._with_user(aliases))

    def update_staging_verified_matches(self, rcp_raw_id):
        """표준 식재료명/별칭과 정확히 일치하는 staging 행을 자동 승인한다. Returns 승인 행 수."""
        return self.sql_session.execute(
            "recipe.update_staging_verified_matches", {"RCP_RAW_ID": rcp_raw_id, "USER_ID": self.user_id})

    def insert_recipe_ingredient_relations(self, rcp_raw_id):
        """승인된 staging 행으로 레시피별 사용 식재료 관계를 만든다. Returns 등록·갱신 행 수."""
        return self.sql_session.execute(
            "recipe.insert_recipe_ingredient_relations", {"RCP_RAW_ID": rcp_raw_id, "USER_ID": self.user_id})

    # =========================================================
    # 레시피 조회 (RecipeSearchService)
    # =========================================================
    def find_recipe_detail(self, rcp_seq=None, rcp_id=None):
        """원본 레시피 번호 또는 내부 레시피 ID로 레시피 한 건을 조회한다. 없으면 None."""
        return self.sql_session.select_one("recipe.find_recipe_detail", {"RCP_SEQ": rcp_seq, "RCP_ID": rcp_id})

    def list_recipes(self, rcp_nm=None, rcp_cat_nm=None, cook_mthd_cd=None, limit=20, offset=0):
        """레시피명(부분 일치)·요리 종류명·조리 방법 코드로 레시피 목록을 조회한다."""
        return self.sql_session.select_list("recipe.list_recipes", {
            "RCP_NM": rcp_nm, "RCP_CAT_NM": rcp_cat_nm, "COOK_MTHD_CD": cook_mthd_cd,
            "LIMIT": limit, "OFFSET": offset,
        })

    def count_recipes(self, rcp_nm=None, rcp_cat_nm=None, cook_mthd_cd=None):
        """``list_recipes()`` 와 같은 조건의 전체 건수."""
        row = self.sql_session.select_one("recipe.count_recipes", {
            "RCP_NM": rcp_nm, "RCP_CAT_NM": rcp_cat_nm, "COOK_MTHD_CD": cook_mthd_cd,
        })
        return row["totalCount"]

    def list_recipe_steps(self, rcp_id):
        """레시피 PK로 조리 단계 목록을 조회한다."""
        return self.sql_session.select_list("recipe.list_recipe_steps", {"RCP_ID": rcp_id})

    def list_recipe_ingredients(self, rcp_id):
        """레시피 PK로 사용 표준 식재료 목록을 조회한다."""
        return self.sql_session.select_list("recipe.list_recipe_ingredients", {"RCP_ID": rcp_id})

    def list_recipe_unmatched_stagings(self, rcp_id):
        """레시피 재료 원문 중 표준 식재료에 연결되지 않은 staging 행."""
        return self.sql_session.select_list("recipe.list_recipe_unmatched_stagings", {"RCP_ID": rcp_id})

    def find_ingredient_by_name(self, ingr_nm):
        """표준 식재료명 또는 별칭과 정확히 일치하는 표준 식재료 목록(보통 0~1건)."""
        return self.sql_session.select_list("recipe.find_ingredient_by_name", {"INGR_NM": ingr_nm})

    def list_ingredient_aliases(self, ingr_id):
        """표준 식재료 PK로 별칭 목록을 조회한다."""
        return self.sql_session.select_list("recipe.list_ingredient_aliases", {"INGR_ID": ingr_id})

    def list_recipes_by_ingredient(self, ingr_id, limit=20, offset=0):
        """표준 식재료 PK로 그 식재료를 사용하는 레시피 목록을 조회한다."""
        return self.sql_session.select_list("recipe.list_recipes_by_ingredient", {
            "INGR_ID": ingr_id, "LIMIT": limit, "OFFSET": offset,
        })

    def count_recipes_by_ingredient(self, ingr_id):
        """표준 식재료를 사용하는 레시피 수."""
        row = self.sql_session.select_one("recipe.count_recipes_by_ingredient", {"INGR_ID": ingr_id})
        return row["totalCount"]

    # =========================================================
    # 집계 / 정합성
    # =========================================================
    def count_recipe_tables(self):
        """목표 모델 11개 테이블 전체 행 수 dict."""
        return self.sql_session.select_one("recipe.count_recipe_tables")

    def count_batch_rows(self, rcp_raw_id):
        """지정 회차 기준 테이블별 행 수 dict."""
        return self.sql_session.select_one("recipe.count_batch_rows", {"RCP_RAW_ID": rcp_raw_id})

    def count_integrity_violations(self):
        """정합성 검사 항목별 위반 건수 dict. 모든 값이 0이어야 정상이다."""
        return self.sql_session.select_one("recipe.count_integrity_violations")

# endregion
