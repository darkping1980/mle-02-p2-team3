# 하나·우리카드 혜택 GraphRAG

**카드 혜택·조건·한도·제외 규정**을 원문 PDF 근거와 연결해 LLM이 답변하도록 만든 프로젝트입니다.

---

## 1. 프로젝트 소개

- **배경**: 카드 상품설명서는 혜택·조건·한도가 복잡하게 얽혀 있어 단순 키워드 검색으로는 정확한 답변을 얻기 어렵습니다. 원문 PDF와 구조화된 데이터(PostgreSQL)·그래프(Neo4j)를 모두 보존해 **근거 기반 검색·답변**을 제공하는 것이 목표였습니다.
- **대상 카드**: 하나카드·우리카드(실제 PDF 자료는 `src/card_benefit/data/`에 포함). 각 카드별 PDF에는 혜택, 이용조건, 한도, 제외 규정이 포함됩니다.
- **핵심 차별점**: 일반 키워드 검색이 아닌 **GraphRAG**(Neo4j + 벡터‑키워드 하이브리드) 검색으로, **PDF Evidence**(원문 페이지)와 **정형화된 혜택 메타데이터**를 동시에 활용합니다.
- **기술 스택**: Python 3.12+, Streamlit UI, PostgreSQL, Neo4j, LangChain/ LangGraph, pgvector, OpenAI‑compatible LLM, OCR(Windows OCR / RapidOCR / Cross‑Check).
- **구현 현황**
  - PDF 파싱·OCR (파일·DB 파이프라인) ✅
  - PostgreSQL에 문서·청크·AI 추출 결과 저장 ✅
  - Neo4j 그래프 동기화 (snapshot, dry‑run) ✅
  - LangGraph 기반 GraphRAG 검색·답변 흐름 ✅
  - 평가용 **Prototype** 모드 (실험) ✅
  - 실서비스 Streamlit 배포 ([앱 링크](https://mle-02-p2-team3-rzlzgdajdysf7nijchzvne.streamlit.app/)) ✅

---

## 2. PDF 파싱 & OCR

### 핵심 엔진
| 엔진 | 구현 파일 | 설명 |
|------|----------|------|
| **PyMuPDF** | `src/common/document_reader.py` ( `_read_mupdf_pages` ) | 페이지당 텍스트와 **시각 요소 여부**(이미지·그래픽) 추출.  | 
| **pypdf** | `src/common/document_reader.py` (fallback) | `extract_text()` 로 텍스트 추출. PyMuPDF가 실패하거나 **GARBLED**/`OCR_REQUIRED` 페이지에 대해 보조용. |
| **Windows OCR** | `src/common/ocr_engines.py` → `WindowsOcrEngine` | Windows 10+ 내장 OCR, `winrt` API 사용. OS‑전용, 별도 의존성 없음. |
| **RapidOCR** | `src/common/ocr_engines.py` → `RapidOcrEngine` | ONNX 기반 한국어 OCR, `uv sync --group ocr` 로 설치. 모델 파일은 환경변수 `RAPIDOCR_MODEL_DIR` 에 위치. |
| **Cross‑Check** | `src/common/ocr_engines.py` → `CrossCheckOcrEngine` | 1차 엔진 결과와 2차 엔진 결과를 비교해 **숫자 불일치**를 검출하고 `disputed_numbers` 를 반환. |

### 파싱 흐름 (Mermaid)
```mermaid
flowchart LR
    PDF[PDF 파일] --> Extract[PyMuPDF 텍스트 추출]
    Extract -->|정상| PageStore[doc_list / page_quality]
    Extract -->|GARBLED/EMPTY| Fallback[pypdf 재추출]
    Fallback --> PageStore
    PageStore -->|품질 < OCR_TARGET_STATUS| OCR[OCR 엔진 선택]
    OCR -->|대체| PageStore
    PageStore -->|완료| Chunk[청크 생성 (optional)]
```

#### 상세 단계
1. **PDF 기본 텍스트 추출** (`_read_mupdf_pages`) – 페이지 텍스트와 시각 요소(`has_visual`) 반환.
2. **품질 평가** (`measure_pdf_text`) – `OK`, `SUSPECT`, `GARBLED`, `OCR_REQUIRED`, `EMPTY` 중 하나.
3. **Fallback** – `GARBLED`, `OCR_REQUIRED`, `EMPTY` 페이지는 `pypdf` 로 재시도. 더 좋은 텍스트가 있으면 교체.
4. **OCR 실행 조건** – `ocr_engine` 가 지정됐고, 페이지 `status` 가 `SUSPECT`, `GARBLED`, `OCR_REQUIRED` 중 하나이면 OCR 수행.
5. **OCR 결과 검증** – `measure_ocr_agreement` 로 텍스트 레이어와 OCR 결과 어절 일치율 계산. `OCR_MIN_AGREEMENT (0.8)` 이상이고, `OCR_MIN_SUSPECT_RATIO (0.05)` 조건을 만족하면 OCR 결과 **채택** (`ocr_replaced=True`).
6. **숫자 교차 검증** – `extract_numbers` 로 원본·OCR 텍스트의 숫자를 추출, 차이(`disputed_numbers`)를 기록.
7. **페이지·청크 정보 보존** – `doc_list` 에 `{page_no, text}`, `page_quality_list` 에 `{page_no, extractor, status, ...}` 저장. 페이지 번호와 추출 엔진 버전이 함께 기록되어 **증거 추적**이 가능.

> **주의**: OCR이 **구현**돼 있지만, 실제 PDF 등록 시 `DocumentReader(..., ocr_engine=...)` 로 전달하지 않으면 OCR이 실행되지 않습니다. 즉, **OCR 지원**이 존재하지만 모든 PDF에 자동 적용되지는 않음.

---

## 3. PostgreSQL 데이터 처리 & 구조화

### 주요 테이블 (스키마: `src/card_benefit/sql/`)
| 테이블 | 역할 |
|--------|------|
| `card_doc` | PDF 파일 메타 (파일명, 등록 일시) |
| `card_doc_page` | 페이지 번호, 원문 텍스트, 추출 상태(`status`) 및 OCR 메타 (`ocr_engine`, `ocr_agreement`) |
| `card_doc_chunk` | 텍스트 청크(문단·문장) – 향후 임베딩 생성용 |
| `benefit` | 구조화된 **혜택** 레코드 (id, name, description) |
| `benefit_rule` | 혜택 내 **조건·규칙** (텍스트, numeric extraction) |
| `benefit_limit` | 혜택 **한도**(횟수·금액·비율) |
| `evidence` | 원문 PDF 페이지와 청크를 연결 (`evidence_id`, `card_doc_page_id`, `benefit_id`) |
| `app_log` | 스트리밍 UI·배치 작업 로그 (request_id, session_id, 단계, 토큰·비용) |

### 데이터 흐름
```mermaid
flowchart TD
    PDFInput[PDF 파일] -->|DocumentReader| PG[PostgreSQL]
    PG -->|AI 추출 (LLM) | Benefit[benefit / rule / limit]
    Benefit -->|Evidence 연결| Evidence[evidence]
    Evidence -->|임베딩 생성| Vector[pgvector]
    Vector -->|Neo4j 동기화| Neo4j[Neo4j]
```

1. **PDF 등록** (`src/card_benefit/payment_card/file_pipeline/` 혹은 `db_pipeline/`의 `register_service`) – `DocumentReader` 로 텍스트·페이지·청크 추출 → `card_doc_page`/`card_doc_chunk` 삽입.
2. **AI 추출** – `src/card_benefit/payment_card/db_pipeline/extract_*` 스크립트가 LLM을 호출해 **혜택·조건·한도** 후보를 JSON 형태로 받음 → `benefit`, `benefit_rule`, `benefit_limit` 테이블에 저장.
3. **PDF Evidence 연결** – 각 혜택/조건/한도와 원문 청크(`card_doc_page`)를 `evidence` 테이블에 매핑 (`benefit_id`, `page_no`).
4. **데이터 검증** – `src/card_benefit/payment_card/db_pipeline/validation/` 에서 숫자·단위 정규화, `ocr_disputed_numbers` 와 `benefit` 값 비교, 상태(`OK`, `UNCERTAIN`)를 `app_log` 에 기록.
5. **임베딩** – `src/card_benefit/payment_card/db_pipeline/embedding_service.py` 에서 텍스트 청크를 OpenAI/본인 임베더로 벡터화, `pgvector` 컬럼에 저장.
6. **Neo4j 동기화** – `src/card_benefit/payment_card/db_pipeline/neo4j_sync.py` 가 **snapshot** 형태로 PostgreSQL → Neo4j 변환, `dry‑run` 옵션으로 사전 검증.

---

## 4. Neo4j 그래프 모델 & 동기화

### 노드·관계 (실제 사용) 
```mermaid
classDiagram
    class Benefit {
        string benefit_id
        string name
        string description
    }
    class Rule {
        string rule_id
        string text
    }
    class Limit {
        string limit_id
        string text
    }
    class Evidence {
        string evidence_id
        int page_no
        string snippet
    }
    Benefit "1" --> "*" Rule : has_rule
    Benefit "1" --> "*" Limit : has_limit
    Benefit "1" --> "*" Evidence : has_evidence
    Evidence "*" --> "1" Page : from_page
```
- **Benefit**: 카드 혜택 ID, 이름, 요약.
- **Rule** / **Limit**: 각각 **조건·규칙**·**한도** 텍스트.
- **Evidence**: 원문 PDF 페이지(`page_no`)와 청크(`snippet`). `evidence_id` 로 `Benefit` 과 연결.
- **Vector Index**: `Evidence` 에 `embedding` (float[768]) 속성을 가진 `VECTOR` 인덱스 (`btree`‑compatible) 가 생성되어 **벡터 검색** 지원.

### 동기화 방식
- `create_neo4j_benefit_search` → `Neo4jBenefitSearch` (키워드+벡터 하이브리드). 
- `db_pipeline/neo4j_sync.py` 은 **snapshot** (PostgreSQL 전체 데이터 → Cypher `MERGE` 명령) 을 만든 뒤 `dry‑run` 로 검증 후 실제 `EXECUTE`.
- **책임 분리**
  - **PostgreSQL**: 원문·청크·정형 데이터 저장, 트랜잭션·정합성 담당.
  - **Neo4j**: 그래프‑검색·RRF(재랭크)·벡터 근접도 담당. 검색 단계에서는 **Neo4j**만 사용 (`retrieve` 노드).

---

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

### Normal vs Prototype (실행 시점)
- **Normal** (`answer_mode='normal'`) – `answer` 노드 이후 `validate_answer` 로 **Python 검증**(숫자·조건 일치) 수행. 검증 실패 시 경고/보정 로직 적용.
- **Prototype** (`answer_mode='prototype'`) – `validate_answer` 를 **우회**하고 `answer` 결과를 그대로 반환 (평가용 실험 모드). 두 모드는 동일한 `interpret`·`retrieve` 파이프라인을 공유하지만 **후처리 단계**만 다릅니다.

---

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
- **Prototype 성능 향상**은 **검증 단계 생략**으로 인한 것으로, 실제 서비스에서는 `Normal`이 권장됩니다.
- 상세 결과 및 분석은 `src/card_benefit/docs/evaluation/` 아래 JSON 및 Notion 페이지에 기록되어 있습니다.

---

## 7. 실행 로그 & 근거 추적

| 흐름 | 로그 저장 위치 | 내용 |
|------|----------------|------|
| **Streamlit UI** | `app_log` (PostgreSQL) | `request_id`, `session_id`, 단계(`interpret`, `retrieve`, `answer`, `finish`), LLM 토큰·비용, 경고·오류 |
| **Neo4j 쿼리** | `app_log.statements` | 실행된 Cypher 식별자, 파라미터, 성공/실패 |
| **PDF Evidence** | `evidence` 테이블 | `evidence_id`, `page_no`, `snippet`, `benefit_ids` |
| **LLM 추적** | `CardState.llm_calls` | 모델명, 입력·출력 토큰, 비용 (USD) |
| **검증** | `CardState.answer_diagnostics` | `validate_answer` 결과, 숫자·조건 일치율, 경고 리스트 |

> 아직 구현되지 않은 **실시간 비용 대시보드** 등은 향후 개선 과제에 포함됩니다.

---

## 8. 프로젝트 디렉터리 구조

```
src/
├── common/                     # DocumentReader, OCR 엔진 등 공통 유틸
│   ├── document_reader.py
│   └── ocr_engines.py
├── card_benefit/
│   ├── payment_card/
│   │   ├── file_pipeline/                 # 파일‑기반 파싱·청크 생성
│   │   ├── db_pipeline/                   # PostgreSQL 저장·검증·Neo4j 동기화
│   │   ├── db_pipeline_origin_search/     # GraphRAG 검색(LangGraph) + Streamlit UI
│   │   └── tests/                         # 단위·통합 테스트
│   ├── docs/                               # 설계·평가·가이드 문서
│   ├── sql/                                # DB 스키마·검증 SQL
│   └── data/                               # 샘플 PDF·임베딩 파일
├── recipe/                                 # 참고용 GraphRAG 레시피 (본 프로젝트와 무관)
└── ...
```

- **`file_pipeline/`**: PDF → `DocumentReader` → `doc_list`/`page_quality_list` → 청크 (옵션) → 파일‑기반 JSON 출력.
- **`db_pipeline/`**: 위 결과를 PostgreSQL에 저장, AI 추출 후 `benefit`·`rule`·`limit`·`evidence` 테이블에 매핑, 검증, 임베딩 생성, Neo4j 동기화.
- **`db_pipeline_origin_search/`**: 최종 **GraphRAG** 검색 엔진. `card_graphrag.py` 에서 LangGraph 파이프라인 정의, `streamlit_app.py` 가 UI 엔트리포인트.
- **`tests/`**: `test_card_graphrag.py` 등 자동 테스트 (CI). 

---

## 9. 설치·실행·배포

### Prerequisites
- **Python 3.12+**, **uv** (`pip install uv`).
- **PostgreSQL** (local or Supabase) + **Neo4j**(>=5) 인스턴스.
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
> **키와 비밀번호**는 README에 절대 포함하지 마세요.

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
- 현재 배포된 앱: **[https://mle-02-p2-team3-rzlzgdajdysf7nijchzvne.streamlit.app/](https://mle-02-p2-team3-rzlzgdajdysf7nijchzvne.streamlit.app/)**
- 배포 시 `requirements.txt` 은 `src/card_benefit/payment_card/db_pipeline_origin_search/requirements.txt` 를 사용합니다.

---

## 10. 알려진 한계 & 개선 과제
- **OCR 적용 범위**: 현재 `DocumentReader` 에 `ocr_engine` 를 명시적으로 전달해야만 OCR 실행. 자동 적용 로직이 없습니다.
- **증거 매핑 정확도**: 숫자 교차 검증(`ocr_disputed_numbers`)은 현재 **경고** 수준이며 자동 교정은 하지 않습니다.
- **검색 파라미터 튜닝**: 하이브리드 검색 RRF 가중치가 고정되어 있어 카드별 특성에 맞는 파라미터 조정이 필요합니다.
- **실시간 비용 모니터링**: `app_log.llm_calls` 에는 토큰·비용이 기록되지만 UI 대시보드는 아직 구현되지 않았습니다.
- **Prototype 모드**: 평가용으로만 유지, 프로덕션에서는 `normal` 모드 사용을 권장합니다.

---

*이 README는 현재 코드베이스(`src/` 이하)와 검증 기록을 기반으로 작성되었습니다. 최신 변경 사항이 반영되지 않았다면 `git pull` 후 다시 검토해 주세요.*
