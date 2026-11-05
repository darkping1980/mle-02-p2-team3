# 개별 카드 10종 등록·검증 (2026-11-05)

- 대상 목록: 프로젝트 루트 `print_cards_10/README.md`(인쇄용 PDF 10개는 `data/raw` 원본과 SHA-256이 모두 같음). 폴더는 수정하지 않았고, `.git/info/exclude`로 로컬 추적 제외가 유지되고 있다.
- 이전 기록: [INDIVIDUAL_CARD_REGISTRATION_REVIEW.md](INDIVIDUAL_CARD_REGISTRATION_REVIEW.md)(수정 안 함)
- 작업 경로: `C:\myproject\workspace\mle-02-p2-team3`(`D:\Bootcamp\...` 없음), 브랜치 `main`
- **유료 LLM 호출 0건.** DDL·기존 행 수정·삭제 0건. Git 커밋·Push 없음.

## 1. 요약표

| 카드사 | 카드명 | 기존/신규 | 문서 등록 | 혜택 등록 | 조건 등록 | 근거 검증 | 보류 |
|---|---|---|---|---|---|---|---|
| 하나 | ONE PICK STYLE 하나 체크카드 | 기존 card 2 | ✓ 20261101_000002 (2쪽/2청크) | 4 + 연회비 1 (`PENDING_REVIEW`) | 혜택 2건 조건식 보유 | 근거 위치 일치 | 추출 실행이 PARTIAL(EXTRACT_V1), 후보 4건 `NO_EVIDENCE`·`VALUE_NOT_IN_QUOTE` |
| 하나 | JADE Classic | 기존 card 5 | ✓ 20261102_000003 (6쪽/6청크) | **상품 혜택 0** (브랜드 Visa 컨시어지 1 + 연회비 1) | 없음 | 2건 근거 일치 | **상품설명서 추출 이력 없음 → 개별 혜택 누락** |
| 하나 | JADE First | 신규 card 20 | ✓ 20261105_000040 (8/8) | 미실행 | 미실행 | — | LLM 추출 승인 대기 |
| 하나 | JADE Prime | 신규 card 21 | ✓ 20261105_000041 (8/8) | 미실행 | 미실행 | — | LLM 추출 승인 대기 |
| 하나 | 더 심플 하나카드 | 신규 card 22 | ✓ 20261105_000042 (1/1) | 미실행 | 미실행 | — | LLM 추출 승인 대기 |
| 우리 | 카드의정석 SHOPPING | 기존 card 6 | ✓ 20261104_000023 (8/8) | 11 + 연회비 1 (`PENDING_REVIEW`) | 혜택 7건 조건식 보유 | 근거 위치 일치 | 11-04 기록대로 1건 제외·1건 SCOPE_UNRESOLVED |
| 우리 | EVERY WON POINT | 신규 | **미등록** | — | — | — | 텍스트 레이어 제어문자로 품질 게이트 차단(승인 필요) |
| 우리 | 카드의정석 POINT II | 신규 card 23 | ✓ 20261105_000043 (8/8) | 미실행 | 미실행 | — | LLM 추출 승인 대기 |
| 우리 | 카드의정석2 DAILY | 신규 | **미등록** | — | — | — | 텍스트 레이어 제어문자로 품질 게이트 차단(승인 필요) |
| 우리 | 카드의정석2 SIMPLE | 신규 card 24 | ✓ 20261105_000044 (2/2, WindowsOCR) | 미실행 | 미실행 | — | LLM 추출 승인 대기 |

## 2. 기존 3종 검증 결과 (읽기 전용)

| 확인 항목 | card 2 ONE PICK STYLE | card 5 JADE Classic | card 6 카드의정석 SHOPPING |
|---|---|---|---|
| 상품 행 | ACTIVE, DEBIT, `brand_opt_list` 2개(LOCAL, MASTERCARD), 카드 조건식 DRAFT | ACTIVE, CREDIT, `brand_opt_list` 4개(Visa Signature 02 등) | ACTIVE, CREDIT, `brand_opt_list` 없음 |
| 문서 연결 | PRODUCT_GUIDE 1(PENDING) | PRODUCT_GUIDE 1 + BRAND_SERVICE 1(VS002) | PRODUCT_GUIDE 1(PENDING) |
| 페이지·청크 | 2/2 | 6/6 | 8/8 |
| AI 추출 | `20261101_000002` PARTIAL, EXTRACT_V1 | **없음** | `20261104_000032` SUCCEEDED, EXTRACT_V8 |
| 등록 항목 (`card_product_item`) | BENEFIT 4, ANNUAL_FEE 1 | BENEFIT 1(BRAND_SERVICE 출처), ANNUAL_FEE 1 | BENEFIT 11, ANNUAL_FEE 1 |
| 근거 (`card_evidence_link`) | 54건, 위치=원문 일치 | 12건, 일치 | 60건, 일치 |
| 중복 (`item_cd`) | 0 | 0 | 0 |
| 공통 혜택 적용 | 0 | 1(Visa Signature) | 0 |
| 검증 상태 | 전 항목 `PENDING_REVIEW` | 전 항목 `PENDING_REVIEW` | 전 항목 `PENDING_REVIEW` |

판단:
- card 2: 등록 항목 자체는 근거와 맞지만 추출이 구 프롬프트의 PARTIAL이다. 누락 여부는 **미확인**이며 V8 재추출로 대조할 것을 제안한다(유료, 2쪽).
- card 5: 상품설명서(6쪽)의 개별 혜택(포인트 적립 등)이 **등록되어 있지 않다**. 기존 행 변경 없이 추가하려면 V8 추출 → 기존 `benefit_main product` 등록 순서가 필요하다(유료, 6쪽).
- card 6: 11-04 등록·평가 기록(`tmp/woori_run32_eval_20261104/verdicts.md`)과 일치한다. 추가 조치 없음.
- 기존 3종 데이터는 변경하지 않았다.

## 3. 신규 등록 결과 (무료 범위)

등록 경로: 기존 `CommonBenefitService.register_card`(상품 행, `product_cd` 기준 멱등) + 기존 `RegisterService.register(product_link=…)`(문서·페이지·청크·`card_product_doc`). 하나 3종은 `hana_all/manifest.csv` 검증 경로, 우리 2종은 외부 발급사 경로를 썼다.

| card_id | product_cd | 상품명 | card_doc_id | doc_cd / doc_family_cd | 쪽·청크 | 추출기 | 심의 표기 |
|---|---|---|---|---|---|---|---|
| 20 | HANA_CREDIT_JADE_FIRST | JADE First | 20261105_000040 | HANA_14998_20250703 / HANA_14998 | 8/8 | PyMuPDF | 심의필 제 2024-C1a-06598호(2024.06.10) / 준법심의 L-25-0239(2025.07.03) |
| 21 | HANA_CREDIT_JADE_PRIME | JADE Prime | 20261105_000041 | HANA_14997_20250703 / HANA_14997 | 8/8 | PyMuPDF | 심의필 제 2024-C1a-06599호 / 준법심의 L-25-0238 |
| 22 | HANA_CREDIT_THE_SIMPLE | 더 심플 하나카드 | 20261105_000042 | HANA_14527_20260929 / HANA_14527 | 1/1 | PyMuPDF | 심의필 제 2026-C1a-16313호(2026.10.27) / 준법심의 L-26-2189 |
| 23 | WOORI_CREDIT_CARD_POINT_II | 카드의정석 POINT II | 20261105_000043 | WOORI_260901_0a4da23acb9a / WOORI_POINT_II | 8/8 | PyMuPDF | 파일명 날짜 260901 |
| 24 | WOORI_CREDIT_CARD2_SIMPLE | 카드의정석2 SIMPLE | 20261105_000044 | WOORI_260204_0f624bae5dd0 / WOORI_CARD2_SIMPLE | 2/2 | WindowsOCR | 심의필 제 2026-C1a-01616호(2026.02.04) — 파일명에 날짜가 없어 원문(OCR + 페이지 이미지 확인) 날짜 사용 |

- 상품명은 각 원문에 있음을 확인했다(`applicability_basis_txt`에 기록). 문서 연결은 `approval_status_cd=PENDING`이다.
- JADE Prime PDF는 manifest상 'JADE Prime 골드클럽멤버스'와 같은 파일이다(`doc_note`에 기록). 이번에는 JADE Prime만 상품으로 만들었다.
- JADE First Centum은 별개 상품이라 등록하지 않았다.
- `brand_opt_list`는 근거로 확정한 옵션 매핑이 없어 `[]`로 두었다(card 6과 같은 처리).
- `card_id`가 20부터인 이유: ROLLBACK 시험 등록에서 시퀀스가 소비되었다. 데이터에는 영향이 없다.

### 미등록 2종 — 원인
`EVERY WON POINT`(`상품안내장_EVERY WON POINT.pdf`)와 `카드의정석2 DAILY`(`…_260602.pdf`)는 텍스트 레이어에 보이지 않는 제어문자 U+0007(BEL)이 각 쪽 23~30개(전체의 약 1%) 들어 있다. U+0003도 1개 있다. 기존 품질 게이트가 두 쪽 모두 `SUSPECT`로 판정해 등록을 거부했다. Windows OCR 재판독도 원문보다 낫지 않아 교체되지 않았다.
- 같은 형식의 SHOPPING·POINT II에는 이 문자가 없다.
- 해결안(승인 필요): `document_service._read_pages`의 외부 발급사 정규화에 기존 사설영역 글리프 치환과 같은 방식으로 제어문자(Unicode `Cc`, 탭·줄바꿈 제외)를 같은 길이의 공백으로 바꾸는 한 줄을 추가하고, 단위 테스트를 함께 넣는다. 이는 품질 판정 대상 문자를 바꾸는 소스 변경이라 승인 없이 하지 않았다.

## 4. 등록 절차 검증

| 단계 | 결과 |
|---|---|
| 중복 검사 | 7종 PDF SHA-256이 `card_doc`에 없음, `product_cd` 미존재 확인 |
| ROLLBACK 시험 | 7종을 하나의 바깥 트랜잭션으로 시험했다. 2종이 품질 게이트에서 차단되어 전체 ROLLBACK. 2종을 제외하고 다시 시험해 5종 정상, 검증 오류 0 |
| 백업 | `src/data/backup/pre_calc_cleanup_20261105_102032` (VERIFY OK) |
| 실제 등록 | 5종 COMMIT |
| 기존 행 비교 | 18개 테이블 전체를 백업과 `to_jsonb` 행 단위로 대조 → 기존 행 변경·삭제 0. `card_product` 3→8, `card_product_doc` 4→9, `card_doc` 23→28, `card_doc_page` 55→82, `card_doc_chunk` 64→91 |
| 재실행 | 같은 명령 재실행(ROLLBACK) 시 5종 모두 `ALREADY_REGISTERED`, 같은 `card_id`·`card_doc_id` |
| 문서 검증 | `RegisterService` 내부 `verify_doc` + PDF 재추출 해시 대조 ERROR 0 |

## 5. 공통서비스 연결 후보 (생성하지 않음)

| card | 상품설명서 근거 | 후보 공통서비스 | 비고 |
|---|---|---|---|
| 20 JADE First | p7 `이 상품은 VISA Infinite 등급의 국제 브랜드 서비스가 제공됩니다.`, `국내외겸용 (VISA)` | 하나 `VISA_INFINITE`(card_common 16) | 국내전용 발급분 제외. 선택서비스 유형 표기는 **미확인** |
| 21 JADE Prime | p7 `VISA Signature등급의 국제 브랜드 서비스`, `VISA : VISA Signature 02 유형` | 하나 `VISA_SIGNATURE`(card_common 1, VS002 문서) | JADE Classic과 같은 유형 |
| 22 더 심플 | `국내전용/국내외겸용(Mastercard)`, 등급 표기 없음 | 없음 | 등급 근거 부족 |
| 23 POINT II | p5 `해외겸용 (Mastercard/VISA)`, 등급 없음 | 없음 | |
| 24 2 SIMPLE | p1 `해외겸용 (Mastercard)`, 등급 없음 | 없음 | 우리카드 공통 혜택 43건과도 연결 근거 없음 |

연결 시에는 `brand_opt_list`를 원문 근거로 채운 뒤 기존 `apply_run`을 거쳐야 한다. 이번에는 하지 않았다.

## 6. 승인이 필요한 항목

### 6-1. 유료 LLM 추출 (EXTRACT_V8, gpt-6.1-terra, 1쪽 1호출)

| 대상 | card_doc_id | 쪽(호출) |
|---|---|---:|
| JADE First (20) | 20261105_000040 | 8 |
| JADE Prime (21) | 20261105_000041 | 8 |
| 더 심플 하나카드 (22) | 20261105_000042 | 1 |
| 카드의정석 POINT II (23) | 20261105_000043 | 8 |
| 카드의정석2 SIMPLE (24) | 20261105_000044 | 2 |
| JADE Classic (5) — 누락 보완 | 20261102_000003 | 6 |
| 소계 | | **33** |
| (선택) ONE PICK STYLE (2) V8 재추출 | 20261101_000002 | 2 |
| (제어문자 승인 후) EVERY WON POINT, 카드의정석2 DAILY | 미등록 | 4 |

- 예상 비용(단가 입력 $1·출력 $5/백만 토큰): 직전 우리카드 상품안내장(run 32)은 8쪽 실제 약 $0.13이었다. 33호출 기준 **약 $0.6~1.5**로 예상한다.
- 상한(입력 6k·출력 16k 토큰/호출): 33호출 약 **$2.9**, 선택 항목까지 39호출 약 **$3.4**. 기존 `TerraClient` 예산 가드로 상한을 걸고 실행한다.
- 추출 뒤 순서: 기존 `benefit_main product` → 후보 검증 → PDF 대조 → ROLLBACK → 등록. 기존 규칙을 통과한 항목만 `card_product_item`·`card_evidence_link`에 추가한다.
- 연회비는 기존 `annual_fee_register.py` 방식(사람 검토 SEED)이 필요하다.

### 6-2. 제어문자 정규화 소스 변경 — 3절

### 6-3. 공통서비스 연결 — 5절 후보(근거 확인 후 `brand_opt_list`·`apply_run`)

## 7. 파일·테스트

- 새 파일: 이 보고서. 소스·테스트 변경 없음.
- 테스트(`payment_card/tests`): 451 passed, 18 skipped, 1 failed(기존 `test_answer_text.py` 실패, 신규 실패 0).
- Identity Registry: 개별 카드 혜택은 `card_product_item`(`item_cd`) 체계라 공통 혜택 대장(`identity_registry/`)과 다르다. 추출·등록 후에 반영한다(이번에는 변경 없음).
- Markdown(`data/markdown/product/`): 신규 문서는 아직 생성하지 않았다. 기존 `markdown_export --doc-id`로 만들 수 있다. 단 card 24는 텍스트 레이어가 없어 공통 문서처럼 DB 원문 방식이 필요하다.
