# db_pipeline — PostgreSQL 중심 처리 방식 (담당: 김병주)

개발 현황과 인수인계 내용은 [PROJECT_STATUS.md](PROJECT_STATUS.md)를 참고합니다.

원천 문서의 텍스트·메타데이터를 PostgreSQL에 저장하고, DB 데이터를 대상으로 전처리·AI 추출·검증까지 수행하는 방식입니다.
`file_pipeline/`(이현근)과 **같은 원천 문서를 다른 방식으로 처리하는 독립 구현**이며, 서로의 결과를 입력으로 쓰지 않습니다.

구현됨: PDF 원문 등록과 SQL 검증 (`card_doc` → `card_doc_page` → `card_doc_chunk`).

```powershell
cd src/card_benefit
uv run python -m payment_card.db_pipeline.main --pdf "debit/파일명.pdf"           # 조회만 하는 dry-run
uv run python -m payment_card.db_pipeline.main --pdf "debit/파일명.pdf" --apply   # 실제 등록
```

| 파일 | 역할 |
|---|---|
| `main.py` | 실행 CLI. `--apply` 가 없으면 DB를 변경하지 않음 |
| `document_service.py` | PDF 읽기와 OCR, manifest 대조, 페이지·청크 구성 |
| `register_service.py` | 문서 등록 순서, 중복 확인, 트랜잭션, 등록 후 검증 |
| `document_repository.py` | PostgreSQL 접근과 SQL mapper 호출 |
| `document_repository.sql` | 문서·페이지·청크·OCR 검토 Named SQL. `verify_doc`, `select_doc_chunks` 는 DBeaver에서 바로 실행 가능 |
| `document_storage.py` | 원본 PDF 업로드·다운로드·존재 확인·해시 검증 |
| `storage_main.py` | Storage 전용 CLI. 문서 등록 흐름과 분리 |
| `extraction_schema.py` | LLM 응답 구조와 Python 검증·통합 구조 |
| `extraction_service.py` | LLM 입력 구성, 응답 검증, 원문 대조, 문서 통합, V6 계약 정규화 |
| `extraction_repository.py` | AI 실행·호출·추출 항목의 DB 접근 |
| `extraction_repository.sql` | AI 이력과 추출 결과 Named SQL |

청크는 `PAGE_V1` 규칙으로 페이지당 1건입니다. 페이지 원문 전체가 청크 원문이고, 내용이 없는 페이지는 청크를 만들지 않습니다.

추출 상태가 `SUSPECT`, `GARBLED`, `OCR_REQUIRED` 인 페이지가 있으면 OCR 없이는 등록하지 않습니다.

### OCR 처리

```powershell
uv sync --group ocr     # OCR 패키지 설치. 이 옵션 없이 uv sync를 실행하면 OCR 패키지가 제거됩니다
uv run python -m payment_card.db_pipeline.main --pdf "credit/파일명.pdf" --ocr cross   # windows, rapidocr, cross
```

- RapidOCR 모델은 내려받지 않고 환경 변수 `RAPIDOCR_MODEL_DIR` 의 폴더에서 읽습니다(저장소 밖 경로).
- 정상 페이지는 OCR하지 않습니다. `SUSPECT` 페이지는 오탐이 많아 조건을 만족할 때만 텍스트를 바꾸고, 그 외에는 텍스트 레이어를 유지합니다.
- OCR을 거친 페이지는 자동 확정하지 않습니다. `page_note` 에 `OCR_REVIEW ...` 사유(엔진, 일치율, 불일치 숫자)를 남기고 청크를 `chunk_status = 'EXCLUDED'` 로 등록해 AI 입력에서 뺍니다. 텍스트를 OCR로 바꾼 경우에만 `page_extractor_nm` 에 엔진명을 기록합니다.
- 검토 흐름: `select_review_pages` 로 대상을 조회하고 원본 PDF와 대조한 뒤 `approve_review_page` 를 실행하면 `page_note` 가 `OCR_CONFIRMED ...` 로 바뀌고 청크가 `RAW` 로 돌아갑니다. AI 입력은 `select_ai_target_chunks` 로 조회합니다.
- OCR 문구를 고쳐야 하는 페이지는 승인하지 않습니다. 청크 위치가 달라지므로 다시 나눠야 합니다(아직 구현하지 않음).

### 원본 PDF Storage

```powershell
uv run python -m payment_card.db_pipeline.storage_main status --pdf "debit/파일명.pdf"           # 접속 없음
uv run python -m payment_card.db_pipeline.storage_main upload --pdf "debit/파일명.pdf" --apply   # 1건 업로드
uv run python -m payment_card.db_pipeline.storage_main verify --pdf "debit/파일명.pdf" --apply   # 해시 대조
uv run python -m payment_card.db_pipeline.storage_main restore --pdf "debit/파일명.pdf" --doc-sha256 <해시> --apply
```

- `--apply` 가 없으면 Storage에 접속하지 않습니다. 한 번에 1건만 처리하고, 덮어쓰기·삭제 명령은 없습니다.
- 설정은 `CARD_STORAGE_SUPABASE_URL`, `CARD_STORAGE_SUPABASE_SECRET_KEY`, `CARD_STORAGE_BUCKET` 입니다. CAR가 쓰는 `SUPABASE_*` 와 분리합니다.
- 객체 경로는 `pdf/{doc_sha256}.pdf` 입니다. DB에는 Storage 경로를 저장하지 않습니다.
- 로컬 파일이 우선입니다. 문서 등록은 Storage를 호출하지 않으므로 Storage 장애의 영향을 받지 않습니다.
- 페이지 이미지는 Storage에 저장하지 않고 필요할 때 PDF에서 만듭니다.
- 다른 Supabase로 옮길 때는 `pdf/` 객체를 복사하고 `CARD_STORAGE_*` 값만 바꿉니다.

### AI 추출

Terra 단일 페이지 실행은 `python -m payment_card.db_pipeline.terra_main --help`를 참고합니다.
`--execute`가 없으면 예상 비용만 표시합니다. 실제 실행은 유료 호출과 DB 중간 결과 저장을 수행합니다.
`--preflight`는 읽기 전용 DB 연결로 상품·문서 관계, PAGE_V1 청크, 로컬 PDF 해시와 입력 이미지를 검증하며 API를 호출하지 않습니다.
페이지별 실행은 새 실행 ID를 발급하며, 서로 다른 실행의 페이지는 자동 병합하지 않습니다.
2쪽 실행 전 1쪽 결과와 사용량을 검토하고 실제 누적 비용을 `--previous-spend-usd`에 입력합니다.
같은 문서의 DB 호출 이력도 합산하며 사용량을 알 수 없는 이력이 있으면 중단합니다.
입력 토큰은 이미지 포함 보수적인 추정치를 직접 지정해야 하며 $1은 청구 상한을 보장하지 않습니다.

페이지 텍스트와 페이지 이미지를 LLM에 보내고 결과를 `card_ai_run`, `card_ai_call`, `card_extr_stg`, `card_source_evidence` 에 저장합니다.
LLM 클라이언트는 `ExtractionService` 에 주입하며, 아직 실제 모델은 연결하지 않았습니다.

- 호출 전에 `card_product` 가 있어야 합니다. `card_extr_stg.card_id` 가 NOT NULL입니다.
- `chunk_status` 가 RAW·CLEANED가 아니거나 `OCR_REVIEW` 인 페이지는 입력에서 뺍니다.
- 항목마다 값 존재(`checks.value_check_cd`)와 혜택 연결(`checks.link_check_cd`)을 따로 판단합니다. 표에서 읽은 연결은 `LINK_REVIEW` 로 남아 사람이 확인합니다.
- 페이지 원본은 `call_resp_json`, `stg_raw_item` 에 그대로 두고, 문서 통합 결과는 대표 행의 `stg_normalized_item` 에 씁니다. 중복 행은 `MERGED_DUP` 이고 상위 ID가 대표 행입니다.
- 재실행은 새 `card_ai_run_id` 로 저장하고 이전 결과를 바꾸지 않습니다. `select_run_compare` 로 비교합니다.
- `stg_sql_check_cd`: `OK`, `NO_EVIDENCE`, `QUOTE_NOT_FOUND`, `VALUE_NOT_IN_QUOTE`, `VALUE_PARSE_DIFF`, `CONTRACT_INVALID`, `MERGE_CONFLICT`, `SCOPE_UNRESOLVED`, `LINK_REVIEW`, `MERGED_DUP`.

개발 예정:
- 실제 LLM 연결과 ONE PICK STYLE 실측
- 검토 완료 항목의 V6 업무 테이블 반영
- 추출 결과와 원문 근거 관리 → 공통 형식으로 내보낸 결과(**결과 B**)

규칙:
- `file_pipeline/` 을 import하지 않습니다. DB 연결·트랜잭션은 `src/common` 의 `PostgresDbSession` 을 사용합니다.
- 별도 하위 폴더 없이 Repository Python 파일과 SQL mapper 파일을 같은 이름으로 1:1 대응시킵니다(`document_repository.py` ↔ `document_repository.sql`).
  파일명이 namespace가 되므로(`document_repository.*`) 추가 시 다른 `.sql` 과 이름이 겹치지 않는지 확인합니다.
- DB 스키마: 테이블·시퀀스·함수는 `db_pipeline` 스키마에 둡니다(DDL 기준본: `src/card_benefit/sql/db_pipeline_schemaV6_draft.sql`).
  SQL은 `db_pipeline.card_doc` 처럼 스키마를 명시하고 `search_path` 에 기대지 않습니다.
  카드 상품은 `db_pipeline.card_product` 를 쓰며, 이전 `card_benefit.card_product` 와 `payment_card.sql` 은 사용하지 않습니다.
- 테이블 DDL은 `src/card_benefit/sql/` 에 둡니다.

상세: `src/card_benefit/docs/development_roles.md`
