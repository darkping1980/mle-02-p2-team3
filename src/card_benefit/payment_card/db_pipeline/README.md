# db_pipeline — PostgreSQL 중심 처리 방식 (담당: 김병주)

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

개발 예정:
- PostgreSQL 데이터 기반 AI 호출·추출 → 추출 데이터 저장
- SQL 기반 정제·검증 (중복·무결성·정합성)
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
