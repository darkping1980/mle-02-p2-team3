# Codex → Claude Code 인수인계

기준: 2026-11-01, 개발 검증 모드 구현 완료, A10-3 재동기화 상태 유지(노드 108, 관계 189, PostgreSQL 차이 0), P4·P5 보류. 프로젝트 루트 `D:\Bootcamp\vscode\workspace\mle-02-p2-team3`. 카드 발급 전 혜택 검색·비교 GraphRAG. PostgreSQL V6에서 원문·추출·검증을 관리하고 Neo4j로 DRAFT를 전환했다. 현재 목표는 `db_pipeline_origin_search` 로컬 Streamlit Neo4j 조회 MVP이며 LLM·챗봇은 범위 밖이다.

## Neo4j DF/PF 전환 (2026-11-01, 최신)

- 설계와 완료 기준: `db_pipeline/NEO4J_DF_PF_DESIGN.md`.
- 2단계 완료: 코드가 `df_` 레이블과 `df_one_pick_style`만 쓴다.
- 4단계 완료: Neo4j에 DF 108/189 적재, Named Cypher 7개 결과 동일.
- 3단계 완료: A8 백업은 `D:\Bootcamp\backups\card_benefit\neo4j\20261101_160805`. 실제 서버 복원은 미검증이다.
- 5단계 완료: Streamlit과 실제 DF 조회를 Mock LLM으로 검증했다. 설계 문서 17절 참고.
- 6·7단계 완료: A8 노드 108, 관계 189, `a8_test_key`를 제거했다. Neo4j는 DF 108/189 단독이고 PF 0이다. `neo4j_validate` `ok: true`, 카드 테스트 157건 통과, 화면 동일. 설계 문서 18절 참고.
- 남은 미검증: 실제 LLM 답변 품질, DBeaver GUI 직접 실행, A8 백업의 실제 서버 복원. 2단계 수정 전 코드 백업은 `D:\Bootcamp\backups\card_benefit\source\20261101_155114`에 있다.

## 공통 Neo4j 연결·쿼리 로그 설정 (2026-11-01)

- `src/common/neo4j_connection.py`(TLS·드라이버 생성)와 `src/common/query_log_config.py`(`.env` 로딩, 스위치, handler)로 옮겼다. 레시피의 기존 import 경로는 유지했다.
- 카드는 `recipe_recommender`, `src.common`, `sys.path` 변경을 쓰지 않는다. `common`, `card_benefit`은 `.venv` 편집 설치로 찾는다. 앱과 테스트는 `card_benefit...` 경로를 쓴다.
- 레시피: `RECIPE_QUERY_LOG` → `DB_QUERY_LOG` → 소스 기본값. 카드: `DB_QUERY_LOG` → 로컬 개발이면 켬. 상세 레벨은 `CARD_SEARCH_LOG_LEVEL`.
- ON 뒤 OFF가 되면 공통 함수가 붙인 handler를 떼고 logger를 기본값으로 되돌린다. 붙인 적이 없으면 아무것도 바꾸지 않아 CLI가 정한 레벨을 유지한다.
- handler 표시 속성은 `recipe_query_log`에서 `common_query_log`로 바뀌었다. handler를 공유하므로 레시피와 카드를 한 프로세스에서 함께 실행하면 한쪽의 OFF가 다른 쪽 출력도 끈다. 지금은 앱이 별도 프로세스라 해당하지 않는다.

## 로그 기본값 (2026-11-01)

`CARD_SEARCH_LOG_LEVEL` 기본값을 `DEBUG`로 바꿨다(`card_graphrag.DEFAULT_LOG_LEVEL`). 개발 단계 설정이며 운영 전 `INFO`로 되돌려야 한다. 프롬프트 전문도 함께 출력된다. `DB_QUERY_LOG=0`이면 출력되지 않는다.

## DBeaver 42001 원인과 공통 렌더링 연결 (2026-11-01)

- **원인:** `$ns`를 값 없이 실행한 것이다. 문법 오류가 아니다. DBeaver와 같은 `neo4j-jdbc-full-bundle-6.15.1.jar`로 같은 메시지를 재현했다. 서버의 하위 원인은 `42N81 missing request parameter`다.
- **코드 원인:** `CARD_LOG`가 `separate` 모드라 터미널에 원문이 나왔다. 레시피는 `combined` + `render_cypher_log`다.
- **수정:** `neo4j_search.py`에서 `combined`로 바꾸고 `render_combined`로 공통 `render_cypher_log`를 연결했다. 실행은 계속 바인딩이다. `src/common`, `src/recipe` 변경 없음.
- **미확인:** DBeaver UI 자체. JDBC 드라이버로만 확인했다.
- **선택 사항:** `Neo4jSearch._query`를 `select_list`로 바꾸는 안은 `READ_ACCESS`와 로그 형식이 달라져 승인 대상이다.

## 개발 검증 모드 (2026-11-01)

설명은 `README.md`의 "개발 검증 모드"를 따른다.

- 신규: `verify_view.py`. 수정: `neo4j_search.py`(`DETAIL_LOG`, `flatten_record`, `statement_plan`, `detail_plan`), `card_graphrag.py`(`verify_*`, `merge_state`, `next_step`, `plan_key`), `streamlit_app.py`(실행 모드 선택).
- 그래프는 그대로다. 같은 노드와 라우팅 함수를 직접 호출하고 체크포인트를 쓰지 않는다.
- 공통 재사용: `render_cypher_inline`(복사용 Cypher), `log_query`, `log_result_data`.
- 검증: Mock LLM·실제 Neo4j. 화면 Cypher를 드라이버로 그대로 실행해 앱 조회와 건수를 대조했다. Neo4j Browser UI 자체에서는 실행하지 않았다. 유료 호출 없음.

## A10-3 Cypher 정리와 재동기화 (2026-11-01)

- **신규:** `graph_questions.cypher`(검색 7개), `../db_pipeline/neo4j_validation.cypher`, `neo4j_validation.sql`, `neo4j_validate.py`, `test_neo4j_validate.py`.
- **읽기:** 공통 `Neo4jDbSession(mapper_root=...).mappers`를 재사용한다. 새 로더는 없다.
- **실행:** `Neo4jSearch._query`를 유지한다. `select_list`는 `READ_ACCESS`와 재시도가 없고 로그가 달라진다.
- **`neo4j_load.cypher`:** 만들지 않았다. 라벨·관계 유형이 동적이라 `MERGE`는 Python에 둔다.
- **의미 변경:** `benefit_evidence`에 Rule 경로를 추가했다. 나머지 6개는 문자열까지 같다.
- **기존 테스트 수정:** `test_db_pipeline.py`, `test_payment_card.py`의 mapper 목록에 `neo4j_validation`을 추가했다. `.sql`을 추가하면 namespace가 늘기 때문이다.
- **데이터:** 조건 근거 8건 추가, 연결 62건. 별도 A10-3 지시 문서를 받지 못해 A10-2 제안 8건을 승인 범위로 해석했다.
- **재동기화:** `MERGE`로 관계 168→189, 삭제 0. `neo4j_validate` 결과 키·JSON·끝점 차이 0, 조건 15·근거 62 SQL·Cypher 일치, 고아 0.
- **회귀:** 기준선 대비 혜택 4, 규칙 6, 한도, 대상, AND/OR/NOT 불변. 값 변화는 P1·P2 두 항목뿐이다. 고유 근거는 놀이공원에 048만 추가됐다.
- **시험:** 카드 235 통과, 11 건너뜀. 실제 Neo4j 포함 95 통과. Mock LLM·실제 Neo4j·Edge 화면 정상. recipe 묶음 실패 20건은 기존과 같다.
- **백업:** `src/data/backup/a10_3_pre_condition_links_20261101/`, `a10_3_pre_neo4j_resync_20261101/`.
- **다음:** P4·P5, 업무 미확정 항목은 상품 약관 또는 카드사 확인이 필요하다.

## A10-2 원문 검증과 최소 보정 (2026-11-01)

전체 내용은 `../db_pipeline/A10_1_DATA_CORRECTION_PLAN.md` 앞부분에 있다.

- **원문:** PDF 2쪽 추출 텍스트가 PostgreSQL과 Neo4j에 잘림 없이 있다. PDF 파일 자체는 DB에 없고 상품 약관 전체는 없다. Neo4j 전문은 Page·Chunk의 `source_json` 안에 있고 추가 저장은 하지 않는다.
- **근거:** 31건 모두 인용 일치, 표 행·문단이 소유 혜택과 일치한다. 오류는 이미 고친 037뿐이다.
- **반영:** P1 `amusement_first_month` 유형을 `BNFT_EXCL`로(진리표 16/16 동일), P2 `transit_spend` 원문을 근거 048 인용으로, 조건 근거 2건, P3 규칙 근거 11건. 연결 41→54, 근거 31 유지.
- **변환기:** `neo4j_dry_run.py`에 RULE 분기, `neo4j_load_draft.py`에 건수 상수(108·181). 새 라벨·관계 유형 없음. 테스트 13개 통과.
- **백업:** `src/data/backup/a10_2_pre_p1_p3_20261101/`(CSV, 변경 기록, 복구 SQL).
- **현재 불일치:** Neo4j가 PostgreSQL보다 뒤처져 있다. `source_json`이 다른 노드 9개, 없는 관계 13개. 재적재 승인 전까지 의도된 상태다.
- **재적재:** 키 집합이 같아 삭제 없이 `neo4j_load_draft --apply --confirm APPROVED_ONE_PICK_STYLE_A8`로 끝난다. 미승인.
- **보류:** P4(국내 일시불이 자격 조건인지 산정 기준인지 불명확), P5(시작일은 `source_doc_list` 키, 집계는 `UNCONFIRMED` 코드 권장). `approved_at` 방식은 철회.
- 시험: 카드 테스트 223 통과, 11 건너뜀. 실제 Neo4j 포함 91 통과.

## A10-1 데이터 보정 (2026-11-01)

계획과 SQL 전체는 `../db_pipeline/A10_1_DATA_CORRECTION_PLAN.md`에 있다.

- **실행:** `card_source_evidence.20261101_000037`의 위치를 1622~1626에서 2270~2274로 정정했다. 좌표·구분선·표 이미지로 ONE PICK 행임을 확인했다. 1행 2컬럼만 변경됐다.
- **백업:** `src/data/backup/a10_1_pre_evidence037_20261101/`에 근거 31행, 연결 41행, 해시, 복구 SQL이 있다.
- **검증:** 인용 31/31 일치, 게이트 `evidence_not_approved` 31건 그대로, 메모리 변환 108·168, 변환기·로더 테스트 8개 통과.
- **현재 불일치:** Neo4j의 근거 037만 정정 전 위치다. 노드·관계 키 집합은 같고 `source_json`이 다른 노드는 이 1건뿐이다. 재적재 전까지 의도된 상태이며 Neo4j를 직접 고치지 않는다.
- **보류:** P1(놀이공원 유형), P2(대중교통 원문), P3(규칙 근거), P4(국내 일시불), P5(가정값), 업무 미확정 항목 전체.
- **DDL:** 불필요. P5를 채택하면 공통코드 1행과 풀 9행 변경, 변환기 수정이 필요하다.
- **재적재:** 키가 같으면 기존 로더 재실행으로 삭제 없이 반영된다. P4처럼 노드가 늘면 로더가 거부하므로 이름공간 교체가 필요하다. RULE 연결은 현 변환기가 거부한다. 재적재는 미승인이다.

## A10 데이터 구조 분석 (2026-11-01)

읽기 전용으로 분석했고 데이터·DDL·공통코드는 바꾸지 않았다. 전체 내용은 `../db_pipeline/A10_V6_NEO4J_STRUCTURE_ANALYSIS.md`에 있다.

- 혜택 4건의 조건 atom과 근거 연결은 SQL·Cypher 불일치 0이다. 문제는 PostgreSQL 값의 의미이고 Neo4j는 이를 그대로 옮겼다.
- 필수 DDL 변경은 찾지 못했다. RULE 근거, `TXN_AMT`, `BNFT_EXCL` 모두 현행 V6에 있다.
- 확인된 데이터 결함: 근거 `...037` 위치 오류, `amusement_first_month` 유형 부정확, `transit_spend` 원문이 조립된 값, 공통 atom 중복, "국내 일시불" 조건 미구조화.
- 구조 문제: `LIMIT_AGG`에 미확정 값이 없고, 시험 가정 표시가 원본이 아니라 `neo4j_dry_run.py`에 하드코딩돼 있으며, 규칙 겹침 게이트가 없다.
- 원문으로 확정 불가: 100·500원 적용 방식, 집계 단위, 최초 발급 월 기준, 1인 1매 범위. 상품 약관 또는 카드사 확인이 필요하다.
- 보정 순서는 문서 7절을 따른다. 다음 작업은 업무 확인과 표현 규약 결정이며, 데이터 변경은 변경안 승인 후 진행한다.

**A9-4 정정:** 아래 "데이터 모델 추가 검토 항목" 6번의 "구분 코드" 제안은 틀렸다. `cond_basis_cd`가 `TXN_AMT`와 `PREV_MONTH_SPEND`를 이미 구분한다. 필요한 것은 Neo4j `basis` 속성 승격이다.

## A9 최종 실호출 검증 (2026-11-01)

**A9를 종료한다. 프로그램은 개발용 GraphRAG MVP로 유지한다.** 승인된 2개 질문을 임시 서버에서 headless Edge로 한 번씩 제출했다. LLM 4회, 실패·재호출·모델 전환 없음, 코드 수정 없음.

| 질문 | Interpret | 조회 | 평가 | 입력/출력 | 추정 비용 |
|---|---|---|---|---|---|
| 1만원 이상 결제하면 캐시백은 얼마인가? | DETAIL, 001·002, ambiguity 있음 | 규칙 4, 조건 10, 한도 6, 근거 18 | 통과, 경미한 표현 잔존 | 6,467 / 445 | $0.000869 |
| ONE PICK과 STYLE 혜택의 차이는? | COMPARE, 001·002 | 규칙 4, 조건 10, 한도 6, 근거 18 | 통과, 구간 문장 이동 | 6,441 / 713 | $0.001001 |

합계는 입력 12,908, 출력 1,158, 추정 $0.001870이다. A9 전체 실호출은 14회, 추정 $0.004956이며 청구 내역과 대조하지 않았다.

- Q5 결론: "혜택별로 100원 또는 500원 구간이 있으나, 어느 금액이 적용되는지는 미확정". LLM이 대중교통을 스스로 고르지 않아 `filter_by_payment`는 동작하지 않았다. 혜택별 문장의 `benefit_id`와 인용 034·040은 정확하다.
- Q5 잔여: 혜택별 문장에 "500원 구간이 적용되며"가 남았다. 100원 구간도 함께 써서 검증기를 통과했다.
- Q3: 4문장의 `benefit_id`가 모두 정확하고 월 30회·10회를 구분했다. 인용도 혜택별로 분리됐다.
- Q3 잔여: 금액 구간과 미확정을 함께 쓴 2문장이 `STATUS_SENTENCE`에 걸려 `uncertain`으로 옮겨진 뒤 중복 주제로 생략됐다. 구간 값은 결론에만 남아 근거 034·040이 화면 인용에 나오지 않는다.
- 로그는 서버 stderr 파일로 받아 `REQUEST → CYPHER → INTERPRET → RETRIEVE → CYPHER → ANSWER → FINAL`을 확인했다. VS Code 터미널 자체는 사용자가 확인해야 한다.
- 잔여 2건은 정확성 판단을 뒤집지 않으므로 수정하지 않고 기록만 한다.

## A9-4 검색·답변 정확성 개선 (2026-11-01)

**A9-4 작업 당시에는 실제 LLM을 호출하지 않았다. 실제 검증 결과는 위 "A9 최종 실호출 검증"에 있다.** 프로그램 검증기는 A9-3 실제 응답을 Mock으로 재생해 확인했다. 동작 설명은 `README.md`의 "검색 대상과 답변 검증"을 기준으로 한다.

- 수정: `card_graphrag.py`, `neo4j_search.py`(`CATALOG_QUERY`에 `payment_min_amounts`), `streamlit_app.py`, `../tests/test_card_graphrag.py`, `README.md`, 이 문서. 스키마·데이터 변경 없음.
- 출력 스키마 변경: `Interpretation.ambiguity`, `CardAnswer.conclusion`, `AnswerPoint.benefit_id`. 입력 문맥에 `rule_selection_unresolved`, `payment_amount`, `evidence.benefit_ids` 추가. Q2 기준 문맥이 5,600자에서 6,125자로 늘었다.
- 재생 결과: Q5는 대중교통 제외, 결론을 "확정할 수 없습니다"로 교체, 500원 단정 문장 제거, ONE PICK 034와 STYLE 040으로 분리. Q3은 사실 3문장 유지, 상태 문장 분리, 20회 차이는 `CALCULATED`. Q2 유예 2문장과 Q4는 경고 없이 유지.

검증 수준:

| 수준 | 결과 |
|---|---|
| Mock LLM + Mock Neo4j | 81개 통과 |
| Mock LLM + 실제 Neo4j 읽기 | 10개 통과 (A9-3 Q2~Q5 응답 재생 포함) |
| 재생 Mock + 실제 Neo4j + Edge | Q2, Q3, Q5, 모호한 질문 화면 정상, 콘솔 오류 0건 |
| 실제 gpt-6-luna | 이후 2개 질문 실행, 위 절 참조 |

회귀: `payment_card/tests` 전체는 `PYTHONPATH=src/card_benefit`로 210 통과, 11 건너뜀. `run_offline_tests.py`의 recipe 묶음은 A9-2와 같은 실패 20건이고 `src/recipe`, `src/common`은 수정하지 않았다. Mock 재생 스크립트는 세션 임시 폴더에 있었고 저장소에 넣지 않았다.

근거 검증 가능 범위: 근거 ID 존재, 혜택 범위, 상태 문장 분리, 값·단위·기간의 인용 원문 일치. 불가능한 범위: 규칙별 근거 대응, 문장 의미와 근거의 일치, 값 없는 문장의 내용, 표 셀의 의미. 이 불가능 범위는 임의로 보완하지 않고 `NOT_CHECKED` 또는 `STRUCTURED_ONLY`로 표시한다.

알려진 한계:

1. 검증기는 정규식 기반이다. 상태·적용 방식 표현을 다르게 쓰면 놓칠 수 있고, 정상 문장이 걸릴 수도 있다.
2. 결제 금액 필터는 규칙 단위 `SPEND_REQ`가 있는지로만 판단한다. 다른 금액 유형의 혜택에는 일반화되어 있지 않다.
3. `UNRESOLVED_ATOMS`와 미확정 주제 목록은 현재 ONE PICK STYLE 데이터 기준이다.
4. 실제 LLM이 `benefit_id`를 비워 쓰면 혜택 범위 검사는 동작하지 않고 문장은 공통으로 표시된다. Q3 재생은 이 경우이며 혜택별 묶음은 Mock 단위 테스트로만 확인했다.

데이터 모델 추가 검토 항목(이번에 변경하지 않음):

1. 규칙 단위 근거 연결. `ev_subject_cd=RULE`과 `rule_key`를 채워 100원·500원 규칙을 각각 추적한다.
2. 금액 구간 혜택의 `rule_select_cd` 확정. 원문 검토로 최고 구간 택일인지 합산인지 정한다.
3. 조건 단위 근거 연결. 현재 COND 연결은 `spend_exclusions`뿐이다.
4. 근거 값의 구조화. 표 원문의 의미가 값 비교만으로 확정되지 않는다.
5. `transit_spend` 원문 정제와 `amusement_first_month` 유형 재검토.
6. 결제 건당 기준과 전월 실적 기준의 구분 코드. 현재 둘 다 `SPEND_REQ`이고 소유자(규칙·혜택)로만 구분된다.

## A9-3 실제 gpt-6-luna 검증 (2026-11-01)

아래 "프로그램·프롬프트 문제"와 "숫자 검증기" 항목은 A9-4에서 처리했다.

**결론: API·Neo4j·근거 연결은 5개 질문 모두 동작했다. 답변 정확성은 4건 통과(1건은 경미한 표현 누락), Q5는 부분 미흡이다.** 코드는 수정하지 않았다.

- 호출: 승인된 5개 질문을 임시 서버(8505)에서 headless Edge로 한 번씩 제출했다. LLM 10회, 실패·재호출 0회, 모델 전환 없음. 임시 서버는 종료했다.
- 호환성: Chat Completions + `json_schema` strict + `reasoning_effort=low` + `max_completion_tokens` 조합이 오류 없이 동작했다. 응답 모델은 `gpt-6-luna`, 출력 상한 도달 없음.
- 합계: 입력 24,007, 출력 1,370토큰, 추정 $0.003086. 토큰 사용량으로 계산한 값이며 OpenAI 청구 내역과 대조하지 않았다.
- 로그: 흐름은 `REQUEST → CYPHER(card.catalog) → INTERPRET → RETRIEVE START → CYPHER → RETRIEVE DONE → ANSWER → FINAL`이다. 혜택 목록을 해석 전에 읽으므로 첫 CYPHER가 INTERPRET보다 앞선다. 서버 stderr를 파일로 받아 확인했고, VS Code 터미널 자체에서 본 것은 아니다.
- 인증정보: 로그와 화면에서 키·접속 문자열 미검출.

공통 Cypher는 `card.catalog`, `card.context`, `card.rules`, `card.conditions`, `card.evidence`이고 Q2를 뺀 4건은 `card.limits`도 실행했다.

| 질문 | 유형 / 혜택 ID(끝 3자리) | 조회(규칙·조건·한도·근거) | LLM 답변 요약 | 인용 근거(끝 3자리) | 평가 | 입력/출력 | 추정 비용 |
|---|---|---|---|---|---|---|---|
| Q1 ONE PICK STYLE 카드의 대중교통 혜택은? | DETAIL / 003 | 1·7·1·13 | 버스·지하철 5%, 월 1,000원, 실적 10만원, 등록일~다음 달 말일 유예, 시외·고속버스·KTX·SRT·ITX 제외 | 044, 045, 046, 049, 050 | 통과, 유예 문장에서 "최초" 누락 | 4,315/285 | $0.000574 |
| Q2 전월 실적이 없어도 대중교통 캐시백을 받을 수 있어? | CONDITION / 003 | 1·7·0·13 | 원칙은 10만원 조건, 최초 등록일~다음 달 말일은 미만이어도 제공 | 044, 049 | 통과 | 4,274/183 | $0.000519 |
| Q3 ONE PICK과 STYLE 혜택의 차이는? | COMPARE / 001, 002 | 4·10·6·18 | 대상 가맹점 차이, 같은 금액 구간, 일 1회·월 30회 대 일 1회·월 10회, 둘 다 월 5천원, 중첩 미확정 | 032~034, 036, 037, 039, 040, 042, 043 | 통과, DRAFT 문장 인용 부적절 | 5,260/474 | $0.000763 |
| Q4 놀이공원 할인율과 이용 횟수 제한은? | LIMIT / 004 | 1·7·2·6 | 에버랜드·롯데월드 50%, 월 1회·연 2회 | 051, 052, 053 | 통과. 1인 1매는 시스템 미확정 목록에 표시 | 3,173/201 | $0.000418 |
| Q5 1만원 이상 결제하면 캐시백은 얼마인가? | DETAIL / 001, 002, 003 | 5·17·7·26 | 대상 가맹점에서 건당 500원, 중첩 방식 미확정은 하단 표시 | 034, 035 | **부분 미흡** | 6,985/227 | $0.000812 |

프로그램·프롬프트 문제(미수정, 확인에 유료 호출 필요):

1. Q5: 1만원 결제는 3천원 이상과 1만원 이상 조건을 모두 충족하는데 본문이 500원을 답처럼 제시한다. 미확정은 하단에만 있다. 대상 혜택도 본문에서 구분하지 않고, 인용은 ONE PICK 쪽 034·035뿐이다.
2. Q5: "대상 불명이면 관련 혜택 모두"라는 프롬프트에 따라 1만원 기준이 없는 대중교통까지 선택했다. 문맥이 12,103자로 늘고 무관한 미확정 안내가 표시됐다.
3. Q3·Q5: DRAFT 상태 문장에 금액 표 근거를 인용했다. `validate_answer`는 ID 존재만 보고 내용 일치는 보지 않는다.
4. 화면 미확정 목록에 LLM 문장과 시스템 문장이 겹친다.

숫자 검증기: 실제 5개 질문에서 버린 문장 0건(warnings 0). 없는 숫자 생성 0, 계산 문장 0, 오탐 0이라 수정하지 않았다. 로컬 시험(LLM 없음)에서는 "30회와 10회의 차이는 20회"가 버려지고(오탐 재현), "3천원"을 "3만원"으로 바꾼 문장은 통과한다(단위를 보지 않음). "3개 혜택"처럼 다른 맥락의 숫자도 같은 값이 있으면 통과한다.

데이터 구조 문제:

1. 근거 연결이 POLICY·BNFT·POOL 단위라 RULE 연결이 없다(`rule_key` 모두 null). one_pick_100과 one_pick_500이 같은 원문 근거(034, 035)를 공유해 규칙별 추적이 안 된다.
2. 조건 대부분이 BNFT SELF 연결이다. COND 연결은 `spend_exclusions`뿐이다.
3. `transit_spend` 원문이 표 행을 이어 붙인 값이라 "10만원"의 의미는 `cond_min_amt`로만 확정된다.
4. `amusement_first_month`(최초 발급 월 미제공)는 `GRACE` 유형인데 NOT=True다. 유형 재검토가 필요하다.
5. `rule_select_cd`가 비어 있어 중첩 선택은 데이터로 판단할 수 없다. 최소 금액 3,000·10,000은 구조화되어 있다.

## A9-2 LangGraph GraphRAG (2026-11-01)

키워드 검색 화면을 질문·답변 화면으로 바꿨다. 구조와 호출 관계는 `README.md`를 기준으로 한다. 아래 "브라우저 검증 결과"의 화면 설명은 이전 키워드 화면 기준이다.

- 신규: `card_graphrag.py`, `../tests/test_card_graphrag.py`.
- 변경: `neo4j_search.py`(Cypher 식별자, 로그, `CATALOG_QUERY`, `list_catalog`, `get_detail(sections)`), `streamlit_app.py`(전면 교체), `../tests/test_neo4j_origin_search.py`, `README.md`, 이 문서.
- 그래프: `interpret → retrieve → answer → finish`. 오류·UNKNOWN·대상 없음·근거 없음은 조건부 Edge로 `finish`로 간다.
- 혜택 선택: 카드명 ONE PICK STYLE이 혜택명 ONE PICK과 겹치므로, 키워드 검색 대신 LLM이 실제 혜택 목록의 ID를 고르고 Python이 검증한다. 이 때문에 interpret에서 `card.catalog`를 한 번 읽는다. Neo4j 장애면 LLM 비용 없이 끝난다.
- 공통 Logger: `QueryLogger`와 `configure_query_logging`을 재사용하고 자식 logger만 추가했다. 새 handler는 없다.
- 모델: `CARD_SEARCH_MODEL`, 기본 `gpt-6-luna`, effort `low`, 재시도 0회. 단가와 지원값은 OpenAI 공식 문서에서 2026-11-01에 확인했다.

검증 수준:

| 수준 | 내용 | 결과 |
|---|---|---|
| Mock LLM + Mock Neo4j | 단위·AppTest 42개 | 통과 |
| 실제 SDK + 가짜 HTTP | 실제 `ChatOpenAI`의 요청 본문과 응답 해석 (위 42개에 포함) | 통과, 네트워크 없음 |
| 실제 Neo4j 읽기 | 4건, OR 구조, 한도 차이, 근거 관계, PENDING | 4개 통과 |
| 실제 Neo4j + Mock LLM + Edge | 예시 5건, 동일 질문, UNKNOWN, 원문 질문, 빈 질문, Neo4j 장애 | 정상, 콘솔 오류 0건 |
| 실제 gpt-6-luna | A9-3에서 5개 질문 실행 | 위 절 참조 |

브라우저 검증용 Mock 실행기는 세션 임시 폴더에 있었고 저장소에 넣지 않았다.

회귀: `payment_card/tests` 전체는 `PYTHONPATH=src/card_benefit`로 171 통과, 5 건너뜀. `run_offline_tests.py`의 recipe 묶음은 실패 20건이다. `src/recipe`, `src/common`은 수정하지 않았고, 원인은 `AppTest.form_submit_button` 부재 19건과 스키마 점검 1건이라 이번 변경과 무관해 보인다. 변경 전 기준선과 비교하지는 않았다.

남은 일: A9-3의 프로그램·프롬프트 문제 처리 여부 판단, Neo4j 장애 시 약 45초 대기 개선 여부 판단.

## Claude Code 브라우저 검증 결과 (2026-11-01, 키워드 화면 기준)

**결론: 브라우저에서 확인한 검증 항목은 모두 통과했고 수정한 코드는 없다.** 아래 Codex 기록 중 "브라우저 미검증" 내용은 이 절로 대체한다.

- 방법: 실제 Microsoft Edge(headless)를 임시 프로필로 띄워 `http://127.0.0.1:8501`에서 입력·선택·펼치기를 수행했다. 프로젝트에 패키지나 파일을 추가하지 않았다. 사람이 일반 브라우저로 본 것은 아니다.
- 서버: Codex가 시작한 PID 9336(11:36 시작, 소스 최종 수정 11:35)이 `127.0.0.1:8501`에서 계속 실행 중이며 `/_stcore/health`는 `ok`다. 다시 띄우지 않고 그대로 사용했다.
- 테스트: `test_neo4j_origin_search` 4개 통과.

| 항목 | 결과 |
|---|---|
| 첫 화면 | 제목·DRAFT 경고·검색창 표시, 브라우저 콘솔 오류·예외 0건 |
| 기본 혜택 | 4건 표시: 놀이공원, 대중교통, ONE PICK, STYLE |
| 키워드 검색 | 대중교통 1, ONE PICK 1, one pick 1(대소문자 무관), STYLE 1, 놀이공원 1, 캐시백 3, 빈 검색 4 |
| 상세(규칙·조건·한도·근거) | 놀이공원 1·7·2·13, 대중교통 1·7·1·14, ONE PICK 2·5·3·15, STYLE 2·5·3·14. 기존 기록과 일치 |
| 원문 대조 | 조건·근거 80건을 Neo4j 원문과 공백 제외 비교했다. 내용 누락·변형 0건, 차이는 아래의 목록 기호뿐이다 |
| 개발자 정보 | 혜택 4건 모두 펼침 성공, Cypher와 namespace 표시 확인 |
| 결과 없음 | `일치하는 혜택이 없습니다.` 표시 |
| 연결 오류 | 임시 서버 8502에 가짜 접속정보를 넣어 확인했다. 일반 오류 메시지만 표시되고 접속 주소·드라이버 오류·Traceback이 나오지 않았다. 임시 서버는 종료했다 |

수정하지 않은 관찰 사항:

1. 연결 실패 시 오류 메시지까지 약 45초(측정값 44.6초) 걸리고 그동안 화면 하단이 비어 있다. Neo4j 드라이버의 트랜잭션 재시도 시간이 원인으로 보이나 확인하지는 않았다. 동작 오류는 아니다.
2. `st.write`가 원문을 마크다운으로 해석해 줄 앞의 `- `, `* `가 글머리표로 표시된다. 글자 내용은 그대로지만 기호 자체는 보이지 않는다. 원문 그대로 보려면 `st.text`를 쓰면 된다.
3. PDF 근거 수는 연결 수라 같은 근거가 반복된다. 고유 근거는 놀이공원 11/13, 대중교통 13/14, ONE PICK 12/15, STYLE 11/14다.
4. Streamlit은 입력·선택마다 스크립트를 다시 실행하므로 `connect()`로 드라이버를 새로 만들고 닫는다. 캐시는 적용되어 있지 않다.

실제 호출 구조:

```text
streamlit_app.py (입력·선택마다 위에서 아래로 재실행)
├─ connect() ─ create_neo4j_driver() ─ load_project_environment()  # .env, TLS 검증
├─ Neo4jSearch.list_benefits(keyword) ─ _query(LIST_QUERY)
├─ Neo4jSearch.get_detail(key)
│    ├─ _query(CONTEXT_QUERY)    # 카드·정책·혜택
│    ├─ _query(RULE_QUERY)       # 규칙·대상
│    ├─ _query(CONDITION_QUERY)  # 정책/혜택/규칙 → 조건식 → 분기 → 조건
│    ├─ _query(LIMIT_QUERY)      # 규칙 → 한도
│    └─ _query(EVIDENCE_QUERY)   # 정책/혜택/한도 → 근거 → 청크 → 페이지 → 문서
├─ source(props)                 # source_json 복원
└─ search.driver.close()         # finally
_query → session(READ_ACCESS) → execute_read → tx.run(query, ns=NAMESPACE, ...) → record.data()
```

## 폴더와 원칙

- `db_pipeline/`: PostgreSQL V6 정제·검증, Neo4j 변환. 상태는 `../db_pipeline/PROJECT_STATUS.md`와 구조 비교 문서 참조.
- `db_pipeline_origin_search/`: 위 그래프의 독립적인 읽기 전용 검색.
- `file_pipeline/`: 팀원 담당. 기존 `graphrag-chatbot/`은 Supabase 기반 독립 프로토타입. 팀원 구현 코드 수정 금지.
- `file_pipeline_origin_search/`: 향후 팀원과 협의하는 Neo4j 검색, 미구현.
- 공통 `tests/`, `main.py`, `models.py`, `repository.py`. 기존 main 실행 동작 변경 금지.

Aura `6ac1f0f8`에는 ONE PICK STYLE 시험 그래프 노드 108·관계 168, `A8Test`, `namespace=ONE_PICK_STYLE_A8`이 있다. 정책 DRAFT·혜택 PENDING_REVIEW·근거 PENDING이며 사용자용 확정 정보가 아니다. `A8Card`→`A8Policy`→`A8Benefit`→`A8Rule`, 조건 Expression→Branch→Condition, LimitPool, Evidence→Chunk→Page→Document 관계가 실재한다. 원문 및 일부 상태는 `source_json`에 있다.

## Codex 구현 기록

- 생성: `__init__.py`, `neo4j_search.py`, `streamlit_app.py`, `README.md`, `../file_pipeline_origin_search/README.md`, `../tests/test_neo4j_origin_search.py`.
- 기존 `../db_pipeline/README.md`와 `../file_pipeline/README.md`는 기존 내용을 유지하면서 실제 구현과 링크를 보완했다. 팀원 Python 소스는 건드리지 않았다.
- `Neo4jSearch.list_benefits(keyword)`는 혜택명 부분 검색. `get_detail(key)`는 context, rules, conditions, limits, evidence 반환. `_query`는 Neo4j `READ_ACCESS`와 `execute_read`, namespace 매개변수를 사용한다. `connect()`는 기존 `src/recipe/recipe_recommender/neo4j_connection.py`의 `create_neo4j_driver()`를 재사용하며 certifi 또는 지정 CA로 TLS 검증을 유지한다. UI는 `source()`로 `source_json`을 읽는다.
- 실제 Aura 조회 성공: 빈 검색 4, ONE PICK 1, STYLE 1, 대중교통 1, 놀이공원 1, 캐시백 3, 없는 문자열 0. 4개 혜택의 상세 조회 성공: 놀이공원 규칙 1·조건 7·한도 2·근거 13, 교통 1·7·1·14, ONE PICK 2·5·3·15, STYLE 2·5·3·14. 근거는 정책 공통·혜택·한도를 포함하는 연결 수이며 중복 인용이 있을 수 있다.
- Streamlit 화면은 검색·선택·규칙/대상·조건 범위와 OR/AND/NOT·한도·근거·개발자 JSON/Cypher·DRAFT 경고·빈 결과/연결 오류 처리를 구현했다. UI의 실제 렌더링은 아직 확인 필요. 오류는 비밀정보 노출 방지를 위해 일반 메시지만 표시한다.
- 상세 쿼리의 `ORDER BY r.rule_key`는 집계 후 원 변수 접근 오류가 발생해 `ORDER BY rule.rule_key`로 수정했고 실제 상세 조회에 성공했다.

## Codex 마지막 실행 기록 (당시 기준, 위 검증 결과로 대체됨)

**후속 확인:** AppTest 경로를 절대 경로로 수정했다. 동일 테스트는 샌드박스에서 중단되는 현상이 있었으나 승인된 샌드박스 밖 실행에서 4개 모두 통과했다(빈 결과·연결 오류 메시지 포함). Streamlit은 `--server.address 127.0.0.1 --server.port 8501`로 실행 중이고 `/_stcore/health`가 HTTP 200 `ok`였다. 브라우저 UI 확인을 시도했으나 Windows Computer Use가 현재 브라우저 URL을 정책상 안전하게 확인하지 못해 해당 턴의 Computer Use를 중지했다. 따라서 화면 렌더링·실제 브라우저 상호작용은 미검증이다. README 실행 명령에도 로컬 주소를 반영했다. 아래 번호는 과거 오류 기록 및 남은 검증 항목으로 읽는다.

1. `python -m unittest src.card_benefit.payment_card.tests.test_neo4j_origin_search -v`에서 4개 중 2개가 실패했다. 원인: `AppTest.from_file()` 상대 경로가 테스트 파일 기준으로 해석돼 APP 경로가 중복됐다. `Path(__file__).resolve().parents[1] / 'db_pipeline_origin_search/streamlit_app.py'` 같은 절대 경로로 고친다. 종료 시 sandbox 임시 디렉터리 PermissionError도 출력됐으므로 재현 시 허용된 workspace 임시 경로 사용이나 실행 권한 확인. 순수 쿼리 범위와 JSON 테스트 2개는 통과했다.
2. `python -m streamlit run ... --server.headless true --server.port 8501`은 서버 시작 성공했으나 `:::8501` 바인딩을 확인해 즉시 중지했다. 로컬 전용으로 `--server.address 127.0.0.1`을 붙여 재실행하고 `http://127.0.0.1:8501/_stcore/health` 확인. README 명령에도 로컬 바인딩 추가 필요.
3. AppTest로 기본 조회·검색 입력·결과 없음·접속 오류를 검증하고 가능하면 브라우저 UI를 확인한다. 연결 실패 시 상세 오류/비밀번호가 화면에 나오지 않아야 한다.
4. README 네 개의 정확한 명령, 변경 범위, 테스트와 실제 UI 결과를 재확인하고 이 문서를 갱신한다. Neo4j/PG 쓰기, 유료 LLM 호출, Git commit/push는 하지 않는다.

## 환경 및 명령

Python `.venv\\Scripts\\python.exe`, 설치된 Streamlit 1.65.0, neo4j 6.4.1, certifi, python-dotenv. 기존 환경변수 이름: `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, 선택 `NEO4J_TRUSTED_CA_FILE`; 값은 기록하지 않는다. 기존 `DB_URL`은 이 검색 화면에서 사용하지 않는다. 루트 실행: `.\\.venv\\Scripts\\python.exe -m streamlit run src/card_benefit/payment_card/db_pipeline_origin_search/streamlit_app.py --server.address 127.0.0.1`; 테스트: `.\\.venv\\Scripts\\python.exe -m unittest src.card_benefit.payment_card.tests.test_neo4j_origin_search -v`.

Streamlit 설치 버전의 개발 지침을 읽고 작업 중이다. 함수 호출은 `streamlit_app.py → connect → Neo4jSearch.list_benefits/get_detail → _query → driver session.execute_read → Cypher → dict → Streamlit`. 원본 JSON을 무조건 승인된 조건으로 해석하지 않는다. DB 스키마·데이터, 기존 LLM 응답, 기존 main.py, file_pipeline 구현은 변경 금지. 기존 미커밋 파일을 보호하고 신규 패키지·불필요한 추상화는 추가하지 않는다. Git Commit/Push 금지.
