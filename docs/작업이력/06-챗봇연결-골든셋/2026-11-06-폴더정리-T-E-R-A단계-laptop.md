# 2026-11-06 file_pipeline 폴더 정리 T·E·R·A 단계

- PC: laptop
- 확인: `hostname`과 `/etc/machine-id` 앞 8자가 `CLAUDE.local.md`의 HOST·MACHINE_ID_PREFIX와 일치함(직접 확인).
- 배경: 사용자가 "발표(2026-11-09 월 오후) 전 파일 이동 금지" 방침을 이번에 예외로 풀었다. 이유는 로직이 어떻게 도는지 폴더 구조로 읽기 쉽게 하기 위해서다.
- 앞선 이력: [extraction 폴더 정리 A·B](2026-11-06-extraction폴더정리-final채점결과-골든셋진단-laptop.md).

## 한 일

흐름 순서에 맞춰 `file_pipeline/` 아래 남은 평평한 모듈 8개를 하위 폴더로 옮기고, 임포트·테스트·노트북·README를 같은 단계에서 고쳤다. 이동은 `~/pilot_work/reorg/reorg.py`가 별도 작업 폴더에서 적용하고, 단계마다 한 커밋, 검증 통과 후 `--no-ff` 병합했다(푸시 안 함).

| 단계 | 병합 직전 → 병합 | 커밋 |
|---|---|---|
| T | 658910a → 0a88643 | 2a9c634 |
| E | 0a88643 → baaf144 | f2dd7c8, cd26ac6(보정) |
| R | baaf144 → 876fa6b | 6df9cd0 |
| A | 876fa6b → e5b12e0 | b0edae4 |
| U | 620ded8 → 아래 U 절 참고 | 아래 U 절 참고 |

- 이동 전후 구조와 모듈별 위치·설계 근거는 [구조 전후와 설계](../../설계/폴더구조-정리-전후와-설계.md)를 참고한다.
- 되돌리는 기준: 정리 시작 전 커밋 `658910a`.

## 실행한 검증과 결과

- 단계마다 컴파일, 관련 테스트, 옛 경로 grep(`docs/작업이력` 제외) 0건을 확인했다. 병합 후 최종 관련 테스트(chat·평가·extraction·graph·노트북 점검·chunking·doc_index·traceability) **391개 통과**.
- `python -m ...<이동 모듈> --help`가 되는 모듈(`doc_index.batch`, `chat.eval.value_conflicts`, `chat.answer.answer_eval`)은 성공을 확인했다.
- 독립 검증(Codex, 읽기 전용): E와 R은 실시했고 지적(E: 임포트 단순화·README 개수·테스트 로더 경로, R: README 안내 범위)을 반영했다. **A는 Codex 검증이 15분 제한에 걸려 출력 없이 끝났다.** 대신 참조 전부, 옛 경로, 이동 모듈 내부 경로(`answer_eval.ROOT`가 저장소 루트로 계산됨), `--help`, 임포트 스모크를 직접 확인했다. 같은 작성자의 확인이라 독립성은 약하다.

## 도구가 놓쳐서 수동으로 고친 것

`reorg.py`는 아래를 처리하지 못했다. 이후 이동 때 같은 문제가 반복된다.

- `from ..모듈 import`형 상대 임포트(T: `doc_index/batch.py`, R: `eval/entity_dup_probe.py`, A: `eval/latency_bench.py`·`fact_judge.py`·`golden_eval.py`).
- `from . import a, b`처럼 이동 대상과 아닌 것이 섞인 임포트(A: `fp_chat_patch.py`).
- 노트북 셀의 `import 모듈`(A: 노트북 3개, R: 1개).
- 테스트의 `importlib spec_from_file_location` 로더 탐색식이 단계마다 중첩 복제됨(E 병합본부터 두 겹이던 것을 R, A에서 한 줄로 정리).
- `sys.modules` 키를 가짜로 바꿔 두는 테스트(A: `test_file_pipeline_chat_answer_check.py`의 `answer.answer_check` 키 추가).
- 도구 쪽 수정: 대상 폴더에 `__init__.py`가 이미 있으면 덮어쓰지 않게 고쳤다(`doc_index/__init__.py` 설명문 보존). 백업 `reorg.py.pre-init-fix.bak`.

## 못 한 것과 남은 위험

- U 단계는 처음에는 보류했다가 같은 날 사용자 승인으로 적용했다(아래 U 절).
- 저장소 밖 `~/pilot_work/eval-assets/usage-guide-wip/make_csv.py`(두 사본)의 모듈 분류 목록에 옛 경로(`traceability`, `answer_eval`)가 남아 있다. 실행해 보지 않았다.
- (후속: 2026-11-07 00:05에 정리와 화면 분기가 합쳐진 상태로 실제 질의 1건을 돌려 통과했다. [화면 분기 이력](2026-11-06-화면분기-render접점-P1-P4-laptop.md)의 "후속 확인" 참고. 브라우저 모양은 미확인.) 정리 당시에는 실제 Streamlit 화면을 실행하지 않았다(`app_v2.py`, `run_fp_chat_v2.py`의 `answer.` 스크립트식 fallback 경로는 테스트와 임포트 스모크까지만 확인).
- 직접 확인하지 못한 것(추측): 노트북 셀을 실제로 실행했을 때의 동작. 노트북은 JSON 유효성과 점검 목록 테스트까지만 확인했다.
- 다른 PC나 팀원이 `file_pipeline`의 옛 모듈 경로를 임포트하고 있다면 깨진다. 팀원 코드는 읽지 않았다.

## Codex 인계 준비

Claude 한도가 끝나도 Codex가 이어받도록 개인 지침(`AGENTS.override.md`, 저장소 루트, `.git/info/exclude`로 제외)과 인계 문서(`~/pilot_work/reorg/HANDOFF-codex.md`)를 만들었다. Codex 샌드박스(`workspace-write`, 승인 없음)는 `.git`이 읽기 전용이라 커밋·병합이 안 된다는 것을 시험으로 확인했다. 파일 작업은 Codex, git은 사용자 또는 Claude로 나누기로 했다. 이 둘은 커밋하지 않는 개인 파일이다.

## U 단계 (후속)

- 도구가 `run_fp_chat_v2.py`의 `runpy` 경로, 테스트의 `from chat.ui_v2`·`app_v2.py` 경로, `ui_v2_check.ipynb`의 `from ui_v2`를 놓쳐 수동 수정했다. `app_v2.py`의 `HERE.parents[5]`(저장소 루트)와 `sys.path`(chat/, src/graphrag_chatbot)는 도구가 맞게 고쳤고, 위치 기준으로 직접 세어 확인했다.
- 새 `chat/ui/README.md`, `chat/README.md`·`file_pipeline/README.md` 갱신. 관련 테스트 391개 통과(화면 AppTest 7개 포함). Codex 독립 검증(읽기 전용)의 지적(지도·README 표현)을 반영했다.
- **실제 Streamlit 화면은 실행하지 않았다. 발표용 화면이므로 병합 후 사용자가 한 번 띄워 확인해야 한다.**
- 이동한 `app_v2.py`는 최상위 이름 `ui`, `rag`, `answer` 등을 `sys.path`로 만든다. 팀 호스트에서 같은 이름을 쓰면 충돌할 수 있다(설계 문서에 기록).

## 다음에 할 일

1. 사용자가 v2 화면을 실행해 확인한다(발표 전).
2. `make_csv.py` 옛 경로 갱신 여부 결정.
3. 도구의 약점(`from ..모듈`, 중첩 로더, 노트북 import) 보강 후 저장소 편입 검토.
4. Streamlit 탭 화면 분기 작업(`feat/streamlit-pipeline-split`)은 정리 후 기준 브랜치를 다시 정한다. 그 브랜치는 `port` 기반이라 이번 정리 결과가 없다.
5. 설계 진단에서 가장 위험하다고 나온 검색 안정성(시드 후보·탐색의 `ORDER BY` 부재, 20회 모두 40노드 포화)은 이번 정리와 별개로 남아 있다.
