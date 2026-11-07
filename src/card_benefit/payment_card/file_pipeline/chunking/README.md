# chunking/

traceability JSON의 쪽 텍스트를 연속된 원문 범위를 유지하는 청크 JSON으로 나눈다.

## 파일

| 파일 | 역할 |
|---|---|
| `__init__.py` | `chunking`을 패키지로 표시한다. |
| `build.py` | 페이지별 청크와 문서별 청크 결과를 구성하고 원문 재결합을 확인한다. |
| `cli.py` | 인덱스·traceability JSON·PDF를 읽어 카드사별 청크 JSON을 만든다. |
| `headings.py` | PDF 페이지의 줄과 표 영역을 사용해 제목 위치를 찾는다. |
| `split.py` | 쪽 텍스트를 제목 위치와 크기 기준으로 나눌 범위를 계산한다. |

## 실행

저장소 루트에서 실행 옵션을 확인한다.

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=src:src/card_benefit uv run --locked --no-sync python -m payment_card.file_pipeline.chunking.cli --help
```

`--help` 명령은 성공했다. 도움말만 표시하며 문서 처리는 실행하지 않았다.

## 입력·출력과 연결

입력은 [`doc_index`](../doc_index/)의 `documents.csv`, `product_docs.csv`, traceability JSON, 그리고 인덱스의 `file_path`가 가리키는 PDF다. 결과는 지정한 출력 폴더의 `<issuer>/<doc_id>.chunks.json`이다. `--include-ocr`를 지정하면 인덱스에서 OCR 필요로 분류한 문서도 포함한다. 결과 청크 JSON은 [`extraction`](../extraction/)의 청크 추출 입력 및 [`ledger`](../ledger/)의 오프라인 매핑 입력으로 이어진다.

청크는 원본 `doc_id`와 쪽 번호·순번으로 `chunk_id`를 만들고, 각각 `page_no`, `start_pos`, `end_pos`를 보존한다. 시작 위치는 해당 쪽 텍스트 기준 1부터 세며 끝 글자를 포함한다. 코드가 각 쪽의 청크 텍스트를 이어 붙여 원문과 같은지 확인한다.

## 주의

청크 JSON에는 쪽 원문에서 가져온 `text`가 포함된다. 출력 폴더를 직접 지정하고 저장소에 원문 청크 JSON을 두지 않는다. 기존 파일은 `--overwrite`를 지정해야 바꾼다.
