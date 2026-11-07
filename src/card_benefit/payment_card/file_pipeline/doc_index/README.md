# doc_index/

카드사별 원본 목록과 PDF 파일을 대조해 문서·상품 인덱스를 만들고 대표 문서의 쪽별 추적 JSON을 생성한다.

## 파일

| 파일 | 역할 |
|---|---|
| `__init__.py` | `doc_index`를 패키지로 표시한다. |
| `adapters/__init__.py` | 하나·우리 어댑터를 공통 목록으로 등록한다. |
| `adapters/hana.py` | 하나카드 원본 manifest를 공통 문서 항목으로 바꾼다. |
| `adapters/woori.py` | 우리카드 원본 manifest를 공통 문서 항목으로 바꾼다. |
| `batch.py` | 인덱스의 대표 문서를 페이지 원문·품질 정보가 있는 traceability JSON으로 변환한다. |
| `cli.py` | 카드사별 `documents.csv`, `product_docs.csv`, `summary.json`을 만든다. |
| `core.py` | 문서 중복·대표 선정, 검토 표시, 상품-문서 연결 행을 구성한다. |
| `measure.py` | PDF의 SHA-256, 쪽 수, 추출 글자 수를 측정한다. |
| `schema.py` | 인덱스 열과 문서 역할·출처 분류 값을 정의한다. |
| `tables.py` | PDF 페이지 표 추출 결과와 페이지 글자의 일치 신호를 계산한다. |

## 실행

저장소 루트에서 인덱스를 만든다.

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=src:src/card_benefit uv run --locked --no-sync python -m payment_card.file_pipeline.doc_index.cli --help
```

대표 문서의 traceability JSON을 만든다. 출력 폴더를 직접 지정한다.

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=src:src/card_benefit uv run --locked --no-sync python -m payment_card.file_pipeline.doc_index.batch --help
```

두 `--help` 명령은 성공했다. 도움말만 표시하며 문서 처리는 실행하지 않았다.

## 입력·출력과 연결

`cli`는 `src/data/<issuer>_all` 아래 카드사별 원본 목록과 PDF 파일을 읽고, 지정한 인덱스 출력 폴더에 `documents.csv`, `product_docs.csv`, `summary.json`을 쓴다. 사람 검토용 카드 구분·문서 판정 CSV가 출력 위치에 있으면 반영한다. `batch`는 `documents.csv`와 PDF를 입력으로 받고 지정한 위치에 문서별 JSON과 `batch_report.json`을 쓴다. 다음 단계인 [`chunking`](../chunking/)은 이 인덱스 및 traceability JSON을 받아 청크 JSON을 만든다.

인덱스의 `doc_id`는 PDF SHA-256의 앞 16자리이며 `file_path`가 원본 경로를 가리킨다. `batch`가 저장하는 traceability JSON은 전체 SHA-256을 문서에, `page_no`와 페이지 텍스트를 쪽별로 보존하고, traceability의 쪽 단위 `chunks`에는 `chunk_id`(`p`와 쪽 번호), `page_no`, `start_pos`, `end_pos`를 기록한다. 이 문자 위치는 각 쪽 텍스트 기준 1부터 시작하고 끝 문자를 포함한다.

## 주의

traceability JSON에는 페이지 전체 원문이 들어간다. 출력 폴더를 직접 지정하고 저장소에 원문 JSON을 두지 않는다. `--overwrite`를 주지 않으면 기존 결과 파일이 있을 때 덮어쓰지 않는다.
