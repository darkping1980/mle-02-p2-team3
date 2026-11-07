"""Count quote-free item losses and additions across extraction run groups.

This tool reports counts and distributions only; it does not judge whether an
item is correct. It never writes item names, item text, evidence, or chunk text.
"""
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .table_density_report import _chunk_index, classify_density, density_score
from ..eval.variance import GROUPS, _norm

ENTITY_GROUPS = GROUPS[:-1]
FIELDS = ("name", "text", "kind")


def _similar(left: tuple, right: tuple, threshold: float) -> bool:
    """Use SequenceMatcher on normalized keys as a coarse signal, not semantic proof."""
    if left[0] != right[0]:
        return False
    a = "\x1f".join(map(str, left[1:]))
    b = "\x1f".join(map(str, right[1:]))
    return SequenceMatcher(None, a, b).ratio() >= threshold


def _load(directory: str | Path) -> dict[str, dict[str, Any]]:
    rows = {}
    for path in sorted(Path(directory).expanduser().glob("*.result.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("chunk_id") is not None:
            rows[str(row["chunk_id"])] = row
    return rows


def _entity_key(section: str, item: dict[str, Any]) -> tuple:
    fields = list(FIELDS)
    fields += {"limits": ("amount", "period", "unlimited"),
               "conditions": ("kind", "min_amount", "amount"),
               "targets": ("kind", "name")}.get(section, ())
    return section, *(_norm(item.get(field)) for field in dict.fromkeys(fields))


def _run_items(row: dict[str, Any] | None) -> dict[str, dict[tuple, dict[str, Any]]]:
    extraction = (row or {}).get("extraction") or {}
    out: dict[str, dict[tuple, dict[str, Any]]] = {g: {} for g in ENTITY_GROUPS}
    ids: dict[str, tuple] = {}
    for section in ENTITY_GROUPS:
        for item in extraction.get(section, []) or []:
            key = _entity_key(section, item)
            if not any(key[1:]):
                continue
            out[section].setdefault(key, item)
            if item.get("id") is not None:
                ids[str(item["id"])] = key
    relations = {}
    for rel in extraction.get("relations", []) or []:
        source, target = ids.get(str(rel.get("source"))), ids.get(str(rel.get("target")))
        if source is None or target is None:
            continue
        key = ("relations", source, _norm(rel.get("type")), target)
        relations.setdefault(key, rel)
    out["relations"] = relations
    return out


def _length(item_key: tuple) -> int:
    # Match variance's name/text/kind key and avoid retaining or printing values.
    if item_key[0] == "relations":
        endpoints = (item_key[1], item_key[3])
        return max((len(str(value)) for endpoint in endpoints for value in endpoint[1:] if value), default=0)
    return max((len(str(value)) for value in item_key[1:] if value), default=0)


def _length_bucket(size: int) -> str:
    return "10_or_less" if size <= 10 else "11_to_20" if size <= 20 else "21_to_40" if size <= 40 else "41_or_more"


def _category(section: str, key: tuple, item: dict[str, Any]) -> str:
    if section == "benefits":
        return str(item.get("method") or "UNKNOWN")
    if section == "conditions":
        value = str(item.get("kind") or "OTHER")
        return value if value in {"SPEND_REQ", "EXCLUDE", "USAGE", "PAYMENT", "MERCHANT", "OTHER"} else "OTHER"
    if section == "limits":
        period = str(item.get("period") or "UNKNOWN")
        return f"{period}|{'shared' if item.get('shared') else 'not_shared'}|{'unlimited' if item.get('unlimited') else 'limited'}"
    if section == "targets":
        return str(item.get("kind") or "UNKNOWN")
    return str(item.get("type") or "UNKNOWN")


def _empty_bucket() -> dict[str, Any]:
    return {"total": 0, "by_chunk": {}, "by_section": {g: 0 for g in GROUPS},
            "by_type": {g: {} for g in GROUPS}, "by_length": {k: 0 for k in ("10_or_less", "11_to_20", "21_to_40", "41_or_more")},
            "by_table_density": {k: 0 for k in ("low", "middle", "high", "unknown")}}


def _count_candidates(candidates, density_by_id):
    result = _empty_bucket()
    types = {g: Counter() for g in GROUPS}
    density_counts = Counter()
    by_chunk = Counter()
    for cid, section, key, item in candidates:
        result["total"] += 1
        by_chunk[cid] += 1
        result["by_section"][section] += 1
        types[section][_category(section, key, item)] += 1
        result["by_length"][_length_bucket(_length(key))] += 1
        density_counts[density_by_id.get(cid, "unknown")] += 1
    result["by_chunk"] = dict(sorted(by_chunk.items()))
    result["by_type"] = {g: dict(sorted(types[g].items())) for g in GROUPS}
    result["by_table_density"] = {k: density_counts[k] for k in ("low", "middle", "high", "unknown")}
    return result


def _ratios(numerator, denominator):
    sections = {section: 0.0 if not denominator["by_section"][section] else round(numerator["by_section"][section] / denominator["by_section"][section], 6) for section in GROUPS}
    types = {section: {} for section in GROUPS}
    for section in GROUPS:
        for category, base_count in denominator["by_type"][section].items():
            count = numerator["by_type"][section].get(category, 0)
            types[section][category] = round(count / base_count, 6) if base_count else 0.0
    total = round(numerator["total"] / denominator["total"], 6) if denominator["total"] else 0.0
    return {"total": total, "by_section": sections, "by_type": types}


def build_report(base_dirs: list[str | Path], compare_dirs: list[str | Path], chunk_dir: str | Path,
                 fuzzy: bool = False, fuzzy_threshold: float = 0.8) -> dict[str, Any]:
    """Count losses; optional difflib fuzzy matching is a coarse spelling signal only."""
    if not base_dirs or not compare_dirs:
        raise ValueError("기준과 비교 실행 폴더가 각각 하나 이상 필요합니다")
    if not 0 <= fuzzy_threshold <= 1:
        raise ValueError("fuzzy_threshold는 0과 1 사이여야 합니다")
    base_runs = [_load(p) for p in base_dirs]
    compare_runs = [_load(p) for p in compare_dirs]
    ids = sorted(set().union(*(r.keys() for r in (*base_runs, *compare_runs))))
    chunks = _chunk_index(chunk_dir)
    density_labels = classify_density([density_score(chunks[cid].get("text", "")) for cid in ids if cid in chunks])
    density_ids = [cid for cid in ids if cid in chunks]
    density_by_id = dict(zip(density_ids, density_labels))
    threshold = (3 * len(base_runs) + 3) // 4
    disappeared, unstable, added, stable_items, spelling, fuzzy_added, genuine = [], [], [], [], [], [], []
    unprocessed_chunks, unprocessed_items = set(), set()
    per_chunk = {}
    for cid in ids:
        unavailable = [run.get(cid) is None or run.get(cid, {}).get("extraction") is None for run in compare_runs]
        if all(unavailable):
            for run in base_runs:
                for section, values in _run_items(run.get(cid)).items():
                    unprocessed_chunks.add(cid)
                    unprocessed_items.update((cid, section, key) for key in values)
            per_chunk[cid] = {"disappeared_candidates": 0, "base_once_only": 0, "compare_only_added": 0}
            continue
        base = [_run_items(run.get(cid)) for run in base_runs]
        comp = [_run_items(run.get(cid)) for run in compare_runs]
        bcounts, ccounts = Counter(), Counter()
        bitems, citems = {}, {}
        for run in base:
            for section in GROUPS:
                for key, item in run[section].items():
                    bcounts[(section, key)] += 1
                    bitems[(section, key)] = item
        for run in comp:
            for section in GROUPS:
                for key, item in run[section].items():
                    ccounts[(section, key)] += 1
                    citems[(section, key)] = item
        stable = [(cid, sec, key, bitems[(sec, key)]) for sec, key in bcounts if bcounts[(sec, key)] >= threshold]
        stable_items.extend(stable)
        gone = [(cid, sec, key, bitems[(sec, key)]) for sec, key in bcounts if bcounts[(sec, key)] >= threshold and not ccounts[(sec, key)]]
        once = [(cid, sec, key, bitems[(sec, key)]) for sec, key in bcounts if bcounts[(sec, key)] == 1]
        new = [(cid, sec, key, citems[(sec, key)]) for sec, key in ccounts if ccounts[(sec, key)] and not bcounts[(sec, key)]]
        if fuzzy:
            base_entity = {key for (sec, key) in bcounts if sec != "relations"}
            comp_entity = {key for (sec, key) in ccounts if sec != "relations"}
            def matched_entity(key, other, left_items, right_items):
                left_item = left_items.get((key[0], key))
                right_item = right_items.get((other[0], other))
                return (left_item is not None and right_item is not None
                        and _category(key[0], key, left_item) == _category(other[0], other, right_item)
                        and (key == other or _similar(key, other, fuzzy_threshold)))
            def relation_matches(key, pool, left_items, right_items):
                return any(key[2] == other[2]
                           and matched_entity(key[1], other[1], left_items, right_items)
                           and matched_entity(key[3], other[3], left_items, right_items)
                           for other in pool)
            fuzzy_gone = []
            for candidate in gone:
                _, sec, key, _ = candidate
                found = False
                if sec == "relations":
                    found = relation_matches(key, [other for (s, other) in ccounts if s == "relations"], bitems, citems)
                else:
                    found = any(other != key and _category(sec, key, candidate[3]) == _category(sec, other, citems[(sec, other)]) and _similar(key, other, fuzzy_threshold) for other in comp_entity if other[0] == sec and (sec, other) in citems)
                if found:
                    spelling.append(candidate)
                else:
                    fuzzy_gone.append(candidate)
            genuine.extend(fuzzy_gone)
            for candidate in new:
                _, sec, key, item = candidate
                found = any(other[0] == sec and _similar(key, other, fuzzy_threshold) and _category(sec, key, item) == _category(sec, other, bitems[(sec, other)]) for other in base_entity if (sec, other) in bitems)
                if sec == "relations":
                    found = relation_matches(key, [other for (s, other) in bcounts if s == "relations"], citems, bitems)
                if found:
                    fuzzy_added.append(candidate)
        disappeared.extend(gone); unstable.extend(once); added.extend(new)
        per_chunk[cid] = {"disappeared_candidates": len(gone), "base_once_only": len(once), "compare_only_added": len(new)}
    stable_report = _count_candidates(stable_items, density_by_id)
    lost_report = _count_candidates(disappeared, density_by_id)
    once_report = _count_candidates(unstable, density_by_id)
    note = None
    if len(base_runs) == 1:
        once_report = _count_candidates([], density_by_id)
        note = "기준 실행 1개라 불안정 항목 정의 불가"
    return {"base_run_count": len(base_runs), "compare_run_count": len(compare_runs),
            "base_threshold_at_least": threshold, "threshold_rule": "ceil(3 * base_run_count / 4)",
            "counts_not_correctness": True,
            "disappeared_candidates": lost_report,
            "stable_items": stable_report,
            "disappeared_candidate_rates": _ratios(lost_report, stable_report),
            "fuzzy_enabled": fuzzy, "fuzzy_threshold": fuzzy_threshold,
            "spelling_difference_candidates": _count_candidates(spelling, density_by_id),
            "genuine_disappeared_candidates": _count_candidates(genuine if fuzzy else disappeared, density_by_id),
            "fuzzy_matched_compare_only_added": _count_candidates(fuzzy_added, density_by_id),
            "base_once_only_unstable": once_report,
            "base_once_only_unstable_note": note,
            "unprocessed_or_failed_chunks": len(unprocessed_chunks),
            "unprocessed_or_failed_item_count": len(unprocessed_items),
            "compare_only_added": _count_candidates(added, density_by_id),
            "per_chunk": per_chunk}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", nargs="+", required=True)
    parser.add_argument("--compare", nargs="+", required=True)
    parser.add_argument("--chunk-dir", required=True)
    parser.add_argument("--output", required=True, help="저장소 밖 JSON 경로")
    parser.add_argument("--fuzzy", action="store_true", help="같은 분류 안의 유사 키를 거친 표기 차이 신호로 비교")
    parser.add_argument("--fuzzy-threshold", type=float, default=0.8)
    args = parser.parse_args()
    out = Path(args.output).expanduser().resolve()
    repo = Path(__file__).resolve().parents[6]
    if out == repo or repo in out.parents:
        parser.error("출력 JSON은 저장소 밖이어야 합니다")
    report = build_report(args.base, args.compare, args.chunk_dir, fuzzy=args.fuzzy, fuzzy_threshold=args.fuzzy_threshold)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
