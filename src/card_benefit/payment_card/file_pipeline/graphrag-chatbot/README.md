# GraphRAG 챗봇 (Streamlit + Supabase)

질문 → 엔티티 선택 → PostgreSQL 그래프 탐색 → 답변 스트리밍, 그리고 근거 그래프와 출처를 함께 보여주는 챗봇입니다.

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `app.py` | Streamlit 화면. 검색창, 대화 기록, 검색 단계, 근거 그래프 |
| `rag.py` | GraphRAG 로직. `answer(question)`이 `{answer, sources, subgraph, steps}`를 반환 |
| `llm.py` | LLM 호출 (기본 Claude). 다른 LLM이면 이 파일만 수정 |
| `graph_view.py` | 하위 그래프를 pyvis로 그리기 (노드 타입별 색) |
| `supabase_schema.sql` | `nodes`, `edges` 테이블과 샘플 데이터 (Supabase SQL Editor에서 실행) |
| `check_db.py` | 연결과 테이블 상태를 읽기 전용으로 확인 |

## 실행

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # DB_URL, ANTHROPIC_API_KEY 입력
python check_db.py          # SELECT 1, nodes/edges 행 수, 엔티티 목록 확인
streamlit run app.py
```

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
