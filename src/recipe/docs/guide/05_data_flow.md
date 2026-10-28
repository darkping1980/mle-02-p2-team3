# 05. 데이터 흐름

[메인](README.md) · [실행 흐름](04_execution_flow.md) · [LangGraph 상세](details/02_langgraph.md)

## 웹 질문에서 화면까지

| 경계 | 실제 형식·주요 키 | 변환 |
| --- | --- | --- |
| 폼 → `run_pipeline` | `question: str`, `limit: int`, `sort: 'coverage'|'missing'` | 질문의 공백 검사 후 전달 |
| `PantryGraphRAG.run` → 초기 `PantryState` | `{'question': str, 'limit': int, 'sort': str, 'warnings': []}` | `graph.invoke` 입력 |
| `interpret` → State | `terms: list[str]`, `term_source: 'rule'|'llm'|'vocabulary'`, `warnings: list[str]` | 쉼표 등 구분 또는 구조화 추출. LLM 추출어는 원문 포함 여부 확인. 문장 대체 경로는 DB 어휘 스캔 |
| `resolve_terms` | `list[TermResolution]`: `term`, `matches: [{ingr_id, ingr_nm, matched_by}]` | [normalize_name](../../recipe_recommender/name_normalization.py)은 양끝 공백 제거·소문자화. `ingredient_name_candidates`로 표준명/별칭 정확 일치 |
| `recommend` | `PantryResult(terms,resolutions,recommendations)` | 해석된 입력어의 정규화 목록을 추천 Cypher에 전달. 미등록어만 있으면 빈 추천 |
| Neo4j 추천 행 | `rcp_id`, `rcp_nm`, `matched_count`, `missing_count`, `matched_ingredients`, `missing_ingredients` | `RCP_USES` 관계에서 보유·전체 집합을 계산 |
| Neo4j 근거 행 | `{'context': {rcp_seq,categories,method,energy_kcal,image_url,ingredients,...}}` | 추천 레시피마다 `graphrag_context` 조회 후 `Recommendation` 조립. `image_url`은 화면용이며 LLM 근거에는 넣지 않음 |
| Neo4j 조리 과정 행 | `recipe_steps`: `rcp_id`, `step_no`, `instruction_txt`, `image_url` | 추천 목록 확정 후 `{rcp_ids}`로 한 번 조회 → 레시피별 `list[RecipeStep]`(원본 번호 순). 실패 시 `PantryResult.step_error` |
| `build_context` → LLM | `list[dict]`: `rcp_id`, `name`, `categories`, `method`, `energy_kcal`, `used_ingredients`, `missing_ingredients`, `all_ingredients` | `json.dumps(..., ensure_ascii=False)`로 프롬프트에 포함. 보유 표준명·미등록어도 별도 포함 |
| LLM → `validate_answer` | `PantryAnswer(summary: str, recipes: list[RecipeReason(rcp_id,reason)])` | 존재하지 않는 ID는 버리고, DB 어휘 중 허용되지 않은 재료가 나온 설명은 근거 문장으로 교체 |
| `answer` → State | `answer: {summary,summary_source,reasons,sources,llm_status,llm_error}` | LLM 미설정/실패/검증 실패 때 대체 문장 |
| `run_pipeline` → 화면 | `{question,sort,terms,term_source,result,owned,unknown,answer,warnings}` | `result`만 `PantryResult.to_dict()`로 직렬화한 dict. `owned`/`unknown`은 계산 속성 |

예를 들어 `"계란, 두부"`는 `split_terms`에서 `['계란','두부']`가 된다. DB의 별칭 데이터가 `계란 → 달걀`로 등록돼 있다면 `TermResolution.matches`의 표준명은 `달걀`, `matched_by`는 `alias`다. 이 매핑은 코드에 고정된 치환표가 아니라 조회 결과에 따른다. `owned_ingredients`는 표준명 중복을 제거한다. `resolutions.matches`가 여러 건일 경우 코드가 모두 보유 재료 후보에 포함한다. 웹 화면에는 이 중 하나를 사용자가 선택하는 단계가 없다.

`Recommendation`의 필드는 `rcp_id: str`, `rcp_nm: str`, `rcp_seq: str|None`, `categories: list[str]`, `method: str|None`, `energy_kcal: float|None`, `matched_ingredients/missing_ingredients/all_ingredients: list[str]`, `matched_count/missing_count: int`, `image_url: str|None`(기본 `None`), `steps: list[RecipeStep]`(기본 빈 목록)이다. 뒤의 두 필드는 표시용이라 추천 순서·LLM 근거에 쓰이지 않는다. `to_dict()`는 `dataclasses.asdict`로 중첩 객체를 dict로 바꾼다. 화면 카드의 레시피명·카운트·재료·대표 이미지·조리 과정은 이 dict에서 직접 읽고, 설명은 `answer['reasons'][rcp_id]`에서 읽는다. 이미지 URL은 화면 직전에 `display_image_url`로 표시 가능 여부를 확인한다(식약처 `http://`는 `https://`로 표시, 그 밖의 비정상 값은 생략).

`llm_status`는 `ok`, `partial`, `failed`, `disabled`가 화면 메시지로 표시되는 값이다. 추천이 없지만 LLM 객체가 있는 경우 `answer()`의 대체 dict에는 `skipped`도 들어갈 수 있으며, 화면 `show_llm_status()`는 이 값에 대한 별도 알림 분기가 없다. LLM 검증은 **DB 식재료 어휘의 부분 문자열 검사**다. DB 어휘 밖의 사실 전체를 증명하는 검증은 아니다.

## 모드 B: 그래프 관계 탐색의 형식

| 경계 | 실제 형식·주요 키 | 변환 |
| --- | --- | --- |
| 폼 → `run_graph_question` | Q1 `{term}`, Q2·Q5 `{rcp_id}`, Q3 `{rcp_id, min_common}`, Q4 `{rcp_cat_nm, limit}` | Q3 `min_common`은 1 이상, Q4 `limit`은 1~50으로 보정 |
| Service → Cypher 파라미터 | Q1 `{term_norm}`, Q2 `{rcp_id}`, Q3 `{rcp_id, min_common}`, Q4 `{rcp_cat_nm, limit}`, Q5 `{rcp_ids: [rcp_id]}` | `normalize_name`(양끝 공백 제거·소문자) |
| Cypher → `GraphAnswer.rows` | Q1 `{ingr_id, ingredient, rcp_id, rcp_seq, rcp_nm}` · Q2 `{rcp_id, rcp_nm, common_count, common_ingredients, jaccard}` · Q3 `{rcp_cat_nm, recipe_count, max_common_count, sample_recipes}` · Q4 `{ingr_nm, recipe_count, category_recipe_count, category_ingredient_count}` · Q5 `{rcp_id, step_no, instruction_txt, image_url}` | 그대로 보관(Q1만 `rcp_id` 중복 제거) |
| `GraphAnswer` → 화면 | `status`('ok'·'empty'·'not_found'), `message`, `question_text`, `parameters`, `rows` | `graph_table`이 한국어 열 이름·쉼표 목록·https 이미지 URL로 바꿔 `st.dataframe`에 전달 |

## 등록과 그래프 적재의 형식

식약처 CSV 한 행은 `dict[str,str]`이며 `read_csv()`가 `RCP_RAW_SEQ`를 더한다. `build_plan()`은 원본·레시피·분류 관계·단계·파싱된 재료 staging의 목록을 `RecipeLoadPlan`에 모은다. `RecipeRepository`가 SQL 파라미터용 대문자 snake_case 키를 넘기고, PostgreSQL 조회 결과는 `PostgresDbSession`의 camelCase 키로 Service에 돌아온다. `rcp_ingr_stg`의 검토 보류 행은 자동으로 최종 `rcp_ingr` 관계가 되지 않는다.

그래프 적재는 PostgreSQL의 `rcp_cat`, `ingr`, `ingr_als`, `rcp`, `rcp_cat_rel`, `rcp_ingr`, `rcp_step` 등을 읽어 `GraphSourceSnapshot`에 묶는다. `prepare()`가 `PreparedGraph.stages`에 `recipe_categories`, `ingredients`, `recipes`, `recipe_links`, `uses`, `steps`를 만든다. `ingr_als`는 식재료 노드의 `alias_names`/`alias_names_norm` 속성으로 접고, `Decimal` 열량은 float로 바꾼다. 그래프에는 `rcp → RCP_IN_RECIPE_CATEGORY → rcp_cat`, `rcp → RCP_USES → ingr`, `rcp → RCP_HAS_STEP → rcp_step`을 적재한다. 원본·staging은 그래프 노드가 아니다. [데이터 파이프라인 상세](details/05_data_pipeline.md).
