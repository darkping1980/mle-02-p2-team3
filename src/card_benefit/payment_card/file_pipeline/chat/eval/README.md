# chat/eval/

챗봇 답변·검색을 오프라인으로 평가하는 도구다. 데이터베이스나 OpenAI 는 코드에서 명시적으로 실행 경로를 고를 때만 호출한다. 실행은 `python -m payment_card.file_pipeline.chat.eval.<모듈>` 이며, 평가 결과 파일은 `/tmp` 아래에만 쓴다.

| 파일 | 역할 |
|---|---|
| `eval_questions.py` | 그래프 CSV의 메타데이터로 결정적인 질문 JSON을 생성한다. |
| `run_eval.py` | 질문 평가를 실행하고 답변·검색 지표를 계산하는 CLI다. |
| `retrieval_eval.py` | CSV 또는 데이터베이스 그래프를 대상으로 검색 결과를 평가한다. |
| `seed_matcher.py` | 검색 평가에서 이름 메타데이터를 기준으로 시드를 결정적으로 선택한다. |
| `golden_set.py` | 사람이 작성한 골든셋 CSV를 평가 하네스의 질문 JSON으로 변환한다. |
| `golden_sampler.py` | 골든셋 작성용 PDF 쪽 표본을 선택한다. |
| `golden_eval.py` | 골든셋과 저장된 결과를 평가하고 요약한다. |
| `fact_judge.py` | 답변 사실을 규칙으로 먼저 비교하고 선택적으로 LLM 판정을 수행한다. |
| `latency_bench.py` | 그래프 조회·탐색 경로의 지연시간을 비교한다. |
| `entity_dup_probe.py` | 질문별로 같은 엔티티 중복이 검색 결과에 미치는 영향을 시뮬레이션한다. |
| `retrieval_stability.py` | 같은 질문을 반복해 검색 결과(노드 집합) 흔들림을 측정한다. |
| `value_conflicts.py` | 질문과 그래프를 조사해 유사 혜택 사이의 수치 충돌을 오프라인으로 점검한다. |
| `golden_set_template.csv` | 사람이 골든셋을 작성할 때 사용하는 열 템플릿이다. |
