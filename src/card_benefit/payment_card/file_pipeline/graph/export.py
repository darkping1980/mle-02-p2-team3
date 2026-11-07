"""Convert extraction result JSON files into validated graph CSV files."""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

_REPO_ROOT = Path(__file__).resolve().parents[5]
CSV_COLUMNS = {
    "fp_load_runs": ["run_id", "input_folder_name", "model_name", "started_at", "node_count", "edge_count"],
    "fp_nodes": ["id", "node_type", "props", "chunk_id", "run_id"],
    "fp_edges": ["id", "source_id", "target_id", "edge_type", "run_id"],
    "fp_evidence": ["node_id", "edge_id", "doc_sha256", "page_no", "start_pos", "end_pos", "quote_status"],
}
ALLOWED_ENDPOINTS = {
    "HAS_CONDITION": ("Benefit", "Condition"), "HAS_LIMIT": ("Benefit", "Limit"),
    "APPLIES_TO": ("Benefit", "Target"), "EXCLUDES": ("Benefit", "Target"),
    "MUTUALLY_EXCLUSIVE": ("Benefit", "Benefit"), "OFFERS": ("Card", "Benefit"),
}
NODE_GROUPS = (("benefits", "Benefit"), ("conditions", "Condition"), ("limits", "Limit"), ("targets", "Target"))
PROPS = {
    "Benefit": ("name", "method", "rate", "amount"), "Condition": ("text", "kind", "min_amount"),
    "Limit": ("text", "period", "amount", "unlimited", "shared"), "Target": ("text", "kind"),
}


def _read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, columns, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _valid_location(location):
    if not isinstance(location, dict):
        return False
    try:
        return bool(location.get("doc_sha256")) and int(location["page_no"]) >= 1 and int(location["start_pos"]) >= 1 and int(location["end_pos"]) >= int(location["start_pos"])
    except (KeyError, TypeError, ValueError):
        return False


def export_files(result_dir, chunk_dir, index_dir, model_name, output_dir, run_id=None):
    result_dir, chunk_dir, index_dir = [Path(p).expanduser().resolve() for p in (result_dir, chunk_dir, index_dir)]
    output_dir = Path(output_dir).expanduser().resolve()
    if output_dir == _REPO_ROOT or _REPO_ROOT in output_dir.parents:
        raise ValueError("출력 폴더는 저장소 밖이어야 합니다.")
    output_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    run_id = run_id or f"{result_dir.name}-{now.strftime('%Y%m%dT%H%M%SZ')}"
    started_at = now.isoformat(timespec="seconds")

    chunks = {}
    for path in chunk_dir.glob("*.json"):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            for chunk in document.get("chunks", []):
                chunks[chunk.get("chunk_id")] = {"doc_id": document.get("doc_id"), "doc_sha256": document.get("doc_sha256"), "page_no": chunk.get("page_no")}
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    products_by_doc = {}
    for row in _read_csv(index_dir / "product_docs.csv"):
        products_by_doc.setdefault(row.get("doc_id"), []).append(row)
    doc_sha = {r.get("doc_id"): r.get("sha256") for r in _read_csv(index_dir / "documents.csv")}

    nodes, edges, evidences = [], [], []
    skipped = 0
    invalid = Counter()
    quote_counts = Counter()
    seen_nodes, seen_edges, seen_edge_keys = set(), set(), set()
    card_registry = {}

    for path in sorted(result_dir.glob("*.result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        extraction = result.get("extraction")
        if extraction is None:
            skipped += 1
            continue
        chunk_id = result.get("chunk_id")
        chunk_info = chunks.get(chunk_id, {})
        doc_id = chunk_info.get("doc_id")
        result_nodes = {}
        for group, node_type in NODE_GROUPS:
            for item_index, item in enumerate(extraction.get(group, [])):
                node_id = f"{chunk_id}:{item.get('id')}"
                if node_id in seen_nodes:
                    invalid["duplicate_node_id"] += 1
                    continue
                seen_nodes.add(node_id)
                props = {key: item[key] for key in PROPS[node_type] if key in item}
                node = {"id": node_id, "node_type": node_type, "props": json.dumps(props, ensure_ascii=False, separators=(",", ":")), "chunk_id": chunk_id, "run_id": run_id}
                nodes.append(node)
                result_nodes[item.get("id")] = (node_id, node_type)
                _collect_evidence(evidences, quote_counts, invalid, item.get("evidence", []), f"{group}[{item_index}]", node_id, None, result, chunk_info, doc_sha, doc_id)

        rel_idx = 0
        for group in ("relations",):
            for i, relation in enumerate(extraction.get(group, [])):
                rel_idx += 1
                edge_id = f"{chunk_id}:rel-{rel_idx}"
                source, target = result_nodes.get(relation.get("source")), result_nodes.get(relation.get("target"))
                expected = ALLOWED_ENDPOINTS.get(relation.get("type"))
                if not source or not target:
                    invalid["missing_endpoint"] += 1
                    continue
                if not expected or (source[1], target[1]) != expected or (relation.get("type") == "MUTUALLY_EXCLUSIVE" and source[0] == target[0]):
                    invalid["invalid_endpoint_types"] += 1
                    continue
                if edge_id in seen_edges:
                    invalid["duplicate_edge_id"] += 1
                    continue
                edge_key = (source[0], target[0], relation["type"])
                if edge_key in seen_edge_keys:
                    invalid["duplicate_edge_relation"] += 1
                    continue
                seen_edges.add(edge_id)
                seen_edge_keys.add(edge_key)
                edges.append({"id": edge_id, "source_id": source[0], "target_id": target[0], "edge_type": relation["type"], "run_id": run_id})
                _collect_evidence(evidences, quote_counts, invalid, relation.get("evidence", []), f"relations[{i}]", None, edge_id, result, chunk_info, doc_sha, doc_id)

        for product in products_by_doc.get(doc_id, []):
            ids = json.loads(product.get("product_ids") or "{}")
            product_key = next((ids.get(k) for k in ("CD_ID", "PC_SEQ", "디자인코드", "모바일_CD_NO", "product_code") if ids.get(k)), None)
            if not product_key:
                invalid["missing_product_key"] += 1
                continue
            card_id = f"card:{product.get('issuer')}:{product_key}"
            if card_id not in card_registry:
                card_registry[card_id] = {"id": card_id, "node_type": "Card", "props": json.dumps({"issuer": product.get("issuer"), "product_name": product.get("product_name"), "card_type": product.get("card_type")}, ensure_ascii=False, separators=(",", ":")), "chunk_id": "", "run_id": run_id}
            for item in extraction.get("benefits", []):
                benefit_id = f"{chunk_id}:{item.get('id')}"
                edge_id = f"{chunk_id}:offers-{product_key}:{item.get('id')}"
                edge_key = (card_id, benefit_id, "OFFERS")
                if edge_id not in seen_edges and edge_key not in seen_edge_keys:
                    seen_edges.add(edge_id)
                    seen_edge_keys.add(edge_key)
                    edges.append({"id": edge_id, "source_id": card_id, "target_id": benefit_id, "edge_type": "OFFERS", "run_id": run_id})
    # Card nodes are inserted once after every chunk has been examined.
    for card_id, card_node in card_registry.items():
        if card_id in seen_nodes:
            invalid["duplicate_node_id"] += 1
        else:
            seen_nodes.add(card_id)
            nodes.append(card_node)
    node_types = {row["id"]: row["node_type"] for row in nodes}
    valid_edges = []
    for edge in edges:
        expected = ALLOWED_ENDPOINTS[edge["edge_type"]]
        if edge["source_id"] not in node_types or edge["target_id"] not in node_types:
            invalid["missing_endpoint"] += 1
        elif (node_types[edge["source_id"]], node_types[edge["target_id"]]) != expected:
            invalid["invalid_endpoint_types"] += 1
        else:
            valid_edges.append(edge)
    edge_ids = {e["id"] for e in valid_edges}
    node_ids = set(node_types)
    evidences = [e for e in evidences if _valid_evidence_row(e, node_ids, edge_ids, invalid)]
    quote_counts = Counter(e["quote_status"] for e in evidences)
    run_row = {"run_id": run_id, "input_folder_name": result_dir.name, "model_name": model_name, "started_at": started_at, "node_count": len(nodes), "edge_count": len(valid_edges)}
    _write_csv(output_dir / "fp_load_runs.csv", CSV_COLUMNS["fp_load_runs"], [run_row])
    _write_csv(output_dir / "fp_nodes.csv", CSV_COLUMNS["fp_nodes"], nodes)
    _write_csv(output_dir / "fp_edges.csv", CSV_COLUMNS["fp_edges"], valid_edges)
    _write_csv(output_dir / "fp_evidence.csv", CSV_COLUMNS["fp_evidence"], evidences)
    return {"chunks": len(list(result_dir.glob("*.result.json"))), "nodes": len(nodes), "edges": len(valid_edges), "evidence": len(evidences), "node_types": dict(sorted(Counter(n["node_type"] for n in nodes).items())), "skipped_chunks": skipped, "quote_status": dict(sorted(quote_counts.items())), "invalid_rows": dict(sorted(invalid.items()))}


def _collect_evidence(output, quote_counts, invalid, evidence_items, path_prefix, node_id, edge_id, result, chunk_info, doc_sha, doc_id):
    ambiguous = {f.get("path") for f in result.get("failures", []) if f.get("code") == "quote_location_ambiguous"}
    for idx, item in enumerate(evidence_items):
        path = f"{path_prefix}.evidence[{idx}]"
        location = item.get("location")
        # 반복 인용문은 위치를 null로 두는 정책(데스크탑 runner)이므로 ambiguous를 먼저 판정한다.
        status = "ambiguous" if path in ambiguous else ("missing" if location is None else "located")
        quote_counts[status] += 1
        # 옛 결과(첫 위치를 저장하던 버전)도 받되, located가 아니면 위치를 비운다.
        if status != "located":
            location = None
        output.append({"node_id": node_id or "", "edge_id": edge_id or "", "doc_sha256": (location or {}).get("doc_sha256") or doc_sha.get(doc_id) or result.get("doc_sha256") or "", "page_no": (location or {}).get("page_no", ""), "start_pos": (location or {}).get("start_pos", ""), "end_pos": (location or {}).get("end_pos", ""), "quote_status": status})


def _valid_evidence_row(row, node_ids, edge_ids, invalid):
    if bool(row["node_id"]) == bool(row["edge_id"]) or (row["node_id"] and row["node_id"] not in node_ids) or (row["edge_id"] and row["edge_id"] not in edge_ids):
        invalid["invalid_evidence_target"] += 1
        return False
    try:
        if row["quote_status"] not in ("located", "ambiguous", "missing") or not re.fullmatch(r"[0-9a-fA-F]{64}", row["doc_sha256"]):
            raise ValueError
        if row["quote_status"] == "located":
            if not row["doc_sha256"] or int(row["page_no"]) < 1 or int(row["start_pos"]) < 1 or int(row["end_pos"]) < int(row["start_pos"]):
                raise ValueError
        elif any(row[k] not in ("", None) for k in ("page_no", "start_pos", "end_pos")):
            raise ValueError
    except (TypeError, ValueError):
        invalid["invalid_evidence_position"] += 1
        return False
    return True


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-dir", required=True); parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--index-dir", required=True); parser.add_argument("--model-name", required=True)
    parser.add_argument("--output-dir", required=True); parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    summary = export_files(args.result_dir, args.chunk_dir, args.index_dir, args.model_name, args.output_dir, args.run_id)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
