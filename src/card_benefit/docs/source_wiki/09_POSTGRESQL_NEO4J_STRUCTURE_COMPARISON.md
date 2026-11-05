# PostgreSQL ↔ Neo4j 구조 비교

[Source Wiki 목차](README.md) · [PostgreSQL 스키마](06_POSTGRESQL_SCHEMA.md) · [Neo4j 동기화](07_NEO4J_SYNC.md) · [GraphRAG 조회](08_GRAPHRAG_QUERY.md)

> 이 문서는 현재 checkout의 DDL·SQL Mapper·Python·Cypher를 정적으로 읽어 작성했다. DB 접속과 적재를 하지 않았으므로, 저장소의 코드/마이그레이션 상태와 운영 DB 적용 상태를 구분한다. 운영 PostgreSQL·Neo4j 카탈로그와 실제 Neo4j 데이터는 미확인이다. 경로 링크의 줄 번호는 현재 파일 기준이다.

## 1. 역할과 데이터 경계

PostgreSQL은 카드, 상품항목, 원문 문서, 페이지·청크, 근거, 검토 상태를 업무 키와 제약으로 저장하는 원본 계층이다. 예를 들어 상품 혜택은 `card_product_item`의 `item_type_cd='BENEFIT'` 행이며 조건식·규칙·혜택 간 관계는 JSONB 컬럼으로 보존된다. 상품과 문서의 연결은 `card_product_doc`, 근거와 업무 주체의 연결은 `card_evidence_link`가 가진다. DDL은 [V7 초안의 상품·문서·근거 정의](../../sql/db_pipeline_schemaV7_draft.sql#L398)와 [상품 항목 전환 DDL](../../sql/db_pipeline_card_product_item.sql#L74)에 있다.

Neo4j 적재 모델은 이 행·JSON을 탐색 경로로 쪼갠다. 상품→혜택→규칙→대상, 소유자→조건식→branch→atom, 업무 주체→근거→청크→페이지→문서가 관계로 연결된다. 같은 속성의 반복 조회, 여러 단계 관계 탐색과 공통 대상 역방향 탐색에 맞춘 표현이다. 이 설계 이유는 구조와 조회 패턴에서 읽히는 해석이며, 소스 주석은 특히 target 노드를 카드 사이에서 공유하여 역탐색한다고 명시한다.

두 DB의 표현은 완전한 복제본이 아니다. 그래프 변환기는 일부 검색용 텍스트·임베딩을 제외하고, `relation_list`를 별도 그래프 간선으로 풀지 않으며, 근거도 링크된 것만 그래프로 옮긴다. 따라서 그래프에서 경로 탐색을 쉽게 하는 대신 PostgreSQL의 원본 필드와 업무 상태 전체를 그래프 노드/관계로 펼치지는 않는다.

## 2. 구조 비교

| 업무 항목 | PostgreSQL 구조 | Neo4j 구조·변환 | 표현 차이·미반영 가능성 |
|---|---|---|---|
| 카드 상품 | `card_product` PK `card_id`; 카드 조건은 `card_cond_expr`, 상태는 `card_cond_status_cd` | `(:dp_card_product)`; PK의 `card_id`로 key 구성. 카드 조건은 condition 하위 그래프 | 행은 상품 속성을 한데 저장하고 관계는 별도 노드/간선. 조건이 NULL이면 expression 없음. 현재 로더는 DRAFT 아닌 카드 조건을 거부하도록 작성됨 |
| 카드별 혜택 | 현행 변환 SQL은 `card_product_item` 중 BENEFIT을 읽고 `card_product_item_id AS card_bnft_id` 등 과거 명칭으로 별칭; 복합 PK `(card_id, card_product_item_id)` | `(:dp_card_bnft)`와 `dp_has_benefit`; 그래프 key·주요 ID는 `card_bnft_id` 사용. 로더가 노드에 `dp_card_product_item` label도 추가 | BENEFIT을 별도 `dp_card_product_item` label로만 만들지 않고 호환 label인 `dp_card_bnft`로 만든다. `item_ref`, 일부 텍스트/검토 메타 등은 source_json에 남을 수 있으나 scalar 속성으로 모두 풀리지는 않음 |
| 연회비 등 비혜택 항목 | 동일한 `card_product_item`; `item_type_cd`, `item_data`, 검토/유효기간/텍스트 컬럼 | `(:dp_card_product_item)`와 상품의 `dp_has_item` 관계. `ANNUAL_FEE` 데이터는 `source_json.item_data` | `fee_lines`를 별도 줄 노드로 만들지 않는다. GraphRAG가 `item_data.fee_lines`를 읽어 화면/답변용으로 처리. 필드 계약은 [항목 DDL](../../sql/db_pipeline_card_product_item.sql#L74) |
| 할인·제외 조건 | `item_cond_expr` 및 `rule_list[].cond_expr`; V7 DDL의 condition/rule views는 JSONB를 relational 조회 형태로 전개 | `dp_cond_expr`→`dp_cond_branch`→`dp_cond_atom`; `dp_has_expr`, `dp_has_branch`, `dp_has_atom` | branch와 atom은 개별 노드지만 원본 JSON 전체도 `source_json`에 보관. 제외 `NOT`은 atom의 `negate_yn`을 scalar 별칭 `negate`로 표현. 별도 NOT 노드는 없음 |
| 규칙·대상 | `rule_list` 배열의 rule, 수치·단위·조건 및 target 목록. DDL view `v_card_rule`, `v_card_rule_target`가 배열을 펼침 | `dp_bnft_rule` 노드와 `dp_has_rule`; `dp_rule_target` 노드와 `dp_targets` | rule PK는 `(card_id, card_bnft_id, rule_key)`. target은 `(target_type_cd,target_key)`로 여러 카드/규칙 사이 공유. 대상/규칙 개별 탐색이 가능. rule의 나머지 원문 속성은 source_json에 보존 |
| 혜택 간 관계 | `relation_list` JSONB 항목에 `relation_key`, `to_bnft_id`, `rel_type_cd`, `rel_priority` 등을 둠. DDL의 `v_card_bnft_rel`가 SQL 조회용 배열 전개 제공 | 현재 `neo4j_dry_run.build()`에서 relation_list를 순회하거나 해당 관계 유형을 생성하지 않음 | 현재 적재 경로에서 혜택 간 JSON 관계는 그래프 간선으로 변환되지 않는다. 비교 결과 `SAME`로 판정된 브랜드 공통 혜택은 별도의 `dp_same_as`로 생성되며, 이는 `relation_list` 변환과 다름 |
| 문서·페이지·청크 | `card_doc`, `card_doc_page`, `card_doc_chunk`; 상품 연결은 `card_product_doc`, 공통서비스 연결은 `card_common_doc` | 동명 `dp_card_doc*` 노드; `dp_has_document`, `dp_in_document`(페이지→문서), `dp_on_page`(청크→페이지) | 관계 테이블의 행은 연결 간선으로 바뀌고 각 문서 단위는 노드. 모든 청크가 아니라 문서 구조 행을 스냅샷으로 읽음 |
| 원문 근거·근거 연결 | `card_source_evidence`에 인용/위치/승인; `card_evidence_link`에 업무 주체·근거 ID·subject/item/rule/relation 키 | `dp_card_source_evidence`; `dp_supported_by`(업무 노드→근거), `dp_in_chunk`(근거→청크). 근거 연결 컬럼은 관계 속성 | `card_source_evidence` 중 하나 이상의 evidence link가 있는 것만 노드화. 관계는 `evidence_link_id AS ev_link_id` 등 소스 필드를 source_json 및 선별 속성으로 보존. 미연결 추출 후보는 그래프 미포함 |
| 공통 혜택·카드 적용 | `card_common`, `card_common_bnft`, `card_common_bnft_apply`; 브랜드별 혜택 유사성은 비교 SQL/서비스 | 공통서비스 `dp_card_common`, 혜택 `dp_card_common_bnft`; `dp_belongs_to`, 카드 적용 `dp_has_common_benefit`; 확정 동일성 `dp_same_as` | 공통 혜택과 카드는 적용행이 있을 때만 간선으로 이어짐. `SAME` 결과만 카드별 BENEFIT에서 공통혜택으로 연결. REVIEW/NO_COMMON은 same_as 미생성 |
| TERMS | `card_product_item`의 `TERMS`와 `item_data`; DDL 전환 스크립트에서 허용/제약과 실제 적용은 별도 확인 대상 | 로더의 비혜택 조회는 `item_type_cd <> 'BENEFIT'`이므로 TERMS도 그래프 항목으로 들어갈 수 있는 코드 형태. 그러나 GraphRAG `item_catalog`는 BENEFIT·TERMS 둘 다 후보에서 제외. 선택된 혜택의 TERMS는 PostgreSQL `select_card_terms`로 조회 | 후보/상세 근거에 붙는 TERMS 경로는 PostgreSQL Mapper와 GraphRAG 코드에 구현돼 있다. 현재 TERMS seed/등록 상태와 운영 DB 적용은 정적 파일만으로 확정할 수 없음. DDL/등록 코드/운영 상태를 혼동하지 않는다 |

주요 변환 정의는 [스냅샷 SQL과 PK](../../payment_card/db_pipeline/neo4j_dry_run.py#L132), [그래프 구성](../../payment_card/db_pipeline/neo4j_dry_run.py#L235), [노드 속성·저장](../../payment_card/db_pipeline/neo4j_load_draft.py#L68), [PostgreSQL DDL views](../../sql/db_pipeline_schemaV7_draft.sql#L950)에서 확인한다.

## 3. PostgreSQL 업무 키와 그래프 식별자

PostgreSQL 행의 PK가 그래프 노드 식별 재료로 쓰인다. 예를 들어 상품 `card_id=42`는 `["card_product",42]`, 혜택은 `["card_bnft",42,"<card_product_item_id>"]`를 정규 JSON 배열로 직렬화한 내부 key다. `dp_node.key`에 이를 저장하고, 각 노드에는 테이블 PK 필드도 둔다. 복합키 값의 경계 충돌을 피하도록 배열 직렬화를 쓴다. 조건식 노드는 원본 테이블 PK가 없으므로 소유자 구분자와 소유자 PK를 이어붙인 `expr_key`를 쓴다. atom은 `expr_key, branch_no, atom_key`로 식별된다.

PostgreSQL의 기술 PK와 업무 식별자는 구분해야 한다. 예컨대 BENEFIT 이관 때 `card_product_item_id`는 이전 `card_bnft_id` 값을 승계하도록 전환 SQL이 작성돼 있다. Neo4j query와 GraphRAG는 `card_bnft_id` 이름을 계속 사용하지만 실제 현재 원천 SELECT는 `card_product_item_id AS card_bnft_id`로 이름을 바꾼다. 이는 동일한 카드 안에서는 기존 ID를 유지하려는 호환 변환이다. 그래프 전역 key에는 카드 ID도 포함되므로 카드가 다른 같은 문자열 ID는 다른 노드다.

## 4. JSONB에서 노드와 관계로

### 4.1 조건식: branch OR, atom AND, negate 속성

소스가 전제하는 표현은 대략 다음과 같다. 실제 저장 행마다 조건 종류와 수치는 달라지며 이 예시는 구조를 읽기 위한 축약이다.

```json
{
  "branches": [
    {"branch_no": 1, "atoms": [
      {"atom_key": "a1", "atom_seq": 1, "cond_type_cd": "SPEND_REQ", "cond_min_amt": 300000, "negate_yn": false},
      {"atom_key": "a2", "atom_seq": 2, "cond_type_cd": "CARD_USE", "negate_yn": false}
    ]},
    {"branch_no": 2, "atoms": [
      {"atom_key": "a3", "atom_seq": 1, "cond_type_cd": "NEW_CARD_WAIVER", "negate_yn": false}
    ]}
  ]
}
```

변환 코드는 조건식을 소유하는 카드/혜택/rule에서 `dp_cond_expr`로 연결하고, 각 branch를 `dp_cond_branch`, 각 atom을 `dp_cond_atom`으로 만든다. 표현 의미는 branch 간 OR, 동일 branch 내 atom 간 AND다. NOT은 `negate_yn` 값으로 atom 속성에 보존한다. 원본 조건식 JSON 자체도 expression 노드의 `source_json`으로 유지한다. 변환기는 branch나 atom을 모르는 구조를 임의로 버리지 않고 예외를 모아 오류 처리한다. 조건식이 SQL NULL이면 그래프 요소도 생성하지 않는다.

### 4.2 `rule_list`

각 JSON rule은 별도 `dp_bnft_rule` 노드가 되고 혜택과 `dp_has_rule`로 연결된다. PK는 카드·혜택·`rule_key` 조합이다. rule의 `cond_expr`가 있으면 rule이 expression의 소유자가 되고, `target_list[]`의 항목은 `(target_type_cd,target_key)`를 식별자로 하는 공유 `dp_rule_target` 노드 및 `dp_targets` 간선이 된다. 대상 명칭은 속성으로 유지한다. 규칙 원본 JSON 전체는 `source_json`에 보존되며 숫자 값/코드 등 일부 필드가 별도 scalar 속성으로도 노출된다.

`v_card_rule`/`v_card_rule_target`는 PostgreSQL에서 JSONB 배열을 SQL 행으로 보이게 하는 조회 뷰다. 이 뷰가 그래프 스키마는 아니다. 현재 `neo4j_dry_run`은 JSONB를 직접 snapshot 행에서 순회한다.

### 4.3 `relation_list`

PostgreSQL에는 JSONB 배열로 혜택 간 관계가 저장되고, `v_card_bnft_rel` 뷰도 선언돼 있다. 그러나 현재 그래프 builder는 `rule_list`와 `cond_expr`는 순회하면서 `relation_list`는 순회하지 않는다. 로더가 허용하는 관계 유형에도 `relation_list` 전용 rel type이 없다. 따라서 relation JSON은 혜택 행의 `source_json`에 남지만 두 혜택을 잇는 Neo4j 간선으로 변환되지 않는다. 별도의 `dp_same_as`는 브랜드 혜택 비교 결과에서 생성되는 관계라서 같은 필드의 변환이 아니다.

### 4.4 `item_data`

`item_data`는 유형별 상세 JSON이다. 현재 노드 생성기는 원천 행 전체를 canonical JSON으로 `source_json`에 넣는다. 즉 중첩 JSON이 `item_data`라는 단독 graph property로 반드시 펼쳐지는 게 아니라 source_json 안에 담긴다. 혜택 외 항목 노드에는 scalar allowlist에 있는 ID·종류·이름·상태 등이 속성으로 복사되지만, `item_data` 객체 자체는 scalar가 아니어서 별도 확장하지 않는다.

연회비 예시 구조는 DDL 계약상 `ANNUAL_FEE_V1`의 `fee_lines[]`로 본인/가족 구분, 브랜드, 기본·제휴·합계 금액 등을 담는다. GraphRAG의 `Neo4jSearch.list_catalog()` 및 `fee_answer()`는 catalog에서 온 `item_source`/`source_json` 내부 `item_data.fee_lines`를 읽는다. 따라서 연회비 처리 코드가 있어도 줄마다 Neo4j 노드를 만들었다는 뜻은 아니다.

TERMS는 현재 registration module이 seed에서 `item_data` 초안을 만들고 `card_product_item`과 ITEM self-evidence link를 쓰는 SQL을 포함한다. 검색 Mapper는 PostgreSQL에서 `item_data`와 근거를 읽고, `attach_terms()`는 scope를 기준으로 선택된 혜택에 붙인다. 이 흐름과 Neo4j 적재 구현 여부, 운영 DB 반영은 각각 별개다.

## 5. 설계 선택을 구조에서 읽기

관계형 관점에서 보면 JSONB 한 행은 업무 원본과 입력/검증 단위를 단단하게 묶고, Neo4j는 그 안의 반복 요소를 별도 정점으로 만들어 탐색 단계를 직접 연결한다. 혜택 규칙·조건 branch·atom을 쪼개면 “이 카드의 이 혜택에서 이 규칙의 어느 대상/조건으로 이어지는가”를 조인 테이블 대신 그래프 경로로 찾을 수 있다. 반복 대상은 공통 PK로 한 정점에 합쳐 여러 규칙에서 공유된다.

무엇을 노드로 만드는지는 독립 식별성·반복성·탐색 경로에 따라 현재 코드에서 드러난다. rule, target, expression, branch, atom, product, document, evidence는 PK/내부 key와 관계가 있다. 상태·이름·금액 같은 값은 노드 속성으로 남는다. 복합 item_data 같은 객체는 JSON source 보존 경계 안에 남으며, 모든 하위 항목을 별도 그래프로 바꾸지 않는다.

관계를 세분화하면 연결 자체의 출처·승인·주체 종류 등을 간선 속성에 달고 경로 질의를 단순화할 수 있다. 비용 측면에서는 관계 수와 적재 검증·키 관리·재동기화 대상이 커지고, 변환기에 구현되지 않은 JSON 필드는 탐색 가능한 간선이 되지 않는다. 현재 적재기는 허용 label/type 목록, 노드별 PK constraint, `dp_node.key` unique constraint, 예상/실제 노드·간선 수 및 endpoint 사후 확인으로 구조를 검증하도록 작성됐다. 이는 정합성 검증 코드의 범위이지, 이번에 실제 데이터베이스에서 통과한 결과가 아니다.

## 6. 데이터 흐름 추적: 등록 카드 혜택을 기준으로 한 소스 경로

프로젝트의 등록 보고서에 기록된 실제 행으로 JADE First(`card_id=20`)의 `card_product_item_id=20261105_000092`, “골프/프리미엄 아울렛 50% 청구 할인”을 추적 사례로 삼는다. 보고서는 상품 문서 `card_doc_id=20261105_000040`, 3쪽 근거 대조, 혜택 4건 등록 및 근거 링크 20건을 기록한다. 다만 그 보고서는 Neo4j 반영을 하지 않았다고 명시한다. 따라서 PostgreSQL 등록은 보고서로 확인된 범위, 그래프 노드·간선은 현재 코드가 만들 것으로 예상되는 변환으로 구분한다. [개별 카드 최종 등록 보고서](../INDIVIDUAL_CARDS_10_FINAL_20261105.md)

1. **PDF → 문서/청크.** [문서 등록 Repository](../../payment_card/db_pipeline/document_repository.sql)와 [06장](06_POSTGRESQL_SCHEMA.md)은 `card_doc`, `card_doc_page`, `card_doc_chunk` 저장을 기술한다. 원문 계층의 PK는 `card_doc_id`, `(card_doc_id,page_no)`, `(card_doc_id,page_no,card_doc_chunk_id)`다. PDF 바이너리에서 이 경로로 들어오는 등록 단계의 함수 호출은 [01장](01_PDF_REGISTRATION.md)을 따른다.
2. **AI 추출 → staging/evidence.** AI 출력은 `card_extr_stg` 후보와 `card_source_evidence` 근거로 관리된다. 등록 전 후보와 업무 승인/연결 완료 근거는 같은 상태가 아니다. Graph builder는 `card_evidence_link`로 실제 주체에 연결된 `evidence_id`만 Neo4j evidence 노드로 선택한다.
3. **정형 등록.** 현재 상품 혜택 Mapper `insert_local_benefit`은 `card_product_item(item_type_cd='BENEFIT')`에 `item_cond_expr`, `rule_list`, `relation_list`, `item_data`를 저장한다. `card_product_item_id`가 반환되어 이후 링크 및 그래프 변환의 업무 키가 된다. 혜택 근거는 `card_evidence_link`의 subject/key 컬럼으로 주체에 연결된다.
4. **PostgreSQL → 그래프 미리보기.** `neo4j_load_draft.main()`은 `neo4j_dry_run.load_snapshot()`을 통해 repeatable-read/read-only 스냅샷을 읽고 `build()`에서 노드/간선을 만든 뒤 `prepare()`가 허용 목록과 속성을 만든다. 원천 BENEFIT의 `card_product_item_id`는 `card_bnft_id`라는 그래프 호환 별칭이 된다. rule key와 target 키, expression key가 JSON에서 추출된다. 그래프의 혜택 조건 흐름은 상품→`dp_card_bnft`→rule/condition/target; 근거는 BENEFIT→`dp_supported_by`→evidence→chunk→page→document다.
5. **Neo4j 쓰기 경계.** `neo4j_dry_run.py --dry-run`은 그래프 변환 검증 후 `neo4j_writes=0`을 출력하는 별도 코드 경로다. 실제 writer는 `neo4j_load_draft.py --apply --confirm ...`일 때만 접속/쓰기하도록 구현돼 있다. 이 문서 작성 과정에서는 실행하지 않았다. 따라서 실제 운영 적재는 미확인.
6. **Cypher → GraphRAG.** `graph_questions.cypher`의 `catalog`, `benefit_rules`, `benefit_conditions`, `benefit_evidence` 등을 `Neo4jSearch.list_catalog()`/`get_detail()`이 실행한다. `CardGraphRAG.retrieve()`는 해석된 key를 상세 검색하고, evidence를 모은 뒤 제외 문구·미확정 항목을 구성한다. ANSWER 단계는 근거가 없으면 답변 LLM을 호출하지 않는다. BENEFIT key는 내부적으로 `card_bnft_id`와 카드 ID를 포함해 조회하며 PostgreSQL 보조 검색의 `pg:` key와 구별된다.
7. **연회비·TERMS 분기.** 연회비는 `dp_card_product_item` source JSON의 fee lines를 프로그램이 사용하고, 연회비만 묻는 경우 등록 금액으로 응답하도록 코드화돼 있다. TERMS는 `select_card_terms` PostgreSQL Mapper로 읽어 범위가 맞으면 답변 문맥과 evidence에 합친다. 둘 다 BENEFIT 규칙 그래프의 변환과 별도 처리다.

관련 소스: [snapshot/build](../../payment_card/db_pipeline/neo4j_dry_run.py#L132), [writer](../../payment_card/db_pipeline/neo4j_load_draft.py#L102), [검색 Cypher](../../payment_card/db_pipeline_origin_search/graph_questions.cypher), [GraphRAG retrieve/answer](../../payment_card/db_pipeline_origin_search/card_graphrag.py#L1611).

## 7. 현재 구현 상태와 관찰 경계

### 구현 코드에서 확인되는 동작

- BENEFIT 원천은 `card_product_item`에서 읽되, 그래프의 label/property/key는 기존 `dp_card_bnft`/`card_bnft_id` 명칭을 유지한다.
- 혜택 조건식, rule, target, branch, atom, 카드·문서·근거 계층 및 공통 혜택 적용/동일성의 그래프 변환 코드가 있다.
- 관계/JSON 원문은 노드·관계의 `source_json`으로 저장하도록 되어 있고, 주요 scalar 속성은 allowlist/alias로 추가한다.
- `relation_list`는 현재 builder의 간선 생성 대상이 아니다. BENEFIT 원문 JSON source 안에 보존될 수 있는 것과 간선 변환은 구분한다.
- 연회비의 `item_data.fee_lines`와 TERMS의 `item_data` 처리 코드는 존재한다. TERMS는 그래프 후보가 아닌 선택된 카드 혜택에 붙이는 PostgreSQL 보조 자료로 구현돼 있다.

### 운영 적용으로 단정할 수 없는 항목

저장소에는 `db_pipeline_schemaV7_draft.sql`, 여러 전환/마이그레이션 SQL, TERMS 전환 SQL, TERMS 등록 Python이 공존한다. 초안 DDL은 최종 운영 DDL이라는 증거가 아니며 마이그레이션 SQL도 실행 이력이 아니다. `terms_register.py`에는 기본 rollback/선택적 commit 제어가 있으므로 파일 존재만으로 seed가 운영 등록됐다고 할 수 없다. Neo4j writer에 apply 경로가 있는 것도 실제 적재 완료 증거가 아니다. 운영 DB 적용 여부, 카드/혜택별 실제 행, Neo4j 노드/관계 건수는 확인하지 않았다.

따라서 PostgreSQL에는 있지만 그래프에서 직접 탐색되지 않는 정보는 `relation_list`의 의미 관계, 검색 텍스트·임베딩, 미연결 evidence, AI staging/run/call 이력 등이다. 반대로 Neo4j에는 원본 별도 테이블이 아니라 변환 과정에서 만들어지는 `dp_cond_expr`/branch/atom, `dp_rule_target`, `dp_same_as` 등의 노드·간선이 있다. 이는 원본 값/비교 결과를 그래프 탐색 표현으로 만든 것으로, 별도 PostgreSQL 업무 테이블이라고 오인하면 안 된다.

## 8. 정합성 검증 코드의 의미

현재 dry-run/build 검증은 원천 행 수로 예상 노드·관계 수를 계산해 변환 결과와 비교하고, dangling edge, 미지원 주체, 부모 누락, 조건 JSON 원본 대조를 확인한다. writer는 `MERGE` 후 대상 key 집합과 관계 key 집합을 다시 읽어 건수와 key를 비교하며, stale `dp_` 노드가 있으면 자동 삭제하지 않고 중단하도록 작성돼 있다. PostgreSQL SQL `v_card_integrity_issue` 및 관련 검증 쿼리는 원천 정합성 관찰에 쓰인다.

이 검증은 JSON 변환 구조와 적재 결과의 기술적 일치를 확인하려는 장치다. 조건의 의미가 원문과 일치하는지, 운영 DB가 특정 DDL 버전인지, 운영 Neo4j에 마지막 로드가 끝났는지까지 자동 증명하지 않는다. 특히 이번 작업은 어떤 validator나 dry-run도 실행하지 않았으며 데이터베이스에 연결하지 않았다.

## 9. 주요 코드 참조

- [상품/혜택/문서·근거 DDL](../../sql/db_pipeline_schemaV7_draft.sql#L398)
- [card_product_item 전환·키 승계 DDL](../../sql/db_pipeline_card_product_item.sql#L74)
- [TERMS DDL 전환](../../sql/db_pipeline_card_product_item_terms.sql)
- [PostgreSQL JSONB 조회 view](../../sql/db_pipeline_schemaV7_draft.sql#L950)
- [BENEFIT·비혜택 snapshot query 및 식별자](../../payment_card/db_pipeline/neo4j_dry_run.py#L132)
- [조건식·rule·target·evidence graph 변환](../../payment_card/db_pipeline/neo4j_dry_run.py#L235)
- [Neo4j 속성 projection과 writer](../../payment_card/db_pipeline/neo4j_load_draft.py#L68)
- [TERMS 조회 SQL](../../payment_card/db_pipeline/embedding_repository.sql#L207)
- [Neo4j 검색 Cypher](../../payment_card/db_pipeline_origin_search/graph_questions.cypher)
- [Neo4j 검색 래퍼](../../payment_card/db_pipeline_origin_search/neo4j_search.py#L208)
- [TERMS scope 적용 및 GraphRAG retrieve](../../payment_card/db_pipeline_origin_search/card_graphrag.py#L722)
- [TERMS seed 등록 코드](../../payment_card/db_pipeline/terms_register.py#L151)

[목차](README.md) · [Neo4j 동기화 →](07_NEO4J_SYNC.md) · [GraphRAG 조회 →](08_GRAPHRAG_QUERY.md)
