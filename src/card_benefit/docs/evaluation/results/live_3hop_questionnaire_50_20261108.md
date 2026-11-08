# Live GraphRAG 50-question run ? 2026-11-08

## Scope and provenance

- The 50 question IDs and exact question text matched the Notion 2026-11-06 questionnaire and `card10_graphrag_golden_dataset_v1.jsonl` (50/50).
- Runner: direct `CardGraphRAG.run`, real Neo4j and real `gpt-6-luna`; no Streamlit app_log writes in this batch. Existing `evaluation_set_50.json` / `golden_answer_set_50.json` were not used because they contain a different 1/2-hop question set.
- The old aligned golden dataset has 49 `NEEDS_REVIEW` and 1 `PDF_VERIFIED` record. Only CARD10-029 is scored; all unverified items remain HOLD. Official PDF binaries were not reopened in this run.

## Summary

- Run ID: `live50-20261108T062408Z-5364151b`; code revision: `4ff5c2244dceb29dc0eaa250cd6355e1ff4919b7+src.a08f5ac932dbabe8`; model: `gpt-6-luna`.
- Invoked: 50/50 once each; completed: 50; execution errors: 0.
- Judgment counts: CORRECT 1, PARTIAL 0, WRONG 0, HOLD 49, ERROR 0.
- By hop: 1-hop 0/20 CORRECT; 2-hop 1/20 CORRECT; 3-hop 0/10 CORRECT. Other items remain HOLD due source verification status.
- LLM: 96 calls, 474,397 input tokens, 24,901 output tokens, $0.059890; embedding estimate 2,010 tokens / $0.000040; elapsed 459.8s.
- Prior run comparison: Normal 33/49 (67.35%) and Prototype 36/49 (73.47%) are not directly comparable; question set and hop composition differ, and this run has only one PDF_VERIFIED record.

## Trace capture limitation

- The expected detailed local Trace file exists but has 50 question entries with 0 captured stage events. Direct runner disabled APP_DB_LOG_ENABLED; the current trace gate also depends on app logging, unintentionally disabling diagnostics. No prompt or raw LLM output is reconstructed or fabricated.
- Result JSON still contains actual Search candidate hits/scores, selected IDs, retrieved data/Evidence, final answers, per-call usage, and errors. Four no-answer cases ended before Retrieve/Answer.
- The one-question Streamlit integration Trace did persist separately to `app_log_id=1110` with three stages; it does not substitute for the missing 50 question traces.

## Observed Search / Interpret findings

- CARD10-010: no candidate for the requested card annual fee in recorded hits; Interpret selected none and returned NOT_ANSWERABLE. Exact prompt-level cause unknown.
- CARD10-020: no candidate for the requested card annual fee in recorded hits; Interpret selected none and returned NOT_ANSWERABLE. Exact prompt-level cause unknown.
- CARD10-047: recorded hits include POINT II/SHOPPING but omit the needed DAILY delivery benefit; Interpret selected none and returned NOT_ANSWERABLE. Likely Search coverage issue, with raw Interpret rationale unavailable.
- CARD10-050: top candidates are airport travel/valet/common benefits but omit lounge candidates; Interpret selected none and returned NOT_ANSWERABLE. Likely Search coverage issue, with raw Interpret rationale unavailable.
- These are observed end-state findings; no Answer cause can be established for these four because Answer was not invoked.

## Per-question outcomes

| ID | Hop | Judgment | Answer status | Selected benefit IDs | Answer excerpt |
| --- | ---: | --- | --- | --- | --- |
| CARD10-001 | 1 | HOLD | ANSWERED | card_product_item:2:20261101_000001, card_product_item:2:20261101_000002, card_product_item:2:20261101_000004, card_product_item:2:20261101_000003 | ONE PICK 편의점·카페 캐시백은 CU·GS25·세븐일레븐과 메가MGC커피·이디야커피·컴포즈커피에서 결제 건당 3천 원 이상이면 100원 캐시백됩니다. 일 1회, 월 30회까지 이용할 수 있고 월 한도는 5천 원입니다. |
| CARD10-002 | 1 | HOLD | ANSWERED | card_product_item:2:20261104_000039 | ONE PICK STYLE 하나 체크카드의 본인 연회비는 없습니다. |
| CARD10-003 | 1 | HOLD | ANSWERED | card_product_item:5:20261105_000105 | JADE Classic은 전 세계 제휴 공항 라운지를 무료로 이용할 수 있으며, 본인·가족·동반자 통합으로 연 3회, 일 3회까지 제공됩니다. 1차년도에는 지난달 50만 원 이상, 2차년도 이후에는 서비스 제공 기간 직전 1년간 600만 원 이상 이용해야 하며 |
| CARD10-004 | 1 | HOLD | ANSWERED | card_product_item:5:20261104_000040 | JADE Classic의 본인 연회비는 국내외겸용 Visa·Mastercard·Amex 12만 원, 국내외겸용 UPI 11만 5천 원입니다. 국내전용은 11만 5천 원이며, 가족 연회비는 각각 3만 원, 2만 5천 원, 2만 5천 원입니다. |
| CARD10-005 | 1 | HOLD | ANSWERED | card_product_item:20:20261105_000092 | 네, JADE First에는 골프 및 프리미엄 아울렛 50% 청구 할인 혜택이 있습니다. 서비스 실적 기간 내 2,400만원 이상 이용 시 보너스 할인 한도 10만원이 제공되며, 3,600만원 이상 이용 시에는 10만원이 추가 제공됩니다. 두 실적 구간에 모두 |
| CARD10-006 | 1 | HOLD | ANSWERED | card_product_item:20:20261105_000093 | JADE First는 전 세계 공항 라운지를 본인·가족·동반자 통합으로 연 8회, 하루 3회까지 무료 이용하실 수 있습니다. 1차년도에는 지난달 100만 원 이상 이용 시, 2차년도부터는 서비스 제공 기간 직전 1년간 1,200만 원 이상 이용 시 제공되며,  |
| CARD10-007 | 1 | HOLD | ANSWERED | card_product_item:21:20261105_000096 | JADE Prime은 전 세계 공항 라운지를 무료로 이용할 수 있으며, 본인·가족·동반자 통합 연 6회, 일 3회까지 제공됩니다. 1차년도에는 지난달 100만 원 이상 이용해야 하고, 2차년도부터는 서비스 제공 기간 직전 1년간 1,200만 원 이상 이용해야  |
| CARD10-008 | 1 | HOLD | ANSWERED | card_product_item:21:20261105_000097 | JADE Prime의 기본적립은 지난달 1일부터 말일까지 200만원 이상 이용하시면 하나머니 1.5%를 적립해 드립니다. |
| CARD10-009 | 1 | HOLD | ANSWERED | card_product_item:22:20261105_000099 | 더 심플 하나카드의 월납 요금 청구할인은 대상 가맹점에 자동납부하면 승인 금액만큼 할인되며, 지난달 이용금액이 30만원 이상 80만원 미만이면 월 1만원, 80만원 이상이면 월 1만5천원까지 할인됩니다. 횟수 제한 없이 월 할인 한도 내에서 합산 할인되며, 월 |
| CARD10-010 | 1 | HOLD | NOT_ANSWERABLE |  |  |
| CARD10-011 | 1 | HOLD | ANSWERED | card_product_item:6:20261104_000013, card_product_item:6:20261104_000017, card_product_item:6:20261104_000014 | 온라인 쇼핑은 인터넷 P/G·인터넷 상거래 등 온라인 업종에서 10% 청구할인됩니다. 전월 국내 가맹점 이용금액이 30만원 이상이면 적용되며, 온라인 할인 월 한도는 전월 이용금액 30만원 이상 70만원 미만일 때 4천원, 70만원 이상 120만원 미만일 때  |
| CARD10-012 | 1 | HOLD | ANSWERED | card_product_item:6:20261104_000022 | 네, 카드의정석 SHOPPING에는 Two-in-One 결제서비스가 있습니다. 사전에 지정한 금액 이하는 체크로 결제하고, 그 초과분은 신용으로 결제하는 서비스입니다. |
| CARD10-013 | 1 | HOLD | ANSWERED | card_product_item:40:20261105_000104 | EVERY WON POINT는 국내외 가맹점에서 0.8% 기본 적립됩니다. 전월실적 조건은 없으며, 월 적립한도는 제한이 없습니다. |
| CARD10-014 | 1 | HOLD | ANSWERED | card_product_item:40:20261105_000103 | EVERY WON POINT는 가족카드 연회비를 청구하지 않습니다. |
| CARD10-015 | 1 | HOLD | ANSWERED | card_product_item:23:20261105_000100 | 카드의정석 POINT II는 네이버페이·카카오페이·PAYCO·SSGPAY에 카드를 등록해 온라인 또는 오프라인에서 결제하면 모아포인트 3% 추가 적립 혜택을 제공합니다. 전월 국내 가맹점 이용실적에 따라 월 적립 한도는 30만원 이상 1만원, 60만원 이상 2 |
| CARD10-016 | 1 | HOLD | ANSWERED | card_product_item:23:20261105_000101 | 카드의정석 POINT II의 Two-in-One 결제서비스는 미리 지정한 금액 이하를 체크로 결제하고, 그 금액을 초과하는 부분은 신용으로 결제하는 서비스입니다. |
| CARD10-017 | 1 | HOLD | ANSWERED | card_product_item:42:20261105_000179 | 카드의정석2 DAILY의 고정소비 혜택은 대상 영역에서 5% 청구할인입니다. 음식점·배달앱, 온라인·오프라인 장보기, 다이소, 택시·카카오T 택시, 주유, SKT·KT·LG U+ 통신요금이 대상이며, 전월 실적 50만원 이상이어야 하고 대부분 매출 건당 3만원 |
| CARD10-018 | 1 | HOLD | ANSWERED | card_product_item:42:20261105_000180 | 정기결제 혜택은 넷플릭스, 유튜브 프리미엄, 티빙, 디즈니플러스, T우주패스 이용 시 50% 청구할인입니다. 전월 실적 50만 원 이상이어야 하며, 공식 홈페이지나 앱에 카드를 등록해 정기결제해야 합니다. 정기결제 할인 한도는 월 5,000원이고, 고정소비 할 |
| CARD10-019 | 1 | HOLD | ANSWERED | card_product_item:24:20261105_000177 | 카드의정석2 SIMPLE은 국내외 가맹점에서 0.8% 또는 0.3% 청구할인 혜택을 제공합니다. Two-in-One 결제서비스로 국내 체크 매출을 이용하면 0.3%가 적용되며, 할인 한도는 없고 전월실적 조건도 없습니다. 다만 어떤 금액에 0.8% 또는 0.3 |
| CARD10-020 | 1 | HOLD | NOT_ANSWERABLE |  |  |
| CARD10-021 | 2 | HOLD | ANSWERED | card_product_item:2:20261101_000001 | ONE PICK 편의점·카페 캐시백은 CU·GS25·세븐일레븐과 메가MGC커피·이디야커피·컴포즈커피에서 결제 건당 3천 원 이상이면 100원 캐시백을 받을 수 있습니다. 하루 1회, 월 30회까지 이용할 수 있고 월 캐시백 한도는 5천 원입니다. |
| CARD10-022 | 2 | HOLD | ANSWERED | card_product_item:2:20261101_000002 | ONE PICK STYLE의 STYLE 영역 캐시백 대상 가맹점은 다이소, 올리브영, 교보문고, 영풍문고, 알라딘, yes24, 아트박스, 무신사, 에이블리입니다. 건당 1만 원 이상 결제하면 500원 캐시백을 받을 수 있으며, 일 1회·월 10회까지이고 월  |
| CARD10-023 | 2 | HOLD | ANSWERED | card_product_item:5:20261105_000105 | JADE Classic 공항 라운지는 본인·가족·동반자 통합으로 연 3회, 하루 3회 이용할 수 있습니다. |
| CARD10-024 | 2 | HOLD | ANSWERED | card_product_item:5:20261104_000040 | JADE Classic의 본인 연회비는 Visa·Mastercard·Amex 국내외겸용 12만 원, UPI 국내외겸용 및 국내전용 각 11만 5천 원입니다. 가족카드는 Visa·Mastercard·Amex 3만 원, UPI 국내외겸용 및 국내전용 각 2만 5천 |
| CARD10-025 | 2 | HOLD | ANSWERED | card_product_item:20:20261105_000093 | JADE First 공항 라운지는 본인·가족·동반자 통합으로 연 8회, 하루 3회까지 이용할 수 있습니다. 이 횟수 한도는 1차년도에는 지난달 100만 원 이상 이용 시, 2차년도 이후에는 서비스 제공 기간 직전 1년간 1,200만 원 이상 이용 시 제공됩니다 |
| CARD10-026 | 2 | HOLD | ANSWERED | card_product_item:20:20261105_000094 | 제휴 주차장 무료 주차는 지난달 실적이 50만 원 이상이면 이용하실 수 있으며, 본인·가족 통합 월 2회까지 제공됩니다. 단, 최초 카드 사용 등록 후 다음 달 말일까지는 지난달 이용금액이 50만 원 미만이어도 제공됩니다. |
| CARD10-027 | 2 | HOLD | ANSWERED | card_product_item:21:20261105_000096 | JADE Prime의 공항 라운지 무료 이용은 본인·가족·동반자 통합 연 6회, 일 3회까지입니다. 국내외겸용카드로 발급받아야 하며, 국내전용카드 보유 회원은 제외됩니다. |
| CARD10-028 | 2 | HOLD | ANSWERED | card_product_item:21:20261105_000097 | JADE Prime의 기본 1.5% 하나머니 적립은 지난달 1일부터 말일까지 200만 원 이상 이용하셔야 받을 수 있습니다. |
| CARD10-029 | 2 | CORRECT | ANSWERED | card_product_item:22:20261105_000099 | 지난달 이용액이 30만 원 이상 80만 원 미만이면 월 할인 한도는 1만 원이고, 80만 원 이상이면 1만 5천 원입니다. |
| CARD10-030 | 2 | HOLD | ANSWERED | card_product_item:22:20261105_000099 | 월납 요금 할인은 국내 대상 가맹점에서 자동납부할 때 적용되며, 통신·렌탈·기타 월납서비스 요금이 대상입니다. 자동납부 결제가 불가한 거래정지·한도 부족, 재발급 후 변경된 카드번호로 자동납부를 다시 등록하지 않은 경우에는 할인을 받을 수 없습니다. 할인은 횟 |
| CARD10-031 | 2 | HOLD | ANSWERED | card_product_item:6:20261104_000013 | 온라인 쇼핑 10% 청구할인은 인터넷 P/G·인터넷 상거래 등 온라인 업종이 대상이며, 전월 국내 가맹점 이용금액이 30만원 이상이어야 합니다. 온라인 월 할인한도는 전월 실적 30만원 이상~70만원 미만이면 4천원, 70만원 이상~120만원 미만이면 8천원, |
| CARD10-032 | 2 | HOLD | ANSWERED | card_product_item:6:20261104_000017, card_product_item:6:20261104_000013 | 네, 4대 PAY 추가 할인은 온라인 쇼핑 할인과 온라인 업종 통합 월 할인한도를 공유합니다. 전월 국내 가맹점 이용금액이 30만원 이상이어야 적용됩니다. |
| CARD10-033 | 2 | HOLD | ANSWERED | card_product_item:40:20261105_000104 | EVERY WON POINT의 국내외 가맹점 기본 적립은 전월 실적 조건 없이 0.8% 적립되며, 월 적립한도도 제한 없습니다. |
| CARD10-034 | 2 | HOLD | ANSWERED | card_product_item:40:20261105_000103 | EVERY WON POINT 가족카드는 연회비를 청구하지 않습니다. 검색 결과에는 이 혜택의 별도 적용 조건이 확인되지 않습니다. |
| CARD10-035 | 2 | HOLD | ANSWERED | card_product_item:23:20261105_000100 | POINT II 간편결제 추가 적립의 통합 월 적립 한도는 전월 국내 가맹점 이용실적 30만원 이상이면 1만원, 60만원 이상이면 2만원, 120만원 이상이면 5만원입니다. |
| CARD10-036 | 2 | HOLD | ANSWERED | card_product_item:23:20261105_000101 | POINT II의 Two-in-One 결제서비스는 사전에 지정한 금액 이하를 체크로 결제하고, 그 금액을 초과하는 부분은 신용으로 결제하는 서비스입니다. 검색 결과에는 적용 결제 유형이나 별도의 추가 조건은 확인되지 않습니다. |
| CARD10-037 | 2 | HOLD | ANSWERED | card_product_item:42:20261105_000179, card_product_item:42:20261105_000180 | 네, 고정소비 할인과 정기결제 할인은 통합 할인한도를 공유합니다. 전월 실적 50만원 이상 100만원 미만이면 통합 한도는 8,000원, 100만원 이상 200만원 미만이면 11,000원, 200만원 이상이면 17,000원입니다. |
| CARD10-038 | 2 | HOLD | ANSWERED | card_product_item:42:20261105_000179 | 배달의민족·쿠팡이츠·요기요에서 공식 배달앱 내 입점 음식점의 음식·음료를 주문하고, 앱 내 카드결제로 건당 3만원 이상 결제하면 5% 청구할인이 적용됩니다. 전월 실적 50만원 이상이 필요하며, 할인 한도는 전월 실적 50만원 이상 100만원 미만이면 월 3, |
| CARD10-039 | 2 | HOLD | ANSWERED | card_product_item:24:20261105_000177 | 국내외 가맹점 기본 할인에서 제외되는 거래는 무이자할부, 정부지원금, 아파트 관리비·공공임대료·부동산임대료, 학교 납부금·대학 등록금, 세금과 공공요금, 상품권·선불카드·기프트카드 구매 및 충전, 환금성 업종, 교통카드 구매 및 충전, 시외·고속버스, 각종 수 |
| CARD10-040 | 2 | HOLD | ANSWERED | card_product_item:24:20261105_000177 | 카드의정석2 SIMPLE은 기본 국내외 가맹점 결제에 0.8% 청구할인이 적용되며, 전월 실적 조건은 없습니다. 다만 Two-in-One 결제서비스를 이용한 국내 체크 매출은 0.3% 청구할인으로 안내되어 있어 기본 할인율보다 낮습니다. 검색 결과에는 두 할인 |
| CARD10-041 | 3 | HOLD | ANSWERED | card_product_item:2:20261101_000001, card_product_item:6:20261104_000015, card_product_item:6:20261104_000016 | ONE PICK STYLE 하나 체크카드는 편의점 1만원 결제 시 건당 100원 캐시백 대상이며, 전월 실적 조건은 없습니다. 카드의정석 SHOPPING은 편의점 오프라인 결제에 10% 청구할인이 적용되지만 전월 실적 30만원 이상이 필요하고, Two-in-O |
| CARD10-042 | 3 | HOLD | ANSWERED | card_product_item:21:20261105_000096, card_product_item:20:20261105_000093, card_product_item:5:20261105_000105 | 연간 무료 이용 횟수는 JADE Classic이 3회, JADE Prime이 6회, JADE First가 8회이며, 모두 본인·가족·동반자 이용 횟수를 통합해 일 3회까지 이용할 수 있습니다. 세 카드 모두 1차년도와 이후의 이용 실적 조건이 다르고, THE  |
| CARD10-043 | 3 | HOLD | ANSWERED | card_product_item:20:20261105_000095, card_product_item:21:20261105_000097, card_product_item:20:20261105_000093, card_product_item:21:20261105_000096 | JADE First - 기본적립: 지난달 이용액 200만원 이상이면 1.5% 하나머니를 적립합니다. - 전세계 공항 라운지 무료 이용: 본인·가족·동반자 통합 연 8회, 일 3회까지 이용할 수 있습니다. 지난달 이용액에 따른 제공 기준은 검색 근거로 확인되지  |
| CARD10-044 | 3 | HOLD | ANSWERED | card_product_item:22:20261105_000099, card_product_item:42:20261105_000179, card_product_item:42:20261105_000180 | 더 심플 하나카드는 대상 통신요금 자동납부에 월 할인 한도 내에서 할인되며, 카드의정석2 DAILY는 통신요금 자동납부에 5%, 대상 구독 정기결제에 50% 할인을 제공합니다.  **더 심플 하나카드** - 휴대전화 요금·구독: 대상 가맹점 자동납부 시 적용됩 |
| CARD10-045 | 3 | HOLD | ANSWERED | card_product_item:6:20261104_000013, card_product_item:6:20261104_000017, card_product_item:23:20261105_000100 | 카드의정석 SHOPPING은 온라인 쇼핑 10% 할인에 더해, 온라인에서 등록한 4대 PAY로 결제하면 5% 추가할인이 적용됩니다. 두 할인은 전월 국내 가맹점 이용실적에 따른 온라인 월 한도를 공유합니다.  카드의정석 POINT II는 주요 간편결제 온라인  |
| CARD10-046 | 3 | HOLD | ANSWERED | card_product_item:40:20261105_000104, card_product_item:24:20261105_000177 | **EVERY WON POINT**은 국내 일반 가맹점에서 0.8% 적립되며 전월 실적 조건이 없고, 기본 적립 한도도 없습니다. **카드의정석2 SIMPLE**은 국내외 가맹점에서 0.8% 또는 0.3% 청구할인되며 전월 실적 조건은 없지만, 국내 일반 가맹 |
| CARD10-047 | 3 | HOLD | NOT_ANSWERABLE |  |  |
| CARD10-048 | 3 | HOLD | ANSWERED | card_product_item:42:20261105_000179, card_product_item:42:20261105_000180 | 고정소비와 정기결제 할인은 각각의 혜택별 한도와 두 혜택이 함께 쓰는 통합 한도가 있습니다. 다만 두 혜택 중 어느 쪽이 먼저 통합 한도를 소진하는지는 정해져 있지 않고, 할인은 거래(매입) 순서대로 적용됩니다.  고정소비 할인은 전월 실적 50만원 이상일 때 |
| CARD10-049 | 3 | HOLD | ANSWERED | card_product_item:2:20261101_000001, card_product_item:24:20261105_000177 | **ONE PICK STYLE 하나 체크카드** — 편의점은 결제 건당 3천 원 이상이면 100원 캐시백되며, 일 1회·월 30회, 월 5천 원 한도입니다. 전월 실적 조건은 없습니다. 검색 결과에는 이 혜택의 제외 항목이 확인되지 않습니다.  **카드의정석2 |
| CARD10-050 | 3 | HOLD | NOT_ANSWERABLE |  |  |

## Files

- Results: `src/card_benefit/docs/evaluation/results/live_3hop_questionnaire_50_20261108T062408Z.json`
- Trace (capture status explicitly marked): `src/card_benefit/docs/evaluation/results/live_3hop_questionnaire_50_trace_20261108T062408Z.json`
