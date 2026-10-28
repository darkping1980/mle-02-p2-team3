"""그래프 적재에 필요한 PostgreSQL 목표 모델을 한 시점의 스냅샷으로 읽는다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ..config import load_project_environment, prepare_common_imports
from ..sql_schema import configured_schema, render_schema_sql


# region 1. 같은 시점의 PostgreSQL 원천 DTO
# =========================================================
# 그래프 노드·관계 원천과 검증용 카탈로그 데이터
# =========================================================
@dataclass(frozen=True)
class GraphSourceSnapshot:
    """한 읽기 트랜잭션의 원천 테이블·카탈로그 조회값을 묶는 DTO.

    ``read_snapshot``이 만들고 그래프 적재 Service가 정합성 검증과 적재에 사용한다.
    ``frozen=True``는 Java의 불변 DTO처럼 필드 재할당을 막지만, 내부 리스트까지
    깊은 복사로 고정하지는 않는다.
    """
    observed_at: datetime  # 스냅샷을 읽은 DB 시각.
    database: str  # 조회 대상 PostgreSQL 데이터베이스명.
    role: str  # 원천 조회에 사용한 DB 사용자.
    recipe_categories: list[dict]  # 레시피 분류 노드 원천 행.
    ingredients: list[dict]  # 표준 식재료 노드 원천 행.
    recipes: list[dict]  # 레시피 노드 원천 행.
    recipe_category_links: list[dict]  # 레시피와 분류의 관계 원천 행.
    aliases: list[dict]  # 식재료 별칭; 정합성 검사에 사용한다.
    uses: list[dict]  # 레시피의 식재료 사용 관계 원천 행.
    steps: list[dict]  # 조리 단계(rcp_step) 노드·RCP_HAS_STEP 관계 원천 행. (rcp_id, step_no) 순서.
    raw_refs: list[dict]  # 식약처 원본 ID와 번호 참조 행.
    stage_status: list[dict]  # 식재료 중간 적재 상태별 건수.
    pk_definitions: dict[str, list[str]]  # 테이블별 기본 키 컬럼 순서.
    column_types: dict[tuple[str, str], tuple[str, bool]]  # (테이블, 컬럼)별 DB 타입·NOT NULL 여부.
    code_groups: list[dict]  # 조리 방법 등 공통코드 그룹 검증 원천.

    @property
    def counts(self) -> dict[str, int]:
        """노드·관계별 원천 행 수를 적재 후 그래프 건수 비교용으로 계산한다."""
        return {
            "rcp_cat": len(self.recipe_categories),
            "ingr": len(self.ingredients),
            "rcp": len(self.recipes),
            "RCP_IN_RECIPE_CATEGORY": len(self.recipe_category_links),
            "RCP_USES": len(self.uses),
            "rcp_step": len(self.steps),
            "RCP_HAS_STEP": len(self.steps),     # 단계 한 행 = 노드 하나 + 관계 하나
        }


# endregion
# region 2. 읽기 전용 원천 스냅샷 Repository
# =========================================================
# REPEATABLE READ READ ONLY로 여러 테이블을 한 시점에서 조회
# =========================================================
class RecipeGraphSourceRepository:
    """PostgreSQL SELECT 전용 DAO. 데이터와 스키마를 변경하지 않는다.

    ``schema``는 읽을 PostgreSQL 스키마를 선택한다(기본값: 환경변수 또는 ``recipe``).
    """

    def __init__(self, schema: str | None = None):
        """명시한 스키마 또는 환경 설정에서 조회 스키마를 결정한다."""
        self.schema = configured_schema(schema)

    def read_snapshot(self) -> GraphSourceSnapshot:
        """REPEATABLE READ READ ONLY 트랜잭션에서 노드·관계 원천을 함께 읽는다.

        테이블을 따로 읽는 동안 다른 세션이 갱신해도 한 시점의 관계를 검증하기 위해서다.
        명시적 rollback은 읽기 트랜잭션을 끝내며, finally는 오류 때도 연결을 정리한다.
        """
        load_project_environment()
        prepare_common_imports()
        from common.database_manager import DatabaseManager

        manager = DatabaseManager()
        try:
            with manager.connect(camel_case_keys=False) as connection:
                # 풀의 새 연결은 pgvector 설정 콜백을 마친 유휴 상태이므로 읽기 트랜잭션을 시작한다.
                connection.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")

                def rows(sql: str, params: tuple = ()) -> list[dict]:
                    """스키마를 적용한 SELECT 결과를 일반 dict 행으로 바꾼다."""
                    return [dict(row) for row in connection.execute(render_schema_sql(sql, self.schema), params).fetchall()]

                try:
                    identity = rows("SELECT now() AS observed_at, current_database() AS database, current_user AS role")[0]
                    recipe_categories = rows("SELECT rcp_cat_id, rcp_cat_nm FROM recipe.rcp_cat ORDER BY rcp_cat_id")
                    ingredients = rows("SELECT ingr_id, ingr_nm FROM recipe.ingr ORDER BY ingr_id")
                    aliases = rows("SELECT ingr_id, ingr_als_nm FROM recipe.ingr_als ORDER BY ingr_id, ingr_als_nm")
                    recipes = rows(
                        "SELECT r.rcp_id, r.rcp_seq, r.rcp_raw_id, r.rcp_nm, "
                        "r.cook_mthd_cd, cd.common_cd_nm AS cook_mthd_nm, "
                        "r.rcp_energy_kcal, r.rcp_nutrition_status, r.rcp_image_url "
                        "FROM recipe.rcp r LEFT JOIN recipe.common_cd cd "
                        "ON cd.common_code_grp_id = 'COOK_MTHD' AND cd.common_cd = r.cook_mthd_cd "
                        "ORDER BY r.rcp_id"
                    )
                    recipe_category_links = rows(
                        "SELECT rcp_id, rcp_cat_id FROM recipe.rcp_cat_rel ORDER BY rcp_id, rcp_cat_id"
                    )
                    uses = rows("SELECT rcp_id, ingr_id, rcp_raw_id FROM recipe.rcp_ingr ORDER BY rcp_id, ingr_id")
                    # 식약처 MANUAL01~20 / MANUAL_IMG01~20을 등록한 원본 그대로의 조리 단계.
                    steps = rows(
                        "SELECT rcp_id, step_no, rcp_step_instruction_txt, rcp_step_image_url "
                        "FROM recipe.rcp_step ORDER BY rcp_id, step_no"
                    )
                    raw_refs = rows("SELECT rcp_raw_id, rcp_seq FROM recipe.rcp_raw")
                    stage_status = rows(
                        "SELECT rcp_ingr_status, count(*) AS n FROM recipe.rcp_ingr_stg "
                        "GROUP BY rcp_ingr_status ORDER BY rcp_ingr_status"
                    )
                    code_groups = rows("SELECT common_code_grp_id, common_code_grp_nm FROM recipe.common_code_grp")
                    pk_rows = rows(
                        "SELECT t.relname AS table_name, a.attname AS column_name "
                        "FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid "
                        "JOIN pg_namespace n ON n.oid=t.relnamespace "
                        "JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum,ord) ON true "
                        "JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=k.attnum "
                        "WHERE n.nspname=%s AND c.contype='p' ORDER BY t.relname,k.ord", (self.schema,)
                    )
                    col_rows = rows(
                        "SELECT t.relname AS table_name, a.attname AS column_name, "
                        "format_type(a.atttypid,a.atttypmod) AS data_type, a.attnotnull AS not_null "
                        "FROM pg_class t JOIN pg_namespace n ON n.oid=t.relnamespace "
                        "JOIN pg_attribute a ON a.attrelid=t.oid "
                        "WHERE n.nspname=%s AND t.relkind='r' AND a.attnum>0 AND NOT a.attisdropped", (self.schema,)
                    )
                    # 카탈로그 행을 테이블별 기본 키 컬럼 순서로 묶어 스키마를 검증한다.
                    pks: dict[str, list[str]] = {}
                    for row in pk_rows:
                        pks.setdefault(row["table_name"], []).append(row["column_name"])
                    types = {
                        (row["table_name"], row["column_name"]): (row["data_type"], row["not_null"])
                        for row in col_rows
                    }
                    return GraphSourceSnapshot(
                        observed_at=identity["observed_at"], database=identity["database"], role=identity["role"],
                        recipe_categories=recipe_categories, ingredients=ingredients, recipes=recipes,
                        recipe_category_links=recipe_category_links, aliases=aliases, uses=uses, steps=steps,
                        raw_refs=raw_refs, stage_status=stage_status, pk_definitions=pks,
                        column_types=types, code_groups=code_groups,
                    )
                finally:
                    connection.rollback()
        finally:
            manager.close()


# endregion
# region 3. Neo4j 적재용 값 변환
def recipe_graph_row(row: dict) -> dict:
    """Neo4j 드라이버가 받도록 PostgreSQL Decimal을 float로 바꾼 레시피 dict를 만든다."""
    result = {key: value for key, value in row.items() if key != "rcp_raw_id"}
    if isinstance(result.get("rcp_energy_kcal"), Decimal):
        result["rcp_energy_kcal"] = float(result["rcp_energy_kcal"])
    return result

# endregion
