// 카드 혜택 GraphRAG 발표 deck V5 Clean 생성기 (pptxgenjs) — build_v5_final.js 기반, 발표 기획 기준본
// V5 Clean: 본문 하단 '다음 질문' 박스 제거, 슬라이드 전환은 발표자 노트로만 전달
// V5 Final: ① 테스트 코드 존재 ≠ 테스트 통과 ② MCP 결과 일관성 표현 ③ 비교 실험 공정성 조건 ④ GraphRAG·MCP 구현 예정 명시
// V5: 사업 목적(외부 AI에 공식 혜택 정보 제공) → 실제 약관의 복잡성 → GraphRAG 구조·검증 → MCP 재사용, 본문 13장 + 부록 7장
// 팔레트·레이아웃·헬퍼는 build_v4_2.js(← build_v2_base.js)를 그대로 쓴다.
// 사용: node build_v5.js <out.pptx> [notes_body.md]
const pptxgen = require("pptxgenjs");
const fs = require("fs");

const OUT = process.argv[2];
const NOTES_OUT = process.argv[3];
const F = "Malgun Gothic";
const MONO = "Courier New";

// palette
const INK = "0E1A2B", INK2 = "1F3350", TXT = "1A2433", MUTED = "5B6778", LINE = "D5DBE3", MIST = "F3F5F8";
const AMBER = "E8A33D", AMBER_D = "8F5208", AMBER_T = "FDF0DC";
const TEAL = "159A8C", TEAL_D = "0D6F64", TEAL_T = "E3F4F1";
const RED = "D9472B", RED_D = "A8311A", RED_T = "FBE6E2";
const VIO = "6A4FB0", VIO_T = "EFE9F8";
const SLATE = "3A4A60", SLATE_T = "E8ECF2";
const DARK_SUB = "A9B7C9";

const THEME = {
  name: "CardEngine",
  headFontFace: F,
  bodyFontFace: F,
  colors: {
    dk1: TXT, lt1: "FFFFFF", dk2: INK, lt2: MIST,
    accent1: AMBER, accent2: TEAL, accent3: RED, accent4: VIO, accent5: SLATE, accent6: INK2,
    hlink: TEAL_D, folHlink: VIO,
  },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.theme = { headFontFace: F, bodyFontFace: F };
pres.title = "카드사 공식 혜택 정보를 AI에 — 하나카드 상품설명서 기반 GraphRAG";
pres.author = "mle-02-p2-team3";

const W = 13.333, L = 0.6, R = 12.733, CW = R - L;

pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: "FFFFFF" },
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: L, y: 0.36, w: 8.2, h: 0.32, fontFace: F, fontSize: 12, bold: true, color: AMBER_D, margin: 0, valign: "middle" }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: L, y: 0.72, w: CW, h: 0.95, fontFace: F, fontSize: 24, bold: true, color: INK, margin: 0, valign: "top", align: "left" }, text: "" } },
  ],
  slideNumber: { x: 12.33, y: 7.04, w: 0.4, h: 0.26, fontFace: F, fontSize: 10, color: "8A94A3", align: "right" },
});
pres.defineSlideMaster({
  title: "DARK",
  background: { color: INK },
  objects: [],
  slideNumber: { x: 12.33, y: 7.04, w: 0.4, h: 0.26, fontFace: F, fontSize: 10, color: "6F7F96", align: "right" },
});

// ---------- helpers ----------
function T(s, text, o) {
  s.addText(text, Object.assign({ isTextBox: true, fontFace: F, margin: 0, color: TXT, fontSize: 14, valign: "top" }, o));
}
function boxT(s, text, o) {
  const opt = Object.assign({ isTextBox: true, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.08, fontFace: F, fontSize: 13, color: TXT, margin: 6, valign: "middle", align: "center", fill: { color: MIST }, line: { color: MIST, width: 0.75 } }, o);
  s.addText(text, opt);
}
function rect(s, o) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, Object.assign({ rectRadius: 0.1, fill: { color: MIST }, line: { color: MIST, width: 0.75 } }, o));
}
function arrow(s, x, y, w, h, color, o) {
  s.addShape(pres.shapes.LINE, Object.assign({ x, y, w, h, line: { color: color || "8A94A3", width: 1.5, endArrowType: "triangle" } }, o || {}));
}
function line(s, x, y, w, h, color, o) {
  s.addShape(pres.shapes.LINE, Object.assign({ x, y, w, h, line: { color: color || "8A94A3", width: 1.5 } }, o || {}));
}
const PILL = {
  "공식 확인": [TEAL_T, TEAL_D], "원문 확인": [TEAL_T, TEAL_D], "구현 완료": [TEAL_T, TEAL_D], "프로젝트 목적": [TEAL_T, TEAL_D],
  "시연 예정": [AMBER_T, AMBER_D], "검증 예정": [AMBER_T, AMBER_D], "가설 · 검증 예정": [AMBER_T, AMBER_D], "시연 예상 화면": [AMBER_T, AMBER_D],
  "설계안": [SLATE_T, SLATE], "팀 해석": [SLATE_T, SLATE], "팀 가설": [SLATE_T, SLATE], "목표": [SLATE_T, SLATE],
  "확장 제안": [VIO_T, VIO], "미실행": [RED_T, RED_D], "가상 시나리오": [RED_T, RED_D],
};
function pills(s, list) {
  let x = R;
  for (let i = list.length - 1; i >= 0; i--) {
    const t = list[i];
    const w = 0.34 + t.replace(/\s/g, "").length * 0.15;
    x -= w;
    const [bg, fg] = PILL[t];
    s.addText(t, { isTextBox: true, shape: pres.shapes.ROUNDED_RECTANGLE, rectRadius: 0.15, x, y: 0.36, w, h: 0.32, fontFace: F, fontSize: 11, bold: true, color: fg, fill: { color: bg }, line: { color: bg }, align: "center", valign: "middle", margin: 0 });
    x -= 0.1;
  }
}
function footer(s, text) {
  T(s, text, { x: L, y: 7.0, w: 11.5, h: 0.32, fontSize: 10, color: "6B7686", valign: "middle" });
}
function content(kicker, title, section) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addText(kicker, { placeholder: "kicker" });
  s.addText(title, { placeholder: "title" });
  s._v4 = { kicker, title };
  return s;
}
function chip(s, text, x, y, w, h, bg, fg, o) {
  boxT(s, text, Object.assign({ x, y, w, h, fill: { color: bg }, line: { color: bg }, color: fg, fontSize: 12, bold: true, rectRadius: 0.06, margin: 3 }, o || {}));
}
const NODE = { card: [INK, "FFFFFF"], benefit: [TEAL, "FFFFFF"], cond: [AMBER, INK], item: [RED, "FFFFFF"], clause: [VIO, "FFFFFF"], grey: [SLATE_T, SLATE] };
function node(s, text, kind, x, y, w, h, o) {
  const [bg, fg] = NODE[kind];
  boxT(s, text, Object.assign({ x, y, w, h, fill: { color: bg }, line: { color: bg }, color: fg, fontSize: 12, bold: true, rectRadius: 0.12, margin: 3 }, o || {}));
}
const tblBorder = { type: "solid", pt: 0.75, color: LINE };
const edge = (s, t, x, y, w, o) => T(s, t, Object.assign({ x, y, w, h: 0.24, fontSize: 9, bold: true, color: SLATE, fontFace: MONO }, o || {}));

// 발표 노트: 슬라이드 addNotes 와 노트 문서(md)에 같은 대본을 쓴다
const NOTES = [];
function notes(s, label, meta, script) {
  s.addNotes(script);
  NOTES.push(Object.assign({ label, script }, meta));
}

// ===================== V5 =====================
// 상태 배지: 원문 확인 / 구현 완료 / 설계안 / 예상 결과 를 일관되게 쓴다
Object.assign(PILL, {
  "공식 발표 확인": [TEAL_T, TEAL_D], "검증 수행": [TEAL_T, TEAL_D],
  "예상 결과": [AMBER_T, AMBER_D], "시연 목표": [AMBER_T, AMBER_D], "검증 계획": [AMBER_T, AMBER_D],
  "가상 상황": [RED_T, RED_D],
});

// ===================== MAIN =====================
pres.addSection({ title: "도입" });

// ---- 1 표지: 공식 정보는 어디에서 오는가 ----
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "도입" });
  T(s, "하나카드 상품설명서 기반 GraphRAG  ·  카드 혜택 공식 정보 제공 구조  ·  2차 팀 프로젝트", { x: 0.7, y: 0.5, w: 11.5, h: 0.32, fontSize: 13, color: DARK_SUB });
  T(s, [
    { text: "고객이 AI에게 카드 혜택을 물으면,", options: { color: "FFFFFF", breakLine: true } },
    { text: "공식 정보는 어디에서 올까요?", options: { color: AMBER } },
  ], { x: 0.7, y: 0.95, w: 12, h: 1.45, fontSize: 34, bold: true, lineSpacingMultiple: 1.05 });

  const fy = 2.8;
  boxT(s, [
    { text: "고객", options: { bold: true, color: MUTED, fontSize: 11, breakLine: true } },
    { text: "ONE PICK STYLE 카드의 대중교통 캐시백 조건이 뭐예요?", options: { bold: true, color: INK, fontSize: 16 } },
  ], { x: 0.7, y: fy, w: 3.7, h: 1.55, fill: { color: "FFFFFF" }, line: { color: "FFFFFF" }, align: "left", margin: 12, rectRadius: 0.16 });
  arrow(s, 4.45, fy + 0.78, 0.6, 0, "C9D3E0");
  T(s, "질문", { x: 4.35, y: fy + 0.42, w: 0.8, h: 0.26, fontSize: 11, color: "C9D3E0", align: "center" });
  boxT(s, [
    { text: "외부 AI", options: { bold: true, fontSize: 19, breakLine: true } },
    { text: "고객과 대화 · 답변 구성", options: { fontSize: 12, color: "D5DEEA" } },
  ], { x: 5.1, y: fy, w: 2.65, h: 1.55, fill: { color: SLATE }, line: { color: SLATE }, color: "FFFFFF", rectRadius: 0.16 });
  arrow(s, 7.8, fy + 0.5, 1.2, 0, "C9D3E0");
  T(s, "조회 (예: MCP)", { x: 7.75, y: fy + 0.14, w: 1.3, h: 0.26, fontSize: 10, color: "C9D3E0", align: "center" });
  arrow(s, 7.8, fy + 1.05, 1.2, 0, AMBER, { flipH: true });
  T(s, "공식 조건·근거", { x: 7.75, y: fy + 1.15, w: 1.3, h: 0.26, fontSize: 10, color: AMBER, align: "center" });
  boxT(s, [
    { text: "카드사 공식 상품정보", options: { bold: true, fontSize: 18, breakLine: true } },
    { text: "카드 혜택 · 조건 · 약관 근거", options: { fontSize: 14, breakLine: true } },
    { text: "하나카드 상품설명서 기반 · 제안 구조", options: { fontSize: 10, color: "CDEFEA" } },
  ], { x: 9.05, y: fy - 0.08, w: 3.68, h: 1.71, fill: { color: TEAL }, line: { color: TEAL }, color: "FFFFFF", rectRadius: 0.16 });

  T(s, [
    { text: "이 프로젝트  ", options: { bold: true, color: AMBER } },
    { text: "카드사가 외부 AI에 공식 카드 혜택·조건·약관 근거를 제공하는 구조를, 하나카드 공식 상품설명서로 설계하고 검증합니다.", options: { color: "FFFFFF" } },
  ], { x: 0.7, y: 4.7, w: 12, h: 0.75, fontSize: 17, lineSpacingMultiple: 1.1 });
  T(s, "제안 구조 · GraphRAG 엔진·MCP 미구현 · 외부 AI의 도구 호출 여부와 최종 답변은 외부 AI가 결정 · 실제 플랫폼 연동 없음", { x: 0.7, y: 5.75, w: 11.5, h: 0.28, fontSize: 10, color: "7F8FA6" });
  T(s, "mle-02-p2-team3  ·  2026.10", { x: 0.7, y: 6.85, w: 6, h: 0.28, fontSize: 11, color: "7F8FA6" });
  notes(s, "1 표지 — 공식 정보는 어디에서 오는가", {
    purpose: "처음 5초 안에 '카드사가 외부 AI에 공식 혜택 정보를 제공하려는 프로젝트'임을 알게 한다. 기술 구조는 꺼내지 않는다.",
    status: "제안 구조 (GraphRAG 엔진·MCP 미구현, 실제 플랫폼 연동 없음)",
    rebuttal: "“외부 AI가 카드사 정보를 꼭 조회하나?” → 아니다. 조회 여부와 최종 답변은 외부 AI가 정한다. 카드사가 할 수 있는 일은 조회될 때 공식 정보를 정확하게 주는 것이다.",
  }, "고객이 AI에게 이렇게 묻습니다. ONE PICK STYLE 카드의 대중교통 캐시백 조건이 뭐예요? AI는 대답을 잘 합니다. 그런데 그 대답의 내용, 즉 캐시백 조건과 근거는 어디에서 와야 할까요. 저희는 카드사의 공식 상품정보에서 와야 한다고 봅니다. 외부 AI가 필요할 때 카드사의 공식 정보를 조회하고, 카드사는 혜택과 조건, 약관 근거를 돌려주는 구조입니다. 이때 연결 방식으로 MCP 같은 도구 연결을 쓸 수 있습니다. 저희 프로젝트는 이 구조를 하나카드 공식 상품설명서로 설계하고 검증하는 것입니다. 현재는 공식 상품설명서 원문 분석과 설계를 진행한 단계이며, GraphRAG와 MCP 연동은 앞으로 구현·검증할 계획입니다. 또 외부 AI가 이 정보를 실제로 조회할지, 최종 답을 어떻게 만들지는 외부 AI가 정합니다. 실제로 카드사가 외부 AI에 공식 상품정보를 연결한 사례가 있습니다. 신한카드 발표를 보겠습니다.");
}

// ---- 2 신한카드 공식 발표 ----
{
  const s = content("01   실제 사례", "카드사 공식 정보를 외부 AI에 연결하는 서비스가 등장했습니다", "도입");
  pills(s, ["공식 발표 확인"]);
  const cards = [
    { x: L, date: "2026-09-09  ·  신한금융그룹 보도자료", head: "“신한카드, 최적의 금융상품 추천하고 선택하는 AI 개발”", sub: "AI 인프라 기업 커넥셔너리와 기술 개발·실증", lab: "회사가 밝힌 기존 생성형 AI의 한계", chips: ["엉뚱한 답변·정보 왜곡", "일관성 부족", "복합 조건 누락", "정책·규정 미반영"], bg: RED_T, fg: RED_D, foot: "“… 조건 수정만으로 실시간 반영될 수 있는 것이다”", it: true },
    { x: 6.78, date: "2026-09-13  ·  신한카드 보도자료", head: "“카드사 최초 ‘ChatGPT for Kakao’와 연계한 AI 대화형 금융 서비스”", sub: "카카오 ‘PlayMCP’ 기반 ‘카카오 툴즈’에 연동", lab: "외부 AI 대화창에서 제공하는 기능", chips: ["카드 추천", "인기카드 조회", "카드 상세혜택 조회", "소비 인사이트·콘텐츠"], bg: TEAL_T, fg: TEAL_D, foot: "고객이 ‘카카오 툴즈’에서 신한카드 툴을 추가한 뒤 대화로 이용", it: false },
  ];
  cards.forEach((c) => {
    rect(s, { x: c.x, y: 1.85, w: 5.95, h: 3.3 });
    T(s, c.date, { x: c.x + 0.25, y: 1.98, w: 5.5, h: 0.28, fontSize: 12, bold: true, color: MUTED });
    T(s, c.head, { x: c.x + 0.25, y: 2.3, w: 5.5, h: 0.72, fontSize: 16, bold: true, color: INK });
    T(s, c.sub, { x: c.x + 0.25, y: 3.03, w: 5.5, h: 0.26, fontSize: 12, color: SLATE });
    T(s, c.lab, { x: c.x + 0.25, y: 3.35, w: 5.5, h: 0.26, fontSize: 11, color: MUTED });
    c.chips.forEach((t, i) => chip(s, t, c.x + 0.25 + (i % 2) * 2.78, 3.65 + Math.floor(i / 2) * 0.44, 2.68, 0.36, c.bg, c.fg, { fontSize: 13 }));
    T(s, c.foot, { x: c.x + 0.25, y: 4.6, w: 5.5, h: 0.45, fontSize: 12, color: SLATE, italic: c.it });
  });
  boxT(s, "외부 AI 채널에 카드사 공식 상품정보를 연결하는 실제 서비스가 등장하고 있습니다.", { x: L, y: 5.28, w: CW, h: 0.55, fill: { color: INK }, line: { color: INK }, color: "FFFFFF", fontSize: 16, bold: true, align: "left", margin: 14 });
  T(s, "공식 자료에 없음(미확인): 두 발표의 내부 시스템 연결 · GraphRAG 사용 여부 · 다른 카드사·은행의 MCP 제공 현황. 우열 비교가 아니라 ‘외부 AI 연결이 실제로 시작됐다’는 근거로 인용합니다.", { x: L, y: 5.9, w: CW, h: 0.45, fontSize: 11, color: RED_D });
  footer(s, "출처: shinhangroup.com/kr/archive/press/detail/966 (2026-09-09) · press1.newswire.co.kr/newsRead.php?no=1042468 (2026-09-13) — 2026-10-30 원문 재확인");
  notes(s, "2 신한카드 공식 발표", {
    purpose: "1장의 구조가 상상이 아니라 실제로 시작된 방향임을 공식 발표로 보인다. 경쟁 우위 주장이 아니다.",
    status: "공식 발표 확인 (2026-10-30 두 보도자료 원문 재확인)",
    rebuttal: "“신한이 이미 하고 있지 않나?” → 맞다. 그래서 인용했다. 우리 프로젝트가 더 낫다는 주장이 아니다. “신한이 GraphRAG를 쓰나? 두 발표가 연결돼 있나?” → 공식 자료에 없다. 미확인이다.",
  }, "실제로 이런 일이 시작됐습니다. 2026년 9월 13일 신한카드는 카드사 최초로 ChatGPT for Kakao와 연계한 AI 대화형 금융 서비스를 발표했습니다. 카카오의 PlayMCP 기반 카카오 툴즈에 신한카드 서비스를 연동해, 고객이 신한카드 툴을 추가하면 대화로 카드 추천과 상세혜택 조회를 할 수 있습니다. 나흘 전 9월 9일에는 최적의 금융상품을 추천하고 선택하는 AI 개발을 발표했는데, 여기서 기존 생성형 AI의 한계로 엉뚱한 답변과 정보 왜곡, 일관성 부족, 복합 조건 누락, 정책·규정 미반영을 꼽았습니다. 두 발표는 서로 다른 발표이고, 내부적으로 연결됐는지, GraphRAG를 쓰는지는 공식 자료에 없습니다. 다른 카드사나 은행의 현황도 확인하지 않았습니다. 저희가 이 사례에서 가져오는 것은 하나입니다. 카드사의 공식 상품정보를 외부 AI에 연결하는 실제 서비스가 등장하고 있다는 것입니다. 다만 연결했다고 해서 복잡한 혜택을 정확하게 안내할 수 있는 것은 아닙니다. 실제 하나카드 약관 한 줄을 같이 보겠습니다.");
}

pres.addSection({ title: "문제" });

// ---- 3 대중교통 5% 캐시백 ----
{
  const s = content("02   실제 약관 사례", "‘대중교통 5% 캐시백’, 정말 이 한 문장으로 충분할까요?", "문제");
  pills(s, ["원문 확인"]);
  boxT(s, [
    { text: "ONE PICK STYLE · ONE MORE 대중교통", options: { fontSize: 12, color: DARK_SUB, breakLine: true } },
    { text: "대중교통\n5% 캐시백", options: { fontSize: 38, bold: true, color: "FFFFFF" } },
  ], { x: L, y: 1.9, w: 4.3, h: 2.0, fill: { color: INK }, line: { color: INK }, align: "left", margin: 18, rectRadius: 0.12 });
  T(s, "고객이 기억하는 한 줄", { x: L, y: 4.0, w: 4.3, h: 0.28, fontSize: 12, color: MUTED });
  T(s, "한 줄 뒤에 조건 5개가 붙어 있고,\n조건마다 걸리는 위치가 다릅니다.", { x: L, y: 4.4, w: 4.3, h: 0.9, fontSize: 17, bold: true, color: INK, lineSpacingMultiple: 1.15 });
  const rows = [
    ["① 전월실적", "지난달 국내외 일시불 이용금액 10만원 이상", AMBER, INK],
    ["② 한도", "캐시백 한도 월 최대 1,000원", AMBER, INK],
    ["③ 혜택 제외", "시외·고속버스, 철도(KTX·SRT·ITX)는 캐시백 제외", RED, "FFFFFF"],
    ["④ 실적 제외", "상품권·기프트카드 구매, 공과금 등은 실적에 미산입", RED_D, "FFFFFF"],
    ["⑤ 예외", "최초 카드 사용 등록일~다음 달 말일은 실적 10만원 미만이어도 제공", VIO, "FFFFFF"],
  ];
  const rx = 5.5, step = 0.86, rh = 0.72;
  line(s, 4.9, 2.9, 0.3, 0, "A0AAB8");
  line(s, 5.2, 1.9 + rh / 2, 0, step * 4, "A0AAB8");
  rows.forEach((r, i) => {
    const y = 1.9 + i * step;
    line(s, 5.2, y + rh / 2, 0.28, 0, "A0AAB8");
    chip(s, r[0], rx, y, 1.6, rh, r[2], r[3], { fontSize: 14 });
    boxT(s, r[1], { x: rx + 1.7, y, w: R - rx - 1.7, h: rh, fill: { color: MIST }, color: INK, fontSize: 15, align: "left", margin: 12 });
  });
  footer(s, "원문: 하나카드 ONE PICK STYLE 상품설명서(15650_20260429) 1쪽 — ONE MORE 표·실적 산정 기준·실적 제외 대상·서비스 제외 대상·실적과 관계없이 서비스 제공, 2026-10-30 대조");
  notes(s, "3 대중교통 5% 캐시백의 조건", {
    purpose: "실제 하나카드 약관 한 줄 뒤에 조건이 여러 겹 붙어 있음을 체감시킨다. 개인 적격성 판단이 아니라 공식 조건의 구조를 보여 준다.",
    status: "원문 확인 (STYLE 상품설명서 1쪽)",
    rebuttal: "“이 정도는 약관을 읽으면 되지 않나?” → 사람은 된다. AI가 매번 이 다섯 조건과 그 위치를 빠짐없이 지키게 하는 것이 문제다.",
  }, "하나카드 ONE PICK STYLE의 대중교통 혜택입니다. 고객이 기억하는 건 대중교통 5% 캐시백, 이 한 줄입니다. 그런데 원문을 보면 조건이 붙어 있습니다. 하나씩 보겠습니다. 첫째, 지난달 국내외 일시불 이용금액이 10만원 이상이어야 합니다. 둘째, 캐시백은 월 최대 1,000원까지입니다. 셋째, 시외버스와 고속버스, KTX·SRT·ITX 같은 철도는 캐시백에서 빠집니다. 넷째, 상품권이나 기프트카드 구매, 공과금 등은 지난달 실적 계산에 들어가지 않습니다. 다섯째, 예외가 있습니다. 카드를 처음 사용 등록한 날부터 다음 달 말일까지는 실적이 10만원이 안 돼도 제공합니다. 한 줄 뒤에 조건이 다섯 개이고, 잘 보시면 이 조건들이 걸리는 위치가 다릅니다. 셋째는 혜택 자체에 걸리고, 넷째는 실적 계산에 걸립니다. 그런데 여기서 더 중요한 문제가 있습니다. 같은 제외 항목이라도 적용되는 범위가 다를 수 있다는 점입니다.");
}

// ---- 4 상품권 제외의 적용 범위 ----
{
  const s = content("03   적용 범위", "같은 ‘상품권 제외’도 걸리는 곳이 다릅니다", "문제");
  pills(s, ["원문 확인"]);
  node(s, "상품권·기프트카드 구매", "item", 4.9, 1.85, 3.5, 0.6, { fontSize: 16 });
  arrow(s, 5.4, 2.47, 2.0, 0.38, SLATE, { flipH: true });
  arrow(s, 7.9, 2.47, 2.0, 0.38, SLATE);
  const sc = [
    [L, AMBER_T, AMBER_D, "① 전월실적 산정에서 제외", "상품권으로 쓴 금액은 ‘지난달 10만원’ 계산에 들어가지 않습니다", "STYLE 1쪽 · 실적 제외 대상"],
    [7.18, RED_T, RED_D, "② 할인·캐시백 서비스 적용에서 제외", "상품권 결제 자체에는 캐시백·할인이 적용되지 않습니다", "STYLE 1쪽 · 서비스 제외 대상(공통)"],
  ];
  sc.forEach(([x, bg, fg, h, b, src]) => {
    rect(s, { x, y: 2.9, w: 5.55, h: 1.45, fill: { color: bg }, line: { color: bg } });
    T(s, [
      { text: h, options: { bold: true, color: fg, fontSize: 17, breakLine: true } },
      { text: b, options: { color: INK, fontSize: 14, breakLine: true } },
      { text: src, options: { color: MUTED, fontSize: 11 } },
    ], { x: x + 0.22, y: 3.0, w: 5.1, h: 1.28, lineSpacingMultiple: 1.15 });
  });
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: INK } } });
  const dot = { text: "●", options: { color: RED_D, bold: true, align: "center" } };
  s.addTable([
    [H("하나카드 상품"), H("실적 산정 제외"), H("혜택 적용 제외 범위")],
    ["ONE PICK STYLE (체크)", dot, "서비스 공통"],
    ["ONE PICK PLAY (체크)", dot, "서비스 공통"],
    ["BT (신용)", dot, "BIG TICKET 할인"],
    ["에너지 더블 (신용)", dot, "대형마트 할인"],
  ], { x: L, y: 4.55, w: 6.6, colW: [2.5, 1.6, 2.5], rowH: 0.3, fontFace: F, fontSize: 12, color: TXT, border: tblBorder, valign: "middle", margin: [2, 6, 2, 6] });
  boxT(s, [
    { text: "키워드 검색만 하면  ", options: { bold: true, color: INK } },
    { text: "‘상품권’ 문구는 모두 찾지만, 어느 문구가 실적에 걸리고 어느 문구가 혜택에 걸리는지는 문맥과 표 구조까지 봐야 구분됩니다.", options: { color: TXT, breakLine: true } },
    { text: "벡터 RAG·SQL도 적용 범위를 데이터로 표현하면 구분할 수 있습니다. 관건은 그 범위를 정확히 추출·저장하는 일입니다.", options: { color: SLATE, fontSize: 11 } },
  ], { x: 7.45, y: 4.55, w: 5.28, h: 1.55, fill: { color: MIST }, fontSize: 13, align: "left", margin: 12 });
  footer(s, "원문: ONE PICK STYLE(15650_20260429)·PLAY(15651_20260429)·BT(14324_20260310)·에너지 더블(14422_20251224) 1쪽, 2026-10-30 대조");
  notes(s, "4 같은 '상품권 제외'의 다른 적용 범위", {
    purpose: "같은 용어가 실적 계산과 혜택 적용이라는 서로 다른 위치에 걸린다는 점, 그리고 상품마다 혜택 제외 범위가 다르다는 점을 보여 관계 분석의 필요성을 끌어낸다.",
    status: "원문 확인 (4종 상품설명서 1쪽)",
    rebuttal: "“RAG나 SQL은 이걸 구분 못 하나?” → 아니다. 적용 범위를 데이터로 저장하면 어느 방식이든 구분할 수 있다. 문제는 그 범위를 PDF에서 정확히 뽑아 저장하는 일이다.",
  }, "상품권 하나만 따라가 보겠습니다. STYLE 원문에서 상품권은 두 군데에 나옵니다. 하나는 실적 제외 대상입니다. 상품권으로 쓴 돈은 지난달 10만원 계산에 들어가지 않습니다. 다른 하나는 서비스 제외 대상입니다. 상품권 결제 자체에는 캐시백이나 할인이 적용되지 않습니다. 같은 단어인데 걸리는 곳이 다릅니다. 아래 표처럼 원문을 대조한 4종 모두 상품권이 실적 산정에서 빠지지만, 혜택에서 빠지는 범위는 상품마다 다릅니다. STYLE·PLAY는 서비스 공통, BT는 BIG TICKET 할인, 에너지 더블은 대형마트 할인입니다. ‘상품권’으로 검색하면 이 문구들이 다 나옵니다. 하지만 어느 문구가 실적에, 어느 문구가 혜택에 걸리는지는 문맥과 표 구조를 함께 봐야 알 수 있습니다. 공정하게 말씀드리면 벡터 RAG나 SQL도 이 범위를 데이터로 저장해 두면 구분할 수 있습니다. 결국 관건은 그 범위를 PDF에서 정확히 뽑아내는 일입니다. 그래서 PDF에서 조건을 뽑을 때 이 관계가 남는지 직접 확인해 봤습니다.");
}

// ---- 5 PDF 추출 ----
{
  const s = content("04   PDF 추출 검증", "PDF에서 숫자는 읽혀도, 조건 사이의 관계는 쉽게 끊어집니다", "문제");
  pills(s, ["검증 수행"]);
  T(s, "원문 PDF 표 — BT · BIG TICKET (도식)", { x: L, y: 1.85, w: 5.5, h: 0.3, fontSize: 13, bold: true, color: INK });
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: SLATE } } });
  s.addTable([
    [H("이용금액 구간"), H("할인율"), H("월 할인한도")],
    ["구간 1", "1.5%", { text: "300만원 · 한도 없음\n(구간별로 대응)", options: { rowspan: 4, valign: "middle", align: "center" } }],
    ["구간 2", "1.2%"], ["구간 3", "1.0%"], ["구간 4", "0.5%"],
  ], { x: L, y: 2.2, w: 5.5, colW: [1.8, 1.4, 2.3], rowH: 0.36, fontFace: F, fontSize: 13, color: TXT, border: tblBorder, valign: "middle", align: "center", margin: [2, 6, 2, 6] });
  arrow(s, 6.2, 3.1, 0.5, 0, SLATE);
  T(s, "기본 옵션 추출 결과 — pdfplumber extract_tables()", { x: 6.78, y: 1.85, w: 5.95, h: 0.3, fontSize: 13, bold: true, color: INK });
  boxT(s, "['할인율', '월 할인한도']\n['1.5%\\n1.2%\\n1.0%\\n0.5%', '300만원\\n한도 없음']", { x: 6.78, y: 2.2, w: 5.95, h: 1.15, fill: { color: INK }, line: { color: INK }, color: "E6ECF4", fontFace: MONO, fontSize: 13, align: "left", margin: 12 });
  T(s, "→ 이용금액 구간 열이 사라지고, 할인율 4개가 한 셀로 묶임", { x: 6.78, y: 3.45, w: 5.95, h: 0.5, fontSize: 14, bold: true, color: RED_D });
  T(s, "같은 검증에서 확인한 사실", { x: L, y: 4.35, w: 2.4, h: 0.4, fontSize: 13, bold: true, color: TEAL_D, valign: "middle" });
  const cw = (R - 3.1 - 0.3) / 3;
  ["STYLE·PLAY: 기본 표 탐지 0개", "에너지 더블: 가맹점 열이 None", "‘월 5천원’이 혜택 3곳에 반복"].forEach((t, i) => chip(s, t, 3.1 + i * (cw + 0.15), 4.35, cw, 0.4, TEAL_T, TEAL_D, { fontSize: 13 }));
  T(s, "예상 위험 (미검증)", { x: L, y: 4.9, w: 2.4, h: 0.4, fontSize: 13, bold: true, color: SLATE, valign: "middle" });
  ["혜택–조건 잘못 연결", "비슷한 문구를 같은 규칙으로 병합", "한도와 구간의 대응 손실"].forEach((t, i) => boxT(s, t, { x: 3.1 + i * (cw + 0.15), y: 4.9, w: cw, h: 0.4, fill: { color: "FFFFFF" }, line: { color: "A0AAB8", width: 1, dashType: "dash" }, color: SLATE, fontSize: 13, bold: true, margin: 3 }));
  boxT(s, "PyMuPDF 1.28.2·pdfplumber 0.11.10 기본 옵션의 표본 결과입니다. 파서 설정·OCR·수작업 보정으로 달라질 수 있으며, PDF 추출 기술 전체의 한계를 뜻하지 않습니다.", { x: L, y: 5.5, w: CW, h: 0.62, fill: { color: MIST }, color: SLATE, fontSize: 12, align: "left", margin: 12 });
  footer(s, "card_pdf_structuring_validation.md (2026-10-29 팀 검증, 대표 페이지 원문 이미지 대조) · 왼쪽 표는 행 구조를 단순화한 도식");
  notes(s, "5 PDF 추출의 어려움", {
    purpose: "비정형 PDF에서 조건 사이의 관계가 끊어지는 실제 사례를 보이고, 검증한 사실과 예상 위험을 구분한다.",
    status: "검증 수행 (2026-10-29 팀 표본 검증) · 예상 위험은 미검증",
    rebuttal: "“더 좋은 파서를 쓰면 해결되지 않나?” → 그럴 수 있다. 이 결과는 기본 옵션 표본이며, 파서 설정·OCR·수작업 보정을 시도할 계획이다. 그래서 추출 후 원문 대조 단계를 따로 둔다.",
  }, "그렇다면 PDF에서 조건을 뽑으면 관계가 남을까요. 저희가 실제로 해 봤습니다. 왼쪽은 BT 카드 BIG TICKET 혜택의 원문 표를 단순화한 그림입니다. 이용금액 구간마다 할인율이 한 행씩 있고, 한도가 구간별로 대응합니다. 오른쪽은 pdfplumber 기본 옵션으로 표를 뽑은 결과입니다. 할인율 네 개가 한 셀에 묶여 나오고, 어느 구간의 할인율인지 알려 주는 이용금액 구간 열은 아예 사라졌습니다. 숫자는 다 읽혔는데 관계가 끊어진 것입니다. 같은 검증에서 STYLE과 PLAY는 표가 하나도 탐지되지 않았고, 에너지 더블은 가맹점 열이 비어서 나왔습니다. 또 월 5천원이라는 값이 혜택 세 곳에 반복돼 숫자만으로는 어느 혜택의 한도인지 알 수 없습니다. 아래 점선 상자는 아직 확인하지 않은 예상 위험입니다. 공정하게 말씀드리면 이건 기본 설정의 표본 결과이고, 파서 설정이나 OCR, 수작업 보정으로 달라질 수 있습니다. 중요한 것은 추출한 조건을 원문과 대조하고, 관계를 따라갈 수 있는 구조로 저장해야 한다는 점입니다. 그래서 저희는 혜택과 조건, 원문 근거를 관계로 구조화하는 방법을 검토했습니다.");
}

pres.addSection({ title: "해결 구조" });

// ---- 6 GraphRAG 구조 ----
{
  const s = content("05   해결 구조", "GraphRAG로 카드·혜택·조건·원문을 연결합니다", "해결 구조");
  pills(s, ["설계안"]);
  boxT(s, "제안 구조 · 카드 도메인 GraphRAG/MCP 구현 예정", { x: L, y: 1.38, w: 5.4, h: 0.38, fill: { color: AMBER_T }, line: { color: AMBER, width: 1 }, color: AMBER_D, fontSize: 13, bold: true, align: "left", margin: 10 });
  const lab = (t, y) => boxT(s, t, { x: L, y, w: 1.7, h: 0.75, fill: { color: SLATE_T }, line: { color: SLATE_T }, color: INK, fontSize: 12, bold: true, margin: 3 });
  lab("지식화\n문서 → 그래프", 1.9);
  lab("GraphRAG\n질문 → 답변", 3.0);
  const x0 = 2.5, g = 0.25;
  const w1 = (R - x0 - g * 4) / 5;
  ["공식 PDF\n(하나카드)", "파싱·청킹\n원문 위치 보존", "LLM 관계\n추출·정규화", "원문 대조·검수", "Neo4j\n관계 저장"].forEach((t, i) => {
    const x = x0 + i * (w1 + g);
    boxT(s, t, { x, y: 1.9, w: w1, h: 0.75, fill: { color: "FFFFFF" }, line: { color: LINE, width: 1 }, color: INK, fontSize: 13, bold: i === 4, margin: 3 });
    if (i < 4) arrow(s, x + w1 + 0.02, 2.275, g - 0.04, 0);
  });
  const w2 = (R - x0 - g * 2) / 3;
  ["① 질문 해석 (LLM)", "② 관계·근거 검색 (Cypher)", "③ 근거 기반 답변 (LLM)"].forEach((t, i) => {
    const x = x0 + i * (w2 + g);
    boxT(s, t, { x, y: 3.0, w: w2, h: 0.75, fill: { color: TEAL }, line: { color: TEAL }, color: "FFFFFF", fontSize: 15, bold: true, margin: 3 });
    if (i < 2) arrow(s, x + w2 + 0.02, 3.375, g - 0.04, 0);
  });
  const nx = x0 + 4 * (w1 + g) + w1 / 2;
  arrow(s, nx, 2.67, x0 + w2 + g + w2 * 0.75 - nx, 0.31, TEAL_D);
  T(s, "그래프 관계 예시 — 질문에 필요한 노드만", { x: L, y: 4.0, w: 8, h: 0.3, fontSize: 13, bold: true, color: INK });
  const nw = 2.15, ng = (CW - nw * 5) / 4;
  [["카드\nONE PICK STYLE", "card"], ["혜택\nONE MORE 대중교통", "benefit"], ["실적 조건\n지난달 10만원", "cond"], ["제외 규칙\n상품권 실적 제외", "item"], ["공식 조항\n15650 · 1쪽", "clause"]].forEach(([t, k], i) => {
    const x = L + i * (nw + ng);
    node(s, t, k, x, 4.35, nw, 0.8, { fontSize: 13 });
    if (i < 4) arrow(s, x + nw + 0.02, 4.75, ng - 0.04, 0, SLATE);
  });
  T(s, "HAS_BENEFIT  →  REQUIRES  →  EXCLUDES {scope: 실적}  →  SOURCED_FROM", { x: L, y: 5.2, w: CW, h: 0.26, fontSize: 11, color: SLATE, fontFace: MONO, align: "center" });
  boxT(s, [
    { text: "GraphRAG  ", options: { bold: true, color: AMBER } },
    { text: "그래프에서 찾은 관계·원문 근거를 LLM 답변에 넣는 방식 — Neo4j 저장만으로는 GraphRAG가 아닙니다.", options: { color: "FFFFFF" } },
  ], { x: L, y: 5.6, w: CW, h: 0.62, fill: { color: INK }, line: { color: INK }, fontSize: 14, align: "left", margin: 14 });
  footer(s, "설계안 — 파싱·추출·적재·검색·답변 모두 미구현 (과제 M1~M7) · 노드 색: 카드·혜택·조건·제외 규칙·조항");
  notes(s, "6 GraphRAG 구조", {
    purpose: "문서를 그래프로 만드는 지식화 단계와, 질문에 그래프를 써서 답하는 GraphRAG 단계를 분리해 보여 준다. 저장만으로는 GraphRAG가 아님을 명시한다.",
    status: "설계안 (전 단계 미구현)",
    rebuttal: "“결국 Neo4j DB 하나 만드는 것 아닌가?” → 아니다. 질문 해석 → 관계·근거 검색 → 검색 결과를 넣은 답변 생성까지가 GraphRAG다. 저장은 그 일부다.",
  }, "저희가 설계한 구조입니다. 위쪽은 문서를 그래프로 만드는 과정입니다. 하나카드 공식 PDF를 원문 위치를 남기며 나누고, LLM이 혜택과 조건의 관계를 뽑아 표기를 맞추고, 사람이 원문과 대조해 검수한 다음 Neo4j에 관계로 저장합니다. 아래쪽이 GraphRAG입니다. GraphRAG는 그래프에서 찾은 관계와 원문 근거를 LLM의 답변에 넣는 방식입니다. 질문이 들어오면 LLM이 무엇을 묻는지 해석하고, 그래프에서 관련 관계와 근거를 검색하고, 그 검색 결과를 바탕으로 답합니다. Neo4j에 저장만 해서는 GraphRAG가 아니라는 점을 강조드립니다. 아래 그림이 3장 사례를 그래프로 그린 모습입니다. STYLE 카드에서 ONE MORE 대중교통 혜택, 그 혜택이 요구하는 지난달 10만원 실적 조건, 그 조건이 상품권을 실적에서 제외한다는 규칙, 그리고 그 규칙이 나온 상품설명서 1쪽까지 하나의 경로로 이어집니다. 카드 도메인의 GraphRAG와 MCP는 앞으로 구현할 제안 구조입니다. 이렇게 연결해 두면 질문 하나에 어떤 결과를 돌려줄 수 있는지 보겠습니다.");
}

// ---- 7 사용 장면 ----
{
  const s = content("06   사용 장면", "질문 하나에 공식 조건과 원문 근거를 함께 반환합니다", "해결 구조");
  pills(s, ["원문 확인", "예상 결과"]);
  boxT(s, "Q.  ONE PICK STYLE 대중교통 캐시백의 전월실적 조건은?", { x: L, y: 1.8, w: CW, h: 0.55, fill: { color: AMBER_T }, line: { color: AMBER_T }, color: AMBER_D, fontSize: 18, bold: true, align: "left", margin: 14 });
  boxT(s, "예상 결과 — 수작업 원문 대조 (시스템 실행 결과 아님)", { x: L, y: 2.45, w: CW, h: 0.38, fill: { color: RED_T }, line: { color: RED, width: 1 }, color: RED_D, fontSize: 13, bold: true, align: "left", margin: 12 });
  rect(s, { x: L, y: 2.95, w: 7.55, h: 3.3, fill: { color: "FFFFFF" }, line: { color: INK, width: 1.25 } });
  [
    ["공식 혜택", "ONE MORE 대중교통 — 버스·지하철 5% 캐시백"],
    ["실적 기준", "지난달 국내외 일시불 이용금액 10만원 이상"],
    ["캐시백 한도", "월 최대 1,000원"],
    ["제외 대상", "시외·고속버스·철도는 혜택 제외 / 상품권 등은 실적 제외"],
    ["신규 예외", "최초 사용 등록일~다음 달 말일은 실적 무관 제공"],
  ].forEach(([k, v], i) => {
    const y = 3.08 + i * 0.62;
    T(s, k, { x: L + 0.2, y, w: 1.45, h: 0.52, fontSize: 14, bold: true, color: TEAL_D, valign: "middle" });
    T(s, v, { x: L + 1.7, y, w: 5.7, h: 0.52, fontSize: 15, color: INK, valign: "middle" });
    if (i < 4) line(s, L + 0.2, y + 0.57, 7.15, 0, LINE, { line: { color: LINE, width: 0.75 } });
  });
  rect(s, { x: 8.4, y: 2.95, w: R - 8.4, h: 2.25, fill: { color: VIO_T }, line: { color: VIO_T } });
  T(s, [
    { text: "원문 근거", options: { bold: true, color: VIO, fontSize: 15, breakLine: true } },
    { text: "ONE PICK STYLE 상품설명서", options: { bold: true, color: INK, fontSize: 13, breakLine: true } },
    { text: "15650_20260429 · 1쪽", options: { bold: true, color: INK, fontSize: 13, breakLine: true } },
    { text: "ONE MORE 혜택 표", options: { bullet: true, breakLine: true } },
    { text: "실적 산정 기준 · 실적 제외 대상", options: { bullet: true, breakLine: true } },
    { text: "서비스 제외 대상", options: { bullet: true, breakLine: true } },
    { text: "실적과 관계없이 서비스 제공", options: { bullet: true } },
  ], { x: 8.6, y: 3.05, w: R - 8.8, h: 2.1, fontSize: 12, color: TXT, paraSpaceAfter: 2 });
  boxT(s, [
    { text: "범위 밖  ", options: { bold: true, color: SLATE } },
    { text: "‘이 고객이 이번 달 받는가’ — 개인 실적·등록일은 조회하지 않고 공식 조건만 안내합니다", options: { color: TXT } },
  ], { x: 8.4, y: 5.3, w: R - 8.4, h: 0.95, fill: { color: SLATE_T }, line: { color: SLATE_T }, fontSize: 12, align: "left", margin: 10 });
  footer(s, "값은 STYLE 상품설명서 원문으로 확인 · 응답 화면은 구현 후 얻으려는 출력 예시(M7) · 개인 혜택 수령 여부는 판단하지 않음");
  notes(s, "7 질문 하나에 조건과 근거", {
    purpose: "핵심 사용 장면. 공식 조건 다섯 가지와 원문 조항이 한 번에 돌아오는 모습을 보인다. 개인 적격성 판단이 아님을 분명히 한다.",
    status: "원문 확인(값) · 예상 결과(화면, 미구현)",
    rebuttal: "“그래서 이 고객은 받나요?” → 그 질문은 범위 밖이다. 고객의 실적·등록일·거래 내역은 쓰지 않는다. 우리가 말하는 ‘판단’은 공식 약관의 조건과 적용 범위 분석이다.",
  }, "핵심 장면입니다. ONE PICK STYLE 대중교통 캐시백의 전월실적 조건을 물으면, 답은 이렇게 돌아와야 합니다. 공식 혜택은 버스·지하철 5% 캐시백, 실적 기준은 지난달 국내외 일시불 10만원 이상, 한도는 월 최대 1,000원, 제외 대상은 혜택에서 빠지는 시외·고속버스와 철도, 실적에서 빠지는 상품권 등이고, 신규 예외까지 함께 나옵니다. 그리고 오른쪽처럼 이 내용이 상품설명서 1쪽의 어느 부분에서 나왔는지가 같이 붙습니다. 이 화면은 구현 후 얻으려는 출력 예시이고, 값은 저희가 원문과 손으로 대조한 것입니다. 한 가지 분명히 할 점이 있습니다. 저희는 이 고객이 이번 달 캐시백을 받는지는 판단하지 않습니다. 개인의 실적이나 등록일, 결제 기록은 쓰지 않습니다. 저희가 말하는 판단은 공식 약관의 조건과 적용 범위를 분석하는 것입니다. 관계를 저장해 두면 조회 말고도 할 수 있는 일이 있습니다. 조건이 바뀌는 경우입니다.");
}

// ---- 8 조건 변경 영향 ----
{
  const s = content("07   변경 영향", "조건이 바뀌면, 다시 검토할 혜택이 관계를 따라 드러납니다", "해결 구조");
  pills(s, ["가상 상황", "예상 결과"]);
  boxT(s, "가상 상황:  ‘상품권 구매’의 전월실적 제외 조항이 바뀐다면?", { x: L, y: 1.8, w: CW, h: 0.5, fill: { color: AMBER_T }, line: { color: AMBER_T }, color: AMBER_D, fontSize: 16, bold: true, align: "left", margin: 14 });
  const hy = 2.42;
  T(s, "공통 개념", { x: L, y: hy, w: 1.9, h: 0.3, fontSize: 12, bold: true, color: RED_D, align: "center" });
  T(s, "카드별 규칙 — 적용 범위·문서 판 따로 보존", { x: 2.85, y: hy, w: 3.95, h: 0.3, fontSize: 12, bold: true, color: TEAL_D });
  T(s, "검토 후보 혜택 (실적 조건에 연결)", { x: 7.25, y: hy, w: 5.48, h: 0.3, fontSize: 12, bold: true, color: INK });
  const ry0 = 2.82, rs = 0.74, rh = 0.62;
  node(s, "상품권\n구매", "item", L, ry0, 1.9, rs * 3 + rh, { fontSize: 16 });
  [
    ["ONE PICK STYLE (체크)", "15650_20260429", "ONE MORE 대중교통(10만) · 놀이공원(20만)"],
    ["ONE PICK PLAY (체크)", "15651_20260429", "ONE MORE 대중교통(10만) · 놀이공원(20만)"],
    ["BT (신용)", "14324_20260310", "인천공항 라운지(50만)"],
    ["에너지 더블 (신용)", "14422_20251224", "에너지 공과금(40/80만) · 일상생활(40만)"],
  ].forEach(([c, d, b], i) => {
    const y = ry0 + i * rs;
    arrow(s, L + 1.92, y + rh / 2, 2.85 - L - 1.96, 0, RED);
    boxT(s, [
      { text: c, options: { bold: true, color: INK, fontSize: 13, breakLine: true } },
      { text: "실적 제외 규칙 · " + d, options: { color: TEAL_D, fontSize: 11 } },
    ], { x: 2.85, y, w: 3.95, h: rh, fill: { color: TEAL_T }, line: { color: TEAL, width: 1 }, align: "left", margin: 8 });
    arrow(s, 6.83, y + rh / 2, 0.39, 0, SLATE);
    boxT(s, b, { x: 7.25, y, w: R - 7.25, h: rh, fill: { color: MIST }, color: INK, fontSize: 14, align: "left", margin: 10 });
  });
  boxT(s, "사람이 검토할 영향 후보입니다 (자동 정책 변경 아님) · 실적 조건 없는 ONE PICK 영역·BIG TICKET은 후보에서 제외", { x: L, y: 5.85, w: CW, h: 0.42, fill: { color: RED_T }, line: { color: RED_T }, color: RED_D, fontSize: 12, bold: true, align: "left", margin: 10 });
  footer(s, "4종 원문 수작업 도출(예상 결과) · Cypher 미실행 · 같은 개념을 공유해도 카드별 정책은 다를 수 있어 규칙을 카드별로 분리 저장");
  notes(s, "8 조건 변경 영향 후보", {
    purpose: "관계를 거꾸로 따라가면 '무엇을 다시 봐야 하는지'를 찾을 수 있음을 보인다. 공통 개념과 카드별 규칙을 분리하는 모델을 강조한다.",
    status: "가상 상황 · 예상 결과 (4종 원문 수작업 도출, Cypher 미실행)",
    rebuttal: "“상품권이 하나의 노드면 정책도 하나로 묶이는 것 아닌가?” → 아니다. ‘상품권 구매’라는 대상만 공통이고, 실적 제외 규칙은 카드별로 따로 저장하며 적용 범위와 문서 판을 각각 보존한다. “이 목록대로 바꾸면 되나?” → 아니다. 사람이 검토할 후보다.",
  }, "관계를 반대 방향으로 따라가 보겠습니다. 가상으로 상품권 구매의 실적 제외 조항이 바뀐다고 해 보겠습니다. 상품권 구매라는 대상에서 출발해, 그 대상을 언급하는 카드별 실적 제외 규칙을 찾고, 그 규칙이 붙은 실적 조건을 요구하는 혜택까지 따라가면 다시 검토할 혜택 후보가 나옵니다. 원문 대조한 4종에서는 STYLE과 PLAY의 대중교통·놀이공원, BT의 공항 라운지, 에너지 더블의 공과금·일상생활 할인입니다. 반대로 실적 조건이 없는 ONE PICK 영역이나 BIG TICKET은 후보에서 빠집니다. 여기서 중요한 설계 원칙이 있습니다. 상품권이라는 대상을 공통으로 연결한다고 해서 카드마다 정책이 같은 것은 아닙니다. 그래서 규칙은 카드별로 따로 저장하고, 적용 범위와 원문 문서 판도 각각 남깁니다. 그리고 이 결과는 자동으로 정책을 바꾸는 목록이 아니라 사람이 검토할 영향 후보입니다. 그런데 이런 관계 탐색은 SQL로도 가능하죠. 그래서 왜 그래프를 검토하는지 설명드리겠습니다.");
}

pres.addSection({ title: "기술 선택과 검증" });

// ---- 9 SQL·RAG·그래프 비교 ----
{
  const s = content("08   기술 선택", "SQL·일반 RAG로도 가능합니다. 그런데 왜 그래프를 검토할까요?", "기술 선택과 검증");
  pills(s, ["팀 해석", "검증 계획"]);
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: SLATE }, fontSize: 13 } });
  const lab = (t) => ({ text: t, options: { bold: true, color: INK, fill: { color: MIST } } });
  s.addTable([
    [H("비교 관점"), H("일반 벡터 RAG"), H("PostgreSQL (관계 테이블 + SQL)"), H("Neo4j 그래프")],
    [lab("모델링 방식"), "원문 청크 + 메타데이터", "카드·혜택·규칙·조항 테이블과 키", "노드와 관계 유형(HAS_BENEFIT 등)"],
    [lab("적용 범위 표현"), "청크 메타데이터·프롬프트로 구분", "scope 컬럼·규칙 테이블", "관계 속성 {scope}"],
    [lab("원문 근거"), "검색된 청크 출처를 그대로 반환", "근거 키 JOIN으로 반환", "SOURCED_FROM 경로로 반환"],
    [lab("다단계·역방향 탐색"), "반복 검색·별도 로직으로 구성", "JOIN·재귀 CTE로 구성", "가변 길이·역방향 경로 패턴"],
    [lab("검증 비용"), "청크와 답변 단위 대조", "행 단위 제약·검증 SQL", "노드·관계 단위 대조"],
    [lab("운영 복잡도"), "낮음", "낮음~중간 (팀 기존 역량, DDL 초안)", "중간~높음 (인프라·온톨로지 관리)"],
  ], { x: L, y: 1.8, w: CW, colW: [2.2, 3.1, 3.4, 3.43], rowH: 0.42, fontFace: F, fontSize: 12, color: TXT, border: tblBorder, valign: "middle", margin: [2, 6, 2, 6] });
  T(s, [
    { text: "공정 비교 원칙  ", options: { bold: true, color: INK } },
    { text: "동일한 공식 PDF·문서 버전·질문·원문 정답셋을 사용하고, 방식별 전처리·수작업 보정·개발 비용을 함께 기록합니다 (부록 C)", options: { color: SLATE } },
  ], { x: L, y: 4.95, w: CW, h: 0.5, fontSize: 12 });
  boxT(s, [
    { text: "이 프로젝트는 복잡한 카드 혜택 관계를 그래프로 표현하고 탐색하는 방법을 검증합니다. ", options: { bold: true, color: "FFFFFF" } },
    { text: "SQL 대비 우위는 실제 비교 이전에 단정하지 않습니다.", options: { bold: true, color: AMBER } },
  ], { x: L, y: 5.5, w: CW, h: 0.75, fill: { color: INK }, line: { color: INK }, fontSize: 15, align: "left", margin: 14 });
  footer(s, "가능·불가능의 우열 표가 아니라 구현 방식의 차이 · 정확도·효율 차이는 실험 전 · PostgreSQL 비교안: sql/hana_card_schema_draft.sql (DB 미적용)");
  notes(s, "9 SQL·일반 RAG·그래프 비교", {
    purpose: "가장 먼저 나올 반박을 정면으로 다룬다. 세 방식 모두 가능하다고 인정하고, 차이를 모델링·표현·탐색·검증 비용·운영 복잡도로만 설명한다.",
    status: "팀 해석 · 검증 계획 (실험 전)",
    rebuttal: "“그럼 왜 굳이 그래프인가?” → 과제가 GraphRAG 구현을 요구하고, 카드 혜택처럼 관계 유형이 많고 역방향 탐색이 필요한 문제에서 그래프 표현이 편한지를 검증하려는 것이다. 편하지 않다는 결과가 나오면 그것도 결과로 보고한다.",
  }, "이제 가장 중요한 질문입니다. SQL로도 되지 않나요? 됩니다. 일반 벡터 RAG도 원문을 찾아 근거를 보여 줄 수 있고, PostgreSQL도 관계 테이블과 JOIN, 재귀 CTE로 조건과 영향 범위를 분석할 수 있습니다. 그래서 이 표는 무엇이 되고 안 되는지를 비교하는 표가 아닙니다. 같은 일을 어떤 방식으로 표현하고 탐색하느냐의 차이입니다. 그래프는 관계 유형과 여러 단계, 역방향 경로를 명시적으로 표현하는 데 편할 가능성이 있습니다. 대신 인프라와 온톨로지 관리 부담이 큽니다. SQL은 저희 팀이 익숙하고 테이블 설계 초안도 있습니다. 어느 쪽이 더 정확하거나 효율적인지는 실제로 비교해 봐야 압니다. 그래서 같은 공식 PDF와 문서 버전, 같은 질문과 원문 정답셋으로 세 방식을 비교하고, 방식마다 필요한 전처리와 수작업 보정, 개발 비용도 함께 기록할 계획입니다. 이 프로젝트는 복잡한 카드 혜택 관계를 그래프로 표현하고 탐색하는 방법을 검증합니다. SQL 대비 우위는 실제 비교 전에 단정하지 않습니다. 어떤 방식을 쓰든, 찾은 조건과 AI의 답변이 맞는지는 따로 검증해야 합니다. 그 방법을 말씀드리겠습니다.");
}

// ---- 10 검증 ----
{
  const s = content("09   검증", "추출한 관계와 생성한 답변은 단계마다 원문과 대조합니다", "기술 선택과 검증");
  pills(s, ["설계안", "검증 계획"]);
  const st = [
    ["① 공식 PDF 원문", "잘못된 표 추출", "예: BT 구간 열 소실", "원문 이미지 ↔ 추출 텍스트"],
    ["② 구조화 관계", "조건 누락 · 적용 범위 혼동", "예: 상품권 ‘실적 제외’ 누락", "원문 문장 ↔ 관계"],
    ["③ 그래프 검색 결과", "원문 조항 연결 오류", "예: 다른 혜택의 조항을 반환", "쿼리·경로 ↔ 기대 결과"],
    ["④ LLM 생성 답변", "검색 결과와 답변 불일치", "예: 근거에 없는 조건을 덧붙임", "검색 결과 ↔ 답변 문장"],
  ];
  const cw = (CW - 0.3 * 3) / 4;
  st.forEach((c, i) => {
    const x = L + i * (cw + 0.3);
    boxT(s, c[0], { x, y: 1.85, w: cw, h: 0.6, fill: { color: SLATE_T }, line: { color: SLATE_T }, color: INK, fontSize: 15, bold: true });
    if (i < 3) arrow(s, x + cw + 0.03, 2.15, 0.24, 0);
    rect(s, { x, y: 2.58, w: cw, h: 1.3, fill: { color: RED_T }, line: { color: RED_T } });
    T(s, [
      { text: "생길 수 있는 오류", options: { bold: true, color: RED_D, fontSize: 11, breakLine: true } },
      { text: c[1], options: { bold: true, color: INK, fontSize: 14, breakLine: true } },
      { text: c[2], options: { color: SLATE, fontSize: 12 } },
    ], { x: x + 0.15, y: 2.65, w: cw - 0.3, h: 1.18 });
    T(s, "대조: " + c[3], { x, y: 3.95, w: cw, h: 0.32, fontSize: 12, bold: true, color: TEAL_D, align: "center" });
  });
  boxT(s, [
    { text: "실행 기록(trace)으로 남길 수 있는 것  ", options: { bold: true, color: TEAL_D } },
    { text: "질문 · 실행 쿼리·파라미터 · 반환 조건·조항 · 생성 답변 · 모델·데이터 버전 (우리 시스템 실행 시)", options: { color: TXT, breakLine: true } },
    { text: "쿼리 로그 포매터(QueryLogger)는 구현돼 있고, trace 저장 구조는 설계안입니다.", options: { color: SLATE, fontSize: 11 } },
  ], { x: L, y: 4.45, w: CW, h: 0.9, fill: { color: TEAL_T }, line: { color: TEAL_T }, fontSize: 13, align: "left", margin: 12 });
  boxT(s, [
    { text: "외부 AI의 최종 답변은 MCP 호출 로그만으로 자동 검증할 수 없습니다. ", options: { bold: true, color: RED_D } },
    { text: "답변을 별도로 확보한 경우에만 사후 대조합니다.", options: { color: TXT } },
  ], { x: L, y: 5.48, w: CW, h: 0.75, fill: { color: RED_T }, line: { color: RED_T }, fontSize: 14, align: "left", margin: 12 });
  footer(s, "오류 6분류·검증 기준은 과제 M8 · 오답 원인 추적 예시(가상)는 부록 D · 원문 근거와 실행 기록의 구분은 부록 E");
  notes(s, "10 단계별 검증", {
    purpose: "최초 기획의 핵심인 판단 근거 검증을 네 단계로 나누고, 단계마다 생길 수 있는 오류와 대조 방법을 보인다. 외부 AI 답변 검증의 한계를 명시한다.",
    status: "설계안 · 검증 계획 (QueryLogger만 구현)",
    rebuttal: "“AI가 왜 그렇게 답했는지 설명할 수 있나?” → LLM의 내부 사고 과정은 설명 대상이 아니다. 기록할 수 있는 검색 경로·근거와 최종 답변이 일치하는지를 검증한다. “외부 AI 답변도 검증하나?” → MCP 호출 로그만으로는 못 한다. 답변을 따로 확보해야 대조할 수 있다.",
  }, "검증은 한 번에 하지 않고 네 단계로 나눕니다. 원문 PDF, 거기서 뽑아 정리한 관계, 그래프에서 검색한 결과, 그리고 LLM이 만든 답변입니다. 단계마다 생길 수 있는 오류가 다릅니다. 원문 단계에서는 5장에서 본 것처럼 표가 잘못 추출될 수 있고, 관계 단계에서는 상품권의 실적 제외처럼 조건이 빠지거나 적용 범위가 섞일 수 있습니다. 검색 단계에서는 다른 혜택의 조항을 잘못 붙일 수 있고, 답변 단계에서는 근거에 없는 조건을 덧붙일 수 있습니다. 그래서 단계마다 대조하는 대상을 따로 정합니다. 이걸 가능하게 하는 것이 실행 기록입니다. 저희 시스템에서 실행한 경우 질문, 실행한 쿼리, 돌려준 조건과 조항, 생성한 답변, 모델과 데이터 버전을 남길 수 있습니다. 쿼리 로그 포매터는 이미 구현돼 있고, 기록을 저장하는 구조는 설계 단계입니다. 한 가지 한계가 있습니다. 외부 AI가 고객에게 최종적으로 한 답은 카드사의 MCP 호출 로그만으로는 검증할 수 없습니다. 그 답변을 따로 확보한 경우에만 나중에 대조할 수 있습니다. 이렇게 검증한 공식 조건 조회 기능을 다른 AI 서비스에서도 쓸 수 있도록 연결하는 방식이 MCP입니다.");
}

pres.addSection({ title: "활용과 현황" });

// ---- 11 MCP ----
{
  const s = content("10   MCP", "MCP로 여러 AI가 같은 공식 조회 기능을 호출합니다", "활용과 현황");
  pills(s, ["설계안", "시연 목표"]);
  boxT(s, [
    { text: "MCP  ", options: { bold: true, color: AMBER_D } },
    { text: "“AI가 외부 서비스와 연결돼 실제 데이터를 주고받을 수 있게 하는 표준 방식” ", options: { color: TXT } },
    { text: "— 신한카드 2026-09-13 보도자료 설명", options: { color: MUTED, fontSize: 11 } },
  ], { x: L, y: 1.8, w: CW, h: 0.45, fill: { color: AMBER_T }, line: { color: AMBER_T }, fontSize: 14, align: "left", margin: 12 });
  const top = 2.6;
  T(s, "AI 클라이언트", { x: L, y: top - 0.32, w: 2.6, h: 0.28, fontSize: 12, bold: true, color: MUTED });
  ["외부 AI 서비스", "자사 AI 상담", "내부 상담·검토 AI"].forEach((t, i) => boxT(s, t, { x: L, y: top + i * 0.72, w: 2.6, h: 0.6, fill: { color: MIST }, color: INK, fontSize: 14, bold: true }));
  T(s, "연결 계층 · 판단 로직 없음", { x: 3.75, y: top - 0.32, w: 3.0, h: 0.28, fontSize: 12, bold: true, color: AMBER_D });
  boxT(s, [{ text: "MCP 서버", options: { bold: true, fontSize: 15, breakLine: true } }, { text: "외부·로컬 AI 클라이언트용", options: { fontSize: 11, color: MUTED } }], { x: 3.75, y: top, w: 2.9, h: 0.95, fill: { color: "FFFFFF" }, line: { color: AMBER, width: 2 }, color: INK });
  boxT(s, [{ text: "내부 API", options: { bold: true, fontSize: 15, breakLine: true } }, { text: "자사 시스템용", options: { fontSize: 11, color: MUTED } }], { x: 3.75, y: top + 1.1, w: 2.9, h: 0.95, fill: { color: "FFFFFF" }, line: { color: SLATE, width: 1.25 }, color: INK });
  arrow(s, L + 2.62, top + 0.3, 0.5, 0.15);
  arrow(s, L + 2.62, top + 1.02, 0.5, 0.55);
  arrow(s, L + 2.62, top + 1.74, 0.5, -0.17);
  boxT(s, [{ text: "공통 GraphRAG 엔진", options: { bold: true, fontSize: 16, breakLine: true } }, { text: "질문 해석 · 관계 검색\n근거 기반 답변", options: { fontSize: 12 } }], { x: 7.1, y: top, w: 2.75, h: 2.05, fill: { color: TEAL }, line: { color: TEAL }, color: "FFFFFF" });
  arrow(s, 6.68, top + 0.48, 0.39, 0);
  arrow(s, 6.68, top + 1.58, 0.39, 0);
  boxT(s, "공식 혜택·조건\n원문 근거", { x: 10.2, y: top, w: R - 10.2, h: 2.05, fill: { color: VIO }, line: { color: VIO }, color: "FFFFFF", fontSize: 16, bold: true });
  arrow(s, 9.88, top + 1.02, 0.29, 0);
  boxT(s, [
    { text: "MCP 도구(안)", options: { bold: true, color: INK, breakLine: true } },
    { text: "get_card_benefits(card) — 혜택·조건·근거 (필수)", options: { breakLine: true } },
    { text: "find_affected_by_condition(condition) — 영향 후보 (여유 시)", options: { breakLine: true } },
    { text: "시연 목표: 로컬 AI 클라이언트 호출 결과 = Neo4j Browser Cypher 결과", options: { bold: true, color: AMBER_D } },
  ], { x: L, y: 4.85, w: 6.0, h: 1.4, fill: { color: MIST }, color: TXT, fontSize: 12, align: "left", margin: 12 });
  boxT(s, [
    { text: "카드사가 확인할 수 있는 범위", options: { bold: true, color: INK, breakLine: true } },
    { text: "기록 가능  ", options: { bold: true, color: TEAL_D } }, { text: "공급한 조건·근거·호출 기록", options: { breakLine: true } },
    { text: "조건부  ", options: { bold: true, color: AMBER_D } }, { text: "외부 AI 최종 답변 대조 — 답변을 별도 확보할 때만", options: { breakLine: true } },
    { text: "보장 불가  ", options: { bold: true, color: RED_D } }, { text: "호출 여부 · 요약·변형 · 문구 표시", options: {} },
  ], { x: 6.85, y: 4.85, w: R - 6.85, h: 1.4, fill: { color: "FFFFFF" }, line: { color: AMBER, width: 1.25 }, color: TXT, fontSize: 12, align: "left", margin: 12 });
  footer(s, "설계안 · MCP 미구현 · 외부 플랫폼(카카오 등) 실연동은 범위 밖 · 컷라인: 3일차 오전 M8 미완료 시 도구 1개만");
  notes(s, "11 MCP로 같은 공식 정보 재사용", {
    purpose: "사업 목적(1장)과 기술 구조(6장)를 잇는다. MCP는 판단 엔진이 아니라 연결 계층이며, 여러 AI가 같은 엔진을 호출한다는 점을 보인다.",
    status: "설계안 · 시연 목표 (MCP 미구현, 외부 플랫폼 연동 없음)",
    rebuttal: "“MCP가 판단하는 것 아닌가?” → 아니다. 판단 로직은 엔진에만 있고 MCP는 연결만 한다. “카카오에 붙이나?” → 이번 범위는 로컬 AI 클라이언트 호출까지다.",
  }, "이제 1장의 구조로 돌아갑니다. MCP는 신한카드 보도자료의 표현대로, AI가 외부 서비스와 연결돼 데이터를 주고받게 하는 표준 방식입니다. 저희 구조에서 MCP는 판단을 하지 않습니다. 외부 AI나 로컬 AI 클라이언트는 MCP 서버를, 자사 시스템은 내부 API를 통해 같은 GraphRAG 엔진을 부르고, 엔진은 공식 혜택과 조건, 원문 근거를 돌려줍니다. 판단 로직은 엔진 한 곳에만 둡니다. 그래서 연동된 AI 클라이언트가 같은 버전의 공식 데이터에 같은 조건으로 도구를 호출하면, 같은 조건과 근거를 돌려주도록 설계합니다. 다만 외부 AI가 이 도구를 반드시 부르는 것은 아니고, 돌려받은 결과를 어떻게 요약해 안내할지도 카드사가 보장하지 못합니다. 카드사가 직접 기록하고 검증할 수 있는 것은 자기 엔진에 들어온 입력과 검색 결과, 근거, 반환한 데이터입니다. 구현할 도구는 카드별 혜택·조건·근거를 돌려주는 도구가 필수이고, 영향 후보를 찾는 도구는 여유가 있으면 만듭니다. 시연 목표는 로컬 AI 클라이언트로 MCP 도구를 불렀을 때의 결과가 Neo4j Browser에서 같은 Cypher를 실행한 결과와 같은지 확인하는 것입니다. 카카오 같은 외부 플랫폼과 실제로 연동하는 것은 범위 밖입니다. 그리고 카드사가 확인할 수 있는 범위는 공급한 조건과 근거, 호출 기록까지이고, 외부 AI의 최종 답변은 따로 확보해야 대조할 수 있습니다. 그럼 지금 저희가 실제로 어디까지 했는지 정리하겠습니다.");
}

// ---- 12 진행 현황 ----
{
  const s = content("11   진행 현황", "실제로 한 것과 앞으로 검증할 것", "활용과 현황");
  const lanes = [
    ["원문 확인", TEAL_T, TEAL_D, ["하나카드 4종 원문 대조 (체크 2 · 신용 2)", "PDF 텍스트·표 추출 표본 검증 (기본 옵션)", "신한 공식 발표 2건 재확인", "목표 약 10종 — 선정 전"]],
    ["코드 존재 확인", TEAL, "FFFFFF", ["카드 등록·조회 코드 및 단위 테스트 코드", "공통 기반 코드: DB·Neo4j 세션, 쿼리 로그, PDF 읽기", "참고 구현: graph_rag_sample (카드 아님)"]],
    ["설계안", SLATE, "FFFFFF", ["그래프 스키마 (카드·혜택·규칙·개념·조항)", "추출·검증 테이블 DDL 초안 (DB 미적용)", "MCP 도구 2안", "검증 기준: 오류 6분류, 파일럿 질문"]],
    ["구현·검증 예정", AMBER, INK, ["파이프라인 A(파일)·B(DB) 독립 추출 → 결과 비교", "Neo4j 적재·Cypher 탐색", "근거 기반 GraphRAG 답변", "MCP 도구 1개", "파일럿 질문 15~20개 검증"]],
  ];
  const lw = (CW - 0.15 * 3) / 4;
  lanes.forEach(([h, bg, fg, items], i) => {
    const x = L + i * (lw + 0.15);
    rect(s, { x, y: 1.85, w: lw, h: 3.75, fill: { color: "FFFFFF" }, line: { color: i === 0 ? TEAL : bg, width: 1.25 } });
    boxT(s, h, { x, y: 1.85, w: lw, h: 0.52, fill: { color: bg }, line: { color: i === 0 ? TEAL : bg }, color: fg, fontSize: 15, bold: true, rectRadius: 0.1 });
    T(s, items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })), { x: x + 0.12, y: 2.5, w: lw - 0.24, h: 3.0, fontSize: 14, color: TXT, paraSpaceAfter: 8 });
    if (i === 1) boxT(s, [
      { text: "테스트 통과 여부: 이번 검토에서 미확인", options: { bold: true, color: RED_D, breakLine: true } },
      { text: "DB 통합 테스트: 실행 기록 없음", options: { color: RED_D, fontSize: 11 } },
    ], { x: x + 0.1, y: 4.8, w: lw - 0.2, h: 0.7, fill: { color: RED_T }, line: { color: RED_T }, fontSize: 12, align: "left", margin: 8 });
  });
  boxT(s, [
    { text: "2인 팀 우선순위  ", options: { bold: true, color: AMBER } },
    { text: "① 4종 추출·관계 검증 → ② Neo4j·Cypher → ③ 근거 기반 답변 → ④ MCP 도구 1개 → ⑤ 검증·실패 사례 → ⑥ 약 10종 (여력 시)", options: { color: "FFFFFF" } },
  ], { x: L, y: 5.72, w: CW, h: 0.55, fill: { color: INK }, line: { color: INK }, fontSize: 12, align: "left", margin: 12 });
  footer(s, "2026-10-30 저장소 확인: card_benefit/README.md · payment_card · src/common · sql · 저장소에 카드 코드의 테스트 실행 기록 없음");
  notes(s, "12 실제로 한 것과 앞으로 검증할 것", {
    purpose: "원문 확인 · 구현 완료 · 설계안 · 예정을 한 장에서 구분해 신뢰를 확보한다. 과제 필수 요소(두 독립 파이프라인)를 빠뜨리지 않는다.",
    status: "2026-10-30 저장소 기준",
    rebuttal: "“아직 핵심은 하나도 안 된 것 아닌가?” → 맞다. 원문 분석·추출 검증·설계와 공통 기반까지가 현재다. 그래서 우선순위와 컷라인을 정해 두었다.",
  }, "지금까지 말씀드린 것 중 무엇이 실제로 된 것인지 구분하겠습니다. 원문 확인한 것은 하나카드 4종의 상품설명서 대조, PDF 추출 표본 검증, 신한 발표 재확인입니다. 약 10종은 목표이고 아직 선정 전입니다. 코드로 확인한 것은 PostgreSQL 카드 상품 등록·조회 코드와 그 단위 테스트 코드, 그리고 팀 공통 기반인 DB·Neo4j 연결, 쿼리 로그, PDF 페이지 텍스트 읽기 코드입니다. 다만 테스트가 통과하는지는 이번 검토에서 확인하지 않았고, DB 통합 테스트도 실행 기록이 없습니다. 코드가 있다는 것과 정상 동작이 검증됐다는 것은 구분해서 말씀드립니다. graph_rag_sample은 참고 구현이고 카드 도메인 코드가 아닙니다. 설계만 된 것은 그래프 스키마, 추출·검증 테이블 초안, MCP 도구안, 검증 기준입니다. 앞으로 할 일은 과제가 요구하는 대로 파일 기반과 DB 기반 두 파이프라인으로 각자 추출해 결과를 비교하고, Neo4j에 적재해 Cypher로 탐색하고, 근거 기반 답변과 MCP 도구 하나를 만든 뒤 파일럿 질문으로 검증하는 것입니다. 2인 팀이라 대표 4종을 먼저 끝내고, 여력이 있으면 10종으로 넓힙니다. 마지막으로, 이 작업이 완성됐을 때의 의미로 마무리하겠습니다.");
}

pres.addSection({ title: "결론" });

// ---- 13 결론 ----
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "결론" });
  T(s, "결론", { x: 0.7, y: 0.55, w: 3, h: 0.3, fontSize: 13, bold: true, color: AMBER });
  T(s, "처음 질문 — 고객이 AI에게 카드 혜택을 물으면, 공식 정보는 어디에서 올까요?", { x: 0.7, y: 0.92, w: 12, h: 0.32, fontSize: 14, color: DARK_SUB });
  T(s, "AI 채널이 달라져도, 카드사가 제공하는 공식 혜택 조건과\n근거는 일관되게 관리할 수 있어야 합니다.", { x: 0.7, y: 1.4, w: 12, h: 1.4, fontSize: 28, bold: true, color: "FFFFFF", lineSpacingMultiple: 1.1 });
  const p = [
    ["왜 필요한가", "카드사", "공식 상품정보와 약관 근거를 관리하고 외부 AI에 제공"],
    ["왜 GraphRAG인가", "GraphRAG", "복잡한 혜택·조건·원문 근거의 관계를 구조화하고 탐색·검증"],
    ["왜 MCP인가", "MCP", "구현한 공식 조회 기능을 여러 AI 클라이언트에서 재사용"],
  ];
  const pw = (12.03 - 0.6) / 3;
  p.forEach((t, i) => {
    const x = 0.7 + i * (pw + 0.3);
    rect(s, { x, y: 3.05, w: pw, h: 1.85, fill: { color: i === 1 ? TEAL_D : INK2 }, line: { color: i === 1 ? TEAL_D : INK2 } });
    T(s, t[0], { x: x + 0.25, y: 3.2, w: pw - 0.5, h: 0.28, fontSize: 12, bold: true, color: i === 1 ? "BFEDE6" : AMBER });
    T(s, t[1], { x: x + 0.25, y: 3.5, w: pw - 0.5, h: 0.45, fontSize: 22, bold: true, color: "FFFFFF", valign: "middle" });
    T(s, t[2], { x: x + 0.25, y: 4.05, w: pw - 0.5, h: 0.75, fontSize: 14, color: "D5DEEA", lineSpacingMultiple: 1.1 });
  });
  T(s, [
    { text: "현재  ", options: { bold: true, color: "7FD6C9" } },
    { text: "하나카드 4종 원문 대조 · PDF 추출 표본 검증 · 카드 등록·조회 코드와 공통 기반 코드", options: { color: "D5DEEA", breakLine: true } },
    { text: "다음  ", options: { bold: true, color: AMBER } },
    { text: "두 파이프라인 추출 → Neo4j·Cypher → 근거 기반 답변 → MCP 도구 1개 → 파일럿 검증 (약 10종은 여력 시)", options: { color: "D5DEEA" } },
  ], { x: 0.7, y: 5.2, w: 12, h: 0.8, fontSize: 14, lineSpacingMultiple: 1.25 });
  T(s, "SQL 대비 우위는 단정하지 않고, 같은 질문으로 비교해 확인하겠습니다.", { x: 0.7, y: 6.25, w: 12, h: 0.4, fontSize: 15, bold: true, color: AMBER });
  notes(s, "13 결론", {
    purpose: "1장 질문에 답하고, 청중이 기억할 세 가지(왜 필요한가·왜 GraphRAG·왜 MCP)를 남긴다. 현재와 다음을 구분해 끝낸다.",
    status: "—",
    rebuttal: "“결국 아직 구현은 거의 없다” → 그렇다. 무엇을 확인했고 무엇을 검증할지를 구분해 말한다.",
  }, "처음 질문으로 돌아가겠습니다. 고객이 AI에게 카드 혜택을 물으면, 공식 정보는 어디에서 와야 할까요. 저희의 답은 이것입니다. AI 채널이 달라져도, 카드사가 제공하는 공식 혜택 조건과 근거는 일관되게 관리할 수 있어야 합니다. 세 가지만 기억해 주십시오. 왜 필요한가. 카드사의 공식 정보를 외부 AI에 제공하기 위해서입니다. 왜 GraphRAG인가. 복잡한 혜택과 조건, 원문 근거의 관계를 구조화하고 탐색하는 방법을 검증하기 위해서입니다. 왜 MCP인가. 그렇게 만든 공식 조회 기능을 여러 AI 클라이언트에서 재사용하기 위해서입니다. 현재는 하나카드 4종의 원문 대조와 PDF 추출 검증, 기본 코드까지 왔고, 다음은 두 파이프라인 추출부터 MCP 도구까지입니다. SQL보다 낫다고 단정하지 않고, 같은 질문으로 비교해 확인하겠습니다. 감사합니다.");
}

// ===================== APPENDIX =====================
pres.addSection({ title: "부록" });

// A — 과제 수행 증빙
{
  const s = content("부록 A   과제 수행 증빙", "M0~M9와 현재 상태 (2026-10-30 저장소 기준)", "부록");
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: INK } } });
  const st = (t, k) => ({ text: t, options: { color: k === "d" ? TEAL_D : k === "p" ? AMBER_D : RED_D, bold: true } });
  s.addTable([
    [H("과제"), H("카드 엔진에서 할 일"), H("관련 쪽"), H("현재 상태")],
    ["M0 주제·문서", "대표 4종 우선, 체크·신용 약 10종 목표", "3·4·12", st("4종 원문 대조 완료 / 약 10종 선정 전", "p")],
    ["M1 전처리", "텍스트 추출·청크·원문 위치 ID", "5·6", st("표본 추출 검증 완료 · 공통 PDF 읽기 있음 / 카드 파이프라인 미구현", "p")],
    ["M2 온톨로지", "카드·혜택·규칙·공통 개념·조항", "6·부록 B", st("설계안", "p")],
    ["M3·M4 LLM 추출", "근거 문장·조항 ID 필수 JSON, 실패 처리", "6·10", st("미구현", "x")],
    ["M5 정규화", "공통 개념 연결, 카드별 규칙 분리 보존", "8", st("미구현", "x")],
    ["M6 Neo4j 적재", "MERGE 재적재, 근거 속성 보존", "6", st("미구현 — Neo4j 세션 공통 기반 있음", "x")],
    ["M7 Cypher", "조건 조회 · 영향 후보 · 근거 경로", "7·8", st("미구현 — 기대 결과는 원문 수작업 도출", "x")],
    ["M8 검증", "원문–관계–그래프–답변 대조, 오류 6분류", "10·부록 C", st("미구현 — 기준·파일럿 질문 정의", "x")],
    ["M9 통합·MCP", "문서 → 그래프 → MCP 한 흐름", "11", st("미구현 — 도구 2안, 컷라인", "x")],
    ["파이프라인 A·B", "파일 기반 / DB 기반 독립 추출 → 결과 비교", "12", st("미구현 — DB 테이블 DDL 초안(미적용)", "x")],
    ["코드 존재", "카드 등록·조회 코드 + 단위 테스트 코드", "12", st("코드 존재 확인 · 테스트 통과 미확인", "p")],
  ], { x: L, y: 1.8, w: CW, colW: [2.1, 4.3, 1.3, 4.43], rowH: 0.4, fontFace: F, fontSize: 12, color: TXT, border: tblBorder, valign: "middle", margin: [2, 6, 2, 6] });
  footer(s, "출처: 과제_매핑표_10.29.md · card_benefit/README.md · src/common · sql/hana_card_schema_draft.sql");
  notes(s, "부록 A 과제 수행 증빙", { purpose: "과제 M0~M9와 두 독립 파이프라인의 현재 상태를 저장소 기준으로 공개한다.", status: "2026-10-30 저장소 확인", rebuttal: "—" },
    "과제 M0부터 M9까지와 두 독립 파이프라인의 현재 상태입니다. 원문 대조와 추출 표본 검증, 카드 등록 프로그램과 공통 기반까지가 완료이고, 나머지는 설계 또는 미구현입니다.");
}

// B — 그래프 설계안
{
  const s = content("부록 B   그래프 설계안 (M2)", "카드별 규칙은 따로, 같은 대상은 공통 개념으로 연결합니다", "부록");
  pills(s, ["설계안"]);
  const y1 = 2.25, y2 = 3.85, nh = 0.75, nw = 2.15;
  const xs = [L, 3.75, 6.9, 10.05];
  node(s, "Card\n카드 상품", "card", xs[0], y1, nw, nh);
  node(s, "Benefit\n혜택", "benefit", xs[1], y1, nw, nh);
  node(s, "Rule\n실적 조건", "cond", xs[2], y1, nw, nh);
  node(s, "Rule\n제외 규칙 {scope, 문서 판}", "item", xs[3], y1, 2.68, nh);
  ["HAS_BENEFIT", "REQUIRES", "EXCLUDES"].forEach((t, i) => {
    arrow(s, xs[i] + nw + 0.03, y1 + nh / 2, xs[i + 1] - xs[i] - nw - 0.06, 0, SLATE);
    T(s, t, { x: xs[i] + nw - 0.2, y: y1 - 0.32, w: 1.6, h: 0.26, fontSize: 10, bold: true, color: SLATE, fontFace: MONO, align: "center" });
  });
  node(s, "Trace\n실행 기록 (설계 메모)", "grey", xs[0], y2, nw, nh, { line: { color: "A0AAB8", width: 1, dashType: "dash" } });
  node(s, "Rule\n월 한도", "cond", xs[1], y2, nw, nh);
  node(s, "Clause\n공식 조항", "clause", xs[2], y2, nw, nh);
  node(s, "Concept\n상품권 구매 (공통)", "grey", xs[3], y2, 2.68, nh, { fill: { color: RED_T }, line: { color: RED, width: 1.25 }, color: RED_D });
  arrow(s, xs[1] + nw / 2, y1 + nh + 0.03, 0, y2 - y1 - nh - 0.06, SLATE);
  T(s, "LIMITED_BY", { x: xs[1] + nw / 2 + 0.08, y: y1 + nh + 0.18, w: 1.3, h: 0.26, fontSize: 10, bold: true, color: SLATE, fontFace: MONO });
  arrow(s, xs[2] + nw / 2, y1 + nh + 0.03, 0, y2 - y1 - nh - 0.06, SLATE);
  T(s, "SOURCED_FROM", { x: xs[2] + nw / 2 + 0.08, y: y1 + nh + 0.18, w: 1.4, h: 0.26, fontSize: 10, bold: true, color: SLATE, fontFace: MONO });
  arrow(s, xs[3] + 1.34, y1 + nh + 0.03, 0, y2 - y1 - nh - 0.06, RED);
  T(s, "REFERS_TO", { x: xs[3] + 1.42, y: y1 + nh + 0.18, w: 1.2, h: 0.26, fontSize: 10, bold: true, color: RED_D, fontFace: MONO });
  T(s, "USED → 경로상의 노드", { x: xs[0], y: y2 + nh + 0.05, w: nw, h: 0.26, fontSize: 10, color: SLATE, fontFace: MONO, align: "center" });
  T(s, [
    { text: "규칙은 카드별로 따로 저장하고, 같은 대상(상품권 구매)만 공통 개념으로 연결합니다. 정책이 같다고 가정해 규칙을 합치지 않습니다.", options: { bold: true, color: INK, breakLine: true } },
    { text: "모든 관계 속성: document_id · page · evidence(원문 문장) · 문서 판", options: { color: SLATE } },
  ], { x: L, y: 4.98, w: CW, h: 0.62, fontSize: 12, lineSpacingMultiple: 1.1 });
  boxT(s, "// 영향 후보 조회 (예시 Cypher, 미실행)\nMATCH (x:Concept {name:'상품권 구매'})<-[:REFERS_TO]-(r:Rule {scope:'실적'})<-[:EXCLUDES]-(c:Rule)<-[:REQUIRES]-(b:Benefit)<-[:HAS_BENEFIT]-(k:Card)\nOPTIONAL MATCH (r)-[:SOURCED_FROM]->(cl:Clause)\nRETURN k.name AS card, b.name AS benefit, r.doc_version AS version, cl.id AS clause", { x: L, y: 5.68, w: CW, h: 1.2, fill: { color: INK }, line: { color: INK }, color: "E6ECF4", fontFace: MONO, fontSize: 10, align: "left", valign: "top", margin: 10 });
  footer(s, "과제_매핑표_10.29.md M2 안을 카드별 규칙 분리로 보완 · Trace는 설계 메모 · 쿼리는 설계 예시이며 실행 결과 아님");
  notes(s, "부록 B 그래프 설계안", { purpose: "8장의 '공통 개념 + 카드별 규칙' 모델을 노드·관계로 보인다.", status: "설계안", rebuttal: "—" },
    "그래프 설계안입니다. 카드, 혜택, 실적 조건, 제외 규칙, 조항을 노드로 둡니다. 제외 규칙은 카드별로 따로 두고 적용 범위와 문서 판을 속성으로 남기며, 상품권 구매 같은 대상만 공통 개념 노드로 연결합니다. 모든 관계에 원문 위치와 문장을 붙입니다.");
}

// C — 파일럿 검증 계획
{
  const s = content("부록 C   파일럿 검증 계획", "초기 파일럿 — 결과 칸은 실행한 뒤에만 채웁니다", "부록");
  pills(s, ["검증 계획"]);
  T(s, "하나카드 4종 약관에서 파일럿 질문 15~20개 · 정답 기준은 원문 조항", { x: L, y: 1.82, w: 6.2, h: 0.5, fontSize: 13, bold: true, color: INK });
  [
    "상품권 구매가 전월실적에서 제외되는가?",
    "상품권 구매가 혜택 적용에서도 제외되는가?",
    "특정 혜택의 전월실적 기준은 얼마인가?",
    "신규 사용 등록 예외는 어느 혜택에 적용되는가?",
    "유사 혜택을 가진 카드들의 조건은 어떻게 다른가?",
    "하나의 조건 변경이 어떤 혜택에 영향을 줄 수 있는가?",
  ].forEach((q, i) => {
    const y = 2.4 + i * 0.6;
    chip(s, "Q" + (i + 1), L, y, 0.6, 0.48, AMBER_T, AMBER_D);
    T(s, q, { x: L + 0.75, y, w: 5.4, h: 0.48, fontSize: 13, color: TXT, valign: "middle" });
  });
  T(s, "15~20개 질문은 초기 파일럿입니다. 일반적인 성능 우위를 입증하지 않으며, 불리한 결과도 공개합니다.", { x: L, y: 6.1, w: 6.2, h: 0.6, fontSize: 12, color: RED_D });
  const H = (t, bg) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: bg || SLATE }, align: "center" } });
  const e = { text: "—", options: { color: "A0AAB8", align: "center", fill: { color: MIST } } };
  rect(s, { x: 7.0, y: 1.85, w: 5.73, h: 2.05, fill: { color: AMBER_T }, line: { color: AMBER_T } });
  T(s, [
    { text: "공정 비교 조건 — 세 방식 공통", options: { bold: true, color: AMBER_D, fontSize: 13, breakLine: true } },
    { text: "같은 평가 질문과 원문 정답, 같은 상품설명서 버전", options: { bullet: true, breakLine: true } },
    { text: "방식별 문서 추출·구조화 범위를 기록", options: { bullet: true, breakLine: true } },
    { text: "수작업 정제·보정량, LLM 사용 조건·비용을 기록", options: { bullet: true, breakLine: true } },
    { text: "전처리는 방식마다 달라도 되며, 차이와 투입 비용을 함께 비교", options: { bullet: true, breakLine: true } },
    { text: "실험의 한계와 실패 사례를 공개", options: { bullet: true } },
  ], { x: 7.15, y: 1.92, w: 5.45, h: 1.95, fontSize: 12, color: TXT, paraSpaceAfter: 2 });
  const metrics = ["답변 정확도", "조건 누락률", "원문 근거 정확도", "조건 적용 범위 정확도", "영향 후보 정밀도·재현율", "검색 결과–답변 일치"];
  s.addTable([[H("평가 지표"), H("벡터 RAG"), H("SQL"), H("GraphRAG")]].concat(metrics.map((m) => [{ text: m, options: { bold: true, color: INK } }, e, e, e])), { x: 7.0, y: 4.05, w: 5.73, colW: [2.55, 1.06, 1.06, 1.06], rowH: 0.36, fontFace: F, fontSize: 12, color: TXT, border: tblBorder, valign: "middle", margin: [2, 6, 2, 6] });
  footer(s, "— : 미실행, 수치는 실험 후에만 기입 · 과제 M8 · 선택 과제 S1(비교 실험)은 필수 M0~M9 완료 후 수행");
  notes(s, "부록 C 파일럿 검증 계획", { purpose: "9장 비교와 10장 검증을 실제로 확인할 질문, 공정 비교 조건, 평가 지표를 보인다.", status: "검증 계획 (미실행)", rebuttal: "—" },
    "검증 계획입니다. 하나카드 4종의 약관에서 15~20개의 파일럿 질문을 만들고, 정답은 원문 조항을 기준으로 합니다. 세 방식에는 같은 공식 PDF와 문서 버전, 같은 질문과 원문 정답을 씁니다. 전처리는 방식마다 다를 수 있으므로 각 방식의 추출·구조화 범위, 수작업 보정량, LLM 사용 조건과 비용을 함께 기록하고, 답변 정확도, 조건 누락, 근거 정확도, 적용 범위, 영향 후보의 정밀도와 재현율, 답변 일치를 비교합니다. 실패 사례와 한계도 공개합니다. 초기 파일럿이라 일반적인 우위를 증명하지는 않습니다.");
}

// D — 오답 원인 추적 예시 (가상)
{
  const s = content("부록 D   오답 원인 추적 예시", "틀린 답이 어느 단계에서 생겼는지 찾아 고치고 다시 확인합니다", "부록");
  pills(s, ["가상 상황"]);
  boxT(s, "가상 오류 시나리오 — 실제 실행 로그가 아닙니다 (구현 후 실제 로그로 교체)", { x: L, y: 1.78, w: CW, h: 0.42, fill: { color: RED_T }, line: { color: RED, width: 1 }, color: RED_D, fontSize: 14, bold: true, align: "left", margin: 12 });
  const y1 = 2.35, h1 = 1.1;
  boxT(s, [{ text: "질문", options: { bold: true, color: MUTED, fontSize: 11, breakLine: true } }, { text: "STYLE 대중교통 캐시백 실적에 상품권 구매도 포함되나요?", options: { color: INK } }], { x: L, y: y1, w: 3.3, h: h1, fill: { color: MIST }, fontSize: 13, align: "left", margin: 10 });
  arrow(s, L + 3.32, y1 + h1 / 2, 0.26, 0);
  boxT(s, [{ text: "AI 오답", options: { bold: true, color: AMBER, fontSize: 11, breakLine: true } }, { text: "“네, 국내외 일시불 이용금액이라 포함됩니다”", options: { color: "FFFFFF" } }], { x: 4.2, y: y1, w: 2.75, h: h1, fill: { color: INK2 }, line: { color: INK2 }, fontSize: 13, align: "left", margin: 10 });
  arrow(s, 6.97, y1 + h1 / 2, 0.26, 0);
  const cw2 = (R - 7.25 - 0.15) / 2;
  boxT(s, [{ text: "잘못 저장된 관계", options: { bold: true, color: RED_D, fontSize: 12, breakLine: true } }, { text: "상품권 → ‘서비스 제외’에만 연결, ‘실적 제외’ 누락", options: { color: TXT } }], { x: 7.25, y: y1, w: cw2, h: h1, fill: { color: RED_T }, line: { color: RED_T }, fontSize: 12, align: "left", margin: 9 });
  boxT(s, [{ text: "원문", options: { bold: true, color: TEAL_D, fontSize: 12, breakLine: true } }, { text: "상품권은 실적 제외 대상이면서 서비스 제외 대상", options: { color: TXT } }], { x: 7.25 + cw2 + 0.15, y: y1, w: cw2, h: h1, fill: { color: TEAL_T }, line: { color: TEAL_T }, fontSize: 12, align: "left", margin: 9 });
  T(s, "단계별 산출물을 원문과 대조해 오류 위치를 찾습니다", { x: L, y: 3.65, w: CW, h: 0.3, fontSize: 14, bold: true, color: INK });
  const st = ["① PDF 추출", "② 조건·범위 추출", "③ 관계 정규화", "④ 그래프 검색", "⑤ LLM 답변"];
  const tag = ["원문 문장 있음", "오류 지점: scope 누락", "②의 오류가 전파", "잘못된 관계를 조회", "다른 유형: 근거 무시"];
  const bw = 2.2, bg = (CW - bw * 5) / 4;
  st.forEach((t, i) => {
    const x = L + i * (bw + bg);
    const err = i === 1, alt = i === 4;
    boxT(s, t, { x, y: 4.05, w: bw, h: 0.68, fill: { color: err ? RED_T : MIST }, line: err ? { color: RED, width: 2.5 } : alt ? { color: AMBER, width: 1.25, dashType: "dash" } : { color: MIST }, color: err ? RED_D : INK, fontSize: 14, bold: true, margin: 4 });
    T(s, tag[i], { x, y: 4.78, w: bw, h: 0.3, fontSize: 11, bold: err || alt, color: err ? RED_D : alt ? AMBER_D : MUTED, align: "center" });
    if (i < 4) arrow(s, x + bw + 0.02, 4.39, bg - 0.04, 0);
  });
  const fx = ["수정: 상품권 실적 제외 관계 보정", "재적재", "같은 질문 재검증", "결과: 실적에 포함되지 않음 (원문 근거)"];
  const fw = [3.4, 1.5, 2.2, 4.13], fg = (CW - fw.reduce((a, b) => a + b, 0)) / 3;
  let fxx = L;
  fx.forEach((t, i) => {
    chip(s, t, fxx, 5.35, fw[i], 0.5, i === 3 ? TEAL : AMBER_T, i === 3 ? "FFFFFF" : AMBER_D, { fontSize: 13 });
    if (i < 3) arrow(s, fxx + fw[i] + 0.02, 5.6, fg - 0.04, 0);
    fxx += fw[i] + fg;
  });
  T(s, "목표는 ‘전부 맞힌다’가 아니라 ‘틀린 지점을 찾을 수 있다’입니다. 고치지 못한 항목은 판단 보류로 공개합니다.", { x: L, y: 6.1, w: CW, h: 0.6, fontSize: 13, bold: true, color: INK });
  footer(s, "V4의 상품권 오답 사례를 개인 적격성 질문이 아닌 공식 조건 질문으로 바꿔 재구성 · 오류 6분류는 과제 M8");
  notes(s, "부록 D 오답 원인 추적 예시", {
    purpose: "10장 검증의 구체 예. 상품권 실적 제외 누락이라는 원문 기반 함정으로 원인 단계 → 수정 → 재검증 루프를 보인다.",
    status: "가상 상황 (실제 실행 로그 아님)",
    rebuttal: "“일부러 만든 오류 아닌가?” → 맞다. 원문에서 확인한 함정으로 만든 가상 시나리오이며, 구현 후 실제 로그로 바꾼다.",
  }, "오답 원인 추적의 예시입니다. 가상 시나리오입니다. STYLE 대중교통 캐시백 실적에 상품권 구매도 포함되느냐고 물었는데 AI가 포함된다고 답했다고 하겠습니다. 원문에서 상품권은 실적 제외 대상입니다. 단계별 산출물을 원문과 대조하면, PDF 추출 단계에는 원문 문장이 있었지만 조건과 적용 범위를 추출하는 두 번째 단계에서 실적 제외 관계가 빠졌고, 그 오류가 검색과 답변까지 전파됐다는 것을 찾을 수 있습니다. 관계를 고치고 다시 적재한 뒤 같은 질문으로 재검증합니다.");
}

// E — 원문 근거 vs 실행 기록, 외부 AI 범위
{
  const s = content("부록 E   검증 대상의 구분", "원문 근거와 실행 기록은 다르고, 외부 AI 답변은 별도입니다", "부록");
  pills(s, ["설계안"]);
  const col = (x, w, bg, fg, ln, h1, h2, items) => {
    rect(s, { x, y: 1.85, w, h: 2.55, fill: { color: "FFFFFF" }, line: { color: ln, width: 1.25 } });
    boxT(s, [{ text: h1, options: { bold: true, fontSize: 15, color: fg, breakLine: true } }, { text: h2, options: { fontSize: 11, color: fg } }], { x, y: 1.85, w, h: 0.7, fill: { color: bg }, line: { color: bg }, align: "left", margin: 12, rectRadius: 0.1 });
    T(s, items.map((t, j) => ({ text: t, options: { bullet: true, breakLine: j < items.length - 1 } })), { x: x + 0.2, y: 2.65, w: w - 0.4, h: 2.0, fontSize: 13, color: TXT, paraSpaceAfter: 3 });
  };
  col(L, 5.9, TEAL_T, TEAL_D, TEAL, "A. 원문 근거", "PDF에 있음 · 지식화 단계에서 저장", ["문서 ID · 판 · 페이지", "조항 위치(표·항목 이름)와 원문 문장", "추출한 조건과 적용 범위(scope)", "조건 ↔ 혜택 ↔ 카드 관계"]);
  col(6.83, R - 6.83, AMBER_T, AMBER_D, AMBER, "B. 실행 기록 (trace)", "PDF에 없음 · 우리 시스템 실행 시 기록", ["질문과 해석 결과", "실행한 쿼리·파라미터와 조회 결과", "반환한 조건·조항", "생성 답변과 근거 일치 여부", "프롬프트·모델·데이터 버전"]);
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: INK } } });
  s.addTable([
    [H("외부 AI 경유 시"), H("카드사가 할 수 있는 것"), H("전제")],
    [{ text: "기록 가능", options: { bold: true, color: TEAL_D } }, "MCP 요청 파라미터, 공급한 조건·근거·trace id", "카드사 서버 로그 (설계안)"],
    [{ text: "조건부", options: { bold: true, color: AMBER_D } }, "고객 질문 원문, 외부 AI 최종 답변과 근거 대조", "답변을 별도로 확보한 경우만"],
    [{ text: "보장 불가", options: { bold: true, color: RED_D } }, "도구 호출 여부, 요약·변형, 문구 표시", "—"],
  ], { x: L, y: 4.65, w: CW, colW: [2.0, 6.2, 3.93], rowH: 0.45, fontFace: F, fontSize: 12, color: TXT, border: tblBorder, valign: "middle", margin: [2, 6, 2, 6] });
  footer(s, "그래프 경로 제시 ≠ LLM 내부 사고 과정 설명 · QueryLogger(쿼리 로그 포매터)는 구현, trace 저장 구조는 설계안");
  notes(s, "부록 E 검증 대상의 구분", { purpose: "원문 근거와 실행 기록, 외부 AI 경유 시 검증 범위를 구분한다.", status: "설계안", rebuttal: "—" },
    "원문 근거는 PDF 안에 있는 것이고, 실행 기록은 저희 시스템이 질문마다 실행하면서 남기는 것입니다. 외부 AI를 거치면 카드사가 기록할 수 있는 것은 공급한 내용까지이고, 최종 답변은 별도로 확보해야 대조할 수 있습니다.");
}

// F — 예상 질문
{
  const s = content("부록 F   예상 질문", "받을 질문을 먼저 정리했습니다", "부록");
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: INK } } });
  const q = (t) => ({ text: t, options: { bold: true, color: INK, fill: { color: MIST } } });
  s.addTable([
    [H("질문"), H("답변 요지")],
    [q("특정 고객이 혜택을 받는지 알려 주나요?"), "아니요. 개인 실적·등록일·거래 내역은 쓰지 않습니다. 공식 약관의 조건과 적용 범위만 분석·안내합니다."],
    [q("SQL로도 되지 않나요?"), "됩니다. 관계 테이블·JOIN·재귀 CTE로 가능합니다. 그래프 방식의 장단점을 같은 질문으로 비교해 확인합니다."],
    [q("일반 RAG도 원문 근거를 보여 주지 않나요?"), "보여 줍니다. 차이는 적용 범위와 다단계 관계를 어떻게 저장·검증하느냐이며, 파일럿으로 비교합니다."],
    [q("신한카드가 GraphRAG를 쓰나요? 두 발표는 연결돼 있나요?"), "공식 자료에 없습니다(미확인). 외부 AI 연결이 실제로 시작됐다는 근거로만 인용했습니다."],
    [q("외부 AI가 카드사 도구를 반드시 쓰나요?"), "아닙니다. 호출 여부와 최종 답변은 외부 AI가 결정합니다. 신한 사례도 고객이 툴을 추가해 이용합니다."],
    [q("외부 AI의 최종 답변도 검증할 수 있나요?"), "MCP 호출 기록만으로는 불가합니다. 최종 답변을 별도로 확보한 경우에만 사후 대조합니다."],
    [q("AI(LLM)의 사고 과정까지 설명하나요?"), "아니요. 기록 가능한 검색 경로·근거와 최종 답변의 일치 여부만 검증합니다."],
    [q("카드사의 정본은 내부 상품 DB 아닌가요?"), "PDF는 고객에게 고지된 문구입니다. 내부 DB와 고지 문서의 불일치를 점검하는 보완 용도로 제안합니다(내부 구조 미확인)."],
    [q("문서가 최신인가요? 재배포는요?"), "시행일·유효 여부·재배포 조건은 미확인입니다. 문서 판과 해시를 기록하고 PDF는 저장소에 넣지 않습니다."],
  ], { x: L, y: 1.75, w: CW, colW: [4.3, 7.83], rowH: 0.48, fontFace: F, fontSize: 11, color: TXT, border: tblBorder, valign: "middle", margin: [2, 6, 2, 6] });
  footer(s, "V4 예상 질문을 V5 범위(개인 적격성 제외, 공정 비교, 외부 AI 답변 검증 한계)에 맞춰 갱신");
  notes(s, "부록 F 예상 질문", { purpose: "예상 반박과 답변 요지.", status: "—", rebuttal: "—" },
    "예상 질문입니다. 가장 먼저 나올 질문은 개인 혜택 여부와 SQL 비교일 것입니다. 개인 데이터는 쓰지 않고, SQL로도 가능하다고 인정한 뒤 비교 계획으로 답합니다.");
}

// G — 출처와 검증 상태
{
  const s = content("부록 G   출처와 검증 상태", "무엇을 확인했고, 무엇을 정정했는가", "부록");
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: INK } } });
  const ok = (t) => ({ text: t, options: { color: TEAL_D, bold: true } });
  s.addTable([
    [H("자료"), H("사용한 내용"), H("상태")],
    ["신한금융그룹 보도자료 2026-09-09 “신한카드, 최적의 금융상품 추천하고 선택하는 AI 개발”", "커넥셔너리와 개발, 기존 생성형 AI의 한계, 조건 구조화", ok("공식 확인 2026-10-30")],
    ["신한카드 보도자료 2026-09-13 “카드사 최초 ‘ChatGPT for Kakao’와 연계한 AI 대화형 금융 서비스”", "기능 4종, PlayMCP 기반 카카오 툴즈 연동, MCP 설명 문장", ok("공식 확인 2026-10-30")],
    ["하나카드 상품설명서 STYLE·PLAY·BT·에너지 더블", "대중교통 조건, 상품권 실적·서비스 제외, 혜택별 실적 조건", ok("원문 확인 2026-10-30")],
    ["card_pdf_structuring_validation.md", "표 추출 실패 사례 (STYLE·PLAY 0개, BT 셀 병합, 에너지 더블 열 누락)", ok("팀 검증 2026-10-29")],
    ["card_benefit/README.md · src/common · payment_card · sql", "구현 상태", ok("저장소 확인 2026-10-30")],
  ], { x: L, y: 1.8, w: CW, colW: [5.6, 4.43, 2.1], rowH: 0.5, fontFace: F, fontSize: 11, color: TXT, border: tblBorder, valign: "middle", margin: [2, 6, 2, 6] });
  rect(s, { x: L, y: 4.95, w: CW, h: 1.62, fill: { color: AMBER_T }, line: { color: AMBER_T } });
  T(s, [
    { text: "정정 사항", options: { bold: true, color: AMBER_D, fontSize: 13, breakLine: true } },
    { text: "V3 ‘대중교통 5% 할인’ → 원문은 ‘5% 캐시백, 월 최대 1천원’ (V4부터 반영)", options: { bullet: true, breakLine: true } },
    { text: "V4의 9월 9일 발표 제목은 의역이었음 → V5는 원제목 사용", options: { bullet: true, breakLine: true } },
    { text: "V4의 ‘실적·등록일 정보를 요청해 판단’ 표현 삭제 — 개인 적격성 판단은 범위 밖", options: { bullet: true, breakLine: true } },
    { text: "V4의 ○·△·× 비교표 → V5는 구현 방식 차이만 기술 (우열 표시 삭제)", options: { bullet: true, breakLine: true } },
    { text: "STYLE 문서는 15650_20260429판 기준. 일부 조사 문서의 15650_20260316판과는 대조하지 않음", options: { bullet: true } },
  ], { x: L + 0.2, y: 5.03, w: CW - 0.4, h: 1.78, fontSize: 12, color: TXT, paraSpaceAfter: 2 });
  footer(s, "원문 PDF는 저장소에 추가하지 않았습니다 (재배포 조건 미확인).");
  notes(s, "부록 G 출처와 검증 상태", { purpose: "출처·검증 상태·정정 이력을 공개한다.", status: "—", rebuttal: "—" },
    "출처와 검증 상태입니다. V5에서는 신한 9월 9일 발표 제목을 원제목으로 바꿨고, 개인 적격성 판단을 연상시키는 표현과 우열 기호 비교표를 삭제했습니다.");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  if (process.env.PPTX_SKILL) {
    const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");
    await applyTheme(OUT, THEME);
  }
  if (NOTES_OUT) {
    const md = NOTES.map((n, i) => [
      `## ${i + 1}. ${n.label}`,
      "",
      `- **목적:** ${n.purpose}`,
      `- **상태:** ${n.status}`,
      `- **예상 반박:** ${n.rebuttal}`,
      "",
      "**발표 대본**",
      "",
      `> ${n.script}`,
      "",
    ].join("\n")).join("\n");
    fs.writeFileSync(NOTES_OUT, md, "utf8");
  }
  console.log("written", OUT, NOTES.length, "slides");
})();
