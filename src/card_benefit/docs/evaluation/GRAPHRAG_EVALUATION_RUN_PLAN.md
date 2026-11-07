# GraphRAG 1·2홉 평가 실행 계획

## 현재 평가 세트 확인

기준 파일은 `evaluation_set_50.json`과 `golden_answer_set_50.json`이다. 구조 검증 결과 질문 50개와 정답 레코드 50개가 1:1로 연결되고, ID 중복이 없으며, 1-hop 25개·2-hop 25개다. 정답 상태는 VERIFIED 49개, NEEDS_REVIEW 1개(CARD10-030), NOT_IN_SOURCE 0개다. CARD10-030은 실행 결과는 보존하지만 정확도 분모에서 제외한다. 러너의 사전 검사도 이 수량과 상태가 변하면 실행 전 중단한다.

시험 실행용 문항은 각 홉에서 첫 VERIFIED 질문을 사용한다.

| 구분 | ID | 질문 |
|---|---|---|
| 1-hop | CARD10-001 | ONE PICK STYLE 하나 체크카드에 등록된 주요 혜택을 알려줘. |
| 2-hop | CARD10-021 | ONE PICK STYLE의 편의점·카페 캐시백은 결제금액과 이용 횟수에 어떤 조건이 있어? |

전체 평가를 실행할 때 CARD10-030도 결과에 포함하되 `JUDGMENT_HOLD`로 유지한다.

## 실제 백엔드 진입점

Streamlit 팩토리 `db_pipeline_origin_search/streamlit_app.py:get_pipeline()`은 `neo4j_search.connect()`, `card_graphrag.create_neo4j_benefit_search(search)`, `card_graphrag.create_llms()`, `CardGraphRAG(...)` 순으로 파이프라인을 구성한다. 실제 사용자 질문은 같은 파일의 제출 경로에서 `pipeline.run(question)`으로 전달된다.

전체 LangGraph 경로의 검증된 진입점은 `db_pipeline_origin_search/card_graphrag.py:CardGraphRAG.run(question)`이며 `self.graph.invoke(self._initial_state(question))`를 호출한다. 컴파일된 그래프는 `interpret → retrieve → answer → finish`이고, 근거가 없거나 오류가 발생하면 라우팅에 따라 answer 단계가 생략된다. 따라서 독립 러너는 Streamlit을 import하지 않고 위와 동일한 팩토리 구성 후 실제 `CardGraphRAG.run(question)`을 호출한다. 테스트용으로 다른 검색·답변 로직을 대체하지 않는다.

실행 스크립트: [run_graphrag_evaluation.py](run_graphrag_evaluation.py)

```powershell
# 무호출 사전 확인: 기본 1-hop/2-hop 두 문항과 비용·범위를 출력
python src/card_benefit/docs/evaluation/run_graphrag_evaluation.py

# 두 문항 유료 smoke 실행: 별도 승인 후에만 실행
python src/card_benefit/docs/evaluation/run_graphrag_evaluation.py --execute --confirm-paid-calls

# 전체 50건: 별도 승인 후에만 실행하며 두 확인 플래그 모두 필요
python src/card_benefit/docs/evaluation/run_graphrag_evaluation.py --all --execute --confirm-paid-calls --confirm-full-50
```

`--execute` 없이 실행하면 평가 JSON만 읽고 네트워크·DB 연결을 하지 않는다. smoke 실행은 최대 2개 ID만 허용한다. 전체 실행은 `--all` 및 추가 확인 플래그가 없으면 거부된다. 평가 요청으로 Golden Answer 파일을 수정하지 않는다.

## 호출량과 저장 동작

예상 호출 수는 추정치와 상한을 구분한다.

| 실행 | 임베딩 API | LLM API | Neo4j 읽기 쿼리 |
|---|---:|---:|---:|
| smoke 2문항 | 질문당 1회, 총 2회 | interpret 1회 + answer 최대 1회/질문, 총 최대 4회 | 통상 문항당 3~5회 수준. catalog batch 1회와 hybrid 검색 1회, 선택 혜택 상세 배치 그룹별 1회 이상, TERMS 적용 시 추가 조회. 실제 실행값은 쿼리 로그/상태로 확인해야 하며 사전 확정하지 않음. |
| 전체 50문항 | 최대 50회 | interpret 최대 50회 + answer 최대 50회 | 문항당 상세 배치·조건부 TERMS에 따라 달라지므로 실행 시 계측 |

`create_llms()`는 키가 설정돼 있지 않으면 두 LLM을 만들지 않으며 러너는 API 호출 전에 중단한다. LLM 호출 설정은 `max_retries=0`이다. 임베더는 질문 검색에서 질문당 한 번 호출된다. 위 숫자는 재시도나 내부 클라이언트 동작을 포함하지 않는 앱 수준 호출 수다. 비용은 모델·토큰 사용량에 따라 달라지므로 여기서 금액을 추정하지 않는다.

직접 백엔드 실행은 Streamlit UI와 `capture_request_queries()` / `persist_app_logs()` 요청 래퍼를 통과하지 않으므로 `db_pipeline.app_log`에 기록하지 않는다. 기본 `APP_DB_LOG_ENABLED`는 ON이며 Streamlit 제출 경로는 정상 응답·예외 후 `finally`에서 로그를 저장한다. 동일 질문 재사용 경로도 이전 결과를 재사용하면서 별도 로그를 저장할 수 있다. 러너는 `streamlit_app`을 import하지 않고 DB 로그 저장 설정을 끄며 `persist_app_logs()`를 호출하지 않는다. 따라서 평가 실행은 PostgreSQL 업무 데이터와 app_log를 모두 변경하지 않는다. Neo4j는 검색·상세조회만 수행한다.

## 결과 기록 형식과 검토

실행 결과는 별도 JSON 파일로 저장한다. 각 질문에 질문 ID·홉·실행 상태·전체 경과 시간·실제 answer와 상태·원본/검증 후 diagnostics·Hybrid 검색 후보·Interpret 선택 참조·혜택 키·Evidence ID/페이지/인용·LLM별 토큰/시간·오류·경고를 기록한다. PDF 근거 객체는 GraphRAG 답변용 evidence와 혜택별 상세조회에서 반환된 원본 Evidence 구조를 나눠 보존한다. 예상 답과 PDF 정보는 검토 편의를 위해 결과에 복사하되 Golden Answer 원본은 변경하지 않는다.

텍스트 문자열 포함 여부만으로 정답을 자동 판정하지 않는다. 최종 판정은 공식 PDF를 기준으로 아래를 확인한 뒤 기록한다.

- **CORRECT**: 핵심 사실과 조건이 모두 일치하고, 답변에 사용된 Evidence가 올바른 혜택·문서·페이지에 귀속되며 인용문이 주장을 뒷받침함.
- **PARTIAL**: 확인된 사실은 맞지만 질문이 요구한 핵심 금액·조건·한도 또는 근거 일부가 누락됨.
- **WRONG**: 틀린 값, 잘못된 혜택 소속/구간 연결, 상충하는 설명 또는 원문이 지지하지 않는 주장이 있음.
- **EXECUTION_ERROR**: LangGraph가 오류 상태를 반환하거나 실행 중 예외가 발생함. VERIFIED 정확도 분모에 남기고 정답으로 세지 않음.
- **JUDGMENT_HOLD**: CARD10-030처럼 Golden Answer 자체가 NEEDS_REVIEW인 문항. 출력은 보존하지만 정확도 분모에서 제외함.

정확도 분모는 전체 고정 49 VERIFIED 문항이다. 실행 오류는 별도 집계하고 49건 중 정답으로 세지 않는다. 홉별 정답률은 각 홉의 VERIFIED 문항 수를 분모로 계산한다(현재 분포상 CARD10-030은 2-hop 분모에서 빠져 1-hop 25, 2-hop 24). 근거 일치율은 VERIFIED 출력 중 기대 혜택의 소유권·문서/페이지·인용 지원을 모두 확인한 출력 비율로 별도 계산한다. 부분 정답은 정확도 정답 수에 포함하지 않는다.

검색 누락 원인은 `expected benefit_id → Hybrid 후보 hit → interpret 선택 → retrieve 선택 혜택/키 → 해당 혜택 Evidence → answer point 인용` 순서로 나눈다. 기대 혜택이 후보에도 없으면 후보검색 누락, 후보에 있으나 선택되지 않으면 interpret/보완 단계 누락, 선택됐으나 상세 데이터가 없으면 retrieve/그래프 연결 누락, detail에 Evidence가 있으나 answer에 없으면 답변 근거 선택·검증 단계 문제로 분류한다.

공통서비스 혜택은 이 카드 상품 50문항 평가 결과와 섞지 않는다. 응답 검색 후보에 공통 혜택이 나타난 경우 개별 오류 추적 기록은 가능하지만 이를 공통서비스 전반의 정확도로 일반화하지 않으며, 공통서비스는 별도 평가 세트와 분모를 마련해 측정한다.

## 제한 및 주의

- 50문항 전체 실행은 임베딩 최대 50회, LLM 최대 100회가 될 수 있는 유료 실행이다. 이번 준비 작업에서는 실행하지 않았다.
- API 응답·DB 접근 가능 여부는 아직 실행 검증하지 않았다. smoke 2문항 실행 후 실제 호출량, Evidence 메타데이터, 응답 시간을 확인하고 전체 실행 여부를 별도로 결정한다.
- 전체 실행에서 예외가 발생한 문항도 결과 파일에 오류 레코드로 보존한다. 파일 기록 전 프로세스 중단 또는 연결 실패의 경우 결과 파일 자체가 만들어지지 않을 수 있으므로, 장시간 전체 평가 전에는 소량 smoke 결과를 별도 보관한다.
- 기존 app_log 동작과 직접 러너의 무기록 동작은 다르다. UI 검증을 대체하지 않으며, 이 준비 단계에서 Streamlit UI는 실행하지 않았다.

수동 PDF 판정 후 결과 JSON의 각 레코드에 `judgment`를 위 분류 중 하나로 기록하고, `evidence_match`를 `true`/`false`로 기록하면 다음 명령으로 홉별 정확도·검토된 근거 일치율·실행 오류·후보 누락을 요약할 수 있다. 이 명령은 파일만 읽으며 backend/API/DB를 호출하지 않는다.

```powershell
python src/card_benefit/docs/evaluation/run_graphrag_evaluation.py --score src/card_benefit/docs/evaluation/runs/evaluation_run_<timestamp>.json
```

49 VERIFIED 문항 중 일부만 실행했거나 PDF 판정이 남아 있으면 결과 요약은 부분 집계로 표시된다. 후보 누락 카운트는 질문 세트의 예상 `benefit_id(s)`와 실제 Hybrid 후보 ID를 비교한 진단값이며, 최종 정확도 판정은 아니다.
