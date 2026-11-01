# db_pipeline_origin_search

`db_pipeline`이 PostgreSQL V6에서 변환한 Neo4j 그래프를 **읽기 전용**으로 탐색하는 로컬 Streamlit 화면입니다. ONE PICK STYLE의 `ONE_PICK_STYLE_A8` DRAFT 시험 데이터만 검색하며 확정 상품 정보가 아닙니다. LLM, 챗봇 및 PostgreSQL 접속은 사용하지 않습니다.

프로젝트 루트에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/card_benefit/payment_card/db_pipeline_origin_search/streamlit_app.py --server.address 127.0.0.1
```

기존 프로젝트 `.env`의 `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`를 사용합니다. 검증된 프로젝트 연결 함수가 TLS 인증서 검증을 유지하며 `NEO4J_TRUSTED_CA_FILE` 또는 `certifi` CA를 사용합니다. 인증정보는 화면에 표시하지 않습니다.

빈 검색은 전체 혜택, 입력 검색은 혜택명에 대한 대소문자 구분 없는 부분 일치입니다. 선택한 혜택의 규칙·대상, 카드 공통/혜택/규칙 조건식, 한도, 정책·혜택·한도 근거를 관계 탐색으로 표시합니다. 원문과 검증 상태는 `source_json`을 함께 확인합니다. 100/500원 선택·대중교통 제외의 NOT·CARD_MEMBER·시작일·1인 1매는 미확정입니다. 텍스트 위치 일치는 근거 승인이나 표 행의 의미 검증을 보장하지 않습니다.

호출 흐름: `streamlit_app.py` 검색어·선택 → `connect()` → `Neo4jSearch.list_benefits()` / `get_detail()` → `_query()`의 읽기 트랜잭션과 Cypher → Python 결과 → 화면. `neo4j_search.py`에 쿼리와 연결이 있고 UI는 이를 호출합니다. 원본 JSON과 Cypher는 화면의 개발자 정보에서 확인합니다. 향후 승인 데이터 분리, 더 정밀한 원문 근거와 GraphRAG 검색은 별도 작업입니다.
