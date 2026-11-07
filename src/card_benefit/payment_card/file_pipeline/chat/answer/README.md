# chat/answer/

챗봇 답변을 만들고 점검하는 기능이다. `fp_chat_patch.py`, `qa_log.py`, `ui/app_v2.py` 와 평가 도구(`eval/`)가 이 모듈들을 불러 쓴다.

| 파일 | 역할 |
|---|---|
| `answer_format.py` | 답변 형식 지침과 모델 호출 없는 형식 진단을 제공한다. |
| `answer_eval.py` | 저장된 챗봇 답변 판정 함수를 제공하며, 런타임 Q/A 기록에서도 사용한다. 명령줄 실행도 지원한다. |
| `answer_check.py` | 답변 숫자가 검색된 그래프 근거 범위에 있는지 확인하는 순수 판정 함수다. |

임포트는 `payment_card.file_pipeline.chat.answer.<모듈>` 이다. 명령줄 실행은 `python -m payment_card.file_pipeline.chat.answer.answer_eval` 이고, `--execute` 경로는 `chat/` 폴더의 `openai_llm_patch`, `fp_chat_patch` 를 부르므로 스크립트식 실행이면 `PYTHONPATH` 에 `chat/` 폴더를 포함한다.
