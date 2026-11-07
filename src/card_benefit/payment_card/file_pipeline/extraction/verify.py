"""Coarse post-extraction signals; numeric-unit matching is a rough comparison only."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[5]
_GROUPS = ("benefits", "conditions", "limits", "targets")
_SHARING_KEYWORDS = ("합산", "통합", "공동", "함께 사용", "본인카드와 가족카드")


def _shared_keyword_flags(group, item):
    """Return coarse shared-limit keyword signals; this constant list is heuristic, not a semantic judgment."""
    if group != "limits":
        return []
    quote_text = " ".join(e.get("text", "") for e in item.get("evidence", []))
    has_keyword = any(keyword in quote_text for keyword in _SHARING_KEYWORDS)
    if has_keyword and item.get("shared") is False:
        return ["shared_keyword_mismatch"]
    if not has_keyword and item.get("shared") is True:
        return ["shared_flag_without_keyword"]
    return []


def _numbers(text):
    values = set()
    for raw, unit in re.findall(r"([\d,]+(?:\.\d+)?)\s*(억|만|천|원|%)?", str(text)):
        if not raw:
            continue
        try:
            n = float(raw.replace(",", ""))
        except ValueError:
            continue
        values.add((n * {"억": 100000000, "만": 10000, "천": 1000}.get(unit, 1), unit == "%"))
    return values


def _item_values(group, item):
    if group == "benefits":
        return [item.get("rate"), item.get("amount")]
    if group == "conditions":
        return [item.get("min_amount")]
    if group == "limits":
        return [item.get("amount")]
    return []


def verify_results(result_dir, chunk_dir, output_dir):
    result_dir, chunk_dir, output_dir = [Path(p).expanduser().resolve() for p in (result_dir, chunk_dir, output_dir)]
    if output_dir == _REPO_ROOT or _REPO_ROOT in output_dir.parents:
        raise ValueError("검증 출력 폴더는 저장소 밖이어야 합니다.")
    chunks = {}
    for path in chunk_dir.glob("*.chunks.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        chunks.update({c.get("chunk_id"): c for c in doc.get("chunks", [])})
    output_dir.mkdir(parents=True, exist_ok=True)
    counts = Counter(); flagged_chunks = 0; processed = 0
    for path in sorted(result_dir.glob("*.result.json")):
        result = json.loads(path.read_text(encoding="utf-8")); extraction = result.get("extraction")
        if extraction is None:
            continue
        chunk = chunks.get(result.get("chunk_id"), {}); source = chunk.get("text", "")
        items = {item.get("id"): (group, item) for group in _GROUPS for item in extraction.get(group, [])}
        connected = set()
        for rel in extraction.get("relations", []):
            connected.update((rel.get("source"), rel.get("target")))
        flags = []
        for group, item in ((g, i) for g in _GROUPS for i in extraction.get(g, [])):
            item_id = item.get("id")
            quote_text = " ".join(e.get("text", "") for e in item.get("evidence", []))
            flags.extend({"item_id": item_id, "code": code} for code in _shared_keyword_flags(group, item))
            for value in _item_values(group, item):
                if value is None:
                    continue
                nums = _numbers(value)
                if nums and not nums.issubset(_numbers(quote_text)):
                    flags.append({"item_id": item_id, "code": "numeric_not_in_quote"})
                    break
            if item_id not in connected:
                flags.append({"item_id": item_id, "code": "unlinked_item"})
        quote_total = quote_bad = 0
        for group in (*_GROUPS, "relations"):
            for item in extraction.get(group, []):
                for evidence in item.get("evidence", []):
                    quote_total += 1
                    quote_bad += evidence.get("location") is None
        ratio = quote_bad / quote_total if quote_total else 0
        if ratio > 0:
            flags.append({"item_id": None, "code": "ambiguous_or_missing_quotes", "ratio": ratio})
        # Never compare relation evidence spans against endpoint quotes.
        out = {"chunk_id": result.get("chunk_id"), "flags": flags}
        (output_dir / f"{path.stem}.verify.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        processed += 1
        counts.update(f["code"] for f in flags)
        flagged_chunks += bool(flags)
    return {"chunks": processed, "chunks_with_flags": flagged_chunks, "flags_by_code": dict(sorted(counts.items()))}
