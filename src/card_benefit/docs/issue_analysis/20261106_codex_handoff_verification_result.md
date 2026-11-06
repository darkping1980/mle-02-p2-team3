# Codex 인수인계 검증 결과 — GraphRAG 데이터 손실·답변 검증

- 확인일: 2026-11-06
- 저장소: `C:\myproject\workspace\mle-02-p2-team3`
- 작업 범위: 기존 구현 확인, 전체 회귀 실행, 읽기 전용 DB 검증, PostgreSQL 보정 dry-run 도구 및 테스트, 이슈 문서 작성
- 제한 준수: Commit/Push 없음, `streamlit_app.py`·`execution_log.py` 변경 없음, PostgreSQL 쓰기·DDL 없음, Neo4j 쓰기/재적재 없음, 유료 LLM 호출 없음

## 1. 인수인계 문서 검증 결과

우선 확인한 문서:

- `20261106_claude_to_codex_handoff.md`
- `20261106_tier_value_none_typeerror.md`
- `20261106_postgresql_neo4j_mapping_query_audit.md`
- `20261106_graphrag_data_loss_fix_plan.md`
- `20261106_graphrag_p0_p1_implementation_result.md`

P0·P1·P2 소스 구현은 현재 워크트리에 존재한다. P2 전체 결과는 handoff 본문에 `670 통과 / 11 실패 / 20 건너뜀`으로 기재되어 있으나, 정확한 `P2_REGRESSION_RESULT` 문자열/원본 로그는 없다. 문서에 기록된 실행 중 상태와 최종 결과 간 시점 차이도 확인했다. 아래 4절은 Codex가 현재 코드로 실행한 최신 결과다.

ONE PICK·STYLE 별도 QA 문서는 기존에 없었고, 이번에 [ONE PICK·STYLE 캐시백 구간 QA 이슈](20261106_onepick_style_cashback_tier_qa_issue.md)로 작성했다.

## 2. Git 변경 상태

작업 시작 시:

- 브랜치: `main`
- HEAD: `fcb2a5111dfad4eec17ec6431fd314f22bbeb451`
- Claude 구현과 문서·테스트가 미커밋 상태였다.
- 다른 실행 프로세스는 Streamlit 두 프로세스로 확인됐다. 테스트 프로세스는 시작 시 없었다.

기존 Claude 미커밋 파일은 유지했다. `streamlit_app.py`, `execution_log.py`는 수정하지 않았다. 이번 작업에서 추가한 파일:

- `payment_card/db_pipeline/limit_struct_backfill.py`
- `payment_card/tests/test_limit_struct_backfill.py`
- `docs/issue_analysis/20261106_onepick_style_cashback_tier_qa_issue.md`
- 본 문서

Commit/Push는 하지 않았다. 마지막 status의 추가 파일 외 기존 미커밋 항목은 11절을 참조한다.

## 3. P0·P1·P2 구현 확인

### P0 — NULL 지급값

`payment_card/db_pipeline_origin_search/card_graphrag.py`에서 확인했다.

- `tier_token()`은 숫자 값과 지원 단위가 있을 때만 토큰을 만들고, `None`은 미확정으로 돌려준다. `0`은 유효한 값이다.
- `rule_conflicts()`는 tier에 `payout_known`을 보존한다.
- `distorts_tier()` 등 지급값 비교는 미확정 payout을 비교 성공/실패 근거로 사용하지 않는다.
- 전월 실적 구간과 정상 수치 검증은 유지된다.
- 전용 테스트 `test_tier_null_payout.py` 14개 통과, Neo4j 통합 1개 건너뜀.

### P1 — 신규 등록 한도 구조 보존

- `extraction_service.py`가 `limits`, `rule_limits`를 검증하며 보존한다.
- `limit_tiers_from_extraction()`은 원문에 상한·한도·근거가 확인되는 명확한 구간만 생성한다.
- `product_benefit_service.py`는 원본 구조를 `item_data`에 넣고 위치 확인된 규칙 조건 근거를 `RULE/COND`로 연결한다.
- 기존 `rule_list`, `item_limit_txt` 의미를 바꾸거나 신규 테이블·컬럼을 추가하지 않는다.
- 전용 테스트 `test_limit_struct.py` 14개 통과.

### P2 — 적재·검증·답변 구간 한도 전달

1. `neo4j_dry_run.py`의 BENEFIT SELECT 및 source JSON 매핑에 `item_data`가 있다.
2. 원천 컬럼 완전성 검사는 `neo4j_validate.py`에서 독립적으로 수행한다.
3. PostgreSQL `item_data`와 Neo4j의 `source_json.item_data`는 독립 조회 후 비교한다.
4. `benefit_context()`는 답변에 필요한 `limit_tiers`만 추려 전달한다.
5. `distorts_limit_tier()`가 구간별 월 한도 혼동을 검사한다.
- 전용 테스트 `test_p2_limit_tiers.py` 17개 통과.

## 4. 전체 회귀 테스트 결과

최종 실행:

```text
pytest -q -p no:cacheprovider payment_card/tests payment_card/db_pipeline
682 passed, 2 failed, 20 skipped, 99 subtests passed in 34.21s
```

테스트 시 DB·Neo4j·LLM 환경 변수는 빈 값으로 설정했다. 실패 두 건:

1. `test_answer_text.py::test_unresolved_tier_cannot_be_decided_in_natural_text` — 예상 `validated_sentences`, 실제 `program_tier`.
2. `test_card_graphrag.py::StreamlitTests::test_example_only_fills_input` — AppTest에서 예시 선택이 질문 입력값을 채우지 않음.

두 실패 유형은 handoff 및 P0/P1 결과 문서에도 기존 실패로 기록된 유형과 일치한다. 다만 과거 원본 pytest 로그가 없어 이전 11개 실패 전체와 각 항목이 정확히 동일하다고 단정할 수 없다. 이번 실행에서 P2 전용 17개와 새 dry-run 테스트 3개는 모두 통과했다. P2 신규 실패를 확인하지 못했다. 20개 skip에는 실제 외부 DB 통합 테스트 등이 포함되어 있어 해당 기능을 이번 테스트 실행으로 확인한 것은 아니다.

## 5. Neo4j 현재 상태 및 불일치

`neo4j_validate`를 실제 PostgreSQL·Neo4j 양쪽에서 실행했다. 이 검증은 PostgreSQL SELECT와 Neo4j `READ_ACCESS` 트랜잭션만 사용한다.

| 항목 | PostgreSQL 예상 원천 | Neo4j 현재 |
|---|---:|---:|
| 노드 | 1,635 | 1,635 |
| 관계 | 2,702 | 2,702 |
| 노드 구조 차이 | — | 0 |
| 관계 구조/속성 차이 | — | 0 |
| 노드 속성 차이 | — | 34 |
| `item_data` 불일치 | — | 34 |
| 원천 컬럼 누락 | — | 0 |
| 범위 밖 노드/관계 | — | 0 / 0 |

34건은 PG 원천 `card_product_item.item_data`와 그래프 `source_json.item_data`의 미반영 차이다. 현재 PG 스냅샷과 Neo4j 건수는 일치하며 `ok=false`는 이 속성 차이 때문이다. 손실 복구를 위한 PG 업데이트와 Neo4j 재적재는 실행하지 않았다. handoff의 `1,643 노드 / 2,718 관계`는 보정 이후 예상치이며 검증된 현재 수치가 아니다.

## 6. PostgreSQL 보정 미리보기

새 도구는 [limit_struct_backfill.py](../../payment_card/db_pipeline/limit_struct_backfill.py)이며 다음과 같이 실행한다.

```powershell
cd src/card_benefit
..\..\.venv\Scripts\python.exe -m payment_card.db_pipeline.limit_struct_backfill --dry-run
```

도구에 `--dry-run` 이외의 쓰기 모드가 없고, PostgreSQL 세션을 읽기 전용으로 설정·확인한다. 테스트는 DB를 연결하지 않고 Mock으로 실행한다.

실제 dry-run 결과:

- 22/`20261105_000099`, 23/`20261105_000100`, 20/`20261105_000092`: 대상 BENEFIT 행 모두 발견, 현재 `item_data={}`.
- 세 행 모두 예상 추출 원본과 live `rule_list`·이름·유형 일치.
- 미리보기 `item_data`는 세 행 모두 변경 예정이며, 충돌하는 기존 키는 0개.
- RULE/COND 연결 예정 8건, 기존 중복 0건, 추가 예상 8건.
- 카드 22는 `r1 → 10,000원`, `r2 → 15,000원` 구간 구조 복원.
- 카드 23은 월 한도와 규칙 연결만 보존. 원문에 없는 구간 상한은 만들지 않고 `limit_tiers`를 생성하지 않음. B2 상한안은 승인 전 보류.
- 카드 20은 10만원 기본 + 10만원 추가의 누적 구조만 보존. 배타 구간이나 20만원 합계로 변환하지 않음.

dry-run 출력에는 변경 전 `item_data`, `item_limit_txt`, 규칙 지문, 기존 조건 근거 연결, 검색 텍스트·임베딩 해시를 포함하는 `backup_preimage`가 있다. 이 payload는 화면 출력용이며 영구 백업이 아니다. 후속 사전 검증에서 `src/card_benefit/docs/schema_cleanup/tools/backup_db_pipeline.py`를 찾아 현재 스키마에서 실행했고, 2026-11-06 백업의 행 단위 대조가 `VERIFY OK`로 완료된 것을 확인했다. 세부 경로 및 범위는 `20261106_db_correction_preflight_result.md`에 기록했다. 실제 수정 전에는 이 백업을 보존하고 선택적 롤백 절차를 별도 승인받아야 한다.

예상 변경량은 `item_data` UPDATE 3행, RULE/COND 링크 INSERT 최대 8건이다. **이번 작업에서는 어떤 PostgreSQL 쓰기도 실행하지 않았다.**

## 7. ONE PICK·STYLE 별도 이슈

읽기 전용 PostgreSQL에서 하나카드 상품설명서(`card_doc_id=20261101_000002`, p.1, chunk `20261101_000012`)와 관련 규칙을 확인했다.

- ONE PICK·STYLE 모두 3,000원 이상 100원, 10,000원 이상 500원으로 저장되어 있다.
- STYLE은 일 1회·월 10회, ONE PICK은 일 1회·월 30회, 각 월 한도 5,000원으로 청크에 기록되어 있다.
- 두 결제 조건의 상한이 `NULL`이라 10,000원 결제에서 두 규칙이 동시에 적용된다.
- `fixed_conclusion()` → `tier_answer()`의 프로그램 문구이며 기존 테스트도 “미확정” 동작을 기대한다.
- 원문에 상위 구간 우선 원칙이 명시되었는지는 확인되지 않았다. PDF 파일의 시각적 표는 직접 열어 보지 않았다.

분석·대안·경계 테스트는 [별도 QA 문서](20261106_onepick_style_cashback_tier_qa_issue.md)에 기록했다. 수정은 하지 않았다.

## 8. DAILY 179 검색 누락

역사적 매핑 감사 문서에는 키워드 검색 상위 5개에 `42/179 고정소비 영역 5%`가 세 번째로 있었지만, 당시 `app_log 198`의 상세 조회 키에서는 빠졌다고 기록돼 있다. 현재 `app_log` 상태는 여기서 재조회하지 않았으므로 이는 감사 문서에 보존된 과거 기록이다.

현재 코드에서 진단 공백을 확인했다.

- `Neo4jBenefitSearch.search()`의 `last_trace`는 식별 카드·후보 수·RRF 점수·자기 카드 여부만 보존한다. 반환 `hits`에는 key·채널 정보가 있지만 기존 `HYBRID` 로그는 후보 개수만 기록한다.
- `CardGraphRAG.interpret()`은 선택 혜택 이름과 제외/필터 결과를 로그에 쓰지만, 선택된 실제 key와 전체 후보→선택 관계를 구조화해 남기지 않는다.
- `retrieve()`는 실제 상세 조회 실패 key를 내부 `missing`에 모으지만 `RETRIEVE DONE` 로그에는 실패 개수만 기록한다.
- 따라서 기존 정보만으로 후보 검색 누락, 해석 단계 미선택, 상세 조회 실패 중 어느 것인지 확정할 수 없다.

후속 진단은 금지 파일을 변경하지 않고 별도 승인 뒤 다음을 기록하는 방향이 적절하다.

1. 후보 단계: request ID, benefit key·카드 ID, channel별 순위/점수, 적용 카드 판정.
2. interpret 단계: 후보 전체 key와 선택된 key, 제외·필터 key 및 코드상 사유.
3. retrieve 단계: 요청한 key와 반환된 key, `missing` key, 실제 쿼리 엔진.

읽기 전용 재현 테스트는 (a) keyword-only 검색에서 179가 후보에 있는지, (b) Mock interpret가 179를 선택/제외할 때 조회 key가 달라지는지, (c) 선택된 179의 `get_detail()`이 정상 응답하는지 분리해 확인한다. Vector embedding과 LLM은 호출하지 않는다. 기존 감사에서 179가 키워드 결과에 있었다는 사실만으로 벡터 순위·실제 interpret 선택·그래프 상세 조회 결함을 추정하지 않는다.

## 9. 남은 작업과 사용자 승인 항목

- 23/100의 B2 상한 추론 및 공유 한도 범위 결론.
- 20/092 한도 atom key 및 등록 `rule_list`와의 추가 대조는 dry-run에서 fixture/live 지문 일치까지 확인했으나, 보정 실행 전 최종 리뷰 필요.
- 내구성 있는 사전 백업과 복구 가능한 롤백 절차 확인.
- PostgreSQL 3행 수정 및 최대 8개 근거 연결 추가는 별도 승인이 필요하며 아직 실행되지 않음.
- Neo4j 재적재는 별도 승인 후 단계적으로 계획·검증해야 하며 아직 실행되지 않음.
- ONE PICK·STYLE 구간 선택 정책은 공식 PDF 원본 시각 대조 및 제품 정책 결정이 필요.
- DAILY 179에 필요한 로그는 `streamlit_app.py`, `execution_log.py` 변경을 포함할 수 있어 별도 범위 승인 전 구현하지 않음.

## 10. 후속 작업 순서

1. ONE PICK·STYLE PDF 원본 표와 주석을 사람 검토로 확인하고, 명시적 우선순위 근거가 있는지 결정한다.
2. 23/100의 공유 한도 적용 범위와 B2안 승인 여부를 결정한다.
3. dry-run JSON을 검토하고, 독립적인 DB 백업 및 롤백 리허설을 준비한다.
4. 승인 후에만 PostgreSQL 보정을 트랜잭션으로 실행하고 3행·8링크 및 비대상 지문을 검증한다.
5. 별도 승인 후 Neo4j 적재·검증을 수행하고 `item_data_mismatch=0`을 확인한다.
6. DAILY 179은 검색→선택→상세조회 로그·Mock 테스트를 분리해 원인을 특정한다.

## 11. 마지막 Git 상태

Commit/Push 전, 변경 사항은 모두 미커밋이다.

기존 Claude 변경(보존):

- `payment_card/db_pipeline/common_benefit_repository.sql`
- `payment_card/db_pipeline/extraction_service.py`
- `payment_card/db_pipeline/neo4j_dry_run.py`
- `payment_card/db_pipeline/neo4j_validate.py`
- `payment_card/db_pipeline/neo4j_validation.cypher`
- `payment_card/db_pipeline/neo4j_validation.sql`
- `payment_card/db_pipeline/product_benefit_service.py`
- `payment_card/db_pipeline_origin_search/card_graphrag.py`
- handoff, fix plan, P0/P1 결과 문서
- limit struct·P2 fixtures 및 테스트

이번 작업 추가 파일은 2절에 적었다. `.env`, 운영 데이터, DB 스키마, Streamlit 앱, 실행 로그 파일은 변경하지 않았다. Commit/Push는 사용자 요청의 금지 조건을 따라 하지 않았다.
