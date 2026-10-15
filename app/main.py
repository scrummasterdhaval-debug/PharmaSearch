"""PharmaSearch HTTP API: compliance document search."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import Settings
from .corpus import load_corpus
from .index import SearchIndex
from .logging_config import configure_logging

logger = logging.getLogger("pharmasearch")

settings = Settings.from_env()
configure_logging(settings.log_level)


class SearchResult(BaseModel):
    id: str
    title: str
    citation: str
    jurisdiction: str
    effective_date: str
    tags: list[str]
    score: float
    snippet: str


class SearchResponse(BaseModel):
    query: str
    jurisdiction: str | None = None
    total: int = Field(description="Number of documents that matched before the limit was applied")
    results: list[SearchResult]
    took_ms: float


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the index once at startup, not per request.

    A cold container pays this cost exactly once; readiness stays false until
    it succeeds, so a broken corpus never receives traffic.
    """
    app.state.index = SearchIndex(load_corpus(settings.corpus_path))
    logger.info(
        "index ready",
        extra={"context": {"documents": len(app.state.index), "environment": settings.environment}},
    )
    yield
    app.state.index = None


app = FastAPI(
    title="PharmaSearch",
    description="Search engine for pharmaceutical compliance documents.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Tag every request with an id and log its outcome as one JSON line."""
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["x-request-id"] = request_id
    logger.info(
        "request",
        extra={
            "context": {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
            }
        },
    )
    return response


def get_index(request: Request) -> SearchIndex:
    index = getattr(request.app.state, "index", None)
    if index is None:
        raise HTTPException(status_code=503, detail="index not ready")
    return index


@app.get("/healthz", tags=["ops"])
def healthz() -> dict[str, str]:
    """Liveness: the process is up. Cheap on purpose — no index touched."""
    return {"status": "ok"}


@app.get("/readyz", tags=["ops"])
def readyz(request: Request) -> JSONResponse:
    """Readiness: the index is built and the service can answer queries."""
    index = getattr(request.app.state, "index", None)
    if index is None:
        return JSONResponse(status_code=503, content={"status": "unready"})
    return JSONResponse(content={"status": "ready", "documents": len(index)})


@app.get("/search", response_model=SearchResponse, tags=["search"])
def search(
    q: str = Query(min_length=1, max_length=256, description="Free-text compliance query"),
    jurisdiction: str | None = Query(default=None, description="Filter to US, EU, ICH, WHO…"),
    limit: int = Query(default=10, ge=1),
    index: SearchIndex = Depends(get_index),
) -> SearchResponse:
    if limit > settings.max_limit:
        raise HTTPException(status_code=422, detail=f"limit may not exceed {settings.max_limit}")

    started = time.perf_counter()
    hits = index.search(q, limit=limit, jurisdiction=jurisdiction)
    took_ms = (time.perf_counter() - started) * 1000

    return SearchResponse(
        query=q,
        jurisdiction=jurisdiction,
        total=len(hits),
        took_ms=round(took_ms, 3),
        results=[
            SearchResult(
                id=hit.document.id,
                title=hit.document.title,
                citation=hit.document.citation,
                jurisdiction=hit.document.jurisdiction,
                effective_date=hit.document.effective_date,
                tags=list(hit.document.tags),
                score=hit.score,
                snippet=hit.snippet,
            )
            for hit in hits
        ],
    )
