"""냉장고 재료 기반 레시피 추천 Service (Neo4j 읽기 전용, LLM 없음).

기존 Named Cypher를 그대로 재사용한다.
    recipe_graph_queries.ingredient_name_candidates  입력어 → 표준 식재료(표준명·별칭 정확 일치)
    recipe_graph_queries.pantry_recommendations      보유 재료로 만들 수 있는 레시피 + 사용/부족 재료
    recipe_graph_queries.graphrag_context            레시피별 분류·조리 방법·열량 등 LLM 근거(+화면용 대표 이미지 URL)
    recipe_graph_queries.recipe_steps                추천 레시피의 식약처 원본 조리 과정(번호·설명·단계 이미지 URL)
    pantry_graphrag.ingredient_vocabulary            LLM 답변 검증용 식재료 어휘

추천 순서(``sort``):
    coverage  보유 재료를 많이 쓰는 순 — pantry_graphrag.pantry_recommendations_by_coverage(같은 매칭, 정렬만 다름)
    missing   부족 재료가 적은 순     — 기존 recipe_graph_queries.pantry_recommendations 그대로
화면에 보여 주는 레시피·재료는 모두 이 Service가 Neo4j에서 조회한 값이며, LLM은 설명 문장만 만든다.
대표 이미지·조리 과정은 추천 목록이 정해진 뒤 붙이는 표시용 데이터라 추천 순서·LLM 근거에 영향을 주지 않는다.
조리 과정 조회가 실패해도 추천은 그대로 반환하고 ``PantryResult.step_error`` 에 사유를 남긴다.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from urllib.parse import urlsplit

from .name_normalization import normalize_name

# region 1. 허용 쿼리와 추천 규칙
logger = logging.getLogger("recipe_recommender.pantry_recommend_service")

# 이 Service가 실행하는 Named Cypher. 모두 MATCH/RETURN만 있는 읽기 전용 쿼리다(테스트로 확인).
ALLOWED_STATEMENTS = (
    "recipe_graph_queries.ingredient_name_candidates",
    "recipe_graph_queries.pantry_recommendations",
    "recipe_graph_queries.graphrag_context",
    "pantry_graphrag.ingredient_vocabulary",
    "pantry_graphrag.pantry_recommendations_by_coverage",
    "recipe_graph_queries.recipe_steps",
)
SORT_STATEMENTS = {
    "coverage": ("pantry_graphrag.pantry_recommendations_by_coverage", "보유 재료를 많이 쓰는 순"),
    "missing": ("recipe_graph_queries.pantry_recommendations", "부족 재료가 적은 순"),
}
MAX_RECOMMENDATIONS = 20                     # 두 쿼리 모두 최대 20건
# 쉼표·줄바꿈·슬래시 등 구분자로만 나눈다. 공백은 나누지 않는다('다진 마늘'처럼 띄어쓰기가 있는 표준명이 있다).
_TERM_SEPARATORS = re.compile(r"[,，、;/\n\r\t·|+]+")
MAX_TERMS = 20
# 식약처 이미지 서버는 http 요청을 같은 경로의 https로 302 리다이렉트한다(2026-10-24 확인).
# HTTPS로 서비스되는 Streamlit Cloud에서 혼합 콘텐츠로 차단되지 않게 이 호스트만 https로 바꿔 표시한다.
HTTPS_UPGRADE_HOSTS = frozenset({"www.foodsafetykorea.go.kr", "foodsafetykorea.go.kr"})


# endregion
# region 2. 입력어와 이미지 URL 변환
def split_terms(text: str) -> list[str]:
    """``'계란, 두부, 양파'`` → ``['계란', '두부', '양파']``. 중복(정규화 기준)은 처음 것만 남긴다."""
    seen, terms = set(), []
    for part in _TERM_SEPARATORS.split(text or ""):
        term = part.strip()
        if term and normalize_name(term) not in seen:
            seen.add(normalize_name(term))
            terms.append(term)
    return terms[:MAX_TERMS]


def display_image_url(url: str | None) -> str | None:
    """식약처 이미지 URL을 화면에 표시할 수 있는 형태로 바꾼다. 표시할 수 없으면 ``None``.

    DB 값은 바꾸지 않고 화면 표시 직전에만 사용한다.
        - 비었거나 http/https가 아닌 값(상대 경로·``javascript:`` 등)은 ``None`` → 이미지만 생략
        - ``HTTPS_UPGRADE_HOSTS`` 의 ``http://`` 는 같은 경로의 ``https://`` 로 바꾼다
        - 그 밖의 http/https URL은 그대로 둔다

    Args:
        url (str | None): Neo4j에 적재된 원본 URL.

    Returns:
        str | None: 브라우저에 넘길 URL 또는 생략 표시.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    url = url.strip()
    try:
        parts = urlsplit(url)
    except ValueError:                       # 잘못된 IPv6 표기 등
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.scheme == "http" and parts.hostname.lower() in HTTPS_UPGRADE_HOSTS:
        return "https://" + url[len("http://"):]
    return url


# endregion
# region 3. 추천 결과 DTO
# =========================================================
# 입력 해석·추천·조리 단계 데이터 구조
# =========================================================
# dataclass는 Java DTO와 비슷하게 필드로 초기화되며, to_dict()에서 화면 저장용 dict로 변환된다.
@dataclass
class RecipeStep:
    """식약처 원본 조리 과정 한 단계(MANUAL01~20)의 Neo4j 조회값."""

    step_no: int  # 원본 MANUAL 번호; 중간 번호가 비어 있을 수 있어 화면에도 이 번호를 그대로 쓴다.
    instruction_txt: str  # 원본 조리 설명(LLM이 만들거나 고치지 않는다).
    image_url: str | None = None  # 원본 단계 이미지 URL; 없으면 None.


@dataclass
class TermResolution:
    """입력어 하나의 해석 결과. ``matches`` 가 비면 DB에 없는 재료, 2개 이상이면 모호한 별칭."""

    term: str  # 사용자 원문의 재료명; 화면에서 매칭 전 입력을 보여 준다.
    matches: list[dict] = field(default_factory=list)     # [{ingr_id, ingr_nm, matched_by: 'name'|'alias'}]


@dataclass
class Recommendation:
    """추천 한 건의 Neo4j 조회 근거; ``recommend``가 만들고 화면과 LLM 검증이 읽는다."""

    rcp_id: str  # 그래프의 레시피 ID; LLM 설명과 조회 결과를 연결한다.
    rcp_nm: str  # 화면에 표시할 레시피명.
    rcp_seq: str | None  # 식약처 원본 번호; 근거 조회에 없으면 None.
    categories: list[str]  # 그래프에서 조회한 분류명 목록.
    method: str | None  # 조리 방법; 등록되지 않았으면 None.
    energy_kcal: float | None  # 열량; 등록되지 않았으면 None.
    matched_ingredients: list[str]  # 사용자 보유 재료 중 레시피가 사용하는 표준명.
    missing_ingredients: list[str]  # 레시피에 필요하지만 보유하지 않은 재료명.
    matched_count: int  # 보유 재료 사용 개수; 화면에 표시한다.
    missing_count: int  # 추가 필요 재료 개수; 화면에 표시한다.
    all_ingredients: list[str]  # LLM 설명 검증에 쓰는 전체 재료 근거.
    image_url: str | None = None  # 식약처 대표 이미지 원본 URL(rcp.rcp_image_url); 화면 표시용.
    steps: list[RecipeStep] = field(default_factory=list)  # 원본 번호 순 조리 과정; 그래프에 없으면 빈 목록.


@dataclass
class PantryResult:
    """입력 해석과 추천 목록을 묶어 LangGraph의 ``result``에 담는 DTO."""

    terms: list[str]  # 추천에 사용한 정제 입력어; 입력 순서를 유지한다.
    resolutions: list[TermResolution]  # 입력어별 DB 표준명·별칭 조회 결과.
    recommendations: list[Recommendation]  # 정렬된 추천 목록; 조회 불가 시 빈 목록.
    step_error: str | None = None  # 조리 과정 조회 실패 시 예외 이름; 추천 목록은 그대로 유지된다.

    @property
    def resolved_terms(self) -> list[str]:
        """``@property``로 호출 괄호 없이 읽는, DB에 일치한 원문 입력어 목록."""
        return [r.term for r in self.resolutions if r.matches]

    @property
    def unknown_terms(self) -> list[str]:
        """DB에 일치 항목이 없어 추천 조회에서 제외된 입력어 목록."""
        return [r.term for r in self.resolutions if not r.matches]

    @property
    def owned_ingredients(self) -> list[str]:
        """해석된 표준 식재료명(중복 제거, 입력 순서)."""
        names: list[str] = []
        for resolution in self.resolutions:
            for match in resolution.matches:
                if match["ingr_nm"] not in names:
                    names.append(match["ingr_nm"])
        return names

    def to_dict(self) -> dict:
        """Streamlit Session State 표시용으로 중첩 dataclass를 dict로 변환한다."""
        return {"terms": self.terms, "resolutions": [asdict(r) for r in self.resolutions],
                "recommendations": [asdict(r) for r in self.recommendations], "step_error": self.step_error}


# endregion
# region 4. Neo4j 추천 Service
# =========================================================
# 입력어 해석 → 추천 조회 → 레시피별 근거 → 조리 단계 일괄 조회
# =========================================================
class PantryRecommendService:
    """보유 식재료 → 추천 레시피·사용/부족 재료·근거를 Neo4j에서 조회한다."""

    def __init__(self, graph):
        """``graph`` 는 ``RecipeGraphRepository`` (또는 같은 ``query_example`` 을 가진 객체)."""
        self.graph = graph
        self._vocabulary: list[dict] | None = None

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
            raise ValueError(f"Statement is not allowed in the read-only pantry service: {statement}")
        namespace, name = statement.split(".", 1)
        if namespace == "recipe_graph_queries":
            # Repository가 같은 이름의 Named Cypher를 common.Neo4jDbSession으로 전달한다.
            return self.graph.query_example(name, parameters)
        return self.graph.mapper.select_list(statement, parameters)

    def resolve_terms(self, terms: list[str]) -> list[TermResolution]:
        """입력어마다 표준명 또는 별칭으로 표준 식재료를 찾는다(ETL과 같은 정규화, 정확 일치만)."""
        resolutions = []
        for term in terms:
            term_norm = normalize_name(term)
            rows = self._query("recipe_graph_queries.ingredient_name_candidates", {"term_norm": term_norm})
            resolutions.append(TermResolution(term=term, matches=[{
                "ingr_id": row["ingr_id"], "ingr_nm": row["ingr_nm"],
                "matched_by": "name" if normalize_name(row["ingr_nm"]) == term_norm else "alias",
            } for row in rows]))
        return resolutions

    def recommend(self, terms: list[str], limit: int = 5, sort: str = "coverage") -> PantryResult:
        """입력어를 표준 재료에 매칭하고 추천 및 레시피별 근거를 조회한다.

        매칭된 재료가 없으면 빈 추천 결과를 반환한다. 건수는 1~20으로 제한한다.

        Args:
            terms (list[str]): ``interpret``가 추출한 원문 재료명.
            limit (int): 반환할 추천 개수.
            sort (str): ``coverage`` 또는 ``missing``.

        Returns:
            PantryResult: 매칭 정보와 추천 목록.

        Raises:
            ValueError: 지원하지 않는 정렬 방식일 때.
        """
        if sort not in SORT_STATEMENTS:
            raise ValueError(f"Unknown sort: {sort}")
        limit = min(max(1, limit), MAX_RECOMMENDATIONS)
        terms = [term for term in (t.strip() for t in terms) if term][:MAX_TERMS]
        resolutions = self.resolve_terms(terms)
        names_norm = [normalize_name(r.term) for r in resolutions if r.matches]
        result = PantryResult(terms=terms, resolutions=resolutions, recommendations=[])
        if not names_norm:
            return result
        statement = SORT_STATEMENTS[sort][0]
        rows = self._query(statement, {"names_norm": names_norm, "limit": MAX_RECOMMENDATIONS})
        # 추천 순서가 확정된 뒤 각 레시피의 화면·LLM 근거를 가져온다. 조리 단계는 아래에서 한 번에 읽는다.
        for row in rows[:limit]:
            context_rows = self._query("recipe_graph_queries.graphrag_context", {"rcp_id": row["rcp_id"]})
            context = context_rows[0]["context"] if context_rows else {}
            result.recommendations.append(Recommendation(
                rcp_id=row["rcp_id"], rcp_nm=row["rcp_nm"], rcp_seq=context.get("rcp_seq"),
                categories=sorted(context.get("categories") or []), method=context.get("method"),
                energy_kcal=context.get("energy_kcal"),
                matched_ingredients=sorted(row["matched_ingredients"]),
                missing_ingredients=sorted(row["missing_ingredients"]),
                matched_count=row["matched_count"], missing_count=row["missing_count"],
                all_ingredients=sorted(context.get("ingredients") or []),
                image_url=context.get("image_url"),
            ))
        self._attach_steps(result)
        return result

    def _attach_steps(self, result: PantryResult) -> None:
        """추천이 확정된 레시피에 조리 과정을 한 번의 조회로 붙인다(추천 순서·건수는 바꾸지 않는다).

        조회가 실패하면 모든 레시피의 ``steps`` 를 빈 목록으로 두고 ``result.step_error`` 에
        예외 이름만 기록한다. 조리 과정은 부가 정보이므로 추천 기능 전체를 멈추지 않는다.

        Args:
            result (PantryResult): ``recommend`` 가 만든 추천 결과(제자리에서 갱신).
        """
        if not result.recommendations:
            return
        try:
            rows = self._query("recipe_graph_queries.recipe_steps",
                               {"rcp_ids": [rec.rcp_id for rec in result.recommendations]})
        except Exception as error:                       # 단계 데이터 장애가 추천을 막지 않게 한다
            logger.warning("recipe_steps query failed: %s", type(error).__name__)
            result.step_error = type(error).__name__
            return
        by_recipe: dict[str, list[RecipeStep]] = {}
        for row in rows:
            by_recipe.setdefault(row["rcp_id"], []).append(RecipeStep(
                step_no=row["step_no"], instruction_txt=row["instruction_txt"], image_url=row.get("image_url")))
        for rec in result.recommendations:
            # 쿼리도 정렬하지만, 원본 번호 순서는 화면의 핵심 요구라 여기서 한 번 더 보장한다.
            rec.steps = sorted(by_recipe.get(rec.rcp_id, []), key=lambda step: step.step_no)

    def vocabulary(self) -> list[dict]:
        """``[{ingr_id, ingr_nm, alias_names}]`` 전체 식재료 어휘(한 번만 조회)."""
        if self._vocabulary is None:
            self._vocabulary = self._query("pantry_graphrag.ingredient_vocabulary", {})
        return self._vocabulary

# endregion
