# extraction/report/

저장된 실행 결과를 숫자로 집계하는 보고·진단 도구다. 인용문 본문은 출력하지 않는다. 실행은 `payment_card.file_pipeline.extraction.report.<모듈>` 로 한다. 저장소 루트 계산은 `Path(__file__).resolve().parents[6]` 이다.

| 파일 | 역할 |
|---|---|
| `__init__.py` | `report`를 패키지로 표시한다. |
| `ambiguity_report.py` | 인용문 본문 없이 근거 위치의 모호성 통계를 집계한다. |
| `full_run_report.py` | 전체 실행의 검증·위치·항목·표 밀도 지표를 종합한다. |
| `item_loss_report.py` | 실행 그룹 사이 항목의 추가·누락·변동을 본문 없이 집계한다. |
| `table_density_report.py` | 청크 텍스트 기반 거친 표 밀도와 추출 지표를 비교한다. |
