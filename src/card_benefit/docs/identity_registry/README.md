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
- 2026-11-04 Neo4j `dp_` 반영(`neo4j_load_draft --apply`): 노드 214→247, 관계 277→310. 추가는 `dp_card_common_bnft` 33개와 `dp_belongs_to` 33개뿐이고
  기존 노드·관계 변경 0, PostgreSQL 대조 차이 0. 새 공통 혜택에는 카드 적용·근거 관계가 없다(적용 카드 0장, 아래 근거 구조 참고).
  적재 전 그래프 백업 `src/data/backup/neo4j_dp_pre_reload_20261104_095543`(Git 제외).

## 알려진 문제: 공통 혜택 근거 조회 (보류, 2026-11-04)

`embedding_repository.select_common_bnft_evidence`는 공통 혜택의 근거를 **문서의 모든 추출 실행에서 혜택명이 같은 대표 후보**로 찾는다.
공통 혜택에는 어느 실행·후보에서 등록했는지 기록하는 컬럼이 없고, `card_evidence_link`는 카드별 혜택만 담는다.

- MP004 33건: 반환 483건 중 Run 31 근거 151건(대장 근거 137건 모두 포함), 과거 실행(26~30) 근거 332건(69%).
  과거 근거는 같은 PDF 줄의 다른 구간 인용이며 다른 혜택의 근거가 섞이지는 않았다. 답변 근거 목록과 프롬프트에 중복이 늘어난다.
- Neo4j에는 공통 혜택→근거 관계가 없다(`same_as`로 연결된 카드 혜택만 근거를 가진다). 검색은 그래프에 근거가 없으면 이 SQL로 대체 조회한다(`card_graphrag.py` retrieve).
- 재추출로 혜택명이 바뀌면 이름이 같은 후보를 찾지 못해 근거가 0건이 될 수 있다.

개선 방향(미적용):
1. 최소안(SQL만): 혜택명이 같은 대표 후보 중 **가장 최근 실행 하나**로 한정한다. 33건 기준 483→151건, 대장 근거는 유지된다.
2. 장기안(DB 구조 변경 필요, 별도 승인): 공통 혜택과 원문 근거를 직접 잇는 연결을 두고 Neo4j에도 `supported_by`로 올린다.

## 개별 카드 혜택 (2026-11-05 추가)

개별 카드 10종의 `card_product_item` 등록·보류 현황은 [product/README.md](product/README.md)에 있다. 공통 혜택 대장과 별개의 체계이다.
