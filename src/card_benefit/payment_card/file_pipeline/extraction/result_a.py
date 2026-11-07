"""DRAFT stage 7 Result A JSONL; align with the counterpart in stage 8.

This module reads file_pipeline result JSON only. It does not read db_pipeline
or map to the counterpart format. Quote text is deliberately excluded.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

GROUPS = {"benefits": "Benefit", "conditions": "Condition", "limits": "Limit", "targets": "Target"}


def export_result_a(result_dir, chunk_dir, output_dir):
    result_dir, chunk_dir, output_dir = map(lambda p: Path(p).expanduser().resolve(), (result_dir, chunk_dir, output_dir))
    chunks = {}
    for path in chunk_dir.glob("*.chunks.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for chunk in data.get("chunks", []):
            chunks[chunk.get("chunk_id")] = (data, chunk)
    rows, counts = [], Counter()
    for path in sorted(result_dir.glob("*.result.json")):
        result = json.loads(path.read_text(encoding="utf-8"))
        extraction = result.get("extraction") or {}
        chunk_doc, chunk = chunks.get(result.get("chunk_id"), ({}, {}))
        doc_sha = result.get("doc_sha256") or chunk_doc.get("doc_sha256")
        page_no = result.get("page_no") or chunk.get("page_no")
        ambiguous = {f.get("path") for f in result.get("failures", []) if f.get("code") == "quote_location_ambiguous"}
        for group, entity_type in GROUPS.items():
            for i, item in enumerate(extraction.get(group, [])):
                _append_item(rows, counts, item, f"{group}[{i}]", entity_type, f"{result.get('chunk_id')}:{item.get('id')}", doc_sha, page_no, ambiguous)
        items = {item.get("id"): (group, item) for group in GROUPS for item in extraction.get(group, [])}
        for i, rel in enumerate(extraction.get("relations", [])):
            src = items.get(rel.get("source")); tgt = items.get(rel.get("target"))
            _append_item(rows, counts, rel, f"relations[{i}]", "Relation", f"{result.get('chunk_id')}:rel-{i+1}", doc_sha, page_no, ambiguous,
                         {"type": rel.get("type"), "source": f"{result.get('chunk_id')}:{rel.get('source')}", "target": f"{result.get('chunk_id')}:{rel.get('target')}",
                          "source_type": GROUPS.get(src[0]) if src else None, "target_type": GROUPS.get(tgt[0]) if tgt else None})
    output_dir.mkdir(parents=True, exist_ok=True)
    located = [r for r in rows if r["quote_status"] == "located"]
    unlocated = [r for r in rows if r["quote_status"] != "located"]
    (output_dir / "result_a.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in located), encoding="utf-8")
    (output_dir / "result_a_unlocated.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in unlocated), encoding="utf-8")
    summary = {"rows": len(rows), "located": counts["located"], "ambiguous": counts["ambiguous"], "missing": counts["missing"], "unlocated_file_rows": len(unlocated)}
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def _append_item(rows, counts, item, path, entity_type, entity_key, doc_sha, page_no, ambiguous, relation=None):
    normalized = relation or {key: item.get(key) for key in ("name", "method", "rate", "amount", "kind", "min_amount", "period", "unlimited", "shared") if key in item}
    for i, evidence in enumerate(item.get("evidence", [])):
        ep = f"{path}.evidence[{i}]"
        loc = evidence.get("location")
        status = "ambiguous" if ep in ambiguous else ("located" if isinstance(loc, dict) else "missing")
        counts[status] += 1
        rows.append({"doc_sha256": (loc or {}).get("doc_sha256") or doc_sha, "page_no": (loc or {}).get("page_no") if status == "located" else None,
                     "start_pos": (loc or {}).get("start_pos") if status == "located" else None, "end_pos": (loc or {}).get("end_pos") if status == "located" else None,
                     "quote_status": status, "entity_type": entity_type, "entity_key": entity_key, "values": normalized})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-dir", required=True); parser.add_argument("--chunk-dir", required=True); parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(export_result_a(args.result_dir, args.chunk_dir, args.output_dir), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
