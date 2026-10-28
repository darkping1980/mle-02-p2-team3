# 냉장고 재료 추천 GraphRAG MVP 인수인계 (2026-10-23, 학원 PC → 집 PC)

상태: **개발 중단(미완성)**. 작업 브랜치 `wip/graphrag-mvp-20261023`에 보존했다. `main`에는 병합하지 않았다.
DB(PostgreSQL·Neo4j) 데이터와 그래프 구조는 이 작업에서 변경하지 않았다(모든 조회는 읽기 전용).

## 1. Git 상태 주의

- `main`의 사용자 커밋 `6519c37`("변경내역 반영", 17:47)에 이 MVP의 초기 파일 2개가 이미 들어가 원격에 있다.
  - `recipe_recommender/pantry_recommend_service.py`(현재 버전과 같음)
  - `recipe_recommender/pantry_graphrag.cypher`(헤더 주석만 이전 버전)
  - 이 두 파일은 어떤 코드에서도 import·실행하지 않으므로 `main`의 기존 기능에는 영향이 없다. 되돌리지 않았다.
- `wip/graphrag-mvp-20261023` = `main`(6519c37) + `pantry_graphrag.py` + `.cypher` 헤더 주석 수정 + 이 문서.

## 2. 완료된 것

| 구분 | 내용 | 파일 |
|---|---|---|
| 재사용 | `RecipeGraphRepository.query_example`(드라이버·TLS·Named Cypher), `normalize_name`, 기존 쿼리 `ingredient_name_candidates`·`pantry_recommendations`·`graphrag_context` | 기존 파일 수정 없음 |
| 신규 쿼리 | `ingredient_vocabulary`(LLM 답변 검증용 식재료·별칭 어휘), `pantry_recommendations_by_coverage`(기존 추천 쿼리와 매칭 같고 정렬만 "보유 재료 많이 쓰는 순") | `recipe_recommender/pantry_graphrag.cypher` |
| 추천 Service | 입력 분리(쉼표·줄바꿈 등, 공백은 나누지 않음), 별칭 해석(계란→달걀), 미등록 재료 구분, 추천 레시피·사용/부족 재료·분류·조리 방법·열량 조회. 실행 쿼리는 허용 목록 4+1개로 제한 | `recipe_recommender/pantry_recommend_service.py` |
| LangGraph | `interpret → retrieve → answer`. 문장형 입력은 LLM 구조화 출력으로 재료를 뽑고, 문장에 없는 재료는 버린다. 답변은 근거 JSON만 주고, 근거 밖 rcp_id·식재료가 나온 문장은 근거 기반 문장으로 교체. LLM 키가 없거나 실패해도 동작 | `recipe_recommender/pantry_graphrag.py` |

실측(학원 PC, AuraDB `6ac1f0f8`, `gpt-6-luna`):
- `계란, 두부, 양파` → 규칙 해석, 보유 재료 달걀·두부·양파, 상위 3개 모두 3개 재료를 사용(두부해물완자, 두부달걀덮밥, 두부스테이크). 약 9초.
- `냉장고에 계란 몇 개랑 두부 반 모, 대파가 남았는데 뭐 해먹지?` → LLM 해석 `['계란','두부','대파']`, 추천 3개, 약 12초.
- 검증 장치가 실제로 동작함: 설명 1건이 근거 밖 재료로 판정되어 근거 문장으로 교체됨(아래 남은 작업 1 참고).

## 3. 남은 작업 (우선순위 순)

1. **검증 오탐 수정**: `닭고기김치찌개` 설명에서 레시피명 속 `닭고기`가 근거 밖 재료로 잡혔다.
   `validate_answer()`에서 검사 전에 레시피명(`rec.rcp_nm`)도 허용 텍스트로 지우도록 고친다.
2. 근거 문장 조사 다듬기(`두부을(를)` 같은 표현), 부족 재료가 많은 경우(물·소금 포함) 화면에서 접어 보이기.
3. 테스트 `recipe_recommender/tests/test_pantry_graphrag.py`: 가짜 Repository·가짜 LLM으로
   입력 분리, 별칭 해석, 근거 밖 rcp_id/재료 차단, LLM 실패 대체, 허용 쿼리에 쓰기 절(CREATE/MERGE/SET/DELETE/REMOVE/DROP) 없음 확인.
   실제 Neo4j 조회 테스트는 읽기 전용으로 `계란, 두부, 양파`.
4. Streamlit 화면 `streamlit_app.py`(과제 폴더 최상위 예정): `st.secrets` → `os.environ` 복사, `st.cache_resource`로
   Repository·LLM 1회 생성, 입력창(기본 `계란, 두부, 양파`), 추천 수·정렬 선택, 입력 해석 결과(별칭·미등록),
   레시피 카드(분류·조리 방법·열량·사용 재료·부족 재료·추천 이유), 근거 JSON 펼치기, 경고 표시.
5. 배포 준비: 과제 폴더에 `requirements.txt`(streamlit, neo4j, certifi, python-dotenv, pydantic, langgraph, langchain-openai),
   `.streamlit/secrets.toml.example`, 루트 `.gitignore`에 `.streamlit/secrets.toml` 추가. Python 3.12 선택.
   Streamlit Community Cloud는 진입 파일 폴더의 requirements를 먼저 찾는다. 진입 경로에 한글 폴더명이 있어 실제 배포에서 확인 필요.
6. 로컬 실행 검증 → Community Cloud 배포 → 강사님 테스트 URL 공유.
7. 검증 후 `main`에 일반 병합(강제 푸시 금지).

## 4. 집 PC에서 이어서 하기

```powershell
cd C:\graph-rag
git fetch origin
git switch wip/graphrag-mvp-20261023          # 처음이면 원격 브랜치를 추적해 만든다
# streamlit은 venv에만 설치했다(pyproject 미반영). uv add/uv sync는 venv 전용 패키지를 지울 수 있어 쓰지 않았다.
uv pip install --python .venv\Scripts\python.exe streamlit

cd "src\graph_rag\2_graphrag\과제_공공데이터로-그래프-만들기_금요일까지"
$py = "C:\graph-rag\.venv\Scripts\python.exe"
# 현재 상태 확인(읽기 전용 Neo4j 조회 + LLM 호출)
& $py -c "from recipe_recommender.recipe_graph_repository import RecipeGraphRepository as R; from recipe_recommender.pantry_recommend_service import PantryRecommendService as S; from recipe_recommender.pantry_graphrag import PantryGraphRAG as G, create_llm; g=R(); s=G(S(g), create_llm()).run('계란, 두부, 양파', limit=3); print(s['answer']['summary']); g.close()"
# 기존 레시피 테스트
& $py -m unittest discover -s recipe_recommender/tests -t .
# (구현 후) 웹 화면
& $py -m streamlit run streamlit_app.py
```

## 5. 필요한 환경변수 (이름만, 값은 저장소 루트 `.env` 또는 Streamlit Secrets)

| 이름 | 필수 | 용도 |
|---|---|---|
| `NEO4J_URI` | 예 | AuraDB 주소(`neo4j+s://...`, 인증서 검증 유지) |
| `NEO4J_USERNAME` | 예 | Neo4j 사용자 |
| `NEO4J_PASSWORD` | 예 | Neo4j 비밀번호 |
| `NEO4J_DATABASE` | 선택 | DB 이름(없으면 서버 기본 DB) |
| `NEO4J_TRUSTED_CA_FILE` | 선택 | 신뢰 CA PEM 경로(없으면 certifi) |
| `OPENAI_API_KEY` | 선택 | LLM 해석·설명. 없으면 규칙·근거 문장으로만 동작 |
| `OPENAI_MODEL` | 선택 | 기본 `gpt-6-luna`(temperature 기본값만 지원해 지정하지 않음) |

`.env`·API 키·비밀번호는 커밋하지 않는다(`.env`는 `.gitignore` 대상). 이 MVP는 PostgreSQL에 접속하지 않는다.

---

## 6. 진행 기록 (2026-10-23, 집 PC)

위 "남은 작업" 1~6 중 배포 실행 전까지 완료했다. DB 데이터·그래프 구조는 변경하지 않았다(모든 조회 읽기 전용).

| 남은 작업 | 결과 |
|---|---|
| 1. 검증 오탐 | `validate_answer()`가 레시피명(띄어쓰기 변형 포함)을 지운 뒤 근거 밖 재료를 찾는다(`mask_phrases`). `닭고기김치찌개`의 `닭고기` 오탐 해소, 레시피명 밖의 근거 없는 `닭고기`는 여전히 차단 |
| 2. 근거 문장 | 받침에 맞는 조사(`두부를`, `달걀, 두부, 양파로`), 부족 재료는 문장에 5개까지만 쓰고 "외 N개", 화면에서는 5개 초과 시 접기 |
| 추가 | 답변에 `llm_status`(`ok`/`partial`/`failed`/`disabled`)·`llm_error`를 담아 화면에서 LLM 설명과 규칙 기반 대체 응답을 구분 |
| 추가 | LLM이 없거나 실패한 **문장형 입력**은 DB 표준명·별칭을 문장에서 직접 찾는다(`term_source='vocabulary'`). 전에는 재료를 하나도 찾지 못했다 |
| 3. 테스트 | `tests/test_pantry_graphrag.py` 21개(가짜 그래프·가짜 LLM + 실제 AuraDB 읽기 전용 1개), `tests/test_streamlit_app.py` 8개(AppTest, 실제 AuraDB 1개). 그래프 mapper 개수 테스트를 44개로 갱신 |
| 4. 화면 | `streamlit_app.py`: 입력 폼(기본 `계란, 두부, 양파`), 정렬·추천 수, 입력 해석 표, LLM 상태 알림, 레시피 카드(분류·조리 방법·열량·사용/부족 재료·이유·출처 배지), 근거 JSON |
| 5. 로컬 실행 | `streamlit run` 서버 health OK, 실제 AuraDB 추천 5건 표시(1위 두부해물완자) |
| 6. 배포 준비 | `requirements.txt`, `.streamlit/secrets.toml.example`, 루트 `.gitignore`에 `**/.streamlit/secrets.toml`. 깨끗한 Python 3.12 환경에서 requirements만으로 동작 확인. 절차: `streamlit_cloud_deploy.md` |

남은 일:
- **집 PC `.env`의 `OPENAI_API_KEY`가 무효(401 invalid_api_key)** 라 실제 LLM 설명은 검증하지 못했다. 화면은 빨간
  "규칙 기반 대체 응답"으로 정상 구분되어 표시된다. 유효한 키로 바꾼 뒤 `계란, 두부, 양파`에서 보라색 "LLM 설명" 배지를 확인한다.
- Streamlit Community Cloud 실제 배포(계정 로그인 필요)와 한글 진입 경로 확인 → 강사님 URL 공유.
- 최종 검증 후 `main`에 일반 병합(강제 푸시 금지).

로컬 실행: `python -m streamlit run streamlit_app.py` (과제 폴더에서, 저장소 루트 `.env` 사용).
