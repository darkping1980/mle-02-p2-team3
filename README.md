# 하나·우리카드 혜택 GraphRAG

**카드 혜택·조건·한도·제외 규정**을 원문 PDF 근거와 연결해 LLM이 답변하도록 만든 프로젝트입니다.

하나카드·우리카드 상품설명서의 혜택, 이용 조건, 한도, 제외 규정과 원문 근거를 구조화하고, GraphRAG 검색으로 카드 혜택 질문에 근거를 연결해 답하는 팀 프로젝트입니다.

> 현재 구현은 파일 기반과 PostgreSQL 기반 처리 경로가 함께 존재합니다. 코드가 존재하는 것과 실제 운영 데이터 처리·검증이 완료된 것은 구분해 표시합니다.

## 프로젝트 배경 및 목표

카드 상품설명서는 혜택마다 실적 조건, 적용 한도, 기간, 제외 규정이 얽혀 있어 키워드 일치만으로는 정확한 답을 고르기 어렵습니다. 원문 위치와 조건 간 관계를 보존하고, 검색 결과와 답변을 근거에 대조할 수 있는 흐름을 만드는 것이 목표입니다.

## 핵심 기능 및 상태

| 기능 | 구현 범위 | 상태 메모 |
|---|---|---|
| PDF 파싱·OCR | 파일/DB 처리 경로에서 텍스트·페이지를 구성하고 OCR 경로 제공 | 지원 코드 존재. 카드별 처리 완료 여부는 자료별로 확인 필요 |
| 문서·페이지·청크 | PostgreSQL 문서 등록·조회·검증 | 구현됨. 실제 등록 현황은 데이터별 상태 확인 필요 |
| AI 혜택 추출 | LLM 응답 스키마, 후보 추출·정규화 | 구현됨. 외부 LLM 실행은 API 설정·비용이 필요 |
| 원문 근거·검증 | 추출 항목의 문서 근거와 데이터 검증 경로 | 구현 및 검증 도구 존재. 모든 항목의 승인 완료를 뜻하지 않음 |
| PostgreSQL → Neo4j | 스냅샷 변환, 적재 미리보기, 검증 | dry‑run/검증 코드 존재. 실제 운영 적재는 별도 확인 필요 |
| GraphRAG 질의 | Neo4j 검색, LangGraph 질의 단계, 근거 확인 | Streamlit 앱 구현. 배포 및 실데이터 응답은 아래 상태 참고 |
| 카드 혜택 검색·비교 | 카드·혜택·조건을 검색 맥락으로 제공 | 앱 기능 존재. 범위별 검증 상태는 검증 문서 참조 |
| 답변 검증 | 근거 ID·수치 점검 및 경고 경로 | 구현됨. 모든 질문 유형의 정답률이 검증된 것은 아님 |
| Streamlit 화면 | 카드 GraphRAG 앱 | 진입점 `db_pipeline_origin_search/streamlit_app.py` |

## 시스템 아키텍처

```mermaid
flowchart LR
  subgraph Data[데이터 처리]
    PDF[카드 상품설명서 PDF] --> Parse[파싱·OCR]
    Parse --> FilePath[파일 기반 처리]
    Parse --> DBPath[DB 기반 문서·페이지·청크 등록]
    FilePath --> ExtractA[AI 추출·검증 A]
    DBPath --> ExtractB[AI 추출·검증 B]
    ExtractB --> PG[(PostgreSQL / Supabase)]
    PG --> Check[데이터 검증]
    Check --> Sync[Neo4j 동기화]
  end
  subgraph Search[GraphRAG 검색]
    Q[사용자 질문] --> UI[Streamlit]
    UI --> LG[LangGraph]
    LG --> SearchDB[(Neo4j 검색)]
    SearchDB --> Evidence[근거 조회]
    Evidence --> Validate[답변·근거 검증]
    Validate --> Answer[응답]
  end
  Sync --> SearchDB
```

파일 기반 경로와 DB 기반 경로는 각각 독립적으로 입력 문서를 처리하는 구현입니다. DB 기반 경로는 PostgreSQL 저장 자료에서 Neo4j 변환·동기화로 이어집니다. 파일 기반 추출 결과가 DB 파이프라인의 입력이라고 가정하지 않습니다.

## 기술 스택

| 영역 | 기술 |
|---|---|
| 언어·UI | Python 3.12+, Streamlit |
| 관계형 저장소 | PostgreSQL, Supabase, psycopg, SQLAlchemy |
| 그래프 | Neo4j, Cypher |
| 검색·에이전트 | LangChain, LangGraph, pgvector |
| PDF·OCR | PyMuPDF, pypdf, 선택 OCR 의존성 |
| LLM | OpenAI 호환 LLM API (`langchain-openai`) |
| 의존성·협업 | uv, Git, GitHub |
| 임베딩 차원 | 1 536 (cosine vector) |

## 폴더 구조

```text
src/
├── common/                     # DocumentReader, OCR 엔진 등 공통 유틸
│   ├── document_reader.py
│   └── ocr_engines.py
├── card_benefit/
│   ├── payment_card/
│   │   ├── file_pipeline/                 # 파일‑기반 파싱·청크 생성
│   │   ├── db_pipeline/                   # PostgreSQL 저장·검증·Neo4j 적재
│   │   ├── db_pipeline_origin_search/     # GraphRAG 검색(LangGraph) + Streamlit UI
│   │   └── tests/                         # 단위·통합 테스트
│   ├── docs/                               # 설계·검증·가이드 문서
│   ├── sql/                                # DB 스키마·검증 SQL
│   └── data/                               # 샘플 PDF·임베딩 파일
├── recipe/                                 # 참고용 GraphRAG 레시피 (본 프로젝트와 무관)
└── ...
```

- **`file_pipeline/`**: PDF → `DocumentReader` → `doc_list`/`page_quality_list` → 청크 (옵션) → 파일‑기반 JSON 출력.
- **`db_pipeline/`**: 위 결과를 PostgreSQL에 저장, AI 추출 후 `benefit`·`rule`·`limit`·`evidence` 테이블에 매핑, 검증, 임베딩 생성, Neo4j 동기화.
- **`db_pipeline_origin_search/`**: 최종 **GraphRAG** 검색 엔진. `card_graphrag.py` 에서 LangGraph 파이프라인 정의, `streamlit_app.py` 가 UI 엔트리포인트.
- **`tests/`**: `test_card_graphrag.py` 등 자동 테스트 (CI).

## 실행 방법

저장소 루트에서 Python 3.12 이상과 uv를 준비합니다.

```powershell
uv sync --locked        # 기본 deps
```

DB 및 외부 서비스 없이 실행 가능한 테스트:

```powershell
uv run python run_offline_tests.py
```

Streamlit 앱 실행:

```powershell
uv run streamlit run src/card_benefit/payment_card/db_pipeline_origin_search/streamlit_app.py
```

실제 검색에는 Neo4j 연결 설정이 필요하며, LLM 답변 경로는 해당 API 설정과 비용이 발생할 수 있습니다. 환경변수 이름과 절차는 해당 디렉터리 README를 확인하세요.

## Streamlit 시연

[배포 앱 열기](https://mle-02-p2-team3-rzlzgdjvne.streamlit.app/)

## 진행 현황

- **구현 확인**: 파일 기반 및 DB 기반 문서 처리 코드, PostgreSQL/Neo4j 매핑·검증 도구, LangGraph 검색 앱 코드가 저장소에 있습니다.
- **검증 필요**: 카드별 문서 등록, AI 추출, 승인 상태, Neo4j 반영 및 배포 앱의 실시간 질의는 각 자료·환경별 상태 문서를 확인해야 합니다. 코드 존재만으로 전체 데이터 완료를 뜻하지 않습니다.
- **후속 개선**: 카드별 데이터 커버리지와 추출 품질을 지속 대조하고, 공통 혜택 및 조건의 원문 근거를 검증하며, 질문 유형별 답변 품질을 평가합니다.

## 팀 역할

프로젝트 문서의 담당 구분은 파일 기반 처리와 DB 기반 처리로 나뉩니다. 파일 기반 경로는 `file_pipeline/`, PostgreSQL 중심 등록·추출·검증 및 그래프 동기화는 `db_pipeline/`을 중심으로 관리합니다. 검색 앱은 `db_pipeline_origin_search/`에 있습니다. 최신 담당자 이름과 세부 범위는 [개발 역할 문서](src/card_benefit/docs/development_roles.md)를 참고하세요.

## 관련 문서

- [카드 혜택 프로젝트 안내](src/card_benefit/README.md)
- [아키텍처](src/card_benefit/docs/architecture.md)
- [디렉터리 구조](src/card_benefit/docs/directory_structure.md)
- [DB 파이프라인 상태](src/card_benefit/payment_card/db_pipeline/PROJECT_STATUS.md)
- [DB 파이프라인 안내](src/card_benefit/payment_card/db_pipeline/README.md)
- [GraphRAG 검색 앱 안내](src/card_benefit/payment_card/db_pipeline_origin_search/README.md)
- [PDF 구조화 검증](src/card_benefit/docs/card_pdf_structuring_validation.md)
- [소스 분석 위키](src/card_benefit/docs/source_wiki/README.md)
- [공통 테스트 시작 안내](docs/TEAM_START_HERE.md)

## 3. PostgreSQL 데이터 처리 & 구조화

### 주요 테이블 (스키마: `src/card_benefit/sql/`)
| 테이블 | 역할 |
|---|---|
| `card_doc` | PDF 파일 메타 (파일명, 등록 일시) |
| `card_doc_page` | 페이지 번호, 원문 텍스트, 추출 상태(`status`) 및 OCR 메타 (`ocr_engine`, `ocr_agreement`) |
| `card_doc_chunk` | 텍스트 청크(문단·문장) – 향후 임베딩 생성용 |
| `card_product` | 카드 상품 메타 (`card_id`, `card_name` 등) |
| `card_product_item` | **혜택 원장** – 각 혜택(이용조건·한도·제외 규정) 행. 주요 컬럼: `item_nm`, `item_rule_txt`, `item_limit_txt`, `item_search_txt`, `item_data`(JSON), `rule_list`(JSON), `item_cond_expr`(JSON) |
| `card_source_evidence` | **PDF Evidence** – 원문 페이지·청크와 연결. 컬럼: `card_doc_id`, `page_no`, `card_doc_chunk_id`, `evidence_id`, `snippet` 등 |
| `benefit` / `benefit_rule` / `benefit_limit` | **존재하지 않음** – 과거 모델에만 있었으며 현재 스키마에 포함되지 않음 |
| `app_log` | 스트리밍 UI·배치 작업 로그 (request_id, session_id, 단계, 토큰·비용) |

### 데이터 흐름
```mermaid
flowchart TD
    PDFInput[PDF 파일] -->|DocumentReader| PG[PostgreSQL]
    PG -->|AI 추출 (LLM) | Benefit[card_product_item]
    Benefit -->|Evidence 연결| Evidence[card_source_evidence]
    Evidence -->|임베딩 생성| Vector[pgvector]
    Vector -->|Neo4j 동기화| Neo4j[Neo4j]
```
1. **PDF 등록** – `DocumentReader` 로 텍스트·페이지·청크 추출 → `card_doc_page` / `card_doc_chunk` 삽입.
2. **AI 추출** – `extract_*` 스크립트가 LLM을 호출해 **혜택·조건·한도** 후보를 JSON 형태로 받아 `card_product_item` 에 저장 (`item_data`, `rule_list`, `item_cond_expr` 등 JSON 필드 유지).
3. **Evidence 연결** – 각 혜택/조건/한도와 원문 청크(`card_doc_page`)를 `card_source_evidence` 테이블에 매핑 (`evidence_id`, `page_no`).
4. **데이터 검증** – `validation/` 에서 숫자·단위 정규화, `ocr_disputed_numbers` 와 `item_*` 값 비교, 상태(`OK`, `UNCERTAIN`)를 `app_log`에 기록.
5. **임베딩** – `embedding_service.py` 에서 텍스트 청크를 OpenAI/본인 임베더로 벡터화, `pgvector` 컬럼에 저장 (1 536 차원).
6. **Neo4j 동기화** – `neo4j_sync.py` 가 **snapshot** 형태로 PostgreSQL → Neo4j 변환, `dry‑run` 옵션으로 사전 검증 후 실제 `EXECUTE`.

## 4. Neo4j 그래프 모델 & 동기화 (2026‑11‑06 재구축 기준)

### 노드·관계 (실제 사용) 
```mermaid
classDiagram
    class dp_card_product_item {
        string card_id
        string card_product_item_id
        string item_nm
        string item_rule_txt
        string item_limit_txt
        string item_search_txt
        string item_data   // JSON
        string rule_list   // JSON
        string item_cond_expr // JSON
        string source_json
        string key
    }
    class dp_card_source_evidence {
        string card_doc_id
        int page_no
        string card_doc_chunk_id
        string evidence_id
        string snippet
        string source_json
        string key
    }
    class dp_card_doc {}
    class dp_card_doc_page {}
    class dp_card_doc_chunk {}
    class dp_card_product {}
    class dp_card_common {}
    class dp_card_common_bnft {}
    class dp_card_extr_stg {}
    class dp_card_ai_call {}
    class dp_card_ai_run {}
    class dp_backup_card_bnft {}
    class dp_common_cd {}
    class dp_common_code_grp {}

    dp_card_product "1" --> "*" dp_card_product_item : dp_has_item
    dp_card_product_item "*" --> "1" dp_card_source_evidence : dp_supported_by
    dp_card_source_evidence "*" --> "1" dp_card_doc_chunk : dp_in_chunk
    dp_card_doc_chunk "*" --> "1" dp_card_doc_page : dp_on_page
    dp_card_doc_page "*" --> "1" dp_card_doc : dp_in_document
    dp_card_common_bnft "1" --> "1" dp_card_common : dp_belongs_to
    dp_card_common_bnft "1" --> "1" dp_card_doc : dp_has_document
    dp_card_product_doc "*" --> "1" dp_card_doc : dp_has_document
    dp_card_common_doc "*" --> "1" dp_card_doc : dp_has_document
    dp_card_ai_call "*" --> "1" dp_card_ai_run : dp_called_in_run
    dp_card_ai_call "*" --> "1" dp_card_doc_chunk : dp_called_on_chunk
    dp_card_extr_stg "*" --> "1" dp_card_product : dp_extracted_for_card
    dp_card_extr_stg "*" --> "1" dp_card_ai_call : dp_extracted_by_call
    dp_card_extr_stg "*" --> "1" dp_card_source_evidence : dp_from_extraction
```
- **노드 라벨**: `dp_card_product_item`, `dp_card_source_evidence`, `dp_card_doc`, `dp_card_doc_page`, `dp_card_doc_chunk`, `dp_card_product`, `dp_card_common`, `dp_card_common_bnft`, `dp_card_extr_stg`, `dp_card_ai_call`, `dp_card_ai_run`, `dp_backup_card_bnft`, `dp_common_cd`, `dp_common_code_grp`, 그리고 공통 라벨 `dp_node`.
- **관계 유형 (18개)**: `dp_has_item`, `dp_supported_by`, `dp_in_chunk`, `dp_on_page`, `dp_in_document`, `dp_belongs_to`, `dp_has_document`, `dp_called_in_run`, `dp_called_on_chunk`, `dp_extracted_for_card`, `dp_extracted_by_call`, `dp_from_extraction`, `dp_backup_of_card`, `dp_code_in_group`, `dp_child_of_candidate`, `dp_supported_by_extraction`, `dp_targets_document`, `dp_applies_to` (etc.).
- **벡터**: `dp_card_product_item` 및 `dp_card_source_evidence` 에는 **1 536 차원** cosine 벡터 인덱스가 존재합니다 (실제 임베딩은 `item_embedding`/`bnft_embedding` 컬럼에서 가져와 저장).
- **통계 (2026‑11‑06)**: 4 359 노드 (14 개 테이블‑별 라벨 + 공통 `dp_node`), 8 648 관계, 18 종류 관계, 1 536 차원 벡터 인덱스 정상 동작.

### 동기화 방식
- `neo4j_load_draft.py` 가 **snapshot** (PostgreSQL 전체 데이터 → Cypher `MERGE` 명령) 를 만든 뒤 `dry‑run` 으로 검증 후 실제 `EXECUTE`.
- **책임 분리**
  - **PostgreSQL**: 원문·청크·정형 데이터 저장, 트랜잭션·정합성 담당.
  - **Neo4j**: 그래프‑검색·RRF(재랭크)·벡터 근접도 담당. 검색 단계에서는 **Neo4j**만 사용 (`retrieve` 노드).

## 5. LangGraph 실행 흐름 (`card_graphrag.py`)

### 전체 파이프라인
```mermaid
flowchart LR
    A[interpret] --> B[retrieve]
    B --> C[answer]
    C --> D[finish]
```
| 노드 | 역할 | 입력 State | 핵심 로직 | 출력 State | 다음 노드 조건 |
|------|------|-------------|-----------|------------|-----------------|
| `interpret` | 질문을 LLM에게 **의도**와 **대상 혜택 ID** 추출 | `question`, `catalog` (전체 혜택 메타) | `INTERPRET_PROMPT` → LLM → `Interpretation` 모델 | `intent`, `benefit_ids`, `ambiguity` | 언제든 `retrieve` 로 이동 |
| `retrieve` | Neo4j에서 **후보 혜택**·**Evidence** 수집 | `intent`, `benefit_ids`, `search_parameters` | `create_neo4j_benefit_search` 로 **하이브리드(키워드+벡터)** 검색 → `retrieval_trace` 기록 | `retrieved_data`, `evidence`, `statements` | `answer` 로 이동 |
| `answer` | LLM에게 **검색 결과**(benefits, evidence, open_conditions) 제공해 **구조화된 답변** 생성 | `retrieved_data`, `evidence` | `ANSWER_PROMPT` → LLM → `CardAnswer` 모델 | `answer` (structured), `context` (LLM 프롬프트용) | `finish` 로 이동 |
| `finish` | 답변 검증·포맷팅, UI 반환 | `answer`, `answer_mode` (`normal`|`prototype`) | `validate_answer`(수치·근거 검증) → `answer_diagnostics` | 최종 `answer_text`, `conclusion`, `cannot_answer_reason` 등 | 종료 |

### Normal vs Prototype
- **Normal** (`answer_mode='normal'`) – `answer` 노드 이후 `validate_answer` 로 **Python 검증**(숫자·조건 일치) 수행. 검증 실패 시 경고/보정 로직 적용.
- **Prototype** (`answer_mode='prototype'`) – `validate_answer` 를 **우회**하고 `answer` 결과를 그대로 반환 (평가용 실험 모드). 두 모드는 동일한 `interpret`·`retrieve` 파이프라인을 공유하지만 **후처리 단계**만 다릅니다.

## 6. 50문항 평가 결과

| Mode | Correct / Total | 정확도 |
|------|----------------|-------|
| **Normal** | 33 / 49 | 67.35% |
| **Prototype** | 36 / 49 | 73.47% |
| **전체** | 69 / 98 | 70.41% |

- **검증 대상**: 50문항 중 49개는 `VERIFIED`, 1개는 `JUDGMENT_HOLD`.
- **주요 오류** (공통):
  - **숫자·한도 검증** 부족 → Normal 모드에서 일부 오답 발생.
  - **조건·제외 규정 해석** 오류 – 표현 다형성 때문에 LLM이 오해.
  - **Evidence 매핑** 실패 – 페이지 번호 누락 시 근거 부족 오류.
- **Prototype** 성능 향상은 **검증 단계 생략**으로 인해 발생, 실제 서비스에서는 `Normal` 모드 사용을 권장.
- 상세 결과 및 분석은 `src/card_benefit/docs/evaluation/` 아래 JSON 및 Notion 페이지에 기록되어 있습니다.

## 7. 실행 로그 & 근거 추적

| 흐름 | 로그 저장 위치 | 내용 |
|------|----------------|------|
| **Streamlit UI** | `app_log` (PostgreSQL) | `request_id`, `session_id`, 단계(`interpret`, `retrieve`, `answer`, `finish`), LLM 토큰·비용, 경고·오류 |
| **Neo4j 쿼리** | `app_log.statements` | 실행된 Cypher 식별자, 파라미터, 성공/실패 |
| **PDF Evidence** | `evidence` 테이블 | `evidence_id`, `page_no`, `snippet`, `benefit_ids` |
| **LLM 추적** | `CardState.llm_calls` | 모델명, 입력·출력 토큰, 비용 (USD) |
| **검증** | `CardState.answer_diagnostics` | `validate_answer` 결과, 숫자·조건 일치율, 경고 리스트 |

> 아직 구현되지 않은 **실시간 비용 대시보드** 등은 향후 개선 과제에 포함됩니다.

## 8. 프로젝트 디렉터리 구조

```text
src/
├── common/                     # DocumentReader, OCR 엔진 등 공통 유틸
│   ├── document_reader.py
│   └── ocr_engines.py
├── card_benefit/
│   ├── payment_card/
│   │   ├── file_pipeline/                 # 파일‑기반 파싱·청크 생성
│   │   ├── db_pipeline/                   # PostgreSQL 저장·검증·Neo4j 동기화
│   │   ├── db_pipeline_origin_search/     # GraphRAG 검색(LangGraph) + Streamlit UI
│   │   └── tests/                         # 자동 테스트 (CI)
│   ├── docs/                               # 설계·검증·가이드 문서
│   ├── sql/                                # DB 스키마·검증 SQL
│   └── data/                               # 샘플 PDF·임베딩 파일
├── recipe/                                 # 참고용 GraphRAG 레시피 (본 프로젝트와 무관)
└── ...
```
- **`file_pipeline/`**: PDF → `DocumentReader` → `doc_list`/`page_quality_list` → 청크 (옵션) → 파일‑기반 JSON 출력.
- **`db_pipeline/`**: 위 결과를 PostgreSQL에 저장, AI 추출 후 `card_product_item`·`card_source_evidence` 등 테이블에 매핑, 검증, 임베딩 생성, Neo4j 동기화.
- **`db_pipeline_origin_search/`**: 최종 **GraphRAG** 검색 엔진. `card_graphrag.py` 에서 LangGraph 파이프라인 정의, `streamlit_app.py` 가 UI 엔트리포인트.
- **`tests/`**: `test_card_graphrag.py` 등 자동 테스트 (CI).

## 9. 설치·실행·배포

### Prerequisites
- **Python 3.12+**, **uv** (`pip install uv`).
- **PostgreSQL** (local or Supabase) + **Neo4j**(≥5) 인스턴스.
- **OpenAI API 키** (`OPENAI_API_KEY`).
- **OCR 의존성** (optional):
  - Windows OCR: 기본 탑재, 별도 설치 없음.
  - RapidOCR: `uv sync --group ocr` 후 `RAPIDOCR_MODEL_DIR` 환경변수에 모델 파일(`*.onnx`)을 배치.

### 환경 변수 (예시)
```
OPENAI_API_KEY=sk-***
POSTGRES_URL=postgresql://user:pwd@host/db
POSTGRES_PASSWORD=***
NEO4J_URI=bolt://host:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=***
RAPIDOCR_MODEL_DIR=C:\path\to\rapidocr_models   # Windows only when using RapidOCR
CARD_SEARCH_MODEL=gpt-6-luna
```
> **키와 비밀번호는 README에 절대 포함하지 않아요.**

### 의존성 설치
```powershell
# 프로젝트 루트에서
uv sync --locked        # 기본 deps
uv sync --group ocr     # OCR 의존성 (Windows OCR은 별도 패키지 없이 동작)
```

### 로컬 실행
```powershell
# 1️⃣ PostgreSQL/Neo4j 연결이 준비됐다고 가정
uv run streamlit run src/card_benefit/payment_card/db_pipeline_origin_search/streamlit_app.py
```

### 테스트
```powershell
uv run pytest src/card_benefit/payment_card/tests
```

### 평가 스크립트
```powershell
uv run python src/card_benefit/payment_card/tests/evaluation_runner.py   # 연관 JSON 결과 출력
```
*API 사용량·비용은 실제 LLM 호출 시 발생하니 사전 확인 필요.*

### 배포 (Streamlit Cloud)
- 현재 배포된 앱: **[https://mle-02-p2-team3-rzlzgdjvne.streamlit.app/](https://mle-02-p2-team3-rzlzgdjvne.streamlit.app/)**
- 배포 시 `requirements.txt` 은 `src/card_benefit/payment_card/db_pipeline_origin_search/requirements.txt` 를 사용합니다.

## 10. 알려진 한계 & 개선 과제
- **OCR 적용 범위**: 현재 `DocumentReader` 에 `ocr_engine` 를 명시적으로 전달해야만 OCR 실행. 자동 적용 로직이 없습니다.
- **증거 매핑 정확도**: 숫자 교차 검증(`ocr_disputed_numbers`)은 현재 **경고** 수준이며 자동 교정은 하지 않습니다.
- **검색 파라미터 튜닝**: 하이브리드 검색 RRF 가중치가 고정되어 있어 카드별 특성에 맞는 파라미터 조정이 필요합니다.
- **실시간 비용 모니터링**: `app_log.llm_calls` 에는 토큰·비용이 기록되지만 UI 대시보드는 아직 구현되지 않았습니다.
- **Prototype 모드**: 평가용으로만 유지, 프로덕션에서는 `normal` 모드 사용을 권장합니다.

---

*이 README는 현재 코드베이스(`src/` 이하)와 검증 기록을 기반으로 작성되었습니다. 최신 변경 사항이 반영되지 않았다면 `git pull` 후 다시 검토해 주세요.*