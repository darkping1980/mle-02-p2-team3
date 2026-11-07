"""Deterministically add question-matched Card and Benefit names to an analysis.

Card matches are resolved by longest normalized name, then lexical name. Benefit
matches are considered by longest normalized question phrase, phrase position,
then lexical candidate name; at most ``max_benefits`` are added. Existing entity
names retain their order and are never removed.
"""
from __future__ import annotations

import re

try:
    from ..eval.seed_matcher import normalize
except ImportError:  # Script-style imports from this directory.
    from eval.seed_matcher import normalize

MAX_BENEFIT_SEEDS = 3
_PARTICLES = ("으로", "에서", "에게", "까지", "부터", "처럼", "보다", "은", "는", "이", "가", "을", "를", "의", "에", "로", "도", "만", "과", "와")


def _question_phrases(question: str) -> list[tuple[int, int, str]]:
    words = re.findall(r"[0-9a-z가-힣%]+", str(question).lower())
    cleaned = []
    for word in words:
        for suffix in _PARTICLES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                word = word[:-len(suffix)]
                break
        cleaned.append(word)
    phrases = set()
    for start in range(len(cleaned)):
        for width in range(1, min(4, len(cleaned) - start) + 1):
            phrase = normalize("".join(cleaned[start:start + width]))
            if len(phrase) >= 2:
                phrases.add((start, phrase))
    return sorted(((start, phrase) for start, phrase in phrases), key=lambda row: (-len(row[1]), row[0], row[1]))


def union_seed_names(question: str, candidates: list[dict], selected: list[str] | None = None,
                     *, max_benefits: int = MAX_BENEFIT_SEEDS) -> list[str]:
    """Return selected names plus deterministic candidate matches, add-only.

    ``candidates`` has the ``name``/``label`` shape returned by
    ``rag.list_entities``. A Card is added only when its normalized name occurs
    in the normalized question; the single longest such match wins. Benefits
    whose normalized names contain a question phrase are added up to the cap.
    """
    result = list(selected or [])
    existing = set(result)
    question_norm = normalize(question)
    rows = sorted(
        ((str(row.get("name", "")), str(row.get("label", ""))) for row in candidates),
        key=lambda row: (row[0], row[1]),
    )
    cards = [(name, normalize(name)) for name, label in rows
             if label == "Card" and name and normalize(name) and normalize(name) in question_norm]
    if cards:
        card_name = sorted(cards, key=lambda row: (-len(row[1]), row[0]))[0][0]
        if card_name not in existing:
            result.append(card_name)
            existing.add(card_name)

    if max_benefits <= 0:
        return result
    phrases = _question_phrases(question)
    benefits = [(name, normalize(name)) for name, label in rows
                if label == "Benefit" and name and normalize(name)]
    ranked = []
    for name, benefit_norm in benefits:
        if name in existing:
            continue
        positions = [(rank, start) for rank, (start, phrase) in enumerate(phrases)
                     if phrase in benefit_norm]
        if positions:
            rank, start = min(positions)
            ranked.append((rank, start, name))
    ranked.sort()
    for _, _, name in ranked[:max_benefits]:
        result.append(name)
    return result
