# 개별 카드 등록 검토

## 기존 상품 확인

2026-11-04 읽기 전용 조회: 하나카드 ONE PICK STYLE 하나 체크카드 (card_id 2, card_doc_id 20261101_000002), JADE Classic (card_id 5, card_doc_id 20261102_000003), 우리카드 카드의정석 SHOPPING (card_id 6, card_doc_id 20261104_000023). 세 상품의 개별 혜택·조건·근거 완결성은 이번에 재검증하지 않았다.

## 신규 대상 (사용자 선정, 미등록)

선정 기준 제안: 기존 상품과 구별되는 개별 상품, common 제외, 상품 안내 PDF 존재. 파일명은 실제 원본 기준이며 상품별 원문 검토 및 PDF 중복 검증 전의 후보이다.

| 카드사 | 후보 | 원본 PDF | 상태 |
|---|---|---|---|
| 하나 | JADE First | 신용_JADEFirst_상품설명서(공식PDF)_14998_20250703.pdf | 미등록 확인, 원문 검토 전 |
| 하나 | JADE Prime | 신용_JADEPrime_상품설명서(공식PDF)_14997_20250703.pdf | 미등록 확인, 원문 검토 전 |
| 하나 | 더 심플 하나카드 | 신용_더심플하나카드_상품설명서(공식PDF)_14527_20260929.pdf | 미등록 확인, 원문 검토 전 |
| 우리 | EVERY WON POINT | 상품안내장_EVERY WON POINT.pdf | 미등록 확인, 원문 검토 전 |
| 우리 | 카드의정석 POINT II | 상품안내장_카드의정석 POINT II_260901.pdf | 미등록 확인, 원문 검토 전 |
| 우리 | 카드의정석2 DAILY | 상품안내장_카드의정석2 DAILY_260602.pdf | 미등록 확인, 원문 검토 전 |
| 우리 | 카드의정석2 SIMPLE | 상품안내장_카드의정석2 SIMPLE_out_게시용.pdf | 미등록 확인, 원문 검토 전 |

각 대상의 card_id, card_doc_id, 페이지·청크, 추출, 혜택·조건·연회비, 임베딩 및 Neo4j: 미실행. 7종 선택은 사용자 확인 완료. 상품 PDF 원문 검토 및 등록 전 절차 확인이 남았다.

등록 절차 확인: RegisterService는 card_product를 생성하지 않으며 기존 card_id를 필요로 한다. 신규 상품 생성과 매핑의 안전한 기존 절차를 아직 확인하지 못했다. 연회비는 원문을 사람이 검토해 SEED를 추가해야 한다. 따라서 7종 모두 보류이며 DB 쓰기와 LLM 호출은 수행하지 않았다.

## 상품 생성 절차 보완 조사 (2026-11-04)

- JADE First 계열 후보 PDF 두 개가 실제 존재함: `신용_JADEFirst_상품설명서(공식PDF)_14998_20250703.pdf` (200,951 bytes), `신용_JADEFirstCentum_상품설명서(공식PDF)_14999_20250703.pdf` (295,077 bytes). 선택 상품 JADE First와 First Centum은 별개로 취급한다.
- DB에서 확인된 기존 `card_product`: card_id 2 `HANA_DEBIT_ONE_PICK_STYLE` / ONE PICK STYLE 하나 체크카드, 5 `HANA_CREDIT_JADE_CLASSIC` / JADE Classic, 6 `WOORI_CREDIT_CARD_SHOPPING` / 카드의정석 SHOPPING. 이전 조회 결과의 등록 문서는 위 표를 참조.
- `RegisterService`는 상품 행을 만들지 않고 `card_product_doc` 연결에 기존 card_id를 요구한다. `common_benefit_repository.sql`의 `insert_card`는 product_cd, product_nm, issuer, card_kind_cd, brand_opt_list 등을 넣고 product_cd 충돌 시 DO NOTHING 후 조회하지만, 이것은 공통 혜택 파이프라인 내부 보조 동작으로 개별 상품 등록을 보장하는 일반 API로 확인되지 않았다.
- `card_product_map`이라는 관계는 현재 확인한 운영 소스/DDL에서 확인되지 않았다. 설계 파일은 운영 DDL이 아니므로 근거로 사용하면 안 된다. 운영 DB의 실제 DDL/제약, `card` 테이블 존재 여부, issuer/kind 코드 마스터, 상품코드 정책, `card_id` 생성 방식은 추가 읽기 전용 카탈로그 조회가 필요하다.
- 카드 상품·매핑 값과 `applicability_basis_txt`는 임의 생성하지 않는다. 현재 근거로 확정된 일회성 SQL은 없다. 신규 상품 카드번호를 포함한 쓰기는 아직 시작하지 않았다.
- 이번 조사에서 우리카드 공통 등록 파일은 수정하지 않았다. 기존 커먼 등록 검토 문서와 identity registry는 작업 전부터 미추적 상태였다.

상태: 신규 7종 모두 **보류**. PostgreSQL DDL/PK/FK/UNIQUE 관계 확인, 운영 등록 규칙 확정, JADE First end-to-end 등록 및 LLM 추출·혜택 검증·정합성 확인이 미완료. Git commit/push 및 Neo4j 적재 없음.

## 동시 작업 및 주의사항

DB 활동 조회 시점에 보이는 활성 트랜잭션은 없었으나 권한 및 조회 시점에 따른 한계가 있고 이후의 다른 작업을 배제할 수 없다. 기존 우리카드 공통 혜택 검토 문서 및 identity registry 미커밋 파일을 보존한다. Neo4j 적재기는 전체 스냅샷을 MERGE하고 제약 생성도 수행하므로 스키마 변경 금지 조건 아래 실행하지 않았다.
