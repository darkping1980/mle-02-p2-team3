# Streamlit 상세

[메인](../README.md) · [실행 흐름](../04_execution_flow.md) · [LangGraph](02_langgraph.md)

원본: [streamlit_app.py](../../../streamlit_app.py), [설정 예시](../../../.streamlit/secrets.toml.example), [config.py](../../../recipe_recommender/config.py). Streamlit은 파일의 최상위 문장을 화면 실행/재실행 때 평가한다. Java `main`의 한 번짜리 순서와 달리 폼 제출 후 스크립트가 다시 실행된다.

| 함수·위치 | 인자 → 반환 | 내부 호출·부작용·오류 |
| --- | --- | --- |
| [`get_pipeline()`](../../../streamlit_app.py) | 없음 → `PantryGraphRAG` | `@st.cache_resource`로 객체 재사용. `RecipeGraphRepository()` 생성, `driver.verify_connectivity()`, Service·LLM 생성. 실패 예외는 함수 밖 화면의 `try/except`가 처리. |
| [`get_log_check_search_service()`](../../../streamlit_app.py) | 없음 → `RecipeSearchService` | 로그 ON에서만 호출. PostgreSQL 세션을 만들어 캐시하고 종료 시 pool을 닫는다. |
| [`run_postgres_log_check(outcome)`](../../../streamlit_app.py) | 화면 결과 `dict` → `None` | 첫 추천 레시피를 `RecipeSearchService.get_recipe_detail`로 추가 조회한다. SQL 4개는 터미널에만 기록되고 조회 실패도 추천 결과를 바꾸지 않는다. 로그 OFF이면 조회하지 않는다. |
| [`run_pipeline(rag, question, limit, sort)`](../../../streamlit_app.py) | RAG, `str,int,str` → 화면용 `dict` | `rag.run`의 State에서 `result.to_dict()`, 보유·미등록어, 답변·경고 추출. 제출 블록이 예외를 잡아 outcome을 `None`으로 비운다. |
| [`show_llm_status(answer)`](../../../streamlit_app.py) | `dict` → `None` | `llm_status`에 따라 `st.success/warning/error/info`. `skipped` 분기는 없다. |
| [`source_badge(source)`](../../../streamlit_app.py) | `str` → `None` | `llm`이면 LLM 배지, 그 외 근거 기반 배지. |
| [`get_graph_question_service()`](../../../streamlit_app.py) | 없음 → `GraphQuestionService` | `@st.cache_resource`. `get_pipeline().service.graph`를 주입(새 드라이버 없음). |
| [`show_graph_explorer()`](../../../streamlit_app.py) | 없음 → `None` | 모드 B 화면. 질문 라디오(key `graph_question`) → 폼 `graph_form`(`graph_inputs`) → `run_graph_question` → `session_state.graph_answer` → `show_graph_answer`. 예외는 `st.error`로 표시하고 반환. |
| [`graph_inputs` / `run_graph_question` / `graph_table` / `graph_summary` / `show_graph_answer`](../../../streamlit_app.py) | 위젯·결과 처리 | 위젯 key: `graph_term`, `graph_recipe`, `graph_min_common`, `graph_category`, `graph_limit`. 표 열 이름은 `GRAPH_COLUMNS`. 요약 문장은 조회 행으로만 만든다(LLM 미사용). 실행 Cypher·파라미터는 화면에 표시하지 않는다. |
| [`escape_markdown(text)`](../../../streamlit_app.py) | `str` → `str` | 원본 조리 설명의 `*`, `~`, `$`, `[` 등 Markdown 특수 문자를 `\`로 이스케이프해 서식 없이 글자 그대로 보이게 한다. |
| [`show_image(url, *, alt, width)`](../../../streamlit_app.py) | URL·대체 텍스트·폭 → `bool` | `display_image_url`이 `None`이면 아무것도 그리지 않고 `False`. 아니면 `st.image(url)`. URL 문자열은 Streamlit 서버가 내려받지 않고 브라우저가 직접 받으므로 원격 장애는 그 이미지 칸에만 영향을 준다. 요소 생성 예외도 잡아 로그만 남긴다. |
| [`show_steps(rec, step_error)`](../../../streamlit_app.py) | 추천 dict·조회 오류 → `None` | `rec['steps']`가 있으면 `st.expander("조리 과정 N단계 보기")` 안에 원본 번호·설명을 표시하고, 단계 이미지가 있으면 `st.columns([3, 2])` 오른쪽에 둔다. 단계가 없고 오류도 없으면 "조리 과정 데이터가 없습니다" 캡션, 조회 오류면 아무것도 그리지 않는다(상단 경고가 한 번 표시됨). |

최상위 초기화는 `TASK_DIR`를 `sys.path`에 추가하고 `st.secrets` 중 정해진 이름만 `os.environ.setdefault`로 복사한다. `st.secrets` 접근 실패는 포괄 `except`로 넘어간다. 다음 `load_project_environment()`가 Git 루트 `.env`를 읽지만 기존 프로세스 값을 덮지 않는다. 관련 이름은 `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `NEO4J_TRUSTED_CA_FILE`, `OPENAI_API_KEY`, `OPENAI_MODEL`이다. 값 자체는 문서에 싣지 않는다.

제목 아래 `사용 모드`(`st.segmented_control`, key `app_mode`, 기본 `pantry`)가 있다. `graph`를 고르면 `show_graph_explorer()` 뒤 `st.stop()`하므로 아래 추천 폼은 그 실행에서 만들어지지 않는다. 기본값이 `pantry`라 기존 추천 화면과 테스트 흐름은 바뀌지 않는다.

폼은 `question`, `sort`, `limit`을 만든다. `sort` 선택지는 `SORT_STATEMENTS`의 `coverage`/`missing`, 슬라이더는 1~10이고 Service 최대치는 20이다. 연결 확인은 폼 렌더 뒤 매번 코드상 호출되지만 캐시 적중 시 객체 생성과 연결 검증을 다시 하지 않는다. 제출하지 않았으면 기존 `session_state.outcome`을 계속 화면에 표시한다. 제출 질문이 비거나 추천 중 예외가 나면 `st.stop()`으로 이번 렌더를 끝낸다.

표는 `outcome['result']['resolutions']`의 `matches`를 펼쳐 표준명/별칭 여부를 보인다. 카드는 제목 → 대표 이미지(`rec['image_url']`, 폭 `RECIPE_IMAGE_WIDTH`) → 배지 → 추천 이유 → 재료 → 조리 과정 펼침(`show_steps`) → 레시피 ID 순서다. 대표 이미지·조리 과정·단계 이미지는 식약처 원본을 Neo4j에서 조회한 값이며 LLM이 만들지 않는다. `outcome['result']['step_error']`가 있으면 카드 위에 경고 한 번을 띄우고 추천은 그대로 보여 준다. 카드의 재료 목록은 Neo4j 결과이며, `answer['sources']` 배지는 설명의 출처다. `st.json`은 State와 결과 근거를 살피는 디버깅 화면이다. 화면의 캡션에 적힌 레시피 수는 문자열 상수이므로 실시간 DB 집계 결과로 읽지 않는다.

**개발용 터미널 로그:** 최상위에서 `load_project_environment()` 다음에 `configure_query_logging(default=local_dev_query_log_default())`를 호출한다. 로컬 개발(저장소 루트 `.env` 있음)에서는 소스 설정값 `LOCAL_DEV_QUERY_LOG_DEFAULT = True`로 기본 켜지고, 환경변수 `RECIPE_QUERY_LOG`에 값이 있으면 그 값이 우선한다(`0`이면 끔). 켜지면 `car_search_rag.neo4j`·`car_search_rag.sql` logger가 INFO로 stderr(실행한 터미널)에 출력되고, `get_pipeline()`이 만드는 `RecipeGraphRepository`가 `cypher_log_mode="combined"`가 되어 모드 A·B의 Neo4j 조회가 값이 들어간 인라인 Cypher(안전하지 않으면 `:param` 대체)로 찍힌다. 모드 A의 추천 직후에는 첫 추천 레시피를 PostgreSQL에서 추가 SELECT하여 인라인 SQL 4개도 남긴다. Streamlit Cloud에는 `.env`가 없어 기본 꺼짐이며, Secrets에 `RECIPE_QUERY_LOG`를 넣지 않는다. 로그 모드는 Repository 생성 시 정해지므로, 바꾼 뒤에는 앱을 다시 시작한다. 자세한 예시는 [쿼리 로그 검증 보고서](07_query_log_verification.md#12-인수인계-최종-검증).

**수명 주의:** 캐시된 그래프 Repository를 닫는 화면 코드가 없다. 서버 프로세스에서 재사용되는 드라이버라는 의미다. CLI는 별도로 `finally`에서 연결을 닫는다.
