# Neo4j DF/PF 구조 설계 (1단계)

기준: 2026-11-01. 전환 완료. Neo4j는 DF 단독이며 최종 결과는 18절에 있다. 1~12절은 설계 당시 기록이다.

## 1. 결론

- A8 노드 13종과 관계 12종을 DF 명칭으로 1:1 변환한다. 건수는 노드 108, 관계 189로 유지된다.
- `df_card_*`는 같은 이름의 PostgreSQL 테이블이 있는 노드에만 쓴다. JSONB에서 풀어낸 5종은 `card_` 없이 이름을 붙인다.
- 공통 레이블은 `df_node`, `pf_node`로 분리하고 제약도 파이프라인별로 둔다.
- PF 명칭은 예약만 한다. `file_pipeline` 스키마에 테이블이 없어 실제 모델과 대조할 수 없다.
- 단순 치환으로 깨지는 곳이 두 군데 있다. 조건 정렬 순서와 범위 밖 검증이다(7절).
- 확정된 결정은 12절, 최종 완료 기준은 13절에 있다.

## 2. 현재 상태 조사 결과

### Neo4j (`6ac1f0f8`, Neo4j 5.27 Aura)

| 항목 | 결과 |
|---|---|
| 사용자 데이터베이스 | `6ac1f0f8` 1개 |
| 노드 / 관계 | 108 / 189. 기준선과 같음 |
| 노드 레이블 | `A8Test` + 업무 13종. 모든 노드가 두 레이블을 가짐 |
| 관계 유형 / 연결 형태 | 12종 / 17종 |
| namespace | 전부 `ONE_PICK_STYLE_A8`. 노드 `test_only=true` |
| A8 외 데이터 | 노드 0, namespace 경계를 넘는 관계 0 |
| 제약 | `a8_test_key`: `A8Test (namespace, key)` 고유성 1개 |
| 인덱스 | 제약 소유 `a8_test_key`, 시스템 LOOKUP `index_1b9dcc97`(관계), `index_460996c0`(노드) |
| 정합성 | `neo4j_validate` 결과 `ok: true`, 차이 0 |

`db.propertyKeys()`에는 `movie`, `rcp_id` 같은 과거 속성 이름이 남아 있다. 값이 없는 이름 목록이며 데이터가 아니다. 삭제해도 목록에서 사라지지 않으므로, 6단계에서 `test_only` 이름이 남아도 잔존 데이터로 판단하면 안 된다.

### PostgreSQL

| 항목 | 결과 |
|---|---|
| `db_pipeline` | 테이블 21, 뷰 13. 카드 1, 정책 1, 문서 1 |
| 적재 범위 | `card_id=2`, 정책 `20261101_000001`, 문서 `20261101_000002`. 현재 전체 행이 이 범위와 같음 |
| 상태 | 정책 `DRAFT` 1, 혜택 `PENDING_REVIEW` 4, 근거 `PENDING` 31 |
| 원본 스냅샷 SHA-256 | `e18fb8a0b3ca42f9ab29d23b54af50f835163df2144d11c9428d24c082d3626b` |
| `file_pipeline` | 스키마는 있고 사용 권한도 있으나 테이블·뷰 0개 |
| `graphrag` | 테이블 2개. 파이프라인 범위 밖이라 내용은 열지 않음 |

Neo4j를 쓰는 PF 코드도 아직 없다. `file_pipeline_origin_search/README.md`는 노드 모델이 미정이라고 밝힌다.

## 3. 명명 규칙

| 대상 | 규칙 | 예 |
|---|---|---|
| PostgreSQL 테이블 대응 노드 | `{df\|pf}_` + 테이블명 | `df_card_bnft` |
| JSONB 파생 노드 | `{df\|pf}_` + JSONB 필드 의미. `card_`로 시작하지 않음 | `df_cond_expr` |
| 관계 유형 | A8 이름을 소문자로 바꾸고 `df_` 적용 | `df_has_rule` |
| 공통 레이블 | `{df\|pf}_node` | `df_node` |
| namespace | `{df\|pf}_{카드 식별명}` | `df_one_pick_style` |
| 제약 | `{df\|pf}_node_key` | `df_node_key` |

## 4. 노드 매핑

| A8 | DF | PF(예약) | 한글 명칭 | 건수 | 원본 |
|---|---|---|---|---:|---|
| `A8Card` | `df_card_product` | `pf_card_product` | 카드 상품 | 1 | `card_product` |
| `A8Policy` | `df_card_policy_version` | `pf_card_policy_version` | 카드 정책 버전 | 1 | `card_policy_version`, `card_product_doc` 포함 |
| `A8Document` | `df_card_doc` | `pf_card_doc` | 카드 문서 | 1 | `card_doc` |
| `A8Page` | `df_card_doc_page` | `pf_card_doc_page` | 문서 페이지 | 2 | `card_doc_page` |
| `A8Chunk` | `df_card_doc_chunk` | `pf_card_doc_chunk` | 문서 청크 | 2 | `card_doc_chunk` |
| `A8Evidence` | `df_card_source_evidence` | `pf_card_source_evidence` | 원문 근거 | 31 | `card_source_evidence` |
| `A8Benefit` | `df_card_bnft` | `pf_card_bnft` | 카드 혜택 | 4 | `card_bnft` |
| `A8LimitPool` | `df_card_limit_pool` | `pf_card_limit_pool` | 한도 풀 | 9 | `card_limit_pool` |
| `A8Rule` | `df_bnft_rule` | `pf_bnft_rule` | 혜택 계산 규칙 | 6 | `card_bnft.rule_list[]` |
| `A8Expression` | `df_cond_expr` | `pf_cond_expr` | 조건식 | 8 | `policy_cond_expr` 1, `bnft_cond_expr` 2, `rule_list[].cond_expr` 5 |
| `A8Branch` | `df_cond_branch` | `pf_cond_branch` | 조건 분기 | 9 | `cond_expr.branches[]` |
| `A8Condition` | `df_cond_atom` | `pf_cond_atom` | 조건 원자 | 15 | `branches[].atoms[]`, 뷰 `v_card_cond_atom`과 대응 |
| `A8Target` | `df_rule_target` | `pf_rule_target` | 규칙 적용 대상 | 19 | `rule_list[].target_list[]` |
| `A8Test` | `df_node` | `pf_node` | DF/PF 공통 식별 레이블 | 108 | 전 노드 |

### 업무 설명

| DF 레이블 | 설명 |
|---|---|
| `df_card_product` | 발급 상품의 기본 정보 |
| `df_card_policy_version` | 상품의 특정 시점 혜택 정책. 공통 조건식의 소유자 |
| `df_card_doc` | 혜택의 원본 PDF 문서 |
| `df_card_doc_page` | 문서의 페이지 원문 |
| `df_card_doc_chunk` | 페이지를 나눈 검색·인용 단위 |
| `df_card_source_evidence` | 청크 안의 인용 구간. 승인 상태 `PENDING` 유지 |
| `df_card_bnft` | 카드가 제공하는 개별 혜택 |
| `df_card_limit_pool` | 기간별 혜택 한도. 구간 목록은 `source_json`의 `tier_list`에 보존 |
| `df_bnft_rule` | 혜택 금액을 계산하는 규칙 |
| `df_cond_expr` | 정책·혜택·규칙이 소유한 조건식 |
| `df_cond_branch` | 분기끼리는 OR. `branch_no` 유지 |
| `df_cond_atom` | 한 분기 안의 조건끼리는 AND. `negate`로 NOT 표현, `atom_seq` 유지 |
| `df_rule_target` | 가맹점 등 적용 대상. 카드·정책·유형·이름으로 합쳐, 19개 중 15개를 규칙 2개가 공유 |

OR/AND 구조는 바뀌지 않는다. 조건식 → 분기 → 원자 계층과 각 노드의 `source_json`을 그대로 유지한다.

## 5. 관계 매핑

| A8 | DF | PF(예약) | 한글 명칭 | 시작 → 끝 | 건수 | 원본 |
|---|---|---|---|---|---:|---|
| `A8_HAS_POLICY` | `df_has_policy` | `pf_has_policy` | 정책 보유 | `df_card_product` → `df_card_policy_version` | 1 | `card_id` |
| `A8_HAS_BENEFIT` | `df_has_benefit` | `pf_has_benefit` | 혜택 보유 | `df_card_policy_version` → `df_card_bnft` | 4 | `card_id`, `policy_ver_id` |
| `A8_HAS_RULE` | `df_has_rule` | `pf_has_rule` | 규칙 보유 | `df_card_bnft` → `df_bnft_rule` | 6 | `rule_list[]` |
| `A8_HAS_EXPR` | `df_has_expr` | `pf_has_expr` | 조건식 보유 | `df_card_policy_version` 1, `df_card_bnft` 2, `df_bnft_rule` 5 → `df_cond_expr` | 8 | 각 조건식 필드 |
| `A8_HAS_BRANCH` | `df_has_branch` | `pf_has_branch` | 분기 보유 | `df_cond_expr` → `df_cond_branch` | 9 | `branches[]` |
| `A8_HAS_ATOM` | `df_has_atom` | `pf_has_atom` | 조건 원자 보유 | `df_cond_branch` → `df_cond_atom` | 15 | `atoms[]` |
| `A8_TARGETS` | `df_targets` | `pf_targets` | 적용 대상 | `df_bnft_rule` → `df_rule_target` | 34 | `target_list[]` |
| `A8_CONSUMES` | `df_consumes` | `pf_consumes` | 한도 소진 | `df_bnft_rule` → `df_card_limit_pool` | 15 | `pool_refs[]` |
| `A8_SUPPORTED_BY` | `df_supported_by` | `pf_supported_by` | 근거 연결 | `df_card_bnft` 34, `df_card_limit_pool` 9, `df_card_policy_version` 8, `df_bnft_rule` 11 → `df_card_source_evidence` | 62 | `card_policy_evidence` 행 |
| `A8_IN_CHUNK` | `df_in_chunk` | `pf_in_chunk` | 청크 소속 | `df_card_source_evidence` → `df_card_doc_chunk` | 31 | `card_doc_chunk_id` |
| `A8_ON_PAGE` | `df_on_page` | `pf_on_page` | 페이지 소속 | `df_card_doc_chunk` → `df_card_doc_page` | 2 | `page_no` |
| `A8_IN_DOCUMENT` | `df_in_document` | `pf_in_document` | 문서 소속 | `df_card_doc_page` → `df_card_doc` | 2 | `card_doc_id` |

연결 형태는 17종 그대로다. 관계 방향도 바꾸지 않는다. 상품과 문서를 직접 잇는 관계는 지금도 없고 이번에도 추가하지 않는다. `card_product_doc`은 정책 노드의 `source_json.product_doc`에 보존된다.

## 6. 속성

모든 노드에 `namespace`, `key`, `source_json`이 있고, 모든 관계에도 같은 3개가 있다.

| DF 레이블 | 추가 속성 |
|---|---|
| `df_card_product` | `card_id` |
| `df_card_policy_version` | `card_id`, `policy_ver_id`, `valid_from_is_assumption` |
| `df_card_doc` | 없음 |
| `df_card_doc_page` | `page_no` |
| `df_card_doc_chunk` | `page_no` |
| `df_card_source_evidence` | `evidence_id`, `page_no`, `start_pos`, `end_pos`, `approval_status` |
| `df_card_bnft` | `card_id`, `policy_ver_id`, `card_bnft_id`, `name`, `verification_status` |
| `df_card_limit_pool` | `card_id`, `policy_ver_id`, `pool_id`, `period`, `unit`, `value`, `aggregation_is_assumption` |
| `df_bnft_rule` | `rule_key`, `value_num` |
| `df_cond_expr` | 없음 |
| `df_cond_branch` | `branch_no` |
| `df_cond_atom` | `atom_seq`, `key_name`, `kind`, `negate`, `min_amt`(6건만), `raw_text` |
| `df_rule_target` | `target_nm` |

관계 추가 속성: `df_has_atom`은 `atom_seq`, `df_supported_by`는 `ev_link_id`, `ev_subject_cd`, `ev_item_cd`, `ev_item_key`.

기존 속성은 이미 소문자 snake_case다. `name`, `kind`, `negate`처럼 PostgreSQL 컬럼명과 다른 별칭은 Cypher와 Python이 사용 중이므로 유지를 제안한다. `test_only`는 제거한다. 사용처를 확인한 결과 값을 읽는 Cypher·검증·화면은 없었고 쓰기 2곳과 화면 숨김 목록 1곳뿐이었다. `test_only`와 DRAFT는 의미가 다르다. DRAFT는 업무 데이터의 검토 상태이고 원본 그대로 유지한다. 시험 데이터 표시를 대신하는 것이 아니다. DF 범위는 `df_` 레이블과 namespace로 식별한다.

## 7. 식별 구조와 DF/PF 충돌

### namespace와 키

| 항목 | 현재 | 변경 |
|---|---|---|
| 노드 키 | `["ONE_PICK_STYLE_A8","Benefit",2,"…","…"]` | `["df_one_pick_style","card_bnft",2,"…","…"]` |
| 관계 키 | 유형·양끝 키·`source_json`의 SHA-256 | 같은 방식. 값은 모두 바뀜 |
| 조건식 소유자 표시 | `policy`, `benefit`, `rule` | 유지 |

키의 나머지 부분은 PostgreSQL 식별값 그대로다. 옛 키와 새 키가 규칙적으로 대응하므로 108개 노드와 189개 관계를 한 건씩 대조할 수 있다.

`source_json` 생성 방식은 바꾸지 않는다. `df_card_policy_version`과 `df_card_limit_pool`의 `{"source": ...}` 감싸기도 유지하므로 값이 현재와 바이트 단위로 같아야 한다.

### 공통 레이블 비교

| 기준 | 하나의 공통 레이블 + namespace | `df_node` / `pf_node` 분리(제안) |
|---|---|---|
| 제약 | 1개를 공유 | 파이프라인별 1개 |
| PF 키 구조 | `(namespace, key)` 강제 | 팀원이 정할 수 있음 |
| 잘못된 삭제 | namespace 조건을 빠뜨리면 양쪽 삭제 | 레이블로 한쪽에 한정 |
| 경계 검증 | namespace 값으로만 판단 | 레이블로도 판단 |
| 추가 구조 | 없음 | 없음 |

### 충돌 분석

| 항목 | 판단 |
|---|---|
| 노드 키 충돌 | 없음. 레이블과 키의 namespace가 다르다 |
| DF–PF 관계 | 코드가 양쪽 레이블을 함께 쓰지 않는 한 생기지 않는다. 6단계와 이후 검증에서 0건을 확인한다 |
| 검색 혼입 | 모든 검색이 `df_` 레이블과 `namespace`를 쓰므로 PF가 조회되지 않는다 |
| 같은 카드의 이중 적재 | DF와 PF에 같은 상품이 각각 있을 수 있다. 의도된 분리이며 합치지 않는다 |

### 단순 치환으로 깨지는 곳

1. **조건 정렬 순서:** `benefit_conditions`는 `ORDER BY owner_labels`를 쓴다. 지금은 혜택 → 정책 → 규칙 순서다. 새 이름에서는 `df_bnft_rule`이 먼저 와서 프롬프트와 화면의 조건 순서가 바뀐다. 소유자 순위를 명시하는 `CASE`로 현재 순서를 고정해야 한다.
2. **범위 밖 검증:** `outside_scope_counts`는 시험 레이블이 아닌 모든 노드를 범위 밖으로 센다. 그대로 옮기면 PF 적재가 시작되는 순간 DF 검증이 실패한다. 다음 세 검사로 나눈다.
   - `df_node`의 namespace 불일치와 `df_` 레이블의 `df_node` 누락
   - DF 노드에 붙은 비 DF 관계
   - PF 건수와 A8 잔존 건수
3. **레이블 문자열:** `card_graphrag.py:260`의 `"A8Policy" in row["owner_labels"]`는 Cypher 치환만으로 바뀌지 않는다. 틀리면 "카드 공통" 표시가 조용히 "혜택"으로 바뀐다.
4. **namespace 조건 누락:** `benefit_evidence`의 `(:A8Rule)`, `condition_structure`와 `evidence_links`의 일부 노드에 `namespace` 조건이 없다. 레이블로 범위가 좁혀져 있어 현재 결과 문제는 없지만 전환 시 함께 맞춘다.

## 8. 제약과 인덱스

| 대상 | 처리 |
|---|---|
| `a8_test_key` | A8 삭제 시 제거. 소유 인덱스도 함께 제거 |
| `df_node_key` | `(n:df_node)`의 `(namespace, key)` 고유성으로 생성 |
| `pf_node_key` | 지금 만들지 않음. PF 키가 정해질 때 팀원이 생성 |
| `index_1b9dcc97`, `index_460996c0` | 시스템 인덱스. 건드리지 않음 |
| 추가 인덱스, 관계 고유성 제약 | 만들지 않음. 108개 규모이고 기존 사후 키 검증이 관계 중복을 막는다 |

```cypher
CREATE CONSTRAINT df_node_key IF NOT EXISTS
FOR (n:df_node) REQUIRE (n.namespace, n.key) IS UNIQUE
```

이 구문은 `neo4j_load_draft.py`의 `CREATE_CONSTRAINT`에 둔다. `db_pipeline`의 `.cypher` 파일은 읽기 전용이어야 한다는 기존 테스트가 있어 별도 파일을 만들지 않았다.

## 9. 변경 대상

| 구분 | 파일 | A8 등장 | 변경 내용 |
|---|---|---:|---|
| 변환 | `db_pipeline/neo4j_dry_run.py` | 5 | `NS`, 레이블, 관계 유형, 키 구성 |
| 적재 | `db_pipeline/neo4j_load_draft.py` | 9 | 허용 목록, MERGE, `--apply`의 제약 생성(`CREATE_CONSTRAINT`), 확인 문자열, `test_only` 제거 |
| 검증 | `db_pipeline/neo4j_validate.py` | 0 | 새 범위 검사 반영 |
| 검증 Cypher | `db_pipeline/neo4j_validation.cypher` | 28 | 전체 치환, 범위 검사 재작성 |
| 검색 Cypher | `db_pipeline_origin_search/graph_questions.cypher` | 26 | 7개 조회 치환, 정렬 고정 |
| 검색 | `db_pipeline_origin_search/neo4j_search.py` | 13 | `NAMESPACE`, 경로 문자열, 숨김 속성 |
| GraphRAG | `db_pipeline_origin_search/card_graphrag.py` | 1 | 소유자 레이블 판단. 7절 3번 |
| 화면 | `streamlit_app.py`, `verify_view.py` | 0 | 코드 변경 없음. 동작만 검증 |
| 테스트 | `test_neo4j_dry_run.py`, `test_neo4j_load_draft.py`, `test_neo4j_validate.py` | 7 / 7 / 7 | 명칭 치환, 경계 테스트 추가 |
| 테스트 | `tests/test_neo4j_origin_search.py`, `tests/test_card_graphrag.py` | 4 / 3 | 명칭 치환, 정렬·소유자 테스트 추가 |
| 현행 문서 | `db_pipeline/README.md`, `db_pipeline_origin_search/README.md`, `PROJECT_STATUS.md`, 인수인계 문서 | 소수 | 현재 구조 설명 갱신 |

변경하지 않는 대상은 다음과 같다.

- `A10_*`, `POSTGRESQL_TO_NEO4J_STRUCTURE_COMPARISON.md`: 당시 기록이므로 유지
- `src/common`, `src/recipe`, `file_pipeline`, PostgreSQL
- 검색 결과 중 `manifest.json`과 `docs/자료조사`의 A8: SHA-256과 URL 일부로 무관

## 10. 재구축과 롤백

순서는 **DF 적재 → 정합성 검증 → 프로그램 DF 전환 검증 → A8 삭제**로 확정했다. 레이블과 제약이 달라 A8과 DF는 공존할 수 있다. A8 삭제는 별도 명시적 승인 후 수행한다.

| 순서 | 작업 | 실패 시 |
|---|---|---|
| 1 | 3단계 백업과 건수·해시 대조 | 진행 중단 |
| 2 | 승인 후 `df_node_key` 생성 | 제약 제거 |
| 3 | PostgreSQL에서 DF 변환 후 단일 트랜잭션 적재 | 자동 롤백 |
| 4 | 재실행해 건수 불변 확인, 정합성 검증 | `df_node`만 삭제, A8 유지 |
| 5 | 프로그램을 DF로 전환해 5단계 검증 | 코드 되돌림, A8 유지 |
| 6 | 별도 승인 후 `A8Test` 삭제, `a8_test_key` 제거 | 백업에서 복원 |

- **백업:** 노드는 레이블 전체와 속성, 관계는 유형·양끝 키·속성 전체를 JSONL로 저장하고 SHA-256을 남긴다. 복원은 백업 파일로 MERGE한다.
- **복원 검증:** 쓰기 없이 백업을 메모리에서 재구성해 현재 그래프, PostgreSQL 변환 결과와 비교한다. 실제 복원 실행 여부는 3단계에서 따로 보고한다.
- **최종 안전망:** Neo4j는 파생 데이터이므로 PostgreSQL에서 다시 만들 수 있다.
- **백업 위치:** `D:\Bootcamp\backups\card_benefit\neo4j\`. 제약과 인덱스 정의도 함께 저장한다. JSON 내보내기를 완전한 복원 보장으로 보지 않고, 복원 절차와 실제 검증 범위를 3단계에서 기록한다.
- **코드 롤백:** 2단계 수정 전 미커밋 작업 30건을 `D:\Bootcamp\backups\card_benefit\source\20261101_155114`에 백업했다. 번들 clone + 패치 + 신규 파일로 복원 검증을 마쳤다. 2단계 반영 소스는 `D:\Bootcamp\backups\card_benefit\source\20261101_161003`에 있다. 기준 커밋은 사용자가 만든 `56208cf`(`origin/main` 반영)이며 코드 롤백 기준점이다.

## 11. 검증 계획

| 단계 | 검증 |
|---|---|
| 2단계 | 변환 결과 건수 108/189, 관계 형태 17종 |
| | 현재 그래프와 `source_json` 전체 일치 |
| | A8 문자열이 현행 코드와 테스트에 0건 |
| | Mock 테스트, 기존 대비 실패 이름 비교 |
| | 조건 순서가 변경 전과 같음 |
| 3단계 | 백업 건수, 양끝 키, 속성, 해시 일치 |
| | 삭제·유지 대상 목록 보고 |
| 4단계 | 원본 스냅샷 해시 일치, 재실행 시 건수 불변 |
| | 옛 키 ↔ 새 키 108 + 189건 대조 |
| | OR/AND 구조, 규칙, 한도, 대상, 근거 연결과 DRAFT·PENDING 상태 유지 |
| 5단계 | Streamlit, LangGraph 경로, Named Cypher 7개 |
| | 실행 로그의 Cypher를 JDBC로 재실행, DBeaver UI는 사용자 확인 필요 |
| | Mock LLM + 실제 Neo4j 답변이 변경 전과 동일 |
| 6단계 | PF 0건, DF–PF 관계 0건, A8 노드·관계·제약 0건 |
| | 레이블별 속성, 관계 시작·끝, 건수, 한글 사전 추출 |

유료 LLM은 쓰지 않는다. 실제 LLM 검증이 필요하면 5단계에서 별도 승인 항목으로 보고한다.

## 12. 확정된 결정

| 번호 | 결정 | 결과 |
|---:|---|---|
| 1 | 파생 노드 5종 명칭 | 승인 |
| 2 | 공통 레이블 | `df_node`, `pf_node` 분리 승인. PF 노드·관계·제약은 미리 만들지 않음 |
| 3 | `test_only` 속성 | 사용처 확인 후 제거 승인 |
| 4 | 속성 별칭 | 유지 |
| 5 | 마이그레이션 순서 | DF 적재 → 검증 → 프로그램 전환 검증 → A8 삭제 |
| 6 | PF 제약 | PF 모델과 키가 확정될 때 팀원이 생성 |
| 7 | 기준 커밋 | `56208cf`. 사용자가 직접 커밋·Push. 추가 Git Commit/Push는 별도 지시 전까지 금지 |
| 8 | Neo4j 백업 위치 | `D:\Bootcamp\backups\card_benefit\neo4j\` |

## 13. 최종 완료 기준

설계, 코드 수정, Mock 테스트만으로는 완료가 아니다. 아래 7개를 실제로 수행해야 하며, DB 적재와 삭제는 단계별 명시적 승인 후 진행한다.

1. 변경된 적재 프로그램을 실행해 PostgreSQL 원본으로 Neo4j DF 그래프 생성
2. 적재된 DF 노드·관계와 PostgreSQL 원본 정합성 검증
3. 적재 프로그램 재실행 시 중복 없음 검증
4. GraphRAG 프로그램이 실제 DF 데이터를 정상 조회하는지 확인
5. 검증 완료 후 기존 A8 데이터 삭제
6. A8 삭제 후 검색 프로그램을 다시 실행해 정상 동작 확인
7. A8 0건, PF 0건, DF 정상 유지 확인

최종 보고서에는 실제 실행 결과, 데이터 건수, 정합성 검증 결과, 검색 테스트 결과를 포함한다.

## 14. 3단계 Neo4j 백업

- 위치: `D:\Bootcamp\backups\card_benefit\neo4j\20261101_160805`
- 내용: 노드 108, 관계 189, 전체 속성(`test_only` 포함), 관계 끝점, 제약·인덱스 정의, 레이블·유형·속성 이름 목록, 복원 스크립트
- 검증: 해시, 식별키, 끝점, Aura 재조회, PostgreSQL 변환 결과 대조, 메모리 복원 시험 통과. 백업 결과는 사용자가 승인했다.
- **미검증: 실제 Neo4j 서버 복원.** 빈 별도 Neo4j 인스턴스가 없어 현재 단계에서는 시험하지 않는다. 절차와 검증 범위는 백업 폴더의 `RESTORE.md`에 있다.

## 15. 기존 실패 테스트 19개

`run_offline_tests.py`의 recipe 묶음에서 실패한다. 이번 단계에서 수정하지 않는다.

| 테스트 | 원인 |
|---|---|
| `test_graph_questions.GraphExplorerAppTests.test_graph_db_error_is_shown_without_crash` | `AppTest.form_submit_button` 없음 |
| `test_graph_questions.GraphExplorerAppTests.test_pantry_mode_is_unchanged` | `AppTest.form_submit_button` 없음 |
| `test_graph_questions.GraphExplorerAppTests.test_q1_shows_hop_path_and_neo4j_rows` | `AppTest.form_submit_button` 없음 |
| `test_graph_questions.GraphExplorerAppTests.test_q3_three_hop_table` | `AppTest.form_submit_button` 없음 |
| `test_graph_questions.GraphExplorerAppTests.test_q5_steps_table_uses_https_image_urls` | `AppTest.form_submit_button` 없음 |
| `test_graph_questions.GraphExplorerAppTests.test_unknown_ingredient_and_empty_result_are_explained` | `AppTest.form_submit_button` 없음 |
| `test_query_log_config.PostgresRecommendationLogCheckTests.test_local_default_without_env_runs_postgres_selects` | `AppTest.form_submit_button` 없음 |
| `test_query_log_config.PostgresRecommendationLogCheckTests.test_log_off_and_cloud_default_do_not_create_postgres_session` | `AppTest.form_submit_button` 없음 |
| `test_query_log_config.PostgresRecommendationLogCheckTests.test_log_on_uses_existing_search_service_and_four_selects` | `AppTest.form_submit_button` 없음 |
| `test_query_log_config.PostgresRecommendationLogCheckTests.test_postgres_failure_keeps_neo4j_recommendations` | `AppTest.form_submit_button` 없음 |
| `test_recipe_search.PackageLayoutTests.test_dry_run_cli_runs_with_python_m` | `DB_URL` 차단으로 PostgreSQL `PoolTimeout`, CLI rc 2 |
| `test_streamlit_app.StreamlitAppTests.test_llm_answer_is_marked_as_llm` | `AppTest.form_submit_button` 없음 |
| `test_streamlit_app.StreamlitAppTests.test_llm_failure_shows_rule_based_fallback` | `AppTest.form_submit_button` 없음 |
| `test_streamlit_app.StreamlitAppTests.test_neo4j_connection_failure_is_shown` | `AppTest.form_submit_button` 없음 |
| `test_streamlit_app.StreamlitAppTests.test_partially_replaced_llm_answer_shows_both_sources` | `AppTest.form_submit_button` 없음 |
| `test_streamlit_app.StreamlitAppTests.test_recipe_images_and_steps_are_shown` | `AppTest.form_submit_button` 없음 |
| `test_streamlit_app.StreamlitAppTests.test_rule_based_answer_when_llm_is_not_configured` | `AppTest.form_submit_button` 없음 |
| `test_streamlit_app.StreamlitAppTests.test_step_query_failure_keeps_recommendations` | `AppTest.form_submit_button` 없음 |
| `test_streamlit_app.StreamlitAppTests.test_unknown_ingredient_is_reported` | `AppTest.form_submit_button` 없음 |

DF 변경과 무관하다고 판단한 근거:

- 실패 이름 19개가 공통화 작업 전, 2단계 수정 전, 현재에 모두 같다.
- 모든 테스트가 `src/recipe` 소속이고, `src/recipe`에는 카드·DF 참조가 0건이다.
- `src/recipe`의 2단계 변경이 없다. 2단계 전 백업과 해시가 같다.
- 18개는 설치된 Streamlit의 `AppTest`에 `form_submit_button`이 없어 버튼 조작 전에 끝난다. 임시 shim으로 속성을 제공하면 모두 통과했다(공통화 작업 시점).
- `test_dry_run_cli_runs_with_python_m`은 자격증명을 막는 실행 환경 때문이다. 자격증명이 있는 단독 실행은 통과했다.

## 16. 4단계 DF 적재 결과

- 실행: `neo4j_load_draft --apply`. 두 번째 실행 후 DF 노드·관계가 elementId까지 첫 실행과 같아 중복이 없다.
- 건수: DF 노드 108, 관계 189, 레이블 13종, 유형 12종, 연결 형태 17종. PF 0. A8 108/189는 백업과 elementId까지 같다.
- 제약: `df_node_key` 생성. `a8_test_key` 유지.
- 정합성: `neo4j_validate` `ok: true`. PostgreSQL 변환값, A8 대응값과 속성·끝점 전체 일치.
- 검색: Named Cypher 7개 결과가 변경 전 A8 결과와 필드 단위로 같다. 조건과 근거의 행 순서도 같다.
- 이후 A8 삭제와 재검증을 마쳤다(18절).

## 17. 5단계 Streamlit·검색 검증 결과

- 근거: `D:\Bootcamp\backups\card_benefit\verification\stage5_20261101_162333` (화면 캡처, 터미널 로그, JDBC 시험 Cypher, 비교 결과)
- 방식: 프로그램에 Mock 옵션이 없어 저장소 밖 실행기에서 `create_llms`만 교체했다. Neo4j 조회는 실제 코드이고 OpenAI 주소는 닫힌 포트로 막았다.
- 화면: 질문 6개와 개발 검증 3단계에서 예외 0, 콘솔 오류 0, 화면의 A8·`pf_` 표기 0.
- 흐름: 5개 질문이 interpret → retrieve → answer → finish, 모호한 질문 1개가 interpret → finish로 실행됐다.
- A8 대조: 같은 Mock으로 DF와 A8 검색을 비교해 LLM 프롬프트 11건과 최종 결과가 같다(측정 시각 제외).
- 로그: 값이 들어간 Cypher 15종을 파라미터 없이 드라이버로 재실행해 바인딩 실행과 결과가 같다. DBeaver의 JDBC 드라이버 6.15.1로도 30회 실행해 행 수가 일치했다.
- `카드 공통`: LLM 컨텍스트에서 혜택 → 카드 공통 → 규칙 순서로 유지된다. 화면에는 이 문구가 직접 나오지 않고 개발 검증 표의 `owner_cd`가 `BNFT → POLICY → RULE`로 나온다.
- `list_benefits`: 질문 흐름에서 호출되지 않는 진단용 조회다. 실제 DF 실행 검증은 4단계에서 했다.
- 미완료: DBeaver GUI 직접 실행, 실제 LLM 호출, 실제 서버 복원. 18절에서도 미검증으로 유지한다.

## 18. 6·7단계 최종 결과

A8 시험 그래프를 제거했고 Neo4j는 DF 단독 상태다. 13절의 완료 기준 7개를 모두 수행했다.

### 최종 구조

- 대상: Aura `6ac1f0f8`
- namespace: `df_one_pick_style`
- 전체 노드 108, 관계 189. 모두 DF다. A8 0, PF 0
- 공통 레이블 `df_node` 108건, 업무 레이블 13종, 관계 유형 12종, 연결 형태 17종
- 제약: `df_node_key`
- 인덱스: `df_node_key`(RANGE), `index_1b9dcc97`, `index_460996c0`(시스템 LOOKUP)

| 노드 레이블 | 건수 |
|---|---:|
| `df_bnft_rule` | 6 |
| `df_card_bnft` | 4 |
| `df_card_doc` | 1 |
| `df_card_doc_chunk` | 2 |
| `df_card_doc_page` | 2 |
| `df_card_limit_pool` | 9 |
| `df_card_policy_version` | 1 |
| `df_card_product` | 1 |
| `df_card_source_evidence` | 31 |
| `df_cond_atom` | 15 |
| `df_cond_branch` | 9 |
| `df_cond_expr` | 8 |
| `df_rule_target` | 19 |

| 관계 유형 | 건수 |
|---|---:|
| `df_consumes` | 15 |
| `df_has_atom` | 15 |
| `df_has_benefit` | 4 |
| `df_has_branch` | 9 |
| `df_has_expr` | 8 |
| `df_has_policy` | 1 |
| `df_has_rule` | 6 |
| `df_in_chunk` | 31 |
| `df_in_document` | 2 |
| `df_on_page` | 2 |
| `df_supported_by` | 62 |
| `df_targets` | 34 |

레이블별 속성과 연결 형태 전체는 `D:\Bootcamp\backups\card_benefit\verification\stage7_20261101_163910\final_structure.json`에 있다. ERD를 다시 만들 때 이 파일과 4·5절의 한글 명칭을 쓴다.

### A8 제거

- 삭제 전 조건 16개를 모두 확인했다.
- 삭제는 `A8Test` + `ONE_PICK_STYLE_A8`로 한정했다. 트랜잭션 안에서 외부 관계 0을 재확인했고, 삭제 건수는 노드 108, 관계 189다.
- 결과 확인 후 `a8_test_key`를 별도로 제거했다.
- `db.propertyKeys()`에 `test_only` 이름이 남아 있다. 값이 없는 이름 목록이며 이를 가진 노드는 0건이다.
- A8 백업은 `D:\Bootcamp\backups\card_benefit\neo4j\20261101_160805`에 보존한다.

### DF 단독 검증

| 항목 | 결과 |
|---|---|
| DF 속성, `source_json`, elementId | 삭제 전과 전체 일치, 변경 0 |
| `neo4j_validate` | `ok: true`, 차이 0, 범위 위반 0, 고아 노드 0 |
| PostgreSQL 정합성 | 원본 해시 동일, 변환값과 노드 108·관계 189 일치, 조건 15·근거 연결 62 일치 |
| Named Cypher 7개 | 변경 전 A8 결과와 차이 0 |
| 카드 테스트 | 실제 Neo4j 포함 157건 통과, 전체 641개 이름 기준 신규 실패 0 |
| GraphRAG 대표 질문 6개 | 삭제 전과 결과·프롬프트 11건 동일 |
| Streamlit | 질문 6개, 개발 검증 3단계 화면 삭제 전과 동일, 예외 0, 콘솔 오류 0 |
| Cypher DEBUG 로그 | 42건 출력, 15종을 드라이버로 재실행해 결과 동일 |
| DBeaver JDBC 드라이버 | 읽기 전용 30회 실행, 행 수 일치 |
| A8·PF 혼입 | 조회 로그, 프롬프트, 결과, 화면 모두 0건 |

LLM은 모두 Mock이다. 근거 파일은 `D:\Bootcamp\backups\card_benefit\verification\stage7_20261101_163910`에 있다.

### 코드에 남은 A8

`neo4j_validation.cypher`의 `other_graph_counts`가 A8 잔존 건수를 센다. 재발 감시용으로 유지한다. 나머지는 주석과 이 검사의 테스트다. 검색 코드에는 없다.

### 남은 미검증 항목

- 실제 LLM 답변 품질
- DBeaver GUI 직접 실행
- A8 백업의 실제 서버 복원
