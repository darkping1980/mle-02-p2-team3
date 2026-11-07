# ledger/

인덱스·추적·청크 JSON을 file_pipeline 문서·쪽·청크 테이블 열에 매핑해 검토용 SQL을 출력한다.

## 파일

| 파일 | 역할 |
|---|---|
| `__init__.py` | `ledger`를 패키지로 표시한다. |
| `plan.py` | 입력 JSON·CSV 검증, ID 및 테이블 행 계획, 읽기 전용 스키마 조회 SQL과 적재 SQL 생성을 제공한다. |

## 실행

저장소 루트에서 실행 옵션을 확인한다.

```bash
UV_CACHE_DIR=/tmp/uv-cache PYTHONPATH=src:src/card_benefit uv run --locked --no-sync python -m payment_card.file_pipeline.ledger.plan --help
```

`--help` 명령은 성공했다. 도움말만 표시하며 파일 읽기나 SQL 생성은 실행하지 않았다.

## 입력·출력과 연결

입력은 [`doc_index`](../doc_index/)의 `documents.csv`, [`chunking`](../chunking/)의 청크 JSON, 그리고 `doc_index.batch`가 만든 traceability JSON이다. `plan`은 문서·쪽·청크 테이블의 열과 입력 값의 대응을 검증하고 요약을 출력한다. `--sql-out`은 사용자가 검토 후 실행할 SQL 파일을, `--schema-sql-out`은 스키마 확인용 읽기 전용 SQL 파일을 지정 경로에 쓴다. 이 모듈은 데이터베이스 연결 코드를 포함하지 않으며 SQL 실행은 사용자가 별도로 수행한다. AI 실행 기록과 추출 결과의 확정 테이블 적재는 모듈 문서에서 미구현 또는 범위 밖으로 표시되어 있다.

## 주의

생성 적재 SQL에는 페이지 및 청크 원문이 들어간다. SQL 출력 경로는 저장소 밖이어야 하며, 생성 파일을 검토한 뒤 사용한다. `--create-user-id`는 호출자가 제공하는 값이다.
