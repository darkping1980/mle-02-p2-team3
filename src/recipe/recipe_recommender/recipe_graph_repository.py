"""Neo4j mapper를 호출하는 그래프 DAO. 업무 검증은 적재 Service가 담당한다."""

from __future__ import annotations

import os
import logging
from pathlib import Path

from .config import configure_query_logging, load_project_environment
from .neo4j_connection import create_neo4j_driver

# region 1. 그래프 모델 및 Mapper 경로
MAPPER_ROOT = Path(__file__).resolve().parent
# 목표 모델 그래프: 식재료 분류 노드(RcpIngredientCategory)·관계는 없다. 남아 있으면 미지 객체로 거부된다.
# rcp_step(조리 단계)은 recipe.rcp_step 행마다 하나이며 RCP_HAS_STEP으로 레시피에 연결된다.
NODE_LABELS = ("rcp_cat", "ingr", "rcp", "rcp_step")
REL_TYPES = ("RCP_IN_RECIPE_CATEGORY", "RCP_USES", "RCP_HAS_STEP")
SCHEMA_NAMES = (
    "rcp_key", "rcp_seq_key", "ingr_key",
    "rcp_cat_key", "rcp_step_key", "rcp_nm_idx", "ingr_nm_norm_idx",
)


# endregion
# region 2. Neo4j 드라이버와 Named Cypher Repository
# =========================================================
# 드라이버 소유권·세션 생성 및 그래프 조회·적재
# =========================================================
class RecipeGraphRepository:
    """Cypher 파일의 ``namespace.statement``를 Neo4jDbSession에 전달하는 DAO.

    추천 Service와 그래프 적재 Service가 생성한다. ``driver``를 외부에서 받으면
    종료 책임도 호출자에게 남기고, 직접 생성했을 때만 ``close``에서 닫는다.
    """
    def __init__(self, driver=None, database: str | None = None):
        """드라이버와 mapper 세션을 준비한다. ``driver`` 생략 시 직접 연결한다."""
        # 빈 그래프 점검은 아직 생성되지 않은 레이블을 조회하므로 알림을 줄인다.
        logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)
        load_project_environment()
        from common.neo4j_db_session import Neo4jDbSession

        # 기본은 none: 적재 CLI의 $rows(배치당 최대 1,000행)까지 :param 줄로 찍히지 않게 꺼 둔다.
        # 로컬 개발에서 RECIPE_QUERY_LOG를 켜면 combined 모드로 로그용 인라인 Cypher를 터미널에 출력한다.
        cypher_log_mode = "combined" if configure_query_logging() else "none"

        self._owns_driver = driver is None
        if driver is None:
            driver = create_neo4j_driver()          # 인증서 검증 유지 + 신뢰 CA 번들 명시
        self.driver = driver
        self.database = database if database is not None else (os.getenv("NEO4J_DATABASE") or None)
        self.mapper = Neo4jDbSession(
            mapper_root=MAPPER_ROOT, driver=driver, database=self.database, cypher_log_mode=cypher_log_mode
        )

    def close(self) -> None:
        """Repository가 직접 만든 드라이버만 닫는다."""
        if self._owns_driver:
            self.driver.close()

    def inspect(self) -> dict:
        """서버 연결과 스키마·노드·관계 현황을 적재 전 검증용으로 조회한다."""
        self.driver.verify_connectivity()
        version = self.mapper.select_one("recipe_graph_validation.server_version")
        database = self.mapper.select_one("recipe_graph_validation.database_name")["name"]
        constraints = self.mapper.select_list("recipe_graph_validation.list_constraints")
        indexes = self.mapper.select_list("recipe_graph_validation.list_indexes")
        total_nodes = self.mapper.select_one("recipe_graph_validation.total_nodes")["n"]
        total_rels = self.mapper.select_one("recipe_graph_validation.total_relationships")["n"]
        unknown_labels = self.mapper.select_list(
            "recipe_graph_validation.unknown_rcp_labels", {"expected": list(NODE_LABELS)}
        )
        unknown_rels = self.mapper.select_list(
            "recipe_graph_validation.unknown_rcp_relationships", {"expected": list(REL_TYPES)}
        )
        return {
            "version": version, "database": database,
            "constraints": constraints, "indexes": indexes,
            "total_nodes": total_nodes, "total_relationships": total_rels,
            "unknown_labels": unknown_labels, "unknown_relationships": unknown_rels,
        }

    def project_rows(self) -> dict[str, list[dict]]:
        """대상 노드와 관계의 키 목록을 종류별로 읽어 원천과 비교하게 한다."""
        return {
            name: self.mapper.select_list(f"recipe_graph_validation.{statement}")
            for name, statement in (
                ("rcp_cat", "recipe_category_keys"),
                ("ingr", "ingredient_keys"),
                ("rcp", "recipe_keys"),
                ("RCP_IN_RECIPE_CATEGORY", "recipe_category_links"),
                ("RCP_USES", "uses_links"),
                ("rcp_step", "recipe_step_keys"),
                ("RCP_HAS_STEP", "recipe_step_links"),
            )
        }

    def project_counts(self) -> dict[str, int]:
        """대상 그래프의 종류별 건수를 반환한다."""
        return self.mapper.select_one("recipe_graph_validation.project_counts")

    def validation_count(self, statement: str) -> int:
        """검증용 Named Cypher의 ``n`` 값을 읽는다."""
        return self.mapper.select_one(f"recipe_graph_validation.{statement}")["n"]

    def sample_recipe(self, recipe_id: str) -> list[dict]:
        """레시피 ID의 노드와 관계 예시를 조회한다."""
        return self.mapper.select_list("recipe_graph_validation.sample_recipe", {"id": recipe_id})

    def sample_ingredient(self, ingredient_id: str) -> list[dict]:
        """식재료 ID의 노드와 관계 예시를 조회한다."""
        return self.mapper.select_list("recipe_graph_validation.sample_ingredient", {"id": ingredient_id})

    # 검증용 읽기 호출과 구분한다. 아래 메서드는 적재 절차에서 스키마나 그래프를 변경한다.
    def create_schema(self) -> None:
        """적재 전 제약과 인덱스를 Named Cypher로 생성한다.

        Neo4j 스키마를 변경하므로 적재 절차에서만 호출한다.
        """
        for name in SCHEMA_NAMES:
            self.mapper.execute(f"recipe_graph_constraints.{name}")

    def explain_load_statements(self) -> int:
        """읽기 세션에서 적재 Cypher의 EXPLAIN 계획만 확인하고 실행 수를 반환한다."""
        from neo4j import READ_ACCESS

        names = (
            "load_recipe_categories", "load_ingredients", "load_recipes",
            "check_recipe_category_batch_matches", "link_recipe_categories",
            "check_uses_batch_matches", "link_uses",
            "check_recipe_step_batch_matches", "load_recipe_steps",
        )
        # 공통 QuerySession에는 EXPLAIN API가 없어 mapper 원문에 붙여 읽기 세션에서 검사한다.
        with self.driver.session(database=self.database, default_access_mode=READ_ACCESS) as session:
            for name in names:
                session.execute_read(
                    lambda tx, statement=name: tx.run(
                        "EXPLAIN\n" + self.mapper._query(f"recipe_graph_load.{statement}"), {"rows": []}
                    ).consume()
                )
        return len(names)

    def write_batch(self, statement: str, rows: list[dict], check_statement: str | None = None) -> None:
        """한 배치의 부모 노드 매칭 건수를 확인한 뒤 같은 트랜잭션에서 MERGE한다."""
        with self.mapper.transaction():
            if check_statement:
                result = self.mapper.select_one(f"recipe_graph_load.{check_statement}", {"rows": rows})
                if result is None or result["input_rows"] != len(rows) or result["matched_rows"] != len(rows):
                    raise ValueError(f"Parent match failure in {statement}: {result}")
            self.mapper.execute(f"recipe_graph_load.{statement}", {"rows": rows})

    def query_example(self, name: str, parameters: dict) -> list[dict]:
        """명명된 읽기 Cypher를 호출한다. 현재 일반 사용자 CLI가 아닌 검증 Service에서 사용한다."""
        return self.mapper.select_list(f"recipe_graph_queries.{name}", parameters)

    def statement_text(self, statement: str) -> str:
        """``namespace.name`` Named Cypher의 원문을 돌려준다(실행하지 않음, 화면의 '실행 Cypher' 표시용)."""
        return self.mapper._query(statement)

# endregion
