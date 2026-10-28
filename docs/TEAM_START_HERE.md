# 2차 팀 프로젝트 — 공통 구조 시작 가이드

## 목적

- 신규 프로젝트의 데이터 모델과 업무 코드는 기존 레시피 구현으로부터 **독립**시키기
- 재사용 가능한 공통 기능만 `src/common`에 유지
- 초보 팀원도 가장 작은 샘플 → 계층형 샘플 → 레시피 실제 구현 순서로 구조를 이해할 수 있게 만들기

## 권장 학습 순서

1. **공통 계약**: `src/common/query_session.py`의 `select_list`, `select_one`, `execute`, `execute_many`, `transaction`
2. **작은 예제**: `src/graph_rag_sample/step_01_basic`에서 SQL/Cypher Mapper와 DB Session의 관계
3. **계층 분리**: `src/graph_rag_sample/step_02_layered`에서 Main → Service → Repository → Mapper → DB
4. **LLM 연결**: `src/graph_rag_sample/step_03_llm`에서 검색 결과와 LLM 책임 분리
5. **실제 구현 참고**: `src/recipe/streamlit_app.py` → `recipe_recommender/pantry_graphrag.py` → Service → Repository → Cypher
6. **DB 설계 참고**: `src/recipe/docs/db/`과 `src/recipe/docs/neo4j/`를 읽되 새 프로젝트 스키마를 그대로 복사하지 않기

## 안전한 테스트

저장소 루트에서:

```powershell
uv run python run_offline_tests.py
```

- 공통 DB 세션과 Mapper, 단계별 GraphRAG 샘플, 레시피 테스트를 `unittest`로 실행합니다.
- 실행기는 자식 프로세스의 `DB_URL`, `NEO4J_URI`, `OPENAI_API_KEY` 등을 비웁니다. `.env`를 로드하더라도 기존 빈 환경변수가 우선하도록 합니다.
- DB 접속을 요구하는 테스트는 건너뜁니다. 건너뛴 테스트는 통과로 간주하지 않습니다.
- 이 실행기는 실제 PostgreSQL/Neo4j 연결 및 DB 쓰기 결과까지 검증하는 **통합 테스트가 아닙니다**.

## DB 연결이 필요한 경우 (명시적 수행)

```powershell
uv run python -m recipe_recommender.tools.check_supabase_connection
uv run python -m recipe_recommender.tools.check_neo4j_connection
```

이 두 명령은 `SELECT 1` / `RETURN 1` 기반의 읽기 연결 점검입니다. GraphRAG 샘플에서 `--run-db`를 붙이면 DB에 테스트 데이터를 쓸 수 있으므로 별도 테스트 DB에서만 실행하세요.

## 새 프로젝트에 추가할 코드 (예시, 아직 생성하지 않음)

```text
src/<new_project>/
  app.py
  services/
  repositories/
  mappers/
    project.sql
    project.cypher
  tests/
docs/
  architecture.md
  db-schema.md
```

- Mapper는 **애플리케이션 별 폴더**에서 로드합니다. 공통 모듈에 도메인 SQL/Cypher를 넣지 않습니다.
- 새 프로젝트의 DB 구조는 주제 확정 후 설계합니다.
- 실행 명령, 환경변수, DB 초기화/데이터 적재 절차는 개발 전에 README에 합의해 적습니다.
- 실제 DB 수정 도구는 실행 대상과 변경 범위를 먼저 확인하고, 데이터 삭제 작업은 백업과 명시적 확인 후 진행합니다.

## 현재 주의사항

- 공통 패키지의 SQL/Cypher 로거 이름은 기존 호환성 때문에 `car_search_rag.sql` / `car_search_rag.neo4j`가 남아 있습니다. 이름을 바꾸려면 공통 테스트와 레시피 로그 설정도 함께 수정해야 합니다.
- `pyproject.toml` 의존성에는 과거 실험용 패키지가 일부 포함되어 있습니다. 잠금파일 `uv.lock`을 깨뜨리지 않도록 이번 정리에서는 임의 제거하지 않았습니다.
- 실제 DB나 클라우드 배포에 대해 이번 정리의 테스트 성공을 주장하지 않습니다. 개발 환경에서 재검증하세요.
