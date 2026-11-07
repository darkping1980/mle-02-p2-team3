# extraction/review/

사람이 원문과 대조하는 검토 자료를 준비하고 판정을 집계하는 도구다. 실행은 `payment_card.file_pipeline.extraction.review.<모듈>` 로 한다. 저장소 루트 계산은 `Path(__file__).resolve().parents[6]` 이다.

| 파일 | 역할 |
|---|---|
| `__init__.py` | `review`를 패키지로 표시한다. |
| `empty_review.py` | 반복 실행에서 빈 청크의 사람 검토 자료를 준비하고 집계한다. |
| `accuracy_review.py` | 추출 표본의 사람 정밀도 검토 자료를 준비하고 판정을 집계한다. |
| `review_auto_audit.py` | 사람 검토표의 인용 위치·숫자 근거를 오프라인 검사한다. |
| `review_sheet.py` | 추출 결과와 쪽 원문을 대조할 사람 검토표를 만든다. |
| `review_tally.py` | 검토표의 사람 판정을 집계한다. |
