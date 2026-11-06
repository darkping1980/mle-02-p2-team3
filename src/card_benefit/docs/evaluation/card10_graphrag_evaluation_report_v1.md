# CARD10 GraphRAG 평가셋 보고서 v1

> v1은 50개 원질문과 Notion baseline 답변/실행 상태, PDF 파일 메타데이터 및 페이지 근거를 연결한 구축물이다. 독립적인 새 판정은 문장 단위 PDF 대조를 통과한 항목만 확정한다. 이번 생성에서 CARD10-029만 사용자가 제공한 실제 재현 답변과 공식 PDF로 독립 확인했고, 나머지 비오류 질문은 `NEEDS_REVIEW`다. 기존 Notion의 27/19/4는 과거 기록이며 신규 판정으로 복사하지 않았다.

- 데이터 행: 50 / 고유 ID: 50
- 기존 Notion baseline 기록: 완료 46, 실행 오류 4; 기존 수기 체크 집계 27개 완료 체크, 19개 오류 체크. 사용자 제공 27/19/4 요약과 문서 체크 방식은 별도 기준이다.
- 신규 판정 분포(현 시점): CORRECT 0, PARTIAL 0, INCORRECT 0, EXECUTION_ERROR 4, NEEDS_REVIEW 46
- 독립 PDF-ground truth 작성 완료: 1; 검수 필요: 49

## 홉별 분포

- 1홉: 총 20; 판정 {'NEEDS_REVIEW': 19, 'EXECUTION_ERROR': 1}
- 2홉: 총 20; 판정 {'NEEDS_REVIEW': 18, 'EXECUTION_ERROR': 2}
- 3홉: 총 10; 판정 {'NEEDS_REVIEW': 9, 'EXECUTION_ERROR': 1}

## 카드별 문항 및 신규 판정

- ONE PICK STYLE: 7 문항; {'NEEDS_REVIEW': 7}
- JADE Classic: 6 문항; {'NEEDS_REVIEW': 6}
- JADE First: 7 문항; {'NEEDS_REVIEW': 7}
- JADE Prime: 7 문항; {'NEEDS_REVIEW': 7}
- 더 심플 하나카드: 6 문항; {'EXECUTION_ERROR': 4, 'NEEDS_REVIEW': 2}
- 카드의정석 SHOPPING: 7 문항; {'NEEDS_REVIEW': 7}
- EVERY WON POINT: 6 문항; {'NEEDS_REVIEW': 6}
- 카드의정석 POINT II: 7 문항; {'NEEDS_REVIEW': 7}
- 카드의정석2 DAILY: 8 문항; {'NEEDS_REVIEW': 7, 'EXECUTION_ERROR': 1}
- 카드의정석2 SIMPLE: 7 문항; {'NEEDS_REVIEW': 7}

## 오류 유형 분포

- EXECUTION_EXCEPTION: 4

## 주요 관찰 및 우선순위

1. **CARD10-029: DATA_MAPPING_ERROR / UNSUPPORTED_UNCERTAINTY** — 실제 사용자 재현 답변은 10,000원·15,000원을 언급하면서 이용실적 구간 연결을 미확정 처리했다. 더 심플 PDF 1쪽의 구간표와 직접 대조해 INCORRECT로 판정했다.
2. **기존 27/19/4는 historical baseline** — 새 판정은 그 값을 그대로 재사용하지 않는다. 46개 질문은 original Notion 답변의 세부 의미 대조와 Ground Truth 원자화가 미완료여서 NEEDS_REVIEW로 둔다. 원본 Notion의 실행 오류 4건은 EXECUTION_ERROR로 보존한다.
3. **검색 vs 답변 생성 분리** — 현 Notion 답변만으로 검색 후보 누락인지, 컨텍스트 구성 오류인지, 생성/검증 문제인지 확정할 수 없다. 재실행 시 retrieval trace/evidence IDs와 answer text를 같은 run ID로 저장해야 한다.
4. **출처 제한** — 프로젝트 catalog에 있는 10개 PDF는 로컬 SHA-256이 catalog와 일치한다. 단, ONE PICK source URL 메타데이터는 추정/공식 출처 미확정 표기이고, 우리카드 일부 URL은 catalog에 없다. 카드의정석2 SIMPLE PDF는 이미지형이어서 직접 시각 검토한 p1/p2 일부만 transcription했다.

## Notion 결과와 차이

Notion의 27 정답·19 오답·4 실행 오류는 과거 사람이 기록한 baseline으로 보존한다. 새 독립판정 집계와 같다고 가정하지 않는다. CSV의 `검수상태`와 JSONL의 `ground_truth_status`는 PDF 기준 검증 진행 상태이고, `historical_notion_review`는 원래 체크와 메모다.

## 재평가 절차

1. 새 실행마다 `evaluation_run_id`, Git SHA, pipeline version, 환경, 실행 시각을 기록한다.
2. 질문 ID 50개를 동일한 질문 문자열로 실행하고 `actual_answer`, `execution_status`, retrieval candidate/evidence trace를 새 run snapshot으로 저장한다. 기존 baseline을 덮어쓰지 않는다.
3. PDF 원문에서 필요한 사실·조건·한도·제외를 원자화하고 근거 페이지를 두 번째 검수자가 확인한 뒤 `ground_truth_status=PDF_VERIFIED`로 승격한다.
4. 사람 검수자는 의미 기준으로 CORRECT/PARTIAL/INCORRECT/EXECUTION_ERROR 판정과 코드 오류 유형을 기록한다. 미확정은 NEEDS_REVIEW로 유지한다.

## 근거/미확인 문항

- PDF 문서 ID/파일명/페이지는 로컬 등록 PDF와 backup catalog를 연결했다. DB evidence ID와 chunk ID는 PostgreSQL 백업의 메타데이터이며 공식 PDF 근거와 동일시하지 않는다.
- 이 버전에서 독립 기준정답 문장과 `expected_facts`가 작성된 항목은 CARD10-029 한 건이다. 나머지 문항의 `expected_answer`는 null로 두었다. 이는 정답 부족을 숨기지 않고 추후 사람이 PDF를 대조하도록 하기 위함이다.
- 실행 오류 질문은 AI 답변을 생성하거나 공식 정답으로 대체하지 않았다.
