# Codex → Claude Code 인수인계

기준: 2026-11-01, Streamlit MVP 브라우저 검증 완료. 프로젝트 루트 `D:\Bootcamp\vscode\workspace\mle-02-p2-team3`. 카드 발급 전 혜택 검색·비교 GraphRAG. PostgreSQL V6에서 원문·추출·검증을 관리하고 Neo4j로 DRAFT를 전환했다. 현재 목표는 `db_pipeline_origin_search` 로컬 Streamlit Neo4j 조회 MVP이며 LLM·챗봇은 범위 밖이다.

## Claude Code 브라우저 검증 결과 (2026-11-01)

**결론: 브라우저에서 확인한 검증 항목은 모두 통과했고 수정한 코드는 없다.** 이 절이 최신 상태이며, 아래 Codex 기록 중 "브라우저 미검증" 내용은 이 절로 대체한다.

- 방법: 실제 Microsoft Edge(headless)를 임시 프로필로 띄워 `http://127.0.0.1:8501`에서 입력·선택·펼치기를 수행했다. 프로젝트에 패키지나 파일을 추가하지 않았다. 사람이 일반 브라우저로 본 것은 아니다.
- 서버: Codex가 시작한 PID 9336(11:36 시작, 소스 최종 수정 11:35)이 `127.0.0.1:8501`에서 계속 실행 중이며 `/_stcore/health`는 `ok`다. 다시 띄우지 않고 그대로 사용했다.
- 테스트: `test_neo4j_origin_search` 4개 통과.

| 항목 | 결과 |
|---|---|
| 첫 화면 | 제목·DRAFT 경고·검색창 표시, 브라우저 콘솔 오류·예외 0건 |
| 기본 혜택 | 4건 표시: 놀이공원, 대중교통, ONE PICK, STYLE |
| 키워드 검색 | 대중교통 1, ONE PICK 1, one pick 1(대소문자 무관), STYLE 1, 놀이공원 1, 캐시백 3, 빈 검색 4 |
| 상세(규칙·조건·한도·근거) | 놀이공원 1·7·2·13, 대중교통 1·7·1·14, ONE PICK 2·5·3·15, STYLE 2·5·3·14. 기존 기록과 일치 |
| 원문 대조 | 조건·근거 80건을 Neo4j 원문과 공백 제외 비교했다. 내용 누락·변형 0건, 차이는 아래의 목록 기호뿐이다 |
| 개발자 정보 | 혜택 4건 모두 펼침 성공, Cypher와 namespace 표시 확인 |
| 결과 없음 | `일치하는 혜택이 없습니다.` 표시 |
| 연결 오류 | 임시 서버 8502에 가짜 접속정보를 넣어 확인했다. 일반 오류 메시지만 표시되고 접속 주소·드라이버 오류·Traceback이 나오지 않았다. 임시 서버는 종료했다 |

수정하지 않은 관찰 사항:

1. 연결 실패 시 오류 메시지까지 약 45초(측정값 44.6초) 걸리고 그동안 화면 하단이 비어 있다. Neo4j 드라이버의 트랜잭션 재시도 시간이 원인으로 보이나 확인하지는 않았다. 동작 오류는 아니다.
2. `st.write`가 원문을 마크다운으로 해석해 줄 앞의 `- `, `* `가 글머리표로 표시된다. 글자 내용은 그대로지만 기호 자체는 보이지 않는다. 원문 그대로 보려면 `st.text`를 쓰면 된다.
3. PDF 근거 수는 연결 수라 같은 근거가 반복된다. 고유 근거는 놀이공원 11/13, 대중교통 13/14, ONE PICK 12/15, STYLE 11/14다.
4. Streamlit은 입력·선택마다 스크립트를 다시 실행하므로 `connect()`로 드라이버를 새로 만들고 닫는다. 캐시는 적용되어 있지 않다.

실제 호출 구조:

```text
streamlit_app.py (입력·선택마다 위에서 아래로 재실행)
├─ connect() ─ create_neo4j_driver() ─ load_project_environment()  # .env, TLS 검증
├─ Neo4jSearch.list_benefits(keyword) ─ _query(LIST_QUERY)
├─ Neo4jSearch.get_detail(key)
│    ├─ _query(CONTEXT_QUERY)    # 카드·정책·혜택
│    ├─ _query(RULE_QUERY)       # 규칙·대상
│    ├─ _query(CONDITION_QUERY)  # 정책/혜택/규칙 → 조건식 → 분기 → 조건
│    ├─ _query(LIMIT_QUERY)      # 규칙 → 한도
│    └─ _query(EVIDENCE_QUERY)   # 정책/혜택/한도 → 근거 → 청크 → 페이지 → 문서
├─ source(props)                 # source_json 복원
└─ search.driver.close()         # finally
_query → session(READ_ACCESS) → execute_read → tx.run(query, ns=NAMESPACE, ...) → record.data()
```

## 폴더와 원칙

- `db_pipeline/`: PostgreSQL V6 정제·검증, Neo4j 변환. 상태는 `../db_pipeline/PROJECT_STATUS.md`와 구조 비교 문서 참조.
- `db_pipeline_origin_search/`: 위 그래프의 독립적인 읽기 전용 검색.
- `file_pipeline/`: 팀원 담당. 기존 `graphrag-chatbot/`은 Supabase 기반 독립 프로토타입. 팀원 구현 코드 수정 금지.
- `file_pipeline_origin_search/`: 향후 팀원과 협의하는 Neo4j 검색, 미구현.
- 공통 `tests/`, `main.py`, `models.py`, `repository.py`. 기존 main 실행 동작 변경 금지.

Aura `6ac1f0f8`에는 ONE PICK STYLE 시험 그래프 노드 108·관계 168, `A8Test`, `namespace=ONE_PICK_STYLE_A8`이 있다. 정책 DRAFT·혜택 PENDING_REVIEW·근거 PENDING이며 사용자용 확정 정보가 아니다. `A8Card`→`A8Policy`→`A8Benefit`→`A8Rule`, 조건 Expression→Branch→Condition, LimitPool, Evidence→Chunk→Page→Document 관계가 실재한다. 원문 및 일부 상태는 `source_json`에 있다.

## Codex 구현 기록

- 생성: `__init__.py`, `neo4j_search.py`, `streamlit_app.py`, `README.md`, `../file_pipeline_origin_search/README.md`, `../tests/test_neo4j_origin_search.py`.
- 기존 `../db_pipeline/README.md`와 `../file_pipeline/README.md`는 기존 내용을 유지하면서 실제 구현과 링크를 보완했다. 팀원 Python 소스는 건드리지 않았다.
- `Neo4jSearch.list_benefits(keyword)`는 혜택명 부분 검색. `get_detail(key)`는 context, rules, conditions, limits, evidence 반환. `_query`는 Neo4j `READ_ACCESS`와 `execute_read`, namespace 매개변수를 사용한다. `connect()`는 기존 `src/recipe/recipe_recommender/neo4j_connection.py`의 `create_neo4j_driver()`를 재사용하며 certifi 또는 지정 CA로 TLS 검증을 유지한다. UI는 `source()`로 `source_json`을 읽는다.
- 실제 Aura 조회 성공: 빈 검색 4, ONE PICK 1, STYLE 1, 대중교통 1, 놀이공원 1, 캐시백 3, 없는 문자열 0. 4개 혜택의 상세 조회 성공: 놀이공원 규칙 1·조건 7·한도 2·근거 13, 교통 1·7·1·14, ONE PICK 2·5·3·15, STYLE 2·5·3·14. 근거는 정책 공통·혜택·한도를 포함하는 연결 수이며 중복 인용이 있을 수 있다.
- Streamlit 화면은 검색·선택·규칙/대상·조건 범위와 OR/AND/NOT·한도·근거·개발자 JSON/Cypher·DRAFT 경고·빈 결과/연결 오류 처리를 구현했다. UI의 실제 렌더링은 아직 확인 필요. 오류는 비밀정보 노출 방지를 위해 일반 메시지만 표시한다.
- 상세 쿼리의 `ORDER BY r.rule_key`는 집계 후 원 변수 접근 오류가 발생해 `ORDER BY rule.rule_key`로 수정했고 실제 상세 조회에 성공했다.

## Codex 마지막 실행 기록 (당시 기준, 위 검증 결과로 대체됨)

**후속 확인:** AppTest 경로를 절대 경로로 수정했다. 동일 테스트는 샌드박스에서 중단되는 현상이 있었으나 승인된 샌드박스 밖 실행에서 4개 모두 통과했다(빈 결과·연결 오류 메시지 포함). Streamlit은 `--server.address 127.0.0.1 --server.port 8501`로 실행 중이고 `/_stcore/health`가 HTTP 200 `ok`였다. 브라우저 UI 확인을 시도했으나 Windows Computer Use가 현재 브라우저 URL을 정책상 안전하게 확인하지 못해 해당 턴의 Computer Use를 중지했다. 따라서 화면 렌더링·실제 브라우저 상호작용은 미검증이다. README 실행 명령에도 로컬 주소를 반영했다. 아래 번호는 과거 오류 기록 및 남은 검증 항목으로 읽는다.

1. `python -m unittest src.card_benefit.payment_card.tests.test_neo4j_origin_search -v`에서 4개 중 2개가 실패했다. 원인: `AppTest.from_file()` 상대 경로가 테스트 파일 기준으로 해석돼 APP 경로가 중복됐다. `Path(__file__).resolve().parents[1] / 'db_pipeline_origin_search/streamlit_app.py'` 같은 절대 경로로 고친다. 종료 시 sandbox 임시 디렉터리 PermissionError도 출력됐으므로 재현 시 허용된 workspace 임시 경로 사용이나 실행 권한 확인. 순수 쿼리 범위와 JSON 테스트 2개는 통과했다.
2. `python -m streamlit run ... --server.headless true --server.port 8501`은 서버 시작 성공했으나 `:::8501` 바인딩을 확인해 즉시 중지했다. 로컬 전용으로 `--server.address 127.0.0.1`을 붙여 재실행하고 `http://127.0.0.1:8501/_stcore/health` 확인. README 명령에도 로컬 바인딩 추가 필요.
3. AppTest로 기본 조회·검색 입력·결과 없음·접속 오류를 검증하고 가능하면 브라우저 UI를 확인한다. 연결 실패 시 상세 오류/비밀번호가 화면에 나오지 않아야 한다.
4. README 네 개의 정확한 명령, 변경 범위, 테스트와 실제 UI 결과를 재확인하고 이 문서를 갱신한다. Neo4j/PG 쓰기, 유료 LLM 호출, Git commit/push는 하지 않는다.

## 환경 및 명령

Python `.venv\\Scripts\\python.exe`, 설치된 Streamlit 1.65.0, neo4j 6.4.1, certifi, python-dotenv. 기존 환경변수 이름: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, 선택 `NEO4J_TRUSTED_CA_FILE`; 값은 기록하지 않는다. 기존 `DB_URL`은 이 검색 화면에서 사용하지 않는다. 루트 실행: `.\\.venv\\Scripts\\python.exe -m streamlit run src/card_benefit/payment_card/db_pipeline_origin_search/streamlit_app.py --server.address 127.0.0.1`; 테스트: `.\\.venv\\Scripts\\python.exe -m unittest src.card_benefit.payment_card.tests.test_neo4j_origin_search -v`.

Streamlit 설치 버전의 개발 지침을 읽고 작업 중이다. 함수 호출은 `streamlit_app.py → connect → Neo4jSearch.list_benefits/get_detail → _query → driver session.execute_read → Cypher → dict → Streamlit`. 원본 JSON을 무조건 승인된 조건으로 해석하지 않는다. DB 스키마·데이터, 기존 LLM 응답, 기존 main.py, file_pipeline 구현은 변경 금지. 기존 미커밋 파일을 보호하고 신규 패키지·불필요한 추상화는 추가하지 않는다. Git Commit/Push 금지.
