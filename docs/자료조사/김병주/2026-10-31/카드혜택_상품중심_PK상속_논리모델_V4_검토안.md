# 카드 혜택 V4 — 상품 중심 PK 상속 논리 모델 검토안

**상태:** 논리 설계 초안. [V4 DBML](../../../../src/card_benefit/sql/db_pipeline_schemaV4_business_draft.dbml)은 물리 FK나 실행 DDL이 아니다. V3 SQL·DBML, 사용자가 캡처한 `카드_ERD설계_1차.png`, 앞선 두 설계 보고서, 로컬 PDF를 확인했다. Google Drive 폴더 링크는 웹 도구에서 열리지 않았으나 동일 프로젝트의 `hana_all/common` PDF 원문은 직접 읽었다. 아래 `P-*`, `PV-*`, `B-*`, `R-*`, `K-*`는 **설명용 가상 키**이고 PDF의 실제 수치/문구와 구분한다. 정책 적용 시작일·실제 DB ID를 추정하지 않는다. DB·DDL·데이터 변경이나 SQL 실행은 하지 않았다.

## 1. 결정: 업무 PK는 상품에서 시작한다

```text
card_product(card_id)
  └─ card_policy_version(card_id, policy_ver_id)
       ├─ card_bnft(card_id, policy_ver_id, card_bnft_id)
       │    ├─ card_bnft_rule(card_id, policy_ver_id, card_bnft_id, rule_id)
       │    └─ card_bnft_target(card_id, policy_ver_id, card_bnft_id, target_id)
       ├─ card_cond(card_id, policy_ver_id, card_cond_id)
       ├─ card_cond_expr(card_id, policy_ver_id, expr_id)
       └─ card_limit_pool(card_id, policy_ver_id, pool_id)

card_doc → page → chunk → approved source_evidence
                               └─ N:M → business rule / condition
```

V3에서 `card_product`는 있었지만 `card_bnft`·`card_cond`의 PK는 `card_doc_id`부터 시작했다. ERD 이미지에도 `card_doc`가 두 테이블의 부모로 표시된다. 한 PDF 판본의 재수집/교체가 혜택 정체성을 바꾸고, 여러 상품이 공유 PDF를 참조할 때 `card_doc.card_id`와 확정 행의 `card_id`가 한 상품을 강제하는 문제가 있다. **V4는 상품 정책판을 업무 부모로, PDF를 근거로** 둔다. PDF 문서판, 상품 정책판, 공통 서비스 정책판은 각각 독립적으로 개정된다.

`card_bnft_rule`이 **상품 고유 혜택 계산값의 유일한 기준**이다. 공유 정책을 실제로 승인한 경우에는 독립적인 `card_common_bnft_rule`이 공통 혜택 계산값의 기준이며 상품 행에 수치를 복제하지 않는다. `card_bnft.bnft_rate/amt`, `card_cond.cond_rate/amt/limit_*`, 대상 테이블의 수치는 V4 확정 구조에서 제거/비권위화한다. `card_cond`는 참·거짓 원자 조건, `card_limit_tier`는 한도 수치다.

## 2. V3 → V4 PK·부모 변경

| 테이블 | V3 PK 또는 상태 | V4 권장 PK | 부모·의미 |
|---|---|---|---|
| `card_product` | `(card_id)` | 유지 | 상품 최상위 |
| `card_product_variant` | `(card_id,card_variant_id)` | 유지 | 상품의 발급형. 브랜드·등급·선택서비스 코드 |
| `card_policy_version` | 없음 | `(card_id,policy_ver_id)` | 상품의 승인 혜택 정책판 |
| `card_policy_variant` | 없음 | `(card_id,policy_ver_id,card_variant_id)` | 발급형 전용 정책판의 적용 관계 |
| `card_bnft` | `(card_doc_id,card_bnft_id)` | **`(card_id,policy_ver_id,card_bnft_id)`** | 상품 정책판의 혜택 인스턴스 |
| `card_bnft_rule` | 설계 결정안에서 문서 중심 제안, V3 미생성 | **`(card_id,policy_ver_id,card_bnft_id,rule_id)`** | 상품 고유 규칙·계산값 |
| `card_bnft_target` | V3 미생성 | `(card_id,policy_ver_id,card_bnft_id,target_id)` | 혜택 소속 대상, 값 없음 |
| `card_bnft_rule_target` | V3 미생성 | `(card_id,policy_ver_id,card_bnft_id,rule_id,target_id)` | 규칙↔대상 N:M |
| `card_cond` | `(card_doc_id,card_cond_id)`, `card_bnft_id` 보조 앵커 | **`(card_id,policy_ver_id,card_cond_id)`** | 정책판의 재사용 원자 조건. 특정 혜택의 자식 아님 |
| `card_bnft_cond` | `(card_doc_id,card_bnft_id,card_cond_id)` | **`(card_id,policy_ver_id,card_bnft_id,card_cond_id)`** | 혜택 전체↔조건 N:M. `card_cond.card_bnft_id` 이중 앵커 폐기안 |
| `card_cond_expr` / `card_cond_expr_atom` | V3 미생성 | `(card_id,policy_ver_id,expr_id)` / `(...,expr_id,branch_no,atom_seq)` | 조건식과 AND/OR/NOT 원자 |
| `card_limit_pool` / `card_limit_tier` | V3 미생성 | `(card_id,policy_ver_id,pool_id)` / `(...,pool_id,tier_id)` | 혜택과 독립적인 공유·영역 한도 |
| `card_bnft_rule_pool` | V3 미생성 | `(card_id,policy_ver_id,card_bnft_id,rule_id,pool_id)` | 규칙↔한도 풀 N:M |
| `card_bnft_rel` | V3 미생성 | `(card_id,from_policy_ver_id,from_bnft_id,to_policy_ver_id,to_bnft_id,rel_type_cd)` | 같은 상품의 동시 유효 혜택 간 우선·배타·소진 후 대체. 기본/발급형 추가판 사이도 연결 |
| `card_doc`·페이지·청크·AI 실행/호출·후보 | 문서/실행 중심 | **V3 원천 PK 유지** | 원문·추출·승인 이력. 상품 업무 PK로 승계하지 않음 |
| `card_product_doc`·`card_product_variant_doc` | V3 N:M | 유지 | 상품/발급형↔원천 문서 적용, 정책 공유의 근거 아님 |

부모 키가 복합 PK에 포함된 위치는 DBML의 `Ref`와 `Indexes [pk]`에서 확인할 수 있다. `card_cond`, `card_cond_expr`, `card_limit_pool`은 여러 혜택·규칙이 공유하므로 `card_bnft_id`를 PK에 넣지 않는다. 반면 `card_bnft_target`은 한 혜택 소속이고, `card_bnft_rule_target`은 해당 규칙과 그 혜택의 대상을 모두 상속한다. 관계 테이블에는 자체 시퀀스가 없다. 고유 로컬 ID에만 후속 DDL에서 기존 `fn_get_biz_id()` + `seq_<테이블>` 규칙을 적용한다. 물리 FK는 만들지 않고 복합 키 부모 존재 검사를 승인 게이트로 둔다.

## 3. 정책 버전·발급형·현재 조회

`card_policy_version`은 `card_id`, `policy_ver_no`, `valid_from`, `valid_to_excl`, `approved_at`, `policy_status_cd`를 갖는다. 기간은 `[시작,종료)`다. **문서 발행일, 정책 승인일, 혜택 적용일은 서로 다른 컬럼/관계**다. 개정 시 기존 혜택 행을 덮어쓰지 않고 새 `policy_ver_id` 아래에 새 행을 만든다. 상품 코드/ID는 유지한다.

정책 범위는 명시한다. `policy_scope_cd=PRODUCT`이고 `policy_effect_cd=BASE`면 모든 발급형에 적용되는 기본 정책판이다. `VARIANT`·`SUPPLEMENT`면 `card_policy_variant`가 해당 발급형을 하나 이상 열거하고 기본 정책에 **추가**된다. 상품 기본판이 둘 겹치거나 동일 발급형의 같은 혜택 코드가 기본/추가판에서 충돌하면 승인 실패시킨다. 기본판과 추가판의 서로 다른 혜택이 중복/우선 관계를 갖는다면 `card_bnft_rel`이 양쪽 정책판·혜택 복합 키를 모두 상속한다. 한 혜택만 특정 발급형에 속하면 `card_bnft.bnft_scope_cd=VARIANT`와 `card_bnft_variant`를 사용한다. 해당 링크가 없는 `VARIANT` 혜택은 오류다. `card_id`만 주어진 조회는 상품에 등록된 확정 혜택 전체를 발급형 범위와 함께 반환한다. **실제 발급형에 적용되는 집합**을 확정하려면 `card_variant_id`도 필요하다.

서비스는 `APPROVED` 정책판과 그 유효 기간을 판정한다. 공통 정책을 적용한 혜택은 상품 정책판과 공통 정책판의 **기간 교집합** 및 승인된 `card_bnft_common` 링크가 필요하다. 승인 상태가 없거나 아직 추출하지 못한 조건은 `조건 없음`으로 취급하지 않는다.

## 4. 공통 PDF와 공통 혜택 정책의 경계

로컬 PDF 직접 확인 결과:

| PDF·쪽 | 확인된 원문 요지 | 모델 판단 |
|---|---|---|
| `common/공통_AMEX브랜드서비스_AP003_20260609.pdf` 1쪽 | AMEX Platinum 등급 카드 소지자 공통서비스와 별도 선택서비스 | 한 파일에서 **공통 부분과 선택 부분을 분리**해 검토 |
| 같은 파일 2쪽 | `Amex Platinum 03`, `대상카드 JADE Classic 카드`, 호텔/공항 발렛파킹 월 2회, 지난달 50만 원 | JADE 발급형↔문서 연결과 JADE 한정 혜택 근거는 확인. 다른 카드와 이 선택서비스 정책을 공유한다고 확정하지 않음 |
| `common/공통_Mastercard브랜드서비스_MP001_20260209.pdf` 2쪽 | Platinum 01; 내 맘대로 쁨·CLUB CEO 등 대상과 실적 조건 | 선택서비스 01의 대상/조건은 별도 정책 |
| `common/공통_Mastercard브랜드서비스_MP004_20260209.pdf` 2쪽 | Platinum 04; CLUB NOBLE·CLUB Leaders 3 대상과 서로 다른 조건 | 같은 브랜드·등급이어도 01/04를 동일 서비스로 합치지 않음 |
| `common/공통_VISA브랜드서비스_VP001_20230727.pdf` 1~2쪽, `...VP001_20260317.pdf` 1~2쪽 | 2023/2026년판의 공통 서비스 내용·기간이 달라짐. 각 선택서비스 안내에 대상 카드 명시 | 같은 문서 계열의 **서로 다른 문서판**; 공통 정책판도 조항 비교·상품 적용 확인 후에만 연결 |
| `common/공통_신용카드개인회원표준약관(2026.05.12시행)_credit_card_260512.pdf`, `common/공통_하나체크카드개인회원약관(2026.09.14시행)_checkcard_personal_terms_20260914.pdf` | 로컬에 신용·체크 약관이 **별도 PDF**로 존재 | 같은 약관 파일이 신용·체크 모든 카드에 공통이라고 추정하지 않음. 각 상품 연결은 별도 승인 |

독립 공통 서비스는 `card_common_bnft(common_bnft_id)` → `card_common_policy_version(common_bnft_id,common_ver_id)` 아래에 규칙·조건식·대상·한도를 한 번 저장한다. 어느 키에도 `card_id`를 넣지 않는다. 상품의 `card_bnft`는 그 서비스에 대한 **상품별 권리/적용 인스턴스**이고 `card_bnft_common`이 공통 정책판과 연결한다. 발급형 제한은 `card_bnft_variant`, 상품별 추가 술어는 `card_bnft_cond`로 표현하여 공통 술어와 **AND**로 적용한다. `COMMON_LINK` 혜택에는 상품 로컬 규칙값을 두지 않는다. 계산법·값을 상품마다 바꿔야 하는 서비스는 공유로 합치지 않고 `LOCAL` 혜택으로 둔다. 한 상품 혜택에 여러 공통판이 동시에 연결되면 승인 게이트가 거부한다.

공통 정책의 상세 컴포넌트(`card_common_*_rule/cond/expr/target/pool`)는 상품 정책과 **같은 의미 규약을 독립 키 계열에 적용**한 논리 확장이다. DBML에는 관계 검토를 위해 전체 후보를 표시했다. 실제 DDL에서 모두 동시에 필요한지는 여러 카드 간 동일 조항이 검증된 뒤 결정한다. 공통 PDF 1개를 공유하는 N:M과 공통 정책판 1개를 공유하는 N:M은 서로 다른 행·승인 절차다.

## 5. 실제 수치 + 가상 키의 관계형 샘플

아래 키·정책 날짜는 실제 ID/적용일이 아니다. `PV-*`의 날짜는 **미확정**이므로 적재 전 PDF 문구·승인 기록으로 확인해야 한다. 표의 `DOC-*`는 실제 파일을 가리키는 **가상 문서 키**다.

### 5.1 JADE Classic C04

원문: `credit/신용_JADEClassic_상품설명서(공식PDF)_14955_20260609.pdf` 3쪽 기본 1%·특별 1.5/1.2%·특별 월 통합 10만, 4쪽 중복 시 큰 적립 우선·한도 소진 후 추가 매출에 기본 제공. AMEX 03 파일 2쪽은 JADE를 대상 카드로 명시한다.

| 논리 테이블 | 샘플 행(가상 키; 확인값은 수치/문구만) |
|---|---|
| `card_product` / `card_policy_version` | `(C04,JADE Classic)` / `(C04,PV-J1,valid_from=미확정)` |
| `card_product_variant` / `card_product_variant_doc` | `(C04,V-AMEX03,AMEX,PLATINUM,03)` / `(C04,V-AMEX03,DOC-AP003)`; AP003 2쪽 대상 카드 근거 |
| `card_bnft` | `(C04,PV-J1,B-SPECIAL,LOCAL)`; `(C04,PV-J1,B-BASE,LOCAL)`; AMEX 선택 발렛은 별도 `(B-VALET,LOCAL,VARIANT)` + `card_bnft_variant→V-AMEX03` |
| `card_bnft_rule` | `(B-SPECIAL,R-15,PERCENT_OF_TXN,1.5%,HANAMONEY)`, `(B-SPECIAL,R-12,...,1.2%)`, `(B-BASE,R-1,...,1%)` |
| `card_bnft_target` / `rule_target` | 해외·항공·면세·여행 대상→`R-15`; 쇼핑·백화점·마트·주유 대상→`R-12`; 대상별 예외는 해당 규칙식에 귀속 |
| `card_cond` / `expr` | `(K-J50,PREV_MONTH_SPEND,min=500000)` → `E-J50`; 기본 1%는 검증된 무실적 상태 |
| `card_limit_pool` / `tier` / `rule_pool` | `(P-J-SPECIAL,MONTH,HANAMONEY)`, `(P-J-SPECIAL,T-1,100000)`; `R-15`와 `R-12`가 같은 풀 소비. 기본 `R-1`은 이 풀 소비하지 않음 |
| `card_bnft_rel` | `(B-SPECIAL,B-BASE,MUTUALLY_EXCLUSIVE)`, `(B-SPECIAL,B-BASE,FALLBACK_AFTER_CAP,trigger_pool=P-J-SPECIAL)`; 원문 4쪽 우선 정책 |
| `card_bnft_rule_evidence` | `R-15/R-12→EVD-J3→DOC-JADE 3쪽 청크`, 관계의 출처는 4쪽 별도 근거 행 필요 |

### 5.2 토스뱅크 하나카드 Wide C05

원문 `credit/신용_토스뱅크하나카드Wide_상품설명서(공식PDF)_15024_20250703.pdf` 1쪽: 40만 원 미만 1%, 이상 2%, 월 할인 한도 10만 원. 구간 하한 포함·상한 미포함으로 정규화한다.

| 논리 테이블 | 샘플 행 |
|---|---|
| `card_product` / `card_policy_version` / `card_bnft` | `(C05,Wide)` → `(C05,PV-W1)` → `(C05,PV-W1,B-WIDE,LOCAL)` |
| `card_cond` | `(K-W-LOW,PREV_MONTH_SPEND,[0,400000))`, `(K-W-HIGH,PREV_MONTH_SPEND,[400000,∞))` |
| `card_cond_expr` / `atom` | `(E-W-LOW,branch1,K-W-LOW)`, `(E-W-HIGH,branch1,K-W-HIGH)` |
| `card_bnft_rule` | `(B-WIDE,R-W-1,E-W-LOW,PERCENT_OF_TXN,1%,KRW)`, `(B-WIDE,R-W-2,E-W-HIGH,PERCENT_OF_TXN,2%,KRW)` |
| `card_bnft_target` / `rule_target` | `(T-W-ALL,국내/해외 일시불)`; 두 규칙 모두 같은 대상 연결 |
| `card_limit_pool` / `tier` / `rule_pool` | `(P-W-MONTH,MONTH,KRW)`, `(T-W-CAP,100000)`; 두 규칙이 같은 풀 소비 |
| 근거 | `R-W-1/R-W-2→EVD-W1→DOC-WIDE 1쪽 청크` |

### 5.3 달달 하나 체크카드 D05

원문 `debit/체크_달달하나체크카드_상품설명서(공식PDF,URL추정확인)_15114_20260306.pdf` 1쪽: 쇼핑·딜리버리 등 5%, 쇼핑 등 영역 한도 2/4/6천, 전체 통합 한도 1/2/3만(실적 30/70/100만), 대상별 결제/제외 조건. 파일의 `URL추정확인` 출처 상태는 미해소다.

| 논리 테이블 | 샘플 행 |
|---|---|
| `card_product` / `policy_version` | `(D05,달달)` / `(D05,PV-D1)` |
| `card_bnft` / `rule` | `(B-SHOP,LOCAL)`·`(R-SHOP,5%)`; `(B-DELIVERY,LOCAL)`·`(R-DELIVERY,5%)` |
| `card_cond` / `expr` | `[300000,700000)`, `[700000,1000000)`, `[1000000,∞)` 실적 조건; 딜리버리는 `공식 홈페이지 OR 공식 앱` 원자식, 백화점은 `NOT 임대매장` 원자식 |
| `card_limit_pool` | `(P-SHOP,영역 월 한도)`, `(P-ALL,카드 전체 월 통합 한도)` — **서로 다른 부모 풀** |
| `card_limit_tier` | `P-SHOP`의 실적 구간별 `2000/4000/6000`; `P-ALL`의 같은 구간별 `10000/20000/30000` |
| `card_bnft_rule_pool` | `R-SHOP→P-SHOP + P-ALL`; `R-DELIVERY→P-ALL` 및 원문상 해당 영역 풀. 숫자가 같아도 영역 풀은 독립 |
| 근거 | 각 조건/규칙/한도→승인된 `EVD-D1`(DOC-DAL 1쪽); 정확한 청크는 실제 추출 후 확정 |

### 5.4 공통 정책의 승인 경계

`MP001`·`MP004` 1쪽에는 Mastercard Platinum 공통 할인 서비스가 기재되지만, 2쪽의 **선택서비스 대상 카드와 조건은 서로 다르다**. 아래는 공통 조항 동일성이 검증되어야만 사용할 수 있는 **구조 시험 행**이며 현재 승인된 상품 적용 사실이 아니다.

| 논리 테이블 | 구조 시험 행 |
|---|---|
| `card_common_bnft` / `card_common_policy_version` | `(CB-MC-TRIPCOM,Mastercard Platinum 공통 Trip.com 호텔 할인)` → `(CB-MC-TRIPCOM,CV-1,valid_from=확인대기)`; 양 파일 1쪽의 6% 문구를 조항별 대조할 후보 |
| `card_common_bnft_rule` / `target` | `(CB-MC-TRIPCOM,CV-1,CR-1,PERCENT_OF_TXN,6%,대상=Trip.com 호텔)` — 실제 예외/기간 동일성 추가 검증 필요 |
| `card_product` / `policy_version` / `card_bnft` | 설명용 상품 `(P-A,PV-A,B-A,COMMON_LINK)`, `(P-B,PV-B,B-B,COMMON_LINK)` |
| `card_bnft_common` | `(P-A,PV-A,B-A,CB-MC-TRIPCOM,CV-1,PENDING)`, `(P-B,PV-B,B-B,CB-MC-TRIPCOM,CV-1,PENDING)`; 승인 전 서비스 조회에서 제외 |
| `card_bnft_variant` / `card_bnft_cond` | 각 상품의 실제 발급형과 추가 조건은 확인된 경우에만 연결. 공통 조건에 로컬 조건은 AND로 추가 |
| `MP001` / `MP004` 선택서비스 | 서로 다른 대상·실적 조건이므로 위 공통 Trip.com 정책과 합치지 않고 상품 고유 혜택 또는 별도 검증된 공통 정책으로 관리 |
| `VP001` 2023/2026 | `DOC-VP23`, `DOC-VP26`의 문서판은 확인. `CV-23`, `CV-26` 공통 정책판 및 각 상품 적용 기간은 비교·승인 후에만 생성 |

## 6. SQL 초안: 상품에서 혜택·규칙·근거로

**모두 V4 제안 테이블 기준의 미실행 SQL**이다. `:card_id`, `:as_of`, `:variant_id`, `:benefit_id`는 바인딩 값. `:variant_id IS NULL`이면 발급형 전체 **목록**을 보되 단일 발급카드의 실제 적용 결과로 주장하지 않는다. SQL로 후보 정책을 찾은 뒤 조건식, 한도 잔량, 거래 데이터는 별도 평가가 필요하다.

```sql
-- 1. card_id만으로 승인·유효 상품 혜택 전체 목록. 발급형 범위를 함께 표시.
SELECT p.card_id, p.product_nm, v.policy_ver_id, v.policy_scope_cd,
       b.card_bnft_id, b.bnft_nm, b.bnft_origin_cd, b.bnft_scope_cd
FROM db_pipeline.card_product p
JOIN db_pipeline.card_policy_version v ON v.card_id=p.card_id
JOIN db_pipeline.card_bnft b
  ON (b.card_id,b.policy_ver_id)=(v.card_id,v.policy_ver_id)
WHERE p.card_id=:card_id AND v.policy_status_cd='APPROVED'
  AND :as_of>=v.valid_from
  AND (v.valid_to_excl IS NULL OR :as_of<v.valid_to_excl)
  AND b.verification_status_cd='CONFIRMED'
  AND (b.bnft_origin_cd='LOCAL' OR EXISTS (
    SELECT 1 FROM db_pipeline.card_bnft_common x
    JOIN db_pipeline.card_common_policy_version cv
      ON (cv.common_bnft_id,cv.common_ver_id)=(x.common_bnft_id,x.common_ver_id)
    WHERE (x.card_id,x.policy_ver_id,x.card_bnft_id)=
          (b.card_id,b.policy_ver_id,b.card_bnft_id)
      AND x.apply_status_cd='APPROVED' AND cv.policy_status_cd='APPROVED'
      AND :as_of>=cv.valid_from
      AND (cv.valid_to_excl IS NULL OR :as_of<cv.valid_to_excl)))
ORDER BY v.policy_ver_id,b.card_bnft_id;

-- 2. 특정 발급형의 현재 정책판: 상품 BASE + 지정 발급형 SUPPLEMENT.
SELECT v.* FROM db_pipeline.card_policy_version v
WHERE v.card_id=:card_id AND v.policy_status_cd='APPROVED'
  AND :as_of>=v.valid_from
  AND (v.valid_to_excl IS NULL OR :as_of<v.valid_to_excl)
  AND (v.policy_scope_cd='PRODUCT' OR EXISTS (
       SELECT 1 FROM db_pipeline.card_policy_variant x
       WHERE (x.card_id,x.policy_ver_id)=(v.card_id,v.policy_ver_id)
         AND x.card_variant_id=:variant_id));

-- 3. 한 LOCAL 혜택의 규칙·대상·조건. benefit-wide 조건은 아래 UNION.
WITH rule_conditions AS (
  SELECT r.card_id,r.policy_ver_id,r.card_bnft_id,r.rule_id,
         a.card_cond_id,'RULE'::text AS condition_scope
  FROM db_pipeline.card_bnft_rule r
  JOIN db_pipeline.card_cond_expr_atom a
    ON (a.card_id,a.policy_ver_id,a.expr_id)=(r.card_id,r.policy_ver_id,r.expr_id)
  UNION ALL
  SELECT x.card_id,x.policy_ver_id,x.card_bnft_id,NULL::varchar(20),
         x.card_cond_id,'BENEFIT'
  FROM db_pipeline.card_bnft_cond x
)
SELECT r.rule_id,r.calc_method_cd,r.value_num,r.value_unit_cd,
       t.target_id,t.target_nm,rc.condition_scope,c.card_cond_id,c.cond_type_cd,
       c.cond_min_amt,c.cond_max_amt_excl
FROM db_pipeline.card_bnft_rule r
LEFT JOIN db_pipeline.card_bnft_rule_target rt
  ON (rt.card_id,rt.policy_ver_id,rt.card_bnft_id,rt.rule_id)=
     (r.card_id,r.policy_ver_id,r.card_bnft_id,r.rule_id)
LEFT JOIN db_pipeline.card_bnft_target t
  ON (t.card_id,t.policy_ver_id,t.card_bnft_id,t.target_id)=
     (rt.card_id,rt.policy_ver_id,rt.card_bnft_id,rt.target_id)
LEFT JOIN rule_conditions rc
  ON (rc.card_id,rc.policy_ver_id,rc.card_bnft_id)=
     (r.card_id,r.policy_ver_id,r.card_bnft_id)
 AND (rc.rule_id=r.rule_id OR rc.condition_scope='BENEFIT')
LEFT JOIN db_pipeline.card_cond c
  ON (c.card_id,c.policy_ver_id,c.card_cond_id)=
     (rc.card_id,rc.policy_ver_id,rc.card_cond_id)
WHERE r.card_id=:card_id AND r.policy_ver_id=:policy_ver_id
  AND r.card_bnft_id=:benefit_id;
-- DNF branch_no/negate_yn까지 포함한 실제 판정은 atom 행을 별도 조회해야 함.

-- 4. 승인된 공통 정책판을 공유하는 상품.
SELECT x.common_bnft_id,x.common_ver_id,p.card_id,p.product_nm,
       b.card_bnft_id,b.bnft_scope_cd
FROM db_pipeline.card_bnft_common x
JOIN db_pipeline.card_bnft b
  ON (b.card_id,b.policy_ver_id,b.card_bnft_id)=
     (x.card_id,x.policy_ver_id,x.card_bnft_id)
JOIN db_pipeline.card_product p ON p.card_id=x.card_id
JOIN db_pipeline.card_policy_version v
  ON (v.card_id,v.policy_ver_id)=(x.card_id,x.policy_ver_id)
JOIN db_pipeline.card_common_policy_version cv
  ON (cv.common_bnft_id,cv.common_ver_id)=(x.common_bnft_id,x.common_ver_id)
WHERE x.common_bnft_id=:common_bnft_id AND x.apply_status_cd='APPROVED'
  AND v.policy_status_cd='APPROVED' AND cv.policy_status_cd='APPROVED'
  AND :as_of>=v.valid_from AND (v.valid_to_excl IS NULL OR :as_of<v.valid_to_excl)
  AND :as_of>=cv.valid_from AND (cv.valid_to_excl IS NULL OR :as_of<cv.valid_to_excl);

-- 5. 상품 고유 + 공통 적용 규칙의 단일 출력 형태.
WITH active_bnft AS (
  SELECT b.* FROM db_pipeline.card_bnft b
  JOIN db_pipeline.card_policy_version v
    ON (v.card_id,v.policy_ver_id)=(b.card_id,b.policy_ver_id)
  WHERE b.card_id=:card_id AND b.verification_status_cd='CONFIRMED'
    AND v.policy_status_cd='APPROVED' AND :as_of>=v.valid_from
    AND (v.valid_to_excl IS NULL OR :as_of<v.valid_to_excl)
    AND (v.policy_scope_cd='PRODUCT' OR EXISTS (
      SELECT 1 FROM db_pipeline.card_policy_variant pv
      WHERE (pv.card_id,pv.policy_ver_id)=(b.card_id,b.policy_ver_id)
        AND pv.card_variant_id=:variant_id))
    AND (b.bnft_scope_cd='PRODUCT' OR EXISTS (
      SELECT 1 FROM db_pipeline.card_bnft_variant bv
      WHERE (bv.card_id,bv.policy_ver_id,bv.card_bnft_id)=
            (b.card_id,b.policy_ver_id,b.card_bnft_id)
        AND bv.card_variant_id=:variant_id))
)
SELECT b.card_bnft_id,'LOCAL' AS rule_source,r.rule_id AS rule_key,
       r.calc_method_cd,r.value_num,r.value_unit_cd
FROM active_bnft b JOIN db_pipeline.card_bnft_rule r
  ON (r.card_id,r.policy_ver_id,r.card_bnft_id)=
     (b.card_id,b.policy_ver_id,b.card_bnft_id)
WHERE b.bnft_origin_cd='LOCAL' AND r.rule_status_cd='CONFIRMED'
UNION ALL
SELECT b.card_bnft_id,'COMMON',cr.common_rule_id,
       cr.calc_method_cd,cr.value_num,cr.value_unit_cd
FROM active_bnft b
JOIN db_pipeline.card_bnft_common x
  ON (x.card_id,x.policy_ver_id,x.card_bnft_id)=
     (b.card_id,b.policy_ver_id,b.card_bnft_id)
JOIN db_pipeline.card_common_policy_version cv
  ON (cv.common_bnft_id,cv.common_ver_id)=(x.common_bnft_id,x.common_ver_id)
JOIN db_pipeline.card_common_bnft_rule cr
  ON (cr.common_bnft_id,cr.common_ver_id)=(cv.common_bnft_id,cv.common_ver_id)
WHERE b.bnft_origin_cd='COMMON_LINK' AND x.apply_status_cd='APPROVED'
  AND cv.policy_status_cd='APPROVED' AND :as_of>=cv.valid_from
  AND (cv.valid_to_excl IS NULL OR :as_of<cv.valid_to_excl);
-- 반환값은 정책 후보 수치. 거래별 조건·잔량 적용 전의 실제 보상액이 아님.

-- 6. 상품 규칙에서 PDF/쪽/청크/승인 후보까지 역추적.
SELECT r.card_id,r.policy_ver_id,r.card_bnft_id,r.rule_id,
       e.evidence_id,d.card_doc_id,d.doc_title,e.page_no,
       e.card_doc_chunk_id,e.card_extr_stg_id,e.quote_txt,
       c.chunk_raw_txt,p.page_raw_txt
FROM db_pipeline.card_bnft_rule r
JOIN db_pipeline.card_bnft_rule_evidence re
  ON (re.card_id,re.policy_ver_id,re.card_bnft_id,re.rule_id)=
     (r.card_id,r.policy_ver_id,r.card_bnft_id,r.rule_id)
JOIN db_pipeline.card_source_evidence e ON e.evidence_id=re.evidence_id
JOIN db_pipeline.card_doc_chunk c
  ON (c.card_doc_id,c.page_no,c.card_doc_chunk_id)=
     (e.card_doc_id,e.page_no,e.card_doc_chunk_id)
JOIN db_pipeline.card_doc_page p
  ON (p.card_doc_id,p.page_no)=(c.card_doc_id,c.page_no)
JOIN db_pipeline.card_doc d ON d.card_doc_id=p.card_doc_id
WHERE r.card_id=:card_id AND r.policy_ver_id=:policy_ver_id
  AND r.card_bnft_id=:benefit_id AND e.approval_status_cd='APPROVED';
-- 공통 규칙은 card_common_rule_evidence로 같은 e→chunk→page→doc 경로 사용.
```

정합성 게이트 예시:

```sql
-- 7a. 부모 정책판이 없는 혜택(물리 FK 없는 설계의 필수 검사).
SELECT b.card_id,b.policy_ver_id,b.card_bnft_id
FROM db_pipeline.card_bnft b
LEFT JOIN db_pipeline.card_policy_version v
  ON (v.card_id,v.policy_ver_id)=(b.card_id,b.policy_ver_id)
WHERE v.policy_ver_id IS NULL;

-- 7b. 한 상품의 두 승인 BASE 정책판이 시간상 겹치는지.
SELECT a.card_id,a.policy_ver_id AS first_ver,b.policy_ver_id AS second_ver
FROM db_pipeline.card_policy_version a
JOIN db_pipeline.card_policy_version b
  ON b.card_id=a.card_id AND b.policy_ver_id>a.policy_ver_id
WHERE a.policy_scope_cd='PRODUCT' AND b.policy_scope_cd='PRODUCT'
  AND a.policy_effect_cd='BASE' AND b.policy_effect_cd='BASE'
  AND a.policy_status_cd='APPROVED' AND b.policy_status_cd='APPROVED'
  AND daterange(a.valid_from,a.valid_to_excl,'[)')
      && daterange(b.valid_from,b.valid_to_excl,'[)');

-- 7c. 공통 연결 혜택에 로컬 계산 규칙도 있으면 출력값 원천이 충돌.
SELECT b.card_id,b.policy_ver_id,b.card_bnft_id
FROM db_pipeline.card_bnft b
WHERE b.bnft_origin_cd='COMMON_LINK'
  AND EXISTS (SELECT 1 FROM db_pipeline.card_bnft_rule r
              WHERE (r.card_id,r.policy_ver_id,r.card_bnft_id)=
                    (b.card_id,b.policy_ver_id,b.card_bnft_id));

-- 7d. 규칙↔대상 행의 양쪽 부모 누락 또는 소속 혜택 불일치.
SELECT rt.card_id,rt.policy_ver_id,rt.card_bnft_id,rt.rule_id,rt.target_id
FROM db_pipeline.card_bnft_rule_target rt
LEFT JOIN db_pipeline.card_bnft_rule r
  ON (r.card_id,r.policy_ver_id,r.card_bnft_id,r.rule_id)=
     (rt.card_id,rt.policy_ver_id,rt.card_bnft_id,rt.rule_id)
LEFT JOIN db_pipeline.card_bnft_target t
  ON (t.card_id,t.policy_ver_id,t.card_bnft_id,t.target_id)=
     (rt.card_id,rt.policy_ver_id,rt.card_bnft_id,rt.target_id)
WHERE r.rule_id IS NULL OR t.target_id IS NULL;

-- 7e. 한 COMMON_LINK 인스턴스에 승인된 공통 정책판이 둘 이상 연결.
SELECT card_id,policy_ver_id,card_bnft_id,count(*) AS approved_links
FROM db_pipeline.card_bnft_common
WHERE apply_status_cd='APPROVED'
GROUP BY card_id,policy_ver_id,card_bnft_id
HAVING count(*)>1;
```

추가 승인 게이트: `card_policy_variant`·`card_bnft_variant`의 부모 발급형 존재, `card_bnft_rule_target`의 규칙/대상 양쪽 부모, `card_bnft_rule_pool`의 규칙/풀 양쪽 부모, `card_bnft_cond`의 혜택/조건 양쪽 부모, 공통 링크의 공통판 존재 및 중복 적용, `rule/cond/evidence` 간 문서·청크·승인 상태, 같은 실효 범위의 구간 겹침/누락, 혜택 대체 순환, 개정판 기간 충돌을 검사한다. 규칙 구간은 `card_id + 정책판 + 혜택 + 대상 + 유효 기간 + 조건식` 기준으로 검사한다. `card_doc_id`만으로 묶으면 안 된다. 검증 SQL은 실제 스키마가 만들어진 뒤 실행·보완해야 한다.

## 7. DDL 작성 전 결정할 사항

1. **정책판과 발급형:** 기본 `PRODUCT`판 + 발급형 `SUPPLEMENT`판 규칙을 채택할지. 같은 혜택 코드가 두 판에 있으면 기본은 충돌로 거부하고, 교체가 필요한 실제 사례에서만 명시적 override 관계를 도입할지.
2. **공통 정책 승인 기준:** MP001/MP004의 동일한 공통 조항을 한 정책으로 승인할 범위와 조항별 차이 검증 방법. AP003 2쪽의 JADE 한정 선택서비스는 우선 상품 발급형 혜택으로 두는 판단.
3. **원천 힌트 정리:** V3 `card_doc.card_id`와 기존 `card_extr_stg.card_id`를 원천 추출 맥락으로만 유지할지, 신규 문서에는 NULL/별도 실행 범위를 적용할지. 확정 혜택 테이블에서는 `card_doc_id`와 단일 `card_extr_stg_id` 필수·UNIQUE를 제거하고 N:M 근거로 전환.
4. **코드·ID·제약:** 기존 문자열 업무 ID 생성 규칙을 자식 로컬 ID에 적용. 관계 테이블은 복합 PK만 사용. 상품/공통 정책판의 기간 겹침, 공통 링크 한 개 제한, 조건식 DNF, 단위/JSON 계약의 CHECK·SQL 승인 게이트 상세 결정.
5. **공통 컴포넌트의 물리화 시점:** DBML의 독립 공통 규칙/조건/한도는 의미적으로 필요하지만, 원문·상품 적용이 검증된 공통 정책부터 생성한다. V4 전체 DDL을 이번 작업에서 작성하지 않는다.

**검토 결론:** `card_id`에서 승인 정책판을 찾고 혜택의 `LOCAL` 규칙 또는 승인된 `COMMON_LINK` 공통 규칙으로 내려가며, 근거는 별도 N:M 링크로 PDF까지 역추적하는 경로가 정의되었다. `card_id`만으로 상품의 확정 혜택 목록을 조회할 수 있고, 실제 발급형/거래 단위 판정에는 발급형 ID·거래 입력·한도 사용량이 더 필요하다. V4 DBML은 논리 검토용이며 위 SQL은 실제 DB에서 실행 검증하지 않았다.
