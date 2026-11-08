# GraphRAG Prototype 50-question Evaluation and Comparison

## Run and judgment notes

- Prototype path: existing `interpret ? retrieve ? answer_prototype ? finish` graph. Interpret and Answer APIs and Neo4j Aura search were real; no Streamlit UI, Judge LLM, or `app_log` persistence was used.
- `answer_prototype` keeps the structured Answer LLM fields unchanged. `content_preserved=true` was recorded for every question that called Answer LLM; 10 questions did not call it (four used the existing programmatic annual-fee path and six had no selected benefit).
- CARD10-030 remains `JUDGMENT_HOLD` and is excluded from the 49-question accuracy denominator.
- Fact adjudication used unchanged VERIFIED Golden facts and their previously checked official PDF page/quote/hash references. PDF binaries were not present in this workspace, so no new visual PDF pass is claimed. No Judge LLM call was made.
- The raw execution JSON is `prototype_evaluation_50_20261107.json`; this is a separate adjudicated copy. Golden files were not changed. During evaluation the code hash was recorded; a Korean explanatory comment and an additional prompt-equality test were added after the run, without changing runtime logic.

## Accuracy summary

| Metric | Previous full pipeline | Prototype |
|---|---:|---:|
| CORRECT | 33 | 36 |
| PARTIAL | 9 | 7 |
| WRONG | 7 | 6 |
| EXECUTION_ERROR | 0 | 0 |
| JUDGMENT_HOLD | 1 | 1 |
| Accuracy (CORRECT / 49 VERIFIED) | 67.35% | 73.47% |

| Hop | Previous correct | Prototype correct | Prototype denominator | Prototype accuracy |
|---|---:|---:|---:|---:|
| 1-hop | 18 | 18 | 25 | 72.00% |
| 2-hop | 15 | 18 | 24 | 75.00% |

## Verification

- Related regression suite: 332 passed, 14 skipped, 32 subtests passed.
- Focused `test_card_graphrag.py`: 193 passed, 9 skipped.
- Python compilation: passed for the changed backend, evaluator, and test module.
- `git diff --check`: passed; Git printed only the existing CRLF/LF notice for the LangGraph guide.
- `full_vector` regression tests were included from `test_neo4j_origin_search.py` and `test_query_logger.py`.
- Prototype prompt and context equality against normal mode is covered by a regression test.

## API usage and latency

- Actual calls: 50 embedding, 50 Interpret LLM, 40 Answer LLM (90 LLM calls total).
- LLM tokens: 401,896 input and 16,452 output; provider-usage estimated cost $0.04642147.
- Embedding input was locally token-estimated at 1,763 tokens; estimated cost $0.00003526 at $0.02/1M. The current embedder does not return provider usage tokens.
- Combined estimated API cost: $0.04645673; per-question wall-time sum 304.17s (mean 6.08s).
- Costs are estimates from response usage and published embedding pricing; actual billing can vary. GPT-6 Luna project rates match the current [official pricing table](https://developers.openai.com/api/docs/pricing?tab=suite); `text-embedding-3-small` is listed at $0.02 per 1M tokens in the [official model page](https://developers.openai.com/api/docs/models/text-embedding-3-small). LLM outputs are nondeterministic, so this is a pipeline comparison, not a paired identical-output test.

## Changes against the previous adjudication

- Improved PARTIAL ? CORRECT: CARD10-008, CARD10-011, CARD10-034, CARD10-038, CARD10-040, CARD10-056.
- Previous CORRECT ? PARTIAL: CARD10-009, CARD10-015, CARD10-026.
- Previous WRONG ? PARTIAL: CARD10-032.
- Previous PARTIAL retained: CARD10-019, CARD10-024, CARD10-035.
- Previous WRONG retained: CARD10-001, CARD10-010, CARD10-020, CARD10-051, CARD10-058, CARD10-059.
- Other previous CORRECT remained CORRECT; CARD10-030 remained on hold.

### CARD10-032 and CARD10-056

- CARD10-032: prior normal pipeline was WRONG because Python validation reversed the Answer LLM meaning. Prototype no longer performs that rewrite; this run says the 4-PAY additional discount shares the online cap and requires 300,000 KRW previous-month spend. It omits the 5% rate, exact cap tiers, and Two-in-One exclusion. Evidence 20261104_001788 belongs to the other online-shopping benefit. Final: PARTIAL.
- CARD10-056: the original Answer LLM tier mapping is retained: 30?70?? ?? ? 6,000?; 70?120?? ?? ? 12,000?; 120?? ?? ? 24,000?, plus 50,000? per-transaction eligible amount at 10%. The normal validator had removed this mapping previously. Final: CORRECT.

## Search / Interpret / Answer findings

- CARD10-001: all four expected ONE PICK benefits were among the eight Hybrid candidates; Interpret selected none, so Retrieve/Answer did not run.
- CARD10-051: the top eight candidates did not include the account-eligibility item; Interpret selected none.
- CARD10-058: expected benefit `20261105_000104` was present in Hybrid candidates but Interpret selected none.
- CARD10-059: the JADE Classic voucher benefit was absent from the eight candidates.
- Programmatic annual-fee path: CARD10-002, CARD10-004, CARD10-024, CARD10-054 did not call Answer LLM. These remain included as end-to-end results, not as Answer LLM samples.
- CARD10-010 and CARD10-020 produced no answer and did not call Answer LLM; annual-fee candidate selection was not achieved.

## Per-question comparison

| ID | Hop | Question | Previous | Prototype | Answer LLM called | Evidence IDs cited | Prototype final answer |
|---|---|---|---|---|---:|---|---|
| CARD10-001 | 1-hop | ONE PICK STYLE 하나 체크카드에 등록된 주요 혜택을 알려줘. | WRONG | WRONG | no | ? | 이 개발 버전이 답할 수 없는 질문입니다. 등록된 카드 혜택의 내용·조건·한도·비교·원문 근거를 물어보세요. |
| CARD10-002 | 1-hop | ONE PICK STYLE 카드의 본인 연회비는 얼마야? | CORRECT | CORRECT | no | 20261104_001827 | 연회비<br>- ONE PICK STYLE 하나 체크카드 — 본인: 0원<br>연회비는 상품설명서에서 추출해 등록한 값이며 담당자 검토 전입니다. |
| CARD10-003 | 1-hop | JADE Classic 카드의 공항 라운지 혜택은 무엇이야? | CORRECT | CORRECT | yes | 20261105_002891, 20261105_002892, 20261105_002898, 20261105_002899, 20261105_002900, 20261105_002901, 20261105_002902, 20261105_002903 | JADE Classic은 전 세계 제휴 공항 라운지를 무료로 이용할 수 있으며, 본인·가족·동반자 통합 연 3회, 일 3회까지 제공됩니다. 1차년도에는 지난달 50만 원 이상, 2차년도 이후에는 서비스 제공 기간 직전 1년간 600만 원 이상 이용해야 하며, 최초 카드 사용 등록 후 다음 달 말일까지는 지난달 이용금액이 50만 원 미만이어도 이용할 수 있습니다. THE LOUNGE 앱에 카드를 등록해 이용권을 내려받고 라운지에서 여권과 탑승권을 제시해야 하며, 탑승자 이름·여권·앱 등록 영문명이 같아야 합니다. |
| CARD10-004 | 1-hop | JADE Classic의 브랜드별 연회비를 알려줘. | CORRECT | CORRECT | no | 20261104_001830, 20261104_001831, 20261104_001832 | 연회비<br>- JADE Classic — 본인 국내외겸용 (Visa, Mastercard, Amex): 120,000원(기본 20,000원 + 제휴 100,000원), 가족 국내외겸용 (Visa, Mastercard, Amex): 30,000원(기본 20,000원 + 제휴 10,000원), 본인 국내외겸용 (UPI): 115,000원(기본 20,000원 + 제휴 95,000원), 가족 국내외겸용 (UPI): 25,000원(기본 20,000원 + 제휴 5,000원), 본인 국내전용: 115,000원(기본 20,000원 + 제휴 95,000원), 가족 국내전용: 25,000원(기본 20,000원 + 제휴 5,000원)<br>연회비는 상품설명서에서 추출해 등록한 값이며 담당자 검토 전입니다. '검토 필요' 줄은 상품 브랜드 옵션 등이 확인되지 않아 확정하지 않았습니다. |
| CARD10-005 | 1-hop | JADE First에 골프 또는 프리미엄 아울렛 관련 혜택이 있어? | CORRECT | CORRECT | yes | 20261105_002448, 20261105_002453, 20261105_002454, 20261105_002457, 20261105_002458, 20261105_002459 | 네, JADE First에는 골프·프리미엄 아울렛 이용 시 50% 청구 할인 혜택이 있습니다. 서비스 실적 기간 내 2,400만원 이상 이용 시 할인 한도 10만원이 제공되고, 3,600만원 이상 이용 시에는 할인 한도 10만원이 추가 제공됩니다. 골프업종·골프연습장과 프리미엄 아울렛은 오프라인 결제만 해당하며, 카카오골프는 공식 홈페이지나 앱에서 골프장 예약 또는 골프용품을 결제한 경우에 해당합니다. |
| CARD10-006 | 1-hop | JADE First의 공항 라운지 혜택을 알려줘. | CORRECT | CORRECT | yes | 20261105_002471, 20261105_002479, 20261105_002481, 20261105_002482, 20261105_002483, 20261105_002484 | JADE First는 전 세계 공항 라운지를 본인·가족·동반자 통합으로 연 8회, 하루 3회까지 무료 이용하실 수 있습니다. 1차년도에는 지난달 100만 원 이상 이용해야 하며, 최초 카드 사용 등록 후 다음 달 말일까지는 지난달 이용액이 100만 원 미만이어도 제공됩니다. 이용 전 THE LOUNGE 앱에 카드를 등록해 이용권을 내려받고, 제휴 라운지에서 여권과 탑승권을 제시하셔야 하며 이름도 앱 등록 영문명과 일치해야 합니다. |
| CARD10-007 | 1-hop | JADE Prime의 공항 라운지 혜택은 무엇이야? | CORRECT | CORRECT | yes | 20261105_002599, 20261105_002605, 20261105_002607, 20261105_002610, 20261105_002611, 20261105_002613, 20261105_002614 | JADE Prime은 전 세계 공항 라운지를 본인·가족·동반자 통합 연 6회, 일 3회까지 무료로 이용할 수 있습니다. 이용하려면 THE LOUNGE 앱에 카드를 등록해 이용권을 다운로드하고, 국내외겸용 카드로 발급받아야 하며 국내전용 카드 보유 회원은 제외됩니다. 1차년도에는 지난달 100만 원 이상 이용해야 하고, 최초 카드 사용 등록 후 다음 달 말일까지는 지난달 이용금액이 100만 원 미만이어도 제공되며, 2차년도 이후에는 서비스 제공 기간 직전 1년간 1,200만 원 이상 이용해야 합니다. |
| CARD10-008 | 1-hop | JADE Prime의 기본 적립 혜택을 알려줘. | PARTIAL | CORRECT | yes | 20261105_002659, 20261105_002660, 20261105_002661 | JADE Prime의 기본적립은 지난달 1일부터 말일까지 200만원 이상 이용하시면 1.5% 하나머니를 적립해 드립니다. 이용 횟수나 적립 한도는 검색 결과에 안내되어 있지 않습니다. |
| CARD10-009 | 1-hop | 더 심플 하나카드의 월납 요금 청구할인 혜택을 알려줘. | CORRECT | PARTIAL | yes | 20261105_002681, 20261105_002682, 20261105_002683, 20261105_002684, 20261105_002685, 20261105_002687, 20261105_002688, 20261105_002689 | 더 심플 하나카드의 월납 요금 청구할인은 대상 가맹점에 자동납부하면 지난달 이용금액 30만원 이상 80만원 미만일 때 월 10,000원, 80만원 이상일 때 월 15,000원까지 할인됩니다. 횟수 제한 없이 월 할인 한도 내에서 합산 할인되며, 월납 요금 승인 금액이 할인 한도보다 적으면 승인 금액만큼 할인됩니다. |
| CARD10-010 | 1-hop | 더 심플 하나카드의 연회비를 알려줘. | WRONG | WRONG | no | ? | 이 개발 버전이 답할 수 없는 질문입니다. 등록된 카드 혜택의 내용·조건·한도·비교·원문 근거를 물어보세요. |
| CARD10-011 | 1-hop | 카드의정석 SHOPPING의 온라인 쇼핑 관련 혜택을 알려줘. | PARTIAL | CORRECT | yes | 20261104_001710, 20261104_001712, 20261104_001713, 20261104_001715, 20261104_001724, 20261104_001726, 20261104_001729, 20261104_001730, 20261104_001785, 20261104_001786, 20261104_001799 | 온라인 쇼핑은 10% 청구할인으로, 전월 국내 가맹점 이용금액에 따라 월 할인한도가 30만원 이상~70만원 미만이면 4천원, 70만원 이상~120만원 미만이면 8천원, 120만원 이상이면 1만6천원입니다. 온라인 업종에서 삼성페이·네이버페이·카카오페이·PAYCO에 카드를 등록해 결제하면 전월 이용금액 30만원 이상부터 5% 추가할인이 적용되어 총 15% 할인되며, 이때 최대 할인액은 7,500원입니다. Two-in-One 결제서비스의 체크매출로 이용하면 온라인 업종에서 0.3% 캐시백을 받을 수 있습니다. |
| CARD10-012 | 1-hop | 카드의정석 SHOPPING에 Two-in-One 서비스가 있어? | CORRECT | CORRECT | yes | 20261104_001757, 20261104_001758 | 네, 카드의정석 SHOPPING에는 Two-in-One 결제서비스가 있습니다. 사전에 지정한 금액 이하는 체크로 결제하고, 초과분은 신용으로 결제하는 서비스입니다. |
| CARD10-013 | 1-hop | EVERY WON POINT의 국내외 가맹점 기본 적립 혜택을 알려줘. | CORRECT | CORRECT | yes | 20261105_002776, 20261105_002778, 20261105_002779 | EVERY WON POINT는 국내외 가맹점에서 0.8% 적립됩니다. 전월 실적 조건이 없으며, 기본 적립의 월 적립 한도도 없습니다. |
| CARD10-014 | 1-hop | EVERY WON POINT의 가족카드 연회비 정책을 알려줘. | CORRECT | CORRECT | yes | 20261105_002773 | EVERY WON POINT는 가족카드 연회비를 청구하지 않습니다. |
| CARD10-015 | 1-hop | 카드의정석 POINT II의 간편결제 추가 적립 혜택을 알려줘. | CORRECT | PARTIAL | yes | 20261105_002734, 20261105_002738, 20261105_002739, 20261105_002740, 20261105_002741, 20261105_002742, 20261105_002744, 20261105_002745, 20261105_002746, 20261105_002747, 20261105_002748, 20261105_002749 | 네이버페이·카카오페이·PAYCO·SSGPAY에 카드를 등록해 온라인 또는 오프라인에서 결제하면 3% 추가 적립됩니다. 전월 국내 가맹점 이용실적에 따라 30만원 이상이면 월 1만원, 60만원 이상이면 월 2만원, 120만원 이상이면 월 5만원까지 적립되며, 여러 구간에 해당할 때 적용 구간은 확정되지 않았습니다. |
| CARD10-016 | 1-hop | 카드의정석 POINT II의 Two-in-One 서비스를 설명해 줘. | CORRECT | CORRECT | yes | 20261105_002751 | 카드의정석 POINT II의 Two-in-One 결제서비스는 미리 지정한 금액까지는 체크로 결제하고, 그 금액을 초과하는 부분은 신용으로 결제하는 서비스입니다. 검색 결과에는 지정 금액이나 이용 횟수·한도는 나와 있지 않습니다. |
| CARD10-017 | 1-hop | 카드의정석2 DAILY의 고정소비 할인 혜택이 뭐야? | CORRECT | CORRECT | yes | 20261105_003031 | 카드의정석2 DAILY의 고정소비 할인은 음식점·배달앱·온라인/오프라인 장보기·다이소·택시·주유·통신요금 대상 결제에 5% 청구할인입니다. 전월 실적 50만원 이상이 필요하며, 고정소비 할인 한도는 전월 실적 50만원 이상 100만원 미만이면 월 3,000원, 100만원 이상 200만원 미만이면 월 6,000원, 200만원 이상이면 월 12,000원입니다. 음식점·배달앱·온라인/오프라인 장보기·택시·주유·통신요금은 건당 3만원 이상 결제해야 하고, 다이소는 건당 조건이 없습니다. |
| CARD10-018 | 1-hop | 카드의정석2 DAILY의 정기결제 혜택이 뭐야? | CORRECT | CORRECT | yes | 20261105_002838, 20261105_002839, 20261105_002841, 20261105_002843, 20261105_002844, 20261105_002845, 20261105_003034 | 넷플릭스, 유튜브 프리미엄, 티빙, 디즈니플러스, T우주패스 정기결제에 50% 청구할인을 제공합니다. 전월 실적 50만 원 이상이고 공식 홈페이지나 앱에 카드를 등록해 정기결제해야 하며, 정기결제 할인 한도는 월 5,000원입니다. 간편결제·인앱결제는 제외되며, 고정소비 할인과의 통합 월 한도는 전월 실적 50만 원 이상 100만 원 미만일 때 8,000원, 100만 원 이상 200만 원 미만일 때 11,000원, 200만 원 이상일 때 17,000원입니다. |
| CARD10-019 | 1-hop | 카드의정석2 SIMPLE의 기본 할인 혜택을 알려줘. | PARTIAL | PARTIAL | yes | 20261105_002762, 20261105_002765, 20261105_002766, 20261105_002767, 20261105_002768 | 국내외 가맹점 청구할인은 0.8% 또는 0.3%이며, 두 금액 중 어떤 할인율이 적용되는지는 아직 확정되지 않았습니다. 전월 실적 조건은 없고 할인 한도 제한도 없습니다. 0.3% 할인은 국내 체크 매출에 Two-in-One 결제서비스를 이용할 때 적용됩니다. |
| CARD10-020 | 1-hop | 카드의정석2 SIMPLE의 연회비를 알려줘. | WRONG | WRONG | no | ? | 이 개발 버전이 답할 수 없는 질문입니다. 등록된 카드 혜택의 내용·조건·한도·비교·원문 근거를 물어보세요. |
| CARD10-021 | 2-hop | ONE PICK STYLE의 편의점·카페 캐시백은 결제금액과 이용 횟수에 어떤 조건이 있어? | CORRECT | CORRECT | yes | 20261101_000032, 20261101_000033, 20261101_000036, 20261101_000037, 20261107_003042 | ONE PICK 편의점·카페 캐시백은 CU·GS25·세븐일레븐과 메가MGC커피·이디야커피·컴포즈커피에서 건당 3천 원 이상 결제하면 100원 캐시백을 받을 수 있습니다. 이용은 일 1회, 월 30회까지이며 월 캐시백 한도는 5천 원입니다. |
| CARD10-022 | 2-hop | ONE PICK STYLE의 STYLE 영역 캐시백을 받으려면 어떤 대상 가맹점과 한도 조건을 만족해야 해? | CORRECT | CORRECT | yes | 20261101_000039, 20261101_000042, 20261101_000043, 20261107_003043 | ONE PICK STYLE의 STYLE 영역 캐시백 대상 가맹점은 다이소, 올리브영, 교보문고, 영풍문고, 알라딘, yes24, 아트박스, 무신사, 에이블리입니다. 대상 가맹점에서 건당 1만원 이상 결제하면 500원을 캐시백 받으며, 이용 횟수는 일 1회·월 10회, 한도는 월 5천원입니다. |
| CARD10-023 | 2-hop | JADE Classic의 공항 라운지는 연간 몇 회, 하루 몇 회 이용할 수 있어? | CORRECT | CORRECT | yes | 20261105_002891 | JADE Classic 공항 라운지는 본인·가족·동반자 통합으로 연 3회, 하루 3회 이용할 수 있습니다. |
| CARD10-024 | 2-hop | JADE Classic의 연회비는 카드 브랜드와 가족카드 여부에 따라 어떻게 달라져? | PARTIAL | PARTIAL | no | 20261104_001830, 20261104_001831, 20261104_001832 | 연회비<br>- JADE Classic — 가족 국내외겸용 (Visa, Mastercard, Amex): 30,000원(기본 20,000원 + 제휴 10,000원), 가족 국내외겸용 (UPI): 25,000원(기본 20,000원 + 제휴 5,000원), 가족 국내전용: 25,000원(기본 20,000원 + 제휴 5,000원)<br>연회비는 상품설명서에서 추출해 등록한 값이며 담당자 검토 전입니다. '검토 필요' 줄은 상품 브랜드 옵션 등이 확인되지 않아 확정하지 않았습니다. |
| CARD10-025 | 2-hop | JADE First 공항 라운지의 본인·가족·동반자 통합 이용 횟수는 어떻게 돼? | CORRECT | CORRECT | yes | 20261105_002471, 20261105_002479, 20261105_002480, 20261105_002481 | JADE First 공항 라운지는 본인·가족·동반자 이용을 합산해 연 8회, 하루 3회까지 이용할 수 있습니다. 1차년도에는 지난달 이용금액 100만 원 이상, 2차년도 이후에는 서비스 제공 기간 직전 1년간 1,200만 원 이상 이용해야 하며, 최초 카드 사용 등록 후 다음 달 말일까지는 지난달 이용금액이 100만 원 미만이어도 제공됩니다. |
| CARD10-026 | 2-hop | JADE First의 제휴 주차장 무료 주차는 전월 실적과 월 이용 횟수 조건이 어떻게 돼? | CORRECT | PARTIAL | yes | 20261105_002528, 20261105_002529, 20261105_002530 | JADE First 제휴 주차장 무료 주차는 지난달 1일부터 말일까지 50만 원 이상 이용하면 제공되며, 본인·가족 통합 월 2회까지 이용할 수 있습니다. 최초 카드 사용 등록 후 다음 달 말일까지는 지난달 이용금액이 50만 원 미만이어도 제공되며, 무료 주차는 1일 기준입니다. |
| CARD10-027 | 2-hop | JADE Prime의 공항 라운지 무료 이용 횟수 제한을 알려줘. | CORRECT | CORRECT | yes | 20261105_002599, 20261105_002605 | JADE Prime의 전세계 공항 라운지 무료 이용은 본인·가족·동반자 통합 연 6회, 일 3회까지입니다. 국내외겸용카드 발급 시 제공됩니다. |
| CARD10-028 | 2-hop | JADE Prime에서 기본 1.5% 적립을 받기 위한 지난달 이용 실적 조건은? | CORRECT | CORRECT | yes | 20261105_002659 | JADE Prime의 기본적립은 지난달 1일부터 말일까지 200만원 이상 이용하시면 1.5% 하나머니를 적립해 드립니다. |
| CARD10-029 | 2-hop | 더 심플 하나카드의 월납 요금 할인 한도는 지난달 이용액 구간에 따라 어떻게 달라져? | CORRECT | CORRECT | yes | 20261105_002681, 20261105_002682, 20261105_002685, 20261105_002686 | 지난달 이용액이 30만원 이상 80만원 미만이면 월 할인 한도는 10,000원이고, 80만원 이상이면 15,000원입니다. |
| CARD10-030 | 2-hop | 더 심플 하나카드의 월납 요금 할인 대상과 제외되는 결제 방식이 무엇인지 확인해 줘. | JUDGMENT_HOLD | JUDGMENT_HOLD | yes | 20261105_002681, 20261105_002682, 20261105_002683, 20261105_002684, 20261105_002685, 20261105_002688, 20261105_002689 | 월납 요금 청구할인은 국내 대상 가맹점에서 자동납부할 때 적용되며, 통신(SKT·KT·LG U+·SK브로드밴드 및 기재된 알뜰폰 사업자), 렌탈(코웨이·LG전자·SK인텔릭스), 기타 월납서비스(유튜브 프리미엄·넷플릭스·디즈니플러스·스카이라이프·HCN)가 대상입니다. 지난달 이용금액이 30만원 이상 80만원 미만이면 월 10,000원, 80만원 이상이면 월 15,000원까지 할인되며 횟수 제한 없이 월 한도 내에서 합산 할인됩니다. 자동납부 결제가 불가능한 사유가 발생하면 할인을 받을 수 없습니다. |
| CARD10-031 | 2-hop | 카드의정석 SHOPPING의 온라인 쇼핑 할인 대상과 전월 실적 조건은 무엇이야? | CORRECT | CORRECT | yes | 20261104_001710, 20261104_001712, 20261104_001785, 20261104_001786, 20261104_001788 | 온라인 쇼핑은 인터넷 P/G, 인터넷 상거래 등 온라인 업종에서 10% 청구할인됩니다. 전월 국내 가맹점 이용금액이 30만원 이상 70만원 미만이면 온라인 월 할인한도는 4천원, 70만원 이상 120만원 미만이면 8천원, 120만원 이상이면 1만6천원이며, 온라인 4대 PAY 추가할인과 온라인 업종 통합 할인한도를 공유합니다. 최초 사용등록 후 실적 유예가 이 혜택에도 적용되는지는 확인되지 않았습니다. |
| CARD10-032 | 2-hop | 카드의정석 SHOPPING의 4대 PAY 추가 할인은 기본 할인과 한도를 공유하니? | WRONG | PARTIAL | yes | 20261104_001728, 20261104_001729, 20261104_001788, 20261104_001798 | 네, 4대 PAY 추가 할인은 온라인 쇼핑 기본 할인과 온라인 업종 통합 월 할인한도를 공유하며 별도 추가 월 한도는 없습니다. 전월 국내 가맹점 이용금액 30만원 이상이어야 할인받을 수 있습니다. |
| CARD10-033 | 2-hop | EVERY WON POINT의 국내외 기본 포인트 적립에는 전월 실적이나 월 적립한도가 있어? | CORRECT | CORRECT | yes | 20261105_002778, 20261105_002779 | EVERY WON POINT의 국내외 기본 포인트 적립은 전월 실적 조건이 없고, 월 적립한도도 제한 없습니다. |
| CARD10-034 | 2-hop | EVERY WON POINT 가족카드 연회비 면제에는 확인해야 할 적용 조건이 있어? | PARTIAL | CORRECT | yes | 20261105_002773 | EVERY WON POINT 가족카드 연회비 면제는 가족카드 연회비를 청구하지 않는 혜택입니다. 별도로 확인해야 할 적용 조건은 검색 결과에 없습니다. |
| CARD10-035 | 2-hop | POINT II 간편결제 추가 적립의 전월 실적 구간별 통합 월 한도를 알려줘. | PARTIAL | PARTIAL | yes | 20261105_002739, 20261105_002740, 20261105_002741, 20261105_002742, 20261105_002744, 20261105_002745, 20261105_002746 | 전월 국내 가맹점 이용실적이 30만원 이상이면 통합 월 적립 한도는 1만원, 60만원 이상이면 2만원, 120만원 이상이면 5만원입니다. |
| CARD10-036 | 2-hop | POINT II의 Two-in-One 결제서비스가 적용되는 결제 유형과 조건을 알려줘. | CORRECT | CORRECT | yes | 20261105_002751 | POINT II의 Two-in-One 결제서비스는 결제 금액 중 사전에 지정한 금액 이하는 체크로, 초과분은 신용으로 결제하는 서비스입니다. 검색 결과에는 결제 유형 외의 추가 조건은 확인되지 않습니다. |
| CARD10-037 | 2-hop | 카드의정석2 DAILY의 고정소비·정기결제 할인은 통합 한도를 공유해? | CORRECT | CORRECT | yes | 20261105_003031, 20261105_003034 | 네, 고정소비 할인과 정기결제 할인은 통합 할인한도를 공유합니다. 전월 실적 50만원 이상 100만원 미만이면 통합 한도는 8,000원, 100만원 이상 200만원 미만이면 11,000원, 200만원 이상이면 17,000원입니다. |
| CARD10-038 | 2-hop | 카드의정석2 DAILY 배달앱 할인은 어느 결제에 적용되고 어떤 실적 조건이 있어? | PARTIAL | CORRECT | yes | 20261105_002826, 20261105_003031 | 배달의민족·쿠팡이츠·요기요 공식 앱에서 입점 음식점의 음식·음료를 주문하고 앱 내 카드결제로 건당 3만원 이상 결제하면 5% 청구할인을 받을 수 있습니다. 전월 실적이 50만원 이상이어야 하며, 월 할인한도는 전월 실적 50만원 이상 100만원 미만이면 3,000원, 100만원 이상 200만원 미만이면 6,000원, 200만원 이상이면 12,000원입니다. 멤버십·테이블 오더·물품 구매와 현장 카드결제는 할인 대상이 아닙니다. |
| CARD10-039 | 2-hop | 카드의정석2 SIMPLE의 국내외 결제 기본 할인에서 제외되는 거래 유형은? | CORRECT | CORRECT | yes | 20261105_002769, 20261105_002770, 20261105_002772 | 국내외 결제 기본 할인에서 제외되는 거래는 무이자할부, 정부지원금, 아파트 관리비·공공임대료·부동산임대료, 학교 납부금·대학 등록금, 세금과 공공요금, 상품권·선불카드·기프트카드 구매 및 충전, 환금성 업종, 교통카드 구매 및 충전, 시외·고속버스, 각종 수수료·이자, 연회비, 현금서비스·카드론, 매출 취소, 신차 구매, 의약품 전용몰·제약회사 업종입니다. 공공요금에는 4대 보험료, 전기·우편·도시가스·상하수도 요금, 과태료·범칙금·벌금, 여권 발급 비용과 국가·공공기관·공공단체 가맹점 이용금액이 포함됩니다. 할인 및 제외 업종·가맹점은 우리카드 전산상 등록 기준입니다. |
| CARD10-040 | 2-hop | 카드의정석2 SIMPLE의 Two-in-One 결제 시 할인율과 기본 할인 조건은 어떻게 달라져? | PARTIAL | CORRECT | yes | 20261105_002762, 20261105_002766, 20261105_002767, 20261105_002768 | 기본 국내외 가맹점 할인은 0.8% 청구할인이며, 전월실적 조건은 없습니다. Two-in-One 결제서비스로 국내 체크 매출을 이용하면 0.3% 청구할인이 적용되며, 이 경우에도 전월실적 조건은 없습니다. 할인 한도는 제한이 없습니다. |
| CARD10-051 | 1-hop | ONE PICK STYLE 체크카드의 결제계좌는 어느 은행 계좌를 사용해야 해? | WRONG | WRONG | no | ? | 이 개발 버전이 답할 수 없는 질문입니다. 등록된 카드 혜택의 내용·조건·한도·비교·원문 근거를 물어보세요. |
| CARD10-052 | 1-hop | 카드의정석 SHOPPING의 주말 주유 청구할인 금액은 얼마야? | CORRECT | CORRECT | yes | 20261104_001732, 20261104_001735, 20261104_001736, 20261104_001738 | 주말에 4대 주유소에서 주유하면 리터당 60원 청구할인됩니다. 전월 국내 가맹점 이용금액이 30만원 이상이어야 하며, 주유 매출 건당 10만원까지 적용되고 통합 월 한도는 30만원입니다. |
| CARD10-053 | 1-hop | 카드의정석 POINT II의 가족카드 연회비 정책은 어떻게 돼? | CORRECT | CORRECT | yes | 20261105_002754 | 카드의정석 POINT II는 가족카드 연회비를 청구하지 않습니다. |
| CARD10-054 | 1-hop | 카드의정석 SHOPPING의 브랜드별 연회비는 얼마야? | CORRECT | CORRECT | no | 20261104_001835, 20261104_001836, 20261104_001837 | 연회비<br>- 카드의정석 SHOPPING — 본인 해외겸용 (Mastercard, VISA): 12,000원(기본 5,000원 + 제휴 7,000원), 본인 국내전용 (UnionPay): 10,000원(기본 5,000원 + 제휴 5,000원), 가족: 0원<br>연회비는 상품설명서에서 추출해 등록한 값이며 담당자 검토 전입니다. '검토 필요' 줄은 상품 브랜드 옵션 등이 확인되지 않아 확정하지 않았습니다. |
| CARD10-055 | 1-hop | 카드의정석2 DAILY의 국내외 가맹점 기본 할인은 얼마야? | CORRECT | CORRECT | yes | 20261105_002798, 20261105_002802, 20261105_002803 | 국내외 가맹점에서 1% 청구할인됩니다. 매출 건당 1만 원 이상 결제해야 하며, 전월 실적 조건과 할인 한도 제한은 없습니다. |
| CARD10-056 | 2-hop | 카드의정석 SHOPPING 오프라인 쇼핑은 전월 실적 구간별 월 한도와 건당 할인 대상 금액 한도가 어떻게 돼? | PARTIAL | CORRECT | yes | 20261104_001717, 20261104_001790, 20261104_001791, 20261104_001793 | 전월 국내 가맹점 이용금액이 30만 원 이상 70만 원 미만이면 월 6천 원, 70만 원 이상 120만 원 미만이면 월 1만 2천 원, 120만 원 이상이면 월 2만 4천 원까지입니다. 건당 할인 대상 금액은 최대 5만 원이며, 그 금액에 10% 할인이 적용됩니다. |
| CARD10-057 | 2-hop | JADE Prime에서 월 적립 한도 소진 후의 1.0% 적립은 어떤 조건으로 적용돼? | CORRECT | CORRECT | yes | 20261105_002662 | 기본적립, 특별적립, 주유/EV충전 적립, 택시 50% 적립, 디지털콘텐츠 50% 적립의 월 적립 한도를 모두 소진한 뒤 발생하는 추가 매출에 1.0% 하나머니를 적립해 드립니다. |
| CARD10-058 | 2-hop | EVERY WON POINT의 국내 온라인 간편결제 추가 적립 대상과 전월 실적·월 한도는 어떻게 돼? | WRONG | WRONG | no | ? | 질문 대상이 모호합니다: EVERY WON POINT의 국내 온라인 간편결제 추가 적립 혜택이 목록에 없습니다. 목록의 국내외 가맹점 기본 적립은 질문의 추가 적립 대상·조건·한도를 직접 뒷받침하지 않습니다. |
| CARD10-059 | 2-hop | JADE Classic 프리미엄 바우처는 몇 회 선택할 수 있고, 1차년도와 이후 연도의 실적 조건은 어떻게 돼? | WRONG | WRONG | no | ? | 질문 대상이 모호합니다: 목록에 JADE Classic의 프리미엄 바우처 혜택 후보가 없습니다. 라운지 혜택의 연도별 실적 조건은 있으나, 바우처 선택 횟수와는 직접 관련이 불분명합니다. |
| CARD10-060 | 2-hop | ONE PICK STYLE의 놀이공원 현장할인에 필요한 전월 실적과 월·연 이용 횟수는 어떻게 돼? | CORRECT | CORRECT | yes | 20261101_000053, 20261101_000054, 20261101_000055 | ONE PICK STYLE의 놀이공원 현장할인은 지난달 실적 20만원 이상일 때 이용할 수 있습니다. 월 1회, 연 2회까지 가능하며, 최초 발급 월에는 제공되지 않습니다. |

## Evidence check and limitations

- Citation IDs had a resolvable retrieved or previously verified Golden PDF record for 42 rows; 7 have absent or misowned citations; 1 is held.
- CARD10-032 has a point citing 20261104_001788, whose actual owner is `card_product_item:6:20261104_000013`; the point names `card_product_item:6:20261104_000017`. Other cited 4-PAY evidence is correctly linked.
- CARD10-039 TERMS evidence 20261105_002769/002770 appears in the answer and Golden PDF citation rows, but the runner flat projection omitted document/chunk metadata; the adjudicated copy enriches it from the Golden record.
- Raw-run flat `pdf_evidence` lacks document/title/file/chunk for many rows. The adjudicated JSON enriches it from detailed relationship retrieval or unchanged Golden citation metadata.
- Official PDF binaries were absent from the active workspace; the existing Golden PDF SHA-256/page/quote references were preserved. This report does not claim a new binary hash or fresh visual PDF inspection.

## Output files

- `prototype_smoke_CARD10-032_CARD10-056_20261107.json`
- `prototype_evaluation_50_20261107.json`
- `prototype_evaluation_50_adjudicated_20261107.json`
- `prototype_evaluation_comparison_20261107.md`
