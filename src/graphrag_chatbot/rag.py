"""GraphRAG 핵심 로직 (Supabase/PostgreSQL 버전). UI(Streamlit)와 분리되어 있어서 나중에 FastAPI 등으로 옮겨도 그대로 씁니다.

흐름: 질의 분석(엔티티 선택) -> 그래프 탐색(PostgreSQL 재귀 쿼리) -> 답변 생성(LLM, 스트리밍)
그래프는 graphrag.nodes(id, name, label, props)와 graphrag.edges(source, target, type) 테이블에 저장됩니다. supabase_schema.sql 참고.
DB 연결과 테이블 이름은 db.py가 맡습니다.
하위 그래프 형식: {"nodes": [...], "edges": [...], "seeds": [...]}
"""
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterator

import db
import llm
import timing

MAX_HOPS = 3
MAX_NODES = 40

ANALYZE_SYSTEM = (
    "사용자의 질문에서 그래프에서 찾을 엔티티를 고릅니다. "
    "반드시 주어진 엔티티 목록에 있는 이름만 사용하세요. "
    "영향 범위, 전파, 연쇄처럼 여러 단계를 따라가야 하는 질문이면 hops를 2, 그 외에는 1로 합니다. "
    '다음 JSON만 출력하세요: {"entities": ["이름"], "hops": 1, "intent": "질문 의도 한 줄"}'
)

ANSWER_SYSTEM = (
    "당신은 그래프 근거로만 답하는 어시스턴트입니다. "
    "아래 '그래프 근거'에 있는 관계와 속성만 사용해 한국어로 3~4문장 안에 답하세요. "
    "근거에 없는 내용은 추측하지 말고, 근거가 부족하면 그렇게 말하세요."
)

# 시작 노드에서 hops 거리 안의 노드를 방향 없이 따라갑니다. (UNION이라 순환이 있어도 depth로 멈춥니다)
REACH_SQL = f"""
with recursive reach(id, depth) as (
  select id, 0 from {db.NODES} where name = any(%(names)s)
  union
  select case when e.source = r.id then e.target else e.source end, r.depth + 1
  from reach r
  join {db.EDGES} e on e.source = r.id or e.target = r.id
  where r.depth < %(hops)s
)
select n.id::text as id, n.name, n.label, n.props
from {db.NODES} n
where n.id in (select id from reach)
limit %(limit)s
"""


@dataclass
class Analysis:
    entities: list[str] = field(default_factory=list)
    hops: int = 1
    intent: str = ""


def list_entities() -> list[dict]:
    """질의 분석에 쓸 엔티티 목록. 그래프가 크면 전문 검색이나 pgvector 검색으로 바꾸세요."""
    with timing.stage("entities_db"):
        rows = db.run_query(f"select name, label from {db.NODES} order by name limit 500")
    return [{"name": r["name"], "label": r["label"]} for r in rows]


def _parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0)) if m else {}


def analyze(question: str, entities: list[dict]) -> Analysis:
    known = {e["name"] for e in entities}
    listing = ", ".join(f"{e['name']}({e['label']})" for e in entities)
    picked: list[str] = []
    hops, intent = 1, ""
    try:
        with timing.stage("analyze_llm"):
            raw = llm.complete(ANALYZE_SYSTEM, f"질문: {question}\n\n엔티티 목록: {listing}")
        data = _parse_json(raw)
        picked = [n for n in data.get("entities", []) if n in known]
        hops = int(data.get("hops", 1))
        intent = str(data.get("intent", ""))
    except Exception:
        pass  # LLM 응답이 깨지면 아래 문자열 매칭으로 대체합니다.
    if not picked:
        picked = [n for n in known if n in question]
    return Analysis(entities=picked, hops=max(1, min(hops, MAX_HOPS)), intent=intent)


def _node_dict(row: dict) -> dict:
    props = row["props"] or {}
    return {
        "id": row["id"],
        "name": row["name"],
        "label": row["label"],
        "props": {
            k: v
            for k, v in props.items()
            if k != "name" and isinstance(v, (str, int, float, bool))
        },
    }


def explore(analysis: Analysis) -> dict:
    """엔티티에서 hops 거리 안의 노드와, 그 노드들 사이의 관계를 가져옵니다. (구간 시간은 timing.stage로 잽니다)"""
    with timing.stage("explore_db"):
        return _explore(analysis)


def _explore(analysis: Analysis) -> dict:
    empty = {"nodes": [], "edges": [], "seeds": []}
    if not analysis.entities:
        return empty
    hops = max(1, min(int(analysis.hops), MAX_HOPS))
    seed_rows = db.run_query(
        f"select id::text as id, name, label, props from {db.NODES} where name = any(%(names)s)",
        {"names": analysis.entities},
    )
    reach_rows = db.run_query(
        REACH_SQL, {"names": analysis.entities, "hops": hops, "limit": MAX_NODES}
    )
    nodes: dict[str, dict] = {}
    seeds: list[str] = []
    for r in seed_rows:  # 질문 대상 노드를 먼저 담아서 개수 제한에서 밀려나지 않게 합니다.
        d = _node_dict(r)
        nodes[d["id"]] = d
        seeds.append(d["id"])
    for r in reach_rows:
        nodes.setdefault(r["id"], _node_dict(r))
    node_list = list(nodes.values())[:MAX_NODES]
    if not node_list:
        return empty
    ids = [n["id"] for n in node_list]
    id_array = [uuid.UUID(i) for i in ids]
    edge_rows = db.run_query(
        f"select source::text as source, target::text as target, type from {db.EDGES} "
        "where source = any(%(ids)s) and target = any(%(ids)s)",
        {"ids": id_array},
    )
    return {
        "nodes": node_list,
        "edges": [
            {"source": e["source"], "target": e["target"], "type": e["type"]}
            for e in edge_rows
        ],
        "seeds": [s for s in seeds if s in set(ids)],
    }


def format_facts(sub: dict) -> str:
    by_id = {n["id"]: n for n in sub["nodes"]}
    lines = []
    for e in sub["edges"]:
        s, t = by_id[e["source"]], by_id[e["target"]]
        lines.append(f"- {s['name']} ({s['label']}) -[{e['type']}]-> {t['name']} ({t['label']})")
    for n in sub["nodes"]:
        if n["props"]:
            props = ", ".join(f"{k}={v}" for k, v in n["props"].items())
            lines.append(f"- {n['name']} 속성: {props}")
    return "\n".join(lines)


def generate_stream(question: str, sub: dict, history=None) -> Iterator[str]:
    """답변을 토큰 단위로 내보냅니다. history는 [(질문, 답변), ...] 형식입니다."""
    t_req = time.perf_counter()
    first_at = None
    ok = False
    try:
        if not sub["nodes"]:
            yield "그래프에서 관련 정보를 찾지 못했습니다. 질문에 포함된 서비스나 팀 이름을 확인해 주세요."
            ok = True
            return
        messages: list[dict] = []
        for q, a in (history or [])[-2:]:
            messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        messages.append(
            {"role": "user", "content": f"그래프 근거:\n{format_facts(sub)}\n\n질문: {question}"}
        )
        for chunk in llm.stream(ANSWER_SYSTEM, messages):
            if first_at is None:
                first_at = time.perf_counter()
                timing.mark("first_token", (first_at - t_req) * 1000)
            yield chunk
        ok = True
    finally:
        # 끝까지 소비되지 않고 닫혀도(화면 이동 등) 지금까지의 시간을 남깁니다.
        if first_at is not None:
            timing.mark("stream", (time.perf_counter() - first_at) * 1000)
        timing.finish(ok=ok, nodes=len(sub["nodes"]), edges=len(sub["edges"]))


def sources(sub: dict) -> list[dict]:
    """하위 그래프 안의 Document 노드를 출처로 돌려줍니다."""
    return [
        {"title": n["name"], "note": str(n["props"].get("summary", ""))}
        for n in sub["nodes"]
        if n["label"] == "Document"
    ]


def steps_text(analysis: Analysis, sub: dict) -> list[str]:
    names = ", ".join(f"'{n}'" for n in analysis.entities) or "없음"
    return [
        f"1. 질의 분석 · 엔티티 {names}, 의도 '{analysis.intent or '-'}'",
        f"2. 그래프 탐색 · {analysis.hops}-hop, 노드 {len(sub['nodes'])}개 · 관계 {len(sub['edges'])}개",
        f"3. 답변 생성 · 문서 {len(sources(sub))}건 사용",
    ]


def answer(question: str, history=None) -> dict:
    """UI 없이 한 번에 결과를 받는 함수. API 서버나 테스트에서 씁니다."""
    timing.start(question)
    analysis = analyze(question, list_entities())
    sub = explore(analysis)
    text = "".join(generate_stream(question, sub, history))
    return {
        "answer": text,
        "sources": sources(sub),
        "subgraph": sub,
        "steps": steps_text(analysis, sub),
    }
