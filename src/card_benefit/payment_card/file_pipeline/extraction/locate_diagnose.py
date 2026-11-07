"""Classify failed quote locations without persisting quote or source text."""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

TYPES = {"a": "whitespace_only", "b": "punctuation_only", "c": "ellipsis_omission",
         "d": "partial_match", "e": "near_absent"}
_ELLIPSIS = re.compile(r"(?:…|\.{2,}|⋯|·{2,}|…+)")


def _strict(text: str) -> str:
    return "".join(c for c in text if not c.isspace() and ord(c) >= 0x20)


def _loose(text: str) -> str:
    return "".join(c for c in _strict(text) if unicodedata.category(c)[0] not in {"P", "S"})


def _max_substring(a: str, b: str) -> int:
    prev = [0] * (len(b) + 1); best = 0
    for ca in a:
        curr = [0] * (len(b) + 1)
        for j, cb in enumerate(b, 1):
            if ca == cb:
                curr[j] = prev[j - 1] + 1; best = max(best, curr[j])
        prev = curr
    return best


def classify_quote(source: str, quote: str) -> tuple[str, float]:
    q, s = _strict(quote), _strict(source)
    if q and q in s:
        return "a", 1.0
    ql, sl = _loose(quote), _loose(source)
    if ql and ql in sl:
        return "b", 1.0
    parts = [part for part in _ELLIPSIS.split(quote) if _loose(part)]
    if len(parts) >= 2:
        cursor = 0
        for part in parts:
            found = sl.find(_loose(part), cursor)
            if found < 0:
                break
            cursor = found + len(_loose(part))
        else:
            return "c", min(1.0, sum(len(_loose(p)) for p in parts) / max(len(ql), 1))
    common = _max_substring(ql, sl) if ql and sl else 0
    ratio = common / max(len(ql), 1)
    # A substantial contiguous span at either edge is treated as a truncation.
    edge = _longest_edge(ql, sl)
    if len(edge) >= 4 and ratio >= 0.35:
        return "d", ratio
    return "e", ratio


def _longest_edge(quote: str, source: str) -> str:
    best = ""
    for n in range(1, len(quote) + 1):
        if quote[:n] in source:
            best = quote[:n]
        if quote[-n:] in source and n > len(best):
            best = quote[-n:]
    return best


def _chunks(chunk_dir):
    chunks = {}
    for path in Path(chunk_dir).glob("*.chunks.json"):
        for chunk in json.loads(path.read_text(encoding="utf-8")).get("chunks", []):
            chunks[chunk.get("chunk_id")] = chunk
    return chunks


def diagnose_locations(result_dir, chunk_dir, output_dir):
    result_dir, output_dir = Path(result_dir), Path(output_dir)
    chunks = _chunks(chunk_dir); rows = []; counts = Counter(); by_chunk = Counter()
    for path in sorted(result_dir.glob("*.result.json")):
        result = json.loads(path.read_text(encoding="utf-8")); chunk_id = result.get("chunk_id")
        source = chunks.get(chunk_id, {}).get("text", "")
        for failure in result.get("failures", []):
            if failure.get("code") != "quote_location_failure":
                continue
            quote = failure.get("quote", "")
            kind, ratio = classify_quote(source, quote)
            row = {"chunk_id": chunk_id, "path": failure.get("path"), "type": kind,
                   "quote_length": len(quote), "max_match_ratio": round(ratio, 6)}
            rows.append(row); counts[kind] += 1; by_chunk[chunk_id] += 1
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "locate_diagnosis.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"items": rows, "by_type": {k: counts.get(k, 0) for k in TYPES}, "by_chunk": dict(sorted(by_chunk.items()))}
