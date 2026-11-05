# GraphRAG Neo4j 단일 검색 전환 분석·구현 계획 (2026-11-05)

> **최종 목표:** PostgreSQL은 원장(카드·혜택·조건·PDF 근거·임베딩)으로 유지하고, GraphRAG 질문 처리에서는 **Neo4j만** 검색 DB로 쓴다.
> 질문 → 질문 임베딩 → Neo4j 키워드 + 벡터 검색 → 후보 통합·그래프 관계 탐색 → 혜택·조건·제외·PDF 근거 조회 → LLM 답변·검증.
> Streamlit의 A/B/C 선택은 Neo4j 단일 검색이 검증된 뒤 제거한다.
>
> 이번 문서는 **분석과 계획**이다. 운영 PostgreSQL·Neo4j 데이터·DDL 변경, 유료 임베딩 호출, 커밋·푸시는 하지 않았다.
> 모든 조회는 읽기 전용이었다(PG 세션 `default_transaction_read_only=on` 확인, Neo4j READ_ACCESS).

---

## 1. 요약

| 질문 | 결론 |
|---|---|
| 1. 어느 노드로 이관하나 | `card_product_item(BENEFIT).item_embedding` → `dp_card_bnft`. `card_common_bnft.bnft_embedding` → `dp_card_common_bnft`. 검색 텍스트·임베딩 모델·실행 ID도 같은 노드에 둔다 |
| 2. Aura 지원·현황 | Neo4j **5.27-aura Enterprise**. `vector.similarity.cosine`, `db.index.vector.queryNodes`, `db.index.fulltext.queryNodes`가 있다. **현재 벡터·전문 인덱스는 0개**(RANGE PK 15개 + LOOKUP 2개뿐) |
| 3. 임베딩이 제외되는 이유 | 버그가 아니라 설계다. `neo4j_dry_run.load_snapshot`이 `item_embedding`·`item_search_txt`를 읽은 뒤 `SEARCH_COLUMNS = ("bnft_search_txt", "bnft_embedding")`("그래프 원본이 아닌 검색용 컬럼")로 지운다. 테스트 `test_embedding_columns_never_become_properties`가 이 정책을 고정한다 |
| 4. 재생성 없이 복사 | **가능.** 저장된 벡터 15개(1536차원, `text-embedding-3-small`)를 PG에서 읽어 Neo4j에 그대로 쓰면 된다. API 호출이 없다. 단, 질문 임베딩은 지금처럼 질문마다 1회 필요하다 |
| 5. A/B/C 전환 변경 | PG 검색 9개 지점을 Neo4j 조회로 바꾼다(§3). 그다음 후보 검색 서비스, 상세, TERMS, 제외 판정, Streamlit을 순서대로 바꾼다 |
| 6. PG를 읽는 검증 경로 | 공통 혜택 근거(대체 경로), 제외 판정 원본 대조, TERMS 근거, `pg:` key 상세, 동일성 병합 판정(§3) |
| 7. 정확도 유지 방법 | 현재 C와 신규 Neo4j 검색을 같은 질문에 함께 실행해 결과 지문을 비교한다(그림자 비교). 전부 같을 때만 전환한다(§6) |

**가장 큰 데이터 공백 두 가지:**
1. **임베딩이 116개 혜택 중 15개에만 있다**(카드 혜택 34개 중 9개, 공통 혜택 82개 중 6개). 지금 B·C의 벡터 검색도 이 15개만 찾는다.
2. **공통 혜택 PDF 근거:** PostgreSQL 추출 경로로는 **82개 모두(근거 701행)** 찾을 수 있다. 그러나 Neo4j에서는 `dp_same_as`를 통해 **1개만** 근거에 닿는다. Neo4j 단일 검색에는 이 근거 연결의 적재가 필수다.

---

## 2. 현재 구조 (실측·소스 확인)

| 모드 | 후보 검색 | 상세·근거 | PG 사용 |
|---|---|---|---|
| A | Neo4j 카탈로그 전체(118행)를 해석 LLM에 전달 | Neo4j | 없음(검색 경로). app_log 저장만 PG |
| B | PG pgvector | Neo4j(+ PG 대체 경로) | 있음 |
| C | PG 문자열 SQL + PG pgvector → RRF 통합 → Neo4j 관계로 순서 보정 | Neo4j(+ PG 대체 경로) | 있음 |

**A가 느렸던(약 18 s) 원인 추정:** A는 카탈로그 전체를 질문 해석 프롬프트에 넣는다. 해석 프롬프트가 **약 9,250 토큰**(o200k 근사)으로 C(약 1,250)의 7배다. 반면 P3 이전 A의 DB 시간은 1.9~5.8 s였다. 지연의 대부분은 해석 LLM으로 추정되며(유료 호출을 하지 않아 미측정), 이는 DB 최적화로 해결되지 않는다. 단일 검색 구조에서는 C처럼 후보를 먼저 좁혀 넘기므로 함께 해소된다.

**pgvector 인덱스 없음:** 현재 벡터 검색은 정확한 전수 비교다. 그래서 Neo4j에서 `vector.similarity.cosine` 전수 비교를 하면 같은 순위가 나온다. HNSW 벡터 인덱스는 근사 검색이라 순위가 달라질 수 있어, 동등성 단계에서는 쓰지 않는다.

---

## 3. PostgreSQL 의존 지점 전체와 Neo4j 대체 방법

| # | 위치 (소스) | 하는 일 | Neo4j 대체 | 필요한 데이터 |
|---|---|---|---|---|
| 1 | `BenefitSearchService._keyword` → `keyword_card_bnft`·`keyword_common_bnft` | 낱말이 카드명·혜택명·적용 대상명(카드 혜택) / 혜택명·공통서비스명·적용 카드명(공통)에 포함된 수 = keyword_score | 같은 규칙을 Cypher `toLower(..) CONTAINS toLower(term)`로 재현한다(Lucene 전문 검색은 점수 체계가 달라 동등성 단계에서는 쓰지 않음) | 이미 있음: `dp_card_product.product_nm`, 혜택 `name`, `dp_rule_target.target_nm`, `dp_card_common.common_nm`, `dp_has_common_benefit` |
| 2 | `_keyword` 보강 → `card.list` | Neo4j 혜택명 일치 수 가산 | 그대로(P3 `list_benefits_many`) | 있음 |
| 3 | `_vector` → `select_last_embedding_run` | 저장 벡터 모델 = 질문 임베딩 모델 확인 | 노드 속성 `embedding_model`(+ `embedding_run_id`)로 확인 | **신규 적재** |
| 4 | `_vector` → `search_card_bnft`·`search_common_bnft` | 코사인 유사도 상위 20건씩(유효기간 필터) | `vector.similarity.cosine(n.embedding, $q)` 전수 비교 + `ORDER BY` + `LIMIT 20`. 유효기간은 `bnft_valid_to_excl` | **신규 적재: embedding** |
| 5 | `_confirmed_duplicates` → `brand_bnft_compare` | 동일성 SAME인 카드 혜택·공통 혜택 병합 | `dp_same_as` 관계(SAME만 적재됨) | 있음. SAME 외 판정의 경고 문구는 Neo4j에 없음 → 판정 상태 속성을 추가하거나 경고 생략을 결정해야 함 |
| 6 | `catalog_rows` → `pg:` key | 그래프에 없는 후보를 PG key로 만든다 | 후보가 모두 그래프 노드에서 나오므로 `pg:` key가 없어진다 | — |
| 7 | `retrieve` → `benefit_search.get_detail(pg:…)` | `pg:` key 상세·근거 | 불필요(#6) | — |
| 8 | `retrieve` → `postgresql_common_key` 대체 경로 → `select_common_bnft_evidence` | 공통 혜택 근거를 추출 스테이징(`card_extr_stg`) 경로로 찾음 | Neo4j에 공통 혜택 → 근거 연결을 적재한다(같은 SQL로 만든 연결) | **신규 적재: 82개 공통 혜택 근거 701행과 해당 원문 근거·청크·페이지 노드** |
| 9 | `find_exclusions` → `read_source`(`select_card_bnft_detail`) | 제외 판정을 PG 원본 `rule_list`로 한다 | 그래프 `source_json`(A가 이미 쓰는 경로) | 있음. 적재 시 `neo4j_validate`가 PG와 노드 속성 전체를 대조한다(현재 차이 0) |
| 10 | `answer` → `card_terms`(`select_card_terms`) | TERMS(할인 유의사항·제외 목록)와 원문 근거 | `dp_card_product_item {item_type_cd:'TERMS'}`의 `source_json.item_data` + `dp_supported_by` 근거 | 있음: TERMS 14개 모두 Neo4j에 있고 근거 연결 18개 |

**정책 결정 필요(#9):** "PostgreSQL 데이터 교차 검증 유지" 조건과 "질문 처리 시 Neo4j만 조회" 목표가 충돌한다. 권장안은 **교차 검증을 질문 시점에서 적재 시점으로 옮기는 것**이다.
- 적재 후 `neo4j_validate`(노드 속성·관계·SQL↔Cypher 대조)가 통과해야 서비스한다.
- 질문 처리 시점에는 PG를 읽지 않는다.

`app_log` 저장은 검색이 아닌 기록이므로 PG에 그대로 둔다(P5 대상).

---

## 4. 데이터 이관 설계 (재생성 없음)

### 4-1. 노드 속성

| Neo4j 노드 | 새 속성 | 원천 (PG) |
|---|---|---|
| `dp_card_bnft` (34) | `embedding` (LIST<FLOAT>, 1536), `search_text`, `embedding_model`, `embedding_run_id` | `card_product_item.item_embedding`, `item_search_txt`, `card_ai_run`(EMBED, 마지막 성공 실행) |
| `dp_card_common_bnft` (82) | 같음 | `card_common_bnft.bnft_embedding`, `bnft_search_txt` |

- 임베딩이 없는 노드(카드 혜택 25개, 공통 혜택 76개)는 속성을 두지 않는다. 현재 PG에서도 벡터 검색 대상이 아니므로 동작이 같다.
- **복사 방법:**
  1. PG에서 `vector::text`를 읽는다(읽기 전용).
  2. `db.create.setNodeVectorProperty(n, 'embedding', $vec)`(float32 저장, pgvector float4와 같은 정밀도)로 쓴다.
  3. 노드별로 PG 값과 Neo4j 값의 SHA-256 및 자기 유사도 1.0을 대조한다.
  4. 유료 API 호출은 없다.

### 4-2. 공통 혜택 근거 연결 (필수)

- `select_common_bnft_evidence`와 **같은 SQL**(문서 → 추출 스테이징 → 원문 근거)로 연결 행을 만든다.
- `(dp_card_common_bnft)-[:dp_supported_by {ev_subject_cd:'COMMON', source:'stg'}]->(dp_card_source_evidence)`로 적재한다. 관계 유형은 기존 `dp_supported_by`를 재사용하거나 새 유형으로 둘 수 있고, 업무 결정이 필요하다.
- 근거 701행 중 그래프에 없는 원문 근거·청크·페이지 노드도 함께 적재한다. 현재 미리보기의 `unlinked_evidence` 2,758건에 포함된 것으로 추정되며, 적재 전 건수를 확정해야 한다.
- 그다음 `COMMON_EVIDENCE_QUERY`를 "`dp_same_as` 경로 + 직접 연결 경로"로 확장한다. 현재 결과(같은 근거 집합)와의 동일성은 PG 대체 경로 결과와 비교해 검증한다.

### 4-3. 인덱스

| 인덱스 | 용도 | 동등성 단계 사용 |
|---|---|---|
| Vector index (`dp_card_bnft.embedding`, `dp_card_common_bnft.embedding`, cosine, 1536) | 혜택 수가 늘었을 때 근사 검색 | 사용 안 함(전수 비교로 PG와 같은 순위 보장). 생성만 해 두고 규모가 커지면 순위 비교 후 전환 |
| Full-text index (혜택명·search_text, CJK analyzer) | 한국어 낱말 검색 고도화 | 사용 안 함(점수 체계가 SQL과 다름). 동등성 확인 뒤 개선 단계에서 평가 |

### 4-4. 적재 방식

Codex의 전체 적재기(`neo4j_load_draft`)는 정책상 임베딩을 넣지 않고 삭제도 하지 않는다. 그래서 `dp_related_to`와 같은 방식으로 **검색 투영 동기화 모듈**을 따로 둔다(예: `neo4j_search_projection_sync.py`).
- **원장 기준 동기화:** 원장에 없는 투영 속성·연결만 제거한다.
- **트랜잭션 1개** 안에서 처리하고, 승인한 변경 건수와 다른 노드·관계 지문 불변을 검사한다.
- preview 기본, `--apply --confirm`일 때만 쓴다.

---

## 5. 소스 변경 범위 (예정, 별도 승인 후)

| 영역 | 파일·함수 | 변경 |
|---|---|---|
| 적재 | 신규 `db_pipeline/neo4j_search_projection_sync.py` + 테스트 | 임베딩·검색 텍스트·모델 속성, 공통 혜택 근거 연결, 인덱스 생성 |
| 적재 검증 | `neo4j_validate.py` | 투영 속성(벡터 SHA)과 공통 근거 연결 대조 추가. 임베딩 정책 테스트를 "적재기는 넣지 않고 투영 모듈만 넣는다"로 갱신(Codex 조율) |
| 후보 검색 | 신규 `Neo4jBenefitSearch`(`neo4j_search.py` 또는 새 모듈) | `search()`·`catalog_rows()`를 `BenefitSearchService`와 같은 `SearchHit`/`SearchOutcome`으로 반환. keyword·vector·RRF·SAME 병합·관계 보정을 Neo4j 문장 1~2개로 처리. `_fuse`·`merge_duplicates`·`_rank_with_graph`의 순수 로직은 재사용 |
| 상세 | `neo4j_search.get_details` (P3, 이미 구현·검증) | 공통 근거 경로 확장 |
| TERMS | 신규 `Neo4jSearch.card_terms(card_ids)` | `select_card_terms`와 같은 필드 구조 |
| GraphRAG | `card_graphrag.interpret`·`retrieve`·`answer`·`create_benefit_search` | 단일 검색 경로. `pg:` 분기·PG 대체 경로·`read_source` 제거. A/B/C 분기 제거는 검증 후 |
| 화면 | `streamlit_app.py` | 검색 방식 라디오 제거, `get_pipeline()` 단일화, 같은 질문 재사용 조건에서 `search_mode` 제거. 개발자 모드에 단계별 소요 시간(후보·관계·상세·TERMS·임베딩·LLM)·선택 혜택·근거 표시 |
| 기록 | `execution_log.request_pipeline` | 검색용 PG 세션 분기 제거(app_log 저장은 유지) |
| 평가 | `search_eval.py`, `verify_view.py` | Neo4j 엔진 비교 추가, 모드 인자 정리 |

**재사용하는 P3 결과:** `get_details`(혜택 N개 상세 1문장), `list_benefits_many`(낱말 N개 1문장), `list_catalog` 1문장, `_run`(배치 문장 기록). 모두 Neo4j 전용이라 단일 검색 구조에 그대로 들어간다.

---

## 6. 검증 계획 (전환 승인 조건)

1. **적재 검증:** 투영 동기화 preview → 승인 → 적용 → `neo4j_validate`. 벡터 15개 SHA 일치, 공통 근거 연결 수 = PG 대체 경로 결과 수, 기존 노드·관계 지문 불변.
2. **그림자 비교(유료 API 없음):** 현재 C(PG 하이브리드)와 신규 Neo4j 검색을 같은 질문에 함께 실행한다. 질문은 app_log 실제 요청 약 20건과 `search_eval` 50문항이고, 질문 벡터는 저장 벡터 대역을 쓴다. 비교 지문은 다음과 같다:
   - 후보 hits 순서, keyword_score, similarity(허용오차 1e-6), 병합 결과, 대상·제외 낱말
   - 선택 혜택 key(해석 stub이 app_log 선택을 재현), 상세 행, PDF 근거(evidence_id·쪽·원문)
   - 제외 판정, open_conditions, TERMS 항목·근거, `dp_related_to`
   - 답변 LLM 입력 context SHA, 해석·답변 프롬프트 바이트 동일성
3. **차이 처리:** 차이가 나면 전환하지 않는다. 원인을 데이터 공백(예: 공통 근거)·로직 차이·부동소수점 순위 동률로 분류해 보고한다.
4. **실제 API 확인(별도 승인):** 소수 질문으로 해석·답변 LLM과 질문 임베딩을 실제로 실행해 답변·검증 결과를 비교한다.
5. **Streamlit 전환:** 위 통과 후 라디오를 제거하고 AppTest·수동 확인을 한다. 기존 Streamlit UI 테스트 9건은 전환 전부터 실패 상태다(HEAD와 동일).
6. **속도 측정:** 전환 전후 같은 질문의 DB·임베딩·LLM 시간을 반복 측정하고 중앙값을 보고한다.

---

## 7. 예상 효과 (측정 단가 기반 추정)

C 혜택 1개 질문의 DB 시간:
- P1 후: PG 약 2.4 s + Neo4j 약 4.1 s
- P3 후: Neo4j 4문장(약 1.2 s, 실측은 §8)
- 단일 검색 후: Neo4j 약 4~5문장(카탈로그·후보·관계·상세·TERMS)으로 약 1.1~1.4 s, PG 0 s

P3 실측(성능 문서 §7)에서 단일 문장 1개는 약 270~380 ms였고, C의 Neo4j 4문장은 1.3~1.9 s, A의 2문장은 0.56~0.75 s였다.

질문 임베딩(실측 1.96 s, 첫 호출 연결 포함)과 LLM 2회(실측 7.85 s)는 남는다.

---

## 8. 위험과 결정 필요 사항

| 위험·결정 | 내용 | 대응 |
|---|---|---|
| 임베딩 적용 범위 | 15/116만 벡터 보유. 단일 검색으로 옮겨도 벡터로 찾을 수 있는 범위는 같다 | 범위 확대는 유료 임베딩 실행이 필요하므로 별도 승인 |
| 공통 근거 적재 | 근거 노드·관계가 크게 늘고 고아 판정·검증 규칙이 바뀐다. Codex 적재기와 조율해야 한다 | 투영 모듈 분리, preview·승인·지문 검사 |
| 교차 검증 시점 | 질문 시점 PG 대조가 없어진다 | 적재 후 `neo4j_validate` 통과를 서비스 조건으로. 정책 승인 필요 |
| 동일성 판정 경고 | SAME 외 판정 문구가 Neo4j에 없다 | 판정 상태 속성 적재 또는 경고 생략 결정 |
| 근사 인덱스 | HNSW는 순위가 달라질 수 있다 | 동등성 단계는 전수 비교. 인덱스 전환은 별도 비교 후 |
| 한국어 전문 검색 | Lucene 분석기 점수가 SQL 포함 규칙과 다르다 | 동등성 단계는 CONTAINS 재현. 개선은 평가 후 |
| 원장–그래프 시차 | PG 변경 후 동기화 전에는 Neo4j 검색이 옛 데이터다 | 등록 후 동기화 절차(관계 동기화와 같은 방식) 명문화 |
| Streamlit 테스트 | 기존 UI 테스트 9건이 이미 실패 중이다 | 전환 전 별도 정리 권장 |

---

## 8-1. 확정 아키텍처와 설계 기준 (2026-11-05 결정)

- PostgreSQL: 추출·정제·검증·관리 원장. Neo4j: 임베딩·키워드·그래프 관계·PDF 근거를 이용한 GraphRAG 검색 DB. Streamlit은 최종적으로 단일 하이브리드 검색.
- 원장–Neo4j 정합성 검증은 적재·동기화 단계에서 한다. 질문 실행 중 PostgreSQL 업무 데이터 조회는 제거한다.
- 공통 혜택 82개 PDF 근거를 보완한다(`dp_supported_by` 재사용 여부 확인 후). SAME·미확정 동일성 판정 상태와 경고를 보존한다.
- 기존 임베딩 15개는 재생성 없이 복사한다. 임베딩 없는 101개는 **전부** 같은 모델·차원·텍스트 규칙으로 생성 대상이다(비용 때문에 제외하지 않음). 생성은 별도 승인.
- 키워드 검색은 기존 SQL 문자열 매칭·순위와 같은 결과여야 한다. Vector Index와 정확도 검증을 포함한다. 캐시는 추가하지 않는다.

## 8-2. 임베딩·누락 근거 데이터 동기화 — 구현과 dry-run 결과 (운영 적재 전)

### 구현

| 파일 | 변경 |
|---|---|
| `neo4j_dry_run.py` (기준 그래프 변환기) | `load_snapshot`이 같은 READ ONLY 스냅샷에서 (1) 저장 임베딩·검색 텍스트를 원본 행에서 떼어 `search_projection`으로 보관하고(원본 행에서는 기존대로 제거), (2) 마지막 EMBED 실행(모델·ID), (3) 공통 혜택 근거 연결(GraphRAG 대체 조회와 같은 SQL)을 읽는다. `build`가 공통 혜택 근거 노드·`dp_in_chunk`·`dp_supported_by`, 임베딩 속성, 동일성 판정 속성을 만들고 건수를 원천에서 따로 세어 대조한다 |
| `neo4j_load_draft.py` | `node_properties`가 변환기의 별도 `search` 값을 속성에 합친다(**source_json에서는 읽지 않음** → 기존 정책 테스트 유지). `relationship_properties`가 공통 혜택 근거 관계에만 `link_source`·소유 공통 혜택·근거 ID를 둔다(기존 `has_common_benefit` 등 관계 속성 불변) |
| `neo4j_validation.cypher` / `.sql`, `neo4j_validate.py` | `evidence_links` 대조는 `card_evidence_link` 행(`link_source IS NULL`)만. 공통 혜택 근거는 새 비교 `common_evidence_links`(SQL 원천 ↔ Cypher)로 따로 대조 |
| 신규 `neo4j_search_projection_sync.py` | 원장 기준 증분 동기화. preview 기본. 허용 변경(공통 근거 노드·연결, 투영 속성) 외 차이가 있으면 중단. 쓰기 트랜잭션 1개 안에서 계획 재계산 → 승인 건수 대조 → UNWIND 일괄 쓰기 → 기준 그래프와 전체 대조 차이 0이면 commit. 인덱스는 별도 스키마 단계(`--create-indexes`)와 인덱스 상위 k = 전수 코사인 상위 k 검증. 임베딩 생성 계획(API 호출 없이 토큰 계산) |
| 신규 `test_neo4j_search_projection.py` | 16건: 변환(근거 노드·연결 속성·기존 근거 재사용·임베딩·판정 상태·오류), 적재 속성, 계획(허용·차단·원장 삭제 반영·모의 적용 차이 0), 트랜잭션(적용 후 재실행 쓰기 0건, 승인 불일치·차단 시 쓰기 0건), 쓰기 범위, 인덱스 구문, 임베딩 계획 규칙 |

**`dp_supported_by` 재사용 판단:** 재사용한다.
- 의미가 같다(소유 노드 → 원문 근거). 근거 주체는 GraphRAG 대체 조회와 같은 `ev_subject_cd='BNFT'`(혜택 자체의 근거), `ev_item_key='-'`다. 그래서 한도 질문의 근거 주체 필터(BNFT·ITEM)도 현재와 같게 동작한다.
- `card_evidence_link` 행이 아니라는 표시로 `link_source='COMMON_STG'`를 둔다. 검증기는 두 종류를 각각의 원천과 따로 대조한다.

### dry-run 결과 (운영 PostgreSQL·Aura 읽기 전용, 쓰기 0)

| 항목 | 현재 Aura | 동기화 후(모의 적용) | 변경 |
|---|---:|---:|---|
| 노드 | 937 | **1,635** | `dp_card_source_evidence` +698 (공통 혜택 근거 701건 중 3건은 이미 그래프에 있는 근거 재사용) |
| 관계 | 1,303 | **2,702** | `dp_in_chunk` +698, `dp_supported_by {link_source:'COMMON_STG'}` +701 |
| 속성 | — | — | 임베딩 보유 노드 15개(카드 혜택 9, 공통 혜택 6)에 `embedding`(1536 실수)·`embedding_dim`·`embedding_model`(`text-embedding-3-small`)·`embedding_run_id`(`20261105_000049`)·`search_text` 설정. 동일성 판정 1건(SAME)에 `brand_compare_status`·`brand_compare_issues`·`brand_compare_common_key` 설정 |
| 기존 노드·관계·속성 변경 | — | — | **0**(차단 항목 0, 모의 적용 후 기준 그래프와 전체 대조 차이 0) |
| 삭제 | — | — | 0 |
| 인덱스 | 0 (벡터·전문) | 2 | `dp_card_bnft_embedding`, `dp_card_common_bnft_embedding` (VECTOR, 1536, cosine). 데이터 적재 후 별도 단계 |

- 공통 혜택 근거 연결: 701 = PostgreSQL 대체 조회 경로 결과 수. 82개 공통 혜택 모두 근거가 생긴다(`common_benefits_without_direct_evidence` = 0).
- 동일성 판정: 현재 원천의 비교 행은 1건(SAME)이다. REVIEW·NO_COMMON 등 다른 상태도 같은 속성으로 보존하도록 구현·테스트했다.
- 기존 고아 문서 `20261103_000012`는 변경하지 않는다(원천 보류 문제로 별도 관리).

**현재 GraphRAG 답변 영향:** 없음.
- 현재 근거 조회 Cypher 3종은 공통 혜택 소유의 `dp_supported_by`를 읽지 않으므로, 공통 혜택 근거는 전환 전까지 지금처럼 PostgreSQL 대체 조회를 쓴다.
- 상세 조회의 `properties(b)`에 임베딩이 포함되지만, 답변 LLM 문맥(`benefit_context`)은 `source_json`만 읽으므로 LLM 입력은 같다.
- 상세 전송량은 임베딩 보유 혜택마다 약 30 KB 늘어난다. 전환 단계에서 상세 조회의 임베딩 제외를 반영할 예정이다.

**적용 후 다른 도구 영향:**
- 동기화 전까지는 기준 그래프에 투영이 포함되어 `neo4j_validate`와 `neo4j_relation_sync` 사전 검증이 "미적재 투영"을 차이로 보고한다(정상, 적용 후 해소).
- 전체 적재기(`neo4j_load_draft --apply`)도 같은 기준 그래프를 쓰므로 이후 재실행과 충돌하지 않는다.

### 임베딩 생성 계획 (API 미호출, EmbeddingService와 같은 규칙으로 계산)

| 대상 | 기존 재사용 | 기존 텍스트 변경(재생성 필요) | 생성 대상 | 토큰(cl100k_base) | 검토 표시 행 |
|---|---:|---:|---:|---:|---:|
| 카드 혜택 (34) | 9 | 0 | **25** | 2,540 | 11 |
| 공통 혜택 (82) | 6 | 0 | **76** | 8,339 | 0 |
| **합계** | **15** | **0** | **101** | **10,879** | 11 |

- 모델 `text-embedding-3-small`, 1536차원. 기존 15개와 같은 텍스트 생성 규칙(`BNFT_SEARCH_TXT_V1`)이다. 기존 15개는 저장 텍스트가 현재 규칙과 같아 재사용 가능하다.
- 예상 비용: 10,879 토큰 × $0.02/1M ≈ **$0.00022**(단가는 가정값, 실행 전 가격표 재확인).
- "검토 표시 행" 11건은 텍스트 생성기가 사람 확인 항목을 남긴 카드 혜택이다(예: 규칙 값 미기재로 원문 사용). 기존 EmbeddingService도 이 경우 텍스트를 만들고 검토 목록으로 보고한다.
- **116개 외 대상:**
  - 연회비(ANNUAL_FEE) 3개·TERMS 14개는 현재 벡터 검색 후보가 아니다. 연회비는 질문의 "연회비" 낱말로 구조 조회하고, TERMS는 선택 혜택에 붙는 근거다. 현재 동작을 유지하려면 추가 임베딩이 필요 없다.
  - 연회비를 벡터 후보로 넣을지는 검색 전환 단계에서 정할 업무 선택이다.
- **생성 후 대조 검증:** 생성 대상 101 = 성공 건수, PostgreSQL 벡터 보유 116, 투영 동기화 preview의 `embedding_reconciliation`(원장 벡터 116 = 동기화 후 Neo4j 벡터 116), 검증기 노드 속성 차이 0.
- **순서:** ① 임베딩 생성(유료, PostgreSQL 쓰기 — 승인 필요) → ② 투영 동기화 preview로 건수 재확인 → ③ 적재 → ④ 인덱스 생성·검증.

## 8-3. 운영 반영 결과 (2026-11-05, 승인 범위)

### PostgreSQL 임베딩 116건 신규 생성

| 항목 | 결과 |
|---|---|
| 실행 | `embedding_main --force --apply`, 실행 이력 `20261105_000050` SUCCEEDED (`run_param.force=true`, 차원 1536) |
| 생성·저장 | 카드 혜택 34/34, 공통 혜택 82/82, 실패 0 (검토 표시 11건 포함) |
| 독립 검증 | 116건 모두 벡터 1,536차원·단위 노름, 검색 텍스트 = 현재 규칙(`BNFT_SEARCH_TXT_V1`) 생성값, `update_date` 116건 갱신(실제 재기록) |
| 기존 15건 | 텍스트 동일, 새 벡터로 교체(기존 대비 코사인 0.9993~1.0009) |
| GraphRAG 모델 대조 기준 | 마지막 EMBED 실행 = `20261105_000050`(`text-embedding-3-small`) |
| 변경 컬럼 | `item_search_txt`·`item_embedding`(카드 혜택), `bnft_search_txt`·`bnft_embedding`·`update_user_id`(공통 혜택), `update_date`, `card_ai_run` 실행 이력 1행. DDL·그 밖의 업무 데이터 변경 없음 |
| 되돌림 자료 | 변경 전 116행 텍스트·벡터 백업(세션 임시 폴더 `pg_embedding_backup_before.json`) |

### 적재 전 중단과 승인 규칙 추가

- 첫 재검증 preview는 **차단 82건**으로 적재를 멈췄다. 원인: 임베딩 저장이 공통 혜택 82행의 `update_date`를 갱신했고, 변환기가 공통 혜택을 `SELECT *`로 읽어 그 값이 `source_json`에 들어 있다. 다른 필드 차이는 없음을 확인했다.
- 승인(A안): `dp_card_common_bnft`의 `source_json`이 **같은 키 구조에서 `update_date`만 다른 경우**에 한해 갱신한다(`audit_only_change`). 그 밖의 속성·구조 변경은 계속 차단한다. 테스트 4건을 추가했다.

### Neo4j Aura 적재 (트랜잭션 1개)

| 항목 | 적재 전 | 적재 후 |
|---|---:|---:|
| 노드 | 937 | **1,635** (+698 `dp_card_source_evidence`) |
| 관계 | 1,303 | **2,702** (+698 `dp_in_chunk`, +701 `dp_supported_by {link_source:'COMMON_STG'}`) |
| 임베딩 보유 노드 | 0 | **116** (카드 혜택 34 + 공통 혜택 82, 1536차원, `text-embedding-3-small`, run `20261105_000050`, `search_text` 모두 있음) |
| 동일성 판정 속성 | 0 | 1 (SAME) |
| `source_json` 갱신 | — | 82 (공통 혜택, `update_date`만) |
| 삭제 | — | 0 |
| `dp_related_to` | 6 | 6 (관계 동기화 재검사: unchanged 6, 변경 0) |
| 고아 문서 `20261103_000012` | 소유 0 | 소유 0 (변경 없음) |

- 직전 preview: 차단 0, 삭제 0, 모의 적용 후 차이 0. 그 계획 건수를 `--expect`로 넘겨, 트랜잭션 안에서 다시 계산한 계획과 같을 때만 쓰고 적용 후 기준 그래프와 차이 0을 확인한 뒤 commit했다.
- 적용 전 Aura 전체 `dp_` 노드·관계를 내보냈다(되돌림 참고용, `aura_preload_export.json`).

### 적재 후 검증

| 검증 | 결과 |
|---|---|
| `neo4j_validate` 기준 그래프 대조 | 노드·라벨·속성·관계·구조 **차이 0**(116개 벡터 값 포함), 범위 위반 0 |
| SQL ↔ Cypher | condition 117=117, card_evidence_link 250=250, **공통 혜택 근거 701=701**, 공통 적용 1=1, 규칙 대상 235=235 |
| 공통 혜택 근거 | 82/82 공통 혜택이 근거 연결 보유 |
| 기존 데이터 비의도 변경 (적용 전 내보내기와 대조) | 기존 노드 937개의 투영 외 속성·라벨 변경 0(승인된 `update_date` 82건 제외), 기존 관계 1,303개 변경·누락 0 |
| 재실행 | preview 계획 전부 0, 차단 0 |
| `ok` | false — 원인은 기존 고아 문서 1건뿐(source_preexisting) |

### 벡터 인덱스

| 인덱스 | 상태 | 설정 | 검증(저장 벡터마다 인덱스 상위 10 vs 전수 코사인 상위 10) |
|---|---|---|---|
| `dp_card_bnft_embedding` | ONLINE 100% | 1536, COSINE, HNSW m=16·ef_construction=100, quantization BINARY(Aura 기본) | 34건 중 30건 완전 일치. 4건은 **유사도가 같은 동률 항목의 순서만 다름**(구성 집합 34/34 일치, top-1 34/34 일치) |
| `dp_card_common_bnft_embedding` | ONLINE 100% | 같음 | 82/82 완전 일치 |

- 동률 예: 카드 23 `20261105_000102`와 카드 6 `20261104_000023`은 검색 텍스트가 같아 유사도가 1.0으로 같다(카드명은 검색 텍스트에 넣지 않는 규칙).
- 검색 전환 단계의 정확도 기준은 전수 코사인(116개)이다. 인덱스는 규모가 커질 때 쓴다.

### `properties(b)` 임베딩 반환 수정

- `graph_questions.cypher`의 `benefit_context`를 `apoc.map.removeKeys(properties(b), [투영 속성 8개])`로 바꿨다. 상세 응답의 `benefit`은 투영 전과 같은 속성만 담는다(기존 응답 계약 유지).
- 목록은 `PROJECTION_PROPS`와 같아야 하며 테스트로 대조한다.
- 확인: 적재 후 회귀에서 Neo4j 전송량이 적재 전과 같았다(예: 127 KB → 127 KB). 1536차원 벡터는 전송되지 않는다.

### GraphRAG 회귀 (A/B/C × 질문 6종, stub LLM·임베딩)

- 적재 전(신규 PostgreSQL 임베딩 반영 후)과 적재 후를 비교했다. **18/18 동일**: 해석·답변 프롬프트 바이트 동일, PDF 근거(evidence_id·쪽·원문)·상세·후보·제외·상태 동일.
- 테스트: Neo4j·검색 관련 142건 통과(8 건너뜀). `test_card_graphrag`는 HEAD와 같은 기존 Streamlit UI 실패 9건.

### 신규 임베딩 후 top-8에서 빠진 3개 사례 (분석만, 로직 변경 없음)

- 방법: 회귀 하네스와 같은 질문 벡터 대역(첫 선택 혜택의 저장 벡터)을 쓴다.
  - 변경 전: 실시간 키워드 SQL·Neo4j 관계 + 백업한 옛 벡터 15개로 벡터 단계를 다시 계산했다.
  - 변경 후: 실시간 검색(116개)이다.
- 실제 질문 임베딩이 아니므로 순위는 근사치다.

| 사례 | 실제 질문 | 실제 LLM이 고른 혜택 (변경 전 순위 → 후) | 빠진 혜택 | 정답에 필요한가 | 원인 |
|---|---|---|---|---|---|
| 1 (B) | DAILY 카드의 고정소비·정기결제 통합 할인한도는? | 고정소비 영역 5% 청구할인 1→1, **정기결제 50% 청구할인 7→16** | 정기결제 50% 청구할인 | **필요.** 두 혜택의 통합 한도를 묻는다 | B는 벡터만 쓴다. 후보군이 15→116개로 늘자 다른 카드(카드의정석 SHOPPING·더 심플)의 비슷한 "청구할인" 혜택이 앞섰다. 질문의 카드명·혜택명 낱말을 쓰지 않는다. 같은 질문의 C는 두 혜택을 모두 유지했다 |
| 2 (B) | ONE PICK STYLE 카드의 전월 실적 조건과 혜택을 알려줘. | 편의점·카페 1→2, 쇼핑 2→3, 대중교통 3→8, **놀이공원 8→순위 밖**(벡터 상위 20 밖) | ONE MORE 놀이공원 현장할인 | **필요.** 카드 혜택 전체와 실적 조건을 묻는다(놀이공원은 별도 실적 조건 20만원) | 카드의정석 SHOPPING "Two-in-One" 혜택 5개가 벡터로 들어왔다. 그중 하나는 관계 보정에서 질문 낱말 "ONE"이 대상명 "Two-in-One"에 **부분 문자열로 일치**해 1위로 올라갔다 |
| 3 (C) | (사례 2와 같은 질문) | 편의점·카페 2→2, 쇼핑 3→3, 대중교통 4→4, **놀이공원 5→10** | ONE MORE 놀이공원 현장할인 | **필요.** 사례 2와 같다 | "ONE"이 "Two-in-One"에 부분 일치해 SHOPPING 혜택들이 키워드 2점을 받고, 이제 벡터도 있어 RRF에서 키워드 4점·유사도 0.46인 놀이공원보다 앞섰다 |

**판단과 개선 후보(이번에는 구현하지 않음):**
1. **카드명 일치 시 같은 카드 혜택 우선.** 질문에 카드명이 있으면(사례 1~3 모두) 그 카드 혜택을 후보에서 빠뜨리지 않는다. top-k를 늘리는 것보다 정확하다.
2. **짧은 영문 낱말의 부분 일치 제한.** "ONE" ⊂ "Two-in-One"처럼 낱말 경계 없는 일치가 키워드 점수와 관계 보정을 왜곡한다. 키워드 SQL·`card.list`·`_rank_with_graph` 공통 문제다. 기존 결과 동일성 원칙과 충돌하므로 업무 결정이 필요하다.
3. **"카드 혜택 전체" 유형의 후보 범위.** 질문이 카드 혜택 전체를 물으면 카드의 혜택 수(ONE PICK 4개)보다 top-k가 작거나 같은 경우 누락 위험이 크다. 카드 단위 전체 포함 규칙을 검토한다.
4. **B(벡터 단독)** 는 후보군이 커지면서 취약하다. 단일 하이브리드 전환 방향과 맞는다.
5. **실제 질문 임베딩으로 재평가 필요.** 대역 벡터는 첫 선택 혜택 쪽으로 치우친다. 질문 수십 건의 임베딩 비용은 1센트 미만이지만 유료 호출이라 별도 승인이 필요하다.

## 9. 작업 순서 (각 단계 별도 승인)

1. (완료) P3 Neo4j 묶음 조회 구현·동등성 검증 → 결과 보고
2. 투영 동기화 설계 확정: 관계 유형·속성 이름·공통 근거 범위·경고 처리 결정
3. 투영 동기화 모듈 구현 → preview → **운영 Neo4j 적재 승인** → 적재·검증
4. `Neo4jBenefitSearch`·TERMS·공통 근거 경로 구현 → 그림자 비교 → 차이 0 확인
5. GraphRAG 단일 경로 전환(PG 검색 분기 제거)
6. Streamlit A/B/C 제거, 개발자 모드 단계별 시간 표시
7. 전환 전후 속도 측정(실제 API는 승인 범위 내)
