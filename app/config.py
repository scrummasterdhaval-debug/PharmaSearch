"""Twelve-factor configuration: everything a deploy can vary comes from env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    port: int
    corpus_path: Path | None
    max_limit: int
    environment: str
    log_level: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Settings":
        source = env if env is not None else dict(os.environ)
        corpus = source.get("PHARMASEARCH_CORPUS")
        return cls(
            # Cloud Run, App Runner, Heroku and Fly all inject PORT; honouring it
            # is the difference between a container that serves and one that is
            # killed as unhealthy.
            port=int(source.get("PORT", "8080")),
            corpus_path=Path(corpus) if corpus else None,
            max_limit=int(source.get("PHARMASEARCH_MAX_LIMIT", "50")),
            environment=source.get("PHARMASEARCH_ENV", "local"),
            log_level=source.get("LOG_LEVEL", "INFO").upper(),
        )
