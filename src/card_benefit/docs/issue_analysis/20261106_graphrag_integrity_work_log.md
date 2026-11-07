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
- 기존 작업의 Markdown 20개 생성 및 PDF 누락 10개 보류 기록은 보존했습니다.

## 2026-11-06 — 누락 PDF 재검사 및 후속 변환

- 후속 검사에서 보류 문서 10개 모두 manifest 상대경로의 원본 PDF를 찾았습니다. 각 파일명 후보는 1개였고 파일 크기 및 SHA-256이 manifest와 일치했습니다.
- 해당 10개만 PyMuPDF 1.28.2로 변환했습니다. 기존 20개 Markdown은 덮어쓰거나 재변환하지 않았습니다.
- 전체 manifest 30개에서 PDF 해시 일치, Markdown 존재/비영 크기, UTF-8 디코딩 및 페이지 표식 수를 확인했습니다. 해시 오류, PDF 누락, Markdown 누락은 없습니다.
- 우리카드 브랜드 안내 PDF 5개와 SIMPLE 카드 PDF 1개는 텍스트 레이어가 없어 추출 불가 표식으로 남겼습니다. 본문 변환 성공으로 간주하지 않으며 육안 확인 및 로컬 OCR/전사가 필요합니다.
- 표·혜택 실적 구간·할인/적립액·한도 연결은 전 문서에서 원문 PDF 수동 검수 대상입니다. 상세 결과는 `src/card_benefit/docs/guide/PDF_TO_MARKDOWN_MANIFEST_CONVERSION_REPORT.md`에 기록했습니다.

## 2026-11-06 — app_log 읽기 쉬운 Neo4j/PDF 요약 컬럼

- `execution_log.py`에 `outcome_neo4j_summary`, `outcome_pdf_evidence_summary`를 추가했습니다. 두 함수는 최종 outcome의 기존 값만 이용하고 실패 시 `None`을 반환합니다. 추가 Neo4j/PostgreSQL 업무 조회나 LLM 호출은 하지 않습니다.
- Neo4j 요약은 답변 points의 benefit ID와 `retrieved_data`의 검증된 Ref를 연결해 출력하며, 검색 후보 전체를 최종 답변에 사용된 노드처럼 표시하지 않습니다. `dp_supported_by`는 답변 point의 evidence ID만 표시합니다. 답변 구조화 검증 상태와 PDF 원문 인용은 별도임을 표시합니다. Ref가 없는 경우 Key/Label을 만들지 않습니다.
- PDF 요약은 `answer.points[].evidence_ids`로 인용/미인용을 분리하고, 기존 `pdf_evidence_text`에 기록된 인용 원문, 문서, 파일, 페이지, 청크 및 소유 관계를 출력합니다. evidence ID가 같은 여러 위치/관계는 유지하고 원문을 변경하지 않습니다.
- `persist_app_logs`의 INSERT 및 ON CONFLICT UPDATE에 신규 두 컬럼을 추가했습니다. Streamlit 정상 응답, 예외(부분 outcome이 있으면 그 데이터), 동일 질문 재사용 경로 모두 summary를 전달합니다. 저장 실패는 기존처럼 경고만 기록해 답변을 실패시키지 않습니다.
- SQL은 `src/card_benefit/sql/db_pipeline_app_log_summaries.sql`에 작성했습니다. DDL은 nullable TEXT 컬럼 두 개만 추가합니다. 롤백은 새 컬럼을 DROP하는 명령이며, 컬럼 사용 전 검토 후 실행해야 합니다.
- 사전 확인 및 기존 행 count/예시를 위한 읽기 전용 SQL은 `src/card_benefit/sql/db_pipeline_app_log_summaries_precheck.sql`에 있습니다. 현재 연결 대상 DB 식별자 및 실제 `app_log` 구조를 확인하지 않았고, 실제 app_log ID 261의 행도 이 로컬 워크스페이스에 제공되지 않아 운영 DB 접근/DDL/일괄 UPDATE를 하지 않았습니다. 과거 로그 보정 대상 수는 DB에서 precheck 실행 전까지 미확인입니다.
- 과거 데이터 보정은 `summaries_from_stored_app_log(detail_text, pdf_evidence_text)`로 기존 JSON에서 재구성할 수 있습니다. 새 컬럼 추가 후 대상 count와 샘플을 확인하고 별도 승인을 받은 뒤, 애플리케이션 함수로 건별 요약을 생성해 UPDATE하는 절차입니다. 기존 JSON은 수정하지 않습니다.
- 대표 출력 형식:
  - Neo4j: `혜택: 주요 간편결제 모아포인트 추가적립`, `노드 Key: ["card_bnft",23,"20261105_000100"]`, `답변 검증: STRUCTURED_ONLY`, Evidence ID `20261105_002740`, `20261105_002742`, `20261105_002743`.
  - PDF: 문서 `카드의정석 POINT II 상품안내장`, 문서 ID `20261105_000043`, 페이지 3, 청크 `20261105_000176`; 원문 인용 `2만원`, `통합 월 적립 한도`, `특별/추가 적립`은 입력 JSON 값을 그대로 출력합니다.
- 검증: `test_app_log_summaries.py`, `test_evidence_trace_log.py`, `test_detail_trace_log.py` 총 11개 통과; 변경 Python 파일 `py_compile` 통과. 테스트는 운영 DB 쓰기 없이 수행했습니다. JSON 누락/null/잘못된 형식, 두 혜택 분리, 역사 JSON 재구성을 포함합니다.

### 승인된 운영 DB 적용 및 실데이터 검증

- 연결 식별: Supabase pooler `aws-0-eu-west-1.pooler.supabase.com:5432`, database `postgres`, project ref `yucdexyyrwnpmeoornuz`, PostgreSQL 17.11. 비밀번호/토큰은 기록하지 않았습니다. `db_pipeline.app_log` 존재 및 기존 GraphRAG 전용 컬럼(`detail_text`, `pdf_evidence_text`)으로 프로젝트 DB임을 확인했습니다.
- DDL 전 컬럼: 11개; 신규 컬럼 없음. 행 수 129.
- 실행 SQL: `src/card_benefit/sql/db_pipeline_app_log_summaries.sql`의 `ALTER TABLE db_pipeline.app_log ADD COLUMN IF NOT EXISTS ...` 문. 적용 후 `neo4j_summary TEXT NULL`, `pdf_evidence_summary TEXT NULL` 확인. 다른 기존 컬럼과 행은 유지됐고 DDL 후 행 수는 129.
- 자동 테스트: 11 passed. Streamlit 서버는 로컬 8501 포트에서 시작됐으나 CUA 브라우저 backend가 unavailable이라 화면에서 입력하는 UI 테스트는 보류했습니다. 서버를 통해 세션 입력하지 못했습니다.
- 대체 통합 테스트: 같은 Streamlit 모듈의 `get_pipeline(SEARCH_MODE)` 실호출로 질문을 실행하고, 기존 persist 함수로 저장했습니다. 정확한 질문 결과는 “전월 실적이 60만원이면 … 통합 월 한도는 2만원입니다.” 신규 정상행 `app_log_id=263`; request/response/detail_text/pdf_evidence_text/두 요약 컬럼 모두 비어 있지 않습니다.
- `app_log_id=263` 요약 확인: Node Label `dp_node, dp_card_bnft, dp_card_product_item`; Node Key `["card_bnft",23,"20261105_000100"]`; 혜택 `주요 간편결제 모아포인트 추가적립`; 상태 `ANSWERED`; 인용 Evidence `20261105_002740`, `20261105_002742`, `20261105_002743`. PDF 문서 `카드의정석 POINT II 상품안내장`, 문서 ID `20261105_000043`, 3페이지, 청크 `20261105_000176`; 인용 원문 `2만원`, `통합 월 적립 한도`, `특별/추가 적립`. 검색됐으나 답변에서 인용되지 않은 근거도 분리 출력됨. 기존 실제 예시 행 `app_log_id=261`도 재구성 결과가 같은 문서/페이지/청크/인용과 일치함을 확인했습니다.
- 첫 직접실행 시도는 PowerShell stdin 인코딩 때문에 request_text가 깨져 `app_log_id=262`로 저장됐습니다. 해당 행은 허용된 범위 밖의 수정/삭제를 하지 않고 보존했습니다. 정확한 Unicode 입력으로 재실행한 정상 검증행은 263입니다.
- 기존 로그 보정 전: 131행 중 두 요약 중 하나 이상 NULL인 행 129개, 재구성 가능한 행 92개(그중 1행은 기존 요약 한 컬럼만 보충 가능). 보정은 `UPDATE app_log SET neo4j_summary=COALESCE(...), pdf_evidence_summary=COALESCE(...) WHERE app_log_id=... AND (summary IS NULL...)` 형태의 단일 DB 트랜잭션으로 수행했습니다. 최종 업데이트 92행(91행은 두 컬럼 모두 채움, 1행은 PDF 요약만 채움); 행 수 131 유지; 요약 NULL 행 38개.
- 미보정 38행: JSON이 없거나 재구성 가능한 provenance가 없어 둘 다 비어 있는 37행(IDs는 141, 142, 152, 161, 162, 176, 183–192, 194–199, 201, 203, 205, 213, 215, 217, 225, 227, 229, 237, 239, 241, 249, 251, 253), 그리고 `app_log_id=193`은 PDF 요약만 이미/추가 가능하고 Neo4j 요약 입력이 없어 유지됐습니다. JSON 파싱 오류 0건.
- 보정 UPDATE는 두 신규 요약 컬럼만 설정했으며 `detail_text`, `pdf_evidence_text`, `response_text`, `execution_log`, `created_at`, 기본키는 UPDATE 문에서 변경하지 않았습니다. 행 수는 131로 유지됐습니다. 운영 DB 검증 결과 조회문은 사용자 제공 SELECT를 그대로 사용하면 됩니다.

## 2026-11-06 — app_log 263 실적 조건·한도 근거 연결 분석 (읽기 전용)

- 확인 대상: `db_pipeline.app_log.app_log_id=263`, 질문은 POINT II 전월 실적 60만원의 특별·추가 적립 통합 월 한도, 답변은 2만원. 이번 분석에서는 PostgreSQL/Neo4j/코드를 변경하지 않았습니다.
- PDF 원문 확인: `src/card_benefit/data/raw/woori_all/credit/상품안내장_카드의정석 POINT II_260901.pdf`, SHA-256 `0a4da23acb9a331182f15aa2591314cb2116a5a7ea40092b57932004612e973d`, 문서 ID `20261105_000043`, 3페이지. PDF 표의 같은 행에 `전월 국내가맹점 이용실적 60만원 이상 | 특별/추가 적립 | 2만원`이 배치되어 있어 원문상 관계는 명확합니다. 아래쪽도 같은 열 구조로 30만원 이상→1만원, 120만원 이상→5만원입니다.
- PDF 추출 자료의 위치별 Evidence: `20261105_002745`는 “전월 국내가맹점 이용실적 60만원 이상”(offset 419–440), `20261105_002740`는 “2만원”(471–473), `20261105_002742`는 “통합 월 적립 한도”(772–781), `20261105_002743`는 “특별/추가 적립”(404–411). 네 항목 모두 문서 `20261105_000043`, 3페이지, 청크 `20261105_000176`, 원본 추출 상태 `PENDING`입니다. PDF의 위치 정렬 때문에 60만원 행·금액 토큰이 서로 인접한 offset은 아니지만, 실제 PDF 표에서는 같은 행에 있습니다.
- 원천 추출 데이터: `db_pipeline.card_extr_stg.card_extr_stg_id=20261105_000636`의 `stg_raw_item`에는 `r2.conditions`의 `c2`, `cond_min_amt=600000`, basis `PREV_MONTH_SPEND`, `limit_keys=["l2"]`가 있습니다. 같은 객체의 `limits`에서 `l2.limit_num=20000`, `period_cd=MONTH`, `shared_scope_txt=특별/추가 적립`입니다. 이 staging 구조에는 60만원→l2→2만원 매핑이 명시적으로 존재합니다. 조건 원문 인용은 `20261105_002745`, cap 인용은 `20261105_002740`으로 `card_source_evidence`에 있고 둘 다 동일 stage/document/page/chunk에 연결됩니다.
- 정규화 PostgreSQL/Neo4j 상태: `card_product_item` ID `20261105_000100`의 `item_data`는 `{}`이고 `rule_list`에는 r1=30만원, r2=60만원, r3=120만원의 `cond_expr` 및 모두 3% 적립이 있지만 cap `limit_keys`는 남아 있지 않습니다. Neo4j 혜택 Ref는 `card_product_item:23:20261105_000100`, Node Key `["card_bnft",23,"20261105_000100"]`, 실제 Labels `["dp_node","dp_card_bnft","dp_card_product_item"]`입니다. 해당 노드의 `limit_text`는 `1만원 / 2만원 / 5만원 / 통합 월 적립 한도 / 특별/추가 적립`을 나열할 뿐 tier 매핑을 구조화하지 않습니다.
- Neo4j 조건 노드 Key는 `["cond_atom","RULE:23:20261105_000100:r1",1,"c1"]`, `["cond_atom","RULE:23:20261105_000100:r2",1,"c2"]`, `["cond_atom","RULE:23:20261105_000100:r3",1,"c3"]`; 각각 min amount 300000, 600000, 1200000 및 `SPEND_REQ`입니다. `c2`의 raw text는 “전월 국내가맹점 이용실적 60만원 이상”입니다. 이 조건 노드에서 `dp_supported_by`로 향하는 관계는 0건이며 condition evidence 2744/2745/2746은 Neo4j `dp_card_source_evidence` 노드로도 조회되지 않았습니다.
- RULE 근거 관계: `dp_supported_by`는 적재되어 있습니다. r1/r2/r3 모두 `20261105_002735`(원문 “3% 추가적립”)를 연결합니다. 이는 적립률 규칙 인용이며 60만원 조건이나 cap 선택의 PDF 근거는 아닙니다. 혜택 노드에는 7개 BNFT 근거 연결이 있습니다. `20261105_002745` 등 조건 셀 Evidence의 `card_evidence_link` 행은 없고 해당 ID들의 `ev_subject_cd=BNFT` 노드 관계도 없습니다. 따라서 RULE 관계 존재와 COND 관계 존재를 구분해야 합니다.
- 프로그램 파생 계산 여부: 맞습니다. `previous_month_spend()`가 질문에서 600000을 읽고, `benefit_context()`가 Ref가 `card_product_item:23:20261105_000100`일 때 `point2_shared_cap_policy()`를 호출합니다. 이 함수는 코드 상수 300000→10000, 600000→20000, 1200000→50000을 사용하며 600000에 대해 `source=PROGRAM_DERIVED`, `selected={min_amt:600000,cap_amount:20000,derived_max_amt_excl:1200000}`를 반환했습니다. 원천 staging에도 같은 연결이 남아 있지만 Neo4j 최종 노드/관계에는 없으므로 실행 시점 매핑은 프로그램 정책으로 산출됩니다.
- `validate_answer()`는 답변을 이 파생 정책 tier와 비교합니다. `_has_structured_limit_tiers()`는 `program_cap_policy.tiers`도 구조 tier로 인정하고 `distorts_limit_tier()`가 60만원 tier에서 2만원이 아닌 값을 말하는 오류를 차단합니다. 따라서 숫자/구간 연결 검증은 코드 파생 mapping 기준으로 수행됩니다. PDF Evidence가 60만원과 2만원의 관계를 모두 증명했는지 검사하거나 그 관계 Evidence ID를 답변에 강제하는 검증은 아닙니다. `verification_level()`의 개별 원문 숫자 일치 판정 역시 tier-to-cap 의미 관계를 인증하지 않습니다.
- app_log 인용: answer point는 `20261105_002740`, `20261105_002742`, `20261105_002743`만 인용했습니다. 즉 금액, “통합 월 적립 한도” 제목, “특별/추가 적립” 셀은 인용했으나 60만원 조건 Evidence `20261105_002745`는 빠졌습니다. 검색/답변 outcome의 PDF evidence 목록에서 인용되지 않은 것은 `20261105_002734`(혜택명/3% 추가적립), `20261105_002738`(대상 가맹점), `20261105_002739`(1만원), `20261105_002741`(5만원)입니다. `20261105_002745`는 outcome에서 검색된 미인용 근거가 아니라, 추출 데이터/PDF에는 있지만 해당 outcome에 들어오지 않은 근거입니다. Neo4j에서 확인된 rule evidence `20261105_002735`는 outcome PDF evidence 목록에 없어 검색·인용 모두 이 로그에서 확인되지 않습니다.
- 요약 컬럼 누락: `neo4j_summary`는 카드 혜택 Label/Key와 답변 point의 사용 Evidence ID를 표시하지만 point의 `verification="STRUCTURED_ONLY"`, `origin="llm"`, 파생 policy의 `PROGRAM_DERIVED`, 선택 tier 600000→20000은 포함하지 않습니다. 상단 `ANSWERED`는 답변 상태일 뿐 point 검증 등급이 아닙니다. `pdf_evidence_summary`는 outcome에 포함된 7개 Evidence만 다뤄서 2745 조건 인용을 표시하지 못하며, 미인용 목록도 outcome 내부 검색 결과까지만 보여 줍니다. 따라서 PDF 원문 전체에서 추출된 2744–2746이 없다는 점과 별도 추출 매핑을 표시하지 않습니다.
- 추적 요약: 질문의 600000 → 혜택 `주요 간편결제 모아포인트 추가적립` → Neo4j r2/c2 `SPEND_REQ 600000` → staging `r2.limit_keys=[l2]` 및 l2 월 20000 → 코드 policy가 같은 값을 `PROGRAM_DERIVED`로 선택 → PDF p.3 동일 행 “60만원 이상 | 특별/추가 적립 | 2만원”. 원문은 연결을 확인해 주지만, 최종 Neo4j 구조화 relation/evidence 경로와 app_log 인용에는 c2/2745가 빠져 있습니다.

## 2026-11-06 — PostgreSQL 원장 기준 Neo4j dp_ 전체 재구축 및 실행 경로 검증

### 원천 매핑과 적재

- PostgreSQL `postgres`, PostgreSQL 17.11의 `db_pipeline`을 repeatable-read, read-only snapshot으로 확인했습니다. 기본 테이블 20개, 뷰 8개, 선언 PK가 없는 테이블 0개, 선언 FK 0개였습니다. 요청대로 실행 로그 `app_log`, `app_log_event_archive` 2개만 Neo4j 매핑에서 제외하고 나머지 18개 테이블 4,359행을 매핑했습니다. 실제 PK/컬럼/행수는 `src/card_benefit/docs/guide/POSTGRESQL_TO_NEO4J_SCHEMA_MAPPING.md`에 기록했습니다.
- 일반 테이블 행은 `dp_<table>` 노드로, 연결 테이블은 Relationship으로 변환했습니다. 원래 PK, NULL 컬럼, 전체 원본 행 JSON을 보존합니다. 실제 선언 FK가 없으므로 문서에 적은 FK 등가 컬럼 조인을 사용하고, 참조가 있으면 정확히 한 PK 행에만 연결되도록 검증합니다. JSON 내부 RULE/COND 노드는 만들지 않고 `source_json`과 원본 텍스트/JSON 속성을 유지했습니다. 기존 1,536차원 임베딩을 재사용했습니다.
- 기존 그래프 DB 식별자 `6ac1f0f8`을 확인하고, 삭제 전 dp_ 그래프 JSON 백업 `tmp/neo4j_dp_backup_20261106.json.gz`(1,635 nodes, 2,702 relationships, 15 constraints, 19 indexes; SHA-256 `2d639a26cce270aa679b418b401b45c245ce7681675dffb92740cf3648102189`)을 확보했습니다. 삭제 대상 dp_와 외부 관계 0을 확인한 다음 dp_ 노드/관계/인덱스/제약만 제거·재생성했습니다. 다른 데이터베이스/프로젝트는 건드리지 않았습니다.
- 전체 재적재 결과 4,359 노드, 8,648 관계(18 relation type), 제약 15개, 인덱스 19개입니다. fulltext 및 vector 인덱스 모두 `ONLINE`; 1,536차원 cosine 구성을 확인했습니다. `neo4j_validate.py`에서 PostgreSQL 원천과 노드·관계·속성을 비교해 누락/초과/차이 0, 외부 관계 0, `ok=true`를 확인했습니다. 고립 `card_ai_run` 5개는 연결할 정확한 대상 문서 참조가 없어서 원본 행으로 보존했습니다.

### Cypher 오류 재현 및 수정

- 사용자 보고 `stage=interpret / NEO4J_FAILED / CypherSyntaxError`를 live `Neo4jSearch.list_catalog()`로 재현했습니다. 원문 Neo4j 오류: `Invalid input ';': expected an expression, ',', 'ASC', 'ASCENDING', 'DESC', 'DESCENDING', 'LIMIT', 'OFFSET' or 'SKIP' (line 5, column 18 (offset: 307))`, 문제가 된 줄은 `ORDER BY name,key;`였습니다. 매퍼 쿼리의 마지막 세미콜론을 `CATALOG_BATCH_QUERY` 서브쿼리에 그대로 삽입한 것이 원인이었습니다. `_subquery()`를 통해 하위 쿼리 세미콜론을 제거하게 수정했고 live 카탈로그 133건 조회가 통과했습니다.
- Retrieve를 실제 실행해 두 번째 오류를 확인했습니다. Neo4j 메시지: `Variable rule_key not defined (line 46, column 148 (offset: 2988))`. `SECTION_FIELDS.evidence`가 `rule_key`를 모으는데 새 table-mapped `item_evidence` query가 해당 alias를 반환하지 않았습니다. `l.rule_key AS rule_key`를 추가해 해결했고 POINT II 상세에서 18개 PDF Evidence와 2745/2740 p.3을 반환했습니다.
- 규칙/조건 JSON을 RULE/COND 노드처럼 개별 조회하는 임시 변경에서는 실제 파이프라인이 `AttributeError: 'str' object has no attribute 'get'`를 냈습니다. 원본 JSON은 `context.benefit.source_json`에 유지되며 `benefit_context()`가 이를 직접 파싱하는 설계이므로, 비어 있는 rules/conditions batch projection을 유지하고 JSON은 source row에서 읽도록 되돌렸습니다. `graph_questions.cypher`는 이전 노드 모델을 요구하지 않습니다.
- 추가 live query 검증에서 배치 키워드 조회 오류도 발견했습니다: `Variable status not defined (line 18, column 32 (offset: 965))`. `LIST_BATCH_QUERY`의 외부 반환 계약은 status를 요구했지만 두 UNION 분기가 alias를 공급하지 않았습니다. 둘 다 `verification_status_cd AS status`를 반환하도록 보완했습니다. 이는 단일 키워드 조회와 달리 배치 경로에만 있던 오류였습니다.
- 코드 검색 결과 active `graph_questions.cypher`, `neo4j_hybrid_search.py`, `neo4j_search.py`, `card_graphrag.py`의 실행 Cypher에는 구형 `dp_card_bnft`, `dp_bnft_rule`, `dp_cond_*`, `dp_rule_target`, `dp_same_as` 탐색이 남지 않았습니다. 예전 label 이름은 `neo4j_validation.cypher`의 삭제 확인 목록/테스트의 부재 assertion 및 legacy 로거 key 호환성에만 있습니다. 구형 incremental sync 진입점은 차단되어 재생성에 사용되지 않습니다.

### LangGraph 및 실제 질문 검증

- LangGraph `interpret → retrieve → answer → finish`의 기본 N 경로는 Neo4j keyword/vector/RRF를 쓰며 업무 질문 중 PostgreSQL 원장을 조회하지 않습니다. 관련 Cypher는 새 table labels와 관계를 사용합니다. PostgreSQL 연결은 app_log 설정일 때 실행 로그 저장용뿐입니다.
- 통합 질문은 `카드의정석 POINT II에서 전월 실적이 60만원이면 특별·추가 적립의 통합 월 한도는 얼마야?`입니다. Neo4j 후보 ID `card_product_item:23:20261105_000100`; Retrieve Evidence 18건; 조건 20261105_002745와 금액 20261105_002740, 한도 표제 20261105_002742, 혜택 셀 20261105_002743가 모두 상품안내장 20261105_000043 3페이지, chunk 20261105_000176입니다.
- 실제 Streamlit 파일을 `AppTest.from_file()`로 실행했습니다. 위젯은 `st.form` 안의 `st.text_area(key="question")`와 `st.form_submit_button("질문하기")`이며 AppTest에선 `at.button[0]`으로 노출되고 key는 `FormSubmitter:question_form-질문하기`입니다. form state가 별도 `.run()` 때 초기화되어, 질문 입력·버튼 click 후 단일 `at.run()`으로 제출했습니다. UI 소스는 변경하지 않았습니다.
- 최종 성공 실행: N search engines `neo4j_keyword`, `neo4j_vector`, `neo4j_rrf`; selected benefit `20261105_000100`; 답변은 “전월 실적 60만원이면 … 한도는 2만원입니다”; status `ANSWERED`. 답변 point 검증 `RAW_MATCH`; citation IDs `20261105_002745`, `20261105_002740`, `20261105_002742`, `20261105_002743`; PDF p.3. `validate_answer()`에서 수치와 PDF evidence가 일치했습니다. 원천 staging validation은 `LINK_REVIEW`라 답변 외의 자료 매핑 검토 경고가 표시됐습니다. 한 번의 별도 호출에서 모델이 미선택 결과를 반환했지만 재실행 및 최종 진단에서는 동일 질문이 정상 답변을 반환했습니다. 이는 DB/Cypher 실패가 아니라 LLM 해석 결과의 변동입니다.
- 첫 AppTest 실수는 한글 label을 PowerShell stdin 인코딩으로 비교해 `submit button not found`를 발생시킨 테스트 하네스 문제였습니다. 브라우저 CUA backend는 unavailable이었지만 AppTest 실제 UI→pipeline 실행으로 대체 검증했습니다. Python `pipeline.run()`을 별도 mocking 없이 AppTest의 제출 분기에서 호출했습니다.
- 1-hop `hop1_card_benefits`와 2-hop `hop2_card_rules` live query는 ONE PICK STYLE 카드 ID `[2]`로 실행해 각각 4건을 확인했습니다. 상세 Evidence·공통 혜택·후보 관계·키워드 배치 경로도 live 읽기 테스트를 통과했습니다.

### 실행 명령과 테스트

- 재구축 실행 명령: `python -m src.card_benefit.payment_card.db_pipeline.neo4j_dry_run --schema-only`, `...neo4j_dry_run --dry-run`, `...neo4j_load_draft` (preview), `...neo4j_load_draft --apply --confirm APPROVED_DP_POSTGRES_REBUILD`, `...neo4j_validate`.
- 최종 로컬 회귀 명령: `\.venv\Scripts\python.exe -m pytest src/card_benefit/payment_card/db_pipeline/test_neo4j_relational_model.py src/card_benefit/payment_card/db_pipeline/test_neo4j_dry_run.py src/card_benefit/payment_card/db_pipeline/test_neo4j_load_draft.py src/card_benefit/payment_card/db_pipeline/test_neo4j_validate.py src/card_benefit/payment_card/db_pipeline/test_neo4j_relation_sync.py src/card_benefit/payment_card/db_pipeline/test_neo4j_search_projection.py src/card_benefit/payment_card/tests/test_neo4j_hybrid_search.py src/card_benefit/payment_card/tests/test_p2_limit_tiers.py src/card_benefit/payment_card/tests/test_neo4j_origin_search.py src/card_benefit/payment_card/tests/test_neo4j_batch_queries.py src/card_benefit/payment_card/tests/test_app_log_summaries.py src/card_benefit/payment_card/tests/test_detail_trace_log.py src/card_benefit/payment_card/tests/test_evidence_trace_log.py -q`. 결과 `65 passed, 3 skipped`.
- 쿼리 수정 및 재구축 이후 마지막 실제 validator도 다시 실행했습니다. 기대/실제 4,359 nodes, 8,648 relationships, `exact_source_match=true`, `constraints_ok=true`, `indexes_ok=true`, `external_relationships=0`, `ok=true`였습니다.
- live integration은 `$env:RUN_NEO4J_INTEGRATION='1'; .\.venv\Scripts\python.exe -m pytest src/card_benefit/payment_card/tests/test_neo4j_origin_search.py -q`로 실행했으며 `25 passed`입니다. 기존 live Neo4j 전체 `test_card_graphrag` 스위트는 이전 시도에서 완료되지 않아 성공으로 표시하지 않았습니다.

### 미완료/수동 검토

- Stage `LINK_REVIEW`를 가진 혜택 매핑은 원본 PDF 표와 대조한 수동 검토가 여전히 필요합니다. 본문 답변은 실제 PDF 원문을 인용하고 `RAW_MATCH`로 검증됐으나, staging 관계 승인 상태 자체를 변경하지 않았습니다.
- Streamlit 브라우저 화면 자동화는 browser backend 불가로 수행하지 못했고 AppTest로 UI 스크립트를 실제 실행했습니다. 자연어 카드 간 비교 전체 질의 집합 및 모든 카드의 정확도 검수는 후속 검토 대상입니다.
- 이번 작업은 PostgreSQL 원장, app_log 기존 행/JSON, Neo4j dp_ 이외 데이터에 쓰기하지 않았습니다. 구형 dp_만 승인된 범위에서 재구축했습니다. Git commit/push는 하지 않았습니다.

## 2026-11-06 GraphRAG 쿼리 중복·조회량·성능 감사 (app_log 271–273)

### 범위와 실행 경로

기존 app_log와 코드를 읽고, Neo4j DB 6ac1f0f8에서 저장된 Cypher를 PROFILE로 재실행한 읽기 전용 분석이다. 질문 재실행, 임베딩/LLM API 호출, 코드·PostgreSQL 원장·Neo4j 데이터/인덱스 변경은 하지 않았다. PostgreSQL 로그 조회 세션은 default_transaction_read_only=on이었다.

호출 흐름: streamlit_app.py:428-429의 pipeline.run → LangGraph interpret(card_graphrag.py:1967)의 list_catalog() → Neo4jBenefitSearch.catalog_rows()/search() → hybrid_search와 products → LLM 후보 선택 → retrieve의 get_details()/detail_batch → answer의 card_terms() → 답변 생성·validate_answer(). N 경로는 질문마다 동일한 세 쿼리를 interpret에서 실행하고, retrieve는 선택 혜택 수만큼 한 detail_batch로 묶으며, answer는 카드 ID를 모아 TERMS를 배치 조회한다.

| app_log | 질문 / 선택 혜택 | detail key 수 | TERMS 카드 ID | 로그에 남은 고유 Evidence |
|---:|---|---:|---|---:|
| 271 | POINT II 60만원 한도 | 1: 카드 23 / 20261105_000100 | [23] | 15 |
| 272 | 더 심플 하나카드 vs 카드의정석2 DAILY 비교 | 2: 카드 22 / 20261105_000099, 카드 42 / 20261105_000180 | [22,42] | 24 |
| 273 | ONE PICK STYLE 주요 혜택·조건 | 4: 카드 2 / 20261101_000001–000004 | [2] | 26 |

### PROFILE 실측

저장된 쿼리를 현재 그래프에서 다시 실행했다. client_ms는 드라이버 왕복과 결과 수신을 포함하며 app_log 요청 당시의 역사적 실행시간이 아니다. DB Hits와 operator time은 PROFILE operator별 값을 합산했다. 직렬화 크기는 반환 레코드의 Python JSON 크기로 Bolt wire 크기와 같지는 않다.

| 쿼리 | 반환 | client ms | operator DB Hits 합 | operator time 합 | JSON 크기 |
|---|---:|---:|---:|---:|---:|
| card.catalog_batch | 1 envelope (BENEFIT 34, 기타 item 17, common 82; 내부 133) | 1,242.0 | 1,740 | 5.2 ms | 120,479 B |
| card.hybrid_search | 116 (BENEFIT 34 + common 82) | 121.3 | 1,788 | 11.5 ms | 70,030 B |
| card.products | 10 | 98.4 | 21 | 0.1 ms | 294 B |
| 271.card.detail_batch | 1 | 966.1 | 3,474 | 5.5 ms | 1,611,045 B |
| 271.card.terms | 0 | 95.7 | 11 | 0.2 ms | 2 B |
| 272.card.detail_batch | 2 | 1,703.1 | 5,851 | 9.0 ms | 3,628,860 B |
| 272.card.terms | 11 | 97.6 | 269 | 0.7 ms | 41,443 B |
| 273.card.detail_batch | 4 | 2,769.8 | 10,939 | 13.1 ms | 5,341,073 B |
| 273.card.terms | 0 | 96.7 | 17 | 0.2 ms | 2 B |

detail_batch Evidence 확장 branch는 18/27/51행을 만들었고 collect_evidence()는 evidence_id로 합쳐 15/24/26개를 결과에 남겼다. 이 병합은 여러 혜택·규칙의 소유 관계를 보존하므로 그 lineage를 없애면 안 된다.

app_log.execution_log에는 QUERY 문장만 저장되고 CYPHER 요약 rows/elapsed_ms가 없다(execution_log.py:417-424). Python 후보 처리 및 LLM 호출의 실제 시간도 해당 요청에 저장되지 않는다. 유료 호출 없이 그 구간별 시간은 측정할 수 없었다. app_log의 qvec는 앞부분 미리보기만 있어 원래 질문 벡터를 복원할 수 없었다. hybrid PROFILE은 동일 타깃 혜택의 Neo4j 저장 임베딩(1,536차원)을 대용 입력으로 썼으므로 쿼리 계획/부하 측정이며 질문별 원래 qvec 측정은 아니다.

### 실행 계획과 중복 분석

현재 벡터 인덱스 2개와 FULLTEXT 인덱스는 ONLINE/100%였다. 그러나 CANDIDATES_QUERY는 vector.similarity.cosine을 각 행에 계산한다. PROFILE은 카드 BENEFIT 쪽 51행 NodeIndexScan 및 common 쪽 82행 NodeByLabelScan을 보였고 vector-index seek 연산자나 fulltext 호출은 없었다. 따라서 이 쿼리는 벡터 인덱스 대신 현재 후보 전체에서 정확 코사인을 계산한다. 후보 116개에서 실측 부담은 작지만 규모에 따라 순회 비용은 증가한다.

| 쿼리와 호출 | 목적·입력·실제 조회 | 중복/필수 여부 | 개선 방향 및 영향 |
|---|---|---|---|
| card.catalog_batch — neo4j_search.py:144-151,308-321; interpret | 파라미터 없음. BENEFIT·기타 상품항목·공통혜택 133개 전부. 카드 source_json, 항목 source_json을 catalog_rows()가 후보를 연결하고 연회비 same_fact 참조에 사용. | 후보 ID/연회비 처리에 역할은 있지만 매 요청 120 KB 전량 회수. 후보 hybrid 결과와 카드/혜택 메타데이터 일부 중복. | 일반 질문은 검색 후보에 필요한 속성만 전달하고, 연회비/동일 사실 질문에서 전체 항목을 보충하거나 선택 key만 조회. 후보 ID 검증 및 연회비 fallback 영향. |
| card.hybrid_search — neo4j_hybrid_search.py:15-38,87-151; interpret | qvec 1,536차원. 카드 BENEFIT 34 + common 82, 116행 전체에서 name/search/rule/limit 텍스트와 sim 계산. Python이 키워드 점수·RRF 후 top 8. | 검색 핵심. 명시 카드가 있어도 전체를 먼저 조회. 현재 vector/fulltext 인덱스 미사용. | 명시 카드 식별 시 해당 카드 혜택+적용 공통혜택 범위를 먼저 탐색하되, 모호·비교·공통 질문은 전체검색 fallback. 정확도/recall 회귀 검증 필수. |
| card.products — neo4j_hybrid_search.py:40,92-104; interpret | 파라미터 없음. 상품 10개 ID/이름으로 카드명 token matching. | hybrid 쿼리가 카드 BENEFIT마다 card_id/product_nm을 반환한다. 실제 graph에서 상품 10개 전부 BENEFIT item이 있음을 확인해 현재 결과와 중복. 왕복 약 98 ms, 응답은 294 B. | 기존 candidate rows에서 카드명을 판별하거나 catalog 결과에 상품 목록을 포함해 왕복 제거. 미래 BENEFIT 없는 카드는 fallback으로 보장. |
| card.detail_batch — neo4j_search.py:126-139,337-359; retrieve | 선택 key 1/2/4개로 context·조건/한도·Evidence를 배치 조회. 응답 1.61/3.63/5.34 MB. Python은 주로 source_json에서 원장 JSON, 카드/혜택 이름·검증상태, Evidence 원문·위치·관계 lineage를 사용한다. | 상세/PDF는 필수. properties(b), properties(owner/evidence/chunk/page/doc)로 노드 전체를 매 Evidence 경로마다 반환한다. benefit_rules/benefit_conditions compatibility 서브쿼리는 새 graph에서 LIMIT 0인데도 label scan을 한다. | 명시 속성만 반환하고 key seek 계획을 재검증. evidence_id 병합은 유지하되 distinct owner/link 관계는 보존. source_json에서 rule_list/item_cond_expr를 직접 읽는 신규 item 경로의 0행 RULE/COND branch 제거 검토. Evidence·조건·제외 처리에 회귀 영향. |
| card.terms — neo4j_hybrid_search.py:41-49,174-188; card_graphrag.py:2175-2185; answer | 선택 card_ids. TERMS JSON 및 ITEM 근거. 271:[23]=0행, 272:[22,42]=11행/41 KB, 273:[2]=0행. attach_terms()가 scope(ALL_BENEFITS/PERFORMANCE/NAMED_ITEMS)로 적용 혜택만 남긴다. | 제외·주의·실적 조건의 정합성에 필요할 수 있어 무조건 제거 불가. 매 답변에서 조건 없이 호출하며 세 건 중 두 건은 빈 결과. 조회는 카드별 배치. | intent·조건/제외 문맥 필요 여부와 TERMS 존재 여부에 따라 조건부 호출. 제외를 보장해야 할 때는 유지. 빈 결과 반복 read는 요청/세션 범위 cache 검토. TERMS 문맥·Evidence 누락 위험. |

catalog_batch는 한 result envelope 안에 133개의 nested row를 가져온다. 별도 products 결과는 10행이고 후보 query가 이름을 이미 포함한다. catalog와 products의 별도 네트워크 왕복은 합칠 여지가 있다. 상품 10/10이 BENEFIT item을 가진다는 확인은 현재 그래프에만 적용되는 안전성 근거다.

detail_batch에서 LIMIT 0 RULE/COND 서브쿼리 외에도 key 탐색 시 PROFILE에서 dp_node.key RANGE seek 대신 UnionNodeByLabelsScan/NodeByLabelScan이 반복됐다. dp_node.key 인덱스가 ONLINE이어도 현재 MATCH 형태가 해당 인덱스를 이용하지 않는 결과다. properties(b)는 embedding 등 답변 경로에서 필요 없는 속성도 반환하고 Evidence owner 전체 properties를 Evidence마다 반복해 큰 응답을 만든다.

### 우선순위

1. detail_batch 전체 properties와 반복 Evidence owner payload를 명시 속성으로 줄이고, 사용되지 않는 0행 RULE/COND compatibility branch를 정리한다. 관찰된 가장 큰 client 비용/응답량이다.
2. catalog_batch에서 N 모드 일반 질문의 전체 catalog 전송을 줄이고 card.products 왕복을 합치거나 candidate rows에서 대체한다. 연회비와 미분류 상품은 안전한 보완 경로로 남긴다.
3. 명시 카드 질문의 hybrid 후보 범위 축소를 시험하되 불명확·비교·공통 혜택 질문에서는 전체 후보와 RRF를 유지한다. 벡터 인덱스는 현재 작은 116 후보의 성능만으로 변경을 정당화하지 말고 정확도와 후보 회수율을 함께 비교한다.

card.terms는 271·273에서 빈 결과에도 약 96 ms 왕복이 있었지만 272에서 11행을 제공하므로 단순 삭제 대상이 아니다. query type별 조건부 호출은 다음 후보로 평가한다. 이번 작업은 성능 분석 및 이력 기록만 수행했다.
## 2026-11-07 — 신규 dp_ 데이터 계약 정합성, 조회량 축소, 실제 응답 성능 검증

### 수정 내용

- `neo4j_search.py`, `graph_questions.cypher`, `card_graphrag.py`, `neo4j_hybrid_search.py`를 신규 `dp_card_product_item` 구조에 맞췄다. 혜택 규칙과 조건은 `rule_list`, `item_cond_expr`, `item_data`에서 정규화하며 빈 RULE/COND 호환 쿼리를 사용하지 않는다. `source_json` 값은 원본 노드에 그대로 있고, Python 소비 로직은 조회된 신규 구조를 이용한다.
- `benefit_context`, `condition_groups`, `unresolved_items`, `attach_terms`, 결제액 필터, 제외 판정, `validate_answer`가 규칙별 조건·SPEND_REQ·적용 범위를 읽도록 유지했다. `TERMS`는 조건이 맞는 선택 혜택의 item_id만 조회한다. 이 실행에서는 1홉 및 POINT II 질문은 적용 TERMS가 없어 쿼리를 건너뛰었고, 비교 질문은 적용 가능한 11개 item으로 제한해 11행(67,159 bytes)을 조회했다.
- 실제 4개 선택 혜택의 상세 Cypher 반환은 166,344 bytes였다. 같은 4개 혜택을 조회한 과거 `app_log=273` 경로의 5.34 MB 대비 약 96.9% 감소했다. 단일 대중교통 혜택은 28,856 bytes, POINT II 혜택은 31,307 bytes였다. PDF Evidence는 전체 67개(비교), 8개(대중교통), 15개(POINT II) 모두 State와 로그 결과에 남는다. LLM 문맥에는 혜택별 후보 Evidence를 한정해 중복 대형 `source_json`을 보내지 않는다. 인용 검증은 전달된 실제 근거만 대상으로 한다.
- `benefit_evidence`는 원문 인용, page, chunk, document의 직접 컬럼만 돌려주고 evidence/relationship/document 계층의 대형 JSON 중복을 제거했다. `execution_log`가 쓰는 문서명·파일명·페이지·청크 직접 속성은 유지했다. 카탈로그 배치에도 `item_rule_txt`, `item_limit_txt`를 포함해 LLM이 질문의 혜택 표현과 이름이 다른 경우 원문 설명으로 매칭할 수 있게 했다.
- `catalog_batch` 결과를 상품 목록과 캐시에 함께 활용해 `card.products` 별도 조회를 생략한다. 비교·공통 검색 정확도는 기존 keyword/vector/RRF 경로를 유지했다. 전체 cosine 계산은 여전히 수행하고 vector index pushdown은 확인되지 않아 미검증 최적화를 추가하지 않았다.
- `compact_answer_context()`는 답변 검증용 전체 context를 바꾸지 않고 LLM 프롬프트에서 중복 `limits`, `condition_text`, `exclusion_text`, `targets` 투영만 제거한다. 4개 혜택 비교에서 LLM 입력이 20,485 tokens에서 마지막 검증 16,519 tokens로 약 19.4% 감소했다. 비교 응답은 선택 혜택별 결과를 하나씩 빠짐없이 제시하도록 제한했다.
- `verify_view.py`가 batch plan의 `parameters.keys`를 표시하도록 수정했다. AppTest 예외 경로에서 outcome이 `None`일 때 전체 시간 계측이 예외를 만들지 않도록 방어했다. 예시 질문 AppTest도 `st.pills`의 실제 label/key를 사용한다. `answer()`에 request id context 설정을 추가해 TERMS 쿼리 계측이 요청 ID를 유지한다.
- 기본 Streamlit 검색 모드 N은 Neo4j hybrid 검색만 사용한다. 실제 N 경로는 PostgreSQL 원장 검색을 호출하지 않았다. 비교 AppTest는 적용 가능한 TERMS를 Neo4j에서만 조회했다. 실행 로그 DB 저장은 AppTest에서 `APP_DB_LOG_ENABLED=false`로 끄고 검사했으며 PostgreSQL 데이터 변경은 하지 않았다. 기존 선택형 B/C 호환 코드는 남아 있으나 기본 Streamlit 경로가 아니다.

### 실제 테스트 및 성능

| 요청 | 실제 응답 | 총 처리 측정 | 질문 임베딩 | catalog_batch | hybrid 검색 | interpret LLM | detail_batch | answer LLM | 검증 | 상세 반환 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1홉: ONE PICK 대중교통 | ANSWERED, 버스·지하철 5%, 월 1,000원 한도, 전월 10만원 조건, 유예 및 제외 설명. Evidence 000044/000046/000048/000049/000050 | 9.870 s (`pipeline.run`) | 0.512 s | 1.515 s | Cypher 0.377 s | 2.303 s | 0.366 s | 4.765 s | 0.005 s | 28,856 B |
| 2홉: POINT II 전월 60만원 한도 | ANSWERED, 2만원. 답변이 Evidence 002745·002740·002742에 인용; 002748·002749는 추가적립 제외/대상 설명. PDF 3쪽 | 11.444 s (`pipeline.run`) | 0.485 s | 1.492 s | Cypher 0.320 s | 3.320 s | 0.364 s | 5.430 s | 0.004 s | 31,307 B |
| 카드 비교: 더 심플 / DAILY | ANSWERED. 선택된 4개 혜택 모두 답변에 포함; 더 심플 구간 규칙 선택의 미확정 상태를 별도 표시; DAILY 조건·한도와 Evidence 인용 검증 | 실제 실행 프로세스 20.1 s (AppTest 외 pipeline 프로세스 포함) | 0.436 s | 1.545 s | Cypher 0.311 s | 2.397 s | 0.574 s | 약 10.8 s 범위의 마지막 관측치; 답변 1,240 tokens | <0.01 s | 166,344 B |

- 측정은 로컬 `perf_counter()`/Neo4j client elapsed/PERF 로깅을 사용했다. 비교는 최종 검증 프로세스 벽시계 20.1초였고 답변 LLM 호출이 가장 큰 구간이었다. 모델/API 응답 시간은 서버·캐시 영향을 받아 반복 간 변동한다. 이전 18–20초 응답 대비 1홉·2홉은 9.9초·11.4초로 줄었고, 비교는 답변 길이를 줄여 약 20초까지 낮췄지만 LLM이 주요 병목으로 남았다.
- 앱 로그 저장 구간은 실제 DB write를 막기 위해 실측하지 않았다. 코드에는 `app_log_save`/전체 Streamlit 요청 계측이 있고, 앱 로그 저장 자체는 기존 단위 테스트로 확인했다. 비교 테스트에서 embedding 1회 + interpret/answer chat 2회, 다른 질문도 embedding 1회 + chat 2회였다. 이번 최종 검사에서 검색 호출은 1 catalog batch + 1 hybrid + 1 detail; TERMS는 해당하는 경우에만 1번이다. app_log 저장은 실행하지 않았다.
- 최초 실제 POINT II 실행에서 interpret LLM이 관련 후보를 누락했다. 카탈로그 후보에 규칙·한도 원문 텍스트를 보강하고 interpret 기준을 명확히 한 뒤 실제 질문을 다시 실행해 선택된 혜택 `주요 간편결제 모아포인트 추가적립`을 확인했다. 최종 실제 답변은 60만원 → 2만원을 `RAW_MATCH`로 판정했다.
- 최종 실제 Streamlit AppTest는 정확한 질문을 폼의 `question` text_area에 입력하고 첫 제출 버튼을 클릭해 수행했다. 결과 `ANSWERED`, 2만원, `neo4j_keyword`·`neo4j_vector`·`neo4j_rrf`, PDF 페이지 3, Evidence 002740·002742·002745 및 기타 해당 혜택 Evidence가 확인됐고 Streamlit 예외/오류는 0건이었다. 앱 시작 단독 테스트 및 제출·Evidence·연결 오류 케이스 AppTest도 통과했다.
- `neo4j_validation.cypher`/live Neo4j 신규 데이터 계약 12개 통합 테스트가 통과했다. 테스트는 Neo4j READ query를 사용했고 그래프·PostgreSQL 원장을 쓰지 않았다. TERMS 적용 범위·규칙 조건, 다중 카드 소유 관계, Evidence 연결, 1홉/2홉, 답변 검증을 신규 그래프 자료로 확인했다.
- 현재 실제 비교 답변은 선택 혜택 4개를 모두 포함하고, 지급 방식의 미확정 정보를 별도 경고로 남긴다. 평가셋에서 기존 추출 원문 상태 경고, 미확정 구간 금액 방지 등 검증 경고가 정상 발생한 것은 테스트 실패가 아니다.

### 변경 파일 및 검증 명령

- 변경 소스: `card_graphrag.py`, `neo4j_search.py`, `neo4j_hybrid_search.py`, `graph_questions.cypher`, `streamlit_app.py`, `verify_view.py`, `README.md`.
- 변경 테스트: `test_card_graphrag.py`, `test_neo4j_batch_queries.py`, `test_neo4j_origin_search.py`.
- 실제 이력 갱신 파일: `src/card_benefit/docs/issue_analysis/20261106_graphrag_integrity_work_log.md`.
- 문법 검사: `python -m compileall -q src/card_benefit/payment_card/db_pipeline_origin_search src/card_benefit/payment_card/tests` 통과.
- 자동 테스트: 관련 pytest 묶음 226 passed, 12 live tests deselected; live Neo4j unittest 12 passed. StreamlitTests 전체는 이전 실행에서 16 passed, 이후 해당 발견 실패 3건을 수정해 개별 재검증 3 passed; 최종 관련 pytest 묶음에 포함되어 226 passed에 반영됐다.
- Streamlit 실질 경로: `APP_DB_LOG_ENABLED=false python .tmp_live_ui.py` 통과. 실제 pipeline 질문 측정: `python .tmp_e2e_core.py`; 비교: `python .tmp_e2e_compare.py`. 이 임시 실행 파일들은 커밋 대상이 아니다.
- PostgreSQL 원장, app_log 행, Neo4j 데이터·인덱스는 수정/재적재하지 않았다. Git push 전 최종 테스트 후 파일 목록·diff·민감정보 검사를 수행한다.

### Commit 및 Push 결과

- 코드 및 테스트 변경 commit: `ef72bae3e9b0ba04f91f5f9f7e0456cc9f916252` (`fix: align GraphRAG queries with rebuilt Neo4j schema and optimize retrieval`).
- 푸시 전 `origin/main` 비교: 본 브랜치 1 commit 앞서, 뒤처짐 0; 충돌 없음.
- `git push origin main`: 성공 (`9ecbbe8..ef72bae`, `main -> main`).
- 스테이지된 11개 파일에서 비밀번호/토큰 형태 문자열 검사 매칭 없음; 임시 파일 및 인증 파일 미포함.


## Partial checkpoint before N-only cleanup (2026-11-07)

The prior task is intentionally recorded as partially complete; the worktree was preserved.

- Full payment_card suite at checkpoint: 594 passed, 18 skipped, 99 subtests passed.
- Read-only Neo4j integration at checkpoint: 9 passed; remaining selection was deselected.
- Three Streamlit AppTest questions returned without exceptions.
- POINT II 600,000-won spend question and the telco/subscription comparison were ANSWERED.
- ONE PICK/STYLE stayed PARTIAL because source evidence did not clearly preserve the tier-to-benefit mapping.
- Remaining work was removal of A/B/C-only runtime code, N-mode regression, and source mapping follow-up for ONE PICK/STYLE.

## N-only runtime cleanup and resumed validation (2026-11-07)

The work remains in progress; the earlier checkpoint is preserved above.

### A/B/C removal
- Removed the A/B/C PostgreSQL candidate service `benefit_search_service.py` and its A/B/C comparison evaluator `search_eval.py`.
- Extracted the N-shared search result types, tokenization, fetch size and RRF constant into `search_contract.py`; retained the N keyword/vector/RRF implementation in `neo4j_hybrid_search.py`. The tokenization particle and stopword rules were checked against the prior implementation.
- `streamlit_app.get_pipeline()` now creates one Neo4j hybrid pipeline, and same-question reuse no longer keys on a search mode. Search UI had no mode picker already. App log persistence remains in place.
- Removed `execution_log.request_pipeline`, the A/B/C factory and CardGraphRAG A/B/C catalog/detail branches, `pg:` detail fallback, and PostgreSQL source callback for exclusions. Neo4j search and PDF Evidence are the sole retrieval sources; PostgreSQL remains used by app_log persistence and unrelated ingestion/ledger code.
- Kept `interpret -> retrieve -> answer -> finish`, keyword/vector/RRF candidate search, topic supplementation, Neo4j batch detail and Evidence lookup, TERMS query, validation, error handling and app_log fields. Runtime always passes N mode.
- Replaced only A/B/C-specific unit tests with N-contract coverage; retained common-benefit ledger comparison tests and shared search-term tests.

### Verification
- `python -m py_compile` passed for changed runtime/search/test modules. `git diff --check` passed.
- Full `src/card_benefit/payment_card/tests`: 571 passed, 18 skipped, 99 subtests passed (36.07s). This includes AppTest coverage; no external LLM or embedding API was called.
- Live Neo4j read-only `LiveAccuracyTests`: 9 passed, 170 deselected (14.08s). The integration fixture uses live Neo4j keyword ranking with embeddings disabled and mock LLM output; vector behavior is covered by unit tests. No graph or PostgreSQL data was written.
- Earlier AppTest replays remain part of the checkpoint: all three questions returned without UI exceptions; POINT II and telco/subscription were ANSWERED, while ONE PICK/STYLE remains PARTIAL because source evidence does not preserve the tier-to-benefit mapping clearly enough. No real LLM AppTest replay was repeated to avoid paid calls.

### Remaining work
- Resolve the ONE PICK/STYLE source/data mapping gap; do not promote it from PARTIAL without stronger source evidence. This likely requires fixing extraction/graph source data and is outside the current no-data-write restriction.
- Do not access or stop localhost:8501. No PostgreSQL or Neo4j writes, commit or push were performed.

### Additional verification after N-only cleanup

- Removed obsolete A/B/C and `pg:` descriptions from `neo4j_search.py`.
- Python compilation and `git diff --check` passed.
- Neo4j batch query regression: 12 passed (2.25s).
- No external LLM was called in this verification.

## Audit of remaining A/B/C runtime references (2026-11-07)

- Re-scanned Python runtime and tests. The deleted `BenefitSearchService`, `search_eval`, `request_pipeline`, `create_benefit_search`, `SEARCH_MODE` setting, and A/B/C branches are absent from the N user-question path.
- Removed two obsolete search-wiring tests from `src/common/tests/test_read_only_manager.py`; they instantiated the deleted PostgreSQL candidate service and exercised `search_mode="C"` / `request_pipeline`.
- The only remaining `search_mode` string in relevant tests is a negative assertion that the Streamlit UI has no search-mode widget. It is not a runtime branch.
- Removed the `mode` input from `Neo4jBenefitSearch.search()` and `catalog_rows()`; the adapter now reports the fixed N label in `SearchOutcome`.
- `benefit_search_text.py`, `embedding_service.py`, and `common_benefit_service.py` remain because separate ledger, embedding, and ingestion workflows use them. They are not alternate question-search modes.
- Updated `db_pipeline_origin_search/README.md` to describe the N-only path. Older handoff and design/wiki documents retain historical A/B/C references and are not imported or called at runtime.
- Post-removal verification: `PYTHONPATH=src/card_benefit;src pytest -q src/card_benefit/payment_card/tests src/common/tests/test_read_only_manager.py --basetemp .pytest_cache/nmode-final-check`: 581 passed, 18 skipped, 99 subtests passed (38.17s).
- The first invocation without `PYTHONPATH` failed collection for 14 modules because the package root was not configured. The rerun with the package paths succeeded; Windows emitted a temporary-directory cleanup permission warning after the failed invocation.
- Actual Neo4j read-only `LiveAccuracyTests`: 9 passed, 170 deselected (14.73s) after the N-only adapter signature was simplified. No graph or PostgreSQL data was written.

## Answer quality and ONE PICK transaction-tier safety (2026-11-07)

### Read-only source review

- Rechecked PostgreSQL `db_pipeline.card_product_item`, Neo4j `dp_card_product_item` and linked Evidence, and the official ONE PICK STYLE debit-card PDF. No PostgreSQL or Neo4j writes were made.
- The official PDF page 1 visually separates the rows: ONE PICK convenience/cafe is 3,000 KRW per transaction -> 100 KRW; STYLE shopping is 10,000 KRW -> 500 KRW. Each has a 5,000 KRW monthly cap; usage limits are 1 per day / 30 per month for ONE PICK and 1 per day / 10 per month for STYLE.
- The registered PostgreSQL/Neo4j items contradict that row separation: each item carries both payout tiers (3,000/100 and 10,000/500). Each item's Evidence links point to a shared quote containing both rows. The extraction staging note also records uncertainty about how the overlapping fixed cashbacks apply. No stored per-row key or source location resolves the mapping. Consequently code cannot safely produce the requested per-benefit payout pairing without changing source mapping or inventing a rule; both remain PARTIAL.
- The PDF visual is clear, but the current graph evidence projection does not preserve the row-to-benefit coordinates. Resolving this as ANSWERED requires repairing the extraction/ledger-to-Evidence mapping and reloading data, which was prohibited in this task.

### Code changes

- `card_graphrag.py`: added a generic detector for overlapping `TXN_AMT` payout rules scoped to a benefit and question, plus `transaction_tier_fallback()`. When such a question asks for per-transaction amounts, the final answer now withholds the unsupported benefit-specific payout pairs regardless of whether the Answer LLM guessed confidently. For questions that also ask for monthly caps, only Evidence-matched limit facts remain; otherwise only a concise mapping uncertainty is shown. The behavior does not hardcode a card, product ID, question, or expected amount.
- `card_graphrag.py`: added question-intent response-shape guidance. Limit questions get a direct 1-2 sentence instruction; comparisons ask for short benefit rows, no repeated opening/closing summary, and only applicable exclusions. Existing facts and validation remain in place.
- `streamlit_app.py`: developer UI is hidden unless `CARD_GRAPHRAG_ENABLE_DEVELOPER_UI=1`; developer verification, diagnostics, Evidence inspection, and logs remain available when enabled. In the normal UI, the PARTIAL notice now identifies that source mapping is unconfirmed and relevant open conditions are shown without internal state names. Non-PARTIAL answers no longer show unrelated unresolved notices.
- `test_card_graphrag.py`: added fallback and developer-UI gating tests and updated prompt/UI assertions.

### Actual AppTest / GraphRAG runs

All actual AppTest requests ran against the local Neo4j-backed N-mode path. `APP_DB_LOG_ENABLED=0` prevented `app_log` writes. The existing localhost:8501 server was not used or stopped. Timings below are AppTest request wall time; candidate time and LLM timings come from the same outcome. The initial full-run first output was lost to Windows cp949 console encoding after the app request completed; the run was repeated with UTF-8 output. The five final question results were captured, and the comparison was rerun after the compact-format prompt change.

| Question | Result | AppTest wall time | Candidate search | Interpret LLM | Answer LLM | Key outcome |
|---|---:|---:|---:|---:|---:|---|
| Telco + subscription comparison | ANSWERED | 16.67s on final compact-prompt rerun (initial 19.95s) | 1.13s final | 2.46s final | 7.89s final; 17,465 input / 1,061 output tokens | Both cards' eligible services, Simple thresholds/caps, DAILY 5% telecom and 50% subscriptions, and DAILY combined caps were present. Final output was shorter (output tokens 1,529 -> 1,061; Answer call 11.06s -> 7.89s). |
| POINT II, 600,000 KRW previous-month spend | ANSWERED | 5.74s | 0.61s | 1.35s | 2.06s; 5,254 input / 163 output tokens | Direct one-sentence answer: 20,000 KRW combined monthly point cap; Evidence IDs included 20261105_002745, 002740, 002742. |
| ONE PICK + STYLE comparison | PARTIAL | 15.13s after safe fallback (earlier 9.72s) | 2.15s final | 3.08s final | 5.32s; 5,626 input / 602 output tokens | Only verified 5,000 KRW monthly caps and daily/monthly usage limits are stated. Per-benefit payout pairs are withheld; Evidence links are 20261101_000034/035 and 000040/041. |
| ONE PICK convenience/cafe single question | PARTIAL | 7.48s after safe fallback | 0.51s | 2.05s | 3.18s; 4,218 input / 295 output tokens | No 3,000/100 or 10,000/500 pair is asserted for this benefit; answer says the mapping cannot be confirmed. |
| STYLE shopping single question | PARTIAL | 6.46s after safe fallback | 0.82s | 1.43s | 2.98s; 4,195 input / 284 output tokens | No payout pair is attributed to STYLE; answer says the mapping cannot be confirmed. |

- Wall time varies between repeated AppTest runs; these values include AppTest/UI overhead and are not pure Streamlit-server timings. No answer accuracy was traded for speed. The comparison still has a large Answer prompt (about 17.5k tokens) and remains the latency bottleneck.
- In the three final ONE PICK runs after the safety change, the comparison contains the two verified caps and clear mapping warning; the single-benefit answers contain only the mapping warning. This is intentionally PARTIAL rather than falsely presenting the PDF's row values as graph-verified facts.

### Verification

- `pytest -q src/card_benefit/payment_card/tests`: 576 passed, 18 skipped, 99 subtests passed (36.27s). This includes Streamlit AppTest coverage for the normal hidden-developer-UI path and explicit developer-mode path.
- Actual Neo4j read-only integration: `RUN_NEO4J_INTEGRATION=1 pytest -q src/card_benefit/payment_card/tests/test_neo4j_origin_search.py src/card_benefit/payment_card/tests/test_card_graphrag.py -k "LiveNeo4jTests or LiveAccuracyTests"`: 14 passed, 198 deselected (20.97s).
- After tightening fallback Evidence IDs to rows that contain a matching threshold/payout pair, targeted fallback/prompt tests passed: 8 passed, 176 deselected; `compileall` passed.
- An earlier full-suite run had two test expectation failures after the prompt wording and normal-view unresolved-item changes. The assertions were updated to the intentional wording/visibility policy; the final full-suite run passed.
- No commit, push, PostgreSQL write, Neo4j write, or use/termination of the existing 8501 process occurred.

### Remaining source-data work

- To return the expected 3,000/100 ONE PICK and 10,000/500 STYLE answers as ANSWERED, repair the extraction row-to-benefit/rule/Evidence links using page-1 row-level PDF coordinates, then reload the affected source/graph mapping under a separately authorized data-change task. Until then the current safe PARTIAL behavior is expected.
