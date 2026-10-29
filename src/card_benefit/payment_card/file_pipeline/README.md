# file_pipeline — 파일 기반 처리 방식 (담당: 이현근, 미구현)

카드 상품설명서 원본 파일을 Python으로 직접 처리해 파싱·추출·검증까지 수행하는 방식입니다.
`db_pipeline/`(김병주)과 **같은 원천 문서를 다른 방식으로 처리하는 독립 구현**이며, 서로의 결과를 입력으로 쓰지 않습니다.

개발 예정:
- PDF 등 원본 파일 파싱 (먼저 `src/common/document_reader.py` 재사용 검토)
- 텍스트·표 데이터 전처리, 정규식 기반 정보 추출
- Python에서 LLM API 호출 → 엔티티·관계·카드 혜택 조건 추출
- Python 기반 결과 검증 → 공통 형식의 구조화 결과(**결과 A**)
- 참고: `graph-rag` 저장소의 `3_LLM식추출` 학습자료

규칙:
- `db_pipeline/` 을 import하지 않습니다. 공통 모델·SQL은 `payment_card/` 최상위 것을 사용하고 복사하지 않습니다.
- 첫 Python 모듈을 추가할 때 `__init__.py` 도 함께 만듭니다. 테스트는 `payment_card/tests/test_*.py` 에 둡니다.
- 원천·샘플 문서는 `src/card_benefit/data/` 에 둡니다.

상세: `src/card_benefit/docs/development_roles.md`
