# CARD10 GraphRAG Golden Evaluation Dataset v1

## 목적과 범위

50개 기존 질문(CARD10-001~050), 기존 Notion Streamlit baseline, 공식 상품설명서 PDF 페이지 근거를 한 레코드로 연결한다. 과거 Notion의 27 정답·19 오답·4 실행 오류는 역사적 검수값이며, 새로운 Ground Truth나 새 판정으로 복사하지 않는다. 이 v1에서는 독립 PDF 대조가 끝난 질문만 `PDF_VERIFIED`로 둔다.

## 파일

- `card10_graphrag_golden_dataset_v1.jsonl`: 질문별 구조화 레코드. 한 줄이 한 문항이다.
- `card10_graphrag_evaluation_v1.csv`: Excel 검수용 UTF-8 BOM CSV. 여러 PDF 근거는 JSON 배열 문자열로 직렬화했다.
- `card10_graphrag_evaluation_report_v1.md`: 현재 분포, 관찰 및 재평가 절차.

## 근거 출처 주의

`official_pdf_evidence`는 등록 PDF 파일명·문서 ID·SHA-256·페이지와 추출/시각 확인 텍스트를 담는다. 내부 `evidence_ids`/`source_chunk_id`는 기존 PostgreSQL 백업의 추출 메타데이터를 연결한 값이며 PDF 본문 인용과 구별한다. 카탈로그상 URL이 미확정인 문서는 `source_provenance_note`를 확인하고, 문서 출처 검증 전에는 최종 기준답안 승격을 보류한다. 이미지형 SIMPLE PDF는 직접 확인한 페이지 일부만 시각 transcription했다.

## 주요 필드

- `question_id`, `hop_count`, `question`, `target_cards`: 기존 질문 식별·대상 보존
- `question_type`: 실제 코드의 intent 명칭(`BENEFIT_DETAIL`, `BENEFIT_LIMIT`, `BENEFIT_CONDITION`, `BENEFIT_COMPARE`, `EVIDENCE_SEARCH`)
- `evaluation_category`: 검수 관점 배열
- `official_pdf_evidence[]`: PDF/페이지/근거 텍스트 및 DB-derived ID provenance
- `expected_answer`, `expected_facts`, `required_conditions`, `required_limits`, `exclusion_conditions`: 기준정답 필드. 미검증은 비워두고 `ground_truth_status=NEEDS_REVIEW`로 둔다.
- `actual_answer`, `execution_status`, `execution_date`, `execution_environment`, `git_commit`, `pipeline_version`, `evaluation_run_id`: baseline 답변과 실행 추적. 기록이 없는 값은 null이다.
- `verdict`: CORRECT, PARTIAL, INCORRECT, EXECUTION_ERROR, NEEDS_REVIEW
- `error_type[]`: RETRIEVAL_MISSING, EVIDENCE_MISSING, EXTRACTION_LOSS, DATA_MAPPING_ERROR, LIMIT_ERROR, CONDITION_ERROR, EXCLUSION_ERROR, TIER_SELECTION_ERROR, COMPARISON_INCOMPLETE, UNSUPPORTED_UNCERTAINTY, HALLUCINATION, ANSWER_VALIDATION_ERROR, EXECUTION_EXCEPTION, OTHER 중 사용
- `historical_notion_review`: 기존 Notion 체크/메모를 새 판정과 분리 보존

## 판정 기준

의미·수치·조건·적용범위·제외조건을 공식 PDF와 대조한다. 정답이 일부만 맞거나 비교 핵심을 누락하면 PARTIAL, 핵심 사실이 잘못되면 INCORRECT, 생성 자체가 실패하면 EXECUTION_ERROR, 원문 또는 해석이 부족하면 NEEDS_REVIEW다. Notion 체크 상태나 기존 AI 답변은 정답 근거가 아니다.

## 재평가 및 버전 관리

1. v1 baseline을 수정하지 말고 새 실행별 JSONL snapshot/version을 만든다.
2. 동일한 50개 `question`을 새 pipeline에서 실행하고 `evaluation_run_id`, 실행일시, Git SHA, pipeline version, 환경을 채운다.
3. 생성 결과는 `actual_answer`에 새 run별로 보존한다. 기존 baseline을 덮어쓰지 않는다.
4. 인간 검수자가 PDF 원문으로 expected facts/evidence를 확정하고 `ground_truth_status=PDF_VERIFIED`로 바꾼다.
5. 판정자, 검수 시각, verdict, 이유, 오류 유형을 기록한다. Ground Truth 변경은 데이터셋 버전을 올리고 변경 이유를 남긴다.

## 현재 한계

현재 v1은 질문/Notion baseline/PDF 페이지 연결을 모두 보존하지만, 독립 기준정답 작성 및 의미 판정 완료는 CARD10-029 한 건뿐이다. 나머지는 NEEDS_REVIEW이며 완성된 정답셋으로 오인해서는 안 된다. 보고서의 분포를 확인한 뒤 우선순위에 따라 사람 검수를 진행한다.
