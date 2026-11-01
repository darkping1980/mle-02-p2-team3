# db_pipeline_origin_search

`db_pipeline`이 PostgreSQL V6에서 변환한 Neo4j 그래프를 자연어로 묻고 답하는 로컬 LangGraph GraphRAG 개발 프로그램입니다. ONE PICK STYLE의 `df_one_pick_style` namespace에 있는 DF DRAFT 데이터만 조회하며 확정 상품 정보가 아닙니다. Neo4j는 읽기 전용이고 PostgreSQL에는 접속하지 않습니다.

## 실행

프로젝트 루트의 VS Code 터미널에서 실행합니다. 단계별 로그는 이 터미널에 출력됩니다.

```powershell
.\.venv\Scripts\python.exe -m streamlit run src/card_benefit/payment_card/db_pipeline_origin_search/streamlit_app.py --server.address 127.0.0.1
```

접속 URL은 `http://127.0.0.1:8501` 입니다. **질문 실행** 버튼을 누르면 유료 API가 호출됩니다. 화면을 열거나 예시 질문을 고르는 것만으로는 호출되지 않습니다.

## 환경 설정

| 이름 | 필수 | 설명 |
|---|---|---|
| `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` | 필수 | 기존 `.env` 사용 |
| `NEO4J_DATABASE`, `NEO4J_TRUSTED_CA_FILE` | 선택 | `common.neo4j_connection`이 사용 |
| `OPENAI_API_KEY` | 필수 | 없으면 질문 실행 시 안내만 표시 |
| `CARD_SEARCH_MODEL` | 선택 | 기본 `gpt-6-luna`. 다른 모델로 자동 전환하지 않음 |
| `CARD_SEARCH_LOG_LEVEL` | 선택 | 기본 `DEBUG`. 프롬프트, 실행 가능한 Cypher, 레코드 표 출력. `INFO`로 끔 |
| `DB_QUERY_LOG` | 선택 | 공통 쿼리 로그 스위치. `0`이면 끔. 없으면 로컬 개발 환경에서 켜짐. `RECIPE_QUERY_LOG`는 카드에 영향을 주지 않음 |

LLM 호출 값은 `card_graphrag.py` 위쪽 상수에 있습니다. reasoning effort는 interpret와 answer 모두 `low`, 출력 상한은 각각 600, 2000토큰, 제한 시간은 60초, 재시도는 0회입니다.

## 개발 검증 모드

화면 위 **실행 모드**에서 **개발 검증**을 고르면 단계를 버튼으로 진행합니다. 자동 실행은 그대로입니다.

| 단계 | 버튼 | 실행되는 것 | 화면 |
|---|---|---|---|
| 1 | 질문 해석 실행 | 카탈로그 Cypher, Interpret LLM 1회 | 유형, 혜택 ID, 검색 조건, 토큰, 카탈로그 Cypher와 결과 |
| 2 | 없음 | 실행 없음 | 실행 예정 Cypher 전문과 파라미터 |
| 3 | DB 조회 실행 | 혜택 상세 Cypher, 읽기 전용 | 문장별 레코드 표, 원본 JSON, 합쳐진 근거, 미확정 사항 |
| 4 | LLM 답변 생성 | Answer LLM 1회 | 자동 실행과 같은 답변 화면 |

2단계 코드 블록의 복사 버튼으로 Neo4j Browser에 붙여넣으면 바로 실행됩니다. 공통 `render_cypher_inline`이 값을 넣은 Cypher이며, 실제 실행은 바인딩 방식이고 결과는 같습니다.

자동 실행과 같은 노드(`interpret`, `retrieve`, `answer`, `finish`)와 라우팅 함수를 직접 호출합니다. 체크포인트는 쓰지 않습니다.

```text
verify_view.render → verify_interpret → interpret
                   → verification_plan → detail_plan (get_detail과 같은 쿼리·순서)
                   → verify_retrieve → retrieve → get_detail
                   → verify_answer → answer → finish
```

- 결과는 `session_state.verify`에 있어 위젯 재실행으로 다시 호출되지 않습니다.
- 이미 실행한 단계를 다시 호출해도 아무 일도 하지 않습니다.
- 질문을 바꾸면 이전 결과를 지웁니다. 검색 조건이 조회 당시와 다르면 `verify_answer`가 거부합니다.

터미널에는 Cypher 전문, 파라미터, 레코드 표가 함께 출력됩니다. 개발 단계라 자동 실행도 기본값 `DEBUG`로 같은 내용을 출력합니다.

## LangGraph 구조

```text
START → interpret ─┬→ retrieve ─┬→ answer → finish → END
                   └→ finish    └→ finish
```

| 노드 함수 | 하는 일 | State 갱신 |
|---|---|---|
| `CardGraphRAG.interpret` | Neo4j 혜택 목록 조회, LLM 해석, 혜택 ID 검증 | `intent`, `search_parameters`, `llm_calls`, `warnings` |
| `CardGraphRAG.retrieve` | 질문 유형별 Cypher 템플릿 실행 | `retrieved_data`, `evidence`, `statements`, `unresolved` |
| `CardGraphRAG.answer` | 검색 결과로 답변 생성, 근거 ID·숫자 검증 | `context`, `answer`, `llm_calls`, `warnings` |
| `CardGraphRAG.finish` | 답변 없는 경로의 안내, 최종 로그 | `answer`, `warnings` |

`after_interpret`는 오류, `UNKNOWN`, 대상 혜택 없음이면 `finish`로 보냅니다. `after_retrieve`는 조회 결과나 근거가 없으면 `finish`로 보내 Answer 호출을 생략합니다. `finish`는 안내 문구와 최종 로그를 한 곳에서 처리하려고 추가한 노드입니다.

### State

`CardState`의 키는 다음과 같습니다. `warnings`, `llm_calls`, `path`는 reducer로 누적됩니다.

| 키 | 내용 |
|---|---|
| `request_id`, `started`, `question` | 요청 식별자, 시작 시각, 질문 |
| `intent` | 질문 유형 |
| `search_parameters` | 검증된 `benefit_ids`, `benefit_names`, `benefit_keys`, `sections`, `payment_amount`, `ambiguity` |
| `retrieved_data` | 혜택별 Neo4j 조회 원본 |
| `evidence` | `evidence_id`로 합친 근거(페이지, 승인 상태, 원문) |
| `statements` | 실행한 Cypher 식별자 |
| `unresolved` | 조회 결과에서 LLM 없이 판별한 미확정 사항 |
| `context` | LLM에 실제로 전달한 검색 결과 |
| `answer` | `status`, `conclusion`, `points`(`text`, `evidence_ids`, `benefit_id`, `benefit_name`, `origin`, `verification`), `uncertain`, `message` |
| `error` | `stage`, `code`, 예외 형식 이름 |
| `warnings`, `llm_calls`, `path` | 경고, 호출별 토큰·비용, 실행 노드 순서 |

### 질문 유형과 조회 범위

| 유형 | 조회 항목 |
|---|---|
| `BENEFIT_DETAIL`, `BENEFIT_COMPARE` | 규칙, 조건, 한도, 근거 |
| `BENEFIT_CONDITION` | 규칙, 조건, 근거 |
| `BENEFIT_LIMIT` | 규칙, 조건, 한도, 근거(정책 공통 근거 제외) |
| `EVIDENCE_SEARCH` | 근거 |
| `UNKNOWN` | 조회 없음 |

LLM은 Cypher를 만들지 않습니다. 실제 혜택 목록에서 ID를 고르고, Python이 목록에 없는 ID를 버립니다. 실행되는 Cypher는 `neo4j_search.py`의 템플릿뿐이며 값은 파라미터로 전달합니다.

## 함수 호출 관계

```text
streamlit_app.py  (질문 실행 버튼을 누른 경우만)
└─ get_pipeline()                       # cache_resource로 재사용
   ├─ neo4j_search.connect() → create_neo4j_driver()
   └─ card_graphrag.create_llms() → ChatOpenAI 2개
└─ CardGraphRAG.run(question) → graph.invoke(...)
   ├─ interpret
   │    ├─ Neo4jSearch.list_catalog() → _query(CATALOG_QUERY)
   │    ├─ _call_llm(Interpretation)
   │    └─ payment_amount() → filter_by_payment()
   ├─ retrieve
   │    ├─ Neo4jSearch.get_detail(key, sections)
   │    │    └─ _query(CONTEXT/RULE/CONDITION/LIMIT/EVIDENCE_QUERY)
   │    ├─ collect_evidence()
   │    └─ find_unresolved()
   ├─ answer
   │    ├─ benefit_context() → condition_groups()   # 조건식 → 분기(OR) → 조건(AND), NOT
   │    ├─ rule_conflicts()                         # 규칙 선택 미확정 구간
   │    ├─ _call_llm(CardAnswer)
   │    └─ validate_answer()
   │         ├─ known_values() → unknown_values()   # 단위·기간·차이 계산
   │         ├─ picks_single_tier()                 # 일부 구간 단정 차단
   │         ├─ verification_level()                # 인용 원문 값 일치 판정
   │         └─ fixed_conclusion()                  # 결론의 미확정 표시 보장
   └─ finish                            # 전체 시간·토큰·추정 비용 로그
_query → session(READ_ACCESS) → execute_read → tx.run(query, ns=..., 파라미터) → record.data()
```

`_call_llm`은 `with_structured_output(schema, method="json_schema", strict=True, include_raw=True)`를 사용합니다. gpt-6-luna의 Chat Completions 함수 호출은 effort `none`에서만 동작하므로 json_schema 방식을 씁니다. `include_raw`로 토큰 사용량을 함께 받습니다.

## 검색 대상과 답변 검증

**대상 선정.** `card.catalog`는 규칙 단위 결제 기준(`payment_min_amounts`)을 함께 읽습니다. LLM은 질문과 직접 관련된 혜택만 고르고, 후보를 좁힐 수 없으면 `benefit_ids`를 비운 채 `ambiguity`에 불명확한 점을 씁니다. 이 경우 Answer를 호출하지 않고 안내만 표시합니다. 결제 금액 질문의 `BENEFIT_DETAIL`, `BENEFIT_CONDITION`은 `filter_by_payment`가 규칙 단위 결제 기준이 없는 혜택을 제외합니다. 비교 질문과 전부 탈락하는 경우는 그대로 둡니다.

**미확정 규칙.** `rule_conflicts`가 규칙이 둘 이상이고 `rule_select_cd`가 없는 혜택의 금액 구간을 계산해 `rule_selection_unresolved`로 LLM에 전달합니다. 결제 금액에 둘 이상의 구간이 해당하면 `validate_answer`가 다음을 보장합니다.

- 일부 구간 금액만 쓴 문장과 결론은 쓰지 않습니다.
- 결론에 미확정을 표시합니다. 없으면 `fixed_conclusion`이 프로그램 문구로 보완합니다.
- 혜택별 금액 구간 문장이 없으면 조회 값과 해당 혜택 근거로 프로그램이 작성합니다(`origin=system`).
- 규칙 선택이 미확정인 혜택에 우선·중복·합산 같은 적용 방식을 말하는 문장은 버립니다.

**값 검증.** `value_tokens`는 금액, 비율, 횟수와 앞에 붙은 기간(일·월·연)을 구분합니다. 1천원과 1,000원은 같은 값입니다. 문장의 값은 해당 혜택의 구조화 값, 조건·근거 원문, 질문 안에 같은 단위로 있어야 합니다. 같은 문장에 있는 두 확인된 값의 차이는 차이를 뜻하는 표현이 있을 때만 허용합니다. 합계와 비율 계산은 허용하지 않습니다. 단위가 없는 숫자는 조회 결과 안의 숫자와 비교합니다.

**근거 검증.** 다음 범위만 프로그램이 판정합니다.

| 검사 | 내용 |
|---|---|
| 존재 | 인용 ID가 이번 조회 결과에 있는지 |
| 혜택 범위 | 인용 근거가 문장의 `benefit_id` 조회에서 나왔는지 |
| 상태 문장 | DRAFT·PENDING·미확정을 말하는 문장을 `points`에서 `uncertain`으로 이동 |
| 값 일치 | 문장의 값이 인용 원문에 있는지(`verification`) |

`verification` 값은 `RAW_MATCH`(인용 원문과 일치), `CALCULATED`(인용 원문 값의 차이), `STRUCTURED_ONLY`(구조화 데이터와 일치, 인용 원문에서는 미확인), `NOT_CHECKED`(값 없는 문장)입니다.

문장의 의미가 근거와 맞는지, 규칙별로 맞는 근거인지는 판정하지 못합니다. `benefit_evidence`는 정책·혜택·규칙·한도 경로를 모두 읽고, 규칙 연결은 `evidence[].rule_keys`로 남습니다. 다만 근거 34~41은 병합 셀 전체를 인용하므로 규칙별로 구분되는 것은 연결입니다. `RAW_MATCH`는 값이 같다는 뜻이며 의미 일치를 보장하지 않습니다.

## Cypher 파일

```text
Streamlit → LangGraph → neo4j_search.py → graph_questions.cypher → Neo4j
```

| 파일 | 맡는 일 |
|---|---|
| `graph_questions.cypher` | 조회 정의. `// name:` 블록 7개, 읽기 전용 |
| `neo4j_search.py` | 파일 읽기, 실행, 로그, 결과 dict 변환 |
| `card_graphrag.py` | 어떤 조회를 언제 쓸지 결정, 검증, 답변 |
| `streamlit_app.py` | 입력과 표시 |

| statement | Python 상수 | 호출 함수 | 로그 식별자 |
|---|---|---|---|
| `graph_questions.catalog` | `CATALOG_QUERY` | `list_catalog` | `card.catalog` |
| `graph_questions.list_benefits` | `LIST_QUERY` | `list_benefits` | `card.list` |
| `graph_questions.benefit_context` | `CONTEXT_QUERY` | `get_detail` | `card.context` |
| `graph_questions.benefit_rules` | `RULE_QUERY` | `get_detail` | `card.rules` |
| `graph_questions.benefit_conditions` | `CONDITION_QUERY` | `get_detail` | `card.conditions` |
| `graph_questions.benefit_limits` | `LIMIT_QUERY` | `get_detail` | `card.limits` |
| `graph_questions.benefit_evidence` | `EVIDENCE_QUERY` | `get_detail` | `card.evidence` |

파일은 공통 `Neo4jDbSession(mapper_root=...).mappers`로 읽습니다. 드라이버 없이 동작하며 별도 로더는 없습니다. 파일명이 namespace이고 `// name:`이 statement입니다.

실행은 `Neo4jDbSession.select_list`가 아니라 `Neo4jSearch._query`가 합니다. `select_list`는 자동 커밋 `session.run`이라 `READ_ACCESS`와 재시도가 없고, 요청 식별자와 노드·관계 경로를 남기는 현재 로그도 달라지기 때문입니다.

값은 `tx.run(query, ns=NAMESPACE, **params)`로 바인딩합니다. Cypher 문자열에 값을 잇지 않습니다.

| 구분 | 텍스트 | 사용처 |
|---|---|---|
| 실행용 | `$ns`가 있는 `.cypher` 원문, 값은 별도 전달 | 드라이버 |
| 복사용 | 값이 들어간 Cypher, 공통 `render_cypher_log`·`render_cypher_inline` | 터미널 로그, 검증 화면, DBeaver |

`.cypher` 파일 원문을 DBeaver에서 그대로 실행하면 값이 없어 `42001`이 납니다. JDBC가 상위 코드의 "invalid syntax" 문구만 보여 줄 뿐, 실제 원인은 `42N81 missing request parameter`입니다. 터미널의 `QUERY` 블록에서 `====` 사이 또는 검증 화면의 코드 블록을 복사하세요. `:param` 줄은 드라이버와 JDBC에서 실행되지 않습니다.

## 로그

`src/common/query_logger.py`의 `QueryLogger`를 재사용합니다. logger 이름은 공통 `car_search_rag.neo4j`의 자식인 `car_search_rag.neo4j.card_graphrag`입니다. handler는 `common.query_log_config`가 부모에 한 번만 붙이므로 Streamlit이 재실행되어도 중복되지 않습니다. 실행 중 `.env`에 `DB_QUERY_LOG=0`을 추가하면 다음 재실행에서 handler를 제거합니다. 이미 읽은 값을 바꾸거나 지우려면 앱을 다시 시작해야 합니다(`.env`는 프로세스 환경변수를 덮어쓰지 않습니다).

| 이벤트 | 내용 |
|---|---|
| `REQUEST` | 요청 식별자, 질문, 시작 시각, 모델 |
| `CYPHER` | Cypher 식별자, 파라미터, 건수, 노드·관계 경로, 시간 |
| `QUERY`, `RESULT DATA` | Cypher 전문과 레코드 표. 검증 모드 또는 DEBUG |
| `INTERPRET` | 모델, 유형, 대상 혜택, 제외한 혜택, 결제 금액, 모호한 점, 토큰, 비용, 시간 |
| `RETRIEVE START`, `RETRIEVE DONE` | 식별자, 항목별 건수, 근거 ID, 시간 |
| `ANSWER` | 모델, 입력 근거 수, 미확정 규칙 혜택, 결론, 답변, 값 일치 판정, 인용 근거, 토큰, 비용, 시간 |
| `FINAL` | 실행 경로, 호출별 토큰, 합계, 추정 비용, 경고 수, 오류, 전체 시간 |

기본값 `DEBUG`에서는 프롬프트(조회된 PDF 인용 포함), 값이 들어간 Cypher, 레코드 표를 출력합니다. `CARD_SEARCH_LOG_LEVEL=INFO`이면 요약 줄만 남고, 검증 모드는 Cypher와 레코드를 계속 출력합니다. `DB_QUERY_LOG=0`이면 쿼리 로그가 꺼져 출력되지 않습니다. API 오류는 예외 형식 이름만 기록합니다.

## 비용

추정 비용은 응답의 토큰 사용량과 `MODEL_PRICES`로 계산합니다. `gpt-6-luna`는 100만 토큰당 입력 $0.10, 캐시 입력 $0.01, 출력 $0.50입니다(OpenAI 가격표, 2026-11-01 확인). 추론 토큰은 출력 토큰 수에 포함된 값으로 계산합니다. 단가가 없는 모델이나 사용량을 받지 못한 호출은 합계에서 빠지고 경고가 남습니다. OpenAI 청구 금액을 대신하지 않습니다.

중복 호출은 다음과 같이 막습니다. 결과는 `session_state`에 저장되어 위젯 재실행으로 다시 호출되지 않습니다. 직전 성공 결과와 같은 질문은 **같은 질문도 다시 실행**을 켜지 않으면 호출하지 않습니다.

## 테스트

```powershell
# Mock LLM·Mock Neo4j, 외부 호출 없음
.\.venv\Scripts\python.exe -m unittest card_benefit.payment_card.tests.test_card_graphrag card_benefit.payment_card.tests.test_neo4j_origin_search

# 실제 Neo4j 읽기 테스트 추가. LLM은 Mock이며 A9-3 실제 응답을 재생한다
$env:RUN_NEO4J_INTEGRATION='1'; .\.venv\Scripts\python.exe -m unittest card_benefit.payment_card.tests.test_card_graphrag card_benefit.payment_card.tests.test_neo4j_origin_search
```

`run_offline_tests.py`에는 카드 테스트가 포함되어 있지 않습니다.

`common`과 `card_benefit`은 `uv sync`의 편집 설치가 `src`를 import 경로에 넣어 찾습니다. 코드에서 `sys.path`를 바꾸지 않으므로 프로젝트 `.venv`의 Python으로 실행합니다.

## 데이터 주의

100원·500원 규칙의 중첩 선택, 대중교통 제외의 NOT과 범위, CARD_MEMBER 집계, 정책 시작일, 1인 1매는 미확정입니다. `find_unresolved`가 조회 결과에서 이를 판별해 LLM 답변과 별도로 화면에 표시합니다. 텍스트 위치 일치는 근거 승인이나 표 행의 의미 검증을 보장하지 않습니다.
