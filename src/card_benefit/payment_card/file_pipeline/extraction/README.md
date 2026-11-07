# extraction/

5~7단계 파일 기반 추출의 스키마, 근거 위치 변환, 청크 실행 파이프라인과 저장 결과 평가·검토 도구를 둔다. 입력·출력 결과는 사용자가 지정하며, PDF 원문이나 인용문이 포함될 수 있는 검토 산출물은 저장소 밖에 둔다.

## 하위 폴더

| 폴더 | 내용 |
|---|---|
| [`report/`](report/README.md) | 저장된 실행 결과를 숫자로 집계하는 보고·진단 도구다. 인용문 본문은 출력하지 않는다. (4개) |
| [`review/`](review/README.md) | 사람이 원문과 대조하는 검토 자료를 준비하고 판정을 집계하는 도구다. (5개) |
| [`eval/`](eval/README.md) | 같은 청크를 여러 번 돌린 결과를 비교하거나 합의 항목을 고르는 반복 실행 평가 도구다. (6개) |

파일 표의 `report/`, `review/`, `eval/` 경로는 이 하위 폴더를 뜻한다. 이동한 모듈은 `payment_card.file_pipeline.extraction.<폴더>.<모듈>` 로 실행·임포트한다(예: `python -m payment_card.file_pipeline.extraction.eval.variance`).

## 파이프라인 본체·실행 지원

| 파일 | 역할 |
|---|---|
| `__init__.py` | 추출 스키마와 근거 위치 변환 패키지를 표시한다. |
| `schema.py` | 온톨로지 v1 추출 데이터 구조와 허용 관계를 정의한다. |
| `evidence.py` | 인용문을 청크에서 찾아 쪽 원문 기준 위치로 변환한다. |
| `prompt.py` | 청크 하나의 온톨로지 v1 추출 프롬프트를 만든다. |
| `llm_adapter.py` | OpenAI/LangChain 호출 함수를 지연 생성하고 안전한 오류 정보를 제공한다. |
| `runner.py` | 청크 하나를 호출·해석·검증하고 인용 위치를 부여한다. |
| `parallel.py` | 청크 실행을 병렬화하고 분류된 재시도 및 중단 처리를 제공한다. |
| `batch.py` | 청크 문서를 순회해 결과·문서 요약을 저장하고 재개를 지원한다. |
| `cli.py` | 표본 선정, 추정, 실행, 요약, 검증 및 진단 명령을 제공한다. |
| `pilot.py` | 오프라인 표본 청크 선정과 프롬프트 크기 추정을 수행한다. |
| `pilot_run.py` | 표본 선정부터 계획·실행·요약·검증·그래프 내보내기까지 조정한다. |
| `result_a.py` | 결과 A 초안 JSONL을 내보낸다. 8단계 비교 상대 형식과 조정이 남아 있다. |
| `relocate.py` | 유일하게 일치하는 공백·문장부호 변형의 인용 위치를 별도 결과로 복구한다. |
| `ocr_pages.py` | 인덱스된 이미지 PDF를 Tesseract로 처리해 쪽 단위 원문 추적 JSON을 만든다. |
| `ocr_review_sheet.py` | 스캔 PDF의 오프라인 OCR 검수 자료를 만든다. |

## 보고·평가·검토·진단 도구

| 파일 | 역할 |
|---|---|
| `review/accuracy_review.py` | 추출 표본의 사람 정밀도 검토 자료를 준비하고 판정을 집계한다. |
| `report/ambiguity_report.py` | 인용문 본문 없이 근거 위치의 모호성 통계를 집계한다. |
| `eval/consensus.py` | 반복 결과에서 기준 횟수 이상 일치한 항목과 관계를 골라 별도 결과를 만든다. |
| `diagnose.py` | 빈 추출 결과를 제목·길이·키워드 수 신호로 분류한다. |
| `review/empty_review.py` | 반복 실행에서 빈 청크의 사람 검토 자료를 준비하고 집계한다. |
| `eval/enum_violation_report.py` | 스키마 enum 위반의 안전한 값·경로 정보를 집계한다. |
| `eval/eval_runs.py` | 저장된 실행 결과의 수치 지표를 집계한다. |
| `report/full_run_report.py` | 전체 실행의 검증·위치·항목·표 밀도 지표를 종합한다. |
| `report/item_loss_report.py` | 실행 그룹 사이 항목의 추가·누락·변동을 본문 없이 집계한다. |
| `eval/label_eval.py` | 사람이 만든 추출 라벨과 그래프 근거의 위치 일치도를 평가한다. |
| `locate_diagnose.py` | 인용 위치 실패 유형을 원문 없이 분류한다. |
| `eval/prompt_version_compare.py` | 프롬프트 실행 사이 항목·근거 수를 비교한다. |
| `review/review_auto_audit.py` | 사람 검토표의 인용 위치·숫자 근거를 오프라인 검사한다. |
| `review/review_sheet.py` | 추출 결과와 쪽 원문을 대조할 사람 검토표를 만든다. |
| `review/review_tally.py` | 검토표의 사람 판정을 집계한다. |
| `report/table_density_report.py` | 청크 텍스트 기반 거친 표 밀도와 추출 지표를 비교한다. |
| `eval/variance.py` | 반복 실행 결과의 항목 집합·건수 편차를 비교한다. |
| `verify.py` | 저장 결과의 숫자·관계·근거 위치 관련 거친 자동 신호를 검사한다. |

보고 도구의 지표는 기계적 신호이며 추출 의미의 정확성을 확정하지 않는다. 사람이 원문을 보는 자료에는 원문이 들어갈 수 있다.

`pilot_hana_15299/`에는 하나카드 한 문서의 추적성 실행·원문 대조 파일럿 기록이 있다.
