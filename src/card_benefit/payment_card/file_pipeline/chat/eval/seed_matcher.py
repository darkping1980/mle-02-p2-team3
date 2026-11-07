"""Deterministic, metadata-only fuzzy seed selection for retrieval evaluation."""
from __future__ import annotations

import re
from collections import Counter

_PARTICLES = ("으로", "에서", "에게", "까지", "부터", "처럼", "보다", "은", "는", "이", "가", "을", "를", "의", "에", "로", "도", "만", "과", "와")
_UNITS = (("퍼센트", "%"), ("만원", "만원"), ("천원", "천원"), ("원", "원"), ("개월", "개월"), ("달", "개월"))


def normalize(value: str) -> str:
    text = str(value).lower()
    for source, target in _UNITS:
        text = text.replace(source, target)
    words = re.findall(r"[0-9a-z가-힣%]+", text)
    normalized = []
    for word in words:
        for suffix in _PARTICLES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                word = word[:-len(suffix)]
                break
        normalized.append(word)
    return "".join(normalized)


def _grams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)} if len(text) > 1 else set()


class SeedMatcher:
    """Build reusable name statistics once, then rank candidates per question."""
    def __init__(self, nodes):
        self.nodes = list(nodes)
        self.names = sorted({str(n.get("name", "")) for n in self.nodes if n.get("label") != "Document" and len(normalize(n.get("name", ""))) > 2})
        self.norm = {name: normalize(name) for name in self.names}
        freq = Counter(self.norm.values())
        self.weight = {name: 1.0 / freq[self.norm[name]] for name in self.names}
        priority = {"Card": 4, "Benefit": 3, "Target": 1, "Condition": 0, "Limit": 0}
        self.priority = {}
        for node in self.nodes:
            name = str(node.get("name", ""))
            self.priority[name] = max(self.priority.get(name, 0), priority.get(str(node.get("label")), 0))

    def select(self, question: str, n: int = 3, *, threshold: float = 0.15) -> list[str]:
        q = normalize(question)
        if len(q) < 3 or n <= 0:
            return []
        qgrams = _grams(q)
        ranked = []
        for name in self.names:
            term = self.norm[name]
            grams = _grams(term)
            if not grams:
                continue
            overlap = len(grams & qgrams) / len(grams | qgrams)
            containment = 1.0 if term in q else 0.0
            score = max(overlap, containment * 0.72) * self.weight[name]
            if score >= threshold:
                label_priority = self.priority[name]
                ranked.append((name, score * (1.0 + label_priority * 0.06), label_priority))
        ranked.sort(key=lambda row: (-row[1], -row[2], row[0]))
        return [name for name, _, _ in ranked[:n]]


def select_seeds_fuzzy(nodes, question: str, n: int = 3, *, threshold: float = 0.15) -> list[str]:
    return SeedMatcher(nodes).select(question, n, threshold=threshold)
