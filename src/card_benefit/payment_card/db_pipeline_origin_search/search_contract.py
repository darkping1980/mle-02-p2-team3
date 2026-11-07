"""Shared value objects and text helpers for the Neo4j-only search path."""
from __future__ import annotations

from dataclasses import dataclass, field
import re


FETCH_PER_TABLE = 20
RRF_K = 60
PARTICLES = re.compile(r"(에서|에게|으로|에는|으로|까지|부터|이나|이나|은|는|이|가|을|를|에|와|과|도|만)$")
STOPWORDS = frozenset({"카드", "혜택", "있는", "하는", "좋은", "무엇", "어떤", "있어", "알려줘", "서비스가"})


@dataclass
class SearchHit:
    """A typed candidate returned by Neo4j keyword/vector fusion."""
    source: str
    key: str
    benefit_id: str
    bnft_cd: str
    bnft_nm: str
    bnft_type_cd: str | None
    cards: list[dict]
    applied: bool
    search_txt: str | None = None
    similarity: float | None = None
    keyword_score: int = 0
    origin: str | None = None
    channels: list[str] = field(default_factory=list)
    graph_targets: list[str] = field(default_factory=list)
    target_terms: list[str] = field(default_factory=list)
    excluded_terms: list[str] = field(default_factory=list)


@dataclass
class SearchOutcome:
    """Candidates plus timing and diagnostics from a Neo4j hybrid search."""
    mode: str
    hits: list[SearchHit]
    elapsed_ms: float
    merged_duplicates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    engines: list[str] = field(default_factory=list)


def search_terms(question: str) -> list[str]:
    """Extract distinct search tokens without inferring synonyms."""
    terms = []
    for word in re.findall(r"[0-9A-Za-z가-힣]+", question):
        word = PARTICLES.sub("", word) if len(word) > 2 else word
        if len(word) >= 2 and word not in STOPWORDS and word not in terms:
            terms.append(word)
    return terms
