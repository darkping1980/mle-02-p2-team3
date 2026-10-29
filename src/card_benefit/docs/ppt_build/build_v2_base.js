// 카드 혜택 GraphRAG 발표 deck 생성기 (pptxgenjs)
const pptxgen = require("pptxgenjs");
const path = require("path");
const { applyTheme } = require(process.env.PPTX_SKILL + "/scripts/apply_theme.js");

const OUT = process.argv[2];
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
pres.title = "카드 혜택 공통 판단 엔진 — 하나카드 상품설명서 기반 GraphRAG";
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
  "공식 확인": [TEAL_T, TEAL_D], "원문 확인": [TEAL_T, TEAL_D], "구현 완료": [TEAL_T, TEAL_D],
  "시연 예정": [AMBER_T, AMBER_D], "검증 예정": [AMBER_T, AMBER_D], "가설 · 검증 예정": [AMBER_T, AMBER_D],
  "설계안": [SLATE_T, SLATE], "팀 해석": [SLATE_T, SLATE], "팀 가설": [SLATE_T, SLATE],
  "확장 제안": [VIO_T, VIO], "미실행": [RED_T, RED_D],
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

// ===================== MAIN =====================
pres.addSection({ title: "도입" });

// ---- S1 hook ----
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "도입" });
  T(s, "하나카드 상품설명서 기반 GraphRAG  ·  카드 혜택 공통 판단 엔진", { x: 0.7, y: 0.55, w: 9, h: 0.35, fontSize: 13, color: DARK_SUB });
  T(s, "고객은 이제 카드사 앱이 아니라\nAI에게 묻습니다.", { x: 0.7, y: 1.5, w: 8.4, h: 1.55, fontSize: 38, bold: true, color: "FFFFFF", lineSpacingMultiple: 1.05 });
  T(s, "그 AI는 어제 바뀐 우리 카드의 조건을\n알고 있습니까?", { x: 0.7, y: 3.3, w: 8.4, h: 1.15, fontSize: 26, bold: true, color: AMBER, lineSpacingMultiple: 1.05 });
  T(s, "AI 채널은 늘어나도 카드 혜택의 판단 기준과 근거는 하나로 관리되어야 합니다.\n이 발표는 그 기준을 만드는 방법에 대한 제안입니다.", { x: 0.7, y: 4.85, w: 8.2, h: 0.85, fontSize: 15, color: "D5DEEA", lineSpacingMultiple: 1.15 });
  T(s, "mle-02-p2-team3  ·  2026.10  ·  2차 팀 프로젝트", { x: 0.7, y: 6.75, w: 6, h: 0.3, fontSize: 11, color: "7F8FA6" });

  // chat mock
  T(s, "고객 → 외부 AI", { x: 9.35, y: 1.5, w: 3.4, h: 0.3, fontSize: 11, color: "7F8FA6" });
  boxT(s, "ONE PICK STYLE로 버스 할인 받으려면 지난달 얼마 써야 해?", { x: 9.35, y: 1.85, w: 3.38, h: 1.0, fill: { color: "FFFFFF" }, line: { color: "FFFFFF" }, color: INK, fontSize: 14, align: "left", margin: 9, rectRadius: 0.14 });
  boxT(s, "지난달 10만원 이상 쓰면 대중교통 5% 할인돼요.", { x: 9.35, y: 3.0, w: 3.38, h: 0.85, fill: { color: INK2 }, line: { color: INK2 }, color: "FFFFFF", fontSize: 14, align: "left", margin: 9, rectRadius: 0.14 });
  T(s, "그럴듯한 답. 그런데…", { x: 9.35, y: 4.0, w: 3.4, h: 0.3, fontSize: 11, color: "7F8FA6" });
  const qs = ["근거 조항은 어디입니까?", "상품권 구매도 실적에 들어갑니까?", "어제 바뀐 조건이 반영됐습니까?"];
  qs.forEach((q, i) => boxT(s, q, { x: 9.35, y: 4.35 + i * 0.5, w: 3.38, h: 0.4, fill: { color: INK }, line: { color: AMBER, width: 1 }, color: AMBER, fontSize: 12, bold: true, align: "left", margin: 8, rectRadius: 0.1 }));
  s.addNotes("고객은 이제 카드사 앱보다 AI에게 먼저 묻습니다. 오른쪽 답은 하나카드 ONE PICK STYLE 상품설명서 기준으로 맞는 답입니다. 그런데 이 답이 어느 조항에서 나왔는지, 상품권 구매가 실적에 들어가는지, 어제 조건이 바뀌었다면 반영됐는지는 답 안에 없습니다. 오늘 발표는 이 세 질문에 답할 수 있는 기반을 어떻게 만들 것인가에 대한 제안입니다.");
}

// ---- S2 Shinhan ----
{
  const s = content("01   업계의 신호", "업계는 이미 ‘고객 접점’과 ‘판단 엔진’을 나눠 준비하고 있습니다", "도입");
  pills(s, ["공식 확인"]);
  const cards = [
    { x: L, date: "2026-09-09  ·  신한금융그룹 보도자료", head: "복합 금융상품 조건을 판단하는 AI 엔진 공동 개발 착수 (커넥셔너리)", lab: "회사가 밝힌 기존 생성형 AI의 문제", chips: ["환각(정보 왜곡)", "답변 비일관성", "복합 조건 누락", "정책·규정 미반영"], bg: RED_T, fg: RED_D, foot: "“조건 자체를 구조화해 탐색 가능한 형태로 정의하면 … 조건 수정만으로 실시간 반영될 수 있다”", it: true },
    { x: 6.78, date: "2026-09-13  ·  신한카드 보도자료", head: "카드사 최초 ‘ChatGPT for Kakao’ 연계 대화형 금융 서비스", lab: "외부 AI 대화창에서 제공하는 기능", chips: ["카드 추천", "인기카드 조회", "카드 상세혜택 조회", "소비 인사이트"], bg: TEAL_T, fg: TEAL_D, foot: "카카오 ‘PlayMCP’ 기반 ‘카카오 툴즈’에 신한카드 툴을 연동 — 외부 AI가 카드사 도구를 호출하는 구조", it: false },
  ];
  cards.forEach((c) => {
    rect(s, { x: c.x, y: 1.85, w: 5.95, h: 3.6 });
    T(s, c.date, { x: c.x + 0.25, y: 2.03, w: 5.5, h: 0.3, fontSize: 12, bold: true, color: MUTED });
    T(s, c.head, { x: c.x + 0.25, y: 2.38, w: 5.5, h: 0.75, fontSize: 17, bold: true, color: INK });
    T(s, c.lab, { x: c.x + 0.25, y: 3.2, w: 5.5, h: 0.28, fontSize: 12, color: MUTED });
    c.chips.forEach((t, i) => chip(s, t, c.x + 0.25 + (i % 2) * 2.78, 3.52 + Math.floor(i / 2) * 0.45, 2.68, 0.37, c.bg, c.fg, { fontSize: 13 }));
    T(s, c.foot, { x: c.x + 0.25, y: 4.5, w: 5.5, h: 0.8, fontSize: 13, color: SLATE, italic: c.it });
  });
  boxT(s, "4일 간격의 두 발표 — 고객이 묻는 곳은 외부 AI로 넓어지고, 답의 정확성은 카드사가 따로 책임져야 할 과제로 남습니다.", { x: L, y: 5.65, w: CW, h: 0.82, fill: { color: INK }, line: { color: INK }, color: "FFFFFF", fontSize: 16, bold: true, align: "left", margin: 14 });
  T(s, "두 시스템의 내부 연계 여부, GraphRAG 사용 여부는 공개 자료에 없습니다. 우리 기술의 검증 근거가 아니라 ‘실재하는 문제’의 근거로 인용합니다.", { x: L, y: 6.57, w: CW, h: 0.32, fontSize: 11, color: RED_D });
  footer(s, "출처: shinhangroup.com/kr/archive/press/detail/966 (2026-09-09) · press1.newswire.co.kr/newsRead.php?no=1042468 (2026-09-13) — 2026-10-30 원문 재확인");
  s.addNotes("신한카드는 2026년 9월 9일 복잡한 금융상품 조건을 판단하는 AI 엔진 공동 개발을 발표했고, 나흘 뒤 9월 13일에는 ChatGPT for Kakao에 카드 추천과 혜택 조회를 연결했습니다. 한쪽은 고객이 묻는 창구를 넓히는 일이고, 다른 쪽은 그 답이 정확한지 책임지는 일입니다. 신한이 직접 꼽은 문제는 환각, 비일관성, 복합 조건 누락, 정책·규정 미반영입니다. 이 사례는 우리 기술이 검증됐다는 뜻이 아니라, 업계가 실제로 이 문제를 고민하고 있다는 근거로 인용합니다. 두 시스템이 내부적으로 연결돼 있는지, GraphRAG를 쓰는지는 공개되지 않았습니다.");
}

// ---- S3 problem ----
{
  const s = content("02   문제 정의", "AI 채널은 늘어나는데, 판단 기준은 누가 관리합니까", "도입");
  pills(s, ["팀 해석"]);
  boxT(s, "상품설명서\n약관\n(공식 원문)", { x: L, y: 2.75, w: 1.85, h: 1.55, fill: { color: INK }, line: { color: INK }, color: "FFFFFF", fontSize: 15, bold: true });
  const ch = ["상품·준법 검토", "상담원 지원", "자사 앱 AI 상담", "외부 AI 서비스"];
  const cy = [1.95, 2.85, 3.75, 4.65];
  line(s, 2.45, 3.525, 0.45, 0);
  line(s, 2.9, cy[0] + 0.36, 0, cy[3] - cy[0]);
  ch.forEach((t, i) => {
    arrow(s, 2.9, cy[i] + 0.36, 0.38, 0);
    boxT(s, t, { x: 3.3, y: cy[i], w: 2.95, h: 0.72, align: "left", fontSize: 15, bold: true, color: INK, margin: 12 });
  });
  boxT(s, "채널마다\n다른 사본,\n다른 해석", { x: 6.45, y: 1.95, w: 1.35, h: 3.42, fill: { color: RED_T }, line: { color: RED_T }, color: RED_D, fontSize: 15, bold: true });

  T(s, "흩어지면 생기는 위험 → 그래서 필요한 것", { x: 8.2, y: 1.95, w: 4.53, h: 0.35, fontSize: 15, bold: true, color: INK });
  const rows = [
    ["근거", "조건이 빠진 답, 출처 없는 답", "→ 답마다 원문 조항까지의 경로"],
    ["변경", "어제 바뀐 조건이 일부 채널에만 반영", "→ 조건 하나가 바뀌면 영향 혜택 목록"],
    ["재사용", "채널마다 판단 로직을 다시 구현", "→ 한 번 검증한 판단을 여러 채널이 호출"],
  ];
  rows.forEach((r, i) => {
    const y = 2.45 + i * 0.98;
    boxT(s, String(i + 1), { shape: pres.shapes.OVAL, x: 8.2, y: y + 0.05, w: 0.5, h: 0.5, fill: { color: AMBER }, line: { color: AMBER }, color: INK, fontSize: 16, bold: true, margin: 0 });
    T(s, [
      { text: r[0] + "  ", options: { bold: true, color: INK, fontSize: 16 } },
      { text: r[1], options: { color: MUTED, fontSize: 13, breakLine: true } },
      { text: r[2], options: { color: TEAL_D, bold: true, fontSize: 14 } },
    ], { x: 8.85, y: y, w: 3.88, h: 0.85, valign: "top", lineSpacingMultiple: 1.15 });
  });
  boxT(s, "이 발표의 질문: 판단 기준을 한곳에서 관리하고, 여러 AI 채널에 같은 근거를 공급할 수 있는가?", { x: L, y: 5.75, w: CW, h: 0.75, fill: { color: AMBER_T }, line: { color: AMBER_T }, color: INK, fontSize: 16, bold: true, align: "left", margin: 14 });
  footer(s, "위험 유형은 신한카드 2026-09-09 발표의 문제 정의(환각·비일관성·조건 누락·규정 미반영)를 채널 관점으로 재구성한 팀 해석입니다.");
  s.addNotes("하나의 카드 상품 조건이 상품·준법 검토, 상담원, 자사 앱 AI, 외부 AI로 흘러갑니다. 채널마다 사본을 따로 들고 해석하면 세 가지 위험이 생깁니다. 조건이 빠지거나 출처가 없는 답, 어제 바뀐 조건이 일부 채널에만 반영되는 문제, 채널마다 판단 로직을 다시 만드는 비용입니다. 그래서 필요한 것을 근거, 변경, 재사용 세 가지로 정리했고, 이 세 단어가 이후 발표의 축입니다.");
}

pres.addSection({ title: "왜 어려운가" });

// ---- S4 Hana scope ----
{
  const s = content("03   실제 약관에서 본 어려움 ①", "같은 ‘상품권 제외’도 카드와 혜택마다 걸리는 곳이 다릅니다", "왜 어려운가");
  pills(s, ["원문 확인"]);
  boxT(s, "Q.  상품권 구매 실적 제외 조항이 바뀌면, 어떤 상품의 어떤 혜택을 다시 봐야 합니까?", { x: L, y: 1.8, w: CW, h: 0.62, fill: { color: AMBER_T }, line: { color: AMBER_T }, color: AMBER_D, fontSize: 17, bold: true, align: "left", margin: 14 });
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: INK }, fontSize: 13 } });
  const dot = (t) => ({ text: t, options: { color: RED_D, bold: true, align: "center" } });
  const rows = [
    [H("하나카드 상품"), H("실적 산정 제외"), H("혜택 제외"), H("실적 조건이 걸린 혜택"), H("실적 조건이 없는 혜택")],
    ["ONE PICK STYLE (체크)", dot("●"), dot("● 서비스 공통"), "ONE MORE 대중교통 (10만원)\nONE MORE 놀이공원 (20만원)", "ONE PICK · STYLE 영역"],
    ["ONE PICK PLAY (체크)", dot("●"), dot("● 서비스 공통"), "ONE MORE 대중교통 (10만원)\nONE MORE 놀이공원 (20만원)", "ONE PICK · PLAY 영역"],
    ["BT (신용)", dot("●"), dot("● BIG TICKET"), "인천공항 라운지 (50만원)", "BIG TICKET 청구할인"],
    ["에너지 더블 (신용)", dot("●"), dot("● 대형마트 할인"), "에너지 공과금 청구할인 (40/80만원)\n일상생활 청구할인 (40만원)", "—"],
  ];
  s.addTable(rows, { x: L, y: 2.6, w: CW, colW: [2.25, 1.6, 1.75, 3.9, 2.63], rowH: [0.45, 0.6, 0.6, 0.45, 0.6], fontFace: F, fontSize: 13, color: TXT, border: tblBorder, valign: "middle", margin: [3, 6, 3, 6] });
  const ins = [
    ["① 실적 제외 ≠ 혜택 제외", "상품권은 ‘실적에 잡히지 않는 금액’이기도 하고 ‘할인되지 않는 결제’이기도 합니다. 둘을 섞으면 영향 범위가 틀어집니다."],
    ["② 조건은 카드가 아니라 혜택에 걸립니다", "BT의 BIG TICKET은 지난달 실적 조건이 ‘없음’, 라운지는 50만원. 카드 단위로 묶으면 영향 없는 혜택까지 끌려옵니다."],
  ];
  ins.forEach((t, i) => {
    const x = L + i * 6.18;
    rect(s, { x, y: 5.68, w: 5.95, h: 1.18 });
    T(s, [{ text: t[0], options: { bold: true, color: INK, fontSize: 15, breakLine: true } }, { text: t[1], options: { fontSize: 13, color: SLATE } }], { x: x + 0.2, y: 5.78, w: 5.6, h: 1.02, lineSpacingMultiple: 1.1 });
  });
  footer(s, "원문: 하나카드 상품설명서 ONE PICK STYLE(15650_20260429)·PLAY(15651_20260429)·BT(14324_20260310)·에너지 더블(14422_20251224) 1쪽, 2026-10-30 대조");
  s.addNotes("이번 질문을 구체화하면 이렇습니다. 상품권 구매 실적 제외 조항이 바뀌면 어떤 상품의 어떤 혜택을 다시 봐야 할까요. 하나카드 상품설명서 4종에는 모두 상품권 제외가 있습니다. 그런데 같은 상품권이 전월실적 산정 제외로도, 할인 제외로도 쓰입니다. 또 실적 조건은 카드 전체가 아니라 혜택마다 걸립니다. BT의 BIG TICKET은 원문 표에 지난달 실적이 ‘없음’이고, 인천공항 라운지만 50만원입니다. 답은 시연 ②에서 그래프로 보여드리겠습니다.");
}

// ---- S5 PDF ----
{
  const s = content("04   실제 약관에서 본 어려움 ②", "PDF는 숫자는 남기고, 조건 사이의 관계는 잃어버립니다", "왜 어려운가");
  pills(s, ["원문 확인"]);
  const xs = [L, 4.75, 8.9], cw = 3.83;
  const heads = ["표가 표로 읽히지 않습니다", "같은 숫자, 다른 혜택", "같은 문장, 다른 결론"];
  heads.forEach((h, i) => {
    rect(s, { x: xs[i], y: 1.85, w: cw, h: 3.35 });
    T(s, h, { x: xs[i] + 0.22, y: 2.0, w: cw - 0.44, h: 0.4, fontSize: 16, bold: true, color: INK });
  });
  // card 1 visual
  boxT(s, "1.5%\n1.2%\n1.0%\n0.5%", { shape: pres.shapes.RECTANGLE, x: xs[0] + 0.3, y: 2.55, w: 1.2, h: 1.2, fill: { color: "FFFFFF" }, line: { color: SLATE, width: 1 }, color: INK, fontSize: 12 });
  boxT(s, "300만원\n한도 없음", { shape: pres.shapes.RECTANGLE, x: xs[0] + 1.5, y: 2.55, w: 1.2, h: 1.2, fill: { color: "FFFFFF" }, line: { color: SLATE, width: 1 }, color: INK, fontSize: 12 });
  boxT(s, "구간\n기준\n열\n소실", { x: xs[0] + 2.82, y: 2.55, w: 0.75, h: 1.2, fill: { color: RED_T }, line: { color: RED_T }, color: RED_D, fontSize: 11, bold: true, margin: 2 });
  T(s, "BT BIG TICKET 표: 할인율 4개가 한 셀로 추출되고 이용금액 구간 열이 빠집니다. STYLE·PLAY는 기본 표 탐지 0개.", { x: xs[0] + 0.22, y: 3.95, w: cw - 0.44, h: 1.5, fontSize: 13, color: SLATE, lineSpacingMultiple: 1.1 });
  // card 2 visual
  ["ONE PICK  월 5천원", "STYLE  월 5천원", "PLAY  월 5천원"].forEach((t, i) => chip(s, t, xs[1] + 0.3, 2.55 + i * 0.42, 3.23, 0.34, AMBER_T, AMBER_D));
  T(s, "‘5천원’ 검색은 세 혜택을 모두 찾지만, 어느 혜택의 한도인지는 표 구조가 있어야 확정됩니다.", { x: xs[1] + 0.22, y: 3.95, w: cw - 0.44, h: 1.5, fontSize: 13, color: SLATE, lineSpacingMultiple: 1.1 });
  // card 3 visual
  T(s, "“PG·간편결제 가맹점으로 분류되는 경우 …”", { x: xs[2] + 0.22, y: 2.5, w: cw - 0.44, h: 0.3, fontSize: 12, italic: true, color: MUTED });
  [["하나 ONE PICK", "혜택 제공", TEAL_T, TEAL_D], ["KB Youth Club", "제외", RED_T, RED_D], ["KB 첵첵", "제외될 수 있음", AMBER_T, AMBER_D]].forEach((r, i) => {
    const y = 2.85 + i * 0.37;
    T(s, r[0], { x: xs[2] + 0.3, y, w: 1.6, h: 0.31, fontSize: 12, color: INK, valign: "middle" });
    chip(s, r[1], xs[2] + 1.95, y, 1.6, 0.31, r[2], r[3]);
  });
  T(s, "문구가 같다고 같은 규칙으로 합치면 틀린 답이 됩니다. (타사는 비교용, 프로젝트 범위는 하나카드)", { x: xs[2] + 0.22, y: 3.95, w: cw - 0.44, h: 1.5, fontSize: 13, color: SLATE, lineSpacingMultiple: 1.1 });
  boxT(s, "필요한 것:  원문 위치 보존(M1) · 근거 문장 필수 추출(M3·M4) · 정책 단위 정규화(M5) · 원문 대조 검증(M8)", { x: L, y: 5.45, w: CW, h: 0.72, fill: { color: INK }, line: { color: INK }, color: "FFFFFF", fontSize: 14, bold: true, align: "left", margin: 14 });
  footer(s, "card_pdf_structuring_validation.md (PyMuPDF 1.28.2·pdfplumber 0.11.10 기본 옵션 표본 검증) · card_scope_comparison_claude.md §5-3");
  s.addNotes("두 번째 어려움은 원문 자체입니다. PDF에서 글자와 숫자는 거의 다 나옵니다. 그런데 BT의 BIG TICKET 표는 할인율 4개가 한 셀로 뭉치고 구간 열이 사라집니다. STYLE과 PLAY는 기본 표 탐지가 0개였습니다. ONE PICK, STYLE, PLAY에 모두 월 5천원이 있어 숫자만으로는 어느 혜택의 한도인지 알 수 없습니다. 그리고 PG·간편결제 재분류 문장은 카드사마다 거의 같지만 결론은 정반대입니다. 그래서 원문 위치 보존, 근거 문장 필수, 정책 단위 정규화, 원문 대조 검증이 필요합니다. 이것이 과제 M1, M3~M5, M8입니다.");
}

pres.addSection({ title: "왜 GraphRAG인가" });

// ---- S6 comparison ----
{
  const s = content("05   왜 GraphRAG인가", "“SQL로도 되지 않나요?” — 됩니다. 차이는 관계를 다루는 방식입니다", "왜 GraphRAG인가");
  pills(s, ["가설 · 검증 예정"]);
  const sym = { o: ["○ ", TEAL_D], t: ["△ ", AMBER_D], x: ["× ", RED_D] };
  const c = (k, t) => ({ text: [{ text: sym[k][0], options: { bold: true, color: sym[k][1] } }, { text: t, options: { color: TXT } }] });
  const H = (t, bg) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: bg }, fontSize: 13 } });
  const lab = (t) => ({ text: t, options: { bold: true, color: INK, fill: { color: MIST } } });
  const rows = [
    [H("비교 기준", SLATE), H("일반 벡터 RAG", SLATE), H("PostgreSQL + 구조화 조건 + LLM", SLATE), H("Neo4j GraphRAG", INK)],
    [lab("복합 조건 검색"), c("t", "유사 청크는 찾지만 AND·NOT 조합 보장 어려움"), c("o", "정규화 후 JOIN으로 정확"), c("o", "관계 패턴 매칭으로 표현")],
    [lab("혜택별 적용 범위"), c("x", "청크 문맥 의존, 실적/혜택 제외 혼동 위험"), c("o", "scope 컬럼으로 표현 가능"), c("o", "관계 속성(scope)으로 표현")],
    [lab("약관 조항 추적"), c("t", "청크 출처는 남지만 조건–조항 연결 없음"), c("o", "근거 컬럼·키로 연결 가능"), c("o", "결과와 함께 근거 경로 반환")],
    [lab("조건 변경 영향"), c("x", "영향 목록의 완전성 보장 불가"), c("t", "다중 JOIN·재귀 CTE, 관계 유형이 늘수록 쿼리 복잡"), c("o", "가변 길이 경로 탐색으로 표현")],
    [lab("근거 설명 재현성"), c("t", "검색·생성 결과가 실행마다 달라질 수 있음"), c("o", "같은 쿼리 → 같은 결과"), c("o", "같은 쿼리 → 같은 경로")],
    [lab("모델링·유지보수"), c("o", "스키마 설계 부담 낮음"), c("t", "새 관계 유형마다 테이블·JOIN 추가"), c("t", "온톨로지 설계·추출 품질 관리 필요")],
    [lab("구현 복잡도"), c("o", "가장 단순"), c("o", "팀 기존 역량, DB 설계 초안 보유"), c("x", "Neo4j 인프라·Cypher 학습 추가")],
  ];
  s.addTable(rows, { x: L, y: 1.8, w: CW, colW: [2.13, 3.7, 3.15, 3.15], rowH: 0.47, fontFace: F, fontSize: 12, color: TXT, border: tblBorder, valign: "middle", margin: [3, 6, 3, 6] });
  T(s, "○ 적합 예상  △ 조건부  × 어려움 예상 — 설계·문헌 기반 가설이며 실험 전입니다", { x: L, y: 5.72, w: CW, h: 0.28, fontSize: 11, color: MUTED, align: "right" });
  boxT(s, [
    { text: "우리의 주장은 ‘GraphRAG가 항상 더 정확하다’가 아닙니다. ", options: { bold: true, color: INK } },
    { text: "카드 → 혜택 → 조건 → 약관 조항을 명시적 경로로 저장할 때 근거 경로 반환·변경 영향 탐색·도구화가 더 단순해지는지를, 같은 질문으로 세 방식에 던져 확인합니다 (부록 C).", options: { color: TXT } },
  ], { x: L, y: 6.05, w: CW, h: 0.85, fill: { color: AMBER_T }, line: { color: AMBER_T }, fontSize: 14, align: "left", margin: 14 });
  footer(s, "카드 3종 규모에서 SQL 대비 성능·정확도 우위는 주장하지 않음 (V2 §8) · PostgreSQL 비교안: sql/hana_card_db_design.md (설계 초안, DB 미적용)");
  s.addNotes("심사위원께서 가장 먼저 물으실 질문을 먼저 꺼내겠습니다. PostgreSQL로도 되지 않나요? 됩니다. 정규화가 끝나면 SQL JOIN으로 같은 영향 목록을 낼 수 있고, 우리 팀은 PostgreSQL 정제·검증 DB 설계 초안도 갖고 있습니다. 일반 벡터 RAG는 구현이 가장 쉽지만 실적 제외와 혜택 제외 같은 적용 범위를 구분하거나 영향 목록의 완전성을 보장하기 어렵습니다. GraphRAG의 가치는 카드, 혜택, 조건, 약관 조항을 명시적 경로로 저장해서 근거 경로를 함께 돌려주고, 가변 길이 영향 탐색과 도구화가 단순해지는가에 있습니다. 이것은 가설이며, 같은 골든 질문으로 세 방식을 비교해 확인하겠습니다. 표의 기호는 실험 결과가 아니라 예상입니다.");
}

pres.addSection({ title: "제안 구조와 시연" });

// ---- S7 architecture ----
{
  const s = content("06   제안 구조", "AI 채널은 달라도, 판단 근거는 하나의 엔진에서 나옵니다", "제안 구조와 시연");
  pills(s, ["설계안"]);
  const top = 2.2, hh = 3.0, mid = top + hh / 2;
  const hdr = (t, x, w) => T(s, t, { x, y: 1.82, w, h: 0.3, fontSize: 12, bold: true, color: MUTED });
  hdr("원천", L, 1.7);
  boxT(s, "하나카드\n상품설명서\nPDF\n\n버전·해시\n기록", { x: L, y: top, w: 1.7, h: hh, fill: { color: MIST }, color: INK, fontSize: 14, bold: true });
  arrow(s, 2.33, mid, 0.3, 0);
  hdr("지식화 파이프라인", 2.68, 2.35);
  ["M1 전처리·청크\n원문 위치 보존", "M3·M4 LLM 관계 추출\n근거 문장 필수", "M5 정규화\n정책 단위 병합", "M8 검증\nA·B 교차 대조"].forEach((t, i) => {
    boxT(s, t, { x: 2.68, y: top + i * 0.78, w: 2.35, h: 0.66, fill: { color: "FFFFFF" }, line: { color: LINE, width: 1 }, color: INK, fontSize: 12 });
  });
  arrow(s, 5.06, mid, 0.27, 0);
  hdr("판단 엔진 · GraphRAG (M6·M7)", 5.36, 3.2);
  rect(s, { x: 5.36, y: top, w: 3.2, h: hh, fill: { color: INK }, line: { color: INK } });
  node(s, "Card", "card", 5.55, top + 0.2, 1.25, 0.42, { line: { color: "6F7F96", width: 1 } });
  node(s, "Benefit", "benefit", 7.12, top + 0.2, 1.25, 0.42);
  node(s, "Condition", "cond", 7.12, top + 0.82, 1.25, 0.42);
  node(s, "Clause", "clause", 5.55, top + 0.82, 1.25, 0.42);
  arrow(s, 6.8, top + 0.41, 0.32, 0, "C9D3E0");
  arrow(s, 7.745, top + 0.62, 0, 0.2, "C9D3E0");
  arrow(s, 6.8, top + 1.03, 0.32, 0, "C9D3E0", { flipH: true });
  T(s, [
    { text: "Neo4j 적재 — 근거 속성 보존", options: { breakLine: true } },
    { text: "Cypher: 혜택 조회·영향 추적·경로", options: { breakLine: true } },
    { text: "판정: 적용 / 미적용 / 판단 불가(사유)", options: { color: AMBER, bold: true } },
  ], { x: 5.55, y: top + 1.45, w: 2.9, h: 1.45, fontSize: 12, color: "FFFFFF", lineSpacingMultiple: 1.25 });
  arrow(s, 8.59, mid, 0.27, 0);
  hdr("연결 계층", 8.9, 1.55);
  boxT(s, "내부 API\n어댑터", { x: 8.9, y: top, w: 1.55, h: 1.25, fill: { color: "FFFFFF" }, line: { color: SLATE, width: 1.25 }, color: INK, fontSize: 13, bold: true });
  boxT(s, [{ text: "MCP 서버", options: { bold: true, fontSize: 14, color: INK, breakLine: true } }, { text: "얇은 어댑터\n판단 로직 없음", options: { fontSize: 11, color: AMBER_D } }], { x: 8.9, y: top + 1.4, w: 1.55, h: 1.6, fill: { color: "FFFFFF" }, line: { color: AMBER, width: 2 } });
  hdr("AI 채널", 10.73, 2.0);
  const chs = [["내부 상품·준법 검토", top, 0.85], ["자사 앱 AI 상담", top + 1.0, 0.85], ["외부 AI 서비스\n(MCP 클라이언트)", top + 2.0, 1.0]];
  chs.forEach((c) => boxT(s, c[0], { x: 10.73, y: c[1], w: 2.0, h: c[2], fill: { color: MIST }, color: INK, fontSize: 13, bold: true }));
  arrow(s, 10.45, top + 0.42, 0.27, 0);
  arrow(s, 10.45, top + 1.08, 0.27, 0.32);
  arrow(s, 10.45, top + 2.4, 0.27, 0.1);
  T(s, "+ 마케팅 정책 계층 (확장 제안)", { x: 10.73, y: top + 3.08, w: 2.1, h: 0.3, fontSize: 10, color: VIO, bold: true });
  boxT(s, [{ text: "카드사가 보장할 수 있는 것   ", options: { bold: true, color: TEAL_D } }, { text: "어느 채널이든 같은 조건·근거·구조화 결과를 공급", options: { color: TXT } }], { x: L, y: 5.65, w: 7.96, h: 0.95, fill: { color: TEAL_T }, line: { color: TEAL_T }, fontSize: 14, align: "left", margin: 14 });
  boxT(s, [{ text: "보장할 수 없는 것", options: { bold: true, color: RED_D, breakLine: true } }, { text: "외부 AI의 호출 여부·요약·문구 표시", options: { color: TXT } }], { x: 8.73, y: 5.65, w: 4.0, h: 0.95, fill: { color: RED_T }, line: { color: RED_T }, fontSize: 14, align: "left", margin: 14 });
  footer(s, "구조는 설계안 · 현재 구현은 PostgreSQL 카드 등록·조회 CLI뿐 (README, architecture.md) · 두 어댑터는 같은 서비스 함수를 재사용 (V2 §6-1)");
  s.addNotes("우리가 제안하는 구조입니다. 왼쪽에서 하나카드 상품설명서를 원문 위치를 보존해 나누고, LLM이 근거 문장과 함께 관계를 추출하고, 정책 단위로 정규화한 뒤 검증합니다. 그 결과가 Neo4j의 카드-혜택-조건-조항 그래프이고, 판단은 이 엔진의 Cypher 쿼리가 합니다. 오른쪽의 내부 API와 MCP 서버는 연결 계층일 뿐, 판단 로직을 갖지 않습니다. 그래서 채널이 달라도 같은 근거가 나갑니다. 다만 외부 AI가 도구를 호출할지, 어떻게 요약할지, 브랜드 문구를 보여줄지는 카드사가 보장할 수 없습니다. 지금 이 구조는 설계안이고, 현재 구현은 카드 등록·조회 CLI까지입니다.");
}

// ---- S8 demo 1 ----
{
  const s = content("07   시연 ① 판단과 근거 경로", "적용·미적용, 그리고 ‘판단 불가’까지 근거와 함께 답합니다", "제안 구조와 시연");
  pills(s, ["원문 확인", "시연 예정"]);
  const rows = [
    { q: "STYLE로 CU에서 결제하면 ONE PICK 캐시백에 전월실적이 필요한가요?", v: "적용", sub: "실적 무관", vc: [TEAL, "FFFFFF"], path: [["STYLE", "card"], ["ONE PICK", "benefit"], ["실적 조건 없음", "cond"], ["1쪽 ONE PICK 조항", "clause"]] },
    { q: "STYLE로 상품권을 사면 ONE MORE 대중교통 실적 10만원에 포함되나요?", v: "미적용", sub: "실적 제외", vc: [RED, "FFFFFF"], path: [["STYLE", "card"], ["ONE MORE 대중교통", "benefit"], ["전월실적\n10만원", "cond"], ["제외: 상품권 구매", "item"], ["1쪽 실적 제외 대상", "clause"]] },
    { q: "○○ 가게가 ONE PICK 편의점 혜택 대상인가요? (가상 가맹점)", v: "판단 불가", sub: "사유 표시", vc: [SLATE, "FFFFFF"], path: [["STYLE", "card"], ["ONE PICK 편의점", "benefit"], ["가맹점 업종 분류", "cond"], ["PDF 밖 정보 — 경로 단절", "x"]] },
  ];
  rows.forEach((r, i) => {
    const y = 1.85 + i * 1.18;
    boxT(s, r.q, { x: L, y, w: 3.7, h: 1.1, fill: { color: MIST }, color: INK, fontSize: 13, align: "left", margin: 10 });
    boxT(s, [{ text: r.v, options: { bold: true, fontSize: 17, breakLine: true } }, { text: r.sub, options: { fontSize: 11 } }], { x: 4.45, y: y + 0.15, w: 1.35, h: 0.8, fill: { color: r.vc[0] }, line: { color: r.vc[0] }, color: r.vc[1] });
    const n = r.path.length, gap = 0.24, avail = R - 6.05;
    const nw = (avail - gap * (n - 1)) / n;
    r.path.forEach((p, j) => {
      const x = 6.05 + j * (nw + gap);
      if (p[1] === "x") boxT(s, p[0], { x, y: y + 0.2, w: nw, h: 0.7, fill: { color: "FFFFFF" }, line: { color: RED, width: 1.25, dashType: "dash" }, color: RED_D, fontSize: 12, bold: true, margin: 3 });
      else node(s, p[0], p[1], x, y + 0.2, nw, 0.7);
      if (j < n - 1) arrow(s, x + nw + 0.02, y + 0.55, gap - 0.04, 0);
    });
  });
  T(s, "원문 근거: “모든 서비스는 하나카드에 등록된 국내 가맹점 및 업종 기준에 따라 제공” — 업종 분류는 상품설명서 밖 정보이므로 단정하지 않습니다.", { x: L, y: 5.4, w: CW, h: 0.32, fontSize: 11, color: MUTED });
  boxT(s, "핵심: 혜택 단위 조건(ONE PICK 실적 무관 / ONE MORE 10만원)을 카드 전체 조건으로 넓히지 않고, 근거가 없으면 답하지 않습니다.", { x: L, y: 5.85, w: CW, h: 0.75, fill: { color: INK }, line: { color: INK }, color: "FFFFFF", fontSize: 15, bold: true, align: "left", margin: 14 });
  footer(s, "판정 값은 ONE PICK STYLE 상품설명서 원문으로 확인 · 그래프 경로·응답 화면은 M7-①③ 시연 설계(미구현) · 노드 색: 카드·혜택·조건·제외 항목·조항");
  s.addNotes("첫 번째 시연은 판단과 근거 경로입니다. 판정은 적용, 미적용, 판단 불가 세 가지입니다. 편의점 ONE PICK 캐시백은 실적 무관이므로 적용, 상품권 구매는 ONE MORE 실적 산정에서 제외되므로 미적용입니다. 세 번째처럼 특정 가게가 편의점 업종인지는 하나카드의 가맹점 업종 기준, 즉 PDF 밖 정보에 달려 있습니다. 이때 엔진은 추측하지 않고 판단 불가와 사유를 돌려줍니다. 판정 값은 원문으로 확인했고, 그래프 경로와 화면은 구현 후 시연할 예정입니다.");
}

// ---- S9 demo 2 (core) ----
{
  const s = content("08   시연 ② 조건 변경 영향 — 핵심 시연", "조건 하나가 바뀌면, 다시 봐야 할 혜택이 경로로 드러납니다", "제안 구조와 시연");
  pills(s, ["원문 확인", "시연 예정"]);
  boxT(s, "가정:  ‘상품권·기프트카드 구매’를 전월실적 산정에 포함하도록 조항이 바뀐다면?", { x: L, y: 1.8, w: CW, h: 0.55, fill: { color: AMBER_T }, line: { color: AMBER_T }, color: AMBER_D, fontSize: 16, bold: true, align: "left", margin: 14 });
  T(s, "영향 검토 대상 — 4개 상품 · 7개 혜택", { x: L, y: 2.5, w: 4.2, h: 0.32, fontSize: 14, bold: true, color: TEAL_D });
  const left = [
    ["ONE PICK STYLE", "ONE MORE 대중교통(10만) · 놀이공원(20만)"],
    ["ONE PICK PLAY", "ONE MORE 대중교통(10만) · 놀이공원(20만)"],
    ["BT", "인천공항 라운지(50만)"],
    ["에너지 더블", "에너지 공과금(40/80만) · 일상생활(40만)"],
  ];
  const ly = [2.88, 3.56, 4.24, 4.92];
  left.forEach((r, i) => {
    boxT(s, [{ text: r[0], options: { bold: true, color: INK, fontSize: 13, breakLine: true } }, { text: r[1], options: { color: TEAL_D, fontSize: 12 } }], { x: L, y: ly[i], w: 4.05, h: 0.6, fill: { color: TEAL_T }, line: { color: TEAL, width: 1 }, align: "left", margin: 8 });
    line(s, 4.65, ly[i] + 0.3, 0.3, 0, TEAL);
  });
  line(s, 4.95, ly[0] + 0.3, 0, ly[3] - ly[0], TEAL);
  arrow(s, 4.95, 4.12, 0.33, 0, TEAL);
  T(s, "REQUIRES → EXCLUDES {scope: 실적}", { x: 4.7, y: 2.53, w: 3.6, h: 0.28, fontSize: 10, color: TEAL_D, bold: true, fontFace: MONO });
  node(s, "상품권·\n기프트카드 구매\n(실적 제외 항목)", "item", 5.3, 3.37, 2.35, 1.5, { fontSize: 14 });
  T(s, "같은 단어, 다른 범위 — 별도 표시", { x: 8.45, y: 2.5, w: 4.28, h: 0.32, fontSize: 14, bold: true, color: SLATE });
  const right = ["BT · BIG TICKET 할인 제외", "에너지 더블 · 대형마트 할인 제외", "STYLE·PLAY · 서비스 공통 제외"];
  const ry = [2.88, 3.56, 4.24];
  right.forEach((t, i) => {
    boxT(s, t, { x: 8.45, y: ry[i], w: 4.28, h: 0.6, fill: { color: MIST }, color: SLATE, fontSize: 13, align: "left", margin: 10 });
    line(s, 8.1, ry[i] + 0.3, 0.35, 0, "A0AAB8", { line: { color: "A0AAB8", width: 1.25, dashType: "dash" } });
  });
  line(s, 8.1, ry[0] + 0.3, 0, ry[2] - ry[0], "A0AAB8", { line: { color: "A0AAB8", width: 1.25, dashType: "dash" } });
  line(s, 7.65, 4.12, 0.45, 0, "A0AAB8", { line: { color: "A0AAB8", width: 1.25, dashType: "dash" } });
  T(s, "scope:\n혜택", { x: 7.72, y: 3.55, w: 0.4, h: 0.5, fontSize: 9, color: MUTED });
  boxT(s, "영향 없음: ONE PICK·STYLE/PLAY 영역, BIG TICKET (지난달 실적 조건 없음)", { x: 8.45, y: 4.92, w: 4.28, h: 0.6, fill: { color: "FFFFFF" }, line: { color: "A0AAB8", width: 1, dashType: "dash" }, color: MUTED, fontSize: 12, align: "left", margin: 10 });
  boxT(s, [
    { text: "‘상품권’ 검색 → ", options: { color: DARK_SUB } },
    { text: "상품권 문구 전부", options: { color: "FFFFFF", bold: true } },
    { text: "      그래프 경로 → ", options: { color: DARK_SUB } },
    { text: "실적 조건에 걸린 7개 혜택 + 범위 다른 조항 분리", options: { color: AMBER, bold: true } },
  ], { x: L, y: 5.8, w: CW, h: 0.75, fill: { color: INK }, line: { color: INK }, fontSize: 15, align: "left", margin: 14 });
  footer(s, "기대 결과는 4종 상품설명서 원문으로 수작업 도출 · Cypher·MCP 실행 결과는 시연 예정(M7-②) · 결과는 자동 변경이 아닌 사람이 확인할 검토 목록");
  s.addNotes("3장의 질문에 답하는 핵심 시연입니다. 상품권 구매를 전월실적에 포함하도록 조항이 바뀐다고 가정합니다. 단순히 ‘상품권’을 검색하면 4개 상품의 모든 상품권 문구가 다 나옵니다. 그래프는 카드에서 혜택, 혜택이 요구하는 실적 조건, 그 조건이 제외하는 항목까지 경로를 따라갑니다. 그래서 실적 조건에 연결된 7개 혜택만 영향 검토 대상으로 나오고, BIG TICKET 할인 제외처럼 같은 단어지만 범위가 다른 조항은 따로 표시됩니다. BIG TICKET은 원문 표에 지난달 실적이 ‘없음’이라 이번 변경의 영향을 받지 않습니다. 이 목록은 원문으로 손으로 도출한 기대 결과이고, 같은 결과를 Cypher와 MCP로 재현하는 것이 시연 목표입니다. 자동 정책 변경이 아니라 사람이 확인할 검토 목록입니다.");
}

// ---- S10 demo 3 ----
{
  const s = content("09   시연 ③ 오류 검증", "틀린 관계를 찾고, 고치지 못한 것은 ‘판단 보류’로 남깁니다", "제안 구조와 시연");
  pills(s, ["원문 확인", "검증 예정"]);
  const st = ["원문 청크", "트리플 JSON", "정규화 개체", "Neo4j 그래프"];
  const sw = 2.72, sg = (CW - sw * 4) / 3;
  st.forEach((t, i) => {
    const x = L + i * (sw + sg);
    boxT(s, t, { x, y: 1.85, w: sw, h: 0.58, fill: { color: SLATE_T }, line: { color: SLATE_T }, color: INK, fontSize: 14, bold: true });
    if (i < 3) arrow(s, x + sw + 0.03, 2.14, sg - 0.06, 0);
  });
  T(s, "단계 사이를 원문과 대조 (M8)", { x: L, y: 2.5, w: CW, h: 0.28, fontSize: 11, color: MUTED, align: "center" });

  T(s, "오류 6분류 — M8 검증 기준", { x: L, y: 2.95, w: 5.9, h: 0.32, fontSize: 14, bold: true, color: INK });
  ["원문에 없는 관계", "방향 오류", "중복", "오병합", "스키마 위반", "적재 누락"].forEach((t, i) => chip(s, t, L + (i % 3) * 1.98, 3.35 + Math.floor(i / 3) * 0.48, 1.88, 0.4, RED_T, RED_D, { fontSize: 13 }));
  T(s, "개선 루프", { x: L, y: 4.42, w: 5.9, h: 0.32, fontSize: 14, bold: true, color: INK });
  ["오류 분류", "프롬프트·정규화 수정", "재추출", "같은 질문 재검증"].forEach((t, i) => {
    const x = L + i * 1.5;
    boxT(s, t, { x, y: 4.8, w: 1.3, h: 0.62, fill: { color: AMBER_T }, line: { color: AMBER_T }, color: AMBER_D, fontSize: 12, bold: true, margin: 3 });
    if (i < 3) arrow(s, x + 1.31, 5.11, 0.18, 0);
  });
  T(s, "A(파일)·B(PostgreSQL) 두 파이프라인의 추출이 어긋나는 항목은 사람 검토 대상으로 분류합니다.", { x: L, y: 5.55, w: 5.95, h: 0.55, fontSize: 12, color: SLATE });

  T(s, "원문 조사에서 이미 확인한 함정 — 시연 후보", { x: 6.85, y: 2.95, w: 5.88, h: 0.32, fontSize: 14, bold: true, color: INK });
  const cases = [
    ["실적 제외 ↔ 혜택 제외 혼동", "상품권이 BT 실적 제외와 BIG TICKET 할인 제외에 모두 등장. scope를 잘못 붙이면 시연 ② 영향 목록이 틀어집니다."],
    ["표 구조 손실 → 잘못된 관계", "BT 할인율 4개가 한 셀로 추출. 구간별 할인율·한도 연결은 사람 검토 대상입니다."],
    ["원문 문구의 임의 정규화", "신한 건담 X 원문의 ‘상품/선불전자지급수단’ → ‘상품권’으로 자동 변환하지 않고 판단 보류."],
  ];
  cases.forEach((c, i) => {
    const y = 3.35 + i * 0.95;
    rect(s, { x: 6.85, y, w: 5.88, h: 0.85 });
    T(s, [{ text: c[0], options: { bold: true, color: INK, fontSize: 13, breakLine: true } }, { text: c[1], options: { fontSize: 12, color: SLATE } }], { x: 7.02, y: y + 0.07, w: 5.55, h: 0.75 });
  });
  boxT(s, "목표는 ‘전부 고쳤다’가 아니라 ‘어디서 멈추는지 안다’입니다. 미해결 1건은 판단 보류로 그대로 공개합니다.", { x: L, y: 6.2, w: CW, h: 0.65, fill: { color: INK }, line: { color: INK }, color: "FFFFFF", fontSize: 15, bold: true, align: "left", margin: 14 });
  footer(s, "함정 사례는 원문 조사로 확인한 위험 · LLM 실행 로그로 재현한 ‘실제 오답’은 M4·M8 이후 교체 (V1·V2 오답 공개 원칙)");
  s.addNotes("세 번째 시연은 신뢰의 근거, 즉 오류 검증입니다. 원문 청크, 트리플, 정규화 개체, 그래프 사이를 원문과 대조하고, 오류는 6가지로 분류합니다. 오른쪽은 원문 조사에서 이미 확인한 함정들입니다. 상품권이 실적 제외와 할인 제외에 모두 나오는 문제, 표가 깨져서 잘못된 관계가 만들어질 위험, 그리고 원문 오기처럼 보이는 문구를 임의로 고치는 위험입니다. 지금은 위험 사례이고, LLM 실행 로그로 재현된 실제 오답은 추출 후 교체하겠습니다. 저희 목표는 전부 고쳤다가 아니라 어디서 멈추는지 안다입니다.");
}

// ---- S11 MCP ----
{
  const s = content("10   MCP 연동", "MCP는 판단하지 않습니다. 검증된 판단을 다른 AI에 그대로 전달합니다", "제안 구조와 시연");
  pills(s, ["설계안", "시연 예정"]);
  T(s, "같은 질문, 두 경로, 같은 결과", { x: L, y: 1.85, w: 6.3, h: 0.32, fontSize: 14, bold: true, color: INK });
  const bw = 1.9, ag = 0.25;
  const rowsA = [["Neo4j Browser", "Cypher 쿼리\n(M7-②)", "결과 A"], ["로컬 MCP\n클라이언트", "MCP 서버 →\n같은 쿼리 함수", "결과 B"]];
  rowsA.forEach((r, i) => {
    const y = 2.3 + i * 0.88;
    r.forEach((t, j) => {
      const x = L + j * (bw + ag);
      const fill = j === 2 ? TEAL_T : (i === 1 && j === 1 ? "FFFFFF" : MIST);
      const ln = i === 1 && j === 1 ? { color: AMBER, width: 1.5 } : { color: fill };
      boxT(s, t, { x, y, w: bw, h: 0.72, fill: { color: fill }, line: ln, color: j === 2 ? TEAL_D : INK, fontSize: 13, bold: true, margin: 3 });
      if (j < 2) arrow(s, x + bw + 0.02, y + 0.36, ag - 0.04, 0);
    });
  });
  boxT(s, [{ text: "결과 A = 결과 B ?  ", options: { bold: true, color: TEAL_D } }, { text: "구조화 응답 일치 검증 · 최종 자연어 답변의 정확성은 별도 평가", options: { color: TXT } }], { x: L, y: 4.12, w: 6.2, h: 0.6, fill: { color: "FFFFFF" }, line: { color: TEAL, width: 1.25 }, fontSize: 13, align: "left", margin: 10 });
  const tb = [
    [{ text: "MCP 도구(안)", options: { bold: true, color: "FFFFFF", fill: { color: SLATE } } }, { text: "내부 동작", options: { bold: true, color: "FFFFFF", fill: { color: SLATE } } }, { text: "우선순위", options: { bold: true, color: "FFFFFF", fill: { color: SLATE } } }],
    ["get_card_benefits(card)", "M7-① 혜택·조건·근거", { text: "필수", options: { bold: true, color: TEAL_D } }],
    ["find_affected_by_condition(condition)", "M7-② 영향 추적", { text: "가능하면", options: { bold: true, color: AMBER_D } }],
    ["explain_judgment(card, benefit)", "M7-③ 판단 경로", { text: "후속", options: { color: MUTED } }],
  ];
  s.addTable(tb, { x: L, y: 4.95, w: 6.2, colW: [3.4, 1.85, 0.95], rowH: 0.38, fontFace: F, fontSize: 11, color: TXT, border: tblBorder, valign: "middle", margin: [2, 5, 2, 5] });

  const rx = 7.2, rw = R - 7.2;
  rect(s, { x: rx, y: 1.85, w: rw, h: 1.95, fill: { color: TEAL_T }, line: { color: TEAL_T } });
  T(s, [
    { text: "MCP가 하는 일", options: { bold: true, color: TEAL_D, fontSize: 15, breakLine: true } },
    { text: "기존 조회 함수를 AI 클라이언트가 호출할 수 있게 연결", options: { bullet: true, breakLine: true } },
    { text: "판정 로직을 따로 만들지 않는 얇은 어댑터", options: { bullet: true, breakLine: true } },
    { text: "자사 AI는 MCP 없이 내부 API를 직접 써도 됩니다", options: { bullet: true } },
  ], { x: rx + 0.22, y: 1.97, w: rw - 0.4, h: 1.75, fontSize: 14, color: TXT, paraSpaceAfter: 6 });
  rect(s, { x: rx, y: 3.95, w: rw, h: 1.1, fill: { color: RED_T }, line: { color: RED_T } });
  T(s, [
    { text: "MCP가 보장하지 못하는 것", options: { bold: true, color: RED_D, fontSize: 15, breakLine: true } },
    { text: "외부 AI의 도구 호출 여부 · 요약·변형 · 브랜드 문구 표시", options: {} },
  ], { x: rx + 0.22, y: 4.05, w: rw - 0.4, h: 0.95, fontSize: 14, color: TXT, lineSpacingMultiple: 1.15 });
  rect(s, { x: rx, y: 5.2, w: rw, h: 1.25, fill: { color: "FFFFFF" }, line: { color: LINE, width: 1 } });
  T(s, [
    { text: "시연 범위: ", options: { bold: true, color: INK } },
    { text: "로컬 MCP 클라이언트 호출까지. 카카오 등 외부 플랫폼 실연동은 범위 밖입니다.", options: { breakLine: true } },
    { text: "컷라인: ", options: { bold: true, color: INK } },
    { text: "3일차 오전까지 M8 미완료 시 get_card_benefits 1개만 구현", options: {} },
  ], { x: rx + 0.22, y: 5.3, w: rw - 0.4, h: 1.08, fontSize: 13, color: SLATE, lineSpacingMultiple: 1.15 });
  footer(s, "업계 사례: 신한카드, 카카오 PlayMCP 기반 ‘카카오 툴즈’ 연동 발표(2026-09-13) — 연결 방식의 실사례일 뿐, 우리 구현과의 동등성 근거는 아닙니다");
  s.addNotes("MCP는 이 구조에서 판단을 하지 않습니다. 이미 검증한 조회 함수를 다른 AI 클라이언트가 호출할 수 있게 연결할 뿐입니다. 시연은 같은 질문을 Neo4j Browser의 Cypher와 로컬 MCP 클라이언트로 각각 실행해 구조화된 결과가 같은지 확인하는 것입니다. 외부 AI가 그 결과를 어떻게 요약하는지는 따로 평가해야 합니다. 신한카드도 카카오 PlayMCP로 외부 AI에 연결했지만, 저희 시연은 로컬 클라이언트까지이며 카카오 연동이 아닙니다. 일정이 밀리면 도구는 get_card_benefits 하나만 남깁니다.");
}

pres.addSection({ title: "가치와 결론" });

// ---- S12 value ----
{
  const s = content("11   카드사 관점의 가치", "자사 AI와 외부 AI의 차이는 엔진이 아니라 ‘통제권’에 있습니다", "가치와 결론");
  pills(s, ["팀 가설", "확장 제안"]);
  const H = (t, bg) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: bg || SLATE } } });
  const lab = (t) => ({ text: t, options: { bold: true, color: INK, fill: { color: MIST } } });
  const rows = [
    [H("구분"), H("카드사 자사 AI", INK), H("외부 AI (연동 허용 시)")],
    [lab("조건·근거 조회"), { text: "같은 엔진 → 같은 구조화 결과", options: { colspan: 2, bold: true, color: TEAL_D, fill: { color: TEAL_T }, align: "center" } }],
    [lab("고객 접점"), "카드사", "외부 플랫폼"],
    [lab("답변·화면 구성"), "카드사가 설계", "외부 AI가 결정"],
    [lab("브랜드·캠페인 표시"), "승인 정책대로 관리", "필드를 줘도 표시 보장 불가"],
    [lab("최신 조건 사용"), "운영 절차로 통제", "호출·캐시·요약에 따라 다름"],
  ];
  s.addTable(rows, { x: L, y: 1.85, w: 7.25, colW: [2.05, 2.55, 2.65], rowH: 0.5, fontFace: F, fontSize: 13, color: TXT, border: tblBorder, valign: "middle", margin: [3, 6, 3, 6] });
  rect(s, { x: 8.1, y: 1.85, w: 4.63, h: 3.0, fill: { color: VIO_T }, line: { color: VIO_T } });
  T(s, [
    { text: "확장 제안 · 마케팅 정책 계층", options: { bold: true, color: VIO, fontSize: 15, breakLine: true } },
    { text: "카드사 승인 문구를 Copy 노드로 관리", options: { bullet: true, breakLine: true } },
    { text: "문구 속 주장(‘실적 무관’ 등)을 약관과 대조", options: { bullet: true, breakLine: true } },
    { text: "조건 변경 시 재심의할 문구 목록 산출", options: { bullet: true, breakLine: true } },
    { text: "질문·오답 피드백 → 검토 → 반영", options: { bullet: true } },
  ], { x: 8.3, y: 2.0, w: 4.25, h: 2.75, fontSize: 14, color: TXT, paraSpaceAfter: 9 });
  boxT(s, [
    { text: "객관성 원칙  ", options: { bold: true, color: RED_D } },
    { text: "판단 먼저, 문구는 나중에. 마케팅 데이터는 판단 입력이 아니며, 문구는 [광고]로 분리 표시하고, 켜고 끈 두 경우의 판단·순위가 같아야 합니다.", options: { color: TXT } },
  ], { x: L, y: 5.05, w: CW, h: 0.78, fill: { color: RED_T }, line: { color: RED_T }, fontSize: 14, align: "left", margin: 14 });
  const v = [["정확성", "적용 범위까지 구분한 근거"], ["추적성", "조건 변경 시 검토 목록"], ["재사용성", "여러 채널이 같은 엔진"]];
  v.forEach((t, i) => boxT(s, [{ text: t[0] + "  ", options: { bold: true, color: AMBER } }, { text: t[1], options: { color: "FFFFFF" } }], { x: L + i * 4.11, y: 6.03, w: 3.91, h: 0.62, fill: { color: INK }, line: { color: INK }, fontSize: 14 }));
  footer(s, "역할 비교: V2 §6-1 · 마케팅 계층: 최종_카드사_자체AI혜택서비스_사업적개발명분_20261029.md (팀 가설, 미구현) · 기대 효과는 실측 전");
  s.addNotes("그렇다면 카드사가 왜 자체 AI 채널을 운영하려 할까요. 같은 엔진을 쓰면 자사 AI와 외부 AI가 받는 판단 근거는 같습니다. 차이는 엔진이 아니라 통제권입니다. 고객 접점, 답변 구성 권한, 브랜드와 캠페인 표시, 최신 조건 반영 절차입니다. 그래서 확장 제안으로 마케팅 정책 계층을 검토합니다. 승인 문구를 관리하고, 문구 속 주장을 약관과 대조하고, 조건이 바뀌면 다시 심의할 문구를 찾는 것입니다. 단 원칙이 있습니다. 판단이 먼저이고, 마케팅 데이터는 판단에 들어가지 않으며, 광고는 분리 표시합니다. 이 계층은 현재 구현 범위가 아닌 제안입니다.");
}

// ---- S13 conclusion ----
{
  const s = pres.addSlide({ masterName: "DARK", sectionTitle: "가치와 결론" });
  T(s, "결론", { x: 0.7, y: 0.6, w: 3, h: 0.32, fontSize: 13, bold: true, color: AMBER });
  T(s, "카드 추천 화면 하나가 아니라,\n여러 AI가 함께 쓰는 카드 혜택 판단의 공통 기반.", { x: 0.7, y: 1.1, w: 12, h: 1.6, fontSize: 34, bold: true, color: "FFFFFF", lineSpacingMultiple: 1.1 });
  T(s, "하나카드 상품설명서로 3일 동안 구현·검증하려는 구조입니다.", { x: 0.7, y: 2.85, w: 12, h: 0.4, fontSize: 16, color: DARK_SUB });
  const p = [["1", "근거", "답마다 원문 조항까지의 경로.\n근거가 없으면 ‘판단 불가’."], ["2", "변경", "조건 하나가 바뀌면\n다시 볼 혜택을 경로로 산출."], ["3", "재사용", "검증된 판단을 내부·자사·외부\nAI가 같은 도구로 호출."]];
  p.forEach((t, i) => {
    const x = 0.7 + i * 4.06;
    rect(s, { x, y: 3.6, w: 3.86, h: 1.75, fill: { color: INK2 }, line: { color: INK2 } });
    boxT(s, t[0], { shape: pres.shapes.OVAL, x: x + 0.25, y: 3.82, w: 0.48, h: 0.48, fill: { color: AMBER }, line: { color: AMBER }, color: INK, fontSize: 15, bold: true, margin: 0 });
    T(s, t[1], { x: x + 0.88, y: 3.82, w: 2.8, h: 0.48, fontSize: 20, bold: true, color: "FFFFFF", valign: "middle" });
    T(s, t[2], { x: x + 0.25, y: 4.42, w: 3.45, h: 0.85, fontSize: 14, color: "D5DEEA", lineSpacingMultiple: 1.1 });
  });
  T(s, "어제 바뀐 조건이 오늘 어떤 혜택을 흔드는지, 원문과 함께 답할 수 있게.", { x: 0.7, y: 5.7, w: 12, h: 0.5, fontSize: 20, bold: true, color: AMBER });
  T(s, "정답을 말하는 AI보다, 놓치는 조건과 답할 수 없는 지점을 먼저 알려주는 AI.", { x: 0.7, y: 6.3, w: 12, h: 0.4, fontSize: 15, color: DARK_SUB });
  s.addNotes("처음 질문으로 돌아가겠습니다. 그 AI는 어제 바뀐 우리 카드의 조건을 알고 있습니까. 저희가 구현하려는 것은 카드 추천 화면 하나가 아니라, 여러 AI가 함께 쓰는 카드 혜택 판단의 공통 기반입니다. 근거, 변경, 재사용. 어제 바뀐 조건이 오늘 어떤 혜택을 흔드는지 원문과 함께 답하는 것, 그리고 답할 수 없는 지점은 답하지 않는 것. 그것이 저희가 3일 동안 검증하려는 구조입니다. 감사합니다.");
}

// ===================== APPENDIX =====================
pres.addSection({ title: "부록" });

// A — task mapping
{
  const s = content("부록 A   과제 수행 증빙", "M0~M9는 발표의 어느 장면을 만드는가 — 현재 상태 포함", "부록");
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: INK } } });
  const st = (t, k) => ({ text: t, options: { color: k === "d" ? TEAL_D : k === "p" ? AMBER_D : RED_D, bold: true } });
  const rows = [
    [H("과제"), H("카드 엔진에서 할 일"), H("관련 장(좌상단 번호)"), H("현재 상태 (2026-10-30)")],
    ["M0 주제·문서", "카드 2~3종, 그래프 질문 3~5개 확정", "3, 8", st("진행 중 — 하나 9종 등 PDF 확보·문구 대조 완료, 최종 2~3종 미확정", "p")],
    ["M1 전처리", "텍스트 추출·청크·원문 위치 ID", "4", st("추출 가능성 표본 검증 완료 / 파이프라인 미구현", "p")],
    ["M2 온톨로지", "Card·Benefit·Condition·Merchant·Clause", "6, 부록 B", st("설계안 (과제 매핑표)", "p")],
    ["M3·M4 LLM 추출", "근거 문장·clause_id 필수 JSON, 실패 처리", "4, 9", st("미구현", "x")],
    ["M5 정규화", "정책 단위 병합, 오병합 점검", "4, 9", st("미구현 — 오병합 위험 사례 확인", "x")],
    ["M6 Neo4j 적재", "MERGE 재적재, 근거 속성 보존", "6", st("미구현", "x")],
    ["M7 Cypher", "혜택 조회 · 영향 추적 · 판단 경로", "7, 8", st("미구현 — 기대 결과는 원문으로 도출", "x")],
    ["M8 검증", "원문–트리플–그래프 대조, 오류 6분류", "9", st("미구현 — 기준 정의", "x")],
    ["M9 통합·MCP", "문서 → 그래프 → MCP 한 흐름", "10", st("미구현 — 도구 3안, 컷라인 설정", "x")],
    ["구현 완료", "PostgreSQL 카드 등록·조회 CLI + 단위 테스트", "—", st("완료 (payment_card)", "d")],
  ];
  s.addTable(rows, { x: L, y: 1.8, w: CW, colW: [2.1, 4.3, 1.3, 4.43], rowH: 0.43, fontFace: F, fontSize: 12, color: TXT, border: tblBorder, valign: "middle", margin: [2, 6, 2, 6] });
  footer(s, "출처: 과제_매핑표_10.29.md · README.md · architecture.md · sql/hana_card_db_design.md (DB 설계 초안, 미적용)");
}

// B — ontology
{
  const s = content("부록 B   그래프 설계안 (M2)", "카드 → 혜택 → 조건 → 약관 조항, 모든 관계에 근거를 붙입니다", "부록");
  pills(s, ["설계안"]);
  const y1 = 2.25, y2 = 3.85, nh = 0.7, nw = 2.15;
  const xs = [L, 3.75, 6.9, 10.05];
  node(s, "Card\n카드 상품", "card", xs[0], y1, nw, nh);
  node(s, "Benefit\n혜택", "benefit", xs[1], y1, nw, nh);
  node(s, "Condition\n전월실적·한도", "cond", xs[2], y1, nw, nh);
  node(s, "Condition\n제외 항목", "item", xs[3], y1, 2.68, nh);
  ["HAS_BENEFIT", "REQUIRES", "EXCLUDES {scope}"].forEach((t, i) => {
    arrow(s, xs[i] + nw + 0.03, y1 + nh / 2, xs[i + 1] - xs[i] - nw - 0.06, 0, SLATE);
    T(s, t, { x: xs[i] + nw - 0.2, y: y1 - 0.32, w: 1.6, h: 0.26, fontSize: 10, bold: true, color: SLATE, fontFace: MONO, align: "center" });
  });
  node(s, "Copy\n승인 문구 (확장 제안)", "grey", xs[0], y2, nw, nh, { fill: { color: VIO_T }, line: { color: VIO, width: 1.25, dashType: "dash" }, color: VIO });
  node(s, "Condition\n월 한도", "cond", xs[1], y2, nw, nh);
  node(s, "Clause\n약관 조항", "clause", xs[2], y2, nw, nh);
  node(s, "Merchant\n가맹점·업종", "grey", xs[3], y2, 2.68, nh);
  arrow(s, xs[1] + nw / 2, y1 + nh + 0.03, 0, y2 - y1 - nh - 0.06, SLATE);
  T(s, "LIMITED_BY", { x: xs[1] + nw / 2 + 0.08, y: y1 + nh + 0.2, w: 1.3, h: 0.26, fontSize: 10, bold: true, color: SLATE, fontFace: MONO });
  arrow(s, xs[2] + nw / 2, y1 + nh + 0.03, 0, y2 - y1 - nh - 0.06, SLATE);
  T(s, "SOURCED_FROM", { x: xs[2] + nw / 2 + 0.08, y: y1 + nh + 0.2, w: 1.4, h: 0.26, fontSize: 10, bold: true, color: SLATE, fontFace: MONO });
  arrow(s, xs[0] + nw, y1 + nh, xs[1] - xs[0] - nw, y2 - y1 - nh, VIO, { flipV: true });
  T(s, "CLAIMS", { x: xs[0] + nw + 0.45, y: y2 - 0.42, w: 0.9, h: 0.26, fontSize: 10, bold: true, color: VIO, fontFace: MONO });
  T(s, "APPLIES_TO ← Benefit", { x: xs[3], y: y2 + nh + 0.05, w: 2.68, h: 0.26, fontSize: 10, color: SLATE, fontFace: MONO, align: "center" });
  T(s, "모든 관계 속성: document_id · chunk_id · evidence(원문 문장).  근거 없는 관계는 만들지 않고, 카드 간 같은 정책만 하나의 노드로 공유합니다.", { x: L, y: 4.95, w: CW, h: 0.35, fontSize: 13, color: INK, bold: true });
  boxT(s, "// 시연 ② 영향 추적 (예시 Cypher, 미실행)\nMATCH (x:Condition {name:'상품권·기프트카드 구매'})<-[:EXCLUDES {scope:'실적'}]-(r:Condition)<-[:REQUIRES]-(b:Benefit)<-[:HAS_BENEFIT]-(c:Card)\nOPTIONAL MATCH (r)-[:SOURCED_FROM]->(cl:Clause)\nRETURN c.name AS card, b.name AS benefit, r.threshold AS spend, cl.id AS clause", { x: L, y: 5.45, w: CW, h: 1.35, fill: { color: INK }, line: { color: INK }, color: "E6ECF4", fontFace: MONO, fontSize: 10, align: "left", valign: "top", margin: 10 });
  footer(s, "노드·관계는 과제_매핑표_10.29.md M2 안 · Copy 노드는 V2 §6 제안 · 쿼리는 설계 예시이며 실행 결과 아님");
}

// C — experiment
{
  const s = content("부록 C   비교 실험 설계", "주장 대신 실험으로 — 결과 칸은 실행한 뒤에만 채웁니다", "부록");
  pills(s, ["미실행"]);
  T(s, "골든 질문 15~20개 · 정답 기준은 원문 조항", { x: L, y: 1.82, w: 6.0, h: 0.6, fontSize: 14, bold: true, color: INK });
  const qs = [
    ["변경 영향", "상품권을 실적에 포함하면 영향받는 카드·혜택·조항은?"],
    ["공유 구조", "ONE PICK STYLE과 PLAY가 공유하는 혜택·조건은?"],
    ["적용 범위", "같은 항목이 할인·적립 제외로 쓰인 상품은?"],
    ["3상태 판정", "적용 / 미적용 / 판단 불가 사유가 맞는가?"],
  ];
  qs.forEach((q, i) => {
    const y = 2.55 + i * 0.72;
    chip(s, q[0], L, y, 1.45, 0.58, AMBER_T, AMBER_D);
    T(s, q[1], { x: L + 1.6, y, w: 4.4, h: 0.58, fontSize: 13, color: TXT, valign: "middle" });
  });
  T(s, "비교: ① 벡터 RAG ② PostgreSQL + 조건 + LLM ③ GraphRAG\n작성자·표본 수·계산법을 기록하고 불리한 항목도 공개합니다.\n선택 과제(S1) — 필수 M0~M9 완료 후 수행합니다.", { x: L, y: 5.5, w: 6.0, h: 1.2, fontSize: 12, color: SLATE, lineSpacingMultiple: 1.15 });
  const H = (t, bg) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: bg || SLATE }, align: "center" } });
  const e = { text: "—", options: { color: "A0AAB8", align: "center", fill: { color: MIST } } };
  const metrics = ["조건 누락률", "근거 조항 정확도", "잘못된 단정 비율", "영향 탐색 정밀도", "영향 탐색 재현율", "근거 경로 일치율", "판단 불가 적정성"];
  const rows = [[H("지표"), H("벡터 RAG"), H("SQL + LLM"), H("GraphRAG", INK)]].concat(metrics.map((m) => [{ text: m, options: { bold: true, color: INK } }, e, e, e]));
  s.addTable(rows, { x: 6.95, y: 1.85, w: 5.78, colW: [2.18, 1.2, 1.2, 1.2], rowH: 0.5, fontFace: F, fontSize: 12, color: TXT, border: tblBorder, valign: "middle", margin: [2, 6, 2, 6] });
  T(s, "— : 미실행. 수치는 실험 후 교체합니다.", { x: 6.95, y: 5.95, w: 5.78, h: 0.3, fontSize: 11, color: MUTED });
  footer(s, "설계 근거: 카드사_자체AI판단엔진_개발명분_공식근거조사_20261028.md §5 · V2 §3·§4 · 과제_매핑표_10.29.md (M8, S1)");
}

// D — Q&A
{
  const s = content("부록 D   예상 질문", "받을 질문을 먼저 정리했습니다", "부록");
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: INK } } });
  const q = (t) => ({ text: t, options: { bold: true, color: INK, fill: { color: MIST } } });
  const rows = [
    [H("질문"), H("답변 요지")],
    [q("카드사의 정본은 PDF가 아니라 내부 상품 DB 아닌가요?"), "PDF는 고객에게 고지된 계약 문구입니다. 내부 DB와 고지 문서의 불일치를 점검하는 보완 용도로 제안합니다 (내부 시스템 구조는 미확인)."],
    [q("카드 3종이면 SQL로 되지 않나요?"), "됩니다. 같은 질의를 Cypher와 SQL로 나란히 보이고, 관계 유형이 늘 때의 차이로 설명합니다. 소규모 성능 우위는 주장하지 않습니다."],
    [q("신한이 이미 비슷한 걸 만들지 않나요?"), "차별점이 아니라 업계가 인정한 문제라는 근거로 인용했습니다. 신한 엔진의 방식(GraphRAG 여부)은 공개되지 않았습니다."],
    [q("표 추출이 자동인가요?"), "기본 표 추출은 대부분 실패했습니다. 수작업 보정과 사람 검토가 들어간다는 점을 공개합니다."],
    [q("MCP가 있으면 외부 AI의 답을 통제하나요?"), "아닙니다. 구조화된 조건·근거를 공급할 뿐, 호출 여부·요약·문구 노출은 외부 AI가 결정합니다."],
    [q("고객에게 추천하면 규제 문제는요?"), "이번 범위는 내부 검토 도구입니다. 고객 대면 추천·광고는 금융소비자보호법상 권유·광고 규율 검토가 필요합니다 (준법 확인 필요)."],
    [q("문서가 최신인가요?"), "시행일·현재 유효 여부·재배포 조건은 미확인입니다. 문서 버전과 SHA-256 해시를 함께 기록합니다."],
  ];
  s.addTable(rows, { x: L, y: 1.8, w: CW, colW: [4.2, 7.93], rowH: [0.42, 0.6, 0.6, 0.6, 0.5, 0.5, 0.6, 0.5], fontFace: F, fontSize: 12, color: TXT, border: tblBorder, valign: "middle", margin: [3, 6, 3, 6] });
  footer(s, "출처: ppt_story_key_points_v2_draft.md §8 (예상 반론과 답변)");
}

// E — sources
{
  const s = content("부록 E   출처와 검증 상태", "무엇을 확인했고, 무엇을 정정했는가", "부록");
  const H = (t) => ({ text: t, options: { bold: true, color: "FFFFFF", fill: { color: INK } } });
  const ok = (t) => ({ text: t, options: { color: TEAL_D, bold: true } });
  const rows = [
    [H("자료"), H("사용한 내용"), H("상태")],
    ["신한금융그룹 보도자료 (2026-09-09) shinhangroup.com/kr/archive/press/detail/966", "조건 판단 AI 엔진 공동 개발, 기존 AI 문제 4가지", ok("공식 확인 2026-10-30")],
    ["신한카드 보도자료 (2026-09-13) press1.newswire.co.kr/newsRead.php?no=1042468", "ChatGPT for Kakao, PlayMCP 기반 카카오 툴즈 연동", ok("공식 확인 2026-10-30")],
    ["하나카드 상품설명서 STYLE·PLAY·BT·에너지 더블 (m.hanacard.co.kr/leaflet/…)", "상품권 제외 범위, 혜택별 실적 조건 (SHA-256이 기존 검증 문서와 일치)", ok("원문 확인 2026-10-30")],
    ["card_pdf_structuring_validation.md", "표 추출 실패 사례 (STYLE·PLAY 0개, BT 셀 병합)", ok("팀 검증 기록")],
    ["card_scope_comparison_claude.md · _gpt_review.md", "공통 문구·scope 차이, PG 재분류 문장 비교", ok("팀 조사 기록")],
    ["ppt_story_key_points.md (V1) · _v2_draft.md (V2) · 과제_매핑표_10.29.md", "스토리 방향, 시연 3개, MCP 범위, 컷라인", ok("팀 문서")],
  ];
  s.addTable(rows, { x: L, y: 1.8, w: CW, colW: [5.2, 4.83, 2.1], rowH: 0.5, fontFace: F, fontSize: 11, color: TXT, border: tblBorder, valign: "middle", margin: [2, 6, 2, 6] });
  rect(s, { x: L, y: 5.5, w: CW, h: 1.3, fill: { color: AMBER_T }, line: { color: AMBER_T } });
  T(s, [
    { text: "이번 원문 대조로 정정한 사항", options: { bold: true, color: AMBER_D, fontSize: 14, breakLine: true } },
    { text: "BT BIG TICKET의 지난달 실적은 원문 표에 ‘없음’입니다. 50만원 조건은 인천공항 라운지에 해당합니다 (card_scope_comparison_claude.md의 ‘BIG TICKET 50만원’ 기재와 다름).", options: { bullet: true, breakLine: true } },
    { text: "에너지 더블은 일상생활 청구할인(40만원)뿐 아니라 에너지 공과금 청구할인(40/80만원)도 지난달 실적 조건이 있어 영향 목록에 포함했습니다 (V2 §4 목록에 추가).", options: { bullet: true } },
  ], { x: L + 0.2, y: 5.58, w: CW - 0.4, h: 1.18, fontSize: 12, color: TXT, paraSpaceAfter: 2 });
  footer(s, "원문 PDF는 저장소에 추가하지 않았습니다 (재배포 조건 미확인).");
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("written", OUT);
})();
