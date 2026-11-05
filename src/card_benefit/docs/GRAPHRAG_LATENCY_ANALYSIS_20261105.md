# Streamlit GraphRAG 답변 지연 원인 분석 (2026-11-05)

> 대상: `src/card_benefit/payment_card/db_pipeline_origin_search/` (Streamlit 화면 → `CardGraphRAG`)
> 범위: 원인 분석만. 소스·DB 구조·데이터 수정 없음, 외부 유료 API(LLM·임베딩) 호출 없음, DB는 읽기 전용 조회만 수행.

## 0. 요약 — 가장 유력한 원인 3개

| 순위 | 원인 | 근거 종류 | 핵심 수치 |
|---|---|---|---|
| 1 | **PostgreSQL SELECT 1건마다 왕복 3회(BEGIN·SELECT·COMMIT) × 원거리 DB(Supabase eu-west-1, RTT ≈ 255 ms)** | 실측 | SELECT 1건 ≈ 765 ms, 서버 실행은 0.06~4 ms. 질문 1건 8건 ≈ **6.1 s** |
| 2 | **Neo4j 쿼리를 문장 단위로 순차 실행(N+1)하고, 매 요청 같은 카탈로그를 다시 읽음** | 실측 + 소스 | 1건 ≈ 260~580 ms, 서버 실행 1~3 ms. 혜택 1개 질문 13건 ≈ **3.9 s**, 혜택 4개 질문 26건 |
| 3 | **LLM 2회(질문 해석 → 답변) + 임베딩 1회가 모두 순차 실행** | 소스 확인 + 로그 기반 상한 추정 (**미측정**) | 답변 프롬프트 ≈ 4.6k 토큰(근사), 출력 상한 2,000. app_log 간격으로 본 LLM·임베딩 합계 상한 ≈ 8 s 이하(추정) |

- LLM을 빼고 실제 DB·Python 경로만 재현해도 **질문 1건이 약 10.2 s**(웜 상태 중앙값) 걸렸다. 이 시간의 99% 이상이 네트워크 대기이고, Python·LangGraph 처리는 약 35 ms다.
- 프로세스 시작 후 첫 질문은 연결 준비 때문에 **약 7 s가 더 걸린다**(실측 17.3 s). 화면 출력 전에 app_log INSERT를 기다리는 구간도 있다(소스 확인, 시간은 추정).
- 검색 정확도나 PDF 근거 검증을 줄이지 않아도 쿼리 묶음 실행·정적 데이터 캐시·autocommit 읽기만으로 DB 구간을 **약 10 s에서 2~3 s 수준으로 줄일 수 있을 것으로 추정**한다(§4).

---

## 1. 전체 실행 흐름 (실제 함수 호출 관계)

기본 검색 방식은 C(하이브리드)다(`streamlit_app.py:378`, `index=2`). 아래는 C 모드 기준이다.

```
[Streamlit] streamlit_app.py (재실행 모델: 폼 제출 시 1회 실행)
 ├ 모듈 수준: configure_card_logging(), configure_application_logging()          :91-93
 ├ 질문 폼 제출(submitted)                                                       :387
 │   ├ 같은 질문·같은 모드·오류 없음 → 이전 결과 재사용(LLM·DB 미호출)             :395-406
 │   └ 그 외
 │      ├ get_pipeline(search_mode)  @st.cache_resource (모드별 1회 생성)          :98-115
 │      │    ├ neo4j_search.connect()  → Neo4j 드라이버
 │      │    ├ card_graphrag.create_benefit_search()  → PostgresDbSession + OpenAIEmbedder
 │      │    └ card_graphrag.create_llms()  → ChatOpenAI ×2 (interpret / answer)
 │      ├ execution_log.request_pipeline()  → 요청마다 새 PostgresDbSession(mapper 재파싱) :147-185
 │      ├ capture_request_queries() 안에서 pipeline.run(question)                  :421-422
 │      ├ finally: persist_app_logs()  → app_log INSERT (화면 출력 전, 동기)        :430-441
 │      └ show_outcome()  → 최종 답변 출력                                         :444-445
 │
[LangGraph] card_graphrag.CardGraphRAG.run → graph.invoke                        :1490-1496
 START → interpret ─┬→ retrieve ─┬→ answer → finish → END                         :1464-1480
                    └→ finish    └→ finish
 ① interpret                                                                     :1565
    ├ Neo4j  list_catalog(): card.catalog, card.item_catalog, card.common_catalog (3건) :1591
    ├ BenefitSearchService.catalog_rows → search(mode="C", use_graph=True)        :1600
    │   ├ _keyword: PG keyword_card_bnft, keyword_common_bnft (2건)               :211-221
    │   │           Neo4j card.list × 질문 낱말 수(3~6건, 낱말마다 1건씩)            :223-229
    │   ├ _vector:  PG select_last_embedding_run (1건)                            :244
    │   │           OpenAI 임베딩 1회 (유료, 미측정)                               :247
    │   │           PG search_card_bnft, search_common_bnft (2건)                 :248-249
    │   ├ _confirmed_duplicates: PG brand_bnft_compare (조건부 1건, 전체 비교표)   :196-209
    │   └ _rank_with_graph: Neo4j card.relations (1건)                           :175
    └ LLM #1 질문 해석 (Interpretation, 구조화 출력)                               :1628
 ② retrieve  (선택된 혜택 key마다 순차)                                           :1675
    ├ Neo4j get_detail: card.context + rules/conditions/limits/evidence (최대 5건/혜택) :1702, neo4j_search.py:250-278
    ├ (공통 혜택 근거 0건이면) PG 근거 대체 조회                                  :1704-1709
    ├ collect_evidence (PDF 근거 병합, 순수 함수)                                 :1721
    └ find_exclusions → PG select_card_bnft_detail (혜택마다 1건, 원본 대조)      :1722-1727
 ③ answer                                                                        :1750
    ├ PG select_card_terms (1건)                                                  :1788
    ├ LLM #2 답변 생성 (CardAnswer, 구조화 출력)                                   :1806
    └ validate_answer → enforce_exclusions (근거·숫자 대조, 순수 함수)             :1816-1817
 ④ finish: 안내 문구·비용 로그                                                    :1840
```

DB 접근 계층:

- Neo4j: `Neo4jSearch._query`(`neo4j_search.py:184-206`)가 **Cypher 1건마다 새 세션과 `execute_read` 트랜잭션 1개**를 만든다. 드라이버는 `get_pipeline` 캐시로 재사용한다.
- PostgreSQL: `PostgresDbSession.select_list`(`common/postgres_db_session.py:489`)가 **SQL 1건마다 pool에서 연결을 빌린다**(`DatabaseManager.connect`, `common/database_manager.py:212`). 연결은 non-autocommit이라 블록이 끝날 때 COMMIT한다. 물리 연결은 pool로 재사용하며 매번 새로 접속하지 않는다.

---

## 2. 병목 분석

### 2-1. app_log로 재구성한 실제 질문 1건

대상: `session_id=02c4429b-769f-4145-b929-b73a9bb63cb5`, `request_id=5a6f4dc5-d4db-44dd-8aec-00b13e272c93`, 질문 "ONE PICK STYLE 카드의 대중교통 혜택은?", 2026-11-05 07:16:21 UTC.
`execution_log`에 남은 실행 순서(21건):

| # | 노드 | 엔진 | 문장 ID | 비고 |
|---:|---|---|---|---|
| 1-3 | interpret | Neo4j | card.catalog → card.item_catalog → card.common_catalog | 매 요청 같은 전체 목록 |
| 4-5 | interpret | PG | keyword_card_bnft → keyword_common_bnft | `TERMS=['ONE','PICK','STYLE','대중교통']` |
| 6-9 | interpret | Neo4j | card.list ×4 | 낱말마다 1건. 그중 3건은 카드명 낱말 |
| — | interpret | OpenAI | 임베딩 1회 | app_log에 기록 없음 |
| 10-12 | interpret | PG | select_last_embedding_run → search_card_bnft → search_common_bnft | |
| 13 | interpret | PG | brand_bnft_compare | 매 요청 같은 전체 비교 |
| 14 | interpret | Neo4j | card.relations | |
| — | interpret | LLM | 질문 해석 | app_log에 기록 없음 |
| 15-19 | retrieve | Neo4j | card.context → rules → conditions → limits → evidence | 혜택 1개 |
| 20 | retrieve | PG | select_card_bnft_detail | 제외 판정 원본 대조 |
| 21 | answer | PG | select_card_terms | |
| — | answer | LLM | 답변 생성 | app_log에 기록 없음 |

app_log 전체 78행(46세션)을 보면 LLM까지 실행된 요청은 14~37건(대부분 20~24건)을 실행했다. 혜택 4개를 고른 "ONE PICK STYLE 카드의 전월 실적 조건과 혜택을 알려줘."는 37건이다. 이 중 Neo4j가 26건이고, `get_detail`과 `select_card_bnft_detail`이 혜택 수에 비례해 늘어난다.

**app_log의 한계.** `execution_log`에는 `QUERY [` 로 시작하는 쿼리 전문만 저장되고 시간이 없다. `SQLCaptureHandler`·`CypherCaptureHandler`(`execution_log.py:71-117`)가 `elapsed_ms`가 든 `CYPHER`/`RESULT`/`FINAL` 요약 줄을 버리기 때문이다. Cypher logger는 `propagate=False`라서 이 줄들은 터미널에도 나오지 않는다. LLM 호출 기록(`llm_calls`)과 후보 검색 시간(`candidate_search.elapsed_ms`)도 app_log에 저장되지 않는다. `track_commit_timestamp=off`라 저장 시각도 알 수 없다. 그래서 단계별 시간은 아래 §3의 읽기 전용 재현으로 측정했다.

**app_log로 얻은 상한값(추정).** 같은 세션에서 LLM까지 실행된 요청과 그다음 요청의 시작 간격은 18.0~24.8 s였다(요청 13건). 이 간격에는 앞 요청 처리, 화면 출력, 사용자 입력 시간이 모두 들어 있다. 따라서 **질문 1건의 처리 시간은 약 18~20 s 이하**로 볼 수 있다.

### 2-2. 확인 항목별 결과

| 확인 항목 | 결과 | 근거 |
|---|---|---|
| 질문 1건당 LLM 호출 횟수 | **채팅 LLM 2회**(interpret 1, answer 1) + **임베딩 1회**(B·C 모드). 연회비만 묻는 질문은 answer LLM을 생략. 재시도 없음(`max_retries=0`) | 소스 `card_graphrag.py:342-353, 1628, 1767-1773, 1806`, `benefit_search_service.py:247` |
| 모델명 | 채팅 `gpt-6-luna`(`CARD_SEARCH_MODEL`로 변경 가능), reasoning_effort=low, 출력 상한 600 / 2,000(추론 토큰 포함), timeout 60 s | 소스 `card_graphrag.py:71-75` |
| 토큰 수 | 재현에서 만든 실제 프롬프트: interpret 2,599자 ≈ 1,243 토큰, answer 9,677자 ≈ 4,602 토큰 (**o200k_base 로컬 근사, 과금 토큰 아님**). 출력 토큰은 미측정 | 재현 측정 |
| LLM 소요 시간 | **미측정**(유료 호출 승인 필요). 상한 추정: 18~20 s − DB 약 10.3 s − app_log 저장 약 0.8 s ⇒ LLM 2회 + 임베딩 + 사용자 입력 ≲ 7~9 s | 추정 |
| Neo4j 쿼리 횟수·시간 | 혜택 1개: **13건 ≈ 3.9 s**(1건 260~580 ms). 서버 실행은 card.catalog 3 ms, card.list 1 ms | 실측 §3 |
| 비슷한 Cypher 반복 | ① `card.list`를 질문 낱말 수만큼 반복(3~6회, 파라미터만 다름). ② `card.context/rules/conditions/limits/evidence`를 혜택마다 반복. ③ card.catalog 3종을 매 요청 동일 결과로 재조회 | app_log + 소스 |
| PostgreSQL 쿼리 횟수·시간 | 혜택 1개: **8건 ≈ 6.1 s**(1건 ≈ 765 ms). 서버 실행 0.06~4 ms | 실측 §3 |
| LangGraph 노드 반복 | **없음.** 경로는 항상 `interpret → retrieve → answer → finish`이고 노드마다 1회. 루프 Edge 없음 | 소스 `_build`, 재현 `path` |
| DB 연결을 매번 새로 생성하는지 | 물리 연결은 **재사용**한다(psycopg_pool, Neo4j 드라이버 pool). 다만 PG는 쿼리마다 트랜잭션(BEGIN/COMMIT)을, Neo4j는 쿼리마다 세션·트랜잭션을 새로 연다. 요청마다 `PostgresDbSession`을 새로 만들어 SQL mapper 파일을 다시 파싱한다(≈ 25 ms) | 소스 + 실측 |
| 순차 실행으로 인한 대기 | 독립적인 작업이 모두 순차 실행된다: Neo4j 카탈로그 ↔ PG 문자열 검색 ↔ 임베딩 API ↔ PG 벡터 검색, 혜택별 상세 조회, `select_card_terms`. `persist_app_logs`(INSERT)가 `show_outcome`보다 먼저 실행돼 화면 출력이 저장을 기다린다 | 소스 `streamlit_app.py:430-445` |
| Streamlit 재실행 영향 | 질문 입력은 `st.form`이라 타이핑 중에는 실행되지 않는다. 같은 질문은 재사용 경로라 LLM·DB를 호출하지 않는다. **첫 질문(모드별)은 cold start 약 +7 s**(§3-3). 모드 A/B/C마다 파이프라인·Neo4j 드라이버·PG pool이 따로 생겨 모드를 바꾸면 다시 cold start를 겪는다. 실행 중 버튼을 다시 누를 때의 중단·재실행 영향은 **미확인** | 소스 + 실측 |
| 로그 출력 부하 | DEBUG 상세 로그(Cypher 전문, 결과 표) 켬/끔 차이는 측정 오차 수준(10.0~12.1 s vs 10.0~10.5 s) | 실측 |

---

## 3. 실제 측정

### 3-1. 측정 방법

- **재현 대상:** §2-1의 실제 요청("ONE PICK STYLE 카드의 대중교통 혜택은?", C 모드, 대상 key `["card_bnft",2,"20261101_000003"]`).
- **실행 코드:** 실제 `CardGraphRAG`, `Neo4jSearch`, `BenefitSearchService`, `request_pipeline`, `capture_request_queries`를 그대로 사용했다. Streamlit과 같은 로그 설정이다(`APP_DB_LOG_ENABLED=on`).
- **대체한 부분 (유료 API 미호출):**
  - 채팅 LLM 2회 → 고정 결과를 바로 반환하는 stub. 해석은 app_log에서 실제로 선택된 혜택을 돌려준다.
  - 임베딩 → 대상 혜택의 저장된 `item_embedding`(같은 차원·모델)을 질문 벡터로 사용. SQL 실행 계획은 같고 결과 순위만 다를 수 있다.
- **계측:** 소스를 수정하지 않고 측정 프로세스 안에서만 `Neo4jSearch._query`, `PostgresDbSession.select_list`, LangGraph 노드 메서드를 시간 측정 래퍼로 감쌌다.
- **쓰기 없음:** Neo4j는 READ_ACCESS, PG는 SELECT와 `EXPLAIN ANALYZE SELECT`만 실행했고 `persist_app_logs`(INSERT)는 호출하지 않았다.
- **회차:** cold 1회 + warm 5회(로그 켬) + warm 3회(상세 로그 끔).
- **측정 위치:** 개발 PC(로컬). 배포 환경(예: Streamlit Cloud)은 DB까지의 거리가 달라 수치가 다를 수 있다.

### 3-2. 질문 1건 단계별 시간 (warm, 8회 중앙값)

| 단계 | 호출 횟수 | 총 소요 시간 | 측정 구간 대비 비율 | 비고 |
|---|---:|---:|---:|---|
| PostgreSQL | 8 | **6.14 s** | 60% | 1건 760~1,060 ms, 서버 실행 ≤ 4 ms |
| Neo4j | 13 | **3.92 s** | 38% | 1건 258~586 ms, 서버 실행 1~3 ms |
| LLM (채팅) | 2 | **미측정** | — | stub 사용. 유료 호출 승인 필요 |
| 임베딩 (OpenAI) | 1 | **미측정** | — | stub 사용 |
| LangGraph·Python 처리 | — | ≈ 0.035 s | < 1% | mapper 재파싱 25 ms 포함 |
| **전체(측정 구간)** | | **10.24 s** | 100% | LLM·임베딩 시간 제외 |

> 전체 대비 비율은 LLM·임베딩 시간을 측정하지 않아 계산할 수 없다. 위 비율은 "LLM을 제외한 측정 구간" 기준이다.
> app_log 상한(≲ 18~20 s)과 비교하면 DB 대기(≈ 10.3 s)가 실제 전체의 **절반 이상일 가능성이 높다(추정)**.

노드별(warm 중앙값): interpret 7.08 s / retrieve 2.39 s / answer 0.77 s / finish 0.2 ms (LLM 시간 제외).

### 3-3. 문장별 시간 (warm 8회 중앙값, ms)

| 엔진 | 문장 | 중앙값 | 서버 실행 |
|---|---|---:|---:|
| PG | keyword_card_bnft | 768 | 4.03 |
| PG | keyword_common_bnft | 781 | 1.86 |
| PG | select_last_embedding_run | 762 | 0.08 |
| PG | search_card_bnft | 766 | — |
| PG | search_common_bnft | 766 | — |
| PG | brand_bnft_compare | 765 | — |
| PG | select_card_bnft_detail | 764 | 0.06 |
| PG | select_card_terms | 762 | 0.07 |
| Neo4j | card.catalog | 374 | 3 |
| Neo4j | card.item_catalog | 263 | — |
| Neo4j | card.common_catalog | 270 | — |
| Neo4j | card.list ×4 | 261~267 (합 ≈ 1,053) | 1 |
| Neo4j | card.relations | 366 | — |
| Neo4j | card.context | 275 | — |
| Neo4j | card.rules | 269 | — |
| Neo4j | card.conditions | 277 | — |
| Neo4j | card.limits | 269 | — |
| Neo4j | card.evidence | 499 | — |

쿼리 내용과 관계없이 PG는 약 765 ms, Neo4j는 약 260 ms로 일정하다. 즉 쿼리 처리 비용이 아니라 왕복 지연이 시간을 결정한다.

### 3-4. 네트워크 왕복 분리 측정

| 항목 | 측정값 |
|---|---|
| PG 호스트 리전 | Supabase pooler **aws-0-eu-west-1** (port 5432) |
| PG 신규 접속 | 1,584 ms |
| PG `SELECT 1` (autocommit) | 258~263 ms ⇒ **RTT ≈ 255 ms** |
| PG `SELECT 1` + COMMIT (non-autocommit) | 760~770 ms ⇒ BEGIN·SELECT·COMMIT **3회 왕복** |
| PG pool 경유 `SELECT 1` (`DatabaseManager.connect`와 같은 방식) | 764~772 ms |
| Neo4j `verify_connectivity` | 900 ms |
| Neo4j `RETURN 1` (쿼리마다 세션) | 279~300 ms |
| Neo4j `RETURN 1` (같은 세션 재사용) | 281~290 ms ⇒ 세션 생성 비용은 무시할 수준, 트랜잭션 왕복이 비용 |
| Neo4j `RETURN` ×5 를 트랜잭션 1개로 | 659~734 ms (5회 개별 실행 ≈ 1,430 ms) |

### 3-5. Cold start (프로세스 시작 후 첫 질문)

| 항목 | 측정값 |
|---|---:|
| 모듈 import (langchain·langgraph·openai 등) | 2.0 s |
| `create_benefit_search` | 0.89 s |
| `CardGraphRAG` 생성(그래프 컴파일) | 0.92 s |
| 첫 요청 전체 | **17.3 s** (warm 10.2 s 대비 +7.0 s) |
| └ 첫 PG 쿼리(pool 생성 + 접속 + pgvector 등록) | 5.37 s (warm 0.77 s) |
| └ 첫 Neo4j 쿼리(라우팅·TLS) | 1.51 s (warm 0.37 s) |
| └ 첫 card.relations | 1.04 s (warm 0.37 s) |

`get_pipeline`은 질문 제출 분기 안에서 처음 호출되므로 이 비용은 **첫 사용자 질문에 그대로 더해진다**. app_log 저장용 `_log_database_manager()` pool도 첫 저장 때 따로 만들어진다(INSERT 금지로 미측정, 같은 pool 생성 방식이라 수 초 추가로 추정).

---

## 4. 개선 방향

### 4-1. 소스에서 확인된 문제

1. **PG SELECT마다 트랜잭션 1개.** `select_list` → `DatabaseManager.connect()` → `pool.connection()`(non-autocommit)라서 SELECT 1건이 BEGIN·SELECT·COMMIT 3회 왕복이다(`common/database_manager.py:211-226`).
2. **Neo4j 쿼리마다 세션·트랜잭션 1개**(`neo4j_search.py:199-200`). `get_detail`은 혜택 1개에 최대 5건을 순차 실행하고, 혜택 N개면 5N건이 된다.
3. **`card.list`를 낱말마다 실행**(`benefit_search_service.py:225-226`). 카드명 낱말(ONE, PICK, STYLE 등)도 각각 실행된다.
4. **매 요청 같은 정적 데이터를 다시 읽음:** `card.catalog / item_catalog / common_catalog`, `select_last_embedding_run`, `brand_bnft_compare`(전체 비교표). 적재가 바뀌기 전에는 결과가 같다.
5. **혜택별 `select_card_bnft_detail` 순차 실행**(`card_graphrag.py:1724-1727`). 여러 혜택을 `ANY(array)` 1건으로 묶을 수 있는 구조다.
6. **독립 작업의 순차 실행:** Neo4j 카탈로그, PG 문자열 검색, 임베딩 API, PG 벡터 검색은 서로 결과를 기다릴 필요가 없다. 혜택별 상세 조회도 서로 독립이다.
7. **화면 출력 전 app_log INSERT 동기 대기**(`streamlit_app.py:430-445`). 응답이 나왔는데도 INSERT(약 3회 왕복)가 끝나야 답변이 보인다.
8. **요청마다 `PostgresDbSession` 재생성 → SQL mapper 재파싱**(`execution_log.py:159`) ≈ 25 ms. 영향은 작다.
9. **모드별로 따로 cold start:** A/B/C마다 Neo4j 드라이버·PG `DatabaseManager`·LLM 클라이언트를 별도로 생성한다(`streamlit_app.py:98-115`, `card_graphrag.py:332`).

### 4-2. 실행 측정으로 확인된 문제

- DB 대기 ≈ 10.2 s / 질문 (LLM 제외). PG 6.1 s, Neo4j 3.9 s.
- 서버 실행 시간은 ms 단위라서 **인덱스·쿼리 튜닝은 효과가 거의 없다.** 줄여야 할 것은 왕복 횟수와 순차 대기다.
- 첫 질문 cold start +7 s.
- 상세 로그(DEBUG)는 병목이 아니다.

### 4-3. 추정되는 문제 (추가 측정 필요)

- LLM 2회 + 임베딩 1회의 실제 소요 시간. app_log 기준 상한은 약 7~9 s로, DB 다음으로 큰 구간일 가능성이 높다. answer는 입력 약 4.6k 토큰, 출력 상한 2,000(추론 포함)이라 출력 생성 시간이 대부분일 것으로 본다.
- 배포 환경의 RTT. 로컬(한국 추정)에서 eu-west-1까지 255 ms다. 배포 서버 위치에 따라 DB 구간 수치는 크게 달라진다.
- app_log 전용 pool의 cold 생성과 INSERT 대기 시간.
- 혜택 다수 질문(37건)의 DB 시간: 측정 단가로 계산하면 Neo4j 26건 × 약 0.29 s + PG 11건 × 약 0.77 s ≈ 16 s (추정).

### 4-4. 개선 방법과 예상 효과 (정확도·PDF 근거 검증 유지)

예상 효과는 §3 측정 단가(PG 765 ms/건, autocommit 258 ms/건, Neo4j 약 280 ms/건)로 계산한 **추정치**다.

| # | 개선 | 정확도 영향 | 예상 절감 (혜택 1개 질문) |
|---|---|---|---|
| A | **검색용 PG 읽기를 autocommit pool로** 실행. 검색 전용 `DatabaseManager`/세션을 따로 두고 쓰기 경로는 그대로 유지. 또는 노드 단위로 `session.transaction()` 1개 안에서 여러 SELECT 실행 | 없음 (같은 SQL·같은 결과) | 8건 × (765 → 258 ms) ≈ **−4.0 s** |
| B | **Neo4j `get_detail` 5건을 트랜잭션 1개(`execute_read` 안에서 `tx.run` 여러 번)로**, 여러 혜택은 `UNWIND $keys`로 묶기 | 없음 (같은 Cypher·같은 레코드) | 혜택당 약 −0.7~1.1 s. 혜택 4개면 약 −4 s 이상 |
| C | **`card.list` N건 → 1건:** `UNWIND $keywords AS kw … RETURN kw, b.key`로 낱말별 일치 행을 한 번에 받아 같은 방식으로 점수를 더함 | 없음 (점수 계산 동일) | (N−1) × 약 0.26 s ≈ **−0.8~1.3 s** |
| D | **정적 데이터 캐시:** card.catalog 3종, `select_last_embedding_run`, `brand_bnft_compare`를 프로세스 캐시에 두고 TTL을 두거나 적재 버전이 바뀔 때 무효화 | 캐시 무효화가 맞으면 없음 (아래 부작용 참고) | Neo4j 약 0.9 s + PG 2건(A 적용 전 1.5 s, 후 0.5 s) ≈ **−1.4~2.4 s** |
| E | **독립 작업 병렬화:** interpret에서 Neo4j 카탈로그 ∥ PG 문자열 검색 ∥ 임베딩 API, retrieve에서 혜택별 상세 ∥ `select_card_terms` 선조회 | 없음 (같은 데이터) | 대기 겹침만큼. 임베딩 시간이 PG 대기에 숨는 효과 |
| F | `select_card_bnft_detail` 혜택 N건 → `ANY(array)` 1건 | 없음 (PG 원본 대조 유지) | (N−1) × 0.26~0.77 s |
| G | **답변 먼저 출력하고 app_log는 나중에 저장:** `show_outcome` 뒤 또는 별도 스레드에서 저장. 저장 실패가 검색 결과에 영향을 주지 않는 기존 원칙 유지 | 없음 | 약 −0.8 s (첫 저장은 수 초, 추정) |
| H | **cold start 미리 준비:** 앱 시작 시 `get_pipeline` 생성과 `DatabaseManager.warmup()`, Neo4j `verify_connectivity()` 실행. 모드 간 드라이버·pool 공유 | 없음 | 첫 질문 약 −7 s |
| I | (인프라) 앱 서버와 DB를 같은 리전에 두기, 또는 사용자 가까운 리전으로 DB 이전 | 없음 | RTT 255 ms가 수 ms로 줄면 DB 구간 대부분 소거 (이번 범위 밖) |
| J | LLM: answer 문맥(약 4.6k 토큰)에서 중복 필드 정리, 출력 상한·추론 강도 재검토 | **정확도 영향 가능** → 50문항 평가로 검증한 뒤에만 적용 | 측정 후 판단 |

A + B + C + D를 함께 적용하면 혜택 1개 질문의 DB 구간은 약 10.2 s에서 **약 2~3 s**로 줄 것으로 추정한다. E·G를 더하면 체감 대기가 더 줄어든다.

**LLM 호출 수는 줄이지 않는 것을 권장한다.** 질문 해석 LLM은 후보 중 대상 혜택을 고르고, 서버가 그 결과를 실제 목록과 다시 대조한다. 답변 LLM의 출력은 `validate_answer`가 근거·숫자로 검증한다. 둘 다 정확도와 근거 검증 구조의 핵심이고, 반복·재시도 같은 불필요한 호출은 소스에서 발견되지 않았다. 연회비만 묻는 질문은 이미 answer LLM을 생략한다.

**Neo4j 쿼리 통합 가능성:**

- (가능, 위험 낮음) `get_detail` 5건, `card.list` N건, 혜택별 반복 → 트랜잭션 1개 또는 `UNWIND`로 묶기.
- (가능, 검증 필요) card.catalog 3종을 `CALL {}` 서브쿼리 1건으로 합치기. 캐시를 적용하면 굳이 합칠 필요가 줄어든다.
- (주의) `card.context / rules / conditions / evidence`를 OPTIONAL MATCH 1개로 합치면 행 곱(카테시안)으로 결과가 부풀 수 있다. `CALL { … collect() }` 서브쿼리 형태로만 합쳐야 한다.
- (검증 필요) `card.list`를 Neo4j 대신 이미 읽은 카탈로그에서 계산하기. 두 쿼리의 대상 조건이 조금 다르므로(catalog는 `dp_card_product`에 연결된 혜택만 포함) 50문항 평가(`search_eval.py`)로 결과가 같은지 확인한 뒤에만 적용한다.

### 4-5. 수정 시 발생할 수 있는 부작용

| 개선 | 부작용·주의점 |
|---|---|
| A autocommit | `DatabaseManager`는 등록(쓰기) 경로와 공용이다. 공용 pool을 autocommit으로 바꾸면 `transaction()`의 원자성이 깨질 수 있으므로 **검색 전용 pool로 분리**해야 한다. 트랜잭션으로 묶는 방식은 LLM 호출 동안 연결을 잡고 있지 않도록 범위를 노드 안으로 한정해야 한다(유휴 트랜잭션 방지). |
| B·C 묶음 실행 | 로그의 문장 단위 기록(app_log `execution_log`)과 `verify_view` 단계별 화면이 문장 ID 기준이라 표시 방식을 함께 바꿔야 한다. 결과 순서·키 매핑을 테스트(`test_neo4j_origin_search.py`, `test_card_graphrag.py`)로 확인해야 한다. |
| D 캐시 | Neo4j 재적재나 신규 카드 등록 뒤에도 캐시가 남으면, 질문 해석 목록과 ID 대조(환각 ID 차단)가 옛 데이터로 이뤄진다. 상세 조회는 실제 DB를 읽으므로 잘못된 답 대신 NO_RESULT가 나는 쪽으로 실패하지만, 적재 버전 확인이나 TTL로 무효화해야 한다. 임베딩 모델 확인(`select_last_embedding_run`) 캐시도 재임베딩 때 무효화가 필요하다. |
| E 병렬화 | `REQUEST_ID`, `ACTIVE_QUERY_EVENTS`(ContextVar)는 스레드로 자동 전달되지 않는다(`contextvars.copy_context` 필요). 전달하지 않으면 app_log 쿼리 수집이 빠진다. psycopg 연결과 Neo4j 세션은 스레드 간에 공유하면 안 된다(pool `max_size=5` 범위 안에서 각자 대여). 로그 순서도 바뀐다. |
| G 저장 순서 | 화면 출력 중 예외가 나도 저장되도록 try/finally 구조를 유지해야 한다. 백그라운드 저장은 프로세스 종료 시 유실될 수 있다. |
| H 사전 준비 | 앱 시작 시간이 늘고, DB가 일시 장애이면 시작 단계에서 오류 처리가 필요하다(현재는 첫 질문에서 오류 표시). |
| J LLM 조정 | 출력 상한을 낮추면 구조화 출력이 잘려 파싱 실패(LLM_FAILED)가 날 수 있다. 문맥을 줄이면 근거 인용이 줄 수 있다. 반드시 평가 후 적용한다. |

---

## 5. 추가 계측 제안 (소스 수정이 필요해 이번에는 미적용)

1. app_log에 단계 시간 저장: capture handler가 `CYPHER`/`RESULT` 요약 줄(`elapsed_ms`)과 `FINAL total_ms`도 수집하도록 하고, `llm_calls`(모델·토큰·`elapsed_ms`)와 `candidate_search.elapsed_ms`를 함께 저장한다.
2. 임베딩 호출 시간·토큰을 `llm_calls`와 같은 형식으로 기록한다(현재 어디에도 남지 않음).
3. 요청 완료 시각(`finished_at`)이나 전체 소요 시간 컬럼을 추가한다(DB 구조 변경이라 별도 승인 필요).

## 6. 승인이 필요한 후속 측정

> **2026-11-05 실측 완료:** [GRAPHRAG_LATENCY_MEASUREMENT_AND_DESIGN_20261105.md](GRAPHRAG_LATENCY_MEASUREMENT_AND_DESIGN_20261105.md) 참조 (실제 API 포함 21.74 s, LLM 7.85 s, 임베딩 1.96 s).

LLM·임베딩 실측은 유료라 이번에는 실행하지 않았다. 승인하면 같은 재현 스크립트에서 stub을 실제 호출로 바꿔 1~3회 실행하고, `llm_calls`의 `elapsed_ms`·입력·출력·추론 토큰을 표 §3-2에 채운다.

- 예상 비용(현재 단가표 `MODEL_PRICES` 기준, 상한): 1회당 입력 약 5.8k 토큰 × $0.10/1M + 출력 최대 2.6k 토큰 × $0.50/1M ≈ **$0.002 이하**, 임베딩은 무시할 수준.

---

### 부록: 측정 재현 메모

- 실행 위치: 개발 PC, 2026-11-05, `uv run python -I <script>`.
- `app_log`: `SELECT … FROM db_pipeline.app_log`, 연결 옵션 `default_transaction_read_only=on`.
- 재현: 실제 `CardGraphRAG`(C 모드) + stub LLM·임베딩. 프로세스 안에서만 메서드를 감싸 시간 측정(소스 파일 무수정).
- RTT: `SELECT 1`(autocommit / commit 포함 / pool 경유), `EXPLAIN (ANALYZE) SELECT`(읽기 전용), Neo4j `RETURN 1`, `ResultSummary.result_available_after`.
- 쓰기 작업은 하지 않았다(app_log INSERT 포함).
