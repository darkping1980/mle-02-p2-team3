# A10 PostgreSQL V6·Neo4j 데이터 구조 분석

기준: 2026-11-01. 대상: `card_id=2`, `policy_ver_id=20261101_000001`, Neo4j `namespace=ONE_PICK_STYLE_A8`.

> **A10-2 갱신:** 근거 037과 P1·P2·P3가 PostgreSQL에 반영됐고 변환기는 RULE 연결을 지원한다. 최신 상태는 `A10_1_DATA_CORRECTION_PLAN.md`를 따른다. 아래 본문은 A10 분석 시점 기준이며, Neo4j는 재적재 전까지 그 시점 값을 유지한다.

**A10 분석은 전부 읽기 전용으로 수행했다.** PostgreSQL은 `SET TRANSACTION READ ONLY`, Neo4j는 `READ_ACCESS` 세션을 사용했고 데이터·DDL·공통코드를 변경하지 않았다. 아래 변경안은 모두 제안이며 실행 전 승인이 필요하다.

원문 자료는 두 가지다.

| 자료 | 파일 | DB 적재 |
|---|---|---|
| 상품설명서 | `체크_ONEPICKSTYLE하나체크카드_상품설명서(공식PDF,URL추정확인)_15650_20260429.pdf` | 적재됨(`card_doc_id=20261101_000002`, 2쪽) |
| 웹 상품 상세 | `체크_ONEPICKSTYLE하나체크카드_웹페이지변환PDF_상품상세(모바일)_18899.pdf` | 미적재 |

표의 행·셀 대응은 상품설명서 1쪽을 이미지로 렌더링해 직접 확인했다. 웹 상세는 텍스트 검색만 했다. 상품 약관은 저장소에 없다.

## 1. 결론

- **PostgreSQL↔Neo4j 정합성은 양호하다.** 혜택 4건의 조건 atom과 근거 연결을 SQL·Cypher로 비교한 결과 불일치 0이다. 노드 108, 관계 168도 유지된다.
- **문제는 두 DB의 불일치가 아니라 PostgreSQL 값의 의미다.** 변환이 정확해서 원본의 의미 문제가 Neo4j에도 그대로 옮겨졌다.
- **필수 DDL 변경은 찾지 못했다.** 7개 항목 모두 현행 V6로 표현할 수 있다. 다만 미확정 상태 저장 방식과 게이트에는 검토할 점이 있다.
- **원문으로 확정할 수 없는 업무 규칙이 4개 있다.** 100원·500원 적용 방식, 한도 집계 단위, 최초 발급 월의 기준, 1인 1매의 범위다. 두 자료 모두에 답이 없어 카드사 확인이나 약관이 필요하다.

## 2. 구조 대응표

### 저장 위치

| 업무 개념 | PostgreSQL V6 | Neo4j | 차이 |
|---|---|---|---|
| 카드 | `card_product` | `A8Card` | 속성 대부분이 `source_json` |
| 정책판 | `card_policy_version` | `A8Policy` | `valid_from_is_assumption`은 Neo4j에만 있음 |
| 공통 조건 | `policy_cond_expr` JSONB | `A8Policy-[A8_HAS_EXPR]->A8Expression` | JSONB가 노드로 분해됨 |
| 혜택 | `card_bnft` 행 | `A8Benefit` | `rule_select_cd`는 `source_json`에만 있음 |
| 혜택 조건 | `bnft_cond_expr` JSONB | `A8Benefit-[A8_HAS_EXPR]->...` | 같음 |
| 규칙 | `rule_list[]` JSONB 원소 | `A8Rule` | PK 없는 JSON 원소가 노드가 됨 |
| 규칙 조건 | `rule_list[].cond_expr` | `A8Rule-[A8_HAS_EXPR]->...` | 같음 |
| 대상 | `rule_list[].target_list[]` | `A8Rule-[A8_TARGETS]->A8Target` | 규칙별 복제 34건이 고유 노드 19개로 합쳐짐 |
| 한도 연결 | `rule_list[].pool_refs[]` | `A8Rule-[A8_CONSUMES]->A8LimitPool` | 논리 키 참조가 실제 관계가 됨. `pool_role_cd`는 관계의 `source_json`에만 있음 |
| 한도 | `card_limit_pool` 행, `tier_list` JSONB | `A8LimitPool` | `tier_list[0].limit_num`이 `value` 속성이 됨 |
| 근거 연결 | `card_policy_evidence` 행 | `-[A8_SUPPORTED_BY]->` | 연결 행이 관계가 됨. `ev_item_key`는 문자열 그대로 |
| 원문 인용 | `card_source_evidence` | `A8Evidence` | 값 같음 |
| 문서 계층 | `card_doc_chunk`, `card_doc_page`, `card_doc` | `A8Chunk`, `A8Page`, `A8Document` | 복합키가 관계가 됨 |

### 조건식 표현

```text
PostgreSQL: card_bnft.bnft_cond_expr
{"branches":[{"branch_no":1,"atoms":[{transit_spend},{spend_exclusions}]},
             {"branch_no":2,"atoms":[{transit_grace}]}]}

Neo4j:      (A8Benefit)-[A8_HAS_EXPR]->(A8Expression)
              ├-[A8_HAS_BRANCH]->(A8Branch 1)-[A8_HAS_ATOM]->(transit_spend), (spend_exclusions)
              └-[A8_HAS_BRANCH]->(A8Branch 2)-[A8_HAS_ATOM]->(transit_grace)
```

둘 다 branch 사이 OR, atom 사이 AND, `negate`로 NOT이다. **그래프의 관계에는 AND/OR 의미가 없다.** 해석 규약을 쿼리나 코드가 알아야 하는 점은 JSONB와 같다.

### 검색 속성으로 승격되지 않은 값

아래 값은 Neo4j에서 `source_json` 문자열 안에만 있어 Cypher로 필터할 수 없다.

| 노드·관계 | 값 |
|---|---|
| `A8Condition` | `cond_basis_cd`, `cond_max_amt_excl`, `cond_status_cd`, `excl_raw_txt`, `predicate_method_cd` |
| `A8Benefit` | `rule_select_cd`, `bnft_type_cd` |
| `A8Rule` | `value_unit_cd`, `calc_method_cd`, `rule_priority`, `predicate_state_cd`, `rule_status_cd` |
| `A8LimitPool` | `pool_scope_cd`, `aggregation_key_cd` |
| `A8_CONSUMES` | `pool_role_cd` |

## 3. 대중교통 혜택 SQL·Cypher 비교

조건식, 한도, 근거가 모두 있는 `20261101_000003`을 선택했다. 아래는 실제 실행 결과다.

### 조건

```sql
-- 혜택 조건. 정책·규칙 조건도 같은 방식으로 UNION ALL 해서 조회했다
SELECT 'BNFT' AS owner, br.value->>'branch_no' AS branch, a.value->>'atom_seq' AS seq,
       a.value->>'atom_key' AS atom, a.value->>'cond_type_cd' AS type,
       a.value->>'cond_basis_cd' AS basis, a.value->>'cond_min_amt' AS min_amt,
       a.value->>'negate_yn' AS negate
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.bnft_cond_expr->'branches') br(value)
CROSS JOIN LATERAL jsonb_array_elements(br.value->'atoms') a(value)
WHERE b.card_id=2 AND b.card_bnft_id='20261101_000003';
```

```cypher
MATCH (p:A8Policy {namespace:$ns})-[:A8_HAS_BENEFIT]->(b:A8Benefit {namespace:$ns,card_bnft_id:$id})
OPTIONAL MATCH (b)-[:A8_HAS_RULE]->(r:A8Rule {namespace:$ns})
WITH p, b, collect(r) AS rules
UNWIND [p,b]+rules AS owner
MATCH (owner)-[:A8_HAS_EXPR]->(:A8Expression)-[:A8_HAS_BRANCH]->(br:A8Branch)-[:A8_HAS_ATOM]->(a:A8Condition)
RETURN owner.rule_key AS rule_key, br.branch_no AS branch, a.atom_seq AS seq,
       a.key_name AS atom, a.kind AS type, a.min_amt AS min_amt, a.negate AS negate
ORDER BY rule_key, branch, seq;
```

| 소유자 | branch·seq | atom | SQL 유형·기준·최소·NOT | Cypher 유형·최소·NOT | 일치 |
|---|---|---|---|---|---|
| 혜택 | 1·1 | `transit_spend` | SPEND_REQ, PREV_MONTH_SPEND, 100000, false | SPEND_REQ, 100000, False | 일치, 기준은 Cypher에 없음 |
| 혜택 | 1·2 | `spend_exclusions` | SPEND_EXCL, PREV_MONTH_SPEND, NULL, true | SPEND_EXCL, None, True | 일치 |
| 혜택 | 2·1 | `transit_grace` | GRACE, PREV_MONTH_SPEND, NULL, false | GRACE, None, False | 일치 |
| 정책 | 1·1 | `common_service_exclusion` | BNFT_EXCL, NULL, NULL, true | BNFT_EXCL, None, True | 일치 |
| 정책 | 1·2 | `common_channel` | PAYMENT_METHOD, NULL, NULL, false | PAYMENT_METHOD, None, False | 일치 |
| 정책 | 1·3 | `merchant_classification` | MERCHANT_RULE, NULL, NULL, false | MERCHANT_RULE, None, False | 일치 |
| 규칙 | 1·1 | `transit_exclusions` | BNFT_EXCL, NULL, NULL, true | BNFT_EXCL, None, True | 일치 |

### 한도

```sql
SELECT r.value->>'rule_key' AS rule_key, ref.value->>'pool_role_cd' AS role, p.pool_id, p.pool_scope_cd,
       p.period_cd, p.cap_unit_cd, p.aggregation_key_cd, p.tier_list->0->>'limit_num' AS cap
FROM db_pipeline.card_bnft b
CROSS JOIN LATERAL jsonb_array_elements(b.rule_list) r(value)
CROSS JOIN LATERAL jsonb_array_elements(r.value->'pool_refs') ref(value)
JOIN db_pipeline.card_limit_pool p
  ON (p.card_id,p.policy_ver_id,p.pool_id)=(b.card_id,b.policy_ver_id,ref.value->>'pool_id')
WHERE b.card_id=2 AND b.card_bnft_id='20261101_000003';
```

```cypher
MATCH (:A8Benefit {namespace:$ns,card_bnft_id:$id})-[:A8_HAS_RULE]->(r:A8Rule)-[c:A8_CONSUMES]->(p:A8LimitPool)
RETURN r.rule_key AS rule_key, p.pool_id AS pool_id, p.period AS period, p.unit AS unit,
       p.value AS cap, p.aggregation_is_assumption AS assumption;
```

| 항목 | SQL | Cypher |
|---|---|---|
| 규칙·풀 | `transit_rate`, `20261101_000007` | 같음 |
| 기간·단위·한도 | MONTH, KRW, 1000 | 같음 |
| 역할·범위 | CONSUME, BENEFIT | 속성 없음(`source_json`) |
| 집계 | CARD_MEMBER | 없음. 대신 `assumption=True` |

SQL은 JSONB 두 층을 펼치고 복합키로 JOIN한다. Cypher는 관계를 따라가며 JOIN이 없다. 반대로 집계 코드는 SQL에서만 바로 보인다.

### 근거

SQL은 `card_policy_evidence`와 `card_source_evidence`의 JOIN, Cypher는 `A8_SUPPORTED_BY→A8Evidence→A8Chunk→A8Page` 경로다. 두 결과는 연결 8건의 `ev_link_id`, 근거 ID, 쪽, 위치, 상태가 모두 같다.

### 전체 대조

| 혜택 | 조건 atom SQL/Cypher | 근거 연결 SQL/Cypher | 일치 |
|---|---|---|---|
| ONE PICK `...001` | 5 / 5 | 7 / 7 | 예 |
| STYLE `...002` | 5 / 5 | 6 / 6 | 예 |
| 대중교통 `...003` | 7 / 7 | 8 / 8 | 예 |
| 놀이공원 `...004` | 7 / 7 | 6 / 6 | 예 |

여기서 일치는 키·값이 같다는 뜻이며 업무 의미가 옳다는 뜻은 아니다. 한도는 대중교통 혜택만 이번에 대조했고, 전체 비교는 A8 적재 시 노드·관계 키와 `source_json`으로 수행됐다.

## 4. 항목별 분석

### 4.1 100원·500원 규칙과 `rule_select_cd`

| 관점 | 내용 |
|---|---|
| PDF 원문 | "결제 건당 3천원 이상 시 100원 / 결제 건당 1만원 이상 시 500원". ONE PICK과 STYLE 행이 **병합 셀 하나**를 공유한다. 웹 상세도 같은 값이며 선택·합산 문구는 두 자료 모두 없다 |
| PostgreSQL | `rule_select_cd=NULL`, `rule_priority=NULL`. 규칙마다 `cond_min_amt` 3000 또는 10000, `cond_max_amt_excl=NULL`, `cond_basis_cd=TXN_AMT`, `FIXED_PER_TXN` |
| Neo4j | 혜택당 `A8Rule` 2개, `A8Condition.min_amt`. `rule_select_cd`는 `A8Benefit.source_json`에만 있음 |
| 의미 판정 | 금액·기준은 **정확**. 1만원 이상의 적용 방식은 **미확정** |
| 데이터 보정 | 가능. 단 확정 후에만 |
| DDL | 불필요 |
| Neo4j | 재적재 필요. `rule_select_cd` 속성 승격 권장 |

확정 결과에 따른 저장안이다.

| 확인 결과 | `rule_select_cd` | 조건식 | 1만원 결제 |
|---|---|---|---|
| 구간 배타 | `EXCLUSIVE_BY_SCOPE` | 100원 규칙에 `cond_max_amt_excl=10000` | 500원 |
| 큰 금액 적용 | `MAX_BENEFIT_VALUE` | 변경 없음 | 500원 |
| 지정 우선순위 | `PRIORITY` | `rule_priority` 입력 | 순위에 따름 |
| 합산 | 현재 코드 없음 | `common_cd` 추가 필요 | 600원 |

앞의 두 방식은 결과가 같다. 표에 `일 1회`가 있어 합산은 어색해 보이지만 이는 정황이며 근거가 아니다. 확정하지 않는다.

`rule_select_cd=NULL`은 두 가지 뜻이 섞여 있다. 대중교통·놀이공원은 규칙이 하나라 불필요해서 NULL이고, ONE PICK·STYLE은 미확정이라 NULL이다.

### 4.2 규칙별 원문 근거

| 관점 | 내용 |
|---|---|
| PDF 원문 | 구간 문구가 셀 하나에 함께 있다 |
| PostgreSQL | 연결 41건 중 BNFT 27, POOL 9, POLICY 5, **RULE 0**. DDL과 공통코드는 RULE을 이미 지원한다(`card_policy_evidence_ck_2`) |
| Neo4j | `A8_SUPPORTED_BY` 시작점은 Policy, Benefit, LimitPool뿐. **Rule과 Condition에서 나가는 근거 관계가 없다** |
| 의미 판정 | 값은 맞지만 추적 단위가 부족하다 |
| 데이터 보정 | 가능 |
| DDL | 불필요 |
| Neo4j | 재적재 필요. A10 시점 변환기는 RULE 연결을 거부했고, A10-2에서 분기를 추가했다 |

**확인된 근거 결함:**

| 근거 | 현재 | 판정 |
|---|---|---|
| `...037` (ONE PICK 월 5천원, 풀 `...003`) | A10 시점 1622~1626 | **오류였고 A10-1에서 2270~2274로 정정.** 이전 위치는 STYLE 행 값이었다. 같은 글자라 인용 일치 검사를 통과했다 |
| `...034`, `035`, `040`, `041` | 모두 1565~1607 | 정상. 병합 셀이라 원문이 한 번뿐이다. 다만 100원용과 500원용을 구분하는 표시가 없다 |
| `...031`, `038` | 1661~1678 | 정상. 표 제목 하나를 공유한다 |
| `...044`, `047` | 2342~2371 | 중복. 역할 구분 표시가 없다 |

`v_card_integrity_issue`에는 인용 위치가 해당 행의 값인지 검사하는 게이트가 없다. 기계적으로 검증하기 어려운 영역이라 사람 검토가 필요하다.

조건 단위 연결(`ev_item_cd=COND`)은 `spend_exclusions` 2건뿐이다. 그래프에서도 Condition 노드가 아니라 Benefit에서 나가는 관계의 `ev_item_key` 문자열로 표현된다.

### 4.3 결제 건당 조건과 전월 실적 조건

| 관점 | 내용 |
|---|---|
| PDF 원문 | 건당 금액은 캐시백 조건 열. 전월 실적은 ONE MORE의 지난달 실적 열 |
| PostgreSQL | 둘 다 `cond_type_cd=SPEND_REQ`이지만 **`cond_basis_cd`가 `TXN_AMT`와 `PREV_MONTH_SPEND`로 구분된다** |
| Neo4j | `kind=SPEND_REQ`만 속성이고 `cond_basis_cd`는 `source_json`에만 있다 |
| 의미 판정 | PostgreSQL은 **정확**. Neo4j는 값은 있으나 **조회 불가** |
| 데이터 보정 | 불필요 |
| DDL | 불필요 |
| Neo4j | 변환기에 `basis` 속성 추가 후 재적재 |

**A9-4 정정:** 이전 보고의 "구분 코드가 없다"는 틀렸다. V6 코드와 값은 이미 존재한다. 부족한 것은 Neo4j 속성 승격이다.

코드명 `SPEND_REQ`(실적 요건)는 건당 금액에는 다소 어색하다. `fn_valid_cond_expr`가 `cond_basis_cd`를 요구하고 `fn_cond_spend_bound`는 `PREV_MONTH_SPEND`만 읽으므로 동작 문제는 없다. 변경하지 않는 것을 권장한다.

GraphRAG의 `CATALOG_QUERY`는 규칙에 달린 `SPEND_REQ`를 결제 기준으로 간주한다. 현재 데이터에서는 맞지만, 규칙 조건에 전월 실적이 들어오면 틀린다. `basis` 속성이 생기면 이 조건으로 바꾸는 것이 맞다.

### 4.4 대중교통 AND/OR/NOT과 제외 범위

| 관점 | 내용 |
|---|---|
| PDF 원문 | 지난달 실적 10만원. 최초 카드 사용 등록일부터 다음 달 말일까지는 미만이어도 10만원 이상 기준 제공. 제외는 공통과 대중교통(시외버스, 고속버스, KTX/SRT/ITX) |
| PostgreSQL | `[transit_spend AND NOT spend_exclusions] OR [transit_grace]`. 규칙에 `NOT transit_exclusions`. 정책에 공통 조건 |
| Neo4j | 같은 구조. Branch 2개 |
| 실효 조건 | 정책 AND 혜택 AND 규칙(DDL 머리 주석 규약) |
| 의미 판정 | OR 구조와 제외 **위치는 정확**. 세부 표현에 문제 있음 |
| 데이터 보정 | 대부분 가능 |
| DDL | 불필요. 실적 정의 표현은 설계 검토 |
| Neo4j | 재적재 필요 |

구조가 맞는 부분:

- 유예 분기에 실적 조건이 없는 것은 원문 "실적과 관계없이"와 맞다.
- 대중교통 제외는 규칙 조건이 맞다. 시외·고속버스는 대상 `버스`의 하위 범위를 좁힌다.
- 공통 제외는 정책 조건이므로 유예 분기에도 AND로 적용된다.

문제점:

| 문제 | 내용 | 보정 |
|---|---|---|
| `spend_exclusions`의 성격 | 거래를 판정하는 조건이 아니라 전월 실적 **계산 범위의 정의**다. AND의 한 항으로 두면 현재 거래의 조건처럼 읽힌다 | 설계 결정 필요. `cond_params` 규약 또는 현 상태 유지와 문서화 |
| 실적 정의 누락 | "국내외 일시불, 승인 시점 기준"이 atom에 없고 근거 048만 혜택에 연결됨 | `cond_params` 또는 조건 원문 |
| `transit_spend` 원문 | `'지난달 실적\n대중교통\n...10만원'`은 추출 스트림 2335~2371에 연속으로 있으나 표 머리글과 행 전체가 섞여 조건 문장이 아니다 | 근거 048 원문으로 교체 |
| 공통 atom 중복 | `common_service_exclusion` 원문이 `common_channel` 전체를 포함하고, `common_channel`은 허용 채널과 제외를 한 atom에 담았다 | 세 atom으로 분리 |
| NOT 규약 | `BNFT_EXCL`이 "제외 대상이다"인지 "제외를 적용했다"인지 규정이 없다 | 전자로 규약화 후 문서화 |
| 유예 판정 | `predicate_method_cd`와 날짜 파라미터가 없어 기계 판정 불가 | 현재는 원문 조건으로 유지 |

**구조화되지 않은 조건:** 원문의 "매출 접수된 국내 일시불 이용금액에 따라 캐시백 혜택을 제공"은 atom도 근거 연결도 없다. 캐시백 혜택 전체에 영향을 주는 조건이다.

`card_excl_item`은 0건이고 제외는 원문 텍스트로만 있다. 현 계약에서 허용되며 MVP에는 충분하다. 항목별 판정이 필요할 때 등록한다.

### 4.5 놀이공원 `GRACE + NOT=True`

| 관점 | 내용 |
|---|---|
| PDF 원문 | 놀이공원 행 지난달 실적 칸에 "20만원 / 최초 발급 월에는 서비스 미제공". 웹 상세도 "놀이공원 서비스는 최초 발급 월에는 서비스 미제공" |
| PostgreSQL | `amusement_first_month`, `cond_type_cd=GRACE`, `negate_yn=true`, `cond_basis_cd=NULL`, `excl_raw_txt`에 원문 |
| Neo4j | `kind=GRACE`, `negate=True` |
| 의미 판정 | 원문은 **제한**인데 유형은 **유예**(완화)다. 값을 그대로 읽으면 "유예가 아님"이 되어 **유형이 부정확**하다. 대중교통의 `GRACE`와 정반대 방향이다 |
| 데이터 보정 | 가능. `cond_type_cd` 변경 |
| DDL | 불필요 |
| Neo4j | 재적재 필요 |

`BNFT_EXCL`(혜택 적용 제외)을 권장한다. 이미 `excl_raw_txt`가 있어 `fn_valid_cond_expr`를 통과하고, `NOT=True` 패턴도 다른 제외 조건과 같다. 대안은 `USAGE_REQ`다.

"최초 발급 월"의 기준일(발급일, 수령일, 등록일)은 미확정이다. `PREDICATE_METHOD`에 `MONTH_IN`이 있지만 `card_method_catalog`의 PREDICATE 행은 0건이다.

**1인 1매:** 웹 상세는 "50%(1인 1매/월 1회/연 2회)"로 쓴다. 한도처럼 보이지만 사람 단위 집계 코드와 매수 단위 코드가 없다. 현재의 `ETC` 원문 보존이 가장 안전하다.

### 4.6 공유 한도와 집계 단위

| 관점 | 내용 |
|---|---|
| PDF 원문 | ONE PICK과 STYLE은 횟수·금액 한도 셀이 **행별로 분리**된다. 캐시백 조건 셀만 병합이다 |
| PostgreSQL | 풀 9개, 모두 `pool_scope_cd=BENEFIT`, `aggregation_key_cd=CARD_MEMBER`, tier `PENDING_REVIEW`. 같은 혜택의 규칙 2개가 풀 3개를 `CONSUME` |
| Neo4j | `A8LimitPool` 9, `A8_CONSUMES` 15, `aggregation_is_assumption=true` |
| 의미 판정 | 혜택별 풀 분리와 규칙 공유는 **정확**. 집계 단위는 **미확정** |
| 데이터 보정 | 풀 구조는 불필요 |
| DDL | 저장 방식 검토 |
| Neo4j | 구조 변경 불필요 |

이미지 대조로 "월 5천원"이 두 영역의 별도 셀임을 확인했다. 금액이 같아도 병합하지 않는 현재 구조가 맞다. 통합 한도 문구는 두 자료에 없다.

**구조 문제:** `aggregation_key_cd`는 NOT NULL인데 `LIMIT_AGG` 코드는 `CARD_MEMBER` 하나뿐이다. 미확정을 저장할 값이 없어 가정이 사실처럼 저장된다. "시험 가정" 표시는 PostgreSQL에 없고 변환기 `neo4j_dry_run.py`가 모든 풀에 `aggregation_is_assumption=True`, 정책에 `valid_from_is_assumption=True`를 넣는다. 즉 **원본에 없는 메타데이터가 코드에 하드코딩되어 있다.** 값을 확정해도 Neo4j는 계속 가정이라고 표시한다.

`LIMIT_SCOPE`에 `AREA`(서비스 영역)가 있다. PDF의 "서비스 영역"과 이름이 맞지만 이 카드는 영역과 혜택이 1:1이라 지금은 결과가 같다.

기간 경계(달력 월 여부), 일 1회의 기준, 한도 초과 건 처리 방식은 원문에 없다.

### 4.7 JSONB와 Neo4j 관계의 구조 차이

| 관점 | PostgreSQL JSONB | Neo4j |
|---|---|---|
| 규칙 식별 | 행 PK 없음. `rule_key`는 JSON 안 값 | 노드와 복합키, 고유 제약 |
| 참조 무결성 | 물리 FK 없음. `pool_ref_orphan` 게이트 | 관계 자체가 연결. 끊어진 참조 불가 |
| 다단계 조회 | `jsonb_array_elements` 다층 전개 | 경로 탐색 |
| 단순 목록 | 단일 테이블로 간단 | 2단계 탐색 |
| 집계·숫자 비교 | 강함 | 속성이 있어야 가능 |
| 형식 검증 | `fn_valid_*`, CHECK, GIN 인덱스 | 없음. 변환기와 제약 1건에 의존 |
| 공유 대상 | 규칙별 복제 | 노드 하나로 합쳐져 "이 가맹점을 쓰는 혜택" 역추적에 유리 |
| 조건 재사용 | 혜택별 복제 | 현재도 복제(`spend_exclusions` 노드 2개) |
| 근거의 조건 연결 | `ev_item_key` 문자열 | 같은 문자열. 그래프 장점을 쓰지 못함 |
| 변경 | UPDATE로 부분 수정 | 현재는 재적재. 부분 동기화 없음 |
| 해석 규약 | 주석과 함수 | 쿼리와 코드 |

V6는 규칙을 JSONB에 넣어 저장·이력 관리를 단순화했고, Neo4j는 탐색 구조를 맡는다. **PostgreSQL을 원본, Neo4j를 파생 조회 모델로 두는 현재 역할 분담이 데이터와 맞는다.** 값이 틀렸다면 PostgreSQL을 고치고 다시 변환해야 하며 Neo4j만 고치면 안 된다.

## 5. 항목 요약

| 항목 | 의미 판정 | 데이터 보정 | DDL | Neo4j |
|---|---|---|---|---|
| 1. 100·500원 | 값 정확, 선택 미확정 | 확인 후 가능 | 불필요 | 재적재 |
| 2. 규칙별 근거 | 부족, 037 오류 | 가능 | 불필요 | 재적재 |
| 3. 건당·실적 구분 | PG 정확 | 불필요 | 불필요 | 변환기 수정 후 재적재 |
| 4. 대중교통 | 구조 정확, 표현 문제 | 대부분 가능 | 불필요, 실적 정의는 검토 | 재적재 |
| 5. 놀이공원 유형 | 유형 부정확 | 가능 | 불필요 | 재적재 |
| 6. 공유 한도·집계 | 풀 정확, 집계 미확정 | 풀은 불필요 | 저장 방식 검토 | 구조 변경 없음 |
| 7. 구조 차이 | 역할 분담 적절 | 해당 없음 | 불필요 | 속성 승격 권장 |

## 6. 변경안 (미실행, 승인 필요)

### 데이터 수정만으로 해결

| 순번 | 대상 | 변경 | 영향 |
|---|---|---|---|
| D1 | `card_source_evidence.20261101_000037` | `start_pos=2270`, `end_pos=2274` | **A10-1 완료.** 인용 동일. 풀 `...003` 근거 위치 교정 |
| D2 | `card_source_evidence`, `card_policy_evidence` | 100원·500원 구간별 인용 추가, `ev_subject_cd=RULE` 연결 | 연결 수 증가. 기존 BNFT 연결 유지 |
| D3 | `transit_spend.cond_raw_txt` | 근거 048 원문으로 교체 | JSONB UPDATE. 수치 불변 |
| D4 | `policy_cond_expr` | 공통 조건을 상품권 제외, 공식 채널, 배달앱·대형시설 제외로 분리 | atom 수 변경, `atom_key` 추가, 근거 재연결 |
| D5 | `amusement_first_month` | `cond_type_cd`를 `BNFT_EXCL`로 변경 | 값 1개 |
| D6 | 캐시백 혜택 조건 | "국내 일시불" 조건 추가와 근거 연결 | atom 추가. 적용 수준 검토 필요 |
| D7 | `...047` | 중복 근거의 역할 정리 또는 유지 판단 | 연결 영향 검토 |

D2, D4, D6은 표현 방식을 결정한 뒤 실행한다. JSONB 변경은 `rule_list`·조건식 전체 교체이므로 변경 전 값을 보존해야 한다. staging 재생성은 하지 않는다. 기존 `build_cond_expr`가 단일 AND로 되돌릴 수 있다.

### 업무 확인 후 데이터 수정

| 순번 | 확인 대상 | 수정 대상 |
|---|---|---|
| B1 | 100원·500원 적용 방식 | `rule_select_cd`, 필요 시 `cond_max_amt_excl` 또는 코드 추가 |
| B2 | 한도 집계 단위 | `aggregation_key_cd` |
| B3 | 최초 발급 월 기준 | 조건 파라미터 |
| B4 | 1인 1매 범위 | 조건 유지 또는 코드 추가 |
| B5 | 정책 시작일 | `valid_from`, `approved_at` 흐름 |

확인처는 상품 약관 또는 하나카드 고객센터 1800-1111이다. 확인 결과는 `card_source_evidence`로 남길 수 있어야 하며, 전화 확인은 현재 문서 근거 구조에 맞지 않는다.

### DDL 변경 검토 항목

**필수 변경은 없다.** 아래는 선택 사항이다.

| 순번 | 내용 | 이유 | 대안 |
|---|---|---|---|
| S1 | 미확정·가정 표시 저장 | 집계·시작일 가정이 원본에 없고 변환기에 하드코딩됨 | `LIMIT_AGG`에 `UNCONFIRMED` 코드 추가(데이터). `valid_from`은 NOT NULL이라 별도 검토 |
| S2 | 규칙 겹침 게이트 | `v_card_integrity_issue`가 규칙 2개 이상, 조건 겹침, `rule_select_cd` NULL을 잡지 못한다 | 뷰 변경은 DDL이지만 테이블 변경은 없음 |
| S3 | 실적 정의 표현 | 제외 항목과 실적 범위가 atom으로 표현됨 | `cond_params` 규약 문서화로 대체 가능 |
| S4 | `link_role_cd` 정리 | V4 유산. JSON 계약에는 있으나 공통코드가 없고 모두 NULL | JSON 계약 문서만 정리 |

공통코드 추가(`LIMIT_AGG`, `RULE_SELECT`)는 DDL이 아니지만 코드 체계 결정이라 승인이 필요하다.

## 7. 권장 보정 순서

| 단계 | 작업 | 이유 |
|---|---|---|
| 1 | B1~B5 업무 확인, 상품 약관 확보 | 뒤 단계의 값을 결정한다 |
| 2 | 표현 규약 결정: NOT 의미, 실적 정의, 공통 조건 분리, S1 | 데이터를 두 번 고치지 않기 위해 |
| 3 | 변경 전 백업과 변경 전후 SQL 준비 | JSONB는 전체 교체 |
| 4 | D1, D5 | 업무 판단 없이 가능한 단건 교정 |
| 5 | D3, D4, D6 조건 정리 | 근거 재연결이 따르므로 D2보다 먼저 |
| 6 | D2 근거 연결 | 조건 키가 확정된 뒤 수행 |
| 7 | B 항목 반영 | 확인된 항목만 |
| 8 | 게이트 재실행, 인용 일치 재검사, 사람 검토 | `fn_valid_*` 통과는 의미 검증이 아님 |
| 9 | 변환기 수정: `basis`, `rule_select_cd`, 단위·역할 승격, 가정 표시 원본화 | PostgreSQL 값이 고정된 뒤 |
| 10 | Neo4j 재적재 후 전체 대조 | 로더는 비어 있지 않은 이름공간을 거부하므로 범위 삭제 승인 또는 새 이름공간 필요 |
| 11 | GraphRAG Mock 회귀, 필요 시 소수 실호출 | `SECTIONS`, `CATALOG_QUERY`, 미확정 목록이 데이터에 의존 |

D1~D7과 재적재가 끝나도 승인 데이터가 되는 것은 아니다. `approval_status_cd=PENDING`, `policy_status_cd=DRAFT`의 승인은 별도 절차다.

## 8. 분석 범위와 한계

- 상품 약관이 없어 약관에만 있는 규칙은 확인하지 못했다.
- 웹 상세 PDF는 키워드 검색만 했다. 표 레이아웃은 검토하지 않았다.
- 2쪽의 해외 수수료 등은 범위 밖이다.
- `037`의 판정은 표 이미지와 텍스트 추출 순서로 내린 것이다. 추출 순서가 셀 순서라는 전제가 있으며, 해당 위치 앞이 `/ 월 10회`로 이어져 STYLE 행으로 판단했다.
- D2의 RULE 연결이 현 변환기에서 `A8Rule` 관계로 나오는지는 코드 실행으로 확인하지 않았다.
