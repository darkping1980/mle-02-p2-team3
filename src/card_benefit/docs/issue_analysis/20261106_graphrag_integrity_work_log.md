# GraphRAG 데이터 무결성 보정 — 전체 작업 이력

- 기준 문서 작성: 2026-11-06 (Asia/Seoul)
- 저장소: `C:\\myproject\\workspace\\mle-02-p2-team3`
- 목적: GraphRAG 카드 원천 데이터, PostgreSQL `item_data`, Neo4j `source_json`, RULE/COND 근거 관계의 분석·보정 준비·검증을 시간순으로 추적한다.
- 운영 데이터 정책: 이력에 `예정`, `미리보기`, `실제 반영` 상태를 분리한다. 이 문서 작성 시점에는 PostgreSQL 보정 0건, Neo4j 적재 0건이다.
- 민감정보 정책: DB URL, 비밀번호, API key, 토큰, 실제 접속 문자열을 기록하지 않는다.

> 이 파일은 전체 이력의 색인과 요약이다. 재현에 필요한 SQL, Cypher, 상세 함수 흐름, 원문 대조 결과는 연결한 개별 분석 문서에 남긴다. 새 작업을 시작할 때 먼저 이 파일에 현재 상태와 작업 범위를 기록하고, 작업 후 명령·결과·실패·미해결 사항을 갱신한다.

## 0. 현재 기준 상태 — 작업 시작 시

### Git 및 소스

| 항목 | 확인 결과 |
|---|---|
| branch | `main` |
| HEAD | `1fcd3e636aa66a284117b6bcf200616ca5133c0a` |
| HEAD 시각 | `2026-11-06T16:02:21+09:00` |
| HEAD 제목 | `GraphRAG 구간별 한도 검증 개선 및 데이터 누락 원인 문서화` |
| upstream | `origin/main`이 HEAD와 동일 |
| 작업 트리 | 시작 시 clean (`git status --short` 출력 없음) |
| P0/P1/P2·POINT II 선택기·더 심플 검증 | HEAD 소스와 테스트에 존재. 관련 구현·결과 문서 참조 |
| 보정 실행 도구 | `payment_card/db_pipeline/limit_struct_backfill.py`; 읽기 전용 SELECT와 `--dry-run`만 존재. UPDATE/INSERT 기능 없음 |
| PostgreSQL/Neo4j 쓰기 | 이 작업 시작 시점까지 없음. 이번 요청 범위에서도 실행 금지 |

실행 전 작업 범위(코드 수정 전에 기록): 기존 dry-run의 제안 payload와 reviewed extraction fixture를 재사용해 승인 단계용 PostgreSQL writer를 최소 확장하고, 기본 동작은 dry-run으로 유지한다. writer는 명시적 실행 플래그·대상 DB 확인·durable preimage·PK/fixture 검증·하나의 트랜잭션·조건부 롤백 기록이 없으면 쓰지 않도록 설계한다. 실행기·rollback 테스트는 mock connection으로만 시험한다. 운영 DB, Neo4j, 배포, Git commit/push에는 접근하지 않는다.

## 1. 문제 발생 이력

| 시점 | 확인된 현상/원인 | 관련 근거 |
|---|---|---|
| 2026-11-06 이전/기존 Streamlit 실행 | 질문의 상세 화면은 초기 `float(None)` TypeError로 실패했다. 정확한 최초 실행 timestamp와 당시 app_log ID는 이 이력에서 확인하지 못해 특정하지 않는다. | [tier.value NULL TypeError 분석](20261106_tier_value_none_typeerror.md) |
| P0 반영 후, 2026-11-06 로컬 화면 재현 | 사용자 질문 “더 심플 하나카드의 월납 요금 할인 한도는 지난달 이용액 구간에 따라 어떻게 달라져?”에 “10,000원과 15,000원은 확인되지만 실적 구간별 적용 한도는 미확정”이라는 오답이 화면에 표시됐다. | [더 심플 구간 한도 원인·수정](20261106_more_simple_limit_tier_root_cause_and_fix.md) |
| 읽기 전용 PG/Neo4j 감사 | PG 대상 `card_product_item` PK `(22,'20261105_000099')`의 `item_data={}`. 실적 조건 r1/r2와 limit text 숫자 둘은 각각 있으나 연결 구조가 없다. 대응 Neo4j BENEFIT `source_json`에는 `item_data`가 없다. r1/r2 `value_num` NULL은 지급액/규칙 값과 누적 한도가 다른 의미이므로 월 한도를 `value_num`에 대입할 수 없다. | [매핑 감사](20261106_postgresql_neo4j_mapping_query_audit.md), [더 심플 상세 분석](20261106_more_simple_limit_tier_root_cause_and_fix.md) |
| P0·P1·P2 검증 및 보정 미리보기 | P1 등록 코드는 신규 행에서 한도 구조와 위치 검증된 조건 근거를 보존하도록 하고, P2 적재는 `item_data`를 Neo4j source JSON에 전달하도록 했다. 기존 행은 자동 수정되지 않는다. `limit_struct_backfill.py`는 현재도 read-only preview 전용이다. | [P0/P1/P2 구현 결과](20261106_graphrag_p0_p1_implementation_result.md), [DB 복원·보정 사전 검증](20261106_db_restore_and_correction_final_preflight.md) |
| 이번 BENEFIT_LIMIT 수정 | TIER_OPEN 지급액 선택 불확실성을 BENEFIT_LIMIT의 한도 구간 매핑에 노출하던 관련성과, 구조화 tiers가 없는 경우 구간-한도 pair를 막지 못하던 검증 문제가 확인·수정됐다. | [더 심플 구간 한도 원인·수정](20261106_more_simple_limit_tier_root_cause_and_fix.md) |

## 2. 변경 이력 — 커밋 및 구현 단계

정확한 시간은 Git author timestamp 또는 당시 문서 timestamp로 확인할 수 있는 경우에만 쓴다. 출처가 없는 작업 timestamp를 추정하지 않는다.

### 2.1 과거 커밋에서 확인한 흐름

| Git 시각 (KST) | 커밋 | 목적/결과 | 상세 문서 |
|---|---|---|---|
| 2026-11-06 09:12:19 | `fd3f195a71f40122c9719d226515b42dda46c6cc` — PDF evidence provenance logs | `pdf_evidence_text`에 Neo4j owner·문서·페이지·청크 추적성 보강 | [P0/P1 구현 결과의 관련 선행 작업](20261106_graphrag_p0_p1_implementation_result.md) 및 Git history |
| 2026-11-06 10:08:42 | `28b7024c429a68db9f44db75424ee4f379fc2a8c` — Neo4j references in answer detail logs | `detail_text` 답변 point에 실제 Neo4j 참조를 연결 | Git history |
| 2026-11-06 11:22:46 | `0359181552d5a89af9976908ef354a8fe1b1cead` — TypeError 원인 문서 | `tier.value=None` 변환 오류 조사 문서 추가 | [tier.value NULL TypeError 분석](20261106_tier_value_none_typeerror.md) |
| 2026-11-06 12:12:18 | `fcb2a5111dfad4eec17ec6431fd314f22bbeb451` — Claude 오류 원인 요약 | 인수인계/원인 요약 문서 기록 | [Claude→Codex handoff](20261106_claude_to_codex_handoff.md) |
| 2026-11-06 14:22:32 | `9283c55132ae47b513911b856cb765cf8625f052` — 50문항 검증 결과 관련 내용 | Notion 기반 PDF QA 수치를 별도 품질 과제로 남김 | [Codex 인수 검증 결과](20261106_codex_handoff_verification_result.md) |
| 2026-11-06 16:02:21 | `1fcd3e636aa66a284117b6bcf200616ca5133c0a` — GraphRAG limit-tier validation | 더 심플 답변 검증 개선, 원인 문서, DB restore preflight 문서가 `main`에 커밋된 HEAD | [더 심플 상세 분석](20261106_more_simple_limit_tier_root_cause_and_fix.md), [DB 복원 사전 검증](20261106_db_restore_and_correction_final_preflight.md) |

커밋 통계상 `1fcd3e6`은 `card_graphrag.py`, 두 테스트 파일, 두 분석/preflight 문서를 변경한다. `main`과 `origin/main`은 이번 시작 확인 시 동기화돼 있었다. 더 앞선 P0/P1/P2 작업의 개별 구현 커밋 ID는 현재 선택한 Git history에서 별도로 확정하지 않는다. 해당 범위와 결과는 구현 결과 및 인수 검증 문서를 정본으로 참조한다.

### 2.2 단계별 구현 이력

| 단계 | 목적 및 원인 | 변경 파일/함수 | 데이터 영향 및 검증 | 상태 |
|---|---|---|---|---|
| P0 — NULL 지급값 안전성 | `tier.value=None`에서 `float(None)` 예외. NULL은 0이 아니며 구간은 보존해야 함. | `card_graphrag.py`: `tier_token`, `tier_label`, `distorts_tier`, `picks_single_tier`, `tier_is_quoted`, `validate_answer` 및 지급값 비교 호출부 | PG/Neo4j 쓰기 없음. P0 전용 null payout 테스트 기록은 [P0/P1 구현 결과](20261106_graphrag_p0_p1_implementation_result.md). | 완료·커밋 |
| P1 — 신규 등록 정보 손실 방지 | 신규 등록 시 한도와 rule mapping, 조건 근거가 평문 처리 또는 누락됨. | `extraction_service.py`: `limit_struct`, `limit_tiers_from_extraction`; `product_benefit_service.py`: `_register`, `_links`; SQL repository insert | 신규 등록 경로만 변경. 기존 22/099·23/100·20/092 행은 자동 변경되지 않음. P1 테스트 결과는 구현 문서 참조. | 완료·커밋 |
| P2 — Neo4j 및 답변 구조 | 적재 SELECT가 `item_data`를 누락하고 GraphRAG 구간 한도 구조 전달/검증이 부족함. | `neo4j_dry_run.py`, `neo4j_validate.py`, `card_graphrag.py`: `benefit_context`, `limit_tier_view`, `distorts_limit_tier` | 코드 반영. 기존 Neo4j 데이터는 재적재되지 않음. 17 P2 단위 테스트가 통과했다고 handoff 결과에 기록. | 구현 완료·실데이터 재적재 미완료 |
| POINT II 선택 정책 | 공식 원문은 실적 하한 30/60/120만원만 명시. 프로그램은 충족한 가장 높은 하한을 고르는 별도 파생 정책을 구현하며 원본 상한은 변경하지 않음. | `card_graphrag.py`: `point2_shared_cap_policy`, `previous_month_spend`, `benefit_context`, `distorts_limit_tier`; `test_p2_limit_tiers.py` | 경계값 및 카드 ID scope 테스트. 정책은 카드 23/100의 정확한 benefit ref에만 적용. | 완료·커밋 |
| 더 심플 추가 수정 | TIER_OPEN이 BENEFIT_LIMIT의 월 한도 불확실성과 섞이고, 구조 유무에 따른 pair 검증 차이가 없음. | `card_graphrag.py`: `affects_question`, `_unstructured_limit_pair_claim`, `limit_tier_answer_problem`, `validate_answer`, `answer_text_problem`; tests | read-only fixture/mock. 마지막 검증 47 passed. 실제 DB/App에 반영 및 재질문은 미완료. | 코드·문서 완료·커밋 |

각 단계의 정확한 diff와 재현 코드는 [상세 원인 문서](20261106_more_simple_limit_tier_root_cause_and_fix.md), [P0/P1 구현 보고서](20261106_graphrag_p0_p1_implementation_result.md), [수정 계획](20261106_graphrag_data_loss_fix_plan.md)를 참조한다.

## 3. 데이터 변경 이력

### 3.1 PostgreSQL

| 대상 | 변경 전 | 변경 예정 (기존 dry-run) | 실제 반영 | SQL/백업/롤백 |
|---|---|---|---|---|
| 카드 22/099: `(22,'20261105_000099')` | `item_data={}`; `item_limit_txt`에 10,000/15,000원; r1 300k~800k, r2 800k+, r3 기타; 지급 `value_num` NULL | `limits`, `rule_limits`, 구조 확실한 `limit_tiers`; RULE/COND 연결 3건 | 없음 | 기존 dry-run preimage는 화면 payload뿐 durable 백업 아님. 백업 경로/격리 복원 한계는 [DB 복원 사전 검증](20261106_db_restore_and_correction_final_preflight.md). |
| 카드 23/100: `(23,'20261105_000100')` | `item_data={}`; 공식 문서상 특별·추가 적립 공유 통합 월 한도 10k/20k/50k; 원본 구간 상한 없음 | `limits`, `rule_limits`; `limit_tiers`는 만들지 않고 `cond_max_amt_excl=NULL` 유지; RULE/COND 3건 | 없음 | UPDATE/INSERT 미실행. POINT II 선택기는 프로그램 파생 정책으로만 동작. |
| 카드 20/092: `(20,'20261105_000092')` | `item_data={}`; 100k 기본 + 100k 추가 누적, 기간 추출 UNKNOWN | `limits`, `rule_limits`; 배타적 `limit_tiers` 없음; RULE/COND 2건 | 없음 | UPDATE/INSERT 미실행. 누적 의미 및 기간 UNKNOWN 유지. |
| 근거 연결 총 8건 | 사전 조사에서 natural-key 중복 0건으로 dry-run 표시 | 카드22 3 + 카드23 3 + 카드20 2. PK `evidence_link_id`는 실행 시 DB 발급 | 없음 | repository SQL은 `card_source_evidence`의 doc/page/chunk를 물려받고 `ON CONFLICT ... DO NOTHING` 패턴을 사용. 신규 실행기는 같은 자연키를 사전 검사하고 `RETURNING evidence_link_id`를 기록해야 함. |

공식 PDF/추출 원본과의 대조, 각 evidence ID의 document/page/chunk/start/end 정보는 [DB 복원 사전 검증](20261106_db_restore_and_correction_final_preflight.md) 및 [P0/P1 구현 결과](20261106_graphrag_p0_p1_implementation_result.md)에 있다. 검증된 extraction fixture를 재사용하고 같은 PDF를 다시 추출했다고 주장하지 않는다.

### 3.2 PostgreSQL 백업과 복원 상태

- 기존 backup directory: `src/data/backup/pre_calc_cleanup_20261106_140723/` (`postgres_db_pipeline.json`, `catalog.json`, `schema_ddl.sql`). 문서 기록상 PostgreSQL 17.11, 테이블 20개, 행 4,864개, 백업/현재 행 대조 `VERIFY OK`.
- `VERIFY OK`는 백업 대조이지 복원 리허설이 아니다. JSON+DDL은 native `pg_dump` archive가 아니며, 격리 PostgreSQL 17, extension/role 준비, JSON loader가 검증되지 않아 실제 restore test는 수행되지 않았다.
- 3행/8 link의 백업 preimage와 선택적 rollback 계획은 사전 검증 문서를 참조한다. 실제 쓰기 전 durable 백업·격리 restore 성공이 선행돼야 한다.
- Git 추적에 백업 파일을 추가하지 않는다. 백업 경로에는 운영 데이터가 있으므로 민감정보와 함께 커밋 제외 대상이다.

### 3.3 Neo4j

- 이전 read-only 시점의 관측값: 1,635 nodes / 2,702 relationships. `item_data` 불일치 34건은 이전 인수 문서 결과이며 현 시점 재조회값이 아니다.
- 재적재 예상 1,643/2,718은 8개 신규 근거 link가 실제 신규이고 전체 graph projection이 동일할 때의 dry-run 추정값일 뿐, 실제 수치로 보고하지 않는다.
- 현재 저장소의 Neo4j loader는 전체 `dp_` graph MERGE를 수행할 수 있지만 운영 보정은 미승인. 전체 MERGE 실패·stale relation·commit ambiguity 및 stale property 위험과 복구 조건은 사전 검증 문서에 기록돼 있다.
- Neo4j 변경/재적재 횟수: 0. 신규 쓰기 전 Aura backup export·restore 가능한 격리 인스턴스 검증이 필요하다.

## 4. 테스트 및 품질 검증 이력

| 테스트 범위 | 명령/결과 | 환경·제한 | 해석 |
|---|---|---|---|
| P0/P1/P2 인수 당시 전체 회귀 | `pytest -q -p no:cacheprovider payment_card/tests payment_card/db_pipeline`; 682 passed, 2 failed, 20 skipped, 99 subtests passed | 당시 DB/Neo4j/LLM 환경 변수를 빈 값으로 둠. 이전 실패 2건은 `test_unresolved_tier_cannot_be_decided_in_natural_text` 및 `StreamlitTests::test_example_only_fills_input`. 당시 문서에서 이전 기준선에 같은 유형 실패가 기록돼 있다고 판단했으나 원본 과거 로그가 없어 전체 개별 항목 동일성은 단정하지 않음. | 전체 이슈 개선 검증은 아님. 외부 DB 통합 skip 있음. 자세한 기록은 [인수 검증 결과](20261106_codex_handoff_verification_result.md). |
| 카드23 selection policy | `test_p2_limit_tiers.py` 경계 테스트 | Stub/fixture, 실적 금액 경계 299,999 / 300,000 / 599,999 / 600,000 / 1,199,999 / 1,200,000 | 가장 높은 충족 하한 선택, 원본 `cond_max_amt_excl` 유지, scope 제한 테스트 통과. |
| 더 심플 답변 수정·NULL/P2 관련 | 2026-11-06에 `test_p2_limit_tiers.py test_tier_null_payout.py -k "not LiveSimpleMonthlyTests"`: 42 passed, 1 deselected | Stub/fixture. 실제 Neo4j 통합 제외, 유료 LLM 호출 없음. | 구조화 한도 정답 수용/미확정 거부, 구조 부재 임의 pair 거부/분리 한도 안내 허용, P0 NULL 회귀 포함. |
| BENEFIT_LIMIT 미확정 routing | `test_card_graphrag.py -k "tier_payout_uncertainty or limit_intent_keeps_conditions_for_unresolved_items or same_tier_issue_is_merged_for_payment_question or tier_issue_is_not_shown_for_count_limit_question"`: 4 passed, 163 deselected | Stub. | 한도 intent에서 지급액 불확실성 분리; 기타 질문 안전장치 테스트. |
| 카드20 누적 구조 | `test_limit_struct.py -k "cumulative_bonus_caps_are_not_turned_into_exclusive_tiers"`: 1 passed, 13 deselected | fixture. | 누적 10만+추가10만을 배타적 구간으로 변환하지 않음. |
| 신규 보정 실행기 | 현재 단계 진행 예정 | mock/fake DB connection만. 실제 DB 연결 테스트 금지. | 아래 진행 기록에 실제 작성 후 결과 추가. |
| 실제 Streamlit | 사용자의 수정 전 로컬 오답 재현 있음. 수정 후 UI 재질문 없음. | 로컬 프로세스 재시작 및 browser CUA 수행 안 함. | 앱 수정 후 확인은 별도 운영/사용자 일정에 남음. |
| 실제 Neo4j 통합 테스트 | 과거 일부 read-only 검증 문서에 결과 기록. 이번 새 writer용 테스트에는 사용 안 함. | Neo4j 쓰기/재적재 금지. | 이번 단계에서 새 통합 테스트를 완료했다고 주장하지 않음. |

50문항 PDF QA(Notion 검수) 요약은 정답 27건, 답변 오류 19건, 실행 오류 4건이다. 이는 별도 답변 품질 backlog이며 P0~P2로 19건이 해결됐다고 간주하지 않는다. QA 재분류·각 실행 로그 대응은 [Codex 인수 검증 결과](20261106_codex_handoff_verification_result.md)와 [ONE PICK/STYLE QA 이슈](20261106_onepick_style_cashback_tier_qa_issue.md)를 참조한다.

## 5. AuraDB Free backup 조사 상태

### 사실과 미확정 구분

- 사용자가 기존 운영 환경을 AuraDB Free라고 밝혔다. 이 작업에서 Aura Console에 로그인하거나 인스턴스 콘솔/DB ID를 직접 확인하지 않았다.
- 2026-11-06에 확인한 Neo4j 공식 문서의 [AuraDB quotas and limits](https://neo4j.com/docs/aura/quotas-and-limits/)는 Free에서 backup frequency `On-demand`, retention `1 backup at a time`으로 표시한다.
- 공식 [Backup, export, restore](https://neo4j.com/docs/aura/managing-instances/backup-restore-export/) 문서 본문은 Free에 on-demand snapshot을 설명하지만, tier별 상세 표의 Free 행은 가용 기간을 `N/A`로 표시하는 문서상 표현 불일치가 있다. 공식 [Free → 다른 Aura tier migration](https://neo4j.com/docs/aura/tutorials/migration-free/) 문서는 Free의 snapshot/dump export 과정을 안내한다.
- 따라서 제품 자료는 Free에서 on-demand backup/export 경로가 제공될 수 있음을 지지하지만, 이 특정 인스턴스의 현재 Snapshot 메뉴·상태·export 가능 여부는 미확정이다. 사용자가 콘솔에서 확인해야 하며 실제 backup 생성/복원은 하지 않았다.
- 필요한 확인: 대상 instance ID/DB 이름/Neo4j 버전, Aura Console > instance > Inspect/Backup & Restore/Snapshots의 실제 메뉴, on-demand snapshot 생성 가능 여부, Completed/Exportable 여부, 파일 형식/크기, 별도 격리 인스턴스 생성·복원 권한.

Aura Free는 “backup 파일을 만들 수 있다”와 “새 인스턴스에 복원해 검증했다”를 구분한다. snapshot/export만으로 복원 검증 완료라고 기록하지 않는다. 실제 Free snapshot 복원/clone 가능 여부는 콘솔 기능과 최신 tier 제한을 확인한 뒤 갱신한다.

## 6. 문서 색인 — 요청 문서 존재 여부

| 문서 | 상태 | 주된 내용 |
|---|---|---|
| [20261106_tier_value_none_typeerror.md](20261106_tier_value_none_typeerror.md) | 존재 | NULL→float TypeError 조사 |
| [20261106_postgresql_neo4j_mapping_query_audit.md](20261106_postgresql_neo4j_mapping_query_audit.md) | 존재 | PG↔Neo4j mapping, P2 이전 누락 감사 |
| [20261106_graphrag_data_loss_fix_plan.md](20261106_graphrag_data_loss_fix_plan.md) | 존재 | P0/P1/P2 설계와 단계별 방안 |
| [20261106_graphrag_p0_p1_implementation_result.md](20261106_graphrag_p0_p1_implementation_result.md) | 존재 | P0/P1 구현, 결과 및 당시 확인 |
| [20261106_claude_to_codex_handoff.md](20261106_claude_to_codex_handoff.md) | 존재 | Claude→Codex 인수인계 |
| [20261106_codex_handoff_verification_result.md](20261106_codex_handoff_verification_result.md) | 존재 | P0/P1/P2 검증, 회귀, DB 현황 |
| [20261106_onepick_style_cashback_tier_qa_issue.md](20261106_onepick_style_cashback_tier_qa_issue.md) | 존재 | 별도 ONE PICK/STYLE 답변 품질 문제 |
| [20261106_db_correction_preflight_result.md](20261106_db_correction_preflight_result.md) | 존재 | 보정 사전 검증 |
| [20261106_db_restore_and_correction_final_preflight.md](20261106_db_restore_and_correction_final_preflight.md) | 존재 | 복원·최종 보정 전 preflight |
| [20261106_more_simple_limit_tier_root_cause_and_fix.md](20261106_more_simple_limit_tier_root_cause_and_fix.md) | 존재 | 22/099 오답의 상세 데이터/코드 원인과 수정 |

## 7. 진행 중 작업 — 보정 실행기 준비

### 7.1 시작 전 원인·범위 기록 (코드 수정 전)

- **확인한 문제:** 기존 `limit_struct_backfill.py`는 dry-run만 가능하다. 변경 전/후 JSON과 target preimage hash, expected link natural key는 보고하지만 durable preimage 파일, transaction writer, retry/rollback 실행 경로가 아직 없다.
- **변경 필요성:** 실제 PG 보정은 별도 승인 후에만 가능하도록 준비하되, 이 단계에서는 승인되지 않은 운영 UPDATE/INSERT가 실행되지 않게 한다. 테스트는 fake connection으로 트랜잭션 성공/실패·preimage compare·link 중복을 검증한다.
- **목표 파일:** `src/card_benefit/payment_card/db_pipeline/limit_struct_backfill.py`, `src/card_benefit/payment_card/tests/test_limit_struct_backfill.py`, 본 이력 문서 및 필요 시 별도 실행/rollback 가이드 문서.
- **예상 데이터 영향:** 코드 실행만. PostgreSQL 3행·8 link 및 Neo4j 0 쓰기. actual apply 명령은 호출하지 않는다.
- **시작 시점 Git:** HEAD `1fcd3e636aa66a284117b6bcf200616ca5133c0a`, clean, `main` == `origin/main`.
- **다음 사전 조사:** current writer용 schema/PK/unique/FK/sequence SQL 확인 및 기존 dry-run tests 실행. production URL/credential은 출력하지 않는다.

### 7.2 실행 종료 후 추가할 항목

다음 표는 실제 작업 뒤 채운다. 완료·실패·미수행 상태를 빈칸으로 남겨 통과로 오해하게 하지 않는다.

| 완료 시각 | 변경 파일/함수 | 테스트 명령·결과 | PG/Neo4j 변경 | Git | 남은 항목 |
|---|---|---|---|---|---|
| 2026-11-06 (KST, 실행 시각은 미기록) | `limit_struct_backfill.py`, `test_limit_struct_backfill.py`, 본 문서 | 아래 7.2 참조 | PostgreSQL/Neo4j 0 writes | HEAD 유지, commit/push 안 함 | 실제 DB 복원·적용 미수행 |

### 7.2.1 이번 실행 준비 변경 내용

**수정 전 원인/범위 기록:** §7.1에 기록했듯, 기존 도구는 reviewed fixture와 현재 SELECT 결과를 결합하는 dry-run만 제공했다. durable preimage 생성, 허용 대상 제한, 단일 트랜잭션 UPDATE/INSERT, post-write 확인, 롤백 경로가 없었다. 실제 쓰기 기능은 기본 경로에 넣지 않고 별도 명시적 플래그·확인 문자열·DB 식별자 입력을 요구하게 한다. 이번 실행에서 실제 PostgreSQL 접속, UPDATE/INSERT, restore는 하지 않았다.

| 항목 | 구현 결과 |
|---|---|
| 대상 | 오직 `(22, '20261105_000099')`, `(23, '20261105_000100')`, `(20, '20261105_000092')` 3개 PK. 대상 집합·행 수·중복을 검사하고 다르면 중단 |
| 기본 동작 | 옵션 없음 또는 `--dry-run`은 기존 읽기 전용 SELECT preview. 명시적 `--apply`와 `--rollback` 이외의 확인 플래그는 CLI가 거부 |
| 대상 검증 | BENEFIT 타입, fixture 혜택명, `rule_list` SHA-256, `item_data` object 여부, 기존 JSON 충돌, evidence 자연키 중복 확인. `relation_key IS NULL`인 정확한 RULE link만 기존 링크로 인정 |
| 근거 검증 | 제안된 최대 8개 evidence ID가 `card_source_evidence`에 존재하고, extraction `card_extr_stg_id`, `start_pos`, `end_pos`, `quote_txt`가 reviewed fixture와 일치해야 진행 |
| preimage | 변경 전 3행 `item_data`, unchanged-field hash, 제안 JSON, 예상 링크, evidence 원문 메타데이터를 durable JSON으로 기록. 절대 경로·부모 폴더 존재·신규 파일 조건, exclusive create, flush/fsync 적용. 기존 파일 덮어쓰기 금지 |
| UPDATE | 정확한 PK와 기존 JSON을 비교하는 compare-and-swap. `item_data`만 수정하고 `rule_list`, `item_limit_txt`, 검색 텍스트 및 embedding은 건드리지 않음 |
| link INSERT | 기존 `card_source_evidence`에서 doc/page/chunk를 가져오는 패턴과 unique constraint `ON CONFLICT DO NOTHING RETURNING` 사용. 기존 링크 PK와 새로 삽입한 PK를 구분해 저장 |
| transaction | 전체 대상 `FOR UPDATE`; session read-write 상태와 `current_database()`/`inet_server_addr()` 확인; 한 transaction에서 UPDATE/INSERT 후 3행 JSON과 모든 자연키 검증. 예외는 transaction context에서 rollback |
| 재시도 | 이미 동일하게 반영된 JSON/link는 추가 link 중복 없이 통과. 충돌 JSON key가 있으면 중단. 정상 재시도 예상 변경/삽입 수는 0 |
| rollback | 별도 확인 문자열 및 committed manifest 필요. 현재 값이 기록된 after-image일 때만 before-image 복구. 이 run에서 삽입한 link ID와 자연키가 함께 일치할 때만 삭제하므로 기존 link는 보존 |
| commit 모호성 | DB commit 뒤 manifest의 `COMMITTED` 변경 전에 프로세스가 종료되면 pending 상태가 남을 수 있다. 자동 재적용/복구 금지; read-only DB 대조 후 수동 판단 필요 |

주요 코드 위치: `compose_preview()` [limit_struct_backfill.py:82](../../payment_card/db_pipeline/limit_struct_backfill.py#L82), exclusive preimage [line 166](../../payment_card/db_pipeline/limit_struct_backfill.py#L166), transactional writer [line 193](../../payment_card/db_pipeline/limit_struct_backfill.py#L193), rollback [line 369](../../payment_card/db_pipeline/limit_struct_backfill.py#L369), CLI guard/default dry-run [line 534](../../payment_card/db_pipeline/limit_struct_backfill.py#L534). 테스트 fake connection은 쿼리·트랜잭션 경로만 검증하며 실제 PostgreSQL 제약, DDL, 권한 또는 복구 성공 증거는 아니다.

데이터 전후 제안은 기존 dry-run fixture 기반이다. 22/099는 30만~80만원 미만 10,000원 및 80만원 이상 15,000원의 명확한 `limit_tiers`를 보존한다. 23/100은 원문에 없는 실적 상한을 만들지 않고 `limit_tiers`를 제안하지 않는다. 가장 높은 충족 하한 선택은 런타임 정책이지 원문 데이터가 아니다. 20/092의 누적 100,000원 + 추가 100,000원 구조를 배타적 구간으로 변환하지 않는다. 세 행과 8 link는 모두 **예정**이고 실제 반영 0건이다.

이번에 실제 `derive_fixture_patches()`를 실행해 검토한 fixture 제안의 연결 식별자는 다음과 같다(수정 전 행은 기존 사전검증 문서상 `item_data={}`).

| 카드/행 PK | 근거 노드 연결 | JSON 구조 제안 및 원문 대조 상태 |
|---|---|---|
| 22/`20261105_000099` | `r1/c1 → 20261105_002685`, `r2/c2 → 20261105_002686`, `r3/c3 → 20261105_002687` | `limits` l1=10,000, l2=15,000; `rule_limits` r1→l1, r2→l2, r3→l1+l2; `limit_tiers` r1 300,000≤실적<800,000→10,000, r2 실적≥800,000→15,000. 수치/구간 관계는 기존 공식 PDF·추출 분석 문서와 reviewed fixture에서 재사용. 이번에는 PDF를 새로 추출하지 않음 |
| 23/`20261105_000100` | `r1/c1 → 20261105_002744`, `r2/c2 → 20261105_002745`, `r3/c3 → 20261105_002746` | `limits` l1/l2/l3=10,000/20,000/50,000, 각 RULE과 연결. 한도 금액 원문 evidence `20261105_002739`, `002740`, `002741`; 원문 하한은 300,000/600,000/1,200,000, 상한 미기재. 따라서 fixture에 가상 상한이나 `limit_tiers`가 없음 |
| 20/`20261105_000092` | `bonus_base_discount/bonus_spend_24m → 20261105_002453`, `bonus_additional_cap_discount/bonus_spend_36m → 20261105_002454` | `limits` bonus_base_cap=100,000 및 bonus_additional_cap=100,000, `period_cd=UNKNOWN`; 누적형/추가 구조 보존, `limit_tiers` 없음 |

이 대조는 현재 저장된 reviewed fixture와 기존 PDF/원천 데이터 검수 결과의 재사용이다. 이번 실행에서는 production DB의 실시간 행, Neo4j `source_json`, PDF 원본 파일을 새로 조회하지 않았다. 실제 live dry-run의 최신 link 중복 수와 현재 JSON before-image는 읽기 전용 사전 확인 후에만 확정할 수 있다.

### 7.2.2 실행 테스트 및 결과

| 명령 | 결과 | 환경/범위 |
|---|---|---|
| `..\\..\\.venv\\Scripts\\python.exe -m py_compile payment_card/db_pipeline/limit_struct_backfill.py payment_card/tests/test_limit_struct_backfill.py` (cwd `src/card_benefit`) | 성공 | 구문 컴파일 |
| `..\\..\\.venv\\Scripts\\python.exe -m pytest -q -p no:cacheprovider --basetemp=..\\..\\tmp\\pytest_limit_backfill --tb=short payment_card/tests/test_limit_struct_backfill.py` | 12 passed | fake DB; 실제 PostgreSQL 연결 없음 |
| `..\\..\\.venv\\Scripts\\python.exe -m pytest -q -p no:cacheprovider --basetemp=..\\..\\tmp\\pytest_limit_related --tb=short payment_card/tests/test_limit_struct.py payment_card/tests/test_p2_limit_tiers.py` | 42 passed | 관련 한도 P1/P2 회귀, fixture/stub |

초기 시도에서 pytest 작업 디렉터리가 root여서 package import가 실패했고, 기본 OS temp 위치 접근도 거부되었다. CWD를 `src/card_benefit`로 맞추고 repo-local `--basetemp`를 지정해 해결했다. 전체 회귀 682 passed/2 failed/20 skipped는 이전 문서의 결과이며 이번 단계에서 재실행하지 않았다.

### 7.2.3 백업·복원 및 재적재 위험 업데이트

- PostgreSQL 백업: `src/data/backup/pre_calc_cleanup_20261106_140723/`의 JSON+DDL 백업 및 17.11 기준 20 tables/4,864 rows, VERIFY OK는 기존 검증 사실이다. 격리 DB restore rehearsal은 성공한 적 없고 이번에도 시도하지 않았다. 현재 writer의 preimage는 특정 3행과 해당 실행 신규 link의 논리적 복구 수단이지 전체 DB backup/restore 대체물이 아니다.
- 실제 운영 보정 승인 전 선행 조건: 격리 PostgreSQL 인스턴스/DB, 현재 schema와 FK/unique constraint 확인, 백업 복원 후 PK/FK·item_data·evidence link 건수 검증, 승인된 별도 신규 preimage 경로, 예상 DB/server 주소 read-only 확인, 동일 실행기 격리 리허설.
- AuraDB Free: 기존 공식 문서 조사에서는 on-demand snapshot/export 경로에 대한 안내와 Free 지원 표기 사이 불일치가 있었다. 특정 Aura Console 접근 권한이 없어 인스턴스 메뉴·snapshot 생성·export·restore 가능 여부를 확인하지 못했다. 실제 snapshot/export 성공 또는 별도 인스턴스 복원 검증은 완료되지 않았다.
- Neo4j 쓰기/재적재: 0건. 기존 수치 1,635 nodes/2,702 relationships 및 예상 1,643/2,718은 기존 문서에 기록된 기준/추정이다. 전체 MERGE의 잔존 관계·중복·임베딩/인덱스 보존을 실제 검증하지 않았으며, DB backup/export와 restore rehearsal 없이는 재적재를 시작하지 않는다. PostgreSQL 부분 보정 후 Neo4j도 정확한 key로 제한한 부분 반영이 가능한지 loader의 MERGE/관계 정리 의미를 별도 검토해야 한다.

### 7.2.4 작업 종료 시점

- 소스 변경: 실행기와 해당 fake DB tests만 추가 수정. 별도 이슈 분석 문서는 생성하지 않고 이 work log에 구현·테스트 이력을 추가.
- 테스트: backfill writer/rollback fake tests 12 passed, 관련 limit-structure/P2 tests 42 passed. `--help`는 CLI 플래그 목록을 출력하고 종료했으며 DB에 접속하지 않았다.
- PostgreSQL UPDATE/INSERT/DELETE/DDL: 0건. Neo4j CREATE/MERGE/DELETE/reload: 0건. restore, deploy, paid LLM: 0건.
- Git HEAD는 시작점 `1fcd3e636aa66a284117b6bcf200616ca5133c0a` 그대로이며 commit/push는 수행하지 않았다. 변경 파일은 이 실행기, 해당 테스트, 본 문서다.
- 미완료: 격리 PostgreSQL restore/실행기 리허설, Aura snapshot/export 및 별도 restore 확인, 운영 DB 보정, Neo4j의 부분 반영 대 전체 reload 선택, 실제 Streamlit 재질문, 50문항 QA의 19 답변 오류 및 4 실행 오류 별도 처리.

## 8. PostgreSQL 기존 데이터 보정 — 읽기 전용 최종 사전 점검

### 8.1 시작 시점 Git 및 안전 조건

- 작업 시작 HEAD/branch: `840b28d2b88d2b129a721804854a9101c40dd0e5` / `main`, commit 제목 `GraphRAG 데이터 보정 실행기 및 작업 이력 문서화`.
- `git status --short`는 출력이 없어 시작 시 working tree clean이었다. 앞선 작업의 실행기·테스트·work log가 이 HEAD에 포함되어 있다. 이번 변경을 commit/push하지 않는다.
- 전체 PostgreSQL 백업 파일이 있고 기존 기록상 PostgreSQL 17.11, 20 tables/4,864 rows, backup compare `VERIFY OK`다. **격리 DB restore rehearsal 성공 기록은 없다.** 백업 파일 검증과 데이터 복원 검증을 같은 것으로 취급하지 않는다.
- 사용자가 명시한 제한에 따라, 이 restore gap은 실제 운영 쓰기 전에 멈춰야 하는 사유다. 아래는 읽기 전용 사전 점검과 예상 계획일 뿐이며 적용 승인을 요청/실행하는 단계까지 진행하지 않는다.

### 8.2 실제 읽기 전용 접속 식별 정보

읽기 전용 psycopg 연결에서 `options='-c default_transaction_read_only=on'`을 설정하고 `SET default_transaction_read_only = on` 후 식별 SELECT와 타깃/evidence SELECT를 수행했다. 접속 문자열이나 인증 정보는 기록하지 않는다.

접속 식별/상세 SELECT를 한 줄 `python -c`로 실행하려던 초반 2회는 PowerShell 인용부호가 SQL/Python 문자열을 잘라 Python SyntaxError로 종료되어 DB 연결 전에 실패했다. 이어 임시 읽기 전용 helper `tmp/codex_readonly_backfill_preflight.py`로 동일 조회를 성공적으로 마쳤고, 조회 후 이 helper 파일은 삭제했다. 두 번의 구문 오류에서 DB 쿼리나 변경은 실행되지 않았다.

| 항목 | 실제 결과 |
|---|---|
| PostgreSQL | `PostgreSQL 17.11 on aarch64-unknown-linux-gnu`, 64-bit |
| `current_database()` | `postgres` |
| `inet_server_addr()` | `2a05:d018:cb1:bb01:8ebd:ef70:d08:18a0/128` |
| `inet_server_port()` | `5432` |
| session | `default_transaction_read_only=on`; 이 확인에서는 SELECT만 실행 |

서버 주소는 향후 writer의 `--expected-server-address` guard에 정확히 입력할 식별값이다. 실제 쓰기 경로는 별도 승인 전 실행하지 않는다.

### 8.3 현재 행 및 제안 변경 요약

실행 명령은 `src/card_benefit` 작업 디렉터리에서 실행한 `..\\..\\.venv\\Scripts\\python.exe -m payment_card.db_pipeline.limit_struct_backfill`이다. 옵션이 없는 기본 dry-run이 `READ_ONLY_DRY_RUN`, `database_writes=0`을 반환했다. 추가로 아래 타깃/evidence SELECT를 읽기 전용 transaction으로 수행했다. 세 대상 행 모두 실제 현재 `item_data={}`이고, BENEFIT 타입과 fixture 이름/`rule_list` 해시가 현재 실행기의 검증을 통과했다. 기존 RULE/COND link는 0건, 제안 8개 link는 모두 `already_exists=false`, 즉 현재 조회상 추가 대상 8건이다.

| PK (card_id, card_product_item_id) | 실제 현재 item name / `item_data` | 변경 예정 | 변경 수 |
|---|---|---|---|
| `(22, '20261105_000099')` | `월납 요금 청구할인` / `{}` | `limits` 2개, `rule_limits` r1/r2/r3, 추출 근거로 구조화한 `limit_tiers` 2구간 | UPDATE 1 |
| `(23, '20261105_000100')` | `주요 간편결제 모아포인트 추가적립` / `{}` | 특별·추가 적립 공유 `limits` 3개 및 `rule_limits` 3개. 원본 조건 상한 null 유지. `PROGRAM_DERIVED` 구간/상한을 원본 `item_data`에 추가하지 않음 | UPDATE 1 |
| `(20, '20261105_000092')` | `골프/프리미엄 아울렛 50% 청구 할인` / `{}` | 누적 base 100,000 및 추가 100,000 limits/rule mapping. `limit_tiers` 생성 안 함 | UPDATE 1 |

전 행에서 기존 `rule_list`와 `value_num`, `cond_max_amt_excl`, `item_limit_txt`, 검색 텍스트·embedding은 유지한다. 특히 22/099의 지급 `value_num=null`을 보정하지 않는다. 23/100 행은 추가 적립 혜택 대상이며 기본 적립 제한 없음은 공식 상품정책이다. 이 JSON patch에는 특별/추가 적립 공유 한도만 담고 기본 적립에 임의 한도/규칙을 만들지 않는다.

실제 현재 `rule_list`의 조건/지급 값 요약은 다음과 같다. dry-run fixture의 `rule_list` hash와 실시간 값이 맞아 기존 규칙을 수정하지 않는 전제가 확인되었다.

| PK | 기존 rule | 실제 `cond_min_amt` / `cond_max_amt_excl` | 실제 `value_num` / unit | 보정 시 처리 |
|---|---|---|---|---|
| 22/099 | r1 / c1 | 300,000 / 800,000 | null / null | 유지 |
| 22/099 | r2 / c2 | 800,000 / null | null / null | 유지 |
| 22/099 | r3 / c3 (`TXN_AMT`) | null / null | null / null | 유지 |
| 23/100 | r1/r2/r3 / c1/c2/c3 | 300,000 / null; 600,000 / null; 1,200,000 / null | 3 / `PERCENT` 각각 | 유지. 공식 원문에 없는 상한 추가 금지 |
| 20/092 | `bonus_base_discount` / `bonus_spend_24m` | 24,000,000 / null (`ROLLING_MONTHS`) | 50 / `PERCENT` | 유지 |
| 20/092 | `bonus_additional_cap_discount` / `bonus_spend_36m` | 36,000,000 / null (`ROLLING_MONTHS`) | 50 / `PERCENT` | 유지 |

### 8.4 정확한 제안 JSON

아래는 live dry-run의 `item_data_after_preview`에서 추린 JSON이다. 변경 전 JSON은 각 타깃에서 실제로 조회한 `{}`다. 이는 아직 DB에 저장된 변경 후 값이 아니다.

#### 22/099 — 제안 `item_data`

```json
{
  "schema_ver": "BENEFIT_V1",
  "limits": [
    {"limit_key":"l1","limit_num":10000,"cap_unit_cd":"KRW","period_cd":"MONTH","limit_raw_txt":"10,000원","shared_scope_txt":"횟수 제한 없이 월 할인 한도 내에서 합산 할인","applies_to_benefit_nms":["월납 요금 청구할인"],"evidence_ids":["20261105_002681"]},
    {"limit_key":"l2","limit_num":15000,"cap_unit_cd":"KRW","period_cd":"MONTH","limit_raw_txt":"15,000원","shared_scope_txt":"횟수 제한 없이 월 할인 한도 내에서 합산 할인","applies_to_benefit_nms":["월납 요금 청구할인"],"evidence_ids":["20261105_002682"]}
  ],
  "rule_limits": {"r1":["l1"],"r2":["l2"],"r3":["l1","l2"]},
  "limit_tiers": {
    "schema_ver":"LIMIT_TIERS_V1","source":"EXTRACTION","basis_cd":"PREV_MONTH_SPEND",
    "tiers":[
      {"tier_key":"r1","rule_key":"r1","label":"30만원 이상 80만원 미만","min_amt":300000,"max_amt_excl":800000,"evidence_ids":["20261105_002685"]},
      {"tier_key":"r2","rule_key":"r2","label":"80만원 이상","min_amt":800000,"max_amt_excl":null,"evidence_ids":["20261105_002686"]}
    ],
    "own":{"column":"월 한도","column_source":"PERIOD_CD","merged_cell":false,
      "caps":{"r1":{"raw":"10,000원","amount":10000,"limit_key":"l1"},"r2":{"raw":"15,000원","amount":15000,"limit_key":"l2"}}},
    "shared":[]
  }
}
```

#### 23/100 — 제안 `item_data`

```json
{
  "schema_ver":"BENEFIT_V1",
  "limits":[
    {"limit_key":"l1","limit_num":10000,"cap_unit_cd":"KRW","period_cd":"MONTH","limit_raw_txt":"1만원","shared_scope_txt":"특별/추가 적립","applies_to_benefit_nms":[],"evidence_ids":["20261105_002739"]},
    {"limit_key":"l2","limit_num":20000,"cap_unit_cd":"KRW","period_cd":"MONTH","limit_raw_txt":"2만원","shared_scope_txt":"특별/추가 적립","applies_to_benefit_nms":[],"evidence_ids":["20261105_002740"]},
    {"limit_key":"l3","limit_num":50000,"cap_unit_cd":"KRW","period_cd":"MONTH","limit_raw_txt":"5만원","shared_scope_txt":"특별/추가 적립","applies_to_benefit_nms":[],"evidence_ids":["20261105_002741"]}
  ],
  "rule_limits":{"r1":["l1"],"r2":["l2"],"r3":["l3"]}
}
```

#### 20/092 — 제안 `item_data`

```json
{
  "schema_ver":"BENEFIT_V1",
  "limits":[
    {"limit_key":"bonus_base_cap","limit_num":100000,"cap_unit_cd":"KRW","period_cd":"UNKNOWN","limit_raw_txt":"보너스 할인 한도 10만원 제공","shared_scope_txt":null,"applies_to_benefit_nms":["골프/프리미엄 아울렛 50% 청구 할인"],"evidence_ids":["20261105_002447"]},
    {"limit_key":"bonus_additional_cap","limit_num":100000,"cap_unit_cd":"KRW","period_cd":"UNKNOWN","limit_raw_txt":"보너스 할인 한도 10만원 추가 제공","shared_scope_txt":null,"applies_to_benefit_nms":["골프/프리미엄 아울렛 50% 청구 할인"],"evidence_ids":["20261105_002448"]}
  ],
  "rule_limits":{"bonus_base_discount":["bonus_base_cap"],"bonus_additional_cap_discount":["bonus_additional_cap"]}
}
```

### 8.5 근거 연결 예정 8건과 원본 근거 검증

현재 `card_source_evidence`를 읽기 전용으로 조회한 결과, 8개 evidence ID가 모두 존재했다. 각 source row의 문서·페이지·청크·추출 staging ID·원문 위치/인용은 다음과 같다. 이들은 source evidence 실재 확인이며, 아래 RULE/COND link는 아직 INSERT되지 않았다.

| 카드 / rule / condition key | evidence ID | 문서 ID / page / chunk | extraction staging ID | start–end | 실제 quote |
|---|---|---|---|---|---|
| 22/099 r1 / c1 | `20261105_002685` | `20261105_000042` / 1 / `20261105_000173` | `20261105_000619` | 3727–3741 | `30만원 이상\n80만원 미만` |
| 22/099 r2 / c2 | `20261105_002686` | `20261105_000042` / 1 / `20261105_000173` | `20261105_000619` | 3743–3757 | `80만원 이상\n15,000원` |
| 22/099 r3 / c3 | `20261105_002687` | `20261105_000042` / 1 / `20261105_000173` | `20261105_000619` | 3182–3223 | `월납 요금 승인 금액이 할인 한도보다 적을 경우 승인 금액만큼 할인 적용` |
| 23/100 r1 / c1 | `20261105_002744` | `20261105_000043` / 3 / `20261105_000176` | `20261105_000636` | 362–383 | `전월 국내가맹점 이용실적 \n30만원 이상` |
| 23/100 r2 / c2 | `20261105_002745` | `20261105_000043` / 3 / `20261105_000176` | `20261105_000636` | 419–440 | `전월 국내가맹점 이용실적 \n60만원 이상` |
| 23/100 r3 / c3 | `20261105_002746` | `20261105_000043` / 3 / `20261105_000176` | `20261105_000636` | 476–498 | `전월 국내가맹점 이용실적 \n120만원 이상` |
| 20/092 bonus_base_discount / bonus_spend_24m | `20261105_002453` | `20261105_000040` / 3 / `20261105_000159` | `20261105_000571` | 684–710 | `서비스 실적 기간 내 2,400만원 이상 이용 시` |
| 20/092 bonus_additional_cap_discount / bonus_spend_36m | `20261105_002454` | `20261105_000040` / 3 / `20261105_000159` | `20261105_000571` | 733–747 | `3,600만원 이상 이용 시` |

실행기가 만들 link의 자연키는 각 행의 `(card_id, card_product_item_id, ev_subject_cd='RULE', rule_key, ev_item_cd='COND', ev_item_key, evidence_id)` 조합이다. 현재 대상에 기존 RULE/COND link가 없으므로 preview상 중복은 0, 신규 제안은 8이다. commit 뒤의 실제 `evidence_link_id`는 DB가 발급하며 아직 알 수 없다.

### 8.6 실행기·SQL·preimage·rollback 확인

- 실제 실행한 DB 쓰기 SQL: **없음**. 실행한 프로그램 명령은 기본 read-only dry-run뿐이다. 읽기 전용으로 실행한 식별 SQL은 `SELECT version(), current_database(), inet_server_addr()::text, inet_server_port()`이고, 현재 PK 행·RULE/COND 관계·`card_source_evidence` 8건을 SELECT했다.
- 읽기 전용 쿼리(실제 실행, 접속에는 `default_transaction_read_only=on` 설정):

```sql
SELECT version(), current_database(), inet_server_addr()::text, inet_server_port();

SELECT card_id, card_product_item_id, item_type_cd, item_nm, item_data, rule_list, item_limit_txt
FROM db_pipeline.card_product_item
WHERE (card_id, card_product_item_id) IN
  ((22, '20261105_000099'), (23, '20261105_000100'), (20, '20261105_000092'));

SELECT card_id, card_product_item_id, rule_key, ev_subject_cd, relation_key,
       ev_item_cd, ev_item_key, evidence_id, evidence_link_id
FROM db_pipeline.card_evidence_link
WHERE (card_id, card_product_item_id) IN
  ((22, '20261105_000099'), (23, '20261105_000100'), (20, '20261105_000092'))
  AND ev_subject_cd = 'RULE' AND ev_item_cd = 'COND';

SELECT evidence_id, card_doc_id, page_no, card_doc_chunk_id, card_extr_stg_id,
       start_pos, end_pos, quote_txt
FROM db_pipeline.card_source_evidence
WHERE evidence_id = ANY(ARRAY[
  '20261105_002685','20261105_002686','20261105_002687',
  '20261105_002744','20261105_002745','20261105_002746',
  '20261105_002453','20261105_002454'
]);
```
- writer 구현상 적용 명령(아직 미실행, `src/card_benefit`에서):

```powershell
..\..\.venv\Scripts\python.exe -m payment_card.db_pipeline.limit_struct_backfill `
  --apply `
  --confirm-write APPLY_GRAPH_LIMIT_BACKFILL_22_23_20 `
  --expected-database postgres `
  --expected-server-address '2a05:d018:cb1:bb01:8ebd:ef70:d08:18a0/128' `
  --preimage-out 'C:\myproject\workspace\mle-02-p2-team3\src\data\backup\pre_calc_cleanup_20261106_140723\graphrag_limit_backfill_preimage_20261106_postgres.json'
```

- 제안된 preimage 경로의 부모 백업 디렉터리는 존재하고 `.gitignore`의 `/src/data/backup/pre_calc_cleanup_*/`에 의해 ignore되는 것을 확인했다. 해당 preimage 파일은 **아직 생성하지 않았다**. 실행기는 이미 존재하는 preimage를 덮어쓰지 않으므로 실제 승인 후 고유하고 없는 파일명을 다시 확인해야 한다.
- 적용 시 실행기는 대상 3행을 `FOR UPDATE`로 잠그고 DB/server/read-write를 검증한다. `item_data`는 before JSON 조건까지 넣은 compare-and-swap UPDATE이고, evidence는 기존 source evidence에서 문서/page/chunk를 가져오는 `INSERT ... SELECT ... ON CONFLICT ... DO NOTHING RETURNING`이다. 3행 JSON과 8개 자연키 확인이 모두 끝나야 transaction commit한다. 실패 시 context rollback.
- rollback 적용 경로는 적용 run의 committed preimage, 별도 `ROLLBACK_GRAPH_LIMIT_BACKFILL_22_23_20` 확인 문자열, 동일 DB/server를 요구한다. 현재 `item_data`가 기록한 after-image인 경우에만 before-image로 복구하고 이 run에서 INSERT된 `evidence_link_id`와 자연키가 모두 맞는 link만 삭제한다. 기존 link는 지우지 않는다. COMMIT 직후 manifest 마킹이 끊기면 DB를 read-only로 먼저 대조해야 하고, 자동 재실행하지 않는다.
- fake PostgreSQL transaction 테스트는 12 passed, 한도/P2 관련 테스트는 42 passed. 실제 DB transaction/rollback은 시험하지 않았다.

### 8.7 적용 중단 결정 및 사용자 판단 필요

운영 백업 파일은 존재하지만 격리 환경에서 복원된 적이 없다. target preimage는 대상 세 행과 이 실행이 새로 넣는 link를 되돌리는 데 유용하지만, DB 전체 상태·FK 관계 또는 장애 복구를 대신하지 않는다. 요청에 명시된 조건에 따라 현재는 **운영 UPDATE 3행 / INSERT 8건을 실행하지 않고 중단**했다. 따라서 PostgreSQL COMMIT/ROLLBACK은 모두 미실행이며 변경 행·link 수는 0이다.

사용자가 판단할 선택지는 다음과 같다.

1. 먼저 격리 PostgreSQL 17 환경을 마련해 백업 복원 rehearsal을 완료하고, PK/FK, 20개 테이블·4,864행, JSON 및 evidence link를 검증한 뒤 운영 적용 계획을 다시 승인한다. 권장 경로.
2. 전체 restore rehearsal 없이 row-level preimage/transaction만으로 진행할 예외를 명시적으로 승인한다. 이 선택은 전체 백업 복구 가능성을 검증하지 않은 상태에서 운영 데이터를 변경하는 위험을 수용한다. 현재 지시는 별도 판단 없이는 이 선택을 허용한 것으로 간주하지 않는다.

### 8.8 Neo4j 후속 범위 (미실행)

- 이번에 바꿀 Neo4j node/relationship 수: 0. PostgreSQL만 승인 후 수정하더라도 Neo4j `source_json.item_data`와 graph RULE/COND relationships는 기존 상태라 양 DB가 일시적으로 불일치한다.
- 후보 변경: BENEFIT key `card_product_item` + `(card_id, item_id)` 3개 노드의 `source_json.item_data`와 8개 RULE/COND evidence relationship. 추가 evidence 노드는 PostgreSQL에 이미 존재하며 현재 Neo4j에 존재하는지/추가 생성이 필요한지는 이번 단계에서 확인하지 않았다.
- 기존 인스턴스 수 1,635 nodes/2,702 relationships는 이전 read-only 확인값이지 이번 실행 시점에 재검증한 수치가 아니다. 1,643/2,718은 옛 예상치일 뿐 실제값으로 사용하지 않는다.
- Neo4j 임베딩·인덱스 보존, 전체 MERGE의 중복/잔존 관계 정리, 부분 동기화가 가능한지, 실패 시 복원은 아직 검증되지 않았다. AuraDB Free snapshot/export 및 별도 인스턴스 restore가 미확인이고 restore rehearsal도 없으므로 Neo4j 적재는 별도 백업·복원 준비와 승인 후에만 검토한다.
- 후속 검증은 PostgreSQL에서 3개 JSON과 8개 관계를 SELECT, Neo4j에서 동일한 node key의 source JSON 및 owner–evidence relationship을 read-only 조회해 양방향 비교한다. Neo4j 전후 노드/관계 수와 embedding/index metadata는 재적재 방식이 확정되면 별도 검증 SQL/Cypher 문서에 정한다.

### 8.9 이번 사전 점검 종료 상태

| 항목 | 상태 |
|---|---|
| 현재 DB 식별/세 행/근거 8개 SELECT | 완료, read-only |
| 제안 JSON·natural key·중복 상태 확인 | 완료, dry-run; 신규 link 8, 기존 0 |
| fresh durable preimage 생성 | 미실행 (쓰기 승인 전 생성 금지) |
| PostgreSQL UPDATE/INSERT/COMMIT/rollback | 미실행, 0 행/0 link 변경 |
| PostgreSQL backup restore rehearsal | 미완료, 적용 중단 조건 |
| Neo4j write/reload | 미실행, 별도 승인 대상 |
| Git | 이번 작업 시작 HEAD `840b28d2b88d2b129a721804854a9101c40dd0e5`; 이번 기록 외 변경사항은 후속 승인 이후만 수행. preimage/backup은 Git에 추가하지 않음 |


## 9. 격리 PostgreSQL 복원 → 보정 적용 → 원복 리허설 (2026-11-06)

### 9.1 범위와 안전 경계

- 목적: JSON+DDL 백업을 격리 PostgreSQL 17에 복원하고, 기존 limit_struct_backfill 실행기의 기본 dry-run·적용·멱등 재실행·실패 rollback·preimage 원복을 실제 PostgreSQL에서 검증했다.
- 시작 시 Git HEAD 840b28d2b88d2b129a721804854a9101c40dd0e5. 추적 파일은 깨끗했다. 작업 중 이 문서만 수정했고 임시 검증 도구는 tmp에 생성했다. 운영 소스 수정, commit/push는 없었다.
- 운영 PostgreSQL은 읽기 전용 catalog 확인 외에 접속/쓰기하지 않았다. Neo4j 미접속·미변경, Streamlit 미배포.
- 테스트 DB는 독립 로컬 Docker 인스턴스이며 운영 DB 접속정보를 재사용하지 않았다.

### 9.2 격리 환경

- Windows에서 Docker Desktop/PostgreSQL 서비스를 찾지 못해 기존 WSL Ubuntu 24.04.5의 Docker Engine 29.9.2를 사용했다. 새 외부 DB 인스턴스는 만들지 않았다.
- 컨테이너: graphrag-pg17-restore-rehearsal; DB graphrag_restore; 역할 restore_admin; host port 127.0.0.1:55432; 별도 volume graphrag-pg17-restore-data-20261106.
- 이미지 pgvector/pgvector:0.8.2-pg17-bookworm, digest sha256:feb68f4f15446397d8cac7f4fe48fe4586de83160d1fc48b46283312d1a33966. 실제 PostgreSQL 17.10 (Debian 17.10-1)이며 운영 17.11과 patch 버전 차이가 남는다.
- 컨테이너가 WSL idle 종료 때 멈춰 리허설 중 keepalive를 사용했다. 테스트 포트는 localhost에 바인딩했다. 테스트 DB만 trust 인증이며 Docker bridge 안의 다른 컨테이너에서 접근 가능할 수 있어 장기 유지 시 인증 전환이 필요하다.
- 구축 중 첫 Docker quoting 시도는 생성 실패, 인자 전달을 고쳐 성공했다. ALTER ROLE의 parameterized password 변경은 PostgreSQL utility statement가 bind parameter를 지원하지 않아 실패해 별도 테스트 암호 설정을 생략했다. WSL idle 종료는 keepalive로 해결했다. 초기 harness의 tuple 결과를 dict로 읽던 테스트 오류도 tuple 인덱싱으로 고쳐 재실행했다. 운영 소스는 수정하지 않았다.
- 격리 접속 값: host=127.0.0.1 port=55432 dbname=graphrag_restore user=restore_admin. 운영 연결정보가 아니다.

### 9.3 JSON+DDL 복원 결과와 제한

- 백업 경로 src/data/backup/pre_calc_cleanup_20261106_140723/의 schema_ddl.sql, postgres_db_pipeline.json, catalog.json을 사용했다. JSON+DDL이므로 pg_restore는 사용하지 않았고 DDL 실행 후 JSON 행을 테이블별로 적재했다.
- 복원 결과는 20개 테이블, 4,864행이며 각 테이블 행 수와 백업 행 데이터 비교가 일치했다.

| 테이블 | 행 | 테이블 | 행 |
|---|---:|---|---:|
| app_log | 127 | app_log_event_archive | 97 |
| backup_card_bnft | 16 | card_ai_call | 122 |
| card_ai_run | 43 | card_common | 14 |
| card_common_bnft | 82 | card_common_bnft_apply | 1 |
| card_common_doc | 19 | card_doc | 30 |
| card_doc_chunk | 95 | card_doc_page | 86 |
| card_evidence_link | 250 | card_extr_stg | 686 |
| card_product | 10 | card_product_doc | 11 |
| card_product_item | 51 | card_source_evidence | 2,959 |
| common_cd | 132 | common_code_grp | 33 |

- 제약조건은 PK 20, UNIQUE 16, CHECK 41, 선언 FK 0. 백업 catalog에 FK가 없으므로 FK 0개를 확인했다. 논리 evidence 참조는 별도로 조인 검사했고 source evidence 누락 0건, document/page/chunk metadata 불일치 0건이었다.
- extensions schema에 vector, pgcrypto, uuid-ossp, pg_stat_statements를 구성했다. Supabase Vault는 DDL에서 참조되지 않아 복원하지 않았으므로 해당 extension 복원은 미검증이다.
- 백업 DDL은 card_product_item.item_ref를 다른 열 참조 DEFAULT로 표현해 PostgreSQL이 거부했다. 운영 catalog의 read-only 확인으로 실제 열이 stored generated column(attgenerated='s')임을 확인했다. 격리 리허설에서만 DDL을 GENERATED ALWAYS AS (...) STORED로 고쳤고, JSON 로더에서 item_ref를 제외해 PostgreSQL이 계산했다. 백업 파일 및 운영 DB는 변경하지 않았다.
- 세 대상 PK (22,20261105_000099), (23,20261105_000100), (20,20261105_000092)는 각 1행, 기존 item_data={} 및 RULE/COND link 0건으로 복원됐다.
- backup_db_pipeline.verify()는 FAIL을 반환했다. 행 지문과 행 비교 문제는 출력되지 않았고 catalog.columns, catalog.views, catalog.functions만 불일치였다. 상세 비교에서 columns 차이는 일부 ordinal position(물리 열 순서), views/functions 차이는 owner가 postgres 대 테스트 역할인 환경 차이 및 함수 정의 개행이었다. strict catalog 검증은 통과하지 못했으므로 전체 복원을 VERIFY OK로 기록하지 않는다. 행 데이터는 일치했으나 catalog 전체 metadata 동등성은 미완료다.
- 격리 복원 자체는 성공했지만 백업 DDL의 generated column 표현을 보정해야 했고, PostgreSQL 17.11 patch-level 검증은 남아 있다.

### 9.4 보정 실행기 통합 테스트

- 기존 모듈 src/card_benefit/payment_card/db_pipeline/limit_struct_backfill.py의 read_live_rows(), compose_preview(), apply_corrections(), rollback_corrections()를 사용했다. Fixture는 src/card_benefit/payment_card/tests/fixtures_limit_struct.json. 추적 코드 변경은 없다.
- 기본 dry-run: READ_ONLY_DRY_RUN, database_writes=0, 대상 3행, 예정 link 8, 기등록 0, 추가 예정 8.
- 실패 rollback: 테스트 DB에만 임시 BEFORE INSERT trigger를 두고 INSERT에서 injected isolated rehearsal failure를 일으켰다. 앞서 UPDATE된 대상 item_data와 link가 전부 rollback되어 item_data 변경 0건, link 증가 0건이었다. 임시 trigger/function은 제거했다.
- 실제 apply: UPDATE 3행, INSERT 8건. 실행기 내부에서 preimage 작성, 대상/규칙 비교, evidence 원본 quote·start/end/staging 검증, 적용 후 JSON 및 RULE/COND natural key 검증이 통과했다.
- 삽입 evidence ID: 20261105_002685, 20261105_002686, 20261105_002687, 20261105_002744, 20261105_002745, 20261105_002746, 20261105_002453, 20261105_002454.
- 멱등 재실행은 UPDATE 0행, INSERT 0건, 이미 존재 link 8건이었다.
- apply가 만든 preimage로 rollback하여 item_data 3행은 원래 {}로, link 8건은 삭제하여 초기 상태로 돌아왔다. 원복 뒤 다시 dry-run한 결과도 세 행/여덟 link 제안이었다.
- PostgreSQL sequence는 트랜잭션 rollback되지 않아 seq_card_evidence_link가 721에서 730으로 증가했다. 행과 link만 원복됐고 sequence는 최초 값으로 돌아가지 않았다.
- 임시 harness는 tmp/run_pg17_restore_rehearsal.py, catalog 비교 도구는 tmp/compact_restore_diff.py 및 tmp/diff_test_restore_catalog.py였다. 이들은 임시 산출물이며 Git 추적 대상이 아니다.

### 9.5 실제 실행 SQL 형태 (격리 DB 전용)

UPDATE db_pipeline.card_product_item
SET item_data = %s::jsonb
WHERE card_id = %s AND card_product_item_id = %s AND item_data = %s::jsonb
RETURNING card_id, card_product_item_id;

INSERT INTO db_pipeline.card_evidence_link
  (card_doc_id, page_no, card_doc_chunk_id, evidence_id, card_id,
   ev_subject_cd, card_product_item_id, rule_key, ev_item_cd, ev_item_key)
SELECT e.card_doc_id, e.page_no, e.card_doc_chunk_id, e.evidence_id, %s,
       'RULE', %s, %s, 'COND', %s
FROM db_pipeline.card_source_evidence e WHERE e.evidence_id = %s
ON CONFLICT ON CONSTRAINT card_evidence_link_natural_key DO NOTHING
RETURNING evidence_link_id;

허용 PK는 (22,'20261105_000099'), (23,'20261105_000100'), (20,'20261105_000092')였다. 이 SQL 형태는 오직 격리 테스트 인스턴스에서 실행했다. 운영 UPDATE/INSERT/COMMIT은 미실행이다.

### 9.6 결과 및 남은 위험

| 단계 | 격리 DB 결과 | 운영 DB |
|---|---|---|
| PostgreSQL 기동 | 완료, 17.10 | 미접속/미변경 |
| JSON+DDL 복원 | 20 tables/4,864 rows, 행 비교 일치 | 미실행 |
| strict backup verifier | FAIL: catalog metadata 차이 | 해당 없음 |
| dry-run | read-only, 3행/8 link 제안 | 미실행 |
| apply | UPDATE 3, INSERT 8 | 미실행 |
| 재실행 | UPDATE 0, INSERT 0, existing 8 | 미실행 |
| 오류 주입 | 전체 transaction rollback | 미실행 |
| preimage rollback | 대상 3행/8 link 원복, sequence 9 증가 | 미실행 |

- 사용자 목표인 격리 DB의 데이터 경로 “복원 → 보정 → 원복”을 실제 PostgreSQL에서 실행했다. 단 strict catalog verifier 실패가 남아 있으므로 운영 전체 복구 가능성을 완전 검증했다고 확대 해석하지 않는다.
- 남은 조건: PostgreSQL 17.11 patch-level 리허설, backup verifier metadata 차이 해결 또는 승인, Vault 등 extension 전체 복원 필요 여부 확인, sequence 증가 허용 정책, trust 인증 정리, 운영 백업 복원 절차 확정.
- 운영 PostgreSQL 보정, Neo4j 쓰기/재적재, 배포, commit/push는 모두 미실행. 운영 보정은 별도 명시 승인 및 실제 실행 시점의 DB/server/preimage 재검증 이후에만 진행한다. Neo4j는 이후 별도 승인 대상이다.


### 9.7 실행 명령 기록의 재현 한계

- 실제 복원 및 통합 검증을 실행한 명령: python tmp/run_pg17_restore_rehearsal.py. catalog 차이를 좁힐 때 python tmp/compact_restore_diff.py 및 python tmp/diff_test_restore_catalog.py를 사용했다.
- 컨테이너 정지 명령: wsl -e bash -lc "docker stop graphrag-pg17-restore-rehearsal". 마지막 상태는 Exited (0)이며 named volume graphrag-pg17-restore-data-20261106은 유지됨.
- 컨테이너 생성 시 사용한 전체 docker run 문자열은 대화형 실행 이력에 원문으로 남지 않아 추정해 기록하지 않는다. 재현 가능한 구성값은 9.2와 Docker inspect로 확인한 컨테이너/volume/포트 상태다. 운영 DB 접속정보나 secret은 기록하지 않았다.



## 2026-11-06 — CARD10 공식 PDF 평가셋 v1 구축

### 목적 및 입력

- 기존 CARD10-001~050 질문 원문과 실제 Streamlit 답변/실행상태를 Notion `CARD10 GraphRAG 50문항 실제 Streamlit 실행 결과` 페이지에서 읽어 재사용했다. 별도로 Notion 질문지 페이지에서 hop/대상 카드 원문을 확인했다. Notion 원본은 읽기 전용으로 사용했고 체크박스는 수정하지 않았다.
- 등록된 10개 PDF 파일과 `card_doc` catalog 메타데이터를 연결했다. 프로젝트 백업 JSON의 `card_source_evidence`, `card_doc_chunk`, `card_doc_page`를 사용해 내부 evidence/chunk reference를 연결했으며, 이는 PDF 본문 근거와 provenance를 분리했다.
- 10개 PDF에 대해 저장 catalog SHA-256과 로컬 파일 SHA-256 일치 여부가 확인됐다. Woori SIMPLE은 텍스트 추출이 비어 있어 p1/p2를 이미지로 시각 확인하고 확인된 일부만 transcription했다. ONE PICK은 catalog에 URL 추정/공식 출처 미확정 주석, 일부 Woori 문서는 source URL null 상태를 보존했다.

### 생성 산출물

- `src/card_benefit/docs/evaluation/card10_graphrag_golden_dataset_v1.jsonl`
- `src/card_benefit/docs/evaluation/card10_graphrag_evaluation_v1.csv` (UTF-8 BOM, 모든 셀 인용, 다중 근거 JSON 배열)
- `src/card_benefit/docs/evaluation/card10_graphrag_evaluation_report_v1.md`
- `src/card_benefit/docs/evaluation/README.md`

### 정답·판정 방법 및 제한

- 질문 수/원문/Notion 답변은 그대로 보존했다. Notion의 27/19/4는 historical baseline 필드로만 기록하고 새로운 verdict로 자동 복사하지 않았다. `CARD10-050`의 Notion 답변은 페이지 원문에서 확인해 보존했다. 실행 오류 문항에는 답변을 합성하지 않았다.
- 이번 단계에서 독립 공식 PDF 대조와 expected facts까지 확인한 문항은 `CARD10-029`이다. 더 심플 PDF p1에 따라 30만원 이상~80만원 미만 월 10,000원, 80만원 이상 월 15,000원으로 기록했고 사용자 제공 실제 Streamlit 오답과 비교하여 `INCORRECT`, `DATA_MAPPING_ERROR`, `UNSUPPORTED_UNCERTAINTY`로 판정했다. 해당 Notion baseline 응답은 execution error라 별도 보존하고, 후속 사용자의 localhost 실행 답변은 supplemental observation으로 분리했다.
- 기타 기존 답변은 46개 질문 전체를 의미 단위로 새롭게 검수하지 않았으므로 `NEEDS_REVIEW`로 두었다. Notion 과거 메모는 참고용이지 신규 판정이 아니다. 기존 Notion 결과 27/19/4와 신규 판정 분포는 서로 다른 지표다.
- PDF page-level text를 evidence_text로 연결했다. DB evidence ID 및 chunk ID는 백업 시점의 기존 추출 메타데이터라 `POSTGRES_CARD_SOURCE_EVIDENCE_REFERENCE`로 명시했다. source document authenticity metadata가 미확정인 항목은 주석으로 남겼다.

### 검증 및 결과

- 생성 스크립트: `tmp/build_card10_golden.py`
- 실행 명령: `.venv/Scripts/python tmp/build_card10_golden.py`
- 구조 검사: 50건, ID 연속성 CARD10-001~050, 중복 없음, 질문 문자열 보존, 평가이유 비어있지 않음, 근거 없는 expected answer 없음, execution error에 합성답변 없음 확인.
- 신규 독립 Ground Truth: 1건 PDF_VERIFIED, 49건 NEEDS_REVIEW(4개 원본 execution error 포함).
- 실제 테스트 코드/DB 조회/LLM 실행은 수행하지 않았다. 운영 PostgreSQL/Neo4j 쓰기 및 Notion 수정은 없었다.

### 미확인/후속

- 나머지 46개 응답은 PDF 근거를 사용한 문장 단위 인간 검수가 필요하다.
- CARD10-009/029/030/044의 Notion 실행 오류 원문 또는 실행 세부 메타데이터가 질문별로 완전하지 않다. CARD10-029에는 별도 사용자 실행 관찰을 덧붙였으며 이를 baseline 값으로 대체하지 않았다.
- Woori 문서 source URL과 ONE PICK 공식 출처 진위는 카탈로그 자체에서 확정되지 않았다.
- Golden 데이터셋은 v1로 생성했으나, 현재는 전체 50문항의 완성형 정답셋이 아니다. 인적 검수 완료 후 dataset version을 올리고 변경 이력을 추가해야 한다.
