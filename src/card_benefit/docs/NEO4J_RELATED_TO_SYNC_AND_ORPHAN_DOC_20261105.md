# Neo4j `dp_related_to` 원장 동기화 설계·사전 검증 + 고아 문서 `20261103_000012` 원인 분석 (2026-11-05)

> 운영 Aura·PostgreSQL 데이터 변경 없음. 커밋·푸시 없음.
> Codex 작업 파일(`neo4j_load_draft.py`, `neo4j_validate.py`, `neo4j_validation.cypher`, `neo4j_dry_run.py` 등)은 수정하지 않았다. import로 재사용만 했다.
> 추가 파일은 2개다: `payment_card/db_pipeline/neo4j_relation_sync.py`, `payment_card/db_pipeline/test_neo4j_relation_sync.py`.

---

# A. `dp_related_to` 원장 기준 동기화

## A-0. 최종 사전 검증 결과 (운영 Aura 적재 전, 읽기 전용)

`python -m card_benefit.payment_card.db_pipeline.neo4j_relation_sync` (PREVIEW, 쓰기 없음) 실행 결과:

| 항목 | 기대 | 결과 |
|---|---|---|
| 원장 `relation_list` 관계 | 6 | **6** |
| 현재 Aura 노드 / 관계 / dp_related_to | 937 / 1,297 / 0 | **937 / 1,297 / 0** |
| 동기화 계획 create / update / replace / delete | 6 / 0 / 0 / 0 | **6 / 0 / 0 / 0** |
| 적용 후 노드 / 관계 | 937 / 1,303 | **937 / 1,303** |
| dp_related_to 외 관계 (원장 vs Aura) | 1,297 = 1,297 | **1,297 = 1,297** |
| dp_related_to 외 차이(누락·초과·라벨·속성·구조) | 0 | **모두 0** |
| SQL↔Cypher 대조 4종 | 일치 | condition 117, evidence_links 250, common_applies 1, rule_targets 235 **모두 일치** |
| dp_ 범위 위반 | 0 | **0 / 0** |
| 고아 노드 | — | 1건 `["card_doc","20261103_000012"]` → **source_preexisting** (적재 원인 0건) |
| 전체 검증 `ok` | — | **false (유지)** — 원인: 미적재 관계 6건 + 기존 고아 문서 1건 |
| 관계 동기화 관문 `relation_sync_ready` | — | **true** |

적용 전 지문(적용 후 같아야 함):
- 노드 937, `nodes_sha256 = ea153daa8836400ef1d4ef184d4fbffd993f9b64138528643480cce14f49354e`
- dp_related_to 외 관계 1,297, `other_relationships_sha256 = 63e4c3a63ae4ef44efc0d30ae9b10957e29de51e1bbdafb7ae15779efc3b2d6e`

### 예상 변경 사항 (신규 6건, 모두 카드 42)

| 출발 혜택 | 대상 혜택 | relation_key | rel_type_cd | rel_priority | 관계 key (앞 12자리) |
|---|---|---|---|---|---|
| 20261105_000179 | 20261105_000178 | fixed_fallback | FALLBACK_AFTER_CAP | null(속성 없음) | e0196578cf88 |
| 20261105_000179 | 20261105_000178 | special_over_basic | OVERRIDES | null | 8b03b9b897bc |
| 20261105_000179 | 20261105_000178 | special_basic_exclusive | MUTUALLY_EXCLUSIVE | null | 8390646e5845 |
| 20261105_000180 | 20261105_000178 | recurring_fallback | FALLBACK_AFTER_CAP | null | 0a9980d0ebe3 |
| 20261105_000180 | 20261105_000178 | special_over_basic | OVERRIDES | null | 0af0b44ab080 |
| 20261105_000180 | 20261105_000178 | special_basic_exclusive | MUTUALLY_EXCLUSIVE | null | b17745a07f41 |

- 방향: 출발 = `relation_list`를 가진 혜택, 대상 = `to_bnft_id`. 같은 카드 안에서만 연결한다.
- 대상 노드의 `card_bnft_id`가 `to_bnft_id`와 같은지 확인했다.
- 각 관계에 기록하는 속성: `key`, `source_json`, `relation_key`, `rel_type_cd`, `to_bnft_id` (`rel_priority`는 null이라 속성 부재). 기존 적재기 `relationship_properties`와 같다.
- 관계 key 6개는 기존 `neo4j_validate`가 "누락"으로 보고하는 key 6개와 정확히 같다.

### 실데이터 모의 적용 (운영 미변경)

실제 Aura 상태를 읽어 메모리 그래프에 복사한 뒤 `sync_transaction`을 실행했다.

| 단계 | 결과 |
|---|---|
| 1차 실행 | create 6, 나머지 0. 노드·기타 관계 지문 불변 |
| 2차 실행 (같은 입력) | 변경 0건, **쓰기 구문 전송 0건** |
| 적용 후 상태를 Codex의 `compare_graph`로 비교 | **차이 0**, 관계 1,303 |

쓰기 Cypher 3개(삭제·갱신·MERGE)는 운영 Aura에서 `EXPLAIN`(계획만 생성, 실행 안 함)으로 문법·계획을 확인했고, 갱신 0건이었다.

### 실제 적용 명령 (승인 후에만, 아직 실행하지 않음)

```
.venv/Scripts/python -m card_benefit.payment_card.db_pipeline.neo4j_relation_sync --apply \
  --confirm APPROVED_DP_RELATED_TO_SYNC \
  --expect '{"create":6,"update":0,"replace":0,"delete":0}'
```

실행 순서: 사전 검증을 다시 수행한다 → 관문 확인 → 쓰기 트랜잭션 1개 안에서 계획을 다시 계산한다. 다시 계산한 계획이 `--expect`와 다르면 쓰기 전에 중단한다.

---

## A-1. 업무 식별 기준 (임의 결정이 아닌 원장 근거)

PostgreSQL CHECK `card_product_item_rel_ck` → `fn_valid_relation_list(relation_list, card_product_item_id)`(운영 DB에서 함수 원문 확인)는 한 출발 혜택 안에서 다음을 강제한다.

| 조건 | 의미 |
|---|---|
| `relation_key` 필수, `^[A-Za-z0-9_.:-]{1,40}$`, **목록 안 유일** | 출발 혜택 안의 관계 식별자 |
| `(to_bnft_id, rel_type_cd)` **목록 안 유일** | 보조 유일키. 같은 대상이라도 유형이 다르면 별개 관계 |
| `to_bnft_id ≠ 자기 자신`, `rel_type_cd` 필수 | 자기참조 금지 |
| `rel_priority`: number 또는 null | **어떤 유일 조건에도 들어가지 않음** → 가변 속성 |

또 `card_evidence_link`의 REL 근거 6건이 `(card_id, card_product_item_id, relation_key)`로 관계를 가리킨다. 예: `special_over_basic`, `special_basic_exclusive`가 같은 근거 `20261105_003032`를 공유한다.

**채택한 식별자 = (출발 노드, relation_key)**
- 보조 유일키 (출발, 대상, rel_type_cd)는 위반 시 중단하는 검사로만 쓴다.
- `rel_priority`, `rel_type_cd`, `to_bnft_id`, `source_json`은 식별자가 아니다.

**`rel_priority`를 Edge 식별 키에 넣는 것은 부적절하다.** 원장에서 유일성에 관여하지 않는 가변 값이므로, 키에 넣으면 우선순위만 바뀌어도 "다른 관계"가 된다. 그러면 삭제·생성(이력 단절)이 일어나거나, 삭제 없는 적재기에서는 같은 관계가 2개로 남는다.

현재 Codex 구현의 관계 `key`는 `sha256(유형, 출발, 대상, 원본 JSON 전체)`이다. 원본 JSON에 `rel_priority`가 있으므로 **사실상 `rel_priority`가 식별 키에 포함된 상태**다. 동기화 모듈은 `key`로 식별하지 않고 (출발, relation_key)로 식별한다. `key` 속성은 기존 검증기와의 호환을 위해 적재기와 같은 값을 그대로 기록하고, 원본이 바뀌면 갱신한다.

### 판단이 갈릴 수 있는 지점과 대안 (결정 필요)

| 상황 | 채택안 (relation_key 식별) | 대안 (to_bnft_id + rel_type_cd 식별) | 근거 |
|---|---|---|---|
| relation_key 그대로, rel_type_cd만 변경 | **같은 관계의 속성 갱신** (update 1) | 기존 삭제 + 신규 생성 | 근거 연결이 relation_key로 관계를 가리키므로 근거가 그대로 붙는 "같은 관계"로 봤다 |
| relation_key 변경, 유형·대상 동일 | 삭제 + 생성 | 속성 갱신 | 근거 연결의 relation_key도 함께 바뀌어야 하므로 다른 관계로 봤다 |
| 대상(to_bnft_id) 변경 | replace (그 관계만 삭제 후 생성) | 삭제 + 생성 | Neo4j 관계는 끝점을 옮길 수 없다 |

업무에서 "유형이 바뀌면 다른 관계"로 봐야 한다면 대안으로 바꿀 수 있다. 바꿀 곳은 `ledger_relations`·`plan`의 식별자 한 곳이다. **현재 원장 6건에는 두 기준의 결과가 같다**(두 키 모두 유일).

---

## A-2. 구현 (`neo4j_relation_sync.py`, 신규)

| 구성 | 내용 |
|---|---|
| `ledger_relations(nodes, edges)` | 기존 `build`·`prepare` 결과에서 dp_related_to만 원장으로 만든다. 원장 CHECK 조건(relation_key 중복, (대상, 유형) 중복, 다른 카드, `to_bnft_id` 불일치, 자기참조, 끝점 없음)을 다시 검사하고, 어기면 중단한다 |
| `plan(ledger, neo4j_rows)` | create / update / replace / delete / unchanged 분류. 같은 식별자의 기존 관계가 여러 개, `relation_key` 없는 기존 관계, dp_node 밖 관계가 있으면 **고르지 않고 중단**한다 |
| `sync_transaction(tx, ledger, expected)` | **쓰기 트랜잭션 1개**에서 실행: 상태 읽기 → 계획 재계산 → 승인 건수 대조 → 삭제(그 관계만) → 갱신(`SET r = $props`, null이 된 속성은 제거) → MERGE 생성 → 사후 검증. 사후 검증 조건: 남은 차이 0, 관계 수 = 원장 수, **노드·기타 관계 지문 불변**. 하나라도 어기면 예외가 나고 rollback된다. 변경이 0건이면 쓰기 구문을 보내지 않는다 |
| 쓰기 범위 | 쓰기 구문 3개 모두 `[r:dp_related_to]`만 대상이다. `DETACH`·`REMOVE`·노드 쓰기 없음 |
| `fingerprint` | 노드(key, **정렬한 라벨**, 전체 속성)와 dp_related_to 외 관계(유형, 끝점, 전체 속성)를 정규화한 SHA-256. 라벨·행 순서와 무관하다. 앞선 롤백의 원인이었던 라벨 순서 비교 문제를 재현하지 않는다 |
| `preflight` | 기존 `neo4j_validate.run()` 결과를 그대로 보고하고(`ok` 판정 무수정), 별도로 dp_related_to 외 차이와 고아 분류를 낸다 |
| `classify_orphans` | Neo4j 고아 노드의 연결 상태가 원장 그래프와 같으면 `source_preexisting`, 다르면 `load_mismatch`로 나눈다. **보고용이며 전체 검증 판정은 완화하지 않는다** |
| 관문 `relation_sync_ready` | dp_related_to 외 차이 0, 범위 위반 0, SQL↔Cypher 4종 일치, 적재 원인 고아 0일 때만 true. 기존 고아(원천 문제)는 실패로 보고되지만 관계 동기화를 막지 않는다 |

### 전체 MERGE vs 관계만 증분 동기화

| 방식 | 장점 | 위험 |
|---|---|---|
| 기존 전체 MERGE (`neo4j_load_draft --apply`) | 원장 전체를 재반영 | 937 노드·1,297 관계 전체에 `SET`을 다시 실행한다. **원장에서 지워진 관계를 지우지 못한다**(삭제 금지 설계). 관계 내용이 바뀌면 key가 바뀌어 옛 관계가 남고 사후 key 검사에서 실패한다 |
| **관계만 원장 동기화 (권장)** | 쓰기가 dp_related_to 6건으로 한정된다. 생성·갱신·삭제를 구분한다. 나머지는 트랜잭션 안 지문으로 불변을 증명한다 | 노드·다른 관계가 원장과 어긋난 상태에서는 하지 않는다(관문으로 차단) |

이번 적재는 **관계만 증분 동기화**를 권장한다. 현재 다른 노드·관계의 차이가 0이라 전체 MERGE가 얻는 것이 없다.

---

## A-3. 테스트 결과

`test_neo4j_relation_sync.py` **21건 모두 통과**. 실제 Neo4j 대신 쓰기 구문을 해석하는 메모리 그래프(FakeGraph)를 쓴다.

| 요청 시나리오 | 테스트 | 결과 |
|---|---|---|
| 최초 실행: 6건 생성 | `test_first_run_creates_six_and_leaves_other_types` | create 6, 다른 유형 관계 동일 |
| 동일 입력 재실행: 0건 | `test_rerun_with_same_input_changes_nothing` | 변경 0, 쓰기 구문 0 |
| rel_priority 변경: 속성만 변경 | `test_priority_change_updates_same_relationship`, `test_priority_back_to_null_removes_property` | update 1, 관계 id 유지, 6건 유지, key 속성은 적재기 값과 동일. null로 돌아가면 속성 제거 |
| 관계 유형 변경 | `test_type_change_with_same_relation_key_updates_in_place`, `test_type_change_with_new_relation_key_is_delete_plus_create` | 키 같으면 update 1 / 키 바뀌면 delete 1 + create 1 |
| 대상 변경 | `test_target_change_replaces_only_that_relationship` | replace 1 |
| 관계 삭제: 그 dp_related_to만 | `test_ledger_deletion_removes_only_that_related_to` | delete 1. 같은 relation_key를 가진 다른 출발 관계는 유지. 다른 유형 불변 |
| 같은 출발·대상, 다른 유형 유지 | `test_same_pair_with_three_types_is_three_relations`, `test_same_pair_different_types_all_kept` | 쌍 2개, 관계 6개 유지 |
| 다른 관계 유형 영향 없음 | `test_other_relationship_change_inside_transaction_aborts` | 다른 관계가 바뀌면 지문 불일치로 예외(rollback) |
| 중복 방지·안전 | 원장 relation_key 중복 / (대상, 유형) 중복 거부, 기존 모호 중복 미선택, relation_key 없는 기존 관계 거부, 승인 건수 불일치 시 쓰기 전 중단, 쓰기 범위·읽기 구문 검사, 지문 라벨 순서 무관, 고아 분류 | 모두 통과 |

기존 Neo4j 테스트와 함께 실행한 결과: **103건 실행, 95 통과, 8 건너뜀, 실패 0**. Codex 기존 82건(74 통과·8 건너뜀)에 신규 21건이 더해졌다.

---

## A-4. 현재 Codex 구현과의 차이와 통합 방안

| 항목 | 현재 Codex 구현 | 동기화 모듈 | 통합 시 변경 (Codex 작업 마무리 후) |
|---|---|---|---|
| 관계 식별 | `key = sha256(유형, 끝점, 원본 JSON 전체)` → rel_priority 포함 | (출발, relation_key) + 보조 유일키 | `neo4j_dry_run.Preview.edge` 호출 시 dp_related_to만 key 재료를 `{relation_key}`(또는 결정된 식별자)로 바꾸는 것을 권장. 그러면 key가 가변 속성에 흔들리지 않는다. 바꾸면 기존 6건 key가 달라지므로 **운영 적재 전에 결정**해야 한다 |
| 쓰기 | 전체 MERGE, 삭제 없음 | dp_related_to만 생성·갱신·삭제 | `neo4j_load_draft.write_transaction`의 관계 반복에서 dp_related_to를 빼고, 같은 트랜잭션 안에서 `sync_transaction`을 호출. 사후 key 검사는 그대로 둔다. 적재기의 "삭제 구문 없음" 테스트는 적재기 파일에 그대로 유효하다(삭제는 동기화 모듈에만 있음) |
| 사전·사후 검증 | `compare_graph` (라벨 집합·전체 속성) | 같은 `compare_graph` 재사용 + 트랜잭션 내부 지문 | `neo4j_validate.run()` 결과에 `orphans.source_preexisting/load_mismatch` 분류와 dp_related_to 식별자 검사(방향·to_bnft_id·중복)를 추가한다. `ok` 판정 조건은 그대로 둔다 |
| 고아 처리 | 고아 1건이면 `ok=false` | 동일 판정 + 원인 분류 | 변경 없음(완화 금지) |
| GraphRAG 조회 | `benefit_relations` 명시 조회 추가 (Codex) | 영향 없음 | — |

---

## A-5. 운영 적재 결과 (2026-11-05, 승인 범위: 신규 dp_related_to 6건)

> **결정:** 관계 식별 기준 = (출발 혜택, relation_key). PostgreSQL 유일성 제약과 근거 참조 구조를 따른다.

### 적재 전 확인

| 확인 항목 | 결과 |
|---|---|
| Codex 파일(`neo4j_dry_run.py`, `neo4j_load_draft.py`, `neo4j_validate.py`, `neo4j_validation.cypher`) 변경 여부 | 사전 검증 이후 수정 시각 동일, 무수정 |
| 6개 관계 key 1:1 비교 (아래 표) | 변환기(prepare) key = 동기화 모듈 저장 key = sha256 재계산 값 = 검증기의 "누락" key, **6/6 일치** |
| 저장할 속성 = 검증기 기대 속성(`key`, `source_json`, `relationship_properties`) | 6/6 일치 |
| 테스트 | 동기화 27건(적재기 호환 6건 추가) 포함 Neo4j 전체 **109건 실행, 101 통과, 8 건너뜀, 실패 0** |

| 출발 | relation_key | rel_type_cd | 대상 | 관계 key (변환기·검증기·동기화 공통) |
|---|---|---|---|---|
| 20261105_000179 | fixed_fallback | FALLBACK_AFTER_CAP | 20261105_000178 | e0196578cf88c6ddb603b7b08a3e95aa2615835ccc654d9a26d314087503f806 |
| 20261105_000179 | special_basic_exclusive | MUTUALLY_EXCLUSIVE | 20261105_000178 | 8390646e584542e643e498819285de2824829d7711772d76700a5f284e1bfbbd |
| 20261105_000179 | special_over_basic | OVERRIDES | 20261105_000178 | 8b03b9b897bc4045a14b03d60c068a20ddc066aa79a46dea5bf4c68f7ce2ac34 |
| 20261105_000180 | recurring_fallback | FALLBACK_AFTER_CAP | 20261105_000178 | 0a9980d0ebe3b9a0de58c071ee5187ecc85283295d202582abbf538a0abf0c0c |
| 20261105_000180 | special_basic_exclusive | MUTUALLY_EXCLUSIVE | 20261105_000178 | b17745a07f412172a5f2a362828a02fd869f52e511239c09ed6cd107628f503a |
| 20261105_000180 | special_over_basic | OVERRIDES | 20261105_000178 | 0af0b44ab08029af03b5e9517fc261b891ebf042af05a75ed5019575ca815d79 |

### 적재 실행

```
neo4j_relation_sync --apply --confirm APPROVED_DP_RELATED_TO_SYNC --expect '{"create":6,"update":0,"replace":0,"delete":0}'
```

결과: `committed {"applied": {"create": 6, "update": 0, "replace": 0, "delete": 0}, "related_after": 6}`

트랜잭션 안의 적용 전·후 지문이 동일하다:
- 노드 937, `ea153daa8836…`
- 기타 관계 1,297, `63e4c3a63ae4…`

### 적재 후 독립 검증 (새 읽기 전용 세션)

| 항목 | 결과 |
|---|---|
| 노드 / 관계 | **937 / 1,303** (dp_related_to 6) |
| 6건 방향·대상 | 모두 `dp_card_bnft` → `dp_card_bnft`, 카드 42 내부, 대상 `card_bnft_id` = `to_bnft_id` = 20261105_000178 |
| 6건 속성 | `key`, `source_json`, `relation_key`, `rel_type_cd`, `to_bnft_id` (rel_priority null → 속성 없음) |
| 식별자 (출발, relation_key) 중복 / (출발, 대상, rel_type_cd) 중복 | 0 / 0 |
| `neo4j_validate` (Codex 검증기) | 모든 차이 **0**, SQL↔Cypher 4종 일치, 범위 위반 0. `ok=false`, 원인은 **기존 고아 문서 1건만**(source_preexisting, 숨기지 않음) |
| 동일 입력 재실행(preview) | create 0 / update 0 / replace 0 / delete 0 / unchanged 6. 지문 적재 전과 동일 |

## A-6. 기존 loader와의 호환성과 향후 운영 방식

### 같은 관계를 같은 key로 본다

- 변환기(`neo4j_dry_run`→`prepare`), 전체 적재기(`neo4j_load_draft`), 검증기(`neo4j_validate`), 동기화 모듈의 관계 key가 **같은 값**이다.
- 따라서 **지금 전체 loader를 다시 실행해도 중복 생성되지 않는다.** 적재기는 `MERGE … {key:$key}`로 같은 관계를 찾고, 같은 속성을 다시 기록한다(테스트 `test_full_loader_after_sync_creates_no_duplicate`).
- 반대로 적재기로 먼저 만들어진 관계도 동기화 모듈은 변경 0으로 본다(`test_sync_after_loader_changes_nothing`).

### key가 달라지는 경우와 그 위험 (원장 관계 내용이 바뀔 때)

| 원장 변경 | 동기화 모듈 | 전체 loader 단독 실행 |
|---|---|---|
| rel_priority·rel_type_cd 변경 | 같은 관계의 속성·key를 갱신 (update) | key가 바뀌어 새 관계를 MERGE → 사후 key 검사 실패로 **rollback** (중복이 commit되지는 않음, 반영도 안 됨) |
| 값이 null로 바뀜 | `SET r = $props`로 속성 제거 | `r += extra`라 옛 값이 남음 |
| 대상 변경 | 그 관계만 교체 (replace) | 위와 같이 rollback |
| 원장에서 삭제 | 그 관계만 삭제 | 삭제 구문이 없어 사후 검사 실패 → rollback |

→ **dp_related_to의 생성·변경·삭제 책임은 동기화 모듈이 갖는다.** 전체 loader는 원장이 바뀐 관계를 반영하지 못하고 실패로 멈추므로 데이터를 망가뜨리지는 않는다. 다만 동기화를 먼저 실행해야 통과한다.

### 운영 절차 (현행, Codex 파일 무수정 상태)

1. PostgreSQL `relation_list` 변경·등록 후 `neo4j_relation_sync`를 preview로 실행해 계획 건수를 확인한다.
2. 계획을 승인하면 `--apply --confirm APPROVED_DP_RELATED_TO_SYNC --expect '<승인 건수>'`로 실행한다.
3. `neo4j_validate`로 확인한다.
4. 노드·다른 관계가 바뀐 적재가 필요하면 **동기화 → 전체 loader → 검증** 순서로 실행한다.

### 통합 권고 (Codex 작업 마무리 후, 별도 승인)

1. `neo4j_load_draft.write_transaction`의 관계 반복에서 `dp_related_to`를 제외하고, 같은 쓰기 트랜잭션 끝에서 `neo4j_relation_sync.sync_transaction`을 호출한다. 그러면 전체 적재 1회로 노드·관계·혜택 간 관계가 함께 일관되게 반영되고, 삭제 권한은 동기화 함수에만 남는다.
2. 그때 기대 건수 승인(`expected_counts`)을 적재기 미리보기 출력에 포함한다.
3. 선택: `neo4j_dry_run`에서 dp_related_to의 key 재료를 (출발, relation_key)로 바꾸면 key가 가변 속성에 흔들리지 않는다. 운영 6건의 key가 바뀌므로 이때는 동기화 모듈로 6건 replace를 승인받아 실행한다.
4. `neo4j_validate`에 고아 원인 분류를 추가한다(`ok` 조건 유지).

---

# B. 고아 문서 `20261103_000012` 원인 분석 (관계 동기화와 별개)

## B-1. 사실 확인 (PostgreSQL 읽기 전용)

| 항목 | 값 |
|---|---|
| 문서 | `HANA_JP002_20260326`, "공통_JCB브랜드서비스_JP002_20260326", `doc_type_cd=BRAND_SERVICE`, `doc_status=ACTIVE`, 1쪽, 2026-11-03 등록 |
| 상위 연결 | `card_product_doc` **0건**, `card_common_doc` **0건** |
| JCB 공통서비스 | `card_common`에 JCB 항목 **없음** (등록된 14개는 VISA·AMEX·MASTERCARD·UPI·우리 계열) |
| 하위 데이터 | 페이지 1, 청크 1, 추출 스테이징 0, 원문 근거 0, 근거 연결 0 |
| 다른 29개 문서 | 모두 상위 연결 1건 이상. 상품설명서 → `card_product_doc`, 브랜드 안내 → `card_common_doc`. `20261102_000004`는 둘 다 있음 |
| PG 정합성 뷰 | `v_card_integrity_issue`의 현재 gate는 `evidence_not_approved` 201, `evidence_item_key_missing` 10뿐이다. **소유자 없는 문서는 검사하지 않는다** |

## B-2. 변환 누락인가, 원천 연결 부재인가

**원천 연결 부재다. 변환 누락이 아니다.**

- `neo4j_dry_run.build`는 `card_doc`을 모두 노드로 만들고, `dp_has_document`는 `card_product_doc`·`card_common_doc` 행에서만 만든다(`neo4j_dry_run.py:278-284, 358-362`).
- 연결 행의 대상이 없으면 조용히 건너뛰지 않고 오류로 적재를 중단한다. 따라서 매핑이 관계를 흘릴 경로가 없다.
- 원장 그래프에도 이 문서로 들어오는 `dp_has_document`가 없다. 연결은 `dp_in_document`(페이지 → 문서) 1건뿐이고, Neo4j와 같다. 그래서 `classify_orphans`가 `source_preexisting`으로 분류했다.
- 이력: 2026-11-03 Codex 인계 문서(`CODEX_HANDOFF_20261103.md` §5·§6·§8)에 이미 orphan으로 보고됐다. 이번 `dp_related_to` 변경 이전부터 있던 상태다.

## B-3. 원인 판단

| 구분 | 판단 |
|---|---|
| 데이터 | **직접 원인.** 등록 시 "문서만 등록, 공통서비스 연결 보류"로 의도적으로 남겼다. 사유: 원문에 JCB **Platinum과 Prestige가 함께** 나와 어느 공통서비스(등급)에 연결할지 확정하지 못함. 인계 지침: "JCB 등급 연결은 확인 전 만들지 않는다" |
| DB 설계 | **보조 원인.** ① "등록됐지만 소유 미확정" 상태를 표현할 값이 없다. `doc_status`는 CHECK 없이 전부 `ACTIVE`라 보류 문서와 정상 문서가 구별되지 않는다. ② PG 정합성 뷰가 소유자 없는 문서를 잡지 못해, 문제가 Neo4j 검증에서야 드러난다. 반면 `card_common_doc` PK가 `(card_common_id, card_doc_id)`라 한 문서를 여러 공통서비스(Platinum·Prestige)에 연결하는 해법은 현재 설계로 가능하다 |
| Python 매핑 | **원인 아님.** 원장을 그대로 투영했다. 고아 검사도 의도대로 동작했다 |

## B-4. 업무적 허용 여부

- **일시적 보류 상태로는 허용된다.** 근거·추출 결과가 0건이라 혜택 답변에 쓰이지 않는다. 어떤 카드·공통서비스에서도 도달할 수 없어 GraphRAG 검색 경로에 나타나지 않는다.
- **영구 상태로는 부적절하다.** `ACTIVE`인데 소유자가 없어 "유효한 공식 문서"처럼 보이고, 전체 검증이 계속 실패해 다른 실제 오류를 가릴 수 있다.
- 이 문서는 하나카드가 공개한 실제 JCB 브랜드 서비스 PDF(원본 URL·SHA-256 기록됨)이므로 **존재해야 하는 문서**다. 삭제 대상이 아니다.

## B-5. 해결 방안 (PostgreSQL 원장 우선, 승인 후 실행)

1. **업무 확인(선행):** JP002 원문(1쪽, 2,477자)에서 혜택별로 Platinum·Prestige 중 어느 등급에 적용되는지 확인한다. 하나카드 상품 중 JCB 브랜드 상품이 있는지도 확인한다.
2. **정상 경로로 연결:**
   - 기존 공통서비스 등록 절차로 `card_common`(예: `JCB_PLATINUM`, `JCB_PRESTIGE`)을 만든다.
   - `card_common_doc`에 확정된 등급만큼 연결한다. 두 등급이면 2행이고, PK상 허용된다.
   - 공통 혜택 추출·등록 후 Neo4j는 기존 적재로 `dp_has_document`를 받는다 → 고아가 자동 해소된다. **Neo4j에서 직접 연결하거나 지우지 않는다.**
3. **범위 밖으로 판단할 경우(대안):** 문서를 지우지 않고 보류·비활성 상태 값(예: `doc_status='HOLD'`)을 정의한다. 그다음 `neo4j_dry_run`이 그 상태의 문서를 적재 대상에서 제외하고 "제외 목록"으로 보고하도록 바꾼다. 상태 코드 정의는 DDL·코드 변경이라 별도 승인이 필요하다.

## B-6. 재발 방지

| 단계 | 방안 |
|---|---|
| 등록 시 | 문서 등록 서비스에서 `BRAND_SERVICE`·`PRODUCT_GUIDE` 문서를 소유 연결 없이 등록할 때 명시적 보류 상태와 사유를 함께 남기게 한다(보류가 기본값이 되지 않게) |
| PG 정합성 | `v_card_integrity_issue`에 `doc_owner_missing` gate 추가: `card_doc` 중 `card_product_doc`·`card_common_doc` 모두 없는 행. 등록 전후 정합성 비교(`_assert_no_new_errors`)가 신규 발생을 자동으로 막는다 (DDL 변경, 승인 필요) |
| Neo4j 미리보기 | `neo4j_dry_run` 통계에 "소유자 없는 문서" 목록을 추가해 적재 전에 보이게 한다(`unlinked_evidence`와 같은 방식) |
| Neo4j 검증 | `neo4j_validate`에 고아 원인 분류(source_preexisting / load_mismatch)를 넣는다. `ok` 판정은 유지하고, 하드코딩한 예외 목록으로 숨기지 않는다 |

---

## 부록: 실행 기록 (모두 읽기 전용)

- `neo4j_load_draft` preview(Neo4j 미접속), `neo4j_validate`, `neo4j_relation_sync` preview
- 쓰기 Cypher `EXPLAIN` 3건
- PG 함수 정의·제약·문서 연결 조회
- 실데이터 메모리 모의 적용
- 측정·조회 스크립트는 세션 임시 폴더에 있고 저장소에 추가하지 않았다.
