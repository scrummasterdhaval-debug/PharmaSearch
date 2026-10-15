"""Loading and validation of the compliance document corpus."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CORPUS = Path(__file__).parent / "data" / "documents.json"


@dataclass(frozen=True)
class Document:
    """A single compliance document in the searchable corpus."""

    id: str
    title: str
    citation: str
    jurisdiction: str
    effective_date: str
    tags: tuple[str, ...]
    text: str

    @property
    def searchable_text(self) -> str:
        return f"{self.title} {self.citation} {' '.join(self.tags)} {self.text}"


def load_corpus(path: Path | None = None) -> list[Document]:
    """Read documents from disk, failing loudly on a malformed corpus.

    A silent fallback to an empty index would make the service answer
    "no results" for every compliance query, which is worse than not starting.
    """
    source = path or DEFAULT_CORPUS
    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"corpus at {source} is empty or not a list")

    documents = []
    seen: set[str] = set()
    for entry in raw:
        missing = {"id", "title", "citation", "jurisdiction", "effective_date", "text"} - entry.keys()
        if missing:
            raise ValueError(f"document {entry.get('id', '<no id>')} missing fields: {sorted(missing)}")
        if entry["id"] in seen:
            raise ValueError(f"duplicate document id: {entry['id']}")
        seen.add(entry["id"])
        documents.append(
            Document(
                id=entry["id"],
                title=entry["title"],
                citation=entry["citation"],
                jurisdiction=entry["jurisdiction"],
                effective_date=entry["effective_date"],
                tags=tuple(entry.get("tags", [])),
                text=entry["text"],
            )
        )
    return documents
