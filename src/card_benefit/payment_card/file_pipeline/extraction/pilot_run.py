"""One-command, auditable pipeline orchestration; plan mode is fully offline."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import random

from .pilot import estimate_prompt_size

_REPO_ROOT = Path(__file__).resolve().parents[5]


def run_pilot(index_csv, chunk_dir, work_dir, count, model, workers=1, execute=False, temperature=None):
    index_csv, chunk_dir = Path(index_csv), Path(chunk_dir)
    work_dir = Path(work_dir).expanduser().resolve()
    if work_dir == _REPO_ROOT or _REPO_ROOT in work_dir.parents:
        raise ValueError("work-dir must be outside the repository")
    if count < 0:
        raise ValueError("count must be non-negative")
    work_dir.mkdir(parents=True, exist_ok=True)
    with index_csv.open(encoding="utf-8-sig", newline="") as f:
        index_rows = list(csv.DictReader(f))
    eligible_docs = {r.get("doc_id") for r in index_rows
                     if r.get("canonical") == "Y" and r.get("ocr_needed") != "Y"
                     and r.get("doc_role") in {"product_guide", "web_capture", "brand_service"}
                     and r.get("card_type") in {"credit", "common"}}
    all_chunks = []
    for path in sorted(chunk_dir.glob("*.chunks.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("doc_id") not in eligible_docs:
            continue
        all_chunks.extend(c.get("chunk_id") for c in doc.get("chunks", []) if c.get("chunk_id"))
    # Stable selection from indexed, canonical, non-OCR documents; no DB access.
    rng = random.Random(17)
    rng.shuffle(all_chunks)
    ids = all_chunks[:count]
    estimate = estimate_prompt_size(ids, chunk_dir)
    plan = {"mode": "execute" if execute else "plan", "selected_chunks": len(ids),
            "estimated_tokens": estimate["estimated_tokens"], "workers": max(1, min(16, workers)),
            "indexed_documents": len(index_rows)}
    (work_dir / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    if not execute:
        return {"selected_chunks": len(ids), "estimated_tokens": estimate["estimated_tokens"],
                "workers": max(1, min(16, workers)), "indexed_documents": len(index_rows)}
    if estimate["estimated_tokens"] > 200000:
        raise ValueError(f"estimated tokens {estimate['estimated_tokens']} exceed limit 200000")

    from .llm_adapter import create_llm_call
    from .batch import run_batch, summarize_batch
    from .verify import verify_results
    from ..graph.export import export_files

    ids_file = work_dir / "selected.json"
    ids_file.write_text(json.dumps(ids) + "\n", encoding="utf-8")
    result_dir = work_dir / "results"
    call = create_llm_call(model, temperature=temperature)
    run = run_batch(sorted(chunk_dir.glob("*.chunks.json")), call, result_dir, chunk_ids=ids, workers=workers)
    summary = summarize_batch(sorted(chunk_dir.glob("*.chunks.json")), result_dir, chunk_ids=ids)
    verification = verify_results(result_dir, chunk_dir, work_dir / "verification")
    graph = export_files(result_dir, chunk_dir, index_csv.parent, model, work_dir / "graph")
    details = {"plan": plan, "run_documents": len(run["documents"]),
               "summarized_documents": len(summary["documents"]), "verification": verification,
               "graph_nodes": graph.get("nodes", 0), "graph_edges": graph.get("edges", 0)}
    (work_dir / "summary.json").write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    return {"chunks": len(ids), "estimated_tokens": estimate["estimated_tokens"],
            "verified_chunks": verification["chunks"], "graph_nodes": details["graph_nodes"],
            "graph_edges": details["graph_edges"]}
