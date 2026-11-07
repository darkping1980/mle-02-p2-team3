# 11단계 OpenAI 답변시험 실행기

- PC: laptop
- 상태: 구현 및 표준 테스트 완료, 실제 API·DB 실행 전, 커밋 전

## 목적

Anthropic API와 유료 Claude 사용을 피하고, 승인된 OpenAI `gpt-6-luna`로 챗봇의 실제 `analyze → explore → answer` 경로를 최대 13문항까지 시험할 실행기를 추가했다. 질문 분석 단계에서 LLM이 엔티티 이름을 고르는 흐름을 포함한다.

## 구현

- `openai_llm_patch.py`에 anthropic 기반 팀 `llm.py` 대신 사용할 모듈 주입 및 기존 모듈 함수 교체, usage 누적, 추정 비용 계산, 기본 비용 상한 USD 0.10, 기본 호출 간 지연 0.3초를 구현했다.
- OpenAI 요청은 `max_completion_tokens`를 사용하고 `temperature`를 보내지 않는다. 스트림 요청에는 `stream_options={"include_usage": true}`를 넣고, 스트림이 거부되면 usage를 기록하는 비스트리밍 요청으로 폴백한다.
- `answer_eval.py`와 `run_eval.py --mode answer --llm openai` 연결을 추가했다. 기본 실행은 질문 수, 호출 수, 예상 비용만 표시하고 DB 및 API를 호출하지 않는다. 실제 실행은 `--execute`가 있어야 하며, DB URL을 환경 변수에서 읽어 `fp_chat` SELECT 경로만 사용한다.
- 질문별 선택 시드, 하위 그래프 크기, 답변, 출처 수, 시간, 토큰, 비용을 JSONL에 저장하고 유형별·전체 요약을 출력한다. 연속 3회 오류 또는 비용 상한 초과 시 중단하며, 출력 오류 메시지에는 예외 원문이나 키를 포함하지 않는다.
- 합성 판정은 기대 문자열 정규화, 시드 적중, 출처 여부, 한국어 거절 패턴, 검색 성공·답변 실패와 검색 실패 분류로 구성했다. 판정용 LLM은 호출하지 않는다.
- `chat_eval_check.ipynb`에 합성 판정 셀을 추가했고 코드 셀 출력은 비워 두었다. 모듈 점검 목록에 `chat/answer_eval` 행을 추가했다.

## 안전장치와 검증

- `OPENAI_API_KEY`는 환경 변수에서만 읽고 출력이나 결과에 기록하지 않는다. 질문·답변 원문은 `/tmp` JSONL에만 저장하고 stdout 표에는 넣지 않는다.
- 출력·요약 및 질문 JSON 경로는 저장소 밖 `/tmp` 아래만 허용한다. 비용 상한은 초과 응답의 usage를 반영한 직후 중단한다.
- 가짜 OpenAI 클라이언트와 합성 테스트로 모듈 주입, `rag` import, usage/비용, 상한, 요청 인자, 스트림 폴백, 드라이런, 판정 로직을 확인했다.
- 표준 테스트: `240 passed`.
- 실제 DB 접속, OpenAI 호출, 노트북 실행은 하지 않았다. 금지된 git 쓰기 작업도 하지 않았다.

## 사용자 실행 명령

전제: 사용자가 터미널에서 `OPENAI_API_KEY`를 이미 export했고, `/tmp/fp-human-hana.json` 질문 파일을 준비했다. 각 명령은 `FP_DATABASE_URL`에서 `DB_URL`을 전달하며 비밀값을 출력하지 않는다.

드라이런:

```bash
DB_URL="${FP_DATABASE_URL}" PYTHONPATH="src:src/card_benefit:src/graphrag_chatbot:src/card_benefit/payment_card/file_pipeline/chat" UV_CACHE_DIR=/tmp/uv-cache uv run --project "$PWD" --locked --no-sync python -m payment_card.file_pipeline.chat.run_eval /tmp/fp-human-hana.json --mode answer --llm openai --limit 5 --hops 1
```

3문항 소량 실행:

```bash
DB_URL="${FP_DATABASE_URL}" PYTHONPATH="src:src/card_benefit:src/graphrag_chatbot:src/card_benefit/payment_card/file_pipeline/chat" UV_CACHE_DIR=/tmp/uv-cache uv run --project "$PWD" --locked --no-sync python -m payment_card.file_pipeline.chat.run_eval /tmp/fp-human-hana.json --mode answer --llm openai --execute --limit 3 --hops 1 --max-cost-usd 0.04 --sleep 0.3 --output /tmp/fp-answer-small.jsonl --summary /tmp/fp-answer-small-summary.json
```

하나카드 사람형 13문항 전체 실행:

```bash
DB_URL="${FP_DATABASE_URL}" PYTHONPATH="src:src/card_benefit:src/graphrag_chatbot:src/card_benefit/payment_card/file_pipeline/chat" UV_CACHE_DIR=/tmp/uv-cache uv run --project "$PWD" --locked --no-sync python -m payment_card.file_pipeline.chat.run_eval /tmp/fp-human-hana.json --mode answer --llm openai --execute --limit 13 --hops 1 --max-cost-usd 0.04 --sleep 0.3 --output /tmp/fp-answer-hana-13.jsonl --summary /tmp/fp-answer-hana-13-summary.json
```

## 한계 및 다음 할 일

- 자동 판정은 문자열 규칙이라 의미가 맞아도 표현이 다르면 정답 값을 놓칠 수 있다.
- 하나카드 사람형 표본 13개로는 일반화에 한계가 있다.
- `gpt-6-luna`의 `chat.completions` 호환성과 해당 엔드포인트의 스트림 usage 형식은 실제 호출 전까지 미확인이다.
- 사용자가 드라이런을 확인한 뒤 소량 실행을 하고, 결과 및 실제 비용을 검토한 다음 전체 13문항 실행 여부를 결정한다.
- 커밋 해시: 없음 (커밋 전)
