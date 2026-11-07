# extraction/ 폴더 정리(단계 A·B), final 39문항 채점 결과, 골든셋 진단

- 날짜: 2026-11-06
- PC: laptop
- 관련 커밋: 단계 A 병합 `75c2beb`(내용 `f23a5e0`·`a461700`), 단계 B 병합 `0750b75`(내용 `b1fffc9`·`e2408c8`)
- 앞선 이력: [PPT 요구사항 대조·Neo4j 적재·README 3개](2026-11-06-PPT요구사항대조-Neo4j적재-README3개-laptop.md)
- 사용자 결정: 발표 준비(11/9 오후)는 보류하고 폴더 정리를 먼저 끝낸다.

## 한 일

1. **`extraction/` 모듈 15개를 하위 폴더로 이동**(`extraction/` 직접 .py 는 `__init__` 포함 33개 → 18개).
   - `report/`(4): `ambiguity_report`, `full_run_report`, `item_loss_report`, `table_density_report`
   - `review/`(5): `empty_review`, `accuracy_review`, `review_auto_audit`, `review_sheet`, `review_tally`
   - `eval/`(6): `consensus`, `eval_runs`, `variance`, `enum_violation_report`, `label_eval`, `prompt_version_compare`
   - 단계 A 8개(보고·평가 의존 묶음), 단계 B 7개(검토표·평가). 핵심 실행 모듈(`schema`, `evidence`, `prompt`, `runner`, `batch`, `cli`, `pilot*` 등)은 옮기지 않았다.
2. **이동 도구 일반화**(저장소 밖 `~/pilot_work/reorg/reorg.py`): 계획 파일을 환경변수 `REORG_PLAN` 으로 고르고, 기준 폴더·단계에서 브랜치·작업 폴더·보고서 이름을 만든다. chat 용 기본 동작은 유지, 원본은 `reorg.py.chat-v1.bak`. 계획 파일 `plan-extraction-A.json`, `plan-extraction-B.json`. 진행 상태는 `STATE.md`.
3. **README 정리**: `extraction/README.md`·`file_pipeline/README.md` 표를 새 경로로 정정(도구는 표를 자동으로 고치지 않아 수동), 하위 폴더 README 3개 추가, `pilot_hana_15299/README.md` 추가(이동하지 않고 기록으로 보존).
4. **문서 상태 갱신**: `docs/프로젝트-지도.md` 9~11단계 행(구버전 dev 39·final 41, 82.9%, OCR 대기, 정규화 시작 전, Neo4j 샘플용을 현재 값으로)과 5절 열린 결정 2건, `docs/운영/그래프-런북.md` 6절(Neo4j 실제 적재 절차·건수), `notebooks/모듈-점검-목록.md` 의 `review_auto_audit` 행(`extraction_audit.ipynb` 에서 호출 확인).

## 직접 확인한 것

- 단계 A·B 모두 별도 git worktree 에서 도구가 적용한 뒤 Claude 가 독립 검증: 이동 모듈의 `Path(__file__).resolve().parents[6]` 가 저장소 루트(`pyproject.toml` 존재)를 가리킴(A 6곳, B 10곳), 이동한 15개 모듈과 `cli` 임포트 성공, 노트북 변경분의 JSON 유효·출력 셀 0, README 표와 실제 파일 일치.
- 단계 B 는 `chat/review/review_sheet.py` 와 이름이 같은 `extraction/review_sheet.py` 를 옮기므로 chat 테스트 112개와 `chat.review.review_sheet` 임포트를 따로 확인(통과).
- 메인 병합 후: 표준 테스트 243 통과, chat·평가 테스트 112 통과. 옛 경로 grep 은 작업이력 외 0건.
- 노트북 점검 목록: Codex 가 "여러 모듈이 어긋난다"고 했으나 이름 검색으로 대조한 결과 실제로 어긋난 것은 `review_auto_audit` 1건뿐(나머지 "예정" 모듈은 노트북이 실제로 없음).

## final 39문항 채점 결과 (한 번 실행, 보정 없는 원본 골든셋)

- 첫 시도는 `run_final_eval.sh` 를 두 터미널에서 동시에 실행해 `run1`·`run2` 파일이 손상(run1 7줄, run2 0줄)돼 폐기했다. 중복 실행 방지(잠금) 포함 `run_final_eval2.sh` 로 깨끗한 폴더에서 다시 실행해 3회 모두 39줄로 정상 완료. 결과: `~/pilot_work/final-eval2/`.
- **AI 판정 정답률(문항 내 모든 사실 일치): 21/39(53.8%), 24/39(61.5%), 24/39(61.5%)**, 평균 59.0%. 95% 구간(Wilson, 24/39 기준) 약 46~75%. 하나 7~9/19(37~47%), 우리 14~16/20(70~80%). 3회 모두 정답 20문항, 3회 모두 오답 12문항, 흔들림 7문항. 정답 없음 문항 거절 3/4.
- **같은 조건(보정 전 원본 골든셋) dev 와 비교**: dev 28~29/41(68.3~70.7%, 하나 13~15/21, 우리 14~15/20). 기대값 6문항을 보정한 dev 는 32/41(78.0%). 즉 final 은 dev 보다 약 11%p 낮고 차이는 **하나카드**에서 크다(우리카드는 비슷).
- **원인은 모른다**: 후보는 final 골든에도 기대값 결함이 있을 가능성(dev 에서는 기대값이 문장 조각인 문항이 약 17개), 하나카드 추출 공백, dev 에 맞춘 조정(기대값 보정·프롬프트 규칙)의 영향. final 의 틀린 문항은 개선에 쓰지 않았고 분석하지도 않았다(과적합 방지).
- 따라서 78.0% 를 일반화 성능처럼 말하면 안 된다. 발표 등에서는 "AI 판정, dev 원본 골든 약 70%, 보정 후 78%, final 약 59%, 사람 확정은 SHOPPER 4개 혜택뿐"으로 함께 표기한다.

## 골든셋 진단 (Codex 읽기 전용 조사, Claude 일부 확인)

- dev 오답 13개 문항 재분류(Codex): 답변 생성 3(G-H-B-04-v1, G-W-A-06, G-W-B-01), 카드 그래프에 기대 문자열 없음 8(G-H-A-02, G-H-A-04·v1, G-H-A-09, G-H-A-11·v1, G-W-A-12), 평가 신뢰성 2(G-W-A-02: 기대값 2자, G-H-A-10: 단어 중간 잘림). "그래프에 없음"은 해당 카드 노드에서 문자열을 그대로 못 찾았다는 뜻이며 원문에 없다는 확정이 아니다. 검색된 노드 ID 는 DB UUID 라서 CSV 노드 ID 와 겹침 0(Claude 확인) → 문항별 검색 성공 여부는 서브그래프 문자열 포함 여부로만 판단했다.
- 골든 기대값 결함: 변경표 기준 17 ID(잘림·분할) + 2자 기대값 2 ID, 한 질문에 여러 사실 14 ID, 변형 10 ID(독립 표본이 41보다 적음). 32/41 의 Wilson 95% 구간 63.3~88.0%(Claude 계산 확인).
- 개선 방향 우선순위(제안, 미실행): 1) 골든 수정·사람 확인(오답 13개 + 정답 표본 약 12개), 2) 카드 시드·hops 고정 / 다중 시드 병합, 3) 혜택별 조건·한도 묶음·v3 점검 문구, 4) 사람이 원문을 확인한 뒤 특정 청크 재추출. 성공 기준(제안): 기존 실패 ID 3개 이상이 3회 중 2회 이상 개선되고 정답 회귀 1개 이하(통계적 유의성 아님). 제안서: `~/pilot_work/eval-assets/golden-improve-proposal.md`.
- 비용 정정: 기록의 `cost_usd` 는 누적값이다. 챗봇 1문항 약 0.0018달러, dev 41문항×3회(챗봇+채점) 약 0.25달러, final 3회 약 0.22달러(실측 0.071~0.075 ×3 + 채점 약 0.008).

## 겪은 문제

- final 채점 중복 실행(위). 완료 알림 오해: 서브에이전트 래퍼 알림은 시작·종료 신호일 뿐 결과가 아니어서, Codex 작업 상태와 결과는 `codex-companion status/result` 로 직접 확인했다.
- 단계 B 병합이 한 번 거부됐다. 원인: 단계 B 가 사용자의 미커밋 문서(코드흐름 한건따라가기)의 85줄 경로도 고쳤고 로컬 수정(17·22·29줄)과 같은 파일이었음. 줄은 겹치지 않아 그 문서만 stash → 병합 → stash pop 으로 해결, 사용자 수정 3곳은 그대로 복원했다(커밋하지 않음).
- Neo4j: Browser 의 예전 결과 화면(167노드/210관계)이 남아 있어 한동안 적재 실패로 보였다. 새로 실행한 쿼리로 12,144/15,697 확인.

## 못 한 것과 남은 위험

- 골든 기대값 사람 확인과 final 이 낮은 원인 확인은 미실시(사용자 확인 대기). 새로 생긴 `docs/PDF_검수기준_정리.md` 는 이번 작업이 만든 파일이 아니라 건드리지 않았다.
- `~/pilot_work/`(53개 항목) 정리는 폴더 지도 README 와 이름 유지 방침만 정했고 아직 실행 전. 삭제는 하지 않는다.
- 이동한 모듈의 외부 참조(저장소 밖 `~/pilot_work/eval-assets/usage-guide-wip/` 의 스크립트 2개)는 갱신하지 않았다(미확인: 실행해 본 적 없음).
- 발표 준비(Neo4j 화면 캡처, 덱 갱신)는 보류 중.

## 다음에 할 일

1. 골든 기대값 사람 확인(8문항: G-H-A-04, G-H-A-09, G-H-A-02, G-H-A-10, G-W-A-12, G-W-A-02, G-W-B-03, G-H-B-15) 후 보정·재채점.
2. `~/pilot_work/` 폴더 지도 README 작성.
3. final 결과를 본 뒤 하나카드 추출 공백 여부 점검(개선에 쓰지 않고 원인 파악만).
4. 발표 준비 재개 여부 결정.
