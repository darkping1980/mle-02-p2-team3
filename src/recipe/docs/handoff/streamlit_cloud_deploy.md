# 냉장고 재료 추천 GraphRAG — Streamlit Community Cloud 배포 안내

## 준비된 파일 (과제 폴더 기준)

| 파일 | 역할 |
|---|---|
| `streamlit_app.py` | 진입 파일. 입력 → `PantryGraphRAG`(입력 해석 → Neo4j AuraDB 조회 → LLM 추천 이유) → 화면 |
| `requirements.txt` | Cloud 의존성. 화면 실행에 필요한 7개 패키지만 둔다(저장소 루트 `uv.lock`의 무거운 패키지 회피) |
| `.streamlit/secrets.toml.example` | Cloud Secrets 입력 형식. 실제 `secrets.toml`은 `.gitignore` 대상 |

Community Cloud는 **진입 파일과 같은 폴더의 의존성 파일을 먼저** 찾는다(`uv.lock` → `Pipfile` → `environment.yml` →
`requirements.txt` → `pyproject.toml`, 없으면 저장소 루트). 과제 폴더에는 `requirements.txt`만 있으므로 그것을 쓴다.
2026-10-23 새 Python 3.12 가상환경에 `requirements.txt`만 설치해 실제 AuraDB 조회 화면이 동작함을 확인했다.

## 배포 절차

1. 배포할 커밋을 GitHub `main`에 푸시한다(2026-10-23부터 별도 작업 브랜치 없이 `main` 하나로 개발·배포).
2. <https://share.streamlit.io> 에 GitHub 계정으로 로그인 → **Create app** → *Deploy a public app from GitHub*.
3. Repository `darkping1980/graph-rag`, Branch `main`,
   Main file path `src/graph_rag/2_graphrag/과제_공공데이터로-그래프-만들기_금요일까지/streamlit_app.py`.
4. **Advanced settings**: Python **3.12**, Secrets에 `.streamlit/secrets.toml.example` 항목을 실제 값으로 입력.
5. Deploy → 첫 화면에서 기본 입력 `계란, 두부, 양파`로 **레시피 추천** 실행.
6. 강사님께 앱 URL을 공유한다. 앱 공개 범위는 Cloud의 Sharing 설정에서 정한다.

확인할 점:
- 진입 경로에 한글 폴더명이 있다. 입력이 거부되거나 앱이 파일을 못 찾으면 그 증상을 기록하고, 영문 경로의 얇은
  진입 파일을 두는 방법을 검토한다(이때 그 폴더에도 `requirements.txt`가 있어야 루트 `uv.lock`을 쓰지 않는다).
- 상단 배지가 `Neo4j AuraDB 연결됨`, `LLM <모델명>`이면 정상. LLM 설명은 보라색 **LLM 설명** 배지,
  대체 응답은 회색 **규칙 기반 설명** 배지와 상단 알림(빨강: 호출 실패, 파랑: LLM 미설정, 노랑: 일부 교체)으로 구분된다.
- AuraDB Free는 일정 기간 사용하지 않으면 일시 중지된다. 화면에 연결 실패가 나오면 Neo4j 콘솔에서 재개한다.

## 화면에서 하는 일 (DB 변경 없음)

- 실행 쿼리는 `pantry_recommend_service.ALLOWED_STATEMENTS`의 읽기 전용 Named Cypher 5개뿐이다(테스트로 쓰기 절 없음 확인).
- PostgreSQL에는 접속하지 않는다.
- 레시피·사용/부족 재료는 Neo4j 조회값이고 LLM은 추천 이유 문장만 만든다. 근거 밖 레시피·재료가 나온 문장은 근거 문장으로 바꾼다.
