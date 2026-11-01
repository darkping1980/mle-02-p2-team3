# ONE PICK STYLE: PostgreSQL V6와 Neo4j 관계 비교

## 범위와 실제 결과 (2026-11-01)

개발 PostgreSQL `postgres.db_pipeline`, `card_id=2`, `card_doc_id=20261101_000002`, `policy_ver_id=20261101_000001` 기준이다. PDF 2쪽 전체는 `card_doc_page`·PAGE_V1 청크에 이미 저장됐다. 1쪽의 네 혜택과 조건·한도는 시험 데이터이고 2쪽은 부가서비스 유지·변경·고지 등 일반 안내다. 새 유료 추출 없이 2쪽 변경·고지 원문을 PENDING 근거로 연결했다. **전체 원문은 저장됐으나 모든 조항의 구조화·의미 검증이나 업무 승인까지 완료된 것은 아니다.** 2쪽의 나머지 해외 수수료·결제 안내 등은 페이지 원문으로 조회되지만 업무 엔티티로 정규화하지 않았다. 별도 혜택을 창작하지 않았다.

| 실제 테이블 | 전체 행 수 | 현재 역할 |
|---|---:|---|
| `card_product`, `card_product_doc`, `card_doc` | 각 1 | 상품, PENDING 상품·문서 관계, PDF 메타데이터 |
| `card_doc_page`, `card_doc_chunk` | 각 2 | 두 페이지 원문과 PAGE_V1 |
| `card_ai_run`, `card_ai_call` | 각 1 | 1쪽 재생 실행 PARTIAL 및 원본 응답. 재생은 추가 유료 호출이 아님 |
| `card_extr_stg` | 8 | 혜택 4, 카드 조건 4, 모두 PENDING_REVIEW |
| `card_source_evidence` | 31 | 1쪽 30, 2쪽 1; PENDING |
| `card_policy_version`, `card_bnft` | 1, 4 | DRAFT 정책과 미검토 혜택, 규칙 JSON 총 6개 |
| `card_limit_pool`, `card_policy_evidence` | 9, 41 | 9개 한도 및 원문 연결. 41은 서로 다른 근거 수가 아니라 연결 수 |
| `card_method_catalog` | 2 | `UNEXECUTABLE` 설명용 방법 계약; 실제 handler 아님 |
| `card_excl_item` | 0 | 원문 제외항목은 조건 텍스트로 보존; 정규화된 제외 개체는 미등록 |
| `card_bnft_common`, `card_common_bnft`, `card_common_policy_version`, `card_common_rule_evidence` | 각 0 | 공통 혜택 정책의 동일성이 확인되지 않아 등록하지 않음 |
| `common_code_grp`, `common_cd` | 44, 162 | 공통코드 사전 |

이번에 2쪽 청크 `20261101_000013`의 문자 1~763을 `card_source_evidence` `20261101_000061`로 삽입하고 정책 근거 `20261101_000041`에 연결했다. 승인 상태는 PENDING이다. 이전 시도 두 번은 문자열 처리 및 길이 검증 실패로 트랜잭션이 롤백됐고, 수정 후 단일 트랜잭션에서 문서 해시·DRAFT·인용 일치 검증을 거쳐 커밋했다. 최초 실측 LLM 응답과 기존 staging은 변경하지 않았다. 2쪽 근거 연결은 정책 전체의 승인이나 유효일 확정이 아니다.

## 관계와 SQL 검증

`card_product.card_id` → 정책 복합키 `(card_id,policy_ver_id)` → 혜택 복합키 `(card_id,policy_ver_id,card_bnft_id)`. `card_bnft.rule_list[]`에는 규칙 키, 대상, 조건식과 `pool_refs[].pool_id`가 들어간다. 풀은 `(card_id,policy_ver_id,pool_id)`로 조인한다. 조건식의 branch 간 OR, branch 내 atom 간 AND를 유지한다. `card_policy_evidence`는 정책·혜택·규칙·풀의 논리 키와 `evidence_id`를 연결하고, `card_source_evidence` → `(card_doc_id,page_no,card_doc_chunk_id)` → 페이지·문서 순으로 근거를 찾는다. 물리 FK는 없다.

실제 SELECT 결과: 혜택 4개, 규칙 6개, 풀 9개, 근거 31개, 연결 41개. 혜택 조건/규칙 JSON 검증 오류 0, 풀 tier 형식 오류 0, 정책 근거의 source 고아 0, 위치가 있는 근거 31/31의 청크 부분문자열 일치. `v_card_integrity_issue`는 `evidence_not_approved=31`만 반환하며 `method_not_in_catalog`, `pool_ref_orphan`, `common_cd_invalid`는 현재 결과에 없다. 위치 일치는 표의 행 연결 및 의미 검증과 다르다. 게이트의 31건은 미승인 상태를 숨기지 않고 남긴 결과다.

1쪽 표 검토: ONE PICK 일 1회/월 30회/월 5천원; STYLE 일 1회/월 10회/월 5천원. 대중교통 5%·월 1천원·전월 10만원 또는 최초 사용 등록 유예. 놀이공원 50% 현장할인·월 1회/연 2회·1인 1매·전월 20만원·최초 발급 월 미제공. PDF 2쪽은 부가서비스 변경 예외·고지 규정을 추가한다. 100원·500원 중첩 우선순위, 9개 풀의 CARD_MEMBER 집계, 정책 적용 시작일은 미확정이다. `valid_from=2026-03-30`은 출시일을 이용한 테스트 가정이다. staging의 대중교통 단일 AND 오류 및 V6 OR의 실적 제외 술어 의미는 남아 있다. PENDING 근거는 승인으로 바꾸지 않았다.

## 실제 PostgreSQL 조회

아래는 **DRAFT 진단용**으로 2026-11-01 실제 SELECT를 실행한 경로다. 운영 답변용 SQL이 아니다. 여러 질문을 같은 결과 집합에서 분석할 수 있다. `bnft_cond_expr IS NULL`만으로 전월 실적 없음이 원문 검증됐다고 단정하지 않는다.

```sql
-- 질문 1: 혜택 전체 (단순 관계 조회)
SELECT bnft_nm, bnft_type_cd, verification_status_cd
FROM db_pipeline.card_bnft WHERE card_id=2 ORDER BY bnft_nm;

-- 질문 2·3: 실적과 교통 유예. branch의 번호는 OR, atom은 AND
SELECT b.bnft_nm, br.ordinality AS branch_no,
       a.value->>'atom_key' AS atom_key, a.value->>'cond_raw_txt' AS 원문
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(coalesce(b.bnft_cond_expr->'branches','[]'))
  WITH ORDINALITY br(value,ordinality)
CROSS JOIN LATERAL jsonb_array_elements(br.value->'atoms') a(value)
WHERE b.card_id=2 AND a.value->>'cond_type_cd' IN ('SPEND_REQ','GRACE')
ORDER BY b.bnft_nm,br.ordinality;

-- 질문 4·6: 혜택별 한도 및 같은 풀을 참조하는 규칙 수
SELECT b.bnft_nm,p.pool_id,p.period_cd,p.cap_unit_cd,
       p.tier_list->0->>'limit_num' AS cap,
       count(DISTINCT r.value->>'rule_key') AS rule_count
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) r
CROSS JOIN LATERAL jsonb_array_elements(r.value->'pool_refs') ref
JOIN db_pipeline.card_limit_pool p
  ON (p.card_id,p.policy_ver_id,p.pool_id)=(b.card_id,b.policy_ver_id,ref.value->>'pool_id')
WHERE b.card_id=2
GROUP BY b.bnft_nm,p.pool_id,p.period_cd,p.cap_unit_cd,p.tier_list
ORDER BY b.bnft_nm,p.pool_id;

-- 질문 5: 정액/정률 및 결제 금액 기준
SELECT b.bnft_nm,r.value->>'rule_key' AS rule_key,
       r.value->>'value_num' AS value,
       r.value->'cond_expr'->'branches'->0->'atoms'->0->>'cond_min_amt' AS min_amt
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) r
WHERE b.card_id=2 ORDER BY 1,2;

-- 질문 7: 혜택에 직접 연결된 원문 (정책·풀 근거는 subject별 별도 조회 필요)
SELECT b.bnft_nm,e.page_no,e.quote_txt,e.approval_status_cd
FROM db_pipeline.card_bnft b
JOIN db_pipeline.card_policy_evidence pe
  ON (pe.card_id,pe.policy_ver_id,pe.card_bnft_id)=(b.card_id,b.policy_ver_id,b.card_bnft_id)
JOIN db_pipeline.card_source_evidence e ON e.evidence_id=pe.evidence_id
WHERE b.card_id=2 ORDER BY b.bnft_nm,e.page_no;
```

실행한 동일 JOIN의 subject별 근거 수는 BNFT 1쪽 27, POOL 1쪽 9, POLICY 1쪽 4·2쪽 1이다. 표의 첫 번째 atom만 꺼내는 5번은 **이 데이터의 진단 예제**이며 일반적인 OR/다중 atom 계산에 사용하면 안 된다. SQL은 JOIN과 JSONB 모두 지원한다. 이 사례의 다단 JSON 펼치기와 배열 위치 처리는 관계형 모델 일반의 필연이라기보다 V6가 조건·규칙·참조를 JSONB에 넣은 선택의 영향이다. 별도 정형 행이면 JOIN은 늘 수 있으나 atom 조회는 단순해질 수 있다.

## Neo4j 변환 초안 — 미실행

| PostgreSQL | 노드 / 관계 | 식별·의미 |
|---|---|---|
| 상품·정책판 | `(:Card)-[:HAS_POLICY]->(:Policy)` | 상품 ID와 정책 복합키, 상태·기간 유지 |
| 혜택·규칙 | `(:Policy)-[:HAS_BENEFIT]->(:Benefit)-[:HAS_RULE]->(:Rule)` | 상품·정책·혜택·rule_key 조합 |
| 조건식 | `(Benefit/Rule)-[:HAS_EXPR]->(:Expression)-[:HAS_BRANCH]->(:Branch)-[:HAS_ATOM]->(:Condition)` | branch OR / atom AND, 순서·negate·범위·미확정 상태 유지 |
| 대상·한도 | `(Rule)-[:TARGETS]->(:Target)`, `(Rule)-[:CONSUMES]->(:LimitPool)` | 풀은 정책+pool_id로 식별; 같은 금액이라고 병합하지 않음 |
| 근거 | `(Policy/Benefit/Rule/LimitPool)-[:SUPPORTED_BY]->(:Evidence)-[:IN_CHUNK]->(:Chunk)-[:ON_PAGE]->(:Page)-[:IN_DOCUMENT]->(:Document)` | subject/item 키·PENDING·문자 위치 보존; 같은 인용이라도 표 위치 의미 별도 확인 |

예: 위 SQL의 한도 질문과 대응하는 **제안 Cypher, 미실행**:

```cypher
MATCH (c:Card {card_id: 2})-[:HAS_POLICY]->(p:Policy)-[:HAS_BENEFIT]->(b:Benefit)
MATCH (b)-[:HAS_RULE]->(r:Rule)-[:CONSUMES]->(l:LimitPool)
RETURN b.name, l.pool_id, l.period, l.unit, l.value, count(DISTINCT r) AS rule_count
ORDER BY b.name, l.pool_id;
```

교통 예외 질문은 아래처럼 분기를 함께 반환한다. branch를 평탄화해 `(spend AND grace)` 또는 혜택 전체의 무조건 OR로 바꾸면 안 된다.

```cypher
MATCH (:Card {card_id: 2})-[:HAS_POLICY]->(:Policy)-[:HAS_BENEFIT]->(b:Benefit)
      -[:HAS_EXPR]->(:Expression)-[:HAS_BRANCH]->(br:Branch)-[:HAS_ATOM]->(a:Condition)
WHERE a.key IN ['transit_spend','transit_grace']
RETURN b.name, br.branch_no, a.key, a.raw_text ORDER BY br.branch_no;
```

PostgreSQL의 복합키·JOIN과 JSON 배열을 그래프는 명시적 관계로 연결하므로 다단 경로와 공유 대상은 시각적으로 탐색하기 쉽다. 반대로 상태·시간·고유성·원문 승인·조건식 해석은 그래프가 자동 보장하지 않는다. 단일 혜택과 숫자 비교는 SQL이 간단할 수 있고 그래프 복제·동기화도 비용이다. 동일 질문·동일 승인 데이터·동일 근거로 실행해 정확성과 비용을 비교하기 전에는 Neo4j 우월성을 주장할 수 없다. 벡터 RAG 비교는 아직 실행하지 않았다.

최종 사용자용 변환에는 승인 정책·혜택·규칙·문서 적용 및 evidence, 유효일, 미해결 상태와 무결성 검사를 모두 반영해야 한다. `v_card_bnft_rule_effective` LOCAL은 DRAFT를 자동 필터하지 않는다. 현재는 DRAFT 진단용 그래프 모델 초안까지만 가능하며, 실제 Neo4j 적재는 별도 승인과 테스트/서비스 분리가 필요하다.

## A7-4 최종 재조회 및 판정 (2026-11-01)

개발 DB `postgres.db_pipeline`을 읽기 전용으로 다시 조회한 결과 테이블별 행수는 위 표와 동일하다. 상품·문서·상품문서·정책 각 1, 혜택 4, 규칙 6(JSON 원소), 한도 9, 페이지·청크 각 2, 실행·호출 각 1, staging 8, source evidence 31, policy evidence 41, method catalog 2다. `common_code_grp` 44, `common_cd` 162, `card_excl_item`과 공통 혜택 4개 테이블은 각 0이다. 모든 행수는 테이블 전체 기준이며 이번 대상의 유일성을 뜻하는 일반 보장은 아니다.

| PDF 주요 조항 | 보존·구조화 상태 | 완료 판정 |
|---|---|---|
| 상품명·브랜드·발급대상·계좌·교통기능 | 상품·문서 및 페이지 1 보존. 모든 가입 제약이 업무 필드로 정형화된 것은 아님 | 부분 구조화; 발급조건 검색은 추가 확인 |
| ONE PICK·STYLE 대상, 100/500원, 일·월 한도 | 혜택·규칙·각 혜택별 풀에 DRAFT로 반영 | 값·표 행 확인; 구간 중첩 선택, 집계 기준, 직접 근거는 미해결 |
| 대중교통 대상·5%·전월 10만원·유예·월 1천원 | DRAFT 규칙·OR 분기·풀에 반영 | OR 존재 확인; 실적 제외와 서비스 제외 및 NOT 의미 검토 필요 |
| 놀이공원 대상·50% 현장할인·실적·발급월·횟수·1인1매 | DRAFT 조건·풀에 반영, 1인1매는 원문 텍스트 | 수치 확인; 사람당 단위의 정형 계약과 근거 미완료 |
| 실적 산정 제외와 서비스 제외 | 정책 또는 혜택·규칙 조건의 원문 텍스트, 페이지 1 보존 | 범위와 NOT의 구조적 의미가 완전히 검증되지 않음; 제외 마스터 0건 |
| 부가서비스 3년 유지·변경 예외·고지 | 페이지 2 전체 및 PENDING 정책 근거 1건 | 원문 보존; 사유·고지 절차별 구조화 미완료 |
| 해외 이용 환율·Mastercard 1%·해외서비스 US$0.5 | 페이지 2 원문 보존 | 발급 전 비용 비교에 유용하나 전용 정형 업무 데이터·근거 관계 미완료. 수수료를 혜택으로 분류하지 않음 |
| 출금·결제안내, 미성년자·후불교통 등 | 페이지 원문 보존 | MVP 검색 범위와 정형화 필요성 결정 전; 페이지 보존만으로 답변 검색 인덱스 구축을 뜻하지 않음 |

사용자에게 제공할 **MVP 전체 적재는 미완료**다. 구조 검증은 아래 확인 범위 내 완료, 의미 검증은 부분 완료다. 현 DRAFT는 격리된 개발용 그래프 변환 설계·시험 후보이나 실제 Neo4j 적재는 별도 승인 대상이며 승인된 서비스 데이터로 사용 불가하다.

### 실제 실행 결과: 7가지 질문

아래 항목의 SQL은 이 문서 앞의 실제 실행 SQL과 다음 보충 SQL이다. 전부 `card_id=2`의 DRAFT를 조회했으며 결과는 현재 저장값이다.

1. **혜택 전체·조건:** `card_bnft` 4건. ONE PICK·STYLE의 혜택 조건식은 NULL; 놀이공원은 실적·발급월·실적 제외·1인1매, 대중교통은 아래 OR. 공통 `policy_cond_expr`와 각 `rule_list[].cond_expr`는 별도 레이어이므로 혜택 조건식 NULL을 무조건 혜택으로 해석하면 안 된다. 테이블 단독 조회 뒤 JSONB를 전개한다.
2. **ONE PICK/STYLE 규칙·한도:** 둘 다 3,000 이상 100원, 10,000 이상 500원이며 선택 방식은 미확정. 각자 일 1회와 월 5,000원, 월 횟수는 각각 30/10이다. `card_bnft.rule_list`와 `card_limit_pool`을 풀 복합키로 JOIN하고 JSONB 배열 두 층을 전개한다.
3. **대중교통:** branch 1은 `transit_spend` AND `spend_exclusions`, branch 2는 `transit_grace`다. branch 간 OR. 별도 rule 조건의 `transit_exclusions`와 policy 공통 제외가 연결되는 해석은 의미 검토 필요. 조건 그룹 논리 자체와 JSON 중첩이 모두 복잡성 원인이다.
4. **규칙·구간:** 실제 6개 규칙은 ONE PICK 100/500, STYLE 100/500, 교통 5%, 놀이공원 50%. SQL의 첫 atom 진단 열은 이 샘플에서 3,000/10,000을 반환하며 범용 조건식 평가 결과가 아니다.
5. **공유·개별 한도:** 같은 혜택의 100원/500원 규칙은 각자 동일한 3개 풀을 참조한다. ONE PICK 풀 `...000001`~`...000003`과 STYLE 풀 `...000004`~`...000006`은 서로 다르다. 동일 5천원 액수만으로 카드 전체 공유로 간주하지 않는다. 각 풀의 CARD_MEMBER는 가정이다.
6. **근거:** 앞의 혜택 근거 JOIN은 27행을 반환했다. 예를 들어 교통 혜택 `20261101_000003` → policy evidence → source evidence `20261101_000049` → 문서 `20261101_000002`, 1쪽 문자 807~895의 등록 유예다. 31개 인용의 텍스트 위치가 청크와 일치하지만 표 행이나 근거 승인까지 입증하지는 않는다. 정책·풀 근거를 포함하려면 대상 유형에 따라 별도로 조회해야 한다.
7. **상태:** 아래 SQL 결과 DRAFT, 시작일 2026-03-30(시험 가정), 종료일 NULL, 혜택 PENDING_REVIEW 4건. 실제 승인 행만 찾는 필터는 이 정책을 제외한다.

```sql
-- 실제 실행: 정책과 혜택의 상태와 건수
SELECT p.policy_status_cd,p.valid_from,p.valid_to_excl,
       b.verification_status_cd,count(*)
FROM db_pipeline.card_policy_version p
JOIN db_pipeline.card_bnft b USING (card_id,policy_ver_id)
WHERE p.card_id=2
GROUP BY 1,2,3,4;

-- 실제 실행: 교통 조건의 OR branch와 내부 atom
SELECT br.ordinality AS branch_no, a.value->>'atom_key' AS atom,
       a.value->>'cond_type_cd' AS kind, a.value->>'negate_yn' AS negate,
       a.value->>'cond_raw_txt' AS raw_text
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.bnft_cond_expr->'branches')
  WITH ORDINALITY br(value,ordinality)
CROSS JOIN LATERAL jsonb_array_elements(br.value->'atoms') a
WHERE b.card_id=2 AND b.card_bnft_id='20261101_000003'
ORDER BY br.ordinality;

-- 실제 실행: JSON 형식 확인 (의미 검증 아님)
SELECT
 (SELECT count(*) FROM db_pipeline.card_bnft WHERE card_id=2
  AND (NOT db_pipeline.fn_valid_cond_expr(bnft_cond_expr)
       OR NOT db_pipeline.fn_valid_rule_list(rule_list,'LOCAL'))) AS invalid_benefits,
 (SELECT count(*) FROM db_pipeline.card_limit_pool WHERE card_id=2
  AND NOT db_pipeline.fn_valid_tier_list(tier_list)) AS invalid_tiers;
-- 결과 0, 0.  v_card_integrity_issue: evidence_not_approved 31건.
```

게이트에 `method_not_in_catalog`, `pool_ref_orphan`, `common_cd_invalid` 및 정책·혜택·근거 관련 다른 이슈는 나오지 않았다. 이는 구현된 게이트의 현재 결과이지 모든 논리 참조·업무 의미의 무오류 증명은 아니다. 실제 source evidence와 청크 JOIN에서 31/31의 인용 위치가 일치했다. `card_method_catalog` 2행은 실행 불가 테스트 계약이며 param_schema의 의미 검증까지 확인된 것은 아니다.

기존 추출 서비스의 단일 AND 생성 때문에 staging을 재생성해 자동 적재하면 오류가 재발한다. 원본과 기존 후보를 보존하고 검토자가 교정한 OR·근거·정정 전후와 검토 이력을 명시적으로 연결한 뒤 수동 검증하여 사용하는 절차가 필요하다. 현재의 `stg_review_note`만으로 불변 변경 이력을 보장한다고 확인하지 못했으므로 이번에는 후보 JSON을 덮어쓰거나 승인하지 않았다. 이 절차와 자동 적재 차단은 아직 구현되지 않았다.

V6 DDL 변경은 이번 검증으로 확정하지 않는다. 날짜 미상, 집계 기준 미상, 1인1매, 정정 이력과 2쪽 수수료 구조화는 기존 코드·JSON 계약으로 정확히 담을 수 있는지 검토 후 판단한다. Neo4j Cypher는 위 초안만 있고 실행·적재하지 않았다. GraphRAG와 벡터 RAG 간 성능도 아직 비교하지 않았다.

## A8 시범 변환 준비 및 동일 질문 비교

### 실제 대상과 환경 (2026-11-01)

PostgreSQL 재조회: 상품 1, 정책 1, 혜택 4, 규칙 6, 풀 9, 근거 31, 정책 근거 연결 41. 정책·혜택·규칙 JSON에서 조건식 8, branch 9, atom 15, 규칙→풀 참조 15개를 확인했다. 대상은 유형·이름의 고유 조합으로 19개이며 대상을 어떻게 동일시할지는 확정하지 않았다. 근거 연결의 실제 종류는 POLICY 5, BNFT 27, POOL 9다. 31개 근거와 41개 연결은 서로 다른 건수다. 조건·규칙별 직접 evidence 연결이 모두 존재한다고 가정하지 않는다.

`.env`의 Neo4j 설정과 기존 `recipe_recommender.neo4j_connection`의 인증서 검증 연결을 이용한 읽기 전용 접근은 성공했다. 대상 데이터베이스는 `6ac1f0f8`; 기존 `rcp_step` 6,717, `rcp` 1,156, `ingr` 275, `rcp_cat` 6개와 `RCP_USES` 10,428, `RCP_HAS_STEP` 6,717, `RCP_IN_RECIPE_CATEGORY` 1,156개가 이미 있다. 기존 그래프는 레시피 관련이므로 공유 범위에 주의해야 한다. 제안 이름공간 `a8_namespace='ONE_PICK_STYLE_A8'` 노드는 조회상 0개다. 최초 기본 드라이버 연결은 라우팅 실패했고, 프로젝트의 CA 검증 설정을 이용한 연결로 해결했다. `db.name()` 함수는 해당 DB에서 지원되지 않아 사용하지 않았다. 위 수치는 라벨별 집계로 중복 라벨이 있으면 노드 총수와 다를 수 있다.

### 변환 계약과 안전 범위

`Card → Policy → Benefit → Rule`, 조건이 존재하는 각 Policy/Benefit/Rule → Expression → Branch → Condition, Rule → Target 및 LimitPool, POLICY/BNFT/POOL → Evidence → Chunk → Page → Document로 연결한다. Expression은 **branch 사이 OR**, Branch는 **atom 사이 AND**, Condition에 `negate_yn`을 보존한다. 하나의 atom을 자격 판단 결과로 오인하지 않으며 실적 산정 제외와 서비스 제외를 별도 범위로 둔다. 현재 V6 DRAFT는 `[transit_spend AND spend_exclusions] OR [transit_grace]`로 저장돼 있어 범위·NOT 의미가 미검증임을 그래프에도 유지한다. 잘못된 staging AND를 변환 원본으로 쓰지 않는다.

각 노드는 공통 `a8_namespace`와 유형별 고정 라벨을 갖고, 식별은 원본 DB 식별자와 전체 상위 복합키를 포함한다: Policy `(card_id,policy_ver_id)`, Benefit은 여기에 `card_bnft_id`, Rule은 `rule_key`, LimitPool은 정책 키와 `pool_id`. Expression/Branch/Condition은 소유 엔티티 키·조건식 위치·branch 번호·atom 키를 포함한다. Evidence는 원본 `evidence_id`; 정책 근거 연결에는 `ev_link_id`, subject/item 유형 및 item 키를 보존해 같은 근거에 대한 서로 다른 연결을 잃지 않는다. Document/Page/Chunk도 원본 복합키를 보존한다. 조건의 텍스트와 NULL·미확정도 보존한다. 표현하기 어려운 원본 JSON은 직렬화 문자열로 보조 보존하고, 중첩 map을 Neo4j 속성에 그대로 저장할 수 있다고 가정하지 않는다.

`valid_from=2026-03-30`과 `CARD_MEMBER`는 테스트 가정이라는 표식을 함께 저장한다. `rule_select_cd=NULL`은 선택방식 미확정으로 유지하고, 1인1매는 원문 조건으로만 둔다. DRAFT/PENDING과 원문 미승인 상태를 모든 사용 경로에서 구별하며, 그래프 변환 자체가 업무 승인이 되지 않는다. 2쪽 수수료 등 원문만 보존된 내용은 정형 혜택인 것처럼 생성하지 않는다.

안전한 실행안은 별도 테스트 DB를 우선 선택하는 것이다. 현재 DB를 사용한다면 A8 이름공간에만 전용 라벨·속성을 부여하고 기존 노드와 `MERGE`하지 않는다. 모든 `MERGE` 키와 조회에 이름공간 및 복합키를 포함하고, 데이터 적재 전 고유성 제약 유무·중복 키를 검사한다. 제약 생성도 스키마 변경이므로 승인 범위에 명시한다. `MERGE`만으로 동시 재실행 중복 방지가 보장되지는 않는다. 변경된 원본의 오래된 관계를 정리하는 정책도 필요하며 무제한 `MATCH ... DETACH DELETE`는 사용하지 않는다. 삭제·재등록은 테스트 이름공간의 노드와 관계만 미리 집계하고, 외부 이름공간과 연결된 관계가 하나라도 있으면 중단하는 방식을 제안한다. 실제 삭제는 별도 승인과 범위 재확인이 필요하다.

### 다섯 질문: SQL 대 Cypher

아래 Cypher는 **계획한 모델에 대한 초안이며 미실행**이다. 앞 절의 SQL은 PostgreSQL 실제 실행 결과다. 두 결과의 동일성은 실제 변환·실행 후 키·상태·행수를 대조해야 하며 지금은 예상이다. 공통 모델과 풀의 재사용을 단순화하여 아래는 진단용 DRAFT만 찾는다.

1. **전체 혜택.** SQL: 위 `card_bnft WHERE card_id=2`는 4행. Cypher는 관계 두 단계를 탐색하며 예상 4행. SQL은 단일 테이블이라 이 질문에서는 더 짧다.

```cypher
MATCH (c:Card {a8_namespace:'ONE_PICK_STYLE_A8',card_id:2})-[:HAS_POLICY]->(p:Policy)-[:HAS_BENEFIT]->(b:Benefit)
RETURN b.card_bnft_id,b.name,b.verification_status ORDER BY b.name;
```

2. **교통 실적·유예.** SQL: 위 branch/atom JSONB 전개 결과 `[spend, spend_exclusions] OR [grace]`. Cypher: 위 기존 교통 예제에 이름공간 및 card_bnft_id 조건을 추가해야 한다. 조건 그룹이 노드로 드러나 경로 파악은 쉬울 수 있으나 OR과 NOT의 해석은 동일하게 필요하다. 현재 교통 예제는 spend/grace 두 atom만 반환하므로 원래 SQL의 전체 branch 결과와 동등하지 않다; 아래가 동일 범위다.

```cypher
MATCH (:Card {a8_namespace:'ONE_PICK_STYLE_A8',card_id:2})-[:HAS_POLICY]->(:Policy)-[:HAS_BENEFIT]->(b:Benefit {card_bnft_id:'20261101_000003'})-[:HAS_EXPR]->(:Expression)-[:HAS_BRANCH]->(br:Branch)-[:HAS_ATOM]->(a:Condition)
RETURN br.branch_no,a.key,a.kind,a.negate,a.raw_text ORDER BY br.branch_no,a.atom_seq;
```

3. **ONE PICK/STYLE 계산 규칙.** SQL: 위 `rule_list` 전개에서 각 100원·500원, 최소 3천/1만원. Cypher: Benefit→Rule→Expression→Branch→Condition. 양 모델 모두 미확정 선택 규칙은 결과에서 확정하지 않는다. `OPTIONAL MATCH`는 조건 없는 rule도 보존한다.

```cypher
MATCH (:Card {a8_namespace:'ONE_PICK_STYLE_A8',card_id:2})-[:HAS_POLICY]->(:Policy)-[:HAS_BENEFIT]->(b:Benefit)-[:HAS_RULE]->(r:Rule)
WHERE r.rule_key IN ['one_pick_100','one_pick_500','style_100','style_500']
OPTIONAL MATCH (r)-[:HAS_EXPR]->(:Expression)-[:HAS_BRANCH]->(:Branch)-[:HAS_ATOM]->(a:Condition)
RETURN b.name,r.rule_key,r.value_num,a.min_amt ORDER BY b.name,r.rule_key;
```

4. **월 한도·공유.** SQL: 위 JSON pool_refs 전개와 복합키 JOIN은 혜택별 9개 풀과 규칙 수를 반환한다. Cypher: 위 한도 예제에 `WHERE l.period='MONTH'`를 붙인다. 예상 월 풀은 6개이고 같은 혜택의 100/500 규칙만 각 풀을 함께 참조한다. 관계 자체는 Cypher가 직접적이지만 풀의 기간·집계 기준 검증은 별도다. 액수가 같은 풀은 병합하지 않는다.

5. **혜택→PDF 근거.** SQL: 위 `card_bnft`→`card_policy_evidence`→`card_source_evidence` JOIN 결과 27행이며 교통 유예 evidence `20261101_000049`, 1쪽 807~895. Cypher: 아래 직접 혜택 근거만 27개 관계를 기대한다. 풀·정책 근거 14개는 별도 경로다. 여러 근거 연결을 하나의 단순 관계로 합치지 않아야 SQL 행수와 비교 가능하다.

```cypher
MATCH (:Card {a8_namespace:'ONE_PICK_STYLE_A8',card_id:2})-[:HAS_POLICY]->(:Policy)-[:HAS_BENEFIT]->(b:Benefit)-[link:SUPPORTED_BY]->(e:Evidence)-[:IN_CHUNK]->(ch:Chunk)-[:ON_PAGE]->(pg:Page)-[:IN_DOCUMENT]->(d:Document)
RETURN b.name,link.ev_link_id,e.evidence_id,pg.page_no,e.start_pos,e.end_pos,e.approval_status ORDER BY b.name,e.evidence_id;
```

### 실행 준비 상태

모델·조회·대상 범위는 초안이다. 실제 변환 스크립트, 복합키·관계 동기화와 중복·격리 검증, PostgreSQL↔Neo4j 결과 동등성 테스트는 아직 작성·실행하지 않았다. 따라서 **즉시 적재 준비 완료라고 판단하지 않는다.** 우선 대상이 레시피 데이터가 있는 `6ac1f0f8`인지 별도 빈 개발 DB인지 결정하고, 그 대상에 한정한 적재 구현과 검증을 완성해야 한다. 이번에는 Neo4j에 CREATE/MERGE/DELETE, 제약 생성, 데이터 변경을 실행하지 않았다.

### A8 추가 확인: 실제 제약과 시범 변환 단위

기존 `src/recipe/recipe_recommender/neo4j_connection.py`의 `create_neo4j_driver()`는 프로젝트 환경을 읽고 `neo4j+s`에 대해 인증서 검증을 유지한 채 지정 CA 또는 `certifi`를 사용하는 드라이버를 제공한다. 카드 프로젝트에서도 같은 드라이버 설정을 재사용해 `src/common/neo4j_db_session.py`에 주입할 수 있다. 현재는 레시피 패키지에 구현돼 있으므로 카드 모듈이 해당 패키지에 직접 의존할지 공통 연결 설정으로 이전할지는 별도 구현 결정이며, 레시피 파일은 수정하지 않았다.

Neo4j `6ac1f0f8`의 `SHOW CONSTRAINTS` 읽기 결과는 `ingr_key(ingr_id)`, `rcp_cat_key(rcp_cat_id)`, `rcp_key(rcp_id)`, `rcp_seq_key(rcp_seq)`, `rcp_step_key(rcp_id,step_no)` 다섯 건으로 모두 레시피 노드 고유성 제약이다. 카드용 제약은 없으며, 고유성 제약 생성은 사용자의 별도 승인 전 실행하지 않는다. 레이블·관계 수는 위 환경 표의 이전 조회와 재조회가 일치했다. 기존 레시피 데이터와의 격리를 위해 카드 전용 레이블과 `a8_namespace=ONE_PICK_STYLE_A8`을 모든 노드에 부여하고 기존 `rcp` 등의 레이블이나 레시피 관계를 재사용하지 않는 방안을 선택한다.

다음은 **현재 원본과 아래 식별 규약으로 처음 생성할 때의 예상치**다. 같은 유형·이름의 대상은 해당 정책 내에서만 합치고 다른 정책·상품의 대상과는 합치지 않는다. 실제 그래프는 아직 존재하지 않으며 이 예상 수가 적재 결과가 아니다.

| 노드 | 예상 수 | 관계 | 예상 수 |
|---|---:|---|---:|
| Card / Policy / Benefit / Rule | 1 / 1 / 4 / 6 | HAS_POLICY / HAS_BENEFIT / HAS_RULE | 1 / 4 / 6 |
| Expression / Branch / Condition | 8 / 9 / 15 | HAS_EXPR / HAS_BRANCH / HAS_ATOM | 8 / 9 / 15 |
| Target / LimitPool | 19 / 9 | TARGETS / CONSUMES | 34 / 15 |
| Evidence / Chunk / Page / Document | 31 / 2 / 2 / 1 | SUPPORTED_BY / IN_CHUNK / ON_PAGE / IN_DOCUMENT | 41 / 31 / 2 / 2 |
| **합계** | **108** | **합계** | **168** |

`TARGETS` 34는 각 규칙의 대상 참조 수이고, 19는 `(정책 키, target_type_cd, target_nm)`의 서로 다른 값 수다. `SUPPORTED_BY` 41은 실제 POLICY 5, BNFT 27, POOL 9 연결이다. Evidence 31과 Chunk 2는 실제 source evidence가 참조하는 값이다. 한 관계의 자연 식별에 `ev_link_id`와 `ev_subject_cd`, `ev_item_cd`, `ev_item_key`를 보존한다. 모든 조건 atom에 직접 근거가 있다고 간주하거나 근거 관계를 새로 추정하지 않는다. 정책·문서 적용관계 자체의 승인 및 적용 기간은 원본을 보조 속성으로 보존할 대상이며, 위 관계 168개에는 이를 위한 별도 관계가 포함되지 않는다.

노드 식별자는 이름공간 + 엔티티 유형 + 원본 복합키를 사용한다. Condition 키는 소유자의 정책/혜택/규칙 키와 조건식 역할·branch 번호·atom 키를 포함한다. 고유키의 텍스트 직렬화에는 구분자 충돌을 방지하는 결정적 인코딩이 필요하다. Target은 위 정책 범위 복합키, Evidence는 evidence_id, Page·Chunk는 원본 문서 복합키다. 관계는 양 끝 키·관계 유형과 필요한 경우 `ev_link_id`/원본 참조 식별자를 포함해 재실행 시 같은 항목을 찾는다. 쓰기 전 중복 확인과 단일 실행을 강제해야 하며, **고유성 제약 없이 MERGE만으로 동시성 중복 방지는 보장되지 않는다.** 원본 삭제·변경에 대한 stale 관계 제거는 범위와 외부 연결을 검증한 뒤 별도로 처리한다.

이 모델은 원본 조건식의 계층·원문·상태와 공유 풀 식별을 보존하도록 정했지만, 실제 변환기·역변환 및 SQL↔Cypher 결과 비교를 아직 실행하지 않아 **무손실이 검증됐다고 할 수 없다.** 특히 Neo4j 속성은 중첩 JSON 객체를 직접 저장할 수 없으므로 파라미터·원본 조건식과 NULL/미존재 구분을 명시적 직렬화 규약으로 보존해야 한다. 교통 제외의 NOT과 실적 산정 범위, 100/500 선택, CARD_MEMBER, 1인1매, 정책 시작일은 검증 대기로 표시한다. 2쪽 수수료는 원문에 남기되 확인되지 않은 구조화된 혜택으로 생성하지 않는다.

실행 전 준비사항: 단일 PostgreSQL 읽기 스냅샷과 원본 상태 재확인, 네임스페이스/키 충돌과 외부 관계 사전 검사, 드라이런 건수 및 JSON·근거 연결 검증, 테스트 DRAFT 라벨·상태의 모든 조회 필터 확인, 동시 실행 방지 또는 승인된 고유성 제약 방안, 동일성 비교 테스트, 트랜잭션 실패 시 롤백과 제한된 정리 절차. 변환 코드와 이 검증은 아직 구현되지 않아 실제 CREATE/MERGE를 요청할 실행 계획이 완성됐다고 주장하지 않는다. Neo4j 실제 쓰기는 별도 승인 후에만 가능하다.

## A8-1 메모리 변환 드라이런 (2026-11-01)

`neo4j_dry_run.py --dry-run`은 `REPEATABLE READ READ ONLY` PostgreSQL 스냅샷에서 현재 상품·문서·정책과 혜택·한도·근거를 읽어 메모리상의 노드와 관계를 생성한다. staging을 읽지 않으며 Neo4j에는 접속하지 않는다. 전체 복합키를 JSON 배열로 인코딩해 구분자 충돌을 피하고, 원본 행·조건식·규칙·관계 내용을 `source_json`으로 보존한다. 정책 시작일과 CARD_MEMBER는 시험 가정, 모든 노드는 `test_only`다. 현재 구현은 계획된 그래프 적재기가 아닌 메모리 표현이다.

실제 드라이런 결과: `A8Card=1`, `A8Policy=1`, `A8Benefit=4`, `A8Rule=6`, `A8Expression=8`, `A8Branch=9`, `A8Condition=15`, `A8Target=19`, `A8LimitPool=9`, `A8Evidence=31`, `A8Chunk=2`, `A8Page=2`, `A8Document=1`. 합계는 **1+1+4+6+8+9+15+19+9+31+2+2+1=108**이다. 기존 표의 상세 합계도 108이며 103이라는 계산은 5개가 빠진 산술 결과다. 어떤 항목이 빠졌는지 원 계산 내역이 없어 특정할 수 없다.

관계별 실제 미리보기: HAS_POLICY 1, HAS_BENEFIT 4, HAS_RULE 6, HAS_EXPR 8, HAS_BRANCH 9, HAS_ATOM 15, TARGETS 34, CONSUMES 15, SUPPORTED_BY 41, IN_CHUNK 31, ON_PAGE 2, IN_DOCUMENT 2; **합계 168**. 경계 노드 고아 0, 근거·혜택·풀 수와 근거 관계 수 원본 일치. 정책·혜택·규칙 조건식의 branch와 atom이 그대로 들어가며, NOT은 원본 atom의 `negate_yn`을 보존한다. 동일 풀 ID는 동일 정책의 단일 노드를 가리킨다. 원본 JSON 보존과 구조 검사는 업무 의미의 정확성이나 그래프 역변환의 완전성을 입증하지 않는다.

`test_neo4j_dry_run.py`의 6개 테스트는 OR·NOT 보존, 풀 누락, 잘못된 근거 페이지, 중복 근거 관계, 고아 관계 및 복합키 경계 충돌을 검사하여 통과했다. 실제 Neo4j 쓰기·제약·Cypher 실행은 하지 않았다.

**제한:** 노드 속성은 현재 `source_json` 중심이므로 위 Cypher 초안의 `name`, `period`, `rule_key` 등 검색용 속성을 아직 제공하지 않는다. 정확한 SQL↔Cypher 비교, 파라미터 및 NULL 왕복 검증, 변경된 원본의 stale 관계 동기화, 동시 실행 보장, 네임스페이스 외부 관계 검사, 실제 Neo4j 쓰기 코드는 미구현이다. 전용 `A8*` 레이블과 이름공간·복합키는 레시피 노드와 분리한다. 실제 적재 전 해당 키의 고유성 제약 또는 다른 동시성 보장과 대상 DB/정리 절차는 별도로 결정·승인해야 한다. 즉 현재 108/168은 적재 실행물의 완성이 아니라 검증된 메모리 미리보기 결과다.

## 레시피 백업 및 카드 DB 전환 준비 (2026-11-01)

읽기 전용 조회: Neo4j `6ac1f0f8` 노드 8,154, 관계 18,301. 레이블은 `rcp` 1,156, `rcp_step` 6,717, `ingr` 275, `rcp_cat` 6; 관계는 `RCP_USES` 10,428, `RCP_HAS_STEP` 6,717, `RCP_IN_RECIPE_CATEGORY` 1,156. 다른 레이블이거나 라벨 없는 노드, 레시피 외 유형이나 외부 노드가 연결된 관계는 현재 조회 0. 이름과 구성에 따른 판단이며 모든 데이터의 업무 소유권을 완전히 증명하지 않는다.

백업은 `src/data/backup/neo4j_recipe_a8_20261101_111009/`에 있다. `nodes.jsonl`, `relationships.jsonl`에 elementId·레이블/유형·모든 속성·양 끝 elementId를, `constraints.json`, `indexes.json`에 DDL 메타데이터를 보관했다. 두 번째 전체 라이브 조회의 정렬된 모든 행 해시가 파일 해시와 일치했다. 파일에서 고유 노드 ID 8,154·관계 ID 18,301 및 관계 끝점 누락 0을 재확인했다. 당시 속성 타입은 문자열·정수·실수·배열이었다. `RESTORE_README.md`는 임시 원본 키를 이용한 별도 빈 DB 복원 절차이며 **실제 복원은 수행하지 않았고 자동 복원 스크립트도 아니다.** 읽기 재조회 사이 변경 감지는 했지만 장기적인 백업 일관성이나 완전한 복원 성공을 보장하지 않는다. 백업은 Git에 추가하지 않는다.

삭제 후보는 위 4개 레시피 레이블의 노드 8,154와 그 사이 관계 18,301, 고유성 제약 `ingr_key`, `rcp_cat_key`, `rcp_key`, `rcp_seq_key`, `rcp_step_key`, 독립 인덱스 `ingr_nm_norm_idx`, `rcp_nm_idx`다. 제약 소유 인덱스 5개는 제약 제거 시 함께 제거되므로 별도로 DROP하지 않는다. DB 공통 NODE/RELATIONSHIP LOOKUP 인덱스 2개는 보존한다. 삭제 직전 전체 유형·수·외부 관계 및 백업 해시를 다시 확인하고 차이가 있으면 중지한다. 아래는 **검토용이며 미실행**, 사전 검사와 실제 삭제는 쓰기 차단·동시 변경 방지 여부까지 별도 확인해야 한다.

```cypher
// 레시피 레이블 외 노드, 외부 관계, 중복/복수 레이블 등이 없다면 승인 후에만 실행
MATCH (n) WHERE size(labels(n)) = 1
  AND labels(n)[0] IN ['rcp','rcp_step','ingr','rcp_cat']
DETACH DELETE n;
DROP CONSTRAINT ingr_key;
DROP CONSTRAINT rcp_cat_key;
DROP CONSTRAINT rcp_key;
DROP CONSTRAINT rcp_seq_key;
DROP CONSTRAINT rcp_step_key;
DROP INDEX ingr_nm_norm_idx;
DROP INDEX rcp_nm_idx;
```

`neo4j_load_draft.py`는 현재 스냅샷을 메모리 변환 후 기본 실행에서 PREVIEW만 출력한다. `--apply`는 별도 확인 문자열과 대상 DB명, 미리 생성된 `A8Test(namespace,key)` 고유성 제약, 빈 시험 네임스페이스를 요구한다. 실제 쓰기는 호출하지 않았다. 노드는 `A8Test`와 `A8*` 타입별 레이블, 원본 복합키·`source_json`·시험용 표시를 갖고 관계는 `A8_*` 타입·원본 관계 속성을 보존한다. 기존 레시피는 일절 MATCH 대상으로 삼지 않는다. 관계와 노드를 단일 트랜잭션에서 쓰고 연결된 노드가 없으면 오류로 롤백한다. 이미 시험 네임스페이스가 비어 있지 않으면 재실행을 거부해 임의 삭제·중복 적재를 방지한다. 관계 동기화와 동시 실행 방지는 미구현이므로 승인 후에도 단일 실행이 필요하다.

필요한 카드 고유성 제약 제안은 `CREATE CONSTRAINT a8_test_key FOR (n:A8Test) REQUIRE (n.namespace,n.key) IS UNIQUE` 한 건이다. 제약 생성은 쓰기이므로 별도 승인 범위다. PREVIEW에서 원본 노드 108·관계 168 확인; 드라이런 및 로더 Mock 테스트 8개 통과. 실제 Cypher/제약의 실행 검증, 복원 테스트, SQL↔그래프 결과 대조, 재실행·동시성 시험은 미실행이어서 승인만으로 즉시 운영 적재가 검증된 것은 아니다. 삭제와 카드 적재는 별도 승인·별도 단계다.

## A8 실제 적재 및 조회 (2026-11-01)

사용자 승인 후 Neo4j `6ac1f0f8`에서 삭제 직전 원본 노드·관계 전체 해시가 백업과 일치하고 노드 8,154·관계 18,301 및 레이블·제약·인덱스가 확인된 기존 레시피 범위와 같음을 확인했다. 노드를 500건씩 삭제하고 레시피 제약 5개·독립 인덱스 2개를 제거했다. 공통 LOOKUP 인덱스 2개는 유지했다. 백업과 미실시된 실제 복원 시험의 제한은 위 절에 있다.

카드 제약 `a8_test_key` (`A8Test(namespace,key)`)를 생성하고 `neo4j_load_draft.py`로 시험 스냅샷을 적재했다. 동일 명령을 **순차적으로 한 번 더** 실행해 두 번 모두 108 노드·168 관계이고 중복 없이 성공했다. 복합키 고유 제약은 노드 중복을 방지하지만 관계 동시 실행·변경 데이터의 stale 관계 동기화는 구현하지 않았으므로 순차 실행과 원본 동일성 확인이 필요하다. 대상 데이터는 `A8Test` 및 `A8*` 라벨·`A8_*` 관계로 격리된 시험 데이터다.

실제 PostgreSQL 스냅샷에서 메모리 변환한 노드 108개와 Neo4j의 키·라벨·원본 JSON을, 관계 168개는 키·시작/끝 노드 키·유형·원본 JSON을 비교해 불일치 0이었다. 키·연결 건수와 원본 JSON에 대한 비교이며, 모든 그래프 속성의 왕복·업무 의미 완결성까지 보증하지 않는다. 정책 DRAFT, 혜택 PENDING_REVIEW, 원문 PENDING과 시작일·한도 집계 시험 가정은 `source_json` 및 가정 표시로 유지한다. 결과를 사용자용 확정 데이터로 내보내면 안 된다. Neo4j 노드 108, 관계 168, 제약 1, 인덱스는 제약 소유 RANGE 1 및 기존 LOOKUP 2다. `test_neo4j_dry_run`과 `test_neo4j_load_draft` 8개 통과.

아래는 실제 실행한 Cypher다. 이전 절의 `Card`·`HAS_POLICY` 등은 설계 초안이며, 실제 라벨과 관계는 아래처럼 `A8` 접두사를 쓴다. 모든 데이터는 DRAFT 시험용이다.

```cypher
// 1. 상품→혜택: 4개, 모두 PENDING_REVIEW
MATCH (:A8Card)-[:A8_HAS_POLICY]->(:A8Policy)-[:A8_HAS_BENEFIT]->(b:A8Benefit)
RETURN b.card_bnft_id AS id,b.name AS name,b.verification_status AS status ORDER BY id;

// 2. 혜택→계산 규칙: 6개
MATCH (b:A8Benefit)-[:A8_HAS_RULE]->(r:A8Rule)
RETURN b.card_bnft_id AS benefit,r.rule_key AS rule,r.value_num AS value ORDER BY benefit,rule;

// 3. 대중교통 분기: 1번 spend 및 spend_exclusions, 2번 grace
MATCH (b:A8Benefit {card_bnft_id:'20261101_000003'})-[:A8_HAS_EXPR]->(:A8Expression)
      -[:A8_HAS_BRANCH]->(br:A8Branch)-[:A8_HAS_ATOM]->(a:A8Condition)
RETURN br.branch_no AS branch,a.key_name AS atom,a.negate AS negate ORDER BY branch,atom;

// 4. 혜택별 풀과 참조 규칙 수: 9개 풀
MATCH (b:A8Benefit)-[:A8_HAS_RULE]->(r:A8Rule)-[:A8_CONSUMES]->(p:A8LimitPool)
RETURN b.card_bnft_id AS benefit,p.pool_id AS pool,p.period AS period,p.unit AS unit,
       p.value AS cap,count(DISTINCT r) AS rules ORDER BY pool;

// 5. 대중교통→근거→원문 페이지: PENDING 8건
MATCH (b:A8Benefit {card_bnft_id:'20261101_000003'})-[r:A8_SUPPORTED_BY]->(e:A8Evidence)
      -[:A8_IN_CHUNK]->(:A8Chunk)-[:A8_ON_PAGE]->(p:A8Page)-[:A8_IN_DOCUMENT]->(d:A8Document)
RETURN e.evidence_id AS evidence,p.page_no AS page,e.start_pos AS start,e.end_pos AS end,
       e.approval_status AS status ORDER BY evidence;

// Neo4j Browser 그래프 시각화용: 실행 시 경로를 그래프로 표시할 수 있다.
MATCH p=(:A8Card)-[:A8_HAS_POLICY]->(:A8Policy)-[:A8_HAS_BENEFIT]->(:A8Benefit)
RETURN p;
```

실제 조회에서 ONE PICK 월 30회·5,000원과 STYLE 월 10회·5,000원은 서로 다른 풀이고, 각 혜택의 100/500원 규칙 2개가 해당 풀들을 참조한다. 교통 유예 원문 근거 `20261101_000049`는 1쪽 807~895 위치·PENDING으로 연결됐다. 이는 앞 절의 PostgreSQL SELECT 결과와 같은 값이다. SQL에서는 `rule_list`·`pool_refs` JSONB 전개와 복합키 JOIN이 필요했고, Cypher는 명시된 관계를 따라간다. 단순 혜택 목록은 SQL 단일 테이블 조회도 간결하다. 실제 관계 시각화 UI 및 다른 팀원의 계정 접속은 확인하지 않았다.

현재 정책 시작일과 CARD_MEMBER는 시험 가정, 100원·500원 선택, 교통 제외의 NOT 및 실적 산정 범위, 1인1매 정형 의미와 원문 승인 상태는 미해결이다. 정책·조건 상태의 상세 원본은 `source_json`에서 확인한다. `v_card_bnft_rule_effective`와 마찬가지로 위 진단용 Cypher에는 승인 필터가 없으므로 최종 답변에 그대로 사용하지 않는다. LLM 호출·PostgreSQL 변경·Git push는 하지 않았다.

## A10-3 재동기화 후 구조 (2026-11-01)

이 절이 최신 상태다. 앞 절의 108·168과 근거 41건은 당시 기준이다. 의미 분석은 `A10_V6_NEO4J_STRUCTURE_ANALYSIS.md`, 보정 이력은 `A10_1_DATA_CORRECTION_PLAN.md`를 따른다.

| 항목 | PostgreSQL | Neo4j | 대조 결과 |
|---|---:|---:|---|
| 노드 / 대응 행 | 혜택 4, 규칙 6, 풀 9, 근거 31 | 108 | 키·라벨·`source_json` 차이 0 |
| 관계 | - | 189 | 키·유형·끝점·`source_json` 차이 0 |
| 조건 atom | 15 | 15 | SQL·Cypher 일치 |
| 근거 연결 | 62 | 62 (`A8_SUPPORTED_BY`) | SQL·Cypher 일치 |

| 근거 연결 주체 | 건수 |
|---|---:|
| 혜택 | 34 |
| 규칙 | 11 |
| 한도 풀 | 9 |
| 정책 | 8 |

조건 atom 15개 모두 조건 단위 근거가 있다.

### SQL과 Cypher 파일

| 구분 | 파일 | 읽는 방법 | 실행 |
|---|---|---|---|
| 업무 SQL | `document_repository.sql`, `extraction_repository.sql` | `PostgresDbSession` mapper | `select_list` |
| 검증 SQL | `neo4j_validation.sql` | `PostgresDbSession` mapper | `select_list` |
| 스냅샷 SQL | `neo4j_dry_run.py` 안의 문자열 | 직접 | `load_snapshot`, 읽기 전용 스냅샷 |
| 검색 Cypher | `graph_questions.cypher` | `Neo4jDbSession().mappers` | `Neo4jSearch._query` |
| 검증 Cypher | `neo4j_validation.cypher` | `Neo4jDbSession().mappers` | `neo4j_validate`, `neo4j_load_draft` |
| 적재 Cypher | `neo4j_load_draft.py`의 `MERGE` | 직접 | `write_transaction` |

```text
검색: Streamlit → LangGraph → neo4j_search.py → graph_questions.cypher → Neo4j
적재: db_pipeline → PostgreSQL 조회 → 변환기 → Neo4j 적재 쿼리 → Neo4j
대조: neo4j_validate.py → neo4j_validation.sql + neo4j_validation.cypher → 차이 보고
```

`neo4j_validation.condition_structure`와 `evidence_links`는 SQL과 Cypher에 같은 이름으로 있어 두 DB의 결과를 직접 비교할 수 있다. `.sql`은 DBeaver에서 그대로 실행한다. `.cypher`의 `$ns`는 DBeaver JDBC에 값을 줄 방법이 없어 `42001`이 나므로 `$ns`를 `'ONE_PICK_STYLE_A8'`로 바꿔 실행한다. 검색 쿼리는 터미널 `QUERY` 블록이나 검증 화면에서 값이 들어간 Cypher를 복사한다.
