"""Compare repeated extraction result folders using counts and quote-free keys."""
from __future__ import annotations

import json
import statistics
import unicodedata
from pathlib import Path

GROUPS = ("benefits", "conditions", "limits", "targets", "relations")


def _norm(value):
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return " ".join(value.split())


def _item_keys(result):
    keys = set()
    extraction = result.get("extraction") or {}
    for group in GROUPS:
        for item in extraction.get(group, []):
            fields = ("name", "text", "kind")
            keys.add((group, *(_norm(item.get(field)) for field in fields)))
    return keys


def _load(directory):
    found = {}
    for path in Path(directory).glob("*.result.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        if item.get("chunk_id") is not None:
            found[item["chunk_id"]] = item
    return found


def compare_variance(result_dirs, output_dir):
    if len(result_dirs) < 2:
        raise ValueError("variance에는 결과 폴더가 2개 이상 필요합니다.")
    runs = [_load(p) for p in result_dirs]
    ids = sorted(set().union(*(run.keys() for run in runs)))
    rows = []
    for chunk_id in ids:
        results = [run.get(chunk_id) for run in runs]
        counts = [sum(len((r.get("extraction") or {}).get(g, [])) for g in GROUPS) if r else 0 for r in results]
        cv = statistics.pstdev(counts) / statistics.mean(counts) if statistics.mean(counts) else 0.0
        keysets = [_item_keys(r) if r else set() for r in results]
        pairs = []
        for i in range(len(keysets)):
            for j in range(i + 1, len(keysets)):
                union = keysets[i] | keysets[j]
                pairs.append(len(keysets[i] & keysets[j]) / len(union) if union else 1.0)
        success = [bool(r and r.get("extraction") is not None and not r.get("failures")) for r in results]
        rows.append({"chunk_id": chunk_id, "item_count_min": min(counts), "item_count_max": max(counts),
                     "item_count_cv": round(cv, 6), "item_set_jaccard": round(statistics.mean(pairs), 6) if pairs else 1.0,
                     "success_agreement": round(max(success.count(True), success.count(False)) / len(success), 6),
                     "success_varies": int(len(set(success)) > 1),
                     "empty_result_in_some_runs": int(0 in counts and any(c > 0 for c in counts))})
    mean_jaccard = statistics.mean(r["item_set_jaccard"] for r in rows) if rows else 0.0
    large = sum(r["item_count_cv"] >= 0.5 for r in rows)
    partial_empty = sum(r["empty_result_in_some_runs"] for r in rows)
    output_dir = Path(output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "variance.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"chunks": len(rows), "mean_jaccard": round(mean_jaccard, 6),
            "high_item_count_variation_chunks": large, "partially_empty_chunks": partial_empty}
