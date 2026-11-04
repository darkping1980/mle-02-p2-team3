# 3. 혜택 등록 및 카드 적용

[목차](README.md) · [AI 추출](02_AI_EXTRACTION.md)

<details><summary>3.1 진입점과 실행 단위</summary>

[`benefit_main.py`](../../payment_card/db_pipeline/benefit_main.py)는 product/common/brand-compare 작업을 선택한다. 적용 모드가 아니면 변경 작업을 하지 않으며 공통 혜택 등록과 카드별 적용도 분리된 실행 단위다.

<details><summary>3.1.1 ProductBenefitService.register_run()</summary>

소스 [ProductBenefitService.register_run() 로컬 (L58)](../../payment_card/db_pipeline/product_benefit_service.py#L58) · [GitHub 기준 커밋](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/product_benefit_service.py#L58).

- run과 대상 카드를 잠그고 기존 무결성 오류를 검사한 뒤 staging 후보를 조회한다.
- 기존 카드 혜택과 동일 키가 있으면 서비스의 변경 정책에 따라 unchanged/excluded/review로 처리한다. 후보 상태, SQL 검사 코드, 관계/규칙 및 근거가 부족하면 등록 대신 review 결과를 남긴다.
- 통과 후보는 `card_product_item`(현재 혜택은 item type BENEFIT) 및 rule/evidence 관계에 반영한다. 삽입 누락이나 무결성 gate 오류가 발생하면 예외로 해당 카드 작업을 rollback한다.
- 정확한 SQL은 [`common_benefit_repository.sql`](../../payment_card/db_pipeline/common_benefit_repository.sql)의 `lock_card`, `integrity_errors`, `select_merged_benefits`, `insert_local_benefit`, evidence-link statement들이다. Python facade는 [`common_benefit_service.py`](../../payment_card/db_pipeline/common_benefit_service.py)와 `product_benefit_service.py`.
</details>

<details><summary>3.1.2 CommonBenefitService.register_run() / apply_run()</summary>

소스 [CommonBenefitService.register_run() 로컬 (L319)](../../payment_card/db_pipeline/common_benefit_service.py#L319) · [GitHub 기준 커밋](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/common_benefit_service.py#L319), [apply_run() 로컬 (L373)](../../payment_card/db_pipeline/common_benefit_service.py#L373) · [GitHub 기준 커밋](https://github.com/darkping1980/mle-02-p2-team3/blob/7b37de03b17a9671d703f183ec83b386c78d98f7/src/card_benefit/payment_card/db_pipeline/common_benefit_service.py#L373).

- `register_run()`은 문서 단위 대표 후보를 확인하고 `card_common`/`card_common_bnft`에 공통 엔티티와 혜택을 등록한다. SQL 적격 후보만 처리하며 제외·불충분·모호한 연결은 REVIEW/EXCLUDED로 남는다.
- `apply_run()`은 등록된 공통 혜택을 지정 카드에 적용할 후보를 검증한다. 카드 상태, 브랜드/등급, 선택 서비스 식별, 적용 근거와 기간 등을 확인하고 확정 불가하면 REVIEW로 보류한다.
- 동일한 코드/내용의 기존 항목은 unchanged가 될 수 있다. 변경된 공통 정보는 이전 출처와의 비교를 거치며 불확실한 변경은 검토로 돌린다.
- card/run 단위 transaction 블록 안에서 쓰기가 수행되고 예외 시 해당 블록은 rollback된다. 공통 등록 완료가 모든 카드 적용 완료를 의미하지 않는다.
- mapper statement는 `common_benefit_repository.sql`의 `find_common`, `insert_common`, `find_common_bnft`, `insert_common_bnft`, `update_common_bnft`, `insert_common_apply` 등이다.
</details>
</details>

<details><summary>3.2 후보 상태와 저장 모델</summary>

상품별 혜택은 현재 SQL에서 `card_product_item` 테이블의 `item_type_cd='BENEFIT'`로 표현된다. 공통 혜택은 `card_common_bnft`, 카드별 적용은 `card_common_bnft_apply`다. 증거 연결은 `card_evidence_link` 및 `card_source_evidence`를 사용한다.

실제 소스는 `SUCCEEDED` 추출만을 무조건 수용하지 않고 SQL check 상태, 관계, 규칙, 근거 등의 개별 gate를 적용한다. 데이터 검토 상태와 업무 적용 상태는 별도다. 자세한 상태/제약은 [4장](04_EVIDENCE_VALIDATION.md)과 [6장](06_POSTGRESQL_SCHEMA.md).
</details>

[근거 검증 →](04_EVIDENCE_VALIDATION.md) · [임베딩 →](05_EMBEDDING.md)

