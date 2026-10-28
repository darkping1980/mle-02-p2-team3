# 추천 Service 상세

[메인](../README.md) · [데이터 흐름](../05_data_flow.md) · [Neo4j Repository](04_neo4j_repository.md)

원본: [pantry_recommend_service.py](../../../recipe_recommender/pantry_recommend_service.py), [조회 Cypher](../../../recipe_recommender/recipe_graph_queries.cypher), [추천 Cypher](../../../recipe_recommender/pantry_graphrag.cypher). 이 Service는 추천·식재료 해석을 담당한다. LLM을 호출하거나 화면을 그리지 않는다.

| 함수·메서드 | 호출/형식 | 실제 처리와 다음 호출 |
| --- | --- | --- |
| [`split_terms(text: str) -> list[str]`](../../../recipe_recommender/pantry_recommend_service.py) | `PantryGraphRAG.interpret`가 호출 | 쉼표·줄바꿈·슬래시 등 정규식 구분자로 나누고 `normalize_name` 기준 중복 제거, 최대 20개. 띄어쓰기만으로 나누지 않는다. DB 부작용 없음. |
| [`PantryRecommendService.__init__(graph)`](../../../recipe_recommender/pantry_recommend_service.py) | 웹 `get_pipeline` | `graph` 필드와 `_vocabulary=None` 저장. 여기서는 DB 질의 없음. |
| [`_query(statement: str, parameters: dict) -> list[dict]`](../../../recipe_recommender/pantry_recommend_service.py) | `resolve_terms`, `recommend`, `_attach_steps`, `vocabulary` | `ALLOWED_STATEMENTS` 외에는 `ValueError`. `recipe_graph_queries.*`면 `graph.query_example(name, params)`, `pantry_graphrag.*`면 `graph.mapper.select_list(full_id, params)`. 오류는 위로 전파. |
| [`resolve_terms(terms: list[str]) -> list[TermResolution]`](../../../recipe_recommender/pantry_recommend_service.py) | `recommend` | 입력어별 `normalize_name` → `ingredient_name_candidates` (`term_norm`) → `ingr_id`, `ingr_nm`, `matched_by='name'|'alias'` 묶기. 한 입력어에 여러 행이 있으면 모두 유지. |

| [`recommend(terms, limit=5, sort='coverage') -> PantryResult`](../../../recipe_recommender/pantry_recommend_service.py) | LangGraph `retrieve` | sort 검증, limit 1~20로 제한, 공백어 제거·최대 20개, `resolve_terms`. 유효어가 없으면 빈 추천 반환. 있으면 정렬별 Cypher에 `{names_norm, limit:20}` 전달, Python에서 `rows[:limit]` 선택, 각 행에 `graphrag_context({rcp_id})` 조회 후 `Recommendation` 조립(대표 이미지 `image_url` 포함). 마지막에 `_attach_steps(result)`. |
| [`_attach_steps(result: PantryResult) -> None`](../../../recipe_recommender/pantry_recommend_service.py) | `recommend` 마지막 | 추천이 있으면 `recipe_steps({rcp_ids})`를 **한 번** 조회해 레시피별 `RecipeStep` 목록을 `step_no` 순으로 붙인다. 추천 순서·건수·재료는 바꾸지 않는다. 조회 예외는 여기서만 잡아 `result.step_error`에 예외 이름을 남기고 `steps=[]`로 둔다. |
| [`display_image_url(url) -> str \| None`](../../../recipe_recommender/pantry_recommend_service.py) | 화면 `show_image`, `show_steps` | 표시용 변환. 비었거나 http/https가 아니면 `None`(이미지만 생략). `HTTPS_UPGRADE_HOSTS`(식약처)의 `http://`는 같은 경로 `https://`로 바꾼다. DB 값은 바꾸지 않는다. |
| [`vocabulary() -> list[dict]`](../../../recipe_recommender/pantry_recommend_service.py) | 문장 fallback·답변 검증 | `ingredient_vocabulary`를 최초 1회 조회해 인스턴스에 캐시. `[{ingr_id,ingr_nm,alias_names}]`. DB 오류는 전파. |

`normalize_name`은 [name_normalization.py](../../../recipe_recommender/name_normalization.py)에 정의된다. 추천 경로와 `setup`의 그래프 적재 Service가 같은 함수를 사용한다.

`TermResolution(term, matches)`는 입력어의 원문과 표준명 후보를 담는다. `RecipeStep(step_no, instruction_txt, image_url=None)`은 식약처 원본 조리 과정 한 단계다. `PantryResult(terms,resolutions,recommendations,step_error=None)`의 `resolved_terms`, `unknown_terms`, `owned_ingredients`는 `@property` 계산 결과다. `to_dict()`는 화면에 전달할 `terms`, `resolutions`, `recommendations`, `step_error`만 변환한다. `Recommendation` 필드 상세는 [데이터 흐름](../05_data_flow.md)에 있다.

`coverage`는 [pantry_recommendations_by_coverage](../../../recipe_recommender/pantry_graphrag.cypher): `matched_count DESC, missing_count ASC, rcp_id`. `missing`은 [pantry_recommendations](../../../recipe_recommender/recipe_graph_queries.cypher): `missing_count ASC, matched_count DESC, rcp_id`. 두 쿼리 모두 `names_norm`의 표준명/별칭 일치를 `ingr`에서 찾고 `RCP_USES`를 따라 레시피별 보유·부족 재료를 계산한다. 추천 쿼리는 사용 재료가 하나 이상 겹치는 레시피만 반환한다. `graphrag_context`는 분류·방법·열량과 **전체 사용 식재료**, 화면용 대표 이미지 URL을 보완한다. [recipe_steps](../../../recipe_recommender/recipe_graph_queries.cypher)는 `rcp -[:RCP_HAS_STEP]-> rcp_step`을 `step_no` 순으로 읽는다. LLM 근거(`build_context`)에는 이미지·조리 과정이 들어가지 않으므로 LLM 설명과 검증 결과는 이 기능 추가 전과 같다.

Java 관점에서 `@dataclass`의 `Recommendation(...)`은 필드 생성자를 자동 제공한다. 반환 행 `dict`의 키는 Cypher `AS` 별칭과 일치해야 한다. `context_rows`가 없으면 `{}`를 써서 선택 필드를 비운다. Neo4j 호출·예외를 Repository가 감싼 뒤 Service로 돌려주지만, `_query`의 `pantry_graphrag` 경로는 Repository의 공개 `query_example`을 우회해 mapper에 직접 접근한다.
