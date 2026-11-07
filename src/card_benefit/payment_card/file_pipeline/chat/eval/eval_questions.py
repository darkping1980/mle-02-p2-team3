"""Create deterministic, metadata-only evaluation questions from graph CSV exports."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import random

REPO_ROOT = Path(__file__).resolve().parents[6]
DEFAULT_DIRS = (Path("/tmp/fp-check-hana"), Path("/tmp/fp-check-woori"))


def _read(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def _props(row):
    try:
        value = json.loads(row.get("props") or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _safe_output(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        raise ValueError("출력은 저장소 밖(/tmp)에만 허용됩니다.")
    if Path("/tmp").resolve() not in path.parents:
        raise ValueError("출력은 /tmp 아래만 허용됩니다.")
    return path


def generate(csv_dirs=DEFAULT_DIRS, *, per_type=10, seed=20261104):
    """Return (questions, skipped_by_type), excluding ambiguous names/answers."""
    nodes_by_id, all_nodes, edges, evidences = {}, [], [], []
    for folder in map(Path, csv_dirs):
        for row in _read(folder / "fp_nodes.csv"):
            node = {**row, "props_obj": _props(row)}
            nodes_by_id[row["id"]] = node
            all_nodes.append(node)
        edges.extend(_read(folder / "fp_edges.csv"))
        evidences.extend(_read(folder / "fp_evidence.csv"))
    name_nodes = {}
    for n in all_nodes:
        name_nodes.setdefault(n["props_obj"].get("name") or n["props_obj"].get("text") or n["props_obj"].get("product_name") or n["id"], []).append(n)
    links = {}
    edges_by_id = {e["id"]: e for e in edges}
    for e in edges:
        links.setdefault((e["source_id"], e["edge_type"]), []).append(e["target_id"])
    reverse = {}
    for e in edges:
        reverse.setdefault((e["target_id"], e["edge_type"]), []).append(e["source_id"])

    adjacency = {}
    for edge in edges:
        source, target = nodes_by_id.get(edge["source_id"]), nodes_by_id.get(edge["target_id"])
        if source and target:
            adjacency.setdefault(source["id"], []).append((edge["edge_type"], target))
            adjacency.setdefault(target["id"], []).append((edge["edge_type"], source))

    def semantic_signature(node):
        attached = [(edge_type, other["node_type"], node_name_for_sig(other), other["props_obj"])
                    for edge_type, other in adjacency.get(node["id"], [])]
        return json.dumps([node["node_type"], node["props_obj"], sorted(attached, key=lambda x: (x[0], x[1], x[2]))], ensure_ascii=False, sort_keys=True, default=str)

    def node_name_for_sig(node):
        p = node["props_obj"]
        return str(p.get("name") or p.get("text") or p.get("product_name") or node["id"])

    evidence_docs_by_node = {}
    for ev in evidences:
        if ev.get("quote_status") != "located" or not ev.get("doc_sha256"):
            continue
        targets = [ev.get("node_id")] if ev.get("node_id") else []
        edge = edges_by_id.get(ev.get("edge_id")) if ev.get("edge_id") else None
        if edge:
            targets.extend((edge["source_id"], edge["target_id"]))
        for target_id in targets:
            if target_id:
                evidence_docs_by_node.setdefault(target_id, set()).add(ev["doc_sha256"])

    candidates = {kind: [] for kind in ("card_benefits", "benefit_limit", "target_benefit", "benefit_excludes", "benefit_condition", "benefit_document")}
    skipped = {k: 0 for k in candidates}

    def node_name(node):
        p = node["props_obj"]
        return str(p.get("name") or p.get("text") or p.get("product_name") or node["id"])

    def put(kind, q, expected, seeds, identities, node_names=()):
        # Duplicate display names that represent differing answers are ambiguous.
        for display in list(seeds) + [str(value) for value in expected]:
            matches = name_nodes.get(display, [])
            if len(matches) > 1 and len({semantic_signature(m) for m in matches}) > 1:
                skipped[kind] += 1
                return
        candidates[kind].append({"type": kind, "question": q, "expected": list(dict.fromkeys(map(str, expected))), "seed_entities": seeds, "expected_node_names": list(dict.fromkeys(node_names)), "_identity": identities})

    for card in (n for n in all_nodes if n["node_type"] == "Card"):
        benefits = [nodes_by_id[i] for i in links.get((card["id"], "OFFERS"), []) if i in nodes_by_id]
        if benefits:
            cn = node_name(card)
            put("card_benefits", f"{cn}의 혜택은 무엇인가요?", [node_name(b) for b in benefits], [cn], [card["id"]], [cn, *[node_name(b) for b in benefits]])
    for b in (n for n in all_nodes if n["node_type"] == "Benefit"):
        bn = node_name(b)
        for lid in links.get((b["id"], "HAS_LIMIT"), []):
            if lid in nodes_by_id:
                p = nodes_by_id[lid]["props_obj"]
                vals = [x for x in (p.get("period"), p.get("amount")) if x not in (None, "")]
                if vals: put("benefit_limit", f"{bn}의 월 한도는 얼마인가요?", [*vals], [bn], [b["id"], lid], [bn])
        for tid in links.get((b["id"], "APPLIES_TO"), []):
            if tid in nodes_by_id:
                tn = node_name(nodes_by_id[tid]); put("target_benefit", f"{tn} 대상 혜택은 무엇인가요?", [bn, tn], [tn], [tid, b["id"]], [tn, bn])
        for tid in links.get((b["id"], "EXCLUDES"), []):
            if tid in nodes_by_id:
                tn = node_name(nodes_by_id[tid]); put("benefit_excludes", f"{bn}에서 제외되는 대상은 무엇인가요?", [tn], [bn], [b["id"], tid], [bn, tn])
        for cid in links.get((b["id"], "HAS_CONDITION"), []):
            if cid in nodes_by_id:
                p = nodes_by_id[cid]["props_obj"]; text = p.get("text")
                vals = [text] if text else [str(v) for k, v in p.items() if k != "name"]
                if vals: put("benefit_condition", f"{bn}의 이용 조건은 무엇인가요?", vals, [bn], [b["id"], cid], [bn])
        for digest in sorted(evidence_docs_by_node.get(b["id"], set())):
            put("benefit_document", f"{bn}의 근거 문서 해시는 무엇인가요?", [digest[:8]], [bn], [b["id"], digest], [bn])

    rng = random.Random(seed)
    result = []
    for kind, rows in candidates.items():
        # Remove repeated identical entities whose answers disagree.
        answer_by_key = {}
        for row in rows:
            key = tuple(row["_identity"][:1]); sig = tuple(row["expected"])
            if key in answer_by_key and answer_by_key[key] != sig:
                skipped[kind] += 1
                continue
            answer_by_key[key] = sig
        unique = list({(tuple(x["_identity"]), tuple(x["expected"])): x for x in rows}.values())
        rng.shuffle(unique)
        for row in unique[:per_type]:
            row.pop("_identity", None)
            row["id"] = f"{kind}-{len(result)+1:04d}"
            result.append(row)
    return result, skipped


def write_questions(csv_dirs, output, *, per_type=10, seed=20261104):
    path = _safe_output(Path(output))
    questions, skipped = generate(csv_dirs, per_type=per_type, seed=seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"seed": seed, "questions": questions, "skipped_ambiguous": skipped}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return questions, skipped


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--hana", default=str(DEFAULT_DIRS[0])); parser.add_argument("--woori", default=str(DEFAULT_DIRS[1]))
    parser.add_argument("--output", default="/tmp/fp-chat-questions.json"); parser.add_argument("--per-type", type=int, default=10); parser.add_argument("--seed", type=int, default=20261104)
    args = parser.parse_args(argv)
    questions, skipped = write_questions([args.hana, args.woori], args.output, per_type=args.per_type, seed=args.seed)
    print(json.dumps({"output": str(_safe_output(Path(args.output))), "counts": {t: sum(q["type"] == t for q in questions) for t in sorted({q["type"] for q in questions})}, "skipped_ambiguous": skipped}, ensure_ascii=False))

if __name__ == "__main__": main()
