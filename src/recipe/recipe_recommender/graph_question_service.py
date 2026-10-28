"""그래프 관계 탐색 Service — 과제 질문 Q1~Q5를 고정 Named Cypher로 답한다 (Neo4j 읽기 전용, LLM 없음).

Streamlit 모드 B(그래프 관계 탐색)가 사용한다. 자연어를 Cypher로 바꾸지 않는다. 질문 5개마다
정해 둔 파라미터화 쿼리만 실행하고, 사용자는 질문과 파라미터(식재료·레시피·분류)만 고른다.

    Q1 1-hop  (ingr)<-[:RCP_USES]-(rcp)                                    recipe_graph_queries.recipes_by_ingredient_term
    Q2 2-hop  (rcp)-[:RCP_USES]->(ingr)<-[:RCP_USES]-(rcp)                  recipe_graph_queries.similar_recipes
    Q3 3-hop  (rcp)-[:RCP_USES]->(ingr)<-[:RCP_USES]-(rcp)-[:RCP_IN_RECIPE_CATEGORY]->(rcp_cat)
                                                                           graph_questions.similar_recipe_categories
    Q4 2-hop  (rcp_cat)<-[:RCP_IN_RECIPE_CATEGORY]-(rcp)-[:RCP_USES]->(ingr) graph_questions.category_ingredients
    Q5 1-hop  (rcp)-[:RCP_HAS_STEP]->(rcp_step)                             recipe_graph_queries.recipe_steps

Hop은 Neo4j 관계를 건너가는 횟수다. 식재료 이름·별칭 해석(``ingredient_name_candidates``)은 노드 속성 비교라
hop에 넣지 않는다. 화면의 표는 모두 Neo4j 조회값 그대로이며 이 Service는 순서·건수를 바꾸지 않는다
(Q1만 같은 레시피가 두 번 나오지 않도록 ``rcp_id`` 기준 중복을 한 번 더 제거한다).
DB 예외는 잡지 않고 호출자(화면)에 전달한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .name_normalization import normalize_name
from .pantry_graphrag import josa, josa_ro

# region 1. 질문 정의와 화면용 결과 모델
# =========================================================
# 질문별 허용 Cypher와 결과 구조
# =========================================================
# 이 Service가 실행하는 Named Cypher. 모두 MATCH/RETURN만 있는 읽기 전용 쿼리다(테스트로 확인).
ALLOWED_STATEMENTS = (
    "recipe_graph_queries.ingredient_name_candidates",
    "recipe_graph_queries.recipes_by_ingredient_term",
    "recipe_graph_queries.similar_recipes",
    "recipe_graph_queries.recipe_steps",
    "graph_questions.recipe_options",
    "graph_questions.category_options",
    "graph_questions.similar_recipe_categories",
    "graph_questions.category_ingredients",
)
DEFAULT_MIN_COMMON = 3          # Q3 공통 재료 최소 개수: 1이면 '설탕'·'소금'처럼 흔한 재료 하나로 거의 모든 분류가 잡힌다
DEFAULT_INGREDIENT_LIMIT = 20   # Q4 상위 식재료 수
MAX_INGREDIENT_LIMIT = 50


@dataclass(frozen=True)
class GraphQuestion:
    """화면에 보여 줄 과제 질문 한 개의 정의(질문·hop·관계 경로·실행 Cypher)."""

    key: str  # 'Q1'~'Q5'; 화면 선택과 테스트의 식별자.
    hop: int  # 패턴이 건너가는 관계 수.
    title: str  # 선택지에 보이는 짧은 이름.
    question: str  # 자연어 질문 형식; ``{target}``·``{eul}``(을/를)·``{gwa}``(과/와)·``{ro}``((으)로) 자리에 대상 이름을 넣는다.
    path: str  # 실제 Cypher 관계 경로.
    statement: str  # 실행하는 Named Cypher(``namespace.name``).
    parameter: str  # 필요한 입력: 'ingredient' | 'recipe' | 'category'.

    def text(self, target: str) -> str:
        """대상 이름을 넣고 받침에 맞는 조사를 붙인 자연어 질문을 만든다."""
        return self.question.format(target=target, eul=josa(target, "을", "를"),
                                    gwa=josa(target, "과", "와"), ro=josa_ro(target))


QUESTIONS: dict[str, GraphQuestion] = {q.key: q for q in (
    GraphQuestion("Q1", 1, "식재료를 사용하는 레시피", "{eul} 사용하는 레시피는 무엇인가?",
                  "(:ingr)<-[:RCP_USES]-(:rcp)", "recipe_graph_queries.recipes_by_ingredient_term", "ingredient"),
    GraphQuestion("Q2", 2, "공통 재료를 쓰는 다른 레시피", "{gwa} 공통 재료를 사용하는 다른 레시피는 무엇인가?",
                  "(:rcp)-[:RCP_USES]->(:ingr)<-[:RCP_USES]-(:rcp)", "recipe_graph_queries.similar_recipes", "recipe"),
    GraphQuestion("Q3", 3, "공통 재료 레시피들의 요리 분류",
                  "{gwa} 공통 재료를 사용하는 다른 레시피들은 어떤 요리 분류에 속하는가?",
                  "(:rcp)-[:RCP_USES]->(:ingr)<-[:RCP_USES]-(:rcp)-[:RCP_IN_RECIPE_CATEGORY]->(:rcp_cat)",
                  "graph_questions.similar_recipe_categories", "recipe"),
    GraphQuestion("Q4", 2, "분류의 레시피가 쓰는 식재료", "{ro} 분류된 레시피에서 사용하는 식재료는 무엇인가?",
                  "(:rcp_cat)<-[:RCP_IN_RECIPE_CATEGORY]-(:rcp)-[:RCP_USES]->(:ingr)",
                  "graph_questions.category_ingredients", "category"),
    GraphQuestion("Q5", 1, "레시피의 조리 단계", "{target}의 조리 단계와 순서는 무엇인가?",
                  "(:rcp)-[:RCP_HAS_STEP]->(:rcp_step)", "recipe_graph_queries.recipe_steps", "recipe"),
)}


@dataclass
class GraphAnswer:
    """질문 한 번의 Neo4j 조회 결과. ``rows`` 는 Cypher 반환 행 그대로(Q1만 중복 제거)."""

    question: GraphQuestion  # 실행한 질문 정의.
    question_text: str  # 파라미터를 채운 자연어 질문.
    parameters: dict  # Cypher에 전달한 바인딩 값.
    status: str  # 'ok'(1건 이상) | 'empty'(0건) | 'not_found'(입력한 식재료·레시피·분류가 DB에 없음)
    rows: list[dict] = field(default_factory=list)  # 표로 보여 줄 조회 행.
    message: str | None = None  # 'empty'·'not_found'·해석 결과 안내 문장.
    resolved: list[dict] = field(default_factory=list)  # Q1 입력어 해석 결과 [{ingr_id, ingr_nm, matched_by}].

    @property
    def row_count(self) -> int:
        """조회 결과 행 수."""
        return len(self.rows)


# endregion
# region 2. 그래프 질문 조회 Service
# =========================================================
# 선택지 캐시와 Q1~Q5 Neo4j 조회
# =========================================================
class GraphQuestionService:
    """과제 질문 Q1~Q5를 허용된 읽기 전용 Named Cypher로 실행한다.

    ``streamlit_app.get_graph_question_service`` 가 기존 ``RecipeGraphRepository`` 를 주입해 만든다.
    레시피·분류 선택지는 인스턴스에 한 번만 조회해 둔다.
    """

    def __init__(self, graph):
        """``graph`` 는 ``RecipeGraphRepository`` (또는 같은 ``query_example`` / ``mapper`` 를 가진 객체)."""
        self.graph = graph
        self._recipes: list[dict] | None = None
        self._categories: list[dict] | None = None

    def _query(self, statement: str, parameters: dict) -> list[dict]:
        """허용된 Named Cypher만 namespace에 맞는 조회 API로 실행한다.

        Args:
            statement (str): ``namespace.name`` 형식의 쿼리 식별자.
            parameters (dict): Cypher 바인딩 값.

        Returns:
            list[dict]: 그래프 조회 행 목록.

        Raises:
            ValueError: 읽기 허용 목록에 없는 식별자일 때.
        """
        if statement not in ALLOWED_STATEMENTS:
            raise ValueError(f"Statement is not allowed in the read-only graph question service: {statement}")
        namespace, name = statement.split(".", 1)
        if namespace == "recipe_graph_queries":
            # Repository의 query_example은 같은 이름의 Named Cypher를 Neo4jDbSession에 전달한다.
            return self.graph.query_example(name, parameters)
        return self.graph.mapper.select_list(statement, parameters)

    def cypher_text(self, key: str) -> str:
        """질문이 실행하는 Cypher 원문(화면의 '실행 Cypher' 표시용)."""
        return self.graph.statement_text(QUESTIONS[key].statement)

    def recipe_options(self) -> list[dict]:
        """``[{rcp_id, rcp_nm, rcp_seq}]`` 레시피 선택지(이름·원본 번호 순, 한 번만 조회)."""
        if self._recipes is None:
            self._recipes = self._query("graph_questions.recipe_options", {})
        return self._recipes

    def category_options(self) -> list[dict]:
        """``[{rcp_cat_id, rcp_cat_nm}]`` 요리 분류 선택지(한 번만 조회)."""
        if self._categories is None:
            self._categories = self._query("graph_questions.category_options", {})
        return self._categories

    def _recipe(self, rcp_id: str) -> dict | None:
        """선택지에서 레시피 한 건을 찾는다. 없으면 ``None``."""
        return next((row for row in self.recipe_options() if row["rcp_id"] == rcp_id), None)

    @staticmethod
    def _answer(key: str, target: str, parameters: dict, rows: list[dict], empty_message: str) -> GraphAnswer:
        """조회 행으로 ``GraphAnswer`` 를 만든다. 0건이면 ``status='empty'`` 와 안내 문장을 둔다."""
        question = QUESTIONS[key]
        return GraphAnswer(question=question, question_text=question.text(target),
                           parameters=parameters, status="ok" if rows else "empty", rows=rows,
                           message=None if rows else empty_message)

    @staticmethod
    def _not_found(key: str, target: str, parameters: dict, message: str) -> GraphAnswer:
        """입력한 대상이 DB에 없을 때의 ``GraphAnswer`` (쿼리를 실행하지 않음)."""
        question = QUESTIONS[key]
        return GraphAnswer(question=question, question_text=question.text(target),
                           parameters=parameters, status="not_found", message=message)

    def recipes_using_ingredient(self, term: str) -> GraphAnswer:
        """Q1 (1-hop) 입력한 식재료(표준명 또는 별칭)를 사용하는 레시피 전체.

        입력어를 ETL과 같은 규칙(``normalize_name``)으로 정규화해 ``ingredient_name_candidates`` 로 먼저 해석한다.
        해석되지 않으면 레시피 쿼리를 실행하지 않고 ``not_found`` 를 반환한다.

        Args:
            term (str): 사용자가 입력한 식재료명(예: '두부', 별칭 '계란').

        Returns:
            GraphAnswer: 행 ``{ingr_id, ingredient, rcp_id, rcp_seq, rcp_nm}`` (레시피명·ID 순, 레시피 중복 없음).
        """
        term = (term or "").strip()
        term_norm = normalize_name(term)
        parameters = {"term_norm": term_norm}
        if not term_norm:
            return self._not_found("Q1", term or "(빈 입력)", parameters, "식재료 이름을 입력하세요.")
        candidates = self._query("recipe_graph_queries.ingredient_name_candidates", parameters)
        if not candidates:
            return self._not_found("Q1", term, parameters,
                                   f"'{term}'은(는) DB의 표준 식재료명·별칭에 없습니다(정확히 일치하는 이름만 찾습니다).")
        resolved = [{"ingr_id": row["ingr_id"], "ingr_nm": row["ingr_nm"],
                     "matched_by": "name" if normalize_name(row["ingr_nm"]) == term_norm else "alias"}
                    for row in candidates]
        rows, seen = [], set()
        for row in self._query("recipe_graph_queries.recipes_by_ingredient_term", parameters):
            if row["rcp_id"] not in seen:            # 한 입력어가 여러 식재료에 걸려도 레시피는 한 번만
                seen.add(row["rcp_id"])
                rows.append(row)
        answer = self._answer("Q1", term, parameters, rows, f"'{term}'을(를) 사용하는 레시피가 없습니다.")
        answer.resolved = resolved
        aliases = [item["ingr_nm"] for item in resolved if item["matched_by"] == "alias"]
        if aliases:
            answer.message = f"'{term}'은(는) 별칭이라 표준 식재료 {aliases}로 조회했습니다."
        return answer

    def similar_recipes(self, rcp_id: str) -> GraphAnswer:
        """Q2 (2-hop) 기준 레시피와 공통 재료를 쓰는 다른 레시피(공통 재료 수·Jaccard 상위 20개).

        Args:
            rcp_id (str): 기준 레시피 ID.

        Returns:
            GraphAnswer: 행 ``{rcp_id, rcp_nm, common_count, common_ingredients, jaccard}``.
        """
        recipe, parameters = self._recipe(rcp_id), {"rcp_id": rcp_id}
        if recipe is None:
            return self._not_found("Q2", rcp_id or "(빈 입력)", parameters, "선택한 레시피가 DB에 없습니다.")
        rows = self._query("recipe_graph_queries.similar_recipes", parameters)
        return self._answer("Q2", recipe["rcp_nm"], parameters, rows,
                            f"'{recipe['rcp_nm']}'와(과) 재료를 함께 쓰는 다른 레시피가 없습니다.")

    def similar_recipe_categories(self, rcp_id: str, min_common: int = DEFAULT_MIN_COMMON) -> GraphAnswer:
        """Q3 (3-hop) 공통 재료가 ``min_common`` 개 이상인 다른 레시피들의 요리 분류별 레시피 수.

        Args:
            rcp_id (str): 기준 레시피 ID.
            min_common (int): 공통 재료 최소 개수(1 이상).

        Returns:
            GraphAnswer: 행 ``{rcp_cat_nm, recipe_count, max_common_count, sample_recipes}``.
        """
        min_common = max(1, int(min_common))
        recipe, parameters = self._recipe(rcp_id), {"rcp_id": rcp_id, "min_common": min_common}
        if recipe is None:
            return self._not_found("Q3", rcp_id or "(빈 입력)", parameters, "선택한 레시피가 DB에 없습니다.")
        rows = self._query("graph_questions.similar_recipe_categories", parameters)
        return self._answer("Q3", recipe["rcp_nm"], parameters, rows,
                            f"'{recipe['rcp_nm']}'와(과) 공통 재료가 {min_common}개 이상인 다른 레시피가 없습니다.")

    def category_ingredients(self, rcp_cat_nm: str, limit: int = DEFAULT_INGREDIENT_LIMIT) -> GraphAnswer:
        """Q4 (2-hop) 요리 분류에 속한 레시피들이 사용하는 식재료(사용 레시피 수 상위 ``limit`` 개).

        Args:
            rcp_cat_nm (str): 요리 분류명(예: '반찬').
            limit (int): 반환할 식재료 수(1~50).

        Returns:
            GraphAnswer: 행 ``{ingr_nm, recipe_count, category_recipe_count, category_ingredient_count}``.
        """
        limit = min(max(1, int(limit)), MAX_INGREDIENT_LIMIT)
        parameters = {"rcp_cat_nm": rcp_cat_nm, "limit": limit}
        if rcp_cat_nm not in {row["rcp_cat_nm"] for row in self.category_options()}:
            return self._not_found("Q4", rcp_cat_nm or "(빈 입력)", parameters, "선택한 요리 분류가 DB에 없습니다.")
        rows = self._query("graph_questions.category_ingredients", parameters)
        return self._answer("Q4", rcp_cat_nm, parameters, rows, f"'{rcp_cat_nm}' 분류의 레시피가 쓰는 식재료가 없습니다.")

    def recipe_steps(self, rcp_id: str) -> GraphAnswer:
        """Q5 (1-hop) 레시피의 식약처 원본 조리 단계(원본 MANUAL 번호 순).

        Args:
            rcp_id (str): 레시피 ID.

        Returns:
            GraphAnswer: 행 ``{rcp_id, step_no, instruction_txt, image_url}``.
        """
        recipe, parameters = self._recipe(rcp_id), {"rcp_ids": [rcp_id]}
        if recipe is None:
            return self._not_found("Q5", rcp_id or "(빈 입력)", parameters, "선택한 레시피가 DB에 없습니다.")
        rows = self._query("recipe_graph_queries.recipe_steps", parameters)
        return self._answer("Q5", recipe["rcp_nm"], parameters, rows, f"'{recipe['rcp_nm']}'의 조리 단계 데이터가 없습니다.")

# endregion
