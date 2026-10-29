# extraction — 문서 파싱·추출 영역 (미구현)

카드 상품 설명서(PDF 등)를 읽어 정규식·LLM으로 카드·혜택 정보를 추출하는 코드를 둡니다.

- 이 영역은 DB에 직접 쓰지 않습니다. 추출 결과는 `ingestion/`으로 넘깁니다.
- PDF 읽기는 먼저 `src/common/document_reader.py` 재사용을 검토합니다.
- 원본·샘플 문서는 `src/card_benefit/data/`에 둡니다.
