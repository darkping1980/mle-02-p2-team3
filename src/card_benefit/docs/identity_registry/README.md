# 공통 혜택 업무 식별자 대장

공통서비스 문서에서 추출한 혜택에 사람이 검토한 **업무 식별자**를 붙여 두는 대장이다.
등록 프로그램(`benefit_main common --identity <stg_id>=<식별자>`)과 DB 구조는 그대로 쓰고, 넘길 식별자만 이 대장에서 정한다.

- `bnft_cd = benefit_code(doc_family_cd, identity)`: 문서 계열과 식별자만 사용한다. 혜택명·문서 판·stg_id는 쓰지 않는다.
- 같은 식별자는 항상 같은 `bnft_cd`가 되므로 재추출 후 다시 등록해도 새 행이 생기지 않는다.
  같은 문서 판에서 값이 달라진 경우 기존 등록 프로그램은 `CHANGE_REVIEW`로 멈추고 자동으로 덮어쓰지 않는다.

## 파일

| 파일 | 내용 |
|---|---|
| `HANA_MP004.json` | MP004(Mastercard Platinum, `card_doc_id 20261103_000014`) 대장. 등록 대상 33건, 제외 20건 |
| `simulate_ledger.py` | 읽기 전용 시뮬레이션. 대장으로 후보를 대응시키고 실제 `register_run`을 쓰기 가로채기로 실행 |

## 식별자 규칙

| 종류 | 형식 | 비고 |
|---|---|---|
| `NAME_V1_AUTO` | `NAME_V1_<sha256>` | 기존 `identity_for()` 결과. 값을 그대로 보존하고 다시 계산하지 않는다 |
| `BIZ_V1_MANUAL` | `BIZ_V1:<영역>/<제휴사·대상>/<혜택 구분>` | 예: `BIZ_V1:TRAVEL/TRIP_COM/HOTEL`. 같은 제휴사의 혜택은 마지막 구분으로 나눈다 |

- 한번 정한 식별자는 바꾸지 않는다. 바꾸면 다른 `bnft_cd`가 되어 중복 행이 생긴다.
- `excluded`의 `reserved_identity`는 충돌 검사용 예약값이다. 등록 인자로 넘기지 않는다.

## 후보 대응(재추출 대비)

대장 항목과 후보는 혜택명이나 stg_id가 아니라 **원문 근거**로 맞춘다.

1. `anchor.line_sha256`: 위치가 확인된 원문 근거 줄의 해시(NFKC → casefold → 공백 제거 → 앞쪽 글머리표 제거). 원문은 저장하지 않는다.
2. `anchor.value_key`: 같은 줄의 여러 혜택(예: Trip.com 호텔 6%·항공 3%·액티비티 5%)을 값 텍스트로 구분한다.
3. 두 값이 모두 같은 후보가 정확히 1건일 때만 식별자를 넘긴다. 0건이거나 2건 이상이면 넘기지 않으며, 등록 프로그램은 그 후보를 REVIEW로 둔다.

문서의 새 판에서 원문 줄이 바뀌면 대응이 실패한다(안전한 실패). 그때는 사람이 원문을 확인해 기존 식별자에 다시 연결하고 대장을 갱신한다.

## 사용

```bash
# 읽기 전용 시뮬레이션(쓰기·API 없음). --rename: 혜택명을 모두 바꿔도 대응이 같은지 확인
uv run python src/card_benefit/docs/identity_registry/simulate_ledger.py HANA_MP004 --rename
```

실제 등록은 사용자 승인 후 기존 명령으로 한다(대장의 `register` 항목만 `--identity`로 전달, 임베딩은 `--no-embed`로 분리).
등록 뒤 다시 시뮬레이션하면 대장 항목은 `UNCHANGED`로 나와야 한다(같은 식별자 → 같은 `bnft_cd`, 쓰기 0건).

## 등록 기록

| 날짜 | 대장 | 결과 |
|---|---|---|
| 2026-11-04 | `HANA_MP004` (run `20261103_000031`) | `card_common_bnft` INSERT 33건(`20261104_000009`~`000041`, `card_common_id=9`), UPDATE 0, REVIEW 20건 유지. 임베딩·Neo4j 미반영. 백업 `src/data/backup/pre_calc_cleanup_20261104_093323`(Git 제외) |

- 등록은 `CommonBenefitService.register_run`(임베딩 없음)을 바깥 트랜잭션으로 감싸, 대장 밖 쓰기·UPDATE·예상과 다른 판정이 나오면 COMMIT 전에 전체 ROLLBACK하도록 실행했다.
- 등록 후 검증: 33건의 혜택명·유형·선택서비스·기간·값·한도·근거 ID 일치, 정합성 게이트 0, `bnft_cd` 중복 0, 백업 대비 다른 테이블·행 변경 0.
- `review_status`는 등록 성공과 별개다. 수동 28건은 사용자 검토 전까지 `DRAFT_PENDING_USER_REVIEW`로 둔다.
