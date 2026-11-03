# 하나카드 GraphRAG 데이터 준비 인수인계 — 2026-11-03

## 1. 현재 지시와 주의사항

이 문서는 2026-11-03 15:10경 KST에 확인한 스냅샷이다. **진행 중인 추출이 있으므로 이 문서를 읽은 시점의 DB와 프로세스 상태를 먼저 재확인한다.** 사용자의 최신 지시는 발표용 실제 데이터 준비다. 신규 통합 실행기·자동 승인 시스템 개발은 중단하고, 기존 `ExtractionService`, `CommonBenefitService`, `EmbeddingService`, Neo4j 로더 및 GraphRAG를 사용한다. `LINK_REVIEW`·`PENDING_REVIEW`는 자동으로 실패가 아니다. 근거 누락·대상 모호·DB 정합성 오류는 별도로 구분한다. DB CHECK를 없애거나 검사 결과를 일괄 `OK`로 바꾸지 않는다.

기존 데이터 삭제·초기화, Neo4j 전체 삭제·재구축, Git commit/push 금지. 원문과 업무 식별자가 불명확한 후보는 임의로 등록하지 않는다. 유료 AI 호출은 사용자가 허용했으나 실제 토큰과 비용을 기록하고, 이미 성공한 문서는 재호출을 피한다. 기존 요청에 데이터 백업과 복원 가능성 확인이 포함되어 있으며, **이번 작업에서 독립적인 백업·복원 검증은 완료하지 않았다.**

## 2. 다음 세션의 첫 작업: 실행 상태 확인

PowerShell에서 저장소 루트 `C:\myproject\workspace\mle-02-p2-team3` 기준:

```powershell
Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
  Where-Object { $_.CommandLine -like '*common_existing_extract_once_codex*' } |
  Format-List ProcessId,ParentProcessId,CommandLine
.venv/Scripts/python tmp/handoff_state_codex.py
.venv/Scripts/python tmp/common_stage_readonly_codex.py
git status --short --untracked-files=all
```

마지막 두 DB 조회 스크립트는 읽기 전용이며 `.env`의 DB 연결을 쓴다. 비밀번호나 키를 출력하지 않는다. 네트워크 sandbox에서 거부되면 승인 절차를 따른다. 프로세스가 살아 있고 해당 run이 `RUNNING`이면 **중단하거나 재실행하지 말고 기다린다**. 호출이 서버에서 처리된 뒤 네트워크 오류가 나면 비용이 발생했을 수 있다. 완료 후 DB `card_ai_call`의 사용량·상태와 `card_ai_run.run_status`를 먼저 확인한다.

## 3. 실제 실행 중인 프로세스

15:10경 확인:

| 대상 | 명령 | 프로세스 / 세션 | DB run | 현재 상태 |
|---|---|---|---|---|
| Visa Infinite `HANA_VI001_20260317`, 문서 `20261103_000020` | `.venv/Scripts/python tmp/common_existing_extract_once_codex.py 20261103_000020` | PID 11540, 실제 Python 자식 PID 26756; 이 세션의 `write_stdin` ID 6085 | `20261103_000016` | `RUNNING`, 확인 당시 `CARD_AI_CALL` 기록 0건. 모델 응답 대기 중인 것으로 보이나 외부 서버 상태는 미확인 |

이 명령은 기존 `ExtractionService.run`을 호출하는 **임시 단건 실행 스크립트**다. `TerraClient`, `gpt-6.1-terra`, 입력 추정 12,000, 출력 상한 16,000, 호출 timeout 180초, 예산 $1, 이전 DB 토큰 비용 반영 설정이다. timeout은 서버 측 청구 여부를 보장하지 않는다. 완료 시 stdout에 `RunResult`, 비용, `usage_uncertain`을 출력한다. 세션 ID는 현재 실행 환경 한정이며 다음 세션에서 유지된다고 보장할 수 없다. PID는 재사용될 수 있으니 명령줄을 함께 확인한다.

AMEX `AP003`, 문서 `20261103_000011`, run `20261103_000015`는 실행 중이었으나 15:10경 **SUCCEEDED**로 완료됐으며 프로세스가 종료됐다. 페이지 2/2, 비용 코드 기준 $0.110439. 이전에 실행하던 `common_auto_main` 프로세스는 종료됐고, Neo4j 로더와 A/B/C 조회 테스트도 종료됐다. 다른 Python 프로세스는 별도 작업일 수 있으므로 건드리지 않는다.

## 4. 파일과 작업 트리

`git status --short --untracked-files=all` 확인 결과:

| 파일 | 상태와 내용 |
|---|---|
| `src/card_benefit/payment_card/db_pipeline/common_benefit_service.py` | 수정: `brand_key` 추가. `UPI`, `UnionPay`, `유니온페이`를 동일 브랜드로 비교하고 등록·카드 적용에서 사용. 실제 UnionPay 후보가 DB 코드 `UPI`와 원문 `UnionPay`의 불일치로 차단된 오류를 해결하기 위한 범위 한정 수정 |
| `src/card_benefit/payment_card/tests/test_common_benefit.py` | 수정: 위 브랜드 별칭 테스트 추가. 관련 테스트 16건 통과 |
| `src/card_benefit/payment_card/db_pipeline/common_auto_main.py` | 미추적. 범위 변경 **이전에** 작성한 미완성 통합 CLI. 최신 지시는 통합 실행기 개발 중단이므로 사용·추가 개발하지 않는다. 이전 단일 문서 실행은 완료됨 |
| `src/card_benefit/payment_card/db_pipeline/common_auto_pipeline.py` | 미추적. 위 CLI의 미완성 연결 코드. 최신 지시상 사용하지 않는다 |
| `src/card_benefit/payment_card/tests/test_common_auto_pipeline.py` | 미추적. 범위 변경 이전 Mock 테스트. 위 미완성 실행기와 관련됨 |
| `src/card_benefit/payment_card/db_pipeline/auto_approval_policy.py`, `tests/test_auto_approval_policy.py` | 기존 파일, 현재 Git 추적 상태. 최신 지시에 따라 이 정책을 강제할 필요 없음 |
| `tmp/common_existing_extract_once_codex.py` | 단건 `ExtractionService.run` 호출용 임시 파일. **현재 Visa 프로세스가 사용하므로 삭제·수정하지 않는다.** |
| `tmp/common_stage_readonly_codex.py`, `tmp/handoff_state_codex.py`, `tmp/common_candidates_readonly_codex.py`, `tmp/card_query_three_modes_codex.py` | 운영 확인용 임시 파일. 앞의 두 파일은 DB 읽기 전용. `common_candidates_readonly_codex.py`는 현재 UP001 특정 후보만 출력하도록 되어 있음. GraphRAG 스크립트는 실제 유료 LLM·임베딩 호출을 하므로 재실행 시 비용 발생 |
| `src/card_benefit/docs/CARD_DATA_REGISTRATION_VALIDATION_DETAIL.md`, `CARD_GRAPHRAG_QUERY_VALIDATION_DETAIL.md` | 이전 요청에서 생성한 상세 문서. 보존한다 |
| `src/card_benefit/docs/CODEX_HANDOFF_20261103.md` | 본 인수인계 문서 |

임시 파일과 docs가 Git 상태에 보이지 않는 것은 ignore 등의 가능성이 있으며, 존재하지 않는다는 뜻이 아니다. 기존 사용자 파일과 미커밋 변경은 보존한다. 테스트 명령: `$env:PYTHONPATH='src;src/card_benefit'; .venv/Scripts/python -m pytest -p no:cacheprovider src/card_benefit/payment_card/tests/test_common_benefit.py -q`.

## 5. PostgreSQL 실제 반영 상태

공통 폴더 PDF 19개: 브랜드 안내 16개, 약관 3개. 브랜드 안내 중 파일명 `upi_premium_service_platinum_20190131`은 기존 파일명 규칙 불일치로 미등록. 약관 3개는 기존 등록기가 지원하는 문서 유형이 아니므로 미등록. **DB에 공통 안내서 15건**: 신규 14건과 기존 Visa Signature 1건. JCB `JP002`는 원문에 Platinum과 Prestige가 함께 나와 문서만 등록하고 공통서비스 연결은 보류. 문서 코드를 임의로 변경하지 않는다.

등록 후 문서별 페이지·청크·해시 검증 ERROR 0, 중복 문서 SHA/코드·공통 코드 0, 확인한 문서·페이지·청크 및 공통 적용 상위 관계 고아 0이었다. 당시 `v_card_integrity_issue` 35건은 모두 기존 `evidence_not_approved`; 승인을 일괄 변경하지 않았다. 그 후 추출이 진행되어 근거 수가 증가했으므로 현재 전체 경고 수는 재확인해야 한다.

15:10경 전체 DB 집계: `card_doc` 17, `card_doc_page` 37, `card_doc_chunk` 37, `card_common_bnft` 1, `card_extr_stg` 65, `card_source_evidence` 274, `card_ai_run` 9, `card_ai_call` 11. 추출이 진행 중이므로 수치는 바뀔 수 있다. 앞서 공통서비스 9개, `card_common_doc` 14개, 공통 혜택 적용 1개였다. 새 공통 혜택은 이번 처리에서 **0건**: 기존 Visa 컨시어지 1건이 전부다. 기존 Visa 실행 `20261102_000003`, 후보 `20261102_000017`을 `VISA_SIGNATURE_CONCIERGE`로 기존 서비스 재등록 시 `UNCHANGED`였다. 실제 UnionPay 등록 시도는 전부 `REVIEW`, INSERT 0건이다. 승인 상태를 임의로 변경하지 않았다.

## 6. 문서별 추출·후속 상태

| 문서 | 문서 ID | run / 추출 결과 | 혜택·후속 |
|---|---|---|---|
| `VS002_20260317` | `20261102_000004` | 기존 `20261102_000003` SUCCEEDED | Visa 컨시어지 1건 기존 등록·임베딩 있음. 재호출 불필요 |
| `AE001_20260305` | `20261103_000009` | `20261103_000012` PARTIAL, 1/3 성공 | 1·3쪽 `PARSE_ERROR`/`JSONDecodeError`, 출력 상한 8,000 도달. 병합 안 됨; 부분 후보·근거는 보존 |
| `AP002_20260305` | `20261103_000010` | `20261103_000013` PARTIAL, 1/2 성공 | 1쪽 `PARSE_ERROR`/`JSONDecodeError`, 출력 상한 8,000 도달. 병합 안 됨 |
| `UP001_20260324` | `20261103_000019` | `20261103_000014` SUCCEEDED, 1/1 | 혜택 후보 23건; 기존 서비스 등록 시도 모두 REVIEW, 0건 INSERT |
| `AP003_20260609` | `20261103_000011` | `20261103_000015` SUCCEEDED, 2/2 | 28개 정규화 후보; 등록·식별자·근거 검토 아직 하지 않음 |
| `VI001_20260317` | `20261103_000020` | `20261103_000016` RUNNING | 현재 진행 중. 결과 확인 전 재실행 금지 |
| `JP002_20260326` | `20261103_000012` | 미실행 | 공통서비스 연결 없음: 원문의 Platinum/Prestige 불일치 확인 필요 |
| `MP001`, `MP004`, `MW002`, `MW003`, `UD001`, `UD002`, `VP001_20230727`, `VP001_20260317` | `20261103_000013`~`000018`, `000021`, `000022` | 미실행 | 등록·추출·임베딩 미완료 |

15:10경 정규화 스테이징: `UP001`은 `LINK_REVIEW` 5, `NO_EVIDENCE` 17, `CONTRACT_INVALID` 1, 모두 `PENDING_REVIEW`; `AP003`은 `LINK_REVIEW` 1, `NO_EVIDENCE` 27, 모두 `PENDING_REVIEW`. 기존 Visa 후보는 `LINK_REVIEW` 1. 두 PARTIAL 문서의 저장된 페이지별 5개 후보는 병합 전이라 `stg_sql_check_cd`가 NULL이다. 기존 상품 문서에도 `NO_EVIDENCE`, `OK`, `VALUE_NOT_IN_QUOTE` 후보가 있으나 이번 공통 문서 결과와 혼동하지 않는다.

`UP001`의 예: 후보 `20261103_000028`의 인천공항 아메리카노 10% 인용은 있으나 `brand_txt=UnionPay`와 DB `brand_cd=UPI` 비교가 이전에 막혔다. 별칭 수정 후에는 `validity_period_txt`가 “이용기간 별도 표기한 경우 외에는 2026년 …”이어서 기존 `period()`가 안전하게 파싱하지 못해 REVIEW다. 조건부 기간의 예외를 버리고 날짜를 강제하지 않았다. 나머지 후보 중에는 규칙별 인용 없음, `UNKNOWN` 계산 방식, 조건 범위 미확정 등 실제 검토가 필요한 항목이 있다. `LINK_REVIEW`만으로 후보를 제거하지 말고 기존 `_candidate_problem`과 `_evidence_ids`의 판단을 따른다.

## 7. LLM·임베딩 비용과 재실행 위험

아래 금액은 코드의 Terra 토큰 단가(입력 $1/백만, 출력 $5/백만)로 계산한 추정이며 실제 청구액이 아니다.

| run | 입력 / 출력 토큰 | 추정 USD | 상태 |
|---|---|---:|---|
| `20261103_000012` | 20,897 / 21,154 | 0.126667 | PARTIAL |
| `20261103_000013` | 13,872 / 13,736 | 0.082552 | PARTIAL |
| `20261103_000014` | 6,939 / 14,629 | 0.080084 | SUCCEEDED |
| `20261103_000015` | 14,399 / 19,208 | 0.110439 | SUCCEEDED |
| `20261103_000016` | 미확인 | 미확인 | RUNNING; API 호출이 청구될 수 있으므로 무응답이라고 0원으로 단정하지 말 것 |

확정된 4개 합계 $0.399742. 이미 성공한 페이지가 있는 PARTIAL 문서도 전체 문서 추출을 재실행하면 기존 성공 페이지가 재호출될 수 있다. 기존 공통 전체 성공 실행의 재사용은 fingerprint와 호출·staging·근거 완전성 검증에 달려 있고, 모델·설정 변경 시 같은 문서라도 호출될 수 있다. `terra_main`의 단일 페이지 실행은 다른 페이지를 생략하므로 전체 성공 통합을 대체하지 않는다.

`embedding_main --table card_common_bnft` dry-run 결과 기존 공통 혜택 1건은 텍스트·벡터가 이미 있고 건너뜀 1; 전체 `card_bnft` 5건 및 공통 1건의 벡터 차원 오류 0. 신규 공통 혜택이 없으므로 이번에 새 임베딩을 만들지 않았다. 임베딩 API 비용은 GraphRAG B/C 질문 임베딩을 포함해 별도 미집계다.

## 8. Neo4j 및 실제 조회

기존 `neo4j_load_draft --apply --confirm APPROVED_DP_HANA_CARD`를 사용해 삭제 없는 MERGE로 노드 200·관계 263 커밋, `dp_` 제약 14개 확인했다. 그 후 AI 추출에서 근거가 추가되어 `neo4j_validate`가 기대 노드 247·관계 310 대비 실제 200·263, 각각 47개 누락으로 `ok=false`를 반환했다. 이 47건은 이후 저장된 원문 근거 및 연결이므로 최신 추출이 끝난 뒤 다시 미리보기·동기화·검증해야 한다. 검증은 문서 `20261103_000012`(공통 연결이 보류된 JCB)를 orphan으로 1건 보고했다. 이 점은 Neo4j 재적재만으로 해결했다고 주장하면 안 된다. 최신 추출이 계속 저장되고 있어 기대 건수는 더 늘 수 있다.

실제 GraphRAG 질문 `Visa 컨시어지 혜택을 알려줘`는 A/B/C 모두 ANSWERED, 각 근거 3건을 반환했다. 화면 검증 수준은 `NOT_CHECKED`이므로 문장 의미 검증까지 성공했다고 해석하면 안 된다. 다른 질문 `Visa Signature 컨시어지 서비스는 무엇인가요?`는 A/B가 답변 불가, C가 ANSWERED였다. 검색 품질은 질문 표현에 따라 차이가 있다. GraphRAG의 LLM 토큰 추정 비용은 호출별 출력에 기록됐으며 B/C 질문 임베딩 비용은 포함되지 않는다.

Neo4j 재동기화 전에는 기존 로더가 전체 스냅샷의 기존 노드 속성을 `MERGE`/설정하고 `CREATE CONSTRAINT IF NOT EXISTS`를 실행한다는 점을 확인한다. 삭제는 하지 않으며 stale 노드가 있으면 중단한다. 실행 중 PostgreSQL 추출이 있으면 로더 스냅샷 직후 새 데이터가 들어와 정합성 검증이 다시 어긋날 수 있다.

## 9. 우선순위와 재개 방법

1. **진행 중인 VI001 종료 확인**: 위 첫 명령과 DB run `20261103_000016`의 `card_ai_call` 및 `card_ai_run`을 읽는다. 실행 중이면 기다린다. 실패·통신 단절 또는 사용량 불명인 경우 자동 재시도하지 않고 비용과 상태를 확인한다. `RUNNING`만 남은 경우 프로세스 종료 여부와 호출 이력부터 확인하고, 사용자가 승인한 작업 범위 안에서 복구한다. 임의로 상태를 바꾸거나 데이터를 삭제하지 않는다.
2. **성공한 AP003과 UP001 후보를 검토**: 공통 식별자는 검토 가능한 업무 식별자여야 한다. 같은 이름·다른 문서 버전의 동일성을 단순히 가정하지 않는다. 기존 `CommonBenefitService.register_run()`은 `LINK_REVIEW`를 허용하지만 위치가 확인된 혜택·규칙·한도 근거, 브랜드·등급, 유효기간, 공통 문서 연결을 따로 검사한다. 승인과 등록은 구별한다. AP003의 검사·원문은 읽기 전용 SQL/기존 repository로 확인한다.
3. **남은 독립 공통 문서**: 기존 `ExtractionService.run`을 사용하고 상태·토큰을 문서별로 기록한다. `tmp/common_existing_extract_once_codex.py <card_doc_id>`는 단건 실행이며 실제 DB 쓰기와 유료 호출이다. 작업 시 모델·비용 제한을 확인한다. JCB 등급 연결은 확인 전 만들지 않는다. PARTIAL 재시도는 중복 호출 비용을 먼저 확인한다.
4. **등록 가능한 공통 혜택만 기존 서비스에 반영**: 실행 예 `benefit_main common --run-id <run_id> --identity <stg_id>=<검토한_업무식별자> --no-embed --apply`. `--no-embed`는 유료 임베딩을 분리하기 위한 선택이다. 이후 기존 `EmbeddingService`/`embedding_main`으로 신규 행을 동기화하고 실패 여부 확인. `--force`는 불필요한 재생성을 유발하므로 쓰지 않는다.
5. **모든 현재 실행 종료 후 Neo4j 미리보기·반영·검증**: `python -m card_benefit.payment_card.db_pipeline.neo4j_load_draft`는 preview, `--apply --confirm APPROVED_DP_HANA_CARD`는 쓰기, `python -m card_benefit.payment_card.db_pipeline.neo4j_validate`는 읽기 대조다. `.venv/Scripts/python` 사용, DB/Neo4j 연결과 대상 DB를 먼저 확인한다. JCB orphan을 포함한 검증 실패 사유는 남긴다.
6. **A/B/C 실제 조회와 다음 범위**: 기존 컨시어지 테스트를 증거로 기록하고, 새 혜택이 실제 등록·근거 연결된 경우 그 혜택으로 재검증한다. 이후 신용·체크카드는 해당 상품과 문서 연결을 확인한 뒤 확대한다. 약관을 상품설명서나 브랜드 문서로 임의 변환하지 않는다.

이 문서는 진행 상황 스냅샷이다. `SUCCEEDED` 추출만으로 혜택 등록, 원문 승인, 카드 적용, 임베딩, Neo4j 반영까지 끝났다는 뜻은 아니다.
