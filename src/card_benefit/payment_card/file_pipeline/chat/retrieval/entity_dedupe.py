"""Pure subgraph collapsing for validated within-card SAME_AS_STRONG links."""
from __future__ import annotations

from copy import deepcopy


def _node_sources(node: dict) -> list[dict]:
    sources = [deepcopy(item) for item in node.get("sources", []) if isinstance(item, dict)]
    props = node.get("props") or {}
    if props.get("source_text") or props.get("source_text_pages"):
        pages = props.get("source_text_pages") or []
        if not isinstance(pages, (list, tuple, set)):
            pages = [pages]
        sources.append({"text": props.get("source_text"), "pages": list(pages)})
    return sources


def dedupe_subgraph(subgraph: dict, group_mapping: dict[str, str]) -> dict:
    """Merge mapped nodes, retaining member evidence and rewriting graph references."""
    result = deepcopy(subgraph)
    nodes = result.get("nodes") or []
    by_id = {str(node.get("id")): node for node in nodes if node.get("id") is not None}

    def canonical_id(node_id: str) -> str:
        seen = set()
        current = str(node_id)
        while current in group_mapping and current not in seen:
            seen.add(current)
            current = str(group_mapping[current])
        return current

    grouped: dict[str, list[dict]] = {}
    for node in nodes:
        node_id = str(node.get("id", ""))
        grouped.setdefault(canonical_id(node_id), []).append(node)

    merged_nodes = []
    for target_id, members in grouped.items():
        canonical = deepcopy(by_id.get(target_id, members[0]))
        if len(members) > 1:
            sources = []
            pages = set()
            member_ids = []
            for member in members:
                member_ids.append(str(member.get("id", "")))
                for source in _node_sources(member):
                    source_pages = source.get("pages", [])
                    if not isinstance(source_pages, (list, tuple, set)):
                        source_pages = [source_pages]
                    source["pages"] = sorted({int(page) for page in source_pages if str(page).isdigit()})
                    pages.update(source["pages"])
                    sources.append(source)
            canonical["sources"] = sources
            canonical["merged_member_count"] = len(members)
            canonical["merged_member_ids"] = sorted(member_ids)
            props = dict(canonical.get("props") or {})
            props["source_text_pages"] = sorted(pages)
            canonical["props"] = props
        merged_nodes.append(canonical)

    result["nodes"] = merged_nodes
    remapped_edges = []
    seen_edges = set()
    for edge in result.get("edges") or []:
        rewritten = dict(edge)
        if "source" in rewritten:
            rewritten["source"] = canonical_id(str(rewritten["source"]))
        if "target" in rewritten:
            rewritten["target"] = canonical_id(str(rewritten["target"]))
        if rewritten.get("source") == rewritten.get("target"):
            continue
        key = (rewritten.get("source"), rewritten.get("target"), rewritten.get("type"))
        if key not in seen_edges:
            seen_edges.add(key)
            remapped_edges.append(rewritten)
    result["edges"] = remapped_edges
    remapped_evidence = []
    seen_evidence = set()
    for evidence in result.get("evidence") or []:
        rewritten = dict(evidence)
        if rewritten.get("node_id") is not None:
            rewritten["node_id"] = canonical_id(str(rewritten["node_id"]))
        if rewritten.get("node_id") is not None:
            key = tuple(sorted((key, repr(value)) for key, value in rewritten.items()))
        else:
            key = tuple(sorted((key, repr(value)) for key, value in rewritten.items()))
        if key not in seen_evidence:
            seen_evidence.add(key)
            remapped_evidence.append(rewritten)
    if "evidence" in result:
        result["evidence"] = remapped_evidence
    result["seeds"] = list(dict.fromkeys(canonical_id(str(seed)) for seed in result.get("seeds") or []))
    return result
