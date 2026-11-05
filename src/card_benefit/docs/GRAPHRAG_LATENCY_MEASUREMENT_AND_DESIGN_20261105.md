# GraphRAG 답변 지연 실측(LLM 포함)과 성능 개선 설계 (2026-11-05)

> 선행 문서: [GRAPHRAG_LATENCY_ANALYSIS_20261105.md](GRAPHRAG_LATENCY_ANALYSIS_20261105.md) (원인 분석, LLM 제외 측정)
> 이번 범위: 승인된 실제 API 1회 측정 + 개선 설계. **성능 개선 소스 수정, 커밋·푸시는 하지 않았다.**

## 0. 요약

- 실제 질문 1건이 **답변 화면 출력 직전까지 21.74 s** 걸렸다(웜 상태).
  - DB 대기: **11.12 s (51%)** — PostgreSQL 6.41 s, Neo4j 4.71 s
  - 외부 API: **9.80 s (45%)** — LLM 2회 7.85 s, 임베딩 1.96 s
  - app_log 저장: 0.77 s (3.6%)
  - Python·LangGraph: 0.04 s
- 화면 렌더링(`show_outcome`)은 서버 기준 +30~60 ms로 무시할 수준이다.
- 같은 SQL·Cypher를 그대로 둔 채 실행 방식만 바꾸는 개선만으로 **DB 대기를 11.1 s에서 약 3 s로**, 전체를 **약 21.7 s에서 약 12~13 s로** 줄일 수 있다(측정 단가 기반 추정).
- 개선 후에는 LLM·임베딩이 남은 시간의 대부분(약 75%)을 차지한다.
- Neo4j는 **트랜잭션 통합**(같은 Cypher, 결과 동일)과 **단일 문장 통합**(실제 왕복 감소, Cypher 변경)의 효과를 따로 측정했다(§3).

---

## 1. 실측 조건

| 항목 | 내용 |
|---|---|
| 질문 | "ONE PICK STYLE 카드의 대중교통 혜택은?" (C 모드, 선행 문서와 동일) |
| 실행 방식 | `streamlit_app.py` 제출 분기(`:407-445`)와 같은 순서로 실행: `request_pipeline` → `capture_request_queries` → `CardGraphRAG.run` → `cleanup` → `persist_app_logs` |
| 실제 API | **1회 요청만 실행.** 채팅 LLM 2회, 임베딩 1회 (가드로 초과 호출 시 즉시 중단, 실제 카운트 `chat=2, embed=1`) |
| 웜업 | API 없이 stub으로 1회 먼저 실행해 연결 pool을 준비(일반적인 2번째 이후 질문 조건). 첫 질문 cold 수치는 선행 문서 §3-5 참조 |
| app_log 저장 | 실제 `persist_app_logs` 코드를 그대로 실행하되, pool의 COMMIT 직전에 ROLLBACK해 **행을 남기지 않음**(INSERT·ROLLBACK 왕복 수는 실제 COMMIT과 같다). id 시퀀스 값 1개는 소비됐을 수 있다 |
| 계측 | 측정 프로세스 안에서만 메서드를 감쌈. 소스 파일 무수정 |
| 측정 위치 | 개발 PC. PG(Supabase eu-west-1) TCP RTT 254~282 ms, Neo4j Aura TCP RTT 89~98 ms |
| 동시 작업 | Codex의 Neo4j 관계 Edge 작업과 겹쳐 진행. 측정에 쓴 쿼리는 `dp_related_to`를 읽지 않으며, Codex 변경 파일은 읽기만 했다 |

### 결과 정확도 확인 (같은 질문의 기존 결과와 비교)

- 상태 `ANSWERED`, 경로 `interpret → retrieve → answer → finish`, intent `BENEFIT_DETAIL`, 대상 혜택 "ONE MORE 대중교통 캐시백"(기존 app_log와 같음)
- PDF 근거 13건. answer_source `llm`
- points 3개: RAW_MATCH 2, NOT_CHECKED 1(제외 문장, 값 없음)
- 답변: "ONE MORE 대중교통 캐시백은 버스와 지하철 이용금액의 5%를 월 최대 1천원까지 돌려드립니다. … 시외버스·고속버스와 KTX·SRT·ITX는 제외됩니다."
- 캡처된 쿼리 이벤트 21건 — app_log 기존 기록과 같은 순서·건수

---

## 2. 실측 결과

### 2-1. 단계별 시간 (질문 1건, 실제 API 포함)

| 단계 | 호출 횟수 | 총 소요 시간 | 전체 대비 비율 |
|---|---:|---:|---:|
| PostgreSQL | 8 | 6,412 ms | 29.5% |
| Neo4j | 13 | 4,711 ms | 21.7% |
| LLM — interpret | 1 | 2,437 ms | 11.2% |
| LLM — answer | 1 | 5,409 ms | 24.9% |
| 임베딩 | 1 | 1,958 ms | 9.0% |
| LangGraph·Python 처리 | — | 42 ms | 0.2% |
| app_log 저장 (`persist_app_logs`) | 1 | 772 ms | 3.6% |
| **전체 (제출 → `show_outcome` 직전)** | | **21,741 ms** | **100%** |
| (참고) `show_outcome` 서버 렌더링 | — | +30~60 ms | — |

- 합계 검증: 6,412 + 4,711 + 2,437 + 5,409 + 1,958 + 42 + 772 = 21,741 ms.
- Python 42 ms의 내역: `request_pipeline`(PostgresDbSession·mapper 재파싱) 28 ms + 노드 내부 처리 14 ms.
- 렌더링: Streamlit `AppTest`로 측정했다. 결과가 없을 때 페이지 실행 298~318 ms, 일반 화면 299~332 ms, 개발자 모드 316~378 ms. 차이만 `show_outcome` 비용으로 봤다. 브라우저 표시 시간은 측정하지 않았다.
- **사용자가 체감하는 총시간(서버 기준) ≈ 21.8 s.**

### 2-2. LLM·임베딩 호출 상세

| 호출 | 모델 | 소요 시간 | 입력 토큰 | 캐시 적중 | 출력 토큰 | 추론 토큰 | 추정 비용(USD) |
|---|---|---:|---:|---:|---:|---:|---:|
| interpret (질문 해석) | gpt-6-luna | 2,437 ms | 1,605 | 0 | 38 | 0 | 0.000180 |
| answer (답변 생성) | gpt-6-luna | 5,409 ms | 5,556 | 0 | 451 | 0 | 0.000781 |
| 임베딩 | text-embedding-3-small (1536차원) | 1,958 ms | 20 | — | — | — | ≈ 0.0000004 |
| **합계** | | **9,804 ms** | | | | | **≈ 0.00096** |

- interpret는 출력이 38 토큰뿐인데 2.4 s, 임베딩은 20 토큰인데 2.0 s가 걸렸다. 두 호출 모두 이 프로세스에서 각 엔드포인트로 보낸 **첫 HTTPS 요청이라 연결 수립 시간이 포함됐을 가능성**이 있다(추정). 웜 상태 값은 승인 범위(1회) 때문에 측정하지 않았다.
- 프롬프트 캐시 적중은 0이다. OpenAI 프롬프트 캐시는 1,024 토큰 이상의 같은 접두부에서 동작한다. 질문 해석·답변 프롬프트는 앞부분이 고정 규칙이므로 연속 질문에서는 적중이 생길 수 있다(추정, 미측정).

### 2-3. 노드별 시간

| 노드 | 시간 | 내역 |
|---|---:|---|
| interpret | 11,658 ms | Neo4j 8건 2,383 + PG 6건 4,875 + 임베딩 1,958 + LLM 2,437 (후보 검색 `candidate_search.elapsed_ms` = 8,295) |
| retrieve | 3,095 ms | Neo4j 5건 2,328 (그중 card.evidence 1,164) + PG 1건 766 |
| answer | 6,184 ms | PG 1건 771 + LLM 5,409 |
| finish | 0.2 ms | |

### 2-4. 문장별 시간 (실측 1회)

| 순서 | 엔진 | 문장 | ms |
|---:|---|---|---:|
| 1-3 | Neo4j | card.catalog / item_catalog / common_catalog | 367 / 270 / 287 |
| 4-5 | PG | keyword_card_bnft / keyword_common_bnft | 776 / 1,031 |
| 6-9 | Neo4j | card.list ×4 (ONE, PICK, STYLE, 대중교통) | 274 / 268 / 266 / 268 |
| 10 | PG | select_last_embedding_run | 764 |
| — | OpenAI | 임베딩 | 1,958 |
| 11-12 | PG | search_card_bnft / search_common_bnft | 770 / 768 |
| 13 | PG | brand_bnft_compare | 767 |
| 14 | Neo4j | card.relations | 383 |
| — | OpenAI | LLM interpret | 2,437 |
| 15-19 | Neo4j | card.context / rules / conditions / limits / evidence | 276 / 266 / 357 / 265 / **1,164** |
| 20 | PG | select_card_bnft_detail | 766 |
| 21 | PG | select_card_terms | 771 |
| — | OpenAI | LLM answer | 5,409 |
| — | PG | app_log INSERT (+ROLLBACK) | 772 |

`card.evidence`는 21행 191 KB를 돌려준다. 그중 `chunk` 72 KB, `page` 70 KB, `document` 23 KB(합 166 KB, 87%)는 GraphRAG 로직이 읽지 않는다. 확인한 바로는 `collect_evidence`, `fee_answer`가 `link`, `evidence`, `rule_key`만 사용하고, 나머지는 개발자 모드의 "Neo4j 조회 원본" 표시에만 쓰인다. 다른 상세 쿼리가 약 265 ms인데 이 쿼리만 1.16 s인 것은 전송량 때문으로 본다(추정).

---

## 3. 개선 방식별 실측 비교 (읽기 전용 프로토타입, API 미사용)

같은 데이터에 대해 실행 방식만 바꿔 측정 스크립트 안에서 비교했다. 소스는 바꾸지 않았다.

### 3-1. PostgreSQL — BEGIN/COMMIT 제거

| 방식 (같은 SQL 8건) | 시간 | 현재 대비 |
|---|---:|---:|
| 현재: SQL마다 pool 대여 + BEGIN·SELECT·COMMIT | 6,412 ms | — |
| 트랜잭션 1개로 묶기 (BEGIN + 8 SELECT + COMMIT) | 2,628~2,832 ms | −3.6 s |
| **autocommit 읽기 (SELECT만 왕복)** | **2,083 ms** (건당 256~268) | **−4.3 s (−68%)** |
| (참고) pipeline 모드: 독립 SELECT 5건을 왕복 1회로 | 267~524 ms (5건) | 5건 기준 −3.6 s |

pipeline 측정 대상 5건은 keyword_card_bnft, keyword_common_bnft, select_last_embedding_run, search_card_bnft, search_common_bnft이고, 행 수는 34/82/1/9/6건으로 기존 결과와 같다.

### 3-2. Neo4j — 트랜잭션 통합 vs 실제 왕복 감소

| 대상 | 현재 (문장마다 트랜잭션) | 트랜잭션 1개로 통합 (Cypher 그대로) | 단일 문장 (Cypher 통합) | 결과 동일성 |
|---|---:|---:|---:|---|
| `get_detail` 5건 (혜택 1개) | 1,946~2,294 ms | 1,077~1,094 ms (−45%) | 699~832 ms (−60%) | 모두 동일 (context 1, rules 1, conditions 7, limits 1, evidence 21) |
| `card.list` ×4 | 1,069~1,091 ms | 543~546 ms (−50%) | **289~290 ms (−73%)** (`UNWIND $keywords`) | (낱말, key) 쌍 12개 동일 |
| 카탈로그 3건 | 827~865 ms | 461~559 ms (−40%) | (미측정) | — |
| 하한: `RETURN 1` 1건 | — | 264~277 ms | — | — |

해석:

- Neo4j TCP RTT는 약 90 ms인데, 관리형 트랜잭션 1건의 하한이 약 265 ms다. 문장마다 BEGIN·RUN/PULL·COMMIT으로 **약 3회 왕복**한다는 뜻이다.
- **트랜잭션 통합**은 문장마다 붙는 BEGIN·COMMIT을 없앤다. 그래도 문장마다 RUN/PULL 왕복은 남는다. 가벼운 쿼리는 1건당 +약 90 ms, 결과가 큰 쿼리는 +약 200 ms다. Cypher와 결과가 완전히 같아 **위험이 가장 낮다.**
- **단일 문장 통합**은 RUN 자체를 1회로 줄여 **실제 왕복 수가 줄어든다.** 대신 Cypher를 새로 작성해야 하고 결과 구조가 바뀌므로 매핑 코드와 동일성 검증이 필요하다.
- 세션 재사용은 효과가 없다(선행 측정에서 세션 생성 비용은 무시할 수준).

---

## 4. 개선 설계 (우선순위순, 수정 대상 함수·예상 효과)

예상 효과는 §2·§3 실측 단가로 계산한 추정치다(혜택 1개 질문, 웜 상태 기준).

### P1. PostgreSQL 읽기 전용 조회의 BEGIN/COMMIT 왕복 제거

**수정 대상**

| 파일 · 함수 | 변경 내용 |
|---|---|
| `common/database_manager.py` `DatabaseManager.__init__` / `_get_pool` (`:146-190`) | 생성 옵션 `autocommit`·`read_only`(기본값 False, 기존 동작 유지) 추가 → `ConnectionPool(kwargs={"row_factory": …, "autocommit": True}, …)`. 읽기 전용 pool은 `options="-c default_transaction_read_only=on"`으로 쓰기를 DB 단에서 차단 |
| `common/postgres_db_session.py` `PostgresDbSession.transaction` (`:423`) | 읽기 전용 manager에서 호출되면 예외 발생(원자성 오해 방지) |
| `card_graphrag.create_benefit_search` (`card_graphrag.py:318`) | 검색 전용 `DatabaseManager(autocommit=True, read_only=True)`를 주입 |
| `execution_log.request_pipeline` (`execution_log.py:147`) | 기존 manager를 그대로 넘기므로 자동으로 같은 설정이 적용됨(변경 불필요) |

**효과:** PG 8건 6.41 s → 2.08 s (**−4.3 s**, 실측 프로토타입).

**2단계(선택):** `BenefitSearchService.search`(`benefit_search_service.py:132`)에서 임베딩을 받은 뒤 독립 SELECT 5건을 psycopg pipeline으로 한 번에 보낸다. 공통 세션에 `select_many(statements)`를 추가해야 한다. 효과는 5건 1.29 s(autocommit) → 약 0.27 s, 추가 −1.0 s.

**정확도 영향:** 없음. 같은 SQL·파라미터·결과다.

**부작용·주의**
- `DatabaseManager`는 등록(쓰기) 파이프라인과 같이 쓴다. **기본값을 바꾸지 말고** 검색 경로에만 옵션을 준다.
- 지금 쓰는 Supabase pooler는 5432(session 모드)다. 6543(transaction 모드)으로 바꾸면 psycopg 자동 prepare와 충돌할 수 있다.
- pipeline 방식은 오류가 나면 뒤 쿼리가 함께 실패하므로 예외 처리를 다시 설계해야 한다.

### P2. 반복 조회되는 Neo4j 카탈로그·정적 조회의 안전한 캐시

**캐시 대상 (질문과 무관하게 적재 전까지 결과가 같은 것만)**

| 대상 | 함수 | 현재 비용 |
|---|---|---:|
| card.catalog / item_catalog / common_catalog | `Neo4jSearch.list_catalog` (`neo4j_search.py:210`) | 924 ms |
| select_last_embedding_run | `BenefitSearchService._vector` (`benefit_search_service.py:244`) | 764 ms (P1 후 약 258) |
| brand_bnft_compare | `BenefitSearchService._confirmed_duplicates` (`:196`) → `CommonBenefitService.compare_brand_benefits` | 767 ms (P1 후 약 258) |

**질문에 따라 달라지는 검색 결과의 캐시 (조건부)**

- 질문 임베딩 벡터: (질문 원문, 임베딩 모델) 키. 같은 질문이면 −1.96 s.
- `get_detail(key, sections)` 결과: (key, sections, 데이터 버전) 키.
- 후보 검색 결과(`catalog_rows`): (질문, 모드, 데이터 버전) 키.
- 모두 입력이 같으면 결과가 결정적이라 안전하다. 다만 효과는 같은 질문·같은 혜택이 반복될 때만 생긴다. 같은 세션의 같은 질문은 이미 `streamlit_app.py:395`에서 재사용된다.
- **LLM 결과(해석·답변)는 캐시하지 않는다.** 출력이 매번 다를 수 있고 검증 흐름이 바뀐다.

**무효화 설계**
- 데이터 버전 키를 쓴다. 예: Neo4j 적재 실행 ID나 PG 등록 실행의 최신 시각, 최신 임베딩 실행 ID.
- 버전 확인 쿼리 1건(약 0.26 s)을 요청마다 실행하거나, TTL(예: 5분)과 개발자 모드 "캐시 비우기" 버튼을 함께 둔다.
- **Codex의 `dp_related_to` 적재처럼 그래프가 다시 적재되는 시점에는 반드시 무효화해야 한다.** 지금 카탈로그 쿼리는 `dp_related_to`를 읽지 않지만, 나중에 읽게 되면 바로 영향을 받는다.
- 캐시 위치는 `Neo4jSearch` / `BenefitSearchService` 인스턴스 안(TTL·버전 포함)을 권장한다. Streamlit뿐 아니라 `search_eval.py`도 효과를 본다.
- 반환 목록은 deepcopy하거나 읽기 전용으로 다뤄야 한다. 현재 `interpret`는 `{**row}`로 복사해 쓰지만, 호출자가 원본 행을 바꾸면 캐시가 오염된다.

**효과:** Neo4j −0.92 s, PG −0.52 s(P1 적용 후 기준) ⇒ **약 −1.4 s**.

**정확도 영향:** 무효화가 맞으면 없음. 무효화가 늦으면 질문 해석 목록과 ID 대조(환각 ID 차단)가 옛 데이터 기준이 된다. 상세 조회는 실제 DB를 읽으므로 잘못된 답 대신 NO_RESULT로 실패하는 쪽이지만, 무효화 테스트가 필수다.

### P3. Neo4j 키워드별 반복 조회와 혜택별 다중 쿼리 최소화

| 개선 | 수정 대상 | 측정 근거 | 예상 효과 |
|---|---|---|---|
| `card.list` N건 → `UNWIND $keywords` 1건. 반환 `(keyword, key)`로 지금과 같은 점수 계산 | `BenefitSearchService._keyword` (`benefit_search_service.py:211-235`)의 낱말 반복 → 새 `Neo4jSearch.list_benefits_many(terms)` + 새 named query `list_benefits_many` (**기존 `list_benefits`는 유지**) | (낱말, key) 쌍 동일, 1,076 → 290 ms | **−0.79 s** (낱말 6개 질문은 약 −1.3 s) |
| `get_detail` 5건 → 트랜잭션 1개 | `Neo4jSearch.get_detail` (`neo4j_search.py:256-284`)과 `_query` (`:186`)를 나눠 "같은 트랜잭션에서 여러 문장 실행" 헬퍼 추가. 문장별 로그(STATEMENTS ID)는 유지 | 결과 동일, 2.0~2.3 s → 1.08 s | **−0.9~1.2 s/혜택** |
| (2단계) `get_detail` → 단일 문장, 여러 혜택은 `UNWIND $keys` | 새 named query `benefit_detail_bundle`, 매핑 함수 | 결과 동일, → 0.70~0.83 s | 혜택 1개 −1.3~1.5 s, 혜택 4개 질문(현재 20건 ≈ 5.6 s 이상) → 약 1 s(추정) |
| `card.evidence` 반환 컬럼 축소: `chunk`·`page`·`document` 전체 속성 대신 필요한 값만 | `graph_questions.cypher`의 `benefit_evidence` / `item_evidence` / `common_benefit_evidence` | 191 KB 중 87% 미사용, 1,164 ms vs 일반 약 265 ms | −0.2~0.9 s (전송량 따라 변동, 추정) |
| `select_card_bnft_detail`(제외 판정 원본 대조) 혜택 N건 → `ANY(array)` 1건 | `CardGraphRAG.retrieve`의 `read_source` (`card_graphrag.py:1722-1727`), `find_exclusions`, 새 SQL | — | (N−1) × 0.26 s (P1 후) |

**유지할 것**
- 카드명 낱말(ONE·PICK·STYLE)도 `keyword_score`에 반영되므로 낱말을 빼서 쿼리 수를 줄이지 않는다. 순위가 바뀐다.
- `find_exclusions`의 PostgreSQL 원본 대조는 정확도 장치이므로 없애지 않고 묶기만 한다.
- 근거 컬럼을 줄여도 `evidence` 속성(`evidence_id`, `page_no`, `quote_txt`, `approval_status_cd`)과 `link`(`ev_subject_cd`, `ev_item_cd`, `ev_item_key`), `rule_key`는 그대로 둔다. 그래야 PDF 근거·쪽수·연회비 줄 근거가 유지된다.
- 개발자 모드 "Neo4j 조회 원본"과 `verify_view` 단계 화면에서 청크 원문이 보이지 않게 되므로, 필요하면 개발 검증 모드에서만 전체 컬럼을 조회한다.

**코드 소유 조율:** `neo4j_search.py`와 `graph_questions.cypher`는 Codex가 지금 수정 중이다(`benefit_relations` 추가, 미커밋). 이 개선은 **Codex 작업을 커밋·병합한 뒤** 시작하고, 기존 named query를 고치지 않고 새 query를 추가하는 방식으로 충돌을 줄인다.

### P4. 쿼리 통합·배치·병렬로 실제 네트워크 왕복 감소

| 구분 | 내용 | 왕복 변화 | 위험 |
|---|---|---|---|
| ① 트랜잭션 통합 (Neo4j) | `get_detail` 5건, 카탈로그 3건, `card.list` N건을 `execute_read` 1개 안에서 실행 | 문장당 약 3 RTT → 첫 문장 3 RTT + 이후 문장 1 RTT(+전송) | 낮음 (같은 Cypher) |
| ② 단일 문장 통합 (Neo4j) | `UNWIND`, `CALL () {}` 서브쿼리로 RUN 1회 | 묶음당 약 3 RTT | 중간 (Cypher 신규, 결과 동일성 검증 필요). `OPTIONAL MATCH`를 단순히 이어 붙이면 행 곱으로 결과가 부푼다. 서브쿼리 안에서 `collect` 해야 한다. 신규 문법 `CALL () {}` 사용(구 문법은 서버가 deprecated 경고) |
| ③ PG autocommit / pipeline | P1 | SELECT당 3 RTT → 1 RTT → 5건 1 RTT | 낮음 / 중간 |
| ④ 단계 내 병렬 실행 | interpret: 임베딩 API ∥ PG 문자열 검색 ∥ Neo4j 카탈로그·card.list. retrieve: 혜택별 상세 ∥ `select_card_terms`(answer에서 미리 조회) | 대기 시간이 합이 아니라 최댓값이 됨 | 중간: `REQUEST_ID`·`ACTIVE_QUERY_EVENTS` ContextVar는 `contextvars.copy_context()`로 넘겨야 app_log 수집이 유지된다. psycopg 연결·Neo4j 세션은 스레드마다 따로 빌려야 한다(pool max 5). 로그 순서가 바뀐다 |

④의 효과: P1~P3 적용 후 interpret의 DB·임베딩 구간은 대략 임베딩 1.96 s와 DB 약 1.5 s의 합이다. 병렬로 실행하면 약 2.0~2.3 s로 줄어 추가 −1.2 s 정도를 기대한다(추정).

### P5. app_log 저장이 답변 표시를 지연시키는 정도와 개선

**실측**
- `persist_app_logs` 1회 = **772 ms** (BEGIN·INSERT·ROLLBACK 3회 왕복, COMMIT도 같은 왕복 수). 전체의 3.6%다.
- `streamlit_app.py:430-441`에서 `finally` 안에서 저장한 뒤 `:444-445`의 `show_outcome`이 실행되므로, **이 시간만큼 답변 표시가 늦어진다.**
- 프로세스 시작 후 첫 저장 때는 app_log 전용 pool(`execution_log._log_database_manager`, `:66`)이 만들어지면서 **+4,656 ms**가 더 든다(pool 생성 실측). 첫 질문이 체감상 특히 느린 원인 중 하나다.

**개선안**
1. `streamlit_app.py` 제출 분기에서 `show_outcome`을 먼저 그리고 그다음 저장한다. 저장은 계속 `finally`에 두어 렌더링 예외가 나도 남게 한다. 효과: 체감 **−0.77 s**(첫 저장은 −5.4 s). 대안으로 `persist_app_logs`를 백그라운드 스레드로 실행할 수 있으나, 프로세스 종료 시 유실 가능성이 있다.
2. `_log_database_manager`를 autocommit pool로 만든다. INSERT 1문장은 그 자체로 원자적이다. 효과: 772 → 약 258 ms.
3. 앱 시작 시 `get_pipeline`(검색 pool)과 `_log_database_manager().warmup(camel_case_keys=False)`를 미리 실행한다. 효과: 첫 질문 −4.7 s 이상(선행 문서의 cold +7 s와 별도).

### 예상 종합 효과 (추정, 웜 상태·혜택 1개 질문)

| 적용 단계 | 전체 시간 | 비고 |
|---|---:|---|
| 현재 (실측) | 21.7 s | DB 11.1 + API 9.8 + 저장 0.8 |
| + P1 autocommit | 약 17.4 s | −4.3 |
| + P2 정적 캐시 | 약 16.0 s | −1.4 |
| + P3 card.list 통합 + get_detail 트랜잭션 통합 | 약 14.2 s | −0.8, −1.0 |
| + P5 저장을 표시 뒤로 | 약 13.4 s (체감) | −0.8 |
| + P3 2단계(단일 문장)·근거 컬럼 축소 | 약 12.5 s | −0.3~1.2 |
| + P4 병렬 | 약 11 s | −1.2 |

개선 후 남는 시간은 대부분 LLM 2회(약 7.8 s)와 임베딩(약 2.0 s)이다. 답변 LLM은 `validate_answer` 검증을 마친 결과만 보여 주므로 스트리밍 표시로 체감을 줄이는 방식은 검증 원칙과 맞지 않아 권장하지 않는다.

---

## 5. 정확도·근거 검증 유지 확인 계획 (구현 단계)

1. 오프라인 테스트: `run_offline_tests.py`, `payment_card/tests/test_card_graphrag.py`, `test_neo4j_origin_search.py`, `test_answer_text.py`.
2. 동일성 비교: app_log의 기존 질문 20여 건에 대해 개선 전후로 아래 항목이 같은지 대조한다(LLM 없이 stub으로 비교 가능).
   - 후보 hits(순위 포함)
   - `search_parameters.benefit_keys`
   - `retrieved_data`의 rules / conditions / limits / evidence 건수와 evidence_id 집합
   - `exclusions`, `open_conditions`
3. `search_eval.py` 50문항 A/B/C 후보 검색 결과가 같은지 확인한다.
4. 캐시 무효화 테스트: Neo4j 재적재 또는 등록 후 카탈로그가 갱신되는지 확인한다.
5. 실제 API를 쓰는 답변 비교는 소수 문항만, 별도 승인을 받아 진행한다.

---

### 부록: 측정 원자료

| 항목 | 값 |
|---|---|
| app_log pool cold 생성 | 4,656 ms |
| PG TCP connect RTT | 253.9 / 257.0 / 281.8 / 254.9 / 269.4 ms |
| Neo4j TCP connect RTT | 98.0 / 89.2 / 92.3 / 94.1 / 89.2 ms |
| PG autocommit 문장별 (8건) | 268 / 264 / 256 / 261 / 261 / 258 / 258 / 257 ms |
| Neo4j `RETURN 1` (트랜잭션 1개) | 277 / 266 / 264 / 267 / 267 ms |
| 웜업 stub 실행(첫 요청, API 미사용) | 15,532 ms (cold 연결 포함) |
| 실측 API 비용 합계 | 약 $0.00096 |
| 측정 스크립트 위치 | 세션 임시 폴더(저장소 밖). 소스·DB 구조 무수정 |
