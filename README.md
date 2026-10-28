# Team Project Prototype — 공통 구조와 GraphRAG 참고 구현

2차 팀 프로젝트의 출발점으로 재정리한 저장소입니다. 레시피 GraphRAG는 **참고 구현체**이며, 새로운 팀 프로젝트의 주제·DB 모델과 분리합니다.

## 폴더 구조

```text
src/
  common/                    # PostgreSQL/Neo4j QuerySession, Mapper, Logger 및 공통 테스트
  graph_rag_sample/          # Step 1(직접 접근) → 2(Service/Repository) → 3(LLM)
  recipe/
    recipe_recommender/      # 레시피 데이터 적재, DB 접근, GraphRAG, 단위 테스트
    streamlit_app.py         # 레시피 시연 앱
    docs/                    # DB 설계/ERD, 실행 흐름, 검증 문서
  data/COOKRCP01.csv         # 레시피 원천 CSV (기존 위치 유지)
docs/TEAM_START_HERE.md      # 2차 팀 프로젝트 개발 가이드
run_offline_tests.py         # 실제 DB/API 접속을 차단한 테스트 실행
```

레시피는 코드와 문서가 많은 완성형 참고 사례입니다. 새 프로젝트를 작성할 때는 `common`의 공통 접근 계약을 참고하고, 새 도메인의 Repository/Service/Mapper와 DB 설계는 별도로 구성하세요.

## 개발 환경

Python 3.12 이상, `uv` 사용:

```powershell
uv sync --locked
Copy-Item .env.example .env
```

`.env`에는 **실제 사용할 때만** PostgreSQL, Neo4j, OpenAI 설정을 넣습니다. 비밀값은 커밋하지 않습니다. 로컬 환경과 배포 환경에 따라 필요한 설정이 다릅니다.

## 공통 구조 먼저 보기 (DB 연결 없이)

```powershell
uv run python -m graph_rag_sample.step_01_basic.main
uv run python -m graph_rag_sample.step_02_layered.graph_rag_sample
uv run python -m graph_rag_sample.step_03_llm.graph_rag_sample
uv run python run_offline_tests.py
```

위 3개 샘플은 기본 실행에서 DB/API를 호출하지 않습니다. **`--run-db`, `--use-openai` 옵션은 실제 연결/쓰기/유료 호출을 발생시킬 수 있으므로 기본 학습에는 사용하지 않습니다.**

`run_offline_tests.py`는 DB/API 환경변수를 비워 Mock 기반 테스트를 수행하고, DB 연결이 필요한 테스트를 건너뜁니다. 세부 사항은 [팀 개발 가이드](docs/TEAM_START_HERE.md)를 참고하세요.

## 레시피 시연 앱

```powershell
uv run python -m streamlit run src/recipe/streamlit_app.py
```

Neo4j 연결 설정이 있어야 실제 그래프 조회가 가능합니다. LLM 키가 없으면 가능한 범위에서 규칙 기반 설명을 사용합니다. Streamlit Community Cloud 배포에 필요한 최소 패키지는 `src/recipe/requirements.txt`에 별도로 있습니다.

자세한 데이터 구성/적재/스키마/주의사항: [레시피 안내](src/recipe/README_recipe.md), [코드 학습 가이드](src/recipe/docs/guide/README.md).

## 구조 원칙

- `common`: 도메인과 무관한 DB 접근, Mapper, 쿼리 로그, 연결 관리
- `graph_rag_sample`: 계층/DB 연결을 설명하는 작고 독립적인 예제
- `recipe`: **읽고 참고하는 기존 예제**, 신규 도메인과 혼합하지 않음
- 새 프로젝트: 팀에서 확정한 DB 스키마와 서비스 요구에 맞춰 별도 구현
- 테스트: 기본은 오프라인 Mock; 실제 DB 연결/쓰기 테스트는 검증용 DB에서 명시적으로만 수행

원본 전체 파일은 `backup/pre-team-project-cleanup-20261028` 브랜치에서 확인할 수 있습니다.
