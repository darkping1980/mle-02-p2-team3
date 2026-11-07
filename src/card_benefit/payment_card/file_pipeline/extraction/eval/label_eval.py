"""Evaluate human extraction labels against graph evidence.

A label and a node match only on the same PDF SHA-256 and page.  With
``--overlap any`` their inclusive evidence ranges need at least one shared
character; with ``--overlap 50`` the shared-character count must be at least
50 percent of the label's inclusive range length.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[6]
KINDS = ("Benefit", "Condition", "Limit", "Target")
RELATIONS = ("HAS_CONDITION", "HAS_LIMIT", "APPLIES_TO")


def safe_tmp(path):
    """Resolve an output directory, allowing only paths below /tmp."""
    path = Path(path).expanduser().resolve()
    tmp = Path("/tmp").resolve()
    if path == tmp or tmp not in path.parents or path == ROOT or ROOT in path.parents:
        raise ValueError("출력은 저장소 밖 /tmp 아래만 허용됩니다.")
    return path


def _csv_rows(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _overlaps(start, end, other_start, other_end, overlap):
    shared = max(0, min(end, other_end) - max(start, other_start) + 1)
    return shared >= 1 if overlap == "any" else shared * 2 >= end - start + 1


def _span_gap(start, end, other_start, other_end):
    """Return the number of characters strictly between two inclusive spans."""
    if end < other_start:
        return other_start - end - 1
    if other_end < start:
        return start - other_end - 1
    return 0


def _node_page(node_id):
    """Get the page embedded by the standard ``<sha>-pNNNN-cNN`` chunk id."""
    match = re.search(r"-p(\d+)-c\d+", node_id)
    return int(match.group(1)) if match else None


def _rate(hits, total):
    return None if not total else hits / total


def _metric(records, key, values):
    result = {}
    for value in values:
        subset = [row for row in records if row[key] == value]
        hits, total = sum(row["hit"] for row in subset), len(subset)
        result[value] = {"hits": hits, "total": total, "recall": _rate(hits, total),
                         "sample_note": "표본 부족" if total < 5 else None}
    return result


def _read_graph(graph_dirs):
    nodes, edges, evidence = {}, set(), defaultdict(list)
    for spec in graph_dirs:
        issuer, sep, directory = spec.partition("=")
        if not sep or not issuer or not directory:
            raise ValueError("--graph-dir은 issuer=directory 형식이어야 합니다.")
        directory = Path(directory).expanduser().resolve()
        for row in _csv_rows(directory / "fp_nodes.csv"):
            if row.get("node_type") in KINDS:
                # props is intentionally never accessed: it can contain body text.
                nodes[row["id"]] = row["node_type"]
        for row in _csv_rows(directory / "fp_edges.csv"):
            edges.add((row.get("source_id", ""), row.get("target_id", ""), row.get("edge_type", "")))
        for row in _csv_rows(directory / "fp_evidence.csv"):
            node_id = row.get("node_id", "")
            if node_id in nodes:
                evidence[node_id].append(row)
    return nodes, edges, evidence


def _pool_pages(pool_path, data_root):
    payload = json.loads(Path(pool_path).read_text(encoding="utf-8-sig"))
    pages = {}
    for item in payload:
        pid, relative, page = str(item.get("pid", "")), item.get("path"), item.get("page")
        if not pid or not relative or page is None:
            continue
        pdf = Path(data_root).resolve() / str(relative)
        pages[pid] = {"issuer": str(item.get("issuer", "")), "page": int(page),
                      "sha": _sha256(pdf) if pdf.is_file() else None}
    return pages


def _labels(labels_path, pages):
    labels = []
    with Path(labels_path).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            # Do not access row["text"]: the evaluator works solely with labels' coordinates.
            if row.get("kind") not in KINDS:
                raise ValueError("kind는 Benefit|Condition|Limit|Target 이어야 합니다.")
            page = pages.get(str(row.get("pid", "")), {})
            labels.append({"id": str(row.get("id", "")), "issuer": str(row.get("issuer", "")),
                           "pid": str(row.get("pid", "")), "kind": row["kind"],
                           "start": int(row["start"]), "end": int(row["end"]),
                           "parent_id": str(row.get("parent_id", "")), "relation": str(row.get("relation", "")),
                           "page": page.get("page"), "sha": page.get("sha")})
    return labels


def evaluate(labels_path, pool_path, graph_dirs, data_root, output_dir, overlap="any", near_chars=30):
    """Write summary.json and misses.csv and return the JSON-compatible summary."""
    if overlap not in {"any", "50"}:
        raise ValueError("--overlap은 any 또는 50 이어야 합니다.")
    if near_chars < 0:
        raise ValueError("--near-chars는 0 이상이어야 합니다.")
    output = safe_tmp(output_dir)
    nodes, edges, evidence = _read_graph(graph_dirs)
    pages = _pool_pages(pool_path, data_root)
    labels = _labels(labels_path, pages)
    prefixes = {node_id[:16] for node_id in nodes}
    by_kind_page = defaultdict(list)
    by_document_page = defaultdict(list)
    nonlocated_page = defaultdict(bool)
    for node_id, kind in nodes.items():
        for item in evidence.get(node_id, []):
            try:
                page = int(item["page_no"])
            except (KeyError, TypeError, ValueError):
                page = _node_page(node_id)
            if not page or not item.get("doc_sha256"):
                continue
            key = (kind, item["doc_sha256"], page)
            if item.get("quote_status") == "located":
                try:
                    span = (node_id, int(item["start_pos"]), int(item["end_pos"]))
                    by_kind_page[key].append(span)
                    by_document_page[(item["doc_sha256"], page)].append((kind, *span))
                except (TypeError, ValueError):
                    pass
            else:
                nonlocated_page[key] = True
    misses, matched = [], {}
    for label in labels:
        in_graph = bool(label["sha"] and label["sha"][:16] in prefixes)
        key = (label["kind"], label["sha"], label["page"])
        candidates = by_kind_page.get(key, [])
        hits = [node_id for node_id, start, end in candidates if _overlaps(label["start"], label["end"], start, end, overlap)]
        if not in_graph:
            reason = "document_not_in_graph"
        elif hits:
            reason = None
        elif candidates:
            reason = "node_on_page_no_overlap"
        elif nonlocated_page.get(key):
            reason = "evidence_not_located"
        else:
            reason = "no_node_on_page"
        label["document_in_graph"], label["hit"] = in_graph, bool(hits)
        matched[label["id"]] = set(hits)
        if reason:
            detail, other_kind, nearest_gap = "", "", ""
            if reason == "node_on_page_no_overlap":
                same_kind_gaps = [
                    _span_gap(label["start"], label["end"], start, end)
                    for _, start, end in candidates
                ]
                nearest = min(same_kind_gaps)
                if nearest <= near_chars:
                    detail = "boundary_near"
                else:
                    other_kind_candidates = []
                    for kind, _, start, end in by_document_page.get((label["sha"], label["page"]), []):
                        if kind == label["kind"]:
                            continue
                        gap = _span_gap(label["start"], label["end"], start, end)
                        if gap <= near_chars:
                            other_kind_candidates.append((gap, kind))
                    if other_kind_candidates:
                        detail = "wrong_kind_nearby"
                        other_kind = min(other_kind_candidates)[1]
                    else:
                        detail = "true_missing_candidate"
                        nearest_gap = str(nearest)
            misses.append({"id": label["id"], "kind": label["kind"], "pid": label["pid"], "issuer": label["issuer"],
                           "reason": reason, "detail": detail, "other_kind": other_kind, "nearest_gap": nearest_gap})
    label_bases = {}
    for name, subset in (("all", labels), ("document_in_graph", [row for row in labels if row["document_in_graph"]])):
        label_bases[name] = {"by_kind": _metric(subset, "kind", KINDS),
                             "by_issuer": _metric(subset, "issuer", sorted({row["issuer"] for row in subset})),
                             "by_page": _metric(subset, "pid", sorted({row["pid"] for row in subset}))}
    relations = []
    ids = {row["id"]: row for row in labels}
    for child in labels:
        if not child["parent_id"] or child["relation"] not in RELATIONS:
            continue
        parent = ids.get(child["parent_id"])
        hit = bool(parent and parent["hit"] and child["hit"] and any((source, target, child["relation"]) in edges for source in matched[parent["id"]] for target in matched[child["id"]]))
        relations.append({"type": child["relation"], "hit": hit, "document_in_graph": bool(parent and parent["document_in_graph"] and child["document_in_graph"])})
    relation_bases = {"all": {"by_type": _metric(relations, "type", RELATIONS)},
                      "document_in_graph": {"by_type": _metric([row for row in relations if row["document_in_graph"]], "type", RELATIONS)}}
    unlabeled = Counter()
    labeled_pages = {(row["sha"], row["page"]) for row in labels if row["sha"] and row["page"]}
    for (kind, sha, page), spans in by_kind_page.items():
        if (sha, page) not in labeled_pages:
            continue
        page_labels = [row for row in labels if row["kind"] == kind and row["sha"] == sha and row["page"] == page]
        for _, start, end in spans:
            if not any(_overlaps(label["start"], label["end"], start, end, overlap) for label in page_labels):
                unlabeled[kind] += 1
    details = ("boundary_near", "wrong_kind_nearby", "true_missing_candidate")
    near_hits = {kind: sum(row["kind"] == kind and row["detail"] == "boundary_near" for row in misses) for kind in KINDS}
    miss_detail_counts = {
        detail: {kind: sum(row["kind"] == kind and row["detail"] == detail for row in misses) for kind in KINDS}
        for detail in details
    }
    summary = {"overlap": overlap, "labels": label_bases, "relations": relation_bases,
               "unlabeled_nodes": {kind: unlabeled[kind] for kind in KINDS},
               "near_hits": near_hits, "miss_detail_counts": miss_detail_counts,
               "miss_reason_counts": dict(sorted(Counter(row["reason"] for row in misses).items())),
               "note": "near는 hit으로 계산하지 않음 (near 는 hit 로 세지 않음), unlabeled_nodes는 정밀도 아님, 라벨 표본 한계"}
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (output / "misses.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "kind", "pid", "issuer", "reason", "detail", "other_kind", "nearest_gap"])
        writer.writeheader(); writer.writerows(misses)
    print(_table(summary))
    return summary


def _table(summary):
    lines = ["basis | slice | hits/total | recall | note"]
    for basis in ("all", "document_in_graph"):
        for kind, metric in summary["labels"][basis]["by_kind"].items():
            recall = "-" if metric["recall"] is None else f"{metric['recall']:.3f}"
            lines.append(f"{basis} | {kind} | {metric['hits']}/{metric['total']} | {recall} | {metric['sample_note'] or ''}")
    lines.append("unlabeled_nodes: " + ", ".join(f"{kind}={count}" for kind, count in summary["unlabeled_nodes"].items()))
    lines.append("near_hits: " + ", ".join(f"{kind}={count}" for kind, count in summary["near_hits"].items()))
    lines.append("정밀도 아님, 라벨 표본 한계")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate phrase-level extraction labels against graph evidence.")
    parser.add_argument("--labels", required=True); parser.add_argument("--pool", required=True)
    parser.add_argument("--graph-dir", action="append", required=True); parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-dir", required=True); parser.add_argument("--overlap", choices=("any", "50"), default="any")
    parser.add_argument("--near-chars", type=int, default=30)
    args = parser.parse_args(argv)
    evaluate(args.labels, args.pool, args.graph_dir, args.data_root, args.output_dir, args.overlap, args.near_chars)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
