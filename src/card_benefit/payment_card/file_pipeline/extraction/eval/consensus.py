"""Conservative consensus can improve precision while reducing recall; it does not measure correctness."""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..schema import Extraction
from .variance import GROUPS, _norm

ENTITY_GROUPS = GROUPS[:-1]
FIELDS = ("name", "text", "kind")
_REPO_ROOT = Path(__file__).resolve().parents[6]


def _external_path(value: str | Path) -> Path:
    path = Path(value).expanduser().resolve()
    if path == _REPO_ROOT or _REPO_ROOT in path.parents:
        raise ValueError("출력 경로는 저장소 밖이어야 합니다.")
    return path


def _key(group: str, item: dict[str, Any]) -> tuple:
    return (group, *(_norm(item.get(field)) for field in FIELDS))


def _load(directory: str | Path) -> dict[str, tuple[str, dict[str, Any]]]:
    found = {}
    for path in sorted(Path(directory).glob("*.result.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        if row.get("chunk_id") is not None:
            found[str(row["chunk_id"])] = (path.name, row)
    return found


def _without_locations(extraction: dict[str, Any]) -> dict[str, Any]:
    data = json.loads(json.dumps(extraction))
    for group in (*ENTITY_GROUPS, "relations"):
        for item in data.get(group, []) or []:
            for evidence in item.get("evidence", []) or []:
                evidence.pop("location", None)
    return data


def _first_evidence(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence = [e for item in candidates for e in (item.get("evidence") or [])]
    located = next((e for e in evidence if e.get("location") is not None), None)
    return [json.loads(json.dumps(located or (evidence[0] if evidence else {"text": ""})))]


def build_consensus(runs: list[list[dict[str, Any]]], k: int = 2) -> dict[str, Any]:
    if len(runs) < 2 or not 1 <= k <= len(runs):
        raise ValueError("2개 이상 실행과 1 <= k <= 실행 수가 필요합니다.")
    by_run = [{str(r["chunk_id"]): r for r in run if r.get("chunk_id") is not None} for run in runs]
    ids = sorted(set().union(*(r.keys() for r in by_run)))
    output, failures, stats = [], [], Counter()
    for cid in ids:
        rows = [run.get(cid) for run in by_run]
        template = next((r for r in rows if r), {})
        base = {key: value for key, value in template.items() if key not in {"extraction", "failures", "notes"}}
        base["chunk_id"] = cid
        base["notes"] = list(template.get("notes") or []) + [f"consensus:k={k},runs={len(runs)}"]
        base["failures"] = []
        counts: dict[str, Counter] = {g: Counter() for g in (*ENTITY_GROUPS, "relations")}
        originals: dict[tuple, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
        run_id_maps: list[dict[str, dict[str, tuple]]] = []
        for ri, row in enumerate(rows):
            mapping = {g: {} for g in ENTITY_GROUPS}
            extraction = (row or {}).get("extraction") or {}
            for group in ENTITY_GROUPS:
                seen = set()
                for item in extraction.get(group, []) or []:
                    key = _key(group, item)
                    mapping[group][str(item.get("id"))] = key
                    originals[key].append((ri, item))
                    if key not in seen:
                        counts[group][key] += 1
                        seen.add(key)
            seen_relations = set()
            for rel in extraction.get("relations", []) or []:
                source = next((m.get(str(rel.get("source"))) for m in mapping.values() if str(rel.get("source")) in m), None)
                target = next((m.get(str(rel.get("target"))) for m in mapping.values() if str(rel.get("target")) in m), None)
                if source is None or target is None:
                    continue
                key = (source, _norm(rel.get("type")), target)
                originals[("relations", key)].append((ri, rel))
                if key not in seen_relations:
                    counts["relations"][key] += 1
                    seen_relations.add(key)
            run_id_maps.append(mapping)
        kept: dict[str, dict[tuple, dict[str, Any]]] = {g: {} for g in ENTITY_GROUPS}
        eligible = {}
        for group in ENTITY_GROUPS:
            for ri, row in enumerate(rows):
                for item_index, item in enumerate(((row or {}).get("extraction") or {}).get(group, []) or []):
                    key = _key(group, item)
                    if counts[group][key] >= k and key not in eligible:
                        eligible[key] = (ri, item_index, ENTITY_GROUPS.index(group), group)
        used_ids = set()
        for key, (_, _, _, group) in sorted(eligible.items(), key=lambda pair: pair[1]):
            candidates = sorted(originals[key], key=lambda pair: pair[0])
            chosen = json.loads(json.dumps(candidates[0][1]))
            # Runs may assign the same ID to different items; keep the earliest run's
            # item and conservatively omit later conflicting candidates.
            if chosen.get("id") in used_ids:
                continue
            used_ids.add(chosen.get("id"))
            chosen["evidence"] = _first_evidence([item for _, item in candidates])
            kept[group][key] = chosen
        relations, seen = [], set()
        for ri, row in enumerate(rows):
            for rel in ((row or {}).get("extraction") or {}).get("relations", []) or []:
                source_key = next((m.get(str(rel.get("source"))) for m in run_id_maps[ri].values() if str(rel.get("source")) in m), None)
                target_key = next((m.get(str(rel.get("target"))) for m in run_id_maps[ri].values() if str(rel.get("target")) in m), None)
                rkey = (source_key, _norm(rel.get("type")), target_key)
                if counts["relations"][rkey] < k or source_key not in kept.get(source_key[0], {}) or target_key not in kept.get(target_key[0], {}):
                    continue
                if rkey in seen:
                    continue
                chosen = json.loads(json.dumps(rel))
                chosen["source"] = kept[source_key[0]][source_key]["id"]
                chosen["target"] = kept[target_key[0]][target_key]["id"]
                chosen["evidence"] = _first_evidence([item for _, item in originals[("relations", rkey)]])
                relations.append(chosen); seen.add(rkey)
        candidate = {"schema_ver": "ONTOLOGY_V1", **{g: list(kept[g].values()) for g in ENTITY_GROUPS}, "relations": relations}
        try:
            Extraction.model_validate(_without_locations(candidate))
            base["extraction"] = candidate
            stats["valid_chunks"] += 1
        except Exception as exc:
            base["extraction"] = None
            base["failures"] = [{"code": "consensus_validation_failure", "error_type": type(exc).__name__}]
            failures.append({"chunk_id": cid, "error_type": type(exc).__name__})
            stats["invalid_chunks"] += 1
        output.append(base)
    return {"rows": output, "failures": failures, "stats": dict(stats)}


def _summary(runs, output_rows):
    groups = (*ENTITY_GROUPS, "relations")
    input_means, retained = {}, {}
    for group in groups:
        values = [len(((row.get("extraction") or {}).get(group) or [])) for run in runs for row in run if row.get("extraction") is not None]
        kept = sum(len(((row.get("extraction") or {}).get(group) or [])) for row in output_rows if row.get("extraction") is not None)
        baseline = (sum(values) / len(runs)) if runs else 0
        input_means[group] = round(baseline, 3)
        retained[group] = {"input_mean": round(baseline, 3), "retained": kept,
                           "retention_rate": round(kept / baseline, 4) if baseline else 0}
    empty = sum(row.get("extraction") is not None and not any(row["extraction"].get(g) for g in groups) for row in output_rows)
    return {"chunks": len(output_rows), "sections": retained, "empty_chunks": empty}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True, help="입력 결과 폴더 (2회 이상 반복)")
    parser.add_argument("--k", type=int, default=2)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--summary-json", required=True, help="저장소 밖 JSON 경로")
    args = parser.parse_args()
    if len(args.run) < 2:
        parser.error("--run은 2회 이상 지정해야 합니다")
    loaded = [_load(p) for p in args.run]
    all_ids = sorted(set().union(*(r.keys() for r in loaded)))
    runs = [[r[cid][1] for cid in all_ids if cid in r] for r in loaded]
    result = build_consensus(runs, args.k)
    out = _external_path(args.output_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("출력 폴더가 비어 있지 않습니다.")
    out.mkdir(parents=True, exist_ok=True)
    for row in result["rows"]:
        # Keep the first available run's filename where possible.
        cid = row["chunk_id"]
        name = next((r[cid][0] for r in loaded if cid in r), f"{cid}.result.json")
        (out / name).write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = _summary(runs, result["rows"])
    summary["validation_failures"] = len(result["failures"])
    path = _external_path(args.summary_json); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
