# 카드사 공통 문서 분류 규칙과 인덱스 구축 (v2)

대상: 하나·우리카드 데이터를 이어받아 문서 인덱스를 만들 담당자

## 0. 범위와 전제

- 이번 범위는 신용카드(`credit/`)와 `common/`. 체크카드(`debit/`)는 2단계.
- 원본 PDF와 카드사 원본 manifest는 이름 변경·이동·삭제·열 이름 수정을 하지 않는다.
- 도구 설치(OCR 포함)는 사용자 승인 후에만 한다. 스크립트는 `uv run --locked --no-sync`로 실행한다.

## 1. 확인된 병목과 대응

| # | 병목 | 대응 |
|---|---|---|
| 1 | OCR 도구 없음. 우리 이미지 PDF 다수 | 이번에는 `ocr_needed`만 표시, OCR 미실행 |
| 2 | 시스템 Python에 PDF 라이브러리 없음 | uv 환경에서만 실행 |
| 3 | `src/data/{hana,woori}_all/`는 `.gitignore` 대상 | 인덱스는 `src/card_benefit/data/index/{issuer}/`에 저장 (추적됨, 확인 완료) |
| 4 | 하나 웹페이지 변환 PDF 54개 (53개 카드 중 38개는 공식 PDF와 중복, 15개는 변환본만) | `doc_role=web_capture`로 분리, 대표 선정에서 공식 PDF 우선 |
| 5 | 하나 `common`에 약관과 브랜드 안내 혼재 | `doc_role`로 구분 |
| 6 | 상품 식별자와 경로 기준이 카드사마다 다름 | `product_ids` JSON, `file_path`는 `{issuer}_all/` 기준 |
| 7 | 파일과 상품이 N:M | `documents`와 `product_docs` 분리 |
| 8 | PDF 안 상품명 자동 확인 실패가 많음 | "틀림"이 아닌 `needs_review` 표시 |
| 9 | 기존 `traceability.py`는 PDF 1개 처리용 | 수정하지 않고 후속 단계에서 래퍼 추가 |
| 10 | 우리 기존 108개는 출처 미확인 | `origin=existing_unverified`, 같은 해시의 공식본이 대표 |

## 2. 공통 규칙

1. 폴더 뼈대: `src/data/{issuer}_all/{credit,debit,common}/` 평면. 중간 폴더 금지.
2. 중복: sha256이 같으면 한 문서. 대표(`canonical=Y`)는 해시 그룹당 1건. 순서: ① 공식 PDF ② 공식 PDF(URL 추정 확인) ③ 웹페이지 변환 PDF ④ 기존 미확인본, 같으면 `board_date` 최신, 그다음 파일명이 짧은 쪽. 나머지는 `duplicate_of`로 연결, 삭제하지 않는다.
3. 공식 PDF가 있는 카드의 변환본은 `canonical=N`. 공식 PDF가 없는 카드에서만 변환본이 대표.
4. 판정은 규칙 기반. 우리는 `source_slot`(g1·g1New→`product_guide`, g2·g3·g11·g12→`brand_service`), 하나는 `문서종류`·`문서구분`. 근거 없으면 `unclassified`, 파일명으로 추측하지 않는다.
5. 파일명·`board_date`로 효력일·최신본을 추정하지 않는다.
6. DRM·로그인·CAPTCHA는 우회하지 않고 `review_reason`에 기록한다.
7. 카드 구분이 불확실하면(우리 체크 의심 7종) `needs_review=Y`, `credit`으로 단정하지 않는다.
8. `ocr_needed`: 쪽당 평균 추출 글자 수 50 미만이면 Y.

## 3. 산출물 (`src/card_benefit/data/index/{issuer}/`)

`documents.csv` (파일 1개당 1행):
`issuer, doc_id(sha256 앞 16자), sha256, file_path, card_type(credit|common), doc_role(product_guide|web_capture|brand_service|terms|other|unclassified), canonical, duplicate_of, pages, text_chars, ocr_needed, source_url, origin(official_download|official_url_inferred|web_capture|existing_unverified), board_date, needs_review, review_reason`

`product_docs.csv` (상품과 문서의 연결):
`issuer, product_name, product_ids(JSON), card_type, doc_id, file_path, relation(primary_guide|shared_guide|brand|terms|unclassified)`

구현 시 정한 세부 규칙:
- `doc_id`는 내용(해시) 기준이라 중복 파일은 같은 값을 갖는다. `duplicate_of`에는 대표 파일의 `file_path`를 적는다.
- `shared_guide`는 같은 해시를 둘 이상의 상품이 쓸 때 붙는다(경로가 달라도 해시가 같으면 공유로 본다).
- 공식 상품설명서가 있는 카드의 웹 변환본은 `canonical=N`이면서 `duplicate_of`가 비어 있다. 따라서 "해시 그룹당 `canonical=Y` 1건" 검증은 모든 파일이 `web_capture`인 그룹에는 적용하지 않는다.

## 4. 작업 순서와 완료 기준

1. 선행 확인(읽기 전용): 결과는 §6.
2. 공통 코드와 어댑터(`adapters/hana.py`, `adapters/woori.py`): 원본 manifest를 §3 스키마로 변환만 한다. 중복·대표·OCR 판정·검증은 공통 코드.
3. 인덱스 생성과 검증 (모두 만족해야 완료):
   - 파일 존재율 100% (우리 312건, 하나 다운로드 성공 216건)
   - 모든 sha256 재계산 일치
   - 두 카드사 `documents.csv`의 열 동일
   - 해시 그룹당 `canonical=Y` 정확히 1건
   - `unmapped` 보고
   - `ocr_needed`, `needs_review`, `unclassified`, 중복 그룹 수 보고
4. 후속(별도 승인): `canonical=Y`인 `product_guide`·`brand_service`를 `traceability.py`로 배치 처리. `ocr_needed=Y`는 별도 큐.
5. 신규 카드사 온보딩: §2-1 뼈대로 수집, 어댑터 1개, §4-3 검증 통과.

## 5. 결정 사항

1. 범위: 신용카드와 `common`만. 체크카드는 2단계.
2. 인덱스 위치: `src/card_benefit/data/index/{issuer}/` (확인 완료).
3. 공유 파일: 청크 1개 + 상품 목록. 청크 메타데이터에 `product_ids` 목록을 붙이고, 그래프에서는 상품 노드 여러 개가 같은 문서 노드를 가리킨다. 상품명 기준 검색은 목록 필터로 처리한다.
4. OCR: §6 측정 결과에 따라 후속 단계에서 결정. 설치 전에 사용자 승인을 받는다.

## 6. 선행 확인 결과 (2026-11-02, 읽기 전용)

- uv 환경에서 PyMuPDF·pypdf import 정상. 인덱스 위치는 Git 추적 대상.
- 이미지 PDF (쪽당 평균 50자 미만): 하나 0개, 우리 credit 37개/262개, 우리 common 27개/29개. 하나 debit 70개, common 19개는 모두 텍스트 추출 가능.
- 하나 웹 변환 PDF 샘플 3개: 텍스트 추출은 되나 UI 문구("비교함", "공유하기")가 섞여 있다. 본문 청킹 전에 제거 규칙이 필요하다.

## 7. 구현 현황 (2026-11-02)

- 코드: `src/card_benefit/payment_card/file_pipeline/doc_index/` (`core.py`, `measure.py`, `schema.py`, `adapters/{hana,woori}.py`, `cli.py`), 테스트: `payment_card/tests/test_file_pipeline_doc_index.py`.
- 실행: `PYTHONPATH=src:src/card_benefit uv run --locked --no-sync python -m payment_card.file_pipeline.doc_index.cli --issuer {hana|woori} [--overwrite]`
- 산출물: `src/card_benefit/data/index/{issuer}/{documents.csv,product_docs.csv,summary.json}`
- 후속 단계(§4-4 배치 처리, 노트북 보조 확인)는 아직 하지 않았다.
- 작업 이력: [docs/작업이력/01-문서인덱스-청킹/2026-11-02-카드사-문서-인덱스.md](../../작업이력/01-문서인덱스-청킹/2026-11-02-카드사-문서-인덱스.md)
