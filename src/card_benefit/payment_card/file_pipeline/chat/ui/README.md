# chat/ui/

사용자 소유 v2 Streamlit 화면이다. 실행은 `chat/run_fp_chat_v2.py` 가 어댑터를 적용한 뒤 이 폴더의 `app_v2.py` 를 `runpy` 로 불러 시작한다.

| 파일 | 역할 |
|---|---|
| `app_v2.py` | v2 Streamlit 화면을 구현한다. 직접 실행하면 팀 `rag`의 Anthropic 임포트 오류가 발생하므로 직접 실행하지 않고 `run_fp_chat_v2.py`로 실행한다. |
| `ui_v2.py` | 화면과 독립적인 질문 분석, 출처 및 비교표 구성 도우미다. 화면 라이브러리 없이 임포트된다. |

- `app_v2.py` 는 저장소 루트를 `HERE.parents[5]` 로 찾고 `chat/` 폴더와 `src/graphrag_chatbot` 을 `sys.path` 에 넣는다. 이 폴더를 더 옮기면 숫자를 같이 바꾼다.
- 임포트는 `payment_card.file_pipeline.chat.ui.<모듈>` 이다. 스크립트식 임포트(`from ui import ui_v2`)가 필요하면 `PYTHONPATH` 에 `chat/` 폴더를 포함한다.
