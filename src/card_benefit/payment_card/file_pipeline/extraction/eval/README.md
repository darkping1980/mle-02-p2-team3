# extraction/eval/

같은 청크를 여러 번 돌린 결과를 비교하거나 합의 항목을 고르는 반복 실행 평가 도구다. 실행은 `payment_card.file_pipeline.extraction.eval.<모듈>` 로 한다. 저장소 루트 계산은 `Path(__file__).resolve().parents[6]` 이다.

| 파일 | 역할 |
|---|---|
| `__init__.py` | `eval`를 패키지로 표시한다. |
| `consensus.py` | 반복 결과에서 기준 횟수 이상 일치한 항목과 관계를 골라 별도 결과를 만든다. |
| `eval_runs.py` | 저장된 실행 결과의 수치 지표를 집계한다. |
| `variance.py` | 반복 실행 결과의 항목 집합·건수 편차를 비교한다. |
| `enum_violation_report.py` | 스키마 enum 위반의 안전한 값·경로 정보를 집계한다. |
| `label_eval.py` | 사람이 만든 추출 라벨과 그래프 근거의 위치 일치도를 평가한다. |
| `prompt_version_compare.py` | 프롬프트 실행 사이 항목·근거 수를 비교한다. |
