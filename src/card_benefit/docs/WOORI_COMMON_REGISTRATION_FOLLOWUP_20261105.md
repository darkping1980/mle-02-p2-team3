# 우리카드 공통 혜택 등록 후속 (2026-11-05)

- 이전 보고서: [WOORI_COMMON_REGISTRATION_REVIEW.md](WOORI_COMMON_REGISTRATION_REVIEW.md)(내용 유지, 수정 안 함)
- ID별 상세: [identity_registry/common/README.md](identity_registry/common/README.md)
- 원문 Markdown: `src/card_benefit/data/markdown/common/20261104_000024~000028/`
- PDF 재등록·LLM 재추출·임베딩·Neo4j·DDL은 하지 않았다. Git 커밋·Push도 하지 않았다.
- 요청에 있던 `src/card_benefit/docs/source_wiki/`는 저장소에 **없다**. 그래서 실제 Python·SQL 소스와 DB 카탈로그로 확인했다.

## 9-1. 기존 상태 (작업 시작 시 읽기 전용 확인)

| 항목 | 값 | 비고 |
|---|---:|---|
| 문서 / 페이지 / 청크 | 5 / 10 / 10 | `card_doc` 20261104_000024~000028 |
| 추출 실행 | 7 | 33·34 PARTIAL(보존), 35~39 SUCCEEDED |
| 추출 후보 | 154 | 모두 `card_extr_stg.stg_status=PENDING_REVIEW` |
| 등록 공통 혜택 | 1 | `card_common_bnft` 20261104_000044 |
| 검토 보류 | 153 | |
| 카드별 적용 관계 | 0 | `card_common_bnft_apply` |

구조 대조 결과:
- 공통 혜택 등록 서비스(`common_benefit_service.py`)와 SQL(`common_benefit_repository.sql`)이 쓰는 `card_common`, `card_common_doc`, `card_common_bnft`, `card_common_bnft_apply`가 실제 DB에 있고 컬럼도 일치한다.
- `card_product_item`(`item_type_cd='BENEFIT'`)은 카드별 상품 혜택 테이블이다. 공통 혜택 경로는 쓰지 않는다. 차이가 없어 중단하지 않았다.
- 11-04 이후 변경: `card_common_bnft`의 마지막 쓰기는 11-04 09:04 UTC였다. 행 수도 11-04 종료 시점과 같았다.
- 새 커밋 `7b37de0`은 문서 3개만 바꿨다. 코드 변경은 없다.

## 9-2. 개선 결과

### 기간 파서 수정 (`common_benefit_service.py`, 제한적 수정)

| 변경 | 내용 | 방향 |
|---|---|---|
| `period()` | 구분자 `~`에 `부터`를 추가하고, `YYYY.MM.DD~(YYYY.)MM.DD` 형식을 추가했다 | 형식 지원만 추가. 시작 연도는 계속 필수 |
| `DEFAULT_PERIOD_PREFIX` | 우리카드 문구 `(본 서비스는) 별도 기간이 지정된 경우를 제외하고`를 추가했다 | 기존 하나카드 문구와 같은 조건부 기본 기간 |
| `OWN_PERIOD_HINT` | `M/D` 표기(예 `~6/30`, `(1/8~)`)를 혜택 자체 기간으로 인식하게 했다 | **더 엄격해짐**. 새 테스트에서 누락을 발견해 보완 |

계속 거부하는 표기: `1월 1일부터 3월 31일까지`(연도 없음), `~3/31`, `4월 중~`, 날짜 역전, `…까지 예정`, 잘못된 월.

**단위 테스트**
- 변경 전 관련 테스트 35개 통과.
- 변경 후 `test_woori_period_wordings_2026_11_05`를 추가했다. `payment_card/tests` 전체 결과는 451 passed, 18 skipped, 1 failed이다.
- 실패 1건(`test_answer_text.py::test_unresolved_tier_cannot_be_decided_in_natural_text`)은 변경 전 소스에서도 똑같이 실패한다. 기간 파서와 무관한 기존 실패다.

### OCR 교차 검증
- RapidOCR 한국어 모델(`korean_PP-OCRv5_rec_mobile.onnx`)이 PC에 없다. `RAPIDOCR_MODEL_DIR`도 설정되어 있지 않다. 패키지에 들어 있는 기본(중국어·일반) 모델로 돌리면 한글이 거의 깨진다(Markdown 생성 시험에서 확인). 그래서 **엔진 간 교차 검증은 하지 못했다(미확인)**. 모델을 받으려면 외부 다운로드 승인이 필요하다.
- 대신 등록 후보 41건은 PDF 2쪽을 렌더링한 이미지와 **값을 하나씩 육안 대조**했다. 할인율·금액·횟수는 40건이 일치했다. 1건(000452)은 OCR이 `5~60%`를 `5-60%`로 읽어 보류했다.
- DB 원문(`card_doc_page`·`card_doc_chunk`·`card_source_evidence`)은 수정하지 않았다. OCR 보정은 아래 제안만 한다.

| OCR 원문(DB) | PDF 실제 | 영향 | 위치 |
|---|---|---|---|
| `ⅥSA` | VISA | VISA-I 34건 브랜드 근거 실패 | 000026 1·2쪽 |
| `80/0`, `200/0`, `50/0`, `150/0`, `100/0`, `]0~200/0` | 8%, 20%, 5%, 15%, 10%, 10~20% | 값 누락·보류 | 000025~000028 2쪽 |
| `5~15%。`, `%。` | 5~15% | 보류 | 다수 |
| `5-60%` | 5~60% | 000452 보류 | 000027 2쪽 |
| `제크카드만 적용(법인카드 적용 제에` | 체크카드만 적용(법인카드 적용 제외) | 000542 보류 | 000025 2쪽 |
| `Trump H0teIs`, `TBR GIobaI`, `C이lection's membershlp` | Trump Hotels, TBR Global, Collection's membership | 000538·000461·000561 보류 | 000025·000027 2쪽 |
| `니ote|s℃om`, `8】【。 힐인` | Hotels.com, 8% 할인 | 000504 보류 | 000024 2쪽 |

### 브랜드 근거 누락 (Mastercard World 39건)
- 해당 후보의 추출 결과에는 APPLICABILITY 근거가 **0건**이다. 원문 2쪽 마지막 줄 `본 서비스는 Mastercard가 제공합니다.`는 DB 원문에 있다.
- 그러나 기존 근거만으로 복구하려면 `card_source_evidence`에 행을 추가해야 한다. 이는 추출 결과를 사람이 만들어 넣는 것이므로 하지 않았다.
- **재추출 필요**: 000024 2쪽 1회. 예상 비용은 최대 약 $0.17(입력 약 7.3k, 출력 한도 32k 토큰). 직전 실제 비용은 약 $0.12였다. 승인 전에는 실행하지 않는다.
- Visa Infinite 33건은 OCR(`ⅥSA`) 원인이다. 재추출만으로는 해결되지 않는다. 원문 OCR 보정(DB 원문 변경 또는 새 문서판 등록)을 결정한 뒤 재추출해야 한다(약 $0.1).

### 기존 검증 규칙 변경 여부
- 등록 판정 규칙(`_candidate_problem`, `_evidence_ids`, 브랜드·등급 확인, 중복 방지, 정합성 게이트)은 바꾸지 않았다.
- 바꾼 것은 기간 **표기 형식 지원**과 자체 기간 감지 **강화**뿐이다.
- 그 위에 **추가 안전 게이트**를 두었다(드라이버에서 적용, 소스 무수정): certainty HIGH, 값 존재, OCR 이상 표기 없음, 자체 기간 표현 없음, PDF 이미지 값 일치, 저장 문구에 OCR 오탈자 없음.

## 9-3. 재검증 결과

| 구분 | 건수 |
|---|---:|
| 기존 후보 | 154 |
| 기존 등록 | 1 |
| 기존 검토 보류 | 153 |
| 이번에 재검증한 후보 | 153 (전체를 기존 `register_run`으로 ROLLBACK 검증) |
| 기간 파서 보완 후 기존 규칙 통과(신규) | 68 |
| 추가 안전 게이트·PDF 대조 통과 | 37 |
| **이번에 추가 등록한 혜택** | **37** |
| 여전히 보류 중인 후보 | **116** |
| 신규 카드 적용 관계 | **0** |

문서별:

| card_doc_id | 공통서비스 | 후보 | 등록(누적) | 보류 |
|---|---|---:|---:|---:|
| 20261104_000024 | WOORI_MASTERCARD_WORLD (20) | 40 | 1 | 39 |
| 20261104_000025 | WOORI_MASTERCARD_PLATINUM (21) | 34 | 22 | 12 |
| 20261104_000026 | WOORI_VISA_INFINITE (22) | 34 | 0 | 34 |
| 20261104_000027 | WOORI_VISA_PLATINUM (23) | 25 | 5 (기존 1 포함) | 20 |
| 20261104_000028 | WOORI_UPI_PLATINUM (24) | 21 | 10 | 11 |
| 합계 | | 154 | 38 | 116 |

보류 116건 사유:

| 구분 | 사유 | 건수 |
|---|---|---:|
| 기존 규칙 | 후보 값·구조 검증 실패(브랜드 근거 누락 MC_W 39, OCR `ⅥSA` VS_I 33) | 72 |
| 기존 규칙 | 연도 없는 혜택별 기간(`~3/31 예약시까지`, `4월 중~` 등) | 10 |
| 기존 규칙 | 브랜드·등급 불일치(`ⅥSA` 1, `유니온페이 프리미엄 카드` 범위 1) | 2 |
| 기존 규칙 | 동일 인용 중복으로 근거 대상 모호 | 1 |
| 추가 게이트 | certainty LOW(일부는 값 없음·OCR 이상 동반) | 14 |
| 추가 게이트 | OCR 이상 표기(`%。`, `|`, 한자 등) | 9 |
| 추가 게이트 | 자체 기간·횟수 표현(Airalo `USD 100까지`, DB손해보험 `만 60세까지…`, 마리나 베이 샌즈 `3개월간`) | 3 |
| 추가 게이트 | OCR 기호 `5-60%`(000452) | 1 |
| OCR 문구 오류 | 저장될 문구 오탈자(000542·538·561·461, 대장 `excluded`) | 4 |
| | 합계 | 116 |

등록된 37건은 [identity_registry/common/README.md](identity_registry/common/README.md)의 문서별 상세에 `card_common_bnft_id`, 원문 근거 `evidence_id`, 위치와 함께 정리했다. 식별자는 대장 `WOORI_BRAND_MC_W/MC_PT/VS_P/UPI_P.json`(`DRAFT_PENDING_USER_REVIEW`)에 있다.

## 9-4. DB 변경 내역

| 테이블 | 전 | 후 | 변화 |
|---|---:|---:|---|
| `card_common_bnft` | 40 | 77 | +37 (`card_common_id` 20: +1, 21: +22, 23: +4, 24: +10) |
| `card_common_bnft_apply` | 1 | 1 | 0 |
| 그 밖 16개 테이블 | — | — | 0 |

- 등록 경로: 기존 `CommonBenefitService.register_run`을 대장 계열별 1트랜잭션으로 실행했다. 대장 밖 INSERT, UPDATE, CHANGE_REVIEW, 근거 ID·`bnft_cd` 불일치가 하나라도 있으면 ROLLBACK하는 조건이었다. 같은 조건으로 먼저 ROLLBACK 검증을 거쳤다.
- 정합성: `register_run` 내부의 등록 전후 정합성 게이트(`integrity_errors`, `common_integrity_errors`)가 통과했다(위반 증가 0). `bnft_cd` 중복 0건. 기존 `card_common_bnft`·`card_product_item`과 코드 충돌 0건.
- 중복 방지: 같은 명령을 다시 실행하면 38건 모두 `UNCHANGED`이고 쓰기는 0건이다. 기존 000044는 `UNCHANGED`로 다시 만들어지지 않았다.
- 기존 데이터: 등록 직전 백업 `src/data/backup/pre_calc_cleanup_20261105_092319`(VERIFY OK)과 `to_jsonb` 행 단위로 대조했다. 18개 테이블의 기존 행은 모두 그대로다(변경·삭제 0).
- `card_extr_stg.stg_status`는 바꾸지 않았다(모두 `PENDING_REVIEW`). 자동 승인은 하지 않았다.

## 9-5. 잔여 문제

| 구분 | 대상 | 필요한 조치 |
|---|---|---|
| 원문 근거 부족 | MC_W 39건(APPLICABILITY 근거 없음) | 000024 2쪽 재추출 승인(약 $0.17 이하) |
| OCR 재처리 | VS_I 34건(`ⅥSA`), 깨진 숫자 후보, 문구 오탈자 4건 | 보정 방식 결정: (a) 한국어 RapidOCR 모델 승인 후 교차 OCR로 새 문서판 등록, 또는 (b) 사람이 확인한 보정 원문 반영. 어느 쪽이든 DB 원문 변경이므로 사전 승인 필요 |
| LLM 재추출 | MC_W(위), VS_I(OCR 보정 후) | 승인 필요 |
| 연도 없는 혜택별 기간 | 10건 + 자체 기간 3건 | 사람이 기간을 확정하거나 기간 없이 보류 유지 |
| certainty LOW | 14건 + 기존 등록 000044 | 사람 검토 |
| 카드별 브랜드·등급 | 우리 card 6(등급 표기 없음) 및 우리카드 다른 상품 | 등급이 적힌 상품안내장 확보 → `brand_opt_list` 근거화 → `apply_run` |
| 사용자 판단 | 대장 `review_status` 승격, 000044 기간 NULL 유지 여부, UPI `프리미엄 카드` 범위 | — |
| 도구 | `simulate_ledger.py`가 이름이 바뀐 `card_bnft`를 조회해 실패함 / 외부 발급사 경로에서 OCR 페이지가 `OCR_REVIEW` 대신 `OK`로 저장됨 / `BLOCK_V1`이 우리카드 `•` 글머리를 나누지 못함 | 별도 수정 검토 |

임베딩(신규 37건 검색 텍스트·벡터)과 Neo4j 반영은 하지 않았다. 다음 단계에서 기존 절차로 진행한다.
