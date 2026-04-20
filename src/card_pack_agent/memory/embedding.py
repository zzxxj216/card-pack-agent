"""Text embedding — OpenAI-compat endpoint via jiekou proxy.

Default model: text-embedding-3-small (1536 dim, $0.02/1M tokens).

In mock mode we fall back to `fake_embed` (hash-based) so retrieval paths
don't crash. In dev/prod we call the OpenAI-compat `/v1/embeddings` endpoint.

An LRU cache dedups repeat calls — embedding the same topic twice (e.g. during
backfill + retrieve) should not round-trip twice.
"""
from __future__ import annotations

from functools import lru_cache

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import settings

log = structlog.get_logger()


def _resolved_base_url() -> str:
    return (settings.embedding_base_url or settings.jiekou_base_url).rstrip("/")


def _resolved_api_key() -> str:
    return settings.embedding_api_key or settings.jiekou_api_key


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, max=15),
    reraise=True,
)
def _call_embeddings(texts: list[str]) -> list[list[float]]:
    key = _resolved_api_key()
    if not key:
        raise RuntimeError(
            "embedding_api_key / jiekou_api_key missing; cannot call real embeddings"
        )
    url = f"{_resolved_base_url()}/v1/embeddings"
    payload = {"model": settings.embedding_model, "input": texts}
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
    items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
    return [item["embedding"] for item in items]


@lru_cache(maxsize=2048)
def _cached_embed(text: str) -> tuple[float, ...]:
    if settings.is_mock:
        from .vector import fake_embed
        return tuple(fake_embed(text, dim=settings.embedding_dim))
    vec = _call_embeddings([text])[0]
    if len(vec) != settings.embedding_dim:
        log.warning(
            "embedding.dim_mismatch",
            got=len(vec), expected=settings.embedding_dim, model=settings.embedding_model,
        )
    return tuple(vec)


def embed_text(text: str) -> list[float]:
    """Single text → embedding vector. Cached per process."""
    return list(_cached_embed(text or ""))
