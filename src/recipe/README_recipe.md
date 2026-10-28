# Recipe GraphRAG — 참고 구현체

이 폴더는 식약처 공공데이터 기반 레시피 GraphRAG의 구현 코드와 DB 설계 자료입니다. 2차 팀 프로젝트에서는 **직접 수정할 신규 업무 코드가 아니라 공통 구조를 참고하는 예제**로 사용합니다.

## 핵심 경로

- `streamlit_app.py`: Streamlit 시연 화면
- `recipe_recommender/pantry_graphrag.py`: LangGraph 입력 해석 → 검색 → 답변 흐름
- `recipe_recommender/pantry_recommend_service.py`: 레시피 추천 로직
- `recipe_recommender/recipe_graph_repository.py`: Neo4j QuerySession/Mapper 기반 Repository
- `recipe_recommender/recipe_repository.py`, `recipe.sql`: PostgreSQL Repository/Mapper
- `recipe_recommender/setup/`: 데이터 적재
- `recipe_recommender/tests/`: 유닛/통합 테스트
- `recipe_recommender/tools/`: 읽기 연결 점검, 데이터 재구축 도구 (주의)
- `docs/db/`, `docs/neo4j/`: 실제 설계·검증 문서
- `docs/guide/`: 컴포넌트·실행·데이터 흐름 학습 문서
- `../data/COOKRCP01.csv`: 원본 CSV

## 실행 (저장소 루트 기준)

```powershell
uv sync --locked
uv run python -m streamlit run src/recipe/streamlit_app.py
```

실제 추천/조회는 Neo4j 설정과 적재된 데이터가 필요합니다. LLM 미설정 시에는 가능한 범위에서 규칙 기반 설명을 사용합니다.

DB 접속 없는 테스트:

```powershell
uv run python run_offline_tests.py
```

**주의:** 전체 레시피 테스트 중에는 실제 DB로 조회하거나 데이터를 쓰는 항목이 있습니다. `run_offline_tests.py`는 DB 설정을 비워 오프라인 경로만 확인합니다. 데이터 재구축/초기화 도구는 운영 DB에서 실행하지 마세요.

현재 PostgreSQL 목표 스키마 설명: `docs/db/recipe_target_schema.sql`, `docs/db/recipe_target_rebuild_runbook.md`.
GraphRAG 모델 설명: `docs/neo4j/neo4j_model_design.md`.
화면 흐름 설명: `docs/guide/04_execution_flow.md`.
