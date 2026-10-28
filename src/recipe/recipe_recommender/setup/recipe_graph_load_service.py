"""PostgreSQL 목표 모델을 검증하고 Neo4j 레시피 그래프에 적재·대조한다.

``load_recipe_graph`` 진입점이 원천·그래프 Repository를 주입해 이 Service를 실행한다.
레시피는 분류(``RCP_IN_RECIPE_CATEGORY``)와 식재료(``RCP_USES``)에 연결된다.
조리 단계(``rcp_step``)는 ``RCP_HAS_STEP``으로 레시피에 연결되며 식약처 원본 설명·이미지 URL을 그대로 담는다.
이전 복합 키 모델 객체가 남은 그래프는 쓰기 전에 거부한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..recipe_graph_repository import RecipeGraphRepository
from ..name_normalization import normalize_name
from .recipe_graph_source_repository import (
    GraphSourceSnapshot, RecipeGraphSourceRepository, recipe_graph_row,
)

# region 1. 적재 순서와 목표 모델 규칙
EXPECTED_PKS = {
    "rcp_raw": ["rcp_raw_id", "rcp_raw_seq"],
    "rcp_cat": ["rcp_cat_id"],
    "rcp_cat_rel": ["rcp_id", "rcp_cat_id"],
    "common_code_grp": ["common_code_grp_id"],
    "common_cd": ["common_code_grp_id", "common_cd"],
    "rcp": ["rcp_id"],
    "rcp_step": ["rcp_id", "step_no"],
    "ingr": ["ingr_id"],
    "ingr_als": ["ingr_id", "ingr_als_id"],
    "rcp_ingr_stg": ["rcp_raw_id", "rcp_raw_seq", "rcp_ingr_stg_id"],
    "rcp_ingr": ["rcp_id", "ingr_id"],
}
EXPECTED_SCHEMA = {
    "rcp_key": ("NODE_PROPERTY_UNIQUENESS", ["rcp"], ["rcp_id"]),
    "rcp_seq_key": ("NODE_PROPERTY_UNIQUENESS", ["rcp"], ["rcp_seq"]),
    "ingr_key": ("NODE_PROPERTY_UNIQUENESS", ["ingr"], ["ingr_id"]),
    "rcp_cat_key": ("NODE_PROPERTY_UNIQUENESS", ["rcp_cat"], ["rcp_cat_id"]),
    "rcp_step_key": ("NODE_PROPERTY_UNIQUENESS", ["rcp_step"], ["rcp_id", "step_no"]),
}
EXPECTED_INDEXES = {
    "rcp_nm_idx": ("RANGE", ["rcp"], ["rcp_nm"]),
    "ingr_nm_norm_idx": ("RANGE", ["ingr"], ["ingr_nm_norm"]),
}
# 이전 그래프 스키마 이름(복합 키·식재료 분류 모델, Rcp* 라벨 시절 제약·인덱스). 남아 있으면 적재하지 않는다.
LEGACY_SCHEMA_NAMES = (
    "rcp_recipe_composite_key", "rcp_ingredient_composite_key", "rcp_ingredient_category_key",
    "rcp_recipe_key", "rcp_recipe_source_seq", "rcp_ingredient_key", "rcp_recipe_category_key",
    "rcp_recipe_name_idx", "rcp_ingredient_name_norm_idx",
)
STAGES = (
    ("load_recipe_categories", "recipe_categories", None),
    ("load_ingredients", "ingredients", None),
    ("load_recipes", "recipes", None),
    ("link_recipe_categories", "recipe_links", "check_recipe_category_batch_matches"),
    ("link_uses", "uses", "check_uses_batch_matches"),
    # 기존 단계 뒤에 추가한다. 노드와 관계를 한 문장에서 MERGE하므로 앞 단계의 결과는 바뀌지 않는다.
    ("load_recipe_steps", "steps", "check_recipe_step_batch_matches"),
)
KEY_SPECS = {
    "rcp_cat": ("rcp_cat_id",),
    "ingr": ("ingr_id",),
    "rcp": ("rcp_id",),
    "RCP_IN_RECIPE_CATEGORY": ("rcp_id", "rcp_cat_id"),
    "RCP_USES": ("rcp_id", "ingr_id"),
    "rcp_step": ("rcp_id", "step_no"),
    "RCP_HAS_STEP": ("rcp_id", "step_no"),
}
STEP_NO_RANGE = range(1, 21)        # 식약처 원본 MANUAL01~MANUAL20 (PostgreSQL ck_rcp_step_no와 같음)


# endregion
# region 2. 원천 키 검증과 적재 입력 DTO
def _key(row: dict, *columns: str) -> tuple:
    """행에서 지정한 컬럼 값을 순서대로 뽑아 비교용 복합 키를 만든다."""
    return tuple(row[column] for column in columns)


def _unique_keys(rows: list[dict], columns: tuple[str, ...], label: str) -> set[tuple]:
    """적재 전 원천 키의 빈 값·타입·중복을 검사하고 키 집합을 반환한다.

    Raises:
        ValueError: 키가 비었거나 문자열이 아니거나 중복될 때.
    """
    seen = set()
    for row in rows:
        key = _key(row, *columns)
        if any(not isinstance(item, str) or not item for item in key):
            raise ValueError(f"NULL/empty/non-string key in {label}: {key}")
        if key in seen:
            raise ValueError(f"Duplicate key in {label}: {key}")
        seen.add(key)
    return seen


def _step_rows(steps: list[dict], recipe_keys: set[tuple]) -> list[dict]:
    """조리 단계 원천을 검사하고 Neo4j 적재 행으로 바꾼다.

    단계 번호는 원본 MANUAL 번호를 그대로 쓰므로 중간 번호가 비어 있어도 허용한다.
    설명은 그대로 두고, 이미지 URL은 빈 문자열만 ``None``으로 바꿔 속성을 생략하게 한다.

    Args:
        steps (list[dict]): ``recipe.rcp_step`` SELECT 결과.
        recipe_keys (set[tuple]): 검증을 마친 레시피 키 집합.

    Returns:
        list[dict]: ``(rcp_id, step_no)`` 순서의 ``load_recipe_steps`` 입력 행.

    Raises:
        ValueError: 키 중복·부모 누락·번호 범위·빈 설명이 있을 때.
    """
    seen: set[tuple] = set()
    rows = []
    for row in steps:
        key = (row["rcp_id"], row["step_no"])
        if not isinstance(row["rcp_id"], str) or not row["rcp_id"]:
            raise ValueError(f"NULL/empty/non-string key in rcp_step: {key}")
        # bool은 int의 하위 타입이라 따로 막는다.
        if isinstance(row["step_no"], bool) or not isinstance(row["step_no"], int) or row["step_no"] not in STEP_NO_RANGE:
            raise ValueError(f"Recipe step number out of MANUAL01~20 range: {key}")
        if key in seen:
            raise ValueError(f"Duplicate key in rcp_step: {key}")
        if (row["rcp_id"],) not in recipe_keys:
            raise ValueError("Recipe step parent orphan")
        if not (row["rcp_step_instruction_txt"] or "").strip():
            raise ValueError(f"Missing recipe step instruction: {key}")
        seen.add(key)
        rows.append({
            "rcp_id": row["rcp_id"], "step_no": row["step_no"],
            "rcp_step_instruction_txt": row["rcp_step_instruction_txt"],
            "rcp_step_image_url": (row["rcp_step_image_url"] or "").strip() or None,
        })
    return sorted(rows, key=lambda item: (item["rcp_id"], item["step_no"]))


@dataclass(frozen=True)
class PreparedGraph:
    """검증된 원천과 적재 단계별 입력 행을 묶는 불변 필드 DTO."""
    source: GraphSourceSnapshot  # 같은 읽기 시점의 PostgreSQL 원천과 스키마 정보.
    stages: dict[str, list[dict]]  # STAGES의 단계명별 Neo4j MERGE 입력 행.

    @property
    def expected_counts(self) -> dict[str, int]:
        """적재 후 그래프와 비교할 원천 노드·관계 건수."""
        return self.source.counts


# endregion
# region 3. PostgreSQL 원천 검증과 Neo4j 적재 Service
# =========================================================
# prepare → preflight_graph → apply 또는 verify
# =========================================================
class RecipeGraphLoadService:
    """원천 검증, 적재 순서, 결과 비교를 조정하는 Service.

    ``load_recipe_graph``가 생성한다. PostgreSQL 읽기는 ``source`` DAO에,
    Neo4j 조회·쓰기는 ``graph`` DAO에 위임한다.
    """
    def __init__(self, source: RecipeGraphSourceRepository, graph: RecipeGraphRepository):
        """원천 조회 DAO와 그래프 DAO를 적재 절차에 주입한다."""
        self.source = source
        self.graph = graph

    def prepare(self) -> PreparedGraph:
        """PostgreSQL 한 시점의 데이터를 읽고 키·참조·코드·별칭을 검사해 배치 입력으로 변환한다."""
        snap = self.source.read_snapshot()
        if snap.pk_definitions != EXPECTED_PKS:
            raise ValueError("PostgreSQL PK/table definitions differ from the approved target model")
        for table, column in (
            ("rcp", "rcp_id"), ("ingr", "ingr_id"), ("rcp_cat", "rcp_cat_id"),
            ("rcp_cat_rel", "rcp_id"), ("rcp_cat_rel", "rcp_cat_id"),
            ("rcp_ingr", "rcp_id"), ("rcp_ingr", "ingr_id"),
        ):
            if snap.column_types.get((table, column)) != ("character varying(20)", True):
                raise ValueError(f"Unexpected key column type/nullability: {table}.{column}")
        if snap.column_types.get(("rcp", "rcp_seq")) != ("text", True):
            raise ValueError("Unexpected recipe source ID type/nullability")
        if snap.column_types.get(("rcp", "cook_mthd_cd")) != ("character varying(20)", True):
            raise ValueError("Unexpected cooking method code type/nullability")
        if snap.column_types.get(("rcp", "rcp_energy_kcal"), (None,))[0] != "numeric(10,2)":
            raise ValueError("Unexpected nutrition mapping")
        if snap.column_types.get(("rcp", "rcp_image_url"), (None,))[0] != "text":
            raise ValueError("Unexpected recipe image mapping")
        for column, expected in (
            ("rcp_id", ("character varying(20)", True)), ("step_no", ("smallint", True)),
            ("rcp_step_instruction_txt", ("text", True)), ("rcp_step_image_url", ("text", False)),
        ):
            if snap.column_types.get(("rcp_step", column)) != expected:
                raise ValueError(f"Unexpected recipe step column type/nullability: rcp_step.{column}")
        if not any(row["common_code_grp_id"] == "COOK_MTHD" for row in snap.code_groups):
            raise ValueError("COOK_MTHD group is absent in actual common_code_grp")

        cat_keys = _unique_keys(snap.recipe_categories, ("rcp_cat_id",), "rcp_cat")
        recipe_keys = _unique_keys(snap.recipes, ("rcp_id",), "rcp")
        ingredient_keys = _unique_keys(snap.ingredients, ("ingr_id",), "ingr")
        _unique_keys(snap.recipes, ("rcp_seq",), "rcp_seq")
        _unique_keys(snap.recipe_category_links, ("rcp_id", "rcp_cat_id"), "rcp_cat_rel")
        _unique_keys(snap.uses, ("rcp_id", "ingr_id"), "rcp_ingr")
        _unique_keys(snap.raw_refs, ("rcp_raw_id", "rcp_seq"), "rcp_raw source reference")

        recipes_by_key = {_key(row, "rcp_id"): row for row in snap.recipes}
        raw_keys = {_key(row, "rcp_raw_id", "rcp_seq") for row in snap.raw_refs}
        for row in snap.recipes:
            if (row["rcp_raw_id"], row["rcp_seq"]) not in raw_keys:
                raise ValueError("Recipe raw source orphan")
            if not row["cook_mthd_nm"]:
                raise ValueError("Cooking method code failed COOK_MTHD group join")
            if not re.fullmatch(r"[0-9]{6}", row["cook_mthd_cd"]):
                raise ValueError("Cooking method code is not a 6-digit COOK_MTHD code")
            if not row["rcp_nm"] or not row["rcp_nutrition_status"]:
                raise ValueError("Missing required recipe display/nutrition status")
        categorized = set()
        for row in snap.recipe_category_links:
            if _key(row, "rcp_id") not in recipe_keys or _key(row, "rcp_cat_id") not in cat_keys:
                raise ValueError("Recipe category relation orphan")
            categorized.add(_key(row, "rcp_id"))
        if categorized != recipe_keys:
            raise ValueError("Recipe without category relation")
        for row in snap.ingredients:
            if not row["ingr_nm"]:
                raise ValueError("Missing ingredient name")
        for row in snap.uses:
            recipe_key = _key(row, "rcp_id")
            if recipe_key not in recipe_keys or _key(row, "ingr_id") not in ingredient_keys:
                raise ValueError("RCP_USES parent orphan")
            if row["rcp_raw_id"] != recipes_by_key[recipe_key]["rcp_raw_id"]:
                raise ValueError("RCP_USES source batch differs from its recipe")

        aliases_by_key: dict[tuple, set[str]] = {key: set() for key in ingredient_keys}
        for row in snap.aliases:
            key = _key(row, "ingr_id")
            if key not in ingredient_keys or not row["ingr_als_nm"]:
                raise ValueError("Ingredient alias has missing parent or name")
            aliases_by_key[key].add(row["ingr_als_nm"])
        name_targets: dict[str, set[tuple]] = {}
        ingredient_rows = []
        for row in snap.ingredients:
            key = _key(row, "ingr_id")
            aliases = sorted(aliases_by_key[key])
            names = {normalize_name(row["ingr_nm"]), *(normalize_name(name) for name in aliases)}
            for name in names:
                name_targets.setdefault(name, set()).add(key)
            ingredient_rows.append({
                **row, "ingr_nm_norm": normalize_name(row["ingr_nm"]),
                "alias_names": aliases, "alias_names_norm": sorted({normalize_name(name) for name in aliases}),
            })
        if any(len(targets) > 1 for targets in name_targets.values()):
            # 한 검색어가 여러 ingr_id로 해석되면 자동 추천 결과가 모호해진다.
            raise ValueError("Ingredient name/alias maps to multiple ingredient keys")

        stages = {
            "recipe_categories": snap.recipe_categories,
            "ingredients": ingredient_rows,
            "recipes": [recipe_graph_row(row) for row in snap.recipes],
            "recipe_links": [{"rcp_id": row["rcp_id"], "rcp_cat_id": row["rcp_cat_id"]}
                             for row in snap.recipe_category_links],
            "uses": [{key: row[key] for key in ("rcp_id", "ingr_id")} for row in snap.uses],
            "steps": _step_rows(snap.steps, recipe_keys),
        }
        return PreparedGraph(snap, stages)

    def _check_schema_names(self, inspection: dict, *, require_all: bool) -> None:
        """실제 Neo4j 제약·인덱스 이름이 목표 모델과 맞는지 확인한다."""
        constraints = {item["name"]: item for item in inspection["constraints"]}
        indexes = {item["name"]: item for item in inspection["indexes"]}
        legacy = sorted(name for name in LEGACY_SCHEMA_NAMES if name in constraints or name in indexes)
        if legacy:
            raise ValueError(f"Legacy graph schema exists {legacy}; "
                             "clean up the previous graph model under a separate approval first")
        for name, (kind, labels, properties) in EXPECTED_SCHEMA.items():
            item = constraints.get(name)
            if item is None:
                if require_all:
                    raise ValueError(f"Missing expected constraint: {name}")
                if name in indexes:
                    raise ValueError(f"Constraint name occupied by index: {name}")
                continue
            if (item["type"], item["labelsOrTypes"], item["properties"]) != (kind, labels, properties):
                raise ValueError(f"Conflicting constraint definition: {name}")
        for name, (kind, labels, properties) in EXPECTED_INDEXES.items():
            item = indexes.get(name)
            if item is None:
                if require_all:
                    raise ValueError(f"Missing expected index: {name}")
                if name in constraints:
                    raise ValueError(f"Index name occupied by constraint: {name}")
                continue
            if (item["type"], item["labelsOrTypes"], item["properties"], item["owningConstraint"]) != (
                kind, labels, properties, None
            ):
                raise ValueError(f"Conflicting index definition: {name}")

    def _expected_sets(self, prepared: PreparedGraph) -> dict[str, set[tuple]]:
        """준비된 PostgreSQL 원천을 노드·관계별 비교 키 집합으로 바꾼다."""
        stages = prepared.stages
        source = {
            "rcp_cat": stages["recipe_categories"], "ingr": stages["ingredients"],
            "rcp": stages["recipes"], "RCP_IN_RECIPE_CATEGORY": stages["recipe_links"], "RCP_USES": stages["uses"],
            "rcp_step": stages["steps"], "RCP_HAS_STEP": stages["steps"],
        }
        return {name: {_key(x, *KEY_SPECS[name]) for x in rows} for name, rows in source.items()}

    def _actual_sets(self, rows: dict[str, list[dict]]) -> dict[str, set[tuple]]:
        """Neo4j 조회 행을 원천과 비교할 키 집합으로 바꾼다."""
        return {name: {_key(item, *KEY_SPECS[name]) for item in entries} for name, entries in rows.items()}

    def preflight_graph(self, prepared: PreparedGraph) -> dict:
        """쓰기 전에 기존 그래프가 이번 PostgreSQL 원천의 부분집합인지 확인한다."""
        inspection = self.graph.inspect()
        if inspection["unknown_labels"] or inspection["unknown_relationships"]:
            raise ValueError("Unexpected or legacy recipe graph label or RCP_ relationship type exists")
        self._check_schema_names(inspection, require_all=False)
        rows = self.graph.project_rows()
        expected = self._expected_sets(prepared)
        actual = self._actual_sets(rows)
        counts = self.graph.project_counts()
        for name, keys in actual.items():
            if len(rows[name]) != len(keys) or counts[name] != len(rows[name]):
                raise ValueError(f"Duplicate or malformed existing project object: {name}")
            if not keys <= expected[name]:
                raise ValueError(f"Existing {name} keys differ from current PostgreSQL source")
        source_seq_by_key = {_key(row, "rcp_id"): row["rcp_seq"] for row in prepared.source.recipes}
        for row in rows["rcp"]:
            if source_seq_by_key[_key(row, "rcp_id")] != row["rcp_seq"]:
                raise ValueError("Existing recipe key has a different source rcp_seq")
        return inspection

    # =========================================================
    # Neo4j 배치 적재와 원천 대조
    # =========================================================
    def apply(self, prepared: PreparedGraph, batch_size: int = 500) -> dict:
        """제약조건을 확인하고 노드 3종, 관계 2종, 조리 단계(노드+관계) 순서로 배치 적재·검증한다.

        PostgreSQL 등록의 단일 트랜잭션과 달리 Neo4j는 write_batch()마다 확정된다.
        중간 오류 후 재실행은 MERGE와 사전 점검을 전제로 한다.
        """
        if batch_size < 1 or batch_size > 1000:
            raise ValueError("batch_size must be between 1 and 1000")
        before = self.preflight_graph(prepared)
        self.graph.explain_load_statements()
        self.graph.create_schema()
        self._check_schema_names(self.graph.inspect(), require_all=True)
        completed: dict[str, int] = {}
        try:
            for statement, stage, check in STAGES:
                rows = prepared.stages[stage]
                completed[statement] = 0
                for start in range(0, len(rows), batch_size):
                    batch = rows[start:start + batch_size]
                    self.graph.write_batch(statement, batch, check)
                    completed[statement] += len(batch)
            verified = self.verify(prepared)
            return {"before_nodes": before["total_nodes"], "before_relationships": before["total_relationships"],
                    "completed": completed, "verified": verified}
        except Exception as error:
            raise RuntimeError(f"Graph load incomplete; committed batches={completed}; error={error}") from error

    def verify(self, prepared: PreparedGraph) -> dict:
        """Neo4j 키 집합과 건수를 원천 스냅샷과 비교한다(읽기 전용)."""
        expected = self._expected_sets(prepared)
        rows = self.graph.project_rows()
        actual = self._actual_sets(rows)
        counts = self.graph.project_counts()
        for name, expected_keys in expected.items():
            if counts[name] != len(expected_keys) or len(rows[name]) != counts[name] or actual[name] != expected_keys:
                raise ValueError(f"Graph count/key mismatch: {name}: actual={counts[name]}, expected={len(expected_keys)}")
        category_errors = self.graph.validation_count("category_errors")
        if category_errors:
            raise ValueError("Recipe without category relationship")
        unlinked = self.graph.validation_count("unlinked_recipe_count")
        expected_unlinked = len(expected["rcp"] - {(key[0],) for key in expected["RCP_USES"]})
        if unlinked != expected_unlinked:
            raise ValueError("Unlinked recipe count mismatch")
        step_link_errors = self.graph.validation_count("step_link_errors")
        if step_link_errors:
            raise ValueError("Recipe step without exactly one owning recipe")
        return {**counts, "total_project_nodes": sum(counts[k] for k in ("rcp_cat", "ingr", "rcp", "rcp_step")),
                "total_project_relationships": sum(
                    counts[k] for k in ("RCP_IN_RECIPE_CATEGORY", "RCP_USES", "RCP_HAS_STEP")),
                "unlinked_recipes": unlinked, "category_errors": category_errors,
                "step_link_errors": step_link_errors}

    # =========================================================
    # 대표 조회 및 검색 시나리오 검증
    # =========================================================
    def verify_examples(self, prepared: PreparedGraph) -> dict:
        """대표 레시피·재료의 그래프 조회값을 준비된 원천과 대조한다."""
        source = prepared.source
        counts_by_recipe = {}
        counts_by_ingredient = {}
        for row in source.uses:
            counts_by_recipe[row["rcp_id"]] = counts_by_recipe.get(row["rcp_id"], 0) + 1
            counts_by_ingredient[row["ingr_id"]] = counts_by_ingredient.get(row["ingr_id"], 0) + 1
        results = {}
        for seq in ("28", "298", "536", "788", "919"):
            source_rows = [row for row in source.recipes if row["rcp_seq"] == seq]
            if len(source_rows) != 1:
                results[seq] = {"source_matches": len(source_rows)}
                continue
            rcp_id = source_rows[0]["rcp_id"]
            actual = self.graph.sample_recipe(rcp_id)
            if len(actual) != 1 or actual[0]["rcp_seq"] != seq or actual[0]["ingredient_count"] != counts_by_recipe.get(rcp_id, 0):
                raise ValueError(f"Representative recipe mismatch: rcp_seq={seq}")
            results[seq] = {**actual[0], "source_ingredient_count": counts_by_recipe.get(rcp_id, 0)}
        for a, b in (("298", "536"), ("788", "919")):
            if a in results and b in results and "rcp_nm" in results[a] and "rcp_nm" in results[b]:
                results[f"{a}_{b}_pair"] = {
                    "distinct_source_ids": a != b,
                    "same_name": results[a]["rcp_nm"] == results[b]["rcp_nm"],
                }
        results["cocktail_shrimp"] = []
        for row in (row for row in source.ingredients if row["ingr_nm"] == "칵테일새우"):
            actual = self.graph.sample_ingredient(row["ingr_id"])
            if len(actual) != 1 or actual[0]["recipe_count"] != counts_by_ingredient.get(row["ingr_id"], 0):
                raise ValueError("Cocktail shrimp source/graph relationship mismatch")
            results["cocktail_shrimp"].append({**actual[0], "ingr_id": row["ingr_id"]})
        return results

    def verify_query_examples(self, prepared: PreparedGraph) -> dict:
        """추천 조회용 Named Cypher의 결과 예시를 원천과 대조한다."""
        source = prepared.source
        recipe = next(row for row in source.recipes if row["rcp_seq"] == "28")
        rcp_id = recipe["rcp_id"]
        uses = [row for row in source.uses if row["rcp_id"] == rcp_id]
        ingredient_by_key = {row["ingr_id"]: row for row in source.ingredients}
        pantry_names = [normalize_name(ingredient_by_key[row["ingr_id"]]["ingr_nm"]) for row in uses[:3]]
        category_ids = sorted(row["rcp_cat_id"] for row in source.recipe_category_links if row["rcp_id"] == rcp_id)
        category_name = next(row["rcp_cat_nm"] for row in source.recipe_categories if row["rcp_cat_id"] == category_ids[0])
        shrimp = next(row for row in source.ingredients if row["ingr_nm"] == "칵테일새우")
        expected_shrimp_uses = sum(row["ingr_id"] == shrimp["ingr_id"] for row in source.uses)
        key_params = {"rcp_id": rcp_id}
        found = self.graph.query_example("find_recipe_by_name", {"rcp_nm": recipe["rcp_nm"]})
        ingredients = self.graph.query_example("recipe_ingredients", key_params)
        using_shrimp = self.graph.query_example("recipes_using_ingredient", {
            "ingr_id": shrimp["ingr_id"], "exclude_rcp_id": None,
        })
        similar = self.graph.query_example("similar_recipes", key_params)
        candidates = self.graph.query_example("ingredient_name_candidates", {
            "term_norm": normalize_name(shrimp["ingr_nm"]),
        })
        pantry = self.graph.query_example("pantry_recommendations", {"names_norm": pantry_names})
        category = self.graph.query_example("category_and_ingredient", {
            "rcp_cat_nm": category_name, "term_norm": pantry_names[0],
        })
        context = self.graph.query_example("graphrag_context", key_params)
        steps = self.graph.query_example("recipe_steps", {"rcp_ids": [rcp_id]})
        expected_steps = [
            (row["step_no"], row["rcp_step_instruction_txt"], row["rcp_step_image_url"])
            for row in prepared.stages["steps"] if row["rcp_id"] == rcp_id
        ]
        if not any(row["rcp_seq"] == "28" for row in found):
            raise ValueError("Recipe name query lost recipe 28")
        if len(ingredients) != 1 or len(ingredients[0]["ingredients"]) != len(uses):
            raise ValueError("Recipe ingredients query differs from PostgreSQL")
        if len(using_shrimp) != expected_shrimp_uses:
            raise ValueError("Cocktail shrimp query differs from PostgreSQL")
        if not similar or not all(0 < row["jaccard"] <= 1 for row in similar):
            raise ValueError("Similar recipe query returned invalid Jaccard results")
        if not any(row["ingr_id"] == shrimp["ingr_id"] for row in candidates):
            raise ValueError("Ingredient name query lost cocktail shrimp")
        if not pantry or not category or len(context) != 1:
            raise ValueError("Pantry, category, or GraphRAG context query returned no result")
        if len(context[0]["context"]["ingredients"]) != len(uses):
            raise ValueError("GraphRAG context ingredients differ from PostgreSQL")
        if len(context[0]["context"]["categories"]) != len(category_ids):
            raise ValueError("GraphRAG context categories differ from PostgreSQL")
        if context[0]["context"].get("image_url") != recipe["rcp_image_url"]:
            raise ValueError("GraphRAG context image URL differs from PostgreSQL")
        # 원본 순서·설명·이미지 URL이 PostgreSQL rcp_step과 글자 단위로 같아야 한다.
        if [(row["step_no"], row["instruction_txt"], row["image_url"]) for row in steps] != expected_steps:
            raise ValueError("Recipe steps query differs from PostgreSQL rcp_step")
        return {
            "find_recipe_by_name": len(found), "recipe_ingredients": len(ingredients[0]["ingredients"]),
            "recipes_using_ingredient": len(using_shrimp), "similar_recipes": len(similar),
            "ingredient_name_candidates": len(candidates), "pantry_recommendations": len(pantry),
            "category_and_ingredient": len(category), "graphrag_context": len(context),
            "recipe_steps": len(steps),
        }

    def verify_search_scenarios(self, prepared: PreparedGraph, *, pantry_terms=("계란", "두부", "양파"),
                                both_terms=("계란", "두부"), category_name="반찬") -> dict:
        """식재료 기반 검색 질의 결과를 같은 PostgreSQL 스냅샷에서 계산한 기대값과 비교한다(읽기 전용).

        입력어는 표준명·별칭 정규화 규칙으로 식재료 ID에 해석한다. 별칭 '계란' → 표준 '달걀' 매핑도 여기서 확인된다.
        """
        source = prepared.source
        names = {row["ingr_id"]: {normalize_name(row["ingr_nm"])} for row in source.ingredients}
        for row in source.aliases:
            names[row["ingr_id"]].add(normalize_name(row["ingr_als_nm"]))
        recipes_by_ingredient: dict[str, set[str]] = {}
        ingredients_by_recipe: dict[str, set[str]] = {}
        for row in source.uses:
            recipes_by_ingredient.setdefault(row["ingr_id"], set()).add(row["rcp_id"])
            ingredients_by_recipe.setdefault(row["rcp_id"], set()).add(row["ingr_id"])

        def resolve(term: str) -> set[str]:
            """원천 표준명·별칭 사전에서 입력어와 일치하는 식재료 ID를 찾는다."""
            return {ingr_id for ingr_id, values in names.items() if normalize_name(term) in values}

        def recipes_for(term: str) -> set[str]:
            """검증 예시의 재료에 연결된 레시피를 조회한다."""
            return set().union(*(recipes_by_ingredient.get(ingr_id, set()) for ingr_id in resolve(term)))

        results = {}
        for term in sorted({*pantry_terms, *both_terms}):
            rows = self.graph.query_example("recipes_by_ingredient_term", {"term_norm": normalize_name(term)})
            actual = {row["rcp_id"] for row in rows}
            if len(rows) != len(actual) or actual != recipes_for(term) or not actual:
                raise ValueError(f"Ingredient search mismatch for '{term}'")
            results[f"by_term:{term}"] = {"ingredients": sorted({row["ingredient"] for row in rows}),
                                          "recipes": len(actual)}

        expected_both = set.intersection(*(recipes_for(term) for term in both_terms))
        rows = self.graph.query_example("recipes_with_all_ingredients",
                                        {"terms_norm": [normalize_name(term) for term in both_terms]})
        if {row["rcp_id"] for row in rows} != expected_both or len(rows) != len(expected_both):
            raise ValueError("All-ingredient search mismatch")
        results["all:" + "+".join(both_terms)] = {"recipes": len(rows), "sample": [row["rcp_nm"] for row in rows[:5]]}

        owned = set().union(*(resolve(term) for term in pantry_terms))
        rows = self.graph.query_example("pantry_recommendations",
                                        {"names_norm": [normalize_name(term) for term in pantry_terms]})
        candidates = {rcp_id: (len(ingredients & owned), len(ingredients - owned))
                      for rcp_id, ingredients in ingredients_by_recipe.items() if ingredients & owned}
        if not rows or any(candidates.get(row["rcp_id"]) != (row["matched_count"], row["missing_count"]) for row in rows):
            raise ValueError("Pantry recommendation counts differ from PostgreSQL")
        if rows[0]["missing_count"] != min(missing for _, missing in candidates.values()):
            raise ValueError("Pantry recommendation order is not by fewest missing ingredients")
        results["pantry:" + "+".join(pantry_terms)] = {
            "candidates": len(candidates), "returned": len(rows),
            "top": [(row["rcp_nm"], row["matched_count"], row["missing_count"]) for row in rows[:3]],
        }

        category_ids = {row["rcp_cat_id"] for row in source.recipe_categories if row["rcp_cat_nm"] == category_name}
        expected_category = {row["rcp_id"] for row in source.recipe_category_links if row["rcp_cat_id"] in category_ids}
        rows = self.graph.query_example("recipes_in_category", {"rcp_cat_nm": category_name})
        if {row["rcp_id"] for row in rows} != expected_category or len(rows) != len(expected_category):
            raise ValueError("Category search mismatch")
        results[f"category:{category_name}"] = {"recipes": len(rows)}
        return results

# endregion
