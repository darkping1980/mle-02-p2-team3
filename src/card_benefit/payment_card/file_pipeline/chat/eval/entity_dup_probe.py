"""Estimate within-card duplicate impact on retrieved golden-question subgraphs.

Start-node selection is an approximation: deterministic SeedMatcher selection
replaces the chatbot's LLM selection and its candidate-ranking stage.
The CSV traversal is stable by input row order, unlike PostgreSQL's unordered
LIMIT, and uses a fixed two-hop analysis because question-level LLM analysis
cannot be reproduced in this offline probe.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict, deque
from pathlib import Path
from typing import Iterable

from ..retrieval.entity_dedupe import dedupe_subgraph
from ...graph.entity_links_loader import validate_links
from .retrieval_eval import uuidish
from .seed_matcher import SeedMatcher

MAX_NODES = 40
HOPS = 2


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def load_graph(folders: Iterable[Path]) -> tuple[list[dict], list[dict], list[dict]]:
    """Load graph CSV rows and synthesize document nodes as retrieval_eval does."""
    nodes: list[dict] = []
    edges_raw: list[dict] = []
    evidence: list[dict] = []
    for folder in folders:
        for row in _read_csv(Path(folder) / "fp_nodes.csv"):
            try:
                props = json.loads(row.get("props") or "{}")
            except (ValueError, TypeError):
                props = {}
            if not isinstance(props, dict):
                props = {}
            name = str(props.get("name") or props.get("text") or props.get("product_name") or row["id"])
            name = " ".join(name.split())[:80]
            nodes.append({
                "id": uuidish(row["id"]), "name": name, "label": row["node_type"],
                "props": {k: v for k, v in props.items() if k != "name" and isinstance(v, (str, int, float, bool))},
                "_fp_id": row["id"],
            })
        edges_raw.extend(_read_csv(Path(folder) / "fp_edges.csv"))
        evidence.extend(_read_csv(Path(folder) / "fp_evidence.csv"))

    fp_nodes = {node["_fp_id"]: node for node in nodes}
    documents: dict[str, list[dict]] = defaultdict(list)
    for row in evidence:
        if row.get("doc_sha256"):
            documents[row["doc_sha256"]].append(row)
    for sha, rows in documents.items():
        located_pages = [int(r["page_no"]) for r in rows
                         if r.get("quote_status") == "located" and r.get("page_no", "").isdigit()]
        page = min(located_pages, default=None)
        nodes.append({
            "id": uuidish("doc:" + sha), "name": "문서 " + sha[:8], "label": "Document",
            "props": {"summary": f"문서 해시 {sha[:8]}, 쪽 {page if page is not None else '미상'}…", "fp_id": "doc:" + sha},
        })

    raw_to_uuid = {node["_fp_id"]: node["id"] for node in fp_nodes.values()}
    edge_by_fp_id = {edge["id"]: edge for edge in edges_raw}
    edges = [{"source": raw_to_uuid[row["source_id"]], "target": raw_to_uuid[row["target_id"]], "type": row["edge_type"], "_fp_id": row["id"]}
             for row in edges_raw if row.get("source_id") in raw_to_uuid and row.get("target_id") in raw_to_uuid]
    return nodes, edges, evidence


def load_link_mapping(path: Path) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Return normalized merge targets and group membership from within-card links."""
    rows = _read_csv(path)
    validation = validate_links(within_csv=path)
    if validation["errors"]:
        raise ValueError("invalid within-card entity links: " + "; ".join(validation["errors"]))
    groups: dict[str, dict] = {}
    for row in rows:
        group_id = row.get("group_id", "")
        group = groups.setdefault(group_id, {"issuer": row.get("issuer", ""), "card_id": row.get("card_id", ""), "canonical": row.get("canonical_node_id", ""), "members": set()})
        if row.get("scope", "within_card") != "within_card":
            continue
        group["members"].add(row.get("member_node_id", ""))
    mapping = {uuidish(member): uuidish(canonical)
               for member, canonical in validation["merge_mapping"].items()}
    member_groups: dict[str, set[str]] = defaultdict(set)
    for gid, group in groups.items():
        if not gid or not group["canonical"]:
            continue
        canonical = uuidish(group["canonical"])
        for member in group["members"]:
            if member:
                normalized = uuidish(member)
                member_groups[gid].add(normalized)
    return mapping, member_groups


def _retrieve(nodes: list[dict], edges: list[dict], seed_names: list[str]) -> dict:
    """Mirror rag._explore: exact-name seeds first, undirected reach, 40 nodes."""
    seeds = [node for node in nodes if node["label"] != "Document" and node["name"] in set(seed_names)]
    by_id = {node["id"]: node for node in nodes}
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge["source"]].append(edge["target"])
        adjacency[edge["target"]].append(edge["source"])
    depth = {node["id"]: 0 for node in seeds}
    queue = deque(node["id"] for node in seeds)
    while queue:
        current = queue.popleft()
        if depth[current] >= HOPS:
            continue
        for neighbor in adjacency[current]:
            if neighbor not in depth:
                depth[neighbor] = depth[current] + 1
                queue.append(neighbor)
    # SQL's reach LIMIT 40 is unspecified; CSV input order is a stable approximation.
    reach_rows = [node for node in nodes if node["id"] in depth][:MAX_NODES]
    ordered = list({node["id"]: node for node in [*seeds, *reach_rows]}.values())[:MAX_NODES]
    ids = {node["id"] for node in ordered}
    return {"nodes": ordered, "edges": [edge for edge in edges if edge["source"] in ids and edge["target"] in ids],
            "seeds": [node["id"] for node in seeds if node["id"] in ids]}


def _subgraph_evidence(subgraph: dict, graph_edges: list[dict], rows: list[dict]) -> tuple[list[dict], set[str]]:
    ids = {node["id"] for node in subgraph["nodes"]}
    edge_by_fp_id = {edge.get("_fp_id"): edge for edge in graph_edges}
    evidence_rows = []
    evidence_node_ids: set[str] = set()
    for index, row in enumerate(rows):
        node_id = uuidish(row["node_id"]) if row.get("node_id") else None
        edge = edge_by_fp_id.get(row.get("edge_id"))
        endpoints = {edge["source"], edge["target"]} if edge else set()
        direct_in = node_id in ids if node_id else False
        edge_in = bool(endpoints) and endpoints <= ids
        if not direct_in and not edge_in:
            continue
        item = {"_probe_evidence_id": str(index), "doc_sha256": row.get("doc_sha256", ""), "page_no": row.get("page_no", ""),
                "quote_status": row.get("quote_status", "")}
        if direct_in:
            item["node_id"] = node_id
            evidence_node_ids.add(node_id)
        else:
            item["edge_id"] = row.get("edge_id", "")
            item["_probe_endpoint_ids"] = sorted(endpoints)
            evidence_node_ids.update(endpoints)
        evidence_rows.append(item)
    subgraph["evidence"] = evidence_rows
    return evidence_rows, evidence_node_ids


def _golden_page_nodes(question: dict, subgraph: dict, evidence_rows: list[dict], evidence_node_ids: set[str]) -> set[str]:
    """Match a golden filename to a retrieved Card node, then use its page evidence."""
    page = str(question.get("evidence_page", ""))
    filename = str(question.get("evidence_doc", ""))
    if not page or not filename:
        return set()
    normalize = lambda value: "".join(re.findall(r"[0-9a-z가-힣]+", str(value).lower()))
    doc_key = normalize(Path(filename).stem)
    card_ids = set()
    for node in subgraph["nodes"]:
        if node.get("label") != "Card":
            continue
        product_key = normalize(node.get("props", {}).get("product_name") or node.get("name", ""))
        if product_key and (product_key in doc_key or doc_key in product_key):
            card_ids.add(node["id"])
    if not card_ids:
        return set()
    matching_shas = {row.get("doc_sha256") for row in evidence_rows
                     if str(row.get("page_no", "")) == page
                     and (row.get("node_id") in card_ids or card_ids.intersection(row.get("_probe_endpoint_ids", [])))}
    if not matching_shas:
        return set()
    return {node_id for node_id in evidence_node_ids
            if any(str(ev.get("page_no", "")) == page and ev.get("doc_sha256") in matching_shas
                   for ev in evidence_rows)}


def evaluate_question(question: dict, nodes: list[dict], edges: list[dict], raw_evidence: list[dict],
                      matcher: SeedMatcher, mapping: dict[str, str], member_groups: dict[str, set[str]]) -> dict:
    seeds = matcher.select(str(question.get("question", "")), n=3, threshold=0.15)
    subgraph = _retrieve(nodes, edges, seeds)
    before_nodes = len(subgraph["nodes"])
    before_evidence, evidence_node_ids = _subgraph_evidence(subgraph, edges, raw_evidence)
    in_subgraph = {node["id"] for node in subgraph["nodes"]}
    overlap = {group_id: sorted(members & in_subgraph) for group_id, members in member_groups.items()}
    overlap = {group_id: members for group_id, members in overlap.items() if len(members) >= 2}
    deduped = dedupe_subgraph(subgraph, mapping)
    # Probe IDs prevent the deduper from coalescing distinct source rows when
    # their node references become the same canonical ID.
    after_nodes = len(deduped["nodes"])
    after_evidence = len(deduped.get("evidence", []))
    evidence_violations = int(after_evidence != len(before_evidence))
    before_reps = {node_id: mapping.get(node_id, node_id) for node_id in evidence_node_ids}
    after_ids = {node["id"] for node in deduped["nodes"]}
    golden_ids = _golden_page_nodes(question, subgraph, before_evidence, evidence_node_ids)
    golden_affected = any(node_id not in after_ids or before_reps.get(node_id) != node_id for node_id in golden_ids)
    golden_vanished = sum(node_id not in after_ids for node_id in golden_ids)
    golden_changed = sum(before_reps.get(node_id) != node_id for node_id in golden_ids)
    names = {node["id"]: node["name"] for node in nodes}
    card_names = []
    if question.get("evidence_doc"):
        stem = Path(str(question["evidence_doc"])).stem
        stem = re.sub(r"^(신용|체크)_", "", stem)
        stem = re.split(r"_상품설명서|_공식PDF|_g1_", stem, maxsplit=1)[0]
        stem = re.sub(r"_\d{4,}$", "", stem)
        card_names = [stem[:40]] if stem else []
    if not card_names:
        card_names = [node["name"] for node in subgraph["nodes"] if node.get("label") == "Card"]
    return {
        "id": question.get("id", ""), "split": question.get("_split", "all"),
        "card_name": (card_names[0] if card_names else "")[:40],
        "node_count_before": before_nodes, "node_count_after": after_nodes,
        "duplicate_groups_present": len(overlap), "duplicate_members_present": sum(map(len, overlap.values())),
        "nodes_reduced": before_nodes - after_nodes, "evidence_count_before": len(before_evidence),
        "evidence_count_after": after_evidence, "evidence_preservation_violation": evidence_violations,
        "golden_evidence_affected": int(golden_affected), "golden_evidence_nodes_vanished": golden_vanished,
        "golden_evidence_nodes_changed_representative": golden_changed,
    }


def summarize(rows: list[dict]) -> dict:
    count = len(rows)
    reduced = [row for row in rows if row["nodes_reduced"] >= 1]
    mean_reduced = sum(row["nodes_reduced"] for row in rows) / count if count else 0.0
    mean_nodes = sum(row["node_count_before"] for row in rows) / count if count else 0.0
    return {
        "questions": count, "affected_questions": len(reduced), "affected_ratio": len(reduced) / count if count else 0.0,
        "mean_nodes_reduced": mean_reduced, "max_nodes_reduced": max((r["nodes_reduced"] for r in rows), default=0),
        "mean_subgraph_nodes_before": mean_nodes,
        "mean_reduced_to_mean_subgraph_ratio": mean_reduced / mean_nodes if mean_nodes else 0.0,
        "evidence_preservation_violations": sum(r["evidence_preservation_violation"] for r in rows),
        "golden_evidence_affected_questions": sum(r["golden_evidence_affected"] for r in rows),
    }


def _safe_output(path: Path) -> Path:
    output = path.expanduser().resolve()
    if Path("/tmp").resolve() not in output.parents:
        raise ValueError("outputs must be under /tmp")
    return output


def run(questions_path: Path, hana_dir: Path, woori_dir: Path, links_path: Path,
        csv_output: Path, json_output: Path, dev_questions_path: Path | None = None,
        final_questions_path: Path | None = None) -> dict:
    questions = json.loads(questions_path.read_text(encoding="utf-8"))["questions"]
    split_by_id = {}
    for split_name, split_path in (("dev", dev_questions_path), ("final", final_questions_path)):
        if split_path is not None:
            split_by_id.update({q.get("id"): split_name for q in json.loads(split_path.read_text(encoding="utf-8"))["questions"]})
    for question in questions:
        question["_split"] = split_by_id.get(question.get("id"), "unassigned")
    nodes, edges, raw_evidence = load_graph((hana_dir, woori_dir))
    matcher = SeedMatcher(nodes)
    mapping, groups = load_link_mapping(links_path)
    rows = [evaluate_question(q, nodes, edges, raw_evidence, matcher, mapping, groups) for q in questions]
    split_rows = {name: [row for row in rows if row["split"] == name] for name in ("dev", "final")}
    result = {"method": {"seed_selector": "SeedMatcher(n=3, threshold=0.15)", "hops": HOPS, "max_nodes": MAX_NODES,
                         "approximations": ["LLM start-node selection replaced by deterministic SeedMatcher", "fixed two-hop CSV traversal; question analysis is not reproduced", "CSV order approximates unordered SQL LIMIT 40"]},
              "all": summarize(rows), "dev": summarize(split_rows["dev"]), "final": summarize(split_rows["final"]),
              "top_overlap": [{"id": r["id"], "card_name": r["card_name"]}
                              for r in sorted(rows, key=lambda x: (-x["duplicate_members_present"], -x["duplicate_groups_present"], x["id"]))[:5]],
              "questions": rows}
    csv_path, json_path = _safe_output(csv_output), _safe_output(json_output)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["id", "split", "card_name", "node_count_before", "node_count_after", "duplicate_groups_present", "duplicate_members_present", "nodes_reduced", "evidence_count_before", "evidence_count_after", "evidence_preservation_violation", "golden_evidence_affected", "golden_evidence_nodes_vanished", "golden_evidence_nodes_changed_representative"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in rows)
    json_path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--dev-questions", type=Path)
    parser.add_argument("--final-questions", type=Path)
    parser.add_argument("--hana-dir", required=True, type=Path)
    parser.add_argument("--woori-dir", required=True, type=Path)
    parser.add_argument("--links", required=True, type=Path)
    parser.add_argument("--csv-output", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run(args.questions, args.hana_dir, args.woori_dir, args.links, args.csv_output, args.json_output,
                 args.dev_questions, args.final_questions)
    print(json.dumps({key: result[key] for key in ("all", "dev", "final", "top_overlap")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
