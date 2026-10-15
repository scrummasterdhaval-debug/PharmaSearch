"""An in-process BM25 index over the compliance corpus.

Deliberately dependency-free: the whole point of the cloud slice is that a
container starts cold, builds this index in milliseconds, and serves traffic
without a vector database or an external search cluster to pay for.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from .corpus import Document
from .synonyms import expand

# BM25 free parameters: k1 controls term-frequency saturation, b the length
# normalisation. These are the standard defaults and are good enough until we
# have relevance judgements to tune against.
K1 = 1.5
B = 0.75

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, keeping dotted citations like `211.100` intact."""
    return _TOKEN.findall(text.lower())


@dataclass(frozen=True)
class SearchHit:
    document: Document
    score: float
    snippet: str


class SearchIndex:
    def __init__(self, documents: list[Document]) -> None:
        self._documents = {doc.id: doc for doc in documents}
        self._tokens: dict[str, list[str]] = {}
        self._term_frequencies: dict[str, Counter[str]] = {}
        self._document_frequency: Counter[str] = Counter()
        postings: defaultdict[str, set[str]] = defaultdict(set)

        for doc in documents:
            tokens = tokenize(doc.searchable_text)
            self._tokens[doc.id] = tokens
            self._term_frequencies[doc.id] = Counter(tokens)
            for term in set(tokens):
                postings[term].add(doc.id)

        self._postings = {term: frozenset(ids) for term, ids in postings.items()}
        self._document_frequency = Counter({term: len(ids) for term, ids in self._postings.items()})
        lengths = [len(t) for t in self._tokens.values()]
        self._average_length = sum(lengths) / len(lengths) if lengths else 0.0

    def __len__(self) -> int:
        return len(self._documents)

    def _idf(self, term: str) -> float:
        n = len(self._documents)
        df = self._document_frequency.get(term, 0)
        # Smoothed IDF; the +1 keeps the value positive for terms that appear
        # in more than half the corpus, which a small corpus hits easily.
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def _score(self, doc_id: str, weighted_terms: dict[str, float]) -> float:
        frequencies = self._term_frequencies[doc_id]
        length = len(self._tokens[doc_id])
        score = 0.0
        for term, weight in weighted_terms.items():
            tf = frequencies.get(term, 0)
            if not tf:
                continue
            denominator = tf + K1 * (1 - B + B * length / self._average_length)
            score += weight * self._idf(term) * (tf * (K1 + 1)) / denominator
        return score

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        jurisdiction: str | None = None,
    ) -> list[SearchHit]:
        query_terms = tokenize(query)
        if not query_terms:
            return []

        # Bridge colloquial phrasing to regulatory vocabulary before matching.
        weighted_terms = expand(query_terms)

        candidates: set[str] = set()
        for term in weighted_terms:
            candidates |= self._postings.get(term, frozenset())

        hits = []
        for doc_id in candidates:
            doc = self._documents[doc_id]
            if jurisdiction and doc.jurisdiction.lower() != jurisdiction.lower():
                continue
            score = self._score(doc_id, weighted_terms)
            if score <= 0:
                continue
            hits.append(SearchHit(document=doc, score=round(score, 4), snippet=self._snippet(doc, query_terms)))

        # Sort by score, then by id so equal scores produce a stable page order
        # across replicas — otherwise pagination in the cloud is non-deterministic.
        hits.sort(key=lambda hit: (-hit.score, hit.document.id))
        return hits[:limit]

    @staticmethod
    def _snippet(document: Document, query_terms: list[str], window: int = 240) -> str:
        """Return the passage around the first query-term match."""
        text = document.text
        wanted = set(query_terms)
        for match in _TOKEN.finditer(text.lower()):
            if match.group() in wanted:
                start = max(0, match.start() - window // 3)
                end = min(len(text), start + window)
                prefix = "…" if start > 0 else ""
                suffix = "…" if end < len(text) else ""
                return f"{prefix}{text[start:end].strip()}{suffix}"
        return text[:window].strip() + ("…" if len(text) > window else "")
