# 4. 근거 검증과 검토 보류

[목차](README.md) · [혜택 등록](03_BENEFIT_REGISTRATION.md)

<details><summary>4.1 검증 레이어</summary>

검증은 한 번의 승인 플래그가 아니라 입력/PDF 검사, 추출 값과 원문 비교, staging SQL gate, 혜택/관계 gate, DB 무결성 검사, 답변의 사실 단위 검증으로 나뉜다.

<details><summary>4.1.1 원문 및 추출 근거</summary>

- PDF 등록: [`DocumentService`](../../payment_card/db_pipeline/document_service.py)가 파일/페이지/해시 품질을 확인. [`RegisterService._insert()`](../../payment_card/db_pipeline/register_service.py)는 DB 저장 후 `verify_doc` 및 로컬/저장 페이지 hash를 비교하며 ERROR면 transaction 실패.
- AI 추출: [`ExtractionService`](../../payment_card/db_pipeline/extraction_service.py)의 `check_values()`는 quote 안의 값과 숫자를 검사하고, `link_check()`는 source-evidence 연결 근거를 점검한다. 위치 또는 원문 일치가 불확실하면 근거 승인으로 추정하지 않는다.
- 추출 근거: `card_source_evidence`는 quote, page, chunk, staging 후보 관계를 기록한다. 정의는 [6장](06_POSTGRESQL_SCHEMA.md), insert SQL은 [`extraction_repository.sql`](../../payment_card/db_pipeline/extraction_repository.sql).
</details>

<details><summary>4.1.2 등록 gate 및 REVIEW 경로</summary>

`ProductBenefitService`와 `CommonBenefitService`는 후보 검증 결과가 충분하지 않을 때 혜택을 확정 등록하지 않고 review/excluded 결과를 분리한다. 일반적인 구분은 다음과 같다.

- 정상: 검증 통과 후보가 목표 엔티티/관계로 저장되고 transaction이 정상 종료.
- 실패: DB 무결성 오류나 쓰기 예외가 transaction을 중단하고 rollback.
- 검토 보류: 근거/대상/조건이 모호하거나 입력 gate가 부족해 해당 후보를 보류. 이는 DB 오류와 같은 의미가 아니다.
- 제외: 대상이 아닌 후보 또는 반려/만료 등 정책상 처리 대상이 아닌 후보를 배제.

정확한 조건은 각 서비스의 if 분기와 `common_benefit_repository.sql` statement를 확인한다. 관련 진입점: [`ProductBenefitService.register_run()`](../../payment_card/db_pipeline/product_benefit_service.py), [`CommonBenefitService.apply_run()`](../../payment_card/db_pipeline/common_benefit_service.py).
</details>
</details>

<details><summary>4.2 답변 시 근거 조건</summary>

조회 단계는 evidence를 검색 결과 구조에 포함하고, 답변 검증은 LLM이 쓴 각 사실을 evidence ID와 연결한다. 근거가 하나도 없거나 검증 가능한 point가 없으면 답변을 거부/제한한다. “검토 대기”는 근거 인용과 동의어가 아니며, 사용자 응답에서 내부 상태를 숨기는 표시 로직이 판정을 승인으로 바꾸지 않는다. 자세한 후속 경로는 [9장](09_ANSWER_VALIDATION.md).
</details>

<details><summary>4.3 한계와 확인 항목</summary>

저장소 내 DDL은 제약 선언을 보여 주지만 실제 서버의 제약 적용 결과는 보여 주지 않는다. 데이터 기반 검증도 본 작업에서는 수행하지 않았다. 따라서 운영 데이터에서의 통과 건수나 승인 상태는 확인하지 않았다.
</details>

[스키마 →](06_POSTGRESQL_SCHEMA.md) · [답변 검증 →](09_ANSWER_VALIDATION.md)

