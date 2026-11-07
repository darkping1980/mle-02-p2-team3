# 10단계 우리카드 카드 키 `product_code`

PC: laptop

## 재현과 원인

- 기존 Woori 변환(`/tmp/pf-graph-woori-full`): 노드 4,439(Benefit 890, Condition 1,536, Limit 696, Target 1,317), 엣지 4,218, evidence 9,266, Card 0, OFFERS 0, `missing_product_key` 908.
- 기존 Hana 변환(`/tmp/pf-graph-hana-full`): 노드 5,748(Card 99), 엣지 7,956(OFFERS 2,924), evidence 11,287, invalid_rows 0. 기존 `pf_load_runs.csv`에서 `full_hana`, `gpt-6-luna`를 확인했다.
- 원인: 키 후보가 `CD_ID`, `PC_SEQ`, `디자인코드`, `모바일_CD_NO`만 포함해 Woori의 `product_ids.product_code`를 놓쳤다.

## 수정과 검증

- `product_code`를 기존 Hana 후보 순서를 유지한 채 마지막 후보로 추가했다. ID 규칙은 `card:<issuer>:<product_key>` 그대로다.
- 합성 회귀 테스트는 Hana 키, Woori `product_code`, 키 없음, 양쪽 키 존재 시 Hana 우선 순위를 확인한다. product_code 단독 테스트는 변경 전 누락으로 실패했고, 수정 후 표준 테스트에서 통과했다.
- 표준 테스트: 203 passed.
- Hana 재변환 비교와 Woori 재변환은 실행하지 않았다. `src/AGENTS.md`의 Codex 작업 공통 규칙 20항은 지시된 `~/pilot_work` 결과 폴더를 읽거나 쓰지 않도록 한다. 재변환 입력이 해당 경로이므로 변환 결과 및 after 집계는 미확인이다. 기존 Hana 기준 수치는 위와 같으며, 수정은 Hana 후보 순서를 바꾸지 않는다.
- 기존 Woori CSV 기준에는 Card 0, OFFERS 0, invalid_rows `missing_product_key` 908이 기록되어 있다. 변환을 다시 실행하지 않아 수정 후 수치는 미확인이다.
- Woori product_docs 메타데이터에서 빈 `product_ids` 행은 1개이며 `doc_role=unclassified`, relation도 `unclassified`다. 이 행은 수정 후에도 경고 대상이다. 기존 908건 경고를 `primary_guide`, `brand`, `shared_guide`, `unclassified`별로 집계할 추출 결과 입력은 읽지 않았으므로 분류 수는 미확인이다.
- `docs/작업이력/README.md`에 이 기록의 인덱스 행을 추가했다.

## 재변환 직접 확인 (Claude, 2026-11-04 16:5x)

Codex는 실데이터 재변환을 하지 못했으므로, 저(Claude)가 같은 입력으로 `export`를 다시 돌려 직접 확인했다(출력은 `/tmp`, 읽기 전용).

| 항목 | 우리카드 수정 전 | 우리카드 수정 후 | 하나카드 수정 후 |
|---|---:|---:|---:|
| 노드 | 4,439 | 4,561 | 5,748 |
| 카드 노드 | 0 | 122 | 99 |
| 엣지 | 4,218 | 5,173 | 7,956 |
| OFFERS 엣지 | 0 | 955 | 2,924 |
| 근거 | 9,266 | 9,266 | 11,287 |
| `invalid_rows` | `missing_product_key` 908 | 0 | 0 |
| 카드와 연결된 혜택 | 0 / 890 | 890 / 890 | 1,474 / 1,474 |

- **직접 확인:** 하나카드는 수정 전 기록(노드 5,748 / 엣지 7,956 / 근거 11,287 / 카드 99 / OFFERS 2,924)과 같아서 영향이 없다.
- **직접 확인:** 우리카드 혜택 890개가 모두 카드에 연결되고 경고가 0이다. 카드 122개에 OFFERS 955개가 걸려 있어 한 혜택이 여러 카드에 연결되는 경우가 있다.
- **추정:** 여러 카드에 연결되는 혜택은 공통 상품설명서와 브랜드 서비스 문서에서 나온 것으로 보인다(문서 역할별 집계는 하지 않았다).
- 남은 `missing_product_key` 경고는 0이므로 앞의 '빈 `product_ids` 1행은 경고로 센다'는 항목은 청크 연결 기준으로는 해당 행이 쓰이지 않았음을 뜻한다(추정).

## 상태

before commit
