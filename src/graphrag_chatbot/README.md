# GraphRAG 챗봇 (Streamlit + Supabase)

질문 → 엔티티 선택 → PostgreSQL 그래프 탐색 → 답변 스트리밍, 그리고 근거 그래프와 출처를 함께 보여주는 챗봇입니다.

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `app.py` | Streamlit 화면. 검색창, 대화 기록, 검색 단계, 근거 그래프 |
| `rag.py` | GraphRAG 로직. `answer(question)`이 `{answer, sources, subgraph, steps}`를 반환 |
| `db.py` | DB 연결과 읽기 전용 조회. 스키마 이름(`graphrag`)과 테이블 상수는 여기 한 곳 |
| `timing.py` | 질문 1건의 구간별 소요 시간을 `errors/timing.jsonl`에 기록 (`.gitignore`에 포함) |
| `llm.py` | LLM 호출 (기본 Claude). 다른 LLM이면 이 파일만 수정 |
| `graph_view.py` | 하위 그래프를 pyvis로 그리기 (노드 타입별 색) |
| `supabase_schema.sql` | `graphrag.nodes`, `graphrag.edges` 테이블과 샘플 데이터 (Supabase SQL Editor에서 실행) |
| `migrate_public_to_graphrag.sql` | 예전 `public.nodes/edges`를 만들었을 때만 한 번 실행해 `graphrag` 스키마로 옮김 |
| `tests/` | 가짜 DB·LLM으로 도는 오프라인 시험 |
| `check_db.py` | 연결과 테이블 상태를 읽기 전용으로 확인 |

## 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # DB_URL, ANTHROPIC_API_KEY 입력
python check_db.py          # SELECT 1, graphrag.nodes/edges 행 수, 엔티티 목록 확인
streamlit run app.py
```

이 폴더(`graphrag-chatbot`)에서 실행합니다. 폴더 이름에 하이픈이 있어 파이썬 패키지로 import할 수 없으므로, 파일 경로로 실행하는 방식을 유지합니다.

## 시험 (DB·API 키 없이)

```bash
python -m unittest discover -s tests -t . -v
```

가짜 DB와 가짜 LLM으로 흐름, `graphrag` 스키마 사용, 측정 로그를 확인합니다. 실제 Supabase/Claude 동작을 증명하지는 않습니다.

## 응답 속도 측정

질문을 보낼 때마다 `errors/timing.jsonl`에 한 줄이 쌓입니다. 구간: `entities_db`(엔티티 목록 조회), `analyze_llm`(질의 분석), `explore_db`(그래프 탐색), `first_token`(첫 글자까지), `stream`(첫 글자부터 끝까지). 질문은 앞 40자만 남습니다. 위치를 바꾸려면 `TIMING_LOG_DIR`을 설정하세요.

## 내 데이터에 맞게 바꾸기

- **노드·관계**: `nodes.name`이 검색 키입니다. `label`(Service, Team 등)은 자유롭게 쓰고, 색은 `graph_view.py`의 `STYLE`에서 지정합니다.
- **출처**: `Document` 라벨 노드를 출처로 보여줍니다. `props`에 `summary`가 있으면 함께 표시합니다.
- **프롬프트**: `rag.py`의 `ANALYZE_SYSTEM`, `ANSWER_SYSTEM`을 도메인에 맞게 고칩니다.

## 알려진 한계

- 엔티티 선택은 노드 이름 목록(최대 500개)을 LLM에 넘기는 방식입니다. 그래프가 크면 전문 검색이나 pgvector 검색으로 바꾸세요.
- 질문마다 DB 연결을 새로 엽니다. 사용자가 많아지면 연결 풀(`psycopg_pool`)을 쓰세요.
- 그래프 노드를 눌러 Python으로 이벤트를 받는 기능은 없습니다(마우스를 올리면 속성 툴팁만 표시).
- 후속 질문은 직전 2개 대화만 맥락으로 씁니다.
- 앱은 DB를 읽기만 합니다. 데이터 입력은 SQL Editor나 별도 스크립트로 하세요.
- 팀 저장소의 공통 DB 세션(`src/common`)과 OpenAI 설정은 쓰지 않고, 이 챗봇은 `psycopg` 직접 접속과 Anthropic을 씁니다. 합칠 때 결정할 사항입니다.
