"""Pure answer-number grounding checks.

Number tokenization follows ``answer_eval._number_candidates`` (same regex,
unit scaling, and full Korean date exclusion); this module adds graph scoping.
"""
from __future__ import annotations

import re

try:
    from .answer_eval import _number_candidates
except ImportError:  # Script-style imports from this directory.
    from answer.answer_eval import _number_candidates


_SCOPE_EDGE_TYPES = {"HAS_LIMIT", "HAS_CONDITION", "APPLIES_TO", "EXCLUDES"}
_DATE_RE = re.compile(
    r"(?<!\d)(?:\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|"
    r"\d{4}\s*[-./]\s*\d{1,2}\s*[-./]\s*\d{1,2})(?!\d)"
)
_PAGE_RE = re.compile(
    r"(?:\bp\.?\s*\d+|\bpage\s*\d+|\b(?:페이지|쪽)\s*\d+|\d+\s*(?:페이지|쪽))", re.I
)


def _unit_kind(unit):
    if unit == "원":
        return "won"
    if unit == "%":
        return "percent"
    if unit in {"회", "개월", "일", "점"}:
        return "count"
    return "unitless"


def numbers_in(text) -> list[dict]:
    """Return numeric tokens with normalized value, unit, and original token."""
    value = str(text or "")
    excluded = [match.span() for pattern in (_DATE_RE, _PAGE_RE) for match in pattern.finditer(value)]
    results = []
    for number, unit, start, end in _number_candidates(value):
        if any(start < right and end > left for left, right in excluded):
            continue
        raw = value[start:end].rstrip(",")
        kind = _unit_kind(unit)
        if kind == "unitless" and re.search(r"(?:억|만|천)\s*$", raw):
            kind = "won"
        normalized = float(number) if kind == "percent" else int(number) if number.is_integer() else number
        results.append({"value": normalized, "unit": unit, "kind": kind, "raw": raw})
    return results


def scope_nodes(subgraph, benefit_ids) -> set:
    """Return Benefits, their direct rule/target neighbors, and offering Cards."""
    subgraph = subgraph or {}
    nodes = list(subgraph.get("nodes") or [])
    edges = list(subgraph.get("edges") or [])
    benefits = {str(item) for item in (benefit_ids or [])}
    scoped = set(benefits)
    for edge in edges:
        source, target = str(edge.get("source")), str(edge.get("target"))
        edge_type = edge.get("type")
        if source in benefits and edge_type in _SCOPE_EDGE_TYPES:
            scoped.add(target)
        if edge_type == "OFFERS" and target in benefits:
            scoped.add(source)
    return {node.get("id") for node in nodes if str(node.get("id")) in scoped}


def _node_text(node):
    values = [node.get("name", "")]
    props = node.get("props") or {}
    if isinstance(props, dict):
        values.extend(value for value in props.values() if isinstance(value, str))
    return " ".join(str(value) for value in values)


def _number_keys(text):
    return {(item["value"], item["kind"]) for item in numbers_in(text)}


def check_answer_numbers(answer, subgraph, seed_benefit_ids=None) -> dict:
    """Classify answer numbers against the selected Benefit's local graph."""
    subgraph = subgraph or {}
    nodes = list(subgraph.get("nodes") or [])
    answer_tokens = numbers_in(answer)
    whole_keys = set().union(*(_number_keys(_node_text(node)) for node in nodes)) if nodes else set()
    has_scope = bool(seed_benefit_ids)
    scoped_ids = scope_nodes(subgraph, seed_benefit_ids) if has_scope else set()
    scoped_keys = set().union(*(
        _number_keys(_node_text(node)) for node in nodes
        if node.get("id") in scoped_ids
    )) if scoped_ids else set()

    scoped_grounded, elsewhere_only, ungrounded, whole_subgraph_grounded = [], [], [], []
    for token in answer_tokens:
        key = (token["value"], token["kind"])
        if has_scope:
            if key in scoped_keys:
                scoped_grounded.append(token)
            elif key in whole_keys:
                elsewhere_only.append(token)
            else:
                ungrounded.append(token)
        elif key in whole_keys:
            whole_subgraph_grounded.append(token)
        else:
            ungrounded.append(token)

    return {
        "scope_unknown": not has_scope,
        "scoped_grounded": scoped_grounded,
        "elsewhere_only": elsewhere_only,
        "ungrounded": ungrounded,
        "whole_subgraph_grounded": whole_subgraph_grounded,
        "counts": {
            "scoped_grounded": len(scoped_grounded),
            "elsewhere_only": len(elsewhere_only),
            "ungrounded": len(ungrounded),
            "whole_subgraph_grounded": len(whole_subgraph_grounded),
        },
    }
