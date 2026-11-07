"""Detect conflicting rate/amount values among similarly named benefits."""
from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation
from pathlib import Path
import unicodedata

NAME_SIMILARITY_THRESHOLD = 0.9
NAME_MATCH_CRITERIA = ("old", "similarity-0.9", "exact")
_GENERIC_WORDS = ("할인", "혜택", "서비스")
_VALUE_KEYS = ("rate", "amount")
_VALUE_RANGE_SEPARATOR = re.compile(r"\s*(?:~|～|〜|–|—|至|到)\s*")
_PERCENT_VALUE = re.compile(r"^(\d[\d,]*(?:\.\d+)?)\s*%$")
_MONEY_VALUE = re.compile(
    r"^(\d[\d,]*(?:\.\d+)?)\s*(천|만|千|万|萬)?\s*(원|韩元|韓元|KRW|won)$",
    re.IGNORECASE,
)


def _decimal_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _canonical_single_value(value: str) -> str | None:
    percent = _PERCENT_VALUE.fullmatch(value)
    if percent:
        try:
            return f"percent:{_decimal_text(Decimal(percent.group(1).replace(',', '')))}"
        except InvalidOperation:
            return None
    money = _MONEY_VALUE.fullmatch(value)
    if money:
        try:
            amount = Decimal(money.group(1).replace(',', ''))
        except InvalidOperation:
            return None
        multiplier = {"천": 1000, "万": 10000, "萬": 10000, "만": 10000}.get(money.group(2) or "", 1)
        return f"krw:{_decimal_text(amount * multiplier)}"
    return None


def _canonical_value(value: str) -> str:
    """Normalize common rate and KRW notation, preserving text fallback."""
    normalized = unicodedata.normalize("NFKC", value).strip()
    pieces = _VALUE_RANGE_SEPARATOR.split(normalized)
    if len(pieces) == 2:
        left, right = (_canonical_single_value(piece) for piece in pieces)
        if left is None or right is None:
            # A bare range endpoint inherits a trailing unit from its neighbor.
            left_raw, right_raw = pieces
            for unit in ("%", "천원", "만원", "千원", "万元", "万韩元", "萬韓元", "원", "韩元", "韓元", "KRW", "won"):
                if right is not None and right_raw.endswith(unit) and left is None:
                    left = _canonical_single_value(left_raw + unit)
                if left is not None and left_raw.endswith(unit) and right is None:
                    right = _canonical_single_value(right_raw + unit)
        if left is not None and right is not None:
            endpoints = sorted((left, right), key=lambda item: (item.split(":", 1)[0], Decimal(item.split(":", 1)[1])))
            return f"range:{endpoints[0]}..{endpoints[1]}"
    single = _canonical_single_value(normalized)
    return single if single is not None else f"text:{value.strip()}"


def _normalized_name(name: object) -> str:
    value = str(name or "").lower()
    value = re.sub(r"[0-9%\s]", "", value)
    for word in _GENERIC_WORDS:
        value = value.replace(word, "")
    return value


def _same_target(left: str, right: str, criterion: str = "exact") -> bool:
    a, b = _normalized_name(left), _normalized_name(right)
    if not a or not b:
        return False
    if criterion == "exact":
        return a == b
    if criterion == "old":
        return a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= 0.6
    if criterion == "similarity-0.9":
        return a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() >= NAME_SIMILARITY_THRESHOLD
    raise ValueError(f"unsupported name match criterion: {criterion}")


def _page_number(source_text: object) -> int | None:
    match = re.match(r"\s*\(p\.(\d+)\)", str(source_text or ""))
    return int(match.group(1)) if match else None


def _card_memberships(subgraph: dict, benefit_nodes: list[dict]) -> tuple[dict[str, set[str]], set[str], int]:
    nodes = list(subgraph.get("nodes") or [])
    cards = [n for n in nodes if n.get("label") == "Card"]
    offers = [e for e in (subgraph.get("edges") or []) if e.get("type") == "OFFERS"]
    card_ids = {str(n.get("id")) for n in cards if n.get("id") is not None}
    membership: dict[str, set[str]] = defaultdict(set)
    for edge in offers:
        source, target = str(edge.get("source")), str(edge.get("target"))
        if source in card_ids:
            membership[target].add(source)
    unknown = {str(n["id"]) for n in benefit_nodes
               if n.get("id") is not None and str(n["id"]) not in membership}
    return membership, unknown, len(card_ids)


def detect_value_conflicts(subgraph: dict, criterion: str = "exact") -> list[dict]:
    """Find matching targets with distinct values on different known pages.

    Names match by exact equality after lowercasing, removing digits, percent
    signs, whitespace, and generic words (할인, 혜택, 서비스). Card scope comes
    only from Card -OFFERS-> Benefit edges; nodes tied to different cards are
    never compared. Benefits without a card edge are counted as unknown. By
    default, unknown-card benefits join the sole card's scope only when the
    subgraph contains exactly one Card; with multiple cards they are excluded.
    Values are normalized for common rate and KRW notation before comparison.
    A conflict requires different canonical values on at least two distinct
    known pages. Unknown-page values are reported separately, not compared.
    Each returned group marks whether any member had an unknown card.
    """
    benefits = [n for n in (subgraph or {}).get("nodes", []) if n.get("label") == "Benefit" and n.get("id") is not None]
    memberships, unknown_ids, card_count = _card_memberships(subgraph or {}, benefits)
    by_card: dict[str, list[dict]] = defaultdict(list)
    for node in benefits:
        node_id = str(node["id"])
        member_cards = set(memberships.get(node_id, set()))
        if node_id in unknown_ids and card_count == 1:
            sole_card = next(n for n in (subgraph or {}).get("nodes", [])
                             if n.get("label") == "Card" and n.get("id") is not None)
            member_cards.add(str(sole_card["id"]))
        for card_id in member_cards:
            by_card[card_id].append(node)

    results: list[dict] = []
    for card_id in sorted(by_card):
        nodes = by_card[card_id]
        adjacency: dict[int, set[int]] = defaultdict(set)
        for i, left in enumerate(nodes):
            for j in range(i + 1, len(nodes)):
                if _same_target(str(left.get("name", "")), str(nodes[j].get("name", "")), criterion):
                    adjacency[i].add(j)
                    adjacency[j].add(i)
        unseen = set(adjacency)
        while unseen:
            root = min(unseen)
            queue = deque([root])
            component = set()
            while queue:
                index = queue.popleft()
                if index in component:
                    continue
                component.add(index)
                queue.extend(adjacency[index] - component)
            unseen -= component
            members = [nodes[i] for i in sorted(component)]
            for key in _VALUE_KEYS:
                valued = []
                for node in members:
                    props = node.get("props") or {}
                    raw = props.get(key)
                    if raw is None or not str(raw).strip():
                        continue
                    valued.append({
                        "node_id": str(node["id"]),
                        "name": str(node.get("name") or "")[:40],
                        "value": str(raw).strip(),
                        "canonical_value": _canonical_value(str(raw).strip()),
                        "page": _page_number(props.get("source_text")),
                    })
                known_by_page: dict[int, set[str]] = defaultdict(set)
                for item in valued:
                    if item["page"] is not None:
                        known_by_page[item["page"]].add(item["canonical_value"])
                pages = sorted(known_by_page)
                cross_page_difference = any(
                    left_value != right_value
                    for index, left_page in enumerate(pages)
                    for right_page in pages[index + 1:]
                    for left_value in known_by_page[left_page]
                    for right_value in known_by_page[right_page]
                )
                if cross_page_difference:
                    results.append({
                        "card_id": card_id,
                        "card_unknown": any(str(nodes[i]["id"]) in unknown_ids for i in component),
                        "node_ids": [item["node_id"] for item in valued],
                        "name": (members[0].get("name") or "")[:40],
                        "value_key": key,
                        "page_unknown_count": sum(item["page"] is None for item in valued),
                        "values": valued,
                    })
    return results


def _safe_output(path: Path) -> Path:
    result = path.expanduser().resolve()
    if Path("/tmp").resolve() not in result.parents:
        raise ValueError("outputs must be under /tmp")
    return result


def _question_subgraph(question: dict, nodes: list[dict], edges: list[dict], matcher, retrieve) -> dict:
    # Reuse the offline CSV graph traversal used by entity_dup_probe.
    seeds = matcher.select(str(question.get("question", "")), n=3, threshold=0.15)
    return retrieve(nodes, edges, seeds)


def run(questions_path: Path, hana_dir: Path, woori_dir: Path, json_output: Path,
        csv_output: Path | None = None, dev_questions_path: Path | None = None,
        final_questions_path: Path | None = None, criterion: str = "exact") -> dict:
    try:
        from .entity_dup_probe import _retrieve as retrieve, load_graph
        from .seed_matcher import SeedMatcher
    except ImportError:  # Script-style import from this directory.
        from entity_dup_probe import _retrieve as retrieve, load_graph
        from seed_matcher import SeedMatcher
    questions = json.loads(questions_path.read_text(encoding="utf-8"))["questions"]
    split_by_id = {}
    for split_name, split_path in (("dev", dev_questions_path), ("final", final_questions_path)):
        if split_path is not None:
            split_by_id.update({q.get("id"): split_name for q in json.loads(split_path.read_text(encoding="utf-8"))["questions"]})
    nodes, edges, _evidence = load_graph((hana_dir, woori_dir))
    matcher = SeedMatcher(nodes)
    rows = []
    for question in questions:
        subgraph = _question_subgraph(question, nodes, edges, matcher, retrieve)
        conflicts = detect_value_conflicts(subgraph, criterion=criterion)
        benefit_nodes = [n for n in subgraph.get("nodes", []) if n.get("label") == "Benefit"]
        _memberships, unknown_ids, card_count = _card_memberships(subgraph, benefit_nodes)
        page_unknown_values = sum(
            1 for node in benefit_nodes
            for key in _VALUE_KEYS
            if (node.get("props") or {}).get(key) is not None
            and str((node.get("props") or {}).get(key)).strip()
            and _page_number((node.get("props") or {}).get("source_text")) is None
        )
        evidence_doc = str(question.get("evidence_doc", ""))
        if evidence_doc:
            card_name = Path(evidence_doc).stem
            card_name = re.sub(r"^(신용|체크)_", "", card_name)
            card_name = re.split(r"_상품설명서|_공식PDF|_g1_", card_name, maxsplit=1)[0]
            card_name = re.sub(r"_\d{4,}$", "", card_name)
        else:
            cards = [n.get("name", "") for n in subgraph["nodes"] if n.get("label") == "Card"]
            card_name = cards[0] if cards else ""
        rows.append({"id": question.get("id", ""), "split": split_by_id.get(question.get("id"), "unassigned"),
                     "card_name": card_name[:40], "card_unknown_benefit_count": len(unknown_ids),
                     "card_unknown_excluded_count": len(unknown_ids) if card_count != 1 else 0,
                     "page_unknown_value_count": page_unknown_values,
                     "conflict_group_count": len(conflicts),
                     "has_conflicts": bool(conflicts), "conflicts": conflicts})

    def summarize(items: list[dict]) -> dict:
        total = len(items)
        affected = sum(row["has_conflicts"] for row in items)
        return {"questions": total, "questions_with_conflicts": affected,
                "ratio": affected / total if total else 0.0,
                "conflict_groups": sum(row["conflict_group_count"] for row in items),
                "page_unknown_values": sum(row["page_unknown_value_count"] for row in items)}

    splits = {name: [r for r in rows if r["split"] == name] for name in ("dev", "final")}
    top = sorted((r for r in rows if r["has_conflicts"]),
                 key=lambda row: (-row["conflict_group_count"], row["id"]))[:5]
    result = {
        "method": {"seed_selector": "SeedMatcher(n=3, threshold=0.15)", "hops": _probe_hops(),
                   "name_match_criterion": criterion,
                   "approximations": ["LLM start-node selection replaced by deterministic SeedMatcher", "fixed two-hop CSV traversal"]},
        "all": summarize(rows), "dev": summarize(splits["dev"]), "final": summarize(splits["final"]),
        "top_questions": [{"id": r["id"], "card_name": r["card_name"]} for r in top],
        "questions": rows,
    }
    json_path = _safe_output(json_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if csv_output is not None:
        csv_path = _safe_output(csv_output)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["id", "split", "card_name", "card_unknown_benefit_count",
                                                        "card_unknown_excluded_count", "page_unknown_value_count",
                                                        "has_conflicts", "conflict_group_count"])
            writer.writeheader()
            writer.writerows({key: row[key] for key in writer.fieldnames} for row in rows)
    return result


def _probe_hops() -> int:
    try:
        from .entity_dup_probe import HOPS
    except ImportError:
        from entity_dup_probe import HOPS
    return HOPS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", required=True, type=Path)
    parser.add_argument("--dev-questions", type=Path)
    parser.add_argument("--final-questions", type=Path)
    parser.add_argument("--hana-dir", required=True, type=Path)
    parser.add_argument("--woori-dir", required=True, type=Path)
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--csv-output", type=Path)
    parser.add_argument("--name-match", choices=NAME_MATCH_CRITERIA, default="exact")
    args = parser.parse_args(argv)
    result = run(args.questions, args.hana_dir, args.woori_dir, args.json_output, args.csv_output,
                 args.dev_questions, args.final_questions, args.name_match)
    print(json.dumps({key: result[key] for key in ("all", "dev", "final", "top_questions")}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
