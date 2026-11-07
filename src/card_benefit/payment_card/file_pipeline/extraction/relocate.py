"""Conservatively restore locations for unique whitespace/punctuation variants."""
from __future__ import annotations

import json
import unicodedata
from collections import Counter
from pathlib import Path

from .locate_diagnose import TYPES, _chunks, classify_quote


def _key(text):
    return "".join(c for c in text if not c.isspace() and ord(c) >= 0x20
                   and unicodedata.category(c)[0] not in "PS")


def relocate_results(result_dir, chunk_dir, output_dir):
    result_dir, output_dir = Path(result_dir), Path(output_dir)
    chunks = _chunks(chunk_dir); counts = Counter(); recovered = missed = 0
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(result_dir.glob("*.result.json")):
        result = json.loads(path.read_text(encoding="utf-8")); chunk_id = result.get("chunk_id")
        chunk = chunks.get(chunk_id, {}); source = chunk.get("text", ""); text_key = _key(source)
        failures = {(f.get("path")): f for f in result.get("failures", [])
                    if f.get("code") == "quote_location_failure"}
        for group in ("benefits", "conditions", "limits", "targets", "relations"):
            for i, item in enumerate((result.get("extraction") or {}).get(group, [])):
                for j, evidence in enumerate(item.get("evidence", [])):
                    item_path = f"{group}[{i}].evidence[{j}]"
                    failure = failures.get(item_path)
                    if failure is None:
                        continue
                    quote = failure.get("quote", evidence.get("text", ""))
                    kind, _ = classify_quote(source, quote); counts[kind] += 1
                    if kind not in {"a", "b"}:
                        missed += 1; continue
                    key = _key(quote)
                    positions = []; pos = text_key.find(key) if key else -1
                    while pos >= 0:
                        positions.append(pos); pos = text_key.find(key, pos + 1)
                    if len(positions) != 1:
                        evidence["location"] = None
                        failure["code"] = "quote_location_ambiguous" if positions else "quote_location_failure"
                        if positions:
                            failure["message"] = "정규화 인용문이 청크에서 여러 번 나타납니다."
                        missed += 1; continue
                    start_idx = positions[0]; end_idx = start_idx + len(key) - 1
                    source_map = [idx for idx, char in enumerate(source)
                                  if not char.isspace() and ord(char) >= 0x20
                                  and unicodedata.category(char)[0] not in "PS"]
                    base = chunk.get("start_pos", 1)
                    evidence["location"] = {"doc_sha256": result.get("doc_sha256"),
                        "page_no": result.get("page_no"), "start_pos": base + source_map[start_idx],
                        "end_pos": base + source_map[end_idx]}
                    result.setdefault("notes", []).append("relocated_tolerant")
                    result["failures"] = [f for f in result["failures"] if f is not failure]
                    recovered += 1
        (output_dir / path.name).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"recovered": recovered, "not_recovered": missed,
            "by_type": {k: counts.get(k, 0) for k in TYPES}}
