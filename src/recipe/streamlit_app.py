"""냉장고 재료 추천 GraphRAG 웹 화면 (Streamlit).

    로컬:  python -m streamlit run streamlit_app.py      (저장소 루트 .env 사용)
           개발용 SQL/Cypher 터미널 로그: 로컬(.env 있는 PC)은 기본 켜짐(config.LOCAL_DEV_QUERY_LOG_DEFAULT),
           Streamlit Cloud는 기본 꺼짐. 환경변수 RECIPE_QUERY_LOG=0/1이 있으면 그 값이 우선한다.
           개발용 PostgreSQL 진단 버튼: RECIPE_DB_DIAGNOSTIC=1을 명시한 로컬 실행에서만 보인다(Cloud는 항상 차단).
    배포:  Streamlit Community Cloud — 진입 파일 이 파일, Secrets에 .streamlit/secrets.toml.example 항목 입력

흐름: 입력 → PantryGraphRAG(입력 해석 → Neo4j AuraDB 조회 → LLM 추천 이유) → 화면.
레시피·사용/부족 재료는 Neo4j 조회값 그대로이고, LLM은 추천 이유 문장만 만든다.
대표 이미지·조리 과정(MANUAL01~20)·단계 이미지도 식약처 원본을 Neo4j에서 조회해 그대로 보여 준다.
이미지는 브라우저가 식약처 서버에서 직접 받으며, URL이 없거나 형식이 잘못되면 그 이미지만 생략한다.
LLM 설명과 규칙 기반(근거) 대체 설명은 상단 알림과 레시피별 배지로 구분해 보여 준다.
DB는 읽기 전용으로만 조회한다(허용 쿼리 목록: pantry_recommend_service.ALLOWED_STATEMENTS).

화면 상단의 '사용 모드'로 두 기능을 고른다.
    냉장고 재료 추천  위 흐름(모드 A). 기존 화면 그대로.
    그래프 관계 탐색  과제 질문 Q1~Q5(1·2·3-hop)를 고정 Named Cypher로 조회(모드 B, LLM 미사용).
                      허용 쿼리 목록: graph_question_service.ALLOWED_STATEMENTS.
"""

# region 1. import 및 실행 환경 설정
# 이 최상위 영역도 Streamlit의 최초 실행과 위젯 이벤트에 따른 재실행마다 평가된다.
from __future__ import annotations

import atexit
import logging
import os
import re
import sys
from pathlib import Path

import streamlit as st

TASK_DIR = Path(__file__).resolve().parent
# Streamlit은 스크립트를 직접 실행하므로 과제 폴더를 import 검색 경로에 올린다.
if str(TASK_DIR) not in sys.path:
    sys.path.insert(0, str(TASK_DIR))

# Streamlit Secrets → 환경변수. 로컬처럼 secrets.toml이 없으면 저장소 루트 .env를 쓴다(이미 있는 환경변수는 덮어쓰지 않음).
SECRET_NAMES = ("NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE", "NEO4J_TRUSTED_CA_FILE",
                "OPENAI_API_KEY", "OPENAI_MODEL")
try:
    for _name in SECRET_NAMES:
        if _name in st.secrets:
            os.environ.setdefault(_name, str(st.secrets[_name]))
except Exception:            # secrets.toml 없음
    pass

from recipe_recommender.config import (  # noqa: E402
    QUERY_LOG_ON_VALUES, configure_query_logging, is_local_dev, load_project_environment, local_dev_query_log_default,
    query_logging_active,
)
from recipe_recommender.graph_question_service import (  # noqa: E402
    DEFAULT_INGREDIENT_LIMIT, DEFAULT_MIN_COMMON, MAX_INGREDIENT_LIMIT, QUESTIONS, GraphAnswer, GraphQuestionService,
)
from recipe_recommender.pantry_graphrag import DEFAULT_MODEL, PantryGraphRAG, create_llm  # noqa: E402
from recipe_recommender.pantry_recommend_service import (  # noqa: E402
    MAX_RECOMMENDATIONS, SORT_STATEMENTS, PantryRecommendService, display_image_url,
)
from recipe_recommender.tools._connection_util import safe_error  # noqa: E402

load_project_environment()
# 로컬 개발 실행에서만 공통 QueryLogger 출력을 터미널(stderr)로 보낸다. Cloud(.env 없음) 기본값은 꺼짐.
configure_query_logging(default=local_dev_query_log_default())

# endregion
# region 2. 화면 상수와 표시 규칙
DEFAULT_QUESTION = "계란, 두부, 양파"
MISSING_INLINE_LIMIT = 5         # 부족 재료가 이보다 많으면 접어서 보여 준다
RECIPE_IMAGE_WIDTH = 360         # 대표 이미지 폭(px); 좁은 화면에서는 컨테이너 폭으로 줄어든다
# st.markdown이 서식으로 해석하는 문자. 원본 설명의 '*', '~', '$' 등이 굵게·취소선·수식으로 바뀌지 않게 한다.
_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]<>()#+\-.!|~$])")
logger = logging.getLogger("streamlit_app")
MODES = {"pantry": "냉장고 재료 추천", "graph": "그래프 관계 탐색"}
GRAPH_DEFAULT_INGREDIENT = "두부"            # 그래프 탐색 Q1 기본 식재료
GRAPH_DEFAULT_RECIPE = "된장 두부찌개"        # Q2·Q3·Q5 기본 기준 레시피(원본 137번)
GRAPH_DEFAULT_CATEGORY = "반찬"              # Q4 기본 요리 분류
# 그래프 탐색 결과 표의 열: 질문별 (Cypher 반환 키, 화면 열 이름). 목록 값은 쉼표로 이어 보여 준다.
GRAPH_COLUMNS = {
    "Q1": (("rcp_nm", "레시피"), ("rcp_seq", "원본 번호"), ("ingredient", "사용 식재료(표준명)")),
    "Q2": (("rcp_nm", "다른 레시피"), ("common_count", "공통 재료 수"), ("common_ingredients", "공통 재료"),
           ("jaccard", "Jaccard")),
    "Q3": (("rcp_cat_nm", "요리 분류"), ("recipe_count", "레시피 수"), ("max_common_count", "최대 공통 재료 수"),
           ("sample_recipes", "공통 재료가 많은 레시피(최대 5개)")),
    "Q4": (("ingr_nm", "식재료"), ("recipe_count", "사용 레시피 수")),
    "Q5": (("step_no", "단계"), ("instruction_txt", "조리 설명(식약처 원본)"), ("image_url", "단계 이미지")),
}
TERM_SOURCE_LABELS = {
    "rule": "쉼표·줄바꿈 기준으로 나눔",
    "llm": "LLM이 문장에서 재료를 추출(문장에 없는 재료는 제외)",
    "vocabulary": "LLM 없이 문장에서 DB 식재료명·별칭을 찾음",
}

# endregion
# region 3. GraphRAG 파이프라인 생성
# =========================================================
# GraphRAG 파이프라인 생성 및 캐싱
# =========================================================
# Streamlit은 파일을 재실행해도 cache_resource가 반환한 드라이버·Service·그래프 객체를 재사용한다.

@st.cache_resource(show_spinner="Neo4j AuraDB와 LLM 연결을 준비하는 중입니다...")
def get_pipeline():
    """화면 재실행 사이에 재사용할 GraphRAG 파이프라인을 생성한다.

    Streamlit은 위젯 조작 때 스크립트 전체를 재실행한다. ``cache_resource``는
    Neo4j 드라이버와 Service를 다시 만들지 않도록 객체를 공유한다.

    Returns:
        PantryGraphRAG: 연결 검증을 마친 추천 파이프라인.

    Raises:
        Exception: Neo4j 연결 검증 또는 의존 객체 생성에 실패하면 화면으로 전파한다.
    """
    from recipe_recommender.recipe_graph_repository import RecipeGraphRepository

    graph = RecipeGraphRepository()
    graph.driver.verify_connectivity()
    # Repository → 추천 Service → LangGraph 순으로 조립한다. LLM 키가 없으면 create_llm()은 None이다.
    return PantryGraphRAG(PantryRecommendService(graph), create_llm())


# endregion
# region 4. PostgreSQL 개발용 로그 검증
# =========================================================
# PostgreSQL 개발용 로그 검증 (모드 A 추천 버튼에서 로컬 로그 켜짐일 때 SELECT 4건 실행)
# =========================================================
# 실행 흐름 가시성을 위해 다시 켰다(추천 지연이 늘어난다). 필요성·성능 판단은 소스 분석 단계에서 한다.
@st.cache_resource(show_spinner=False)
def get_log_check_search_service():
    """로그 검증 모드 전용 PostgreSQL 조회 Service를 한 번만 만든다.

    호출 경로: ``RecipeSearchService`` → ``RecipeRepository`` → ``PostgresDbSession`` (Named SQL ``recipe.sql``).
    ``create_recipe_sql_session()`` 은 ``sql_log`` 를 생략하므로 이 프로세스의 로그 결정(켜짐)을 따라 combined
    SQL 로그를 남긴다. 세션의 ``DatabaseManager`` pool은 첫 조회 때 생기고, 프로세스 종료 시 ``atexit`` 로 닫는다.

    Returns:
        RecipeSearchService: 읽기 전용 조회 Service.
    """
    from recipe_recommender.database import create_recipe_sql_session
    from recipe_recommender.recipe_search_service import RecipeSearchService

    session = create_recipe_sql_session()
    atexit.register(session.database_manager.close)
    return RecipeSearchService(sql_session=session)


def run_postgres_log_check(outcome: dict) -> None:
    """로컬 로그 검증 모드에서만 첫 추천 레시피를 PostgreSQL에서 읽기 전용으로 다시 조회한다.

    공통 SQL 로그(``PostgresDbSession`` → ``mogrify``)를 실제 앱 경로에서 확인하기 위한 조회다. 결과는 화면에
    쓰지 않고 터미널 로그에만 남는다. 로그가 꺼진 환경(Streamlit Cloud 기본)에서는 아무 조회도 하지 않고,
    Streamlit Cloud 실행 표지가 있으면 로그 옵션을 켜도 조회하지 않는다.
    조회 실패나 결과 없음은 경고 로그만 남기고 Neo4j 추천 결과에는 영향을 주지 않는다.

    Args:
        outcome (dict): ``run_pipeline`` 이 만든 화면 결과.
    """
    if not query_logging_active() or running_on_streamlit_cloud():
        return
    recommendations = outcome["result"]["recommendations"]
    if not recommendations:
        return
    rcp_id = recommendations[0]["rcp_id"]
    try:
        detail = get_log_check_search_service().get_recipe_detail(rcp_id=rcp_id)
    except Exception as error:                   # PostgreSQL 장애가 추천 화면을 막지 않게 한다
        logger.warning("PostgreSQL log check failed [rcp_id=%s]: %s", rcp_id, type(error).__name__)
        return
    if detail is None:
        logger.warning("PostgreSQL log check: recipe not found [rcp_id=%s]", rcp_id)
        return
    logging.getLogger("car_search_rag.sql").info(
        "LOG CHECK [postgres] rcp_id=%s rcp_seq=%s steps=%d ingredients=%d (화면 표시 없음)",
        rcp_id, detail["recipe"].get("rcpSeq"), len(detail["steps"]), len(detail["ingredients"]))


DB_DIAGNOSTIC_ENV = "RECIPE_DB_DIAGNOSTIC"     # 개발용 PostgreSQL 진단을 켜는 명시적 옵션(1/true/yes/on)


def running_on_streamlit_cloud() -> bool:
    """Streamlit Community Cloud 실행 환경의 표지(소스 위치·계정·호스트명) 중 하나라도 있으면 True."""
    return (Path(__file__).resolve().as_posix().startswith("/mount/src/")
            or os.getenv("HOME") == "/home/appuser" or os.getenv("HOSTNAME") == "streamlit")


def postgres_diagnostic_enabled() -> bool:
    """개발용 PostgreSQL 진단을 허용할지 판단한다.

    ``RECIPE_DB_DIAGNOSTIC`` 를 명시적으로 켜고, 로컬(.env 있음)이며 쿼리 로그가 켜져 있을 때만 True다.
    Streamlit Cloud 표지가 있으면 옵션을 켜도 항상 False다(.env 유무만으로 판단하지 않는다).
    """
    explicit = os.getenv(DB_DIAGNOSTIC_ENV, "").strip().lower() in QUERY_LOG_ON_VALUES
    return explicit and not running_on_streamlit_cloud() and is_local_dev() and query_logging_active()


def run_postgres_sql_diagnostic(name: str) -> dict:
    """로컬 개발용 DB 진단: 버튼을 눌렀을 때만 레시피명 검색 SELECT 2건을 PostgreSQL에서 실행한다.

    모드 A·B는 Neo4j만 조회하므로 평소에는 SQL 로그가 없다. 이 진단은 추천 결과와 무관하게
    ``RecipeSearchService.search_recipes`` → ``PostgresDbSession`` 경로(``recipe.count_recipes``·
    ``recipe.list_recipes``, 읽기 전용)를 실제로 실행해 공통 QueryLogger의 SQL·PARAMS·RESULT 로그를 남긴다.

    Args:
        name (str): 레시피명 검색어(부분 일치).

    Returns:
        dict: ``{"totalCount", "page", "pageSize", "items"}``.

    Raises:
        PermissionError: 진단이 허용되지 않은 환경(Cloud 포함)에서 호출한 경우. DB에 접속하지 않는다.
    """
    if not postgres_diagnostic_enabled():
        raise PermissionError(f"PostgreSQL diagnostic is disabled (set {DB_DIAGNOSTIC_ENV}=1 on a local run)")
    return get_log_check_search_service().search_recipes(name=name, page_size=3)


# endregion
# region 5. 추천 실행과 결과 표시 함수
# =========================================================
# 추천 실행 및 화면 데이터 변환
# =========================================================
def run_pipeline(rag: PantryGraphRAG, question: str, limit: int, sort: str) -> dict:
    """폼 제출 시 GraphRAG를 실행하고 화면 보관용 값으로 직렬화한다.

    Args:
        rag (PantryGraphRAG): 캐시된 추천 파이프라인.
        question (str): 사용자가 입력한 재료 또는 문장.
        limit (int): 표시할 추천 건수.
        sort (str): ``coverage`` 또는 ``missing`` 정렬 방식.

    Returns:
        dict: State의 추천 결과와 설명, 경고를 담은 Session State 저장값.
    """
    # LangGraph의 interpret → retrieve(Neo4j) → answer(선택적 LLM) 결과를 화면용 dict로 바꾼다.
    state = rag.run(question, limit=limit, sort=sort)
    return {
        "question": question, "sort": sort, "terms": state.get("terms", []),
        "term_source": state.get("term_source", "rule"), "result": state["result"].to_dict(),
        "owned": state["result"].owned_ingredients, "unknown": state["result"].unknown_terms,
        "answer": state["answer"], "warnings": state.get("warnings", []),
    }


# =========================================================
# 추천 결과 표시 도우미
# =========================================================
def show_llm_status(answer: dict) -> None:
    """``answer.llm_status``에 따라 LLM 검증 또는 대체 응답 상태를 표시한다.

    Args:
        answer (dict): ``PantryGraphRAG.answer``가 만든 설명과 상태값.
    """
    status, model = answer.get("llm_status"), os.getenv("OPENAI_MODEL") or DEFAULT_MODEL
    if status == "ok":
        st.success(f"`{model}`이(가) Neo4j에서 조회한 근거만 사용해 추천 이유를 작성했고, 검증을 통과했습니다.",
                   title="LLM 설명", icon=":material/auto_awesome:")
    elif status == "partial":
        st.warning("LLM 설명 중 근거 밖 재료·레시피가 나온 문장은 규칙 기반 설명으로 바꿨습니다. "
                   "레시피별 배지로 출처를 확인하세요.", title="LLM 설명 일부 교체", icon=":material/rule:")
    elif status == "failed":
        st.error(f"LLM 호출에 실패해({answer.get('llm_error') or '알 수 없는 오류'}) Neo4j 근거로 만든 규칙 기반 설명을 "
                 "표시합니다. 추천 레시피와 재료는 정상 조회 결과입니다.", title="규칙 기반 대체 응답",
                 icon=":material/error:")
    elif status == "disabled":
        st.info("LLM이 설정되지 않아(OPENAI_API_KEY 없음) Neo4j 근거로 만든 규칙 기반 설명을 표시합니다.",
                title="규칙 기반 응답", icon=":material/info:")


def source_badge(source: str) -> None:
    """요약과 레시피 이유가 LLM 또는 근거 규칙 중 어디서 왔는지 표시한다.

    Args:
        source (str): ``llm``이면 LLM 배지, 그 밖에는 규칙 기반 배지.
    """
    if source == "llm":
        st.badge("LLM 설명", icon=":material/auto_awesome:", color="violet")
    else:
        st.badge("규칙 기반 설명", icon=":material/rule:", color="gray")


def escape_markdown(text: str) -> str:
    """원본 문장을 Markdown 서식 없이 글자 그대로 보이도록 특수 문자를 이스케이프한다."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def show_image(url: str | None, *, alt: str, width: int | str) -> bool:
    """식약처 이미지 URL을 표시한다. 표시할 수 없으면 아무것도 그리지 않고 ``False`` 를 반환한다.

    URL 문자열은 Streamlit 서버가 내려받지 않고 브라우저에 그대로 전달되므로, 원격 서버 장애는
    해당 이미지 칸에만 영향을 준다. 그래도 요소 생성 단계의 예외는 잡아서 추천 화면 전체를 지킨다.

    Args:
        url (str | None): Neo4j에 적재된 원본 이미지 URL.
        alt (str): 보조 기술용 이미지 이름.
        width (int | str): ``st.image`` 의 ``width``.

    Returns:
        bool: 이미지 요소를 만들었으면 ``True``.
    """
    display = display_image_url(url)
    if display is None:
        return False
    try:
        st.image(display, width=width, alt=alt)
    except Exception as error:                   # 이미지 하나의 실패가 추천 화면을 멈추지 않게 한다
        logger.warning("image render failed: %s", type(error).__name__)
        return False
    return True


def show_steps(rec: dict, step_error: str | None) -> None:
    """레시피의 식약처 원본 조리 과정을 펼침 영역에 번호 순서대로 보여 준다.

    단계 이미지가 있으면 설명 옆(좁은 화면에서는 아래)에 두고, 없으면 설명만 보여 준다.

    Args:
        rec (dict): ``Recommendation`` 을 dict로 바꾼 값(``steps`` 포함).
        step_error (str | None): 조리 과정 조회 실패 사유. 있으면 안내 문구만 보여 준다.
    """
    steps = rec.get("steps") or []
    if not steps:
        if step_error is None:
            st.caption("이 레시피는 조리 과정 데이터가 없습니다.")
        return
    with st.expander(f"조리 과정 {len(steps)}단계 보기", icon=":material/menu_book:"):
        st.caption("식약처 원본 조리 과정(MANUAL)을 그대로 보여 줍니다. 단계 번호는 원본 번호입니다.")
        for step in steps:
            text = f"**{step['step_no']}.** {escape_markdown(step['instruction_txt'])}"
            if display_image_url(step.get("image_url")) is None:
                st.markdown(text)
                continue
            text_col, image_col = st.columns([3, 2], vertical_alignment="top")
            text_col.markdown(text)
            with image_col:
                show_image(step["image_url"], alt=f"{rec['rcp_nm']} 조리 {step['step_no']}단계", width="stretch")


# endregion
# region 6. 그래프 관계 탐색 (모드 B)
# =========================================================
# 그래프 관계 탐색 (모드 B)
# =========================================================
# 모드 B는 아래 Service로 고정 Named Cypher를 실행하며 추천용 Repository를 재사용한다.
@st.cache_resource(show_spinner="그래프 탐색 선택지를 준비하는 중입니다...")
def get_graph_question_service() -> GraphQuestionService:
    """추천 파이프라인의 ``RecipeGraphRepository`` 를 재사용하는 그래프 탐색 Service를 만든다.

    새 드라이버를 만들지 않고 ``get_pipeline()`` 이 연결 검증을 마친 Repository를 주입한다.

    Returns:
        GraphQuestionService: 레시피·분류 선택지를 캐시하는 읽기 전용 Service.
    """
    return GraphQuestionService(get_pipeline().service.graph)


def graph_inputs(service: GraphQuestionService, key: str) -> dict:
    """질문에 필요한 대상(식재료·레시피·분류)과 조건 위젯을 그리고 선택값을 돌려준다.

    Args:
        service (GraphQuestionService): 선택지를 조회할 Service.
        key (str): 'Q1'~'Q5'.

    Returns:
        dict: ``run_graph_question`` 에 넘길 파라미터.
    """
    parameter = QUESTIONS[key].parameter
    if parameter == "ingredient":
        return {"term": st.text_input("식재료 (표준명 또는 별칭)", value=GRAPH_DEFAULT_INGREDIENT, key="graph_term",
                                      help="DB의 표준 식재료명·별칭과 정확히 같은 이름만 찾습니다. 예: 두부, 계란(→ 달걀)")}
    if parameter == "category":
        names = [row["rcp_cat_nm"] for row in service.category_options()]
        index = names.index(GRAPH_DEFAULT_CATEGORY) if GRAPH_DEFAULT_CATEGORY in names else 0
        return {"rcp_cat_nm": st.selectbox("요리 분류", names, index=index, key="graph_category"),
                "limit": st.slider("표시할 식재료 수", 5, MAX_INGREDIENT_LIMIT, DEFAULT_INGREDIENT_LIMIT,
                                   key="graph_limit")}
    recipes = service.recipe_options()
    labels = {row["rcp_id"]: f"{row['rcp_nm']} (원본 {row['rcp_seq']}번)" for row in recipes}
    ids = list(labels)
    index = next((i for i, row in enumerate(recipes) if row["rcp_nm"] == GRAPH_DEFAULT_RECIPE), 0)
    params = {"rcp_id": st.selectbox("기준 레시피", ids, index=index, format_func=labels.get, key="graph_recipe",
                                     help="이름이 같은 레시피가 있어 식약처 원본 번호를 함께 보여 줍니다.")}
    if key == "Q3":
        params["min_common"] = st.number_input("공통 재료 최소 개수", min_value=1, max_value=10,
                                               value=DEFAULT_MIN_COMMON, key="graph_min_common",
                                               help="1이면 소금·설탕 같은 흔한 재료 하나만 겹쳐도 포함합니다.")
    return params


def run_graph_question(service: GraphQuestionService, key: str, params: dict) -> GraphAnswer:
    """선택한 질문에 맞는 Service 메서드를 호출한다. DB 예외는 호출자에게 전달한다.

    Args:
        service (GraphQuestionService): 그래프 탐색 Service.
        key (str): 'Q1'~'Q5'.
        params (dict): ``graph_inputs`` 가 돌려준 값.

    Returns:
        GraphAnswer: Neo4j 조회 결과.
    """
    handlers = {
        "Q1": lambda: service.recipes_using_ingredient(params["term"]),
        "Q2": lambda: service.similar_recipes(params["rcp_id"]),
        "Q3": lambda: service.similar_recipe_categories(params["rcp_id"], params["min_common"]),
        "Q4": lambda: service.category_ingredients(params["rcp_cat_nm"], params["limit"]),
        "Q5": lambda: service.recipe_steps(params["rcp_id"]),
    }
    return handlers[key]()


def graph_table(answer: GraphAnswer) -> list[dict]:
    """조회 행을 화면 열 이름으로 바꾼다(값은 바꾸지 않고 목록만 쉼표로 잇는다. 이미지는 표시용 URL)."""
    rows = []
    for row in answer.rows:
        item = {}
        for source, label in GRAPH_COLUMNS[answer.question.key]:
            value = row.get(source)
            if source == "image_url":
                value = display_image_url(value)
            elif isinstance(value, list):
                value = ", ".join(str(part) for part in value)
            elif isinstance(value, float):
                value = round(value, 3)
            item[label] = value
        rows.append(item)
    return rows


def graph_summary(answer: GraphAnswer) -> str | None:
    """조회 행만으로 만든 한 줄 결과 요약(LLM 미사용). 결과가 없으면 ``None``."""
    rows, key = answer.rows, answer.question.key
    if not rows:
        return None
    if key == "Q1":
        return f"조회된 레시피 {len(rows)}개(레시피명 순)."
    if key == "Q2":
        top = rows[0]
        return (f"공통 재료가 가장 많은 레시피는 '{top['rcp_nm']}'(공통 재료 {top['common_count']}개)입니다. "
                f"공통 재료 수 → Jaccard → 레시피 ID 순 상위 {len(rows)}개.")
    if key == "Q3":
        total = sum(row["recipe_count"] for row in rows)
        top = rows[0]
        return (f"공통 재료 {answer.parameters['min_common']}개 이상인 다른 레시피 {total}개가 {len(rows)}개 분류에 속합니다. "
                f"가장 많은 분류는 '{top['rcp_cat_nm']}'({top['recipe_count']}개)입니다.")
    if key == "Q4":
        first = rows[0]
        return (f"'{answer.parameters['rcp_cat_nm']}' 분류 레시피 {first['category_recipe_count']}개가 식재료 "
                f"{first['category_ingredient_count']}종을 사용합니다. 사용 레시피 수 상위 {len(rows)}종.")
    return f"조리 단계 {len(rows)}개(식약처 원본 MANUAL 번호 순)."


def show_graph_answer(answer: GraphAnswer) -> None:
    """질문 문장·hop·관계 경로·조회 결과 표를 보여 준다.

    실행 Cypher와 바인딩 파라미터는 화면에 보이지 않는다. 로컬 개발 실행에서는 터미널 로그(combined)에서
    확인하고(``RECIPE_QUERY_LOG`` 참고), 과제용 Cypher는 docs/assignment 문서·노트북에 있다.

    Args:
        answer (GraphAnswer): 표시할 조회 결과.
    """
    question = answer.question
    with st.container(border=True):
        st.markdown(f"#### {answer.question_text}")
        with st.container(horizontal=True):
            st.badge(f"{question.key} · {question.hop}-hop", icon=":material/route:", color="blue")
            st.badge("Neo4j 조회 결과 (LLM 미사용)", icon=":material/hub:", color="green")
            st.badge(f"{answer.row_count}건", icon=":material/table_rows:", color="gray")
        st.markdown(f"**관계 경로** ({question.hop}개 관계를 건너감)")
        st.code(question.path, language="cypher")
        if answer.status == "not_found":
            st.warning(answer.message, icon=":material/search_off:")
        elif answer.message:
            st.info(answer.message, icon=":material/info:")
        summary = graph_summary(answer)
        if summary:
            st.caption(summary)
        if answer.rows:
            column_config = {"단계 이미지": st.column_config.ImageColumn("단계 이미지")} if question.key == "Q5" else None
            st.dataframe(graph_table(answer), hide_index=True, column_config=column_config,
                         alt=f"{question.key} {answer.question_text} 조회 결과 {answer.row_count}건")


def show_graph_explorer() -> None:
    """모드 B: 과제 질문 Q1~Q5를 고르고 대상을 정해 Neo4j를 조회한다(읽기 전용, LLM 미사용).

    연결·조회 오류는 이 화면 안에서 알리고 함수를 끝낸다. 마지막 결과는 ``session_state.graph_answer`` 에 둔다.
    """
    st.caption("과제 질문 5개를 고정된 읽기 전용 Cypher로 조회합니다. 자연어를 Cypher로 바꾸지 않고, "
               "LLM을 쓰지 않으며, 표는 Neo4j 조회 결과 그대로입니다.")
    try:
        service = get_graph_question_service()
        key = st.radio("질문", list(QUESTIONS), key="graph_question",
                       format_func=lambda k: f"{k} · {QUESTIONS[k].hop}-hop · {QUESTIONS[k].title}")
        with st.form("graph_form"):
            params = graph_inputs(service, key)
            submitted = st.form_submit_button("그래프 조회", type="primary", icon=":material/hub:")
        if submitted:
            st.session_state.graph_answer = run_graph_question(service, key, params)
    except Exception as error:
        st.session_state.graph_answer = None
        st.error(f"{type(error).__name__}: {safe_error(error)}", title="그래프 조회 중 오류가 발생했습니다",
                 icon=":material/cloud_off:")
        return
    answer = st.session_state.get("graph_answer")
    if answer is None or answer.question.key != key:
        st.info("대상을 고르고 **그래프 조회**를 누르세요.", icon=":material/hub:")
        return
    show_graph_answer(answer)


# endregion
# region 7. Streamlit 화면 실행과 모드 분기
# =========================================================
# Streamlit 화면 실행 시작
# =========================================================
# 여기부터는 함수 정의가 아닌 최상위 화면 코드다. 위의 import·환경 초기화도 앞서 실행된다.
# Streamlit은 최초 접속과 위젯 이벤트마다 스크립트를 위에서부터 다시 실행하고,
# get_pipeline()의 객체는 cache_resource, 마지막 화면 결과는 session_state로 재사용한다.
st.set_page_config(page_title="냉장고 재료 레시피 추천", page_icon=":material/kitchen:", layout="centered")
st.title("냉장고 재료로 레시피 추천", anchor=False)
st.caption("식약처 레시피 1,156건을 담은 Neo4j 그래프에서 보유 재료로 만들 수 있는 레시피를 찾고, "
           "LLM이 조회 근거만으로 추천 이유를 설명합니다. 사진과 조리 과정은 식약처 원본입니다.")

mode = st.segmented_control("사용 모드", list(MODES), default="pantry", required=True, format_func=MODES.get,
                            key="app_mode")
if mode == "graph":
    # 모드 B는 그래프 조회 화면을 만든 뒤 이 실행을 끝내므로 아래 모드 A 코드는 실행하지 않는다.
    show_graph_explorer()
    st.stop()

# endregion
# region 8. 모드 A 입력·연결 확인·추천 제출
# =========================================================
# 모드 A: 입력 폼과 추천 버튼 처리
# =========================================================
if "outcome" not in st.session_state:
    st.session_state.outcome = None

with st.form("pantry_form"):
    question = st.text_area("가지고 있는 재료", value=DEFAULT_QUESTION, height=80,
                            help="쉼표나 줄바꿈으로 구분합니다. '냉장고에 계란이랑 두부가 있어'처럼 문장으로 써도 됩니다.")
    with st.container(horizontal=True, vertical_alignment="bottom"):
        sort = st.segmented_control("추천 순서", options=list(SORT_STATEMENTS), default="coverage", required=True,
                                    format_func=lambda key: SORT_STATEMENTS[key][1])
        limit = st.slider("추천 수", min_value=1, max_value=min(10, MAX_RECOMMENDATIONS), value=5)
    submitted = st.form_submit_button("레시피 추천", type="primary", icon=":material/search:")

try:
    # 화면을 다시 그릴 때마다 호출하지만 실제 GraphRAG 객체는 cache_resource가 재사용한다.
    rag = get_pipeline()
except Exception as error:
    st.error(f"{type(error).__name__}: {safe_error(error)}", title="Neo4j AuraDB에 연결하지 못했습니다",
             icon=":material/cloud_off:")
    st.stop()

with st.container(horizontal=True):
    st.badge("Neo4j AuraDB 연결됨", icon=":material/hub:", color="green")
    if rag.llm is None:
        st.badge("LLM 미설정", icon=":material/block:", color="gray")
    else:
        st.badge(f"LLM {os.getenv('OPENAI_MODEL') or DEFAULT_MODEL}", icon=":material/smart_toy:", color="violet")

if postgres_diagnostic_enabled():
    # RECIPE_DB_DIAGNOSTIC=1을 명시한 로컬 실행(로그 켜짐)에서만 보인다. Cloud에서는 옵션을 켜도 나타나지 않는다.
    # 버튼을 눌렀을 때만 PostgreSQL 읽기 전용 SELECT를 실행하며 추천 결과에는 영향을 주지 않는다.
    with st.expander("개발용 DB 진단 (로컬 전용)"):
        last = st.session_state.outcome
        diag_name = last["result"]["recommendations"][0]["rcp_nm"] if last and last["result"]["recommendations"] else "두부"
        if st.button(f"PostgreSQL SQL 로그 확인: '{diag_name}' 검색", key="postgres_sql_diagnostic"):
            try:
                found = run_postgres_sql_diagnostic(diag_name)
                st.caption(f"PostgreSQL 조회 완료: 전체 {found['totalCount']}건 중 {len(found['items'])}건. "
                           "SQL·PARAMS·RESULT 로그는 터미널(car_search_rag.sql)에서 확인합니다.")
            except Exception as error:               # 진단 실패가 추천 화면을 막지 않게 한다
                st.caption(f"PostgreSQL 진단 실패: {type(error).__name__}: {safe_error(error)}")

if submitted:
    if not question.strip():
        st.warning("재료를 한 개 이상 입력하세요.")
        st.stop()
    with st.spinner("Neo4j에서 레시피를 찾고 추천 이유를 작성하는 중입니다..."):
        try:
            # 폼 제출에서만 입력값을 PantryGraphRAG에 전달하고 최종 State를 화면용 dict로 저장한다.
            st.session_state.outcome = run_pipeline(rag, question, limit, sort)
        except Exception as error:
            st.session_state.outcome = None
            st.error(f"{type(error).__name__}: {safe_error(error)}", title="추천 중 오류가 발생했습니다")
            st.stop()
        run_postgres_log_check(st.session_state.outcome)    # 로컬 로그 검증 모드에서만 실행(화면 영향 없음)

# ``session_state``는 위젯으로 인한 스크립트 재실행 뒤에도 마지막 제출 결과를 유지한다.
# 재실행 때 버튼이 눌리지 않아도 아래 화면은 이 결과 dict를 읽어 다시 그린다.
outcome = st.session_state.outcome
if outcome is None:
    st.info("재료를 입력하고 **레시피 추천**을 누르세요.", icon=":material/kitchen:")
    st.stop()

answer = outcome["answer"]
recommendations = outcome["result"]["recommendations"]

# endregion
# region 9. 모드 A 추천 결과 화면 출력
# =========================================================
# 모드 A: 입력 해석과 추천 결과 표시
# =========================================================
# DB 조회는 위의 run_pipeline에서 끝났으며 여기서는 보관된 결과와 설명의 출처를 표시한다.
st.subheader("입력 해석", anchor=False)
st.caption(f"해석 방식: {TERM_SOURCE_LABELS.get(outcome['term_source'], outcome['term_source'])}")
rows = []
for resolution in outcome["result"]["resolutions"]:
    # 한 입력어가 여러 표준명·별칭에 일치할 수 있으므로 각 매칭을 별도 행으로 보여 준다.
    if resolution["matches"]:
        for match in resolution["matches"]:
            rows.append({"입력": resolution["term"], "DB 표준 식재료": match["ingr_nm"],
                         "일치 방식": "별칭" if match["matched_by"] == "alias" else "표준명"})
    else:
        rows.append({"입력": resolution["term"], "DB 표준 식재료": "—", "일치 방식": "DB에 없음(추천에서 제외)"})
st.table(rows, alt="입력한 재료와 DB 표준 식재료 매칭 결과")

for warning in outcome["warnings"]:
    st.warning(warning, icon=":material/warning:")

st.subheader("추천 결과", anchor=False)
show_llm_status(answer)
with st.container(border=True):
    source_badge(answer.get("summary_source", "grounded"))
    st.markdown(answer["summary"])

step_error = outcome["result"].get("step_error")
if step_error:
    st.warning(f"조리 과정을 불러오지 못했습니다({step_error}). 추천 레시피와 재료는 정상 조회 결과입니다.",
               icon=":material/menu_book:")

for rank, rec in enumerate(recommendations, start=1):
    with st.container(border=True):
        st.markdown(f"#### {rank}. {rec['rcp_nm']}")
        show_image(rec.get("image_url"), alt=f"{rec['rcp_nm']} 완성 사진", width=RECIPE_IMAGE_WIDTH)
        with st.container(horizontal=True):
            for category in rec["categories"]:
                st.badge(category, icon=":material/category:", color="blue")
            if rec["method"]:
                st.badge(rec["method"], icon=":material/skillet:", color="orange")
            if rec["energy_kcal"] is not None:
                st.badge(f"{rec['energy_kcal']:.0f} kcal", icon=":material/local_fire_department:", color="red")
            source_badge(answer["sources"].get(rec["rcp_id"], "grounded"))
        st.markdown(answer["reasons"].get(rec["rcp_id"], ""))
        st.markdown(f"**사용하는 보유 재료 {rec['matched_count']}개:** {', '.join(rec['matched_ingredients'])}")
        missing = rec["missing_ingredients"]
        if not missing:
            st.markdown("**추가로 필요한 재료:** 없음")
        elif len(missing) <= MISSING_INLINE_LIMIT:
            st.markdown(f"**추가로 필요한 재료 {rec['missing_count']}개:** {', '.join(missing)}")
        else:
            with st.expander(f"추가로 필요한 재료 {rec['missing_count']}개 보기"):
                st.markdown(", ".join(missing))
        show_steps(rec, step_error)
        st.caption(f"레시피 ID {rec['rcp_id']} · 식약처 원본 번호 {rec['rcp_seq'] or '—'}")

if not recommendations:
    st.info("DB에 등록된 재료가 없어 추천할 레시피가 없습니다. 재료 이름을 확인해 주세요.")

with st.expander("근거 데이터(JSON) 보기"):
    st.json({"terms": outcome["terms"], "term_source": outcome["term_source"], "owned_ingredients": outcome["owned"],
             "unknown_terms": outcome["unknown"], "answer": answer, "result": outcome["result"]}, expanded=False)
# endregion
