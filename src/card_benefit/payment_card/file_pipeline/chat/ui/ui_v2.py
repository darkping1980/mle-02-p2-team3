"""Streamlit-independent helpers for the v2 card chatbot screen."""
from __future__ import annotations

import json
import re
from typing import Any

EXAMPLE_QUESTIONS = (
    "신세계 by JADE 카드의 디지털 콘텐츠 할인 조건은?",
    "국민행복카드 커피 할인 한도는?",
    "하나 Any PLUS 카드의 주유 혜택은?",
    "우리 카드의 연회비와 혜택을 알려줘.",
)

MISSING = "자료에서 확인하지 못함"
DISCLAIMER = "원문 구간은 자동 추출 근거이며 사람 검수 전입니다"
_DEIXIS = re.compile(r"그\s*카드|그중|이\s*카드|그럼|또|거기|같은\s*카드|그건|그\s*할인|그\s*혜택|그\s*중", re.I)


def build_analysis_question(question: str, history_turns: list[dict], last_entities: list[str]) -> str:
    """Add prior selected entities only for a follow-up containing a deixis marker."""
    if not history_turns or not _DEIXIS.search(question):
        return question
    entities = [str(value).strip() for value in (last_entities or []) if str(value).strip()]
    if not entities:
        entities = [str(value).strip() for value in history_turns[-1].get("selected_entities", []) if str(value).strip()]
    if not entities:
        return question
    return f"(이전 대화에서 다룬 대상: {', '.join(entities)})\n{question}"


def _page_list(value: Any) -> list[int] | str:
    if value is None or value == "":
        return MISSING
    if isinstance(value, str):
        values = re.findall(r"\d+", value)
    elif isinstance(value, (tuple, list, set)):
        values = list(value)
    else:
        values = [value]
    pages = sorted({int(v) for v in values if str(v).isdigit()})
    return pages or MISSING


def _document_hash(node: dict) -> str | None:
    props = node.get("props") or {}
    raw = props.get("doc_sha256") or props.get("sha256") or props.get("document_hash")
    if not raw:
        raw = str(node.get("id", ""))
        if raw.startswith("doc:"):
            raw = raw[4:]
    if not raw:
        return None
    digest = str(raw)
    return digest if re.fullmatch(r"[0-9a-fA-F]{8,}", digest) else None


def collect_sources(subgraph: dict, evidence_refs: list[dict] | None = None) -> list[dict]:
    """Build compact user-facing benefit-span and document source entries."""
    nodes = subgraph.get("nodes") or []
    document_pages: dict[str, set[int]] = {}
    for ref in evidence_refs or []:
        digest = ref.get("doc_sha256")
        page = ref.get("page_no")
        if digest and page is not None:
            try:
                document_pages.setdefault(str(digest), set()).add(int(page))
            except (TypeError, ValueError):
                continue

    sources = []
    for node in nodes:
        label = node.get("label")
        props = node.get("props") or {}
        if label == "Benefit":
            raw = props.get("source_text")
            text = str(raw).strip() if raw else MISSING
            explicitly_truncated = bool(props.get("source_text_truncated"))
            clipped = len(text) > 700
            if clipped:
                text = text[:700]
            pages = _page_list(props.get("source_text_pages"))
            sources.append({
                "title": str(node.get("name") or props.get("name") or MISSING),
                "text": text,
                "pages": pages,
                "truncated": explicitly_truncated or clipped,
            })
        elif label == "Document":
            digest = _document_hash(node)
            title = f"문서 {digest[:8]}" if digest else f"문서 {MISSING}"
            pages = sorted(document_pages.get(digest, set())) if digest else []
            sources.append({
                "title": title,
                "text": MISSING,
                "pages": pages or MISSING,
                "truncated": False,
            })
    sources.append({"title": "안내", "text": DISCLAIMER, "pages": MISSING, "truncated": False})
    return sources


def _node_value(node: dict) -> str:
    props = node.get("props") or {}
    preferred = ("text", "value", "description", "name", "amount", "rate", "method")
    values = [str(props[key]).strip() for key in preferred if props.get(key) not in (None, "")]
    if not values:
        name = node.get("name")
        values = [str(name).strip()] if name else []
    return " · ".join(dict.fromkeys(values)) if values else MISSING


def build_compare_table(subgraph: dict) -> dict | None:
    """Summarize available benefit graph relationships in one row per selected card."""
    nodes = subgraph.get("nodes") or []
    all_cards = [node for node in nodes if node.get("label") == "Card"]
    seeds = {str(value) for value in (subgraph.get("seeds") or [])}
    cards = [node for node in all_cards if str(node.get("id")) in seeds] if seeds else all_cards
    if len(cards) < 2:
        return None
    by_id = {str(node.get("id")): node for node in nodes}
    edges = subgraph.get("edges") or []
    rows = []
    for card in cards:
        benefits = []
        for edge in edges:
            if edge.get("type") == "OFFERS" and str(edge.get("source")) == str(card.get("id")):
                target = by_id.get(str(edge.get("target")))
                if target and target.get("label") == "Benefit":
                    benefits.append(target)
        values = {"혜택": [], "조건": [], "한도": [], "제외": []}
        for benefit in benefits:
            values["혜택"].append(_node_value(benefit))
            for edge in edges:
                if str(edge.get("source")) != str(benefit.get("id")):
                    continue
                target = by_id.get(str(edge.get("target")))
                if target is None:
                    continue
                relation = edge.get("type")
                column = {"HAS_CONDITION": "조건", "HAS_LIMIT": "한도", "EXCLUDES": "제외"}.get(relation)
                if column:
                    values[column].append(_node_value(target))
        row = {"카드": str(card.get("name") or (card.get("props") or {}).get("product_name") or MISSING)}
        for column, entries in values.items():
            actual = [entry for entry in dict.fromkeys(entries) if entry != MISSING]
            row[column] = " · ".join(actual) if actual else MISSING
        rows.append(row)
    return {"columns": ["카드", "혜택", "조건", "한도", "제외"], "rows": rows}


def serialize_turn(turn: dict) -> str:
    """Serialize the v2 turn shape without dropping any user-visible fields."""
    required = ("question", "analysis_question", "answer", "sources", "compare_table", "selected_entities", "latency_ms")
    payload = {key: turn.get(key) for key in required}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
