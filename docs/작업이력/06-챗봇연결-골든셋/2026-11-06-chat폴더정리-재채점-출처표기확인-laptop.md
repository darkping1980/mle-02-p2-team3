# chat/ 폴더 정리(eval/·review/), 골든셋 보정 재채점, 출처 표기 확인

- 날짜: 2026-11-06
- PC: laptop
- 관련 커밋: `1a9c550`(이동), `d522139`(병합). 출처 표기 기능 `9a418f4`, 앞선 이력 [H1 기준선](2026-11-06-H1기준선-새run적재-거절판정수정-laptop.md)

## 한 일

1. **chat/ 평가·검수 모듈 13개를 하위 폴더로 이동**: `chat/eval/` 11개(golden_set, golden_sampler, golden_eval, retrieval_eval, eval_questions, seed_matcher, fact_judge, latency_bench, run_eval, entity_dup_probe, retrieval_stability)와 템플릿 CSV, `chat/review/` 2개(review_sheet, review_focus). 실행용 모듈(answer_eval, db_pool, fp_chat_patch 등 15개)은 `chat/`에 그대로 둔다.
2. **이동 도구**: 저장소 밖 `~/pilot_work/reorg/reorg.py`(`plan` → `apply` → `cleanup`). `apply`는 별도 git worktree에서만 동작하고 메인 작업 폴더는 건드리지 않는다. 이동표는 `reorg_plan.json`. 임포트는 AST로 고치고, 테스트 로더·`parents[N]` 깊이·`sys.path` 삽입·문서 경로는 규칙으로 고친다(작업이력 문서는 제외).
3. **README**: `chat/README.md`에서 이동 항목을 빼고 `chat/eval/README.md`, `chat/review/README.md`를 새로 만들었다.
4. **저장소 밖 스크립트 경로 갱신**: `~/pilot_work/reorg/fix_outside_scripts.sh apply` 로 `run_h1_*.sh`, `run_stability_ab.sh` 의 모듈 경로를 새 경로로 바꿨다.
5. **골든셋 보정 재채점**(사용자 실행, 챗봇 답변은 그대로, 기대 값 6문항만 보정한 입력): 3회 모두 **32/41(78.0%)**, 하나 71.4%(15/21), 우리 85.0%(17/20). 비용 약 0.005달러. 자동 판정이며 사람 확정 정답률이 아니다.
6. **출처 표기(`FP_SOURCE_LABEL=1`) 확인**(사용자 시험): SHOPPER 해외 호텔 할인 답변에 `(국제브랜드 공통 안내장(VISA))` 표기, "VISA 브랜드로 발급된 경우에만 적용", 브랜드별 구분이 나왔다. 그린카드 연회비 답변에는 표기가 붙지 않았다. 기본값은 아직 꺼짐.

## 검증 (직접 실행한 결과)

- 작업 폴더에서: 컴파일 통과, 표준 테스트 243 통과, 챗봇·평가 테스트 112 통과, 이동한 CLI `--help` 11/11 성공, 옛 경로 잔존 수정 대상 0건.
- 병합 후 메인에서 표준 테스트 243 통과.
- 테스트가 못 잡은 오류 1건을 직접 확인해 고쳤다: `run_eval` 의 `CHATBOT_DIR = HERE.parents[3]` 이 한 단계 깊어져 없는 경로를 가리킴 → `parents[4]`. 스크립트 규칙에 추가했다.
- `run_eval` 의 `REPO_ROOT = HERE.parents[5]` 는 원래부터 저장소의 한 단계 위 폴더를 가리킨다(기존 동작, 이번에 `parents[6]` 로 같은 폴더를 가리키게 유지). 바로잡을지는 별도 결정.

## 겪은 문제

- `cleanup` 을 병합 전에 실행해 브랜치가 지워졌고(이 때 바깥 스크립트는 이미 새 경로로 바뀜) 커밋 `1a9c550` 에서 브랜치를 되살려 병합했다. 병합 명령 순서를 `병합 → 스크립트 갱신 → cleanup` 으로 지켜야 한다.
- 병합이 사용자 미커밋 문서(코드흐름 한건따라가기)와 같은 파일을 건드려 막혔고, 줄이 겹치지 않음을 확인한 뒤 stash → 병합 → stash pop 으로 해결했다. 그 문서의 사용자 수정은 커밋하지 않았다.

## 못 한 것과 남은 위험

- `extraction/` 의 일회성 도구 정리는 이번 범위가 아니다.
- 데스크탑에서 옛 경로를 쓰는 개인 스크립트가 있으면 pull 후 따로 맞춰야 한다(추정: 있을 수 있음, 미확인).
- 재채점 78.0% 는 AI 판정이다. 사람이 확정한 정답률은 SHOPPER 4개 혜택 외에는 0건이다.
- 병합 시 `README ↔ 파일` 자동 동기 테스트는 없다(이번 README 는 손으로 맞춤).

## 다음에 할 일

1. 실패로 보이는 문항 사람 확인: G-H-A-04, G-W-A-12, G-H-A-09, G-H-A-02. G-W-A-02, G-H-A-10 은 골든 기대 값 검토 필요.
2. 출처 표기 기본값을 켤지 결정.
3. 실패 층 하나(생성 13, 검색 9, 추출 6 중)를 골라 작은 A/B.
4. 남은 실패 청크 3개(json_parse_failure) 재처리, `doc_index/`·`chunking/`·`ledger/` README.
